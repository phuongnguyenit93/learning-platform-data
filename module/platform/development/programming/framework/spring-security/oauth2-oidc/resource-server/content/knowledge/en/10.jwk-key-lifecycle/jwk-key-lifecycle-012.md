# Testing Rotation, Key Mismatches, and Disrupted JWKS Sources

In a **Spring Security OAuth 2.0 / OIDC Resource Server**, a JWT access token is verified using public keys retrieved from the Authorization Server's **JSON Web Key Set (JWKS)**. Signing keys do not live forever: organizations rotate keys periodically, replace them urgently upon suspected compromise, or migrate algorithms on schedule. During transitions, the Resource Server must properly handle tokens signed with old keys, new keys, and tokens whose signatures or keys mismatch. Meanwhile, the JWKS endpoint may go down temporarily due to network, DNS, TLS, proxy, or Authorization Server failures.

The challenge is that **three distinct concerns must be tested independently**:

1. **Key rotation:** The published key set changes over time while both old and new JWTs can remain valid simultaneously.
2. **Key mismatch:** A JWT carries an unknown `kid`, a signature failing verification against the public key, a disallowed algorithm, or a key outside a trusted issuer.
3. **Disrupted JWKS source:** The Resource Server fails to fetch the key set, or an older cache lacks the key needed for a new token.

Handled poorly, the system can reject waves of valid tokens during key switches—or worse, an API might accidentally **skip signature verification** to paper over transient errors. Testing aims to preserve availability within safe bounds, **never accepting an unverified token**.

> **Core principle:** The JWKS tells the Resource Server *which public keys are trusted for signature verification*; `kid` helps *locate a candidate key*; only the signature and JWT validators determine whether the API accepts the token. When keys are missing or the JWKS is unreachable, the API must never treat a Bearer token as valid.

## 1. A Simple Model for Understanding Verification

Suppose a commerce system has:

- **Identity Server:** Authorization Server issuing JWT access tokens for applications.
- **Orders API:** Spring Security Resource Server accepting only access tokens whose `aud` includes `orders-api`.
- **Shop Web:** OAuth2 Client sending tokens to the Orders API.
- **JWKS endpoint:** `https://identity.example.test/realms/shop/protocol/openid-connect/certs` (illustrative URI).

Initially, the Identity Server signs JWTs with private key **A**, and the JWKS publishes public key **A**. The JWT carries JWS header:

~~~json
{
  "alg": "RS256",
  "kid": "key-A",
  "typ": "at+jwt"
}
~~~

Illustrative JWT payload:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "user-42",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "iat": 1893456000,
  "exp": 1893456900
}
~~~

When the Orders API receives the token, the conceptual sequence is:

~~~mermaid
sequenceDiagram
    participant C as OAuth2 Client
    participant R as Orders API
    participant J as JWKS Endpoint

    C->>R: Authorization: Bearer JWT (kid=key-A)
    R->>R: Parse JOSE header per policy
    opt Matching public key not yet available
        R->>J: Request JWKS from trusted issuer
        J-->>R: Public JWK A, B, ...
    end
    R->>R: Select candidate JWK by kid/alg/kty
    R->>R: Verify JWS signature
    R->>R: Validate iss, aud, exp, nbf, token type
    R->>R: Check scope and data permissions
    R-->>C: Resource or error
~~~

**`kid` may be read prior to verification** because the library needs it to choose a candidate key. However, `kid` and the entire header are sender-controlled inputs at that point and may only be used within **the key set and algorithms bound to a trusted issuer**. Never allow a token to nominate an arbitrary JWKS URI and make the API trust keys from it.

### 1.1. How Do JWK, JWKS, `kid`, and Algorithms Differ?

| Concept | Role | Example |
| --- | --- | --- |
| **JWK (JSON Web Key)** | Represents a single key in JSON | RSA public key with `kty`, `n`, `e`, `kid` |
| **JWKS (JSON Web Key Set)** | Collection of JWKs, allowing multiple keys to be published together | `{"keys":[keyA,keyB]}` |
| **`kid` (Key ID)** | Hint to pick a candidate key from the JWKS | `key-A`, `key-B` |
| **`alg`** | Protection algorithm declared in the JOSE header | `RS256` |
| **Issuer (`iss`)** | Issuing authority accepted by the API | `https://identity.example.test/realms/shop` |
| **Audience (`aud`)** | API authorized to receive the access token | `orders-api` |

A public RSA JWK looks like:

~~~json
{
  "kty": "RSA",
  "use": "sig",
  "kid": "key-A",
  "alg": "RS256",
  "n": "<base64url-modulus>",
  "e": "AQAB"
}
~~~

The `n` value here is a placeholder, **not a real key**. A public JWKS must never expose private key fields such as RSA `d`, `p`, or `q`. Private signing keys must stay managed inside the Authorization Server/HSM/KMS or delegated signing service.

Not every issuer includes `alg` or `use` on every JWK. The verifier must combine key-format requirements, the JOSE header, and **configured algorithm policy**, rather than inferring trust from a single field.

### 1.2. Testing JWKS Differs from Testing Permissions

**Signature verification** answers "Does this JWT match a trusted signing key?"; **claim validation** answers "Is the token from the right issuer, intended for this API, unexpired, and of the right type?"; **authorization** answers "Does the caller have sufficient scope and data access rights?".

A JWT validly signed with key B yet carrying `aud = billing-api` must still be rejected by the Orders API. Never write rotation tests that verify only signatures while omitting the remaining checks.

## 2. Safe Key-Rotation Lifecycle

During scheduled key changes, the standard pattern is **publishing the new key before signing with it**, keeping the old key while old tokens remain valid, and only then removing the old key.

