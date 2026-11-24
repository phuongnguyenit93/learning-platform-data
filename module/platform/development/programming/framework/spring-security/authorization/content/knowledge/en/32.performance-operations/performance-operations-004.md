# Designing Cache Keys by User, Tenant, Resource, and Policy Version

## 1. The Problem: Improving Performance Without Reusing Permissions for the Wrong Subject

A Spring Security system may need to evaluate permissions repeatedly: whether a caller may read a document, edit a contract, download a report, or approve a transaction. Evaluating permissions may require reading roles, memberships, ACLs (Access Control Lists), tenants, resource attributes, and policies. When storing **authorization decision outcomes** (ALLOW/DENY) in a cache to reduce query counts, the single most important rule is that **two permission checks may share a result only if every factor determining their permission is equivalent**.

If the cache key is only the resource ID, Alice's ALLOW decision can be reused for Bob. If the key includes user and resource but omits tenant, IDs that are only unique per tenant can collide. If the key has full identity yet fails to reflect permission or policy changes, the cache can still return ALLOW after the user's permission has been revoked.

**Learning objectives:**

1. Identify the actual inputs of an authorization decision and distinguish them from the returned business data.
2. Construct keys by **user (subject), tenant, resource type/ID, action, policy version, and permission-data versions**.
3. Understand why **policy version**, **subject grant version**, and **resource ACL version** are needed, and when to add other context dimensions.
4. Design TTL, invalidation, concurrent-change handling, and multi-node behavior without breaking permission revocation requirements.
5. Integrate at the right Spring Security layer, measure hit rate, and prove isolation with tests covering both allowed and denied cases.

This lesson focuses on **caching permission-check outcomes** in a Spring Security authorization architecture. Caching document content, tokens, sessions, or HTTP responses is a related problem with its own mechanisms and risks; a sound decision cache does not automatically make other data caches safe.

## 2. What Does an Authorization Decision Depend On?

An authorization decision can be expressed as:

~~~text
Decision = Authorize(
    subject,           // authenticated caller
    tenant,            // trusted tenant scope
    resource,          // resource type, ID, and attributes
    action,            // READ, UPDATE, DELETE, APPROVE...
    policy,            // active rules/version
    context            // grants, ACL, groups, time, state, risk...
)
~~~

Depending on the policy, a user may READ but not UPDATE the same document; an admin in tenant A is still denied on tenant B's documents; sharing or revoking a resource flips the decision even when user, resource, and action stay unchanged.

**Example:** tenant **T1** has Alice's document **doc-7**, and tenant **T2** also has another user's document **doc-7**. Bob in T1 is shared doc-7 for one hour. A key equal to just **doc-7** cannot distinguish the actual object, the requester, or the share's validity.

### 2.1. Fundamental Key Dimensions

| Dimension | Illustrative Value | Why It Must Be Distinguished |
| --- | --- | --- |
| Namespace / service / environment | reports:prod:v1 | Avoid mixing caches across different policy domains, apps, or environments |
| Stable Subject ID | user-42 | Alice's permissions must not be reused for Bob |
| Trusted Tenant ID | tenant-t1 | Prevent ID and decision collisions across tenants |
| Resource type | document | Document ID 7 is not the same as invoice ID 7 |
| Resource ID | doc-7 | Permissions differ per individual object |
| Action | READ / UPDATE | Permission to read does not imply permission to edit |
| Policy version | policy-v12 | Rule changes must establish a new logical namespace |
| Subject grants version | grants-v5 | Changes to roles, memberships, permissions, or user status |
| Resource ACL/version | acl-v9 | Changes to owner, shares, classification label, or object security state |
| Other context dimensions if any | region, assurance, purpose | Share only when every factor the policy actually inspects is equivalent |

Not every system needs these exact fields. **The standard is completeness with respect to the policy**, not adding a fixed checklist and assuming safety. For example, if access depends on tenant subscription, add a tenant entitlement version; if it depends on group membership, add an effective membership version; if it depends on time, share expiry, or step-up authentication, design dedicated expiration handling.

A key can be represented clearly as:

~~~text
authz:v2 | reports | prod
        | tenant=t1 | subject=alice
        | resourceTenant=t1 | type=document | resource=doc-7
        | action=READ
        | policy=12 | subjectGrant=5 | resourceAcl=9
~~~

