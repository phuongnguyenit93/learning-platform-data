# Method Result Caching and Cross-User Data Leakage Risks

## 1. Problem: One Cache Key, Two Users

A service returns a document page whose data depends on the currently logged-in user:

- `alice` views document `#10` and sees her own personalized content.
- `bob` calls the same method with ID `10`.
- Both pass through a shared application cache.

If the method uses `@Cacheable(cacheNames = "documentViews", key = "#p0")`, the cache receives only the **document ID** as the key. `alice`'s call stores a result under key `10`; `bob`'s call can receive **`alice`'s exact result without executing the method body**, depending on where permission checks sit, how the result is built, and the call structure. This risks leaking data across principals/tenants even when the database retrieval logic itself is written correctly.

The issue is not that the cache knows the caller's permissions; **a cache is not an authorization system**. The cache looks up results by `cacheNames` and key. If the key does not capture every factor that changes the output, or if authorization is not checked on the cache-hit path, security boundaries can break.

This lesson helps you:

1. Understand `@Cacheable`, `@CachePut`, `@CacheEvict`, `@EnableCaching`, and the cache hit/miss lifecycle.
2. Distinguish cache keys by **arguments**, **user**, **tenant**, **permissions**, and **data version**.
3. Analyze the intersection of Spring Cache, Spring Method Security, and Spring AOP proxies.
4. Design a **secured facade checking permissions on every call** before using an internal cache.
5. Write a runnable Java 17+ Spring Boot example testing valid/invalid permissions, cache hits, and invalidation.
6. Identify which data can be cached shared, which must be separated per user, and which should avoid caching.

**Context:** Spring Security Method Security on Spring Boot / Spring Framework using AOP proxies; the demo uses `ConcurrentMapCacheManager` for easy observation. Redis/Caffeine deployments, multi-instance systems, and transactions require additional measures covered later.

## 2. What Does Spring Cache Actually Do?

When `@EnableCaching` is enabled, Spring registers interception infrastructure for beans with cache annotations. For a method invoked **through a Spring proxy**:

```java
@Cacheable(cacheNames = "products")
public Product findProduct(long id) {
    return repository.findById(id).orElseThrow();
}
```

- **Cache miss:** the interceptor computes the key, queries the cache and finds no entry, invokes the method body, stores the result, and returns it to the caller.
- **Cache hit:** the interceptor finds an entry for the key and returns the cached result; **the method body normally does not run again**.
- **The cache** does not automatically check `SecurityContextHolder`, data owners, roles, tenants, or ACL policies unless you design them into the call path and cache key.
- `@Cacheable` and `@PreAuthorize` are two pieces of advice that can coexist; how those advisors nest determines what is checked before returning data.

Main annotations:

| Annotation | Effect | What to be careful about |
| --- | --- | --- |
| `@Cacheable` | Checks cache first; calls method body only on cache miss | Cache hits can skip computations/checks **inside** the method body |
| `@CachePut` | Always invokes the method, then updates the cache with the result | Must keep keys consistent with read methods and write timing |
| `@CacheEvict` | Removes one key or clears the entire cache | Handle stale caches after data edits/deletions and ACL changes |
| `@Caching` | Combines multiple cache operations | Does not solve authorization |
| `@EnableCaching` | Enables cache annotations on Spring beans | Adding the library or method annotations alone is not enough |

`@Cacheable` is not HTTP caching and is not automatically equivalent to `Cache-Control: private`. Browsers/CDNs form a separate caching layer; a single system can simultaneously have Spring Cache, Hibernate cache, Redis, CDN, and HTTP response caching. Each layer requires its own key, scope, and policy.

## 3. The Default Cache Key Does Not Automatically Include the Principal

When neither `key` nor `keyGenerator` is specified, Spring Cache defaults to **the method arguments** (via `SimpleKeyGenerator`):

| Method signature | Default key value (meaning) |
| --- | --- |
| `find()` | `SimpleKey.EMPTY` |
| `find(10L)` | `10L` |
| `find("alice", 10L)` | `SimpleKey("alice", 10L)` |
| `find(10L, "vi")` | `SimpleKey(10L, "vi")` |

For a `find(long id)` method whose result also depends on `SecurityContextHolder.getContext().getAuthentication().getName()`, **the principal is not a method parameter** and thus does not appear in the default key.