~~~mermaid
flowchart LR
    S0["T0: JWKS has A; AS signs A"]
    S1["T1: JWKS has A+B; AS still signs A"]
    S2["T2: JWKS has A+B; AS switches to sign B"]
    S3["T3: A-signed tokens expire; JWKS keeps B"]
    S0 --> S1 --> S2 --> S3
~~~

| Phase | Published JWKS | Key AS Uses for New Tokens | Tokens Resource Server Must Accept |
| --- | --- | --- | --- |
| **T0 — pre-rotation** | A | A | A if unexpired and valid audience/permissions |
| **T1 — pre-publish** | A and B | A | A tokens; API has an opportunity to fetch B |
| **T2 — switch signing** | A and B | B | Unexpired A tokens and B tokens |
| **T3 — end of grace period** | B | B | B; A tokens only accepted if trust policy still permits, though goal is A already expired |

OAuth2/JWKS does not mandate fixed lengths for T1–T3. The Authorization Server team must account for:

- **Longest access token lifetime** signed with A, plus clock skew tolerance and policy-defined propagation/storage lag.
- **JWKS refresh/cache windows** on Resource Servers, including low-traffic pods.
- **Rolling deployments**, autoscaling, newly booted instances, and older cached instances.
- **Replication/CDN/proxy caches** in front of the JWKS endpoint, if any.
- Emergency key revocation rules, distinct from routine rotation.

### 2.1. Why Pre-Publish Key B?

If the AS starts signing with B **before** all APIs can see public key B, valid tokens fail because `kid = key-B` is unknown. Some JWKS libraries refresh on seeing an unseen `kid`, yet refreshing still requires a healthy JWKS endpoint and exact behavior varies by cache and library version.

**Pre-publishing lowers risk**, while tests must confirm the API actually fetches and selects key B under the application's real mechanics. Never assume an unknown-`kid` request always refreshes caches instantaneously.

### 2.2. Why Not Remove A Immediately When Switching to B?

Access tokens issued with A remain unexpired past T2. If the JWKS drops A immediately, fresh instances or instances refreshing their JWKS lose the ability to verify those older tokens—triggering mass logouts or 401 errors before `exp`.

In planned rotation, keep public key A in the JWKS **long enough** for A-signed tokens to expire per policy, and only then stop publishing A. For a **suspected compromised** key, evaluate a security override: you may need to withdraw/block A immediately and accept invalidating old tokens rather than prioritizing seamless login continuity.

## 3. Goals of the Test Suite

Your test suite should cover both **positive** and **negative** paths across at least three infrastructure states:

1. **JWKS healthy**, publishing one or more public keys.
2. **JWKS returning malformed/mismatched data**, such as a key differing from `kid`, invalid format, HTTP 5xx, or bad responses.
3. **JWKS unreachable** while caches either hold or lack known keys.

Every test must specify:

- **Key set published by the AS** prior to sending requests.
- **Actual key signing the JWT** (A, B, or an untrusted party's key).
- **JOSE header**, especially `alg` and `kid`.
- **Resource Server JWKS memory/cache state**.
- **Issuer, audience, and token lifetime**.
- **Expected outcome**: authenticated, denied as invalid token, or dependency error—never looking only at a single HTTP code.

A practical test matrix:

| Test | Current JWKS | JWT Signed With | Additional Conditions | Expected Result |
| --- | --- | --- | --- | --- |
| R1 — baseline | A | A | `kid = A`, unexpired | Signature valid; proceed to claim/permission checks |
| R2 — pre-publish | A+B | A | B not yet signing new tokens | A tokens continue succeeding |
| R3 — switch signer | A+B | B | API has B or can refresh JWKS | B tokens valid |
| R4 — grace period | A+B | A | A token unexpired | A token still valid |
| R5 — retire old key | B | A | A token expired | Rejected; expired/retired A must not remain accepted by policy |
| R6 — unknown kid | A+B | C | `kid = C` absent from trusted key source | Rejected |
| R7 — wrong signature | A+B | C | Header says `kid = A`, signed with private key C | Invalid signature; rejected |
| R8 — wrong algorithm | A+B | Incompatible key | `alg` disallowed by API | Rejected |
| R9 — wrong issuer | A+B | A | `iss` differs from configured issuer | Rejected |
| R10 — wrong audience | A+B | A | `aud = billing-api` | Rejected |
| R11 — expired | A+B | A | `exp` in the past | Rejected |
| R12 — insufficient scope | A+B | A | Valid token lacking `orders.read` | Signature/token valid; authorization rejects |

**Crucial note on R5:** A cached copy still holding public key A can continue verifying A signatures mathematically. What keeps old tokens rejected after the grace period is primarily **`exp`**, key-trust policy, and refresh/retirement mechanics. If testing revoking a key *before* tokens expire, you must manage caches or blocklists so every instance stops trusting A as required. Merely deleting A from the JWKS never guarantees every cache instantly forgets A.

## 4. Testing Key Rotation Step by Step

### 4.1. Setup: Two Independent Key Pairs

In tests, generate two distinct RSA key pairs:

~~~text
KeyPair A:
  private A -> signs older JWTs
  public  A -> published via JWKS, kid=key-A

KeyPair B:
  private B -> signs newer JWTs
  public  B -> published via JWKS, kid=key-B
~~~

To keep tests reproducible, give each key a distinct `kid`. **Never use production signing keys in fixtures.** In tests, the mock JWKS exposes only **public keys**, while private keys stay strictly inside the test fixture/process.

### 4.2. Step T0: Verifying Token A

Initial mock JWKS:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "use": "sig",
      "kid": "key-A",
      "alg": "RS256",
      "n": "<A-public-modulus>",
      "e": "AQAB"
    }
  ]
}
~~~

