# Stale Account Info Due to Cache or Changed Authorities in Spring Security

## 1. Diagnostic Problem

An administrator just removed `ROLE_ADMIN` from Alice's account in the database, yet Alice can still access `/admin`. Someone else just changed their password and found that logging in with the old password still succeeds. A locked account can still use an existing session. The same user calling an API through node A gets 403, while through node B gets 200.

These symptoms can stem from a common issue: **the identity or authority information being used is a stale snapshot**. However, do not conclude every case is caused by "cache". In Spring Security, data can live in several different layers:

1. **Source of truth**: database, LDAP/AD, Identity Provider (IdP), permission service.
2. **Cache of `UserDetails` / account / roles**: `UserCache`, `CachingUserDetailsService`, Spring Cache `@Cacheable`, Redis, Caffeine.
3. **Created `Authentication`**: principal and `GrantedAuthority` loaded at authentication time.
4. **Stored `SecurityContext`** in an HTTP session or elsewhere.
5. **Issued access token / JWT / OIDC claims**, with its own expiration time.
6. **Business cache**: authorization decisions, response caches, gateways, frontend state.
7. **Data replicas / distributed systems**: DB replicas, LDAP replicas, nodes, and IdP.

This lesson aims to **diagnose the exact layer holding stale data, fix the right boundary, and test the effective enforcement of authority/status changes**. Focus is on Spring Boot 3.x / Spring Security 6.x / Java 17+ (Servlet), with notes for Spring Security 7.x, Resource Server, and WebFlux.

After this lesson, you will be able to:
- Clearly define "effective authorities" versus "authorities just written to the DB".
- Distinguish stale cache from **session snapshots** and **JWT claim snapshots**.
- Accurately inspect `Authentication.getAuthorities()`, login timestamp, and authority versions.
- Design post-commit eviction, session revocation, token strategies, and tenant-scoped cache keys.
- Write Java 17 and JUnit 5 tests verifying stale cache and credential erasure.
- Evaluate race conditions when authorities change across a cluster.
- Explain why "flush Redis cache and retry" is not a guaranteed solution.

## 2. What Is "Stale"? Distinguishing Three Points in Time

Consider an account:

```text
T0 = 10:00:00  DB: Alice has ROLE_ADMIN
T1 = 10:00:05  Alice logs in, Authentication A1 has ROLE_ADMIN
T2 = 10:02:00  Admin revokes ROLE_ADMIN in DB
T3 = 10:02:01  Alice uses session A1 to call /admin
T4 = 10:04:00  Alice logs out, logs in fresh, creating Authentication A2
```

There are three distinct questions:

- **What does the DB have at T3?** At T2 authorities changed; the source of truth no longer holds `ROLE_ADMIN`.
- **What does `Authentication` A1 have at T3?** It may still hold `ROLE_ADMIN` from T1, because an `Authentication` typically carries a **snapshot of authorities at creation time**.
- **What does `Authentication` A2 have at T4?** It depends on whether the loader/IdP/cache saw the T2 data at the time of the new login.

You cannot merely read the DB and claim requests are already using the new authorities. Nor can you merely log out and log back in and claim the cache was refreshed: if the loader returns a stale snapshot, **A2 is also stale**.

**Some phenomena are not stale bugs:**
- A user gets 403 because of a missing `ROLE_` prefix even though the DB granted `ADMIN`: that may be a mapping bug.
- A user gets 200 because a different `SecurityFilterChain` does not enforce the policy: that is a rule/matcher bug.
- Someone just changed the role on screen but the transaction has not committed yet: the DB does not hold the new source of truth yet.
- The system allows old sessions to remain valid until TTL expiry under a **published policy**: that is eventual revocation, requiring an SLA assessment rather than automatically being called a bug if it matches the contract.
- Frontend still shows the Admin menu while the API already returns 403: stale UI cache, **not necessarily server allowance**.

State the problem concretely: "After revoking an authority at T2, a **new request** from Alice on an existing session must receive 403 within at most N seconds." That is a testable criterion.

## 3. Map of Where Authorities and State Live

| Layer | Values Typically Held | When Is It Refreshed? | What Happens If Stale? |
| --- | --- | --- | --- |
| DB / LDAP / IdP | enabled, locked, groups, roles, password hash | Source update/replication | Node reading a replica sees old data |
| `UserDetailsService` | Builds `UserDetails` from source | When `loadUserByUsername` actually runs | Loader maps wrongly or uses an old local copy |
| `UserCache` / `@Cacheable` | `UserDetails`, role snapshot, password hash | TTL, evict, update, cache miss | New logins still receive old roles/password |
| `DaoAuthenticationProvider` | Verifies password/account checks | Each authentication attempt; may use cached user | Can verify against old snapshot if cache is not invalidated |
| `Authentication` | Name, `GrantedAuthority`, principal, details | Typically on fresh authentication or explicit app replacement | Old roles on an active session |
| `SecurityContextRepository` | `Authentication` bound to request/session | Load/save context | Subsequent requests keep using session snapshot |
| OIDC/JWT access token | `sub`, `scope`, `roles`, `iat`, `exp` | When issuer mints a new token | Old token keeps being accepted by Resource Server |
| Application authorization cache | `hasAccess(user,object)` or user/tenant permissions | Per specific TTL/eviction | Stale allow/deny decision despite fresh `Authentication` |
| Gateway/CDN/UI cache | HTTP responses or menus | Cache headers/invalidation | Displays stale roles/data or leaks data |
| Multi-node | Local L1 cache + Redis/DB replica | Propagation after event/TTL | Node A and Node B decide differently |

**Diagnostic rule:** to know which cache to evict, first identify **where** the request gets its `Authentication`. Session-based form login, stateless Basic, and JWT Resource Server load identity differently.

## 4. Username/Password Flow With Caching

In a typical Servlet username/password flow:

```text
POST /login
   |
   v
UsernamePasswordAuthenticationFilter
   |
   v
ProviderManager
   |
   v
DaoAuthenticationProvider
   |  +--> UserDetailsService / UserCache
   |  +--> check account flags
   |  +--> PasswordEncoder.matches(raw, encoded)
   |  +--> build Authentication with authorities
   |
   v
ProviderManager erases credentials if enabled
   |
   v
Success handler + SecurityContextRepository
   |
   v
HTTP session holds SecurityContext (if session-based)
   |
   v
Subsequent GET /admin:
   typically uses Authentication already saved in session
   DOES NOT automatically call UserDetailsService to reload roles every time
```

Spring Security 6.5 docs describe `CachingUserDetailsService`, `UserCache`, and `@Cacheable`. In stateless Basic where passwords must be checked on every request, account caching can reduce lookups; in session-based form login, the saved `Authentication` means an authority change **does not automatically re-run login**.

### Questions to Answer Before Fixing

1. Are you actually using `CachingUserDetailsService`, `AbstractUserDetailsAuthenticationProvider.setUserCache(...)`, `@Cacheable`, Redis, or a custom cache?
2. Does the cache **key by username, email, account ID, or tenant + username**?
3. Does the cache store password hashes and enabled/locked flags, or only authorities?
4. Was the account updated in the primary DB or only visible there vs a read replica?
5. Do incoming requests carry a session cookie or a JWT? Did a fresh login actually happen?
6. Are there multiple app nodes, multiple cache instances, or an IdP issuing roles from another source?
7. Are DB role changes overridden by a custom `GrantedAuthoritiesMapper` / `JwtGrantedAuthoritiesConverter`?
8. Is there an invalidation mechanism on role change/account disable? Does it run **after commit** or before?
9. If a token was issued before the change, does policy allow that token to live until `exp`?
10. Is the UI merely stale while the server is already rejecting properly?

Do not call `SecurityContextHolder.clearContext()` in one request and conclude all sessions are logged out: under normal mechanisms it only affects the current thread's context.

## 5. Caching `UserDetails`: Two Common Approaches

### 5.1. `CachingUserDetailsService`

Spring Security provides `org.springframework.security.authentication.CachingUserDetailsService` to wrap a `UserDetailsService` and store `UserDetails` via `UserCache`. The goal is to avoid querying the datasource on subsequent authentications.

