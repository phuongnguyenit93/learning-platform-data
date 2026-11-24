# Validating JWT Signature, Algorithm, Issuer, Audience, and Expiration

A **JWT (JSON Web Token)** can be read without a secret key. Therefore, decoding the payload and seeing fields such as `sub`, `scope`, `iss`, or `exp` **does not prove** that the token is trustworthy. When an API receives a JWT **Bearer access token**, it must verify the **signature and verification key**, **allowed algorithm**, **issuer**, **audience**, **expiration**, and appropriate business conditions **before** using claims to construct an identity or grant access.

In a Spring Security Servlet application, this work is typically handled by OAuth2 Resource Server via `BearerTokenAuthenticationFilter`, `JwtAuthenticationProvider`, and `JwtDecoder`. Once the token is verified as valid, Spring Security converts the appropriate claims into an `Authentication` and `GrantedAuthority` collection; the authorization step then decides which operations the API permits.

This lesson focuses on exactly five verification groups: **signature, algorithm, issuer, audience, time**. The examples use Spring Boot 3.x, Spring Security 6.x, Java 17+, and tokens issued by a trusted authorization server/IdP. Domains, audiences, keys, and claims in this lesson are illustrative; there are no real private keys or access tokens.

## 1. How Is a JWT Passed to an API?

In OAuth2, a Resource Server typically receives an access token over HTTP:

~~~http
GET /api/orders/ping HTTP/1.1
Host: api.example.test
Authorization: Bearer eyJ...<test-token>...abc
~~~

**Bearer** means the party holding the token can present it to request permissions; if the token leaks, someone else can reuse it until it expires or the system blocks it. The transport protocol must be protected with HTTPS; never put tokens in URLs, logs, or commits.

A **JWS Compact JWT** has three Base64url segments joined by dots:

~~~text
BASE64URL(protected-header).BASE64URL(payload).BASE64URL(signature)
                 ①                  ②                 ③
~~~

- **Protected header** contains parameters such as `alg` (signing algorithm), `kid` (key selection hint), and optionally `typ`.
- **Payload** is the set of claims such as `iss`, `sub`, `aud`, `iat`, `nbf`, `exp`, `scope`.
- **Signature/MAC** is computed over the first two segments using the selected algorithm and appropriate key type. Any meaningful modification to the header or payload must cause signature verification to fail.

Two JSON parts **only for learning structure**, not a signed token:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-01",
  "typ": "JWT"
}
~~~

~~~json
{
  "iss": "https://auth.example.test/realms/training",
  "sub": "user-123",
  "aud": ["urn:orders-api"],
  "iat": 1793923200,
  "nbf": 1793923200,
  "exp": 1793923500,
  "scope": "orders.read"
}
~~~

In this fixture, `iat` and `nbf` are at 2026-11-06 00:00:00 UTC, and `exp` is at 00:05:00 UTC on the same day. Those numbers only make sense when testing at the corresponding time. When running after the expiration time, **the validator must reject it**, even if the signature is valid. Printed claims are **untrusted data until all checks succeed**.

### How Does a JWT Differ from an Access Token?

- **JWT** is a token format that can serve as an access token, ID token, or internal token. Not every access token is a JWT; an opaque access token requires introspection with the authorization server.
- **JWS** provides integrity and issuer authenticity via a digital signature or MAC. JWS does not encrypt the payload contents by itself.
- **JWE** is an encrypted token format with a different decryption/verification pipeline; do not feed a five-part JWE into a three-part JWS decoder and infer meaning from the failure.
- **OIDC ID token** is meant for the client to identify a user login session; an API must not accept an ID token as an access token by default merely because it has a valid signature and the same issuer. Separate audience, token type/use, and policies are needed for access tokens.

## 2. Verification Chain from Bearer Token to Authentication

~~~text
Client sends Authorization: Bearer <JWT>
            │
            ▼
BearerTokenAuthenticationFilter
            │ extracts raw bearer token
            ▼
BearerTokenAuthenticationToken
            │
            ▼
JwtAuthenticationProvider
            │ calls JwtDecoder
            ▼
NimbusJwtDecoder
    ├─ parses JWS, checks structure/typ per decoder
    ├─ checks "alg" is in allowlist and key type matches
    ├─ selects trusted key from pinned JWKS, typically via "kid"
    ├─ verifies digital signature/MAC
    └─ runs claim validators
         ├─ iss == trusted issuer
         ├─ aud contains an accepted resource/API identifier
         ├─ exp not expired (per configured clock skew)
         ├─ nbf not in the future beyond allowed skew
         └─ additional claims if required by the application
            │ all PASS
            ▼
JwtAuthenticationToken (authenticated)
            │ scopes → authorities, e.g. SCOPE_orders.read
            ▼
AuthorizationFilter
    ├─ sufficient permissions: enter controller
    └─ insufficient permissions: deny access
