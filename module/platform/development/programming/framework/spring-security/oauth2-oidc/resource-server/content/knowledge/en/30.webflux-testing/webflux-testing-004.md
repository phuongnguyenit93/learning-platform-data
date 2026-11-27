# Inspecting Reactor Context and the Principal at the Handler Layer

In a **Spring Security WebFlux Resource Server**, authentication and authorization happen inside a reactive pipeline. Consequently, `SecurityContext` and the principal must be read from the current subscription's **Reactor Context**. This is an important difference compared to Spring Security Servlet, which typically uses the `ThreadLocal`-based `SecurityContextHolder`.

A WebFlux request may hop across multiple threads when using `publishOn`, `subscribeOn`, or other schedulers. The Reactor Context follows the subscriber and propagates throughout the pipeline; the current thread is not the security identity. If a service reads `SecurityContextHolder.getContext()` as in a Servlet application, the result may be empty or fail to reflect the active request.

This lesson focuses on practical questions:

- How does Spring Security put authentication into the Reactor Context?
- How do controllers obtain the principal from `@AuthenticationPrincipal` or `ServerWebExchange`?
- How do services retrieve `Authentication` from `ReactiveSecurityContextHolder`?
- How do you verify context across `flatMap`, `publishOn`, and reactive services?
- Why must you never call `block()` or manually call `subscribe()` inside a service?
- How do you write tests using `WebTestClient`, `mockJwt()`, `mockOpaqueToken()`, and real Bearer tokens?
- How do you detect context leakage between requests or subscribers?

> **Principle:** in WebFlux, propagate data and read the security principal inside the reactive chain. Use `ReactiveSecurityContextHolder` to obtain `SecurityContext`; use `@AuthenticationPrincipal` or `ServerWebExchange.getPrincipal()` at the web layer. Do not rely on `ThreadLocal` to identify the caller.

The examples use **Spring Security Servlet-independent WebFlux**, Spring WebFlux, Reactor, Java 17+, JUnit 5, and `WebTestClient`. If your application uses Spring MVC/Servlet, the reactive APIs in this lesson do not apply directly.

## 1. Why Does WebFlux Need Reactor Context?

### 1.1. ThreadLocal Fits the Traditional Servlet Model

In a typical Servlet application, a request is usually processed on a single thread for most of its lifecycle. Spring Security can store `SecurityContext` in `SecurityContextHolder`, which uses `ThreadLocal` by default:

~~~text
Servlet request
      |
      v
Servlet thread-17
      |
      +-- SecurityContextHolder.setContext(...)
      |
      +-- Controller
      |
      +-- Service
      |
      +-- SecurityContextHolder.getContext()
      |
      +-- Clear context
~~~

This model relies on a thread-bound context. If the application switches threads without a context propagation mechanism, security details may not carry over.

### 1.2. WebFlux Does Not Pin a Request to a Fixed Thread

WebFlux is designed for non-blocking processing. A single request can execute across multiple threads:

~~~text
HTTP request
    |
    v
event-loop thread A
    |
    +-- decode bearer token
    |
    +-- publishOn(scheduler B)
    |
    v
worker thread B
    |
    +-- call service
    |
    +-- flatMap(...)
    |
    v
event-loop thread C
    |
    +-- write response
~~~

If identity only lived in `ThreadLocal` on thread A, code running on threads B/C might not see that identity. Trying to keep a request on the same thread goes against reactive design and can reduce scalability.

Reactor provides a **Context** attached to the subscription. Spring Security uses it to propagate `SecurityContext` through the reactive pipeline.

### 1.3. Comparing the Two Models

| Aspect | Servlet | WebFlux |
|---|---|---|
| Common security holder | `SecurityContextHolder` | `ReactiveSecurityContextHolder` |
| Default context mechanism | `ThreadLocal` | Reactor `Context` |
| Context attachment unit | Thread | Subscriber/subscription |
| How context is retrieved | Synchronous | Reactive, returns `Mono` |
| Processing API | `SecurityFilterChain`, Servlet filters | `SecurityWebFilterChain`, WebFilters |
| Web testing | `MockMvc` | `WebTestClient` |
| Authentication API | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque introspector | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |

Do not migrate code from Servlet to WebFlux merely by changing controllers to return `Mono`. Security configuration, authentication providers, and context access must also use reactive APIs.

## 2. How Does Reactor Context Work?

Reactor `Context` is an immutable key-value structure attached to a subscriber. An operator can read the context during subscription, and the `contextWrite` operator can add or modify values for upstream operators.

Example:

~~~java
Mono<String> result =
    Mono.deferContextual(context ->
        Mono.just(context.get("requestId"))
    )
    .contextWrite(context ->
        context.put("requestId", "req-123")
    );
~~~

On subscription:

1. `contextWrite` creates a Context with `requestId=req-123`.
2. The Context is propagated upstream.
3. `deferContextual` reads the Context at subscription time.
4. The publisher emits `req-123`.

Result:

~~~text
Mono source
   |
   v
deferContextual(read requestId)
   |
   v
contextWrite(put requestId)
   |
   v
subscribe
~~~

### 2.1. Context Is Not an Application-Wide Shared Map

Context belongs to a subscription. Two concurrent requests can have two different values:

~~~java
Mono<String> requestA =
    readRequestId()
        .contextWrite(context -> context.put("requestId", "A"));

Mono<String> requestB =
    readRequestId()
        .contextWrite(context -> context.put("requestId", "B"));
~~~

Each subscription sees its own context. Do not use a static variable or mutable singleton to store the request's current username or tenant.

### 2.2. Context Is Read at Subscription Time

`Mono.just(...)` typically creates its value eagerly when the publisher is constructed. If you need to read context, use `deferContextual` or a reactive API designed to read context on subscribe.

Unsuitable example:

~~~java
// Cannot read Reactor Context at publisher assembly time this way.
String requestId = "value that needs to be read from Context";
return Mono.just(requestId);
~~~

Suitable approach:

~~~java
Mono<String> requestId() {
    return Mono.deferContextual(context ->
        Mono.just(context.getOrDefault("requestId", "unknown"))
    );
}
~~~

Do not store a request-specific value in a singleton service field. Spring services are typically used concurrently by many requests.

### 2.3. `contextWrite` Propagates Upstream

A common point of confusion is that `contextWrite` is placed near the end of the chain yet makes the Context available to operators ahead of it:

