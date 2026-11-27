# AuthenticationWebFilter and the Reactive Authentication Chain

In a **Spring Security OAuth 2.0 / OIDC Resource Server** running on **Spring WebFlux**, Bearer access token authentication does not follow the Servlet `Filter` chain as in Spring MVC. Instead, Spring Security uses a **reactive `WebFilter` chain** built from `SecurityWebFilterChain`. A central component in this chain is **`AuthenticationWebFilter`**: it extracts credentials from `ServerWebExchange`, invokes **`ReactiveAuthenticationManager`**, handles success or failure, and places the authenticated identity into the **Reactor Context** so authorization and business logic can access it within the same reactive flow.

Understanding `AuthenticationWebFilter` accurately answers frequently asked questions:

- Why can configuring `oauth2ResourceServer().jwt()` or `opaqueToken()` authenticate tokens without writing a manual filter?
- At which step is the Bearer token extracted from the request?
- Which manager does `AuthenticationWebFilter` invoke to validate a JWT or opaque token?
- How do `Authentication` and authorities reach `@PreAuthorize`, `ReactiveSecurityContextHolder`, and reactive services?
- Why can using Servlet-style `SecurityContextHolder.getContext()` or calling `block()` on the event loop cause failures?
- When a token is missing, invalid, or lacks sufficient scope, what returns 401/403?
- When a custom converter or custom authentication is needed, where should you customize it to **avoid duplicating filters** and avoid bypassing token verification?

This lesson focuses on the **WebFlux architecture**, i.e., Spring Security's non-blocking processing flow on WebFlux, which is distinct from Servlet's **`SecurityFilterChain` and `BearerTokenAuthenticationFilter`** configuration.

> **Example context:** The Authorization Server issues a JWT access token with `iss=https://login.example.com`, `aud=orders-api`, and `scope=orders.read`. The Orders API runs on Spring Boot 3.x / Spring Security 6.x and Spring WebFlux, receiving `Authorization: Bearer <access-token>`. Domain names, tokens, and identifiers are illustrative examples.

## 1. Comparing Servlet and WebFlux Architectures

Spring Security supports two separate web models. They share `Authentication`, `GrantedAuthority`, `SecurityContext`, and OAuth2 concepts, but **filter APIs, context propagation mechanisms, and return types differ**.

| Component / Concept | Servlet / Spring MVC | Reactive / Spring WebFlux |
|---|---|---|
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Configuration object | `HttpSecurity` | `ServerHttpSecurity` |
| Request interception mechanism | Servlet `Filter` | Reactive `WebFilter` |
| Primary Bearer filter | `BearerTokenAuthenticationFilter` | `AuthenticationWebFilter` configured for Resource Server |
| HTTP representation | `HttpServletRequest` | `ServerWebExchange` |
| Bearer token extraction | `BearerTokenResolver` | `ServerAuthenticationConverter`, typically `ServerBearerTokenAuthenticationConverter` |
| Authentication | `AuthenticationManager` | `ReactiveAuthenticationManager` |
| JWT decoder | `JwtDecoder` | `ReactiveJwtDecoder` |
| Opaque introspection | `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| Storing identity during processing | `SecurityContextHolder`, typically ThreadLocal-based | `ReactiveSecurityContextHolder` based on Reactor Context |
| Return value from authentication | `Authentication` | `Mono<Authentication>` |
| Authorization chain | `AuthorizationFilter` / method interceptor | Reactive authorization web filter / reactive method security |
| HTTP error responses | Servlet entry point / denied handler | `ServerAuthenticationEntryPoint` / `ServerAccessDeniedHandler` |

**Do not copy Servlet `HttpSecurity` snippets verbatim into WebFlux.** For example, `SecurityFilterChain`, `JwtDecoder`, and `BearerTokenAuthenticationFilter` are not the appropriate components for configuring a reactive flow.

### 1.1. What Does “Reactive” Mean Here?

Spring WebFlux uses Reactor with two common types:

- `Mono<T>`: asynchronous, emitting **0 or 1** value or an error signal.
- `Flux<T>`: asynchronous, emitting **0 to many** values or an error signal.

A `ReactiveAuthenticationManager` does not return `Authentication` immediately; instead it returns:

```java
Mono<Authentication> authenticate(Authentication authentication);
```

The result is only processed when the reactive publisher is **subscribed** as part of handling the request. Authentication, authorization, and controller execution are composed into a **reactive pipeline**, rather than a sequence of synchronous calls blocking on the request thread.

However, **an API returning `Mono` does not automatically make the underlying code non-blocking**. If you invoke blocking JDBC databases or blocking `RestTemplate` directly on the event loop, the system can still stall even though the method signature is `Mono<...>`.

## 2. Overview of the WebFlux Security Chain

In WebFlux, Spring Security registers `WebFilterChainProxy` with `SecurityWebFilterChain` beans. Each chain contains WebFilters in the appropriate order. Processing layers include:

1. Restoring/persisting the security context from a repository if configured.
2. Converting the request credential into an authentication request.
3. Invoking the authentication manager to verify the credential.
4. Recording successful authentication in the reactive chain's context.
5. Translating authentication/authorization exceptions.
6. Evaluating `authorizeExchange` rules.
7. Dispatching the request to the handler/controller if permitted.

### 2.1. A Typical Bearer JWT Flow

```mermaid
sequenceDiagram
    autonumber
    participant Client as OAuth Client
    participant Proxy as WebFilterChainProxy
    participant Filter as AuthenticationWebFilter
    participant Converter as ServerBearerTokenAuthenticationConverter
    participant Manager as JwtReactiveAuthenticationManager
    participant Decoder as ReactiveJwtDecoder
    participant Context as Reactor Security Context
    participant Authz as Authorization WebFilter
    participant Handler as WebFlux Handler
    Client->>Proxy: GET /api/orders/42 + Authorization: Bearer JWT
    Proxy->>Filter: Pass ServerWebExchange
    Filter->>Converter: convert(exchange)
    Converter-->>Filter: Mono<BearerTokenAuthenticationToken>
    Filter->>Manager: authenticate(authenticationRequest)
    Manager->>Decoder: decode(raw JWT)
    Decoder->>Decoder: Verify signature, issuer, exp, and validators
    Decoder-->>Manager: Mono<Jwt>
    Manager-->>Filter: Mono<Authentication> (JwtAuthenticationToken)
    Filter->>Context: Put SecurityContext into Reactor Context
    Filter->>Authz: Continue reactive chain
    Authz->>Authz: Check SCOPE_orders.read
    Authz->>Handler: Allow handler invocation
    Handler-->>Client: Authorized response
```

In the opaque token case, the `JwtReactiveAuthenticationManager / ReactiveJwtDecoder` block is replaced by the reactive manager and introspector for opaque tokens; the remaining steps follow the same Bearer model.

### 2.2. Failure Flow

```mermaid
flowchart TD
    A["ServerWebExchange"] --> B["ServerAuthenticationConverter"]
    B --> C{"Usable credential present?"}
    C -->|None| D["Mono.empty() / continue chain"]
    D --> E{"Does endpoint require authentication?"}
    E -->|Yes| F["401 Bearer challenge"]
    E -->|No| G["Public endpoint"]
    C -->|Malformed credential| H["Authentication error"]
    H --> F
    C -->|Credential present| I["ReactiveAuthenticationManager"]
    I --> J{"Token verification succeeded?"}
    J -->|No| F
    J -->|Yes| K["Reactive SecurityContext"]
    K --> L{"Required authority present?"}
    L -->|No| M["403 Forbidden"]
    L -->|Yes| N["Service checks tenant/owner/state"]
    N --> O{"Permitted on resource?"}
    O -->|No| P["403 / 404 per policy"]
    O -->|Yes| Q["Process request"]
