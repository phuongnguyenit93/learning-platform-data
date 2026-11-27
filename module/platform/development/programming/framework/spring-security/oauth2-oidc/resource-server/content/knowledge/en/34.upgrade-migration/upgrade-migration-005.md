# Differences Between Explicit Bean Configuration and Auto-Configuration

When building a **Spring Security OAuth 2.0/OIDC Resource Server**, an application can be configured via Spring Boot properties, explicit `@Bean` definitions, or a combination of both. The key point is that Spring Boot does not flip a single "automatic" mode switch off globally the moment you write Java configuration. A Resource Server consists of multiple independent components, and each component follows its own replacement rules.

For a Servlet Resource Server using JWTs, the main components are:

- `SecurityFilterChain`: determines which requests go through Spring Security, how Bearer tokens are authenticated, and the authorization policy.
- `JwtDecoder`: parses, verifies signatures, and validates JWT claims.
- `JwtAuthenticationConverter`: converts a verified `Jwt` into an `Authentication` and authorities.

For opaque tokens, `JwtDecoder` is replaced by:

- `OpaqueTokenIntrospector`: calls the introspection endpoint, checks whether the token has `active=true`, and builds the principal/attributes.

Spring Boot can auto-configure the security chain and decoder/introspector from properties. When an application declares its own Bean, Boot typically **backs off only for the exact Bean type that was replaced**. Other components can continue to be auto-configured.

> **Core principle:** `SecurityFilterChain`, `JwtDecoder`, and `OpaqueTokenIntrospector` are independent extension points. Adding one explicit Bean does not make all Resource Server auto-configuration disappear. You must know precisely which default Bean is being replaced and which responsibilities the application must now own.

This lesson focuses on Spring Boot and Spring Security Servlet Resource Servers while pointing out the corresponding APIs in WebFlux. Examples use Java and YAML. API names, properties, and auto-configuration conditions should be verified against your project's actual Spring Boot/Spring Security BOM.

## 1. The Two Approaches and Their Roles

### 1.1. Auto-Configuration via Properties

Declare issuer information and basic policy:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

Spring Boot reads the properties and creates the appropriate Resource Server components when required dependencies are present and no explicit Bean replaces them.

For JWT, the overall flow:

~~~text
application.yml
      |
      v
Spring Boot Resource Server auto-configuration
      |
      +--> Default SecurityFilterChain
      |
      +--> Default JwtDecoder
                |
                +--> issuer metadata / JWKS
                +--> signature validation
                +--> issuer / time / audience validation
      |
      v
Bearer token request
      |
      v
Authentication + authorization
~~~

Advantages:

- Minimal code and easy to read.
- Properties split cleanly across profiles/environments.
- Spring Security defaults are applied consistently.
- Configuration changes are easy to verify across deployments without editing Java code.
- Fits well when issuer, JWKS, audience, and scope mapping follow standard conventions.

Limitations:

- When you need multiple decoders, multiple issuers, custom HTTP clients, specialized validation, or non-standard principal mapping, properties may not suffice.
- The default security chain is only a baseline configuration. It does not know which business endpoints are public or which endpoints require distinct read/write scopes.
- When an application defines its own replacement Bean, properties targeting that Bean do not necessarily continue to apply.

### 1.2. Explicit Bean Configuration

The application explicitly declares the component it wants to customize:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .requestMatchers(HttpMethod.POST, "/api/orders/**")
                .hasAuthority("SCOPE_orders.write")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

This Bean describes the security chain and authorization rules. If the application still declares `issuer-uri`, `audiences`, and algorithm policy in properties, Boot's auto-configured decoder can still be used.

You can also declare a decoder explicitly:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    // Decoder constructed by the application
}
~~~

In that case, the application is responsible for ensuring the decoder performs all required verification steps.

Advantages:

- Fine-grained control over the filter chain, matchers, authorization, and exception handling.
- Ability to add custom validators, converters, HTTP clients, caches, or key sources.
- Ability to configure multiple security chains or multiple issuers.
- Easy integration of domain-specific policies.

Costs:

- More code.
- Easy to accidentally omit issuer/audience/timestamp validation.
- Can lose defaults Boot previously supplied.
- Requires more thorough testing since the application owns more configuration responsibilities.

### 1.3. Quick Comparison

| Criterion | Auto-Configuration | Explicit Bean |
|---|---|---|
| Primary configuration source | `application.yml` / properties | Java/Kotlin `@Configuration` |
| Security chain | Boot creates a default chain if no other chain exists | Application defines `SecurityFilterChain` |
| JWT decoder | Boot creates from issuer/JWKS properties if no replacement decoder exists | Application builds or passes decoder into DSL |
| Opaque introspector | Boot creates from introspection properties if no replacement introspector exists | Application builds or passes introspector into DSL |
| Authorization rules | Requires `authenticated` by default | Custom matchers and permissions |
| Custom validation | Limited by supported properties/APIs | Can combine multiple `OAuth2TokenValidator` instances |
| Custom authority mapping | Can use a converter via DSL/Bean as appropriate | Can configure converter explicitly |
| Complexity | Low | Higher |
| Responsibility for preserving validation | Mostly handled by Boot/Security standard configuration | Application must verify when replacing decoder/introspector |

## 2. Auto-Configuration Is Not a Single Monolith

A misconception that leads to bugs is: "Once a `SecurityFilterChain` is declared, Spring Boot stops configuring Resource Server." That is incorrect.

