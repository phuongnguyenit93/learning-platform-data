# 31.5. Testing Expired ID Tokens, Wrong Issuer, Wrong Audience, and Bad Signature

## 1. Context: Token Endpoint Returning 200 Does Not Mean the ID Token Is Trustworthy

An **Employee Portal** application uses **Spring Security OAuth 2.0/OIDC Client** so users can log in through an OpenID Provider (OP):

~~~text
Browser
  -> Employee Portal (Relying Party / OAuth2 Client)
      -> Authorization endpoint
      -> Token endpoint
      -> OpenID Provider's JWK Set endpoint
~~~

In the Authorization Code Flow, the OP returns:

~~~json
{
  "access_token": "<redacted-access-token>",
  "token_type": "Bearer",
  "expires_in": 300,
  "id_token": "<compact-signed-jwt>"
}
~~~

The **ID Token** is authentication proof issued by the OP to the **OAuth2/OIDC Client**, distinct from the **access token** used to call a Resource Server. Even when the HTTP status is 200 and the token contains a valid-looking user name, Spring Security must reject the ID Token if:

1. **Expired**: the `exp` claim is no longer valid.
2. **Wrong issuer**: the `iss` claim does not match the trusted issuer.
3. **Wrong audience**: the `aud` claim does not contain the current registration's `client_id`.
4. **Bad signature**: the JWS signature fails verification against a trusted signing key.

If you only test:

~~~java
mockMvc.perform(get("/api/me").with(oidcLogin()))
    .andExpect(status().isOk());
~~~

you have not proven any of those four checks. `oidcLogin()` is a **Spring Security Test postprocessor** that injects a mock Authentication into the request, bypassing the token endpoint and real JWT decoding/verification.

**Lesson goal:** use a **fake OP** issuing genuinely RSA-signed ID Tokens, let **Spring Security OIDC Client** process the authorization-code callback, fetch JWKS, and verify the token. The first test must succeed with a valid token; the next four tests must fail when changing just one factor at a time.

> Context: Java 17+, Spring Boot 3, Spring Security 6, Servlet/Spring MVC, MockMvc, and Nimbus JOSE + JWT. Corresponding guidance for WebFlux is included. All hosts, secrets, and keys used in this lesson are fixtures; never pull ID Tokens/client secrets from production.

## 2. Concrete Goals of the Test Suite

After this lesson, your tests should prove:

- **Valid control**: a token with valid issuer, audience, expiration, nonce, and signature is accepted.
- **Expired**: a token with `exp` far enough in the past to exceed clock skew must be rejected.
- **Wrong issuer**: a token signed by a trusted key, yet with the wrong `iss`, must be rejected.
- **Wrong audience**: a properly signed token with the right issuer, yet `aud` missing the client ID, must be rejected.
- **Bad signature**: valid claims and a JOSE header `kid` pointing to a trusted key, yet signed by another key, must be rejected.
- **Fail closed**: a negative callback creates no authenticated session and grants no access to protected endpoints.
- **Sound test technique**: failure occurs during ID Token validation, not masked by state/cookie/token-endpoint/JWKS errors.
- **Operational security**: tests and logs never expose private signing keys, real credentials, codes, refresh tokens, or raw ID Tokens.

## 3. Claims You Must Understand Correctly

An illustrative ID Token JWT payload:

~~~json
{
  "iss": "https://login.company.example",
  "sub": "employee-0042",
  "aud": "employee-portal-web",
  "exp": 1893456600,
  "iat": 1893456300,
  "nonce": "nonce-tied-to-authorization-request"
}
~~~

The timestamps above are illustrative only. In tests, compute times relative to `Instant.now()` instead of hardcoding a year that can eventually expire.

| Claim | Meaning | What Is Checked |
|---|---|---|
| `iss` | Issuing OpenID Provider identifier | Matches the trusted issuer exactly |
| `sub` | Subject under that issuer | Non-empty valid value mapped properly |
| `aud` | ID Token audience | Contains the exact OAuth client ID |
| `exp` | Expiration timestamp | Not expired within clock skew policy |
| `iat` | Issued-at timestamp | Fits validation contract |
| `nonce` | Binds to authentication request | Matches original authorization request |
| `azp` | Authorized party in some cases | Valid under client/audience rules |
| `auth_time` | When user authenticated if requested | Satisfies max_age policy |

**Do not confuse these three values:**

~~~text
iss = who issued the ID Token?
aud = which OAuth client is this ID Token intended for?
sub = which user was authenticated by that issuer?
~~~

### 3.1. ID Token Audience Differs from Access Token Audience

~~~text
ID Token:
  aud = employee-portal-web

Access Token:
  aud = orders-api (when required by the Resource Server contract)
~~~

Do not alter the ID Token audience validator to accept `orders-api` just because the Portal needs to call the Orders API.

### 3.2. Issuer Must Match Exactly

~~~text
https://login.example.com/realms/staff
https://login.example.com/realms/partners
~~~

These two values can be two separate issuers even if they share a hostname/JWK infrastructure. Do not strip paths or force issuers to match merely because they share a vendor.

## 4. Where Does Spring Security Verify the ID Token?

In the Servlet stack, the typical flow is:

~~~text
OAuth2AuthorizationRequestRedirectFilter
  -> creates authorization request, state, nonce
  -> redirects browser to Authorization Server

OAuth2LoginAuthenticationFilter
  -> processes authorization code callback
  -> invokes OAuth2/OIDC authentication provider
  -> exchanges code for token response
  -> decodes/verifies ID Token per ClientRegistration
  -> creates Authentication once all checks succeed
~~~

Key components to know:

~~~java
org.springframework.security.oauth2.client.oidc.authentication
    .OidcAuthorizationCodeAuthenticationProvider

org.springframework.security.oauth2.client.oidc.authentication
    .OidcIdTokenDecoderFactory
~~~

`OidcIdTokenDecoderFactory` provides a decoder per `ClientRegistration`, applying the appropriate issuer/client ID/JWK Set and algorithm policy. Across the OIDC login flow, additional checks bind the ID Token to the authorization request, such as nonce.

### 4.1. Two Distinct JWT Validation Paths

A backend may simultaneously act as:

~~~text
OAuth2 Client:
  Validates OIDC ID Tokens for browser login.

OAuth2 Resource Server:
  Validates JWT access tokens received from callers.
