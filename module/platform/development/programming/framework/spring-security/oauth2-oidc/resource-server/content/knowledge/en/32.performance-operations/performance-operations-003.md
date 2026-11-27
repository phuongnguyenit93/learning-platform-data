# JWKS Caching vs. Introspection Caching and Their Distinct Goals

## 1. Two Cache Types Solve Two Different Problems

A Spring Security OAuth 2.0 Resource Server typically validates access tokens in two ways:

- **JWT validation**: the Resource Server verifies the JWT signature using public keys retrieved from a JSON Web Key Set (JWKS), then checks issuer, audience, timestamps, and claims per policy.
- **Opaque token introspection**: the Resource Server sends the token to the Authorization Server (AS), receives the introspection result, and builds a principal if the token is active.

Both flows can use caching, but the cached data and operational goals differ.

The **JWKS cache** stores the set of public keys (JWK Set) so the Resource Server does not have to fetch keys from the AS on every request. It primarily optimizes distribution and refresh of the trust material used to verify signatures.

The **introspection cache** stores the verification result of individual access tokens, typically including active, scope, subject, audience, expiration, and other attributes. It reduces how often the Resource Server calls the introspection endpoint, but can delay when the Resource Server observes token revocation or permission changes.

| Aspect | JWKS cache | Introspection cache |
|---|---|---|
| Cached object | Public JWK set of an issuer | Introspection result for a single token |
| Cache key | JWKS URI / issuer trust domain | Token fingerprint + issuer/resource context |
| Represented data | Signature verification keys | Token state and metadata |
| Access frequency | When the decoder needs the JWK set or a refresh | Potentially tied to every request/token |
| Primary goal | Reduce key fetches, support key rotation and availability | Reduce network round trips to the AS, reduce introspection load |
| Revocation impact | Key removal can affect many tokens sharing that key | Positive results may still be used after a token is revoked |
| Unit of freshness | JWK set | Token-specific authentication result |
| Primary risk | Using an old key or mistimed refresh | Accepting stale active status or claims |
| Sensitive data | Public keys, trust metadata | Principal attributes, scopes, subject, tenant data |
| Invalidation | Key rotation, issuer/JWKS changes | Token revocation, grant/permission changes, exp |

**Never substitute one cache for the other.** A JWKS cache does not reduce introspection calls for opaque tokens. An introspection cache does not supply public keys for verifying JWT signatures.

## 2. Both Authentication Flows Seen from a Caching Perspective

### JWT: Cache Keys, Still Verify Every Token

~~~mermaid
flowchart TD
    A["HTTP Bearer JWT"] --> B["JWT Decoder"]
    B --> C{"Usable JWK set in cache?"}
    C -->|Yes| D["Use matching public key"]
    C -->|No| E["Fetch / refresh trusted JWKS"]
    E --> D
    D --> F["Verify signature"]
    F --> G["Validate iss, aud, exp, nbf, profile"]
    G --> H["Authentication"]
~~~

The cache holds public keys. Every JWT request still goes through signature verification and validators. A cached JWK set does not mean every token signed by a key in that set is valid; a token can still have a bad signature, be expired, have the wrong audience, or have the wrong issuer.

### Opaque: Cache Token-Specific Results

~~~mermaid
flowchart TD
    A["HTTP Bearer opaque token"] --> B["ReactiveOpaqueTokenIntrospector"]
    B --> C{"Valid entry in cache?"}
    C -->|Yes| D["Use cached result per policy"]
    C -->|No| E["Call trusted introspection endpoint"]
    E --> F{"active?"}
    F -->|true| G["Cache active result with bounded TTL"]
    F -->|false| H["Reject; optionally short negative cache"]
    G --> I["Build authenticated principal"]
    D --> J["Check freshness and expiration"]
    J --> I
~~~

The introspection cache stores per-token results. If the AS revokes a token right after the Resource Server caches active=true, the RS may continue accepting the token until the entry's TTL expires or it is invalidated. This is a trade-off that must be decided by the revocation SLA.

## 3. What Is JWKS and Why Does the Resource Server Need to Cache It?

A JWKS is a JSON object containing a set of JSON Web Keys. For asymmetrically signed JWTs, the Authorization Server publishes public keys so Resource Servers can verify signatures.

Example:

~~~http
GET /oauth2/jwks HTTP/1.1
Host: auth.example.com
~~~

Illustrative response:

~~~json
{
  "keys": [
    {
      "kty": "RSA",
      "kid": "shop-signing-2026-02",
      "use": "sig",
      "alg": "RS256",
      "n": "base64url-modulus",
      "e": "AQAB"
    }
  ]
}
~~~

The JWT JOSE header can indicate a key ID:

~~~json
{
  "alg": "RS256",
  "kid": "shop-signing-2026-02",
  "typ": "at+jwt"
}
~~~

The decoder uses kid to locate a candidate key in the trusted JWK set, then verifies the signature. kid is a key-selection hint within an already-trusted JWK set; it does not authenticate a token by itself.

### Without JWKS Caching

Suppose an API receives 5,000 requests per second. If every request had to fetch JWKS:
- The AS would have to serve thousands of unnecessary HTTP calls.
- API latency would depend directly on the network path to the AS.
- An AS outage would prevent the entire API from verifying JWTs.
- Multiple Resource Server instances could trigger a thundering herd.
- Network and TLS handshake overhead would climb.

With caching, the decoder typically reuses the fetched key set and only refreshes according to cache policy, when an unknown key is encountered, or when the cache expires per the implementation.

### Caching JWKS Does Not Cache Authorization Results

Suppose key K1 is cached:

~~~text
Request 1:
  JWT signature valid with K1
  iss/aud/exp/nbf valid
  -> Authentication success

Request 2:
  JWT uses K1 but exp has passed
  -> Authentication failure

Request 3:
  JWT uses K1 but aud is wrong
  -> Authentication failure
~~~

The same public key can verify signatures for many different tokens. Each token still has to be checked against claims and policy individually.

## 4. Where Can the JWKS Cache Live?

~~~text
Resource Server
   |
   +-- Nimbus/JWK source in-process cache
   |
   +-- HTTP client / proxy cache (if permitted)
   |
   +-- CDN or gateway cache (if securely configured)
   |
   +-- Authorization Server JWKS service
~~~

Not every application uses all of these layers. Each layer can have different TTLs, stale behaviors, and invalidation rules.

### Decoder In-Memory Cache

Spring Security JWT Resource Server typically uses Nimbus JOSE + JWT to load the JWK set from a URI. Remote JWK retrieval caching behavior is determined by the Nimbus/Spring Security version and its configuration.

Do not assume the same default TTL applies across all versions. Inspect the actual dependency version, JWK source, HTTP client, and cache configuration in your runtime.

### HTTP Cache / CDN

If the JWKS endpoint sits behind a reverse proxy or CDN, ensure:
- Cache keys include the proper host/path and any factors affecting the response.
- Metadata or key sets from different issuers are never cached under the same key.
- Cache-Control/max-age matches the key rotation SLA.
- Origin TLS is verified.
- Invalidation/purging has an operational procedure.
- Arbitrary requests cannot craft JWKS URLs or cache namespaces.
- stale-if-error is not applied beyond approved policy.

Public keys are not secrets, but **the source of public keys is trust material**. Caching the wrong issuer or wrong endpoint can still compromise authentication decisions.

### Discovery Metadata Is a Separate Cache

OIDC discovery metadata typically provides issuer, jwks_uri, and other endpoints. The metadata cache and the JWKS cache are two distinct objects.

~~~text
Issuer metadata:
  issuer
  jwks_uri
  authorization_endpoint
  token_endpoint
       |
       v
JWKS:
  keys[]
       |
       v
JWT signature verification
~~~

A test or metric confirming a JWKS cache hit does not automatically prove metadata discovery caching works, and vice versa.

## 5. How Does JWKS TTL Affect Key Rotation?

Suppose the AS currently signs with K1 and wants to transition to K2.

~~~text
Phase 1 - Publish:
  JWKS = { K1, K2 }
  AS still signs tokens with K1

Phase 2 - Switch signer:
  JWKS = { K1, K2 }
  AS starts signing new tokens with K2

Phase 3 - Overlap:
  JWKS = { K1, K2 }
  Tokens signed by both K1 and K2 exist

Phase 4 - Retire:
  JWKS = { K2 }
  K1 is removed after old tokens expire and overlap policy completes
~~~

A safe process typically requires:
1. Publishing the new public key before the AS starts signing with the corresponding private key.
2. Giving Resource Servers enough time to refresh JWKS.
3. Switching the signer to the new key.
4. Keeping the old public key during an overlap window long enough for still-valid JWTs.
5. Retiring the old key after tokens signed by it expire, plus clock skew and policy-defined cache/propagation margins.
6. Monitoring unknown-kid, signature failures, and JWKS refresh errors.

### Why Does Removing K1 from JWKS Not Take Effect Immediately?

A Resource Server may hold a cached JWKS that includes K1. If its cache has not refreshed yet, the decoder can still find K1 and verify old tokens. A CDN or proxy may also still hold an older JWKS copy.

Therefore, the moment K1 is removed on the AS does not mean every RS immediately forgets K1.

### Unknown kid and Refreshes

When a JWT carries a kid not present in the cached JWK set, the implementation may attempt to refresh the remote JWK set to find the new key. Exact behavior depends on the Nimbus/Spring Security version and JWK source.

Protect the JWKS endpoint against refresh storms:
- Rate-limit refreshes triggered by unknown kids.
- Coalesce concurrent refresh requests if supported by the implementation.
- Use timeouts and bounded retries.
- Never fetch URLs from untrusted jku/x5u headers.
- Never try another issuer simply because a kid is missing.
- Track unknown-kid request rates to detect abuse or broken rotations.

Attackers can send many JWTs with random kids to trigger refreshes. Cache policy must account for DoS, not just latency.

## 6. JWKS Caching and Availability During an AS Outage

When the AS/JWKS endpoint is unavailable, the outcome depends on whether the Resource Server already has a matching key in cache and how long cache policy permits using cached keys.

| State | Possible Behavior |
|---|---|
| Cached JWK still usable, token uses that key | Decoder can verify with cached key without network call |
| Cache miss, new key needed, JWKS unavailable | No key to verify; request must fail closed |
| Token has unknown kid, refresh fails | Must not blindly trust token |
| JWKS endpoint returns malformed set | Do not overwrite trust material with invalid response |
| Cache expired and implementation requires refresh | Behavior depends on cache/stale policy |
| Key compromise announced but cache not yet invalidated | Window of using the old key may remain |

### Using Cached Keys During an Outage Is a Trade-Off

Continuing to use public keys already fetched from a trusted issuer can keep APIs running while the AS is temporarily down. However, if a key has just been compromised and removed from JWKS, a stale cache can extend the window during which tokens signed by that key are accepted.

Decide explicitly:
- Maximum cache age.
- Whether stale-if-error is allowed.
- When refreshes are forced.
- Whether an emergency cache purge mechanism exists.
- Whether trust for an entire key can be revoked immediately.
- Acceptable RTO/RPO and availability targets.

