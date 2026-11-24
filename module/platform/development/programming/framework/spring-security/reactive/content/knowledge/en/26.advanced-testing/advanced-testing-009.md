# Limitations of Mocked Tokens and Real Testing of JWT Decoders, Signatures, Issuer, and Audience in Spring Security WebFlux

## 1. Goal and context

This lesson is for **Spring Security - reactive (WebFlux)** at the advanced testing level. The goal is to clearly separate tests using mocked identities from real end-to-end verification of `Authorization: Bearer <JWT>` → security filters → `ReactiveJwtDecoder` → signature/claims verification → authority mapping → access decision.

A JWT typically has the form `header.payload.signature` (each part Base64URL-encoded). Decoding JSON from the payload **does not prove** the token is trustworthy: the application must verify the signature with a trusted key, validate time constraints (`exp`, `nbf`), issuer (`iss`), and audience (`aud`), and only then apply authorization policies. Headers like `alg`/`kid` are untrusted inputs that must be checked against trusted configuration; never permit an algorithm or key URL just because the token proposes it.

In WebFlux, the component that decodes and validates JWTs is **`ReactiveJwtDecoder`**. `JwtDecoder` commonly seen in Servlet/MVC examples is a different type; do not use it by mistake in reactive tests. If the application uses opaque tokens instead of JWTs, the corresponding verification path is `ReactiveOpaqueTokenIntrospector`, which uses different testing techniques.

## 2. What does `mockJwt()` prove, and what does it skip?

`SecurityMockServerConfigurers.mockJwt()` from `spring-security-test` attaches a simulated `JwtAuthenticationToken` to test requests through `WebTestClient`. It works very well for testing **authorization** and principal data once identity is assumed authenticated. Depending on configured claims/scopes, `mockJwt()` lets you test HTTP 200/403, `SCOPE_*` authorities, protected paths, and logic reading JWT claims.

However, `mockJwt()` **bypasses parsing the Bearer token string, decoding JWS, and invoking a real `ReactiveJwtDecoder`**. A mocked token can have `alg: none`, no signature, the wrong issuer, the wrong audience, or an expired timestamp and the test still passes if permissions are granted. Therefore:

| Testing approach | Hits real decoder? | Verifies signature, `iss`, `aud`, expiry? | Best suited for |
| --- | --- | --- | --- |
| `mockJwt()` / `mockAuthentication()` | No | No | Authority rules, scopes, principal, handlers |
| Mock bean `ReactiveJwtDecoder` returning a canned `Jwt` | Calls decoder API but uses fake output | Does not verify real validation algorithms | Testing wiring, success/failure branches |
| `NimbusReactiveJwtDecoder` + **real JWT signed** by a test key | Yes | Yes, when full validators are configured | Signature, issuer, audience, exp/nbf, and HTTP 401/403 |
| Real JWT + controlled stub HTTP JWKS/metadata | Yes, including key retrieval | Yes; plus `kid`, JWKS, cache/rotation, network errors | Integration testing close to deployment |

**Rule:** a passing 200 test using `mockJwt()` must never be cited as evidence that the resource server rejects tampered payloads or tokens signed by an unknown key.

## 3. Building a minimal WebFlux application to test

The example below uses Java 17, Spring Boot 3.5.0 (Spring Security 6.x family), Maven, and JUnit 5. `.example.test` URLs are illustrative placeholders; the JWT signing tests below build keys and decoders in memory so no real IdP is needed. Place the files at the exact names and paths shown to run `mvn test`.

