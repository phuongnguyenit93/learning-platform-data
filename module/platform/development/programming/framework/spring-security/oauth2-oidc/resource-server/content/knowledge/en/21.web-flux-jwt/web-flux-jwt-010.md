# Testing Invalid Tokens While Still Exercising a Real Reactive Decoder

In a **Spring Security OAuth 2.0/OIDC Resource Server** using **WebFlux**, an HTTP request carrying a Bearer JWT is typically authenticated through `ReactiveJwtDecoder` before Spring Security creates an `Authentication` and enforces authorization rules. When writing tests, we usually want to prove that tokens with an **invalid signature, wrong issuer, wrong audience, expired time, future not-before time, or disallowed algorithm** are genuinely rejected.

A common trap is writing tests with `mockJwt()`, `@WithMockUser`, or mocking `ReactiveJwtDecoder`, and concluding that "the application verifies invalid JWTs." Those tools are useful for **testing authorization**, yet they normally **bypass real JWT decoding and verification**. Tests can stay green even when the real decoder has a misconfigured issuer, omits audience checks, trusts the wrong key, or is not even wired into the security chain.

This lesson focuses on **testing invalid tokens while still exercising a real reactive decoder** in the **JWT in WebFlux** chapter of the **Spring Security OAuth 2.0 OIDC Resource Server** module. We will build a self-contained test environment: generate a test RSA keypair, sign real JWTs with the test private key, use a real `NimbusReactiveJwtDecoder` configured with the matching public key, send tokens over HTTP via `WebTestClient`, and cross-check results with `StepVerifier` when testing the decoder directly.

> All issuer URLs, audiences, keys, and tokens in the examples are **test data** and must never be used against production APIs. Code snippets follow common Spring Boot 3.x / Spring Security 6.x API styles; when running against a specific version, use the dependencies and overloads supported by that version.

## 1. What Must the Test Results Prove?

Suppose the Orders API accepts only JWT access tokens with:

~~~text
iss = https://issuer.example.test/realms/shop
aud contains orders-api
JWS alg = RS256 (allowlisted)
valid signature under the test's trusted RSA public key
exp not expired
nbf not in the future beyond permitted clock skew
scope contains orders.read when calling GET /api/orders
~~~

A real test must prove at least three distinct layers:

| Layer | What is tested? | Example outcome |
|---|---|---|
| **JWS/decoder** | JWT syntax, signature, key, algorithm, and claims per validators | JWT with invalid signature → authentication fails |
| **Reactive security filter chain** | Bearer token is extracted from the HTTP request and passed to the active `ReactiveJwtDecoder` | HTTP request with invalid JWT → usually 401 |
| **Authorization** | Does the authenticated principal have permission to call the endpoint? | Valid JWT missing `SCOPE_orders.read` → usually 403 |

Proper testing must never conflate:

~~~text
401 due to bad JWT signature     → authentication / decoder
401 due to wrong issuer/audience → authentication / JWT validators
403 due to missing scope         → authorization
404 due to missing handler       → routing/controller, proves nothing about decoder
503 when JWKS is unreachable     → may be infrastructure failure, does not prove token invalid
~~~

### 1.1. Execution Flow That Must Be Preserved in Tests

~~~mermaid
sequenceDiagram
    participant T as Test (WebTestClient)
    participant W as WebFlux Server
    participant F as Spring Security WebFilter
    participant D as Real ReactiveJwtDecoder
    participant K as Trusted keys/validators
    T->>W: GET /api/orders + Authorization: Bearer <JWT>
    W->>F: HTTP exchange
    F->>D: decode(token)
    D->>K: JWS verification + iss/aud/exp/nbf
    alt Invalid token
        K-->>D: JWT validation error
        D-->>F: Mono.error(...)
        F-->>T: 401 / Bearer challenge
    else Valid token
        K-->>D: Verified Jwt
        D-->>F: Mono<Jwt>
        F->>F: JwtAuthenticationToken + authorities
        F->>W: HTTP authorization
        W-->>T: 200 if scope suffices, or 403 if lacking permission
    end
~~~

Here "real" does not mean calling a production Authorization Server or using real user tokens. A **real decoder** is an actual cryptographic/claim-validation implementation like `NimbusReactiveJwtDecoder`, configured with **test keys** and real validators; tests can run entirely locally or in CI.

## 2. Three Test Types: Avoid Confusing Their Purposes

### 2.1. Testing Authorization with `mockJwt()`

In WebFlux, Spring Security Test provides `SecurityMockServerConfigurers.mockJwt()`:

~~~java
webTestClient
    .mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

This test **simulates** an authenticated principal and assigns arbitrary authorities. It is great for testing `hasAuthority(...)`, route rules, or controllers, yet **does not prove** JWT signatures are verified, issuers match, or `exp` is evaluated. If you attach invalid claims via `mockJwt()`, they can still be treated as an authenticated `Jwt` inside the test context.

### 2.2. Testing `ReactiveJwtDecoder` Directly with `StepVerifier`

~~~java
StepVerifier.create(realDecoder.decode(token))
    .expectError(JwtException.class)
    .verify();
~~~

This test genuinely invokes `decode(token)` and checks the error signal in `Mono`. It **does not prove** the WebFlux security chain selected the right decoder or handled the `Authorization` header properly. This is the decoder/validator test layer.

### 2.3. Integrated HTTP Testing with `WebTestClient` and Real Bearer Tokens

~~~java
webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers -> headers.setBearerAuth(invalidSignedToken))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

If the test application uses `oauth2ResourceServer(oauth2 -> oauth2.jwt(...))` and the `ReactiveJwtDecoder` bean is **not mocked**, this HTTP request traverses the actual authentication pipeline. **This is the central focus of this lesson.**

| Tool / approach | Verifies real signatures and JWT claims? | Passes through HTTP security filters? | Purpose |
|---|---|---|---|
| `mockJwt()` | **No** | Covers the authorization/security test slice, with simulated authentication | Test permissions |
| `@WithMockUser` | **No** | Simulated authentication | Test permissions/controller |
| Mock `ReactiveJwtDecoder` returning `Mono.error(...)` | **No** | Potentially yes | Test how app handles decoder errors |
| Calling `NimbusReactiveJwtDecoder.decode(token)` with `StepVerifier` | **Yes** | No | Test cryptography + validators |
| `WebTestClient` sending real signed Bearer JWT, using real decoder | **Yes** | **Yes** | Test end-to-end auth flow in the app |
| `WebTestClient` sending token against a test JWKS HTTP server | **Yes**, including HTTP key fetch | **Yes** | Test full decoder/JWKS/key-selection |

## 3. Designing the Negative JWT Dataset

A meaningful test suite needs a **positive control**: a valid JWT accepted under the same configuration. If every token returns 401 due to a wrong URL, missing decoder, or failed app startup, "negative tests" easily create a false sense of security.

### 3.1. Variants to Test

| Test token | What to change | Layer that must reject |
|---|---|---|
| Valid | RS256, valid key/iss/aud/time/scope | Allowed; 200 if endpoint works |
| Invalid signature | Signed with a **different private key** | JWS verification → 401 |
| Payload tampered after signing | Alter payload while keeping original signature | JWS verification → 401 |
| Wrong issuer | Signed with valid key, `iss` differs from trusted issuer | Issuer validator → 401 |
| Wrong audience | Signed with valid key, `aud` omits `orders-api` | Audience validator → 401 |
| Expired | `exp` far enough in the past to exceed clock skew | Timestamp validator → 401 |
| Not yet valid | `nbf` far enough in the future | Timestamp validator → 401 |
| Disallowed algorithm | `alg=none` or HS256 when only RS256 is permitted | JOSE/algorithm policy → 401 |
| Malformed token | Unparseable JWT | Decoder parsing → 401 |
| Valid token lacking scope | Properly signed JWT, `scope` lacks `orders.read` | Authorization → 403 |
| Missing Bearer token | Omit `Authorization` | Authentication entry point → 401 |

