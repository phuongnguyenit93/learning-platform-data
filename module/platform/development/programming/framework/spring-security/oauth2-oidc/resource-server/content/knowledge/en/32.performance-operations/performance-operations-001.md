# Cost of Local JWT Verification vs. Remote Introspection

A Spring Security Resource Server has two common verification paths for access tokens: **local JWT verification** using signatures and claims, or **calling the Authorization Server's token introspection endpoint** to check whether the token is still active and retrieve related metadata. Both approaches carry different operational costs.

With local JWT verification, the Resource Server typically verifies the signature on every request using public keys fetched and cached from JWKS. Most requests do not need to call the Authorization Server; the main costs lie in token parsing, cryptographic verification, validators, object allocation, and CPU on the Resource Server. With introspection, the Resource Server sends the token to a remote endpoint. Without caching the result, every request incurs an additional network round trip and processing load on the Authorization Server. Caching reduces that cost, but extends the window during which the Resource Server may continue accepting a stale active result after a token has been revoked.

Neither option is always faster or always more secure. The decision depends on request rate, inter-service latency, the Authorization Server's capacity, token revocation requirements, token format, cache policy, and identity infrastructure availability.

This lesson belongs to the **Performance and Operations** chapter, focusing on the CPU cost of JWT signature verification, the network cost of introspection, the differences between a JWKS cache and an introspection-result cache, Spring Security configuration, capacity planning, benchmarking, metrics, timeouts, retries, and outage behavior.

> **Illustrative Context:** The Orders API runs on Spring Boot 3.x / Spring Security 6.x and receives access tokens from an Authorization Server. We compare locally verified JWT access tokens with opaque access tokens verified via RFC 7662 introspection. A JWT can also be introspected if the architecture requires centralized state; the two options describe how the Resource Server verifies tokens, not solely the string format of the token.

## 1. Two Access Token Verification Models

### 1.1. JWT: The Resource Server Verifies Locally

A JWT access token contains claims and a signature. The Resource Server retrieves the public key from JWKS, then verifies the signature and validates the issuer, audience, expiration, token profile, and authorities.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant JWKS as JWKS Endpoint
    Note over RS,JWKS: Key set is typically fetched and cached
    C->>RS: Request + Bearer JWT
    RS->>RS: Parse JWT
    RS->>RS: Verify signature using cached public key
    RS->>RS: Validate issuer, audience, exp, nbf
    RS->>RS: Map claims to authorities
    RS-->>C: Response
~~~

In steady state, individual requests do not need to call the JWKS endpoint. JWKS is fetched when the decoder needs the key set, when the cache expires, or when a refresh is needed due to an unknown key ID, depending on the JWK source and configuration.

### 1.2. Introspection: The Resource Server Queries the Authorization Server

The Resource Server sends the token to a configured endpoint. The Authorization Server returns a response indicating whether the token is active and may include subject, scope, audience, client ID, expiry, or other attributes.

~~~mermaid
sequenceDiagram
    participant C as Client
    participant RS as Resource Server
    participant AS as Authorization Server
    C->>RS: Request + access token
    RS->>AS: POST /introspect
    AS->>AS: Check token state and policy
    AS-->>RS: active + token metadata
    RS->>RS: Build authenticated principal
    RS-->>C: Response
~~~

Without caching, every authenticated request triggers an introspection call. When the Resource Server caches results, only cache misses need to call the Authorization Server.

### 1.3. Token Format and Verification Path Are Separate Concepts

Common pairings:

- JWT + local validation is a common model because a JWT contains claims and a signature that can be checked offline.
- Opaque token + introspection is a common model because the Resource Server cannot decode the token on its own.
- JWT + introspection can still be used if centralized state checking is desired.
- An opaque token can be verified through a custom mechanism if the system has an appropriate trust contract.

When comparing costs, identify the actual **verification path**. Do not assume that every JWT is verified locally or that every opaque token must be introspected the same way in every architecture.

## 2. Cost of Local JWT Verification

A JWT request typically performs the following steps:

1. Extract the access token from the Authorization header.
2. Parse the compact JWT and protected header.
3. Look up the public key matching the issuer and kid in the JWK set cache.
4. Verify the signature using an allowed algorithm.
5. Validate issuer, audience, timestamps, and token profile.
6. Convert claims into a principal and authorities.
7. Enforce authorization for the endpoint/service.

### 2.1. CPU Is the Primary Cost on the Request Path

Signature verification cost depends on the signing algorithm such as RS256, PS256, or ES256; RSA key size or curve; JWT size and number of claims; JOSE/JWT library; CPU architecture; JVM/JIT; garbage collector; validators; and custom converters.

Signature verification is usually cheaper than a network round trip to the Authorization Server, but it is not free. At very high request rates or with large tokens/claims, parsing, cryptography, and object allocation can consume substantial CPU.

