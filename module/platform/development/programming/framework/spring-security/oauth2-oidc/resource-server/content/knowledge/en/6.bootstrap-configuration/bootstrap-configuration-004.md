# Configuring JWTs with issuer-uri, jwk-set-uri, or Managed Keys

A **Spring Security OAuth 2.0 Resource Server** receives an access token from a client, verifies the token, and decides API access permissions. When the access token is a **signed JWT (JWS)**, the Resource Server must have a **trusted source of public keys** to verify that the token was genuinely issued by the Authorization Server and has not been tampered with. Three common configuration approaches in Spring Boot are:

1. **`issuer-uri`:** declare a trusted issuer so Spring Security discovers metadata and the JWK Set URI.
2. **`jwk-set-uri`:** explicitly declare the endpoint publishing public keys, optionally combined with `issuer-uri` to keep validating `iss`.
3. **Managed key:** supply a public key via file or application configuration, or build a custom `JwtDecoder` when you do not want runtime reliance on metadata/JWKS endpoints.

These three approaches address **where verification keys come from**; they do not replace validating `aud`, `exp`, `nbf`, token type, scopes, and per-resource permissions. This lesson uses Spring Boot and Spring Security **Servlet/Spring MVC**; for WebFlux, use `ReactiveJwtDecoder` and `SecurityWebFilterChain` accordingly.

## 1. The Resource Server Trust Model

~~~text
Authorization Server                         Resource Server (orders-api)
     |                                                 |
     | signs JWT with private key                      |
     |                                                 |
     +--> Client --> Authorization: Bearer <JWT> ------>|
                                                       |
                                        1. Locate trusted public key
                                        2. Verify JWS signature
                                        3. Verify iss / aud / exp / nbf
                                        4. Map scope to authority
                                        5. Check endpoint/data permissions
                                                       |
                                                   200 / 401 / 403
~~~

With an asymmetric algorithm like `RS256`, the Authorization Server uses its **private key** to sign and the Resource Server uses the matching **public key** to verify. The public key can be published in a **JWK Set** or distributed via a trusted configuration management system. The Resource Server never needs the Authorization Server's private key.

A JWS compact JWT typically has three parts:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

The header may contain `alg`, `kid`; the payload contains `iss`, `sub`, `aud`, `exp`, and `scope`. Merely Base64URL-decoding the header/payload **proves nothing about validity**. After verifying the signature, Spring Security still needs validators for issuer, audience, timestamps, and token type. Once the token is valid, the application checks permissions.

### Spring Security Components to Know

| Component | Responsibility |
|---|---|
| `BearerTokenAuthenticationFilter` | Extracts the bearer token from the HTTP request |
| `JwtAuthenticationProvider` | Coordinates JWT authentication |
| `JwtDecoder` | Decodes and verifies the JWT per configuration |
| `NimbusJwtDecoder` | Standard implementation backed by Nimbus JOSE + JWT |
| `OAuth2TokenValidator<Jwt>` | Validates claims and token policies |
| `JwtAuthenticationConverter` | Maps a JWT to a principal/authorities |
| `SecurityFilterChain` | Enforces authentication and authorization rules |

A JWT with `scope="orders.read"` is normally converted by Spring Security into authority `SCOPE_orders.read`, **after the token is verified**. That is an authorization layer separate from signature verification.

## 2. Preparing the Spring Boot Application

### 2.1. Dependencies

In a Spring MVC application using Gradle:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

Spring Boot's Resource Server starter brings in the required JWT libraries. If managing Spring Security modules manually, JWT support requires both `spring-security-oauth2-resource-server` and `spring-security-oauth2-jose`.

### 2.2. Shared SecurityFilterChain Configuration

This filter chain works with all three public-key provisioning methods:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This configuration requires a JWT bearer token on protected routes. Specific requirements for CORS, CSRF, sessions, and browser cookies must be designed for the application's architecture; never disable CSRF unconditionally if browsers still use cookies to authenticate requests.

`oauth2.jwt()` only enables JWT processing. The Resource Server still needs to know **where to obtain public keys** and **which issuer/audience are accepted**.

## 3. Option A: `issuer-uri` — Discovering the Key Source via the Issuer

This is the common choice when the Authorization Server supports **OpenID Connect Discovery** or **OAuth 2.0 Authorization Server Metadata**.

### 3.1. Configuring application.yml

