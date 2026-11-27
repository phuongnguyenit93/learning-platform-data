# Rotating Keys in a Test Environment While Old Tokens Are Still Valid

## 1. The Problem: Swapping Signing Keys Without Breaking Active Tokens

JWT access tokens are signed with the Authorization Server's (AS) private key. The Resource Server (RS) fetches public keys from the JWKS endpoint to verify signatures. When the AS rotates signing keys, new tokens are signed with the new key while tokens already issued with the old key may still be unexpired.

Suppose the AS is currently signing with key **K1**. An application just received access token T1, valid for another 12 minutes. Then operations wants to switch to key **K2**. If public key K1 is removed from JWKS the moment signing switches to K2, an RS that has not cached K1 or just refreshed JWKS will fail to verify T1. Users holding valid, unexpired tokens will receive `401`.

Standard key rotation publishes the new public key first, keeps both old and new public keys during an overlap window, switches the AS to sign with the new key, and removes the old key only after tokens signed by it are no longer valid.

In this practical exercise, we simulate the process using two RSA key pairs, a test JWKS endpoint, and a Spring Security JWT decoder. We test both old and new tokens during the overlap period, simulate retiring the old key, and observe the difference between a decoder with a cached key and a fresh instance.

**Key principle:** unexpired old tokens must continue to verify during a normal rotation. Changing the signing key does not automatically expire old tokens, nor does it revoke them.

### Learning Objectives

After this lesson, you will be able to:

1. Explain the relationship between private signing keys, public verification keys, `kid`, and JWKS.
2. Plan the timeline to publish, overlap, switch, and retire a key.
3. Generate two RSA key pairs for a test environment.
4. Stand up a JWKS endpoint whose contents can be changed during tests.
5. Issue an old token with K1 and a new token with K2.
6. Use the same `JwtDecoder` to verify tokens across the rotation phases.
7. Understand JWKS caching and behavior when a decoder encounters an unknown `kid`.
8. Test unexpired old tokens, expired tokens, and tokens using a retired key.
9. Simulate multiple Resource Server instances with different caches.
10. Distinguish scheduled rotation from emergency response when a private key is compromised.

---

## 2. Components in the Lab

### 2.1. Diagram

~~~mermaid
flowchart TD
    AS[Test Authorization Server] -->|Sign new token with K2| T2[New access token]
    AS -->|Previously issued with K1| T1[Old access token]
    JWKS[Test JWKS endpoint] -->|Public K1 + K2| RS1[Resource Server A]
    JWKS -->|Public K1 + K2| RS2[Resource Server B]
    T1 --> RS1
    T2 --> RS1
    T1 --> RS2
    T2 --> RS2
    RS1 --> V1[Signature + issuer + audience + time]
    RS2 --> V2[Signature + issuer + audience + time]
~~~

The AS holds private keys for signing. JWKS publishes only public keys. The RS does not need and must never receive the AS's private keys.

In the lab, a test process acts as the AS and a local HTTP server acts as the JWKS endpoint. This makes changing the public key list controllable. Never use real private keys or production endpoints in tests.

### 2.2. Fixed Values

Use a single issuer and a single audience throughout the lab:

~~~text
Issuer:
https://issuer.test.example

Audience:
orders-api

JWKS URI:
http://127.0.0.1:<test-port>/jwks

Old key:
kid = rsa-key-1

New key:
kid = rsa-key-2

Algorithm:
RS256
~~~

The JWKS URI uses HTTP loopback solely to simplify local testing. Real environments must use HTTPS, verify TLS certificates, and manage the endpoint via trusted configuration.

The issuer does not change during rotation. Neither does the audience. Rotating signing keys only changes the key used for signing and the set of published public keys.

### 2.3. Initial State Before Starting

Initially:

- The AS signs tokens with K1.
- JWKS contains public K1.
- The RS may already have fetched public K1.
- Token T1 is signed with private K1 and is unexpired.
- K2 has been generated in the lab but not yet published.

| Component | Initial state |
|---|---|
| AS active signing key | K1 |
| JWKS | K1 |
| Resource Server cache | May contain K1 |
| Token T1 | Signed with K1, unexpired |
| K2 | Not yet published |

---

## 3. Proper Rotation Timeline

### 3.1. Four Phases

~~~mermaid
sequenceDiagram
    participant AS as Authorization Server
    participant J as JWKS endpoint
    participant RS as Resource Server
    participant C as Client

    Note over AS,J: Phase 1: K1 is active
    AS->>C: Issue T1 signed with K1
    C->>RS: Call API with T1
    RS->>J: Fetch JWKS containing K1
    RS-->>C: API response

    Note over AS,J: Phase 2: Publish K2, keep K1
    AS->>J: Publish K1 + K2
    RS->>J: Refresh JWKS
    Note over RS: RS can verify both K1 and K2

    Note over AS,J: Phase 3: Switch signer
    AS->>C: Issue T2 signed with K2
    C->>RS: Call API with T2
    RS-->>C: API response
    C->>RS: Call API with unexpired T1
    RS-->>C: API response

    Note over AS,J: Phase 4: Retire K1 after overlap
    AS->>J: Remove K1, keep only K2
    RS->>J: Refresh per cache policy
~~~

The process consists of:

1. **Publish:** add public K2 into JWKS alongside public K1.
2. **Warm-up/propagation:** allow RS instances to pick up K2.
3. **Switch:** AS starts signing new tokens with private K2.
4. **Retire:** remove public K1 after tokens signed with K1 are past their validity window.

Do not remove K1 in the publish step. Also do not start signing with K2 before public K2 is published and RS instances have had a chance to receive the new key.

### 3.2. Calculating When to Remove the Old Key

A conservative calculation:

\[
t_{remove(K1)} \geq t_{lastIssue(K1)} + maxTokenLifetime + clockSkew + propagationMargin
\]

Where:

- **`t_lastIssue(K1)`:** the last timestamp when the AS issued a token with K1.
- **`maxTokenLifetime`:** the maximum access token lifetime that can be issued with K1.
- **`clockSkew`:** clock skew tolerance allowed by the RS.
- **`propagationMargin`:** buffer for caches, multiple instances, and deployment propagation.

If the system tracks the maximum expiration timestamp across all tokens issued with K1, you can use that timestamp instead of the conservative calculation from the last issuance time:

\[
t_{remove(K1)} \geq max(exp_{K1}) + clockSkew + propagationMargin
\]

Do not rely solely on a client's default TTL. Calculate from the actual token policy, including refresh flows that may continue issuing access tokens with K1 until the AS switches signers.

### 3.3. Timeline Example

Suppose:

| Event | Illustrative time |
|---|---|
| AS issues last token with K1 | 10:00 |
| Maximum access-token lifetime | 20 minutes |
| Allowed clock skew | 60 seconds |
| Propagation/cache margin | 5 minutes |
| Earliest time to retire K1 | After 10:26 |

These numbers are illustrative. Real systems must pull maximum lifetime and clock skew from active configuration. If the AS still issues any K1 token after 10:00, recalculate the cutoff.

### 3.4. Old Tokens Are Not Re-Signed Automatically

T1 was already signed with K1. When the AS switches to K2:

- T1 still retains K1's signature.
- T1 still carries K1's `kid`.
- T1 remains valid until `exp`, provided other conditions hold.
- T2 is signed with K2 and carries K2's `kid`.

Nothing replaces T1's signature with a K2 signature. If you want old tokens to stop working immediately, you need a revocation/denylist mechanism or shorter lifetimes by design; merely rotating the active signing key is not enough.

---

## 4. Preparing the Test Project

### 4.1. Dependencies

Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Spring Security OAuth2 JOSE uses Nimbus JOSE + JWT for JWT/JWK processing. If test code imports Nimbus classes directly but the build does not expose the dependency through the active module, declare the matching test dependency aligned with your project's BOM instead of pinning an incompatible version.

Common Nimbus imports:

~~~java
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.JOSEObjectType;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.KeyUse;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
~~~

### 4.2. Generating Two RSA Key Pairs

In tests, generate K1 and K2 independently:

~~~java
static KeyPair generateRsaKeyPair() throws GeneralSecurityException {
    KeyPairGenerator generator = KeyPairGenerator.getInstance("RSA");
    generator.initialize(2048);
    return generator.generateKeyPair();
}

KeyPair keyPair1 = generateRsaKeyPair();
KeyPair keyPair2 = generateRsaKeyPair();
~~~

Each key pair consists of:

- Private key: used only in tests to sign tokens.
- Public key: placed into JWKS for the Resource Server to verify signatures.

Do not reuse the same key pair under two `kid`s. `kid` must distinguish two distinct keys.

### 4.3. Creating Public JWKs

~~~java
static RSAKey publicJwk(KeyPair pair, String kid) {
    return new RSAKey.Builder((RSAPublicKey) pair.getPublic())
        .keyID(kid)
        .algorithm(JWSAlgorithm.RS256)
        .keyUse(KeyUse.SIGNATURE)
        .build();
}

RSAKey publicKey1 = publicJwk(keyPair1, "rsa-key-1");
RSAKey publicKey2 = publicJwk(keyPair2, "rsa-key-2");
~~~

JWKS contains only public JWKs:

~~~java
String jwksWithK1 = new JWKSet(publicKey1).toString();

String jwksWithBoth = new JWKSet(
    List.of(publicKey1, publicKey2)
).toString();

String jwksWithK2 = new JWKSet(publicKey2).toString();
~~~

Never call `toJSONString`/`toString` on a JWK containing a private key to build a JWKS response. Construct a public JWK from the public key alone or call `toPublicJWK()` before serializing.

---

## 5. Standing Up a Mutable Local JWKS Endpoint

### 5.1. Why Is a Dynamic Endpoint Needed?

To test rotation, we need to change the JWKS response across phases:

- Initially return K1.
- During overlap return K1 and K2.
- After retirement return only K2.

A test HTTP endpoint lets us update the JWKS payload via an `AtomicReference`. The Nimbus decoder fetches JWKS from that URL according to the library's caching behavior.

### 5.2. Example with JDK `HttpServer`

The following is a test fixture using JDK `HttpServer`:

~~~java
import com.sun.net.httpserver.HttpServer;
import java.net.InetSocketAddress;
import java.nio.charset.StandardCharsets;
import java.io.OutputStream;
import java.util.concurrent.atomic.AtomicReference;

AtomicReference<String> currentJwks =
    new AtomicReference<>(jwksWithK1);

