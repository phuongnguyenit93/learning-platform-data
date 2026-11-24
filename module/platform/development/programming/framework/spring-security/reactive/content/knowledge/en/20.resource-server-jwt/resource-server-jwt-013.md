# Avoiding Custom JWT-Decoding Filters and Treating Unverified Data as Identity

*Topic: Spring Security Reactive — Resource Server JWT. Java 17+, Spring WebFlux, Spring Security 6.x.*

## 1. The Core Security Problem

A WebFlux API receives an `Authorization: Bearer` JWT. A developer might split the JWT into three parts, Base64URL-decode the payload, find `sub=admin`, and attach an `Authentication` with `ADMIN` privileges to the Reactor `SecurityContext`. This is a **critical authentication vulnerability**: Base64URL merely turns a string into readable data without verifying any signature or origin. An attacker can trivially craft a payload with any `sub`, `roles`, `tenant`, or `expiresAt`.

Never build a custom authentication WebFilter just to read JWTs. Spring Security Reactive already provides OAuth2 Resource Server, `JwtReactiveAuthenticationManager`, `ReactiveJwtDecoder`, and `NimbusReactiveJwtDecoder` to verify tokens before creating `Authentication`. `authorizeExchange` rules or method security are trustworthy only when `Authentication` is produced from a token that genuinely traversed the verification pipeline.

By the end of this lesson, you should be able to:

1. Distinguish decoding data, verifying JWS signatures, validating claims, creating `Authentication`, and authorizing a request.
2. Explain why unverified JWT headers/payloads, `X-User`, `X-Role`, username cookies, `Origin`, or URL query parameters cannot serve as identity.
3. Configure a standard JWT Resource Server using `ServerHttpSecurity`, a trusted JWKS, RS256, and `iss`, `exp`, `nbf`, `aud` validators.
4. Recognize `alg=none`, algorithm confusion, untrusted `jku`/`x5u`, key confusion, ID-token confusion, wrong-audience, and JWT tampering vulnerabilities.
5. Distinguish status 401 from an invalid token versus 403 from a valid principal lacking scope.
6. Use `JwtAuthenticationToken`/`@AuthenticationPrincipal Jwt` and `SCOPE_orders.read` authorities properly.
7. Build a Gradle Java 17+ Spring Boot 3.5.16 application with three endpoints: public, authenticated, and scope-protected.
8. Write `WebTestClient` tests using **real RSA signatures** and an internal MockWebServer JWKS rather than merely mocking principals to pretend authentication succeeded.
9. Identify offline JWT limitations: revocation, JWKS rotation, trust boundaries, audience, token type, and resource/tenant permissions.

**Principle:** every claim is untrusted data until the JWT's signature is verified and its context is validated. Even after authentication, a valid JWT does not automatically grant access to all data.

## 2. A JWT Is Readable Data, Not Trusted Data

A compact JWS-formatted JWT typically consists of:

~~~text
BASE64URL(header).BASE64URL(payload).BASE64URL(signature)
~~~

Illustrative header:

~~~json
{
  "alg": "RS256",
  "typ": "JWT",
  "kid": "key-2026"
}
~~~

Illustrative payload:

~~~json
{
  "iss": "https://issuer.example.test",
  "sub": "alice",
  "aud": ["api://training"],
  "iat": 1780000000,
  "nbf": 1780000000,
  "exp": 1780001800,
  "scope": "orders.read"
}
~~~

**There is no encryption in the JWS example.** Anyone holding the JWT can read the header and payload. Therefore, never place passwords, refresh tokens, sensitive PII, or secrets in a JWT. The signature confirms authenticity/integrity when the verifier uses a trusted key, the right algorithm, and performs real signature verification; it does not hide claims.

| Step | What it does | Security significance |
| --- | --- | --- |
| Base64URL decode | Reads JSON header and payload | Does not verify origin at all |
| Parse JSON | Extracts `sub`, `iss`, `aud`, `scope` claims | Still caller-supplied input |
| JWS verification | Checks signature using trusted public key + approved algorithm | Detects header/payload tampering |
| Claim validation | Checks issuer, `aud`, `exp`, `nbf`, token type | Ensures token targets this API and is currently valid |
| Authentication conversion | Converts verified `Jwt` into Authentication/authorities | Principal now sits inside a trust boundary |
| Authorization | Checks scope/role/tenant/ownership | Whether the caller has rights on the specific request/resource |

**Wrong** example—never deploy this as authentication:

~~~java
String[] parts = bearerToken.split("\\.");
String decodedPayload = new String(
        java.util.Base64.getUrlDecoder().decode(parts[1]),
        java.nio.charset.StandardCharsets.UTF_8);
// Parsing decodedPayload and trusting "sub":"admin" or "role":"ADMIN"
// to build Authentication lets attackers forge fake tokens.
// Checking three segments and decoding JSON checks NO signature at all.
~~~