**Never cram all faults into a single token.** If one JWT simultaneously has an invalid signature, wrong issuer, and expired `exp`, the decoder may stop at the signature check; a 401 test proves nothing about whether issuer/expiry validators ran. Each case should **vary only one critical condition**, keeping all other conditions valid.

### 3.2. No Production Private Keys Needed

In tests, generate an RSA 2048-bit (or stronger per policy) keypair:

~~~java
KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
generator.initialize(2048);
KeyPair testKeys = generator.generateKeyPair();
~~~

- **Private key**: used solely to sign test JWTs at test runtime.
- **Public key**: given to `NimbusReactiveJwtDecoder` as the trusted key.
- **Wrong key**: use a separate RSA pair to produce invalidly signed JWTs for the decoder.
- **Never** copy a real Authorization Server private key into tests or repositories.

### 3.3. Timestamps and Clock Skew

JWT libraries normally allow a certain clock skew window; therefore:

~~~text
exp = now - 1 second
~~~

is not necessarily a stable negative test. For default tests, use an `exp` further in the past than clock skew (e.g., several minutes or one hour) and an `nbf` sufficiently in the future. If testing exact skew boundaries, control `Clock`/validators per your version's API.

Avoid hardcoding a fixed timestamp like the year 2026 and expecting an "unexpired token" test to still pass years later. For positive controls, derive `iat`, `nbf`, and `exp` from test execution time or a `Clock` injected across the policy.

## 4. Test Application Setup: Real WebFlux + Resource Server

In a Spring Boot WebFlux project, basic dependencies:

~~~gradle
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'io.projectreactor:reactor-test'
}
~~~

This Gradle example targets a **WebFlux** application; avoid mixing in Servlet `spring-boot-starter-web` which unexpectedly alters the web application type. When managing dependencies without Boot starters, ensure compatible Spring Security JWT/JOSE and Nimbus JOSE JWT modules are included.

### 4.1. Security Chain Accepting Only the Right Scope

A WebFlux configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

import static org.springframework.security.config.Customizer.withDefaults;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers(HttpMethod.GET, "/api/orders")
                    .hasAuthority("SCOPE_orders.read")
                .anyExchange().denyAll()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(withDefaults()))
            .build();
    }
}
~~~

This is a baseline illustrative configuration. When multiple `SecurityWebFilterChain` beans exist, ensure requests actually select the chain with `oauth2ResourceServer(...jwt(...))`; an overly broad chain ordered earlier can shadow the API chain. The integration test below uses a minimal test application to keep this controlled.

### 4.2. Configuring a Real Decoder Using a Test Public Key

~~~java
NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
    .withPublicKey((RSAPublicKey) testKeyPair.getPublic())
    .signatureAlgorithm(SignatureAlgorithm.RS256)
    .build();
~~~

This implementation genuinely verifies **RSA JWS signatures**, rather than just parsing claims. To test issuer/audience/timestamps, attach validators:

~~~java
OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
    jwt.getAudience().contains("orders-api")
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token", "Audience is not accepted", null));

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(
            "https://issuer.example.test/realms/shop"),
        audienceValidator
    )
);
~~~

Key point: `setJwtValidator(...)` **replaces** the validator configured on the decoder. Composing `JwtValidators.createDefaultWithIssuer(issuer)` preserves the default validator set including version-appropriate issuer/timestamp checks before adding audience. If the contract mandates `exp` presence, `typ=at+jwt`, or custom claims, add the corresponding validators rather than assuming all profile checks are included automatically.

### 4.3. Why Use a Public Key Before JWKS in the First Test?

`NimbusReactiveJwtDecoder.withPublicKey(...)` is still a **real decoder**. It verifies signatures with the public key without requiring an HTTP JWKS server, isolating tests from networking and making them easy to control:

~~~text
Test RSA private key → signs real token
Test RSA public key  → NimbusReactiveJwtDecoder verifies for real
WebTestClient        → HTTP request passes through security filters
~~~

This test level is well suited for proving **invalid tokens are rejected by the decoder**. However, it **does not test** JWKS fetching, `kid` selection, cache refreshing, or key rotation. Those require an integration test layer with a test JWKS endpoint, covered in a later section.

## 5. Full Example: `WebTestClient` Sending Real RSA-Signed JWTs

Below is a **self-contained test configuration** Java file. It declares:

- A minimal Spring Boot WebFlux application used only in tests.
- A real `SecurityWebFilterChain` with `oauth2ResourceServer().jwt()`.
- A real `NimbusReactiveJwtDecoder` trusting a test-generated RSA public key.
- JWTs signed via Nimbus JOSE/JWT using the **matching private key**.
- A GET `/api/orders` controller returning `ok` as a positive control.
- HTTP tests using real Bearer headers, **never calling `mockJwt()`**.

### 5.1. `ReactiveJwtHttpIntegrationTest.java`

~~~java
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.List;
import java.nio.charset.StandardCharsets;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.PlainJWT;
import com.nimbusds.jwt.SignedJWT;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

import static org.springframework.security.config.Customizer.withDefaults;