The mock AS mints an RS256 JWS JWT with `kid = key-A` and valid `iss` and `aud`. The Resource Server verifies it, maps `scope = orders.read` to the matching authority, and the protected endpoint runs.

Send two consecutive calls to observe both **initial key fetch** and **cached key hit**. Do not rely solely on HTTP 200; assert the request actually traversed validators and policy, and count JWKS fetches if verifying caching.

### 4.3. Step T1: JWKS Publishes Both A and B Simultaneously

Mock JWKS updates to:

~~~json
{
  "keys": [
    { "kty": "RSA", "use": "sig", "kid": "key-A",
      "alg": "RS256", "n": "<A-public-modulus>", "e": "AQAB" },
    { "kty": "RSA", "use": "sig", "kid": "key-B",
      "alg": "RS256", "n": "<B-public-modulus>", "e": "AQAB" }
  ]
}
~~~

The AS keeps signing with A. Verify A JWTs are not disrupted when B joins the JWKS. This is a vital regression check: adding a key must never invalidate keys that are still active.

Because Resource Servers cache, **updating the mock JWKS payload may not immediately change the key set inside the decoder**. If a test needs to verify post-refresh behavior, control the cache/TTL, trigger a refresh per library behavior, or instantiate a fresh decoder for cache-independent testing.

### 4.4. Step T2: Switch AS to Sign with B

The AS starts issuing JWTs with `kid = key-B`, signed with private key B. The Resource Server must obtain public key B from the trusted source and accept JWT B after full claim validation.

Simultaneously send an **unexpired** A-signed JWT. During the overlap phase, **both A and B JWTs must verify** as long as policy trusts both keys.

This is the highest-value rotation test: proving multiple active keys coexist cleanly as the signer updates.

### 4.5. Step T3: Completing the Transition Window

Once the last A JWT expires and the rotation plan permits, the JWKS retains only B. Test that new B-signed JWTs keep succeeding while expired A JWTs fail. To test **removing A while an A JWT is still unexpired**, treat that as a key-revocation scenario and verify explicitly how caches holding A are handled.

## 5. Key Mismatches: More Than Just an Unknown `kid`

"Key mismatch" failures take several forms. Collapsing them into one test case easily hides security bugs.

### 5.1. `kid` Absent from JWKS

JWKS publishes A and B; the token header says:

~~~json
{"alg": "RS256", "kid": "key-C", "typ": "at+jwt"}
~~~

With no eligible candidate public key, the Resource Server must reject it. Some JWKS clients attempt a refresh on an unseen `kid`; that refresh may contact **only the configured trusted JWKS URI**. If still missing after refresh, verification still fails.

### 5.2. Matching `kid`, Yet Signed by Another Key

The token declares `kid = key-A` but is signed with private key C. This tests far more than an unknown `kid`:

~~~text
JWKS        -> public key A
JWS header  -> kid = key-A
JWS signer  -> private key C
Result      -> verification fails
~~~

If an API only looks up `kid` and trusts claims, this test catches the flaw. `kid` **is not proof** the token was signed by the matching private key.

### 5.3. Matching `kid`, Yet Different Key Material

The JWKS returns a JWK with `kid = key-A` whose `n`/`e` differs from the public key A matching the signer. The signature fails against that key material. This can happen due to misconfiguration, stale caches/proxies, or issuer errors.

**Never "fix" this by skipping signature verification.** Check consistency of the published JWKS, signer cutover timing, caches, and key IDs.

### 5.4. Incompatible Algorithm or Key Type

Cases that must be rejected:

- API expects **RS256**, token claims `alg = HS256`.
- JWT uses `alg = none` where a signed access token is required.
- JWKS has only EC keys while the header requests an incompatible RSA algorithm.
- JWK usage is disallowed for signing by policy, or the header uses an algorithm outside the allowlist.
- Token points to an unconfigured, untrusted JWK source.

The accepted algorithm list must be configured by the Resource Server per issuer contract—**never chosen by the incoming token**. Tests should craft these disallowed JWT formats and verify no trusted `Authentication` is produced.

### 5.5. Valid Signature, Invalid Claims

A JWT validly signed with private key A that has a wrong `iss`, wrong `aud`, past `exp`, or wrong token purpose must still be rejected. Include these in the same suite so you never equate "rotation works" with "security works."

### 5.6. Malformed or Unusable JWKS

Test JWKS returning:

~~~json
{"keys": []}
~~~

or invalid JSON, JWKs missing required fields, unparseable key parameters, ambiguous duplicate keys, or malformed HTTP responses. **The safe outcome is zero signatures trusted when no valid matching key exists.** Depending on implementation, the app may use a valid non-revoked cache entry or raise auth/dependency errors—never mint authorities from an unverified payload.

## 6. Disrupted JWKS Source: Testing Warm Cache vs. Cold Cache

A common misconception is "JWTs are self-contained, so if the Authorization Server goes down, APIs keep running." Asymmetrically signed JWTs **can** be verified locally **when the Resource Server already holds the matching public key**. Fetching keys from JWKS still introduces network dependencies at certain points.

### 6.1. Warm Cache: Public Key Already Present

Scenario:

1. JWKS is healthy and returns public key A.
2. Resource Server verifies JWT A, caching A in its JWKS client.
3. JWKS endpoint starts returning 503 or refuses connections.
4. Client keeps sending unexpired JWT A with valid issuer, audience, and scope.

In many setups, **JWT A continues verifying** while public key A stays in cache and cache policy permits reuse. Exact behavior depends on library, version, TTL, refresh policy, retries, and test timing.

