# Mocked Tokens vs. Testing Real Decoders, Signatures, or Introspection

## 1. The distinction to make

A Spring Security test can return HTTP `200 OK` when using `jwt()` in MockMvc or `mockJwt()` in WebTestClient, even when the real API **rejects** the JWT due to a bad signature, wrong `aud`, forged `iss`, rotated keys, expired token, or introspection returning `active=false`.

Reason: authentication mocking utilities in `spring-security-test` set up an already-trusted `Authentication`/`SecurityContext` to test **authorization and business logic**. They **do not automatically issue a real Bearer credential through a decoder or call an authorization server**. A green controller/role test does not prove token verification at the system boundary is secure.

This lesson belongs to the **Login Testing** group in the Spring Security authentication module, yet three layers often loosely called "login tests" must be separated:

- **User login** via form/session or OIDC `oauth2Login()`: creates a session or executes Authorization Code Flow.
- **Bearer access token verification at the Resource Server**: each request with `Authorization: Bearer ...` is checked by a JWT decoder or opaque-token introspector before building `Authentication`.
- **Access authorization**: after Authentication is valid, scope/role/ACL rules decide 200, 403, or 404.

A mock JWT test can test the last layer without checking **signature/claims** in the second layer. Similarly, `oidcLogin()` supplies a mocked principal to test controllers, not proving the Spring client actually performed OIDC discovery, nonce, state, token exchange, or ID token signature verification.

### Learning objectives

1. Know precisely what `jwt()`, `opaqueToken()`, `mockJwt()`, `mockOpaqueToken()`, mock `JwtDecoder`, and mock `OpaqueTokenIntrospector` verify vs. skip.
2. Write fast unit/controller tests with mocked tokens and state **the exact scope of their evidence**.
3. Use `NimbusJwtDecoder` and **genuinely signed** RSA/JWS tokens to verify signatures, trusted keys, algorithms, and `iss/aud/exp/nbf` policies.
4. Test `SpringOpaqueTokenIntrospector` sending HTTP to a controlled endpoint, handling `active=true/false` and infrastructure errors.
5. Run tests through the **HTTP filter chain** with string Bearer tokens rather than pre-built principal post-processors to verify exact statuses/challenges.
6. Understand what must be tested separately against staging IdP/JWKS/introspection servers: caching, rotation, introspection client auth, timeouts, TLS, and revocation.
7. Avoid putting real tokens, private keys, or credentials into logs or public test fixtures.

**Version assumptions:** Java 17+, Spring Boot 3.x / Spring Security 6.5.x, Spring Framework 6.x, Spring Security Test, JUnit Jupiter. Some classes have different packages or DSLs in Spring Security 7.x, so check your project BOM. Never run illustrative snippets in production with hardcoded secrets.

## 2. Proper mechanism: who confirms a credential is valid?

### 2.1. JWT Resource Server

~~~text
Client: Authorization: Bearer eyJhbGciOiJSUzI1NiIs...
             |
             v
BearerTokenAuthenticationFilter
             |
             v
JwtAuthenticationProvider
             |
             v
JwtDecoder.decode(rawJwt)
   |- parse compact JWS, check structure/alg
   |- select trusted public key (static or JWKS)
   |- verify signature/MAC
   |- validate exp, nbf, iss, aud, typ, custom policy
             |
        +----+-------+
        |            |
      valid        invalid
        |            |
        v            v
 JwtAuthentication  Authentication failure
        |            |
        v            v
 scope -> SCOPE_*  401, WWW-Authenticate
        |
        v
  AuthorizationManager (scope/ACL)
        |             |
      allow          deny
        |             |
      200/2xx      403/404 policy
~~~

Exact ordering and validators depend on configuration, yet **the crux** is that a real token must enter `JwtDecoder.decode(String)`, rather than dropping a pre-built `Jwt` object into `SecurityContext`. A valid signature alone **is not enough** for token acceptance: issuer, audience, time window, token type, and scope policy must also be valid.

### 2.2. Opaque Token Resource Server

~~~text
Client: Authorization: Bearer opaque-secret-value
             |
             v
BearerTokenAuthenticationFilter
             |
             v
OpaqueTokenAuthenticationProvider
             |
             v
OpaqueTokenIntrospector.introspect(rawToken)
             |
             +-- HTTPS POST to authorization server
             |      (client authentication + token)
             |      <--- {"active":true,"sub":"alice","scope":"orders.read"}
             |
             +-- if active false / unable to verify:
             |      Authentication failure
             |
             v
OAuth2AuthenticatedPrincipal + authorities
             |
             v
AuthorizationManager
~~~

In opaque-token mode, **the authorization server is where status is confirmed**; the application cannot infer `active` from a token having dots like a JWT. Spring Security allows introspecting even JWT-shaped tokens if the resource server is configured that way. This differs from local signature verification via `NimbusJwtDecoder` and has different revocation/availability characteristics.

### 2.3. Comparison table

