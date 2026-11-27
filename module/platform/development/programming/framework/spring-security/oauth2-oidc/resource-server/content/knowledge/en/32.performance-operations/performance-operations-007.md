# Bounding Tenant Count, Decoder Count, and Cached Data

A multi-tenant Spring Security Resource Server may have to verify tokens for hundreds or thousands of tenants. Each tenant may have its own issuer, JWKS endpoint, audience, algorithms, introspection endpoint, client credentials, and permission policy. If the application creates a decoder/manager on every request, retains every tenant indefinitely, or caches introspection results without bounds, memory usage, network connections, and authentication overhead will grow with traffic and tenant count.

A multi-tenant design needs **a cap on onboarded tenants, a cap on authentication managers/decoders held in memory, and dedicated cache policies for each type of data**.

Three principles must hold:

1. Only governed, authorized tenants may create trust configurations.
2. Decoders/managers and caches must have explicit bounds, lifecycles, eviction, and invalidation.
3. Caching must never weaken issuer, audience, tenant isolation, revocation SLAs, or fail-closed behavior.

This lesson focuses on capacity management for a WebFlux Resource Server: tenant registries, `ReactiveAuthenticationManager`, `ReactiveJwtDecoder`, JWKS/key caches, introspection caches, revocation state, cache keys, TTLs, eviction, cold starts, cache stampedes, observability, and capacity testing.

## 1. Why Does Tenant Count Affect Performance?

With a simple single-tenant JWT setup, the application can use one decoder and one manager. With multiple tenants, each tenant can entail:

- One or more `ReactiveAuthenticationManager` instances.
- A `ReactiveJwtDecoder` or `ReactiveOpaqueTokenIntrospector`.
- A dedicated JWKS endpoint and public key cache.
- A dedicated HTTP client/connection pool or TLS configuration.
- Issuer, audience, algorithm, and validator configuration.
- Introspection client credentials.
- Tenant metadata and status caches.
- Metrics, circuit breakers, rate limiters, and health state.

If every tenant owns a separate set of components, cost scales with active tenants.

~~~mermaid
flowchart TD
    REG[Tenant registry] --> RES[ReactiveAuthenticationManagerResolver]
    RES --> MA[Manager tenant A]
    RES --> MB[Manager tenant B]
    RES --> MC[Manager tenant C]
    MA --> DA[Decoder / introspector A]
    MB --> DB[Decoder / introspector B]
    MC --> DC[Decoder / introspector C]
    DA --> KA[JWKS / token state cache A]
    DB --> KB[JWKS / token state cache B]
    DC --> KC[JWKS / token state cache C]
~~~

This is a logical model. Some tenants can share an issuer or infrastructure, but only share components when their trust contracts are genuinely identical.

### 1.1. Tenant Count, Issuer Count, and Decoder Count Are Not One and the Same

Examples:

| Configuration | Tenant Count | Issuer Count | Decoders Potentially Needed |
|---|---|---|---|
| Each tenant has its own issuer | 100 | 100 | Potentially close to 100 |
| Many tenants share one issuer and identical policy | 100 | 1 | Can share one decoder |
| Same issuer but different audiences/validators | 100 | 1 | May need multiple manager/decoder policies |
| One tenant uses both JWT and opaque tokens | 1 | May be 1 or more ASes | May have multiple managers |

Do not use tenant count as the sole proxy for decoder count. Count **distinct trust configurations**: issuer, JWKS/introspection endpoints, audience, algorithm policy, validator set, and client authentication.

### 1.2. Which Objects Consume Resources?

| Object | Primary Resource | Lifecycle to Manage |
|---|---|---|
| Tenant configuration | Memory, metadata | Onboard, update, disable, delete |
| `ReactiveAuthenticationManager` | Object graph, decoder/introspector references | Create, cache, evict |
| `ReactiveJwtDecoder` | Key source, HTTP client/config, validators | Create, cache, refresh keys |
| JWKS/public key set | Memory, network refreshes | TTL, rotation, invalidation |
| `ReactiveOpaqueTokenIntrospector` | HTTP connections, client credentials | Pooling, timeouts, secret rotation |
| Introspection result | Memory, sensitive token-derived data | TTL, revocation, eviction |
| Revocation/session cache | Memory, consistency | TTL, event updates, cleanup |
| Metrics/circuit breakers | Memory and cardinality | Label bounds, lifecycle |

A decoder does not necessarily open its own connection pool; that depends on the implementation and configured HTTP client. Even so, repeatedly creating decoders or HTTP clients duplicates caches, connection resources, and initialization work.

## 2. Enforce Tenant Limits Starting at Onboarding

Tenant limits should be enforced at the **tenant provisioning/configuration layer**, before a tenant can send traffic.

A tenant record should include the required fields:

~~~yaml
tenantId: tenant-a
status: ACTIVE
issuer: https://id-a.example.com
jwksUri: https://id-a.example.com/.well-known/jwks.json
audience:
  - orders-api-a
tokenStrategy: JWT
policyVersion: 4
~~~

This configuration is illustrative. Production systems may store records in a database or config service and manage secrets separately.

### 2.1. Never Auto-Create Tenants from Incoming Requests

Do not do this:

~~~text
Request sends X-Tenant-ID: tenant-new
  -> app auto-creates tenant config
  -> fetches issuer metadata from request-supplied URL
  -> builds decoder
  -> accepts token
~~~

A request must never be allowed to inflate tenant count, spawn managers, or trigger network lookups to an ungoverned issuer.

The right approach:

1. Tenants are registered through an authenticated onboarding workflow.
2. Issuer, JWKS URI, audience, and token strategy are validated.
3. The tenant is added to a managed registry.
4. The system enforces quotas on active and pending tenants.
5. Managers/decoders are prepared per policy.
6. The tenant transitions to ACTIVE only after required configuration is ready.

### 2.2. Distinguish Active, Disabled, and Deleted

| Status | Meaning | Eligible to Resolve Manager? |
|---|---|---|
| PENDING | Onboarding in progress | No |
| ACTIVE | Permitted to receive requests | Yes, if manager is ready |
| DISABLED | Access temporarily suspended | No |
| DELETING | Offboarding/draining in progress | Reject new requests |
| DELETED | Removed per retention policy | No |

Do not use the manager cache as the source of truth for tenant status. The tenant registry must determine whether a tenant is still permitted to operate; the cache merely holds components built from the registry.

### 2.3. Set Actionable Quotas

You can cap:

- Total onboarded tenants.
- Active tenants.
- Distinct issuers.
- Trust configurations.
- Tenants with dedicated introspection endpoints.
- Tenants allowed custom JWKS URIs.
- Rate of issuer/policy changes over a time window.
- Creation rate of new decoders/managers.

Do not pick arbitrary numbers. Derive them from memory budgets, connection pools, network capacity, AS rate limits, and product requirements. Enforce quotas at both the onboarding API and the service/database layer so concurrent requests cannot race past limits.

## 3. Bounding `ReactiveAuthenticationManager` and `ReactiveJwtDecoder` Counts

A simple approach for small systems is pre-creating managers for a finite list of tenants:

~~~java
Map<String, ReactiveAuthenticationManager> managers = Map.of(
    "tenant-a", managerA,
    "tenant-b", managerB
);
~~~

The resolver simply looks up the tenant in the registry:

~~~java
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> {
        String tenantId = resolveTenantFromTrustedRoute(exchange);

        ReactiveAuthenticationManager manager = managers.get(tenantId);
        if (manager == null) {
            return Mono.error(unknownTenant());
        }

        return Mono.just(manager);
    };
~~~

This is easy to reason about, though manager count roughly equals configured tenant count. When tenant count is large or dynamic, bounded lifecycles and caches are required.

### 3.1. Never Create a New Decoder per Request

Anti-pattern:

~~~java
ReactiveAuthenticationManagerResolver<ServerWebExchange> resolver =
    exchange -> {
        String issuer = resolveIssuer(exchange);

        return Mono.fromCallable(
            () -> ReactiveJwtDecoders.fromIssuerLocation(issuer)
        )
        .subscribeOn(Schedulers.boundedElastic())
        .map(JwtReactiveAuthenticationManager::new);
    };
~~~

Every request creates a fresh decoder, repeating metadata discovery, key caching, and object graph allocation. As traffic grows, the application spawns many decoders for the same issuer and hammers the Authorization Server / JWKS endpoint.

**Decoders/managers must be built per trust configuration and reused**, never created per request.

### 3.2. Cache Keys Must Represent Policy, Not Just Tenant Name

A manager/decoder cache key may need:

~~~text
tenantId
issuer
jwksUri
audience
algorithm policy
validator policy version
client/introspection configuration version
~~~

Using only `tenantId` risks accidentally reusing an old manager with stale policy after an audience or issuer change.

Use an immutable key:

~~~java
record DecoderKey(
    String tenantId,
    String issuer,
    String jwksUri,
    String audience,
    long policyVersion
) {}
~~~

Never put raw client secrets into keys or logs. Use a secret/configuration version or reference ID to detect configuration changes.

### 3.3. Share Decoders Only When Trust Policies Match

Two tenants sharing an issuer cannot necessarily share the entire decoder/manager.

Example:

~~~text
Tenant A:
  issuer = https://id.example.com
  audience = orders-api-a

Tenant B:
  issuer = https://id.example.com
  audience = orders-api-b
~~~

You can share the public key/JWKS source at an appropriate layer, but audience validators and tenant policies must stay distinct. Sharing a decoder with an overly broad validator could let Tenant A's token pass Tenant B's audience check.

**Sharing key retrieval does not mean sharing authorization policy.**

### 3.4. Bounding the Manager Cache with Caffeine

Caffeine can cap how many managers stay resident in the process:

~~~java
import java.time.Duration;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

Cache<DecoderKey, ReactiveAuthenticationManager> managerCache =
    Caffeine.newBuilder()
        .maximumSize(500)
        .expireAfterAccess(Duration.ofMinutes(30))
        .recordStats()
        .build();
~~~

The values 500 and 30 minutes are illustrative only; size them to real capacity and tenant lifecycles.

A cache object does not replace the tenant registry. The resolver must confirm the tenant is still ACTIVE before fetching a manager. If the manager was evicted from cache, the system needs a controlled recreation flow or transient error—never blindly trust an arbitrary issuer.