Never automatically accept unverified keys when a JWKS fetch fails. If no matching trusted key exists, fail closed.

## 7. A JWKS Cache Is Not a User-Token Revocation Cache

Suppose K1 signs tokens for 10,000 users. One user is revoked:

~~~text
K1:
  User A token
  User B token
  User C token
  ...
  User 10,000 token
~~~

Removing K1 from JWKS affects every token using K1 once Resource Servers refresh their caches. It is not a way to selectively revoke User A's token alone.

Conversely, keeping K1 in JWKS does not prove every token signed with K1 is active. A JWT can still be:
- Expired.
- For the wrong audience.
- From the wrong issuer.
- Before nbf.
- Missing required scopes.
- Denylisted by jti.
- Disallowed by domain policy.

**A JWKS cache manages key availability/trust material; revocation is a state of a token, grant, user, or signing key.**

If a private key is compromised, key-level emergency removal may be necessary despite its wide blast radius. If only a single token is exposed, consider a jti denylist, introspection, token versioning, or short lifetimes.

## 8. What Does an Opaque Token Introspection Cache Store?

RFC 7662 defines token introspection: the Resource Server sends a token to the AS and receives metadata about the token's state.

Example request:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Content-Type: application/x-www-form-urlencoded
Authorization: Basic RESOURCE_SERVER_CREDENTIALS

token=opaque-access-token&token_type_hint=access_token
~~~

Active response:

~~~json
{
  "active": true,
  "sub": "user-42",
  "client_id": "shop-web",
  "scope": "orders.read orders.write",
  "aud": ["orders-api"],
  "iat": 1794729600,
  "exp": 1794730500
}
~~~

An introspection cache can store:
- active.
- issuer/subject/client_id.
- scopes and mapped authorities.
- audience/resource binding.
- exp/iat/nbf if supplied by the AS.
- Attributes used by the application.

This is **token-specific** data. Two tokens for the same subject may differ in scope, audience, client, lifetime, or revocation state. Never cache principals by subject alone and reuse them across all of a user's tokens.

### Cache Raw Response or Principal?

You can cache:
- Raw/normalized introspection response.
- The constructed OAuth2AuthenticatedPrincipal.
- A domain-specific structure holding active, expiry, claims, and authorities.

Whichever option you choose, preserve the contract and never reuse an entry across a different token, issuer, resource, or client context. If authorities are mapped per audience/client/route, the cache key and cached value must reflect those dimensions.

## 9. Why Does Introspection Caching Introduce a Revocation Trade-Off?

Suppose:

~~~text
10:00:00 AS returns active=true
10:00:01 RS caches positive result for 60 seconds
10:00:10 Admin revokes token at AS
10:00:11 Request continues using positive cache
10:01:01 Entry expires
10:01:02 RS calls AS and receives active=false
~~~

In this example, the token can still be accepted for nearly 51 seconds after revocation. That is cache-induced **revocation visibility delay**.

No TTL can simultaneously eliminate network calls and guarantee instant visibility of every revocation without a synchronous invalidation mechanism.

### Aligning TTL with the Revocation SLA

If the organization requires revoked tokens to stop being accepted within at most 30 seconds, the positive cache TTL must be chosen at or below the remaining budget after accounting for:
- AS replication/propagation delay.
- Cache invalidation delay.
- In-flight requests.
- Clock skew.
- CDN/proxy/cache layers if present.
- Failure/retry behavior.

A simple model:

~~~text
Revocation visibility delay
  <= AS propagation delay
     + positive cache remaining TTL
     + invalidation delivery delay
     + bounded in-flight request duration
~~~

This is an estimation model for SLA design, not an absolute guarantee if the system has unbounded stale caches or network partitions.

## 10. Positive Introspection Cache TTL

A positive cache entry is typically bounded by:
- Maximum TTL configured by the Resource Server.
- Remaining time until exp if the introspection response provides exp.
- Revocation SLA.
- Scope/permission change policy.
- Token audience/resource context.

Reference formula:

~~~text
positiveTTL =
  min(configuredMaxPositiveTTL,
      exp - now,
      remainingRevocationFreshnessBudget)
~~~

If exp is absent from the response, do not infer infinite lifetime. Use a short contract-defined max positive TTL, or skip positive caching if freshness requirements forbid it.

### Never Use a TTL Exceeding exp

If a token has 10 seconds left until exp while the cache TTL is 60 seconds, a cache hit at second 30 must not return an active principal. Either the entry must expire at exp or the code must check exp on every cache hit.

Use a monotonic clock for in-cache durations when supported by the library, while keeping absolute expiry for token validity checks. Never depend on local timezones.

### Caching active=true Does Not Replace Timestamp Validation

If the AS returns active=true with a past exp due to a contract bug, clock mismatch, or stale cache, the Resource Server must enforce its own acceptance policy. Never treat a positive cache entry as exempt from expiration.

## 11. Negative Introspection Cache

The AS may return:

~~~json
{
  "active": false
}
~~~

Negative results can be cached briefly to reduce repeated introspection of an already-rejected token.

Benefits:
- Reduces AS load from repeated invalid tokens.
- Limits repeated network round trips.
- Can curb abuse from a revoked credential.

Risks:
- Cache pollution if an attacker sends endless random tokens.
- Tokens re-activated under special policy may continue being rejected during the TTL.
- Token rotation/new grants may not be reflected immediately if the cache key is wrong.
- Sharing negative entries across the wrong issuer/resource context can cause false rejections.

