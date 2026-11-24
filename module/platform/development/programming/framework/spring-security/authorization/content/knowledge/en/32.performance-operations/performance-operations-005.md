# Permission Revocation, Cache Invalidation, and Multi-Instance Consistency in Spring Security

When an administrator revokes a role, removes a member from an organization, or disables an account, **the revoked permission must genuinely stop taking effect across every application instance**. This is both an **authorization** problem and a **data-consistency and operations** problem. Merely updating a permission table in the database may not be enough: `Authentication` in the session still holds old authorities, a JWT remains valid, another instance still uses a permission cache, or an in-flight request already passed the check before revocation occurred.

This lesson focuses on Spring Security in the **servlet stack**, Java 17+, and multi-instance architectures using databases, Spring Cache, Spring Session/Redis, or OAuth2 Resource Server. Spring configuration snippets are explicitly marked when they are **fragments requiring integration into an application**; the Java 17 simulation in section 6 is a complete program compiled and run with plain JDK.

## 1. Identify Precisely What Must Be Revoked

"Revoking permissions" has several meanings and requires handling at different layers:

| Action | Affected Data Source / Mechanism | Satisfaction Condition |
| --- | --- | --- |
| Remove `ADMIN` role from user | User–role relationship; effective permissions | All subsequent decisions requiring `ADMIN` must deny |
| Remove `EXPORT` permission in one tenant | User–tenant–permission relationship; ACL | Cannot export in that tenant, even while still logged in |
| Change resource owner | Resource owner/ACL table | Former owner loses resource access once transfer takes effect |
| Lock account | User status; login sessions/tokens | Must not continue performing protected actions |
| Log out one device | Device's HTTP session or refresh/access token | Corresponding credential can no longer be used per policy |
| "Log out all devices" | All related sessions/refresh tokens; unexpired access tokens | Other devices cannot keep calling APIs with old credentials |
| Revoke one access token | Token state (`jti`/opaque token) | Token is rejected even before `exp`, if the system promises immediate revocation |

**Authentication** establishes who the request comes from, while **authorization** decides whether that principal may perform an action on a specific resource. A cryptographically valid token does not necessarily carry permissions that are still valid at access time.

Example: at 10:00, `alice` holds `REPORT_EXPORT` in tenant `shop-1`. Instances A and B both load the permission list into memory. At 10:05, an admin removes this permission in the database. If instance A receives the invalidation event while B misses it, two identical requests can get contradictory results: A denies, B still allows export. This is the **stale permission via cache** bug.

### Define "Effective" Before Choosing a Solution

Write a testable commitment, such as:

> After the revocation transaction commits, every **new authorization decision** for sensitive data exports must rely on the latest permission version. Requests that started before commit must follow the business's defined consistency rule.

Operational requirements should clarify:

- Does "immediate" mean before the **next request**, within at most a few seconds, or only after token expiration?
- Do you also need to stop requests that already passed authorization and are **in flight**?
- When the permission store/Redis/database is temporarily unreachable, do you return **503** to avoid granting wrong access, or allow stale cache within an approved bound?
- Does revocation apply to **one user, one tenant, one resource, one session, one device**, or the entire account?
- Do you need to track the 99th percentile of revocation propagation latency and how often stale data granted access?

Do not say "immediate revocation" if the design relies solely on a 15-minute TTL.

## 2. Why Does Permission Data Become Stale?

Typical path of a request:

~~~mermaid
flowchart LR
    U["Client + credential"] --> LB["Load balancer"]
    LB --> A["Instance A"]
    LB --> B["Instance B"]
    A --> CA["Permission cache A"]
    B --> CB["Permission cache B"]
    CA --> DB["DB/authoritative permission store"]
    CB --> DB
    AD["Admin revokes"] --> DB
    DB --> EV["Outbox/Event"]
    EV -. "invalidate" .-> CA
    EV -. "invalidate" .-> CB
~~~

Multiple **copies of data** can exist along this flow:

1. **Database/permission store**: authoritative permission source with transactions and owner/role/ACL records.
2. **Authorities on `Authentication`**: computed at login or token decoding; they do not automatically update after DB role changes.
3. **HTTP session**: can hold a `SecurityContext` created prior to revocation.
4. **JWT access token**: typically carries signed scopes/roles; Resource Server validates signature, issuer, and timestamps by default, without knowing the permission DB changed.
5. **In-JVM permission cache**, such as Caffeine: each node has its own copy; `@CacheEvict` only affects the cache backend that node uses.
6. **Distributed cache**, such as Redis: multiple instances share keys, yet you must still mind replica lag, local near-caches, TTL, write ordering, and invalidation reliability.
7. **Event messages**: can arrive late, duplicated, out of order, or be lost if relying on non-durable pub/sub.

