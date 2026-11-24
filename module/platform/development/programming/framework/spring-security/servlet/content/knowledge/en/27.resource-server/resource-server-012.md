# JWT Revocation Limits, Token Lifetimes, and Testing Invalid Tokens in Spring Security Resource Server

## 1. Goal and Context

A Java API using **Spring Security OAuth2 Resource Server** commonly receives access tokens as **JWTs** via the **Authorization: Bearer ...** header. Signed JWTs can be verified locally by the resource server using the issuer's (Authorization Server, abbreviated AS) public keys. That avoids calling the AS on every request, yet introduces an important trade-off:

> A JWT that has been issued and remains valid by signature, timestamps, issuer, audience, and API rules generally **cannot be revoked instantaneously merely by logging out or deleting the refresh token at the AS**.

Suppose a user receives an access token at 10:00 with **exp = 10:15**. At 10:05 the user logs out, but the token was previously leaked. If the API verifies JWTs purely statelessly, the copied token may still be accepted until it expires, subject to clock skew and extra policies. This is the **JWT revocation limit**, not a bug in Spring Security.

This lesson focuses on three tasks:

1. **Understand precisely what a valid JWT means:** signature and algorithm, **iss**, **aud**, **exp**, **nbf**, **iat**, scopes/authorities, and revocability.
2. **Design lifetimes and revocation mechanisms suited to risk:** short-lived access tokens, refresh token rotation, **jti** denylists, introspection, key rotation, and caching.
3. **Test invalid tokens** in Spring Security Servlet: missing token, malformed token, expired, not yet valid, wrong issuer/audience, bad signature, excessive TTL, and missing permissions; clearly distinguish **401** from **403**.

Context: Spring Boot 3.x / Spring Security 6.x / Java 17+, using a servlet web application and **OAuth2 Resource Server JWT**, not Spring Security WebFlux.

## 2. What Does a JWT Access Token Contain?

A JWS-formatted JWT normally has three Base64URL-encoded parts:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Conceptual payload example (not a real token usable for login):

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "alice",
  "aud": ["urn:orders-api"],
  "iat": 1790000000,
  "nbf": 1790000000,
  "exp": 1790000900,
  "jti": "random-unique-token-id",
  "scope": "orders.read"
}
~~~

Timestamps only illustrate **NumericDate** representation (seconds since Unix epoch), not a demo token schedule.

| Claim / Component | Meaning | Policy That Should Be Checked |
| --- | --- | --- |
| **JWS signature** and **alg** | Whether the token was tampered with and signed with a trusted algorithm/key | Use a decoder with allowed algorithms and trusted managed keys; never trust arbitrary alg from the token |
| **iss** | Identifier of the token issuer | Exact match against configured issuer |
| **aud** | Resource/API the token was issued to call | Must include the API's audience; do not rely solely on issuer |
| **exp** | Expiration time | Reject expired tokens, accounting for bounded clock skew |
| **nbf** | Not valid before this time | Reject tokens used too early |
| **iat** | Issued-at time | Used to bound maximum token age and sanity checks when policy requires |
| **jti** | Token ID, often used for replay/revocation tracking | Should be unique; useful for revocation only if the API **queries state** |
| **scope/scp**, roles | Permissions granted for the API | Check per endpoint; Spring typically maps scopes to **SCOPE_...** authorities |

**Standard JWT payloads are not confidentially encrypted.** Base64URL is encoding, not encryption. Never put passwords, client secrets, sensitive personal data, or abusable info into claims just because a token is signed.

**An unexpired token does not mean permission to access every API.** A valid signature with the wrong **aud** or missing **orders.read** must still be rejected.

## 3. JWT Revocation Limits and Architectural Choices

### 3.1. Why Doesn't Logout Revoke Already-Issued JWTs?

The resource server verifies signatures with public keys fetched from a JWK Set and validates claims right inside the API. Without querying external state, it **cannot know** the user just logged out, changed their password, had their account locked, or had an admin terminate their session.

These actions **do not automatically invalidate** JWT access tokens already held by a client or attacker:

- Clearing the web application's session.
- Deleting the token from memory/browser storage.
- Revoking the **refresh token** at the AS.
- Changing passwords if the resource server trusts static JWTs without checking account state.
- Removing a user from a group if permissions are baked into the JWT and the API does not query current permissions.

