# Testing Token Revocation, Issuer Failures, and Caching Policies

When deploying a **Spring Security OAuth 2.0 Resource Server**, you must address three easily conflated concerns simultaneously: whether a token verifies as valid, whether it remains effective after revocation, and how long authentication/authorization data stays cached.

An unexpired **JWT** with a valid signature, issuer, and audience can continue to be accepted by a Resource Server **after the Authorization Server has processed a revocation request**, if the application relies solely on `JwtDecoder` for local verification. Conversely, with **opaque tokens**, the Resource Server typically calls the introspection endpoint to check `active` status; if it caches `active=true` responses, that state can become stale after revocation.

Therefore, testing must separate:

1. **Revocation:** who sends the revocation request, how does the AS handle it, and when does the Resource Server learn of it?
2. **Issuer/AS failures:** how are tokens with the wrong issuer, signature, or audience handled, and what happens when JWKS, discovery, or introspection endpoints fail?
3. **Cache policies:** what are the TTL, key, capacity, invalidation, and staleness policies for JWKS, introspection, denylists, tenant configuration, and authorization decisions?

This lesson guides building a test suite from unit tests to integration tests for Servlet and WebFlux, including real signed JWTs, an HTTP introspection test server, clock/ticker-controlled caches, event propagation, and failure handling. **Never treat mock `Authentication` tests as proof of real signature or introspection verification.**

## 1. Lifecycle and Responsibility Map

~~~mermaid
flowchart TD
    C[OAuth client] -->|Token request| AS[Authorization Server]
    AS -->|Access token| C
    C -->|Bearer token| RS[Resource Server]
    C -->|RFC 7009 revocation request| AS
    RS --> M{Validation strategy}
    M -->|JWT local| J[JwtDecoder: JWS + claims]
    M -->|Opaque or introspected JWT| I[OpaqueTokenIntrospector]
    I --> CACHE{Positive introspection cache?}
    CACHE -->|Miss| AS2[AS introspection RFC 7662]
    CACHE -->|Valid hit| A[Authenticated principal]
    AS2 -->|active=true| A
    AS2 -->|active=false| X[Authentication failure]
    AS2 -->|Timeout or 5xx| E[No verification result]
    J -->|Valid| R{Revocation lookup?}
    J -->|Invalid| X
    R -->|Not revoked| A
    R -->|Revoked| X
    R -->|No lookup policy| A
    R -->|Store error| E
    A --> Z[Scope, role, tenant, ownership]
    Z -->|Authorized| OK[Allow]
    Z -->|Insufficient permission| D[403 or domain 404]
~~~

Notes:

- **RFC 7009** specifies the request from an OAuth client to the Authorization Server to revoke a token.
- **RFC 7662** specifies the request from a protected resource to the Authorization Server to determine a token's active state and metadata.
- The revocation endpoint is not an API the Resource Server calls on every request.
- A cache hit can be faster than introspection, yet **does not prove the token's current state at the AS**.

### 1.1. Four Distinct Concepts

| Concept | Question | Example |
|---|---|---|
| Signature verification | Was the token signed by a trusted key? | `RS256` + public JWK |
| Claim validation | Is the token for this API, unexpired, from a valid issuer? | `iss`, `aud`, `exp`, `nbf` |
| Revocation check | Was the token/grant/session revoked by the AS or internal policy? | `active=false`, `jti` denylist |
| Authorization | Is the principal permitted to operate on this resource? | `SCOPE_orders.read` and `tenant_id` |

A token can pass the first three conditions and still lack business-level permission.

## 2. RFC 7009: Token Revocation

An OAuth client may request token revocation when a user logs out, unlinks an account, an admin revokes a grant, an account is disabled, or credentials are compromised.

Example request:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: idp.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic <client-authentication>

token=example-refresh-token&token_type_hint=refresh_token
~~~

The endpoint path, client authentication, and support for revoking access tokens depend on the Authorization Server. `token_type_hint` is only a hint. Per RFC 7009, a successful response must not disclose whether a token existed.

### 2.1. Success at the Revocation Endpoint Is Not Enough

Suppose the AS issues a JWT expiring at 10:30 and receives a revocation call at 10:05:

~~~text
10:00  Access JWT issued, exp = 10:30
10:05  Client calls revocation endpoint, AS responds with success
10:06  Resource Server receives the previously issued JWT
10:06  Signature, iss, aud, exp are still valid
10:06  Without introspection or denylist lookup -> token may still pass
10:30  Token expires, decoder rejects it
~~~

This does not mean the decoder is broken. **Signature verification and revocation checking are two separate mechanisms.**

### 2.2. Refresh Token vs. Access Token Revocation

Revoking a refresh token typically stops further access tokens from being obtained under that grant, but does not guarantee in-flight access tokens are invalidated immediately. Whether access-token revocation is supported and how it affects related tokens depends on AS policy.

Therefore tests must verify:

- Is the revoked token an access token or a refresh token?
- Does the AS revoke the entire grant/token family?
- How long do circulating access tokens remain valid?
- How do Resource Servers receive the updated state?
- Are any caches extending the revocation window?

## 3. Choosing a Revocation Strategy