### 2.2. Public Keys Are Cached, but Signatures Still Must Be Verified per Token

JWKS caching avoids repeatedly downloading public keys. It does not mean the Resource Server caches the authentication result of every access token.

Typically, every request still needs to read the token, parse or process the compact JWT, verify the signature, run validators, and build the Authentication/authorities for the request. The public key cache reduces network and key-parsing overhead; it does not replace verifying the current request's signature with a stale authentication result.

### 2.3. JWKS Fetch Is an Amortized Cost, Not Per-Request

| Operation | Typical Frequency | Impact |
|---|---|---|
| JWT parse/signature/claims validation | Every request | CPU, allocation, internal latency |
| JWKS fetch/refresh | Startup, refresh, or unknown kid | Network, latency dependent on identity provider |

If the Resource Server has a stable key set cache, the number of JWKS fetches is typically far lower than the number of API requests. Cold starts, key rotation, cache expiry, or unknown kids can trigger refresh spikes. Both steady state and cold/rotation behavior should be measured.

### 2.4. Local Validation Reduces Coupling to Authorization Server Availability

Once keys are in the cache, the Resource Server can verify tokens without requiring the Authorization Server to respond for every request. This reduces synchronous dependency between API traffic and the introspection service.

Even so, the system still depends on the issuer/JWKS to fetch new keys, start up under certain discovery configurations, and handle rotation. Local JWT validation does not mean the identity infrastructure can remain down indefinitely.

### 2.5. Local Validation Does Not Automatically Detect Immediate Revocation

If a token is validly signed and has not expired, the Resource Server may continue accepting it after the user is disabled or the AS intends to revoke it, unless additional mechanisms are in place.

Ways to narrow this window include short access token lifetimes, a denylist/revocation store, token version/session state, event-driven invalidation, introspection for sensitive endpoints, or emergency denial by signing key. Each additional mechanism carries consistency, latency, and availability costs. If every request has to query a remote revocation store, part of the benefit of local JWT validation is reduced.

## 3. Cost of Remote Introspection

### 3.1. A Network Round Trip Sits on the Authentication Path

Without caching, an API request typically creates an extra HTTP request to the Authorization Server. Latency depends on network distance, DNS/TLS/connection setup if connections are not reused, connection pooling, AS queueing, database/cache on the AS side, serialization, and network congestion.

Even when the introspection endpoint processes requests quickly, the network round trip can account for most of the added latency.

### 3.2. Introspection Scales Load with Request Rate

Suppose a Resource Server receives 5,000 API requests/second and every request introspects the token. Without caching, the AS must handle roughly 5,000 introspection requests/second from that workload alone, not counting retries or traffic from other Resource Servers.

If 12 instances receive traffic concurrently, total load must be calculated across the entire cluster. Never capacity-plan based on a single pod.

### 3.3. Introspection Creates a Direct Availability Dependency

If the AS introspection endpoint is unavailable, the Resource Server cannot obtain fresh token state on a cache miss. When a valid cached entry exists, the request may proceed using the cached result if policy allows. Without a trustworthy result, the Resource Server must fail closed.

~~~text
API request
   |
   v
Resource Server
   |
   v
Introspection endpoint
   |
   v
Authorization Server state
~~~

An outage in the AS, network, or connection pool can affect multiple APIs simultaneously. Introspection should be treated as a critical production dependency with its own SLOs, capacity, timeouts, and alerts.

### 3.4. Introspection Can Provide Up-to-Date Centralized State

The Authorization Server can respond based on current token state: whether the token is still active, whether it has been revoked, whether the client/user/session is disabled, which scopes/audiences are granted, and what metadata may be shared.

This capability depends on how the AS is implemented and its internal caching. RFC 7662 defines the active response, but does not by itself guarantee that every state change is reflected instantaneously if the AS has caching or replication lag.

## 4. Overall Cost Comparison

| Criterion | JWT local verification | Remote introspection |
|---|---|---|
| Per-request work | Parse, verify signature, validate claims | HTTP call or cache lookup, parse response |
| Resource Server CPU | Includes cryptographic verification | Lower JWT crypto cost if not verifying JWT itself |
| Steady-state network | Typically no call to AS | Makes request on cache miss |
| Latency | Primarily CPU and request processing | Adds network + AS processing on miss |
| Authorization Server load | JWKS refresh/discovery and token issuance | Scales with introspection traffic |
| Revocation visibility | Not immediate without additional mechanisms | Can be near real-time depending on AS state/cache |
| Dependency during AS outage | Can continue with cached public keys | Cache hits may continue; misses require AS |
| Key cache | Public JWK set | Introspection result per token |
| Scaling dimension | Verification CPU on each Resource Server | AS throughput and network fan-out |
| Metadata | Claims in JWT | Attributes in introspection response |

