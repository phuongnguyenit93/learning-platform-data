# Configuring `jwk-set-uri` Directly While Still Validating the Issuer

When deploying a **Spring Security OAuth 2.0 Resource Server** to accept **JWT Bearer Access Tokens**, the application usually declares `issuer-uri` so Spring Security discovers the Authorization Server metadata and thereby determines where to fetch public keys. However, some systems already know the **JWK Set URI** beforehand, or want the Resource Server to start up without running the **issuer discovery** step. In that case, you can **configure `jwk-set-uri` directly**.

The single most important point of this lesson is: **knowing where to fetch signature verification keys is not the same as verifying that the JWT was issued by the right issuer**. Configuration must preserve both constraints:

1. **Trusted signing keys**: fetched from the configured JWK Set URI.
2. **Trusted issuer**: the JWT's **`iss`** claim must match exactly the issuer accepted by the Resource Server.

Additionally, a real API must check **audience**, token lifetimes, and access scopes. This lesson clearly explains the two properties `issuer-uri` and `jwk-set-uri`, the difference between Spring Boot auto-configuration and manually constructing **NimbusJwtDecoder**, along with implementation, operations, and testing examples.

The examples use Spring Boot 3.x, Spring Security 6.x, Java 17+, and the Servlet API. URIs in the lesson use the illustrative domain `example.test` and must be replaced with real issuer/JWKS values in deployment.

## 1. Issuer and JWK Set URI Solve Two Different Problems

Suppose the application has an orders management API that accepts tokens only from an Authorization Server belonging to realm **demo**:

~~~text
Trusted issuer:
  https://login.example.test/realms/demo

Trusted JWKS endpoint:
  https://login.example.test/realms/demo/protocol/openid-connect/certs

Resource Server audience:
  orders-api
~~~

The **Issuer URI** is the identifier of the token publisher; the **JWK Set URI** is the HTTP(S) address returning keys as a JSON Web Key Set for the Resource Server to verify token signatures. An issuer can publish its JWK Set through OIDC/OAuth 2.0 metadata, yet the issuer URI and the JWK Set URI are **not the same kind of address**.

| Component | Question it answers | Typical data |
| --- | --- | --- |
| **`issuer-uri`** | “Was the JWT issued by the exact publisher I trust?” | `https://login.example.test/realms/demo` |
| **`jwk-set-uri`** | “Where do I fetch public keys to verify the JWT signature?” | `https://login.example.test/realms/demo/protocol/openid-connect/certs` |
| **`aud` validator** | “Was the JWT issued for my API?” | `orders-api` |
| **`exp` / `nbf` validators** | “Is the token already active and not yet expired?” | `NumericDate` in JWT |
| **Authorization rules** | “Does the valid token have permission to call the API and access this record?” | `SCOPE_orders.read`, per-tenant policy |

A JWT with a valid signature under a public key in the JWK Set can still be rejected if **`iss` is wrong**, **`aud` does not contain the API**, it is expired, or it lacks permissions. Therefore, “keys loaded successfully” is only one step in authentication.

## 2. JWT, JOSE, and JWK Set in a Request

A compact JWS JWT Access Token typically has three parts:

~~~text
BASE64URL(header).BASE64URL(claims).BASE64URL(signature)
~~~

Illustrative header and payload:

~~~json
{
  "alg": "RS256",
  "kid": "rsa-signing-2026-01",
  "typ": "at+jwt"
}
~~~

~~~json
{
  "iss": "https://login.example.test/realms/demo",
  "sub": "employee-123",
  "aud": ["orders-api"],
  "iat": 1893452400,
  "nbf": 1893452400,
  "exp": 1893456000,
  "scope": "orders.read"
}
~~~

The **JOSE Header** provides information such as algorithm `alg` and key ID `kid`. The **Claims Set** contains `iss`, `aud`, `exp`, and the issued claims. The JSON above is illustrative only, **not a validly signed token**.

To validate an RS256 token:

1. The Resource Server receives the **`Authorization: Bearer <token>`** header.
2. Spring Security passes the token to **`JwtDecoder`**, typically **`NimbusJwtDecoder`**.
3. The decoder finds the matching public key in the JWK Set. `kid` helps pick the key, but on its own is **not proof of trust**.
4. The decoder verifies the signature using the algorithm configured as permitted.
5. Validators check **issuer, lifetime, audience**, and any extra constraints.
6. Spring Security converts scopes into authorities and evaluates endpoint access permissions.

