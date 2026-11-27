# Introspection Caching and Revocation Propagation Delay

With an OAuth 2.0 Opaque Token, the Resource Server typically calls the Authorization Server (AS) to introspect the access token before creating an Authentication. Each introspection call incurs network cost, latency, AS load, and dependency on the token endpoint's availability. Caching introspection results reduces those calls, yet introduces an important security trade-off: **a token cached as active may continue to be accepted for a period of time after the AS revokes it**.

This period is commonly called *revocation propagation delay*, *revocation latency*, or the *stale authorization window*. If the cache TTL is 30 seconds, a Resource Server can continue accepting a revoked token for nearly 30 seconds after the last active introspection, plus AS state update latency, invalidation event delivery, and clock drift.

You cannot choose a TTL based on performance alone. You must weigh endpoint risk level, token lifetime, how the AS performs revocation, the number of Resource Server instances, and active invalidation capabilities. This lesson explains RFC 7662 introspection, positive/negative caching, TTLs, Spring Security Servlet/WebFlux integration, distributed caches, testing, and operating during token revocation.

## 1. What Is Introspection?

OAuth 2.0 Token Introspection is defined in RFC 7662. The Resource Server sends a token to an endpoint published by the AS; the AS returns metadata about the token's state. The `active` attribute indicates whether the token is considered active.

Illustrative request:

~~~http
POST /oauth2/introspect HTTP/1.1
Host: login.example.test
Authorization: Basic <RESOURCE_SERVER_CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<OPAQUE_ACCESS_TOKEN>
token_type_hint=access_token
~~~

An active response may look like this:

~~~json
{
  "active": true,
  "scope": "orders.read orders.write",
  "client_id": "shop-web",
  "username": "alice",
  "token_type": "Bearer",
  "sub": "alice",
  "aud": ["orders-api"],
  "iss": "https://login.example.test",
  "iat": 1924991700,
  "exp": 1924992000
}
~~~

Attributes beyond `active` depend on the token profile and AS policy. The Resource Server must validate the attributes required for its resource, such as audience, scope, subject, issuer, or timestamps.

An inactive response typically takes the form:

~~~json
{
  "active": false
}
~~~

`active: false` can mean the token does not exist, has expired, was revoked, is not permitted for introspection by the calling client, or is no longer valid under AS policy. The Resource Server should not guess a detailed cause when the AS omits one.

### 1.1. Uncached Request Flow

~~~text
Client
  |
  | Authorization: Bearer <opaque token>
  v
Resource Server
  |
  | POST /introspect
  v
Authorization Server
  |
  | active=true + claims
  v
Resource Server
  |
  | build Authentication
  v
Controller / API
~~~

If the Resource Server introspects tokens on every request, revocation state is queried from the AS continuously. In return, every request depends on the network and AS, increasing latency, cost, and pressure on identity infrastructure.

### 1.2. Cached Request Flow

~~~text
Client
  |
  | Bearer token
  v
Resource Server
  |
  v
Introspection cache
  |
  +-- cache hit, unexpired entry --> Authentication
  |
  +-- cache miss/expired
          |
          v
      Authorization Server
          |
          v
      Cache active result
          |
          v
      Authentication
~~~

The cache stores introspection results, usually comprising principal attributes and authorities built from the response. A cache hit skips the network call to the AS. Consequently, the Resource Server may not immediately know a token was revoked while an active entry stays cached.

## 2. How Caching Changes Revocation Semantics

Suppose the Resource Server introspects token T at 10:00:00 and receives `active=true`. It caches the result for 30 seconds. The AS revokes T at 10:00:05.

~~~text
10:00:00  Introspection(T) → active=true
          Cache T until 10:00:30

10:00:05  AS revokes T

10:00:08  Request with T → cache hit → accepted
10:00:20  Request with T → cache hit → accepted
10:00:29  Request with T → cache hit → accepted

10:00:30  Cache entry expires

10:00:31  Introspection(T) → active=false
          Resource Server rejects T
~~~

In this example, the token remains accepted for roughly 25 seconds after revocation. This is an intentional consequence of caching, not a cache bug.

### 2.1. Revocation Does Not Automatically Push into Caches

RFC 7009 defines the token revocation endpoint, yet a local cache inside a Resource Server has no built-in awareness that the AS just processed a revocation request. Nor does RFC 7662 require the AS to push notifications to every Resource Server when token state changes.

Without a dedicated invalidation mechanism, the Resource Server discovers revocation only when:

- The cache entry expires and the token is introspected again.
- The Resource Server actively evicts the entry via a deployed invalidation channel.
- Another request refreshes state according to system policy.

### 2.2. TTL Is a Latency Bound, Not a Revocation Time

TTL does not control when the AS revokes a token. TTL governs how long the Resource Server can reuse an **old introspection result** before querying the AS again.

A 10-second cache TTL does not mean tokens are revoked after 10 seconds. It means cached entries must not be served beyond their TTL expiration.

### 2.3. Revocation Can Have Multiple Delay Layers

Actual delay can include:

1. AS persisting token state in its database/cluster.
2. Introspection replicas observing the updated state.
3. Revocation event emitted toward Resource Servers (if present).
4. Resource Server instances receiving and applying invalidation.
5. Old cache entry evicted or reaching TTL expiry.
6. In-flight requests that already passed authentication before invalidation completed.

Simply shrinking TTL does not eliminate AS or event-transport lag. Measure and design across the entire chain.

## 3. Defining Revocation Propagation Delay

Let:

- `T_cache`: maximum TTL of the positive introspection cache.
- `T_as`: maximum delay for revocation state to take effect across introspection nodes.
- `T_event`: maximum latency of the push invalidation channel (if any).
- `T_clock`: clock skew and scheduling/expiration tolerance.
- `T_inflight`: duration of a request that passed authentication before revocation was observed.

When relying on TTL alone without push invalidation, a conservative bound on stale time is:

\[
T_{\text{stale}} \lesssim T_{\text{as}} + T_{\text{cache}} + T_{\text{clock}} + T_{\text{inflight}}
\]

When push invalidation operates reliably, delay can be bounded by AS event emission, delivery, and cache eviction:

\[
T_{\text{push}} \lesssim T_{\text{as}} + T_{\text{event}} + T_{\text{clock}} + T_{\text{inflight}}
\]

TTL should remain as a fallback in case events are dropped or a Resource Server goes temporarily offline. In practice, never claim a hard upper bound without measuring and verifying each component above.

### 3.1. Example Stale Window Calculation

Assume:

| Component | Assumed Value |
|---|---:|
| AS replication delay | 2 seconds |
| Cache TTL | 20 seconds |
| Event invalidation | None |
| Clock skew allowance | 1 second |
| Request already past authentication | 1 second |

The estimated bound under this TTL design is around 24 seconds. If the business requirement states revoked tokens must lose access within 5 seconds, a 20-second TTL fails the requirement even if the introspection endpoint responds very quickly.

### 3.2. Requests Authenticated Before Revocation