~~~

Specific components may vary by version and configuration, but the logical security order must hold: **use claims to authenticate and grant permissions only after JWS and validators succeed**.

A JWT with a valid signature but wrong `aud` must be rejected; a JWT with the right `iss` that has expired must also be rejected; an unmodified JWT signed with a key **not belonging to the issuer** is likewise invalid.

## 3. Verifying the Signature and Selecting a Trusted Key

### 3.1. What Does a Signature Prove?

With `RS256` (RSA + SHA-256):

- The Authorization Server holds the **private key** to sign tokens.
- The Resource Server obtains the corresponding **public key** from an authenticated/configured source.
- If the signature is valid, the validator knows the token was not altered after being signed by the **corresponding key**.
- To conclude "the token came from an issuer the API trusts," the Resource Server must also know **that key truly belongs to the trusted issuer**. A signature under an arbitrary public key attached to the request is not enough.

With HMAC (`HS256`), signing and verification use **the same secret**; designs with multiple Resource Servers must be careful because any verifier that knows the secret can also mint new tokens. With asymmetric signatures such as `RS256` or `ES256`, the API only needs the public key.

### 3.2. JWKS, JWK, and kid

An authorization server typically publishes its key set as a **JWKS** (JSON Web Key Set) over a known HTTPS URL, for example:

~~~text
https://auth.example.test/realms/training/protocol/openid-connect/certs
~~~

The JWKS response may contain multiple public JWKs:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "key-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "<base64url-RSA-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

The snippet above only illustrates structure and contains no real RSA key for verification. `kid` is a **selection hint** among keys already fetched from a **trusted JWKS**; it **does not by itself prove the key is trustworthy**.

Safe verification principles:

1. Configure the issuer/JWKS endpoint from application configuration or metadata fetched via a **trusted issuer**; never take the URL from the request.
2. Only select keys whose type, use, and algorithm match policy.
3. Use `kid` to look up a key in **that issuer's** JWKS; never treat `kid` as a file path, table name, or URL.
4. Verify the signature and all claim validations.
5. When the issuer rotates keys, allow the system to refresh the JWKS from the trusted source with an appropriate cache policy; test tokens signed with old/new keys during the overlap window.

**Preventing key-source spoofing:** headers like `jku`, `jwk`, or `x5u` sent inside a token are caller-supplied data. Never automatically fetch URLs from them or trust a public key embedded in the token. If you configure a trusted issuer at `https://auth.example.test`, do not accept a token pointing `jku` to an attacker's domain just because the signature verifies with the key hosted there.

**If `kid` is not found:** the token generally fails verification; distinguish between issuer key rotation/JWKS caching and a forged token. Never "fall back" to an arbitrary caller-supplied key.

### 3.3. Why Is Checking the Signature Not Enough?

An attacker might hold an account on the very same issuer and obtain an access token **for another application**. That token is still validly signed by the issuer, yet must not be used to call the current API if `aud` is wrong. A token from another tenant or issuer could also be validly signed by **another system's** key outside this API's trust boundary.

That is why signature, issuer, and audience checks must work together. Granting access based solely on `sub` or `scope` after parsing a JWT is wrong.

## 4. Signing Algorithms: Accept Only an Allowlist

The JWT protected header has an `alg` field. This value is chosen by the token sender, so **never let the token dictate security policy**.

| Algorithm | Key Type | Notes |
| --- | --- | --- |
| `RS256` | RSA private/public | Common for authorization server JWTs; API only needs public key |
| `ES256` | ECDSA P-256 private/public | Requires matching key type/curve and verifier |
| `PS256` | RSA-PSS private/public | Must be configured on both issuer and Resource Server |
| `HS256` | HMAC shared secret | Use only with an appropriate shared-secret management design |
| `none` | No signature | Must not be accepted for Bearer access tokens requiring signature verification |

Other algorithms may be standard-compliant, yet should only be enabled after evaluating policy, key types, and library support. **Never enable all algorithms for convenience.**

### Algorithm Confusion

In weak libraries or custom implementations, an attacker can alter the header from `RS256` to `HS256` and trick the verifier into treating the RSA public key as an HMAC secret, or switch to `none` to skip signature verification. RFC 8725 describes these vulnerabilities.

How to prevent them:

- Pin an **algorithm allowlist** per issuer.
- Bind algorithms to their corresponding **key types**; never allow the same key to serve as both an RSA public key and an HMAC secret.
- Use a JWT library with standard JWS validation; never write a custom `verify` by comparing Base64 text.
- Never trust claims or permissions if the token did not pass signature verification.
- Test tokens with `alg` modified to `none`/`HS256`/disallowed algorithms and ensure they are rejected.

