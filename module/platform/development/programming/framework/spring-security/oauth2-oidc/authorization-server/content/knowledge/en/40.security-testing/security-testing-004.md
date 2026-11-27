# Testing client assertions with invalid signature, wrong audience, and replay

With the `private_key_jwt` method, a client authenticates at the token endpoint using a JWT assertion signed with the client's private key. The Authorization Server retrieves the registered public key to verify the signature and checks claims identifying the client, the target server receiving the assertion, and its validity window. If the server checks only the signature while ignoring audience or failing to detect replayed assertions, a stolen assertion can be misused.

This lesson guides you through testing three critical failure categories: invalid signatures, audiences not intended for the current Authorization Server, and previously used assertions. Examples use `private_key_jwt` with RSA and Nimbus JOSE + JWT; the same principles apply to other asymmetric algorithms permitted by your deployment.

After this lesson, you will be able to:

- Distinguish a client assertion used for client authentication from a JWT bearer grant used as an authorization grant.
- Build test assertions containing `iss`, `sub`, `aud`, `exp`, `iat`, `jti`, and `kid`.
- Test invalid signatures, unknown keys, wrong audiences, and expired assertions.
- Design replay detection based on `jti` and a shared store with atomic operations.
- Validate client assertions through the token endpoint and observe appropriate OAuth errors.
- Test concurrent requests and behavior across multiple Authorization Server instances.

## 1. Distinguishing client assertions and grant assertions

A JWT assertion can appear in two different roles:

| Usage | Request parameters | Purpose |
|---|---|---|
| JWT for client authentication (`private_key_jwt`) | `client_assertion_type`, `client_assertion` | Proves the client calling the token endpoint is the registered client |
| JWT bearer authorization grant | `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`, `assertion` | Uses a JWT as a credential/authorization grant to request tokens per RFC 7523 |

This lab tests **client authentication via `private_key_jwt`**. In the request, `grant_type` may be `client_credentials` or another grant type supported by the client; `client_assertion` remains solely proof of client authentication. Do not confuse it with the JWT bearer grant, and do not place the client authentication assertion in the other grant type's `assertion` field.

The client sends a request to the token endpoint with these parameters:

```text
grant_type=client_credentials
client_id=orders-service
client_assertion_type=urn:ietf:params:oauth:client-assertion-type:jwt-bearer
client_assertion=<signed-client-assertion>
scope=orders.read
```

The client does not send HTTP Basic credentials in this request. The Authorization Server must locate the matching `RegisteredClient`, verify the client registered `ClientAuthenticationMethod.PRIVATE_KEY_JWT`, fetch the client's public key, and validate the assertion.

## 2. Claims and headers to verify

A client assertion JWT has a header and payload structured per JWT/JWS. Example header using RSA:

```json
{
  "alg": "RS256",
  "kid": "orders-client-key-2026-01",
  "typ": "JWT"
}
```

The payload must bind the assertion to the client and the Authorization Server:

```json
{
  "iss": "orders-service",
  "sub": "orders-service",
  "aud": "https://auth.example.test",
  "iat": 1794859200,
  "exp": 1794859260,
  "jti": "unique-assertion-id"
}
```

Timestamps are illustrative only. In tests, generate claims from a `Clock` or a fixed `Instant` to avoid depending on the test runner's wall clock.

| Component | Meaning | Mandatory check in lab |
|---|---|---|
| `alg` | Signing algorithm | Within the server's allowlist; never accept arbitrary header algorithms |
| `kid` | Client public key identifier | Resolves to a registered key unambiguously |
| `iss` | Assertion issuer | Matches `client_id` per the client assertion contract |
| `sub` | Assertion subject | Matches the authenticated `client_id` |
| `aud` | Receiving Authorization Server | Contains the exact audience configured for the server to accept |
| `exp` | Assertion expiration time | Still valid, accounting for configured clock skew |
| `iat` | Issuance time | Within a reasonable time window per policy |
| `jti` | Unique assertion identifier | Not previously accepted within the anti-replay window |

With Spring Authorization Server, `JwtClientAssertionDecoderFactory` provides the default decoder and validators for client assertions. Verify the exact audience required by your application's version and configuration. In the common default setup, the audience is matched against the Authorization Server's issuer; deployments with custom validators must use the audience agreed upon in their contract. Do not derive the audience from an internal host or a pod URL.

Having `jti` present in the JWT does not automatically prevent replay. A purely stateless JWT decoder can verify the same assertion multiple times while its signature and timestamps remain valid. If the system requires single-use assertions, a replay store or equivalent mechanism is needed to mark accepted `jti` values.