Cache invalidation does not necessarily abort an in-flight request that already passed authentication. For example, a report-export request takes 2 minutes while the token is revoked mid-execution. The Resource Server typically does not re-introspect between internal service calls.

If running work must also be aborted, implement a dedicated cancellation/session/task-revocation mechanism. Never assume cache eviction automatically rolls back transactions or kills executing requests.

## 4. Choosing TTL Based on Security Requirements

Shorter TTLs reflect revocation faster at the cost of more introspection calls. Longer TTLs raise cache hits and reduce AS load, yet let revoked tokens stay accepted longer.

| Positive Cache TTL | Revocation Freshness | Introspection Load | Best Fit |
|---:|---|---|---|
| 0 seconds / no cache | Queries AS every time | Highest | Near-real-time status needed and AS has capacity |
| 1–5 seconds | Very fast within cache bound | High | Sensitive endpoints, high-risk transactions |
| 10–30 seconds | Balanced per policy | Medium | Standard APIs, measured latency and revocation SLA |
| 1–5 minutes | Slower | Low | Lower risk, short-lived tokens, compensating controls |
| Equal to or longer than token lifetime | May never re-introspect before expiry | Low | Usually defeats fast revocation goals |

These ranges are illustrative starting points. No single TTL fits every system.

### 4.1. TTL Must Never Exceed Token Expiration

If the introspection response includes `exp`, the cache entry must not outlive the token's expiration timestamp:

\[
T_{\text{effective}} = \min(T_{\text{configured}}, exp - now)
\]

For instance, if configured TTL is 30 seconds while only 8 seconds remain on the token, cache the entry for at most 8 seconds (typically minus a safety margin). Without capping against `exp`, the Resource Server could serve an active principal past the token's lifetime.

If the introspection profile omits `exp`, use a short policy-approved TTL; the AS remains the authority for `active`. Never try to infer expiry from an opaque token string.

### 4.2. Token Expiration and Token Revocation Are Distinct Events

- **Expiry:** natural expiration per `exp` or AS-defined lifetime.
- **Revocation:** AS actively marks the token inactive ahead of expiry.

Caching must respect both. A long TTL cannot be justified solely because access tokens have short expiries if the AS can revoke tokens early and the system requires rapid enforcement.

### 4.3. High-Privilege Tokens Deserve Dedicated Policies

Consider shorter TTLs or bypassing caching for:

- Payments, money transfers, account changes.
- User/role/permission administration.
- Email, credential, or recovery settings changes.
- Actions requiring immediate session termination during incidents.

Not every API needs the same TTL. A Resource Server can tailor cache policies by audience, route, or risk class, provided cache keys and authorization contexts remain safely isolated.

## 5. Positive Cache and Negative Cache

### 5.1. Positive Cache: Introspection Returns active=true

This is the primary cache:

~~~text
token fingerprint → {
    active = true,
    principal = alice,
    authorities = [SCOPE_orders.read],
    validUntil = min(now + TTL, token exp)
}
~~~

Positive caching cuts down AS calls, at the cost of a stale-active window after revocation.

### 5.2. Negative Cache: Introspection Returns active=false

You can cache inactive results briefly to prevent repeated AS calls for the same invalid token:

~~~text
token fingerprint → {
    active = false,
    validUntil = now + negativeTTL
}
~~~

Negative TTLs should generally be very short and deliberately scoped. A token might have just been minted or change state under a provider flow; caching inactive too long risks rejecting a newly active token.

### 5.3. Never Cache Infrastructure Failures as Inactive

Draw a clear boundary:

| Introspection Outcome | Cache? | Reason |
|---|---|---|
| HTTP success, `active=true` | Yes, per positive TTL | Valid principal/claims available |
| HTTP success, `active=false` | Optional, very short negative TTL | Reduces repeat calls for inactive tokens |
| Timeout / connection refused | No | Unknown whether token is active or inactive |
| HTTP 5xx from AS | No | Service error is not an inactive-token verdict |
| `invalid_client` / RS auth failure | No | Client/secret configuration issue |
| Malformed response / missing `active` | No | No valid result to cache |

Caching timeouts or 5xx responses as inactive turns a brief AS hiccup into prolonged rejections for all tokens. Caching errors as active fails open and accepts tokens without fresh verification.

### 5.4. Negative Caches Can Be Abused

An attacker can send floods of random token strings to bloat cache memory. Enforce maximum size, eviction policies, rate limiting, and token length caps. Never cache unbounded entries for arbitrary bad tokens.

### 5.5. Be Careful with BadOpaqueTokenException

Spring Security's opaque token introspector typically signals inactive tokens using an exception such as `BadOpaqueTokenException`. If you implement negative caching, separate exceptions representing a **valid inactive-token result** from network, AS, or client-configuration errors. Never catch every `RuntimeException` and treat it as inactive.

## 6. Cache Keys: Never Store Raw Access Tokens

An access token is a credential. Never use the raw token as a cache key if the cache backend could expose keys in metrics, management UIs, logs, heap dumps, or diagnostic endpoints.

A cache key should combine:

~~~text
cache namespace
    + issuer/introspection endpoint
    + resource-server client identity
    + tenant/resource context (if applicable)
    + token fingerprint
~~~

The token fingerprint can be an HMAC-SHA-256 of the token using a Resource Server-specific secret:

~~~java
import java.nio.charset.StandardCharsets;
import java.util.Base64;
import javax.crypto.Mac;
import javax.crypto.SecretKey;
import javax.crypto.spec.SecretKeySpec;

final class TokenFingerprint {

    private final SecretKey key;

    TokenFingerprint(byte[] secret) {
        this.key = new SecretKeySpec(secret, "HmacSHA256");
    }

    String of(String token) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(key);
            byte[] digest = mac.doFinal(
                token.getBytes(StandardCharsets.UTF_8));
            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (Exception ex) {
            throw new IllegalStateException(
                "Cannot fingerprint access token", ex);
        }
    }
}
~~~

Manage the HMAC secret as a security key rather than hardcoding it in source code. An HMAC fingerprint prevents cache keys from storing raw tokens and prevents arbitrary cross-system correlation of fingerprints.

### 6.1. Why Include Issuer/Client/Resource in the Namespace?

A token may be introspected across multiple security contexts or AS instances. Results can vary by introspection endpoint, authenticated resource server client, tenant, or resource-specific policy.

Never share a cache entry across:

- Different issuers.
- Different tenants.
- Different Resource Server client registrations with differing introspection permissions.
- Different resource audiences with distinct authorization policies if introspection or conversion depends on the resource.

### 6.2. Never Use sub as the Cache Key

One user can hold multiple tokens with different scopes, audiences, expiries, clients, and revocation states. Keying on `sub=alice` risks handing one token's principal or authorities to another token.

Cache keys must identify the **token**, not merely the user.

## 7. What Should Be Cached?

Typically cache the verified introspection outcome, such as `OAuth2AuthenticatedPrincipal` and the attributes/authorities derived from the response. Never cache just a boolean `active=true` while ignoring claims.

