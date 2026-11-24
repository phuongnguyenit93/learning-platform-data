# Accessing `Principal` and `ReactiveSecurityContextHolder` in Spring WebFlux

## 1. Objectives

In Spring WebFlux, an HTTP request often needs to know **who is sending the request**, whether that caller is authenticated, and which operations they are permitted to perform. Spring Security provides the `Principal`, `Authentication`, and `SecurityContext` abstractions, and integrates with the **Reactor Context** so the current identity can be accessed properly inside an asynchronous pipeline.

This lesson focuses on two paths for obtaining identity:

1. **In a controller or request handler:** receive `java.security.Principal`, `Mono<Principal>`, or `@AuthenticationPrincipal` directly, or call `ServerWebExchange.getPrincipal()`/`ServerRequest.principal()`.
2. **In services and Reactor chains:** read `ReactiveSecurityContextHolder.getContext()`, extract `Authentication`, use `getName()` and `getAuthorities()`, and compose via `map`, `flatMap`, and `switchIfEmpty`.

We also explore how `SecurityWebFilterChain` propagates context to subscribers, distinguish authentication from authorization, handle anonymous callers, use `contextWrite`, handle thread/scheduler switches, apply method-level protection, test with `WebTestClient` and `StepVerifier`, understand boundaries when calling other HTTP services, and build a runnable Java 17+ project.

**Most important takeaway:** In WebFlux, **do not treat `ThreadLocal`-based `SecurityContextHolder` as a reliable identity source for every reactive callback**. For a reactive sequence, use `ReactiveSecurityContextHolder` or the request principal APIs; never treat a client-supplied username as proof of authentication.

## 2. Distinguishing `Principal`, `Authentication`, and `SecurityContext`

### 2.1. `Principal`: Identity

`java.security.Principal` is a simple interface:

```java
public interface Principal {
    String getName();
}
```

In Spring WebFlux, `Principal` generally represents the entity recognized by the security mechanism. The name returned by `getName()` may be a username, a JWT subject, or another identifier depending on the authentication mechanism. Do not assume it is always an email or a database user ID.

### 2.2. `Authentication`: Identity with Status and Authorities

Spring Security's `Authentication` extends `Principal`. It adds:

- `getPrincipal()`: the underlying principal object, such as `UserDetails`, `Jwt`, or `OAuth2User`.
- `getName()`: the name computed from the current token/principal.
- `getAuthorities()`: the collection of granted `GrantedAuthority` instances.
- `isAuthenticated()`: whether the token has completed authentication according to the implementation.
- `getCredentials()`: associated credentials; never log or serialize to JSON.
- `getDetails()`: additional provider-stored metadata; do not assume it is safe to expose to clients.

Comparison table:

| Value | With HTTP Basic user `alice` | With OAuth2 Resource Server |
| --- | --- | --- |
| `Authentication` | `UsernamePasswordAuthenticationToken` | Typically `JwtAuthenticationToken` |
| `Authentication.getName()` | `alice` | Typically the JWT `sub`, or a configured claim |
| `Authentication.getPrincipal()` | `UserDetails` implementation | Typically `Jwt` |
| Authorities | `ROLE_USER`, `ROLE_ADMIN` if granted | May be `SCOPE_read`, `SCOPE_write`, or mapped authorities |
| Credentials | Internal credential/token, may be erased | Never include credentials/bearer tokens in responses |

Some systems configure custom principals. Therefore, casting `authentication.getPrincipal()` to `UserDetails` is only valid when you know the authentication provider produces that type.

### 2.3. `SecurityContext`: Holding `Authentication`

`SecurityContext` is a container holding the current `Authentication`:

```java
SecurityContext context = ...;
Authentication authentication = context.getAuthentication();
```

`context.getAuthentication()` may be `null`. The context itself does not grant permissions; allowing a request or method call must be enforced by Spring Security authorization rules or controlled business authorization logic.

### 2.4. Anonymous vs. "Authenticated"

On a public endpoint, there may be **no context/authentication** or there may be an `AnonymousAuthenticationToken` created by Spring Security's anonymous mechanism. An anonymous token may report `isAuthenticated() == true` depending on the implementation; therefore, do not rely solely on `isAuthenticated()` to decide whether a real user is logged in.

For access decisions, prefer:
- `authorizeExchange(...).authenticated()` on `SecurityWebFilterChain`.
- `@PreAuthorize("isAuthenticated()")` or role/authority expressions at the method layer.
- `AuthenticationTrustResolver` when code needs to distinguish anonymous/remember-me/full authentication.
- Business rules verifying ownership/tenant, not just the principal name.

When retrieving identity for display purposes, you can handle an empty publisher with `switchIfEmpty`. Never represent anonymous as a `"guest"` string and treat it as an authenticated user.

## 3. Flow of `SecurityContext` in WebFlux

Spring Security uses a chain of `WebFilter` instances, where `SecurityWebFilterChain` defines authentication/authorization for HTTP exchanges.

General model:

```text
HTTP request
      |
      v
Spring Security WebFilter chain
      |
      +-- Extract credentials / session / bearer token
      +-- Perform authentication if present
      +-- Enforce authorization by URL/authority
      +-- Store SecurityContext in Reactor Context
      |
      v
DispatcherHandler / Controller / HandlerFunction
      |
      +-- Principal / Mono<Principal>
      +-- @AuthenticationPrincipal
      +-- ServerWebExchange.getPrincipal()
      |
      v
Service reactive pipeline
      |
      +-- ReactiveSecurityContextHolder.getContext()
      +-- Authentication.getName()/getAuthorities()
      +-- @PreAuthorize in reactive method security
      |
      v
Reactive publisher completes / response
```

In a properly configured WebFlux Security application, `ReactorContextWebFilter` bridges the `SecurityContext` so it can be read per subscriber/reactive pipeline. The authentication source can be HTTP Basic, form login, session, bearer JWT, or another authentication mechanism.

**Distinguishing storage vs. access:**

- `ReactiveSecurityContextHolder` is the API for accessing `SecurityContext` in the **Reactor Context**, not a persistent repository.
- `ServerSecurityContextRepository` controls loading/saving context across requests when the application mechanism requires it (e.g., a `WebSession`-based repository or a `NoOp` repository for stateless models).
- HTTP Basic usually sends credentials on every request; a JWT resource server usually validates a bearer token on every request. Using the Context does not by itself create a long-lived login session.

