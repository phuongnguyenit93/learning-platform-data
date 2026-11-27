# Verifying Signature, Issuer, Audience, and Timestamps

## 1. Why Can a JWT with a Valid Signature Still Be Rejected?

In a **Spring Security OAuth 2.0/OIDC Resource Server using WebFlux**, the client sends the access token to the API via HTTP Bearer:

    GET /api/orders/42 HTTP/1.1
    Host: orders-api.example.com
    Authorization: Bearer eyJhbGciOiJSUzI1NiIsImtpZCI6ImsxIn0...

A properly signed JWT **does not prove on its own that it is meant for the API receiving the request**. The Resource Server must verify simultaneously:

1. **JWS signature**: was the JWT signed with a trusted key and a permitted algorithm?
2. **Issuer (iss)**: was the token issued by the exact Authorization Server the API trusts?
3. **Audience (aud)**: was the token issued for this API, rather than a different API?
4. **Timestamps (exp and nbf)**: is the token within its validity window?
5. **Issued At (iat)**: if the API requires token freshness or max-age, does `iat` satisfy the custom policy?
6. **Token purpose/profile**: is the token an access token intended for the Resource Server, rather than an OIDC ID token or JWT assertion?
7. **Authorization**: once the token is authenticated, do scopes, roles, and domain policy allow the action?

Separate **credential authentication** from **business authorization**. A token with valid signature, issuer, audience, and timestamps but only the `orders.read` scope can authenticate successfully; if the endpoint requires `orders.write`, the request is normally rejected with HTTP 403. Conversely, a JWT with `orders.write` scope but `aud=billing-api` must be blocked at token acceptance, usually HTTP 401.

Visualize it as:

    tokenAccepted =
        signatureValid
        AND jwsAlgorithmAllowed
        AND issuerTrusted
        AND audienceMatchesResource
        AND timeWindowValid
        AND tokenProfileValid

    requestAllowed =
        tokenAccepted
        AND scopeOrAuthorityAllowed
        AND domainPermissionAllowed

**Signature, issuer, audience, and timestamp conditions operate with logical AND. None of them can substitute for another.**

## 2. Where JWT Verification Fits in Spring WebFlux

Typical flow:

    HTTP Authorization: Bearer JWT
                 |
                 v
    ServerWebExchange / WebFilterChainProxy
                 |
                 v
    AuthenticationWebFilter
                 |
                 v
    ServerBearerTokenAuthenticationConverter
      extracts raw credential, unauthenticated
                 |
                 v
    BearerTokenAuthenticationToken
                 |
                 v
    ReactiveAuthenticationManager
                 |
                 v
    ReactiveJwtDecoder
      - parse JWS
      - fetch key from trusted JWKS
      - verify signature and algorithm
      - validate iss, aud, exp, nbf, token profile
                 |
                 v
    Authentication with principal and authorities
                 |
                 v
    ReactiveSecurityContextHolder
                 |
                 v
    WebFlux authorization / method security
                 |
                 v
    Controller / domain service

Components:

| Component | Role |
|---|---|
| **ServerBearerTokenAuthenticationConverter** | Extracts the Bearer credential from `ServerWebExchange` |
| **BearerTokenAuthenticationToken** | Carries the raw token before authentication |
| **ReactiveAuthenticationManager** | Coordinates the authentication process |
| **ReactiveJwtDecoder** | Reactive API to decode/verify/validate JWTs |
| **NimbusReactiveJwtDecoder** | Spring Security implementation using Nimbus JOSE + JWT |
| **OAuth2TokenValidator<Jwt>** | Contract for JWT claim validation |
| **JwtIssuerValidator** | Validates `iss` |
| **JwtTimestampValidator** | Validates `exp` and `nbf` with clock skew |
| **DelegatingOAuth2TokenValidator** | Combines multiple validators |
| **ServerHttpSecurity** | WebFlux security configuration DSL |
| **SecurityWebFilterChain** | Chain of WebFilters protecting requests |
| **ReactiveSecurityContextHolder** | SecurityContext backed by Reactor Context |

Comparing the two stacks:

| Servlet | WebFlux |
|---|---|
| HttpSecurity | ServerHttpSecurity |
| SecurityFilterChain | SecurityWebFilterChain |
| JwtDecoder | ReactiveJwtDecoder |
| NimbusJwtDecoder | NimbusReactiveJwtDecoder |
| HttpServletRequest | ServerWebExchange |
| Servlet Filter | WebFilter |
| Common thread-local security context | Reactor Context |

**Do not copy Servlet's `JwtDecoder`/`HttpSecurity` and call `block()` to use them in WebFlux.** In WebFlux, use reactive components and let the security pipeline authenticate the token before the controller is allowed to use claims.

`ReactiveJwtDecoder.decode(String)` returns **`Mono<Jwt>`**. If the token is validated, the `Mono` emits `Jwt`; otherwise, decoding/validation signals an error. A manually constructed `Jwt` object in a unit test does not prove the JWT signature was verified.

## 3. JWT, JWS, and Signature Verification Differ from Parsing JSON