Those steps can block **future token issuance**, but cannot alter the signature or claims of an existing JWT. When **immediate** revocation is required, add state checks or switch token models.

### 3.2. Four Common Strategies

| Strategy | Effect | Trade-off |
| --- | --- | --- |
| **Short-TTL Access JWT** | Caps the exposure window of a leaked token without calling AS per request | Not immediate revocation: token remains usable near **exp** |
| **Shared Redis/DB jti denylist** | Blocks individual JWTs before exp, e.g., at logout or incident | API must query state; introduces consistency, uptime, TTL, and scaling needs |
| **Opaque access token + introspection** | AS can return **active=false** after revocation | Latency/AS dependency; introspection caches delay revocation proportionally |
| **Rotate/revoke signing key** | Can invalidate a whole class of JWTs signed by the old key | Broad blast radius, JWK caches across APIs, outage risk; unsuitable for single-user revocation |

A sensible default for many APIs is **short-lived access tokens + protected, rotating, revocable refresh tokens**. This remains a trade-off; financial or privileged-admin systems may require a denylist or introspection to meet strict revocation SLAs.

### 3.3. jti Denylist: Designing the Full Lifecycle

A deployment workflow might look like:

1. The AS issues access JWTs with a unique **jti**, **iss**, and **exp**. The resource server verifies signature, issuer, audience, and expiry as usual.
2. When revoking an access JWT, the backend authorizes the revocation request and writes a denylist entry keyed by **(iss, jti)**. Avoid relying solely on **sub** when the goal is revoking a single token.
3. On each API request, after the decoder validates the JWT, the resource server checks the denylist. If an active entry is found, reject the token.
4. The denylist entry lives for roughly **exp − current time + maximum tolerated clock skew**. Afterward the JWT itself is unusable, so the record can expire.

Storage algorithm example (pseudocode, **not** copy-paste Redis commands):

~~~text
revocationKey = "revoked:" + hash(issuer + "|" + jti)
remainingSeconds = max(1, expEpochSeconds - nowEpochSeconds + clockSkewSeconds)

SET revocationKey "1" EX remainingSeconds

on each authenticated JWT request:
    validate signature + issuer + audience + exp + nbf
    if revocationStore.contains(revocationKey):
        reject as invalid token
    continue with authorization
~~~

In multi-instance deployments, **an in-JVM HashMap is insufficient**: instance A will not see a revocation recorded on instance B, and data disappears on restart. Use a shared store or session-state system designed for this purpose.

Mandatory conditions before adopting a denylist:

- **Missing or non-unique jti:** decide whether to reject the token. If policy requires per-token revocation while the AS omits reliable jtis, fix the AS or use another token identifier (such as a hash of the verified token).
- **Denylist store outage:** have an explicit **fail-closed** policy or accept fail-open risk; never silently treat lookup errors as **not revoked** on high-risk APIs.
- **Race conditions/caching:** if the API caches “not revoked” outcomes for 5 minutes, effective revocation can lag up to that cache TTL. Measure and publish revocation SLAs.
- **Data leakage:** never store raw JWTs; protect denylist keys, do not log tokens, and enforce TTLs/resource bounds.
- **Bulk logout:** revoking all of a user's tokens usually needs an additional structure like a **session version**, user **issued-before cutoff**, or central session mechanism; per-jti denylists may miss unknown tokens.
- **Trusting revocation events:** only an authenticated, authorized AS or service may issue revocations; never trust arbitrary requests claiming someone else's jti is revoked.

### 3.4. Refresh Tokens and Lifetimes

**Access tokens** are sent to resource servers; **refresh tokens** are normally used only between the authorization server and OAuth2 client to obtain fresh access tokens. Never send refresh tokens to ordinary APIs or use refresh tokens as bearer access tokens.

Sample policy for discussion (not a universal requirement for every system):

| Token / Mechanism | Example Lifetime | Purpose |
| --- | --- | --- |
| Access JWT | **5–15 minutes** | Limits how long a leaked token remains usable |
| Refresh token | **Hours/days**, by sensitivity and client type | Reduces how often users must re-authenticate |
| Refresh token rotation | Issues a new token per refresh, invalidates previous one | Limits reuse and helps detect stolen tokens |
| Absolute session limit | A final hard expiration timestamp | Prevents indefinite login extension merely by refreshing |

