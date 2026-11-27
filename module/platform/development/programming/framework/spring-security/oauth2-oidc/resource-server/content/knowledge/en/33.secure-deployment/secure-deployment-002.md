# Trusted Lists of Issuers, Audiences, Algorithms, and Key Sources

## 1. Trust Boundary of a Resource Server

A Spring Security OAuth 2.0 Resource Server should only accept access tokens issued by a configured trusted Authorization Server, intended for the right API, and signed with a key and algorithm within the system's policy.

A JWT with a valid signature can still be unsuitable for the current API. A token may be signed by a valid issuer but intended for `billing-api`; it may have the right audience but an untrusted issuer; or it may have both the right issuer and audience yet use an algorithm the system disallows. Therefore, verifying the signature is only one part of the authentication decision.

Four lists must be explicitly managed:

- **Issuer allowlist:** the Authorization Servers permitted to issue tokens for the system.
- **Audience allowlist:** the resource identifiers permitted to receive tokens on this API.
- **Algorithm allowlist:** the signature algorithms accepted to verify access tokens.
- **Trusted key sources:** the endpoints or key stores permitted to provide public keys for signature verification.

These lists form the trust policy. They must be configured from a trusted administrative source, reviewed, and changed through a formal process. Never let a token choose its own issuer, audience, algorithm, or key-loading URL and turn those values into trust anchors.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the role of issuer and audience in access-token validation.
2. Build explicit issuer/audience allowlists for a Resource Server.
3. Restrict signature algorithms by policy.
4. Select JWKS URIs and metadata endpoints from trusted configuration sources.
5. Distinguish Authorization Server public signing keys from client-sent JWKs in DPoP proofs.
6. Manage key rotation, unknown `kid`s, and cache refreshes.
7. Handle multiple issuers without creating arbitrary discovery mechanisms from tokens.
8. Validate opaque token introspection according to its trust boundary.
9. Write negative tests for issuer, audience, algorithm, and key source.
10. Track trust policy changes without leaking credentials or private keys.

---

## 2. Issuer: Determining Who Is Allowed to Issue Tokens

### 2.1. The `iss` Claim Identifies the Authorization Server

A JWT access token typically has an `iss` claim:

~~~json
{
  "iss": "https://id.example.com/realms/shop",
  "sub": "user-417",
  "aud": ["orders-api"],
  "exp": 1893456000
}
~~~

The Resource Server must verify that the `iss` value matches the configured issuer. Comparison must match the exact issuer value published and signed in the token by the Authorization Server.

For example, the following values should not be treated as equivalent if the policy declares only one issuer:

~~~text
https://id.example.com/realms/shop
https://id.example.com/realms/shop/
http://id.example.com/realms/shop
https://id.example.com/other-realm
~~~

Do not strip slashes, change schemes, change hosts, or normalize paths heuristically to make a token "match". If the Authorization Server changes its issuer URI, that is a trust configuration change that must be rolled out intentionally.

### 2.2. Issuer Is Not Subject

Issuer answers "who issued the token?". Subject answers "who is the token about?".

- `iss` usually identifies the Authorization Server.
- `sub` usually identifies the user, service account, or principal.
- `aud` identifies the resource server or group of resources receiving the token.

Do not use `sub` to decide which system issued the token. Nor use a familiar-looking user ID to skip issuer validation.

### 2.3. Configuring a Single Trusted Issuer

With Spring Boot, configuring an issuer URI is usually the simplest option:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/shop
~~~

Spring Security uses the issuer to locate metadata/JWK endpoints via supported discovery mechanisms, creates the decoder, and validates the issuer along with default time conditions.

Configuring an issuer URI does not mean the Resource Server accepts any issuer. It is a specific issuer declared by the application.

If the application needs explicit control over the JWKS endpoint, you can configure the key endpoint directly. When using a JWK Set URI directly, you must still configure an issuer validator; knowing the JWKS URL does not by itself prove the token has a valid issuer.

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/shop
          jwk-set-uri: https://id.example.com/realms/shop/protocol/openid-connect/certs
~~~

In some configurations, declaring both lets the application know both the expected issuer and the specific JWK Set endpoint. Check the behavior of your Spring Boot/Spring Security version and verify that the decoder actually has an issuer validator.

### 2.4. When Is a Custom `JwtDecoder` Needed?

A custom decoder may be needed when the application must:

- Enforce an API-specific audience.
- Allow only a specific set of algorithms.
- Use an independently managed JWKS endpoint.
- Combine default validators with additional policies.
- Apply clock skew per operational requirements.
- Use multiple decoders for multiple issuers.

When declaring your own `JwtDecoder` bean, take full responsibility for configuring all validators. Do not assume that every prior Spring Boot property is automatically applied to a custom bean.

---

## 3. Audience: The Token Must Be Intended for the Right API

### 3.1. Why Verifying Only the Issuer Is Not Enough

An Authorization Server may issue tokens for multiple resources:

~~~text
Issuer:
  https://id.example.com/realms/shop

Token A:
  aud = orders-api

Token B:
  aud = billing-api

Token C:
  aud = inventory-api
~~~

All three tokens may be signed by the same issuer. However, the Orders API should only accept tokens whose audience includes `orders-api`.

