# Caching Permissions, Relationships, and Decisions Within the Proper Scope

## 1. The Problem: Fast Caching Must Preserve Security Context

In Spring Security, the decision "is user U allowed to perform action A on resource R in tenant T?" often requires reading the authenticated identity, roles/permissions, memberships, ownership, ACLs, resource attributes, and business rules. Repeated evaluation can generate many queries, increasing latency and database load. Caching avoids redundant work, yet an `ALLOW` or `DENY` result **is only meaningful within the scope and point in time in which it was computed**.

A critical failure example: Alice is allowed to read document `doc-7` and the system caches `true` keyed only by `doc-7`. When Bob requests the same ID, the cache returns Alice's `true` even though Bob has no permission. Similarly, tenant B can receive tenant A's result; a `READ` permission can be reused for `DELETE`; or a revoked permission remains effective because an old `ALLOW` entry has not expired yet.

This is an **out-of-context authorization decision reuse** vulnerability. It can cause IDOR/BOLA, cross-tenant access, privilege escalation, post-revocation access, or data exposure through response caches. Even a properly written Spring Security filter or `@PreAuthorize` method becomes ineffective if the caching layer uses the wrong key.

After this lesson, learners should be able to distinguish cache types, design cache scope/keys and lifecycles, handle policy/relationship changes, choose appropriate consistency bounds, and write tests proving permissions are never shared erroneously.

## 2. Three Cache Layers to Distinguish

| Layer | Stored Data | Typical Scope | Common Pitfalls |
| --- | --- | --- | --- |
| **Permission/grant cache** | Permissions, authorities, role mappings, or grants from a verified source | Issuer/subject, tenant, grants revision | Roles or memberships are revoked while stale grants remain in use |
| **Relationship cache** | Ownership, groups, share links, parent–child resource relationships | Tenant, actor, relation type, resource, relation revision | Owner/ACL or permission inheritance path changes without cache awareness |
| **Decision cache** | Final `ALLOW`/`DENY` outcome for an action | Actor, tenant, resource type/id, action, policy and revisions | Mixing results across different users, actions, resources, or points in time |

Permission caching does not automatically authorize an operation: an `EDITOR` role still has to be evaluated against the action and resource. Relationship caching does not automatically grant access either: Alice belonging to group G does not prove G may publish document D. Decision caching is the most dangerous when a key dimension is missing, because it reuses the **final conclusion** without re-running the policy.

Beyond these three layers lies the **response/data cache** (for example `DocumentDto` or HTTP responses). Even with a completely accurate decision cache, a response cache keyed by URL/ID that omits tenant or user can serve **Alice's content to Bob**. You must inspect both data caches and authorization caches, especially at API Gateways, CDNs, reverse proxies, ORMs, and services.

## 3. What Information Does a Decision Depend On?

A decision can be viewed as a function:

```text
allow = policy.evaluate(
    verifiedPrincipal,
    effectiveTenant,
    resourceTypeAndId,
    action,
    currentOwnershipAndRelationships,
    currentResourceAttributes,
    currentGrants,
    policyVersion,
    relevantEnvironment
)
```

Each factor must be understood accurately:

- **Principal:** a trusted identity from SecurityContext after authentication. When using multiple IdPs, `issuer + subject` or a mapped internal user ID avoids `sub` collisions across issuers. With delegation/impersonation, the decision may depend on both the acting user and delegated rights.
- **Tenant:** the effective workspace/organization where the actor's membership/permissions are verified. A client-selected `tenantId` in a URL or header is only a *selector*, not proof of permission.
- **Resource:** `resourceType + resourceId`; identical IDs can exist across multiple resource types or tenants. You must verify the resource actually belongs to the tenant being checked.
- **Action:** read, edit, export, share, transfer ownership, approve, and delete have distinct semantics. A cached `READ` must never be reused for `DELETE`.
- **Attributes/relationships:** owner, status, sensitivity, ACL, groups, inheritance links, membership, delegated rights. Any change can flip the decision.
- **Policy:** the version of RBAC/ABAC/ReBAC rules and role → permission mappings. When deployed logic or policy rules change, caches from the old policy may become invalid.
- **Environment:** current time, MFA freshness window, IP, device trust, access purpose, or risk level if the policy depends on them. For continuously changing conditions, you typically need a TTL bounded to the exact deadline or skip decision caching altogether.