All of these components must be **normalized and obtained from trusted sources**. A tenant in the URL, an ownerId field in JSON, a client-claimed role, or a policyVersion passed in the request never automatically becomes verified permission data.

### 2.2. Distinguishing Subject, Principal, User, and Login Session

- **Principal** is the identity authenticated by Spring Security; extract a stable ID according to your implementation rather than assuming display names are unique.
- One **user** may have multiple sessions, tokens, or devices. If the policy only depends on account permissions, a key using user + permission versions can suffice.
- If the policy depends on **authentication level (MFA/assurance), OAuth2 token scope, delegation, session context, device trust, token audience**, or login timestamp, include the corresponding info in the key or **do not cache** that decision.
- Never put raw access tokens, session cookies, personal data, or raw emails into Redis keys or logs. Use stable internal IDs or reduced-exposure identifiers, and control access to the cache infrastructure.

**Expired or revoked tokens must be rejected at the authentication layer.** A cached ALLOW must never replace per-request token/session validation. If permissions inside a token change while the token remains valid, you need explicit revocation and permission-validity policies; keys do not refresh stale claims automatically.

## 3. Analyzing Broken Key Designs vs. Sound Versions

Consider Alice and Bob in tenant T1; document D7 belongs to Alice, and only Alice may READ it; Carol in T2 has a different document also bearing ID D7.

| Key | Flaw | Potential Consequence |
| --- | --- | --- |
| **authz:D7** | Missing user, tenant, action, policy | Bob gets Alice's ALLOW; T2 reuses T1's decision |
| **authz:alice:D7** | Missing tenant, resource type, action, versions | READ permission reused for DELETE; cache misses ACL changes |
| **authz:T1:alice:D7:READ** | Has actor/tenant/action but lacks versions | After revocation, stale ALLOW can still be returned |
| **authz:T1:alice:D7:READ:policy12** | Policy code version does not represent ACL/grants | Rules did not change, yet membership was already removed |
| **authz:T1:alice:D7:READ:policy12:grants5:acl9** | Reasonably sound for a policy depending only on these dimensions | Must still verify tenant context, resource type, and other dynamic attributes |
| **Fully policy-aligned structured key** | Each dimension is identified and versioned | Cache hits occur only between genuinely equivalent evaluations |

The last row is a **mental model**, not a guarantee that simply having enough field names solves time, concurrent updates, or lagging version data.

### 3.1. Preventing Key Packaging Collisions

If you concatenate strings via **tenant + ":" + user + ":" + resource**, an ID containing **:** can produce the exact same key as another combination of components. In Java memory, prefer **a record key with distinct fields**; when sending to Redis, use structured/length-prefixed encoding, disciplined escaping, or canonical serialization; you may hash a canonical representation with a suitable algorithm when hiding identities is needed.

Example using a **record** instead of ad-hoc string concatenation:

~~~java
record DecisionKey(
        String namespace,
        String subjectTenantId,
        String subjectId,
        String resourceTenantId,
        String resourceType,
        String resourceId,
        Action action,
        long policyVersion,
        long subjectGrantVersion,
        long resourceAclVersion) {
}
~~~

A Java record provides **equals/hashCode over every component**, making it convenient as a **ConcurrentHashMap** key. When scaling out to Redis, you still need a serializer that stays stable across deployments with consistent data types, normalized IDs, and key schema versioning.

## 4. Choosing Version Sources: Policy, User, and Resource

### 4.1. Policy Version

**Policy version** must change whenever rules that can affect decisions change: changing role conditions, adding tenant restrictions, updating business rules, modifying policy bundles, changing data-classification logic, etc.

- Pick a **non-reused** version ID for a given policy scope (a monotonically increasing revision or an immutable content hash of the policy and its dependencies).
- Distinguish **deployment version** from **policy version**: deploying frontend changes or fixing logs need not affect permissions; changing policy without bumping the version is dangerous.
- If policies differ per tenant, use a tenant-scoped policy or corresponding dimension. A global version still works if all changes apply across all tenants.
- Rollbacks must not arbitrarily reuse an old epoch if grants/ACL data has changed and keys could collide with earlier cache entries; monotonic epochs are easier to reason about.

### 4.2. Subject Grant Version