Database changes **do not automatically** update these copies. Choosing how to synchronize depends on permission sensitivity and acceptable latency.

## 3. Distinguishing Sessions, JWTs, and Opaque Tokens on Revocation

### 3.1. Applications Using HTTP Sessions

When authentication is stored in an HTTP session, Spring Security can restore `SecurityContext` across requests. After permissions change, authorities inside an old session **can remain a login-time snapshot** unless the application refreshes them.

**Spring Security's default logout** handles the current session via `SecurityContextLogoutHandler`, typically invalidating the session and clearing the security context; Spring also runs other configured handlers. However, logging out **one session** does not imply "logging out every session on every node."

Across multiple instances, you can use **Spring Session** to store HTTP sessions in Redis (or a suitable shared store) instead of per-server session memory. When the same session ID lives in a central store, deleting the session in one place prevents the **next** session read from another node from restoring the old authentication. Verify the exact session repository, indexes, secondary caches, and in-flight request behavior.

The following Java sample **is a complete class when the application has the Spring Session dependency and a matching `FindByIndexNameSessionRepository` bean**; it handles "revoke all sessions indexed by principal":

~~~java
package com.example.security;

import java.util.List;
import org.springframework.session.FindByIndexNameSessionRepository;
import org.springframework.session.Session;

public final class UserSessionRevoker<S extends Session> {
    private final FindByIndexNameSessionRepository<S> sessions;

    public UserSessionRevoker(FindByIndexNameSessionRepository<S> sessions) {
        this.sessions = sessions;
    }

    public int revokeAll(String principalName) {
        // Snapshot the ID list so we do not mutate the map while iterating.
        List<String> ids = List.copyOf(
                sessions.findByPrincipalName(principalName).keySet());
        ids.forEach(sessions::deleteById);
        return ids.size();
    }
}
~~~

Critical prerequisites:

- The repository must support `FindByIndexNameSessionRepository` (for example an **indexed** implementation; not every Spring Session repository has indexing by default).
- The principal index must actually be populated; if unconfigured, `findByPrincipalName` can return empty even when sessions exist.
- `principalName` must match the indexed identifier, avoiding confusion between mutable usernames and immutable user IDs; design consistent ID mapping.
- Deleting a session **does not halt a request that already read SecurityContext earlier**; recheck permissions when performing sensitive operations if business rules require it.
- Local session caches or WebSocket sessions must be handled separately if they retain access independently of HTTP requests.

If the requirement is merely removing `EXPORT` while letting the user keep reading, you can **keep the session** but must refresh/reconcile permissions properly. Deleting all sessions is a simpler way to force re-login, though it is disruptive and still does not handle standalone access tokens.

### 3.2. Applications Using Self-Contained JWT Access Tokens

A JWT typically has `sub`, `iat`, `exp`, `iss`, and possibly `aud` and scope/role claims. Resource Server validates the token on each request, yet **a signed JWT remains valid until expiration**, unless the application adds revocation-status/permission-version checks or a suitable blocking mechanism.

For instance, `alice` has a JWT with `scope=["reports:export"]`, `exp` 45 minutes out. The database removes the permission 1 minute after token issuance. If the endpoint only uses:

~~~java
// Spring method fragment; this checks a claim that may already be stale.
@PreAuthorize("hasAuthority('SCOPE_reports:export')")
public byte[] exportReport() {
    return reportService.export();
}
~~~

then changing the role in the database **does not remove** the `SCOPE_reports:export` authority from the authentication constructed out of the old token. `@PreAuthorize` is still faithfully applying **stale input data**, not refreshing permissions.

Options:

- **Short-lived access tokens + deny renewal of revoked rights**: bounds how long an old token remains usable, but does not satisfy immediate revocation.
- **Denylist of `jti` or token hash** in a shared store: each request checks if the token is revoked; retain block entries at least until token expiry and account for clock skew and issuer/audience.
- **Permission version/epoch**: when permissions change, increment `authzVersion` in the authoritative store; JWTs carry the version at issuance. Resource Server compares the JWT version against the authoritative version on protected requests and rejects stale ones.
- **Check resource-level permissions directly in the service**: for fast-changing owner/tenant/ACL data, read policies from an appropriately consistent source instead of relying solely on claims.
- **Opaque tokens + introspection**: Resource Server queries the authorization server for token status; if the endpoint returns `active=false`, the token is rejected. If introspection or its response is cached, effective revocation delay depends on that cache.

