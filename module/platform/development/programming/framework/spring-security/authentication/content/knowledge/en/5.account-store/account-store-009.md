# Caching Policies, Revocation, and Consistency When Account Data Changes

**Module:** Spring Security – authentication. **Knowledge group:** Account Store.

## 1. The Problem: Account Data Changes, Yet the System Holds Stale State

Suppose user `an` logs in at 09:00 with `ROLE_ADMIN`. At 09:05, an administrator revokes the admin role. The database now stores `ROLE_USER`, yet the user still holds an active HTTP session whose `Authentication.getAuthorities()` contains `ROLE_ADMIN`. If a `UserDetails` cache exists, a new authentication may also read the stale entry. If the client uses a still-valid JWT, the role claims inside the signed token do not change automatically when the database updates.

Thus, the question **"the account was updated in the DB, why haven't permissions changed?"** actually spans multiple layers:

- Is the record in the **account store** (JDBC/JPA/LDAP/IdP) accurate and committed?
- Does the **`UserDetails` cache** still hold a stale snapshot of username, password hash, flags, and authorities?
- Does **`SecurityContext` in the session** hold an `Authentication` from a previous login?
- Are previously issued **access tokens or refresh tokens** still valid?
- Do **other nodes**, CDNs/gateways, the authorization layer, and in-flight requests all observe the same version?

**Principle:** Caching reduces query cost, whereas revocation and consistency form a **multi-layer security policy**. Calling `cache.evict(username)` alone cannot revoke sessions, refresh tokens, JWTs, or permissions already evaluated inside an in-flight request.

This lesson focuses on **the account store serving Spring Security authentication**, controlled caching, invalidation events, revocation mechanisms, and verifying consistency latency.

## 2. Distinguishing Five Data Layers That Can Go Stale

| Layer | What does it hold? | When is it read? | How is it refreshed/revoked? |
| --- | --- | --- | --- |
| **Authoritative store** (DB/LDAP/IdP) | Username, hash, status, roles, change version | When a service or provider queries the source | Transaction commit, replica sync, conflict resolution |
| **`UserDetails` cache** | Data loaded for `UserDetailsService` / `AuthenticationProvider` | On login/re-authentication depending on mechanism | Evict by identity, TTL, version, invalidation events |
| **HTTP session / `SecurityContext`** | Authenticated `Authentication` with authorities | Subsequent requests using the session | Logout, session invalidation/expiration, refresh/re-authentication, and request-time policies |
| **Access token** (JWT/opaque) | `sub`, scopes/roles, `exp`, `jti`, or reference ID | Every bearer request per configuration | JWT: expiry/denylist/version check; opaque: server-side introspection/revocation |
| **Authorization/business cache** | ACLs, tenant memberships, permission check results | When services authorize objects | Evict by resource/tenant/user, TTL, request-time revalidation |

**The authoritative source of truth must be explicitly defined**: in an app with an internal account DB, the DB may be authoritative for enabled status and roles; in SSO, the IdP may be authoritative for authentication while domain roles live in the app DB. Never assume `JWT.roles` is always the freshest source of permissions.

### A Lifecycle Diagram

~~~text
Admin changes roles / locks account / changes password
                     |
                     v
             Account service
                     |
                     v
       UPDATE DB + authVersion++
                     |
                     v
              COMMIT succeeds
                     |
          +----------+-----------+
          |          |           |
          v          v           v
     Cache evict   Session     Token policy
     / reload      revoke      denylist/version
          |          |           |
          +----------+-----------+
                     |
                     v
        Re-check on subsequent requests
          (may add DB check
           for high-risk operations)
~~~

Each branch has its own propagation delay and failure modes. If the business requires revocation within seconds, define and test a **revocation latency budget**; a 15-minute TTL is never a guarantee of "near-instant revocation".

## 3. How Does `UserDetails` Caching Work in Spring Security?

### 3.1. `UserDetailsService` and `DaoAuthenticationProvider`

In a typical username/password flow:

1. The filter creates an unauthenticated `UsernamePasswordAuthenticationToken` from username and raw password.
2. `ProviderManager` selects `DaoAuthenticationProvider`.
3. The provider loads `UserDetails` from `UserDetailsService` or a cache if configured.
4. `PasswordEncoder.matches(rawPassword, storedHash)` and account status checks determine success/failure.
5. The provider returns an authenticated `Authentication` with authorities from a trusted source.
6. The web filter saves `SecurityContext` for the request/session per configuration.

`AbstractUserDetailsAuthenticationProvider` exposes `setUserCache(UserCache)`. **The default is `NullUserCache`**: there is no real user cache in the standard provider. The reason: in session-based apps, there is no need to query the DB to re-authenticate on **every request**; the server normally restores `SecurityContext` from the session.

Therefore, measure before enabling caching. Do not attach Redis/Ehcache to auth just because "every request needs `UserDetails`": for standard sessions, that assumption is false by default.

### 3.2. `UserCache` Has Three Basic Operations

~~~java
// Interface signatures for study; not a standalone executable class.
UserDetails getUserFromCache(String username);
void putUserInCache(UserDetails user);
void removeUserFromCache(String username);
~~~

`UserCache` does not mandate TTLs, versioned eviction, distributed invalidation, or size bounds. Those capabilities belong to the implementation and cache backend.

