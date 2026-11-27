# JwtIssuerAuthenticationManagerResolver and trusted issuer sets

In a **Spring Security OAuth 2.0/OIDC Resource Server** serving **multiple tenants**, an API may need to accept JWT access tokens issued by **multiple Authorization Servers or multiple issuers**. For example, tenant A uses one realm of an identity provider while tenant B uses another; each issuer has its own metadata, JWK Set, signing keys, and policies.

For **Servlet/Spring MVC** Spring Security applications, `JwtIssuerAuthenticationManagerResolver` selects an `AuthenticationManager` based on the JWT **`iss`** claim so the token is verified against the right issuer. However, a mandatory condition is that **the selected issuer must belong to the set of issuers trusted by the Resource Server**. Simply reading `iss` from the token payload does not verify the issuer's identity.

> **Foundational rule:** read an unverified `iss` claim only to **route to an approved verification mechanism**; never treat it as proof of token validity, never connect to an arbitrary issuer automatically, and never grant permissions from other claims before signature verification and validators succeed.

This lesson explains the trust boundary, configuring `fromTrustedIssuers(...)`, handling dynamic issuer sets, validating issuer and audience, distinguishing tenants from issuers, SSRF/JWKS confusion risks, lazy loading, testing, and operations. Code samples use **Java 17+, Spring Boot, and Spring Security Servlet**; pay attention to API milestones when running Spring Security 6.x or 7.x.

## 1. What is a multi-tenant Resource Server?

A Resource Server may need to handle:

~~~text
Tenant A
   |
   +-- Authorization Server A / realm A
   |       issuer = https://idp-a.example.com/realms/shop
   |       JWKS   = https://idp-a.example.com/realms/shop/certs
   |
   v
                    +-------------------------+
                    | Orders Resource Server  |
                    | /api/orders/**          |
                    +-------------------------+
   ^
   |
Tenant B
   |
   +-- Authorization Server B / realm B
           issuer = https://idp-b.example.com/realms/shop
           JWKS   = https://idp-b.example.com/realms/shop/certs
~~~

Two issuers may both use RS256, share the same scope name `orders.read`, and even have overlapping `sub` or `kid` values. The Resource Server must still:

1. Select the right **key source** to verify each token.
2. Check that the JWT matches the corresponding **expected issuer**.
3. Check that the token **is intended for this API** via `aud` or another resource binding.
4. Check `exp`, `nbf`, and the applicable token profile.
5. Map scopes/roles according to each issuer's contract.
6. Only permit access to the tenant and records the subject is actually authorized for.

Spring Security refers to this as the **resolve tenant** and **propagate tenant** problem. `JwtIssuerAuthenticationManagerResolver` primarily solves **selecting the authentication strategy by issuer**; it **does not automatically enforce ownership, tenant membership, or data isolation** in the business layer.

### 1.1. An issuer is not necessarily a tenant

The following three systems have different models:

| Model | Issuer | Tenant | Consequence |
|---|---|---|---|
| One issuer per tenant | A → issuer A; B → issuer B | One-to-one | Issuer can be used to choose the authentication strategy |
| One issuer for many tenants | Both A and B use issuer X | Multiple tenants in tokens/DB | Resolving by `iss` **does not distinguish** tenant A from B |
| One tenant trusts multiple issuers | Tenant A uses issuers X and Y | One tenant, multiple identity providers | Must verify issuer first, then map identity/membership to tenant |

**Never assume `tenantId = issuer`.** In some deployments each tenant does have its own realm/issuer, but that is an **architectural convention**, not an inherent property of OAuth 2.0/OIDC.

### 1.2. What a JWT can carry

Token from issuer A:

~~~json
{
  "iss": "https://idp-a.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-a",
  "exp": 2000000300
}
~~~

Token from issuer B:

~~~json
{
  "iss": "https://idp-b.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "tenant_id": "tenant-b",
  "exp": 2000000300
}
~~~

Even with the same `sub=user-42`, the two principals **are not automatically the same person**. When identifying users in a multi-issuer database, you can use the key `(issuer, subject)` or a canonical internal user ID mapped from that pair by a trusted service.

## 2. Why is a single shared `JwtDecoder` often not enough?

Single-issuer configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp-a.example.com/realms/shop
~~~

typically creates a decoder that verifies tokens for issuer A. This is reasonable if the API only trusts A, but when tenant B uses issuer B with different signing keys, a decoder pinned to issuer A cannot meet the requirement.

A wrong approach is taking a token from any issuer and:

~~~text
1. Only decoding the payload.
2. Reading the new issuer from `iss`.
3. Trusting the payload and granting access.
```

The right approach requires **a set of permitted issuers** and **a corresponding authentication manager/decoder** for each issuer:

~~~text
Unverified JWT
        |
        v
Read `iss` ONLY for routing
        |
        v
Is `iss` in trusted issuers set?
   |                         |
   No                       Yes
   |                         |
   v                         v
 Reject              Manager for that issuer
                             |
                       Fetch keys from approved
                       JWK source
                             |
                       Verify signature
                       Validate iss/aud/time
                             |
                       Authentication succeeds
                             |
                       Authorization/resource policy
~~~

This handles **manager selection**, without turning `iss` into trusted proof from step one.

## 3. Trust boundary: initial `iss` is unverified data

A JWS JWT has the structure:

~~~text
base64url(header).base64url(payload).base64url(signature)
~~~

The header and payload bytes are supplied by the caller; before signature verification, the caller can alter them.

Example forged payload:

~~~json
{
  "iss": "https://attacker.example/oidc",
  "sub": "admin",
  "aud": ["orders-api"],
  "scope": "orders.read orders.write"
}
~~~

An attacker can stand up their own Authorization Server, publish a JWKS with a public key they control, and sign tokens with the matching private key.

If the Resource Server does:

~~~java
// DANGEROUS: creates a decoder from any caller-declared issuer.
AuthenticationManager resolve(String issuer) {
    JwtDecoder decoder = JwtDecoders.fromIssuerLocation(issuer);
    return new JwtAuthenticationProvider(decoder)::authenticate;
}
~~~

without **checking an allowlist**, a forged token will still validate **against the attacker's own issuer**. That does not prove the API trusts that issuer.

Beyond **authentication bypass/cross-issuer trust**, this design can also introduce **SSRF** if the server is tricked into fetching unintended metadata/JWKS URLs or internal addresses.

### 3.1. What may an unverified `iss` value be used for?

Allowed—**routing** to a manager registered from a trusted source:

~~~text
unverified iss -> exact allowlist lookup -> verified manager
```

Not allowed:

~~~text
unverified iss -> arbitrary HTTP metadata fetch -> accept self-signed attacker token
unverified iss -> trusted=true
unverified iss -> ROLE_ADMIN
unverified iss -> authorization to tenant database
```

Only after the decoder actually verifies the signature **and** validates the issuer does `Jwt#getIssuer()` become an attribute of an **authenticated token** suitable for identity mapping.

### 3.2. The allowed issuer list belongs in configuration

An allowlist should originate from:

- Server configuration managed by the operations/security team.
- An approved tenant onboarding flow persisted to a trusted registry.
- An internal control plane with authentication, authorization, and auditing.
- A trusted configuration service with integrity guarantees and change control.

Never obtain the list from:

- An unverified JWT `iss`.
- Query parameters like `?issuer=...`.
- Client-supplied `X-Issuer` or `X-Tenant` headers.
- Arbitrary email domains, usernames, or hosts.
- Discovery endpoints chosen from `jku`/`x5u` in a JWT header.

## 4. What does `JwtIssuerAuthenticationManagerResolver` do?

Spring Security Servlet provides the class:

~~~java
org.springframework.security.oauth2.server.resource.authentication
    .JwtIssuerAuthenticationManagerResolver
~~~

It implements:

~~~java
AuthenticationManagerResolver<HttpServletRequest>
~~~

Conceptually, the resolver:

1. Extracts the bearer token from `HttpServletRequest` when authentication runs.
2. Parses claims to read `iss` **for manager selection**.
3. Checks/looks up an `AuthenticationManager` corresponding to that issuer.
4. Delegates the bearer token to the chosen manager.
5. The manager uses `JwtAuthenticationProvider`/`JwtDecoder` to **actually verify the token**.
6. Only if verification succeeds does it produce an `Authentication` for authorization.

**Technical note:** `resolve(HttpServletRequest)` returns an `AuthenticationManager` that resolves the issuer during the authentication stage; not all parsing/selection necessarily happens immediately inside the `resolve` call across every implementation version.

### 4.1. Position in the Servlet filter chain

~~~text
HTTP Authorization: Bearer token
               |
               v
BearerTokenAuthenticationFilter
               |
               v
JwtIssuerAuthenticationManagerResolver
               |
               v
     Look up manager by `iss`
               |
         +-----+-----+
         |           |
      Issuer A    Issuer B
         |           |
         v           v
     JwtAuthenticationProvider A/B
         |
         v
     JwtDecoder for issuer/key source
         |
         +-- Verify JWS signature
         +-- Validate `iss`, `aud`, `exp`, `nbf`
         |
         v
     JwtAuthenticationToken
         |
         v
     AuthorizationFilter / Controller
~~~

In this model, the resolver performs **authentication routing**, not `AuthorizationManager` checks like `hasAuthority` or ACL enforcement.

### 4.2. Why does this class belong to Servlet?

It implements `AuthenticationManagerResolver<HttpServletRequest>` and pairs with `HttpSecurity`/`SecurityFilterChain`. In WebFlux, the counterpart is **`JwtIssuerReactiveAuthenticationManagerResolver`** using Reactive APIs.

Do not arbitrarily rename Java classes while keeping `HttpServletRequest`/`JwtDecoder` in WebFlux. This lesson focuses on **Servlet Resource Server** as indicated by the `JwtIssuerAuthenticationManagerResolver` API itself.

## 5. Simplest configuration: `fromTrustedIssuers(...)`

With two known trusted issuers:

~~~java
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://idp-a.example.com/realms/shop",
        "https://idp-b.example.com/realms/shop"
    );
~~~

This follows the **Spring Security multi-tenancy** documentation: explicitly supplying the allowed issuers.

### 5.1. Full `SecurityFilterChain`

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class MultiIssuerSecurityConfig {

    @Bean
    JwtIssuerAuthenticationManagerResolver trustedIssuerResolver() {
        return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
            "https://idp-a.example.com/realms/shop",
            "https://idp-b.example.com/realms/shop"
        );
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtIssuerAuthenticationManagerResolver resolver)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()

                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")

                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")

                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(resolver))
            .build();
    }
}
~~~

This configuration uses **`authenticationManagerResolver`** instead of a single fixed JWT decoder in the DSL. Spring Security creates/maintains per-issuer managers according to `fromTrustedIssuers` in the active version.

**Important:** this example only enforces default trusted issuer checks. If the API requires **`aud` = `orders-api`**, token type validation, or issuer-specific claim policies, add validators using an appropriate resolver/manager strategy (see the registry section). Never assume an issuer allowlist automatically guarantees `aud`.

### 5.2. Gradle dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Rely on the Spring Boot BOM/Dependency Management rather than hardcoding mismatched Spring Security artifact versions.

### 5.3. Spring Security versions and APIs

| API | Notes |
|---|---|
| `JwtIssuerAuthenticationManagerResolver` | Available since Spring Security 5.3 |
| `fromTrustedIssuers(String...)` | Available since **6.2** |
| `fromTrustedIssuers(Collection<String>)` | Available since **6.2** |
| `fromTrustedIssuers(Predicate<String>)` | Available since **6.2** |
| Constructors taking `String...` or `Collection<String>` | **Deprecated since 6.2**, marked for removal |
| Constructor taking `AuthenticationManagerResolver<String>` | Used for custom manager registries |

With Spring Security 6.2+/7.x, prefer **`fromTrustedIssuers(...)`** over the deprecated constructors. For projects older than 6.2, check the Javadoc/API of your exact version before choosing syntax.

Do not copy old tutorials using `new JwtIssuerAuthenticationManagerResolver("issuer-a", "issuer-b")` and dismiss deprecation warnings as irrelevant to upgrades.

## 6. How does `fromTrustedIssuers` protect you?

With:

~~~java
.fromTrustedIssuers("https://idp-a.example.com/realms/shop")
~~~

a token claiming:

~~~json
{"iss":"https://attacker.example/oidc"}
~~~

will not trigger an automatic discovery fetch against the attacker: the issuer is not in the registered set.

A token claiming **issuer A** but signed with an **attacker's key** must also fail verification, because manager A only trusts keys from the source configured for issuer A.

~~~text
Case 1:
iss = attacker.example
-> does not match allowlist -> rejected before creating a decoder for unknown issuer

Case 2:
iss = idp-a.example.com
signature = attacker key
-> selects manager A
-> signature fails verification against A's trusted JWK
-> rejected

Case 3:
iss = idp-a.example.com
signature = real key of A
aud = another-api
-> valid signature, yet must still be rejected if API requires aud=orders-api

Case 4:
iss = idp-a.example.com
signature = real key A
aud = orders-api
exp in the past
-> rejected because token is expired
```

**The allowlist only defines who may issue tokens the API will consider; signatures and claims must still be validated.**

### 6.1. Exact string matching for issuers

An issuer is a URL identifier (exact `iss` value), not just a hostname. These strings are **not automatically equivalent**:

~~~text
https://idp-a.example.com/realms/shop
https://idp-a.example.com/realms/shop/
https://IDP-A.example.com/realms/shop
http://idp-a.example.com/realms/shop
https://idp-a.example.com/realms/SHOP
~~~

Do not arbitrarily lowercase the entire string, strip paths, trim trailing slashes, or downgrade HTTPS to HTTP for "issuer normalization." If an AS uses a specific canonical issuer, configure the **exact published issuer value**.

Allowing issuers purely via a parent domain suffix like `endsWith(".example.com")` can expand trust to unintended services, subdomains, or realms.

### 6.2. A dynamic `Predicate` must not become `issuer -> true`

Some projects require a predicate:

~~~java
Set<String> approved = Set.of(
    "https://idp-a.example.com/realms/shop",
    "https://idp-b.example.com/realms/shop"
);

JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        approved::contains
    );
~~~

This pattern only accepts issuers inside the approved set.

Conversely:

~~~java
// DANGEROUS: allows any self-declared issuer.
JwtIssuerAuthenticationManagerResolver resolver =
    JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        issuer -> true
    );
~~~

nullifies the protection of the allowlist. Never assume `Predicate` implies the framework validates the issuer's domain ownership.

## 7. Lazy loading: operational benefits and risks

With `fromTrustedIssuers`, Spring Security **creates the per-issuer manager/provider the first time that issuer is needed**; the docs note that issuer endpoints are loaded lazily.

Benefits:

- The application can start even if some AS instances are temporarily unreachable.
- There is no need to create decoders and run discovery for every issuer at startup.
- Infrequently used tenants do not require network activity during boot.

However, understand the trade-off:

~~~text
Application startup
    |
    +-- resolver knows the trusted list
    +-- has not necessarily called all JWKS/metadata endpoints
    |
    v
First token for issuer B
    |
    +-- creates manager/decoder for B
    +-- may require issuer discovery/JWKS retrieval
    +-- if B is temporarily unavailable -> authentication failure/dependency error
```

**AS-independent startup does not mean AS-independent first request.**

### 7.1. Cold start and first-request latency

Measure:

- The first time an instance sees a token for a new issuer.
- DNS/TLS/discovery/JWKS latency.
- Concurrent requests for the same issuer while cold.
- Behavior when the AS is unreachable.
- Key caching after the manager is constructed.
- Key rotation and unknown `kid` handling.

A deployment with 200 replicas and many tenants can create a traffic spike against the AS when instances cold-start together. Consider bounded warm-up, a trusted JWKS gateway, connection timeouts, bounded retries, and load observability.

### 7.2. Fail closed when the AS is unavailable

If no trusted cached public key is available and metadata/JWKS cannot be fetched, tokens requiring that key **must not authenticate**.

Never write a fallback like:

~~~java
// WRONG: bypasses verification when issuer is unavailable.
return authentication -> new JwtAuthenticationToken(unverifiedJwt);
~~~

An AS outage can produce an authentication failure or infrastructure error depending on your handler, but it must never create an authenticated principal from an unverified token.

## 8. Trusted issuers are not enough: audience must be checked

Suppose AS A issues two kinds of access tokens:

~~~text
Token 1: aud = orders-api
Token 2: aud = billing-api
```

Both are signed by issuer A. If the Resource Server only validates signature + issuer without **requiring the right `aud`**, a token meant for Billing API can be misused on Orders API.

### 8.1. Separating issuer validation from resource audience

| Check | Question |
|---|---|
| Trusted issuer allowlist | Is this AS allowed to issue tokens the API considers? |
| JWS signature | Was the token genuinely signed by the corresponding AS key? |
| `iss` | Does the verified token match the selected issuer? |
| `aud` | Was this token issued for **this API**? |
| `exp`/`nbf` | Is the token within its valid time window? |
| Token profile/`typ` | Is it the expected JWT access token type accepted by the API? |
| Scope/authority | Does the caller have permission for the operation? |
| Tenant/resource policy | Does the caller have access to the specific entity/tenant? |

**Never rely solely on `sub` and scope** when accepting tokens from multiple issuers. You must enforce the right issuer, audience, and identity namespace.

### 8.2. Per-issuer customization to enforce audience

If each issuer needs its own audience check, register each `AuthenticationManager` with an explicit decoder and validators. This is shown in the registry section below.

## 9. Dynamic issuer sets: changing tenants without restarting

A SaaS system may onboard new tenants while running:

~~~text
T0: approved issuers = {A, B}
T1: Admin approves tenant C + issuer C
T2: approved issuers = {A, B, C}
T3: Tenant B offboards
T4: approved issuers = {A, C}
~~~

With a hardcoded list, changes require a deploy/restart. Spring Security supports the constructor:

~~~java
new JwtIssuerAuthenticationManagerResolver(
    AuthenticationManagerResolver<String> issuerManagerResolver
)
~~~

A repository can store an **issuer → AuthenticationManager** map. In Spring's documentation, `authenticationManagers::get` is used as the strategy; an issuer absent from the map returns no manager.

**Security point:** this registry must be updated **only via a trusted onboarding/control plane**, never automatically from an unverified JWT or a public `POST /tenants` endpoint.

### 9.1. Registry structure

~~~text
Trusted Issuer Registry
    |
    +-- issuer A -> AuthenticationManager A
    |                 +-- JwtDecoder A
    |                 +-- public JWKS A
    |                 +-- validators iss A, aud orders-api
    |
    +-- issuer B -> AuthenticationManager B
    |                 +-- JwtDecoder B
    |                 +-- public JWKS B
    |                 +-- validators iss B, aud orders-api
    |
    +-- issuer C -> AuthenticationManager C
                      +-- JWT decoder C ...
```

Never key the map by `kid` alone, because two issuers can share the same `kid`. **Managers and key sources must be bound to the issuer identity.**

## 10. Full example: server-managed manager registry with allowlist

This example uses an **explicit JWK Set URI** per issuer, avoiding metadata discovery from token-claimed URIs. Each entry stores the canonical issuer, approved JWKS URI, and target API audience.

Entries added to the registry **must come only from trusted configuration sources**. A public controller must never be allowed to call `registerApprovedIssuer`.

### 10.1. Configuration model

~~~java
package com.example.orders.security;

// Domain config managed by a trusted server/control plane.
public record TrustedIssuerSpec(
    String issuer,
    String jwkSetUri,
    String audience
) {}
~~~

`TrustedIssuerSpec` is an illustrative application-defined class, not a Spring Security API.

### 10.2. Registry and per-issuer AuthenticationManager

~~~java
package com.example.orders.security;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.server.resource.authentication.JwtAuthenticationProvider;

public final class TrustedIssuerManagerRegistry {

    private final ConcurrentMap<String, AuthenticationManager> managers =
        new ConcurrentHashMap<>();

    // ONLY call from an approved bootstrap/admin control plane.
    public void registerApprovedIssuer(TrustedIssuerSpec spec) {
        // Validate canonical URLs, HTTPS, uniqueness, ownership, and
        // endpoint egress allowlist during onboarding before calling.
        // Never pass a spec received directly from an untrusted HTTP request.

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(spec.jwkSetUri())
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains(spec.audience())
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
                JwtValidators.createDefaultWithIssuer(spec.issuer()),
                audienceValidator
            )
        );

        JwtAuthenticationProvider provider =
            new JwtAuthenticationProvider(decoder);

        AuthenticationManager manager =
            new ProviderManager(provider);

        managers.put(spec.issuer(), manager);
    }

    public AuthenticationManager resolve(String issuer) {
        // Unknown issuer => null; JwtIssuerAuthenticationManagerResolver
        // rejects it instead of creating an arbitrary manager.
        return managers.get(issuer);
    }

    public void deactivateIssuer(String issuer) {
        // Only an authorized control plane may call this.
        managers.remove(issuer);
    }
}
~~~

**Role of each piece:**

- `ConcurrentHashMap` lets concurrent requests read managers safely; replacing a map entry is an atomic publication step.
- Each decoder has a **registered JWKS URI** and a JWS algorithm allowlist.
- `JwtValidators.createDefaultWithIssuer(...)` enforces issuer matching and appropriate default validators including token timestamps.
- The audience validator requires `aud` to contain `orders-api` (or the per-issuer value).
- Unknown issuers have no manager and **never instantiate a decoder**.
- `deactivateIssuer` removes the map entry so new lookups cannot retrieve the old manager.

**Scope of example:** `registerApprovedIssuer` does not implement the entire secure onboarding pipeline on its own. Production requires URL/HTTPS validation, issuer ownership checks, egress allowlists, auditing, strict admin authorization, and concurrency/lifecycle management for retired managers. Never construct `TrustedIssuerSpec` from a public request and invoke this method.

### 10.3. Wiring the registry into SecurityFilterChain

~~~java
package com.example.orders.security;

import jakarta.servlet.http.HttpServletRequest;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class RegistrySecurityConfig {

    @Bean
    TrustedIssuerManagerRegistry trustedIssuerRegistry() {
        TrustedIssuerManagerRegistry registry =
            new TrustedIssuerManagerRegistry();

        // These values illustrate an approved configuration.
        registry.registerApprovedIssuer(new TrustedIssuerSpec(
            "https://idp-a.example.com/realms/shop",
            "https://idp-a.example.com/realms/shop/certs",
            "orders-api"
        ));

        registry.registerApprovedIssuer(new TrustedIssuerSpec(
            "https://idp-b.example.com/realms/shop",
            "https://idp-b.example.com/realms/shop/certs",
            "orders-api"
        ));

        return registry;
    }

    @Bean
    AuthenticationManagerResolver<HttpServletRequest> issuerResolver(
            TrustedIssuerManagerRegistry registry) {

        return new JwtIssuerAuthenticationManagerResolver(
            registry::resolve
        );
    }

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            AuthenticationManagerResolver<HttpServletRequest> issuerResolver)
            throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/public/**")
                    .permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .authenticationManagerResolver(issuerResolver))
            .build();
    }
}
~~~

**This is an alternative** to the `fromTrustedIssuers` configuration in section 5; do not accidentally declare both overlapping `SecurityFilterChain` beans in the same application.

If using `issuer-uri` and `jwk-set-uri` per tenant in a control plane, ensure that pair is **approved together**. Never trust tokens from issuer A while fetching keys from a caller-specified URI.

### 10.4. Why use a direct `jwkSetUri`?

`NimbusJwtDecoder.withJwkSetUri(...)` builds a decoder from an **explicit key source**, rather than discovering issuer metadata from `iss` in the request. A trusted registry maintains:

~~~text
Canonical issuer -> trusted JWKS URL
```

This keeps egress controlled and prevents arbitrary discovery for unapproved tenants.

Still, **a trusted key source does not replace the issuer validator**. That is why section 10.2 still sets `JwtValidators.createDefaultWithIssuer(spec.issuer())`.

### 10.5. If you want metadata discovery instead of direct JWKS

A manager created from:

~~~java
JwtAuthenticationProvider provider =
    new JwtAuthenticationProvider(
        JwtDecoders.fromIssuerLocation(approvedIssuer)
    );
~~~

is the option documented in Spring Security for dynamic tenants, **provided** `approvedIssuer` comes from a trusted registry. It may perform discovery/JWKS network calls when the manager is built or during decoding depending on version.

To add audience validators and custom timeouts/key settings, you will typically build the decoder per your version's API and attach explicit validators as in section 10.2.

**Never pass an unapproved `issuer` directly into `JwtDecoders.fromIssuerLocation`.**

## 11. When a tenant is disabled, how are in-flight requests and caches handled?

Removing an entry from the registry prevents **new lookups** from finding that issuer's manager:

~~~java
registry.deactivateIssuer("https://idp-b.example.com/realms/shop");
~~~

However, the system may still have:

- Requests that already resolved manager B and are mid-verification.
- Completed authentications currently executing in the service layer.
- Multiple replicas with unsynchronized registry state.
- Unexpired JWTs still held by clients.
- Cached JWK Sets inside decoder B.
- Separately cached database memberships/ACLs.

Therefore, never claim that `remove()` alone guarantees **every active request stops immediately**. If immediate system-wide revocation is required, define policies for in-flight requests, distributed registry consistency, token revocation, object/service authorization checks, and cache invalidation.

### 11.1. Tenant change scenarios

| Event | Expected behavior |
|---|---|
| Add approved tenant C | Once C is published, tokens for C are verified by manager C |
| Unapproved issuer D | No manager exists; no metadata/JWKS fetch to D |
| Tenant B disabled | Subsequent lookups do not find manager B |
| Tenant B re-enabled | A new manager is created only from approved trusted config |
| Tenant A JWKS URL changes | Updated via control plane, never from token headers |
| Tenant A audience policy changes | Manager/decoder is rebuilt/updated accordingly |
| Attacker sends thousands of unknown issuers | Rejected early without per-issuer managers, caches, or network calls |

### 11.2. Controlling the onboarding workflow

A `POST /admin/tenants` endpoint can be legitimate if it is **truly an internal control plane** with strong authentication, admin authorization, logging/auditing, and input validation. Never expose a public "register any issuer to test a JWT" endpoint that directly invokes `registerApprovedIssuer`.

Manage the tenant lifecycle as an audited approval workflow with rollback and testing, never as a side effect of bearer token requests.

## 12. `fromTrustedIssuers(Predicate)` or a dynamic repository?

| Approach | Pros | When appropriate |
|---|---|---|
| `fromTrustedIssuers(String...)` | Simple, clear static trust set | Few issuers, fixed deployment |
| `fromTrustedIssuers(Collection)` | Reads collection from managed config | List known at startup |
| `fromTrustedIssuers(Predicate)` | Flexible trust-check policy | Trusted registry with clear predicate |
| Constructor with `AuthenticationManagerResolver<String>` | Full control over managers, validators, and lifecycle | Dynamic onboarding, per-issuer JWKS/audience |
| Multiple `SecurityFilterChain`s | Isolates distinct API/web/route policies | Each request group has a distinct contract |

**Do not assume `Predicate` is a full dynamic registry.** It decides which issuers are trusted; the implementation may cache managers, so lifecycle, revocation, metadata updates, and configuration changes must be evaluated separately.

If you need explicit runtime *removal/reconfiguration of per-issuer managers*, an application-controlled `issuer -> AuthenticationManager` repository is usually clearer, provided config is synchronized across replicas and race conditions are handled.

## 13. Do not blindly select issuers from headers or subdomains

An API may use subdomains or paths to indicate the target tenant:

~~~http
GET /api/tenants/tenant-a/orders HTTP/1.1
Host: api.example.com
X-Tenant-Id: tenant-a
Authorization: Bearer <JWT>
~~~

That alone does not guarantee the bearer JWT belongs to tenant A. A client might intentionally send:

~~~text
Path tenant = tenant-a
JWT issuer  = issuer-b
```

Selecting a manager solely from headers/paths while skipping JWT issuer verification can cause **cross-tenant confusion**.

### 13.1. Two independent questions

1. **Who issued the JWT?** → `iss`, signing keys, issuer validation.
2. **Which tenant does the request target and is the principal authorized there?** → path/header target, membership/ACL after authentication.

Even when issuer A is tightly bound to tenant A, store that mapping in a trusted registry and update it through controlled procedures if tenant A changes issuers.

### 13.2. What if the route determines the issuer?

Some architectures enforce "`/tenants/a/**` accepts only issuer A." You can pick a manager by path if routing is carefully engineered, **provided you still verify the token's `iss` is issuer A** and validate the path tenant against membership post-authentication.

`JwtIssuerAuthenticationManagerResolver` is especially useful when selecting managers by **`iss`** rather than path; the two approaches involve trade-offs, never a replacement for the security boundary.

## 14. Audience, scopes, and issuer-specific authorities

One tenant may use scopes:

~~~text
orders.read
orders.write
```

while another tenant uses:

~~~text
read:orders
manage:orders
```

Never normalize them into the same permission without an explicit contract.

### 14.1. Default scope mapping

For a JWT containing:

~~~json
{
  "scope": "orders.read orders.write"
}
~~~

Spring Security typically converts this to:

~~~text
SCOPE_orders.read
SCOPE_orders.write
```

The rule:

~~~java
.hasAuthority("SCOPE_orders.read")
~~~

only checks for that authority; it does not understand which tenant or order is involved.

### 14.2. Customizing per-issuer converters

If AS B returns `roles` instead of `scope`, configure a dedicated `JwtAuthenticationConverter` on **B's `JwtAuthenticationProvider`**. Only derive authorities from claims that AS B is **authorized to grant for `orders-api`**; never map arbitrary email, username, or client claims into admin roles.

Conceptual example:

~~~java
JwtAuthenticationProvider provider =
    new JwtAuthenticationProvider(decoder);

JwtAuthenticationConverter converter =
    new JwtAuthenticationConverter();

// Only use the converter if claim mapping is controlled.
provider.setJwtAuthenticationConverter(converter);
~~~

`JwtAuthenticationConverter` has sensible defaults for OAuth scopes; custom role/permission claims require configuring the converter/`JwtGrantedAuthoritiesConverter` according to your version. Never alter a converter to "work around" a token lacking real permissions.

### 14.3. Role names can collide across issuers with different meanings

Issuer A's `ROLE_ADMIN` may mean realm A administrator; issuer B's `ROLE_ADMIN` may mean administrator of a different portal. Never treat both strings as **Resource Server-wide admin** privileges without an explicit role catalog and policy.

An authority **only has meaning within the context of a trusted source and application policy**.

## 15. Canonical principal identity in multi-issuer systems

After `JwtDecoder` succeeds, you can extract:

~~~java
Jwt jwt = authenticationToken.getToken();

String issuer = jwt.getIssuer().toString();
String subject = jwt.getSubject();
~~~

If business data keys records by `user-42` without the issuer, `user-42` from issuer B can collide with `user-42` from issuer A.

Define a domain identity:

~~~java
public record ExternalPrincipalId(
    String issuer,
    String subject
) {}
~~~

and an internal service mapping `(issuer, subject)` to a controlled `InternalUserId`.

**Never** use email or username as a primary owner key across multiple issuers without a dedicated, approved verification and identity-linking flow.

### 15.1. Distinguish client credentials tokens

A JWT from `client_credentials` typically represents a machine application, not a human user or tenant admin. Enforce policies for subject/client types and OAuth grant profiles rather than assuming the presence of `sub` implies human user access.

### 15.2. AS-issued `tenant_id` also needs a contract

If a verified JWT contains `tenant_id`, that claim is only trustworthy to the extent **"the AS asserted this."** The Resource Server must know whether that AS actually governs membership for that tenant. If tenant entitlements live in a separate database, the JWT claim is just a signal, not absolute authorization.

## 16. Resource permissions must still be checked after authentication

Consider the request:

~~~http
GET /api/tenants/tenant-a/orders/order-9001 HTTP/1.1
Authorization: Bearer <jwt-from-trusted-issuer-a>
~~~

Once the resolver and decoder succeed, Spring Security knows the token was issued by valid issuer A. The API must still ask:

~~~text
(issuer A, subject user-42)
       |
       +-- Has SCOPE_orders.read?
       |
       +-- Has membership in tenant-a?
       |
       +-- Does order-9001 belong to tenant-a?
       |
       +-- Is subject allowed to view this order?
       |
       +-- Are there order status/field-level access constraints?
```

Without tenant and ownership checks in the query, a user can guess order IDs to read someone else's order: **Broken Object Level Authorization (BOLA/IDOR)**.

### 16.1. HTTP rules are only the first layer

~~~java
.requestMatchers(HttpMethod.GET, "/api/tenants/*/orders/**")
    .hasAuthority("SCOPE_orders.read")
~~~

This rule does not decide whether the user may enter a specific tenant. Path matchers and wildcards only specify which routes require the read scope.

### 16.2. Illustrative service policy

~~~java
// Pseudocode: application-owned types/repositories.
Order order = orderRepository
    .findByIdAndTenantId(orderId, requestedTenant)
    .orElseThrow(NotFoundException::new);

ExternalPrincipalId actor =
    new ExternalPrincipalId(
        verifiedJwt.getIssuer().toString(),
        verifiedJwt.getSubject()
    );

if (!orderPolicy.canRead(actor, order)) {
    throw new AccessDeniedException("Forbidden");
}

return toDto(order);
~~~

`Order`, `NotFoundException`, `orderPolicy`, and `toDto` are illustrative domain abstractions. `verifiedJwt` is the JWT **already verified by the Resource Server**, not raw data decoded before authentication.

## 17. The double JWT parsing issue

Spring Security documentation notes a trade-off of resolving by the `iss` claim: the JWT may be **parsed once to read the issuer for manager selection**, and then **parsed/verified again inside `JwtDecoder`**.

~~~text
JWT
 |
 +-- 1st claim parse to find iss (routing, UNVERIFIED)
 |
 +-- Select AuthenticationManager for trusted issuer
 |
 +-- 2nd parse + verify + validate in JwtDecoder
```

This is extra parsing overhead, **not** the framework verifying the cryptographic signature twice by default.

### 17.1. Should you eliminate the first parse yourself?

Do not rush to write a custom parser/decoder to shave off minor parsing work before measuring latency. Compared to network JWKS fetches, DB authorization queries, and business logic, parsing overhead is rarely the main bottleneck.

Spring Security docs cover an advanced approach using Nimbus **`JWTClaimsSetAwareJWSKeySelector`**, which chooses the JWK source from the claim set during JWT processing. That design requires:

- A trusted tenant/issuer repository.
- Controlled per-tenant JWK selection.
- A properly configured `JWTProcessor`.
- A tenant-aware issuer validator, in addition to defaults.
- Accurate signature and claim checks.
- Tests for parsing, unknown issuers, key rotation, and cross-issuer attacks.

**This is not code to copy halfway.** Changing the key selector while forgetting the issuer validator or deriving the JWKS URL directly from an untrusted `iss` can weaken security just to parse once.

### 17.2. When to use the advanced key selector approach?

Consider it when:

- High issuer volume makes double parsing a measurable cost.
- You need centralized registry-driven JWKS management.
- The team can maintain custom Nimbus components and validators.
- Integration tests prove the trust boundary after optimization.

For most projects, **`JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` or a manager registry** is easier to review and less risky.

## 18. SSRF and resource abuse: it is not just about signatures

Issuer discovery can trigger HTTP calls to:

~~~text
https://issuer/.well-known/openid-configuration
https://issuer/.well-known/oauth-authorization-server
https://issuer/jwks
```

Exact endpoints and fallbacks depend on the decoder and profile; never hardcode all paths as universal across every AS.

If a caller can steer the issuer URL so the server makes outbound calls, impacts can include:

- SSRF against localhost, metadata IPs, or internal services.
- Internal network scanning via timing or error differences.
- DNS rebinding or redirects to unintended hosts.
- Prolonged connection timeouts and connection pool exhaustion.
- Fetching huge JWKS payloads causing resource exhaustion.
- Thundering herds when many issuers or unknown keys are requested.
- Tokens from a self-hosted attacker AS whose signatures look "valid" under the attacker's key.

### 18.1. Defense layers

1. **Exact issuer allowlist** from a trusted source.
2. Configure **trusted JWK Set URIs** per issuer where needed rather than deriving them from arbitrary caller input.
3. Enforce HTTPS, TLS validation, and hostname verification.
4. Control DNS, egress, redirects, and proxies at the infrastructure layer.
5. Enforce bounded timeouts and connection pools.
6. Cap onboarded issuers, JWKS payload sizes, key counts, and refresh rates.
7. Never log raw tokens or credentials on errors.
8. Test that unknown issuers **make zero outbound calls** to attacker hosts.
9. Separate canonical issuer strings from internal JWKS network hostnames.
10. Never share public key caches across issuers.

**Checking `issuer.startsWith("https://")` alone is not safe.** HTTPS does not turn any random domain into an Authorization Server your API is authorized to trust.

## 19. Canonical issuers and reverse proxies

In multi-tenant deployments, an AS may sit behind an ingress or reverse proxy:

~~~text
Issuer in JWT:
  https://login.example.com/realms/tenant-a

Internal JWKS URI:
  https://keys.internal.example/realms/tenant-a/certs
```

This can be valid when the control plane manages the issuer → JWKS URL mapping and TLS/egress are protected.

However:

- `iss` must match the **canonical external issuer** per contract.
- `jwk-set-uri` may point to a different internal network address.
- Never take a new issuer from the client's `Host` header.
- Never change `JwtValidators.createDefaultWithIssuer(...)` to an internal hostname just to silence metadata errors.
- If an AS emits the wrong `iss` due to proxy misconfiguration, fix the AS/proxy configuration instead of removing issuer validation.

**Issuer and JWK Set URI serve two distinct purposes.**

## 20. A token from a trusted issuer might still not be for your API

Suppose an AS issues:

~~~json
{
  "iss": "https://idp-a.example.com/realms/shop",
  "sub": "user-42",
  "aud": ["frontend-client"],
  "scope": "openid profile"
}
~~~

This token or ID token may be valid in another flow, yet it is **not** an access token intended for `orders-api`.

Accepting it solely because the issuer is on the allowlist causes **token substitution/cross-JWT confusion**.

You must:

- Verify the token is an access token per profile contract.
- Check `aud` matches this Resource Server.
- Check `iss` and signature.
- Enforce allowed JWS algorithms and key types.
- Validate `exp`/`nbf` with reasonable clock skew.
- Never use an OIDC Client ID token as an API Bearer credential.
- If the token type requires `at+jwt`, configure the corresponding type/profile validator for your framework version.

### 20.1. `JwtValidators.createDefaultWithIssuer(...)` does not know every custom policy

The default validator checks core claims such as issuer and timestamps per configuration, but **does not automatically know each API's business audience** or tenant-specific role policies.

With a custom decoder, use `DelegatingOAuth2TokenValidator` to combine issuer defaults with audience and other contract-required validators.

## 21. `kid` values can collide between two issuers

A JWT header contains:

~~~json
{
  "alg": "RS256",
  "kid": "main-key"
}
~~~

Issuer A and issuer B can easily both use `kid=main-key` with different public keys. `kid` is **not a globally unique identifier**.

Wrong:

~~~text
Cache key = kid
"main-key" -> public key used for every issuer
```

Conceptually right:

~~~text
Cache key = trusted issuer / configured JWK source + kid + key metadata
```

Nimbus/Spring Security manages key selection per JWK source. If you write a custom cache or shared key store, namespace it by tenant/issuer so token B can never be verified with key A just because `kid` matches.

### 21.1. Never treat `jku` in a JWT header as a trusted source

A header might contain:

~~~json
{
  "alg": "RS256",
  "kid": "x",
  "jku": "https://attacker.example/jwks"
}
~~~

`jku`/`x5u` are untrusted data inside the token. Never let them direct JWKS endpoint fetches; use the approved key source from the manager registry.

## 22. Testing: the issuer allowlist is a security boundary

To prove multi-issuer support works safely, create **separate test signing keys** for A/B and an untrusted issuer C.

### 22.1. Test matrix

| Scenario | Expected outcome |
|---|---|
| Token A signed by A, `iss=A`, `aud=orders-api`, unexpired | Authenticates; HTTP policy still applies |
| Token B signed by B, `iss=B`, `aud=orders-api` | Authenticates if B is trusted |
| Attacker self-signed token C, `iss=C` | Rejected; no metadata/JWKS fetch to C |
| Token with `iss=A`, signed with key B | Rejected |
| Token with `iss=B`, signed with key A | Rejected |
| Token A validly signed, `aud=billing-api` | Rejected when audience validator is active |
| Expired token A | Rejected |
| Token A with future `nbf` outside skew | Rejected |
| Token A with disallowed `alg` | Rejected |
| Malformed JWT missing `iss` | Rejected |
| `iss` differing only by a trailing slash | No match unless an exact entry exists |
| Valid issuer A, missing `SCOPE_orders.read` | Authentication succeeds, HTTP returns 403 |
| Issuers A and B sharing `sub=user-42` | Identities are not merged |
| Token from issuer A accessing tenant B without membership | Rejected by business authorization |
| Issuer B deactivated | New lookups are rejected |
| New key B appears in JWKS | Rotation handled per policy/version |
| AS B times out on first request | Must not fail open |

Actual HTTP status codes depend on your entry point, exception handler, and service routes, but the **security decision** must hold.

### 22.2. `MockMvc.with(jwt())` does not verify the resolver

Spring Security Test supports:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

This creates a **mock authenticated JWT**. It is useful for testing `hasAuthority`/HTTP authorization, yet it can **completely bypass** `JwtIssuerAuthenticationManagerResolver`, issuer selection, signatures, discovery/JWKS, and validators.

Never rely on the test above to claim "untrusted issuers are rejected."

### 22.3. Real tests passing through the Bearer filter

A proper integration test should:

1. Generate separate RSA/EC key pairs for issuers A and B.
2. Serve each tenant's public key from a fake JWKS endpoint A/B.
3. Configure the registry with the approved test JWKS URLs.
4. Sign real access tokens with the test private keys, setting `iss`, `aud`, and `exp`.
5. Send `Authorization: Bearer <signedJwt>` to `MockMvc` or an HTTP test server.
6. Verify A/B authenticate and C is rejected.
7. Verify `iss=A` signed with key B is rejected.
8. Verify wrong `aud` and expired tokens are rejected.
9. Count HTTP requests to the JWKS servers to prove C triggers **zero** outbound requests.
10. Verify that once B is disabled, no manager is selected for it.

**Never use real production private keys in tests.** Test JWKS responses must publish only test public key material.

### 22.4. Unit testing the registry without networking

You can test `resolve` mechanics with a fake registry/manager:

~~~java
AuthenticationManager aManager =
    authentication -> authentication; // Test stub only.

Map<String, AuthenticationManager> allowed = Map.of(
    "https://idp-a.example.com/realms/shop",
    aManager
);

JwtIssuerAuthenticationManagerResolver resolver =
    new JwtIssuerAuthenticationManagerResolver(allowed::get);
~~~

This stub is **strictly for unit testing manager selection**, never for production: it returns authentication without verifying the JWT. To test the actual trust boundary, use a real decoder and keys in integration tests.

### 22.5. Testing dynamic disablement

After `registry.deactivateIssuer(B)`, new requests with token B must fail to resolve manager B. However, if immediate revocation is required for requests already inside the service layer, add tests covering your lifecycle/concurrency policy—`remove()` does not automatically abort already-authenticated requests.

## 23. Distinguishing 401, 403, and issuer configuration errors

| Symptom | Likely root layer | What to check |
|---|---|---|
| No Bearer token on private API | Missing authentication | Returns 401 via Bearer entry point |
| JWT `iss` not in allowlist | Resolver finds no manager | Token rejected; no auto-onboarding |
| JWT `iss` missing or malformed | Cannot determine issuer | Invalid token |
| Correct `iss` but invalid signature | Issuer's decoder | JWK key source, algorithm |
| Correct `iss` and signature, wrong `aud` | JWT audience validator | API audience constraint |
| Token expired | Timestamp validator | `exp`, clock skew |
| Issuer A experiencing downtime | Discovery/JWKS | Timeouts, network, cache, TLS |
| Valid JWT but missing scope | HTTP authorization | 403 |
| JWT has scope but targets another tenant | Business authorization | Membership/ownership |
| Token A shares `sub` with B and reads B's data | Identity mapping | `(iss, sub)` namespace |
| New issuer not yet trusted | Control plane onboarding | Do not populate allowlist from runtime untrusted data |
| New `kid` missing from JWKS | Key rotation | AS publication, cache refresh |

**401** usually indicates an authentication failure; **403** usually indicates an authorization failure after a principal has authenticated. Network outages and discovery errors may be surfaced differently by handlers; do not assume every Spring Security version returns the exact same HTTP code for every failure.

For diagnostics, distinguish invalid tokens from unavailable JWKS sources without exposing issuer registry internals or token contents in responses.

## 24. Multiple `SecurityFilterChain`s and the issuer resolver

An application may contain:

- `/api/**` → Multi-issuer Resource Server.
- `/admin-ui/**` → browser login/session and CSRF.
- `/actuator/**` → operational endpoints under their own policy.

You can define multiple `SecurityFilterChain` beans, each with a `securityMatcher` and `@Order`. Attach `JwtIssuerAuthenticationManagerResolver` only to the **Resource Server chain** requiring Bearer tokens.

Verify that:

- The `/api/**` chain is actually matched.
- A broader earlier chain does not accidentally shadow the API chain.
- `anyRequest().denyAll()` on a narrowly matched chain **does not** protect URLs outside that chain's matcher.
- The API does not accept UI session cookies as authentication if the contract requires bearer-only auth.
- Decoders are never selected from an untrusted `Host` header.

`JwtIssuerAuthenticationManagerResolver` does not replace sound `SecurityFilterChain` design.

## 25. Comparing `JwtIssuerAuthenticationManagerResolver` and alternatives

| Need | Solution |
|---|---|
| Single issuer | `issuer-uri` / single `JwtDecoder` |
| Fixed set of multiple issuers | `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` |
| Dynamically added/removed issuers | `AuthenticationManagerResolver<String>` + trusted manager registry |
| Different audience/JWKS/policies per issuer | Registry with per-issuer `JwtAuthenticationProvider` and validators |
| Tenants separated by path under one issuer | Separate tenant context/authorization checks; issuer resolver alone is insufficient |
| Coexisting JWT and opaque tokens | `AuthenticationManagerResolver<HttpServletRequest>` selecting the appropriate token strategy |
| Fewer JWT claim parse passes | Nimbus `JWTClaimsSetAwareJWSKeySelector` per docs, with trust registry and issuer validators |
| Using Spring WebFlux | `JwtIssuerReactiveAuthenticationManagerResolver`, not the Servlet class |
| Simple `orders.read` authorization | `hasAuthority("SCOPE_orders.read")` after authentication |
| Per-order/per-tenant permissions | Domain/service ACL, membership, and live data checks |

Avoid unnecessary complexity if a static allowlist suffices. When you must manage tenant lifecycles, revocation, differing audiences, and multiple key sources, a governed registry is far safer than hardcoded controller logic.

## 26. Secure deployment checklist

Before shipping a multi-issuer Resource Server to production:

- [ ] Trusted issuers are configured from an authoritative source, never from client JWTs/headers.
- [ ] Every issuer uses an exact canonical URL, not broad host-suffix matching.
- [ ] The resolver rejects unknown issuers **before creating managers or making JWKS network calls**.
- [ ] Each decoder verifies the JWS signature with the JWK source matching that issuer.
- [ ] Allowed JWS algorithms are restricted per AS contract.
- [ ] `iss` is re-validated **after signature verification**, not only parsed beforehand.
- [ ] `aud` is validated for this Resource Server.
- [ ] `exp`, `nbf`, clock skew, and token type/profile policies are enforced.
- [ ] Role/scope mapping never elevates unknown usernames, emails, or groups to admin.
- [ ] Identity mapping uses issuer + subject or a trusted canonical internal ID.
- [ ] Business tenant membership, ownership, and object-level policies are enforced.
- [ ] Issuer onboarding enforces admin authentication, auditing, URL validation, and egress limits.
- [ ] Issuer deactivation propagates across replicas and accounts for in-flight requests.
- [ ] JWKS caching/rotation is monitored, without mixing `kid` across issuers.
- [ ] Outbound HTTPS, TLS, timeouts, retry limits, and metadata URLs are controlled.
- [ ] Tests cover unknown issuers, bad signatures, wrong audiences, expired tokens, missing scopes, and cross-tenant access.
- [ ] Tests prove zero outbound calls are made to attacker issuers.
- [ ] Raw JWTs, private keys, Authorization headers, and secrets are never logged.
- [ ] Servlet vs. WebFlux is clearly identified so the matching resolver class is used.
- [ ] A fallback `SecurityFilterChain` protects paths outside the API matcher.

## 27. Common misconceptions

**"The `iss` in a JWT payload is signed data, so reading it before verification is still trustworthy."** False. It is only protected *after* the signature is actually verified against the right trusted key.

**"If an issuer serves a valid HTTPS JWKS, the Resource Server must trust that issuer."** False. HTTPS secures transport to a domain; it does not prove your organization authorized that domain to issue tokens for your API.

**"`JwtIssuerAuthenticationManagerResolver` automatically trusts any issuer in the token."** False when configured properly; it requires a trusted issuer list or a strategy that only returns approved managers.

**"Using `fromTrustedIssuers(issuer -> true)` is safe because JWTs are signed."** False. An attacker can run their own AS and sign tokens with their own key.

**"Once the signature is valid, checking `aud` is unnecessary."** False. The token could be intended for a completely different API.

**"Two tokens with the same `sub` belong to the same person."** Not when the issuers differ and no trusted identity linking exists.

**"Issuer and tenant are always one-to-one."** No. One issuer can serve multiple tenants; one tenant can trust multiple issuers.

**"`tenant_id` in the URL proves membership."** False. It is a client-chosen target.

**"Any token with `SCOPE_orders.read` can view every order."** False. Object-level authorization is required.

**"`kid` is globally unique."** False. It can collide across issuers; key lookup must be scoped to the trusted issuer context.

**"JWT header `jku` tells the Resource Server where to fetch keys."** Not by default, because a caller can point it at an attacker-controlled URL.

**"Dynamic tenant onboarding means reading the issuer from a JWT and auto-registering it."** False. Additions and removals must go through a trusted control plane.

**"Disabling an issuer by removing a map entry immediately stops all authenticated requests."** No. In-flight requests, replicas, and caches remain.

**"The resolver loads every AS on application startup."** Not with the documented lazy trusted issuers behavior. However, the first request may still hit that network dependency.

**"A `MockMvc.with(jwt())` test proves untrusted issuers are rejected."** No. It mocks authentication and can bypass the resolver and decoder.

**"To avoid double parsing, just read the payload and skip the decoder."** False. Parsing optimizations must never trade away signature and issuer validation.

**"Changing the issuer validator to match an internal JWK hostname is valid."** No. The canonical issuer and the network path used to fetch public keys are two separate things.

## 28. Self-check questions

**1.** What is `JwtIssuerAuthenticationManagerResolver` used for?

> Routing JWT authentication by the bearer token's issuer claim in a multi-issuer Servlet Resource Server.

**2.** Why is `iss` untrusted before verification?

> Because the caller can alter the payload; the resolver should only use it to look up an approved **trusted manager**.

**3.** If a JWT claims `iss=https://attacker.example`, what should the Resource Server do?

> Reject it because the issuer is not on the allowlist, without auto-discovering or fetching the attacker's JWKS.

**4.** How do you create a resolver with a static list in Spring Security 6.2+?

> `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(issuerA, issuerB)`.

**5.** Why are the `String...`/`Collection` constructors no longer preferred?

> They were deprecated in 6.2; the `fromTrustedIssuers` factory methods are recommended in modern versions.

**6.** If `iss` is already validated, do you still need `aud`?

> Yes. Issuer states who minted the token; audience states which API the token is meant for.

**7.** Can a token with `iss=A` signed by key B get through?

> No. Manager A must verify against A's key source and reject invalid signatures.

**8.** If two issuers both emit `sub=user-42`, is it the same user?

> Not by default. You need an issuer namespace or an authoritative identity mapping.

**9.** Can you use a `ConcurrentHashMap<String,AuthenticationManager>` for dynamic tenants?

> Yes, provided entries are added only via trusted onboarding and per-issuer managers/validators are properly constructed—never auto-registered from requests.

**10.** Once manager B is removed, has all activity for B stopped immediately?

> Not guaranteed for in-flight requests, caches, or other replicas. A lifecycle policy is required.

**11.** Does `JwtIssuerAuthenticationManagerResolver` enforce per-order permissions?

> No. It handles authentication; ownership and tenant checks belong in the business authorization layer.

**12.** Why must you not select keys solely by `kid`?

> Because `kid` is not globally unique and different issuers can reuse key names.

**13.** Why do the docs mention the JWT is parsed twice?

> The first pass reads `iss` for routing; the second pass inside the decoder verifies and converts it into a validated `Jwt`.

**14.** Which resolver is used in WebFlux?

> `JwtIssuerReactiveAuthenticationManagerResolver` alongside Reactive security APIs.

**15.** Which test proves an unknown issuer makes no network call?

> An integration test sending a signed JWT from an untrusted issuer through the real bearer auth path with a JWKS/metadata stub counting outbound requests.

## 29. References

- [Spring Security — OAuth 2.0 Resource Server Multi-tenancy (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): trusted issuers, dynamic managers, single/double parsing.
- [Spring Security — JwtIssuerAuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html): `fromTrustedIssuers`, constructors, and `resolve`.
- [Spring Security 6.5 — JwtIssuerAuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html): `fromTrustedIssuers` version milestone and constructor deprecations.
- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer/JWK discovery, JWT validators, scopes.
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): JWK Set builder, algorithms, and validators.
- [Spring Security — JwtAuthenticationProvider API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationProvider.html): `JwtDecoder` and `JwtAuthenticationToken` creation.
- [Spring Security — JwtDecoders API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtDecoders.html): creating decoders from trusted issuer metadata.
- [Spring Security — WebFlux Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html): `JwtIssuerReactiveAuthenticationManagerResolver` counterpart.
- [Spring Security — Authorization HTTP Requests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): scope authorization at the HTTP boundary.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `sub`, `aud`, `exp`, `nbf`.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK and JWK Set.
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/audience/algorithm and cross-JWT confusion.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): OAuth JWT access token profile.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): bearer authentication, challenges, and errors.

**Conclusion:** `JwtIssuerAuthenticationManagerResolver` helps a Resource Server **route JWT authentication by issuer** across multiple tenants or Authorization Servers. Still, the `iss` used for initial routing remains **unverified data**; only a **pre-approved set of issuers** may supply or resolve managers. After selecting a manager, you must **verify the signature against the issuer's trusted JWK source and validate `iss`, `aud`, timestamps, and token profile**. Finally, tenant membership, per-order permissions, and identity namespacing remain the responsibility of business authorization—never skip them simply because a JWT came from an allowlisted issuer.