**Browser logout or cookie deletion does not automatically revoke all existing JWTs.** Access tokens and refresh tokens must be handled per authorization server policy; already-issued access tokens can still be accepted elsewhere until expiration or a revocation check stops them.

Never use a **local denylist** per JVM if immediate multi-node enforcement is required without reliable synchronization. Never log raw access tokens; if identifiers are needed in logs, use redacted identifiers or irreversible hashes.

### 3.3. Opaque Tokens and Introspection

Spring Security Resource Server supports OAuth2 opaque token introspection. On each successful introspection, Resource Server relies on the authorization server's response to decide whether the token is active. The upside is centralized state updates; the trade-off is latency, dependency on the introspection service, and per-request cost.

If you add caching for introspection results to reduce load, that cache becomes the **stale-permission window**. Set explicit TTLs or invalidate on revocation; for sensitive permissions requiring immediate effect, do not treat a cached `active=true` response as proof the permission still holds.

## 4. Permission Cache Invalidation Strategies

### 4.1. Per-Instance Local Cache

With Caffeine/in-memory caches, instances A and B have separate memories. `@CacheEvict(cacheNames="permissions", key="...")` on A cannot directly delete an entry on B when each node uses an in-memory cache.

~~~java
// Spring Cache integration fragment: methods on Spring beans.
@Service
class PermissionQueries {
    @Cacheable(cacheNames = "permissions", key = "#tenantId + ':' + #userId")
    public Set<String> findEffective(String tenantId, String userId) {
        return repository.loadEffectivePermissions(tenantId, userId);
    }
}

@Service
class PermissionEviction {
    @CacheEvict(cacheNames = "permissions", key = "#tenantId + ':' + #userId")
    public void evict(String tenantId, String userId) {
        // Spring Cache interceptor handles cache eviction.
    }
}
~~~

This is a **fragment**, omitting imports, fields, and collaborating beans. Operational requirements:

- `@EnableCaching` must be present in the context; both `@Cacheable` and `@CacheEvict` must go through a Spring proxy. Calling `this.evict(...)` on the same object in standard proxy mode can **bypass the advice**.
- Keys must fully represent **tenant + user** and any dimensions that alter outcomes: resource, action, policy, version. Avoid collisions from unescaped concatenation or changing ID formats.
- With local caches, events must reach **every node** with a fallback when events are lost. `@CacheEvict` does not provide broadcasting on its own.
- Eviction after successful method completion is the `@CacheEvict` default; `beforeInvocation=true` changes timing. Still, the annotation does not turn a database update and cache eviction into an atomic distributed transaction.

### 4.2. Shared Cache

A Redis-backed Spring Cache lets multiple instances read/delete the same key, reducing per-node divergence. Yet you still need to check:

- Is there a **near-cache** or local map consulted before Redis?
- Is the key deleted after the permission data **commits** or before commit?
- Can a lagging Redis read replica return stale values after the primary deleted the key?
- On concurrent cache misses, can an old request load permissions **before commit** and repopulate the cache **after eviction**?
- If the cache or event bus is unavailable, what consistency model does the system follow?

Switching from Caffeine to Redis alone **is not enough** to guarantee new permissions take effect immediately unless the entire update/invalidation chain is verified.

### 4.3. Periodic TTL

Using TTL can bound how long stale permissions survive **provided the cache strictly honors TTL**, yet TTL is not synchronized with commits:

- Cache with a 10-minute TTL: an entry created **right before** revocation can stay valid for nearly 10 minutes.
- 30-second TTL: shrinks the window but can increase DB queries, especially when caching per-user/per-tenant permissions.
- Sliding / expire-after-access TTL can extend entry lifetime when users make continuous requests; never use it to claim a hard upper bound without an appropriate expire-after-write setting.

TTL is a **safety net** for lost events, not a standalone solution for permissions requiring immediate effect.

### 4.4. Permission-Versioned Caching

Design the data source with a monotonically increasing `authz_version` per user or per user–tenant, updating the version in the **same transaction** as permission changes.