## 3. Configuring the test client

Create a dedicated confidential client for tests. Register the `PRIVATE_KEY_JWT` authentication method, the grant type under test, and the client's public key/JWK Set.

Example `RegisteredClient` configuration:

```java
RegisteredClient client = RegisteredClient.withId("registered-orders-service")
        .clientId("orders-service")
        .clientAuthenticationMethod(ClientAuthenticationMethod.PRIVATE_KEY_JWT)
        .authorizationGrantType(AuthorizationGrantType.CLIENT_CREDENTIALS)
        .scope("orders.read")
        .clientSettings(ClientSettings.builder()
                .jwkSetUrl(clientJwksUri)
                .build())
        .build();
```

`clientJwksUri` is the client's public JWKS URL in the test environment. If the application registers JWKs directly or uses a custom `JWKSource`, keep that integration intact and ensure the server can retrieve the corresponding public key. The private key stays solely on the test client; never register or publish private keys in JWKS.

Check before running tests:

- The client has the exact `client_id` and `PRIVATE_KEY_JWT`.
- The client is permitted to use the grant type being submitted.
- The public JWK has a `kid` matching the JWT header.
- The JWK has the appropriate key type, algorithm, and `use`/`key_ops` if those attributes are declared.
- The Authorization Server's issuer and expected assertion audience are configured consistently.
- The token endpoint is called via the public URL the client actually uses.

## 4. Creating test client assertions with Nimbus

In tests, generate a dedicated RSA key pair. Nimbus can hold the private key for signing and export the public JWK for a mock JWKS server.

```java
static RSAKey generateClientKey(String kid) throws JOSEException {
    return new RSAKeyGenerator(2048)
            .keyID(kid)
            .generate();
}

static String createClientAssertion(
        RSAKey signingKey,
        String clientId,
        String audience,
        Instant issuedAt,
        String jti) throws JOSEException {

    JWTClaimsSet claims = new JWTClaimsSet.Builder()
            .issuer(clientId)
            .subject(clientId)
            .audience(audience)
            .issueTime(Date.from(issuedAt))
            .expirationTime(Date.from(issuedAt.plusSeconds(60)))
            .jwtID(jti)
            .build();

    JWSHeader header = new JWSHeader.Builder(JWSAlgorithm.RS256)
            .keyID(signingKey.getKeyID())
            .type(JOSEObjectType.JWT)
            .build();

    SignedJWT assertion = new SignedJWT(header, claims);
    assertion.sign(new RSASSASigner(signingKey.toPrivateKey()));
    return assertion.serialize();
}
```

This snippet assumes the Nimbus JOSE + JWT dependency and corresponding imports have been added. In real tests, use a fixed `Clock` so `issuedAt`, `exp`, and validators reference the same time source. `jti` must be distinct for each new assertion, except in tests intentionally replaying the same assertion.

Creating a valid assertion:

```java
String validAssertion = createClientAssertion(
        clientPrivateKey,
        "orders-service",
        expectedAudience,
        clock.instant(),
        "assertion-001");
```

`expectedAudience` must be the value the server actually accepts. With the common default Spring Authorization Server configuration, use the Authorization Server's public issuer; if the application has a custom audience validator, use the value from that validator's contract.

## 5. Submitting the assertion to the token endpoint

Example calling the token endpoint via MockMvc with the client credentials grant:

```java
mockMvc.perform(post(tokenEndpoint)
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param(OAuth2ParameterNames.GRANT_TYPE,
                AuthorizationGrantType.CLIENT_CREDENTIALS.getValue())
        .param(OAuth2ParameterNames.CLIENT_ID, "orders-service")
        .param("client_assertion_type",
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer")
        .param("client_assertion", validAssertion)
        .param(OAuth2ParameterNames.SCOPE, "orders.read"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.access_token").isNotEmpty())
    .andExpect(jsonPath("$.token_type").value("Bearer"));
```

`tokenEndpoint` is obtained from test configuration or Discovery metadata. The `OAuth2ParameterNames` constants must exist in the Spring Security version in use; if a version lacks a constant for the assertion type, use the exact standard parameter name shown in the example. A passing test should also verify the access token works at the Resource Server and contains the requested scope.

## 6. Testing assertions with invalid signatures

The server must verify the signature using the public key registered for the client. Two cases must be separated:

- `kid` does not exist in the JWKS or no public key can be found.
- `kid` exists, but the assertion was signed with a private key that does not match that public key.

The second case proves the server actually verifies the cryptographic signature. Checking only that `kid` exists is insufficient.