### 4.1. Do Not Compare CPU Against Network Alone

Measuring only signature verification CPU and introspection latency is insufficient. You must also account for AS CPU, TLS/network overhead, cache memory, JWKS fetches during rotation/cold starts, retry amplification, cache-induced revocation delay, and the operational cost of identity infrastructure.

An approach that lowers CPU on the Resource Server while shifting heavy load onto the Authorization Server can increase total system cost.

## 5. Simple Cost Model for Estimation

Let:

- R: total API requests per second requiring authentication.
- Cj: CPU time to verify one JWT, in CPU seconds.
- Ci: Resource Server CPU time for introspection response handling.
- L: latency of one introspection round trip.
- h: introspection cache hit ratio, from 0 to 1.
- Ca: CPU time spent by the Authorization Server per introspection.
- J: number of JWKS refresh requests per second in steady state.

### 5.1. Local JWT Verification

~~~text
ResourceServer CPU cores for verification
    ~= R * Cj
~~~

For example, if one verification consumes 0.25 ms of CPU and the system processes 4,000 requests/second:

~~~text
4,000 * 0.00025 seconds
    = 1 CPU core
~~~

This is an arithmetic example, not a benchmark for Spring Security or a specific algorithm. Actual CPU usage must be measured on your application's hardware/JVM.

JWKS traffic is accounted for separately: the JWKS fetch rate is approximately J. In steady state J can be low; during a rollout or an unknown-kid flood, it can spike sharply.

### 5.2. Introspection Without Caching

~~~text
Introspection request rate ~= R
AS CPU demand ~= R * Ca
Additional latency ~= L
~~~

If the request rate is 4,000/second, the AS must handle roughly 4,000 introspection requests/second for that workload. Latency L sits on the synchronous request authentication path.

### 5.3. Introspection With Caching

If the cache hit ratio is h:

~~~text
Introspection request rate ~= R * (1 - h)
AS CPU demand ~= R * (1 - h) * Ca
~~~

For example, with R = 4,000 requests/second and a 95% hit ratio:

~~~text
4,000 * (1 - 0.95) = 200 remote requests/second
~~~

Caching substantially reduces AS traffic, but does not eliminate misses, evictions, cold starts, or concurrent duplicate misses.

### 5.4. Average Latency and Tail Latency

~~~text
Average auth latency
    ~= h * L_hit + (1 - h) * L_miss
~~~

L_hit is typically a local cache lookup and principal construction. L_miss includes the network round trip, AS processing, and response parsing. The average formula does not fully capture p95/p99. Even a small fraction of cache misses can dominate tail latency when the AS experiences occasional slowdowns.

### 5.5. Cluster-Wide Calculation

~~~text
Cluster introspection QPS
    = sum(request rate of every Resource Server)
      * (1 - effective cache hit ratio)
~~~

If each pod maintains its own cache, the hit ratio can be lower when traffic is spread across many infrequently repeated tokens. Scaling out can create cold caches on new pods. A centralized cache can increase the hit ratio, but adds a network hop and its own dependency.

## 6. Introspection Cache: Reducing Load and Bounding Revocation Delay

### 6.1. Cache Keys Must Represent the Exact Token Without Storing Raw Tokens

An introspection result belongs to a specific access token. The cache key must distinguish tokens precisely while avoiding storing raw tokens in keys, logs, or metrics. A cryptographic hash or HMAC of the token can be used as the cache key.

Do not use a token prefix, subject, or client ID as the key because multiple tokens can share the same subject or client while having different state, scopes, audiences, and expiries. A fingerprint can still be a sensitive identifier; never place it in logs or metric labels.

### 6.2. Cache Active Responses with a Bounded TTL

If introspection returns:

~~~json
{
  "active": true,
  "sub": "customer-42",
  "scope": "orders.read",
  "aud": ["orders-api"],
  "exp": 2000000600
}
~~~

The Resource Server can cache the principal/metadata for a short TTL. The TTL should not exceed the remaining time until token expiry, the acceptable revocation staleness window, and the maximum TTL allowed by security policy.

~~~text
cacheTTL = min(
    configuredMaximumTTL,
    tokenExpiry - now,
    allowedRevocationStaleness
)
~~~

If the response does not contain a trustworthy expiry claim, use only a small configured TTL per policy. Never cache an active result longer than the token can remain valid.

### 6.3. Caching Active Results Delays Revocation Visibility

Suppose the Resource Server caches an active result for 60 seconds. A user is disabled right after the cache entry is created. The Resource Server may continue accepting the token until the entry expires or is invalidated.