If only issuer and signature are checked, a token intended for the Billing API could be misused at the Orders API. This is a resource-separation flaw and can enable token substitution across APIs.

### 3.2. Audience Can Be a String or a List

In a JWT, `aud` can be represented as a single value or an array. Spring Security's API returns the audience as a list for the application to inspect.

Example:

~~~json
{
  "aud": "orders-api"
}
~~~

Or:

~~~json
{
  "aud": ["orders-api", "mobile-client"]
}
~~~

If the API requires `orders-api`, the second token may be valid because the audience contains that resource identifier. Exact policy depends on the architecture; what matters is comparing against the exact identifier chosen by the API.

Do not use substring matching, wildcards, or checking "`aud` is non-empty" instead of an allowlist.

### 3.3. Writing an Audience Validator

Example validator for the Orders API:

~~~java
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;

static OAuth2TokenValidator<Jwt> audienceValidator(
        String requiredAudience) {

    return jwt -> {
        if (jwt.getAudience().contains(requiredAudience)) {
            return OAuth2TokenValidatorResult.success();
        }

        OAuth2Error error = new OAuth2Error(
            "invalid_token",
            "Required audience is missing",
            null
        );

        return OAuth2TokenValidatorResult.failure(error);
    };
}
~~~

The validator only accepts tokens with the exact resource identifier. When the audience does not match, the decoder rejects the token before creating an `Authentication`.

### 3.4. Combining Issuer, Audience, and Timestamps

~~~java
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;

static OAuth2TokenValidator<Jwt> accessTokenValidator(
        String issuer,
        String audience) {

    OAuth2TokenValidator<Jwt> defaults =
        JwtValidators.createDefaultWithIssuer(issuer);

    return new DelegatingOAuth2TokenValidator<>(
        defaults,
        audienceValidator(audience)
    );
}
~~~

The default validator with issuer checks the issuer and Spring Security's default timestamp conditions. The audience validator adds the resource check.

For access tokens, you must also confirm the token profile/purpose matches the API. If the Authorization Server issues both ID tokens and access tokens as JWTs, do not rely solely on both having valid signatures. Issuer, audience, and token profile configuration must distinguish API access tokens from tokens used for OIDC client authentication.

### 3.5. Do Not Use `client_id` Instead of Audience

`client_id` identifies the OAuth client that requested the token. Audience identifies the resource receiving the token. They serve different roles.

Example:

~~~text
client_id = shop-mobile
aud       = orders-api
scope     = orders.read
~~~

The `shop-mobile` client can call the Orders API with the `orders.read` scope. The API should check its own audience and the required scope. Having the right `client_id` does not mean the token was issued for this resource.

---

## 4. Signature Algorithms: The Allowlist Must Be Explicitly Configured

### 4.1. The `alg` Header Is Untrusted Input

A JWT has a JOSE header:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-01",
  "typ": "JWT"
}
~~~

The `alg` value is sent with the token. Before the signature is verified, this header is untrusted input. The Resource Server must not read `alg` and accept whatever algorithm the token requests.

Common mistakes:

- Accepting the `none` algorithm.
- Allowing both symmetric and asymmetric algorithms without a policy.
- Using the same key in two different ways and causing algorithm confusion.
- Not restricting algorithms in the decoder.
- Treating the algorithm recorded in the JWK as sufficient to define policy.
- Allowing tokens to use weaker algorithms simply because the library supports them.

### 4.2. Using Asymmetric Signatures for Distributed Resource Servers

With asymmetric signatures:

- The Authorization Server holds the private signing key.
- Resource Servers only need the public verification key.
- Exposing the public key does not allow creating new signatures.
- Multiple Resource Servers can verify tokens without sharing the private signing key.

Common algorithm families:

| Family | Examples | Characteristics |
|---|---|---|
| RSA PKCS#1 v1.5 | RS256, RS384, RS512 | Common, broad compatibility |
| RSA-PSS | PS256, PS384, PS512 | More modern padding, check compatibility |
| ECDSA | ES256, ES384, ES512 | Elliptic curve–based signatures |
| HMAC | HS256, HS384, HS512 | Uses a shared secret; verifiers also hold the signing secret |

In multi-Resource-Server architectures, asymmetric signatures are usually preferable because each Resource Server only needs the public key. With HMAC, every component holding the verification secret is capable of signing valid tokens. Evaluate the secret-sharing risk before choosing.

### 4.3. Configuring a Single Allowed Algorithm

Example using RS256:

~~~java
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(
            "https://id.example.com/realms/shop/protocol/openid-connect/certs"
        )
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    decoder.setJwtValidator(
        accessTokenValidator(
            "https://id.example.com/realms/shop",
            "orders-api"
        )
    );

    return decoder;
}
~~~

The decoder only accepts the declared algorithm. The issuer/audience validator continues validating token contents after signature verification.

This is an illustrative example for a single issuer and audience. Align the algorithm with the Authorization Server's signing configuration. If the AS rotates keys while keeping the algorithm, the Resource Server can pick up the new key from the same JWKS endpoint without widening the allowlist.

### 4.4. When Multiple Algorithms Are Needed