Spring Security provides `NullUserCache` and `SpringCacheBasedUserCache`. There is also `CachingUserDetailsService`, a wrapper that caches in front of an underlying `UserDetailsService`; with Spring Framework, `@Cacheable` can also be used. **Cache locations are not identical**: a provider-level cache and a wrapper/service-level cache can be two separate layers. When updating/deleting an account, know **exactly which layers** hold copies and invalidate them by design.

### 3.3. A Little-Noticed Detail: Cache Hits Still Require Credential Verification

For `DaoAuthenticationProvider`, **a cache hit does not skip password verification**. The provider still runs credential/status checks; if password verification against the cached entry fails, `AbstractUserDetailsAuthenticationProvider` has a mechanism to reload fresh data and retry verification, avoiding rejecting a newly changed password just because the cache held an old hash.

However, this reload mechanism **is not a full cache-synchronization contract**:

- The cache can still hold stale authorities even when the credential remains valid.
- Locked/disabled flags can remain stale between updates if relying solely on the cache.
- Never rely on "wrong password" events as a role-refresh strategy.
- Custom providers or `UserDetailsService` implementations may have different semantics.

In other words, **automatic handling of password mismatches does not replace event-driven eviction, versioning, and request-time checks**.

## 4. Security Trap: Credential Erasure and a Cache Sharing the Same Object

By default, `ProviderManager` attempts to call `eraseCredentials()` on the authentication result if the object implements `CredentialsContainer`. This shortens the lifetime of raw passwords, password hashes, or secrets inside `Authentication`/sessions.

However, if `Authentication.principal` points to **the exact same `UserDetails` instance** stored in the cache, credential erasure can **wipe the password hash inside the cached instance**. Subsequent authentications relying on that cached object will fail.

~~~text
UserDetailsService --> UserDetails object U (passwordHash != null)
                           |
                +----------+-----------+
                |                      |
                v                      v
        UserCache holds U         Authentication.principal = U
                                       |
                                       v
                          ProviderManager.eraseCredentials()
                                       |
                                       v
                              U.password = null
                                       |
                                       v
                       Cache holds the same U, password now null
~~~

**Safe ways to handle this:**

- Prefer **copying** `UserDetails` when populating/creating the authenticated result so the cached instance is never mutated; test that the copy shares no mutable credential container with the cache.
- Or design the cache to store a properly protected immutable projection/DTO and load the hash during login when needed.
- Keep TTLs short and restrict access to the cache, since password hashes remain sensitive data.
- Do not disable `eraseCredentialsAfterAuthentication` just to fix a cache bug without analyzing the risk. Some Spring guides note disabling credential erasure when using `CachingUserDetailsService`/`@Cacheable`, yet that is a **security trade-off** requiring validation; separate copies are usually the less leaky option.

Caching `UserDetails` is distinct from caching an **authenticated `SecurityContext`**. The latter may hold an `Authentication` from an earlier request and cannot be "fixed" merely by evicting the provider's `UserDetails` cache.

## 5. Cache Policy: Keys, TTL, Versioning, Bounds, and Failure Behavior

### 5.1. Choosing Meaningful Keys

Keys can use canonicalized usernames or stable user IDs, provided they align with lookup rules:

~~~text
Single tenant: auth:user:<canonical-username>
Multi-tenant:  auth:user:<verified-tenant-id>:<canonical-username>
By ID:         auth:user-id:<stable-user-id>
~~~

These are **design patterns**, not Spring Security defaults. If usernames can change, evict **both the old and new keys**; keying by `userId` reduces rename issues, though the default `UserCache` API queries by username so the adapter must map accurately.

Never let a client self-declare a higher-privilege `tenantId` and use it directly as a cache key: tenant scope must be verified. Prevent key collisions across environments (dev/test/prod), principal types, tenants, and login methods.

### 5.2. TTL Is Not an Immediate Revocation Mechanism

`TTL = 300 seconds` means an entry is considered expired after that duration **if** the cache enforces TTL accurately without sliding expiration extending it indefinitely. It **does not** promise every request stops using stale info within 300 seconds if sessions, JWTs, or other caches still exist.

Set TTLs based on data sensitivity and risk budgets:

| Information type | Change sensitivity | Typical policy considerations |
| --- | --- | --- |
| Display name, avatar | Low | Relatively long TTL, refresh on profile edit |
| Username, account enabled/locked | High | Evict after commit, version/revalidate; avoid long TTLs |
| Roles/authorities | High | Explicit events + versioning + session/token policy |
| Tenant membership, sensitive data ACLs | Very high | Revalidate at authorization or short cache with guaranteed invalidation |
| Password hash used for login | Very high | Avoid caching unless needed; protect credentials and copy properly |
| "User does not exist" | Risky | Short/cautious negative cache to avoid blocking newly registered users |

**Negative caching:** If "no account" results are cached, a newly registered user may keep getting treated as non-existent. On `createUser`, evict matching negative entries; also avoid creating username-enumeration channels or cache poisoning vectors.

### 5.3. Size Bounds, Data Protection, and Eviction

An auth cache must define:

- Maximum capacity/weight, eviction policy, TTL, and monitoring of hits/misses/evictions;
- Access control on the cache backend, TLS in transit, and data protection at rest;
- Rules forbidding logging password hashes, raw credentials, tokens, or full serialized `UserDetails`;
- Behavior when Redis/cache fails: never automatically accept unverified data;
- Namespace separation and key versioning when schemas/serializers change;
- Cache-stampede protection when many requests miss the cache concurrently;
- Rebuild/warmup plans; **never** open access merely because of a cache miss or unavailable cache.

Auth caching is a conditional performance optimization; **authoritative decisions** must always come from data/credentials verified under policy.

## 6. When an Account Changes, What Must Be Invalidated?

Critical events:

| Event | `UserDetails` cache | Session/`Authentication` | Token | Request-time check |
| --- | --- | --- | --- | --- |
| New account created | Evict negative cache, username key | No session to revoke from creation alone | No tokens yet if not logged in | Check email/activation if applicable |
| Password changed | Evict old hash | Consider logging out other sessions and re-authing current session | Revoke refresh tokens; access tokens per policy | May require step-up/`passwordChangedAt` |
| Password reset due to suspected compromise | Evict immediately | Revoke all related sessions | Revoke refresh tokens; denylist/version check for live access tokens | Stricter policy than routine self-change |
| User locked/disabled | Evict flags | Expire/invalidate sessions; block new requests | Revoke live tokens if high risk | Recheck `enabled` at protected boundaries |
| Role revoked/granted | Evict authorities | Old context may still hold old role; refresh or expire | Old claims/scopes may not yet update | Authorize against updated permissions per policy |
| Tenant membership changed | Evict by user/tenant | Refresh tenant context/session | Tokens with tenant claims need refresh/revocation | Check tenant + object-level rights |
| Username renamed | Evict old and new keys; update mapping | Session has old `getName`, use stable ID | Subjects/claims need safe mapping | Prevent old username from hitting wrong account |
| User deleted | Evict user data/negative cache | Revoke sessions & remember-me | Revoke tokens, remove related keys/credentials | Deny login and old resource access |
| Email/phone changed | Evict if auth uses it for login/MFA | Based on risk and re-verification | Update claims on next issuance | Never treat profile edits as role grants |

**Crucial point:** "Evict cache after UPDATE" fixes **one layer**. If `Authentication` already lives in an HTTP session, `UserDetailsService` may not be called again on the next request. When revoking a role, never assume evicting the cache alone revoked the permission.

### A Usable Event Model

~~~text
AccountChanged(userId, usernameBefore, usernameAfter,
               tenantId, authVersion, reason, committedAt)
                      |
                      v
        DB record commits successfully
                      |
                      v
             Outbox / event bus
                      |
        +-------------+----------------+
        |             |                |
        v             v                v
  Evict cached    Invalidate      Update token
  auth details    sessions        revocation state
        |             |                |
        +-------------+----------------+
                      |
                      v
         Metrics + audit + retry/DLQ
~~~

Events should carry **minimal identity/version info**, never password hashes, raw passwords, or unnecessary PII. Consumers must be **idempotent** because message brokers may redeliver the same event.

## 7. Transactions, Event Ordering, and Consistency Windows

### 7.1. Never Evict Before the Transaction Commits

Suppose a service calls `cache.evict("an")` before the DB transaction commits. Between those two steps, another request misses the cache, loads **stale data** from the DB, and repopulates the cache. Once the commit finishes, the cache holds stale data again with no further eviction event pending.

~~~text
Wrong order:
t0   UPDATE not yet COMMITted
t1   EVICT cache
t2   request B cache miss -> SELECT stale DB data -> CACHE PUT stale
t3   COMMIT new data
t4   cache still holds stale data until next TTL/eviction
~~~

**Better:** Write the new state and increment `authVersion` in **one transaction**, then publish invalidation after commit. Even so, read/write races and dropped events can still happen, so keep TTLs, versioning, or stronger safeguards at sensitive checkpoints.

### 7.2. The Re-Population Race After Eviction

Even "COMMIT then EVICT" has a race:

~~~text
t0 Request B starts loading v1 (before commit), waiting
t1 Admin COMMITs v2
t2 Cache EVICT event
t3 Request B finishes and PUTs v1 into cache (stale resurrection)
~~~

Solutions depend on required consistency:

- **Version/generation fencing:** each entry carries a version, and the cache rejects writes older than the latest known version;
- **Evict + short TTL** when a bounded stale window is acceptable;
- **Read authoritative store on high-risk operations** instead of relying solely on cache;
- **Per-key locking/serialization** when strict synchronization is truly required and worth the cost;
- **Outbox + retries + idempotent consumers** so events are not lost if a process crashes after commit;
- **Read-your-writes:** after a change, requests from the same actor can read the primary or match the new version to avoid replica lag.

`authVersion` is typically a **monotonically increasing** integer incremented whenever auth/authorization state changes. Wall-clock timestamps across machines with clock skew are less reliable than a DB-transaction version counter.

### 7.3. Replicas and Distributed Caches

Reading from a read replica after a primary commit can still return stale data during replication lag. Evicting Redis on time **does not guarantee** the next query sees the new version. Critical actions like locking an account or revoking high privileges may require primary/consistent reads or verifying committed versions before accepting data.

With per-node caches, every node must receive invalidation. Even with a centralized cache, stale copies can remain in thread-local requests, sessions, or other services' local copies. Watching `cache hit ratio` alone never measures revocation latency.