A signed JWT access token typically uses **JWS Compact Serialization**:

    BASE64URL(Protected Header)
        .
    BASE64URL(Payload)
        .
    BASE64URL(Signature)

Example header:

    {
      "alg": "RS256",
      "typ": "at+jwt",
      "kid": "rsa-2026-11"
    }

Example payload:

    {
      "iss": "https://auth.example.com/realms/shop",
      "sub": "user-42",
      "aud": ["orders-api"],
      "scope": "orders.read orders.write",
      "client_id": "shop-web",
      "iat": 1794729600,
      "nbf": 1794729600,
      "exp": 1794731400
    }

These are illustrative values, not a real signed JWT. Three steps must remain separate:

- **Base64URL decoding** only decodes bytes to read the header/payload; it does not authenticate.
- **JWS signature verification** checks that the data was signed with a trusted key.
- **Claims validation** checks issuer, audience, expiration, token type, and other constraints.

An attacker can craft JSON claiming `sub=admin` and `scope=orders.admin` and Base64URL-encode it. If a custom filter reads those claims before verifying the signature, it can grant severely unauthorized access.

**JWS signs the payload; it does not encrypt the payload.** A token can carry readable personal data if leaked. JWE is a separate encryption mechanism; do not assume a JWS JWT decoder automatically handles every JWE or nested JWT.

## 4. Trusted Key Sources and JWKS

With asymmetric RSA/EC:

    Authorization Server:
      holds private signing key
      signs JWT access token
             |
             v
    OAuth Client:
      sends Bearer JWT to Resource Server
             |
             v
    WebFlux Resource Server:
      fetches public verification key from trusted source
      verifies JWS signature

A **JWKS (JSON Web Key Set)** is a set of JSON Web Keys published by the issuer, typically via an HTTPS endpoint. Abbreviated example:

    {
      "keys": [
        {
          "kty": "RSA",
          "kid": "rsa-2026-11",
          "use": "sig",
          "alg": "RS256",
          "n": "PUBLIC_MODULUS_BASE64URL",
          "e": "AQAB"
        }
      ]
    }

This is a hypothetical key and cannot be used for verification. Fields:

| Field | Meaning |
|---|---|
| **kty** | Key type, e.g., RSA, EC, OKP |
| **kid** | Key ID to select a key from the key set |
| **use** | Key purpose such as `sig`, if declared |
| **key_ops** | Permitted key operations, if present |
| **alg** | Corresponding algorithm, if present |
| **n, e** | RSA public key components |

A public JWKS must never contain private key components such as RSA `d`/`p`/`q`. For symmetric keys, the `k` field of an `oct` JWK is a secret and **must never be placed in a public JWKS**.

A signature that validates against an **attacker-supplied public key** does not prove the token is trustworthy. The Resource Server must obtain keys from a **configured and authorized issuer/JWKS**.

## 5. `alg`, `kid`, and Trust Policy

Header:

    {
      "alg": "RS256",
      "kid": "key-a"
    }

- **alg** states the JWS algorithm recorded in the token.
- **kid** helps select the matching public key inside a trusted JWKS.
- Both are token data; neither may alter trust policy on its own.

A flawed design:

    Read alg from token -> enable any algorithm automatically.
    Read kid from token -> construct URL to fetch public key.
    Read jku/x5u from token -> HTTP request to arbitrary host.
    Verify with that key -> trust user claims.

Proper design:

    Configured issuer allow-list
       -> trusted JWKS/key source
       -> allowed JWS algorithms
       -> select candidate key by kid/kty/alg
       -> verify signature
       -> validate iss/aud/exp/nbf/profile

### Algorithm Confusion

A historic vulnerability occurred when a verifier meant to use an RSA public key to verify RS256 instead accepted HS256 self-declared by the JWT, and used the RSA public key bytes as the HMAC secret. A weak implementation like this can have its MAC forged.

How to prevent it:

1. Allow only JWS algorithms agreed upon with the AS.
2. Check that the algorithm matches the key type.
3. Never switch algorithms based on the token.
4. Never accept unsigned `alg=none` as a signed access token.
5. Never use an RSA public key as a symmetric HMAC secret.

### `kid` Is Not a Global Identifier

Two issuers may both have a `kid` of `signing-2026`. Never use `kid` as an issuer ID or global key identifier. Look up keys by `kid` **within the JWKS of the right issuer**. When a `kid` cannot be found, it may be due to key rotation, a stale cache, a wrong JWKS URI, or a forged token; never fetch an arbitrary JWKS from a caller-supplied header.

## 6. Common JWS Algorithms

| Algorithm | Signing mechanism | Verification key | Notes |
|---|---|---|---|
| RS256 | RSA PKCS#1 v1.5 + SHA-256 | RSA public key | Common Spring Security default |
| RS512 | RSA + SHA-512 | RSA public key | Enable only when issuer uses it |
| PS256 | RSA-PSS + SHA-256 | RSA public key | Requires issuer/decoder support |
| ES256 | ECDSA + SHA-256 | EC P-256 public key | Do not use RSA key |
| ES384 | ECDSA + SHA-384 | EC P-384 public key | Must match curve |
| EdDSA | Edwards curve | OKP public key | Depends on version/provider |
| HS256 | HMAC + SHA-256 | Shared secret | Verifier holding secret can also sign |
| none | Unsigned | None | Unsuitable for signed Bearer JWTs |