These durations are **illustrative**. Pick TTLs using threat modeling, UX expectations, revocability, clock drift, and AS policies. A JWT access token has a **fixed exp**: an API cannot extend the exp of an already-signed JWT; it must request a **new token** from the AS.

**Clock skew:** resource servers may tolerate a small clock difference when checking **exp/nbf**. This avoids false errors from slight clock drift, yet slightly extends how long a token works past exp. Sync clocks via NTP, keep skew bounded, and in tests pick timestamps far enough from thresholds (e.g., 10 minutes) to avoid flaky boundary tests.

### 3.5. Revocation via Keys and JWKS

JWTs typically carry a **kid** header so the decoder selects a public key from a JWK Set. If a signing key leaks, rotate or emergency-revoke per AS procedure, keeping in mind:

- APIs may **cache the JWK Set**; deleting a key at the AS does not guarantee APIs immediately forget cached keys.
- Removing an old key too early can cause widespread 401s for **valid, unexpired JWTs**.
- Keeping a compromised key too long prolongs exposure. Have procedures for key replacement, cache refresh, monitoring, and recovery.
- Never accept algorithms or JWK key sources merely because a JWT header asks for them; decoders must enforce server-side trust policies.

**Key rotation does not replace per-user denylists.** It suits scheduled key changes or issuer-wide compromise response.

## 4. Where Does Spring Security Resource Server Validate Tokens?

Bearer authentication flow in the Servlet security chain:

~~~text
GET /api/orders
Authorization: Bearer <jwt>
           │
           ▼
BearerTokenAuthenticationFilter
           │
           ▼
JwtAuthenticationProvider → JwtDecoder
           │                     │
           │                     ├── parse compact JWT/JWS
           │                     ├── verify signature with trusted key
           │                     ├── check iss / exp / nbf
           │                     ├── check aud and custom TTL policy
           │                     └── if enabled: check jti revocation store
           │
           ├── token error → AuthenticationEntryPoint → HTTP 401
           └── valid token → create Authentication / authorities
                                        │
                                        ▼
                              AuthorizationFilter
                                        │
                              missing authority → HTTP 403
                              sufficient authority → Controller
~~~

Specifically:

- **401 Unauthorized:** unauthenticated or unaccepted token (missing/malformed/expired/bad signature/wrong issuer/wrong audience).
- **403 Forbidden:** token authenticated successfully, yet lacks permission to access the endpoint, such as missing **SCOPE_orders.read**.
- If the app has custom error handlers, proxies, or multiple chains, actual responses may differ; tests must target the exact security chain.
- **Authentication principal** for a successful JWT is usually a **Jwt** object, while **JwtAuthenticationToken** holds authorities derived from scope/scp.
- Merely seeing a valid signature **does not prove** the token was issued for the right API. Check **aud** instead of accepting every access token from the same issuer.
- Never write Base64-decode helpers to read claims and “authenticate” tokens. Reading a payload is not verifying a signature.

## 5. Java 17+ Configuration Example with Issuer, Audience, and TTL Limits

The following example targets **Spring Boot 3.x, Spring Security 6.x, Servlet applications**. It needs a Boot project with a Gradle wrapper and an AS publishing a valid JWK Set.

In **build.gradle**, add dependencies:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

File **src/main/resources/application.yml**:

~~~yaml
security:
  jwt:
    issuer-uri: "https://issuer.example.test"
    jwk-set-uri: "https://issuer.example.test/.well-known/jwks.json"
    audience: "urn:orders-api"
~~~

The **example.test** addresses are illustrative data only: replace them with real issuer/JWK Set URIs from a trusted provider. When using **NimbusJwtDecoder.withJwkSetUri**, the app **does not** query the issuer URL for discovery metadata because the JWK Set URI is given directly; simultaneously you must **configure issuer validation explicitly** via a validator (see code). Ensure TLS, key storage, connectivity, and rotation policies are sound.

File **src/main/java/com/example/jwtlimits/JwtLimitsApplication.java**:

~~~java
package com.example.jwtlimits;

import java.time.Duration;
import java.time.Instant;
import java.util.List;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.security.core.annotation.AuthenticationPrincipal;

