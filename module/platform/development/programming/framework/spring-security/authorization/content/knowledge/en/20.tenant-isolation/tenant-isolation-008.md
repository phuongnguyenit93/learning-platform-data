# Tenant-Scoped Cache Keys to Prevent Permission or Result Leaks

> **Topic:** Spring Security – authorization · **Group:** Tenant Isolation. In a multi-tenant application, caching is a **real data-access path**, not merely a performance optimization. A cache key missing the tenant or authorization-shaping factors can cause a user in tenant B to receive data or authorization outcomes from tenant A. This article covers key modeling, authorization check boundaries, Spring Cache `@Cacheable`/`@CacheEvict`, Redis/distributed caching, invalidation mechanisms, and tests against cross-tenant leakage. Examples primarily target Java 17+, Spring Boot 3.x, Spring Framework 6.x, and Spring Security 6.x; details may vary in Spring Boot 4/Spring Framework 7, so verify against your runtime version.

## 1. Learning objectives

After this lesson, you can:

1. Explain why **two resources with the same ID in different tenants** must never share a cache entry.
2. Separate **data**, **query result**, **authorization decision**, and **authentication/membership context** caches, and build proper keys for each.
3. Understand Spring Cache's default key generation and when `@Cacheable(key = "...")` inadvertently drops the tenant.
4. Obtain the tenant from a **verified source**, never unvalidated headers/paths/JWT claims; construct structured cache keys free of string-concatenation collisions.
5. Ensure authentication and tenant authorization **still execute on cache hits**, even when the cache returns a value without running the method body.
6. Design eviction, TTLs, cache versioning, revoke/grant handling, read-your-writes, and alignment between DB commits and invalidation.
7. Write integration tests where two tenants share the same document ID; test switching active tenants, revoked memberships, differing per-tenant roles, and updates without leaks.
8. Spot bugs involving `ThreadLocal`, `SecurityContext`, `@Async`, distributed Redis caches, serialization, cache warmups, batch jobs, and logging.
9. Apply fail-closed strategies for permission-decision caches instead of caching `allowed=true` indefinitely or reusing it across principals.

## 2. The problem: a cache hit can turn into an authorization bug

Suppose a SaaS platform holds this data:

~~~text
Tenant alpha:
  Document id=7
  title="ALPHA:Budget"
  allowed users: Alice

Tenant beta:
  Document id=7
  title="BETA:Budget"
  allowed users: Bob
~~~

The application has a service:

~~~java
// COUNTEREXAMPLE: key is only documentId.
@Cacheable(cacheNames = "document", key = "#p0")
public Document loadById(Long documentId) {
    return repository.findById(documentId).orElseThrow();
}
~~~

This snippet omits full Spring/JPA layers. The following flow can occur:

~~~text
Alice, tenant=alpha, GET /documents/7
  cache key = "document::7"
  miss -> DB returns ALPHA:Budget -> cache["7"] = ALPHA:Budget

Bob, tenant=beta, GET /documents/7
  cache key = "document::7"
  hit -> cache returns ALPHA:Budget
  method body is no longer executed
  -> Bob risks seeing alpha's data!
~~~

Even if the repository enforces a tenant filter inside the method body, a cache hit can **return before the method executes**, so placing tenant protection solely inside a cached method's body is insufficient for call paths lacking an outer authorization boundary.

**Fundamental rule:** caching is part of **the authorized data-access path**. A cache must never act as a shortcut bypassing tenant membership, permission checks, or tenant-scoped repositories.

## 3. Definition: what does a cache key reflect?

A sound key must uniquely identify **the safely reusable value** across every dimension affecting content or permissions. For shared raw documents within a tenant, the minimal key looks like:

~~~text
cache name      = tenantDocument
logical key     = {tenantId, documentId}
example         = tenantDocument::alpha:7
another tenant  = tenantDocument::beta:7
~~~

If two tenants share `documentId=7`, they remain **two distinct keys**.

For data distinguished by translation, version, state, data region, or resource type, add:

~~~text
{namespace, schemaVersion, tenantId, resourceType, resourceId,
 locale?, projection?, filter?, page?, consistencyVersion?}
~~~

Longer is not automatically safer. Each dimension must reflect whether **identical keys truly imply identical shareable results**.

### 3.1. Four cache categories requiring distinct thinking

| Cache type | Example data | Minimal key components | Security notes |
| --- | --- | --- | --- |
| **Tenant-shared resource data** | Unpersonalized document metadata | tenantId + documentId + type/schemaVersion | Still authorize caller before returning |
| **List/query results** | Filtered document search | tenantId + canonical filters + sort + page + projection | Avoid mixing search results/total counts across tenants |
| **User-visible results** | “My documents”, redacted DTOs | tenantId + principalId + action/view + query parameters | Must invalidate/re-check if roles/ACLs change; cached output can disclose info |
| **Authorization decisions** | `canRead(user, doc) = true` | tenantId + principalId + target type/id + action + security/policy revisions | Highly sensitive; **not caching** may be the safest choice |

Never share a single cache name `"result"` across raw documents, list exports, and permission booleans with differing key/value schemas. Partition namespaces and TTLs explicitly—e.g., `tenantDocumentById`, `tenantSearchPage`, `permissionDecision`.

### 3.2. Tenant in the key must be the verified tenant

A request arrives with headers:

~~~http
GET /api/documents/7
X-Tenant-ID: beta
Authorization: Bearer [Alice's token]
~~~

This does not mean Alice may read beta. Authenticate the principal, verify active membership and action rights in the tenant, and only then produce a **trusted tenant context**. A cache key built solely from `X-Tenant-ID` does not replace authorization, and can let an attacker actively “borrow” another tenant's partition.

Proper flow:

~~~text
requestedTenantId (untrusted)
   -> membership/action verification
   -> authorizedTenantId (trusted)
   -> tenant-scoped cache key
   -> data lookup/cache
   -> object-level/response policy if any
~~~

When tenant comes from a JWT, validate signature/issuer/audience/expiry per security configuration, then check the claim's domain semantics: a tenant-selection claim does not automatically grant access to every document in that tenant.

## 4. How does Spring Cache generate default keys?

With `@EnableCaching`, Spring Framework uses `CacheInterceptor`/`CacheOperationSource` to apply caching to Spring-managed beans via proxies/advice. Under the default generator in Spring Framework 6.x, keys derive from **the parameters passed to the method**:

| Parameter count | Default key (conceptual) |
| --- | --- |
| 0 | `SimpleKey.EMPTY` |
| 1 | That parameter itself |
| More than 1 | `SimpleKey` wrapping all parameters, preserving `equals/hashCode` semantics |

Example:

~~~java
@Cacheable("tenantDocument")
Document load(String tenantId, Long documentId) { ... }
~~~

Calling `load("alpha",7L)` and `load("beta",7L)` normally produces distinct default keys because the tenant argument differs. However, two traps await:

**Trap A: the method takes no tenant parameter.**

~~~java
@Cacheable("tenantDocument")
Document load(Long id) {
    // Tenant is implicitly read from ThreadLocal inside the body.
    return repository.findWithinTenant(TenantContext.get(), id);
}
~~~

The default key sees only `id`. Requests from alpha and beta with the same ID collide; Spring cannot guess a `ThreadLocal` exists outside the signature.

**Trap B: a custom key drops the tenant.**

~~~java
@Cacheable(cacheNames = "tenantDocument", key = "#p1")
Document load(String tenantId, Long id) { ... }
~~~

Two parameters exist, yet the custom key uses only `id`. The default key no longer saves you: `@Cacheable.key` overrides key generation.

### 4.1. Right SpEL for tenant and ID keys

~~~java
@Cacheable(
    cacheNames = "tenantDocument",
    key = "#p0 + ':' + #p1"
)
Document load(String trustedTenant, Long documentId) {
    return repository.findByTenantIdAndId(
            trustedTenant, documentId).orElseThrow();
}
~~~

`#p0` is the first argument and `#p1` is the second. Using `#p0`/`#p1` avoids depending on parameter names preserved via `-parameters`. This is a snippet: the method sits inside a Spring bean/proxy, tenant was verified at the calling layer, and the repository includes a tenant predicate.

If tenant IDs are free-form strings capable of containing `:` or multiple free-form strings are concatenated, naive concatenation risks **collisions**:

~~~text
tenant="a:b", documentId="7" -> "a:b:7"
tenant="a",   documentId="b:7" -> "a:b:7"
~~~

Use strict tenant ID grammars, canonical Long/UUID document IDs, or structured `SimpleKey`/record/length-prefixed/escaped encodings. For example:

~~~java
// In Java code with Spring Cache dependency:
var key = new org.springframework.cache.interceptor.SimpleKey(
        tenantId, "Document", documentId);
~~~

When using object keys with Redis, **verify the serializer/key conversion**. A local-cache `SimpleKey` does not automatically yield a safe, stable Redis representation across serializer changes, Java upgrades, or other languages. Treat key formats as versioned contracts when multiple instances share a cache.

### 4.2. Custom KeyGenerator

When multiple methods follow the same tenant convention, define a `KeyGenerator`:

~~~java
// Configuration snippet inside a Spring project.
@Bean("tenantAwareKeyGenerator")
KeyGenerator tenantAwareKeyGenerator() {
    return (target, method, params) -> {
        if (params.length < 2
                || !(params[0] instanceof String tenant)
                || !(params[1] instanceof Long id)) {
            throw new IllegalArgumentException(
                    "Expected trusted tenant and Long id");
        }

        // Namespace method/resource type to avoid collisions across caches.
        return new SimpleKey(
                "v2", target.getClass().getName(),
                method.getName(), tenant, id);
    };
}
~~~

Main imports: `org.springframework.cache.interceptor.KeyGenerator`, `org.springframework.cache.interceptor.SimpleKey`, and `org.springframework.context.annotation.Bean`. Usage:

~~~java
@Cacheable(cacheNames = "tenantDocument",
           keyGenerator = "tenantAwareKeyGenerator")
Document load(String trustedTenant, Long id) {
    return repository.findByTenantIdAndId(
            trustedTenant, id).orElseThrow();
}
~~~

**Never specify both `key` and `keyGenerator` on the same annotation**: they are mutually exclusive options. In this example, Spring may pass a proxy class for `target`; if you want namespaces stable across proxy/version upgrades, use an explicit resource type instead of `target.getClass().getName()`. A key generator is a **tested naming convention**, not proof that the caller holds membership.

## 5. Cache hits must never bypass authorization

### 5.1. Why combining @PreAuthorize and @Cacheable on the same method requires caution

A method might carry both:

~~~java
@PreAuthorize("hasPermission(#p1, 'Document', 'read')")
@Cacheable(cacheNames = "tenantDocument", key = "#p0 + ':' + #p1")
public Document read(String tenantId, Long id) {
    return repository.findByTenantIdAndId(tenantId,id).orElseThrow();
}
~~~

This is an **architectural counterexample**: the security expression checks permission by ID alone without ensuring type/id match the tenant; moreover, both caching and method security rely on Spring AOP advisors, whose interception ordering must be explicitly configured and tested. If cache advice returns directly on a hit before security advice runs, authorization is lost on hits. Never assume a single universal default advisor order across Spring versions/configs.

In particular, the method body never runs on a cache hit, so tenant/owner/role checks placed **solely inside the method body** will be skipped.

### 5.2. Recommended structure: authorizing service outside, cache reader in a separate bean

~~~text
HTTP/controller
    |
    v
DocumentService (bean A):
  @PreAuthorize("hasAuthority('document:read')")
  verify membership + tenant-specific read permission
  -> CachedDocumentReader (bean B):
       @Cacheable(key = trustedTenant + ':' + documentId)
       query scoped tenant/id on miss
  -> optional owner/ACL/classification check
  -> return authorized response
~~~

Benefits:
- Every call to `DocumentService` evaluates security before touching the cached reader.
- `CachedDocumentReader` caches only **tenant-scoped raw documents**, never per-user authorization decisions.
- On a cache hit, the reader's body may be skipped, yet the outer `DocumentService` still runs and enforces tenant/authority checks.
- If object-specific ACLs apply, check them in the outer service **after loading the object** or in resource-bound policies—never cache owner-specific outcomes as public data.
- Place these methods in **two distinct Spring beans** so caching proxies genuinely intercept; self-invocation `this.load(...)` can bypass caching or authorization depending on setup.

**Never call the cached reader directly from controllers or jobs, bypassing the security boundary.** Restrict visibility of the cached reader, organize modules/packages cleanly, and audit all call sites. Even though the cached reader uses tenant-scoped keys, unauthorized callers must never invoke it for another tenant.

### 5.3. Never implicitly treat a cache key as authz

A key `tenant=beta:id=7` only prevents collisions. It **does not** prove the current caller belongs to beta. An attacker like Alice can guess tenant beta and ID 7; if an endpoint reads the cache directly without checking membership, data still leaks. Maintain two independent barriers: **authorization before data** and **tenant-partitioned cache entries**.

## 6. Complete Spring Boot example: two tenants sharing a document ID

The application below demonstrates:
- Same `id=7`, with `ALPHA:Budget` in alpha and `BETA:Budget` in beta.
- Alice holds global `document:read`/`document:write`, yet has READ/WRITE in alpha and READ-only in beta.
- Bob has READ in beta and no membership in alpha.
- Viewer lacks feature read authority.
- The service verifies tenant-specific permissions **before** invoking the cache reader.
- Spring Cache keys on `tenant:id` and evicts only the matching tenant on update.
- An in-memory store keyed by record `DocKey(tenant,id)`; no real JPA/DB in this demo.

Save as `src/main/java/demo/cache/TenantCacheApplication.java` in a Java 17+ Spring Boot 3.x project:

~~~java
package demo.cache;

import java.util.Map;
import java.util.Optional;
import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.http.HttpStatus;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.core.userdetails.User;
import org.springframework.security.core.userdetails.UserDetailsService;
import org.springframework.security.provisioning.InMemoryUserDetailsManager;
import org.springframework.security.web.SecurityFilterChain;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PatchMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.server.ResponseStatusException;

@SpringBootApplication
@EnableCaching
@EnableMethodSecurity
public class TenantCacheApplication {
    public static void main(String[] args) {
        SpringApplication.run(TenantCacheApplication.class, args);
    }

    @Bean
    CacheManager cacheManager() {
        // Local demo. Production Redis/Caffeine requires explicit TTL/size/serializer.
        return new ConcurrentMapCacheManager("tenantDocument");
    }

    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        return http
                .authorizeHttpRequests(auth -> auth
                        .requestMatchers("/api/tenants/**")
                            .authenticated()
                        .anyRequest().denyAll())
                .httpBasic(Customizer.withDefaults())
                .build();
        // Do not disable CSRF indiscriminately. PATCH in tests uses csrf().
    }

    @Bean
    UserDetailsService users() {
        return new InMemoryUserDetailsManager(
                User.withUsername("alice")
                    .password("{noop}demo")
                    .authorities("document:read", "document:write")
                    .build(),
                User.withUsername("bob")
                    .password("{noop}demo")
                    .authorities("document:read")
                    .build(),
                User.withUsername("viewer")
                    .password("{noop}demo")
                    .authorities("profile:read")
                    .build());
    }
}