HttpServer jwksServer = HttpServer.create(
    new InetSocketAddress("127.0.0.1", 0),
    0
);

jwksServer.createContext("/jwks", exchange -> {
    byte[] body = currentJwks.get()
        .getBytes(StandardCharsets.UTF_8);

    exchange.getResponseHeaders().set(
        "Content-Type",
        "application/jwk-set+json"
    );

    exchange.sendResponseHeaders(200, body.length);

    try (OutputStream output = exchange.getResponseBody()) {
        output.write(body);
    }
});

jwksServer.start();

String jwksUri =
    "http://127.0.0.1:" +
    jwksServer.getAddress().getPort() +
    "/jwks";
~~~

Always stop the server after tests:

~~~java
@AfterEach
void stopJwksServer() {
    if (jwksServer != null) {
        jwksServer.stop(0);
    }
}
~~~

In modular projects, JDK `HttpServer` lives in module `jdk.httpserver`. If your test module descriptor does not read that module, declare it or use a mock HTTP server already in the project.

### 5.3. Updating JWKS Across Phases

~~~java
// Initial state
currentJwks.set(jwksWithK1);

// Publish K2 while keeping K1
currentJwks.set(jwksWithBoth);

// After overlap ends
currentJwks.set(jwksWithK2);
~~~

Changing the endpoint response does not mean every RS instance immediately sees the new content. Decoders may keep JWKS in cache. The lab must test cache hits, cache misses, and fresh instances.

---

## 6. Issuing Tokens with Each Key

### 6.1. Creating a JWT with an Explicit `kid`

An access token needs an issuer, subject, audience, timestamps, and scope. The header needs a `kid` pointing to the key used to sign it.

~~~java
static String issueToken(
        KeyPair signingKey,
        String kid,
        Instant expiresAt) throws Exception {

    Instant now = Instant.now();

    JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
        .keyID(kid)
        .type(JOSEObjectType.JWT)
        .build();

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
        .issuer("https://issuer.test.example")
        .subject("user-417")
        .audience("orders-api")
        .issueTime(Date.from(now.minusSeconds(5)))
        .expirationTime(Date.from(expiresAt))
        .claim("scope", "orders.read")
        .build();

    SignedJWT jwt = new SignedJWT(header, claims);

    jwt.sign(new RSASSASigner(
        (RSAPrivateKey) signingKey.getPrivate()
    ));

    return jwt.serialize();
}
~~~

Issue T1 with K1:

~~~java
String oldToken = issueToken(
    keyPair1,
    "rsa-key-1",
    Instant.now().plus(Duration.ofMinutes(15))
);
~~~

Issue T2 with K2:

~~~java
String newToken = issueToken(
    keyPair2,
    "rsa-key-2",
    Instant.now().plus(Duration.ofMinutes(15))
);
~~~

In tests, time can be controlled with a fixed `Clock` so tests do not depend on wall-clock execution time. The example above uses `Instant.now()` for readability; real suites should provide a helper taking explicit `issuedAt` and `expiresAt`.

### 6.2. Do Not Change `kid` While Keeping the Old Signature

`kid` is metadata for key selection, not a signature. If you change the header `kid` from `rsa-key-1` to `rsa-key-2` without re-signing the JWT using private K2, the signature will fail verification.

The new token must actually be signed by the private key matching the public key published under the new `kid`.

### 6.3. Verify Private Keys Never Appear in JWKS

A Resource Server's JWKS endpoint needs only public verification keys. Tests can parse the response and assert there are no private RSA parameters such as `d`, `p`, `q`, `dp`, `dq`, or `qi`.

Never log or commit test private keys. Even for test-only keys, keep them in memory or managed test directories scoped to the test lifecycle.

---

## 7. Configuring `JwtDecoder` Against the Test JWKS Endpoint

### 7.1. Decoder with Explicit Algorithm and Validators

~~~java
static JwtDecoder createDecoder(String jwksUri) {
    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwksUri)
            .jwsAlgorithm(SignatureAlgorithm.RS256)
            .build();

    OAuth2TokenValidator<Jwt> issuerAndTime =
        JwtValidators.createDefaultWithIssuer(
            "https://issuer.test.example"
        );

    OAuth2TokenValidator<Jwt> audience = jwt -> {
        if (jwt.getAudience().contains("orders-api")) {
            return OAuth2TokenValidatorResult.success();
        }

        return OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Token audience is not orders-api",
                null
            )
        );
    };

    decoder.setJwtValidator(
        new DelegatingOAuth2TokenValidator<>(
            issuerAndTime,
            audience
        )
    );

    return decoder;
}
~~~

This decoder:

- Fetches public keys from the configured JWKS URI.
- Allows only `RS256`.
- Validates the issuer.
- Validates default timestamps.
- Validates audience for `orders-api`.

In Spring Security, `JwtDecoder` is the synchronous API for Servlet Resource Servers. For WebFlux, use `NimbusReactiveJwtDecoder` and `ReactiveJwtDecoder`; the trust policy logic is the same, while the decode result is `Mono<Jwt>`.

### 7.2. Create the Decoder Once and Reuse It

~~~java
JwtDecoder decoder = createDecoder(jwksUri);
~~~

