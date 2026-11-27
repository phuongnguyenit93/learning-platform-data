# Load Spikes from Unknown `kid`s, Multiple Issuers, or Random Tokens

A Spring Security OAuth 2.0 Resource Server can experience heavy load spikes even when most requests are ultimately rejected. The cause usually lies in token-verification steps that reach external services or allocate cache entries:

- **JWTs with an unknown `kid`:** the decoder cannot find the matching public key in the cached JWK Set and may have to re-fetch JWKS to look for a new key.
- **Multiple issuers:** each issuer has its own metadata, decoder, JWK Set cache, connections, and policy. If issuers are discovered dynamically, tokens from unknown issuers can trigger lookups or create new managers.
- **Random tokens:** structurally valid JWTs containing random `kid`s can drive up JWKS refresh counts; random opaque tokens can drive up introspection calls.

These requests often come from misconfigured clients, unsynchronized key rotations, API scanners, or denial-of-service attacks. They can also appear during normal rollouts when many instances simultaneously receive tokens signed with a new key.

> **Operational principle:** constrain trusted issuer sources, control the cost of key refreshes and introspection, prevent cache stampedes, set concurrency/timeout limits, and stay fail-closed when tokens cannot be verified. Do not inadvertently block valid new keys during a legitimate rotation.

This lesson belongs to the **Performance and Operations** section. It focuses on a Servlet-based Spring Security Resource Server using JWT/JWKS, opaque tokens/introspection, and multi-issuer setups. Several caching, rate-limiting, and observability concepts apply to WebFlux as well, though the reactive APIs differ from Servlet APIs.

## 1. Why Can Rejected Tokens Still Generate Heavy Load?

A bearer request passes through several steps before the server decides whether the token is valid:

~~~text
HTTP request
    |
    v
BearerTokenResolver
    |
    v
Parse token / read unverified header claims
    |
    v
Select AuthenticationManager / issuer
    |
    +----------------------------+
    |                            |
    v                            v
JWT Resource Server          Opaque Resource Server
    |                            |
    v                            v
JwtDecoder                  Token Introspection
    |                            |
    v                            v
Select key by kid           Call Authorization Server
    |                            |
    v                            v
JWKS cache / refresh        active + token attributes
    |                            |
    +-------------+--------------+
                  |
                  v
        Validate issuer/audience/time
                  |
                  v
        Authentication / Authorization
~~~

A request can be rejected at multiple points:

- Header lacks a bearer token: no JWKS fetch or introspection needed.
- Token fails to parse: usually rejected before key lookup.
- JWT parses but `kid` misses the key cache: may trigger a JWKS refresh.
- Issuer is not on the allowlist: must be rejected before performing unauthorized discovery or lookup.
- Opaque token: the Resource Server usually has to call introspection if no valid cache entry exists.
- Token authenticates successfully but lacks scope: rejected at authorization, after authentication cost has already been paid.

Therefore, **a high 401 rate alone does not prove the system is safe from malicious load**. You must also monitor JWKS fetches, introspection requests, cache misses, unknown issuers, latency, and concurrency.

## 2. Three Load Patterns to Distinguish

### 2.1. JWTs with a New or Unknown `kid`

A JWT header might contain:

~~~json
{
  "alg": "RS256",
  "kid": "signing-key-2026-b",
  "typ": "at+jwt"
}
~~~

The Resource Server uses `kid` to select a public key from the configured issuer's JWKS. When the key is absent from the JWK Set cache, the decoder/JWK source may refresh JWKS to locate a newly published key.

This behavior is necessary for key rotation. However, a client could send many distinct JWTs, each carrying a random `kid`:

~~~text
kid=random-001 -> key missing -> refresh may occur
kid=random-002 -> key missing -> refresh may occur
kid=random-003 -> key missing -> refresh may occur
...
~~~

Possible consequences:

- Many HTTP requests to the JWKS endpoint.
- Increased TLS handshakes, DNS lookups, or connection pool usage.
- Higher CPU and memory load on the Authorization Server, CDN, or proxy.
- Cache stampedes when many requests refresh concurrently.
- Higher latency for legitimate requests occurring at the same time.
- Collateral impact on other systems sharing the JWKS endpoint.

Exact refresh behavior depends on the Spring Security version, Nimbus JOSE + JWT, JWK Set cache, and HTTP caching. Neither assume every unknown `kid` triggers a separate fetch, nor assume your current cache blocks every refresh storm. Measure on your exact dependency versions and deployment configuration.

### 2.2. Multiple Issuers

A Resource Server may accept tokens from multiple Authorization Servers, such as tenants or federated systems:

~~~text
Issuer A -> metadata A -> JWKS A -> decoder A
Issuer B -> metadata B -> JWKS B -> decoder B
Issuer C -> metadata C -> JWKS C -> decoder C
~~~

Each issuer may require:

- Dedicated discovery metadata.
- Dedicated JWKS URI and cache.
- Dedicated signing keys and algorithms.
- Dedicated audience and token validators.
- Dedicated connection pools, timeouts, and metrics.
- Dedicated trust policies and lifecycles.

If the system accepts arbitrary issuers from tokens and runs automatic discovery, an attacker can send many distinct `iss` values. An unsafe resolver could spawn unbounded outbound requests, managers, or cache entries.

### 2.3. Random Tokens

"Random tokens" are not a single scenario. Classify them:

| Input Pattern | Potential Cost Incurred |
|---|---|
| No token present | Bearer authentication challenge; usually no JWKS/introspection |
| Non-Bearer header | Ignored by bearer resolver |
| Malformed Bearer grammar | Rejected early by resolver |
| Malformed compact JWT format | Rejected by parser before signature verification |
| Validly structured JWT, random `kid` | May trigger key lookup/refresh |
| Validly structured JWT, unknown issuer | May trigger issuer resolution if configured dynamically |
| JWT with valid key but invalid signature | Fetches public key if uncached, then verification fails |
| Random opaque token | May trigger introspection calls if unthrottled/uncached |
| Valid token missing scope | Authentication succeeds; authorization rejects |

