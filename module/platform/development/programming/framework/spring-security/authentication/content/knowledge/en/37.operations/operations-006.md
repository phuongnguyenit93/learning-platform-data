# Identity Caching and Effective Time of Permission and Status Changes

## 1. Objective: A Database Change Does Not Automatically Update Active Permissions

In a Spring Security system, user Alice may have logged in at 09:00 with the `ADMIN` role. At 09:10, an administrator revokes `ADMIN` or sets Alice's status to `DISABLED`. The database updates immediately, yet:

- A cached `UserDetails` may still contain old authorities.
- `Authentication` inside the HTTP session's `SecurityContext` is typically a **snapshot** created at login; it does not automatically reload roles on every request.
- An already-issued JWT access token may still carry the `roles=["ADMIN"]` claim until expiration if the resource server checks only signature and expiry.
- Redis/local caches, API gateways, microservices, and in-flight requests may observe different versions of the data.
- A queued job or an operation approved before demotion may still proceed unless enforced separately at execution time.

**The operational question is not just "how long is the cache TTL?", but "where, when, with what maximum delay do new permissions or status take effect, and can this be proven with tests and metrics?".**

Example business requirements:
- Adding `REPORT_VIEWER` role: taking effect within one minute may be acceptable.
- Revoking `ADMIN` role: must take effect nearly instantaneously on admin APIs.
- Locking an account due to compromise: all sessions, tokens, and authentication paths must be blocked within a very short security SLA window.
- Password change: new logins must use the new hash; whether existing sessions stay or are revoked depends on policy.

After this lesson, you will understand cache layers, consistency models, TTL/invalidation/version patterns, Spring Security 6.x/Java 17 implementation, revocation latency measurement, and testing against **stale authorization**.

## 2. Four Concepts to Distinguish

| Concept | Question Answered | Where Data Typically Lives |
|---|---|---|
| **Identity** | Who does this request represent? | Principal, `Authentication.getName()`, JWT `sub` |
| **Authentication state** | How and when did the principal authenticate? | `SecurityContext`, session, bearer token, IdP |
| **Authorization state** | Which actions is the user currently permitted to perform? | Roles/scopes, policy engine, database, cache |
| **Account state** | Is the user currently `ACTIVE`, `LOCKED`, `DISABLED`, or deleted? | Account table, IdP, account-state cache |

A successful login at 09:00 does not guarantee the account is still active at 09:30. Likewise, a role recorded in `Authentication.getAuthorities()` is not necessarily the current role in the authorization source of truth.

You must separate **when identity was authenticated** from **when authorization policy is evaluated**.

### 2.1. Source of Truth vs. Snapshot

Assume the database is the current source of truth for permissions:

~~~text
DATABASE (source of truth)
  user_id=42
  status=ACTIVE
  roles=[USER, ADMIN]
  authorization_version=17

LOGIN AT 09:00:
  SecurityContext/Authentication snapshot:
  principal=user42, authorities=[ROLE_USER, ROLE_ADMIN]

CHANGE AT 09:10:
  database: status=ACTIVE, roles=[USER], version=18

REQUEST AT 09:11:
  Session snapshot may still be [ROLE_USER, ROLE_ADMIN]
  ⇒ If only calling hasRole("ADMIN") on the stale Authentication,
     the revoked role may still pass.
~~~

Proof of prior login establishes **who is sending the request**, whereas sensitive actions must combine it with **sufficiently fresh** permission state.

### 2.2. Invalidation Differs from Expiry

- **Expiry/TTL:** accepts cached entries until expiration before reloading. Provides predictable bounded staleness if not arbitrarily extended.
- **Invalidation:** actively deletes or marks stale cache entries after data changes.
- **Version check:** compares the permission/session version against the current version; avoids hunting down every cache record if checked at the right boundary.
- **Revocation:** invalidates sessions/tokens or marks a principal/credential as no longer usable.
- **Authorization at point of use:** checks permissions directly where the action executes rather than relying solely on decisions made at login time.

Do not conflate these five operations. For example, deleting Redis cache key `user:42` **does not automatically delete already-logged-in HTTP sessions**.

## 3. Data Layers That Can Go Stale in a Spring Security System

### 3.1. UserDetails Cache

In username/password flows, `DaoAuthenticationProvider` uses `UserDetailsService`. Spring Security provides:
- `CachingUserDetailsService` paired with `UserCache`;
- Spring Framework's `@Cacheable` on `loadUserByUsername`;
- A `UserCache` configured in the provider/service if the app opts in.

The cache may store `username`, password hash, `enabled`/account flags, and `GrantedAuthority`, depending on the `UserDetails` implementation.

**Key point:** `CachingUserDetailsService` defaults to `NullUserCache` if you do not supply an actual cache. Spring Security does not automatically turn on Redis UserDetails caching merely because Redis is on the classpath.

### 3.2. SecurityContext in Session

With form login/sessions, after authentication succeeds, `Authentication` is typically stored in `SecurityContext` via `SecurityContextRepository`. Subsequent requests retrieve that context without necessarily calling `UserDetailsService` again.

~~~text
POST /login:
  UserDetailsService → check password → Authentication(role snapshot)
                                       |
                                       v
                                   HttpSession

GET /api/admin after 20 minutes:
  HttpSession → SecurityContext → stale Authentication
                                       |
                                       v
                             hasRole("ADMIN") on snapshot
~~~

Therefore, **evicting the `UserDetails` cache only affects future `UserDetails` loads**, not the authorities of an `Authentication` already residing in a session.

Spring Security 6 uses **explicit saving** for `SecurityContextRepository` in many setups. If you manually modify `Authentication` or clear context, understand how saving/invalidation works rather than assuming `SecurityContextHolder.clearContext()` on one request revokes all sessions.

### 3.3. JWT Access Tokens

A signed JWT can hold `sub`, `scope`, `roles`, `iat`, `exp`, and other claims. Once issued, the JWT payload **does not change automatically** when the DB removes a role.

A typical resource server validates signature, `iss`, `exp`, `nbf`, audience if configured, and maps claims to authorities. Without a live status/permission lookup, a validly signed token with an old `ROLE_ADMIN` remains accepted until `exp`.

**Validating a JWT signature does not mean validating current permissions.** An unexpired JWT also does not prove the account is active or its refresh token has not been revoked.

### 3.4. Opaque Tokens and Introspection Caches

An OAuth2 resource server using opaque tokens can call Authorization Server introspection to confirm `active` and scopes. However, if introspection results are **cached** in the resource server or gateway, an old `active=true` entry persists for that cache TTL.

Do not assume opaque tokens are always instantaneously revocable: immediacy depends on how the Authorization Server updates state, introspection caches, networking, and actual verification paths.

### 3.5. Separately Cached Business Authorization

