# ReactiveSecurityContextHolder and Identity in Reactor Context

In a **Spring Security OAuth 2.0/OIDC Resource Server** using **Spring WebFlux**, an HTTP request can pass through multiple Reactor operators, switch execution threads, and invoke asynchronous services. That changes how an application stores and accesses the **caller's identity** compared to Servlet applications using `ThreadLocal`.

In WebFlux, Spring Security provides **`ReactiveSecurityContextHolder`** to access `SecurityContext` through the **Reactor Context attached to the subscriber**. Once the Resource Server authenticates the Bearer access token, downstream components can read `Authentication` inside the reactive pipeline to verify subject, scopes, and resource permissions. However, identity is not simply “bound to the current thread”, nor may a client-supplied `sub` string be arbitrarily turned into a trusted Authentication.

This lesson focuses on:

- The difference between **ThreadLocal-based `SecurityContextHolder`** and **`ReactiveSecurityContextHolder` in Reactor Context**.
- The Bearer JWT/opaque token flow through **`SecurityWebFilterChain`**, reactive authentication, and authorization.
- Using `ReactiveSecurityContextHolder.getContext()`, `withAuthentication(...)`, `withSecurityContext(...)`, `clearContext()`, and `contextWrite(...)`.
- The rule that **Context follows the subscriber and is read at subscription time**, plus the effects of `publishOn`, `subscribeOn`, `block()`, `subscribe()`, thread pools, and out-of-Reactor callbacks.
- Reading JWT/opaque principals in controllers and services, applying **reactive method security**, protecting tenant/ownership boundaries, and testing with **StepVerifier/WebTestClient**.

Examples use modern Java, Reactor, Spring Security WebFlux, and Spring Boot. Exact APIs may vary across version lines, but security principles and the subscriber-context model must remain consistent.

## 1. WebFlux Resource Server Architectural Frame

A client calls:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

Unlike Servlet `SecurityFilterChain`, WebFlux uses **`SecurityWebFilterChain`** composed of **`WebFilter`** instances working asynchronously on requests and responses. For JWT, authentication typically includes extracting the Bearer token, invoking `ReactiveAuthenticationManager` and `ReactiveJwtDecoder`, and placing the authentication into the reactive security context.

~~~mermaid
flowchart TD
    A["HTTP GET + Bearer access token"] --> B["WebFlux WebFilter chain"]
    B --> C["AuthenticationWebFilter / Bearer token converter"]
    C --> D{"Bearer token present?"}
    D -- "Yes" --> E["ReactiveAuthenticationManager"]
    E --> F["ReactiveJwtDecoder or ReactiveOpaqueTokenIntrospector"]
    F --> G{"Token valid, right issuer/audience/time/profile?"}
    G -- "No" --> H["ServerAuthenticationEntryPoint: typically 401"]
    G -- "Yes" --> I["Authenticated Authentication"]
    I --> J["SecurityContext in Reactor Context"]
    D -- "No" --> K["Continue WebFilter chain"]
    J --> K
    K --> L["AuthorizationWebFilter"]
    L --> M{"Sufficient endpoint permissions?"}
    M -- "No" --> N["401/403 per state and handler"]
    M -- "Yes" --> O["Handler / Controller / Service"]
    O --> P["ReactiveSecurityContextHolder.getContext()"]
    P --> Q["Check business resource permissions"]
~~~

This diagram outlines the flow of responsibilities and is **not a guarantee of exact WebFilter names or ordering across every version**. Spring Security includes related filters such as `ReactorContextWebFilter` and `SecurityContextServerWebExchangeWebFilter` to coordinate the authentication context in WebFlux. `AuthenticationWebFilter` can attach the authentication result to the Reactor Context for downstream processing.

| Component | Responsibility |
| --- | --- |
| `SecurityWebFilterChain` | Configures WebFilters and security rules for WebFlux |
| `ServerHttpSecurity` | DSL for configuring reactive HTTP security |
| `ReactiveAuthenticationManager` | Authenticates requests using the reactive model |
| `ReactiveJwtDecoder` | Decodes/verifies JWT access tokens on the reactive JWT path |
| `ReactiveOpaqueTokenIntrospector` | Verifies opaque tokens via introspection and returns a principal reactively |
| `ReactiveSecurityContextHolder` | Retrieves `Mono<SecurityContext>` from Reactor Context |
| `Authentication` | Authenticated identity and authorities |
| `AuthorizationWebFilter` | Enforces `permitAll`, `authenticated`, scopes, and HTTP rules |
| Reactive method security | Enforces permissions on service methods returning `Mono`/`Flux` |

**A Resource Server validates access tokens; it does not mint new access tokens.** An OIDC **ID token** used for client login does not automatically become an API access token, even if it carries `sub` and a valid signature.

## 2. Why Is ThreadLocal Unsuitable for Holding Identity in a Reactive Pipeline?

In the synchronous Servlet model, Spring Security typically provides:

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;

Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

That approach relies primarily on a **ThreadLocal**-based `SecurityContextHolder` strategy in typical Servlet applications. A request runs on the current thread, and the framework manages setting and clearing the context for the request scope.

