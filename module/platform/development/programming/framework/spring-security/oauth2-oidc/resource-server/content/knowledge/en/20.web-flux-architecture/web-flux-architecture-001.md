# SecurityWebFilterChain and Configuration via ServerHttpSecurity

## 1. Why Does WebFlux Have a Separate Spring Security System?

In **Spring Security OAuth 2.0 / OIDC Resource Server**, an API can run on Spring MVC or Spring WebFlux. Both can receive HTTP Bearer access tokens, verify JWTs or opaque tokens, and check scopes; however, their **security filter infrastructure** is different.

| Servlet/Spring MVC | Reactive/Spring WebFlux |
|---|---|
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| Servlet `Filter` and `FilterChainProxy` | WebFlux `WebFilter` and `WebFilterChainProxy` |
| ThreadLocal-based `SecurityContextHolder` | Reactor Context-based `ReactiveSecurityContextHolder` |
| `JwtDecoder` | `ReactiveJwtDecoder` |
| `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` |
| `MockMvc` | `WebTestClient` |

Simply changing a controller's return type from `OrderDto` to `Mono<OrderDto>` **does not mean** a Servlet `SecurityFilterChain` configuration will automatically become a security configuration for WebFlux. When building a reactive API, you must use the corresponding reactive abstractions.

The two most important components:

- **`SecurityWebFilterChain`:** describes the `WebFilter` instances protecting a group of HTTP exchanges.
- **`ServerHttpSecurity`:** DSL builder to configure authentication, authorization, OAuth 2.0 Resource Server, CSRF, CORS, exception handling, and security headers.

A `SecurityWebFilterChain` bean is typically the result of `ServerHttpSecurity.build()`. When multiple chains exist, Spring Security selects the first chain that matches the request in the configured order.

### Objectives

After this lesson, you will be able to:

1. Create a `SecurityWebFilterChain` for WebFlux.
2. Use `authorizeExchange`, `pathMatchers`, and `anyExchange` to describe policies.
3. Enable `oauth2ResourceServer(...jwt(...))` or `opaqueToken(...)`.
4. Distinguish between 401 authentication errors and 403 authorization errors.
5. Design multiple chains using `securityMatcher` and `@Order`.
6. Understand CSRF/CORS, stateless Bearer APIs, Reactor Context, and reactive principals.
7. Integrate reactive method security and test using `WebTestClient`.

## 2. WebFlux Security Operates on a WebFilter Chain

### 2.1. `WebFilter` Is Not a Servlet `Filter`

A WebFlux filter uses:

~~~java
package org.springframework.web.server;

public interface WebFilter {
    Mono<Void> filter(
        ServerWebExchange exchange,
        WebFilterChain chain
    );
}
~~~

This is a simplified signature for illustration; the types are provided by Spring Framework. `ServerWebExchange` represents the request/response in WebFlux. `Mono<Void>` represents an asynchronous completion task, not an immediate return value after the entire request has been processed.

Servlet code typically uses `Filter#doFilter(ServletRequest, ServletResponse, FilterChain)`, whereas WebFlux uses reactive publishers. Therefore, security extension points must also use reactive types.

### 2.2. Overview Pipeline

~~~mermaid
flowchart TD
    A["HTTP request"] --> B["Spring WebFlux WebFilter pipeline"]
    B --> C["Spring Security WebFilterChainProxy"]
    C --> D{"Which SecurityWebFilterChain matches?"}
    D --> E["Authentication WebFilters"]
    E --> F{"Is the JWT or opaque token valid?"}
    F -->|No| G["Authentication error, usually 401"]
    F -->|Yes| H["Reactive Authentication in Reactor Context"]
    H --> I["AuthorizationWebFilter"]
    I --> J{"Does the authorizeExchange rule allow it?"}
    J -->|No| K["Access denied, usually 403"]
    J -->|Yes| L["WebFlux controller / handler"]
    L --> M["Mono or Flux response"]
~~~

This diagram is conceptual and does not list all WebFilters or the exact ordering across every Spring Security version.

Some commonly encountered components:

| Component | Role |
|---|---|
| `WebFilterChainProxy` | Selects the matching security chain |
| `SecurityWebFilterChain` | List of WebFilters for a security policy |
| `ServerHttpSecurity` | Builder that creates the chain |
| `AuthenticationWebFilter` | Performs the authentication step according to the configured mechanism |
| `ServerBearerTokenAuthenticationConverter` | Reads the Bearer token from the request |
| `ReactiveAuthenticationManager` | Validates credentials and creates an Authentication |
| `ReactiveJwtDecoder` | Decodes/verifies JWTs against validators |
| `ReactiveOpaqueTokenIntrospector` | Introspects opaque tokens |
| `AuthorizationWebFilter` | Checks authorization for the exchange |
| `ReactiveSecurityContextHolder` | Accesses the security context via Reactor Context |

**Authentication** and **authorization** are two separate concerns. A valid JWT does not mean the caller is allowed to read every order; URL scope rules and tenant/owner permissions still need to be checked.

### 2.3. Reactor Context Replaces ThreadLocal

Servlet code typically accesses:

~~~java
SecurityContextHolder.getContext().getAuthentication();
~~~

In WebFlux, the pipeline can switch threads. ThreadLocal does not automatically propagate across a reactive subscription. Spring Security WebFlux uses Reactor Context:

~~~java
ReactiveSecurityContextHolder.getContext();
~~~

This method returns `Mono<SecurityContext>`. Do not call `block()` during request processing just to obtain Authentication synchronously.

## 3. Initializing a WebFlux Resource Server Application

### 3.1. Gradle Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Use the Spring Boot plugin/BOM to manage compatible versions rather than mixing Spring Framework and Spring Security versions arbitrarily.

**Note when adding both web starters:** if a project includes both `spring-boot-starter-web` and `spring-boot-starter-webflux`, Spring Boot typically prefers a Servlet web application based on its web type deduction mechanism. Do not assume an application is reactive simply because the WebFlux dependency or some `Mono` types are present in the source code.

### 3.2. Correct Imports

~~~java
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
~~~

Do not confuse them with:

~~~java
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.security.config.annotation.web.configuration.EnableWebSecurity;
~~~

The second group belongs to the Servlet stack.

## 4. Minimal SecurityWebFilterChain Configuration

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class ReactiveSecurityConfig {

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .anyExchange().authenticated()
            )
            .build();
    }
}
~~~

This configuration illustrates **authorization policy** and has not yet selected a Bearer token authentication mechanism.

- `@EnableWebFluxSecurity` enables WebFlux security support.
- `@Bean` provides a security chain to the Spring context.
- `authorizeExchange(...)` defines authorization rules based on ServerWebExchange.
- `pathMatchers(...)` selects specific paths.
- `permitAll()` removes authorization requirements for those paths.
- `authenticated()` requires an authenticated principal.
- `build()` creates the `SecurityWebFilterChain`.

Spring Boot may auto-configure default security in certain situations; when custom policies are needed, define the bean explicitly and test the HTTP routes.

### 4.1. Comparing WebFlux and Servlet DSLs

Servlet:

~~~java
http.authorizeHttpRequests(auth -> auth
    .requestMatchers("/api/public/**").permitAll()
    .anyRequest().authenticated()
);
~~~

WebFlux:

~~~java
http.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .anyExchange().authenticated()
);
~~~

Do not use `authorizeHttpRequests` directly on `ServerHttpSecurity`. In the reactive stack, the DSL is designed for `ServerWebExchange` and reactive matchers/managers.

## 5. Complete JWT Resource Server Configuration

### 5.1. Issuer and Audience

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          audiences:
            - orders-api
~~~

The issuer and audience above are examples. A valid token for the Resource Server must have the right signature, issuer, expiration, and audience for the API itself. `audiences` is a Boot property on supported versions; with a custom decoder, you must explicitly preserve the audience validator.

**Do not use an OIDC ID Token as an access token.** An ID Token is issued to the OIDC client for login authentication; an API requires an OAuth access token with the proper audience and profile.