### 3.5. Cache Eviction Is Not Tenant Offboarding

Evicting an idle manager merely frees an object/cache entry. The tenant may still be ACTIVE and get re-provisioned on a later request.

Offboarding must update the tenant registry and block new requests before eviction. Deleting a manager from cache while the tenant remains active will simply recreate the manager repeatedly or cause sporadic errors.

## 4. Lazy Initialization and Cold-Start Limits

Eagerly creating all decoders at startup can cause:

- Startup times scaling with tenant count.
- A single issuer outage slowing down the entire application.
- Simultaneous bursts of JWKS discovery requests.
- High memory usage even when most tenants carry zero traffic.

Lazy initialization builds a manager only when a tenant actually needs it. Still, lazy does not mean unbounded: an attacker could send requests across many tenants to force mass manager creation.

### 4.1. Combine Lazy Creation with Tenant Admission

A strategy:

1. Resolve only tenants marked ACTIVE in the registry.
2. Allow at most one active initialization per tenant.
3. Cap total concurrent initializations.
4. Cache the resulting manager by trust configuration.
5. Cap resident managers.
6. Upon eviction, keep registry metadata so managers can be rebuilt per policy.
7. When capacity is exhausted, reject/throttle with an explicit operational error.

### 4.2. Prevent Cache Stampedes

If the first 500 requests for a tenant arrive before its decoder exists, do not build 500 decoders or send 500 discovery/JWKS requests.

Use **single-flight initialization**: concurrent requests for the same tenant share one manager-creation task. Successful results are shared; failures follow bounded backoff and retry policy.

This can be implemented via a shared future/Mono per cache key, an async loading cache, or an initialization registry. In Reactor, ensure the factory never blocks on the event loop.

### 4.3. Never Cache Initialization Failures Indefinitely

If an issuer is briefly down, caching a manager creation failure forever prevents the tenant from recovering once the AS comes back up.

Conversely, retrying on every request triggers a network storm.

Use:

- Retries with backoff and jitter.
- Short failure caching or a circuit breaker.
- A cap on concurrent initializations.
- Metrics for initialization failures and recovery.
- An administrative mechanism to retry/refresh tenant config.

Never fail open by constructing a dummy Authentication when manager initialization fails.

## 5. Cache Types in a Resource Server

Do not call every cache a "token cache". Each data type has its own purpose, TTL, and risks.

| Cache | Data | Goal | Risk if TTL/Eviction Is Wrong |
|---|---|---|---|
| Tenant metadata | issuer, audience, status, policy version | Reduce config reads | Disabled tenant still treated as active |
| Manager/decoder | Token verification objects | Reuse objects | Retains stale policy or bloats memory |
| JWKS/key set | Public JWKs | Reduce key endpoint load | Delays key rotation or emergency removal |
| Introspection result | active, scope, subject, expiry | Reduce AS calls | Revoked tokens remain accepted |
| Revocation/denylist | jti/session/user version | Reject revoked tokens | Revocation missed |
| Authorization data | Roles, tenant entitlements, policy | Reduce policy queries | Stale permissions remain valid |
| Discovery metadata | Issuer endpoints, supported algorithms | Reduce discovery requests | Stale endpoints/policies remain in use |

Never use one uniform TTL across all caches. For example, a JWKS cache handles key distribution; an introspection cache directly controls token state freshness; a tenant status cache controls how fast a tenant can be disabled.

## 6. JWKS Caching and Key Rotation

JWT decoders typically fetch public keys from the issuer's JWKS endpoint. The public key set can be cached to avoid re-fetching on every request.

~~~mermaid
sequenceDiagram
    participant R as Resource Server
    participant C as JWKS cache
    participant J as JWKS endpoint

    R->>C: Lookup kid
    alt Key present in cache
        C-->>R: Public key
        R->>R: Verify JWT
    else Cache miss / refresh needed
        R->>J: Fetch JWKS
        J-->>R: Public JWK set
        R->>C: Update cache
        R->>R: Verify JWT
    end
~~~

### 6.1. Cache Public Keys per Issuer

The JWKS cache must be namespaced by trust source. Never mix public keys across issuers just because they share a `kid`.

`kid` is not globally unique. Two issuers can both use `kid=key-1` with completely different public keys.

Key caches must bind to the allowlisted issuer/JWKS source and appropriate policy version.

### 6.2. Overly Long TTLs Delay Emergency Rotation

If the AS drops a compromised key from JWKS while the Resource Server still holds that key in cache, tokens signed by the old private key can continue verifying until the cache refreshes or the key is invalidated.

JWKS TTL must balance:

- Load on the issuer/JWKS endpoint.
- Time to pick up new keys.
- Time to drop compromised keys.
- Availability during temporary issuer unreachability.

Never claim key removal is instantaneous if Resource Servers hold independent un-invalidated caches.

### 6.3. Overly Short TTLs Also Cause Problems

If JWKS caches expire too frequently, many Resource Servers hit the endpoint every cycle, creating heavy load and making authentication more network-dependent.

Use sensible caching, refresh coordination, jitter, and outbound concurrency limits.

### 6.4. Unknown `kid`s and Refresh Storms

A JWT can carry a `kid` missing from JWKS. The decoder may need to refresh the key set to check for a newly published key.