TTL is not purely a performance parameter; it is a security policy decision. If revocation is required to take effect within at most 5 seconds, a 60-second TTL fails that requirement.

### 6.4. Cache Negative Results Carefully

Short negative caching can reduce load when the same inactive token is sent repeatedly, but:

- Do not cache network/timeout errors as if the token were inactive.
- Do not cache server errors as authentication results.
- Use a short TTL for inactive results.
- Bound the cache size so random tokens cannot exhaust memory.
- Distinguish active=false from introspection service unavailability.

Do not turn a transient AS outage into long-lived negative caching that keeps rejecting valid tokens after the service recovers.

### 6.5. Concurrent Cache Misses and Stampedes

Many requests carrying the same token can arrive at a pod right after a cache entry expires. If every request introspects simultaneously, they create a burst to the AS.

Techniques that can be used:

- Per-key single-flight/loading cache.
- A cache provider with atomic loading semantics.
- Concurrency limits to the introspection endpoint.
- Connection pooling.
- TTL jitter to avoid many entries expiring simultaneously.
- Rate limits or bulkheads for introspection calls.

Do not use a single global lock that blocks all tokens when only one key misses. Synchronization should be scoped per token fingerprint.

### 6.6. Cache Results Must Be Isolated by Issuer/Resource Policy

If the application supports multiple issuers, the cache key must include the appropriate trust context, or cache namespaces must be separated per issuer/introspection client. Never share a single cache entry between two authorization servers with different policies.

If principal mapping depends on the resource/audience or client registration, the cache key and cached result must reflect that context.

## 7. Caching OpaqueTokenIntrospector in Spring

Spring Security lets you customize `OpaqueTokenIntrospector`. You can wrap the real introspector with a cache to cache the principal returned from introspection.

~~~java
public final class CachingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final Cache cache;

    public CachingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            Cache cache) {
        this.delegate = delegate;
        this.cache = cache;
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        String key = hmacFingerprint(token);

        Cache.ValueWrapper cached = cache.get(key);
        if (cached != null) {
            return (OAuth2AuthenticatedPrincipal) cached.get();
        }

        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        // Cache only successful active results.
        // The cache provider must enforce a bounded TTL and size.
        cache.put(key, principal);
        return principal;
    }
}
~~~

This is a skeleton illustrating the decorator; imports, the HMAC helper, and the cache provider are omitted. Production requires a cache provider with TTL and size limits; a TTL that never exceeds token expiry or revocation staleness policy; per-entry expiry when token lifetimes vary; single-flight to avoid duplicate misses; never caching network/AS exceptions; considering immutable or defensively copied principal attributes; separate cache namespaces per issuer; and metrics for hits, misses, evictions, and expirations.

Do not use a single long fixed TTL for every token if token lifetimes vary. If a trustworthy expiry cannot be determined from the introspection response, enforce a tighter policy TTL.

### 7.1. Configuring the Introspection Endpoint

Example application YAML:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        opaquetoken:
          introspection-uri: https://id.example.com/oauth2/introspect
          client-id: orders-resource-server
          client-secret: SECRET_FROM_ENVIRONMENT
~~~

Or via DSL:

~~~java
http.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspectionUri(
            "https://id.example.com/oauth2/introspect"
        )
        .introspectionClientCredentials(
            "orders-resource-server",
            introspectionClientSecret
        )
    )
);
~~~

Client credentials here authenticate the Resource Server to the introspection endpoint. They are not the end user's access token. Keep secrets in a secret manager or environment injection; never commit them to source control or logs.

### 7.2. Wiring the Caching Introspector into the Resource Server

Conceptual configuration:

~~~java
@Bean
OpaqueTokenIntrospector opaqueTokenIntrospector(
        CacheManager cacheManager,
        IntrospectionProperties properties) {

    OpaqueTokenIntrospector remote =
        new NimbusOpaqueTokenIntrospector(
            properties.introspectionUri(),
            properties.clientId(),
            properties.clientSecret()
        );

    return new CachingOpaqueTokenIntrospector(
        remote,
        cacheManager.getCache("activeAccessTokens")
    );
}
~~~

The Resource Server uses the introspector bean according to the corresponding configuration:

~~~java
.oauth2ResourceServer(oauth2 -> oauth2
    .opaqueToken(opaque -> opaque
        .introspector(opaqueTokenIntrospector)
    )
)
~~~

Constructor names, property binding, and how Spring Boot auto-creates the introspector may vary by version. When providing a custom bean, verify auto-configuration back-off and ensure only one introspector is used in the filter chain.

## 8. Configuring Local JWT Verification in Spring Security

### 8.1. Using issuer-uri and JWKS

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
~~~

Spring Security uses issuer metadata/JWKS discovery according to configuration to build the decoder. At runtime, public keys are fetched and cached according to JWK source behavior; the JWT signature is verified for each token.