**Access timing:** Reactor Context belongs to the subscriber; code must read it when the pipeline is subscribed. For operations creating publishers via `flatMap`, `defer`, or other operators, the right context propagates as long as the chain is composed and subscriptions are not detached arbitrarily.

## 4. Approach 1 — Receiving `Principal` Directly in a WebFlux Controller

Spring Framework WebFlux supports `java.security.Principal` as a controller method argument. Because resolving identity may be asynchronous, reactive wrappers are also supported.

### 4.1. Direct `Principal`

```java
@RestController
public class PrincipalController {

    @GetMapping("/me")
    public String me(Principal principal) {
        return principal.getName();
    }
}
```

This is an **illustrative controller snippet**. When the endpoint is configured as `authenticated`, `principal` exists and `getName()` is suitable for displaying the username/subject. However, `Principal` itself does not carry all authorities or custom claims.

### 4.2. `Mono<Principal>` for Reactive Composition

```java
@GetMapping("/me")
public Mono<String> me(Mono<Principal> principal) {
    return principal.map(Principal::getName);
}
```

This fits well when keeping publishers in a reactive flow without calling `block()` and without manually reading the Reactor Context in the controller.

On routes requiring `authenticated()`, security filters reject unauthenticated requests before reaching the controller. On `permitAll()` routes, `principal` may be absent; an empty `Mono` is not the same as a login error. Do not assume the `Publisher` always emits a value.

### 4.3. Receiving `Principal` via `ServerWebExchange`

```java
@GetMapping("/me/exchange")
public Mono<String> fromExchange(ServerWebExchange exchange) {
    return exchange.getPrincipal()
            .map(Principal::getName);
}
```

`ServerWebExchange.getPrincipal()` returns a `Mono<Principal>`, which may be empty. Its advantage is that the method can simultaneously access request attributes, the request URL, and response metadata. If the controller only needs the username, injecting `Mono<Principal>` directly is simpler.

### 4.4. Functional Routing

In WebFlux functional endpoints, `ServerRequest.principal()` also returns a publisher:

```java
@Bean
RouterFunction<ServerResponse> routes() {
    return RouterFunctions.route(
            RequestPredicates.GET("/functional/me"),
            request -> request.principal()
                    .flatMap(principal ->
                            ServerResponse.ok()
                                    .contentType(MediaType.TEXT_PLAIN)
                                    .bodyValue(principal.getName()))
    );
}
```

This is a **router bean snippet**; the project needs imports for `RouterFunction`, `ServerResponse`, `RouterFunctions`, `RequestPredicates`, and `MediaType`, as well as security configuration for `/functional/me`.

### 4.5. Which API to Choose?

| Need | Recommended API |
| --- | --- |
| Only need the name in a controller | `Principal` or `Mono<Principal>` |
| Need broader HTTP exchange details | `ServerWebExchange.getPrincipal()` |
| Functional handler | `ServerRequest.principal()` |
| Want the actual `Authentication.getPrincipal()` | `@AuthenticationPrincipal` |
| Need authorities/token in a controller | `Authentication` via Reactor Context or appropriate principal/token type |
| Need identity in an HTTP-agnostic service | `ReactiveSecurityContextHolder` |

Controllers can take `Principal`, but business services should not depend on `ServerWebExchange` unnecessarily. When a service needs identity across multiple callers (HTTP, message listeners, tests), `ReactiveSecurityContextHolder` or passing a verified identity parameter is a cleaner choice.

## 5. Approach 2 — `@AuthenticationPrincipal`

Spring Security provides `@AuthenticationPrincipal` to resolve **`Authentication.getPrincipal()`**, not the entire `Authentication`.

Example with HTTP Basic and Spring Security `UserDetails`:

```java
@GetMapping("/me/annotation")
public Mono<String> annotated(
        @AuthenticationPrincipal UserDetails userDetails) {
    return Mono.just(userDetails.getUsername());
}
```

Advantage: the method signature explicitly declares the expected domain principal type instead of casting inside the method body.

### 5.1. Do Not Confuse with `Authentication`

With the default `UsernamePasswordAuthenticationToken`:

- `Authentication.getPrincipal()` can be a `UserDetails`.
- `Authentication.getName()` is the username.
- `Authentication.getAuthorities()` is where granted authorities live.

If you need authorities, do not infer them merely from `UserDetails.getUsername()` or a role string in the URL. Use `Authentication` and authorization policies.

### 5.2. `JwtAuthenticationToken` and `OAuth2User`

When using a JWT resource server, the principal is typically `Jwt`, not `UserDetails`:

```java
@GetMapping("/me/jwt")
public Mono<String> currentJwtSubject(
        @AuthenticationPrincipal Jwt jwt) {
    return Mono.just(jwt.getSubject());
}
```

This is a **snippet for endpoints protected by OAuth2 Resource Server JWT only**. It requires the corresponding starter and decoder/issuer configuration; adding the annotation alone does not turn HTTP Basic into JWT auth.

With OAuth2 Login, the principal can be `OAuth2User` or `OidcUser`. Design code around the actual authentication mechanism rather than assuming a single principal type across every environment.

### 5.3. Type Mismatch and Custom Principals

If `@AuthenticationPrincipal` declares a type that does not match the actual principal object, the resolver normally returns `null`; you can enable `errorOnInvalidType = true` to fail fast on misconfiguration:

```java
@GetMapping("/me/strict")
public Mono<String> strict(
        @AuthenticationPrincipal(errorOnInvalidType = true)
        UserDetails user) {
    return Mono.just(user.getUsername());
}
```

On a route protected by HTTP Basic with a `UserDetails` provider, this example works. If you switch to JWT without updating the signature, this catches the type mismatch instead of producing a hard-to-trace `null`.

**Important:** The principal is created by Spring Security from the authentication mechanism. Never read a client-supplied `X-Username` header and cast or treat it as `@AuthenticationPrincipal`.

## 6. Approach 3 — `ReactiveSecurityContextHolder` in Services