```

**Important distinction:** the absence of a credential is typically represented by `Mono.empty()` from the converter. That **does not mean a protected API becomes public**: if the endpoint requires an authenticated user, authorization/exception handling will return 401.

## 3. What Work Does AuthenticationWebFilter Perform?

`AuthenticationWebFilter` is a **general-purpose WebFilter for authentication**. It is not exclusive to JWT; other WebFlux mechanisms can use it with different converters and managers.

Conceptual processing flow:

```text
AuthenticationWebFilter.filter(exchange, chain)
   |
   +-- requiresAuthenticationMatcher.matches(exchange)?
   |       |
   |       +-- false -> chain.filter(exchange)
   |
   +-- ServerAuthenticationConverter.convert(exchange)
   |       |
   |       +-- Mono.empty() -> chain.filter(exchange)
   |       +-- Mono.error(...) -> authentication failure
   |       +-- Mono<Authentication request>
   |
   +-- ReactiveAuthenticationManager.authenticate(request)
   |       |
   |       +-- Mono<Authentication success> -> success handler
   |       +-- Mono.error(AuthenticationException) -> failure handler
   |       +-- Mono.empty() -> no matching authentication outcome
   |
   +-- Store/propagate SecurityContext downstream
   |
   +-- chain.filter(exchange) under the appropriate Reactor Context
```

This is a logical-level architectural description; exact steps and success/error implementations depend on the Spring Security version and the attached `ServerAuthenticationSuccessHandler`, `ServerAuthenticationFailureHandler`, and `ServerSecurityContextRepository`.

### 3.1. `requiresAuthenticationMatcher`

This matcher determines **when the filter should attempt authentication**. In a Resource Server, the Spring DSL attaches the filter to the appropriate chain/path. If creating a filter manually, you can set a matcher to avoid attempting authentication on unrelated routes.

Example:

```java
authenticationWebFilter.setRequiresAuthenticationMatcher(
    ServerWebExchangeMatchers.pathMatchers("/api/**")
);
```

This is an option **internal to the filter**. It does not replace `securityMatcher(...)` on the overall `SecurityWebFilterChain`. If the chain itself is not selected, filters inside that chain do not run even if their internal matcher matches.

### 3.2. `ServerAuthenticationConverter`

The converter reads `ServerWebExchange` and creates an authentication request:

```java
public interface ServerAuthenticationConverter {
    Mono<Authentication> convert(ServerWebExchange exchange);
}
```

For a Bearer Resource Server, the standard converter is `ServerBearerTokenAuthenticationConverter`. It reads the Bearer credential according to configured rules and produces an **unauthenticated** `BearerTokenAuthenticationToken`.

Do not confuse this converter with `JwtAuthenticationConverter`:

- **`ServerBearerTokenAuthenticationConverter`:** HTTP request → raw Bearer authentication request.
- **JWT authentication converter:** verified `Jwt` from the decoder → principal/authorities in `Authentication`.

These two converters operate at **two different layers**. The first neither parses nor verifies JWT signatures. The second does not extract tokens directly from HTTP headers.

### 3.3. `ReactiveAuthenticationManager`

The manager receives an unverified authentication request and emits either a valid authentication or an error:

```java
Mono<Authentication> authenticate(Authentication authentication);
```

In a Resource Server:

- JWT: `JwtReactiveAuthenticationManager` coordinates with `ReactiveJwtDecoder`.
- Opaque token: the reactive manager for opaque tokens coordinates with `ReactiveOpaqueTokenIntrospector`.

A manager **must never** simply set `authenticated=true` for any arbitrary Bearer string. It must rely on trusted decoding/verification or introspection results, validate contract conditions, and construct principal/authorities according to policy.

### 3.4. Success Handler and Failure Handler

When authentication succeeds, `AuthenticationWebFilter` uses success handling to place the security context into the pipeline and continue the chain. When an `AuthenticationException` occurs, failure handling sends the appropriate 401/challenge response.

Related interfaces:

- `ServerAuthenticationSuccessHandler`.
- `ServerAuthenticationFailureHandler`.
- `ServerSecurityContextRepository`.
- `ServerAuthenticationEntryPoint`.
- `ServerAccessDeniedHandler`.

When customizing them, preserve Bearer challenge semantics, avoid inadvertently redirecting to an HTML login page, avoid unintentionally storing tokens in sessions, and never allow the request to proceed when authentication fails.

## 4. How Is the Bearer Token Extracted from the HTTP Request?

Typical request:

```http
GET /api/orders/42 HTTP/1.1
Host: api.example.com
Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
```

`ServerBearerTokenAuthenticationConverter` processes the credential string according to the Bearer contract. The result is an authentication request containing the raw token value.

**Do not treat a client-sent Bearer token as already-trusted data.** A request might supply a token with an invalid signature, an expired token, a token issued by a different issuer, or even a random string.

### 4.1. Tokens in the Query String Are a Dangerous Choice

Passing tokens via:

```text
GET /api/orders?access_token=...
```

can leak tokens through URLs, proxy logs, browser history, monitoring, referer headers, or caches. Converters typically prefer the `Authorization: Bearer` mechanism and should not enable query-parameter token extraction unless under a carefully evaluated exception.

Do not “fix a mobile client that omits the header” by accepting tokens from arbitrary query parameters or request bodies. Standardize clients to use the Bearer header.

### 4.2. Converters Must Not Create Authorities from Arbitrary Headers

Headers such as:

```http
X-User: admin
X-Roles: ORDER_MANAGER
X-Tenant: tenant-a
```

are not trusted authentication sources simply because they are present. If a converter builds principals or authorities from caller-controlled headers, it bypasses token verification and introduces privilege escalation risks.

If a gateway sends identity headers, there must be dedicated gateway-to-service authentication and an explicit trust boundary—never apply that pattern by default to a public Resource Server.

## 5. Basic WebFlux JWT Resource Server Configuration

### 5.1. Dependencies

Gradle Groovy DSL example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
```

This is the **WebFlux stack**; do not include `spring-boot-starter-web` in the example because the MVC starter can alter the web application type Boot selects when both frameworks are present.

### 5.2. Configuring Issuer and Audience

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
```

Explanation:

- `issuer-uri` selects the issuer trusted by the Resource Server.
- Auto-configuration can use the issuer's metadata/JWKS to create a `ReactiveJwtDecoder`.
- `audiences` is a property supported on corresponding Spring Boot versions; if using another version or a custom decoder, configure an explicit audience validator.
- The JWT decoder verifies the token against configured validators (signature, expiration, issuer, audience, and other checks).
- Signature and claim verification is a prerequisite before the converter constructs the authentication object.

An access JWT intended for a Billing API with `aud=billing-api` must not be accepted by the Orders API merely because a scope happens to be named `orders.read`.

### 5.3. Creating a SecurityWebFilterChain

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOrdersSecurity {

    @Bean
    SecurityWebFilterChain ordersApiChain(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api", "/api/**")
            )
            .authorizeExchange(auth -> auth
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults())
            )
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new BearerTokenServerAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new BearerTokenServerAccessDeniedHandler()
                )
            )
            .build();
    }
}
```

**Important note on CSRF:** `csrf(...disable)` in this example applies only to an **API that accepts Bearer headers and does not rely on session cookies sent automatically by browsers**. If the API also accepts cookies or another browser login model, design CSRF protection accordingly rather than disabling it application-wide.

**Important note on URLs:** `securityMatcher("/api", "/api/**")` selects this chain for those URLs. Other paths must be protected by appropriate chains or a fallback. A `SecurityWebFilterChain` with a narrow matcher does not protect the entire application.

### 5.4. Where Does AuthenticationWebFilter Appear?

You do not see a statement like:

```java
new AuthenticationWebFilter(...)
```

in the configuration above because Spring Security **creates and wires the Bearer authentication components** when the `oauth2ResourceServer(...jwt(...))` DSL is enabled. Under the Resource Server architecture, the authentication filter is configured with a converter that extracts Bearer tokens and a manager that verifies JWTs.

This is the preferred approach when using standard JWT or opaque tokens: **configure via the DSL** and only customize the manager, converter, or decoder where genuinely needed. Manually registering an extra `AuthenticationWebFilter` in the same chain can cause duplicate authentication, conflicting handlers, or incorrect execution ordering.

### 5.5. What Does Stateless Configuration Mean?

`NoOpServerSecurityContextRepository` indicates that the SecurityContext is neither saved to nor read from a session repository under that configuration. In a Bearer API, callers typically send the access token **on every request**.

Even when stateless, the current request still has an `Authentication` in the **Reactor Context** after successful authentication. “Not storing a session” does not mean “no SecurityContext”.

## 6. How Does a JWT Flow Through ReactiveJwtDecoder and the Manager?