In production, the decoder should have a shared lifecycle rather than being instantiated per request. Re-creating decoders repeatedly loses the cache and increases JWKS fetches.

In tests, create the decoder once to observe cache behavior across phases. Then instantiate a fresh decoder separately when simulating a newly started Resource Server instance.

---

## 8. Core Test: Both Old and New Tokens Valid During Overlap

### 8.1. Setting Up Initial State

1. Generate K1 and K2.
2. Initial JWKS contains only public K1.
3. Start the endpoint.
4. Create decoder D1 pointing at the JWKS URI.
5. Issue T1 signed with private K1, with `exp` in the future.
6. Decode T1 so D1 fetches and caches JWKS containing K1.

~~~java
currentJwks.set(jwksWithK1);

JwtDecoder decoder = createDecoder(jwksUri);

String oldToken = issueToken(
    keyPair1,
    "rsa-key-1",
    Instant.now().plus(Duration.ofMinutes(15))
);

Jwt oldJwt = decoder.decode(oldToken);

assertEquals("user-417", oldJwt.getSubject());
~~~

The first decode also warms up the key retrieval path. If you want to test cold starts, create a fresh decoder per test case and count how many times the JWKS endpoint was called.

### 8.2. Publish Public K2 While Keeping K1

~~~java
currentJwks.set(jwksWithBoth);
~~~

Create T2 with K2:

~~~java
String newToken = issueToken(
    keyPair2,
    "rsa-key-2",
    Instant.now().plus(Duration.ofMinutes(15))
);
~~~

Use the same decoder D1 to verify T2:

~~~java
Jwt newJwt = decoder.decode(newToken);

assertEquals("user-417", newJwt.getSubject());
~~~

When D1 does not yet have K2 in cache, the Nimbus JWK source can refresh JWKS to locate the new `kid`. Verify the refresh behavior in the Nimbus/Spring Security version your project uses; do not assume caches update instantaneously simply because the endpoint's response changed.

### 8.3. Verify T1 Still Works

~~~java
Jwt oldJwtAfterPublish = decoder.decode(oldToken);

assertEquals("user-417", oldJwtAfterPublish.getSubject());
~~~

K1 is still in JWKS, so the old token continues verifying. This is the core requirement of the overlap window.

### 8.4. Expected Results

| Token | `kid` | JWKS during overlap | Result |
|---|---|---|---|
| T1 | `rsa-key-1` | K1 + K2 | Accepted if unexpired and claims valid |
| T2 | `rsa-key-2` | K1 + K2 | Accepted if unexpired and claims valid |
| T1 with header `kid` changed to K2 without re-signing | `rsa-key-2` | K1 + K2 | Signature rejected |
| Token signed with key absent from JWKS | `unknown-key` | K1 + K2 | Rejected |
| T2 with wrong audience | `rsa-key-2` | K1 + K2 | Rejected |
| Expired T1 | `rsa-key-1` | K1 + K2 | Rejected due to timestamp |

Overlap does not relax issuer, audience, signature, or expiry validation. It only ensures the RS has the public keys needed for validly issued tokens.

---

## 9. Simulating Removal of K1 While Old Tokens Are Still Unexpired

### 9.1. Updating JWKS to Keep Only K2

~~~java
currentJwks.set(jwksWithK2);
~~~

T1 is still unexpired, yet K1 has been removed from JWKS. A fresh Resource Server that has never cached K1 cannot find a public key to verify T1. That request must be rejected because the signature cannot be verified against the current trusted key source.

However, D1 may still have public K1 cached. It may keep verifying T1 until its cache refreshes/expires or the key is invalidated per implementation. Thus, results across nodes can diverge while caches have not yet converged.

### 9.2. Comparing a Cached Decoder vs. a Fresh Decoder

~~~java
// D1 previously fetched JWKS containing K1.
assertDoesNotThrow(() -> decoder.decode(oldToken));

// D2 simulates a fresh Resource Server instance.
JwtDecoder freshDecoder = createDecoder(jwksUri);

assertThrows(
    JwtException.class,
    () -> freshDecoder.decode(oldToken)
);
~~~

The first assertion only illustrates how caching can retain an old key; it depends on the library's cache policy and refresh timing. Do not treat it as a guarantee that every Nimbus version caches keys for a fixed duration.

The second assertion tests a fresh instance that sees only the current JWKS containing K2. Since T1 still carries `kid` K1, the fresh decoder has no matching key and must reject it.

To deterministically test D1 rejecting after cache refresh, explicitly control caching/refresh in the test or instantiate a new decoder after JWKS contains only K2. Never rely on `Thread.sleep` to wait out an uncontrolled TTL.

### 9.3. Operational Lesson

Removing a key from JWKS does not guarantee every RS immediately forgets that public key. Each instance can maintain its own cache, and Nimbus/JWK source cache policies can vary by version or configuration.

For routine rotation, the right solution is never removing K1 before K1-signed tokens expire. For key compromise, an emergency procedure is required, which may include:

- Removing the key from JWKS.
- Triggering cache refresh/invalidation across all RS instances.
- Revoking or blocking affected tokens.
- Shortening token lifetimes or applying denylists/introspection depending on architecture.
- Monitoring requests still presenting the compromised `kid`.

Do not assume the entire cluster has absorbed a change just because the JWKS endpoint updated.

---