Suppose the published issuer is `https://idp.example.com/realms/shop` and this API's audience is `orders-api`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

Meaning:

- `issuer-uri` is the **trusted Authorization Server identifier**, not a token endpoint or login page.
- Spring Security can discover the issuer's metadata, locate `jwks_uri`, and use the public keys there to verify JWT signatures.
- Spring Security applies an `iss` validator matching the declared issuer.
- `audiences` is a Spring Boot property supported in modern releases to validate `aud`. If your Boot version does not support it, provide a custom audience validator.

**The `issuer-uri` value must exactly match the `iss` claim in tokens** per the Authorization Server contract. Differences in path or trailing `/` can cause issuer validation to fail.

### 3.2. What Happens During Discovery?

Conceptually:

~~~text
Resource Server
    |
    | trusted issuer-uri
    v
OIDC Provider Configuration / OAuth AS Metadata
    |
    | locate jwks_uri
    v
AS JWK Set endpoint
    |
    | public keys: kid, kty, n, e...
    v
JwtDecoder
    |
    +-- select matching key
    +-- verify signature
    +-- verify issuer, exp, nbf, audience, and policy
    v
Valid Authentication or error
~~~

Example metadata endpoint an OIDC provider **might** serve:

~~~text
https://idp.example.com/realms/shop/.well-known/openid-configuration
~~~

Illustrative response:

~~~json
{
  "issuer": "https://idp.example.com/realms/shop",
  "jwks_uri": "https://idp.example.com/realms/shop/protocol/openid-connect/certs"
}
~~~

Metadata/JWKS paths depend on the provider. Spring Security follows standard discovery rules for those endpoints matching the issuer, including issuers with paths. Do not guess URL structures when official docs/metadata exist.

### 3.3. Required Checks Beyond the Signature

With standard Spring Security Resource Server configuration, the system verifies signature, `exp`, `nbf`, and `iss` as configured. **Audience validation is not automatically enabled just by setting `issuer-uri`**; declare `audiences` or a custom validator.

For example:

~~~json
{
  "iss": "https://idp.example.com/realms/shop",
  "aud": ["billing-api"],
  "scope": "billing.read"
}
~~~

Even with a valid signature and matching issuer, `orders-api` must reject a token meant only for `billing-api`. Audience validation prevents clients from reusing tokens across different services in the same ecosystem.

### 3.4. Does Discovery Happen at Startup or on First Request?

Spring Security versions and setups can differ in when metadata/JWKS is fetched. Modern Spring Security docs describe **lazy discovery** of issuer details upon the first JWT via `SupplierJwtDecoder`. This avoids making application startup strictly depend on the AS always being online.

However, if you build a decoder with an eager factory or replace the default bean, accessing the AS may happen earlier. Therefore distinguish:

- **Application startup**: may not require immediate AS connectivity when using the appropriate lazy mechanism.
- **First JWT**: if metadata/keys are not yet cached, verification may need network access.
- **Subsequent JWTs**: public keys are cached per the decoder's mechanism; key rotation may trigger a refresh.
- **Custom JwtDecoder**: check exactly when the factory/bean executes.

Do not rely on blanket claims that "`issuer-uri` always blocks startup" or "`issuer-uri` never needs network at runtime." Check your actual Spring Boot/Security version and how the decoder is constructed.

### 3.5. When Should You Choose `issuer-uri`?

Ideal when the Authorization Server publishes standard metadata, the Resource Server can reach the AS/JWKS, key rotation across multiple keys is needed, and you want clean Spring Boot configuration. This is usually the best starting point for standard IdPs/OIDC Providers.

## 4. Option B: `jwk-set-uri` — Explicitly Specifying the JWK Set Endpoint

Some Authorization Servers issue JWTs and publish JWKS without supporting metadata discovery, or operations teams want explicit control over the JWKS URL.

### 4.1. Configuring Only `jwk-set-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
~~~

Spring Security knows the public key source without discovering the URI from metadata. However, remember:

> **The JWK Set URI states where to fetch keys; it does not by itself define which issuer is valid.**

If you declare only `jwk-set-uri`, Spring Security does not automatically check the `iss` claim against an expected issuer. The Resource Server must add issuer validation when the API has a fixed trusted issuer. Also validate `aud` and other token policies.

### 4.2. Recommended Configuration When Both Issuer and JWKS Are Known

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

