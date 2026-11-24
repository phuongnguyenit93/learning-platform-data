# Cache Keys by User, Organization, or Data Scope in Spring Cache

## Learning Objectives

After this lesson, you will be able to design a cache key that accurately reflects the **user**, **organization (tenant)**, and **permitted data scope**; distinguish shareable data from personalized data; avoid returning the wrong data across authorization boundaries; and ensure `@Cacheable`, `@CachePut`, and `@CacheEvict` operations use the same cache identity when needed. This lesson focuses on **key design** in Spring Cache. Examples use Java 17, Spring Boot 3.3, and an in-memory cache to observe behavior directly.

One principle to remember from the start: **caching is only a performance optimization mechanism, not an authorization boundary**. You must authenticate and check permissions before returning a result, even when the result is already in the cache. A proper key prevents results from two scopes from getting mixed together, yet does not by itself prove the caller is allowed access.

## 1. Identifying a Cache Entry

In Spring Cache, an entry is logically identified by the pair:

~~~text
(cacheName, key) -> cachedValue
~~~

`cacheName` specifies the storage region, while `key` is generated from the call by a `key` expression or `KeyGenerator`. For example, a method `readDocument(organizationId, userId, documentId)` returns content filtered by the viewer.

~~~text
viewerDocuments
├── (acme, alice, D1) -> Alice's view at Acme
├── (acme, bob,   D1) -> Bob's view at Acme
└── (beta, alice, D1) -> Alice's view at Beta
~~~

Three entries have the same `documentId = D1`, yet different organizations or users. If you only use `"D1"` as the key in the same `"viewerDocuments"` cache, a subsequent caller can receive the previous caller's result.

The crux is defining a mapping function:

~~~text
key = f(data identifier, context affecting the result)
~~~

Two invocations may share **the same key** only when the cached result is interchangeable under the business contract. If results can vary by tenant, user, access permissions, locale, filters, or policy version, those factors must be accounted for.

### Three Common Scopes

| Data kind | Example | Key components typically needed |
| --- | --- | --- |
| **Public, identical for everyone** | Public exchange rates at the same moment, public product category list | Resource identifier, plus locale/unit/version if impactful |
| **Shared within an organization** | Organization-wide display settings, reports independent of individual members | `organizationId` + resource identifier + impactful parameters |
| **Per-user or specific permission** | Personal homepage, filtered document list, export with hidden columns | `organizationId` + `userId` or appropriate permission fingerprint + resource identifier/filters |

`userId` is not always necessary: adding a user to a shared cache lowers the hit rate without improving correctness. Conversely, if the result genuinely differs per user and the key only contains `organizationId`, you risk mistakenly sharing results. **The scope of the key must match the scope of the returned data itself.**

## 2. Designing Keys for Multi-Tenant Systems

Suppose both Acme and Beta have a document with code `"D1"`.

~~~java
// Wrong when the cache name is shared and D1 can appear across multiple tenants.
// This is an illustrative snippet, not a standalone runnable program.
@Cacheable(cacheNames = "documents", key = "#p1")
public Document read(String organizationId, String documentId) {
    return repository.find(organizationId, documentId);
}
~~~

With calls `read("acme", "D1")` followed by `read("beta", "D1")`, the `#p1` expression returns `"D1"` both times. If the first call is cached, the next call can return the wrong data without executing `repository.find(...)`.

A simple approach is including both parameters in the key:

~~~java
// Illustration: fixed cache name, composite key from both arguments.
@Cacheable(cacheNames = "documents")
public Document read(String organizationId, String documentId) {
    return repository.find(organizationId, documentId);
}
~~~

When `key` is not declared, Spring's default `SimpleKeyGenerator` takes **all arguments**: with multiple arguments, Spring uses `SimpleKey`. In this example, `(acme, D1)` and `(beta, D1)` differ. However, if the method also receives data that does not affect the result such as traceId, different traceIds will needlessly create different keys; in that case, declare the identifying components explicitly.