Policy:
- Negative TTL is usually shorter than positive TTL.
- Bound cache size and configure eviction.
- Rate-limit sources sending random tokens.
- Never cache arbitrary upstream failures as active=false.
- Distinguish AS returning active=false from timeouts, HTTP 5xx, TLS failures, and invalid_client.

### Never Turn Dependency Errors into Negative Cache Entries

The following errors do not mean the token is inactive:
- Introspection endpoint timeout.
- HTTP 500/503.
- DNS/TLS failure.
- HTTP 401 invalid_client.
- HTTP 403 Resource Server not permitted to introspect.
- Malformed response.

Never cache these as active=false. Also never cache them as active=true. Preserve failure semantics, fail closed, and apply retries/circuit breakers per policy.

## 12. Introspection Cache Keys Must Isolate Trust Contexts

Never use subject as the cache key:

~~~text
Cache key = user-42
~~~

Because the same user can have:
- A read-only access token.
- A read/write access token.
- A token for a different audience.
- A token from a different issuer.
- A different client.
- A different tenant context.
- An old revoked token and a new active token.

Avoid storing raw Bearer tokens as keys in logs or cache systems whenever possible. One option is a **keyed HMAC fingerprint** of the token.

~~~text
cacheKey =
  HMAC(cacheKeySecret,
       issuerId || introspectionEndpointId || resourceId || token)
~~~

Exact components depend on the contract:
- Issuer/AS identity.
- Introspection endpoint.
- Resource/audience context.
- Token type hint.
- Client/tenant policy if it affects the response.

Manage the HMAC key securely with planned rotation. Unkeyed hashes can still be probed if token entropy is low; access tokens must have sufficient entropy and cache keys must never be logged.

### Cache Namespaces for Multiple Issuers

Two AS instances could coincidentally issue the same token string or share subjects. Cache keys must distinguish issuer and endpoint. Never use a single global map from token string to principal across all trust domains.

## 13. Introspection Caching in Spring Security WebFlux

The reactive contract of the introspector:

~~~java
public interface ReactiveOpaqueTokenIntrospector {
    Mono<OAuth2AuthenticatedPrincipal> introspect(String token);
}
~~~

Spring Security provides an introspector that performs HTTP introspection. Caching can be implemented with a decorator or dedicated caching component.

~~~text
OpaqueTokenReactiveAuthenticationManager
                 |
                 v
       CachingReactiveIntrospector
                 |
          +------+------+
          |             |
       Cache hit      Cache miss
          |             |
          v             v
   Principal/result   Delegate introspector
          |             |
          |             v
          |         Authorization Server
          |             |
          +-------------+
                 |
                 v
      OAuth2AuthenticatedPrincipal
~~~

The decorator must:
- Return the verified authenticated principal.
- Not alter authorities/attributes contrary to contract.
- Compute TTLs bounded by exp and freshness policy.
- Distinguish active=false from dependency errors.
- Bound cache size.
- Never block the event loop.
- Never let a pending request trigger thousands of concurrent introspection calls.
- Never serve cached results from a different issuer/resource.

### Do Not Assume Spring Boot Automatically Caches Introspection

~~~yaml
spring:
  cache:
    type: caffeine
~~~

This configuration alone does not prove `ReactiveOpaqueTokenIntrospector` is wrapped with a cache. The Spring Cache abstraction only takes effect when code or beans explicitly use it. You must deliberately configure a decorator, cache manager, or caching implementation.

Similarly, adding a Caffeine dependency does not automatically switch Nimbus's JWKS cache to Caffeine. Verify the actual JWK source and integration.

## 14. Decorator Illustration: Bounded Cache with Per-Token TTL

A production implementation must choose a suitable cache library and semantics. The snippet below is **algorithmic pseudo-code**, not a complete copy-paste class:

~~~java
Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
    String key = hmacFingerprint(
            issuerId, introspectionEndpointId, resourceId, token);

    return cache.getOrLoad(key, () ->
            delegate.introspect(token)
                    .map(principal -> {
                        Instant expiresAt = readExpiration(principal);

                        Duration ttl = calculatePositiveTtl(
                                clock.instant(),
                                expiresAt,
                                maxPositiveTtl,
                                revocationBudget);

                        return CacheEntry.positive(principal, ttl);
                    })
                    .onErrorMap(this::preserveDependencyFailure));
}
~~~

Assumed properties:
- The cache has bounded size and per-entry expiry.
- getOrLoad coalesces concurrent misses for the same key.
- The cache writes only when the delegate returns a valid introspection result.
- The TTL function returns a positive value bounded by exp and the SLA.
- Dependency errors do not become positive or negative entries.
- The error path is preserved per the authentication contract.

If the response is active=false, a negative entry with a short policy-defined TTL may be stored. Do not share the same TTL with positive results if revocation and freshness requirements differ.

### Reactive Implementations Must Be Non-Blocking

Avoid:

~~~java
OAuth2AuthenticatedPrincipal principal =
        delegate.introspect(token).block();
~~~

Blocking inside the WebFlux request pipeline can stall the event loop. Use Mono composition and a cache library supporting asynchronous loading or an appropriate reactive design.

Never use an unbounded `ConcurrentHashMap<String, Mono<...>>` in production without eviction, TTLs, in-flight cleanup, and concurrent-miss protection.

## 15. Spring Cache, Caffeine, and Redis: Choosing by Deployment