Caching only `active=true` while sourcing claims elsewhere risks pairing active status with the wrong subject or scope.

An entry can store:

~~~text
CacheEntry
    principal
    authorities
    issuer/resource context
    introspectedAt
    validUntil
    token fingerprint
~~~

Never store the raw access token in the value. Avoid mutating attributes/authorities after caching; treat the cached principal as immutable or store an immutable snapshot.

### 7.1. Do Not Accidentally Cache Domain Authorization Decisions

Introspection returns token metadata. Whether a user can read order 42 can also depend on ownership, tenant, order status, live policy, or business data.

Caching a principal does not mean caching the entire authorization decision. If you also cache domain decisions, maintain separate TTL and invalidation policies for that data.

### 7.2. exp and validUntil

Compute:

~~~text
validUntil = now + configuredPositiveTtl

if introspection response contains exp:
    validUntil = min(validUntil, exp - safetyMargin)

if validUntil <= now:
    do not cache as a reusable active entry
~~~

The safety margin avoids cache hits right on the expiry edge when node clocks differ slightly. Keep the margin consistent with clock synchronization and token lifetimes; never set it so large that valid tokens are rejected prematurely.
## 8. Integrating Caching into Spring Security Resource Server

Spring Security provides the following introspector abstractions:

| Stack | Interface | Role |
|---|---|---|
| Servlet | `OpaqueTokenIntrospector` | Synchronously introspects tokens and returns `OAuth2AuthenticatedPrincipal` |
| WebFlux | `ReactiveOpaqueTokenIntrospector` | Reactively introspects tokens, typically returning `Mono<OAuth2AuthenticatedPrincipal>` |

You can wrap the existing introspector in a caching decorator. The security authentication provider still calls the same abstraction; the decorator decides whether to serve from cache or invoke the delegate.

### 8.1. Servlet Authentication Flow

~~~text
BearerTokenAuthenticationFilter
        |
        v
OpaqueTokenAuthenticationProvider
        |
        v
CachingOpaqueTokenIntrospector
        |
        +-- hit --> cached principal
        |
        +-- miss --> delegate introspector --> AS
        |
        v
BearerTokenAuthentication
        |
        v
Authorization / Controller
~~~

### 8.2. WebFlux Authentication Flow

~~~text
Bearer token WebFilter
        |
        v
Reactive opaque-token authentication manager
        |
        v
CachingReactiveOpaqueTokenIntrospector
        |
        +-- hit --> cached principal Mono
        |
        +-- miss --> delegate introspector Mono --> AS
        |
        v
Reactive Authentication
        |
        v
Authorization / Handler
~~~

The extension point lives at the introspector so caching runs before a principal enters the authentication context. Never cache a request-bound Authentication or a global `SecurityContext`.

## 9. Implementing CachingOpaqueTokenIntrospector for Servlet

The example below uses Caffeine as a local in-memory cache. Add Caffeine to runtime dependencies:

~~~gradle
dependencies {
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

### 9.1. Cache Entry with validUntil

Store not only the principal, but also the timestamp until which the entry may be used:

~~~java
import java.time.Instant;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;

record CachedIntrospection(
    OAuth2AuthenticatedPrincipal principal,
    Instant validUntil
) {}
~~~

`validUntil` is the lesser of the configured TTL and the token's expiry minus the safety margin.

### 9.2. Synchronous Decorator

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.InvalidBearerTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

final class CachingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private final OpaqueTokenIntrospector delegate;
    private final Cache<String, CachedIntrospection> cache;
    private final TokenFingerprint fingerprint;
    private final Clock clock;
    private final Duration ttl;
    private final Duration safetyMargin;

    CachingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            TokenFingerprint fingerprint,
            Clock clock,
            Duration ttl,
            Duration safetyMargin,
            long maximumSize) {
        this.delegate = delegate;
        this.fingerprint = fingerprint;
        this.clock = clock;
        this.ttl = ttl;
        this.safetyMargin = safetyMargin;
        this.cache = Caffeine.newBuilder()
            .maximumSize(maximumSize)
            .expireAfterWrite(ttl)
            .build();
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        String key = fingerprint.of(token);

        CachedIntrospection entry = cache.get(
            key, ignored -> load(token));

        if (!entry.validUntil().isAfter(clock.instant())) {
            cache.invalidate(key);
            return introspect(token);
        }

        return entry.principal();
    }

    void invalidate(String token) {
        cache.invalidate(fingerprint.of(token));
    }

    void invalidateFingerprint(String tokenFingerprint) {
        cache.invalidate(tokenFingerprint);
    }

    private CachedIntrospection load(String token) {
        OAuth2AuthenticatedPrincipal principal =
            delegate.introspect(token);

        Instant now = clock.instant();
        Instant validUntil = now.plus(ttl);
        Instant tokenExpiry = asInstant(principal.getAttribute("exp"));

        if (tokenExpiry != null) {
            Instant expiryLimit = tokenExpiry.minus(safetyMargin);
            if (!expiryLimit.isAfter(now)) {
                throw new InvalidBearerTokenException(
                    "Introspection returned an expired token");
            }
            if (expiryLimit.isBefore(validUntil)) {
                validUntil = expiryLimit;
            }
        }

        return new CachedIntrospection(principal, validUntil);
    }

    private Instant asInstant(Object value) {
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
}
~~~

This decorator pattern targets Java 17+. `TokenFingerprint` is the HMAC helper shown earlier. Caffeine's `cache.get(key, loader)` coalesces concurrent loads for the same key within a local cache. `expireAfterWrite(ttl)` enforces a physical upper bound; checking `validUntil` ensures tokens whose `exp` is shorter than TTL are never served past expiry.

If the delegate throws `BadOpaqueTokenException`, times out, or hits an AS error, the loader returns no `CachedIntrospection`; Caffeine caches no fake active result. This pattern also rejects tokens when the AS anomalously returns `active=true` with an `exp` already inside the safety margin. Crucially, never catch delegate errors and return a stale expired principal.

### 9.3. Wiring the Decorator into the Servlet SecurityFilterChain

The opaque-token Security DSL accepts an `OpaqueTokenIntrospector`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ServletResourceServerConfiguration {

    @Bean
    SecurityFilterChain apiSecurity(
            HttpSecurity http,
            OpaqueTokenIntrospector cachingIntrospector) throws Exception {

        return http
            .authorizeHttpRequests(authorize -> authorize
                .requestMatchers("/health").permitAll()
                .anyRequest().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque -> opaque
                    .introspector(cachingIntrospector))
            )
            .build();
    }
}
~~~

The `cachingIntrospector` bean must wrap the delegate introspector already configured with the right introspection URI, client ID/secret, HTTP client, timeouts, and error handling. Builder/constructor names for creating the delegate depend on your Spring Security version; keeping the project's existing delegate and wrapping it minimizes behavior changes.