Example signed JWT payload:

```json
{
  "iss": "https://login.example.com",
  "sub": "customer-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-a",
  "exp": 2000000000
}
```

Processing flow:

```text
ServerBearerTokenAuthenticationConverter
    → BearerTokenAuthenticationToken(raw JWT)
    → JwtReactiveAuthenticationManager
    → ReactiveJwtDecoder.decode(raw JWT)
    → Verified Jwt or AuthenticationException
    → Converter from Jwt to Authentication
    → JwtAuthenticationToken with authorities
    → Reactor SecurityContext
```

### 6.1. Decoding the Payload Is Different from Verifying the Token

A JWT can be Base64URL-decoded by any client, but that **does not prove** the token was issued by a trusted issuer.

`ReactiveJwtDecoder` must verify the signature and mandatory constraints such as expiration, issuer, and audience. If a token's `scope` is tampered with and its signature no longer matches, the decoder rejects it before authorities are created.

**Never call `Jwt.withTokenValue(...)` with a client-supplied string and mark authenticated=true in production.** That builder API can be useful in tests, but it does not replace verification.

### 6.2. Authentication Result

With a typical JWT converter:

```text
Principal object:
  Jwt

Authentication type:
  JwtAuthenticationToken

Authentication name:
  sub (default)

Granted authorities:
  SCOPE_orders.read
  SCOPE_orders.write
```

Scopes from `scope` or `scp` are typically mapped into authorities with the `SCOPE_` prefix. `Authentication.getName()` defaults to `sub`; it does not default to an email, `UserDetails`, or a database customer entity.

### 6.3. A Valid Token Does Not Grant Access to Every Order

A JWT with `SCOPE_orders.read` only permits the agreed-upon operation category. Services must still check:

- Which tenant does the order belong to?
- Does the subject own or have delegated access to it?
- Does the endpoint accept client credentials or only user-delegated tokens?
- Is the order in a state that permits the operation?
- Are role/tenant memberships still valid according to the contract?

**AuthenticationWebFilter validates credentials; it does not replace object-level authorization.**

## 7. Customizing Authorities and Principal Name in WebFlux

Spring Security allows customizing the converter from a verified `Jwt` to an authentication token.

Suppose the Authorization Server issues:

```json
{
  "sub": "customer-42",
  "preferred_username": "lan.nguyen",
  "permissions": ["orders.read", "orders.export"],
  "scope": "orders.read"
}
```

If `permissions` is a trusted business-permission claim by contract, you can build a compatible JWT converter and wrap it with **`ReactiveJwtAuthenticationConverterAdapter`**.

### 7.1. Adapting JwtAuthenticationConverter to Reactive

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;
import reactor.core.publisher.Mono;

@Configuration
public class JwtAuthoritiesConfiguration {

    @Bean
    Converter<Jwt, Mono<AbstractAuthenticationToken>> jwtToAuthentication() {
        JwtGrantedAuthoritiesConverter permissions =
            new JwtGrantedAuthoritiesConverter();

        permissions.setAuthoritiesClaimName("permissions");
        permissions.setAuthorityPrefix("PERMISSION_");

        JwtAuthenticationConverter blockingStyleConverter =
            new JwtAuthenticationConverter();

        // Only change getName() when the contract guarantees the appropriate claim.
        // If a stable identity is needed, keep sub instead of username/email.
        blockingStyleConverter.setPrincipalClaimName("sub");
        blockingStyleConverter.setJwtGrantedAuthoritiesConverter(
            permissions
        );

        return new ReactiveJwtAuthenticationConverterAdapter(
            blockingStyleConverter
        );
    }
}
```

Configuring the Resource Server to use the converter bean:

```java
@Bean
SecurityWebFilterChain customJwtChain(
        ServerHttpSecurity http,
        Converter<Jwt, Mono<AbstractAuthenticationToken>>
            jwtToAuthentication) {

    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        )
        .authorizeExchange(auth -> auth
            .pathMatchers("/api/export/**")
                .hasAuthority("PERMISSION_orders.export")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtToAuthentication)
            )
        )
        .build();
}
```

These two configuration snippets are an **alternative variant** to the earlier `ordersApiChain` configuration, not a recommendation to register two chains with overlapping matchers without control.

### 7.2. Be Careful When Replacing the Authorities Converter

When you call `setJwtGrantedAuthoritiesConverter(permissions)`, the default converter reading `scope/scp` **is replaced** by the converter reading `permissions`. Consequently, `SCOPE_orders.read` will no longer appear automatically unless you merge them.

If the API needs both scopes and permissions:

1. Keep a dedicated scope converter to read `scope/scp` into `SCOPE_*`.
2. Build a custom converter that merges scope results and approved permission claims.
3. Use `GrantedAuthority` names with distinct namespaces, such as `SCOPE_*` and `PERMISSION_*`.
4. Never grant authorities from arbitrary role/permission strings outside an allowlist.
5. Only consume claims guaranteed by the issuer/audience contract, never inferred from self-asserted user data.

### 7.3. Does the “Reactive” Adapter Make Every Converter Non-Blocking?

**No.** `ReactiveJwtAuthenticationConverterAdapter` can wrap a synchronous converter returning an authentication into a `Mono`; it **does not transform** blocking JDBC or blocking HTTP calls inside that converter into non-blocking I/O.

If permissions must be loaded from a database during authentication:

- Evaluate whether dynamic permissions belong in authentication or should be checked in service/method security.
- If reactive I/O is needed, use a natively reactive converter contract instead of calling `block()`.
- Pay attention to timeouts, data ownership, caching, and permission revocation.
- Do not spawn a nested `subscribe()` to “wait later”; Spring Security must receive a completed `Mono<Authentication>` to populate the SecurityContext.

## 8. Reactive Opaque Tokens Also Use AuthenticationWebFilter

When the Authorization Server issues opaque tokens, the API can use introspection:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: ${ORDERS_INTROSPECTION_CLIENT_ID}
          client-secret: ${ORDERS_INTROSPECTION_CLIENT_SECRET}
```

Reactive DSL:

```java
.oauth2ResourceServer(oauth2 ->
    oauth2.opaqueToken(Customizer.withDefaults())
)
```

General flow:

```text
ServerBearerTokenAuthenticationConverter
    → BearerTokenAuthenticationToken
    → Reactive authentication manager for opaque token
    → ReactiveOpaqueTokenIntrospector.introspect(token)
    → HTTPS POST to Authorization Server
    → active=true + attributes or error
    → BearerTokenAuthentication
    → Reactor SecurityContext
```

**Key differences from JWT:**

| Aspect | JWT | Opaque |
|---|---|---|
| Verification mechanism | `ReactiveJwtDecoder` verifies signature/claims | `ReactiveOpaqueTokenIntrospector` queries AS |
| Information received | Verified `Jwt` | `OAuth2AuthenticatedPrincipal`/attributes from introspection |
| Typical Authentication | `JwtAuthenticationToken` | `BearerTokenAuthentication` |
| Network dependency | May fetch/discover JWKS, then verify locally | Typically calls AS for introspection per policy |
| Revocation effect | Requires dedicated design if only verifying JWT offline | Can reflect upon re-introspection, depending on AS/cache |
| Identity propagation in reactive pipeline | Reactor SecurityContext | Reactor SecurityContext |

Opaque tokens do not make WebFlux “less reactive”. If a custom introspector calls blocking `RestTemplate` directly on the event loop, it introduces stalling risks. Use `ReactiveOpaqueTokenIntrospector` and an appropriate reactive HTTP client.

### 8.1. Introspection Must Still Fail Closed

If the AS returns `active=false`, client credentials fail, TLS fails, or the endpoint times out, never construct an authenticated principal for an unverified token.

An `active=true` token also does not prove authorization for all resources: scope, audience/resource contract, tenant, and ownership must still be checked.

## 9. When Should You Manually Create an AuthenticationWebFilter?

**Usually not necessary** for a Resource Server using standard JWT or opaque tokens. `ServerHttpSecurity.oauth2ResourceServer(...)` already configures the Bearer authentication path.

Manually creating `AuthenticationWebFilter` is useful when you have **a custom authentication mechanism**, for example:

- An internal API endpoint using organization-defined credentials rather than OAuth Bearer tokens.
- A multi-tenant/multi-issuer design with specialized authentication management requiring controlled custom routing.
- A dedicated chain requiring an authentication converter/manager that cannot be safely expressed through the standard DSL.
- A vetted protocol-specific security layer.

However, never use a custom filter to manually parse JWT payloads and grant authorities while bypassing `ReactiveJwtDecoder`.

### 9.1. Manual JWT Filter Configuration Example — Understanding the Structure

The example below illustrates the wiring points. It is **an alternative to the Resource Server DSL**, and must not be placed alongside `oauth2ResourceServer().jwt()` on the same chain without a very specific design to prevent two Bearer filters from attempting authentication simultaneously.

```java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.config.web.server.SecurityWebFiltersOrder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.web.server.ServerBearerTokenAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAuthenticationEntryPoint;
import org.springframework.security.oauth2.server.resource.web.server.BearerTokenServerAccessDeniedHandler;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.authentication.AuthenticationWebFilter;
import org.springframework.security.web.server.authentication.ServerAuthenticationEntryPointFailureHandler;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;

@Configuration
public class ManualBearerFilterConfiguration {

    @Bean
    SecurityWebFilterChain manualApiChain(
            ServerHttpSecurity http,
            ReactiveJwtDecoder decoder) {

        var manager = new JwtReactiveAuthenticationManager(decoder);

        AuthenticationWebFilter bearerFilter =
            new AuthenticationWebFilter(manager);

        bearerFilter.setServerAuthenticationConverter(
            new ServerBearerTokenAuthenticationConverter()
        );

        bearerFilter.setRequiresAuthenticationMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        );

        bearerFilter.setSecurityContextRepository(
            NoOpServerSecurityContextRepository.getInstance()
        );

        bearerFilter.setAuthenticationFailureHandler(
            new ServerAuthenticationEntryPointFailureHandler(
                new BearerTokenServerAuthenticationEntryPoint()
            )
        );

        return http
            .securityMatcher(
                ServerWebExchangeMatchers.pathMatchers("/api/**")
            )
            .authorizeExchange(auth -> auth
                .anyExchange().authenticated()
            )
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .formLogin(form -> form.disable())
            .httpBasic(basic -> basic.disable())
            .csrf(csrf -> csrf.disable())
            .exceptionHandling(ex -> ex
                .authenticationEntryPoint(
                    new BearerTokenServerAuthenticationEntryPoint()
                )
                .accessDeniedHandler(
                    new BearerTokenServerAccessDeniedHandler()
                )
            )
            .addFilterAt(
                bearerFilter,
                SecurityWebFiltersOrder.AUTHENTICATION
            )
            .build();
    }
}
```

**Technical caveat:** the example demonstrates how to wire common WebFlux/Spring Security 6.x APIs, but you must adapt it to your exact version, matchers, error handling, token validators, and other chains when applying it. In production, **the `oauth2ResourceServer().jwt()` DSL is the preferred configuration path** because it includes Spring Security's official integrations and handlers.

### 9.2. Explaining Each Node in the Example

- `ReactiveJwtDecoder` remains the JWT **verifier**; never skip signature, issuer, audience, or timestamp checks.
- `JwtReactiveAuthenticationManager` turns a Bearer authentication request into `Mono<Authentication>` via the decoder and converter.
- `ServerBearerTokenAuthenticationConverter` extracts the Bearer credential from `ServerWebExchange`.
- `AuthenticationWebFilter` coordinates the converter, manager, and success/failure handling.
- `NoOpServerSecurityContextRepository` avoids storing authentication in a web session.
- `ServerAuthenticationEntryPointFailureHandler` routes authentication failures to the Bearer entry point.
- `SecurityWebFiltersOrder.AUTHENTICATION` determines the custom filter's position in the reactive filter chain.
- `authorizeExchange(...authenticated())` is still required so requests **without a token** are not permitted into protected handlers.

If a filter is placed in the wrong order relative to authorization or exception translation, 401/403 outcomes may behave unexpectedly. Do not infer execution order from the order of Java DSL method calls; use `SecurityWebFiltersOrder` and official configuration.

## 10. AuthenticationWebFilter and ReactiveAuthenticationManagerResolver

Some systems accept tokens from **multiple issuers**, environments, or tenants with separate contracts. In such cases, the authentication manager may need to be selected based on trusted request context.

Spring Security provides a resolver mechanism for reactive authentication managers in `AuthenticationWebFilter`, allowing manager selection while processing an exchange.

Model:

```text
ServerWebExchange
    |
    v
Resolver selects appropriate ReactiveAuthenticationManager
    |
    +--> Manager for trusted issuer A
    +--> Manager for trusted issuer B
    |
    v
Manager verifies token against exact issuer/keys/audience
```

**Warning:** unverified information from a JWT payload is **not trustworthy proof of the issuer**. It may be used as a *hint* to select a manager from a **fixed allowlist**, but the selected manager must still genuinely verify the signature, issuer, audience, and token profile.

Never take a client-sent `iss` claim or HTTP header and dynamically construct an HTTP client to fetch JWKS or introspection URLs from it. Doing so risks SSRF, token leakage, or issuer confusion.

### 10.1. Two Common Design Mistakes

**Mistake 1 — A single default manager shared system-wide without checking issuer/audience.** Valid tokens for another API may be accepted due to overly broad key/trust configuration.

**Mistake 2 — The resolver instantiates a new manager and fetches JWKS from a token-declared URL on every request.** This eliminates the allowlist, causes network/resource exhaustion, and risks connecting to attacker-specified hosts.

For multi-issuer setups, manage **trust configuration per allowed issuer**, cache decoders/keys appropriately, and verify each Resource Server's audience.

## 11. Reactor Context: Where Is SecurityContext Carried?

One of the biggest differences from Servlet is how **SecurityContext** is stored.

### 11.1. Servlet: ThreadLocal Along Typical Processing Paths

In synchronous Spring MVC, code often reads:

```java
Authentication authentication =
    SecurityContextHolder.getContext().getAuthentication();
```

Under typical Servlet configurations, the context is bound to the thread handling the request. This model **must not be applied directly** to WebFlux.

### 11.2. WebFlux: Reactor Context

In a reactive flow:

```java
Mono<SecurityContext> contextMono =
    ReactiveSecurityContextHolder.getContext();
```

`ReactiveSecurityContextHolder` relies on **Reactor Context**, attached to the subscriber/pipeline. Because a pipeline can switch threads across schedulers, binding identity to a “fixed” ThreadLocal is unreliable.

```text
Reactive HTTP request
    |
    +--> AuthenticationWebFilter creates Authentication
    |
    +--> SecurityContext is attached to Reactor Context
    |
    +--> Authorization WebFilter
    |
    +--> Controller returns Mono/Flux
    |
    +--> Service, reactive repository
           |
           +--> Same subscription/context: identity is readable
```

Reactor operators such as `flatMap`, `publishOn`, and `subscribeOn` propagate Reactor Context along properly chained pipelines; however, **manual subscribe**, out-of-pipeline callbacks, or library integrations that do not honor context propagation can lose identity.

### 11.3. Reading Authentication in a Reactive Service

```java
package com.example.orders.security;

import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

import reactor.core.publisher.Mono;

public final class ReactiveCaller {

    public static Mono<Authentication> currentAuthentication() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .filter(Authentication::isAuthenticated)
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "Authentication required"
                )
            ));
    }

    private ReactiveCaller() {
    }
}
```

This is an illustrative helper; it is unnecessary if controllers/services already obtain Authentication appropriately. `isAuthenticated()` alone does not guarantee the right **principal type** or resource permissions: services must still verify scope, issuer, audience, tenant, and ownership.

### 11.4. Do Not Forge Authentication to Bypass Policy

Do not do this:

```java
// Intentionally unsafe example: forging admin privileges.
Mono<Result> unsafe = performOperation()
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
            forgedAdminAuthentication
        )
    );
```

The fact that `contextWrite` can attach an Authentication **does not make that Authentication trustworthy**. Only a trust boundary that genuinely validates credentials or a properly governed workload identity may construct contexts used for authorization.

In **unit tests**, creating a test Authentication is normal; in production, forging a user/admin identity to “fix a missing context” is an anti-pattern.

## 12. Do Not Block or Manually Subscribe Inside the Authentication Pipeline