A JWS-formatted JWT **is signed, not encrypted by default**: anyone holding the token can read the payload via Base64url. Do not place secrets or unnecessary personal data in tokens, and never log Bearer tokens in URLs, logs, or error messages.

## 3. When Only `issuer-uri` Is Configured: How Does Discovery Work?

Common configuration in `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
~~~

With an issuer URI configured, Spring Security can discover **Authorization Server metadata** or **OIDC Provider metadata** at the appropriate well-known endpoints. The metadata document contains **`issuer`** and **`jwks_uri`**:

~~~json
{
  "issuer": "https://login.example.test/realms/demo",
  "jwks_uri": "https://login.example.test/realms/demo/protocol/openid-connect/certs"
}
~~~

The system then knows the address hosting the public keys to verify JWTs. Overview of the flow:

~~~text
Resource Server
   |
   | configured issuer-uri
   v
OIDC/OAuth Authorization Server metadata
   |  issuer = ...
   |  jwks_uri = ...
   v
JWK Set endpoint
   |
   | public keys
   v
JWT signature verification
   |
   v
Validators: iss, exp, nbf, aud...
~~~

Depending on the Spring Security version and how the decoder is built, discovery may occur during decoder initialization, upon first use, or on demand. What matters architecturally is that **if the application requires discovery at startup, an unavailable issuer metadata endpoint can affect startup**. Where the JWK Set URI is known in advance, direct configuration eliminates the need for **discovering the JWK URI**, though it does not eliminate all network connectivity requirements to fetch keys.

Using only `issuer-uri` normally establishes the issuer check through Spring Boot/Spring Security's auto-configuration. However, **audience should not be assumed to be validated automatically**, as that depends on specific properties or validators.

## 4. Configuring Both `issuer-uri` and `jwk-set-uri` Directly

This is the pattern to remember for a Spring Boot Resource Server where both the issuer and JWKS endpoint are managed beforehand.

### 4.1. `application.yml`

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

In Spring Boot versions supporting **`audiences`**, this configuration means:

- **`issuer-uri`**: the API accepts only JWTs whose `iss` claim matches the declared issuer.
- **`jwk-set-uri`**: the decoder knows right away where to fetch JWKs; no call to issuer metadata is needed just to find `jwks_uri`.
- **`audiences`**: the JWT must have an audience containing `orders-api`.
- The decoder still verifies signatures, lifetimes, and relevant default checks.

If your Spring Boot version does not support `audiences`, you must add an **audience validator** via a custom `JwtDecoder`; an unbound YAML key will not make tokens any safer.

### 4.2. Difference from Configuring Only `jwk-set-uri`

The two configurations below are **not equivalent** in terms of trust semantics.

**Configuration A — Both issuer and JWKS URI:**

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
~~~

When letting Spring Boot auto-configure the JWT Resource Server with both properties, the issuer is used to **validate `iss`**, while the JWK Set URI is used to fetch keys.

**Configuration B — Only JWKS URI:**

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          jwk-set-uri: https://login.example.test/realms/demo/protocol/openid-connect/certs
~~~

The decoder has a public key source to verify signatures, yet **no issuer is required by this configuration**. Do not assume it will automatically enforce the same `iss` rule as Configuration A. If declaring only `jwk-set-uri`, add an **explicit issuer validator** in Java or equivalent configuration.

This is an easy bug to miss because test tokens from the right issuer still pass, creating the illusion that issuer validation is working.

### 4.3. Comparison Table

| Criterion | Only `issuer-uri` | Only `jwk-set-uri` | Both |
| --- | --- | --- | --- |
| Where JWKS is fetched | Discovered from issuer metadata. | Declared URI. | Declared URI. |
| Needs issuer discovery to find JWKS | Yes. | No. | No. |
| Checks `iss` under default Boot config | Yes. | No trusted issuer specified. | Yes. |
| Signature verification | Yes, using discovered JWKs. | Yes, using JWKs at configured URI. | Yes, using JWKs at configured URI. |
| Checks `aud` for API | Needs config/validator. | Needs config/validator. | Needs config/validator. |
| Needs JWKS endpoint reachable during verification | Yes. | Yes. | Yes. |

**Technical conclusion:** When you want to skip metadata discovery while still validating the issuer, Spring Boot configuration **`issuer-uri` + `jwk-set-uri`** is the most direct choice. Supplying a direct JWKS URI is **no reason to omit issuer validation**.

## 5. What Is in a JWK Set and Why Must You Choose the Right Key Source?

A JWK Set is a JSON object with a **`keys`** field containing one or more JSON Web Keys. Example for RSA public keys (modulus values replaced with placeholders):

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "rsa-signing-2026-01",
      "use": "sig",
      "alg": "RS256",
      "n": "RSA_PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    },
    {
      "kty": "RSA",
      "kid": "rsa-signing-2026-02",
      "use": "sig",
      "alg": "RS256",
      "n": "SECOND_RSA_PUBLIC_MODULUS_BASE64URL",
      "e": "AQAB"
    }
  ]
}
~~~

Here:

- **`kty`** indicates the key type, such as RSA.
- **`kid`** distinguishes signing keys, useful during rotation.
- **`n`**, **`e`** are RSA public key parameters.
- **`use: sig`** indicates the key is intended for signing/verification.
- **`alg`** describes the corresponding algorithm per metadata; the decoder must still enforce its own trusted algorithm policy.

The `n` values in the example are not valid RSA moduli; this document does not supply real signing keys or tokens.

For RSA signatures, the **Authorization Server holds the private key**, while the Resource Server downloads the **public key**. A public JWKS must never contain private key parameters such as `d`. A Resource Server does not need a private signing key to verify tokens.

### 5.1. A Trusted JWK Endpoint Is a Security Boundary

When an API downloads public keys from a JWKS URI, it accepts that source as the **foundation for signature verification**. If the key source is swapped, an attacker can inject public keys they control and sign tokens with the corresponding private key.

Therefore:

1. Obtain the JWKS URI from **trusted managed configuration**, never freely from requests.
2. Use **HTTPS** with proper TLS verification.
3. Never automatically follow `jku` or `x5u` headers supplied by an unverified JWT.
4. Never choose a JWKS URI based on an unverified `iss` without a strict **issuer allowlist** mechanism.
5. Restrict accepted algorithms and key types per contract with the Authorization Server.
6. Never handle key-loading failures by skipping signature verification.

**`kid` is neither a secret nor an issuer attestation.** It mainly helps select a key inside a **JWKS already trusted by the Resource Server**.

## 6. Combining a Direct JWKS URI with `NimbusJwtDecoder`

Spring Boot auto-configuration suffices for many applications. When you need control over validators, algorithms, or caching, you can build a **`JwtDecoder`** yourself.

### 6.1. Java Configuration

The following example builds a decoder from a JWKS URI while **attaching an explicit issuer validator** and checking audience:

~~~java
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
public class JwtDecoderConfig {

    private static final String TRUSTED_ISSUER =
        "https://login.example.test/realms/demo";

    private static final String TRUSTED_JWKS =
        "https://login.example.test/realms/demo/protocol/openid-connect/certs";

    private static final String API_AUDIENCE = "orders-api";

    @Bean
    JwtDecoder jwtDecoder() {
        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(TRUSTED_JWKS)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
            if (jwt.getAudience().contains(API_AUDIENCE)) {
                return OAuth2TokenValidatorResult.success();
            }

            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error(
                    "invalid_token",
                    "JWT audience is not accepted",
                    null));
        };

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER),
                audienceValidator));

        return decoder;
    }
}
~~~

Key takeaways:

- **`withJwkSetUri(TRUSTED_JWKS)`** defines the key source; on its own it **does not specify the valid issuer**.
- **`jwsAlgorithm(SignatureAlgorithm.RS256)`** restricts the algorithm for an example Authorization Server signing with RS256. If the issuer uses ES256/RS512 or another algorithm, align and configure accordingly.
- **`JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER)`** adds issuer validation and default timestamp validators; not just signature checks.
- **`audienceValidator`** prevents tokens meant for another API from being used at `orders-api`.
- **`DelegatingOAuth2TokenValidator`** combines rules. When calling **`setJwtValidator`**, retain the default constraints in the new set so you do not accidentally drop `exp`, `nbf`, or `iss`.

This is **an alternative** to letting Spring Boot auto-create the decoder. If you define a **`JwtDecoder`** bean, Spring Boot typically backs off from auto-configuring one for your custom bean; in that case, do not assume the `audiences` YAML property still applies to that bean. Mandatory validators must be placed on the **actual decoder in use**.

In production, load issuer, JWKS URI, and audience from environment-managed configuration. Constants are used in the example only to make the flow easy to follow.

### 6.2. Common Mistake: A Decoder with Keys but No Issuer Validator

The snippet below is **not enough** to authenticate an API trusting a specific issuer:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    return NimbusJwtDecoder
        .withJwkSetUri("https://login.example.test/realms/demo/keys")
        .build();
}
~~~

The decoder can verify signatures with keys from the given endpoint, yet it cannot infer the API's issuer policy from that alone. Add **`JwtValidators.createDefaultWithIssuer(...)`** and, when needed, an audience validator as in the complete example above.

### 6.3. If You Only Want to Check the Issuer, Must You Write a Lambda Yourself?

You do not need to compare `jwt.getIssuer().toString()` manually in every application. Spring Security already provides **`JwtValidators.createDefaultWithIssuer(issuer)`** for a specific issuer. Using the built-in validator ensures proper semantics alongside the default checks.

You only need custom validators for conditions outside that set, for example:

- Mandatory audience containing `orders-api`.
- Mandatory `tenant_id` claim within an allowed domain.
- Authorization Server-specific token profile or custom claims.
- Stricter time policies if business requirements demand them.

Do not confuse **issuer validation** with **authorization**: a JWT with the right issuer but missing scopes must still be rejected at the protected endpoint.

## 7. Configuring `SecurityFilterChain` to Use That Decoder

Example API authenticating via Bearer header without session cookies:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth ->
                oauth.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

Spring Security will use the available `JwtDecoder` from Boot configuration or the declared bean. If the token lacks **`SCOPE_orders.read`**, a valid token will still be denied when GETting resources requiring that scope.

**Architectural notes:**

- **`STATELESS`** suits APIs authenticating each request with a Bearer Access Token.
- Disabling **CSRF** in the example applies only to pure Bearer-header APIs. If the same application serves a website using cookie/session login, design separate security chains and CSRF handling.
- Spring Security typically maps `scope` or `scp` claims into authorities prefixed with **`SCOPE_`**. Custom roles/permissions need a custom converter or policy.
- When the Authorization Server issues Access Tokens for multiple APIs, checking **`aud`** in the decoder must still be enforced per target API.

A valid request might look like:

~~~http
GET /api/orders/42 HTTP/1.1
Host: api.example.test
Authorization: Bearer ACCESS_TOKEN_FOR_ORDERS_API
Accept: application/json
~~~

In practice, an Access Token is a sensitive credential: never put real tokens into URLs, public docs, logs, or error responses.

## 8. The Issuer String: Exact Matching and Subtle Traps

A JWT's `iss` claim is typically a URI string, for example:

~~~json
{
  "iss": "https://login.example.test/realms/demo"
}
~~~

If the Resource Server configures a different issuer, such as:

~~~text
https://login.example.test/realms/demo/
~~~

then the trailing **/** difference can cause the issuer validator to reject the token. Do not arbitrarily “normalize” `iss` by stripping paths, lowercasing paths, or substituting hostnames to force a match. **The issuer identifier is a contract between Authorization Server and Resource Server**—take the exact value published by the issuer.

### 8.1. Reverse Proxies and Internal URLs

For example, the Authorization Server sits behind a reverse proxy with an internal URL:

~~~text
http://identity-service:8080/realms/demo
~~~

but publishes its official issuer as:

~~~text
https://login.example.test/realms/demo
~~~

The Resource Server must verify **`iss` against the token's official issuer**. It may fetch JWKS from a tightly governed internal URI when architecture demands it, yet using an internal route to fetch keys **does not mean changing `iss` to the internal URL**.

For example, if JWKS is served over an internal network with proper TLS:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/demo
          jwk-set-uri: https://identity-internal.example.test/realms/demo/certs
          audiences:
            - orders-api
~~~

The architecture above is safe only when the internal JWKS address is a **controlled key source matching that issuer**. Never treat any internal address as trusted simply because it resides on the corporate network.

### 8.2. Development, Staging, and Production Environments

Do not share a “virtual” issuer across all environments if the Authorization Server actually issues tokens with different `iss` values. For example:

| Environment | Issuer | JWKS |
| --- | --- | --- |
| Dev | `https://login-dev.example.test/realms/demo` | Dev endpoint of dev issuer |
| Staging | `https://login-staging.example.test/realms/demo` | Staging endpoint |
| Production | `https://login.example.test/realms/demo` | Production endpoint |

