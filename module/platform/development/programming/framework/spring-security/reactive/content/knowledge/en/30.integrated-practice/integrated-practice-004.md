# Building a JWT Resource Server with Issuer, Audience, and Scope Validation — Spring Security Reactive

## Objectives and Scope

This lab builds an **OAuth 2.0 Resource Server** on Spring WebFlux with Java 17+, Spring Boot 3.x, and Spring Security 6.x. The API accepts a **JWT access token** only when four conditions are simultaneously satisfied:

1. **Valid signature and timestamps:** the JWT is signed with a trusted key, uses an allowed algorithm, is not expired, and has reached its valid-from time.
2. **Correct issuer (`iss` claim):** the token was issued by the configured Authorization Server/Identity Provider.
3. **Matching audience (`aud` claim):** the token was issued for this API, for example `api://orders`.
4. **Sufficient scope (`scope` or `scp` claim):** the token grants `orders.read` for GET and `orders.write` for POST.

You will create two endpoints, configure authentication and authorization, understand the Bearer token flow, run an **in-memory real RSA-signed** JWT test suite, distinguish 401/403 responses, and recognize the limits of `mockJwt()`. The lab is designed for learning and running tests offline without embedding production private keys into the application.

## 1. Resource Server Mindset: Authenticate First, Authorize Second

~~~text
HTTP Authorization: Bearer <access token>
              |
              v
WebFlux SecurityWebFilterChain
              |
              v
ReactiveJwtDecoder
   +-- Parse JWT/JWS and alg/kid
   +-- Fetch trusted public key from JWK Set
   +-- Verify signature
   +-- Validate exp, nbf, iss, aud
   |
   +-- Invalid --> 401 Unauthorized
              |
              v
JwtAuthenticationToken
   +-- Principal = Jwt, default name from sub
   +-- scope/scp => GrantedAuthority "SCOPE_*"
              |
              v
authorizeExchange: hasAuthority(...)
   +-- Missing scope --> 403 Forbidden
              |
              v
Controller / service --> 200 OK or 202 Accepted
~~~

`iss` answers **who issued the token**, `aud` answers **which system the token was issued for**, and `scope` answers **which actions the receiving system permits**. Two tokens with the same issuer and valid signatures may still belong to two different APIs. Skipping audience validation risks accepting a token meant for another API; skipping scope validation lets a read-only token perform writes.

An illustrative JWT payload:

~~~json
{
  "iss": "https://idp.example.net/realms/training",
  "sub": "alice",
  "aud": ["api://orders"],
  "scope": "orders.read orders.write",
  "iat": 1760000000,
  "nbf": 1760000000,
  "exp": 1760003600
}
~~~

These numeric timestamps merely illustrate the `NumericDate` format, not a currently valid token. A Base64URL-encoded payload **is not protected by encoding alone**; the JWS signature must be verified with a trusted key before trusting any claims.

| Claim / field | Validation and meaning |
| --- | --- |
| Header `alg` | JWS algorithm must be on an allowlist, e.g., RS256; never trust `alg=none` |
| Header `kid` | Helps look up the public key in the JWK Set; `kid` itself confers no trust |
| `iss` | Matches the trusted issuer, including exact path and trailing `/` |
| `aud` | List of intended token recipients; must contain `api://orders` |
| `exp`, `nbf` | Expired or not-yet-valid tokens are rejected |
| `sub` | Principal identifier accessed by controllers via `Jwt.getSubject()` |
| `scope` / `scp` | Mapped to authorities with the `SCOPE_` prefix |
| `client_id` / `azp` | Does not automatically substitute for audience or scope |

**Access Tokens and ID Tokens are different.** An OIDC ID Token authenticates a login event to an OAuth client and usually has the client ID as its `aud`. A Resource Server requires an **access token issued for its API**; do not use an ID Token simply because it is also a JWT. If your provider uses RFC 9068 JWT access tokens, verify the corresponding token type/profile as well.

## 2. Creating the Java 17+ / Spring WebFlux Project

In a Spring Boot 3.x project already configured with Gradle plugins and dependency management, declare in `build.gradle`:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Spring Boot Resource Server starter provides the required OAuth2/JWT libraries. When managing dependencies manually, both `spring-security-oauth2-resource-server` and `spring-security-oauth2-jose` are required to decode and verify JWTs.