Someone can craft a fake JWT with header `alg=none`, payload `sub=admin`, `scope=orders.read`, and next-year expiry. If the app trusts the payload before verification, the attacker bypasses authentication. Even checking for three dot-separated segments leaves signatures unverified or absent.

### 2.1. Headers Are Not Trust Anchors Either

Parameters `kid`, `alg`, `jku`, `jwk`, and `x5u` in the JOSE header are chosen by the token presenter. Policy must come from the Resource Server:

- Allowed algorithms: e.g., RS256, never dictated by the token itself.
- Issuer and JWKS URL from trusted deployment configuration, never URLs inside token headers.
- `kid` only hints which key to pick **inside the trusted JWKS**; it is not a filesystem path or URL to fetch.
- Reject `alg=none` for signed access tokens.
- Do not confuse an RSA public key with an HMAC secret when a library permits multiple algorithms. That is algorithm/key confusion.
- Never accept a JWK public key embedded inside the JWT by an attacker as a trusted verification key.

Allowing a token to point `jku` at an unexpected hostname risks **SSRF** and attacker-key substitution. Never write custom dynamic JWKS fetching driven by token headers.

### 2.2. Claims Still Need Context

**`iss`** identifies the issuer. **`sub`** is usually the subject within that issuer's scope; in multi-issuer systems consider `(iss, sub)` pairs rather than `sub` alone. **`aud`** identifies the intended resource recipient. Tokens meant for another API must be rejected even with a valid signature. **`exp`** and **`nbf`** define the validity window; apply controlled clock skew. **`scope`/`scp`** are mapped to authorities only after validation.

A valid JWT with `orders.read` scope still does not allow Alice to read Bob's order if the API enforces ownership/tenant checks. Authorization is a separate step from token verification.

## 3. Do Not Confuse ID Tokens with OAuth2 Access Tokens

OIDC ID tokens are also typically signed by the Authorization Server, yet they are meant for the OAuth2/OIDC Client to confirm a login event, not as Bearer access tokens for a Resource Server. A password-reset token might also be a JWT signed by the same issuer key. Never accept every JWT as an access token solely because its signature verifies.

Enforce the rules of the actual token profile: API audience, issuer, token type/`typ` (such as `at+jwt` per RFC 9068 if the provider follows that profile), `use`, `client_id`, and other contracted mandatory claims. Never casually disable type validation to let any JWT into the API.

Some APIs use opaque access tokens instead of JWTs; in that case use OAuth2 Resource Server opaque-token introspection rather than **assuming every token has three parts**.

### 3.1. A Valid JWT Does Not Mean Admin Privileges

A valid signature only states the token was signed by an accepted key. If the issuer minted an access token for Bob, the Resource Server must take subject Bob and ignore a request-injected `X-User: admin` header. If Bob lacks `orders.read` scope, `GET /api/orders` must return 403. If Bob has the scope but tries to read Alice's order, business logic must check owner/tenant.

## 4. How Does Spring Security Reactive Verify JWTs?

~~~text
HTTP GET + Authorization: Bearer <token>
                  |
                  v
         SecurityWebFilterChain
                  |
                  v
      Bearer authentication converter
                  |
                  v
       JwtReactiveAuthenticationManager
                  |
                  v
         ReactiveJwtDecoder
       (NimbusReactiveJwtDecoder)
           |       |       |
           |       |       +-- check issuer, audience, exp, nbf
           |       +---------- approved JWS algorithm
           +------------------ verify JWS with trusted JWKS
                  |
          +-------+-------+
          |               |
        valid           invalid
          |               |
          v               v
  JwtAuthentication     401 + WWW-Authenticate: Bearer
          |
          v
  Reactor SecurityContext
          |
          v
 authorizeExchange / method security / owner checks
          |
       +--+--+
       |     |
  authorized unauthorized
       |     |
       v     v
      200   403
~~~

This is a responsibility diagram, not an immutable internal class ordering across every version. The core point: **decoder and validators run before claims become `Authentication`**.

### 4.1. Common Concise Configuration

When the provider supports valid issuer metadata and Boot can reach it, these lines are a standard starting point:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test
~~~

Paired with `SecurityWebFilterChain` configuration:

~~~java
http
    .authorizeExchange(ex -> ex.anyExchange().authenticated())
    .oauth2ResourceServer(oauth2 -> oauth2.jwt(
            org.springframework.security.config.Customizer.withDefaults()));
~~~

The snippet above is only an illustrative method fragment. Spring Boot and Spring Security provide the decoder, signature verification, and issuer/timestamp checks by default. **The Resource Server's audience must be explicitly enforced** via version-appropriate Boot config or a custom `OAuth2TokenValidator`; do not assume defaults automatically check every API's audience.