| Strategy | How it works | Pros | Limitations |
|---|---|---|---|
| Short-lived JWT | Wait for `exp`; refresh tokens managed centrally | Low per-request network cost | Window where old tokens still work |
| JWT + introspection | AS returns `active` per request | Centralized state | Depends on AS latency/availability |
| JWT + `jti` denylist | RS checks revoked state | Can revoke quickly | Requires shared state, TTL, fail-closed |
| JWT + session/token version | Match user/grant version | Useful for session revocation | Requires lookup/invalidation |
| Opaque introspection | AS checks `active` and returns metadata | Centralized policy | Network dependency |
| Event-driven revocation | AS pushes revoke events to nodes | Avoids polling AS constantly | Event loss, lag, multi-node consistency |

Choose a solution based on your **revocation SLA**: the maximum time between the AS revoking a token and every Resource Server rejecting it. Relying on short JWT `exp` alone cannot beat the remaining access token lifetime without an additional mechanism.

## 4. Opaque Tokens and JWT Introspection

Spring Security supports opaque tokens via **`OpaqueTokenIntrospector`** in Servlet and **`ReactiveOpaqueTokenIntrospector`** in WebFlux.

Spring Boot configuration example:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://idp.example.com/introspect
          client-id: orders-resource-server
          client-secret: ${INTROSPECTION_CLIENT_SECRET}
~~~

In Servlet:

~~~java
@Bean
SecurityFilterChain api(HttpSecurity http) throws Exception {
    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(Customizer.withDefaults())
        )
        .build();
}
~~~

Introspection response:

~~~json
{
  "active": true,
  "iss": "https://idp.example.com",
  "sub": "alice",
  "client_id": "orders-client",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"],
  "exp": 1893456000
}
~~~

Spring Security can map scopes to `SCOPE_orders.read` and `SCOPE_orders.write`; authorization then enforces the Resource Server's rules.

### 4.1. `active=false` vs. Missing Scope

| AS result | Authentication | Authorization |
|---|---|---|
| `active=false` | Fails | Never reaches permission checks |
| `active=true`, sufficient scope | Succeeds | May be permitted |
| `active=true`, missing scope | Succeeds | Denied, typically `403` |
| `active=true`, wrong tenant | Succeeds | Denied per tenant policy |
| Introspection timeout | No verification result | Must not create an active principal |
| Introspection `5xx` | No verification result | Must not fail open |

### 4.2. JWTs Can Also Be Introspected

Spring Security Opaque Token support does not require the token to actually be opaque-formatted; it sends the raw Bearer token to the introspection endpoint. Thus a JWT can also be verified via the AS if your security architecture requires centralized revocation checks.

In that case, the principal is typically **`OAuth2AuthenticatedPrincipal`** inside **`BearerTokenAuthentication`**, rather than **`Jwt`** inside **`JwtAuthenticationToken`**. Controller tests must use the matching `Authentication` type.

## 5. Testing with Mock Authentication: Scope and Limits

MockMvc offers `jwt()` and `opaqueToken()`; `WebTestClient` offers `mockJwt()` and `mockOpaqueToken()`. These helpers inject a simulated `Authentication` into the test context. They are useful for:

- Scope and role authorization.
- Testing controllers reading `sub`, `tenant_id`, and other claims.
- Testing ownership/resource permissions.
- Method security.
- Testing `403` when a principal lacks an authority.

Example:

~~~java
mvc.perform(get("/api/orders")
        .with(jwt().authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )))
    .andExpect(status().isOk());
~~~

**This helper does not invoke `JwtDecoder`**, does not verify signatures, and does not query a revocation store if revocation is integrated inside the decoder.

Similarly:

~~~java
webTestClient
    .mutateWith(mockOpaqueToken()
        .authorities(
            new SimpleGrantedAuthority("SCOPE_orders.read")
        )
    )
    .get()
    .uri("/api/orders")
    .exchange()
    .expectStatus().isOk();
~~~

**`mockOpaqueToken()` does not invoke `ReactiveOpaqueTokenIntrospector`**. Do not use this test to claim revocation or HTTP introspection works.

## 6. Testing Real Signed JWTs

To test signatures, issuer, audience, expiration, and custom revocation wrappers, generate a JWT with a test private key and send it via `Authorization: Bearer` through a real `SecurityFilterChain`.

### 6.1. Generating an RSA Test Key

~~~java
RSAKey rsaKey = new RSAKeyGenerator(2048)
    .keyID("test-rsa-1")
    .generate();

JWKSource<SecurityContext> signingSource =
    new ImmutableJWKSet<>(new JWKSet(rsaKey));

JwtEncoder encoder = new NimbusJwtEncoder(signingSource);

NimbusJwtDecoder decoder = NimbusJwtDecoder
    .withPublicKey(rsaKey.toRSAPublicKey())
    .build();
~~~

The private key stays strictly in the test encoder; the Resource Server receives only the public key. Never reuse production keys.

### 6.2. Configuring Issuer and Audience Validators

~~~java
String issuer = "https://issuer.test";
String audience = "orders-api";

OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
    jwt.getAudience().contains(audience)
        ? OAuth2TokenValidatorResult.success()
        : OAuth2TokenValidatorResult.failure(
            new OAuth2Error(
                "invalid_token",
                "Audience does not match resource",
                null
            )
        );