~~~

The Resource Server's `JwtDecoder` does not automatically replace the OIDC Client's decoder factory. Mocking the wrong decoder can leave your test completely bypassing the mechanism you meant to verify.

### 4.2. Outcomes That Must Be Distinguished

~~~mermaid
flowchart TD
    A["OIDC callback with code/state"] --> B["Token endpoint returns id_token"]
    B --> C{"JWT parse + trusted JWK/signature"}
    C -->|Invalid| R["Reject login"]
    C -->|Valid| D{"iss, aud, exp and time claims"}
    D -->|Invalid| R
    D -->|Valid| E{"nonce / OIDC flow binding"}
    E -->|Invalid| R
    E -->|Valid| F["Authenticated OAuth2AuthenticationToken"]
~~~

A failing callback **does not prove** that the `exp` or signature validator ran. It could have failed earlier on state mismatch before the token endpoint was ever called.

## 5. Test Matrix: Change Only One Factor at a Time

| Scenario | Issuer | Audience | Expiration | Signing Key | Expect |
|---|---|---|---|---|---|
| VALID | Expected | Client ID | Future | Trusted | Succeed |
| EXPIRED | Expected | Client ID | **Past** | Trusted | Reject |
| WRONG_ISSUER | **Unexpected** | Client ID | Future | Trusted | Reject |
| WRONG_AUDIENCE | Expected | **Other client ID** | Future | Trusted | Reject |
| BAD_SIGNATURE | Expected | Client ID | Future | **Attacker** | Reject |

Across all five scenarios, `nonce`, `state`, token endpoint status, and JWK Set response must remain valid.

**Do not** create a wrong-issuer token by editing the payload after signing: the signature will break and mask the issuer check.

## 6. Why Do We Need a Fake OpenID Provider?

A **fake OP** provides:

~~~text
POST /token
  -> HTTP 200 + access_token/id_token

GET /jwks
  -> HTTP 200 + trusted public RSA JWK
~~~

The test initiates the OAuth2 authorization request directly through Spring Security:

~~~text
GET /oauth2/authorization/oidc-test
  -> 302 Location: <fake-op>/authorize?...state=...&nonce=...
~~~

Then the test acts as the browser sending the callback:

~~~text
GET /login/oauth2/code/oidc-test?code=fake-code&state=<original-state>
~~~

**Essential point:** reuse the same `MockHttpSession` between start and callback so Spring Security locates the original authorization request. The fake OP only needs to serve token/JWKS endpoints, since the test does not actually open an authorization page in a browser.

### 6.1. Test Diagram

~~~mermaid
sequenceDiagram
    participant Test as JUnit / MockMvc
    participant Portal as Spring Security OAuth2 Client
    participant Fake as Fake OP

    Test->>Portal: GET /oauth2/authorization/oidc-test
    Portal-->>Test: Redirect with state and nonce
    Test->>Test: Save session, parse state/nonce
    Test->>Fake: Set next scenario
    Test->>Portal: Callback with original state, fake code, same session
    Portal->>Fake: POST /token
    Fake-->>Portal: Signed id_token scenario
    Portal->>Fake: GET /jwks (may be cached)
    Fake-->>Portal: Trusted public JWK
    Portal->>Portal: Verify JWS + claims + nonce
    Portal-->>Test: Success or authentication failure
~~~

### 6.2. Never Call a Real IdP in CI

The fake OP should bind `127.0.0.1` on a random port. Integration tests are far more reliable when they don't depend on production credentials, external networks, consent prompts, or provider rate limits.

## 7. Dependencies and Tools

Gradle Kotlin DSL:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-security")
    implementation("org.springframework.boot:spring-boot-starter-oauth2-client")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("org.springframework.security:spring-security-test")
    testImplementation("com.nimbusds:nimbus-jose-jwt")
}

tasks.test {
    useJUnitPlatform()
}
~~~

The Spring Boot BOM manages compatible dependency versions. To minimize external libraries, the example fake server uses the JDK's `com.sun.net.httpserver.HttpServer`. When a project uses the Java module system, you may need to declare the `jdk.httpserver` module for tests.

### 7.1. Do Not Use Resource Server Test's jwt() for This Goal

~~~java
.with(jwt())
~~~

only creates a mock JWT Authentication for testing Spring Resource Server or controllers. It does not make Spring Security OAuth2/OIDC Client exchange a code, fetch an ID Token, and verify its signature.

## 8. RSA Keys for Creating Valid and Invalid Signatures

Nimbus JOSE:

~~~java
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;

RSAKey trusted = new RSAKeyGenerator(2048)
    .keyID("trusted-kid")
    .generate();
RSAKey attacker = new RSAKeyGenerator(2048)
    .keyID("attacker-kid")
    .generate();

String publicJwks = new JWKSet(
    trusted.toPublicJWK()
).toString();
~~~

Only serve `trusted.toPublicJWK()` at fake `/jwks`. Private RSA keys stay strictly inside the test process and are never sent over HTTP.

### 8.1. How to Produce a True Bad Signature

Keep:

~~~text
JWT header:
  alg=RS256
  kid=trusted-kid

JWKS:
  kid=trusted-kid -> trusted public key
~~~

but sign with the **attacker private key**. When the decoder selects the trusted public key, RSA signature verification must fail. If you instead change the header `kid` to an unknown one, the test can fail at **key lookup**, without proving signature verification ran.

### 8.2. Do Not Manually Edit Compact JWTs

If you alter the base64url payload of a signed JWT, the signature immediately breaks. For negative tests `EXPIRED`, `WRONG_ISSUER`, and `WRONG_AUDIENCE`, modify the claims first and then **sign with the trusted key** to test the exact target validator.

## 9. Helper for Creating a Signed JWT ID Token

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

import java.time.Instant;
import java.util.Date;

static String signedIdToken(
    RSAKey privateSigningKey,
    String advertisedKid,
    String issuer,
    String audience,
    String nonce,
    Instant issuedAt,
    Instant expiresAt
) throws Exception {
    JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .issuer(issuer)
        .subject("employee-0042")
        .audience(audience)
        .issueTime(Date.from(issuedAt))
        .expirationTime(Date.from(expiresAt))
        .claim("nonce", nonce)
        .build();

    SignedJWT jwt = new SignedJWT(
        new JWSHeader.Builder(JWSAlgorithm.RS256)
            .keyID(advertisedKid)
            .build(),
        claims
    );
    jwt.sign(new RSASSASigner(privateSigningKey));
    return jwt.serialize();
}
~~~