You can configure the JWKS URI directly:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://id.example.com
          jwk-set-uri: https://id.example.com/oauth2/jwks
~~~

Configuring the JWKS URI directly can reduce the need for metadata discovery on some startup paths, though issuer validation must still be preserved. Check the behavior of the Spring Boot/Spring Security version in use.

### 8.2. Adding an Audience Validator

A valid JWT signature is not enough; the token must also be issued for this API.

~~~java
OAuth2TokenValidator<Jwt> audienceValidator = jwt -> {
    if (jwt.getAudience().contains("orders-api")) {
        return OAuth2TokenValidatorResult.success();
    }

    OAuth2Error error = new OAuth2Error(
        "invalid_token",
        "Required audience is missing",
        null
    );

    return OAuth2TokenValidatorResult.failure(error);
};
~~~

Combine with the default issuer/time validators:

~~~java
@Bean
JwtDecoder jwtDecoder() {
    String issuer = "https://id.example.com";
    String jwkSetUri = "https://id.example.com/oauth2/jwks";

    NimbusJwtDecoder decoder =
        NimbusJwtDecoder.withJwkSetUri(jwkSetUri).build();

    OAuth2TokenValidator<Jwt> validator =
        new DelegatingOAuth2TokenValidator<>(
            JwtValidators.createDefaultWithIssuer(issuer),
            audienceValidator()
        );

    decoder.setJwtValidator(validator);
    return decoder;
}
~~~

Do not replace default timestamp/issuer validation with a standalone custom audience validator unless intentional. Compose validators so all conditions remain enforced.

### 8.3. Signature Verification Still Consumes CPU

Local JWT validation is not decoding the payload and trusting its claims. The Resource Server must verify the signature using a trusted public key. Only after both the signature and validators succeed should an authenticated principal be created.

Do not cache an authentication decision indefinitely based on the token string. If verified results are cached, you must account for exp, key rotation, issuer/audience policy, revocation, and cache invalidation. In most systems, caching the public JWKs is sufficient and easier to control.

## 9. Optimizing Performance for JWT Verification

### 9.1. Keep the JWK Source and Connection Pooling Stable

JWKS fetches should use an HTTP client with connection reuse, explicit timeouts, and proper TLS configuration. Avoid creating a new HTTP client per request or per decoder instance. Ensure the decoder/JWK source is managed as a singleton appropriate to the application context.

### 9.2. Avoid Refresh Storms on Unknown Key IDs

When key rotation occurs, many initial requests may carry the new kid. If every request triggers a JWKS refresh simultaneously, the AS/JWKS endpoint experiences a burst. Review the cache/refresh mechanism of your Nimbus/Spring version and apply concurrency limits or rate controls at the appropriate layer.

An unknown kid can also be exploited by an attacker to induce load. Never refresh unboundedly or synchronize unboundedly on the request path.

### 9.3. Keep Tokens and Claims Reasonably Sized

Oversized JWTs increase header parsing, base64url decoding, JSON parsing, allocation, network bytes at every hop, logging/tracing risk, and proxy header limits. Include only necessary claims in access tokens. Avoid embedding user profiles, very long permission lists, or business data that can be queried from a dedicated service.

### 9.4. Choose Algorithms Based on Policy and Benchmarks

RSA and EC have different performance profiles across CPUs and JVMs. Do not pick an algorithm based on a benchmark on a single machine. Consider interoperability, key management, issuer support, security policy, and benchmark results on production-like hardware.

Never reduce key size or switch to a weaker algorithm solely for throughput. An algorithm allowlist must be explicitly configured.

### 9.5. Do Not Cache JWT Principals While Bypassing Validators

Caching authentication results by token fingerprint can bypass a newly passed expiry, updated issuer/audience policy, a denied/compromised key, token revocation, or changed tenant/permission policies.

If caching is unavoidable, entry TTLs must be bounded by exp and staleness budgets; invalidation must occur when keys/policies change; and a cache hit must not be treated as unbounded authority. For most systems, caching the JWK set and verifying tokens per request is simpler.

## 10. Optimizing Performance for Remote Introspection

### 10.1. Use an HTTP Connection Pool

The introspection client should reuse connections and TLS sessions. Never create a new HTTP client per request. Size pool limits to match concurrency and AS capacity; measure connection lease wait time separately from AS processing time.

### 10.2. Set Finite Timeouts

Configure connection timeout, response/read timeout, pool acquisition timeout, and an overall deadline aligned with the API request budget.

Never let requests hold threads or connections indefinitely when the AS hangs. Overly short timeouts cause false errors under heavy load; overly long timeouts inflate tail latency and tie up resources.

### 10.3. Limit Concurrency and Retries

