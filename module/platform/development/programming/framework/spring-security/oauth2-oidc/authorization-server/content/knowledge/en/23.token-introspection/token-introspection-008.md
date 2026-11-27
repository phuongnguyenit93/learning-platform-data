# Trade-Off Between Introspection Result Caching and Revocation Delay

## 1. Context and Objectives

In an **OAuth 2.0/OpenID Connect Authorization Server** system using **Spring Security**, **Spring Authorization Server**, and **Spring Boot**, a Resource Server can verify JWT access tokens by signature and claims. With reference/opaque access tokens, the Resource Server typically calls the **Token Introspection Endpoint** to ask the Authorization Server whether the token is active and retrieve attributes such as scope, client, subject, audience, and expiration.

Calling introspection on every request gives the Resource Server the latest token state within the Authorization Server's consistency guarantees, but adds network latency, load on the endpoint, and a dependency on Authorization Server availability. Caching introspection results reduces network calls, yet creates a window during which the Resource Server may continue accepting a revoked token.

End-to-end example: Orders API receives 8,000 requests/second from services using opaque access tokens. The Authorization Server can handle introspection, but each network call increases latency and load. The operations team wants to cache <code>active=true</code> results for a short period. At the same time, when an administrator revokes a token due to a compromised service account, the API must stop accepting the token within a committed SLA.

After this lesson, you will be able to:

1. Explain accurately what introspection caching saves and how it delays revocation.
2. Calculate the maximum window during which a cache can continue trusting a stale <code>active=true</code> result.
3. Choose TTL based on <code>exp</code>, revocation SLA requirements, invalidation propagation time, and API risk.
4. Distinguish positive caches, negative caches, error caches, and HTTP caches; know which cases must never be cached.
5. Design single-tier or multi-tier caches without inadvertently extending freshness.
6. Wrap <code>OpaqueTokenIntrospector</code> in Spring Security with a bounded-TTL cache and safe keys.
7. Handle revocation events, token families, introspection outages, and fail-open/fail-closed decisions.
8. Measure latency, hit ratio, stale acceptance windows, and test revocation end-to-end.

**Version scope:** Examples use Spring Security 6.x and Spring Authorization Server 1.x with a Servlet Resource Server. <code>OpaqueTokenIntrospector</code> is a Spring Security extension point. Caffeine is used as an illustrative cache library; it can be replaced with a distributed cache. HTTP introspector creation APIs can vary across versions, so configuration focuses on wrapping an already properly configured introspector.

## 2. Introspection Is a Token Status Decision

### 2.1. Basic Request and Response

The Resource Server sends the token to the introspection endpoint over HTTPS and authenticates itself per the Authorization Server's policy:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: auth.example.com
Authorization: Basic <resource-server-credential>
Content-Type: application/x-www-form-urlencoded

token=opaque-access-token-value
~~~

An active response may include metadata:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json
Cache-Control: no-store
Pragma: no-cache

{
  "active": true,
  "scope": "orders.read",
  "client_id": "orders-worker",
  "sub": "service-account-orders",
  "aud": ["https://orders-api.example.com"],
  "iss": "https://auth.example.com",
  "iat": 1794800000,
  "exp": 1794800300,
  "jti": "token-7f31"
}
~~~

The response above is only an example of common fields; <code>exp</code>, <code>aud</code>, <code>sub</code>, <code>jti</code>, and other metadata depend on the token and configuration. The <code>Cache-Control: no-store</code> header is included to illustrate a response forbidding caching. If the Authorization Server actually returns <code>no-store</code>, the Resource Server must respect that directive; never bypass it by wrapping the introspector in an application cache and storing the response anyway.

### 2.2. What Does <code>active</code> Mean?

<code>active=true</code> means the Authorization Server confirms the token is active under its state and policy at the moment introspection is processed. A token may be considered inactive because it does not exist, is invalid, expired, revoked, or no longer permitted for use. The Authorization Server does not necessarily disclose the specific reason.

<code>active=false</code> is an answer about token status, not an endpoint error. Distinguish:

| Result | Meaning | Resource Server Action |
| --- | --- | --- |
| <code>active=true</code> | Token is active per Authorization Server. | Continue checking issuer, audience, expiry, scope, and API policy. |
| <code>active=false</code> | Token is not permitted for use at introspection time. | Reject authentication request. |
| Timeout/connection failure | Token status unknown because no answer was received. | Apply outage policy; never treat timeout as <code>active=true</code> or <code>active=false</code>. |
| 401/403 from introspection | Introspection client authentication invalid or unauthorized. | Fix config/credentials and refuse decisions based on invalid results. |
| 5xx/malformed JSON | Endpoint or protocol failure. | Report service error; never cache as a token result. |

Introspection is only part of authorization. An <code>active=true</code> token may still be denied from calling Orders API if the audience is wrong or scopes are insufficient.

### 2.3. Why Does Introspection Support Revocation?

With reference tokens, the Authorization Server can look up token status in the authorization store. When a token is revoked, its status can transition from active to inactive. The next introspection request will receive the updated status once the change has committed and become consistent across the system.

The Resource Server only learns of that change when it queries the Authorization Server again or receives a trustworthy invalidation signal. If the Resource Server is using a cached active result, it may continue accepting the token until the cache expires or is evicted.