The demo uses a `NimbusReactiveJwtDecoder` bean with a configured JWKS URI and an audience validator to make every check clear. Never write a custom JWT-parsing WebFilter.

### 4.2. Verified Principal

Spring Resource Server JWT normally creates a `JwtAuthenticationToken` with `Jwt` as its principal. A controller can receive `Jwt` via `@AuthenticationPrincipal`:

~~~java
@GetMapping("/api/me")
public Mono<Map<String, String>> me(@AuthenticationPrincipal Jwt jwt) {
    return Mono.just(Map.of("subject", jwt.getSubject()));
}
~~~

This is a controller method snippet, not a standalone Java file. Here `Jwt` comes from Spring's `SecurityContext` after successful authentication. If reading `ReactiveSecurityContextHolder` inside a service, also use only the `Authentication` produced by the security pipeline rather than assigning a fake object from raw request headers.

## 5. Key Validators

| Check | Purpose | Outcome on failure |
| --- | --- | --- |
| JWS signature | Detects header/payload tampering and wrong signer | 401 |
| Trusted alg | Prevents `alg=none` / alg confusion | 401 |
| JWKS trust | Never fetches keys from attacker-chosen URLs | 401 / fail closed |
| Issuer `iss` | Token comes from an approved Authorization Server | 401 |
| Audience `aud` | Token must target this specific API | 401 |
| Expiration `exp` | Token is unexpired (within limited skew) | 401 |
| Not-before `nbf` | Not-yet-valid tokens must be rejected | 401 |
| Type/use | Reject ID or password-reset tokens posing as access tokens | 401 |
| Scope/authority | Permission to call endpoint | 403 if JWT is valid but lacks authority |
| Owner/tenant | Permission to access specific resource | 403 or 404 per existence-hiding policy |
| Revocation | Depends on offline JWT vs. introspection model | May require state or short token TTL |

**Invalid claims must never be used as a principal to be “fixed later”.** Reject them in the decoder/validator or auth manager before authorization.

### 5.1. Clock Skew Does Not Mean Skipping Expiry Checks

Resource Server uses `JwtTimestampValidator` with a clock-skew tolerance (typically 60 seconds in Spring Security 6.x). Set skew just large enough for NTP/network latency, never removing `exp`/`nbf` validation to work around broken machine clocks. Test expired tokens with an expiration several minutes in the past to avoid flakiness right at the boundary.

### 5.2. Key Rotation

The Authorization Server may issue new JWTs with a new `kid`. Trusted JWKS can publish multiple public keys during the transition window. Rely on `NimbusReactiveJwtDecoder`/library JWKS caching; test key rotation before deployment rather than hardcoding a permanent public key if the issuer rotates regularly.

If the JWKS endpoint temporarily errors, **never fall back to accept-all** or skip signature validation. Handle availability, timeouts, caching, and observability inside proper trust boundaries.

## 6. Hands-On Java 17+ Project: Spring Boot WebFlux Resource Server

This example uses **Spring Boot 3.5.16** with compatible Gradle 8.x and Java 17+. `issuer.example.test` addresses are placeholders with no real Internet IdP. The app can start and serve `GET /public/ping`, whereas accepting a real Bearer token in production requires configuring real issuer/JWKS/audience values. The integration tests in Section 7 serve JWKS from a loopback `MockWebServer` and sign JWTs with a test private key to prove the decoder works without an external IdP.

Endpoint policy:

| Method/path | Policy |
| --- | --- |
| `GET /public/ping` | Public |
| `GET /api/me` | Valid JWT |
| `GET /api/orders` | Valid JWT and `SCOPE_orders.read` |
| Other URLs | `denyAll` |

### 6.1. Directory Structure

~~~text
verified-jwt-api/
├── settings.gradle
├── build.gradle
├── src/main/resources/application.yml
├── src/main/java/example/resource/ResourceApplication.java
├── src/main/java/example/resource/SecurityConfig.java
├── src/main/java/example/resource/ApiController.java
└── src/test/java/example/resource/JwtSecurityIntegrationTest.java
~~~

### 6.2. settings.gradle

~~~groovy
rootProject.name = 'verified-jwt-api'
~~~

### 6.3. build.gradle

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The project uses only WebFlux and Resource Server. Do not include MVC `spring-boot-starter-web` or inject a custom Bearer-parsing WebFilter. `MockWebServer` is a test-only dependency.

### 6.4. application.yml

~~~yaml
app:
  security:
    issuer: https://issuer.example.test
    jwk-set-uri: https://issuer.example.test/oauth2/jwks
    audience: api://training
~~~

All three values must come from trusted deployment configuration. In production, the JWKS URI needs HTTPS and an approved IdP domain; never take `issuer` or `jwkSetUri` from untrusted JWTs or request queries. The mock HTTP loopback JWK URI in tests is **strictly for tests**, never for production config.

