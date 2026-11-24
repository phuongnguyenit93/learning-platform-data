# Mocking JWK Endpoints, Introspection Endpoints, and Identity Provider Failures

> **Scope:** advanced testing of a **Spring Security WebFlux Resource Server** accepting Bearer tokens, where authentication relies on a JWK Set (JWT) or OAuth 2.0 Token Introspection (opaque token). The goal is to test both HTTP communication with the Identity Provider (IdP) and security behavior when the IdP responds with errors, rather than only simulating logged-in users.

## 1. Learning objectives and boundaries

After this lesson, you will be able to:

1. Distinguish **authorization** tests using `mockJwt()` / `mockOpaqueToken()` from **real authentication** tests using signed JWTs, HTTP JWK Sets, and HTTP introspection.
2. Spin up a stub IdP on a random port, publish JWK public keys, respond to introspection calls, and inspect incoming requests from the Resource Server.
3. Test valid JWTs, bad signatures, mismatched `kid`, invalid issuer/audience/expiration, and key rotation scenarios.
4. Test opaque tokens with `active=true/false`, scopes, client authentication, and 401/429/5xx/timeout errors from the introspection endpoint.
5. Prove the system **fails closed**: authentication errors or inability to verify a token must never expose resources; distinguish token errors from infrastructure outages and keep causes observable.

**Version note:** Java 17+ examples use JUnit 5, Reactor Test, `MockWebServer` 4.x, and Spring Security 6.5 Reactive APIs. For Spring Security 7, cross-check API signatures when upgrading. This lesson is about a WebFlux *Resource Server*, not OAuth2 Login or Servlet `HttpSecurity`.

## 2. Underlying mechanisms

### 2.1. JWT and JWK Set

A JWT is signed with a private key and carries headers such as `{"alg":"RS256","kid":"key-a"}` and claims such as `iss`, `sub`, `aud`, `exp`, `nbf`, `scope`. The Resource Server downloads the **JWK Set** (JWKS) containing **public** keys from the IdP endpoint, selects a key by `kid`/algorithm, and verifies the signature locally. Abbreviated example response:

```json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "key-a",
      "alg": "RS256",
      "n": "<modulus-base64url>",
      "e": "AQAB"
    }
  ]
}
```

`n` and `e` here are illustrative placeholders, **not a runnable valid JWK**. Real tests must generate an RSA key pair, sign tokens with the private key, and publish only the public JWK. Never include `d`, `p`, `q`, or a private JWK in an HTTP response.

Flow:

```text
Client -- Authorization: Bearer <signed-JWT> --> WebFlux Resource Server
                  |                                |
                  |                       ReactiveJwtDecoder
                  |                                |
                  |                        GET /jwks (when needed)
                  |                                v
                  |                         Mock IdP
                  |                        200 { "keys": [...] }
                  |                                |
                  +--> verify signature, alg, exp, nbf, iss, aud per config
                                                   |
                                        Authentication + authorities
                                                   |
                                         SecurityWebFilterChain
```

Common points of confusion:

- `jwk-set-uri` only tells Spring where to fetch keys; if you build `NimbusReactiveJwtDecoder` manually via builder, configure the required `iss`/`aud` validators. Never assume a valid signature alone is enough.
- Setting both `issuer-uri` and `jwk-set-uri` in Spring Boot config specifies JWKS directly while still validating `iss` via standard configuration.
- JWK Sets may be cached; whether the endpoint is called again depends on caching, version, and key selection. Never assume "every request runs GET /jwks".
- A JWT with a valid signature can still be rejected due to `exp`, `nbf`, `iss`, `aud`, or missing scope. Authentication checks and authorization checks are distinct verifications.

### 2.2. Opaque tokens and introspection

Opaque tokens generally do not carry self-verifiable information for the Resource Server. Whenever verification is needed (unless the app explicitly adds caching), `ReactiveOpaqueTokenIntrospector` sends an HTTP POST to the IdP per RFC 7662, typically using HTTP Basic authentication for the client:

```http
POST /introspect HTTP/1.1
Authorization: Basic <base64(client-id:client-secret)>
Content-Type: application/x-www-form-urlencoded

token=opaque-123
```