In Spring Security Resource Server with `NimbusJwtDecoder`, the documentation notes that `RS256` is trusted by default under standard configuration, yet the application should explicitly manage algorithm policy if the issuer uses another algorithm. Verify the IdP's actual algorithm before changing it.

## 5. Issuer: Who Issued the Token?

The `iss` claim identifies the issuer. Its value must match the **exact issuer the API accepts**. For example:

~~~json
{
  "iss": "https://auth.example.test/realms/training"
}
~~~

The API expects:

~~~text
EXPECTED_ISSUER=https://auth.example.test/realms/training
~~~

Do not accept a token with `iss=https://auth.attacker.test` simply because the attacker signed it with some public key. The Resource Server must know the mapping **issuer → trusted JWKS/keys** from configuration.

Key points to watch:

- Compare against the exact canonical issuer published by the IdP; do not strip realm/tenant paths, alter hostnames, or drop trailing `/` without an explicit contract.
- `https://auth.example.test/realms/training` and `https://auth.example.test/realms/other` are two distinct issuers.
- When using OIDC/OAuth Authorization Server metadata, verify the metadata belongs to the expected issuer and the JWKS endpoint is obtained through a trusted mechanism.
- In multi-tenant/multi-issuer systems, maintain an **accepted issuer allowlist** and configure the corresponding authentication manager/decoder per issuer. Never trust a new issuer based solely on an unverified `iss` claim.

**Distinction:** the `sub` claim identifies a subject scoped to the issuer; when storing cross-issuer users, identify them by the pair (`iss`, `sub`), not `sub` alone. A JWT with the right issuer is still not necessarily intended for the API serving the request.

## 6. Audience: Which API Is the Token For?

The `aud` claim identifies the intended recipient(s). Per the JWT spec, it can be a **string** or an **array of strings**; Spring Security provides `jwt.getAudience()` to access it as a list.

For example, the Orders API requires:

~~~text
EXPECTED_AUDIENCE=urn:orders-api
~~~

A token with:

~~~json
{"aud":["urn:orders-api","urn:reporting-api"]}
~~~

can satisfy the Orders API's audience check because the list **contains** `urn:orders-api` (if policy allows multiple audiences). The following token must be rejected:

~~~json
{"aud":"urn:payments-api"}
~~~

Even when the signature, issuer, and timestamps are valid, a token issued for the Payments API must not be used to call the Orders API.

**Audience is not scope**:

| Claim / Concept | Answers the Question | Example |
| --- | --- | --- |
| `iss` | Who issued the token? | `https://auth.example.test/realms/training` |
| `aud` | Which resource/API was the token issued for? | `urn:orders-api` |
| `sub` | Which subject is the token about? | `user-123` |
| `scope` or `scp` | Granted permissions within the relevant context | `orders.read` |
| `client_id` / `azp` per profile | Which OAuth client app received/makes the request? | `web-client` |

`client_id` or `azp` **does not replace `aud`**. Having `scope=orders.read` does not make the audience valid if the token was issued for another API. For an OAuth2 Resource Server, a typical policy is **right issuer + right audience + unexpired + sufficient authority**.

### Cross-JWT Confusion and ID Tokens

An OIDC ID token may share the same `iss`, be signed with the same JWK, contain `sub`, and be unexpired. However, its `aud` is typically the **OIDC client ID**, different from the API's audience. The API must reject tokens intended for another purpose. If the architecture involves multiple token types, also verify token type/profile such as `typ`, required claims, and how the issuer distinguishes ID tokens from access tokens; a valid signature alone is not enough to prevent token-type confusion.

## 7. Expiration and Time Windows: exp, nbf, iat, Clock Skew

In JWTs, time claims typically use **NumericDate**: seconds since the Unix epoch UTC. This is **not milliseconds** like Java's `System.currentTimeMillis()`.

| Claim | Meaning | Validation |
| --- | --- | --- |
| `exp` (*expiration time*) | Token must not be used from expiration onward | Reject once expired, accounting for allowed clock skew |
| `nbf` (*not before*) | Do not accept token before it becomes effective | Reject if "not yet valid," accounting for skew |
| `iat` (*issued at*) | When the token was issued | Useful for sanity checks / max age per policy; **does not replace `exp`** |

Example timestamps for a test fixture:

~~~text
iat = nbf = 1793923200  → 2026-11-06 00:00:00 UTC
exp =       1793923500  → 2026-11-06 00:05:00 UTC

T=00:02:00 UTC: valid in time
T=00:06:00 UTC: expired
T=23:59:00 previous day: before nbf
~~~

The table above assumes **no slack added via clock skew**. When skew is configured, boundary checks allow a small margin to compensate for clock drift between the IdP and the API. Spring Security's `JwtTimestampValidator` supports skew; the documentation describes a common default of 60 seconds for Resource Server. Never increase skew to several minutes or hours just to mask clock sync issues, as that widens the window for expired or not-yet-valid tokens.