A bulkhead or semaphore can cap concurrent introspection calls. When the AS is overloaded, failing early per policy is better than letting all requests queue indefinitely.

Retries should only be used for well-defined transient errors, with a small retry count, backoff/jitter, and a deadline. Do not retry inactive tokens or invalid credentials. Do not retry all 4xx responses. Retries can multiply load during an outage if there is no retry budget.

### 10.4. Cache Deliberately

Caching active results can reduce QPS to the AS. Choose TTLs based on revocation SLAs, token expiry, and invalidation capabilities. A local cache offers low latency with per-pod consistency; a distributed cache shares state but adds a network hop and its own dependency.

### 10.5. Distinguish Introspection Failures from Inactive Tokens

These are two distinct situations:

- The AS returns a successful response with active=false: the token is inactive.
- The Resource Server cannot reach the AS or receives a malformed response: token state is unknown.

Never cache a dependency failure as an inactive token. Never turn a dependency failure into an authenticated state. Error mapping should distinguish invalid tokens from identity provider unavailability in line with the API contract and observability.

## 11. Availability and Fail-Closed Behavior

### 11.1. Local JWT Validation During a JWKS Endpoint Outage

If the required public key is still cached, the Resource Server can continue verifying JWTs according to the JWK source's behavior. If a new key is needed and JWKS cannot be fetched, the token cannot be verified and must be rejected.

Never bypass signature verification when JWKS is unavailable.

### 11.2. Introspection Outage

If the cache holds an active result within its TTL and policy allows it, the Resource Server can use that result. On a cache miss when the AS is unreachable, the Resource Server does not know whether the token is active. It must fail closed for requests requiring authentication.

Never treat a timeout as active. Never accept a token simply because an earlier request succeeded.

### 11.3. Should You Return 401 or 503?

Invalid/inactive tokens are typically handled as authentication failures, usually 401 with appropriate Bearer semantics. Dependency unavailability is an operational failure. An API gateway or error handler may choose 503 when it determines the identity dependency is unavailable, but must never turn it into access granted.

Spring Security's default exception mapping and the exception types thrown by the decoder/introspector can affect the final status code. If the API needs to distinguish 401 invalid token from 503 identity provider outage, configure and integration-test the mapping for your version; do not change status codes in a way that leaks internal details or tokens.

### 11.4. A Circuit Breaker Is Not an Allow Fallback

A circuit breaker stops calls to a failing AS and protects thread pools. When the circuit is open, a request requiring introspection still has no trustworthy result. The safe fallback is to reject or return a dependency error per contract, never to automatically accept the token.

## 12. Capacity Planning for Resource Server and Authorization Server

### 12.1. Estimating JWT CPU

Use realistic benchmarks to measure CPU time for a representative token:

~~~text
JWT verification CPU cores
    ~= request rate * CPU seconds per verification
~~~

Add CPU for controllers, database, serialization, TLS, and other filters. Do not allocate the entire core budget to signature verification.

### 12.2. Estimating AS Introspection QPS

Without caching:

~~~text
AS introspection QPS ~= authenticated API request QPS
~~~

With caching:

~~~text
AS introspection QPS
    ~= API request QPS * (1 - cache hit ratio)
~~~

Account for retries, cold starts, multiple resources, token churn, and cache evictions. The cache hit ratio must be measured against realistic workloads; do not assume 99% if every request carries a different token.

### 12.3. Estimating Concurrency from Latency

An estimate using Little's Law:

~~~text
in-flight introspection calls
    ~= introspection arrival rate * average response time
~~~

For example, 1,000 calls/second with a 40 ms average round trip:

~~~text
1,000 * 0.040 = 40 concurrent calls
~~~

This is an idealized average concurrency. p95/p99, traffic bursts, and connection pool contention may require higher headroom.

### 12.4. Scaling Out Can Make Caches Colder

If the introspection cache is local to each pod, adding pods spreads token traffic and creates cache cold starts. If each token is used only a few times, the hit ratio may be low. A distributed cache increases sharing, but adds network and availability dependencies.

Compare both options under the same traffic distribution and token reuse pattern.

## 13. Benchmarking Properly

### 13.1. Measure Each Component First

Benchmarks can be split into:

1. JWT parsing + signature verification.
2. JWT validators + authority conversion.
3. Introspection HTTP client against a mock AS with fixed latency.
4. Introspection against a real test AS.
5. Cache hit lookup.
6. Cache miss + remote introspection.
7. End-to-end request through the SecurityFilterChain.

Microbenchmarks of cryptography are useful for understanding CPU, but do not replace end-to-end load tests.

### 13.2. Keep Comparison Conditions Fair

Hold CPU/memory/JVM flags, Spring Security/JWT library versions, request mix, authorization rules, representative token size/claims, TLS, connection pool, JVM warm-up, and concurrency constant. Isolate database/downstream effects or measure them separately.