@SpringBootTest(
    classes = ReactiveJwtHttpIntegrationTest.TestApp.class,
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class ReactiveJwtHttpIntegrationTest {

    static final String ISSUER =
        "https://issuer.example.test/realms/shop";
    static final String AUDIENCE = "orders-api";

    @Autowired
    WebTestClient client;

    @Autowired
    KeyPair signingKey;

    // Test-only app: never uses production Authorization Server.
    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({TestSecurity.class, OrdersEndpoint.class})
    static class TestApp {}

    @Configuration(proxyBeanMethods = false)
    static class TestSecurity {

        @Bean
        KeyPair signingKey() throws GeneralSecurityException {
            KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        }

        @Bean
        ReactiveJwtDecoder reactiveJwtDecoder(KeyPair signingKey) {
            NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                    .withPublicKey((RSAPublicKey) signingKey.getPublic())
                    .signatureAlgorithm(SignatureAlgorithm.RS256)
                    .build();

            OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Audience is not accepted",
                            null
                        )
                    );

            decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(ISSUER),
                    audience
                )
            );

            return decoder;
        }

        @Bean
        SecurityWebFilterChain securityWebFilterChain(
                ServerHttpSecurity http) {
            return http
                .authorizeExchange(exchanges -> exchanges
                    .pathMatchers(HttpMethod.GET, "/api/orders")
                        .hasAuthority("SCOPE_orders.read")
                    .anyExchange().denyAll()
                )
                .oauth2ResourceServer(oauth2 ->
                    oauth2.jwt(withDefaults()))
                .build();
        }
    }

    @RestController
    static class OrdersEndpoint {
        @GetMapping("/api/orders")
        Mono<String> orders() {
            return Mono.just("ok");
        }
    }

    // Fresh claims per test based on current runtime clock.
    private JWTClaimsSet.Builder validClaims() {
        Instant now = Instant.now();
        return new JWTClaimsSet.Builder()
            .issuer(ISSUER)
            .subject("test-user")
            .audience(List.of(AUDIENCE))
            .issueTime(Date.from(now.minusSeconds(30)))
            .notBeforeTime(Date.from(now.minusSeconds(30)))
            .expirationTime(Date.from(now.plusSeconds(300)))
            .claim("scope", "orders.read");
    }

    // Real JWS: uses test private key to generate an RS256 signature.
    private String sign(
            JWTClaimsSet claims,
            RSAPrivateKey privateKey) throws JOSEException {

        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
            .type(JOSEObjectType.JWT)
            .keyID("test-rsa-key")
            .build();

        SignedJWT signed = new SignedJWT(header, claims);
        signed.sign(new RSASSASigner(privateKey));
        return signed.serialize();
    }

    private String validToken() throws JOSEException {
        return sign(
            validClaims().build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );
    }

    private void expectUnauthorized(String bearerToken) {
        client.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(bearerToken))
            .exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void validSignedJwtWithReadScopeIsAccepted() throws Exception {
        client.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(validToken()))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("ok");
    }

    @Test
    void jwtSignedByDifferentKeyIsRejected() throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair untrusted = generator.generateKeyPair();

        String token = sign(
            validClaims().build(),
            (RSAPrivateKey) untrusted.getPrivate()
        );

        expectUnauthorized(token);
    }

    @Test
    void tamperingPayloadAfterSigningIsRejected() throws Exception {
        String original = validToken();
        String[] parts = original.split("\\.", -1);

        // Alter payload WITHOUT re-signing: old signature is invalid.
        String changedPayload = Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(
                "{\"sub\":\"changed-after-signing\"}"
                    .getBytes(StandardCharsets.UTF_8)
            );

        String tampered =
            parts[0] + "." + changedPayload + "." + parts[2];
        expectUnauthorized(tampered);
    }

    @Test
    void wrongIssuerIsRejectedEvenWithValidSignature()
            throws Exception {
        String token = sign(
            validClaims()
                .issuer("https://other-issuer.example.test")
                .build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );

        expectUnauthorized(token);
    }

    @Test
    void wrongAudienceIsRejectedEvenWithValidSignature()
            throws Exception {
        String token = sign(
            validClaims()
                .audience(List.of("billing-api"))
                .build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );

        expectUnauthorized(token);
    }

    @Test
    void expiredJwtIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(
            validClaims()
                .issueTime(Date.from(now.minusSeconds(7200)))
                .notBeforeTime(Date.from(now.minusSeconds(7200)))
                .expirationTime(Date.from(now.minusSeconds(3600)))
                .build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );

        expectUnauthorized(token);
    }

    @Test
    void notYetValidJwtIsRejected() throws Exception {
        Instant now = Instant.now();
        String token = sign(
            validClaims()
                .notBeforeTime(Date.from(now.plusSeconds(3600)))
                .build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );

        expectUnauthorized(token);
    }

    @Test
    void unsignedPlainJwtIsRejected() {
        String token = new PlainJWT(validClaims().build())
            .serialize();
        expectUnauthorized(token);
    }

    @Test
    void malformedJwtIsRejected() {
        expectUnauthorized("this-is-not-a-jwt");
    }

    @Test
    void validJwtWithWrongScopeIsForbidden() throws Exception {
        String token = sign(
            validClaims()
                .claim("scope", "orders.create")
                .build(),
            (RSAPrivateKey) signingKey.getPrivate()
        );

        client.get()
            .uri("/api/orders")
            .headers(headers -> headers.setBearerAuth(token))
            .exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void missingBearerTokenIsUnauthorized() {
        client.get()
            .uri("/api/orders")
            .exchange()
            .expectStatus().isUnauthorized();
    }
}
~~~

### 5.2. Why Is This an Integration Test of a Real Reactive Decoder?

In the code above, `WebTestClient` requests travel through the test HTTP server port and the WebFlux security filter chain. The `ReactiveJwtDecoder` bean created with `NimbusReactiveJwtDecoder.withPublicKey(...)` is **not a Mockito mock**, and is used by `oauth2ResourceServer().jwt()`.

JWTs are signed with `RSASSASigner` using the test private key. The decoder uses the paired public key and runs its own signature and validator checks. Thus:

- Valid token yields 200: **positive control** confirms the setup works.
- Signature from another key yields 401: proves the Resource Server **does not accept arbitrary structurally valid JWTs**.
- Same key with wrong issuer/audience/time yields 401: exercises **claim validators**.
- Valid token with wrong scope yields 403: distinguishes **authentication** from **authorization**.
- Missing Bearer header yields 401: tests the authentication entry point.

`RANDOM_PORT` runs the test with a real HTTP server on a random port; it exercises WebFlux filters just like a client request rather than invoking a Java method directly. When faster tests are needed, `WebTestClient.bindToApplicationContext(...)` with appropriate Spring Security mock server configurers can be used, provided you still send the **Bearer token via the header** and ensure the real decoder is wired. Never accidentally call `mutateWith(mockJwt())` in tests meant for the decoder.

### 5.3. Differences from Production Systems

This test deliberately avoids calling a real issuer, discovery metadata, or JWKS HTTP endpoint. It replaces only the **key source** with a test RSA public key; cryptography and claim validation remain real.

If production uses `issuer-uri` + JWKS, add **dedicated tests** for:

- Fetching the JWK Set from the right URL and a trusted source.
- Selecting public keys by `kid` and allowlisted algorithms.
- Public key rotation and JWKS cache refreshes.
- JWKS endpoint errors/timeouts or missing matching keys.
- The application's real issuer/audience/token-profile requirements.

Do not equate "ran `NimbusReactiveJwtDecoder` with a public key" with "tested full discovery and JWKS lifecycle." The two test suites complement each other.

## 6. Testing `ReactiveJwtDecoder.decode(...)` Directly with `StepVerifier`

When an HTTP test returns 401, the failure could originate in the Bearer token resolver, decoder, authentication entry point, or a custom WebFilter. To isolate **claim and signature** checks, call the real decoder used by the application directly:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.test.StepVerifier;

import static org.assertj.core.api.Assertions.assertThat;

// Members added to the test class from Section 5.
@Autowired
ReactiveJwtDecoder actualDecoder;

@Test
void decoderAcceptsValidJwt() throws Exception {
    String token = validToken();

    StepVerifier.create(actualDecoder.decode(token))
        .assertNext(jwt -> {
            assertThat(jwt.getSubject()).isEqualTo("test-user");
            assertThat(jwt.getIssuer().toString()).isEqualTo(ISSUER);
            assertThat(jwt.getAudience()).contains(AUDIENCE);
        })
        .verifyComplete();
}

@Test
void decoderRejectsSignedJwtWithWrongAudience() throws Exception {
    String token = sign(
        validClaims().audience(List.of("billing-api")).build(),
        (RSAPrivateKey) signingKey.getPrivate()
    );

    StepVerifier.create(actualDecoder.decode(token))
        .expectError(JwtException.class)
        .verify();
}
~~~

These methods rely on `validToken()`, `validClaims()`, `sign(...)`, and `signingKey` from Section 5's test class. Place fields and methods in the proper class scope; this is not a standalone class to copy verbatim into a new file.

### 6.1. Why Is `StepVerifier` Suitable?

`ReactiveJwtDecoder.decode(String)` returns `Mono<Jwt>`. Valid JWTs emit `onNext(Jwt)` then `onComplete`, whereas invalid JWTs emit `onError(...)`. Reactive tests must actually subscribe:

~~~text
Valid:
  Mono<Jwt> → onNext(verified JWT) → onComplete

Invalid:
  Mono<Jwt> → onError(JwtException subtype)
~~~

An anti-pattern:

~~~java
// ANTI-PATTERN: non-null Mono does NOT prove the token is valid.
assertNotNull(decoder.decode(invalidToken));
~~~

The `Mono` object can be non-null even when subscribing emits an error. Therefore, tests must assert the **reactive signal** using `StepVerifier` or an equivalent subscriber.

### 6.2. Avoid Depending on Internal Messages

JWTs with bad signatures may be wrapped by Spring Security/Nimbus into different exception subtypes and messages across versions. When testing policy, asserting `JwtException` or an application-normalized stable exception type is usually sufficient. Never print raw tokens into CI failure messages or logs.