**Safe reuse condition:** two checks may share a decision only when every attribute capable of changing the outcome is equivalent and still valid under the system's contract. Having two requests share the same path or ID is not enough.

## 4. Designing Properly Scoped Cache Keys

### 4.1. Under-Scoped Keys

Unsafe example in Spring Cache:

```java
// BUG ILLUSTRATION: Do not use in a real application.
@Cacheable(cacheNames = "authorizationDecisions", key = "#documentId")
public boolean canOperate(UUID documentId,
                          UUID tenantId,
                          Authentication authentication,
                          String action) {
    return policy.evaluate(authentication, tenantId, documentId, action);
}
```

Even if `policy.evaluate` uses full context on a cache miss, Alice's result can be retrieved by Bob via the same `documentId` key; tenant A's decision can be used for tenant B, or `READ` can be reused for `DELETE`. This is a bug in the **key**, not necessarily in the policy itself.

### 4.2. Keys with Context and Freshness

A key can be modeled as follows:

```text
DecisionKey(
  principalNamespaceOrIssuer,
  stableSubjectId,
  effectiveTenantId,
  resourceType,
  resourceId,
  action,
  grantOrSubjectRevision,
  relationOrMembershipRevision,
  resourceAuthorizationRevision,
  policyRevision,
  relevantEnvironmentFingerprint
)
```

This is an **analytical template**, not a mandate that every system have these exact fields. For truly public resources, some factors may not affect the decision; for complex policies, you may need field-level permissions, project ancestry, delegation, MFA freshness, purpose, time range, or role within the tenant.

Verification requirements:

1. **Actor identity must be verified by the backend.** Never treat client-asserted `role`, `ownerId`, or `subject` as a permission source. If the actor is derived from a JWT, verify signature, issuer, audience, expiry, and resource-server mapping; a validly signed token can still carry outdated permissions.
2. **Tenant is a verified permission scope.** You must verify membership and permissions in the selected tenant, and ensure the resource actually resides in that tenant.
3. **Actions must be clearly distinguished.** Use enums or canonical names. `READ_METADATA` and `READ_PRIVATE_CONTENT` may need separate decisions; `UPDATE` does not mean `PUBLISH`.
4. **Revisions must come from a trusted source.** When owner/ACL/grants change, the corresponding revision must increment. Accepting a client-supplied `policyVersion` in the request does not make the cache safer.
5. **Never put secrets in keys.** Raw access tokens, cookies, passwords, or credentials should not appear in cache keys, logs, or metrics. Use canonical identifiers and trusted versions.
6. **Equality must follow semantics.** Avoid mutable key objects, missing/unstable `equals/hashCode`, or string concatenation that fails to delimit fields unambiguously. A Java `record` with immutable fields is a solid choice.

With multiple tenants and resource namespaces, a key containing only `subject + documentId` is still wrong if document IDs can repeat across tenants or if actions vary.

### 4.3. Versions and Fingerprints Must Represent All Dependencies

Multiple version fields can be replaced with a single `authorizationFingerprint` if the backend builds the fingerprint from **all** permission-affecting attributes, updates it on every relevant change, and readers obtain the current fingerprint with the required consistency. If the fingerprint only reflects roles in an old JWT while the business requires immediate revocation, it will not prevent stale authorization.

Every update path must follow the versioning mechanism: changing owner, membership, groups, ACLs, status, policies, or parent–child links. If a batch job updates an owner without bumping the revision, even a complete cache key can return the wrong decision.

## 5. Caching ALLOW, DENY, and Time Bounds

**Caching ALLOW** carries the risk of unauthorized access after revocation/transfer; **caching DENY** can keep newly granted permissions blocked. You can choose different TTLs or skip caching one of them depending on sensitivity and change frequency. Do not assume DENY is always harmless: timing differences alone can sometimes leak resource existence.

Freshness models often combine:

| Mechanism | What It Gives You | What It Does Not Guarantee |
| --- | --- | --- |
| **Single-request** caching | Eliminates duplicate evaluation, avoids cross-request sharing | Does not handle owner/role changes mid-request automatically |
| Version/revision in key | New requests at a new revision never hit stale decisions | Still wrong if revision comes from a stale source; old keys occupy memory |
| Active evict/invalidate | Shrinks stale window, helpful across multiple nodes | Notifications can be delayed/lost; cache fill after evict can resurrect stale entries |
| Short TTL | Caps maximum entry lifetime | TTL does not guarantee **immediate** revocation |
| Authoritative freshness gate | Can verify current revision/state before reuse | Incurs read/sync cost; must be designed consistently with writes |

