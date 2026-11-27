# Caching Valid Results, Token Expiration, and the Revocation Lag Window

In a **Spring Security OAuth 2.0 Resource Server**, authenticating an **opaque access token** typically relies on **token introspection**: the Resource Server calls the Authorization Server to ask whether an access token is still active, and receives attributes and authorities to make API access decisions. Compared to verifying a JWT locally with a public key, introspection can add network latency and load on the Authorization Server on every authentication.

One optimization is **caching successful introspection results** for a short duration. However, caching introduces a security trade-off: **the Authorization Server may have already revoked the token, while the Resource Server still holds a stale `active: true` result**. The period during which a revoked token may still be accepted due to caching is called the **revocation lag/window**.

Proper design is not simply slapping `@Cacheable` onto `OpaqueTokenIntrospector.introspect(...)`. You must understand **token expiration**, **cache TTL**, **how to compute a safe reuse deadline**, **token revocation**, **changing scopes/claims**, **cache keys**, **introspection failures**, **multiple instances**, and the requirement to **fail closed**.

This lesson focuses on customizing introspection in Spring Security OAuth 2.0/OIDC Resource Server, with Java Servlet stack examples using `OpaqueTokenIntrospector`, Caffeine, and short-lived caching policies.

## 1. Introspection and the Role of Caching

Request to the Orders API:

~~~http
GET /api/orders/123 HTTP/1.1
Host: orders.example.com
Authorization: Bearer opaque-access-token-example
~~~

In a Resource Server using opaque tokens:

1. `BearerTokenAuthenticationFilter` extracts the token string.
2. `OpaqueTokenAuthenticationProvider` passes the token to `OpaqueTokenIntrospector`.
3. The introspector sends the token to the Authorization Server's trusted introspection endpoint according to the protocol supported by both sides.
4. If the Authorization Server confirms the token is valid, the introspector returns an `OAuth2AuthenticatedPrincipal` with attributes and authorities.
5. The provider constructs an authenticated `BearerTokenAuthentication`.
6. Spring Security proceeds with authorization, e.g., checking `SCOPE_orders.read` and permissions for the exact order.

Without caching, the typical flow is:

~~~mermaid
sequenceDiagram
    autonumber
    participant C as OAuth2 Client
    participant F as BearerTokenAuthenticationFilter
    participant I as OpaqueTokenIntrospector
    participant AS as Authorization Server
    participant A as AuthorizationFilter
    C->>F: Authorization: Bearer T
    F->>I: introspect(T) via AuthenticationProvider
    I->>AS: POST /introspect, token=T
    AS-->>I: active=true + exp + scope + ...
    I-->>F: OAuth2AuthenticatedPrincipal
    F->>A: BearerTokenAuthentication
    A-->>C: Response per permissions
    Note over C,AS: Subsequent requests may repeat the introspection call
~~~

When caching is added on the Resource Server side:

~~~mermaid
flowchart TD
    A["Bearer token T"] --> B["CachingOpaqueTokenIntrospector"]
    B --> C{"Does cache have a valid positive entry?"}
    C -- "Yes" --> D["Use previously introspected principal"]
    C -- "No" --> E["Delegate to trusted OpaqueTokenIntrospector"]
    E --> F{"Did introspection accept the token?"}
    F -- "No" --> G["Reject authentication; do not cache positive"]
    F -- "Yes" --> H["Compute reuseUntil from TTL and exp"]
    H --> I["Cache positive entry if eligible"]
    I --> J["Return OAuth2AuthenticatedPrincipal"]
    D --> J
    J --> K["Provider → Authentication → Authorization"]
~~~

A cache hit avoids a network call, yet **does not ask the Authorization Server whether the token was just revoked**. Therefore, caching must have explicit timing and revocation policies.

## 2. What Is an Introspection Result?

Under **RFC 7662**, the Authorization Server may return:

~~~json
{
  "active": true,
  "iss": "https://auth.example.com/realms/shop",
  "sub": "user-42",
  "client_id": "orders-web",
  "aud": ["orders-api"],
  "scope": "orders.read orders.export",
  "exp": 1893456000,
  "iat": 1893452400,
  "tenant_id": "t-7"
}
~~~

When the token is inactive:

~~~json
{
  "active": false
}
~~~

`active: true` reflects the Authorization Server's decision **at the moment of introspection**. It is not a guarantee that the token will remain active for the next several minutes, nor does it by itself prove the token has sufficient scopes or permission to access another tenant's resource.

Metadata in the response can vary by Authorization Server and the introspection client's permissions:

| Field | Meaning for Caching/Authorization |
| --- | --- |
| `active` | Token is active per current introspection result |
| `exp` | Token expiration time; results must not be cached past this point |
| `nbf` | Time before which the token is not yet valid, if supplied |
| `iat` | Issuance time, not cache expiration |
| `iss` | Issuer; must match configured trust domain when required by contract |
| `aud` | Target API/resource; avoids accepting tokens intended for another API |
| `scope` | Granted scopes; usually converted to `SCOPE_...` authorities |
| `sub`, `client_id` | User subject/client identity; does not establish record ownership on its own |
| `tenant_id`, `permissions` | Custom claims interpreted per agreed policy and schema |

In Spring Security, a valid `OpaqueTokenIntrospector` typically returns **`OAuth2AuthenticatedPrincipal`**, not simply raw JSON. The principal holds `getAttributes()`, `getName()`, and `getAuthorities()`. Caching at the introspector layer should store a **verified and policy-checked result**, rather than storing raw `active: true` responses and skipping permission conversion.