Error-prone example:

```java
@Cacheable(cacheNames = "personalDashboard", key = "#p0")
public Dashboard dashboard(long workspaceId) {
    String username = SecurityContextHolder.getContext()
        .getAuthentication().getName();
    return buildDashboard(workspaceId, username);
}
```

Two users sharing `workspaceId` produce the exact same key, even though the result depends on `username`. The code above is merely a **vulnerable illustrative snippet**, not for production systems. If the result contains personal data, returning another user's cached entry leaks data.

`key = "#p0"` is a **Spring Cache** SpEL expression; `#p0` refers to the first parameter, working even when parameter names are not retained in bytecode. You can write `key = "#workspaceId"` if Spring can resolve parameter names, such as when compiled with `-parameters`.

## 4. Two Independent Risks: Sharing Results and Bypassing Permission Checks

### 4.1. Caching a Personalized Result Under a Shared Key

Suppose the input is only `reportId`, while the method body returns a report with different columns stripped/masked per role. If cached by `reportId`, user A can populate the cache with a broad view, and user B receives that same broad view. **Even if both are allowed to read the report**, B can see information not intended for them.

A safe key must cover **every variable affecting the output**: document, user, tenant, permission/role or policy version, locale, redaction mode, display options, etc., depending on the domain. Do not blindly dump every field into keys; include only factors genuinely needed to distinguish outputs while evaluating cache cardinality costs.

### 4.2. Cache Hits Short-Circuiting Permission Checks Inside the Method Body

Example:

```java
@Cacheable(cacheNames = "userViews", key = "#p0")
public String loadForCurrentUser(long id) {
    // Checking permissions here is too late if cache hits skip the method body.
    enforceOwner(id);
    return renderForCurrentUser(id);
}
```

If the first user populates the cache entry and a second user requests the same key, `enforceOwner(id)` inside the method body may **never execute**. Checking permissions **only on cache misses** is insufficient.

If both `@PreAuthorize` and `@Cacheable` are placed on **the exact same method**, advisor ordering must be examined. Conceptual model:

```text
A) Security advice wraps outside cache advice
   request -> @PreAuthorize -> cache hit/miss -> return
   => Permissions are still checked before a cache hit.

B) Cache advice wraps outside security advice
   request -> cache hit ----------------------> return
                    \ cache miss -> @PreAuthorize -> method
   => A hit can bypass the inner security advice.
```

In common Spring Security 6.x configurations, the `@PreAuthorize` advisor defaults to order `200`, while the cache advisor normally defaults to low precedence (`LOWEST_PRECEDENCE`), yet **order can be altered by configuration, custom advisors, or other environments**. Never rely on an untested ordering assumption as your sole security boundary.

An easier-to-verify model is **two separate beans**: a facade carrying `@PreAuthorize` that **does not cache facade results**, and an inner bean responsible solely for caching already-scoped data.

## 5. Recommended Structure: Authorize Every Time, Cache Behind It

```text
HTTP Controller / Job / Other Service
                  |
                  v
       SecuredDocumentService
       (separate bean/proxy)
       @PreAuthorize on public method
                  |
      check Authentication + ACL
          |               |
         deny            allow
          |               |
  AccessDeniedException   |
                          v
                   OwnerViewCache
                   (separate bean/proxy)
                    @Cacheable
                   key = (viewer, id)
                          |
                     hit / miss
                          |
                        return
```

For every call entering `SecuredDocumentService`, authorization runs before calling `OwnerViewCache`. Even when the inner cache returns a hit, the facade's permission check **already happened**. At the same time, the cache key includes both viewer and document ID so personalized strings are never mixed.

There are two main strategies:

**A. Cache shared data, authorize at the facade.** If the underlying data is identical for everyone and the cached value embeds no viewer-specific information, you can cache by `(tenantId, documentId, dataVersion)` in an internal bean. The facade verifies permissions every time before reading from the cache. Prevent any call path outside the facade from reaching this bean unchecked.

**B. Cache per-user personalized data.** If values contain usernames, permission-based redactions, or other viewer-dependent fields, the key must distinguish viewer/tenant/policy. Permissions must still be checked on every call; **a user-scoped key does not replace authorization**. When permissions change, invalidate or version keys accordingly.