decoder.setJwtValidator(
    new DelegatingOAuth2TokenValidator<>(
        JwtValidators.createDefaultWithIssuer(issuer),
        audienceValidator
    )
);
~~~

Keep the default validators for timestamps, issuer, and other Spring Security version defaults. Never replace the entire chain with an audience-only validator.

### 6.3. Signing a JWT with `jti`

~~~java
Instant now = Instant.now();

JwtClaimsSet claims = JwtClaimsSet.builder()
    .issuer("https://issuer.test")
    .subject("alice")
    .audience(List.of("orders-api"))
    .issuedAt(now.minusSeconds(10))
    .expiresAt(now.plusSeconds(300))
    .id("jti-test-001")
    .claim("scope", "orders.read")
    .claim("tenant_id", "tenant-a")
    .build();

JwsHeader header = JwsHeader
    .with(SignatureAlgorithm.RS256)
    .keyId("test-rsa-1")
    .build();

String token = encoder.encode(
    JwtEncoderParameters.from(header, claims)
).getTokenValue();
~~~

Send the real token through the filter chain:

~~~java
mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer " + token))
    .andExpect(status().isOk());
~~~

This test requires MockMvc to have Spring Security filters attached. Never pass `.with(jwt())` on the request if you want the decoder and revocation checks to actually execute.

### 6.4. Negative Test Cases

| Test token | Outcome |
|---|---|
| Valid key, valid issuer/audience/timestamps | Authenticated |
| Token signed with another private key | `401`, invalid signature |
| Wrong issuer claim | `401`, issuer validator |
| Wrong audience claim | `401`, audience validator |
| Expired | `401` |
| `nbf` in the future beyond clock skew | `401` |
| Disallowed algorithm | Rejected |
| Valid signature but missing scope | Authenticated, `403` if policy requires scope |

Use a second key pair to produce an invalid signature; do not merely flip one character in the token and claim a specific signature algorithm was tested.

## 7. Testing JWT Revocation with a `jti` Denylist

Suppose the system maintains state:

~~~text
revoked:<issuer-id>:<jti>
~~~

The `issuer+jti` pair prevents token ID collisions across issuers. Only read `jti` **after the decoder has verified the JWT**.

### 7.1. Wrapping the Decoder in Servlet

~~~java
interface RevocationStore {
    boolean isRevoked(String issuer, String jti);
}

JwtDecoder revocationAwareDecoder(
        JwtDecoder delegate,
        RevocationStore store) {

    return compactToken -> {
        Jwt jwt = delegate.decode(compactToken);

        if (jwt.getIssuer() == null || jwt.getId() == null) {
            throw new JwtException("Required revocation claims are missing");
        }

        String issuer = jwt.getIssuer().toString();
        if (store.isRevoked(issuer, jwt.getId())) {
            throw new JwtException("Token has been revoked");
        }

        return jwt;
    };
}
~~~

Here `store.isRevoked` must semantically distinguish **verified false (not revoked)** from **store unavailable**. Never return `false` on timeout when fail-closed is a security requirement.

### 7.2. WebFlux Requires a Reactive Store

~~~java
interface ReactiveRevocationStore {
    Mono<Boolean> isRevoked(String issuer, String jti);
}

ReactiveJwtDecoder revocationAwareDecoder(
        ReactiveJwtDecoder delegate,
        ReactiveRevocationStore store) {

    return compactToken -> delegate.decode(compactToken)
        .flatMap(jwt -> {
            if (jwt.getIssuer() == null || jwt.getId() == null) {
                return Mono.error(
                    new JwtException("Required revocation claims are missing")
                );
            }

            return store.isRevoked(
                    jwt.getIssuer().toString(),
                    jwt.getId()
                )
                .flatMap(revoked ->
                    revoked
                        ? Mono.error(new JwtException("Token has been revoked"))
                        : Mono.just(jwt)
                );
        });
}
~~~

Never call `.block()` or `onErrorReturn(false)` in an authentication flow. When the store errors, authentication must not pass by default.

### 7.3. Testing the Denylist

1. Valid signed JWT whose `jti` is not in the store → authenticates.
2. Record `issuer+jti` in the store → the exact same token is rejected on the next request.
3. A token from another issuer with the same `jti` is unaffected if that issuer is independently valid.
4. JWT missing `jti` → rejected if policy mandates `jti`.
5. Store timeout → no successful `Authentication` created.
6. Denylist entries must live until `exp` plus the clock-skew margin.
7. Cache eviction must never allow a revoked token to be accepted again.

**Do not use `jwt()`/`mockJwt()` for these tests**, because those helpers skip the decoder wrapper.

## 8. Testing Real HTTP Introspection

To verify real code calls the Authorization Server properly, use an HTTP test server such as `MockWebServer` or WireMock. `SpringOpaqueTokenIntrospector` must be pointed at the local endpoint.

### 8.1. Servlet Introspector Test

~~~java
OpaqueTokenIntrospector introspector =
    SpringOpaqueTokenIntrospector
        .withIntrospectionUri(
            mockWebServer.url("/introspect").toString()
        )
        .clientId("test-resource-server")
        .clientSecret("test-client-secret")
        .build();