@SpringBootApplication
public class JwtLimitsApplication {
    public static void main(String[] args) {
        SpringApplication.run(JwtLimitsApplication.class, args);
    }
}

@Configuration
class SecurityConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers(HttpMethod.GET, "/api/public/ping").permitAll()
                        .requestMatchers(HttpMethod.GET, "/api/orders")
                            .hasAuthority("SCOPE_orders.read")
                        .anyRequest().authenticated())
                .sessionManagement(session ->
                        session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
                // Suitable only for APIs using bearer tokens in the Authorization header,
                // NOT using auto-sent cookies/sessions as credentials.
                .csrf(AbstractHttpConfigurer::disable)
                .oauth2ResourceServer(oauth2 ->
                        oauth2.jwt(Customizer.withDefaults()))
                .build();
    }

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${security.jwt.jwk-set-uri}") String jwkSetUri,
            @Value("${security.jwt.issuer-uri}") String issuer,
            @Value("${security.jwt.audience}") String audience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();
        decoder.setJwtValidator(validators(issuer, audience));
        return decoder;
    }

    static OAuth2TokenValidator<Jwt> validators(
            String issuer, String audience) {

        // Includes issuer and timestamp checks via default validators.
        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator =
                new JwtClaimValidator<List<String>>(
                        "aud",
                        aud -> aud != null && aud.contains(audience));

        // Custom policy for the sample API: require iat + exp and max 15-minute TTL.
        OAuth2TokenValidator<Jwt> lifetimeValidator = jwt -> {
            Instant issuedAt = jwt.getIssuedAt();
            Instant expiresAt = jwt.getExpiresAt();
            boolean invalid =
                    issuedAt == null ||
                    expiresAt == null ||
                    !expiresAt.isAfter(issuedAt) ||
                    Duration.between(issuedAt, expiresAt)
                            .compareTo(Duration.ofMinutes(15)) > 0 ||
                    issuedAt.isAfter(Instant.now().plusSeconds(60));

            if (invalid) {
                OAuth2Error error = new OAuth2Error(
                        "invalid_token",
                        "JWT missing iat/exp, has invalid times, or exceeds TTL",
                        null);
                return OAuth2TokenValidatorResult.failure(error);
            }
            return OAuth2TokenValidatorResult.success();
        };

        return new DelegatingOAuth2TokenValidator<>(
                standard, audienceValidator, lifetimeValidator);
    }
}

@RestController
class OrdersController {
    @GetMapping("/api/public/ping")
    String ping() {
        return "pong";
    }

    @GetMapping("/api/orders")
    String orders(@AuthenticationPrincipal Jwt jwt) {
        return "subject=" + jwt.getSubject();
    }
}
~~~

### Analysis of Choices

1. **The decoder verifies JWS with trusted keys** from the JWK Set URI. Never fetch public keys from a URL placed by an attacker in a JWT header. If the AS uses a non-default algorithm, configure it per the AS contract rather than trusting arbitrary **alg** headers.
2. **JwtValidators.createDefaultWithIssuer(issuer)** includes default time checks such as **exp/nbf** and verifies **iss** per Spring Security policy. **Clock skew** must be considered when choosing expiration bounds and tests.
3. **Audience validator** guarantees the token was genuinely intended for **urn:orders-api**. A JWT for the same user meant for another resource cannot be used on this API.
4. **Lifetime validator** is an extra policy: requires **iat** and **exp**, **exp > iat**, disallows **exp - iat** exceeding **15 minutes**, and rejects **iat** too far in the future. Checking **exp - iat** differs from checking whether the token already expired: **both** are needed.
5. **SCOPE_orders.read** is the permission required on the endpoint; Spring Security by default maps **scope: "orders.read"** to the matching authority. A valid JWT lacking scope receives **403**, not 401.
6. **STATELESS + csrf.disable()** fits only APIs truly designed to accept bearer tokens placed by the client in the **Authorization** header, without cookie/session mechanisms auto-sent cross-origin. If the same app uses sessions/cookies for browser login, design separate CSRF and security chains; never copy this disable call across all request types.
7. **The 15-minute TTL** is an example rule; the issuer must issue matching access tokens. An API enforcing a tighter max TTL than the issuer is valid for security yet can cause live clients to get 401s: verify the token contract between AS and API before deploying.

