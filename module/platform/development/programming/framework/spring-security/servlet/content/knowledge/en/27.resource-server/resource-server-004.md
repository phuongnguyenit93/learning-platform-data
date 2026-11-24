# JWT in Spring Security Resource Server: Signature, Issuer, Lifetime, and Audience

> **Scope:** Spring Security **Servlet** 6.x (typically Spring Boot 3.x, Java 17+), with the application acting as an **OAuth 2.0 Resource Server** receiving JWT access tokens via HTTP `Authorization: Bearer …`. This lesson focuses on signature verification and four trust boundaries: **issuer (`iss`), lifetime (`exp`/`nbf`), and audience (`aud`)**. This is the API access token authentication mechanism; do not assume it applies identically to ID tokens, opaque tokens, or Spring WebFlux.

## 1. Why Is a Valid Signature Still Not Enough?

Suppose a system has two APIs, `orders-api` and `payments-api`, both trusting the same token-issuing server. Someone holding a valid access token to call `orders-api` must not necessarily be allowed to use that token to call `payments-api`, even when the signature is valid. Similarly, tokens issued by another system, expired tokens, or not-yet-valid tokens must all be rejected.

A Resource Server must ask four independent questions:

1. **Signature:** Was the JWT genuinely signed with a trusted key for the configured mechanism and algorithm?
2. **Issuer:** Who issued the token, and does `iss` **match exactly** the trusted issuer?
3. **Lifetime:** Is the token within an acceptable time window, specifically per `exp` and `nbf`?
4. **Audience:** Was the token issued **specifically for this API**, or intended for another API/client?

Afterward come separate decisions: scope/role, resource access rights, tenant, token type, revocation, and application policy. **Passing JWT validation does not automatically mean the caller is allowed to perform every action.**

## 2. What Is a JWT, and Where Is the Trustworthy Proof?

JWT (JSON Web Token) is a format carrying claims as JSON. The common access token case is a **signed JWT (JWS)** consisting of three dot-separated parts:

~~~text
base64url(JWS protected header)
  .
base64url(JWT claims payload)
  .
base64url(signature)
~~~

**Illustrative** header and payload examples—not real tokens to copy and use:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "signing-key-2026-01"
}
~~~

~~~json
{
  "iss": "https://identity.example.test/realms/acme",
  "sub": "user-123",
  "aud": ["orders-api"],
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600,
  "scope": "orders.read orders.write"
}
~~~

- `alg`: signing algorithm declared by the JWS; the backend must **restrict trusted algorithms** and verify the real signature, not blindly trust the `alg` string.
- `kid`: hint for selecting the verification key from the key set the backend **already trusts**. `kid` is not permission for a client to point to an arbitrary key server.
- `iss`: issuer, usually the URL identifying the authorization server.
- `sub`: subject assigned by the issuer; not proof of access rights on its own.
- `aud`: set of audiences the token is intended for; the Resource Server checks for the API's audience.
- `iat`: issued-at timestamp. It **does not replace** `exp` and does not automatically block overly old tokens.
- `nbf`: token must not be used before this time (not before), if present.
- `exp`: expiration timestamp.
- `scope` or `scp`: permissions granted by the issuer, after the token passes trust checks.

**Base64URL is not security encryption.** Anyone holding a JWT can usually decode its header and payload to read claims. The signature protects **integrity and origin**, not data confidentiality. Never put passwords, session secrets, or unnecessary sensitive data in the payload. Encrypted JWTs (JWE) are a separate mechanism, and Spring Resource Server under standard signed-JWT configuration does not automatically decrypt JWE.

### Treating a JWT as a Credential Carrying Authority

Possessing a Bearer JWT is usually sufficient to call an API while the token remains valid and holds matching permissions. Therefore, use HTTPS, never put tokens in query strings, avoid logging raw `Authorization` headers, and avoid storing tokens in exposed locations. A JWT whose `scope`/`aud` claims were altered and re-encoded by a client will **no longer have a valid signature** if the server properly verifies against the right key.