**C. Do not cache highly sensitive or rapidly changing data.** When revocation, TTL, key composition, and cross-node eviction are hard to guarantee, consider skipping caching at this layer or caching only PII-free data.

## 6. Runnable Example: Java 17+ / Spring Boot 3.5.x

This demo uses Spring Boot **3.5.8** with Gradle, Spring Security, and an in-memory cache. There are no HTTP endpoints or databases. The goal is observing these conditions:

- `alice` reads her document `#1`; repeated reads return a cache hit.
- `bob` is denied when reading `#1`, **even while `alice`'s data is already sitting in the cache**.
- `bob` reads his document `#2`; output contains `bob`.
- After `alice` edits `#1`, the cache is evicted and the next read returns the updated content.
- Callers go through Spring beans; `@PreAuthorize`, `@Cacheable`, and `@CacheEvict` take effect.

In real applications, use a supported Spring Boot version and an environment-appropriate cache provider. The demo pins versions for reproducible builds; it does not depend on Spring Framework 7 cache APIs.

### 6.1. Directory Structure

```text
secure-cache-demo/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/demo/
    │   ├── SecureCacheApplication.java
    │   ├── Document.java
    │   ├── DocumentStore.java
    │   ├── DocumentPolicy.java
    │   ├── OwnerViewCache.java
    │   └── SecuredDocumentService.java
    └── test/java/demo/
        └── SecuredDocumentServiceTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'secure-cache-demo'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-cache` provides Spring Boot's caching infrastructure. In this example, the application also explicitly defines a `ConcurrentMapCacheManager` bean instead of relying on classpath-inferred default providers.

### 6.2. Domain and Server-Side Data Store

**`src/main/java/demo/Document.java`:**

```java
package demo;

public record Document(long id, String owner, String title) {
}
```

**`src/main/java/demo/DocumentStore.java`:**

```java
package demo;

import java.util.Map;
import java.util.NoSuchElementException;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

@Component
public class DocumentStore {

    private final Map<Long, Document> records = new ConcurrentHashMap<>();

    public DocumentStore() {
        records.put(1L, new Document(1L, "alice", "Alpha"));
        records.put(2L, new Document(2L, "bob", "Beta"));
    }

    public Optional<Document> find(long id) {
        return Optional.ofNullable(records.get(id));
    }

    public Document rename(long id, String newTitle) {
        Document updated = records.computeIfPresent(
            id,
            (key, old) -> new Document(old.id(), old.owner(), newTitle)
        );
        if (updated == null) {
            throw new NoSuchElementException("No document: " + id);
        }
        return updated;
    }
}
```

Ownership data lives inside the server's `DocumentStore`. If a caller submits `owner="alice"` in JSON, the backend **must never treat that as proof of ownership**. In real deployments, repositories/ACLs determine permissions from the database by ID and tenant.

### 6.3. Authorization Policy in a Separate Bean

**`src/main/java/demo/DocumentPolicy.java`:**

```java
package demo;

import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("documentPolicy")
public class DocumentPolicy {

    private final DocumentStore store;

    public DocumentPolicy(DocumentStore store) {
        this.store = store;
    }

    public boolean canRead(Authentication authentication, long id) {
        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            return false;
        }
        return store.find(id)
            .map(doc -> authentication.getName().equals(doc.owner()))
            .orElse(false);
    }

    public boolean canWrite(Authentication authentication, long id) {
        // Demo: write permission matches ownership; in practice policies can separate.
        return canRead(authentication, id);
    }
}
```

Both `canRead` and `canWrite` **fail closed** if authentication is invalid, the document does not exist, or the owner does not match. Multi-tenant apps must also verify tenant conditions from the principal **and** server data, never trusting client-supplied tenant IDs.

### 6.4. Bean Responsible Only for Caching Personalized Values

**`src/main/java/demo/OwnerViewCache.java`:**

