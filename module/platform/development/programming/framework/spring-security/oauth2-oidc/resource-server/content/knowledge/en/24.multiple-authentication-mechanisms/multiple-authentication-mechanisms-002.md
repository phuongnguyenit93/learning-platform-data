# Selecting an AuthenticationManager Based on Requests and Managed Configuration

In a **Spring Security OAuth 2.0/OIDC Resource Server**, a single application may protect multiple API groups with different credential types and authentication sources. For example, the same application might accept **JWT access tokens** issued by an Authorization Server for partners, **opaque access tokens** requiring introspection for internal APIs, and also serve a browser UI using sessions or administrative endpoints requiring mTLS.

There are two separate questions here: **which mechanism should handle this request?** and **after selecting that mechanism, is the credential genuinely valid and allowed for this resource?** Spring Security provides extension points such as `AuthenticationManagerResolver<HttpServletRequest>` and, in WebFlux, `ReactiveAuthenticationManagerResolver<ServerWebExchange>` to choose the right manager per request. However, a resolver is **not** a standalone authenticator; it only returns the component that will perform authentication.

Core security principle:

> **The request provides data to select an AuthenticationManager from a managed configuration set; the selected AuthenticationManager must verify the credential against the full contract of that mechanism. On failure, do not fall back to a looser mechanism to try your luck.**

This is very different from a dangerous implementation such as: "Read `iss` or `alg` from an unverified JWT, create a decoder/JWKS URL directly from that string; if the JWT is invalid, try introspection; if that still fails, read a cookie or `X-User` header."

This lesson explains in detail how to select a manager by **HTTP request**, trust configuration for JWT/opaque/Basic/session, the relationship with multiple `SecurityFilterChain` beans, the boundary between **resolver / manager / provider**, fail-closed behavior, WebFlux, multi-tenancy, testing, and operations.

## 1. Why Does a Resource Server Need Multiple Authentication Mechanisms?

Consider the Orders Platform system:

| Resource area | Expected credential | Authentication source | Example policy |
|---|---|---|---|
| `/api/partners/**` | `Authorization: Bearer <JWT>` | JWT decoder for a registered partner issuer | `aud=orders-partner-api`, scopes `orders.read`/`orders.write` |
| `/api/internal/**` | `Authorization: Bearer <opaque-token>` | Internal introspection endpoint | `aud=orders-internal-api`, introspection `active=true` |
| `/admin/**` | Browser session after login or mTLS per architecture | Web login provider / certificate validation | Admin roles, session/CSRF or client certificate policy |
| `/actuator/health` | No Bearer token if exposing minimal health only | `permitAll` per deployment | Do not expose sensitive data |

Each credential can represent an identity, but that **does not mean** a token for `/api/partners/**` can be used on `/api/internal/**`. Two APIs might share the scope name `orders.read` while having different audiences, issuers, clients, and tenant boundaries.

### 1.1. Four Things That Must Not Be Mixed into One

```mermaid
flowchart TD
    R["HTTP request + credential"] --> S["SecurityFilterChain selection<br/>by path/condition"]
    S --> T["Authentication mechanism/filter<br/>extracts credential"]
    T --> U["AuthenticationManagerResolver<br/>selects manager from registry"]
    U --> V["AuthenticationManager / Provider<br/>verifies credential"]
    V --> W{"Token/credential valid?"}
    W -->|"No"| X["Authentication failure<br/>do not try less secure mechanism"]
    W -->|"Yes"| A["Authentication + authorities"]
    A --> B{"HTTP/method rule allowed?"}
    B -->|"No"| C["403 / access denied"]
    B -->|"Yes"| D["Domain authorization<br/>owner/tenant/state"]
    D --> E["Business operation if allowed"]
```

Roles:

- **`SecurityFilterChain`:** decides which filters apply to a request; when multiple chains exist, Spring Security picks the matching chain in order.
- **Authentication filter:** extracts the credential from the HTTP request, e.g., a Bearer token from `Authorization`.
- **`AuthenticationManagerResolver`:** selects a **manager** from a trusted request/context per policy.
- **`AuthenticationManager`:** authenticates the Authentication request; may delegate to an `AuthenticationProvider`.
- **`AuthorizationManager` or method security:** decides access after Authentication has been verified.
- **Domain policy:** checks owner, tenant, order status, and object-level permissions.

An `AuthenticationManagerResolver` picking the right manager does not automatically produce `200 OK`. The credential must still pass signature/introspection, issuer/audience, scope, and business rules.

## 2. `AuthenticationManager`, `AuthenticationProvider`, and `AuthenticationManagerResolver`

### 2.1. `AuthenticationManager` Performs Authentication

Servlet API:

```java
package org.springframework.security.authentication;

import org.springframework.security.core.Authentication;

public interface AuthenticationManager {
    Authentication authenticate(Authentication authentication)
        throws AuthenticationException;
}
```

This is an illustrative signature; import the interface provided by Spring Security rather than redefining it. The input is an **unverified** `Authentication`, such as `BearerTokenAuthenticationToken`. The output is an authenticated `Authentication` or an appropriate `AuthenticationException` on failure.

Common implementations:

- `ProviderManager`: manages a list of `AuthenticationProvider` instances.
- A lambda/adapter forwarding `authenticate` calls to a specific provider.
- A manager configured by the framework for form login, HTTP Basic, or a custom mechanism.

### 2.2. `AuthenticationProvider` Handles One Type of Authentication

Examples:

| Provider | Common input | How it proves validity |
|---|---|---|
| `JwtAuthenticationProvider` | `BearerTokenAuthenticationToken` | `JwtDecoder` verifies signature and validators |
| `OpaqueTokenAuthenticationProvider` | `BearerTokenAuthenticationToken` | `OpaqueTokenIntrospector` queries Authorization Server |
| `DaoAuthenticationProvider` | `UsernamePasswordAuthenticationToken` | UserDetails/PasswordEncoder |
| Controlled custom provider | Custom Authentication type | Dedicated verification contract; never trusts caller claims |

Do not confuse **"provider supports an Authentication type"** with **"provider is responsible for validating the endpoint's token profile"**. Both JWT and opaque providers can handle `BearerTokenAuthenticationToken`, yet there is no safe reason to arbitrarily try both for every Bearer string.

### 2.3. `AuthenticationManagerResolver` Selects the Manager

General Servlet interface:

```java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import jakarta.servlet.http.HttpServletRequest;

AuthenticationManagerResolver<HttpServletRequest> resolver =
    request -> {
        // Select a preconfigured manager.
        return selectTrustedManager(request);
    };
```

`AuthenticationManagerResolver<C>` essentially has a `resolve(C context)` method returning an `AuthenticationManager`. It does not take a password or JWT and check signatures itself. It decides **which manager should be called** for that request.

In WebFlux, there is a semantically equivalent asynchronous interface:

```java
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> Mono.just(selectedReactiveManager);
```

`resolve(...)` returns a `Mono<ReactiveAuthenticationManager>`, allowing manager selection from an asynchronous source if the architecture requires it, but **never** allowing unverified data to be used as proof of authorization.

### 2.4. Manager Resolver vs. Multi-Provider `ProviderManager`

`ProviderManager` can hold multiple providers and search sequentially for a provider matching an Authentication token. In contrast, a resolver selects **one manager per request context**.

```text
ProviderManager([Provider A, Provider B]):
  The same input Authentication is processed across a chain of providers.

AuthenticationManagerResolver(request):
  Select Manager A for route A.
  Select Manager B for route B.
  Each manager validates the credential against its own contract.
```

Since JWT and opaque both originate as Bearer tokens, using a route/contract-based resolver helps avoid unintended "JWT failed → opaque fallback" logic. If you try to put both `JwtAuthenticationProvider` and `OpaqueTokenAuthenticationProvider` in a single `ProviderManager`, you must understand the exact ordering, `supports` behavior, and exception/parent manager handling; do not assume every token will be safely routed according to its type.

## 3. What Should Manager Selection Be Based On?

A resolver can observe the HTTP request, but **not all request data has the same trust level**.

| Data used to select manager | Usable? | Conditions |
|---|---|---|
| **Matched route/path** | Usually suitable | Use matching/normalization consistent with the security chain, mapped to managed config |
| HTTP method + route | Yes | Endpoint policy must be clear; never pick weaker auth just for GET |
| Server-defined endpoint group | Very suitable | Defined by server-side configuration/routing |
| Host/subdomain | Yes, with caution | Must control Host/forwarded headers and trusted proxies |
| Tenant from URL | Yes, to look up in registry | Tenant slug alone does not prove caller permissions |
| `iss` in an unverified JWT | **Hint** only | Issuer allowlist; final decoder must verify signature + `iss` + audience |
| `kid`, `alg`, `jku` in JWT header | Insufficient for trust decisions | Do not fetch arbitrary keys; bind key/alg to the selected issuer |
| Client `X-Auth-Mechanism: opaque` header | Untrusted as sole policy | Easily changed arbitrarily by clients |
| Session cookie | Yes, in browser chain | Do not let pure Bearer APIs accidentally use sessions |
| mTLS client identity verified by TLS terminator | Yes, per contract | Must have a trusted proxy boundary; never trust client-sent certificate headers |