## 10. Testing an Expired Old Token While K1 Is Still Published

This is an important test to separate two mechanisms:

- **Key availability:** does the RS have the public key to verify the signature?
- **Token validity:** is the token still within its validity window?

Even when K1 remains in JWKS, token T1 must be rejected after `exp`.

Create a token signed with K1 that is already expired:

~~~java
String expiredOldToken = issueToken(
    keyPair1,
    "rsa-key-1",
    Instant.now().minus(Duration.ofMinutes(1))
);

assertThrows(
    JwtException.class,
    () -> decoder.decode(expiredOldToken)
);
~~~

This test proves keeping public K1 during overlap does not let old tokens live indefinitely. The timestamp validator still applies to every token regardless of `kid`.

If using a fixed clock in tests, derive `issuedAt`/`exp` from the same `Clock`. Avoid relying on wall-clock time when testing `exp` boundaries and clock skew.

### 10.1. Testing Clock Skew

An RS may allow a small clock skew window to avoid rejecting tokens due to minor clock drift. Configure and test the clock skew value explicitly.

Example initializing a timestamp validator with a chosen skew:

~~~java
JwtTimestampValidator timestampValidator =
    new JwtTimestampValidator(Duration.ofSeconds(30));
~~~

Compose the timestamp validator with issuer, audience, and remaining policy checks per your API version. Clock skew is not a reason to keep K1 arbitrarily long; it is part of calculating the key retirement cutoff.

---

## 11. Simulating Multiple Resource Server Instances

### 11.1. Why Test Multiple Nodes?

Each RS instance may:

- Start at a different time.
- Fetch JWKS for the first time at a different time.
- Hold a different K1/K2 cache state.
- Encounter an unknown `kid` at a different time.
- Lose reachability to JWKS temporarily.
- Be deployed or restarted mid-rotation.

A test with a single decoder cannot simulate those differences.

### 11.2. Two-Node Scenario

Suppose:

- Node A has cached JWKS containing only K1.
- The AS publishes K1 + K2.
- Node B starts after publish and loads both keys.
- The AS switches signing to K2.
- Node A encounters a K2 token and must refresh.
- Node B verifies both T1 and T2 from cache.
- After overlap, JWKS contains only K2, and a fresh node does not verify T1.

Verification table:

| Moment | JWKS | Node A | Node B |
|---|---|---|---|
| Before publish | K1 | Has K1 | May not be started yet |
| After publish | K1 + K2 | Stale cache K1 | Fetches K1 + K2 |
| After switch | K1 + K2 | Refreshes on `kid` K2 | Verifies T1/T2 |
| After retire | K2 | May temporarily retain K1 cache | Refreshes/expires per policy |
| After cache convergence | K2 | Uses K2 only | Uses K2 only |

### 11.3. Testing with Two Independent Decoders

In tests, create two separate decoders:

~~~java
JwtDecoder nodeA = createDecoder(jwksUri);
JwtDecoder nodeB = createDecoder(jwksUri);
~~~

Have `nodeA` decode T1 before publishing K2 so it caches K1. Then publish K1 + K2, start `nodeB`, and decode both T1/T2. Next send T2 to `nodeA` to observe refresh on an unknown `kid`.

After retiring K1, instantiate a fresh `nodeC` to confirm T1 no longer verifies against the current JWKS. If testing cache convergence on `nodeA`/`nodeB`, explicitly control cache and refresh behavior rather than waiting arbitrarily.

### 11.4. Configuration Synchronization and Rollout

In real environments, verify:

- Every RS instance uses the same issuer and JWKS URI.
- No stale instance points to a different endpoint.
- Egress to the JWKS endpoint works from every network zone.
- Cache refreshes are not blocked by misconfigured proxies/CDNs.
- AS and RS rollouts do not create a window where an active key is unpublished.
- Newly autoscaled instances can fetch the current JWKS.
- Dashboards can identify nodes that have not yet observed the new `kid`.

---

## 12. Testing JWKS Unavailability and Unknown `kid`

### 12.1. Temporary JWKS Endpoint Failure

When public keys are already cached, some requests can keep verifying using known keys while the JWKS endpoint is down. However, tokens using a new, uncached `kid` will fail.

Test both cases:

| State | Outcome to verify |
|---|---|
| Token K1, cache has K1, JWKS endpoint temporarily down | Can continue verifying per cache/library behavior |
| Token K2, cache lacks K2, JWKS endpoint down | Cannot verify without trusted K2 |
| Fresh instance, JWKS down, token K1 | No key to verify; rejected |
| JWKS endpoint returns malformed JSON | Do not accept error key responses |

Never turn a JWKS fetch failure into skipping signature verification.

### 12.2. Unknown `kid` Must Not Trigger Arbitrary Trust

A token can send a random `kid`. The RS may trigger a JWKS refresh depending on the JWK source's behavior. Avoid letting bursts of unknown `kid`s create unbounded load on the AS/JWKS endpoint.

Monitor:

- Unknown-`kid` rate.
- JWKS fetch count.
- JWKS fetch latency.
- Refresh failures.
- Decoder failures.
- Requests waiting on refresh.

Never fetch keys from a token-supplied `jku`/`x5u` to resolve an unknown `kid`. `kid` is only used to look up keys in a pre-configured trusted source.