## 3. How Does Spring Security Servlet Process Bearer JWTs?

The primary configuration is `oauth2ResourceServer(oauth2 -> oauth2.jwt(…))`. When a request hits a protected endpoint:

~~~text
Client
  |
  | Authorization: Bearer <JWT>
  v
Servlet FilterChainProxy / SecurityFilterChain
  |
  v
BearerTokenAuthenticationFilter
  |
  v
AuthenticationManager / JwtAuthenticationProvider
  |
  v
JwtDecoder (typically NimbusJwtDecoder)
  |   1. Parse JWS
  |   2. Verify signature using trusted key and allowed alg
  |   3. Run OAuth2TokenValidator<Jwt>:
  |      issuer, exp/nbf, audience, additional policies
  |
  +--> Invalid -> authentication fails, typically HTTP 401
  |
  +--> Valid -> JwtAuthenticationToken
                       |
                       v
                  Authorization:
                  scope / authority / business rules
                       |
                       +--> Insufficient permissions -> typically HTTP 403
                       +--> Authorized -> controller
~~~

These class names belong to **Servlet Resource Server**. `JwtDecoder.decode(token)` must produce a `Jwt` object that passed signature verification and its validators; **controllers never manually Base64-decode to authenticate tokens**.

`JwtAuthenticationConverter` typically maps scopes in a JWT into authorities prefixed with `SCOPE_` (for example, scope `orders.read` becomes `SCOPE_orders.read`). That step serves **authorization**, distinct from verifying signature, issuer, lifetime, and audience.

### What Do the HTTP Status Codes Mean?

- Request to a protected endpoint **without a Bearer token**: typically **401 Unauthorized**, with `WWW-Authenticate: Bearer`.
- JWT with bad signature, wrong issuer, wrong audience, or expired: authentication fails, typically **401**, possibly with `error="invalid_token"`.
- Valid JWT lacking required authority/role/permission: typically **403 Forbidden**.
- Controller rejects based on business logic: may return another status, independent of the JWT having passed.

Do not rely solely on status codes to conclude a specific root cause: API gateways, reverse proxies, custom entry points, and multiple security chains can alter responses.

## 4. JWT Signature: Which Key and Which Algorithm to Trust?

### 4.1. Asymmetric Signatures and JWKS

An authorization server typically uses a private key to sign an `RS256` JWS, while Resource Servers use the corresponding public key to verify it. Public keys can be published via a **JSON Web Key Set (JWKS)** at a system-configured URI:

~~~text
Trusted authorization server
   |
   +-- Private key: signs access tokens
   |
   +-- HTTPS JWKS endpoint: publishes public keys, with kid
                                      |
                                      v
                          Trusted JwtDecoder
                          + checks alg
                          + selects key by kid
                          + verifies signature
~~~

Key takeaways:

- **The JWKS URL is a trusted configuration of the Resource Server**, never taken from an arbitrary URL inside an untrusted token.
- `kid` only helps look up a key **within the trusted key set**. It cannot replace signature verification.
- `RS256` uses RSA with SHA-256. The token's algorithm must be in the decoder's allowed set. Never accept `alg=none` or automatically trust any algorithm declared by a client.
- Key rotation can introduce a new `kid`. The authorization server must publish the new key in time; the Resource Server must be able to refresh/cache JWKS appropriately. Still-valid older tokens may continue needing the old public key during the transition window.
- A successful JWS signature verification only tells you the token was signed by **a currently trusted key**; you must still evaluate issuer, audience, lifetime, and token type.

### 4.2. Why Must Algorithms Be Restricted?

Never take the `alg` value sent in a token and pick an unconstrained implementation. That pattern historically caused **algorithm confusion** bugs: systems mixing up symmetric/asymmetric keys, or skipping verification when `alg=none`. With `NimbusJwtDecoder`, configure the accepted algorithms based on the **issuer contract**, such as `RS256` only, and manage the corresponding keys. If the issuer migrates from RS256 to ES256, update the configuration, key set, and tests intentionally.