A load test must send the exact input type you intend to measure. Sending `not-a-jwt` does not test unknown-`kid` cost because the parser may reject it before touching JWKS.

## 3. Distinguishing Malformed JWTs from Unknown `kid`s

This distinction is critical when investigating load spikes.

### 3.1. Malformed JWTs Are Usually Rejected Before Fetching JWKS

Example:

~~~http
Authorization: Bearer not-a-jwt
~~~

This string is not a structurally valid compact JWT. The decoder can reject it right at parsing, before needing a signing key.

### 3.2. Structurally Valid JWTs with Unknown `kid`s Travel Further

A compact JWT with syntactically valid header, payload, and signature segments might carry a header like:

~~~json
{
  "alg": "RS256",
  "kid": "attacker-generated-random-kid",
  "typ": "JWT"
}
~~~

The payload can hold fake claims and the signature can be garbage. The decoder may still have to look up a key by `kid` before concluding the signature is invalid. If the key is not in cache, the JWK source may refresh JWKS.

**An attacker does not need a valid private key to craft input that hits the key-selection path.** All they need is a token structured well enough for the decoder to reach key lookup.

### 3.3. `kid` Is Unverified Input

Do not trust `kid` just because it sits in the JWT header. Before the signature is verified:

- `kid` could be crafted by anyone.
- `alg` could be chosen by an attacker.
- `iss` in the payload is not yet a verified issuer.
- Headers like `jku`/`x5u` must not dictate where keys are fetched from.

The Resource Server must fetch keys only from the JWKS URI bound to a trusted configured issuer. Never fetch arbitrary URLs supplied inside a token.

### 3.4. Never Disable Signature Verification to Shed Load

A broken response is skipping the signature check, reading `iss`, `sub`, `scope`, or `kid`, and building a principal. That turns forged tokens into accepted credentials.

Optimize the verification path, caching, and network access; never bypass cryptographic validation.

## 4. Unknown `kid`s Can Cause JWKS Refresh Amplification

### 4.1. Key Selection Flow

~~~text
JWT header.kid
      |
      v
JwtDecoder / Nimbus JWK source
      |
      v
JWK Set cache
      |
      +-- Matching key present
      |       |
      |       v
      |   Verify signature
      |
      +-- No matching key
              |
              v
        May re-fetch JWKS
              |
              v
        Look up key again
              |
              +-- Found -> verify signature
              |
              +-- Missing -> reject token
~~~

Refreshing is required when the Authorization Server has just published a new key. Yet if every request carries a different `kid`, the server may repeatedly enter the refresh branch depending on JWK source behavior.

### 4.2. A Cache Hit Does Not Mean Every Unknown `kid` Is Cheap

JWKS caching avoids frequent key set downloads, yet there are two distinct lookup outcomes:

- **Cache hit with matching key:** the decoder retrieves the existing public key and verifies the signature.
- **Cache hit without matching key:** the decoder sees the key is absent from the JWK Set; the implementation may try refreshing to discover a new key.

That is why measuring overall cache hit rate alone can be misleading. Separate:

- Key found in cached JWKS.
- Unknown `kid`.
- JWKS refresh attempted.
- Refresh succeeded/failed.
- Key found after refresh.
- Unknown `kid` still missing after refresh.

If the library does not emit these granular metrics natively, instrument the HTTP client/JWK retrieval layer or test stubs to count requests.

### 4.3. Amplification Example

Suppose an API receives 1,000 requests/second. If 10% are JWTs with unknown `kid`s and each of those triggers a JWKS fetch, the JWKS endpoint could receive up to 100 requests/second from a single Resource Server.

This is a **hypothetical illustrative example**, not a benchmark or guarantee of Nimbus behavior. Real numbers depend on caching, concurrency, refresh policy, and library version.

With multiple replicas:

~~~text
API replica A ----+
API replica B ----+---- JWKS endpoint
API replica C ----+
API replica D ----+
~~~

Each replica may keep its own cache. A burst of new-`kid` or random-`kid` tokens can create cumulative load on the JWKS endpoint.

## 5. Cache Stampedes When Many Requests Hit an Unknown Key Together

A cache stampede occurs when many concurrent requests observe a cache miss and trigger the same reload operation simultaneously.

~~~text
Request 1 ----+
Request 2 ----+
Request 3 ----+---- cache miss ---- JWKS fetch
Request 4 ----+
Request 5 ----+
~~~

Without coalescing or single-flight coordination, many requests may download the exact same JWKS document concurrently.

Impact:

- A single key rotation event triggers a traffic spike.
- Network connection pools fill up.
- AS/CDN load surges.
- Request latency climbs.
- Client retries amplify the spike.
- Multiple replicas refreshing together multiply load by instance count.

### 5.1. Single-Flight Refresh

A helpful strategy is allowing only one refresh per issuer/JWKS URI at a time within a process:

~~~text
N requests see unknown kid
          |
          v
     Refresh coordinator
          |
          +-- First request starts JWKS fetch
          |
          +-- Remaining requests wait on that fetch
          |
          v
     All share the new result
~~~

Exact implementation details depend on the JWK source/cache library and version. Do not assume `NimbusJwtDecoder` provides a distributed single-flight coordinator out of the box for every deployment.

Across multiple replicas, in-memory single-flight only coalesces within each process. You may need shared caching or coordination at the HTTP client, gateway, proxy, or key-distribution layer.