Use **reactive APIs**: `ServerHttpSecurity`, `SecurityWebFilterChain`, `ReactiveJwtDecoder`, and `WebTestClient`. `HttpSecurity`, `SecurityFilterChain`, `NimbusJwtDecoder`, and `MockMvc` belong to the Servlet stack and are not the WebFlux equivalents.

## 3. Configuring Issuer, Audience, and JWK Set

File `src/main/resources/application.yml`:

~~~yaml
server:
  port: 8080

spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: "https://idp.example.net/realms/training"
          jwk-set-uri: "https://idp.example.net/realms/training/protocol/openid-connect/certs"
          audiences:
            - "api://orders"
~~~

**These URLs are examples to replace with your real IdP.** Before running the application with Bearer tokens from an IdP, update the issuer and JWK Set URI per your provider's docs, issue tokens with the proper audience, and ensure the API reaches the JWK Set over HTTPS. To run the tests in section 8, no real IdP is needed because the tests register an in-memory RSA decoder.

- `issuer-uri` identifies the trusted issuer and expected `iss` value. Full path matching applies; an issuer with or without a trailing slash can be two distinct values.
- `jwk-set-uri` locates the public keys used to verify signatures. When both `issuer-uri` and `jwk-set-uri` are declared, the Resource Server can avoid metadata discovery at startup to find the JWK URI while **still validating the issuer**. If only `issuer-uri` is set, the framework discovers the endpoint via provider metadata.
- `audiences` is a built-in property starting in Spring Boot 3.3 for both Servlet and reactive Resource Servers. The token's `aud` must contain `api://orders`. Tokens missing `aud` or containing only `api://reports` fail authentication.
- The default check uses **contains** semantics, meaning `aud=["api://orders","api://reports"]` is accepted when `api://orders` is required. A “single audience only” policy requires a custom validator rather than assuming strict equality from `contains`.

Signature verification depends on public keys from a trusted source. Never fetch an arbitrary JWK Set URI supplied by a token or request, and never let a JWT header choose the issuer dynamically.

### When to Declare a ReactiveJwtDecoder Bean

YAML alone suffices for standard issuer + audience requirements. If you need custom claim policies, multi-tenant allowlists, or special audience rules, you can replace auto-configuration with an explicit `ReactiveJwtDecoder` bean:

~~~java
// Fragment integrated into a @Configuration class with two config values:
// String issuer; String jwkSetUri;
@Bean
ReactiveJwtDecoder jwtDecoder() {
    NimbusReactiveJwtDecoder decoder =
            NimbusReactiveJwtDecoder.withJwkSetUri(jwkSetUri).build();

    OAuth2TokenValidator<Jwt> defaults =
            JwtValidators.createDefaultWithIssuer(issuer);

    OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
            jwt.getAudience().contains("api://orders")
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error("invalid_token",
                                    "Wrong audience for orders API", null));

    decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
            defaults, audienceValidator));
    return decoder;
}
~~~

This is an **illustrative replacement snippet**, not a standalone runnable file: it requires Spring Security imports, injected `issuer`/`jwkSetUri`, and `@Configuration`. When calling `setJwtValidator`, you must **compose** the default validator (`JwtValidators.createDefaultWithIssuer`, covering timestamps and issuer) with the audience validator. Replacing everything with only the audience validator can accidentally disable timestamp/issuer validation. Declaring your own bean also overrides Boot's auto-configured decoder, so double-check your configuration before deploying.

## 4. Configuring WebFlux Security for Scope-Based Authorization

File `src/main/java/com/example/orders/OrdersApplication.java`:

~~~java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {
    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
~~~

File `src/main/java/com/example/orders/SecurityConfig.java`:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.reactive.EnableWebFluxSecurity;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;
import org.springframework.security.web.server.context.NoOpServerSecurityContextRepository;

@Configuration
@EnableWebFluxSecurity
public class SecurityConfig {

    @Bean
    SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
        return http
                // Applies only to stateless APIs using the Bearer header:
                .csrf(ServerHttpSecurity.CsrfSpec::disable)
                .securityContextRepository(
                        NoOpServerSecurityContextRepository.getInstance())
                .authorizeExchange(exchanges -> exchanges
                        .pathMatchers(HttpMethod.GET, "/api/orders")
                            .hasAuthority("SCOPE_orders.read")
                        .pathMatchers(HttpMethod.POST, "/api/orders")
                            .hasAuthority("SCOPE_orders.write")
                        .anyExchange().denyAll())
                .oauth2ResourceServer(oauth2 -> oauth2
                        .jwt(Customizer.withDefaults()))
                .build();
    }
}
~~~

Analysis:

- `oauth2ResourceServer(...jwt(...))` enables Bearer JWT authentication. Spring Security builds an `Authentication` from the JWT verified by the decoder.
- `hasAuthority("SCOPE_orders.read")` requires the read-scope authority; POST requires `SCOPE_orders.write`.
- By default `JwtGrantedAuthoritiesConverter` converts `scope="orders.read orders.write"` into `SCOPE_orders.read` and `SCOPE_orders.write`; it also supports the `scp` claim using default rules.
- `hasRole("ADMIN")` uses the `ROLE_` prefix convention, which is **distinct** from scopes. Do not use role APIs to match `SCOPE_orders.read`.
- `NoOpServerSecurityContextRepository` suits a Bearer-only stateless API: each request supplies its own Bearer token without relying on `WebSession` to “remember” the user.
- CSRF is disabled solely **because this is a stateless demo not relying on cookies**. If the system serves browser sessions/cookies alongside Bearer auth, design CSRF properly rather than disabling it broadly.
- `anyExchange().denyAll()` reduces the risk of newly added endpoints being exposed publicly by mistake. Explicitly open any operational health/public routes if your application requires them.

File `src/main/java/com/example/orders/OrdersController.java`:

~~~java
package com.example.orders;

import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

import reactor.core.publisher.Mono;

@RestController
public class OrdersController {
    public record OrderList(String owner, List<String> orderIds) {}

    @GetMapping("/api/orders")
    public Mono<OrderList> list(@AuthenticationPrincipal Jwt jwt) {
        return Mono.just(new OrderList(
                jwt.getSubject(), List.of("order-1001", "order-1002")));
    }

    @PostMapping("/api/orders")
    @ResponseStatus(HttpStatus.ACCEPTED)
    public Mono<Map<String, String>> create(
            @AuthenticationPrincipal Jwt jwt) {
        return Mono.just(Map.of(
                "status", "accepted", "owner", jwt.getSubject()));
    }
}
~~~

The controller receives the authenticated `Jwt`; `jwt.getSubject()` returns the subject. The hardcoded order IDs merely illustrate security, not real order management logic. In production, enforce per-order tenant/ownership checks as well rather than assuming a read scope grants access to every order. With multiple issuers, user identity typically requires combining both issuer and subject.

## 5. Interpreting 401, 403, 200, and 202

| Token and request | Decoder/authentication | Scope/authorization | Result |
| --- | --- | --- | --- |
| Missing Bearer token | No principal | Not evaluated | **401 Unauthorized** |
| Invalid signature or disallowed algorithm | Invalid | Not evaluated | **401** |
| `exp` passed or `nbf` in future | Invalid | Not evaluated | **401** |
| Issuer differs from `issuer-uri` | Invalid | Not evaluated | **401** |
| `aud` missing `api://orders` | Invalid | Not evaluated | **401** |
| Valid JWT with `orders.write` calling GET | Valid | Missing `orders.read` | **403 Forbidden** |
| Valid JWT with `orders.read` calling POST | Valid | Missing `orders.write` | **403** |
| Valid JWT with `orders.read` calling GET | Valid | Matching scope | **200 OK** |
| Valid JWT with `orders.write` calling POST | Valid | Matching scope | **202 Accepted** |

The HTTP statuses in the table reflect the expected behavior of the example security chain and controller. Alongside the status, Bearer responses may include `WWW-Authenticate` with `invalid_token` / `insufficient_scope` details depending on the handler. Do not convert every failure into 403, and never return HTTP 200 with a failure payload when authentication actually failed.

## 6. Why mockJwt() Is Insufficient for Testing Issuer and Audience