~~~java
Mono<String> pipeline =
    Mono.deferContextual(context ->
        Mono.just(context.get("caller"))
    )
    .map(String::toUpperCase)
    .contextWrite(context -> context.put("caller", "user-42"));
~~~

The context is written at the subscription boundary and upstream operators can read it. If `contextWrite` is placed on a branch outside the required subscription path, other operators may not see that value.

## 3. How Does Spring Security Put SecurityContext into Reactor Context?

In WebFlux, Spring Security uses reactive components:

- `WebFilterChainProxy`: entry point to select the `SecurityWebFilterChain`.
- `SecurityWebFilterChain`: collection of WebFilters for a request.
- `AuthenticationWebFilter`: converts credentials into authentication via a reactive manager.
- `ReactiveAuthenticationManager`: verifies credentials asynchronously.
- `ServerSecurityContextRepository`: saves/loads `SecurityContext` per application policy.
- `ReactorContextWebFilter`: puts the context from the repository into the Reactor Context.
- `ReactiveSecurityContextHolder`: API to read SecurityContext within the reactive pipeline.
- `SecurityContextServerWebExchangeWebFilter`: exposes the exchange's principal based on the security context.

Conceptual diagram:

~~~text
HTTP request
    |
    v
WebFilterChainProxy
    |
    v
SecurityWebFilterChain
    |
    v
Bearer token authentication
    |
    +-- JWT -> ReactiveJwtDecoder
    |
    +-- Opaque -> ReactiveOpaqueTokenIntrospector
    |
    v
Authentication succeeds
    |
    v
ServerSecurityContextRepository
    |
    v
ReactorContextWebFilter
    |
    v
ReactiveSecurityContextHolder
    |
    +-- Controller
    +-- Service
    +-- Reactive method security
    |
    v
HTTP response
~~~

Internal filter names and ordering may vary by version/configuration. The key takeaway is that `SecurityContext` is provided in the reactive execution context, not in a `ThreadLocal` that services must manage manually.

### 3.1. Only Successful Authentication Produces a Trusted Principal

Before a JWT/opaque token is verified, the bearer string is merely an unverified credential. After:

- JWT signature and claims validators succeed; or
- Introspection confirms the opaque token is active per contract;

Spring Security creates an authenticated `Authentication` and places it into the pipeline's security context.

Do not Base64-decode a JWT payload and manually put `sub` into the Reactor Context. Do not take `X-User-Id` or `X-Tenant-Id` from the request and use it as the principal.

### 3.2. `SecurityContext` Is Read via `ReactiveSecurityContextHolder`

Primary API:

~~~java
ReactiveSecurityContextHolder.getContext()
~~~

It returns a `Mono<SecurityContext>`, not a synchronous `SecurityContext`.

Example:

~~~java
Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName);
}
~~~

If no context is present, the `Mono` may complete empty. You can use `switchIfEmpty` or `defaultIfEmpty` per policy, but never fabricate a mock authenticated principal to mask missing authentication.

## 4. Configuring WebFlux Resource Server

A basic JWT configuration:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;

@Configuration
@EnableWebFluxSecurity
public class ApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveJwtDecoder jwtDecoder) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.jwtDecoder(jwtDecoder))
            )
            .build();
    }
}
~~~

Points to note:

- WebFlux uses `ServerHttpSecurity`, not Servlet `HttpSecurity`.
- The chain bean has type `SecurityWebFilterChain`.
- The JWT decoder has type `ReactiveJwtDecoder`.
- Authorization is configured via `authorizeExchange`.
- Token authentication runs reactively; do not call a synchronous decoder inside controllers.
- `SCOPE_*` authorities are generated per the JWT resource server converter/configuration.

If the API only uses bearer headers and does not use cookies/sessions sent automatically by browsers, you can consider a dedicated CSRF policy. Do not disable CSRF simply because the token is a JWT; evaluate the credential model first.

### 4.1. Configuring Issuer and Audience

Example properties for Reactive Resource Server:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
          audiences:
            - orders-api
~~~

Property names and capabilities depend on the Spring Boot version. If you build `ReactiveJwtDecoder` yourself, ensure issuer, audience, timestamp, signature algorithm, and token profile validators are still applied.

Do not use a Servlet `JwtDecoder` instead of `ReactiveJwtDecoder`. If you must use a blocking library to verify tokens in WebFlux, understand the impact on the event loop and offload blocking work to an appropriate scheduler; prefer framework-supported reactive decoders.

### 4.2. Opaque Token

For opaque tokens, WebFlux uses reactive introspection:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspector(reactiveOpaqueTokenIntrospector)
    )
)
~~~

`ReactiveOpaqueTokenIntrospector` returns `Mono<OAuth2AuthenticatedPrincipal>`. Do not invoke a synchronous Servlet `OpaqueTokenIntrospector` on the reactive request path if doing so performs blocking network calls on the event loop.

## 5. Retrieving the Principal in Controllers

There are several valid ways depending on what data the controller needs.

### 5.1. Using `@AuthenticationPrincipal`

When JWT authentication succeeds, the principal is typically a `Jwt`:

~~~java
package com.example.orders.api;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import java.util.Map;

@RestController
public class ProfileController {

    @GetMapping("/api/me")
    Mono<Map<String, Object>> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
            "subject", jwt.getSubject(),
            "issuer", jwt.getIssuer().toString()
        ));
    }
}
~~~

`@AuthenticationPrincipal` retrieves the principal from the current `Authentication`. In a JWT Resource Server, the principal is typically `Jwt`; not every authentication type has this principal type.

If a route can accept both JWT and opaque tokens, do not try to cast every principal to `Jwt`. Use an appropriate abstraction or accept `Authentication`.

### 5.2. Using `ServerWebExchange.getPrincipal()`

`ServerWebExchange#getPrincipal()` returns `Mono<P extends Principal>`:

~~~java
@GetMapping("/api/whoami")
Mono<String> whoAmI(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName);
}
~~~

This is useful when the controller needs a generic principal without coupling directly to `Jwt`.

In WebFlux, the principal is a reactive value. Do not call `.block()` to turn it into a synchronous object inside the controller.

### 5.3. Accessing Authentication in the Reactive Chain

You can read the full authentication:

~~~java
@GetMapping("/api/authentication")
Mono<Map<String, Object>> authentication() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(authentication -> Map.of(
            "name", authentication.getName(),
            "authenticated", authentication.isAuthenticated(),
            "authorities", authentication.getAuthorities()
                .stream()
                .map(GrantedAuthority::getAuthority)
                .toList()
        ));
}
~~~

This works well when you need `Authentication#getName()`, authorities, or the authentication type. Do not return all sensitive tokens/claims from an API just for debugging.

### 5.4. JWT Principal and Opaque Principal Differ

| Resource Server mode | Typical Authentication | Principal |
|---|---|---|
| JWT | `JwtAuthenticationToken` | `Jwt` |
| Opaque | `BearerTokenAuthentication` | `OAuth2AuthenticatedPrincipal` |

With JWT:

~~~java
JwtAuthenticationToken authentication
```

You can retrieve:

- `authentication.getToken().getSubject()`
- `authentication.getToken().getIssuer()`
- `authentication.getAuthorities()`

With opaque tokens:

~~~java
BearerTokenAuthentication authentication
```

The principal can be an `OAuth2AuthenticatedPrincipal` with attributes supplied by the introspection response.

Do not use `@AuthenticationPrincipal Jwt` on an endpoint supporting opaque tokens if the controller cannot handle other principal types. An application-defined `CallerIdentity` DTO can normalize `(issuer/source, subject, clientId, authorities)` after authentication succeeds.

## 6. Retrieving SecurityContext at the Service Layer

Controllers typically know the route and HTTP inputs. Services need the identity to enforce business logic by user/service caller, tenant, or ownership. In WebFlux, services should return `Mono`/`Flux` and read the security context inside the publisher.

### 6.1. A Service Retrieving the Current Caller

~~~java
package com.example.orders.service;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class CurrentCallerService {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }

    public Mono<Authentication> currentAuthentication() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication);
    }
}
~~~

The methods return publishers instead of fetching the identity synchronously. When called inside a request pipeline, the current subscription's context is read when the publisher executes.

### 6.2. Combining the Principal with Data Queries

~~~java
@Service
public class OrderQueryService {

    private final OrderRepository repository;

    public OrderQueryService(OrderRepository repository) {
        this.repository = repository;
    }

    public Flux<Order> findMyOrders() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .flatMapMany(repository::findByOwnerSubject);
    }
}
~~~

This assumes `OrderRepository#findByOwnerSubject` returns `Flux<Order>`. Queries should scope data by the authenticated identity. In a multi-issuer system, using `Authentication#getName()`/`sub` alone may not be enough; you need an issuer namespace or a canonical internal user ID.

### 6.3. Passing the Principal Explicitly vs. Reading from Context

There are two design approaches:

**Reading context in the service:**

~~~java
public Flux<Order> findMyOrders() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMapMany(repository::findByOwnerSubject);
}
~~~

Suitable when the service genuinely depends on the current security context and is invoked inside a request pipeline.

**Passing domain identity explicitly:**

~~~java
public Flux<Order> findOrdersFor(CallerIdentity caller) {
    return repository.findVisibleTo(caller);
}
~~~

The controller/adapter retrieves the authenticated principal, converts it to `CallerIdentity`, and passes it to the service. This makes dependencies explicit and makes the service easier to unit test. For domain services used across multiple contexts (HTTP, message consumers, scheduled jobs), passing identity explicitly is usually easier to control.

Do not pass the raw bearer token down to business services if the service only needs subject/tenant/permissions.

### 6.4. Domain Identity Adapter

Example of an application-defined data type:

~~~java
public record CallerIdentity(
    String issuer,
    String subject,
    String clientId,
    CallerKind kind
) {}

public enum CallerKind {
    USER,
    SERVICE
}
~~~

The adapter accepts a verified `Authentication` and produces a domain identity according to the token contract:

~~~java
public Mono<CallerIdentity> currentCaller() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(authentication -> {
            if (authentication instanceof JwtAuthenticationToken jwtAuth) {
                Jwt jwt = jwtAuth.getToken();

                return new CallerIdentity(
                    jwt.getIssuer().toString(),
                    jwt.getSubject(),
                    jwt.getClaimAsString("client_id"),
                    CallerKind.USER
                );
            }

            throw new AccessDeniedException(
                "Unsupported authentication type");
        });
}
~~~

This is just a skeleton for JWTs and assumes issuer/client/caller kind have been checked by validators. If the endpoint receives service tokens or opaque tokens, the adapter must handle them accordingly. Do not label every JWT as `USER`; machine tokens can represent services.

## 7. Principal in `flatMap`, `map`, and `publishOn`

A major benefit of Reactor Context is that it is not tied to the current thread. Standard reactive operators preserve the subscriber's context through the processing chain.

Example:

~~~java
public Mono<String> loadCallerName() {
    return Mono.defer(() ->
            ReactiveSecurityContextHolder.getContext()
                .map(SecurityContext::getAuthentication)
                .map(Authentication::getName)
        )
        .publishOn(Schedulers.parallel())
        .map(String::toUpperCase);
}
~~~

`publishOn` can switch downstream processing to another scheduler. The security context remains accessible via the subscription's Reactor Context.

### 7.1. Using `deferContextual` to Inspect the Context

You can read the context directly:

~~~java
Mono<String> debugCaller() {
    return Mono.deferContextual(contextView ->
        ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .defaultIfEmpty("anonymous")
    );
}
~~~

In practice, `ReactiveSecurityContextHolder.getContext()` is already the right abstraction, so services do not need to read Spring Security's internal keys from `ContextView`.

### 7.2. `flatMap` Preserves Context in Inner Publishers

~~~java
public Mono<Order> findOrder(String id) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(subject ->
            repository.findById(id)
                .filter(order -> order.getOwnerSubject().equals(subject))
        );
}
~~~

Inner publishers in the same reactive chain can read the subscription's context. However, when writing services, passing `subject` explicitly to the repository/policy usually makes the logic easier to read and test.

### 7.3. Avoid Imperative Callbacks Without Context

Risky example:

~~~java
return Mono.fromRunnable(() -> {
    // Do not assume ThreadLocal SecurityContext is present here.
    String name = SecurityContextHolder.getContext()
        .getAuthentication().getName();
});
~~~

Code inside the callback may execute on another thread without the corresponding `ThreadLocal`. Retrieve the data via `ReactiveSecurityContextHolder` inside the chain and pass the value into the callback:

~~~java
return ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication)
    .map(Authentication::getName)
    .flatMap(name ->
        Mono.fromRunnable(() -> audit(name))
            .thenReturn(name)
    );
~~~

If `audit(...)` performs blocking I/O, offload it to a scheduler suited for blocking work or use a reactive client/repository. Do not block event-loop threads.

## 8. Operations That Lose or Detach from the Reactive Context

### 8.1. Do Not Use `block()` in the Request Pipeline

Wrong:

~~~java
public String currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .block();
}
~~~

Problems:

- Introduces a blocking boundary in a non-blocking application.
- Can deadlock or throw errors when called on a Reactor non-blocking thread.
- Creates a separate subscription, no longer within the expected context/lifecycle.
- Breaks backpressure and error propagation.
- Makes cancellation hard to control.

Right:

~~~java
public Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName());
}
~~~

### 8.2. Do Not Manually Call `subscribe()` in Services

Wrong:

~~~java
public Mono<Void> createOrder(Order order) {
    repository.save(order).subscribe();
    return Mono.empty();
}
~~~

`subscribe()` creates an independent subscription. It can run outside the request lifecycle, lose proper cancellation/error handling, and miss the expected context.

Right:

~~~java
public Mono<Order> createOrder(Order order) {
    return repository.save(order);
}
~~~

The controller/WebFlux runtime will subscribe at the appropriate boundary. Services should return publishers for callers to compose using `flatMap`, `then`, `zip`, or other suitable operators.

### 8.3. Do Not Spawn Arbitrary Threads to Read Security Context

Wrong:

~~~java
new Thread(() -> {
    Authentication authentication =
        SecurityContextHolder.getContext().getAuthentication();
}).start();
~~~

The new thread does not automatically inherit the request's Reactor Context. If work must be dispatched to a message queue or executor, pass the required identity explicitly as authenticated message metadata under clear policy; do not rely on thread-locals.

### 8.4. Context Does Not Automatically Become MDC

Reactor Context and logging MDC are two distinct mechanisms. If you want request IDs or caller IDs in MDC during logging, you need an explicitly configured context propagation/bridge, such as Micrometer Context Propagation depending on your application version.

Do not treat the presence of a username in MDC as proof of a valid security context; authorization must use a verified `Authentication`, never the log context.

## 9. Reactive Method Security and Principal

WebFlux services can use method security:

~~~java
@Configuration
@EnableReactiveMethodSecurity
public class MethodSecurityConfiguration {
}
~~~

Example:

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Flux<Order> findOrders() {
        return repository.findAll();
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public Mono<Order> create(Order order) {
        return repository.save(order);
    }
}
~~~

Reactive method security uses Reactor Context to look up authentication. Protected methods must return reactive types such as `Mono` or `Flux` so authorization is enforced during reactive execution.

Do not apply reactive method security annotations as if they were Servlet method security on a method returning a synchronous object and expect context propagation to work automatically.

### 9.1. Testing Both HTTP Authorization and Method Authorization

A request may pass `authorizeExchange` yet be denied by `@PreAuthorize` at the service layer. Tests should be clear about which layer owns which policy:

- HTTP rule: path, method, authority.
- Method rule: permission to invoke the business operation.
- Object-level rule: whether the caller can read/modify that specific order/tenant.

Do not skip method security merely because the route already requires a scope. A business service might be called by a message consumer or a different route.

### 9.2. Object-Level Authorization

Example:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.read')")
public Mono<Order> findOrder(String orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(subject ->
            repository.findByIdAndOwnerSubject(orderId, subject)
        );
}
~~~

This example checks scope at the method boundary and constrains the query to the subject. In a multi-issuer system, use an `(issuer, subject)` identity namespace or an internal ID; in a multi-tenant system, add tenant membership/ACL checks.

## 10. Testing Reactor Context Independently with StepVerifier

Not every test needs to start a WebFlux server. You can test a service reading context using Reactor's `StepVerifier`.

### 10.1. Creating Authentication for Tests

~~~java
Authentication authentication =
    new UsernamePasswordAuthenticationToken(
        "user-42",
        "n/a",
        List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
    );
~~~

This is a directly constructed test authentication, not the result of an OAuth token. It is only used to verify that the service reads the context.

### 10.2. Putting Authentication into Reactor Context in Tests

~~~java
@Test
void serviceReadsAuthenticationFromReactorContext() {
    Authentication authentication =
        new UsernamePasswordAuthenticationToken(
            "user-42",
            "n/a",
            List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
        );

    Mono<String> result = currentCallerService.currentName()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(authentication)
        );

    StepVerifier.create(result)
        .expectNext("user-42")
        .verifyComplete();
}
~~~

`ReactiveSecurityContextHolder.withAuthentication(authentication)` creates a `Context` containing the authentication. The test attaches it to the subscription with `contextWrite`.

Do not call `SecurityContextHolder.setContext(...)` in reactive tests to simulate WebFlux behavior; that tests the wrong mechanism.

### 10.3. Testing When Context Is Absent

~~~java
@Test
void serviceCompletesEmptyWhenNoSecurityContextExists() {
    StepVerifier.create(currentCallerService.currentName())
        .verifyComplete();
}
~~~

If the service contract requires a mandatory caller, you can convert the empty state into an appropriate domain/authentication error:

~~~java
public Mono<String> requiredCallerName() {
    return currentName()
        .switchIfEmpty(Mono.error(
            new IllegalStateException("No authenticated caller")));
}
~~~

Do not default to `defaultIfEmpty("admin")` or create a privileged fallback principal.

### 10.4. Testing Context Across Schedulers

~~~java
@Test
void contextIsAvailableAfterPublishOn() {
    Authentication authentication =
        new UsernamePasswordAuthenticationToken(
            "user-42",
            "n/a",
            List.of()
        );

    Mono<String> result = currentCallerService.currentName()
        .publishOn(Schedulers.parallel())
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(authentication)
        );

    StepVerifier.create(result)
        .expectNext("user-42")
        .verifyComplete();
}
~~~

This test confirms the context is tied to the subscription rather than a specific thread. Do not use `Thread.sleep` to wait for the scheduler; `StepVerifier` coordinates subscription and signals.

## 11. Verifying Context Does Not Leak Between Subscribers

A singleton service can serve many concurrent requests. One request's security context must never appear in another request.

Unit test example:

~~~java
@Test
void concurrentSubscribersSeeTheirOwnAuthentication() {
    Authentication userA =
        new UsernamePasswordAuthenticationToken("user-A", "n/a", List.of());

    Authentication userB =
        new UsernamePasswordAuthenticationToken("user-B", "n/a", List.of());

    Mono<String> requestA = currentCallerService.currentName()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(userA)
        );

    Mono<String> requestB = currentCallerService.currentName()
        .contextWrite(
            ReactiveSecurityContextHolder.withAuthentication(userB)
        );

    StepVerifier.create(Mono.zip(requestA, requestB))
        .assertNext(tuple -> {
            assertThat(tuple.getT1()).isEqualTo("user-A");
            assertThat(tuple.getT2()).isEqualTo("user-B");
        })
        .verifyComplete();
}
~~~

Each publisher receives its own context. Do not use a mutable `currentUser` field in a service; if you do, concurrent requests can overwrite each other's data.

### 11.1. Testing an Anonymous Request After an Authenticated Request

At the HTTP layer, send sequentially:

1. A request with a mock JWT or valid Bearer token.
2. A follow-up request with no token.
3. Confirm the second request is rejected on a private endpoint and does not receive the first request's principal.

This catches faulty context persistence or a test client that was mutated with authentication applied globally across all requests.

## 12. Testing WebFlux with WebTestClient and Spring Security

WebFlux uses `WebTestClient`, not MockMvc.

### 12.1. Attaching the Real SecurityWebFilterChain

With an application context:

~~~java
@BeforeEach
void setUp() {
    webTestClient = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();
}
~~~

`springSecurity()` integrates Spring Security WebFlux filters into `WebTestClient`. When using `bindToApplicationContext`, tests can execute the application's `WebFilterChainProxy` and `SecurityWebFilterChain`.

### 12.2. Spring Boot Integration Test

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class OrdersWebFluxSecurityTests {

    @Autowired
    WebTestClient webTestClient;
}
~~~

This setup uses Spring Boot's real application context. When you need explicit control over the filter chain, you can build the client from the context and apply `springSecurity()`; avoid applying duplicate configurations without understanding filter registration.

### 12.3. WebFlux Slice Test

~~~java
@WebFluxTest(controllers = OrdersController.class)
@Import(ApiSecurityConfiguration.class)
class OrdersControllerWebTests {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    OrdersService ordersService;
}
~~~

`@WebFluxTest` only loads the required MVC/WebFlux slice. Import the application's right security configuration and mock out-of-scope dependencies. On older Spring Boot/Spring Framework versions, projects may use `@MockBean` instead of `@MockitoBean`.

### 12.4. `bindToController` Does Not Represent Full Application Security

`WebTestClient.bindToController(...)` is convenient for controller-focused tests, but does not automatically load the application's full `SecurityWebFilterChain`. If the goal is security integration, use `bindToApplicationContext(...).apply(springSecurity())` or a Boot test context with security filters configured.

## 13. Mocking Principals with `mockJwt()` and `mockOpaqueToken()`

Spring Security Test provides request mutators for `WebTestClient`:

- `mockUser()`
- `mockJwt()`
- `mockOpaqueToken()`

They enable fast authorization testing without issuing real tokens.

### 13.1. `mockJwt()`

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt
            .subject("user-42")
            .claim("scope", "orders.read")
        )
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

`mockJwt()` creates a mock JWT authentication for the test. It does not invoke `ReactiveJwtDecoder` and does not verify the JWT signature, issuer, or audience using the production decoder.

If a test needs to verify that the production converter maps scopes from claims, do not merely pass authorities directly; test the converter separately or send a signed bearer token through the decoder.

### 13.2. `mockOpaqueToken()`

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes -> {
            attributes.put("sub", "user-42");
            attributes.put("client_id", "web-client");
        })
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

`mockOpaqueToken()` creates a sample opaque authentication/principal. It does not invoke `ReactiveOpaqueTokenIntrospector` and does not test the introspection HTTP client.

### 13.3. `mockUser()`

~~~java
webTestClient
    .mutateWith(mockUser("mai"))
    .get()
    .uri("/api/profile")
    .exchange()
    .expectStatus().isOk();
~~~

This is a mock user authentication, not an OAuth2 access token. Use it for authorization rules requiring an authenticated principal, not to prove the Resource Server accepts JWT/opaque tokens.

### 13.4. What Mock Authentication Does Not Prove

| Test helper | Tests filter chain? | Verifies real token? | Invokes decoder/introspector? |
|---|---:|---:|---:|
| `mockUser()` | Yes, if security WebFilters are attached | No | No |
| `mockJwt()` | Yes, if security WebFilters are attached | No | No |
| `mockOpaqueToken()` | Yes, if security WebFilters are attached | No | No |
| `Authorization: Bearer ...` | Yes | Yes, if real decoder/introspector | Yes |
| Bearer header + mock decoder | Yes | No crypto verification | Calls mock decoder |
| Bearer header + test key decoder | Yes | Yes, with test key | Yes |
| Bearer header + introspector HTTP stub | Yes | Per stub contract | Yes |

## 14. Sending Real Bearer Tokens Through WebTestClient

To test the authentication pipeline, do not use `mockJwt()`. Send the token in the header:

~~~java
webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers ->
        headers.setBearerAuth("test-access-token")
    )
    .exchange()
    .expectStatus().isOk();
~~~

If the Resource Server uses JWT, the request passes through:

~~~text
WebTestClient
   |
   v
WebFilterChainProxy
   |
   v
Bearer authentication WebFilter
   |
   v
ReactiveAuthenticationManager
   |
   v
ReactiveJwtDecoder
   |
   v
SecurityContext / Reactor Context
   |
   v
Authorization
   |
   v
Controller
~~~

### 14.1. Testing the Bearer Filter and Provider with a Mock Decoder

You can mock `ReactiveJwtDecoder` to verify the bearer token is forwarded to the decoder:

~~~java
given(reactiveJwtDecoder.decode("test-access-token"))
    .willReturn(Mono.just(testJwt));

webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers ->
        headers.setBearerAuth("test-access-token")
    )
    .exchange()
    .expectStatus().isOk();

verify(reactiveJwtDecoder).decode("test-access-token");
~~~

This test verifies bearer extraction, the authentication provider, and wiring to the decoder. Because the decoder is a mock, it **does not prove JWT signatures** are verified.