### 5.2. Shared Caches and Cache Namespaces

A shared cache can cut how often each replica fetches JWKS, provided namespaces are isolated accurately:

~~~text
jwks:{issuer-A}:{jwks-uri-A}
jwks:{issuer-B}:{jwks-uri-B}
~~~

Never use `kid` alone as the cache key. Two issuers can use the same `kid` for different public keys.

Bind cache entries to the trusted issuer/JWKS URI. When switching issuers or endpoints, never reuse stale entries simply because a key ID matches.

### 5.3. Jitter and Refresh Coordination

If all replicas boot together or share identical TTLs, they may refresh in lockstep. TTL jitter or pre-warming spreads load over time.

Example operational strategies:

- Roll out replicas using rolling deployments.
- Pre-warm JWKS caches after configuring issuers.
- Avoid identical TTLs across all caches when controllable.
- Use connection pooling and bound concurrent outbound fetches.
- Coalesce refreshes per issuer.
- Avoid synchronized retry storms when the JWKS endpoint recovers.

Do not tune TTLs arbitrarily: balance freshness, key rotation SLAs, and outage tolerance.

## 6. Unknown `kid`s and Negative Caching

One option to consider is **negative caching**: briefly remembering that a specific `kid` was absent in the recently fetched JWKS.

Example:

~~~text
issuer-A + kid=random-123
    |
    v
JWKS refresh
    |
    v
Key not found
    |
    v
Short-lived negative cache entry
    |
    v
Repeated requests with same kid -> fast reject
~~~

### 6.1. Benefits

- Cuts repeated identical lookups and refreshes.
- Helps when a bot resends the same token or `kid`.
- Reduces JWKS endpoint load during certain retry loops.

### 6.2. Risks

If an attacker generates a fresh `kid` on every request, the negative cache can fill with useless entries.

If the cache is unbounded, the negative cache itself becomes a memory-exhaustion DoS vector.

If the TTL is too long, a legitimate key newly published by the AS may be treated as unknown until the negative entry expires.

### 6.3. Rules If Implemented Customly

- Bound the cache size.
- Use a short TTL.
- Namespace by issuer/JWKS URI.
- Never store raw access tokens.
- Configure an eviction policy.
- Rate-limit new unknown `kid` entries per time window.
- Clear/invalidate negative entries when a JWKS refresh succeeds and new keys appear.
- Measure negative cache hit and eviction rates.

Negative caching is an optimization that must be designed and tested for your version and stack; do not assume it is enabled by default in every Spring Security/Nimbus setup.

## 7. JWKS Caching in Spring Security

Spring Security Servlet Resource Server uses `NimbusJwtDecoder` for JWTs. The decoder fetches the JWK Set from the configured URI and caches it to avoid downloading public keys on every request.

In current versions documenting builder cache support, you can pass a Spring `Cache` into the decoder:

~~~java
@Bean
JwtDecoder jwtDecoder(
        CacheManager cacheManager,
        @Value("${app.security.issuer}") String issuer,
        @Value("${app.security.jwk-set-uri}") String jwkSetUri) {

    NimbusJwtDecoder decoder = NimbusJwtDecoder
        .withJwkSetUri(jwkSetUri)
        .cache(cacheManager.getCache("orders-jwks"))
        .build();

    decoder.setJwtValidator(
        JwtValidators.createDefaultWithIssuer(issuer)
    );

    return decoder;
}
~~~

This is a Servlet example. Retain required validators such as issuer, timestamp, audience, and your API's token profile. When defining a custom `JwtDecoder`, do not accidentally drop validations that Boot auto-configuration previously wired.

### 7.1. Default Cache vs. Custom Cache

Current Spring Security versions describe `NimbusJwtDecoder` using a default in-memory cache with a short TTL (current Servlet docs mention roughly 5 minutes). Exact TTLs and APIs can vary by version.

A custom cache helps when:

- Multiple replicas want to share a JWK Set.
- You want centralized TTL management.
- You need hit/miss/eviction metrics.
- You want to tailor the cache backend to your infrastructure.
- You need visibility into refreshes and outages.

However, a shared cache alone will not stop an unknown-`kid` flood if every distinct request still triggers a refresh. Inspect the JWK source's actual behavior and enforce appropriate refresh limits.

### 7.2. Never Cache Authentication by `kid`

`kid` identifies a key, not a token's identity. One key can sign millions of tokens with different scopes, subjects, and audiences.

Never use:

~~~text
cache["orders-signing-key-1"] = authenticated=true
~~~

to decide whether a token is valid. Every JWT must still have its signature and claims verified individually.

### 7.3. Cache Keys Must Include Issuer Context

In a multi-issuer system:

~~~text
issuer A / kid=key-1 -> public key A
issuer B / kid=key-1 -> public key B
~~~

If the cache uses `kid=key-1` alone, issuer A's key could be mistakenly used for issuer B. Always bind caches to the configured issuer/JWKS URI and corresponding trust context.

## 8. Proper Key Rotation to Avoid Load Spikes

An unknown `kid` is not always an attack. It often occurs when the AS rotates signing keys.

### 8.1. Rotation with Overlap

A normal rotation workflow:

~~~text
T0: JWKS publishes only key-A
    AS signs tokens with key-A

T1: JWKS publishes key-A and key-B
    Resource Servers have time to pick up key-B

T2: AS starts signing new tokens with key-B
    New tokens carry kid=key-B

T3: Old tokens signed with key-A remain valid
    JWKS keeps key-A during overlap window

T4: Token-A expires + clock skew
    AS removes key-A per policy
~~~

If the AS starts signing with key-B before publishing key-B, Resource Servers can receive a wave of legitimate unknown `kid`s and refresh continuously.