Never compare local JWT in a warm JVM against cold-connection introspection on every call and draw architectural conclusions from that.

### 13.3. Measure p50, p95, p99, and Throughput

Collect request throughput, end-to-end latency p50/p95/p99, authentication latency, CPU utilization and CPU time/request, allocation/GC, JWKS fetch count/latency, introspection QPS/latency, cache hit ratio, timeout/retry/error rate, and AS CPU/queue depth/connection saturation.

Average latency can hide tail latency when the AS or network spikes.

### 13.4. Test Cold Start, Rotation, and Outages

Beyond steady state, run scenarios for: Resource Server starting up with an empty JWKS cache; slow or 503 JWKS endpoint; JWT carrying a new kid after rotation; empty introspection cache after deploy; increased AS latency; AS outage and recovery; unavailable cache backend; high token churn; bursts of concurrent requests with the same token; and many distinct tokens causing cache eviction.

These scenarios typically determine whether the system withstands incidents.

## 14. Testing Performance and Behavior with Spring Security

### 14.1. JWT Integration Tests

Use a real Nimbus decoder with a test key/JWKS endpoint. Verify that properly signed tokens are accepted, invalid signatures are rejected, issuer/audience/expiry validators work, JWKS fetching follows cache/refresh behavior, rotation with a new kid works, and outage behavior works for both cached keys and cache misses.

Do not use the `jwt()` MockMvc postprocessor to benchmark JWT verification; that postprocessor installs a mock authentication and skips signature verification.

### 14.2. Introspection Integration Tests

Use WireMock/MockWebServer or a test Authorization Server. Verify POST requests hit the right endpoint, client authentication is correct, the token is sent according to protocol rather than in the URL, active=true builds the expected principal, active=false is rejected, timeouts/5xx never become authenticated, cache hits do not call the AS, cache expiry triggers a new call, and revocation after cache fill becomes visible within the TTL/invalidation policy window.

### 14.3. Test Cache TTL with a Clock/Test Cache

Do not use long `Thread.sleep` calls to wait for TTLs. Use a cache provider that supports a controllable ticker/clock or a test abstraction that can advance time. Verify that the remaining time until token expiry is applied to the cache TTL.

### 14.4. Test That Credentials Are Never Logged

Use log capture or test instrumentation to confirm raw access tokens never appear in logs, metric labels, exception messages, or cache diagnostics. Introspection request bodies contain the token and must be protected from HTTP wire logging.

## 15. Metrics and Observability

### 15.1. Local JWT Verification Metrics

| Metric | Meaning |
|---|---|
| jwt.validation.success | Valid JWT token |
| jwt.validation.failure | Rejected JWT token |
| jwt.signature.validation.time | Time spent verifying signature |
| jwt.claim.validation.time | Time spent in validators |
| jwt.authority.conversion.time | Time spent mapping authorities |
| jwks.fetch.count | Number of JWKS fetches |
| jwks.fetch.latency | Latency to fetch key set |
| jwks.fetch.failure | JWKS fetch errors |
| jwks.cache.hit / miss | Cache behavior |
| jwt.unknown_kid | Token using an unknown kid |

Not all of these metrics are emitted out of the box by Spring Security. You may need to instrument the decoder, JWK source, or HTTP client.

### 15.2. Introspection Metrics

| Metric | Meaning |
|---|---|
| introspection.request.count | Number of requests to AS |
| introspection.request.latency | Round-trip time |
| introspection.request.failure | Timeouts, network, or HTTP errors |
| introspection.active | Active responses |
| introspection.inactive | Inactive responses |
| introspection.cache.hit | Cache hits |
| introspection.cache.miss | Cache misses |
| introspection.cache.eviction | Evicted entries |
| introspection.inflight | Concurrent in-flight calls |
| introspection.retry.count | Number of retries |

### 15.3. Avoid High-Cardinality and Secret Labels

Never use raw tokens, token hashes, sub, email, session ID, or jti as metric labels. Even a token fingerprint can be a sensitive identifier and create high cardinality. Use bounded labels such as issuer alias, outcome, resource server name, and error category.

Logs must not contain Authorization headers, introspection request bodies, client secrets, or full claims. Correlation IDs and standardized reason codes may be logged.

## 16. Choosing by Workload

### 16.1. High API Traffic, Short Token Lifetimes, Acceptable Revocation Window

Local JWT validation is usually a good fit when request rates are high, the Resource Server needs low latency, issuer/JWKS availability is strong, tokens have clear audience/scope, access token lifetimes are short, and the system accepts TTL-bounded revocation delay or has supplemental mechanisms.

Cryptographic verification cost is distributed across Resource Server instances rather than centralized on the AS.

