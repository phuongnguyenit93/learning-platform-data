# Time-Bounded Decision Caching and Invalidation on Permission Changes

## 1. Objectives and context

In Spring Security Authorization, a decision such as **"Can Alice read Document #42?"** may require querying an ACL database, permission groups, dynamic policies, or an external Policy Decision Point (PDP). Repeating the same check on every request consumes queries and adds latency. **Authorization decision caching** temporarily stores an `ALLOW` or `DENY` outcome for reuse while all relevant conditions remain valid.

However, an `ALLOW` valid at 10:00 is not guaranteed to remain valid at 10:01: an administrator may **revoke permissions**, a user may be removed from a group, a document's owner may change, tenant membership may be canceled, or a new policy may roll out. Caching improves performance, yet can turn stale decisions into **access vulnerabilities** without expiration and invalidation mechanisms.

This lesson belongs to the **Dynamic Policies** group of the Spring Security Authorization module. After this lesson, you will be able to:

1. Distinguish **authorization decision caching** from data caching, sessions/JWTs, role permissions, and Spring Security's ACL cache.
2. Design cache keys around **tenant + stable subject + action + resource type/ID + policy version** instead of just username or resource ID.
3. Apply TTLs to both `ALLOW` and `DENY`, understanding that **TTL bounds staleness rather than guaranteeing instant revocation**.
4. Invalidate when permissions are granted/revoked, resource/owner/parent ACL changes, roles/memberships change, or policies deploy.
5. Explain how to coordinate **transaction commit → event → invalidation**, and handle delayed/lost events, multiple instances, and race conditions.
6. Measure hit/miss rates, decision evaluation counts, latency, stale-decision windows, and detect failure modes.
7. Run a Java 17+ project with real Spring Method Security, TTL caching using a fake clock, and JUnit 5 tests covering grant/revoke/expiry/tenant isolation/fail closed.
8. Identify when **long-lived caching is forbidden**, or when the authoritative store must be checked directly at sensitive operation time.

**Scope:** Java 17+, Spring Boot BOM 3.5.x, Spring Security 6.5.x, Spring Test/JUnit 5. The in-memory cache example uses `ConcurrentHashMap` to keep mechanics clear; production should use a cache library with `maximumSize`, TTL, metrics, and proper invalidation like Caffeine, or a controlled distributed architecture.

## 2. What is cached, and which data does a decision depend on?

Example: `Document#42` in `TENANT_A`; Alice has `READ` permission, not `WRITE`. A decision may depend on:

- **Subject:** verified stable identity `issuer + subject`; not just `username`, as two tenants may share a username.
- **Tenant:** server-verified tenant; never an arbitrary value from a request header.
- **Action:** `READ`, `WRITE`, `DELETE`, `APPROVE`, `EXPORT` are actions with independent policies.
- **Resource:** type `Document`, ID, resource tenant, owner, state, sensitivity, parent ACL relationships.
- **Policy:** ACL version/epoch, organization rule version, role hierarchy, permission groups, tenant membership.
- **Context:** current time, IP/device assurance, authentication level, transaction amount, legal hold, workflow, or per-request changing attributes.

Not every factor should be cached. For policies with continuously changing conditions, it is better to **cache only the immutable/low-churn portion** and re-check dynamic conditions on every call. If a policy uses current time, IP, account status, or recently changed data, include them in the key or exclude them from the cached decision portion.

### 2.1. Flow diagram

```text
Caller -> Spring-managed service proxy
                 |
                 v
   @PreAuthorize("hasAuthority('DOC_READ') and
                  @decisionPolicy.can(authentication, #id, 'READ')")
                 |
                 v
           Trusted principal?
            /           \
        invalid          valid
          |                |
        DENY               v
                Cache key = tenant + issuer/sub +
                            action + resource type/id +
                            policy revision
                             |
                     +-------+-------+
                     |               |
                 HIT & fresh     MISS/expired
                     |               |
                     v               v
               ALLOW / DENY      Authoritative policy
                                     |
                                ALLOW / DENY
                                     |
                             cache with TTL
                                     |
                                     v
                              decision returned
```

When permissions change:

```text
Admin changes ACL/role/owner  --transaction--> COMMIT
                                           |
                                           v
                                  policy version increments
                                           |
                                           v
                              send invalidation event
                                           |
                         +-----------------+-----------------+
                         |                 |                 |
                      node A            node B            node C
                      evict             evict             evict
                         |                 |                 |
                         +------------ next request ----------+
                                           |
                                           v
                                 recompute decision
```

**Note:** events and caches across multiple nodes can be delayed or lost. Adding a TTL only guarantees the decision expires after a period **by the node's clock**; it does not automatically guarantee the entire system sees a revocation instantaneously.

## 3. Designing cache keys: never accidentally share outcomes

### 3.1. Minimal key for the illustrative policy

```java
record ResourceKey(
    String tenant, String resourceType, long resourceId
) {}

record SubjectKey(
    String tenant, String issuer, String subject
) {}

record DecisionKey(
    ResourceKey resource,
    SubjectKey actor,
    String action,
    long policyRevision
) {}
```

These are Java `record` types compilable in a Java 17+ project, used in the complete test example below.

| Key component | Why mandatory in this scenario? |
| --- | --- |
| Resource's `tenant` | `Document#42` in A differs from `Document#42` in B |
| `resourceType` | `Document#42` differs from `Invoice#42` |
| `resourceId` | Distinguishes objects of the same type |
| Actor's `tenant` | User in A must not receive B's cache entry |
| `issuer + subject` | Name `alex` can collide across identity providers/tenants |
| `action` | `READ` must never be reused for `WRITE` or `EXPORT` |
| `policyRevision` | Changed permissions must hit a new cache generation |

If the policy also depends on `roleSet`, MFA level, owner, workflow state, time, or request context, **the key above is insufficient**. Include an `authorizationEpoch`/session/role version in the key or check those conditions outside the cache. Never turn every claim/request into an uncontrolled complex key: define **the exact cacheable scope** via threat modeling.

### 3.2. Common wrong keys

```java
// WRONG: two tenants with the same resource ID could share a decision.
String key1 = "document:42";

// WRONG: username is not necessarily a global user identity.
String key2 = "alex:document:42";

// WRONG: READ and WRITE have different policies.
String key3 = "TENANT_A:alice:document:42";

// WRONG if role/policy changed without changing revision:
String key4 = "A:alice:document:42:READ";
```

Nor must the client send a prebuilt `cacheKey` or `tenantId` for the server to use directly. Keys must be built from **verified `Authentication`** and resources resolved from trusted sources.