### 14.2. Testing JWT Signatures with a Test Key

To verify cryptographic validation:

1. Generate an RSA key pair dedicated to testing.
2. Create a JWT signed with the test private key.
3. Configure `NimbusReactiveJwtDecoder` with the test public key.
4. Configure issuer/audience validators.
5. Send the token via `Authorization: Bearer`.
6. Confirm a validly signed token is accepted.
7. Sign a token with a different key pair and confirm it is rejected.
8. Test wrong issuer, audience, and expiry timestamps.

Example initializing the decoder with a public key:

~~~java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder(RSAPublicKey publicKey) {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder
            .withPublicKey(publicKey)
            .signatureAlgorithm(SignatureAlgorithm.RS256)
            .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(
            "https://idp.test.example"
        )
    );

    return decoder;
}
~~~

Depending on the Spring Security version, you can add an audience validator using `DelegatingOAuth2TokenValidator`. Never use production private keys in tests.

### 14.3. Testing the JWKS Endpoint via a Mock HTTP Server

If you need to confirm the reactive decoder fetches keys over HTTP:

- Run a JWKS stub/test server.
- Return a JWK Set containing only the test public key.
- Configure `NimbusReactiveJwtDecoder.withJwkSetUri(testJwksUri)`.
- Send a signed JWT with the matching `kid`.
- Confirm the token is verified.
- Update the JWKS to test key rotation.
- Have the endpoint timeout/return 5xx and confirm it does not fail open.

Testing directly with a public key verifies signatures; testing with a JWKS stub verifies both network retrieval and key selection.

## 15. Testing Opaque Introspection in WebFlux

For opaque tokens, the configuration uses `ReactiveOpaqueTokenIntrospector`.

### 15.1. Mock Introspector for the Bearer Flow

A test can mock the introspector:

~~~java
given(reactiveOpaqueTokenIntrospector.introspect("opaque-test-token"))
    .willReturn(Mono.just(testPrincipal));

webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers ->
        headers.setBearerAuth("opaque-test-token")
    )
    .exchange()
    .expectStatus().isOk();

verify(reactiveOpaqueTokenIntrospector)
    .introspect("opaque-test-token");
~~~

Unlike `.mutateWith(mockOpaqueToken())`, this test sends a bearer header so the filter/provider calls the mocked introspector dependency.

### 15.2. Testing a Real or Stub Introspection Server

To test the HTTP request and response parsing, use a test Authorization Server or HTTP stub:

- `active=true` with valid scope.
- `active=false`.
- Expired/revoked token.
- Wrong client credentials.
- Malformed response.
- Timeout/5xx.
- Invalid audience/resource context.
- Authority mapping from `scope`/`permissions`.

Ensure the real `ReactiveOpaqueTokenIntrospector` is pointed at the test endpoint. Never use production introspection credentials.

## 16. Testing Endpoints Reading the Principal from Reactor Context

Suppose the controller is:

~~~java
@RestController
public class ContextController {

    @GetMapping("/api/context-name")
    Mono<String> contextName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
~~~

Test with mock JWT:

~~~java
@Test
void controllerReadsJwtPrincipalFromReactiveSecurityContext() {
    webTestClient
        .mutateWith(mockJwt()
            .jwt(jwt -> jwt.subject("user-42"))
        )
        .get()
        .uri("/api/context-name")
        .exchange()
        .expectStatus().isOk()
        .expectBody(String.class)
        .isEqualTo("user-42");
}
~~~

This test confirms the mock authentication is placed in the reactive security context and the controller reads the principal. It does not verify the JWT signature.

### 16.1. Testing Across a Scheduler in a Service

Create a service:

~~~java
@Service
public class ReactiveCallerService {

    public Mono<String> currentNameAcrossScheduler() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName)
            .publishOn(Schedulers.parallel())
            .map(String::toUpperCase);
    }
}
~~~

In a WebFlux integration test, call an endpoint using this method with `mockJwt()` and verify the principal name remains present after the scheduler hop.

### 16.2. Testing `ServerWebExchange.getPrincipal()`

Controller:

~~~java
@GetMapping("/api/exchange-principal")
Mono<String> principal(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName);
}
~~~

Test similarly with `mockJwt()` or `mockUser()`. If the request is unauthenticated and the route does not permit anonymous access, the security layer may reject it before the controller is called.

## 17. Testing `@AuthenticationPrincipal` with JWT

Controller:

~~~java
@GetMapping("/api/jwt-subject")
Mono<String> subject(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(jwt.getSubject());
}
~~~

Test:

~~~java
webTestClient
    .mutateWith(mockJwt()
        .jwt(jwt -> jwt.subject("user-42"))
    )
    .get()
    .uri("/api/jwt-subject")
    .exchange()
    .expectStatus().isOk()
    .expectBody(String.class)
    .isEqualTo("user-42");
~~~

If the controller receives an opaque token, the default principal is not a `Jwt`. Write the controller/adapter to accept an appropriate abstraction rather than casting blindly.

A controller supporting both can accept `Authentication` via the appropriate argument resolution mechanism or read `ReactiveSecurityContextHolder`, then normalize authenticated principals into a domain caller.

## 18. Testing Reactive Method Security

Service example:

~~~java
@Service
public class SecureOrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Flux<Order> findAll() {
        return repository.findAll();
    }
}
~~~

Method security configuration:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

WebTestClient tests:

- Call the endpoint using the service with `mockJwt()` having `SCOPE_orders.read`: allowed.
- Call the same endpoint with `mockJwt()` missing the scope: denied.
- Send a signed bearer token with the right scope: tests decoder + method security.
- Verify the repository is not called when method security denies access.

Reactive method security requires returning a publisher so authorization runs within reactive execution. If a method returns a synchronous `Order`, do not assume `ReactiveSecurityContextHolder` is handled the same way as a method returning `Mono<Order>`.

## 19. Testing 401, 403, and Principal Absence

Common scenarios:

| Request | Typical result | Meaning |
|---|---|---|
| No token on private route | 401 | Unauthenticated |
| Malformed/invalid JWT | 401 | Authentication failed |
| Inactive opaque token | 401 | Introspection rejected |
| Valid JWT, missing scope | 403 | Authorization failed |
| Valid JWT, wrong tenant | 403/404 per policy | Business authorization |
| `permitAll` route without token | 200 if controller succeeds | Authentication not required |
| Anonymous principal calling service requiring context | Per service contract | Context may be absent or anonymous |
| Mock JWT with right scope | 200 if rule allows | Authorization test, does not verify token |
| Real Bearer token with right scope | 200 if decoder and policy match | Authentication + authorization pipeline |