Never configure two competing introspectors leaving it ambiguous which bean the chain uses. In tests/integration checks, verify real requests flow through this decorator.

### 9.4. Configuring the Delegate

Where the bean is constructed, structure it as:

~~~java
OpaqueTokenIntrospector remoteIntrospector =
    createExistingRemoteIntrospector(
        introspectionUri,
        resourceServerClientId,
        resourceServerClientSecret);

OpaqueTokenIntrospector cachingIntrospector =
    new CachingOpaqueTokenIntrospector(
        remoteIntrospector,
        tokenFingerprint,
        clock,
        Duration.ofSeconds(10),
        Duration.ofSeconds(1),
        50_000);
~~~

`createExistingRemoteIntrospector(...)` is a placeholder representing your application's existing Nimbus/Spring introspector setup; it is not a Spring Security API of that name. This shows the decorator layering: remote delegate inside, cache wrapper outside.

## 10. Caching for ReactiveOpaqueTokenIntrospector

In WebFlux, never call a blocking introspector or blocking cache/network operation on the event loop. Use a reactive delegate and an async cache so concurrent requests with the same token share the in-flight load.

### 10.1. Reactive Decorator

Example using Caffeine `AsyncCache`:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;

import com.github.benmanes.caffeine.cache.AsyncCache;
import com.github.benmanes.caffeine.cache.Caffeine;

import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.InvalidBearerTokenException;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import reactor.core.publisher.Mono;

final class CachingReactiveOpaqueTokenIntrospector
        implements ReactiveOpaqueTokenIntrospector {

    private final ReactiveOpaqueTokenIntrospector delegate;
    private final AsyncCache<String, CachedIntrospection> cache;
    private final TokenFingerprint fingerprint;
    private final Clock clock;
    private final Duration ttl;
    private final Duration safetyMargin;

    CachingReactiveOpaqueTokenIntrospector(
            ReactiveOpaqueTokenIntrospector delegate,
            TokenFingerprint fingerprint,
            Clock clock,
            Duration ttl,
            Duration safetyMargin,
            long maximumSize) {
        this.delegate = delegate;
        this.fingerprint = fingerprint;
        this.clock = clock;
        this.ttl = ttl;
        this.safetyMargin = safetyMargin;
        this.cache = Caffeine.newBuilder()
            .maximumSize(maximumSize)
            .expireAfterWrite(ttl)
            .buildAsync();
    }

    @Override
    public Mono<OAuth2AuthenticatedPrincipal> introspect(String token) {
        String key = fingerprint.of(token);
        return Mono.defer(() -> Mono.fromFuture(
            cache.get(key, (ignored, executor) ->
                delegate.introspect(token)
                    .map(this::toEntry)
                    .toFuture()
            )
        )).flatMap(entry -> {
            if (!entry.validUntil().isAfter(clock.instant())) {
                cache.synchronous().invalidate(key);
                return introspect(token);
            }
            return Mono.just(entry.principal());
        });
    }

    void invalidate(String token) {
        cache.synchronous().invalidate(fingerprint.of(token));
    }

    void invalidateFingerprint(String tokenFingerprint) {
        cache.synchronous().invalidate(tokenFingerprint);
    }

    private CachedIntrospection toEntry(
            OAuth2AuthenticatedPrincipal principal) {
        Instant now = clock.instant();
        Instant validUntil = now.plus(ttl);
        Object rawExpiry = principal.getAttribute("exp");
        Instant tokenExpiry = asInstant(rawExpiry);

        if (tokenExpiry != null) {
            Instant expiryLimit = tokenExpiry.minus(safetyMargin);
            if (!expiryLimit.isAfter(now)) {
                throw new InvalidBearerTokenException(
                    "Introspection returned an expired token");
            }
            if (expiryLimit.isBefore(validUntil)) {
                validUntil = expiryLimit;
            }
        }
        return new CachedIntrospection(principal, validUntil);
    }

    private Instant asInstant(Object value) {
        if (value instanceof Instant instant) return instant;
        if (value instanceof Date date) return date.toInstant();
        if (value instanceof Number seconds) {
            return Instant.ofEpochSecond(seconds.longValue());
        }
        return null;
    }
}
~~~

`AsyncCache.get` returns the same in-flight future for duplicate loads of the same key within a cache instance, curbing concurrent calls to the introspection endpoint. When the delegate errors, the future fails and is never retained as an active principal. If the AS returns `active=true` with `exp` already past the safety margin, the decorator rejects the token instead of caching or looping introspection.

### 10.2. Wiring the Decorator into the WebFlux SecurityWebFilterChain

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.server.resource.introspection.ReactiveOpaqueTokenIntrospector;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
class ReactiveResourceServerConfiguration {

    @Bean
    SecurityWebFilterChain apiSecurity(
            ServerHttpSecurity http,
            ReactiveOpaqueTokenIntrospector cachingIntrospector) {

        return http
            .authorizeExchange(exchanges -> exchanges
                .pathMatchers("/health").permitAll()
                .anyExchange().authenticated()
            )
            .oauth2ResourceServer(oauth2 -> oauth2
                .opaqueToken(opaque -> opaque
                    .introspector(cachingIntrospector))
            )
            .build();
    }
}
~~~

The reactive delegate introspector must use a reactive HTTP client with proper timeouts. Never wrap a synchronous `OpaqueTokenIntrospector` in `Mono.fromCallable()` on the event loop; if a legacy blocking API must be used, offload it to a bounded scheduler and evaluate backpressure and capacity.

### 10.3. Servlet and WebFlux Do Not Share the Same Implementation

The two interfaces have different execution models. You can share the token fingerprint, cache policy, cache entry, and metric names, but never use a blocking `Cache.get` on the reactive request path. Choose `Cache` for Servlet and `AsyncCache`/reactive adapters for WebFlux.

## 11. The Revocation Endpoint and Implications for Introspection Caching

RFC 7009 defines OAuth 2.0 Token Revocation. The client sends a token to the revocation endpoint; the AS authenticates the client and revokes the token per policy. A success response does not necessarily reveal whether the token existed or was already revoked, preventing token probing.

Illustrative request:

~~~http
POST /oauth2/revoke HTTP/1.1
Host: login.example.test
Authorization: Basic <CLIENT_CREDENTIALS>
Content-Type: application/x-www-form-urlencoded

token=<ACCESS_TOKEN>
token_type_hint=access_token
~~~

Once the AS processes revocation, the introspection endpoint should reflect the token as inactive according to the provider's semantics and consistency guarantees. However, active caches on Resource Servers are not automatically cleared simply because the revocation endpoint returned success.

### 11.1. Revoking Access Tokens vs. Refresh Tokens

The two token types play distinct roles:

- Revoking an **access token** stops Resource Servers from continuing to accept the current credential.
- Revoking a **refresh token** stops the client from requesting new access tokens using that refresh credential.

Revoking a refresh token does not automatically render already-issued access tokens inactive immediately. Some AS implementations cascade-revoke linked tokens by policy; others let issued access tokens remain valid until expiry. Check your AS contract and test actual behavior.