~~~

Wire into `HttpSecurity`:

~~~java
@Bean
SecurityFilterChain security(
        HttpSecurity http,
        OpaqueTokenIntrospector introspector) throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .requestMatchers(HttpMethod.GET, "/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .opaqueToken(opaque -> opaque.introspector(introspector))
        )
        .build();
}
~~~

### 8.2. `active=true`

~~~java
mockWebServer.enqueue(new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("""
        {
          "active": true,
          "sub": "alice",
          "scope": "orders.read",
          "tenant_id": "tenant-a"
        }
        """));

mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer test-opaque-token"))
    .andExpect(status().isOk());
~~~

Inspect the HTTP exchange:

~~~java
RecordedRequest request = mockWebServer.takeRequest(
    1, TimeUnit.SECONDS
);

assertThat(request).isNotNull();
assertThat(request.getMethod()).isEqualTo("POST");
assertThat(request.getPath()).isEqualTo("/introspect");
assertThat(request.getHeader("Authorization")).startsWith("Basic ");
assertThat(request.getBody().readUtf8())
    .contains("token=test-opaque-token");
~~~

This is an integration test against the introspector's real HTTP client using a test AS response. It does not assert that the production Authorization Server behaves identically.

### 8.3. `active=false`

~~~java
mockWebServer.enqueue(new MockResponse()
    .setResponseCode(200)
    .addHeader("Content-Type", "application/json")
    .setBody("{\"active\":false}"));

mvc.perform(get("/api/orders")
        .header(HttpHeaders.AUTHORIZATION, "Bearer revoked-token"))
    .andExpect(status().isUnauthorized());
~~~

No `Authentication` succeeds, and the controller is never invoked.

### 8.4. `active=true` Lacking Scope

~~~json
{
  "active": true,
  "sub": "alice",
  "scope": "orders.write"
}
~~~

`GET /api/orders` requiring `SCOPE_orders.read` normally returns `403`. Do not conflate this case with inactive-token tests.

### 8.5. Reactive Introspection

WebFlux uses:

~~~java
ReactiveOpaqueTokenIntrospector introspector =
    SpringReactiveOpaqueTokenIntrospector
        .withIntrospectionUri(
            mockWebServer.url("/introspect").toString()
        )
        .clientId("test-resource-server")
        .clientSecret("test-client-secret")
        .build();
~~~

Wire into `SecurityWebFilterChain` and send:

~~~java
webTestClient
    .get()
    .uri("/api/orders")
    .headers(headers -> headers.setBearerAuth("test-opaque-token"))
    .exchange()
    .expectStatus().isOk();
~~~

To confirm HTTP introspection actually ran, inspect the test server's `RecordedRequest`. Never use `mockOpaqueToken()` on this request.

## 9. Testing RFC 7009 End-to-End

An integration test against a sandbox Authorization Server can:

1. Provision a test user/client/grant in the test environment.
2. Acquire an access token and confirm the Resource Server request succeeds.
3. Call the revocation endpoint with that token.
4. Call the Resource Server again with the same token.
5. Measure the time until the Resource Server rejects it.
6. Repeat across multiple replicas.
7. Compare worst-case lag against the revocation SLA.
8. Clean up test client/grant/tokens.

~~~mermaid
sequenceDiagram
    participant T as Test client
    participant AS as Authorization Server
    participant RS as Resource Server
    T->>AS: Request test access token
    AS-->>T: Access token
    T->>RS: GET /api/orders + Bearer
    RS-->>T: 200
    T->>AS: POST /revoke (RFC 7009)
    AS-->>T: Revocation response
    T->>RS: Same Bearer token
    RS->>AS: Introspection or revocation state lookup
    AS-->>RS: inactive / revoked
    RS-->>T: 401
~~~

In an architecture using only local JWT validation without a revocation lookup, the final step may keep succeeding until `exp`. Tests must reflect the actual policy rather than assuming immediate `401` is default `JwtDecoder` behavior.

## 10. Issuer Validation and Authorization Server Failures

A wrong issuer differs from an unreachable issuer.

| Scenario | Meaning | Security outcome |
|---|---|---|
| Malformed JWT | Token cannot be parsed | Unauthenticated |
| Invalid signature | Not signed by a trusted key | Unauthenticated |
| Wrong issuer | Issuer claim does not match trusted issuer | Unauthenticated |
| Wrong audience | Token intended for another resource | Unauthenticated |
| Expired / `nbf` | Time constraints failed | Unauthenticated |
| JWKS HTTP `404`/`5xx` | Cannot fetch required key | Never skip signature verification |
| JWKS timeout | Key retrieval failure | Never trust unverified keys |
| Metadata discovery error | No valid issuer/JWKS configuration | Never synthesize trust from request input |
| Introspection `active=false` | Inactive token | Authentication failure |
| Introspection `401`/`403` | Client auth/configuration error | Never create an active principal |
| Introspection timeout/`5xx` | AS/network unavailable | Never fail open |
| Tenant registry error | Trust configuration undetermined | Never fall back to another tenant |

### 10.1. Issuer Mismatch

For example, the Resource Server trusts `https://id-a.example.com`, yet the JWT carries `iss=https://id-b.example.com`. Even if another key could verify the signature, the token must be rejected by the API's issuer/audience policy.