### 7.4. Consistency Levels

| Level | Acceptable behavior | Example |
| --- | --- | --- |
| **Eventual consistency** | Updates propagate with finite operational delay | Avatar/display name |
| **Bounded staleness** | Explicit time budget for staleness (must be measured) | Low-sensitivity roles with short cache TTL |
| **Read-your-writes** | After a user edits their own data, their next read sees it | Renaming/registration |
| **Security critical revalidation** | Sensitive decisions verify fresh state/authoritative permission source | Disabling accounts, money transfers, granting admin, revoking tenant access |

Never claim "strong consistency" merely because cache eviction ran: specify **where** decisions are refreshed, which source is read, how in-flight requests and replica lag behave, and how disconnects are handled.

## 8. `SecurityContext`/HTTP Sessions Are Not Identical to `UserDetails` Cache

In Spring Security Servlet, after successful login, `SecurityContextHolder` holds `Authentication`. `SecurityContextRepository` may persist it across requests in the HTTP session. On subsequent requests, Spring restores the identity without necessarily re-invoking `DaoAuthenticationProvider` or `loadUserByUsername`.

Therefore:

~~~text
Login -> UserDetails (may read cache) -> Authentication ROLE_ADMIN
                                              |
                                              v
                                  HttpSession/SecurityContext
                                              |
                                              v
                                  Request 2: ROLE_ADMIN
                                              |
Admin updates DB ROLE_USER + evicts UserCache ------+  (DOES NOT auto-update session)
~~~

To revoke authorities on existing sessions, an application can:

1. **Expire/invalidate sessions** belonging to the user so the next access forces re-authentication;
2. **Revalidate `authVersion` or account status** on every request / at high-risk endpoints, rejecting or rebuilding authentication per policy;
3. **Refresh authorities** from an authoritative source at a clear trust boundary, never "changing roles" from client input;
4. Use shorter session lifetimes alongside multi-device logout rules on password changes or account locks.

`SessionRegistry` supports concurrent session management when wired properly; `SessionInformation.expireNow()` marks a session expired for filter handling, **not immediately killing an in-flight request** or wiping every session in a distributed cluster. With Spring Session, distributed session management must rely on the real repository/index and tracking configuration rather than assuming one node's `SessionRegistry` sees everything.

Spring Security Servlet's default **Logout** invalidates the HTTP session and clears `SecurityContextHolder`/repository. However, logging out in one browser **does not automatically** revoke issued JWTs/refresh tokens, sessions on other devices, or external IdP sessions.

## 9. Revoking JWTs and Opaque Tokens: Clearing `UserCache` Won't Solve It

### 9.1. Signed JWTs Are Issue-Time Snapshots

A JWT whose signature and claims (issuer, audience, expiration) verify cleanly can remain **cryptographically valid** even after DB roles/accounts change. Stateless resource servers do not inherently query the user database for every token. Thus, clearing the `UserDetails` cache or updating the account **does not alter** signatures or claims inside issued JWTs.

Options:

- **Short access token TTL:** shrinks the stale window; insufficient when immediate blocking is required.
- **Denylist by `jti`:** store revoked token identifiers until expiration and check on every request at the gateway/resource server. Requires reliable storage, outage handling, and synchronized clocks.
- **`authVersion`/`securityStamp` claim:** token carries the version at issuance; each request or sensitive checkpoint compares it against the latest version in a trusted store/cache. Without a version lookup, the claim **does not revoke anything by itself**.
- **Opaque/reference tokens + introspection:** the authorization server can mark the token inactive; resource servers introspect and manage introspection cache TTLs carefully.
- **Rotate/revoke refresh tokens:** blocks issuing subsequent access tokens; revoking a refresh token **does not automatically expire an already-issued access JWT**.

If the requirement is "locking an account must strip access within seconds", pick a revocation or revalidation strategy that meets that goal; relying solely on a 1-hour JWT TTL is inadequate.

### 9.2. What Does Token Versioning Actually Control?

Suppose a token contains:

~~~json
{
  "sub": "account-42",
  "auth_ver": 7,
  "scope": "document:read",
  "exp": 1893456000
}
~~~

This is **illustrative JSON**, not a valid/signed token. After an admin updates the account, the DB sets `authVersion = 8`. The resource server must **verify signature, allowed algorithms, issuer/audience/exp**, and then compare `auth_ver == currentAuthVersion` (per policy). When the current version is 8, a token with version 7 is rejected.

If the version is cached for 5 minutes without reliable invalidation, requests can still observe 7 for 5 minutes. **A version check is only as strong as the freshness of its version source and its lookup failure handling.**

### 9.3. Opaque Tokens Do Not Guarantee Absolute Consistency Automatically

Opaque tokens are typically introspected at the authorization server, which can return `active=false` after revocation. Yet resource servers often cache introspection responses; if that cache TTL is long, revoked tokens still have a stale window. Align time budgets and cache policies on both sides.

## 10. Architecture Tiers: Match Complexity to Requirements

### Tier A: Single Instance, Session-Based, Simple Requirements

- Leave `NullUserCache` as the default unless measurements prove `UserDetails` caching is needed.
- Rely on `SecurityContextRepository` and sessions per Spring Security; protect CSRF/cookies.
- On user lock/role revocation, invalidate related sessions or revalidate at sensitive endpoints.
- Query the primary DB for critical authorization checks.
- Keep audit trails for account mutations and logouts.