However, WebFlux can execute stages of the same request across **different threads**:

~~~text
Request #A
  event-loop-1: read HTTP, receive access token
      |
      v
  event-loop-1: start reactive pipeline
      |
      +-- publishOn(boundedElastic)
      |
      v
  boundedElastic-2: query or compute
      |
      v
  event-loop-3: write HTTP response
~~~

If identity were stored solely in a `ThreadLocal`, steps executing after a thread switch might fail to read the previous value or read stale state if thread-local cleanup is mishandled. This is one reason WebFlux uses **per-subscription Reactor Context** to carry information across asynchronous stages.

| Criterion | ThreadLocal-Based `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| --- | --- | --- |
| Primary scope | Current thread | Reactor subscriber/subscription |
| Access | Synchronous, current value | `Mono<SecurityContext>`, evaluated on subscribe |
| On thread switch | ThreadLocal is not automatically preserved | Reactor Context stays with the subscription across standard Reactor operators |
| Setting context | Set/Clear SecurityContextHolder per strategy | `contextWrite(...)` with a context carrying SecurityContext |
| Testing | Attach thread-local test context | `StepVerifier`/`WebTestClient` with reactive context |
| Common risk | ThreadLocal leaking across requests/threads | Losing context when leaving the reactive chain or spawning detached subscriptions |

**Do not use `SecurityContextHolder.getContext()` as the default identity source in a WebFlux reactive service.** There, `ReactiveSecurityContextHolder.getContext()` is the proper API aligned with the subscriber context managed by Spring Security.

## 3. What Is Reactor Context?

In Project Reactor, **`Context`** is a key–value structure attached to the **Subscriber**. It differs from:

- **`ThreadLocal`:** data stored on the executing thread.
- **Java local variables:** data scoped to a single method invocation/block.
- **`ServerWebExchange.getAttributes()`:** request data stored on the exchange by the framework or application code.
- **A thread pool's `Context`:** Reactor Context is not a global map belonging to a scheduler.

Reactor Context is designed as a **semantically immutable** structure: `put` returns a new context rather than mutating in place. Different subscriptions can carry different contexts even when sharing the same `Mono` or `Flux`.

Example using a non-security application key:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> requestLabel = Mono.deferContextual(contextView ->
    Mono.just(contextView.getOrDefault("requestLabel", "anonymous-request"))
);

Mono<String> flow = requestLabel
    .contextWrite(Context.of("requestLabel", "request-42"));
~~~

When `flow` is subscribed, `requestLabel` reads `request-42`. This is **custom metadata**; a string inside Reactor Context **is not automatically trustworthy for authorization**. Users or application code could arbitrarily write a plain key. Only an Authentication verified through the Spring Security pipeline may serve as a security identity.

### Context Flows Upstream from the Subscriber

A commonly misunderstood trait is that **`contextWrite(...)` affects operators upstream of it** when a subscription is created. Visualize:

~~~text
source (reads Context)
     |
     v
map / flatMap
     |
     v
contextWrite(put key)
     |
     v
subscriber

On subscribe:
subscriber -> contextWrite -> upstream source sees key
~~~

Therefore, where `contextWrite` sits in the pipeline **matters**; it is not simply a global variable assignment visible to all subsequent code.

## 4. Core API of ReactiveSecurityContextHolder

`ReactiveSecurityContextHolder` resides in:

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
~~~

Key APIs:

| API | Result / Meaning |
| --- | --- |
| `ReactiveSecurityContextHolder.getContext()` | `Mono<SecurityContext>`, reads the existing context from the subscriber |
| `ReactiveSecurityContextHolder.withAuthentication(authentication)` | Creates a Reactor `Context` carrying a `SecurityContext` for the given Authentication |
| `ReactiveSecurityContextHolder.withSecurityContext(Mono<SecurityContext>)` | Creates a Reactor `Context` carrying a SecurityContext publisher |
| `ReactiveSecurityContextHolder.clearContext()` | Reactor Context transformer function to remove the security context when applied via `contextWrite(...)` |

The exact generic signature of `withSecurityContext(...)` may use wildcards depending on the version. In common Spring Security versions, you can pass `Mono.just(securityContext)`.

### 4.1. Reading SecurityContext

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;
import reactor.core.publisher.Mono;

Mono<Authentication> currentAuthentication =
    ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()));
~~~

This is a `Mono<Authentication>`, **not** an Authentication object already materialized when the variable is declared. It only emits a value when a subscriber executes within the corresponding context.

If the subscriber has no security context, `getContext()` can complete **empty**; if the context has a null Authentication, `Mono.justOrEmpty(...)` also emits empty. On chains with anonymous authentication enabled, you may receive an `AnonymousAuthenticationToken` — do not treat it as a logged-in user simply because `isAuthenticated()` returns true.

### 4.2. Writing an Authentication into Context

~~~java
import java.util.List;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

Authentication authenticated = new UsernamePasswordAuthenticationToken(
    "alice",
    "not-used",
    List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
);

Mono<String> currentName = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName());

Mono<String> forTest = currentName.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(authenticated)
);
~~~

When `forTest` is subscribed, the upstream `currentName` publisher receives Authentication `alice` via Reactor Context.

**This example is for understanding the API and creating test fixtures**, not a production pattern for authenticating users from a raw username or client header. In an HTTP Resource Server, the Spring Security filter must verify the Bearer access token **before** establishing a trusted Authentication.

### 4.3. Writing a Complete SecurityContext

~~~java
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextImpl;
import reactor.core.publisher.Mono;

SecurityContext context = new SecurityContextImpl(authenticated);

Mono<String> name = currentName.contextWrite(
    ReactiveSecurityContextHolder.withSecurityContext(Mono.just(context))
);
~~~

`withAuthentication(...)` is a concise helper when you already have an Authentication. `withSecurityContext(...)` is useful when the framework or a fixture already has a `Mono<SecurityContext>`. Both only establish **context for upstream operators upon subscription**; they do not turn `SecurityContext` into an application-wide static variable.

### 4.4. Clearing Context Within a Subscriber Scope

~~~java
Mono<String> withoutIdentity = currentName
    .contextWrite(ReactiveSecurityContextHolder.clearContext());
~~~

This demonstrates removing the security context from the upstream portion of a publisher; without a context, `currentName` in the example completes empty. In tests, `clearContext()` is useful for verifying how a service handles missing identity. **Never use it in production to disable authentication or bypass API authorization**.

## 5. Subscription Time Is When Identity Is Read

A common mistake is expecting a call to `getContext()` to immediately return a “current request” context:

~~~java
// Not the synchronous way to retrieve Authentication:
Mono<SecurityContext> contextMono =
    ReactiveSecurityContextHolder.getContext();
~~~

The `contextMono` variable is just a **publisher**. The context is resolved when it is subscribed within the subscriber scope of an actual pipeline. Spring WebFlux and Reactor subscribe to the publisher returned by controllers/services while handling HTTP requests.

### Right: Return the Publisher for the Framework to Subscribe

~~~java
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public Mono<String> currentName() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
~~~

### Wrong: Blocking Manually Inside a Reactive Service

~~~java
// AVOID in a WebFlux reactive flow:
String name = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .block();
~~~

`block()` creates a new synchronous subscription and can block the event loop; it also does not guarantee carrying the current request's Reactor Context into that new subscription. On WebFlux threads that disallow blocking, this operation can throw a runtime exception.

### Wrong: Subscribing Manually to Run a Side Effect and Returning Early

~~~java
// AVOID: fire-and-forget, detached subscription.
ReactiveSecurityContextHolder.getContext()
    .doOnNext(ctx -> audit(ctx.getAuthentication().getName()))
    .subscribe();
~~~

Side effects may execute outside the request lifecycle, lose context, not be awaited before completion, and leave errors unhandled. Instead, **compose the audit step into the returned publisher**:

~~~java
public Mono<Void> auditCurrentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx ->
            auditService.recordUserAction(
                ctx.getAuthentication().getName()));
}
~~~

This example assumes `auditService.recordUserAction(...)` returns `Mono<Void>`. Callers must compose the publisher into the chain subscribed by WebFlux. Never write raw access tokens, refresh tokens, or unnecessary personal data to logs or audit records.

## 6. contextWrite Position Determines Which Upstream Sees the Identity

Suppose:

~~~java
Mono<String> readName = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName());
~~~

Correct placement:

~~~java
Mono<String> result = Mono.just("work")
    .then(readName)
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authenticated));
~~~

With this structure, `contextWrite` sits downstream of the entire `Mono.just(...).then(readName)` publisher, so upstream `readName` can read the context.

Error-prone placement:

~~~java
Mono<String> wrong = Mono.just("work")
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(authenticated))
    .then(readName);
~~~

Here `contextWrite` only wraps the upstream `Mono.just("work")` publisher; `readName` is a publisher chained in downstream `then(...)`, so **it is not guaranteed to see that context**.

**Do not reason as “this code appears lower in the file so the context must be present”.** Inspect the Reactor operator graph: the subscriber, `contextWrite`, and the upstream segment it affects.

### Different Subscriptions Can Carry Different Identities

~~~java
Mono<String> source = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName());

Mono<String> forAlice = source.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(aliceAuth));

Mono<String> forBob = source.contextWrite(
    ReactiveSecurityContextHolder.withAuthentication(bobAuth));
~~~

Even though both publishers share `source`, each subscription has its own context. Therefore, **never store Authentication in a static field** or shared singleton field expecting per-request synchronization.

## 7. Configuring a JWT Resource Server in WebFlux

Common Spring Boot dependencies:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Suppose the Orders API accepts JWT access tokens from an issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://auth.example.com/realms/shop
~~~

In WebFlux, Spring Security uses **reactive** components such as `ReactiveJwtDecoder`. A custom Servlet `JwtDecoder` **does not automatically replace** WebFlux's reactive decoder.

Example `SecurityWebFilterChain` configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class ReactiveApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

The `csrf(...disable())` example assumes the application is a **Bearer-only stateless** API that does not rely on browser-sent authentication cookies. For applications using cookies/sessions, evaluate CSRF thoroughly.

A JWT Resource Server must verify **signature, issuer, timestamps, audience, and token profile per contract**. Configuring `issuer-uri` does not automatically replace API-specific validators. A non-expired JWT whose `aud` targets the Payments API must not be accepted by the Orders API.

### Why Does Reactive Context Appear After Authentication?

On the JWT path, the provider/manager creates a `JwtAuthenticationToken` with `Jwt` as principal and authorities mapped from `scope`/`scp`. Spring Security's reactive web filters ensure a successful Authentication is readable by reactive publishers executing **throughout the rest of the request chain**.

You do not need to manually set:

~~~java
// DO NOT add manually in production controllers:
// SecurityContextHolder.getContext().setAuthentication(jwtAuth);
~~~

for WebFlux to recognize the user. The framework already populates the security context in the reactive pipeline after validating the access token.

## 8. Reading JWT Identity in a Controller

In an annotated WebFlux controller, you can inject the authenticated principal with `@AuthenticationPrincipal`:

~~~java
import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
class ProfileController {

    @GetMapping("/api/me")
    Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        ));
    }
}
~~~

This example assumes the endpoint only accepts authenticated JWTs with valid `sub`/`iss` claims. Never return all claims or the raw token value to clients. When an endpoint is `permitAll()`, the principal may be absent; do not use this signature without handling anonymous requests.

### Reading Authentication via Reactor Context in a Service

In a service without a controller `Jwt` parameter, use:

~~~java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Mono;

@Component
public class CurrentJwtProvider {

    public Mono<Jwt> currentJwt() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                Mono.justOrEmpty(context.getAuthentication()))
            .filter(Authentication::isAuthenticated)
            .ofType(JwtAuthenticationToken.class)
            .map(JwtAuthenticationToken::getToken)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "JWT access token required")));
    }
}
~~~

Advantages:

1. Reads the principal when the publisher **is subscribed**, respecting the subscriber context.
2. Does not mistake `AnonymousAuthenticationToken` for a JWT user.
3. Avoids unsafe casts from Authentication to Jwt.
4. When no appropriate JWT authentication exists, **emits an error** rather than assigning a default “system user”.
5. Does not use `block()` or store principals in static fields.

In production, the web/entry-point layer must map authentication errors to appropriate HTTP responses; if business logic invokes this provider outside an HTTP request flow, pass identity via an explicit contract instead of implicitly depending on HTTP context.

## 9. Principal in Opaque Tokens and Key Differences

With opaque access tokens, the Resource Server performs **reactive introspection** instead of reading a JWS. Illustrative configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://auth.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: REPLACE_WITH_RUNTIME_SECRET
~~~

And WebFlux DSL:

~~~java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults()))
~~~

This is a **separate opaque token option**—do not add it alongside JWT configuration just to “make it work” without defining how requests select between authentication mechanisms.

With opaque tokens, Authentication is typically `BearerTokenAuthentication`, and the principal is `OAuth2AuthenticatedPrincipal`. Read it as follows:

~~~java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.authentication.BearerTokenAuthentication;
import reactor.core.publisher.Mono;

public Mono<OAuth2AuthenticatedPrincipal> currentOpaquePrincipal() {
    return ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .ofType(BearerTokenAuthentication.class)
        .map(BearerTokenAuthentication::getPrincipal)
        .switchIfEmpty(Mono.error(
            new AuthenticationCredentialsNotFoundException(
                "Opaque token authentication required")));
}
~~~

Do not cast `authentication.getPrincipal()` to `Jwt` when the application has switched to opaque tokens. If a service supports both JWT and opaque tokens, translate both into a **verified domain abstraction**, such as `AuthenticatedActor(issuer, subject, clientId, tenantId, authorities)`.

| Authentication Path | Typical Authentication | Typical Principal | Identity Source |
| --- | --- | --- | --- |
| Reactive JWT | `JwtAuthenticationToken` | `Jwt` | Claims from JWT verified by `ReactiveJwtDecoder` |
| Reactive opaque token | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` | Attributes accepted by the issuer's introspector |
| Anonymous | May be `AnonymousAuthenticationToken` depending on chain | Anonymous principal | Not an authenticated user identity |