Another approach is separating **cache names by tenant**, such as `"documents.acme"` and `"documents.beta"`, and using only `"D1"` within each region. This usually requires a `CacheResolver` and a naming/region-limit policy. With a large number of tenants, one stable region with a tenant-prefixed/composite key is usually easier to manage than creating thousands of regions. Whichever approach you choose, **reads, writes, and evictions** must target the exact same `(cacheName, key)`.

### Be Careful with Simple String Concatenation

~~~java
// Concise, yet safe only if identifiers cannot cause ambiguity.
@Cacheable(cacheNames = "documents", key = "#p0 + ':' + #p1")
~~~

If `organizationId="a:b", documentId="c"` and `organizationId="a", documentId="b:c"`, both produce `"a:b:c"`. Use length-prefixed component encoding, properly ruled escaping, or better yet an **immutable structured key type** such as a Java `record` when supported by the backend. Never use a bare integer `hashCode()` as identity because hash collisions can occur.

## 3. Per-User Keys When Results Are Personalized

Consider the method `getDashboard(orgId, userId, period)`. Two members of the same organization may see different metrics. A key with only `(orgId, period)` is insufficient, because `userId` directly affects the value.

~~~text
getDashboard("acme", "alice", "2026-11")
    -> (acme, alice, 2026-11)

getDashboard("acme", "bob", "2026-11")
    -> (acme, bob, 2026-11)
~~~

Including `userId` in the key makes sense when:

- The result contains personal attributes, individual settings, or differing visibility across users.
- The system does not have a shared permission group proven to produce **the exact same result**.
- A single user's personalized cache must be invalidated when that user's personalized data changes.

**Do not take a client-supplied user ID directly and treat it as authenticated.** The backend must derive the identity from a verified principal/session/token and verify that the user is authorized to access the requested organization, resource, and action. A parameter such as `requestedUserId` in an HTTP path is not proof of the caller's identity.

### One User Can Belong to Multiple Organizations

If user `"alice"` belongs to both Acme and Beta, the key `(alice, D1)` still risks colliding between the two organizations. `(orgId, userId, documentId)` is usually needed. Even when `userId` is globally unique, the current working context (`activeOrganizationId`) can still determine the data and must be reflected if the output depends on that organization.

Also clarify the case of **an administrator viewing on behalf of someone else**: should the key reflect the **requester**, the **data owner**, or both? The answer depends on whose context filters the content. Name variables clearly as `viewerId`, `ownerId`, and `subjectId` instead of an ambiguous `userId`.

## 4. Data Scope Also Includes Permissions, Filters, and Display Context

Tenant and user are often still not enough. Two calls from the same user can return different results if any of these factors change:

| Factor | When does it enter cache identity? | Example |
| --- | --- | --- |
| Permissions or policy | Output changes based on granted permissions or field redaction | `FULL` mode vs. `REDACTED`; `policyVersion` |
| Role/group | Role actually determines the exact subset of returned data | Reviewers see extra fields, readers do not |
| Filters and pagination | Changes the returned list or ordering | `status`, `sort`, `page`, `size` |
| Locale and timezone | They alter rendered content | Vietnamese/English versions; dates in local timezone |
| Feature flag/version | Processing or UI version returns different results | `projectionVersion=2` |
| Organization/region/branch | Data scope changes by context | `organizationId`, `branchId` |

A report example could use the cache identity:

~~~text
(
  namespace = "report:v2",
  organizationId = "acme",
  viewerId = "alice",
  permissionVersion = 7,
  reportId = "R1",
  statusFilter = "OPEN",
  page = 0,
  size = 20,
  locale = "vi-VN"
)
~~~

This is an **analytical example**, not a rule that every function needs all of these fields. Include only the fields that determine the result value. Parameters that do not affect the output such as `traceId`, `requestId`, loggers, or per-HTTP-request timestamps should normally be omitted from the key.

### Should Role Be Used Instead of userId?

Only if you prove every user with the same role sees the exact same dataset and redaction level. In many systems, two people with the same `"MANAGER"` role still differ in branch, project list, permission exceptions, or shared documents. The key `(orgId, role, documentId)` is then insufficient. For sensitive data or complex permissions, per-user keys are usually easier to reason about; however, **permissions must still be checked on every request**.