### 16.2. Centralized State Control Required

Introspection fits when tokens are opaque, token revocation/state must be checked frequently, metadata lives on the AS, rapid state changes are required, and the AS has sufficient capacity and availability.

If cached for too long, the benefit of fresh state diminishes. Without caching, the AS must absorb QPS and latency for every request.

### 16.3. Hybrid Models

You can use local JWTs for most API read traffic, introspection for sensitive endpoints needing near real-time state, short access token lifetimes, very short introspection caches for workloads with high token reuse, or service identity/token exchange for outbound calls.

Hybrid models increase complexity. Clearly define which endpoints or token classes use which decoder or introspector, and never accidentally fall back between the two mechanisms when one fails.

## 17. Common Pitfalls

1. **Assuming JWT verification is free because public keys are cached:** signatures and claims are still checked on every request.
2. **Assuming the Resource Server calls JWKS on every request:** the JWK set is typically cached; fetches follow lifecycle/refresh behavior.
3. **Assuming introspection is always slow:** results depend on network, AS, connection pooling, and cache hit ratio.
4. **Skipping introspection caching despite high token reuse:** the AS can be loaded with the entire API QPS.
5. **Caching active results for too long:** revocation is delayed beyond policy.
6. **Caching timeout errors as inactive:** a dependency outage turns into prolonged invalid-token rejections.
7. **Caching inactive results indefinitely:** valid tokens may continue to be rejected after recovery or state changes.
8. **Not bounding cache size:** random tokens can exhaust memory.
9. **Using raw tokens as cache keys or in logs:** increases credential exposure risk.
10. **Omitting single-flight:** concurrent cache misses trigger an introspection stampede.
11. **Unbounded retries:** worsens an AS outage.
12. **Failing open when the AS is unavailable:** requests are accepted without trustworthy token state.
13. **Benchmarking only average latency:** hides p95/p99 and cache-miss tail latency.
14. **Benchmarking JWTs with the jwt() test postprocessor:** does not measure signature verification.
15. **Measuring only Resource Server CPU:** ignores AS CPU/network and total cluster cost.
16. **Using an introspection cache without factoring in the revocation SLA:** performance optimization violates security requirements.

## 18. Design and Operations Checklist

| Item | Question to Answer |
|---|---|
| Token model | JWT or opaque? Does the JWT also need introspection? |
| Verification path | Local decoder or remote introspector? |
| JWT crypto | Are algorithms/key sizes allowlisted and benchmarked? |
| JWKS | What are the TTL, refresh, unknown-kid, and outage behaviors? |
| Issuer/audience | Are validators fully configured? |
| Introspection | Are the endpoint, client authentication, and TLS protected? |
| Connection pool | Are connections reused and concurrency bounded? |
| Timeout | Are connect/read/overall deadlines finite? |
| Retry | Are retry budget and backoff bounded? |
| Cache | What are the TTL, size, key fingerprint, and namespace? |
| Revocation | Does the cache TTL fit within the revocation SLA? |
| Cache outage | How does policy fail when the cache is unavailable? |
| Stampede | Do concurrent misses use single-flight? |
| Capacity | Are AS QPS and Resource Server CPU calculated cluster-wide? |
| Benchmark | Are p50/p95/p99, throughput, CPU, GC, and network measured? |
| Failure tests | Are timeouts, 5xx, JWKS outages, and rotation tested? |
| Observability | Are cache hit/miss, fetch latency, AS saturation, and error categories tracked? |
| Logging | Are tokens, secrets, and introspection bodies excluded from logs? |
| Fallback | Are tokens never accepted when they cannot be verified? |

## 19. References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response and token active state.
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750): Bearer token transmission and error semantics.
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519): JWT claims and token structure.
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517): JWK/JWKS format.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): JWT validation and algorithm/key security.
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068): access token profile and validation.
- [Spring Security — JWT Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): JWT decoder, issuer, JWKS, and validators.
- [Spring Security — Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html): introspection and opaque token authentication.
- [Spring Security — OAuth2 Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/index.html): Servlet Resource Server configuration.
- [Nimbus JOSE + JWT](https://connect2id.com/products/nimbus-jose-jwt): JWT, JWK/JWKS, and remote key source.

**Conclusion:** Local JWT verification shifts most authentication cost onto each Resource Server's CPU and only requires JWKS fetches/refreshes per the key lifecycle; introspection shifts part of the cost onto the network and Authorization Server, especially when uncached. Introspection caching reduces QPS and latency but introduces revocation delay that must stay within the security SLA. Benchmark end-to-end under realistic workloads, measuring p95/p99, CPU, AS QPS, cache hit ratio, and outage behavior; then choose the verification path that fits your revocation, availability, latency, and total system cost requirements.