### 4.3. What About HS256?

HS256 uses a shared secret. If multiple Resource Servers know the secret to verify tokens, in principle they also have the ability to **sign** JWTs with that secret. In multi-service architectures, asymmetric algorithms like RS256/ES256 establish a clearer boundary: the authorization server holds the private key, while APIs only hold public keys. Never use short passwords as HMAC secrets.

## 5. Checking `iss`: Who Actually Issued the Token?

`iss` (issuer) identifies the server that issued the JWT. Example:

~~~json
{
  "iss": "https://identity.example.test/realms/acme"
}
~~~

The Resource Server must compare it against the configured trusted issuer. **Do not infer the issuer from the JWT itself and then trust that issuer.** If you accept any `iss` supplied by a client, another authorization server could mint tokens to access your API.

In Spring Boot, common declarative configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/acme
~~~

When using `issuer-uri` auto-configuration with compatible issuer metadata, Spring can use the authorization server's metadata to find the JWKS endpoint and build a decoder with **issuer validation** and default time checks. This requires the issuer to expose the appropriate metadata endpoint; issuer availability can affect startup when the decoder must fetch metadata.

If the JWKS URI is known in advance, both can be declared:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/acme
          jwk-set-uri: https://identity.example.test/realms/acme/protocol/openid-connect/certs
~~~

An explicit `jwk-set-uri` avoids depending on **automatic metadata discovery** at startup in corresponding configurations, while `issuer-uri` remains the basis for checking `iss`. At runtime when verifying new tokens, the JWKS endpoint must still be reachable or the needed key must still be cached.

**Common issuer pitfalls:**

- Mismatched `http`/`https` scheme, path/realm, or trailing `/` compared to the exact string issued by the real issuer.
- Token issued by a different realm/tenant even on the same domain.
- Using an internal issuer hostname in dev while production tokens carry a different public URL.
- Defining a custom `JwtDecoder` bean that replaces auto-configuration while forgetting to register `JwtIssuerValidator`.

The issuer must be governed by server configuration or **verified** tenant routing, never an unverified claim.

## 6. Lifetime: `exp`, `nbf`, `iat`, and Clock Skew

JWT uses **NumericDate**: seconds since the UTC Unix epoch; not milliseconds and not local time.

| Claim | Meaning | Validation |
| --- | --- | --- |
| `exp` | Time when the token expires. | Token must not be accepted after expiration (allowed clock skew may apply). |
| `nbf` | Not valid before this time. | Reject if the current clock is still before `nbf` beyond tolerance. |
| `iat` | Time when the token was issued. | Useful for auditing or custom max-age rules defined by the app; does not replace `exp`. |

Example (illustrative timestamps):

~~~json
{
  "iat": 1893456000,
  "nbf": 1893456000,
  "exp": 1893459600
}
~~~

An expired access token does not become valid merely because its signature still checks out. Spring Security's timestamp validator checks `exp` and `nbf` against a clock, typically with a default **clock skew** to tolerate minor clock drift between issuer and resource server. Never configure an excessively large clock skew just to work around expired-token errors: synchronize server clocks, use NTP, and design appropriate lifetimes.

### Is a Missing `exp` Accepted by Default?

Distinguish **validating a claim if present** from **requiring that claim to be present**. Depending on the validator and token profile, timestamp validators may not require `exp` to be present by default. If your product specifies that every access token must have an expiration, **add a validator requiring `exp` to be present**; the example in section 9 does this.

### What About `iat` and Maximum Token Age?

Having `exp` does not automatically enforce an internal maximum lifetime limit. A token whose `exp` is years in the future may exceed expectations. If a maximum TTL is needed, you can additionally check `iat`/`exp` and their span against a policy threshold while accounting for clock skew. This is an extra policy rule, not something automatically inferred from the signature or `JwtTimestampValidator`.

### Why Doesn't Logout Immediately Invalidate a JWT?