Spring Security Reference notes that **`NimbusReactiveJwtDecoder` trusts and verifies RS256 by default** in standard JWT Resource Server setups. If the AS actually uses ES256 or RS512, add that algorithm only after confirming the contract, key family, and support.

Spring Boot configuration:

    spring:
      security:
        oauth2:
          resourceserver:
            jwt:
              issuer-uri: https://auth.example.com/realms/shop
              jws-algorithms:
                - RS256

Illustrative Java configuration:

    import org.springframework.context.annotation.Bean;
    import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
    import org.springframework.security.oauth2.jwt.JwtValidators;
    import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
    import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;

    @Bean
    ReactiveJwtDecoder jwtDecoder() {
        String issuer = "https://auth.example.com/realms/shop";

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder.withIssuerLocation(issuer)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        decoder.setJwtValidator(
                JwtValidators.createDefaultWithIssuer(issuer));

        return decoder;
    }

The code selects RS256 and a trusted issuer. If using HMAC, keep in mind that the secret must remain confidential and be distributed differently from an asymmetric public key.

## 7. Issuer: The `iss` Field Identifies Who Issued the Token

Issuer claim:

    {
      "iss": "https://auth.example.com/realms/shop"
    }

Spring Boot configuration:

    spring:
      security:
        oauth2:
          resourceserver:
            jwt:
              issuer-uri: https://auth.example.com/realms/shop

An AS may host multiple realms:

    https://auth.example.com/realms/shop
    https://auth.example.com/realms/admin
    https://auth.example.com/realms/partners

They may run the same IAM software, even on the same infrastructure, yet still have separate issuer identifiers and policies. A token issued by the `admin` realm is not automatically accepted by an API trusting only the `shop` realm.

### Exact Issuer Matching

    Expected:
      https://auth.example.com/realms/shop

    Received:
      https://auth.example.com/realms/shop/

Two URIs differing by a trailing slash are not treated as identical in issuer validation. Do not arbitrarily rewrite hostnames/paths/realms just to make a token pass. Align the AS/RS with the metadata contract.

**Both signature and issuer must be valid:**

- Correct `iss` with invalid signature: reject.
- Signature verifies against another key with wrong `iss`: reject.
- Valid signature/`iss` with wrong `aud`: reject.

Reading `iss` from an unverified JWT can only serve as a **routing hint** into a trusted issuer allowlist, not as authorization for the API to dynamically discover a new issuer.

## 8. Audience: Which API Was the Token Issued For?

Audience claim:

    {
      "aud": ["orders-api"]
    }

RFC 7519 allows `aud` as a string or an array of strings. Spring Security `Jwt` provides `getAudience()` to retrieve the audience list.

An access token with:

    {
      "iss": "https://auth.example.com/realms/shop",
      "sub": "user-42",
      "aud": ["billing-api"],
      "scope": "orders.read",
      "exp": 1794731400
    }

**must not be accepted at `orders-api`** if `orders-api` requires `aud` to contain `orders-api`. A scope named `orders.read` cannot replace audience validation.

A simple audience validator:

    jwt.getAudience().contains("orders-api")

### `client_id` Does Not Replace `aud`

- **aud** is the intended recipient/resource of the JWT.
- **client_id** is the OAuth Client to which the token was issued.
- **scope/scp** are the granted permission scopes.
- **sub** is the subject within the issuer's scope.

A token intended for `orders-api` issued to client `shop-web` can carry both `aud=orders-api` and `client_id=shop-web`; the two fields do not mean the same thing.

### Multi-Audience

    {
      "aud": ["orders-api", "inventory-api"]
    }

If the token profile allows multiple audiences, a `contains("orders-api")` validator will accept it. If the API requires a single audience, add an explicit check. Multi-audience tokens can widen where a Bearer token can be replayed, so review least privilege.

## 9. Spring Boot YAML: Issuer, Audience, Key Set

Spring Boot supports the `audiences` property for both Servlet and reactive Resource Servers in compatible versions.

    spring:
      security:
        oauth2:
          resourceserver:
            jwt:
              issuer-uri: https://auth.example.com/realms/shop
              audiences:
                - orders-api
              jws-algorithms:
                - RS256

You can declare the trusted JWKS URI directly:

    spring:
      security:
        oauth2:
          resourceserver:
            jwt:
              issuer-uri: https://auth.example.com/realms/shop
              jwk-set-uri: https://auth.example.com/realms/shop/jwks
              audiences:
                - orders-api
              jws-algorithms:
                - RS256

The JWKS URI in the example is a placeholder only. There is no single standardized JWKS path across all Authorization Servers.

**`issuer-uri` establishes trust identity**; **`jwk-set-uri` establishes the public key source**. When creating a decoder manually with only `jwk-set-uri`, keep an issuer validator. Do not assume `issuer-uri` in YAML automatically attaches to a custom `ReactiveJwtDecoder` bean that overrides auto-configuration.