~~~text
subject_key       authz_version   permissions
shop-1:alice      41             {REPORT_VIEW, REPORT_EXPORT}
   -> REVOKE REPORT_EXPORT + version increments to 42
shop-1:alice      42             {REPORT_VIEW}
~~~

When building the cache, store `PermissionSnapshot(version, grants)`. For sensitive decisions, read the current version from a **sufficiently trusted** source:

1. Read `currentVersion` (prefer transactional/primary if strong consistency is needed).
2. If the local snapshot has a lower or different version from currentVersion, reload fresh permissions.
3. Authorize only from a snapshot matching the current version.
4. If a trusted version cannot be obtained and the action is high-risk, deny/fail closed (e.g., return 503 when the authorization dependency fails) instead of falling back to stale-allow.

**Mandatory invariant:** any change that can affect authorization **always increments the version**, and the permission snapshot travels atomically with its version. If you read the new version while reading permissions from a lagging replica, the system can tag stale data with the new version. Read a consistent snapshot or use appropriate transactions.

Checking versions on every request adds load to the authority store; you can classify endpoints: financial/export/admin actions perform strong checks, while low-risk endpoints use bounded TTLs. Never claim "immediate revocation" if versions come from an independent cache that can lag.

### 4.5. Event-Driven Invalidation, Outbox, and Reconciliation

A more reliable flow when an admin revokes access:

~~~text
Admin request
   -> Transaction: update role/ACL + increment authz_version + write outbox
   -> COMMIT
   -> Outbox dispatcher publishes PermissionsChanged(subject, version)
   -> Each node clears relevant local/near-cache
   -> Every sensitive request still checks the authoritative version
~~~

Why an outbox? If the DB write succeeds but message publishing fails, the event can be lost. Writing the outbox **in the same transaction** and relaying afterward closes that gap. Consumers must be idempotent and tolerate duplicate or out-of-order versions.

Events should contain **subject ID + tenant + version + change type**, without sensitive data or full permission lists. Consumers should only invalidate when the event is newer than the known snapshot; if an old event arrives late, never restore permissions or overwrite a newer version with a lower one.

In Spring, `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` runs a callback **after commit within the same application**, but **is not a durable message bus** and does not guarantee delivery to other nodes. It can work as an internal trigger; to survive crashes between commit and publish, use an outbox/replay or an equivalently durable mechanism.

With Redis Pub/Sub, an offline subscriber misses messages. If auditing/replay is required, consider durable queues alongside periodic `authz_version` checks; pub/sub can still serve as a latency optimization.

## 5. End-to-End Revocation Flow and Race Windows

Suppose we need to remove `REPORT_EXPORT` in `shop-1` from `alice`:

| Milestone | Component | Behavior | Risk to Check |
| --- | --- | --- | --- |
| T0 | A and B | Cache stale permissions version 41 | Both currently allow export |
| T1 | Admin + DB | Transaction changes permission, version 42, outbox; commit | Must not publish new version before data commits |
| T2 | Dispatcher | Publishes version 42 event | Message may be delayed, duplicated, or lost |
| T3 | A | Receives event, invalidates cache | A denies new requests |
| T4 | B | Has not received event, local cache version 41 | If trusting cache alone, B still allows export |
| T5 | B | Checks currentVersion=42 at authoritative store | B discards stale entry and denies |
| T6 | Monitor | Records convergence time | Must detect nodes failing to converge or missing events |

**Specifically: in-flight requests.** A request can pass the permission check at T0.9, admin commits revocation at T1, and then the request writes to the DB at T1.1. To guarantee writes cannot commit after permission revocation, you need explicit transactional policies: appropriate locking, optimistic locking/version-conditional writes, or checking permissions in the same transaction as the data mutation. Filter checks at request start only protect **that point in time**, and do not automatically provide atomicity with later writes.

**Invalidation ordering:** "evict cache first, then commit DB" invites cache misses reading pre-commit data and repopulating stale values. "Commit DB, then invalidate" also leaves a gap between the two steps. Outbox + version guard serves as the primary safety mechanism, while invalidation reduces latency and load.

**Re-granting permissions:** When an admin restores a revoked permission, issue a new version (43). An old version 42 event arriving after 43 must not revert the cache to a historical state or treat 42 as current. When re-fetching from the DB by version, only the latest version is authoritative.

## 6. Runnable Java 17 Simulation: Two Instances and a Lost Event