You must define the **permission validity contract**: must revocation take effect immediately, or is a bounded delay acceptable? If the product requires immediate effect, a 30–60 second TTL alone is insufficient. For time-dependent policies like a grant expiring at 15:00 or MFA freshness, an entry must not be reused past the deadline even if the default TTL has not elapsed.

When the cache fails, never default to `ALLOW` to shed load. Fallbacks are only allowed per an explicit contract and must still evaluate permissions from a trusted source. If a safe decision cannot be made, return a controlled error or fail closed.

## 6. Spring Security / Spring Cache: Placing Cache at the Right Spot

Spring Cache supports `@Cacheable`, `CacheManager`, Redis/Caffeine adapters, and provider-specific concurrency options. It **does not automatically know** which decisions must be invalidated when membership/owner/role changes. That responsibility belongs to the policy service and permission update flows.

When using method security:

```java
@PreAuthorize("@documentPolicy.canRead(authentication, #tenantId, #documentId)")
public DocumentDto read(UUID tenantId, UUID documentId) {
    return documentService.loadDocument(tenantId, documentId);
}
```

This is an illustrative snippet inside an application with `@EnableMethodSecurity` and a `documentPolicy` bean. `canRead` must extract the actor from the authenticated `Authentication`, verify tenant/resource, and fetch relevant revisions before consulting the cache. Never use `isAuthenticated()` as a sufficient condition for record-level access.

A clear example with Spring Cache; the interfaces `VerifiedActorResolver`, `AuthorizationSnapshotStore`, and `DocumentPermissionEvaluator` are **application-defined components**, not default Spring APIs:

```java
record DecisionKey(
        String issuer, String subject,
        UUID tenantId, String resourceType, UUID resourceId,
        String action, long grantRevision, long relationRevision,
        long resourceRevision, long policyRevision) {}

public boolean canRead(Authentication authentication,
                       UUID tenantId, UUID documentId) {
    VerifiedActor actor = actors.resolve(authentication);
    AuthorizationSnapshot snapshot =
            snapshots.load(actor, tenantId, documentId);

    // Authoritative snapshot, tenant/resource in proper scope.
    if (snapshot == null) {
        return false;
    }

    DecisionKey key = new DecisionKey(
            actor.issuer(), actor.subject(),
            snapshot.tenantId(), "DOCUMENT", documentId, "READ",
            snapshot.grantRevision(), snapshot.relationRevision(),
            snapshot.resourceRevision(), snapshot.policyRevision());

    Boolean cached = cache.get(key, Boolean.class);
    if (cached != null) {
        return cached;
    }

    boolean allowed = evaluator.canRead(actor, snapshot);
    cache.put(key, allowed);
    return allowed;
}
```

`cache` above is a configured `org.springframework.cache.Cache`. When storing `Boolean.FALSE`, checking `cached != null` accurately distinguishes a cached deny from a cache miss. `AuthorizationSnapshot` must come from an authoritative source containing both versions and policy data under **the same consistency contract**. Reading revisions on every hit has a cost: optimizing expensive ACL/graph calculations does not necessarily eliminate every query. Measure in practice before rolling out.

**Important limitations:**

- A version snapshot read before a write can still be altered by another transaction. For sensitive operations, the database must guard permissions at write time using conditional updates/optimistic versioning or appropriate locks/transactions. Decision caching does not replace locks or prevent TOCTOU.
- If the policy depends on other tables, reading only the resource version is **not enough**; you need revisions/freshness for membership, ACLs, or external facts.
- Proxy-based `@Cacheable` may not run on internal `this.method()` self-invocation. Test real hit/miss behavior; never rely on caching to enforce authorization.
- Caching `Authentication` or `SecurityContext` globally risks retaining another request's identity. Pass verified actors/immutable keys into the policy rather than sharing request contexts across users.
- A `tenantId` in a URL or header can be a valid parameter for selecting a tenant; **never** treat it as proof of tenant access.

## 7. Java 17+ Program Demonstrating Unsafe vs. Scoped Caching

