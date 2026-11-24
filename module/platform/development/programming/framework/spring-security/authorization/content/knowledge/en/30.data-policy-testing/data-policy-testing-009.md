# Testing Cross-Tenant Cache Isolation and Effective State After Permission Changes

## 1. Objective and Scope

In a multi-tenant application, **caches must keep each tenant's data isolated**, and **access permissions must be checked against the active policy state at read time**. A cache that improves performance yet mixes data scopes or enforces stale permissions causes data leaks.

After this lesson, you will:

1. Construct a scenario where two tenants share the same document ID with different payloads, and test that no **cross-tenant cache leak** occurs.
2. Verify **cache hits do not bypass authorization**: an unauthorized user is still denied even when another user has already warmed the cache.
3. Verify **permission revocation** after the cache is warmed: subsequent reads are denied under a policy requiring immediate effect.
4. Verify **permission grants** after a denied read: fresh reads succeed once the new permission takes effect.
5. Verify tenant independence, repository invocation counts, and the limits of permission caching, TTLs, eviction, and multi-instance deployments.

This lesson belongs to **Data and Policy Testing** in **Spring Security – Authorization**. Examples use Java 17+, Spring Boot 3.5.7, Spring Security 6.x, Spring Cache, and JUnit 5; these are **service-layer** tests without an HTTP controller or real database.

## 2. Two Independent Bugs to Catch

### 2.1. Cross-Tenant Data Mixing

Suppose **tenant acme** and **tenant beta** both have a document with ID = **same-id**:

| Tenant | Document ID | Actual Content |
| --- | --- | --- |
| acme | same-id | ACME: private |
| beta | same-id | BETA: private |

If the cache key uses only **documentId**, loading acme first can cause a valid query for beta to wrongly receive acme's content. Even though the caller **is authorized for beta**, that is still a cross-tenant data leak.

**A proper cache key must contain tenantId and every dimension affecting the output.** In this example, the cached method accepts two parameters `(tenantId, documentId)` and lets Spring Cache generate its default **SimpleKey(tenantId, documentId)**. When multiple parameters are passed, the default key includes all of them. Always re-check keys if you configure a custom **key=...**, supply a custom KeyGenerator, or change method signatures.

### 2.2. Stale Permissions After Grant/Revoke

A document may be validly cached while a user holds permission. If permission is later **revoked**, that user must not use a cache hit to bypass the permission check.

Distinguish two kinds of caches:

- **Data cache**: caches document payloads; safe to share within a tenant only if every retrieval passes an active authorization check.
- **Authorization decision cache**: caches **allow/deny** outcomes. When caching decisions, you must enforce controlled invalidation/policy versioning/TTLs; keying a data cache properly does not by itself make permission changes visible.

An easily testable architecture looks like this:

~~~text
Authenticated caller
        |
        v
SecureDocumentService.read(tenantId, documentId)
        |
        v
@PreAuthorize checks current permission by user + tenant + document
        |
        +---- DENY ----> AccessDeniedException; data source not called
        |
        v
CachedDocuments.get(tenantId, documentId)
        |
        +---- CACHE HIT ----> Returns tenant-scoped data
        |
        +---- CACHE MISS ---> DocumentRepository.find(tenantId, documentId)
~~~

Place `@PreAuthorize` on a **dedicated facade** wrapping the `@Cacheable` data-reading bean. That guarantees every public service call goes through authorization before touching the cache. Do not rely on advisor ordering when placing method security and caching on the **exact same method**.

> **Intentional assumption of this test suite:** every grant/revoke change in the sample permission store takes effect immediately, with no decision cache. Real systems using policy engines, database replication, JWTs, or asynchronous invalidation messages must be tested against their actual consistency contract rather than assuming every network update takes effect instantaneously.

## 3. Mandatory Test Matrix