Successful active response:

```json
{
  "active": true,
  "sub": "alice",
  "scope": "lesson:read",
  "client_id": "resource-server-client",
  "token_type": "Bearer"
}
```

Expired or revoked token:

```json
{"active": false}
```

`active=false` differs from an IdP outage: the former is a valid authentication verdict; the latter means **verification could not be completed**. By default, scope `lesson:read` typically maps to authority `SCOPE_lesson:read`. Never assume HTTP 200 means "valid token" when the body says `active=false`.

### 2.3. Choosing the right test layer

| Layer | Approach | What is proven | What is NOT yet proven |
| --- | --- | --- | --- |
| Fast authorization | `WebTestClient.mutateWith(mockJwt())` or `mockOpaqueToken()` | `hasAuthority`, `hasRole` rules, principal mapping, 403 on missing permission | HTTP JWKS/introspection, signatures, parsers, credentials, timeouts |
| Adapter contract | `MockWebServer` + real decoder/introspector + `StepVerifier` | How Spring sends requests, parses responses, accepts/rejects tokens, handles upstream errors | Every filter/controller in the app |
| WebFlux integration | `@SpringBootTest` + `WebTestClient` + stub IdP | HTTP 401/403/2xx, `SecurityWebFilterChain`, property binding, fail-closed behavior | 100% compatibility with real IdP |
| Environment compatibility | Real IdP in staging/Testcontainers if available | Provider-specific contract, TLS, metadata, real policies | Unsuitable as the base for every unit test |

`mockJwt()` and `mockOpaqueToken()` are very useful, but they bypass network token verification. Use them for authorization; for **mocking IdP endpoints**, include at least one test that passes through the real decoder/introspector.

## 3. Setting up the test environment

With Gradle Groovy DSL in a Spring Boot project with dependency management, typical dependencies:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'io.projectreactor:reactor-test'
    testImplementation 'com.squareup.okhttp3:mockwebserver:4.12.0'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`spring-boot-starter-oauth2-resource-server` provides Bearer and JWT authentication components, including JOSE support; `spring-boot-starter-webflux` provides the reactive runtime. Never hardcode real environment URLs or client secrets in tests. `MockWebServer` is an in-process HTTP stub that picks an ephemeral free port: no external Keycloak or IdP is needed.

Application config in **JWT mode** when using Spring Boot auto-configuration:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.test/realm
          jwk-set-uri: http://127.0.0.1:${JWK_STUB_PORT}/jwks
```

Application config in **opaque mode** in a separate test profile/context:

```yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: http://127.0.0.1:${INTROSPECTION_STUB_PORT}/introspect
          client-id: resource-server-client
          client-secret: test-secret
```

Placeholders `${JWK_STUB_PORT}` and `${INTROSPECTION_STUB_PORT}` only illustrate supplying dynamic URLs; the YAML snippets cannot run standalone without supplying variables. In integration tests, use `@DynamicPropertySource` to inject `server.url(...).toString()` into the Spring context **before context creation**. When testing both token types, split test contexts explicitly between `.jwt()` and `.opaqueToken()`; never assume both activate equally just because both property blocks are present.

## 4. Complete JUnit example: mocking JWK and introspection over real HTTP

Create `src/test/java/example/security/IdpEndpointContractTest.java`. This example runs standalone as a JUnit class inside a project with the dependencies above; it tests real reactive components without depending on project-specific controllers.

```java
package example.security;

import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusReactiveJwtDecoder;
import org.springframework.security.oauth2.server.resource.introspection.SpringReactiveOpaqueTokenIntrospector;
import reactor.test.StepVerifier;

import java.io.IOException;
import java.time.Instant;
import java.util.Date;
import java.util.concurrent.TimeUnit;

import static org.junit.jupiter.api.Assertions.*;

class IdpEndpointContractTest {
    private MockWebServer idp;

    @BeforeEach
    void startIdp() throws IOException {
        idp = new MockWebServer();
        idp.start();
    }

    @AfterEach
    void stopIdp() throws IOException {
        idp.shutdown();
    }