### 12.1. `block()` on the Event Loop

Bad example:

```java
public String currentUserBlocking() {
    return ReactiveSecurityContextHolder.getContext()
        .map(context -> context.getAuthentication().getName())
        .block(); // Do not use in WebFlux request processing
}
```

Problems:

- `block()` stalls the thread, defeating WebFlux's non-blocking goal.
- Reactor may warn or throw when blocking on a non-blocking thread.
- Subscribing independently to block can cause Reactor Context to diverge from the request pipeline.
- Under high load, blocking starves the event loop and increases system-wide latency.

Better:

```java
public Mono<String> currentUser() {
    return ReactiveSecurityContextHolder.getContext()
        .map(ctx -> ctx.getAuthentication().getName());
}
```

Then compose using `flatMap`, `map`, or other reactive service methods.

### 12.2. Calling `subscribe()` Manually in a Controller/Service

Undesirable example:

```java
public Mono<Void> cancelOrder(String orderId) {
    checkAuthorizationReactive()
        .subscribe(); // Runs separately, does not block mutation below

    return repository.cancel(orderId);
}
```

The check and the mutation are no longer in an ordered pipeline, which can detach context and allow the mutation to run before authorization is confirmed.

Better:

```java
public Mono<Void> cancelOrder(String orderId) {
    return checkAuthorizationReactive()
        .then(repository.cancel(orderId));
}
```

`checkAuthorizationReactive()` must emit an error or an appropriate signal when unauthorized, and must never emit `Mono.empty()` as an unintended “allow” signal before policy verification.

### 12.3. When Integrating Blocking Libraries

Some applications must call legacy blocking JDBC/SDKs. When unavoidable, offload from the event loop using an appropriate scheduler and bound concurrency:

```java
Mono<LegacyResult> result = Mono
    .fromCallable(() -> legacyBlockingClient.call())
    .subscribeOn(Schedulers.boundedElastic());
```

This is an adaptation measure, not true non-blocking I/O. Manage thread pools, timeouts, and authentication context boundaries; prefer R2DBC, `WebClient`, or reactive clients whenever possible.

Never use scheduler thread switching as an excuse to skip security checks or manually pass tokens via ThreadLocal.

## 13. Reactive Service Example: Sufficient Scope Still Requires Checking the Order Owner

Suppose the request has authenticated a JWT and requests:

```http
GET /api/orders/order-9001 HTTP/1.1
Authorization: Bearer <valid-jwt>
```

The token has `scope=orders.read` and subject `customer-42`. The service must check that the order belongs to the right tenant and owner before returning it.

### 13.1. Domain Model and Reactive Repository

```java
package com.example.orders.domain;

public record Order(
    String id,
    String tenantId,
    String ownerIssuer,
    String ownerSubject,
    String status
) {}
```

```java
package com.example.orders.domain;

import reactor.core.publisher.Mono;

public interface ReactiveOrderRepository {
    Mono<Order> findByIdAndTenantId(String id, String tenantId);
}
```

The repository adapter must **actually enforce the tenant constraint in the query**; an interface method name does not enforce policy if the implementation omits that predicate.

### 13.2. Policy for Subject and Object

```java
package com.example.orders.security;

import com.example.orders.domain.Order;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Component;

@Component
public final class ReactiveOrderPolicy {

    public boolean canRead(Jwt jwt, Order order) {
        if (jwt == null || order == null
                || jwt.getIssuer() == null
                || jwt.getSubject() == null) {
            return false;
        }

        String tenant = jwt.getClaimAsString("tenant_id");
        if (tenant == null || tenant.isBlank()) {
            return false;
        }

        return tenant.equals(order.tenantId())
            && jwt.getIssuer().toString().equals(order.ownerIssuer())
            && jwt.getSubject().equals(order.ownerSubject());
    }
}
```

This is an **illustrative policy for user-delegated tokens**. With `client_credentials`, the subject may represent a service rather than a customer; a separate client/job policy is required. The `tenant_id` claim is trustworthy only when issued by a trusted issuer under contract.

### 13.3. Service Reading Reactor Context and Checking Permissions

```java
package com.example.orders.application;

import com.example.orders.domain.Order;
import com.example.orders.domain.ReactiveOrderRepository;
import com.example.orders.security.ReactiveOrderPolicy;

import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AuthenticationCredentialsNotFoundException;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationToken;
import org.springframework.stereotype.Service;

import reactor.core.publisher.Mono;

@Service
public final class ReactiveOrderQueryService {

    private final ReactiveOrderRepository repository;
    private final ReactiveOrderPolicy policy;

    public ReactiveOrderQueryService(
            ReactiveOrderRepository repository,
            ReactiveOrderPolicy policy) {
        this.repository = repository;
        this.policy = policy;
    }

    public Mono<Order> getOrder(String orderId) {
        return ReactiveSecurityContextHolder.getContext()
            .map(ctx -> ctx.getAuthentication())
            .switchIfEmpty(Mono.error(
                new AuthenticationCredentialsNotFoundException(
                    "No security context"
                )
            ))
            .flatMap(authentication ->
                readAuthorizedOrder(orderId, authentication)
            );
    }

    private Mono<Order> readAuthorizedOrder(
            String orderId,
            Authentication authentication) {

        if (!(authentication instanceof JwtAuthenticationToken jwtAuth)
                || !jwtAuth.isAuthenticated()) {
            return Mono.error(
                new AccessDeniedException("JWT principal required")
            );
        }

        boolean hasScope = jwtAuth.getAuthorities().stream()
            .anyMatch(authority ->
                "SCOPE_orders.read".equals(authority.getAuthority())
            );

        if (!hasScope) {
            return Mono.error(
                new AccessDeniedException("Missing orders.read scope")
            );
        }

        Jwt jwt = jwtAuth.getToken();
        String tenant = jwt.getClaimAsString("tenant_id");

        if (tenant == null || tenant.isBlank()) {
            return Mono.error(
                new AccessDeniedException("Missing trusted tenant")
            );
        }

        return repository.findByIdAndTenantId(orderId, tenant)
            .switchIfEmpty(Mono.error(
                new OrderNotFoundException(orderId)
            ))
            .flatMap(order -> {
                if (!policy.canRead(jwt, order)) {
                    return Mono.error(
                        new AccessDeniedException("Not allowed")
                    );
                }
                return Mono.just(order);
            });
    }
}
```

`OrderNotFoundException` is an application-specific domain exception; mapping it to HTTP 404 is decided by the error handler. When returning a DTO, return only fields the client is allowed to view rather than exposing the entire entity.

Key takeaways:

1. Authentication is obtained from **Reactor Context**, not ThreadLocal.
2. The service verifies the **correct Authentication type** and authority.
3. The tenant is read from a verified JWT per contract.
4. The repository queries within the tenant; the policy re-checks issuer/subject and tenant.
5. If scope or object policy fails, emit `Mono.error(...)` — never proceed to return data.
6. Never call `block()` or `subscribe()` inside the method.
7. Production systems also require membership/delegation checks, status validation, data minimization, and distinguishing user vs. service tokens.

### 13.4. WebFlux Controller Returning Mono

```java
package com.example.orders.api;

import com.example.orders.application.ReactiveOrderQueryService;
import com.example.orders.domain.Order;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/orders")
public final class ReactiveOrderController {

    private final ReactiveOrderQueryService service;

    public ReactiveOrderController(ReactiveOrderQueryService service) {
        this.service = service;
    }

    @GetMapping("/{orderId}")
    public Mono<Order> getOrder(@PathVariable String orderId) {
        return service.getOrder(orderId);
    }
}
```

The controller **returns the publisher** and does not subscribe itself. WebFlux manages subscription; the Spring Security context attached to the request pipeline is available to the service.

Even if the caller has `SCOPE_orders.read`, if the order belongs to another tenant or user, the service still denies access. This prevents **Broken Object Level Authorization (BOLA/IDOR)**.

## 14. Authentication via Controller Parameters or @AuthenticationPrincipal

WebFlux also supports obtaining the principal from an authenticated request. Example:

```java
@GetMapping("/api/me")
public Mono<Map<String, String>> me(
        @AuthenticationPrincipal Jwt jwt) {

    String subject = jwt.getSubject();
    String issuer = jwt.getIssuer().toString();

    return Mono.just(Map.of(
        "subject", subject,
        "issuer", issuer
    ));
}
```

