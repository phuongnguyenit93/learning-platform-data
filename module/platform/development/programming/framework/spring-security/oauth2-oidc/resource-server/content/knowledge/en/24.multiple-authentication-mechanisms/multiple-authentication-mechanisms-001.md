# Supporting JWT and Opaque Tokens in a Resource Server

A **Spring Security OAuth 2.0/OIDC Resource Server** may need to accept two forms of **OAuth 2.0 bearer access token**: **JWT** and **opaque token**. This situation often arises when migrating from reference tokens to JWTs, when multiple Authorization Servers (AS) issue tokens for the same API, or when some tenants use JWTs while other tenants use opaque tokens requiring introspection.

For example, the same Orders API system serves:

- Tenant A: AS issues JWT access tokens; the Resource Server verifies signatures using a JWK Set.
- Tenant B: AS issues opaque access tokens; the Resource Server queries the OAuth 2.0 Token Introspection Endpoint to confirm the token is `active`.
- During migration: some clients still use reference tokens, while other clients have switched to JWTs.
- An API with fast token revocation requirements: may choose introspection even for JWTs if the AS supports it and policy requires it.

Both token formats **can be supported together**, but you should not assume that simply calling both `.jwt()` and `.opaqueToken()` in the same Spring Security configuration will work.

> **Foundational principle:** **selecting an authentication mechanism** is a routing step; **proving that a token is valid** must still be performed by the corresponding `JwtDecoder` or `OpaqueTokenIntrospector`. Do not treat token shape, request path, client-sent headers, or an unverified issuer as proof of authorization.

This guide covers **`SecurityFilterChain`**, **`AuthenticationManagerResolver<HttpServletRequest>`**, **`JwtAuthenticationProvider`**, **`OpaqueTokenAuthenticationProvider`**, JWT/opaque routing design, issuer/audience/resource binding, unifying scopes/authorities, error handling, and testing. The main code examples use **Spring Security Servlet/Spring MVC, Java 17+, and modern Spring Boot**. WebFlux requires different reactive APIs, which are noted separately at the end.

## 1. Distinguishing JWT and Opaque Access Tokens

Both JWT and opaque tokens can be used with HTTP bearer syntax:

~~~http
GET /api/orders HTTP/1.1
Host: orders.example.com
Authorization: Bearer <access-token>
~~~

The difference lies in **how the Resource Server validates the token**, not in the HTTP header.

| Aspect | JWT access token | Opaque access token |
|---|---|---|
| Common format | Three-part compact JWS | Reference string with no required readable format |
| Verification | JWS signature, trusted keys, claims validators | Introspection via AS or token validation service |
| Spring Security Servlet components | `JwtDecoder`, `JwtAuthenticationProvider` | `OpaqueTokenIntrospector`, `OpaqueTokenAuthenticationProvider` |
| Default principal | `Jwt` inside `JwtAuthenticationToken` | `OAuth2AuthenticatedPrincipal` inside `BearerTokenAuthentication` |
| Common authorities | `scope`/`scp` → `SCOPE_*` | `scope` in introspection → `SCOPE_*` |
| Network call | When discovery/JWKS/key refresh is needed | Usually calls introspection endpoint per token, unless cached |
| Early revocation capability | Depends on revocation check/TTL design | AS can return `active=false` after revocation |
| Binding token to the right API | Must validate `aud`/resource and profile | AS/introspection response or contract must confirm resource binding |
| What not to do | Decode an unsigned payload and trust claims | Fabricate a principal without querying a trusted state source |

Example illustrative JWT payload:

~~~json
{
  "iss": "https://login.example.com/realms/orders",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write",
  "exp": 2000000300
}
~~~

This data **only has security value** when the signature is verified against a public key belonging to an approved issuer and all validators succeed. Base64URL-decoding the payload to inspect `scope` is **not** JWT verification.

An opaque introspection response might contain:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "legacy-orders-client",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 2000000300
}
~~~

`active=true` is the result **from a trusted introspection endpoint**. Do not accept JSON sent by a client or an untrusted self-declared endpoint returning `active=true`.

### 1.1. A Token That Looks Like a JWT Is Not Necessarily an Accepted Token

Three dot-separated parts are usually a sign of a compact JWS, but:

- A caller can craft a forged three-part string.
- An opaque token can theoretically contain dots or look like a JWT.
- A JWE compact token usually has five parts, unlike a three-part JWS.
- There are many different JWT profiles: OIDC ID token, access token, client assertion, DPoP proof, etc.
- An ID token with a valid signature is **not** automatically an access token intended for the Orders API.

**Shape is a verifiable routing hint, not a source of trust.** Misclassification can cause an authentication failure; classification must never be used to bypass verification.

## 2. Two Main Deployment Models

A Resource Server can support both token types using different architectures:

~~~text
                 A Resource Server Application
                               |
                    Has bearer access token?
                               |
                               v
                 Select authentication mechanism
                     /                \
                   JWT                Opaque
                    |                   |
              JwtDecoder       OpaqueTokenIntrospector
                    |                   |
             verify JWS             active=true?
             validate claims        validate token context
                     \                 /
                      \               /
                          Authentication
                               |
                         Authorization
                         + scope/role
                         + tenant/ACL
                         + business rules
                               |
                            Handler
~~~

There are two practical scenarios:

**A. Routes have different contracts.** `/api/jwt/**` accepts only JWTs; `/api/legacy/**` accepts only opaque tokens. You can use **two `SecurityFilterChain` beans**, each with its own Resource Server configuration.

**B. The same route must accept both.** `/api/orders/**` may receive either a JWT or an opaque access token. You need an **`AuthenticationManagerResolver<HttpServletRequest>`** to select the `AuthenticationManager` at request time based on an intentional routing rule, and then still verify the token with the proper provider.

There is also **C. Using introspection for both**: if the AS supports introspecting both JWT and opaque access tokens, the Resource Server can configure **a single opaque token flow** and does not need format classification at the API. This approach changes trade-offs around network calls, revocation, and source of trust.

## 3. Important DSL Limitations

The following code is **not** a valid way to enable both token types in the same Spring Security Resource Server configurer:

~~~java
// INVALID inside the same oauth2ResourceServer configurer.
.oauth2ResourceServer(oauth2 -> oauth2
    .jwt(Customizer.withDefaults())
    .opaqueToken(Customizer.withDefaults())
)
~~~

Spring Security checks the configuration: without a custom `AuthenticationManagerResolver`, the Resource Server configurer only supports **either JWT or opaque token**, not both at the same time. In `OAuth2ResourceServerConfigurer`, configuring both default modes simultaneously can be rejected when building the security chain.

Another configuration that is also wrong:

~~~java
// Do not mix with .jwt()/.opaqueToken() in the same configurer.
.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationManagerResolver(myResolver)
    .jwt(Customizer.withDefaults())
)
~~~

When a custom resolver is provided, the resolver **replaces the default authentication manager selection strategy**. Within the same configurer, you should not simultaneously declare `jwt()` or `opaqueToken()` as if branches would be merged automatically.

### 3.1. Three Correct Patterns to Remember

| Goal | Configuration |
|---|---|
| JWT only in one chain | `.oauth2ResourceServer(o -> o.jwt(...))` |
| Opaque only in one chain | `.oauth2ResourceServer(o -> o.opaqueToken(...))` |
| JWT and opaque selected per request in the **same chain** | `.oauth2ResourceServer(o -> o.authenticationManagerResolver(resolver))` |

Two different chains **can** have separate JWT and opaque configurations; the limitation above only applies to using both default branches inside **the same Resource Server configurer**.

## 4. What Roles Do the Components Play?