### 6.5. ResourceApplication.java

~~~java
package example.resource;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceApplication {
    public static void main(String[] args) {
        SpringApplication.run(ResourceApplication.class, args);
    }
}
~~~

### 6.6. SecurityConfig.java

~~~java
package example.resource;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    ReactiveJwtDecoder jwtDecoder(Environment env) {
        String jwksUri = required(env, "app.security.jwk-set-uri");
        String issuer = required(env, "app.security.issuer");
        String audience = required(env, "app.security.audience");

        NimbusReactiveJwtDecoder decoder =
                NimbusReactiveJwtDecoder
                        .withJwkSetUri(jwksUri)
                        .jwsAlgorithm(SignatureAlgorithm.RS256)
                        .build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                jwt.getAudience().contains(audience)
                        ? OAuth2TokenValidatorResult.success()
                        : OAuth2TokenValidatorResult.failure(
                                new OAuth2Error(
                                        "invalid_token",
                                        "Required audience is missing",
                                        null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                        standard, audienceValidator));
        return decoder;
    }

    private static String required(Environment env, String key) {
        String value = env.getProperty(key);
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(
                    "Missing trusted JWT setting: " + key);
        }
        return value;
    }

    @Bean
    SecurityWebFilterChain securityWebFilterChain(
            ServerHttpSecurity http) {
        return http
                .authorizeExchange(ex -> ex
                        .pathMatchers(HttpMethod.GET,
                                "/public/ping").permitAll()
                        .pathMatchers(HttpMethod.GET,
                                "/api/orders")
                                .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.GET,
                                "/api/me").authenticated()
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth -> oauth
                        .jwt(Customizer.withDefaults()))
                .formLogin(ServerHttpSecurity.FormLoginSpec::disable)
                .httpBasic(ServerHttpSecurity.HttpBasicSpec::disable)
                .build();
    }
}
~~~

**Security decisions in SecurityConfig:**

1. JWKS URI, issuer, and audience are read from trusted `Environment`, never from requests or tokens.
2. `NimbusReactiveJwtDecoder` verifies **JWS RS256** against the configured JWKS.
3. `JwtValidators.createDefaultWithIssuer` validates issuer and default timestamps. Never manually Base64URL-decode.
4. The audience validator checks whether this API appears in the `aud` claim; never do substring `contains` on raw payloads.
5. `DelegatingOAuth2TokenValidator` preserves both standard checks and the audience check.
6. `oauth2ResourceServer().jwt()` enables the authentication framework; Spring builds `JwtAuthenticationToken`/authorities after verification.
7. `/api/orders` requires **`SCOPE_orders.read`** derived from a valid JWT's scope, never from `X-Role`.
8. The `denyAll` rule blocks requests to undeclared URLs.
9. There is no OAuth2 Client flow in the Resource Server demo; the API only receives and verifies Bearer tokens.
10. To require RFC 9068 access tokens (`typ=at+jwt`), configure token-type validation per the issuer's contract; this example does not define that profile yet.

### 6.7. ApiController.java

~~~java
package example.resource;

import java.util.Map;

import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Mono;

@RestController
public class ApiController {

    @GetMapping("/public/ping")
    public Mono<Map<String, String>> ping() {
        return Mono.just(Map.of("status", "ok"));
    }

    @GetMapping("/api/me")
    public Mono<Map<String, String>> me(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of("subject", jwt.getSubject()));
    }

    @GetMapping("/api/orders")
    public Mono<Map<String, String>> orders(
            @AuthenticationPrincipal Jwt jwt) {
        // Real business logic also checks owner/tenant.
        return Mono.just(Map.of(
                "subject", jwt.getSubject(),
                "resource", "orders"));
    }
}
~~~

The controller never reads the `Authorization` header or parses raw tokens. `Jwt` is supplied by Spring only to requests that authenticated successfully. Never expose raw JWTs or full claims via the API unless explicitly needed.

## 7. Integration Tests Using Real RSA Signatures and Local Trusted JWKS

Tests using `mockJwt()` are valuable for testing **authorization rules**, yet intentionally skip signature verification. This lesson needs negative tests that actually traverse `ReactiveJwtDecoder`. Therefore, the test generates an RSA keypair at runtime, uses `NimbusJwtEncoder` with the **private key** to sign tokens, lets `MockWebServer` publish only the **public key** via JWKS, and calls the Spring WebFlux server using `WebTestClient`.

**No real IdP, no Internet needed.** The test fixture creates a dummy yet consistent issuer and audience. Any bad JWT must still be rejected by `NimbusReactiveJwtDecoder`.

### 7.1. JwtSecurityIntegrationTest.java