This program **needs neither Spring nor Redis**, because the goal is to illustrate a distributed-systems property: two instances with separate local caches return different answers when only one node receives invalidation. `PermissionDirectory` represents the shared authority source; `Node` represents JVMs A and B. In a real application, the shared source is a DB/authorization store with transactions and suitable consistency.

Create **`RevocationDemo.java`** (filename matching the public class):

~~~java
import java.util.HashSet;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;

public class RevocationDemo {
    record Snapshot(long version, Set<String> permissions) {
        Snapshot {
            permissions = Set.copyOf(permissions);
        }
    }

    static final class PermissionDirectory {
        private final Map<String, Snapshot> current = new ConcurrentHashMap<>();

        void initialize(String subject, Set<String> grants) {
            current.put(subject, new Snapshot(1, grants));
        }

        Snapshot read(String subject) {
            // Demo: read atomic snapshot from shared source.
            return current.getOrDefault(subject, new Snapshot(0, Set.of()));
        }

        Snapshot revoke(String subject, String permission) {
            return current.compute(subject, (key, old) -> {
                if (old == null) {
                    throw new IllegalArgumentException("Unknown subject: " + key);
                }
                Set<String> next = new HashSet<>(old.permissions());
                next.remove(permission);
                // Update permissions and version as an immutable snapshot.
                return new Snapshot(old.version() + 1, next);
            });
        }
    }

    static final class Node {
        private final String name;
        private final PermissionDirectory directory;
        private final Map<String, Snapshot> local = new ConcurrentHashMap<>();

        Node(String name, PermissionDirectory directory) {
            this.name = name;
            this.directory = directory;
        }

        boolean localOnly(String subject, String permission) {
            // INTENTIONALLY WRONG for permissions needing immediate effect:
            // stale cache is not refreshed if the node misses the event.
            Snapshot snapshot = local.computeIfAbsent(subject, directory::read);
            return snapshot.permissions().contains(permission);
        }

        boolean withVersionGuard(String subject, String permission) {
            Snapshot authoritative = directory.read(subject);
            Snapshot cached = local.get(subject);
            if (cached == null || cached.version() != authoritative.version()) {
                local.put(subject, authoritative);
                cached = authoritative;
            }
            return cached.permissions().contains(permission);
        }

        void onPermissionsChanged(String subject, long newVersion) {
            // Remove stale entry; event does not contain the permission list.
            local.computeIfPresent(subject, (key, cached) ->
                cached.version() < newVersion ? null : cached);
        }

        @Override
        public String toString() {
            return name;
        }
    }

    public static void main(String[] args) {
        PermissionDirectory source = new PermissionDirectory();
        String subject = "shop-1:alice";
        String action = "REPORT_EXPORT";
        source.initialize(subject, Set.of(action, "REPORT_VIEW"));

        Node a = new Node("A", source);
        Node b = new Node("B", source);

        System.out.println("Before: A=" + a.localOnly(subject, action)
                + ", B=" + b.localOnly(subject, action));

        Snapshot changed = source.revoke(subject, action);
        System.out.println("After revoke, no event: A=" + a.localOnly(subject, action)
                + ", B=" + b.localOnly(subject, action));

        // Simulate B temporarily losing connection to the event bus.
        a.onPermissionsChanged(subject, changed.version());
        System.out.println("Event delivered only to A: A=" + a.localOnly(subject, action)
                + ", B=" + b.localOnly(subject, action));

        System.out.println("With version check: A=" + a.withVersionGuard(subject, action)
                + ", B=" + b.withVersionGuard(subject, action));
    }
}
~~~

Compile and run:

~~~bash
javac RevocationDemo.java
java RevocationDemo
~~~

**Exact stdout**:

~~~text
Before: A=true, B=true
After revoke, no event: A=true, B=true
Event delivered only to A: A=false, B=true
With version check: A=false, B=false
~~~

Analysis:

1. Initially A and B load permissions at version 1.
2. `source.revoke` bumps to version 2 and removes `REPORT_EXPORT`; **both local caches remain at version 1**.
3. Only A receives the event, so A evicts its cache and re-reads version 2; B keeps allowing because of its stale cache.
4. `withVersionGuard` checks the authoritative version before deciding; B detects the version mismatch, loads the new snapshot, and therefore denies.