// Demo-only DTO; contains no secrets or per-user ACLs.
record Document(long id, String tenantId, String title) {}
record DocKey(String tenant, long id) {}
record RenameRequest(@NotBlank @Size(max = 180) String title) {}

@Component
class TenantMemberships {
    private final Map<String, Map<String, Set<String>>> rights = Map.of(
            "alice", Map.of(
                    "alpha", Set.of("read", "write"),
                    "beta", Set.of("read")),
            "bob", Map.of(
                    "beta", Set.of("read")),
            "viewer", Map.of(
                    "alpha", Set.of("read")));

    void requireAction(Authentication auth, String tenant, String action) {
        if (auth == null || !auth.isAuthenticated()
                || auth instanceof AnonymousAuthenticationToken
                || tenant == null
                || !tenant.matches("[a-z][a-z0-9-]{0,31}")
                || !rights.getOrDefault(auth.getName(), Map.of())
                    .getOrDefault(tenant, Set.of()).contains(action)) {
            throw new AccessDeniedException("Tenant/action denied");
        }
    }
}

@Component
class DocumentStore {
    private final ConcurrentMap<DocKey, Document> records =
            new ConcurrentHashMap<>(Map.of(
                new DocKey("alpha", 7L),
                    new Document(7L, "alpha", "ALPHA:Budget"),
                new DocKey("beta", 7L),
                    new Document(7L, "beta", "BETA:Budget"),
                new DocKey("alpha", 8L),
                    new Document(8L, "alpha", "ALPHA:Plan")));

    private final ConcurrentMap<DocKey, AtomicInteger> reads =
            new ConcurrentHashMap<>();

    Document findRequired(String trustedTenant, Long id) {
        DocKey key = new DocKey(trustedTenant, id);
        reads.computeIfAbsent(key, ignored -> new AtomicInteger())
             .incrementAndGet();
        Document found = records.get(key);
        if (found == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return found;
    }

    Document rename(String trustedTenant, Long id, String newTitle) {
        DocKey key = new DocKey(trustedTenant, id);
        Document updated = records.computeIfPresent(key,
                (ignored, oldValue) -> new Document(
                        oldValue.id(), oldValue.tenantId(), newTitle));
        if (updated == null) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        return updated;
    }

    int storeReads(String tenant, long id) {
        AtomicInteger n = reads.get(new DocKey(tenant, id));
        return n == null ? 0 : n.get();
    }
}

// Bean B: ONLY caches data keyed by verified tenant.
// Never put permission checks inside a body that cache hits can skip.
@Component
class CachedDocumentReader {
    private final DocumentStore store;

    CachedDocumentReader(DocumentStore store) {
        this.store = store;
    }

    @Cacheable(cacheNames = "tenantDocument",
               key = "#p0 + ':' + #p1")
    public Document load(String trustedTenant, Long id) {
        return store.findRequired(trustedTenant, id);
    }
}

// Bean C: scoped update, evicting the exact entry after method succeeds.
// This is an in-memory demo without DB transactions or outbox.
@Component
class DocumentWriter {
    private final DocumentStore store;

    DocumentWriter(DocumentStore store) {
        this.store = store;
    }

    @CacheEvict(cacheNames = "tenantDocument",
                key = "#p0 + ':' + #p1")
    public Document rename(String trustedTenant, Long id, String title) {
        return store.rename(trustedTenant, id, title);
    }
}

// Bean A: Security boundary invoked by HTTP/jobs/integration tests.
@Service
class DocumentService {
    private final TenantMemberships memberships;
    private final CachedDocumentReader reader;
    private final DocumentWriter writer;

    DocumentService(TenantMemberships memberships,
                    CachedDocumentReader reader,
                    DocumentWriter writer) {
        this.memberships = memberships;
        this.reader = reader;
        this.writer = writer;
    }

    private Authentication actor() {
        return SecurityContextHolder.getContext().getAuthentication();
    }

    @PreAuthorize("hasAuthority('document:read')")
    public Document read(String tenant, Long id) {
        memberships.requireAction(actor(), tenant, "read");
        // Record is fetched scoped by tenant even on cache miss.
        Document doc = reader.load(tenant, id);
        // When owner/ACL is needed: check further here, on EVERY cache hit.
        return doc;
    }

    @PreAuthorize("hasAuthority('document:write')")
    public Document rename(String tenant, Long id, RenameRequest request) {
        memberships.requireAction(actor(), tenant, "write");
        return writer.rename(tenant, id, request.title());
    }
}

@RestController
@RequestMapping("/api/tenants/{tenantId}/documents")
class DocumentController {
    private final DocumentService service;

    DocumentController(DocumentService service) {
        this.service = service;
    }

    @GetMapping("/{id}")
    Document read(@PathVariable("tenantId") String tenant,
                  @PathVariable("id") Long id) {
        return service.read(tenant, id);
    }

    @PatchMapping("/{id}")
    Document rename(@PathVariable("tenantId") String tenant,
                    @PathVariable("id") Long id,
                    @Valid @RequestBody RenameRequest request) {
        return service.rename(tenant, id, request);
    }
}
~~~

### 6.1. Dependencies

In a Java 17+ Spring Boot 3.x project with plugin/dependency management configured, add:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-cache'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

This is only the `dependencies` block, not a complete `build.gradle`. The sample uses `ConcurrentMapCacheManager`, so no Redis server is required. `{noop}` passwords are for learning only; production requires a secure password encoder. If using Spring Boot 4.x, check the corresponding cache/security/test starters before copying.

### 6.2. Practical scenarios

| Principal | Selected tenant | Global authority | Tenant action | Document ID 7 | Outcome |
| --- | --- | --- | --- | --- | --- |
| Alice | alpha | read | read | alpha ID 7 | 200, `ALPHA:Budget` |
| Alice | beta | read | read | beta ID 7 | 200, `BETA:Budget` |
| Bob | beta | read | read | beta ID 7 | 200, `BETA:Budget` |
| Bob | alpha | read | no membership | alpha ID 7 | 403 |
| Viewer | alpha | lacks `document:read` | read | alpha ID 7 | 403 |
| Alice | beta | write | beta read-only | beta ID 7 | PATCH 403 |
| Alice | alpha | write | alpha write | alpha ID 7 | PATCH 200, exact single entry evicted |
| Anonymous | alpha | unauthenticated | none | alpha ID 7 | Typically 401 with HTTP Basic |

**Note:** the demo models action memberships only, without per-document owner/ACL checks. In real applications, `read()`/`rename()` must also invoke object authorization against trusted data, and never cache per-user decisions like shared raw documents.

### 6.3. Where does the cache sit along the call path?

~~~text
GET /api/tenants/beta/documents/7
  -> HTTP authentication (Bob)
  -> DocumentService.read("beta",7)
       @PreAuthorize read global
       TenantMemberships.requireAction(Bob,beta,read)
       -> CachedDocumentReader.load("beta",7)
            key="beta:7"
            HIT? return cached beta Document
            MISS? DocumentStore finds (beta,7)
       -> optional object ACL check
       -> response BETA:Budget
~~~

For a Bob→alpha request, `requireAction` stops before `CachedDocumentReader`, even when `alpha:7` is already warmed in cache by Alice. **Having an entry in the cache is not an access pass.**

## 7. Integration tests: same ID across tenants, eviction, and revocation

Create `src/test/java/demo/cache/TenantCacheApplicationTest.java`:

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.web.servlet.MockMvc;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.csrf;
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.httpBasic;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .patch;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class TenantCacheApplicationTest {
    @Autowired MockMvc mvc;
    @Autowired DocumentStore store;

    @Test
    void sameIdInTwoTenantsNeverSharesValue() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("ALPHA:Budget"));