### 11.2. Logout Does Not Mean All Access Tokens Are Invalidated

Logout may clear a session cookie or end a browser session while issued access tokens remain alive. To ensure logout/revocation takes effect at Resource Servers:

- The AS must revoke the access token or token family per policy.
- Introspection must return inactive for revoked tokens.
- Resource Server caches must use appropriate TTLs/invalidation.
- Downstream Resource Servers must receive updated state within SLA.

Never conclude logout revoked access tokens solely because the browser lost its session.

### 11.3. Revocation Propagation Is a Contract Between AS and Resource Server

Operational documentation should specify:

| Question | Contract to Define |
|---|---|
| When does the AS persist revocation? | Synchronous commit vs. eventual consistency |
| When do introspection replicas update? | Replication SLA |
| How long is Resource Server cache TTL? | Positive/negative TTLs by risk |
| Is push invalidation used? | Event type, delivery, retries, authentication |
| How are lost events handled? | TTL fallback, event replay, reconciliation |
| What happens when the AS is unavailable? | Fail closed, cache hit policy, stale-if-error if approved |
| Where is the revocation SLA measured? | From revocation acceptance to the last accepted request |

## 12. Local Caches, Distributed Caches, and Push Invalidation

### 12.1. Local Cache per Resource Server Instance

~~~text
                 Authorization Server
                   /      |      \
                  /       |       \
                 v        v        v
             RS node A  RS node B  RS node C
              cache A    cache B    cache C
~~~

Advantages:

- Low cache-hit latency.
- No extra network dependency per lookup.
- Each node operates independently within TTL bounds.

Limitations:

- Each node holds its own cache copy.
- Invalidation must reach all nodes.
- Newly started/restarted nodes start with different cache state.
- A post-revocation request may be rejected by node A yet still accepted by node B.

When using local caches, establish a maximum TTL and a way to broadcast invalidations across all instances.

### 12.2. Shared Distributed Cache

~~~text
RS node A ----\
RS node B -----+---- Redis / shared cache
RS node C ----/
                    |
                    +-- key fingerprint
                    +-- principal/claims
                    +-- TTL
~~~

Advantages:

- A single cache invalidation affects all nodes.
- Cache hits do not depend on which node handles the request.
- Capacity, metrics, and eviction policies can be centralized.

Limitations:

- Every request adds a network hop to the cache.
- The shared cache becomes a critical dependency.
- Principal/authority serialization must be tightly controlled.
- Network partitions or cache outages need an explicit failure policy.
- Cached data and credentials must be protected as security-sensitive data.

A distributed cache does not solve revocation by itself if the AS neither deletes keys nor emits events. It simply shares cache state.

### 12.3. Push Invalidation via Events

An architecture can emit an event after revocation:

~~~text
Admin / Client
     |
     v
Authorization Server
     |
     +--> persist revocation
     |
     +--> publish TokenRevoked event
                |
                v
          Event broker
             /  |  \
            v   v   v
          RS-A RS-B RS-C
            |   |   |
            v   v   v
         invalidate cache entry
~~~

Events can carry an internal token identifier, issuer, tenant, timestamp, event ID, and token type. For opaque tokens, the AS can emit a stable revocation identifier that Resource Servers map to their cache keys. Avoid sending raw access tokens over the broker.

### 12.4. Requirements for Invalidation Events

- **Authenticated producer:** only the AS or an authorized component may emit events.
- **Authenticated consumers:** Resource Servers verify event source/broker ACLs.
- **At-least-once safe:** events may arrive multiple times; invalidation must be idempotent.
- **Ordering:** handle events by version/sequence if out-of-order delivery is possible.
- **Retry/DLQ:** failed event processing must retry and be monitored.
- **Replay:** offline nodes must catch up on events or reconcile state.
- **TTL fallback:** if an event is dropped, cache entries still expire per policy.
- **Observability:** measure event lag, consumer lag, and invalidated cache entry counts.

### 12.5. Race Between In-Flight Introspection and Revocation Events

An important race condition:

~~~text
T0  RS cache miss, starts introspection request
T1  AS revokes token
T2  Revocation event reaches RS, cache key deleted
T3  Stale introspection request returns active=true from an un-updated replica
T4  RS writes active=true back into cache
~~~

Left unhandled, a stale entry can be repopulated after invalidation. Mitigations include:

- AS ensures introspection reads consistent revocation state after revocation commits.
- Events carry a version/sequence and cache entries are written only if no newer revocation version exists.
- Store a revocation tombstone for a minimum window so cache misses cannot re-insert an old active entry.
- Check event timestamp vs. request start time before accepting an in-flight introspection result.
- Track an invalidation generation per token fingerprint.

Simply deleting a key from Redis or a local cache is insufficient if an in-flight introspection call can write the result back afterward.

### 12.6. Events Do Not Replace TTL

Push invalidation shortens stale windows under normal operation. Yet events can be dropped, consumers can go offline, brokers can lag, or a node can miss a message. TTL remains the mandatory fallback safety bound.

## 13. Caching and Availability During Authorization Server Outages

Caching reduces load and can let a Resource Server keep authenticating previously introspected tokens during brief AS outages. However, handling of cache misses and stale entries must be explicit.

### 13.1. Unexpired Cache Hit During an AS Outage

If an active entry remains within its TTL, the Resource Server can use it per approved policy. Revocations occurring during the outage may go unnoticed without push invalidation.

### 13.2. Cache Miss During an AS Outage

The Resource Server has no proof the token is active. The safe default policy is rejecting authentication whenever introspection fails, typically returning 401/503 depending on error handling. Never turn a timeout into `active=true`.

### 13.3. Stale-if-Error

Some systems consider continuing to serve cached active results past TTL when the AS is unreachable. This *stale-if-error* mode must be treated as an explicit security policy decision:

- Strictly bound the stale grace period.
- Apply only to entries previously confirmed active.
- Never apply to tokens that were never successfully introspected.
- Never exceed token expiry.
- Disable it on high-risk endpoints.
- Emit metrics/alerts every time a stale result is served.
- Never serve stale if a revocation event arrived or token compromise is suspected.

Stale-if-error widens the acceptance window for revoked tokens. Never enable it by default merely to boost availability.

### 13.4. Fail-Open vs. Fail-Closed

| Policy | When Introspection Fails | Consequence |
|---|---|---|
| Fail closed | Reject without a valid result | Higher security, depends on AS availability |
| Fail open | Accept despite inability to verify | Can admit invalid tokens |
| Bounded stale-if-error | Serve cached active entries only within a bounded grace period | Explicit trade-off with stale revocation risk |

Never say "caching keeps the API running when the AS is down" without answering whether tokens could have been revoked during the outage.

### 13.5. Timeouts, Retries, and Circuit Breakers