### Tier B: Multiple Instances, DB + Distributed Cache

- Cache `UserDetails`/auth projections with TTLs, size limits, and tenant-scoped keys.
- Give each account an `authVersion`, incremented transactionally on critical changes.
- Emit invalidation after commit, preferably using a **transactional outbox** if reliable delivery is needed.
- Nodes consume events idempotently, monitoring propagation lag and retries/DLQs.
- Store sessions in a distributed repository or clear strategy supporting cross-node revocation.
- Define handling for replica lag, network partitions, and Redis outages.

### Tier C: Stateless JWT / High-Risk APIs

- Short-lived access tokens, refresh token rotation, and revocation.
- Depending on security tier: `jti` denylist, token versioning, or introspection.
- Resource servers validate JWTs/opaque tokens under strict freshness policies.
- Decisions on sensitive data cross-check fresh account/tenant status or a trusted authority service.
- "Fast revocation" targets must have SLOs and end-to-end tests, not just cache unit tests.

**There is no universal configuration for all apps.** Turning on Redis, adding a TTL, and declaring "consistent" skips defining security requirements, topology, and decision points.

## 11. Standalone Java 17 Example: TTL, Stale Data, Eviction, and Versioning

The plain Java example below simulates **three separate stores**: authoritative account store, TTL cache, and session snapshot. The goal is visualizing the consequences of updating only the DB or evicting only the cache.

**This is an educational model**, not an implementation of Spring Security's `UserCache`/`SecurityContextRepository`. It stores no passwords and uses no HTTP or JWT cryptography because the focus is consistency when account roles/flags change.

### 11.1. File and Run Commands

Create **`AuthCacheConsistencyDemo.java`**:

~~~java
import java.util.HashMap;
import java.util.Map;

public final class AuthCacheConsistencyDemo {

    record Account(long id, String username, String role,
                   boolean enabled, long authVersion) {}

    record CacheEntry(Account account, long expiresAtMillis) {}

    record SessionSnapshot(long userId, String role, long authVersion) {}

    static final class AccountStore {
        private Account account = new Account(
                42L, "an", "ROLE_ADMIN", true, 1L);

        Account find(String username) {
            if (!account.username().equals(username)) {
                throw new IllegalArgumentException("Unknown account");
            }
            return account;
        }

        void changeRole(String role) {
            account = new Account(
                    account.id(), account.username(), role,
                    account.enabled(), account.authVersion() + 1);
        }

        void disable() {
            account = new Account(
                    account.id(), account.username(), account.role(),
                    false, account.authVersion() + 1);
        }
    }

    static final class AccountCache {
        private final Map<String, CacheEntry> values = new HashMap<>();
        private final long ttlMillis;

        AccountCache(long ttlMillis) {
            this.ttlMillis = ttlMillis;
        }

        Account get(AccountStore store, String username, long nowMillis) {
            CacheEntry cached = values.get(username);
            if (cached != null && nowMillis < cached.expiresAtMillis()) {
                return cached.account();
            }
            Account fresh = store.find(username);
            values.put(username,
                    new CacheEntry(fresh, nowMillis + ttlMillis));
            return fresh;
        }

        void evict(String username) {
            values.remove(username);
        }
    }

    public static void main(String[] args) {
        AccountStore db = new AccountStore();
        AccountCache cache = new AccountCache(1000L);

        // t = 0: first read, populates cache and creates session with ADMIN role.
        Account first = cache.get(db, "an", 0);
        SessionSnapshot oldSession = new SessionSnapshot(
                first.id(), first.role(), first.authVersion());

        System.out.println("initial.cacheRole=" + first.role());
        System.out.println("initial.sessionVersion="
                + oldSession.authVersion());

        // t = 100: DB role changed; cache TTL not expired, session unchanged.
        db.changeRole("ROLE_USER");
        System.out.println("db.afterChangeRole=" + db.find("an").role());
        System.out.println("cache.at100.role="
                + cache.get(db, "an", 100).role());
        System.out.println("oldSession.role=" + oldSession.role());

        // t = 1100: cache expires and loads new role, old session still stale.
        Account refreshed = cache.get(db, "an", 1100);
        System.out.println("cache.afterTTL.role=" + refreshed.role());
        System.out.println("oldSession.versionCurrent="
                + (oldSession.authVersion()
                   == db.find("an").authVersion()));

        SessionSnapshot renewed = new SessionSnapshot(
                refreshed.id(), refreshed.role(), refreshed.authVersion());

        // t = 1200: disable user. Cache still holds "enabled=true".
        db.disable();
        System.out.println("cache.beforeEvict.enabled="
                + cache.get(db, "an", 1200).enabled());

        // Eviction causes the next cache read to load the updated account.
        cache.evict("an");
        Account latest = cache.get(db, "an", 1200);
        System.out.println("cache.afterEvict.enabled=" + latest.enabled());
        System.out.println("renewedSession.versionCurrent="
                + (renewed.authVersion()
                   == db.find("an").authVersion()));
    }
}
~~~

Run with JDK 17+:

~~~bash
javac AuthCacheConsistencyDemo.java
java AuthCacheConsistencyDemo
~~~