In a reactive service, there is no `ServerRequest` or controller argument. Spring Security provides:

```java
ReactiveSecurityContextHolder.getContext()
```

This API returns a `Mono<SecurityContext>` retrieved from the subscriber's Reactor Context.

### 6.1. Reading `Authentication` and Username

```java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Objects::nonNull)
            .map(Authentication::getName);
}
```

This snippet requires imports for `Objects`, `Mono`, `Authentication`, `SecurityContext`, and `ReactiveSecurityContextHolder`.

- `getContext()` may complete empty if no context is present.
- `getAuthentication()` may return `null`; `filter(Objects::nonNull)` only applies after `map`, though Reactor's `Mono.map` forbids emitting `null`: if the mapper returns `null`, `Mono` completes empty per the Reactor contract. Thus you can use `flatMap(context -> Mono.justOrEmpty(context.getAuthentication()))` to express nullable semantics clearly.
- `getName()` is neither synonymous with a database user ID nor a license to access arbitrary records.

A clearer version:

```java
public Mono<String> currentUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                    Mono.justOrEmpty(context.getAuthentication()))
            .map(Authentication::getName);
}
```

If authentication is missing, the result is `Mono.empty()`. Routes protected with `authenticated()` must be configured to genuinely require a user; the service does not replace authentication/authorization rules on its own.

### 6.2. Getting Authorities

```java
public Mono<List<String>> currentAuthorities() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                    Mono.justOrEmpty(context.getAuthentication()))
            .map(auth -> auth.getAuthorities().stream()
                    .map(GrantedAuthority::getAuthority)
                    .sorted()
                    .toList());
}
```

Requires imports for `List` and `GrantedAuthority`. When checking roles, distinguish:
- `hasRole("ADMIN")` typically checks for authority `ROLE_ADMIN`.
- `hasAuthority("ROLE_ADMIN")` checks for the exact string `ROLE_ADMIN`.
- An OAuth2 resource server may use `SCOPE_reports.read` per authority mapping.

Do not derive roles from `getName()`, unverified claims, request bodies, or untrusted headers.

### 6.3. Handling Missing Context

```java
public Mono<String> requireUsername() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(context ->
                    Mono.justOrEmpty(context.getAuthentication()))
            .filter(auth -> auth.isAuthenticated()
                    && !(auth instanceof AnonymousAuthenticationToken))
            .map(Authentication::getName)
            .switchIfEmpty(Mono.error(
                    new AccessDeniedException("Authenticated user required")));
}
```

This **does not replace `SecurityWebFilterChain`**: Spring Security handles 401/403 at the HTTP boundary via authentication, entry points, and access denied handlers. In a business service, the error signals the absence of a valid identity; HTTP status mapping belongs to the security layer.

### 6.4. Why Not Call `block()`?

Wrong in a reactive request:

```java
String user = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .block();
```

`block()` creates an independent subscription that may not inherit the request's Reactor Context and blocks the event loop. Reading the context must be composed inside the pipeline:

```java
return ReactiveSecurityContextHolder.getContext()
        .flatMap(ctx -> Mono.justOrEmpty(ctx.getAuthentication()))
        .map(Authentication::getName)
        .flatMap(user -> orderService.findForOwner(user));
```

This is an **illustrative snippet**, where `orderService.findForOwner` returns a `Mono` result. For complex authorization, ownership must still be verified at the data access/query layer.

## 7. Why Reactor Context Matters

### 7.1. `ThreadLocal` Is Not the Security Context of a Reactive Chain

In imperative Servlets, `SecurityContextHolder` typically uses `ThreadLocal`. However, WebFlux can handle multiple requests on the same event loop, switch threads after I/O, `publishOn`, or `subscribeOn`, and use worker pools.

In that environment:

```java
Authentication auth = SecurityContextHolder
        .getContext()
        .getAuthentication();
```

is not a reliable way to retrieve the right `Authentication` for the active WebFlux subscriber. The value may be missing or come from an unexpected thread context.

Reactor Context is bound to the subscriber/sequence. Reactive Spring Security uses it so identity stays intact when operators execute across different schedulers.

### 7.2. Context Flows from Subscriber Upstream

Reactor Context is supplied during subscription; `contextWrite(...)` applies to upstream operators along the subscription direction. Non-HTTP test example:

```java
Authentication authentication =
        UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                "not-a-real-password",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));

Mono<String> pipeline = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        authentication));
```

Upon subscription, the pipeline emits `alice`. Placing `contextWrite` at the end of the chain makes the upstream `getContext` able to read `Authentication`.

**Do not use `withAuthentication` to spoof users in production.** It is a helper to populate context for a trusted subscriber, suitable in tests or where the framework has already verified identity. Constructing an `Authentication` from a client-declared username and writing it into the Context is a security vulnerability.

### 7.3. `ReactiveSecurityContextHolder` APIs

| API | Return Type | Meaning |
| --- | --- | --- |
| `getContext()` | `Mono<SecurityContext>` | Read security context from Reactor Context |
| `withAuthentication(Authentication)` | `Context` | Create a context containing `Authentication` |
| `withSecurityContext(Mono<? extends SecurityContext>)` | `Context` | Create a context containing a `Mono` of `SecurityContext` |
| `clearContext()` | `Function<Context, Context>` | Clear security context within the Reactor Context scope where applied |

Non-HTTP example given an already verified `Authentication`:

```java
SecurityContext context = new SecurityContextImpl(authentication);

Mono<String> task = readCurrentUser()
        .contextWrite(ReactiveSecurityContextHolder
                .withSecurityContext(Mono.just(context)));
```

`readCurrentUser()` is an illustrative publisher. `withAuthentication` is a shortcut for supplying an `Authentication`; you do not need to construct `SecurityContextImpl` manually in simple cases.

### 7.4. `clearContext` Is Not Logout

```java
Mono<String> taskWithoutContext = readCurrentUser()
        .contextWrite(ReactiveSecurityContextHolder.clearContext());
```

This removes the security context from the upstream subscription scope; it does **not** automatically:
- Revoke a JWT access token.
- Delete stored cookies/sessions.
- Invoke a logout handler.
- Invalidate the user at the identity provider.
- Prevent the next request from re-authenticating via HTTP Basic.