Update **subjectGrantVersion** when changing direct roles/permissions, memberships, group rights, disable/suspend flags, or any subject attribute inspected by the policy. If permissions are inherited from a group, bumping only the user's version is insufficient when the group changes without touching the user record: use an **effective authorization epoch**, a group/membership version, or an invalidation mechanism covering all members.

Principal data inside a token may lag behind the DB. You must decide which source is authoritative and how refresh/revocation works; never take a new version number while still evaluating against stale rights.

### 4.3. Resource ACL/Version

Update **resourceAclVersion** when changing owner, shares, classification, document state, or policy-relevant metadata. If the policy depends on multiple related resources (parent folder, project, organization, hierarchy), a child document's ACL version alone may not reflect parent changes. You need a composite version, dependency epoch, or to skip caching where consistency cannot be guaranteed.

A safe design typically loads **resourceTenantId, owner, aclVersion** from a trusted repository/data layer rather than trusting client-supplied ID/tenant/owner values.

### 4.4. Cache Invalidation vs. Versioned Keys

The two strategies can be combined:

- **Versioned key:** changing the version makes the next access use a new key without needing to immediately hunt down and delete all old keys. In exchange, old keys continue consuming memory until eviction/TTL.
- **Eviction/event invalidation:** when a role or ACL changes, delete affected keys. In distributed caches, events can arrive late, be dropped, or arrive out of order.
- **TTL:** caps key lifetime, aids memory management, and bounds the stale window; TTL **does not prove** permissions are revoked immediately.

If the requirement is "revocation must take effect immediately," you need a sufficiently consistent version/permission source on **every check**, or skip caching for that sensitive decision. Firing asynchronous cache-delete events alone provides no strong guarantee on when all nodes stop using a stale ALLOW.

## 5. Flowchart of Cached Permission Checks

~~~mermaid
flowchart TD
    A[Request passes authentication] --> B{Principal and tenant valid?}
    B -- No --> X[DENY]
    B -- Yes --> C[Read permission/ACL snapshot and versions from trusted source]
    C --> D{Can policy inputs be cached safely?}
    D -- No --> E[Evaluate policy directly]
    D -- Yes --> F[Build full DecisionKey]
    F --> G{Valid cache hit, TTL not expired?}
    G -- Yes --> H[Return stored decision]
    G -- No --> I[Evaluate policy on snapshot]
    I --> J{Cacheable per TTL/consistency policy?}
    J -- Yes --> K[Store ALLOW or DENY with bounded TTL]
    J -- No --> L[Do not store]
    K --> M[Return decision]
    L --> M
    E --> M
~~~

**Important note:** even when the key contains versions, the algorithm above is only sound when **the snapshot and versions** reflect a single sufficiently consistent state, and every fact the policy depends on is covered by the versioning mechanism. If you read an old version from local memory while the DB ACL has already changed, a new key will not fix stale permissions. If you read the version at time A while the policy reads data at time B, design transactions/snapshots, rechecks, or synchronization matching your security requirements.

Example of changing permissions on a document:

1. Bob cannot view report R7 yet; **key(T1, Bob, R7, READ, policy=12, grants=3, acl=8)** returns DENY.
2. Alice shares R7 with Bob; the system commits the new ACL **acl=9**. The next evaluation reads the new snapshot, builds a key with **acl=9**, evaluates ALLOW, and may cache it.
3. Alice revokes the share; the system commits **acl=10**. If the next evaluation fetches the current snapshot, key **acl=10** cannot hit the ALLOW of **acl=9**, so it re-evaluates and returns DENY.
4. If one node still reads **acl=9** due to metadata caching or replica lag, that node can serve a stale ALLOW. That is an **input data consistency** issue, not just a key structure issue.

## 6. Standalone Java 17 Example: Proper Key Dimensions and Versions

This small example avoids Spring dependencies to focus on key correctness. All subjects/resources are **server-built trusted snapshots**; revisions must increment when permissions/ACLs change. Sample policy: within the same tenant, the owner has READ/EDIT, shared readers have READ only, and a tenant ADMIN can READ/EDIT within that tenant. Admin rights **never cross tenants**.

Create **AuthorizationCacheDemo.java**:

~~~java
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

public class AuthorizationCacheDemo {
    enum Action {
        READ, EDIT
    }

    record Subject(
            String id,
            String tenantId,
            long grantsVersion,
            boolean admin) {
    }