Each environment should have clear configuration and test tokens issued by the right issuer. Never point to production JWKS just to make dev tokens “pass signature verification”: issuer, audience, signing keys, and data boundaries must stay separated per organizational architecture.

## 9. Audience and Issuer Cannot Substitute for Each Other

Suppose the Authorization Server issues a JWT:

~~~json
{
  "iss": "https://login.example.test/realms/demo",
  "sub": "user-123",
  "aud": ["billing-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

Resource Server **`orders-api`** shares the same issuer as the token and has valid public keys. Yet `aud` contains only **`billing-api`**, so **`orders-api` must reject it**. Without audience constraints, tokens intended for one resource can be misused against another, even when both trust the same issuer.

Conversely, a token with `aud: ["orders-api"]` whose `iss` is an unknown issuer must also be rejected. The conditions are **independent and simultaneously mandatory per policy**:

~~~text
Successful JWT authentication result
       |
       +-- Valid signature with trusted key
       +-- Algorithm in permitted allowlist
       +-- iss == trusted issuer
       +-- aud contains orders-api
       +-- Valid exp/nbf
       +-- Token profile/type satisfies requirements (if applicable)
       |
       v
Authorization: check scopes, tenant permissions, and resource access
~~~

An **OIDC ID Token** typically has the login app's client ID as its audience, whereas an **OAuth Access Token** must match the API. A validly signed JWT from the right issuer **does not automatically turn an ID Token into an Access Token**.

## 10. Startup, Network, and Caching When Supplying `jwk-set-uri` Directly

### 10.1. No Discovery Does Not Mean Completely Offline

When declaring only `issuer-uri`, Spring Security needs a discovery mechanism to find the JWKS endpoint. When declaring `jwk-set-uri` directly, the application already knows where to fetch keys without looking it up in metadata.

This can reduce reliance on the **discovery endpoint at startup**. Still, JWTs require public keys:

- If the decoder does not yet have/cache the right public key, it must fetch it from the JWKS endpoint.
- If a new `kid` arrives, the decoder may need to refresh JWKS depending on cache policy.
- When the JWKS endpoint is unavailable and the decoder lacks the right verification key, the token must not be authenticated successfully.

**Do not** fall back to “reading claims while skipping signatures” when the key source temporarily loses connectivity.

### 10.2. Caching and Rotation

The Authorization Server can publish multiple JWKs over a transition period to rotate keys:

~~~text
T0: JWKS publishes key-A; Access Tokens signed with key-A
T1: JWKS publishes key-A and key-B
T2: New tokens signed with key-B; key-A tokens still valid
T3: Old key-A tokens expire or are handled per policy
T4: JWKS stops publishing key-A
~~~

Decoders and JOSE libraries typically cache the JWK Set to avoid re-fetching on every request. Cache lifetimes and refresh behavior depend on version/configuration. During rotation, ensure:

1. The new public key is published before or in time for signing new tokens.
2. Resource Server caches can refresh to pick up the new key.
3. The old key remains published long enough for still-valid tokens, except during emergency revocation.
4. Tokens with unknown keys are rejected when no trusted verification key can be found.

### 10.3. Failure Modes to Monitor

| Incident | Symptom | How to handle |
| --- | --- | --- |
| Discovery endpoint fails when using only issuer URI | Metadata init/discovery fails depending on discovery timing. | Check issuer URI, TLS, metadata; consider managed direct JWKS URI. |
| JWKS endpoint unreachable when key is needed | JWT requests may receive 401 or corresponding auth errors. | Check connectivity, TLS, caching, and endpoint availability; keep signature checks intact. |
| Issuer has wrong trailing slash or realm | Signature may be valid, yet JWT is rejected. | Compare `iss` published by the issuer with trusted configuration. |
| JWKS has new key, but cache has not refreshed | New JWTs with unfamiliar `kid` are rejected. | Review rotation plan, TTL/cache, and key publication schedule. |
| Token has wrong audience | Validly signed JWT is still rejected. | Check API audience and token issuance configuration. |
| Custom decoder overrides Boot auto-config | Issuer/audience validators lost if not re-attached. | Inspect the actual `JwtDecoder` bean in use. |
| Wrong algorithm or key type | JWT rejected even though JWKS endpoint is reachable. | Check agreed token profile, algorithm, and key type. |

Monitor 401/403 error counts, standardized error categories, and JWKS endpoint availability. Never write raw JWTs, Authorization headers, secrets, or sensitive stack traces into logs/metrics.

## 11. Testing That “Issuer Is Still Validated”

This is especially important to verify when migrating from discovery configuration to direct `jwk-set-uri`.

### 11.1. Test Matrix

| Token sent to `orders-api` | Signature / JWKS | Issuer | Audience | Expected result |
| --- | --- | --- | --- | --- |
| Valid token | Right key | Valid | `orders-api` | Passes authentication; still checks scopes. |
| Token with same key but different issuer | Right key | **Wrong** | `orders-api` | **401** if API checks issuer. |
| Token with right issuer but different audience | Right key | Valid | **Wrong** | **401** if API checks audience. |
| Token signed with unknown private key | **Wrong** | Valid | `orders-api` | **401**. |
| Expired token | Right key | Valid | `orders-api` | **401**. |
| Valid token missing `orders.read` | Right key | Valid | `orders-api` | **403** on GET requiring that scope. |
| No Bearer token | None | — | — | **401** on protected endpoint. |

You must have a **test with a wrong issuer yet valid signature**. If you only use an invalid signature when testing 401, you have not proven the issuer validator is active: the request may be rejected at the signature step before `iss` is ever checked.

### 11.2. Testing Authorization with MockMvc Differs from Testing the Decoder

Spring Security Test provides `jwt()`:

~~~java
mockMvc.perform(get("/api/orders/42")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

This pattern helps test authorization because `jwt()` creates an already-authenticated `Authentication` for the request. **It does not send a real signed JWT through `NimbusJwtDecoder`**, so it does not prove issuer/JWKS validation works. Passing a wrong `iss` into `jwt()` and seeing 200 is not necessarily a decoder bug; the decoder is not invoked in that test.

To test the actual validators:

- Generate a **test-only RSA key pair**.
- Sign JWTs with the test private key.
- Set up a JWKS fixture returning the test public key.
- Build a decoder using `withJwkSetUri` pointing to the local JWKS, with validator `createDefaultWithIssuer`.
- Test both a right-issuer JWT and a wrong-issuer JWT **signed with the exact same test private key**.

### 11.3. Example Testing the Validator with a Test RSA Key

The JUnit 5 snippet below illustrates testing the **issuer validator** with real signed JWTs. It uses `withPublicKey` to avoid HTTP in a unit test, whereas production uses `withJwkSetUri`. The `iss` check via the validator is equivalent, though **this test does not yet verify fetching JWKS over HTTP**.

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class TrustedIssuerDecoderTest {

    private static final String TRUSTED_ISSUER =
        "https://login.example.test/realms/demo";

    private KeyPair keyPair;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void initialize() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        keyPair = generator.generateKeyPair();

        decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) keyPair.getPublic())
            .build();

        OAuth2TokenValidator<Jwt> audience = jwt ->
            jwt.getAudience().contains("orders-api")
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(
                        "invalid_token", "Wrong audience", null));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(TRUSTED_ISSUER),
                audience));
    }

    private String signedJwt(String issuer) throws Exception {
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("employee-123")
            .audience("orders-api")
            .issueTime(Date.from(Instant.now().minusSeconds(60)))
            .expirationTime(Date.from(Instant.now().plusSeconds(600)))
            .claim("scope", "orders.read")
            .build();

        SignedJWT jwt = new SignedJWT(
            new JWSHeader(JWSAlgorithm.RS256), claims);
        jwt.sign(new RSASSASigner(
            (RSAPrivateKey) keyPair.getPrivate()));
        return jwt.serialize();
    }

    @Test
    void correctIssuerIsAccepted() throws Exception {
        Jwt actual = decoder.decode(signedJwt(TRUSTED_ISSUER));
        assertEquals("employee-123", actual.getSubject());
    }

    @Test
    void wrongIssuerWithValidSignatureIsRejected() throws Exception {
        String token = signedJwt(
            "https://untrusted.example.test/realms/other");
        assertThrows(JwtException.class, () -> decoder.decode(token));
    }
}
~~~