Validation examples:

- Token with 2 minutes left before `exp` and `nbf` already passed: valid **in time**, still needs signature, issuer, and audience checks.
- Token whose `exp` passed 10 minutes ago: must not be accepted merely because the JWT has the right `scope`.
- Token with `nbf` 5 minutes in the future: reject per policy (under normal skew).
- `iat` far in the past: not automatically a standard error if `exp` is still valid, though the application may enforce a separate **max token age / max lifetime** policy.
- Token missing `exp`: whether required depends on token profile/issuer policy. For secure access tokens, require `exp` and a finite lifetime; if mandatory, add an appropriate validator and tests.

**These checks use the Resource Server's clock**, so containers must synchronize via NTP. If logs print timestamps in a local timezone, convert properly to UTC before concluding a token expired prematurely.

### Trustworthiness of iat

`iat` does not mean "permissions granted from this exact moment." An issuer can mint a JWT with an older or current `iat`; the application needs its own policy if it wants to reject overly old tokens, cap TTL, or require `iat <= now + skew`. Never treat `iat` as milliseconds, and never replace Spring's `exp`/`nbf` validator with a handwritten `iat` check.

## 8. Spring Boot 3.x + Spring Security 6.x Configuration

The most common approach is configuring the application as an **OAuth2 Resource Server accepting JWTs**, using a real Authorization Server's issuer/JWKS. Spring Security handles JWS, signature, timestamps, and issuer; Spring Boot lets you declare the expected audience.

### 8.1. Dependencies

In a Spring Boot project's Groovy DSL `build.gradle` where versions are managed by the BOM/plugin:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

The OAuth2 Resource Server starter pulls in compatible JWT/JOSE dependencies via Spring Boot; there is no need to manually manage Nimbus versions unless special requirements dictate otherwise. The snippets below belong in a project with Gradle wrapper, Java 17+, and the Spring Boot plugin; they do not create an IdP or sign tokens themselves.

### 8.2. application.properties

File `src/main/resources/application.properties`:

~~~properties
spring.security.oauth2.resourceserver.jwt.issuer-uri=https://auth.example.test/realms/training
spring.security.oauth2.resourceserver.jwt.jwk-set-uri=https://auth.example.test/realms/training/protocol/openid-connect/certs
spring.security.oauth2.resourceserver.jwt.audiences[0]=urn:orders-api
spring.security.oauth2.resourceserver.jwt.jws-algorithms[0]=RS256
~~~

Explanation:

1. **`issuer-uri`** is the issuer to verify against `iss`. Spring Security uses this to configure the issuer validator.
2. **`jwk-set-uri`** is the JWKS endpoint providing public keys for signature verification. When both issuer and JWKS URI are declared, the app can initialize configuration without relying on startup metadata discovery; JWKS still must be reachable when verifying tokens or refreshing keys.
3. **`audiences[0]`** is the expected audience. Spring Boot 3.3 supports `spring.security.oauth2.resourceserver.jwt.audiences`. The Orders API rejects access tokens intended for other APIs.
4. **`jws-algorithms[0]`** is the signing algorithm allowlist; here only `RS256` is permitted. Only switch algorithms if the actual issuer uses another algorithm and key design matches.

**Never replace the illustrative hostname with a client-supplied endpoint.** All URIs and audiences must come from environment-managed trusted configuration; JWKS must use HTTPS and its TLS certificate must be verified by the JVM.

**If only `jwk-set-uri` is configured without an issuer:** signatures can be verified, but do not assume `iss` has been checked. If you need issuer pinning, declare `issuer-uri` or configure an equivalent `JwtIssuerValidator`.

**If the issuer exposes standard discovery:** the app can set only `issuer-uri` and let Resource Server discover JWKS via metadata. Also specifying `jwk-set-uri` avoids depending on metadata discovery at startup, while requiring you to keep the JWKS endpoint accurate if the IdP changes it.

### 8.3. SecurityFilterChain and Verification Endpoint

File `src/main/java/example/jwt/JwtResourceApplication.java`:

~~~java
package example.jwt;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class JwtResourceApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtResourceApplication.class, args);
    }
}

@Configuration(proxyBeanMethods = false)
class JwtResourceSecurity {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {

        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated());

        http.oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}

@RestController
class OrdersController {
    @GetMapping("/api/orders/ping")
    String ping() {
        return "ok";
    }
}
~~~

Meaning:

- `oauth2ResourceServer(...jwt...)` enables Bearer JWT authentication using the `JwtDecoder` configured by Boot from the properties above.
- `hasAuthority("SCOPE_orders.read")` is an **authorization check after the token is valid**. By default, Spring maps scope `orders.read` to authority `SCOPE_orders.read`.
- The `/api/orders/ping` endpoint returns `ok` only when the request has passed authentication and carries the required scope.
- Tokens with bad signature/issuer/audience/timestamps **do not receive a valid authentication**; authorization policy cannot fix an invalid token.
- If the app has multiple `SecurityFilterChain` beans, verify the right chain applies to this API; avoid letting another public chain shadow the Bearer chain.