### 3.1. Selection Is Routing, Not Credential Verification

Example:

```http
GET /api/partners/orders/123 HTTP/1.1
Authorization: Bearer attacker-controlled-string
```

The resolver can choose the **partner JWT manager** because the path starts with `/api/partners/`. But that **does not mean** the token is a valid JWT, issued by the partner issuer, or has the read scope. The JWT manager must verify every condition itself.

Conversely, if a request calls `/api/internal/orders/123`, the resolver selects the **internal opaque manager**. A partner JWT, even with a valid signature from the partner issuer, must not be implicitly tried against the internal AS.

### 3.2. Do Not Let Clients Choose a Weaker Authentication Policy

Anti-pattern:

```java
// DO NOT DO THIS: caller decides which manager to use.
String mode = request.getHeader("X-Auth-Mode");
if ("legacy".equals(mode)) {
    return permissiveLegacyManager;
}
return strictJwtManager;
```

An attacker only needs to send `X-Auth-Mode: legacy` to enter the less restrictive mechanism. If multiple mechanisms are legitimately required, selection must rely on **server-controlled routes/policies**, or a trusted token-profile binding verified by the corresponding manager.

### 3.3. Do Not Build an AuthenticationManager from Untrusted Input

Anti-pattern:

```java
String issuer = request.getParameter("issuer");
JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
return new JwtAuthenticationProvider(decoder)::authenticate;
```

This can cause the server to perform metadata/JWKS discovery against an attacker-supplied URL, creating **SSRF, DoS, and trust injection** risks. Trusted managers must come from **managed issuers/endpoints**, never initialized from arbitrary per-request URLs.

## 4. Two Architectural Strategies: Multiple Chains or One Resolver?

There are two common ways to structure this. Both can work well; choose based on the number of resource groups and how isolated the authentication policies are.

### 4.1. Multiple `SecurityFilterChain` Beans for Independent Areas

```text
/api/partners/**  -> chain A -> JWT resource server
/api/internal/**  -> chain B -> opaque token resource server
/admin/**         -> chain C -> browser form login / session
/...              -> fallback chain -> deny
```

Advantages:

- Each chain has clear filters, CSRF/session policy, entry points, and authentication.
- Easy to separate browser sessions from stateless Bearer APIs.
- No need to write a custom resolver if each route group uses only one mechanism.

Disadvantages:

- Multiple chains require accurate management of `@Order` and `securityMatcher`.
- New routes might fall into a different chain or remain unprotected if a fallback is missing.
- Configuration duplication if API areas share most rules.

### 4.2. One Bearer Chain with `AuthenticationManagerResolver`

```text
/api/** -> single SecurityFilterChain
            |
            v
       BearerTokenAuthenticationFilter
            |
            v
       AuthenticationManagerResolver
         /                     \
        /                       \
   /api/partners/**       /api/internal/**
     JWT manager           Opaque manager
        \                       /
         \                     /
          v                   v
             Authentication
                   |
                   v
       HTTP/method/domain authorization
```

Advantages:

- A single stateless API area shares one Bearer filter.
- Routes select managers from a controlled registry.
- Fits well when multiple Bearer issuers/tenants/mechanisms share an endpoint surface with clear selection rules.

Disadvantages:

- The resolver becomes a sensitive configuration component; route coverage must be complete.
- A manager selection bug can verify credentials in the wrong context.
- **Non-Bearer** mechanisms (Basic, form login, mTLS) still need appropriate filters/chains; a Bearer resolver does not handle every credential type automatically.

### 4.3. Decision Rules

| Need | Usually reasonable direction |
|---|---|
Browser session and Bearer API | **Split `SecurityFilterChain`** because session/CSRF/entry points differ |
| Two API groups both use Bearer, but JWT vs. opaque differ | Multiple chains **or** route-based Bearer resolver |
| Multiple JWT issuers in the same API | `JwtIssuerAuthenticationManagerResolver` or trusted manager registry |
| Multiple tenants with route-based selection policy | Custom resolver mapping route → trusted registry |
| One route allowing Basic or Bearer per contract | Explicitly design multiple authentication filters; never assume Bearer resolver handles Basic |
| All requests use a single JWT issuer | One `JwtDecoder`/chain is usually enough; no complex resolver needed |

**Do not add multiple mechanisms just because the framework supports them.** The more authentication paths exist, the harder it is to prove there are no fallbacks or downgrades.

## 5. Managed Configuration: The Source of Truth for Manager Selection

Suppose Orders Platform's policy is centrally managed:

```yaml
# application.yml - configuration example, no real credentials
security:
  partner:
    issuer: https://partner-idp.example.com/realms/partners
    jwk-set-uri: https://partner-idp.example.com/realms/partners/jwks
    audience: orders-partner-api
  internal:
    introspection-uri: https://identity.example.com/oauth2/introspect
    client-id: orders-internal-resource-server
    client-secret: "${INTERNAL_INTROSPECTION_CLIENT_SECRET}"
    audience: orders-internal-api
```

URLs are illustrative only. In practice, use endpoints published by the issuer and vetted; do not guess JWKS URLs by arbitrary string concatenation from the issuer.

A managed registry should describe:

1. **Resource group/route matcher** specifying which manager applies.
2. **Authentication mechanism**: JWT, opaque introspection, Basic/session/mTLS.
3. **Trust source**: exact issuer, JWKS URI, introspection URL, client credentials.
4. **Token profile**: signing algorithms, audience, expiry/not-before, token type, scope catalog.
5. **Tenant binding**: which tenant maps to which issuer/manager.
6. **Error policy**: unknown route/issuer, missing token, invalid token, AS unavailable.
7. **Lifecycle**: onboarding, revocation/offboarding, key/secret rotation, cache invalidation.

### 5.1. Managed Means Who Is Allowed to Modify It?

A configuration file in Git or a database **does not automatically become trustworthy**. You need to know:

- Who has permission to add a new issuer/introspection URL?
- Can a tenant admin insert an issuer they control into another tenant's trusted set?
- Is configuration reviewed/validated before deployment?
- Is there consistent distribution across all replicas?
- When a tenant is suspended/offboarded, are cached managers evicted from the trust set?

In particular, if a customer is allowed to register an arbitrary JWKS endpoint and the API uses it to verify tokens with system-wide privileges, they can self-sign accepted credentials. **Registration** must bind permission scope to a specific tenant, issuer, and resource—you cannot just store a URL and consider it safe.

### 5.2. Do Not Hard-Code Secrets

```yaml
client-secret: "${INTERNAL_INTROSPECTION_CLIENT_SECRET}"
```

reads from environment configuration or a secret manager. Never commit real secrets, log them in error responses/logs, or pass them in query strings. During credential rotation, the Resource Server must refresh the manager/introspector properly according to its version and deployment.

### 5.3. Route Configuration Needs Deny-by-Default

Example:

```text
KNOWN:
  /api/partners/**
  /api/internal/**

UNKNOWN:
  /api/experimental/**
```

New routes must **never** fall into a "permissive default manager". For a resolver, an unknown route must lead to rejection or a manager with an explicit deny policy; at the same time, HTTP authorization rules should include `anyRequest().denyAll()`. Never let a missing mapping become a reason to fall back to an admin/service manager.

## 6. Building a JWT AuthenticationManager for the Partner Area

In Servlet Spring Security 6.x, you can build a `JwtAuthenticationProvider` with a `NimbusJwtDecoder` configured from **trusted settings**.

### 6.1. JWT Decoder Verifying Issuer and Audience

```java
import java.util.List;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtAuthenticationProvider;

public final class PartnerJwtManagers {

    public static AuthenticationManager create(
            String issuer,
            String jwkSetUri,
            String audience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            // Valid only if the partner AS signs with RS256 per contract.
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> defaultsAndIssuer =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Unexpected JWT audience",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                defaultsAndIssuer,
                audienceValidator));

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);

        return provider::authenticate;
    }
}
```

Explanation:

- `withJwkSetUri` takes a **managed URL**, not one from `iss` or `jku` of an unverified token.
- `jwsAlgorithm(RS256)` is an illustrative policy and must match the actual algorithm agreed upon with the AS. Never accept `alg=none` or unapproved algorithms.
- `createDefaultWithIssuer(issuer)` applies the version-appropriate default validators, including issuer and timestamp checks per Spring Security's contract.
- The audience validator proves the token is intended for `orders-partner-api`.
- `setJwtValidator(...)` **replaces the current validator set**; the example intentionally combines default+issuer+audience so audience-only validation is not accidentally left alone.
- `JwtAuthenticationProvider` returns an authenticated result only after the decoder verifies the token. Authorities like `SCOPE_orders.read` are mapped from the verified token by the provider's converter.

