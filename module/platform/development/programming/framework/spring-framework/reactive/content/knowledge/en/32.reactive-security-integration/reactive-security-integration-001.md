# `SecurityWebFilterChain` and Spring Security Integration Points in Spring WebFlux

## 1. Objectives and Scope

Spring WebFlux operates on the reactive model, while Spring Security provides authentication, authorization, CSRF protection, HTTP headers protection, access error handling, and OAuth2 integration. In WebFlux, HTTP security runs through `WebFilter` and is configured primarily with `ServerHttpSecurity` to produce one or more `SecurityWebFilterChain` beans.

This lesson focuses on integrating Spring Security into a Spring WebFlux application **without confusing it with Spring MVC/Servlet**.

After this lesson, you will be able to:

1. Explain how a request passes through the security `WebFilter` chain before reaching a controller or functional handler.
2. Create a `SecurityWebFilterChain` with `ServerHttpSecurity`, URL rules, and authentication mechanisms.
3. Distinguish between `securityMatcher(...)` which selects the **filter chain** and `authorizeExchange(...)` which sets **access rules within that chain**.
4. Use multiple security chains with `@Order` and a fallback chain so no endpoint is missed.
5. Know where to integrate `ReactiveAuthenticationManager`, `AuthenticationWebFilter`, `ServerSecurityContextRepository`, `SecurityWebFiltersOrder`, and a custom `WebFilter`.
6. Retrieve the current user from the Reactor Context using `ReactiveSecurityContextHolder`.
7. Combine HTTP authorization with `@EnableReactiveMethodSecurity` and `@PreAuthorize`.
8. Understand the differences between 401 and 403, CSRF, CORS, sessions, HTTP Basic, and JWT Resource Server.
9. Write and test a Java 17+ Spring Boot application using `WebTestClient` and Spring Security Test.
10. Avoid common security pitfalls such as accidentally exposing endpoints, arbitrarily disabling CSRF, or using `ThreadLocal` to store identity.

The runnable example is built for **Java 17, Spring Boot 3.3.5, Spring WebFlux, and Spring Security 6.3.x**. Code snippets belonging to the sample project are presented under their exact filenames; standalone snippets in the explanation sections only illustrate APIs and may require additional imports/beans when used independently.

## 2. How WebFlux Security Differs from Spring MVC Security

Spring Security has two main web integration approaches:

| Aspect | Spring MVC / Servlet | Spring WebFlux / Reactive |
|---|---|---|
| HTTP entry point | Servlet `Filter` | Spring `WebFilter` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Configuration | `HttpSecurity` | `ServerHttpSecurity` |
| Request matching | `RequestMatcher` | `ServerWebExchangeMatcher` |
| Authentication manager | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| Authentication filter | Servlet authentication filters | `AuthenticationWebFilter` |
| Context propagation | Typically relies on `SecurityContextHolder`/ThreadLocal | Reactor Context via `ReactiveSecurityContextHolder` |
| HTTP request abstraction | `HttpServletRequest` | `ServerWebExchange` |
| Method security | `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| HTTP testing | `MockMvc` | `WebTestClient` |

Do not replace class names by mechanically swapping prefixes. An application using `spring-boot-starter-webflux` requires security configuration for the reactive stack.

The following example is **not** a WebFlux configuration:

```java
SecurityFilterChain servletChain(HttpSecurity http) {
    // Servlet stack; do not use for WebFlux Security.
    return http.build();
}
```

The corresponding WebFlux configuration uses:

```java
@Bean
SecurityWebFilterChain reactiveChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchange -> exchange
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

`Customizer` comes from `org.springframework.security.config.Customizer`. The `SecurityWebFilterChain` class comes from `org.springframework.security.web.server`.

An application may contain both Servlet and Reactive dependencies due to the dependency tree. Identify which web application type the application is actually running on before applying security guidance.

## 3. Where Does a Request Go Through Security?

WebFlux has `WebHttpHandlerBuilder`, `WebHandler`, `WebFilter`, and `WebExceptionHandler`. Spring Security participates via a `WebFilterChainProxy` holding a set of `SecurityWebFilterChain` instances.

General flow:

```text
HTTP request
    |
    v
HTTP server / Reactor Netty
    |
    v
WebFlux HttpHandler
    |
    v
Spring Security WebFilterChainProxy
    |
    +-- Select SecurityWebFilterChain matching request
    |
    +-- CORS/CSRF/HTTP headers (as configured)
    |
    +-- Load SecurityContext
    |
    +-- Authentication (Basic, Bearer, form login, ...)
    |
    +-- Exception translation
    |
    +-- Authorization
    |
    v
WebFlux HandlerMapping / HandlerAdapter
    |
    v
@RestController or RouterFunction
    |
    v
Service with reactive method security
    |
    v
Mono/Flux response
```

The exact filter order is determined by the configuration and `SecurityWebFiltersOrder`; the diagram provides a functional view rather than a guarantee that all filters are present in every chain.

### Three Layers of Defense to Distinguish

- **Authentication**: Which identity is associated with this request, and are the credentials accepted?
- **Authorization at the HTTP boundary**: Is that identity allowed to call this URL + method?
- **Authorization at the service/domain**: Is that identity permitted to act on the specific business object?

`SecurityWebFilterChain` helps enforce the first two steps; reactive method security and domain services provide defense in depth. URL rules cannot fully replace ownership rules such as "a user may only read their own documents".

## 4. `SecurityWebFilterChain` and `ServerHttpSecurity`

`SecurityWebFilterChain` defines a matcher to determine whether the chain applies to a request, and holds the `WebFilter` instances configured for that chain.

`ServerHttpSecurity` is Spring Security's DSL/builder for WebFlux. Call `.build()` to create a `SecurityWebFilterChain`.

Minimal configuration example:

```java
@Configuration
@EnableWebFluxSecurity
public class SecurityConfiguration {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers("/public/**").permitAll()
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .build();
    }
}
```

Reading from top to bottom:

1. `/public/**` can be accessed without logging in.
2. All remaining requests require an authenticated `Authentication`.
3. Enable HTTP Basic as an authentication method.
4. `.build()` creates the `WebFilter` chain that WebFlux can use.

### 4.1. Rule Ordering in `authorizeExchange`

Matchers/rules are evaluated in declaration order. Specific rules should come before `anyExchange()`.

```java
.authorizeExchange(exchange -> exchange
        .pathMatchers(HttpMethod.GET, "/api/catalog").permitAll()
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated()
        .anyExchange().denyAll())
```

If `anyExchange().permitAll()` is placed too early, subsequent rules will no longer protect endpoints as intended. Write rules from most specific to most general.

### 4.2. `permitAll`, `authenticated`, `hasRole`, and `hasAuthority`