For a Servlet JWT Resource Server, distinguish at least two Beans:

1. `SecurityFilterChain`: configures HTTP security and enables JWT Resource Server.
2. `JwtDecoder`: verifies and decodes token strings.

For opaque tokens, the corresponding pair is:

1. `SecurityFilterChain`.
2. `OpaqueTokenIntrospector`.

These components have independent replacement conditions.

### 2.1. Bean Matrix and Back-Off Behavior

| Bean Declared by Application | Default Bean Replaced / Backs Off | Other Components |
|---|---|---|
| `SecurityFilterChain` | Boot's default security chain | `JwtDecoder` or `OpaqueTokenIntrospector` can still be created by Boot |
| `JwtDecoder` | Boot's default decoder | Boot's default security chain can still be created |
| `OpaqueTokenIntrospector` | Boot's default introspector | Boot's default security chain can still be created |
| `SecurityFilterChain` + `JwtDecoder` | Both default chain and default decoder | Application controls both HTTP policy and JWT validation |
| `SecurityFilterChain` + `OpaqueTokenIntrospector` | Both default chain and default introspector | Application controls both HTTP policy and introspection |

Practical rules to remember:

- Once you define your own `SecurityFilterChain`, you no longer rely on Boot's default chain to protect routes.
- Once you define your own `JwtDecoder`, do not expect it to automatically pick up all properties Boot used for the default decoder.
- Once you define your own `OpaqueTokenIntrospector`, do not expect Boot's endpoint/credentials properties to be wired into your custom introspector automatically.
- Beans that are not replaced can continue to be auto-configured.

### 2.2. Configuring the Chain and the Decoder Are Separate Responsibilities

For example, the application declares:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

This Bean replaces the default chain. However, `.jwt(Customizer.withDefaults())` still expects the JWT Resource Server to operate using a suitable decoder in the application context. Without a custom `JwtDecoder`, Boot can still supply a decoder built from properties.

Conversely, if the application declares only a `JwtDecoder` Bean without a `SecurityFilterChain`, Boot's default chain can still be created and invoke that custom decoder.

### 2.3. Do Not Confuse a Custom Bean with DSL Customization

There are two ways to supply a decoder to a chain:

**Using a decoder from the application context:**

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
)
~~~

This lets Spring Security use the decoder configured in the context, whether it is Boot's auto-configured decoder or a `JwtDecoder` Bean supplied by the application.

**Passing a decoder directly into the DSL:**

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(jwt -> jwt.decoder(myCustomDecoder))
)
~~~

The second approach overrides which decoder the chain uses. When passing a decoder directly, do not assume Boot's properties for creating the default decoder apply to the passed instance.

## 3. Case 1: Properties Only

This is the simplest option when the application uses a single issuer and JWT access tokens following standard conventions.

### 3.1. Dependencies

With Spring Boot, use the starters:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The starters and BOM manage the corresponding Spring Security modules. When managing dependencies manually outside Spring Boot, JWT support requires both the Resource Server module and the JOSE module to decode/verify JWTs.

### 3.2. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
~~~

Meaning:

- `issuer-uri`: the issuer identifier that must match the `iss` claim in the JWT.
- `audiences`: audiences accepted by the API.
- `jws-algorithms`: allowed signing algorithms.

When the appropriate dependencies and properties are present, Boot/Spring Security auto-configures the default decoder and security chain.

### 3.3. What Does the Default Security Chain Mean?

Conceptually, the default configuration is equivalent to:

~~~java
@Bean
SecurityFilterChain filterChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}
~~~

This means requests must be authenticated. It does not express public routes, read/write scopes, admin privileges, or object ownership.

For a production API, a dedicated `SecurityFilterChain` is normally needed to express authorization clearly, while still letting Boot build the decoder from properties.

### 3.4. Discovery and When the Authorization Server Is Called

With `issuer-uri`, Spring Security can use Provider Configuration or Authorization Server Metadata to locate the JWKS URI. According to current Spring Security documentation, discovery is deferred until the first request carrying a JWT in the relevant configurations. This avoids making startup immediately dependent on Authorization Server reachability.

If the Authorization Server does not support discovery, or the Resource Server needs an explicit JWKS URI:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          jwk-set-uri: https://keys.internal.example/realms/shop/jwks
          audiences:
            - orders-api
~~~

When both `issuer-uri` and `jwk-set-uri` are configured via properties, the Resource Server can fetch keys directly from the JWKS URI while still validating the `iss` claim.

Do not guess a JWKS URI by concatenating strings onto the issuer. Use the endpoint published or confirmed by the Authorization Server.

## 4. Case 2: Declaring `SecurityFilterChain`, Keeping the Auto-Configured Decoder

This is the most common combination: the application needs custom authorization rules without needing to write its own decoder.

### 4.1. Properties Still Manage Issuer and Audience

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
~~~

### 4.2. Explicit `SecurityFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration(proxyBeanMethods = false)
public class ApiSecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
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

Here:

- `SecurityFilterChain` is a Bean owned by the application.
- Boot's default chain backs off.
- `JwtDecoder` can still be created by Boot from `issuer-uri`, `audiences`, and `jws-algorithms`.
- `.jwt(Customizer.withDefaults())` uses the decoder available in the application context.
- Authorization rules are defined by the application.

This is a clear example of combining explicit Beans with auto-configuration.

### 4.3. What You Own When Replacing the Chain