| Scenario | Precondition | Action | Expected |
| --- | --- | --- | --- |
| Same ID, two tenants | alice can read documents in both acme and beta | Read acme → beta → repeat | Each tenant returns its own content; exactly one cache miss per tenant |
| Cache warmed by another user | bob can read beta; alice cannot read beta | Bob reads beta → alice reads beta | Alice gets AccessDeniedException and receives zero data |
| Revoke after cache hit | alice has read permission on acme | Alice reads acme → revoke → read again | Subsequent read is denied; no extra source query |
| Grant after DENY | alice lacks read permission on acme | Read blocked → grant → read again | Fresh read returns correct data; source queried exactly once |
| Revoke only one tenant | alice has acme and beta access, both cached | Revoke acme → read acme and beta | Acme is blocked; beta remains readable; zero cache crossover |

Every test should **assert payload contents**, **assert allow/deny status**, and **assert source query counts** where applicable. Asserting only the absence of exceptions will not detect cross-tenant cache mixing.

## 4. End-to-End Runnable Maven Example

Create the project with this layout:

~~~text
tenant-cache-authz/
├── pom.xml
├── src/main/java/com/example/cacheauth/
│   ├── CacheSecurityApplication.java
│   ├── ResourceKey.java
│   ├── Document.java
│   ├── DocumentRepository.java
│   ├── Permissions.java
│   ├── CachedDocuments.java
│   └── SecureDocumentService.java
└── src/test/java/com/example/cacheauth/
    └── CacheAuthorizationTest.java
~~~

### 4.1. Dependencies

**pom.xml**:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>tenant-cache-authz</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-security</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-cache</artifactId>
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

**CacheSecurityApplication.java**: enables method security and caching. The example uses **ConcurrentMapCacheManager** so tests run without Redis or network connections.

~~~java
package com.example.cacheauth;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
@EnableCaching
public class CacheSecurityApplication {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("documents");
    }

    public static void main(String[] args) {
        SpringApplication.run(CacheSecurityApplication.class, args);
    }
}
~~~

**ResourceKey.java**: key used in the simulated data source and permission store; Java records automatically implement equals/hashCode across both fields.

~~~java
package com.example.cacheauth;

record ResourceKey(String tenantId, String documentId) {
}
~~~

**Document.java**:

~~~java
package com.example.cacheauth;

public record Document(String tenantId, String documentId, String body) {
}
~~~

**DocumentRepository.java**: tenant-isolated in-memory data source. The **fetchCount** counter tracks actual repository hits (cache hits do not increment it).

~~~java
package com.example.cacheauth;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Repository;

@Repository
public class DocumentRepository {

    private final Map<ResourceKey, Document> data = new ConcurrentHashMap<>();
    private final Map<ResourceKey, AtomicInteger> fetches = new ConcurrentHashMap<>();

    public void put(String tenantId, String documentId, String body) {
        ResourceKey key = new ResourceKey(tenantId, documentId);
        data.put(key, new Document(tenantId, documentId, body));
    }

    public Document find(String tenantId, String documentId) {
        ResourceKey key = new ResourceKey(tenantId, documentId);
        fetches.computeIfAbsent(key, k -> new AtomicInteger()).incrementAndGet();
        return data.get(key);
    }

    public int fetchCount(String tenantId, String documentId) {
        AtomicInteger count = fetches.get(new ResourceKey(tenantId, documentId));
        return count == null ? 0 : count.get();
    }

    public void reset() {
        data.clear();
        fetches.clear();
    }
}
~~~

**Permissions.java**: simulated policy source. Permission is identified by the triple `(username, tenantId, documentId)`. Every `canRead` call reads the **current** permission set without caching allow/deny.

~~~java
package com.example.cacheauth;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component("permissions")
public class Permissions {

    private record Grant(String username, String tenantId, String documentId) {
    }

    private final Set<Grant> grants = ConcurrentHashMap.newKeySet();

    public boolean canRead(String username, String tenantId, String documentId) {
        return grants.contains(new Grant(username, tenantId, documentId));
    }