| Rule | Meaning |
|---|---|
| `permitAll()` | Allow access regardless of identity |
| `authenticated()` | Require an authenticated user/request |
| `hasRole("ADMIN")` | Check the `ROLE_ADMIN` authority following the role prefix convention |
| `hasAuthority("invoice:write")` | Check the exact authority `invoice:write` |
| `denyAll()` | Deny all |

`hasRole("ADMIN")` does not look for the authority `"ADMIN"` directly; by default Spring Security checks `"ROLE_ADMIN"`. When a Resource Server maps OAuth2 scopes to `SCOPE_read`, `hasAuthority("SCOPE_read")` is typically used instead of `hasRole("read")`.

### 4.3. Do Not Equate `permitAll` with Bypassing Filters

`permitAll()` is an authorization decision. The request still passes through the selected security chain, including applicable filters such as security headers, CORS, or CSRF.

For example, a `permitAll` POST request can still be rejected by CSRF if CSRF is enabled and the request falls into the group requiring a CSRF token. "Allowing access" does not mean disabling all protections for the request.

## 5. `securityMatcher` Selects the Chain; `authorizeExchange` Sets Permissions

This is the most common source of confusion when multiple chains exist.

### 5.1. `securityMatcher(...)`

Defines **whether the entire `SecurityWebFilterChain` participates in handling the request**.

```java
http.securityMatcher(
        new PathPatternParserServerWebExchangeMatcher("/api/**"));
```

If a request does not match `/api/**`, the entire filter chain does not apply.

### 5.2. `pathMatchers(...)` Inside `authorizeExchange`

Defines **the authorization policy once the chain has been selected**.

```java
http.authorizeExchange(exchange -> exchange
        .pathMatchers("/api/admin/**").hasRole("ADMIN")
        .pathMatchers("/api/**").authenticated());
```

If a request does not match a specific rule, evaluation continues through the remaining rules of that chain. Therefore, you should end with `anyExchange().authenticated()` or `denyAll()`.

### 5.3. Difference by Example

```text
GET /api/admin/report
    |
    v
securityMatcher("/api/**") -> MATCH
    |
    v
authorizeExchange("/api/admin/**") -> ROLE_ADMIN
    |
    +-- insufficient role -> 403
    +-- sufficient role -> controller

GET /health
    |
    v
securityMatcher("/api/**") -> NOT MATCH
    |
    v
Evaluate lower-priority chain (fallback)
```

**Critical warning:** if no `SecurityWebFilterChain` matches the request, that request is not protected by a Spring Security web chain. Never create only an `/api/**` chain and assume other paths are blocked by default.

## 6. Multiple Chains with `@Order` and a Safe Fallback

An application may require different security mechanisms for:

- `/api/**`: Bearer JWT.
- `/console/**`: Form Login + CSRF/session.
- `/health`: public endpoint per policy.
- Everything else: denied.

Spring Security evaluates `SecurityWebFilterChain` instances in order. **The first matching chain is selected**; chains are not executed cumulatively.

Example:

```java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .authorizeExchange(exchange -> exchange
                    .pathMatchers("/api/public").permitAll()
                    .anyExchange().authenticated())
            .httpBasic(Customizer.withDefaults())
            .build();
}

@Bean
@Order(2)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchange -> exchange
                    .pathMatchers("/health").permitAll()
                    .anyExchange().denyAll())
            .httpBasic(Customizer.withDefaults())
            .build();
}
```

The second chain does not declare a `securityMatcher`, so it uses the default matcher that applies to all requests not selected by higher-priority chains.

### 6.1. Checklist When Using Multiple Chains

- Place specific chains before general chains.
- Use `@Order` instead of relying on bean registration order.
- Ensure the fallback chain actually matches all remaining URLs.
- Test API URLs, public URLs, and URLs outside any expected path.
- Do not assume authentication configuration from chain A automatically applies to chain B.
- Do not leave `/actuator/**` or `/admin/**` unprotected due to a missing matcher.
- If there is a WebSocket handshake, test whether the handshake path passes through the appropriate chain.

### 6.2. A Single Chain Can Use Multiple Authentication Methods

Not every system needs multiple chains. If multiple mechanisms are permitted for the same set of endpoints, the corresponding specs can be configured within one chain. However, if browser endpoints need CSRF/session/cookie while APIs are stateless Bearer-only, splitting chains is usually easier to review.

## 7. Where Is Authentication Integrated?

Authentication is the step of verifying credentials and creating an `Authentication` containing the principal and authorities.

Key reactive components:

| Component | Role |
|---|---|
| `AuthenticationWebFilter` | Receives request, extracts credentials, invokes authentication manager |
| `ServerAuthenticationConverter` | Converts `ServerWebExchange` into an authentication token |
| `ReactiveAuthenticationManager` | Verifies the token and returns `Mono<Authentication>` |
| `ReactiveUserDetailsService` | Retrieves a user by username using a reactive API |
| `PasswordEncoder` | Hashes/verifies passwords |
| `ServerSecurityContextRepository` | Loads/saves `SecurityContext` according to a strategy |
| `ReactiveSecurityContextHolder` | Accesses `SecurityContext` in the Reactor Context |
| `ServerAuthenticationEntryPoint` | Handles when authentication is required, typically producing 401 |
| `ServerAccessDeniedHandler` | Handles when authenticated but permission is denied, typically 403 |

### 7.1. HTTP Basic

A chain can enable Basic:

```java
.httpBasic(Customizer.withDefaults())
```

For username/password, Spring uses the appropriate authentication mechanism, such as `ReactiveUserDetailsService` and a password encoder.

Example registering in-memory users (for demo/test only):

```java
@Bean
PasswordEncoder passwordEncoder() {
    return new BCryptPasswordEncoder();
}

@Bean
MapReactiveUserDetailsService demoUsers(PasswordEncoder encoder) {
    UserDetails reader = User.withUsername("reader")
            .password(encoder.encode("read-pass"))
            .roles("READER")
            .build();

    return new MapReactiveUserDetailsService(reader);
}
```

For production, use an identity provider/directory or a corresponding reactive repository. Never hardcode credentials, never use `{noop}` for production passwords, and never log the `Authorization` header.

### 7.2. `AuthenticationWebFilter`: Extension Point for Authentication

If a custom credential mechanism is needed (such as a token passed in a header with a special contract), an `AuthenticationWebFilter` can use:

1. `setRequiresAuthenticationMatcher(...)` to restrict which requests it applies to.
2. `setServerAuthenticationConverter(...)` to parse credentials.
3. `ReactiveAuthenticationManager` to validate.
4. Appropriate success/failure handlers and context repository.