    record Resource(
            String id,
            String tenantId,
            String ownerId,
            long aclVersion,
            Set<String> sharedReaders) {
        Resource {
            sharedReaders = Set.copyOf(sharedReaders);
        }
    }

    record DecisionKey(
            String namespace,
            String subjectTenantId,
            String subjectId,
            String resourceTenantId,
            String resourceType,
            String resourceId,
            Action action,
            long policyVersion,
            long grantsVersion,
            long aclVersion) {
    }

    static final class AuthorizationCache {
        private final ConcurrentHashMap<DecisionKey, Boolean> answers =
                new ConcurrentHashMap<>();
        private final AtomicInteger evaluations = new AtomicInteger();

        boolean allowed(Subject subject, Resource resource,
                        Action action, long trustedPolicyVersion) {
            DecisionKey key = new DecisionKey(
                    "report-service:prod:v1",
                    subject.tenantId(),
                    subject.id(),
                    resource.tenantId(),
                    "report",
                    resource.id(),
                    action,
                    trustedPolicyVersion,
                    subject.grantsVersion(),
                    resource.aclVersion()
            );

            return answers.computeIfAbsent(
                    key,
                    ignored -> evaluate(subject, resource, action)
            );
        }

        private boolean evaluate(Subject subject, Resource resource,
                                 Action action) {
            evaluations.incrementAndGet();

            // Always check tenant boundary even before admin permissions.
            if (!subject.tenantId().equals(resource.tenantId())) {
                return false;
            }

            if (subject.admin()) {
                return true;
            }

            if (subject.id().equals(resource.ownerId())) {
                return true;
            }

            return action == Action.READ
                    && resource.sharedReaders().contains(subject.id());
        }

        int evaluationCount() {
            return evaluations.get();
        }
    }

    public static void main(String[] args) {
        AuthorizationCache cache = new AuthorizationCache();

        Subject alice = new Subject("alice", "T1", 1, false);
        Subject bob = new Subject("bob", "T1", 1, false);
        Subject carol = new Subject("carol", "T2", 1, true);

        Resource original = new Resource(
                "R7", "T1", "alice", 1, Set.of()
        );

        System.out.println("Alice READ: "
                + cache.allowed(alice, original, Action.READ, 1));
        System.out.println("Bob READ: "
                + cache.allowed(bob, original, Action.READ, 1));
        System.out.println("Bob READ again: "
                + cache.allowed(bob, original, Action.READ, 1));
        System.out.println("Evaluations after repeat: "
                + cache.evaluationCount());

        // ACL changed; version must increment to produce a new key.
        Resource shared = new Resource(
                "R7", "T1", "alice", 2, Set.of("bob")
        );
        System.out.println("Bob after share: "
                + cache.allowed(bob, shared, Action.READ, 1));

        Resource revoked = new Resource(
                "R7", "T1", "alice", 3, Set.of()
        );
        System.out.println("Bob after revoke: "
                + cache.allowed(bob, revoked, Action.READ, 1));

        // Subject permissions changed, so grantsVersion changes too.
        Subject adminBob = new Subject("bob", "T1", 2, true);
        System.out.println("Bob after admin grant: "
                + cache.allowed(adminBob, revoked, Action.READ, 1));

        // T2 admin has no implicit permissions in T1.
        System.out.println("Other tenant admin: "
                + cache.allowed(carol, revoked, Action.READ, 1));

        // Policy version changed so cache does not hit old-version keys.
        System.out.println("Bob after policy version bump: "
                + cache.allowed(bob, revoked, Action.READ, 2));
        System.out.println("Evaluations total: "
                + cache.evaluationCount());
    }
}
~~~

Run in the file's directory with JDK 17 or higher:

~~~bash
javac AuthorizationCacheDemo.java
java AuthorizationCacheDemo
~~~

Exact expected stdout:

~~~text
Alice READ: true
Bob READ: false
Bob READ again: false
Evaluations after repeat: 2
Bob after share: true
Bob after revoke: false
Bob after admin grant: true
Other tenant admin: false
Bob after policy version bump: false
Evaluations total: 7
~~~

Why is the total policy evaluation count **7**? Alice and Bob create two separate keys. Bob repeats READ with the same key, hitting the cache. Each bump in ACL version, grant version, tenant/subject change, or policy version yields a distinct key, triggering a fresh evaluation. **No permission is shared between Alice and Bob merely because of the same resource ID**.