Concept:

```text
loadUserByUsername("alice")
        |
        v
UserCache lookup
        |
        +--> HIT: retrieve stored UserDetails
        |
        `--> MISS: delegate UserDetailsService -> cache -> return user
```

`UserCache` is an abstraction; how entries are stored/removed depends on the implementation, such as `SpringCacheBasedUserCache` backed by Spring Cache. Never assume evicting a cache named "users" automatically clears every active `UserCache`.

### 5.2. Spring Cache `@Cacheable`

Another approach:

```java
@Cacheable(cacheNames = "userDetailsByUsername", key = "#p0")
public UserDetails loadUserByUsername(String username) {
    return repositoryLookup(username);
}
```

This is a **snippet** requiring `@EnableCaching`, a Spring-managed bean, a cache manager, and a real lookup. `#p0` is the method's first parameter.

**Warning 1 — self-invocation:** Spring Cache uses proxies by default. A method in the same bean calling `this.loadUserByUsername(...)` can **bypass the cache proxy**, causing unexpected hits/misses and evictions.

**Warning 2 — mutable objects:** a cache holding the exact `UserDetails` object referenced by `Authentication` can have **the password hash erased from the cached object** when `ProviderManager` erases credentials. This is not merely stale data; it can cause subsequent logins to fail.

**Warning 3 — wrong cache key:** if usernames are not globally unique across tenants, a username-only key can mix roles/identities across tenants. Security-sensitive caches must be scoped by a **server-verified** stable identifier.

**Warning 4 — TTL:** a 5-minute TTL lets stale snapshots survive up to 5 minutes on cache-reading paths (and potentially longer in sessions/tokens). TTL does not guarantee immediate authority revocation.

## 6. Why Does Credential Erasure Relate to Stale Cache?

Spring Security `ProviderManager` defaults to `eraseCredentialsAfterAuthentication=true`. After success, it calls `eraseCredentials()` if the result `Authentication` implements `CredentialsContainer`. `UsernamePasswordAuthenticationToken` can also forward erasure to its principal/details when applicable. `org.springframework.security.core.userdetails.User` implements `CredentialsContainer`.

If `Authentication.getPrincipal()` references **the same mutable `User`** held in cache:

```text
Cached User instance U:
 U.username = alice
 U.password = $2a$...
 U.authorities = [ROLE_USER]
          |
          +--> provider returns Authentication(principal=U)
                         |
                         v
              ProviderManager.eraseCredentials()
                         |
                         v
                   U.password = null
                         |
                         v
    Cache still points to U with null password
    -> next login may fail
```

Spring Security documentation outlines two approaches:

- You can **disable credential erasure** in a cache design sharing the same `UserDetails`, though this keeps credentials in `Authentication`/session longer and requires a security review.
- **Prefer avoiding object sharing**: cache an independent snapshot and build a fresh `UserDetails` on every authentication; or have a custom provider return a principal without the password hash, leaving the cached user unmutated.

**Do not use** `setEraseCredentialsAfterAuthentication(false)` as a "quick fix" without understanding what secrets live in the principal/session. In real applications, keep hashes safely in a dedicated store, never retain raw passwords, and test a second login after the first.

This is a frequent cause of **"login worked at first, then suddenly threw BadCredentialsException even though the password did not change"** after enabling caching.

## 7. A Safer Cache Design: Immutable Snapshots and Fresh Principals

Instead of caching Spring Security's mutable `User`, cache **immutable source data** and build a fresh `UserDetails` on each authentication attempt.

Example snapshot:

```java
package example.stale;

import java.util.Set;

public record AccountSnapshot(
        String username,
        String encodedPassword,
        boolean enabled,
        boolean locked,
        Set<String> authorities,
        long securityVersion) {

    public AccountSnapshot {
        authorities = Set.copyOf(authorities);
    }
}
```

**Note:** the record still holds a **password hash**, not public data. Snapshot caches must have TTLs, restricted access, encryption-at-rest if required, and invalidation on password/factor changes. `Set.copyOf` prevents accidental mutation of authorities; `String` is immutable though it does not guarantee zeroing the hash from RAM.

Cached lookup service (snippet in an app with a real repository):

```java
package example.stale;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedAccountSnapshotService {

    private final AccountRepository repository;

    public CachedAccountSnapshotService(AccountRepository repository) {
        this.repository = repository;
    }

    @Cacheable(cacheNames = "accountSecurity", key = "#p0")
    public AccountSnapshot findByUsername(String username) {
        return repository.findSnapshotByUsername(username)
            .orElseThrow(() -> new
                org.springframework.security.core.userdetails
                    .UsernameNotFoundException("Not found"));
    }
}
```

`AccountRepository` is a **domain interface to implement**; the file above only makes sense in a project with a repository and cache manager. `findSnapshotByUsername` must scope to **the right tenant** in multi-tenant systems, or key by account ID/tenant.

Building a separate `UserDetails` per call:

```java
package example.stale;

import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.stereotype.Service;

@Service
public class SnapshotUserDetailsService implements UserDetailsService {

    private final CachedAccountSnapshotService snapshots;

    public SnapshotUserDetailsService(
            CachedAccountSnapshotService snapshots) {
        this.snapshots = snapshots;
    }

    @Override
    public UserDetails loadUserByUsername(String username) {
        AccountSnapshot s = snapshots.findByUsername(username);

        return User.withUsername(s.username())
            .password(s.encodedPassword())
            .disabled(!s.enabled())
            .accountLocked(s.locked())
            .authorities(s.authorities().toArray(String[]::new))
            .build();
    }
}
```

**Key point:** `CachedAccountSnapshotService` and `SnapshotUserDetailsService` are **two separate beans**. Calling through the cached service bean passes through the Spring Cache proxy. Each time `UserDetailsService` is actually invoked, it creates a **new** `User`; if the principal is erased after login, the cached snapshot is untouched.

This design avoids **object sharing**, but **does not automatically solve stale `securityVersion`/roles**: if the cache is not invalidated, `AccountSnapshot` remains stale. You must add timely eviction.

### Minimal Cache Configuration

In a Spring Boot config that has `spring-context-support` and a cache manager:

```java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CachingConfig {}
```

With `spring-boot-starter-cache` and an appropriate provider (Caffeine/Redis), the app can use caching. `@EnableCaching` **does not pick a TTL by itself**; TTL and sizing are configured on the cache provider. Never use an unbounded global cache for security data.

## 8. Standalone Java 17: Reproducing Cache Staleness and Session Staleness Precisely

The following program uses **plain JDK Java 17**; no Spring/DB required. It simulates a source of truth, a cache, and an `Authentication` snapshot created at login. The goal is to prove in code that **evicting the cache does not change an existing session**.

Create `StaleAuthorityDemo.java`:

```java
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class StaleAuthorityDemo {

    record Account(
            String username, Set<String> roles, long version) {
        Account {
            roles = Set.copyOf(roles);
        }
    }

    record LoginSnapshot(
            String username, Set<String> roles, long version) {}

    private final Map<String, Account> database =
        new ConcurrentHashMap<>();

    private final Map<String, Account> cache =
        new ConcurrentHashMap<>();

    void changeRoles(String username, Set<String> roles) {
        Account old = database.get(username);
        database.put(
            username,
            new Account(username, roles, old.version() + 1)
        );
    }

    void evict(String username) {
        cache.remove(username);
    }

    LoginSnapshot login(String username) {
        Account user = cache.computeIfAbsent(
            username, database::get
        );
        if (user == null) {
            throw new IllegalArgumentException("No such test user");
        }
        return new LoginSnapshot(
            user.username(), user.roles(), user.version()
        );
    }

    static String oneRole(LoginSnapshot snapshot) {
        return snapshot.roles().iterator().next();
    }

    public static void main(String[] args) {
        StaleAuthorityDemo app = new StaleAuthorityDemo();
        app.database.put(
            "alice",
            new Account("alice", Set.of("ROLE_READER"), 1)
        );

        LoginSnapshot oldSession = app.login("alice");

        app.changeRoles("alice", Set.of("ROLE_AUDITOR"));
        LoginSnapshot beforeEvict = app.login("alice");

        app.evict("alice");
        LoginSnapshot afterEvict = app.login("alice");

        System.out.println(
            "initial=" + oneRole(oldSession)
        );
        System.out.println(
            "new-login-before-evict=" + oneRole(beforeEvict)
        );
        System.out.println(
            "new-login-after-evict=" + oneRole(afterEvict)
        );
        System.out.println(
            "existing-session=" + oneRole(oldSession)
        );
        System.out.println(
            "session-stale=" + (
                oldSession.version() !=
                    app.database.get("alice").version()
            )
        );
    }
}
```