    public void grant(String username, String tenantId, String documentId) {
        grants.add(new Grant(username, tenantId, documentId));
    }

    public void revoke(String username, String tenantId, String documentId) {
        grants.remove(new Grant(username, tenantId, documentId));
    }

    public void reset() {
        grants.clear();
    }
}
~~~

**CachedDocuments.java**: caches data only. **Never** use a key containing only documentId.

~~~java
package com.example.cacheauth;

import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CachedDocuments {

    private final DocumentRepository repository;

    public CachedDocuments(DocumentRepository repository) {
        this.repository = repository;
    }

    // Two parameters -> default cache key SimpleKey(tenantId, documentId).
    @Cacheable(cacheNames = "documents")
    public Document get(String tenantId, String documentId) {
        return repository.find(tenantId, documentId);
    }
}
~~~

**SecureDocumentService.java**: access-controlled document read entry point. The expression uses **#p0** and **#p1**, avoiding dependence on whether compilation preserves Java parameter names.

~~~java
package com.example.cacheauth;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class SecureDocumentService {

    private final CachedDocuments cachedDocuments;

    public SecureDocumentService(CachedDocuments cachedDocuments) {
        this.cachedDocuments = cachedDocuments;
    }

    @PreAuthorize("@permissions.canRead(authentication.name, #p0, #p1)")
    public Document read(String tenantId, String documentId) {
        return cachedDocuments.get(tenantId, documentId);
    }
}
~~~

Because **SecureDocumentService** and **CachedDocuments** are two distinct Spring beans, calls from the facade to the caching bean pass through the `@Cacheable` proxy. Permissions are checked before calling the caching bean; a cache hit never bypasses the `read` method's interceptor.

In real applications, a client-supplied tenantId must be cross-checked against the login session's tenant or the set of tenants the principal is authorized to access. The `canRead` method in this example achieves this by requiring an **exact grant across all three dimensions**, never trusting tenantId in isolation.

## 5. Integration Test Suite with Spring Security and Spring Cache

**CacheAuthorizationTest.java**: tests run with a real Spring context, real security proxy beans, real cache beans, and in-memory fixtures. **@WithMockUser** sets the current user. Each test clears the cache and resets the data/permission stores to prevent execution-order dependencies.

~~~java
package com.example.cacheauth;

import java.util.List;
import java.util.Objects;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.cache.CacheManager;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContext;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.test.context.support.WithMockUser;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.NONE)
class CacheAuthorizationTest {

    @Autowired private SecureDocumentService service;
    @Autowired private DocumentRepository repository;
    @Autowired private Permissions permissions;
    @Autowired private CacheManager cacheManager;

    @BeforeEach
    void arrange() {
        Objects.requireNonNull(cacheManager.getCache("documents")).clear();
        repository.reset();
        permissions.reset();

        repository.put("acme", "same-id", "ACME: private");
        repository.put("beta", "same-id", "BETA: private");
    }

    @Test
    @WithMockUser(username = "alice")
    void sameDocumentIdMustStayIsolatedAcrossTenants() {
        permissions.grant("alice", "acme", "same-id");
        permissions.grant("alice", "beta", "same-id");

        assertEquals("ACME: private",
                service.read("acme", "same-id").body());
        assertEquals("BETA: private",
                service.read("beta", "same-id").body());

        // Second read must be a cache hit for the right tenant.
        assertEquals("ACME: private",
                service.read("acme", "same-id").body());
        assertEquals("BETA: private",
                service.read("beta", "same-id").body());

        assertEquals(1, repository.fetchCount("acme", "same-id"));
        assertEquals(1, repository.fetchCount("beta", "same-id"));
    }

    @Test
    @WithMockUser(username = "alice")
    void otherUserCannotReadAlreadyCachedTenantDocument() {
        permissions.grant("bob", "beta", "same-id");

        // Bob calls the facade directly to warm beta's cache.
        assertEquals("BETA: private",
                readAs("bob", "beta", "same-id").body());

        // Alice lacks permission; a warm cache must still not leak data.
        assertThrows(AccessDeniedException.class,
                () -> service.read("beta", "same-id"));
        assertEquals(1, repository.fetchCount("beta", "same-id"));
    }