In WebFlux, authentication/authorization errors are handled by reactive entry points/handlers. Do not use Servlet `AuthenticationEntryPoint` or `AccessDeniedHandler` directly; the corresponding APIs are typically `ServerAuthenticationEntryPoint` and `ServerAccessDeniedHandler`.

## 20. Context and Principal When Supporting Multiple Token Types

A Resource Server may support both JWT and opaque tokens. Controllers should not assume:

~~~java
Jwt jwt = (Jwt) authentication.getPrincipal();
~~~

Opaque tokens typically have an `OAuth2AuthenticatedPrincipal`. You can build an adapter:

~~~java
public Mono<CallerIdentity> currentCaller() {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(authentication -> {
            Object principal = authentication.getPrincipal();

            if (principal instanceof Jwt jwt) {
                return new CallerIdentity(
                    jwt.getIssuer().toString(),
                    jwt.getSubject()
                );
            }

            if (principal instanceof OAuth2AuthenticatedPrincipal opaque) {
                return new CallerIdentity(
                    "trusted-introspection-source",
                    opaque.getName()
                );
            }

            throw new AccessDeniedException(
                "Unsupported principal type");
        });
}
~~~

`CallerIdentity` and `"trusted-introspection-source"` are domain mapping examples. In production, the identity source must come from a trusted issuer/introspection configuration, not an arbitrary string sent by the request.

In multi-issuer setups, canonical identity typically requires `(issuer, subject)`. Two tokens with the same `sub` but different issuers do not automatically represent the same person.

## 21. Reactor Context Is Not a Place for Arbitrary Business State

You can store request-scoped metadata in Reactor Context, but do not turn it into a mutable data store:

- Do not store large entities or entire request bodies.
- Do not store raw access tokens if only the subject is needed.
- Do not store shared mutable maps.
- Do not use Context as a replacement for a database/cache.
- Do not use custom context keys as proof of authentication.
- Do not set `isAdmin=true` from a request header and trust it in a service.

Security identity must come from verified Spring Security authentication. Values such as trace IDs or correlation IDs may live in Reactor Context, but must have their own separate origin and semantics.

## 22. Common Pitfalls When Reading the Principal in WebFlux

| Symptom | Common cause | How to fix |
|---|---|---|
| `ReactiveSecurityContextHolder.getContext()` completes empty | Request is unauthenticated or code runs outside security subscription | Check chain, bearer token, and subscription boundary |
| `SecurityContextHolder.getContext()` is empty | Used Servlet ThreadLocal API in reactive code | Use `ReactiveSecurityContextHolder` |
| Controller sees JWT but service does not | Service created a separate subscription or called `subscribe()` | Compose publishers in the same chain |
| Context lost after `publishOn` | Read ThreadLocal or non-reactive custom callback | Read via reactive holder; pass values explicitly |
| Principal is null in controller | Endpoint is anonymous/permitAll or security chain did not apply | Check matchers and authentication |
| Casting to `Jwt` fails | Request used an opaque token or different authentication type | Use an abstraction/adapter |
| Test passes yet production decoder does not run | Used `mockJwt()` | Send a real Bearer header |
| Test sees principal from previous request | Used mutable singleton/thread-local state or shared mutated test client | Use subscriber-scoped context and per-request client mutators |
| `block()` triggers event-loop error | Blocking inside reactive pipeline | Return `Mono`/`Flux` and compose operators |
| Method security does not trigger | `@EnableReactiveMethodSecurity` not enabled or method does not return a Publisher | Configure reactive method security and return `Mono`/`Flux` |
| `exchange.getPrincipal()` has no value | No authentication in exchange context | Check authentication filter/repository |
| Opaque token triggers blocking introspection | Used Servlet introspector in WebFlux | Use `ReactiveOpaqueTokenIntrospector` |

## 23. Anti-Patterns to Avoid

### 23.1. Using `SecurityContextHolder` in WebFlux

~~~java
// Wrong for reactive request context.
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
~~~

Use:

~~~java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication);
~~~

### 23.2. Calling `block()` to Retrieve Username

~~~java
String name = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName())
    .block();
~~~

This introduces a blocking boundary and can detach the subscription. Return `Mono<String>`.

### 23.3. Calling `subscribe()` Manually in a Service

~~~java
repository.findAll().subscribe();
return Mono.empty();
~~~

Do not let a service spawn unmanaged subscriptions. Return the publisher so the caller controls the lifecycle.

### 23.4. Storing Current User in a Singleton Field

~~~java
@Service
class BadCallerService {
    private String currentUser;
}
~~~

Concurrent requests will overwrite the value. Use Reactor Context or pass `CallerIdentity` explicitly.

### 23.5. Putting an Unverified Principal into Custom Context

Do not construct a custom `Context` from an `X-User` header, an unverified JWT payload, or a query parameter and treat it as an authenticated principal.

### 23.6. Using `mockJwt()` to Prove Token Signatures

Mock JWT is only for authorization tests. Use a signed JWT and a real `ReactiveJwtDecoder` when testing token validation.

### 23.7. Using Servlet Security Classes in WebFlux

Do not use `HttpSecurity`, `SecurityFilterChain`, `JwtDecoder`, `OpaqueTokenIntrospector`, or `MockMvc` for reactive security paths. Use `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtDecoder`, `ReactiveOpaqueTokenIntrospector`, and `WebTestClient`.

### 23.8. Using Context as a Global Variable

Do not use `Hooks.onEachOperator` or custom global mutable state to store the current principal without an explicit context propagation design. Security context already has a standard abstraction.

## 24. Test Matrix for Reactor Context and Principal