## 3. What Does Caching Help With and What Is the Trade-Off?

### 3.1. No Cache: Freshest State at a Network Cost

On every API request:

1. Resource Server receives the bearer token.
2. Calls the introspection endpoint over HTTPS.
3. Waits for the Authorization Server to verify the token.
4. Receives active/metadata.
5. Checks scope, audience, and request authorization.

The advantage is not holding stale active results for long in the Resource Server. The drawback is that every request depends on network and introspection capacity; if the API has high traffic, introspection request volume is nearly equal to API request volume.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as API Client
    participant RS as Orders Resource Server
    participant AS as Authorization Server
    C->>RS: GET /orders + opaque access token
    RS->>AS: POST /oauth2/introspect
    AS-->>RS: active=true + scope + aud + exp
    RS->>RS: Check scope/audience
    RS-->>C: 200 OK
~~~

### 3.2. Caching: Fewer Introspection Calls but Accepting Stale State

If the Resource Server caches <code>active=true</code>, subsequent requests with the same token can be authenticated locally while the cache remains fresh:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as API Client
    participant RS as Orders Resource Server + Cache
    participant AS as Authorization Server
    C->>RS: Request 1 with token T
    RS->>AS: Introspect T (cache miss)
    AS-->>RS: active=true
    RS->>RS: Cache metadata of T
    RS-->>C: 200 OK
    C->>RS: Request 2 with token T
    RS->>RS: Cache hit, no AS call
    RS-->>C: 200 OK
    Note over AS,RS: Token T is revoked at AS
    C->>RS: Request 3 with token T
    RS->>RS: Cache still fresh
    RS-->>C: May still return 200 until cache expires
    RS->>AS: Re-introspect after cache expires
    AS-->>RS: active=false
    RS-->>C: 401 Unauthorized
~~~

Caching does not make the Authorization Server revoke more slowly; it makes the **Resource Server detect revocation status more slowly**. This is a critical distinction when defining SLAs.

### 3.3. Trade-Off Comparison Table

| No Cache | Caching Results |
| --- | --- |
| Every request incurs a network round trip. | Cache hits skip calling introspection. |
| Latency depends on Authorization Server and network. | Lower, more predictable latency on cache hits. |
| Introspection load scales with API traffic. | Load drops according to distinct token count and TTL. |
| Revocation status is observed on the very next introspection. | Stale active tokens may be accepted until cache expiry/invalidation. |
| API availability depends on ability to reach AS. | Fresh cache can serve requests during brief AS failures. |
| Centralized state is easy to reason about. | Must manage cache consistency, invalidation, and stale data. |

## 4. Quantifying the Revocation Delay Window

### 4.1. Basic Formula

Suppose:

- <code>T</code> is the maximum TTL of an <code>active=true</code> result in the Resource Server.
- <code>t_r</code> is the time the Authorization Server commits the token revocation.
- <code>t_c</code> is the time the cache entry was most recently created or refreshed.
- <code>t_e = t_c + T</code> is the time the cache entry expires.

Without push invalidation, the Resource Server can continue trusting the stale result until <code>t_e</code>. In the worst case, the cache was refreshed right before revocation occurred:

\[
W_{\text{stale}} \leq T + \epsilon
\]

Here <code>ε</code> includes in-flight request processing time, clock skew, and deployment delays. If TTL is computed using a monotonic clock and the cache refuses to serve expired entries, this error margin can be kept small.

**Example:** Active introspection results are cached for 30 seconds. A token is revoked right after a cache hit/fill. The Resource Server may accept the token for nearly 30 additional seconds. If the SLA requires revoked tokens to stop being accepted within at most 5 seconds, a 30-second TTL does not meet the SLA.

### 4.2. With Push Invalidation

Suppose the system emits revocation events from the Authorization Server to Resource Servers. Let <code>P</code> be the maximum time from revocation commit until all relevant caches receive and apply the invalidation. If events are reliably delivered and caches evict the right entries, the stale delay can be bounded by either TTL or event propagation time:

\[
W_{\text{stale}} \leq \min(T, P) + \epsilon
\]

This bound holds only when invalidation is guaranteed to reach every verifier. If events can be lost, subscribers can go offline, or newly started nodes do not load revoked state, TTL acts as the fallback and the real bound must account for the event recovery path. Never use event publish time as proof that every cache has evicted the entry.

### 4.3. Calculating TTL from the Revocation SLA

Let:

- <code>D</code> be the maximum SLA from revocation commit until APIs reject the token.
- <code>P</code> be the maximum invalidation propagation budget.
- <code>M</code> be the margin for clock skew, in-flight requests, scheduling, and propagation.

Without reliable invalidation, choose:

\[
T \leq D - M
\]

With reliable invalidation whose propagation is measured and controlled:

\[
\min(T, P) + M \leq D
\]

When <code>P</code> cannot be guaranteed, do not use a formula relying on <code>P</code> to justify a large TTL. Use the fallback TTL and measure actual invalidation latency.

Example: SLA is 10 seconds, invalidation events target a max of 3 seconds, margin is 2 seconds. When events work properly, the stale window is bounded by events; if events are lost, the fallback TTL must still meet the SLA. Thus, without strong event confirmation/repair mechanisms, the safe TTL should still not exceed 8 seconds (<code>D - M</code>).