### JWTs Can Also Be Introspected

The term "opaque token Resource Server" usually refers to **verifying via introspection**. If the issuer supports it, a JWT access token can also be introspected instead of verified offline. TTL and revocation-lag principles still apply to **cached introspection results**, regardless of whether the token string looks like a JWT or opaque.

## 3. Distinguishing Three Kinds of Time

Let:

- `t₀`: the time the Resource Server receives a successful introspection result.
- `C`: maximum allowed cache duration, e.g., 30 seconds.
- `E`: the access token's `exp` timestamp, if provided by the issuer.
- `δ`: a safety margin before token expiration, e.g., 5 seconds.
- `R`: the time the token is revoked at the Authorization Server.

Three independent concepts:

| Concept | Measured From? | What Does It Decide? |
| --- | --- | --- |
| **Access token lifetime** | Authorization Server's issuance decision; usually via `iat` and `exp` | Whether the token is still within its validity period |
| **Cache TTL** | When the cache entry is written at the Resource Server | How long verified introspection data may be reused |
| **Revocation lag/window** | When the issuer revokes the token before the Resource Server learns of it | How long a revoked token may continue being accepted from cache |

**Cache TTL never changes the token's `exp`.** A token expiring in 10 seconds must not be cached for 30 seconds just because the configured TTL is 30 seconds.

### Reuse Deadline Formula

For a token with a trustworthy `exp`:

~~~text
reuseUntil = min(t₀ + C, E - δ)

TTL_effective = max(0, reuseUntil - t₀)
~~~

Suppose policy permits caching for 30 seconds and reserves a 5-second safety margin before `exp`:

| Token Expires In | Configured TTL | Max Effective TTL | Reason |
| --- | --- | --- | --- |
| 10 minutes | 30 seconds | 30 seconds | Cache window is the tighter bound |
| 40 seconds | 30 seconds | 30 seconds | `exp - 5s` is 35 seconds away |
| 20 seconds | 30 seconds | 15 seconds | Do not cache right up to `exp` |
| 5 seconds | 30 seconds | 0 seconds | Not enough safety margin to cache |
| Already expired | 30 seconds | 0 seconds; token must be rejected per policy | Cannot extend a token via cache |
| No trustworthy `exp` | 30 seconds | Conservative policy: do not cache | No hard bound to block expired use |

The numbers 30 seconds and 5 seconds are **design examples only**, not mandatory TTLs of OAuth 2.0 or Spring Security.

### NumericDate and the Java Type of `exp`

In JWTs and related OAuth metadata, `exp` is typically a **NumericDate: seconds since the Unix epoch**, not milliseconds. However, an introspector may convert `exp` into an `Instant` before returning `OAuth2AuthenticatedPrincipal`:

~~~java
Object rawExpiry = principal.getAttribute("exp");

if (rawExpiry instanceof java.time.Instant instant) {
    // Use instant as an absolute point in time.
}
else if (rawExpiry instanceof Number number) {
    // Treat as epoch seconds only when permitted by the issuer contract.
    java.time.Instant exp =
        java.time.Instant.ofEpochSecond(number.longValue());
}
~~~

Never assume `(Long) principal.getAttribute("exp")` always succeeds; nor call `Instant.ofEpochMilli(...)` on a NumericDate measured in seconds. For fractional NumericDates, write an exact converter matching the schema; the cache example below intentionally handles common whole-second forms conservatively.

## 4. How Is a Revocation Lag Window Created?

Suppose token T is introspected at **10:00:00**, and the Resource Server caches `active: true` with a **60-second** TTL:

~~~text
10:00:00  Introspect T -> active=true
          Cache T, authorities = [SCOPE_orders.read]

10:00:10  Authorization Server revokes T

10:00:25  Client resends T
          Resource Server cache hit -> may accept T!

10:01:00  Cache entry expires

10:01:05  Client resends T
          Resource Server introspects -> active=false -> reject
~~~

That is **revocation lag** caused by caching. With maximum TTL `C`, the worst case typically occurs when a token is revoked **right after a successful cache refresh**. When the cache only permits reuse for `C` and no other cache layer extends data age, cache-induced revocation lag can approach `C`, plus delays from in-flight requests and issuer state propagation.

~~~mermaid
sequenceDiagram
    autonumber
    participant C as Client holding T
    participant RS as Resource Server cache TTL=30s
    participant AS as Authorization Server
    C->>RS: Request with T
    RS->>AS: introspect(T)
    AS-->>RS: active=true
    RS-->>C: Allow if authorized
    Note over RS: Cache T until t0+30s or before exp
    AS->>AS: Revoke T at t0+5s
    C->>RS: Request with T at t0+10s
    Note over RS: Cache hit; unaware token was revoked
    RS-->>C: May still accept T
    C->>RS: Request after cache expires
    RS->>AS: introspect(T)
    AS-->>RS: active=false
    RS-->>C: Reject authentication
~~~

**You cannot simultaneously cache positive results independently for a significant window and guarantee every revocation takes effect immediately**, unless you have a sufficiently reliable and consistently enforced active-notification/invalidation mechanism. Even push invalidation must account for races and connection failures.

### A Note on "Exact 30-Second TTL"

A system may have multiple cache layers:

~~~text
Resource Server A: local introspection cache
Resource Server B: local introspection cache
                 |
          Shared cache (if any)
                 |
         HTTP/proxy/issuer cache
                 |
          Authorization Server