**Simulation limitations:** an in-process `ConcurrentHashMap` merely represents a shared store and does not simulate crashes, network partitions, replica lag, or DB transactions. Reading a version then deciding still has a race if permissions change **after** the read. To prevent writes from committing wrongly after revocation, use transactional consistency mechanisms. Never copy `localOnly` into production for sensitive permissions.

## 7. Implementing Authorization Policies in Spring Security

### 7.1. Active Permissions Must Be Verified at the Right Moment

A Spring Security method can call a policy bean that checks current state:

~~~java
// Illustrative fragment placed in a Spring service bean.
@PreAuthorize("@exportPolicy.canExport(authentication, #tenantId)")
public byte[] export(@P("tenantId") String tenantId) {
    return reportExporter.buildReport(tenantId);
}
~~~

`@P` has type `org.springframework.security.access.method.P` so `#tenantId` does not depend on compiler flags. The `exportPolicy` bean must consult the right permission source for the current tenant:

~~~java
// Fragment: policy with injected repository/authority-store.
public boolean canExport(Authentication auth, String tenantId) {
    if (auth == null || !auth.isAuthenticated()) {
        return false;
    }
    String subject = auth.getName();
    return permissions.existsCurrentGrant(
            tenantId, subject, "REPORT_EXPORT");
}
~~~

**Never assume** `auth.getName()` is an immutable user ID in every system: with JWT, it may default to `sub`; with custom principals, it may be username. Choose and test the exact mapping against your actual authentication system.

If the expression only uses `hasAuthority("REPORT_EXPORT")` on an `Authentication` created from an old session/JWT, Spring Security enforces that condition accurately yet **cannot know** the grant was revoked after `Authentication` was built. The policy needs fresh permission checks or equivalent version/session/token invalidation.

For specific resources, check **tenant, resource owner, and action**, not just global permissions. For example, a user may still hold export permission in `shop-2` after having it revoked in `shop-1`.

### 7.2. Permission Update and Event Emission Flow

In the admin service, change grants and increment the version in the **same transaction**; the outbox record goes in that transaction too:

~~~java
// Architectural fragment; repositories, entities, and outbox are
// application-implemented components, not built-in Spring Security APIs.
@Transactional
public void revokeExport(String tenantId, String userId) {
    grants.deleteGrant(tenantId, userId, "REPORT_EXPORT");
    long version = grants.incrementAuthzVersion(tenantId, userId);
    outbox.insert(new PermissionsChanged(tenantId, userId, version));
}
~~~

A dispatcher reads the outbox, publishes events, and marks them processed **after** broker acknowledgement; on failure, it retries. Consumers process events with at-least-once delivery and idempotency. Do not push full sensitive permission sets into event payloads.

If the update rolls back, **never** emit an event claiming permissions changed. If another change commits later, the higher version must win on comparison; never infer state from whichever event arrived last.

### 7.3. Cache Synchronization: Events for Speed, Versions for Safety

Operational architecture can split into two paths:

- **Fast path:** after commit, the outbox/broker publishes an event → every node proactively invalidates its local/near-cache.
- **Safety path:** every sensitive decision checks version/ACL from a sufficiently consistent source; if an event is lost, requests still detect stale permissions.

If policy allows a bounded delay (for example public-read documents), you can combine TTL with events instead of source checks per request, but you must **document and measure that window**. For admin, payment, or sensitive data export permissions, never treat TTL as an immediate revocation guarantee.

### 7.4. Handling Permission Store or Redis Failures

When a request cannot read authoritative permissions, the choice is a pre-defined **product/security decision**:

- For high-risk actions, use **fail closed**: refuse the action; you may return 503 when the permission-check mechanism fails, avoiding sensitive data exposure.
- For certain low-risk read-only actions, allow bounded-age caching with clear degraded-mode alerting if policy permits.
- Never silently replace `AuthorizationDecision.DENY` with `ALLOW` just because the permission store timed out.
- Separate **legitimate denials** (403) from **dependency outages** (typically 503); monitoring and incident investigation will be far clearer.

Never rely solely on in-memory cache lifetime to bound revocation time. When an instance restarts, its cache clears; meanwhile on live node B, its cache can persist much longer.

## 8. Testing Across Multiple Instances

A unit test that calls `cache.evict(user)` and checks an empty map proves very little. You must test **actual authorization output behavior** with at least two real instances/contexts using realistic sessions/tokens and permission stores.

### Minimum Matrix