Outside Spring Security, apps often cache:
- groups, teams, departments, tenants;
- read permissions for a project, order, or report;
- object-level permissions/ACLs;
- feature flags, subscription/contract state;
- entitlements from external services.

`MANAGER` role may remain valid while the user no longer belongs to `tenant-A`. Clearing only `UserDetails` cache does not refresh **object ownership** or ACLs in another service.

## 4. Layer-by-Layer Change Effectiveness Matrix

| Change | Layers That Can Be Stale | What Must Be Done |
|---|---|---|
| Display name change | Profile/UI cache | TTL, invalidate profile cache, eventual consistency acceptable |
| Grant reporting role | UserDetails, session, entitlement cache, JWT | Refresh context/token or live authorization per SLA |
| Revoke admin role | Session/JWT, permission caches | Revalidate on sensitive endpoints, revoke, or version check |
| Disable user | UserDetails/session/token and downstream services | Block new logins **and** active requests/sessions/tokens |
| Lock account after failed passwords | Authentication/login state, session per policy | Enforce login lockout; follow policy on existing sessions |
| Password change | Password hash cache, sessions, refresh tokens | Evict hash cache; revoke sessions/tokens if policy requires |
| Tenant change | Principal, role mappings, object ACLs, sessions | Enforce current tenant and account binding |
| Delete user | All caches/sessions/tokens | Deny access, revoke, and purge data per lifecycle |
| Revoke refresh token | Authorization Server token store | Block new refreshes; account for remaining access token TTL |
| Logout | Session/client/tokens | Invalidate sessions and tokens per architecture, not just client cookie removal |

Correctness does not come merely from an `enabled=false` flag: if an API skips status checks because it trusts an old session, a disabled account can still access resources.

## 5. What Does "Effective Time" Mean Precisely?

Define the milestones:

~~~text
T0: administrator clicks "Revoke ADMIN role"
T1: database transaction commits and returns success
T2: invalidation event is published
T3: caches/replicas receive event or TTL expires
T4: Alice's new request hits a permission-checking endpoint
T5: endpoint denies under the new policy
~~~

There are multiple latencies:
- **Database commit latency:** T0 to T1.
- **Propagation latency:** T1 until caches/instances update.
- **Enforcement latency:** T1 until the first request/operation is actually denied.
- **Outstanding-work latency:** transactions or jobs already authorized before T1 may still finish.

Measure `T5 - T1` via controlled request testing, not just when the event was published at T2. For an idle account making no requests, there is no T4/T5 to observe; use synthetic probes or state inspection per SLA requirements.

### 5.1. TTL Gives Approximate Bounded Staleness, Not an End-to-End Guarantee

If a local cache has a fixed 60-second TTL from write time, stale data can persist up to ~60 seconds **in that cache layer**, excluding:
- other caches at gateways or downstream services;
- in-flight requests;
- clients/sessions holding separate snapshots;
- a JWT still valid for 15 minutes;
- stale-while-revalidate or sliding TTL renewals;
- failed invalidations or delayed event queues.

You cannot conclude "permission changes take effect in at most 60 seconds" simply because a Redis key has a 60-second TTL. Inspect **the longest-lived enforcement path**.

### 5.2. Operational Timeline Example

~~~text
JWT issued:       09:00, expires 09:15, contains ADMIN
Session created:  09:01, TTL 8h, contains ADMIN
User cache:       TTL 60s
DB role removed:  09:03

If /api/admin trusts only JWT roles:
  old token may still be usable until 09:15.

If /web/admin trusts only session Authentication:
  snapshot may persist until session expires/re-login.

If /admin always checks current DB roles:
  requests AFTER COMMIT will be denied per the new DB snapshot
  (except requests that already passed the check before commit).

If /admin uses a 60s TTL permission cache:
  may lag until cache invalidates/TTL expires,
  not counting other layers.
~~~

**Illustrative SLAs**, not mandatory standards:
- Non-sensitive role grant: eventual consistency within 60 seconds.
- Revoke admin role: deny new requests within 5 seconds.
- Disable compromised account: deny new requests on every replica almost immediately after commit, with a fallback when the store fails.

If product specifies a 5-second SLA, a 15-minute JWT with no current-state check **does not meet that SLA**.

## 6. Consistency Models: Eventual or Strong?

### 6.1. Eventual Consistency

Stale caches converge to the new state after TTL/events, though requests in that window may observe old permissions.

Suitable when:
- changing display data or low-risk entitlements;
- the documented lag is acceptable;
- monitoring detects stuck propagation;
- no sensitive actions occur during the staleness window.

### 6.2. Strong / Read-Current Authorization

Sensitive endpoints read from a suitably consistent data source and check at point of use. Add:
- row locks/optimistic versioning on writes;
- conditional updates ensuring permissions were not revoked mid-transaction;
- denylist/epoch checks before side effects;
- transaction-specific approvals for financial operations.

Do not claim "reading the DB on every request is strictly instantaneous": a request checked right before role revocation can still continue executing. If you must prevent **commits after revocation**, check inside the transaction or adopt an operation-appropriate protocol.

### 6.3. Risk-Based Hybrid

A practical design:
- Cache profiles/roles for low-sensitivity pages with short TTLs.
- Admin requests use **live account status + live authorization version/roles**.
- Sessions/JWTs supply only identity; the policy source decides current permissions.
- On disable or revocation, publish invalidation events and revoke sessions/tokens to close stale paths.
- If the state store is unavailable on highly sensitive actions, **fail closed** instead of falling back to old authorities.

In exchange, live checks raise latency/DB load. Use batch queries, synchronized read models, and risk-aware circuit breakers, without opening a bypass on stale data.

## 7. Spring Security: How Does UserDetails Caching Work?

Spring Security 6.5 documents `CachingUserDetailsService`, `UserCache`, and `@Cacheable`. Configuration-level example:

~~~java
@Bean
CachingUserDetailsService cachedUsers(
        UserDetailsService delegate,
        UserCache userCache) {

    CachingUserDetailsService service =
            new CachingUserDetailsService(delegate);
    service.setUserCache(userCache);
    return service;
}
~~~

This is a **configuration fragment**, not a standalone Java file. It requires importing `org.springframework.security.authentication.CachingUserDetailsService`, `org.springframework.security.core.userdetails.UserDetailsService`, `org.springframework.security.core.userdetails.UserCache`, and `@Bean`; specify clearly which bean serves as delegate to avoid dependency cycles.

Another option:

~~~java
@Override
@Cacheable(cacheNames = "userDetails", key = "#username")
public UserDetails loadUserByUsername(String username) {
    return accountRepository.loadAsUserDetails(username);
}
~~~

This illustrates annotation usage; real apps need `@EnableCaching` and a configured `CacheManager`. For cache keys, canonicalize usernames consistently with lookups. In multi-tenant apps, use `tenantId + userId` or properly namespaced keys so roles from another tenant never collide.