In multi-tenant setups, an unverified JWT issuer can only act as a **routing hint** into a trusted issuer registry. Never construct a decoder/JWKS client for an arbitrary issuer URL supplied by a JWT.

### 10.2. JWKS Outage: Cache Hit vs. Cache Miss

If the decoder already has the public key cached, a JWT can still verify while the JWKS endpoint is temporarily down, per cache policy. When encountering a new, uncached key, the decoder must fetch a valid public key; if it cannot, the signature cannot be verified.

Test separately:

- Cached key + JWKS down.
- New `kid` + JWKS down.
- Invalid signature while JWKS is healthy.
- Issuer mismatch even when a key verifies.
- Timeouts exceeding the request budget.

Do not treat every JWKS outage as an invalid token, yet never accept unverified tokens just to preserve availability.

### 10.3. Introspection Timeout/`5xx`

Without a trustworthy `active` result, never build a successful `Authentication`. Exact HTTP statuses may depend on exception translation and API error policy; tests must confirm no protected data is returned and errors are accurately classified, rather than assuming every infrastructure timeout always yields `401`.

## 11. Key Rotation and JWKS Caching

A JWT header may contain:

~~~json
{
  "alg": "RS256",
  "kid": "key-2026-02",
  "typ": "JWT"
}
~~~

Normal rotation:

1. AS publishes the new public key on JWKS.
2. AS starts signing new tokens with the matching private key.
3. Resource Servers refresh JWKS and discover the new key.
4. AS retains the old key during overlap so unexpired tokens remain verifiable.
5. AS removes the old key once policy permits.

### 11.1. Testing Rotation

- A token signed with key A is accepted while JWKS contains A.
- Publish key B, sign a token with B; the decoder refreshes and accepts B.
- A token signed with an unknown key is rejected.
- Remove A and determine when all nodes stop accepting tokens signed with A.
- Unknown `kid`s do not cause refresh storms or unbounded cache entries.
- Issuer A's keys are never used in Issuer B's trust context.

### 11.2. Emergency Key Compromise

Removing a key from JWKS does not guarantee every node notices immediately. JWKS caches may retain a compromised key until refresh/invalidation. An emergency plan is needed: invalidate key caches, trigger refreshes, revoke affected tokens, or update trust configuration.

Never use key rotation as a substitute for revoking a specific token when many tokens share the same signing key.

## 12. Distinguishing Types of Caches

| Cache | Data | Security impact |
|---|---|---|
| JWKS/key cache | Public keys per issuer | Rotation and compromise |
| Positive introspection cache | `active=true` and attributes | Revocation lag |
| Negative introspection cache | `active=false` | Cache cardinality and stale negatives |
| JWT denylist | `issuer+jti` or token fingerprint | If entries drop before `exp`, revoked JWTs may be accepted |
| Tenant metadata cache | Issuer, audience, active state, policy version | Disabled tenants/new policies not applied |
| Authorization decision cache | Subject, resource, action, tenant, policy | Revoked permissions persist in cached decisions |
| Decoder/manager cache | Validator/key source/HTTP client objects | Reusing stale trust configurations |

**A JWKS cache is not a revocation cache.** It only supports signature verification.

### 12.1. Positive Introspection Cache Creates a Stale Window

~~~text
10:00:00  Introspection -> active=true, cache TTL 10s
10:00:02  Authorization Server revokes token
10:00:05  Resource Server cache hit -> still active=true
10:00:10  TTL expires
10:00:11  New introspection -> active=false
~~~

This interval is cache-induced revocation lag. If the revocation SLA is at most 5 seconds, a 10-second TTL is unacceptable unless event invalidation is proven to satisfy the SLA.

### 12.2. Positive Result TTL Must Not Exceed Token `exp`

A policy:

~~~text
effective cache TTL =
    min(configured positive TTL,
        remaining token lifetime,
        allowed revocation staleness)
~~~

If the response lacks `exp`, a maximum token lifetime guaranteed by the issuer contract is required before caching positive results for long; otherwise disable positive caching or pick a very short TTL per risk acceptance.

### 12.3. Negative Caches Must Not Grow Unbounded

Caching `active=false` can mitigate repeated invalid-token requests, but requires a short TTL and maximum size. Never cache HTTP infrastructure exceptions as `active=false`; timeouts are infrastructure failures, not token state.

### 12.4. Denylists Must Survive Until `exp`

If a revoked `jti` entry is evicted before `exp`, a local `JwtDecoder` can still verify the token and the revocation lookup will return "not found," allowing acceptance again. The store must enforce retention until `exp` plus clock skew, or use another mechanism ensuring the token cannot be re-accepted.

## 13. Cache Keys, Isolation, and Policy Versions

Never use raw Bearer tokens in Redis keys, logs, or metric labels. You can use a SHA-256/HMAC-SHA-256 token fingerprint aligned with your threat model and key management.

Example logical keys:

~~~text
introspection : issuer-id : resource-id : token-fingerprint
revocation    : issuer-id : jti
tenant        : tenant-id : policy-revision
jwt-manager   : issuer-id : audience : validator-revision
authorization : tenant-id : subject : resource : action : policy-revision
~~~