~~~

Never claim "revocation takes effect in at most 30 seconds" just because **one** in-JVM cache has a 30-second TTL. The issuer may not propagate state instantaneously; proxies or other caches may hold stale responses; in-flight requests can still finish.

**To commit to a revocation bound**, measure the entire path from the revocation action to authentication decisions across every Resource Server instance.

## 5. What to Cache and What to Avoid Caching

What to cache when eligible:

~~~text
Token T introspected successfully
    -> trusted OAuth2AuthenticatedPrincipal
       attributes + name + authorities
    -> reuseUntil computed from cache TTL and token exp
~~~

**Caching only successful results (positive caching)** is the easiest baseline strategy to control. Avoid mistakes:

| Data/Result | Conservative Starting Policy |
| --- | --- |
| Principal from `active: true` introspection, matching issuer/audience/profile | May cache briefly if well before `exp` |
| `active: false` introspection | Do not cache under the same positive policy |
| Introspection timeout, 5xx, or TLS error | Never cache as a valid token; **fail closed** |
| Token missing `exp` or wrong-typed `exp` | Do not cache without a clear lifetime contract |
| Principal missing a profile-required claim | Reject per policy; do not cache |
| Token expiring within the safety margin | Return result per current policy, yet do not cache past `exp` |
| Permissions depending on per-request membership/shares | Check current relationships separately or use dedicated invalidation |

### Should You Negatively Cache?

**Negative caching** stores `active: false` or token errors to avoid repeatedly calling the issuer. This can shed load when an attacker replays an invalid token, yet introduces its own issues:

- A token deemed inactive at `t₀` might have a different status under issuer policy, or the failure might be an infrastructure fault rather than token state.
- Caching network errors as `invalid_token` hinders diagnosis and can prolong outages.
- Risk of cache growth when an attacker sends endless distinct token strings.

If a system decides to use negative caching, it needs a **separate** policy, very short TTL, bounded capacity, and strict separation between `active: false` and network/issuer errors. This lesson focuses on **positive caching**; never assume negative caching is safe or necessary by default.

## 6. Choosing Cache Keys: Never Use Raw Access Tokens Carelessly

The simplest cache key is the token string:

~~~java
// Simple idea, but avoid in systems with logs/cache monitoring:
cache.getIfPresent(rawAccessToken);
~~~

A Bearer token is a **credential**. If the system logs cache keys, takes heap dumps, displays keys on dashboards, or places the cache in an external service, raw tokens can leak. One mitigation is using an **HMAC-SHA-256 of the token with a dedicated secret** as the cache key:

~~~text
raw bearer token
      |
      v
HMAC-SHA-256(token, cache-secret)
      |
      v
Base64URL/HMAC digest cache key
~~~

Advantages of HMAC over an unkeyed hash:

- Avoids storing the raw bearer token string directly as the key.
- When tokens lack very high entropy, the HMAC secret reduces the risk of guessing tokens from leaked hashes.
- You can rotate the HMAC secret and clear the cache during security incidents.

However, an HMAC cache key **does not encrypt principal attributes in the cached value**. User data in cached values must still be protected, access-controlled, and kept out of logs/metrics.

Cache keys must also be **partitioned by trust domain**. If the same cache serves multiple issuers, multiple introspection endpoints, multiple resource audiences, or multiple authentication policies, include those context components in the key or use a **separate cache instance per configuration**. Never let a result accepted for API A automatically serve as proof of validity for API B.

## 7. Java Example: Positive-Result Caching Decorator with Caffeine

A clean customization approach is implementing `OpaqueTokenIntrospector` and **wrapping a delegate that performs real token verification**. Spring Security calls this decorator instead of calling the remote introspector directly.

The example below makes deliberate choices:

1. Cache **only when** delegate introspection succeeds.
2. Never store raw bearer tokens in cache keys; use HMAC.
3. Use `expireAfterWrite(maxTtl)` to enforce a **hard cache age limit**, never extending on read.
4. Also verify `reuseUntil` on every hit, bounded by `exp - safetyMargin`.
5. Do not cache if `exp` is absent or cannot be interpreted in an allowed type.
6. Never swallow/lose introspection exceptions: errors still propagate to the authentication layer.
7. You may cache the principal produced from introspection, yet never use the cache to decide resource ownership relationships.

Assumes Java 17+, Spring Security Resource Server, and a build-compatible Caffeine version. Imports and code illustrate a **local in-memory positive cache**, not a Spring Security built-in implementation.

~~~java
import com.github.benmanes.caffeine.cache.Cache;
import com.github.benmanes.caffeine.cache.Caffeine;
import java.security.GeneralSecurityException;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.LinkedHashMap;
import java.util.List;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.security.oauth2.core.DefaultOAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.core.OAuth2AuthenticatedPrincipal;
import org.springframework.security.oauth2.server.resource.introspection.BadOpaqueTokenException;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