Spring Security Test provides `SecurityMockServerConfigurers.mockJwt()`:

~~~java
// Fragment placed in a JUnit test configured with WebTestClient:
client.mutateWith(mockJwt()
        .jwt(jwt -> jwt.claim("sub", "alice")
                .claim("scope", "orders.read")))
      .get().uri("/api/orders")
      .exchange().expectStatus().isOk();
~~~

`mockJwt()` builds a synthetic `Authentication` and inserts it into the request's `SecurityContext`. It **does not** invoke `ReactiveJwtDecoder`, **does not** fetch a JWK Set, and **does not** verify signature, issuer, audience, or expiration. It is useful for testing authority mapping and controllers, but it does not prove real token validation works. By default, a mock JWT has `sub=user` and `scope=read`; you can customize claims or supply authorities per case.

A strong test suite includes both:

- **Authorization tests:** using `mockJwt()` to check GET/POST with sufficient and missing scopes.
- **Decoder/integration tests:** sending **real signed** RS256 Bearer tokens, varying `iss`, `aud`, `exp`, and signature, and observing Spring Security return 401/403/2xx.

The test suite below implements the second category, and a final test deliberately demonstrates the difference from `mockJwt()`.

## 7. Offline End-to-End Testing with Real RSA-Signed JWTs

No running IdP is needed. The test generates a fresh in-memory RSA `KeyPair`, signs tokens with the private key, and configures a `NimbusReactiveJwtDecoder` with the public key. It replaces Boot's auto-configured decoder **only in the test context**, combining default issuer/timestamp validation with the audience validator. Every Bearer request still passes through the actual WebFlux security filters and decoder.

File `src/test/java/com/example/orders/OrdersResourceServerTest.java`:

~~~java
package com.example.orders;

import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.interfaces.RSAPrivateKey;
import java.security.interfaces.RSAPublicKey;
import java.time.Instant;
import java.util.Date;
import java.util.List;

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
import org.springframework.context.annotation.Primary;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.jwt.ReactiveJwtDecoder;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
        .SecurityMockServerConfigurers.springSecurity;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@Import(OrdersResourceServerTest.LocalJwtTestConfig.class)
class OrdersResourceServerTest {
    private static final String ISSUER =
            "https://idp.example.net/realms/training";
    private static final String AUDIENCE = "api://orders";

    @Autowired
    ApplicationContext context;

    @Autowired
    KeyPair testKeys;

    private WebTestClient client;

    @BeforeEach
    void setUp() {
        client = WebTestClient.bindToApplicationContext(context)
                .apply(springSecurity())
                .configureClient()
                .build();
    }