**`Authentication.getName()` does not always equal an email or internal user ID.** For JWTs it typically uses `sub`, while for opaque tokens it depends on the principal implementation. Multi-issuer systems should map **(issuer, subject)** to an internal identity rather than assuming `sub` is unique across issuers.

## 10. Reactive Method Security: Permissions Checked on Subscription

Spring Security WebFlux can enable:

~~~java
@EnableReactiveMethodSecurity
~~~

to apply expressions such as `@PreAuthorize` on reactive services. In this model, protected methods generally need to return **`Mono`/`Flux`** or a supported publisher type so the framework can weave permission checks into the reactive chain.

Example:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class OrderQueryService {

    private final CurrentActorService actors;
    private final ReactiveOrderRepository orders;

    public OrderQueryService(
            CurrentActorService actors,
            ReactiveOrderRepository orders) {
        this.actors = actors;
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> readOrder(String tenantId, String orderId) {
        return actors.currentActor()
            .flatMap(actor ->
                orders.findReadableOrder(
                    orderId, tenantId, actor.userId()))
            .map(OrderDto::from)
            .switchIfEmpty(Mono.error(new OrderNotFoundException()));
    }
}
~~~

`CurrentActorService`, `ReactiveOrderRepository`, `OrderDto`, and `OrderNotFoundException` are **application-defined components**. `findReadableOrder(...)` represents a query enforcing tenant, owner, or share checks; it is not a built-in Spring Security API.

**Scopes are only functional permissions.** Even if a token has `SCOPE_orders.read`, a user is not automatically allowed to view another user's or another tenant's order. Business policies may require:

~~~text
Order read allowed when:
  JWT/introspection is verified
  AND has SCOPE_orders.read
  AND is an active member of the tenant owning the order
  AND (is owner OR authorized manager OR holds an active READ share)
~~~

Reactive Context **propagates identity** to the service, but **does not enforce** ownership/tenant rules automatically. Database reads must be constrained by policy, and membership/share state may need live checks while the token remains valid.

### Watch Out for Self-Invocation

Reactive method security typically works through proxies/interceptors. When a method on the same object calls another `@PreAuthorize` method via `this`, the internal call may **bypass the proxy**. Never treat an annotation on a method as absolute protection for all call paths; enforce policies at proper service and repository boundaries, and test HTTP, batch, and message-consumer entry points when they operate on the same data.

## 11. Do publishOn and subscribeOn Lose Reactor Context?

An important property: **switching schedulers with standard Reactor operators does not lose Reactor Context**.

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

Mono<String> name = ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .publishOn(Schedulers.boundedElastic())
    .map(value -> value.toUpperCase());
~~~

If this publisher is subscribed within a valid security context, the subscription-bound context remains accessible via `ReactiveSecurityContextHolder` even across thread switches. Reactor handles propagating Context through its operators.

However, **`ThreadLocal` does not automatically follow** in the same way. Inside a lambda running on another thread:

~~~java
// Unreliable for reading the principal in a reactive pipeline:
// SecurityContextHolder.getContext().getAuthentication();
~~~

Reading `ReactiveSecurityContextHolder.getContext()` from **a publisher within the same reactive chain** is the right approach.

### Where Context Is Actually Lost

- Calling `.block()` on another publisher and creating an independent subscription.
- Calling `.subscribe()` fire-and-forget instead of composing with the request chain.
- Bridging to `CompletableFuture`, executors, or callbacks outside Reactor without an appropriate **context propagation** mechanism.
- Creating a new Publisher at an external boundary and subscribing without carrying context.
- Using imperative APIs that read ThreadLocal `SecurityContextHolder` on another thread.
- Placing `contextWrite(...)` in the wrong spot so the publisher reading identity is not upstream of it.

**Do not equate `publishOn` with losing Reactor Context.** The real risk usually lies in **detached subscriptions** or **bridges to systems unaware of Reactor Context**.

## 12. Integrating with Blocking APIs, Executors, and @Async

WebFlux does not mean every library beneath the service layer is non-blocking. When you must invoke a blocking API in a reactive system, offload the blocking work to an appropriate scheduler:

~~~java
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;

public Mono<OrderRecord> loadFromBlockingRepository(String id) {
    return Mono.fromCallable(() -> blockingRepository.findById(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

This is a technical pattern for protecting the event loop from blocking I/O; check the repository's actual return type, error/not-found handling, and thread bounds. **Do not call a blocking repository eagerly on the event loop** and merely tack `publishOn` onto the end of the pipeline thinking it shifted the prior work.

If identity is needed inside a blocking callback, **extract the verified identity from Reactive Context and pass it explicitly as a parameter**:

~~~java
public Mono<OrderRecord> loadOrderForCurrentUser(String id) {
    return actors.currentActor()
        .flatMap(actor ->
            Mono.fromCallable(() ->
                    blockingRepository.findVisibleOrder(
                        id, actor.userId(), actor.tenantId()))
                .subscribeOn(Schedulers.boundedElastic()));
}
~~~

Here `actors.currentActor()` must retrieve the **authenticated** identity from the request; `actor.userId()` and `tenantId()` must come from trusted identity/policy sources. Passing the actor explicitly into the callback avoids relying on ThreadLocal on the worker thread.

### @Async and CompletableFuture

An `@Async` method running on an executor or a `CompletableFuture.supplyAsync(...)` does not naturally inherit the Reactor subscriber context. If background work or auditing needs the associated actor, pass a **minimized, authorized identity/authorization context** as task data, or use an official context-propagation mechanism designed for that boundary.

Never copy a raw Bearer token into a background job for indefinite reuse. Background tasks should have their own **task identity, narrow permissions, lifetime, and appropriate authentication**.

## 13. Reactor Context Is Not an Authority Source on Its Own

Applications can place custom values into Reactor Context:

~~~java
import reactor.core.publisher.Mono;
import reactor.util.context.Context;

Mono<String> requestedTenant = Mono.deferContextual(view ->
    Mono.justOrEmpty(view.<String>getOrEmpty("requestedTenant"))
);

Mono<String> withTenant = requestedTenant
    .contextWrite(Context.of("requestedTenant", "t-7"));
~~~

However, `"requestedTenant"` here is merely **application-supplied context**. If it originates from a URL, request header, cookie, or body, it remains **potentially client-controlled input**. Never write:

~~~java
// UNSAFE:
// if (contextTenant.equals(order.getTenantId())) allow();
~~~

without verifying that the user genuinely belongs to that tenant and has rights to the order.

Distinguish:

| Data | Who Establishes It? | Can It Serve as Authorization Evidence? |
| --- | --- | --- |
| Authentication from Resource Server after token validation | Spring Security and trusted configured components | Serves as identity/functional-permission input |
| `scope`/`aud`/`iss` from a verified token | Issuer per contract | Used per authentication and authorization policies |
| `requestedTenant` from request/header/custom Context | Client or application code | Only request context; **does not prove membership** |
| Owner/tenant/share in DB | Controlled business data | Authoritative source of current relationships |
| Trace ID/correlation ID | Gateway or tracing | For observability; **not an authority** |

Never assume that “data inside Reactor Context” has been signed, verified, or tamper-protected by the framework. **Trust comes from validation steps and policies**, not from the container holding the data.

## 14. Do Not Confuse Reactor Context with MDC/Logging Context

Java logging systems typically use **MDC** backed by ThreadLocal. A pipeline switching schedulers can preserve Reactor Context while **not guaranteeing MDC on the new thread holds the expected values** without an appropriate context-propagation bridge.

Example not to trust blindly:

~~~java
Mono<String> publisher = currentJwtProvider.currentJwt()
    .publishOn(Schedulers.boundedElastic())
    .map(jwt -> {
        // An MDC ThreadLocal set on another thread may not retain its previous value.
        return jwt.getSubject();
    });
~~~

To attach correlation IDs to logs, use Reactor Context together with a logging/tracing integration supported by your **Reactor/Spring/Micrometer version**. If enabling automatic context propagation or `ContextSnapshot` at imperative boundaries, verify the bridge's configuration and lifecycle; never turn mechanisms on blindly without understanding performance impact or data leakage risks.

**Never place raw access tokens, refresh tokens, sensitive private claims, or credentials into MDC.** Trace IDs and permitted internal user IDs are fundamentally different from Bearer tokens.

## 15. Testing ReactiveSecurityContextHolder with StepVerifier

`StepVerifier` from `reactor-test` lets you subscribe to a publisher with a prepared reactive context and assert emissions and errors without starting an HTTP server.

Example of a small service:

~~~java
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.core.publisher.Mono;

public class CurrentActorService {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .flatMap(ctx ->
                Mono.justOrEmpty(ctx.getAuthentication()))
            .map(auth -> auth.getName())
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authentication required")));
    }
}
~~~

Testing with Authentication attached to the **subscriber Context**:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import reactor.test.StepVerifier;

class ReactiveCurrentActorTest {

    private final CurrentActorService service =
        new CurrentActorService();

    @Test
    void readsNameFromSubscriberSecurityContext() {
        Authentication alice = new UsernamePasswordAuthenticationToken(
            "alice",
            "unused",
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
        );

        StepVerifier.create(
                service.currentName()
                    .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                            alice)))
            .expectNext("alice")
            .verifyComplete();
    }

    @Test
    void rejectsMissingSecurityContext() {
        StepVerifier.create(service.currentName()
                .contextWrite(
                    ReactiveSecurityContextHolder.clearContext()))
            .expectError(AuthenticationCredentialsNotFoundException.class)
            .verify();
    }
}
~~~

This test verifies **reading context inside the publisher**; it does not prove a JWT or opaque token was verified. The directly constructed `UsernamePasswordAuthenticationToken` is a test fixture. In production, never construct a similar token from a request username and place it into Reactive Context.

### Testing with a JWT Principal

If a service uses `CurrentJwtProvider.currentJwt()` from Section 8, you can create a test Authentication:

~~~java
import java.time.Instant;
import java.util.List;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import reactor.test.StepVerifier;

Jwt jwt = Jwt.withTokenValue("unit-test-only")
    .header("alg", "RS256")
    .issuer("https://auth.example.com/realms/shop")
    .subject("user-42")
    .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
    .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
    .claim("scope", "orders.read")
    .build();

JwtAuthenticationToken auth = new JwtAuthenticationToken(
    jwt, List.of(new SimpleGrantedAuthority("SCOPE_orders.read")));

StepVerifier.create(new CurrentJwtProvider().currentJwt()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(auth)))
    .expectNext(jwt)
    .verifyComplete();