### 12.3. Preventing Cache Stampedes

If many requests encounter a new `kid` concurrently, some implementations coalesce refreshes while others trigger multiple fetches depending on cache/source configuration. Measure the real behavior of your version.

Mitigate risk by:

- Publishing K2 before the AS begins signing with it.
- Warming up the new key on RS instances if supported.
- Sharing cache and HTTP client lifecycles.
- Bounding retries/refreshes within library capabilities.
- Avoiding restarting all RS instances simultaneously unless required.

Never build an infinite refresh loop upon encountering an unknown `kid`.

---

## 13. Comprehensive JUnit Test Suite

### 13.1. Required Helpers

A complete test fixture can group helpers together:

~~~java
class SigningKeyRotationTests {

    static final String ISSUER =
        "https://issuer.test.example";

    static final String AUDIENCE = "orders-api";

    KeyPair keyPair1;
    KeyPair keyPair2;

    RSAKey publicKey1;
    RSAKey publicKey2;

    AtomicReference<String> currentJwks;
    HttpServer jwksServer;
    String jwksUri;

    JwtDecoder decoder;

    @BeforeEach
    void setUp() throws Exception {
        keyPair1 = generateRsaKeyPair();
        keyPair2 = generateRsaKeyPair();

        publicKey1 = publicJwk(keyPair1, "rsa-key-1");
        publicKey2 = publicJwk(keyPair2, "rsa-key-2");

        currentJwks = new AtomicReference<>(
            new JWKSet(publicKey1).toString()
        );

        startJwksServer();

        decoder = createDecoder(jwksUri);
    }

    @AfterEach
    void tearDown() {
        if (jwksServer != null) {
            jwksServer.stop(0);
        }
    }
}
~~~

`startJwksServer()`, `generateRsaKeyPair()`, `publicJwk()`, `issueToken()`, and `createDecoder()` were shown in earlier sections. You can extract them into a test utility to reuse across other rotation tests.

### 13.2. Overlap Test

~~~java
@Test
void acceptsOldAndNewTokensDuringOverlap() throws Exception {
    String oldToken = issueToken(
        keyPair1,
        "rsa-key-1",
        Instant.now().plus(Duration.ofMinutes(10))
    );

    assertEquals(
        "user-417",
        decoder.decode(oldToken).getSubject()
    );

    currentJwks.set(
        new JWKSet(List.of(publicKey1, publicKey2)).toString()
    );

    String newToken = issueToken(
        keyPair2,
        "rsa-key-2",
        Instant.now().plus(Duration.ofMinutes(10))
    );

    assertEquals(
        "user-417",
        decoder.decode(newToken).getSubject()
    );

    assertEquals(
        "user-417",
        decoder.decode(oldToken).getSubject()
    );
}
~~~

This verifies the primary goal: the same decoder can verify both old and new tokens during the overlap window, provided JWKS refresh behaves as expected in the active version.

### 13.3. Expired Old Token Test

~~~java
@Test
void rejectsExpiredOldTokenEvenWhenOldKeyIsPublished() throws Exception {
    currentJwks.set(
        new JWKSet(List.of(publicKey1, publicKey2)).toString()
    );

    String expiredToken = issueToken(
        keyPair1,
        "rsa-key-1",
        Instant.now().minus(Duration.ofMinutes(1))
    );

    assertThrows(
        JwtException.class,
        () -> decoder.decode(expiredToken)
    );
}
~~~

This confirms keeping the old public key in JWKS does not disable `exp` validation.

### 13.4. Old Token After K1 Retirement Test

~~~java
@Test
void freshDecoderCannotVerifyOldKidAfterRetirement() throws Exception {
    String oldToken = issueToken(
        keyPair1,
        "rsa-key-1",
        Instant.now().plus(Duration.ofMinutes(5))
    );

    currentJwks.set(new JWKSet(publicKey2).toString());

    JwtDecoder freshDecoder = createDecoder(jwksUri);

    assertThrows(
        JwtException.class,
        () -> freshDecoder.decode(oldToken)
    );
}
~~~

The token is still unexpired in this test, yet public K1 is no longer served by JWKS. The fresh decoder cannot verify the signature. This simulates retiring too early and explains why old tokens fail on some instances.

Do not treat this test as the desired behavior of a normal rotation. In production, retire K1 only after old tokens have expired per policy.

---

## 14. Testing the Spring Security HTTP Endpoint

### 14.1. Wiring the Decoder into the Servlet Resource Server

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        JwtDecoder decoder) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.decoder(decoder))
        )
        .build();
}
~~~

Test controller:

~~~java
@RestController
class OrdersController {

    @GetMapping("/api/orders")
    Map<String, String> orders(Authentication authentication) {
        return Map.of("subject", authentication.getName());
    }
}
~~~

When testing with MockMvc, send real access tokens signed by K1/K2 via the `Authorization` header. Never use mock `jwt()` when the goal is verifying signatures and key rotation, because mock authentication bypasses the decoder.

### 14.2. Checking Status Codes

| Request | Expected outcome |
|---|---|
| T1 signed with K1 during overlap | 200 |
| T2 signed with K2 during overlap | 200 |
| Expired T1 while K1 is still published | 401 |
| Unexpired T1 after K1 is retired, fresh decoder | 401 |
| T2 with wrong audience | 401 |
| Token signed with private key whose public key is absent from JWKS | 401 |
| Valid token missing `SCOPE_orders.read` | 403 |