        mvc.perform(get("/api/tenants/beta/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("BETA:Budget"));

        // Second call must hit the exact key without calling the store again.
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(jsonPath("$.title").value("ALPHA:Budget"));

        assertEquals(1, store.storeReads("alpha", 7L));
        assertEquals(1, store.storeReads("beta", 7L));
    }

    @Test
    void unauthorizedUserCannotReadHotCacheEntry() throws Exception {
        // Alice warms alpha's cache.
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk());

        // Bob holds global read authority but does NOT belong to alpha.
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("bob", "demo")))
                .andExpect(status().isForbidden());

        assertEquals(1, store.storeReads("alpha", 7L));
    }

    @Test
    void updateEvictsOnlyMatchingTenantAndId() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk());
        mvc.perform(get("/api/tenants/beta/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(status().isOk());

        mvc.perform(patch("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"ALPHA:Revised\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.title").value("ALPHA:Revised"));

        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(jsonPath("$.title").value("ALPHA:Revised"));

        mvc.perform(get("/api/tenants/beta/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(jsonPath("$.title").value("BETA:Budget"));

        assertEquals(2, store.storeReads("alpha", 7L));
        assertEquals(1, store.storeReads("beta", 7L));
    }

    @Test
    void readPermissionIsTenantScopedEvenWhenGlobalWriteExists()
            throws Exception {
        // Alice holds global document:write, yet beta permits READ only.
        mvc.perform(patch("/api/tenants/beta/documents/7")
                    .with(httpBasic("alice", "demo"))
                    .with(csrf())
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("{\"title\":\"Forbidden\"}"))
                .andExpect(status().isForbidden());

        mvc.perform(get("/api/tenants/beta/documents/7")
                    .with(httpBasic("alice", "demo")))
                .andExpect(jsonPath("$.title").value("BETA:Budget"));
    }

    @Test
    void missingGlobalReadAuthorityIsDenied() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7")
                    .with(httpBasic("viewer", "demo")))
                .andExpect(status().isForbidden());
    }

    @Test
    void anonymousCannotUseCachedData() throws Exception {
        mvc.perform(get("/api/tenants/alpha/documents/7"))
                .andExpect(status().isUnauthorized());
    }
}
~~~

**Explanation:** `@DirtiesContext` recreates the application context after each test in this sample to prevent data/cache mutations across tests; in larger suites, swap for safe fixture resets or explicit cache clearing. Assertions on `storeReads` prove the second lookup hit the right tenant key and eviction targeted only the matching partition. The test where Bob accesses alpha after Alice warms the cache is a critical regression test: testing only **cache misses** can miss bypasses on cache hits.

### 7.1. Additional tests needed beyond the demo

- Alpha and beta users sharing an ID where versions, locales, or redactions differ.
- User with global feature read whose tenant membership is revoked **after the cache is warmed**.
- A user who is ADMIN of alpha yet VIEWER of beta; `WRITE beta` always denies.
- Search, pagination, count, recommendation, and file download APIs using tenant-scoped keys with full query dimensions.
- Concurrent updates and reads: cache invalidation aligned with transaction commits, preventing re-insertion of stale entries after revocation.
- Multiple app nodes sharing Redis with unified namespaces, serialized key versions, and pub/sub invalidation.
- Invalid tenant IDs or IDs containing delimiters/Unicode collisions: must never share entries.
- Async/messaging/batch scopes never retaining the previous task's tenant context.
- Owner/ACL/feature-flag/tenant-status changes: revocation takes effect within SLA.
- Migration to a new cache backend: never read legacy keys missing tenant.

## 8. Keys for authorization decisions must be stricter than data keys

The fact that `canRead(Bob, Document 7)` returned `true` today **cannot** be reused for Alice or another tenant. If an application genuinely needs to cache decisions, model the key as:

~~~text
decision:v4:
  tenant=beta
  actor=user-52
  resourceType=Document
  resourceId=7
  action=READ
  policyVersion=2026-11
  aclRevision=119
  membershipRevision=57
  resourceStateVersion=4
~~~

This is a **conceptual schema**, not a mandatory Redis format. Beyond tenant, include:
- A stable principal ID, not merely a display username.
- Exact action/permission (READ, WRITE, DELETE differ).
- Resource type + ID; Document 7 differs from Invoice 7.
- Verifiable policy/ACL/role-membership revisions, or reliable invalidation; never fake nonexistent versions.
- Other policy inputs that truly affect outcomes, such as ACTIVE/SUSPENDED tenant status, owner, classification, time, delegation expiry, or client context if used.

**The simpler approach is usually safer:** avoid caching **ALLOW** decisions for sensitive resources or frequently changing permissions. Cache tenant-scoped raw/resource data, while **re-evaluating authorization on every request** against live sources. If caching decisions, design explicit revocation guarantees, very short TTLs per threat model, invalidation on all relevant changes, and fail-closed behavior when versions cannot be verified.

### 8.1. Why a 5-minute TTL is not a complete solution

If Alice leaves tenant beta right after caching `allowed=true`, a 5-minute TTL lets her keep accessing data for the remainder of that window. For sensitive internal data, accepting that window must be an explicit risk/legal/product sign-off—never assume “5 minutes is short” and ignore revocation.

Specifically:
- Revoking a membership can require invalidating **thousands of decision keys** tied to that actor/tenant.
- Editing a parent ACL can affect descendants and many principals; evicting a single object ID is insufficient.
- Role hierarchy or permission mapping updates also render decision caches stale.
- If tokens hold stale role claims, disabling the cache alone does not fix freshness; design token lifetimes/revocation in parallel.

### 8.2. Caching DENY also has consequences

Caching `false` for too long keeps newly authorized users locked out. That is usually an availability bug rather than a leak, yet it breaks workflows and triggers support escalations. Do not treat GRANT and DENY caches identically with the same TTL if grant/revoke SLAs differ. `UNKNOWN` results, policy service exceptions, or “failed to load ACL” must **never** be cached as GRANT.

### 8.3. Caching principal roles is a form of decision cache

Caching Alice's `Set<GrantedAuthority>` without tenant and reusing it across alpha and beta lets alpha roles unlock beta. Cache memberships/roles by `{tenant,principal,scope,version}` with invalidation or freshness checks. If a provider returns a global membership list, the caller must still pick the right tenant and action—caching the whole list is not an authorized tenant context on its own.

## 9. Lists, search, and pagination: keys need more than tenant:id

Caching a query:

~~~java
@Cacheable(cacheNames = "tenantSearch",
           key = "#p0 + ':' + #p1")
List<Document> search(String tenant, String query) { ... }
~~~

may omit `page`, `size`, `sort`, `status`, `projection`, `locale`, `author`, or `permissionView` when they affect output. A proper key canonicalizes the query:

~~~text
tenantSearch:v3:
  tenant=alpha
  filter={status:ACTIVE,tag:budget}
  sort=createdAt:desc,id:asc
  page=2
  size=20
  view=viewer
  locale=vi-VN
~~~

This example describes **the fields**, not production string-building code. For JSON/dictionaries, canonicalize field ordering and types; never rely on `Map.toString()` whose iteration order may vary across runtimes. If results are already ACL-filtered **per user**, include principal/action/permission versions or avoid caching at a cross-user layer.

### 9.1. Never cache tenant-wide top-N and filter per user afterward assuming safety

If a cache stores a tenant-wide list containing sensitive content, it can be served to a user authorized for only a subset. You can:
1. Cache tenant-scoped metadata **excluding forbidden payloads**, and perform object-level filtering on every request; or
2. Enforce ACLs inside the DB/search engine query/pagination and cache user-scoped results with full invalidation; or
3. Skip caching when security complexity outweighs the benefit.

Accurate pagination and total counts are also required: caching a full list first and filtering later skews counts and inadvertently discloses document existence via timings, highlights, or metadata.

### 9.2. Negative caching

A record not found in tenant alpha may **exist in beta**. Never cache `NOT_FOUND(id=7)` globally. If using negative caching, keys must still include tenant and full scope, keep TTLs short, and never cache infrastructure errors as permanent “not found.”

### 9.3. Feature flags and response personalization

If responses depend on plans, entitlements, feature flags, field-level redaction, locale, or A/B tests, keys must reflect all differences **eligible for sharing**. Otherwise, a full admin response can be served to a viewer in the same tenant. Caching raw data and redacting **after** cache lookup reduces key dimensionality, provided raw data in Redis is well protected and every consumer enforces redaction.

## 10. Invalidation: right tenant, right ID, right timing

Proper tenant keys solve **cross-tenant collisions**, not freshness after updates or revocations.

### 10.1. Editing a Document must evict only one partition

~~~java
@CacheEvict(
    cacheNames = "tenantDocument",
    key = "#p0 + ':' + #p1")
public void rename(String trustedTenant, Long id, String title) {
    repository.renameWhereTenantMatches(
            trustedTenant, id, title);
}
~~~

This snippet omits transactions/row-count/error handling. In a shared DB, use `WHERE tenant_id = :trustedTenant AND id = :id`; on 0 rows, handle NOT_FOUND/conflict rather than treating it as success or evicting another tenant's key.

**Do not do this:**

~~~java
@CacheEvict(cacheNames = "tenantDocument", key = "#p1")
public void rename(String tenant, Long id, String title) { ... }
~~~

If the cache keys on `tenant:id`, evicting by `id` misses the old entry and leaves stale data behind. Likewise, avoid `allEntries=true` on every update unless strictly required: it triggers stampedes, hurts availability, and can disturb other tenants sharing a namespace.

### 10.2. Eviction and transaction commits

With DB transactions:
- `@CacheEvict` executes according to cache advice timing and does not automatically guarantee “evict only after DB commit” under all configurations.
- Evicting **before commit** lets concurrent requests read old DB data and **re-populate the cache** right before commit finishes.
- Evicting **after commit** reduces some races, though publishers can fail or cache replicas may lag behind invalidation.
- Use `TransactionAwareCacheManagerProxy` or transaction-aware cache decorators where appropriate and verify exact semantics; for distributed/high-risk systems, consider outbox + versioned keys.
- When an update spans multiple objects, ensure events/evictions cover every affected tenant/type/id and `policyVersion`.

A race timeline:

~~~text
t1: transaction updates alpha:7 -> ALPHA:Revised (uncommitted)
t2: evict cache alpha:7 early
t3: concurrent reader queries DB and sees ALPHA:Old (old snapshot)
t4: reader caches ALPHA:Old
t5: transaction commits ALPHA:Revised
t6: cache hits ALPHA:Old even though DB committed
~~~

Depending on consistency SLAs, solutions include after-commit invalidation, versions/tags in cache keys, optimistic lock versions, and coalescing update events. Never rely on TTL alone as a substitute for immediate revocation.

### 10.3. Revoking tenant membership vs. editing a document

When a user is removed from a tenant, **raw document caches do not necessarily need eviction** if every caller still passes an outer membership check. Remaining legitimate tenant users can still use the cached data while the revoked user is blocked before any hit. However:
- All decision caches/role caches for that user must be invalidated or re-validated.
- Pre-signed URLs, active sessions, and long-running jobs may require separate revocation.
- If the cache stores **personalized responses** tailored to that user, evict the corresponding user/tenant entries.
- If authorization was mistakenly checked only on cache miss, fix the architecture—do not merely evict once.

### 10.4. Tenant offboarding and migration

When a tenant is disabled or deleted:
- Block all new requests/jobs at the authorization boundary.
- Invalidate or purge the tenant's cache namespace per retention/security policy; never treat data caches as the sole source of truth for lifecycle state.
- Clean up object storage, CDNs, vector/search indexes, analytics, and browser/client caches—not just Redis.
- If a tenant ID were ever reused (avoid doing so), old cache entries could “resurrect” into the new tenant. Use stable never-reused tenant identities and namespace versions.

## 11. Redis / distributed caches: key schemas are contracts

In a local `ConcurrentMapCacheManager`, `SimpleKey` is a Java object with `equals/hashCode`. In Redis, keys serialize to bytes; when multiple app instances, versions, or languages read the cache, **key formats must be stable, collision-free, and backed by a migration strategy**.

### 11.1. Cache names and key prefixes

Spring Data Redis caches typically prefix keys with the cache name (conceptually `cacheName::logicalKey`, depending on configuration). Cache names/keys should distinguish:
- Environment/deployment: production separate from staging if Redis is ever shared.
- Service/resource type: `docByTenant` separate from `invoiceByTenant`.
- Schema/key version: `v3` whenever serialization/fields change.
- Trusted, canonical tenant identifier.
- Resource/query ID.

Example:

~~~text
prod:document:v3::alpha|7
prod:document:v3::beta|7
prod:perm:v2::alpha|alice|Document|7|READ|aclRev=20
~~~

This is a reference convention, not a claim that Redis Cache Manager emits this exact string automatically. When using delimiters, validate/escape/length-prefix segments. Avoid embedding raw secrets (JWTs, access tokens, sensitive emails) in keys because Redis keys surface in monitoring, logs, and metrics.

### 11.2. Tenant-scoped keys do not equal Redis IAM tenant isolation

A shared Redis instance may grant a service account read rights across all namespaces. If your threat model requires strict tenant separation, consider Redis ACLs/per-service users, separate namespaces/databases/instances, encryption at rest/in transit, network segmentation, and restricting `KEYS`/`SCAN` for unauthorized operators. Tenant keys prevent **application logic from mixing values**, not cryptographic or storage-level isolation automatically.

### 11.3. Serialization and object types

Never trust a cached JSON object merely because its key has the right tenant. Watch for:
- Stale schemas: added/removed fields deserializing older data incorrectly.
- Poisoned values from another service with Redis write access.
- Custom serializers posing deserialization/gadget risks on untrusted payloads.
- Key collisions when teams share cache names/IDs while storing different value types.

Use safe typed serializers, versioned payloads, restrict uncontrolled polymorphic deserialization, verify owner/resource tenant where needed, and isolate namespaces per domain.

### 11.4. TTL, eviction, and stampedes

TTLs must align with business rules and threat models. Caching low-sensitivity metadata for a few minutes may be fine; caching `allowed=true` for minutes after revocation may not. Separate:
- Data TTL.
- Membership/role freshness.
- ACL decision TTL.
- Negative-cache TTL.
- Tenant suspension/revocation freshness.

Across multiple app nodes, evictions can hit simultaneously; post-invalidation request storms require backpressure/load control, potentially using `sync=true` or local single-flight where supported and tested. Never turn cache unavailability into “allow all”; on cache failure, fall back to trusted DB/policy per contract, or fail closed for sensitive operations.

## 12. @Async, thread reuse, and cache context

A design using:

~~~java
@Cacheable(cacheNames = "document", key = "#p0")
public Document load(Long id) {
    String tenant = TenantContextHolder.get();
    return repository.findByTenantIdAndId(tenant,id).orElseThrow();
}
~~~

has three flaws:
1. Tenant is absent from method arguments, so the default key cannot distinguish tenants.
2. Method body may be skipped on cache hits, so `TenantContextHolder.get()` is not guaranteed to run.
3. Servlet/async executor `ThreadLocal` state can be missed or retained across worker reuse.

**Better:** pass an explicit `trustedTenantId` into services and cached methods, deriving the key from arguments; create `trustedTenantId` only after membership/action checks. For `@Async`, capture context per task, install it in the worker, and clean up in `finally`; never serialize an entire `SecurityContext` onto a queue and treat it as permanently valid authorization.

### 12.1. Nested calls and self-invocation

`@Cacheable` and `@PreAuthorize` rely on Spring proxies in standard configurations. Calling `this.cachedRead(...)` inside the same bean can skip cache advice; calling `this.securedRead(...)` can skip security advice. Splitting the security boundary and cache data loader into separate beans makes testing clearer, while requiring that you **never expose the loader as an unprotected API**.

### 12.2. WebFlux/Reactor differs from Servlet ThreadLocal

In Reactive WebFlux, security context uses Reactor `Context` instead of relying purely on `ThreadLocal`. When sharing publishers via `Mono.cache()` or `Flux.cache()`, separate data by tenant/user and subscription scope; never share a cached reactive stream personalized for Alice with Bob. Design dedicated context-aware reactive caching rather than copying Servlet `SecurityContextHolder` habits into reactive pipelines.

## 13. Standalone Java 17: observing collisions and fixing keys

This program **compiles and runs with JDK 17 alone**, without Spring. It intentionally contrasts a “bad cache” keyed solely by ID against a “good cache” keyed by a composite record `(tenant,resourceType,id)`. Source data shares ID 7 across alpha and beta.

Save as `TenantCacheKeyDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class TenantCacheKeyDemo {
    record CacheKey(String tenant, String kind, long id) {}

    static final Map<CacheKey, String> DATABASE = new HashMap<>(Map.of(
            new CacheKey("alpha", "Document", 7L), "ALPHA-7",
            new CacheKey("beta", "Document", 7L), "BETA-7"));

    static final Map<Long, String> BAD_CACHE = new HashMap<>();
    static final Map<CacheKey, String> GOOD_CACHE = new HashMap<>();

    static String unsafeRead(String tenant, long id) {
        return BAD_CACHE.computeIfAbsent(id, ignored ->
                DATABASE.get(new CacheKey(tenant, "Document", id)));
    }

    static String scopedRead(String tenant, long id) {
        CacheKey key = new CacheKey(tenant, "Document", id);
        return GOOD_CACHE.computeIfAbsent(key, DATABASE::get);
    }

    public static void main(String[] args) {
        System.out.println("unsafe-alpha=" + unsafeRead("alpha", 7));
        System.out.println("unsafe-beta=" + unsafeRead("beta", 7));

        System.out.println("safe-alpha=" + scopedRead("alpha", 7));
        System.out.println("safe-beta=" + scopedRead("beta", 7));

        CacheKey alphaKey = new CacheKey("alpha", "Document", 7L);
        DATABASE.put(alphaKey, "ALPHA-7-V2");
        GOOD_CACHE.remove(alphaKey);

        System.out.println("after-update-alpha=" + scopedRead("alpha", 7));
        System.out.println("beta-still=" + scopedRead("beta", 7));
        System.out.println("good-entries=" + GOOD_CACHE.size());
    }
}
~~~

Run:

~~~bash
javac --release 17 TenantCacheKeyDemo.java
java TenantCacheKeyDemo
~~~

**Exact stdout:**

~~~text
unsafe-alpha=ALPHA-7
unsafe-beta=ALPHA-7
safe-alpha=ALPHA-7
safe-beta=BETA-7
after-update-alpha=ALPHA-7-V2
beta-still=BETA-7
good-entries=2
~~~

Explanation:
- `BAD_CACHE` keys only by Long `7`, so once alpha warms first, beta receives alpha's content.
- `GOOD_CACHE` uses `record CacheKey(tenant,kind,id)`, where Java auto-generates `equals/hashCode` over all components, preventing collisions across tenants.
- After updating alpha's source data and evicting only alpha's key, beta retains its own accurate value.
- This demo illustrates **data partitioning** only; it performs no authentication, membership, or ACL checks. Production must authorize callers before accessing caches and never let clients control keys freely.

### 13.1. Why are record keys beneficial?

An immutable record like `CacheKey` prevents forgetting a field in `equals/hashCode` and avoids collisions from unescaped string concatenation. Even so:
- When serializing keys to Redis, establish a stable cross-version format.
- If `tenant` could be null, creating a null key risks an unintended “global” tenant; validate upstream.
- If permissions depend on user/action, a record containing only tenant/id is **insufficient** for a permission decision cache.
- If Document and Invoice share IDs, `kind` prevents cross-resource collisions.
- Never use `hashCode()` alone as a persistent key due to hash collisions and version instability.

## 14. Process for fixing a tenantless cache key in a live system

Do not just edit an annotation and deploy: **legacy cache entries** may linger, and older service instances may still read the wrong keys.

### Step 1 — Inventory cache paths

Locate every site:
- `@Cacheable`, `@CachePut`, `@CacheEvict`, `@Caching`, `CacheManager.getCache(...)`, direct `RedisTemplate` calls.
- Get/list/search/export data, permission decisions, user roles, ACLs, and tenant lookups.
- CDN/browser/HTTP caches, API gateway caches, GraphQL DataLoaders, search index query caches.
- Background jobs, webhooks, report generation, object storage presigned URLs.

Do not search only for the literal string `tenantDocument` in one repository; different places often use different cache names for the same underlying data.

### Step 2 — Classify entries

For each cache:
1. Can entries be shared across users within a tenant?
2. Are entries subject to principal-specific redaction/ACL/personalization?
3. Could key collisions expose another tenant's resources?
4. Are there time-sensitive policies (revocation, suspension, plans, `expiresAt`)?
5. What are the source of truth and cache invalidation paths?

### Step 3 — Define the new key schema

For example:

~~~text
legacy: document::7
new:    document:v3::tenant=alpha|type=Document|id=7
        document:v3::tenant=beta|type=Document|id=7
~~~

Validate/encode every segment and version the namespace; if doing a “read old then rewrite new” migration, **never reuse old values lacking tenant proof**, as they may already contain another tenant's resource. Prefer cold-starting the new cache from scoped trusted data and retiring the old namespace on schedule.

### Step 4 — Update GET, PUT, and EVICT together

Changing a read method's key generator while forgetting eviction/updates leaves stale entries behind. Reads, writes, deletes, retries, prewarmers, and refresh jobs must all share one key name/field/encoding contract.

### Step 5 — Roll out safely

- Block or restrict older service versions from reading tenantless keys.
- Deploy the new `v` namespace and monitor per-tenant cache hits/misses/errors.
- Warm via per-tenant queries from trusted DBs rather than copying legacy entries.
- Monitor cross-tenant anomalies, stale results, and role/permission revocation lag.
- Prepare a rollback strategy that never restores unsafe key schemas.
- Document key schema ownership so another team does not “optimize away” the tenant later.

## 15. Testing beyond the happy path

| Test case | Expectation |
| --- | --- |
| Alpha Document ID 7; Beta Document ID 7 | Two keys, two distinct values |
| Warm alpha, then Bob in beta reads ID 7 | Never returns alpha's data |
| Bob in beta requests `/alpha/7` after alpha is warm | 403/404 per policy, zero cache leak |
| User lacks `document:read`, cache already warm | DENY, no bypass on hit |
| Alice has READ in beta, WRITE in alpha | Global write does not permit PATCH beta |
| Tenant membership revoked after warmup | DENY promptly / within freshness SLA, no decision reuse |
| Two principals in same tenant, different ACLs | Raw cached object may be shared; personalized outputs are not |
| Identical IDs across Document and Invoice | Cache key type separates them |
| Same-tenant queries with differing page/sort/filter | Distinct keys |
| Queries with differing locale/projection | Proper key or output policy |
| NULL/unknown tenant | Fail closed, never fall back to default/global tenant |
| Tenant ID with invalid delimiter/Unicode | Rejected or canonically encoded, zero collisions |
| PATCH alpha:7 | Evicts alpha:7, leaves beta:7 intact |
| DB mutation rollback | Never leaves uncommitted values cached |
| Concurrent reader and writer | Never re-caches stale data past commit beyond freshness SLA |
| ACL/role change | Decision cache invalidated/re-validated |
| Negative-cache NotFound alpha:7 | Does not make beta:7 appear NotFound |
| Redis restart/serializer upgrade | Never misreads legacy keys/schemas |
| Multi-instance cache invalidation | All nodes honor consistency contract |
| `@Async` thread reused | Never carries previous task's tenant |
| RLS/session tenant setting changes | Never causes cache keys to use stale tenant |
| Tenant deleted/suspended | Never serves stale cached data to blocked actors |
| Export/search/CDN/browser caches | Proper tenant/resource/user scope |
| Audit logs | Trusted tenant, principal, action, cache hit/miss; no tokens/PII |

### 15.1. Mutation tests validate the test suite

Intentionally change:

~~~java
@Cacheable(cacheNames = "tenantDocument", key = "#p1")
~~~

in place of `key = "#p0 + ':' + #p1"`. `sameIdInTwoTenantsNeverSharesValue` must turn **red** or return the wrong value. That confirms the suite catches cross-tenant cache collisions.

Next, delete `memberships.requireAction(...)` from the service: `unauthorizedUserCannotReadHotCacheEntry` must fail. Remove `@CacheEvict` from the writer: `updateEvictsOnlyMatchingTenantAndId` must fail. If these three mutations do not turn tests red, the suite is not actually guarding the boundary.

### 15.2. Never assert status 200 alone

A GET returning 200 for beta does not prove correctness. Assert `tenantId`/`title`/owner/allowed fields of **the right tenant**. For sensitive data, negative tests should check that response bodies contain no strings characteristic of other tenants, cache operations are properly namespaced, and DB queries carry tenant predicates.

## 16. Common mistakes to avoid

### Mistake 1 — Keying solely by resource ID

`id=7` can exist in multiple tenants. Key resource data on `(tenant,type,id)`, never `id` alone.

### Mistake 2 — Treating cache name as a tenant namespace

`@Cacheable("document")` only names the cache; if an app-wide cache uses keys without tenant, entries still collide. Put the tenant in the key (or use dedicated per-tenant caches with strict lifecycles/policies, never uncontrolled dynamic cache names).

### Mistake 3 — Reading tenant from ThreadLocal while method args contain only id

Spring's default key generator inspects only parameters. Put trusted tenant into the signature or use a custom key generator with a reliable contract; avoid ambiguous implicit tenant contexts.

### Mistake 4 — Letting the client pick a tenant and treating it as “trusted”

Unvalidated headers/paths/JWTs are not authorization. Verify tenant against principal, membership, action, and ACTIVE tenant status before using it.

### Mistake 5 — Skipping membership checks because tenant is in the key

Keys only prevent collisions; they do not prove the caller has rights. Keep the security boundary running on every hit.

### Mistake 6 — Assuming @Cacheable and @PreAuthorize on one method are always safe

Spring AOP advisor ordering/config can interfere. Prefer two separate beans with security outside caching, and test cache hits with unauthorized users.

### Mistake 7 — Caching personalized responses solely by tenant

Admins and viewers in the same tenant have different field-level redactions. Either cache raw data and redact on every request, or include principal/view/action/policy version in the key instead of sharing full responses.

### Mistake 8 — Caching `allowed=true` by documentId

User, tenant, action, ACL, role/version/expiry can all change. If caching decisions, include complete keys and invalidation; for sensitive resources, prefer not caching allow decisions.

### Mistake 9 — Evicting with a different key than reading

Reads use `alpha:7`, while evictions use `7` or `beta:7`. Stale entries linger and can leak access after ownership changes. Share one factory/key contract across GETs, mutations, refreshes, and jobs.

### Mistake 10 — Invalidating before DB commit and letting readers re-warm stale data

The cache can hold old data after commit. Use after-commit invalidation/versioning per consistency SLA and test race conditions.

### Mistake 11 — Tenant role revoked while ALLOW cache lives on

Cache TTLs do not track revocations automatically. Use revisions/invalidation or live checks in the outer service, with clear hard/soft revocation SLAs.

### Mistake 12 — Storing tokens or PII in Redis keys

Keys frequently show up in scans/logs/metrics and can leak. Use stable opaque IDs, clear namespaces, and appropriate cache access controls/encryption.

### Mistake 13 — Retaining tenantless legacy keys during migration

Old cached entries may already be wrong. Version namespaces, cold-start from trusted sources, and never fall back to old shared keys.

### Mistake 14 — Using Spring object cache keys without checking Redis serializers

Stringified keys can change across upgrades or services. Define a key format contract and safe serializer, and test multi-instance setups.

### Mistake 15 — Correct cache tenant, yet repository misses query the whole DB

Cache misses can still leak. Keep tenant predicates (and ACL scope if needed) in repositories; caches never replace source-of-truth isolation.

### Mistake 16 — Async jobs reusing a prior request's tenant

Thread pools/context propagation and connection pooling can leak tenants. Pass explicit trusted tenant parameters, clean up in `finally`, and re-check policy in workers when needed.

### Mistake 17 — Ignoring caches for lists, search, and exports

Raw queries, pagination, sorting, projections, user ACLs, and negative hits all need proper key dimensions; do not fix only single-document caches.

### Mistake 18 — Overusing `allEntries=true` on every update

Clears caches too broadly, causing thundering herds and hurting availability. Appropriate for intentional migrations or tenant purges, but normal updates should evict by exact key or bump namespace versions.

## 17. Pre-production deployment checklist

| Area | Questions to answer |
| --- | --- |
| Source of truth | Where do tenant/owner/permissions come from, and are they verified? |
| Entrypoints | Do all HTTP/job/queue paths pass the security boundary? |
| Key fields | Are tenant, type, ID, query dimensions, view/user/action all included? |
| Canonicalization | Do IDs/encoding/escaping/lengths prevent collisions? |
| Spring caching | Are `@EnableCaching`, proxy calls, `#p0`, and default keys right? |
| Spring Security | Is `@EnableMethodSecurity` active, with grant/deny tests on cache hits? |
| Storage scope | Do cache-miss queries always enforce `WHERE tenant_id = ?`? |
| ACL | Do object-level policies execute on cache hits? |
| Role freshness | Do membership/decision caches have revocation SLAs/invalidation? |
| Cache write paths | Do `@CacheEvict`/`@CachePut`/manual Redis calls use the exact same key contract? |
| Transactions | Can eviction race with DB commit? Are after-commit/versioning in place? |
| Multi-instance | Are Redis serializers/prefixes and invalidation/restart consistent? |
| Async | Does context avoid leaking across reused workers? |
| Search/export | Are pagination/filters/projections/identities scoped? |
| Security ops | No secrets in keys/logs, proper cache IAM/TLS/encryption? |
| Migration | Are tenantless legacy cache entries never reused? |
| Testing | Same ID across 2 tenants, warm-cache unauthorized access, update/evict, revoke, concurrency? |
| Monitoring | Alerts for cross-tenant anomalies, cache hit/miss, invalidation delay, stale reads? |

## 18. Self-check exercises

**Question 1 — Is default caching safe already?** Method `load(String tenant, Long id)` uses `@Cacheable("tenantDocument")` with no `key`. Will alpha and beta sharing ID 7 collide under the default key?

**Answer:** In Spring Framework 6.x, the default generator builds `SimpleKey(tenant,id)` from all arguments, so those two pairs are normally distinct. Still, validate the tenant, check membership before cache hits, and never change the annotation to `key="#p1"`. If the method accepts only `id` and reads tenant from `ThreadLocal`, the default key is insufficient.

**Question 2 — Is having tenant in the key enough?** Bob does not belong to alpha, yet guesses `alpha:7`. An entry is cached. May Bob read it?

**Answer:** No. Cache key partitioning is not authorization. The outer service must verify `Authentication`, tenant membership, action, and ACL before returning raw data.

**Question 3 — User's role changes after cache warmup?** Alice is no longer an admin of tenant alpha. Redis holds cached `canDelete(alice, Document 7)=true`. May it be used until TTL expires?

**Answer:** Only if your risk model explicitly accepts that freshness window; for sensitive data, invalidate/re-check immediately per SLA or do not cache privileged ALLOWs. Keys must include tenant, principal, action, resource, and policy/ACL/membership versions if using live revisions.

**Question 4 — Why did @CacheEvict miss?** Read key is `alpha:7`, while the update method uses `@CacheEvict(key="#p1")`. Result?

**Answer:** Evicting `7` misses key `alpha:7`, leaving the stale entry intact. Fix eviction to use the exact same factory/key expression and test update→read.

**Question 5 — Why test the exact same ID in two tenants?** If alpha has Document 7 and beta has Document 8, an ID-only key can still pass tests. What happens in production?

**Answer:** When IDs overlap across tenants, cache collisions swap data. Using fixtures with **the same ID in different tenants** deliberately exposes that bug.

**Question 6 — Can personalized responses be cached per tenant?** Two users in alpha: Alice sees salary, Bob sees salary redacted. If the key is only `alpha:employee-7`, what is the risk?

**Answer:** Bob may receive Alice's unredacted version. Either cache raw records per tenant and enforce permissions/redaction **after cache lookup on every request**, or cache views per principal/permission/revision; never store sensitive fields in an unguarded shared cache.

**Question 7 — Is early eviction inside a transaction dangerous?** A transaction updates the DB before committing; the cache is evicted, a concurrent reader sees old DB data and re-caches it; after commit, stale data is still served. Solution?

**Answer:** Use after-commit invalidation, versioned keys, or an appropriate transaction-aware cache strategy; verify with race tests and define consistency SLAs. TTLs alone do not ensure post-commit visibility.

**Question 8 — Is a Redis cache key name authorization?** Redis key `tenant=alpha:id=7`, while the app role can GET any key. Does that isolate tenants at the storage layer?

**Answer:** No. Namespacing prevents logic errors, while storage-level isolation requires Redis ACLs/IAM/network/TLS and separate instances where demanded by the threat model.

## 19. Summary

**Cache keys must accurately reflect data and permission reuse boundaries**:

~~~text
Authentication + trusted tenant/action membership
              |
              v
      Secure application service
              |
              v
     (tenant, resource type, ID, ...)
              |
              +-- HIT: right tenant + still authorize caller
              |
              +-- MISS: tenant-scoped repository query
              |
              v
      optional object ACL + safe response
~~~

Core takeaways:
- Shared caches do not understand tenants on their own; keys must contain **trusted tenant** and every output-shaping dimension.
- Spring default keys look only at **arguments**; custom `key` expressions can accidentally drop tenant despite a complete signature.
- Tenant-scoped data may be shared within a tenant, whereas authorization decisions and personalized responses need **principal/action/policy revision** scoping or no caching.
- The security boundary must execute **on both cache hits and misses**. Separate beans to make proxy/AOP ordering explicit.
- Every read/update/evict path, DB query, Redis key migration, and async context must enforce a consistent tenant.
- TTLs do not replace revocation/invalidation for sensitive permissions; measure freshness and test mid-flight changes across requests.

**Final check question:** “If Bob belongs only to tenant beta while alpha's cache already holds Document 7 warmed by Alice, can Bob receive a single byte of alpha through any controller, service, Redis API, list/search/export, or background job?” If the answer could be yes, the cache is not yet properly enclosed inside the authorization boundary.

## Official references

- [Spring Framework – Declarative Annotation-based Caching](https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html): `@Cacheable`, `@CachePut`, `@CacheEvict`, default `SimpleKeyGenerator`, SpEL `#p0`/`#p1`, `KeyGenerator`, `unless`.
- [Spring Framework – Cache Abstraction](https://docs.spring.io/spring-framework/reference/integration/cache.html): `CacheManager`, proxy behavior, cache providers, and concurrency.
- [Spring Framework – Cache Transaction Support](https://docs.spring.io/spring-framework/reference/integration/cache/strategies.html): transaction-aware cache manager, provider behaviors, and cache configuration.
- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, Spring AOP proxies, and advisor ordering.
- [Spring Security – Authorize HttpServletRequests](https://docs.spring.io/spring-security/reference/servlet/authorization/authorize-http-requests.html): request-level authorization, authentication, and `AuthorizationManager`.
- [Spring Security – Testing with MockMvc](https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/index.html): HTTP security tests and `httpBasic`, `csrf` post-processors.
- [Spring Data Redis – Caching](https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html): `RedisCacheManager`, key prefixes, TTLs, cache configuration, and writers.