Self-contained JWTs can usually be verified offline until `exp`. The Resource Server does not query a database by default to learn whether the user just logged out or the token was revoked. If business requirements demand immediate revocation, you need a dedicated mechanism such as short token lifetimes, a `jti` denylist, introspection/opaque tokens, or a carefully designed session-state layer. **Signature + exp does not equal revocation.**

## 7. Checking `aud`: Which API Is This Token Meant For?

`aud` (audience) identifies the recipients the token is intended for. The claim can be a string or an array in JWT; Spring Security's `Jwt.getAudience()` provides a list for the application to inspect.

~~~json
{
  "aud": ["orders-api", "account-api"]
}
~~~

If your backend is `orders-api`, the minimum policy is **the audience list must contain `orders-api` exactly**. A token intended only for `payments-api` must be rejected even if its issuer, signature, and exp are valid.

Why does this matter? Two APIs trusting the same issuer/key can both verify the token signature. Not checking aud creates a risk of **token substitution / cross-service token replay**: a token issued for one API being presented to another API.

### Audience Differs from Scope and Client ID

- **`aud`** answers “which Resource Server is permitted to accept this token?”.
- **`scope`/`scp`** answers “what capabilities/operations were granted to the token?” within the context of other policies.
- **`client_id`/`azp`** may identify the client that requested the token or the authorized party, depending on the authorization server/profile; it does not replace `aud`.
- **`sub`** is the subject; it neither replaces audience nor proves authority by itself.

A token with `aud=["orders-api"]` but **without** `scope=orders.read` may pass JWT validation yet **must not be allowed** on an endpoint requiring `SCOPE_orders.read`. Conversely, a token with scope `orders.read` but audience `payments-api` must be blocked during **authentication/token validation** before scopes are even checked.

### Should All Audiences from an Issuer Be Allowed?

No. Just because a token was signed by a trusted issuer does not mean it belongs to every Resource Server. Each API must know its own identifying audience; when multiple audiences are supported, maintain an explicit allowlist and test each case rather than loosely matching with `startsWith` or substrings.

## 8. Java 17+ Configuration for Spring Boot 3: JWT Resource Server

This sample application receives Bearer tokens via `Authorization`, using an HTTPS issuer and a server-managed JWKS endpoint. It selects **RS256**, requires `exp`, and requires the `orders-api` audience. Files live in package `com.example.orderssecurity` of a Spring Boot app.

This is a Spring Boot integration example: the Java code compiles in a **project with the dependencies installed**, and the IdP addresses must be replaced with a real issuer. It cannot be compiled/run with bare `javac` without Spring libraries.

### 8.1. Dependencies

In a Spring Boot Gradle project with Java and Spring Boot plugins configured, the core dependencies are:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The Resource Server starter brings in the JWT/JOSE support needed for standard setups. To keep dependency versions consistent, let Spring Boot manage versions through the project's dependency management/BOM.

### 8.2. application.yml

**`src/main/resources/application.yml`:**

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/acme
          jwk-set-uri: https://identity.example.test/realms/acme/protocol/openid-connect/certs

app:
  security:
    jwt:
      audience: orders-api
~~~

The `example.test` URLs are **illustrative values** only, not a live identity provider. Replace them with real, trusted issuer and JWKS URIs over valid HTTPS.

### 8.3. SecurityFilterChain and JwtDecoder Configuration Class

**`src/main/java/com/example/orderssecurity/JwtSecurityConfig.java`:**

~~~java
package com.example.orderssecurity;