A `permissionFingerprint` or `policyVersion` only makes sense if computed from trusted permission state, updated when policies change, given stable semantics, and managed for expiration. Never trust role or permission strings self-reported by the client.

## 5. Cache Hits Can Bypass Permission Checks Placed Inside the Method

This is a dangerous design flaw:

~~~java
// COUNTER-EXAMPLE: do not use in a system with permission-scoped data.
// checkPermission inside the method body will not run on a cache hit.
@Cacheable(cacheNames = "documents", key = "#p0")
public Document read(String documentId) {
    checkCurrentUserCanRead(documentId);
    return loadDocument(documentId);
}
~~~

On a cache hit, `@Cacheable` normally returns the stored value **without executing the method body**. If the permission check lives only inside that body, the check can be skipped. Expanding the key to `(userId, documentId)` isolates results, yet **does not handle permission revocation by itself**: a user who was previously permitted can still hit old data after permissions are revoked unless a permission check runs every time.

### A Safer Flow Design

Separate a **per-call access check layer** from a bean that **caches authorized data**:

~~~text
HTTP / job / caller
       |
       v
Authenticate identity and organization context (trusted principal)
       |
       v
DocumentFacade
 - verify organization membership
 - check document read permission for this request
 - select valid viewer/organization/scope
       |
       v
ScopedDocumentCache (@Cacheable)
 - build key from verified scope
 - hit: return matching content
 - miss: fetch and build result
~~~

Only allow authorized entrypoints to call through the facade; do not expose the cached service directly as an API for unchecked requests. Test advice ordering carefully if combining `@PreAuthorize` with caching on **the same method**; do not rely on an implicit assumption that the authorization interceptor always runs before the cache interceptor. A separate facade layer keeps boundaries much clearer.

**At the same time, the data layer must still enforce tenant/permission boundaries when querying the source.** Cache keys prevent mixing data across calls, yet do not prevent a SQL query missing `tenant_id` from fetching the wrong rows from the database.

## 6. Runnable Java 17 Example: Isolating Organizations and Viewers

This example uses Spring Boot 3.3.5, Java 17, and `ConcurrentMapCacheManager` (a single-JVM cache). Two members of the same organization see separate results; a user with the same ID in another organization also gets a different key. The facade verifies the organization boundary **before every call**, even when data is already cached. In a real product, the facade must also check ACL/permissions on **each document**; the demo simulates organization membership checks only to stay focused on keys.

Project structure:

~~~text
scoped-cache-demo/
├── pom.xml
└── src/main/java/example/scopedcache/
    ├── DemoApplication.java
    ├── DocumentFacade.java
    └── ScopedDocumentCache.java
~~~

### `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>scoped-cache-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### `src/main/java/example/scopedcache/DemoApplication.java`

~~~java
package example.scopedcache;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableCaching
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("viewerDocuments");
    }

    // Method name is not in the key: read and evict share the same identity.
    @Bean("viewerDocumentKey")
    KeyGenerator viewerDocumentKey() {
        return (target, method, params) -> {
            if (params.length != 3
                    || !(params[0] instanceof String org)
                    || !(params[1] instanceof String viewer)
                    || !(params[2] instanceof String document)) {
                throw new IllegalArgumentException(
                        "Expected orgId, viewerId and documentId");
            }
            return new ScopeKey("v1", org, viewer, document);
        };
    }

    // Record is an immutable structural key; equals/hashCode are generated by Java.
    private record ScopeKey(String version, String orgId,
                            String viewerId, String documentId) {}

    @Bean
    CommandLineRunner demo(DocumentFacade facade) {
        return args -> {
            var aliceAcme = new DocumentFacade.Caller("alice", "acme");
            var bobAcme = new DocumentFacade.Caller("bob", "acme");
            var aliceBeta = new DocumentFacade.Caller("alice", "beta");

            System.out.println(facade.read(aliceAcme, "acme", "D1"));
            System.out.println(facade.read(aliceAcme, "acme", "D1"));
            System.out.println(facade.read(bobAcme, "acme", "D1"));
            System.out.println(facade.read(aliceBeta, "beta", "D1"));

            facade.invalidate(aliceAcme, "acme", "D1");
            System.out.println(facade.read(aliceAcme, "acme", "D1"));

            try {
                facade.read(aliceAcme, "beta", "D1");
            } catch (SecurityException expected) {
                System.out.println("DENIED: " + expected.getMessage());
            }
        };
    }
}
~~~