### 6.3. Decoder Tests and HTTP Integration Tests Complement Each Other

If `StepVerifier` rejects the wrong audience while HTTP requests still return 200, the app may **not be using that decoder** in the chain or a security test override may be active. If HTTP returns 401 while `StepVerifier` accepts the token, the failure may lie in the Bearer resolver, filter chain, or another authorization config. That is why both **direct decoder tests** and **HTTP tests through security filters** are needed.

## 7. Proving HTTP Requests Actually Call the Decoder

If you need proof that the decoder was invoked, wrap the real decoder in a decorator that increments a counter on subscription and **passes the exact token unchanged to the real decoder**.

~~~java
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import reactor.core.publisher.Mono;

final class CountingReactiveJwtDecoder implements ReactiveJwtDecoder {
    private final ReactiveJwtDecoder delegate;
    private final AtomicInteger subscriptions = new AtomicInteger();

    CountingReactiveJwtDecoder(ReactiveJwtDecoder delegate) {
        this.delegate = Objects.requireNonNull(delegate);
    }

    @Override
    public Mono<Jwt> decode(String token) {
        return Mono.defer(() -> {
            subscriptions.incrementAndGet();
            return delegate.decode(token);
        });
    }

    int calls() {
        return subscriptions.get();
    }
}
~~~

In the test configuration, **replace** the existing decoder bean with the decorator (do not register two competing beans):

~~~java
@Bean
CountingReactiveJwtDecoder reactiveJwtDecoder(KeyPair signingKey) {
    NimbusReactiveJwtDecoder real = NimbusReactiveJwtDecoder
        .withPublicKey((RSAPublicKey) signingKey.getPublic())
        .signatureAlgorithm(SignatureAlgorithm.RS256)
        .build();

    OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
        jwt.getAudience().contains(AUDIENCE)
            ? OAuth2TokenValidatorResult.success()
            : OAuth2TokenValidatorResult.failure(
                new OAuth2Error("invalid_token", "Wrong audience", null));

    real.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audienceValidator
        )
    );

    return new CountingReactiveJwtDecoder(real);
}
~~~

An HTTP test can read `calls()` before and after a request and verify it incremented by one. Ensure tests **do not run in parallel** when sharing a counter; avoid asserting exact counts while concurrent requests may execute simultaneously. With complex redirect/filter setups, know how many times the decoder is expected to run.

Key point: this is a **delegating wrapper**, not a mock fabricating `Mono.just(fakeJwt)` or `Mono.error(...)` on demand. Signatures and validators are still verified by the real `NimbusReactiveJwtDecoder`.

You do not need a counter on every test: a 200 positive control, a 401 negative signature test, and 401 negative claim tests are already strong evidence. A decorator helps when investigating wiring bugs, multiple chains/decoder beans, or the risk of tests accidentally using mocks.

## 8. Testing Disallowed Signing Algorithms

A JWT carries a self-declared JOSE header such as `alg=HS256`, `alg=RS256`, `alg=none`, or another algorithm. The Resource Server **must never trust an arbitrary algorithm just because the header requests it**.

The decoder in Section 5 allowlists:

~~~java
.signatureAlgorithm(SignatureAlgorithm.RS256)
~~~

Thus, unsigned tokens or HS256-signed tokens must be rejected even when issuer, audience, scope, and timestamps look valid.

### 8.1. Unsigned / `alg=none` Tokens

~~~java
String unsigned = new PlainJWT(validClaims().build()).serialize();
expectUnauthorized(unsigned);
~~~

`PlainJWT` carries no required JWS signature. This negative test verifies the application rejects payload-only tokens.

### 8.2. Test HS256 Tokens

A test method added to the integration test class from Section 5:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.MACSigner;
import com.nimbusds.jwt.SignedJWT;

@Test
void hs256TokenIsRejectedByRs256OnlyDecoder() throws Exception {
    byte[] testOnlyHmacKey =
        "01234567890123456789012345678901"
            .getBytes(StandardCharsets.UTF_8);

    SignedJWT jwt = new SignedJWT(
        new JWSHeader(JWSAlgorithm.HS256),
        validClaims().build()
    );
    jwt.sign(new MACSigner(testOnlyHmacKey));

    expectUnauthorized(jwt.serialize());
}
~~~

The HMAC key is only a dummy test string, **never a secret for production**. HS256 JWTs must be disallowed in an RS256-only setup. If the Authorization Server legitimately uses an additional algorithm, establish an explicit key/algorithm trust contract and test it thoroughly rather than enabling algorithms based on header content.

### 8.3. Do Not "Guess" Algorithms from Untrusted Tokens

An anti-algorithm-confusion configuration must satisfy:

~~~text
Expected: RS256 + trusted RSA public key

Incoming RS256, right signer → accept if claims valid
Incoming RS256, wrong signer → reject
Incoming HS256               → reject
Incoming alg=none            → reject
Incoming unsupported alg     → reject
~~~

Never fix tests by turning off signature verification or letting the decoder accept any `alg`. This tests **trust policy**, not merely whether a parser can read a header.

## 9. Wrong Issuer, Wrong Audience, and Token Profile

### 9.1. Wrong Issuer Despite a Valid Signature

The test `wrongIssuerIsRejectedEvenWithValidSignature()` uses the **trusted** private key to sign a JWT with a different `iss`:

~~~text
signature = valid
iss       = https://other-issuer.example.test
aud       = orders-api
time      = valid
scope     = orders.read
~~~

If this token is accepted, the issuer validator may be missing or the HTTP request is hitting a different decoder. A token with both an invalid signature and a wrong issuer **does not prove** issuer validation ran, because the decoder may reject the signature first.

### 9.2. Wrong Audience Despite Valid Signature and Issuer

~~~text
signature = valid
iss       = trusted issuer
aud       = billing-api
time      = valid
scope     = orders.read
~~~

The Orders API must reject JWTs intended for the Billing API. **Audience** identifies which resource is authorized to receive the token; **scope** identifies permitted operations. The string `orders.read` does not compensate for a wrong audience.

| `aud` value | For Orders API | Audience decision |
|---|---|---|
| `["orders-api"]` | Contains exact resource ID | Audience valid |
| `["billing-api"]` | Lacks right resource ID | Reject |
| `["billing-api","orders-api"]` | If issuer/profile allows multi-audience tokens | May pass audience check |
| Missing `aud` | Profile requires audience | Reject |
| `["orders-api-v2"]` | Valid only if allowlist includes this value | Never equate with `orders-api` |

The validator `jwt.getAudience().contains(AUDIENCE)` enforces an **at-least-one matching audience policy**. If the token profile mandates **strictly one audience** or forbids multi-audience tokens, write a stricter validator and add matching negative tests.

### 9.3. Do Not Use OIDC ID Tokens as Access Tokens

An OIDC ID token can be a JWT validly signed by the same issuer yet issued for the **OIDC client**, not the Resource Server API. When the ID token's `aud` is the client ID rather than the resource ID, the Orders API must reject it. In systems enforcing a JWT access token profile such as RFC 9068, you may also need to validate `typ=at+jwt` and profile claims.

A `JwtDecoder` checking only signature + issuer does not guarantee every JWT from that issuer has the right purpose. When adding token-type/profile validation, include a test with a validly signed JWT of the **wrong token type**.

### 9.4. Missing `exp` Is Not Automatically Rejected in Every Profile

Some timestamp validators evaluate `exp`/`nbf` **when the claim is present**, while a contract may also require `exp` to be mandatory. If the Orders API must reject tokens missing `exp`, add a validator:

~~~java
OAuth2TokenValidator<Jwt> expRequired = jwt ->
    jwt.getExpiresAt() != null
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Required exp claim is missing",
                null
            )
        );

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(ISSUER),
        audienceValidator,
        expRequired
    )
);
~~~

