# Creating a WebFlux Version with Policy Parity to the Servlet Version

When migrating a Spring Security OAuth 2.0/OIDC Resource Server from **Servlet/MVC** to **WebFlux**, the goal is to preserve the exact same security decisions for the same request: the same trusted issuer, the same algorithms and token profile, the same audience, the same scopes/roles, the same public/private route rules, the same error policy, and the same tenant/object boundaries.

The two stacks have different execution models. Servlet uses `HttpSecurity`, `SecurityFilterChain`, `JwtDecoder`, `OpaqueTokenIntrospector`, and typically stores `SecurityContext` via a thread-bound mechanism. WebFlux uses `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtDecoder`, `ReactiveOpaqueTokenIntrospector`, and Reactor Context. Therefore, a proper migration **translates the policy and preserves semantics** while using the right reactive APIs.

This lesson builds a WebFlux counterpart equivalent to a sample Servlet API. The scope covers:

- JWT Resource Server and opaque token Resource Server.
- Issuer, JWKS, algorithms, timestamps, audience, and scopes.
- Public/private routes, HTTP methods, and multiple security chains.
- Stateless behavior, CSRF, CORS, and exception handling.
- Principals, the service layer, and reactive method security.
- Testing with `WebTestClient`, real test tokens, and mock authentication.
- A Servlet/WebFlux result comparison matrix to confirm parity.

> **Principle:** do not compare class counts or lines of code between the two stacks. Compare policies and observable outcomes. Given the same token and the same request, Servlet and WebFlux must make equivalent decisions per the agreed contract.

## 1. Start with a Policy Inventory of the Servlet Version

Before writing WebFlux configuration, document the current policy. If you only port matchers while forgetting decoder validators, session handling, CSRF, or error handling, both applications may start cleanly yet protect the API differently.

Suppose the current Servlet version has the following policy:

| Item | Orders API Policy |
|---|---|
| Authentication | OAuth 2.0 Bearer access token |
| Token format | JWT per issuer profile |
| Issuer | `https://login.example.com/realms/shop` |
| JWKS | Endpoint published by the issuer |
| Algorithm | `RS256` only |
| Audience | Must contain `orders-api` |
| Timestamp | Validate `exp`, `nbf`, `iat` per profile and clock-skew policy |
| Token type | Access-token profile accepted by the API |
| Read scope | `SCOPE_orders.read` |
| Write scope | `SCOPE_orders.write` |
| Public routes | `/api/public/**` |
| Read routes | `GET /api/orders/**` |
| Write routes | `POST`, `PUT`, `DELETE /api/orders/**` |
| Default route policy | Deny |
| Session | Stateless for Bearer API |
| CSRF | Disabled only when the API does not use auto-sent cookies as credentials |
| CORS | Allow only approved frontend origins |
| Authentication failure | 401 with Bearer challenge |
| Authorization failure | 403 |
| Object access | Read/modify only orders belonging to an authorized tenant or owner |
| Method security | Optional additional checks at the service boundary |

This is an example contract. When migrating a real system, replace each value with the verified policy of the Servlet application.

### 1.1. Separate Authentication, Authorization, and Business Authorization

Keep these three layers independent:

1. **Authentication:** Is the token valid, with the right issuer, signature, audience, and validity window?
2. **HTTP authorization:** Does the caller have the scope/authority to invoke this route and HTTP method?
3. **Business authorization:** Is the caller permitted to act on the specific order, tenant, or object?

For instance, a token with `orders.read` but `aud=billing-api` must be rejected at authentication. A token with audience `orders-api` but lacking `orders.write` authenticates and is then rejected at HTTP authorization. A token with write scope targeting an order in another tenant must be rejected at business authorization.

Do not collapse these conditions into a `permitAll()` or a single scope check.

## 2. Mapping Servlet APIs to WebFlux APIs

| Servlet/MVC | WebFlux | Responsibility |
|---|---|---|
| `HttpSecurity` | `ServerHttpSecurity` | Builds security configuration |
| `SecurityFilterChain` | `SecurityWebFilterChain` | Policy for a group of requests |
| `FilterChainProxy` | `WebFilterChainProxy` | Selects the security chain |
| Servlet `Filter` | `WebFilter` | Processes requests in the filter pipeline |
| `RequestMatcher` | `ServerWebExchangeMatcher` | Matches routes/chains |
| `JwtDecoder` | `ReactiveJwtDecoder` | Decodes and validates JWTs |
| `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` | Introspects opaque tokens |
| `AuthenticationManager` | Reactive authentication manager | Authenticates credentials asynchronously |
| `SecurityContextHolder` | `ReactiveSecurityContextHolder` | Accesses the security context |
| `SecurityContextRepository` | `ServerSecurityContextRepository` | Saves/loads context per stack |
| `AuthenticationEntryPoint` | `ServerAuthenticationEntryPoint` | Handles authentication failures |
| `AccessDeniedHandler` | `ServerAccessDeniedHandler` | Handles access denied |
| `MockMvc` | `WebTestClient` | Tests HTTP/security |
| `@EnableMethodSecurity` | `@EnableReactiveMethodSecurity` | Method security |
| `MockMvc` + `jwt()` | `WebTestClient` + `mockJwt()` | Mocks JWT authentication in tests |

Concepts are analogous, but types differ. Never pass a `JwtDecoder` into a WebFlux configurer or use `MockMvc` to test a `SecurityWebFilterChain`.

## 3. Dependencies and Application Type

A WebFlux Resource Server application typically requires:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The Spring Boot BOM manages compatible versions. Never mix Spring Security Test from a different release than the runtime.

### 3.1. Avoid Accidentally Running the Servlet Stack

If both `spring-boot-starter-web` and `spring-boot-starter-webflux` are on the classpath, Spring Boot typically chooses the Servlet application type via auto-configuration conditions. When targeting a WebFlux server:

- Verify the application starts with the reactive web application type.
- Avoid pulling in `spring-boot-starter-web` transitively from another dependency.
- If both stacks must coexist, configure the application type explicitly and understand which components are actually initialized.
- Inspect startup logs/context to verify the WebFlux server and reactive security chain are active.