- Set connect/read/response timeouts on the introspection HTTP client.
- Retry only transient errors, with bounded attempts and exponential backoff/jitter.
- Never retry invalid tokens or invalid client credentials.
- Circuit breakers shield the AS from retry storms; when open, apply your fail-closed or approved stale policy.
- Cap concurrent introspection calls to prevent token floods.
- Never let retries exceed the inbound request deadline.

## 14. Capacity, Cache Stampedes, and Concurrency

### 14.1. Estimating Cache Size

If N distinct tokens are active within a TTL window, the cache must hold roughly N entries (barring eviction). For example, 2,000 requests/s each using a new token with a 30-second TTL can generate roughly 60,000 active entries.

User tokens are typically reused across multiple requests, so actual entry counts depend on distinct active tokens rather than total request rate.

### 14.2. Cache Stampede

When an entry expires, multiple concurrent requests with the same token can hit the AS simultaneously. Use a loading cache/single-flight mechanism to coalesce loads per key inside an instance. Across multiple nodes, local single-flight can still trigger one introspection call per node; add distributed locks only if the cost and complexity are genuinely justified.

### 14.3. Refreshing Cache Entries

Avoid background-refreshing every entry purely because it approaches TTL expiry unless clearly required. Background refreshes can generate heavy introspection traffic even for idle tokens. Simple expire-after-write often suffices; if using refresh-ahead, refresh only actively accessed entries while honoring expiry and revocation policies.

### 14.4. Maximum Size and Eviction

Caches must enforce a capacity bound. Early eviction only increases introspection requests; it must never make an expired token valid. When an entry is evicted, the next request must query the AS again.

### 14.5. Keep Tokens Out of Cache Keys and Metrics

Metrics should use only bounded labels such as issuer alias, result, cache outcome, and resource server ID. Never use raw tokens, unique fingerprints, subjects, or token IDs as labels due to high cardinality and data exposure risks.

## 17. Metrics, Logs, and SLOs for Revocation

Without measuring the time from revocation to the last accepted request, an organization cannot verify whether its TTL meets requirements.

### 17.1. Cache Metrics

Useful metrics:

| Metric | Purpose |
|---|---|
| `oauth2_introspection_requests_total` | Calls sent to delegate/AS |
| `oauth2_introspection_duration_seconds` | Introspection latency |
| `oauth2_introspection_errors_total` | Timeouts, 5xx, invalid client, malformed responses |
| `oauth2_introspection_cache_hits_total` | Cache hits |
| `oauth2_introspection_cache_misses_total` | Cache misses |
| `oauth2_introspection_cache_evictions_total` | Evicted entries |
| `oauth2_introspection_cache_size` | Current entry count |
| `oauth2_introspection_cache_stale_served_total` | Stale-if-error serves |
| `oauth2_revocation_events_received_total` | Received revocation events |
| `oauth2_revocation_event_lag_seconds` | Delay from event emission to consumer handling |
| `oauth2_revocation_cache_invalidations_total` | Invalidated cache entries |
| `oauth2_revocation_last_accept_delay_seconds` | Measured delay from revocation to last accepted request |

Metric names are illustrative; follow your project's telemetry conventions. Use only bounded label values such as issuer alias, resource-server alias, outcome, and environment. Never use tokens, fingerprints, subjects, or `jti` as labels.

### 17.2. Calculating Cache Hit Ratio

A simple calculation:

\[
\text{hit ratio} =
\frac{\text{cache hits}}
{\text{cache hits} + \text{cache misses}}
\]

A high hit ratio lowers AS load, yet does not prove security. A 99.9% hit ratio with a 10-minute TTL can violate a 5-second revocation SLA.

### 17.3. Measuring Revocation SLA

You can define:

~~~text
revocation acceptedAt:
    timestamp when AS confirms revocation succeeded

lastAcceptedAt:
    timestamp when any Resource Server last accepted the token

revocationDelay:
    lastAcceptedAt - acceptedAt
~~~

Measure across all Resource Server nodes, behind the load balancer, and across the cache invalidation path. For in-flight requests, define whether the SLO measures authentication time or response completion time.

### 17.4. Structured Logs

Log events without credentials:

~~~text
event=introspection outcome=active issuer=shop-rs cache=miss
event=introspection outcome=cache_hit issuer=shop-rs
event=introspection outcome=inactive issuer=shop-rs cache=miss
event=revocation_invalidation outcome=success issuer=shop-rs
event=revocation_invalidation outcome=retry event_id=evt-123
event=introspection outcome=error reason=timeout issuer=shop-rs
~~~

Never log:

~~~text
token=eyJ...
Authorization: Bearer ...
refresh_token=...
full_introspection_request_body=...
~~~

Even though opaque tokens reveal no readable claims, they remain usable credentials. Redact them across application logs, proxy logs, traces, broker payload inspections, and exception output.

## 18. Runbook When a Revoked Token Still Grants Access

When an incident shows a revoked token still receiving 2xx responses, check in order:

1. Confirm the AS returned revocation success for the right token type.
2. Call introspection with a valid resource server client and confirm the AS returns `active=false`.
3. Verify whether the Resource Server is on the opaque introspection path or a local JWT decoder path.
4. Inspect cache hits/misses, entry age, TTL, and `validUntil`.
5. Check whether cache key namespace/issuer/tenant matches the exact entry.
6. Confirm revocation events were published, consumed, and invalidated on every node.
7. Check whether an older in-flight introspection call wrote an active entry back after invalidation.
8. Inspect shared/local caches and which node received requests from the load balancer.
9. Check whether stale-if-error or a fallback policy is enabled.
10. Record the timestamp of the last accepted request and compare against the revocation SLA.

### 18.1. Mitigation Actions

Depending on incident severity:

- Lower positive TTL per approved policy.
- Invalidate the cache entry using the verified token identifier.
- Temporarily disable caching for sensitive resources.
- Disable stale-if-error if active.
- Diagnose and fix event consumer or replication lag.
- Revoke the token family/session or require re-issuance per AS procedures.
- Restrict high-risk endpoints/operations during remediation.

Never flush the entire cache in production without evaluating the surge in introspection load; doing so can trigger a cache stampede against the AS. If a broad flush is necessary, prepare rate/concurrency limits and coordinate with identity operations.

### 18.2. When AS Introspection Returns active=true After Revocation

If the AS accepted revocation yet introspection still returns active:

- Verify the revoked token ID/type matches the token being tested.
- Check AS replication and consistency.
- Check provider revocation semantics and whether an access token or only a refresh token was revoked.
- Verify the resource server client has introspection rights and targets the right issuer/tenant.
- Confirm whether AS policy cascade-revokes related tokens.

Resource Server caching is not the only possible culprit; distinguish stale AS state from stale cache state.

## 19. Common Implementation Mistakes

### 19.1. Overly Long TTL Just to Reduce AS Load

Long TTLs can push revocation delay past SLA. Pick TTLs based on threat models and load measurements, not cache hit ratios alone.

### 19.2. Indefinite Positive Caching

Never cache active principals/tokens without expiration. Without a TTL, revoked tokens can remain accepted until eviction or node restart.