If an attacker sends many JWTs with random `kid`s, it risks triggering repeated refresh attempts. Apply:

- Request rate limiting.
- Coalescing refresh requests per issuer.
- Bounded HTTP concurrency and timeouts.
- Never creating a new decoder/JWKS client per token.
- Monitoring refresh failures and unknown-`kid` rates.
- Safe, short negative-caching/rate-limiting strategies if supported by your implementation.

Never permanently cache "kid does not exist", since a valid new key may be published later.

## 7. Introspection Cache and Revocation Lag

For opaque tokens, `ReactiveOpaqueTokenIntrospector` calls the Authorization Server to check whether the token is active and fetch attributes.

Introspection results can be cached to cut network traffic, though caching `active=true` opens a window where stale results are accepted.

Example:

~~~text
10:00:00  introspection -> active=true, cache 30s
10:00:05  Authorization Server revokes token
10:00:20  Resource Server cache hit active=true
10:00:30  cache expires
10:00:31  introspection -> active=false
~~~

In this example, the token was revoked at 10:00:05 yet remains accepted until the cache expires.

### 7.1. TTL Must Align with the Revocation SLA

If the business requires revocations to take effect within at most 5 seconds, you cannot cache `active=true` for 60 seconds and claim compliance.

Introspection TTL should be bounded by:

- Remaining time until token `exp`.
- Revocation SLA.
- AS state update speed.
- Network/cache propagation.
- Availability requirements.

Never cache an active result beyond the token's `exp`.

### 7.2. Cache Keys Must Separate Issuer and Resource Context

Never use the raw token value as a cache key visible in logs. Derive a stable lookup key using a hash of the token:

~~~text
issuer-id : resource-id : SHA-256(token)
~~~

If the same token is introspected across different tenant/resource contexts, the cache key must preserve those boundaries. Never let `active=true` from AS A be reused for AS B.

### 7.3. Never Store Raw Tokens in Cache Keys or Metrics

A token is a Bearer credential. Using raw tokens as Redis keys, metric labels, or log values risks exposing credentials through operational tooling.

Use an appropriate token fingerprint/hash; protect cache values too, as they may hold subjects, scopes, and personal data.

### 7.4. `active=false` Also Needs a Bounded Cache

Caching inactive results cuts repeated introspection calls for invalid tokens, but needs a short TTL and bounded cardinality. Attackers can send endless random tokens to grow the cache without bound.

Never let a negative cache become an unbounded store for every credential an attacker sends.

## 8. Revocation and Authorization Caches

Beyond introspection, applications may cache:

- `jti` denylists.
- User/session token versions.
- Account enabled status.
- Tenant entitlements.
- Role and permission mappings.
- Domain authorization decisions.

These caches govern whether requests are allowed or denied. TTLs and invalidation must satisfy revocation requirements.

### 8.1. Revocation State Must Not Be Arbitrarily Evicted

Suppose a revoked `jti` is stored in cache. If that entry is evicted before `exp`, the Resource Server might accept the token again.

For a denylist, entries typically must persist until `exp` plus clock-skew margin, or until another mechanism guarantees the token is invalid.

If a cache enforces `maximumSize` and evicts critical entries prematurely, the system can lose revocation guarantees. Choose an appropriate store and eviction policy; never place critical revocation state in a generic LRU cache without analyzing the consequences.

### 8.2. Caching User Enabled/Disabled State

If an account is disabled, a user status cache may still report enabled briefly.

Define clearly:

- Maximum TTL.
- Invalidation events.
- Behavior when events are dropped.
- Behavior when the cache backend fails.
- Fail-open vs. fail-closed policy for sensitive operations.

### 8.3. Never Cache Broad Authorization Decisions

A decision like "user X can read order Y" can change when owner, tenant, order state, or policy changes.

Cache keys must include all inputs affecting the decision, with an appropriate TTL. For sensitive operations, checking permissions directly against the domain/repository is usually safer than reusing stale cached decisions.

## 9. Cache Keys and Tenant Isolation

A cache key missing tenant/issuer namespaces can leak one tenant's data into another tenant's context.

Insufficient keys:

~~~text
decoder:issuer-a
introspection:token-hash
user:123:roles
~~~

Depending on the data, namespace properly:

~~~text
tenant:{tenantId}:issuer:{issuer}:policy:{version}:...
~~~

### 9.1. Elements Typically Needed in Keys

| Cache | Key Components Typically Needed |
|---|---|
| Tenant config | tenant ID + config revision |
| Manager/decoder | issuer/tenant + trust policy version |
| JWKS | canonicalized issuer/JWKS URI + key-source version |
| Introspection | issuer + resource/client context + token fingerprint |
| Revocation | issuer + jti |
| User/session version | issuer + subject/session ID |
| Authorization decision | tenant + subject + resource + action + policy revision |

This is a design guideline, not a mandatory literal string format for every app. Ensure entries sharing a key truly share identical trust semantics.

### 9.2. Canonicalize Issuers and URIs

Issuer URIs may appear in slightly varying forms. Normalize them under consistent rules before using them as registry/cache keys, without collapsing two distinct issuers together.