Once a custom chain is registered, do not assume default rules remain in place. The application must define:

- Which routes are public.
- Which routes require authentication.
- Which scopes/roles protect each HTTP method.
- How unmatched requests are handled.
- Whether CSRF should be enabled or disabled based on the credential model.
- How CORS is configured.
- Whether the session policy fits the API.
- Whether exception handling and `WWW-Authenticate` match the contract.
- Whether the chain matcher covers the intended routes.

If an API uses Bearer tokens in the `Authorization` header and does not rely on browser-attached cookies, evaluate an appropriate stateless session and CSRF policy. Do not disable CSRF merely because the token is a JWT.

## 5. Case 3: Declaring Only a `JwtDecoder` Bean

An application may need a custom decoder while keeping Boot's default security chain.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
public class JwtDecoderConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.issuer}") String issuer,
            @Value("${app.security.jwk-set-uri}") String jwkSetUri) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(
            JwtValidators.createDefaultWithIssuer(issuer)
        );

        return decoder;
    }
}
~~~

Dedicated decoder properties:

~~~yaml
app:
  security:
    issuer: https://login.example.com/realms/shop
    jwk-set-uri: https://keys.internal.example/realms/shop/jwks
~~~

In this case:

- Boot's default `JwtDecoder` Bean is replaced.
- Boot's default `SecurityFilterChain` can still be created.
- The default chain enables JWT Resource Server and uses the custom decoder in the context.

### 5.1. Custom Decoders Must Preserve Required Validations

When constructing a `JwtDecoder` manually, ensure:

- Signatures are verified with the right public key.
- Algorithms belong to an allowlist.
- The issuer is accurate.
- `exp` and `nbf` are checked.
- The audience contains the API's resource identifier.
- Token profile/type matches the contract if required by the system.
- Clock skew is chosen per policy.
- Claim mapping does not alter the meaning of security claims.

The example above preserves default issuer and timestamp validators via `JwtValidators.createDefaultWithIssuer(issuer)`. It does not yet add an audience validator; if the API requires an audience, add it explicitly.

### 5.2. Custom Decoders Do Not Automatically Inherit Boot Properties

This is a common configuration mistake.

Suppose previously you had:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
~~~

Then the team declares `@Bean JwtDecoder`. Boot backs off from creating the default decoder. Do not assume the custom Bean automatically picks up `audiences` and `jws-algorithms` from Boot the way the auto-configured decoder did.

If the custom decoder checks only signature and issuer, the API can silently lose its intended audience validation or algorithm restriction.

### 5.3. Adding an Audience Validator

Example validator:

~~~java
public final class OrdersAudienceValidator
        implements OAuth2TokenValidator<Jwt> {

    private final String requiredAudience;

    public OrdersAudienceValidator(String requiredAudience) {
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2TokenValidatorResult validate(Jwt jwt) {
        if (jwt.getAudience().contains(this.requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        );

        return OAuth2TokenValidatorResult.failure(error);
    }
}
~~~

Combine with issuer and timestamp validators:

~~~java
@Bean
JwtDecoder jwtDecoder(
        @Value("${app.security.issuer}") String issuer,
        @Value("${app.security.jwk-set-uri}") String jwkSetUri,
        @Value("${app.security.audience}") String audience) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwkSetUri)
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audienceValidator =
        new OrdersAudienceValidator(audience);

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            defaults,
            audienceValidator
        )
    );

    return decoder;
}
~~~

Main imports:

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
~~~

This snippet illustrates composing validators. If your application uses RFC 9068, a custom `typ`, multi-issuer, or other policies, use the corresponding validators and test tokens with invalid profiles.

## 6. Case 4: Replacing the Decoder Directly in the DSL

Spring Security offers multiple levels of customization under `oauth2ResourceServer().jwt()`.

### 6.1. Using `jwkSetUri()`

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwkSetUri("https://keys.internal.example/realms/shop/jwks")
            )
        )
        .build();
}
~~~

`jwkSetUri()` in the DSL takes precedence over a JWK Set URI configured via properties.

Use this when you need to override the JWKS endpoint at the chain level. However, explicitly verify issuer validation and other validators in the resulting configuration. Do not simply swap the URI and assume every property-based validator is retained across all versions/wiring styles.

If you want to skip metadata discovery while keeping property-based issuer validation, setting both `issuer-uri` and `jwk-set-uri` in properties is explicit and clear.

### 6.2. Using `decoder()`

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    JwtDecoder decoder = createOrdersJwtDecoder();

    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.decoder(decoder))
        )
        .build();
}
~~~

`decoder()` sets the decoder used by the DSL and can replace Boot's auto-configured decoder for that chain.

Suitable when you need:

- Custom algorithm allowlists.
- Custom `OAuth2TokenValidator` implementations.
- Custom JWK sources/caches/HTTP clients.
- Multiple issuers or decoder routing.
- Claim-set conversion.
- Token profile validation.
- A decoder initialized by a separate security module.

Because the decoder is supplied directly, the application must verify its validators and key source. Do not expect `spring.security.oauth2.resourceserver.jwt.*` properties to be merged into that object automatically.

### 6.3. Replacing the Converter Does Not Replace the Decoder

Custom authority mapping example:

~~~java
@Bean
JwtAuthenticationConverter jwtAuthenticationConverter() {
    JwtGrantedAuthoritiesConverter authorities =
        new JwtGrantedAuthoritiesConverter();

    authorities.setAuthoritiesClaimName("permissions");
    authorities.setAuthorityPrefix("SCOPE_");

    JwtAuthenticationConverter converter =
        new JwtAuthenticationConverter();

    converter.setJwtGrantedAuthoritiesConverter(authorities);

    return converter;
}
~~~

Attach the converter to the chain:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtAuthenticationConverter jwtAuthenticationConverter)
        throws Exception {

    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt
                .jwtAuthenticationConverter(jwtAuthenticationConverter)
            )
        )
        .build();
}
~~~

The converter only changes how a verified `Jwt` maps to authorities/`Authentication`. It does not alter:

- JWKS URI.
- Signature verification.
- Issuer validation.
- Timestamp validation.
- Audience validation.

If you only need to change which claim holds permissions, keep the default decoder and replace only the converter. There is no need to create a new `JwtDecoder` just to map authorities.

## 7. Opaque Tokens: Auto-Config and Explicit Beans

Opaque tokens use introspection instead of JWT signature verification on the Resource Server.

### 7.1. Properties Only

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

Spring Boot/Spring Security can auto-configure:

- Default `SecurityFilterChain` with opaque token support.
- `OpaqueTokenIntrospector` using the introspection URI and credentials.
- Scope-to-authority mapping with the `SCOPE_` prefix.

When a request sends a Bearer token, the introspector calls the endpoint and checks whether the response has `active=true`. The default principal is `OAuth2AuthenticatedPrincipal`; `Authentication` is typically `BearerTokenAuthentication`.

### 7.2. Custom Chain While Keeping the Auto-Configured Introspector

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        )
        .build();
}
~~~

If no replacement `OpaqueTokenIntrospector` Bean is declared, the introspection properties can still be used to create the default introspector.

### 7.3. Declaring an `OpaqueTokenIntrospector` Bean

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        @Value("${app.security.introspection-uri}") String uri,
        @Value("${app.security.client-id}") String clientId,
        @Value("${app.security.client-secret}") String clientSecret) {

    return SpringOpaqueTokenIntrospector
        .withIntrospectionUri(uri)
        .clientId(clientId)
        .clientSecret(clientSecret)
        .build();
}
~~~

A custom Bean replaces Boot's default introspector.

If a custom chain calls:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(Customizer.withDefaults())
)
~~~

the configuration uses the corresponding introspector in the context.

When creating an introspector manually, the application must ensure:

- The introspection URI matches the environment.
- Client authentication uses the right method and credentials.
- TLS is verified.
- Timeout/connect/read policies are appropriate.
- `active=false` is rejected.
- Scopes/attributes are mapped accurately.
- Audience/resource and issuer are verified per the AS contract.
- Network errors are never treated as active tokens.

### 7.4. Overriding URI and Credentials in the DSL

You can configure directly:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspectionUri("https://login.example.com/oauth2/introspect")
        .introspectionClientCredentials(
            "orders-resource-server",
            introspectionClientSecret
        )
    )
)
~~~

`introspectionUri()` and `introspectionClientCredentials()` in the DSL override property values.

### 7.5. Passing a Custom Introspector in the DSL

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspector(customIntrospector)
    )
)
~~~

`introspector()` replaces the auto-configured introspector. This is useful when you need a decorator, caching, a custom HTTP client, response adaptation, or additional attribute validation.

Avoid configuring the same setting ambiguously across multiple places. Make clear whether the URI/credentials live in properties, a Bean, or the DSL, and inspect the actual object used by the chain.

## 8. Comparing Replacement Levels for JWT and Opaque Tokens

| Need | JWT | Opaque Token |
|---|---|---|
| Configure endpoint via properties only | `issuer-uri`, `jwk-set-uri` | `introspection-uri`, `client-id`, `client-secret` |
| Customize routes/authorization | Declare `SecurityFilterChain` | Declare `SecurityFilterChain` |
| Customize token verification | `JwtDecoder` Bean or `.decoder()` | `OpaqueTokenIntrospector` Bean or `.introspector()` |
| Change key/endpoint source | `.jwkSetUri()` or properties | `.introspectionUri()` |
| Change credentials | Usually involves key source/HTTP client | `.introspectionClientCredentials()` |
| Change authority mapping | `JwtAuthenticationConverter` | `OpaqueTokenAuthenticationConverter` or authority mapping in introspector |
| Check issuer/audience | JWT validators | Based on introspection response and contract |
| Verify token | Signature + claims | AS returns `active=true` and attributes |

JWT and opaque tokens can both use the Bearer scheme at the HTTP layer, yet their verification components differ. Never pass a `JwtDecoder` into an opaque configurer or an `OpaqueTokenIntrospector` into a JWT configurer.

## 9. WebFlux: Same Principles, Different Bean Types

For WebFlux, the corresponding Bean types are:

| Servlet | WebFlux |
|---|---|
| `SecurityFilterChain` | `SecurityWebFilterChain` |
| `HttpSecurity` | `ServerHttpSecurity` |
| `JwtDecoder` | `ReactiveJwtDecoder` |
| `OpaqueTokenIntrospector` | `ReactiveOpaqueTokenIntrospector` |
| `JwtAuthenticationProvider` | Reactive authentication manager/provider path |
| `MockMvc` | `WebTestClient` |

Spring Boot can auto-configure a default `SecurityWebFilterChain` and reactive decoders/introspectors. When an application declares explicit reactive Beans, the same back-off rules apply per Bean type.