**Exact stdout of the program**:

~~~text
initial.cacheRole=ROLE_ADMIN
initial.sessionVersion=1
db.afterChangeRole=ROLE_USER
cache.at100.role=ROLE_ADMIN
oldSession.role=ROLE_ADMIN
cache.afterTTL.role=ROLE_USER
oldSession.versionCurrent=false
cache.beforeEvict.enabled=true
cache.afterEvict.enabled=false
renewedSession.versionCurrent=false
~~~

### 11.2. Reading the Output and Connecting to Spring Security

- `cache.at100.role=ROLE_ADMIN`: before TTL expires, a cache lookup still sees the stale role even though the DB has `ROLE_USER`.
- `oldSession.role=ROLE_ADMIN`: the session still holds the old snapshot; **cache expiration does not automatically refresh the session**.
- `oldSession.versionCurrent=false`: comparing `authVersion` against the authoritative store detects the stale snapshot. In practice, sessions/tokens must be **rejected or safely refreshed** on version mismatch.
- `cache.beforeEvict.enabled=true`: disabling the account in the DB does not automatically alter cached entries.
- `cache.afterEvict.enabled=false`: after eviction, the next read observes the disabled status; this still does not automatically log out active sessions.
- `renewedSession.versionCurrent=false`: even a session created after the role refresh becomes stale as soon as the account is subsequently disabled.

**Limitations:** The clock in the demo is passed manually to keep output deterministic; real implementations must rely on the cache's TTL mechanism and account for clock drift/latency. `HashMap` here is single-threaded; multi-threaded production requires a concurrency-safe cache backend. The demo does not simulate stale-repopulation races, transaction/replica lag, in-flight requests, or signed tokens; those require integration tests.

## 12. Applying to Spring Security: Exact API Connection Points

### 12.1. `UserCache` Only Manages UserDetails

~~~java
// ILLUSTRATIVE CODE: beans configured in a Spring application context.
@Bean
UserCache userCache(org.springframework.cache.CacheManager cacheManager) {
    var springCache = cacheManager.getCache("authUsers");
    if (springCache == null) {
        throw new IllegalStateException("Missing authUsers cache");
    }
    return new SpringCacheBasedUserCache(springCache);
}

@Bean
DaoAuthenticationProvider daoAuthenticationProvider(
        UserDetailsService userDetailsService,
        PasswordEncoder encoder,
        UserCache userCache) {
    DaoAuthenticationProvider provider =
            new DaoAuthenticationProvider(userDetailsService);
    provider.setPasswordEncoder(encoder);
    provider.setUserCache(userCache);
    return provider;
}
~~~

This is a **Spring integration snippet**, not a standalone program; it requires imports for `UserCache`, `SpringCacheBasedUserCache`, `@Bean`, Spring Security/Cache dependencies, and a configured `CacheManager` with TTL/eviction policies. It illustrates the provider-level cache API; two beans alone do not solve cache credential aliasing, logout, or distributed invalidation.

When modifying a user via `UserDetailsManager`/service, evict the cache in use:

~~~java
// Illustration after the account-update transaction has committed.
userCache.removeUserFromCache(username);
~~~

If **other** `@Cacheable`/`CachingUserDetailsService` caches exist, evict them as well. Never assume calling one method clears every place storing user data.

### 12.2. Post-Commit Events