### `src/main/java/example/scopedcache/DocumentFacade.java`

~~~java
package example.scopedcache;

import org.springframework.stereotype.Service;

@Service
public class DocumentFacade {
    private final ScopedDocumentCache cache;

    public DocumentFacade(ScopedDocumentCache cache) {
        this.cache = cache;
    }

    // Demo: in a real application, Caller must come from an authenticated identity.
    public record Caller(String userId, String orgId) {}

    public String read(Caller caller, String requestedOrg,
                       String documentId) {
        authorize(caller, requestedOrg);
        // In production, also check the documentId ACL on every request.
        return cache.read(requestedOrg, caller.userId(), documentId);
    }

    public void invalidate(Caller caller, String requestedOrg,
                           String documentId) {
        authorize(caller, requestedOrg);
        cache.evict(requestedOrg, caller.userId(), documentId);
    }

    private void authorize(Caller caller, String requestedOrg) {
        if (caller == null || !caller.orgId().equals(requestedOrg)) {
            throw new SecurityException("organization mismatch");
        }
    }
}
~~~

### `src/main/java/example/scopedcache/ScopedDocumentCache.java`

~~~java
package example.scopedcache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ScopedDocumentCache {
    private final AtomicInteger loads = new AtomicInteger();

    @Cacheable(cacheNames = "viewerDocuments",
               keyGenerator = "viewerDocumentKey")
    public String read(String orgId, String viewerId, String documentId) {
        int number = loads.incrementAndGet();
        return orgId + "/" + viewerId + "/" + documentId
                + " -> load#" + number;
    }

    @CacheEvict(cacheNames = "viewerDocuments",
                keyGenerator = "viewerDocumentKey")
    public void evict(String orgId, String viewerId, String documentId) {
        // Demo only evicts the cache; source data does not change.
    }
}
~~~

Run inside the `scoped-cache-demo` directory using JDK 17+ and Maven:

~~~bash
mvn -q spring-boot:run
~~~

Besides Spring startup logs, `CommandLineRunner` prints these exact lines:

~~~text
acme/alice/D1 -> load#1
acme/alice/D1 -> load#1
acme/bob/D1 -> load#2
beta/alice/D1 -> load#3
acme/alice/D1 -> load#4
DENIED: organization mismatch
~~~

Explanation:

1. Alice/Acme's first call is a cache miss, runs `ScopedDocumentCache.read`, and stores key `(v1, acme, alice, D1)`.
2. Alice/Acme's second call hits so the counter does not increment, still returning `load#1`. **`DocumentFacade.authorize` is still invoked again before the cache hit**.
3. Bob/Acme generates key `(v1, acme, bob, D1)` and receives `load#2`.
4. Alice/Beta has the same `viewerId` and `documentId` yet a different `orgId`; generates a separate key and receives `load#3`.
5. Evicting Alice/Acme using **the same `cacheNames` and `KeyGenerator`** as read removes the exact entry; reading again returns `load#4`. Bob/Acme and Alice/Beta entries remain intact.
6. Alice belonging to Acme requesting Beta's data is blocked by the facade with `SecurityException`, before querying the cache.

`ScopeKey` is an immutable Java `record` with `equals()`/`hashCode()` matching its components. `"v1"` is an illustrative version namespace; incrementing the version requires a plan to clear old entries. `ConcurrentMapCacheManager` can use object keys directly in the JVM; Redis or distributed cache backends may require different conversion/serialization and do not automatically understand this record.