### 6.1. Creating an assertion signed with the wrong key

Generate two key pairs. Register the public key of `registeredKey` in the client's JWKS, but sign the assertion with `attackerKey`. To keep the test focused on the signature, use the same `kid` in the invalid assertion's header as the registered key, while the actual signing private key does not match that public key.

```java
RSAKey registeredKey = generateClientKey("orders-key-1");
RSAKey attackerKey = generateClientKey("orders-key-1");

String wrongSignatureAssertion = createClientAssertion(
        attackerKey,
        "orders-service",
        expectedAudience,
        clock.instant(),
        "assertion-wrong-signature");
```

In the JWKS fixture, publish only `registeredKey.toPublicJWK()`. Do not publish `attackerKey`'s public key for this client.

### 6.2. Assertion with an unknown key

Create an assertion signed with another key and use a `kid` that does not appear in the JWKS. The decoder cannot select a key to verify with, so client authentication must fail.

These two tests distinguish key-lookup failures from cryptographic verification failures. Both must lead to client authentication rejection, typically the OAuth error `invalid_client` at the token endpoint. Do not return details such as which public key was found or where signature verification failed, as that information can help probe key configurations.

### 6.3. Testing the assertion via the token endpoint

```java
mockMvc.perform(post(tokenEndpoint)
        .contentType(MediaType.APPLICATION_FORM_URLENCODED)
        .param("grant_type", "client_credentials")
        .param("client_id", "orders-service")
        .param("client_assertion_type",
                "urn:ietf:params:oauth:client-assertion-type:jwt-bearer")
        .param("client_assertion", wrongSignatureAssertion)
        .param("scope", "orders.read"))
    .andExpect(jsonPath("$.error").value(OAuth2ErrorCodes.INVALID_CLIENT));
```

The HTTP status for client authentication errors depends on how the endpoint and authentication mechanism respond in your framework version. The primary assertion is that the server issues no access token and returns the appropriate error code. Never assert only the status code while ignoring the body.

## 7. Testing wrong audience

Audience binds the assertion to the Authorization Server intended to receive it. If an assertion was created for another server, the current server must reject it even if the signature is completely valid.

Create an assertion using the client's genuine private key, valid `iss`, `sub`, `kid`, `iat`, `exp`, and `jti`, but set `aud` to the issuer of another environment or a value outside the audience allowlist.

```java
String wrongAudienceAssertion = createClientAssertion(
        clientPrivateKey,
        "orders-service",
        "https://auth-other.example.test",
        clock.instant(),
        "assertion-wrong-audience");
```

Outcomes to verify:

- A valid signature does not allow an assertion to be accepted when the audience is wrong.
- The token endpoint returns a client authentication error.
- No access token is issued.
- The replay store does not mark the assertion as used if basic claims have not passed validation.
- No internal information about issuer/audience is leaked in the error response.

Audience may be the issuer or an agreed-upon Authorization Server identifier depending on the validator. Never accept any audience or skip audience validation merely for compatibility with older clients. If the audience must change during an upgrade, implement a planned transition and test both old and new client/server versions.

## 8. Testing temporal and identity claims

Beyond signature and audience, verify that an assertion cannot be reused or transferred to another client by altering claims.

| Assertion variant | Outcome to verify |
|---|---|
| `iss` differs from `client_id` | Reject client authentication |
| `sub` differs from `client_id` | Reject client authentication |
| `aud` does not match Authorization Server | Reject client authentication |
| `exp` has elapsed | Reject |
| `iat` in the future beyond clock skew | Reject if validator checks issuance time |
| `exp` too far in the future | Reject if policy caps maximum assertion lifetime |
| Missing `jti` when replay protection requires it | Reject |
| `kid` absent from JWKS | Reject |
| `alg` outside allowlist or `none` | Reject |
| Invalid signature | Reject |

Keep assertion lifetimes short, typically just enough for a single token endpoint call plus allowed clock skew. The exact value must follow system policy. If clock skew is allowed, the replay store must retain `jti` at least until after `exp` plus clock skew so the assertion cannot be accepted again while the validator still considers the token active.

## 9. Designing and testing replay protection with `jti`

### 9.1. Why a replay store is needed

A validly signed JWT can be resubmitted multiple times within its `exp` window. Checking signature, `iss`, `sub`, `aud`, and timestamps only proves the assertion was created by a valid client and is within its validity window; those stateless checks do not prove the assertion has not been used.

To protect against replay, the Authorization Server must record accepted pairs of client identifier and `jti`. This store must be shared across instances. If each pod keeps an in-memory `Set`, the same assertion can be sent to pod A and then pod B and both will accept it.