public final class PositiveCachingOpaqueTokenIntrospector
        implements OpaqueTokenIntrospector {

    private record CachedPrincipal(
        OAuth2AuthenticatedPrincipal principal,
        Instant reuseUntil
    ) {}

    private final OpaqueTokenIntrospector delegate;
    private final Cache<String, CachedPrincipal> cache;
    private final Clock clock;
    private final Duration maxTtl;
    private final Duration safetyMargin;
    private final byte[] hmacSecret;

    public PositiveCachingOpaqueTokenIntrospector(
            OpaqueTokenIntrospector delegate,
            Clock clock,
            byte[] hmacSecret,
            Duration maxTtl,
            Duration safetyMargin) {

        if (delegate == null || clock == null ||
                hmacSecret == null || hmacSecret.length < 32 ||
                maxTtl == null || maxTtl.isZero() || maxTtl.isNegative() ||
                safetyMargin == null || safetyMargin.isNegative()) {
            throw new IllegalArgumentException("Invalid cache configuration");
        }

        this.delegate = delegate;
        this.clock = clock;
        this.hmacSecret = hmacSecret.clone();
        this.maxTtl = maxTtl;
        this.safetyMargin = safetyMargin;
        this.cache = Caffeine.newBuilder()
            .maximumSize(10_000)
            .expireAfterWrite(maxTtl)
            .build();
    }

    @Override
    public OAuth2AuthenticatedPrincipal introspect(String token) {
        String key = cacheKey(token);
        Instant now = clock.instant();
        CachedPrincipal hit = cache.getIfPresent(key);

        if (hit != null && now.isBefore(hit.reuseUntil())) {
            return hit.principal();
        }

        if (hit != null) {
            // Remove only this stale entry; avoid removing a newer entry from another thread.
            cache.asMap().remove(key, hit);
        }

        // MANDATORY: delegate performs introspection and checks the token.
        // If active=false or an error occurs, never create a positive entry.
        OAuth2AuthenticatedPrincipal verified = delegate.introspect(token);

        Object rawExpiry = verified.getAttribute("exp");
        Instant expiry = expiryInstant(rawExpiry);
        now = clock.instant();

        // Unknown exp -> do not cache; policies requiring exp can
        // reject earlier inside a trusted delegate or policy validator.
        if (expiry == null) {
            return verified;
        }

        if (!now.isBefore(expiry)) {
            throw new BadOpaqueTokenException("Access token expired");
        }

        Instant safeExpiry = expiry.minus(safetyMargin);
        Instant cacheLimit = now.plus(maxTtl);
        Instant reuseUntil = safeExpiry.isBefore(cacheLimit)
            ? safeExpiry
            : cacheLimit;

        if (!now.isBefore(reuseUntil)) {
            return verified; // Too little remaining time to cache safely.
        }

        // Copy outer map/collection to avoid direct mutation.
        // If attributes contain mutable nested objects, deep-freeze/copy
        // per product schema before using a shared cache.
        OAuth2AuthenticatedPrincipal snapshot =
            new DefaultOAuth2AuthenticatedPrincipal(
                verified.getName(),
                new LinkedHashMap<>(verified.getAttributes()),
                List.copyOf(verified.getAuthorities())
            );

        cache.put(key, new CachedPrincipal(snapshot, reuseUntil));
        return snapshot;
    }

    private static Instant expiryInstant(Object raw) {
        if (raw instanceof Instant instant) {
            return instant;
        }
        if (raw instanceof Date date) {
            return date.toInstant();
        }
        if (raw instanceof Long seconds) {
            return Instant.ofEpochSecond(seconds);
        }
        if (raw instanceof Integer seconds) {
            return Instant.ofEpochSecond(seconds.longValue());
        }
        // If exp is BigDecimal/fractional or custom type, do not guess units:
        // normalize via a schema-checked converter before caching.
        return null;
    }

    private String cacheKey(String token) {
        try {
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(hmacSecret, "HmacSHA256"));
            byte[] digest = mac.doFinal(token.getBytes(
                java.nio.charset.StandardCharsets.UTF_8));
            return Base64.getUrlEncoder()
                .withoutPadding()
                .encodeToString(digest);
        } catch (GeneralSecurityException e) {
            throw new IllegalStateException("HMAC unavailable", e);
        }
    }
}
~~~

### Understanding the Limitations of This Example

This is **an implementation pattern**, not a substitute for choosing production-appropriate policies:

- **No default single-flight:** concurrent requests with the same token on a cache miss may invoke the delegate simultaneously. To prevent cache stampedes, add per-key request coalescing and ensure exceptions are never turned into cached successes.
- **In-JVM cache:** each replica maintains its own cache. Cluster-wide invalidation requires additional design.
- **Does not validate every token claim inside the caching decorator:** the delegate and trusted policy layer must still verify token state, issuer, audience, token purpose, and required constraints.
- **Missing or wrong-schema `exp`:** the example skips caching. If the profile mandates `exp`, the policy evaluator must **reject** non-compliant tokens rather than merely skipping caching.
- **`expireAfterWrite` bounds entry age by elapsed time:** cache reads do not extend data lifetime; `reuseUntil` prevents returning principals past their valid window.
- **Nested attributes:** the map copy in the example is a **shallow copy**. Never share mutable objects or mutate authorities after caching; use immutable snapshots/deep copies per schema if the app mutates attributes.
- **Cache key secret:** must be generated randomly from a secure source, never hardcoded, never logged; clear the cache if needed when rotating secrets.
- **Raw token is still sent to the delegate:** HMAC only masks the **cache key**, not making the token "anonymous" to the Authorization Server.

### Practical Formula in the Example

With `maxTtl=30s` and `safetyMargin=5s`:

~~~text
cacheLimit = now + 30s
safeExpiry = exp - 5s
reuseUntil = min(cacheLimit, safeExpiry)

Cache only if reuseUntil > now.
Every cache hit requires now < reuseUntil.
~~~