| Option | Pros | Risks / Considerations |
|---|---|---|
| In-memory bounded cache | Simple, low latency, no extra network dependency | Each instance has its own cache; restarts lose cache |
| Caffeine | Expiration, eviction, high-performance local cache | Requires explicit integration; does not auto-wrap introspector/JWKS |
| Redis/distributed cache | Shares entries across RS instances, centralized invalidation | Adds network, availability, and security dependencies |
| CDN/proxy for JWKS | Reduces AS load and supports edge distribution | Must preserve issuer/path/cache headers and rotation semantics |
| No introspection cache | Near-AS freshness on every request | Higher latency and AS load |
| Short-lived positive cache | Cuts calls while bounding staleness window | Revocation still delayed up to TTL/invalidation |

### In-Memory Cache

Appropriate when instance count is small, token volume is moderate, and the revocation SLA permits local caching.

With 20 pods, each maintaining its own cache, the same token can experience:
- Pod A has already observed active=false.
- Pod B still holds active=true.
- Pod C just restarted and calls the AS.

This is a consistency model to understand, not necessarily a bug.

### Distributed Cache

Redis helps share results and centralize invalidation. However:
- A cache outage can affect authentication.
- Redis network latency becomes part of request latency.
- Cached data containing subject/scope/tenant metadata requires ACLs, TLS, encryption, and retention limits.
- Key namespaces must isolate issuer and resource.
- Invalidation events can be delayed or lost; TTL remains the safety bound.
- Never keep using stale positive entries indefinitely during a Redis or AS outage.

### When the Cache Is a Hard Dependency

If the cache backend goes down:
- You may bypass the cache and call the AS directly if the AS is healthy and capacity permits.
- You may fail closed if state cannot be verified.
- Never automatically serve stale positive results outside the freshness budget.
- Never switch to an untrusted issuer or introspection endpoint.

Bypassing the cache to call the same trusted AS is very different from switching trust authorities.

## 16. Cache Stampedes, Concurrency, and Backpressure

When a positive entry's TTL expires, many requests with the same token may call introspection simultaneously:

~~~text
Cache entry expires
       |
       +-- Request A -> AS
       +-- Request B -> AS
       +-- Request C -> AS
       +-- ...
       +-- Request N -> AS
~~~

This is a cache stampede. Mitigations:
- Single-flight loading/coalescing for the same key.
- TTL jitter so batches of entries do not expire at the exact same instant.
- Bounded concurrent introspection requests.
- Per-AS connection pools and timeouts.
- Per-client or per-route rate limits if needed.
- Circuit breakers to protect dependencies.
- Bounded backoff for transient errors.

### TTL Jitter Must Respect the SLA

If the maximum positive cache TTL is 30 seconds under the revocation SLA, never add jitter that pushes the TTL to 45 seconds. Jitter should spread refresh timing without exceeding the freshness ceiling.

### Circuit Breakers Must Not Open a Fail-Open Path

When the introspection AS fails repeatedly, a circuit breaker prevents flooding the network. However, an open circuit does not prove a token is active. Protected requests must still fail closed or follow an explicit, bounded, approved stale policy.

## 17. Cache Invalidation on Revocation or Permission Changes

Invalidation can be triggered by events:
- Token revoked.
- Refresh token family revoked.
- User disabled.
- Client disabled.
- Consent/grant revoked.
- Scope/role assignment changed.
- Tenant membership removed.
- Issuer key compromised.

### Token-Specific Invalidation

If an event carries a token ID or jti, the corresponding cache entry can be removed. For opaque tokens, the AS and RS need a way to correlate the token event with the cache key without broadcasting raw tokens.

### Subject/Grant-Wide Invalidation

If a user is locked or an entire grant is revoked, multiple entries can be invalidated by:
- Issuer + subject.
- Issuer + client ID.
- Grant/session identifier.
- Tenant/user version.

A secondary index or versioned namespace can assist invalidation. Take care not to accidentally delete entries belonging to another issuer with the same subject.

### Event Delivery Does Not Replace TTL

Pub/sub events can be lost due to network partitions, consumer restarts, or message retention limits. Therefore:
- TTL must still satisfy the maximum staleness window.
- Implement retries, dead-letter queues, and replay.
- Track event lag with metrics.
- Make invalidation handlers idempotent.
- Reconcile state if necessary.
- Never assume publishing an event means every RS has processed it.

## 18. Neither JWKS Caching Nor Introspection Caching Equals Revocation Caching

| Flow | Cache | What Is Cached | What Is Not Guaranteed |
|---|---|---|---|
| JWT | JWKS cache | Public signing keys | Revocation of a specific token |
| JWT | Additional denylist/status cache | jti/token/user status | Key set freshness |
| Opaque | Introspection cache | Token active flag and attributes | Instant revocation visibility |
| Opaque | JWKS cache | Unrelated to introspection | Does not speed up opaque tokens |

A system may need all of:
- A JWKS cache to verify JWTs.
- A denylist or token-version cache to detect revocations.
- An introspection cache to reduce AS calls for opaque tokens.
- An OIDC metadata cache to reduce discovery requests.

Each cache requires its own owner, TTL, key namespace, invalidation, and metrics.

## 19. Token Expiry Must Be Checked on Cache Hits

A common mistake:

~~~text
10:00 Cache stores active=true, exp=10:01.
10:00:50 Cache hit.
10:01:10 Cache hit again due cache TTL=60s.
10:01:10 RS returns cached active=true without checking exp.
~~~

The token has expired yet the cache entry still exists. The right approach:
- Positive entry TTL must not exceed remaining time until exp.
- Check absolute exp on every cache hit if the entry stores exp.
- Apply a consistent clock skew policy.
- If exp is missing, use a policy-approved max TTL or do not cache.
- Never treat cache TTL as a substitute for token lifetime validation.