### 4.4. TTL Must Be Bounded by exp

If introspection returns <code>exp</code>, the cache must never keep an entry active past the token's expiration time:

\[
T_{\text{effective}} =
\min(T_{\text{configured}},\; exp - now,\; T_{\text{revocation-budget}})
\]

Never cache past <code>exp</code>, even if the configured cache TTL is longer. If the response lacks <code>exp</code>, use a maximum TTL agreed with the Authorization Server while still obeying the revocation SLA.

Add a margin if clocks between the Resource Server and Authorization Server are unsynchronized. Never extend a cache entry to compensate for clock skew; synchronize clocks and use a safety buffer so tokens are never accepted past expiration.

## 5. Cache Types and Corresponding Policies

### 5.1. Positive Cache: <code>active=true</code>

This cache delivers most performance gains. However, it is also what creates the stale-positive window when a token is revoked.

Cache a positive result only when:

- The introspection response comes from an Authorization Server authenticated via HTTPS and proper client authentication.
- The response is valid, parsed successfully, and <code>active=true</code>.
- The Authorization Server's cache policy/contract permits caching.
- The TTL does not exceed <code>exp</code>, the revocation SLA, or resource policy.
- Stored principal/attributes are immutable or cannot be mutated by other requests.

Never turn an error response or timeout into a positive result. Never cache a principal with scope/audience inferred from the current request rather than the introspection response.

### 5.2. Negative Cache: <code>active=false</code>

Caching <code>active=false</code> does not delay revocation; it can reduce repeated requests for invalid tokens. However, if the Authorization Server has eventual consistency or a newly issued token has not yet synchronized across all nodes, negative caching can delay acceptance of a valid token.

Recommendations:

- By default, do not cache inactive responses unless there is a clear need.
- If needed to curb repeated requests for invalid tokens, use a very short TTL and bounded capacity.
- Never cache introspection errors, timeouts, 5xx, 401/403, or malformed JSON as <code>active=false</code>.
- Use a token hash as the cache key; never store raw bearer tokens in keys/logs.
- Assess token scanning risks and prevent negative caching from becoming a token-status oracle.

### 5.3. Error Cache

Never cache errors such as:

- Timeouts or connection resets.
- Authorization Server returning 5xx.
- Invalid introspection client credentials.
- Failed TLS certificate validation.
- Broken JSON responses or schema mismatches.
- Rate limits/429.

These errors indicate the Resource Server has not obtained a valid decision. Caching them as inactive can wrongly reject valid tokens after service recovery; caching them as active is a dangerous fail-open. Use bounded circuit breakers/retries and a dedicated outage policy.

### 5.4. HTTP Caches vs. Application Caches

HTTP caches follow the semantics of HTTP headers such as <code>Cache-Control</code>, <code>Age</code>, <code>Date</code>, <code>Expires</code>, <code>Vary</code>, and related directives. An application cache in Java (Caffeine, Redis, cache decorator) is a separate logical layer.

If the Authorization Server returns:

~~~http
Cache-Control: no-store
Pragma: no-cache
~~~

then the client must not store the response for reuse. Never ignore <code>no-store</code> merely to lower latency. If the Authorization Server permits caching under a dedicated contract, define TTL, cache scope, revocation handling, and actual headers explicitly; never infer caching permission simply because the response is HTTP 200.

A standard <code>OpaqueTokenIntrospector</code> returns <code>OAuth2AuthenticatedPrincipal</code> and typically does not expose HTTP response headers to a wrapper layer. If you need to honor dynamic per-response cache directives, the HTTP transport layer must pass cache policy into the cache layer, or avoid a simple cache decorator. Never write a cache wrapper unable to observe <code>no-store</code> and cache every principal by default.

## 6. Designing Cache Keys and Cached Data

### 6.1. Never Use Raw Bearer Tokens as Cache Keys

A bearer token is a credential: anyone holding the token can exercise its permissions. If the cache key is written to logs, dumps, metric labels, or a distributed cache, the raw token could be exposed.

Use a one-way digest of the token:

\[
K = SHA\text{-}256(issuer \parallel 0x00 \parallel token)
\]

You can also include resource-server identity, introspection endpoint, or policy version if a cache is shared across multiple issuers/resource servers. Never use the raw token string in logs, tracing spans, metric labels, or exceptions.

Helper example:

~~~java
static String cacheKey(String issuer, String token) {
    try {
        MessageDigest digest = MessageDigest.getInstance("SHA-256");
        digest.update(issuer.getBytes(StandardCharsets.UTF_8));
        digest.update((byte) 0);
        digest.update(token.getBytes(StandardCharsets.UTF_8));
        return Base64.getUrlEncoder()
            .withoutPadding()
            .encodeToString(digest.digest());
    } catch (NoSuchAlgorithmException ex) {
        throw new IllegalStateException("SHA-256 unavailable", ex);
    }
}
~~~

SHA-256 here is used to derive a cache key, not to verify token validity. Never put cache keys into metric labels because cardinality will be huge; log keys only when needed for investigation and still subject to data policies.

### 6.2. Caching the Principal and Necessary Metadata

A cache entry may hold:

- <code>OAuth2AuthenticatedPrincipal</code> from the introspector.
- Absolute <code>freshUntil</code> timestamp.
- Token expiration (<code>exp</code>) if present.
- Issuer/resource-server policy version for invalidation when policy changes.
- Metadata for invalidation indexing such as authorization ID or <code>jti</code> if returned by introspection and allowed by contract.

Never cache raw HTTP requests, introspection client secrets, or raw tokens. Never use a cache key based solely on <code>jti</code> if <code>jti</code> is not globally unique across all issuers; at minimum namespace by issuer.

### 6.3. Cached Objects Must Not Be Mutated

If a principal or its attributes contain mutable collections, one request could modify the data and affect subsequent requests sharing the cache entry. Store immutable representations or deep-copy needed structures. Never attach request-specific state such as correlation IDs, servlet requests, or security contexts to shared cached objects.

## 7. Caching OpaqueTokenIntrospector in Spring Security

### 7.1. Extension Point

Spring Security uses the interface:

~~~java
public interface OpaqueTokenIntrospector {
    OAuth2AuthenticatedPrincipal introspect(String token);
}
~~~

The Resource Server calls <code>introspect(token)</code> when processing an opaque bearer token. An HTTP implementation calls the Authorization Server; a cache can be placed as an outer decorator around that implementation:

~~~text
BearerTokenAuthenticationFilter
  -> OpaqueTokenAuthenticationProvider
    -> CachingOpaqueTokenIntrospector
      -> Remote OpaqueTokenIntrospector
        -> Authorization Server /oauth2/introspect
~~~

The decorator caches only successful introspection results. It does not change how the client authenticates at the introspection endpoint or how the Authorization Server determines whether a token is active.

### 7.2. Caffeine Cache with Bounded TTL

The following example illustrates a positive cache. Enable it only when the introspection contract allows caching results and responses do not include <code>no-store</code>. Imports are omitted:

~~~java
public final class CachingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final Cache<String, CacheEntry> cache;
    private final Clock clock;
    private final String issuer;
    private final Duration maxTtl;
    private final Duration revocationBudget;

    public CachingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            Cache<String, CacheEntry> cache,
            Clock clock,
            String issuer,
            Duration maxTtl,
            Duration revocationBudget) {
        this.delegate = Objects.requireNonNull(delegate);
        this.cache = Objects.requireNonNull(cache);
        this.clock = Objects.requireNonNull(clock);
        this.issuer = Objects.requireNonNull(issuer);
        this.maxTtl = Objects.requireNonNull(maxTtl);
        this.revocationBudget = Objects.requireNonNull(revocationBudget);
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        Instant now = clock.instant();
        String key = cacheKey(issuer, token);

        CacheEntry cached = cache.getIfPresent(key);
        if (cached != null) {
            if (cached.freshUntil().isAfter(now)) {
                return cached.principal();
            }
            cache.invalidate(key);
        }

        // If the token is inactive or introspection fails, the delegate throws an exception.
        // Those exceptions must never be turned into active or cached.
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Instant freshUntil = now
            .plus(min(maxTtl, revocationBudget));
        Instant tokenExpiry = readExpiry(principal);
        if (tokenExpiry != null && tokenExpiry.isBefore(freshUntil)) {
            freshUntil = tokenExpiry;
        }

        if (freshUntil.isAfter(now)) {
            cache.put(key, new CacheEntry(principal, freshUntil));
        }

        return principal;
    }

    public void invalidate(String token) {
        cache.invalidate(cacheKey(issuer, token));
    }

    private static Duration min(Duration left, Duration right) {
        return left.compareTo(right) <= 0 ? left : right;
    }

    private static Instant readExpiry(
            OAuth2AuthenticatedPrincipal principal) {
        Object value = principal.getAttribute("exp");
        if (value instanceof Instant instant) {
            return instant;
        }
        if (value instanceof Date date) {
            return date.toInstant();
        }
        if (value instanceof Number epochSeconds) {
            return Instant.ofEpochSecond(epochSeconds.longValue());
        }
        return null;
    }

    private record CacheEntry(
        OAuth2AuthenticatedPrincipal principal,
        Instant freshUntil) {}
}
~~~

<code>Cache</code> in the example is <code>com.github.benmanes.caffeine.cache.Cache</code>. Initialize with bounded size and hard TTL:

~~~java
Cache<String, CacheEntry> cache =
    Caffeine.newBuilder()
        .maximumSize(50_000)
        .expireAfterWrite(Duration.ofSeconds(10))
        .build();
~~~

The snippet above illustrates the algorithm; give <code>CacheEntry</code> appropriate visibility for configuration beans creating the cache. <code>expireAfterWrite</code> is the hard cache cap; <code>freshUntil</code> inside the entry further bounds by <code>exp</code> and the revocation budget. Never configure a cache engine with stale-while-revalidate/stale-if-error extending past <code>freshUntil</code>.

**Note on expiry type:** Spring's introspection converter may represent <code>exp</code> as an <code>Instant</code> or another type depending on version/response converter. Verify the actual runtime type in your application. If expiry cannot be read, the cache must still be bounded by <code>maxTtl</code> and the revocation budget; never assume a token never expires.

### 7.3. Wiring the Decorator into the Resource Server