Never reuse an `active` result from Issuer A for Issuer B or reuse authorization decisions across different tenants. When audience policies, role mappings, or tenant status change, bump the revision/invalidate the cache.

### 13.1. Local vs. Distributed Caches

A local Caffeine cache offers low latency, though each application replica holds separate state. Distributed caches share revocation state at the cost of network failure modes. In WebFlux, never call blocking cache APIs on the Reactor event loop.

### 13.2. Event Invalidation and Reconciliation

Events you can emit:

~~~text
TokenRevoked(issuerId, jti, exp)
TenantDisabled(tenantId, policyRevision)
UserDisabled(issuerId, subject, revision)
SigningKeyCompromised(issuerId, kid)
~~~

Nodes must invalidate affected cache entries. Events can be lost; design for durable delivery, retries, idempotency, and periodic reconciliation. Never assume instantaneous propagation without measuring worst-case lag.

## 14. Example Positive Introspection Cache Decorator

Caffeine can cache the result of an `OpaqueTokenIntrospector` after the delegate verifies it. Servlet example:

~~~java
final class CachedOpaqueIntrospector implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final Clock clock;
    private final Cache<String, OAuth2AuthenticatedPrincipal> cache;

    CachedOpaqueIntrospector(
            OpaqueTokenIntrospector delegate,
            Clock clock) {
        this.delegate = delegate;
        this.clock = clock;
        this.cache = Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(Duration.ofSeconds(2))
            .build();
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        String fingerprint = fingerprint(token);

        OAuth2AuthenticatedPrincipal cached =
            cache.getIfPresent(fingerprint);

        if (cached != null) {
            if (notExpired(cached)) {
                return cached;
            }
            cache.invalidate(fingerprint);
        }

        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        if (notExpired(principal)) {
            cache.put(fingerprint, principal);
        }

        return principal;
    }

    private boolean notExpired(OAuth2AuthenticatedPrincipal principal) {
        Object rawExp = principal.getAttribute("exp");
        Instant expiration;

        if (rawExp instanceof Instant instant) {
            expiration = instant;
        }
        else if (rawExp instanceof Number epochSeconds) {
            expiration = Instant.ofEpochSecond(epochSeconds.longValue());
        }
        else {
            return false;
        }

        return clock.instant().isBefore(expiration);
    }

    private static String fingerprint(String token) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256")
                .digest(token.getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        }
        catch (NoSuchAlgorithmException e) {
            throw new IllegalStateException("SHA-256 unavailable", e);
        }
    }
}
~~~

**This illustrates local caching, not a complete production implementation.**

- A two-second TTL is only an example, not a default SLA.
- Cache reads check `exp` themselves so cached principals are never returned after expiration.
- In multi-issuer/multi-resource systems, namespace the fingerprint key.
- Support immediate entry invalidation on revocation events if required by SLA.
- Never cache failed introspections, inactive results as principals, or exceptions as positive results.
- Account for memory, concurrency, cache stampedes, and data protection.
- Consider an HMAC fingerprint instead of a plain hash to prevent offline comparison for low-entropy tokens.
- Isolate cached results if principal attributes contain personal data.

In WebFlux, use a reactive decorator with a non-blocking cache/store or asynchronous loading. Never call `.block()` inside a reactive introspector.

## 15. Testing Caches with Fake Clocks/Tickers

Avoid long `Thread.sleep` calls when you can test deterministically using a fake `Clock` and cache `Ticker`.

### 15.1. Testing Hits/Misses

~~~java
AtomicInteger calls = new AtomicInteger();

OpaqueTokenIntrospector delegate = token -> {
    calls.incrementAndGet();
    return principalWithValidExpiration(token);
};
~~~

Scenario:

1. Request 1: delegate is called, principal is cached.
2. Request 2 within TTL: cache hit, `calls` does not increment.
3. Advance the test ticker past TTL.
4. Request 3: delegate is called again.
5. Delegate returns inactive: authentication fails.
6. Delegate times out: no positive cache entry is created.

### 15.2. Testing Revocation Before TTL Expiration

~~~text
T0: active=true -> cached
T1: AS revokes token
T2: request cache hit -> may still return 200 per stale policy
T3: revoke event arrives -> invalidate positive entry
T4: request calls AS -> active=false -> 401
~~~

Measure `T4 - T1` and compare with the revocation SLA. If the SLA demands immediacy, positive caches with stale windows are unacceptable unless invalidation guarantees the bound.

### 15.3. Testing Token `exp` Before Cache TTL

Token `exp` has one second left while cache TTL is two seconds. Advance the clock by two seconds; the cache must not return an active principal past `exp` even if the cache entry has not yet been evicted automatically.

### 15.4. Testing Errors Are Not Cached

- Introspector times out on request 1.
- Test server recovers and returns `active=true` on request 2.
- Request 2 must invoke the delegate again, rather than serving a cached error or bogus principal.

## 16. Handling Issuer Outages and Fail-Closed Policy

There is no single universal fallback for all errors. Define each case:

| Incident | Ability to continue | Boundary never to cross |
|---|---|---|
| JWKS server down, key cached | Can continue verifying with still-trusted key | Never drop signature/issuer validation |
| JWKS down, new key needed | Cannot verify | Never treat token as valid |
| Introspection down, no cache | No `active` status | Never create a successful `Authentication` |
| Introspection down, valid positive cache TTL | Per stale policy and revoke SLA | Never exceed `exp`/SLA |
| Revocation store down | Fail closed if lookup is mandatory | Never map errors to "not revoked" |
| Tenant registry down | Can use age-bounded trusted snapshot or reject | Never build tenant/issuer from arbitrary request input |
| Event broker down | Caches may go stale | Require TTLs and reconciliation |
| Signing key compromised | Emergency invalidate/rotate | Never keep trusting key indefinitely |

### 16.1. Never Disclose Internal Information

Client responses must never expose raw Bearer tokens, introspection client secrets, JWKS/internal URLs, TLS credentials, or stack traces. Internal logs should include correlation IDs, logical issuer/tenant identifiers, error categories, and request timings.

### 16.2. `401`, `403`, and Infrastructure Errors

- **`401`:** missing token or authentication failure (signature, expiry, inactive).
- **`403`:** authenticated, yet lacking authority/role/resource permission.
- **AS/JWKS infrastructure errors:** exact status codes depend on exception translation and API contract; never assume every timeout always returns `401`.

Tests must verify **protected data is never returned without verification** and errors are categorized clearly enough for operations.

## 17. Testing Multiple Resource Server Replicas

If each node maintains a local cache, revocation can take effect at different times across nodes.

~~~text
Node A cache expires at 10:00:05
Node B cache expires at 10:00:09
Node C cache expires at 10:00:07

10:00:03 token revoked
10:00:04 A/B/C may still cache active=true
10:00:05 A introspects again
10:00:07 C introspects again
10:00:09 B introspects again
~~~

Multi-node testing:

1. Send the token through each replica to populate cache entries.
2. Revoke the token at the AS or emit the revocation event.
3. Periodically resend the token through every replica.
4. Measure when the last node begins rejecting it.
5. Test event broker outages and restarts.
6. Verify a fresh replica does not reconstruct stale `active` state.
7. Verify issuer/tenant cache isolation.
8. Compare worst-case lag against SLA.

Never measure only the average or a single favorable node.

## 18. Observability and Auditing

Useful metrics:

| Metric group | Purpose |
|---|---|
| Introspection request count/latency | Measure AS load and p95/p99 |
| Introspection active/inactive/errors | Distinguish invalid tokens from AS outages |
| Positive/negative cache hits/misses | Understand stale windows and efficiency |
| JWT validator failures | Signature, issuer, audience, timestamp |
| JWKS refreshes and unknown `kid`s | Key rotation, abuse, outages |
| Revocation lookup latency/errors | State store availability |
| Revocation propagation lag | Multi-node SLA compliance |
| Tenant policy revision | Detect stale configurations |

Never use tokens, subjects, `jti`, or fingerprints as unbounded-cardinality metric labels. Audit logs must minimize sensitive data and apply retention policies.

## 19. Comprehensive Test Matrix

| Scenario | Test setup | What to prove |
|---|---|---|
| Valid JWT | Test RSA key + real decoder | Valid signature/claims |
| JWT wrong issuer | Signed token, different `iss` | Issuer validation |
| JWT wrong audience | Signed token, different `aud` | Audience validation |
| JWT invalid signature | Different key | Authentication failure |
| Revoked JWT | Valid JWT + `jti` denylist | Requests after revoke are rejected |
| Revocation store timeout | Faulty mock store | Fail-closed |
| Opaque `active=true` | HTTP introspection server | Principal/authorities created |
| Opaque `active=false` | Inactive HTTP response | Authentication failure |
| Opaque missing scope | `active=true`, wrong scope | Authorization `403` |
| Wrong introspection client credentials | AS returns `401`/`403` | No authenticated principal |
| Introspection timeout/`5xx` | HTTP stub fault | No active caching/fail-open |
| JWKS down/cache hit | Cached key | Stale-key policy works properly |
| JWKS down/cache miss | Unknown key | Unverified new key is not trusted |
| Unknown `kid` flood | Many random `kid`s | Refresh is bounded |
| Stale positive cache | Revoked within TTL | Lag is measured |
| Cache invalidation event | Remove entry | Subsequent request calls AS again |
| Token `exp` before TTL | Fake clock | Expired principal is not used |
| Tenant disabled | Bump policy version | Old manager/cache grants no access |
| Multi-node revoke | Multiple replicas | Worst-case SLA is upheld |

## 20. Common Anti-Patterns

**Calling RFC 7009 and assuming every JWT is rejected immediately.** Local decoders do not learn about revocations automatically.

**Using `jwt()` or `mockJwt()` to test a denylist inside the decoder.** The helpers fabricate `Authentication` without calling the decoder.

**Using `opaqueToken()` or `mockOpaqueToken()` to test HTTP introspection.** The helpers bypass the introspector.

**Caching `active=true` indefinitely or longer than `exp`.** Expired/revoked tokens may continue to be accepted.

**Optimizing cache hit ratio while ignoring the revocation SLA.** Improves performance while breaking revocation guarantees.

**Using the JWKS cache as a substitute for token revocation.** Public keys do not represent token state.