Unused imports in the example can be removed in a real project. For an **RFC 9068** token profile, you may need a `typ`/token-use validator and other required attributes. Do not treat signature + issuer + audience as the entirety of every AS policy.

### 6.2. Why Is an Issuer Validator Needed Even After the Resolver Picks the Partner Manager?

The resolver chose the manager because the request called `/api/partners/**`. That does not prove the JWT was genuinely issued by the partner. A JWT from another issuer might have the same `aud` and `scope`, or use misconfigured key material. **Each manager must verify the final issuer**, rather than relying on the manager-selection decision.

```text
request path = /api/partners/orders/123
   |
   v
choose partnerJwtManager
   |
   v
partner decoder:
  signature valid with partner keys?
  verified iss == configured partner issuer?
  aud contains orders-partner-api?
  exp/nbf valid?
   |
   v
JwtAuthenticationToken when all conditions hold
```

If any required condition fails, the manager must **reject authentication**. Do not send the failed token to the opaque manager to see if the internal AS happens to accept it.

## 7. Building an Opaque AuthenticationManager for the Internal API

Opaque access tokens are validated via **RFC 7662 Token Introspection**. Spring Security Servlet provides `OpaqueTokenAuthenticationProvider` backed by `OpaqueTokenIntrospector`.

Example for Spring Security 6.x versions having the corresponding `NimbusOpaqueTokenIntrospector` constructor:

```java
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication
    .OpaqueTokenAuthenticationProvider;
import org.springframework.security.oauth2.server.resource.introspection
    .NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection
    .OpaqueTokenIntrospector;

public final class InternalOpaqueManagers {

    public static AuthenticationManager create(
            String introspectionUri,
            String clientId,
            String clientSecret) {

        OpaqueTokenIntrospector introspector =
            new NimbusOpaqueTokenIntrospector(
                introspectionUri,
                clientId,
                clientSecret);

        OpaqueTokenAuthenticationProvider provider =
            new OpaqueTokenAuthenticationProvider(introspector);

        return provider::authenticate;
    }
}
```

In newer Spring Security lines, `SpringOpaqueTokenIntrospector` and its builder may be preferred; choose the API **matching your project's version** rather than forcing deprecated or removed constructors. The architecture remains **trusted introspection delegate → provider → manager**.

### 7.1. An Active Token Is Not Enough

Example introspection response:

```json
{
  "active": true,
  "scope": "orders.read orders.update",
  "iss": "https://identity.example.com",
  "aud": ["orders-internal-api"],
  "sub": "service-order-worker",
  "client_id": "order-worker"
}
```

`active=true` only states that the AS considers the token active. The API still needs policies on:

- `aud=orders-internal-api` or equivalent resource binding.
- `iss` (if returned by the AS) or another source-of-truth binding from the introspection service.
- Token type/client identity and tenant per contract.
- Authorities mapped from `scope`, defaulting `orders.read` to `SCOPE_orders.read`.
- Business permissions on each object.

**Do not assume** `OpaqueTokenIntrospector` in every version automatically validates all `aud`/`iss` extensions required by the app. If needed, wrap the delegate in a policy introspector **after the delegate has validated the token**.

### 7.2. Decorator Checking Audience When the AS Returns Metadata

```java
import java.util.Collection;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection
    .BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection
    .OpaqueTokenIntrospector;

public final class AudienceCheckingIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final String requiredAudience;

    public AudienceCheckingIntrospector(
            OpaqueTokenIntrospector delegate,
            String requiredAudience) {
        this.delegate = delegate;
        this.requiredAudience = requiredAudience;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        // Verify credential via AS first.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Object raw = principal.getAttribute("aud");
        boolean allowed =
            (raw instanceof String value
                && requiredAudience.equals(value))
            || (raw instanceof Collection<?> values
                && values.contains(requiredAudience));

        if (!allowed) {
            throw new BadOpaqueTokenException(
                "Token audience is not accepted");
        }

        return principal; // Preserve SCOPE_... authorities from delegate.
    }
}
```

In manager configuration, wrap it:

```java
OpaqueTokenIntrospector remote =
    new NimbusOpaqueTokenIntrospector(uri, clientId, secret);

OpaqueTokenIntrospector checked =
    new AudienceCheckingIntrospector(
        remote, "orders-internal-api");

return new OpaqueTokenAuthenticationProvider(checked)::authenticate;
```

`uri`, `clientId`, and `secret` must come from trusted configuration. `aud` is not a mandatory field returned by every AS per RFC 7662. If the AS does not return audience and the API requires token-resource binding, there must be an **equivalent assurance contract** (e.g., the endpoint only reports active for the right resource/client); never simply drop the check because the provider omits the field.

### 7.3. Introspection Timeout Differs from an Invalid Token

| Case | Meaning | Handling |
|---|---|---|
| `active:false` | AS rejects the token | Authentication fails |
| `active:true` but wrong audience | Token not intended for this API | Authentication/policy fails |
| AS DNS/TLS/timeout/5xx | No reliable authentication proof | **Fail closed**; do not create a fallback principal |
| AS returns scope metadata but token lacks endpoint permission | Authentication may succeed, authorization fails | Typically HTTP 403 |

Do not write `catch(Exception) -> new SimpleGrantedAuthority("SCOPE_orders.read")`. Keeping the API running while the AS is down is never more important than blocking forged or revoked tokens.

## 8. Building a Route-Based Servlet Resolver from Managed Config

Once you have the **partner JWT manager** and **internal opaque manager**, connect them with `AuthenticationManagerResolver<HttpServletRequest>`.

One way in Spring Security 6.x is using `RequestMatcher`:

```java
import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.web.util.matcher.AntPathRequestMatcher;
import org.springframework.security.web.util.matcher.RequestMatcher;

@Configuration
public class ManagedBearerResolverConfiguration {

    @Bean
    AuthenticationManagerResolver<HttpServletRequest>
            managedBearerResolver(
                @Qualifier("partnerJwtManager")
                AuthenticationManager partnerJwtManager,
                @Qualifier("internalOpaqueManager")
                AuthenticationManager internalOpaqueManager) {

        // For Spring Security 6.x. Newer lines may recommend
        // PathPatternRequestMatcher instead.
        RequestMatcher partner =
            new AntPathRequestMatcher("/api/partners/**");
        RequestMatcher internal =
            new AntPathRequestMatcher("/api/internal/**");

        return request -> {
            if (partner.matches(request)) {
                return partnerJwtManager;
            }
            if (internal.matches(request)) {
                return internalOpaqueManager;
            }

            // No fallback to a broader-privilege manager.
            throw new BadCredentialsException(
                "No authentication manager for protected resource");
        };
    }
}
```

**Version note:** `AntPathRequestMatcher` has been transitioning toward path-pattern matchers in newer versions. To maintain consistent match semantics, use the matcher type supported by **your project's Spring Security version** and aligned with actual `securityMatcher`/routing. Do not scatter custom regex/`startsWith` checks when the app has context paths, servlet mappings, or complex encoded paths.

### 8.1. Manager Beans Created from Managed Settings

Example beans for the code above:

```java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.authentication.AuthenticationManager;

@Configuration
public class ManagedAuthenticationManagers {

    @Bean("partnerJwtManager")
    AuthenticationManager partnerJwtManager(
            @Value("${security.partner.issuer}") String issuer,
            @Value("${security.partner.jwk-set-uri}") String jwks,
            @Value("${security.partner.audience}") String audience) {

        return PartnerJwtManagers.create(
            issuer, jwks, audience);
    }

    @Bean("internalOpaqueManager")
    AuthenticationManager internalOpaqueManager(
            @Value("${security.internal.introspection-uri}") String uri,
            @Value("${security.internal.client-id}") String clientId,
            @Value("${security.internal.client-secret}") String secret,
            @Value("${security.internal.audience}") String audience) {

        OpaqueTokenIntrospector remote =
            new NimbusOpaqueTokenIntrospector(
                uri, clientId, secret);
        OpaqueTokenIntrospector checked =
            new AudienceCheckingIntrospector(remote, audience);

        return new OpaqueTokenAuthenticationProvider(
            checked)::authenticate;
    }
}
```

Imports for `OpaqueTokenIntrospector`, `NimbusOpaqueTokenIntrospector`, and `OpaqueTokenAuthenticationProvider` are as shown in previous sections. These are illustrative classes combined into a project with matching dependency configuration; when using Spring Security 7.x, check the new APIs if older implementations were replaced.