```java
package demo;

import java.util.NoSuchElementException;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class OwnerViewCache {

    private final DocumentStore store;
    private final AtomicInteger actualLoads = new AtomicInteger();

    public OwnerViewCache(DocumentStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "ownerViews")
    public String load(String viewer, long id) {
        actualLoads.incrementAndGet();

        Document doc = store.find(id)
            .orElseThrow(() -> new NoSuchElementException("No document: " + id));

        return "For " + viewer + ": " + doc.title();
    }

    @CacheEvict(cacheNames = "ownerViews", allEntries = true)
    public void clearViews() {
        // Cache interceptor evicts after this method returns.
    }

    public int actualLoads() {
        return actualLoads.get();
    }
}
```

**Why not write `key = "#p1"`?** Because `#p1` is only `id`, omitting `viewer`. In this example, the default `SimpleKeyGenerator` builds a key containing **both arguments** `viewer` and `id`, so `(alice, 1)` differs from `(bob, 1)`.

`actualLoads` increments only when **the body of `load` actually runs**, i.e., on a cache miss. Cache hits do not increment the counter. `clearViews()` evicts **all** `ownerViews` entries after returning; this strategy is easy to verify yet can hurt performance on large caches. Production apps need targeted key eviction or synchronized versioning/invalidation.

This cache bean is an internal component for the facade. **Never expose `OwnerViewCache.load` directly as a controller endpoint**, since it only formats/caches and has no authorization annotations. If another caller is added, it must pass through an appropriate authorization boundary.

### 6.5. Facade: Enforcing Permissions on Every Call

**`src/main/java/demo/SecuredDocumentService.java`:**

```java
package demo;

import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Service;

@Service
public class SecuredDocumentService {

    private final DocumentStore store;
    private final OwnerViewCache cache;

    public SecuredDocumentService(DocumentStore store, OwnerViewCache cache) {
        this.store = store;
        this.cache = cache;
    }

    @PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
    public String view(long id) {
        // Read viewer from Authentication verified by Spring.
        String viewer = SecurityContextHolder.getContext()
            .getAuthentication().getName();

        // Cache advice runs on another bean, after the facade checked permissions.
        return cache.load(viewer, id);
    }

    @PreAuthorize("@documentPolicy.canWrite(authentication, #p0)")
    public String rename(long id, String newTitle) {
        Document changed = store.rename(id, newTitle);

        // Call through separate cache bean's proxy, avoiding self-invocation.
        cache.clearViews();

        return changed.title();
    }
}
```

`#p0` in `@PreAuthorize` refers to the method's first parameter (`id`), independent of compiler parameter-name retention. `authentication` is provided by Method Security. `@PreAuthorize` on the facade **is not cached**, so every `view`/`rename` call from outside the bean goes through the authorization advisor before entering the method body.

In `view`, the username comes from Spring's `SecurityContextHolder`, **never from a client-supplied `viewer`**. The call path ensures the name used in the cache key matches the verified identity.

In `rename`, data updates first and then the cache is evicted; the example omits transactions and external caches. With real databases, account for commits, rollbacks, concurrency, and cluster invalidation in section 10.

### 6.6. Bootstrapping: Enabling Caching and Method Security

**`src/main/java/demo/SecureCacheApplication.java`:**

```java
package demo;

import java.util.List;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Profile;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.core.authority.SimpleGrantedAuthority;
import org.springframework.security.core.context.SecurityContextHolder;

@SpringBootApplication
@EnableCaching
@EnableMethodSecurity
public class SecureCacheApplication {

    public static void main(String[] args) {
        SpringApplication.run(SecureCacheApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("ownerViews");
    }

    @Bean
    @Profile("!test")
    CommandLineRunner demo(
            SecuredDocumentService service,
            OwnerViewCache cache) {
        return args -> {
            try {
                authenticate("alice");
                System.out.println("ALICE_FIRST: " + service.view(1L));
                System.out.println("ALICE_AGAIN: " + service.view(1L));
                System.out.println("LOADS_AFTER_ALICE: " + cache.actualLoads());

                authenticate("bob");
                try {
                    service.view(1L);
                    System.out.println("BOB_OTHER: UNEXPECTED");
                } catch (AccessDeniedException denied) {
                    System.out.println("BOB_OTHER: DENIED");
                }
                System.out.println("LOADS_AFTER_DENIAL: " + cache.actualLoads());
                System.out.println("BOB_OWN: " + service.view(2L));

                authenticate("alice");
                System.out.println("ALICE_UPDATE: "
                    + service.rename(1L, "Alpha revised"));
                System.out.println("ALICE_REFRESHED: " + service.view(1L));
                System.out.println("LOADS_AFTER_EVICTION: " + cache.actualLoads());
            } finally {
                SecurityContextHolder.clearContext();
            }
        };
    }

    private static void authenticate(String username) {
        var token = new UsernamePasswordAuthenticationToken(
            username,
            "demo-only",
            List.of(new SimpleGrantedAuthority("ROLE_USER"))
        );
        SecurityContextHolder.getContext().setAuthentication(token);
    }
}
```