## 10. `SecurityWebFilterChain` for a JWT Resource Server

    import org.springframework.context.annotation.Bean;
    import org.springframework.context.annotation.Configuration;
    import org.springframework.http.HttpMethod;
    import org.springframework.security.config.Customizer;
    import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
    import org.springframework.security.config.web.server.ServerHttpSecurity;
    import org.springframework.security.web.server.SecurityWebFilterChain;

    @Configuration
    @EnableWebFluxSecurity
    public class OrdersSecurity {

        @Bean
        SecurityWebFilterChain api(ServerHttpSecurity http) {
            return http
                    .authorizeExchange(auth -> auth
                            .pathMatchers("/api/public/**").permitAll()
                            .pathMatchers(HttpMethod.GET, "/api/orders/**")
                                .hasAuthority("SCOPE_orders.read")
                            .pathMatchers(HttpMethod.PUT, "/api/orders/**")
                                .hasAuthority("SCOPE_orders.write")
                            .anyExchange().authenticated())
                    .oauth2ResourceServer(oauth2 -> oauth2
                            .jwt(Customizer.withDefaults()))
                    .build();
        }
    }

The Resource Server performs:

1. Extracting the Bearer credential.
2. Verifying JWS and validating issuer/audience/temporal claims.
3. Creating the authenticated principal and authorities.
4. Checking scope/authority in WebFlux HTTP security.
5. Optionally checking tenant, ownership, resource state, and live permissions in the domain.

**`hasAuthority` does not verify the JWT itself.** It relies on the `Authentication` already verified by the Resource Server. A JWT with an invalid signature must never reach authorization as a trusted principal.

## 11. JWT Timestamps Use NumericDate

RFC 7519 defines:

| Claim | Meaning | Role |
|---|---|---|
| **exp** | Expiration Time | Reject tokens after expiration, subject to reasonable tolerance |
| **nbf** | Not Before | Token is not yet valid before this timestamp |
| **iat** | Issued At | Time the token was issued; can be used for custom freshness |
| **auth_time** | OIDC authentication time | Not the same as `iat` |
| **expires_in** | OAuth response field | Duration, not JWT `exp` |
| **jti** | JWT ID | Not a timestamp |

Example:

    {
      "iat": 1794729600,
      "nbf": 1794729600,
      "exp": 1794731400
    }

The span `exp - iat` is **1,800 seconds = 30 minutes**.

JWT NumericDate is **seconds since Unix epoch**, not milliseconds:

    JWT seconds:     1794729600
    Milliseconds:    1794729600000

An AS writing milliseconds into `exp` as seconds produces tokens that appear valid for far too long. Fix the token producer rather than relaxing the verifier to accept absurd timestamps.

## 12. `exp`: Expiration and Practical Acceptance Window

    Resource Server UTC: 10:31:00
    JWT exp:             10:30:00

The JWT is past its expiration time. `JwtTimestampValidator` normally checks `exp`, with **clock skew tolerance** to handle clock drift.

An unexpired access token may still carry old roles:

    09:00 AS issues token scope=orders.write, exp=09:20
    09:05 Admin revokes write
    09:06 Old JWT still contains scope=orders.write

If the API relies solely on JWT scopes, the old permission can still be exercised until the token expires. `exp` is not a live current-entitlement lookup. If near-instant revocation is required, use token revocation/denylists, versioning, short TTLs, or live domain authorization.

### Missing `exp`

Do not assume **every `JwtTimestampValidator` version requires `exp` to be present by default**. Spring Security 7.x provides APIs controlling whether missing `exp` and `nbf` are allowed, and the default may permit missing fields. If your API's token profile requires `exp`:

    Condition 1: exp must be present.
    Condition 2: exp must not be expired per temporal validator.

Include an explicit required-`exp` validator instead of relying on an assumption about default behavior.

## 13. `nbf`: Time When Validity Begins

Example:

    {
      "iat": 1794729600,
      "nbf": 1794730200,
      "exp": 1794731400
    }

A token can be issued earlier but only usable after `nbf`.

    iat = 09:00
    nbf = 09:10
    exp = 09:30

Do not force `iat=nbf`. If `now` is before `nbf`, the JWT must be rejected under temporal policy, aside from permitted clock skew.

`nbf` is optional under the general JWT specification, though a specific profile may require it. If the API mandates `nbf`, include a validator checking that the claim exists.

## 14. `iat` Does Not Replace `exp` or Max-Age

`iat` indicates when the JWT was issued.

    iat = 09:00
    exp = 09:30
    now = 09:25

The token is still unexpired, yet it is 25 minutes old. If the API wants a 10-minute `maxAge`, add a custom policy. **`JwtTimestampValidator` does not automatically enforce max token age simply because the JWT contains `iat`.**

A token with:

    now = 10:00
    iat = 11:00

may indicate an inaccurate issuer clock or an invalid token profile. If the API wants to block `iat` too far in the future, add a validator such as `iat <= now + futureLeeway`.

In OIDC, **`auth_time`** indicates when the user authenticated at the OP; **`iat`** indicates when the token was issued. A refresh token flow can mint a new access token with a fresh `iat` even though the user did not just log in.

