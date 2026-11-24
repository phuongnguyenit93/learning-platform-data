# StatelessTicketCache, Lifetimes, and Reuse Limits for Cached Proxy Authentication Results in Spring Security CAS

**Problem:** A CAS Proxy Ticket (**PT**) under the Central Authentication Service (**CAS**) protocol is valid for only **one validation attempt** at the CAS Server and is issued for **one specific service**. In a stateless application, a client makes multiple API calls without an `HttpSession`, so if it resends the same PT and the backend asks CAS every time, subsequent calls will receive `INVALID_TICKET`. Spring Security provides **`StatelessTicketCache`** to store a **successfully validated `CasAuthenticationToken`** and let the server reuse that result for a bounded window.

**Key takeaway:** **CAS does not turn a PT into a multi-use ticket.** The PT is consumed by CAS during the first validation. Having the client reuse the same PT string against the backend is **Spring Security reusing a locally cached Authentication**, not CAS re-validating on every request. This improves performance yet **turns the cached PT into a replayable bearer credential at the app itself**, requiring short TTLs, service/proxy-chain/tenant controls, per-request authorization, and revocation mechanisms.

This lesson belongs to **Spring Security – federation → CAS Proxy**, focusing on `StatelessTicketCache`, cache lifecycles, `SpringCacheBasedTicketCache` and `NullStatelessTicketCache`, reuse limits, lifetimes, risk controls, runnable Spring Security and Java 17 examples, testing, and runbooks.

## 1. From SSO to CAS Proxy: Why Is a PT Needed?

In regular web browser SSO:

1. Browser visits Portal A and is redirected to CAS `/login`.
2. CAS authenticates the user and issues a **Service Ticket (ST)** for Portal A.
3. Portal A calls `/serviceValidate` to check the ST; upon success, Portal creates a local session.
4. Browser uses Portal's session cookie for subsequent requests.

However, when Portal A needs to access backend Service B **on behalf of the user**, Portal's cookie is not evidence B can trust for the user; B needs a credential scoped to B.

~~~text
Browser                   Portal A                  CAS                   API B
   |                         |                      |                     |
   |--- CAS Login ---------->|--- validate ST ----->|                     |
   |                         |<-- Assertion + PGT --|                     |
   |                         |                      |                     |
   |--- View data ---------->|--- /proxy(PGT,B) --->|                     |
   |                         |<------ PT-B ---------|                     |
   |                         |--- API + PT-B ---------------------------->|
   |                         |                      |<--- /proxyValidate -|
   |                         |                      |--- authentication ->|
   |                         |<------------------ API response -----------|
~~~

A **Proxy-Granting Ticket (PGT)** lets Portal A request **dedicated PTs for service B**. B validates PT-B with CAS, checks the proxy chain, and enforces local authorization before returning data.

**Do not confuse:**

| Credential | Function | Reusable per CAS Protocol? |
| --- | --- | --- |
| ST | User logs into one exact service | **No**, one-time validation |
| PT | Service A accesses service B on user's behalf | **No**, one-time validation |
| PGT | Service A requests PTs for permitted backends | **Yes**, within allowed lifetime/policy |
| TGT | User's CAS SSO session | **Yes**, for CAS to issue tickets per policy |
| TGC | CAS browser cookie identifying SSO session | Sent by browser back to CAS; never sent directly to API B |
| Cached `CasAuthenticationToken` | **Already-succeeded** authentication result at B | **May** be reused by B per cache policy |
| OAuth access token | API credential under OAuth2 | Distinct mechanism from CAS; not equivalent to PT |

**Each PT must still be issued for a specific backend service and validated once**; PGT/PT are never blanket administrative privileges.

## 2. Apparent Contradiction: Single-Use PT Yet Stateless Backend Accepts the Same PT Multiple Times?

Both statements are true, because they operate at **different layers**.

**CAS Protocol layer:** The PT is minted by the CAS Server for service B, has a short lifetime, and is validated **once**. If B calls `/proxyValidate` with that PT a second time, CAS rejects it.

**Spring Security application layer:** B stored a **successful validation result** in `StatelessTicketCache`. When the client resends that exact PT, `CasAuthenticationProvider` can retrieve the **`CasAuthenticationToken` from cache** without calling CAS again.

~~~text
Request 1: PT-X -> API B -> cache MISS
                          -> CAS /proxyValidate(PT-X,B)
                          -> SUCCESS, PT-X consumed at CAS
                          -> CasAuthenticationToken
                          -> cache.put(PT-X, auth)
                          -> process request

Request 2: PT-X -> API B -> cache HIT
                          -> retrieve authenticated auth
                          -> DO NOT call CAS
                          -> process request if still authorized

Request 3: PT-X -> API B -> cache entry EXPIRED
                          -> attempts CAS validation again
                          -> CAS rejects already-consumed PT-X
                          -> must request a FRESH PT
~~~

**Never equate “PT is still valid at CAS” with “cache entry is still alive at B.”** CAS already invalidated the PT under single-use rules; the app holds an **independent cached authentication result** for a short window.

### What Does Stateless Mean Here?

The client does not rely on an `HttpSession` across requests; however, if B uses a cache, **the backend still keeps a small amount of state**: a `ticket ID → Authentication` map. It is **stateless with respect to client/server HTTP sessions**, not zero-state.

## 3. Why Does Spring Security Provide `StatelessTicketCache`?

Per Spring Security Javadoc, `StatelessTicketCache` caches authentication results for **stateless connections**, including CAS service/proxy tickets. When a request presents an unseen ticket, the backend validates it with CAS and creates a `CasAuthenticationToken`. That token is cached by the ticket string; repeat submissions can retrieve the already-succeeded token from cache.

Goals:

- No browser session/cookie needed for service-to-service calls.
- Avoid requesting a fresh PT for **every single** API request in a short burst of calls.
- Reduce CAS validation network latency and CAS Server load.
- Preserve verified principal/authorities for the backend.
- Provide a short usage window when multiple requests follow one validation.

**Limitations:** caching does not magically verify that the user is still active, the PGT has not been revoked, groups have not changed, the current service matches the originally validated service, or the ticket was not stolen. Those properties require additional policies and checks.

## 4. Core API Classes and Methods

| Class / Interface | Role |
| --- | --- |
| `org.springframework.security.cas.authentication.StatelessTicketCache` | Contract for caching stateless CAS authentication results |
| `SpringCacheBasedTicketCache` | Adapter storing `CasAuthenticationToken` in an `org.springframework.cache.Cache` |
| `NullStatelessTicketCache` | Stores no entries; always misses, used when caching is unwanted |
| `CasAuthenticationProvider` | Decides cache lookup vs. `TicketValidator` and produces `Authentication` |
| `CasAuthenticationToken` | Succeeded `Authentication` holding credentials, principal, authorities, and assertion |
| `CasServiceTicketAuthenticationToken` | Authentication request token for CAS tickets in modern versions |
| `CasAuthenticationFilter` | Extracts `ticket` from requests and invokes `AuthenticationManager` |
| `ServiceProperties` | Configures service URL and `authenticateAllArtifacts` |
| `ServiceAuthenticationDetailsSource` | Supplies per-request service URL when handling tickets across multiple URLs |
| `Cas20ProxyTicketValidator` | Validator calling CAS proxy validation endpoint and checking proxy chains |

`StatelessTicketCache` methods:

~~~java
CasAuthenticationToken getByTicketId(String serviceTicket);
void putTicketInCache(CasAuthenticationToken token);
void removeTicketFromCache(String serviceTicket);
void removeTicketFromCache(CasAuthenticationToken token);
~~~

**Explanation:**

- `getByTicketId(...)`: returns the cached token or `null` if absent.
- `putTicketInCache(...)`: stores the token keyed by `CasAuthenticationToken.getCredentials()`, i.e., the ticket string.
- `removeTicketFromCache(String)`: removes a ticket from the cache to terminate local reuse.
- `removeTicketFromCache(token)`: removes by the stored token's credentials.

These operations **do not revoke TGT/PGT/PT at the CAS Server** and are not a global CAS logout API. `removeTicketFromCache` affects **the service's own cache**, not credentials across the federation.

## 5. `NullStatelessTicketCache`: The No-Cache Option

`NullStatelessTicketCache` is an implementation with no backing store:

- `getByTicketId` always returns `null`.
- `putTicketInCache` is a no-op.
- `removeTicketFromCache` is a no-op.
- This is the default choice on `CasAuthenticationProvider` in Spring Security Javadoc.

**Consequence:** if a client resends the **same** PT after its first use, the provider calls CAS validation again and gets rejected per CAS single-use rules. That can be **desired behavior** when security requires **a fresh ticket per request**, rejecting bearer replay at the service.

~~~java
// Configuration fragment on Spring Security CAS provider:
casAuthenticationProvider.setStatelessTicketCache(
        new NullStatelessTicketCache());
~~~

This is an **illustrative configuration snippet**; the provider bean must be fully wired with `TicketValidator`, `ServiceProperties`, user details, and `AuthenticationManager`/filter. Use the matching `spring-security-cas` dependency version.

**When to pick Null:** low request volume, acceptable CAS latency, strict no-ticket-reuse requirement, ability to mint a fresh PT per request, and desire not to hold `Authentication` snapshots in cache. Even without caching, you still need rate limits, TLS, and exact service/proxy-chain validation.

## 6. `SpringCacheBasedTicketCache`: An Adapter That Does Not Decide TTL Itself

`SpringCacheBasedTicketCache` accepts a **Spring `Cache`** via its constructor. It delegates `StatelessTicketCache` put/get/remove calls to that backing store.

~~~java
// An org.springframework.cache.Cache whose TTL is configured
// through the cache provider:
Cache cache = cacheManager.getCache("casProxyAuth");
StatelessTicketCache tickets =
        new SpringCacheBasedTicketCache(cache);
~~~

This is a Spring configuration snippet, not a standalone class. Ensure `cache` is non-null. **Whether the cache supports timeouts, eviction, distributed storage, serialization, encryption at rest, or max size is governed by the cache provider**, not by a TTL parameter on `StatelessTicketCache`.

**Warning:** `ConcurrentMapCache` or `ConcurrentMapCacheManager` by default **provides no time-based TTL** like an expiring cache. Using them in production without another bound lets an authentication live indefinitely. Wrapping `ConcurrentMapCache` inside `SpringCacheBasedTicketCache` **does not** enforce expiration.

### Common Cache Providers

| Provider | Guidance | Notes |
| --- | --- | --- |
| **Caffeine** | Local in-memory TTL, max size, eviction | Each node has a separate cache; handle multi-node revocation |
| **Redis + Spring Cache** | Supports TTL and sharing across nodes | Secure transport/credentials/serialization; verify invalidation |
| **JCache/Ehcache** | Per-cache expiry policies | Check compatibility with your Spring/Security versions |
| **ConcurrentMapCache** | Simple experimentation only | No built-in TTL; never use by default for production auth caches |
| **NullStatelessTicketCache** | No caching | Resending old PTs is rejected by CAS |

Never assume a config line like `cacheName=casProxyAuth` implies a TTL exists. Always inspect the actual provider implementation and expiry policy.

## 7. Configuring Stateless Flows in Spring Security CAS

Spring Security documentation explains that `CasAuthenticationProvider` distinguishes stateful vs. stateless authentication requests; stateless flows use the special identifier **`CasServiceTicketAuthenticationToken.CAS_STATELESS_IDENTIFIER`** in modern versions (or a similarly named constant on `CasAuthenticationFilter` in older docs).

To accept CAS tickets across multiple URLs (beyond the `/login/cas` browser callback), pay attention to:

1. `ServiceProperties.authenticateAllArtifacts = true`.
2. `CasAuthenticationFilter` using that `ServiceProperties`.
3. `ServiceAuthenticationDetailsSource` creating details carrying the request's exact service URL.
4. `AuthenticationManager` routing tokens to the right `CasAuthenticationProvider`.
5. Provider using a **proxy-capable `TicketValidator`** and an approved proxy-chain policy.
6. Provider configured with `StatelessTicketCache` with proper TTL/eviction if reuse is needed.
7. Filter chain scoped strictly to URLs and methods genuinely using CAS PTs.
8. Every API still enforcing its own authorization post-authentication.

~~~text
HTTP /api/orders?ticket=PT-X
            |
  CasAuthenticationFilter
    authenticateAllArtifacts=true
    identify stateless request
            |
  CasServiceTicketAuthenticationToken
      credentials=PT-X
      details=service URL
            |
  CasAuthenticationProvider
        |
        +-- cache.getByTicketId(PT-X)
        |       |
        |       +-- hit -> existing CasAuthenticationToken
        |
        +-- miss -> Cas20ProxyTicketValidator
                  /proxyValidate(ticket=PT-X, service=...)
                  -> verify permitted proxy chain
                  -> load UserDetails/authorities
                  -> cache.put(...)
            |
  Spring SecurityContext for request
            |
  Endpoint + method/object authorization
~~~

**Note:** If a request already has an `Authentication`, the filter may skip processing a new ticket depending on chain and config. Explicitly test multiple filter chains, bearer/session mechanisms, and filter ordering; never let another user's prior authentication be reused unintentionally.

## 8. Spring Boot 3 / Spring Security 6.x Example: Short-TTL Cache with Caffeine

The example below illustrates a **configuration fragment** for a Servlet app using `spring-security-cas` and **Spring Cache + Caffeine**. It is not a standalone Java program and cannot run without `TicketValidator`, CAS service registry entries, the authentication filter, user details, and a `SecurityFilterChain`.

Example goal: cache CAS proxy authentication results for at most **2 minutes from write time** and cap entry count. **Two minutes is purely illustrative, not a universal default or recommendation for every product.**

File `src/main/java/com/example/security/CasProxyCacheConfig.java`:

~~~java
package com.example.security;

import java.time.Duration;
import java.util.Objects;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.security.cas.authentication.SpringCacheBasedTicketCache;
import org.springframework.security.cas.authentication.StatelessTicketCache;

@Configuration
public class CasProxyCacheConfig {

    @Bean("casProxyCacheManager")
    CacheManager casProxyCacheManager() {
        CaffeineCacheManager manager =
                new CaffeineCacheManager("casProxyAuth");

        manager.setCaffeine(Caffeine.newBuilder()
                .maximumSize(10_000)
                .expireAfterWrite(Duration.ofMinutes(2)));

        return manager;
    }

    @Bean("casStatelessTicketCache")
    StatelessTicketCache casStatelessTicketCache(
            @Qualifier("casProxyCacheManager") CacheManager manager) {
        Cache cache = Objects.requireNonNull(
                manager.getCache("casProxyAuth"),
                "CAS proxy cache must be configured");

        return new SpringCacheBasedTicketCache(cache);
    }
}
~~~