The standalone program below uses in-memory structures to illustrate two key designs. It simulates owner and membership with backend-updated versions. This is a **sequential model**; it does not guarantee real database atomicity and is not production code for concurrent writes.

Save as `AuthorizationCacheDemo.java`:

```java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class AuthorizationCacheDemo {
    record Document(String tenant, String id, String owner, long version) {}
    record Key(String issuer, String subject, String tenant,
               String resourceType, String resourceId, String action,
               long resourceVersion, long membershipVersion,
               long policyVersion) {}

    private static final Map<String, Document> DOCUMENTS = new HashMap<>();
    private static final Set<String> MEMBERS = new HashSet<>();
    private static final Map<String, Boolean> BAD = new HashMap<>();
    private static final Map<Key, Boolean> GOOD = new HashMap<>();
    private static long membershipVersion = 1L;
    private static long policyVersion = 1L;

    private static String id(String tenant, String document) {
        return tenant + "|" + document;
    }

    private static boolean evaluate(
            String actor, String tenant, String docId, String action) {
        Document doc = DOCUMENTS.get(id(tenant, docId));
        return "READ".equals(action)
                && doc != null
                && doc.tenant().equals(tenant)
                && doc.owner().equals(actor)
                && MEMBERS.contains(actor + "|" + tenant);
    }

    // Wrong: shares the result across all actors and tenants with the same docId.
    static boolean unsafe(
            String actor, String tenant, String docId, String action) {
        return BAD.computeIfAbsent(docId,
                key -> evaluate(actor, tenant, docId, action));
    }

    static boolean scoped(
            String actor, String tenant, String docId, String action) {
        Document doc = DOCUMENTS.get(id(tenant, docId));
        long version = doc == null ? 0L : doc.version();
        Key key = new Key("trusted-idp", actor, tenant, "DOCUMENT",
                docId, action, version, membershipVersion, policyVersion);
        return GOOD.computeIfAbsent(key,
                ignored -> evaluate(actor, tenant, docId, action));
    }

    static void transfer(String tenant, String docId, String newOwner) {
        String key = id(tenant, docId);
        Document doc = DOCUMENTS.get(key);
        DOCUMENTS.put(key,
                new Document(tenant, docId, newOwner, doc.version() + 1));
    }

    static void revoke(String actor, String tenant) {
        MEMBERS.remove(actor + "|" + tenant);
        membershipVersion++;
    }

    public static void main(String[] args) {
        DOCUMENTS.put(id("t1", "d7"),
                new Document("t1", "d7", "alice", 1L));
        DOCUMENTS.put(id("t2", "d7"),
                new Document("t2", "d7", "bob", 1L));
        MEMBERS.add("alice|t1");
        MEMBERS.add("bob|t1");
        MEMBERS.add("bob|t2");

        System.out.println("Alice unsafe: "
                + unsafe("alice", "t1", "d7", "READ"));
        System.out.println("Bob unsafe: "
                + unsafe("bob", "t1", "d7", "READ"));
        System.out.println("Bob scoped before transfer: "
                + scoped("bob", "t1", "d7", "READ"));
        System.out.println("Alice scoped before transfer: "
                + scoped("alice", "t1", "d7", "READ"));
        System.out.println("Alice in tenant t2: "
                + scoped("alice", "t2", "d7", "READ"));

        transfer("t1", "d7", "bob");
        System.out.println("Alice scoped after transfer: "
                + scoped("alice", "t1", "d7", "READ"));
        System.out.println("Bob scoped after transfer: "
                + scoped("bob", "t1", "d7", "READ"));

        revoke("bob", "t1");
        System.out.println("Bob scoped after revoke: "
                + scoped("bob", "t1", "d7", "READ"));
    }
}
```

Compile and run on JDK 17 or higher:

```bash
javac AuthorizationCacheDemo.java
java AuthorizationCacheDemo
```

Stdout:

```text
Alice unsafe: true
Bob unsafe: true
Bob scoped before transfer: false
Alice scoped before transfer: true
Alice in tenant t2: false
Alice scoped after transfer: false
Bob scoped after transfer: true
Bob scoped after revoke: false
```

Alice populated `ALLOW` in the unsafe cache, causing Bob to receive `true` by mistake. With a key containing actor/tenant/action/version, Bob is blocked before the ownership transfer while Alice is allowed. Transferring ownership to version 2 blocks Alice and allows Bob; revoking membership bumps the revision and removes Bob's access. Document `d7` in tenant `t2` is not mixed with tenant `t1`.