This **extends** the decoder's existing `audienceValidator`; do not call `setJwtValidator` twice forgetting that the second call replaces the first. Only with this rule in place does a test with a validly signed token missing `exp` have grounds to expect 401. Without that rule, do not claim every Spring Security version requires `exp` by default.

### 9.5. `iat` Claim in the Future

`iat` records issuance time, yet whether a future `iat` is immediately rejected depends on your validator set and token profile. If the API enforces token-age limits, build an explicit validator for `iat` with clock skew and test a **validly signed** JWT whose `iat` violates policy.

Do not infer from an `nbf` test that the app necessarily enforces the same rule for `iat`: they are two distinct claims.

## 10. Testing JWKS Over HTTP: A Separate Layer from Static Public Keys

In production, Resource Servers commonly use `issuer-uri` and `jwk-set-uri`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/shop
          jwk-set-uri: https://issuer.example.test/realms/shop/jwks
~~~

Then the decoder **fetches, caches, selects JWKs by `kid`/`alg`**, and handles key rotation. A `withPublicKey(...)` test does not exercise this networking/JWKS path. To test it without depending on a production IdP, start an **HTTP test server on loopback** returning a JWKS containing only the test public key.

### 10.1. Creating a JWK from an RSA Public Key

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import java.security.KeyPair;
import java.security.interfaces.RSAPublicKey;

RSAKey publicJwk = new RSAKey.Builder(
        (RSAPublicKey) testKeyPair.getPublic())
    .keyID("test-rsa-key")
    .algorithm(JWSAlgorithm.RS256)
    .build();

String jwksJson = new JWKSet(publicJwk).toString();
~~~

When building `RSAKey` from a public key as above, the JWKS never contains the private signing key. When signing the JWT, the JOSE header sets `keyID("test-rsa-key")` matching the published JWK. **Never export private keys into JWKS, test logs, or shared artifacts.**

### 10.2. Test Server Helper Using JDK `HttpServer`

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.sun.net.httpserver.HttpServer;

import java.io.IOException;
import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.interfaces.RSAPublicKey;
import java.util.concurrent.atomic.AtomicReference;

final class LocalJwksServer implements AutoCloseable {
    private final HttpServer server;
    private final AtomicReference<String> jwksBody;

    LocalJwksServer(KeyPair trustedKeys) throws IOException {
        RSAKey jwk = new RSAKey.Builder(
                (RSAPublicKey) trustedKeys.getPublic())
            .keyID("test-rsa-key")
            .algorithm(JWSAlgorithm.RS256)
            .build();

        jwksBody = new AtomicReference<>(new JWKSet(jwk).toString());

        server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/jwks", exchange -> {
            byte[] bytes = jwksBody.get()
                .getBytes(StandardCharsets.UTF_8);
            exchange.getResponseHeaders()
                .set("Content-Type", "application/json");
            exchange.sendResponseHeaders(200, bytes.length);
            try (OutputStream out = exchange.getResponseBody()) {
                out.write(bytes);
            }
        });

        server.start();
    }

    String jwksUri() {
        return "http://127.0.0.1:"
            + server.getAddress().getPort() + "/jwks";
    }

    void publishJwks(String json) {
        jwksBody.set(json);
    }

    @Override
    public void close() {
        server.stop(0);
    }
}
~~~

This is a **test-only server**, using `http://127.0.0.1` to run locally without provisioning certificates. Production JWKS must use trusted URLs and proper TLS. If the project uses Java modules (`module-info.java`), using `com.sun.net.httpserver` requires configuring the `jdk.httpserver` module appropriately.

### 10.3. Real Decoder Pointing to the Test JWKS Endpoint

~~~java
try (LocalJwksServer jwks = new LocalJwksServer(testKeyPair)) {
    NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
        .withJwkSetUri(jwks.jwksUri())
        .jwsAlgorithm(SignatureAlgorithm.RS256)
        .build();

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(ISSUER),
            audienceValidator
        )
    );

    StepVerifier.create(decoder.decode(validSignedToken))
        .expectNextCount(1)
        .verifyComplete();
}
~~~

This snippet is a **fragment inside a test method**: `testKeyPair`, `validSignedToken`, `audienceValidator`, and `ISSUER` must be constructed as in earlier sections. It exercises a real decoder/JWKS over an HTTP test server. To test the **HTTP `SecurityWebFilterChain`**, expose this JWKS-backed decoder as the bean actually used by the test app, then send tokens via `WebTestClient`.

### 10.4. JWKS Cases Worth Covering

| Test JWKS server | JWT | Expectation |
|---|---|---|
| Has matching public key and `kid` | JWT signed with matching private key | Accepted when claims valid |
| Missing matching key | JWT signed with different private key | Not authenticated |
| Same `kid` but wrong public key | JWT signature does not match | Not authenticated |
| Publishes only disallowed-algorithm key | JWT uses another algorithm outside allowlist | Not authenticated |
| Returns JSON that is not a valid JWKS | JWT needs key | Decoder cannot verify |
| Returns 503 or times out | JWT needs uncached key | No principal created |
| Publishes both old and new keys simultaneously | JWTs signed with each key | Tests rollover window |
| Removes old key before old tokens expire | Old JWT | May be rejected depending on cache; surfaces operational risk |

JWKS caching and `kid` refresh timing depend on the decoder, cache configuration, and Nimbus/Spring Security version. Do not assume changing the JWKS response refreshes every decoder immediately. For tests requiring an empty cache, use a **fresh decoder instance** or reset cache via official APIs rather than relying on test execution order.

### 10.5. `kid` Is Not Proof of Trust

`kid` is merely a key identifier that the token sender can set in the header. The decoder must choose keys from a **trusted configured JWK Set URL**, never taking a URL from `jku` or `x5u` self-declared by an unverified token. `withPublicKey(...)` tests do not prove `kid` selection works; when testing key selection, use a JWKS-aware decoder as shown in this section.

## 11. JWKS Fetch Errors Differ from Bad-Signature Tokens

A bad-signature JWT is a case where **the right key is available and the signature is proven invalid**. A JWKS returning 503 or unreachable can be a case where **no sufficiently trusted key is available to decide**.

~~~text
Case A: Invalid JWS signature
    → Decoder verifies against trusted public key
    → No Authentication created
    → Typically HTTP 401

Case B: JWKS endpoint unavailable, no cached key
    → Decoder lacks a trusted key
    → No Authentication created
    → HTTP status depends on exception mapping (possibly 401/5xx)
~~~

| Case | Meaning | What to investigate |
|---|---|---|
| Bad signature | Token fails cryptographic verification | Wrong signing key, tampered token, forged token |
| Unknown `kid` | No matching key found | Rotation, cache refresh, token profile |
| Wrong `iss` | Issuer validator rejects | Trust configuration, wrong-issuer token |
| Wrong `aud` | Audience validator rejects | Client obtained token for wrong resource |
| Expired JWT | Timestamp validator rejects | TTL, client refresh |
| JWKS 503/timeout | Key source temporarily unavailable | Availability, network, timeout/cache |

Invariant: **never accept an unverified token merely because the key service is failing**.

~~~java
// ANTI-PATTERN: never let a JWT pass when the decoder errors.
return realDecoder.decode(token)
    .onErrorResume(error ->
        Mono.just(trustClaimsWithoutVerification(token)));
~~~

If the system must verify JWTs while the JWKS endpoint is temporarily down, it must rely on a **policy-compliant valid trusted key cache** or pre-designed backup verification. Never build a principal from unverified token claims.

### 11.1. JWKS Caching and Key Lifecycle