| Component | Role in Servlet Resource Server |
|---|---|
| `BearerTokenAuthenticationFilter` | Extracts the bearer token and passes the request to the authentication strategy |
| `DefaultBearerTokenResolver` | Reads the bearer token according to RFC 6750/Spring rules |
| `BearerTokenAuthenticationToken` | Authentication object holding the unverified credential |
| `AuthenticationManagerResolver<HttpServletRequest>` | Selects the `AuthenticationManager` for the request |
| `ProviderManager` | Uses one or more `AuthenticationProvider` instances |
| `JwtAuthenticationProvider` | Uses `JwtDecoder` to verify a JWT and produces `JwtAuthenticationToken` |
| `OpaqueTokenAuthenticationProvider` | Uses `OpaqueTokenIntrospector` and produces `BearerTokenAuthentication` |
| `NimbusJwtDecoder` | Verifies JWS signatures using a trusted public key source |
| `SpringOpaqueTokenIntrospector` | Calls the introspection endpoint per trusted configuration |
| `JwtAuthenticationConverter` | Maps a verified JWT into authorities |
| `OAuth2AuthenticatedPrincipal` | Principal from successful introspection |
| `AuthorizationFilter` / method security | Checks scopes, roles, and policies after authentication succeeds |

`AuthenticationManagerResolver` **selects** the verification mechanism, but **does not verify** the token itself. `AuthorizationManager` decides access permissions after authentication succeeds. These two concepts should not be confused.

### 4.1. Why Does Spring Security Support a Resolver?

Each request may have different characteristics:

~~~text
Request 1 -> Tenant A / JWT
Request 2 -> Tenant B / opaque
Request 3 -> Tenant A / JWT
Request 4 -> Tenant C / unsupported
~~~

If a single `JwtDecoder` is used, an opaque token that is not a JWT cannot be decoded. If a single introspector is used, every token must be introspected by the AS, which may not fit a system that wants local JWT verification.

The resolver allows selecting an **approved manager per request**. Managers that were not selected should not automatically be invoked as a fallback for an invalid token.

## 5. Dependencies and Basic Configuration

Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Spring Boot manages Spring Security/JOSE versions via its BOM. If not using the starter, make sure you include the OAuth2 Resource Server and OAuth2 JOSE modules for JWT support.

Example `application.yml`:

~~~yaml
app:
  security:
    jwt:
      issuer: https://login.example.com/realms/orders
      jwk-set-uri: https://login.example.com/realms/orders/certs
      audience: orders-api
    opaque:
      introspection-uri: https://auth-legacy.example.com/oauth2/introspect
      client-id: orders-resource-server
      client-secret: "${INTROSPECTION_CLIENT_SECRET}"
      audience: orders-api
~~~

The `app.security.*` keys are **custom properties defined for this example**, not standard Spring Boot properties. When creating `JwtDecoder` and `OpaqueTokenIntrospector` beans manually, you must explicitly bind issuer, audience, URIs, and credentials.

**Do not** hardcode the introspection client secret into source code, images, logs, or browsers. In production, retrieve it from a controlled secret manager or environment.

## 6. Approach A — Two Route-Based SecurityFilterChains

This is the easiest approach to understand when the two endpoint groups **have distinct URL namespaces**.

Suppose:

~~~text
/api/jwt/**       accepts only JWT access tokens
/api/legacy/**    accepts only opaque access tokens
```

Each chain lives in the same Java application, but has a separate authentication flow:

~~~text
Incoming request
       |
       v
FilterChainProxy
       |
       +-- /api/jwt/** ?
       |       |
       |       +-- JwtDecoder / JwtAuthenticationProvider
       |
       +-- /api/legacy/** ?
       |       |
       |       +-- OpaqueTokenIntrospector / OpaqueTokenAuthenticationProvider
       |
       +-- other?
               |
               +-- fallback deny
~~~

### 6.1. Splitting Chains in Code

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class DualTokenChainsConfig {

    @Bean
    @Order(1)
    SecurityFilterChain jwtApiChain(
            HttpSecurity http,
            JwtDecoder decoder) throws Exception {

        return http
            .securityMatcher("/api/jwt/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/jwt/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/jwt/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.decoder(decoder)))
            .build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain legacyApiChain(
            HttpSecurity http,
            OpaqueTokenIntrospector introspector) throws Exception {

        return http
            .securityMatcher("/api/legacy/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/legacy/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/legacy/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque -> opaque.introspector(introspector)))
            .build();
    }

    @Bean
    @Order(3)
    SecurityFilterChain fallbackChain(HttpSecurity http)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .anyRequest().denyAll())
            .build();
    }
}
~~~

**Important assumption:** both APIs are **bearer-only** and do not authenticate using cookies automatically sent by browsers. That is why the example disables CSRF in the two API chains. Do not apply this as-is to OIDC browser login, BFF, or cookie-based authentication; CSRF must be evaluated according to the credential model.

### 6.2. Effects of `securityMatcher` and `@Order`

- `securityMatcher("/api/jwt/**")` selects the **JWT chain** for matching paths.
- `securityMatcher("/api/legacy/**")` selects the **opaque chain**.
- `@Order` determines which chain is evaluated first.
- `.requestMatchers(...)` inside each chain determines HTTP rules after the chain has been selected.
- `anyRequest().denyAll()` in a chain applies only to requests **that matched that chain**.
- The fallback chain protects URLs outside the two namespaces above.

If a general chain is ordered before a specific chain, it can shadow the JWT/opaque chain. Without a fallback, URLs that do not match any chain might not go through Spring Security filters.

### 6.3. The URL Only Selects the *Validator*, It Does Not Grant Access

A caller can send a JWT from `/api/jwt/orders` to `/api/legacy/orders`. When that happens:

- The opaque introspector decides whether the token is active according to the contract.
- The request must never be allowed merely because the route is `/api/legacy/**`.
- If the introspection endpoint can validate JWTs, the result may be accepted **if** AS/Resource Server policy allows JWTs on that route; if the contract mandates strict separation, additional checks on token type/issuer are needed.
- Scope/tenant/ownership must still be checked after authentication.

**Path is a routing input, not security proof.** If your organization requires ensuring JWTs are only used on JWT routes and opaque tokens only on legacy routes, you must test the behavior of the AS/validators rather than trusting path names alone.

### 6.4. When Is the Two-Chain Approach Unsuitable?

If the same endpoint `/api/orders` must accept both JWT and opaque tokens, you cannot configure two chains with the same `securityMatcher("/api/orders/**")` hoping Spring Security will try them sequentially: **only the first matching chain is selected** in the filter chain mechanism. You must switch to a resolver or use shared introspection.

## 7. Creating a JwtDecoder That Enforces Issuer and Audience

When creating a custom decoder for a JWT route, you must explicitly verify that **the JWT was issued for the right Resource Server**.

### 7.1. JWT Decoder Bean with a Trusted JWK Set

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
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwtValidationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.security.jwt.issuer}") String issuer,
            @Value("${app.security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Required audience is missing",
                        null
                    )
                );

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

In this example:

- `jwkSetUri` is configured by the server, not read from the JWT header `jku` or the request.
- `jwsAlgorithm(RS256)` restricts the algorithm according to the assumed AS contract. Do not arbitrarily accept multiple algorithms.
- `JwtValidators.createDefaultWithIssuer(...)` applies the appropriate issuer/time validators.
- The audience validator rejects JWTs that do not contain `orders-api` in the `aud` claim.
- The JWT must still be a valid access token profile; if the application requires `typ=at+jwt` or an RFC 9068 validator, integrate it according to your version.

If you declare a custom `JwtDecoder` bean, Spring Boot's auto-configured decoder may **back off**. Do not assume all `spring.security.oauth2.resourceserver.jwt.*` properties still apply to a custom bean, especially validators that you must manage yourself.

### 7.2. Why Does `aud` Still Matter If the Signature Is Valid?

An Authorization Server can issue access tokens for multiple APIs:

~~~text
aud = orders-api
aud = billing-api
aud = frontend-client
```

A token with a valid signature and valid `iss` may still **not be intended for the current API**. Without checking audience/resource, a token intended for Billing API or an ID token used for sign-in could be misused against Orders API.

**Valid issuer + valid signature does not automatically mean valid audience.**

## 8. Creating an OpaqueTokenIntrospector and Enforcing Resource Binding

An opaque token is verified by querying the AS:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth-legacy.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <resource-server-client-credentials>

token=<opaque-token>
~~~

RFC 7662 defines the introspection request/response; client authentication may vary depending on AS configuration. `Basic` is just a common example, not a mandatory choice for every system.

### 8.1. Bean Using the Standard Introspector

~~~java
package com.example.orders.security;

import java.util.Collection;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;

@Configuration
public class OpaqueValidationConfig {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${app.security.opaque.introspection-uri}") String uri,
            @Value("${app.security.opaque.client-id}") String clientId,
            @Value("${app.security.opaque.client-secret}") String clientSecret,
            @Value("${app.security.opaque.audience}") String audience) {

        OpaqueTokenIntrospector delegate =
            SpringOpaqueTokenIntrospector.withIntrospectionUri(uri)
                .clientId(clientId)
                .clientSecret(clientSecret)
                .build();

        return token -> {
            // Inactive/invalid tokens must be rejected by the delegate.
            OAuth2AuthenticatedPrincipal verified =
                delegate.introspect(token);

            Object rawAudience = verified.getAttribute("aud");

            boolean forThisApi =
                rawAudience instanceof String value
                    && value.equals(audience);

            if (rawAudience instanceof Collection<?> values) {
                forThisApi = values.contains(audience);
            }

            if (!forThisApi) {
                throw new BadOpaqueTokenException(
                    "Token is not intended for this API"
                );
            }

            return verified;
        };
    }
}
~~~

**Specific assumption of this example:** the introspection endpoint **returns `aud`** as a string or collection and the organization requires an exact audience match. RFC 7662 does not mandate that every response contain every attribute. If the AS does not return `aud`, this implementation fails closed and rejects opaque tokens; you will need to update the AS contract or establish equivalent resource binding at an **authoritative** introspection service.

**Do not mutate the response** by adding `aud=orders-api` when missing just to avoid errors. That destroys protection against token misuse across APIs.

### 8.2. `active=true` Is Necessary, Not Always Sufficient

Given an introspection response:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "client_id": "legacy-client",
  "aud": ["orders-api"]
}
~~~

The API still needs to know:

- Is this introspection endpoint trusted and configured for the right AS?
- Did the AS confirm the token belongs to the right resource/audience?
- Are the token type, client credentials, and issuer context appropriate?
- Was the `orders.read` scope actually granted by the AS?
- Have permissions on the specific tenant/order been checked by the service?

`active=true` is not a license to access every resource.

### 8.3. Opaque Introspection Differs from Local JWT Decoding

Some ASes also support **introspecting JWT access tokens**. When the Resource Server calls introspection and the AS returns `active=true`, that is an **introspection-based authentication flow**; the API does not necessarily run local JWS verification if policy chooses to trust the introspection endpoint. This is a valid architecture, though its trust, latency, and availability characteristics differ from local JWT verification.

## 9. Approach B — AuthenticationManagerResolver in a Single Chain

If the JWT vs. opaque decision must be made **at request time** within a single security chain, Spring Security documentation recommends `AuthenticationManagerResolver<HttpServletRequest>`.

### 9.1. Two Independent Managers

~~~java
AuthenticationManager jwtManager =
    new ProviderManager(new JwtAuthenticationProvider(jwtDecoder));

AuthenticationManager opaqueManager =
    new ProviderManager(
        new OpaqueTokenAuthenticationProvider(opaqueTokenIntrospector)
    );
~~~

- `jwtManager` is used only to **verify JWTs** with the configured decoder.
- `opaqueManager` is used only to **introspect tokens** via the configured service.
- Both can accept `BearerTokenAuthenticationToken` as unauthenticated input.
- Success produces different `Authentication` types, while authorization can check common `GrantedAuthority` values.

Do not turn the two providers into a "if JWT fails, try opaque" mechanism unless policy explicitly permits a fallback: doing so can open an **authentication downgrade** path.

### 9.2. Example Path-Based Routing Resolver

Suppose a single chain protects `/api/**`, with two route groups having clear contracts:

~~~text
/api/v2/**      -> JWT
/api/legacy/**  -> opaque
other /api/**   -> reject
```

Resolver:

~~~java
package com.example.orders.security;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.authentication.OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
public class TokenManagerResolverConfig {

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
            tokenAuthenticationManagerResolver(
                JwtDecoder jwtDecoder,
                OpaqueTokenIntrospector introspector) {

        AuthenticationManager jwtManager = new ProviderManager(
            new JwtAuthenticationProvider(jwtDecoder)
        );

        AuthenticationManager opaqueManager = new ProviderManager(
            new OpaqueTokenAuthenticationProvider(introspector)
        );

        AuthenticationManager reject = authentication -> {
            throw new BadCredentialsException(
                "Unsupported token route"
            );
        };

        return request -> {
            String path = request.getRequestURI();
            String contextPath = request.getContextPath();

            if (!contextPath.isEmpty()
                    && path.startsWith(contextPath)) {
                path = path.substring(contextPath.length());
            }

            if (path.equals("/api/v2")
                    || path.startsWith("/api/v2/")) {
                return jwtManager;
            }

            if (path.equals("/api/legacy")
                    || path.startsWith("/api/legacy/")) {
                return opaqueManager;
            }

            return reject;
        };
    }
}
~~~

The example code uses path only to **select the manager**. In production, URIs may be affected by servlet paths, forwarding, and reverse-proxy rewriting; if path matching is complex, use matchers following Spring Security's request matching contract and test alignment with controller mappings rather than scattering `startsWith(...)` checks.

**Important:** `reject` is still an `AuthenticationManager` that fails closed; never return a dummy `Authentication` with `authenticated=true`.

### 9.3. Wiring the Resolver into SecurityFilterChain

~~~java
package com.example.orders.security;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MixedApiSecurityConfig {

    @Bean
    SecurityFilterChain mixedApiChain(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> resolver)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/v2/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/v2/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .requestMatchers(
                    HttpMethod.GET, "/api/legacy/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/legacy/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver))
            .build();
    }
}
~~~

This example is an **alternative** to the two-chain configuration in section 6. In a single application, do not declare both solutions simultaneously with overlapping chain matchers without precisely defining order and ownership.

### 9.4. Why Doesn't This Code Call `.jwt()` or `.opaqueToken()`?

Because **the resolver already selects the authentication manager**, the DSL needs:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .authenticationManagerResolver(resolver))
~~~

Do not add:

~~~java
.jwt(...)
.opaqueToken(...)
~~~

into the same configurer; that configuration violates Spring Security's mutual exclusivity contract.

### 9.5. The Resolver Is Called with an Unauthenticated Request

`AuthenticationManagerResolver.resolve(request)` receives the `HttpServletRequest` **before the JWT or opaque token is authenticated**. Therefore, any path/header/token string read from the request is only an **input to select the manager**, not a source of roles or permissions.

If route `/api/v2/**` is selected, only `JwtAuthenticationProvider` succeeding after full JWT verification grants authorization.

## 10. A Single URL Accepting Both JWT and Opaque Tokens: Explicit Criteria Required

A harder case:

~~~text
GET /api/orders
Authorization: Bearer <JWT or opaque token>
```

There is no `/jwt` or `/legacy` in the path to distinguish them.

Several options exist:

1. **Prefer introspection for both** if the AS supports it and policy permits.
2. Use a **token namespace convention** guaranteed by the AS, e.g., opaque tokens always start with a defined prefix, while JWTs have a valid compact JWS shape.
3. Use a **trusted gateway** that verifies tokens and forwards identity over an authenticated internal channel, when the architecture and trust model fit.
4. Change the API contract so clients use different routes/hosts per token type.
5. With multiple issuers, use an appropriate routing contract and trusted issuer registry; do not use an unverified issuer URL to trigger discovery.

**There is no universal rule that "JWTs contain two dots and opaque tokens do not"**: an opaque token can inherently be any arbitrary string.

### 10.1. Example Classification by an AS-Approved Format Contract

Suppose **in this system**:

- The legacy AS issues opaque tokens prefixed with `ref_`.
- The new AS issues three-segment Base64URL compact JWS JWTs.
- Tokens not matching either format above are rejected.
- The AS guarantees opaque tokens **never have** a three-part JWS shape and JWTs **never** start with `ref_`.

This is a **system-specific contract**, not an RFC rule.

~~~java
package com.example.orders.security;

import java.util.regex.Pattern;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.web.authentication.preauth.PreAuthenticatedAuthenticationToken;
import org.springframework.security.oauth2.server.resource.web.DefaultBearerTokenResolver;

public final class TokenFormatAuthenticationManagerResolver
        implements AuthenticationManagerResolver<HttpServletRequest> {

    private static final Pattern COMPACT_JWS =
        Pattern.compile(
            "[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+"
        );

    private final DefaultBearerTokenResolver tokenResolver =
        new DefaultBearerTokenResolver();

    private final AuthenticationManager jwt;
    private final AuthenticationManager opaque;

    private final AuthenticationManager reject = authentication -> {
        throw new BadCredentialsException(
            "Unsupported bearer token format"
        );
    };

    public TokenFormatAuthenticationManagerResolver(
            AuthenticationManager jwt,
            AuthenticationManager opaque) {

        this.jwt = jwt;
        this.opaque = opaque;
    }

    @Override
    public AuthenticationManager resolve(HttpServletRequest request) {
        String token = tokenResolver.resolve(request);

        if (token == null) {
            return reject;
        }

        if (token.startsWith("ref_")) {
            return opaque;
        }

        if (COMPACT_JWS.matcher(token).matches()) {
            return jwt;
        }

        return reject;
    }
}
~~~

This class only **selects the manager**. It does not parse the payload to extract `sub`, does not trust `alg`/`kid`, and does not log tokens. You can remove the `PreAuthenticatedAuthenticationToken` import as it is unnecessary for this solution. When integrating, create the two managers as in section 9.1, pass them to the constructor, and attach the resolver to `.authenticationManagerResolver(...)`.

**Important security condition:** both managers must still verify tokens independently; a three-part token with an invalid signature must be rejected by the JWT decoder and **not** automatically fall through to opaque introspection. A `ref_` token must be rejected by the introspector when inactive. If an adversary prepends `ref_`, that only sends the request through the opaque manager; they cannot conjure `active=true` out of thin air.

### 10.2. Limitations of Format-Based Routing

- `COMPACT_JWS` is a **very coarse syntax check**, not a JWT parser or validator.
- An opaque token with three parts will be classified as JWT and may be rejected even if the AS recognizes it.
- A JWT with a five-part JWE structure will not be accepted by this classifier.
- If the AS changes format without updating the API, failures will occur.
- Bearer token size limits and log redaction are needed to reduce abuse.
- Do not allow query parameters or auxiliary headers to select "bypass validation" without a contract.
- Each route/issuer may need its own audience, token type, and authority policy.

Because of these limitations, format-based routing is only appropriate when **the AS guarantees an unambiguous namespace/format** and integration tests exist. If token formats lack a clear contract, **prefer shared introspection or API-namespace routing**.

### 10.3. Do Not Use an Unverified Issuer to Auto-Register an AS

A JWT containing:

~~~json
{
  "iss": "https://attacker.example/oidc"
}
~~~

must not cause the Resource Server to dynamically create:

~~~java
JwtDecoders.fromIssuerLocation(untrustedIssuer)
~~~

and accept an attacker's self-signed token. If multi-issuer JWTs are supported, there must be a **trusted issuer allowlist**; only then select the manager/decoder for the matching issuer and verify signature/claims.

## 11. Why Not Try JWT First and Fall Back to Opaque on Error?

A seemingly convenient approach:

~~~text
1. Try JwtDecoder.decode(token)
2. If any exception is thrown
3. Automatically call introspection
4. If introspection returns active=true, accept
```

At first glance, this might let malformed JWTs or opaque tokens pass through introspection, but it **conflates many error types with different security semantics**:

- JWT from an untrusted issuer.
- JWT with invalid signature.
- Expired JWT.
- JWT with wrong audience.
- Valid JWT failing the token profile.
- JWKS server outage.
- A genuinely opaque token, not a JWT.

An invalid JWT could accidentally be accepted by another introspection endpoint with a looser contract. A network failure at the decoder could cause the system to switch mechanisms, making auditing difficult and creating a **downgrade path**.

### 11.1. A ProviderManager with Two Providers Does Not Solve This Safely Either

For example:

~~~java
new ProviderManager(
    new JwtAuthenticationProvider(jwtDecoder),
    new OpaqueTokenAuthenticationProvider(introspector)
)
~~~

is not a safe default way to express "if JWT then JWT provider, if opaque then opaque provider". Both providers can support `BearerTokenAuthenticationToken`, and the ordering/exception handling in `ProviderManager` can cause the next provider to be tried in ways that do not reflect token-format policy.

**Prefer a resolver that explicitly selects a manager** or a single shared introspection source. If a fallback is deliberately allowed for a very specific case, you need a threat model, an exception taxonomy, and tests proving an invalid JWT cannot be routed to a weaker authentication path.

### 11.2. Fallback "for Availability" Is Dangerous

Never do this:

~~~java
try {
    return jwtDecoder.decode(token);
} catch (Exception e) {
    return trustClaimsWithoutSignature(token);
}
~~~

If JWKS is down, the right answer is that **tokens needing that key cannot be verified**, not to issue ungrounded principals/authorities.

## 12. Approach C — Introspection for Both JWT and Opaque Tokens

An opaque token Resource Server is really a **Resource Server using introspection**, not a component restricted to strings without dots.

If the AS allows introspecting **both JWT access tokens and opaque access tokens**, you can configure:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspector(trustedIntrospector)))
~~~

Both tokens are sent to the **trusted** introspection endpoint, and the AS decides whether they have `active=true` according to resource binding and token status.

### 12.1. Advantages

- No need to classify by token shape.
- Can receive live status/revocation results from the AS.
- Single authorities contract (especially scopes).
- Can reduce multi-branch logic in the Resource Server.
- Easy to enforce the policy "AS is the source of truth for current token status".

### 12.2. Trade-offs

- Introspection endpoint network latency/availability becomes a per-request dependency.
- Requires client authentication, TLS, timeouts, rate limiting, and bounded retry policies.
- The AS might not support introspecting JWTs or might not expose sufficient claims.
- Must still check `aud`, issuer, client type, and token purpose per the AS contract.
- Introspection caching can delay token/role revocation.
- With multiple issuers, **a single introspection endpoint** might not know tokens from every AS.

### 12.3. When Not to Choose Shared Introspection?

If AS A only issues JWTs and does not introspect JWTs, while AS B issues opaque tokens at a different endpoint, a single shared introspector cannot verify both. In that case, use a **resolver with two managers** or split routes; do not let one AS vouch for another AS's tokens without explicitly designed trust federation.

## 13. JWT Branch: Issuer, Keys, Algorithms, and Type

For the JWT branch, at minimum you must know:

| Check | Purpose |
|---|---|
| Trusted `issuer-uri` | Issuer allowed by the API |
| Trusted JWKS URL | Source of the issuer's public keys |
| Allowed `alg` | Restricts JWS algorithms/key types |
| Signature | Proves the token was signed by a trusted key |
| `iss` | Verified token matches the expected issuer |
| `aud` | Token was issued for this Resource Server |
| `exp`/`nbf` | Token is valid within the time window |
| `typ`/profile | Is this actually an OAuth access-token JWT |
| `scope`/`scp` | Granted permissions per the AS contract |

An **unverified JWT header** can contain `kid`, `jku`, `x5u`, and `alg`; never use a URL from the header to dynamically fetch a public key from an untrusted host. `kid` should only select a key from a trusted key source.

### 13.1. Multi-Issuer JWT

If JWT tokens from multiple issuers are accepted, use `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` or a manager repository containing only approved issuers.

Do not pass an unverified `iss` into `JwtDecoders.fromIssuerLocation(...)` for arbitrary Internet URLs. That both widens trust excessively and can create SSRF.

### 13.2. Verifying Resource Binding

A token A with a valid signature but `aud=["billing-api"]` must not be automatically accepted by `orders-api`. Validating the right AS is not enough if the intended resource is wrong.

Do not use an OIDC Client ID token as a bearer access token just because both are JWTs.

## 14. Opaque Branch: Introspection Trust and Token Status

RFC 7662 introspection allows the AS to return:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "legacy-orders-client",
  "scope": "orders.read",
  "aud": ["orders-api"]
}
~~~

The Resource Server must:

1. Call **the exact endpoint** from server configuration, not from tokens/headers.
2. Authenticate the **resource-server client** to the AS.
3. Use HTTPS/TLS and an explicit timeout policy.
4. Reject `active=false` or malformed responses.
5. Never default `active=true` when the introspection service errors.
6. Verify audience/resource binding per the AS contract.
7. Never turn arbitrary introspection attributes into an admin role.
8. Never store or log raw bearer tokens in logs or metrics.

### 14.1. Introspection Results May Differ from JWT Claims

An opaque response might lack `iss` or format scopes/roles differently from a JWT. Therefore, the API must define the **identity namespace** of the opaque AS using trusted configuration sources.

Do not assume an opaque principal without `iss` is the same user as a JWT issuer's user just because `sub` matches.

### 14.2. Client Credentials Tokens

With `client_credentials`, a token may represent a workload rather than a human user. Do not assume every `client_id` or `sub` is a user who owns orders.

The API needs separate policies for machine identities, allowed scopes, tenant binding, and auditing.

## 15. Unifying Authorities Between JWT and Opaque Tokens

An API with two authentication flows needs a **consistent** way to interpret authorities; otherwise the same endpoint could allow two unintended permission sets.

Suppose JWT:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

and opaque introspection:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write"
}
~~~

By default conventions, Spring Security typically generates:

~~~text
SCOPE_orders.read
SCOPE_orders.write
~~~

In both paths, authorization rules can use:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

### 15.1. Not Every Role Claim Is Mapped Automatically

A JWT might contain:

~~~json
{
  "scope": "orders.read",
  "roles": ["orders_manager"]
}
~~~

Opaque introspection might contain:

~~~json
{
  "active": true,
  "scope": "orders.read",
  "permissions": ["orders.export"]
}
~~~

`roles` and `permissions` here are **custom claims** with no universal mapping across all ASes.

| Verified input | Authority that may be created | Condition |
|---|---|---|
| JWT `scope=orders.read` | `SCOPE_orders.read` | Scope genuinely granted by AS |
| Introspection `scope=orders.read` | `SCOPE_orders.read` | Token active, AS granted scope |
| JWT `roles=orders_manager` | `ROLE_ORDERS_MANAGER` | AS is authoritative to grant this role for the API |
| Introspection `permissions=orders.export` | `PERM_ORDERS_EXPORT` | Approved custom mapping |
| Email ending in `@company.example` | Do not auto-grant admin | Email is not an entitlement |
| `username=admin-support` | Do not auto-grant admin | Username is not an entitlement |
| Missing role | Do not fabricate role | Do not add permissions to hide 403 errors |
| Unknown role | Do not create authority | Allowlist mapping |

### 15.2. Different Prefixes, Different Semantics

`SCOPE_orders.read` is not `ROLE_ORDERS_READER`; `hasRole("ORDERS_READER")` typically checks `ROLE_ORDERS_READER`. The `PERM_*` convention is application-defined, not a Spring Security standard.

If one AS calls it `read:orders` and another calls it `orders.read`, map them to the same authority only when the contract proves **equivalent resource scope, actions, and tenant constraints**.

## 16. Principals Have Different Types After Authentication

After the JWT branch succeeds, you typically have:

~~~java
JwtAuthenticationToken
    |
    +-- getToken() -> Jwt
    +-- getAuthorities() -> GrantedAuthority collection
    +-- getName() -> usually from sub per converter
~~~

After the opaque branch succeeds, you typically have:

~~~java
BearerTokenAuthentication
    |
    +-- getPrincipal() -> OAuth2AuthenticatedPrincipal
    +-- getTokenAttributes() -> introspected attributes
    +-- getAuthorities() -> GrantedAuthority collection
~~~

A controller written as:

~~~java
@GetMapping("/api/me")
Map<String, Object> me(@AuthenticationPrincipal Jwt jwt) {
    return Map.of("sub", jwt.getSubject());
}
~~~

may only fit the **JWT branch**. When an opaque token passes through, the principal is not `Jwt` by default, so injection/casting may not work.

### 16.1. Using the Common Authentication Abstraction

If an endpoint serves both token types, it can accept:

~~~java
@GetMapping("/api/me")
Map<String, Object> me(Authentication authentication) {
    return Map.of(
        "name", authentication.getName(),
        "authenticated", authentication.isAuthenticated()
    );
}
~~~

`getName()` is not guaranteed to share the same namespace across issuers. Real APIs need identity mapping in the service layer.

### 16.2. Domain CallerIdentity with Explicit Source

An application-level model could be:

~~~java
public record CallerIdentity(
    String identitySource,
    String subject,
    String clientId,
    boolean servicePrincipal
) {}
~~~

This is an **application-defined record**, not a Spring Security API.

- JWT branch: `identitySource` is typically the **verified trusted `iss`**.
- Opaque branch: `identitySource` can be the **trusted introspection authority identifier** from configuration, or `iss` returned by the AS per contract.
- `subject` must come from the authenticated principal.
- `clientId` represents OAuth client identity and does not replace a human subject.
- `servicePrincipal` must be based on authoritative token purpose/contract, not a self-asserted request header.

**Never equate two `sub=user-42` values from two ASes just because the strings match.** When binding ownership, use `(identitySource, subject)` or map to an internal user ID via a trusted directory.

### 16.3. Do Not Copy Every Introspection Attribute into Responses

An `/api/me` endpoint can return the needed name/display name; do not dump all JWT/opaque attributes, raw tokens, client secrets, or internal privileges into public JSON.

## 17. Tenant-Aware Routing: Two Questions to Separate

In a multi-tenant system, there are two independent questions:

**Authentication question:** was the token issued by a valid AS for this API?

**Authorization question:** does that principal have permission for the requested tenant and object?

~~~text
GET /api/tenants/tenant-a/orders/order-99
Authorization: Bearer <token>
                   |
                   v
JWT / opaque verification
                   |
                   v
Known principal + authorities
                   |
                   v
Check membership tenant-a
                   |
                   v
Check order-99 really belongs to tenant-a
                   |
                   v
Check owner/ACL/state
                   |
                   v
Return data only if authorized
~~~

The path `tenant-a`, HTTP host, `X-Tenant-Id`, or `tenantId` parameter is a **client-selected target**, not proof of membership.

### 17.1. One Issuer Can Issue for Multiple Tenants

If one AS issues JWTs for the whole enterprise with a `tenant_id` claim, an issuer-based resolver **does not automatically enforce** tenant permissions. You must verify `tenant_id` semantics and enforce membership/ACLs.

### 17.2. One Tenant Can Use Multiple Issuers

Tenant A might allow human users from OIDC issuer X and workloads from AS Y. Tokens from X and Y have different principal namespaces; controlled policy mapping is required.

### 17.3. Route Selection Does Not Replace Issuer/Audience Validation

An opaque token sent to `/api/legacy/**` is not guaranteed to belong to the legacy tenant if the introspection service checks loosely. Likewise, a JWT sent to `/api/v2/**` must have its issuer, audience, and real token profile verified.

## 18. Token Lifecycle, Revocation, and Migration

Supporting both token types commonly occurs during migration:

~~~text
T0  Legacy clients -> opaque tokens
T1  New clients -> JWT
T2  Resource Server supports both
T3  Stop issuing new opaque tokens
T4  Wait for existing opaque tokens to expire or be revoked
T5  Remove opaque support after checking telemetry
```

A proper roadmap requires:

- List of clients/issuers permitted to use each token type.
- Audience/resource binding for both.
- Equivalent or intentionally differentiated permission mappings.
- Token lifetimes, refresh token policies, and revocation.
- Count of still-valid opaque tokens via telemetry.
- A controlled rollback window to the legacy mechanism.
- Security tests ensuring invalid JWTs cannot fall back to opaque.
- A plan to retire introspection credentials and endpoint routing once migration finishes.

### 18.1. JWT Revocation Differs from Opaque Revocation

Local JWT verification may accept a token until `exp` even if the user's session/roles were just revoked, unless there is a denylist, security-version check, or equivalent mechanism.

Opaque introspection can reflect `active=false` sooner if the AS updates state and caching permits. However, do not assume every AS always returns up-to-the-second entitlements; it may cache introspection/entitlements.

**Do not choose the opaque branch just because "the token looks harder to read".** Choose based on revocation, trust, latency, and operational requirements.

## 19. Latency and Network Dependencies of Both Paths

A JWT request flow:

~~~text
JWT -> check signature locally
         |
         +-- JWK key available -> no network call needed
         +-- key/refresh needed -> fetch trusted JWKS
```

An opaque flow:

~~~text
Opaque -> HTTP introspection
              |
              +-- endpoint online -> active, attributes
              +-- endpoint timeout -> authentication cannot be proven
```

This affects:

| Aspect | JWT | Opaque |
|---|---|---|
| p99 latency | Usually low when keys are warm | Depends on introspection latency/cache |
| AS outage | Tokens with cached keys can still verify per policy | May be disrupted if endpoint is unavailable |
| Signing key rotation | Requires JWKS refresh | Handled by AS inside introspection flow |
| Token revocation | Requires revocation design if needed before `exp` | AS can report `active=false` |
| Scaling many replicas | Per-instance/gateway JWKS cache | Introspection QPS grows with request rate |
| Resource Server secrets | Usually only public keys needed | May require introspection client secret |
| Troubleshooting | JWS/claims/key rotation | Network/client auth/`active`/schema |

These statements are **general operational guidance**, not latency/availability guarantees for every deployment. A JWT decoder may still need network access on missing keys; an introspection cache can reduce network load but make revocation stale.

### 19.1. Timeouts and Infrastructure Errors

Set timeouts for HTTP clients calling JWKS/introspection to match your SLO. Do not use infinite timeouts and never fail open when upstream does not respond.

If the introspection endpoint times out, the Resource Server **must not** return a dummy `Authentication` just to keep the API returning 200.

### 19.2. Separate Cache Types

- **JWKS cache:** caches public keys; does not bypass JWT signature validation.
- **Introspection cache:** caches token status/attributes; can delay revocation taking effect.
- **Business ACL cache:** caches tenant/order permissions; requires invalidation.
- **HTTP response cache:** must never accidentally share private data across users/tenants.

Do not use a cache key consisting solely of `sub` if two different issuers can have overlapping `sub` values.

## 20. 401 and 403 in a Mixed Resource Server

Common status codes:

| Scenario | Typical result | Layer |
|---|---|---|
| No bearer token sent to private route | 401 | Unauthenticated |
| JWT invalid signature | 401 | JWT authentication failure |
| JWT wrong issuer/audience/expired | 401 | JWT validators |
| Opaque token `active=false` | 401 | Introspection failure |
| Opaque introspection service unavailable | Authentication/infrastructure error per handler | Must not grant access |
| Token format not in contract | Rejected | Resolver/manager |
| Valid token missing `orders.read` | 403 | HTTP authorization |
| Valid token but order belongs to another tenant | 403/404 per policy | Business authorization |
| Public route with invalid bearer token | May return 401 | Authentication filter processes bad credential |
| Request hits `anyRequest().denyAll()` | 403 if authenticated, otherwise depends on entry point | Authorization |

**401** usually indicates authentication has not succeeded; **403** usually indicates an authenticated principal was denied permission. Introspection/JWKS availability errors may be surfaced as 5xx or another error depending on version/exception handling; do not assume every timeout returns 401.

### 20.1. Bearer Challenge

Per RFC 6750, responses can include:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Or when scopes are insufficient:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

Do not echo raw access tokens, introspection client secrets, or sensitive claims in responses for debugging.

## 21. Session, CSRF, and Browser Clients

A pure bearer-header Resource Server can use:

~~~java
.sessionManagement(session -> session
    .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
~~~

This tells Spring Security not to rely on `HttpSession` to retrieve authentication across requests. Each request supplies its own token.

However, **`STATELESS` does not prevent other components from creating a session** (controllers, filters, login flows, CSRF repositories). JWT/opaque coexistence does not automatically solve browser CSRF/XSS/CORS.

### 21.1. CSRF Depends on the Credential Model

If the API only accepts `Authorization: Bearer ...` actively sent by clients, the CSRF threat model differs from cookie-session apps. Disabling CSRF can be chosen after reviewing the architecture.

If tokens/credentials are automatically sent by browsers via cookies, **CSRF can still be a risk** even if authentication uses JWT or opaque tokens. Do not disable CSRF simply because you see `STATELESS` or `oauth2ResourceServer`.

### 21.2. OIDC Login Differs from Resource Server

`oauth2Login()` / OIDC Authorization Code flow of **OAuth2 Client** requires state, PKCE verifier, and nonce across redirects; it does not automatically become a shared bearer JWT/opaque authentication path.

If an application has both an OIDC Login web UI and a Resource Server, you should typically use **clearly scoped filter chains** with separate CSRF/session policies.

## 22. CORS and the `Authorization` Header

An SPA sending a Bearer header cross-origin may trigger an `OPTIONS` preflight:

~~~http
OPTIONS /api/orders HTTP/1.1
Origin: https://app.example.com
Access-Control-Request-Method: GET
Access-Control-Request-Headers: authorization
~~~

CORS must be configured for browsers, but **CORS is not authentication**. Adding `Access-Control-Allow-Origin` does not make a JWT or opaque token valid.

When debugging, distinguish:

- Preflight blocked by CORS/security.
- Missing or malformed bearer token.
- JWT signature/issuer/audience failure.
- Opaque introspection timeout.
- HTTP authority denied.
- Business ACL/tenant denial.

Never open all endpoints with `permitAll()` to "fix CORS".

## 23. Testing Token Classification and Non-Fallback

A mixed solution needs **security tests for both branches and the branch-selection boundary**.

### 23.1. Main Test Matrix

| Request / Token | JWT branch | Opaque branch |
|---|---|---|
| Valid JWT, right issuer/audience | Allow authentication | Allow only if AS introspection contract intentionally supports it |
| JWT invalid signature | Reject | Must not treat as fallback success |
| Expired JWT | Reject | Must not bypass expiration |
| JWT for another API | Reject | Must not accept wrong resource |
| Active opaque, right resource | Reject if not a JWT | Allow authentication |
| Inactive opaque | Reject | Reject |
| Opaque introspection timeout | Irrelevant if JWT branch selected | Do not grant |
| Unsupported token format | Reject | Reject if outside contract |
| JWT with read scope calling POST write | 403 | Not write permission |
| Opaque with read scope calling POST write | Not write permission | 403 |
| Valid token, wrong tenant | Business policy reject | Business policy reject |
| Unknown issuer | Reject | Allow only if trusted AS has a contract |
| JWT-like opaque token | May be misclassified | Supported only if contract enables proper routing |

Do not test only the happy path where both tokens work. **Branch-switching paths and negative cases** are what catch privilege escalation.

### 23.2. Testing with MockMvc Using Real Signed Tokens

To prove both branches work:

1. Generate a **test private/public key pair** for JWTs.
2. Use a fake JWKS server returning the test public key with a real decoder.
3. Sign test JWTs containing `iss`, `aud`, `scope`, `exp`.
4. Use a fake introspection server returning `active=true` for one opaque token and `active=false` for another.
5. Send requests via `MockMvc`/test server with the `Authorization` header.
6. Measure how many times the JWT JWKS endpoint and introspection endpoint are called.
7. Verify an invalid JWT is **not** forwarded to introspection as an out-of-contract fallback.
8. Verify an inactive opaque token is rejected even if the string looks valid.
9. Check 401/403 on read/write endpoints.
10. Check invalid issuer/audience and wrong tenant.

To test full route selection, **do not rely solely on mock authentication** and claim the resolver executed.

### 23.3. What Are the Limits of MockMvc `.with(jwt())`?

Spring Security Test:

~~~java
mvc.perform(get("/api/jwt/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

can bypass the real `JwtDecoder` and attach authentication directly. It is useful for testing `hasAuthority`, **not** for proving signatures, resolvers, issuers, or audiences.

Similarly, mocking opaque token authentication can also skip network introspection.

### 23.4. Counting Calls to Introspection/JWKS Servers

For a resolver selecting the JWT branch, expect **zero introspection requests** for a valid JWT token under a strict split-routing policy. For the opaque branch, expect **no reliance on JWKS** to validate an opaque token.

If using shared introspection per approach C, a JWT generating an introspection call is **architecturally expected**, not a bug. Test expectations must match the chosen design.

## 24. Unit Testing the Resolver Independently

You do not need to call a real AS to verify the resolver picks the right manager by path.

Conceptual setup example:

~~~java
AuthenticationManager jwt = authentication -> {
    throw new BadCredentialsException("JWT test manager invoked");
};

AuthenticationManager opaque = authentication -> {
    throw new BadCredentialsException("Opaque test manager invoked");
};
~~~

You can inject two stub managers into the resolver, call `resolve(mockRequest)` for each URL, and assert which manager reference is returned.

**However**, these stubs only verify branch selection and do not validate tokens at all. Never put a stub that returns an automatic principal into production.

### 24.1. Cases That Must Be Included

- `/api/v2/orders` → right JWT manager.
- `/api/legacy/orders` → right opaque manager.
- `/api/v2X/orders` → must not falsely match `/api/v2/`.
- `/api/unknown` → reject.
- With/without context path → policy remains accurate.
- Forwarded path/proxy rewrite per deployment → no misrouting.
- Missing bearer header → no authenticated principal.
- Malformed JWT → selects JWT per contract and fails.
- Inactive opaque → selects opaque and fails.
- Concurrent requests → thread-safe manager reuse.

## 25. Anti-Patterns to Avoid

### 25.1. Enabling Both DSLs in the Same Chain

~~~java
// WRONG inside the same oauth2ResourceServer configurer.
.oauth2ResourceServer(o -> o
    .jwt(Customizer.withDefaults())
    .opaqueToken(Customizer.withDefaults()))
~~~

Use `authenticationManagerResolver` or separate chains.

### 25.2. Trying Both Providers Without Classification

~~~java
// DO NOT treat this as an explicit JWT-vs-opaque choice.
new ProviderManager(jwtProvider, opaqueProvider);
~~~

You need to know which input types each provider supports and what exception/fallback policy applies. Both providers above can support bearer inputs, making "which one gets tried first" semantics hard to control.

### 25.3. Trusting a Token as a Valid JWT Just Because It Has Two Dots

~~~java
// WRONG if used as proof that the token is valid.
if (token.contains(".")) {
    return grantAdmin();
}
~~~

Format checks only select a manager; they do not grant privileges.

### 25.4. Accepting Any Request-Chosen Introspection Endpoint

~~~text
X-Introspection-Uri: https://attacker.example/validate
```

Do not use such a header as the introspection endpoint source. A trusted configuration is mandatory.

### 25.5. Skipping Issuer/Audience Validators Because the JWT Signature Is Valid

A valid signature does not prove the intended API. An access token from another issuer/trust context could be misused.

### 25.6. Adding Extra Authorities So Both Token Types "Produce the Same Result"

~~~java
// WRONG without real entitlement.
authorities.add(new SimpleGrantedAuthority("SCOPE_orders.write"));
~~~

Do not add write permission just because legacy opaque tokens tended to have broader rights; migration must use properly issued AS permissions and authoritative mappings.

### 25.7. Relying on a Bare `sub` Across Multiple Issuers

~~~text
JWT issuer A:    sub=user-42
Opaque issuer B: sub=user-42
```

Do not automatically merge two users. Use an identity-source namespace.

### 25.8. Confusing `JSESSIONID` with JWT/Opaque Coexistence

An `HttpSession` cookie is not a bearer token. If an API expects a bearer header, `JSESSIONID` should not silently replace authentication unless the app intentionally maintains a separate session mechanism.

### 25.9. Using Access Tokens as Log Keys

Do not log raw bearer tokens in debug logs, cache metric labels, or exception messages. If correlation is needed, use a policy-controlled reference or digest.

### 25.10. Skipping Service-Level Ownership Checks

`SCOPE_orders.read` from a JWT or opaque token does not prove the principal can read every order. You must verify tenant, owner, ACL, and resource state.

## 26. A Security Design Checklist

Before allowing a Resource Server to accept both JWT and opaque tokens, verify:

- [ ] Which issuers/ASes and environments do the two token types come from?
- [ ] Is each AS accepted through a governed allowlist/configuration?
- [ ] Is there a contract for token type/namespace or route to select the right manager?
- [ ] If a shared URL needs both types, did you choose shared introspection or a safe resolver?
- [ ] Does the resolver avoid constructing endpoints/JWKS URIs from untrusted tokens/headers?
- [ ] Is there no fallback from JWT signature/audience/expiry failures to a weaker mechanism?
- [ ] Do JWTs have signature, allowed algorithms, issuer, audience, timestamp, and token profile validators?
- [ ] Are opaque tokens genuinely introspected and `active=false` rejected?
- [ ] Is the introspection response bound to the right API/resource?
- [ ] Are introspection client credentials/TLS/timeouts managed securely?
- [ ] Do `SCOPE_*`, `ROLE_*`, and `PERM_*` come from approved entitlement sources?
- [ ] Do multi-issuer principals use an identity namespace or trusted canonical ID?
- [ ] Does route selection avoid replacing membership/owner/ACL checks in services?
- [ ] Do HTTP security matchers/fallbacks prevent sensitive URLs from bypassing filter chains?
- [ ] Are session/CSRF/CORS configured appropriately for bearer-only vs. cookie/browser models?
- [ ] Do JWKS/introspection timeouts fail closed without creating principals from unverified data?
- [ ] Does introspection caching have an appropriate TTL/revocation freshness?
- [ ] Are invalid JWT signatures, inactive opaque tokens, wrong audiences, missing scopes, and wrong tenants all tested?
- [ ] Are paths tested so invalid JWTs do not unintentionally fall back?
- [ ] Does observability distinguish JWT decoding, introspection, and authorization denials?
- [ ] Is there a plan to remove legacy support after migration and revoke unused secrets?

## 27. Choosing a Solution by Requirements

| Practical condition | Suitable starting approach |
|---|---|
| JWT and opaque use **separate URL namespaces** | Multiple `SecurityFilterChain` beans, one token mechanism per chain |
| One chain with route-specific policy | `AuthenticationManagerResolver<HttpServletRequest>` selecting manager by path |
| Same URL accepts both, **AS can introspect both** | Single opaque introspection flow |
| Same URL, AS has unambiguous token namespace | Format-based resolver **for routing only**; both providers still verify |
| Same URL, unknown token format and AS cannot share introspection | Change token/API contract or design explicit trusted routing; do not guess |
| Multiple JWT issuers | `JwtIssuerAuthenticationManagerResolver` with trusted issuer list/registry |
| Multiple opaque ASes | Trusted resolver/registry selecting approved introspection services |
| Immediate revocation required | Consider introspection/denylist/policy freshness, not local JWT only |
| JWT only, no real opaque tokens | Use simple `jwt()` instead of a mixed architecture |
| Only tokens needing introspection | Use simple `opaqueToken()`, no complex resolver needed |

An important rule: **choose the simplest approach that still satisfies trust, issuer/audience, and revocation requirements**. Mixed support increases configuration and testing surface area; do not add it without a real need.

## 28. Self-Check Questions

**1.** What is the main difference between JWT and opaque tokens?

> How the Resource Server verifies them: JWT uses signature/claims validators and a trusted JWK source; opaque typically uses a trusted introspection endpoint.

**2.** In a single `oauth2ResourceServer` DSL, can you call both `.jwt()` and `.opaqueToken()` so Spring selects automatically?

> No. You need separate `SecurityFilterChain` beans or an `AuthenticationManagerResolver` for request-time selection.

**3.** What is `AuthenticationManagerResolver<HttpServletRequest>` responsible for?

> Selecting the `AuthenticationManager` for the request. The selected provider/decoder/introspector is what proves the token is valid.

**4.** If the two token types have separate routes, what is the simplest approach?

> Two `SecurityFilterChain` beans with clear `securityMatcher` and `@Order`, plus a fallback chain for other URLs.

**5.** When can one endpoint accept both JWT and opaque without format classification?

> When a trusted AS introspection endpoint accepts and validates both access token types per contract.

**6.** Why shouldn't you automatically fall back to opaque when the JWT decoder reports an invalid signature?

> Because it can create an authentication downgrade path and mask issuer/audience/signature errors; token type must be determined on sound grounds.

**7.** Does `token.contains(".")` prove a token is a valid JWT?

> No. Shape is only a hint; a JWT must pass full signature and claims verification.

**8.** Can an opaque token returning `active=true` access every API?

> No. Resource/audience binding, authorities, and business policies are still required.

**9.** Can both branches use the same `SCOPE_orders.read`?

> Yes, if the scope from each AS has equivalent semantics and was genuinely granted.

**10.** Why shouldn't you use `@AuthenticationPrincipal Jwt` on an endpoint shared by both token types?

> Because the default opaque principal is `OAuth2AuthenticatedPrincipal`, not `Jwt`. Use `Authentication` or a domain identity adapter.

**11.** Are two users from two issuers with the same `sub=user-42` the same person?

> Not by default. You must attach the issuer/trusted introspection source namespace.

**12.** Is `hasAuthority("SCOPE_orders.read")` enough to read another tenant's order?

> No. You must check tenant membership, object owner/ACL, and query constraints.

**13.** During a JWKS or introspection service outage, can you create a temporary principal so the API stays up?

> No. If authentication cannot be proven, fail closed or handle the infrastructure error without executing unauthorized actions.

**14.** Does `MockMvc.with(jwt())` test the production JWT decoder and resolver?

> Not by default. It mocks authentication; you need tests with real signed tokens, decoders, and fake JWKS/introspection endpoints.

**15.** If `oauth2Login()` uses a session for browsers, does that automatically support opaque bearer tokens?

> No. OAuth2 Client OIDC Login differs from a Resource Server accepting bearer access tokens; you must explicitly configure security chains and credential flows.

## 29. References

- [Spring Security — Servlet OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): **Supporting both JWT and Opaque Token** section, `AuthenticationManagerResolver` examples, trusted issuers, and dynamic managers.
- [Spring Security — OAuth2ResourceServerConfigurer API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/web/configurers/oauth2/server/resource/OAuth2ResourceServerConfigurer.html): `jwt`, `opaqueToken`, `authenticationManagerResolver`, and Bearer filter configuration.
- [Spring Security — OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): authentication filters and bearer flow.
- [Spring Security — Servlet Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, JWKS, `iss`, scope mapping.
- [Spring Security — Servlet Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection, `active`, principal, authorities.
- [Spring Security — JwtAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationProvider.html): JWT authentication provider.
- [Spring Security — OpaqueTokenAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/OpaqueTokenAuthenticationProvider.html): token introspection provider.
- [Spring Security — BearerTokenAuthenticationFilter API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/authentication/BearerTokenAuthenticationFilter.html): bearer extraction and authentication manager resolution.
- [Spring Security — DefaultBearerTokenResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/web/DefaultBearerTokenResolver.html): HTTP bearer token extraction.
- [Spring Security — ProviderManager API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ProviderManager.html): multiple AuthenticationProviders and exception handling.
- [Spring Security — Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher`, `@Order`, and filter-chain fallback.
- [Spring Security — WebFlux Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html): reactive tenant resolver and API differences.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): HTTP bearer header and authentication errors.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): token `active`, scopes, client/resource context.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): issuer/subject/audience/time claims.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access-token profile and audience.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm/token confusion, validation, and key selection.

**Conclusion:** A Resource Server **can support both JWT and opaque bearer access tokens**, but the authentication architecture must be chosen **explicitly**. If token types belong to distinct routes, use multiple `SecurityFilterChain` beans. If selection must happen at request time in the same chain, use `AuthenticationManagerResolver<HttpServletRequest>` with separately configured `JwtAuthenticationProvider` and `OpaqueTokenAuthenticationProvider`. If the AS can introspect both, a single opaque introspection flow may suffice. In every approach, **routing does not replace verification**, valid tokens must match the expected issuer/audience/type, permissions must never be inferred from format or profile, and tenant/ownership must be enforced at the business layer.