import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class JwtSecurityConfig {

    @Bean
    SecurityFilterChain apiChain(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().authenticated()
            )
            // Only use this option for a pure Bearer API that does not use
            // session cookies to authenticate state-changing requests.
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
                    String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
                    String jwkSetUri,
            @Value("${app.security.jwt.audience}")
                    String requiredAudience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
            .withJwkSetUri(jwkSetUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

        decoder.setJwtValidator(validationPolicy(issuer, requiredAudience));
        return decoder;
    }

    // Package-private so tests in the same package can reuse it.
    static OAuth2TokenValidator<Jwt> validationPolicy(
            String issuer,
            String requiredAudience) {

        OAuth2TokenValidator<Jwt> issuerAndTime =
            JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt -> {
            List<String> aud = jwt.getAudience();
            if (aud != null && aud.contains(requiredAudience)) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "JWT audience is not accepted", null));
        };

        OAuth2TokenValidator<Jwt> expirationRequired = jwt -> {
            if (jwt.getExpiresAt() != null) {
                return OAuth2TokenValidatorResult.success();
            }
            return OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token",
                    "JWT exp claim is required", null));
        };

        return new DelegatingOAuth2TokenValidator<>(
            issuerAndTime, audience, expirationRequired);
    }
}
~~~

**Explanation of key decisions:**

1. `NimbusJwtDecoder.withJwkSetUri(…)` uses a **configured fixed JWKS** for signature verification; `jwsAlgorithm(RS256)` restricts accepted algorithms.
2. `JwtValidators.createDefaultWithIssuer(issuer)` builds default checks including **issuer validation and timestamps**. In the example, the validation policy also checks aud and requires the exp claim to be present.
3. `DelegatingOAuth2TokenValidator` requires **all validators** to succeed, not just one of the three.
4. `JwtDecoder` is an application-declared bean. This **replaces Spring Boot's auto-configured decoder**; therefore, you must actively keep all checks required by your security policy. Adding only an audience validator while forgetting issuer/timestamp is a critical bug.
5. The `hasAuthority("SCOPE_orders.read")` rule is **authorization** after JWT validation. If the issuer uses a non-default scope claim name, configure `JwtAuthenticationConverter` to match the contract rather than modifying audience to “grant permissions.”
6. The disabled CSRF and stateless session example is **only valid for a pure Bearer API** that does not authenticate state-changing requests via browser cookies. If the same app serves form login/cookies, design chains/CSRF appropriately rather than disabling CSRF across all endpoints.

If you do not need mandatory audience or custom policies, Spring Boot can auto-configure a decoder from `issuer-uri` without this bean. However, this lesson's goal is **requiring aud and exp**, so the example declares the policy explicitly.

### 8.4. Sample Controller

**`src/main/java/com/example/orderssecurity/OrdersApplication.java`:**