| Scenario | Action | Expectation |
| --- | --- | --- |
| Before revoke | A/B have valid `EXPORT` | Both allow |
| After DB commit | Revoke on A, call API on B with old credential | B denies within SLA |
| Event reaches A only | Block/delay B's consumer | B still denies if immediate version check is required |
| Duplicate event | Deliver same version repeatedly | Stable outcome, never re-grants |
| Out-of-order event | Deliver version 12 after version 13 | Does not roll back state to 12 |
| Regrant | Revoke then re-grant, bumping version | Only the new version is allowed |
| Different session, same user | Log in on two browsers/nodes, "logout all" | Both sessions revoked per policy |
| Old JWT | Use unexpired JWT `exp` after revoke | Rejected if immediate revocation is required |
| Opaque token | Introspection returns `active=false` | Resource Server rejects |
| Cache miss + commit race | Loading old rights as commit occurs | Does not overwrite new cache with old rights |
| In-flight write request | Starts before revoke, commits after revoke | Outcome follows chosen transactional constraint |
| Network partition | B gets no events and cannot reach store | Does not grant sensitive access from unverified data |
| New instance | C joins after revoke | Does not load stale rights from replica/cache |
| Tenant isolation | Revoke `shop-1`, keep `shop-2` | Only affects the matching tenant's grant |

### Integration Test Scenario Template

With Docker Compose/Testcontainers (when the real system uses Postgres/Redis/broker), launch **two application instances sharing DB/Redis**. Execute:

~~~text
1. Grant Alice EXPORT in tenant X, version 7.
2. Log in / issue token, send protected GET/POST through instances A and B.
3. Ensure both caches are warmed up.
4. Admin on A revokes EXPORT and commits version 8.
5. Simulate B missing the event, or delay consumer/invalidation.
6. Call with the same old credential through B and A; check status 403 or
   defined authorization error, and verify no data was exported.
7. Deliver duplicate event and late version 7 event to B; call again.
8. Re-grant permission with version 9; verify permission takes effect only
   after policy/version is properly updated.
9. Start a new instance C; verify no stale permission exists.
10. Measure elapsed time from COMMIT until every node rejects.
~~~

**Never use `@WithMockUser` as proof of end-to-end JWT/session revocation testing.** That annotation pre-populates an authentication for tests, bypassing real token/session issuance and parsing. It is great for testing policy logic, but you need integration tests with real credentials for the mechanism under test.

When testing `@PreAuthorize` with MockMvc, inject the Spring-managed bean so calls pass through the method-security proxy and enable `@EnableMethodSecurity`. When testing full requests, verify the exact `SecurityFilterChain` and CSRF/filter behavior so you do not confuse a 403 from CSRF with a 403 from revoked permissions.

### Verifying Data Preservation Invariants

For sensitive operations, assert system state as well:

~~~java
// Assertion fragment, used with an appropriate test framework.
assertThat(response.getStatus()).isEqualTo(403);
assertThat(exportStore.countExportsFor("shop-1", "alice"))
        .isEqualTo(0);
~~~

This is **not** standalone code: `response` and `exportStore` are integration test fixtures. The point is to verify **no side effects** occurred after authorization failed, even when the check ran on another node.

## 9. Monitoring, SLOs, and Incident Handling

Track at least these metrics:

- **Revocation-to-enforcement latency:** elapsed time from DB commit until new requests are reliably rejected on every node; measure p50/p95/p99 and max per policy.
- **Event delivery lag/outbox backlog:** unpublished messages, retries, dead-letters, consumer lag, nodes not yet on the latest version.
- **Permission cache age/version:** entries behind the authoritative version, hit/miss ratios, invalidation frequency, stale cache refills.
- **JWT/session state:** revoked sessions count; rejected stale tokens; 401/403/503 counts split by cause.
- **Dependency latency and availability:** database permission lookups, Redis/session store, introspection endpoint, message broker.
- **Permission audit events:** who revoked, target subject, tenant, permission, before/after versions, commit timestamp, and correlation ID.

Never log raw tokens, session IDs, or sensitive permission payloads. Follow data protection and log-access controls for user/tenant IDs in logs.

An example measurable objective is "100% of export requests **starting authorization after commit** must check the latest permission version from the authoritative source; if the check fails, do not export." This objective is stronger than "event delivered within 1 second": fast event delivery does not prove all subsequent permission decisions used fresh data.