### 8.2. Pre-Publishing and Warm-Up

To reduce spikes:

1. Publish the new key in JWKS first.
2. Wait long enough for caches/replicas to pick up the key.
3. Verify JWKS from each Resource Server's network path.
4. Only then begin signing tokens with the new key.
5. Keep the old key until old tokens expire plus clock skew and required overlap.
6. Monitor unknown `kid`s and refresh rates during rollout.

You can pre-warm decoders/caches during deployment or readiness checks, while controlling startup dependencies. Avoid having all replicas hit the AS simultaneously.

### 8.3. Emergency Key Compromise Response

If a private signing key is compromised, keeping the old key in JWKS just to prevent 401s may no longer be acceptable. Follow an emergency procedure:

- Stop signing with the compromised key.
- Remove/deny the key per AS policy.
- Refresh or invalidate JWKS caches on Resource Servers.
- Review token lifetimes, revocation, and deny-lists per AS capabilities.
- Identify instances still holding the old public key in cache.
- Monitor tokens signed with the old key.
- Coordinate across the AS and all APIs sharing that issuer.

A long cache TTL can allow the old public key to keep being used after the AS has removed it. This is the trade-off between availability and response speed during a compromise.

## 9. Multi-Issuer: Constrain Trust Before Creating Decoders

### 9.1. Never Discover from Arbitrary Issuers

A dangerous design:

~~~text
1. Parse JWT payload.
2. Read arbitrary iss.
3. Append well-known path to iss.
4. Call URL dictated by token.
5. Create new decoder/manager.
~~~

`iss` in an unverified token is untrusted input. An attacker can send:

- A fake issuer on a domain they control.
- An internal URL or loopback address.
- A cloud metadata service hostname.
- Thousands of distinct issuers.
- URLs that trigger redirects or DNS rebinding.

If the server performs outbound discovery based on this input, risks include SSRF, DNS/network scanning, cache exhaustion, and connection pool exhaustion.

### 9.2. Use a Trusted Issuer Allowlist

If your API accepts only a known set of issuers, declare them explicitly:

~~~java
@Bean
AuthenticationManagerResolver<HttpServletRequest>
trustedIssuerResolver() {

    return JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(
        "https://login-a.example.com/issuer",
        "https://login-b.example.com/issuer",
        "https://login-c.example.com/issuer"
    );
}
~~~

Attach the resolver to the Servlet Resource Server:

~~~java
@Bean
SecurityFilterChain apiSecurity(
        HttpSecurity http,
        AuthenticationManagerResolver<HttpServletRequest> trustedIssuerResolver)
        throws Exception {

    return http
        .authorizeHttpRequests(auth -> auth
            .anyRequest().authenticated()
        )
        .oauth2ResourceServer(oauth2 -> oauth2
            .authenticationManagerResolver(trustedIssuerResolver)
        )
        .build();
}
~~~

Primary imports include:

~~~java
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.security.authentication.AuthenticationManagerResolver;
import org.springframework.security.oauth2.server.resource.authentication.JwtIssuerAuthenticationManagerResolver;
~~~

The allowlist limits which issuers the resolver can trust. Each issuer still needs proper audience, signature, timestamp, algorithm, and token profile validation.

### 9.3. Never Use Unverified `iss` for Tenant Authorization

The resolver may inspect the unverified issuer claim to choose a manager. That is purely routing to a pre-configured trusted manager; **it is not successful issuer authentication**.

Once a manager is selected, its JWT decoder must still verify the signature and the exact `iss` claim for that issuer.

Never use unverified `iss` to:

- Grant tenant permissions.
- Select arbitrary tenant databases.
- Provision accounts or user records.
- Accept an audience.
- Call arbitrary endpoints.

### 9.4. Dynamic Issuer Registries Must Be Bounded

Some multi-tenant systems need dynamic issuer onboarding. In that case:

- Issuers must be pre-registered and approved.
- The registry stores canonical issuers and verified metadata/JWKS URLs.
- Cap the number of active issuers.
- Manager/decoder caches must have explicit eviction or lifecycles.
- Never instantiate a new manager for every unknown token.
- Never auto-trust an issuer just because a tenant submits a URL.
- Have a process to disable issuers and invalidate caches.
- Isolate credentials and network policies per issuer when needed.

If an issuer registry allows unbounded tenant registrations, manager, decoder, cache, and connection costs can scale with tenant count.

## 10. Multi-Issuer Cache and Connection Management

For each issuer, the Resource Server may need:

- Metadata cache.
- JWK Set cache.
- `JwtDecoder`/`AuthenticationManager`.
- HTTP client connection pool.
- Metrics and failure state.
- Audience/token validators.

For example, 100 issuers can create 100 independent trust contexts. Not all have to be active concurrently, yet cache and connection footprints must be measured.

### 10.1. Never Share JWK Caches Across Issuers

Cache namespaces should include the issuer or JWKS URI:

~~~text
jwks:{canonical-issuer}:{jwks-uri}
~~~

Never key caches solely by `kid` or algorithm.

### 10.2. Bound the Issuer Manager Cache

If a resolver creates managers for dynamic issuers, address:

- Maximum number of managers.
- Idle eviction.
- TTL aligned with tenant lifecycle.
- Single-flight manager creation.
- Duplicate discovery suppression.
- Connection/cache cleanup when an issuer is disabled.
- Metrics for manager count and cache size.

Never create a new `JwtDecoder` per request. Decoders and managers should be reused per registered issuer.

### 10.3. Separate Timeouts and Concurrency by Dependency

One slow issuer should not starve outbound resources used by other issuers. Split connection pools or concurrency budgets by dependency or issuer group when traffic warrants it.