    @Test
    void jwtDecoderFetchesJwkAndValidatesSignatureAndIssuer() throws Exception {
        RSAKey key = new RSAKeyGenerator(2048)
                .keyID("key-a")
                .keyUse(KeyUse.SIGNATURE)
                .generate();

        // HTTP publishes only the public key; private key is used only for signing.
        String publicJwks = new JWKSet(key.toPublicJWK()).toString();
        idp.enqueue(json(200, publicJwks));

        NimbusReactiveJwtDecoder decoder = NimbusReactiveJwtDecoder
                .withJwkSetUri(idp.url("/jwks").toString())
                .build();
        decoder.setJwtValidator(
                JwtValidators.createDefaultWithIssuer("https://idp.test/realm"));

        Instant now = Instant.now();
        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer("https://idp.test/realm")
                .subject("alice")
                .issueTime(Date.from(now.minusSeconds(5)))
                .expirationTime(Date.from(now.plusSeconds(300)))
                .build();

        SignedJWT signed = new SignedJWT(
                new JWSHeader.Builder(JWSAlgorithm.RS256)
                        .keyID("key-a")
                        .build(),
                claims);
        signed.sign(new RSASSASigner(key));

        StepVerifier.create(decoder.decode(signed.serialize()))
                .assertNext(jwt -> assertEquals("alice", jwt.getSubject()))
                .verifyComplete();

        RecordedRequest request = idp.takeRequest(2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertEquals("GET", request.getMethod());
        assertEquals("/jwks", request.getPath());
    }

    @Test
    void introspectionSendsFormAndBasicAuthThenRejectsInactiveToken()
            throws Exception {
        var introspector = SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(idp.url("/introspect").toString())
                .clientId("sample-client")
                .clientSecret("sample-secret")
                .build();

        idp.enqueue(json(200,
                "{\"active\":true,\"sub\":\"alice\",\"scope\":\"lesson:read\"}"));

        StepVerifier.create(introspector.introspect("opaque-123"))
                .assertNext(principal -> {
                    assertEquals("alice", principal.getAttribute("sub"));
                    assertTrue(principal.getAuthorities().stream()
                            .anyMatch(a ->
                                    a.getAuthority().equals("SCOPE_lesson:read")));
                })
                .verifyComplete();

        RecordedRequest request = idp.takeRequest(2, TimeUnit.SECONDS);
        assertNotNull(request);
        assertEquals("POST", request.getMethod());
        assertEquals("/introspect", request.getPath());
        assertTrue(request.getHeader("Authorization").startsWith("Basic "));
        assertTrue(request.getBody().readUtf8().contains("token=opaque-123"));

        idp.enqueue(json(200, "{\"active\":false}"));

        StepVerifier.create(introspector.introspect("revoked-token"))
                .expectError()
                .verify();
    }

    @Test
    void unavailableIdpNeverCountsAsSuccessfulIntrospection() {
        var introspector = SpringReactiveOpaqueTokenIntrospector
                .withIntrospectionUri(idp.url("/introspect").toString())
                .clientId("sample-client")
                .clientSecret("sample-secret")
                .build();

        idp.enqueue(json(503, "{\"error\":\"temporarily_unavailable\"}"));

        StepVerifier.create(introspector.introspect("opaque-123"))
                .expectError()
                .verify();
    }

    private static MockResponse json(int status, String body) {
        return new MockResponse()
                .setResponseCode(status)
                .addHeader("Content-Type", "application/json")
                .setBody(body);
    }
}
```

Run just this class with the project's Gradle wrapper:

```bash
./gradlew test --tests 'example.security.IdpEndpointContractTest'
```

On Windows PowerShell, use `.\gradlew.bat test --tests 'example.security.IdpEndpointContractTest'`.

**Expected results:** three **PASS**ing tests. The JWK test proves HTTP GET was called and the valid public key decodes the JWT signed with the matching private key. The introspection test proves HTTP POST form submission, Basic auth, authorities from scope, and rejection of `active=false`. The 503 test proves upstream errors do not turn into an authenticated principal. There is no fixed stdout; PASS/FAIL reporting belongs to JUnit/Gradle and depends on actual execution.

**Why do the tests use `StepVerifier`?** `decode()` and `introspect()` return `Mono` publishers. Tests must actually subscribe and distinguish `onNext/onComplete` from `onError`. Creating a `Mono` without subscribing executes no HTTP request; calling `.block()` in production WebFlux handlers is wrong because it can block the event loop, whereas using `StepVerifier` in tests is appropriate.

## 5. Extending to end-to-end WebFlux HTTP tests

A real application may protect an API as follows:

```java
@Bean
SecurityWebFilterChain apiSecurity(ServerHttpSecurity http) {
    return http
            .authorizeExchange(exchanges -> exchanges
                    .pathMatchers("/api/lessons/**")
                    .hasAuthority("SCOPE_lesson:read")
                    .anyExchange().authenticated())
            .oauth2ResourceServer(oauth -> oauth.jwt(
                    org.springframework.security.config.Customizer.withDefaults()))
            .build();
}
```

The above is a **configuration fragment** to place inside a `@Configuration` class; to test opaque tokens, replace `.jwt(...)` with `.opaqueToken(Customizer.withDefaults())` in a separate context. With `@SpringBootTest(webEnvironment = RANDOM_PORT)` and `@AutoConfigureWebTestClient`, send a real signed JWT with `WebTestClient`:

```java
// Illustrates a test body; signedJwt must be generated from a test fixture.
webTestClient.get()
        .uri("/api/lessons/42")
        .headers(headers -> headers.setBearerAuth(signedJwt))
        .exchange()
        .expectStatus().isOk();
```

The application must expose route `/api/lessons/42`; this snippet **is not a standalone runnable class**. Things to verify:

1. A properly signed JWT with valid claims and `SCOPE_lesson:read` → 2xx response per API contract.
2. A valid JWT missing the required scope → HTTP 403 (authenticated, insufficient permission).
3. An expired/bad-signature/wrong-issuer JWT → HTTP 401 when using the default bearer authentication entry point.
4. An opaque token with `active=false` → HTTP 401.
5. IdP HTTP 5xx, connection reset, or timeout → no request may be treated as authenticated; the specific status may be 401 or 5xx depending on exception translation and configured handlers. Lock down your application's response policy and assert the **actual observed status and error body**, rather than guessing blindly from a component test.

Start the stub IdP before the Spring context reads `@DynamicPropertySource`, and shut it down after the test context completes. Using random ports avoids CI collisions. When testing authorization alone without remote verification, you can use `SecurityMockServerConfigurers.mockJwt()`/`mockOpaqueToken()` with a Spring Security-integrated `WebTestClient`; in that mode, you **cannot** use JWK/introspection request counts as evidence.

## 6. Matrix of scenarios to test

### 6.1. JWK endpoint and JWT

| Scenario | Stub or input token | Result to prove |
| --- | --- | --- |
| Success | JWKS 200 with RSA public key `kid=key-a`, RS256 JWT signed by matching private key | `decode()` returns `Jwt`; claims and authorities verified properly |
| Tampered signature | Keep old signature and alter payload, or sign with a key absent from published JWKS | `decode()` emits `onError`; API grants no access |
| `kid` not found | Header `kid=key-b`, JWKS contains only `key-a` | Token rejected; JWK refresh may occur depending on cache |
| Untrusted algorithm | JWT uses an algorithm outside the allowlist, e.g. disallowed `HS256` | Rejected; never trust `alg` merely because it appears in the header |
| Time claims | `exp` in past, `nbf` in future, including clock skew | Rejected per configured validator and clock skew |
| Origin/target claims | `iss` differs from trusted issuer, or `aud` lacks expected API | Rejected when matching validators exist; remember to declare the audience validator |
| Broken JWKS | HTTP 200 with invalid JSON, missing `keys`, malformed RSA modulus | Decode/JWK error; not authenticated |
| IdP unavailable | 500/503, disconnect, DNS failure, timeout | No bypass path granting access; error category recorded |
| Key rotation | JWKS transitions from `key-a` to `key-b`; JWT carries `kid=key-b` | Test with controlled cache/decoder to confirm refresh and new token acceptance |
| Multiple keys | JWKS contains `key-a` and `key-b` | Correct `kid`, `kty`, `use`, `alg`; tokens signed with wrong key rejected |

**Rotation has caching traps:** never write a test asserting "GET /jwks must be called exactly twice". To prove refresh, use a fresh decoder/context or a controllable cache mechanism, issue a JWT with the new `kid`, and assert both the outcome and the actually recorded requests. Never disable signature verification to make rotation easier to test.

**Audience:** `aud` is not automatically validated solely from a JWKS URI. In Spring Boot, you can configure `spring.security.oauth2.resourceserver.jwt.audiences` if your version supports it; with a manually constructed decoder, add an `OAuth2TokenValidator<Jwt>` for audience and combine it with default/issuer validators.

### 6.2. Introspection endpoint and opaque tokens

| Scenario | Simulated response | What to check |
| --- | --- | --- |
| Active token | `200 {"active":true,"sub":"alice","scope":"lesson:read"}` | Correct principal and authorities |
| Revoked token | `200 {"active":false}` | Authentication rejected |
| Missing access permission | `active=true` but missing scope | Authentication may succeed; protected API returns 403 |
| Bad client credentials | `401` or `403` from introspection | Handled as credential/IdP error, never treated as active token |
| Rate limited | `429` and possibly `Retry-After` | No bypass; verify bounded timeout/retry |
| Server error | `500`, `502`, `503` | Authentication does not succeed; error classified/observed |
| Malformed response schema | Invalid JSON, missing `active`, wrong field type, wrong content type | Never silently treat token as valid |
| Slow network | Stub delay exceeding configured threshold | Completes via bounded timeout; test does not hang indefinitely |
| Credentials/encoding | Stub records `Authorization`, form `token`, and `Content-Type` | Proper POST format, Basic auth uses test secret; avoid logging secrets |
| Special characters in token | e.g., token containing `+`, `/`, `=` | Proper URL-encoded form data; IdP receives literal token |

A 401 response **from the IdP** is not the same as a 401 **from your API**: those are two separate HTTP hops and may be mapped differently. Observe the exception at the introspector, then assert the status on `WebTestClient` separately. Avoid `onErrorReturn(principalAdmin)` or a default "allow on error" cache, which creates a fail-open vulnerability.

## 7. Actively simulating identity provider failures

Three categories to distinguish:

1. **Invalid/revoked token:** the IdP is healthy and concludes the token is invalid; your software reports authentication failure.
2. **IdP/transport failure:** 5xx, HTTP 429, DNS/TLS, connection reset, timeout; the Resource Server cannot complete verification. Must block access and emit classified logs/metrics without leaking tokens or credentials.
3. **Configuration/protocol failure:** wrong `issuer-uri`, malformed JWKS, missing public key, wrong mTLS/client secret, bad JSON schema; must surface clearly to operations rather than "self-healing" by dropping validators.

Use `MockWebServer.enqueue()` to queue responses sequentially, or WireMock mappings by URL/method/body when multiple routes exist. Example with `MockWebServer` (insert into a test method body):

```java
idp.enqueue(new MockResponse()
        .setResponseCode(503)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"error\":\"temporarily_unavailable\"}"));