`401` reflects authentication failure. `403` reflects an authenticated token lacking sufficient authority. Keep the two cases separate to diagnose rotation failures accurately.

### 14.3. WebFlux

For WebFlux, configure `ReactiveJwtDecoder` and `SecurityWebFilterChain`. When testing with `WebTestClient`, send real signed compact tokens to pass through the decoder.

If a test uses only `mockJwt()`, it tests authorization rules after an `Authentication` is already fabricated; it does not verify JWKS fetching, `kid` selection, or signature verification.

---

## 15. Routine Rotation vs. Key Compromise

### 15.1. Routine Rotation

The goal is transitioning signing keys without disrupting active tokens:

- Publish the new public key.
- Keep the old public key.
- Ensure RS instances receive the new key.
- Switch the AS to sign with the new key.
- Wait for all K1 tokens to expire plus skew/margin.
- Remove public K1.

In this scenario, an overlap window is essential.

### 15.2. Key Compromise

If private K1 is leaked, an attacker can forge tokens signed by K1. Keeping K1 in JWKS to avoid disrupting old tokens would also keep forged tokens verifiable.

Handle this as a security incident:

1. Stop signing with K1.
2. Remove K1 from JWKS or mark the key revoked per system capabilities.
3. Force cache refresh/invalidation across all RS instances.
4. Revoke affected tokens via introspection/denylist or appropriate mechanisms.
5. Audit tokens issued during the compromise window.
6. Consider shortening maximum token lifetimes and re-issuing tokens.
7. Monitor requests presenting the compromised `kid`.
8. Document the incident and verify all nodes have converged.

During a compromise, never apply a normal overlap window mechanically. Priority goes to revoking trust in the leaked key while managing user impact for legitimate tokens.

### 15.3. Limits of Removing a Key from JWKS

If an RS has already cached K1, removing K1 from JWKS may not make that node reject it immediately. You must understand the cache policy, refresh mechanism, and invalidation capabilities of your decoder/JWK source.

If rapid emergency revocation is required, design and test a mechanism to refresh caches or deny a compromised `kid`. Restarting all nodes can be an operational fallback, but should not be the sole assumption if fast response times are needed.

---

## 16. Common Pitfalls in the Lab

| Mistake | Consequence | Fix |
|---|---|---|
| Removing K1 immediately when publishing K2 | Unexpired K1 tokens can be rejected | Keep K1 during overlap |
| AS signs with K2 before publishing public K2 | RS lacks the key to verify new tokens | Publish/warm up before switching |
| Changing `kid` without re-signing JWT | Signature mismatch | Sign new tokens with private K2 |
| Reusing the same key pair for two `kid`s | Fails to simulate real rotation | Generate two independent key pairs |
| Putting private JWK in JWKS | Signing key leak | Publish only public JWKs |
| Creating a new decoder per request | Cache loss and extra fetches | Use a singleton/managed bean decoder |
| Testing only one RS instance | Misses cache divergence across nodes | Test multiple independent decoders |
| Assuming JWKS updates take effect immediately | Nodes may retain stale caches | Test refresh/cache convergence |
| Using `Thread.sleep` to wait for cache | Flaky tests | Control cache/clock and use test endpoints |
| Keeping K1 forever | Extends trust window for old key | Retire based on maximum token lifetime |
| Removing K1 while old tokens remain valid | Some RS instances fail to verify tokens | Compute retirement from `exp`/skew/margin |
| Treating signer switch as revoking old tokens | Old tokens still work | Use a separate revocation policy if needed |
| Not testing `exp` while K1 is published | May miss timestamp validation | Test expired tokens independently |
| Testing only new tokens | Misses overlap bugs | Test T1 and T2 in parallel |
| Fetching `jku` from token on unknown `kid` | Opens arbitrary trust sources | Use only trusted JWKS URIs |
| Skipping signature on cache refresh failure | Fail-open | Reject unverifiable tokens |
| Deleting K1 after compromise while forgetting caches | Old nodes may still trust K1 | Have a cache invalidation/incident procedure |

---

## 17. Lab Completion Checklist

### Setup

- [ ] Generate K1 and K2 from two separate RSA key pairs.
- [ ] Assign a unique `kid` to each key.
- [ ] Publish only public JWKs.
- [ ] Stand up a test JWKS endpoint whose response can change.
- [ ] Configure the decoder with issuer, audience, and `RS256` allowlist.
- [ ] Issue T1 signed by K1 and confirm it is unexpired.

### Publish and Switch

- [ ] Initial JWKS contains only K1.
- [ ] RS verifies T1.
- [ ] Publish K1 + K2.
- [ ] RS picks up K2.
- [ ] AS issues T2 signed with K2.
- [ ] RS verifies T2.
- [ ] RS continues to verify T1.

### Retire

- [ ] Calculate retirement time from the last K1 token, maximum lifetime, skew, and margin.
- [ ] Do not retire K1 while K1 tokens remain valid per policy.
- [ ] Verify expired tokens are rejected even when K1 is still published.
- [ ] After retirement, fresh instances cannot verify K1 tokens.
- [ ] Verify old caches may require refresh/invalidation.
- [ ] Confirm T2 remains valid.