### 19.3. Failing to Cap TTL by exp

Entries can outlive the access token lifetime. Compute `validUntil` as `min(configured TTL, token expiry minus safety margin)`.

### 19.4. Caching Timeouts/5xx as Active or Inactive

Connectivity errors are not introspection verdicts. Never cache infrastructure errors as token validity decisions.

### 19.5. Keying Cache by Subject Instead of Token

Multiple tokens for the same user can differ in scopes, audiences, and expiries. Keying by subject can hand out privileges belonging to another token.

### 19.6. Invalidating Only One Node

Local caches on other nodes still hold active results. Broadcast invalidations, use a shared cache, or maintain TTL fallback and test cross-node behavior.

### 19.7. Push Invalidation Without Race Protection

Old in-flight introspection calls can overwrite cache state after an event arrives. Use generations, tombstones, versions, or AS consistency guarantees.

### 19.8. Using Raw Tokens as Cache Keys

Cache keys can leak via metrics, logs, management tools, or heap dumps. Use HMAC fingerprints and namespace by issuer/client/resource.

### 19.9. Failing Open When the AS Is Unreachable

On a cache miss during an AS outage, there is no proof the token is active. Allow stale-if-error only within an approved grace period, and never accept tokens that were never introspected.

### 19.10. Confusing JWKS Caching with Introspection Caching

JWKS caches store public keys for verifying JWT signatures; they do not track per-token revocation states. The two caches serve different purposes and have different TTLs.

### 19.11. Assuming Revoking a Refresh Token Revokes Access Tokens

Already-issued access tokens may stay active until expiry depending on the AS. Verify provider semantics and post-revocation introspection responses.

### 19.12. Testing Only One Resource Server Node

One node receiving events while another misses them yields inconsistent behavior. Test through the load balancer and inspect every node.

## 20. Introspection Cache Design Checklist

### 20.1. Security Semantics

- [ ] AS returns `active=false` for expired/revoked tokens per confirmed contract.
- [ ] Access token revocation is distinguished from refresh token revocation.
- [ ] Positive TTL is chosen per revocation SLA and risk class.
- [ ] Entry TTL never exceeds token expiry minus safety margin.
- [ ] Timeouts/5xx/invalid-client errors are never cached as active or inactive.
- [ ] Negative cache (if used) has a short TTL and dedicated capacity limit.
- [ ] Cache keys identify the token, never the subject.
- [ ] Cache keys never store raw tokens; HMAC fingerprints are used.
- [ ] Cache namespace separates issuer, tenant, resource server client, and resource context.
- [ ] Cached principals/authorities are never mutated after storage.

### 20.2. Spring Integration

- [ ] Servlet uses an `OpaqueTokenIntrospector` decorator.
- [ ] WebFlux uses `ReactiveOpaqueTokenIntrospector` and a non-blocking async cache.
- [ ] `SecurityFilterChain`/`SecurityWebFilterChain` actually wires the caching introspector bean.
- [ ] Delegate preserves introspection URI, client authentication, HTTP timeouts, and error mapping.
- [ ] Cache hits return the principal matching the exact token.
- [ ] Cache misses call the AS and cache only valid responses.
- [ ] Cache eviction/invalidation introduces no fail-open path.

### 20.3. Cluster and Revocation

- [ ] Local cache, distributed cache, or hybrid model explicitly chosen.
- [ ] Local cache invalidations broadcast to all instances where needed.
- [ ] Distributed cache has proper ACLs, encryption, network policies, and capacity.
- [ ] Push events enforce authentication, retries, idempotency, and replay/reconciliation.
- [ ] In-flight introspection cannot overwrite a newer revocation event.
- [ ] TTL remains a fallback if events are lost.
- [ ] AS replication delay and introspection consistency have been measured.
- [ ] Tested through the load balancer across all Resource Server nodes.

### 20.4. Availability and Observability

- [ ] Bounded timeouts, retries, circuit breakers, and concurrency limits configured.
- [ ] Clear fail-closed policy on cache miss during AS unavailability.
- [ ] Stale-if-error (if present) is bounded, metered, and formally approved.
- [ ] Hit ratio, misses, introspection latency/errors, cache size/evictions monitored.
- [ ] Revocation event lag and last-accepted-after-revoke delay monitored.
- [ ] Tokens, raw fingerprints, refresh tokens, and full introspection bodies never logged.
- [ ] Runbook distinguishes stale AS state from stale Resource Server cache state.

## 21. Example Risk-Based Policies

An organization might define illustrative policy profiles:

| Profile | Positive TTL | Push Invalidation | Stale-if-Error | Example Use Case |
|---|---:|---|---|---|
| High risk | 0–2 seconds | Mandatory or equivalent control | Disabled | Payments/admin/recovery |
| Standard API | 5–15 seconds | Enabled if AS supports | Disabled or very short | Orders/customer data |
| Low-risk internal | 30–60 seconds | Optional | Only if approved | Read-only metadata |

These are merely starting examples for discussion. Final policies must reflect revocation SLA, AS capacity, token lifetime, user impact, and threat model. Never copy one service's TTL across all APIs without evaluating risk.

## 22. Conclusion

Introspection caching helps Resource Servers cut latency and Authorization Server load when authenticating opaque access tokens. Yet caching an `active=true` result also means the Resource Server may keep accepting a token after the AS revokes it.

Stale windows depend on positive TTL, AS replication, event invalidation, clock skew, and in-flight requests. TTL provides a vital fallback; push invalidation can shrink revocation delay, provided dropped events, offline nodes, and races with in-flight introspection calls are handled.

In Spring Security, wrapping `OpaqueTokenIntrospector` or `ReactiveOpaqueTokenIntrospector` in a caching decorator is a clean integration point. Caches must key on token fingerprints rather than raw tokens, store token-bound principals/authorities, cap `validUntil` against `exp`, bound capacity, and never cache infrastructure failures as token validity verdicts. WebFlux requires async/reactive caching to avoid blocking the event loop.

**Cache hit ratio is not a security metric.** What matters is measuring from when the AS confirms revocation to when the last request is rejected by any Resource Server across the cluster. Choose TTLs and invalidation strategies so measured delay satisfies each endpoint's revocation SLA.

## References