Run commands:

```bash
javac StaleAuthorityDemo.java
java StaleAuthorityDemo
```

**Exact expected stdout:**

```text
initial=ROLE_READER
new-login-before-evict=ROLE_READER
new-login-after-evict=ROLE_AUDITOR
existing-session=ROLE_READER
session-stale=true
```

Explanation:
1. Initial load puts account version 1 into the cache; old session holds `ROLE_READER`.
2. DB updates to version 2/`ROLE_AUDITOR`, but cache has not changed: **new login still sees old role**.
3. After eviction, the new login reads DB version 2 and gets the new authorities.
4. The session created at version 1 **was not modified**; a separate reauthentication/reload/revocation policy is needed.

**Limitations:** this is a simple thread-safe Java model to illustrate timing, not a password verifier, with no `HttpSession`, transactions, or JWTs. `Set` in the example holds one role so stdout is deterministic. Real products can have multiple roles and a more complex authorization chain.

## 9. "Cache Was Cleared, Yet Authorities Are Still Stale": Pinpointing the Right Layer

A common scenario:

```text
DB authorities changed
   |
   +-- UserDetails cache: evicted
   |
   +-- Authentication A1 in SecurityContext/HttpSession:
   |          still holds ROLE_ADMIN from previous login
   |
   +-- Signed JWT still holds roles: ["ADMIN"] until expiration
   |
   `-- App permission cache: still has allow=true
```

Why is `@CacheEvict("accountSecurity")` not enough?

- It only affects the **cache with that exact name/manager**.
- An `Authentication` already in `SecurityContextRepository` does not re-query `UserDetailsService` on every request.
- A self-contained JWT carries claims inside the token held by the user; clearing Redis user cache does not alter JWT bytes.
- If a service or gateway permission cache still exists, authorization outcomes can remain stale.
- If eviction ran only on node A, node B may keep its local Caffeine cache.

**Three-test rule:**

| Test | If Still Stale | Top Suspects |
| --- | --- | --- |
| A. Call endpoint with same old session | Stale, while new login is fresh | Session snapshot / application authorization cache |
| B. Log out, log in fresh as real user | Still stale, while DB is fresh | `UserDetails` cache, IdP, role mapper, DB replica |
| C. Send a **new access token** instead of the old one | Old token has old roles, new token is right | JWT/issuer snapshot by design |
| D. Call node A then node B with the same test | One node is stale | L1 cache, replication lag, deployment version/feature flag |

Do not "fix" by refreshing the UI repeatedly before knowing which request the server is actually authorizing.

## 10. `SecurityContext`, HTTP Session, and Loaded Authorities

In Servlet form login, after successful authentication, the result is stored in `SecurityContext` via the session/repository mechanism. Subsequent requests typically restore **the semantically equivalent `Authentication`**, including the authorities from login time.

Example:

```text
POST /login
    user=alice, authorities=[ROLE_ADMIN], securityVersion=12
    |
    v
HttpSession S1 -> SPRING_SECURITY_CONTEXT -> Authentication A1
    |
    v
Admin updates DB authorities=[ROLE_USER], securityVersion=13
    |
    v
GET /admin with JSESSIONID=S1
    |
    v
SecurityContext A1 still has ROLE_ADMIN
    |
    v
hasRole("ADMIN") can still return ALLOW
```

Note: session serialization, copy-on-save, or custom repositories may change the stored object shape. What matters is that **authorization uses the authenticated snapshot**, not that it must be the identical Java object instance across every server.

### Does Changing a Role in the DB Automatically Update the Session?

**There is no default guarantee.** `DaoAuthenticationProvider` is primarily used **during authentication**. `authorizeHttpRequests` and `@PreAuthorize` typically evaluate the current `Authentication`. They do not automatically query the role repository on every request just because a user has an active session.

### Handling Strategies Based on Requirements

- **Low risk:** allow old sessions to survive until TTL or next login if acceptable to the product.
- **Sensitive privileges:** revoke existing sessions when roles change, forcing re-login.
- **Near-real-time updates required:** use `securityVersion`/`permissionsVersion` or a policy check at the request boundary to reject stale `Authentication` objects.
- **Per-object permissions:** query the policy engine/fresh data per resource rather than relying solely on role snapshots.

Never directly mutate `authentication.getAuthorities()` from an admin thread into another session's object. `Authentication`/`GrantedAuthority` can be accessed concurrently; mutating shared objects unexpectedly causes races. **Invalidate/re-authenticate** or create a new `Authentication` through a controlled flow instead.

## 11. Spring Security 6: Custom Login and Saving Context

If an application writes its own login controller/filter, in Spring Security 6.x `SecurityContextHolderFilter` primarily **reads** context from `SecurityContextRepository`; making it take effect on subsequent requests requires **explicit saving**.

Servlet snippet for an **already-verified** authentication:

```java
Authentication authenticated =
    authenticationManager.authenticate(
        UsernamePasswordAuthenticationToken.unauthenticated(
            username, password
        )
    );

SecurityContext context =
    SecurityContextHolder.createEmptyContext();
context.setAuthentication(authenticated);
SecurityContextHolder.setContext(context);

securityContextRepository.saveContext(
    context,
    request,
    response
);
```

This is a **snippet inside server code** that already has `AuthenticationManager`, `SecurityContextRepository`, `HttpServletRequest`, `HttpServletResponse`, and proper session-strategy/CSRF/session-fixation handling. It is not a complete controller. Never build an authenticated token directly from a username without going through a provider.

**Two bugs to distinguish:**
- **Context not saved** → user becomes logged out/anonymous on the next request, not stale authorities.
- **Context saved but not revoked after role change** → user keeps carrying old authorities.

When upgrading Spring Security major/minor versions, re-verify repository and filter-chain designs; do not assume every 5.x example shares the same persistence semantics.

## 12. Session Revocation: Logging Out One Session vs Revoking All

`SecurityContextHolder.clearContext()` clears only the context within the current thread's execution scope; it **does not** scan all of the user's HTTP sessions.

`session.invalidate()` on the current request invalidates only **that session**, not other sessions for the same account across devices.

To **log out all sessions on password/role change**, you need a session index or repository capable of finding sessions by principal/account:

- `SessionRegistry` and Spring Security Servlet session management can be used where configuration/architecture fit.
- With Spring Session (Redis/JDBC), pick a repository that supports finding sessions by principal, verify deletion semantics, and deploy across the right nodes/namespaces.
- On a cluster, an in-memory registry on one instance **does not know all sessions** on other nodes.
- When privileges are revoked urgently, merely marking a session expired might not stop in-flight requests immediately; add policy checks on critical operations.
- For federated/OIDC logins, logging out an app session does not automatically terminate the IdP session or tokens on other clients.

### Session Version Check

A common pattern stores a **security version** in the principal/session at login, e.g. `securityVersion=12`, and stores `currentSecurityVersion=13` in the account repository after a role change. Before sensitive operations:

```text
if session.securityVersion < account.currentSecurityVersion:
    deny / require reauthentication
else:
    apply role + permission policy