### 8.4. Running and Testing Requests

With the project prepared and a real IdP exposing the configured endpoints:

~~~bash
./gradlew bootRun
~~~

On Windows use `gradlew.bat bootRun`. Put a **real** access token issued for `urn:orders-api` into your shell's `ACCESS_TOKEN` environment variable, then:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/orders/ping
~~~

The commands above use Unix shell syntax. In PowerShell, adjust the environment variable syntax accordingly. Call plain HTTP only on loopback for local illustration; production requires HTTPS and never saving tokens in command history or logs.

If the token is signed by a trusted key, `iss` matches, `aud` contains `urn:orders-api`, timestamps are valid, and scope includes `orders.read`, the response body is:

~~~text
ok
~~~

Actual results depend on a JWT issued by the IdP, reachable JWKS, and permission configuration. **You cannot run the example successfully just by copying placeholder domains or illustrative JWT JSON.** Missing or invalid tokens are rejected at authentication (typically HTTP 401); authenticated tokens missing `orders.read` are rejected at authorization (HTTP 403).

## 9. Customizing Validators in Java for Complex Policies

Spring Boot properties are great when standard issuer/audience checks suffice. When custom validators are needed, configure a custom `JwtDecoder` while **retaining default checks**, especially issuer and timestamps. A common mistake is registering a custom `JwtDecoder` that only checks audience and accidentally drops auto-configured issuer/time validators.

Complete example of a bean for **one issuer, one audience, RS256**. This is an **alternative** to Boot's auto-configured `JwtDecoder` in section 8.2, not a class to register alongside another decoder bean.

Add to `application.properties` for the custom example (using `app.jwt.*` keys, while keeping the `SecurityFilterChain` above):

~~~properties
app.jwt.issuer=https://auth.example.test/realms/training
app.jwt.jwk-set-uri=https://auth.example.test/realms/training/protocol/openid-connect/certs
app.jwt.audience=urn:orders-api
~~~

File `src/main/java/example/jwt/CustomJwtDecoderConfig.java`:

~~~java
package example.jwt;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration(proxyBeanMethods = false)
public class CustomJwtDecoderConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${app.jwt.issuer}") String issuer,
            @Value("${app.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${app.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwkSetUri)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> standardValidators =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> requiredAudience = jwt -> {
            if (jwt.getAudience().contains(audience)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                    "invalid_token",
                    "JWT is missing the required audience",
                    null));
        };

        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                standardValidators, requiredAudience));

        return decoder;
    }
}
~~~

Key takeaways from this example:

1. `withJwkSetUri(jwkSetUri)` selects the **trusted key endpoint**. The decoder verifies JWS with matching JWKs, never arbitrary keys embedded in the JWT by the caller.
2. `jwsAlgorithm(SignatureAlgorithm.RS256)` enforces the allowlist; it does not blindly trust the `alg` header.
3. `JwtValidators.createDefaultWithIssuer(issuer)` preserves standard validators including issuer and timestamp checks. Replacing all validators with a single audience lambda can **silently drop critical checks**.
4. `jwt.getAudience().contains(audience)` requires the `aud` list to include the expected audience; missing/`null` audience is represented as an empty list by Spring's `Jwt` accessor, leading to rejection.
5. `DelegatingOAuth2TokenValidator` combines validators; the token must pass all of them.
6. Defining a custom `JwtDecoder` bean replaces Boot's auto-configured decoder. Always re-test issuer/time/audience/algorithm checks when doing so.

For APIs with multiple audiences or per-endpoint policies, do not blindly allow all `aud` values hoping `hasAuthority` will compensate. Either separate Resource Servers or design clear validator/route boundaries, since a token meant for another resource may carry the same scope string.

### Adding Lifetime Limits and Required Claims

An API with stricter requirements can require `exp`, cap `exp - iat` (e.g., max 15 minutes), and forbid `iat` too far in the future. Clearly define **NumericDate seconds**, clock skew, and `Instant` types after Spring decodes them.

Illustrative snippet inside a custom `OAuth2TokenValidator<Jwt>` (not a standalone class):

~~~java
OAuth2TokenValidator<Jwt> lifetimePolicy = jwt -> {
    if (jwt.getIssuedAt() == null || jwt.getExpiresAt() == null) {
        return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                "invalid_token", "iat and exp are required", null));
    }

    long lifetimeSeconds =
            java.time.Duration.between(
                    jwt.getIssuedAt(), jwt.getExpiresAt()).getSeconds();

    if (lifetimeSeconds <= 0 || lifetimeSeconds > 900) {
        return OAuth2TokenValidatorResult.failure(new OAuth2Error(
                "invalid_token", "Token lifetime is outside policy", null));
    }

    return OAuth2TokenValidatorResult.success();
};
~~~