- [RFC 7662 — OAuth 2.0 Token Introspection](https://www.rfc-editor.org/rfc/rfc7662)
- [RFC 7009 — OAuth 2.0 Token Revocation](https://www.rfc-editor.org/rfc/rfc7009)
- [RFC 6749 — The OAuth 2.0 Authorization Framework](https://www.rfc-editor.org/rfc/rfc6749)
- [RFC 6750 — OAuth 2.0 Bearer Token Usage](https://www.rfc-editor.org/rfc/rfc6750)
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068)
- [Spring Security — OAuth 2.0 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html)
- [Spring Security — Reactive OAuth 2.0 Resource Server](https://docs.spring.io/spring-security/reference/reactive/oauth2/resource-server/opaque-token.html)
- [Spring Security — OpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/OpaqueTokenIntrospector.html)
- [Spring Security — ReactiveOpaqueTokenIntrospector Javadoc](https://docs.spring.io/spring-security/site/docs/current/api/org/springframework/security/oauth2/server/resource/introspection/ReactiveOpaqueTokenIntrospector.html)
- [Caffeine Cache — User Guide](https://github.com/ben-manes/caffeine/wiki)

## 15. Self-Contained JWTs Differ from Opaque Token Introspection

Do not confuse introspection caching with JSON Web Key Set (JWKS) caching.

| Opaque Access Token | Self-Contained JWT Access Token |
|---|---|
| Resource Server typically queries AS via introspection | Resource Server verifies signature/claims locally |
| Cache stores active state and principal from introspection | Decoder caches public signing keys/JWKS metadata |
| Revocation reflects via introspection after AS updates | Cryptographically valid JWTs may remain accepted until expiry without a separate revocation check |
| Introspection TTL directly governs the stale revocation window | JWKS cache TTL mainly affects key rotation, not per-token revocation |

### 15.1. JWKS Cache Is Not a Revocation Cache

A JWKS cache holds public keys for verifying signatures. When the AS revokes a JWT access token, the public key usually must remain published to verify other tokens signed with that key. Removing a signing key from JWKS just to revoke one token would break all tokens signed by that key.

### 15.2. Ways to Revoke JWTs Early

Options depending on architecture:

- Short access token lifetimes with refresh token rotation.
- A denylist/revocation store keyed by `jti` or token fingerprint.
- Introspection for JWTs if supported by the AS and the Resource Server uses the opaque/introspection path.
- Event invalidation so Resource Servers update local revocation state.
- Token profiles/architectures with a version or session epoch checked per request.

Each option carries different network/state costs and delays. Self-contained JWTs do not provide real-time revocation out of the box.

### 15.3. Caching Claims and Permission Changes

Even without token revocation, user permissions can change after introspection. If the AS returns scopes/roles in the introspection response, caching the principal also caches that permission snapshot. TTL and invalidation policies must account for permission changes, logouts, and account disabling, not only token revocation.

## 16. Testing Introspection Caching and Revocation Delay

Test the decorator at the unit level, `SecurityFilterChain`/`SecurityWebFilterChain` at the integration level, and multi-node/event propagation in deployed environments.

### 16.1. Testing That Cache Hits Reduce Delegate Calls

Synchronous test example with a stubbed delegate:

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.Clock;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.Test;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

class CachingOpaqueTokenIntrospectorTest {

    @Test
    void repeatedRequestsUseOneIntrospectionResult() {
        AtomicInteger calls = new AtomicInteger();

        OAuth2AuthenticatedPrincipal principal =
            new DefaultOAuth2AuthenticatedPrincipal(
                "alice",
                Map.of("scope", "orders.read"),
                List.of(new SimpleGrantedAuthority("SCOPE_orders.read"))
            );

        OpaqueTokenIntrospector delegate = token -> {
            calls.incrementAndGet();
            return principal;
        };

        var caching = new CachingOpaqueTokenIntrospector(
            delegate,
            new TokenFingerprint(new byte[32]),
            Clock.systemUTC(),
            Duration.ofSeconds(10),
            Duration.ofSeconds(1),
            1_000);

        caching.introspect("opaque-token-1");
        caching.introspect("opaque-token-1");
        caching.introspect("opaque-token-1");

        assertEquals(1, calls.get());
    }
}
~~~

This test proves the same token is introspected once within the local cache TTL. It does not prove revocation is reflected immediately; test invalidation and expiry separately.

### 16.2. Testing Invalidation After a Revoke Event

Suppose the AS stub initially returns active, then switches to inactive:

~~~java
AtomicBoolean active = new AtomicBoolean(true);
AtomicInteger calls = new AtomicInteger();

OpaqueTokenIntrospector delegate = token -> {
    calls.incrementAndGet();
    if (!active.get()) {
        throw new BadOpaqueTokenException("Token is inactive");
    }
    return principal;
};

var caching = new CachingOpaqueTokenIntrospector(
    delegate,
    fingerprint,
    Clock.systemUTC(),
    Duration.ofSeconds(30),
    Duration.ofSeconds(1),
    1_000);

caching.introspect("opaque-token-1");  // cache active
active.set(false);                    // AS revokes token

// A cache hit may still return active before invalidation.
caching.introspect("opaque-token-1");

// Event consumer processes TokenRevoked.
caching.invalidate("opaque-token-1");

// Next call delegates and is rejected.
assertThrows(
    BadOpaqueTokenException.class,
    () -> caching.introspect("opaque-token-1"));
~~~

This illustrates local cache behavior. In a real test, the event consumer should receive an authenticated event, map its identifier to the namespaced cache key, and invoke invalidation. Never pass raw tokens through an event broker just to simplify tests.

### 16.3. Testing Negative Results Are Not Confused with Transient Failures

Dedicated tests:

- Inactive token: delegate throws `BadOpaqueTokenException`; subsequent calls re-query if negative caching is disabled.
- Timeout: delegate throws timeout; errors must never become active principals.
- HTTP 5xx: never cache fake active results.
- Invalid client credentials: surface configuration error and alert; never classify user tokens as inactive.

If negative caching is enabled, assert inactive entries persist only for the configured negative TTL and never affect the positive cache.

### 16.4. Testing TTL and exp

With a controllable clock/ticker in tests:

1. Create a principal with `exp` 5 seconds away and configured TTL of 30 seconds.
2. Assert `validUntil` does not exceed `exp` minus safety margin.
3. Advance the clock past `validUntil`.
4. Assert the next introspection calls the delegate again.
5. Create an expired token; assert the decorator does not cache an active principal.

Inject `Clock` and a Caffeine `Ticker` into the cache factory for deterministic time tests instead of long `Thread.sleep` calls.

### 16.5. Testing Concurrent Requests

Launch multiple concurrent requests with the same token and assert the delegate is invoked once per cache miss inside an instance. Across multiple nodes, set clear expectations: local single-flight can still trigger one introspection call per node without a shared cache or distributed coordination.

### 16.6. Testing End-to-End Revocation Propagation

A system test can measure:

~~~text
1. Obtain opaque access token T
2. Send request to Resource Server A → accepted
3. Send request to Resource Server B → accepted
4. Revoke T at Authorization Server
5. Wait for AS state propagation
6. Deliver invalidation event (if configured)
7. Send request repeatedly to every Resource Server node
8. Record time of last accepted request
9. Assert last-accept time <= configured revocation SLA
~~~

Do not test only a single node. Load balancers route traffic across nodes with differing cache states; tests must cover the entire cluster.

### 16.7. Testing Race Conditions

Simulate:

- Introspection request starts before revocation.
- Revocation event arrives while the request is in flight.
- Stale introspection response returns after the event.

Assert the active entry is not written back after a newer invalidation version. This is an essential test when combining push invalidation with async caches.