In standard scenarios, prefer built-in Spring Security modules: HTTP Basic, OAuth2 Login, Resource Server Bearer token. Do not write a custom JWT parsing filter that skips verifying signature/issuer/audience/expiry.

### 7.3. `ReactiveAuthenticationManager` Must Be Truly Reactive

The manager returns `Mono<Authentication>`. Avoid calling blocking JPA/JDBC or synchronous HTTP directly on the Netty event loop inside the authentication pipeline. If the identity store only supports blocking I/O, prefer a reactive alternative or isolate blocking work on an appropriate bounded scheduler.

Never place user credentials into a global singleton field where other requests could accidentally share them.

## 8. `SecurityContext` in the Reactor Context, Not ThreadLocal

In Servlet applications, many examples use:

```java
SecurityContextHolder.getContext().getAuthentication();
```

In reactive WebFlux, execution can hop across multiple threads due to scheduling and asynchrony. `ThreadLocal` is not a reliable place to propagate authentication across reactive operators.

Spring Security places `SecurityContext` in the **Reactor Context** of the publisher. Use:

```java
Mono<String> currentUsername =
        ReactiveSecurityContextHolder.getContext()
                .map(context -> context.getAuthentication().getName());
```

In a controller:

```java
@GetMapping("/api/me")
public Mono<String> me() {
    return ReactiveSecurityContextHolder.getContext()
            .map(context -> context.getAuthentication().getName());
}
```

When a request is authenticated, the context flows along with the subscription. If code spawns its own thread/task and calls a detached `subscribe()`, you cannot assume context and cancellation automatically propagate to that task.

### 8.1. Using Identity Across an Async Boundary

Example:

```java
public Mono<Profile> profile() {
    return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication().getName())
            .flatMap(profileRepository::findByUsername);
}
```

The publisher returned from the service remains part of the request pipeline. If `profileRepository` is a reactive repository, there is no need to block.

### 8.2. When to Use `contextWrite(...)`?

Spring Security creates the context when authenticating the request; most controllers/services **do not need to attach authentication manually**. `contextWrite(ReactiveSecurityContextHolder.withAuthentication(...))` is useful in infrastructure/test code or specifically designed boundaries, not as a way for a user to grant themselves privileges.

Never take a username from a header and construct an authenticated `Authentication` to bypass Spring Security.

## 9. Authorization at HTTP and Service Layers

HTTP authorization protects the API surface. Method security protects business operations after the request has passed through the security chain.

### 9.1. Enabling Reactive Method Security

```java
@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
class SecurityConfig {
}
```

Service:

```java
@Service
public class BillingService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> readFinanceSummary() {
        return Mono.just("finance-summary");
    }
}
```

`@PreAuthorize` intercepts the method based on the authentication/authorities in the reactive context. The method must be invoked through a Spring bean proxy; self-invocation within the same instance can bypass the advice.

### 9.2. Why Are URL Rules Still Needed?

Not every request enters an annotated method; controllers, functional routes, static resources, and fallbacks all need a default policy.

Defense-in-depth example:

```java
.authorizeExchange(exchange -> exchange
        .pathMatchers("/api/reports/**").authenticated()
        .anyExchange().denyAll())
```

In the service:

```java
@PreAuthorize("hasRole('ADMIN')")
public Mono<Report> confidentialReport() {
    return repository.loadConfidentialReport();
}
```

The URL requires being logged in; the service requires `ADMIN`. If a route or caller changes later, the method still retains a verification layer.

### 9.3. Checking Resource Ownership

Roles are only sufficient for general rules. If you need "user A may only view user A's invoices", the domain service must check the relationship between the principal and the resource ID, rather than relying solely on `/api/invoices/{id}`.

You can use custom reactive authorization logic or check inside the service after loading metadata. Avoid exposing sensitive ownership information in error messages.

## 10. `SecurityWebFiltersOrder` and Custom `WebFilter`

Spring Security defines relative positions via the `SecurityWebFiltersOrder` enum, such as `AUTHENTICATION`, `EXCEPTION_TRANSLATION`, `AUTHORIZATION`, `CSRF`, `HTTP_BASIC`, `REACTOR_CONTEXT`, and others.

You can add a custom filter to **a security chain** using:

```java
http.addFilterBefore(customFilter, SecurityWebFiltersOrder.AUTHORIZATION);
http.addFilterAfter(customFilter, SecurityWebFiltersOrder.AUTHENTICATION);
http.addFilterAt(customFilter, SecurityWebFiltersOrder.AUTHENTICATION);
```

The snippet above illustrates the three position-selection APIs; **do not call all three** for the same filter without a reason, as that would add the filter multiple times.

### 10.1. Example Filter Recording Processing Time

```java
WebFilter timingFilter = (exchange, chain) -> {
    long started = System.nanoTime();

    return chain.filter(exchange)
            .doFinally(signal -> {
                long millis = java.util.concurrent.TimeUnit.NANOSECONDS
                        .toMillis(System.nanoTime() - started);

                metrics.record("api.response", millis);
            });
};

http.addFilterAfter(timingFilter, SecurityWebFiltersOrder.AUTHORIZATION);
```

`metrics.record(...)` is an illustrative API of an application metrics adapter. Use Micrometer Observation/Tracing when the system already has standard observability tooling, rather than creating custom tags containing full URLs or personal information.

### 10.2. Using the Right Position When Authentication Is Involved

- Filters that read credentials should be integrated into the authentication pipeline, not arbitrarily placed after Authorization.
- Filters that need to read the authenticated principal must be placed at an appropriate position and read from the Reactor Context, not `ThreadLocal`.
- Filters that modify request metadata must avoid altering `Authorization` or bypassing matchers.
- Custom filters should have tests proving which routes pass through them.

A `@Component WebFilter` resides in the global WebFlux filter chain and has a different scope from a filter added via `ServerHttpSecurity.addFilter...` within a security chain. Understand the scope clearly before choosing how to register it.

## 11. Spring Security WebFlux and HTTP 401/403

Two important responses:

- **401 Unauthorized**: no valid credentials or authentication is required; with HTTP Basic, `WWW-Authenticate` is typically included.
- **403 Forbidden**: the request is authenticated but lacks the required permissions, or was rejected by a policy such as CSRF.

Examples:

| Request | Rule | Typical Outcome |
|---|---|---|
| No credentials → `GET /api/me` | `authenticated()` | 401 |
| Basic with wrong password → `GET /api/me` | `authenticated()` | 401 |
| User ROLE_READER → `GET /api/admin` | `hasRole("ADMIN")` | 403 |
| User ROLE_ADMIN → `GET /api/admin` | `hasRole("ADMIN")` | 200 |
| User ROLE_EDITOR → POST with CSRF protection but missing token | `hasRole("EDITOR")` | 403 |
| Request to a path outside any chain | No matching filter chain | Risk of not being protected by Spring Security |