Configuration example:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        @Qualifier("cachingOpaqueTokenIntrospector")
        OpaqueTokenIntrospector introspector) throws Exception {

    http
        .authorizeHttpRequests(authorize -> authorize
            .requestMatchers("/health").permitAll()
            .anyRequest().authenticated())
        .oauth2ResourceServer(resourceServer ->
            resourceServer.opaqueToken(opaque ->
                opaque.introspector(introspector)));

    return http.build();
}
~~~

The <code>cachingOpaqueTokenIntrospector</code> bean must be created by wrapping a remote introspector already properly configured with the endpoint, client authentication, and TLS. Never inject the cache wrapper bean itself into its own delegate constructor; give the remote introspector a distinct name/qualifier to avoid circular dependencies.

### 7.4. Caching Is Only an Optimization Layer

The Resource Server must still check authorization on every request:

- Scope is sufficient for the endpoint/action.
- Audience matches the API.
- Tenant/principal matches the resource.
- Token type and client policies are valid.
- Fast-changing business conditions (disabled account, revoked entitlement) if required by the SLA.

Never cache an authorization decision like <code>hasAuthority("orders.write")</code> indefinitely simply because the introspection principal is cached for 10 seconds. If business permissions have their own cache, include it in the same revocation/freshness analysis.

## 8. Proactive Invalidation When a Token Is Revoked

### 8.1. TTL-Only vs. Event Invalidation

There are two strategies:

| Strategy | How It Works | Characteristics |
| --- | --- | --- |
| TTL-only | Entries expire naturally after TTL. | Easy to implement; stale window is bounded by TTL if there is no stale extension. |
| Event invalidation | Authorization Server emits an event on revocation; Resource Server deletes matching entries. | Faster revocation; requires delivery, retries, ordering, fan-out, and confirmation of application. |
| Combined | Events evict cache early; TTL acts as a safety net if events are lost. | Often suits systems needing low latency that can operate a reliable event bus. |

RFC 7662 does not define a standard push invalidation protocol for all Resource Servers. An event channel is an architectural extension of the system and must be secured and operated separately.

### 8.2. Event Payload

An event can carry authorization ID, token ID (<code>jti</code>), issuer, revocation timestamp, reason code, and policy version. Never send raw bearer tokens inside events. Example:

~~~json
{
  "event_type": "TOKEN_REVOKED",
  "issuer": "https://auth.example.com",
  "authorization_id": "authorization-42",
  "jti": "token-7f31",
  "revoked_at": "2026-11-16T10:15:30Z",
  "policy_version": 1842
}
~~~

This is an application-defined event schema, not a standard RFC 7662 payload. Events must have source authentication, replay protection, and a version/sequence so Resource Servers never overwrite newer state with older state.

### 8.3. Invalidating a Single Token or an Entire Authorization

An authorization may involve an access token, a refresh token, and multiple tokens issued across refreshes. When revoking an entire authorization/session, evicting only the cache entry for the token submitted to the revocation endpoint may be insufficient. Map authorization ID/token family to all related cached tokens or use a policy version to force re-introspection.

If the cache key is only a token hash, the event needs that token's digest. If invalidating by <code>jti</code>, the cache can maintain a secondary index; account for memory, races, and index cleanup. For opaque tokens, the Authorization Server might not return <code>jti</code>; in that case use authorization ID or token digest under an internal contract.

### 8.4. Race Between Introspection and Revoke Events

A race condition can occur:

1. Resource Server starts introspection.
2. Authorization Server returns <code>active=true</code>.
3. The token is revoked and an invalidation event is emitted.
4. Resource Server receives the event and evicts the cache.
5. The older introspection response arrives late and the cache wrapper writes <code>active=true</code> back.

Without a version/fence, stale entries can reappear after invalidation. Mitigation:

- Each token/authorization has a revocation version or epoch.
- Invalidation events update a tombstone/version before evicting the cache.
- When an introspection response returns, cache it only if the response is not older than the current version.
- If versions cannot be compared, record the invalidation timestamp and prevent responses started before that timestamp from repopulating the entry.
- Short TTLs act as a safety net when event ordering is imperfect.

## 9. Multi-Tier Caching and Stale Data

### 9.1. Common Cache Tiers

A request may pass through:

1. Cache inside <code>OpaqueTokenIntrospector</code> in each JVM.
2. Cache in a sidecar/API gateway.
3. Cache in a shared Redis/distributed store.
4. HTTP/proxy cache between Resource Server and Authorization Server.
5. Authorization state cache in another policy service.

There is no single TTL if multiple independent tiers hold copies.

### 9.2. Do Not Reset Data Age at Each Tier

Suppose the gateway caches an active result for 10 seconds. A service fetches the result from the gateway at second 9 and caches it for another 10 seconds from receipt. The data can be trusted for nearly 19 seconds since the real introspection call. Adding a third cache tier can extend the window even further.

To keep the bound:

- Propagate/maintain an **absolute freshness deadline** from the original introspection.
- Compute <code>remaining_ttl = fresh_until - now</code> at each tier.
- Honor <code>Age</code>/<code>Date</code>/<code>max-age</code> if using HTTP caching and permitted by contract.
- Never grant a fresh full TTL when reading from an upstream cache.
- Never use stale-while-revalidate or stale-if-error beyond the approved revocation budget.