In a real application, revisions need a trusted source and must be updated consistently across all permission-change paths. Using a global `membershipVersion` variable is purely illustrative; per-tenant/subject/relation versions can avoid unnecessary hit-rate drops. Concurrent read/modify/write flows still need database mechanisms to protect invariants.

## 8. Invalidation After Permission Changes: Designing the Lifecycle

For each policy, build a **dependency map**: which inputs can flip a decision, and which update events must invalidate dependent entries.

| Change | Cache Consequence |
| --- | --- |
| Revoke role/grant | Increment subject/tenant grant revision or invalidate affected decisions |
| Add/remove membership | Increment membership/relation revision; disallow old tenant access |
| Transfer ownership | Increment resource authorization version; stale out both old and new owners' decisions |
| Add/remove ACL, group, share | Invalidate relationship and all decisions built on it |
| Resource status change | Invalidate status-dependent actions, e.g., EDIT/PUBLISH/DELETE |
| Policy change | Increment policy revision/namespace so old logic's decisions are not reused |
| Parent/project change | Reflect inherited permissions in the relationship tree revision |
| Token/session/MFA expiry | Enforce deadline or configured revocation/freshness check |

When permissions change inside a transaction, invalidation must coordinate with commit. Never emit "revoke succeeded" as a final event before a transaction that might roll back. You can use a **transactional outbox** to record the event in the same transaction and publish after commit, idempotently on retries. However, outbox/pubsub can lag: between commit and every node receiving invalidation, a stale window still exists. If the policy requires **immediate** revocation, add an authoritative freshness gate or stricter consistency.

### Races to Test

**Cache fill after eviction:** Thread A reads stale permissions and takes a long time computing; Thread B revokes permissions, commits, and evicts; Thread A writes the stale `ALLOW` **after eviction**. Fixed-key eviction alone does not solve this race. Use revisions/epochs in the key, verify revisions before publishing, or use proper synchronization.

**Owner A → B → A:** comparing owner ID alone cannot tell whether a request used a stale snapshot; monotonically increasing revisions distinguish epochs when anti-stale policies require it.

**Multi-version policy deployment:** old and new nodes run different policy logic while sharing Redis; without distinguishing policy revisions, old results can be served under new logic.

**Distributed local caches:** instances A and B both cache ALLOW; evicting only one instance does not update the other. Test invalidation fanout, dropped/delayed events, reconnects, and fallbacks.

**Time:** a grant expires at 10:00 while the cache has a 30-minute TTL; the entry must not remain valid past 10:00. Policies based on IP, device, or risk level are poorly suited to long-lived decision caches.

## 9. Testing Both Correctness and Performance Thoroughly

Do not test policies only on **cache miss**. Each scenario should seed data, trigger an actual cache hit, then change one scope factor or permission fact and observe the result. You can use Spring Security tests with MockMvc to check principals/authorities at the web layer, Testcontainers with a production-like DB to verify transactions, and metrics/cache/repository spies to prove hits or misses.

| Test Case | How to Create the Situation | What to Assert |
| --- | --- | --- |
| Cross-subject | Alice READ D creates ALLOW; Bob READ D | Bob does not benefit from Alice's cache |
| Cross-tenant | Same ID in tenant A/B | Tenant B does not reuse A's decision/response |
| Cross-action | READ ALLOW, DELETE DENY | DELETE does not reuse READ's result |
| Cross-resource-type | Document 42 and Invoice 42 | No key collision |
| Role revoked | Warm ALLOW then remove role | Stale ALLOW does not exceed validity contract |
| Membership revoked | Warm ALLOW then remove actor from tenant | Cannot access departed tenant |
| Owner transferred | Alice → Bob with Alice's ALLOW cached | Alice denied; Bob follows current permissions |
| ACL/group changed | Revoke share or change group | Relation/decision cache refreshed |
| Resource status changed | DRAFT → LOCKED | WRITE/PUBLISH blocked even if actor is still owner |
| Policy revision changed | Change role matrix/policy logic | Old policy decisions not reused |
| DENY then granted | Bob initially denied, later granted | Stale DENY does not block beyond allowed window |
| Time-expired grant | Grant expires while TTL remains | No ALLOW after deadline |
| Fill race | Stale read → revoke+evict → stale cache fill | Revoked ALLOW is not resurrected |
| Multi-instance | A/B warm cache, C revokes | All instances uphold consistency contract |
| Cache outage | Redis errors/timeouts | Does not auto-ALLOW; clear fallback/error |
| Valid hit | Same actor/tenant/action/revisions | Actual hit and result matches pure policy |
| Impersonation/delegation | Original actor and acting user differ | Decisions without delegation context never mixed |
| Response cache | Cached body holds private data | Content never served to another actor/tenant |