This prevents **the cache from extending token lifetime** when clocks and metadata are properly normalized. It does not prevent the issuer from revoking a token **before `exp`**: cached results can still experience revocation lag up to the TTL.

## 8. Configuring Spring Boot Resource Server to Use the Decorator

Resource Server dependency:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-resource-server</artifactId>
</dependency>
~~~

Add Caffeine matching your project version:

~~~xml
<dependency>
    <groupId>com.github.ben-manes.caffeine</groupId>
    <artifactId>caffeine</artifactId>
</dependency>
~~~

Example configuration:

~~~yaml
orders:
  introspection:
    uri: https://auth.example.com/oauth2/introspect
    client-id: orders-resource-server
    client-secret: ${INTROSPECTION_CLIENT_SECRET}
    cache-hmac-key-base64: ${INTROSPECTION_CACHE_HMAC_KEY_B64}
    max-cache-seconds: 30
    expiry-safety-seconds: 5
~~~

Introspection and HMAC secrets must be loaded from a secret manager or protected runtime configuration—never commit real values to the repository.

Bean wiring example, for **versions still providing the corresponding `NimbusOpaqueTokenIntrospector` constructor**:

~~~java
import java.time.Clock;
import java.time.Duration;
import java.util.Base64;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.server.resource.introspection.NimbusOpaqueTokenIntrospector;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;

@Configuration
class IntrospectionCacheConfiguration {

    @Bean
    OpaqueTokenIntrospector opaqueTokenIntrospector(
            @Value("${orders.introspection.uri}") String uri,
            @Value("${orders.introspection.client-id}") String clientId,
            @Value("${orders.introspection.client-secret}") String clientSecret,
            @Value("${orders.introspection.cache-hmac-key-base64}") String keyB64,
            @Value("${orders.introspection.max-cache-seconds}") long maxSeconds,
            @Value("${orders.introspection.expiry-safety-seconds}") long guardSeconds) {

        OpaqueTokenIntrospector remote = new NimbusOpaqueTokenIntrospector(
            uri, clientId, clientSecret);

        // In a real system: wrap with an introspector verifying
        // audience/issuer/client policy before wrapping with cache.
        return new PositiveCachingOpaqueTokenIntrospector(
            remote,
            Clock.systemUTC(),
            Base64.getDecoder().decode(keyB64),
            Duration.ofSeconds(maxSeconds),
            Duration.ofSeconds(guardSeconds)
        );
    }
}
~~~

**Version note:** remote introspector class names, constructors, and builders can differ across Spring Security lines; some Nimbus classes are marked deprecated in newer lines. Use the API supported in your current version, such as the Spring-based implementation when provided. **The core principle remains:** `trusted remote introspector → policy checks → positive cache decorator → Resource Server`.

Security filter chain:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.oauth2.server.resource.introspection.OpaqueTokenIntrospector;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurity {

    @Bean
    SecurityFilterChain apiChain(
            HttpSecurity http,
            OpaqueTokenIntrospector introspector) throws Exception {
        return http
            .csrf(csrf -> csrf.disable())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/health").permitAll()
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().authenticated())
            .oauth2ResourceServer(oauth2 -> oauth2.opaqueToken(opaque ->
                opaque.introspector(introspector)))
            .build();
    }
}
~~~

In this example:

- Controllers/APIs **do not cache JWT claims themselves**. Caching is attached to the introspector used by the provider.
- `SCOPE_orders.read` comes from the authorities of the principal built by the introspector. If a custom introspector does not map scopes, add the corresponding mapping.
- Disabling CSRF is reasonable only for a **stateless API authenticating with Bearer tokens**, not using automatic browser cookies/sessions. Apps with cookies must evaluate CSRF separately.
- `permitAll()` **does not disable the Bearer filter**. An invalid token sent to `/health` can still trigger authentication and be rejected, unless that route uses a separate chain/resolver by design.

### Never Cache Before Checking Audience and Issuer

If the Authorization Server introspects T and returns `active: true`, yet `aud` is `payments-api`, the Orders API must **reject the token before creating a positive cache entry**. Likewise, untrusted issuers or clients not allowed to call the Orders API must never enter the valid cache.

This is especially important when one introspection endpoint is shared across multiple resources. Place a **policy-aware decorator** before the positive cache:

~~~text
remote introspection
    -> validate active + issuer/audience/client policy
    -> map attributes and authorities per contract
    -> positive cache bounded by TTL/exp
    -> Resource Server authentication
~~~

If policy varies per request or per tenant, avoid caching an overly broad decision and reusing it in another context. In that case, cache only **issuer-confirmed token metadata** and evaluate business relationships per request in the service layer.

## 9. Caching Does Not Replace Tenant, Owner, and Object Permissions

Suppose introspection returns:

~~~json
{
  "active": true,
  "sub": "user-42",
  "scope": "orders.read",
  "tenant_id": "t-7",
  "exp": 1893456000
}
~~~

A few seconds later, the user is **removed from tenant `t-7`**. If the Resource Server caches the principal for 30 seconds, the stale scope/claim can still be reused. However, **an access token having `SCOPE_orders.read` does not mean the user is still a member of that tenant or owns a specific order**.

Separate responsibilities:

~~~text
CachingOpaqueTokenIntrospector:
    Is the token active + scopes + trusted identity?

OrderPolicy / TenantMembershipService:
    Does the actor currently still have permission in this tenant and order?

OrderRepository:
    Query by orderId AND permitted tenantId.
~~~