### 7.1. The Credential Erasure Issue

Spring Security documentation notes that when caching `UserDetails` for password verification, certain setups must account for `eraseCredentialsAfterAuthentication` so cached objects do not lose the password hash needed for subsequent logins.

**Trade-off:** keeping password hashes in caches longer increases sensitive secret exposure. Never disable credential erasure globally just to cache roles/profiles. Prefer:
- separating an **identity/authorization projection** without password hashes from password verification data;
- caching only the fields needed;
- keeping TTLs short and controlling cache access;
- testing after one authentication to verify the cache is not corrupted;
- avoiding caching password hashes altogether unless performance demands it.

### 7.2. UserCache and Sessions Are Different Things

~~~text
UserDetails cache --(at login/lookup)--> Authentication
                                              |
                                              v
                                       Session/SecurityContext

UserDetails cache evict(user42)
        |
        +--> SUBSEQUENT login/lookup can read updated user
        |
        └--> DOES NOT automatically refresh Authentication already in session
~~~

For demotions to take effect in existing sessions, enforce a policy:
- invalidate open sessions;
- force reauthentication/context refresh;
- or perform **live-check authorization** on every protected action;
- optionally combine with version/epoch checks to block stale sessions.

Never call `@CacheEvict` alone and assume all active logged-in requests immediately reflect the new permissions.

## 8. Distinguishing "Disable Login" from "Disable Current Access"

In Spring Security, `UserDetails.isEnabled()`, `isAccountNonLocked()`, and `isAccountNonExpired()` are checked by the authentication provider **at authentication time**.

Example:
1. Alice logs in at 09:00; the session holds `Authentication`.
2. An admin sets `enabled=false` at 09:10.
3. `UserDetailsService` for new logins returns `disabled=true` (or `isEnabled() == false`), so new logins are rejected.
4. **The old session still holds `Authentication`** and can reach endpoints that skip current account status checks.

Options to neutralize existing sessions:
- Locate and invalidate the subject's sessions via a session registry or distributed session store.
- Check `active`/authorization epoch on requests, denying when locked.
- Revoke access/refresh tokens and coordinate across resource servers.
- For highly sensitive actions, check account status directly inside the business transaction.

**Do not automatically equate bad-password account lockouts with compromise revocation:** a product may want existing valid sessions to finish limited work while lockout stops password guessing. Define explicit policies for `LOCKED`, `DISABLED`, `SUSPENDED`, and `DELETED`.

## 9. SessionRegistry and Spring Session: Managing Multiple Sessions

Spring Security provides `SessionRegistry` to track sessions, `SessionInformation.expireNow()` to mark them expired within session management, and concurrent session controls.

Notes:
- `SessionRegistryImpl` typically lives in application memory; it has no awareness of sessions on other replicas.
- `SessionInformation.expireNow()` flags the session and `ConcurrentSessionFilter`/related infrastructure handles it on the next request; **it does not necessarily cancel an already-running job**.
- `HttpSession.invalidate()` applies to the current session; finding all sessions for a user across nodes requires a consistent session store/registry.
- With Spring Session + Redis, corresponding session repositories/registries exist, but must be implemented per library version and tested on a cluster; do not assume every `SessionRegistry` bean is wired automatically.
- Custom principals used as registry keys require consistent `equals`/`hashCode`; changing principal classes or usernames can cause incomplete session enumeration.

**"Log out all devices" mechanisms must be tested across multiple replicas**, including older browser sessions, remember-me cookies, refresh tokens, and WebSocket connections. Clearing only a local JVM cache does not fulfill this requirement.

## 10. JWT: An Unexpired Token Does Not Mean Permissions Are Unchanged

### 10.1. Default Flow

~~~text
T0: Authorization Server issues JWT:
    sub=alice, scope=["orders.read","orders.write"],
    exp=T0+15m, authorizationVersion=3

T1: DB revokes orders.write and increments version=4

T2: Client sends old JWT to resource server

If resource server only checks signature/exp/iss:
    JWT still has scope "orders.write" and may be accepted.

If resource server checks current version=4:
    authzVersion in JWT is 3 => reject/step-up/reissue.
~~~

Spring Security Resource Server by default verifies JWTs and maps scopes per config; **it does not query the DB on every request to detect role changes**. Version validation requires custom checks.

### 10.2. Strategy Options

| Strategy | Pros | Limitations |
|---|---|---|
| Short access token TTL | Bounds claim staleness window | No immediate revocation before expiration |
| Per-request introspection | Can reflect near-real-time active/revoked status | Adds network dependency; introspection caches add lag |
| Token `jti` denylist | Revokes specific tokens before expiry | Needs store lookup/sync and denylist TTL |
| Subject `tokenVersion` / epoch | Bulk-revokes all account tokens | Requests must check current version, not trust claim alone |
| `authorizationVersion` | Detects permission changes | Needs refresh token policy and lag handling |
| Recompute permissions server-side | Never trusts stale role claims | DB/cache load and consistency requirements |
| Revoke refresh tokens | Stops minting new access tokens | Existing access tokens remain valid until expiry |
| Sender-constrained tokens | Reduces stolen-token replay risk | Does not solve role/status changes by itself |

**Never imagine overwriting `exp` on the server:** a signed JWT cannot have its held payload edited in place. Invalidate via policy or issue a fresh token once the user re-qualifies.

### 10.3. Safe Token Version Rules

Store `token_version` and `authorization_version` in the DB:
- `token_version`: incremented to revoke all user sessions/tokens.
- `authorization_version`: incremented whenever roles/groups/entitlements change.
- Access tokens carry both values as signed claims.
- Resource servers validate the signed token **and** read current versions from a trusted source.

**Embedding a version in a JWT without comparing it against the current version provides zero revocation effect.**

Current-version caches can also go stale. For endpoints needing sub-few-second enforcement, design the current-version cache to meet the SLA, or read from a strongly consistent store.

## 11. Redis/Local Cache: Cache-Aside and Invalidation

### 11.1. Cache-Aside

~~~text
GET authz:user42:
  local/Redis hit → return snapshot
             miss → SELECT DB → store snapshot with TTL

UPDATE roles user42:
  BEGIN
     UPDATE account_roles...
     UPDATE user.authz_version = authz_version + 1
  COMMIT
  publish invalidate(user42, newVersion)
~~~

Cache-aside is popular for cutting DB load. However, `UPDATE DB` followed by `cache.evict` is not atomic across two systems.

### 11.2. Two Race Scenarios

**Race A — stale read before invalidation:**

~~~text
Reader: SELECT old roles from DB before commit
Writer: COMMIT new roles
Writer: EVICT cache
Reader: PUT old roles into cache AFTER EVICT