### 9.1. Properties for a Reactive JWT Resource Server

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/shop
          audiences:
            - orders-api
~~~

### 9.2. Explicit `SecurityWebFilterChain`

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http) {

    return http
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
~~~

If no replacement `ReactiveJwtDecoder` Bean is declared, Boot can still build the decoder from properties.

### 9.3. Explicit Reactive Decoder

~~~java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder(
        @Value("${app.security.issuer}") String issuer,
        @Value("${app.security.jwk-set-uri}") String jwkSetUri) {

    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri).build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

This is a reactive example; synchronous `JwtDecoder` cannot substitute for `ReactiveJwtDecoder`.

### 9.4. Reactive Opaque Introspector

When using opaque tokens in WebFlux, use `ReactiveOpaqueTokenIntrospector`. Do not put a synchronous introspector performing blocking network I/O onto the event loop by invoking it inside a reactive pipeline.

Properties and replacement principles are analogous to Servlet, but use the reactive APIs for your running Spring Security version.

## 10. Multiple `SecurityFilterChain` Beans: A Custom Chain Can Alter Overall Routing

Once at least one explicit `SecurityFilterChain` exists, do not rely on Boot's default chain to protect remaining routes. If the application needs multiple security zones, define each chain with explicit matchers and ordering.

Example:

~~~java
@Bean
@Order(1)
SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
    return http
        .securityMatcher("/api/**")
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/api/public/**").permitAll()
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(Customizer.withDefaults())
        )
        .build();
}

@Bean
@Order(2)
SecurityFilterChain browserChain(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/assets/**", "/login").permitAll()
            .anyRequest().authenticated()
        )
        .formLogin(Customizer.withDefaults())
        .build();
}
~~~

`FilterChainProxy` selects the first chain matching the request. Therefore:

- The `/api/**` chain must be ordered before the broad catch-all chain.
- The browser chain must not inadvertently receive API requests.
- Routes not matching specialized chains must have an explicit policy.
- Never allow sensitive routes to fall through to a chain with a weaker policy.
- If a fallback chain exists, configure `denyAll()` or explicit rules for the remainder.

A `JwtDecoder` Bean can be used by the JWT chain; the form-login chain does not need a decoder. Do not create a separate decoder just because another chain was added if trust policies and token validation are identical.

## 11. When to Use Properties vs. Dedicated Beans?

### 11.1. Use Properties Only When

- There is a single issuer or a simple Resource Server setup.
- JWTs use a standard JWKS endpoint.
- Audience and algorithm policies can be expressed via properties.
- Default timestamp/issuer validations satisfy the contract.
- Opaque tokens use a standard introspection URI and client credentials.
- Scope mapping follows the `SCOPE_` convention.
- No custom HTTP client or complex caching is required.

### 11.2. Customize Only `SecurityFilterChain` When

- Distinct public/private routes are needed.
- Rules by HTTP method and scope are needed.
- Multiple chains are needed for API, admin, and browser routes.
- Custom CORS, CSRF, sessions, or exception handling are needed.
- The default decoder/introspector still meets requirements.

In this case, keeping the auto-configured decoder/introspector is usually simple and safe.

### 11.3. Declare a Custom `JwtDecoder` When

- Complex validators or a specific token profile are required.
- Multiple issuers and distinct decoders are needed.
- A custom JWK source/HTTP client/cache is needed.
- A specialized algorithm policy is needed.
- Custom claim-set conversion is needed.
- Integration with custom key management or trust sources is needed.

### 11.4. Declare a Custom `OpaqueTokenIntrospector` When

- A custom HTTP client and timeouts are needed.
- Introspection caching aligned with a revocation SLA is needed.
- Additional validation for issuer/audience/tenant is needed.
- AS responses must be mapped to an internal principal.
- Metrics, tracing, or bounded retries are needed.
- Coordinating multiple introspection sources is needed.

### 11.5. Avoid Custom Beans Just to Change One Simple Value

If you only need to change the issuer or audience, prefer properties. If you only need to change authority mapping, replace the converter. If you only need to change the JWKS URI, use the appropriate property or DSL option.

A custom decoder shifts more validation responsibility onto the application. Never create a dedicated decoder just to change one attribute Boot already supports.

## 12. Key Differences When Migrating from Properties to Beans

Suppose the application originally had:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com
          audiences:
            - orders-api
          jws-algorithms:
            - RS256
~~~

Later, the team creates a decoder:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    return NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();
}
~~~

This can cause Boot to stop creating the default decoder. If the new decoder is not configured with issuer, audience, and algorithm policies, the application's security behavior has changed.

### 12.1. What to Check When Replacing the Decoder

| Previous Configuration | What to Check in Custom Decoder |
|---|---|
| `issuer-uri` | `iss` validator remains enabled |
| `audiences` | Audience validator remains present |
| `jws-algorithms` | Decoder allows only approved algorithms |
| Timestamp validation | `exp`, `nbf`, and clock skew are preserved |
| JWKS URI | Proper issuer/key source and TLS |
| JWKS cache | TTL, refresh, timeout, and eviction |
| Token type/profile | Profile-specific validator included if required |
| Custom claim conversion | Does not alter trust semantics |
| Error handling | Invalid tokens never fail open |

### 12.2. What to Check When Replacing the Chain

| Default Configuration | When Defining Custom `SecurityFilterChain` |
|---|---|
| Every request requires authentication | Write matchers and rules per route |
| JWT Resource Server | Enable `.oauth2ResourceServer().jwt(...)` |
| Default entry point | Keep or replace with protocol-compliant handler |
| CSRF/CORS defaults | Evaluate against credential model |
| Session behavior | Set stateless/stateful explicitly |
| Fallback behavior | Do not let requests fall into another chain |
| Scope mapping | Ensure authority prefix matches rules |

### 12.3. Break Migration Into Small Steps

A controllable workflow:

1. Document current properties and behavior.
2. Add the custom `SecurityFilterChain`, still calling `.jwt(Customizer.withDefaults())`.
3. Test public/private routes and scope rules.
4. Confirm the decoder is still Boot's auto-configured decoder.
5. Add a `JwtDecoder` Bean only if genuinely needed.
6. When adding the decoder, carry over all issuer/audience/algorithm/time/profile validators.
7. Test valid and invalid tokens.
8. Verify startup behavior and JWKS network calls.
9. Deploy to staging and compare authentication/authorization metrics.
10. Only after verification, remove unused properties.

## 13. Testing to Verify Which Beans Are Actually Active

Do not just check that the application starts. Verify actual runtime behavior and wiring.

### 13.1. Testing HTTP Authorization Through the Filter Chain

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class ResourceServerConfigurationTests {

    @Autowired
    MockMvc mvc;

    @Test
    void privateEndpointRequiresBearerToken() throws Exception {
        mvc.perform(get("/api/orders"))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointDoesNotRequireToken() throws Exception {
        mvc.perform(get("/api/public/health"))
            .andExpect(status().isOk());
    }
}
~~~

Tests must keep MockMvc filters enabled. Never use `@AutoConfigureMockMvc(addFilters = false)` when testing Spring Security.

### 13.2. Verifying Which Decoder Is Used

You can inspect the Bean in the application context:

~~~java
@Autowired
JwtDecoder jwtDecoder;
~~~

To prove the Bearer filter calls the intended decoder, send `Authorization: Bearer ...` through MockMvc using an appropriate test decoder or Mockito spy. Do not use `.with(jwt())` to test the decoder, because that request post-processor injects a mock authentication and bypasses the normal decoder.

### 13.3. Testing Signatures, Issuer, and Audience

With a real decoder:

- Generate a test RSA key pair.
- Sign a JWT with the private test key.
- Configure test JWKS/public key.
- Send the token in a Bearer header.
- Confirm tokens with valid signature, issuer, and audience are accepted.
- Send a token signed by another key and confirm 401.
- Send tokens with wrong issuer/audience and confirm rejection.
- Confirm missing scopes result in 403 after authentication.

Never use production signing keys in tests.

### 13.4. Testing the Converter Separately from the Decoder

When replacing `JwtAuthenticationConverter`, construct tokens with claims per contract and check authorities after authentication.

Example:

~~~text
JWT claim:
  permissions = ["orders.read"]

Expected Authentication:
  SCOPE_orders.read
~~~

Converter unit tests can construct a `Jwt` directly. Integration tests need a real Bearer token to confirm the converter runs after the decoder.

### 13.5. Testing Opaque Introspection

Use an HTTP stub/test Authorization Server:

- `active=true` with required scopes.
- `active=false`.
- Missing scope.
- Invalid audience/resource per contract.
- Incorrect introspection client credentials.
- Timeout/5xx.
- Malformed response.

Send a Bearer header through the filter chain. Do not use `.with(opaqueToken())` when the goal is verifying the real introspector is invoked.

### 13.6. Testing Multiple `SecurityFilterChain` Beans

Create requests for each matcher:

| Request | Expected Chain | Outcome to Verify |
|---|---|---|
| `/api/orders` | API chain | Bearer authentication |
| `/api/public/health` | API chain | Permit all |
| `/login` | Browser chain | Login behavior |
| `/admin/reports` | Admin chain if present | Admin authorities |
| Route matching no specific chain | Fallback | Deny/authentication per policy |

Check `@Order` and matcher overlap. A broad chain placed ahead of a specialized chain can prevent the specialized chain from ever being selected.

### 13.7. Inspecting Auto-Configuration Conditions

When diagnosing why a default Bean did not appear:

- Start the application with `--debug` to view the condition evaluation report.
- Check which Beans of type `SecurityFilterChain`, `JwtDecoder`, or `OpaqueTokenIntrospector` exist in the application context.
- Confirm the active profile and verify properties bound properly.
- Check dependencies/classpath for Servlet vs. Reactive stack.
- Check whether any test configuration overrides production Beans.

If Actuator is enabled and the conditions endpoint is exposed securely, the condition report can aid investigation. Never expose sensitive configuration diagnostic endpoints to the public Internet.

## 14. Common Mistakes When Mixing Auto-Config and Explicit Beans

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| Custom chain exists but API rejects Bearer tokens | Chain does not call `oauth2ResourceServer` or matcher is wrong | Check chain and request matchers |
| Custom chain runs without a `JwtDecoder` | No valid properties and no decoder Bean | Check decoder creation conditions |
| Validly signed JWT with wrong issuer is accepted | Custom decoder omitted issuer validator | Check `JwtValidators` |
| Token for another API is accepted | Custom decoder lacks audience validator | Check `aud` |
| Unapproved algorithm is accepted | Custom decoder allowlist is too broad or unset | Check JWS algorithms |
| Scopes are not mapped | Converter reads wrong claim/prefix | Check `JwtAuthenticationConverter` |
| Opaque token is always inactive | Wrong introspection URI/credentials or response lacks `active=true` | Check introspector |
| Opaque token active but authorities missing | Wrong scope/attribute mapping | Check response and converter |
| Public route still demands a token | Wrong matcher/chain order or malformed Bearer token sent | Check filter chain |
| A route is unprotected | Custom chain fails to match and no fallback exists | Check chain coverage |
| App fails to start when AS is down after adding decoder Bean | Custom decoder runs eager discovery at Bean creation | Check discovery/JWKS initialization strategy |
| Properties changed but behavior did not | Custom Bean/DSL replaced the auto-configured component | Identify the source of truth |
| Two introspection calls for one request | Multiple chains/filters or a custom decorator calls twice | Check wiring and call paths |
| Reactive app fails with Bean type error | Used `JwtDecoder` instead of `ReactiveJwtDecoder` | Use proper reactive types |

## 15. Configurations to Avoid

### 15.1. Custom Chain Without Enabling Resource Server

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(authorize -> authorize
            .anyRequest().authenticated()
        )
        .build();
}
~~~

This chain requires authentication without configuring JWT/opaque Bearer support. The application may fall back to another authentication mechanism or reject requests without the intended Resource Server behavior.

If the API requires JWT:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
)
~~~

### 15.2. Custom Decoder That Only Parses Claims

Never Base64-decode a payload yourself and treat its claims as trusted. A decoder must verify signature, issuer, audience, timestamps, and token profile per policy.

### 15.3. Replacement Custom Decoder Missing Validators

A custom decoder Bean does not automatically inherit Boot's property-based validations. Configure validators inside the custom decoder explicitly.

### 15.4. Creating a New Decoder per Request

`JwtDecoder` is a shared component in the application context. Never instantiate a new decoder inside a controller/filter per request. Doing so can repeat discovery, create fresh caches, and overload JWKS endpoints.

### 15.5. Using One Bean Type for Two Different Trust Policies

If two issuers have different audiences, algorithms, or validators, do not force them into a single global decoder with overly permissive policies. Use an issuer-aware resolver and dedicated decoders per trust context.

### 15.6. Declaring Too Many Chains Without Matchers

A chain without a specific matcher can match broadly and shadow other chains. Use `securityMatcher`, `@Order`, and an explicit fallback policy.

### 15.7. Mixing Servlet and Reactive Beans

Do not use:

- `SecurityFilterChain` in WebFlux instead of `SecurityWebFilterChain`.
- `JwtDecoder` instead of `ReactiveJwtDecoder`.
- `OpaqueTokenIntrospector` instead of `ReactiveOpaqueTokenIntrospector`.
- `MockMvc` instead of `WebTestClient`.

Boot chooses the application type and corresponding auto-configuration. Bean types must match the active stack.

### 15.8. Keeping Secrets in Java Source

Never hard-code introspection client secrets inside `@Bean` methods. Use a secret manager, environment variables, or controlled externalized configuration.

### 15.9. Configuring the Same Value in Multiple Places

If the issuer/JWKS URI appears in YAML, a `@Value`, a `@Bean`, and hardcoded in the DSL, switching environments easily causes configuration drift. Choose one primary configuration source and avoid unnecessary overrides.

## 16. Pre-Selection Checklist

### When Using Auto-Configuration

- [ ] Correct Resource Server dependencies are present.
- [ ] `issuer-uri` or `jwk-set-uri` matches the environment.
- [ ] Audience is configured if required by the API.
- [ ] Algorithm allowlist matches the issuer.
- [ ] Introspection URI and credentials are valid if using opaque tokens.
- [ ] Default authorization policy suffices or is replaced by a tailored chain.
- [ ] No stray custom Bean accidentally causes auto-configuration to back off.
- [ ] Both valid and invalid tokens have been tested.

### When Declaring an Explicit `SecurityFilterChain`

- [ ] `.oauth2ResourceServer().jwt()` or `.opaqueToken()` is configured.
- [ ] Public/private routes are defined.
- [ ] Scope/authority rules are accurate.
- [ ] Matchers and `@Order` do not shadow each other.
- [ ] A fallback policy exists.
- [ ] CSRF/CORS/session policies fit the clients.
- [ ] Entry point and access-denied handler are appropriate.
- [ ] Default decoder/introspector remains in context if relying on auto-config.

### When Declaring an Explicit `JwtDecoder`

- [ ] JWKS URI/key source is trusted.
- [ ] Signatures are verified.
- [ ] Algorithm allowlist is explicit.
- [ ] Issuer validator is preserved.
- [ ] Timestamp validator is preserved.
- [ ] Audience validator is added.
- [ ] Token type/profile is validated if required.
- [ ] Caching/timeouts/rotation are accounted for.
- [ ] Not mistakenly relying on properties Boot no longer applies.
- [ ] Integration tests use real Bearer tokens.

### When Declaring an Explicit `OpaqueTokenIntrospector`

- [ ] Endpoint and client authentication are accurate.
- [ ] TLS and timeouts are configured.
- [ ] `active=false` is rejected.
- [ ] Scope/authority mapping is accurate.
- [ ] Audience/resource binding is checked per contract.
- [ ] Cache TTL meets revocation SLA.
- [ ] Does not fail open on AS errors.
- [ ] Tests confirm introspection is invoked.

## 17. Decision Path Based on Requirements

Start by asking: "Which piece actually needs to differ from the defaults?"

~~~text
Start with Resource Server
          |
          v
Only need issuer/JWKS/audience/scope conventions?
          |
      Yes | No
          |
          v
    Use properties
          |
          v
Need route rules, public paths, multiple chains?
          |
      Yes | No
          |
          v
Declare SecurityFilterChain
and keep default decoder/introspector
          |
          v
Need custom validation, key source,
HTTP client, cache, or token mapping?
          |
      Yes | No
          |
          v
Declare dedicated decoder/introspector
and preserve full security validations yourself
~~~

You do not have to walk every step. If properties suffice, do not add Java Beans. If only custom authorization is needed, a `SecurityFilterChain` is enough. Replace the decoder/introspector only when token verification requirements genuinely diverge from defaults.

## 18. Self-Check Questions

**1.** What are the main components of Spring Boot Resource Server auto-configuration?

> For JWT, the default `SecurityFilterChain` and `JwtDecoder`; for opaque tokens, the default `SecurityFilterChain` and `OpaqueTokenIntrospector`.

**2.** When declaring a custom `SecurityFilterChain`, does the default `JwtDecoder` automatically disappear?

> No. Boot's default chain backs off; Boot can still create the decoder unless the application provides another decoder.

**3.** When declaring a custom `JwtDecoder` Bean, can the default security chain still exist?

> Yes. The two Beans have independent replacement conditions.

**4.** What does `.jwt(Customizer.withDefaults())` mean?

> Enable JWT Resource Server on the chain and use the matching decoder available in the application context.

**5.** How do `.jwkSetUri()` and `.decoder()` differ?

> `jwkSetUri()` supplies the JWKS URI in the DSL and takes precedence over properties; `decoder()` replaces the decoder instance used by the chain.

**6.** Does a custom `JwtDecoder` Bean automatically inherit `audiences` from Boot?

> Do not assume so. Once Boot backs off from the default decoder, the custom decoder must apply any required audience validation itself.

**7.** Which part does `JwtAuthenticationConverter` change?

> It converts a verified JWT into an `Authentication`/authorities; it does not alter signature, issuer, audience, or timestamp validation.

**8.** For opaque tokens, which Bean corresponds to `JwtDecoder`?

> `OpaqueTokenIntrospector`.

**9.** How does `.introspector()` differ from `.introspectionUri()`?

> `.introspectionUri()` configures the endpoint/credentials for the default introspector; `.introspector()` replaces it with a custom implementation.

**10.** If you only need custom route authorization, do you need a custom decoder?

> No. You can declare a `SecurityFilterChain` and keep the auto-configured decoder.

**11.** When a custom chain is declared, why is a fallback policy needed?

> Because Boot's default chain has backed off; routes not matching a specialized chain must be handled explicitly.

**12.** Which Bean type does WebFlux use instead of `JwtDecoder`?

> `ReactiveJwtDecoder`.

**13.** Can a synchronous `OpaqueTokenIntrospector` be used in WebFlux?

> Avoid using it on the reactive request path if it performs blocking I/O; use `ReactiveOpaqueTokenIntrospector` instead.

**14.** Why can a custom decoder cause an application to lose audience validation?

> Because Boot no longer builds the default decoder that applies those properties; the custom decoder must configure the validator itself.

**15.** How do you verify the real decoder is being used?

> Send a Bearer token through the real filter chain and verify the decoder/validation path; `.with(jwt())` does not invoke the normal decoder.

**16.** Should issuer/JWKS URIs be declared in multiple places?

> Avoid doing so without good reason. Pick a single primary configuration source to avoid drift between properties, Beans, and the DSL.

## 19. References

- [Spring Boot — OAuth2](https://docs.spring.io/spring-boot/reference/security/oauth2.html): Resource Server properties, issuer URI, JWK Set URI, and audiences.
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): default chain, decoder, override/replacement, trusted algorithms, validators, and converters.
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): default introspector, `introspectionUri()`, `introspector()`, and authentication flow.
- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `SecurityWebFilterChain`, `ReactiveJwtDecoder`, and WebFlux auto-configuration.
- [Spring Security — Reactive Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector` and reactive introspection.
- [Spring Security — `JwtDecoder` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoder.html): interface for decoding and verifying JWTs.
- [Spring Security — `OpaqueTokenIntrospector` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html): introspection interface.
- [Spring Security — `SecurityFilterChain` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/SecurityFilterChain.html): Servlet security chain.
- [Spring Security — `SecurityWebFilterChain` API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/web/server/SecurityWebFilterChain.html): Reactive security chain.
- [Spring Security — Testing OAuth 2.0 with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html): testing JWT/opaque authorization and limitations of mock authentication.
- [Spring Security — Testing OAuth 2.0 with WebTestClient](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): reactive security testing.

**Conclusion:** Explicit Bean configuration and auto-configuration can coexist. Declaring a `SecurityFilterChain` replaces the default security chain without removing `JwtDecoder` or `OpaqueTokenIntrospector`; declaring a custom decoder/introspector replaces only the corresponding token verification component. Use properties for issuer, JWKS, audience, and introspection when defaults meet requirements; declare a custom chain when route authorization is needed; and replace the decoder/introspector only when specialized validation or integration is required—while preserving full signature, issuer, timestamp, audience, active-state, and token-policy checks yourself.