Required imports include `java.util.Map`, `org.springframework.security.core.annotation.AuthenticationPrincipal`, `org.springframework.security.oauth2.jwt.Jwt`, and `reactor.core.publisher.Mono`.

**Limitation:** this example assumes the endpoint is protected and a valid JWT has `sub`/`iss`. If the application uses opaque tokens, the principal is not `Jwt` by default; use `OAuth2AuthenticatedPrincipal` or the appropriate `Authentication`.

### 14.1. Should You Pass the Principal or Read Context in the Service?

Both approaches can be appropriate:

- **Reading `ReactiveSecurityContextHolder`:** convenient when the service is invoked within an authenticated reactive chain and needs the security context.
- **Passing a verified actor context as a parameter:** clearer when the service is shared across HTTP, messaging, and jobs, provided you control who constructs that actor.
- **Using method security:** can express scope/role constraints on bean methods, though object policies are still required when accessing data.

Never take `userId` or `tenantId` directly from the path or request body and treat it as a verified identity. Parameters are **request inputs**, not proof of authority.

## 15. Reactive Method Security and Its Relationship with the Filter Chain

In WebFlux you can enable:

```java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfiguration {
}
```

Then protect reactive methods:

```java
@Service
public class ReactiveOrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> getOrder(String orderId) {
        return repository.findAuthorizedOrder(orderId);
    }
}
```

`OrderDto`/`repository.findAuthorizedOrder` belong to the application domain; the snippet only illustrates annotation placement.

Key differences:

- Web-layer `authorizeExchange` protects URLs and scopes per HTTP route.
- Reactive method security protects **Spring bean method invocations** within the reactive pipeline.
- Both require Authentication in the **Reactor Context**.
- Self-invocation within the same bean can bypass the AOP proxy; design method boundaries clearly.
- Method-level scopes **do not replace** owner/tenant/resource and business-state checks.
- Do not rely on `@PostAuthorize` as the sole protection for mutations that already caused side effects.

### 15.1. Why Is Method Security Still Needed in WebFlux?

A use case can be invoked from:

- A REST controller.
- A GraphQL resolver.
- A reactive message handler.
- Another workflow or service.
- An internal application adapter.

If `hasAuthority` is only placed on REST routes, callers not going through those routes will not automatically enforce the same constraints.

However, **message consumers or scheduled jobs do not automatically have an HTTP security context**. They need a workload identity or an actor context authenticated across a separate trust boundary; do not forge an admin `JwtAuthenticationToken` to “fix a missing context”.

### 15.2. Characteristics of Reactive Methods

When a method returns `Mono<OrderDto>` and is guarded by reactive method security, keep the actual execution inside the publisher. If a method performs side effects before returning `Mono`, authorization placement may fail to guard those out-of-pipeline side effects as intended.

Undesirable example:

```java
public Mono<Void> unsafeCancel(String id) {
    legacyRepository.cancelNow(id); // Immediate synchronous side effect
    return Mono.empty();
}
```

Use reactive repository/domain operations and pipeline-integrated policies with appropriate transaction and concurrency controls.

## 16. Exception Translation and 401/403 Responses in WebFlux

Authentication and authorization errors must be handled by **reactive** components:

- `ServerAuthenticationEntryPoint`: handles unauthenticated requests, typically HTTP 401.
- `ServerAccessDeniedHandler`: handles insufficient permissions, typically HTTP 403.
- `BearerTokenServerAuthenticationEntryPoint`: Bearer challenge.
- `BearerTokenServerAccessDeniedHandler`: Bearer insufficient-permission error.
- `ExceptionTranslationWebFilter`: handles certain security exceptions from downstream filters.
- Authentication failure handler in `AuthenticationWebFilter`: handles errors occurring during authentication.