Because of `@Profile("!test")`, the demo runner executes during normal application startup; when running tests under profile `test`, `CommandLineRunner` does not mutate test data.

Enter the directory containing `build.gradle` and run:

```bash
./gradlew bootRun
```

On Windows PowerShell: `.\gradlew.bat bootRun`. If the project lacks a Gradle Wrapper, use an installed compatible Gradle with `gradle bootRun`, or generate a Wrapper from an existing Gradle installation.

**Expected output printed by the demo code**, aside from Spring Boot logs:

```text
ALICE_FIRST: For alice: Alpha
ALICE_AGAIN: For alice: Alpha
LOADS_AFTER_ALICE: 1
BOB_OTHER: DENIED
LOADS_AFTER_DENIAL: 1
BOB_OWN: For bob: Beta
ALICE_UPDATE: Alpha revised
ALICE_REFRESHED: For alice: Alpha revised
LOADS_AFTER_EVICTION: 3
```

Explanation:

1. `alice` reads `#1` twice: first is a miss, second is a hit, `actualLoads == 1`.
2. `bob` reads `#1`: the facade checks permission and denies **before calling the cache bean**, so load count stays `1`.
3. `bob` reads `#2`: allowed; key `(bob,2)` causes a new cache miss, total loads become `2`.
4. `alice` edits `#1`: the facade allows and calls `cache.clearViews()` through the proxy to evict.
5. Reading `#1` again after eviction returns `Alpha revised` and total loads become `3`.

**Important:** Constructing `UsernamePasswordAuthenticationToken` manually only simulates a `SecurityContext` for the demo. Real applications must use trusted authentication flows (sessions, OAuth2 resource server, etc.); never accept a client-supplied username and build an authenticated token.

## 7. Testing Through the Spring Context and Security Proxy

Create **`src/test/java/demo/SecuredDocumentServiceTest.java`**:

```java
package demo;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("test")
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class SecuredDocumentServiceTest {

    @Autowired SecuredDocumentService service;
    @Autowired OwnerViewCache cache;

    @Test
    @WithMockUser(username = "alice")
    void sameViewerGetsCacheHit() {
        assertEquals("For alice: Alpha", service.view(1L));
        assertEquals("For alice: Alpha", service.view(1L));
        assertEquals(1, cache.actualLoads());
    }

    @Test
    @WithMockUser(username = "bob")
    void deniedRequestCannotReuseAllicesData() {
        assertThrows(
            AccessDeniedException.class,
            () -> service.view(1L)
        );
        assertEquals(0, cache.actualLoads());
    }

    @Test
    @WithMockUser(username = "alice")
    void renameEvictsOldSnapshot() {
        assertEquals("For alice: Alpha", service.view(1L));
        assertEquals("Alpha revised", service.rename(1L, "Alpha revised"));
        assertEquals("For alice: Alpha revised", service.view(1L));
        assertEquals(2, cache.actualLoads());
    }
}
```

Run tests:

```bash
./gradlew test
```

`@WithMockUser` is provided by `spring-security-test`. `@Autowired` obtains the Spring-managed bean/proxy, unlike manual `new SecuredDocumentService(...)`. `@DirtiesContext` refreshes the context after each test so state in `DocumentStore` and `ConcurrentMapCacheManager` does not leak across tests; this is simple though costly in large suites.

You can also add a test within **the same test method** switching identity from `alice` to `bob` after `alice` warms the cache to verify directly that cross-user cache hits remain blocked. The `CommandLineRunner` example demonstrates that exact scenario.

### What Failures Do the Tests Catch?