Result: stale cache reappears until the next TTL.
~~~

**Race B — out-of-order events:**

~~~text
Version 10 → 11 (grant)
Version 11 → 12 (revoke)

Event version 12 arrives before event version 11.
If the handler overwrites the snapshot with "latest received event",
cache may revert to version 11 even though DB is at 12.
~~~

### 11.3. Mitigating Races

- **Versioned keys:** store `authz:{userId}:{version}`, read the current version, and accept only the matching snapshot. Ensure current-version lookup meets the SLA.
- **Monotonic versions:** event handlers only accept versions higher than the stored one; never overwrite newer state with an older version.
- **Transactional outbox:** write the DB change and an outbox event in the same transaction; a publisher emits events after commit with safe retries.
- **Bounded TTL:** even if an event is lost, caches converge; keep TTL within SLA and only for layers with acceptable risk.
- **Cross-node invalidation:** pub/sub or queues with retries; local in-memory caches must receive events too, not just shared Redis.
- **Fail-closed critical paths:** if current roles/status cannot be verified, deny sensitive actions rather than trusting stale data.
- **Caution with negative caching:** a newly created/activated account can remain cached as "nonexistent/disabled" too long.

**Do not assume Redis Pub/Sub provides durable message delivery.** If a consumer is offline, messages are lost. Pair with TTLs, reconciliation, outboxes, or streams with retry policies as needed.

## 12. Choosing Proper Cache Keys

A cache key with only a username like `user:alice` breaks in multi-tenant systems or when a user changes email:

~~~text
tenant-A / alice → ROLE_ADMIN
tenant-B / alice → ROLE_VIEWER

WRONG: cache key = "alice"
RIGHT: cache key = "tenant-A:user-42:authz-v7"
       cache key = "tenant-B:user-99:authz-v3"
~~~

Recommendations:
- Use an **immutable user ID**, tenant ID, and version/policy namespace.
- Avoid email as the sole key if emails can change.
- When username/email changes, invalidate aliases and lookup mapping caches.
- Never take tenant from a client-supplied `X-Tenant-Id` header to derive permissions; the tenant in cache keys must be verified against the principal/session.
- Avoid putting raw emails/PII in Redis keys needlessly; log safe keys/correlation IDs.
- For per-resource roles, cache keys may need `resourceId`, `action`, `policyVersion`, and owner version.

If sharing a cache across environments (dev/staging/prod), always namespace by environment; never let staging permissions leak into production.

## 13. Standalone Java 17 Example: Stale Snapshot vs. Version Guard

This snippet runs on JDK 17 with no Spring dependencies. It models a session holding ADMIN from login, after which the database demotes the account. We compare **trusting session roles alone** against **checking version/live account**.

File `AuthorizationVersionDemo.java`:

~~~java
import java.util.Set;

public final class AuthorizationVersionDemo {
    record Account(long version, boolean active, Set<String> roles) {
        Account {
            roles = Set.copyOf(roles);
        }
    }

    record SessionSnapshot(long authzVersion, Set<String> roles) {
        SessionSnapshot {
            roles = Set.copyOf(roles);
        }
    }

    static boolean cachedOnlyAllowsAdmin(SessionSnapshot session) {
        return session.roles().contains("ADMIN");
    }

    static boolean currentAllowsAdmin(
            SessionSnapshot session, Account liveAccount) {
        return liveAccount.active()
                && session.authzVersion() == liveAccount.version()
                && liveAccount.roles().contains("ADMIN");
    }

    public static void main(String[] args) {
        Account first = new Account(
                7, true, Set.of("USER", "ADMIN"));
        SessionSnapshot session = new SessionSnapshot(
                first.version(), first.roles());

        System.out.println("initial=" + currentAllowsAdmin(
                session, first));

        Account demoted = new Account(
                8, true, Set.of("USER"));

        System.out.println("stale-session-alone="
                + cachedOnlyAllowsAdmin(session));
        System.out.println("version-guard-after-demotion="
                + currentAllowsAdmin(session, demoted));

        SessionSnapshot fresh = new SessionSnapshot(
                demoted.version(), demoted.roles());
        System.out.println("fresh-session-after-demotion="
                + currentAllowsAdmin(fresh, demoted));

        Account disabled = new Account(
                9, false, Set.of("USER"));
        System.out.println("after-disable="
                + currentAllowsAdmin(fresh, disabled));
    }
}
~~~

Run:

~~~bash
javac AuthorizationVersionDemo.java
java AuthorizationVersionDemo
~~~

**Exact stdout:**

~~~text
initial=true
stale-session-alone=true
version-guard-after-demotion=false
fresh-session-after-demotion=false
after-disable=false
~~~

Key takeaways:
- `stale-session-alone=true` shows the danger of basing authorization **solely on cached roles**.
- Version increment rejects the old snapshot—which works only because `currentAllowsAdmin` actually consults **current account version**.
- After re-logging in with a fresh snapshot, Alice is no longer ADMIN.
- Disabling the account blocks access even when the session carries historical data.
- The demo **does not simulate distributed caches or real HTTP requests**; the next section shows a Spring Boot example.

## 14. Spring Boot 3.x / Spring Security 6.x: Checking Current Permissions on Every Request

The following demo runs on Java 17, Spring Boot 3.5.x, and Spring Security 6.5.x. It uses **form login** and a test-only in-memory account store. When Alice logs in, Spring creates a session and `Authentication` holding her login-time roles. Then the test "demotes" her in the store and sends another request **with the exact same old session**.

`/admin` uses a custom `AuthorizationManager` reading the live account instead of merely calling `hasRole("ADMIN")` on the stale session. `/me` also checks that the account remains enabled.

**Limitations:** the in-memory store does not sync across replicas, tests use no Redis/PostgreSQL, sessions are not actually revoked, and there is no persistence or cross-service authorization. It demonstrates **the request-time permission check path**, not a production account management system.

### 14.1. Project Structure

~~~text
fresh-authorization-demo/
├── pom.xml
└── src/
    ├── main/java/com/example/freshauthz/
    │   ├── FreshAuthorizationApplication.java
    │   ├── AccountSnapshot.java
    │   ├── InMemoryIdentityStore.java
    │   ├── LiveAuthorization.java
    │   ├── SecurityConfiguration.java
    │   └── AccountController.java
    └── test/java/com/example/freshauthz/
        └── AuthorizationChangeTest.java
~~~

### 14.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>fresh-authorization-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
        <dependency>
            <groupId>org.springframework.security</groupId>
            <artifactId>spring-security-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
~~~

The Boot BOM manages compatible Spring Security versions. Tests use `spring-security-test`'s `formLogin()` post-processor without launching a real browser.

### 14.3. `FreshAuthorizationApplication.java`