### 16.1. 401 When Token Is Missing or Invalid

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
```

When a token is invalid, it may include:

```http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
```

Header parameters depend on the specific error and entry point configuration. Not every 401 must contain the exact same `error` attribute.

### 16.2. 403 When Token Is Valid but Lacks Permissions

```http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
```

If an owner/tenant policy denies access, the API may return 403 or 404 per business contract. Never return an HTML login page or a 302 redirect to an OIDC authorization endpoint simply because a Bearer token lacks permissions.

### 16.3. Network Errors During JWT/Opaque Verification

If `ReactiveJwtDecoder` needs to fetch JWKS and the endpoint is unavailable, or opaque introspection times out:

- Do not treat the token as automatically valid.
- Do not fall back to `permitAll()`.
- Distinguish invalid-token errors from dependency/infrastructure failures in metrics and exception mapping.
- Some configurations may return 401 or 5xx depending on the exception; if the product requires 503 for dependency outages, implement and test that mapping explicitly.
- Do not log raw access tokens or introspection credentials.

## 17. Separating Multiple SecurityWebFilterChain Beans for API and Web Login

A WebFlux application may serve both Bearer APIs and web session logins. In that case, separate chains by URL pattern and order.

### 17.1. Prioritized API Chain

```java
@Bean
@Order(1)
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        )
        .authorizeExchange(ex -> ex
            .anyExchange().authenticated()
        )
        .formLogin(form -> form.disable())
        .httpBasic(basic -> basic.disable())
        .oauth2ResourceServer(oauth2 ->
            oauth2.jwt(Customizer.withDefaults())
        )
        .build();
}
```

### 17.2. Web Chain for Interactive Login

```java
@Bean
@Order(2)
SecurityWebFilterChain webSecurity(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers(
                "/web/**", "/login", "/logout"
            )
        )
        .authorizeExchange(ex -> ex
            .pathMatchers("/web/public/**", "/login").permitAll()
            .anyExchange().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
```

The snippets above are illustrative beans inside a configuration class with the required `@Order`/`ServerHttpSecurity` imports. If the application uses real OAuth2/OIDC login, replace the web chain with `oauth2Login(...)` and ensure `/oauth2/**` and callback URLs reside in the corresponding chain.

**Note:** multiple chains with overlapping matchers require explicit `@Order` priority; WebFlux selects a single matching chain and does not apply all chains to a request. Include a fallback/deny-all chain for out-of-scope URLs if the application exposes other endpoints.

### 17.3. Never Redirect API Requests to a Login Page

For Bearer APIs:

```text
No token       -> 401 Bearer
Invalid token  -> 401 invalid_token
Missing scope  -> 403
```

For interactive web login:

```text
No session -> may redirect to /login
```

Do not use `Accept: text/html` from a browser as a signal to switch an API's authentication mechanism. Whether a URL belongs to the API or web UI must be configured by trust boundary, not merely content negotiation.

## 18. Filter Order in WebFlux: Why Does addFilterAt Matter?

Spring Security WebFlux uses the `SecurityWebFiltersOrder` enum for positions such as:

- `REACTOR_CONTEXT`.
- `AUTHENTICATION`.
- `ANONYMOUS_AUTHENTICATION`.
- `EXCEPTION_TRANSLATION`.
- `AUTHORIZATION`.

Relative filter order determines:

1. Is authentication established before authorization runs?
2. Is SecurityContext placed into the Reactor Context for handlers and services?
3. Which filter translates exceptions into HTTP responses?
4. Could a custom filter accidentally run before authentication exists or after authorization has already checked?

If you write a custom `WebFilter` to inspect the principal, it must be placed at the appropriate order and use `ReactiveSecurityContextHolder` rather than `ThreadLocal`. However, if you only need to check scopes, **use `authorizeExchange` or method security** instead of writing a new filter per endpoint.

### 18.1. Duplicating Authentication Filters

A design flaw:

```text
Chain:
  - Custom AuthenticationWebFilter reading Bearer
  - AuthenticationWebFilter created by oauth2ResourceServer().jwt()
  - AuthorizationWebFilter
```

Can lead to:

- Tokens being verified twice.
- Custom failure handlers competing with standard handlers.
- SecurityContext getting overwritten.
- JWT and opaque tokens being routed to the wrong manager.
- Hard-to-diagnose 401/403 errors.
- Wasted resources or redundant introspection calls.

Choose **one clear authentication configuration path** per credential/chain, or design multi-credential support with explicit branching and controlled ordering.

### 18.2. Do Not Use a Separate Filter to Replace OAuth Claims Validation

A custom `WebFilter` that reads the header and parses the JWT payload to determine `scope` before decoder verification is unsafe. Claims are trustworthy only after signature/issuer/audience validation; if you need claim validators, configure `ReactiveJwtDecoder`/validators. If you need authority mapping, configure the converter.

## 19. Clearly Distinguishing Authentication and Authorization

| Stage | Question | Failure Example |
|---|---|---|
| Credential extraction | Is there a syntactically valid `Authorization: Bearer`? | Malformed header |
| JWT/opaque authentication | Is the token trusted and active? | Invalid signature, expired, `active=false` |
| Principal and authorities | Who is calling, and what scopes does the token have? | Missing claim or contract mismatch in mapping |
| Endpoint authorization | Does the token have permission to call this operation? | Missing `SCOPE_orders.read` |
| Object authorization | Does the subject have permission on **order 42**? | Order belongs to another tenant |
| Business policy | Does the current state allow the action? | Canceling a shipped order |

`AuthenticationWebFilter` belongs to the earlier stages. `authorizeExchange` and service policies belong to the later stages.

### 19.1. Scopes Are Only Part of Authorization

If a token contains `orders.read`, WebFlux authorization may allow the GET endpoint through, but the service still needs to verify `(issuer, sub)`, tenant, ownership, and state. Never treat `hasAuthority("SCOPE_orders.read")` as proof of access to every row in the database.

### 19.2. Client Credentials Are Not Equivalent to a User

In a machine-to-machine token:

```json
{
  "sub": "nightly-worker",
  "client_id": "nightly-worker",
  "scope": "orders.export",
  "aud": ["orders-api"]
}
```

`sub` can be a service identity rather than a customer. Reactive SecurityContext still holds an Authentication, but business policies must distinguish **user-delegated** from **service/client** tokens. Never blindly use `authentication.getName()` as a user ID to fetch personal data.

## 20. Testing AuthenticationWebFilter and SecurityWebFilterChain with WebTestClient

`WebTestClient` is the standard tool for testing WebFlux. Spring Security Test provides configurers to inject mock Authentication into test requests.

Example dependencies:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
```

### 20.1. Testing with mockJwt()

With `WebTestClient` bound to the application context:

```java
package com.example.orders.security;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class ReactiveSecurityTest {

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

    @Test
    void validMockAuthenticationWithReadScopeCanReachHandler() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt
                    .subject("customer-42")
                    .claim("tenant_id", "tenant-a"))
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_orders.read")
                ))
            .get()
            .uri("/api/orders/order-42")
            .exchange()
            .expectStatus().isOk();
    }

    @Test
    void missingScopeIsForbidden() {
        client.mutateWith(mockJwt()
                .authorities(
                    new SimpleGrantedAuthority("SCOPE_unrelated")
                ))
            .get()
            .uri("/api/orders/order-42")
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void missingAuthenticationGetsUnauthorized() {
        client.get()
            .uri("/api/orders/order-42")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
```

**Precondition:** the test requires a handler and repository fixture for `order-42` readable by subject `customer-42`; otherwise, the first test may return 404/403 due to **object policy** — which is not a failure of mock authentication. This illustrates testing the web API chain, not a standalone runnable project.

**Important warning:** `mockJwt()` creates a mock Authentication; it **does not send a real JWT through `ServerBearerTokenAuthenticationConverter` and does not prove that `ReactiveJwtDecoder` verifies signatures**. Use it to test authorization and handlers, not as an end-to-end token-validation test.

### 20.2. Testing with a Bearer Header and Real/Test-Double ReactiveJwtDecoder

An integration test covering the full flow needs to:

1. Send the HTTP header `Authorization: Bearer <TEST_JWT>`.
2. Let `AuthenticationWebFilter` actually run and have the converter read the header.
3. Use a **controlled** `ReactiveJwtDecoder` or fake issuer/JWKS server.
4. Confirm a token with valid signature/issuer/audience passes authentication.
5. Confirm a token with bad signature/expired/wrong issuer/wrong audience gets 401.
6. Confirm a valid token missing a scope gets 403.
7. Confirm missing tokens on protected URLs get 401.
8. Confirm `WWW-Authenticate` uses Bearer and does not redirect to login.
9. Confirm service object policy still denies cross-tenant/cross-owner access.

If a decoder test double always returns a valid JWT, the test **does not prove signature validation**; testing signatures requires a real key pair and test issuer.

### 20.3. Testing Reactive Security Context

You can construct a test Authentication directly to test context propagation:

```java
Jwt testJwt = Jwt.withTokenValue("test-only")
    .header("alg", "RS256")
    .claim("sub", "customer-42")
    .claim("iss", "https://login.example.com")
    .claim("scope", "orders.read")
    .build();

JwtAuthenticationToken testAuthentication =
    new JwtAuthenticationToken(
        testJwt,
        List.of(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    );

Mono<String> identity = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName())
    .contextWrite(
        ReactiveSecurityContextHolder.withAuthentication(
            testAuthentication
        )
    );

StepVerifier.create(identity)
    .expectNext("customer-42")
    .verifyComplete();
```

This fragment requires imports for `Jwt`, `JwtAuthenticationToken`, `SimpleGrantedAuthority`, `List`, `Mono`, and `StepVerifier` in the test class.

Here the test **explicitly constructs an Authentication** to verify Reactor Context behavior, which does not mean production code is allowed to construct principals from unverified data.

### 20.4. For Opaque Tokens

Spring Security Test supports mock opaque principals for WebFlux. Authorization logic tests can use mock tokens/principals depending on your test library version, but to test **HTTP introspection**, send a real Bearer header and use a fake introspection endpoint returning `active=true/false`, Basic credential errors, timeouts, or malformed responses.

### 20.5. Essential Test Cases

| Scenario | Objective |
|---|---|
| GET protected endpoint without token | 401 Bearer |
| JWT with invalid signature | Rejected by decoder |
| JWT with wrong issuer/audience | Rejected by decoder/validator |
| Expired token | Authentication fails |
| Valid token, missing scope | Authorization returns 403 |
| Valid token, sufficient scope | Handler receives Authentication |
| Sufficient scope, wrong tenant/owner | Denied by service |
| Converter sees no Bearer header | No authenticated principal created |
| Malformed header or multiple Bearer credentials | Fails per RFC/policy |
| Inside pipeline using `ReactiveSecurityContextHolder` | Principal is retrieved |
| Detached `subscribe()`/out-of-pipeline callback | Must not assume context exists |
| Opaque `active=false` | Access not granted |
| AS/JWKS/introspection outage | Fail closed, handle infrastructure error |
| Multiple security chains | API not hijacked by web login chain |
| Custom filter | No duplicate authentication or bypass |
| Method security path on reactive service | Permissions enforced even outside controllers |

## 21. Troubleshooting in Production

### 21.1. API Receives Token but Authentication Is Always Null

Possible causes:

- The request is not passing through the expected `SecurityWebFilterChain`.
- Incorrect `securityMatcher` or route rewrite.
- Converter does not see the Bearer header.
- Decoder/introspector rejects the token.
- Code reads Servlet `SecurityContextHolder` instead of `ReactiveSecurityContextHolder`.
- Code executes in a detached subscription/thread without Reactor Context.
- Controller runs outside the WebFlux-managed pipeline.

**How to investigate:** check filter chain matchers, inbound headers safely, decoder errors, and where Reactor Context gets detached. Never log raw tokens.

### 21.2. AuthenticationWebFilter Bean Exists but Does Not Run

Possible causes:

- Not registered in a `SecurityWebFilterChain`.
- The chain does not match the request.
- `requiresAuthenticationMatcher` does not match.
- Filter placed at the wrong order.
- Accidentally using Servlet `Filter` APIs in WebFlux.
- Application is running as MVC because `spring-boot-starter-web` is present and the web application type is not what was expected.

Declaring a filter as a Spring bean **does not automatically ensure** it is inserted properly into every WebFlux chain; attach it via the DSL or `addFilterAt` on a specific chain.

### 21.3. Getting 403 Even Though the Token Has the Scope

Check:

- Is `scope` a string or `scp` a list?
- Is the actual authority named `SCOPE_orders.read` or using a different prefix?
- Did a custom JWT converter accidentally replace the default scope converter?
- Which authority does the endpoint matcher require?
- Is the rejection coming from the web filter, method security, or object policy?
- Does the token have the right audience and pass the decoder?

Never disable signature/audience validation or add `permitAll()` to “fix” a missing-permission 403.

### 21.4. Some Requests Succeed While Others Lose the Principal

Symptoms may stem from:

- Code calling `subscribe()` manually.
- Bridging reactive code to callbacks/executors outside the same pipeline.
- Blocking libraries relying on ThreadLocal without proper context propagation.
- Async scheduling or message consumers running outside the request.
- Tests using mocked authentication that do not reflect production paths.

Design around **reactive composition** rather than detached pipelines.

### 21.5. Calling `block()` Causes System Hangs Under High Load

WebFlux has a small number of event-loop threads, so blocking can slow down all requests. Do not place blocking lookups, JDBC, or synchronous HTTP clients inside reactive converters or managers without controlled scheduling. Prefer reactive I/O and monitor event-loop latency.

### 21.6. API Returns HTML Login Instead of 401 Bearer

Common causes:

- API requests fall into the web login chain due to matcher ordering.
- A custom failure handler redirects to `/login`.
- OAuth2 Login is configured globally without separating API paths.
- Gateway/ingress rewrites 401 into 302/HTML.
- Clients automatically follow redirects, masking the initial response.

Configure Bearer entry points and inspect each hop. A Resource Server should never turn token errors into unexpected HTML login pages.

## 22. Security and Operability

### 22.1. Never Log Bearer Credentials

A bearer access token is a credential: anyone holding it can attempt to use it while it remains valid. Avoid placing raw tokens in:

- HTTP access logs.
- Trace span attributes or baggage.
- Exception details returned to frontends.
- Metrics labels.
- Query parameters/URLs.
- Public debugger dumps.

Log request IDs, verified issuer IDs, `authenticated/denied` outcomes, categorized internal error codes, and latency; minimize personal data.

### 22.2. An Active Token Does Not Replace Business Authorization

Even when `AuthenticationWebFilter` works perfectly, a `SCOPE_orders.read` token is not enough to read every order. Services must verify owner, tenant, delegated rights, and resource state—especially in GraphQL, batch jobs, and nested resources.

### 22.3. Rate Limiting Before Authentication

An attacker can send floods of meaningless Bearer tokens to trigger decoder/network fetches or opaque introspection. Implement:

- Rate limiting at the edge/gateway.
- Header and token length limits.
- Connection pools, timeouts, and concurrency limits for outbound introspection.
- Appropriate JWKS caching and key rotation policies.
- Retry storm protection and fail-closed behavior when dependencies are unavailable.
- Never allow clients to select JWKS/introspection URLs from unverified inputs.

### 22.4. Observability

Measure metrics such as:

- Authentication success and failure counts.
- JWT decode and introspection durations.
- Signature/issuer/audience/exp failures at non-sensitive error-code granularity.
- 401 vs. 403 ratios by endpoint group.
- Reactor Netty event-loop delays or blocking warnings.
- Opaque introspection HTTP timeouts and pool saturation.
- Number of custom filter invocations of the authentication manager.
- Rejection rates outside authority or object policy boundaries.

Do not use raw tokens or `sub` as high-cardinality metric tags.

### 22.5. Enforce Load Boundaries and Fail Closed

In WebFlux, non-blocking execution handles high request concurrency, but **does not guarantee downstream Authorization Servers, JWKS endpoints, or databases have unlimited capacity**. If opaque tokens must be introspected on every request, enforce timeouts, connection pooling, backpressure/admission control, and revocation-aware caching.

When valid authentication evidence is missing, **never open access** to “keep the API alive”. Distinguish dependency failures from token errors for proper operations while still denying protected actions.

## 23. Preferred Standard Design

A practical approach for building a WebFlux Resource Server:

1. Start with **`@EnableWebFluxSecurity` + `SecurityWebFilterChain` + `ServerHttpSecurity.oauth2ResourceServer`**.
2. Choose one authentication path: **JWT via `ReactiveJwtDecoder`** or **opaque via `ReactiveOpaqueTokenIntrospector`** per contract.
3. Configure required issuer, audience, token profile, and claim validators; never just decode payloads.
4. Use standard `ServerBearerTokenAuthenticationConverter` for Bearer headers; avoid accepting arbitrary tokens via URLs.
5. Use `JwtAuthenticationConverter`/reactive adapter or official converters to map authorities when needed; do not write filters merely to rename scope prefixes.
6. Use `authorizeExchange` for functional permissions by HTTP route.
7. Use reactive method security and domain policies for service, tenant, owner, and resource-state permissions.
8. Use `ReactiveSecurityContextHolder` or verified actor contexts; **never assume ThreadLocal**.
9. Keep every step in a single Reactor pipeline; never call `block()` or `subscribe()` arbitrarily.
10. Separate the API chain and web login chain if the application has both authentication models.
11. Return Bearer 401/403 responses; never redirect API requests to HTML login.
12. Test filter integration with Bearer headers, mocked authorization, object policies, and context propagation.
13. Only create a manual `AuthenticationWebFilter` when the standard DSL cannot fit, with explicit filter order, failure handlers, security context handling, and no duplicate filtering.

## 24. Summary of Component Responsibilities

| Component | Input | Output | Responsibility |
|---|---|---|---|
| `SecurityWebFilterChain` | `ServerWebExchange` | Matching WebFilter chain | Selects filters protecting the request |
| `AuthenticationWebFilter` | Exchange, converter, manager | Auth success/failure and context | Coordinates authentication in the reactive pipeline |
| `ServerBearerTokenAuthenticationConverter` | `Authorization: Bearer ...` | `Mono<BearerTokenAuthenticationToken>` | Extracts credential; does not verify JWT yet |
| `JwtReactiveAuthenticationManager` | Bearer auth request | `Mono<Authentication>` | Calls JWT decoder and converts Jwt to Authentication |
| `ReactiveJwtDecoder` | Raw JWT string | `Mono<Jwt>` | Verifies token using keys and validators |
| `ReactiveOpaqueTokenIntrospector` | Raw opaque token | `Mono<OAuth2AuthenticatedPrincipal>` | Validates token via introspection |
| `ReactiveSecurityContextHolder` | Reactor Context | `Mono<SecurityContext>` | Accesses security identity in the pipeline |
| Reactive authorization web filter | Authentication, endpoint rules | Allow/deny | Evaluates `authorizeExchange` |
| Reactive method security | Authentication, method invocation | Allow/deny | Protects service invocations |
| Domain policy | Actor, resource, action | Allow/deny | Enforces object/tenant and business rules |
| `ServerAuthenticationEntryPoint` | Authentication error | HTTP error | e.g., 401 Bearer challenge |
| `ServerAccessDeniedHandler` | Access denied | HTTP error | e.g., 403 Forbidden |

## 25. References

- [Spring Security Reference — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `@EnableWebFluxSecurity`, `SecurityWebFilterChain`, and `ServerHttpSecurity`.
- [Spring Security Reference — Reactive OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): Bearer JWT, `ReactiveJwtDecoder`, validators, and JWT authorities.
- [Spring Security Reference — Reactive OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector` and opaque authentication.
- [Spring Security API — AuthenticationWebFilter](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/web/server/authentication/AuthenticationWebFilter.html): converter, authentication manager resolver, success/failure, context repository.
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): SecurityContext in Reactor Context.
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` and method authorization.
- [Project Reactor Reference — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): context propagation in reactive pipelines.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer tokens, 401, and 403.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token requirements under the OAuth profile.

**Remember:** `AuthenticationWebFilter` is the **authentication coordinator in the WebFlux chain**, but it does not “trust” a token merely because a Bearer string was found. The converter extracts the credential, the reactive manager and decoder/introspector **verify** it, and Spring Security places the result into the **Reactor Context** so authorization can proceed. In downstream layers, `authorizeExchange`, reactive method security, and domain policies decide whether the request may operate on a specific resource. Designing these boundaries properly keeps a WebFlux Resource Server **non-blocking**, **compliant with the OAuth2 model**, and **free of business security gaps**.