**Never** pull issuer/audience/client secret from a request's form body to construct a manager. The `@Value` fields in the example read from managed server configuration.

### 8.2. Wiring the Resolver into the Resource Server DSL

```java
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
public class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurityChain(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest>
                managedBearerResolver)
            throws Exception {

        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(
                    HttpMethod.GET, "/api/partners/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.POST, "/api/partners/orders")
                    .hasAuthority("SCOPE_orders.create")
                .requestMatchers(
                    HttpMethod.GET, "/api/internal/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(
                    HttpMethod.PUT, "/api/internal/orders/**")
                    .hasAuthority("SCOPE_orders.update")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(
                    managedBearerResolver))
            .build();
    }
}
```

Key points to remember:

1. `securityMatcher("/api/**")` determines which requests are handled by the API chain.
2. `oauth2ResourceServer(...authenticationManagerResolver...)` configures the **Bearer filter** to select a manager for the request.
3. `authorizeHttpRequests` checks **post-authentication authorities**; do not use the resolver to decide business permissions directly.
4. `SessionCreationPolicy.STATELESS` expresses the intent not to load an existing HTTP session's SecurityContext for Bearer API authentication.
5. `anyRequest().denyAll()` blocks unmapped routes; the resolver also has no fallback.
6. Other endpoints in the application need their own chains or a fallback chain; if no chain matches, requests may not be protected by Spring Security as expected.

CSRF is disabled in this example assuming the API only uses Bearer headers not automatically sent by browsers. If the app also uses cookie/session/Basic browser credentials for write requests, evaluate CSRF separately; do not copy this configuration for web login.

### 8.3. What Happens When a Client Sends the Wrong Bearer Token Type?

For example:

```text
Request: GET /api/partners/orders/123
Token: opaque token used for internal API

Resolver -> partner JWT manager
JWT decoder -> invalid token / wrong profile
Response -> authentication failure
Internal opaque manager is not tried.
```

And:

```text
Request: GET /api/internal/orders/123
Token: JWT used for partner API

Resolver -> internal opaque manager
Introspection endpoint -> active=false or
token-resource policy rejects
Response -> authentication failure
Partner JWT manager is not tried.
```

If the internal AS **also** accepts partner JWTs as active without audience binding, the problem lies in the **introspection/token-resource contract**. Never rely on "a JWT isn't opaque" to assume a token will definitely be rejected.

## 9. Not Every Mechanism Can Be Handled by a Bearer Manager Resolver Alone

`BearerTokenAuthenticationFilter` (Servlet) or WebFlux's Bearer authentication path is triggered when the request carries a configured Bearer credential. A resolver inside `oauth2ResourceServer` **does not automatically extract**:

- `Authorization: Basic ...`;
- Form username/password;
- HTTP session cookies;
- mTLS client certificates;
- API keys from custom headers;
- OIDC login authorization code callbacks.

These mechanisms require **their corresponding authentication filters/flows**, which may have their own `AuthenticationManager` and a different resolution strategy if supported by the framework/extension.

### 9.1. Separating Browser Form Login and Stateless API

A clean design:

```text
@Order(1) /api/**  -> Bearer Resource Server + managed resolver
@Order(2) /web/**  -> formLogin + HTTP session + CSRF
@Order(3) /**      -> deny-by-default or explicit policy
```

In the browser:

```http
GET /web/account
Cookie: JSESSIONID=...
```

The server can restore Authentication from the session.

On the API:

```http
GET /api/partners/orders/123
Authorization: Bearer eyJ...
```

The API validates the token **of the current request**. Never let a `JSESSIONID` from a web session accidentally satisfy a Bearer API requirement just because they share a host.

### 9.2. Basic and Bearer Can Coexist, But Require Explicit Policy

In an app with both `httpBasic()` and `oauth2ResourceServer()` in the same chain, the filters can handle different `Authorization` schemes. However, that **does not allow** arbitrarily downgrading policy when a JWT is invalid:

```text
Authorization: Bearer invalid-jwt
    -> Bearer filter rejects
    -> MUST NOT turn into Basic/anonymous with privileges.
```

If an endpoint is strictly for service-to-service Bearer calls, do not enable Basic just for "quick test access" without justification. If an endpoint legitimately accepts two mechanisms, explicitly define **whether both mechanisms carry equivalent privileges**, how principals map, and how auditing works.

### 9.3. mTLS and Forwarded Certificate Headers

mTLS authentication typically relies on TLS client authentication and X.509 handling, not just a Bearer `AuthenticationManagerResolver`. If TLS terminates at a proxy, the application must have a **trust contract** for the client certificate/identity from the proxy and block clients from spoofing headers. Never read an arbitrary `X-Client-Cert` header and mint an admin Authentication.

### 9.4. API Keys Need Their Own Token Type and Credential Store

An API key in `X-API-Key` is a distinct mechanism. A custom filter can convert it into a dedicated Authentication token for a manager that checks key hash/expiry/owner. Do not stuff that API key string into a `BearerTokenAuthenticationToken` hoping the JWT/opaque provider knows what to do; and never grant all scopes just because a key exists.

## 10. Multiple JWT Issuers: Use a Dedicated Resolver When Appropriate

A route group may accept JWTs from multiple trusted issuers:

```text
/api/partners/**
   -> Partner A issuer
   -> Partner B issuer
   -> Partner C issuer
```

In that case, selection is not necessarily JWT vs. opaque by path. Within the **same JWT group**, you can use Servlet's `JwtIssuerAuthenticationManagerResolver`:

```java
import org.springframework.security.oauth2.server.resource.authentication
    .JwtIssuerAuthenticationManagerResolver;

JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://partner-a.example.com/issuer",
        "https://partner-b.example.com/issuer"
    );
```

The resolver can read the unverified `iss` claim as a **routing hint**. Mandatory conditions:

- The issuer value must match the application's **trusted list**.
- The selected manager/decoder must verify the signature and check the **final issuer**.
- The API's audience/token profile must still be verified.
- Never instantiate a decoder for an arbitrary issuer URL from a bearer token.
- The requested tenant must be bound to the verified issuer/actor.

### 10.1. Routing by Unverified Issuer Is Not "Trusting the Issuer"

Suppose an attacker crafts a self-asserted JWT:

```json
{
  "iss": "https://partner-a.example.com/issuer",
  "sub": "admin",
  "scope": "orders.delete"
}
```

Even if the router selects manager A, A still must verify the signature against JWKS A and validate issuer/audience. If the attacker lacks the true signing key, the token is rejected. A resolver that merely compares the `iss` string and creates an Authentication from claims **is a critical vulnerability**.

### 10.2. Same `kid` Does Not Mean Same Issuer

The JWT header `kid` is only a hint to pick a key **within a trusted key set**. Two issuers can both use `kid=key-1`. Never use `kid` to look up any key in a global map and accept a signature without checking the issuer. Look up keys only inside the trusted JWKS source of the selected manager.

### 10.3. Audience Validators Must Apply to Every Issuer

If a custom multi-issuer resolver builds `JwtAuthenticationProvider` instances from separate decoders, **every decoder** must have issuer/time/audience validators. Do not assume Boot's `spring.security.oauth2.resourceserver.jwt.audiences` automatically attaches to every decoder you instantiate manually.

A valid JWT intended for `billing-api` must not be accepted at `orders-api` just because it shares the same issuer and similar scope strings.

## 11. Multi-Tenancy: Route, Issuer, Principal, and Business Tenant

Consider the request:

```http
GET /api/tenants/alpha/orders/123
Authorization: Bearer JWT_FROM_BETA
```

You might have:

- Route tenant: `alpha`.
- JWT issuer hint: `beta` (untrusted when first read).
- Verified issuer: `beta` (after the right decoder verifies it).
- Claim `tenant_id=beta` or separate domain membership.

If the system models issuer beta as serving only tenant beta, **even a valid beta JWT must not read tenant alpha**.

### 11.1. Authentication Success Is Not Enough to Access a Tenant

```text
JWT beta:
  signature valid
  issuer beta valid
  audience orders-api valid
  scope orders.read present

Request:
  tenant alpha

Result:
  Authentication may succeed
  Tenant authorization MUST DENY if beta lacks alpha access
```

This is different from a manager-selection failure. The resolver only chooses the manager; the **business tenant** must be checked using the verified principal and authoritative business data.

### 11.2. Identity Keys Need the Issuer

Two different issuers can issue tokens with the same `sub=user-842`. The system should not treat them as the same identity merely because the subject matches. A safe identity key usually starts as:

```text
IdentityKey = (verifiedIssuer, subject)
```

Then:

```text
Permission = IdentityKey + tenant membership
             + scopes/roles + object state
```

When one issuer serves multiple tenants, check `tenant_id`/membership per contract. When one user is linked across multiple issuers, account linking must be a controlled process, not inferred from matching email addresses.