~~~java
// SKETCH CODE in a Spring application with declared event/repository.
// Not a standalone program.
@Transactional
public void revokeRole(long userId) {
    Account account = repository.lockAndFind(userId);
    account.revokeAdmin();
    account.bumpAuthVersion();
    applicationEventPublisher.publishEvent(
            new AuthChanged(account.id(), account.username(),
                    account.authVersion()));
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(AuthChanged event) {
    userCache.removeUserFromCache(event.username());
    // Other session/token revocation steps must be executed separately.
}
~~~

An after-commit event listener works **within the same process**, yet if the process crashes after commit before handling the event, or if multiple nodes must be notified, this simple mechanism **does not guarantee delivery**. Use a transactional outbox + broker/retry/idempotency when strong delivery is required; events should carry only needed `accountId`/version/username, never credentials.

### 12.3. Session Registry and Revocation

In a Servlet app configured with concurrent session management and a proper session registry, `SessionRegistry` can find sessions for a known principal and mark them expired:

~~~java
// ILLUSTRATIVE CODE, not a standalone program.
// principal must match how SessionRegistry stores identity.
for (SessionInformation session :
        sessionRegistry.getAllSessions(principal, false)) {
    session.expireNow();
}
~~~

**This is not an "instant session kill"**: expiration usually takes effect when the filter checks the next request, and untracked sessions cannot be found. With Spring Session/Redis, choose the repository/index and integration setup capable of locating all of an account's sessions across nodes. Avoid passing a username that does not match `SessionRegistry`'s principal object/`equals` semantics.

### 12.4. Logout and Bearer Tokens

For form/session apps, use Spring Security's logout support to clear the context and invalidate sessions properly. For bearer tokens, add dedicated revocation mechanisms via `jti`, token versioning, introspection, or refresh token rotation. Never assume `SecurityContextLogoutHandler` invalidates already-issued JWTs.

### 12.5. Distinguishing Servlet from Reactive

The `UserCache`/`DaoAuthenticationProvider` and `SessionRegistry` examples above are for **Spring Security Servlet**. WebFlux applications use `ReactiveUserDetailsService`, `ReactiveAuthenticationManager`, and `ServerSecurityContextRepository`, with different lifecycles and hooks. Do not copy `HttpSecurity`/`SecurityContextHolder` configs into Reactive without checking the corresponding APIs and context propagation.

## 13. Testing Consistency, Not Just Cache Values

### 13.1. Required Risk-Based Test Matrix

| Test | Scenario | Expected |
| --- | --- | --- |
| Password changed while cache holds old hash | Re-authenticate with new/old password | Per policy: new succeeds, old is rejected once update is observed; never "cache hit => skip password" |
| User disabled with live session | Request to protected endpoint | Blocked within revocation SLO; does not wait until next login |
| `ROLE_ADMIN` revoked | Sessions and tokens issued prior to change | Admin endpoint denies within published revocation budget |
| User changes tenant membership | User cache and ACL cache across nodes | Old tenant is inaccessible; new tenant follows policy |
| Cache miss racing with eviction | Loader starts before commit, finishes after eviction | Never persists old version indefinitely; fencing/TTL handles it |
| Redelivered event | Consumer receives duplicate | Idempotent; does not regress version or re-grant roles |
| Broker/Redis down | Logout/revocation during outage | Explicit fail-closed, retry, or bounded degradation; never opens access |
| Replica lag | Primary DB committed, replica lags behind | Sensitive revalidation never grants permissions from stale state |
| Session on another node | One node revokes, next request hits node B | Consistent outcome within SLO |
| Unexpired JWT | Account disabled after token issuance | Token rejected per chosen mechanism, or stale window explicitly documented |
| Username renamed | Cache uses old/new keys | Old username cannot hit wrong account, no stale key remains |
| Credential erasure + cache | Repeated logins for same user with caching | Password hash not wiped in shared cache; no secrets logged |

Tests should run through the **real `SecurityFilterChain`** using MockMvc/WebTestClient or matching integration tests. A passing unit test for `cache.evict(key)` **does not prove** HTTP sessions or JWTs lost access.

### 13.2. Measuring Revocation Latency

Record safe timestamps (no secrets):

~~~text
t_commit: DB commits authVersion update
t_event:  invalidation sent/received across nodes
t_evict:  user/ACL cache evicted
t_revoke: session/token revocation state updated
t_deny:   first request with stale identity is denied
~~~

Track `t_deny - t_commit` at p95/p99 and worst case, broken down by account mutation type. A system might target **under 5 seconds** for disabling an account; this is merely an **example agreed target**, not a Spring Security guarantee or default TTL setting.

Explicitly decide whether requests that **started before commit** may finish. In many systems, in-flight requests cannot be aborted mid-flight; extremely sensitive operations need an additional authorization checkpoint right before business commit.

### 13.3. Behavior When Cache or Revocation Store Loses Connection

If `enabled` or `authVersion` cannot be checked at a high-security boundary, "allowing through because Redis failed" breaks revocation policy. Depending on business needs, you can:

- **Fail closed** on sensitive decisions, returning a transient error and alerting;
- **Fall back to reading the primary DB** if reachable with sufficient capacity;
- Rely on trusted state with a very short TTL if policy accepts bounded staleness;
- Deny high-impact mutations while allowing low-risk APIs under explicitly designed rules.

Never silently downgrade security. Record degraded states, alert, and test against SLOs.

## 14. Common Mistakes to Avoid

| Mistake | Why is it wrong? | How to fix |
| --- | --- | --- |
| "Evicted `UserDetails`, so user is logged out" | HTTP session/`Authentication` is a different layer | Revoke/refresh sessions per policy |
| "Changed password, so old JWT is invalid" | Signed JWTs retain claims until `exp` without revalidation/revocation | Short TTL + version/denylist/introspection when needed |
| Long TTLs for locked flags/roles | Keeps stale permissions alive for long periods | Invalidation + revalidation/version + SLO |
| Caching password hashes and sharing objects with principal | `eraseCredentials()` can wipe the hash in the cache | Copy objects or separate cache from principal |
| Evicting before transaction commit | Concurrent loader can repopulate stale data | After-commit + proper event/invalidation ordering |
| Handling events only on the local node | Other nodes retain stale caches | Distributed invalidation/repository and retries |
| Using local timestamps as the sole version | Clock skew/collisions break ordering | Monotonically increasing version in DB |
| Long-lived negative cache | Newly created users cannot log in | Short TTL + evict on creation |
| Single username key across all tenants | Cache collisions and identity mix-ups | Keys with verified tenant or stable ID |
| Assuming `@CacheEvict` clears all caches | Only affects the explicitly targeted cache | Inventory all cache/session/token layers |
| Relying on token roles with no freshness policy | Revoked roles persist inside tokens | Choose stale budget and check as needed |
| Reusing `authVersion` without bumping on role changes | Old tokens/sessions still match version | Bump version on every auth-relevant event |
| Treating TTL as a revocation-time guarantee | Sessions, queues, events, and replicas add latency | End-to-end testing and p99 measurement |
| Enabling caching to fix unmeasured performance | Adds unnecessary risk and complexity | Profile DB/LDAP calls before enabling |
| Failing open when revocation store is unreachable | Nullifies account-locking mechanisms | Explicit degraded/fail-closed policy |
| Logging full `UserDetails` or tokens | Leaks secrets/PII and bearer tokens | Log identity ID, event type, version, and trace ID |

## 15. Production Readiness Checklist

1. **Inventory:** document where users, `UserDetails`, `SecurityContext`, sessions, tokens, ACLs, and tenant memberships live.
2. **Source of truth:** identify the authoritative source for passwords/enabled/roles/tenants and who can modify them.
3. **Cache policy:** canonical keys, TTL, max size, namespaces, negative caching, credential protection, and hit/miss metrics.
4. **Mutation policy:** create/update/delete/lock/password-reset/role-change all have reasons, audits, and matching invalidation.
5. **Transactions:** update permissions and increment `authVersion` atomically; emit post-commit events, considering outbox.
6. **Version fencing:** prevent stale loaders from overwriting newer versions; do not rely solely on TTL.
7. **Sessions:** have revocation/re-authentication flows for active multi-device and multi-node sessions.
8. **Tokens:** access TTL, refresh revocation, JWT denylist/version, or opaque introspection matched to risk.
9. **Authorization:** sensitive endpoints check current permissions with sufficient freshness.
10. **Outage behavior:** define fallback/fail-closed rules for caches, DB replicas, brokers, and token revocation stores.
11. **Testing:** test concurrency, replica lag, logout, password/role changes, cross-node sessions, and unexpired JWTs.
12. **Observability:** measure p95/p99 time from commit to denied request; alert when exceeding targets.
13. **Privacy:** caches/sessions hold no excess business data or credentials; keep logs minimal.
14. **Documentation:** specify which changes require **immediate** revocation, how much staleness is allowed for others, and who owns enforcement.

## 16. Self-Check Questions

**Question 1.** After an admin evicts a user's `UserCache`, does a browser logged in via session automatically lose `ROLE_ADMIN`?  
**Answer:** No. `Authentication` in the session is a separate snapshot; you need session revocation, refresh, or revalidation policies.

**Question 2.** Why does Spring Security default to `NullUserCache` for the username/password provider?  
**Answer:** In many session-based Servlet apps, passwords are not re-verified on every request; `UserDetails` caching is often unnecessary for that flow.

**Question 3.** `DaoAuthenticationProvider` sees the password on a cached `UserDetails` does not match. Does that mean the system has good cache invalidation?  
**Answer:** No. The provider may reload the user to test the new password, yet roles, locked flags, and sessions still require their own freshness/revocation policies.

**Question 4.** Why can running an `evict` event before DB commit leave stale data in the cache?  
**Answer:** Another request can miss the cache, read uncommitted old data, and write the stale entry back before the transaction finishes.

**Question 5.** Does incrementing `authVersion` from 8 to 9 in the DB automatically revoke a JWT carrying `auth_ver=8`?  
**Answer:** No; the resource server must check the version reliably against sufficiently fresh data and reject old-version tokens.

**Question 6.** Does `SessionInformation.expireNow()` guarantee an in-flight request is aborted immediately?  
**Answer:** No. It marks the session expired for session/filter mechanisms to handle, typically on the next request; understand session tracking and distributed configuration.

**Question 7.** If a password changes while a refresh token stays valid, what can happen?  
**Answer:** The client can keep exchanging the refresh token for new access tokens depending on policy; decide on refresh revocation/rotation and handling live access tokens.

**Question 8.** Why must permission revocation be tested end-to-end?  
**Answer:** Because cache eviction, sessions, JWTs, replicas, and multiple nodes exist side by side; testing one layer alone does not prove real requests are blocked.

## 17. References

- [Spring Security 6.5 – Authentication Architecture](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/architecture.html): `ProviderManager`, credential erasure, and caching notes.
- [Spring Security 6.5 – AbstractUserDetailsAuthenticationProvider API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/authentication/dao/AbstractUserDetailsAuthenticationProvider.html): `UserCache`, default `NullUserCache`, and cache password-mismatch handling.
- [Spring Security – Caching UserDetails](https://docs.spring.io/spring-security/reference/6.5-SNAPSHOT/servlet/authentication/passwords/caching.html): `CachingUserDetailsService`, `@Cacheable`, and credential erasure.
- [Spring Security 6.5 – UserCache API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/userdetails/UserCache.html): get/put/remove and contract scope.
- [Spring Security 6.5 – Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextRepository`, session persistence, and explicit save.
- [Spring Security 6.5 – Logout](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/logout.html): session invalidation, context cleanup, and logout handlers.
- [Spring Security 6.5 – SessionInformation API](https://docs.spring.io/spring-security/reference/6.5/api/java/org/springframework/security/core/session/SessionInformation.html): active/expired/destroyed session states.
- [Spring Security – OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT validation for resource servers.
- [Spring Security – Opaque Tokens](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection and principals from tokens.
- [OWASP – Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifecycles and revocation controls.

**Remember:** **DB commit** creates the new data, **cache invalidation** lets subsequent reads see the new data, **session/token revocation** governs already-issued identities, and **authorization freshness** determines when changes actually take effect in APIs. To claim consistency, define the staleness window, measure end-to-end, and handle races, network failures, multiple nodes, and in-flight requests.