This is a clean combination:

| Property | Responsibility |
|---|---|
| `issuer-uri` | Trusted `iss` value |
| `jwk-set-uri` | Trusted source of public keys |
| `audiences` | Resource/API the token must target |

When `jwk-set-uri` is set, the Resource Server **does not need metadata discovery just to find the JWKS URI**. Still, it may need to reach the JWKS endpoint to fetch uncached or rotated keys. If the AS/JWKS loses connectivity, JWTs signed with already-cached keys may continue working depending on cache settings and configuration.

### 4.3. JWK Set and `kid`

Simple example JWKS response:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-A",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus-A>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-key-B",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-modulus-B>",
      "e": "AQAB"
    }
  ]
}
~~~

- `keys`: list of public keys.
- `kid`: key identifier helping match the key referenced in the JWT header.
- `kty`: key type, e.g., RSA.
- `alg` and `use`: describe algorithm/intended use if provided by the AS.
- `n`, `e`: RSA public key components.

This illustrative example contains no real keys. An Authorization Server should never expose private-key material in a public JWKS.

A JWT header might contain:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-B"
}
~~~

`kid` is only a **key-selection hint within an already-trusted JWKS source**. A JWT header is unverified input; never fetch an arbitrary URL from `jku` or `x5u` headers and trust an attacker's key. The trusted JWKS URI must come from application configuration management, never from the request.

### 4.4. Creating a JWKS Decoder in Java

When you need custom validators instead of properties alone, for example:

~~~java
package com.example.orders.security;

import java.util.List;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class JwksDecoderConfig {

    private static final String ISSUER =
        "https://idp.example.com/realms/shop";
    private static final String JWKS =
        "https://idp.example.com/realms/shop/protocol/openid-connect/certs";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS).build();

        OAuth2TokenValidator<Jwt> audience =
            new JwtClaimValidator<List<String>>(
                "aud", values -> values != null &&
                        values.contains("orders-api")
            );

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience
            )
        );

        return decoder;
    }
}
~~~

This preserves **issuer, timestamp, and audience validation** when building a custom decoder. `JwtValidators.createDefaultWithIssuer(...)` supplies default checks plus issuer verification; `JwtClaimValidator` adds the audience check.

In a real application, move the URLs and expected audience into environment-specific configuration properties. Issuer and JWKS URLs must be controlled by a trusted system.

**Note on Spring Boot auto-configuration:** when you declare your own `JwtDecoder` bean, Boot typically backs off from creating the default decoder. Do not assume YAML properties like `audiences` will automatically attach to a decoder you write yourself. Explicitly wire all required validators.

## 5. Option C: Locally Managed Verification Keys

If the Resource Server cannot reach a JWKS endpoint, or deployment infrastructure distributes the public key via file/config volumes, you can use a managed RSA public key.

### 5.1. The `public-key-location` Property

Spring Boot supports pointing to a public key file:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          public-key-location: classpath:keys/as-public.pem
          audiences:
            - orders-api
~~~

Example `src/main/resources/keys/as-public.pem` in **PEM X.509 SubjectPublicKeyInfo** format:

~~~text
-----BEGIN PUBLIC KEY-----
<base64-encoded-public-key>
-----END PUBLIC KEY-----
~~~

The middle line is placeholder data, not a usable key. For asymmetric JWS, the Resource Server only needs the public key to verify and **must not hold the AS's private signing key**.

You can place the file outside the application artifact:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          public-key-location: file:/etc/orders/security/as-public.pem
~~~

This fits operations setups that distribute public keys via volumes or configuration management. However, **replacing the file on disk does not guarantee a running decoder reloads the key**. You need a reload strategy, rolling restarts, or an alternative key-distribution mechanism.

### 5.2. Where Are Managed Keys Stored?

"Managed key" can follow several patterns:

| Pattern | Characteristics | Considerations |
|---|---|---|
| Public key packaged in JAR | Minimal runtime dependencies | Key rotation may require rebuild/redeploy |
| Public key on mounted volume | Decouples key from artifact | Must manage read permissions and reloading |
| Public key from config/secret manager | Centralized management, audit | Protect write access to trust source and caching |
| Organization-managed internal JWKS | Publishes multiple public keys | Still follows the `jwk-set-uri` pattern |
| AS private key in HSM/KMS | Protects signing operations at AS | RS normally only reads the public key, needs no signing permission |