### 11.3. Who Is Allowed to Modify the Tenant Registry?

A tenant admin might be allowed to request IdP changes for **the tenant they manage**, but that must not let them add an issuer privileged across all tenants. Selecting a manager by tenant slug must:

- Read config from an admin-authorized registry.
- Scope the created manager to the corresponding resource/tenant.
- Validate audience, issuer, and policy objects.
- Support auditing, onboarding/offboarding, and rollback.

"The config is stored in the database" does not replace checking **who has permission to edit the config**.

## 12. Fail-Closed Behavior and Prohibiting Downgrade/Fallback

In a multi-mechanism system, the biggest bug is not necessarily "failing to authenticate a token", but **a token rejected by a strong mechanism getting accepted unintentionally by another mechanism**.

### 12.1. Anti-Pattern: JWT Failed → Introspection Fallback

```java
// DO NOT DO THIS as a default policy.
try {
    return jwtManager.authenticate(bearer);
} catch (AuthenticationException invalidJwt) {
    return opaqueManager.authenticate(bearer);
}
```

Risks:

- A JWT rejected for wrong issuer/audience/expiry might be accepted by a loosely configured introspection endpoint.
- One token might accidentally be valid in both mechanisms with different semantics.
- A caller can deliberately craft a token to trigger the weaker branch.
- Logs/metrics become ambiguous about which mechanism granted access.

If a system genuinely supports **two token profiles on the same endpoint**, it must have a **safe routing contract**: how credential profiles are distinguished, trust sources, per-profile audiences, final verification results, and negative tests. Never turn exception fallback into a router.

### 12.2. Anti-Pattern: Missing Mapping Selects an Admin Manager

```java
return request -> {
    AuthenticationManager manager =
        managedRoutes.get(extractRouteKey(request));
    return manager != null ? manager : adminManager;
};
```

If someone accesses a new route or crafts an unusual path, they could enter a manager not meant for that route. Unknown routing conditions must **reject**, never choose higher privileges.

### 12.3. Anti-Pattern: Introspection Failure Creates a Guest with Scopes

```java
// DO NOT DO THIS:
try {
    return opaqueIntrospector.introspect(token);
} catch (Exception upstreamFailure) {
    return guestPrincipalWithScope("orders.read");
}
```

An unresponsive AS is not proof that a token is active. To reduce latency or AS dependency, use caching with clear TTL, revocation, and resource-binding rules—never mint permissions from an infrastructure error.

### 12.4. Manager Resolvers Do Not Create Authentication Directly

This is the ideal trust boundary:

```text
resolver:
  request -> manager (selection only)

manager:
  credential -> verified Authentication or failure

authorization:
  verified Authentication + resource -> allow/deny
```

Do not collapse all three into a single lambda that reads a header and returns a `JwtAuthenticationToken` with `ROLE_ADMIN` to "optimize away" the decoder.

## 13. HTTP Status Codes and Where Errors Happen

| Scenario | Rejecting component | Typical HTTP status |
|---|---|---|
| Protected route without Bearer token | Authentication entry point | 401 |
| Malformed Bearer token | Bearer resolver/filter | 401 |
| Resolver has no manager for protected route | Authentication/routing | 401 or handler error, **never allow** |
| Partner JWT invalid signature/issuer/audience | JWT manager/decoder | 401 |
| Internal opaque token `active=false` | Opaque manager/introspector | 401 |
| Introspection AS timeout/5xx | Authentication infrastructure unavailable | Do not grant access; status depends on exception mapping |
| Valid token missing `SCOPE_orders.read` | HTTP/method authorization | 403 |
| Valid token but different tenant/owner | Domain authorization | 403/404 per policy |
| Client sends Basic to Bearer-only route | Bearer-only authentication rejects credential | Usually 401 |
| Browser session from `/web/**` sent to Bearer-only API | API chain does not rely on sessions | Must reject if no Bearer token |

**Do not assume** all introspection infrastructure errors default to 401; some service-unavailable exceptions may pass through another handler. What is mandatory is never creating an authenticated principal without proof.

### 13.1. Do Not Let a Handler "Rescue" Security Errors

A global exception handler can customize bodies/statuses, but must never:

```text
JwtValidationException
  -> return 200 with fallback user

AccessDeniedException
  -> call controller anyway
```

When Authentication fails, the request must not cross the security boundary into sensitive operations. Distinguish HTTP status presentation from the actual deny decision.

## 14. WebFlux: `ReactiveAuthenticationManagerResolver<ServerWebExchange>`

In reactive applications, the resolver returns a **`Mono<ReactiveAuthenticationManager>`** instead of a direct manager.

Example of a WebFlux API with two zones:

```text
/api/partners/** -> ReactiveJwtAuthenticationManager
/api/internal/** -> OpaqueTokenReactiveAuthenticationManager
```

### 14.1. Configuring Two Managed Managers

```java
import java.util.List;

import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication
    .JwtReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.authentication
    .OpaqueTokenReactiveAuthenticationManager;
import org.springframework.security.oauth2.server.resource.introspection
    .ReactiveOpaqueTokenIntrospector;

public final class ReactiveManagerFactory {

    public static ReactiveAuthenticationManager jwt(
            String issuer, String jwks, String audience) {
        NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwks).build();

        OAuth2TokenValidator<Jwt> audValidator = token ->
            token.getAudience().contains(audience)
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token",
                        "Wrong audience",
                        null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(issuer),
                audValidator));

        return new JwtReactiveAuthenticationManager(decoder);
    }

    public static ReactiveAuthenticationManager opaque(
            ReactiveOpaqueTokenIntrospector introspector) {
        return new OpaqueTokenReactiveAuthenticationManager(
            introspector);
    }
}
```

The reactive JWT path must also restrict algorithms per the AS contract if needed; the example uses Spring Security's default builder and token validators—do not assume all algorithms/claim profiles required by the API policy are checked automatically. `ReactiveOpaqueTokenIntrospector` must be a non-blocking implementation that genuinely verifies tokens via the AS.

### 14.2. Path-Based Resolver in WebFlux

```java
import org.springframework.context.annotation.Bean;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.ReactiveAuthenticationManager;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.web.server.ServerWebExchange;
import reactor.core.publisher.Mono;

@Bean
ReactiveAuthenticationManagerResolver<ServerWebExchange>
    managedReactiveResolver(
        @Qualifier("reactivePartnerJwtManager")
        ReactiveAuthenticationManager partner,
        @Qualifier("reactiveInternalOpaqueManager")
        ReactiveAuthenticationManager internal) {

    return exchange -> {
        String path =
            exchange.getRequest().getPath().pathWithinApplication().value();

        // Illustrative example; production should use matchers aligned
        // with SecurityWebFilterChain pathMatchers.
        if (path.equals("/api/partners")
                || path.startsWith("/api/partners/")) {
            return Mono.just(partner);
        }
        if (path.equals("/api/internal")
                || path.startsWith("/api/internal/")) {
            return Mono.just(internal);
        }
        return Mono.error(new BadCredentialsException(
            "No configured manager for requested resource"));
    };
}
```

`@Qualifier` needs to be imported from `org.springframework.beans.factory.annotation`. The `reactivePartnerJwtManager`/`reactiveInternalOpaqueManager` beans are built with `ReactiveManagerFactory` and trusted server configuration.

**Note:** `startsWith("/api/internal/")` in the example includes a slash boundary so it does not match `/api/internal-admin`. Even so, real systems must ensure URL normalization, encoding, context path, and matcher semantics align with the security framework. Otherwise, the resolver and authorization matchers could interpret the same URL differently.

### 14.3. Wiring the Resolver into WebFlux Resource Server

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.ReactiveAuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.reactive
    .EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.web.server.ServerWebExchange;

@Configuration
@EnableWebFluxSecurity
public class ReactiveOrdersApiSecurity {