### 3.3. Never cache data records as decisions

An `ALLOW`/`DENY` cache **differs from** a response body or entity cache. After authorization permits, returning the document must still scope by tenant/resource, apply field redaction, and check additional policies if needed. If data is cached solely by `id=42`, even a correct decision cache can let an endpoint return another tenant's body.

Spring Security ACL's `AclCache` caches ACL objects, which is **not synonymous** with a Boolean `hasPermission` cache. The two layers have distinct TTLs/invalidations; revocation must refresh both ACL data and computed decisions in time.

## 4. TTL: bounding staleness, not replacing revoke events

### 4.1. Mechanism and TTL selection

A typical entry:

```text
key       = (TENANT_A, issuer-a/user-123, READ, Document#42, rev=7)
decision  = ALLOW
createdAt = 10:00:00
expiresAt = 10:00:05
```

If current time is **before** `expiresAt`, the entry may be reused; at or after expiry it must be recomputed. The test example uses a fake `Clock` to test boundary timestamps without `Thread.sleep`.

An illustrative choice:

- **ALLOW TTL = 5 seconds**.
- **DENY TTL = 2 seconds**: newly granted permissions become visible sooner when grant events lag.
- For financial/sensitive decisions, use an even shorter TTL or **skip caching and re-check the authoritative source** before commit.
- TTL must have an upper bound and observability policy; never default `ALLOW` to live as long as the JWT/session.
- Cache size must be bounded to prevent excessive key cardinality and memory exhaustion.

These 5s/2s numbers are **learning configurations**, not universal defaults for every product. If the requirement is "revoked permissions take effect within at most 1 second", a 5-second TTL is **insufficient** without reliable invalidation.

### 4.2. What TTL does not guarantee

- Does not revoke instantaneously when an admin revokes access.
- Does not cancel an already-authorized request currently executing.
- Does not synchronize caches across multiple instances.
- Does not detect revoked tokens/JWTs if the app relies solely on authorities inside the old token.
- Does not alter the outcome of a decision already cached from wrong data.
- Does not guarantee accurate **wall-clock** time; production should use the cache library's monotonic clock/ticker for expiration and an injectable clock for tests.

**When expiry is too long:** stale `ALLOW` permits unauthorized access after revocation. **When expiry is too short:** increases database/PDP hit rates, reduces performance gains, and can trigger a "cache stampede".

## 5. Invalidation: when must entries be evicted or version-bumped?

Events to consider:

| Event | Invalidation scope to evaluate |
| --- | --- |
| Grant/revoke ACE for a document | All decisions on that resource, related actions/SIDs |
| Owner change or DRAFT→APPROVED transition | Resource and owner/state-dependent permissions |
| Parent ACL or `entriesInheriting` change | Child and inheriting descendants |
| Alice's role/group membership changes | Decisions relying on Alice's authorities/groups; old tokens handled separately |
| Tenant membership revoked | All related actor–tenant decisions, plus session/token/DB scopes |
| Policy code/config version changes | Invalidate by policy version/epoch or controlled clear |
| Resource deleted/moved to another tenant | Decisions for old resource, new keys, and cached data |
| Sensitivity level or export approval changes | READ/EXPORT decisions and related field projections |
| Emergency user suspension | Do not wait for normal TTL; block via authoritative gate/denylist |

### 5.1. Two commonly combined techniques

**Active eviction:** after a successful update, evict caches by resource/subject/policy. Use `cache.invalidate(resource)`, Pub/Sub topics, a message bus, or framework cache eviction.

**Version/epoch:** the key embeds the policy version. When permissions change, the resource/policy/subject version increments. Subsequent requests use the new key so they cannot match an old-version `ALLOW`.

```text
Before revoke: key = (... Document#42, revision=7) -> ALLOW
After revoke:  key = (... Document#42, revision=8) -> MISS -> DENY
```

A **critical condition**: every node must learn **the new revision** reliably and fast enough. If the revision lives only in node A's RAM, node B never learns it changed and keeps serving cached `ALLOW`. Versioning **does not solve distributed consistency on its own**; many systems need revisions fetched from an authoritative store or versioned event streams, plus handling for missed events.

### 5.2. Why evict after commit?

If a transaction changes an ACL and publishes invalidation **before commit**, another node can cache-miss, read **the old permissions**, and cache the stale outcome right as the transaction commits. If the transaction rolls back, pre-commit invalidation also causes pointless churn.

A pattern to consider:

```text
BEGIN
  UPDATE acl_entries ...
  UPDATE permission_revision ...
  INSERT INTO outbox(permission-changed, revision=8)
COMMIT
  -> outbox publisher / after-commit callback
  -> subscribers evict or bump revision
  -> monitoring/ack/retry
```

An outbox lowers the risk of the DB committing while the process crashes before emitting the event. Still, subscribers can lag; TTLs and versioned/strong reads remain safety nets. For ultra-sensitive permissions, reading the authoritative revision on every request or handling synchronously may be required despite the cost.

### 5.3. Delayed, lost, duplicate, or out-of-order events

- **Lost events:** TTL prevents entries from living forever; if instant revocation is required, TTL alone is not enough.
- **Duplicate events:** invalidation must be idempotent.
- **Out-of-order events:** attach monotonically increasing revisions; never overwrite a newer permission snapshot with an older one.
- **Newly started nodes:** if they missed past events, start with an empty cache; if preloading snapshots, attach revisions.
- **Concurrent misses:** many simultaneous misses can slam the PDP; use coalescing/synchronous `cache.get(key, loader)` to curb stampedes.
- **Invalidate-vs-load race:** an old loader can finish after a revoke. Version tokens from trusted sources or sequenced invalidation are needed to solve this completely; never claim `cache.evict()` alone linearizes every request.

## 6. Rules for safe decision caching

1. **Deny by default:** invalid principal, wrong tenant, nonexistent resource, missing permission, or policy source error => never grant.
2. **Check authority every request:** in Spring, keep `hasAuthority` outside the cache; never use cached `ALLOW` to skip authentication or account status checks.
3. **Cache only successful evaluations:** network/PDP errors are not `ALLOW`. If caching error-induced `DENY`, document separate semantics/TTL so outages are not masked.
4. **Complete keys:** resource, tenant, actor issuer/sub, action, policy version; add role/membership/assurance versions if the policy depends on them.
5. **Bounded cache:** cap size, TTL, metrics, and avoid putting raw JWTs/PII into loggable keys; use opaque stable IDs.
6. **Never let users trigger invalidation or pick policy revisions:** management events come only from authenticated sources.
7. **Audit permission changes:** editor, target, old/new permissions, revision, commit time, and nodes receiving invalidation.
8. **Sensitive WRITE/APPROVE calls need write-time checks:** `@PreAuthorize` using a cache is only one layer; add conditional updates/versioning/transactions.
9. **Define stale windows with SLOs:** e.g., max stale grant, P99 propagation, detection alerts; avoid vague terms like "fresh cache".
10. **Separate policy caches from data caches** and protect both paths. Invalidating a decision does not automatically evict a cached document payload.