The fact that a **public key is not secret** does not mean anyone should be allowed to modify it. If an attacker replaces the trusted public key in the Resource Server's configuration, they can make the API accept tokens signed with a private key they control.

### 5.3. Limitations of a Single Fixed Key

With `NimbusJwtDecoder.withPublicKey(publicKey)`, a static decoder trusts only the key passed in. It has no awareness of the AS's key rotation list. When the AS rotates its signing private key, the API must receive the corresponding new public key. During the overlap when both old and new JWTs remain valid, multiple keys may need to be accepted simultaneously; JWKS with multiple public keys is usually much better suited than hardcoding one key.

If using `public-key-location`, the Resource Server also cannot infer the **valid issuer** from the public key itself. Ensure an issuer validator (and audience validator) is active per your Boot/Security configuration.

### 5.4. Building a Decoder from a Managed RSA Public Key

Example application loading an RSA public key from a resource path and explicitly configuring issuer/audience:

~~~yaml
security:
  jwt:
    public-key-location: file:/etc/orders/security/as-public.pem
    issuer: https://idp.example.com/realms/shop
    audience: orders-api
~~~

~~~java
package com.example.orders.security;

import java.security.interfaces.RSAPublicKey;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
public class ManagedPublicKeyConfig {

    @Bean
    JwtDecoder jwtDecoder(
        @Value("${security.jwt.public-key-location}") RSAPublicKey publicKey,
        @Value("${security.jwt.issuer}") String issuer,
        @Value("${security.jwt.audience}") String audience
    ) {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withPublicKey(publicKey).build();

        OAuth2TokenValidator<Jwt> audienceValidator =
            new JwtClaimValidator<List<String>>(
                "aud",
                aud -> aud != null && aud.contains(audience)
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

Spring Security supports converting certain RSA public key resources into `RSAPublicKey` via an appropriate conversion service. In apps without that converter active, you can inject a `Resource` and parse the PEM using `RsaKeyConverters.x509()` or configure a dedicated key-loading bean. Verify key loading against your exact version and integration setup.

**Key takeaway:** `withPublicKey(...)` selects the public key for signature verification—it **does not configure issuer or audience**. The example above explicitly wires `JwtValidators.createDefaultWithIssuer(...)` alongside the audience validator.

### 5.5. Do Not Confuse Public Keys with Private Keys or Shared Secrets

~~~text
Authorization Server                      Resource Server
  private key                                public key
      |                                          |
      | sign JWT                                 | verify JWT
      v                                          v
     JWT -------------------------------------> JWT
~~~

- **Private key** signs asymmetric JWS tokens; only the AS or an authorized signing service should hold it.
- **Public key** verifies signatures; it can be distributed to many Resource Servers.
- **HMAC secret (HS256)** is shared for both creating and verifying MACs; sharing the secret with an RS gives that RS the ability to forge MACs as well. That carries a different trust risk than asymmetric signing. Spring Security supports `withSecretKey`, but you should avoid defaulting to HMAC in multi-Resource-Server systems where separating signing authority matters.

## 6. Comparing the Three Options

| Criterion | `issuer-uri` | `jwk-set-uri` | Managed public key |
|---|---|---|---|
| Known upfront | Issuer | JWKS URI | Public key/resource |
| Metadata discovery | Yes | Not needed to find JWKS | Not needed |
| Source of public keys | JWKS discovered via metadata | JWKS configured directly | File/config/key provider |
| `iss` validation | Yes, per issuer config | Needs issuer/validator configured | Needs issuer/validator configured |
| `aud` validation | Configure audience explicitly | Configure audience explicitly | Configure audience explicitly |
| Multiple public keys | Via JWKS | Via JWKS | Depends on management setup |
| Rotation | JWKS refresh | JWKS refresh | Key redistribution/reload |
| Runtime network | Metadata/JWKS when needed | JWKS when needed | Can operate offline |
| Best fit | AS supports discovery | AS only exposes JWKS or fixed endpoint desired | Network-isolated infra, dedicated key delivery |
| Operational risks | Bad/unavailable metadata | Wrong URI or forgotten issuer | Stale key, wrong format, no reload |

Selection rule:

~~~text
Does the Authorization Server support standard discovery?
    |
    +-- Yes ---> issuer-uri
    |              |
    |              +-- To specify JWKS explicitly: add jwk-set-uri
    |
    +-- No
         |
         +-- Has JWKS endpoint ---> jwk-set-uri + issuer validator
         |
         +-- Only has public key -> public-key-location/custom JwtDecoder
~~~

Across all three branches, validate `iss`/`aud` per the API contract. Never choose a key strategy based solely on a token being "readable with Base64URL."

## 7. Controlling the JWT Signing Algorithm

A token header can declare:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-02"
}
~~~

The JWT header is **untrusted data prior to verification**. The decoder must enforce an allowed signing algorithm and verify the matching key type. Standard Spring Security configuration trusts algorithms per the decoder's policy, typically `RS256` in documented defaults.

When the AS actually signs with `RS512`, you can configure:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
          jws-algorithms:
            - RS512
~~~

Or in a custom decoder:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;

// ...
NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withJwkSetUri(jwksUri)
    .jwsAlgorithm(SignatureAlgorithm.RS512)
    .build();
~~~

If creating a custom decoder, remember to attach claim validators as shown earlier. Never change algorithms to "fix" a forged JWT; confirm the exact algorithm the AS uses to sign and ensure a compatible public key.

Never accept `alg=none` on an API requiring signed JWTs, and never allow a token to alter key sources or algorithms outside your trust configuration.

## 8. Issuer, Audience, and Lifetime Are Separate Validation Layers

### Issuer (`iss`)

The issuer asserts who issued the token under the contract. For a fixed issuer:

~~~json
{
  "iss": "https://idp.example.com/realms/shop"
}
~~~

It must match what the API trusts. A caller modifying `iss` in the payload does not make the token valid because the signature is verified alongside the claims.

### Audience (`aud`)

Audience answers **which API this token is intended for**:

~~~json
{
  "aud": ["orders-api"]
}
~~~

If a token is meant for `inventory-api`, `orders-api` must reject it even when the signature and issuer are valid. In modern Spring Boot, use `spring.security.oauth2.resourceserver.jwt.audiences`; custom decoders must wire an audience validator explicitly.

### Validity Period

- `exp`: rejects expired JWTs.
- `nbf`: rejects JWTs before their valid-from timestamp.
- `iat`: issuance time; additional token-age policies may be applied.

Spring Security provides `JwtTimestampValidator` and enforces time checks by default in standard configurations. If overriding validators with custom logic, retain all required time checks. Keep clock skew bounded intentionally and synchronize server clocks.

### Token Type and Profile

In OpenID Connect, an **ID token** is meant for the OIDC client; an **access token** is meant for the Resource Server. Do not accept an ID token in place of an access token simply because both are JWTs. For RFC 9068 JWT access token profiles, you can additionally check token type and profile claims. This is an additional policy beyond merely picking a public key.

### After the Token Is Valid: Authorization

An access token with `scope=orders.read` may allow `GET /api/orders`, yet still must not permit `POST /api/orders`. Even with read scope, the API must verify whether the user is authorized for the **specific order**.

## 9. Key Rotation and Public Key Caching

### 9.1. Rotation via JWKS

An AS can transition from `key-A` to `key-B` in phases:

~~~text
T0: JWKS has key-A; AS signs with key-A
T1: JWKS publishes key-A and key-B
T2: AS starts signing new JWTs with key-B
T3: Tokens signed with key-A have expired
T4: AS removes key-A from JWKS
~~~

While JWKS publishes both public keys, the Resource Server can verify both old and new tokens during the transition window. The decoder/JWKS cache must refresh appropriately when encountering a new `kid`. Common mistakes include the AS signing with a new key before publishing it in JWKS, or removing the old key too early.

Spring Security/Nimbus JWKS handling includes caching/refresh depending on the implementation and version. Operations teams should check timeouts, cache TTL, key-rotation schedules, TLS/DNS, and behavior when JWKS cannot be fetched.

### 9.2. Rotating a Key File

If the Resource Server loads a **single fixed public key**, updating the file or environment variable does not automatically refresh an existing `JwtDecoder` bean immediately. Plan key deployments or reloads carefully. If multiple keys must be accepted concurrently, prefer JWKS or a trusted multi-key `JWKSource` instead of hardcoding a single public key.

### 9.3. Should the Old Key Be Removed Immediately?

Not necessarily. Access tokens signed with the old key may still be within their lifetime. Removing the key from JWKS before all old tokens expire will cause the API to return `401` for those tokens. Removal timing should balance security, token lifetimes, and emergency revocation needs.

In the event of private key compromise, immediate key revocation/removal takes priority even if previously valid tokens are disrupted. That is an incident-response decision requiring system-wide coordination.

## 10. Environment-Specific Configuration

Never mix up issuer/JWKS/public keys across dev, staging, and production.

`application-dev.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp-dev.example.com/realms/shop
          audiences:
            - orders-api-dev
~~~

`application-prod.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          jwk-set-uri: https://idp.example.com/realms/shop/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Issuer/JWKS addresses may be public information, yet **permission to modify them is security-sensitive**. If an attacker changes `jwk-set-uri` to an endpoint they control, they can make the API trust forged signatures when other checks are insufficient.

For filesystem-mounted keys, set strict read-only permissions, define rotation lifecycles, and ensure all instances read the same key version during rollouts. Never store the AS private key in a Resource Server repository, container image, or config.

## 11. Custom Decoders and Impact on Auto-Configuration

If the application defines a bean:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    return NimbusJwtDecoder.withJwkSetUri(jwksUri).build();
}
~~~

Spring Boot typically **backs off** instead of creating another default `JwtDecoder`. Consequently:

- YAML properties such as `issuer-uri` or `audiences` may not be applied to your custom decoder.
- `withJwkSetUri(...)` only chooses the key source; it does not know the trusted issuer.
- When calling `setJwtValidator(...)`, combine issuer, timestamp, and audience checks rather than accidentally overwriting required validators.
- Defining an eager bean may change when metadata/JWKS is fetched compared to lazy auto-configuration.
- If multiple filter chains exist, verify which chain actually handles the target URL.

If standard issuer/JWKS/audience selection is all you need, Boot YAML configuration is usually cleaner and less prone to missing validators.

### Avoid Confusing the Two Decoder APIs

~~~java
JwtDecoder byIssuer =
    JwtDecoders.fromIssuerLocation(issuerUri);

NimbusJwtDecoder byJwks =
    NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();
~~~

`fromIssuerLocation(...)` expects an **issuer URI**, not a JWKS URL. `withJwkSetUri(...)` expects a **JWK Set URI**, not an issuer URI. With a decoder built from the JWKS builder, add issuer validation manually when needed.

## 12. Multiple Issuers or Multi-Tenant Scenarios

A multi-tenant Resource Server may need to accept JWTs from a curated set of enterprise-approved issuers:

~~~text
tenant-A -> https://idp-a.example.com
tenant-B -> https://idp-b.example.com
~~~

In this case, the application may inspect the **unverified** `iss` claim to select a decoder. This is only allowed as a **hint to pick a candidate from a trusted issuer allowlist**, after which the chosen decoder must still verify the signature, issuer, audience, and tenant policy.

Never automatically discover JWKS from arbitrary `iss` URLs sent by clients; doing so opens SSRF risks or lets an attacker steer the Resource Server to a rogue issuer. Use a trust registry/allowlist, restrict network destinations, and control per-tenant configuration.

Multi-tenant APIs in Spring Security can evolve across releases; pick a design compatible with your stack and avoid rolling custom unverified-token key selection unless necessary.

## 13. Diagnosing JWT Configuration Errors

### 13.1. `401 Unauthorized`

Common causes:

| Symptom | Where to check |
|---|---|
| JWT payload is readable, but signature rejected | Public key/JWKS, algorithm, JWS signature |
| `iss` differs from `issuer-uri` | Actual issuer from AS; path and trailing `/` |
| `aud` does not contain this API | Audience validator, which API the token was issued for |
| JWT expired / not yet valid | `exp`, `nbf`, clock synchronization, clock skew |
| Header has new `kid` but API lacks the key | AS JWKS, cache/refresh, rotation |
| JWKS returns 404 or TLS error | URI, DNS, certificate trust, firewall, proxy |
| AS does not support discovery | Switch to direct `jwk-set-uri` and keep issuer validation |
| ID token or opaque token sent instead of JWT access token | OAuth/OIDC flow, token type, Resource Server config |
| YAML is correct, yet decoder behaves differently | Is there a custom `JwtDecoder` bean or multiple SecurityFilterChains? |

**Note:** seeing `scope` or `iss` via a Base64URL decoder does not mean the token is valid. A JWT payload is easily readable even when the signature is forged.

### 13.2. `403 Forbidden`

If the JWT authenticates successfully but lacks `SCOPE_orders.write` for a POST request, the API may return `403`. This is an **authorization** error, not necessarily tied to the key source. Beyond scopes, services may also enforce ownership or tenant rules.

### 13.3. JWKS/AS Unavailability

- With `issuer-uri`, metadata/JWKS may need to be fetched if discovery or refresh has not completed.
- With `jwk-set-uri`, discovery is skipped, yet network access to the JWKS endpoint may still be required.
- With a managed public key in local resources, offline verification works as long as the decoder holds the right key.
- With a populated JWKS cache, some tokens may continue verifying during an endpoint outage; never assume all tokens or new keys will work.

Never **fail open** and accept unverified tokens simply because the AS/JWKS is unreachable.

### 13.4. Malformed Public Key File

Real-world pitfalls:

- Wrong path or the service account lacks read permission.
- File contains `-----BEGIN RSA PUBLIC KEY-----` (PKCS#1) instead of `-----BEGIN PUBLIC KEY-----` (X.509 SubjectPublicKeyInfo) expected by the loader.
- File is a PEM certificate or private key in an unsupported format.
- Public key does not match the private key used by the AS to sign.
- Algorithm expects EC, yet config provides an RSA public key.
- File was updated, yet the decoder retains the old key in memory.

Resolve by confirming the key material format and loader contract; never disable signature verification just to "make it work."

## 14. Protecting Tokens and Configuration Data

A Bearer token is a credential: anyone possessing a valid access token can exercise its granted permissions unless additional bindings exist. Therefore:

- Use HTTPS both when clients call the Resource Server and when the Resource Server fetches metadata/JWKS.
- Never log raw `Authorization` headers or access tokens.
- Never paste real tokens into online JWT decoder sites, chats, tickets, or public issues.
- Never expose debug endpoints letting clients read internal trust config or full JWT claims.
- Restrict audience, scope, and token lifetimes.
- Emit categorized failure telemetry without leaking credentials.

Illustrative log:

~~~text
event=jwt_authentication_failed
path=/api/orders
reason=invalid_audience
expectedAudience=orders-api
traceId=3c2a...
bearerToken=[REDACTED]
~~~

JWKS/issuer URLs may be public URLs, yet they remain **trust anchors**, so protect configuration change workflows and monitor key rotations.

## 15. Complete Implementation Example: orders-api Using `issuer-uri`

When the AS publishes standard metadata, the setup is concise:

`build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.com/realms/shop
          audiences:
            - orders-api
~~~

`SecurityConfig.java`:

~~~java
package com.example.orders.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/actuator/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

A controller can use the authenticated JWT principal:

~~~java
package com.example.orders.api;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class IdentityController {

    @GetMapping("/api/orders/whoami")
    public Map<String, String> whoami(
            @AuthenticationPrincipal Jwt jwt) {
        return Map.of("subject", jwt.getSubject());
    }
}
~~~

This example assumes a valid token has a non-null `sub` per the AS contract. In production, avoid returning unnecessary sensitive claims and still enforce data-level permissions.

Call the API with a test access token issued by the AS:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.example.com/api/orders/whoami
~~~

Typical outcomes:

| Scenario | Expected HTTP | Reason |
|---|---|---|
| Valid JWT, right issuer/audience, has `orders.read` | `200` | Authentication and authorization succeed |
| No bearer token sent | `401` | Unauthenticated |
| JWT with invalid signature | `401` | Rejected by decoder |
| Valid signature, wrong `iss` | `401` | Issuer validation failed |
| Valid signature, wrong `aud` | `401` | Audience validation failed |
| Expired JWT | `401` | Time validation failed |
| Valid JWT missing `orders.read` | `403` | Missing authority |
| Cannot fetch JWKS when new key needed | Depends on exception/cache handling | Unable to verify token |

Actual HTTP status codes can vary with filter chains, exception handlers, and custom error mappings; observe runtime behavior.

## 16. Real-World Selection Scenarios

### Scenario A — Standard OIDC Provider

The AS publishes `.well-known/openid-configuration` and `jwks_uri`. Use `issuer-uri` alongside `audiences` to minimize manual configuration and support JWKS rotation seamlessly.

### Scenario B — AS with JWKS Only

No discovery endpoint exists, yet a trusted JWKS URL is available. Use **`issuer-uri` + `jwk-set-uri` + `audiences`** if appropriate; direct JWKS fetches the keys while the issuer property validates the `iss` claim.

### Scenario C — API Running in an Isolated Network

The Resource Server cannot reach metadata/JWKS, but receives the public key via deployment infrastructure. Use `public-key-location` or a custom `JwtDecoder`, wire full issuer/audience validators, and establish a key rotation workflow.

### Scenario D — Multiple Issuers

Never let clients choose arbitrary JWKS endpoints. Maintain an approved issuer allowlist, select decoders via a registry, re-verify the issuer after selection, and enforce tenant/audience policies.

## 17. Common Misconceptions to Avoid

**"`issuer-uri` is the JWKS address."** False. It is the issuer identifier. Spring Security uses it to discover JWKS via metadata.

**"`jwk-set-uri` guarantees `iss` is correct."** False. You still need an issuer validator or the issuer property configured alongside it.

**"Setting `issuer-uri` automatically checks `aud`."** Not by default. Explicitly configure the expected audience.

**"`jwk-set-uri` means the API has zero network dependencies."** False. It skips metadata discovery, but still needs to fetch/refresh JWKS when required.

**"Having a public key file makes every JWT valid."** False. The public key only handles signature verification; claims and permissions still must be checked.

**"Spring Boot always honors my properties even with a custom JwtDecoder."** Not guaranteed. A custom bean can cause auto-configuration to back off.

**"The JWT `kid` header is a source of trust."** False. It is merely a hint for selecting a key within an already-trusted key set.

**"A public key file reloads automatically when replaced."** Not by default. The decoder may cache the loaded key in memory; plan reloads/deployments.

**"The RS needs the AS's private key to verify."** False for asymmetric algorithms; the RS only needs the public key.

**"A validly signed JWT can call any endpoint."** False. Audience, scopes, and authorization policies still govern access.

## 18. Self-Check Questions

**Q1.** The AS supports standard discovery and rotates public keys via JWKS. How should you start?

> Use `issuer-uri` and the expected audience. Spring Security discovers the key source and validates the issuer per configuration.

**Q2.** The AS has no metadata, only a JWKS URL. How do you keep issuer validation?

> Declare both `issuer-uri` and `jwk-set-uri`, or build a custom decoder with `JwtValidators.createDefaultWithIssuer(...)`.

**Q3.** A JWT has `aud=billing-api` and is signed with the same key that `orders-api` trusts. Should it be accepted?

> No. If `orders-api` requires `aud=orders-api`, the audience validator must reject the token.

**Q4.** When the AS rotates keys, new tokens get `401` while old tokens still work. What should you check?

> The new `kid`, whether JWKS has published the new public key, cache/refresh behavior, algorithm, TLS/DNS, and endpoint reachability. Never skip signature verification.

**Q5.** With `public-key-location`, does the Resource Server need the private signing key?

> No. The RSA public key suffices for asymmetric JWS verification; the private key must stay protected at the Authorization Server.

**Q6.** You declared a custom `JwtDecoder` bean and the `audiences` property no longer takes effect. How do you fix it?

> Account for Boot's auto-configuration back-off and attach the audience validator directly to your custom decoder while preserving issuer/time validation.

## 19. References

- [Spring Security — OAuth 2.0 Resource Server JWT (Servlet)](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): issuer discovery, direct JWK Set URI, trusted algorithms, validation, and authorization.
- [Spring Boot — OAuth2 Resource Server](https://docs.spring.io/spring-boot/reference/security/oauth2.html): `issuer-uri`, `jwk-set-uri`, `public-key-location`, and `audiences` properties.
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): builders using issuer, JWK Set, RSA public key, and shared secret.
- [RFC 7515 — JSON Web Signature](https://www.rfc-editor.org/rfc/rfc7515): JWS format and signatures.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK and JWK Set.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT claims.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): AS metadata standard.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer and OIDC provider configuration.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): algorithm and key trust, issuer/audience validation.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): JWT access token profile.

When configuring a Resource Server, clearly separate three decisions: **where trusted public keys come from**, **which issuers/audiences are allowed**, and **which requests are authorized once a token is valid**. `issuer-uri`, `jwk-set-uri`, and managed keys solve the first part; validators and Spring Security policies solve the rest.