~~~text
T0: JWKS = [oldKey]
T1: JWKS = [oldKey, newKey]
T2: issuer starts signing tokens with newKey
T3: last old token expires (+ skew)
T4: issuer removes oldKey from JWKS
~~~

Removing `oldKey` too early can reject valid unexpired older JWTs. JWKS caching makes visibility of old/new keys depend on TTL and refresh policy. Key-rollover tests must cover the **overlap window**, rather than just swapping JSON and expecting all decoders to switch simultaneously.

### 11.2. Separate Test Types for Better Diagnostics

1. **Public-key decoder tests**: cryptographic signatures + claim validators.
2. **JWKS decoder tests**: HTTP key retrieval, `kid`, and caching.
3. **Issuer discovery tests**: issuer metadata and trusted JWK Set URI.
4. **WebFlux HTTP security tests**: chain selection, Bearer handling, `Authentication` creation, and scopes.

When one group fails, it immediately pinpoints the broken link instead of showing only an opaque HTTP 401.

## 12. Choosing the Right Spring Security Test Style

### 12.1. `@SpringBootTest(webEnvironment = RANDOM_PORT)`

The Section 5 example boots the WebFlux application with a real web server on a random port and uses `WebTestClient` to make HTTP calls through filters. This stays close to runtime behavior, at the cost of startup/auto-configuration overhead.

### 12.2. `@WebFluxTest`

`@WebFluxTest` normally loads only the web slice. It is helpful for controllers/serialization, yet **never assume the production decoder and security chain are loaded automatically**. To test JWT validation, import the security config and supply a **real `ReactiveJwtDecoder` + keys/validators**.

### 12.3. `WebTestClient.bindToController(...)`

~~~java
WebTestClient.bindToController(new OrdersController()).build();
~~~

This test style can invoke the controller **without the Spring Security WebFilter chain**. Seeing 200 proves nothing about JWT verification. Bind to the application context with the right security test configurers, or use `@SpringBootTest` as in Section 5.

### 12.4. Why `mutateWith(mockJwt())` Is Not a Decoder Test

~~~java
// ANTI-PATTERN if the goal is testing issuer verification.
webTestClient
    .mutateWith(mockJwt().jwt(jwt ->
        jwt.claim("iss", "https://wrong-issuer.example.test")))
    .get()
    .uri("/api/orders")
    .exchange();
~~~

`mockJwt()` creates a simulated authentication without invoking JWS verification or issuer validators. A wrong `iss` claim in this test **does not necessarily trigger 401**. To test issuer checks, **sign a real JWT with the test private key** carrying the wrong issuer and send it via `Authorization`.

### 12.5. Mocking the Decoder Is Useful Only for Error-Handling Tests

~~~java
when(reactiveJwtDecoder.decode(anyString()))
    .thenReturn(Mono.error(new BadJwtException("synthetic")));
~~~

This mock verifies responses when the decoder reports an error, yet **never tests whether the real decoder catches bad signatures or claims**. Mechanisms like `@MockBean` or `@MockitoBean` (depending on version) that replace the real decoder with a mock also fail this lesson's goal. Keep **mock-based error-handling tests** separate from **real-decoder cryptographic verification tests**.

## 13. HTTP 401, 403, and Selecting the Right Security Chain

A valid JWT with `scope="orders.create"` may pass the decoder, yet GET `/api/orders` requires `SCOPE_orders.read`. The typical HTTP authorization result is:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

A JWT with invalid signature, issuer, audience, or timestamps is normally rejected at authentication:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

Missing Bearer credentials on a protected endpoint:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

These responses follow RFC 6750 examples; exact headers and bodies depend on Spring Security version, entry point, access-denied handler, and chain config. In this lesson's main tests, `expectStatus().isUnauthorized()` and `isForbidden()` verify the **authentication/authorization boundary** without coupling to exact internal `error_description` strings.

### 13.1. Asserting 401 Alone Does Not Prove the Decoder Ran

If a test calls a URL outside the JWT chain or a route with no controller:

~~~java
client.get()
    .uri("/unknown-path")
    .headers(h -> h.setBearerAuth(invalidToken))
    .exchange()
    .expectStatus().isUnauthorized();
~~~

401 could come from an authentication filter or a different chain, without proving the decoder is wired for `/api/orders`. For real proof, test **the same protected URL** for positive/negative controls and observe the decoder directly or via a delegating counter when needed.

### 13.2. `permitAll` Does Not Guarantee Invalid Tokens Are Ignored

A public endpoint:

~~~text
GET /public/catalog, no Bearer token:
    → may be permitted

GET /public/catalog, Authorization: Bearer invalid:
    → may return 401 from the authentication filter
~~~

`permitAll()` applies at authorization, yet a Bearer authentication filter in the same chain may still process credentials and reject them before authorization runs. If public areas should truly be isolated from Bearer authentication, design a separate chain; never use `permitAll` on a protected API to let invalid tokens "pass."

### 13.3. Multiple `SecurityWebFilterChain` Beans

Suppose:

~~~text
@Order(1) public chain: securityMatcher("/public/**")
@Order(2) API chain: securityMatcher("/api/**"), oauth2ResourceServer(jwt)
@Order(3) fallback chain: denyAll
~~~

Invalid-JWT tests must target URLs in the **API chain**, not the public chain or an unmatched URL. Both security chain selection and `authorizeExchange(...)` matchers are first-match-wins per config. A misplaced broad matcher can cause tests to "never reach the decoder" while still returning an error status.

### 13.4. CORS, OPTIONS, and HTTP Methods

Browsers send CORS preflight using `OPTIONS` without a Bearer token. Proper CORS configuration lets preflight pass per policy, while actual HTTP requests must still authenticate. Never use a Bearer-less OPTIONS test to conclude the decoder protects GET/POST APIs. Match the exact route + HTTP method in each test.

### 13.5. Ensure 401 Does Not Echo the Raw Token

When the decoder rejects a token, Spring Security may include Bearer error details in `WWW-Authenticate`. The HTTP response **must never echo the full JWT**, `Authorization` header, private key, sensitive claims, or Nimbus stack traces.

A test can verify:

~~~java
String fakeToken = "invalid-token-for-test-only";

client.get()
    .uri("/api/orders")
    .headers(h -> h.setBearerAuth(fakeToken))
    .exchange()
    .expectStatus().isUnauthorized()
    .expectBody(String.class)
    .value(body -> assertThat(body).doesNotContain(fakeToken));
~~~

This protects the **response body**; if the body is empty or uses another representation, adapt the assertion to the response format. It does not automatically inspect access logs, APM/tracing, or gateways, so add privacy tests at those layers if your organization captures HTTP headers/bodies.

## 14. Mistakes That Produce "False Green" Negative Tests

### 14.1. Passing an Arbitrary String and Seeing 401

~~~java
expectUnauthorized("abc");
~~~

This only proves unparseable strings are rejected. It **proves nothing about RSA signatures, issuer, audience, or timestamp validators**. Use real signed JWTs differing by one condition at a time.

### 14.2. Mocking a `Jwt` Object Only

~~~java
// ANTI-PATTERN for cryptographic validation checks:
Jwt jwt = Jwt.withTokenValue("fake")
    .header("alg", "RS256")
    .claim("iss", "https://issuer.example.test/realms/shop")
    .build();
~~~

Constructing a `Jwt` object does not mean it was signed or verified. That fixture works for testing claim mapping, not JWS verification.

### 14.3. Asserting Errors from a Mock Decoder

~~~java
when(decoder.decode(anyString()))
    .thenReturn(Mono.error(new JwtException("bad")));
~~~

A 401 proves only that the filter handles `Mono.error`, not that the real decoder detects invalid signatures.

### 14.4. Combining Multiple Faults in One JWT