**Why is this test meaningful?** Both JWTs are signed with the same private key, and the decoder has the matching public key. Therefore, if the token with the unfamiliar issuer is rejected, the reason lies in **claim validation**, not just a bad signature.

To test the **exact direct JWKS URI configuration**, start a local test HTTP server serving a JWK Set with the test public key, configure `NimbusJwtDecoder.withJwkSetUri(localJwksUri)`, and run the same two scenarios again. Also test JWKS missing the matching `kid`, rotated keys, and endpoint failures.

### 11.4. Testing the Real HTTP Path

An integration test with the Resource Server must send the JWT string in an HTTP header:

~~~http
GET /api/orders/42 HTTP/1.1
Host: localhost:8080
Authorization: Bearer JWT_SIGNED_BY_TEST_KEY
~~~

Test flow:

~~~text
JUnit/Test fixture
   |
   +-- test private key signs JWT
   |
   +-- local JWKS endpoint publishes test public key
   |
   v
MockMvc / HTTP test sends Authorization: Bearer ...
   |
   v
BearerTokenAuthenticationFilter
   |
   v
NimbusJwtDecoder.withJwkSetUri(local JWKS)
   |
   +-- verify signature
   +-- validate issuer
   +-- validate audience, exp, nbf
   v
Authorization rule -> 200 / 401 / 403
~~~

