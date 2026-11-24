# Testing Decoders, Introspectors, or Identity Providers Beyond Simulations in Spring Security Servlet

## 1. Why Is HTTP Testing with Mock Authentication Alone Insufficient?

In a **Spring Security Servlet Resource Server**, the application typically receives `Authorization: Bearer <access-token>`, validates the access token, and then uses the `Authentication` and authorities to make authorization decisions. Tests using `@WithMockUser`, `jwt()`, or `opaqueToken()` from `spring-security-test` are very helpful, yet they normally **construct a test authentication directly**. They do not necessarily invoke a real JWT verifier or introspection endpoint.

For instance, a controller protected with `hasAuthority("SCOPE_reports.read")` can pass this test:

~~~java
mvc.perform(get("/api/reports")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

This snippet belongs in a test that already has `MockMvc mvc` and the right static imports. The test proves **authorization** is enforced for a simulated principal/authority. It **does not prove**:

- The access token has a valid signature, an allowed signing algorithm, or the right signing key.
- `iss` matches a trusted issuer and `aud` includes the current API.
- `exp`, `nbf`, and clock skew are enforced properly.
- Spring Security reads the HTTP Bearer header and invokes the real `JwtDecoder`.
- An opaque token was sent to the introspection endpoint and returned `active=true`.
- The resource server's own client credentials for introspection work.
- Discovery/JWKS configuration or the identity provider (IdP) continues to work across TLS, proxies, and key rotation.

If every test simply "injects an already logged-in user", a resource server can pass all tests while production rejects every access token, misses audience validation, or cannot reach JWKS.

**Lesson goal:** build a layered testing strategy that retains fast tests, verifies the real authentication path, and ultimately validates the contract with an **external identity provider**. Examples target **Java 17+, Spring Boot 3.x, Spring Security 6.x, Spring MVC/Servlet, and JUnit 5**. Domains, client IDs, and tokens in this lesson are educational sample data; no request is claimed to have run against a live IdP.

## 2. Understanding the Three Testing Layers

| Layer | How it is executed | What it verifies | What remains unverified |
| --- | --- | --- | --- |
| A. Simulated authentication | `@WithMockUser`, `jwt()`, `opaqueToken()` | URL authorization, method authorization, assumed role/scope mapping, business responses | Signatures, decoder/introspector, network, credentials, and IdP |
| B. Real authentication components | Send a real Bearer JWT into `MockMvc` with a real `JwtDecoder`; or call a real `OAuth2TokenIntrospector` against a local HTTP stub | Token parsing, signature/claims/expiry, Bearer filter, HTTP introspection request/response, status/challenge | Real IdP policies and operations, real external TLS/JWKS/rotation |
| C. Integration beyond simulations | App connects to a test/staging IdP or a real containerized IdP environment | Discovery, real token signing/issuance, public keys, scopes, issuer/audience, introspection, contract rotation/revocation | Cannot exhaustively prove every production scenario or load capacity from one test |

Do not abandon Layer A: simulated tests run fast, stay stable, and pinpoint policy changes cleanly. Instead, **supplement with sufficient Layer B and Layer C coverage** at critical security boundaries.

A minimum matrix:

| Scenario | Real JWT decoder | Real opaque introspector | Integrated IdP |
| --- | --- | --- | --- |
| Valid token with permission | Decode/verify signature, map scopes | Send introspection request, parse active/scope | Obtain token from IdP and call API |
| Missing token | Bearer authentication entry point | Bearer authentication entry point | Verify real 401 behind proxy |
| Tampered token / bad signature | Mandatory test | JWT signature N/A under opaque contract | Production-like IdP/JWKS |
| Expired `exp` / premature `nbf` | Mandatory test for JWT | Introspection response/validation per contract | Real token lifetime and skew |
| Wrong issuer/audience | Mandatory when API has a trust boundary | Usually relies on introspection policy and claims | Wrong IdP / wrong client / wrong resource |
| `active=false` | Not applicable | Mandatory test | Real token revocation |
| Insufficient scope | 403 after authentication | 403 after introspection | Scope/consent/claims from IdP |
| JWKS unavailable/rotated | Test via HTTP JWKS stub | N/A unless hybrid design | Test key rotation and cache/latency |
| Introspection endpoint 401/5xx/timeout | Not applicable | Mandatory test | Client secret config, TLS, resilience |

## 3. The Real Path of HTTP Bearer in Servlet

Typical JWT Resource Server:

~~~text
HTTP request: Authorization: Bearer eyJ...
          │
          ▼
Spring Security Servlet FilterChainProxy
          │
          ▼
BearerTokenAuthenticationFilter
          │  resolve Bearer token
          ▼
AuthenticationManager
          │
          ▼
JwtAuthenticationProvider
          │
          ├─ JwtDecoder: parse + verify signature + validate claims
          │
          └─ JwtAuthenticationConverter: map claims/scope → authorities
          │
          ▼
Authentication in SecurityContext
          │
          ▼
authorizeHttpRequests / @PreAuthorize / business checks
          │
          ├─ allowed ───────────► controller
          └─ denied ────────────► AccessDeniedHandler
~~~

With opaque tokens, the middle path is replaced by `OpaqueTokenAuthenticationProvider` and `OAuth2TokenIntrospector`. The introspector queries an authorization server endpoint or a trusted token-validation service. By default, the authorization server returns attributes such as `active`, `scope`, `sub`, and `exp`; responses must still be processed according to provider contract and Spring Security configuration.

**Assertions that must be kept distinct:**

- **401 Unauthorized**: missing valid credentials or rejected token; the Bearer challenge may include `invalid_token`.
- **403 Forbidden**: authentication succeeded yet required permission is missing, such as `SCOPE_reports.read`; may include `insufficient_scope` in the right context.
- **400 Bad Request**: certain Bearer syntax errors like `invalid_request`, depending on where it is detected.
- **5xx / unavailable**: upstream authentication service failed. Never turn all network errors into "invalid token"; clients need to distinguish credential errors from operational outages.
- **`MockMvc` HTTP status** depends on the filter chain, handlers, and policy configured in the test; assert attributes belonging to the right layer.

For JWTs, **merely decoding the payload does not mean the JWT was verified**. Anyone can craft Base64URL header/payload strings; only checking the signature with the right public key, issuer, audience, timestamps, and required claims establishes trust.

## 4. Setting Up a Spring Boot Resource Server for JWT Tests

The example app uses JWTs and opens the reports endpoint only when the token carries `SCOPE_reports.read`. The project builds with Gradle; do not run Spring files with raw JDK because Spring, Nimbus JOSE/JWT, JUnit, and the Servlet runtime are required.

### 4.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

The Boot BOM manages compatible versions if the project applies Spring Boot's plugin/dependency management. Never add a homegrown JWT library just to "test faster". Spring Security Resource Server JWT uses Nimbus JOSE/JWT via the proper dependencies.

Example Java files live in package `com.example.demo`.

### 4.2. Application Entry Point

File `DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

### 4.3. SecurityFilterChain

File `SecurityConfig.java`:

~~~java
package com.example.demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http
            .sessionManagement(s -> s
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/public").permitAll()
                .requestMatchers("/api/reports")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth -> oauth
                .jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

The example app has only GETs. If adding POST/PUT/DELETE, evaluate **CSRF per credential model**: a stateless API accepting only Bearer headers may use a dedicated policy; with session cookies/browsers, never disable CSRF globally by reflex. `STATELESS` does not replace permission checks.

File `ReportController.java`:

~~~java
package com.example.demo;

import java.util.Map;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportController {

    @GetMapping("/api/public")
    public Map<String, String> publicInfo() {
        return Map.of("status", "public");
    }

    @GetMapping("/api/reports")
    public Map<String, String> reports() {
        return Map.of("status", "ok");
    }
}
~~~

Production configuration might use:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
~~~

This domain is an **example**. With real issuer discovery, Spring Security can fetch metadata/JWKS depending on configuration and version. Explicitly configure **audience validation** if the API requires `aud=reports-api`; checking issuer/expiry does not mean every JWT decoder automatically validates your intended audience.

In the next test, a **test-only** `JwtDecoder` bean replaces the need to reach an external issuer. It genuinely verifies signatures with a key pair generated in the test, rather than mocking `JwtDecoder.decode(...)`.

## 5. Testing Real JWTs with MockMvc and a Test-Generated RSA Pair

### 5.1. How This Differs from .with(jwt())

Instead of:

~~~java
mvc.perform(get("/api/reports").with(jwt()))
~~~

construct a **digitally signed** JWT and send it as an HTTP header:

~~~http
GET /api/reports HTTP/1.1
Authorization: Bearer <signed-jwt-created-in-test>
~~~

Then `BearerTokenAuthenticationFilter` extracts the token from the header, `JwtAuthenticationProvider` calls `JwtDecoder`, signature and validators execute, and only then are scopes mapped into authorities.

The local test design has two parts:

1. The test generates an **RSA key pair** in memory and signs JWTs with the private key via `NimbusJwtEncoder`.
2. The test provides a **real `NimbusJwtDecoder`** using the matching public key along with issuer, audience, and timestamp validators.

This verifies signatures and claims **without** needing an online identity provider on every run. Even so, it still does not test discovery, JWKS caching/rotation, TLS, or a real IdP's contract — those belong to the next integration layer.

### 5.2. Full Integration Test (Java 17+, Spring Boot 3.x)

File `RealJwtHttpTest.java` under `src/test/java/com/example/demo/`. It uses the controller and security config from section 4.

~~~java
package com.example.demo;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.List;

import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
@Import(RealJwtHttpTest.LocalJwtKeys.class)
class RealJwtHttpTest {

    private static final String ISSUER =
        "https://issuer.example.test";
    private static final String AUDIENCE = "reports-api";

    @Autowired
    MockMvc mvc;

    @Autowired
    JwtEncoder encoder;

    // Create a real JWT, do not use the jwt() request post-processor.
    private String signedToken(String issuer, String audience,
                               String scope, long expiresInSeconds) {
        Instant now = Instant.now();
        JwtClaimsSet claims = JwtClaimsSet.builder()
            .issuer(issuer)
            .subject("alice")
            .audience(List.of(audience))
            .issuedAt(now.minusSeconds(120))
            .notBefore(now.minusSeconds(5))
            .expiresAt(now.plusSeconds(expiresInSeconds))
            .claim("scope", scope)
            .build();

        JwsHeader header = JwsHeader
            .with(SignatureAlgorithm.RS256)
            .keyId("local-test-key")
            .build();

        return encoder.encode(
            JwtEncoderParameters.from(header, claims))
            .getTokenValue();
    }

    @Test
    void signedJwtWithExpectedClaimsIsAccepted()
            throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + signedToken(
                        ISSUER, AUDIENCE, "reports.read", 300)))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.status").value("ok"));
    }

    @Test
    void missingTokenIsUnauthorized() throws Exception {
        mvc.perform(get("/api/reports"))
            .andExpect(status().isUnauthorized())
            .andExpect(header().string(
                HttpHeaders.WWW_AUTHENTICATE,
                containsString("Bearer")));
    }

    @Test
    void expiredJwtIsRejectedBeforeAuthorization()
            throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + signedToken(
                        ISSUER, AUDIENCE, "reports.read", -60)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongIssuerIsRejected() throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + signedToken(
                        "https://other.example.test",
                        AUDIENCE, "reports.read", 300)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void wrongAudienceIsRejected() throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + signedToken(
                        ISSUER, "another-api", "reports.read", 300)))
            .andExpect(status().isUnauthorized());
    }

    @Test
    void validJwtWithoutRequiredScopeIsForbidden()
            throws Exception {
        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + signedToken(
                        ISSUER, AUDIENCE, "profile.read", 300)))
            .andExpect(status().isForbidden());
    }

    @Test
    void changedSignatureFailsCryptoVerification()
            throws Exception {
        String valid = signedToken(
            ISSUER, AUDIENCE, "reports.read", 300);

        String[] pieces = valid.split("\\.");
        // Flip the first character of the Base64URL signature,
        // without altering the signed header/payload.
        String signature = pieces[2];
        pieces[2] = (signature.charAt(0) == 'A' ? "B" : "A")
            + signature.substring(1);
        String forged = String.join(".", pieces);

        mvc.perform(get("/api/reports")
                .header(HttpHeaders.AUTHORIZATION,
                    "Bearer " + forged))
            .andExpect(status().isUnauthorized());
    }

    @TestConfiguration
    static class LocalJwtKeys {

        @Bean
        KeyPair testKeyPair() throws Exception {
            KeyPairGenerator generator =
                KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        }

        @Bean
        JwtEncoder jwtEncoder(KeyPair pair) {
            RSAKey jwk = new RSAKey.Builder(
                    (RSAPublicKey) pair.getPublic())
                .privateKey((RSAPrivateKey) pair.getPrivate())
                .keyID("local-test-key")
                .build();

            return new NimbusJwtEncoder(
                new ImmutableJWKSet<>(new JWKSet(jwk)));
        }

        @Bean
        JwtDecoder jwtDecoder(KeyPair pair) {
            NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withPublicKey((RSAPublicKey) pair.getPublic())
                .build();

            OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Unexpected audience",
                            null));

            decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    JwtValidators.createDefaultWithIssuer(ISSUER),
                    audience));
            return decoder;
        }
    }
}
~~~

**This is an integration test at the Spring application context and Servlet filter chain level**; there is no Mockito mock of `JwtDecoder`, and no `jwt()` shortcut. The RSA key pair is generated inside the test, and the private key never leaves the JVM. `changedSignatureFailsCryptoVerification` alters one leading character of the signature so the signature fails rather than tampering with claims and expecting the decoder to ignore the signature.

The tests assert:

- JWT with valid signature, issuer, audience, expiry, and scope → 200 from the controller.
- Missing token, expired JWT / wrong issuer / wrong audience / invalid signature → 401.
- JWT **valid for authentication** yet missing `SCOPE_reports.read` → 403.

**Limitation to recognize:** testing with `NimbusJwtDecoder.withPublicKey(...)` does not call a JWKS/metadata endpoint. It does not test how the app fetches real public keys, caches keys, selects `kid`, or handles key rotation. That requires an integration test using `NimbusJwtDecoder.withJwkSetUri(...)` against an HTTP JWKS server or connecting to a real test IdP.

Never report "tested the IdP end-to-end" just because you minted a local JWT and decoded it. What was proven here is **JWT cryptographic validation and the authentication/authorization pipeline** inside the application, under the test-configured validation policy.

### 5.3. Running and Reading Results

Run in the Gradle project containing the example files and dependencies above:

~~~bash
./gradlew test --tests com.example.demo.RealJwtHttpTest
~~~

On Windows:

~~~powershell
.\gradlew.bat test --tests com.example.demo.RealJwtHttpTest
~~~

An equivalent Maven project can run `./mvnw -Dtest=RealJwtHttpTest test`. These examples are **commands to run in the project**, not stdout actually observed here. Output depends on Boot/Security versions, context configuration, other beans, and environment. If the context has conflicting `JwtDecoder`/`SecurityFilterChain` beans, adjust so tests use the intended bean and target chain.

**Do not hard-code expected Gradle stdout**, because test counts and logs vary. What must be asserted is that tests genuinely execute against the HTTP Bearer filter and real decoder.

## 6. Testing JWTs with an HTTP JWKS Endpoint Instead of a Hardcoded Public Key

A common production setup has the resource server fetch public keys from a **JWKS** URL. Unlike `withPublicKey(...)`, configuring `withJwkSetUri(...)` performs HTTP calls to that endpoint to fetch public keys and pick a key by `kid` when verifying a JWT.

Valuable test checkpoints:

1. Generate RSA key pair A in the test, exporting the public key as a JWK with `kid="key-a"`. Only the public key is served at the JWKS endpoint; **never expose the private key over HTTP**.
2. Run a local test HTTP server returning `{"keys":[{...public JWK...}]}` at `/jwks`.
3. Create `NimbusJwtDecoder.withJwkSetUri("http://127.0.0.1:<port>/jwks").build()` as the test bean and send a JWT signed by key A with `kid="key-a"` in its header.
4. Verify the decoder calls JWKS, picks the right key, and returns 200 when token/claims are valid.
5. Sign a token with key B absent from JWKS or with a mismatched `kid`: the response must reject it without arbitrary fallbacks.
6. When the IdP rotates keys, update JWKS accordingly and test behavior after cache refresh; never assume the decoder fetches on every request or expires caches instantaneously. Refresh timing depends on JWKS cache policy/version.

Loopback JWKS tests catch URL, HTTP client, and key-set handling bugs that direct RSA tests miss. It is **still a local fake IdP endpoint**; it only checks the JWKS contract you constructed, not the real metadata or policy of an external IdP.

A dangerous mistake is disabling issuer/audience validation so "tokens signed by test keys pass". Test keys and test claims should match the policy, while production policy remains strict. When defining a custom `JwtDecoder`, make sure you do not accidentally overwrite default timestamp or issuer validators when attaching an audience validator.

### On Signing Algorithms and Key Confusion

- Accept only algorithms configured in the trust contract, such as RS256 if the issuer actually uses RS256. Never treat the token's `alg` header as a caller-trusted choice.
- Never accept `alg=none` just to "speed up unsigned test tokens".
- Never accept a JWT signed by another issuer's key even if `sub` and `scope` look valid.
- Never treat `kid` as a URL and download keys from an attacker-controlled address; only load JWKS from configured/trusted sources.
- Enforce `iss`, `aud`, and `exp/nbf` meaningful to **this API**. A validly signed JWT whose audience belongs to another client must still be rejected.

## 7. Testing a Real OAuth2TokenIntrospector Over Local HTTP

### 7.1. When Are Opaque Tokens Used?

An opaque access token is an opaque string whose signature/claims the resource server cannot verify locally like a JWT. Instead, the resource server queries an **introspection endpoint** per OAuth 2.0 Token Introspection (RFC 7662). The authorization server decides whether the token is active and returns matching metadata.

Spring Security Servlet can be configured with:

~~~java
http.oauth2ResourceServer(oauth -> oauth
    .opaqueToken(Customizer.withDefaults()));
~~~

This is a **snippet inside `HttpSecurity` configuration**, requiring `Customizer`/related imports and an introspector bean. Real apps configure the introspection URI and client credentials matching the token issuer:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://issuer.example.test/oauth2/introspect
          client-id: resource-server-client
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

This is a Boot property example, where `${...}` is a placeholder reading the secret from env/secret manager once configured for real. Never commit secrets to Git or log introspection responses containing tokens.

A common shortcut:

~~~java
mvc.perform(get("/api/reports")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_reports.read"))))
    .andExpect(status().isOk());
~~~

That test **does not call `OAuth2TokenIntrospector.introspect(token)`**. It fabricates an already-authenticated principal. To test introspection, run the real implementation and observe HTTP requests/responses.

### 7.2. Testing the HTTP Protocol with a Local Introspection Endpoint

The example below uses the JDK's built-in HTTP server (`jdk.httpserver` module) as an **authorization server stub**. It does not mock the `OAuth2TokenIntrospector` interface: the real `NimbusOpaqueTokenIntrospector` implementation must send an HTTP POST, supply client authentication, and process the response.

File `IntrospectionHttpTest.java` in package `com.example.demo`:

~~~java
package com.example.demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Arrays;
import java.util.Base64;

import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

class IntrospectionHttpTest {

    private HttpServer server;
    private OpaqueTokenIntrospector introspector;

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(
            new InetSocketAddress("127.0.0.1", 0), 0);

        server.createContext("/introspect", exchange -> {
            try {
                String authorization = exchange
                    .getRequestHeaders()
                    .getFirst("Authorization");

                String expected = "Basic " + Base64.getEncoder()
                    .encodeToString(
                        "resource-client:local-secret".getBytes(
                            StandardCharsets.UTF_8));

                if (!"POST".equals(exchange.getRequestMethod())
                    || !expected.equals(authorization)) {
                    send(exchange, 401, "{}");
                    return;
                }

                String form = new String(
                    exchange.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8);

                String token = Arrays.stream(form.split("&"))
                    .filter(p -> p.startsWith("token="))
                    .findFirst()
                    .map(p -> URLDecoder.decode(
                        p.substring(6), StandardCharsets.UTF_8))
                    .orElse("");

                if (!"active-token".equals(token)) {
                    send(exchange, 200, "{\"active\":false}");
                    return;
                }

                long exp = Instant.now().plusSeconds(300)
                    .getEpochSecond();

                send(exchange, 200,
                    "{\"active\":true,\"sub\":\"alice\","
                    + "\"client_id\":\"client-1\","
                    + "\"scope\":\"reports.read\","
                    + "\"exp\":" + exp + "}");
            } finally {
                exchange.close();
            }
        });

        server.start();
        String uri = "http://127.0.0.1:"
            + server.getAddress().getPort()
            + "/introspect";

        introspector = new NimbusOpaqueTokenIntrospector(
            uri, "resource-client", "local-secret");
    }

    private static void send(HttpExchange exchange, int code,
                             String body) throws IOException {
        byte[] bytes = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "application/json");
        exchange.sendResponseHeaders(code, bytes.length);
        exchange.getResponseBody().write(bytes);
    }

    @AfterEach
    void stopServer() {
        if (server != null) {
            server.stop(0);
        }
    }

    @Test
    void activeTokenProducesPrincipalAndScope() {
        OAuth2AuthenticatedPrincipal principal =
            introspector.introspect("active-token");

        assertEquals("alice", principal.getAttribute("sub"));
        assertTrue(principal.getAuthorities().stream().anyMatch(
            a -> "SCOPE_reports.read".equals(a.getAuthority())));
    }

    @Test
    void inactiveTokenIsRejected() {
        assertThrows(BadOpaqueTokenException.class,
            () -> introspector.introspect("revoked-token"));
    }
}
~~~

**What this test is designed to verify:** the client sends an HTTP POST to a local endpoint, uses Basic client authentication, passes the token in a form-encoded request body, and handles `active=true/false` responses. It does not claim to call a real provider.

**Limitation:** this is a **component-level introspector** test; it does not by itself prove `BearerTokenAuthenticationFilter`, the security chain, and controllers work with opaque tokens. To cover the full Resource Server HTTP layer, create a `@SpringBootTest @AutoConfigureMockMvc` with an `OpaqueTokenIntrospector` bean pointing at the stub and send `Authorization: Bearer active-token` via `MockMvc`, asserting 200/401/403 per policy. Then the mock sits only at the **external HTTP endpoint**, not at the introspector API.

If your build tool does not resolve the JDK's `jdk.httpserver` module, configure the test JVM with `--add-modules jdk.httpserver` or use WireMock/MockWebServer with appropriate dependencies. In production, never use plain HTTP for introspection: evaluate TLS, credential handling, endpoint auth, timeouts, and network policies.

### 7.3. Testing Introspection Endpoint Failure Modes

A thorough suite should vary stub responses across scenarios:

| Introspection endpoint response | Expectation |
| --- | --- |
| HTTP 200, `{"active":true,...}` with matching scopes | Principal accepted; authorization checks permissions |
| HTTP 200, `{"active":false}` | Token rejected |
| HTTP 200, active true yet missing scope | Token authenticated, yet route requiring scope returns 403 |
| HTTP 401 from introspection endpoint | Wrong resource-server client credentials; do not confuse with expired user token |
| HTTP 500/503, timeout, TLS failure | Infrastructure/service error; never treat as active token |
| HTTP 200 with invalid JSON / missing required fields | Reject or report error properly, **fail closed** |
| Different token for same user | Never blindly reuse unverified cached results |

**Do not conclude validity from a "200 response" alone**: RFC 7662 normally uses HTTP 200 for successful introspection even when the token is inactive. Meaning lies in `active=true/false`, not the HTTP status of the introspection call.

Verify **authorization server-specific claims**: some IdPs return `scope`, `client_id`, `aud`, and `exp` differently. The resource server should rely only on agreed, verified attributes and never fabricate permissions if the response omits scopes.

If the system caches introspection results to reduce load, test TTL, revocation windows, and cache keying by exact token. Caching `active=true` for too long lets revoked tokens stay valid. Consider behavior when the introspection service is unavailable: security-sensitive systems typically **fail closed**.

## 8. When Must You Test Against a Real IdP?

Local signed JWTs and local introspection stubs prove only **the portion of the contract** you built. When a real IdP changes issuer, signing algorithms, endpoint paths, claim mappings, or client permissions, the application can break even when mocks and local tests are green.

The **IdP integration test layer** should use one of two setups:

- **Organization-controlled test/staging IdP**: dedicated client registration, dedicated issuer, dedicated test scopes/roles, certificates and secrets managed by a secret manager. Never run automated tests with production accounts or production tokens.
- **Isolated IdP environment (e.g., container)**: provides OIDC/OAuth2 metadata, JWKS, grant/token endpoints, and introspection matching the contract. Pin image/container versions and realm/client data so tests stay reproducible. This is a real running IdP, though it may still differ from the production vendor.

Meaningful integration test steps:

1. **Provision a dedicated test client:** register the client/resource server with exact redirect URI or service grant, minimal scopes, and exact audience.
2. **Fetch metadata or configure endpoints:** verify issuer URI, token URI, introspection URI, JWKS URI, and TLS certificates per provider.
3. **Acquire a real token via the right grant:** client credentials for service-to-service; authorization code/PKCE for interactive users; never hard-code user passwords in tests.
4. **Call the Resource Server over real HTTP** with the access token via `Authorization: Bearer ...`, asserting status, minimal body, and absence of sensitive data.
5. **Wrong issuer or audience:** use a token from another environment/client/API and verify rejection rather than accepting it because its key sits in an overly broad trust store.
6. **Wrong scope/role:** a valid token lacking permission returns 403; only granting the right scope succeeds. Test claim mapping against real IdP output.
7. **Expiry/revocation:** use short-lived tokens and revoked or `active=false` tokens; verify cache and refresh/re-auth logic never bypass revocation.
8. **Key rotation:** add a new key, rotate `kid`, keep the old key for the contracted grace period; verify the decoder uses JWKS/cache and handles the old key disappearing.
9. **Availability failures:** block connectivity to the IdP or simulate timeout/DNS/TLS errors; the app must not fail open or leak credentials/stack traces.
10. **Cleanup:** remove test users and revoke test tokens/clients as appropriate so tests never leave long-lived credentials or side effects on real systems.

**Testing conclusion:** a token issued by a *real provider* and accepted by the resource server verifies the **contract between the two systems**, not just a test key generated by the app itself.

### 8.1. CI Execution and Cadence

Do not force every pull request to call a shared staging IdP to run all authentication tests. A practical split:

- **Every commit/PR:** unit policy tests, `MockMvc` with locally signed JWT/real decoder, introspector with loopback HTTP stub. No production secrets, fast and repeatable.
- **Integration / pre-release pipeline:** containerized IdP or ephemeral environment testing metadata/JWKS, actual token issuance, introspection protocol, and version compatibility.
- **Periodic / release staging smoke tests:** test the real vendor IdP, TLS/redirects/callbacks, scopes, role/audience, and availability contracts.

Stratifying prevents CI from becoming flaky due to network blips while ensuring critical integration misconfigurations cannot slip through.

### 8.2. Real IdP Tokens Usually Require Explicit Audience Validation

A validly signed JWT with a trusted `iss` may have been issued for **another API**. If a resource server accepts any audience, a token from System A can be replayed against System B. Tests must prove tokens with a different audience are rejected.

Spring Security provides configurable validators for issuer, timestamps, and audience; **do not assume `issuer-uri` automatically infers every audience check needed**. Likewise, OAuth scopes do not equal permission over every resource: concrete actions must still check user/tenant/owner.

## 9. Testing HTTP Statuses, Challenges, and What Must Not Be Leaked

For Resource Server Bearer authentication, observe both status and `WWW-Authenticate`, not only the body:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

When the token is invalid, the response may include a standard error code:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer error="invalid_token"
~~~

When the token is valid yet lacks scope, the response may be:

~~~http
HTTP/1.1 403 Forbidden
WWW-Authenticate: Bearer error="insufficient_scope"
~~~

These examples are **illustrative shapes**, not fixed byte-for-byte responses. Spring Security may also add `realm` and other parameters, and behavior is affected by entry points, `AccessDeniedHandler`, or proxies. Do not assert a rigid exact header string when policy allows multiple valid representations.

Safety checks:

- Never output access tokens, refresh tokens, client secrets, private RSA keys, or `Authorization` headers in responses or logs.
- Never expose raw `JwtException.getMessage()` or sensitive introspection HTTP bodies in `error_description`.
- For guests, 401 tells the client a Bearer token is required; a valid token lacking permission transitions to 403.
- A 401 from **the introspection endpoint due to bad client auth** is an upstream/service integration fault; do not tell end users their access token definitely expired.
- When the IdP is unreachable, fail safely server-side with correlation ID, alerts/metrics, and bounded retries—never retry infinitely or accept tokens while offline.

In tests, you can assert headers **do not contain specific diagnostic strings**, without printing tokens into test reports. When logging for debugging, log only route templates, request IDs, error categories, configured issuer, and status, avoiding PII or sensitive claims.

## 10. Distinguishing Four Questions Often Mixed Up in Tests

### 10.1. "Is the User Authenticated?"

Test authentication/decoder/introspector: signature or introspection, active token, expiry, issuer, audience. If any fail, never create a trusted authenticated principal.

### 10.2. "Does the Principal Have the Required Authority?"

Test converter/authorization mapping: claim `scope="reports.read"` can convert to `SCOPE_reports.read` by convention. If the IdP returns `roles`, `groups`, or namespaced claims instead of `scope`, configure a custom `JwtAuthenticationConverter`/introspector mapping per contract. Do not manually add the authority in a test and assume the converter was tested.

### 10.3. "Does the Principal Have Permission for That Specific Resource?"

Even a `reports.read` token does not mean Alice can view Bob's reports or another tenant's data. Services must enforce ownership/ACL/tenant rules and test real data at the business boundary. JWT validation and scopes are only necessary conditions.

### 10.4. "Does the IdP Fulfill the Contract?"

Only real integration covering metadata/JWKS, token issuance, introspection, TLS, and lifecycle verifies that. A local HTTP stub only checks **the resource server's protocol expectations**, not that the real provider always sends valid data.

That is why an integration suite can never be replaced by "the `jwt()` test returned 200".

## 11. Common Testing Mistakes and How to Spot Them

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `jwt()` tests pass yet production rejects all tokens with 401 | Tests bypassed decoder or `issuer-uri`/JWKS is wrong | Send signed JWTs via Bearer header with real decoder; add IdP tests |
| Wrong-audience JWT still accepted | Missing audience validator, or tests only mocked authorities | Add validator and negative wrong-aud test |
| Expired JWT still returns 200 in tests | Used mock authentication without `exp` validation | Test real signed token with past `exp` |
| Tampered signature undetected by tests | No cryptographic validator used | Tamper signature or sign with untrusted key against real decoder |
| Valid signature yet missing scope returning 403 is untested | Only tested JWT parsing | Test converter + HTTP authorization with insufficient-scope token |
| `active=false` token passes `opaqueToken()` test | Post-processor bypasses introspector | Test `NimbusOpaqueTokenIntrospector` over HTTP returning `active=false` |
| Introspection HTTP 200 misleads test into assuming valid token | Ignored `active` field in response | Assert `active=true/false` semantics |
| Resource Server calls real IdP during every unit test | Failed to isolate local integration fixtures | Use test JWT keys or local introspection server; run E2E in a separate stage |
| CI fails intermittently on JWKS cache/rotation | Tests depend on uncontrolled timers/network/key state | Pin key fixtures and fake clock/cache cleanly; add scheduled E2E |
| Introspection returns 401 due to wrong client secret | Confused resource server client auth with user token | Check client ID/secret, auth method, URL, and TLS |
| Test builds "signed" JWT yet skips Bearer filter | Called `decoder.decode(...)` directly, skipping HTTP security chain | Add `MockMvc` with a real `Authorization` header |
| Test gets HTTP 401 without clear origin | Proxy/Basic auth replaced Resource Server entry point | Inspect `WWW-Authenticate` and logs at the right layer |
| Scope passes yet user views another tenant's data | Authorization only checked scope, missing object-level checks | Test ACL/owner/tenant at service/resource layer |
| Test writes secrets into reports or code | Printed tokens/JWK private keys or committed secret fixtures | Use ephemeral keys, secret manager, and redaction |
| Resource Server fails to start offline | IdP discovery or JWKS required at startup in tests | Inject test decoder explicitly; test external discovery in integration tier |

### When Is Mockito Mocking Appropriate?

Mockito mocks of `JwtDecoder` or `OAuth2TokenIntrospector` fit **fast exception-handling, controller, and service tests**—for example, testing how the app reacts when the decoder throws an error without caring about cryptography. Still, label the scope accurately: **mocked error handling**, never "JWT validation integration test".

In real component tests, you may mock repositories/downstream services, yet **never mock the very decoder/introspector under test**. In IdP E2E tests, never replace the IdP with a stub and claim vendor TLS/issuer discovery was verified.

## 12. Acceptance Checklist for a Servlet Resource Server

- [ ] Fast policy tests use `jwt()/opaqueToken()/@WithMockUser`, never treated as crypto/introspection proof.
- [ ] `MockMvc` sends `Authorization: Bearer <real-signed-JWT>` through a real `JwtDecoder`.
- [ ] Cases cover valid JWT, missing token, bad `exp`/`nbf`, bad issuer/audience, bad signature, missing scope, and sufficient scope.
- [ ] Scope/claim converter is verified against **claims from a real token**, not only mock-assigned authorities.
- [ ] If using remote JWKS, metadata/JWK URL, `kid`, wrong keys, key rotation/caching, and unavailable endpoints are tested.
- [ ] If using opaque tokens, a real `OAuth2TokenIntrospector` runs over HTTP covering `active` true/false, client credentials, and errors/timeouts.
- [ ] Full `BearerTokenAuthenticationFilter → Authentication → authorization → controller` flow is tested; isolated component tests do not replace HTTP tests.
- [ ] Contract tests run against a test IdP covering actual token issuance, issuer/aud/scopes, and refresh/revocation per grant.
- [ ] 400/401/403/5xx are distinguished and `WWW-Authenticate` matches the Bearer mechanism in use.
- [ ] No tokens, secrets, private keys, or sensitive claims are logged or leaked in responses/CI artifacts.
- [ ] Negative security tests, timeouts/retries, concurrent requests, multi-tenancy, and key rotation run before release.
- [ ] Test environments use dedicated secrets/clients, HTTPS with real IdPs, and automatic cleanup.
- [ ] Test results state clearly whether they cover Layer A, B, or C; never claim coverage beyond components that actually executed.

**Conclusion:** `@WithMockUser`, `jwt()`, and `opaqueToken()` enable fast authorization testing, yet **never replace** real authentication testing. To evaluate a Spring Security Servlet Resource Server thoroughly, test JWTs through a **`JwtDecoder` with real signatures/validators**, opaque tokens through a **real `OAuth2TokenIntrospector` and HTTP introspection**, and **issuer/JWKS/grant/claim/revocation contracts** against an external identity provider beyond simulations. Each layer has distinct value and must be reported with its exact limits.