```

This can be checked only on sensitive routes or inside an `AuthorizationManager` reading the version from a trusted source. Reading the version from a cache also carries staleness risk; the version source must meet an appropriate SLA.

Never store a browser-sent `rolesFresh=true` boolean. The version in a token/session must be signed/stored by a trusted system; `currentSecurityVersion` must come from an authoritative store or a cache with consistent policy.

## 13. Cache Eviction: Right Key, Right Timing, Right Nodes

### 13.1. An `evict` Call Must Be Exact

With Spring Cache:

```java
Cache cache = cacheManager.getCache("accountSecurity");
if (cache != null) {
    cache.evict(username);
}
```

This is a **server-side snippet**, not a standalone program. `username` must be normalized and mapped to the exact cache key; cache name `accountSecurity` must match `@Cacheable`. In multi-tenant apps, do not evict by global username and assume it suffices.

`@CacheEvict(cacheNames="accountSecurity", key="#p0")` reduces boilerplate, with caveats:
- The method must be invoked through the Spring proxy (self-invocation typically skips advice).
- `beforeInvocation=false` is the default, meaning eviction runs after the method returns normally, **which does not by itself prove it ran after DB commit** if other advice/transaction boundaries exist.
- If the transaction rolls back, the cache must not retain entries for uncommitted data.
- `@CachePut` updates cache, which is not equivalent to revoking old sessions/tokens.
- Forgetting a secondary cache like `permissionsByAccountId` still leaves authorization stale.

### 13.2. Evicting After Commit

Suppose roles are updated inside a transaction:

```text
BEGIN
    UPDATE account_roles ...
    publish "AccountSecurityChanged"
COMMIT
    -> evict the right cache entries
    -> emit revocation event to instances
```

Spring supports `@TransactionalEventListener(phase=AFTER_COMMIT)` to process events **after a successful commit** in a managed transaction:

```java
public record AccountSecurityChanged(
        String accountId,
        String username,
        long newVersion) {}
```

```java
@Component
public class LocalSecurityCacheInvalidator {
    private final CacheManager cacheManager;

    public LocalSecurityCacheInvalidator(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onSecurityChange(AccountSecurityChanged event) {
        Cache users = cacheManager.getCache("accountSecurity");
        if (users != null) {
            users.evict(event.username());
        }

        Cache permissions =
            cacheManager.getCache("permissionsByAccountId");
        if (permissions != null) {
            permissions.evict(event.accountId());
        }
    }
}
```

Imports:

```java
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;
```

The two blocks above are **snippets in two separate Java files** and require event-publishing code inside the role-changing transaction. In real applications:
- Ensure the event is published inside an active transaction.
- Verify the listener runs after commit and events are not lost on process crashes.
- With multi-node caches, a local listener **only affects the current process**.
- When strong reliability/ordering is required, use a **transactional outbox**, event bus, and idempotent consumers, monitoring retries and dead letters.
- Session/token revocation must coordinate with version/cache updates, not merely evict account data.

**Do not mistake `@TransactionalEventListener(AFTER_COMMIT)` for an automatic distributed event bus.**

### 13.3. Cluster Strategies

| Strategy | Pros | Limitations |
| --- | --- | --- |
| Short TTL only | Simple, low coupling | Stale window lasts until TTL expires |
| Distributed Redis cache | Nodes share one store | Local L1 caches and session/JWT snapshots still exist |
| Pub/Sub invalidation | Can be near real-time | Messages can be lost if not durable; requires retry/resync |
| Outbox + consumers | Auditable/retryable/stronger delivery guarantees | More complex; requires lag monitoring |
| Version check before sensitive decisions | Quickly blocks stale privileges | Adds lookup and contention; version source must be trusted |
| Revoke session + token | Strong for high-risk users | Must cover all clients, nodes, and token types |
| Do not cache sensitive privileges | Easier consistency | Higher latency/DB load |

There is no single best choice for every system; start from the **privilege revocation SLA** (immediate, seconds, minutes, or next login only).

## 14. Diagnosing Stale Authorities in OAuth2 Resource Server and JWT

A JWT access token carries signed claims itself. Example at issuance time:

```json
{
  "iss": "https://idp.example.org",
  "sub": "alice",
  "aud": ["reports-api"],
  "iat": 1793940000,
  "exp": 1793940900,
  "scope": "reports:read admin"
}
```

**Timestamps are illustrative only**, not for determining current time. If the issuer minted the token before Alice lost `admin`, the resource server verifying the JWT can still load `SCOPE_admin` until expiration unless additional revocation/version checks exist.

In Spring Security Resource Server, `JwtAuthenticationProvider` uses `JwtDecoder` to verify the token and `JwtAuthenticationConverter` builds authorities from claims; by default `scope`/`scp` becomes `SCOPE_...`. **`DaoAuthenticationProvider` / `UserDetailsService` do not run by default on every JWT request**.

Therefore:
- Clearing the password-login `UserDetails` cache **does not modify already-issued JWTs**.
- Clearing another app's HTTP session **does not automatically revoke JWTs**.
- Updating `roles` in the database **does not alter bytes of a JWT stored on a client**.
- Changing role mapping on the resource server alters **how claims are interpreted**, taking effect only when the converter runs with the new config; never silently turn an under-privileged token into a privileged one.
- A refresh token can issue a new access token carrying updated privileges **if the issuer loads current account state**; if the issuer also keeps stale claims, the new token remains stale.
- An old JWT session can stay valid after an account is disabled if the server checks only signature/`exp`/`iss` without checking account state/revocation.

### Options When Revocation Is Required

1. **Short-lived access tokens** + refresh tokens with rotation/revalidation: bounds the stale window without immediate mid-token revocation.
2. **Token revocation** via `jti`/token hash or auth-version checked at the API boundary: incurs lookup cost; define consistency clearly.
3. **OAuth2 introspection / opaque tokens**: checks token state via the authorization server or an introspection cache with an acceptable TTL.
4. **Version claim** (`security_version`) inside the token compared against current server version at the API: old tokens are blocked once the version increments.
5. **Dynamic policy/permission checks** for sensitive actions: do not rely solely on frozen roles inside the JWT.
6. **Issuer push events** to consumers if architecture requires it, with retries and verification.

An unexpired token should not be accepted blindly forever; that is an **architectural decision**. When emergency account lock is required, prefer a boundary with revocation meeting the defined SLA.

## 15. SSO/OIDC, SAML, LDAP: Authority Sources Can Live Outside the Application

Several flows do not use `DaoAuthenticationProvider`:

- **OIDC login**: principal/authorities may be built from ID Token/UserInfo, IdP groups, or custom mappers; the app session can retain login-time results.
- **SAML2 login**: responses/assertions and local authority mappers create a session snapshot; later LDAP group edits do not change an already-received assertion.
- **LDAP bind/search**: LDAP groups/attributes may be cached in the app, directory client, LDAP proxy, or replica. Locking an LDAP account does not automatically destroy an already-issued app session.
- **OAuth2 access token**: scopes come from the issuer; the resource server verifies the token and may not query LDAP/DB on every request.
- **Passkey/WebAuthn**: public-key credential verification does not automatically reload fresh roles from the repository if a session or mapper cached old authorities.

To diagnose, record **the authority source actually in use**: `Authentication.getClass()`, principal type, group mapper, issuer/subject, and storage location. Do not touch random caches.

### OIDC and "IdP Logout"

Logging out a session at the Identity Provider does not automatically clear:
- The RP/app session cookie unless Single Logout (back-channel/front-channel) is implemented per contract.
- Already-issued, active access tokens.
- Account/role snapshots in the application cache.

If an app must immediately revoke privileges when someone is removed from an IdP group, it needs provisioning/deprovisioning contracts, session termination, or fresh authorization checks — not merely re-displaying the login screen.

## 16. Is Authority Mapping Right? Avoid Misdiagnosing as Stale Cache

**Sometimes authorities are not stale at all** — the app is reading the wrong format.

For instance, DB stores `ADMIN`, while the Spring rule checks:

```java
.requestMatchers("/admin/**").hasRole("ADMIN")
```

`hasRole("ADMIN")` checks authority `ROLE_ADMIN` by default, not the plain string `ADMIN`. With a JWT resource server, scope `reports:read` typically becomes `SCOPE_reports:read`, not `ROLE_reports:read`.

| Source | Loaded Value | Rule | Expected Outcome |
| --- | --- | --- | --- |
| `User.withUsername(...).roles("ADMIN")` | `ROLE_ADMIN` | `hasRole("ADMIN")` | Allowed |
| `.authorities("ADMIN")` | `ADMIN` | `hasRole("ADMIN")` | Fails default prefix check |
| JWT `"scope":"reports:read"` | `SCOPE_reports:read` | `hasAuthority("SCOPE_reports:read")` | Allowed |
| DB roles `[USER, AUDITOR]` mapped to `ROLE_...` | `ROLE_USER`, `ROLE_AUDITOR` | `hasRole("ADMIN")` | Denied |
| Claim `roles:["ADMIN"]` not read by converter | Possibly only scope authorities | `hasRole("ADMIN")` | Denied until mapped |

When a DB account was just granted `ADMIN` yet the session lacks the role, classify step-by-step:

```text
(1) Does DB/snapshot source have ADMIN?
(2) Does loader/mapper return ROLE_ADMIN?
(3) Does the new Authentication have ROLE_ADMIN?
(4) Does the Authentication in current session have ROLE_ADMIN?
(5) Does AuthorizationManager use the right rule and right chain?
```

If (1) yes, (2) no: source/mapping/cache. If (2) yes, (3) no: provider/mapper. If (3) yes, (4) no: old session. If (4) yes, (5) denies: matcher/rule/method security or another policy.

### Checking `@PreAuthorize` and Custom Permission Evaluators

Beyond URL rules, method security can use:

```java
@PreAuthorize("hasAuthority('SCOPE_reports:read')")
public Report readReport(String id) { ... }
```

A custom `PermissionEvaluator` or `AuthorizationManager` can **have its own decision cache**, independent of `UserDetails`. Tests must cover this layer too. Conversely, a `permitAll` controller cannot be locked down merely by clearing user caches.

## 17. Symptom-Based Diagnostic Runbook

| Symptom | Quick Test | Primary Suspect |
| --- | --- | --- |
| Revoked ADMIN yet old tab still gets in | Log in fresh from a separate browser | `Authentication` in session still holds old roles |
| New login still receives old roles | Compare loader, cache hit, and DB version | `UserDetails`/role cache or IdP/replica |
| One node updated, another did not | Record node ID in internal telemetry | L1 cache, propagation, deployment mismatch |
| Changed password yet old password still logs in | Test **new login** with old password (test account) | Cached old password hash / another IdP |
| First login works, second fails as bad password | Inspect cached `UserDetails.getPassword()` | Mutable cached `User` erased by `eraseCredentials` |
| Disabled account yet old session gets 200 | Test old session vs new session | Missing session revocation/version check |
| `@PreAuthorize` does not see new authorities | Inspect authorities on `Authentication` | Session snapshot or custom method-auth cache |
| Old JWT still retains admin privileges | Decode claims + `iat`/`exp` **safely**, verify issuer | Token has old privileges; missing revocation |
| New JWT also retains old privileges | Inspect claims newly minted by issuer | IdP/authorization server claims cache |
| UI menu still shows Admin while API returns 403 | Call API directly with a test client | Stale frontend/browser cache, not server authorization |
| DB is updated yet role changes lag | Read primary/replica under control | Replication lag / transaction ordering |
| One tenant sees another tenant's authorities | Test by account/tenant key | Cache key or query missing tenant isolation |
| Logged out yet Bearer token still works | Send unexpired JWT to test resource server | Session logout does not revoke tokens |
| Only legacy API has wrong privileges | Inspect `SecurityFilterChain` / matchers | Inconsistent protection configuration |

**Never use real customer data to test bypass possibilities.** Use authorized test accounts, synthetic roles/tenants, and controlled staging environments.

## 18. Evidence Collection Without Leaking Secrets

During a "stale privileges" incident, store under role-restricted telemetry:

- Request trace ID, endpoint, and request type.
- `Authentication` implementation name, verified **internal principal ID**, and tenant ID.
- **Normalized** authority list, or a hash/version/compact authority set in sensitive environments.
- Authentication timestamp (`auth_time` from a trusted source if present) and session/security version.
- Cache name, **pseudonymized** key, hit/miss, TTL, node/instance ID.
- Account/permissions version in the DB and last-updated timestamp.
- Token `iat`, `exp`, issuer/audience, and appropriately **hashed/encrypted** `jti`; never store raw JWTs.
- Authorization decision (allow/deny) and the applied rule/method.
- Invalidation events: change time, publish/receive time, propagation lag per node.
- Transaction commit time and read-replica lag where relevant.

**Strictly avoid** logging:
- Raw passwords, password hashes, OTPs, recovery codes.
- `Authorization` headers, `JSESSIONID`, refresh tokens, raw JWTs.
- Full `UserDetails.toString()` if a custom principal holds PII/secrets.
- Full session/claims JSON without legitimate need and read-access controls.

For debugging, prefer an internal maintenance-role endpoint returning minimal metadata and disabled in production; never expose a public `"getUserAuthorities?email=..."` API that could enumerate memberships/roles.

## 19. JUnit 5: Component Test Reproducing Stale Roles and Fixing via Eviction

The example below uses **real Spring Security**, without a Spring Boot server. It uses a `ConcurrentHashMap` mock database, a separate snapshot cache, `DaoAuthenticationProvider`, and `ProviderManager`. Goal: demonstrate stale authorities before eviction, fresh authorities after eviction, that old session/authentication snapshots stay unchanged, and that cached data is not corrupted by `eraseCredentials()`.

Create `src/test/java/example/stale/StaleAuthoritiesComponentTest.java`:

```java
package example.stale;

import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.stream.Collectors;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.ProviderManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.authentication.dao.DaoAuthenticationProvider;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetails;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.bcrypt.BCryptPasswordEncoder;
import org.springframework.security.crypto.password.PasswordEncoder;

import static org.junit.jupiter.api.Assertions.*;

class StaleAuthoritiesComponentTest {