With only a 60-second TTL and no authoritative check, you **cannot** certify a 1-second SLA. To prove a bound, account for every real latency source: TTL, replica lag, event backlog, token lifetime, reload process, clock skew, and in-flight requests. If just one layer can hold stale rights for 20 minutes, faster layers do not eliminate that window.

### Runbook When a Node Is Suspected of Honoring Stale Permissions

1. Identify the commit timestamp and current permission version in the authoritative source.
2. Compare the cache/session/token version used by the suspect request, checking logs via correlation ID.
3. Inspect the node, filter chain, policy/method-security path, and cache provider handling the request.
4. Check outbox backlog, consumer lag, subscriber restarts, retries, and dropped events.
5. If risk is high, pause the sensitive action using designed safety switches while restoring the authoritative verification path.
6. After remediation, re-run 2+ instance integration tests and verify convergence SLOs; add a regression test for the discovered counterexample.

## 10. Common Pitfalls

**"Updated the user_role table so the permission is gone."** `Authentication` or JWTs can carry snapshotted authorities from earlier. You need token/session refresh/revocation or dynamic authorization.

**"Ran `@CacheEvict` so every instance cleared its cache."** That holds only for the scope of the `CacheManager` and backend. Local JVM caches do not propagate across nodes; Spring Cache abstraction does not build an event bus for you.

**"Redis Pub/Sub alone is enough."** Disconnected subscribers miss events. You need TTL, version checks, durable bus/replay, or a combination per SLA; for high-risk systems, version/authoritative checks are the primary control.

**"Evict cache before transaction commit to be safe."** Another node can cache-miss and load stale uncommitted rights, then repopulate. Design must consider ordering, transactions, and versions.

**"We have versions so the cache is always accurate."** If versions come from a lagging replica or an ACL update path forgets to bump the version, decisions are still wrong. Verify invariants and consistent read paths.

**"Logging out on node A invalidates the JWT on B."** Session logout and JWT revocation are separate mechanisms; self-contained access tokens can remain valid until `exp` without extra blocking.

**"Revocation definitely stops requests already started."** The permission check can happen before the revocation commit while side effects occur afterward. Strict operations need transactions/locking/conditional updates, not middleware alone.

**"Disabling cache completely is enough."** If tokens/sessions hold old authorities, or the DB reads from lagging replicas, stale permission sources still exist even without Spring Cache.

## 11. Acceptance Checklist

- [ ] Clearly define whether revoking **roles, tenant grants, resource ACLs, sessions, tokens**, or account state.
- [ ] Write a concrete SLA: from commit time to **new authorization decisions** across all instances.
- [ ] Every permission change updates snapshot and version atomically/consistently.
- [ ] Check authorities stored in `Authentication`, JWTs, refresh tokens, and HTTP sessions.
- [ ] `@CacheEvict` runs through the Spring proxy against the right backend; cache keys include required tenant/user/action/resource.
- [ ] Have a strategy for multi-node local caches and delayed/lost/out-of-order messages.
- [ ] Events are only an optimization; the primary control path meets SLA even when subscribers are offline.
- [ ] When cache/store is unavailable, never auto-grant sensitive actions from unverified snapshots.
- [ ] Test two or more instances with old credentials before/after revocation.
- [ ] Test unexpired tokens, sessions on other devices, re-granted permissions, and newly started nodes.
- [ ] Test **no side effects** occur after denial; test races on writes requiring atomicity.
- [ ] Have audits and metrics proving enforcement latency, not merely confirming a message was sent.

## 12. Reference Documentation

- Spring Security — Handling Logouts: https://docs.spring.io/spring-security/reference/servlet/authentication/logout.html
- Spring Security — Session Management: https://docs.spring.io/spring-security/reference/servlet/authentication/session-management.html
- Spring Security — OAuth2 Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security — OAuth2 Opaque Token: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Session — Redis with Spring Boot: https://docs.spring.io/spring-session/reference/guides/boot-redis.html
- Spring Session — `FindByIndexNameSessionRepository` API: https://docs.spring.io/spring-session/reference/api/java/org/springframework/session/FindByIndexNameSessionRepository.html
- Spring Framework — Cache annotations (`@Cacheable`, `@CacheEvict`): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html

**Expected outcome:** After an admin revokes permissions, a new request arriving at **any** instance enforces the committed validity policy; dropped events or stale local caches cannot silently authorize sensitive actions. For sessions/JWTs, explicitly state which credentials are revoked, when they expire, and what mechanism enforces it.