A valid token has:

~~~text
iss = testIssuer
sub = employee-0042
aud = employee-portal-test
iat = now - 10 seconds
exp = now + 10 minutes
nonce = nonce from /authorize redirect
signature = trusted RSA key
~~~

### 9.1. Why Should the exp Case Also Adjust iat?

If you set `exp=now-15 minutes` while leaving `iat=now`, `iat > exp` is itself anomalous temporal data. To isolate expiration cleanly, use:

~~~java
Instant issuedAt = now.minusSeconds(1800);
Instant expiresAt = now.minusSeconds(900);
~~~

That means the ID Token was issued 30 minutes ago and expired 15 minutes ago.

## 10. Test ClientRegistration Pointing Directly to the Fake OP

Instead of real issuer discovery:

~~~yaml
provider:
  company:
    issuer-uri: https://production-idp.example
~~~

tests can build a `ClientRegistration` directly:

~~~java
ClientRegistration registration =
    ClientRegistration.withRegistrationId("oidc-test")
        .clientId("employee-portal-test")
        .clientSecret("only-a-test-secret")
        .clientAuthenticationMethod(
            ClientAuthenticationMethod.CLIENT_SECRET_BASIC)
        .authorizationGrantType(
            AuthorizationGrantType.AUTHORIZATION_CODE)
        .redirectUri(
            "{baseUrl}/login/oauth2/code/{registrationId}")
        .scope("openid")
        .authorizationUri(fakeIssuer + "/authorize")
        .tokenUri(fakeIssuer + "/token")
        .jwkSetUri(fakeIssuer + "/jwks")
        .issuerUri(fakeIssuer)
        .clientName("Test OpenID Client")
        .build();
~~~

This preserves:

- Client ID to validate audience.
- Trusted issuer to validate `iss`.
- JWKS URI to validate signature.
- Token endpoint for Spring Security to exchange the fake code for an ID Token.
- Redirect URI/callback per registration.

`scope("openid")` activates OIDC login semantics. UserInfo is unnecessary in this example since the goal is testing ID Tokens; if adding a UserInfo endpoint, stub it and separate UserInfo failures from ID Token failures.

## 11. MockMvc Must Execute the Real Filter Chain

A test security chain might look like:

~~~java
@Bean
SecurityFilterChain testSecurityFilterChain(HttpSecurity http)
        throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/me").authenticated()
            .anyRequest().permitAll())
        .oauth2Login(oauth -> oauth
            .successHandler((request, response, auth) ->
                response.setStatus(204))
            .failureHandler((request, response, ex) ->
                response.sendError(401)))
        .exceptionHandling(errors -> errors
            .authenticationEntryPoint(
                new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
        .build();
}
~~~

In this sample code:

- A **successful** callback returns 204 instead of redirecting.
- A **failed** callback returns 401 instead of redirecting to `/login?error`.
- Anonymous requests to `/api/me` return 401.

This is a **test-only policy** to make assertions clear. Production may keep default OAuth2 Login redirects; in that case assertions must reflect the actual redirects.

### 11.1. Never Test by Disabling the Signature Validator

Do not install a custom decoder that always returns a "valid" token in this lesson; the goal is to make Spring Security genuinely verify the JWT signed by the fake OP.

### 11.2. Avoid 401s Unrelated to the Token

If even a valid token gets rejected due to SecurityFilterChain config, a missing registration bean, or a broken failure handler, negative tests become meaningless. Always get the valid baseline passing first.

## 12. Fake OP Server Using JDK HttpServer

The server has two routes:

~~~java
HttpServer server = HttpServer.create(
    new InetSocketAddress("127.0.0.1", 0), 0);
~~~

`0` is an OS-assigned ephemeral port. After `server.start()`, use:

~~~java
String issuer = "http://127.0.0.1:"
    + server.getAddress().getPort();
~~~

Only use HTTP localhost for **tests**. Production OIDC issuer/token/JWKS endpoints must use HTTPS/TLS and trusted metadata.

### 12.1. JWKS Handler

~~~java
server.createContext("/jwks", exchange -> {
    byte[] data = new JWKSet(
        trusted.toPublicJWK()
    ).toString().getBytes(StandardCharsets.UTF_8);
    exchange.getResponseHeaders().set(
        "Content-Type", "application/json");
    exchange.sendResponseHeaders(200, data.length);
    try (OutputStream out = exchange.getResponseBody()) {
        out.write(data);
    }
});
~~~

### 12.2. Token Endpoint Handler

~~~java
server.createContext("/token", exchange -> {
    try {
        exchange.getRequestBody().readAllBytes();
        String jwt = makeTokenForCurrentScenario();
        String body =
            "{\"access_token\":\"fake-access-token\","
            + "\"token_type\":\"Bearer\","
            + "\"expires_in\":300,"
            + "\"id_token\":\"" + jwt + "\"}";
        byte[] data = body.getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set(
            "Content-Type", "application/json");
        exchange.sendResponseHeaders(200, data.length);
        try (OutputStream out = exchange.getResponseBody()) {
            out.write(data);
        }
    } catch (Exception ex) {
        exchange.sendResponseHeaders(500, -1);
        exchange.close();
    }
});
~~~

This is a **fixture code fragment**: `makeTokenForCurrentScenario()` is defined in the helper below. The fake token handler does not validate a real client secret/authorization code; it lets the test focus on OIDC Client validation. If you want to test grant/code/client authentication, write a separate integration test for fake AS behavior.

## 13. Combining the Pieces into a Test Fixture

We use a **FakeOidcServer** fixture managing:

~~~java
enum Scenario {
    VALID,
    EXPIRED,
    WRONG_ISSUER,
    WRONG_AUDIENCE,
    BAD_SIGNATURE
}
~~~

State:

~~~java
final AtomicReference<Scenario> scenario =
    new AtomicReference<>(Scenario.VALID);
final AtomicReference<String> nonce =
    new AtomicReference<>();
final RSAKey trusted;
final RSAKey attacker;
final HttpServer server;
final String issuer;
~~~

Before each test:

~~~java
@BeforeEach
void reset() {
    fakeOp.scenario.set(Scenario.VALID);
    fakeOp.nonce.set(null);
}
~~~

When running tests in parallel, a global mutable scenario can be overwritten by another test. Therefore, the sample fixture assumes **sequential** execution, or else you must isolate a server per test / route responses using a correlation ID.

### 13.1. Generating Tokens per Scenario

~~~java
String makeTokenForCurrentScenario() throws Exception {
    Instant now = Instant.now();
    Scenario current = scenario.get();

    String actualIssuer =
        current == Scenario.WRONG_ISSUER
            ? "https://wrong-issuer.example.invalid"
            : issuer;

    String actualAudience =
        current == Scenario.WRONG_AUDIENCE
            ? "unrelated-client"
            : "employee-portal-test";

    Instant issuedAt =
        current == Scenario.EXPIRED
            ? now.minusSeconds(1800)
            : now.minusSeconds(10);

    Instant expiresAt =
        current == Scenario.EXPIRED
            ? now.minusSeconds(900)
            : now.plusSeconds(600);

    RSAKey signingKey =
        current == Scenario.BAD_SIGNATURE
            ? attacker
            : trusted;

    return signedIdToken(
        signingKey,
        trusted.getKeyID(), // keep trusted kid even when signature is bad
        actualIssuer,
        actualAudience,
        nonce.get(),
        issuedAt,
        expiresAt
    );
}
~~~

`signedIdToken()` is the Nimbus helper defined in Section 9.

### 13.2. Never Hardcode the Real Nonce

The nonce must come from the authorization request generated by Spring Security. A hardcoded nonce shared across tests can cause the valid case to fail OIDC flow binding before reaching the target claim checks.

## 14. First: Create the Authorization Request and Keep MockHttpSession

Test helper:

~~~java
private MockHttpSession beginLoginAndCaptureContext() throws Exception {
    MvcResult started = mockMvc
        .perform(get("/oauth2/authorization/oidc-test"))
        .andExpect(status().is3xxRedirection())
        .andReturn();

    MockHttpSession session = (MockHttpSession)
        started.getRequest().getSession(false);
    assertNotNull(session);

    String location = started.getResponse().getRedirectedUrl();
    assertNotNull(location);

    var query = UriComponentsBuilder.fromUriString(location)
        .build()
        .getQueryParams();
    String state = query.getFirst("state");
    String nonce = query.getFirst("nonce");

    assertNotNull(state);
    assertNotNull(nonce);

    fakeOp.nonce.set(nonce);
    savedState = state; // test field, kept strictly local to the fixture
    return session;
}
~~~

Here `fakeOp` is the server fixture and `savedState` is a test field. If tests run in parallel, replace these fields with a per-test immutable context record.

### 14.1. Why Do We Need State?

`state` binds the callback to the original authorization request and defends against login CSRF. If you send a callback with the wrong state, Spring Security may reject it before token exchange. That is **a separate state test**, and does not prove exp/issuer/aud/signature validation.

### 14.2. Why Do We Need Nonce?

Nonce binds the ID Token to the original OIDC authentication request. Spring Security may store a raw nonce and send a hashed nonce; when the fake OP issues an ID Token, it must return **the nonce value received in the authorization request**. Tests do not guess the nonce.

### 14.3. Same Session Is Mandatory in the Sample Flow

Do not initiate the authorization request with session A and send the callback with session B. The authorization request repository will fail to find the original context, leading to false-positive negative tests.

## 15. Callback Helper Running Each Scenario

~~~java
private MockHttpSession performLogin(
    Scenario scenario,
    int expectedCallbackStatus
) throws Exception {
    MockHttpSession session = beginLoginAndCaptureContext();

    fakeOp.scenario.set(scenario);

    mockMvc.perform(
        get("/login/oauth2/code/oidc-test")
            .session(session)
            .param("code", "fake-authorization-code")
            .param("state", savedState)
    ).andExpect(status().is(expectedCallbackStatus));

    return session;
}
~~~

The goal is not to prove the OP accepts the fake authorization code for security semantics; the fake token endpoint always returns a fixture token. **The goal is to deliver a valid/invalid JWT to the OIDC Client's decoder inside a callback that is valid in state/session.**

## 16. Valid Baseline Test: Proper ID Token Is Accepted

~~~java
@Test
void validIdTokenIsAccepted() throws Exception {
    MockHttpSession session =
        performLogin(Scenario.VALID, 204);

    mockMvc.perform(get("/api/me").session(session))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.subject")
            .value("employee-0042"))
        .andExpect(jsonPath("$.registration")
            .value("oidc-test"));
}
~~~

A probe controller:

~~~java
@RestController
class CurrentUserController {

    @GetMapping("/api/me")
    Map<String, String> me(
        OAuth2AuthenticationToken authentication
    ) {
        return Map.of(
            "subject", authentication.getName(),
            "registration",
            authentication.getAuthorizedClientRegistrationId()
        );
    }
}
~~~

When the valid test succeeds:

~~~text
Original request state was valid.
Fake token endpoint responded.
JWT parse/signature/claims/nonce validations succeeded.
Authenticated principal persisted in session.
Protected endpoint is accessible.
~~~

### 16.1. If the Valid Baseline Fails, Stop Drawing Conclusions from Negative Tests

If all tokens fail because the JWKS endpoint returns 404, negative tests will show "rejected" yet **prove nothing** about validating the four claims. Always get the valid flow passing first.

## 17. Expired Test: Past exp with Valid Signature

~~~java
@Test
void expiredIdTokenIsRejected() throws Exception {
    MockHttpSession session =
        performLogin(Scenario.EXPIRED, 401);

    mockMvc.perform(get("/api/me").session(session))
        .andExpect(status().isUnauthorized());
}
~~~

Fixture:

~~~text
iss: expected
aud: employee-portal-test
nonce: expected
signature: trusted
iat: now - 1800 seconds
exp: now - 900 seconds
~~~

The token expired 15 minutes ago so clock-skew tolerance won't make the test flaky.

### 17.1. Do Not Just Edit Payload After Signing

If you edit `exp` via base64url decoding while keeping the old signature, the test can fail due to bad signature. Always sign **after** setting the past expiry.

### 17.2. Clock Skew and Custom Validators

Times very close to `now` are generally unsuitable for stable integration tests. If you must test exact skew boundaries, write a **time validator unit test** with an explicitly configured Clock/tolerance rather than guessing defaults.