~~~java
package com.example.freshauthz;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FreshAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(FreshAuthorizationApplication.class, args);
    }
}
~~~

### 14.4. `AccountSnapshot.java`

~~~java
package com.example.freshauthz;

import java.util.Set;

public record AccountSnapshot(
        String username,
        String encodedPassword,
        Set<String> roles,
        boolean enabled,
        long authorizationVersion) {

    public AccountSnapshot {
        roles = Set.copyOf(roles);
    }
}
~~~

The record is an immutable snapshot: every mutation produces a new object with a higher version. `Set.copyOf` prevents another thread from mutating roles on the same instance.

### 14.5. `InMemoryIdentityStore.java`

~~~java
package com.example.freshauthz;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;

import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Component;

@Component
public final class InMemoryIdentityStore {

    private final PasswordEncoder encoder;
    private final ConcurrentMap<String, AccountSnapshot> accounts =
            new ConcurrentHashMap<>();

    public InMemoryIdentityStore(PasswordEncoder encoder) {
        this.encoder = encoder;
        reset();
    }

    public AccountSnapshot find(String username) {
        return accounts.get(username);
    }

    public void reset() {
        accounts.clear();
        accounts.put("alice", new AccountSnapshot(
                "alice",
                encoder.encode("local-only-demo-password"),
                Set.of("USER", "ADMIN"),
                true,
                1L));
    }

    public void demote(String username) {
        accounts.computeIfPresent(username, (id, old) ->
                new AccountSnapshot(
                        old.username(),
                        old.encodedPassword(),
                        Set.of("USER"),
                        old.enabled(),
                        old.authorizationVersion() + 1L));
    }

    public void disable(String username) {
        accounts.computeIfPresent(username, (id, old) ->
                new AccountSnapshot(
                        old.username(),
                        old.encodedPassword(),
                        old.roles(),
                        false,
                        old.authorizationVersion() + 1L));
    }
}
~~~

The store is seeded with a fake password **for local tests only**, not a production account/credential. `ConcurrentHashMap.computeIfPresent` protects one key within **a single JVM**, not replacing DB transactions or Redis atomic operations across instances.

### 14.6. `LiveAuthorization.java`

~~~java
package com.example.freshauthz;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.authorization.AuthorizationDecision;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component
public final class LiveAuthorization {

    private final InMemoryIdentityStore accounts;

    public LiveAuthorization(InMemoryIdentityStore accounts) {
        this.accounts = accounts;
    }

    public AuthorizationDecision check(
            Authentication authentication, String requiredRole) {

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return new AuthorizationDecision(false);
        }

        AccountSnapshot current = accounts.find(authentication.getName());

        boolean granted = current != null
                && current.enabled()
                && (requiredRole == null
                    || current.roles().contains(requiredRole));

        return new AuthorizationDecision(granted);
    }
}
~~~

Key takeaway: `roles` and `enabled` here come from the **current account snapshot in the store**, **not** from the stale `authentication.getAuthorities()` in the session. When the store is a DB or consistent read model, rules reflect changes according to that store's freshness.

If the store becomes unavailable, production code must handle errors and **deny sensitive actions**, never falling back automatically to stale roles. This test does not evaluate SLAs, transaction consistency, or caching.

### 14.7. `SecurityConfiguration.java`

~~~java
package com.example.freshauthz;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.core.userdetails.UsernameNotFoundException;
import org.springframework.security.crypto.factory.PasswordEncoderFactories;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfiguration {

    @Bean
    PasswordEncoder passwordEncoder() {
        return PasswordEncoderFactories.createDelegatingPasswordEncoder();
    }

    @Bean
    UserDetailsService userDetailsService(InMemoryIdentityStore accounts) {
        return username -> {
            AccountSnapshot current = accounts.find(username);
            if (current == null) {
                throw new UsernameNotFoundException("Invalid credentials");
            }

            return User.withUsername(current.username())
                    .password(current.encodedPassword())
                    .roles(current.roles().toArray(String[]::new))
                    .disabled(!current.enabled())
                    .build();
        };
    }

    @Bean
    SecurityFilterChain security(
            HttpSecurity http,
            LiveAuthorization current) throws Exception {

        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/login", "/error").permitAll()
                        .requestMatchers(HttpMethod.GET, "/admin")
                            .access((authentication, context) ->
                                current.check(authentication.get(), "ADMIN"))
                        .requestMatchers(HttpMethod.GET, "/me")
                            .access((authentication, context) ->
                                current.check(authentication.get(), null))
                        .anyRequest().denyAll())
                .formLogin(form -> form.permitAll())
                .build();
    }
}
~~~

- `UserDetailsService` reads the current account for new logins; a disabled user cannot log in with a password after being disabled.
- `AuthorizationManager` on `/admin` checks the live store per request rather than trusting login-time roles.
- `/me` rejects a disabled user even when the earlier session still holds an `Authentication`.
- `anyRequest().denyAll()` keeps all endpoints outside the demo closed.
- `formLogin(form -> form.permitAll())` configures and permits the Spring Security login page/endpoint.
- **CSRF remains enabled**. Login forms/test post-processors must supply a valid CSRF token.
- In production, status/permission checks must cover **every protected endpoint, method security, WebSockets, queue workers, gRPC, and batch jobs**, not just two sample routes.

### 14.8. `AccountController.java`

~~~java
package com.example.freshauthz;

import java.util.Map;
import org.springframework.security.core.Authentication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    private final InMemoryIdentityStore accounts;

    public AccountController(InMemoryIdentityStore accounts) {
        this.accounts = accounts;
    }

    @GetMapping("/me")
    public Map<String, Object> me(Authentication authentication) {
        AccountSnapshot current = accounts.find(authentication.getName());
        return Map.of(
                "username", current.username(),
                "enabled", current.enabled(),
                "authorizationVersion", current.authorizationVersion());
    }

    @GetMapping("/admin")
    public Map<String, String> admin() {
        return Map.of("result", "admin-access-granted");
    }
}
~~~

The controller exposes no public endpoint to mutate permissions; tests call the store directly. Authorization sits **before the controller**. Production still requires object-level authorization at the service/domain layer for individual resources.

### 14.9. JUnit Test: Stale Session Demoted and Disabled

File `src/test/java/com/example/freshauthz/AuthorizationChangeTest.java`:

~~~java
package com.example.freshauthz;