    @Test
    void absentBearerReturns401() {
        client.get().uri("/api/orders")
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validSignatureIssuerAudienceAndReadScopeReturns200()
            throws Exception {
        String jwt = sign(testKeys.getPrivate(), ISSUER, AUDIENCE,
                "orders.read", Instant.now().plusSeconds(300));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isOk()
                .expectBody()
                .jsonPath("$.owner").isEqualTo("alice")
                .jsonPath("$.orderIds[0]").isEqualTo("order-1001");
    }

    @Test
    void differentIssuerReturns401() throws Exception {
        String jwt = sign(testKeys.getPrivate(),
                "https://other-issuer.example.net", AUDIENCE,
                "orders.read", Instant.now().plusSeconds(300));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void differentAudienceReturns401() throws Exception {
        String jwt = sign(testKeys.getPrivate(), ISSUER,
                "api://reports", "orders.read",
                Instant.now().plusSeconds(300));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void expiredTokenReturns401() throws Exception {
        // Expired beyond the default 60-second clock skew.
        String jwt = sign(testKeys.getPrivate(), ISSUER, AUDIENCE,
                "orders.read", Instant.now().minusSeconds(180));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void forgedSignatureReturns401() throws Exception {
        KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        KeyPair untrusted = generator.generateKeyPair();

        String jwt = sign(untrusted.getPrivate(), ISSUER, AUDIENCE,
                "orders.read", Instant.now().plusSeconds(300));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isUnauthorized();
    }

    @Test
    void validTokenButWrongReadScopeReturns403() throws Exception {
        String jwt = sign(testKeys.getPrivate(), ISSUER, AUDIENCE,
                "orders.write", Instant.now().plusSeconds(300));

        client.get().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void validWriteScopeCanPost() throws Exception {
        String jwt = sign(testKeys.getPrivate(), ISSUER, AUDIENCE,
                "orders.write", Instant.now().plusSeconds(300));

        client.post().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isAccepted()
                .expectBody()
                .jsonPath("$.status").isEqualTo("accepted")
                .jsonPath("$.owner").isEqualTo("alice");
    }

    @Test
    void readScopeCannotPost() throws Exception {
        String jwt = sign(testKeys.getPrivate(), ISSUER, AUDIENCE,
                "orders.read", Instant.now().plusSeconds(300));

        client.post().uri("/api/orders")
                .header(HttpHeaders.AUTHORIZATION, "Bearer " + jwt)
                .exchange().expectStatus().isForbidden();
    }

    @Test
    void mockJwtChecksScopeButDoesNotCheckIssuerOrAudience() {
        // iss and aud intentionally wrong: still 200 because mockJwt bypasses the decoder.
        client.mutateWith(mockJwt().jwt(jwt -> jwt
                    .claim("iss", "https://other-issuer.example.net")
                    .claim("aud", List.of("api://reports"))
                    .claim("scope", "orders.read")))
                .get().uri("/api/orders")
                .exchange().expectStatus().isOk();
    }

    private String sign(
            PrivateKey privateKey, String issuer, String audience,
            String scope, Instant expiration) throws JOSEException {
        Instant now = Instant.now();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject("alice")
                .audience(List.of(audience))
                .issueTime(Date.from(now.minusSeconds(20)))
                .notBeforeTime(Date.from(now.minusSeconds(10)))
                .expirationTime(Date.from(expiration))
                .claim("scope", scope)
                .build();

        SignedJWT signed = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .type(JOSEObjectType.JWT).build(), claims);
        signed.sign(new RSASSASigner((RSAPrivateKey) privateKey));
        return signed.serialize();
    }

    @TestConfiguration(proxyBeanMethods = false)
    static class LocalJwtTestConfig {
        @Bean
        KeyPair testKeys() throws Exception {
            KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
            generator.initialize(2048);
            return generator.generateKeyPair();
        }

        @Bean
        @Primary
        ReactiveJwtDecoder testDecoder(KeyPair testKeys) {
            NimbusReactiveJwtDecoder decoder =
                    NimbusReactiveJwtDecoder.withPublicKey(
                            (RSAPublicKey) testKeys.getPublic()).build();

            OAuth2TokenValidator<Jwt> defaults =
                    JwtValidators.createDefaultWithIssuer(ISSUER);

            OAuth2TokenValidator<Jwt> audience = jwt ->
                    jwt.getAudience().contains(AUDIENCE)
                            ? OAuth2TokenValidatorResult.success()
                            : OAuth2TokenValidatorResult.failure(
                                    new OAuth2Error("invalid_token",
                                            "Wrong audience for orders API",
                                            null));

            decoder.setJwtValidator(
                    new DelegatingOAuth2TokenValidator<>(
                            defaults, audience));
            return decoder;
        }
    }
}
~~~

### What Is Verified?

- `testKeys()` generates an RSA key pair directly in the test context without pulling production private keys.
- `sign(...)` creates an RS256 JWS JWT with `iss`, `aud`, `scope`, `exp`, `nbf`, and a real signature.
- `testDecoder(...)` uses only the matching public key; signatures from other keys are rejected.
- `JwtValidators.createDefaultWithIssuer(ISSUER)` enforces standard JWT checks plus issuer; the additional audience validator requires `api://orders`.
- `@Import` registers the test decoder bean so Boot does not auto-create the default decoder; thus the tests never contact the illustrative JWK Set URI in YAML.
- The tests send a Bearer header through the filter, decoder, and authorization rules. The final test uses `mockJwt()` to **demonstrate that mocking alone skips issuer/audience validation**.

This test file verifies both authentication and authorization across the pipeline rather than calling the validator directly and assuming the filter chain works. The keys are test data; **a production Resource Server must never receive the IdP's private key**.

Run from the Gradle project root:

~~~bash
./gradlew test --tests 'com.example.orders.OrdersResourceServerTest'
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test --tests com.example.orders.OrdersResourceServerTest
~~~

Expected result when files and dependencies are placed properly: **10 tests PASS**. This is the expected logical outcome of the sample; always run Gradle in the project to confirm your implementation. Running local tests requires no IdP; running the application with real access tokens still requires a reachable issuer/JWK URI.

## 8. Testing HTTP Calls with a Real IdP Token

To run `bootRun` for real, replace the three sample issuer/JWK Set/audience values in YAML with the configuration provided by your IdP:

~~~bash
./gradlew bootRun
~~~

Obtain a valid **access token** using the appropriate OAuth2 flow (e.g., Authorization Code for users or Client Credentials for machine-to-machine, depending on the use case). The token must have the right issuer, the API's audience, the required scope, not be expired, and be signed by the IdP trusted by the Resource Server.

Place the access token in the `ACCESS_TOKEN` environment variable using your environment's secure mechanism, never committing it to source control. Run:

~~~bash
curl -i -H "Authorization: Bearer $ACCESS_TOKEN" \
    http://localhost:8080/api/orders
~~~

Windows PowerShell:

~~~powershell
curl.exe -i -H "Authorization: Bearer $env:ACCESS_TOKEN" http://localhost:8080/api/orders
~~~

To test creating an order, change GET to POST and request a token with `orders.write`. The `idp.example.net` URLs are not a live IdP; when you do not have a provider available, run the RSA test suite in section 7.

**Do not use an ID Token in place of an access token**, and never copy non-expired JWTs into public logs. A Base64 decoder can read the payload, but it does not prove signature, issuer, or audience checks passed.

## 9. Scope, scp, and Authorities

Spring Security maps scopes to authorities with the `SCOPE_` prefix by default.

| Claim in JWT | Default result |
| --- | --- |
| `"scope": "orders.read"` | `SCOPE_orders.read` |
| `"scope": "orders.read orders.write"` | `SCOPE_orders.read` and `SCOPE_orders.write` |
| `"scp": ["orders.read","orders.write"]` | Both corresponding authorities |
| Missing both `scope` and `scp` | No scope authorities generated |
| `"roles": ["ADMIN"]` | Does not generate `ROLE_ADMIN` by default |

If your IdP uses a custom `permissions` claim or a different scope format, configure a converter. Example **fragment** changing authority mapping (use only if your provider actually issues a `permissions` claim):

~~~java
JwtGrantedAuthoritiesConverter grants = new JwtGrantedAuthoritiesConverter();
grants.setAuthoritiesClaimName("permissions");
grants.setAuthorityPrefix("SCOPE_");

ReactiveJwtAuthenticationConverter converter =
        new ReactiveJwtAuthenticationConverter();
converter.setJwtGrantedAuthoritiesConverter(
        new ReactiveJwtGrantedAuthoritiesConverterAdapter(grants));

http.oauth2ResourceServer(oauth2 -> oauth2
        .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)));
~~~

This fragment belongs inside a configuration class, requires Spring Security imports, and is not a standalone file. **An authority converter does not replace audience/issuer validators**. If using a custom converter, add tests with real tokens and confirm missing scopes still yield 403.

## 10. Common Errors and Troubleshooting

| Symptom | Likely cause | How to check |
| --- | --- | --- |
| 401 despite valid token signature | Wrong `iss`, wrong `aud`, expired, or not yet valid | Compare actual claims against config; check timestamps |
| 401 after key rotation | JWK Set lacks public key for `kid` or is unreachable | Check TLS, JWK endpoint, and cache refresh |
| JWT meant for another API returns 200 | Audience validation disabled or not configured | Configure `audiences`; add a wrong-audience test |
| 403 with valid Bearer token | Missing `SCOPE_orders.read`/`SCOPE_orders.write` | Inspect `scope`/`scp`, mapping, and route policy |
| `mockJwt()` tests pass but real tokens always return 401 | Mock bypasses signature/issuer/audience | Run RSA-signed token tests with a real decoder |
| 403 on POST | Missing write scope or CSRF still enabled in a cookie-based app | Check authorities/CSRF according to authentication type |
| Only getting an ID Token from IdP | Requesting the wrong token type | Request an access token targeting the API resource |
| Custom decoder stops checking expiration | `setJwtValidator` replaced default validators | Compose `JwtValidators.createDefaultWithIssuer` with custom validators |
| API accepts every path | Overly broad `permitAll` rule or wrong matcher order | Specify method + path explicitly; default deny |
| Logs contain full access tokens | Logging Authorization header or sensitive claims | Strip tokens from logs; use trace IDs and error categories |

Never “fix” a 401 by adding `permitAll()`, disabling signature validation, removing audience checks, or allowing `alg=none`. If a token lacks a scope, do not fix it by granting every authority—adjust IdP provisioning and API rules deliberately.

## 11. Additional Requirements for Production Deployment

**Algorithm and trust restrictions.** Accept only public keys from the trusted issuer using RS256 or an approved algorithm set. Never fetch a JWK Set URL dynamically from an untrusted JWT header, and never let a token choose its own issuer freely. For multi-tenancy, use an allowlist of valid issuers and a safe decoder selection mechanism.

**Expiration and clock skew.** Spring Security validates `exp` and `nbf`; configure a small clock skew tolerance if expected clock drift exists. Never widen tolerance indefinitely or disable validation just for test convenience. The test suite sets the expired token 180 seconds in the past to exceed typical tolerance.

**Business-level authorization.** `orders.read` grants access to the endpoint, not automatically to every individual order. Add ownership/tenant checks in the service layer. With client credentials, `sub` may identify a service/client rather than an individual user.

**IdP/JWK availability.** Refreshing keys can require outbound HTTP calls. Apply proper timeouts and cache policies, monitor JWK fetch errors, and never fail open when a signature cannot be verified. Plan for key rotation and token revocation processes.

**Observability.** Distinguish 401 (invalid token), 403 (insufficient authority), and upstream errors. Track error rates and latency with bounded labels; never put raw tokens, emails, user IDs, or sensitive claims into metric labels.

**Test strategy.** Run fast authorization tests with `mockJwt()`, integration tests with real signed JWTs and a real decoder, and staging tests against the real IdP to verify metadata/JWK/TLS/clocks and exact issuer/audience configuration. Never treat mocked tests as proof that cryptography works.

## 12. Lab Completion Checklist

- [ ] Uses a Spring WebFlux security chain without mixing Servlet APIs.
- [ ] Configures `issuer-uri` matching the Authorization Server's issuer.
- [ ] Configures a valid JWK URI/trusted key and allowed algorithms.
- [ ] Configures `audiences` matching the `api://orders` resource.
- [ ] GET requires `SCOPE_orders.read`; POST requires `SCOPE_orders.write`.
- [ ] Missing token, bad signature, wrong issuer, wrong audience, expired -> 401.
- [ ] Valid JWT missing the required scope -> 403.
- [ ] Valid JWT with the matching scope -> 200 for GET, 202 for POST.
- [ ] Includes tests with **real signed JWTs**, not just `mockJwt()`.
- [ ] Distinguishes ID Tokens from Access Tokens and rejects tokens for other APIs.
- [ ] Keeps private keys, access tokens, and sensitive claims out of source control and logs.
- [ ] Accounts for key rotation, timeouts, and ownership/tenant checks.

## Official References

- [Spring Security — Reactive Resource Server JWT](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): decoder configuration, issuer, JWK Set, authorities, and audience validators.
- [Spring Boot 3.3 — Security Resource Server](https://docs.spring.io/spring-boot/3.3/reference/web/spring-security.html): `issuer-uri`, `jwk-set-uri`, and `audiences` properties in both reactive and Servlet stacks.
- [Spring Security — Testing OAuth 2.0 in WebFlux](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html): `mockJwt()` and fixture limitations.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): `iss`, `aud`, `exp`, `nbf`, and `sub`.
- [RFC 9068 — JWT Profile for OAuth2 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): requirements for dedicated JWT access tokens.

Key principle to remember: **a JWT with a valid signature is not automatically meant for this API**, and **a JWT with a valid issuer and audience is not automatically allowed to call every endpoint**. Authentication, audience selection, and scope authorization are three independent gates that must be configured and verified separately.