Only allow multiple algorithms when there is a clear compatibility or migration reason. For example, during a transition period, the AS might sign with RS256 or ES256:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(JWKS_URI)
            .jwsAlgorithms(algorithms -> {
                algorithms.add(SignatureAlgorithm.RS256);
                algorithms.add(SignatureAlgorithm.ES256);
            })
            .build();

    decoder.setJwtValidator(
        accessTokenValidator(ISSUER, AUDIENCE)
    );

    return decoder;
}
~~~

The list must be declared explicitly in code/config. Do not build the allowlist dynamically from the `alg` value sent in the token. After migration, remove the old algorithm on schedule and confirm no valid tokens still depend on it.

If the Spring Security builder/version you use does not have the exact method above, check the Javadoc of the resolved artifact and use the corresponding API. Do not fall back to an unrestricted default decoder just to make the example compile.

### 4.5. Algorithm and Key Type Must Be Compatible

An allowed algorithm still requires a compatible key:

- RS256 requires an appropriate RSA public key.
- ES256 requires an EC key on the appropriate curve.
- If a JWK declares an `alg` field, it must match the intended use.
- The key must have the right verify/signing purpose per metadata and policy.
- Keys must not contain private material where only a public verification key is needed.

Do not use an arbitrary JWK just because it can be parsed. Check algorithm, key type, curve/key size, `use`, and key operations according to organizational and library policy.

---

## 5. Trusted Key Source: Where to Obtain Public Keys

### 5.1. JWKS URI Is a Trust Decision

A Resource Server typically fetches public keys from a JWKS endpoint. Example:

~~~text
Issuer:
https://id.example.com/realms/shop

JWKS:
https://id.example.com/realms/shop/protocol/openid-connect/certs
~~~

The Resource Server must trust both relationships:

1. The configured issuer is an accepted Authorization Server.
2. The JWKS endpoint is the authorized key source representing that issuer.

Do not pick a JWKS endpoint by taking an arbitrary URL from the token. If a token contains `jku` or `x5u`, do not automatically fetch keys from that URL to verify an access token. Doing so lets the token sender influence the public key source the server uses to authenticate that very token.

### 5.2. Static JWKS URI vs. Issuer Discovery

There are two common configuration approaches.

**Issuer discovery:** the application configures the issuer URI, then locates metadata and `jwks_uri` via a supported discovery protocol.

Advantages:

- Compact configuration.
- Metadata binds the issuer to the key endpoint.
- Easy to operate following standard OIDC/OAuth Authorization Server metadata.

Points to control:

- Metadata must be fetched from a trusted issuer.
- HTTPS and TLS certificates must be verified.
- The issuer in metadata must match the expected issuer.
- Do not let a token introduce a new issuer for the application to discover arbitrarily.

**Static JWKS URI:** the application configures the key endpoint directly.

Advantages:

- Explicit endpoint in deployment configuration.
- Can decouple metadata discovery from the startup path.
- Useful when environments have separately managed endpoints.

Points to control:

- Must still validate the issuer in the token.
- The JWKS URI must belong to reviewed trust configuration.
- Endpoint configurations across dev/staging/prod must be managed.
- Do not let an uncontrolled environment variable override a production endpoint.

### 5.3. HTTPS and TLS Certificate Validation

JWKS is the source of public keys. If an attacker can alter the JWKS response in transit or hijack DNS/the endpoint, they can inject a public key they control and sign forged tokens.

Therefore:

- Use HTTPS for metadata and JWKS endpoints.
- Keep TLS certificate validation enabled.
- Manage trust stores/certificate authorities according to policy.
- Never disable hostname verification in production.
- Never accept all certificates just to bypass environment errors.
- Protect DNS, ingress, service accounts, and endpoint configuration.
- Monitor certificate and endpoint changes.

Public keys may be public, but the authenticity of the source providing the public key is a critical security property.

### 5.4. Do Not Take Keys from Token Headers

For JWT access tokens, a Resource Server should not trust:

- A `jku` URL supplied by the token.
- An `x5u` URL supplied by the token.
- An arbitrary embedded JWK in the header.
- A certificate chain supplied by the token sender without separate trust validation.
- A `kid` used as a file path or endpoint name.

`kid` is only an identifier to select a key within a trusted key set. It is not a URL, file path, or proof that the key is trustworthy.

### 5.5. Distinguishing Access-Token Signing Keys and DPoP Proof Keys

These are two different trust models:

| Key | Controlled By | Used By Resource Server For |
|---|---|---|
| AS signing key | Authorization Server | Verifying the access token signature |
| DPoP public key | Client | Verifying the DPoP proof and comparing thumbprint against `cnf.jkt` |

A DPoP proof includes a public JWK sent by the Client in the proof header. This is by design in DPoP: the Resource Server verifies the proof with that key and then compares its thumbprint with the key binding in the AS-verified access token.

Do not mechanically apply the "never use a JWK from the request" rule to DPoP proofs. You must distinguish a public key allowed in a DPoP proof per the RFC from the key source used to verify the access token signature. A DPoP public key is only accepted after the proof signature, claims, and `cnf.jkt` binding are all valid.

---