| Test | Setup | Expectation |
|---|---|---|
| Principal in controller | WebTestClient + `mockJwt()` | Controller reads subject |
| Principal via exchange | `exchange.getPrincipal()` | `Mono<Principal>` has name |
| SecurityContext in service | `contextWrite(withAuthentication(...))` + StepVerifier | Service reads correct name |
| Missing context | StepVerifier without context | Empty publisher or error per contract |
| Scheduler hop | `publishOn` then read context | Principal remains intact |
| Concurrent subscribers | Two different contexts | No leak from user A to B |
| Mock JWT authorization | `mockJwt()` + authority | HTTP rules work |
| Mock opaque authorization | `mockOpaqueToken()` | Opaque principal mapping/authority rules work |
| Real JWT bearer | Bearer header + test decoder | Decoder is invoked |
| Real JWT signature | Signed token + reactive decoder/test key | Signature and validators are checked |
| Opaque bearer flow | Bearer header + reactive introspector | Introspector is invoked |
| Method security | `@EnableReactiveMethodSecurity` + publisher method | Valid scope passes, missing scope denied |
| Missing token | Private route, no Authorization | 401 |
| Wrong scope | Valid mock/real authentication missing authority | 403 |
| Context isolation | Auth request followed by anonymous request | No stale context |
| No blocking | Reactor pipeline never calls block | Does not block event loop |

## 25. Step-by-Step Debugging Order

When the principal does not appear at the service layer, check in order:

1. Did the request enter the expected `SecurityWebFilterChain`?
2. Did `securityMatcher`/`pathMatchers` select a different chain?
3. Did the request send a valid `Authorization: Bearer ...` header?
4. Did the JWT decoder or opaque introspector succeed?
5. Was `Authentication` created with the expected principal?
6. Is the service code running inside the same reactive subscription as the request?
7. Are there any `block()`, nested `subscribe()`, or manually created threads/executors?
8. Did code mistakenly use Servlet `SecurityContextHolder`?
9. Is a custom `ServerSecurityContextRepository` changing context persistence?
10. Is method security enabled and does the method return a `Publisher`?
11. Does the controller use the right principal type for JWT/opaque?
12. Is the test using mock authentication and therefore bypassing the decoder?

You can temporarily observe `authentication.getClass().getSimpleName()`, principal type, and authority names in test logs. Avoid logging raw tokens, full PII claims, or credentials.

## 26. Self-Check Questions

**1.** Why should WebFlux not use `SecurityContextHolder` like Servlet?

> Because WebFlux does not pin a request to a fixed thread; `SecurityContextHolder` defaults to ThreadLocal, whereas WebFlux uses Reactor Context.

**2.** Which API reads SecurityContext in a reactive pipeline?

> `ReactiveSecurityContextHolder.getContext()`, which returns `Mono<SecurityContext>`.

**3.** Is Reactor Context attached to a thread or a subscriber?

> Subscriber/subscription; the context follows reactive execution rather than a specific thread.

**4.** Does `publishOn` automatically lose Reactor Context?

> No. Reactor Context is designed to follow the subscription across standard reactive operators; issues usually come from ThreadLocal or detached subscriptions.

**5.** Why not call `block()` to retrieve the principal?

> Because it creates a blocking boundary and can spawn a subscription detached from the request pipeline; return `Mono` and compose reactive operators instead.

**6.** Why not manually call `subscribe()` in a service?

> Because the service detaches lifecycle/error/cancellation from the caller and may not preserve the expected context.

**7.** How does a controller obtain the JWT principal?

> It can use `@AuthenticationPrincipal Jwt` when the route only accepts JWTs, or read `Authentication` via `ReactiveSecurityContextHolder`.

**8.** What does `ServerWebExchange.getPrincipal()` return?

> A `Mono<Principal>`.

**9.** Is an opaque token's principal always a `Jwt`?

> No. It is typically an `OAuth2AuthenticatedPrincipal`; the authentication is typically `BearerTokenAuthentication`.

**10.** Does `mockJwt()` verify the JWT signature?

> No. It creates a mock authentication for authorization tests.

**11.** What is needed to test the reactive bearer filter and decoder?

> Send `Authorization: Bearer ...` through WebTestClient and configure a real or mock test decoder matching the test goal.

**12.** What is `@EnableReactiveMethodSecurity` used for?

> Enabling method security with reactive context, such as `@PreAuthorize` on methods returning `Mono`/`Flux`.

**13.** How do you test a service reading SecurityContext without running a WebFlux server?

> Use `StepVerifier` and `contextWrite(ReactiveSecurityContextHolder.withAuthentication(authentication))`.

**14.** Why must a singleton service not store `currentUser` in a field?

> Because multiple concurrent subscribers/requests could overwrite each other's values.

**15.** Can user A's context automatically leak into user B's request?

> Not when using Reactor Context properly; each subscription has its own context. Leaks usually stem from mutable global state, ThreadLocal, or faulty test wiring.

**16.** Does `Reactor Context` automatically sync data to MDC?

> No. Logging MDC is a separate mechanism; a dedicated context propagation bridge is needed if desired.

## 27. References

- [Spring Security — Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/index.html): Spring Security WebFlux architecture and reactive security context.
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder`, JWT bearer authentication, and authorities.
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector` and opaque authentication.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity`, `@PreAuthorize`, and Publisher return types.
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html): WebTestClient and reactive security testing.
- [Spring Security — Testing OAuth 2.0 with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, `mockOpaqueToken()`, and OAuth test support.
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): reading/writing SecurityContext in Reactor Context.
- [Spring Security — ReactorContextWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ReactorContextWebFilter.html): populating reactive context from the security context repository.
- [Spring Security — SecurityContextServerWebExchangeWebFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/SecurityContextServerWebExchangeWebFilter.html): principal access via `ServerWebExchange`.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): context semantics, `contextWrite`, `deferContextual`.
- [Project Reactor — Threading and Schedulers](https://projectreactor.io/docs/core/release/reference/coreFeatures/schedulers.html): `publishOn`, `subscribeOn`, and scheduler behavior.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): WebFlux integration tests and client binding modes.

**Conclusion:** Spring Security WebFlux places authentication into the **Reactor Context** so the principal follows the request's subscriber. Controllers can use `@AuthenticationPrincipal` or `ServerWebExchange.getPrincipal()`; services should read via `ReactiveSecurityContextHolder` or receive an explicitly passed domain identity. Reactor Context continues working across reactive operators and scheduler hops, but does not protect code that spawns detached subscriptions or uses ThreadLocal. Use `StepVerifier` to verify context isolation, `WebTestClient` with real security filters to test the pipeline, and distinguish `mockJwt()`/`mockOpaqueToken()` from real Bearer tokens that require decoder/introspector verification.