Spring Security uses exception translation to invoke the authentication entry point or access denied handler depending on the error and authentication state.

### 11.1. Customizing the Entry Point / Denied Handler

You can configure:

```java
.exceptionHandling(spec -> spec
        .authenticationEntryPoint((exchange, error) -> {
            exchange.getResponse()
                    .setStatusCode(HttpStatus.UNAUTHORIZED);
            return exchange.getResponse().setComplete();
        })
        .accessDeniedHandler((exchange, error) -> {
            exchange.getResponse()
                    .setStatusCode(HttpStatus.FORBIDDEN);
            return exchange.getResponse().setComplete();
        }))
```

The example lambdas only return the status code with no body. When replacing the HTTP Basic entry point, consider preserving `WWW-Authenticate` semantics for compatible clients. If writing a JSON `ProblemDetail`, use a reactive response writer, set `Content-Type`, and avoid leaking authentication failure reasons or secrets.

Never return `200 OK` with `"not authorized"` instead of 401/403, as clients, gateways, and observability require accurate status codes.

## 12. CSRF in WebFlux: Do Not Disable It Arbitrarily

CSRF occurs when a victim's browser automatically sends stored credentials (such as a session cookie or Basic credentials) to a website while an attacker tricks the browser into sending a state-changing request.

Spring Security WebFlux enables CSRF protection by default. Safe requests such as GET/HEAD/OPTIONS/TRACE normally do not require a CSRF token, whereas POST/PUT/PATCH/DELETE typically require a token when the default policy applies.

Example request:

```http
POST /api/items HTTP/1.1
Authorization: Basic ...
Content-Type: application/json
```

Even if authentication is valid and the user has `ROLE_EDITOR`, the POST can still receive **403** when the CSRF token is missing.

### 12.1. Does CSRF Apply to HTTP Basic?

Yes. Browsers can automatically attach stored Basic credentials. Therefore, it is incorrect to say "an API using Basic definitely does not need CSRF".

An API that only accepts a Bearer token manually attached in the `Authorization` header, without cookies or ambient browser credentials, generally has a different CSRF threat model. Only consider disabling CSRF **in that specific stateless chain** after verifying all credential paths, CORS, frontend, and login/logout flows.

### 12.2. Do Not Confuse CSRF with CORS

- **CORS** restricts which website origins are allowed to access cross-origin responses in the browser.
- **CSRF** protects against browsers automatically sending requests with credentials without the user's intent.

Enabling CORS does not replace CSRF. CORS is also not authentication/authorization; `curl` or server-to-server clients are not subject to browser CORS rules.

### 12.3. Testing CSRF with Spring Security Test

```java
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;

client.mutateWith(csrf())
        .post()
        .uri("/api/items")
        .bodyValue(new ItemRequest("Notebook"))
        .exchange()
        .expectStatus().isOk();
```

In a real application, the browser/form needs a mechanism to receive and send the CSRF token matching the `ServerCsrfTokenRepository` in use. The test helper is not a guide for production clients to arbitrarily fabricate tokens.

## 13. CORS and Browser Requests

A request from `https://app.example.com` to `https://api.example.com` may undergo a CORS preflight before sending the actual request, especially when using a custom `Authorization` header.

Spring WebFlux provides CORS configuration via `CorsConfiguration` and `CorsWebFilter`/WebFlux mappings. Spring Security has `.cors(Customizer.withDefaults())` to coordinate CORS handling when a suitable configuration source is provided.

Example illustrating specific origin configuration:

```java
CorsConfiguration config = new CorsConfiguration();
config.setAllowedOrigins(List.of("https://app.example.com"));
config.setAllowedMethods(List.of("GET", "POST"));
config.setAllowedHeaders(List.of("Authorization", "Content-Type",
        "X-CSRF-TOKEN"));
config.setAllowCredentials(true);
```

The snippet above only creates the config object; it must be registered via a `CorsConfigurationSource` or WebFlux configuration to take effect.

If `allowCredentials=true`, do not use the wildcard `*` for `allowedOrigins` in a way that violates the policy. Only allow genuinely trusted origins.

OPTIONS preflight requests should not require credentials that browsers do not send during preflight. Verify that CORS is handled early enough in the filter chain, and do not broaden the allowed origins list merely to work around frontend errors.

## 14. Sessions, Context Repository, and Stateless APIs

`ServerSecurityContextRepository` allows Spring Security to load/save `SecurityContext` via a storage strategy.

Common implementations:

- `WebSessionServerSecurityContextRepository`: stores context information in `WebSession` when the configuration uses sessions.
- `NoOpServerSecurityContextRepository`: does not persist context across requests.
- Custom repository: used for a specific design whose threat model has been evaluated.

Do not infer that `.httpBasic()` automatically makes the entire application stateless under every configuration. A chain may use a default or customized repository; always check the actual policy.

For a Bearer JWT API, each request can be authenticated independently via the token. If the API does not use sessions/cookies, `NoOpServerSecurityContextRepository` fits the goal of not storing the security context in an HTTP session.

API-only example (independent of the Basic project later in this lesson):

```java
SecurityWebFilterChain jwtChain(ServerHttpSecurity http) {
    return http
            .securityMatcher(
                    new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .securityContextRepository(
                    NoOpServerSecurityContextRepository.getInstance())
            .authorizeExchange(exchange -> exchange
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
            .build();
}
```

An appropriate `ReactiveJwtDecoder` or issuer/JWK Set URI must be configured; enabling the DSL above alone is not enough to trust JWTs properly. Disabling CSRF, if done, must be a separate, conditional decision made after reviewing all cookie/credential flows.

## 15. OAuth2 Resource Server JWT Integration

When a WebFlux API receives Bearer tokens issued by an authorization server, prefer Spring Security OAuth2 Resource Server over parsing JWTs manually:

Maven dependency:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
```

Issuer configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/issuer
```

Resource Server typically fetches metadata/JWK Set via issuer discovery and verifies signature, issuer, `exp`, and `nbf` according to the configured decoder's capabilities. Production applications also need to verify the audience (`aud`) matches the API, scope/authority mapping, and key rotation strategy.

JWT chain example:

```java
@Bean
SecurityWebFilterChain resourceServerChain(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchange -> exchange
                    .pathMatchers("/api/public").permitAll()
                    .pathMatchers("/api/admin/**")
                        .hasAuthority("SCOPE_catalog.admin")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2
                    .jwt(Customizer.withDefaults()))
            .build();
}
```

The snippet above is an alternative configuration option replacing the HTTP Basic chain in the sample project. Do not register both catch-all beans without `@Order` and explicit matchers.