**Never assume caches live forever.** Tests must define cache settings explicitly; once a cache expires or evicts, the decoder needs to fetch JWKS and requests fail.

### 6.2. Cold Cache: Fresh Instance Lacks the Key

Scenario:

1. A brand-new Resource Server starts up without ever having fetched JWKS.
2. JWKS endpoint returns 503, times out, or fails DNS.
3. Client sends an unexpired JWT A.

Without key A from a trusted source, the API cannot verify the signature. The request must **fail closed**. Even if the JSON payload says `scope = orders.read`, never convert it into authorities.

### 6.3. Cache Holds A, New Token Signed with B

Scenario:

1. Resource Server holds only public key A.
2. Authorization Server switches to signing with B.
3. JWKS endpoint goes down.
4. Client sends JWT B with `kid = key-B`.

Lacking matching public key B, the API cannot verify JWT B's signature. This highlights the major risk of failing to pre-publish B or rotating right during an outage.

### 6.4. Cache Holds A, Yet JWKS Already Removed A

This is the inverse case. The updated JWKS publishes only B, while a pod still caches A. Token A may still pass **signature verification** while the cache retains A. Whether accepting it should continue depends on:

- Whether token A is unexpired.
- Whether it is routine rotation or **emergency key revocation**.
- Maximum allowed cache retention duration.
- Whether revocation signals or decoder reconstruction are wired when needed.

**Deleting a key from the endpoint is not enough to prove instant removal across every pod.** Emergency rotation tests must verify your target time-to-stop-accepting-old-key SLA directly rather than guessing.

### 6.5. Outage Matrix for Integration Tests

| Resource Server State | JWKS State | Incoming Token | Expected Outcome |
| --- | --- | --- | --- |
| Cold cache | JWKS healthy | Token A | Fetches A and verifies |
| Cold cache | JWKS 503/timeout | Token A | Cannot verify without key |
| Warm cache with eligible A | JWKS 503/timeout | Unexpired Token A | Can verify per cache policy |
| Warm cache with A only | JWKS 503/timeout | Token B | Cannot verify B |
| Cache A+B | JWKS 503/timeout | Unexpired Token A/B | Can verify if cache use permitted |
| Cache expired/evicted | JWKS 503/timeout | Previously valid token | Fails due to no usable key |
| Cache A, JWKS just removed A | JWKS healthy | Unexpired Token A | Depends on cache/retirement policy; does not automatically fail instantly |
| Cache B, JWKS healthy | Token A bad signature / A absent | Token A | Must reject when no trusted key A exists |

**What to measure:** not only HTTP response codes, but also JWKS HTTP GET counts, wait times, cache hit/miss ratios if exposed, key IDs used, retry counts, and behavior when a new key appears.

## 7. Resource Server Startup When Discovery or JWKS Is Down

Two endpoints serve two distinct goals:

- **Issuer discovery:** retrieves metadata, including JWKS URI, from the issuer.
- **JWKS retrieval:** fetches public keys for JWT checking.

Example Spring Boot config:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}
~~~

When `jwk-set-uri` is provided directly, the application can avoid contacting the metadata endpoint just to *locate the keys* during initialization, while still validating the issuer. Still, `jwk-set-uri` **does not mean keys are pre-loaded**; the first request may still call the JWKS endpoint.

With `issuer-uri` alone, depending on version and decoder setup, issuer discovery may happen at startup or lazily. Test your exact Spring Boot/Spring Security version instead of inferring startup behavior from property names.

### Three Useful Startup Tests

1. **Issuer URI only, metadata unreachable:** observe how the decoder/app initializes and at which step the first request fails.
2. **Explicit Issuer URI + JWKS URI, metadata unreachable:** confirm discovery is not required to locate JWKS while `iss` is still validated.
3. **Explicit JWKS URI, JWKS endpoint down:** confirm startup and request verification are separate phases; the app may boot, yet incoming requests fail verification.

Never resolve outages by disabling signature validators. The aim is clarifying dependencies and key-fetch timing to build proper availability strategies.

## 8. Configuring Spring Security to Validate JWTs and Audience

Example with **Spring Boot 3 / Spring Security 6**, Orders API using signed JWTs:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
}
~~~