## 7. Integrating with Spring Security Method Security

In Spring Security 6.5, `@EnableMethodSecurity` activates interceptors for `@PreAuthorize` on Spring-managed beans. SpEL can invoke a Java bean:

```java
@PreAuthorize(
    "hasAuthority('DOC_READ') and " +
    "@decisionPolicy.can(authentication, #id, 'READ')"
)
public String read(@P("id") long id) {
    return repository.findAllowedDocument(id);
}
```

This is a **fragment**, not a standalone program. `decisionPolicy` must be a registered bean with that name; `@P("id")` identifies the parameter name for SpEL. `authentication` is provided to the expression by Spring Security.

Never use just:

```java
@Cacheable(cacheNames = "decisions", key = "#id")
public boolean canRead(long id) { ... }
```

That is an **anti-pattern**: the key lacks actor, tenant, action, and version; furthermore, both `@Cacheable` and method security rely on AOP, so advice ordering, self-invocation, and cache conditions must be tested.

With Spring Cache/Caffeine, use a consistent key builder and `@CacheEvict` or post-commit invalidation APIs. **Spring Security does not automatically cache `@PreAuthorize` outcomes** merely because Method Security is enabled. Decision caching is application/PDP logic, distinct from `SecurityContext`/session caching.

## 8. Runnable Java 17+ project, testing TTL with a fake clock

The test project uses **real Spring Method Security** without mocking the interceptor, while keeping the policy store and document repository **in-memory** to focus on caching. It demonstrates:

- Two resources sharing ID 42 across two tenants; two users named `alex` with distinct subjects.
- Keys containing tenant + issuer/sub + action + type/ID + revision.
- 5s ALLOW TTL, 2s DENY TTL; tested via fake `Clock` without `Thread.sleep`.
- Admin grant/revoke increments revision and invalidates decisions by resource.
- A test simulating **lost invalidation** within the same JVM; the new revision still forces a cache miss.
- Tests for authority gates, no-rule cases, policy source outages, cache hits/misses, isolation, and zero side effects on deny.

**Design limitations:** the version map and decision cache live inside **one JVM**; multi-node production requires distributing invalidations/revisions. `ConcurrentHashMap` in the example caps size crudely by clearing all entries when full; it is **not** a production eviction algorithm, nor does it prevent all cross-node races like a distributed transaction.

### 8.1. Project structure

```text
decision-cache-demo/
├── settings.gradle
├── build.gradle
└── src/test/java/demo/DecisionCacheSecurityTest.java
```

`settings.gradle`:

```groovy
rootProject.name = 'decision-cache-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-security'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

This project uses `src/test/java` only: `testImplementation` suffices. When turning this into a real application, place Spring Security/Context dependencies in `implementation` and a suitable runtime cache library. Java 17 is the minimum for `record`; no preview APIs are used.

### 8.2. Complete Java integration test file

Create `src/test/java/demo/DecisionCacheSecurityTest.java`:

```java
package demo;

import java.security.Principal;
import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneId;
import java.time.ZoneOffset;
import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicLong;
import java.util.concurrent.atomic.AtomicReference;
import java.util.function.Supplier;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.authority.AuthorityUtils;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringJUnitConfig(DecisionCacheSecurityTest.Config.class)
public class DecisionCacheSecurityTest {

    private static final String ISSUER = "https://idp.example.test";

    public record Actor(
        String tenant, String issuer, String subject, String username
    ) implements Principal {
        @Override
        public String getName() {
            return username;
        }
    }

    public record ResourceKey(
        String tenant, String type, long id
    ) {}

    public record SubjectKey(
        String tenant, String issuer, String subject
    ) {}

    public record GrantKey(
        ResourceKey resource, SubjectKey actor, String action
    ) {}

    public record DecisionKey(
        ResourceKey resource, SubjectKey actor,
        String action, long revision
    ) {}

    public record Entry(boolean allowed, Instant expiresAt) {}

    private static final Actor ALICE = new Actor(
        "TENANT_A", ISSUER, "subject-a", "alex");

    private static final Actor BOB = new Actor(
        "TENANT_B", ISSUER, "subject-b", "alex");

    private static final Actor IMPOSTOR = new Actor(
        "TENANT_A", ISSUER, "other-subject", "alex");

    private static final Actor ADMIN = new Actor(
        "TENANT_A", ISSUER, "policy-admin", "admin");

    private static ResourceKey doc(String tenant, long id) {
        return new ResourceKey(tenant, "Document", id);
    }

    private static SubjectKey subject(Actor actor) {
        return new SubjectKey(
            actor.tenant(), actor.issuer(), actor.subject());
    }

    public static class TestClock extends Clock {
        private final AtomicReference<Instant> current =
            new AtomicReference<>(Instant.parse(
                "2030-01-01T00:00:00Z"));

        @Override
        public ZoneId getZone() {
            return ZoneOffset.UTC;
        }

        @Override
        public Clock withZone(ZoneId zone) {
            if (!ZoneOffset.UTC.equals(zone)) {
                throw new IllegalArgumentException(
                    "Demo supports only UTC");
            }
            return this;
        }

        @Override
        public Instant instant() {
            return current.get();
        }

        void reset() {
            current.set(Instant.parse(
                "2030-01-01T00:00:00Z"));
        }

        void advance(Duration duration) {
            current.updateAndGet(t -> t.plus(duration));
        }
    }

    public static class Documents {
        private final Map<ResourceKey, String> bodies =
            new ConcurrentHashMap<>();

        void reset() {
            bodies.clear();
            bodies.put(doc("TENANT_A", 42), "A private 42");
            bodies.put(doc("TENANT_B", 42), "B private 42");
            bodies.put(doc("TENANT_A", 43), "A document 43");
        }

        Optional<String> read(ResourceKey resource) {
            return Optional.ofNullable(bodies.get(resource));
        }

        void write(ResourceKey resource, String newBody) {
            if (!bodies.containsKey(resource)) {
                throw new AccessDeniedException("Not visible");
            }
            bodies.put(resource, newBody);
        }
    }