Logout, session invalidation, and token revocation have dedicated flows and configuration in Spring Security.

## 8. Propagating Context Across Operators, Nested Publishers, and Schedulers

### 8.1. `publishOn` and `subscribeOn`

In a properly composed Reactor pipeline, context follows the subscriber rather than depending on a specific `ThreadLocal`:

```java
Mono<String> result = ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .publishOn(Schedulers.parallel())
        .map(String::toUpperCase)
        .contextWrite(
                ReactiveSecurityContextHolder.withAuthentication(
                        authentication));
```

This is a **non-HTTP/test snippet** requiring the corresponding imports. It produces `ALICE` using the authentication from the previous example. In a real application, the context is provided by Spring Security; never manually inject `Authentication` from unverified data.

### 8.2. Nested `flatMap`

```java
public Mono<String> loadForCurrentUser() {
    return Mono.just("start")
            .flatMap(ignored ->
                    ReactiveSecurityContextHolder.getContext())
            .flatMap(context ->
                    Mono.justOrEmpty(context.getAuthentication()))
            .map(Authentication::getName);
}
```

Because inner publishers are composed via `flatMap`, they can access the subscriber Context. This differs from calling `subscribe()` manually.

### 8.3. Losing Context Due to Separate `subscribe()`

Wrong:

```java
public Mono<String> bad() {
    ReactiveSecurityContextHolder.getContext()
            .subscribe(context -> audit(context));

    return Mono.just("ok");
}
```

`subscribe()` starts an independent subscription not connected to the caller's reactive chain. Context, cancellation, error handling, and lifecycle can behave unexpectedly, and when the callback runs is not awaited.

Compose instead:

```java
public Mono<String> better() {
    return ReactiveSecurityContextHolder.getContext()
            .flatMap(context -> auditReactive(context))
            .thenReturn("ok");
}
```

Here `auditReactive(context)` is assumed to return `Mono<Void>`. In production, auditing needs appropriate reliability; do not use arbitrary fire-and-forget for critical audit requirements.

### 8.4. Boundaries Requiring Active Handling

- Manual `subscribe()`, uncomposed/unbridged `CompletableFuture`, callbacks from SDKs lacking Reactor Context support, and work dispatched to executors outside Reactor can lose context.
- Reactor Context **does not automatically cross the network** to WebClient, Kafka, or another RSocket server.
- Reactor supports Micrometer Context Propagation to bridge specific `ThreadLocal`s when needed; accessors must be registered and the propagation mode chosen per version. Do not turn it into a substitute for authorization.
- When a background job running after a request needs identity, pass the **verified business identity and necessary data** under an explicit contract; do not arbitrarily retain the raw `Authentication` object long-term.

## 9. Configuring Reactive Spring Security Properly

Spring WebFlux mirrors the Servlet stack configuration with different APIs.