Never take an issuer URL straight from an unverified token, use it as a cache key, and spawn a resource or network client for it. Look it up in the trusted registry first.

### 9.3. Policy Versioning Aids Invalidation

Whenever audience, JWKS URI, allowed algorithms, or role mappings change, increment the policy/config revision.

Cache keys carrying the new revision will not accidentally reuse a manager built under the old policy. After publishing new configuration, proactively evict old entries and track surviving manager/decoder counts.

## 10. Eviction, Expiration, and Invalidation Differ

| Mechanism | Meaning | Example |
|---|---|---|
| Expiration | Entry expires over time | 10-second introspection cache |
| Eviction | Cache drops entries due to capacity/policy | LRU manager evicted past `maximumSize` |
| Invalidation | Proactively deleting entries when data changes | Disabled tenant or compromised JWKS key |
| Refresh | Updating data before/after cache expiration | Fetching fresh JWKS |
| Reconciliation | Re-syncing state when events/caches drift | Rebuilding tenant registry after reconnect |

Never rely on expiration alone for tenant offboarding. When a tenant is disabled, trigger active invalidation so new requests cannot use old managers or caches.

### 10.1. Does Manager Eviction Affect In-Flight Requests?

If an in-flight request already holds a reference to a manager, removing the cache entry does not usually destroy the object mid-request. However, if the manager owns dedicated HTTP clients/resources and the app closes them immediately upon eviction, in-flight requests may fail.

Manage lifecycles cleanly:

- Stop issuing the manager to new requests.
- Let in-flight requests finish within bounds.
- Close application-owned resources once no longer in use.
- Never close a shared HTTP client during a single tenant's eviction if other managers use it.

### 10.2. Tenant Offboarding

An offboarding flow can:

1. Transition the tenant to DISABLED/DELETING in the registry.
2. Reject new requests and stop resolving managers.
3. Revoke refresh tokens/sessions per AS policy.
4. Invalidate issuer/audience/tenant trust configuration.
5. Invalidate tenant metadata, manager/decoder, and introspection caches.
6. Handle revocation/authorization caches per retention policy.
7. Drain in-flight requests.
8. Close application-owned tenant-specific clients/resources.
9. Audit completion and verify the tenant cannot be recreated from incoming requests.

Clearing the decoder cache alone is insufficient if the tenant registry still marks the tenant ACTIVE.

## 11. Local Cache vs. Distributed Cache?

Not every cache needs Redis or a shared store.

| Data Type | Local Cache | Shared/Distributed Store |
|---|---|---|
| Decoder/manager objects | Suitable since objects live in-process | Never ship Java objects across nodes |
| JWKS/public keys | Usually suitable | Can share key material if architecture supports it |
| Tenant metadata | Fast; requires cross-node invalidation | Useful when replicas need the same revision |
| Introspection results | Fast, but per-node state | Can share active/revoked state |
| `jti` denylist | Insufficient if stored on one node only | Usually needs shared store / event propagation |
| User/session versions | Local cache has propagation lag | Shared store or event-driven invalidation |

### 11.1. Local Cache

Pros:

- Fast reads.
- Zero network round trips.
- Integrates cleanly with decoder/manager object lifecycles.

Cons:

- Each node holds its own copy.
- Restarts wipe the cache.
- Invalidations must reach every replica.
- Memory is multiplied across nodes.

### 11.2. Distributed Cache

Pros:

- Shared data across nodes.
- Centralized revocation/configuration updates.
- Reduces cache skew between replicas.

Costs:

- Network latency and a new dependency.
- Requires timeouts, connection pools, retries, and circuit breakers.
- Sensitive data must be protected.
- Cache outages can impact authentication/authorization.
- Never serialize decoder/manager objects to share them.

With WebFlux, never call a blocking Redis client directly on the event loop. Use a reactive client or offload blocking work to a managed scheduler.

## 12. Bounding Outbound Connections and Introspection Traffic

A tenant with a dedicated introspection endpoint adds HTTP traffic and connection pool demand.

If every tenant creates an unbounded WebClient/connection pool, large tenant counts drive up sockets, file handles, TLS handshakes, and memory.

Consider:

- Reusing HTTP clients when trust/TLS policies match.
- Bounding connections per host/tenant.
- Setting connect/read/response timeouts.
- Capping pending acquires and concurrency.
- Applying rate limits to introspection.
- Using circuit breakers for AS outages.
- Retrying with bounded backoff and jitter.
- Never retrying invalid tokens unboundedly.
- Never using one tenant's client credentials for another tenant.

### 12.1. Separate Token Errors from Authorization Server Errors

| Scenario | Meaning |
|---|---|
| Introspection returns active=false | Token invalid/inactive |
| Introspection returns active=true | Proceed to validation/authorization |
| Timeout | Token state unknown |
| AS 5xx | No trustworthy verification result |
| TLS/client authentication failure | Configuration or trust failure |

Timeout/5xx does not mean the token is inactive, yet it must never mean the token is active either. Authentication lacking a trustworthy verification result must fail or follow a clearly defined fail-closed availability policy.

## 13. Protecting the Resolver from Cardinality and Request Abuse

The resolver executes on the authentication path. If resolution logic can allocate cache entries or trigger network calls from arbitrary input, it becomes a target for resource exhaustion.