## 18. Wrong Issuer Test: Different iss with Valid Public Key

~~~java
@Test
void wrongIssuerIsRejected() throws Exception {
    MockHttpSession session =
        performLogin(Scenario.WRONG_ISSUER, 401);

    mockMvc.perform(get("/api/me").session(session))
        .andExpect(status().isUnauthorized());
}
~~~

Fixture:

~~~text
expectedIssuer: http://127.0.0.1:<fake-port>
actualIssuer: https://wrong-issuer.example.invalid
aud: expected
exp: future
nonce: expected
signature: trusted
~~~

**Important:** the signature must be valid—never use the attacker key in this scenario. Otherwise, the test does not prove issuer validation executed.

### 18.1. Issuers with Paths

`https://id.example/realms/a` and `https://id.example/realms/b` must never be treated as the same issuer. Do not weaken the validator to compare hostnames alone.

### 18.2. A Public Key May Be Reused

Even if a token from another issuer is signed with a key the client already trusts, the issuer check must still prevent accepting tokens across trust boundaries.

## 19. Wrong Audience Test: aud Missing Client ID

~~~java
@Test
void wrongAudienceIsRejected() throws Exception {
    MockHttpSession session =
        performLogin(Scenario.WRONG_AUDIENCE, 401);

    mockMvc.perform(get("/api/me").session(session))
        .andExpect(status().isUnauthorized());
}
~~~

Fixture:

~~~text
clientId in ClientRegistration: employee-portal-test
aud in ID Token: unrelated-client
iss: expected
exp: future
signature: trusted
nonce: expected
~~~

Expected: the OIDC Client rejects the token because it was not intended for the current Relying Party.

### 19.1. aud as a String or Array

~~~json
{"aud": "employee-portal-test"}
~~~

or:

~~~json
{"aud": ["employee-portal-test", "other-client"]}
~~~

With multiple audiences, also consider `azp` per OIDC rules and client policy. Do not check only a single string literal and overlook array cases.

### 19.2. Do Not Accept an API Audience

ID Token `aud` must target the **client ID**, not `orders-api` or a downstream API hostname, unless it actually happens to be the client ID per contract (which must never be guessed).

## 20. Bad Signature Test: Different Signer While Keeping Trusted kid

~~~java
@Test
void badSignatureIsRejected() throws Exception {
    MockHttpSession session =
        performLogin(Scenario.BAD_SIGNATURE, 401);

    mockMvc.perform(get("/api/me").session(session))
        .andExpect(status().isUnauthorized());
}
~~~

Token:

~~~text
iss: expected
aud: expected
exp: future
nonce: expected
JOSE header kid: trusted-kid
JWKS public key: trusted
actual signing private key: attacker
~~~

When Spring Security verifies the signature using the trusted public key, the token must be rejected.

### 20.1. Different from Unknown kid

~~~text
kid=unknown
JWKS does not contain unknown
~~~

may fail because no key was found, not necessarily via cryptographic signature verification. Both should be tested, as **two distinct cases**.

### 20.2. Do Not Confuse Malformed JWT with Wrong Signature

A compact JWT with bad base64 or missing segments usually fails in the parser. To test signatures, generate a properly formatted JWS with Nimbus and sign it with a different key.

## 21. Configuring @SpringBootTest + @AutoConfigureMockMvc

A minimal test application can use:

~~~java
@SpringBootTest(
    classes = IdTokenValidationIT.TestApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.MOCK
)
@AutoConfigureMockMvc
class IdTokenValidationIT {

    @Autowired MockMvc mockMvc;

    @SpringBootConfiguration
    @EnableAutoConfiguration
    @Import({
        TestSecurityConfiguration.class,
        CurrentUserController.class
    })
    static class TestApplication {}
}
~~~

Inside `TestSecurityConfiguration`, declare:

~~~java
@Configuration
class TestSecurityConfiguration {

    @Bean
    ClientRegistrationRepository clientRegistrations() {
        return new InMemoryClientRegistrationRepository(
            testClientRegistration());
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/me").authenticated()
                .anyRequest().permitAll())
            .oauth2Login(oauth -> oauth
                .successHandler((req, res, a) ->
                    res.setStatus(204))
                .failureHandler((req, res, ex) ->
                    res.sendError(401)))
            .exceptionHandling(errors -> errors
                .authenticationEntryPoint(
                    new HttpStatusEntryPoint(HttpStatus.UNAUTHORIZED)))
            .build();
    }
}
~~~

`testClientRegistration()` returns the fixture from Section 10 and must be created after the fake OP is listening on its port. When wiring real code, start the fake server in a static fixture/extension with a guaranteed lifecycle **before the Spring context creates ClientRegistrationRepository**, and stop the server in `@AfterAll` / a JUnit extension.

### 21.1. Why Is a Mini Test App Useful?

Large applications may contain multiple SecurityFilterChains, a JWT Resource Server, custom login handlers, and a production `issuer-uri`. A minimal context isolates ID Token validation without interference from other tests or auto-discovery.

### 21.2. Replace Production Handlers or Use Test-Only Ones?

Test-only 204 success / 401 failure handlers are easy to assert. If you want to test exact production handler behavior, keep the production handlers and assert the right 302 redirect or error page. **Do not rely solely on a handler's 401 status as proof**; verify the valid baseline and post-failure session state.

## 22. Ensuring Negative Logins Create No Authentication

For every negative case:

~~~java
MockHttpSession session =
    performLogin(Scenario.WRONG_AUDIENCE, 401);

mockMvc.perform(get("/api/me").session(session))
    .andExpect(status().isUnauthorized());
~~~

Meaning:

~~~text
callback rejected
  -> no authenticated OAuth2AuthenticationToken persisted
  -> subsequent protected request is denied
~~~

**Do not inspect only the exception message**: an exception might be swallowed by a custom error handler while SecurityContext was already modified. Testing session behavior provides application-level proof.

### 22.1. When the Session Was Already Logged In Beforehand

If a user was already authenticated before attempting a new login, failure policy may keep or clear the old Authentication depending on design. The negative tests in this lesson should start with a **fresh session**, rather than reusing an authenticated session from a valid scenario, so results stay unambiguous.

## 23. Separating Direct Decoder Tests and Callback Integration

If you only want to test the decoder:

~~~java
import org.springframework.security.oauth2.client.oidc.authentication
    .OidcIdTokenDecoderFactory;
import org.springframework.security.oauth2.jwt.JwtDecoder;

OidcIdTokenDecoderFactory factory =
    new OidcIdTokenDecoderFactory();

JwtDecoder decoder = factory.createDecoder(testRegistration);

assertThrows(RuntimeException.class,
    () -> decoder.decode(expiredSignedJwt));
~~~

`expiredSignedJwt` must be a genuinely signed JWT; the fake JWKS endpoint must be running so the decoder can fetch the trusted key.

### 23.1. Strengths of Unit Decoder Tests

- Focuses on `exp`, `iss`, `aud`, and signature.
- Fast setup with minimal session/callback dependencies.
- Easy to inject a fixed Clock and directly assert validation exceptions.

### 23.2. Limitations

`factory.createDecoder().decode()` does not prove:

- Original authorization request/state.
- Authorization Code Flow/token endpoint exchange.
- Nonce binding in the OIDC authentication provider.
- Cookie/session persistence.
- Custom success/failure handlers.

Therefore, maintain both **decoder tests** and several **fake OP callback integration tests**.

## 24. Clock Skew: Avoiding Flaky Expired Tests

Some JWT validators permit clock tolerance:

~~~text
server now = 10:00:00
token exp  = 09:59:59
allowed skew = 60 seconds
~~~

The token may still be accepted per policy. That is not necessarily a bug.

### 24.1. Expired Tests Should Clearly Exceed Skew

~~~java
Instant now = Instant.now();
Instant expired = now.minusSeconds(900);
~~~

A 15-minute offset is large enough for most default tolerances. If the application configures a longer skew, adjust the test to match the policy.

### 24.2. Unit Testing Boundaries with a Fixed Clock

When boundary precision is needed:

~~~text
exp just inside tolerance -> result according to policy
exp just outside tolerance -> reject
~~~

Test the validator with a controlled Clock/clock skew instead of using `Thread.sleep()` and hoping real wall-clock time keeps the test stable.

### 24.3. Iat and nbf

An unusually future `iat` and a future `nbf` may need separate tests per validator/policy. Avoid introducing all three timing errors at once if your target is strictly `exp`.

## 25. OIDC Nonce: Additional Tests Worth Having

Nonce binds the ID Token to the authorization request:

~~~text
Original authorization request nonce = N1
ID Token nonce = N2
N1 != N2
=> OIDC login must fail
~~~

To test this, keep the token issuer/audience/expiration/signature valid while changing `nonce` before signing.

### 25.1. State Differs from Nonce

`state` binds the authorization callback to the request and mitigates login CSRF. `nonce` binds the ID Token to the authentication request. Never substitute one for the other.

### 25.2. Nonce Mismatch Is Not Wrong Issuer

If a wrong-issuer test accidentally uses a wrong nonce, failure may stem from nonce. Keep nonce valid across the four main scenarios so failures aren't masked.

### 25.3. Never Use a Global Nonce in Production

Nonce must be generated per authorization request with sufficient entropy. Tests should read the nonce from Spring Security's redirect rather than forcing the application to use a fixed nonce.

## 26. Multiple Audiences and azp

OIDC allows multi-valued audiences:

~~~json
{
  "aud": ["employee-portal-web", "another-client"],
  "azp": "employee-portal-web"
}
~~~

The expected Client ID must appear in the audience, while also applying OIDC `azp` rules when required. Spring Security/validator extensions can vary in extra checks across versions, so test against your chosen security contract.

Additional cases to cover:

~~~text
aud includes expected, azp expected -> evaluate other claims, accept if valid
aud includes expected, azp unexpected -> reject under relevant OIDC policy
aud excludes expected                 -> reject
~~~

### 26.1. Sharing an Issuer Does Not Authorize Other Audiences

Two registrations:

~~~text
employee-client: clientId=employee-portal
admin-client: clientId=admin-portal
issuer: same company OP
~~~

An ID Token with `aud=employee-portal` is not valid for `admin-client` just because the OP/JWKS are identical.

## 27. Signature, alg, and kid: Closely Related Cases

| Scenario | Mechanism Under Test |
|---|---|
| BAD_SIGNATURE, same trusted kid | Cryptographic signature verification |
| Unknown `kid` | Trusted JWK lookup/refresh |
| Wrong JWK key | Signature verification or key selection |
| Unsupported `alg` | Algorithm allowlist |
| `alg=none` | Unsigned token rejection |
| New key after rotation | JWKS cache/refresh |

### 27.1. Never Trust Self-Declared JOSE Headers

Before verification, `alg`, `kid`, and optional key URLs are untrusted data. Clients must bind algorithms/key sources to trusted ClientRegistration/OP metadata, never fetching keys from arbitrary token-provided URLs.

### 27.2. JWKS Must Contain Only Public Material

The fake JWKS response must never accidentally expose RSA private components. Always use `trusted.toPublicJWK()`.

### 27.3. JWKS Caching Does Not Guarantee a GET Every Time

The decoder may cache the JWK Set and refresh as needed. Signature validity tests should assert outcomes rather than forcing every callback to issue a network GET `/jwks`.

## 28. Signing Key Rotation and Caching

Consider:

~~~text
Phase 1:
  JWKS -> key-old
  ID Token signed key-old
  Expected accepted

Phase 2:
  JWKS -> key-old, key-new
  ID Token signed key-new
  Expected accepted after supported JWKS refresh

Phase 3:
  JWKS -> only key-new
  New tokens signed key-new
  Old key trust/revocation follows policy
~~~

The goal is ensuring key rotation causes neither a login outage nor weakened validation. **Never accept keys outside the trusted JWKS** just to keep logins working.

### 28.1. Clock and Cache Create Asynchronous Edge Cases

When caches expire or JWKs refresh can depend on the implementation. Use a test-lifecycle fake OP, controlled cache configuration, and test timeouts rather than blind polling.

## 29. Multi-Tenant and Provider Mix-Up

Suppose a SaaS app has:

~~~text
tenant ACME:
  issuer = https://id.acme.example/oidc
  client_id = portal-acme

tenant GLOBEX:
  issuer = https://id.globex.example/oidc
  client_id = portal-globex
~~~

Negative tests should cover:

- ACME callback receives an ID Token with GLOBEX issuer.
- ACME callback receives an ID Token with GLOBEX client `aud`.
- ACME ID Token signed by a key outside trusted ACME JWKS.
- User alters tenant in query string while original state/registration still belongs to ACME.

**Never take an unverified `iss` from a JWT payload to dynamically construct a ClientRegistration** and treat it as a trusted provider. The expected issuer must come from the original authorization request and the managed tenant/client catalog.

### 29.1. Subject Does Not Replace Tenant Authorization

Even with a valid ID Token, the user must still hold active membership and resource permissions in the tenant. Successful OIDC authentication does not automatically unlock all SaaS data.

## 30. Do Not Confuse OIDC ID Token and Resource Server JWT Tests

| Question | Appropriate Test |
|---|---|
| Does the OIDC Client accept an expired ID Token? | Fake OP + callback/ID Token decoder |
| Does the OIDC Client accept wrong `iss`? | Fake OP signed ID Token wrong issuer |
| Does the OIDC Client accept wrong `aud`? | Fake OP signed ID Token wrong client |
| Does the OIDC Client verify real signatures? | Trusted JWKS + bad RSA signature |
| Does the API Resource Server reject wrong-audience access tokens? | JwtDecoder/Resource Server integration |
| Does the controller render the right user after login? | `oidcLogin()` MockMvc |
| Do SameSite callback cookies work in a browser? | Browser E2E / proxy integration |

An app can act as both an OAuth2 Client and a Resource Server; both validators must be tested along their respective paths.

## 31. WebFlux: Applying the Same Strategy with WebTestClient

With Spring WebFlux, configure:

~~~text
ReactiveClientRegistrationRepository
SecurityWebFilterChain
WebTestClient
WebSession
~~~

The flow remains similar:

~~~text
GET /oauth2/authorization/oidc-test
  -> redirect with state/nonce
GET /login/oauth2/code/oidc-test?code=...&state=...
  -> fetch fake token
  -> validate ID Token
  -> establish reactive authentication/session
~~~

### 31.1. mockOidcLogin() Does Not Verify Signatures

~~~java
webTestClient.mutateWith(mockOidcLogin())
~~~

only creates a mock OidcUser/Authentication on an in-process exchange. Never use it to claim ID Token JWTs are verified.

### 31.2. Preserving WebSession Between Requests

WebFlux callback integration requires cookie/WebSession continuity. Do not start the authorization request with a client that drops cookies and then hit the callback on another session, or you will fail at state correlation.

### 31.3. Reactive Decoders Must Not Fail Open

If the JWKS endpoint returns 503 or signature verification fails, never accept an unverified ID Token. Tests should prove login fails closed rather than falling back to a mock principal.

## 32. Observing Failures Without Leaking Sensitive Data

An event can be normalized as:

~~~json
{
  "event": "oidc_login_failure",
  "registrationId": "oidc-test",
  "reasonCategory": "WRONG_AUDIENCE",
  "correlationId": "req-42"
}
~~~

This is an **application-defined category**, not a guarantee that Spring Security always emits this exact string. Exception types/messages can vary across versions and JOSE libraries.

Never log:

~~~text
id_token=<compact-JWT>
access_token=<Bearer>
refresh_token=<secret>
client_secret=<secret>
authorization_code=<one-time-code>
Authorization: Basic <credential>
Cookie: JSESSIONID=<session-id>
RSA private key
~~~

### 32.1. Never Display Raw Exceptions to the Browser

Appropriate user message:

~~~text
Could not verify sign-in information from the provider.
Please try again or contact support.
~~~

Never put stack traces, JWK keys, raw OAuth `error_description`, or sensitive JWT claims into the UI.

## 33. Causes of False-Positive Negative Tests

| Symptom | Why It Doesn't Prove the Right Validator | How to Fix |
|---|---|---|
| Valid token also returns 401 | Broken test setup | Get valid baseline passing |
| Token endpoint 404/500 | No ID Token reached validation | Fix fake OP |
| JWKS endpoint 404 | Signature validator lacked key | Serve trusted public key |
| State mismatch | Callback failed before token exchange | Preserve original state |
| Lost session | Authorization request not found | Use same session |
| Nonce mismatch | Failed at nonce check | Copy nonce from auth request |
| Wrong issuer signed by attacker | Failed at signature | Use trusted signing key |
| Wrong audience with expired exp | Failed at expiration | Set future exp |
| Bad signature with unknown kid | Failed at key lookup | Keep trusted header kid |
| Edited JWT payload after signing | Invalid signature | Re-sign after editing claims |
| Clock skew accepts barely expired exp | Tested right on boundary | Set exp far in the past |
| Used oidcLogin() | Decoder never ran | Use fake OP callback |
| Mocked JwtDecoder always valid | Bypassed mechanism under test | Use real ID Token decoder |
| Parallel tests sharing scenario | Token scenario overwritten | Isolate fixtures |
| Fake OP started after bean creation | Registration URI got wrong port | Control lifecycle |

## 34. Diagnosing Failure Causes in Order

~~~text
Unexpected test outcome
    |
    v
Does VALID scenario succeed end-to-end?
    |-- No -> fix session/state/callback/OP/JWKS setup.
    |
    v
Is token endpoint called with response 200?
    |-- No -> callback or fake AS problem.
    |
    v
Does ID Token contain expected nonce?
    |-- No -> authorization request binding problem.
    |
    v
Does JWT signature verify against trusted JWKS?
    |-- No -> signature/key test, not issuer/audience test.
    |
    v
Does iss match ClientRegistration?
    |-- No -> issuer validation should reject.
    |
    v
Does aud contain OAuth client ID?
    |-- No -> audience validation should reject.
    |
    v
Is exp within accepted validity/skew window?
    |-- No -> expiry validation should reject.
    |
    v
Did negative callback leave session unauthenticated?
    |-- No -> inspect failure handler/security persistence.
~~~

## 35. Anti-Patterns to Avoid

**1. Using `oidcLogin()` to prove signature validation.** Mock Authentication bypasses the protocol.

**2. Using production tokens in CI.** Risks credential leaks and flaky external dependencies.

**3. Editing JWT payloads after signing to test wrong issuer/audience/exp.** Signature failure hides the intended check.

**4. Putting wrong signature, expired exp, and wrong issuer in one token.** Fails to isolate validators.