## 6. Key Selection, `kid`, and Key Rotation

### 6.1. `kid` Helps Select a Key in JWKS

A JWKS can contain multiple keys:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "signing-key-2025",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA-MODULUS>",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "signing-key-2026",
      "use": "sig",
      "alg": "RS256",
      "n": "<RSA-MODULUS-NEW>",
      "e": "AQAB"
    }
  ]
}
~~~

`kid` in the JOSE header helps the decoder locate the corresponding key. However, `kid` must not be used as an independent trust decision. The decoder should select the key from the trusted JWKS and verify the signature with a compatible key.

### 6.2. Safe Key Rotation Process

A rotation process typically has the following phases:

~~~text
Phase 1: Publish the new key
  JWKS contains old key + new key

Phase 2: Wait for Resource Servers to receive the new key
  Cache refresh / warm-up / propagation

Phase 3: Begin signing with the new key
  New tokens carry the new kid

Phase 4: Retain the old key during the overlap window
  Valid older tokens can still be verified

Phase 5: Overlap window ends
  Remove the old key from JWKS per policy
~~~

The overlap duration must account for:

- Maximum access token lifetime.
- Allowed clock skew.
- JWK cache lifetime/refresh behavior.
- Propagation delay across Resource Servers.
- In-flight requests and tokens issued right before the key switch.
- Emergency procedures if the old key is compromised.

Do not delete the old key immediately when the AS begins signing with the new key if valid tokens signed with the old key still exist.

### 6.3. Unknown `kid`

When the decoder receives a token with a `kid` not yet in cache, it may refresh JWKS to find the key. If no matching key is found, the token must be rejected.

You must control:

- Whether an unknown `kid` triggers a refresh.
- The number of refreshes within a time window.
- Behavior when the JWKS endpoint times out or returns 5xx.
- Behavior when JWKS returns an invalid response.
- Cache stampede when many concurrent requests use an unknown `kid`.
- Logs/metrics for unknown `kid` without logging tokens.

Never automatically accept an embedded key in the token when `kid` is not found. That turns a trusted key source failure into an unsafe trust fallback mechanism.

### 6.4. Compromised Key

If a signing key is exposed, the emergency procedure differs from scheduled rotation:

1. Stop using the compromised private key on the AS.
2. Remove or mark that key as untrusted as supported by infrastructure capabilities.
3. Evaluate cache invalidation/refresh on Resource Servers.
4. Handle tokens issued with the compromised key.
5. Assess remaining access token lifetime and replay risk.
6. Monitor requests using the old `kid`.
7. Notify service owners per the incident response process.

Simply removing the key from JWKS may not take effect immediately if Resource Servers still cache the public key. You need to understand cache behavior and have a refresh/invalidation mechanism suitable for compromise scenarios.

---

## 7. Configuring Spring Security for a Single Issuer and Audience

### 7.1. Minimal Configuration via `issuer-uri`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com/realms/shop
~~~

This configuration is the baseline for a single issuer. However, the API still needs audience validation if tokens are issued for multiple resources.

### 7.2. Creating a Decoder with Issuer, Audience, and Algorithm Allowlist

~~~java
package com.example.orders.security;

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
public class TrustedJwtConfig {

    private static final String ISSUER =
        "https://id.example.com/realms/shop";

    private static final String JWKS_URI =
        "https://id.example.com/realms/shop/protocol/openid-connect/certs";

    private static final String AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder =
            NimbusJwtDecoder.withJwkSetUri(JWKS_URI)
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(ISSUER);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            if (jwt.getAudience().contains(AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "Token is not intended for orders-api",
                    null
                )
            );
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                issuerAndTime,
                audience
            )
        );

        return decoder;
    }
}
~~~

Components:

- The JWKS URI is the key endpoint configured from a trusted source.
- RS256 is the only algorithm in the example allowlist.
- `JwtValidators.createDefaultWithIssuer` checks the issuer and default timestamps.
- The audience validator ensures the token was issued for the Orders API.
- `DelegatingOAuth2TokenValidator` combines the validators.

If the application uses Spring Boot, this custom `JwtDecoder` bean will be injected into the Resource Server. Verify that no other bean or security chain accidentally uses a decoder with a weaker policy.

### 7.3. Attaching the Decoder to a Servlet Resource Server