If near-instantaneous membership/share revocation is required, query the permission DB/service **on every request**, or use a dedicated cache invalidated whenever membership changes. Never use a long introspection TTL to keep sensitive business privileges alive by default.

### Scope Changes at the Authorization Server

An issuer can change the permissions associated with a token per server policy. If a new introspection result drops `orders.export` while a cached entry still holds `SCOPE_orders.export`, the API may keep allowing exports until the cache expires. Therefore:

- Choose cache duration based on **permission sensitivity**, not just latency.
- For high-impact operations like approving payments, bulk deletions, or exporting PII, consider **re-introspecting right at the operation** or using dedicated revocation/invalidation.
- A single token used across multiple endpoints may require a unified policy; avoid assuming "GET is low risk, POST is high risk" without inspecting actual semantics.

## 10. Strategies to Reduce Revocation Lag

| Strategy | Performance | Revocation Impact | Trade-Offs |
| --- | --- | --- | --- |
| **No caching** | Many introspection requests | Sees issuer state as early as endpoint allows | High latency and network dependency |
| **Very short positive cache TTL** | Reduces part of network load | Shorter revocation lag window | Still has a stale window; needs proper sizing |
| **Cache TTL bounded by `min(C, exp)`** | Never reuses past token expiration | Bounded by token lifetime | Does not address early revocation |
| **Push invalidation/events** | Cuts repeated requests | Can shrink lag if delivered reliably to all instances | Requires event delivery, idempotency, and race handling |
| **Shared cache + invalidation** | Cuts introspection across replicas | Single place to manage entries | Needs security, HA, issuer/policy partitioning, consistency |
| **Local cache + distributed notification** | Low latency on cache hits | Can evict local entries on revoke events | If events drop or nodes go offline, hard TTL is still needed |
| **Short TTL for sensitive permissions** | Can add fresh introspection on sensitive operations | Reduces stale window for critical flows | Adds complexity; requires clear endpoint/action boundaries |

**No strategy automatically turns caching into instantaneous revocation.** Especially with event invalidation, account for:

- Revoke events arriving before or after an in-flight introspection response.
- Nodes losing connectivity while events are broadcast.
- Newly started nodes vs. older nodes that missed an event.
- Issuers with multiple regions/replicas propagating revocation state asynchronously.

A hard TTL remains a **final safety bound** when notifications fail.

## 11. Why Can Caching Slow Down Revocation Refresh Even More?

An anti-pattern is using an **expire-after-access** cache:

~~~java
// NOT suitable if you want introspection data age
// strictly bounded from fetch time.
Caffeine.newBuilder()
    .expireAfterAccess(Duration.ofMinutes(5));
~~~

With `expireAfterAccess`, every cache hit extends retention if the token keeps being sent frequently. A revoked token continuously replayed by an attacker could be reused far longer than what operators expect from a "5-minute TTL."

Prefer **absolute age since introspection**, such as `expireAfterWrite` or `reuseUntil`, never resetting just because the token is sent again.

### Treating Every Request as a "Refresh" Is Wrong

A cache hit is not the Authorization Server confirming the token is still active. Never update `validatedAt = now` on a cache hit if you want to measure age from **the last introspection**.

~~~text
lastVerifiedAt = time the result was actually confirmed by the issuer
lastUsedAt     = time the token was most recently sent to the API by a client

Never use lastUsedAt to extend lastVerifiedAt.
~~~

To bound the revocation window, `reuseUntil` must be calculated from **when the trusted result was received**, not from the latest cache access.

## 12. Timeouts, Fail Closed, and Caching During Outages

If the introspection endpoint experiences issues, the Resource Server may see:

- DNS, TLS, or connect/read timeouts.
- HTTP 429, 5xx, or invalid responses.
- Revoked/wrong introspection credentials.
- Authorization Server state synchronization lag.

Scenarios:

| Cache State | Introspection Endpoint | Safe Behavior |
| --- | --- | --- |
| **Cache hit**, entry still before `reuseUntil` | No issuer call needed on that request | May use cached principal under accepted revocation-lag policy |
| **Cache miss** | Healthy, returns active | Check policy and optionally positive-cache |
| **Cache miss** | Returns inactive | Reject token; create no positive entry |
| **Cache miss** | Timeout/5xx | No trustworthy result; **do not let through** |
| **Cached entry expired** | Timeout/5xx | Do not extend entry just because issuer failed, unless an approved stale-on-error policy exists |
| **Token reached `exp`** | Any | Never use cache to extend token lifetime |

**Fail closed** means not accepting tokens unverified under policy. It does not mean every infrastructure error must be reported as `401 invalid_token`; HTTP responses depend on handlers/implementations and how token errors are distinguished from service faults.

### Stale-While-Error Is Highly Sensitive

A system might want to serve stale cache entries during an issuer outage to preserve availability. That is a separate risk decision: tokens may have been revoked, scopes narrowed, or the issuer may be mitigating a security incident.

Never implement by default:

~~~java
// DO NOT DO THIS FOR ALL ERRORS:
// try introspection, catch Exception -> return cached principal forever
~~~

If stale-on-error is genuinely approved, enforce an absolute staleness cap, never exceed `exp`, limit which low-risk endpoints/actions qualify, log/audit usage, and support a kill switch when token compromise is suspected. For sensitive operations, **never accept expired cache entries as a default fallback**.

## 13. Performance, Cache Stampedes, and Resource Limits

Suppose an API handles 2,000 requests/second with only 50 active tokens in use. A short-TTL positive cache can cut introspection calls dramatically because each token is re-verified periodically rather than on every request.