If each tier resets TTL independently, conservatively calculate the worst case as the sum of all tier TTLs plus propagation/in-flight delays, or remove extra cache tiers.

### 9.3. Local Cache or Distributed Cache?

| Criterion | Local Cache (Caffeine) | Distributed Cache (Redis, etc.) |
| --- | --- | --- |
| Hit latency | Very low, no network call. | Incurs network round trip. |
| Shared across instances | No; each JVM has its own copy. | Can be shared. |
| Invalidation | Must broadcast to all instances. | Can delete centrally, though replica/partition handling is still needed. |
| Availability | Cache lives with the process. | Depends on cache cluster/network. |
| Capacity | Bounded by each node's heap. | Centrally managed, can be larger. |
| Risks | Nodes have inconsistent state if events are missed. | Stale reads/replication lag or cache outage. |

Local cache works well when TTLs are short, token counts are moderate, and broadcast invalidation exists. Distributed cache is useful when many instances must share results or require centralized eviction, though it does not automatically guarantee absolute consistency.

## 10. Outages and Fail-Open / Fail-Closed Decisions

### 10.1. Fresh Cache Hits During Authorization Server Errors

If a cache entry is still within its freshness deadline, the Resource Server can keep using the verified result per policy. This is an availability benefit of caching. However, once the entry expires and introspection cannot be reached, the Resource Server has no fresh proof that the token is still active.

### 10.2. Fail-Closed

Fail-closed means that when a token cannot be verified with a fresh result, no access is granted. The system can return an appropriate service error (e.g., 503 when the Authorization Server is unavailable) rather than assuming the token is invalid and returning 401 in all cases. Distinguish:

- Token verified inactive: 401.
- Unable to verify due to introspection outage: dependency service error (typically 503/5xx per API contract).

Fail-closed protects authorization, though it can disrupt the API during Authorization Server outages.

### 10.3. Fail-Open or Stale-If-Error

Fail-open uses expired active results or ignores introspection errors to let requests continue. It can improve availability, but breaks the revocation SLA bound. If using stale-if-error, explicitly define:

- Which API/risk categories may use it.
- Maximum staleness duration.
- Which errors trigger it (timeouts/5xx; never when the AS returns <code>active=false</code>).
- Whether the token is still within <code>exp</code> and scope/audience remain valid.
- Who approves it and how stale authorizations are observed.

Never make fail-open a hidden default behavior inside a cache library. Financial, administrative, sensitive-data, or high-privilege operations typically require fail-closed.

### 10.4. Circuit Breakers and Retries

A circuit breaker can stop the Resource Server from flooding a failing introspection endpoint. However:

- Retries must be bounded with backoff; never retry endlessly on every API request.
- Never retry <code>active=false</code>, <code>invalid_client</code>, or logic errors as if they were transient network errors.
- When the circuit is open and cache misses/expires, apply fail-closed or an approved stale policy.
- Never extend TTL just because the circuit breaker is open.
- Monitor circuit state, introspection error rate, and stale cache usage.

## 11. Configuring TTL per Resource Type

Not all APIs share the same risk tolerance. Policies can be tiered:

| API Type | Target Examples | Suggested Cache Policy |
| --- | --- | --- |
| Low-sensitivity informational reads | Catalogs, authenticated public content | Short/moderate TTL if revocation SLA allows. |
| Standard business APIs | Orders read, profile | Short TTL, clamped by <code>exp</code>, invalidation on revoke. |
| Data-mutating APIs | Orders write, billing operations | Very short TTL or per-request introspection, depending on SLA. |
| Admin/privileged APIs | Admin, key management, permission changes | Prefer freshest state checks; typically no stale positive usage. |
| Money/asset-handling APIs | Payments, transfers | Fail-closed, ultra-short TTL or centralized state per business requirements. |

TTL values must derive from threat models and SLAs—never treat the table above as a default for every system. Also consider token privilege: broader-scoped tokens usually require shorter freshness windows.

### 11.1. TTL by Token Lifetime

A token with 2 seconds left until <code>exp</code> cannot be cached as active for 10 seconds. The cache deadline must be clamped to <code>exp</code> or earlier per clock-skew policy. Tokens lacking <code>exp</code> in the introspection response need a small server-contract-defined TTL; never interpret missing `exp` as infinite.

### 11.2. TTL by Revocation Class

If a system has batch client tokens and administrative operation tokens, TTLs can be chosen by client/scope/audience:

- Read-only, low-privilege tokens: may have a longer cache TTL if SLA allows.
- Write or admin tokens: shorter TTL, proactive invalidation.
- Tokens tied to a tenant/session requiring fast revocation: cache keys and invalidation events must correlate to that tenant/authorization.

Never let clients send a header like <code>X-Cache-TTL</code> to extend how long their own permissions stay cached. TTL is a Resource Server policy, not a privilege dictated by a bearer token.

## 12. Observing Caching and Revocation

### 12.1. Metrics to Monitor