idp.enqueue(new MockResponse()
        .setResponseCode(200)
        .addHeader("Content-Type", "application/json")
        .setBody("{\"active\":false}"));
```

These are **two sequential responses**; share one server only when the order of the two requests in the test is deterministic. To avoid flaky parallel tests, spin up an isolated server per test as in the JUnit example above. To simulate timeouts, enqueue a response delayed longer than the **explicitly configured network timeout on WebClient/HTTP client**, plus an overall test timeout; never rely on the framework's long default timeouts.

**Retries and circuit breakers:** add only when operational design requires them. Introspection may be invoked repeatedly on retries; cap attempts, use backoff, and enforce a time budget. Never auto-retry every HTTP error or invent an "authenticated fallback". With JWKS, caching may let you keep verifying tokens whose trusted key is already cached during a brief IdP outage, but un-fetched new keys must never be accepted. Verify your library's actual behavior and cache policy instead of guessing.

## 8. Verifying what matters most: fail closed and no data leaks

In every failure scenario, assert across all three layers:

- **Auth result:** no valid `Authentication` exists on bad signature/`active=false`/unverifiable IdP; API returns no protected data.
- **HTTP contract:** verify status codes, `WWW-Authenticate` when appropriate, and that response bodies contain no tokens, client secrets, private keys, or stack traces.
- **Observability:** distinguish invalid tokens, missing scopes, upstream 401/403, upstream 429/5xx, and timeouts via safe loggers/metrics; correlation IDs enable tracing without logging raw Bearer tokens.

Never put production credentials, private signing keys, or real user tokens in fixtures. The mock server publishes only public JWKs. For HTTP introspection, checking the Basic header in a test may compare against a value built from **test credentials**, without printing the header to console or CI reports.

When signing JWTs in tests, use a fixed fixture key pair or generate one per test for isolation; use `Instant.now()` with a wide enough margin (e.g., ± several minutes) to avoid runtime-timing flakiness. Clock-skew scenarios should have dedicated tests with a controllable clock. In parallel CI, never share a `MockWebServer`/response queue across asynchronous tests.

## 9. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Calling only `mockJwt()` and claiming "JWKS tested" | No HTTP GET or RSA verification ran | Generate real signed JWT + real decoder + public JWKS stub |
| Returning placeholder `n` in JWK | JSON looks right but key is unusable | Generate a real `RSAKey` and call `toPublicJWK()` |
| Checking only HTTP 200 from introspection | `active=false` also returns 200 | Inspect body and `StepVerifier` error |
| Using Servlet APIs `JwtDecoder`, `HttpSecurity` | Does not reflect WebFlux flow | Use `ReactiveJwtDecoder`, `ServerHttpSecurity`, `WebTestClient` |
| Forgetting issuer/audience validators on a manual decoder | Validly signed token for wrong target slips through | Attach validators explicitly |
| Asserting a fixed JWKS GET count | Caching/key rotation makes tests flaky | Assert verification outcome; control cache when testing refresh |
| Mixing JWT and opaque in one context unintentionally | Testing the wrong authentication manager | Separate contexts or configure filter chains explicitly |
| `Mono` never subscribed | No HTTP request actually runs | Use `StepVerifier` or `WebTestClient.exchange()` |
| Treating timeout/503 as "anonymous but allow" | Fail-open risk and resource leakage | Deny access, classify errors, and monitor |
| Logging tokens/client secrets in test logs | Credential leakage in CI | Redact logs, use fake fixtures, assert internally |

## 10. Checklist for a reliable test suite

- [ ] At least one real signed JWT and valid public JWKS; verify signature, `kid`, and issuer.
- [ ] Bad-signature and expired-token cases; never grant access.
- [ ] A key rotation or JWK `kid` mismatch case with explicit cache policy.
- [ ] Real POST introspection verifying form/Basic authentication and `active=true/false`.
- [ ] Valid/missing scope cases separating 401 (authentication) from 403 (authorization).
- [ ] At least one 5xx and one timeout/connection error; never fail-open.
- [ ] API response checks with `WebTestClient` when verifying the end-to-end filter chain.
- [ ] Isolated tests, ephemeral ports, server cleanup, and zero reliance on internet IdPs.
- [ ] No private keys, raw tokens, or secrets in logs, reports, or responses.

## References

- Spring Security — [Reactive Resource Server: JWT](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/jwt.html).
- Spring Security — [Reactive Resource Server: Opaque Token](https://docs.spring.io/spring-security/reference/6.5/reactive/oauth2/resource-server/opaque-token.html).
- Spring Security — [Testing OAuth 2.0 with WebFlux](https://docs.spring.io/spring-security/reference/6.5/reactive/test/web/oauth2.html).
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517).
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662).

**Expected outcome:** learners can provide concrete evidence that resources are accessible only when tokens are properly verified via remote JWK/introspection, while invalid tokens and IdP outages are handled safely and remain diagnosable.