~~~java
package com.example.orderssecurity;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/orderssecurity/OrdersController.java`:**

~~~java
package com.example.orderssecurity;

import java.util.Map;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class OrdersController {

    @GetMapping("/api/public")
    public Map<String, String> status() {
        return Map.of("status", "public");
    }

    @GetMapping("/api/orders")
    public Map<String, String> list() {
        return Map.of("result", "orders visible");
    }
}
~~~

`GET /api/public` requires no token; `GET /api/orders` requires a valid JWT **and** the `SCOPE_orders.read` authority. Illustrative JSON response when authorized:

~~~json
{"result":"orders visible"}
~~~

This is a minimal controller to highlight boundaries; real data, tenant permissions, and object-level authorization must be built separately.

### 8.5. Calling the API from an HTTP Client

With a token issued by a real issuer (signed with the right key, valid iss/aud/exp/scope):

~~~bash
curl -i "http://localhost:8080/api/orders" \
  -H "Authorization: Bearer <ACCESS_TOKEN>"
~~~

`<ACCESS_TOKEN>` is a placeholder for the learner to replace manually in a terminal—**never put it in source code, repositories, or logs**. On PowerShell, you can place the token in an environment/process-scoped variable securely and send it with `curl.exe` or PowerShell `Invoke-WebRequest`; the example above uses Unix shell syntax.

A Gradle project with the Spring Boot plugin can run:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

When using the non-existent `example.test` URL, Bearer requests cannot be verified because the JWKS key set cannot be fetched. End-to-end runs require a real authorization server or a mock issuer/JWKS in a test environment.

## 9. Testing JWT Validation with Self-Generated RSA Keys: No Real IdP Needed

To test all four trust boundaries **independently of the network**, you can sign JWTs in tests using a temporary RSA private key, pass the RSA public key into `NimbusJwtDecoder.withPublicKey(…)`, and reuse the same `validationPolicy` from section 8. This exercises real signature and claim validators, unlike a test that merely mocks a `Jwt` object.

**`src/test/java/com/example/orderssecurity/JwtValidationPolicyTest.java`:**

~~~java
package com.example.orderssecurity;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

import static org.junit.jupiter.api.Assertions.assertDoesNotThrow;
import static org.junit.jupiter.api.Assertions.assertThrows;

class JwtValidationPolicyTest {

    private static final String ISSUER =
        "https://identity.example.test/realms/acme";
    private static final String AUDIENCE = "orders-api";

    private KeyPair trusted;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void init() throws Exception {
        trusted = newKeyPair();

        decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) trusted.getPublic())
            .build();

        decoder.setJwtValidator(
            JwtSecurityConfig.validationPolicy(ISSUER, AUDIENCE));
    }

    @Test
    void acceptsTrustedSignatureIssuerTimeAndAudience() throws Exception {
        String token = sign(trusted, ISSUER, List.of(AUDIENCE),
            Instant.now().plusSeconds(300));

        assertDoesNotThrow(() -> decoder.decode(token));
    }

    @Test
    void rejectsSignatureFromAnotherKey() throws Exception {
        KeyPair attackerKey = newKeyPair();

        String token = sign(attackerKey, ISSUER, List.of(AUDIENCE),
            Instant.now().plusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsWrongIssuer() throws Exception {
        String token = sign(trusted, "https://other-issuer.example.test",
            List.of(AUDIENCE), Instant.now().plusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsExpiredToken() throws Exception {
        // Expired by 300 seconds, exceeding typical clock skew tolerance.
        String token = sign(trusted, ISSUER, List.of(AUDIENCE),
            Instant.now().minusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsWrongAudience() throws Exception {
        String token = sign(trusted, ISSUER, List.of("payments-api"),
            Instant.now().plusSeconds(300));

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    @Test
    void rejectsMissingExpiration() throws Exception {
        String token = sign(trusted, ISSUER, List.of(AUDIENCE), null);

        assertThrows(JwtException.class, () -> decoder.decode(token));
    }

    private static KeyPair newKeyPair() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    private static String sign(
            KeyPair keyPair,
            String issuer,
            List<String> audience,
            Instant expiration) throws Exception {

        JWTClaimsSet.Builder claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audience)
            .issueTime(Date.from(Instant.now().minusSeconds(10)));

        if (expiration != null) {
            claims.expirationTime(Date.from(expiration));
        }

        SignedJWT signed = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                .type(JOSEObjectType.JWT)
                .keyID("test-rsa")
                .build(),
            claims.build()
        );

        signed.sign(new RSASSASigner(
            (RSAPrivateKey) keyPair.getPrivate()));
        return signed.serialize();
    }
}
~~~

Key points when running the tests:

- The test generates RSA keys **only in test memory**; never use test keys as production keys.
- In the bad-signature case signed by another private key, the decoder trusts only the `trusted` public key and must reject it.
- Wrong-issuer and wrong-audience tokens are still signed by the **right key**; thus they prove a valid signature alone is insufficient.
- Exp is **300 seconds** in the past so the test does not accidentally pass due to default clock skew. A missing exp is rejected by the dedicated validator.
- The JWT in the test is a JWS produced by `SignedJWT`, not a hand-concatenated base64 string lacking a signature.

Run with a Gradle project having the dependencies from section 8:

~~~bash
./gradlew test
~~~

Or Windows:

~~~powershell
.\gradlew.bat test
~~~

**Expected:** all six tests pass when API and dependency versions match Spring Boot 3 / Spring Security 6, without needing a network IdP. This tests decoder logic and claim validation; it does not test `jwk-set-uri` networking, caching, rotation, HTTP security filters, or scope authorization.

### 9.1. Why Doesn't `MockMvc.with(jwt())` Verify Real Signatures?

`spring-security-test` provides the `jwt()` request post-processor to build authentication for controller/security-rule tests, but **it does not necessarily invoke `JwtDecoder.decode`**. If you only write:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

that is a **fragment** of a MockMvc test that already has an `mvc` field and proper static imports. This test verifies authorization/controller behavior with mocked authentication; **it does not prove** that a JWT with a bad signature is rejected. To test signature, issuer, exp, and aud, invoke a real decoder like section 9 or run an integration test sending a real Bearer token through the filter against a test trusted key/JWKS.

### 9.2. Additional Test Cases for Real Deployments

- `nbf` in the future beyond clock skew → rejected.
- Token missing `aud` → rejected; token with multiple audiences containing `orders-api` → accepted if policy permits.
- Token with an alg outside the allowlist, tampered payload, unsigned token, or `kid` absent from trusted JWKS → rejected.
- Key rotation: tokens before/after switching `kid` and while the old public key remains valid.
- JWT passing validation without `SCOPE_orders.read` → 403 when calling the endpoint.
- Request without a Bearer token → 401 on a protected endpoint.
- Different tenant issuer or different token type (e.g., ID token) → must have explicit policy handling.

Do not write redundant unit tests for every internal branch if acceptance/integration tests already prove the security boundaries; prioritize behavior-driven tests with meaningful adversarial inputs.

## 10. Common Pitfalls in Spring Resource Server

| Symptom | Possible Cause | How to Verify and Fix |
| --- | --- | --- |
| JWT Base64-decodes cleanly, yet API returns 401 | Base64 decoding does not verify signature, or key/alg is untrusted. | Inspect `JwtDecoder`, JWKS, `kid`, alg, and signature. |
| Token issued by another issuer returns 401 | `iss` does not match configured issuer. | Compare exact scheme/host/path/trailing slash in `iss`. |
| Two APIs share an IdP; token works on the wrong API | Missing audience validator. | Enforce `aud` identifying each API. |
| Expired token returns 401 | `exp` is in the past or clock skew exceeded. | Check UTC/NumericDate, NTP, token lifetime; fetch a fresh token. |
| Not-yet-valid token returns 401 | `nbf` is in the future. | Check issuer and resource server clocks; avoid excessive clock skew. |
| Token without `exp` still passes timestamp validator | Policy does not require claim presence. | Add an `exp required` validator if the access token profile requires it. |
| Startup fails when using `issuer-uri` | Cannot fetch discovery metadata or wrong issuer URI. | Check metadata/JWKS/config; use explicit `jwk-set-uri` when appropriate. |
| After key rotation new tokens suddenly return 401 | JWKS has not published the new key or decoder has not refreshed cache. | Check `kid`, JWKS, rollout, and caching; do not relax alg. |
| JWT passes, yet endpoint returns 403 | Missing `SCOPE_…` or another authorization policy. | Check authorities, `JwtAuthenticationConverter`, and authorization rules. |
| Custom `JwtDecoder` exists, yet issuer/aud are unchecked | Custom bean replaced auto-config and only verifies signature. | Attach `JwtValidators.createDefaultWithIssuer` plus audience/exp validators. |
| Frontend JWT accepted as an access token | Audience/token type not validated against contract. | Use a proper access token profile; verify aud, typ/token-use if required by issuer. |
| Revoked token after logout still works | Self-contained JWT has no revocation check. | Short TTLs, denylist/introspection based on risk requirements. |
| Browser reports CORS instead of 401 | Response missing CORS headers, proxy, or another filter. | Inspect Network tab and CORS config; do not conflate with JWT validation. |

### Safe Diagnostic Workflow

1. Determine whether a real Bearer token is present in the request, **without logging the full token**.
2. Check which `JwtDecoder` is active: Boot auto-configuration or a custom declared bean?
3. Confirm issuer/JWKS URLs and the alg allowlist come from **server configuration**, never from token input.
4. Distinguish signature, issuer, exp/nbf, and audience failures using decoder tests with trusted test data.
5. If the decoder succeeds yet the endpoint returns 403, inspect authorities/scopes and method/URL matchers.
6. Check gateways/proxies, clock sync, JWKS cache/rotation, multiple security chains, and deployment environment.

In production, log failures by **standardized category** (invalid signature, invalid issuer, expired, invalid audience) with safe request context. Avoid logging tokens, private keys, Authorization headers, session cookies, user secrets, or exception text containing client-controlled data.

## 11. Dangerous Misconceptions

**“If a JWT has three parts and decodes, it is valid.”** False: you must verify the signature with a trusted key and run appropriate validators.

**“A valid signature is all you need.”** Insufficient: tokens with the wrong issuer, expired, or meant for another audience must still be rejected.

**“Any issuer with an HTTPS JWKS is trustworthy.”** False: HTTPS only protects the transport to that endpoint; the backend itself must configure trusted issuers. Never let a token dictate an arbitrary JWKS URL or issuer.

**“`aud` is the same as scope.”** False: audience determines which resource may accept the token, while scope represents specific permissions. Both are needed when policy requires them.

**“`sub` is a globally unique account.”** False: subject is meaningful only **within an issuer's context**; two issuers can assign the same `sub` to two different people.

**“Larger clock skew is safer.”** False: excessive skew widens the acceptance window for expired or not-yet-valid tokens. Sync clocks and configure intentionally tight tolerance.

**“Because JWT has exp, logout revokes it automatically.”** False: self-contained JWTs generally remain valid until exp unless an extra revocation mechanism exists.

**“`with(jwt())` proves the decoder verifies signatures.”** False: that test post-processor can bypass the decoder. You must test the real decoder or the HTTP Bearer integration path.

**“`issuer-uri` always checks audience automatically.”** Not by default. Issuer validation is one step; the API's audience must be declared and checked by policy unless another mechanism guarantees it.

**“Every access token is a JWT.”** False: an authorization server can issue opaque tokens. `oauth2ResourceServer().opaqueToken(…)` uses introspection, which differs from JWS/JWKS.

## 12. Self-Review Questions

1. **What if a token is properly signed by a trusted private key, yet `iss` differs?** Reject it because the issuer is not on the trusted list.
2. **Two microservices both verify an RS256 JWT; why is aud needed?** Prevents a JWT meant for one API from being used at another API even with the same issuer/key.
3. **Is `exp=1893459600` in seconds or milliseconds?** NumericDate is Unix UTC seconds.
4. **How does `nbf` differ from `exp`?** `nbf` is the earliest time a token may be used; `exp` is when the token expires.
5. **Can `iat` replace `exp`?** No; if you want a max-age limit, add an explicit policy validator.
6. **What should a Resource Server do if a client sends header `alg=none`?** Distrust that header; reject any JWT not validly signed with an allowed algorithm.
7. **How do you tell 401 and 403 apart in a Resource Server?** 401 generally means missing or invalid authentication; 403 generally means authenticated but lacking permission.
8. **Does a custom `JwtDecoder` bean automatically inherit issuer and audience validators from `application.yml`?** Never assume so; configure validators on the decoder per contract, as in section 8.
9. **When signing keys rotate, why might new JWTs suddenly return 401?** JWKS/caching/`kid` are not yet aligned between the issuer and Resource Server.
10. **Why is a decoder test using fresh RSA key pairs still valuable?** It tests real signature and claim validators without depending on a networked IdP; complement it with integration tests covering real JWKS/HTTP.

**Remember:** JWT validation in a Servlet Resource Server must bind **trusted keys + algorithms** with an **allowed issuer**, a **valid time window**, and the **API's exact audience**. Only after a token passes all of these steps should scopes/authorities and business policies decide access.