Add this validator to `DelegatingOAuth2TokenValidator` **alongside** standard issuer/timestamp and audience validators, rather than replacing them. Enforcing a max token lifetime is an **additional policy**, not applied to all JWTs by default.

## 10. Testing: Make Sure Invalid Tokens Are Rejected

A solid test suite must include both **positive cases** and **negative cases** using tokens signed by controllable test keys/issuers. A reliable approach is setting up a **test authorization server** or JWS fixtures with a test private key, fixed public JWKS, and controllable clock. Never put production private keys in source or tests.

### 10.1. Mandatory Test Matrix

| Test Case | Fixture Variation | Expected Result |
| --- | --- | --- |
| **T01 — valid** | RS256 signed with key in JWKS, valid `iss`, `aud`, `nbf`/`exp`, has `orders.read` | Authenticated + HTTP 200 |
| **T02 — tampered payload** | Keep old signature, modify `sub` or `scope` | **401** due to signature mismatch |
| **T03 — wrong private key** | Token signed with a key absent from trusted JWKS | **401** |
| **T04 — fake kid** | `kid` not present in issuer's JWKS | **401** when unverified |
| **T05 — alg none** | Header changed to `alg=none`/signature stripped | **401** |
| **T06 — disallowed alg** | `HS256`/`ES256` on an API allowing only RS256 | **401** |
| **T07 — wrong issuer** | Valid signature with test key, but `iss` differs from configured issuer | **401** |
| **T08 — missing issuer** | Token omits `iss` when policy requires it | **401** |
| **T09 — wrong audience** | `aud=urn:payments-api` | **401** |
| **T10 — missing audience** | No `aud` when API requires it | **401** |
| **T11 — multiple audiences** | `aud=["urn:orders-api","urn:analytics-api"]`, allowed by policy | Passes audience check, still checks scope |
| **T12 — expired exp** | Verification time past `exp` beyond skew | **401** |
| **T13 — future nbf** | `nbf` in the future beyond skew | **401** |
| **T14 — clock skew boundary** | Token expired by a few seconds, per skew config | Outcome matching documented policy |
| **T15 — future iat / long TTL** | Violates custom lifetime policy if enabled | **401** when custom policy applies |
| **T16 — missing scope** | Signature/iss/aud/time all valid, missing `orders.read` | **403** from authorization |
| **T17 — ID token** | ID token from same issuer, `aud` is client ID | **401** due to audience/type policy |
| **T18 — JWKS rotation** | Issuer publishes new key then retires old key on schedule | Valid tokens work during overlap; retired key stops being trusted after refresh |
| **T19 — JWKS outage** | JWKS endpoint down with warm/cold cache | Behavior per cache/error policy; unverified tokens never accepted |
| **T20 — empty Bearer token** | Missing token or malformed header | No authenticated principal created |

HTTP status codes in the table reflect typical expectations for a Spring Security resource server protecting an endpoint; custom entry points, exception handlers, and gateways may alter the final response. What matters is **never creating a valid Authentication** for tokens violating signature/issuer/audience/time rules.

### 10.2. Why Not Test Signatures by Just Mocking Jwt?

In Spring Security Test, `jwt()` in MockMvc **pre-builds an Authentication** and skips running the decoder that verifies signature/issuer/audience/time. It is great for testing authorization rules like `hasAuthority`, yet **does not prove** the API rejects tampered or expired tokens. To test the decoder and Bearer filter, send **raw signed JWTs** over HTTP or call `JwtDecoder.decode(rawToken)` with test JWKS/keys and production-like validators.

Distinguish:

- **Claim validator unit test:** uses a mock `Jwt` built in test, checking `JwtValidators` or custom audience validators.
- **Decoder integration test:** uses a raw JWS with test keys, checking signature, alg, issuer, audience, and exp/nbf.
- **End-to-end HTTP test:** exercises `SecurityFilterChain` receiving a Bearer header, verifying 401/403/200 and JWKS rotation/caching where needed.

Relying only on `jwt.getAudience()` unit tests misses vulnerabilities like "forgot to enable signature verification."

### 10.3. Diagnostic JWT Inspection Tool — No Verification

To see the difference between **decoding** and **verifying**, the Java 17 program below only prints the first two Base64url JSON parts of a JWS. It **intentionally skips signature verification** and must never be used as authentication logic.