    public static class RuleStore {
        private final Documents documents;
        private final Map<GrantKey, Boolean> grants =
            new ConcurrentHashMap<>();
        private final Map<ResourceKey, AtomicLong> revisions =
            new ConcurrentHashMap<>();
        private final AtomicInteger evaluations =
            new AtomicInteger();
        private final AtomicBoolean available =
            new AtomicBoolean(true);

        RuleStore(Documents documents) {
            this.documents = documents;
        }

        void reset() {
            grants.clear();
            revisions.clear();
            evaluations.set(0);
            available.set(true);
            grant(doc("TENANT_A", 42), subject(ALICE), "READ");
            grant(doc("TENANT_B", 42), subject(BOB), "READ");
            grant(doc("TENANT_A", 43), subject(ALICE), "READ");
        }

        long revision(ResourceKey key) {
            AtomicLong current = revisions.get(key);
            return current == null ? 0L : current.get();
        }

        private void bump(ResourceKey resource) {
            revisions.computeIfAbsent(
                resource, ignored -> new AtomicLong()
            ).incrementAndGet();
        }

        void grant(
                ResourceKey resource, SubjectKey actor,
                String action) {
            grants.put(
                new GrantKey(resource, actor, action),
                Boolean.TRUE);
            bump(resource);
        }

        void revoke(
                ResourceKey resource, SubjectKey actor,
                String action) {
            grants.remove(new GrantKey(resource, actor, action));
            bump(resource);
        }

        boolean evaluate(
                ResourceKey resource, SubjectKey actor,
                String action) {
            evaluations.incrementAndGet();
            if (!available.get()) {
                throw new IllegalStateException(
                    "Policy source unavailable");
            }
            return documents.read(resource).isPresent()
                && Boolean.TRUE.equals(grants.get(
                    new GrantKey(resource, actor, action)));
        }

        int evaluations() {
            return evaluations.get();
        }

        boolean isAvailable() {
            return available.get();
        }

        void setAvailable(boolean state) {
            available.set(state);
        }
    }

    public static class DecisionCache {
        private static final Duration ALLOW_TTL =
            Duration.ofSeconds(5);
        private static final Duration DENY_TTL =
            Duration.ofSeconds(2);
        private static final int MAX_ENTRIES = 1000;

        private final TestClock clock;
        private final Map<DecisionKey, Entry> entries =
            new ConcurrentHashMap<>();
        private final AtomicInteger hits = new AtomicInteger();
        private final AtomicInteger misses = new AtomicInteger();

        DecisionCache(TestClock clock) {
            this.clock = clock;
        }

        boolean decide(
                DecisionKey key, Supplier<Boolean> loader) {
            Instant now = clock.instant();
            Entry entry = entries.get(key);

            if (entry != null && now.isBefore(entry.expiresAt())) {
                hits.incrementAndGet();
                return entry.allowed();
            }

            misses.incrementAndGet();
            // If loader throws, never cache ALLOW.
            boolean allowed = loader.get();
            Duration ttl = allowed ? ALLOW_TTL : DENY_TTL;

            // Coarse bound for the demo; production uses an LRU/size-bounded cache
            // like Caffeine, avoiding full clear under high load.
            if (entries.size() >= MAX_ENTRIES) {
                entries.clear();
            }

            entries.put(
                key, new Entry(allowed, clock.instant().plus(ttl)));
            return allowed;
        }

        void invalidateResource(ResourceKey resource) {
            entries.keySet().removeIf(
                k -> k.resource().equals(resource));
        }

        void invalidateSubject(SubjectKey actor) {
            entries.keySet().removeIf(
                k -> k.actor().equals(actor));
        }

        void reset() {
            entries.clear();
            hits.set(0);
            misses.set(0);
        }

        int hits() { return hits.get(); }
        int misses() { return misses.get(); }
        int size() { return entries.size(); }
    }

    public static class DecisionPolicy {
        private final RuleStore rules;
        private final DecisionCache cache;

        DecisionPolicy(RuleStore rules, DecisionCache cache) {
            this.rules = rules;
            this.cache = cache;
        }

        private Actor trusted(Authentication authentication) {
            if (authentication == null
                || !authentication.isAuthenticated()
                || !(authentication.getPrincipal() instanceof Actor a)
                || a.tenant() == null || a.tenant().isBlank()
                || a.issuer() == null || a.issuer().isBlank()
                || a.subject() == null || a.subject().isBlank()) {
                return null;
            }
            // Test only simulates an already-verified authentication
            // boundary; production must verify JWT/issuer/membership.
            return a;
        }

        public boolean can(
                Authentication authentication, long id,
                String action) {
            Actor actor = trusted(authentication);

            if (actor == null || !rules.isAvailable()) {
                // Fail closed even when a cache entry exists:
                // demo uses an immediate in-JVM availability flag.
                return false;
            }

            ResourceKey resource = doc(actor.tenant(), id);
            SubjectKey who = subject(actor);
            DecisionKey key = new DecisionKey(
                resource, who, action, rules.revision(resource));

            try {
                return cache.decide(key,
                    () -> rules.evaluate(resource, who, action));
            } catch (IllegalStateException policyUnavailable) {
                return false;
            }
        }
    }

    public static class Probe {
        private final Map<String, AtomicInteger> calls =
            new ConcurrentHashMap<>();

        void mark(String action) {
            calls.computeIfAbsent(
                action, ignored -> new AtomicInteger()
            ).incrementAndGet();
        }

        int count(String action) {
            AtomicInteger value = calls.get(action);
            return value == null ? 0 : value.get();
        }

        void reset() {
            calls.clear();
        }
    }

    public static class ProtectedDocuments {
        private final Documents documents;
        private final Probe probe;

        ProtectedDocuments(Documents documents, Probe probe) {
            this.documents = documents;
            this.probe = probe;
        }

        private Actor actor() {
            Authentication authentication =
                SecurityContextHolder.getContext()
                    .getAuthentication();
            if (authentication == null
                || !(authentication.getPrincipal() instanceof Actor a)) {
                throw new AccessDeniedException(
                    "Trusted principal required");
            }
            return a;
        }

        @PreAuthorize(
            "hasAuthority('DOC_READ') and " +
            "@decisionPolicy.can(authentication, #id, 'READ')"
        )
        public String read(@P("id") long id) {
            probe.mark("READ");
            Actor a = actor();
            return documents.read(doc(a.tenant(), id))
                .orElseThrow(() ->
                    new AccessDeniedException("Not visible"));
        }

        @PreAuthorize(
            "hasAuthority('DOC_WRITE') and " +
            "@decisionPolicy.can(authentication, #id, 'WRITE')"
        )
        public void write(
                @P("id") long id, String newBody) {
            probe.mark("WRITE");
            Actor a = actor();
            documents.write(
                doc(a.tenant(), id), newBody);
        }
    }