To compile inside a matching Spring project, you need:

- Compatible **Spring Security CAS** and CAS Java Client dependencies.
- `spring-context-support`/Spring Cache abstraction matching the Spring BOM.
- **Caffeine** library (`com.github.ben-manes.caffeine:caffeine`).
- Spring Boot 3.x / Spring Security 6.x and Java 17+.
- `@Qualifier("casStatelessTicketCache")` on the provider bean if other caches exist.

### Why `expireAfterWrite` Instead of `expireAfterAccess`?

`expireAfterWrite` enforces an **absolute age cap from write time**. Using `expireAfterAccess` without a secondary maximum age allows a caller sending the PT continuously to extend the `Authentication` snapshot indefinitely, defeating reuse limits.

If an idle timeout is also needed, combine an **absolute TTL** with an idle cap—verifying the provider supports it and testing that **max lifetime is never extended by cache hits**.

**Caffeine `maximumSize` caps entry count, not how many times a PT can be used.** Enforcing “at most N requests” requires a separate atomic counter/policy.

## 9. Wiring `StatelessTicketCache` into `CasAuthenticationProvider`

Bean wiring example assuming `ServiceProperties`, `TicketValidator`, and `AuthenticationUserDetailsService<CasAssertionAuthenticationToken>` are already provided in a trusted CAS context:

~~~java
@Bean
CasAuthenticationProvider casProxyProvider(
        ServiceProperties serviceProperties,
        TicketValidator proxyTicketValidator,
        AuthenticationUserDetailsService<CasAssertionAuthenticationToken>
                casUsers,
        @Qualifier("casStatelessTicketCache")
        StatelessTicketCache statelessTicketCache) {

    CasAuthenticationProvider provider =
            new CasAuthenticationProvider();

    provider.setServiceProperties(serviceProperties);
    provider.setTicketValidator(proxyTicketValidator);
    provider.setAuthenticationUserDetailsService(casUsers);
    provider.setStatelessTicketCache(statelessTicketCache);
    provider.setKey("api-b-cas-provider-v1");

    return provider;
}
~~~

**This is a code fragment inside a Spring `@Configuration`, not a standalone runnable class.** Corresponding imports:

- `org.springframework.security.cas.authentication.CasAuthenticationProvider`
- `org.springframework.security.cas.authentication.CasAssertionAuthenticationToken`
- `org.springframework.security.cas.ServiceProperties`
- `org.springframework.security.core.userdetails.AuthenticationUserDetailsService`
- `org.apereo.cas.client.validation.TicketValidator`

The provider must be registered in the `AuthenticationManager` used by `CasAuthenticationFilter`. You still need a `SecurityFilterChain`, a CAS entry point if serving browser logins, URL matching, error responses, cache invalidation, and live CAS infrastructure. **Never assume declaring the provider bean alone enables CAS PTs end-to-end.**

### `TicketValidator` Must Enforce the Proxy Chain

`Cas20ProxyTicketValidator` from CAS Java Client is the standard validator for proxy tickets. It provides **`allowedProxyChains`** and **`acceptAnyProxy`** in applicable versions.

**Production:** trust only approved proxy chains. **Never copy** tutorial snippets with `acceptAnyProxy=true` into production, as that vastly expands who may delegate user authentication.

Proper configuration must enforce:

- CAS Server HTTPS and TLS certificate trust.
- Ticket bound to exact service B.
- Proxy chain containing exact Portal A with no unknown proxies.
- CAS Service Registry permitting A to proxy to B.
- CAS validation timeouts.
- Valid XML/subject/attributes response.
- Account/tenant authorization on B.

## 10. `ServiceProperties.authenticateAllArtifacts` and Dynamic URLs

For standard browser CAS login, the filter handles `/login/cas`. For proxy authentication to a stateless backend, tickets may accompany requests to other URLs, so Spring docs show enabling:

~~~java
ServiceProperties properties = new ServiceProperties();
properties.setService("https://api.example.test/login/cas");
properties.setAuthenticateAllArtifacts(true);
~~~

**This is a partial setup**, while the service URL used during proxy validation can be resolved dynamically via `ServiceAuthenticationDetailsSource`:

~~~java
CasAuthenticationFilter casFilter = new CasAuthenticationFilter();
casFilter.setServiceProperties(properties);
casFilter.setAuthenticationDetailsSource(
        new ServiceAuthenticationDetailsSource(properties));
casFilter.setAuthenticationManager(authenticationManager);
~~~

**Skeleton wiring only**—it omits filter-chain positioning, endpoint matchers, proxy validator, and security context persistence. Check the Javadoc of your exact version.

**Security concern:** When `ServiceAuthenticationDetailsSource` derives the service URL from incoming HTTP requests, never trust attacker-spoofable `Host`, `X-Forwarded-Host`, scheme, or path values. The CAS service URL must match the registered service and public HTTPS origin; rely strictly on trusted reverse proxies and host allowlists.

**Never enable `authenticateAllArtifacts` application-wide** when only a subset of APIs needs CAS tickets. Restrict it to the exact filter chain/paths so `ticket` query params on other URLs do not unexpectedly trigger authentication.

## 11. Critical Risk: Cache Keyed by Ticket, Not Keyed by Service by Default

Per Javadoc, `SpringCacheBasedTicketCache` stores `CasAuthenticationToken` keyed by the **ticket string** from `token.getCredentials()`. `getByTicketId(String)` takes no `serviceUrl`, `tenantId`, or `proxyChain` parameter.

**Consequence:** If the same provider/cache instance receives the same ticket across **multiple URLs**, a cache hit can return an `Authentication` validated for an earlier URL **without re-calling CAS** for the current URL. Spring Security CAS docs explicitly note that a cached PT can be accepted at another URL once the backend has validated it once.

Example:

~~~text
PT-X issued by CAS for:
  service=https://api.example.test/payments

Request 1: /payments?ticket=PT-X
  cache MISS -> CAS validates for payments -> SUCCESS -> caches PT-X

Request 2: /admin?ticket=PT-X
  cache HIT -> old authentication may be reused
  if sharing the same cache/provider/filter without other checks

=> CAS never gets a chance to reject service mismatch on Request 2.
=> API MUST independently enforce authority and endpoint scope.
~~~

**Never treat “CAS only issued the PT for `/payments`” as sufficient proof** if `/admin` can accept the same cached `Authentication` out of scope. This is the single most important trust boundary of `StatelessTicketCache`.

### Controls

1. **Separate filter chains/providers/caches** by service trust domain when distinct scopes are needed.
2. Enable CAS proxy ticket processing strictly on **the exact API endpoints**.
3. Check service identity and intended audience **before honoring cached authority** via an explicit policy.
4. Bind permissions at API/method/object level; a cached `Authentication` proves identity/granted authorities, not permission to hit every URL.
5. With multiple tenants/issuers/proxy chains, design explicit cache/trust-context namespacing; never share one cache across incompatible realms.
6. If cache keys must incorporate **ticket + trusted service + trusted tenant**, implement a wrapper/custom cache with trusted context wired properly into the provider; **the standard `StatelessTicketCache` interface accepts only a ticket string**, so merely tweaking Caffeine config to use a composite key will not work on its own.
7. Where scope cannot be guaranteed, prefer **no caching** or switch to a better-suited backend authentication mechanism.

**Separating users/tenants via unverified query parameters is insufficient.** Trusted context must come from server-side registration, routing/authorization, and policy.