Local tests are helpful because they avoid network/production Authorization Server dependencies. Never put real tokens or real private signing keys into test fixtures. If the application uses multiple issuers or specialized JWK Sets, also test allowlist-based issuer routing, key selection, and caching/rotation.

## 12. Multiple Issuers and the Limits of a Single `jwk-set-uri`

A Resource Server may need to accept tokens from multiple tenants or Authorization Servers. Do not solve this by pointing to one JWK Set and **omitting `iss` validation** to “accept all tenants”.

For example:

~~~text
Tenant A: issuer https://login-a.example.test
          JWKS   https://login-a.example.test/keys

Tenant B: issuer https://login-b.example.test
          JWKS   https://login-b.example.test/keys
~~~

You need a mechanism mapping **permitted issuer → corresponding decoder/JWK source/validators**. In Spring Security Servlet, mechanisms such as **JwtIssuerAuthenticationManagerResolver** exist for certain multi-issuer models, provided the list of trusted issuers is explicitly managed.

An unverified JWT can supply `iss` to **help choose a verification branch**, but that is purely **routing**. It does not make the issuer trustworthy; the resolver must still enforce an allowlist and the decoder must re-verify both signature and `iss` after choosing the branch.

~~~text
Bearer JWT
  |
  v
Read iss to determine branch (claim not yet trusted)
  |
  v