## 15. Clock Skew: Why Can a Newly Issued Token Return 401?

    Authorization Server UTC: 10:00:00
    Resource Server UTC:     09:59:53
    Skew:                    7 seconds

If `nbf=10:00:00`, a Resource Server receiving the token immediately may see `nbf` in the future. `JwtTimestampValidator` uses **clock skew tolerance**. Spring Security documentation describes a default leeway of **60 seconds** in the referenced versions.

Approximate logic:

    nbf validity: now + skew >= nbf
    exp validity: now - skew < exp

Clock skew widens the acceptance window, not just for newly issued tokens. If skew is too large, tokens can be accepted long after `exp` or long before `nbf`.

Recommendations:

- Synchronize NTP/chrony.
- Use UTC consistently.
- Choose a small skew based on measurement.
- Monitor clock drift per instance.
- Never use skew to mask a wrong NumericDate unit.
- Account for skew in token lifetime/revocation SLAs.

## 16. Complete Custom `NimbusReactiveJwtDecoder` Configuration

When explicit audience and required `exp` are needed:

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

    @Configuration
    public class OrdersJwtValidationConfig {

        private static final String ISSUER =
                "https://auth.example.com/realms/shop";
        private static final String AUDIENCE = "orders-api";

        @Bean
        ReactiveJwtDecoder reactiveJwtDecoder() {
            NimbusReactiveJwtDecoder decoder =
                    NimbusReactiveJwtDecoder.withIssuerLocation(ISSUER)
                            .jwsAlgorithm(SignatureAlgorithm.RS256)
                            .build();

            OAuth2TokenValidator<Jwt> defaults =
                    JwtValidators.createDefaultWithIssuer(ISSUER);

            OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                    jwt.getAudience().contains(AUDIENCE)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required audience missing",
                                        null));

            OAuth2TokenValidator<Jwt> requiredExp = jwt ->
                    jwt.getExpiresAt() != null
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required exp missing",
                                        null));

            decoder.setJwtValidator(
                    new DelegatingOAuth2TokenValidator<>(
                            defaults,
                            audienceValidator,
                            requiredExp));

            return decoder;
        }
    }

Key points:

1. **`withIssuerLocation`** uses the trusted issuer to retrieve metadata/JWKS.
2. **`jwsAlgorithm(RS256)`** restricts the allowed signature algorithm.
3. **`JwtValidators.createDefaultWithIssuer`** retains issuer/time defaults per version.
4. **`audienceValidator`** requires `aud` to contain `orders-api`.
5. **`requiredExp`** requires the `exp` claim to be present per token contract.
6. **`DelegatingOAuth2TokenValidator`** combines the conditions.
7. **`setJwtValidator` replaces any validators previously attached to the decoder**, so keep all required checks.

This code illustrates a single issuer/RS256/audience setup. If the AS uses RFC 9068 or a custom profile, add the appropriate token-purpose and required-claim validation.

## 17. Customizing `JwtTimestampValidator` and Clock Skew

You can use:

    import java.time.Duration;
    import org.springframework.security.oauth2.jwt.JwtTimestampValidator;

    JwtTimestampValidator timestamp =
            new JwtTimestampValidator(Duration.ofSeconds(30));

Combine with other validators:

    import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
    import org.springframework.security.oauth2.jwt.JwtIssuerValidator;

    decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                    timestamp,
                    new JwtIssuerValidator(ISSUER),
                    audienceValidator,
                    requiredExpiration));

Variables `decoder`, `audienceValidator`, and `requiredExpiration` are assumed to be defined in the same method; this fragment illustrates composition.

**Do not call `setJwtValidator` twice expecting the second call to merely append a validator.** The second call replaces the previous composition. Retain issuer, audience, timestamp, required claims, and token purpose.

Spring Security 7.x adds setters to allow/disallow missing `exp` or `nbf`; do not copy 7.x methods into 6.x if the API does not exist there.

## 18. Custom `iat` Max-Age Validator

If the contract requires access tokens to be no older than 10 minutes, you can add:

    import java.time.Clock;
    import java.time.Duration;
    import java.time.Instant;
    import org.springframework.security.oauth2.core.OAuth2Error;
    import org.springframework.security.oauth2.core.OAuth2TokenValidator;
    import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
    import org.springframework.security.oauth2.jwt.Jwt;

    public final class TokenAgeValidator
            implements OAuth2TokenValidator<Jwt> {

        private final Duration maxAge;
        private final Duration futureLeeway;
        private final Clock clock;

        public TokenAgeValidator(
                Duration maxAge, Duration futureLeeway, Clock clock) {
            this.maxAge = maxAge;
            this.futureLeeway = futureLeeway;
            this.clock = clock;
        }

        @Override
        public OAuth2TokenValidatorResult validate(Jwt jwt) {
            Instant iat = jwt.getIssuedAt();

            if (iat == null) {
                return reject("iat is required");
            }

            Instant now = clock.instant();

            if (iat.isAfter(now.plus(futureLeeway))) {
                return reject("iat is too far in the future");
            }

            if (iat.isBefore(now.minus(maxAge))) {
                return reject("token exceeds permitted max age");
            }

            return OAuth2TokenValidatorResult.success();
        }

        private OAuth2TokenValidatorResult reject(String reason) {
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error("invalid_token", reason, null));
        }
    }