~~~java
@Configuration
@EnableWebSecurity
public class SecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            JwtDecoder jwtDecoder) throws Exception {

        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public/**").permitAll()
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(jwt -> jwt.decoder(jwtDecoder))
            )
            .build();
    }
}
~~~

The decoder enforces the token's trust policy. Authorization rules continue checking scopes. Issuer/audience validation does not replace endpoint-level authorization.

### 7.4. Configuring `ReactiveJwtDecoder`

With WebFlux, the trust policy principles are the same, except the decoder returns a `Mono`:

~~~java
@Bean
ReactiveJwtDecoder reactiveJwtDecoder() {
    NimbusReactiveJwtDecoder decoder =
        NimbusReactiveJwtDecoder.withJwkSetUri(JWKS_URI)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(ISSUER);

    OAuth2TokenValidator<Jwt> audience =
        audienceValidator(AUDIENCE);

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTime,
            audience
        )
    );

    return decoder;
}
~~~

Configuring the decoder in a WebFlux security chain:

~~~java
@Bean
SecurityWebFilterChain apiSecurity(
        ServerHttpSecurity http,
        ReactiveJwtDecoder reactiveJwtDecoder) {

    return http
        .authorizeExchange(exchange -> exchange
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.jwtDecoder(reactiveJwtDecoder))
        )
        .build();
}
~~~

The validator remains a synchronous API. `ReactiveJwtDecoder` invokes the validator in the decode pipeline and emits an error via `Mono` if validation fails. Do not put blocking network lookups inside `OAuth2TokenValidator`.

---

## 8. Multiple Issuers: Explicit Allowlists and Separate Decoders

### 8.1. When Are Multiple Issuers Needed?

A Resource Server may serve multiple tenants or organizations, each with its own Authorization Server. In that case, tokens may arrive from multiple accepted issuers.

Example:

~~~text
Trusted issuers:
  https://login.alpha.example
  https://login.beta.example

Resource:
  orders-api
~~~

Each issuer may have:

- Its own JWKS URI.
- Its own signing keys.
- Its own key rotation schedule.
- Its own audience policy.
- Its own claim mapping or scope convention.

Do not use one decoder with one JWKS URI for all issuers when the trust model requires separate key sources.

### 8.2. Resolve Issuers Only from a Configured List

Spring Security provides `AuthenticationManagerResolver` to select an `AuthenticationManager` per request. For multi-issuer setups, use a declared list of trusted issuers:

~~~java
@Bean
AuthenticationManagerResolver<HttpServletRequest>
authenticationManagerResolver() {

    return JwtIssuerAuthenticationManagerResolver
        .fromTrustedIssuers(
            "https://login.alpha.example",
            "https://login.beta.example"
        );
}
~~~

This is the pattern for a Servlet Resource Server. Specific factory APIs and imports must match the Spring Security version in use.

The key point is that issuers are restricted to a trusted list. Do not create decoders by taking any `iss` from a token and running discovery for that `iss`.

### 8.3. Each Issuer Has Its Own Audience Policy

If Alpha issues tokens for `orders-api` while Beta issues tokens for `orders-service`, configure the corresponding audience in each issuer's manager/decoder.

Do not use a single overly broad shared audience validator just to reuse code. You can reuse a decoder factory, but issuer, JWKS URI, audience, and algorithm allowlist parameters must be governed configuration.

### 8.4. Avoiding Issuer Confusion

Scenarios to reject:

- Issuer not in the allowlist.
- Issuer resembling a trusted issuer but differing in host/path.
- Valid issuer but audience not intended for the API.
- Issuer Alpha token verified with Beta's key.
- An issuer dynamically added from user-controlled data.
- An issuer discovery endpoint redirecting to a host disallowed by network policy.

If the system supports dynamic tenant onboarding, adding an issuer must be a governed workflow: verify domain/metadata, approve key source, define audience, and store trust configuration. Never automatically trust an issuer simply because a token contains that URL.

---

## 9. Opaque Tokens: Trusting the Introspection Endpoint and Response

### 9.1. No JWT Signature Verification on the Resource Server

For opaque tokens, the Resource Server typically sends the token to a configured introspection endpoint. The Authorization Server returns information such as:

~~~json
{
  "active": true,
  "sub": "user-417",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "iss": "https://id.example.com/realms/shop"
}
~~~

The Resource Server trusts the result because the request is sent to a trusted introspection endpoint over a protected channel and the endpoint is properly authenticated. The token itself never selects the introspection URL.

### 9.2. Configuring the Endpoint and Client Authentication

Spring Boot example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: ORDERS_INTROSPECTION_SECRET_FROM_SECRET_MANAGER
~~~

The client ID/secret here are the Resource Server's credentials for calling the introspection endpoint. Never commit secrets to source code or config files stored in a repository. The placeholder in the example represents a value injected from a secret manager or runtime environment.

In production:

- Use a secret manager or workload identity if supported by the AS.
- Limit the permissions of the introspection client.
- Use HTTPS and certificate validation.
- Do not send tokens to client-specified endpoints.
- Configure timeouts and connection pools.
- Rotate introspection credentials on a schedule.
- Scrub tokens and secrets from logs.

### 9.3. Checking Attributes in the Introspection Response

If customizing `OpaqueTokenIntrospector` or `ReactiveOpaqueTokenIntrospector`, verify:

- `active` is `true`.
- Issuer is right if the response includes an issuer and policy requires it.
- Audience contains the API's resource identifier.
- Scope is sufficient for the endpoint.
- Subject/principal is mapped per contract.
- Token type/profile matches.
- Client/authorized party is correct when required by policy.
- Custom claims are not inadvertently turned into unintended authorities.

Do not treat HTTP 200 from the introspection endpoint as proof that the token is active. HTTP 200 can contain `active=false`. Nor treat a response missing `active` as active by default.

### 9.4. Introspection Endpoint Failures

If the endpoint times out, returns 5xx, or fails TLS validation, the Resource Server cannot verify the token. Never fail open by creating a default `Authentication`.

Distinguish:

- Inactive token: the Authorization Server confirms the token is no longer active.
- Introspection unavailable: token status cannot be determined.
- Wrong Resource Server credentials: the introspection client is not authorized to call the endpoint.
- TLS/hostname failure: cannot verify that the endpoint is the trusted server.

None of these cases may produce a successful `Authentication`. Error mapping may differ, but a dependency failure must never be turned into a valid token.

---

## 10. Token Profile and Intended Purpose

### 10.1. An ID Token Is Not an Access Token

In OIDC, an ID token carries information about an authentication event and is issued to an OIDC client. An access token is used to access a resource server.

An ID token may have a valid signature and the right issuer, yet still must not be accepted as an access token. The Resource Server needs to verify the audience and token profile appropriate for the API.

Example:

~~~text
ID token:
  iss = https://id.example.com
  aud = shop-web-client

Access token:
  iss = https://id.example.com
  aud = orders-api
~~~

If the Orders API accepts any JWT from the issuer without checking audience/purpose, an ID token could be misused at the API.

### 10.2. Checking Token Type/Profile

Depending on the Authorization Server and token profile, standardized `typ` headers or claims can distinguish access tokens. For example, JWT access tokens under RFC 9068 use `typ` `at+jwt`.

If applying that profile, check `typ` and the profile's required claims. Do not add an arbitrary `typ` check and assume it replaces issuer, audience, signature, expiry, and scope validation.

A custom validator can check `typ` after the decoder verifies the signature:

~~~java
static OAuth2TokenValidator<Jwt> accessTokenTypeValidator() {
    return jwt -> {
        Object typ = jwt.getHeaders().get("typ");

        if ("at+jwt".equals(typ)) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Expected an access token JWT",
                null
            )
        );
    };
}
~~~

Only enable this validator if the Authorization Server actually issues tokens following that profile. If the system uses a different profile, configure the check to match the agreed token contract.

---

## 11. Testing Trust Policy: Positive and Negative Cases

### 11.1. Testing the Audience Validator

~~~java
@Test
void acceptsExpectedAudience() {
    Jwt jwt = validJwtWithAudience("orders-api");

    OAuth2TokenValidatorResult result =
        audienceValidator("orders-api").validate(jwt);

    assertTrue(result.getErrors().isEmpty());
}

@Test
void rejectsDifferentAudience() {
    Jwt jwt = validJwtWithAudience("billing-api");

    OAuth2TokenValidatorResult result =
        audienceValidator("orders-api").validate(jwt);

    assertFalse(result.getErrors().isEmpty());
}
~~~

### 11.2. Testing the Issuer

~~~java
@Test
void rejectsUntrustedIssuer() {
    Jwt jwt = validJwtWithIssuer(
        "https://attacker.example/issuer"
    );

    OAuth2TokenValidator<Jwt> validator =
        JwtValidators.createDefaultWithIssuer(
            "https://id.example.com/realms/shop"
        );

    assertTrue(validator.validate(jwt).hasErrors());
}
~~~

This test verifies the issuer validator. Decoder integration tests should also include signed compact JWTs to confirm the full path.

### 11.3. Testing the Algorithm Allowlist

Use a token fixture signed with an allowed algorithm and a fixture signed with a disallowed algorithm.

| Fixture | Policy | Result |
|---|---|---|
| RS256, trusted key | RS256 only | Accepted if claims are valid |
| ES256, trusted key | RS256 only | Rejected |
| RS256, key not in trusted JWKS | RS256 only | Rejected |
| `none` | RS256 only | Rejected |
| HS256 when policy is asymmetric-only | RS256 only | Rejected |
| RS256, wrong audience | RS256 only | Rejected |
| RS256, wrong issuer | RS256 only | Rejected |

Do not merely edit the `alg` string in the header of an already signed token to build a test. The signature will become invalid and the test may fail at signature verification rather than for the algorithm allowlist reason. Generate dedicated fixtures to target the exact branch under test.

### 11.4. Testing the Trusted Key Source

Tests should cover:

- Valid JWKS endpoint returns the right public key.
- JWKS endpoint TLS hostname mismatch.
- JWKS endpoint timeout.
- JWKS returns malformed JSON/JWK.
- Non-existent `kid`.
- JWK key type incompatible with the algorithm.
- Key rotation with overlap.
- Old key removed while older tokens are still valid.
- JWKS URI changed outside approved configuration.

Use a mock HTTP server or test JWKS endpoint to control responses. Never call a production Authorization Server in tests.

### 11.5. Testing Audience and Issuer Together

A token is only accepted when every condition holds:

~~~text
issuer trusted
AND signature valid with trusted key
AND algorithm allowed
AND audience contains this API
AND exp/nbf valid
AND token profile acceptable
AND required authorization scope present
~~~

Here, scope is typically checked at the authorization layer after `Authentication`. Therefore, test the decoder and authorization rules separately, and also have an integration test confirming they are wired together properly.

### 11.6. Testing Multiple Issuers

For a multi-issuer resolver, verify:

- Issuer Alpha uses Alpha's decoder/key source.
- Issuer Beta uses Beta's decoder/key source.
- An issuer outside the allowlist is rejected.
- An Alpha token is not verified using Beta's key.
- Each issuer's audience policy is enforced.
- Changing the issuer allowlist requires deployment/configuration approval per process.

---

## 12. Logging, Metrics, and Auditing for Trust Policy

### 12.1. Recording Rejection Reasons Safely

You can track failure categories such as:

- `untrusted_issuer`
- `invalid_audience`
- `unsupported_algorithm`
- `signature_invalid`
- `unknown_kid`
- `jwks_unavailable`
- `malformed_jwks`
- `token_expired`
- `token_not_yet_valid`
- `token_profile_invalid`
- `introspection_inactive`
- `introspection_unavailable`

Use stable error codes or standardized categories. Never put raw JWTs, access tokens, client secrets, private keys, or full sensitive claims into logs.

### 12.2. Metric Cardinality

Metric tags should have a bounded set of values:

~~~text
security.jwt.validation{outcome="success"}
security.jwt.validation{outcome="invalid_audience"}
security.jwt.validation{outcome="unknown_kid"}
security.jwks.fetch{outcome="error"}
~~~

Do not use subject, email, token, request ID, or unbounded `kid` as tags. If a specific key needs investigation, emit controlled audit events rather than creating metric series per dynamic value.

### 12.3. Auditing Trust Configuration Changes

Changes to issuers, audiences, JWKS URIs, algorithms, and key trust must be traceable:

- Who made the change?
- In which environment?
- What were the old and new values?
- Why was it changed?
- Who reviewed/approved it?
- When was it deployed?
- What is the rollback plan?
- Does key rotation have an overlap window and validation tests?

Never record private keys or secrets in audit logs. For JWKS URIs and issuers, recording public endpoint values may be appropriate, subject to organizational security policy.

---

## 13. Common Mistakes

| Mistake | Risk | Mitigation |
|---|---|---|
| Verifying only the signature | Tokens from another issuer or API can slip through | Validate issuer and audience |
| Accepting any issuer from the token | Attackers can control discovery/key sources | Use a preconfigured issuer allowlist |
| Checking only `iss` | Tokens intended for other APIs can still be accepted | Check specific audience |
| Using `client_id` instead of audience | Confuses OAuth client with resource server | Check `aud` per API |
| Allowing all library-supported `alg`s | Algorithm confusion and weak policy | Explicit algorithm allowlist |
| Allowing `none` | No signature verified | Reject `none` |
| Sharing an HMAC secret across all Resource Servers | Every verifier can sign tokens | Prefer asymmetric keys when appropriate |
| Trusting `jku`/`x5u` in the token | Token chooses its own key source | Configure trusted JWKS URI |
| Using `kid` as a URL/file path | Key selection can be manipulated | Only use `kid` to look up keys in trusted JWKS |
| Skipping issuer validator when using JWKS URI | Valid key could verify tokens with wrong issuer | Attach an issuer validator |
| Using one shared audience for all APIs | Token substitution across resources | Separate audience per API |
| Accepting ID tokens at Resource Server | Wrong token purpose | Check access-token profile and audience |
| Deleting old key immediately on rotation | Valid older tokens are rejected | Maintain an overlap window |
| Keeping a compromised key cached indefinitely | Forged tokens continue passing verification | Have an incident procedure and cache invalidation |
| Falling back to embedded JWK on unknown `kid` | Unsafe trust fallback | Only use configured key sources |
| Disabling TLS certificate validation for JWKS | Key source can be replaced in transit | Keep TLS validation enabled |
| Treating introspection HTTP 200 as active | `active=false` tokens can pass | Check `active=true` |
| Treating introspection timeout as active | Fail-open | Never grant `Authentication` when verification fails |
| Metric tags containing dynamic issuer/token/user | High cardinality and data leakage | Use bounded categories |
| Multi-issuer auto-discovering arbitrary `iss` | SSRF or trust expansion | Allowlist issuers and govern onboarding |

---

## 14. Process for Implementing a Trust Policy

### Step 1: Define the Resource Identifier

Choose the official audience for the API, e.g. `orders-api`. Use the same identifier across the Authorization Server, token issuance, and Resource Server validation.

### Step 2: Identify Permitted Issuers

List exact issuers. Verify issuer metadata and JWKS endpoints through a trusted channel. If there are multiple issuers, each issuer must have its own configuration or a manager resolved from an allowlist.

### Step 3: Select Algorithms

Choose asymmetric signing algorithms compatible with the AS and crypto policy. Configure the allowlist in the decoder. If migrating across algorithms, specify start/end dates for accepting the legacy algorithm.

### Step 4: Manage Key Sources

Configure issuer discovery or static JWKS URIs. Ensure HTTPS, TLS validation, network egress policies, and cache lifecycles. Never load access-token signing keys from URLs specified by the token.

### Step 5: Attach Validators

Combine issuer, audience, timestamp, and token-profile validators. Keep scope/role/resource authorization in the authorization layer.

### Step 6: Design Rotation

Establish key overlap, cache refresh, unknown-`kid` handling, and incident response for key compromise. Test across multiple Resource Server instances.

### Step 7: Run Negative Tests

Create tokens with wrong issuer, audience, `alg`, signature, `kid`, expiry, and token profile. Confirm all are rejected.

### Step 8: Observe and Audit

Monitor validation failure categories, JWKS fetches, and rotation events. Audit all trust configuration changes. Never log credentials.

---

## 15. Self-Check Questions

**Question 1.** How do issuer and audience differ?

**Answer:** Issuer identifies the Authorization Server that issued the token; audience identifies the resource/API permitted to receive the token.

**Question 2.** Why can a token with a valid signature still be rejected?

**Answer:** The token may have the wrong issuer, wrong audience, be expired, use a disallowed algorithm, or not match the API's token profile.

**Question 3.** Should you trust an issuer taken directly from the `iss` claim for automatic discovery?

**Answer:** No. Issuers must be in a configured and governed allowlist. Tokens must not expand the trust boundary on their own.

**Question 4.** Does `client_id` replace audience?

**Answer:** No. `client_id` is the OAuth client requesting the token; `aud` is the resource receiving the token.

**Question 5.** Why is an algorithm allowlist needed?

**Answer:** JOSE `alg` is input from the token. An allowlist prevents tokens from requesting out-of-policy algorithms or causing algorithm confusion.

**Question 6.** Why are asymmetric keys well suited for multiple Resource Servers?

**Answer:** The AS holds the private key for signing, while Resource Servers only need the public key for verification. Verifiers do not need to hold a secret capable of signing tokens.

**Question 7.** Can access-token verification keys be loaded from `jku` in the token?

**Answer:** No. The JWKS URI must come from trust configuration or metadata of a trusted issuer, not from a URL sent in the token.

**Question 8.** Is `kid` proof that a key is trusted?

**Answer:** No. `kid` is only an identifier used to select a key inside a trusted JWKS.

**Question 9.** When using a JWKS URI directly, do you still need to check the issuer?

**Answer:** Yes. Configuring a key source does not replace issuer validation.

**Question 10.** Why is an overlap window needed during key rotation?

**Answer:** Resource Servers need time to pick up the new key and must still verify valid older tokens signed with the old key.

**Question 11.** If the JWKS endpoint times out, can tokens with an unknown key be accepted?

**Answer:** No. Without a trusted key to verify the signature, the token cannot be authenticated.

**Question 12.** Can an ID token be used as an access token?

**Answer:** No. ID tokens are intended for OIDC clients; Resource Servers must verify the audience and token profile of access tokens.

**Question 13.** Is an HTTP 200 introspection response sufficient to accept an opaque token?

**Answer:** No. The response must indicate `active=true` and required attributes must satisfy the trust policy.

**Question 14.** How should a multi-issuer setup select decoders?

**Answer:** Use a resolver with a preconfigured list of trusted issuers and an appropriate decoder, key source, and audience policy for each issuer.

**Question 15.** Should metrics use `subject` or raw `kid` as tags?

**Answer:** No. Dynamic values increase cardinality; use bounded outcome categories and separate audits when investigation is needed.

---

## 16. References

- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): algorithm verification, issuer/audience validation, and common JWT pitfalls.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): `iss`, `sub`, `aud`, `exp`, `nbf` claims and JWT structure.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517.html): JWK, JWKS, `kid`, `use`, and key metadata.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068.html): access-token JWT profile and `typ` `at+jwt`.
- [OpenID Connect Discovery](https://openid.net/specs/openid-connect-discovery-1_0.html): issuer metadata and `jwks_uri`.
- [OAuth 2.0 Authorization Server Metadata, RFC 8414](https://www.rfc-editor.org/rfc/rfc8414.html): Authorization Server metadata.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `issuer-uri`, `jwk-set-uri`, `JwtDecoder`, and validators.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` and reactive JWT validation.
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): configuring JWT decoders and JWS algorithms.
- [Spring Security API — JwtIssuerAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerAuthenticationManagerResolver.html): resolver for multiple trusted issuers.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and opaque token authentication.

APIs may change between Spring Security versions. Check the Javadoc of the exact resolved artifact, especially for decoder builders, algorithm configuration, and multi-issuer resolvers.

---

## 17. Key Takeaways

A Resource Server must have an explicit trust policy before accepting tokens. A valid signature only proves a token was signed by some key; issuer, audience, algorithm, and key source determine whether that key and token are trusted by the API.

- **Issuer:** accept only allowlisted Authorization Servers.
- **Audience:** tokens must be intended for the specific API/resource.
- **Algorithm:** declare an explicit allowlist; do not let tokens choose their own algorithm.
- **Key source:** use trusted issuer metadata or JWKS URIs over HTTPS; never fetch access-token signing keys from URLs specified in the token.
- **Key rotation:** maintain an overlap window, handle unknown `kid`s, and have an emergency procedure for compromised keys.
- **Multi-issuer:** each issuer needs its own decoder, key source, and audience policy.
- **Opaque tokens:** trust a configured introspection endpoint, verify `active` and response attributes; dependency failures must never grant `Authentication`.
- **Testing/operations:** test both valid tokens and tokens with wrong issuer, audience, `alg`, signature, `kid`, and profile; audit all trust configuration changes.

A secure Resource Server only authenticates a token when the entire trust policy aligns with the protected resource.