- Removing `@EnableCaching` causes the second read to increment cache-method invocations, failing the cache-hit test.
- Removing `@EnableMethodSecurity` or bypassing the facade lets `bob` read a document he does not own, failing the denial test.
- Removing eviction after `rename` leaves the old value cached, failing the post-edit read test.
- Using an `id`-only cache key while letting another endpoint call the cache directly risks returning personalized content to the wrong viewer.

**Do not build tests that mock `SecuredDocumentService` itself**, as you would only be testing the mock without exercising Spring Security advisors or cache interception.

## 8. When Is Shared Caching Still Valid?

Shared caching of a document snapshot **can be safe** if the snapshot is unpersonalized and authorization always runs on the entry path:

```java
// Architectural pseudocode, not a standalone Java file.
@PreAuthorize("@documentPolicy.canRead(authentication, #p0)")
public DocumentView read(long id) {
    return sharedSnapshotCache.load(currentTenantId(), id);
}
```

In `sharedSnapshotCache.load(...)`, the cache key must include tenant (if IDs are not globally unique) and record ID. The cached data can be an **internal representation** needed for authorized viewers. Non-negotiable conditions: callers **have no path to fetch cached data directly** without authorization, and cached values carry no traces belonging to another user.

If the same record returns different content per viewer (e.g., fields masked by permission), build the view after authorization or key by **exact permission/viewer level**. With roles, keying only by `"ADMIN"` or `"USER"` can still be insufficient if ACLs grant per-record permissions. With tenants, keying solely by `documentId` is dangerous when IDs collide across tenants.

Never put access tokens, refresh tokens, or passwords into cache keys or logs to "represent a user." Use a stable, acceptably non-sensitive internal identifier (such as an opaque user ID and tenant ID). Caching sensitive content also requires storage encryption, Redis access policies, retention limits, and data governance per system requirements.

## 9. Designing Cache Keys Around Output-Determining Factors

A sample key model:

```text
cache-name = documentView
cache-key  = (tenantId, documentId, viewerId, viewPolicyVersion, locale)
```

This is a **conceptual model**; it is not mandatory for every application's key to include all five fields.

| Factor | When to include in key | If omitted |
| --- | --- | --- |
| `tenantId` | Record IDs are unique only per tenant; tenant-isolated data | May read another tenant's data |
| `documentId` | Per-record caching | Mixes up documents |
| `viewerId` | Output is personalized or per-user permissioned | Mixes user data |
| `scope/role/policyVersion` | Output varies by permission or ACL | Returns data under stale permissions |
| `locale` | Strings/formats are localized by language | Returns wrong-language content |
| `dataVersion` | Multiple consistent snapshots must coexist | Returns stale snapshot after update |
| `redactionMode` | Multiple field-masking levels exist | Leaks another user's masked fields |

If a method takes only `id` while the key requires `viewerId`, you can **pass the server-verified viewer as an argument to the cache bean** as in the demo. A custom `KeyGenerator` or SpEL calling an identity bean is also possible, though it hides `SecurityContext` dependencies; test it under async, background jobs, and permission changes. Avoid taking principals from client-sent HTTP headers as trusted sources.

With `@Cacheable`, key expressions run in the **cache SpEL context**, which differs from the security expression root. `authentication.name` working in `@PreAuthorize` does not mean an identical `authentication` variable exists by default in `@Cacheable`. When needed, pass explicit parameters `#p0`, `#p1` or a purposefully configured bean/key generator.

## 10. Invalidation: Content Changes and Access-Right Changes

### 10.1. When Data Changes

After `update`, `delete`, `publish`, or `move`, corresponding entries can become stale. Common strategies:

1. `@CacheEvict(cacheNames="...", key="...")` to remove the exact key when the identity is known.
2. `allEntries = true` to clear the entire cache when viewer keys are unknown; simple to make correct though costly.
3. Key/snapshot versioning (`documentVersion`, `ACLVersion`) to generate new keys whenever data or permissions change.
4. Short TTLs as a **risk-reduction layer**, never a substitute for immediate permission revocation.

Be careful with `@CacheEvict(beforeInvocation = true)`: evicting before updating can drop cached data even if the subsequent write fails. Default post-success eviction fits simple flows, yet **does not automatically ensure post-DB-commit timing** when a transaction wraps another advice layer.

### 10.2. When Permissions / ACLs Change