    public static class PermissionAdmin {
        private final RuleStore rules;
        private final DecisionCache cache;

        PermissionAdmin(
                RuleStore rules, DecisionCache cache) {
            this.rules = rules;
            this.cache = cache;
        }

        @PreAuthorize("hasAuthority('POLICY_ADMIN')")
        public void revoke(
                String tenant, long id, Actor target,
                String action) {
            requireSameTenant(tenant, target);
            ResourceKey key = doc(tenant, id);
            rules.revoke(key, subject(target), action);
            cache.invalidateResource(key);
        }

        @PreAuthorize("hasAuthority('POLICY_ADMIN')")
        public void grant(
                String tenant, long id, Actor target,
                String action) {
            requireSameTenant(tenant, target);
            ResourceKey key = doc(tenant, id);
            rules.grant(key, subject(target), action);
            cache.invalidateResource(key);
        }

        @PreAuthorize("hasAuthority('POLICY_ADMIN')")
        public void invalidateActor(Actor target) {
            cache.invalidateSubject(subject(target));
        }

        private void requireSameTenant(
                String tenant, Actor target) {
            if (target == null
                || !tenant.equals(target.tenant())) {
                throw new IllegalArgumentException(
                    "Cross-tenant policy mutation");
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableMethodSecurity
    public static class Config {

        @Bean TestClock clock() {
            return new TestClock();
        }

        @Bean Documents documents() {
            return new Documents();
        }

        @Bean RuleStore ruleStore(Documents documents) {
            return new RuleStore(documents);
        }

        @Bean DecisionCache decisionCache(TestClock clock) {
            return new DecisionCache(clock);
        }

        @Bean("decisionPolicy")
        DecisionPolicy decisionPolicy(
                RuleStore rules, DecisionCache cache) {
            return new DecisionPolicy(rules, cache);
        }

        @Bean Probe probe() {
            return new Probe();
        }

        @Bean ProtectedDocuments protectedDocuments(
                Documents documents, Probe probe) {
            return new ProtectedDocuments(documents, probe);
        }

        @Bean PermissionAdmin permissionAdmin(
                RuleStore rules, DecisionCache cache) {
            return new PermissionAdmin(rules, cache);
        }
    }

    @Autowired TestClock clock;
    @Autowired Documents documentsData;
    @Autowired RuleStore rules;
    @Autowired DecisionCache cache;
    @Autowired ProtectedDocuments protectedDocs;
    @Autowired PermissionAdmin admin;
    @Autowired Probe probe;

    private void as(Actor actor, String... authorities) {
        SecurityContext ctx =
            SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                actor, "test-only",
                AuthorityUtils.createAuthorityList(authorities)));
        SecurityContextHolder.setContext(ctx);
    }

    private void asAlice() {
        as(ALICE, "DOC_READ", "DOC_WRITE");
    }

    private void asBob() {
        as(BOB, "DOC_READ", "DOC_WRITE");
    }

    private void asAdmin() {
        as(ADMIN, "POLICY_ADMIN");
    }

    @BeforeEach
    void prepare() {
        clock.reset();
        documentsData.reset();
        rules.reset();
        cache.reset();
        probe.reset();
        asAlice();
    }

    @AfterEach
    void cleanup() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void springSecurityActuallyProxiesProtectedMethods() {
        assertThat(AopUtils.isAopProxy(protectedDocs)).isTrue();
        assertThat(AopUtils.isAopProxy(admin)).isTrue();
    }

    @Test
    void firstAllowMissThenSecondAllowHitsCache() {
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        assertThat(rules.evaluations()).isEqualTo(1);
        assertThat(cache.misses()).isEqualTo(1);
        assertThat(cache.hits()).isEqualTo(1);
    }