## 12. Proxy Chain Scope: Who May Represent Whom?

CAS Proxy Authentication lets app A call backend B on a user's behalf. When `/proxyValidate` succeeds, the response can contain the proxies in the delegation chain.

~~~text
User -> Portal A -> Service C -> API B
          |             |
       Proxy 1       Proxy 2

CAS /proxyValidate(PT-B) -> principal + proxy chain
~~~

If B permits direct proxying only from Portal A yet receives a ticket from unapproved Proxy X, B must reject even if the ticket and subject appear valid.

**Policy questions to answer:**

- Which exact proxy URLs are trusted?
- How long may a proxy chain be?
- Is forwarding through intermediary proxies permitted?
- Does Service B allow direct STs or only PTs via A?
- Is a specific authentication method/MFA/context required?
- Are there user/tenant/resource restrictions per proxy caller?
- How is proxy registration revocation handled?

**Never use `acceptAnyProxy=true` in production** absent an extraordinary, approved threat model. The cache holds previously checked results, yet **proxy authorization must also be re-evaluated when policies change**—never treat a stale cache entry as proof that proxy A remains authorized forever.

## 13. Rules for Choosing TTL: Separating Two Clocks

There are at least **two lifetimes**:

1. **CAS PT validity prior to validation:** how long CAS accepts an unconsumed PT; CAS recommends short lifetimes for unvalidated ST/PTs (5 minutes is a protocol recommendation, not a universal default across all deployments).
2. **Spring Authentication cache TTL after validation:** how long B permits reusing **an already-validated result**. This clock starts at cache write time, independent of CAS.

Illustrative timeline:

~~~text
10:00:00 CAS issues PT-X for API B
10:00:12 B validates PT-X successfully
         CAS consumes PT-X
         B caches Authentication (TTL = 120 seconds)
10:01:00 Client sends PT-X again -> cache HIT
10:02:12 Cache expires relative to 10:00:12
10:02:13 Client sends PT-X again -> cache MISS
         CAS refuses to revalidate consumed PT-X
         Client needs a fresh PT
~~~

**Never assume:** “CAS lets the PT live 5 minutes, so the cache also defaults to 5 minutes” or “CAS PT expires after 5 minutes, so the cache automatically clears.” They are two separate lifecycles.

### Criteria for Choosing TTL

| Factor | Impact |
| --- | --- |
| API sensitivity | Payment/admin endpoints may require tiny TTLs or no caching |
| Request frequency | Bursts of calls in one operation benefit from a brief cache |
| Revocation agility | Fast revocation requires short cache TTLs or active invalidation |
| Proxy chain changes | Requires invalidation when proxy delegation is withdrawn |
| CAS outage policy | Cache hit does not prove CAS still trusts the principal |
| Device/network risk | A stolen PT remains replayable throughout the cache window |
| Cache size | Memory/DoS risk; requires `maximumSize` and load controls |
| Multi-node consistency | Each node tracks TTL independently with local caches |
| Compliance/SLA | Dictates maximum delay to revoke accounts/roles/tokens |

**Suggested rule:** Derive TTL from your **maximum acceptable revocation lag**, not just performance. For example, a “must revoke access within 60 seconds” requirement makes a 10-minute cache TTL **non-compliant** without active invalidation and per-request checks.

Never treat a fixed number as universal. Run canary tests, measure traffic, and conduct a security review.

## 14. Reuse Limits: TTL Is Not Usage Count

The `StatelessTicketCache` interface has no `maxUses` method. Standard cache backends likewise track entries by time/capacity, not “how many times it was used.”

A cached `Authentication` could be used:

- Many times within 30 seconds.
- Continuously right up to the TTL boundary.
- Across multiple endpoints sharing the cache.
- Concurrently across multiple threads.
- From a different client if the PT leaked, unless additional caller binding exists.

**To enforce at most N uses**, add explicit design:

1. Define clearly **what counts**: every cache hit? including initial validation? all endpoints or only sensitive operations?
2. Count **atomically** so concurrent threads cannot exceed `maxUses`.
3. Combine with an **absolute TTL** from validation time.
4. Bind scope: service, proxy chain, tenant, and operation class.
5. Upon reaching the limit, evict the entry and require a fresh PT—never self-issue PTs.
6. Optionally require per-request proof (mTLS/client auth/DPoP-like binding where platform supports it), since a PT is a bearer string.
7. Test concurrent hits and races; distributed caches require atomic Lua/CAS ops or transactional primitives.
8. Emit a `reuse_count` metric while **never logging raw tickets**.

**Note:** If strict single-use at the backend is desired, **disabling the cache** is the clearest choice. Enabling caching is an explicit decision to allow bounded reuse at the service.

## 15. Standalone Java 17: Cache with Absolute TTL, Scope, and `maxUses`

The program below simulates **supplementary policy checks** rather than replicating all of Spring Security. It shows that a PT validated once by CAS can be reused briefly by the backend, provided service/proxy/tenant match, TTL has not elapsed, and usage stays within the limit.

Create **`ProxyTicketReusePolicyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public class ProxyTicketReusePolicyDemo {

    record Scope(String service, String proxy, String tenant) {}

    record Cached(String user, Scope scope, long expiresAt,
                  int uses) {}

    static final class PolicyCache {
        private final Map<String, Cached> entries = new HashMap<>();
        private static final long TTL_SECONDS = 120;
        private static final int MAX_USES = 2;

        void storeValidated(String ticket, String user, Scope scope,
                            long nowSeconds) {
            // Called only after CAS successfully validated the PT.
            // Do not simulate ticket validation with this method.
            entries.put(ticket, new Cached(
                    user, scope, nowSeconds + TTL_SECONDS, 0));
        }

        String use(String ticket, Scope expected, long nowSeconds) {
            Cached value = entries.get(ticket);
            if (value == null) {
                return "MISS";
            }
            if (nowSeconds >= value.expiresAt()) {
                entries.remove(ticket);
                return "EXPIRED";
            }
            if (!value.scope().equals(expected)) {
                return "DENY_SCOPE";
            }
            if (value.uses() >= MAX_USES) {
                entries.remove(ticket);
                return "REAUTH_REQUIRED";
            }
            entries.put(ticket, new Cached(
                    value.user(), value.scope(),
                    value.expiresAt(), value.uses() + 1));
            return "ALLOW " + value.user();
        }

        void revoke(String ticket) {
            entries.remove(ticket);
        }
    }

    public static void main(String[] args) {
        PolicyCache cache = new PolicyCache();
        Scope payments =
                new Scope("payments-api", "portal-a", "north");
        Scope admin =
                new Scope("admin-api", "portal-a", "north");

        cache.storeValidated("PT-A", "alice", payments, 100);
        System.out.println("first: "
                + cache.use("PT-A", payments, 100));
        System.out.println("wrong service: "
                + cache.use("PT-A", admin, 110));
        System.out.println("second: "
                + cache.use("PT-A", payments, 180));
        System.out.println("third: "
                + cache.use("PT-A", payments, 190));

        cache.storeValidated("PT-B", "bob", payments, 300);
        System.out.println("after TTL: "
                + cache.use("PT-B", payments, 421));

        cache.storeValidated("PT-C", "carol", payments, 500);
        cache.revoke("PT-C");
        System.out.println("after revoke: "
                + cache.use("PT-C", payments, 510));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac ProxyTicketReusePolicyDemo.java
java ProxyTicketReusePolicyDemo
~~~

**Exact stdout:**

~~~text
first: ALLOW alice
wrong service: DENY_SCOPE
second: ALLOW alice
third: REAUTH_REQUIRED
after TTL: EXPIRED
after revoke: MISS
~~~

### Reading the Output

- First call: validated `Authentication` granted to `payments-api`.
- Reusing the same PT at `admin-api`: rejected by scope check; **does not increment use count**.
- Second call at the right service: permitted within TTL window.
- Third call: hits `maxUses` → requires fetching a fresh PT.
- `PT-B` written at 300 expires at 420; expired at 421.
- `PT-C` revoked, so lookup misses.

**Critical safety note:** this is a **single-threaded simulation using a `HashMap` and simulated clock**. Production requires CAS protocol validation before caching, an atomic cache backend, high-entropy ticket keys, race handling, session/account revocation, and network protections. Never drop this demo in as a production `StatelessTicketCache`; Spring's standard interface **looks up solely by ticket string**, so enforcing scope/`maxUses` must be engineered at the proper boundary rather than blindly copying `PolicyCache`.

## 16. Authentication Cache Lifetime and Permission Freshness

The cache stores the **`CasAuthenticationToken` constructed upon successful validation**, including the principal and `GrantedAuthority` at that moment. If anything changes in CAS or the local DB:

- The user's account is locked.
- The user leaves the tenant.
- CAS groups/roles change.
- Proxy A loses permission to call API B on the user's behalf.
- The underlying TGT/PGT token/session is revoked.
- MFA/assurance policy introduces stricter requirements.

A **cache hit does not re-call CAS or `UserDetailsService` to learn about changes**. Therefore, define **when permissions become stale**.

Strategies:

| Strategy | Capability | Trade-Off |
| --- | --- | --- |
| Short TTL | Caps maximum staleness of `Authentication` snapshot | Increases PT request / validation frequency |
| Active `removeTicketFromCache` | Revokes a known PT locally | Must know cache key and fan out across all nodes |
| Flush entire cache on policy change | Simple when rotating trust versions | Spikes login/validation traffic |
| Per-request account/role version check | Enables rapid permission revocation | Adds a database/cache lookup |
| Live DB domain authorization | Never relies solely on stale authorities | Adds latency, ensures accurate entitlements |
| Additional mTLS/caller binding | Reduces risk of stolen PT used by another client | Requires service caller identity |
| No cache | Never reuses `Authentication` via PT | Higher load minting fresh PTs |

**TGT/PGT logout does not automatically purge `StatelessTicketCache`.** That cache is managed by backend B. The CAS Server may have invalidated the root tickets while B still holds a cached `Authentication` until TTL expires or eviction runs.

## 17. Can a PT Still Be Reused After CAS Revokes the Session?

**Yes, within the service's cache window**, if backend B has not been notified or purged the entry and policy skips live account/session checks.

Example:

~~~text
10:00 API B validates PT-X -> caches auth (5-minute TTL)
10:01 CAS logs user out, destroys TGT/PGT
10:02 Caller resends PT-X to API B
      cache HIT -> backend skips CAS
      may continue honoring stale Authentication
10:05 Cache TTL expires; next PT-X reuse misses
      CAS rejects already-consumed PT
~~~

**This illustrates a risk model, not a guarantee every Spring setup stays open:** backends may enforce stricter revocation policies. The essential point is that **CAS logout is not a guaranteed automatic cache invalidation signal**.

For sensitive operations (payments, admin, PII), consider revocation epochs or live backend entitlement checks; if immediate revocation is required, TTL alone is insufficient.

## 18. Multi-Node Deployments, Redis, and TTL Consistency

When API B runs multiple pods behind a load balancer:

~~~text
            Proxy caller Portal A
                     |
                 Load Balancer
                  /          \
              API B-1      API B-2
                |             |
          local cache 1  local cache 2
                  \          /
                 CAS Server
~~~

**With local Caffeine caches:**

1. First PT-X request hits B-1 → CAS validates once; B-1 caches the result.
2. Next PT-X request hits B-2 → B-2 cache misses.
3. B-2 attempts to revalidate PT-X with CAS → CAS rejects because the PT was already consumed.
4. Users see intermittent errors depending on which node handles the request.

Options:

- Use a centralized cache with TTL/eviction such as Redis, if permitted and using safe serialization.
- Maintain sticky routing during the TTL window if engineered and monitored—bearing in mind sticky routing does not solve failover cleanly.
- Have clients mint a **fresh PT per request/node** instead of sharing caches.
- Adopt an API authentication mechanism whose audience, TTL, and validation fit the topology better.
- When revoking, fan out invalidations across all nodes/caches.

**Redis caching of `CasAuthenticationToken` requires extra care:** `Authentication` objects may break under default Java serialization across versions/nodes and may contain PII; design explicit serializers, schemas/versions, encryption/access controls, and key namespaces. Never enable insecure Java deserialization on untrusted data.

### TTLs in a Cluster

- Verify TTLs in the **actual cache backend**, not only local config.
- Use consistent clocks; prefer server/cache monotonic semantics where applicable.
- Define eviction when deploying new versions or changing roles.
- Audit caches shared across tenants and CAS contexts.
- Keep key namespaces narrow to avoid collisions between apps trusting different CAS servers.
- Evict stale entries when changing CAS service URLs or proxy trust.

## 19. Cache Keys and Sensitive Data in Telemetry

Spring cache implementations typically use the **raw ticket string** as the cache key. That string is a bearer secret. Exposing tickets in metrics, logs, or Redis command traces increases leak risk.

Never log:

- Raw `PT-...` or `ST-...` in access logs.
- Full `CasAuthenticationToken` dumps in logs.
- CAS Assertions containing identity attributes/PII.
- PGT, TGT, TGC, or cookie values.
- Headers/URL queries carrying tickets in APM traces.

Permissible per policy:

- Keyed hash/digest (HMAC) of a ticket for internal correlation, never the raw value.
- CAS trust-context identifier and approved public service ID.
- Cache hit/miss/evict/expired counters.
- Proxy-chain policy outcomes at a non-secret level.
- Active entry counts and cache latency.
- Authentication decision vs. domain authorization decision.
- Correlation IDs independent of ticket values.

**Note:** Hashing a ticket does not make a bearer credential public-safe if ticket entropy is low or logs correlate to PII. Enforce retention and access controls.

## 20. Why Not Use the Same Ticket Across All Backends?

Suppose Portal A calls Billing B and HR C:

~~~text
Portal A -> CAS /proxy(PGT, target=Billing B) -> PT-B
Portal A -> CAS /proxy(PGT, target=HR C)      -> PT-C
~~~

**`PT-B`** is issued by CAS for Billing B, not HR C. The CAS protocol rejects `PT-B` if HR C tries validating it for HR C's target.

If multiple backends **share one cache** or proxy auth boundary with ticket-key-only lookups, a cached `Authentication` could be reused out of scope. Therefore:

1. Never share a `StatelessTicketCache` instance across distinct service trust boundaries without explicit isolation.
2. Never forward `PT-B` arbitrarily to HR C.
3. Never treat a ticket authentication cache as a cluster-wide SSO tool.
4. Enforce service/tenant scope on every request.
5. Across multiple hosts/tenants, separate cache namespaces or migrate to audience-scoped tokens.

A cache hit **is not a second successful CAS `/proxyValidate` for a new service**.

## 21. `StatelessTicketCache` Is Not the CAS Server's Stateless Ticket Registry

The two names look similar yet belong to **different products and purposes**.

| Term | Where Does It Live? | Function |
| --- | --- | --- |
| **Spring Security `StatelessTicketCache`** | CAS Client / backend service | Caches **`Authentication` results** after CAS validates a ticket |
| **Apereo CAS Stateless Ticket Registry** | CAS Server | Mechanism for issuing/verifying **self-contained tickets** in a CAS Server deployment |
| **CAS Proxy-Granting Ticket Storage** | Proxying CAS client | Stores PGTs so service A can request PTs for backend B |
| **Spring `SecurityContext` Session Repository** | Spring web application | Stores local `Authentication` in `HttpSession` or another repository |

**Never conflate these stores:** PGT storage does not cache PT validation results; Spring `StatelessTicketCache` does not mint PTs; CAS Stateless Ticket Registry does not replace Spring's `Authentication` cache.

**Version warning:** Apereo CAS **Stateless Ticket Registry** (development docs) carries trade-offs that may **forgo single-use ticket guarantees** and alter session revocation compared to stateful registries. That is a **CAS Server-side exception** requiring separate evaluation if enabled—never extrapolate its caveats as default behavior of Spring's `StatelessTicketCache`.

This lesson assumes the **CAS Protocol with one-time ST/PT validation** per specification; if your CAS Server runs another registry mode, verify its exact behavior and risks independently.

## 22. Protecting Proxy Credentials in Transit Over HTTP

A CAS PT is a bearer ticket. When sending from A to B:

- Mandate **HTTPS/TLS** with certificate and hostname verification.
- In server-to-server traffic, prefer **mTLS** or gateway service identities wherever possible.
- Limit ticket exposure in query strings; when CAS clients use the `ticket` request parameter, configure access log redaction.
- Never allow untrusted browsers/JS to mint or alter `PT` values to hit backends.
- Keep tickets out of `Referer`, analytics, tracing, error URLs, frontend URLs, and support tickets.
- Set strict timeouts/rate limits and replay defenses beyond the cache layer.
- Never send `PT-B` to another backend or staging environment.
- Protect PGTs on A; a PGT can mint many PTs, carrying a larger blast radius than a single PT.
- Define rotation/revocation workflows for keys, service registries, and proxy chains.

**Caching does not make a PT less sensitive.** On the contrary, it creates an extra window where a stolen PT can still be accepted by service B **after its first validation**, even though CAS Server refuses revalidation.

## 23. Per-Request Authorization: Identity Alone Is Insufficient for Business Actions

Suppose B retrieves a cached `Authentication` with `ROLE_FINANCE_VIEWER`. Request:

~~~text
GET /api/tenants/south/invoices/773
ticket=PT-X (for a user belonging to north)
~~~

**Authentication may succeed**, yet **Authorization must deny** because the user does not belong to tenant `south`.

Checks to enforce:

1. Local account remains active.
2. Proxy chain/caller remains permitted.
3. Request tenant is in the user's verified memberships.
4. Authorities permit the requested action.
5. Resource belongs to that tenant.
6. Current session/role version has not been revoked.
7. Sensitive operations satisfy auth freshness/step-up rules.
8. Where required, the caller proves its identity via mTLS alongside the PT.

`@PreAuthorize("hasRole('VIEWER')")` can guard a route layer, yet **cannot verify invoice ownership/tenant**. Domain service checks are essential.

**Never extend the lifetime of an authorization decision** merely because the cache holds `Authentication`. Object permissions can change faster than an authentication snapshot.

## 24. Handling Cache Misses, CAS Outages, and Validation Errors

### On Cache MISS

The backend calls CAS to validate the ticket. A fresh PT succeeds; if an **already-consumed PT** missed because its cache entry expired or was evicted, CAS returns `INVALID_TICKET`. That is normal behavior, never a reason to disable validation.

**Expected behavior:** return 401/challenge or instruct the caller to request a fresh PT via its authorized PGT. Never retry the same ticket endlessly.

### On CAS Outage

- Cache HITs may still return cached `Authentication` if policy allows.
- Cache MISSes cannot validate unknown tickets; **fail closed**.
- Never use “CAS is down” as an excuse to set infinite TTLs or accept any ticket.
- For sensitive endpoints, reject even cache HITs if freshness or revocation SLAs demand it.

### On Cache Backend Outage

Never fail open by default. Decide per architecture:

- If a **fresh PT** can be validated once against CAS, a cache write failure may allow the first request per policy, while subsequent calls need fresh PTs.
- If an old ticket was already consumed, you cannot “revalidate to repopulate the cache.”
- If the cache is shared, add telemetry and bounded retries.
- Serialization/deserialization errors on cached `Authentication` must fail authentication—never produce an empty token.

### On Service / Proxy Chain Mismatch

Never use an old-scope cache entry to bypass a new policy. Return 403/401 distinguishing authentication vs. authorization, without leaking raw tickets, assertions, proxy chain secrets, or stack traces to the client.

## 25. Changes That Mandate Eviction or Shorter TTLs

| Change | Recommended Action |
| --- | --- |
| User locked or role removed | Evict affected cache entries or verify account version per request |
| CAS/PGT logout | Does not auto-clear Spring cache; actively invalidate if required |
| Proxy chain revoked | Evict auth snapshots previously issued via that proxy |
| Service registration changed | Evict old entries / rotate cache namespace |
| Tenant suspended | Deny in domain policy and invalidate cached privileges |
| CAS server/trust anchor changed | Revalidate new tickets; evaluate flushing old cache |
| Service URL/host/ACS changed | Never reuse cross-service; verify cache scope |
| `maxUses` policy changed | Reject cached entries violating the new policy version |
| Extended CAS backend outage | Consider forced denial per policy; never extend cache TTLs |
| Ticket leak risk | Evict ticket, block requests, and audit logs |
| Deployment changes serialization schema | Perform controlled cache eviction/migration |

**Implementation capability:** `removeTicketFromCache(ticket)` deletes by key when the ticket is known. To revoke **by user, tenant, or proxy chain**, build a **reverse index**, cache tags, or entitlement version checks. The standard cache interface **has no `removeAllByUser`**.

## 26. Test Matrix: Functionality, TTL, and Preventing Privilege Escalation

| # | Scenario | Expected Outcome |
| --- | --- | --- |
| 01 | Fresh PT for API B, valid proxy chain | One CAS validation → caches auth |
| 02 | Same PT resent immediately | Cache hit; CAS not called again |
| 03 | Same PT resent after TTL | Cache miss and CAS rejects consumed PT |
| 04 | Cache disabled via `NullStatelessTicketCache` | Resent PT is rejected |
| 05 | Cache `expireAfterWrite=120s` | Repeated reads do not extend absolute TTL |
| 06 | Cache `expireAfterAccess` without max age | Flag risk of unbounded lifetime extension |
| 07 | API B's PT sent to API C | Blocked by scope/authorization |
| 08 | North tenant's PT sent to south | Domain policy denies |
| 09 | PT via disallowed proxy chain | Validator rejects before cache write |
| 10 | Role revoked post-validation | Sensitive requests denied within revocation SLA |
| 11 | User logs out of CAS while PT still cached | Explicitly verify cache hit policy; never assume auto-revocation |
| 12 | Cache entry evicted via `removeTicketFromCache` | No longer hits cache; requires new ticket |
| 13 | `maxUses=2` in custom policy | Calls beyond limit are rejected |
| 14 | 100 concurrent requests on one key | `maxUses` never exceeded under race if counted |
| 15 | Stolen PT before user logs out | TLS/mTLS/caller binding and cache scope limit exposure |
| 16 | CAS `/proxyValidate` endpoint times out | Creates no unverified `Authentication` |
| 17 | Cache hit during CAS outage | Follows freshness policy; does not blindly allow everything |
| 18 | Cache miss during CAS outage | Fails closed |
| 19 | Cache provider lacks TTL | QA catches and blocks from production |
| 20 | Local Caffeine cache across multiple nodes | Detects PT failure on second node after one-time validation |
| 21 | Shared Redis cache eviction | All nodes immediately stop reusing revoked PT |
| 22 | Cached serialized `Authentication` version bump | Never deserializes infinitely or bypasses policy |
| 23 | Request already holds another `SecurityContext` | Never confuses identities from an unprocessed PT |
| 24 | Spoofed `Host`/`X-Forwarded-Host` | Never constructs unauthorized service URL |
| 25 | PT from another service with same subject | Never authorizes based on username alone |
| 26 | PT replayed before initial validation finishes | CAS one-time semantics and race handling hold |
| 27 | Ticket consumed by wrong-service validation | CAS rejects subsequent validation |
| 28 | `UserDetails` role mapper sees unknown group | Never grants `ROLE_ADMIN` |
| 29 | Ticket appears in access logs | Redaction strips it |
| 30 | CAS Stateless Ticket Registry enabled | Tested separately since semantics differ from one-time registry |
| 31 | Proxying disabled in CAS Service Registry | No new PTs can be issued |
| 32 | Proxy chain and cache policy change together | Stale cache entries invalidated / fail closed |

**PASS criteria:** observe CAS validation counts, cache hits/misses, security context, endpoint authorization, and actual request outcomes. Unit-testing `CacheManager` alone does not prove `TicketValidator` ran only once.

## 27. Common Error Diagnostics

| Symptom | Likely Cause | How to Check |
| --- | --- | --- |
| First request succeeds, second gets `INVALID_TICKET` | Cache disabled, `NullStatelessTicketCache`, hit different node, or expired | Inspect cache bean, TTL, and multi-node routing |
| Requests keep working after CAS logout | Cached `Authentication` still within TTL | Check revocation/eviction policy and domain authorization |
| PT works on an endpoint outside intended target | Cache keyed by ticket; all URLs share provider | Restrict chains/paths, service scope, and authorization |
| User retains old privileges after group removal | Cached authorities snapshot | Add entitlement version check or evict |
| Cached `Authentication` never expires | Backing cache lacks TTL | Configure `expireAfterWrite`/absolute TTL |
| More requests than `maxUses` succeed | `StatelessTicketCache` has no built-in counter | Add atomic usage-budget guard at boundary |
| PT works on node A but fails on node B | Independent local caches, CAS single-use | Shared cache or alternative auth design |
| Sudden mass logouts when cache clears | No fresh PTs minted; clients replay consumed PTs | Callers must obtain fresh PTs from CAS via PGT |
| Proxy ticket validation rejected | `Cas20ProxyTicketValidator` does not allow that chain | Compare proxy list with Service Registry |
| `acceptAnyProxy=true` lets unfamiliar proxy tickets in | Overly permissive trust | Specify explicit `allowedProxyChains` |
| CAS reports `INVALID_SERVICE` | Target URL differs between PT issuance and validation | Compare service URL and reverse proxy config |
| Service URL changes behind gateway | Missing trusted forwarded headers config | Host allowlist and canonical public origin |
| Cache grows unbounded | Missing max entries / TTL | Set max size, TTL, and metrics |
| Redis serialization exception | `CasAuthenticationToken` breaks serializer/schema | Versioning and custom secure serialization |
| `ROLE_ADMIN` appears from CAS group | Direct group→role mapping | Strict allowlist and tenant scoping |
| Tickets appear in logs/APM | Verbatim query string logged | Mask ticket credentials and shorten log retention |
| Spring 5 snippet fails to compile on Spring 6/7 | API/token classes or JCache/Ehcache changed | Check exact Javadoc/BOM and test build |

**Never fix errors by** setting infinite TTLs, skipping proxy chain checks, accepting arbitrary service URLs, or disabling TLS validation.

## 28. Production Deployment Runbook

### Before Enabling Cache

1. Inventory stateless clients, API service URLs, proxy chains, CAS server/version, and CAS client version.
2. Verify CAS Service Registry permits only approved services and proxy chains.
3. Test the uncached PT flow: CAS issues PT for B, B validates successfully **once**.
4. Confirm why ticket reuse is needed; could a fresh PT per request or OAuth2 tokens fit better?
5. Assess **replay risk**, tenant boundaries, API sensitivity, and account revocation SLAs.
6. Agree on absolute TTL, cache max size, reuse limit (if needed), cleanup behavior, and ownership.
7. Pick cache backend: local Caffeine vs. shared Redis, factoring in single-use PTs and multi-node topology.
8. Separate filter chains, trust contexts, service URLs, and cache namespaces per policy.
9. Design eviction for user/group/tenant/proxy-chain changes.
10. Set up redaction metrics and verify logs contain zero tickets.

### During Rollout

1. Enable caching on a canary backend, keeping quick rollback to `NullStatelessTicketCache`.
2. Measure `CAS validate`, `cache hit/miss`, `INVALID_TICKET`, service mismatches, and p95 latency.
3. Verify TTL accuracy against wall-clock time and continuous calls.
4. Test presenting a PT to another endpoint and another tenant; policy must block both.
5. Test logout, user disablement, role revocation, and proxy-chain updates.
6. Test node switching, cache eviction, Redis outage, and CAS outage.
7. Verify object-level authorization does not rely solely on cached roles.
8. Monitor replay anomalies and identical PTs arriving from distinct caller identities.
9. Cross-check proxy validation trust and errors on the CAS Server.
10. Expand rollout only after security, revocation, and latency criteria pass.

### During Rollback or Incident

1. Stop accepting uncontrolled cached `Authentication`s (evict cache or update config) per change policy.
2. Because PTs were consumed, clients must obtain **fresh PTs**; never replay old tickets.
3. Never extend cache TTLs to ride out a CAS outage without security owner approval.
4. Check whether tokens leaked into proxy logs/traces and rotate/revoke affected credentials.
5. Audit CAS server service registry, proxy chains, and backend authorization.
6. Document the incident timeline, replay exposure window, tenant impact, and mitigation results.

## 29. Monitoring and Alerting

These metrics are **recommended application instrumentation**, not default auto-instrumentation from Spring Security CAS:

| Metric | Meaning |
| --- | --- |
| `cas_proxy_cache_hit_total` | Count of cached authentication reuses |
| `cas_proxy_cache_miss_total` | Count requiring validation or missing cache |
| `cas_proxy_cache_evictions_total` | Entries evicted by TTL, manual revoke, or capacity |
| `cas_proxy_cache_entry_age_seconds` | Age of cache entry at time of use |
| `cas_proxy_validation_success_total` | Successful PT validations at CAS |
| `cas_proxy_validation_failure_total` | Failed PT validations by reason |
| `cas_proxy_replay_blocked_total` | Requests denied due to scope/maxUses/revoked state |
| `cas_proxy_chain_denied_total` | Disallowed proxy chains |
| `cas_proxy_authz_denied_total` | Valid authentication denied by domain authorization |
| `cas_proxy_cache_size` | Current entry count to spot memory pressure |
| `cas_proxy_revocation_delay_seconds` | Lag between revocation and denied request |

Never put raw PTs, principal IDs, emails, TGT/PGTs, or proxy credentials into **metric labels**. When tracing is needed, use protected short-lived correlation IDs. Separate **cache hit resulting in 403** from **CAS validation failed**.

**Alert triggers:** sudden spike in hit rate for one PT or unfamiliar callers; elevated `INVALID_TICKET` after failover; cache entries failing to expire; spikes in invalid proxy chains; or users still succeeding past revocation SLAs.

## 30. Frequently Asked Questions

**1. Does `StatelessTicketCache` make a CAS Proxy Ticket multi-use at CAS?**  
No. CAS validation remains single-use. Spring Security **reuses the already-validated `CasAuthenticationToken`** at the backend on cache hits.

**2. Why does resending the same PT a second time still work?**  
Because the backend reads `Authentication` from its cache without calling CAS again. On a cache miss or expiry, CAS rejects the consumed PT.

**3. Is the cache lifetime automatically derived from the PT's expiration?**  
Not by default. The backing Spring `Cache` controls TTL independently and must be explicitly configured and tested.

**4. Does `SpringCacheBasedTicketCache` have `setMaxUses`?**  
No. The standard interface exposes only get, put, and remove; add an explicit policy/atomic counter if usage caps are required.

**5. When should `NullStatelessTicketCache` be used?**  
When you do not want cached `Authentication`s; every new request must present an unconsumed PT.

**6. Does the cache key automatically include the service URL and tenant?**  
No. Javadoc specifies lookup strictly by **ticket ID string**. Design isolation and authorization separately.

**7. Can the same PT be used across API B and API C?**  
In the CAS protocol, a PT is bound to a single target service. A cache hit inside a multi-URL backend does not make it valid for service C; enforce scope checks.

**8. Does CAS logout automatically clear all cached `Authentication`s?**  
Not automatically. The service must implement invalidation/revocation policies.

**9. Is `expireAfterAccess` safe?**  
Without an absolute TTL, continuous traffic can keep extending the entry. Prefer a hard maximum age and verify against policy.

**10. Does the cache synchronize across pods automatically?**  
No. Local Caffeine caches are per-node; once CAS consumes the PT, another node's validation will fail.

**11. Does caching the authentication result mean the user is authorized on the API?**  
No. Always authorize by route, method, tenant, resource, and current account status.

**12. Does shared Redis solve every risk?**  
No. It enables shared caching while introducing serialization, data protection, key namespacing, revocation, and outage risks.

**13. Are Apereo CAS Stateless Ticket Registry and Spring `StatelessTicketCache` the same thing?**  
No. One is a CAS Server ticket registry; the other is an `Authentication` cache on the Spring Client—their semantics differ.

**14. Should `acceptAnyProxy=true` be enabled to reduce errors?**  
Not in normal production; restrict proxy chains per service registry and trust policy.

**15. What if near-instant revocation is required?**  
Do not rely solely on TTL. Actively evict and verify account/entitlement/role versions on sensitive requests—or disable caching altogether.

## 31. Pre-Production Checklist

- [ ] Understood that PT/ST are **single-use validation at CAS**, and the cache only reuses `Authentication` results on the backend.
- [ ] Verified PGT/PT flow and confirmed CAS Server and service registry permit only exact proxy callers/targets.
- [ ] `CasAuthenticationProvider` uses a proxy-capable `TicketValidator` with strict **allowed proxy chains**.
- [ ] `acceptAnyProxy=true` is not enabled in production without threat-model approval.
- [ ] `ServiceProperties.authenticateAllArtifacts` is enabled strictly on required filter chains/paths.
- [ ] `ServiceAuthenticationDetailsSource` derives trusted service URLs, immune to spoofed `Host`/forwarded headers.
- [ ] Understood `StatelessTicketCache` looks up strictly by ticket ID with no default scoped composite key.
- [ ] Never share caches/providers across trust contexts/tenants without isolation and domain checks.
- [ ] Backing `Cache` enforces `expireAfterWrite` or an actual absolute TTL.
- [ ] Configured maximum entries and verified eviction; max size is not max uses.
- [ ] If enforcing usage limits, implemented atomic counting and tested concurrent requests.
- [ ] Distinguished CAS PT expiry from `Authentication` cache TTL rather than assuming equality.
- [ ] Chose TTL thresholds based on sensitivity and revocation SLA, not latency alone.
- [ ] Cached `Authentication` never replaces account/tenant/resource authorization.
- [ ] Invalidation path exists for disabled users, changed roles/tenants/proxy trust, or leaked tokens.
- [ ] Tested multi-node/Redis/Redis outage/CAS outage, failover, and clients acquiring fresh PTs.
- [ ] Zero raw tickets/TGT/PGT/TGC or PII-bearing serialized `Authentication`s in logs.
- [ ] Tested replay after TTL, logout, wrong service, wrong tenant, wrong proxy chain, and `maxUses`.
- [ ] Never confused Spring `StatelessTicketCache` with Apereo CAS Stateless Ticket Registry.
- [ ] Verified APIs/packages against your exact Spring Security and CAS Client BOM rather than copying legacy configs blindly.

## 32. Conclusion

**`StatelessTicketCache` lets `CasAuthenticationProvider` serve stateless callers by remembering `CasAuthenticationToken` after an initial successful CAS validation.** When the same PT arrives again, the provider can serve a cache hit without re-calling CAS, even though the PT was consumed at the CAS Server. This helps short bursts of API calls yet creates a **backend bearer replay window**, rather than extending the CAS Proxy Ticket's own validity.

To use it safely, **bound absolute lifetime, entry count, service/proxy-chain/tenant scope, and per-request authorization**; add an atomic policy if you need usage caps, since the standard interface has no `maxUses`. Also design **explicit revocation**, because CAS logout, withdrawn permissions, or proxy-chain changes **do not automatically clear** Spring's cache. Whenever those risks cannot be controlled, use `NullStatelessTicketCache` with a fresh PT per request or a better-suited API authentication mechanism.

### Official Documentation and Further Reading

- Spring Security — CAS Authentication, **Proxy Ticket Authentication**, `StatelessTicketCache`, stateless flows: https://docs.spring.io/spring-security/reference/servlet/authentication/cas.html
- Spring Security Javadoc — `StatelessTicketCache`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/StatelessTicketCache.html
- Spring Security Javadoc — `SpringCacheBasedTicketCache`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/SpringCacheBasedTicketCache.html
- Spring Security Javadoc — `NullStatelessTicketCache`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/NullStatelessTicketCache.html
- Spring Security Javadoc — `CasAuthenticationProvider`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/authentication/CasAuthenticationProvider.html
- Spring Security Javadoc — `CasAuthenticationFilter`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/web/CasAuthenticationFilter.html
- Spring Security Javadoc — `ServiceProperties`: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/cas/ServiceProperties.html
- Apereo CAS — CAS Protocol Specification, Sections 2.5–3.3 (ST/PT/PGT): https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html
- Apereo CAS — Proxy Authentication: https://apereo.github.io/cas/development/authentication/Configuring-Proxy-Authentication.html
- Apereo CAS — Stateless Ticket Registry (**distinct concept** with its own caveats): https://apereo.github.io/cas/development/ticketing/Stateless-Ticket-Registry.html