With a JWT signed by the wrong key and carrying the wrong `iss`, which step rejects it depends on the decoder; you cannot conclude the issuer validator works. Keep all other conditions valid in each test case.

### 14.5. Sending a Valid JWT Missing Scope and Expecting 401

Scopes are normally checked at authorization after the decoder builds the principal. When a JWT is valid yet lacks `SCOPE_orders.read`, the expected response is usually **403**, unless a token-profile validator enforces a specialized rule. Keep the two layers distinct.

### 14.6. JWT Expired by Only a Few Seconds

Clock skew can make tests flaky. Put `exp` far enough in the past; when testing skew boundaries, control the clock/validator directly rather than relying solely on virtual schedulers.

### 14.7. Testing Only a Non-Existent Endpoint

A URL without a handler can return 404 when authentication succeeds, breaking positive controls. The main example includes `OrdersEndpoint` actually returning `ok`, eliminating confusion between routing and decoding errors.

### 14.8. Testing a Different Decoder Bean Than the HTTP Chain Uses

A `StepVerifier` calling decoder bean A does not prove the chain uses decoder A if security config uses decoder B or multiple chains exist. Control the context or use a decorator to confirm.

### 14.9. Inferring Algorithm from the Token to Build a Decoder

Never construct a decoder with algorithms/URLs taken from an untrusted header and conclude the JWT is valid. When testing algorithm confusion, the allowlist policy must reside in server configuration, never driven by the token.

### 14.10. Temporarily Removing Claim Validators to Test Signatures

To test signatures in isolation, write a focused low-level decoder test with an explicit policy. **Integration tests**, however, must use the validator set matching the production contract; never strip issuer/audience checks just to make negative tests "run" and accidentally miss gaps.

### 14.11. Leaking Test Secrets/Keys into Production Config

Never reuse test private keys or test public-key configs in production runtimes. With `@SpringBootTest`, isolate test configuration in `src/test/java` or test-only classes so nothing is packaged into the production artifact.

### 14.12. Using `StepVerifier.withVirtualTime` to Fake the System Clock

Reactor's virtual time controls **supported schedulers**, not `Clock.systemUTC()` or `Instant.now()` inside JWT validators. To test exact deadlines/clock skew, inject the clock actually used by the validator or offset claim timestamps well beyond boundaries as in the example.

### 14.13. Enabling Full JWT Logging for Debugging

Never log raw Bearer tokens, private keys, `Authorization` headers, or PII claims in CI. For failure visibility, log error categories, request IDs, and bounded instrumentation. Test tokens are dummy data, yet credential-logging habits tend to get copied into production.

## 15. Preventing Flaky Tests and Cross-Case State Leaks

### 15.1. Generate Test Keys Aligned with Test Context Lifecycle

The RSA keypair should be scoped to the **test context** or test suite so tokens are signed with the exact private key matching the decoder bean's public key. Generating a fresh key per test while the decoder holds an old public key turns every valid test into 401, breaking positive controls.

### 15.2. Generate Fresh JWT Claims per Test

A JWT with a hardcoded near-future `exp` can expire on slow CI runs or when tests are rerun years later. `validClaims()` computing timestamps relative to `Instant.now()` as in Section 5 keeps tests independent of calendar dates.

### 15.3. Prevent Test Ordering from Affecting Caches

JWKS decoders may cache keys. Test A loads JWKS, then Test B swaps the server's public key while reusing the old decoder and hits cached state. For clean-cache cases, use a **new decoder**/context or official cache-reset APIs rather than relying on test order. When intentionally testing caching, control timing and cache state explicitly.

### 15.4. Avoid Shared Mutable Counters During Parallel Execution

`CountingReactiveJwtDecoder` counts subscriptions. If parallel tests share the bean, asserting `before+1` can fail when concurrent requests run. Run instrumented suites sequentially, isolate contexts, or track observations by managed request IDs.

### 15.5. Clean Up Test HTTP Servers and Resources

With `LocalJwksServer`, use `try-with-resources` or test lifecycle hooks to `stop()` the server and avoid leaking ports/sockets. Never leave mock JWKS servers running after tests or bound to public network interfaces.

### 15.6. Never Use a Live Production Authorization Server

Tests must control signing keys, tokens, issuer policy, clocks, and JWKS responses. Calling a production IdP makes tests slow, brittle, noisy in audit logs, or dependent on real credentials. If acceptance tests against a staging IdP are needed, use **test-dedicated** environments and tokens, protect secrets, and never log raw tokens.

## 16. Real JWT Regression Matrix in WebFlux

A solid test suite includes a **positive control**, single-fault invalid tokens, and cases where authentication succeeds yet authorization denies.

| Case | Token / condition | Layer that must check | Typical result |
|---|---|---|---|
| R01 | RS256, valid key/iss/aud/exp/nbf/scope | Decoder + authorization | HTTP 200 |
| R02 | Signed with untrusted private key | JWS signature | HTTP 401 |
| R03 | Tampered payload after signing | JWS signature | HTTP 401 |
| R04 | `alg=none` | JOSE algorithm policy | HTTP 401 |
| R05 | HS256 when only RS256 is allowlisted | JOSE algorithm policy | HTTP 401 |
| R06 | Malformed JWT | Decoder parsing | HTTP 401 |
| R07 | Wrong `iss`, valid signature | Issuer validator | HTTP 401 |
| R08 | Wrong `aud`, valid signature | Audience validator | HTTP 401 |
| R09 | `exp` sufficiently in the past | Timestamp validator | HTTP 401 |
| R10 | `nbf` sufficiently in the future | Timestamp validator | HTTP 401 |
| R11 | Missing `exp` when mandatory custom rule active | Claim/profile validator | HTTP 401 |
| R12 | Wrong `typ` under required access-token profile | Token type validator if configured | HTTP 401 |
| R13 | Valid JWT with only `orders.create` | HTTP `hasAuthority("SCOPE_orders.read")` | HTTP 403 |
| R14 | Missing Bearer token | Authentication entry point | HTTP 401 |
| R15 | Valid JWT whose signer key is absent from JWKS | JWKS/key-selection | Not authenticated |
| R16 | JWKS server timeout, no trusted cached key | JWKS transport/trust | Not authenticated; HTTP code per error policy |

For R11 and R12, Spring Security does not automatically infer every issuer-specific contract. Assert rejection only when the application **has configured the corresponding validator**. For R15/R16, infrastructure errors may differ from `invalid_token`; the invariant is **never granting a principal without verification proof**.

### 16.1. Wiring and Configuration Test Matrix

| Configuration change | Risk to detect |
|---|---|
| Real decoder bean accidentally mocked | Tests only check mock-emitted `Mono` |
| Audience validator dropped from `setJwtValidator` | Tokens issued for other APIs accepted |
| Timestamp validator replaced by audience-only validator | Expired tokens accepted |
| Security chain omits `oauth2ResourceServer().jwt()` | Bearer tokens bypass decoder |
| Public chain has overly broad matcher | Requests hit wrong chain |
| JWT converter changes authority prefix | Valid tokens get 403 or wrong permissions |
| Uncontrolled JWKS caching | Key-rotation tests become order-dependent |
| JWT `typ` profile changed | ID token/access token confusion |
| Custom error handler leaks stack trace/raw token | Credential leakage |

Not every case needs `@SpringBootTest`. Split into decoder-focused `StepVerifier` tests, HTTP integration `WebTestClient` tests, JWKS integration tests, and authorization tests to balance speed and coverage.

## 17. Diagnosing a Failing Negative Test

### 17.1. Wrong Audience Still Returns 200

Check whether the test uses `mockJwt()` or a mock decoder; whether the audience validator is attached to the real bean; whether `setJwtValidator(...)` was called a second time overwriting rules; whether the request hits the right security chain; and whether any custom `onErrorResume` creates a principal from unverified tokens.