### JWT Authentication Is Not OAuth2 Client

- **Resource Server** validates Bearer tokens sent to the application.
- **OAuth2 Client** helps the application log in via an Identity Provider or obtain access tokens to call other APIs.
- **Authorization Server** is the party issuing tokens.

An application can hold multiple roles, but the configuration needs clear boundaries, trust relationships, and credential sources.

### JWT Authorities and Scopes

Spring Security can map scopes in the token to `SCOPE_<scope>` authorities. For example, scope `"catalog.read"` becomes `"SCOPE_catalog.read"` under the default mapping. If the token uses a custom roles claim, a `ReactiveJwtAuthenticationConverter` or another tested converter is needed to produce the appropriate authorities.

Do not use `.hasRole("ADMIN")` and assume the JWT scope `admin` automatically becomes `ROLE_ADMIN`.

## 16. Other Integration Points in Spring WebFlux

### 16.1. `@RestController` and Functional Routes

Because security sits at the `WebFilter` layer before the handler, the same `SecurityWebFilterChain` can protect both annotated controllers and `RouterFunction` routes.

A functional route:

```java
RouterFunction<ServerResponse> routes(Handler handler) {
    return RouterFunctions.route()
            .GET("/api/items/{id}", handler::findById)
            .build();
}
```

If the path matches the `/api/**` chain, the route is still governed by that chain's authentication/authorization policy. There is no need to write a separate security interceptor solely because the application uses functional endpoints.

### 16.2. Calling Downstream Services with `WebClient`

Spring Security protects **inbound** server requests. When a service uses `WebClient` to call downstream services, token forwarding or OAuth2 Client token acquisition is a separate concern.

Never automatically forward the inbound request's raw `Authorization` header to every downstream host. Only forward tokens to permitted audiences/hosts, or use `ServerOAuth2AuthorizedClientExchangeFilterFunction` in a client with appropriate scopes.

### 16.3. WebSocket Handshake

WebSocket begins with an HTTP upgrade request, so the handshake URL can still be protected by WebFlux `SecurityWebFilterChain`. After upgrading, WebSocket messages are not new HTTP requests; business authorization for each message/command requires a separate mechanism.

### 16.4. RSocket

Spring Security has dedicated RSocket authentication/authorization support at the RSocket layer. `SecurityWebFilterChain` does not automatically protect individual RSocket messages just because the application also runs WebFlux HTTP. RSocket over WebSocket has an HTTP handshake, but RSocket message security must still be designed at the protocol level.

### 16.5. Reverse Proxy and Forwarded Headers

If TLS terminates at the ingress, WebFlux may see plain HTTP connections from the proxy. Any redirect-to-HTTPS rule relying on the scheme requires trustworthy forwarded headers. The proxy at the trust boundary must strip spoofed `Forwarded`/`X-Forwarded-*` headers and set the metadata cleanly. `ForwardedHeaderTransformer` does not itself verify that headers came from a trusted proxy.

## 17. Spring Boot Auto-Configuration and Configuration Pitfalls