Issuer in allowlist?
  | No                    | Yes
  v                       v
Reject             Select trusted decoder
                          |
                          v
               Verify signature + issuer
                          |
                          v
                   Audience + lifetime
                          |
                          v
                      Authorization
~~~

If issuer A and issuer B use the `roles` claim with different semantics, the API also needs per-issuer policies/claim converters. Never apply uniform permissions merely because tokens share `roles: ["ADMIN"]`.

## 13. Diagnosing Why a JWT Returns 401 When JWKS Is Configured Directly

When a JWT is not accepted, analyze each trust boundary in order:

| Symptom | What to confirm | Adjustment |
| --- | --- | --- |
| API starts up but cannot fetch keys | Are DNS/TLS/firewall/JWKS URI correct? | Fix connectivity or managed URI; never disable verification. |
| JWT has valid signature but returns 401 | Is `iss` exact? Trailing slash? Right `aud` for API? Expired token? | Compare verified claims against configuration. |
| JWT with wrong issuer is still accepted by API | Was an issuer validator omitted when configuring only JWKS URI? | Add `issuer-uri` or `createDefaultWithIssuer` on the actual decoder. |
| JWT has right issuer, but new JWKS has a different key | Are `kid`, key type, algorithm, and rotation compatible? | Inspect JWKS, cache, and token signing policy. |
| Token meant for another API is still accepted | Is audience validation missing? | Add `audiences` or custom audience validator and negative tests. |
| Valid token, yet endpoint returns 403 | Are authorities/scopes sufficient? | Inspect `scope`/`scp`, `SCOPE_` mapping, and resource permissions. |
| Behavior changes after adding a `JwtDecoder` bean | Did it override Boot auto-configuration? | Configure all required validators on the custom bean. |