**Intentional limitations of the demo:** there is no TTL, max size, distributed storage, real security context, transaction, or snapshot version verification; thus use it to learn how keys distinguish inputs, **do not copy verbatim as a production cache**. **trustedPolicyVersion** is supplied by simulated server code; policy versions and grant/ACL versions must never be taken from unverified requests. If an input changes without bumping its revision, the example can still return a stale result.

## 7. Integrating Cached Decisions at the Right Spring Security Layer

In Spring Security 6, you can enable method security with **@EnableMethodSecurity**, then use **@PreAuthorize** to call a policy bean. Caching should sit **inside the authorization evaluation engine**; a cache HIT only replaces re-evaluating a *decision* with equivalent inputs—it never skips authentication and never replaces guards on other entry points into the service.

Proper flow:

~~~text
SecurityFilterChain
   -> authenticate user/token/session
   -> Spring-managed service method proxy
   -> @PreAuthorize calls policy bean
   -> policy bean loads trusted subject + resource + versions
   -> authorization decision cache (hit or re-evaluate)
   -> only invoke business logic if ALLOW
~~~

The following Spring snippets are **integration fragments**; application types such as **ReportDto**, **ReportRepository**, **DecisionService**, and permission/tenant loaders must be defined for your real system. The standalone Java example in section 6 is a runnable program.

**SecurityConfig.java (configuration class fragment):**

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class SecurityConfig {
}
~~~

**ReportService.java (service boundary fragment):**

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class ReportService {
    private final ReportRepository repository;

    public ReportService(ReportRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize("@reportPolicy.canRead(authentication, #p0)")
    public ReportDto read(String reportId) {
        return repository.findDtoById(reportId);
    }
}
~~~

**ReportPolicy.java (policy bean fragment):**

~~~java
import org.springframework.security.core.Authentication;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.stereotype.Component;

@Component("reportPolicy")
public class ReportPolicy {
    private final DecisionService decisionService;

    public ReportPolicy(DecisionService decisionService) {
        this.decisionService = decisionService;
    }

    public boolean canRead(Authentication authentication, String reportId) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }

        // DecisionService must obtain subject/tenant/ACL/versions
        // from the verified principal and a trusted repository.
        return decisionService.canRead(authentication, reportId);
    }
}
~~~

In **@PreAuthorize**, **#p0** references the first method parameter, avoiding reliance on compiler parameter-name retention. **@EnableMethodSecurity** must be active in the application context; service calls must pass through the Spring-managed proxy. If an annotated method is invoked via **this.method()** on the same bean, the Spring AOP proxy can be bypassed; never treat cache or annotations as the sole barrier if actual call paths skip the interceptor.

**Important:** do not casually place **@Cacheable** directly on the method returning **ReportDto** just because **@PreAuthorize** is present. A data cache applied before the authorization step—or another call path bypassing the security proxy—can return data to the wrong owner. Separate **decision evaluation** from **content retrieval**, and verify advice ordering and all entry points with real tests.

If you choose **@Cacheable** on a policy evaluator, verify the **key generator**, SpEL key, proxy interception, provider TTL, and behavior when policies change. Spring Cache's default key uses method parameters; if a method only accepts a resource ID and reads the current user from a thread-local, the default key **omits user/tenant/action/version** and is very dangerous. Construct a **complete DecisionKey** and pass it into the cached method, or use the cache API directly to control every dimension.

## 8. TTL, ALLOW/DENY, and Revocation in Practice

### 8.1. TTL Should Reflect Acceptable Staleness

| Decision Type | Suggested Cache Policy | Risk to Control |
| --- | --- | --- |
| READ on low-churn resources | Short TTL / versioned and evicted | Stale ALLOW after share revocation |
| High-impact WRITE/DELETE/APPROVE | Possibly do not cache, or require strong versions and recheck right before write | Write succeeds even though role/ACL just changed |
| Temporary DENY when not yet shared | Short cache with trusted version | After access is granted, stale DENY causes UX errors |
| DENY from emergency state or dynamic policy | Usually re-evaluate unless context/version is modeled | Stale result misses updated risk level |
| Time-bound or short-lived conditions | TTL must not exceed the earliest instant the decision expires | Returning ALLOW after share expiry or MFA timeout |