**`pom.xml`**:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jwt-reactive-tests</artifactId>
    <version>1.0.0</version>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>
    <properties><java.version>17</java.version></properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webflux</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter-oauth2-resource-server` brings in the Resource Server/JWT components; `spring-security-test` supplies `mockJwt()` and `springSecurity()`. Omit `spring-boot-starter-web` to preserve the WebFlux context.

**`src/main/java/example/securityreactive/ResourceServerApp.java`**:

```java
package example.securityreactive;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ResourceServerApp {
    public static void main(String[] args) {
        SpringApplication.run(ResourceServerApp.class, args);
    }
}
```

**`src/main/java/example/securityreactive/SecurityConfig.java`**:

```java
package example.securityreactive;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {
    @Bean
    SecurityWebFilterChain securityWebFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/public").permitAll()
                .pathMatchers("/reports").hasAuthority("SCOPE_reports.read")
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
```

**`src/main/java/example/securityreactive/ReportsController.java`**:

```java
package example.securityreactive;

import reactor.core.publisher.Mono;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ReportsController {
    @GetMapping("/reports")
    public Mono<String> reports() {
        return Mono.just("report:visible-to-reader");
    }

    @GetMapping("/public")
    public Mono<String> publicPage() {
        return Mono.just("public");
    }
}
```

**`src/main/resources/application.yml`**:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/tenant
          jwk-set-uri: https://issuer.example.test/tenant/jwks
          audiences:
            - reports-api
```

In real environments, replace URLs with your IdP's trusted endpoints. `issuer-uri` sets the expected `iss`; `jwk-set-uri` sets where to fetch public keys for signature verification; `audiences` requires `aud` to contain `reports-api`. Boot 3.5 supports this audience property for both servlet and reactive apps. If you declare your own `ReactiveJwtDecoder` bean, you must **wire in the appropriate issuer/audience/time validators yourself**; configuration properties do not automatically attach validators to a custom bean.

## 4. First test layer: access rules with `mockJwt()`

**`src/test/java/example/securityreactive/MockJwtAuthorizationTest.java`**:

```java
package example.securityreactive;

import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
class MockJwtAuthorizationTest {
    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @Test
    void noAuthenticationReturns401() {
        client.get().uri("/reports").exchange()
            .expectStatus().isUnauthorized();
    }

    @Test
    void authenticatedWithoutRequiredScopeReturns403() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("scope", "profile.read")))
            .get().uri("/reports").exchange()
            .expectStatus().isForbidden();
    }

    @Test
    void expectedScopeReturns200() {
        client.mutateWith(mockJwt()
                .jwt(jwt -> jwt.claim("scope", "reports.read")))
            .get().uri("/reports").exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:visible-to-reader");
    }

    @Test
    void fakeExpiredWrongIssuerAndAudienceCanStillPass() {
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                .claim("scope", "reports.read")
                .claim("iss", "https://attacker.example.test")
                .claim("aud", List.of("someone-else"))
                .claim("exp", Instant.now().minusSeconds(3600))))
            .get().uri("/reports").exchange()
            .expectStatus().isOk();
    }
}
```

The final test **intentionally** supplies invalid claims while still expecting 200 to demonstrate the mock's boundary: the authentication object is pre-built, skipping signature/issuer/audience/expiration checks. Never treat this outcome as production policy.

`mockJwt().jwt(...)` can customize `sub`, `scope`, `scp`, `iss`, and other claims; `mockJwt().authorities(...)` can supply an authority list directly when tests focus solely on permissions. When testing a **real** authority-mapping converter (especially a custom one), write dedicated converter tests or run the real token pipeline; assigning authorities directly bypasses that conversion logic.

## 5. Second test layer: real RSA signing, real decoder verification, and Bearer over HTTP

The next example creates two RSA key pairs inside the test: one **trusted** pair and one **untrusted** pair. The Resource Server knows only the **public key** of the trusted pair; the test uses the private key to sign real compact RS256 JWTs via Nimbus JOSE. `NimbusReactiveJwtDecoder` performs real signature verification, and `DelegatingOAuth2TokenValidator` combines standard timestamp/issuer validation with a custom audience check.

Configuring keys in memory keeps the test independent of network IdPs/JWKS while still exercising the full **HTTP Bearer → SecurityWebFilterChain → ReactiveJwtDecoder → authentication/authorization** chain, completely unlike `mockJwt()`.

**`src/test/java/example/securityreactive/SignedJwtHttpTest.java`**:

```java
package example.securityreactive;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.NoSuchAlgorithmException;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;

import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestConfiguration;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Import;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server.SecurityMockServerConfigurers.springSecurity;

@SpringBootTest
@Import(SignedJwtHttpTest.TestDecoderConfig.class)
class SignedJwtHttpTest {
    private static final String ISSUER = "https://issuer.example.test/tenant";
    private static final String AUDIENCE = "reports-api";
    private static final KeyPair TRUSTED = generateKeyPair();

    @Autowired ApplicationContext context;
    WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .build();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class TestDecoderConfig {
        @Bean
        ReactiveJwtDecoder reactiveJwtDecoderForTest() {
            NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
                .withPublicKey((RSAPublicKey) TRUSTED.getPublic())
                .build();

            OAuth2TokenValidator<Jwt> issuerAndTime =
                JwtValidators.createDefaultWithIssuer(ISSUER);

            OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience() != null && jwt.getAudience().contains(AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(new OAuth2Error(
                        "invalid_token", "Unexpected audience", null));

            decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                issuerAndTime, audience));
            return decoder;
        }
    }

    @Test
    void acceptsValidSignedJwt() throws JOSEException {
        String jwt = sign(TRUSTED, ISSUER, AUDIENCE, "reports.read",
            Instant.now().minusSeconds(10), Instant.now().plusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange()
            .expectStatus().isOk()
            .expectBody(String.class).isEqualTo("report:visible-to-reader");
    }

    @Test
    void rejectsJwtSignedByUnknownPrivateKey() throws JOSEException {
        String jwt = sign(generateKeyPair(), ISSUER, AUDIENCE, "reports.read",
            Instant.now().minusSeconds(10), Instant.now().plusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void rejectsWrongIssuer() throws JOSEException {
        String jwt = sign(TRUSTED, "https://evil.example.test", AUDIENCE,
            "reports.read", Instant.now().minusSeconds(10),
            Instant.now().plusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void rejectsWrongAudience() throws JOSEException {
        String jwt = sign(TRUSTED, ISSUER, "unrelated-service",
            "reports.read", Instant.now().minusSeconds(10),
            Instant.now().plusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void rejectsExpiredToken() throws JOSEException {
        String jwt = sign(TRUSTED, ISSUER, AUDIENCE, "reports.read",
            Instant.now().minusSeconds(1200),
            Instant.now().minusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void rejectsTokenNotYetValid() throws JOSEException {
        String jwt = sign(TRUSTED, ISSUER, AUDIENCE, "reports.read",
            Instant.now().plusSeconds(600),
            Instant.now().plusSeconds(1800));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validJwtWithInsufficientScopeReturns403() throws JOSEException {
        String jwt = sign(TRUSTED, ISSUER, AUDIENCE, "profile.read",
            Instant.now().minusSeconds(10), Instant.now().plusSeconds(600));

        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth(jwt))
            .exchange().expectStatus().isForbidden();
    }

    @Test
    void malformedBearerTokenReturns401() {
        client.get().uri("/reports")
            .headers(headers -> headers.setBearerAuth("not.a.valid.jwt"))
            .exchange().expectStatus().isUnauthorized();
    }

    private static String sign(KeyPair signingKey, String issuer,
                               String audience, String scope,
                               Instant notBefore, Instant expiresAt)
            throws JOSEException {
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .audience(audience)
            .subject("alice")
            .claim("scope", scope)
            .issueTime(Date.from(Instant.now()))
            .notBeforeTime(Date.from(notBefore))
            .expirationTime(Date.from(expiresAt))
            .build();

        SignedJWT jwt = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                .type(JOSEObjectType.JWT).build(),
            claims);
        jwt.sign(new RSASSASigner(
            (RSAPrivateKey) signingKey.getPrivate()));
        return jwt.serialize();
    }

    private static KeyPair generateKeyPair() {
        try {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        } catch (NoSuchAlgorithmException exception) {
            throw new IllegalStateException(exception);
        }
    }
}
```

**Run tests** in the directory containing `pom.xml`:

```bash
mvn test
```

No special Maven stdout is assumed here since logs depend on the environment; what must be verified is that all tests pass. Expected HTTP behaviors: valid signature + valid issuer/audience/time/scope → **200**; wrong signature/wrong issuer/wrong audience/expired/not-yet-valid/malformed token → **401**; valid token lacking the required scope → **403**. Timestamp validators typically have a default clock skew of around 60 seconds, so the ±600-second offsets in the tests stay well clear of the boundary.

In this example, `@Import(TestDecoderConfig.class)` builds a real decoder from the test public key and overrides Boot's auto-configured decoder bean. Thus the test verifies the RSA mechanism and the validators installed in `TestDecoderConfig`, but **does not** verify fetching JWKs from the production URL. The private key lives inside the test solely to generate test tokens; a normal resource server never needs the IdP's private key.

## 6. More realistic testing of JWKS, `kid`, algorithms, and issuer discovery

When a system relies on `issuer-uri`/`jwk-set-uri`, add an integration test group using an embedded stub HTTP server (such as WireMock or MockWebServer) **serving a real JWK Set**:

1. Generate a test-only RSA key pair and publish the **public JWK** (including `kty`, `n`, `e`, `kid`, and `alg` if needed) at the `/jwks` endpoint. Keep the private key only in tests to sign JWTs with the matching `kid` header.
2. Start the JWKS stub on a random port. Build the decoder with `NimbusReactiveJwtDecoder.withJwkSetUri(stubJwksUrl).build()` and attach `JwtValidators.createDefaultWithIssuer(issuer)` plus the audience validator. If testing discovery, also serve a valid metadata endpoint declaring `jwks_uri`, then build the decoder via `issuer-uri`/issuer discovery.
3. Send real Bearer JWTs through `WebTestClient`; verify valid tokens succeed. Test a `kid` absent from JWKS, tokens signed by untrusted keys, algorithms outside the allowed list, unreachable JWKS, malformed JSON/JWK, and key rotation under realistic caching behavior.
4. When testing rotation/caching, use supported refresh mechanisms or controlled clocks/caches to avoid flaky timing-dependent tests. Verify old keys are rejected when policy requires and new keys are accepted after reload. Never assume every request re-fetches JWKS.
5. Lock trust criteria in application configuration. Never load arbitrary keys from `jku` or `x5u` headers in client-sent JWTs; never blindly trust arbitrary `alg` values. `alg: none` or switching to a symmetric key outside policy must be rejected.

Tests with `withPublicKey(...)` (Section 5) and tests with `withJwkSetUri(...)` complement each other: the former are fast, stable, and network-free; the latter verify key distribution/selection, metadata, and network failure modes.

## 7. Minimum test case table

| Case | Result when requesting `/reports` | What is verified |
| --- | --- | --- |
| No Bearer token | 401 | Unauthenticated |
| Valid JWT + `scope=reports.read` | 200 | Authentication and authorization succeed |
| Valid JWT missing `reports.read` | 403 | Post-authentication authorization |
| Payload modified after signing | 401 | Signature no longer matches content |
| Signed with untrusted private key | 401 | Trust anchor/public key |
| Untrusted `alg` or unsigned token | 401 | Algorithm/signing policy |
| `iss` differs from exact configured value | 401 | Issuer validator |
| `aud` missing or lacks API audience | 401 | Audience validator |
| `exp` in the past (beyond clock skew) | 401 | Expiration validator |
| `nbf` in the future (beyond clock skew) | 401 | Not-before validator |
| Structurally invalid/unparseable JWT | 401 | Invalid Bearer handling |
| `kid` matches no key in JWKS | 401 | Key selection from JWKS |
| IdP/JWKS unreachable | Must reject authentication; check actual status/error | No fail-open when verification cannot complete |

Rows covering signature/issuer/audience only hold when running through a **real decoder**. If policy allows multiple audiences, `aud` can be a list: check that it **contains** the target audience, and never conflate `aud` with `scope`. `iss` must match the exact trusted issuer (including tenant path, per configuration), rather than comparing hostnames alone. Unauthenticated tokens usually return **401**; valid authenticated tokens with insufficient permissions usually return **403**.

## 8. Common mistakes and how to avoid them

- **Using only `mockJwt()` to claim "JWTs are secure".** Fix with signed-token tests, specifically testing bad signatures, wrong issuers, wrong audiences, and `exp`/`nbf`.
- **Just Base64-decoding the payload and checking claims.** This verifies neither origin nor integrity. Always use a trusted decoder/JWS verifier.
- **Checking `iss` while forgetting `aud`.** Tokens from the same IdP issued for another service can be wrongly accepted. Configure `spring.security.oauth2.resourceserver.jwt.audiences` when using Boot auto-config, or add an audience validator when building the bean manually.
- **Defining a custom `ReactiveJwtDecoder` bean and losing default validators.** Attach `JwtValidators.createDefaultWithIssuer(...)` and an audience validator as needed; double-check timestamp/clock-skew rules.
- **Using Servlet-style `JwtDecoder` in WebFlux.** For a reactive resource server, inject and configure `ReactiveJwtDecoder` with `SecurityWebFilterChain`.
- **Setting authorities directly in a mock and thinking the converter was tested.** Test `scope`/`scp` mapping with real tokens or standalone converter tests; mocked authorities do not prove JWT mapping.
- **Confusing 401 with 403.** 401 usually means authentication failed; 403 means valid identity lacking the required permission.
- **Using timestamps right next to "now" in `exp`/`nbf` tests.** Prone to flakiness from clock skew or CI speed; use a fake clock or sufficiently large offsets.
- **Depending on an external IdP during routine unit/integration runs.** Use dedicated test keys and JWKS stubs; reserve real-IdP E2E tests for controlled environments and schedules.
- **Letting the JWT dictate trust sources or algorithms directly.** Restrict allowed algorithms and public keys via server config, test key rotation, and never trust sender-supplied key URLs.
- **Logging real tokens, private keys, or sensitive details on test failure.** In CI, log only enough error category/reason to diagnose; avoid credential leaks.
- **Running `WebTestClient` against a live HTTP server and assuming `mockJwt()` still intercepts it.** `mockJwt()` is designed for WebFlux mock-server test support; against a live HTTP server you must send `Authorization: Bearer <token>` and configure a matching decoder.

## 9. Workflow for choosing test types during development

Start from endpoint rules: use `mockJwt()` to clearly express which users/scopes are allowed or denied. Next, use real RS256 JWTs with active issuer, audience, and `exp`/`nbf` checks to ensure the auth chain cannot be fooled by fake tokens. Finally, if deployment uses JWKS/issuer discovery, add HTTP stubs to verify `kid` selection, algorithms, rotation, and network failures. Fix any issue found at the layer where it belongs; never replace a real `ReactiveJwtDecoder` with a mock in a test whose goal is verifying signatures.

**Official references:**
- Spring Security — Testing OAuth 2.0 for WebFlux: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security — Reactive OAuth 2.0 Resource Server JWT: https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html
- Spring Boot 3.5 — Resource Server properties and audience configuration: https://docs.spring.io/spring-boot/3.5/reference/web/spring-security.html