**5. Asserting only callback != 200.** Could fail due to session/state/JWKS.

**6. Skipping the valid baseline.** You won't know if the integration works at all.

**7. Serving a fake public JWK while signing with a different key in the VALID case.** Baseline fails.

**8. Accepting unsigned `alg=none` JWTs because claims look right.** Breaks the trust boundary.

**9. Disabling issuer/audience checks because the IdP differs from the client.** Fix configuration/trust contracts instead.

**10. Using Resource Server JwtDecoder to infer OIDC ID Token validation.** Those are two separate paths.

**11. Letting query params determine issuer/JWK URLs.** Creates SSRF/issuer mix-up risks.

**12. Reusing an authenticated session in a new negative case.** Can mask failure persistence bugs.

**13. Logging ID Tokens or private RSA keys for debugging.** Can expose identities/credentials.

**14. Running parallel tests against a shared mutable fake OP scenario.** Produces flaky results.

**15. Dropping nonce/state validation to make callback tests easier.** Weakens integration security.

## 36. Practice Exercises

### Exercise 1 — Past exp After Signing

You sign a valid JWT and then modify `exp` in the base64url payload while keeping the original signature.

**Question:** Does the failing callback prove the expiration validator?

**Answer:** No. The signature is already invalid. Set `exp` first, then sign with the trusted key.

### Exercise 2 — Wrong Issuer That Also Has a Bad Signature

A token has the wrong issuer and is signed with the attacker private key.

**Question:** Has the test proven issuer validation?

**Answer:** Not yet. It may have failed on signature. Keep the trusted signature and change only `iss`.

### Exercise 3 — Wrong Audience Is Orders API

~~~text
ID Token aud=orders-api
OAuth Client clientId=employee-portal-web
~~~

**Question:** Is this valid?

**Answer:** No. ID Token audience must contain the Relying Party's client ID, not automatically the downstream Resource Server name.

### Exercise 4 — Signer B, Header kid A

JWKS contains RSA public key A, header `kid=A`, JWT signed with RSA private key B.

**Question:** Expected outcome?

**Answer:** Signature verification must fail, even if claims are valid.

### Exercise 5 — Clock Skew

`exp=now-1s` yet the test login still succeeds.

**Question:** Why?

**Answer:** The validator may allow clock tolerance. Use a clearly past `exp` or unit-test with a fixed Clock.

### Exercise 6 — Wrong Callback State

Callback with `state=wrong` and an ID Token with the wrong issuer.

**Question:** Does this prove the issuer validator?

**Answer:** No. It likely failed on state before calling the token endpoint.

### Exercise 7 — mockOidcLogin Wrong Issuer

`oidcLogin().idToken(token -> token.claim("iss","wrong"))` and controller GET returns 200.

**Question:** Does Spring Security ignore the issuer in production?

**Answer:** You cannot conclude that. The test postprocessor injected a mock Authentication; you need a fake OP + real decoder test.

### Exercise 8 — Multiple Registrations Sharing an Issuer

Client A has ID `employee-portal`, client B has ID `admin-portal`. ID Token has `aud=employee-portal`.

**Question:** Can it be used for client B?

**Answer:** No. Audience must match the current registration's client ID.

### Exercise 9 — JWKS Timeout

Fake OP returns 503 for JWKS and login fails.

**Question:** Should you temporarily disable signature verification?

**Answer:** No. Fail closed and handle availability/caching per policy.

### Exercise 10 — Valid Baseline Also Fails

All five tests return 401.

**Question:** Can you conclude the four negative cases are working?

**Answer:** No. Fix the valid token/session/token-endpoint/JWKS/nonce so the baseline returns 204 with an authenticated session first.

## 37. Implementation Checklist

| Question | Confirm |
|---|---|
| Is there a local fake OP/token endpoint? | Yes |
| Is the fake public JWKS valid? | Yes |
| Does the test ClientRegistration use its own issuer/client ID? | Yes |
| Does it avoid calling a production IdP? | Yes |
| Does the fake token response return JSON with id_token? | Yes |
| Is the compact JWT signed with Nimbus? | Yes |
| Does the trusted public key omit private params? | Yes |
| Is the original state parsed and reused? | Yes |
| Is the original nonce embedded in the ID Token? | Yes |
| Is the same MockHttpSession used on callback? | Yes |
| Does the valid baseline callback succeed? | Yes |
| Can the valid session access protected endpoints? | Yes |
| Is the expired token far enough past clock skew? | Yes |
| Does wrong issuer keep a valid signature? | Yes |
| Does wrong audience keep a valid signature? | Yes |
| Does bad signature use attacker signer with trusted kid? | Yes |
| Are all negative logins rejected? | Yes |
| Is the negative session left unauthenticated? | Yes |
| Avoided using oidcLogin() in place of real validation? | True |
| Avoided mocking an always-valid decoder? | True |
| Avoided skipping nonce/state? | True |
| Tested JWKS caching/rotation if needed? | Yes |
| Tested multi-registration/tenant if needed? | Yes |
| Is the fake OP fixture isolated during parallel runs? | Yes |
| Are logs free of raw tokens/keys? | Yes |
| Are separate browser/cookie E2E tests in place if needed? | Yes |

## 38. Summary

**An ID Token is trustworthy only after Spring Security verifies its signature, expiration, issuer, audience, and OIDC bindings.** A token with a valid-looking `sub` or email must still be rejected if the signature is invalid, `exp` has expired, `iss` is untrusted, or `aud` omits the ClientRegistration client ID.

To test these four cases, set up **RSA-signed JWT fixtures and fake OP token/JWKS endpoints**, then run the **OAuth2/OIDC Client callback** through real Spring Security. Always keep a valid baseline; the four negative tests vary **exactly one factor** at a time while keeping state, session, nonce, and all other claims valid. After a failed callback, verify no authenticated session can access protected endpoints.

`oidcLogin()` is useful for testing controllers/RBAC but does not verify signatures or claims; direct decoder tests isolate JWT validation, while fake OP callback integration tests prove those checks are wired into OIDC Login. For WebFlux, apply the same fake OP pattern with `WebTestClient` and `WebSession`.

**Conclusion:** the quality of the test suite lies not in "invalid tokens get rejected," but in proving **valid tokens are accepted**, **each distinct failure is caught at the right layer**, and **no fallback path skips security validation just to let login succeed**.