**Do not** paste real Access Tokens into online decoding tools or full logs. When investigating, use mock/fixture tokens, standardized error codes, server-generated trace IDs, and safe-to-display configuration details. JWKS public keys may be published to verify signatures, but never log or expose private signing keys.

### 13.1. Do Not Confuse 401 and 403

For a typical JWT Resource Server:

- **401 Unauthorized**: no valid Bearer token, or signature, issuer, audience, expiration, or another authentication requirement failed.
- **403 Forbidden**: token is authenticated, yet lacks sufficient scopes/roles or permissions required by the endpoint.

When customizing error responses, preserve the HTTP status code and **`WWW-Authenticate: Bearer`** header appropriately; do not reflect raw JWTs, raw exceptions, or signing key details in error responses.

## 14. Misconceptions to Avoid

1. **“Configuring `jwk-set-uri` automatically knows the issuer.”** False: the key source only verifies signatures; issuer requires its own validator or combined configuration.
2. **“Declaring both URIs forces discovery.”** When the JWKS URI is known directly, metadata discovery is not needed just to find JWKS; fetching keys may still depend on the network.
3. **“A validly signed JWT is definitely meant for this API.”** Audience validation is required; the token may be meant for another API.
4. **“JWKS can be chosen by the client from the token header.”** That introduces key-substitution risk; the URI must come from trusted configuration.
5. **“The issuer is the JWKS host.”** The issuer identifier can differ from the hostname/path of the key-fetching endpoint; validate `iss` per the token-issuing contract.
6. **“Having the right scope means you can ignore the issuer.”** Scope describes permissions; it does not prove the token came from a trusted issuer.
7. **“Even after adding a `JwtDecoder` bean, Boot still attaches all YAML validators.”** A custom bean can replace the auto-configured decoder; validator setup must be verified on the real decoder.
8. **“A JWK key stays valid forever without rotation.”** Keys can rotate; plan for distribution, caching, and JWK Set refreshing.
9. **“MockMvc testing with `jwt()` proves issuer validation.”** That helper creates a mocked `Authentication` and bypasses JWT signature verification.
10. **“If JWKS errors, we can let requests through to avoid downtime.”** A token that cannot be verified per policy must be rejected.