import jakarta.servlet.http.HttpSession;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.mock.web.MockHttpSession;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestBuilders.formLogin;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.authenticated;
import static org.springframework.security.test.web.servlet.response
        .SecurityMockMvcResultMatchers.unauthenticated;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class AuthorizationChangeTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    InMemoryIdentityStore accounts;

    @BeforeEach
    void reset() {
        accounts.reset();
    }

    private MockHttpSession loginAlice() throws Exception {
        MvcResult result = mvc.perform(
                formLogin()
                    .user("alice")
                    .password("local-only-demo-password"))
            .andExpect(authenticated().withUsername("alice"))
            .andReturn();

        HttpSession session = result.getRequest().getSession(false);
        return (MockHttpSession) session;
    }

    @Test
    void removingRoleAppliesToAlreadyLoggedInSession()
            throws Exception {

        MockHttpSession session = loginAlice();

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isOk());

        accounts.demote("alice");  // DB-like role change.

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isForbidden());

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.authorizationVersion").value(2));
    }

    @Test
    void disabledUserCannotKeepAccessThroughOldSession()
            throws Exception {

        MockHttpSession session = loginAlice();

        mvc.perform(get("/me").session(session))
            .andExpect(status().isOk());

        accounts.disable("alice");

        mvc.perform(get("/me").session(session))
            .andExpect(status().isForbidden());
    }

    @Test
    void disabledUserCannotPerformNewPasswordLogin()
            throws Exception {

        accounts.disable("alice");

        mvc.perform(formLogin()
                .user("alice")
                .password("local-only-demo-password"))
            .andExpect(unauthenticated());
    }

    @Test
    void authorizedUserInitiallyHasAdminAccess()
            throws Exception {

        MockHttpSession session = loginAlice();

        mvc.perform(get("/admin").session(session))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value(
                    "admin-access-granted"));
    }
}
~~~

Run:

~~~bash
mvn clean test
~~~

**Expected:** 4 test methods PASS given compatible project/dependencies and Spring Boot/Security configuration. There is no fixed Maven stdout because it varies by environment and Maven Surefire version.

**Significance of the two key tests:**
- Alice's session is created **before** role revocation. `/admin` switching from 200 to 403 on the exact same session proves the endpoint does not rely purely on the stale authority snapshot.
- When disabled, `/me` denies the same old session; new logins also fail because `UserDetails` reads current status.

**What the demo leaves unsolved:** the old session cookie is not deleted at the source, and requests already started before the role change can still finish. If other endpoints use only `hasRole` on the session snapshot, they remain stale. Production needs uniform policy and revocation/session-version mechanisms matched to SLAs.

## 15. Using authorizationVersion / Security Epochs in Production

Reading DB roles on every request can be expensive. A variant uses a **monotonic version**:

~~~sql
CREATE TABLE app_accounts (
    user_id                BIGINT PRIMARY KEY,
    enabled                BOOLEAN NOT NULL,
    authorization_version BIGINT NOT NULL DEFAULT 1,
    token_version         BIGINT NOT NULL DEFAULT 1,
    updated_at            TIMESTAMPTZ NOT NULL
                          DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE account_roles (
    user_id BIGINT NOT NULL REFERENCES app_accounts(user_id),
    role    VARCHAR(120) NOT NULL,
    PRIMARY KEY (user_id, role)
);
~~~

When changing roles:

~~~sql
BEGIN;

DELETE FROM account_roles
 WHERE user_id = 42 AND role = 'ADMIN';

UPDATE app_accounts
   SET authorization_version = authorization_version + 1,
       updated_at = CURRENT_TIMESTAMP
 WHERE user_id = 42;

COMMIT;
~~~

Updating roles and the version must happen in **the same transaction**, so you never see changed roles with an old version or vice versa.

When a user logs in, the `Authentication`/session carries snapshot `authorizationVersion=17`; on each request:
1. Read `currentAuthorizationVersion` from a trusted source.
2. If current > snapshot, **deny** or refresh principal/authorities per policy.
3. If user is disabled, deny regardless of version.
4. If current == snapshot, accept only per policy matching that authority snapshot.
5. Whenever roles are granted/revoked, increment the version atomically.
6. Whenever all tokens must be revoked, increment `tokenVersion` separately.

**Never store permissions in a shared `static` variable across users**, and never use a bare timestamp as a version if clock resolution or drift can collide. An atomically incremented integer in the DB is far safer to compare.

### 15.1. Why Do Version Guards Usually Fail Closed?

If the old session is at version 17 and the database is at 18, there are two options:
- **Reject + reauthenticate/refresh:** simple and safe, though UX may be interrupted.
- **Reload current authorities and rebuild `SecurityContext`:** smoother, but must preserve subject/tenant/session binding and save context accurately. Refreshing roles alone is insufficient if the account was disabled or credentials were revoked.

For role removals or compromises, default to denying sensitive endpoints until refresh/reissue is proven safe.

### 15.2. Can Version Checks Still Use a Cache?

`currentVersion` can be cached in Redis or locally. However, the version itself can still go stale, so effective latency remains bounded by:
- version cache TTL/eviction;
- propagation time;
- consistent database read capability;
- fallback policy when the store is unreachable.

For highly sensitive permissions, read version directly from the DB or a state store with guaranteed latency and consistency. A token claiming `version=18` cannot prove by itself that the DB has not already moved to 19.

## 16. Pitfalls When Updating SecurityContext Directly

Some implementations try to "update a logged-in user's authorities" by constructing a new `Authentication`:

~~~java
Authentication updated = UsernamePasswordAuthenticationToken.authenticated(
        existingPrincipal,
        null,
        refreshedAuthorities);
~~~

This is an **API illustration**, not a complete solution.

Understand that:
- `SecurityContextHolder` typically binds to the **current request/thread**, not every active browser/session.
- Spring Security 6 requires saving the context to `SecurityContextRepository` in many cases for changes to persist past the current request.
- Never construct `authenticated(...) = true` from unverified data or trust client-supplied roles.
- Principals can hold stale account/tenant attributes beyond authorities; refresh must sync all state.
- With multiple active sessions, updating context on one request **does not update other sessions**.
- Under concurrent cache/multi-instance updates, a race can overwrite a newly refreshed context with an older snapshot.

For urgent demotions, **invalidating/revoking sessions and checking current version at request boundaries** is much easier to reason about than mutating all session objects.

## 17. Multi-Instance Rollout and Event-Driven Invalidation

A recommended architecture:

~~~text
Admin Service
    |
    | update roles/status + version
    v
Primary DB + Outbox (transaction)
    |
    | committed event, userId, version
    v
Event Publisher → Queue/Stream
    |
    +--> API Instance A: invalidate local role cache
    +--> API Instance B: invalidate local role cache
    +--> API Instance C: invalidate local role cache
    +--> Resource Server: revoke/refresh policy cache
    +--> Session/IdP Service: invalidate sessions/tokens
    |
    v
Monitoring: consumer lag, event loss/replay, enforcement probe
~~~

**Outbox events must carry explicit version and identity**, not merely "evict all caches" or an email string. Consumers must be idempotent and tolerate duplicate/out-of-order messages; a lower version must never overwrite a higher version.

To reduce propagation delay:
- use change-data-capture/outbox instead of firing an event outside the transaction and hoping both succeed;
- measure consumer lag p95/p99;
- use retries and dead-letter queues for persistent errors;
- run reconciliation jobs scanning current DB versions in case events were missed;
- avoid local caches without TTLs or invalidation listeners;
- protect the event bus from forged messages attempting unauthorized grants/revocations.

**Never treat a "grant role" event as authoritative truth** at a resource server from an unverified message; consumers should verify version and state from a trusted policy source.

## 18. Measuring and Setting Permission Enforcement SLAs

An operational illustration table:

| Change Type | Proposed SLA | Enforcement Path | How to Measure |
|---|---|---|---|
| Display name change | 60 seconds | Profile cache TTL | UI/data freshness probe |
| Grant reporting role | 60 seconds | Event invalidation + TTL | Read API under new role |
| Revoke `ADMIN` | 5 seconds | Current role/version read | Request with old session across every replica |
| Disable compromised account | 5 seconds or per risk policy | Revoke + current status/version | Old session, old JWT, and refresh token tests |
| Password reset | Immediate for new logins; sessions per policy | UserDetails cache evict, session/token revoke | Login with old password and active sessions |
| Tenant membership removal | 5 seconds on tenant-sensitive APIs | Live tenant scope check | Access old resource across every path |

The numbers above are **sample SLAs for discussion**, not guarantees of Spring Security, Redis, JWT, or any international standard. Measure:
- `authz_change_committed_at`, `authz_change_version`;
- `cache_invalidation_received_at` per instance;
- `decision_account_version` and policy version per request;
- count of requests **allowed after revocation commit**;
- elapsed time from commit to effective denial;
- store error rates, fallbacks, and authentication failures;
- measured p50/p95/p99/max staleness;
- skew across replicas and network partitions.

Never log raw JWTs, session cookies, passwords, full emails, or reusable token IDs. Use correlation IDs, stable pseudonymized account IDs, and minimal metadata.

## 19. Distributed Testing: Same Session, Multiple Replicas, Old and New

### 19.1. Scenario 1 — Role Revocation

1. Log in as `alice` with `ADMIN`; capture the session and JWT issued in the test environment.
2. Confirm `GET /admin` returns 200.
3. Call the admin mutation to revoke `ADMIN`; wait for DB commit and version increment.
4. Send `/admin` requests using the **old session/JWT** to every replica (not a fresh session).
5. Measure time from commit until 403/401 per policy.
6. Ensure gateway caches/fallbacks do not keep returning 200 past the SLA.
7. Inject invalidation message delays/drops to verify TTL/version guards still block access.

### 19.2. Scenario 2 — Disable User

1. Log in and create multiple sessions/hit multiple resource servers.
2. Disable the user, commit the transaction, and increment the security epoch.
3. Verify new logins are denied.
4. Verify all prior sessions are invalidated **or** all protected routes deny access.
5. Test old bearer access tokens and refresh tokens per policy; not just form-login cookies.
6. Check whether open WebSockets/API jobs are terminated or reauthorized on next use.

### 19.3. Scenario 3 — Stale Cache Reinsertion

1. Thread A starts `SELECT` for role version 4 and pauses right before cache `PUT`.
2. Thread B commits version 5 and evicts the cache.
3. Allow A to execute cache `PUT` for version 4.
4. Verify sensitive requests **never** accept version 4 when the DB is at 5.
5. Use monotonic/versioned writes or current-version guards so the test passes.

### 19.4. Scenario 4 — Out-of-Order Events

1. Emit versions 12 and 13, delivering them to the consumer in order 13 then 12.
2. The cache must retain version 13 or re-fetch from DB, never reverting to 12.
3. Test retries and duplicate deliveries; applying 13 twice must be idempotent.
4. Simulate an offline consumer; verify reconciliation/TTL recovery.

### 19.5. Scenario 5 — Cache Backend Outage

1. Disable Redis/read model in the test.
2. Sensitive actions must **fail closed** or use controlled live DB reads.
3. Non-sensitive actions may degrade gracefully per SLA.
4. Ensure no generic exception handler turns "unknown permissions" into `permitAll`.

### 19.6. Scenario 6 — In-Flight Transaction

1. Alice starts `POST /admin/transfer`, passing the request-entry permission check.
2. `ADMIN` role is revoked before the transaction commits.
3. If policy requires blocking commit after revocation, the service must check current role/version **inside the same transaction** before writing.
4. If the operation uses an external payment/job queue, maintain approval/transaction state and re-check at the consumer.

**A request accepted before revocation cannot "turn back time" on its own.** Define business rules for in-flight operations rather than making baseless zero-latency/instant-cancellation promises.

## 20. Comprehensive Test Matrix

| Test | What to Confirm |
|---|---|
| `UserDetails` cache hit | Does not query DB repeatedly outside policy |
| Cache miss | Reads and populates the right user/tenant |
| Cache entry expired | Loads fresh version |
| Cache invalidation after role update | Stale entry unused if policy requires current state |
| Role revoked with live session | Admin endpoint denies within SLA |
| Role granted with old session | Clear refresh/re-login policy, no over-granting |
| Account disabled with live session | Protected requests denied |
| Account disabled before login | New password login blocked |
| Password changed | Old hash cache evicted, new password works |
| Unexpired JWT with old role | Denied when violating `authorizationVersion`/live-role policy |
| Refresh token revoked | Cannot mint new access tokens |
| Stale opaque introspection cache | Honors TTL/SLA with active revocation path |
| Local-only `SessionRegistry` | Cross-replica test catches missing cluster coverage |
| Lost cache event | TTL/reconciliation recovers |
| Out-of-order event | Does not downgrade version |
| Cache-aside stale reinsertion | Critical action rejects stale version |
| Multi-tenant same username | Caches do not mix permissions |
| User changes username/email | Identity alias/cache invalidation handled |
| Concurrent role updates | Monotonic versions, no lost updates |
| Event producer fails after DB commit | Outbox retries without losing invalidation |
| Redis unavailable | Critical path fails closed |
| Old cookie after logout/revoke | No longer grants access |
| Method security `@PreAuthorize` | Live policy not bypassed via another route |
| Resource/object-level entitlement | Checks exact resource, not just coarse roles |
| Queue worker after role revocation | Revalidates at execution time if required by business logic |
| Permission-change p99 | Meets SLA across all replicas and token types |

**Do not test only "cache cleared" by asserting a Redis key is gone.** Acceptance criteria must verify **requests/operations can no longer exercise the revoked permission** within the committed window.

## 21. Common Operational Mistakes

1. **Evicting `UserDetails` cache and claiming old sessions are updated.** Sessions hold their own snapshot.
2. **Setting long JWT TTLs with embedded roles while promising instant revocation.** Claims do not update themselves.
3. **Revoking only refresh tokens.** Existing access tokens remain valid until expiry.
4. **Evicting cache on only one node.** Other replicas retain stale data.
5. **Defining no SLA.** Cannot prove whether operations behave correctly or not.
6. **Setting a Redis TTL while session TTL is longer.** The longest-lived permission layer still governs access.
7. **Keying cache globally by username in multi-tenant apps.** Leads to cross-tenant permission mix-ups.
8. **Trusting client-sent `X-User-Role` headers.** Bypasses the trust boundary.
9. **Letting lower-version events overwrite higher versions.** Out-of-order events roll back permissions.
10. **Publishing invalidation before DB commit.** Consumers can read old state and re-cache it.
11. **Updating DB only without outbox/Redis.** Invalidation events can be lost.
12. **Ignoring cache-aside PUT-after-EVICT races.** Stale data reappears.
13. **Caching negative account lookups too long.** Newly activated users keep getting rejected.
14. **Disabling credential erasure globally just to cache roles.** Increases password hash exposure risk.
15. **Assuming `enabled=false` automatically halts all sessions.** Only login-time authentication may check that flag.
16. **Skipping permission checks after queue enqueue.** Jobs execute with revoked permissions.
17. **Checking `hasRole` only in controllers, forgetting method/service authorization.** Another API route can bypass it.
18. **Ignoring tenant/ownership state.** Role remains valid while object ownership changed.
19. **Failing to invalidate sessions on account compromise.** Stolen bearer sessions keep working.
20. **Failing open on store outages.** Redis/DB errors allow stale permissions through.
21. **Using client timestamps as versions.** Can be spoofed or collide across clocks.
22. **Logging cookies/JWTs to measure propagation.** Creates bearer credential leaks.
23. **Ignoring in-flight requests started before commit.** Leads to unfounded "instantaneous" guarantees.
24. **Testing only one replica/token type.** Fails to prove system-wide policy enforcement.

## 22. Production Design and Operations Checklist

- [ ] Identified sources of truth for identity, roles, tenants, permissions, and account status.
- [ ] Classified risk level for each change: grant, revoke, disable, compromise, password reset.
- [ ] Explicit enforcement SLAs defined; measured from database commit to enforcement.
- [ ] Complete inventory of snapshot/cache layers: `UserDetails`, `Authentication`/session, JWT, introspection, gateway, ACLs, downstream services.
- [ ] Cache keys use immutable user ID + tenant/context + version to avoid mixing permissions.
- [ ] Caches have TTLs, max sizes, eviction policies, and miss/outage handling.
- [ ] Critical requests never auto-succeed when current state cannot be retrieved.
- [ ] Current account status/roles or `authorizationVersion` checked on sensitive endpoints.
- [ ] Old sessions/tokens revoked/refreshed per policy.
- [ ] JWT signature/expiry validation is not mistaken for up-to-date permissions.
- [ ] Token version claims are actually compared against current versions, not just embedded decoratively.
- [ ] Every permission change increments a monotonic version in the same DB transaction.
- [ ] Invalidations are published post-commit via outbox/retries where required.
- [ ] Consumers tolerate duplicate/out-of-order events without downgrading versions.
- [ ] Cache-aside stale reinsertion race windows are tested.
- [ ] Explicit strategy exists for in-flight requests and queued jobs.
- [ ] Disabled accounts are blocked on both new logins and old sessions/tokens.
- [ ] `UserDetails`/password-hash caches account for credential erasure and access control.
- [ ] Method security, HTTP filters, and object-level checks enforce consistent policies.
- [ ] Tested across multiple replicas, session stores, resource servers, cache outages, and partitions.
- [ ] Metrics cover event lag, cache age/version, post-revoke allowed requests, and enforcement latency p95/p99.
- [ ] Logs contain no raw JWTs, session cookies, passwords, refresh tokens, or unnecessary personal data.
- [ ] Incident response procedures can revoke a user quickly and verify enforcement took effect.
- [ ] Architecture ensures safe reader/writer/event-consumer rollouts and rollbacks.

## 23. Key Takeaways

**A successful permission change in the database does not automatically refresh every existing `Authentication`.** `UserDetails` caches, HTTP sessions, JWT access tokens, introspection results, and ACL caches are independent layers with different lifetimes.

Practical rules:
1. **Identity determines who**, while current authorization state determines **what is allowed**.
2. **TTL bounds a single cache layer**, not the end-to-end SLA of the entire system.
3. **Evicting `UserDetails` does not evict `SecurityContext`**; sessions must be refreshed/revoked or guarded by live authorization.
4. **A valid JWT signature does not mean roles have not been revoked**.
5. **Versions/epochs only work when compared against live state** and updated atomically.
6. **Critical actions must fail closed when permissions cannot be verified** within SLA.
7. **Test with old sessions/tokens across all replicas after revocation**, rather than just inspecting Redis keys or DB rows.

The operational goal is turning "permissions were revoked" into a **verifiable guarantee**: which requests must be denied, starting when, across which components, and under which failure conditions.

## 24. References

1. [Spring Security 6.5 — Caching UserDetails](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/passwords/caching.html): `CachingUserDetailsService`, `UserCache`, `@Cacheable`, and credential erasure.
2. [Spring Security 6.5 — Authentication Persistence and Session Management](https://docs.spring.io/spring-security/reference/6.5/servlet/authentication/session-management.html): `SecurityContextRepository`, explicit saving, and session concurrency.
3. [Spring Security 6.5 — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/jwt.html): JWT `iss/exp/nbf` validation, authorities, and custom validators.
4. [Spring Security 6.5 — OAuth2 Resource Server Opaque Token](https://docs.spring.io/spring-security/reference/6.5/servlet/oauth2/resource-server/opaque-token.html): introspection and active-token verification.
5. [Spring Security 6.5 — Authorize HTTP Requests](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/authorize-http-requests.html): `AuthorizationManager` and HTTP request authorization.
6. [Spring Security 6.5 — Method Security](https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html): `@PreAuthorize` and service-boundary authorization.
7. [Spring Security 6.5 — UserDetails / Account Flags](https://docs.spring.io/spring-security/site/docs/6.5.2/api/org/springframework/security/core/userdetails/UserDetails.html): account enabled/locked/expired semantics.
8. [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `@Cacheable`, `@CacheEvict`, cache keys, and enabling caching.
9. [Spring Session — Redis](https://docs.spring.io/spring-session/reference/guides/boot-redis.html): distributing HTTP sessions across multiple application nodes.
10. [Spring Framework — Transactional Outbox: Transaction Principles](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): transaction mechanisms for coordinating data and business events.
11. [OWASP — Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html): session lifetime, invalidation, and hijacking defenses.
12. [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): per-request/action permission checks, deny-by-default, and least privilege.