Re-read data in a fresh transaction and verify owner, ACL, permissions, and side effects. For writes, test the race where permission is checked and then owner/revocation changes before the update: synchronize ordering with `CountDownLatch`/barriers and real commits; never use `Thread.sleep` as proof. Tests must confirm that **the write statement or transaction** preserves invariants even if the cache previously returned ALLOW.

A test using only a mock repository returning DENY does not prove cache invalidation works across DB commits and nodes holding stale data. A test that only asserts a 403 response without verifying hit/miss can pass by accident because the code always misses cache. Complete tests must also include valid allow flows so a buggy solution cannot pass by denying everyone.

## 10. Operational Monitoring and Optimization Choices

Authorization caching is only worthwhile when **gains are measured** and consistency satisfies security commitments. Monitor:

- Hit rate by policy/action/resource type, separating permission, relation, and decision caches.
- Permission check p50/p95/p99 latency; DB query count and relationship lookup time.
- Memory/entry count, eviction rate, cardinality, and stampede frequency on mass misses.
- Invalidation delay between commit and nodes adopting the new revision; event consumer errors.
- Cache backend availability, timeouts, fallback/fail-closed counts.
- Revision mismatch counts, stale results, and suspected cross-tenant test/alert events.

Avoid using emails, user IDs, resource IDs, or raw tokens as metric labels due to cardinality and data exposure. In access-controlled business audit logs, you may log verified actor ID/tenant ID, action, decision source (hit/miss), policy revision, and correlation ID subject to retention policies.

Before adding long-lived decision caches, try simpler optimizations: add proper indexes, eliminate N+1 queries, query scoped by tenant/owner, batch-lookup grants, memoize within a request, and fetch relationships via optimized queries. If using a decision cache still requires reading multiple revisions from the DB on every hit, measure whether it actually saves time. Redis incurs network round-trips; local Caffeine is faster but harder to keep synchronized across instances. No cache provider fixes missing key dimensions.

### Common Mistakes to Avoid

- Using `resourceId` as the sole key, or keying by actor without tenant/action.
- Treating client-supplied `tenantId`, `role`, or `ownerId` as authoritative before reading the cache.
- Treating `@Cacheable` as an authorization boundary and skipping permission checks on database writes.
- Evicting one node and assuming every node is updated.
- Treating TTL as a guarantee of immediate revocation.
- Putting mutable state or sensitive tokens in keys.
- Forgetting to bump revisions in batch jobs, migrations, admin paths, or message consumers.
- Testing only ALLOW, never testing DENY after access changes.
- Caching full HTTP responses by URL even when content varies by user/tenant.
- Failing to verify Spring Cache proxying/self-invocation, leaving caching inactive.

## 11. Acceptance Criteria and Self-Check Exercise

An authorization cache design is acceptable when: (1) valid identical scopes reuse decisions; (2) changing principal, tenant, action, resource type/id, or permission facts never reuses stale ALLOW/DENY; (3) versioning/invalidation and multi-instance behavior uphold the revocation contract; (4) cache failures never turn into granted access; (5) sensitive writes still enforce DB/transaction checks against TOCTOU; and (6) hit rate and latency are measured to prove benefit.

For high-risk actions such as ownership transfer, assigning admin roles, exporting sensitive data, or approvals, prefer checking permissions at the execution boundary and consider **not caching ALLOW across requests** unless freshness can be proven. For low-churn read permissions with a clear staleness SLA, scoped caching is a reasonable option.

Final question: **If Alice received ALLOW for tenant T, resource R, and action READ, what prevents Bob from reusing that result; and when ownership, membership, or policy changes, what mechanism ensures the current cache can no longer grant access wrongly?** Your answer must identify the key scope, revision source, and actual point in time when the change takes effect.