    @Bean
    SecurityWebFilterChain apiChain(
            ServerHttpSecurity http,
            ReactiveAuthenticationManagerResolver<ServerWebExchange>
                managedReactiveResolver) {

        return http
            .securityMatcher(
                new PathPatternParserServerWebExchangeMatcher("/api/**"))
            .csrf(ServerHttpSecurity.CsrfSpec::disable)
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/partners/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .pathMatchers(HttpMethod.GET, "/api/internal/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(
                    managedReactiveResolver))
            .build();
    }
}
```

`PathPatternParserServerWebExchangeMatcher` resides in `org.springframework.security.web.server.util.matcher` in common WebFlux Security 6.x versions; add the corresponding import. Check the DSL/matcher API if using a different version. The example only shows wiring and read endpoints; write operations require separate scope/tenant policies.

### 14.4. Reactor Context Does Not Change the Trust Boundary

After authentication succeeds, Spring Security WebFlux propagates Authentication via `ReactiveSecurityContextHolder`/Reactor Context. The manager must be selected and the token verified **before** handing a principal to the service.

Never use `SecurityContextHolder.MODE_GLOBAL` to "share users" across reactive requests. For policies requiring I/O, compose `Mono`/`Flux` operators and never call `block()` on the event loop.

## 15. Multiple AuthenticationManagers Sharing the Same Bearer Type

A common scenario is that **both managers handle `BearerTokenAuthenticationToken`**:

```text
JwtAuthenticationProvider.supports(BearerTokenAuthenticationToken)
OpaqueTokenAuthenticationProvider.supports(BearerTokenAuthenticationToken)
```

That does not safely define token type. A string containing two dots does not prove it is a JWT access token from the right issuer; an opaque token can take any format, including looking like a JWT.

### 15.1. Do Not Rely Only on Token Shape

Anti-pattern:

```java
if (token.split("\\.").length == 3) {
    return jwtManager;
}
return opaqueManager;
```

An attacker can craft a three-part string to force the JWT branch, or a valid opaque token with three parts could be sent to the wrong branch. If selecting by token profile is necessary, the selection is only a **routing hint** and the selected manager must verify issuer/audience/token type; never accept a token on another branch simply because this branch's parser errored.

### 15.2. Unverified `typ`/`alg` Is Only Metadata

A JWT header can contain `typ=at+jwt`, `alg=RS256`, `kid=key-a`. These fields are in a caller-supplied token; they should only be used according to the verifier's validation policy. Never trust `alg` to enable weak algorithms, and never load `jku` from the header as a new JWKS URI.

### 15.3. What If the Same Endpoint Must Accept Both JWT and Opaque?

You must design a clearer contract:

- Which client/token issuer receives which profile?
- Is there a trusted namespace/prefix for routing?
- If the wrong branch is selected, what happens?
- Do the JWT decoder and introspection endpoint share the same resource audience?
- Could the same credential ever be accepted by both branches?
- A token profile mismatch must be an authentication failure, not a policy bypass.
- Do negative tests prove there is no downgrade and no cross-issuer confusion?

You can use a controlled **token-format-aware resolver** if genuinely required, but **never default to falling back on `AuthenticationException`**. When safer, separate endpoints/hosts for the two mechanisms to eliminate ambiguity.

## 16. Selecting AuthenticationManager vs. Selecting AuthorizationManager

Both interfaces contain "Manager", yet their responsibilities differ:

| Component | Question | General input/output |
|---|---|---|
| `AuthenticationManager` | Does the credential prove an identity? | Authentication request → authenticated Authentication or error |
| `AuthenticationManagerResolver` | Which manager should check this request? | Request context → manager |
| `AuthorizationManager` | Is the authenticated principal allowed to access the resource? | Authentication + secure object → allow/deny |
| `OpaqueTokenIntrospector` | How does the AS confirm this token? | Token → verified principal/metadata |
| `JwtDecoder` | Does this JWT have a valid signature/claims? | Compact JWT → verified Jwt |

Suppose an API does:

```text
1. /api/internal/orders/123 -> resolver chooses opaque manager
2. Opaque introspection -> active=true, scope=orders.read
3. Authentication -> SCOPE_orders.read
4. Authorization -> HTTP GET requires SCOPE_orders.read
5. Domain -> does order 123 belong to the actor/tenant?
```

Steps 1–3 **have not granted object access yet**. Step 4 only checks operation type. Step 5 handles permissions on the specific resource.

### 16.1. Use `hasAuthority` with the Right Prefix

OAuth scope `orders.read` is usually mapped to `SCOPE_orders.read`.

```java
.hasAuthority("SCOPE_orders.read")
```

differs from:

```java
.hasRole("orders.read") // checks ROLE_orders.read by default
```

If a JWT manager and an opaque manager generate authorities with different prefixes, HTTP rules can allow/deny inconsistently. Establish a clear contract for `GrantedAuthority` generation from each source and test the result—never relax policy to `authenticated()` just to avoid 403s.

### 16.2. Same Authority Name Does Not Mean Same Trust Level

An internal service token and a partner user token might both carry `SCOPE_orders.read`. Never assume both tokens can view the same data. You may need:

- HTTP route isolation.
- Audience/resource binding.
- Principal type: user vs. client credentials.
- Verified issuer/client ID.
- Tenant/owner/membership.
- Data sensitivity and business rules.

Manager selection narrows **the authentication source**; domain authorization narrows **what that authentication result is allowed to do**.

## 17. Ensuring Consistent Route Matching

A subtle risk is **the resolver and security matcher disagreeing on a URL**.

For example:

```text
securityMatcher:
  /api/partner/**

resolver:
  startsWith("/api/partners")
```

A plural/singular mismatch can let a request enter the chain without a matching manager, or let a manager process an endpoint unexpected by authorization rules. Similarly, context paths, servlet paths, path encoding, trailing slashes, and proxy rewrites can introduce discrepancies.

### 17.1. Never Use `contains` for Route Security

```java
// DO NOT DO THIS:
if (request.getRequestURI().contains("internal")) {
    return internalOpaqueManager;
}
```

A URL like `/api/partners/internal-preview` would misroute. A route matcher must:

- Respect path segment boundaries.
- Have a precisely defined URL scope.
- Match the security filter chain matcher.
- Not trust raw forwarded paths unauthenticated by a proxy.
- Have tests for trailing slashes, encoded characters, case sensitivity, servlet mappings, and URL normalization.

### 17.2. Unmatched Routes Must Not Fall Outside Security

With multiple chains, Spring Security selects the first matching chain. If no chain matches, the request may proceed without the corresponding Spring Security filters. For public-facing apps, configure a **fallback `SecurityFilterChain`** with an explicit policy, typically deny-by-default or limited strictly to defined public resources.

One way to structure it:

```java
@Bean
@Order(99)
SecurityFilterChain fallbackSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth ->
            auth.anyRequest().denyAll())
        .build();
}
```

This snippet requires standard imports for `@Bean`, `@Order`, `SecurityFilterChain`, and `HttpSecurity`. For apps with public endpoints, declare explicit matchers needing `permitAll` in the appropriate chain rather than opening up the entire fallback.

### 17.3. What If the Resolver Is Called on a Denied Route?

Authentication filters may run before HTTP authorization. For a request carrying a Bearer token to a route covered by `anyRequest().denyAll()`, the resolver might be invoked and reject due to an unknown manager. This behavior does not grant access; the HTTP response may reflect an authentication failure instead of 403. Never try to "fix" this by picking a permissive manager just so every route returns the "right" status code.

## 18. Test Scenarios for the Resolver

Split testing into **selection unit tests**, **authentication provider tests**, and **HTTP integration tests**. Each layer proves a different boundary.

### 18.1. Unit Testing Request → Manager

First prove the resolver does not misselect:

| Request path | Expected manager |
|---|---|
| `/api/partners/orders/123` | partner JWT |
| `/api/partners/orders` | partner JWT |
| `/api/internal/orders/123` | internal opaque |
| `/api/internal/orders` | internal opaque |
| `/api/partners-admin/orders` | Must not match partner |
| `/api/internal-preview/orders` | Must not match internal |
| `/api/unmanaged/orders` | Reject |

Example unit test invoking the resolver bean directly with a mock request:

```java
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.authentication.BadCredentialsException;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.mock;

class ManagedBearerResolverTest {

    private final AuthenticationManager partner =
        mock(AuthenticationManager.class);
    private final AuthenticationManager internal =
        mock(AuthenticationManager.class);

    private final AuthenticationManagerResolver<HttpServletRequest>
        resolver = new ManagedBearerResolverConfiguration()
            .managedBearerResolver(partner, internal);

    @Test
    void partnerPathSelectsPartnerManager() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET",
                "/api/partners/orders/123");
        request.setServletPath("/api/partners/orders/123");

        assertThat(resolver.resolve(request)).isSameAs(partner);
    }

    @Test
    void internalPathSelectsOpaqueManager() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET",
                "/api/internal/orders/123");
        request.setServletPath("/api/internal/orders/123");

        assertThat(resolver.resolve(request)).isSameAs(internal);
    }

    @Test
    void unknownPathCannotChoosePermissiveFallback() {
        MockHttpServletRequest request =
            new MockHttpServletRequest("GET",
                "/api/unknown/orders");
        request.setServletPath("/api/unknown/orders");

        assertThatThrownBy(() -> resolver.resolve(request))
            .isInstanceOf(BadCredentialsException.class);
    }
}
```

In this illustrative code, `ManagedBearerResolverConfiguration` must match the configuration class in section 8 (`ManagedBearerResolverConfiguration` or renamed per project); the snippet focuses strictly on selection logic. `HttpServletRequest` must be imported from Jakarta Servlet. Matcher tests should confirm the running version's behavior.

**Limitation:** this test sends no Bearer token and **does not check JWT signatures or HTTP introspection**. It only proves the right manager is selected by route.

### 18.2. Testing the JWT Manager

For JWTs, tests should cover:

- Token signed with the partner issuer's test key and `aud=orders-partner-api`.
- Token with valid signature but wrong issuer.
- Token with right issuer but `aud=payments-api`.
- Expired token or future `nbf`.
- Token using an algorithm rejected by policy.
- Token with `scope=orders.read` mapped to `SCOPE_orders.read`.
- Parsed token with invalid signature **does not** produce Authentication.

Do not use `Jwt.withTokenValue(...).build()` as proof of signature verification: it merely constructs a test Jwt object. To test the real decoder, sign a JWT with a test private key and serve the matching public key via JWKS.

### 18.3. Testing the Opaque Manager

A mock introspection endpoint should return:

```json
{"active":true,"scope":"orders.read","aud":["orders-internal-api"]}
```

and:

```json
{"active":false}
```

Tests must prove:

| Response/Upstream | Result |
|---|---|
| `active=true`, right audience, read scope | Authenticated principal with `SCOPE_orders.read` |
| `active=false` | Authentication fails |
| `active=true`, wrong audience | Policy rejects |
| `active=true`, missing scope | Does not auto-add `SCOPE_orders.read` |
| HTTP 401 from AS due to bad client credentials | No fallback |
| Timeout/5xx | No privileged principal created |

These are **introspection adapter** tests, separate from request-resolver unit tests.

### 18.4. MockMvc Integration Through the Bearer Filter

At the HTTP layer, do not just call `resolver.resolve(request)`—verify:

```text
GET /api/partners/orders/123
Authorization: Bearer valid-partner-jwt
  -> partner manager is called
  -> internal opaque manager is not called
  -> HTTP read-scope rule is enforced

GET /api/internal/orders/123
Authorization: Bearer active-internal-opaque-token
  -> internal opaque manager is called
  -> partner JWT manager is not called

GET /api/partners/orders/123
Authorization: Bearer invalid-partner-jwt
  -> authentication fails
  -> internal manager is NOT called next
```

You can use `MockMvc` with test managers/mock introspection servers at the proper boundary. If a test uses:

```java
.with(jwt().authorities(
    new SimpleGrantedAuthority("SCOPE_orders.read")))
```

that is a **mock Authentication**; it can bypass the Bearer filter and resolver and **does not prove manager selection**. To test routing end-to-end, send a Bearer header and assert that spy/fake managers or decoder/introspection endpoints receive the right requests.

### 18.5. WebFlux Testing with `WebTestClient`

In WebFlux, use:

```java
client.get().uri("/api/internal/orders/123")
    .headers(headers ->
        headers.setBearerAuth("opaque-test-token"))
    .exchange()
    .expectStatus().isOk();
```

This test assumes fixtures with a controller, valid token, and permitting scope/domain policy. `mockJwt()`/`mockOpaqueToken()` are suitable for testing authorization with a simulated Authentication, but do not prove the reactive resolver selected a real manager. Test the pipeline separately with real Bearer headers and injected managers.

### 18.6. Mandatory Negative Matrix

| Request and credential | Expectation |
|---|---|
| Partner route + valid partner JWT | Passes authentication; scope/domain policy continues |
| Internal route + active opaque token with right audience | Passes authentication; scope/domain policy continues |
| Partner route + internal opaque token | Partner JWT manager rejects; no fallback |
| Internal route + partner JWT | Internal opaque policy rejects; no fallback |
| Partner JWT with invalid signature | 401; no introspection call |
| Partner JWT right issuer, wrong audience | 401 |
| Opaque `active=false` | 401 |
| Opaque AS timeout | Fail closed; HTTP status per handler |
| Active token missing required scope | 403 |
| Token has scope but accesses another tenant | 403/404 per business policy |
| Unknown route `/api/new/**` | Must not auto-select a privileged default manager |
| Basic credential on Bearer-only route | Not accepted as Bearer |
| Web session cookie present without API Bearer token | API must not authenticate from old session |
| Header `X-Auth-Mode: legacy` | Does not alter manager unless part of trusted policy |
| JWT header `jku` pointing to attacker URL | Keys are not fetched from header |
| Recently offboarded manager config | Token/route rejected once policy takes effect |

## 19. Tenant Onboarding, Secret Rotation, and Manager Caching

With a few static resource groups, you can create managers at startup and keep them as Spring beans. With hundreds of tenants, dynamic registry/caching is needed—yet that is a **security configuration lifecycle**, not arbitrary caching of unverified issuers.

### 19.1. Cache Managers Only by Trusted Key

Example structure:

```text
ManagedRegistry
  alpha:
    trusted issuer
    validated JWKS metadata
    audience and scopes
    active version

  beta:
    trusted issuer
    introspection endpoint credentials
    audience and scopes
    active version

ManagerCache:
  key = (tenantKey, configVersion, mechanism)
  value = preconfigured manager
```

Never use:

```text
cacheKey = unverified JWT iss (no allowlist)
manager = dynamically discover arbitrary issuer
```

because an attacker can invent endless `iss` values, forcing the server to perform unbounded network discovery and manager creation.

### 19.2. Offboarding Must Invalidate Trust

When removing an issuer/tenant from the registry, verify:

- Does the resolver still return a cached manager for that issuer?
- Have all replicas received the updated configuration?
- Does the JWKS cache still allow tokens to be accepted by an old manager?
- Does the introspection cache retain principals for revoked tokens?
- Do any Authentication sessions still exist in a browser chain?
- Does the gateway still route requests to the old area?

A still-living cached decoder is not necessarily a vulnerability if the resolver **no longer allows selecting it**. However, if the manager remains reachable through a stale registry, offboarding has not taken effect.

### 19.3. Secret Rotation for Introspection

When the AS rotates a client secret, refresh the introspector/HTTP client accordingly. Never log `client_secret` or place it in URLs. Trying old and newly rotated secrets may be a temporary migration need, but requires a **time-bounded policy and auditing**, never an indefinite fallback to weaker credentials.

### 19.4. JWKS Rotation Is Not Changing the Issuer

An issuer can rotate its JWT signing keys; the decoder must fetch new keys from **the right issuer's** JWKS. Key rotation does not permit accepting tokens from another issuer, and identical `kid` values across two issuers do not mean the two keys share an identity.

## 20. Observability: Knowing Which Manager Was Selected Without Leaking Tokens

With multiple authentication mechanisms, metrics/logs should show **which route selected which manager**, while avoiding raw credentials:

```text
requestCorrelationId
routePolicyId = partner-api-v1
selectedMechanism = JWT
selectedManagerId = partner-jwt-manager
authenticationOutcome = success / invalid_signature / invalid_audience
authorizationOutcome = allow / deny
tenantPolicyId = tenant-alpha
issuerRegistryKey = trusted-partner-id (if needed)
durationMs
```

Never log:

```text
Authorization: Bearer eyJ...
Authorization: Basic base64-credentials
client_secret=...
opaque_token=...
unbounded raw unverified claims/headers
full introspection responses containing PII
```

In particular, never use unverified issuers or arbitrary tenant headers as metric labels: attackers can generate unbounded values causing **high cardinality** or log injection. Use **managed configuration IDs** like `partner-jwt-manager`/`internal-opaque-manager`.

### 20.1. Distinguishing Authentication Failure from Authorization Failure

A helpful trace:

```text
request:
  pathPolicy = /api/internal/orders/**
selection:
  mechanism = opaque
  managerId = internal-opaque
authentication:
  introspection = active
  audience = correct
  scopeAuthorities = [SCOPE_orders.read] (filtered when logging)
authorization:
  required = SCOPE_orders.update
  outcome = denied
http:
  status = 403
```

This differs from:

```text
selection:
  mechanism = JWT
authentication:
  signature = invalid
  outcome = failed
http:
  status = 401
```

You do not need to log the entire token or principal attributes to see where the failure occurred.

## 21. Common Pitfalls and How to Troubleshoot

| Symptom | Possible cause | What to check |
|---|---|---|
| Valid JWT on partner route returns 401 | Wrong manager, issuer, JWKS, audience, or algorithm | Trace managerId, decoder validators |
| Active opaque token returns 401 | Wrong introspection credentials/URI, audience policy mismatch | Test AS contract with fake response |
| API returns 403 even though token is active | Missing `SCOPE_` authority, wrong role prefix, owner/tenant deny | Inspect authorization rule/domain policy |
| Unknown route returns 200 | Missing fallback chain/manager or overly broad `permitAll` | Check chain matching and deny-by-default |
| Same URL sometimes uses JWT manager, sometimes opaque | Client-supplied header used to pick mode | Rely on managed route/server policy |
| Invalid Bearer still reaches controller | Broken exception handler/filter fallback | Test "no side effects on denied auth" |
| Unknown issuer token triggers outbound requests | Building decoder/discovery from non-allowlisted `iss` | Trusted registry + egress controls |
| Manager cache grows unbounded | Attacker-controlled cache key | Bounded cache keyed by trusted config |
| Beta token accesses tenant alpha | Checked token only, skipped tenant authorization | Bind verified issuer + membership/object |
| Partner JWT hits internal opaque manager | Overlapping matchers, differing path interpretation | Test route boundaries and filter order |
| Basic credentials accepted on Bearer-only API | HTTP Basic filter in same chain or fallback | Split chains/remove unneeded mechanisms |
| Browser cookie grants Bearer API access | Mixed session persistence/chains | Stateless API chain, test cookie-only requests |
| Resolver unit tests pass, real tokens fail | Tests did not run decoder/introspection/wiring | MockMvc/WebTestClient Bearer tests |
| Mock JWT test passes, invalid signature still succeeds | Used `jwt()` fixture instead of real pipeline | Signed compact JWT tests |
| Config change has no effect | Stale resolver/manager cache or replica lag | Config version/invalidation |
| AS downtime makes all requests hang | Unbounded timeouts/retries | Bounded network timeouts, fail-closed policy |

### 21.1. A Useful Diagnostic Checklist of Questions

When a request is rejected, ask in order:

1. Which **`SecurityFilterChain`** did the request enter?
2. Which filter accepted the **credential scheme**?
3. Which manager did the resolver select and **based on which policy**?
4. Which **key/AS/issuer/audience** did the manager use?
5. Was Authentication constructed from a **verified** credential?
6. What `GrantedAuthority` values resulted after mapping?
7. Which HTTP/method authorization rule denied it?
8. Which business owner/tenant/state policy denied it?

Never fix every 401/403 by adding `permitAll()`, removing audience validators, or switching to a more permissive manager.

## 22. Step-by-Step Safe Implementation Workflow

A project needing multiple authentication mechanisms can follow this sequence:

1. **Inventory the API surface** and permitted credential types per area.
2. **Choose a separation strategy:** multiple `SecurityFilterChain` beans, one Bearer manager resolver, or a combination of both.
3. **Establish managed config:** trusted issuers, JWKS, introspection endpoints, audiences, algorithms, tenant mappings, secrets.
4. **Build independent managers:** JWT must verify signature/issuer/audience/time; opaque must introspect and check metadata/resource per contract.
5. **Write a pure selection resolver:** route/request context → trusted manager; unknown → reject.
6. **Wire the resolver into the right filter chain:** `oauth2ResourceServer().authenticationManagerResolver(...)` in Servlet/WebFlux as appropriate.
7. **Define HTTP authorization rules:** `hasAuthority("SCOPE_...")`, deny-by-default, method-specific permissions.
8. **Protect the domain:** actor issuer + subject + tenant + object permissions; never trust request parameters as identity.
9. **Forbid downgrades/fallbacks:** a token rejected by the selected mechanism must never try another mechanism simply on exception.
10. **Control the lifecycle:** secret/key rotation, tenant onboarding/offboarding, config versioning, and cache invalidation.
11. **Test selection separately:** route boundaries, malformed paths, unknown routes, no overly permissive manager.
12. **Test token validation separately:** JWT signed keys, opaque RFC 7662, invalid audience/issuer/expiry, AS timeouts.
13. **Test real HTTP:** Bearer headers flowing through configured filters/managers; 401/403/domain denials with zero side effects.
14. **Monitor:** routePolicyId, selectedManagerId, outcomes, and latency; never log secrets.

### 22.1. Decision Flowchart

```mermaid
flowchart TD
    A["Receive request"] --> B{"Route in managed policy?"}
    B -->|"No"| X["Deny / secure fallback chain"]
    B -->|"Yes"| C{"Credential scheme allowed by route?"}
    C -->|"No"| Y["Authentication required / reject"]
    C -->|"Yes"| D["Resolver gets manager from trusted registry"]
    D --> E{"Manager exists and config active?"}
    E -->|"No"| X
    E -->|"Yes"| F{"JWT / opaque / declared mechanism?"}
    F -->|"JWT"| G["Verify signature + iss + aud + exp + profile"]
    F -->|"Opaque"| H["Trusted introspection + active + aud + issuer contract"]
    F -->|"Other mechanism"| I["Dedicated provider/filter with trust checks"]
    G --> J{"Authentication succeeded?"}
    H --> J
    I --> J
    J -->|"No"| Z["Fail closed; no fallback to weaker manager"]
    J -->|"Yes"| K["Authentication / authorities"]
    K --> L{"Scope / method authorization?"}
    L -->|"No"| M["403 / deny"]
    L -->|"Yes"| N{"Tenant + object policy?"}
    N -->|"No"| M
    N -->|"Yes"| O["Allow execution"]
```

## 23. Summary

```text
MANAGED MULTI-MECHANISM AUTHENTICATION

HTTP request
   |
   v
SecurityFilterChain / credential filter
   |
   v
AuthenticationManagerResolver
   |  route / trusted context
   |  known key -> managed manager
   |  unknown   -> reject
   |
   +---- partner JWT manager
   |        JwtDecoder:
   |          signature + issuer + audience + time
   |
   +---- internal opaque manager
   |        OpaqueTokenIntrospector:
   |          active + audience + token contract
   |
   +---- other mechanisms
            only via matching trusted filters/chains
   |
   v
Authenticated Authentication
   |
   v
SCOPE_ authorities / HTTP-method rules
   |
   v
Tenant, owner, object state policy
   |
   v
Business operation

NEVER:
  untrusted URL -> dynamic JWT verifier
  invalid JWT -> try loose opaque fallback
  AS timeout -> allow default scope
  unknown path -> permissive manager
  browser session -> Bearer API auth without explicit design
```

**`AuthenticationManagerResolver` is a router to an authentication mechanism, not proof that a token is valid.** When an API has multiple mechanisms, select the manager from **managed routes/contexts and configuration registries**. Each manager must prove the credential matches the right issuer, audience, and token profile. Rejected tokens must never automatically route to a weaker authentication branch.

In **Servlet**, the appropriate extension point is `AuthenticationManagerResolver<HttpServletRequest>` wired into `oauth2ResourceServer().authenticationManagerResolver(...)`. In **WebFlux**, use `ReactiveAuthenticationManagerResolver<ServerWebExchange>`, returning `Mono<ReactiveAuthenticationManager>` and keeping I/O non-blocking. For mechanisms completely distinct from Bearer such as form login, Basic, mTLS, or API keys, design **the right filters/chains for each mechanism** rather than expecting a Bearer resolver to handle everything.

Finally, keep the three layers separate: **manager selection**, **token verification**, and **endpoint/tenant/object authorization**. Only then can a system with multiple issuers, token types, and tenants avoid confusing "which path a request chooses" with "what privileges a credential actually holds".

## References

- [Spring Security Reference — Authentication Architecture (Servlet)](https://docs.spring.io/spring-security/reference/servlet/authentication/architecture.html): `AuthenticationManager`, `ProviderManager`, `AuthenticationProvider`.
- [Spring Security Reference — OAuth 2.0 Resource Server Multitenancy (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): `AuthenticationManagerResolver` and `JwtIssuerAuthenticationManagerResolver`.
- [Spring Security Reference — Multiple SecurityFilterChain](https://docs.spring.io/spring-security/reference/servlet/configuration/java.html): `securityMatcher`, filter-chain matching, and ordering.
- [Spring Security Reference — JWT Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, issuer, audience, JWT authorities.
- [Spring Security Reference — Opaque Token Resource Server (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and `OpaqueTokenIntrospector`.
- [Spring Security Reference — Reactive Resource Server Multitenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html): `JwtIssuerReactiveAuthenticationManagerResolver` and WebFlux multi-tenancy.
- [Spring Security Reference — Reactive WebFlux Security](https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html): `ServerHttpSecurity`, `SecurityWebFilterChain`.
- [Spring Security Reference — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` and WebFlux JWT.
- [Spring Security Reference — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html): `ReactiveOpaqueTokenIntrospector`.
- [Spring Security API — AuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManagerResolver.html): interface for selecting `AuthenticationManager`.
- [Spring Security API — ReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerResolver.html): reactive resolver interface.
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html): selecting JWT issuers from a trusted list.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): access tokens and scopes.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer credentials, `invalid_token`, `insufficient_scope`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): `active` and opaque token metadata.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer/discovery metadata.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm confusion, key confusion, and cross-JWT validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token issuer/audience/type profile.
- [OWASP API Security Top 10 (2023) — Broken Object Level Authorization](https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/): object/tenant-level permissions beyond OAuth scopes.