Safeguards:

- Look up tenants only in a finite registry.
- Never create tenants/decoders from arbitrary headers.
- Allowlist issuers and JWKS/introspection endpoints.
- Cap distinct issuers/tenants.
- Rate-limit unknown tenants/issuers.
- Never create unbounded cache entries for random tokens or random `kid`s.
- Coalesce initialization and JWKS refreshes.
- Cap discovery/introspection concurrency.
- Never log raw tokens or secrets.
- Use bounded caches with measured cardinality.

### 13.1. Unknown Tenants Must Not Create Unbounded Cache Entries

If every request sends a random tenant ID and the resolver caches not-found results, the cache can grow without bound.

Either skip caching unknown IDs or use a negative cache with a very short TTL and strict maximum size. Rate-limit requests by source and route as well.

### 13.2. Never Let Metric Cardinality Grow with Tokens

Never place raw tokens, `jti`s, subjects, or arbitrary full issuer URLs into metric labels. High-cardinality metrics inflate memory and monitoring costs.

Use bounded tenant IDs, logical issuer IDs, or status categories. Token fingerprints belong only in internal cache lookups where needed, never as metric labels.

## 14. Measure Capacity Rather Than Guessing Limits

Before picking `maximumSize` or TTLs, measure:

- Onboarded and active tenant counts.
- Distinct issuers/trust configurations.
- Resident managers/decoders.
- Memory per manager/decoder in your implementation.
- JWKS entries and key counts per issuer.
- Introspection QPS per tenant.
- Introspection cache hit ratio.
- JWKS refresh rate and unknown-`kid` rate.
- Initialization latency and failures.
- Outbound connection counts and pending acquires.
- Event/revocation propagation lag.
- Cache eviction and miss rates.
- GC pauses and heap pressure.

### 14.1. Simple Estimation Model

A directional formula:

~~~text
Estimated heap
  ≈ active tenant metadata
  + resident manager/decoder objects
  + cached JWKS/public keys
  + introspection result entries
  + revocation/authorization entries
  + HTTP client/cache overhead
~~~

Or:

~~~text
M_total
  ≈ N_active × M_tenant_config
  + N_manager × M_manager
  + N_decoder × M_decoder
  + N_jwks × M_jwks
  + N_introspection_entries × M_introspection
~~~

This is an estimation model, not an exact measurement. Decoders may share clients or key caches; one tenant may need multiple decoders. Profile the heap and measure under realistic load.

### 14.2. Measure Both per Tenant and System-Wide

Per tenant:

- Request rate.
- Authentication success/failure.
- Introspection latency.
- Cache hits/misses.
- Decoder initialization.
- JWKS refreshes.
- Timeouts/circuit breaker state.

System-wide:

- Heap usage.
- Cache size/evictions.
- Active connections.
- Pending requests.
- Scheduler/event-loop saturation.
- GC.
- Authentication p95/p99.
- Counts of active tenants/managers/decoders.

Never log token data for observability.

## 15. Illustrative Caffeine Configuration

Caffeine works well for in-process local caching, especially for manager/decoder references or metadata with clear lifecycles.

~~~java
import java.time.Duration;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

Cache<String, TenantConfig> tenantConfigCache =
    Caffeine.newBuilder()
        .maximumSize(2_000)
        .expireAfterWrite(Duration.ofMinutes(5))
        .recordStats()
        .build();

Cache<DecoderKey, ReactiveAuthenticationManager> managerCache =
    Caffeine.newBuilder()
        .maximumSize(500)
        .expireAfterAccess(Duration.ofMinutes(30))
        .recordStats()
        .build();
~~~

Sizes and TTLs above merely illustrate the API. Choose values from tenant quotas, memory profiles, and revocation/configuration SLAs.

### 15.1. Why Do Config and Manager Caches Have Different TTLs?

Tenant configuration changes when an admin disables a tenant or updates issuer/audience. A long TTL without invalidation leaves nodes running stale config.

Manager/decoder objects can live longer when trust config is stable. However, when the policy version changes, invalidate the old manager immediately.

### 15.2. Caffeine Is Not a Distributed Cache

Each application instance holds its own Caffeine cache. Across 10 replicas, `maximumSize=500` allows up to roughly 10 × 500 entries cluster-wide, depending on which entries each instance creates.

Never rely on a local cache to assume every node has received a revocation event. For shared state, use a distributed store or event propagation with a defined consistency policy.

### 15.3. Eviction Listeners and Resource Cleanup

If a cache entry owns a dedicated HTTP client/resource, eviction may need cleanup. Close only resources exclusively owned by that entry; never close a shared client used by other managers.

Keep eviction listeners short and never run blocking cleanup on the event loop. For complex lifecycles, track resources in a dedicated registry and drain/close them cleanly.

## 16. Testing Limits and Cache Behavior

Do not test only happy-path authentication. Test capacity limits, eviction, tenant disabling, and concurrent initialization.

### 16.1. Tenant Admission Tests

- New tenants within quota are onboarded.
- Tenants exceeding quota are rejected.
- Concurrent onboarding requests cannot race past quota.
- DISABLED tenants fail to resolve managers.
- Issuers outside the allowlist do not create decoders.
- Custom JWKS URLs cannot be injected from requests.
- Deleted tenants cannot be recreated from stale caches.