**Evicting revoked `jti` entries before `exp`.** Tokens can revert to being accepted.

**Caching timeouts as `active=true`.** Turns an AS outage into fail-open behavior.

**Using `onErrorReturn(false)` for denylist lookups.** Store errors silently become "not revoked."

**Not namespacing caches by issuer/resource.** Easily mixes trust domains.

**Reading an unverified issuer URL and creating a decoder.** Risks SSRF and unintended trust expansion.

**Not testing cached-key JWKS outages separately from cache misses.** Fails to reveal actual runtime behavior.

**Testing only one node.** Fails to prove cluster-wide revocation SLAs.

**Logging full introspection responses or Bearer tokens.** Leaks credentials and personal data.

## 21. Implementation and Testing Workflow

**Step 1 — Define the token strategy.** Local JWT, JWT + denylist, JWT introspection, or opaque introspection.

**Step 2 — Document the revocation SLA.** Maximum time a revoked token may still be accepted.

**Step 3 — Map all state/caches.** JWKS, positive/negative introspection, denylists, tenant metadata, authorization decisions.

**Step 4 — Set cache keys/TTLs/capacities.** Namespace by issuer/resource/tenant; positive TTL never exceeds `exp` or SLA; denylist lasts until `exp` + skew.

**Step 5 — Test scope/tenant policies with mock identity helpers.** Never use them in place of signature/introspection tests.

**Step 6 — Sign test JWTs and pass Bearer tokens through a real decoder.** Verify signature, issuer, audience, and `exp`/`nbf`.

**Step 7 — Test JWT revocation lookups.** Populate the denylist, test rejections, and test store failures.

**Step 8 — Stand up an introspection HTTP server.** Test `active` true/false, client credentials, bodies, timeouts, `5xx`, and scopes.

**Step 9 — Test cache hits/misses/invalidation.** Use fake clocks/tickers; avoid long sleeps.

**Step 10 — Test key rotation/issuer outages.** Cached keys, unknown `kid`, JWKS timeouts, discovery mismatches.

**Step 11 — Test event propagation across multiple replicas.** Measure worst-case revoke lag.

**Step 12 — Run AS sandbox contract tests.** Verify real issuer RFC 7009 and RFC 7662 behavior.

**Step 13 — Monitor metrics and audits.** Never put tokens/secrets into logs or labels.

## 22. Self-Check Questions

**1. What does RFC 7009 define?**

An endpoint for OAuth clients to request that the Authorization Server revoke a token.

**2. What does RFC 7662 define?**

Token introspection: a protected resource queries a token's `active` status and attributes.

**3. Does `JwtDecoder` automatically reject a revoked JWT?**

No, if the decoder only verifies signatures and claims without an additional revocation check.

**4. How do `active=false` and `active=true` lacking scope differ?**

`active=false` is an authentication failure; `active=true` lacking scope typically results in an authorization `403`.

**5. Does the JWKS cache tell you whether a token is revoked?**

No. JWKS contains only public keys.

**6. What risk does positive introspection caching introduce?**

A cached `active=true` entry can still be used after the token has been revoked.

**7. Can a positive cache exceed `exp`?**

No. It must be bounded by remaining lifetime and checked on read.

**8. Why does a denylist need `issuer+jti`?**

To avoid token ID collisions across issuers.

**9. If the revocation store times out, should the token be treated as unrevoked?**

No when lookup is mandatory; that is fail-open.

**10. Does JWKS downtime cause all JWTs to fail?**

Not necessarily. Cached keys can still verify, while unknown new keys must not be trusted.

**11. Does `mockOpaqueToken` call real introspection?**

No. You need a Bearer request through the filter chain and an HTTP introspection test server.

**12. Why test multiple replicas?**

Each replica has separate caches/invalidation timing, which can extend revocation lag.

## Conclusion

Token revocation, issuer failures, and caching are fundamentally about **the lifetime and scope of credential trust**. RFC 7009 lets OAuth clients request revocation; RFC 7662 lets Resource Servers check status. Local JWT validation does not automatically detect revocation, while introspection centralizes state at the cost of a network dependency.

JWKS caches affect key rotation; positive introspection caches affect revocation lag; denylists track revoked tokens; tenant and authorization caches store trust/policy decisions. Each type requires its own TTL, cache key, capacity, invalidation, and consistency rules.

Your test suite must cover signed JWTs, issuer/audience/signature failures, JWKS key rotation/outages, introspection `active` true/false, timeouts/`5xx`, revocation lookups, cache staleness/invalidation, token `exp`, and multi-node propagation. **Never fail open without a trusted verification result; never retain positive caches past `exp` or beyond the revocation SLA; and never let cache eviction allow a revoked JWT to be accepted again.**

### References

- [Spring Security — Servlet JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [Spring Security — Servlet Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — Servlet OAuth2 Resource Server Testing](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html)
- [Spring Security — WebFlux OAuth2 Testing](https://docs.spring.io/spring-security/reference/reactive/test/web/oauth2.html)
- [Spring Security API — OpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security API — ReactiveOpaqueTokenIntrospector](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517)
- [Caffeine — Eviction](https://github.com/ben-manes/caffeine/wiki/Eviction)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