`application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    audience: ${OAUTH_API_AUDIENCE}
~~~

Example environment values:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
OAUTH_API_AUDIENCE=orders-api
~~~

These URIs are illustrative; use the exact endpoints published by your trusted issuer.

### 8.1. Decoder Enforcing Signature, Issuer, Audience, and Lifetime

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class JwtVerificationConfig {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder = NimbusJwtDecoder
                .withJwkSetUri(jwksUri)
                // Example where the issuer contract uses RS256.
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> standard =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audience = jwt ->
                jwt.getAudience().contains(expectedAudience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Token has an unexpected audience",
                            null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(standard, audience));
        return decoder;
    }
}
~~~

This code does not perform manual rotation; **`NimbusJwtDecoder`** fetches keys from the configured JWKS endpoint to verify JWS signatures via library-supported mechanics. Exact fetch/refresh/cache/timeout behaviors must be verified on your running version. `JwtValidators.createDefaultWithIssuer` retains default JWT and issuer checks; the additional validator ensures the audience matches the Orders API.

If the issuer uses another algorithm or requires a broader set of allowed algorithms, configure it **strictly per the issuer contract**—never treat an untrusted token's `alg` as policy.

### 8.2. Map Permissions Only After Verification Succeeds

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This assumes `/api/**` is a REST API authenticated solely by Bearer tokens, so CSRF is disabled on this filter chain. If serving browsers with cookies/sessions, configure CSRF and separate filter chains appropriately. Scope `orders.read` gates calling the endpoint; reading **a specific order** still requires owner/tenant checks in the business service.

**Inviolable boundary during JWKS downtime:** if `JwtDecoder` fails, never synthesize a fake `Authentication` with `SCOPE_orders.read` just to let the request "proceed." Endpoints must reject unverified tokens.

## 9. Building a Controllable JWKS Test Environment

Never test rotation/outages against production JWKS. Use an **HTTP mock server** whose JWK set and HTTP responses you control per scenario—typically **OkHttp MockWebServer** or **WireMock** in integration tests.

Fixture components:

~~~text
Test issuer       = https://issuer.example.test (claim value)
Local JWKS URL    = http://127.0.0.1:<random-port>/jwks
RSA private key A = test-only old signer
RSA public  key A = JWKS entry kid=key-A
RSA private key B = test-only new signer
RSA public  key B = JWKS entry kid=key-B
JWT audience      = orders-api
JWT scope         = orders.read
~~~

**The issuer claim can be a logical URI** in tests while the JWKS HTTP endpoint runs on localhost, as long as the decoder is configured separately with issuer and JWKS URI; never use this trick to drop issuer validation in production. When testing metadata discovery end-to-end, mock metadata must declare consistent `issuer` and `jwks_uri` per contract.

### 9.1. Generating Real JWKs and Signed JWTs for Fixtures

In Java, use **Nimbus JOSE + JWT** (used under the hood by Spring Security) to generate key pairs and sign test tokens. Example test helper:

~~~java
import java.time.Instant;
import java.util.Date;
import java.util.List;

import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;

final class TestJwtKeys {

    static RSAKey newRsaKey(String kid) throws Exception {
        return new RSAKeyGenerator(2048)
                .keyID(kid)
                .generate();
    }

    static String publicJwks(RSAKey... keys) {
        return new JWKSet(
                java.util.Arrays.stream(keys)
                    .map(RSAKey::toPublicJWK)
                    .toList())
                .toString();
    }

    static String signedAccessToken(
            RSAKey signingKey,
            String issuer,
            String audience,
            String subject) throws Exception {

        Instant now = Instant.now();

        JWTClaimsSet claims = new JWTClaimsSet.Builder()
                .issuer(issuer)
                .subject(subject)
                .audience(audience)
                .issueTime(Date.from(now))
                .notBeforeTime(Date.from(now.minusSeconds(5)))
                .expirationTime(Date.from(now.plusSeconds(300)))
                .claim("scope", "orders.read")
                .build();

        JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
                .keyID(signingKey.getKeyID())
                .type(new JOSEObjectType("at+jwt"))
                .build();

        SignedJWT jwt = new SignedJWT(header, claims);
        jwt.sign(new RSASSASigner(signingKey.toPrivateKey()));
        return jwt.serialize();
    }

    private TestJwtKeys() {}
}
~~~

This helper produces **genuinely RSA-signed tokens**, not mere JSON or Base64URL stubs. When testing key mismatches, generate an independent private key C, set `kid = key-A` in the JWT header, and sign with C; this verifies the Resource Server **actually checks signatures**.

Because the snippet uses `Stream.toList()`, it assumes **Java 16+**; older Java versions can substitute `Collectors.toList()`. Generated keys are strictly for test fixtures and must never be committed to repositories as shared private keys.

### 9.2. Mocking the JWKS Endpoint: Swapping Key Sets and Simulating Failures

HTTP fixture pseudocode example:

~~~java
// Illustrative pseudocode; exact API names depend on MockWebServer/WireMock.
setJwksResponse(200, publicJwks(keyA));          // T0
assertAccepted(sign(keyA, "key-A"));

setJwksResponse(200, publicJwks(keyA, keyB));    // T1
refreshJwksAccordingToTestCachePolicy();
assertAccepted(sign(keyA, "key-A"));

assertAccepted(sign(keyB, "key-B"));              // T2
assertAccepted(sign(keyA, "key-A"));              // Grace period

setJwksResponse(503, "Service Unavailable");     // Outage
assertNeverAcceptedIfSignatureCannotBeVerified();
~~~

This pseudocode **is not runnable as-is**; helpers like `refreshJwksAccordingToTestCachePolicy()` depend on your chosen library and cache setup. The goal is decoupling **JWKS server state** from **decoder cache state** so each test explicitly controls and records the state under test.

### 9.3. Minimal Integration Test Using MockWebServer

A runnable test example using **JUnit Jupiter, OkHttp MockWebServer, and Nimbus JOSE/JWT** once the corresponding test dependencies are added:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import com.nimbusds.jose.jwk.RSAKey;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jose.jws.SignatureAlgorithm;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtException;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

class JwksVerificationTest {
    private static final String ISSUER =
            "https://issuer.example.test";
    private static final String AUDIENCE = "orders-api";

    private MockWebServer jwksServer;
    private RSAKey keyA;
    private NimbusJwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        keyA = TestJwtKeys.newRsaKey("key-A");
        jwksServer = new MockWebServer();
        jwksServer.start();

        decoder = NimbusJwtDecoder
                .withJwkSetUri(jwksServer.url("/jwks").toString())
                .jwsAlgorithm(SignatureAlgorithm.RS256)
                .build();

        OAuth2TokenValidator<Jwt> expectedAudience = jwt ->
                jwt.getAudience().contains(AUDIENCE)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                            new OAuth2Error(
                                "invalid_token",
                                "wrong audience",
                                null));
        decoder.setJwtValidator(new DelegatingOAuth2TokenValidator<>(
                JwtValidators.createDefaultWithIssuer(ISSUER),
                expectedAudience));
    }

    @AfterEach
    void tearDown() throws Exception {
        jwksServer.shutdown();
    }

    @Test
    void acceptsTokenSignedWithTrustedKey() throws Exception {
        jwksServer.enqueue(new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(TestJwtKeys.publicJwks(keyA)));

        String token = TestJwtKeys.signedAccessToken(
                keyA, ISSUER, AUDIENCE, "user-42");

        Jwt verified = decoder.decode(token);
        assertEquals("user-42", verified.getSubject());
    }

    @Test
    void rejectsTokenSignedWithDifferentPrivateKey() throws Exception {
        jwksServer.enqueue(new MockResponse()
                .setResponseCode(200)
                .setHeader("Content-Type", "application/json")
                .setBody(TestJwtKeys.publicJwks(keyA)));

        // Physically different key from A reusing the same kid to test signature verification.
        RSAKey fakeA = TestJwtKeys.newRsaKey("key-A");
        String forged = TestJwtKeys.signedAccessToken(
                fakeA, ISSUER, AUDIENCE, "user-42");

        assertThrows(JwtException.class,
                () -> decoder.decode(forged));
    }

    @Test
    void refusesColdCacheWhenJwksIsUnavailable() throws Exception {
        jwksServer.enqueue(new MockResponse()
                .setResponseCode(503));

        String token = TestJwtKeys.signedAccessToken(
                keyA, ISSUER, AUDIENCE, "user-42");

        assertThrows(JwtException.class,
                () -> decoder.decode(token));
    }
}
~~~

This is an **illustrative example** using common JUnit/MockWebServer/Nimbus APIs; real projects must declare matching test dependencies and adjust packages/APIs if needed. The three tests cleanly separate: **valid key**, **matching `kid` with wrong signature**, and **unreachable JWKS on a cold cache**.

In a full rotation suite, add an HTTP mock that updates responses mid-test and controls decoder caching. Never write assertions assuming JWKS refreshes on the exact first request without knowing your version's cache policy.

### 9.4. Testing the HTTP API Instead of Just the Decoder

`JwtDecoder` tests focus on token validation. At the HTTP layer, use `MockMvc` or an HTTP test client with **real signed JWTs** to prove invalid tokens are rejected **before** reaching controllers. Example matrix:

~~~text
GET /api/orders/42
  Token signed A, right issuer/aud/scope -> passes JWT/scope layer;
                                            data policy decides next
  Token with bad signature               -> authentication fails
  Valid signature, wrong aud             -> authentication fails
  Valid token, missing scope             -> authentication succeeds,
                                            authorization fails
~~~

For OAuth2-protected API tests, **`SecurityMockMvcRequestPostProcessors.jwt()`** is handy for testing authority mapping or endpoint rules **without** signatures. However, it **cannot replace** real JWS/JWKS/rotation tests because it injects an authentication into the test request without exercising signature verification like a production Bearer token.

To test rotation or mismatches, send **real signed Bearer JWTs** through the filter chain using the configured decoder, or test the decoder directly with signed tokens as shown above.

## 10. Interpreting Failures During Testing

Errors can look identical at the HTTP layer while coming from very different sources:

| Symptom | Likely Cause | How to Distinguish |
| --- | --- | --- |
| Unknown `kid` | JWT signed with new key, stale JWKS, or forged token | Cross-check `kid` against trusted issuer's JWKS and rotation schedule |
| Signature mismatch | Signing private key does not match public JWK; tampered token | Verify signer and public key; do not look at `kid` alone |
| Unsupported `alg` | Token declares an off-allowlist algorithm or wrong key type | Inspect decoder's algorithm policy |
| HTTP 404/500/503 on JWKS | Wrong endpoint or dependency failure | Check URL, network, server logs, and status codes |
| Timeout/DNS/TLS error | Unable to fetch keys from trusted source | Check DNS, CA/truststore, network policies, and timeouts |
| Invalid JWKS JSON | Malformed response or unparseable keys | Inspect JWK shape, JSON, Content-Type, and parser logs |
| Token expired | `exp` in the past | Check timestamps, clock skew, and lifetime |
| Invalid issuer/audience | Token not intended for this environment/API | Check `iss`/`aud` and per-environment config |
| Insufficient scope | Valid JWT lacking required authority | Check `scope`/`scp` mapping and endpoint rules |

With Bearer authentication, **invalid tokens** typically yield **401 Unauthorized**. Valid tokens **lacking permissions** typically yield **403 Forbidden**. However, **failing to fetch JWKS** is a dependency/network failure; exact HTTP status can vary by version, exception mapping, and configuration. In tests, assert **no protected operation executes** while classifying the error in decoder/observability logs—never blindly hardcode that every outage must return the exact same 401.

### 10.1. Logs You Should Emit

For diagnostics, record:

- Request/correlation ID, instance/pod ID, and endpoint.
- JWKS reachability status, fetch latency, network errors, and HTTP status codes.
- **Configured** issuer/JWKS URI; treat `kid` and `alg` from the token as **untrusted inputs** until verified.
- Failure category: unknown key, invalid signature, issuer mismatch, audience mismatch, expired token, insufficient scope.
- JWKS refresh counts and cache hits/misses if exposed by libraries or instrumentation.

**Never log raw access tokens**, private signing keys, client secrets, or unnecessary claims. When using `kid` in logs or metrics, bound length and cardinality because unverified tokens can carry attacker-chosen `kid` values leading to cardinality explosions or log injection if unsanitized.

## 11. Key Rotation and Caching: Assumptions to Avoid

### 11.1. Never Hardcode One Fixed TTL Across Versions

Never write tests assuming:

~~~text
JWKS is definitely cached for 5 minutes.
After exactly 5 minutes every pod must refresh.
On an unknown kid every Nimbus version immediately fetches JWKS.
~~~

Cache lifetimes, miss-refresh policies, HTTP cache headers, retries, and eager vs. lazy fetching are **implementation details**. They vary across Spring Security versions, Nimbus JOSE/JWT versions, decoder setups, and custom caches.

When testing:

1. Identify exact running library versions.
2. Fix the cache mechanism in test fixtures where determinism is needed.
3. When simulating a stale cache, **ensure cache A was actually warmed first**.
4. When simulating a cold cache, use a **fresh decoder/instance**.
5. When simulating refreshes, observe/control requests hitting the mock JWKS.
6. Verify behavior under cache expiry, missing keys, and network timeouts.

### 11.2. Never Assume Removing a Key from JWKS Immediately Invalidates Old Tokens

Tokens with `kid = key-A` can keep verifying against cached public key A even after the JWKS endpoint stops publishing A. In routine rotation this is sometimes expected; in a key compromise incident, it is a major risk.

An **emergency key revocation** plan may require:

- Disabling signing with private key A on the Authorization Server.
- Stopping trust in A on Resource Servers via forced cache refreshes, decoder reconfiguration, pushed key denylists, or equivalent pre-built controls.
- Revoking related credentials and auditing issued tokens.
- Monitoring every pod and region to confirm none still accept A out of policy.

There is no instant revocation guarantee from editing a JWKS entry alone. Test this end-to-end against your organization's target SLA.

### 11.3. Multiple Concurrent Instances

In a 10-pod deployment, each pod can hold different cache states and JWKS refresh schedules:

~~~text
Pod 1: cache A+B  -> accepts token B
Pod 2: cache A    -> must refresh upon seeing B
Pod 3: empty cache, JWKS down -> cannot verify
Pod 4: cache A+B but expired -> depends on refresh/cache policy
~~~

Staging tests should therefore exercise **rolling restarts**, **autoscaling**, **multi-region**, **restarts mid-rotation**, and **outages coinciding with key B activation**. A single-JVM test cannot prove cross-instance cache drift is under control.

## 12. Recommended Testing Pipeline for CI and Staging

### Tier 1 — Unit Tests for Validation Logic

Focus on:

- Audience must contain `orders-api`.
- Issuer must match the trusted issuer.
- Token is unexpired and `nbf` is valid.
- Scopes map cleanly to `SCOPE_orders.read`.
- ID tokens are rejected as OAuth2 access tokens per profile.

These tests do not need real JWKS because they target validators and authorization rules.

### Tier 2 — Decoder Integration Tests with Local JWKS

Use **real signed JWTs**, a mock JWKS, and cases R1–R12. Include scenarios for:

- Key B pre-published, then AS switches to signing with B.
- Both A and B tokens valid simultaneously during the grace period.
- Missing key / bad signature / wrong `alg`.
- JWKS returning 503, timing out, or returning malformed JSON.
- Cold cache vs. warm cache holding the matching key.

When testing time bounds, inject a controllable clock into application policy or craft JWTs with deliberately near/far `exp` values—avoid long `Thread.sleep` calls and flaky race conditions.

### Tier 3 — Filter Chain Tests

Send real HTTP Bearer JWTs to the Spring Security Resource Server:

~~~text
Valid JWT + scope + valid data permissions -> 2xx
Invalid signature                          -> rejected before controller
Unknown kid, no trusted key                -> rejected
Wrong issuer/audience                      -> rejected
Valid JWT missing scope                    -> 403 per security config
Valid JWT with scope, wrong owner          -> 403/404 per data policy
~~~

Tests must guarantee controllers/services never receive a trusted `Authentication` when the JWT signature is invalid, even while the JWKS endpoint is down.

### Tier 4 — Staging Fault Injection

In staging, simulate:

1. Key A active with warm caches across pods.
2. Blocking the JWKS endpoint with a network fault or 503s.
3. Sending unexpired token A and never-published token B.
4. Observing old/new pods and retries.
5. Restoring JWKS, pre-publishing B, and switching signing to B.
6. Running rolling restarts/autoscaling.
7. Removing A after the grace period, or running an emergency rotation drill in isolation.

Remember: **never induce real outages in production** just to test these lessons. Staging must have dedicated signing keys, tokens, and data—never use production private keys to build tests.

### 12.1. Evidence Checklist to Retain

| Evidence | Contents |
| --- | --- |
| Versions | Spring Boot, Spring Security, Nimbus/JWK client, test libraries |
| Scenarios | JWKS A/A+B/B, signer A/B/C, cache states, outages |
| Token contract | Issuer, audience, algorithms, lifetime, scopes |
| Outcomes | Tokens accepted vs. rejected, failure stage |
| Telemetry | JWKS HTTP request counts, latency, timeouts, error categories, pods |
| Recovery | Whether valid new tokens verify once JWKS recovers or caches refresh |
| Security invariant | Zero unverified tokens permitted past policy |

Keep evidence **free of private keys and raw Bearer tokens**. Recording test `kid`s, validator outcomes, and request IDs is fine per internal policy.

## 13. Runbook When Key Rotation or JWKS Fails

### Case 1 — New Tokens Return 401 Right After Rotation

Check in order:

1. Which `kid` and algorithm are in the new token? This is untrusted until verified, yet narrows down where to look.
2. Does the API's configured JWKS publish the matching public key?
3. Does the key material actually match the new signing private key?
4. Did the failing pod refresh its JWKS, or does it still hold a stale cache?
5. Are token issuer, audience, and lifetime valid?
6. Did the AS switch signers **before** B was pre-published and APIs had time to refresh caches?

If the root cause is an unpublished key or unrefreshed cache, fix the rotation sequence or JWKS reachability. **Never disable JWS verification** to let tokens through temporarily.

### Case 2 — Same Token Works on Pod A, Fails on Pod B

Likely diverging cache states, though still verify from decoder logs. Check:

- Startup/restart times of each pod.
- Most recent JWKS GET, result, and cache expiration.
- Token `kid`/algorithm, plus issuer/JWKS/audience config on both pods.
- Network routes, TLS truststores, and DNS between each pod and the JWKS endpoint.

Do not conclude a token was tampered with solely because one instance passes and another fails.

### Case 3 — JWKS Temporarily Down

1. Determine whether the endpoint itself is down or DNS/TLS/firewall/proxy failed.
2. Identify which instances still hold eligible cached keys per policy.
3. Keep signature and claim checks active; **never fail open**.
4. Curb retry storms with proper timeouts and backoff.
5. Monitor 401/dependency errors and new tokens carrying unseen `kid`s.
6. Once the endpoint recovers, monitor key refreshes and verification recovery.

**Warm caches can sustain verification for some JWTs**, yet this is never a reason to permit unknown tokens or extend token lifetimes.

### Case 4 — Suspected Private Key Compromise

This is an **emergency rotation**, not a routine cycle:

- Stop signing new tokens with the suspected key and generate a replacement key per key-governance procedures.
- Coordinate across AS, Resource Servers, configuration distribution, and incident response to drop trust in the old key within target SLAs.
- Assess already-issued tokens and impact on users and clients.
- Verify every pod and region stops accepting forged JWTs signed with the revoked key.
- Monitor outcomes and audit root cause, key-access logs, and operational permissions.

Never assume deleting a public JWK from the endpoint instantly revokes all signed JWTs; handle caches and instance state explicitly in the plan.

## 14. Misconceptions to Avoid

**"`kid` matches, so the signature is valid."** False. `kid` is only a key-lookup hint; a token declaring `kid = A` yet signed with C must be rejected.

**"Once we switch signing to B, we can delete A immediately."** In routine rotation, unexpired A tokens still need public key A. You need a grace period and retirement plan.

**"If JWKS returns 503, just trust payload claims to authorize requests."** False. Without signature verification, `sub`/`scope`/`roles` are merely caller-supplied assertions.

**"JWTs verify offline, so JWKS outages don't need testing."** False. Fresh instances, cold caches, and tokens using new keys depend on JWKS.

**"Removing A from JWKS stops every API from trusting A immediately."** Not guaranteed. Stale caches may retain A; emergency revocation must be designed and tested separately.

**"Verifying the JWT signature is enough to secure the API."** Insufficient. You still need issuer, audience, lifetime, token profile, scopes, and per-resource permissions.

**"Testing with Spring MockMvc `jwt()` tests JWKS."** False. Authentication/authorization test helpers do not exercise real signed Bearer JWTs flowing through a real `JwtDecoder`.

**"One successful JWKS retry proves rotation is safe."** Insufficient. Test cold/warm caches, overlapping unexpired A+B tokens, multiple pods, and outages overlapping rotation.

**"Allowing whatever algorithm the token declares is more flexible."** Unsafe. Resource Servers must allowlist only trusted configured algorithms to prevent algorithm confusion.

**"Reusing the same `kid` across different keys is fine."** Causes ambiguous key selection and operational headaches. Maintain unique key identifiers and verify signatures with the right key material.

## 15. Scenario Exercises

**Scenario A:** JWKS holds A+B, and the AS signs new tokens with B; the Resource Server caches only A. Token B fails initially but succeeds once the decoder refreshes JWKS. Is this a security vulnerability?

Not necessarily. It shows **refresh/cache timing** affects availability. Ensure zero unverified tokens are accepted and design pre-publish/caching cleanly to avoid avoidable 401s.

**Scenario B:** A JWT header declares `kid = A` yet is signed with private key C. JWKS publishes public key A. What must the API do?

Reject due to signature mismatch. `kid` never substitutes for a valid signature.

**Scenario C:** JWKS is down; Pod A holds usable cached A while Pod B just booted with an empty cache. The same unexpired JWT A works on A yet fails on B. Why?

The key is **per-instance key state**. A can verify locally; B lacks the public key and cannot fetch it. Inspect startup/cache/network behavior—never skip verification on B.

**Scenario D:** After a suspected private key A leak, the AS drops A from JWKS. Some pods keep accepting A-signed tokens due to caching. Can revocation be declared complete?

Not yet. You need mechanisms to stop trusting A across all Resource Servers within target SLAs, verify across pods/regions, and assess already-issued tokens.

**Scenario E:** A JWT is validly signed with B, yet carries `aud = payments-api`. What must the Orders API do?

Reject for audience mismatch. A valid signature proves only that the token matches a trusted signing key—not that it is meant for the Orders API.

**Scenario F:** A test uses `MockMvc.jwt()` with `scope = orders.read`, gets 200, and concludes JWKS rotation works. Is that conclusion valid?

No. `MockMvc.jwt()` is a convenience helper for testing request-level security rules; it never proves the decoder fetched a JWK or verified a real token signature. Write integration tests with signed JWTs and a real/mock JWKS endpoint.

---

**Takeaway:** To test the JWK lifecycle in a Spring Security Resource Server, generate **at least two key pairs A/B**, mint real signed JWTs, use a **controllable JWKS mock capable of swapping key sets and simulating 5xx/timeouts**, and step through **pre-publish → switch signer → grace period → retire key**. Add tests for **unknown `kid`, same `kid` with wrong signature, wrong algorithm, wrong issuer/audience, cold/warm caches, and outages**. A system behaves securely when valid tokens remain accepted under designed conditions while every unverifiable token is **rejected without bypassing JWT validation or authorization**.