Keep total outbound requests bounded. Retries require limits, backoff, and jitter; never retry 401/403 or unknown-key failures unboundedly.

## 11. Random Opaque Tokens Can Cause an Introspection Flood

With opaque tokens, the Resource Server usually cannot verify tokens offline. It calls the introspection endpoint:

~~~text
Authorization: Bearer opaque-random-token
              |
              v
OpaqueTokenAuthenticationProvider
              |
              v
Reactive/Servlet OpaqueTokenIntrospector
              |
              v
POST /introspect
              |
              v
Authorization Server
              |
              v
active=false
~~~

If an API receives 5,000 random opaque tokens per second without caching or rate limiting, the AS could receive nearly 5,000 introspection calls/second from that API alone. This is an illustrative calculation: real load depends on caching, concurrency, retries, and introspector behavior.

### 11.1. Protecting the Introspection Endpoint

- Authenticate the Resource Server client using an AS-approved method.
- Grant only the introspection permissions needed by the API.
- Use TLS and verify server certificates.
- Set short connect/read timeouts aligned with SLOs.
- Cap concurrent requests.
- Use a bounded connection pool.
- Enforce rate limits per client/resource server at the gateway or AS.
- Monitor latency, client auth 401/403s, 5xx responses, and timeouts.
- Never fail open when the introspection endpoint errors.

### 11.2. Caching Active and Inactive Responses

Introspection responses can be cached, though TTLs directly impact revocation freshness.

- Caching `active=true`: reduces AS load, but revoked tokens may continue being accepted until the cache expires.
- Caching `active=false`: reduces load when the same invalid token is sent repeatedly, though a long TTL can delay accepting newly issued or state-changed tokens.
- Never cache network errors as inactive or active; those are dependency failures, not token state.
- Derive cache keys safely from the token and bind them to the introspection endpoint and resource context.
- Bound size and TTL to prevent memory exhaustion.

Negative caching helps most when the same invalid token is replayed repeatedly. When every request sends a brand-new random token, rate limits and concurrency limits matter more.

### 11.3. Opaque Tokens Do Not Have a `kid`

Opaque tokens do not use `kid` for JWK selection, yet they can create comparable load at the introspection layer. Do not apply unknown-`kid` mitigations to opaque tokens; instrument the introspection path separately.

## 12. Rate Limiting: Stop Excess Load Before It Reaches the AS/JWKS

Rate limiting should be enforced at one or more layers:

1. CDN/WAF/API gateway.
2. Ingress/load balancer.
3. Application filter prior to network-bound authentication steps.
4. JWK/introspection outbound client.
5. Authorization Server endpoint.

### 12.1. Rate Limiting Before Authentication

Unauthenticated requests lack a trusted user ID for per-principal rate limiting. You can use:

- Source IP or network identity supplied by a trusted proxy.
- Connection/client certificate if verified at the TLS layer.
- Route/API key or integrity-protected gateway client metadata.
- Global budget for anonymous traffic.
- Per-tenant/client budget once a trusted identity is established.

Watch out for NAT IPs: many legitimate users may share a single IP. Overly strict per-IP limits can block real traffic.

### 12.2. Separate Budgets by Cost Type

Do not rely on a single global request rate. You may need separate budgets:

| Budget | Target |
|---|---|
| Inbound request rate | Caps total API requests |
| Invalid bearer rate | Dampens token floods |
| Unknown issuer rate | Dampens discovery/manager lookups |
| Unknown `kid` refresh rate | Protects the JWKS endpoint |
| JWKS outbound concurrency | Limits concurrent key fetches |
| Introspection concurrency | Protects the AS token endpoint |
| Per-issuer connection budget | Prevents one issuer from consuming the whole pool |

When a single request can trigger multiple outbound calls, rate limiting at the outermost layer is most effective.

### 12.3. Rate Limiting Does Not Replace Token Validation

A request allowed past a rate limiter must still pass:

- Signature verification.
- Issuer/audience/time validators.
- Token profile validation.
- Scope/authority authorization.
- Tenant and object-level authorization.

Never let a request through simply because it is under the rate limit.

### 12.4. Response When Rate Limited

The gateway may return:

~~~http
HTTP/1.1 429 Too Many Requests
Retry-After: 10
~~~

This is a rate-limiting policy response, distinct from `401 invalid_token`. Clients should understand `429` means exceeding the request budget, not necessarily a bad token.

Do not return `WWW-Authenticate: Bearer error="invalid_token"` for requests that were merely rate-limited if the token was never verified.

## 13. Timeouts, Retries, and Circuit Breakers for JWKS/Introspection

### 13.1. Timeouts

Configure timeouts for:

- DNS/connect.
- TLS handshake.
- Response/read.
- Total dependency call duration.
- Pool acquisition.
- Retry budget.

Timeouts must fit within the API's latency budget. A 30-second timeout makes little sense if the API has a 200 ms SLO.

### 13.2. Bounded Retries

Retry only appropriate transient errors:

- Connection reset.
- Temporary network failure.
- HTTP 502/503/504 if policy permits.

Never retry unboundedly on:

- Unknown `kid` after JWKS was already refreshed and the key is still missing.
- Invalid signature.
- Issuer/audience mismatch.
- Introspection client 401/403.
- Inactive token.

Use backoff, jitter, and an overall deadline. Simultaneous retries across all replicas can cause a retry storm.

### 13.3. Circuit Breakers

A circuit breaker stops the application from piling load onto a failing JWKS or introspection endpoint.

~~~text
CLOSED
  |
  | failures exceed threshold
  v
OPEN
  |
  | pause outbound calls
  v
HALF-OPEN
  |
  +-- dependency recovers -> CLOSED
  |
  +-- still failing -------> OPEN
~~~

When the circuit is open:

- Tokens whose valid keys are cached can still be verified per policy.
- Tokens requiring a new key that cannot be fetched must be rejected.
- Opaque tokens without a valid cached introspection result cannot be confirmed.
- Never build a default principal or treat a dependency timeout as `active=true`.

Distinguish authentication failures from dependency outages in monitoring and error handling. Depending on your architecture, dependency errors may return 503 rather than assuming an invalid token; never alter the fail-closed decision.

## 14. Prevent Unknown Issuers from Becoming SSRF

The issuer in a JWT payload is unverified. If the application builds metadata URLs from a request-supplied `iss` value, an attacker can steer outbound requests.

Example dangerous input:

~~~json
{
  "iss": "http://127.0.0.1:8080/admin"
}
~~~

Or an issuer pointing to an internal hostname or cloud metadata service.

Safeguards:

- Use a canonical issuer allowlist.
- Never fetch arbitrary metadata/JWKS URIs from untrusted tokens.
- Never trust `jku` or `x5u` in JWT headers to fetch signing keys.
- Block loopback, link-local, private networks, and out-of-policy redirects at the egress layer.
- Do not let tenants register issuer URLs without an approval workflow.
- Enforce DNS/network egress policies as defense-in-depth.
- Verify exact issuer equality after the decoder verifies the signature.
- Cap cache/manager counts if the issuer registry is dynamic.

Application-level allowlists and network-level egress controls complement each other.

## 15. Observing Load: Which Metrics Pinpoint the Cause?

Do not look solely at CPU or 401 counts. Track:

### 15.1. JWT/JWKS

| Metric/event | Meaning |
|---|---|
| `jwt_requests_total` | Total JWT authentication attempts |
| `jwt_parse_failures_total` | Tokens malformed before verification |
| `jwt_unknown_kid_total` | Tokens with missing key IDs |
| `jwks_fetch_total` | Number of JWKS fetches |
| `jwks_fetch_duration` | Latency to fetch key sets |
| `jwks_fetch_failures_total` | HTTP/DNS/TLS/timeout failures |
| `jwks_cache_hits_total` | Cache served the key |
| `jwks_cache_misses_total` | Needed key lookup/refresh |
| `jwks_refresh_after_unknown_kid_total` | Refresh triggered by missing key |
| `jwt_signature_failures_total` | Key found but signature invalid |
| `jwt_issuer_rejected_total` | Rejected issuer |
| `jwt_audience_rejected_total` | Invalid audience |

Metric names are instrumentation suggestions; do not assume Spring Security emits all of these out of the box.

### 15.2. Multi-Issuer

- Unknown issuer count.
- Issuer manager creation count.
- Active decoder/manager count.
- Metadata fetch rate.
- Per-issuer JWKS fetch rate.
- Cache size/evictions.
- Per-issuer authentication latency.
- Issuer disabled/rejected events.

### 15.3. Opaque/Introspection

- Introspection requests per second.
- Active/inactive response counts.
- Introspection p50/p95/p99 latency.
- Timeout/5xx rate.
- Client authentication 401/403s.
- Cache hits/misses.
- Concurrent introspection calls.
- Response parsing failures.

### 15.4. Avoid High Metric Cardinality

Never use unbounded attacker-controlled values as metric labels:

- Raw token.
- Arbitrary `kid` from attacker.
- Arbitrary `iss`.
- Username/email/subject.
- Arbitrary URL supplied by request.

Instead:

- Use issuer IDs from an approved registry.
- Group errors by category.
- Log truncated/hashed `kid`s when investigating.
- Sample logs for unknown values.
- Use counters/histograms free of attacker-controlled labels.

If every random `kid` becomes a metric label, the metrics backend can suffer cardinality exhaustion DoS.

## 16. Testing Unknown `kid` and Cache Behavior

Tests must construct structurally valid JWTs carrying a `kid` absent from JWKS. A malformed string is insufficient to test refresh behavior.

### 16.1. JWKS Stub with Request Counter

Use a mock HTTP server to serve the JWK Set and count GET requests:

~~~text
Test JWKS server
  GET /jwks
    -> counter++
    -> return current JWK Set
~~~

Test cases:

1. Token signed with a key present in JWKS.
2. Multiple distinct tokens sharing the same valid `kid`.
3. Token carrying a nonexistent `kid`.
4. Multiple tokens with distinct random `kid`s.
5. Many concurrent requests with the same unknown `kid`.
6. Adding a new key to JWKS.
7. Token signed with the new key.
8. Removing the old key after overlap and testing the old token.
9. JWKS endpoint returning timeouts or 503s.
10. Verify zero requests go to URLs supplied in token `jku`/`x5u` headers.

Measure JWKS fetch counts and latency for each case. Outcomes depend on your Nimbus/Spring Security version; these tests reveal the exact behavior of your pinned dependencies.

### 16.2. Testing Cache Stampedes

~~~text
1. Clear JWKS cache.
2. Prepare a token with an unknown kid.
3. Send N concurrent requests.
4. Count JWKS fetches.
5. Measure p95/p99 request latency.
6. Repeat across multiple application instances.
~~~

Compare:

- Single instance, in-memory cache.
- Single instance, refresh coordination.
- Multiple instances with separate caches.
- Multiple instances with shared cache/coalescing if supported.

Do not check only the 401 HTTP response; the goal of the test is measuring outbound amplification.

### 16.3. Testing Legitimate Key Rotation

- Initial JWKS contains key A.
- Publish key B alongside A.
- Wait for cache propagation per policy.
- Issue tokens signed with B.
- Verify valid requests do not cause sustained refresh spikes.
- Keep token A during overlap and verify it still works.
- Retire A after token A expires per policy.