Instantiate:

    OAuth2TokenValidator<Jwt> maxAge =
            new TokenAgeValidator(
                    Duration.ofMinutes(10),
                    Duration.ofSeconds(30),
                    Clock.systemUTC());

Combine it with issuer, audience, and `exp`/`nbf` validators. **Max age is an optional policy**, not built into the general JWT specification. If the AS intentionally issues 30-minute tokens while the API enforces 10 minutes, the client/AS and Resource Server must align.

## 19. OIDC ID Tokens Are Not JWT Access Tokens

An ID token:

    {
      "iss": "https://auth.example.com/realms/shop",
      "sub": "user-42",
      "aud": "shop-web-client",
      "iat": 1794729600,
      "exp": 1794730200
    }

An access token for `orders-api`:

    {
      "iss": "https://auth.example.com/realms/shop",
      "sub": "user-42",
      "aud": ["orders-api"],
      "scope": "orders.read",
      "iat": 1794729600,
      "exp": 1794731400
    }

Both tokens can share the same issuer/JWKS while having **different audiences/purposes**.

- ID tokens are for the OIDC Client/Relying Party.
- Access tokens are for the Resource Server.
- Refresh tokens, JWT client assertions, or logout tokens have distinct purposes.
- Never treat every JWT with a valid signature as an API access token.

If the AS issues the **RFC 9068 JWT Access Token Profile**, the Resource Server may need to validate `typ=at+jwt` and profile-required claims. Spring Security supports profile validators such as `JwtValidators.createAtJwtValidator()` in compatible versions. Configuring JOSE type validation may need coordination with the builder's `validateTypes(false)`. Do not enforce RFC 9068 on an issuer using a different token profile without agreement.

## 20. Discovery, `jwk-set-uri`, and Key Rotation

With `issuer-uri`, Spring Security can use OIDC Provider Configuration or OAuth Authorization Server Metadata to locate `jwks_uri`. Abbreviated metadata:

    {
      "issuer": "https://auth.example.com/realms/shop",
      "jwks_uri": "https://auth.example.com/realms/shop/jwks"
    }

If `jwk-set-uri` is declared directly, the Resource Server can avoid metadata discovery dependencies at some initialization stages, though it still needs to fetch trusted public keys.

Spring Boot/Spring Security supports **lazy decoder initialization**, such as `SupplierReactiveJwtDecoder` in matching configurations. Custom decoder beans created via `withIssuerLocation` may access metadata at a different time. Do not assert that every configuration blocks on the AS at startup or that every configuration is lazy.

### Rotation Timeline

    T0: AS signs JWTs with key kid=old.
    T1: AS publishes JWKS containing old and new.
    T2: AS begins signing JWTs with kid=new.
    T3: RS refreshes trusted JWKS as needed.
    T4: Old tokens expire; AS may remove old from JWKS.

Overlap reduces errors caused by unrefreshed JWKS caches. When a `kid=new` token is rejected:

- Check issuer, `jwks_uri`, and HTTPS trust.
- Check `kid`/`kty`/`alg` compatibility.
- Check JWKS cache/refresh.
- Check whether the AS published the new key before signing new tokens.
- Never disable signature verification to fix an error.

**A JWKS timeout does not prove a token is expired.** When no matching trusted key is available, fail closed while accurately recording the dependency/trust error in metrics.

## 21. Multi-Issuer: Unverified Issuer May Only Serve as a Routing Hint

An API may accept:

    Issuer A: https://auth.example.com/realms/shop
    Issuer B: https://auth.example.com/realms/partners
    Issuer C: https://login.partner.net/

Each issuer has its own JWKS and validators:

    Incoming JWT
         |
         v
    Read iss as untrusted routing hint
         |
         v
    Trusted issuer allow-list
         |
         +-- A -> decoder/JWKS A
         +-- B -> decoder/JWKS B
         +-- C -> decoder/JWKS C
         |
         v
    Verify signature + exact issuer
         |
         v
    Validate audience + time + token purpose

Never use `iss` from an unverified JWT to dynamically fetch JWKS for an arbitrary issuer, as this risks SSRF or attacker-controlled trust domains. In WebFlux, use a reactive authentication-manager resolver with a trusted-issuer strategy; do not copy Servlet's `HttpServletRequest`-based resolver.

Two issuers may both share `sub=123` or `kid=signing-key` while remaining two distinct users/two key namespaces. When mapping local identity, typically use **`(issuer, subject)`**, not `sub` alone.

## 22. 401/403 Errors in a JWT Resource Server