~~~

The string `"unit-test-only"` **is not a validly signed JWS**. Constructing Authentication directly is only suitable for testing services and context handling; it does not verify signatures, issuer, audience, `exp`, or token profiles.

## 16. WebTestClient: Testing the Real SecurityWebFilterChain

In WebFlux, the integration tool is **`WebTestClient`**. Two testing styles must be distinguished.

### 16.1. Mocking Authentication to Test Authorization

Spring Security Test supports `mockJwt()` with `WebTestClient` on compatible versions:

~~~java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;

webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders/123")
    .exchange()
    .expectStatus().isOk();
~~~

This snippet assumes the endpoint/fixture returns 200 when authorized. `mockJwt()` creates an Authentication to **test authorization**, but typically **does not pass a Bearer token through a real decoder**. Passing tests do not prove expired, wrongly signed, or wrong-issuer JWTs will be rejected.

### 16.2. Sending a Real Bearer Header, Mocking ReactiveJwtDecoder

To test **WebFilter token handling and HTTP responses**, send a real `Authorization: Bearer ...` header and mock **`ReactiveJwtDecoder`**, keeping the security chain intact.

Example using Spring Boot, `WebTestClient`, and Spring Test versions supporting `@MockitoBean`:

~~~java
import static org.mockito.Mockito.when;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.reactive.server.WebTestClient;
import reactor.core.publisher.Mono;