### 16.2. Manager/Decoder Cache Tests

- Identical trust configurations reuse managers.
- New policy versions build new managers.
- `maximumSize` is respected per cache semantics.
- Expired entries are evicted.
- Cache misses do not spawn duplicate concurrent managers.
- Initialization failures apply backoff and recover.
- Tenant eviction never closes shared resources still in use.

### 16.3. JWKS Tests

- Key cache hits avoid re-calling the endpoint within the valid cache window.
- Key rotation is picked up within policy bounds.
- Unknown `kid`s do not trigger refresh storms.
- JWKS timeouts never allow unverified tokens.
- Emergency key removal propagates to nodes within SLA.
- Issuer A never uses Issuer B's key cache.

### 16.4. Introspection Cache Tests

- `active=true` is cached without exceeding `exp` or the revocation SLA.
- Revoking a token invalidates the cache per policy.
- `active=false` negative cache enforces TTL and `maximumSize`.
- Cache keys include issuer/resource namespaces.
- Raw tokens never appear in cache key logs/metrics.
- Introspection timeouts never turn into `active=true`.

### 16.5. Multi-Node Tests

Across multiple application instances:

1. Send tokens through nodes A and B.
2. Revoke a token or disable a tenant.
3. Verify both A and B observe the new state within SLA.
4. Disrupt the event bus or cache backend.
5. Verify fail-closed/staleness-window behavior.
6. Restart a node and confirm registries/caches rebuild safely.
7. Verify zero cross-tenant or cross-principal leakage.

## 17. Operating When the Tenant Registry or Cache Fails

| Incident | Behavior to Define |
|---|---|
| Tenant registry unreachable | Never auto-create tenants; fail closed or use an age-bounded snapshot |
| Manager cache full | Evict per policy or reject new initializations cleanly |
| JWKS endpoint timeout | Reject unverified new keys; use existing cached keys per stale policy |
| Introspection timeout | Never produce a successful Authentication |
| Revocation cache unavailable | Fail closed for sensitive operations or follow defined SLA |
| Tenant config changed but event dropped | Reconcile via revision/snapshot |
| Caffeine cache cleared on restart | Rebuild managers from trusted registry |
| One tenant sends traffic burst | Enforce per-tenant rate limits and concurrency budgets |

No single fallback fits every cache. Key caches, introspection caches, and revocation stores have different semantics.

### 17.1. Stale-While-Revalidate

For metadata or JWKS, a system may keep using cached data for a bounded stale window when refreshes fail. However, stale policies must distinguish:

- Known public keys verifying already-issued tokens.
- Unfetched new keys.
- Old keys under emergency revocation.
- Newly disabled tenants.
- Stale introspection active results.

Never apply stale-while-revalidate to disabled tenants or revocation states in a way that still admits revoked tokens. Stale JWKS boosts availability but prolongs trust in compromised keys.

### 17.2. Config Revisions and Reconciliation

Each tenant config can carry a revision:

~~~text
tenant-a policyVersion = 12
tenant-b policyVersion = 8
~~~

When a node receives a new config revision:

1. Update the registry.
2. Stop routing new requests to old-revision managers.
3. Create/activate the new manager if needed.
4. Invalidate old manager/decoder entries.
5. Reconcile if a node missed events.
6. Emit a revision-lag metric.

Events provide fast updates; snapshots/reconciliation recover from dropped events.

## 18. Common Anti-Patterns

**Creating a decoder per request.** Repeats discovery, key caching, and object allocations.

**Creating decoders for arbitrary issuers in unverified JWTs.** Opens SSRF and breaks trust boundaries.

**Unbounded tenant registries.** Tenant and decoder counts can grow uncontrollably.

**Using tenant ID as the sole cache key across policy changes.** Reuses managers with stale audiences/validators.

**Sharing a decoder across tenants with different audiences and overly broad validators.** Causes cross-tenant token acceptance.

**Using one TTL for all caches.** JWKS, introspection, revocation, and tenant status have different requirements.

**Caching `active=true` for too long.** Revoked tokens keep getting accepted.

**Evicting `jti` denylists before `exp`.** Revoked tokens can become accepted again.

**Caching unknown tenants unboundedly.** Attackers can inflate cache cardinality.

**Not coalescing manager/JWKS initialization.** Triggers cache stampedes and network storms.

**Closing shared HTTP clients when evicting a single tenant.** Breaks in-flight requests for other tenants.

**Using a local Caffeine cache as a cluster-wide revocation store.** Replicas do not share entries automatically.

**Caching principals/Authentications across requests.** Risks leaking identities or authorities across users/tenants.

**Logging raw access tokens or using tokens as metric labels.** Leaks credentials and explodes cardinality.

**Failing open when introspection/cache/registry fails.** Builds Authentication without trustworthy verification.

**Offboarding a tenant solely by deleting its decoder.** The tenant registry or other caches may still allow requests.

## 19. Capacity and Cache Design Process

**Step 1 — Count trust configurations.** Inventory active tenants, issuers, audiences, JWKS/introspection endpoints, and required managers/decoders.

**Step 2 — Set admission quotas.** Bound tenants, issuers, initialization concurrency, and config changes.