| Scenario | Processing layer | Typical HTTP response |
|---|---|---|
| Missing Bearer token on protected endpoint | Authentication required | 401 |
| Invalid JWT signature | ReactiveJwtDecoder | 401 invalid_token |
| Disallowed JWS algorithm | Signature policy | 401 invalid_token |
| Wrong `iss` | Issuer validator | 401 invalid_token |
| Wrong `aud` | Audience validator | 401 invalid_token |
| `exp` passed | Timestamp validator | 401 invalid_token |
| `nbf` not yet reached | Timestamp validator | 401 invalid_token |
| `iat` violates custom max-age | Custom validator | 401 invalid_token |
| ID token used as access token | Token-purpose check | 401 invalid_token |
| Valid token lacking `orders.write` | Authorization | 403 insufficient_scope when applicable |
| Valid token, wrong tenant/ownership | Domain authorization | 403 or domain-specific denial |
| JWKS fetch timeout | Dependency/trust | Fail closed, do not conclude token expired |

Example:

    HTTP/1.1 401 Unauthorized
    WWW-Authenticate: Bearer error="invalid_token"

And:

    HTTP/1.1 403 Forbidden
    WWW-Authenticate: Bearer error="insufficient_scope"

Never return raw tokens, private keys, stack traces, or sensitive authorization details in error responses.

## 23. Test Matrix for Signature, Issuer, `aud`, and Timestamps

These scenarios are **test case designs**, not observed test run results.

| Input | Expectation |
|---|---|
| JWT signed with trusted RS256 key, valid `iss`/`aud`/time | Authentication succeeds if profile passes |
| Payload modified after signing | Signature rejection |
| JWT signed with key from unknown issuer | Reject |
| `alg=none` | Reject |
| `alg=HS256` on RS256-only decoder | Reject |
| `kid` absent from trusted JWKS | Reject or trusted refresh; never trust unknown key |
| Issuer from different realm | Reject |
| Issuer differing by trailing slash | Reject on exact issuer mismatch |
| `aud=billing-api` | Reject at `orders-api` |
| `aud` array contains `orders-api` | Can pass audience check if profile allows |
| Missing `aud` when audience is required | Reject |
| `exp` expired beyond skew | Reject |
| `nbf` in future beyond skew | Reject |
| `exp` recently passed within leeway | Per clock skew policy |
| `iat` in the future | Reject when future-iat policy is enabled |
| `iat` too old | Reject when max-age policy is enabled |
| `exp` missing | Reject when profile mandates required-exp |
| Valid signature and claims, missing scope | Authenticated, authorization may return 403 |
| ID token used as API credential | Reject per token purpose/`aud` |
| Stale JWKS cache after rotation | Fail closed, investigate key refresh |
| RS replica clock skew | Temporal errors may be inconsistent |

**Unit tests of validators** only verify predicates on a `Jwt` object; they do not prove signatures are verified. **`ReactiveJwtDecoder` integration tests** require signed tokens and trusted test keys. **`WebTestClient` security integration tests** test requests passing through the WebFlux `SecurityWebFilterChain` and resulting HTTP 401/403 and `WWW-Authenticate`. Spring Security Test `mockJwt()` creates a mock Authentication suitable for testing authorization, but it does not replace cryptographic verification tests.

## 24. Diagnosing a JWT 401

An investigation flow:

    [1] Was Authorization: Bearer sent?
     |
     v
    [2] Did the Bearer converter extract the credential?
     |
     v
    [3] Is the JWT compact format valid?
     |
     v
    [4] Is JWS alg in the allow-list?
     |
     v
    [5] Does the trusted JWKS have a key compatible with kid/alg?
     |
     v
    [6] Does the signature verify?
     |
     v
    [7] Exact match on iss?
     |
     v
    [8] Does aud contain the Resource Server?
     |
     v
    [9] Are exp/nbf valid within skew?
     |
     v
    [10] Are token purpose/required claims valid?
     |
     v
    [11] Does optional iat freshness policy pass?
     |
     v
    [12] Are scope/domain authorizations sufficient?

The decoder's actual internal order may differ from the diagram; this is a diagnostic checklist, not an executable test.

| Symptom | Likely cause |
|---|---|
| All tokens return 401 after deploy | Wrong `issuer-uri`/`jwk-set-uri`/`alg`, custom decoder override |
| Old tokens pass, new tokens return 401 | Key rotation, `kid`, JWKS cache |
| JWT has right scope yet returns 401 | Signature/`iss`/`aud`/time/purpose failed |
| Newly issued JWT has future `nbf` | Clock skew or wrong issuer clock |
| `exp` not expired yet still returns 401 | Wrong `iss`/`aud`/`alg`/`nbf` or `maxAge` policy |
| Missing `exp` still passes | Required-`exp` validator missing |
| Future `iat` still passes | Future-`iat` rule not configured |
| JWT authenticated yet returns 403 | `SCOPE_` mapping or domain policy |
| Only one RS instance fails | Clock/config drift or JWKS cache |
| JWKS TLS/timeout error | Truststore, hostname, AS availability |
| ID token accepted as access token | Missing token-purpose/audience policy |

### Safe Logging

Record request ID, issuer configuration ID, error type (`signature`/`issuer`/`audience`/`expired`/`not_before`), JWKS fetch status, and latency. Never log raw access tokens, `Authorization` headers, private keys, or full payloads containing PII. Prior to verification, `kid` and `iss` are untrusted data; do not use raw values as unbounded metric labels.

## 25. Anti-Patterns to Avoid