A minimal contract:

```java
public interface ClientAssertionReplayStore {
    /**
     * Atomically reserves this jti until expiresAt.
     * Returns true only for the first successful reservation.
     */
    boolean reserve(String clientId, String jti, Instant expiresAt);
}
```

Implementations can use Redis with `SET key value NX EX ...` or a database with a unique constraint on `(client_id, jti)` and `expires_at`. Never implement this as separate `exists` followed by `insert` operations because two concurrent requests could both pass the existence check.

### 9.2. Validation ordering

Only reserve `jti` after the assertion has passed signature verification and basic claims such as issuer, subject, audience, expiration, and issuance time. If reserved first and an invalid audience is discovered afterward, an invalid assertion could occupy the `jti` and unintentionally cause a valid assertion regenerated with the same ID to be rejected.

In Spring Authorization Server, additional logic can be integrated through a custom validator on `JwtClientAssertionDecoderFactory` or a custom `JwtDecoderFactory` attached to `JwtClientAssertionAuthenticationProvider`, depending on the API version in use. The validator structure should execute logic in this order:

```java
OAuth2TokenValidator<Jwt> replayValidator(String clientId) {
    return jwt -> {
        String jti = jwt.getId();
        Instant expiresAt = jwt.getExpiresAt();

        if (!StringUtils.hasText(jti) || expiresAt == null) {
            return OAuth2TokenValidatorResult.failure(
                    new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
        }

        Instant retainUntil = expiresAt.plus(clockSkew);
        boolean firstUse = replayStore.reserve(clientId, jti, retainUntil);

        return firstUse
                ? OAuth2TokenValidatorResult.success()
                : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(OAuth2ErrorCodes.INVALID_CLIENT));
    };
}
```

This snippet illustrates the standalone validator; when wiring it into the decoder, run signature/issuer/subject/audience/time validators before the replay validator. You can compose an aggregate validator: run the baseline validators first, and invoke `replayStore.reserve` only when the result has no errors. The exact configuration API of `JwtClientAssertionDecoderFactory` must match your project's Spring Authorization Server version.

Do not return detailed errors such as "jti already exists" outside the token endpoint. You may emit metrics or audit events with assertion/token values redacted for operations, but never log the full JWT.

### 9.3. Testing replay of the same assertion

Create a valid assertion with a fixed `jti`, and send the first and second requests with that exact JWT string:

| Submission | Expected outcome |
|---|---|
| First attempt with `jti` not yet in store | Client authentication succeeds; grant may issue token |
| Second attempt with same assertion and `jti` | Reject client authentication; do not issue a second token |
| New assertion, new `jti` | May be accepted if other claims are valid |
| New assertion, previously used `jti` | Reject |
| Expired assertion | Reject, even if `jti` has not appeared in store |

Example integration test:

```java
String assertion = createClientAssertion(
        clientPrivateKey,
        "orders-service",
        expectedAudience,
        clock.instant(),
        "replay-test-001");

ResultActions first = postClientCredentials(assertion);
first.andExpect(status().isOk());

ResultActions replay = postClientCredentials(assertion);
replay.andExpect(jsonPath("$.error").value(OAuth2ErrorCodes.INVALID_CLIENT));
```

`postClientCredentials` is a test helper submitting the exact form parameters from the earlier section. If the application performs automatic retries, ensure retries never reuse an already-sent assertion; the client must generate a fresh assertion with a new `jti` for each authentication attempt.

### 9.4. Testing concurrency and multiple instances

Send the same assertion in two concurrent requests, or send it to two different Authorization Server instances sharing the replay store. Only one request may reserve `jti` and authenticate successfully. The remaining request must be rejected.

This scenario must use a real replay store or an implementation with equivalent atomic primitives. A unit test using a `HashSet` inside one JVM does not prove replay protection in a multi-instance deployment.

Also test behavior when the replay store is unavailable. For client assertion authentication, the system should fail closed: do not issue tokens if it cannot confirm `jti` has not been used. Never bypass the replay check just to preserve availability during a store outage.

## 10. Testing client key rotation

Clients may rotate their private keys and registered public JWKs. During a transition period, the server may need to accept both the old and new keys:

1. Client publishes the new public key with a new `kid` to JWKS.
2. Server fetches or synchronizes the new public key.
3. Client begins signing assertions with the new private key.
4. Client stops signing with the old private key.
5. Keep the old public key long enough for in-flight requests or valid retries to finish, per system policy.
6. Remove the old public key once assertions signed with it no longer need verification.