However, cache effectiveness depends on traffic distribution:

- **Many repeated requests with the same token:** high cache hit rate.
- **Many single-use tokens:** low cache hit rate; memory spent on rarely reused entries.
- **Very short token TTLs:** effective cache window is bounded by `exp`.
- **Multiple replicas:** each replica has its own cache and may introspect the same token at different times.
- **Concurrent cache misses:** multiple threads calling the issuer simultaneously for one or many tokens.

In the Java example in Section 7, `getIfPresent → delegate → put` can cause a **cache stampede** on the same key when many requests arrive at once. A production version can add **single-flight / per-key request coalescing**, provided it:

1. Shares only **an in-progress verification result**, never accepting the token before the delegate returns success.
2. Never turns timeouts/exceptions into cached principals.
3. Bounds the number of waiting requests to avoid holding threads indefinitely.
4. Never holds a global lock across introspection calls, which would block unrelated tokens.
5. Partitions cache keys by issuer/policy in multi-source systems.

### Bounding Entry Counts

Attackers can send thousands of garbage tokens, stressing introspection even without positive caching. Enforce rate limiting, timeouts, right-sized connection pools, and API-layer protections. Bound cache entry counts, eviction, and memory budgets. Never use raw token strings or unbounded digests as **metric labels**, which bloat monitoring cardinality.

## 14. Caching Across Multiple Resource Server Instances

Suppose the Orders API runs across three replicas:

~~~text
Client
  |
Load Balancer
  |
  +-- API instance A -> local cache A
  +-- API instance B -> local cache B
  +-- API instance C -> local cache C
                          |
                   Introspection endpoint
~~~

The same token T may be:

- Cached on A at 10:00:00.
- Cached on B at 10:00:10.
- Cached on C at 10:00:20.

If T is revoked at 10:00:25 with a 30-second TTL, the instances hold different cache timestamps. **When revocation takes effect cluster-wide depends on the last cache entry verified before revocation**, plus issuer propagation. Therefore, testing against one instance is not enough to conclude the whole cluster rejects the token.

With distributed caches, account for:

- Cached principal values may contain sensitive metadata; encrypt transport and restrict access.
- Serializers/deserializers must preserve authorities and temporal types accurately.
- Cache keys should be partitioned by issuer, audience, and tenant/policy when appropriate.
- Invalidation must reach all nodes or all entries sharing the key.
- Redis/distributed caches can experience consistency lag or network failures; never fall back to accepting unverified tokens.
- Distributed cache TTLs and local cache TTLs must be budgeted together so stacked layers do not multiply the revocation window.

Never share one principal cache across Resource Servers with **different audience or authority-mapping policies** merely because the bearer token string is identical.

## 15. Observing Caching and Testing Revocation Behavior

Useful signals:

| Metric/Signal | Meaning |
| --- | --- |
| Cache hit/miss by issuer and application | Measures whether caching actually reduces introspection |
| Introspection requests per second | Load on issuer and token reuse ratio |
| P50/P95/P99 introspection latency | Latency impact on requests |
| Introspection timeouts/5xx/429 | Network/issuer incidents |
| `active=false` counts by broad category | Rejected token volume |
| Entry age on cache hits | Detects overly stale cached data or buggy renewal |
| Time from revocation until all instances reject | End-to-end measured revocation lag |
| Rejection rate due to missing scope/tenant | Separates token verification from business permissions |

Never log **raw access tokens**, HMAC secrets, or full introspection responses. You may log request IDs, verified issuers, error categories, authentication outcomes, and cache hit/miss; keep cardinality and identifying data bounded.

### Mandatory Test Matrix for Cache Implementations

Assuming policy max TTL 30 seconds, safety margin 5 seconds:

| Scenario | Expected Behavior |
| --- | --- |
| First active T, `exp` far away | Delegate called, positive entry stored |
| Repeated T within TTL | Cache hit, delegate not called again |
| After 30s TTL | Cache miss, introspection called again |
| Token expires in 20s | Cached only until ~5s before `exp` |
| Token expires in 4s | Not cached; not reused past `exp` |
| Introspection returns inactive | Reject; no positive cache entry created |
| Introspection timeout/5xx | Fail closed; never stored as active token |
| Token revoked within TTL | May still be accepted until entry expires |
| Token revoked after cache expires | Next check must reflect issuer state |
| Issuer changes scope/permissions | Cache hit may retain old authorities until TTL expires |
| Token missing `exp` under no-cache policy | Delegate called per request; profile validator decides acceptance |
| Same token across different issuer/policy caches | Cached principals never leak across contexts |
| Concurrent requests on cache miss | Verify load/stampede behavior and concurrency bounds |
| Multiple replicas with staggered TTLs | Measure revocation lag across all instances, not just one node |

### Testing Boundary Conditions Without `Thread.sleep`

To test `reuseUntil` logic, inject `Clock.fixed(...)` or a **MutableClock** in unit tests. Caffeine's `expireAfterWrite` uses its own elapsed-time ticker, so advancing `Clock` alone does not expire Caffeine entries. When testing actual Caffeine TTLs, configure a **fake ticker** on Caffeine or test time logic and cache expiry separately.

Example test plan skeleton:

~~~java
// Pseudocode / test plan:
// 1. Fake delegate returns principal with exp = T + 20s.
// 2. Set Clock to T.
// 3. introspect("T") -> delegateCalls == 1, positive cached until T+15s.
// 4. Advance Clock to T+10s; introspect("T") -> cache hit.
// 5. Advance Clock to T+16s; introspect("T") -> calls delegate again.
// 6. Have delegate report inactive; introspect("T") must fail.
//
// Separately test Caffeine expireAfterWrite(30s) with a fake ticker
// to verify elapsed-time eviction.
~~~

### Decorator Unit Tests Do Not Replace End-to-End Revocation Tests

A fake introspector returning a hand-built principal only proves **how the cache behaves**; it does not prove:

- Introspection connections use proper TLS and credentials.
- `active: false` responses are handled properly by the remote introspector.
- `exp`, `scope`, and `aud` claims are converted to the right types.
- The real filter chain builds `BearerTokenAuthentication` and returns appropriate 401/403 codes.
- Revocation events propagate between the issuer and instances.

When deploying, run integration tests against a test introspection endpoint / HTTP stub, tokens managed by a test Authorization Server, and requests flowing through the **real `SecurityFilterChain`**. Spring Security Test's `opaqueToken()` post-processor normally builds a test Authentication and **bypasses the real introspector/cache**, so it does not verify revocation lag.

## 16. When Should You Not Cache Introspection Results?

Situations to avoid positive caching or use a tiny TTL:

- Systems requiring **near-instantaneous access token revocation**, such as sensitive financial transactions.
- Token/authorization state changes frequently and access decisions must reflect changes immediately.
- Introspection responses lack expiration or the token profile does not supply a trustworthy `exp`.
- A shared cache is proposed across multiple issuers/resources with inconsistent policies.
- Sensitive principal data in caches/dumps/logs cannot be adequately protected.
- No fallback protection exists when the issuer is down and cache entries expire.
- Cache hit ratios are low because tokens are rarely reused.

**No caching** is a valid security choice. It increases network requests while eliminating cache-induced stale introspection. Even without caching, revocation timeliness still depends on when the Authorization Server publishes state changes and request processing latency.

## 17. Common Misconceptions

**"A token has 15 minutes left until `exp`, so caching introspection for 15 minutes is safe."**  
No. Tokens can be revoked or have permissions modified before `exp`. Caching needs its own cap based on acceptable revocation lag.

**"A 30-second cache TTL causes JWTs or opaque tokens to expire after 30 seconds."**  
No. TTL only controls how long **introspection results are reused**. Token lifetime is governed by the Authorization Server and metadata.

**"`active: true` means the result can be reused all the way until `exp`."**  
No. `active: true` is a snapshot at the moment of introspection, not an immutable guarantee.

**"If `exp` is present, checking revocation is unnecessary."**  
No. `exp` is a maximum lifetime, while revocation can happen earlier.

**"A cache hit means the token was just re-verified."**  
No. A cache hit merely reuses an earlier decision. `lastUsedAt` must not be treated as `lastVerifiedAt`.

**"Expire-after-access is good because active tokens should stay cached longer."**  
Not when the goal is bounding revocation lag. Steady token activity can keep an entry alive longer than intended.

**"When the introspection endpoint errors, use expired cached results to avoid 401s."**  
That is stale-on-error and requires explicit risk approval; never extend TTLs indefinitely or past `exp` by default.

**"Using SHA-256 of the token as the key solves all cache security."**  
No. Keyed HMAC helps protect keys in some scenarios, yet you must still protect cached values, memory, persistence, endpoints, multi-issuer separation, and logs.

**"A cached principal with `SCOPE_orders.read` is enough to read any order."**  
No. Ownership, tenant membership, sharing, and resource permissions must still be checked by business logic.

**"Spring Security enables a positive cache for all opaque tokens by default."**  
Do not assume this. Caching behavior depends on implementation, version, and configuration. When you need specific TTL/revocation policies, configure an application-managed introspector or cache layer and verify the runtime path.

## 18. Decision Framework for Designing Introspection Caching

Before enabling positive-result caching, establish:

1. **Who verifies the token?** Introspect only at trusted issuer endpoints; protect credentials and TLS.
2. **Which token policies must pass?** `active`, issuer, audience, access-token purpose, expiration, client, and required claims.
3. **What result is cached?** Verified positive principals with mapped authorities; never cache network errors as successes.
4. **What is the maximum TTL?** Choose from revocation-lag requirements, not performance metrics alone.
5. **Is there a trustworthy `exp`?** Use `reuseUntil=min(now+C, exp-δ)`; if missing, skip caching or enforce a stricter policy.
6. **Are there other caches?** Local JVM, shared caches, proxies, or the issuer can all affect staleness.
7. **How are cache keys protected?** Never log raw tokens; prefer HMAC keys with dedicated secrets and issuer/policy partitioning.
8. **Who revokes business permissions?** Membership, ownership, sharing, and sensitive actions need dedicated checks/invalidation.
9. **How are network errors handled?** Cache misses and introspection errors must fail closed; stale-on-error requires an explicit security decision.
10. **Where is revocation lag tested?** Test end-to-end from the Authorization Server to every Resource Server instance, covering TTLs, cache expiry, and propagation.

**Key takeaway:** Introspection caching reduces latency and load on the Authorization Server, yet every positive cache hit **re-trusts an old decision**. Safe rules are **cache briefly, bound by `exp`, never extend on access, never cache errors as successes, protect cache keys/values, preserve validation, and enforce business authorization**. The revocation lag window must be **an explicitly designed, measured, and accepted trade-off**, not an overlooked side effect of performance tuning.