There is no universal TTL number. The platform team must define the **revocation SLA** (for instance immediate effect, within seconds, or per-session) and select a strategy based on what versions, replicas, and nodes actually guarantee. **A 30-second TTL is only a cache lifetime cap**, not a guarantee that all nodes deny in 0 seconds.

If a decision depends on the **expiresAt** of a temporary grant, cap the TTL at **min(configured TTL, expiresAt - now)** and watch out for clock skew; sometimes it is better to skip caching or use a consistent time source. For context that is hard to capture in a key (per-request risk score, IP, device), default to **not caching** unless equivalence and staleness limits are proven.

### 8.2. After Changing a Role, Share, or Policy

A safe workflow matching consistency requirements can follow:

1. Update permission data at the authoritative source and increment the corresponding **revision/epoch** in the same consistency unit (usually a transaction).
2. Publish the new version only after the change commits; specify clearly which version nodes read and whether stale replicas are permitted.
3. Emit invalidation/events or switch namespace versions for affected caches; implement retry/deduplication and handle out-of-order events.
4. On the next request, load a sufficiently fresh **snapshot + version**; build the key and hit only if every dimension matches; when the version cannot be verified, act per risk policy: re-evaluate from the authoritative source or deny cleanly.
5. For especially sensitive operations, recheck permissions at commit/transaction time to prevent **time-of-check to time-of-use (TOCTOU)**: allowed at check time, yet revoked before the DB update.

Never clear a key on one node and assume the whole system has revoked access. With **L1 local cache + L2 Redis**, each tier has its own state; invalidation, TTL, and where versions are read from must be explicit.

### 8.3. Cache Downtime and Policy Backend Errors

- **Cache unreachable:** if the policy can be evaluated from the authoritative source, bypass the cache and recompute. If the policy source also fails, never return **ALLOW** by default for a sensitive operation.
- **Cached ALLOW exists, but current version cannot be read:** you cannot prove the key is still valid. For systems requiring immediate revocation, avoid serving the cached ALLOW.
- **Cache stampede:** concurrent misses can overload the policy backend. Use per-key load coalescing, jittered TTLs, bounded caches, batch limits, and latency monitoring; never relax permission checks to shed load.
- **Cache poisoning / key tampering:** namespaces and keys must be server-computed; never accept raw cache keys or arbitrary policyVersions from clients; cache storage needs proper network ACLs, encryption, and auditing.

## 9. Required Test Suite

An authorization cache test suite must check **both permission correctness** and **performance**. Seeing cache hits rise alone does not prove the system is secure.

| Test Case | What Stays the Same? | What Changes? | Expectation |
| --- | --- | --- | --- |
| Valid cache HIT | Subject, tenant, resource, action, versions | Nothing | Same decision; evaluator does not re-run |
| Block different user | Tenant, resource, action, versions | Alice → Bob | Alice's ALLOW is not used for Bob |
| Block different tenant | Identical-looking resource ID | T1 → T2 | No collision / no cross-tenant access |
| Block different action | User, tenant, resource | READ → DELETE | READ ALLOW does not grant DELETE |
| Block different resource type | Tenant, user, ID | document → invoice | Decision is not shared |
| ACL changed | User/resource/action | Share or revoke + ACL version bumped | New key, decision recomputed |
| Role/grant changed | User/resource/action | Subject grant version bumped | New key, old role not retained |
| Policy changed | All other business inputs | Policy version bumped | New rules evaluated |
| Parent/group relation changed | Resource/child relation | Parent ACL or group membership changed | Dependency version reflects it, old rights dropped |
| Grant expired | Same base key | Time passes expiry | Never returns ALLOW past expiry |
| Cache failure | Valid request | Redis unavailable | Safe recompute or policy-driven denial |
| Multi-node | Requests across L1/L2 | Revoke permission on node A | Node B meets revocation SLA |
| Concurrent update | Same user/resource | ACL changes during evaluate/cache insert | Unauthorized ALLOW is not resurrected |
| Object deleted/recreated | Same resource ID | Object generation changes | Key/version blocks decision reuse for new object |

For Spring Security, write tests with **MockMvc** or service tests using **@WithMockUser** and corresponding real principals. Include both **ALLOW** and **DENY** request cases, then test the policy service directly via the Spring bean to ensure HTTP matchers are not masking cache bugs. When testing writes, check DB **side effects**: returning 403 after data was already mutated is still a bug.