    record AccountData(
        String hash, Set<String> authorities, boolean enabled, long version) {
        AccountData {
            authorities = Set.copyOf(authorities);
        }
    }

    private final Map<String, AccountData> database =
        new ConcurrentHashMap<>();
    private final Map<String, AccountData> cache =
        new ConcurrentHashMap<>();

    private final PasswordEncoder encoder =
        new BCryptPasswordEncoder(4); // Test-only cost.

    private AuthenticationManager manager;

    @BeforeEach
    void setUp() {
        database.clear();
        cache.clear();
        database.put(
            "alice",
            new AccountData(
                encoder.encode("old-password"),
                Set.of("ROLE_READER"),
                true,
                1
            )
        );

        UserDetailsService loader = username -> {
            AccountData data = cache.computeIfAbsent(
                username,
                key -> database.get(key)
            );
            if (data == null) {
                throw new UsernameNotFoundException("Not found");
            }
            // Fresh UserDetails per request/attempt; cached data does not
            // lose its password hash when ProviderManager erases credentials.
            return User.withUsername(username)
                .password(data.hash())
                .disabled(!data.enabled())
                .authorities(data.authorities().toArray(String[]::new))
                .build();
        };

        DaoAuthenticationProvider dao =
            new DaoAuthenticationProvider(loader);
        dao.setPasswordEncoder(encoder);
        manager = new ProviderManager(List.of(dao));
    }

    private Authentication login(String password) {
        return manager.authenticate(
            UsernamePasswordAuthenticationToken.unauthenticated(
                "alice", password
            )
        );
    }

    private Set<String> authorities(Authentication auth) {
        return auth.getAuthorities().stream()
            .map(GrantedAuthority::getAuthority)
            .collect(Collectors.toSet());
    }

    @Test
    void newLoginSeesNewRolesOnlyAfterEviction() {
        Authentication first = login("old-password");
        assertEquals(Set.of("ROLE_READER"), authorities(first));

        AccountData old = database.get("alice");
        database.put(
            "alice",
            new AccountData(
                old.hash(),
                Set.of("ROLE_AUDITOR"),
                true,
                old.version() + 1
            )
        );

        Authentication staleNewLogin = login("old-password");
        assertEquals(
            Set.of("ROLE_READER"), authorities(staleNewLogin)
        );

        cache.remove("alice");
        Authentication freshNewLogin = login("old-password");
        assertEquals(
            Set.of("ROLE_AUDITOR"), authorities(freshNewLogin)
        );

        // Authentication created before the role change stays unchanged.
        assertEquals(Set.of("ROLE_READER"), authorities(first));
    }