**Security limitations of the demo:** `Caller` is constructed manually for illustration, does not integrate Spring Security, and does not check per-document ACLs. In a real system, only let controllers/entrypoints go through the facade, build identity from an authenticated principal, verify real membership/ACLs, and restrict calling `ScopedDocumentCache` directly from unauthorized paths. The demo does not grant users permission to view all documents in an organization.

## 7. When to Use Default Keys, SpEL, or `KeyGenerator`?

Spring Cache defaults to `SimpleKeyGenerator` if the annotation declares neither `key` nor `keyGenerator`:

| Method | Logical default key | When appropriate? |
| --- | --- | --- |
| `get(String org, String id)` | `SimpleKey(org, id)` | Both parameters determine the result |
| `get(String org, String user, String id)` | `SimpleKey(org, user, id)` | Result is personalized per user |
| `get(String org, String user, String id, String traceId)` | `SimpleKey` of all four parameters | **Unsuitable** if traceId does not affect the result |
| `find(String id)` | The `id` object directly | Safe only if no data scope is omitted |

If parameters already match the identifying structure, writing a custom generator is unnecessary. However, if call signatures include extra arguments that do not affect the result, or require namespace normalization, a custom key is clearer.

### Using SpEL for Simple Cases

~~~java
// Illustrates a method whose permissions were already checked externally.
// Key depends on the first three parameters; requestId does not affect the data.
@Cacheable(
    cacheNames = "viewerDocuments",
    key = "T(java.util.List).of(#p0, #p1, #p2)"
)
public String read(String orgId, String viewerId, String docId,
                   String requestId) {
    return loadDocument(orgId, viewerId, docId);
}
~~~

`#p0`, `#p1`, `#p2` correspond to org, viewer, and document. `List.of` returns an immutable list with element-based `equals` and rejects `null`; identifiers must be validated/normalized beforehand. This is an **illustration of Spring Expression Language in an internal cache**, not a recommendation to use `List` directly as a key for every backend. `loadDocument`, repositories, and access control belong to the real application.

With multiple operations having different parameter orders, a `KeyGenerator` can explicitly extract the required fields; this approach builds a clear record key, yet **the generator in the runnable example requires exactly three parameters**. If you add a four-parameter `update(..., payload)` method, actively update the generator or use an explicit `key` so both operations produce **the same** `ScopeKey` from org/viewer/docId. Do not copy a three-parameter generator onto a four-parameter method and expect it to work.

**`key` and `keyGenerator` are mutually exclusive on the same annotation.** They only affect the key; selecting the cache name is handled by `cacheNames` or `CacheResolver`.

## 8. Permission Changes: Avoiding Right Key, Wrong Policy

Suppose Alice had permission to view the `salary` field. `readForViewer(acme, alice, D1)` stored a result containing that field in the cache. Later, Alice's permissions are downgraded.

- **Only `userId` in the key:** the old cache entry may still contain `salary`. If permissions are not re-checked on hit, that is a leak. Even when document read access remains, which fields must be redacted can change.
- **Adding `role` to the key:** may produce a new key if the role changes, yet is insufficient when permissions depend on teams, branches, individual ACLs, ABAC, or related data. Do not treat role as a complete permission fingerprint.
- **Adding a trusted `permissionVersion`:** when the version changes, keys move to a new value space; you still must update the version promptly and handle old entries.
- **Evict affected entries:** when permissions change, delete affected entries before they are reused; you may need to evict by user, document, tenant, or the entire region depending on key structure and provider.
- **Check permissions at the facade every time:** an essential safeguard for access control. For content cached under an old projection, you must still **not return** a projection containing fields that are no longer permitted.

TTL only limits entry age and **does not automatically make permission revocation take effect immediately**. Systems requiring immediate revocation must coordinate authorization, invalidation/versioning, and multi-instance synchronization policies.

### Permissions Changing While a Request Is In Flight

A race can occur between checking permissions and retrieving results from the cache or database. For sensitive workflows, define the required consistency guarantee: transactions, version checks, policy snapshots, a final check before returning results, or a mechanism rejecting data when permission versions mismatch. Cache key design is only one part of a consistency strategy.