    @Test
    void allowCacheExpiresAfterFiveSeconds() {
        protectedDocs.read(42L);
        clock.advance(Duration.ofSeconds(4));
        protectedDocs.read(42L);
        assertThat(rules.evaluations()).isEqualTo(1);

        clock.advance(Duration.ofSeconds(1));
        protectedDocs.read(42L);
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void denyDecisionCanBeCachedWithoutRunningMethodBody() {
        as(IMPOSTOR, "DOC_READ");
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(1);
        assertThat(cache.hits()).isEqualTo(1);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void denyEntryExpiresAtTwoSeconds() {
        as(IMPOSTOR, "DOC_READ");
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);

        clock.advance(Duration.ofSeconds(2));
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void revokeInvalidatesPreviouslyCachedAllow() {
        protectedDocs.read(42L);

        asAdmin();
        admin.revoke("TENANT_A", 42L, ALICE, "READ");
        asAlice();

        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(2);
        assertThat(probe.count("READ")).isEqualTo(1);
    }

    @Test
    void grantInvalidatesPreviouslyCachedDeny() {
        as(IMPOSTOR, "DOC_READ");
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);

        asAdmin();
        admin.grant("TENANT_A", 42L, IMPOSTOR, "READ");
        as(IMPOSTOR, "DOC_READ");

        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void resourceRevisionProtectsAgainstMissedLocalEviction() {
        protectedDocs.read(42L);
        assertThat(cache.size()).isEqualTo(1);

        // Test simulates a lost eviction event within the SAME JVM.
        // Not an allowed production mutation path.
        rules.revoke(
            doc("TENANT_A", 42L), subject(ALICE), "READ");

        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void sameResourceIdAndUsernameInOtherTenantHasOwnEntry() {
        assertThat(ALICE.getName()).isEqualTo("alex");
        assertThat(BOB.getName()).isEqualTo("alex");

        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        asBob();
        assertThat(protectedDocs.read(42L))
            .isEqualTo("B private 42");
        assertThat(rules.evaluations()).isEqualTo(2);

        asAlice();
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        assertThat(cache.hits()).isEqualTo(1);
    }

    @Test
    void sameUsernameDifferentSubjectDoesNotReuseAllow() {
        protectedDocs.read(42L);
        as(IMPOSTOR, "DOC_READ");
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void readGrantDoesNotBecomeWriteGrant() {
        protectedDocs.read(42L);
        assertThatThrownBy(() ->
            protectedDocs.write(42L, "Tampered"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(documentsData.read(
            doc("TENANT_A", 42L))).contains("A private 42");
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void newlyGrantedWriteWorksOnlyForItsTenant() {
        asAdmin();
        admin.grant("TENANT_A", 42L, ALICE, "WRITE");
        asAlice();

        protectedDocs.write(42L, "A edited");
        assertThat(documentsData.read(
            doc("TENANT_A", 42L))).contains("A edited");
        assertThat(documentsData.read(
            doc("TENANT_B", 42L))).contains("B private 42");
        assertThat(probe.count("WRITE")).isEqualTo(1);
    }

    @Test
    void resourceEvictionDoesNotClearUnrelatedResource() {
        protectedDocs.read(42L);
        protectedDocs.read(43L);
        assertThat(rules.evaluations()).isEqualTo(2);

        asAdmin();
        admin.revoke("TENANT_A", 42L, ALICE, "READ");
        asAlice();
        assertThat(protectedDocs.read(43L))
            .isEqualTo("A document 43");
        assertThat(rules.evaluations()).isEqualTo(2);
    }

    @Test
    void invalidatingSubjectForcesItsEntriesToReevaluate() {
        protectedDocs.read(42L);
        protectedDocs.read(43L);
        assertThat(rules.evaluations()).isEqualTo(2);

        asAdmin();
        admin.invalidateActor(ALICE);
        asAlice();

        protectedDocs.read(42L);
        protectedDocs.read(43L);
        assertThat(rules.evaluations()).isEqualTo(4);
    }

    @Test
    void ordinaryUserCannotRevokeSomebodyElse() {
        long before = rules.revision(doc("TENANT_A", 42L));
        assertThatThrownBy(() ->
            admin.revoke("TENANT_A", 42L, ALICE, "READ"))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.revision(
            doc("TENANT_A", 42L))).isEqualTo(before);
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
    }

    @Test
    void policyAdminCannotMutateAnotherTenantTargetByMistake() {
        asAdmin();
        assertThatThrownBy(() ->
            admin.grant("TENANT_A", 42L, BOB, "READ"))
            .isInstanceOf(IllegalArgumentException.class);
        assertThat(rules.revision(
            doc("TENANT_A", 42L))).isEqualTo(1L);
    }

    @Test
    void missingFunctionAuthorityStopsBeforeCacheLookup() {
        as(ALICE, "DOC_WRITE");
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isZero();
        assertThat(cache.misses()).isZero();
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void untrustedStringPrincipalCannotUseOtherUsersCache() {
        protectedDocs.read(42L);
        SecurityContext ctx =
            SecurityContextHolder.createEmptyContext();
        ctx.setAuthentication(
            new UsernamePasswordAuthenticationToken(
                "alex", "test-only",
                AuthorityUtils.createAuthorityList("DOC_READ")));
        SecurityContextHolder.setContext(ctx);

        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(1);
    }

    @Test
    void unknownResourceIsDeniedAndMayBeCachedBriefly() {
        assertThatThrownBy(() -> protectedDocs.read(999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThatThrownBy(() -> protectedDocs.read(999L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(rules.evaluations()).isEqualTo(1);
        assertThat(probe.count("READ")).isZero();
    }

    @Test
    void policySourceOutageBlocksEvenCachedAllowInDemo() {
        protectedDocs.read(42L);
        rules.setAvailable(false);

        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
        assertThat(probe.count("READ")).isEqualTo(1);
        rules.setAvailable(true);
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
    }

    @Test
    void revokingBDoesNotChangeACachedDecision() {
        protectedDocs.read(42L);
        asBob();
        protectedDocs.read(42L);
        assertThat(rules.evaluations()).isEqualTo(2);

        asAdmin();
        admin.revoke("TENANT_B", 42L, BOB, "READ");
        asAlice();
        assertThat(protectedDocs.read(42L))
            .isEqualTo("A private 42");
        assertThat(rules.evaluations()).isEqualTo(2);

        asBob();
        assertThatThrownBy(() -> protectedDocs.read(42L))
            .isInstanceOf(AccessDeniedException.class);
    }

    @Test
    void cacheDoesNotKeepAnAllowBeyondExactTtlBoundary() {
        protectedDocs.read(42L);
        clock.advance(Duration.ofMillis(4999));
        protectedDocs.read(42L);
        assertThat(rules.evaluations()).isEqualTo(1);

        clock.advance(Duration.ofMillis(1));
        protectedDocs.read(42L);
        assertThat(rules.evaluations()).isEqualTo(2);
    }
}
```

### 8.3. What roles do the classes in the project play?

| Class / record | Role |
| --- | --- |
| `Actor` / `SubjectKey` | Separates display username from tenant+issuer+subject |
| `ResourceKey` | Distinguishes Document#42 of tenant A and B |
| `DecisionKey` | Holds resource, actor, action, and revision |
| `RuleStore` | Simulated policy source, counts evaluations and bumps revision on grant/revoke |
| `DecisionCache` | TTL-based Boolean cache; evicts by resource or actor; counts hits/misses |
| `DecisionPolicy` | Bridges `Authentication` to policy+cache; fails closed on invalid principals/sources |
| `ProtectedDocuments` | Two READ/WRITE methods guarded by `@PreAuthorize` via Spring proxy |
| `PermissionAdmin` | Grant/revoke paths guarded by `POLICY_ADMIN`, bumps revision and evicts |
| `TestClock` | Controllable UTC clock, tests TTL without real-time waiting |
| `Probe` | Proves the method body never executes when denied |

### 8.4. Running and expected results

In the `decision-cache-demo` directory:

```bash
gradle test --tests demo.DecisionCacheSecurityTest
```

If using Gradle Wrapper: use `./gradlew test --tests demo.DecisionCacheSecurityTest` on Linux/macOS or `gradlew.bat test --tests demo.DecisionCacheSecurityTest` on Windows.

**Expected:** **22 JUnit tests** pass and Gradle reports `BUILD SUCCESSFUL`. This is **predicted from reading the sample code**, not a collected execution log. HTML report: `build/reports/tests/test/index.html`.

| Test group | Result to prove |
| --- | --- |
| Spring proxy | Method Security genuinely active |
| Cache hit / TTL ALLOW | Second call skips RuleStore; after 5s it recomputes |
| Cache hit / TTL DENY | DENY can cache for 2s while body never executes |
| Revoke | Cached ALLOW is invalidated after permission change |
| Grant | Cached DENY does not block new permission after invalidation |
| Missed eviction same JVM | Incremented revision creates a new key; stale ALLOW is not reused |
| Tenant and subject | Same ID/username does not share decisions across actors |
| Action READ vs WRITE | READ grant does not imply WRITE grant |
| Resource/subject eviction | Only matching scope is recomputed |
| Admin policy | Actor without `POLICY_ADMIN` cannot alter permissions |
| Missing authority/principal | Cannot borrow cached ALLOW |
| Unknown resource | Fails closed with short-lived DENY |
| Source unavailable | In-JVM outage flag denies before cache |
| Exact TTL boundary | Must miss exactly at `expiresAt` |

**Understand the test limitations:** the clock and policy revisions reside within one process. The missed-eviction test is meaningful only when **the revision on that same node changed**. It does **not** prove another node has the new revision, nor linearizability between an in-flight request and a newly committed revocation.

## 9. Production deployment with Spring Cache, Caffeine, or Redis

### 9.1. Caffeine for single-JVM caching

With Caffeine, a typical config caps size and TTL:

```java
// Illustrative fragment; add com.github.ben-manes.caffeine:caffeine dependency.
com.github.benmanes.caffeine.cache.Cache<DecisionKey, Boolean> cache =
    com.github.benmanes.caffeine.cache.Caffeine.newBuilder()
        .maximumSize(50_000)
        .expireAfterWrite(java.time.Duration.ofSeconds(5))
        .recordStats()
        .build();

// Fetch from policy source on miss:
Boolean allowed = cache.get(key, k -> policyStore.evaluate(k));
```

`DecisionKey`/`policyStore` must be defined by the application as earlier; this snippet is **not a standalone program**. This sets one shared TTL across all entries, whereas the demo used different TTLs for ALLOW/DENY. If per-outcome TTL is required, implement a custom `Expiry` and test accurately; do not claim `expireAfterWrite` natively supports distinct Boolean TTLs.

With Spring Cache, `@Cacheable` and `@CacheEvict` help, yet you must control **keys, method-security advisor ordering, transaction boundaries, proxy self-invocation, and permission versions**. Never replace `@PreAuthorize` directly with `@Cacheable`.

### 9.2. Redis/distributed cache

A shared Redis cache reduces divergence across nodes, yet **does not guarantee instant revocation on its own**:

- Pub/Sub messages can be dropped while subscribers are offline; streams/outboxes with replay and versions are stronger.
- Cache writes, DB commits, and event publishes are not atomic by default.
- Multi-region setups have replication lag; TTLs and propagation SLAs must be defined.
- Redis eviction policies/memory pressure can cause hit rates to fluctuate.
- Keys need clear tenant/resource/action/policy namespacing; policy changes must keep versions and invalidations consistent.
- Mind sensitive data in cache keys/logs: use hashed/opaque IDs where appropriate, plus TLS and auth for Redis.

An architecture for **strong revocation** can store a `revocationEpoch` in an authoritative store and check the current epoch before accepting a cached ALLOW. If the epoch lookup itself is cached per node with a long TTL, stale permissions remain unsolved. High-impact actions may require **skipping ALLOW caches** or re-evaluating inside the transaction at execution time.

### 9.3. Mismatched invalidation between ACL and decision caches

When permissions come from Spring Security ACLs, changing an ACE via `MutableAclService.updateAcl` can invalidate the implementation's `AclCache`. However, an external Boolean decision cache **does not automatically learn** about that update. Wire ACL change events to both cache layers, accounting for **parent ACLs, descendants, group memberships**, and effective permissions.

## 10. Sensitive scenarios and race conditions

### 10.1. TOCTOU: checking permissions at a different time than execution

```text
t0  Request A: cached ALLOW for Document#42
t1  Admin: revoke READ
t2  Request A: enters method body and returns data
t3  Other nodes receive invalidation event
```

Even with eviction at t1, a request that already passed the gate can still finish. For simple reads, define acceptable staleness. For deletions, approvals, or financial transactions, enforce **condition checks inside transactions/conditional SQL** or controlled concurrency strategies—not just a cache gate.

### 10.2. Cache stampede and concurrent loaders

When 10,000 requests hit TTL expiration together, all could call the PDP simultaneously. In the demo, simple `ConcurrentHashMap` + `get`/`put` allows multiple loaders to run concurrently; production uses proper loader coalescing/atomic cache loading, load limits, and avoids turning a cache stampede into an outage.

### 10.3. Policy store outage

If the PDP/database is unavailable, a cached ALLOW **can still be served** up to its TTL unless the app checks an updated health/revocation gate. The demo deliberately checks `RuleStore.isAvailable()` before the cache to model in-JVM fail-closed, yet **a local health flag does not prove network-wide fail-closed**. For high-risk data, never use "stale-while-revalidate" for authorization unless approved by your threat model.

### 10.4. JWT revocation and role changes

If `hasAuthority('DOC_READ')` reads authorities from a validly signed JWT with a long lifetime, revoking a role in the DB does not strip authorities from existing tokens. Evicting a decision cache cannot fix already-issued JWTs. You may need short token lifetimes, introspection, authz/version checks, session revocation, or policy epochs; test the entire path, not just `DecisionCache`.

### 10.5. Batch/list/export

Caching a READ decision for `Document#42` does not mean the user may export every Document in the tenant. Each resource and action needs its own policy; `READ` does not imply `EXPORT`. For large lists, cache only appropriate parts and push tenant/row filtering into repositories/SQL; avoid N+1 PDP queries and `@PostFilter` distorting pagination.

## 11. Observability and SLOs for authorization caching

| Metric / signal | Meaning |
| --- | --- |
| `authz_decision_cache_hit_total` / miss | Reuse rate / PDP evaluation cost |
| `authz_decision_cache_entries` | Size and key cardinality |
| `authz_decision_cache_evictions_total` | Invalidations and capacity evictions |
| `authz_policy_evaluation_seconds` | PDP/DB latency on misses |
| `authz_policy_revision` | Which version is active per node |
| `authz_invalidation_delivery_lag_seconds` | Lag from commit to node receiving event |
| `authz_invalidation_errors_total` | Failed events, high staleness risk |
| `authz_revocation_stale_allow_total` | Tests/canaries detecting ALLOW after revocation |
| `authz_policy_source_unavailable_total` | Tracks permission source errors and fail-closed behavior |

Avoid putting **raw tokens, usernames/emails, or document contents** into metric labels due to cardinality and data leaks. When debugging, log correlation IDs, hashed/opaque principal IDs, log-safe resource types/tenants, policy revisions, cache hits/misses, and decisions (per audit policy).

**Illustrative SLO to agree upon:** "99.9% of revoke events reach every node within 1 second; max stale ALLOW is 5 seconds when events are lost." This is purely an example target; if the product SLA requires **strictly immediate revocation**, a stronger architecture than TTL/eventual invalidation is needed.

## 12. Common pitfalls and fixes

| Symptom | Likely cause | Check |
| --- | --- | --- |
| Revoked user can still read | ALLOW entry still within TTL, delayed/lost event, node lacks new revision | Audit commit→event→evict; test post-revoke across multiple nodes |
| User has READ yet WRITE also succeeds | Key missing action | Separate READ/WRITE/EXPORT |
| Tenant B gets A's cached ALLOW | Key missing tenant or resource type | Test shared ID 42 across A/B |
| Two users with same username share cache | Key uses only `authentication.getName()` | Test distinct issuer/sub |
| New grant remains DENIED for too long | DENY cache TTL too long or missing invalidation | Short DENY TTL + grant invalidation |
| Revoke does not affect Spring ACL cache | Only evicted Boolean decision cache | Invalidate ACL objects/parent dependencies properly |
| Node A works while B fails | Invalidation events/revisions not broadcast | Multi-instance tests, outbox/streams, health/version |
| Memory grows continuously | No max size, overly fragmented keys | Bounded cache, size metrics, policy key audits |
| PDP suffers load spikes after TTL | Cache stampede | Single-flight/coalescing, jitter, rate limits |
| Method-security denial missing | Missing `@EnableMethodSecurity`, self-invocation, `new` instantiation | Test Spring proxy, `Probe` |
| Policy source fails yet still ALLOWs | Using cached ALLOW during outage | Risk-appropriate fail-closed gate, authoritative checks |
| Wrong data returned despite right decision cache | Payload/repository cache lacks tenant scope | Separate decision caches from data caches |
| Role revoked yet token keeps authority | JWT/session cache not refreshed | Token/version/introspection/revocation tests |
| Cache slow/ineffective | TTL too short, overly broad invalidation, high-cardinality keys | Hit/miss P95, group by policy, tune within risk bounds |

### Minimal diagnostic procedure

1. Check **verified principal**, tenant, issuer/sub, authorities, and target resource.
2. Print/inspect **structured cache key** (never log tokens), action, and revision.
3. Re-test evaluation **bypassing the cache** on the same authoritative data.
4. Compare cache entry against `expiresAt`; test at the exact TTL boundary.
5. Verify the permission-updating transaction actually **COMMITTED**.
6. Check whether invalidation events were emitted and processed with the right revision on each node.
7. Check whether other role/session/JWT/ACL caches still hold old permissions.
8. Verify denied requests stop **before the body**, with zero side effects.
9. Verify SQL/repositories and data caches never leak another tenant's resources.

## 13. Pre-production checklist

- [ ] Cache keys include actor tenant + stable identity, resource type/tenant/ID, action, and revision/affecting attributes.
- [ ] Never use display usernames, local IDs, or coarse `hasAuthority` caches as global identities.
- [ ] Risk-appropriate TTLs for ALLOW/DENY; DENY TTL does not keep users blocked too long after grants.
- [ ] Max size, metrics, and single-flight/rate limiting for loaders under heavy load.
- [ ] Post-commit invalidation for grant/revoke/owner/parent/role/membership/policy changes.
- [ ] Distributed events support retries/replays/versions and lag monitoring; lost/duplicate/out-of-order events tested.
- [ ] Policy source outages handled per fail-closed policy; never reuse stale ALLOWs for high-risk actions.
- [ ] `@PreAuthorize` tested via Spring proxies without self-invocation bypasses.
- [ ] READ/WRITE/EXPORT separated by action; tenant/resource checks enforced even on cache hits.
- [ ] Tests cover revoke after cached ALLOW, grant after cached DENY, exact TTL boundaries, 2 tenants sharing an ID, and 2 subjects sharing a username.
- [ ] Multi-node, JWT/session revocation, other caches (ACL/document), and TOCTOU tested.
- [ ] For sensitive side effects, re-verify conditions at write time under transactions/conditional SQL.
- [ ] Audit actor/resource/revision and define clear targets for maximum stale authorization.

## 14. Exercises

1. **Wrong TTL:** change ALLOW TTL to 15 minutes and remove invalidation. Determine the maximum stale ALLOW window and why the design is unsafe under a 1-second revocation SLA.
2. **Wrong cache key:** remove tenant from `ResourceKey` or use username `alex` instead of issuer/sub. Write a test with two tenants sharing ID 42 and confirm the cache collision.
3. **Action:** add `APPROVE` or `EXPORT`, ensuring a READ grant never produces an ALLOW entry for the new action.
4. **Group membership:** add a REVIEWER group and `roleRevision`. When Alice leaves the group, invalidation by subject must purge all decisions relying on that group; old tokens must also be handled.
5. **Caffeine:** replace the map with a cache using `maximumSize`, `expireAfterWrite`, and `recordStats`; test TTL with a fake ticker instead of real sleeping.
6. **Transactions:** add an H2/PostgreSQL database and an outbox row on revoke; emit events only after commit. Test rollback and verify the cache stays consistent with real data.
7. **Multiple nodes:** run two instances with separate caches. Revoke on A, simulate node B dropping the event; observe TTL and revision refresh behavior.
8. **TOCTOU:** add a `write` updating DB under optimistic versioning. Revoke between precheck and commit; propose how to block the side effect using authoritative policy.
9. **Outage:** simulate an unresponsive PDP and verify no new ALLOWs occur; analyze existing cached ALLOWs and decide fail-closed behavior per action.
10. **Parent ACL:** modify a parent ACE and test invalidation across all inheriting descendants, not only the parent ACL.

## 15. Summary

Authorization decision caching pursues two **simultaneous** goals: cutting policy evaluation cost and **never reusing stale permissions beyond risk bounds**. TTL only caps lifetime; when ACLs/roles/policies change, invalidate and/or bump to a new **policy revision**. In distributed systems, propagate changes or verify revisions from trusted sources—otherwise another node will keep returning cached `ALLOW`.

The essence of a cache key is **"who + in which tenant + wants to do what + on which resource + under which permission version"**. Spring Security `@PreAuthorize` still checks authorities per invocation; caching only optimizes the policy evaluation portion deemed safe to store temporarily. High-consequence actions require stronger transaction/re-check guards than cache TTLs alone.

## Official references

- Spring Security 6.5 — Method Security, `@EnableMethodSecurity`, custom beans in `@PreAuthorize`: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Framework — Cache Abstraction and cache annotations: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Caffeine Wiki — Eviction, size & expiration: https://github.com/ben-manes/caffeine/wiki/Eviction
- Caffeine Wiki — Population, `Cache.get(key, loader)`: https://github.com/ben-manes/caffeine/wiki/Population
- Spring Security — Domain Object Security ACLs and ACL cache: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/acls.html
- OWASP API1:2023 — Broken Object Level Authorization: https://owasp.org/API-Security/editions/2023/en/0xa1-broken-object-level-authorization/