@SpringBootTest
@AutoConfigureWebTestClient
class WebFluxBearerResponseTest {

    @Autowired WebTestClient client;

    @MockitoBean
    ReactiveJwtDecoder jwtDecoder;

    @Test
    void missingTokenOnProtectedRouteReturns401() {
        client.get().uri("/api/orders/123")
            .exchange()
            .expectStatus().isUnauthorized()
            .expectHeader().valueMatches(
                HttpHeaders.WWW_AUTHENTICATE, "Bearer.*");
    }

    @Test
    void invalidBearerReturns401() {
        when(jwtDecoder.decode("invalid-token"))
            .thenReturn(Mono.error(new BadJwtException("Bad JWT")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("invalid-token"))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validTokenWithoutReadScopeReturns403() {
        when(jwtDecoder.decode("valid-without-scope"))
            .thenReturn(Mono.just(jwt(
                "valid-without-scope", "profile.read")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("valid-without-scope"))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void validTokenWithReadScopeReachesController() {
        when(jwtDecoder.decode("valid-with-scope"))
            .thenReturn(Mono.just(jwt(
                "valid-with-scope", "orders.read")));

        client.get().uri("/api/orders/123")
            .headers(h -> h.setBearerAuth("valid-with-scope"))
            .exchange()
            .expectStatus().isOk();
    }

    private static Jwt jwt(String value, String scope) {
        return Jwt.withTokenValue(value)
            .header("alg", "RS256")
            .issuer("https://auth.example.com/realms/shop")
            .subject("user-42")
            .issuedAt(Instant.parse("2026-01-01T00:00:00Z"))
            .expiresAt(Instant.parse("2031-01-01T00:00:00Z"))
            .claim("aud", List.of("orders-api"))
            .claim("scope", scope)
            .build();
    }
}
~~~

Preconditions for this example to run:

- The test app actually runs on **WebFlux** and configures the JWT Resource Server as in Section 7.
- A matching `GET /api/orders/123` exists; if the controller also enforces membership/ownership, prepare the matching fixture.
- `@MockitoBean` is available in your Spring Test version; on older Boot versions, use `@MockBean` if supported.
- A mocked `ReactiveJwtDecoder` only controls outcomes; **it does not verify real cryptographic signatures**.

To test JWS signatures, `iss`, `aud`, `exp`, and JWKS, write another integration test using a **real decoder**, JWTs signed with a test key, a test issuer/JWKS server, and the corresponding validators.

### You Can Also Test Reactive Context Over HTTP

A protected test endpoint can return `authentication.getName()` read from `ReactiveSecurityContextHolder`. If `WebTestClient` sends a token accepted by the mock decoder and the endpoint returns the right subject, the test proves the WebFilter **propagated Authentication into Reactor Context** for downstream reading. When a bad token is sent, the endpoint must never execute.

That is a much more meaningful test than merely constructing `Authentication` in a unit test, though it still does not replace real decoder cryptography tests.

## 17. Public Endpoints, permitAll, and Reactor Context

If a WebFlux `SecurityWebFilterChain` has:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/public/**").permitAll()
    .anyExchange().authenticated())
.oauth2ResourceServer(oauth2 ->
    oauth2.jwt(Customizer.withDefaults()))
~~~

then `permitAll` only states that **authorization requires no privileges** on `/public/**`. It **does not disable Bearer authentication by default** when a client proactively sends a token to a public endpoint.

| Public Request | Typical Behavior |
| --- | --- |
| No token | Can enter the handler without a JWT Authentication |
| Valid Bearer JWT | Filter authenticates the token and the handler may see the JWT Authentication in Reactor Context |
| Invalid/expired Bearer JWT | Filter may return **401 before permitAll allows it through** |

If the app wants public routes to **ignore any supplied Bearer tokens**, design a **separate `SecurityWebFilterChain`** or appropriate token converter instead of calling `clearContext()` in the controller. With multiple chains, verify matchers, selection order, and fallback protection for remaining paths.

### Do Not Manufacture Fallback Data as a Real User

Example:

~~~java
ReactiveSecurityContextHolder.getContext()
    .map(ctx -> ctx.getAuthentication().getName())
    .defaultIfEmpty("guest");
~~~

This may be suitable for a **display label on a public endpoint**, but `guest` must **never** be treated as an authorized identity. Endpoints requiring permissions must be guarded by filter/method policies and services, not by fallback strings deciding record access.

## 18. Distinguishing Context Errors from Business Authorization Errors

When a service fails to read an identity:

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `getContext()` completes empty | Unauthenticated request; subscriber lacks context; test missing fixture | Check `SecurityWebFilterChain` and subscription boundaries |
| `SecurityContextHolder.getContext()` returns null/anonymous in WebFlux | Reading ThreadLocal instead of Reactor Context | Use `ReactiveSecurityContextHolder` |
| Context has Authentication, but not JWT | Endpoint uses opaque tokens, anonymous auth, or another mechanism | Handle per actual principal type and policy |
| Authenticated with scope, but returns 403 | Missing another authority, method security, or tenant/owner policy | Inspect the exact authorization layer |
| Identity present in controller, lost in background callback | Spawned subscription/future outside Reactor or didn't pass actor | Compose within the chain or pass a normalized identity |
| Context intact after `publishOn`, but MDC empty | Reactor Context differs from ThreadLocal MDC | Configure appropriate tracing/context bridges |
| Tests with `.with(mockJwt())` pass, but real tokens get 401 | Mock bypasses decoder/issuer/JWKS | Test with Bearer headers and a real decoder or clear mock boundaries |

When debugging, never log raw Bearer access tokens, client secrets, or full JWT claims. Log request IDs, Authentication type, permitted issuer/subject identifiers, required authorities, and policy outcomes at appropriate levels.

## 19. Common Misconceptions

**“ReactiveSecurityContextHolder is just a newer ThreadLocal.”**  
No. It accesses SecurityContext via **Reactor subscriber Context**. The executing thread can change while the subscription context stays intact.

**“Calling getContext() returns SecurityContext immediately.”**  
No. It returns a `Mono<SecurityContext>` evaluated upon subscription.

**“publishOn or subscribeOn always loses identity.”**  
No. Standard Reactor operators preserve Reactor Context within the same subscription. The major risks are detached subscriptions and non-Reactor callbacks.

**“Calling block() to fetch Authentication is fine for convenience.”**  
Not in a WebFlux request flow: it blocks, creates a separate subscription, and does not guarantee preserving the right context.

**“Creating an Authentication from a username header and calling withAuthentication is secure enough.”**  
No. `withAuthentication` only puts an object into the context; it **does not validate tokens**. Production must go through a trusted authentication mechanism.

**“JWT and opaque tokens share the same principal type.”**  
Not by default. JWTs typically use `JwtAuthenticationToken`/`Jwt`, while opaque tokens typically use `BearerTokenAuthentication`/`OAuth2AuthenticatedPrincipal`.

**“Having SCOPE_orders.read means permission to read every order.”**  
No. Tenant, owner, sharing, and business policies must still be checked.

**“A tenant ID in Reactor Context proves the user belongs to that tenant.”**  
No. A custom context key is not proof of membership or ownership.

**“@PreAuthorize always runs even when a method calls another method on the same bean.”**  
Not guaranteed. Proxy self-invocation can bypass the interceptor; structure services and policies properly.

**“Testing with mockJwt() proves signature and expiry are checked.”**  
No. It typically creates an Authentication directly; testing the decoder requires real JWT/JWKS/validators or dedicated decoder tests.

**“permitAll stops the JWT filter from processing invalid tokens.”**  
No. A supplied Bearer token may still be validated and rejected prior to authorization.

## 20. Checklist for WebFlux Resource Servers

1. **Choose the right stack:** `SecurityWebFilterChain` + `ServerHttpSecurity` for WebFlux, never copying Servlet `HttpSecurity` verbatim.
2. **Keep the right authentication source:** `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector` with defined issuer/audience/time/profile checks.
3. **Read principals via Reactor:** use `ReactiveSecurityContextHolder.getContext()` in `Mono`/`Flux`, or `@AuthenticationPrincipal` in WebFlux controllers where appropriate.
4. **Do not rely on ThreadLocal:** `SecurityContextHolder.getContext()` is not the default way to retrieve users in reactive pipelines.
5. **Do not manually subscribe/block:** return or compose publishers so Spring WebFlux manages subscriptions.
6. **Place contextWrite carefully:** understand that it affects upstream operators at subscription time.
7. **Do not treat Reactor Context as inherently trusted:** identity must come from authentication and token validators; custom keys are merely data.
8. **Protect business logic:** scopes/authorities do not replace tenant membership, ownership, sharing, and record checks.
9. **Test at both layers:** `StepVerifier` verifies context propagation; `WebTestClient` verifies `SecurityWebFilterChain`, 401/403, and HTTP responses.
10. **Respect async boundaries:** when handing off to executors, callbacks, or background tasks, pass normalized actor data or use an explicitly designed context-propagation mechanism.

**Key takeaway:** In Spring Security WebFlux, the authenticated identity **travels with the reactive subscription**, not implicitly with the thread. `ReactiveSecurityContextHolder` is the bridge between Bearer authentication results and downstream publishers. Using it properly means **reading SecurityContext at subscription time, keeping a unified pipeline, understanding `contextWrite` scope, and never bypassing access-token verification**. Once a trusted principal is established, the Resource Server must still enforce permissions for the **specific endpoint, tenant, and business resource**.