Add dependencies:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
</dependency>
```

When Spring Security is on the classpath, Spring Boot provides default security for web applications, including WebFlux. In development environments, there may be a default user named `user` with an auto-generated password; this is **not** a production identity store.

When you provide a `SecurityWebFilterChain` bean, you can customize rules and authentication modes. When you provide a `ReactiveUserDetailsService` or `ReactiveAuthenticationManager`, you can customize the authentication user setup. Boot auto-configuration has specific backoff rules and can behave differently when adding OAuth2 modules; do not assume all default beans disappear merely by defining a single chain.

### Ways to Check

- Is `spring-boot-starter-web` present, causing the application to run Servlet instead of WebFlux?
- Are there multiple `SecurityWebFilterChain` beans without `@Order` or a catch-all?
- Is there a `WebFilterChainProxy` bean manually created by the framework/app?
- Is an OAuth2 Resource Server/JWT module present without configured issuer/JWK settings?
- Is `@EnableReactiveMethodSecurity` enabled if `@PreAuthorize` is used?
- Is `@EnableWebSecurity` (Servlet) mistakenly used in WebFlux?
- Are there demo accounts or passwords not yet replaced for production?

## 18. Runnable Java 17+ Project: Multiple Chains, Basic, CSRF, and Method Security

The small project below demonstrates:

1. A dedicated security chain for `/api/**`, and a fallback chain for everything else.
2. `GET /api/public` requires no credentials.
3. `GET /api/me` requires authentication.
4. `GET /api/admin` requires `ROLE_ADMIN`.
5. `POST /api/items` requires `ROLE_EDITOR` and a CSRF token.
6. `GET /api/reports/secret` uses `@PreAuthorize("hasRole('ADMIN')")`.
7. `GET /health` is publicly permitted.
8. Other URLs are denied by the fallback chain.
9. `WebTestClient` verifies 200/401/403 statuses and response bodies.
10. Demo credentials are BCrypt-hashed; no real passwords are used.

### 18.1. Directory Structure

```text
webflux-security-chain/
├── pom.xml
└── src/
    ├── main/java/edu/demo/security/
    │   ├── SecurityApplication.java
    │   ├── SecurityConfig.java
    │   ├── ApiController.java
    │   └── ReportService.java
    └── test/java/edu/demo/security/
        └── SecurityIntegrationTests.java
```

### 18.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>edu.demo</groupId>
    <artifactId>webflux-security-chain</artifactId>
    <version>1.0.0</version>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

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
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### 18.3. `SecurityApplication.java`

```java
package edu.demo.security;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SecurityApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecurityApplication.class, args);
    }
}
```

### 18.4. `SecurityConfig.java`

```java
package edu.demo.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration
        .EnableReactiveMethodSecurity;
import org.springframework.security.config.annotation.web.reactive
        .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.provisioning.MapReactiveUserDetailsService;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher
        .PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
@EnableReactiveMethodSecurity
public class SecurityConfig {

    @Bean
    PasswordEncoder passwordEncoder() {
        return new BCryptPasswordEncoder();
    }

    @Bean
    MapReactiveUserDetailsService users(PasswordEncoder encoder) {
        UserDetails reader = User.withUsername("reader")
                .password(encoder.encode("read-pass"))
                .roles("READER")
                .build();

        UserDetails editor = User.withUsername("editor")
                .password(encoder.encode("editor-pass"))
                .roles("EDITOR")
                .build();

        UserDetails admin = User.withUsername("admin")
                .password(encoder.encode("admin-pass"))
                .roles("ADMIN")
                .build();

        return new MapReactiveUserDetailsService(
                reader, editor, admin);
    }

    @Bean
    @Order(1)
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                .securityMatcher(
                        new PathPatternParserServerWebExchangeMatcher(
                                "/api/**"))
                .authorizeExchange(exchange -> exchange
                        .pathMatchers(HttpMethod.GET, "/api/public")
                            .permitAll()
                        .pathMatchers(HttpMethod.GET, "/api/admin")
                            .hasRole("ADMIN")
                        .pathMatchers(HttpMethod.POST, "/api/items")
                            .hasRole("EDITOR")
                        .anyExchange().authenticated())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain fallbackSecurity(ServerHttpSecurity http) {
        return http
                .authorizeExchange(exchange -> exchange
                        .pathMatchers(HttpMethod.GET, "/health")
                            .permitAll()
                        .anyExchange().denyAll())
                .httpBasic(Customizer.withDefaults())
                .formLogin(form -> form.disable())
                .build();
    }
}
```

The two chains have explicit matchers and orders. POST requests remain subject to default CSRF protection; the code does not disable CSRF.

These usernames/passwords are for demo/test only. In production, manage credentials through an identity provider or secure storage, enforce appropriate hashing policies, and never place passwords in code.

### 18.5. `ReportService.java`

```java
package edu.demo.security;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public class ReportService {

    @PreAuthorize("hasRole('ADMIN')")
    public Mono<String> secretReport() {
        return Mono.just("finance-report");
    }
}
```

The service policy is enforced when the method is called through a Spring proxy, after the authenticated security context has been propagated into the Reactor pipeline.

### 18.6. `ApiController.java`

```java
package edu.demo.security;

import java.util.Map;

import org.springframework.http.MediaType;
import org.springframework.security.core.context
        .ReactiveSecurityContextHolder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    private final ReportService reportService;

    public ApiController(ReportService reportService) {
        this.reportService = reportService;
    }

    @GetMapping("/api/public")
    public Mono<String> publicInfo() {
        return Mono.just("public");
    }

    @GetMapping("/api/me")
    public Mono<String> me() {
        return ReactiveSecurityContextHolder.getContext()
                .map(context ->
                        context.getAuthentication().getName());
    }

    @GetMapping("/api/admin")
    public Mono<String> admin() {
        return Mono.just("admin-only");
    }

    @GetMapping("/api/reports/secret")
    public Mono<String> secretReport() {
        return reportService.secretReport();
    }

    @PostMapping(
            path = "/api/items",
            consumes = MediaType.APPLICATION_JSON_VALUE)
    public Mono<Map<String, String>> createItem(
            @RequestBody Mono<ItemRequest> incoming) {

        return incoming.map(item ->
                Map.of("name", item.name(), "state", "created"));
    }

    @GetMapping("/health")
    public Mono<String> health() {
        return Mono.just("healthy");
    }

    @GetMapping("/unexpected")
    public Mono<String> unexpected() {
        return Mono.just("should-not-be-visible");
    }

    public record ItemRequest(String name) {
    }
}
```

`/api/me` shows how to read identity from the Reactor Context. The `/api/reports/secret` endpoint only requires being authenticated in its URL rule, but is checked for `ROLE_ADMIN` by `ReportService`.

In this simple example, the service returns a fixed string; production code must enforce permissions on specific resources/domains and validate request bodies.

### 18.7. `SecurityIntegrationTests.java`

```java
package edu.demo.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.csrf;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockUser;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class SecurityIntegrationTests {

    @Autowired
    ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void publicApiDoesNotRequireAuthentication() {
        client.get()
                .uri("/api/public")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("public");
    }

    @Test
    void healthIsPublicThroughFallbackChain() {
        client.get()
                .uri("/health")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("healthy");
    }

    @Test
    void protectedApiWithoutCredentialsReturns401() {
        client.get()
                .uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void wrongBasicCredentialsReturn401() {
        client.get()
                .uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth("reader", "wrong"))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void validBasicCredentialsExposeUsername() {
        client.get()
                .uri("/api/me")
                .headers(headers ->
                        headers.setBasicAuth("reader", "read-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("reader");
    }

    @Test
    void readerCannotEnterAdminEndpoint() {
        client.get()
                .uri("/api/admin")
                .headers(headers ->
                        headers.setBasicAuth("reader", "read-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void adminCanEnterAdminEndpoint() {
        client.get()
                .uri("/api/admin")
                .headers(headers ->
                        headers.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-only");
    }

    @Test
    void serviceMethodSecurityDeniesReader() {
        client.get()
                .uri("/api/reports/secret")
                .headers(headers ->
                        headers.setBasicAuth("reader", "read-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void serviceMethodSecurityAllowsAdmin() {
        client.get()
                .uri("/api/reports/secret")
                .headers(headers ->
                        headers.setBasicAuth("admin", "admin-pass"))
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("finance-report");
    }

    @Test
    void editorPostWithoutCsrfIsForbidden() {
        client.post()
                .uri("/api/items")
                .headers(headers ->
                        headers.setBasicAuth("editor", "editor-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.ItemRequest("Notebook"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void editorPostWithValidCsrfSucceeds() {
        client.mutateWith(csrf())
                .post()
                .uri("/api/items")
                .headers(headers ->
                        headers.setBasicAuth("editor", "editor-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.ItemRequest("Notebook"))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.name").isEqualTo("Notebook")
                .jsonPath("$.state").isEqualTo("created");
    }

    @Test
    void readerWithCsrfStillCannotCreateItem() {
        client.mutateWith(csrf())
                .post()
                .uri("/api/items")
                .headers(headers ->
                        headers.setBasicAuth("reader", "read-pass"))
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(new ApiController.ItemRequest("Notebook"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void fallbackChainDeniesOtherPathsEvenWhenLoggedIn() {
        client.get()
                .uri("/unexpected")
                .headers(headers ->
                        headers.setBasicAuth("reader", "read-pass"))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void mockUserCanTestAuthorizationWithoutPassword() {
        client.mutateWith(mockUser().roles("ADMIN"))
                .get()
                .uri("/api/admin")
                .exchange()
                .expectStatus().isOk()
                .expectBody(String.class).isEqualTo("admin-only");
    }
}
```

`WebTestClient.bindToApplicationContext` uses the WebFlux mock server pipeline without needing to open a real HTTP port. `.apply(springSecurity())` integrates Spring Security Test with `WebTestClient`, enabling per-request mutators like `mockUser()` and `csrf()`. Tests using HTTP Basic directly also verify real credentials against the demo in-memory user store.

Assertion targets:

| Group | Result |
|---|---|
| Public API/health | 200 |
| Missing Basic or wrong password | 401 |
| ROLE_READER accessing admin | 403 |
| ROLE_ADMIN accessing admin | 200 |
| `@PreAuthorize` denies reader | 403 |
| `@PreAuthorize` allows admin | 200 |
| POST as editor without CSRF | 403 |
| POST as editor with valid CSRF | 200 + JSON |
| POST as reader even with CSRF | 403 |
| Fallback path | 403 |
| Mock principal for admin | 200 |

These are expected outcomes, not test results recorded from an actual Maven run in the authoring environment.

### 18.8. Running the Project

In the directory containing `pom.xml`:

```bash
mvn test
```

Start the server:

```bash
mvn spring-boot:run
```

Public GET:

```bash
curl -i http://localhost:8080/api/public
```

GET with demo Basic credentials:

```bash
curl -i -u reader:read-pass http://localhost:8080/api/me
```

Admin GET:

```bash
curl -i -u admin:admin-pass http://localhost:8080/api/admin
```

Do not use demo passwords or cleartext HTTP in production. In real systems, HTTPS/TLS is a minimum requirement when transmitting Basic credentials. POST requests from browsers/clients must follow the application's CSRF token flow; do not simply add a Basic header and assume data writes will succeed.

### 18.9. What the Sample Tests Do Not Cover

For production readiness, additional tests are needed:

- Invalid or expired CSRF tokens.
- Role changes during a session.
- Slow or temporarily failing authentication backends.
- CORS preflight from allowed/disallowed origins.
- OAuth2 JWT issuer/audience/scope validation.
- Authentication/authorization at WebSocket handshakes.
- Method security with `Mono.error`, `Flux`, and cancellation.
- Reverse proxy forwarded headers and HTTPS redirects.
- Path encoding/trailing slash/URL normalization.
- Security HTTP response headers and caching policies.
- Multiple chains when Actuator endpoints are present.

## 19. Testing: Mock Identity vs. Testing Real Credentials

There are two distinct layers of testing.

### 19.1. Mock User

```java
client.mutateWith(mockUser().roles("ADMIN"))
        .get()
        .uri("/api/admin")
        .exchange()
        .expectStatus().isOk();
```

Convenient for testing authorization rules, but it **does not** prove that the Basic password encoder, JWT signature validation, or connection to the identity provider actually works.

### 19.2. Sending Real Credentials in Tests

```java
client.get()
        .uri("/api/me")
        .headers(headers ->
                headers.setBasicAuth("reader", "read-pass"))
        .exchange()
        .expectStatus().isOk();
```

This tests the Basic authentication pipeline and the configured user service in the test application context.

For JWT, Spring Security Test provides `mockJwt()` to test authorization with simulated authorities/claims; use separate integration tests to verify signatures, expiry, audience, issuer, and JWK rotation.

### 19.3. Testing Beyond the Happy Path

At minimum, include cases for:

- Unauthenticated → 401.
- Authenticated but lacking permission → 403.
- Authenticated with sufficient permission → 200/201.
- `permitAll` endpoints.
- CSRF protection with unsafe HTTP methods.
- URLs outside the intended chain.
- URLs matching multiple matchers: verifying chain precedence.
- Method security outside HTTP handlers if the service has other callers.

## 20. Per-Request Authorization and Idempotency Checks

Security only decides who is permitted to invoke an operation. It does not guarantee that an operation can be safely retried or will not cause duplicate side effects.

For example, an order creation endpoint:

```text
POST /api/orders
```

Even when `ROLE_EDITOR` is allowed to POST and the CSRF token is valid, a client retry due to a timeout can still resubmit a transaction already processed by the server. You must design idempotency keys, transaction boundaries, and ownership-checking authorization at the domain layer.

Do not mix authentication/authorization logic with retry handling, database transactions, or outbound network calls inside a complex custom `WebFilter`. Filters should handle appropriate security/observability responsibilities, while business use cases belong in services.

## 21. Common Mistakes and Fixes

| Mistake | Consequence | Fix |
|---|---|---|
| Using `HttpSecurity`/`SecurityFilterChain` in WebFlux | Configuring the wrong stack | Use `ServerHttpSecurity`/`SecurityWebFilterChain` |
| Defining an `/api/**` chain with no fallback | Other paths may remain unprotected | Create a catch-all chain with `anyExchange().denyAll()` |
| Confusing `securityMatcher` with `pathMatchers` | Thinking a path is protected when the chain never applies | Distinguish selecting a chain from authorizing within a chain |
| Placing `anyExchange().permitAll()` too early | Stricter rules afterward do not apply | Order from most specific to most general |
| Multiple chains without `@Order` | Unpredictable which chain matches first | Declare explicit ordering |
| Assuming `permitAll` bypasses all filters | Public POST still rejected by CSRF | Understand the security pipeline and token policy |
| Using `hasRole("ADMIN")` with authority `"ADMIN"` | Role check fails | Use `ROLE_ADMIN` or `hasAuthority` matching the contract |
| Treating JWT scope `admin` as role ADMIN without a converter | Incorrect authorization | Configure tested authority mapping |
| Calling `SecurityContextHolder` as in Servlet | Context lost on thread switches | Use `ReactiveSecurityContextHolder` |
| Calling `subscribe()` manually inside a service | Detaches context, errors, and cancellation | Return/compose `Mono`/`Flux` |
| Disabling CSRF for all chains | Browser sessions/Basic become vulnerable to CSRF | Disable only for a verified stateless Bearer-only threat model |
| Using CORS as a substitute for authentication | Non-browser clients can still call the API | Protect with real authentication/authorization |
| Allowing all origins with credentials | Increases risk of data being read by untrusted sites | Allowlist specific origins |
| Decoding JWTs manually without verifying signature/issuer/expiry | Forged tokens may be accepted | Use OAuth2 Resource Server and validators |
| Storing Bearer tokens in a global field | Leaks tokens across multiple users | Scope tokens per request/authorized client |
| Annotating `@PreAuthorize` without enabling method security | Annotations are not enforced | Enable `@EnableReactiveMethodSecurity` and test |
| Self-invoking an annotated method | Bypasses Spring proxy/interceptor | Call across a bean boundary or redesign the service |
| Blocking the event loop in the auth manager | Increases latency for all requests | Use reactive I/O or a bounded scheduler |
| Logging raw `Authorization`/cookies | Leaks credentials | Mask secrets and log safe metadata |
| Returning 403 for all authentication failures | Clients do not know when login is required | Distinguish 401 entry point from 403 access denied |
| Injecting arbitrary roles from a request header into the context | Privilege escalation | Verify credentials through the authentication manager |
| Assuming a security chain protects every WebSocket/RSocket message | Missing per-message authorization | Design protocol/message-level security separately |
| Not testing routes outside chains | Exposes endpoints when new controllers are added | Fallback `denyAll` + regression tests |

## 22. Production Checklist

### Architecture

- Is the application running reactive WebFlux rather than Servlet?
- Are `SecurityWebFilterChain` beans of the correct type?
- Does each chain have an appropriate `securityMatcher` and `@Order`?
- Is there a catch-all chain or deny policy for undeclared URLs?
- Are specific rules placed before `anyExchange()`?
- Are error, actuator, and WebSocket handshake endpoints tested?

### Authentication

- Are standard HTTP Basic/OAuth2 Resource Server/OAuth2 Client mechanisms used?
- Do `ReactiveAuthenticationManager` and the identity store avoid blocking the event loop?
- Is a secure password encoder used without storing plain text?
- Do credentials/tokens have appropriate TTL, rotation, and revocation policies?
- Are JWT signature, issuer, audience, `exp`/`nbf`, and authorities verified?
- Are tokens excluded from URLs, logs, and metrics tags?

### Authorization

- Are roles and authorities mapped according to convention?
- Is `@EnableReactiveMethodSecurity` enabled if `@PreAuthorize` is used?
- Are services invoked through a Spring proxy so advice runs?
- Are resource ownership/domain policies checked?
- Are 401 and 403 distinguished in the response contract?
- Are both authenticated-insufficient-permission and sufficient-permission cases tested?

### Web Security

- Is CSRF enabled wherever ambient browser credentials exist?
- Is the CORS allowlist reasonable and does preflight work?
- Are HTTPS/TLS and proxy forwarded headers handled safely?
- Are cookies/sessions configured with appropriate `Secure`, `HttpOnly`, and `SameSite` flags?
- Are security response headers retained per policy?
- Are management/diagnostics endpoints prevented from unintentional exposure?

### Reactive and Operations

- Is `ThreadLocal` avoided for propagating security context across operators?
- Are manual `subscribe()`/blocking calls avoided in the authentication/authorization pipeline?
- Are metrics collected for authentication failures, access denials, and latency?
- Is rate limiting/abuse protection present if needed?
- Are correlation IDs logged without logging raw credentials?
- Are integration tests implemented with `WebTestClient` including negative scenarios?

## 23. Self-Check Questions

**1.** How does `SecurityWebFilterChain` differ from `SecurityFilterChain`?

**Answer:** `SecurityWebFilterChain` is the reactive type for WebFlux (`WebFilter`); `SecurityFilterChain` belongs to Servlet (`Filter`).

**2.** Do `securityMatcher("/api/**")` and `pathMatchers("/api/admin")` share the same responsibility?

**Answer:** No. `securityMatcher` decides whether the chain applies; `pathMatchers` inside `authorizeExchange` selects authorization rules once that chain has been chosen.

**3.** If no chain matches `/debug`, is the endpoint automatically denied?

**Answer:** You cannot rely on that. Requests without a matching security chain risk not being protected by Spring Security. A catch-all chain is needed.

**4.** What authority does `hasRole("ADMIN")` require by default?

**Answer:** `ROLE_ADMIN`.

**5.** Which status does an authenticated user lacking the required role typically receive?

**Answer:** 403 Forbidden. When valid credentials are missing, 401 Unauthorized is typically returned via the appropriate entry point.

**6.** In a WebFlux service, where do you retrieve authentication from?

**Answer:** `ReactiveSecurityContextHolder.getContext()` in the Reactor Context, not Servlet `ThreadLocal` as the primary source.

**7.** Should CSRF be disabled simply because an API uses HTTP Basic?

**Answer:** No. Browsers can automatically send Basic credentials. CSRF must be evaluated based on credential type and how browsers actually send requests.

**8.** Which annotation is needed to enable `@PreAuthorize` on a service in a WebFlux application?

**Answer:** `@EnableReactiveMethodSecurity`, and the method must be called through a Spring-managed proxy with the reactive context.

**9.** What authority does JWT scope `catalog.read` typically become under the default mapping?

**Answer:** `SCOPE_catalog.read`.

**10.** What does `mockUser()` test and what does it not test?

**Answer:** It tests authorization rules with a simulated principal. It does not prove password hashing, JWT signature/issuer/audience validation, or connectivity to a real identity provider.

## 24. Key Takeaways

- WebFlux Security relies on `WebFilter`, `SecurityWebFilterChain`, and `ServerHttpSecurity`.
- `WebFilterChainProxy` selects one matching chain for a request; higher-priority chains are evaluated first.
- `securityMatcher` selects the chain; `authorizeExchange` defines access permissions within the chain.
- Include a fallback chain to avoid unprotected URLs.
- Authentication runs via `AuthenticationWebFilter`/`ReactiveAuthenticationManager`; authorization runs via the corresponding `WebFilter`s.
- Identity travels with the Reactor Context: use `ReactiveSecurityContextHolder`.
- HTTP authorization and reactive method security protect different layers; use both where appropriate.
- CSRF and CORS serve different purposes and do not replace each other.
- `permitAll()` does not disable security filters, while `denyAll()` helps enforce default protection.
- HTTP Basic and browser cookies can be subject to CSRF; disable only according to a verified threat model.
- For Bearer JWT, prefer OAuth2 Resource Server and validate token issuer/audience/scopes properly.
- `SecurityWebFiltersOrder` allows inserting filters at exact positions, but you should not hand-roll authentication when the framework already provides it.
- Test 200/401/403, CSRF, chain order, method security, fallback, and credentials with `WebTestClient`.

**Quick verification rule:** **Which chain does the request match? How does that chain authenticate? Which authorization rule decides access? Does the service also enforce domain/method security?** Answering all four questions helps keep Spring Security configuration for WebFlux accurate and secure.

## 25. Official Documentation

- Spring Security — WebFlux Security and multiple chains: https://docs.spring.io/spring-security/reference/6.3/reactive/configuration/webflux.html
- Spring Boot 3.3 — WebFlux Security auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/6.3/reactive/authorization/method.html
- Spring Security — Reactive OAuth2 Resource Server/JWT: https://docs.spring.io/spring-security/reference/6.3/reactive/oauth2/resource-server/jwt.html
- Spring Security — Reactive CSRF: https://docs.spring.io/spring-security/reference/6.3/reactive/exploits/csrf.html
- Spring Security — Reactive Web Security Test: https://docs.spring.io/spring-security/reference/6.3/reactive/test/web/
- Spring Security — `ServerHttpSecurity` API: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/config/web/server/ServerHttpSecurity.html
- Spring Security — `AuthenticationWebFilter` API: https://docs.spring.io/spring-security/site/docs/6.3.4/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html
- Spring Framework — WebFlux and WebFilter infrastructure: https://docs.spring.io/spring-framework/reference/6.1/web/webflux/reactive-spring.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/6.1/testing/webtestclient.html