| Test level | What the test does | Real JWT signature/time/issuer/audience? | Calls introspection HTTP? |
| --- | --- | --- | --- |
| `MockMvc .with(jwt())` | Injects mocked `JwtAuthenticationToken` into request/security context | **No** | No |
| `MockMvc .with(opaqueToken())` | Injects mocked opaque principal and configured authorities | No | **No** |
| `WebTestClient .mutateWith(mockJwt())` | Injects reactive security context with JWT Authentication | **No** | No |
| `WebTestClient .mutateWith(mockOpaqueToken())` | Injects reactive opaque principal | No | **No** |
| Mock `JwtDecoder.decode(...)` returning `Jwt` | Tests filter/provider calling decoder per stub | **No**, because stub returns canned result | No |
| Mock `OpaqueTokenIntrospector` returning principal | Tests provider/authorization mapping per stub | No | **No**, because stub skips HTTP |
| `NimbusJwtDecoder` + genuinely signed token + real key | Verifies JWS and configured validators | **Yes**, within test key/validators scope | No |
| `SpringOpaqueTokenIntrospector` + `MockRestServiceServer` | Runs real HTTP client/introspector against mock HTTP transport, testing active/errors | No | **Yes via mocked HTTP client**, not live IdP |
| Resource Server filter chain + real signed Bearer header | Tests wiring filter → decoder → authorization → HTTP | **Yes**, if using real decoder | Mode-dependent |
| Local test IdP/JWKS/introspection server or staging | Tests protocol endpoints, discovery, TLS, cache/rotation, client auth | Yes if configured properly | Real network calls to test server |

**Never treat a 200 test using a mock principal as proof that a token has a valid signature.** Name tests after their real scope: `canReadOrdersWithScope()` differs from `rejectsWrongJwtSignature()`.

## 3. Using mock tokens for the right purpose

### 3.1. MockMvc Servlet: `jwt()` and `opaqueToken()`

Suppose `GET /api/orders` is protected by `hasAuthority("SCOPE_orders.read")` with a controller returning 200 for authorized users. The snippets below are **fragments placed inside a test class already configured with MockMvc and the Spring Security filter chain**, not standalone runnable code:

~~~java
import static org.springframework.security.test.web.servlet
    .request.SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.security.test.web.servlet
    .request.SecurityMockMvcRequestPostProcessors.opaqueToken;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Mock JWT: tests authorization policy, does not verify signature.
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
   .andExpect(status().isOk());

// Mock JWT missing scope: tests authorization denial.
mvc.perform(get("/api/orders").with(jwt()))
   .andExpect(status().isForbidden());