Standalone file `JwtPeek.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;

public class JwtPeek {
    public static void main(String[] args) {
        if (args.length != 1) {
            System.err.println("Usage: java JwtPeek <test-jws>");
            System.exit(2);
        }

        String[] parts = args[0].split("\\.", -1);
        if (parts.length != 3) {
            throw new IllegalArgumentException(
                    "Expected JWS compact token with 3 parts");
        }

        Base64.Decoder decoder = Base64.getUrlDecoder();
        String header = new String(
                decoder.decode(parts[0]), StandardCharsets.UTF_8);
        String claims = new String(
                decoder.decode(parts[1]), StandardCharsets.UTF_8);

        System.out.println("UNVERIFIED HEADER: " + header);
        System.out.println("UNVERIFIED CLAIMS: " + claims);
        System.out.println("SIGNATURE NOT VERIFIED");
    }
}
~~~

Compile and run with Java 17+:

~~~bash
javac --release 17 JwtPeek.java
java JwtPeek '<test-jws-created-by-your-test-issuer>'
~~~

For example, when given an input encoding the two JSON fixtures from section 1, it prints the decoded JSON and the final line:

~~~text
SIGNATURE NOT VERIFIED
~~~

This warning line is always printed whenever the three-part/Base64url syntax is valid; the two JSON lines depend on the input. **Do not run with production JWTs if tools log output or the machine is untrusted**, as payloads may contain sensitive data. This program does not verify signature, issuer, audience, or expiration; its sole purpose is to prove that "readable payload" is not "valid token."

### 10.4. Modifying Tokens Properly in Tests

You cannot "edit a claim and keep the same signature" to produce a valid token. Maintain three types of fixtures:

1. **Modified without re-signing**: e.g., change `scope` from `orders.read` to `orders.admin` in the payload while keeping the old signature. Tests must reject at the signature step.
2. **Validly re-signed with a test private key**: change `iss`, `aud`, `exp`, or `nbf` in the fixture, then re-sign with the trusted JWKS test key. This isolates claim validation because the signature is valid.
3. **Different key/algorithm**: mint a token signed with a key outside the JWKS, or an algorithm not in the allowlist, to test signature/key selection.

If all negative tests use tokens with broken signatures, the test suite only proves the signature verifier ran—not that **issuer/audience/time validators** actually work.

## 11. Distinguishing 401 and 403

| Scenario | Typical Output | Handling Layer |
| --- | --- | --- |
| No Bearer token on protected endpoint | 401 | Entry point: unauthenticated |
| Expired token, bad signature, invalid issuer/audience | 401, often with Bearer `invalid_token` | JWT decoding/authentication |
| Valid token, missing `SCOPE_orders.read` | 403, often `insufficient_scope` or access denied | Authorization |
| Valid token, sufficient permissions, controller executes | 200 | Business endpoint |

Local testing example:

~~~bash
curl -i http://localhost:8080/api/orders/ping
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
  http://localhost:8080/api/orders/ping
~~~

Never put raw tokens, signatures, or full Authorization headers into logs or app metrics. For an invalid token, you can return a summary error `invalid_token` in the response while keeping controlled internal error-category details for debugging. If the system uses an API Gateway, HTTP statuses may be returned by the gateway before the request reaches Spring.

## 12. Common Errors and How to Fix Them

| Symptom | Common Cause | What to Check |
| --- | --- | --- |
| JWT parses, yet anyone can log in | Only Base64-decoding and trusting payload | Enforce `JwtDecoder`/JWS verification before trusting claims |
| `alg=none` or RS256→HS256 still accepted | Algorithm not restricted, buggy verifier | Enforce allowlist/key type, use standard library |
| Token for another app can call this API | Missing audience validation | Configure `jwt.audiences` or an audience validator |
| Token from another realm is accepted | Missing issuer validator or dynamic issuer trust | Pin `issuer-uri`/`JwtIssuerValidator` and per-issuer JWKS |
| Expired token still accepted | Missing `JwtTimestampValidator`, excessive skew, or wrong clock | Verify default validators and NTP sync |
| Newly issued token rejected for `nbf` | Clock drift between IdP and API | Compare UTC clocks, use only small skew |
| `JWT signature invalid` | Wrong JWKS, rotated key, tampered token, or wrong algorithm | Check issuer/JWKS, `kid`, algorithm, cache cycle |
| `Unable to resolve JWK` | Missing `kid`, JWKS error/timeout, or wrong URL | Check configured endpoint, TLS, cache, and key rotation |
| Token authenticates, returns 403 | Missing `SCOPE_orders.read` authority | Check `scope`/`scp` mapping and `hasAuthority` rule |
| Valid token fails when custom `JwtDecoder` is added | Custom bean replaced Boot auto-config, dropping standard validators | Register `JwtValidators.createDefaultWithIssuer` and audience validator |
| Tests green, yet fake tokens enter production | Only mocking `Jwt`, never testing raw JWS | Add decoder/integration tests with real test keys and JWKS |
| JWT leaked via logs/URLs | Placing Bearer in query strings, request logs, or screenshots | Use HTTPS Authorization header, redact logs, limit TTL |

### JWKS Rotation and Availability

- When the issuer publishes a new key, the JWKS may hold both old and new keys during the transition window.
- Still-valid tokens signed with the old key may need verification until they expire; the issuer and API must coordinate key publication and removal windows.
- Resource Servers typically cache JWKS per decoder behavior; verify TTL/refresh behavior during key rotation. Never cache revoked keys indefinitely.
- When the JWKS endpoint loses connectivity, tokens signed with valid cached keys may still verify depending on cache state, yet **you must not trust a new token lacking a verification key**.
- JWKS must be fetched from a fixed configured endpoint over valid HTTPS with appropriate timeouts and monitoring. Never open SSRF vectors via `jku` or `kid`.

### Premature JWT Revocation

Signed JWTs are typically verified offline, so there is no built-in "has the user logged out?" check. A validly signed, unexpired token can still be accepted after logout unless a dedicated revocation mechanism exists. Architecture options include short TTLs, server-side session/token status checks, a `jti` denylist, introspection, or account-lock/issuer-rotation policies. Do not confuse **checking `exp`** with **supporting immediate revocation**.

## 13. Design and Acceptance Process

Before shipping JWT Bearer authentication to production, align on:

1. **Issuer and token profile:** which issuer must mint tokens, is it a standard OAuth2 access token or custom JWT, and which claims are mandatory?
2. **Keys and algorithms:** trusted JWKS URI, key rotation process, algorithm allowlist, and matching key types.
3. **Audience:** canonical Resource Server identifier, whether multiple audiences are allowed, and how ID tokens are rejected.
4. **Lifetimes:** require `exp`, handle `nbf` and `iat`, clock sync, small clock skew, and max TTL if needed.
5. **Permissions:** map `scope`/`scp` to `GrantedAuthority`, and enforce matching `hasAuthority` rules.
6. **Security testing:** prove both valid tokens and negative cases (signature/key/algorithm/issuer/audience/expiry/not-before).
7. **Operations:** HTTPS, Bearer token hygiene, JWKS caching/rotation, safe logging, minimal error disclosure, and revocation if required.

### Quick Checklist

- [ ] Never trust a JWT just because Base64 decoding yields readable JSON.
- [ ] Reject bad signatures, untrusted keys, `alg=none`, and non-allowlisted algorithms.
- [ ] JWKS endpoint and issuer come from trusted config, never from URLs inside the token.
- [ ] `iss` must match the issuer; `aud` must contain the expected API/resource ID.
- [ ] `exp` and `nbf` are checked, clocks are synced, and skew is bounded.
- [ ] `iat` is distinguished from expiration, with an extra lifetime policy if needed.
- [ ] Custom `JwtDecoder` retains default issuer/time validators.
- [ ] Scopes/roles are derived only after JWT validation; 401 differs from 403.
- [ ] Decoder is tested with raw signed JWTs and test JWKS, beyond MockMvc tests with mocked Authentication.
- [ ] Rotation and JWKS outages are handled, and tokens never appear in logs or URLs.

## 14. Review Questions

1. Why is simply decoding the three JWT segments and reading `scope=orders.read` dangerous?
2. How does `kid` help select a key? Should you automatically fetch a URL from the token's `jku`?
3. A token has a valid RS256 signature, is unexpired, and has the right issuer, yet `aud=urn:payments-api`. How does the Orders API handle it?
4. A token has `exp` in the past, while `iat` is very recent. Should it be accepted?
5. What is the difference between `exp`, `nbf`, and `iat`? Is NumericDate in seconds or milliseconds?
6. Why does pinning allowed algorithms defend against `alg=none` and algorithm confusion?
7. When customizing `NimbusJwtDecoder`, which default validators must be kept and how is audience added?
8. If a client is authenticated yet lacks `SCOPE_orders.read`, which HTTP error group should the API return?
9. Why does a MockMvc `jwt()` unit test not prove that signature verification works?
10. If the JWKS has a new key while old tokens remain unexpired, how should rotation be coordinated?

**Reference answers:** (1) Base64 does not prove integrity or authenticity; (2) selects a key from the trusted issuer's JWKS, never trust token-supplied URLs; (3) reject; (4) no, if past `exp` beyond skew; (5) expiration, not-before, and issued-at, in Unix UTC seconds; (6) accepts only specified algorithms and matching key types; (7) issuer + timestamp plus audience validator; (8) 403 forbidden / insufficient permission; (9) it mocks Authentication, so the decoder may not run; (10) keep the old key for the overlap window, publish the new key early, tune caching, and remove the old key per policy.

## 15. References

- [Spring Security 6.5 — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html)
- [Spring Boot 3.3 — Resource Server/JWT issuer and audiences](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html)
- [Spring Security — Bearer Token Authentication](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/bearer-tokens.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