## 9. Synchronizing Keys Across `@Cacheable`, `@CachePut`, and `@CacheEvict`

Establish a shared **cache identity** for reads and operations modifying the same data. In the runnable example, `read` and `evict` share the `(orgId, viewerId, documentId)` signature and the same generator, so they produce the exact same `ScopeKey`.

For an update method with an added payload:

~~~java
// Illustration: signature belongs to an application service, not a standalone program.
@CachePut(cacheNames = "viewerDocuments",
          key = "T(java.util.List).of(#p0, #p1, #p2)")
public ViewDto updateView(String orgId, String viewerId,
                          String documentId, UpdateRequest request) {
    return persistAndRender(orgId, viewerId, documentId, request);
}
~~~

This snippet aligns with the read method **only if the read method also uses the same `List.of(...)` key type**. It is **incompatible** with the `ScopeKey` record in the runnable example: same logical information yet different object types means the keys are not equal. Within an application, pick **one consistent key standard** and apply it across all related operations, including event-driven eviction methods.

Other notes:

- `@CachePut` always executes the method and puts the result into the cache; avoid updating another user's cached result without checking permissions.
- `@CacheEvict` can use `key` or `keyGenerator`; by default it evicts after the method completes successfully. `beforeInvocation=true` changes timing yet cannot fix a wrong key.
- `@CacheEvict(allEntries=true)` clears the entire region. For regions shared across users/tenants, this may wipe more entries than intended, though it does not leak data by itself.
- One document update can affect **multiple per-user projections**. Evicting only the editor's key may be insufficient; design multi-user invalidation, per-document versioning, combined TTL, or policy-based eviction.
- With multi-instance distributed caches, eviction must actually reach the shared cache store; per-JVM in-memory caches do not synchronize evictions across JVMs.

## 10. Protecting Information Inside the Cache Key Itself

Keys can appear in logs, dashboards, metrics, traces, or be serialized as physical key names in Redis. Therefore:

1. **Never put access tokens, passwords, session secrets, cookies, or raw sensitive data** into cache keys. Those values also change frequently, hurting hit rates.
2. Prefer stable internal identifiers that do not directly carry sensitive data. An opaque ID reduces exposure compared to emails/real names, though it does not create authorization by itself.
3. When Redis requires string keys, pick a clear, unambiguous codec with namespace/versioning. Check serializer rules and how the provider adds prefixes.
4. Avoid keys containing mutable objects, collections modifiable after insertion, or classes using address-based `equals/hashCode`. Immutable Java records are usually convenient for in-memory caches.
5. Do not log full cache keys when they contain user identities; log only safe metadata with appropriate reduced granularity and anonymization/redaction.
6. Do not use an unkeyed hash of secret data and assume the data is fully protected: small input spaces can be guessed and matched against hashes. Key/logging handling policies must match actual data sensitivity.

### Notes for Multi-Instance Deployments

The example's `ConcurrentMapCacheManager` stores data in **each JVM's memory**. It does not synchronize caches across replicas or provide per-entry TTL out of the box. With Caffeine, Redis, or other backends, serializer behavior, TTL, cache key conversion, capacity limits, and invalidation must be verified in practice. Using a Java record as an object key does not guarantee a distributed backend can serialize that record identically and stably.

## 11. Testing Mandatory Boundaries

Do not test only cache hits. A meaningful test suite should prove:

| Scenario | Condition | Expected outcome |
| --- | --- | --- |
| Same user, org, and resource | Alice/Acme/D1 called again | Hit, does not read the source again |
| Two users in the same org | Alice/Acme/D1 then Bob/Acme/D1 | Do not share an entry when views are personalized |
| Same user ID across two orgs | Alice/Acme/D1 then Alice/Beta/D1 | Do not share an entry |
| Cross-organization request | Caller from Acme requests Beta/D1 | Rejected **before** any cache hit |
| Permission revocation | User just lost read access to the document | Does not return data even if old entry still exists |
| Display permission change | Role/ACL/permission version changes | Does not return old projection with disallowed fields |
| Evict after update | Edit D1 then read again | Does not receive stale value for affected entry |
| Two different methods | Same cache name and same parameters | No semantic collision when outputs differ |
| Backend key serializer | Written on one instance, read on another | Keys interpreted consistently, no cross-tenant data leak |
| Cache failure/miss | Provider timeout or missing entry | System still enforces authentication and authorization properly |