Operations like `revoke`, `removeMember`, role changes, account locking, owner transfers, or tenant transfers must be treated as **security invalidation events**.

- If facade authorization checks **every time** against fresh policy sources, a revoked user is blocked before touching the cache. Even so, ACL changes can alter **the shape of visible data** for a user who still has read access; personalized caches need eviction/versioning.
- If caching **authorization results themselves** (`canRead`/`hasPermission`), that policy cache must also be keyed by principal/tenant/target/action and invalidated immediately on permission changes. Stale authorization caches are a major risk.
- When a user logs out, a per-user key does not turn into public data; nonetheless, cache expiration and revocation rules must be explicit. Never rely on logout as the sole cache-clearing mechanism in multi-device systems.

### 10.3. Transactions and Race Conditions

A broken sequence:

```text
DB update starts
cache entry is evicted
another request cache-misses and reads stale uncommitted data
DB update commits
cache now retains the stale version
```

When combining `@Transactional`, `@CacheEvict`, and Redis/Caffeine, consider advisor order, isolation, and commit/rollback. Solutions depend on system architecture: dispatching invalidation events **after commit**, transaction-aware cache managers, versioned keys, or synchronized/atomic DB update patterns. Never promise `@CacheEvict` always runs after commit merely because both annotations appear on the same method.

Spring AOP proxies also carry self-invocation limits: `this.loadCached(...)` or `this.clearCache()` inside the same bean can bypass advice. The demo calls `cache.clearViews()` on **a separate bean** to ensure interception.

## 11. Multi-Instance Systems, Redis, and Tenants

`ConcurrentMapCacheManager` in the demo is a **per-process** cache. Two application instances have separate cache memories; eviction on instance A does not automatically clear entries on B. With shared backends like Redis/CDNs, there is also the risk of users across instances reading from unseparated namespaces.

Production checklist:

- **Namespace:** prefix with environment, schema version, service, and tenant when needed; never reuse cache keys across data types with different semantics.
- **Identity:** obtain viewer/tenant from verified principals; for service-to-service calls, clarify service identity and end-user delegation.
- **TTL:** base on data sensitivity and permission churn; never treat TTL as the sole enforcement for revocation.
- **Invalidation fan-out:** ensure updates and ACL changes propagate to all nodes or shared cache backends.
- **Serializer:** use versioned formats/schemas; avoid unsafe arbitrary-class deserialization from untrusted cache entries.
- **Observability:** aggregate hit/miss/eviction/denial metrics; never log cached payloads or tokens; control logging of user/tenant IDs separately.
- **Capacity:** per-user caching increases cardinality; balance hit rate, memory, and security. When too large, cache shared data and assemble personalized parts after authorization.
- **Isolation tests:** test two principals, two tenants with colliding IDs, role/owner changes, revocations, and cross-instance access.

When a user may view a record yet only see restricted fields, **a boolean `canRead` check alone is not enough**. Enforce field-level permissions or build a redacted DTO after authorization; redacted outputs must be keyed properly by permission context.

## 12. Common Pitfalls and How to Fix Them

| Symptom | Cause | Fix |
| --- | --- | --- |
| B sees A's name/private content | `@Cacheable` keyed only by ID while output is personalized | Add viewer/tenant/policy context to key, or cache shared data and render per viewer afterward |
| User who lost access still sees data | Authorization checked only on cache miss, or allow results cached too long | Check permissions at facade every time; invalidate/version ACLs |
| Cache hit skips check inside method | Check sits inside cached method body | Move authorization boundary in front of cache; test hits with another user |
| `@PreAuthorize` appears ignored | Missing `@EnableMethodSecurity`, self-invocation, caller used `new` | Call through Spring proxy; write allow/deny tests |
| `@Cacheable` does nothing | Missing `@EnableCaching`, self-invocation, or missing cache provider | Check config, bean, proxy, and provider |
| Cache key throws SpEL error | Used `authentication` like a security expression inside cache context | Pass verified identity as argument or configure bean/key generator |
| `@CacheEvict` fails to clear entry | Wrong cache name, mismatched key, or internal `this` call | Use consistent keys, call via proxy, test read-after-write |
| Stale entry reappears after commit | Race among eviction, cache miss, and transaction commit | Invalidate after commit / version keys |
| Test passes for one user yet leaks in production | Missing cross-user/cache-hit tests or mocked proxy | Have A warm cache then B access; assert both body and denial |
| Differences across application nodes | Per-node in-memory cache; eviction does not propagate | Use distributed cache / invalidation events |
| Cache explodes when keyed by user | Cardinality grows as `(user × resource × policy)` | Cache shared data post-auth, reduce personalization, tune TTL |
| Data leaks via CDN despite proper Spring cache | Public HTTP cache missing `Vary`, `private`/`no-store` | Configure HTTP layer separately; never rely on Spring Cache for HTTP guarantees |