## 17. Testing Multi-Issuer and Unknown Issuers

Test matrix:

| Token | Expected Outcome |
|---|---|
| Allowlisted Issuer A, valid signature/audience | Authenticated |
| Allowlisted Issuer B, valid signature/audience | Authenticated by decoder B |
| Non-allowlisted issuer | Rejected; no discovery of arbitrary URL |
| Fake issuer pointing to loopback/private IP | Rejected; zero outbound requests |
| Issuer A claim but key from Issuer B | Signature/issuer validation fails |
| Issuer A and B sharing same `kid` | Correct key selected per issuer namespace |
| Issuer A disabled | No new authentication manager created |
| Thousands of random issuers | Managers/caches do not grow unboundedly |
| Metadata endpoint A times out | Affects only trust path A per policy |
| JWKS A fails | Does not overwrite cache/manager B |

A key test uses an HTTP stub to count outbound requests. For an unknown issuer, expected discovery/JWKS calls should be **0** when the allowlist rejects it.

## 18. Testing Opaque Token Floods

For opaque tokens, use an introspection stub:

~~~text
POST /introspect
  count++
  token=random-token
  -> {"active": false}
~~~

Test:

- Same inactive token repeated.
- Many distinct random tokens.
- Rising introspection latency.
- Introspection endpoint timeouts/503s.
- Bad client authentication.
- Concurrency hitting its cap.
- Active/inactive cache across TTL boundaries.
- Newly revoked token while positive cache is still valid.
- Malformed responses.
- One resource server never reusing another resource server's cache.

Measure introspection requests per inbound request and peak concurrent calls. Confirm the system never fails open on dependency errors.

## 19. Runbook When Seeing JWKS or AS Load Spikes

When alerts fire for surging JWKS/introspection requests:

**Step 1 — Classify traffic.** Check inbound RPS, 401 rate, token parse failures, unknown `kid`s, unknown issuers, and opaque token rates.

**Step 2 — Check key rotation.** Confirm whether the AS recently published a new key, changed `kid`s, or switched signing keys.

**Step 3 — Inspect JWKS.** Verify whether `kid`s in valid tokens appear in JWKS; check from each replica's network path.

**Step 4 — Inspect caches.** Check hits/misses, refresh counts, TTLs, evictions, and skew across replicas.

**Step 5 — Inspect issuers.** Look for tokens from non-allowlisted issuers or random `iss` values.

**Step 6 — Inspect introspection.** Check for opaque token floods, AS latency, client auth errors, and cache behavior.

**Step 7 — Cap outbound traffic.** Apply appropriate concurrency limits, timeouts, rate limits, and circuit breakers. Do not increase retries to cure an outage.

**Step 8 — Preserve validation.** Never disable signature, issuer, audience, or active checks to reduce load.

**Step 9 — Coordinate with the AS.** Confirm rotations, key compromises, endpoint health, and AS-side rate limiting.

**Step 10 — Verify recovery.** Watch JWKS fetch rates, introspection RPS, p95/p99, and valid token success rates after changes.

## 20. Illustrative Operational Configuration

A basic JWT configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://login.example.com/realms/orders
          jwk-set-uri: https://login.example.com/realms/orders/protocol/openid-connect/certs
          audiences:
            - orders-api
~~~

Values are illustrative. In real environments:

- Use environment-appropriate issuer/JWKS URIs.
- Retain issuer and audience validation.
- Set HTTP connect/read timeouts for JWKS retrieval per your version's API.
- Choose cache TTLs based on your key rotation SLA.
- Instrument fetches and caches.
- Restrict outbound network access to approved hosts.

For multiple issuers, use an allowlisted resolver rather than inferring trust from every `iss` appearing in tokens.

For opaque tokens, configure the introspection URI and dedicated Resource Server client credentials; add timeouts, connection pooling, rate limits, and caching aligned with revocation policy.

## 21. Balancing Performance, Availability, and Security

| Decision | Performance Gain | Risk to Control |
|---|---|---|
| Longer JWKS cache | Fewer fetches | Slower propagation of key rotation or compromise |
| Longer introspection cache | Fewer AS calls | Revoked tokens accepted until TTL expires |
| Negative cache for unknown `kid`s | Cuts repeated refreshes | Legitimate new keys briefly rejected; cache fill risk |
| Shared JWKS cache | Cuts fetches across replicas | Cache isolation/availability and issuer namespacing |
| Single-flight refresh | Prevents cache stampedes | Waiting requests share a slow refresh |
| Inbound rate limiting | Sheds backend load | Can block valid clients if keyed poorly |
| Circuit breaker | Protects dependencies during outages | Tokens needing new keys or uncached opaque tokens fail |
| Dynamic issuer registry | Flexible onboarding | Unbounded cache/manager growth and SSRF if uncontrolled |
| Pre-warming JWKS | Cuts cold-start latency | Startup can depend on AS if synchronous |

No single TTL or rate limit fits every system. Choose based on:

- Maximum access token lifetime.
- Key rotation interval and overlap.
- Revocation SLA.
- Number of issuers.
- Number of application replicas.
- Inbound RPS and invalid-token ratio.
- AS/JWKS capacity.
- API latency SLO.
- Network failure model.

## 22. Anti-Patterns to Avoid

**Refreshing JWKS unboundedly on every unknown `kid`.** Can trigger amplification; measure refresh behavior and cap outbound calls.

**Creating a decoder for every issuer sent in a token.** Risks SSRF, unbounded manager caches, and metadata floods.

**Using `kid` as a global cache key.** Identical `kid`s across two issuers do not mean the same public key.

**Using unverified `iss` as tenant identity.** An issuer is trusted only after verifying the token with an allowlisted manager.

**Disabling signature validation when JWKS is slow.** Turns forged tokens into accepted credentials.