Suggested property test for the key builder: given two input sets differing on **any field the policy depends on**, keys must differ; when all components match, keys must be equal and hashCode consistent. Test canonicalization for IDs containing delimiters or Unicode characters. For Redis serializers, test across multiple application versions and optional fields.

### 9.1. Positive and Negative State Tests

In particular, avoid writing tests only for authorized users. For example:
- Alice can read D7, Bob cannot read D7: Bob must get DENY even after the cache has stored Alice's ALLOW.
- Bob is shared D7: after the version increments, Bob must get ALLOW.
- D7 share is revoked: after the version increments, Bob must get DENY and D7 data must not appear in the response.
- Bob is promoted to admin **in T1**: documents in T2 must still return DENY.
- When policyVersion changes, an old key must not be retrieved under the new version, even if the final decision happens to match.

For sensitive operations, automate race/invalidation tests with latches or a fake clock instead of **Thread.sleep** which makes tests flaky. A fake clock lets you test TTL expiration and temporary-grant revocation deterministically.

## 10. Monitoring Performance and Operational Safety

Measure separately: **evaluation count**, hits/misses per service/action, policy check latency at p50/p95/p99, TTL expirations, invalidation counts, event queue lag, version-fetch latency, cache memory/cardinality, and fallback counts when backends fail.

**A high cache hit rate is not proof of good performance if the key is too coarse**: hit rate can be high simply because ALLOW is accidentally shared across users. Conversely, a complete key with multiple versions may lower hit rate while staying permission-correct. Optimize on **valid hit rate + latency + measured staleness**, not hit maximization alone.

When logging and auditing:
- You may log **namespace, action, outcome, hit/miss, policy revision, request trace ID**, and policy-redacted resource/subject identifiers.
- Avoid logging full tokens, user sessions, sensitive ACLs, or keys containing raw emails/IPs.
- Distinguish policy-driven **authorization denied** from **backend unavailable**, **snapshot/version unavailable**, and **cache hit**; lumping everything into one HTTP 403 or one metric makes incident detection difficult.
- Bound cache size (entries/weight), set TTL/eviction, and monitor stale keys after version bumps; versioned keys aid correctness but can raise cardinality.

### Design Review Checklist

1. Does the key include **subject + trusted tenant + resource type/ID + action**? Does it distinguish resource tenant when different from subject tenant or when IDs are only tenant-unique?
2. Which **scope** does the policy for this decision belong to? Which deploy/code changes bump the version? Can old versions ever be reused?
3. Do all **grants, ACLs, parent/group links, and tenant entitlements** affecting the decision have guaranteed revisions or invalidation?
4. Are versions and permission data read from **the same consistent state**, or is there replica/local cache lag? Is there a real revocation SLA?
5. Do permissions depend on **time, MFA, token scope, IP, risk, purpose**, or other dynamic conditions? If so, do keys/TTLs cover them completely or should caching be skipped?
6. How does the system block requests when **cache/version backends fail**? Can stale ALLOW ever be returned without valid proof?
7. Does the integration point keep authentication and method/request authorization **before returning resources**, or does it accidentally cache business responses?
8. Are there tests for valid hits, cross-user/cross-tenant, different actions, policy changes, revocation, concurrency, multi-node, and side effects?
9. Does the cache have **bounded size, TTL, metrics, and cleanup for old keys**? Are cache contents and logs protected against identity exposure?

## 11. Applied Conclusion

An authorization cache is only safe when **the key accurately represents every fact the policy used to make its decision**, and those facts remain valid at reuse time. The four core pillars of the design are **subject, tenant, resource/action, and versions**; versioning must cover both **policy logic** and mutable permission data such as **roles/grants** and **ACLs**.

In Spring Security, place caching at the policy/decision layer, take the subject from the authenticated security context, load tenant/resource metadata/versions from trusted sources, and test **negative authorization** and revocation behavior. Whenever you cannot guarantee snapshots/versions are fresh enough for the security requirement, **re-evaluating or skipping caching** is the right choice over serving an ungrounded cached ALLOW.

### References

- Spring Security, Method Security: https://docs.spring.io/spring-security/reference/6.5/servlet/authorization/method-security.html
- Spring Framework, Cache Abstraction and @Cacheable annotation: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework, AOP proxying and self-invocation: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html
- OWASP, Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