| Servlet/MVC | Reactive/WebFlux |
| --- | --- |
| `HttpSecurity` | `ServerHttpSecurity` |
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `SecurityContextHolder` `ThreadLocal` | `ReactiveSecurityContextHolder` |
| `UserDetailsService` | `ReactiveUserDetailsService` |
| `AuthenticationManager` | `ReactiveAuthenticationManager` |
| Servlet `Filter` chain | `WebFilter` chain |
| `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |

Do not use Servlet `HttpSecurity`/`SecurityFilterChain` to configure a pure WebFlux application. If a project includes both MVC and WebFlux starters, Spring Boot may choose the servlet web application type; check the classpath and `web-application-type` before diagnosing context errors.

### 9.1. `SecurityWebFilterChain`

Example rules:
- `GET /public` requires no login.
- `/admin/**` requires `ROLE_ADMIN`.
- All other routes require `authenticated`.
- HTTP Basic is used for the demo.
- Form login is disabled so unauthenticated requests receive 401 rather than redirecting to a login page.

```java
@Bean
SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/public").permitAll()
                    .pathMatchers("/admin/**").hasRole("ADMIN")
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .formLogin(form -> form.disable())
            .build();
}
```

In practice, matcher ordering matters: specific rules should come before the fallback. On public routes, do not expect a user `Authentication` to always be present.

### 9.2. Method Security

Enable `@EnableReactiveMethodSecurity` and annotate a Spring-managed service:

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<String> adminMessage() {
    return currentUsername().map(name -> "admin:" + name);
}
```

Reactive method security uses the Reactor Context. Protected methods should return `Mono`/`Flux` or a compatible reactive `Publisher` so authorization attaches to the subscription. Do not expect annotations to work on private methods or self-invocations bypassing the Spring proxy.

When a method performs side effects, place authorization **before** write operations in the pipeline. Never execute side effects before the authorization decision has completed.

### 9.3. Code Responsibilities

Protecting an endpoint with `authenticated()` only proves the user passed authentication. It **does not guarantee that user is allowed to view record ID X**. For example:

```java
@GetMapping("/orders/{id}")
public Mono<OrderDto> order(@PathVariable long id) {
    return identityService.currentUsername()
            .flatMap(name -> orderService.findOwnedBy(id, name));
}
```

This is a snippet: `findOwnedBy` must check ownership against a trusted data source and never return another tenant's records. If a JWT carries a tenant claim, that claim must be verified via token validation/claim mapping; never trust an unverified tenant ID as authorization.

## 10. Complete Example: Java 17+ Spring Boot WebFlux Security

This project demonstrates 3 ways to obtain the user:

1. `Mono<Principal>` in a WebFlux controller.
2. `@AuthenticationPrincipal UserDetails` in a controller.
3. `ReactiveSecurityContextHolder` in a service.

The project uses HTTP Basic with two demo users. For production, replace this with an identity provider/OIDC, user store, TLS, and secure secret management.

### 10.1. Structure

```text
reactive-security-identity/
  settings.gradle
  build.gradle
  src/main/java/demo/security/
    IdentityApplication.java
    SecurityConfiguration.java
    IdentityView.java
    IdentityService.java
    IdentityController.java
  src/test/java/demo/security/
    IdentityServiceTest.java
    IdentityHttpTest.java
```

### 10.2. `settings.gradle`

```groovy
rootProject.name = 'reactive-security-identity'
```

### 10.3. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.6'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

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
```

Spring Boot manages Spring Framework, Spring Security, and Reactor versions via dependency management. Do not arbitrarily mix Spring Security 7 major versions into a Boot 3.5/Security 6.5 application.

### 10.4. `IdentityApplication.java`

```java
package demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class IdentityApplication {

    public static void main(String[] args) {
        SpringApplication.run(IdentityApplication.class, args);
    }
}
```

### 10.5. `SecurityConfiguration.java`

```java
package demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.MapReactiveUserDetailsService;
import org.springframework.security.core.userdetails.ReactiveUserDetailsService;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers("/public").permitAll()
                        .pathMatchers("/admin/**").hasRole("ADMIN")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    ReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails alice = User.withUsername("alice")
                .password(encoder.encode("demo-pass"))
                .roles("USER")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("USER", "ADMIN")
                .build();

        return new MapReactiveUserDetailsService(alice, admin);
    }
}
```

In this example, `User.withUsername(...).roles("ADMIN")` generates the `ROLE_ADMIN` authority; `hasRole("ADMIN")` checks that same authority. Passwords are handled by the encoder, unlike storing raw passwords with `{noop}`. Still, hardcoded demo credentials **are not suitable for production**.

Do not disable CSRF by default just because the demo uses HTTP Basic. The illustrated endpoints are all GET; if adding POST/PUT/DELETE in a browser app with cookies/sessions, design CSRF properly.

### 10.6. `IdentityView.java`

```java
package demo.security;

import java.util.List;

public record IdentityView(
        String name,
        List<String> authorities) {
}
```

The DTO only contains the name and list of authorities for the demo. Never return raw `Authentication` or `SecurityContext` to clients, as they can contain credentials, tokens, and internal details.

### 10.7. `IdentityService.java`

```java
package demo.security;

import java.util.List;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class IdentityService {

    public Mono<IdentityView> currentIdentity() {
        return ReactiveSecurityContextHolder.getContext()
                .flatMap(context ->
                        Mono.justOrEmpty(context.getAuthentication()))
                .filter(authentication ->
                        authentication.isAuthenticated()
                                && !(authentication
                                    instanceof AnonymousAuthenticationToken))
                .map(authentication ->
                        new IdentityView(
                                authentication.getName(),
                                authentication.getAuthorities()
                                        .stream()
                                        .map(GrantedAuthority::getAuthority)
                                        .sorted()
                                        .toList()))
                .switchIfEmpty(Mono.error(
                        new AccessDeniedException(
                                "Authenticated user required")));
    }

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> adminGreeting() {
        return currentIdentity()
                .map(identity -> "admin:" + identity.name());
    }
}
```

Key points:
- `getContext()` reads the subscriber's Reactor Context.
- `flatMap(Mono.justOrEmpty(...))` handles a potentially `null` `Authentication`.
- The filter excludes anonymous tokens so guests are not treated as authenticated users.
- `getAuthorities()` is mapped to a sorted list of strings rather than returning the whole token.
- The `adminGreeting` method has `@PreAuthorize` and runs through a Spring proxy because it is invoked by the controller from another bean.

`AccessDeniedException` in the service indicates no valid identity is present. Rules for returning 401 vs. 403 over HTTP are the responsibility of the security chain, entry point, and access denied handler.

### 10.8. `IdentityController.java`

```java
package demo.security;

import java.security.Principal;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class IdentityController {

    private final IdentityService identityService;

    public IdentityController(IdentityService identityService) {
        this.identityService = identityService;
    }

    @GetMapping("/public")
    public Mono<String> publicMessage() {
        return Mono.just("public");
    }

    @GetMapping("/me/principal")
    public Mono<String> principal(Mono<Principal> principal) {
        return principal.map(Principal::getName);
    }

    @GetMapping("/me/annotation")
    public Mono<String> annotation(
            @AuthenticationPrincipal UserDetails userDetails) {
        return Mono.just(userDetails.getUsername());
    }

    @GetMapping("/me/context")
    public Mono<IdentityView> context() {
        return identityService.currentIdentity();
    }

    @GetMapping("/admin/greeting")
    public Mono<String> adminGreeting() {
        return identityService.adminGreeting();
    }
}
```

`/me/principal` obtains the name from a method argument; `/me/annotation` only works with providers that produce `UserDetails`; `/me/context` goes through the service to read `SecurityContext`. The `/admin/greeting` route is protected by both URL security rules and reactive method security.

### 10.9. Running the Example

Run via the Gradle wrapper if generated for the project:

```bash
./gradlew bootRun
```

Or `gradle bootRun` if Gradle is installed globally. If only the two Gradle files from the example exist, you can generate the wrapper with `gradle wrapper` first.

HTTP commands:

```bash
curl -i http://localhost:8080/public
curl -i http://localhost:8080/me/principal
curl -i -u alice:demo-pass http://localhost:8080/me/principal
curl -i -u alice:demo-pass http://localhost:8080/me/annotation
curl -i -u alice:demo-pass http://localhost:8080/me/context
curl -i -u alice:demo-pass http://localhost:8080/admin/greeting
curl -i -u admin:admin-pass http://localhost:8080/admin/greeting
```

Key expected results:

| Request | Expected Status | Response Body on Success |
| --- | --- | --- |
| `GET /public` without credentials | 200 | `public` |
| `GET /me/principal` without credentials | 401 | Unauthorized |
| `GET /me/principal` as `alice` | 200 | `alice` |
| `GET /me/annotation` as `alice` | 200 | `alice` |
| `GET /me/context` as `alice` | 200 | JSON with `name=alice` and `authorities` containing `ROLE_USER` |
| `GET /admin/greeting` as `alice` | 403 | Forbidden |
| `GET /admin/greeting` as `admin` | 200 | `admin:admin` |

Note: HTTP Basic sends username/password in a Base64-encoded `Authorization` header, **which is not encryption**. Always use HTTPS in production. Never log raw `Authorization` headers or credentials.

## 11. Testing `ReactiveSecurityContextHolder` with `StepVerifier`

You can test the service without starting an HTTP server. In unit tests, create a **test-constructed** `Authentication` and attach it to the Reactor Context.

File `src/test/java/demo/security/IdentityServiceTest.java`:

```java
package demo.security;

import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;

import reactor.core.publisher.Mono;
import reactor.core.scheduler.Schedulers;
import reactor.test.StepVerifier;

class IdentityServiceTest {

    private final IdentityService service = new IdentityService();

    private Authentication user() {
        return UsernamePasswordAuthenticationToken.authenticated(
                "alice",
                "test-credential",
                List.of(new SimpleGrantedAuthority("ROLE_USER")));
    }

    @Test
    void currentIdentityReadsReactorContext() {
        Mono<IdentityView> result = service.currentIdentity()
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user()));

        StepVerifier.create(result)
                .expectNext(new IdentityView(
                        "alice",
                        List.of("ROLE_USER")))
                .verifyComplete();
    }

    @Test
    void missingContextDoesNotFabricatePrincipal() {
        StepVerifier.create(service.currentIdentity())
                .expectError(AccessDeniedException.class)
                .verify();
    }

    @Test
    void identitySurvivesSchedulerHandoff() {
        Mono<String> result = Mono.just("start")
                .publishOn(Schedulers.parallel())
                .flatMap(ignored -> service.currentIdentity())
                .map(identity -> identity.name().toUpperCase())
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user()));

        StepVerifier.create(result)
                .expectNext("ALICE")
                .verifyComplete();
    }

    @Test
    void clearContextIsNotLogoutButHidesContextHere() {
        Mono<IdentityView> result = service.currentIdentity()
                .contextWrite(ReactiveSecurityContextHolder.clearContext())
                .contextWrite(
                        ReactiveSecurityContextHolder.withAuthentication(
                                user()));

        StepVerifier.create(result)
                .expectError(AccessDeniedException.class)
                .verify();
    }
}
```

Explanation of `contextWrite` ordering in the final test: the user context is provided downstream, and `clearContext` is closer to `currentIdentity` along the subscription direction, so upstream does not see the key. The test does not perform HTTP logout or token revocation.

**Limitation of unit tests:** These tests verify Reactor Context handling; they do not prove that HTTP Basic is parsed properly, `SecurityWebFilterChain` is applied, or Spring AOP method security is enabled. HTTP integration tests are also required.

## 12. Testing HTTP and Authorization with `WebTestClient`

File `src/test/java/demo/security/IdentityHttpTest.java`:

```java
package demo.security;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class IdentityHttpTest {

    @Autowired
    WebTestClient client;

    @Test
    void publicRouteNeedsNoAuthentication() {
        client.get()
                .uri("/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void protectedRouteRejectsAnonymousRequest() {
        client.get()
                .uri("/me/principal")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void principalAndAnnotationResolveBasicUser() {
        client.get()
                .uri("/me/principal")
                .headers(h -> h.setBasicAuth("alice", "demo-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");

        client.get()
                .uri("/me/annotation")
                .headers(h -> h.setBasicAuth("alice", "demo-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("alice");
    }

    @Test
    void reactiveServiceReadsAuthenticatedContext() {
        client.get()
                .uri("/me/context")
                .headers(h -> h.setBasicAuth("alice", "demo-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("alice")
                .jsonPath("$.authorities[0]")
                    .isEqualTo("ROLE_USER");
    }

    @Test
    void nonAdminCannotAccessAdminRoute() {
        client.get()
                .uri("/admin/greeting")
                .headers(h -> h.setBasicAuth("alice", "demo-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanAccessAdminRoute() {
        client.get()
                .uri("/admin/greeting")
                .headers(h -> h.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin:admin");
    }
}
```

Run:

```bash
./gradlew test
```

With `RANDOM_PORT`, the test starts a real HTTP server and sends Basic credentials on each request. It verifies that identity flows through the authentication filter to the controller, service, and method security. There is no assumption that the test thread shares a Reactor Context with the server thread.

### 12.1. When to Use `mockUser`?

Spring Security Test supports:

```java
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

WebTestClient mockClient = WebTestClient
        .bindToApplicationContext(context)
        .apply(springSecurity())
        .configureClient()
        .build();

mockClient.mutateWith(mockUser("alice").roles("USER"))
        .get()
        .uri("/me/principal")
        .exchange()
        .expectStatus().isOk();
```

This is a mock-bound test snippet requiring an `ApplicationContext context` injected by Spring test. When using `@SpringBootTest(RANDOM_PORT)` to send requests to a live server, `@WithMockUser` on the test thread **does not substitute** for HTTP authentication on the server thread. In live HTTP integration tests, send an `Authorization` header or a real/test-issuer token as shown above.

### 12.2. Testing JWT/OAuth2 Differs from Basic

When switching to a resource server, use `mockJwt()` for mock-bound tests or a valid test JWT signed by a test issuer/decoder for end-to-end HTTP tests. `mockUser()` does not produce a complete `JwtAuthenticationToken`/claims if code expects `@AuthenticationPrincipal Jwt`.

Do not use `@WithMockUser` to "prove" JWT signature validation succeeded: it bypasses real signature verification.

## 13. Authenticated, Authorities, and Business Authorization

Reading a username does not automatically prove that user is allowed to view specific data.

### 13.1. Authentication

Answers "who is making the request?" and "are the credentials valid?". Spring Security performs this via filters, `AuthenticationManager`, `ReactiveUserDetailsService`, JWT decoders, or other providers.

### 13.2. Request-Level Authorization

Security rules on `SecurityWebFilterChain` decide whether a path/method is allowed:

```java
.authorizeExchange(exchanges -> exchanges
        .pathMatchers("/public").permitAll()
        .pathMatchers("/admin/**").hasRole("ADMIN")
        .anyExchange().authenticated())
```

`authenticated()` is insufficient for APIs that read sensitive per-owner data.

### 13.3. Method-Level Authorization

`@PreAuthorize` on a Spring bean (with reactive method security enabled) restricts access by role/authority:

```java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public Mono<Report> readReport(String reportId) {
    return repository.findById(reportId);
}
```

This is an OAuth2 resource server snippet (assuming scopes have been mapped to authorities properly); not every token carries `SCOPE_reports.read`.

### 13.4. Object-Level Authorization

For example, user `alice` accessing `/users/bob/orders/1`. Even though `alice` is authenticated, `alice`'s permission cannot be inferred from being logged in. The repository/service must compare trusted owner/tenant attributes:

```java
public Mono<Order> currentUsersOrder(long orderId) {
    return currentUsername()
            .flatMap(username ->
                    repository.findByIdAndOwner(
                            orderId, username));
}
```

This is a repository-dependent snippet, not a full demo project. If usernames can change, use a verified stable subject/userId instead of a display name.

## 14. `SecurityContext` and Outbound `WebClient`

A call from Service A to Service B involves two separate security boundaries:

```text
Client ----Bearer/Basic----> Service A
             |
             v
    Authentication in Service A's Reactor Context
             |
             v
       WebClient calls Service B
             |
             v
    New HTTP headers/token at B
             |
             v
    B authenticates independently and creates B's SecurityContext
```

**Reactor Context does not cross HTTP automatically.** Service B cannot read Service A's `SecurityContextHolder` from A's memory. If **on-behalf-of** user calls are needed, use OAuth2 client token relay/delegation or token exchange with proper scopes and audience. Never serialize `Authentication.toString()` or raw credentials into arbitrary headers.

A `WebClient` filter can read the reactive Context if composed in the same subscription, but setting the `Authorization` header must adhere to the identity system and trust boundaries:

```java
Mono<String> result = identityService.currentIdentity()
        .flatMap(identity ->
                webClient.get()
                        .uri("/reports")
                        .retrieve()
                        .bodyToMono(String.class));
```

This illustrative snippet shows the caller's Reactor Context is accessible inside the nested chain. Data from `identity` **does not automatically become a header** sent to `/reports`. Never use a username read by code to impersonate a user downstream; authenticate using credentials/tokens issued by a trusted system.

## 15. Anonymous, `permitAll`, and Handling `Mono.empty()`

### 15.1. Public Pages

A `permitAll()` route allows unauthenticated access. In that case `ReactiveSecurityContextHolder.getContext()` may be empty or contain an anonymous `Authentication`. Avoid:

```java
return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .defaultIfEmpty("anonymous");
```

Using `"anonymous"` solely for **display** can be fine, but never use it for authorization or accessing private data. If you must identify anonymous callers reliably, use Spring Security's trust resolver or token type along with an explicit policy.

### 15.2. Protected Routes

Routes requiring `authenticated` are normally rejected by filters before reaching the controller; do not write code expecting `getContext()` itself to emit a 401 error. `Mono.empty()` is simply a publisher with no value; the HTTP status depends on where you handle it and the `SecurityWebFilterChain`.

### 15.3. `Principal` Can Be Another Type

When using JWT, OIDC, pre-authentication, or custom principals, `getName()` and `getPrincipal()` can differ in semantics. Choose a clear **stable user key** from a trusted authentication source. Never Base64-decode a name out of a token without verifying signature, issuer, audience, expiry, and other requirements.

## 16. Common Pitfalls

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling `SecurityContextHolder.getContext()` in a reactive callback | Missing/wrong user due to `ThreadLocal` | Use `ReactiveSecurityContextHolder` |
| Calling `block()` to read context | Blocking or creating a separate subscription without context | Compose with `map`/`flatMap` |
| Calling `subscribe()` manually in a service | Context/errors/cancellation are detached | Return the publisher and compose the chain |
| Using a username from an HTTP header as `Principal` | User impersonation | Only trust verified `Authentication` |
| Casting `getPrincipal()` to `UserDetails` for JWT | `ClassCastException` or `null` | Use the actual principal type |
| Confusing `@AuthenticationPrincipal` with `Authentication` | Cannot retrieve authorities | Read `Authentication`/`ReactiveSecurityContextHolder` |
| Assuming `isAuthenticated()` excludes anonymous | May mistakenly accept anonymous callers | Use trust resolver or security authorization |
| Assuming `Mono.empty()` automatically becomes 401 | Missing HTTP authentication flow | Configure `authenticated()` in `SecurityWebFilterChain` |
| Placing `contextWrite` in the wrong position | Upstream cannot read context | Check subscription direction and operator scope |
| Assuming `contextWrite` logs a user in | Risk of improper self-impersonation | Only use `withAuthentication` with trusted identities/tests |
| Assuming `clearContext()` logs out | Cookies/tokens remain valid | Use security logout/session/token revocation |
| Putting `@PreAuthorize` on private/self-invoked methods | Bypasses the proxy | Place on public Spring bean methods called via proxy |
| Using synchronous method security for publishers | Authorization does not attach to lifecycle | Use `@EnableReactiveMethodSecurity` and `Mono`/`Flux` |
| Using `HttpSecurity` in pure WebFlux | Configuring the wrong stack | Use `ServerHttpSecurity` |
| Assuming `SecurityContext` propagates automatically via `WebClient` | Service B lacks A's identity | Use proper token relay/delegation |
| Exposing raw `Authentication` in JSON/logs | Leaks credentials/tokens/details | Use field-restricted DTOs |
| Testing only `@WithMockUser` against a live server | Does not authenticate real HTTP requests | Send Basic/JWT test tokens |
| Using only `authenticated()` without owner checks | IDOR/BOLA vulnerabilities | Check record ownership/tenant in service |
| Setting `ROLE_ADMIN` from user input | Privilege escalation | Authorities must come from trusted auth/authorization sources |
| Expired token while a job retains stale `Authentication` | Uses outdated permissions | Design separate auth context and job boundaries |

## 17. Security and Production Considerations

### 17.1. Never Log Credentials, Tokens, or Full Principal Objects

`Authentication.getCredentials()`, JWT token values, cookie/session IDs, and sometimes `getDetails()` contain sensitive information. Logs should favor request ID, route, status, and pseudonymized stable subjects when needed. Avoid `log.info("auth={}", authentication)` without a redaction policy.

### 17.2. TLS Is Mandatory for Real Credentials

HTTP Basic transmits credentials in Base64, which is insecure without HTTPS. Browser sessions and OAuth2 also require secure cookies, redirect URI validation, issuer/audience validation, and appropriate protections.

### 17.3. CSRF, CORS, and Authentication Are Distinct Decisions

CSRF protects browser requests carrying ambient credentials (such as cookies). CORS governs cross-origin reads in browsers. Do not disable CSRF/CORS or treat CORS as authentication; choose policies based on actual clients and credentials.

### 17.4. Separate Identity from Authorization

Identity is "who is this?"; authority/role is granted capability; ownership/tenant policy is application rules. Simply checking `authenticated` is not secure enough.

### 17.5. Never Store Mutable `Authentication` in Static Fields

Singleton beans serve multiple concurrent requests. Storing the current user in a mutable field allows request A to read request B's user. Context must stay bound to the subscription and never leak across requests.

### 17.6. Do Not Trust Incoming `X-User` Headers

A proxy may add identity headers within a verified trust boundary, but the backend must ensure the header can only be set by the trusted gateway and any external incoming values are stripped. In standard architectures, use Bearer tokens/JWTs or Spring Security-managed authenticated sessions.

## 18. Implementation Checklist

1. Does the application run WebFlux reactive or MVC servlet? Is `SecurityWebFilterChain` configured for the right stack?
2. Is the authentication mechanism Basic, session, OAuth2 login, JWT resource server, or custom?
3. Does the controller only need `getName()`? Can you use the simplest `Principal`/`Mono<Principal>`?
4. Do you need the actual `Authentication.getPrincipal()`? Are you using `@AuthenticationPrincipal` with the right type?
5. Does the service need context? Does it use `ReactiveSecurityContextHolder.getContext()` inside the publisher?
6. Are empty context, `null` authentication, and anonymous callers handled properly?
7. Are `ThreadLocal` `SecurityContextHolder`, `block()`, or manual `subscribe()` avoided in reactive paths?
8. Is `contextWrite` placed correctly so upstream publishers can read the context?
9. Do any manual executors or background jobs need an explicit propagation/identity contract?
10. Do request security rules deny unknown routes or require `authenticated()` appropriately?
11. Is method security enabled and are protected methods called via proxies returning `Mono`/`Flux`?
12. Do routes check both roles/authorities and object-level ownership/tenant?
13. Are principals from JWT/OIDC typed properly with a verified stable ID?
14. Does outbound `WebClient` use proper token relay/delegation rather than forwarding raw identity headers?
15. Do tests cover missing auth, wrong authority, valid authority, context propagation, and anonymous cases?
16. Are credentials/tokens/raw `Authentication` excluded from API responses and logs?
17. Are TLS, secure sessions, CSRF/CORS, and logout/revocation designed specifically for the threat model?

## 19. API Summary

| Need | Suitable API |
| --- | --- |
| Identity in an annotated WebFlux controller | `Principal` / `Mono<Principal>` |
| Underlying principal in a controller | `@AuthenticationPrincipal` |
| Identity in `ServerWebExchange` | `exchange.getPrincipal()` |
| Identity in a functional handler | `request.principal()` |
| Reading the subscriber's `SecurityContext` | `ReactiveSecurityContextHolder.getContext()` |
| Attaching `Authentication` for trusted/test subscribers | `ReactiveSecurityContextHolder.withAuthentication(auth)` |
| Attaching `Mono<SecurityContext>` | `withSecurityContext(mono)` |
| Clearing context upstream of a subscription | `clearContext()` + `contextWrite` |
| Defining security rules for HTTP routes | `SecurityWebFilterChain`, `ServerHttpSecurity` |
| Reactive method-level authorization | `@EnableReactiveMethodSecurity`, `@PreAuthorize` |
| Getting username | `Authentication.getName()` |
| Getting authorities | `Authentication.getAuthorities()` |
| Getting raw principal object | `Authentication.getPrincipal()` |
| Testing Reactor Context | `StepVerifier` + `withAuthentication` |
| Testing HTTP authentication | `WebTestClient` + Basic/JWT test credentials |
| Mocking authentication in mock WebFlux tests | `springSecurity()` + `mockUser()`/`mockJwt()` |

## 20. Official References

- [Spring Framework – WebFlux Controller Method Arguments](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/arguments.html): support for `Principal` and reactive wrappers in annotated controllers.
- [Spring Security – ReactiveSecurityContextHolder Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): `getContext`, `withSecurityContext`, `withAuthentication`, and `clearContext`.
- [Spring Security – Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): Reactor Context, `@EnableReactiveMethodSecurity`, and `@PreAuthorize`.
- [Spring Security – Authorize ServerHttpRequest](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html): `authorizeExchange`, `authenticated`, `hasRole`, and security rules.
- [Spring Security – WebTestClient Testing Authentication](https://docs.spring.io/spring-security/reference/reactive/test/web/authentication.html): `mockUser`, `WithMockUser`, and testing authentication.
- [Spring Security – WebTestClient Setup](https://docs.spring.io/spring-security/reference/reactive/test/web/setup.html): `bindToApplicationContext`, `springSecurity()`.
- [Spring Security – @AuthenticationPrincipal](https://docs.spring.io/spring-security/reference/servlet/integrations/mvc.html#mvc-authentication-principal): explains the annotation and accessing `Authentication.getPrincipal()`; note the documentation illustrates Servlet, though the annotation also works in WebFlux.
- [Spring Boot 3.5 – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `RANDOM_PORT`, mock environments, and `WebTestClient`.
- [Project Reactor – Adding a Context to a Reactive Sequence](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): `Context`, `ContextView`, `deferContextual`, `contextWrite`, and subscriber lifecycle.

## 21. Key Takeaways

**`Principal` provides the identity name; `Authentication` holds the principal and authorities; `SecurityContext` holds `Authentication`.** In WebFlux, controllers can accept `Principal`/`Mono<Principal>` or `@AuthenticationPrincipal`. In reactive services, the proper way to read the subscriber's `Authentication` is `ReactiveSecurityContextHolder.getContext()`.

`SecurityContext` propagates via the Reactor Context rather than relying on a single `ThreadLocal`; it does not cross HTTP automatically, does not turn client-sent usernames into authenticated identities, and does not replace authorization. Protect routes with `SecurityWebFilterChain`, protect methods with reactive method security when needed, verify data ownership at the business layer, and validate behavior with `WebTestClient` and `StepVerifier`.