| Anti-pattern | Risk | Solution |
|---|---|---|
| Decode Base64URL only | Signature unverified | `ReactiveJwtDecoder` |
| Compare `iss` only | Attacker self-declares issuer | Verify JWS with trusted key |
| Verify signature only | Wrong-issuer/audience tokens slip through | Claim validators |
| Use `scope` instead of `aud` | Cross-API token substitution | Require audience |
| Trust `alg` chosen by the JWT | Algorithm confusion | Allowed algorithms |
| Accept `alg=none` | Unsigned token | Require signed JWT |
| `kid` points to a JWKS URL | SSRF/key substitution | Trusted JWKS URI |
| Omit required `exp` | Credentials may live indefinitely | Required-`exp` validator |
| Use `iat` instead of `exp` | Wrong semantics | `exp`/`nbf` and optional max-age |
| Huge clock skew | Weakens token validity window | NTP, bounded skew |
| Accept OIDC ID token as access token | Cross-JWT confusion | Profile and audience |
| Use Servlet `JwtDecoder` and `block()` | Breaks reactive architecture | `ReactiveJwtDecoder` |
| Custom `WebFilter` fabricating authenticated JWT | Can bypass security | Standard Resource Server |
| `setJwtValidator` with `aud` only | Drops issuer/time checks | Delegating validators |
| Allow token through on JWKS timeout | Fail open | Fail closed |
| Mock JWT test treated as crypto verification | Decoder may not even run | Signed JWT integration tests |
| Log raw Bearer JWT | Credential leakage | Sanitized telemetry |

## 26. Summary

    JWT access token
         |
         v
    ReactiveJwtDecoder
         |
         +-- Trusted signature key + allowed JWS alg
         |
         +-- Exact issuer match
         |
         +-- Audience intended for this API
         |
         +-- exp/nbf validity, bounded clock skew
         |
         +-- Required token purpose/claims
         |
         +-- Optional iat freshness policy
         |
         v
    Authenticated principal
         |
         v
    Scope / authorities / domain authorization
         |
         v
    Protected business operation

Key principles:

1. **Verify signatures using trusted keys and algorithms**, not just reading the payload.
2. **`iss` matches an issuer trusted by the Resource Server**; never dynamically load arbitrary issuers/JWKS from an unverified token.
3. **`aud` must target the current API**; `client_id` and `scope` do not replace `aud`.
4. **`exp`/`nbf` define the validity window**; clock skew is only for small clock drift tolerance.
5. **`iat` is not automatically expiration or max-age**; optional `iat` policies must be explicitly defined.
6. **Token purpose and required claims** must match the issuer's access-token profile.
7. **Custom validators must be composed completely**, especially when calling `setJwtValidator`.
8. **Use `ReactiveJwtDecoder` and `SecurityWebFilterChain` in WebFlux**, avoiding parallel custom JWT filters.
9. **An OIDC ID token is not an API access token**, even with the same issuer/signing key.
10. **A valid token is not enough for a business action**; scope, tenant, and domain permissions must be checked after authentication.

**Conclusion:** A JWT is accepted by a Spring Security WebFlux Resource Server only when its JWS signature, issuer, audience, temporal window, and token profile all satisfy the trust contract. `ReactiveJwtDecoder` is responsible for token acceptance; WebFlux authorization and domain policy decide subsequent actions.

## 27. References

- **Spring Security — Reactive OAuth 2.0 Resource Server JWT:** signature, issuer, JWKS, audience, timestamps, and `ReactiveJwtDecoder`. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security — Reactive Resource Server:** WebFlux Bearer architecture. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/index.html
- **Spring Security API — NimbusReactiveJwtDecoder:** `withIssuerLocation`, `withJwkSetUri`, `setJwtValidator`. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- **Spring Security API — JwtTimestampValidator:** `exp`/`nbf` and clock skew. https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/JwtTimestampValidator.html
- **Spring Boot — Resource Server:** `issuer-uri`, `audiences`, and `jwk-set-uri` for WebFlux/Servlet. https://docs.spring.io/spring-boot/reference/security/oauth2.html
- **Spring Security — WebFlux Security:** `ServerHttpSecurity`/`SecurityWebFilterChain`. https://docs.spring.io/spring-security/reference/reactive/configuration/webflux.html
- **Spring Security — Reactive JWT 6.5:** API reference for 6.x versions. https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- **RFC 7519 — JWT:** `iss`, `aud`, `exp`, `nbf`, `iat`, and NumericDate. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7515 — JWS:** signatures, protected headers. https://www.rfc-editor.org/rfc/rfc7515
- **RFC 7517 — JWK:** JSON Web Keys and JWKS. https://www.rfc-editor.org/rfc/rfc7517
- **RFC 7518 — JWA:** algorithms and key compatibility. https://www.rfc-editor.org/rfc/rfc7518
- **RFC 8725 — JWT Best Current Practices:** algorithms, issuer, audience, token confusion. https://www.rfc-editor.org/rfc/rfc8725
- **RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens:** access token purpose and required claims. https://www.rfc-editor.org/rfc/rfc9068
- **OpenID Connect Core:** ID tokens, `aud`, and `auth_time`. https://openid.net/specs/openid-connect-core-1_0.html