**Step 3 — Choose manager lifecycles.** Static registries for small tenant sets; bounded caches with controlled lazy creation for large or dynamic sets.

**Step 4 — Define cache keys.** Include issuer, tenant, resource, and policy version wherever they affect trust semantics.

**Step 5 — Separate cache types.** Tenant metadata, managers/decoders, JWKS, introspection, revocation, and authorization each need distinct TTLs and eviction.

**Step 6 — Define consistency.** Specify local vs. distributed caches, invalidation events, snapshots/reconciliation, and staleness windows.

**Step 7 — Bound network resources.** Connection pools, timeouts, concurrency, rate limits, and circuit breakers per tenant/issuer.

**Step 8 — Design cold starts.** Single-flight initialization, bounded executors, backoff, and capacity limits.

**Step 9 — Design offboarding.** Disable route/tenant first, block new requests, invalidate caches, drain requests, and clean up resources.

**Step 10 — Instrument metrics.** Cache size/hits/misses/evictions, decoder count, initialization latency, JWKS refreshes, introspection QPS, heap, and connection pools.

**Step 11 — Test failure modes.** Full caches, AS timeouts, unknown `kid`s, dropped events, tenant disabling, concurrent onboarding, and multi-node propagation.

**Step 12 — Revisit when adding tenants or issuers.** Every new trust configuration consumes memory/network budget and changes cache cardinality.

## 20. Self-Check Questions

**1. Does tenant count always equal decoder count?**

No. Many tenants can share an issuer and trust policy, whereas a single issuer with distinct audiences or validators may need separate manager/decoder policies.

**2. Should you create a `ReactiveJwtDecoder` per request?**

No. Build them per trust configuration and reuse them.

**3. Why can a cache key with tenant ID alone be insufficient?**

Issuer, audience, JWKS URI, or validator policies can change. Include a policy/config revision to avoid reusing stale objects.

**4. Do JWKS caches and introspection caches share the same TTL?**

No. One stores public keys; the other stores token state. Revocation SLAs directly constrain introspection TTLs.

**5. Does a local Caffeine cache share entries across replicas?**

No. Each process maintains its own cache.

**6. Should `active=true` be cached indefinitely?**

No. A token can be revoked or expire while the cache still reports active.

**7. Can you evict a `jti` denylist before `exp` to save memory?**

No, unless another mechanism guarantees the token can no longer be accepted.

**8. Why is single-flight manager initialization necessary?**

So concurrent requests for the same tenant do not build duplicate decoders/managers and fire duplicate discovery requests.

**9. Should an unknown tenant auto-create a decoder from the request's issuer?**

No. Tenants and issuers must come from a governed registry.

**10. Is deleting the manager cache sufficient for tenant offboarding?**

No. You must disable the tenant in the registry, block new requests, invalidate related caches, and clean up lifecycle resources.

**11. Should `Authentication` or principals be cached and shared across requests?**

No. `Authentication`/`SecurityContext` belong to a single request; sharing them risks identity or authority leakage.

**12. When introspection times out, can the token be treated as active to preserve availability?**

No. Without a trustworthy verification result, a successful `Authentication` must never be created.

## Conclusion

A multi-tenant Resource Server must treat **tenant count, manager/decoder count, and cache cardinality** as real operational limits. Each new trust configuration adds object graphs, JWKS state, HTTP traffic, and initialization overhead. Never build decoders per request, never auto-provision tenants from untrusted input, and never retain managers or caches unboundedly.

Separate caches by semantics: tenant metadata, managers/decoders, JWKS, introspection, revocation, and authorization each have different TTLs, invalidation, and consistency models. **Introspection caching affects revocation lag; JWKS caching affects key rotation; tenant caching affects disabling/offboarding; revocation caching affects whether revoked tokens can be re-accepted.**

Use bounded caches, tenant admission quotas, single-flight initialization, trusted issuer registries, policy-versioned cache keys, connection/concurrency caps, and observability. When caches or Authorization Servers fail, maintain fail-closed behavior per security policy. **Capacity planning must be validated with metrics, heap profiling, and load/failure tests—not an arbitrary `maximumSize` number.**

### References

- [Spring Security — Reactive OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/multitenancy.html)
- [Spring Security — Servlet OAuth 2.0 Resource Server Multi-tenancy](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/multitenancy.html)
- [Spring Security — Reactive JWT Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/jwt.html)
- [Spring Security — Reactive Opaque Token Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security API — ReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authentication/ReactiveAuthenticationManagerResolver.html)
- [Spring Security API — JwtIssuerReactiveAuthenticationManagerResolver](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtIssuerReactiveAuthenticationManagerResolver.html)
- [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html)
- [Caffeine — High Performance Java Caching](https://github.com/ben-manes/caffeine/wiki)
- [Caffeine — Eviction](https://github.com/ben-manes/caffeine/wiki/Eviction)
- [Project Reactor — Context](https://projectreactor.io/docs/core/release/reference/advancedFeatures/context.html)
- [RFC 7517 — JSON Web Key (JWK)](https://www.rfc-editor.org/rfc/rfc7517)
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519)
- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 8414 — Authorization Server Metadata](https://www.rfc-editor.org/rfc/rfc8414)