Test assertions signed with both the old key and the new key during the transition window. After the old key is removed and the server refreshes JWKS, assertions signed with the old key must be rejected. A `kid` must never be reused for a different key pair.

If the client uses a remote JWKS endpoint, test the server's cache and refresh behavior. If using a static key set stored with `RegisteredClient`, test the client registration update workflow and consistency across Authorization Server instances.

## 11. Security test matrix

| Category | Input | Expected outcome |
|---|---|---|
| Happy path | Valid signature, valid claims, fresh `jti` | Client authentication succeeds |
| Wrong signature | Signed with private key not matching registered public key | `invalid_client`, no token issued |
| Unknown `kid` | Header references a key absent from JWKS | `invalid_client`, no token issued |
| Wrong audience | Valid signature but wrong `aud` | `invalid_client`, no token issued |
| Wrong issuer | `iss` does not match client ID | `invalid_client` |
| Wrong subject | `sub` does not match client ID | `invalid_client` |
| Expired assertion | `exp` has elapsed | `invalid_client` |
| Future assertion | `iat` exceeds clock skew | Rejected by time validator |
| Missing jti | No `jti` when replay protection requires it | `invalid_client` |
| Replay | Resubmit same assertion and `jti` | Only first attempt may succeed |
| Concurrent replay | Two concurrent requests with same `jti` | At most one request succeeds |
| Cross-node replay | Send same assertion to two instances | At most one instance accepts |
| Replay store outage | Unable to reserve `jti` | Fail closed, no token issued |
| Algorithm downgrade | `alg` outside allowlist or `none` | Rejected |
| Client not registered for method | Client lacks `PRIVATE_KEY_JWT` | `invalid_client` |
| Client not allowed grant | Valid client auth but grant not registered | `unauthorized_client` |

Besides error codes, verify that no access token is created or persisted when client authentication fails. Responses must not contain assertions, private keys, internal JWKS, or detailed reasons why signature verification failed.

## 12. Test automation

Tests can be structured as follows:

```text
src/test/java/.../clientassertion/
  ClientAssertionFactory.java
  ClientAssertionSignatureTest.java
  ClientAssertionAudienceTest.java
  ClientAssertionClaimsTest.java
  ClientAssertionReplayTest.java
  ClientAssertionConcurrencyTest.java
  ClientAssertionKeyRotationTest.java
```

Implementation suggestions:

- Use Nimbus to generate key pairs and sign real JWT assertions.
- Use MockMvc or WebTestClient to invoke the token endpoint.
- Use a mutable JWKS stub to simulate registered public keys and key rotation.
- Use a fixed `Clock` to test `iat`, `exp`, and clock skew.
- Use Redis/Testcontainers or a real database for replay store and concurrency tests.
- Run tests across multiple instances or multiple application contexts when proving shared replay state.
- Generate a fresh assertion for every valid request; reuse the exact assertion only in replay tests.
- Mask tokens, assertions, secrets, and private keys from logs and test reports.

In CI, run baseline signature, audience, claim, and replay tests during integration builds. Run concurrency, replay store outage, and key rotation tests in pre-release/staging against production-equivalent infrastructure.

## 13. Pre-release checklist

- [ ] Client properly registers `PRIVATE_KEY_JWT` and its corresponding public key.
- [ ] `client_assertion_type` matches the standard JWT bearer client assertion URI.
- [ ] `iss` and `sub` match the client ID per contract.
- [ ] `aud` matches the audience the Authorization Server actually validates.
- [ ] `exp` is short and validated with clock skew.
- [ ] `iat` is validated per time policy.
- [ ] `kid` is unique and points to the appropriate public key.
- [ ] Signing algorithm is within the allowlist.
- [ ] Invalid signatures and unknown keys are rejected.
- [ ] Wrong audiences are rejected even when the signature is valid.
- [ ] `jti` is checked via a shared replay store if policy requires one-time assertions.
- [ ] Replay check reserves `jti` only after basic claims have passed validation.
- [ ] Two concurrent requests with the same `jti` cannot both succeed.
- [ ] Replay store failures cause the system to fail closed.
- [ ] Key rotation is tested across all instances.
- [ ] Token endpoint does not return sensitive details or credentials in error responses/logs.

## Conclusion

Testing `private_key_jwt` must simultaneously verify client identity, signature, audience, lifetime, and assertion uniqueness. A valid signature is not enough if the assertion was sent to the wrong Authorization Server; the presence of `jti` is also not enough if the server does not store and check it atomically. Use genuinely signed JWTs, invoke the token endpoint via integration tests, and test replay across multiple instances to prove client assertions cannot be forged or reused.