**Important:** There is no denylist in the Java demo. Therefore, an already-issued, valid JWT with matching scope is still accepted even after the user logs out. That is the designed behavior of a stateless resource server, not a forgotten revocation switch.

## 6. Testing Real JWT Verification, Not Just Mocked Principals

Two common testing approaches are **not equivalent**:

| Approach | Verifies Real Signature / Decoder? | What Is It For? |
| --- | --- | --- |
| **MockMvc with .with(jwt())** from spring-security-test | **No**: injects a simulated authentication | Testing authorization/controllers as an already logged-in principal |
| **MockMvc + self-signed JWT with test private key + NimbusJwtDecoder using test public key** | **Yes**, through the real decoder | Testing signature, issuer, audience, exp, nbf, TTL, 401 errors, and 403 scopes |

If you want to prove **expired tokens or bad signatures are rejected**, use the second approach or test JwtDecoder directly. Never claim a **.with(jwt())** test verified real signatures, because it bypasses that step.

### 6.1. Integration Test Suite with RSA Keys Generated in the Test JVM

File **src/test/java/com/example/jwtlimits/JwtLimitsTest.java** (same package as the application class):

~~~java
package com.example.jwtlimits;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.UUID;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(properties = {
        "security.jwt.issuer-uri=https://issuer.example.test",
        "security.jwt.jwk-set-uri=https://issuer.example.test/jwks",
        "security.jwt.audience=urn:orders-api"
})
@AutoConfigureMockMvc
class JwtLimitsTest {

    static final String ISSUER = "https://issuer.example.test";
    static final String AUDIENCE = "urn:orders-api";

    // For tests only. Never embed private keys in production source.
    static final KeyPair TRUSTED_KEY = newRsaKeyPair();
    static final KeyPair OTHER_KEY = newRsaKeyPair();

    @Autowired
    MockMvc mvc;

    @TestConfiguration
    static class LocalDecoderConfig {
        @Bean
        @Primary
        JwtDecoder testJwtDecoder() {
            NimbusJwtDecoder decoder = NimbusJwtDecoder.withPublicKey(
                    (RSAPublicKey) TRUSTED_KEY.getPublic()).build();
            decoder.setJwtValidator(
                    SecurityConfiguration.validators(ISSUER, AUDIENCE));
            return decoder;
        }
    }

    private static KeyPair newRsaKeyPair() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (Exception e) {
            throw new IllegalStateException("Cannot create test RSA key", e);
        }
    }

    private String token(
            String issuer,
            String audience,
            Instant issuedAt,
            Instant notBefore,
            Instant expiresAt,
            String scope,
            KeyPair signingKey) throws Exception {

        JWTClaimsSet.Builder claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject("alice")
                .audience(List.of(audience))
                .issueTime(Date.from(issuedAt))
                .notBeforeTime(Date.from(notBefore))
                .jwtID(UUID.randomUUID().toString());

        if (expiresAt != null) {
            claims.expirationTime(Date.from(expiresAt));
        }
        if (scope != null) {
            claims.claim("scope", scope);
        }

        SignedJWT signedJwt = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .type(JOSEObjectType.JWT)
                        .keyID("test-key")
                        .build(),
                claims.build());
        signedJwt.sign(
                new RSASSASigner((RSAPrivateKey) signingKey.getPrivate()));
        return signedJwt.serialize();
    }

    private String validToken() throws Exception {
        Instant now = Instant.now();
        return token(
                ISSUER, AUDIENCE,
                now.minusSeconds(30), now.minusSeconds(30),
                now.plusSeconds(300),
                "orders.read", TRUSTED_KEY);
    }

    private void expectUnauthorized(String jwtValue) throws Exception {
        mvc.perform(get("/api/orders")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer " + jwtValue))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void publicEndpointNeedsNoToken() throws Exception {
        mvc.perform(get("/api/public/ping"))
                .andExpect(status().isOk())
                .andExpect(content().string("pong"));
    }

    @Test
    void missingTokenIs401() throws Exception {
        mvc.perform(get("/api/orders"))
                .andExpect(status().isUnauthorized());
    }

    @Test
    void validSignedTokenWorks() throws Exception {
        mvc.perform(get("/api/orders")
                        .header(HttpHeaders.AUTHORIZATION,
                                "Bearer " + validToken()))
                .andExpect(status().isOk())
                .andExpect(content().string("subject=alice"));
    }

    @Test
    void malformedTokenIs401() throws Exception {
        expectUnauthorized("not-a-jwt");
    }

    @Test
    void expiredTokenIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, AUDIENCE,
                now.minusSeconds(1800), now.minusSeconds(1800),
                now.minusSeconds(1200),
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void notBeforeInTheFutureIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, AUDIENCE,
                now.minusSeconds(60), now.plusSeconds(600),
                now.plusSeconds(720),
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void wrongIssuerIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                "https://attacker.example.test", AUDIENCE,
                now.minusSeconds(30), now.minusSeconds(30),
                now.plusSeconds(300),
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void wrongAudienceIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, "urn:another-api",
                now.minusSeconds(30), now.minusSeconds(30),
                now.plusSeconds(300),
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void invalidSignatureIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, AUDIENCE,
                now.minusSeconds(30), now.minusSeconds(30),
                now.plusSeconds(300),
                "orders.read", OTHER_KEY));
    }

    @Test
    void excessiveLifetimeIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, AUDIENCE,
                now.minusSeconds(60), now.minusSeconds(60),
                now.plusSeconds(1800),
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void missingExpiryIs401() throws Exception {
        Instant now = Instant.now();
        expectUnauthorized(token(
                ISSUER, AUDIENCE,
                now.minusSeconds(30), now.minusSeconds(30),
                null,
                "orders.read", TRUSTED_KEY));
    }

    @Test
    void validTokenButMissingScopeIs403() throws Exception {
        Instant now = Instant.now();
        String value = token(
                ISSUER, AUDIENCE,
                now.minusSeconds(30), now.minusSeconds(30),
                now.plusSeconds(300),
                "profile", TRUSTED_KEY);
        mvc.perform(get("/api/orders")
                        .header(HttpHeaders.AUTHORIZATION, "Bearer " + value))
                .andExpect(status().isForbidden());
    }
}
~~~