### 5.2. Enabling JWT and Controlling Scopes

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class OrdersApiSecurity {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET,
                    "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST,
                    "/api/orders", "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

In a typical configuration, Spring Security reads `scope` or `scp` from the JWT and converts them into authorities prefixed with `SCOPE_`. For example:

~~~json
{"scope": "orders.read orders.export"}
~~~

can become:

~~~text
SCOPE_orders.read
SCOPE_orders.export
~~~

The rule `hasAuthority("SCOPE_orders.write")` will not be satisfied automatically when the token only contains `orders.read`.

### 5.3. Meaning of the DSL

| DSL | Meaning |
|---|---|
| `authorizeExchange(...)` | Declares HTTP authorization rules |
| `pathMatchers(HttpMethod.GET, ...)` | Restricts the rule by HTTP method and path |
| `hasAuthority("SCOPE_orders.read")` | Matches the exact authority string |
| `authenticated()` | Requires a valid Authentication |
| `oauth2ResourceServer(...)` | Enables Resource Server Bearer authentication |
| `jwt(Customizer.withDefaults())` | Uses the default reactive JWT verification |
| `build()` | Builds the security WebFilter chain |

**`authenticated()` does not decode Bearer JWTs by itself.** You must enable an authentication mechanism such as `oauth2ResourceServer(...jwt(...))` so that tokens are verified.

### 5.4. Typical HTTP Outcomes

A request without a token to a protected URL:

~~~http
GET /api/orders/42 HTTP/1.1
~~~

typically receives **401** with a Bearer challenge.

A token with an invalid signature, expired timestamp, or wrong issuer/audience: authentication fails, typically returning **401** with `invalid_token`.

A valid token without `SCOPE_orders.read`: authorization rejects the request, typically returning **403**. Access to a specific resource may still be denied by tenant/owner policies even when the scope is valid.

## 6. Matcher Rules: Specific Rules Must Come Before Broad Rules

### 6.1. Configuration That Risks Exposing the API Publicly

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/**").permitAll()
    .pathMatchers("/api/admin/**")
        .hasAuthority("SCOPE_admin")
    .anyExchange().authenticated()
)
~~~

The overly broad rule `"/api/**"` comes first, so the admin matcher below it may never be evaluated. Having a strict-looking rule name in the source code cannot save an incorrect ordering.

Better:

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers("/api/admin/**")
        .hasAuthority("SCOPE_admin")
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .anyExchange().authenticated()
)
~~~

### 6.2. `anyExchange().authenticated()` or `denyAll()`?

If you use:

~~~java
.anyExchange().authenticated()
~~~

then a newly added endpoint without a dedicated scope rule can still be accessed by **any authenticated token**. This may be an intentional policy, but you must understand the trade-off.

If you use:

~~~java
.anyExchange().denyAll()
~~~

then every unmatched route is rejected according to the **default deny** principle. When adding a new route, developers must explicitly update the policy.

| Goal | Typical Appropriate Fallback |
|---|---|
| Every API route requires a token, and certain routes require specific scopes | `authenticated()` |
| Only open explicitly listed routes | `denyAll()` |
| Completely public API with specific restrictions | Requires fine-grained policies; do not accidentally place a broad `permitAll` |

A `denyAll` fallback can also return 403 for non-existent URLs because authorization runs before handler routing. Do not confuse this 403 with a controller 404.

### 6.3. Pay Attention to HTTP Methods and Root Paths

The rule:

~~~java
.pathMatchers(HttpMethod.GET, "/api/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

does not automatically govern POST requests. If POST must require a write scope, add an explicit rule.

The path `/api/orders` may need a separate matcher from `/api/orders/**` depending on pattern matching semantics. This lesson uses both paths in example 5 to clearly express both the root endpoint and sub-endpoints.

## 7. Multiple SecurityWebFilterChain Beans and @Order Priority

### 7.1. Why Have Multiple Chains?

An application may have:

- `/api/**`: Bearer JWT/opaque token.
- `/actuator/health`: health check for the platform.
- `/admin/**`: stricter rules.
- `/web/**`: OIDC browser login/session.

You can create separate `SecurityWebFilterChain` beans, each with its own `securityMatcher`.

### 7.2. Multi-Chain Configuration Pattern

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.PathPatternParserServerWebExchangeMatcher;

@Configuration
@EnableWebFluxSecurity
public class MultiChainSecurityConfig {

    @Bean
    @Order(1)
    SecurityWebFilterChain health(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/actuator/health"
                )
            )
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().permitAll()
            )
            .build();
    }

    @Bean
    @Order(2)
    SecurityWebFilterChain api(ServerHttpSecurity http) {
        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher(
                    "/api/**"
                )
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }

    @Bean
    @Order(3)
    SecurityWebFilterChain fallback(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .anyExchange().denyAll()
            )
            .build();
    }
}
~~~

This is **an alternative configuration** to the single-chain example; do not register two overlapping configuration sets in the same application without controlling matchers and priorities.

**Note:** the health endpoint might only be `/actuator/health`, while `/actuator/health/liveness` is a different route. If child paths also need to be public, add an appropriate matcher and test them separately; do not expose all of `/actuator/**` publicly just to make health checks work. Some actuator endpoints expose sensitive data that requires separate authentication.

### 7.3. Two Different Matching Layers

~~~text
SecurityWebFilterChain.securityMatcher(...)
    -> Should the request be routed into this chain?

ServerHttpSecurity.authorizeExchange(...)
    -> Inside the selected chain, what permissions does the request need?
~~~

The **first matching** security chain is applied in order; Spring Security does not continue through other chains to find a permit rule. If a broad `"/api/**"` chain with `permitAll` is ordered before an `"/api/admin/**"` chain, the admin chain may never be selected.

### 7.4. A Fallback Chain Prevents Unprotected Security Gaps

If no chain matches a path, the request may not receive the intended policy. A `fallback` chain with `anyExchange().denyAll()` enables default-deny across the application.

Every new route, CORS preflight, actuator endpoint, health check, metrics endpoint, WebSocket handshake, or static resource must be verified for chain coverage before production.

## 8. ReactiveJwtDecoder and Custom JWT Validation

### 8.1. Reactive Decoder

WebFlux uses:

~~~java
org.springframework.security.oauth2.jwt.ReactiveJwtDecoder
org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder
~~~

Do not use a Servlet `JwtDecoder` bean as the default choice and call `block()`. The reactive decoder is responsible for processing tokens within the reactive authentication flow.

### 8.2. Issuer Discovery and JWK Set URI

Common configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
~~~

When issuer discovery is used, the framework resolves issuer details and JWKS from the metadata published by the AS. Depending on the version and initialization approach, network discovery may occur at startup or when decoding the first request.

When a trusted JWKS URI is provided by contract:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.test/realms/shop
          jwk-set-uri: https://id.example.test/realms/shop/protocol/openid-connect/certs
~~~

this can reduce reliance on metadata discovery, but **issuer validation must not be skipped**. A JWT signed by the same IdP with an audience intended for another API must still be rejected.

### 8.3. Reactive Decoder Bean with Issuer and Audience Validators

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration
public class ReactiveDecoderConfig {

    private static final String ISSUER =
        "https://id.example.test/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.test/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder() {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(JWKS_URI)
                .build();

        OAuth2TokenValidator<Jwt> standard =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token audience is not orders-api",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                standard,
                audience
            )
        );

        return decoder;
    }
}
~~~

**Important when creating a custom decoder:**

- Spring Boot auto-configuration may back off when a custom `ReactiveJwtDecoder` bean is present; properties such as `audiences` are not guaranteed to be automatically attached to that decoder.
- `setJwtValidator(...)` replaces the decoder's validators; do not replace it with only a custom audience validator and inadvertently lose issuer and timestamp checks.
- Verify JWT signature/`alg` allowlist, `iss`, `aud`, `exp`, `nbf`, and required custom claims according to the contract.
- Do not use unverified `jku`/`kid` values to fetch keys from arbitrary hosts.
- Avoid logging raw bearer tokens.

## 9. Reactive Authority Converter and Token Permission Boundaries

### 9.1. Scopes to Authorities

Given the token:

~~~json
{
  "sub": "user-123",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-42"
}
~~~

Spring Security by default typically produces:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

`hasAuthority("SCOPE_orders.read")` matches by exact string. Claims such as `app_roles` or `groups` do not automatically become `ROLE_ADMIN`. Only map roles via a converter with an explicit issuer, audience, schema, and allowlist.

### 9.2. ReactiveJwtAuthenticationConverterAdapter

One way to use a synchronous converter for in-memory claims in WebFlux:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationConverter;
import org.springframework.security.oauth2.server.resource.authentication.JwtGrantedAuthoritiesConverter;
import org.springframework.security.oauth2.server.resource.authentication.ReactiveJwtAuthenticationConverterAdapter;

@Configuration
public class ReactiveAuthoritiesConfig {

    @Bean
    ReactiveJwtAuthenticationConverterAdapter jwtConverter() {
        JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

        scopes.setAuthoritiesClaimName("scope");
        scopes.setAuthorityPrefix("SCOPE_");

        JwtAuthenticationConverter delegate =
            new JwtAuthenticationConverter();

        delegate.setJwtGrantedAuthoritiesConverter(scopes);

        return new ReactiveJwtAuthenticationConverterAdapter(delegate);
    }
}
~~~

In the chain, you can inject `ReactiveJwtAuthenticationConverterAdapter jwtConverter`:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(jwtConverter)
    )
)
~~~

The adapter is convenient for fast, non-I/O mappings. If the converter needs to perform reactive DB or network calls, use an appropriate reactive converter or a separate authorization service. **Do not call `block()` inside a JWT converter** to load roles from a database.

### 9.3. Do Not Turn Local Permissions into Scopes

A token with only `orders.read` does not automatically gain `orders.approve` just because the user has an approve role in the database. If an approval endpoint requires both **the token scope and a local entitlement**, the policy must express an AND condition:

~~~text
ALLOW_APPROVE =
    JWT active and intended for API
    AND SCOPE_orders.approve
    AND current local entitlement permits approve
    AND order tenant/owner/ACL permits action
~~~

Do not simply merge OAuth scopes with database permissions into one set and evaluate them with OR.

## 10. Stateless APIs: CSRF, Basic/Form Login, and SecurityContextRepository

### 10.1. When Can CSRF Be Disabled?

CSRF is an issue when browsers automatically send **ambient credentials** such as session cookies. For an API that only accepts a **Bearer token in the Authorization header**, does not use cookie authentication, and has no browser login in the chain, disabling CSRF can be considered.

However, **do not** blindly disable CSRF in applications that use cookies/sessions or browser OIDC login. Apply it per security chain and according to your threat model.

### 10.2. Example: Bearer-Only Without Persisting WebSession SecurityContext

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class BearerOnlyApiConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
            .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

This is an **alternative** to the chain in Section 5; do not register multiple overlapping chains without configuring `securityMatcher` and `@Order`.

`NoOpServerSecurityContextRepository` does not store the SecurityContext in WebSession across requests. It **does not remove authentication for the current request**: Bearer authentication is still placed into the Reactor Context for authorization.

### 10.3. Cookie-Based Web UIs Must Keep Separate Policies

An application that has:

~~~text
/api/** -> Bearer-only stateless -> JSON 401/403
/web/** -> OIDC login/session    -> redirects, CSRF protects browser flows
~~~

should generally use separate security chains. Do not globally disable CSRF just because `/api/**` is Bearer-only.

## 11. CORS in WebFlux

### 11.1. Why Can the Frontend Encounter a CORS 401?

An SPA at `https://app.example.test` calls the API at `https://api.example.test` with an `Authorization` header. The browser may send an OPTIONS preflight before the actual request. If the preflight is blocked because it lacks a JWT, the frontend may only see a CORS error message.

CORS must be handled appropriately in the reactive pipeline. CORS does not validate tokens and does not replace OAuth 2.0 validation.

### 11.2. Reactive CorsWebFilter

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsWebFilter;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;

@Configuration
public class ReactiveCorsConfig {

    @Bean
    CorsWebFilter corsWebFilter() {
        CorsConfiguration cors = new CorsConfiguration();

        cors.setAllowedOrigins(
            List.of("https://app.example.test")
        );
        cors.setAllowedMethods(
            List.of("GET", "POST", "PUT", "DELETE", "OPTIONS")
        );
        cors.setAllowedHeaders(
            List.of("Authorization", "Content-Type")
        );
        cors.setExposedHeaders(
            List.of("WWW-Authenticate", "X-Request-Id")
        );

        UrlBasedCorsConfigurationSource source =
            new UrlBasedCorsConfigurationSource();

        source.registerCorsConfiguration("/api/**", cors);
        return new CorsWebFilter(source);
    }
}
~~~

This is the **WebFlux** `CorsWebFilter` and reactive `UrlBasedCorsConfigurationSource`, not the Servlet `CorsFilter`.

If using `ServerHttpSecurity.cors(...)` or another WebFlux CORS configuration, maintain one consistent strategy and avoid unintentionally registering duplicate CORS filters with conflicting policies.

### 11.3. Exposing the Bearer Challenge

If frontend JavaScript needs to read `WWW-Authenticate` on cross-origin responses:

~~~http
Access-Control-Expose-Headers: WWW-Authenticate
~~~

When using cookie credentials, do not set uncontrolled wildcard origins. For preflight requests, ensure allowed origins, methods, and headers are configured specifically and processed before Bearer authorization.

## 12. Reactive Errors: Authentication Entry Point and Access Denied Handler

### 12.1. Extension Points Differ from Servlet

In WebFlux:

~~~java
org.springframework.security.web.server.ServerAuthenticationEntryPoint
org.springframework.security.web.server.authorization.ServerAccessDeniedHandler
~~~

These methods operate on `ServerWebExchange` and return `Mono<Void>`. They differ from Servlet `AuthenticationEntryPoint` and `AccessDeniedHandler`.

They can be wired via:

~~~java
http.exceptionHandling(exceptions -> exceptions
    .authenticationEntryPoint(myReactiveEntryPoint)
    .accessDeniedHandler(myReactiveDeniedHandler)
);
~~~

`myReactiveEntryPoint` and `myReactiveDeniedHandler` are reactive implementations provided by the application. When standard Bearer errors suffice, prefer the OAuth2 Resource Server default handlers over crafting headers manually.

### 12.2. RFC 6750 and HTTP Status Codes

| Scenario | Typical HTTP Status | Bearer Error |
|---|---|---|
| No token sent to protected endpoint | 401 | Bearer challenge, typically no `error` |
| Invalid/expired JWT | 401 | `invalid_token` |
| Malformed Bearer request | 400 | `invalid_request` when applicable |
| Valid token but missing OAuth scope | 403 | `insufficient_scope` |
| Tenant/owner/ACL denied | 403 or 404 per policy | Do not falsely assume missing scope |
| JWKS/introspection unavailable | Infrastructure error per config | Do not fail open or claim the token is revoked |

If adding an RFC 9457 JSON body:

~~~json
{
  "type": "about:blank",
  "title": "Unauthorized",
  "status": 401,
  "detail": "Authentication is required or the token is invalid.",
  "code": "invalid_token"
}
~~~

the actual HTTP status must still be 401, `Content-Type` must be `application/problem+json`, and `WWW-Authenticate` must be preserved. **Do not return HTTP 200 with a JSON status of 401**.

### 12.3. WebFlux Responses Do Not Use Servlet sendError

A reactive handler sets the status/headers on `ServerHttpResponse` and returns a publisher that writes the body. Do not use `HttpServletResponse.sendError(...)` in WebFlux. Do not call `subscribe()` yourself and return `Mono.empty()`, as this may complete the response before the body is written or lose error/context propagation.

If the response has already been committed, status/headers cannot reliably be changed. When a uniform JSON format is desired, test the Bearer filter, authorization WebFilter, and handler exception paths on your actual Spring Security version.

## 13. Opaque Token Introspection in WebFlux

### 13.1. Configuring Opaque Tokens

If the Authorization Server issues opaque tokens or the API requires online introspection:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.test/oauth2/introspect
          client-id: orders-api-introspector
          client-secret: ${OAUTH_INTROSPECTION_CLIENT_SECRET}
~~~

Do not commit `client-secret` to source control and do not expose the secret to browser frontends. The Resource Server needs its own client credentials to be authorized to introspect.

### 13.2. Enabling Opaque Resource Server

~~~java
@Bean
SecurityWebFilterChain opaqueSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        )
        .build();
}
~~~

This is an **alternative** to the JWT chain, not an extra bean to add when the same request path already has another JWT chain.

### 13.3. ReactiveOpaqueTokenIntrospector

WebFlux uses the interface:

~~~java
org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector
~~~

Introspection can reflect `active:false` from the AS when a token is revoked, but it also introduces an HTTP dependency. Risks include:

- Network latency and tail latency.
- AS timeouts, HTTP 5xx errors, or rate limits.
- Inability to make fresh trust decisions when the introspection endpoint is down.
- Cached results causing stale `active` status and scopes.
- `active:true` not automatically granting read access across all tenants or owners.

Do not fall back to a synchronous Servlet `OpaqueTokenIntrospector` and call `block()` inside the reactive security pipeline.

### 13.4. Opaque Principal

Opaque Resource Server typically creates a principal of type `OAuth2AuthenticatedPrincipal`, not `Jwt`. If controllers need claims while the application supports both opaque and JWT workflows, choose the principal abstraction per security chain or use an internal identity DTO.

## 14. Principal and SecurityContext in Reactive Controllers

### 14.1. WebFlux Controller Receiving `@AuthenticationPrincipal Jwt`

~~~java
package com.example.orders.api;

import reactor.core.publisher.Mono;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class MeController {

    @GetMapping("/api/me")
    public Mono<MeResponse> me(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(
            new MeResponse(
                jwt.getSubject(),
                jwt.getClaimAsString("tenant_id")
            )
        );
    }

    public record MeResponse(
        String subject,
        String tenantId
    ) {}
}
~~~

This example assumes a JWT-only protected endpoint and an access token contract with the corresponding claims. If `tenant_id` determines data scope, validate its type and value in the JWT decoder or policy; do not default to a global tenant when the claim is missing.

### 14.2. Retrieving Authentication from Reactor Context

~~~java
package com.example.orders.service;

import reactor.core.publisher.Mono;

import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.ReactiveSecurityContextHolder;
import org.springframework.security.core.context.SecurityContext;

public class CallerService {

    public Mono<String> currentName() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
~~~

If there is no context, the pipeline may complete empty. On `permitAll` endpoints, callers must define an explicit guest/null policy; do not let `Mono.empty()` accidentally lead to a default permission.

### 14.3. Do Not Use ThreadLocal for Reactive Security

An error-prone code pattern:

~~~java
Authentication auth =
    SecurityContextHolder.getContext().getAuthentication();
~~~

In WebFlux, the thread executing operators can change. Unless specialized context propagation is explicitly configured and verified, do not rely on ThreadLocal as the source of truth. Prefer `ReactiveSecurityContextHolder` or the principal injected by Spring Security.

### 14.4. Do Not Call `subscribe()` Manually to Detach Authorization and Business Side Effects

Bad idea:

~~~java
public Mono<Void> approve(String id) {
    policy.canApprove(id).subscribe(allowed -> {
        if (allowed) {
            orders.approve(id).subscribe();
        }
    });

    return Mono.empty();
}
~~~

These are two detached subscriptions. The HTTP response may complete before authorization or the DB write runs; security context, transactions, and error propagation may be lost.

Better:

~~~java
public Mono<Void> approve(String id) {
    return policy.canApprove(id)
        .flatMap(allowed -> {
            if (!allowed) {
                return Mono.error(
                    new AccessDeniedException(
                        "Approval is not permitted"));
            }

            return orders.approve(id);
        });
}
~~~

`policy` and `orders` are illustrative reactive application services. Imports: `reactor.core.publisher.Mono` and `org.springframework.security.access.AccessDeniedException`.

**Do not call `block()` on the WebFlux request path** just to fetch authentication or DB permissions synchronously.

## 15. Reactive Method Security and Business Boundaries

### 15.1. Enabling the Reactive Annotation

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableReactiveMethodSecurity;

@Configuration
@EnableReactiveMethodSecurity
public class ReactiveMethodSecurityConfig {
}
~~~

It integrates with Reactor Context and reactive application publishers. Do not enable only Servlet `@EnableMethodSecurity` and assume reactive method security is active.

### 15.2. Service Returning Mono

~~~java
package com.example.orders.service;

import reactor.core.publisher.Mono;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class OrdersQueryService {

    private final ReactiveOrderRepository orders;

    public OrdersQueryService(ReactiveOrderRepository orders) {
        this.orders = orders;
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Mono<OrderDto> load(String id) {
        return orders.findDtoById(id);
    }
}
~~~

`ReactiveOrderRepository` and `OrderDto` are application-defined. With reactive method security, return `Mono`/`Flux` according to the framework/version contract so the interceptor can compose the policy into the publisher.

### 15.3. Tenant/ACL Permissions Are Still Required in the Service

A token with `SCOPE_orders.read` must still be denied if the order belongs to a different tenant. You can combine checks with a reactive repository:

~~~java
public Mono<OrderDto> loadForCaller(
        String orderId,
        String subject,
        String tenantId) {

    return access.canReadOrder(subject, tenantId, orderId)
        .flatMap(allowed -> {
            if (!allowed) {
                return Mono.error(
                    new AccessDeniedException(
                        "Order access denied"));
            }

            return orders.findByIdAndTenantId(orderId, tenantId)
                .switchIfEmpty(
                    Mono.error(
                        new ResponseStatusException(
                            HttpStatus.NOT_FOUND)));
        });
}
~~~

This is a business example; `access` and `orders` must be real reactive services/repositories. URL/method-level scopes and object/tenant-level permissions are conditions that must **all be satisfied** when the contract requires them.

### 15.4. Self-Invocation Remains an AOP Limitation

Even in reactive code, a method:

~~~java
@PreAuthorize("hasAuthority('SCOPE_orders.approve')")
public Mono<Void> approve(String orderId) { ... }
~~~

can be bypassed if another method on the same target bean calls `this.approve(orderId)` under the Spring AOP proxy model. Extract the separately protected method into another bean and invoke it via dependency injection, or secure the public entry point appropriate for the entire workflow.

Do not conclude every execution path is protected simply because the annotation is “present in the source code”.

## 16. Non-Blocking Must Be Preserved Throughout the Security Flow

### 16.1. Blocking Operations to Avoid

- `Thread.sleep(...)` inside a reactive operator.
- Blocking `RestTemplate` HTTP calls directly on the event loop.
- Synchronous JDBC/JPA repositories in a request handler.
- `Mono.block()`/`Flux.block()` on a WebFlux event-loop thread.
- Blocking file I/O not offloaded to an appropriate scheduler.

A reactive Resource Server can still stall if business code blocks the event loop.

### 16.2. When Legacy Blocking Dependencies Still Exist

Transitional solution:

~~~java
public Mono<OrderDto> findLegacyOrder(String id) {
    return Mono.fromCallable(
            () -> jdbcRepository.findOrderDto(id))
        .subscribeOn(Schedulers.boundedElastic());
}
~~~

Import `reactor.core.scheduler.Schedulers`. Bounded elastic helps offload blocking work from the event loop, but it does not turn JDBC into reactive I/O and does not guarantee unbounded concurrency. Timeouts and throughput must be controlled and load-tested.

With a native reactive stack, prefer `WebClient` and appropriate reactive drivers/repositories; do not use `subscribe()` or `block()` to bridge the security flow.

## 17. WebSocket, SSE, and Long-Lived Streams

WebFlux can serve Server-Sent Events, streaming `Flux` responses, and WebSocket handshakes. Distinguish between:

- Authentication/authorization when **establishing the request/handshake**.
- Permissions on **each message/record/event** while the stream is running.
- The possibility that a token expires or is revoked **after the initial request passed security**.

`SecurityWebFilterChain` does not by default re-verify the Bearer token for **every Flux element** of a long-lived streaming response. For systems requiring revocation or entitlement freshness in long-lived streams, you must build policy-based re-verification mechanisms.

Do not emit sensitive data in a stream before ownership/tenant authorization has succeeded.

## 18. Testing WebFlux Security with WebTestClient

### 18.1. Differences from Servlet MockMvc

WebFlux uses:

~~~java
org.springframework.test.web.reactive.server.WebTestClient
~~~

A Spring Boot test can look like:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest
@AutoConfigureWebTestClient
class ApiSecurityTests {

    @Autowired
    WebTestClient client;
}
~~~

Test starter imports and annotation names may change across Spring Boot major versions; this example follows the Spring Boot 3.x style.

### 18.2. Missing Token: 401

~~~java
@Test
void protectedApiRequiresBearerToken() {
    client.get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isUnauthorized();
}
~~~

When thoroughly testing Bearer responses, also assert the corresponding `WWW-Authenticate` header.

### 18.3. Testing Authorities with `mockJwt()`

Spring Security Test provides a reactive helper:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;

import org.springframework.security.core.authority.SimpleGrantedAuthority;
~~~

For GET with `SCOPE_orders.read`:

~~~java
@Test
void readScopeAllowsGet() {
    client.mutateWith(
            mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        )
        .get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isOk();
}
~~~

Missing scope:

~~~java
@Test
void missingReadScopeIsForbidden() {
    client.mutateWith(
            mockJwt().authorities(
                new SimpleGrantedAuthority("SCOPE_profile")
            )
        )
        .get()
        .uri("/api/orders/42")
        .exchange()
        .expectStatus().isForbidden();
}
~~~

`mockJwt()` requires a `WebTestClient` integrated with Spring Security test support, such as via `springSecurity()` configuration for an application-context-bound client. Whether `@AutoConfigureWebTestClient` wires the proper integration automatically must be checked against your Spring Boot/test setup version.

**Important:** `mockJwt()` creates a mock Authentication and does not verify signature, issuer, audience, expiration, or JWKS. To test JWT verification, use a real test token signed with a test key/JWKS, or stub `ReactiveJwtDecoder` in the integration context and verify Bearer filter behavior.

### 18.4. Test Matrix

| Request | Principal/Token | Security Expectation |
|---|---|---|
| GET `/api/orders/42` | No token | 401 |
| GET `/api/orders/42` | Valid JWT with `SCOPE_orders.read` | Passes URL authz |
| GET `/api/orders/42` | Only `SCOPE_profile` | 403 |
| POST `/api/orders` | Only `SCOPE_orders.read` | 403 when write rule is correct |
| POST `/api/orders` | `SCOPE_orders.write` | Passes URL authz |
| GET `/api/public/info` | No token | Permitted past security |
| GET public URL | Invalid Bearer | May return 401 because the filter still authenticates |
| GET unmatched URL | Valid token | Per `authenticated`/`denyAll` fallback |
| GET health URL | No token | Per health chain |
| JWT invalid signature/expired | Real Bearer | 401 via decoder |
| JWT wrong audience | Real Bearer | 401 if audience validator is configured |
| API read with valid scope but wrong tenant | Valid JWT | Denied by service policy |
| OPTIONS preflight | No Bearer token | Per CORS policy, without enforcing authn |
| Browser reading Bearer challenge | Cross-origin | Proper exposed header |

“Passes URL authz” **does not automatically mean HTTP 200**. The controller may return 404 because the order does not exist or 500 due to missing test fixtures. When writing tests, clearly separate security checks from business logic checks.

### 18.5. Testing Multiple Chains

With `@Order`, test these paths:

- `/actuator/health` selects the health chain.
- `/api/orders/42` selects the API JWT chain.
- Other URLs select the fallback deny chain.
- No broad public chain is ordered ahead of the API chain.
- 401/403 from the JWT chain do not turn into OIDC browser redirects.
- No new routes are permitted solely because of an overly broad fallback.

## 19. Common Architectural Mistakes

### Mistake 1 — Using `HttpSecurity` in a WebFlux App

`HttpSecurity`/`SecurityFilterChain` are for Servlet. For WebFlux, use `ServerHttpSecurity`/`SecurityWebFilterChain`.

### Mistake 2 — Not Enabling `oauth2ResourceServer(...)`

`anyExchange().authenticated()` is a policy and does not verify JWT Bearer tokens by itself. A reactive authentication mechanism is required.

### Mistake 3 — Relying on ThreadLocal `SecurityContextHolder`

Reactive publishers can switch threads. Use `ReactiveSecurityContextHolder` or an injected principal.

### Mistake 4 — A Broad `permitAll` Rule Shadowing Scope-Protected Rules

Matcher order matters. Place specific rules before broad rules.

### Mistake 5 — Assuming Multiple Chains Merge Policies

Only the first matching chain is selected. `@Order` and `securityMatcher` define the security boundary.

### Mistake 6 — Missing a Fallback Chain

URLs that match no chain may not be protected as intended. For default-deny, use a fallback with `anyExchange().denyAll()`.

### Mistake 7 — Disabling CSRF Globally Including Browser Login

Only consider disabling CSRF on Bearer-only chains based on the threat model. Cookie-based flows still need appropriate CSRF protection.

### Mistake 8 — Using Servlet CORS Classes

WebFlux requires reactive CORS support such as `CorsWebFilter`. Ensure preflight handling and expose `WWW-Authenticate` if the SPA needs to read challenges.

### Mistake 9 — Calling Blocking Code on the Event Loop

`block()`, synchronous JDBC/HTTP, and `Thread.sleep` can cause latency and stalls. Use reactive composition or a managed transitional scheduler.

### Mistake 10 — Using `@EnableMethodSecurity` Instead of Reactive Method Security

WebFlux reactive method security should use `@EnableReactiveMethodSecurity` and Reactor context-aware interception.

### Mistake 11 — Using an ID Token Instead of an Access Token

A Resource Server requires an OAuth access token with the proper audience and token profile. An OIDC ID Token is not intended for API access by default.

### Mistake 12 — Granting Access Across All Tenants Based Only on Scope

Scopes govern the type of action; owner/ACL/tenant checks must be enforced by the service/repository.

### Mistake 13 — Testing `mockJwt()` and Concluding the Decoder Is Flawless

`mockJwt()` is for authorization tests and does not prove signature, issuer, or audience verification. Dedicated decoder/JWKS tests are required.

### Mistake 14 — Returning HTTP 200 Containing Error JSON from a Reactive Handler

An invalid JWT should typically return 401; a valid token missing an authority should typically return 403. A JSON body must not replace HTTP response semantics.

### Mistake 15 — Logging Bearer Tokens or Secrets

Do not log `Authorization`, raw JWTs, opaque tokens, or introspection client secrets. Use correlation IDs, error categories, and redacted metrics.

## 20. Integrated Architecture Diagram

~~~mermaid
flowchart TD
    A["Client Bearer request"] --> B["WebFlux WebFilterChainProxy"]
    B --> C{"SecurityWebFilterChain + @Order"}
    C --> D["API SecurityWebFilterChain"]
    C --> E["Health SecurityWebFilterChain"]
    C --> F["Fallback deny chain"]
    D --> G["Reactive authentication"]
    G --> H{"JWT or opaque?"}
    H --> I["ReactiveJwtDecoder + validators"]
    H --> J["ReactiveOpaqueTokenIntrospector"]
    I --> K["Authentication in Reactor Context"]
    J --> K
    K --> L["authorizeExchange path/method/scope"]
    L --> M{"Sufficient permissions?"}
    M -->|No| N["Semantically accurate 401/403"]
    M -->|Yes| O["WebFlux handler Mono/Flux"]
    O --> P["Reactive method security"]
    P --> Q["Entitlement + tenant/owner/ACL"]
    Q --> R["Reactive repository"]
    R --> S["HTTP response"]
~~~

JWT and opaque in the diagram are **two configurable authentication options**, not a requirement to enable both for a single token.

## 21. Summary

**`SecurityWebFilterChain`** is the chain that protects WebFlux requests; **`ServerHttpSecurity`** is the DSL for configuring that chain. These two concepts mirror Servlet `SecurityFilterChain`/`HttpSecurity` in responsibility, but they cannot be used interchangeably.

Core principles:

1. **Use the right reactive stack:** `@EnableWebFluxSecurity`, `ServerHttpSecurity`, `SecurityWebFilterChain`, reactive decoder/introspector.
2. **Make exchange authorization explicit:** `authorizeExchange`, method/path matchers, scopes, and fallbacks.
3. **Do not confuse chain selection with policy:** `securityMatcher` and `@Order` select the chain; `authorizeExchange` defines permissions within the chain.
4. **Enable actual Resource Server support:** `jwt(...)` or `opaqueToken(...)`; `authenticated()` alone does not verify Bearer tokens.
5. **Preserve Reactor Context:** use `ReactiveSecurityContextHolder` and `Mono`/`Flux` composition instead of ThreadLocal, `block()`, or detached subscriptions.
6. **Configure CSRF/CORS per threat model:** Bearer-only differs from browser cookies/sessions; preflight requests must be handled properly.
7. **Scopes do not replace business rules:** owner/tenant/ACL and entitlements may all need to be verified together.
8. **Test with the right stack:** `WebTestClient`, `mockJwt()` for authz, and decoder/introspection tests for authn.
9. **Preserve response semantics:** invalid tokens typically return 401; valid tokens lacking scopes typically return 403; never return HTTP 200 with error JSON.

### References

- [Spring Security Reference — WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html)
- [Spring Security Reference — Resource Server JWT (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security Reference — Resource Server Opaque Token (Reactive)](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security Reference — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/authorize-http-requests.html)
- [Spring Security Reference — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html)
- [Spring Security Reference — WebFlux Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/index.html)
- [Spring Security API — ServerHttpSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/web/server/ServerHttpSecurity.html)
- [Spring Security API — SecurityWebFilterChain](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/SecurityWebFilterChain.html)
- [Spring Security API — ReactiveSecurityContextHolder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html)
- [Spring Framework Reference — WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