    @Test
    @WithMockUser(username = "alice")
    void revokeTakesEffectEvenAfterCacheWasWarmed() {
        permissions.grant("alice", "acme", "same-id");
        assertEquals("ACME: private",
                service.read("acme", "same-id").body());
        assertEquals(1, repository.fetchCount("acme", "same-id"));

        permissions.revoke("alice", "acme", "same-id");

        assertThrows(AccessDeniedException.class,
                () -> service.read("acme", "same-id"));
        // Denied before reaching cache/repository, even though data stays cached.
        assertEquals(1, repository.fetchCount("acme", "same-id"));
    }

    @Test
    @WithMockUser(username = "alice")
    void newGrantTakesEffectAfterPreviousDenial() {
        assertThrows(AccessDeniedException.class,
                () -> service.read("acme", "same-id"));
        assertEquals(0, repository.fetchCount("acme", "same-id"));

        permissions.grant("alice", "acme", "same-id");

        assertEquals("ACME: private",
                service.read("acme", "same-id").body());
        assertEquals(1, repository.fetchCount("acme", "same-id"));
    }

    @Test
    @WithMockUser(username = "alice")
    void revokingOneTenantDoesNotRemoveAnotherTenantsPermission() {
        permissions.grant("alice", "acme", "same-id");
        permissions.grant("alice", "beta", "same-id");
        service.read("acme", "same-id");
        service.read("beta", "same-id");

        permissions.revoke("alice", "acme", "same-id");

        assertThrows(AccessDeniedException.class,
                () -> service.read("acme", "same-id"));
        assertEquals("BETA: private",
                service.read("beta", "same-id").body());

        assertEquals(1, repository.fetchCount("acme", "same-id"));
        assertEquals(1, repository.fetchCount("beta", "same-id"));
    }

    // Switch principal for a single call; always restore alice.
    private Document readAs(String username, String tenantId, String documentId) {
        SecurityContext previous = SecurityContextHolder.getContext();
        try {
            SecurityContext context = SecurityContextHolder.createEmptyContext();
            context.setAuthentication(
                new UsernamePasswordAuthenticationToken(
                    username,
                    "unused",
                    List.of(new SimpleGrantedAuthority("ROLE_USER"))
                )
            );
            SecurityContextHolder.setContext(context);
            return service.read(tenantId, documentId);
        } finally {
            SecurityContextHolder.setContext(previous);
        }
    }
}
~~~

### Why Do These Assertions Prove What Needs Testing?

- **Two tenants sharing an ID:** if someone changes `@Cacheable` to key only by documentId, reading beta after acme risks wrongly returning **ACME: private**. Body assertions catch this regression even when both calls are allowed.
- **Bob warms, Alice is blocked:** tests prove authorization evaluates the **current caller**, not the first user who populated the cache. A fetch count of 1 confirms the entry was cached before Alice attempted her read.
- **Revoke:** tests prove policy lookup stays active when the data cache is warm; repository fetch count does not rise on the blocked request.
- **Grant:** tests prove denials are not permanently stuck in the data cache or sample policy. After granting, a new request is evaluated and proceeds.
- **Tenant isolation after revocation:** altering one tenant's permission does not affect readability in another tenant.

`readAs` only simulates Bob invoking the service within the **same test** to warm the cache before Alice accesses it. It always restores `SecurityContext` in a **finally** block to avoid polluting other tests.

## 6. Running Tests and Regression Verification

In the directory containing `pom.xml`, using JDK 17+ and Maven:

~~~bash
java -version
mvn -version
mvn test
~~~

When all code and dependencies are wired properly, expect **5 tests run, 0 failures, 0 errors**. Spring context startup logs may vary across environments.