For caches shared across multiple tenants, always include a test proving `(tenant A, id X)` and `(tenant B, id X)` do not point to the same entry. When permission-dependent outputs exist, add a test where a user's **permissions are revoked right before a call that would otherwise hit the cache**. A test that merely runs `@Cacheable` twice with the same arguments cannot catch scope leaks.

### Incident Troubleshooting

| Symptom | Possible cause | How to verify |
| --- | --- | --- |
| User A sees B's data | Key omits user, org, or permissions affecting the result | Compare full cacheName + key + scope across both calls |
| Different tenants get the same cache hit | ID is unique only per tenant; key lacks tenant | Add tenant or separate caches per tenant |
| Hits right user yet returns revoked field | Missing projection eviction/versioning by permission, or permission check only inside method body | Add per-request check and invalidation strategy |
| Very low cache hit rate | Key contains requestId, timestamp, or object without proper equals/hashCode | Remove parameters that do not affect the result |
| Eviction has no effect | Read/evict keys have different types, order, or cache names | Check record/List/string types and exact field order |
| Data mixes after switching organizations | Used userId without activeOrganizationId | Include verified organization scope in the key |
| Redis backend key conversion error | Object key only works in ConcurrentMap | Define serialization and test across multiple instances |
| Interceptor never runs | Missing `@EnableCaching`, self-invocation, or non-Spring-managed bean | Call via another bean/proxy and verify configuration |

## 12. Self-Check Exercises

**Exercise 1 — Organization report.** Function `getRevenue(String orgId, YearMonth month)` returns one shared report for every authorized member in the organization. Should `userId` be included in the key?  
**Answer:** Usually no, since content is not personalized. The key `(orgId, month)` suffices if all impactful parameters are accounted for. Whether the user is **allowed to call it** must still be checked separately every time.

**Exercise 2 — Document list.** Two employees share the `"EDITOR"` role in Acme, yet one only sees project X and the other only sees project Y. Can `(orgId, role, page)` be used?  
**Answer:** Insufficient. Role does not fully describe ACLs/projects; use a viewer-scoped key or a permission version/signature proven to represent exact access scope, alongside per-request authorization checks.

**Exercise 3 — Permission change.** Alice used to see a report with a salary column, and later her permissions changed. Is the key `(orgId, userId, reportId)` enough?  
**Answer:** Insufficient if the old entry still exists and the system does not verify permissions/content versions. Check permissions on every call and evict/re-key data when projections change; TTL only bounds the delay.

**Exercise 4 — Invalidation.** The read method uses `record ScopeKey(org, user, id)`, while the update method uses the string `org + ":" + user + ":" + id`. Is the same cache entry updated?  
**Answer:** No, because the key types and `equals` differ, even though the text looks similar. Use the exact same format, same `cacheName`, and same scope policy across related operations.

**Exercise 5 — Design question.** Why not use `SecurityContextHolder.getContext()` directly as the entire key?  
**Hint:** It is a context object that can hold unstable state, sensitive details, and has no guaranteed `equals/hashCode` matching data identity; in async/background contexts it may not even propagate. Extract only the **authenticated, result-affecting identifiers** into a stable key.

## References

- Spring Framework, Declarative Annotation-based Caching (`@Cacheable`, `KeyGenerator`, SpEL, proxy semantics): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework, Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Security, Method Security: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Boot, Caching Providers: https://docs.spring.io/spring-boot/reference/io/caching.html

**Takeaway:** a cache key must fully represent *the scope determining the output content*, typically including tenant and sometimes viewer/permissions. Authorization checks must run even on cache hits; read, update, and eviction paths must use the exact same identity. Cache isolation, authorization checks, and data query scoping must reinforce one another.