**Runnability explanation:** the test context contains the production decoder and a **@Primary** test decoder. SecurityFilterChain receives the test decoder backed by the JVM-generated RSA public key. JWTs in each test are signed with the corresponding test private key. Because **.with(jwt())** is not used, real requests pass through BearerTokenAuthenticationFilter and the Nimbus decoder, testing cryptographic signatures and validators without connecting to an IdP.

Run from the root of a Boot project with a Gradle wrapper:

~~~bash
./gradlew test --tests com.example.jwtlimits.JwtLimitsTest
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests com.example.jwtlimits.JwtLimitsTest
~~~

**Expected when the project environment is configured properly:** 12 tests pass. Public GET and valid access JWT return **200**; missing/malformed/expired/not-yet-valid/wrong-issuer/wrong-audience/bad-signature/excessive-TTL/missing-exp tokens return **401**; valid token lacking scope returns **403**. These are expectations from the sample config, not a verified run output. With a real AS, add end-to-end tests over HTTPS/JWKS using AS-issued tokens.

### 6.2. Additional Cases to Test When Enabling a Denylist

The test suite above does **not** include revocation beyond JWT validation. When deploying a real denylist, add:

| Test | Expectation |
| --- | --- |
| Valid signature/claims, jti **not** denylisted | Authenticated, then checked for permissions |
| Revoke a jti, resend **the same JWT** | Returns **401 invalid_token** when denylist integrates into authentication validation |
| Two JWTs with same sub yet different jtis; revoke one | Only the targeted token is rejected if policy is per-token revocation |
| JWT missing jti in a system requiring jti revocation | Fails per explicit policy, never slips through |
| Two API instances reading shared Redis/DB state | Rejected consistently after revocation write succeeds |
| Redis/DB unresponsive | Follows approved fail-closed/fail-open policy; emits logs/alerts |
| Denylist entry TTL expires **after the JWT expires** | JWT remains rejected due to **exp**, never “revives” |
| AS rotates signing keys / JWK cache refreshes | Tokens signed with new/old keys behave correctly during transition |

**Test design must not merely assert Redis has a key**: send requests through the filter chain, assert HTTP status, and verify zero side effects in controllers/services.

## 7. Evaluating Real Tokens in Production

When the resource server consumes JWTs from a real AS, observe layer by layer:

1. **No token:** check 401 and **WWW-Authenticate: Bearer** header where appropriate.
2. **Unparseable JWT or bad signature:** confirm the decoder returns an authentication failure without entering the controller. Never expose key details or sensitive JWTs in logs.
3. **exp / nbf / iat:** test well outside clock-skew bounds, sync clocks via NTP, and confirm max TTL policies align with the AS.
4. **iss and aud:** test a valid token issued for **another API**; it must be rejected.
5. **Scope:** test a valid token lacking permissions to confirm 403, never treating all signed JWTs as full access.
6. **Logout/revocation:** measure from revocation write time to the last accepted request, not merely whether the UI cleared its token.
7. **JWKS/AS outage:** verify caching, timeouts, key rotation, and how the API handles tokens with a new **kid**; never bypass signature validation when the JWK endpoint fails.
8. **Replay/leakage:** enforce HTTPS, keep bearer tokens out of URL queries, stack traces, and access logs. Clients should store tokens appropriately for their security model; if cookies are used, evaluate CSRF separately.
9. **Session/refresh:** verify refresh token rotation, reuse detection, locked sessions, and absolute session caps at the AS—those are not performed automatically by a Resource Server JWT decoder.
10. **Multiple resource servers:** align issuer/audience policies, key trust, skew, and revocation data across all participating APIs.

### Quick Troubleshooting of Common Errors

| Symptom | Causes to Distinguish | Fix |
| --- | --- | --- |
| 401 even though payload decodes | Base64 decoding does not prove signature; exp/iss/aud/nbf may fail | Check decoder messages, trusted JWKs, issuer/audience, and timestamps |
| 401 right after AS key rotation | Stale JWK cache, new token **kid** unrecognized, wrong JWKS URI | Check JWKS reachability, algorithms, cache refresh, and rotation plan |
| Token still works after logout | Resource server does not check revocation state | Short TTLs; add denylist/introspection if pre-exp blocking is required |
| Token revoked on one node yet accepted on another | Local-only denylist or unsynced cache | Use shared state and define consistency SLAs |
| Token does not expire despite “15-minute limit” | AS still issues long exp or API checks exp without checking **exp - iat** | Cap TTL at AS and/or add validator as shown |
| 403 even though JWT signature is valid | Token authenticated yet lacks **scope/role** | Check authority mapping and endpoint policy |
| Token with only another **aud** reaches API | Audience validator not configured | Add fixed aud validator matching resource API |
| Tokens rejected right near exp | Clock skew across services or temporal validator policy | Sync clocks, bound skew, and test intentionally past margins |
| **jwt()** tests pass yet real tokens fail | Tests bypassed decoder and signatures | Use self-signed JWTs with test keys and real decoder as in section 6 |
| Token still works after password change | JWT is a claim snapshot; API checks no account status | Add revocation/session-version checks or lower TTL as required |

## 8. Pre-Deployment Decision Checklist

- **What is the maximum acceptable revocation lag?** If 5 minutes is acceptable, short-lived access tokens may suffice. If seconds are required, pure stateless JWTs are usually insufficient.
- **Who is authorized to revoke?** User logout, admin account lock, stolen-token detection, or role changes each need authenticated, audited policies.
- **Is revocation data shared across API instances?** Are TTLs, failure recovery, and fail behavior defined?
- **Does the AS issue access tokens matching the contract?** issuer, audience, iat, exp, jti, scope, algorithm/kid, issuance limits, and refresh rotation.
- **Does the resource server reject invalid tokens at the authentication layer?** Never confuse 401 with authorization 403; never merely Base64-decode.
- **Do tests verify real signatures?** Test signatures, exp, iss, aud, and TTL through JwtDecoder. For scopes/endpoints you may add .with(jwt()) tests for authorization branches.
- **Are emergency procedures ready?** Compromised signing key, leaked refresh tokens, JWKS outages, denylist outages, and cache-induced revocation lag.
- **Do operational reports measure the real risk window?** Time from logout/revocation until the last accepted request matters more than “token deleted” state in the UI.

**Conclusion:** With JWT access tokens, **short exp limits exposure, rather than providing instant revocation**. Resource Servers must thoroughly verify signature, issuer, audience, lifetime, and permissions. If tokens must be invalidated before exp, add a denylist/introspection/trusted state store and test real API requests after revocation rather than testing only that logout succeeded.