~~~java
package example.resource;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Base64;
import java.util.List;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.source.ImmutableJWKSet;
import okhttp3.mockwebserver.Dispatcher;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.reactive.AutoConfigureWebTestClient;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.JwtClaimsSet;
import org.springframework.security.oauth2.jwt.JwtEncoder;
import org.springframework.security.oauth2.jwt.JwtEncoderParameters;
import org.springframework.security.oauth2.jwt.JwsHeader;
import org.springframework.security.oauth2.jwt.NimbusJwtEncoder;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class JwtSecurityIntegrationTest {

    private static final String ISSUER =
            "https://issuer.example.test";
    private static final String AUDIENCE =
            "api://training";
    private static final String KID = "rsa-test-key-1";

    private static final KeyPair KEYS = newKeyPair();
    private static final RSAKey JWK =
            new RSAKey.Builder((RSAPublicKey) KEYS.getPublic())
                    .privateKey((RSAPrivateKey) KEYS.getPrivate())
                    .keyID(KID)
                    .algorithm(JWSAlgorithm.RS256)
                    .build();

    private static final JwtEncoder ENCODER =
            new NimbusJwtEncoder(
                    new ImmutableJWKSet<>(new JWKSet(JWK)));

    private static final MockWebServer JWKS_SERVER =
            startJwksServer();

    @Autowired
    WebTestClient client;

    private static KeyPair newKeyPair() {
        try {
            KeyPairGenerator generator =
                    KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (Exception e) {
            throw new IllegalStateException(e);
        }
    }

    private static MockWebServer startJwksServer() {
        MockWebServer server = new MockWebServer();
        String publicJwks = new JWKSet(
                JWK.toPublicJWK()).toString();

        server.setDispatcher(new Dispatcher() {
            @Override
            public MockResponse dispatch(RecordedRequest request) {
                if ("/jwks".equals(request.getPath())) {
                    return new MockResponse()
                            .setResponseCode(200)
                            .addHeader("Content-Type",
                                    "application/json")
                            .setBody(publicJwks);
                }
                return new MockResponse().setResponseCode(404);
            }
        });

        try {
            server.start();
            return server;
        } catch (IOException e) {
            throw new IllegalStateException(e);
        }
    }

    @DynamicPropertySource
    static void jwtProperties(DynamicPropertyRegistry registry) {
        registry.add("app.security.issuer", () -> ISSUER);
        registry.add("app.security.audience", () -> AUDIENCE);
        registry.add("app.security.jwk-set-uri",
                () -> JWKS_SERVER.url("/jwks").toString());
    }

    @AfterAll
    static void shutdown() throws IOException {
        JWKS_SERVER.shutdown();
    }

    private static String sign(
            String subject, String issuer,
            String audience, String scope, Instant expiry) {
        Instant issued = Instant.now().minusSeconds(7200);

        JwtClaimsSet claims = JwtClaimsSet.builder()
                .issuer(issuer)
                .subject(subject)
                .audience(List.of(audience))
                .issuedAt(issued)
                .notBefore(issued)
                .expiresAt(expiry)
                .claim("scope", scope)
                .build();

        JwsHeader header = JwsHeader
                .with(SignatureAlgorithm.RS256)
                .keyId(KID)
                .build();

        return ENCODER.encode(
                JwtEncoderParameters.from(header, claims))
                .getTokenValue();
    }

    private static String valid(String subject, String scope) {
        return sign(subject, ISSUER, AUDIENCE, scope,
                Instant.now().plusSeconds(900));
    }

    @Test
    void publicPingIsAccessible() {
        client.get().uri("/public/ping")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.status").isEqualTo("ok");
    }

    @Test
    void protectedApiNeedsBearerToken() {
        client.get().uri("/api/me")
                .exchange()
                .expectStatus().isUnauthorized()
                .expectHeader().exists("WWW-Authenticate");
    }

    @Test
    void signedJwtBecomesTrustedPrincipal() {
        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(
                        valid("alice", "orders.read")))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("alice");
    }

    @Test
    void verifiedScopeAllowsOrders() {
        client.get().uri("/api/orders")
                .headers(h -> h.setBearerAuth(
                        valid("alice", "orders.read")))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.resource").isEqualTo("orders");
    }

    @Test
    void validJwtWithoutScopeIsForbidden() {
        client.get().uri("/api/orders")
                .headers(h -> h.setBearerAuth(
                        valid("alice", "profile")))
                .exchange()
                .expectStatus().isForbidden();
    }

    @Test
    void fakeUserAndRoleHeadersDoNotReplaceJwtIdentity() {
        client.get().uri("/api/me")
                .header("X-User", "admin")
                .header("X-Role", "ADMIN")
                .headers(h -> h.setBearerAuth(
                        valid("alice", "profile")))
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.subject").isEqualTo("alice");
    }

    @Test
    void fakeUserHeaderWithoutBearerCannotAuthenticate() {
        client.get().uri("/api/me")
                .header("X-User", "admin")
                .header("X-Role", "ADMIN")
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void modifiedSignatureIsRejected() {
        String[] parts = valid(
                "alice", "orders.read").split("\\.");
        String sig = parts[2];
        parts[2] = (sig.charAt(0) == 'A' ? "B" : "A")
                + sig.substring(1);

        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(
                        String.join(".", parts)))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctSignatureButWrongIssuerIsRejected() {
        String jwt = sign(
                "admin", "https://other-issuer.example.test",
                AUDIENCE, "orders.read",
                Instant.now().plusSeconds(900));

        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void correctSignatureButWrongAudienceIsRejected() {
        String jwt = sign(
                "admin", ISSUER, "api://other",
                "orders.read", Instant.now().plusSeconds(900));

        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void expiredSignedJwtIsRejected() {
        String jwt = sign(
                "admin", ISSUER, AUDIENCE,
                "orders.read", Instant.now().minusSeconds(600));

        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(jwt))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    @Test
    void algNoneUnsignedJwtCannotImpersonateAdmin() {
        String header = b64(
                "{\"alg\":\"none\",\"typ\":\"JWT\"}");
        String payload = b64(
                "{\"sub\":\"admin\",\"scope\":\"orders.read\","
                + "\"iss\":\"https://issuer.example.test\","
                + "\"aud\":[\"api://training\"]}");
        String forged = header + "." + payload + ".";

        client.get().uri("/api/me")
                .headers(h -> h.setBearerAuth(forged))
                .exchange()
                .expectStatus().isUnauthorized();
    }

    private static String b64(String text) {
        return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(
                        text.getBytes(StandardCharsets.UTF_8));
    }
}
~~~

### 7.2. Running and Explaining Results

~~~bash
gradle test
~~~

**Expected:** 12 JUnit tests pass with compatible JDK, Gradle, and dependencies. This is an expectation from the design, **not a claim that an actual build was run**. `MockWebServer` binds a loopback port solely to return public JWKS; the test encoder signs JWTs with an RSA private key randomly generated in memory.

Tested scenarios:

| Case | Expected HTTP status | What it proves |
| --- | --- | --- |
| GET `/public/ping` without token | 200 | Public endpoint |
| GET `/api/me` without token | 401 | Missing Authentication |
| Valid RS256 JWT, valid `iss`/`aud`/`exp` | 200 | Valid signature and claims |
| JWT with `orders.read` scope | 200 on `/api/orders` | `SCOPE_orders.read` mapping |
| Valid JWT with only `profile` scope | 403 | Independent authorization |
| Alice's JWT + `X-User: admin` | 200 returning Alice | Forged header does not replace principal |
| `X-User: admin`, no Bearer | 401 | Self-asserted headers are untrusted |
| Byte-modified signature | 401 | Real signature verification |
| Valid signature, wrong issuer | 401 | `iss` validation |
| Valid signature, wrong audience | 401 | `aud` validation |
| JWT expired by several minutes | 401 | `exp` validation |
| `alg=none` with admin payload | 401 | Unsigned tokens rejected |

**Why sign with real RSA?** Using only `mockJwt()` or `@MockBean` decoder tests controllers and authorization, yet **does not prove cryptographic signature verification**. This lesson has the real `NimbusReactiveJwtDecoder` fetch public JWK and verify real JWTs signed by the test encoder, making negative tests meaningful.

**Test boundary:** The localhost HTTP JWK server is a test environment, distinct from production. These tests do not verify an enterprise's live JWKS endpoint, issuer discovery, TLS certs, key rotation, multi-issuer policies, or revocation. Additional staging tests are required.

### 7.3. Valid Signature but Different Authorities

Spring Security's default JWT converter maps `scope`/`scp` to `SCOPE_`-prefixed `GrantedAuthority`s. Thus `.hasAuthority("SCOPE_orders.read")` allows only JWTs carrying a verified `orders.read` scope. If an issuer uses a custom roles claim, configure an appropriate `JwtAuthenticationConverter`/`ReactiveJwtAuthenticationConverterAdapter` **after the decoder**, never reading raw roles before verification.

For example, the API uses the user subject as the identity key rather than inferring it from `X-User`. With real multi-user/multi-tenant data, the service must check owner/tenant in the DB rather than stopping at scopes.

## 8. Checking with curl, Logs, and DevTools

Start the demo:

~~~bash
gradle bootRun
~~~

Because YAML contains `issuer.example.test` (a documentation domain), the application can start and public ping works, yet **tokens issued by a real IdP will verify only after deployment configures real JWKS/issuer/audience**.

~~~bash
curl -i http://localhost:8080/public/ping
curl -i http://localhost:8080/api/me
~~~

Expected: ping returns 200 with JSON `status=ok`, `/api/me` without Bearer returns 401 with a Bearer challenge.

Once configured against a real staging IdP, call the HTTPS API with an **access token issued for the API's audience**:

~~~bash
curl -i \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  https://api.staging.example.org/api/me
~~~

Outcome: valid token returns 200 with the matching subject; bad signature/issuer/audience/expired returns 401; valid JWT missing scope on `/api/orders` returns 403. Never paste real tokens into reports, shell history, logs, or screenshots. Never use `curl -k` to skip certificate verification in production.

**Avoid `/decode` endpoints** that return raw claims prior to verification. Anyone holding a JWT can already decode its payload; a dedicated endpoint adds zero security and can mislead operations into mistaking unverified data for identity.

## 9. Additional Production Risks to Evaluate

### 9.1. Revocation

A JWT with a valid signature and `exp` may still have been revoked by the Authorization Server. With offline JWT validation, the Resource Server does not automatically know about immediate revocations. Based on your threat model, use short TTLs, token introspection/opaque tokens, revocation lists, or stateful authorization checks. Signatures do not grant permanent privileges.

### 9.2. HTTPS and Bearer Tokens

A Bearer token is a credential: anyone holding it can use it within its granted scope. HTTPS/TLS with certificate verification is mandatory; a JWS signature neither hides the payload nor stops eavesdroppers from replaying tokens. Never transmit tokens via URL queries, logs, error pages, metrics, or public resources.

### 9.3. JWKS Key Rotation

The Authorization Server can rotate signing keys with new `kid`s. Keep the JWKS endpoint reliable, manage caching/refreshing, and monitor unknown `kid`s. Never skip signature verification when the JWKS server errors. In multi-issuer/multi-tenant systems, enforce separate issuer-to-keyset mappings; never load arbitrary keys from tokens.

### 9.4. Type Confusion and ID Tokens

An OIDC Client's ID token is not an access token. Beyond `aud`/`iss`/`exp`/`nbf`, real projects may require `typ=at+jwt`, `client_id`/`token_use`, or validators per RFC 9068 and issuer contracts. Never disable `typ` validation without a proper alternative. When multiple token profiles share an issuer, specify precisely which tokens the Resource Server permits.

### 9.5. Proxies and Trusted Headers

An API gateway may verify tokens and forward `X-User`/`X-Tenant` to backends. Trust such headers only with **mTLS, network isolation, stripping incoming untrusted headers, and an explicit trust contract**; Internet clients must never be able to send same-named headers through the proxy to spoof identity. In the demo, the backend verifies JWTs itself and ignores `X-User`, avoiding complex header-trust layers.

### 9.6. Do Not Treat JWE Like JWS

JWS signs payloads to protect integrity/authenticity without encryption. JWE encrypts without inherently proving issuer authenticity in all structures; when both confidentiality and authenticity are required, use standardized nested signing/encryption token profiles rather than decrypting payloads yourself and trusting them as identity.

## 10. Common Pitfalls

| Pitfall | Risk | Fix |
| --- | --- | --- |
| Decode JWT and read `sub` | Impersonation | `ReactiveJwtDecoder` + validators |
| Read `X-User`/`X-Role` to build Authentication | Client self-grants privileges | Trust only verified `SecurityContext` |
| Check only `exp` | Attacker sets far-future `exp` | Verify signature, issuer, audience |
| Check only signature | Right-key token meant for wrong API | Validate `aud`/`iss`/type |
| Let `jku` header decide JWKS URL | SSRF / key substitution | Trusted JWKS URI config |
| Trust `kid` as a URL | Attacker-key injection | `kid` only picks keys in trusted JWKS |
| Allow `alg=none` | Unsigned tokens accepted | Pin trusted JWS algorithms |
| Mix HS256/RS256 without key-type checks | Key confusion | Nimbus decoder, alg policy |
| Accept ID token as access token | Token type confusion | Audience/type validators |
| Read roles from raw payload | Privilege escalation | Authority conversion post-verification |
| `orders.read` scope allows reading all orders | IDOR / cross-tenant access | Owner/tenant checks |
| Return 200 on expired tokens | Replay | `exp`/`nbf` validators |
| Use fake `Jwt` principal and claim signature tested | False test confidence | Real RSA/JWKS tests as shown above |
| Ignore key rotation | Outages or broken trust policies | Trusted JWKS cache/rotation |
| Omit HTTPS | Bearer token exposure | TLS with certificate verification |
| Log raw `Authorization` | Secret leak | Redaction |
| Call `block()` inside a WebFilter | Stalls Reactor event loop | Built-in Spring Security |
| Fall back to accept-all on JWKS errors | Authentication bypass | Fail closed |
| Treat 401 as 403 | Client UX/authorization confusion | Test distinct status codes |

## 11. Code Review Checklist

1. Resource Server uses `spring-boot-starter-oauth2-resource-server` and `oauth2ResourceServer.jwt`, with no custom Base64URL-authentication filter.
2. Decoder verifies RS256 against trusted JWKS/public keys; only allowed algorithms accepted.
3. Exact issuer validation, mandatory API audience, and valid `exp`/`nbf`.
4. Required token profile/type enforced; ID and password-reset tokens rejected.
5. `jku`, `x5u`, and `kid` headers never act as untrusted key sources.
6. Authentication is never constructed from raw headers, self-asserted claims, or query parameters.
7. Scopes/roles map to authorities post-verification; 403 tested for missing permissions.
8. Tenant/owner checks live in service/DB rather than checking `sub` alone.
9. 401 tests cover missing/bad signature/wrong issuer/wrong audience/expired/`alg=none`.
10. Tested that Alice's principal cannot be replaced by `X-User: admin`.
11. JWKS rotation, unknown `kid`, and timeouts tested in staging.
12. Bearer tokens never sent over public HTTP, URL queries, or logs.
13. Revocation and short token lifetimes evaluated against risk.
14. No unnecessary secrets/PII placed inside JWT payloads.
15. Clear trust boundaries between Authorization Server, Resource Server, and OAuth2 Client.
16. Auth failure metrics broken down by error category without leaking tokens.
17. Verify proxies/WAFs do not strip or overwrite `Authorization` headers.
18. With multiple `SecurityWebFilterChain`s, verify matchers/ordering introduce no API bypasses.

## 12. Self-Check Questions and Answers

1. Does Base64URL decoding prove the JWT was signed by the issuer? **No.**
2. Does a JWT with `sub=admin` and next-year `exp` but an empty signature represent an admin user? **No, 401.**
3. What happens with a validly signed JWT whose `aud` targets another API? **401.**
4. What happens with a valid JWT lacking `orders.read` on `/api/orders`? **403.**
5. Can Alice's JWT principal be overridden by `X-User: admin`? **No.**
6. Why never trust `jku` in headers? **Attackers can specify malicious JWKS or trigger SSRF.**
7. What is `kid` used for? **Selecting a key inside the trusted JWKS, never picking an issuer or key source.**
8. Why pin `alg` to RS256? **To prevent `alg=none` and algorithm confusion.**
9. Can an ID token substitute for an API access token? **No, unless it satisfies profile/audience and Resource Server contract—which it should not.**
10. Do a valid signature and scope permit reading every user's orders? **No; owner/tenant checks are still required.**
11. Why sign with real RSA in tests? **To verify cryptographic validation, not just authorization mocks.**
12. When the JWKS endpoint fails, should verification be skipped to keep the API up? **No; fail closed.**
13. How do expiry and revocation differ? **An unexpired token can still be revoked; offline JWTs do not detect it automatically.**
14. Should a JWT payload be considered secret because it is encoded? **No; Base64URL is not encryption.**
15. Where should the principal come from? **Spring `SecurityContext` / `@AuthenticationPrincipal` after verification.**
16. How does 403 differ from 401? **403 is insufficient permission once authenticated; 401 is missing/invalid authentication.**

## 13. Reference Documentation

- Spring Security — Reactive OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/index.html
- Spring Security Javadoc — NimbusReactiveJwtDecoder: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusReactiveJwtDecoder.html
- Spring Security Javadoc — JwtValidators: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/JwtValidators.html
- Spring Security — Reactive Authorization: https://docs.spring.io/spring-security/reference/reactive/authorization/index.html
- OWASP JWT Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/JSON_Web_Token_for_Java_Cheat_Sheet.html
- RFC 7515 (JWS): https://www.rfc-editor.org/rfc/rfc7515.html
- RFC 7519 (JWT): https://www.rfc-editor.org/rfc/rfc7519.html
- RFC 8725 (JWT Best Current Practices): https://www.rfc-editor.org/rfc/rfc8725.html
- RFC 9068 (JWT access token profile): https://www.rfc-editor.org/rfc/rfc9068.html
- RFC 6750 (OAuth Bearer): https://www.rfc-editor.org/rfc/rfc6750.html

**Conclusion:** Being able to read `sub`/`roles` from a payload **does not mean authentication succeeded**. Only let Spring Security Resource Server place a `Jwt` into Reactor `SecurityContext` after `NimbusReactiveJwtDecoder` verifies the signature against a trusted JWKS along with algorithm, issuer, audience, and timestamps. Only then apply scopes, business permissions, and owner/tenant checks. A `WebTestClient` suite using real RSA signatures, testing forged tokens, and distinguishing 401/403 is a practical QA baseline to prevent hand-rolled JWT authentication bugs.