| Metric | Meaning |
| --- | --- |
| <code>introspection_requests_total</code> | Number of calls to the Authorization Server. |
| <code>introspection_latency</code> | Latency of introspection requests. |
| <code>introspection_errors_total</code> | Connection, HTTP, or parsing errors. |
| <code>introspection_cache_hits_total</code> | Cache hit count. |
| <code>introspection_cache_misses_total</code> | Cache miss count. |
| <code>introspection_cache_evictions_total</code> | Entries evicted due to TTL/capacity. |
| <code>introspection_active_total</code> | Aggregate count of active results. |
| <code>introspection_inactive_total</code> | Count of inactive results. |
| <code>revocation_event_lag</code> | Delay from revocation commit to cache invalidation. |
| <code>revocation_policy_version</code> | Policy version currently applied by the instance. |
| <code>stale_cache_served_total</code> | Count of stale entries served under special policy, if enabled. |

Never attach raw tokens, token hashes, <code>jti</code>, usernames, or client secrets as metric labels. Use low-cardinality labels such as resource server, issuer alias, result class, and cache tier.

### 12.2. Measuring Actual Revocation Latency

In a staging/production drill:

1. Issue a test token and call the API to populate the cache.
2. Revoke the token at the Authorization Server.
3. Record the revocation commit timestamp.
4. Record event publish/consume timestamps, if applicable.
5. Send continuous requests across regions/instances.
6. Record when the first request is rejected at each Resource Server.
7. Calculate max, p95, and p99 revocation latency and compare against the SLA.

Do not merely measure how quickly the revocation endpoint returns 200. Measure the time from **revocation commit** until **all verifiers stop accepting the token**.

### 12.3. Safe Logging

Logs may record issuer alias, resource server ID, result (<code>active</code>/<code>inactive</code>/<code>error</code>), cache hit/miss, policy version, latency, and request correlation ID. Never log raw bearer tokens or introspection bodies containing sensitive data. If incident correlation is needed, use a purpose-built, protected identifier.

## 13. Testing Caching and Revocation Delay

### 13.1. Unit Testing TTL and Expiration

Decouple clock and cache policy so tests do not require <code>Thread.sleep</code>. Test cases:

- Active responses are cached and subsequent calls hit the cache.
- Expired TTL invokes the delegate again.
- When <code>exp</code> is earlier than configured TTL, the entry expires at <code>exp</code>.
- <code>active=false</code> throws an exception and creates no positive entry.
- Timeouts/5xx create no cache entries.
- Expired cache entries are never returned even if the cache engine has not physically evicted them yet.
- Cache keys differ by issuer/token digest.

### 13.2. Testing Revocation Latency

An integration test can simulate:

~~~text
T0: Introspect token T -> active=true
T1: Resource Server caches T for 5 seconds
T2: Authorization Server revokes T
T3: Request using T before invalidation/TTL -> may be accepted
T4: Invalidation event reaches Resource Server -> cache entry evicted
T5: Request using T -> re-introspect -> active=false -> 401
~~~

Assertions must measure <code>T5 - T2</code>, not merely assert that an event handler was invoked. If there are no events, verify the token is rejected once TTL expires. With multiple instances, test every instance and newly booted nodes.

### 13.3. Test Matrix

| Case | Expected Result |
| --- | --- |
| Cache miss, introspection active | Calls AS, caches within valid TTL, and permits if scope/audience match. |
| Cache entry expired | Re-queries AS before deciding. |
| Token revoked right after cache fill | Accepted at most within the published TTL/event window. |
| Invalidation event arrives before TTL | Cache entry is evicted and next request re-introspects. |
| Invalidation event lost | Fallback TTL still bounds stale window within SLA. |
| Response <code>active=false</code> | Rejected; no positive cache entry created. |
| Timeout/5xx | Not cached as active/inactive; outage policy applied. |
| Response has <code>Cache-Control: no-store</code> | Response is not stored in cache. |
| Token expires before cache TTL | Cache does not serve past <code>exp</code>. |
| Multiple cache tiers | Freshness deadline is not reset at each tier. |
| Event arrives late after stale introspection response | Stale response cannot recreate an invalidated entry. |
| Token family revoked | Evicts all related cache entries or increments policy version. |
| Registry/event bus failure | Fail-safe behavior per policy with alerting. |
| Newly autoscaled Resource Server | Loads revocation state before serving traffic. |
| Wrong introspection credentials | Reports configuration error; never caches. |
| Wrong audience | Rejected even if introspection returns `active=true`. |
| Insufficient scope | Rejected even if introspection returns `active=true`. |
| Token hash as cache key | Raw token never appears in logs/metrics/visible cache keys. |

## 14. Common Design Mistakes

### Mistake 1: Caching active=true Too Long to Optimize Latency

**Symptom:** A token is revoked yet the API still accepts it for minutes.

**Cause:** TTL was chosen for performance without accounting for the revocation SLA.

**Fix:** Quantify the stale window, set TTL according to the SLA, and add reliable invalidation.

### Mistake 2: Caching Active Tokens Past exp

**Symptom:** Expired tokens still succeed on cache hits.

**Cause:** Fixed cache TTL not clamped by expiration.

**Fix:** <code>freshUntil = min(configuredDeadline, exp, revocationDeadline)</code> and check freshness on every hit.

### Mistake 3: Ignoring Cache-Control: no-store

**Symptom:** Introspection responses are cached even though the Authorization Server forbids caching.

**Cause:** Adding a Caffeine/Redis decorator without checking cache directives.

**Fix:** Respect `no-store`; enable caching only when the AS contract permits it and transport can enforce policy properly.

