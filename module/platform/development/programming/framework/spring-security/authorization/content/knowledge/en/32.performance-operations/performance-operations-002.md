# Avoiding N+1 Queries When PermissionEvaluator or ACL Checks Multiple Objects

## 1. Problem Statement and Goals

In Spring Security, checking permissions on **a single object** is usually straightforward:

~~~java
@PreAuthorize("hasPermission(#documentId, 'Document', 'READ')")
public DocumentDto getDocument(long documentId) {
    return documentService.load(documentId);
}
~~~

The snippet above illustrates an example where method security is enabled and \`PermissionEvaluator\` is configured. If permissions must be looked up in a database, one \`hasPermission\` call can trigger at least one query. That is easily acceptable for a single object, but it creates an **N+1** problem when an API returns a list of N objects and checks each element one by one.

For example:

~~~java
@PostFilter("hasPermission(filterObject, 'READ')")
public List<Document> listDocuments() {
    return documentRepository.findAll();
}
~~~

\`@PostFilter\` iterates over the returned objects, evaluates the expression for each element, and removes unauthorized items. If each \`hasPermission\` evaluation runs an ACL query, the total query count can be **1 query to load the list + N permission queries**. If the evaluator also looks up memberships, roles, ACL inheritance, or owners per item, the query count can be even higher. Collecting objects in a Java Stream does not automatically batch SQL queries.

**Goals of this lesson:**
- Identify N+1 queries caused by authorization policies, separating them from N+1 caused by Hibernate lazy loading.
- Measure query count, latency, and ACL/PDP call count as list size grows.
- Choose between **filtering permissions at the database before pagination** and **batch-loading permissions for a bounded set of objects**.
- Apply \`PermissionEvaluator\`, \`AclService\`, \`PermissionCacheOptimizer\`, and caching properly without accidentally altering ACL semantics.
- Verify allowed/denied results, pagination correctness, and tenant isolation after optimization.

## 2. How N+1 Occurs During Authorization Checks

Suppose a request fetches 100 documents:

~~~text
HTTP GET /tenants/t-a/documents
  └─ SELECT ... FROM document WHERE tenant_id = 't-a'       [1 query]
      ├─ hasPermission(doc1, READ) → SELECT ACL...           [1 query]
      ├─ hasPermission(doc2, READ) → SELECT ACL...           [1 query]
      ├─ ...
      └─ hasPermission(doc100, READ) → SELECT ACL...         [1 query]

Total: roughly 101 queries, excluding membership, SID, and lazy associations.
~~~

Table assuming **one permission query per object**, without caching:

| N Objects | List Load Queries | Per-Item Permission Queries | Total |
|---:|---:|---:|---:|
| 1 | 1 | 1 | 2 |
| 10 | 1 | 10 | 11 |
| 100 | 1 | 100 | 101 |
| 500 | 1 | 500 | 501 |

This is an illustrative calculation, not a fixed Spring Security number. Actual counts depend on the evaluator, ACL cache, ACE structure, membership, SQL query plan, and how many objects are filtered out.

### 2.1. Common Code Paths That Cause This

**Path A — \`@PostFilter\` + \`PermissionEvaluator\`:**

~~~java
@PostFilter("hasPermission(filterObject, 'READ')")
public List<Document> findAll() {
    return documentRepository.findAll();
}
~~~

Spring Security iterates over the collection after the service returns. If the evaluator accesses a repository to decide each object, N+1 occurs even if the initial \`findAll\` query is fast.

**Path B — Filtering with a Stream:**

~~~java
List<Document> visible = documents.stream()
        .filter(d -> permissionEvaluator.hasPermission(
                authentication, d, "READ"))
        .toList();
~~~

The code looks concise, yet it still invokes \`hasPermission\` N times; if the inside helper queries the DB, it still runs N queries.

**Path C — Database-backed ACL:** \`AclPermissionEvaluator\` can call \`AclService\` to look up the ACL for an \`ObjectIdentity\`. If the ACL is not cached, each object may trigger reads of the ACL and related records. User/authority SIDs and ACL inheritance can complicate the query path further. However, **not every Spring ACL setup is N+1 by default**: caches, lookup strategies, and batching mechanisms can improve it.

**Path D — ORM and remote authorization:** the evaluator calls \`document.getOwner().getMemberships()\`, causing Hibernate to load lazy associations per element; or it calls a PDP/OPA service over HTTP per object. Both are also N+1 patterns, even though the resource bottleneck differs.

### 2.2. Symptoms to Check

- SQL logs show the same ACL query repeated with different \`document_id\` values.
- Increasing page size from 20 to 200 causes query count and response time to grow nearly linearly.
- Database CPU / connection pool usage spikes on list/search endpoints while detail endpoints remain fast.
- \`@PostFilter\` leaves very few items after pagination; \`totalElements\` may fail to reflect the number of items the user is actually allowed to see.
- Enabling a cache makes benchmarks look good on the second run, yet the first run or post-revocation runs remain slow.

**Important distinction:** Evaluating permissions N times in Java is not necessarily an N+1 problem if permission data was preloaded and lookups happen entirely in memory. The optimization target is DB/network round-trips and overall cost, not eliminating every loop.

## 3. Define the Policy Before Optimizing

Optimizing authorization must preserve **ALLOW/DENY** decisions. Example document system:

- \`document\` has \`id\`, \`tenant_id\`, \`owner_id\`, \`visibility\`, \`deleted_at\`, \`created_at\`.
- \`tenant_membership\` has \`tenant_id\`, \`user_id\`, \`role\`, \`active\`.
- \`document_share\` has \`tenant_id\`, \`document_id\`, \`recipient_id\`, \`permission\`, \`expires_at\`, \`revoked_at\`.
- A user must have an **active membership in the tenant**. For READ permission within that tenant, reading is allowed if the user is the owner, is an ADMIN of the tenant, the document visibility is TENANT, or there is a non-expired, unrevoked READ/WRITE grant.
- WRITE does not implicitly mean SHARE/DELETE; policies for other actions must be defined independently.

When the client passes \`tenantId\`, the server must still obtain identity from \`Authentication\` and verify the corresponding membership. Never trust \`role\`, \`owner_id\`, \`isAdmin\`, or \`grantedBy\` sent by the client. **An ADMIN of tenant B has no permissions on tenant A's documents.**

Two kinds of lists must be distinguished:

1. **A list containing only READ-authorized documents:** authorization should be pushed down into the data query before pagination whenever possible.
2. **A list already authorized by the repository that needs extra \`canEdit\` / \`canShare\` flags for the UI:** you can use batch permission lookup on the already bounded document set.

If you keep \`@PostFilter\` on top of a page already sliced in the database, both performance **and** pagination can break.

## 4. Best Approach for Lists: Filter at the Database Before Pagination

For a relatively straightforward READ policy like in section 3, let the database filter permissions in **one set-based query**. The illustrative SQL below uses parameters taken from the authenticated principal and verified tenant:

~~~sql
SELECT d.id, d.title, d.owner_id, d.created_at
FROM document d
WHERE d.tenant_id = :tenantId
  AND d.deleted_at IS NULL
  AND EXISTS (
      SELECT 1
      FROM tenant_membership m
      WHERE m.tenant_id = d.tenant_id
        AND m.user_id = :userId
        AND m.active = TRUE
  )
  AND (
      d.owner_id = :userId
      OR d.visibility = 'TENANT'
      OR EXISTS (
          SELECT 1
          FROM tenant_membership m_admin
          WHERE m_admin.tenant_id = d.tenant_id
            AND m_admin.user_id = :userId
            AND m_admin.active = TRUE
            AND m_admin.role = 'ADMIN'
      )
      OR EXISTS (
          SELECT 1
          FROM document_share s
          WHERE s.tenant_id = d.tenant_id
            AND s.document_id = d.id
            AND s.recipient_id = :userId
            AND s.permission IN ('READ', 'WRITE')
            AND s.revoked_at IS NULL
            AND (s.expires_at IS NULL OR s.expires_at > :now)
      )
  )
ORDER BY d.created_at DESC, d.id DESC
LIMIT :pageSize OFFSET :offset;
~~~

In a real system, membership verification may happen prior to the query via a single lookup; the \`EXISTS\` clause above is kept to illustrate the authorization constraint directly in SQL. \`:userId\`, \`:tenantId\`, and \`:now\` are **bind parameters**, never concatenated SQL strings from the request.

**Why does this avoid N+1?** The database processes the document set and share set via joins/semi-joins/subqueries instead of the application sending a separate SQL request per document. From the application perspective, the statement count is typically one page query plus one count query if the API returns a \`Page\`; the database may still scan many internal rows, so inspect the query plan. \`EXISTS\` also prevents duplicating documents when a document has multiple share/role rows.

### 4.1. Pagination and Count Must Share the Same Policy

Wrong:

~~~text
Database fetches 20 arbitrary documents → @PostFilter drops 17 documents
→ client receives 3 documents even though many more authorized documents exist on later pages.
~~~

If the API exposes \`Page<DocumentDto>\`, apply the exact **same permission predicate** to both the page query and the \`COUNT\` query. If the count totals all documents before filtering, the total is both wrong and may leak the count of data the user is not allowed to see.

For large tables, deep \`OFFSET\` can be slow; you can use keyset/cursor pagination on \`(created_at, id)\` with the same permission condition. Cursors must be bound to the same tenant and filter; the list may shift if shares/revokes happen between requests. Do not mask that behavior with stale caches.

### 4.2. Indexes and Columns to Read

Initial suggested indexes (tune with \`EXPLAIN ANALYZE\` and real data):

~~~sql
CREATE INDEX idx_document_tenant_order
    ON document (tenant_id, created_at DESC, id DESC);

CREATE INDEX idx_membership_tenant_user
    ON tenant_membership (tenant_id, user_id);

CREATE INDEX idx_share_tenant_recipient_doc
    ON document_share (tenant_id, recipient_id, document_id);
~~~

Add conditions/partial indexes for active shares or revocation status depending on the DBMS and query profile; do not add indexes blindly without evidence. The \`expires_at\` column changes meaning over time, so you cannot assume a cached boolean \`active\` column stays accurate. Select only the columns needed for the DTO; if you map entities and traverse lazy relationships afterward, Hibernate N+1 can still happen.

**Important limitation:** The SQL \`EXISTS\` here models **a simple share grant model**. If the system uses full Spring Security ACL with ordered allow/deny ACEs, group/role SIDs, parent ACL/inheritance, and a \`PermissionGrantingStrategy\`, a hand-written SQL \`EXISTS\` might **not be equivalent** to the ACL engine. In that case, preserve ACL semantics via batched \`AclService\`, or build a permission projection proven equivalent by tests.

## 5. When to Use Batch Permission Prefetch?

Use batching when you need to check a **bounded set of objects**, such as a list of 50 documents that already passed READ and need \`canEdit\`/\`canShare\` computed for the UI, or a workflow processing 100 specific objects that requires per-item decisions.

Instead of:

~~~java
// Illustrative: each call may query the DB.
for (Document d : documents) {
    boolean canEdit = permissionEvaluator.hasPermission(auth, d, "EDIT");
    // ...
}
~~~

Load the relevant relationships once and look them up in an in-memory map/set:

~~~java
// Service pseudocode: repository and DTO are defined by the application.
List<Document> documents =
        documentRepository.findReadablePage(tenantId, userId, pageRequest);
Set<Long> ids = documents.stream()
        .map(Document::getId)
        .collect(Collectors.toSet());

Map<Long, Set<String>> grantsByDocument =
        shareRepository.findActivePermissionsFor(
                tenantId, userId, ids, clock.instant());

List<DocumentDto> result = documents.stream()
        .map(d -> mapper.toDto(d,
                policy.canEdit(d, membership, grantsByDocument.get(d.getId()))))
        .toList();
~~~

This is **non-standalone illustrative code**; \`findReadablePage\`, \`findActivePermissionsFor\`, \`policy\`, and the DTO are application-defined APIs. If \`ids\` is empty, skip the batch query. Always scope by both \`tenantId\` and the \`ids\` set when loading shares; never treat data from another tenant as a valid grant.

SQL for the prefetch step:

~~~sql
SELECT s.document_id, s.permission
FROM document_share s
WHERE s.tenant_id = :tenantId
  AND s.recipient_id = :userId
  AND s.document_id IN (:documentIds)
  AND s.revoked_at IS NULL
  AND (s.expires_at IS NULL OR s.expires_at > :now);
~~~

When receiving multiple grants for the same document, combine permissions according to the actual policy. If the system has **deny ACEs**, do not naively combine by OR-ing allow grants.

### 5.1. Why Is Batching Effective?

With N documents, per-item checks can take \`1 + N\` round-trips. If batching supports up to B IDs per query, the statement count is approximately \`1 + ceil(N/B)\`. For 100 items and B=100, that is only about 2 statements; if membership/role uses separate queries, add that fixed overhead. **This is a cost model, not a universal guarantee for every implementation.**

A massive batch query is not free either: databases have bind-parameter limits and plan cache limits, result sets can be large, and concurrent requests can create memory pressure. Choose sensible page/batch sizes, chunk when needed, measure queries/latency, and do not load millions of ACLs into a single set.

### 5.2. Protecting Consistency

- Prefetch must use the **same tenant, actor, action, and timestamp** as the decision step.
- If permissions can be revoked between reading shares and performing a write, you need transactions/locking/versioning or a re-check at the mutation boundary per your threat model; batch prefetch does not allow bypassing the final check.
- Only cache necessary data within the request/transaction scope when no reliable invalidation mechanism exists.
- Never check object permissions while ignoring membership (a user who left the tenant may still have old grants).
- If the batch repository fails or returns incomplete data, apply **deny by default** instead of returning true for availability.

## 6. With Spring Security ACL: Use Multi-Identity Read APIs

Spring Security provides \`AclPermissionEvaluator\` to integrate ACL into \`hasPermission\`. \`AclService\` provides two important API groups:

~~~java
// Single object: easily becomes N calls if used inside a loop.
Acl acl = aclService.readAclById(objectIdentity, sids);

// Multiple objects: API supports loading in batches.
Map<ObjectIdentity, Acl> acls =
        aclService.readAclsById(objectIdentities, sids);
~~~

These are **two illustrative snippets inside a service that already has the corresponding variables and beans**. \`objectIdentities\` is a list of \`ObjectIdentity\` instances built from actual type + ID, and \`sids\` reflects the principal and authorities under evaluation. When comparing permissions, use the exact ACL/ACE semantics, including deny, SID ordering, parent ACL, and permission mask; do not replace it with \`acls.containsKey(id)\` or treat a missing ACL as allowed.

### 6.1. PermissionCacheOptimizer for Collection Filtering

Spring Security has the \`PermissionCacheOptimizer.cachePermissionsFor(Authentication, Collection<?>)\` interface. For ACL, \`AclPermissionCacheOptimizer\` can batch-load ACLs for a collection before evaluating expressions repeatedly. If a project uses method security + \`AclPermissionEvaluator\`, an illustrative Spring Security 6.x configuration is:

~~~java
@Configuration
@EnableMethodSecurity
class MethodSecurityConfig {
    @Bean
    static MethodSecurityExpressionHandler methodSecurityExpressionHandler(
            AclPermissionEvaluator aclPermissionEvaluator,
            AclService aclService) {
        var handler = new DefaultMethodSecurityExpressionHandler();
        handler.setPermissionEvaluator(aclPermissionEvaluator);
        handler.setPermissionCacheOptimizer(
                new AclPermissionCacheOptimizer(aclService));
        return handler;
    }
}
~~~

The snippet assumes the corresponding Spring imports and \`AclPermissionEvaluator\`/\`AclService\` beans are already declared; it is not a standalone Spring Boot application. Verify the API/configuration against your **actual Spring Security version**, cache, and \`LookupStrategy\`. Creating the optimizer alone does not guarantee fewer queries if the evaluator does not share the same cache mechanism, if object identities/SIDs are mapped inconsistently, or if another repository layer still queries per item.

Even when ACL cache optimization succeeds, \`@PostFilter\` still filters **after loading data** and still does not fix broken pagination caused by filtering after \`LIMIT/OFFSET\`. For paginated list/search APIs, prefer authorized queries at the data layer or design a permission projection verified to be equivalent.

### 6.2. Caching Does Not Replace Tenant Scoping

ACL caches typically key on \`ObjectIdentity\`, SID, and information used by the lookup strategy. If IDs are only unique per tenant, you need a tenant-isolated identity model so the same ID does not collide between tenant A and B. You must also manage invalidation when grants are issued/revoked, membership/roles change, or object state/owner changes. Long TTLs or stale \`ALLOW\` entries can become access-control vulnerabilities.

Never cache decisions using only \`documentId\` as the key; at minimum the key depends on **actor or SID/authority**, tenant, object identity, action, policy version, and time if expiry applies. If cache correctness is hard to prove, prefer request-scoped caching and reading authoritative data from the database.

## 7. Standalone Java 17 Example: Counting Round-Trips Before and After Batching

The following program simulates a database with in-memory lists while counting each repository call as **one query**. It demonstrates the \`1 + N\` vs \`1 + 1\` principle and **does not replace real SQL benchmarks**. Both algorithms apply a simple policy: a user may only read a document in the target tenant if they are the owner or have a READ share.

~~~java
import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

public class NPlusOneAuthorizationDemo {
    record Document(long id, long tenantId, long ownerId) {}
    record Grant(long tenantId, long documentId, long recipientId) {}

    static class FakeStore {
        private final List<Document> documents;
        private final List<Grant> grants;
        int queries;

        FakeStore(List<Document> documents, List<Grant> grants) {
            this.documents = documents;
            this.grants = grants;
        }

        List<Document> loadCandidates(long tenantId) {
            queries++;
            return documents.stream()
                    .filter(d -> d.tenantId() == tenantId)
                    .toList();
        }

        boolean hasGrant(long tenantId, long documentId, long userId) {
            queries++;
            return grants.stream().anyMatch(g ->
                    g.tenantId() == tenantId
                    && g.documentId() == documentId
                    && g.recipientId() == userId);
        }

        Set<Long> loadGrantedIds(
                long tenantId, Set<Long> documentIds, long userId) {
            queries++;
            return grants.stream()
                    .filter(g -> g.tenantId() == tenantId
                            && g.recipientId() == userId
                            && documentIds.contains(g.documentId()))
                    .map(Grant::documentId)
                    .collect(Collectors.toSet());
        }
    }

    static List<Long> naive(FakeStore db, long tenantId, long userId) {
        List<Document> candidates = db.loadCandidates(tenantId);
        return candidates.stream()
                .filter(d -> {
                    boolean shared = db.hasGrant(tenantId, d.id(), userId);
                    return d.ownerId() == userId || shared;
                })
                .map(Document::id)
                .toList();
    }

    static List<Long> batched(FakeStore db, long tenantId, long userId) {
        List<Document> candidates = db.loadCandidates(tenantId);
        Set<Long> ids = candidates.stream()
                .map(Document::id)
                .collect(Collectors.toSet());
        Set<Long> sharedIds = ids.isEmpty()
                ? Set.of()
                : db.loadGrantedIds(tenantId, ids, userId);
        return candidates.stream()
                .filter(d -> d.ownerId() == userId
                        || sharedIds.contains(d.id()))
                .map(Document::id)
                .toList();
    }

    public static void main(String[] args) {
        List<Document> documents = List.of(
                new Document(101, 10, 7),
                new Document(102, 10, 8),
                new Document(103, 10, 9),
                new Document(104, 10, 8),
                new Document(105, 10, 9),
                new Document(106, 20, 7));
        List<Grant> grants = List.of(
                new Grant(10, 102, 7),
                new Grant(10, 104, 7),
                new Grant(20, 106, 7));

        FakeStore slow = new FakeStore(documents, grants);
        FakeStore fast = new FakeStore(documents, grants);
        List<Long> first = naive(slow, 10, 7);
        List<Long> second = batched(fast, 10, 7);

        if (!first.equals(List.of(101L, 102L, 104L))
                || !first.equals(second)
                || slow.queries != 6
                || fast.queries != 2) {
            throw new AssertionError("Authorization or query count mismatch");
        }

        System.out.println("Authorized IDs: " + second);
        System.out.println("Naive queries: " + slow.queries);
        System.out.println("Batch queries: " + fast.queries);
    }
}
~~~

Save as \`NPlusOneAuthorizationDemo.java\` and use JDK 17 or higher:

~~~bash
javac --release 17 NPlusOneAuthorizationDemo.java
java NPlusOneAuthorizationDemo
~~~

Expected output:

~~~text
Authorized IDs: [101, 102, 104]
Naive queries: 6
Batch queries: 2
~~~

Explanation: in tenant 10 there are 5 documents; \`naive\` calls \`loadCandidates\` once and \`hasGrant\` five times (1 + 5 = 6). \`batched\` calls \`loadCandidates\` once and \`loadGrantedIds\` once for all IDs (2). User 7 owns 101 and is shared 102 and 104; document 106 belongs to tenant 20 so even though it has a grant, it does not appear. The results and order of both algorithms match.

**Intentional limitation of the demo:** both algorithms load candidates before filtering in memory so we can compare query counts. For **paginated list APIs or large document volumes**, filter permissions at the database **before** pagination as in section 4; do not copy the demo technique directly into production. Production must also enforce membership, expiry, revocation, action, repository errors, and transactions.

## 8. Supporting Techniques and Limitations

### 8.1. ORM Fetching Does Not Automatically Cure Evaluator N+1

If repeated SQL comes from accessing lazy associations such as \`document.owner\` or \`document.memberships\`, consider DTO projections, \`@EntityGraph\`, fetch joins for appropriate associations, or Hibernate batch fetching. However:
- \`JOIN FETCH\` on a \`@OneToMany\` collection combined with pagination can cause Cartesian multiplication, warnings, or in-memory pagination; check how the ORM handles it.
- Enabling \`hibernate.default_batch_fetch_size\` helps some lazy associations, **but does not** automatically turn N calls to a custom repository inside \`PermissionEvaluator\` into one query.
- Eagerly loading every ACL/SID for every document can inflate data volume, memory usage, and SQL joins dramatically.
- Projections and batches must enforce tenant boundaries and never expose confidential fields to unauthorized code or responses.

### 8.2. Remote PDP or Authorization Service

If each object makes an HTTP call to a policy decision point, optimize with a check-many API or a bounded "authorized IDs" query, combined with retries/circuit breakers as required by the business. Send consistent context per decision: subject, tenant, action, resource attributes, policy version. If the batch API omits an ID in its response, **never default to ALLOW**; fail closed on missing or errored decisions. Measure network request count, p95/p99 latency, and payload size.

### 8.3. Single-Object Checks Remain Independent

GET/PUT/DELETE endpoints for a single document must still enforce authorization before revealing or modifying the object. Optimizing the list endpoint does not mean you can drop \`@PreAuthorize\` or service-level checks on write operations. Avoid having the controller load the entire entity and confidential relationships before calling \`hasPermission\` when you can verify ID/tenant before fetching.

### 8.4. Reduce Overfetching and Avoid Queries Inside Serializers

After authorizing, map to a DTO that already contains the required columns. Do not let Jackson or a mapper traverse lazy associations per item and recreate N+1 during serialization. For large lists, use right-sized projections and fetch permission flags in the query or batch; never let a serializer invoke \`PermissionEvaluator\`.

## 9. Measuring Properly Before and After Optimization

To prove improvement, keep the dataset, principal, tenant, policy version, cache state, and page size fixed. Measure:

| Metric | Meaning |
|---|---|
| SQL statement count/request | Signal of N+1, especially as N grows. |
| Number of ACL lookups / cache hits | Separates query reduction due to batching from a warm cache. |
| DB time, query plan, rows read | One very heavy query is not automatically better than several light ones. |
| Request p50/p95/p99 and throughput | Real impact on users and the system. |
| Connection pool wait, GC, and heap | Impact of loading full collections and ACLs. |
| Authorized IDs and count | Confirms optimization did not alter security behavior. |

You can enable Hibernate SQL logging in test environments or collect statement counts via Hibernate Statistics / a data source proxy. Separate queries for loading documents, memberships, ACLs, lazy associations, and counts to pinpoint the source of N+1. Duplicate queries in logs do not prove N+1 if they come from different requests; attach a request/test correlation ID.

Example directional test expectation (not a measured benchmark):

~~~text
N=10:  baseline ACL queries ~10; batched ACL queries ~1
N=100: baseline ACL queries ~100; batched ACL queries ~1
N=500: baseline ACL queries ~500; batched ACL queries ~ceil(500 / B)
~~~

The deciding factor is the **slope with respect to N**. Even if the base query count exceeds 1 due to membership checks or count queries, the per-item ACL growth should disappear or grow only per chunk when batching. With SQL that filters permissions before pagination, statement count usually stays independent of page N, though internal database cost must still be optimized via indexes/plans.

## 10. Permission and Performance Test Matrix

An optimization is only acceptable when ALLOW/DENY results match the prior version across all critical scenarios:

| Scenario | Expectation | Evidence |
|---|---|---|
| Owner in tenant A | ALLOW READ | ID present in list, right object. |
| User with non-expired READ share | ALLOW READ | Grant is readable when \`expires_at > now\`. |
| Non-owner, no grant, PRIVATE | DENY | No ID returned, excluded from count. |
| User in tenant B with same ID | DENY | Does not leak into tenant A list/cached result. |
| ADMIN A and ADMIN B | Only ADMIN A has access in A | Role scope checked properly. |
| Revoked share | DENY immediately after revoke | Cache invalidated or stale decision not kept. |
| Grant expiring exactly at \`now = expiresAt\` | DENY | Fixed Clock, boundary condition tested. |
| VIEWER has WRITE grant while EDIT policy requires EDITOR | DENY EDIT | Does not conflate grant with role. |
| ACL with deny ACE and allow grant | Matches engine semantics | Batch and single \`AclService\` make same decision. |
| Parent ACL / inheritance | Matches actual config | Same SID/permission mask, parent not skipped. |
| Page size 20, many unauthorized items | Receives up to page limit of valid items | Filtered before pagination, accurate total/count. |
| Empty batch request or missing ACL | No error, never auto-ALLOW | No invalid \`IN ()\` query; fail closed. |
| Mutation denied after share change | Database unchanged | Prevents flawed time-of-check/time-of-use. |

### 10.1. A Meaningful Query-Count Test

1. Seed at least 2 tenants, 1 principal, 100 documents, unevenly distributed grants (owner, shared, private), and a fixed Clock timestamp.
2. Run the same endpoint/permission set with N=10 and N=100; reset counters and control warm/cold cache before each measurement.
3. Assert the exact list of IDs against an oracle defined by the fixture rather than deriving expected values from \`PermissionEvaluator\`.
4. Assert ACL/query count grows per **chunk** rather than per document; do not hardcode total request queries if the framework runs legitimate auxiliary queries.
5. For \`Page\`, verify content, \`totalElements\`, ordering, next page, and tenant isolation; run tests before and after revocation on the same dataset.
6. Use query plans/metrics to confirm a set-based SQL query does not perform full table scans as data grows.

Never test performance with just one document or only a warm cache: neither proves N+1 was eliminated on the cold-cache path.

## 11. Safe Change Plan for Existing Applications

**Step 1 — Locate the exact query-causing loop.** Mark the endpoint and method security boundaries. Capture logs for one request with N documents; determine whether duplicate SQL comes from \`PermissionEvaluator\`, \`AclService\`, Hibernate lazy associations, or an HTTP PDP. Do not assume caching is the cause by default.

**Step 2 — Choose the approach based on data semantics.** For paginated list/search, prefer pushing authorization predicates into the repository and count queries. For small/bounded lists computing permission flags, prefer batch prefetch. For full Spring ACL, use \`readAclsById\`/optimizer + semantically sound caching, or design an ACL projection proven equivalent by tests.

**Step 3 — Keep decisions consistent.** Membership, tenant, owner, action, expiry, revocation, deny ACEs, and parent ACLs must produce identical results before and after. Never send unauthorized records to the client to filter in the UI.

**Step 4 — Add instrumentation and regression tests.** Query counters, p95 latency, auth matrices, and pagination tests are your evidence. Run on data with realistic allow/deny ratios; evaluate results under cold cache and when memberships/shares change.

**Step 5 — Monitor operations.** Set alerts on SQL statement counts, list endpoint latency, ACL cache miss counts, and slow queries. When the slope rises again, check whether new code added \`hasPermission\` or lazy-association mapper access inside a loop.

## 12. Checklist and Reference Links

Before concluding N+1 has been eliminated, verify: (1) repeated queries were measured; (2) lists enforce authorization before pagination when returning a Page; (3) count uses the same predicate; (4) batching scopes tenant/user/action/IDs and handles empty collections; (5) the ACL engine preserves allow/deny, SIDs, and inheritance; (6) caches invalidate when permissions change; (7) tests cover cross-tenant, revoked, expired, owner, role, deny, and Page; (8) performance improves as N grows under controlled cache conditions; and (9) write operations still check permissions at the execution boundary.

Related Spring Security documentation:
- Method Security, especially \`@PostFilter\`: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Domain Object Security (ACLs): https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html
- \`PermissionEvaluator\` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionEvaluator.html
- \`AclService\` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/AclService.html
- \`PermissionCacheOptimizer\` API: https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/access/PermissionCacheOptimizer.html

**Technical takeaway:** checking permissions on N objects does not have to require N round-trips. For list/search, push permission predicates down to the database before pagination; for bounded collections or full ACLs, load ACLs/grants in batches and cache with proper scope. An optimization truly succeeds only when **query count drops, pagination results are accurate, and permission boundaries remain unchanged**.