For JWTs, the decoder must still validate exp/nbf on every request even when the JWK set is cached.

## 20. Cache Key Rotation and Issuer Isolation

### JWKS Cache Key

Cache the JWK set by **trusted JWKS endpoint/issuer namespace**. Never cache by kid alone:

~~~text
Bad:
  cache["key-2026"] = publicKey

Better:
  cache[(issuerA, jwksUriA)] = JWKSet
  cache[(issuerB, jwksUriB)] = JWKSet
~~~

kid only has meaning within its corresponding JWK set. Two issuers can use the same kid for completely different public keys.

### Introspection Cache Key

Cache by token fingerprint and trust/resource context:

~~~text
(issuerId, introspectionEndpointId, audience/resourceId, tokenFingerprint)
~~~

Never use:
- subject alone.
- client_id alone.
- raw token as a metric label.
- unverified iss as an arbitrary namespace.
- token fingerprint without distinguishing endpoint/resource when responses depend on those factors.

## 21. Security of Cached Principals and JWK Sets

A JWKS holds public keys, yet it is still trust material. If the cache is poisoned with attacker-controlled data, the Resource Server could verify tokens against the wrong keys. Safeguards:
- TLS and hostname verification.
- Trust issuer/JWKS URIs only from verified configuration or metadata.
- Never trust arbitrary jku/x5u headers.
- Cache integrity and access control when using a shared cache.
- Never use request-supplied cache namespaces.
- Audit key sources and refresh failures.

Introspection results may include subject/user ID, email/username, tenant ID, scopes/roles, client ID, and audience. This cached data requires:
- Encryption in transit and at rest where appropriate.
- ACLs restricted to authorized Resource Servers.
- Short TTLs and retention.
- Never writing principal objects or raw claims to logs.
- Key rotation and namespace isolation.
- Never sharing caches across environments (dev/prod) or different issuers.

## 22. Observability: Measure Both Caches Separately

Never use a single generic `auth_cache_hit` metric without knowing which cache it measures. Separate them:

~~~text
jwks_cache_hit_total
jwks_cache_miss_total
jwks_refresh_total
jwks_refresh_failure_total
jwks_unknown_kid_total
jwks_fetch_latency_seconds

introspection_cache_hit_total
introspection_cache_miss_total
introspection_positive_hit_total
introspection_negative_hit_total
introspection_upstream_request_total
introspection_upstream_failure_total
introspection_latency_seconds
introspection_entry_expired_total
introspection_invalidation_total
~~~

Labels should have low cardinality:
- Configured issuer ID.
- Resource Server ID.
- Cache outcome.
- Failure category.
- Environment/region if needed.

Never use raw tokens, raw sub values, unbounded kids, or unverified issuer URLs as metric labels.

### Key Indicators

**JWKS**
- Cache hit ratio.
- Refresh latency/failure rate.
- Unknown-kid rate.
- Age of the current JWK set.
- Key rotation overlap.
- Signature failures by configured issuer/key source.

**Introspection**
- Positive/negative hit ratio.
- AS request rate.
- AS latency/error rate.
- Age of positive entries.
- Remaining TTL when revocation events are processed.
- Invalidation event lag.
- Number of stale results rejected.

A high hit ratio speaks only to performance. Freshness and correctness determine safety.

## 23. Designing Operational Goals for Both Caches

| Goal | JWKS cache | Introspection cache |
|---|---|---|
| Reduce latency | Avoid frequent public key fetches | Avoid calling AS on cache hits |
| Reduce AS load | Reduce GET JWKS calls | Reduce POST introspection calls |
| Availability | Can verify with trusted cached keys during brief AS downtime per policy | Can use cached active results within freshness window if policy allows |
| Key rotation | Must refresh promptly to pick up new keys and drop old ones | Does not handle key rotation |
| Individual token revocation | Does not address directly | May delay revocation visibility up to positive TTL |
| Permission changes | Does not refresh token claims | May cache stale claims; needs invalidation/freshness |
| Security boundary | Correct issuer/JWKS source | Correct issuer, endpoint, resource, and token |
| Failure policy | Fail closed if no trusted key exists | Fail closed if no fresh/valid cached positive introspection exists |
| Primary SLA | Key freshness / rotation propagation | Revocation visibility / active-result freshness |

### Do Not Optimize One Goal by Breaking Another

- Overly long JWKS TTLs cut network calls but prolong use of old keys.
- Overly short JWKS TTLs raise refresh load and AS dependency.
- Overly long introspection TTLs cut latency but widen revocation delay.
- Overly short introspection TTLs raise AS load and request latency.
- Disabling caching maximizes freshness but increases dependency pressure.
- stale-if-error boosts availability but keeps accepting stale credentials.

Derive TTLs from concrete SLOs/SLAs rather than copying numbers from a blog post or another environment.

## 24. Example Policy for a System with Both JWT and Opaque Tokens

An API with two Resource Server route groups:

~~~text
/api/jwt/**
  JWT issuer Shop
  JWKS cache max age = 5 minutes (illustrative policy)
  Rotation overlap = 15 minutes (illustrative policy)
  exp <= 10 minutes
  Emergency key purge procedure

/api/opaque/**
  Introspection AS Partner
  Positive cache max TTL = 10 seconds (illustrative policy)
  Negative cache TTL = 2 seconds (illustrative policy)
  Positive TTL also bounded by exp
  Revoke visibility target <= 15 seconds
~~~

These numbers illustrate how to express a policy; they are not Spring Security defaults or universal recommendations. Validate them against:
- AS propagation delay.
- Clock skew.
- Network/replica topology.
- Maximum token lifetime.
- Key rotation process.
- Business risk of stale authorization.
- Load tests and failure tests.

With a 10-second opaque positive cache TTL but a 20-second AS replication delay, a 15-second revocation target cannot be met. Account for the entire pipeline, not just the local cache TTL.

## 25. Testing the JWKS Cache

| Test | Setup | Expected Outcome |
|---|---|---|
| JWKS first load | Empty cache, token signed with trusted key | GET JWKS occurs, token verifies |
| Cache hit | Send subsequent token using same set | No re-fetch within cache freshness window |
| New kid | JWKS updated with new key | Decoder refreshes per version behavior |
| Unknown kid | Token uses kid absent from set | Reject; bounded refresh |
| Wrong signature | Valid kid but token signed with different private key | Reject |
| JWKS malformed | Response is not a valid JWK Set | Do not update trusted cache |
| JWKS timeout | No matching cached key | Fail closed |
| Cached key + outage | Key still cached per policy | Matches stale/cache policy behavior |
| Remove old key | JWKS drops old key after overlap | Old token rejected after refresh/cache expiry |
| Two issuers same kid | Same kid but different keys | Cache namespaces never mix issuers |
| Refresh storm | Many requests with same unknown kid | Bounded/coalesced refresh per implementation |

Do not assert that every request produces exactly one JWKS call. Cache and refresh policies vary request counts. Assert behavior against your actual cache contract and version.

## 26. Testing the Introspection Cache

| Test | Setup | Expected Outcome |
|---|---|---|
| First positive | Cache miss, AS active=true | One introspection call, positive cached |
| Positive hit | Same token within TTL | No second AS call, correct principal |
| Exp boundary | Cache entry exists but exp has passed | Reject |
| TTL boundary | Entry TTL expired | Introspect again |
| Revoke after positive | AS switches active=true to false | Stale window matches TTL/invalidation SLA |
| Explicit invalidation | Revoke event reaches cache | Entry removed, next request introspects |
| Negative result | AS active=false | Reject; short negative TTL if enabled |
| Negative expiry | Token state changes per test policy | Re-calls AS after TTL |
| Upstream 500/timeout | Cache miss | Fail closed; do not cache active |
| invalid_client | AS returns 401 for RS credentials | Classify as dependency/config error |
| Different audience | Same token under different resource context | Do not reuse wrong cached result |
| Different issuer | Same token string across two issuer domains | Independent cache entries |
| Concurrent miss | Multiple requests with same token | Single-flight/bounded concurrency |
| Cache backend down | Redis/local cache failure | Clear bypass or fail-closed policy |
| User role change | Stale claims in positive entry | Invalidation/freshness per contract |

### Measuring Actual Revocation Delay

1. First request populates the positive cache entry.
2. Revoke the token at the AS.
3. Send repeated requests over time.
4. Record the first timestamp when the RS rejects the token.
5. Compare against TTL, propagation delay, and invalidation event lag.
6. Run across multiple RS instances to detect cache inconsistency.

Only measured results prove the revocation SLA in your actual topology.

## 27. Failure Policy for Each Cache

| Failure | JWKS cache | Introspection cache |
|---|---|---|
| Cache miss, source healthy | Fetch JWK set | Call AS |
| Cache miss, source unavailable | Cannot verify without trusted key | No active result; fail closed |
| Cache backend unavailable | May use in-process trusted key cache if policy allows | May bypass to same AS if capacity permits, or fail closed |
| Cached entry expired | Refresh per policy | Introspect again |
| Source returns malformed response | Do not replace trusted JWK set with error response | Do not build principal |
| Source returns explicit negative | Not applicable to JWK set | active=false, reject |
| Source timeout | Do not treat as a valid new key | Treat as neither active=false nor active=true |
| Emergency invalidation | Purge compromised key set/entry | Delete token/grant/subject entries |
| Unknown issuer/endpoint | Never fetch arbitrary JWKS | Never send token to arbitrary AS |

### Stale Positive Results Are a Security Decision

If the AS is unavailable and the introspection cache still holds a positive entry:
- If the entry is still within TTL/freshness budget, policy may allow using it.
- If the entry has expired, never treat it as fresh.
- If a revocation event has arrived, the entry must be invalidated.
- During emergency revocation or compromise, stale-positive exceptions may be disabled immediately.

Never extend TTLs during an AS outage just to maintain availability if doing so violates the revocation SLA.

## 28. Common Misconceptions

**"Enabling Spring Cache automatically caches JWKS."**

Not necessarily. JWKS retrieval and caching belong to the JWK source/Nimbus and its configuration. The Spring Cache abstraction does not automatically replace the JWK source.

**"Enabling Caffeine automatically caches introspection."**

No. You need an explicit caching decorator/bean or integration around `ReactiveOpaqueTokenIntrospector`.

**"A JWKS cache hit means the JWT is authenticated."**

No. A cache hit only provides a candidate key. The decoder still must verify the signature and validate issuer, audience, exp, nbf, and token purpose.

**"An introspection cache hit means the token is currently active at the AS right now."**

No. It only means the Resource Server holds a prior active result still within local freshness policy. The token may have been revoked after caching.

**"The JWKS cache TTL and introspection TTL should be equal."**

There is no default reason for them to match. The two caches differ in data, invalidation, security objectives, and SLAs.

**"Removing an old key from JWKS revokes an individual token."**

No. A key may be shared by many tokens, and caches may still hold the old key. Token-specific revocation requires a dedicated mechanism.

**"Cache timeout responses as active=false to reduce calls."**

No. A timeout is not an answer from the AS that the token is inactive. Failure semantics must be preserved.

**"If the cache backend goes down, use stale principals indefinitely."**

No. Stale-positive behavior must have a bounded freshness budget and explicit approval.

## 29. Design Checklist

Before enabling JWKS caching:
1. Which trust configuration provides the issuer/JWKS URI?
2. What is the JWK cache TTL/refresh policy of your running version?
3. How long is the key rotation overlap window?
4. Can unknown kids trigger a refresh storm?
5. How are AS outages handled for cached keys vs. cache misses?
6. How long does an emergency key purge take to reach all RS instances?
7. Could a CDN or proxy retain a stale key set?
8. Do metrics measure cache age, refresh errors, and unknown kids?

Before enabling introspection caching:
1. What is the revocation visibility SLA?
2. How is positive TTL bounded by exp?
3. Is exp present in the response; if not, what max TTL is permitted?
4. How long is the negative TTL and how is cache pollution controlled?
5. Do cache keys include issuer/endpoint/resource context?
6. Are keyed fingerprints used instead of raw tokens?
7. Are upstream errors excluded from the cache?
8. Does revocation event invalidation guarantee delivery/replay?
9. Does a cache backend outage bypass to the same AS or fail closed?
10. How are cached principal attributes protected?

Before production:
- Test key rotation and token revocation.
- Test across multiple instances.
- Test AS/JWKS outages.
- Test cache outages.
- Test concurrency/stampedes.
- Measure p95/p99 latency and upstream load.
- Measure actual freshness/revocation delay.
- Document the failure policy and owner of each cache.

## 30. Summary

~~~text
JWT request
   |
   v
JWT Decoder
   |
   v
JWKS cache
  stores public keys
   |
   v
Verify signature + validate claims
   |
   v
Authentication

Opaque request
   |
   v
ReactiveOpaqueTokenIntrospector
   |
   v
Introspection cache
  stores token-specific active/claims
   |
   v
On miss: call Authorization Server
   |
   v
Build authenticated principal
~~~

Key principles:

1. **JWKS caches store public signing keys** to cut key fetches and support JWT validation availability.
2. **Introspection caches store per-token results** to cut AS round trips.
3. **JWT signatures and claims must still be checked on every request**; cached keys are not cached authentications.
4. **Positive introspection caching can delay revocation visibility**; TTLs must be derived from the revocation SLA.
5. **Positive TTLs must never exceed exp or the freshness budget**.
6. **Negative results differ from upstream errors**; timeouts, 5xx, and invalid_client do not mean active=false.
7. **Cache keys must isolate issuer, endpoint, resource, and token identity**; never key by subject alone.
8. **JWKS cache freshness affects key rotation and emergency key removal**, but does not revoke individual user tokens.
9. **Spring Cache/Caffeine does not automatically enable either cache**; explicit integration must be configured.
10. **Bounded caches, single-flight, rate limits, and metrics** help prevent stampedes and DoS.
11. **In-memory and distributed caches carry different consistency and availability trade-offs**.
12. **Stale-if-error must have explicit limits**; never use stale positive results indefinitely during dependency downtime.

**Conclusion:** JWKS caches and introspection caches both reduce network work, but serve two distinct goals. A JWKS cache optimizes distributing public keys for JWT signature verification; an introspection cache optimizes per-token verification results for opaque tokens and directly affects revocation visibility delay. A sound design requires separate TTLs, namespaces, invalidation, outage behavior, and metrics for each cache, grounded in key rotation, revocation freshness, availability, and Authorization Server load requirements.

## 31. References

- **Spring Security Reference — Reactive JWT Resource Server:** configuring ReactiveJwtDecoder, issuer, and JWK Set URI. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html
- **Spring Security Reference — Servlet JWT Resource Server:** NimbusJwtDecoder, JWKS, and key rotation. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- **Spring Security Reference — Reactive Opaque Token Resource Server:** ReactiveOpaqueTokenIntrospector and introspection. https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html
- **Spring Security Reference — Servlet Opaque Token Resource Server:** OpaqueTokenIntrospector and token active state. https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- **Nimbus JOSE + JWT Documentation:** Remote JWK Set, JWK source, and cache/refresh behavior. https://connect2id.com/products/nimbus-jose-jwt
- **RFC 7517 — JSON Web Key (JWK):** JWK and JWKS representation. https://www.rfc-editor.org/rfc/rfc7517
- **RFC 7515 — JSON Web Signature (JWS):** JWS header, kid, and signature validation. https://www.rfc-editor.org/rfc/rfc7515
- **RFC 7519 — JSON Web Token (JWT):** iss, aud, exp, nbf, and claims. https://www.rfc-editor.org/rfc/rfc7519
- **RFC 7662 — OAuth 2.0 Token Introspection:** active flag and introspection response. https://www.rfc-editor.org/rfc/rfc7662
- **RFC 7009 — OAuth 2.0 Token Revocation:** token/grant revocation. https://www.rfc-editor.org/rfc/rfc7009
- **RFC 8414 — OAuth 2.0 Authorization Server Metadata:** issuer metadata and jwks_uri. https://www.rfc-editor.org/rfc/rfc8414
- **OpenID Connect Discovery 1.0:** provider metadata discovery. https://openid.net/specs/openid-connect-discovery-1_0.html
- **Caffeine Cache Documentation:** bounded local cache, expiration, eviction, and loading. https://github.com/ben-manes/caffeine/wiki
- **Spring Framework Cache Abstraction:** cache abstraction and integration boundaries. https://docs.spring.io/spring-framework/reference/integration/cache.html