The key is **separating two questions**: *who may access the resource?* is decided by authorization; *which computed values may be reused?* is decided by caching. Both answers must remain consistent on cache hits, permission changes, and multi-node deployments.

## 13. Practice Scenarios

**Scenario 1:** `getInvoices(long teamId)` reads the current user from `SecurityContextHolder` and uses `@Cacheable(key="#p0")`. Two users on the team have permission to view different invoices.  
**Question:** what is the bug?  
**Answer:** The cache key uses only `teamId`, whereas the output varies by viewer/permissions. You must authorize every call and key per user/policy, or cache base data and filter permissions in an unbypassable layer.

**Scenario 2:** `@PreAuthorize` sits on the same method as `@Cacheable`; the developer concludes it is always safe.  
**Question:** what must be checked?  
**Answer:** Proxy type, call path, whether both infrastructures are enabled, actual advisor ordering at runtime, cache hits with another user, and whether cached content distinguishes viewers. For clear boundaries, split the secured facade and cached bean.

**Scenario 3:** `alice` just had her permission on a document revoked. The cache key already includes the username.  
**Question:** is username in the key enough?  
**Answer:** No. Per-viewer keys prevent mixing data between users, yet you must still check current permissions; snapshots depending on ACLs/roles may need invalidation or versioning.

**Scenario 4:** Cache an identical DTO for everyone, while only authorized users may retrieve it.  
**Question:** is per-user caching mandatory?  
**Answer:** No, if the DTO is genuinely identical for authorized callers and every retrieval path checks permissions before the cache. Still, isolate tenants/namespaces and handle invalidation.

**Scenario 5:** An app uses `ConcurrentMapCacheManager` across three pods. Updating a document on pod A evicts cache on A.  
**Question:** will pod B definitely serve fresh data?  
**Answer:** No. In-memory caches are process-local, so cross-pod invalidation or a shared cache backend is required.

**Scenario 6:** To prove data does not leak on cache hits, is asserting `AopUtils.isAopProxy(service)` enough?  
**Answer:** No. A proxy existing proves neither the right advisors, right call path, right policy, nor right key. Test multiple principals on the same resource across hits/misses and after revocations/updates.

## 14. Summary and Further Reading

- Cache keys must cover every factor **that alters the output**: tenant, resource, viewer, policy/view version, etc., depending on the case.
- Authorization must be enforced on **every access path**, even when cached data exists; checking only inside the cached method body is insufficient.
- With Spring proxies, designing a **separate secured facade** and an inner cache bean keeps boundaries explicit and reduces advisor-ordering risks.
- Caching personalized results must distinguish identities; caching shared data remains viable when permissions are checked first, content does not depend on the viewer, and no bypass paths exist.
- Data and ACL updates entail eviction/versioning policies; with transactions and multiple instances, address post-commit timing and distributed invalidation.
- Never put tokens/passwords into keys, never trust client-supplied DTO owner/tenant fields as proof, and never treat TTL as a revocation guarantee.

Official documentation:

1. [Spring Framework — Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): caching concepts and abstraction scope.
2. [Spring Framework — Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, default keys, `condition`, `unless`, `@CacheEvict`, and proxy/self-invocation limits.
3. [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, and interceptor/advisor ordering.
4. [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): Spring AOP proxy limits and self-invocation.
5. [Spring Security — Testing Method Security](https://docs.spring.io/spring-security/reference/servlet/test/method.html): `@WithMockUser` and testing method authorization calls.

**Practical takeaway:** a cache speeds up returning previously computed data; it does not know whether the caller is still allowed to see that data. Every cache hit is a data-returning path that requires proper authorization and isolation per user context.