### Mistake 4: Caching Timeouts as active=false

**Symptom:** Temporary Authorization Server downtime causes all tokens to be treated as inactive.

**Cause:** Collapsing connection errors and inactive results into the same cached value.

**Fix:** Distinguish inactive tokens from introspection unavailability; never cache errors.

### Mistake 5: Unbounded Fail-Open After Cache Expiry

**Symptom:** APIs continue accepting tokens while the Authorization Server is down.

**Cause:** Unbounded stale-if-error extension.

**Fix:** Choose fail-closed or a stale allowance with an explicit deadline, scope, and owner; measure stale served counts.

### Mistake 6: Multi-Tier Caches Resetting TTL

**Symptom:** Configured TTL is 10 seconds, yet tokens remain accepted far longer.

**Cause:** Each cache tier recomputes TTL from when it received stale data.

**Fix:** Use an absolute freshness deadline/remaining TTL and never reset data age.

### Mistake 7: Invalidation Event Arrives Yet Stale Response Repopulates Cache

**Symptom:** Cache entry reappears immediately after revocation.

**Cause:** Race between in-flight introspection and the event handler.

**Fix:** Version/fence/tombstone per token or authorization, and never cache responses older than the revocation version.

### Mistake 8: Evicting One Token When an Entire Authorization Is Revoked

**Symptom:** Other refresh-derived access tokens remain accepted.

**Cause:** Cache lacks relationships between tokens and authorizations/token families.

**Fix:** Maintain an index or authorization version to invalidate all related tokens.

### Mistake 9: Using Raw Tokens as Cache Keys or in Logs

**Symptom:** Bearer tokens appear in Redis keys, heap dumps, or logs.

**Cause:** Using raw token strings directly for convenience.

**Fix:** Use a digest, restrict cache access, encrypt sensitive data, and avoid logging tokens.

## 15. Production Checklist

| Item | Question to Confirm |
| --- | --- |
| Revocation SLA | How soon after revocation commit must all APIs reject the token? |
| Cache permission | Does the introspection response have <code>no-store</code>? Does the contract allow application caching? |
| TTL | Is TTL bounded by <code>exp</code>, SLA, and propagation margin? |
| Positive cache | Are only verified active results cached? |
| Negative/error | Inactive never confused with timeout/5xx; is negative TTL truly needed? |
| Cache key | Uses token digest and namespaces issuer/resource server? |
| Multi-tier | Is freshness deadline propagated across tiers without resetting TTL? |
| Invalidation | Are there events for token/authorization revocation and a repair mechanism for missed events? |
| Race | Can stale introspection responses recreate an entry after revocation? |
| Outage | Are fail-open/closed and stale allowances approved? |
| Expiry | Never serves cached principals past <code>exp</code>? |
| Authorization | Are scope/audience/tenant still checked at the Resource Server? |
| Observability | Are hit ratio, latency, event lag, stale served, and policy version tracked? |
| Security | No raw token logging, no bearer tokens in cache keys, introspection client authenticated? |
| Testing | Tests cover TTL, invalidation, event loss, multi-node, outages, and token families? |

## 16. Hands-On Exercise

Orders API receives 5,000 requests/second. The Authorization Server has a p95 introspection latency of 35 ms. Product requires that when an administrator revokes a token, all Resource Server instances reject the token within at most 8 seconds. There are 6 API instances, each using a Caffeine local cache; the event bus has 2-second p99 propagation but can drop events.

1. Estimate the approximate introspection request rate without caching and explain why this is a load estimate rather than an exact guaranteed request count.
2. Choose a local cache TTL that still meets the SLA if events are dropped.
3. Calculate the stale window when the cache is populated right before revocation.
4. Design event invalidation to evict caches across all 6 instances and confirm every instance applied it.
5. Handle the race when an <code>active=true</code> introspection returns after the revocation event has already been processed.
6. Design a cache key that stores no raw bearer token and namespaces by issuer.
7. Define behavior when the Authorization Server is down and cache entries are fresh, expired, or stale.
8. Check responses for <code>Cache-Control: no-store</code>; decide whether application caching is permitted.
9. Write virtual-clock tests for TTL, <code>exp</code>, invalidation events, and token families.
10. Propose metrics to prove p95/p99 revocation latency meets the SLA.

**Pass criteria:** You can quantitatively explain how cache hits reduce round trips and introspection load, while proving **the time a Resource Server continues trusting a stale active result always stays within the approved revocation budget**.

## 17. Reference Materials

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response, <code>active</code>, metadata, and security considerations.
- [RFC 6749 — OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749): token lifecycle, token revocation context, and client authentication.
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009): token revocation and revocation endpoint semantics.
- [RFC 9111 — HTTP Caching](https://www.rfc-editor.org/rfc/rfc9111): cache directives, freshness, age, and validation.
- [Spring Security — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): <code>OpaqueTokenIntrospector</code>, opaque token authentication, and introspection configuration.
- [Spring Authorization Server — Protocol Endpoints](https://docs.spring.io/spring-authorization-server/reference/protocol-endpoints.html): Token Introspection Endpoint and token status handling.
- [Caffeine Cache](https://github.com/ben-manes/caffeine/wiki): TTL, eviction, maximum size, and cache implementation for Java.