Merely changing controllers to return `Mono` does not turn a Servlet application into WebFlux.

## 4. Reference Servlet Version

An example Servlet configuration might look like this:

~~~java
@Configuration
class ServletApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .requestMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

This snippet assumes the decoder is configured separately via properties or a Bean to check issuer, audience, algorithm, and token profile. It also assumes the API only accepts Bearer tokens in the `Authorization` header and does not use cookies/sessions as credentials. Accordingly, disabling CSRF must be evaluated against the actual credential model.

The WebFlux version will keep the same route policy and token validation, using reactive components.

## 5. Configuring the Equivalent WebFlux `SecurityFilterChain`

### 5.1. Creating `SecurityWebFilterChain`

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

@Configuration(proxyBeanMethods = false)
@EnableWebFluxSecurity
public class ReactiveApiSecurityConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .securityContextRepository(
                NoOpServerSecurityContextRepository.getInstance()
            )
            .csrf(csrf -> csrf.disable())
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/api/public/**").permitAll()
                .pathMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .pathMatchers(HttpMethod.PUT, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .pathMatchers(HttpMethod.DELETE, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults())
            )
            .build();
    }
}
~~~

Key correspondences:

- `ServerHttpSecurity` replaces `HttpSecurity`.
- `SecurityWebFilterChain` replaces `SecurityFilterChain`.
- `authorizeExchange` replaces `authorizeHttpRequests`.
- `pathMatchers` replaces `requestMatchers`.
- `anyExchange().denyAll()` replaces `anyRequest().denyAll()`.
- `oauth2ResourceServer().jwt(...)` still enables JWT Bearer authentication.
- `NoOpServerSecurityContextRepository` expresses the policy of not persisting the security context in `WebSession` for this API.

If the project has a different CSRF/CORS policy, preserve that policy instead of copying `disable()` from the example.

### 5.2. When to Use `Customizer.withDefaults()`?

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
)
~~~

This uses the appropriate `ReactiveJwtDecoder` in the application context, whether auto-configured by Spring Boot from properties or declared as a Bean by the application.

If the application uses opaque tokens:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
)
~~~

Do not enable both JWT and opaque just to "support all token types." Enable only what matches the issuer's token contract and the designed authentication manager.

### 5.3. Statelessness in WebFlux

Servlet typically uses:

~~~java
.sessionCreationPolicy(SessionCreationPolicy.STATELESS)
~~~

WebFlux does not use `SessionCreationPolicy` in the same way. `ServerSecurityContextRepository` controls whether the context is saved/loaded from a server-side session.

For a stateless Bearer API, you can use:

~~~java
.securityContextRepository(
    NoOpServerSecurityContextRepository.getInstance()
)
~~~

This does not mean no part of the application ever uses `WebSession`. WebFlux can still use sessions for other features. It only specifies that this chain's security context is not persisted by that repository.

If the application also has browser login/sessions, use a separate chain and an appropriate repository for the browser flow.

## 6. Preserving JWT Validation When Switching Decoders

### 6.1. Using Properties When Standard Policy Suffices

Example configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://login.example.com/realms/shop/protocol/openid-connect/certs
          jws-algorithms:
            - RS256
~~~

Property names and support such as `audiences` depend on the Spring Boot version. To guarantee audience validation across versions, declare the validator explicitly in the decoder and verify the exact behavior of the active BOM.

`issuer-uri` is the canonical issuer. `jwk-set-uri` is where public keys are fetched. Do not replace the issuer with the JWKS URL and do not drop issuer validation just because the JWKS URI is known.

### 6.2. Declaring `ReactiveJwtDecoder` Explicitly

When a specific policy is required, create a reactive decoder:

~~~java
package com.example.orders.security;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

@Configuration(proxyBeanMethods = false)
public class ReactiveJwtDecoderConfiguration {

    @Bean
    ReactiveJwtDecoder reactiveJwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.audience}") String audience) {

        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder
                .withJwkSetUri(jwkSetUri)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Required audience is missing",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audienceValidator
            )
        );

        return decoder;
    }
}
~~~

This configuration preserves:

- JWS signature verification via public keys fetched from the JWKS URI.
- Allowing only `RS256`.
- Issuer validation.
- Default timestamp validation in the corresponding validator.
- Requiring the audience to contain `orders-api` (read from a property).

If the API requires RFC 9068, a custom `typ`, or a dedicated token profile, add the corresponding profile validator. Never disable type validation and forget to replace it with a profile validator.

### 6.3. When Declaring a Custom Decoder, Auto-Configuration Backs Off

Declaring a `ReactiveJwtDecoder` Bean can replace the decoder Boot would have created. Therefore, do not assume a custom decoder automatically picks up all `issuer-uri`, `audiences`, and `jws-algorithms` properties.

Wire all required conditions into the custom decoder and write negative tests for:

- Wrong issuer.
- Wrong audience.
- Invalid signature.
- Disallowed algorithm.
- Expired token.
- Wrong token type/profile.

### 6.4. Distinguishing JWT Authentication from Authorization

The decoder only verifies the token. Spring Security then maps scopes/claims into `GrantedAuthority`.

By standard convention, `scope` or `scp` claims map to authorities with the `SCOPE_` prefix:

~~~text
scope = "orders.read orders.write"

Authorities:
  SCOPE_orders.read
  SCOPE_orders.write
~~~

If the Servlet version uses a custom `JwtAuthenticationConverter` reading a `permissions` claim, the WebFlux version must use an equivalent reactive converter or appropriate adapter. Never assume a Servlet converter is directly invoked in a reactive chain.

## 7. Custom Authority Mapping in WebFlux

Suppose the issuer's token contains:

~~~json
{
  "sub": "user-42",
  "permissions": ["orders.read", "orders.write"]
}
~~~

The Servlet version might use `JwtAuthenticationConverter` paired with `JwtGrantedAuthoritiesConverter`. In WebFlux, authentication conversion is reactive; use `ReactiveJwtAuthenticationConverter` or the adapter provided by your Spring Security version.

Conceptual configuration example:

~~~java
ReactiveJwtAuthenticationConverter converter =
    new ReactiveJwtAuthenticationConverter();

JwtGrantedAuthoritiesConverter authoritiesConverter =
    new JwtGrantedAuthoritiesConverter();

authoritiesConverter.setAuthoritiesClaimName("permissions");
authoritiesConverter.setAuthorityPrefix("SCOPE_");

converter.setJwtGrantedAuthoritiesConverter(
    new ReactiveJwtGrantedAuthoritiesConverterAdapter(
        authoritiesConverter
    )
);
~~~

Then wire the converter into the JWT configurer:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt
        .jwtAuthenticationConverter(converter)
    )
)
~~~

Exact class/adapter names and packages should be verified against your Spring Security version. If the project does not need custom claim mapping, keeping the default converter is simpler.

### 7.1. Parity Must Compare Authorities, Not Just Claims

The same token must produce the same set of authorities on both stacks:

| Token claim | Servlet expected | WebFlux expected |
|---|---|---|
| `scope=orders.read` | `SCOPE_orders.read` | `SCOPE_orders.read` |
| `scope=orders.write` | `SCOPE_orders.write` | `SCOPE_orders.write` |
| `permissions=["orders.admin"]` | Per custom converter | Same result from reactive converter |
| No scope | No scope authority | No scope authority |
| Unrecognized scope | Not granted automatically | Not granted automatically |

If one converter uses `ROLE_` and the other uses `SCOPE_`, the two applications will make different decisions for the exact same token.

## 8. Opaque Tokens: Switching to Reactive Introspection

If the Servlet Resource Server uses opaque tokens, WebFlux must use `ReactiveOpaqueTokenIntrospector`.

### 8.1. Properties

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://login.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: "${ORDERS_INTROSPECTION_CLIENT_SECRET}"
~~~

If your Boot version supports reactive opaque Resource Server auto-configuration, properties can create the appropriate reactive introspector. Inspect the dependency stack and auto-configuration report for your version.

### 8.2. Security Chain

~~~java
@Bean
SecurityWebFilterChain opaqueApiSecurity(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        )
        .build();
}
~~~

### 8.3. Custom Reactive Introspector

When custom timeouts, HTTP clients, caching, or response mapping are needed, declare a `ReactiveOpaqueTokenIntrospector` Bean. It returns `Mono<OAuth2AuthenticatedPrincipal>`.

Never invoke a blocking Servlet `OpaqueTokenIntrospector` performing network I/O directly on the event loop. If integrating a blocking library is unavoidable, offload it to an appropriate blocking scheduler and manage timeouts/cancellation explicitly; prefer a reactive client.

### 8.4. Preserving Opaque Token Semantics

Both stacks must preserve:

- `active=false` must be rejected.
- Proper introspection client authentication.
- Issuer/resource context matching the contract.
- Identical scope mapping.
- Timeouts and dependency failures never fail open.
- Cache TTL never exceeds the revocation SLA.
- Never log raw access tokens or client secrets.

The default opaque token principal is typically `OAuth2AuthenticatedPrincipal`, whereas the JWT principal is typically `Jwt`. If controllers currently cast the principal to `Jwt`, update the adapter/domain boundary to support the right token type.

## 9. Route Policy: Porting Matchers While Preserving Order and Semantics

### 9.1. Matcher Mapping Table

| Servlet | WebFlux |
|---|---|
| `.authorizeHttpRequests(...)` | `.authorizeExchange(...)` |
| `.requestMatchers("/api/public/**")` | `.pathMatchers("/api/public/**")` |
| `.requestMatchers(HttpMethod.GET, "/api/**")` | `.pathMatchers(HttpMethod.GET, "/api/**")` |
| `.anyRequest().denyAll()` | `.anyExchange().denyAll()` |
| `.hasAuthority("SCOPE_orders.read")` | `.hasAuthority("SCOPE_orders.read")` |
| `.hasRole("ADMIN")` | `.hasRole("ADMIN")` |
| `.authenticated()` | `.authenticated()` |
| `.permitAll()` | `.permitAll()` |

Matching authority names do not guarantee identical policies if matchers or ordering differ.

### 9.2. Complete Route Policy Example

~~~java
.authorizeExchange(exchanges -> exchanges
    .pathMatchers("/api/public/**").permitAll()
    .pathMatchers(HttpMethod.GET, "/api/orders/**")
        .hasAuthority("SCOPE_orders.read")
    .pathMatchers(
        HttpMethod.POST,
        "/api/orders/**"
    ).hasAuthority("SCOPE_orders.write")
    .pathMatchers(
        HttpMethod.PUT,
        "/api/orders/**"
    ).hasAuthority("SCOPE_orders.write")
    .pathMatchers(
        HttpMethod.DELETE,
        "/api/orders/**"
    ).hasAuthority("SCOPE_orders.write")
    .pathMatchers("/actuator/health").permitAll()
    .anyExchange().denyAll()
)
~~~

Verify that:

- `GET` is not accidentally assigned write scope.
- `POST`/`PUT`/`DELETE` all require write permission.
- Public routes do not accidentally match too broadly.
- Actuator policy does not expose administrative endpoints.
- Unknown routes are denied.
- Path variables, trailing slashes, encoded paths, and context paths have verified behavior.

### 9.3. `permitAll()` Does Not Bypass the Bearer Filter

A public request does not need a token to pass authorization. However, if the client still sends a malformed Bearer token, the authentication `WebFilter` may process that token and reject the request before the controller executes.

This is an important behavior when comparing both stacks: do not test a public route with an invalid header expecting `permitAll()` to always skip credential parsing.

## 10. Multiple `SecurityWebFilterChain` Beans and Ordering

If the Servlet version has multiple `SecurityFilterChain` beans, WebFlux needs corresponding `SecurityWebFilterChain` beans with explicit matchers and `@Order`.

Example API chain:

~~~java
@Bean
@Order(1)
SecurityWebFilterChain apiChain(ServerHttpSecurity http) {
    return http
        .securityMatcher(
            ServerWebExchangeMatchers.pathMatchers("/api/**")
        )
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/public/**").permitAll()
            .anyExchange().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

A browser/fallback chain can be configured separately:

~~~java
@Bean
@Order(2)
SecurityWebFilterChain fallbackChain(ServerHttpSecurity http) {
    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/assets/**").permitAll()
            .anyExchange().denyAll()
        )
        .build();
}
~~~

Key imports:

~~~java
import org.springframework.core.annotation.Order;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.util.matcher.ServerWebExchangeMatchers;
~~~

`WebFilterChainProxy` selects the matching chain by matcher and order. Therefore:

- The `/api/**` chain must precede broader chains.
- The fallback chain needs an explicit policy.
- Do not let the first chain match all requests unintentionally.
- Do not leave sensitive routes uncovered between chains.
- Each chain must enable the right authentication mechanism.

If the API chain uses JWT and the browser chain uses form login, there is no need to attach a JWT decoder to the browser chain. If two API chains share the same trust policy, they can share a reactive decoder; if issuer/audience/algorithm differ, separate decoders/managers by trust context.

## 11. CSRF: Preserve the Threat Model, Not Just One Line of Config

Both Servlet and WebFlux include CSRF protection, while API and browser flows may have different credential models.

### 11.1. When Can CSRF Be Disabled?

An API accepting only Bearer tokens explicitly attached by the client in the `Authorization` header typically has a different CSRF threat model from cookie authentication. If the application does not use auto-sent cookies as API credentials, you can configure:

~~~java
.csrf(csrf -> csrf.disable())
~~~

### 11.2. When Should It Not Be Disabled?

If browsers automatically send session cookies or authentication cookies, cross-site requests can carry credentials without attacker knowledge. CSRF protection may still be necessary.

JWT does not inherently eliminate CSRF. If a JWT is stored in a cookie, browsers can send that cookie automatically; evaluate CSRF based on how credentials are transported.

### 11.3. CSRF Parity Tests

| Request | Servlet expected | WebFlux expected |
|---|---|---|
| `GET` private route, valid token | Allowed if sufficient scope | Same result |
| `POST`, Bearer header, CSRF disabled per policy | Evaluated per API contract | Same result |
| `POST`, cookie/session auth, missing CSRF | 403 if CSRF enabled | 403 if CSRF enabled |
| `POST`, valid CSRF token | Continues to authorization | Same result |

Do not add a CSRF token to every WebFlux test just to make tests pass. Tests must accurately reflect the endpoint's policy.

## 12. CORS: Moving Configuration to a Reactive Source

WebFlux uses a reactive CORS configuration source:

~~~java
@Bean
CorsConfigurationSource corsConfigurationSource() {
    CorsConfiguration configuration = new CorsConfiguration();

    configuration.setAllowedOrigins(
        List.of("https://app.example.com")
    );
    configuration.setAllowedMethods(
        List.of("GET", "POST", "PUT", "DELETE", "OPTIONS")
    );
    configuration.setAllowedHeaders(
        List.of("Authorization", "Content-Type", "X-Request-Id")
    );
    configuration.setExposedHeaders(
        List.of("WWW-Authenticate")
    );
    configuration.setAllowCredentials(false);

    UrlBasedCorsConfigurationSource source =
        new UrlBasedCorsConfigurationSource();

    source.registerCorsConfiguration("/api/**", configuration);

    return source;
}
~~~

Use the reactive types:

~~~java
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.reactive.CorsConfigurationSource;
import org.springframework.web.cors.reactive.UrlBasedCorsConfigurationSource;
~~~

Attach to the chain:

~~~java
.cors(cors -> cors.configurationSource(corsConfigurationSource))
~~~

The values above are examples. Preserve the exact origins, methods, headers, and credentials policy of the Servlet version.

### 12.1. Differences to Check

- Is `Authorization` included in allowed headers?
- Is preflight `OPTIONS` handled prior to authentication?
- Is `WWW-Authenticate` exposed if browser JavaScript needs to read it?
- Are credentials/cookies allowed?
- Is a wildcard origin used while `allowCredentials=true`?
- Does a gateway/proxy modify CORS headers?

Mock tests verify server responses; browser E2E tests confirm the browser enforces the CORS protocol properly.

## 13. Authentication Failure and Access Denied in WebFlux

Servlet uses `AuthenticationEntryPoint` and `AccessDeniedHandler`. WebFlux uses:

- `ServerAuthenticationEntryPoint`.
- `ServerAccessDeniedHandler`.

Spring Security Resource Server provides the corresponding reactive Bearer handlers, such as `BearerTokenServerAuthenticationEntryPoint` and `BearerTokenServerAccessDeniedHandler`.

Normally, enabling `.oauth2ResourceServer().jwt()` or `.opaqueToken()` configures default Bearer authentication behavior.

### 13.1. Status Parity

| Scenario | Expected outcome |
|---|---|
| Private route, missing token | 401 |
| Malformed/invalid Bearer token | 401 |
| JWT wrong issuer/audience/signature | 401 |
| Opaque token inactive | 401 |
| Valid token but missing scope | 403 |
| Tenant/object policy denies | 403 or 404 per contract |
| Request exceeds rate limit | 429 if gateway/app policy uses 429 |
| Identity provider timeout | Unauthenticated; status depends on dependency/error contract, never fail open |

Do not turn an audience mismatch into `403`: a token not intended for the API is not authenticated at that API.

### 13.2. Preserving `WWW-Authenticate`

For a Bearer Resource Server, `401` responses should include the `WWW-Authenticate: Bearer` challenge. Invalid tokens can include `error="invalid_token"`. Insufficient scope can be reflected by `403` and `error="insufficient_scope"`.

If a custom reactive entry point writes a JSON body, it must still retain the proper protocol challenge. Never let a custom handler drop headers that clients rely on.

### 13.3. Custom Reactive Handlers

You can attach handlers via the exception handling configurer or Resource Server configurer depending on the goal. Use the reactive interfaces and return `Mono<Void>`; never use a Servlet handler writing directly to `HttpServletResponse`.

Never call `.block()` inside a handler. Write bodies using reactive response APIs and ensure the response is committed only once.

## 14. Principals and the Service Layer: Replacing `ThreadLocal` with Reactor Context

In Servlet, code might read:

~~~java
SecurityContextHolder.getContext()
    .getAuthentication();
~~~

In WebFlux, use:

~~~java
ReactiveSecurityContextHolder.getContext()
    .map(SecurityContext::getAuthentication);
~~~

Service example:

~~~java
@Service
public class CurrentCallerService {

    public Mono<String> currentSubject() {
        return ReactiveSecurityContextHolder.getContext()
            .map(SecurityContext::getAuthentication)
            .map(Authentication::getName);
    }
}
~~~

A controller can use:

~~~java
@GetMapping("/api/me")
Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(Map.of(
        "subject", jwt.getSubject(),
        "issuer", jwt.getIssuer().toString()
    ));
}
~~~

Or retrieve the generic principal:

~~~java
@GetMapping("/api/whoami")
Mono<String> whoAmI(ServerWebExchange exchange) {
    return exchange.getPrincipal()
        .map(Principal::getName);
}
~~~

### 14.1. Do Not Assume the Principal Is Always `Jwt`

JWT mode typically uses `JwtAuthenticationToken` with a `Jwt` principal. Opaque mode typically uses `BearerTokenAuthentication` with an `OAuth2AuthenticatedPrincipal`.

If the Servlet controller casts the principal to `Jwt`, check whether the WebFlux endpoint can receive opaque tokens. If so, introduce a domain abstraction such as `CallerIdentity` and map from verified principals.

### 14.2. Do Not Call `block()` or `subscribe()` in Services

Wrong:

~~~java
String subject = ReactiveSecurityContextHolder.getContext()
    .map(context -> context.getAuthentication().getName())
    .block();
~~~

Wrong:

~~~java
repository.save(order).subscribe();
return Mono.empty();
~~~

Right:

~~~java
public Mono<Order> createOrder(Order order) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(subject ->
            repository.save(order.withOwner(subject))
        );
}
~~~

Publishers must stay in the same reactive chain so context, cancellation, and error propagation are preserved.

### 14.3. Tenant and Object Ownership

Example of a service querying only the caller's orders:

~~~java
public Mono<Order> findOrder(String orderId) {
    return ReactiveSecurityContextHolder.getContext()
        .map(SecurityContext::getAuthentication)
        .map(Authentication::getName)
        .flatMap(subject ->
            repository.findByIdAndOwnerSubject(orderId, subject)
        );
}
~~~

In multi-issuer systems, subjects can collide across issuers. Domain identity should use a canonical user ID or the `(issuer, subject)` pair. The tenant must come from verified claims or a trusted membership store, never from an arbitrary header.

## 15. Reactive Method Security

Where the Servlet version has:

~~~java
@EnableMethodSecurity
~~~

the WebFlux version uses:

~~~java
@EnableReactiveMethodSecurity
~~~

Example:

~~~java
@Configuration
@EnableReactiveMethodSecurity
class ReactiveMethodSecurityConfiguration {
}
~~~

Service:

~~~java
@Service
public class OrderService {

    @PreAuthorize("hasAuthority('SCOPE_orders.read')")
    public Flux<Order> findOrders() {
        return repository.findAll();
    }

    @PreAuthorize("hasAuthority('SCOPE_orders.write')")
    public Mono<Order> createOrder(Order order) {
        return repository.save(order);
    }
}
~~~

Reactive method security uses Reactor's security context, and protected methods must return reactive `Publisher` types such as `Mono` or `Flux` so authorization runs within the reactive flow.

### 15.1. HTTP Authorization Does Not Replace Business Authorization

Even when a route requires `SCOPE_orders.write`, the service may still need to check:

- Does the order belong to the caller's tenant?
- Is the caller the owner or a delegate?
- Does the order's state permit updating?
- Is a service token allowed to perform this action?
- Does the resource belong to the right organization/project?

This is object-level/business authorization. Switching to WebFlux does not make these rules appear automatically.

## 16. Testing WebFlux with `WebTestClient`

### 16.1. Application Context Test

Example:

~~~java
@SpringBootTest
@AutoConfigureWebTestClient
class ReactiveOrdersSecurityTests {

    @Autowired
    WebTestClient webTestClient;
}
~~~

Boot builds `WebTestClient` from the application context. Verify the test is actually running the WebFlux stack and that security `WebFilter`s are registered.

If constructing the client manually from the context:

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

`springSecurity()` in reactive test support attaches Spring Security `WebFilter`s to `WebTestClient`. Avoid registering duplicate security filters when auto-configuration already wires them.

### 16.2. Slice Test with `@WebFluxTest`

~~~java
@WebFluxTest(controllers = OrdersController.class)
@Import(ReactiveApiSecurityConfiguration.class)
class OrdersControllerSecurityTests {

    @Autowired
    WebTestClient webTestClient;

    @MockitoBean
    OrdersService ordersService;
}
~~~

`@WebFluxTest` loads a WebFlux slice context. Import the exact production security configuration you want to verify. Depending on the Spring Boot/Spring Framework version, older projects may use `@MockBean` instead of `@MockitoBean`.

Never replace the security config with a `permitAll()` test chain and conclude the production policy is sound.

## 17. Mock Authentication vs. Real Bearer Tokens

### 17.1. Using `mockJwt()` to Test Authorization

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

`mockJwt()` creates a simulated JWT authentication. It is useful for testing:

- Path matchers.
- Authority rules.
- Controllers receiving the principal.
- Method security.
- Business policies using authentication.

It does not prove `ReactiveJwtDecoder` verifies signatures, issuers, audiences, or JWKS.

### 17.2. Using `mockOpaqueToken()`

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .attributes(attributes ->
            attributes.put("sub", "user-42")
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

This request post-processor creates a sample opaque authentication. It does not call the introspection endpoint.

### 17.3. Testing Missing Token and Missing Scope

~~~java
@Test
void privateRouteWithoutTokenReturns401() {
    webTestClient
        .get()
        .uri("/api/orders")
        .exchange()
        .expectStatus().isUnauthorized()
        .expectHeader().valueMatches(
            HttpHeaders.WWW_AUTHENTICATE,
            "Bearer.*"
        );
}

@Test
void readOnlyTokenCannotCreateOrder() {
    webTestClient
        .mutateWith(mockJwt()
            .authorities(
                new SimpleGrantedAuthority("SCOPE_orders.read")
            )
        )
        .post()
        .uri("/api/orders")
        .bodyValue(new CreateOrderRequest("SKU-1", 2))
        .exchange()
        .expectStatus().isForbidden();
}
~~~

The first test verifies missing Bearer credentials. The second verifies HTTP authorization with mock authentication. If CSRF remains enabled in the application, `POST` might be rejected by CSRF before the scope rule is evaluated; configuration/tests must match the credential model.

### 17.4. Sending Real Bearer Tokens

To test the resolver, authentication manager, and decoder, send the token in the header:

~~~java
webTestClient
    .post()
    .uri("/api/orders")
    .headers(headers ->
        headers.setBearerAuth(signedAccessToken)
    )
    .bodyValue(new CreateOrderRequest("SKU-1", 2))
    .exchange()
    .expectStatus().isCreated();
~~~

Use a real decoder with a test key/JWKS or a test Authorization Server. Do not use `mockJwt()` in tests meant to verify signatures.

### 17.5. Testing Real Opaque Introspection via Stub

Configure `ReactiveOpaqueTokenIntrospector` pointing to an HTTP stub. Send a normal Bearer token and verify:

- The introspector is invoked.
- The request uses `POST` with proper client authentication.
- `active=true` creates authentication.
- `active=false` is rejected.
- Scope/authority mapping matches the Servlet version.
- Timeouts/`5xx` do not fail open.

Do not use `mockOpaqueToken()` to claim HTTP introspection works.

## 18. Parity Testing: Same Inputs, Comparing Results Across Both Stacks

An effective approach is creating a shared contract test suite using common inputs and running it against both Servlet and WebFlux.

### 18.1. Token Matrix

| Token fixture | Servlet expected | WebFlux expected |
|---|---|---|
| Valid JWT, valid issuer/audience/scope | `2xx` per endpoint | Same status/body contract |
| No token on private route | 401 | 401 |
| Malformed JWT | 401 | 401 |
| Invalid signature | 401 | 401 |
| Wrong issuer | 401 | 401 |
| Wrong audience | 401 | 401 |
| Expired token | 401 | 401 |
| Algorithm outside allowlist | 401 | 401 |
| Wrong token type/profile | 401 | 401 |
| Valid token but missing scope | 403 | 403 |
| Inactive opaque token | 401 | 401 |
| Active opaque token missing scope | 403 | 403 |

If the two applications have different error bodies where the contract does not mandate identical bodies, compare status codes, challenge headers, and access decisions. If the body is part of the public API contract, preserve the exact schema.

### 18.2. Route Matrix

| Request | Servlet | WebFlux |
|---|---|---|
| `GET /api/public/health` without token | Permit | Permit |
| `GET /api/orders` with read scope | Permit | Permit |
| `POST /api/orders` with read scope | 403 | 403 |
| `POST /api/orders` with write scope | Permit | Permit |
| `DELETE /api/orders/42` with read scope | 403 | 403 |
| `GET /admin/reports` with API scope | Per admin policy | Same policy |
| Unknown route | Deny | Deny |

### 18.3. Principal/Business Policy Matrix

- Same issuer and subject produce the same domain caller identity.
- Same scopes produce the same authority set.
- Same verified tenant claim produces the same tenant context.
- Tenant mismatch produces the same `403`/`404` outcome.
- Object ownership checks share identical semantics.
- Service tokens and user tokens retain their separate policies as before.
- No request ever inherits a principal from a previous request.

### 18.4. Do Not Compare Status Codes Alone

Two `200` responses can still expose different data. Two `403` responses can still originate from two different layers.

For sensitive endpoints, also compare:

- Response bodies and returned fields.
- Service/repository invocations.
- Side effects.
- Tenant filters in queries.
- Audit events.
- Rate-limit behavior.
- `WWW-Authenticate`.
- Stable API error codes.

## 19. Configuring Shared Test Tokens

To run contract tests against both stacks, build reusable token fixtures:

~~~text
Test signing key pair
       |
       +--> JWT valid: issuer A, audience orders-api, scope read
       |
       +--> JWT valid: issuer A, audience orders-api, scope write
       |
       +--> JWT wrong issuer
       |
       +--> JWT wrong audience
       |
       +--> JWT expired
       |
       +--> JWT signed by another key
       |
       +--> JWT wrong typ/profile
       |
       +--> JWT with disallowed alg
~~~

Fixtures must be signed with a private test key. The test public key/JWKS is consumed by both Servlet `JwtDecoder` and WebFlux `ReactiveJwtDecoder`.

### 19.1. Sharing the Same Issuer/Audience Validator Contract

Where possible, place shared policy constants and test fixtures in a module independent of Servlet/WebFlux:

~~~java
public final class OrdersTokenPolicy {
    public static final String ISSUER =
        "https://idp.test.example";

    public static final String AUDIENCE =
        "orders-api";

    public static final String READ_SCOPE =
        "SCOPE_orders.read";

    public static final String WRITE_SCOPE =
        "SCOPE_orders.write";

    private OrdersTokenPolicy() {
    }
}
~~~

You do not need to share the exact same decoder implementation; Servlet and WebFlux require different decoder types. You can share constants, expected outcomes, key fixtures, and contract tests.

### 19.2. Avoiding Policy Drift

If the same issuer URL is hardcoded in two config files, they can drift apart when changing environments. Use externalized configuration and verify profile binding so both stacks receive identical trust metadata.

However, do not share one property if Servlet and WebFlux genuinely have different trust boundaries. When policies differ, document that as an intentional change rather than a migration bug.

## 20. Error Handling Parity

### 20.1. Authentication Failure

Cases typically returning `401`:

- Missing token.
- Malformed bearer token.
- Invalid JWT signature.
- Issuer/audience/type validation failure.
- Inactive opaque token.

WebFlux must preserve the Bearer challenge. Never let a custom `ServerAuthenticationEntryPoint` omit the `WWW-Authenticate` header.

### 20.2. Authorization Failure

Cases typically returning `403`:

- Missing scope.
- Missing role.
- Method security denial.
- Tenant/ownership policy denial (or `404` per anti-enumeration contract).

Use `ServerAccessDeniedHandler` for reactive paths. Never use Servlet `AccessDeniedHandler`.

### 20.3. Dependency Outage

If the JWKS or introspection endpoint times out:

- Do not create an authenticated principal.
- Do not treat a timeout as a valid token.
- Do not retry indefinitely.
- Distinguish invalid tokens from dependency failures in metrics/logs.
- The public HTTP status per API contract may be `401` or `503` depending on error classification; failing closed is mandatory.

If the Servlet version has custom error mapping for dependency outages, the WebFlux version needs matching mapping and confirming tests.

## 21. CORS and `WWW-Authenticate` in Browser Clients

If the frontend needs to distinguish a missing token from an invalid token, it may need to read `WWW-Authenticate`. In CORS configuration:

~~~java
configuration.setExposedHeaders(
    List.of("WWW-Authenticate")
);
~~~

Without exposing the header, browser JavaScript may be unable to read it even though the server sent it.

This is a commonly overlooked parity issue: Servlet and WebFlux might both return `401`, yet the browser sees different headers due to non-equivalent CORS configs.

## 22. Post-Migration Observability and Operations

Monitor both applications in staging:

| Metric | Purpose |
|---|---|
| 401 rate | Authentication failures |
| 403 rate | Authorization denials |
| JWT decoder latency | Verification overhead |
| JWKS fetch count/duration | Key retrieval |
| Unknown `kid` | Key rotation or anomalous input |
| Introspection latency | AS dependency |
| 5xx/timeout | Identity provider availability |
| Request p95/p99 | Overall API latency |
| Active WebFlux connections | Reactive server load |
| Thread/event-loop saturation | Blocking code or CPU pressure |
| Memory/connection pool | Resource utilization |
| Tenant authorization denials | Business policy behavior |

Metric names depend on Micrometer/instrumentation; the table lists groups to observe rather than claiming every metric exists automatically.

### 22.1. Detecting Blocking in the Reactive Path

A WebFlux version can have the exact right policy yet suffer poor performance if it calls JDBC/blocking HTTP on the event loop. Check:

- Is `.block()` called in any controller/service/filter?
- Are there nested `.subscribe()` calls inside services?
- Is a synchronous Servlet `JwtDecoder` used on a reactive request path?
- Is a blocking introspection client invoked on the event loop?
- Is CPU-heavy work running with unbounded concurrency?
- Is an appropriate Reactor scheduler used at unavoidable blocking boundaries?

Switching to WebFlux does not automatically make all dependencies non-blocking.

## 23. Controlled Migration Roadmap

**Step 1 — Document Servlet policy.** Inventory issuer, JWKS, algorithms, audience, token profile, routes, authorities, session, CSRF, CORS, errors, and business rules.

**Step 2 — Create the reactive application slice.** Add WebFlux dependencies and confirm the application type is truly reactive.

**Step 3 — Create `SecurityWebFilterChain`.** Port request matchers to `authorizeExchange` and preserve public/private/method rules.

**Step 4 — Port the decoder.** Use `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector`, preserving issuer/audience/algorithm/type/active checks.

**Step 5 — Port authority mapping.** Keep the same claim sources and prefixes; verify identical authority sets.

**Step 6 — Port session/CSRF/CORS.** Use `ServerSecurityContextRepository` and a reactive CORS source matching the credential model.

**Step 7 — Port principal/services.** Replace `ThreadLocal` access with Reactor Context; eliminate blocking calls and nested subscriptions.

**Step 8 — Port method security.** Use `@EnableReactiveMethodSecurity` and publisher-returning methods.

**Step 9 — Write parity tests.** Run the same token fixtures and request matrix through both Servlet and WebFlux.

**Step 10 — Compare in staging.** Compare status codes, headers, response payloads, side effects, tenant filters, latency, and dependency calls.

**Step 11 — Controlled rollout.** Use shadow/canary traffic if architecture allows, monitor `401`/`403` rates, and roll back on policy drift.

## 24. Common Migration Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| WebFlux accepts token but scopes are missing | Reactive converter differs from Servlet converter | Compare authority mapping |
| JWT valid in Servlet but `401` in WebFlux | Different JWKS URI, issuer, audience, algorithm, or clock skew | Compare decoder validators |
| ID token passes one stack but is rejected in the other | Inconsistent token-type validation | Align token profiles |
| Public route works in Servlet but `401` in WebFlux | Chain matcher/order or invalid Bearer header | Inspect WebFilter chains and resolver |
| Private route exposed in WebFlux | Missing `anyExchange().denyAll()` or chain mismatch | Add fallback policy |
| `POST` always returns `403` | CSRF still enabled in WebFlux or missing CSRF token | Verify credential model and CSRF policy |
| Browser cannot read `WWW-Authenticate` | CORS does not expose the header | Add to exposed headers |
| Principal present in controller but empty in service | Service creates an independent subscription or uses `ThreadLocal` | Use `ReactiveSecurityContextHolder` in the same chain |
| Requests slow despite WebFlux | Blocking I/O on the event loop | Use reactive client/repository or proper scheduler |
| Opaque tokens spike AS load | Frequent introspection calls, different cache/timeout | Compare introspector policies |
| Wrong decoder selected under multi-issuer | Different resolver/issuer mapping | Use a trusted issuer registry |
| `403` instead of `401` | Different authentication/authorization handlers or decoder behavior | Compare failure paths |
| Security context persists unexpectedly | Different repository/session policy | Check `ServerSecurityContextRepository` |
| Tests pass yet signatures are unverified | Using `mockJwt()` | Send signed Bearer tokens through a real decoder |

## 25. Parity Checklist Before Shifting Traffic

### Token Trust

- [ ] Canonical issuer matches the Servlet version.
- [ ] JWKS URI is accurate and trusted.
- [ ] Algorithm allowlist is identical.
- [ ] Signature verification is active.
- [ ] `exp`, `nbf`, and clock skew policies match.
- [ ] Audience/resource validation matches.
- [ ] Token type/profile validation matches.
- [ ] JWT and opaque token modes align with the contract.
- [ ] Introspection `active=false` is rejected.
- [ ] Multi-issuer trust allowlist matches if applicable.

### HTTP Authorization

- [ ] Public routes match.
- [ ] Private routes match.
- [ ] `GET`/`POST`/`PUT`/`DELETE` scope rules match.
- [ ] Role/authority prefixes match.
- [ ] Unknown routes are denied.
- [ ] Chain matchers and ordering are verified.
- [ ] `401`/`403` semantics match.
- [ ] `WWW-Authenticate` is preserved.
- [ ] CORS origins/methods/headers/exposed headers match.
- [ ] CSRF policy reflects the same credential model.

### Principal and Business Policy

- [ ] Subject/issuer mapping matches.
- [ ] JWT and opaque principals are handled properly.
- [ ] Tenant context comes from verified claims or a trusted store.
- [ ] Object ownership checks match.
- [ ] Method security is enabled on the reactive stack.
- [ ] No `ThreadLocal` or mutable current-user fields remain.
- [ ] No blocking calls or nested `subscribe()` in reactive paths.

### Testing and Operations

- [ ] Identical token fixtures run against both stacks.
- [ ] Signed JWT tests verify real signatures.
- [ ] Wrong issuer/audience/type/algorithm are all rejected.
- [ ] Opaque active/inactive and timeouts are tested.
- [ ] CSRF/CORS/preflight are tested.
- [ ] Multi-chain routing is tested.
- [ ] Service side effects on denied requests are checked.
- [ ] Staging metrics and latency are compared.
- [ ] Rollback plan is ready.

## 26. Self-Check Questions

**1.** Which Servlet API does `ServerHttpSecurity` replace in WebFlux?

> `HttpSecurity`.

**2.** What replaces `SecurityFilterChain`?

> `SecurityWebFilterChain`.

**3.** What replaces `JwtDecoder`?

> `ReactiveJwtDecoder`.

**4.** What replaces `OpaqueTokenIntrospector`?

> `ReactiveOpaqueTokenIntrospector`.

**5.** What replaces `authorizeHttpRequests`?

> `authorizeExchange`.

**6.** Why not use `SecurityContextHolder` in WebFlux?

> Because WebFlux propagates the security context via Reactor Context per subscription, rather than relying on `ThreadLocal` as Servlet does by default.

**7.** What does a WebFlux stateless API use instead of `SessionCreationPolicy.STATELESS`?

> You can use `NoOpServerSecurityContextRepository` for the chain's security context.

**8.** Can the same Servlet `JwtDecoder` be used in WebFlux?

> No. WebFlux requires `ReactiveJwtDecoder`.

**9.** Does `mockJwt()` verify real signatures?

> No. It creates a mock authentication; to test signature verification, send a signed Bearer token through a real decoder.

**10.** Which test helper does an opaque token in WebFlux use for authorization?

> `mockOpaqueToken()`, though this helper does not call the introspection endpoint.

**11.** What is needed to test the real introspection pipeline?

> Send a Bearer header via `WebTestClient` and configure a real reactive introspector pointing to a test AS or HTTP stub.

**12.** Why is having the same scope string not enough to guarantee parity?

> Because issuer, audience, token type, converters, and route matchers also affect decisions.

**13.** Why does `permitAll()` not necessarily skip a malformed Bearer token?

> The authentication `WebFilter` may process the supplied credential prior to the authorization step.

**14.** Which annotation does WebFlux method security require?

> `@EnableReactiveMethodSecurity`.

**15.** Why must a service not call `block()` to retrieve the principal?

> It introduces a blocking boundary and can break reactive execution semantics/context.

**16.** When customizing a WebFlux decoder, which validators must be retained?

> Signature/algorithm policy, issuer, timestamps, audience, and token profile per contract.

**17.** Why test CORS `WWW-Authenticate` exposure?

> Browser JavaScript can only read response headers exposed by CORS.

**18.** What proves the migration preserved parity?

> The same token fixtures and request scenarios produce the same authentication/authorization outcomes, response contracts, and business side effects across both stacks.

## 27. References

- [Spring Security — Reactive Applications](https://docs.spring.io/spring-security/reference/reactive/index.html): WebFlux Security architecture and `SecurityWebFilterChain`.
- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder`, issuer, JWKS, and JWT authentication.
- [Spring Security — Reactive OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector` and opaque authentication.
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html): `authorizeExchange` and reactive authorization.
- [Spring Security — Reactive Method Security](https://docs.spring.io/spring-security/reference/reactive/authorization/method.html): `@EnableReactiveMethodSecurity` and publisher-returning methods.
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html): testing WebFlux Security.
- [Spring Security — Testing OAuth 2.0 with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()`, `mockOpaqueToken()`, and test helpers.
- [Spring Security — ReactiveSecurityContextHolder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/core/context/ReactiveSecurityContextHolder.html): accessing `SecurityContext` in Reactor Context.
- [Spring Security — ServerSecurityContextRepository API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/context/ServerSecurityContextRepository.html): saving/loading context in a reactive server.
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html): reactive web integration tests.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): `@SpringBootTest` and test auto-configuration.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer transport, `401`/`403`, and `WWW-Authenticate`.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access-token profile, issuer/audience/type/signature validation.

**Conclusion:** A WebFlux counterpart equivalent to Servlet must preserve the same trust policies and access decisions while moving to reactive security APIs. Use `SecurityWebFilterChain`, `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector`, preserve issuer/audience/algorithm/type validation, port matchers to `authorizeExchange`, use `ServerSecurityContextRepository` for session policy, and read the principal via Reactor Context. Verify parity by running the same token fixtures and request matrix across both stacks; compare status codes, headers, response data, and business side effects before shifting traffic.