// Mock opaque principal: introspection endpoint is never called.
mvc.perform(get("/api/orders")
        .with(opaqueToken().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read"))))
   .andExpect(status().isOk());
~~~

**Imports in the snippet are line-wrapped for text width; in a Java file, each `import` statement must sit on a single line.** Use IDE auto-import in a real project; the `jwt` method lives in `SecurityMockMvcRequestPostProcessors`, not `org.springframework.security.oauth2.jwt.Jwt`. You can customize claims with `jwt().jwt(builder -> builder.claim("scope", "orders.read"))`, yet those remain **test-constructed** claims. It does not prove a JWT was signed or verified.

Limitations: the route must exist, `MockMvc` must integrate Spring Security and the `hasAuthority(...)` rule; without matching setup, assumed 200/403 statuses are not guaranteed. In HTTP filter tests exercising a real JWT decoder, **do not use `.with(jwt())`**.

### 3.2. Reactive WebTestClient

For a WebFlux app using `SecurityWebFilterChain`, `WebTestClient` with Spring Security test support applied:

~~~java
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockJwt;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOpaqueToken;

import org.springframework.security.core.authority.SimpleGrantedAuthority;

// Mock reactive JWT, used to test mapping/authorization:
client.mutateWith(mockJwt().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders").exchange()
    .expectStatus().isOk();

// Mock reactive opaque token:
client.mutateWith(mockOpaqueToken().authorities(
        new SimpleGrantedAuthority("SCOPE_orders.read")))
    .get().uri("/api/orders").exchange()
    .expectStatus().isOk();
~~~

**Also a snippet with wrapped imports**, not a standalone file; unwrap imports onto single lines when pasting. Do not conclude `ReactiveJwtDecoder.decode(...)` or `ReactiveOpaqueTokenIntrospector.introspect(...)` ran. To test a real reactive decoder/introspector, send a Bearer header in a real request through `WebTestClient`, using a properly configured server/test fixture and checking `Mono`/HTTP statuses.

### 3.3. How do a mocked decoder and a fake principal differ?

Distinguish carefully:

- **Principal injection** (`jwt()`, `mockJwt()`): the test builds an authentication object and places it in the security context before authorization. Reading the token from headers and running the verifier are usually bypassed.
- **Mock `JwtDecoder`**: the filter/provider may still read the Bearer header and **call** `decode(String)`, yet what is returned is decided by the mock. Tests can check error mapping, 401 responses, and that the decoder was invoked; **it does not prove RSA signature verification**.
- **Real decoder**: sends a genuinely signed JWT compact string, invoking `NimbusJwtDecoder.decode(token)` or going through the resource server filter. Only this approach (with right/wrong keys and proper validators) directly tests the crypto/claims path.
- **Mock introspector**: similar to a mock decoder, without sending HTTP to the introspection endpoint; tests response handling rather than real request formatting, authentication headers, `active`, or network failures.

An anti-pattern:

~~~java
// This test only proves that the mock decoder returns Jwt as stubbed.
when(jwtDecoder.decode("anything")).thenReturn(fakeJwt);
mvc.perform(get("/api/orders")
        .header("Authorization", "Bearer anything"))
   .andExpect(status().isOk());
~~~

This snippet assumes Mockito, `jwtDecoder`, `fakeJwt`, `mvc`, and a valid route exist. `anything` need not be a signed compact JWT; because `JwtDecoder` was stubbed, the test can still go green. Call this a **filter wiring test**, not a `verifiesJwtSignature` test.

## 4. Preparing dependencies and layering tests

In a Spring Boot 3.x project with plugin/BOM version management, you can declare:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-oauth2-resource-server` includes the components needed for JWT decoders and opaque introspectors. The Spring Boot BOM manages versions so JUnit/Spring Security/Nimbus stay compatible; never mix an arbitrary Spring Security version outside the BOM without evaluating. `spring-boot-starter-test` provides JUnit 5, Mockito, Spring Test, `MockRestServiceServer`, and MVC test utilities.

Tests should be organized as:

- **Fast authorization tests:** `mockJwt`/`mockOpaqueToken`, no IdP startup, checking route/role/claim mapping and business ACLs.
- **Decoder unit tests:** real `NimbusJwtDecoder`, ephemeral in-memory test RSA keys, genuinely signed JWTs; verifying signature/issuer/audience/time/algorithm.
- **Introspection HTTP-client component tests:** real `SpringOpaqueTokenIntrospector` and `MockRestServiceServer` simulating wire responses, testing POST form/client auth and `active`.
- **Resource Server filter integration:** client sends real `Authorization: Bearer <token>`, verifying filters, JWT decoder/introspector, success/401/403, and challenges.
- **Provider contract/e2e:** test server hosting JWKS/introspection or staging IdP with TLS/client credentials, testing cache/rotation/revocation/latency; this is where network bugs invisible to mock transports surface.

Choose tests according to **threat model**. Not every controller test needs a live IdP, yet trust boundaries require a layer that verifies them for real.

## 5. JUnit 5: `NimbusJwtDecoder` genuinely verifying RSA signatures and claims

This example is **a complete JUnit 5 class** for Spring Security 6.5.x using the Nimbus JOSE + JWT library included via the resource-server dependency. It generates 2048-bit RSA keys in the test, **signs a compact RS256 JWT** with private key A, verifies with public key A, and tests a signature from private key B plus invalid claims.

Each test uses a fresh in-memory key pair; no production certificates or real tokens exist. `withPublicKey` verifies against a fixed public key and **does not test HTTP JWKS/discovery**; that category is separated in section 6.

Create `src/test/java/example/RealJwtDecoderTest.java`:

~~~java
package example;

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
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtClaimValidator;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class RealJwtDecoderTest {

    private static final String ISSUER =
        "https://issuer.example.test/realms/demo";
    private static final String AUDIENCE = "orders-api";

    private KeyPair trusted;
    private NimbusJwtDecoder decoder;

    private static KeyPair newRsaKeyPair() throws Exception {
        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);
        return generator.generateKeyPair();
    }

    @BeforeEach
    void setUp() throws Exception {
        trusted = newRsaKeyPair();

        decoder = NimbusJwtDecoder
            .withPublicKey((RSAPublicKey) trusted.getPublic())
            .build();

        // Default timestamp/issuer + API audience validator.
        var audience = new JwtClaimValidator<List<String>>(
            "aud", value -> value != null && value.contains(AUDIENCE));

        decoder.setJwtValidator(
            new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                audience));
    }

    private static String signedJwt(
            KeyPair signingKey,
            String issuer,
            String audience,
            Instant expiresAt) throws Exception {

        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(issuer)
            .subject("alice")
            .audience(audience)
            .issueTime(Date.from(now.minusSeconds(20)))
            .notBeforeTime(Date.from(now.minusSeconds(10)))
            .expirationTime(Date.from(expiresAt))
            .claim("scope", "orders.read")
            .build();

        SignedJWT signed = new SignedJWT(
            new JWSHeader.Builder(JWSAlgorithm.RS256)
                .type(JOSEObjectType.JWT)
                .keyID("test-key")
                .build(),
            claims);

        signed.sign(
            new RSASSASigner(
                (RSAPrivateKey) signingKey.getPrivate()));

        return signed.serialize();
    }

    @Test
    void acceptsSignedTokenWithTrustedKeyAndValidClaims()
            throws Exception {

        String token = signedJwt(
            trusted, ISSUER, AUDIENCE,
            Instant.now().plusSeconds(300));

        Jwt result = decoder.decode(token);

        assertEquals("alice", result.getSubject());
        assertEquals(ISSUER, result.getIssuer().toString());
        assertTrue(result.getAudience().contains(AUDIENCE));
    }

    @Test
    void rejectsValidRs256SignatureFromUntrustedPrivateKey()
            throws Exception {

        KeyPair attacker = newRsaKeyPair();
        String token = signedJwt(
            attacker, ISSUER, AUDIENCE,
            Instant.now().plusSeconds(300));

        assertThrows(JwtException.class,
            () -> decoder.decode(token));
    }

    @Test
    void rejectsWrongIssuerAlthoughSignatureIsValid()
            throws Exception {

        String token = signedJwt(
            trusted, "https://other-issuer.example.test",
            AUDIENCE, Instant.now().plusSeconds(300));

        assertThrows(JwtException.class,
            () -> decoder.decode(token));
    }

    @Test
    void rejectsWrongAudienceAlthoughSignatureIsValid()
            throws Exception {

        String token = signedJwt(
            trusted, ISSUER, "other-api",
            Instant.now().plusSeconds(300));

        assertThrows(JwtException.class,
            () -> decoder.decode(token));
    }

    @Test
    void rejectsExpiredToken() throws Exception {
        String token = signedJwt(
            trusted, ISSUER, AUDIENCE,
            Instant.now().minusSeconds(600));

        // Avoid falling inside default clock-skew (usually 60 s).
        assertThrows(JwtException.class,
            () -> decoder.decode(token));
    }

    @Test
    void rejectsMalformedNonJwtString() {
        assertThrows(JwtException.class,
            () -> decoder.decode("not-a-jwt"));
    }
}
~~~

Run when the project has the Gradle wrapper and aligned dependencies:

~~~bash
./gradlew test --tests "example.RealJwtDecoderTest"
~~~

**Expected result:** six tests pass; there is no reliable fixed stdout because Gradle/JUnit versions and settings affect printed output. Never mark "executed" from merely reading sample code.

### What the tests genuinely prove

- `acceptsSignedToken...`: the decoder verifies RS256 JWS using **the matching public key**, then validates `iss, aud, exp, nbf` per configured validators. `orders.read` permission is not yet tested at a controller.
- `rejectsValidRs256SignatureFromUntrustedPrivateKey`: a properly formatted token signed by a different key is still rejected. It differs from a mock JWT because real signature verification executes.
- `rejectsWrongIssuer...` and `rejectsWrongAudience...`: **a valid signature is not enough**; tokens issued for another OP or API must be rejected.
- `rejectsExpiredToken`: a token expired for several minutes is no longer trusted; clock skew requires an explicit policy.
- `rejectsMalformedNonJwtString`: the decoder must reject non-compact-JWT inputs.
- These tests **do not prove** the real bean configuration uses the right decoder; they do not test JWKS HTTP, key rotation, proxies/TLS, Bearer headers, `scope→SCOPE_...` conversion, or HTTP statuses. An appropriate integration layer is required.

### Additional cases needed depending on threat model

| Input JWT | Expectation |
| --- | --- |
| `alg=none` unsigned | Rejected; disallow anonymous algorithms |
| Algorithm outside allowlist | Rejected |
| `kid` absent from trusted JWKS | Rejected, per cache/refresh policy |
| `nbf` far in the future | Rejected |
| Missing or wrong-type `exp` | Rejected if profile requires it; do not assume every default profile enforces this claim |
| `aud` array not containing API ID | Rejected |
| `iss` lookalike domain differing subtly | Rejected |
| `typ=at+jwt` or specialized profile | Matching type/claims validator, never inferred from signature |
| Oversized claims, huge JWS | Bounded by gateway/server limits, fails safely |
| Revoked token still within `exp` | Local JWT verification does not know revocation automatically; needs denylist/short TTL/introspection/rotation strategy per architecture |
| JWKS rotated/old key removed | Cache-refresh/rollover behavior tested against a test JWKS server |
| Validly signed token yet disabled account | Application must enforce account-state policy if needed, not just the decoder |

**Important warning:** Spring Security provides useful defaults, yet **an audience validator usually needs explicit configuration**. `NimbusJwtDecoder.withPublicKey(...).build()` does not automatically know which audience belongs to your API. The example added `JwtClaimValidator` to separate cryptographic trust from audience authorization.

## 6. Testing JWKS, issuer discovery, and rotation differs from fixed public keys

The example above passes a public key directly into `withPublicKey(...)`. In real systems, the application may use `spring.security.oauth2.resourceserver.jwt.issuer-uri` or `jwk-set-uri`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://issuer.example.test/realms/demo
          # jwk-set-uri if you want to specify the JWKS endpoint explicitly;
          # an issuer validator is still needed when configuring manually.
~~~

This is an illustrative URL only. With `issuer-uri`, Spring Security/the JWT decoder can use metadata discovery to locate `jwks_uri` and select trusted keys. Unlike fixed public key tests, integration tests should spin up a **test OIDC issuer/JWKS server** (e.g., WireMock or a loopback mock HTTP server) and configure the service with that server's issuer URL.

An adequate JWKS test should verify:

1. Metadata endpoint publishes the right `issuer` and `jwks_uri`; the service rejects untrusted issuers.
2. JWT A with `kid=old`, `alg=RS256` signed by private key A; JWKS serves public JWK A; request succeeds.
3. Rollover: JWKS contains A+B, token `kid=new` is signed by B; decoder refresh/cache behavior matches configuration. **Never assume** refresh always happens immediately at one exact instant across all versions/caches.
4. JWKS removes A after the grace window; token A must be rejected once stale cache refreshes or policy window expires.
5. Forged keys or tokens with altered payload retaining old signature are rejected.
6. JWKS 500/timeout/TLS failure: fails closed, logs operational error, never bypasses signature checks.
7. Unusual `kid` headers and token-supplied `jku`/`x5u` must never automatically point the decoder to arbitrary hosts: prevents SSRF/trust-source hijacking.
8. Design an algorithm allowlist so token-header algorithm substitution cannot break the trust model.

**Do not configure a test by replacing the real decoder with `@MockBean JwtDecoder`**, and then call it a key-rotation test. If discovery/key caching is the target, the test must pass through the real decoder and real HTTP JWKS client (even if the remote server is test-controlled).

### "Real" has multiple levels

- **Real signature/local decoder**: real RSA verification without networking.
- **Real decoder + mock HTTP JWKS server**: real HTTP fetch/cache/discovery logic against a fixture server.
- **Real integration staging IdP**: protocol against a real issuer in a test environment; requires safe credentials/secrets and non-flaky tests.
- **Real production-like end-to-end**: service, gateway, TLS, claim policies, auth server, caching, retries, and security controls aligned, at higher cost.

Just because one layer does not cover everything does not make it useless. What matters is **labeling the evidence accurately**.

## 7. JUnit 5: running SpringOpaqueTokenIntrospector with a controlled HTTP client

An opaque token normally cannot be decoded locally; the service must send it to the authorization server's introspection endpoint with the resource server's credentials. A mock `OpaqueTokenIntrospector` merely returns a canned principal and skips checking POST/form/`active`. Below is a **component test with the real introspector** and a real `RestTemplate` whose HTTP responses are supplied by `MockRestServiceServer`; **no external IdP is called over the network**. It tests interactions at the HTTP client boundary.

Create `src/test/java/example/OpaqueIntrospectionHttpTest.java`:

~~~java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.support.BasicAuthenticationInterceptor;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.SpringOpaqueTokenIntrospector;
import org.springframework.test.web.client.MockRestServiceServer;
import org.springframework.web.client.RestTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import static org.springframework.test.web.client.match.MockRestRequestMatchers.method;
import static org.springframework.test.web.client.match.MockRestRequestMatchers.requestTo;
import static org.springframework.test.web.client.response.MockRestResponseCreators.withSuccess;

class OpaqueIntrospectionHttpTest {

    private static final String ENDPOINT =
        "https://idp.example.test/oauth2/introspect";

    private static RestTemplate testRestTemplate() {
        RestTemplate rest = new RestTemplate();

        // Fake secret for tests only. Production uses a secret store.
        rest.getInterceptors().add(
            new BasicAuthenticationInterceptor(
                "test-client", "test-secret"));
        return rest;
    }

    @Test
    void activeTokenIsResolvedThroughIntrospectionHttpClient() {
        RestTemplate rest = testRestTemplate();
        MockRestServiceServer http =
            MockRestServiceServer.bindTo(rest).build();

        http.expect(requestTo(ENDPOINT))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess(
                "{\"active\":true,"
                + "\"sub\":\"alice\","
                + "\"scope\":\"orders.read\"}",
                MediaType.APPLICATION_JSON));

        var introspector =
            new SpringOpaqueTokenIntrospector(ENDPOINT, rest);

        var principal = introspector.introspect("opaque-valid");

        assertEquals("alice", principal.getName());
        assertTrue(principal.getAuthorities().stream().anyMatch(
            authority -> "SCOPE_orders.read".equals(
                authority.getAuthority())));
        http.verify();
    }

    @Test
    void inactiveTokenIsRejectedByRealIntrospectorLogic() {
        RestTemplate rest = testRestTemplate();
        MockRestServiceServer http =
            MockRestServiceServer.bindTo(rest).build();

        http.expect(requestTo(ENDPOINT))
            .andExpect(method(HttpMethod.POST))
            .andRespond(withSuccess(
                "{\"active\":false}",
                MediaType.APPLICATION_JSON));

        var introspector =
            new SpringOpaqueTokenIntrospector(ENDPOINT, rest);

        assertThrows(BadOpaqueTokenException.class,
            () -> introspector.introspect("opaque-revoked"));
        http.verify();
    }
}
~~~

Run:

~~~bash
./gradlew test --tests "example.OpaqueIntrospectionHttpTest"
~~~

**Expected result:** both tests pass if dependencies/APIs align. `MockRestServiceServer` intercepts `RestTemplate` requests with a mocked HTTP client, so it checks method/url/response parsing/`active` yet **does not prove real TLS connectivity to the IdP, client authorization, timeouts, or live revocation**.

### Adding assertions so the security contract is not dropped

In real tests, verify the exact HTTP request:

- `Content-Type: application/x-www-form-urlencoded` and the `token` parameter properly encoded, without logging raw tokens. Use `MockRestRequestMatchers.content()` to verify the request body.
- `Authorization: Basic ...` or whichever client authentication method the IdP supports, per configuration/secret store. In the example, the interceptor adds Basic auth to the HTTP client yet **the header is not asserted**; add that assertion when testing protocol specifics.
- `active=false` is rejected, rather than creating a principal with an empty scope list.
- IdP errors (4xx/5xx), malformed responses, expiration, and timeouts must **fail closed** and return appropriate errors, never masquerading as valid tokens.
- An `active=true` response carrying `iss`, `aud`, `client_id`, `sub`, `scope` must be cross-checked against resource server policies if returned by the authorization server and required by the app. Introspection only states the server believes the token is active; it does not check all business constraints automatically.
- Evaluate introspection caching: caching `active=true` responses too long can delay revocation. Test TTL/invalidation and outage behavior.

**Never claim "real introspection with the IdP" when using only `MockRestServiceServer`.** This is an internal test of the client/introspector against simulated HTTP; staging/live tests require separately managed credentials, endpoints, and policies.

## 8. HTTP integration: sending a real Bearer token through the filter chain

### 8.1. Avoiding bypassing the decoder with a post-processor

To test end-to-end in a **Spring Security Servlet application** with a `SecurityFilterChain`:

~~~java
@Bean
SecurityFilterChain apiSecurity(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated())
        .oauth2ResourceServer(oauth -> oauth.jwt(
            org.springframework.security.config.Customizer.withDefaults()))
        .build();
}
~~~

The config above is a snippet only; a `@Configuration` class, a real `JwtDecoder` bean, and a real controller are required. In Spring Security 6.x, `oauth2ResourceServer(oauth -> oauth.jwt(Customizer.withDefaults()))` enables JWT authentication. Requests under `/api/orders/**` require the scope even when the JWT is validly signed.

### 8.2. Tests must send the token string, not inject Authentication

~~~java
// Inside @SpringBootTest + @AutoConfigureMockMvc,
// with a real JwtDecoder and /api/orders/42 endpoint configured.

mvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer " + signedJwt))
   .andExpect(status().isOk());

mvc.perform(get("/api/orders/42")
        .header("Authorization", "Bearer " + wrongKeySignedJwt))
   .andExpect(status().isUnauthorized())
   .andExpect(header().string(
       "WWW-Authenticate",
       org.hamcrest.Matchers.startsWith("Bearer")));
~~~

The snippet assumes `signedJwt`/`wrongKeySignedJwt` are created by a helper like section 5 and the endpoint has matching permissions. Never attach `.with(jwt())` to these requests, because doing so injects a fake Authentication and can stop the test from proving the decoder path.

- Verify **401 + `WWW-Authenticate: Bearer`** when no valid Bearer token is present (challenge details per RFC 6750); Spring Security may use the `invalid_token` code.
- Verify **403** when the JWT signature/claims are valid yet `SCOPE_orders.read` is missing; 403 is **authorization**, not a signature failure.
- Verify 200 when the token is valid and has sufficient scope.
- Verify the endpoint leaks no exceptions, meets the public error contract, and sets cache headers when needed.
- Verify the real profile has a properly configured `JwtDecoder` bean, not accidentally replaced by `@MockBean`, `@SpyBean`, or test-profile overrides.
- If using servlet `oauth2Login()`/ID tokens, test Authorization Code, state/nonce, redirect URI, and ID tokens with a dedicated test IdP; **never** treat Resource Server JWT access token tests as covering OIDC login.

**Boundary:** `MockMvc` executes the servlet filter chain and controller in a mock servlet environment when configured properly, yet is not a real socket/TLS/network test. Environments with reverse proxies, forwarded headers, gateways, and OAuth IdPs still need separate testing.

### 8.3. Opaque token integration

Replace `.oauth2ResourceServer(oauth -> oauth.jwt(...))` with `opaqueToken(...)` on the chain per version/DSL, providing a real `OpaqueTokenIntrospector` and HTTP test endpoint. Send a real `Authorization: Bearer opaque-valid`, testing 200 for `active=true` with required scope; send an `active=false` token for 401; `active=true` missing scope for 403. Never use `.with(opaqueToken())` in tests meant to prove the introspection path.

### 8.4. Reactive equivalent

With WebFlux, the resource server uses `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector`. Integration tests pass the Bearer header into `WebTestClient` and use a real reactive decoder/introspector, not `mutateWith(mockJwt())`/`mockOpaqueToken()`. Spring Security Test supports both mock configurers, yet they do not replace verifying crypto/protocol behavior.

## 9. Pure Java 17: seeing the difference between signatures and self-declared data

This example uses no JWT library: it uses **JCA RSA/SHA-256** to illustrate that "having an object containing claims" is completely different from "data signed by the holder of a trusted private key". This is purely **standalone** message signing, not JWT/JWS, lacking issuer/audience/expiry, and must never replace `NimbusJwtDecoder` in production.

Create `SignatureTrustBoundaryDemo.java`:

~~~java
import java.nio.charset.StandardCharsets;
import java.security.GeneralSecurityException;
import java.security.KeyPair;
import java.security.KeyPairGenerator;
import java.security.PrivateKey;
import java.security.PublicKey;
import java.security.Signature;

public class SignatureTrustBoundaryDemo {

    private static byte[] sign(
            PrivateKey key, byte[] bytes)
            throws GeneralSecurityException {

        Signature signer = Signature.getInstance("SHA256withRSA");
        signer.initSign(key);
        signer.update(bytes);
        return signer.sign();
    }

    private static boolean verify(
            PublicKey key, byte[] bytes, byte[] signature)
            throws GeneralSecurityException {

        Signature verifier = Signature.getInstance("SHA256withRSA");
        verifier.initVerify(key);
        verifier.update(bytes);
        return verifier.verify(signature);
    }

    public static void main(String[] args)
            throws GeneralSecurityException {

        KeyPairGenerator generator =
            KeyPairGenerator.getInstance("RSA");
        generator.initialize(2048);

        KeyPair trusted = generator.generateKeyPair();
        KeyPair untrusted = generator.generateKeyPair();

        byte[] original = "sub=alice;scope=orders.read"
            .getBytes(StandardCharsets.UTF_8);
        byte[] tampered = "sub=alice;scope=orders.admin"
            .getBytes(StandardCharsets.UTF_8);

        byte[] signature = sign(trusted.getPrivate(), original);

        System.out.println("valid="
            + verify(trusted.getPublic(), original, signature));
        System.out.println("tampered="
            + verify(trusted.getPublic(), tampered, signature));
        System.out.println("wrongKey="
            + verify(untrusted.getPublic(), original, signature));
    }
}
~~~

Compile/run with JDK 17+:

~~~bash
javac SignatureTrustBoundaryDemo.java
java SignatureTrustBoundaryDemo
~~~

Logically deterministic stdout even though RSA keys are generated randomly:

~~~text
valid=true
tampered=false
wrongKey=false
~~~

Takeaway from the demo: the server **needs a trusted public key** and verifies the exact signed bytes. If a test merely builds an `Authentication` object with `ROLE_ADMIN`, no signing/verification occurs, so it cannot detect tampering or keys outside the trust set.

**Do not confuse the RSA example with JWT**: JWT/JWS also has `alg/kid` headers, a canonical wire format, time-based claims, issuer/audience, and policy validation. `NimbusJwtDecoder` is where a standard library is used to verify those factors.

## 10. Minimum testing matrix

| What to prove | Token/fixture | Test level | Expected |
| --- | --- | --- | --- |
| Controller reads `SCOPE_orders.read` role | `jwt().authorities(...)` | MockMvc | 200, if endpoint matches |
| Controller rejects user missing scope | `jwt()` without required authority | MockMvc | 403 |
| WebFlux security context already has JWT | `mockJwt()` | WebTestClient | Business rule/authorization passes |
| Valid RS256 signature | Private key A signs, public key A decoder | Decoder unit | Valid `Jwt` |
| Key B signature | Private key B, public key A decoder | Decoder unit | `JwtException` |
| Wrong `iss` | JWT signed by A, another issuer's `iss` | Decoder unit | `JwtException` |
| Wrong `aud` | JWT signed by A, another API's `aud` | Decoder unit | `JwtException` |
| Expired | Properly signed JWT, `exp` minutes in the past | Decoder unit | `JwtException` |
| JWKS rollover | issuer + mock JWKS server, keys A/B | Decoder integration | Accepted/rejected per trust/cache policy |
| Opaque active | HTTP introspection `active=true` | Introspector component | Valid principal |
| Opaque inactive | HTTP introspection `active=false` | Introspector component | Rejected |
| IdP 5xx/timeout | HTTP mock timeout/5xx | Introspector component | Fail closed + operationally visible error |
| Missing Bearer | No `Authorization` header | Security filter integration | 401 + challenge |
| Valid JWT yet missing scope | Real signed Bearer JWT, insufficient policy | Security filter integration | 403 |
| Invalid JWT | Bearer JWT wrong signature | Security filter integration | 401 |
| Well-formed opaque yet inactive | Bearer string through filter, HTTP introspection false | Security filter integration | 401 |
| Local user disabled | Cryptographically valid token, account check policy | Domain integration | Denied per policy |
| Revoked JWT still within `exp` | Local offline JWT decoder | Architecture test | **May remain valid** without revocation mechanism |
| OAuth login callback | Test OIDC OP with code/state/nonce/signature | OIDC login e2e | Only verified flows accepted |

### Assertion guidelines

- Do not assert only "401" while ignoring `WWW-Authenticate`; HTTP Bearer challenges carry specific semantics.
- Never assert exception substrings containing secrets/issuer hosts and return them in response bodies; operational logs must redact.
- Never write an invalid-signature JWT test with `Jwt.withTokenValue("fake")...build()`: that is a `Jwt` object, not signed JWS bytes.
- Never use real production refresh tokens or client secrets in CI. Generate test keys/tokens in memory and isolate test IdPs.
- Avoid negative-only tests: without real positive tests, you will not notice a decoder misconfigured to "deny all".
- Avoid positive-only tests: a valid signature does not verify issuer/audience/time/revocation policies.
- With virtual time/clock skew, time tests need safe margins; integration expiry near the boundary can flake.
- Assert that the decoder/introspector **was genuinely invoked** when claiming boundary coverage; use spies/counters where helpful, though spies do not replace cryptographic checks.
- If benchmarking introspection performance, separate performance/load tests from unit tests and test timeouts/backoff/rate limits.

## 11. Common misconceptions and fixes

1. **"`jwt()` tests signatures"** → False. It pre-populates a `Jwt` Authentication for controller/filter authorization.
2. **"Test has `alg=RS256` in claims so real keys are checked"** → False. Constructing header/claim objects performs no cryptographic verification.
3. **"Mocking `JwtDecoder.decode` to return `Jwt` is a real decoder test"** → False. Mockito fakes the outcome; use it only to test wiring/error mapping.
4. **"`opaqueToken()` tests HTTP introspection requests"** → False. It creates a mock principal without network calls.
5. **"A JWT-shaped token must be verified offline"** → False. The authorization server may require introspection even when a token looks like a JWT.
6. **"If a JWT's signature is right, every API must accept it"** → False. `aud`, `iss`, `exp`, `nbf`, type, and policies must all be checked.
7. **"A client-supplied access token with `scope=admin` is trustworthy"** → False. Never rely on unverified claims in controllers.
8. **"No need to test 401/403 because StepVerifier/decoder passes"** → False. HTTP filters/challenges are a separate layer.
9. **"Introspection returned `active=false` yet included `sub`, so it can pass"** → False. Inactive must be rejected.
10. **"When JWKS rotates, the decoder will definitely refresh immediately"** → False. Caching/refresh depends on implementation, config, and timing; test per policy.
11. **"A JWT revoked at the IdP is immediately blocked by an offline decoder"** → False. Offline signature validation does not automatically call a revocation service.
12. **"Skipping TLS verification in staging tests is more convenient"** → Never do this. It hides real trust errors and risks being copied into production.
13. **"Every E2E test should hit the live production IdP"** → No. Use local mock servers/test IdPs and controlled staging; avoid quotas, PII, and impacting real accounts.
14. **"Testing only a correct signature is enough"** → False. You need invalid claims, wrong audience/issuer, alg allowlists, key mismatches, and expiry.
15. **"A verified bearer token means the user is still ACTIVE"** → Not necessarily. Check account status/domain policies at the appropriate layer.

## 12. Checklist before considering authentication testing complete

- [ ] Authorization tests (mocked principals) are separated from JWT decoder/introspection tests.
- [ ] Real positive/negative tests exist for RSA signatures, key mismatches, issuer, audience, exp/nbf, and algorithm policy.
- [ ] JWKS discovery/rotation/caching/timeout tests exist if dynamic keys are used.
- [ ] Introspection client tests cover POST/form/auth/`active`/scopes and fail-closed network errors.
- [ ] HTTP filter chain tests send **raw Bearer credentials** in headers rather than injecting `JwtAuthenticationToken`.
- [ ] 401/403 and `WWW-Authenticate` are asserted per RFC 6750 semantics.
- [ ] OIDC `oauth2Login` is tested separately when using login federation; access tokens do not substitute for ID tokens.
- [ ] Test configs do not replace real `JwtDecoder`/`OpaqueTokenIntrospector` with mocks in integration layers unintentionally.
- [ ] Test keys/tokens/credentials are fake, with no production secrets or secret logging.
- [ ] Test names reflect actual evidence: authorization/mock, decoder/crypto, HTTP introspection, provider e2e.
- [ ] Monitoring captures `invalid_token`, issuer mismatch, and JWKS timeout errors without exposing exception details in public responses.
- [ ] Tests run reliably in CI and staging, avoiding uncontrolled live IdP dependencies on every commit.

**Summary:** using `jwt()`, `mockJwt()`, `opaqueToken()`, or `mockOpaqueToken()` to test **authorization once a principal exists** is very helpful, yet they **do not verify raw credentials**. To know JWTs are genuinely protected, pass genuinely signed compact tokens through `NimbusJwtDecoder`/the filter chain with explicit validators; to know opaque tokens are trusted properly, run `SpringOpaqueTokenIntrospector` with verified HTTP responses and `active` checks. Combine layers instead of reading too much into a single green test.

## 13. Official references

- Spring Security 6.5 — Testing OAuth2 in MockMvc: https://docs.spring.io/spring-security/reference/6.5/servlet/test/mockmvc/oauth2.html
- Spring Security 6.5 — Testing OAuth2 in WebTestClient: https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html
- Spring Security 6.5 — JWT Resource Server, signatures, validators, JWK: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html
- Spring Security 6.5 — Opaque Token Resource Server: https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html
- Spring Security 6.5 API — `NimbusJwtDecoder`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html
- Spring Security 6.5 API — `SpringOpaqueTokenIntrospector`: https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/oauth2/server/resource/introspection/SpringOpaqueTokenIntrospector.html
- RFC 7515 — JSON Web Signature: https://www.rfc-editor.org/rfc/rfc7515.html
- RFC 7662 — OAuth 2.0 Token Introspection: https://www.rfc-editor.org/rfc/rfc7662.html
- RFC 6750 — Bearer Token Usage: https://www.rfc-editor.org/rfc/rfc6750.html
- RFC 8725 — JWT Best Current Practices: https://www.rfc-editor.org/rfc/rfc8725.html