Two useful mutations to verify test strength yourself:

**Mutation A – break the cache key**: edit `CachedDocuments`:

~~~java
@Cacheable(cacheNames = "documents", key = "#p1") // WRONG: documentId only
public Document get(String tenantId, String documentId) {
    return repository.find(tenantId, documentId);
}
~~~

Now **sameDocumentIdMustStayIsolatedAcrossTenants** must FAIL: acme's cache entry can be served as beta's content. Restore the default `@Cacheable` afterward.

**Mutation B – remove facade authorization**: temporarily remove `@PreAuthorize` on `SecureDocumentService.read`. **otherUserCannotReadAlreadyCachedTenantDocument**, **revokeTakesEffectEvenAfterCacheWasWarmed**, **newGrantTakesEffectAfterPreviousDenial** (and the deny branch of the final test) will FAIL because `AccessDeniedException` is missing. Restore the annotation immediately after the experiment.

Do not rely on elapsed wall-clock timing (milliseconds) to prove cache hits; the `fetchCount` counter is far more reliable and deterministic in CI than timing-based tests.

## 7. If the System Also Caches Authorization Decisions

The runnable example above **does not cache canRead**. If a real system caches policy decisions for performance, it needs an explicit freshness contract—especially for revocations.

### 7.1. Permission Decision Keys and Invalidation Timing

A decision cache typically needs at least:

~~~text
decisionKey = (subjectId, tenantId, resourceId, action, policyVersion)
~~~

Additional dimensions may include org/role, scopes, resource attributes, and environmental conditions (time, IP, risk level) if they actually affect the outcome. Avoid keying solely by username or solely by resourceId.

When permissions update, common options include:

1. **Do not cache decisions** for sensitive actions: each request reads current permissions from a policy source with suitable consistency guarantees.
2. **Evict/refresh affected decisions** when grant/revoke commits succeed; all relevant nodes/cache instances must receive invalidation notifications.
3. **Policy version / entitlement version**: keys or comparisons require the latest version, preventing decisions from older versions from being reused.
4. **Short TTL** if business requirements accept a quantified propagation delay; a TTL **does not prove** instant revocation and cannot replace expiration-window testing.

With Redis or a distributed cache, tests must verify **both the emitter of updates and the node holding old decisions**. Never call `Cache.clear()` manually inside a permission test; doing so hides the application's failure to invalidate automatically on permission changes.

### 7.2. Adding Tests for Async Propagation and Multiple Instances

If the product commits to revocations taking effect within at most **T seconds** after commit, tests must measure that contract:

~~~text
T0: User A has permission; request on instance-1 populates cache entry.
T1: Admin revokes permission; records commit / new policyVersion.
T2: Request from A hits instance-2, which holds stale decision cache.
Expected: after deadline T, every instance denies; before deadline T behavior
         matches the published consistency contract.
~~~

Use Redis/message-broker Testcontainers or an integration environment if the system uses them. Wait on a version/event acknowledgment or poll **with a deadline** instead of using fixed sleeps as proof of updated permissions. Add tests for **delayed, duplicate, out-of-order, or dropped events**; the system needs reconciliation/version checks or fail-closed handling matched to its risk level.

If permissions live inside **self-contained JWT roles/scopes**, revoking in the database does not automatically alter claims in already-issued tokens. Test against the intended mechanism: fresh tokens, introspection, revocation lists, entitlement versions, or token TTLs. Never expect tests using `@WithMockUser` to reflect the full real-world JWT pipeline.

## 8. Distinguishing Document Caches from Personalized Data Caches

A data cache keyed by `(tenantId, documentId)` is not always sufficient on its own:

| Cached Data Type | Minimum Key Components Typically Needed | Accompanying Conditions |
| --- | --- | --- |
| Base document identical for all authorized callers | tenantId, documentId | Every read checks current permission before returning data |
| Document field-filtered by role/user | tenantId, documentId, identity/role or policy version | Prevents lower-privileged users from receiving a higher role's cached copy |
| Search results filtered by permissions | tenantId, query/filter, principal/scope/policy version | Caches accurate result sets per user and permission state |
| Allow/deny decision | subject, tenant, resource, action, relevant version/policy | Invalidation/TTL per permission-freshness contract |

Beyond keys, verify **database tenant predicates** (e.g., `WHERE tenant_id = :tenantId AND id = :id`), connection separation/row-level security if used, and restricted direct access to `CachedDocuments`/`Repository`. Testing the facade does not replace checking all application entry points.

When **document content changes**, the data cache also needs eviction/refresh to avoid stale data; that is separate from authorization changes. Before adding `@CacheEvict` or overwriting cache entries, confirm the exact tenant + document key and update atomicity.

## 9. Common Mistakes When Writing Tests

| Mistake | Why It Is Dangerous | Fix |
| --- | --- | --- |
| Testing only one tenant | Misses colliding document IDs and key mixing | Create two tenants with the same ID and distinct bodies; assert each body |
| Cache key is documentId only | One tenant can retrieve another tenant's data | Include tenantId and all output-affecting dimensions in the key |
| Putting `@Cacheable` and auth on the same method without checking proxy/advisors | Risk of authorization skipping on cache hits depending on setup | Separate `@PreAuthorize` facade and `@Cacheable` bean; test warm cache + denied |
| Asserting only HTTP 403/exception | Unknown which queries ran or what body leaked | Assert return values, exceptions, and `fetchCount` |
| Failing to reset state between tests | Subsequent runs depend on earlier cache/permission state | Clear cache + reset permissions + seed fixtures in `@BeforeEach` |
| Testing revoke by clearing cache right before next read | Turns the case into a cache miss rather than testing a hot cache | Keep the data entry warm; modify only permissions |
| Caching permissions while tests mutate a Map directly | Fails to exercise the real invalidation path | Trigger the exact command/event production uses to update permissions |
| Assuming `@WithMockUser` represents real JWT/tenant resolution | Misses claims, tenant resolution, token expiry, revoked tokens | Add dedicated HTTP/JWT/identity-provider tests |
| Using arbitrary sleeps to wait for invalidation | Flaky tests that do not verify SLAs | Poll until version/condition with a deadline; use multi-instance tests |
| Mixing personalized data into a tenant-shared cache | Higher-role fields can leak to lower roles | Separate base data from authorized projections or expand cache key dimensions |

## 10. Acceptance Checklist

- [ ] Cache keys distinguish **tenantId + documentId**, even when two tenants share the same ID.
- [ ] Tests assert the exact **body for each tenant**, not merely the absence of exceptions.
- [ ] An unauthorized user is blocked **when the cache is already warm** from another user.
- [ ] **Revoke** causes the next read to be blocked per contract; cached data never bypasses authorization.
- [ ] **Grant** takes effect on the next read per contract.
- [ ] Revoking in tenant A does not accidentally affect tenant B.
- [ ] Tests verify repository hit counts to distinguish hits, misses, and denials.
- [ ] Dedicated tests cover decision-cache invalidation/versioning, JWTs, and multi-instance setups if used in production.
- [ ] Run **mvn test** and verify all tests pass; mutation checks catch broken cache keys and missing authorization.

## 11. References

- Spring Security, **Method Security**: https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Security, **Testing Method Security**: https://docs.spring.io/spring-security/reference/servlet/test/method.html
- Spring Framework, **Declarative Annotation-based Caching / Default Key Generation**: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework, **Cache Abstraction**: https://docs.spring.io/spring-framework/reference/integration/cache.html

**Technical takeaway:** verify two properties independently—**no cross-tenant data mixing** and **no use of expired/revoked permissions**. Using two tenants with colliding IDs, actors with distinct permissions, warmed caches, and explicit grant/revoke transitions uncovers flaws that "single successful read" tests routinely miss.