    @Test
    void disableMustInvalidateLoadedAccountForNewLogin() {
        Authentication first = login("old-password");
        assertTrue(first.isAuthenticated());

        AccountData old = database.get("alice");
        database.put(
            "alice",
            new AccountData(
                old.hash(),
                old.authorities(),
                false,
                old.version() + 1
            )
        );

        // Proves only the cache stale window: still able to log in.
        assertTrue(login("old-password").isAuthenticated());

        cache.remove("alice");

        assertThrows(
            DisabledException.class,
            () -> login("old-password")
        );
    }

    @Test
    void passwordChangeNeedsCacheInvalidation() {
        login("old-password"); // Populate cache.
        AccountData old = database.get("alice");

        database.put(
            "alice",
            new AccountData(
                encoder.encode("new-password"),
                old.authorities(),
                true,
                old.version() + 1
            )
        );

        // Before eviction, cache still holds the old password hash.
        assertTrue(login("old-password").isAuthenticated());
        assertThrows(
            BadCredentialsException.class,
            () -> login("new-password")
        );

        cache.remove("alice");

        assertThrows(
            BadCredentialsException.class,
            () -> login("old-password")
        );
        assertTrue(login("new-password").isAuthenticated());
    }

    @Test
    void credentialErasureCannotMutateCachedSnapshot() {
        Authentication result = login("old-password");

        assertNull(result.getCredentials());
        assertTrue(result.getPrincipal() instanceof UserDetails);
        assertNull(
            ((UserDetails) result.getPrincipal()).getPassword()
        );

        AccountData cached = cache.get("alice");
        assertNotNull(cached);
        assertNotNull(cached.hash());
        assertTrue(encoder.matches("old-password", cached.hash()));

        // Second login does not break because the cached object is independent.
        assertTrue(login("old-password").isAuthenticated());
    }
}
```

Run in a Spring Boot 3.x/Gradle project with `spring-boot-starter-security` and `spring-boot-starter-test`:

```bash
./gradlew test --tests example.stale.StaleAuthoritiesComponentTest
```

**Expected:** 4 `@Test` methods pass. They deliberately model **the security window before eviction** to expose staleness behavior. In production, never treat old passwords still working as acceptable behavior; integrate invalidation into the real workflow.

### Why Is This Test More Trustworthy Than `@WithMockUser`?

`@WithMockUser(roles="ADMIN")` builds a fake `Authentication`, skipping `UserDetailsService`, password hashes, and cache. The Section 19 test actually invokes `DaoAuthenticationProvider` via `ProviderManager`, reads roles from the (intentionally cached) loader, and observes authorities and erasure.

**However, this test does not cover HTTP sessions/JWTs.** To test existing sessions, write separate filter-chain/session tests or resource-level version checks. Never alter test assertions to pretend an old `Authentication` updates itself after eviction.

## 20. HTTP Integration Tests: Distinguishing Cache Miss From Existing Session

An end-to-end form-login test should follow this sequence:

```text
1. Create test account Alice: ROLE_ADMIN, enabled=true, version=1.
2. Browser A (cookie jar A) logs in as Alice and GET /admin -> 200.
3. Admin changes Alice's role to ROLE_USER, version=2, COMMIT.
4. Invalidate UserDetails/permission caches across nodes.
5. Browser A KEEPS old JSESSIONID, GET /admin.
6. Browser B (cookie jar B) logs in as Alice FRESH, GET /admin.
7. Compare each outcome against the revocation policy.
```

If policy requires **immediate revocation**, both steps 5 and 6 must deny admin access. If the app only evicts `UserDetails`, step 6 may pass while step 5 still returns 200.

### MockMvc: Login and Checking Old vs New Sessions

The following is a **snippet** for an integration test in an app **with real form login and `MockMvc`**, a test account repository capable of updating roles, and an implemented eviction service:

```java
MvcResult first = mvc.perform(
        formLogin().user("alice").password("test-password"))
    .andExpect(authenticated().withUsername("alice"))
    .andReturn();

MockHttpSession oldSession =
    (MockHttpSession) first.getRequest().getSession(false);

// Change role via business service, then commit/invalidate.
// accountService.replaceAuthorities("alice", Set.of("ROLE_USER"));

MvcResult second = mvc.perform(
        formLogin().user("alice").password("test-password"))
    .andExpect(authenticated().withUsername("alice"))
    .andReturn();

MockHttpSession newSession =
    (MockHttpSession) second.getRequest().getSession(false);

assertNotEquals(oldSession.getId(), newSession.getId());
```

Imports (in a test class with `mvc` and required beans):

```java
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.springframework.security.test.web.servlet.request.SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response.SecurityMockMvcResultMatchers.authenticated;
```

This is only a **skeleton for session isolation checks**: you must add the actual role-change step and assert `get("/admin").session(oldSession)` and `get("/admin").session(newSession)` per policy after commit. Never skip that step and claim stale-authority testing is complete.

**Common testing mistake:** using `@WithMockUser` for `/admin` after changing roles; that test uses a fixture authority and checks neither sessions nor real logins.

### For Resource Server

Use two access tokens belonging to **the same account**:
- Token T1 issued before privilege removal.
- Token T2 issued after privilege removal.
- Send T1/T2 to the API, verifying issuer/audience/exp/role and HTTP 200/403.
- If policy requires immediate revocation of T1, verify revocation/version logic; checking T2 alone is insufficient.
- Do not use `.jwt()` mock tests to claim you verified signatures or fresh issuer claims; it only tests authorization with mock claims.

## 21. Race Conditions: Concurrent Authority Changes and Logins

Suppose:

```text
Thread LOGIN                         Thread ADMIN
------------                         ------------
load UserDetails version 5
                                     BEGIN
                                     UPDATE roles -> version 6
                                     COMMIT
authenticate with version 5
save HTTP session -> AUTH version 5
                                     publish invalidation event
```

Even if cache eviction runs after commit, login can build an `Authentication` from a snapshot read **before** the change. If the system requires **strong revocation**, add a blocking check when an older version is used rather than relying solely on eviction for future loads.

One approach:
- Every security change increments `securityVersion` atomically.
- Every `Authentication`/session stores the version at authentication time.
- When a sensitive request begins, compare against the current authoritative version.
- If the version is lower, deny and require reauthentication.
- When an API performs a long/sensitive operation, consider re-checking at the **business commit boundary** to avoid time-of-check/time-of-use gaps.
- For tokens, the issuer embeds a security version or the API checks the account version for the token subject.
- Event consumers treat versions **monotonically**: older events must never overwrite newer state.

Do not "fix" by calling `evict()` twice and hoping the race vanishes; what you need is a **verifiable consistency invariant**.

### Why Doesn't `@CacheEvict` Provide System-Wide Atomicity?

Database transactions and caches (especially Redis/Caffeine) do not typically participate in **the same ACID transaction**. A window exists between DB commit and cache invalidation. Event delivery can be delayed or reordered. For highly sensitive privileges, an authoritative version check or reliable session/token revocation gives stronger guarantees than TTL alone.

## 22. Asynchronous Checks Across Multiple Instances

Tests running only a single Spring Boot instance rarely reproduce:

```text
T1 node-A cached Alice v5
T2 node-B cached Alice v5
T3 role updated to v6
T4 event delivered to A, B has not received it yet
T5 request A -> role v6
T6 request B -> role v5
```

### Controlled Staging Test Scenario

1. Start two instances with local L1 caches sharing the same test database.
2. Have Alice log in / call a permission endpoint through both A and B to warm up caches.
3. Change roles through a trusted admin path and wait for DB COMMIT.
4. Send new requests to each instance, recording node ID and authority version.
5. Verify propagation within the SLA, e.g. **N seconds defined by policy**.
6. Test a consumer temporarily going offline then reconnecting: is there replay/resync/outbox?
7. Test out-of-order events: v8 before v7; v7 must not overwrite newer privileges.
8. Verify old sessions and old JWTs separately; do not assume node cache invalidation solved everything.
9. Test cache misses during primary/replica lag and retries; data must never pull the wrong tenant.
10. Ensure tests never flush caches shared with production or log out real users.

Distributed staleness is not necessarily a "Spring Security framework bug"; it can be an **external invalidation system** failing to meet consistency requirements.

## 23. Key Design and Security-Sensitive Caches

An insufficiently discriminating key can turn stale data into a **cross-user privilege leak**:

```text
Cache key = username
Tenant A: username=admin, ROLE_ADMIN
Tenant B: username=admin, ROLE_USER
```

If both share key `admin`, tenant A's `UserDetails` could be returned to tenant B. That is not just slow role updates — it is a severe tenant-isolation failure.

Rules:
- Use a **stable account ID** combined with **tenant ID** in multi-tenant systems.
- Verify tenant membership from server/IdP-verified data; never trust an unverified self-declared `X-Tenant` header.
- Keys for permission-decision caches must include principal/account, tenant, resource, action, policy version, and any condition affecting the decision.
- Avoid keys consisting only of `ROLE_ADMIN` or `/api/resource` for per-user decisions.
- Never use raw JWTs/passwords as cache keys or log entries.
- Invalidate on account rename, merge, role change, or tenant transfer.
- Avoid caching "allow" decisions indefinitely without tying them to a policy version.
- Monitor memory growth and eviction rates to prevent OOM or abnormal latency spikes.

**Note:** `UserDetailsService.loadUserByUsername` takes only a `username` parameter in its interface. If your product allows duplicate usernames across tenants, enforce a full identity contract across the authentication and repository layers; implicitly pulling tenant from an unmanaged static/ThreadLocal can cause cross-tenant data leaks.

## 24. Cache TTL, Negative Caching, and Read Replicas

### TTL Should Be Risk-Based

| Data Kind | Risk If Stale | Protection Direction |
| --- | --- | --- |
| Display name/avatar | Typically low | Longer TTL if UX allows |
| `enabled` / `locked` | High: locked user still logs in | Immediate eviction, version/revocation for active sessions |
| Password hash | High: old password still verifies | Evict on password change, session/token policy |
| Admin roles | High: revoked privileges remain active | Session revoke or version check, evict across all nodes |
| UI feature flags | Typically medium/low | Cache + independent server authorization |
| Scope in access token | Potentially high | Short-lived tokens + revocation/claims refresh |
| Public metadata | Typically low | Cache more aggressively, never mix with authorization |

**Do not use a single default TTL for password hashes, roles, and avatars** when SLAs and risks differ.

### Negative Caching

Caching "username does not exist" can also cause issues: a newly created account cannot log in until the negative entry expires, or a username changes while the negative entry lingers. Negative caching needs appropriate TTL/eviction and must not become a **user enumeration oracle** via differing responses.

### Read Replica Lag

Some systems write account updates to the primary while `UserDetailsService` reads a replica. Even after the cache is cleared, the replica still holds old roles, causing the cache to **refill immediately with stale values**. Measure:
- Commit LSN/version on the primary.
- Version returned by the replica.
- Read-your-writes routing for security-sensitive changes.
- Cache refills after eviction while the replica lags.

If privilege revocation must take effect immediately, read the authoritative store for critical decisions or use a version/revocation mechanism meeting the SLA rather than merely shrinking TTL.

## 25. WebFlux and Redis: Same Problem, Different Context

In WebFlux:
- `Authentication` lives in **Reactor Context** (`ReactiveSecurityContextHolder`), not just `ThreadLocal` `SecurityContextHolder`.
- `ReactiveUserDetailsService` data may be cached in a reactive lookup or another store.
- `SecurityWebFilterChain` and `ServerSecurityContextRepository` have reactive semantics.
- A `Mono<UserDetails>`/`Mono<Permission>` with `.cache()` at singleton scope can accidentally share data across accounts if unscoped.
- Redis or reactive HTTP sessions still have TTL and revocation constraints.
- Never call `.block()` on the event loop to force reading fresh roles; use a reactive datasource or suitable policy.

**The diagnostic approach remains the same:** check data source, cache, authenticated principal snapshot, session/token, policy mapper, and real request. However, **the APIs do not mirror Servlet**; do not copy `HttpSecurity`/`SecurityFilterChain` into WebFlux apps using `ServerHttpSecurity`/`SecurityWebFilterChain`.

## 26. Anti-Patterns to Avoid

**Wrong 1: "After changing roles, just clear the cache."**  
Insufficient if already-issued sessions/JWTs still carry old roles. Define the revocation SLA and cover every entry path.

**Wrong 2: "Every request automatically calls `UserDetailsService`."**  
False in session-based login; many requests simply restore `Authentication` from the session.

**Wrong 3: "JWTs automatically reflect new DB roles."**  
Self-contained JWTs retain signed claims until expiration unless there is a revocation/version/policy check layer.

**Wrong 4: "Disable `eraseCredentialsAfterAuthentication` to avoid errors."**  
Can keep credentials in memory/sessions longer; prefer independent copies/snapshots so caches are not mutated.

**Wrong 5: "Using `@CacheEvict` guarantees post-commit eviction."**  
Does not automatically cover every transaction/distributed-cache layer; review advice ordering and event timing.

**Wrong 6: "One node received the event, so all nodes are updated."**  
L1 caches and event propagation need observability/retries/resync.

**Wrong 7: "Use `SecurityContextHolder.clearContext()` to log out all devices."**  
Affects only the current thread's local context, not all sessions/JWTs.

**Wrong 8: "Session logout invalidates JWTs."**  
No guarantee; tokens have their own `exp` and separate revocation mechanisms.

**Wrong 9: "Testing with `@WithMockUser` alone is enough."**  
It mocks `Authentication` and tests neither real caches, loaders, logins, nor sessions.

**Wrong 10: "If a role is in the DB, `hasRole` will definitely see it."**  
Check `ROLE_` prefixes and mappings; JWT scopes default to the `SCOPE_` prefix.

**Wrong 11: "Adding `synchronized` eliminates staleness."**  
Synchronizing one process does not update other nodes' caches, issued sessions, or JWTs.

**Wrong 12: "Read roles from a client header to refresh UI quickly."**  
Never grant privileges from unverified `X-Role`/JSON fields.

**Wrong 13: "Store roles in Redis under the same username key across all tenants."**  
Can mix identities and roles across tenants; keys must include account/tenant scope.

**Wrong 14: "Lowering TTL solves it immediately."**  
TTL only bounds staleness of **one cache**; it does not address sessions, JWTs, or replication lag.

**Wrong 15: "When a user's role changes, mutate `Authentication` on every request."**  
Mutating shared objects invites races and ignores issuers/tokens. Explicit reauthentication/revocation/version checks are cleaner.

## 27. Short Ordered Investigation Workflow

When receiving a "privileges did not update" ticket, follow a repeatable checklist:

1. **Record expectations:** which privilege changed, by whom, exact commit time, and effective deadline per policy.
2. **Identify the endpoint:** is it returning 200, 401, 403, or is only the UI displaying stale state?
3. **Identify the authentication mechanism:** form session, Basic, JWT, SSO, opaque token, WebFlux?
4. **Record a safe fingerprint:** principal ID, authorities, tenant, auth type, `securityVersion`, `iat`, node ID, trace ID.
5. **Check primary database and source of truth:** did the new role/version/flags actually commit?
6. **Trace loader/cache:** which cache hit, which key, which snapshot version, how much TTL remains?
7. **Test a fresh login from a separate client** without old sessions/cookies; record resulting authorities.
8. **Test the old session/token** separately to detect unrevoked snapshots.
9. **Verify mappers/rules:** `ROLE_`/`SCOPE_`, `GrantedAuthoritiesMapper`, `JwtGrantedAuthoritiesConverter`, method security, matcher chains.
10. **Test each app node** and backend replica with a test account; measure propagation.
11. **Fix the right layer:** post-commit cache eviction, session/token revocation, version check, or mapper/DB replica fix.
12. **Add regression tests** for fresh logins, old sessions, and old tokens; measure against SLA rather than just one passing request.

### Actionable Conclusion Examples

**Case 1:** "DB v18, cache v17; logout/fresh login still gets v17."  
Fix direction: cache invalidation or cache refill/replica handling, without touching the existing session first.

**Case 2:** "DB v18, cache v18, fresh login is right; old session still gets v17."  
Fix direction: session revocation or version check, no need to clear the cache again.

**Case 3:** "Resource Server sees JWT `iat` before revocation with 20 minutes left on `exp`; new token is right."  
Fix direction: revocation/short TTL/dynamic authorization per SLA; do not tweak `DaoAuthenticationProvider`.

**Case 4:** "`Authentication` has `SCOPE_read`, rule requires `ROLE_read`."  
Fix direction: mapper or authorization rule, not cache.

**Case 5:** "Node A v18, node B v17; only B had a cache hit."  
Fix direction: distributed invalidation/TTL or centralized version, rather than telling users to retry randomly.

## 28. QA Checklist When Fixing the Issue

### Data and Cache

- [ ] Source of truth has clear versioning/`updatedAt` and commit ordering.
- [ ] Current caching configs are inventoried: `UserCache`, Spring Cache, Redis, Caffeine, local maps.
- [ ] Cache keys distinguish tenant + account; no user-controlled roles/tenants.
- [ ] Eviction targets the right cache name/key, actually runs after commit, and reaches relevant nodes.
- [ ] Recovery for lost/misordered events includes monitoring and replay/resync.
- [ ] Password hashes in cached snapshots are not erased by `ProviderManager` via shared objects.
- [ ] Negative caches and DB replicas do not hold stale snapshots past SLA.
- [ ] Permission/decision caches have their own invalidation.
- [ ] Security data TTLs are risk-based, not infinite defaults.

### Authentication / Session / Token

- [ ] **Fresh** logins receive the right roles/flags/password hashes.
- [ ] **Existing** sessions are revoked/re-authenticated or version-checked per policy.
- [ ] Custom `SecurityContextRepository` never saves context for the wrong account/session.
- [ ] Password change / account disable invalidates sessions/remember-me tokens per policy.
- [ ] Old JWTs cannot perform sensitive actions if revocation SLA requires blocking them.
- [ ] Refresh tokens mint new tokens using current account data rather than copying stale roles forever.
- [ ] SSO/IdP group mappings align at both token issuer and receiver.
- [ ] No legacy endpoint or separate filter chain bypasses revocation checks.
- [ ] `@PreAuthorize` and object-level permissions verify the right principal/tenant.
- [ ] Disabled accounts cannot bypass via weaker passkey/OTT/SSO/recovery flows.

### Testing and Operations

- [ ] JUnit component tests verify stale cache before eviction and fresh load after eviction.
- [ ] Tests confirm credential erasure does not corrupt cached data.
- [ ] HTTP tests use two independent browsers/sessions, distinguishing old vs new sessions.
- [ ] Token tests cover T1 (pre-revocation) and T2 (post-revocation).
- [ ] Cluster tests use at least two nodes and cover delayed events.
- [ ] Tests cover role revoke, role grant, password change, account disable/lock, and tenant changes.
- [ ] Propagation lag and authorization deny/allow meet SLA.
- [ ] No secrets/PII in logs; trace ID/actor/version/cache-hit metadata suffice for investigation.
- [ ] Password hashing/credential erasure is never disabled just to make tests pass.
- [ ] Races between login and role updates, and cache misses during replica lag, have been reviewed.
- [ ] Runbook exists for emergency revocation covering both session and token paths.

## 29. Self-Check Questions

**Q1:** After revoking `ROLE_ADMIN` and clearing the `UserDetails` cache, the browser can still access `/admin`. What should you check next?

**A:** Inspect the `Authentication` saved in the session and the revocation/version policy. Cache eviction does not automatically update authorities on an existing session.

**Q2:** After logging out and logging back in, old roles still appear. Is it definitely the session?

**A:** No. Check the loader, cache hits/misses, DB primary/replica, IdP claims, and role mapper. The old session is gone, yet the fresh login source may still be stale.

**Q3:** First login works, second login fails after enabling caching. Why?

**A:** The cached `UserDetails` and authentication principal may reference the same mutable `User`; `ProviderManager.eraseCredentials()` clears the password on the cached object. Use an independent snapshot and build a fresh principal.

**Q4:** A user holds an unexpired JWT containing role `ADMIN`. Does removing the role in the DB and clearing Redis fix the JWT?

**A:** No. A JWT carries signed claims. You need token revocation/version checking/short TTL or appropriate reauthorization.

**Q5:** Why might `@CacheEvict` on an internal service fail to run?

**A:** With default Spring AOP proxies, self-invocation within the same bean bypasses the proxy; cache advice may not execute.

**Q6:** The same user gets 403 on node A and 200 on node B after privilege revocation. What should you compare first?

**A:** The active session/token, `Authentication` version, cache hit/miss, node ID, replica source, and invalidation event delivery — do not blame Spring Security blindly.

**Q7:** Why might an `ADMIN` privilege in the DB fail to satisfy `hasRole("ADMIN")`?

**A:** Because `hasRole` expects authority `ROLE_ADMIN` by default. If the mapper produces only `ADMIN`, that is a mapping bug, not stale cache.

**Q8:** Should you flush all of Redis in production every time a role changes?

**A:** No. That can trigger load spikes, disrupt unrelated sessions/data, and still fails to fix JWTs/sessions. Invalidate the right key, right cache, at the right time.

**Q9:** In session login, can `SecurityContextHolder.clearContext()` serve as "logout all devices"?

**A:** No. It clears only the context in the current thread; you need an actual session/token revocation mechanism.

**Q10:** Why is a security version needed even when using a very short cache TTL?

**A:** Cache TTL does not address snapshots in sessions/JWTs and leaves race windows. Version checks establish a condition to reject stale `Authentication` objects at protected boundaries.

## 30. Summary

When account/authority information appears stale, **identify which snapshot is being used** before changing configuration:

- **Stale `UserDetails` cache** causes **new authentications** to keep loading old data.
- **Stale `Authentication`/session** causes **requests on an active session** to carry old authorities even after the DB and cache updated.
- **Stale JWT/SSO claims** cause resource servers to keep accepting privileges issued before the change.
- **Permission/data caches, multiple nodes, and DB replicas** can make decisions diverge across requests/instances.
- **Mapper/authorization rule bugs** can look like stale cache when new privileges were simply never mapped properly.

Remediation must align with the **effective-privilege SLA**: update the source of truth, invalidate the right caches **after commit**, synchronize/monitor nodes, and revoke sessions/tokens or check security versions where guaranteed enforcement is needed. In Spring Security, enabling `@Cacheable`, `SessionRegistry`, or JWT Resource Server alone does not solve the full problem automatically.

Testing must cover **new logins, old sessions, old tokens, cache hits/misses, role/password/account-status changes, and multiple nodes**. Only by testing both the authentication-issuance path and the active authorization path can the system guarantee privileges are revoked or updated on time.

## 31. Official References

- Spring Security 6.5 — Caching `UserDetails`: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/caching.html
- Spring Security 6.5 — Authentication Architecture / `ProviderManager` erasure: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html
- Spring Security 6.5 — Authentication Persistence and Session Management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html
- Spring Security 6.5 — Session Management migrations / explicit context save: https://docs.spring.io/spring-security/reference/6.5/migration/servlet/session-management.html
- Spring Security 6.5 — `UserDetails` and credentials management: https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/user-details.html
- Spring Security — OAuth2 Resource Server JWT authorities and claims: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — Authorize HttpServletRequests: https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html
- Spring Framework — Cache Annotations (`@Cacheable`, `@CacheEvict`, proxies): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Transaction-bound Events (`@TransactionalEventListener`): https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Session — HTTP Session and indexed session repositories: https://docs.spring.io/spring-session/reference/http-session.html
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — Session Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html