## 15. Checklist for Applying This to a Project

1. Confirm from the Authorization Server the **official issuer identifier** and **trusted JWKS endpoint**, never inferring them from unverified tokens.
2. Confirm tokens are issued for the API with the right **audience** and **scopes**, appropriate lifetimes, and algorithms.
3. If using Boot auto-configuration, declare **both `issuer-uri` and `jwk-set-uri`**; add **`audiences`** on supported versions.
4. If building **`NimbusJwtDecoder.withJwkSetUri`** manually, call **`setJwtValidator`** with **`JwtValidators.createDefaultWithIssuer`** and an audience validator.
5. Configure **`SecurityFilterChain`** for Bearer authentication and authorization by endpoint, HTTP method, tenant, and resource.
6. Test a **wrong issuer with a valid signature** to prove issuer validation was not forgotten; also test wrong audience, expiration, unknown key, and missing scope.
7. Prepare operations for **JWKS caching/rotation**, connection errors, TLS, and safe logging; never disable verification when JWKS is temporarily unavailable.

**Key takeaway:** With Spring Security Resource Server, configuring **`jwk-set-uri`** directly solves where to fetch public keys; keeping **`issuer-uri`** or an explicit issuer validator ensures the JWT came from a trusted publisher. Both conditions must be combined with **audience, lifetime, and authorization** to protect the API as intended.

## References

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — NimbusJwtDecoder API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html).
- [Spring Boot — OAuth 2.0 Resource Server configuration](https://docs.spring.io/spring-boot/reference/web/spring-security.html).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414).
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html).
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