### Operations

- [ ] Test at least two independent RS instances/caches.
- [ ] Test JWKS endpoint unavailability.
- [ ] Test unknown `kid` and malformed JWKS.
- [ ] Monitor key fetches, unknown `kid`, `401`s, and decoder errors.
- [ ] Maintain a dedicated procedure for key compromise.
- [ ] Never log tokens or private keys.

---

## 18. Self-Check Questions

**Question 1.** Why keep K1 in JWKS after the AS starts signing with K2?

**Answer:** Tokens previously issued with K1 may still be unexpired. The RS needs public K1 to verify those tokens' signatures during the overlap window.

**Question 2.** Does the issuer need to change when rotating signing keys?

**Answer:** No. The issuer identifies the AS and stays constant. Rotation changes the signing key and the set of published public keys.

**Question 3.** Does `kid` replace the signature?

**Answer:** No. `kid` only helps select the public key. New tokens must be signed with the corresponding private key.

**Question 4.** When can K1 be retired?

**Answer:** After no K1 tokens remain valid, plus clock skew and propagation/cache margin. Use `max(exp)` or the last K1 issuance time plus maximum token lifetime.

**Question 5.** Why might a node accept T1 after K1 is removed from JWKS?

**Answer:** The node may still have public K1 cached. Caches are not necessarily invalidated immediately when the endpoint changes.

**Question 6.** Can a fresh node reject T1 even if the token is unexpired?

**Answer:** Yes. If the current JWKS no longer includes K1, the fresh node has no public key to verify T1's signature.

**Question 7.** Does keeping K1 in JWKS let tokens live past `exp`?

**Answer:** No. The timestamp validator still rejects expired tokens.

**Question 8.** What happens if the JWKS endpoint is down and the RS does not yet have K2?

**Answer:** The RS cannot verify a K2 token without the trusted key. It must reject that token rather than skipping signature verification.

**Question 9.** Can you use the same key pair for K1 and K2 and just change the `kid`?

**Answer:** No. That does not simulate a real rotation and prevents tests from catching key-selection bugs.

**Question 10.** How do routine rotation and key compromise differ?

**Answer:** Routine rotation uses overlap so old tokens keep working. Key compromise requires revoking trust in the leaked key quickly, refreshing caches, and handling tokens signed by that key.

**Question 11.** Should a new `JwtDecoder` be created per request to see fresh JWKS?

**Answer:** No. The decoder should be managed and reused. Creating a new one per request destroys caching and increases JWKS load.

**Question 12.** Why test multiple RS instances?

**Answer:** Each node can have different cache states and refresh timing. Testing one node misses cluster-wide inconsistencies.

**Question 13.** If T1 is unexpired yet K1 was retired per plan, is a `401` error expected behavior?

**Answer:** No. That signals premature retirement or a K1 token issued later than expected. In planned rotation, keep K1 until old tokens expire.

**Question 14.** If K1 is compromised, must overlap continue until old tokens expire?

**Answer:** Not necessarily. Follow incident policy: remove the key, refresh caches, and revoke/block affected tokens. Keeping a compromised key allows attackers to keep forging valid-looking tokens.

**Question 15.** What did this lab prove?

**Answer:** It proved the RS can verify both old and new tokens during overlap when both public keys are trusted; expired tokens are still rejected; and retiring a key affects old token verification depending on each node's cache state.

---

## 19. References

- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517.html): JWK, JWKS, `kid`, key use, and public key representation.
- [RFC 7515 — JSON Web Signature (JWS)](https://www.rfc-editor.org/rfc/rfc7515.html): JOSE header, signing input, and JWT signatures.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519.html): issuer, audience, `exp`, and time claims.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725.html): validating algorithms, issuer, audience, and handling JWTs safely.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, `issuer-uri`, `jwk-set-uri`, and JWK retrieval.
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html): `ReactiveJwtDecoder` and JWT verification on WebFlux.
- [Spring Security API — NimbusJwtDecoder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/jwt/NimbusJwtDecoder.html): Servlet decoder configuration.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): APIs for creating JWKs, JWKS, signing JWTs, and handling remote JWK sources.

API and cache behavior can vary across Spring Security/Nimbus versions. Check the exact resolved dependencies in your project and run the lab against the same version you deploy.

---

## 20. Key Takeaways

Safe signing key rotation requires an overlap window so Resource Servers continue verifying old tokens while starting to accept new ones.

- **Publish first:** add public K2 to JWKS alongside K1 before the AS signs tokens with K2.
- **Switch second:** switch the signer only once RS instances can fetch public K2.
- **Keep old key:** continue publishing K1 until all K1-signed tokens expire, plus clock skew and propagation margin.
- **Retire in a controlled way:** remove K1 after overlap; verify each RS instance's cache.
- **Keep all validation:** issuer, audience, algorithm, signature, and `exp` must still be verified across every phase.
- **Test multiple nodes:** differing caches can yield differing results during convergence.
- **Handle compromise separately:** if a private key leaks, prioritize revoking trust, invalidating caches, and revoking affected tokens rather than maintaining normal overlap.

Rotation is complete when the AS signs with K2, every RS verifies K2 tokens, K1 tokens are past their validity window, and K1 is retired per policy.