### 17.2. Bad Signature Still Returns 200

This requires immediate investigation:

~~~text
HTTP Authorization: Bearer ...
    ↓
Resource Server AuthenticationWebFilter
    ↓
Real ReactiveJwtDecoder?
    ↓
JWS signature verification using trusted key?
    ↓
Authentication only when JWT is valid
~~~

Common causes are simulated authentication in the test, `WebTestClient` bound without security filters, or a custom decoder parsing payloads without verifying signatures. The test JWT should be signed with a **wrong RSA private key** while all other claims remain valid.

### 17.3. Valid Token Returns 401

Check whether private/public keys match, whether `kid` matches JWKS, whether `alg` is allowlisted, whether `iss`/`aud` match the contract, whether the token is unexpired under the test clock, and whether the HTTP request selects the right decoder/chain. When the 200 positive control fails, **never conclude from 401 negative tests that the decoder works**.

### 17.4. Valid Token Returns 403

The decoder may have succeeded while the error lies in authority mapping. For example:

~~~text
JWT claim: scope="orders.read"
Expected GrantedAuthority: SCOPE_orders.read
HTTP rule: hasAuthority("SCOPE_orders.read")
~~~

If a custom converter changed the claim name/prefix or produced different authorities, the JWT authenticates yet lacks permissions. Never remove HTTP authorization rules just to make tests return 200; fix the mapping and contract alignment.

### 17.5. JWKS Server Is Stopped Yet JWT Still Authenticates

The decoder may be holding a **valid cached public key**. That is not necessarily fail-open. When testing key-fetch failures, use a decoder with an empty cache or explicitly control key state; distinguish "no JWKS call needed due to cache" from "skipped verification."

### 17.6. Tests Pass Individually Yet Fail Together

Look for shared mutable state: RSA keypairs replaced mid-suite, stale JWKS cache from an earlier test, closed local HTTP server, parallel calls skewing counters, timestamps too close to skew boundaries, or mutated profile configs. Enforce test isolation and deterministic inputs independent of order.

### 17.7. `StepVerifier` Failures Do Not Indicate HTTP Wiring

`StepVerifier` invokes the decoder directly and does not exercise the Bearer resolver or HTTP security chain. Conversely, an HTTP 401 can occur before reaching the decoder. That is why both **direct decoder tests** and **HTTP Bearer integration tests** are essential.

## 18. Practice Exercises

### Exercise 1. Distinguish Bad Signature from Wrong Issuer

Create two JWTs:

- JWT A: valid `iss`/`aud`/time/scope, signed with an untrusted RSA private key.
- JWT B: valid signature/public key, audience/time/scope, with a different `iss`.

Send both through `WebTestClient` to `GET /api/orders`, confirming both return 401 while `validToken()` still returns 200. Then use `StepVerifier` to prove the real decoder emits an error for each JWT. Never use a mock decoder to fake results.

### Exercise 2. Test Audience for a Different Resource

Sign a valid JWT with `aud=["billing-api"]` and `scope="orders.read"`. Expect the Orders API to reject at **authentication** due to wrong audience, never letting `scope` pass it through.

### Exercise 3. Test Wrong Scope on an Otherwise Valid Token

Sign a JWT with valid issuer/audience/key/time and `scope="orders.create"`. Send GET `/api/orders` and expect **403** instead of 401. This test proves the separation between validation and authorization.

### Exercise 4. Test a JWT Expired Close to Current Time

Create `exp=now-1s` and observe how the test can become sensitive to clock skew. Change it to `exp=now-1h` for a deterministic expiration test, or configure clock/skew explicitly if testing exact time boundaries. Never use `StepVerifier.withVirtualTime` assuming it replaces `Clock.systemUTC()`.

### Exercise 5. Test JWKS

Run `LocalJwksServer` publishing the public JWK, and decode a token signed with the matching `kid`. Next, create a new decoder pointing to a JWKS lacking the signer key and confirm the JWT is rejected. Do not reuse a decoder with an old cache when testing missing keys.

### Exercise 6. Prove Execution Goes Through the Decoder

Switch the test bean to `CountingReactiveJwtDecoder` wrapping `NimbusReactiveJwtDecoder`. Send a bad-signature Bearer JWT and observe the subscription count increment in a sequential test; also verify a valid JWT still returns 200. **Never replace the delegate with a mock.**

## 19. Completion Checklist for the Test Suite

- [ ] Tests include **real JWTs signed with a test private key**, not just mocked principals.
- [ ] Security chain enables `oauth2ResourceServer(...jwt(...))` and uses a real `ReactiveJwtDecoder`.
- [ ] Decoder trusts the allowlisted public key/JWKS and algorithm.
- [ ] Positive control exists: valid JWT receives 200 on an endpoint with a controller.
- [ ] Cases for bad signature, issuer, audience, expiry, and not-before are tested separately.
- [ ] Negative cases cover unsigned/unsupported algorithms.
- [ ] Valid JWT missing scope returns 403 at authorization.
- [ ] Tests target the right URL/method in the right `SecurityWebFilterChain`.
- [ ] `StepVerifier` asserts the error signal rather than merely non-null `Mono`.
- [ ] `mockJwt()` is never used to claim cryptographic verification.
- [ ] Claim validators after `setJwtValidator` still keep default issuer/timestamp rules.
- [ ] Mandatory token type, `exp` presence, or tenant rules have matching validators and tests.
- [ ] For JWKS: tests cover key retrieval, `kid`, missing/wrong keys, and cache/rotation as needed.
- [ ] No reliance on near-expiry clocks, test ordering, or uncontrolled caches.
- [ ] No production private keys/tokens used; no raw Bearer credentials logged.
- [ ] When JWKS fails, the system **never accepts unverified tokens**.

## 20. Conclusion

To test invalid JWTs in Spring Security WebFlux, clearly separate **simulating an authenticated principal** from **running real JWT verification**:

~~~text
Insufficient for JWT validation:
    mockJwt()
    @WithMockUser
    mocked ReactiveJwtDecoder
    Jwt.withTokenValue(...) object construction
    checking Mono != null

On target:
    Test RSA private key → sign JWT
    WebTestClient → Authorization: Bearer <signed JWT>
    Spring Security WebFlux filter chain
    Real NimbusReactiveJwtDecoder
    Verify JWS + issuer + audience + timestamps
    401 if token invalid
    403 if token valid but missing authority
    200 if valid and authorized
~~~

**`StepVerifier` tests the decoder directly; `WebTestClient` tests the decoder inside the real HTTP flow.** Combining both with a positive control and single-fault negative cases proves the API does not merely reject arbitrary strings, but genuinely **rejects invalid tokens through a reliably configured reactive decoder**.

When production depends on JWKS/discovery, add integration tests with a **test JWK Set server** to cover key fetching, `kid`, and key rotation. Whether in public-key tests or JWKS tests, the core security principle remains unchanged: **without trusted verification, no successful `Authentication` is created, and verified JWTs must still pass endpoint and business-data authorization**.

## References

- [Spring Security — Reactive OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Test Support](https://docs.spring.io/spring-security/reference/reactive/test/index.html)
- [Spring Security — Reactive Authorization](https://docs.spring.io/spring-security/reference/reactive/authorization/index.html)
- [Spring Security — NimbusReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html)
- [Spring Security — ReactiveJwtDecoder Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/ReactiveJwtDecoder.html)
- [Spring Security — JwtValidators Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/jwt/JwtValidators.html)
- [Spring Framework — WebTestClient](https://docs.spring.io/spring-framework/reference/testing/webtestclient.html)
- [Reactor — StepVerifier](https://projectreactor.io/docs/test/release/api/reactor/test/StepVerifier.html)
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 8725 — JWT Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