**Caching `authenticated=true` by `kid`.** One key signs many tokens with different claims; each token must be verified.

**Caching introspection without a TTL.** Revoked tokens could be accepted indefinitely.

**Caching unknown `kid`s unboundedly.** Attackers can fill memory with random values.

**Retrying all errors unboundedly.** Triggers retry storms and worsens AS/JWKS outages.

**Using one unbounded connection pool for all issuers.** One slow issuer can starve resources for every issuer.

**Trusting `jku`/`x5u` from JWT headers.** Lets attackers control the public key source.

**Monitoring only CPU and 401s.** Misses JWKS refresh amplification and introspection floods.

**Using raw `kid`, issuer, or token as metric labels.** Cardinality can grow without bound.

**Returning `active=true` on introspection timeout.** Fails open and lets unverified tokens proceed.

**Dropping old keys immediately when introducing new ones.** Valid tokens signed with the old key will fail unexpectedly.

## 23. Self-Check Questions

**1.** Why can a JWT with a random `kid` increase JWKS load?

> If the token parses but the key is missing from the JWK Set cache, the JWK source may refresh JWKS to search for a new key before rejecting the token.

**2.** Can `not-a-jwt` test unknown-`kid` behavior?

> No. The parser may reject it before key selection; you need a structurally valid compact JWT carrying a nonexistent `kid`.

**3.** Is `kid` trustworthy data before signature verification?

> No. It comes from an unverified JWT header and is only used to pick a key from a trusted configured JWKS source.

**4.** Why should you not run discovery against arbitrary issuers from tokens?

> It can cause SSRF, DNS/network scanning, unbounded manager caches, and metadata request floods.

**5.** What does `JwtIssuerAuthenticationManagerResolver.fromTrustedIssuers(...)` provide?

> It restricts which issuers the Resource Server can select authentication managers for.

**6.** Can two issuers with the same `kid` share the same key?

> Possibly, but never assume so. Caches and key selection must be namespaced by issuer/JWKS source.

**7.** Does JWKS caching mean unknown `kid`s never trigger network requests?

> No. A cache hit lacking a matching key can trigger a refresh depending on the implementation and version.

**8.** What is a cache stampede?

> Many requests concurrently hitting a cache miss and executing the exact same refresh or data fetch simultaneously.

**9.** What does a single-flight refresh do?

> Coalesces multiple concurrent refreshes for the same issuer/JWKS source into a single operation within the coordinator's scope.

**10.** What are the risks of negative caching unknown `kid`s?

> The cache can be filled by random `kid`s or delay recognizing legitimate new keys if the TTL is too long.

**11.** Where do random opaque tokens generate load?

> At the introspection endpoint if the Resource Server calls the AS for every token without adequate caching or rate limiting.

**12.** Why does introspection cache TTL affect revocation?

> Cached active responses can continue being used after the AS revokes a token until the cache entry expires.

**13.** Should you fail open when the JWKS or introspection endpoint times out?

> No. If a token cannot be verified, an authenticated principal must not be created.

**14.** Why pre-publish new keys?

> So Resource Servers receive the public key before the AS starts signing tokens with it, reducing unknown-`kid` spikes.

**15.** Why keep old keys during an overlap window?

> Older tokens may still be valid; removing keys too early causes legitimate tokens to be rejected.

**16.** Where should unknown-issuer rate limiting be placed?

> At the ingress/gateway or resolver boundary before discovery or manager creation; only use allowlisted issuers as identity labels.

**17.** Why avoid placing random `kid`s in metric labels?

> Each unique value creates a new time series and can cause metrics cardinality exhaustion.

**18.** What test verifies unknown-`kid` refresh behavior?

> Send signed/compact JWTs with nonexistent `kid`s through the real decoder against a JWKS stub counting fetches, under both single requests and concurrent bursts.

## 24. References

- [Spring Security — Servlet OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): `JwtDecoder`, JWKS, caching, and key rotation.
- [Spring Security — Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html): trusted issuer resolvers and multiple authentication managers.
- [Spring Security — AuthenticationManagerResolver API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/AuthenticationManagerResolver.html): selecting an authentication manager per request.
- [Nimbus JOSE + JWT — RemoteJWKSet API](https://javadoc.io/doc/com.nimbusds/nimbus-jose-jwt/latest/com/nimbusds/jose/jwk/source/RemoteJWKSet.html): loading JWK Sets from remote sources and version-specific cache behavior.
- [RFC 7517 — JSON Web Key](https://www.rfc-editor.org/rfc/rfc7517): JWK, JWK Set, and `kid`.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519): JWT structure and registered claims.
- [RFC 8414 — OAuth 2.0 Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414): issuer metadata and `jwks_uri`.
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662): introspection request/response and `active`.
- [RFC 8725 — JSON Web Token Best Current Practices](https://www.rfc-editor.org/rfc/rfc8725): issuer/audience validation, algorithm verification, and avoiding JWT confusion.
- [Spring Framework — HTTP Clients](https://docs.spring.io/spring-framework/reference/integration/rest-clients.html): configuring HTTP clients, timeouts, and connection behavior.
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html): Reactor Context when building a reactive Resource Server.

**Conclusion:** Load spikes from unknown `kid`s, multiple issuers, or random tokens originate from distinct cost paths: JWKS refreshes, issuer discovery/manager creation, and introspection. Distinguish malformed tokens from JWTs with unknown `kid`s, constrain issuers with an allowlist, namespace caches by issuer, coalesce refreshes, enforce rate/concurrency/timeout limits, manage key rotations with overlap, and monitor outbound calls. When a signature or token state cannot be verified, the Resource Server must fail closed; performance optimizations must never weaken trust validation.
