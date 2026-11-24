# @Caching for Grouping Multiple Operations on One Method

Spring Framework's **@Caching** allows **grouping multiple cache annotations on the same method**. A single business action often needs to affect multiple storage regions: updating a lookup-by-ID cache, updating a lookup-by-SKU cache, and clearing stale summary lists. Updating only one entry can leave other read paths returning inconsistent data. **@Caching** declares the related actions on a single invocation instead of creating artificial methods just to attach annotations.

The three supported groups are **cacheable**, **put**, and **evict**, holding **@Cacheable**, **@CachePut**, and **@CacheEvict** respectively. However, **@Caching is not a transaction**; it does not automatically fix wrong keys, does not guarantee atomic updates across multiple caches, and does not synchronize across multiple nodes. Those concerns must be designed and tested separately.

## 1. Structure and Meaning

~~~java
@Caching(
    cacheable = { /* @Cacheable annotations */ },
    put = { /* @CachePut annotations */ },
    evict = { /* @CacheEvict annotations */ }
)
public ReturnType method(Arguments args) {
    // Business logic
}
~~~

| Group | Meaning | Typical Behavior |
| --- | --- | --- |
| **cacheable** | Read result from cache if present; on miss, execute and store | A cache hit can skip the method body |
| **put** | Execute method and place the returned result into the cache | Method must run to produce the result for @CachePut |
| **evict** | Delete a key or all entries of a cache | By default, deletes after the method completes normally |

Each nested annotation can have **cacheNames**, **key**, **condition**, and its own specific attributes. For example, **@CacheEvict** has **allEntries** and **beforeInvocation**; **@CachePut** has **unless** and can use **#result** in its key after the method returns.

**@Caching is purely a grouping annotation.** If a single action is enough, use **@Cacheable**, **@CachePut**, or **@CacheEvict** directly. If the same key and same operation type apply to multiple caches, a single annotation with multiple cacheNames can be shorter:

~~~java
@CacheEvict(cacheNames = {"productsById", "productsBySku"}, key = "#p0")
public void invalidate(String id) {
    // Only valid when both caches genuinely use the same key id.
}
~~~

If one region uses key **id** while the other uses key **sku**, this single annotation is insufficient. In that case, **@Caching** allows describing each key separately.

## 2. @Caching(evict): Invalidating Multiple Related Caches

For example, renaming a Product can stale the detail cache and summary views:

~~~java
@Caching(evict = {
    @CacheEvict(cacheNames = "productById", key = "#p0"),
    @CacheEvict(cacheNames = "productSummary", key = "#p0"),
    @CacheEvict(cacheNames = "productCatalog", allEntries = true)
})
public void rename(String productId, String newName) {
    repository.rename(productId, newName);
}
~~~

After the method succeeds, Spring instructs removing the entry from **productById** and **productSummary** by productId, and clearing **all entries specifically in the productCatalog cache**. Subsequent reads must reload data according to the rules of the read methods.

**allEntries = true** evicts the entire specified cache region, not every cache in the CacheManager. When using **allEntries**, do not declare an individual key expecting selective eviction. Weigh the cost: a large list with many entries can trigger simultaneous cache misses after clearing the whole region.

### Eviction timing: beforeInvocation

~~~java
@Caching(evict = {
    @CacheEvict(
        cacheNames = "reportSnapshot",
        key = "'latest'",
        beforeInvocation = true),
    @CacheEvict(
        cacheNames = "reportStats",
        allEntries = true,
        beforeInvocation = true)
})
public void rebuildReport() {
    reportService.rebuild();
}
~~~

By default **beforeInvocation = false**: eviction happens after the method completes normally. If the method throws an exception, post-invocation eviction generally does not occur. With **beforeInvocation = true**, the cache is cleared **before** the method runs, even if the method later fails.

You cannot use **#result** in the key of an eviction running **before invocation**, because the result does not exist yet. Post-invocation eviction can use **#result** where context supports it, though avoid depending on null results and test thoroughly.

In applications with database transactions, when the method returns successfully and when the transaction **commits** do not necessarily coincide. Evicting before commit can let another thread miss and load old DB data. **@Caching does not solve this race automatically**; when strict consistency is needed, choose an after-commit policy, event-driven invalidation, or appropriate transaction-cache coordination.

## 3. @Caching(put): Writing One Result into Multiple Caches

If a Product is looked up by **id** and **sku**, each region has its own key. A method saving a Product can warm both caches:

~~~java
@Caching(put = {
    @CachePut(cacheNames = "productById", key = "#result.id()"),
    @CachePut(cacheNames = "productBySku", key = "#result.sku()")
})
public Product save(Product product) {
    return repository.save(product);
}
~~~

**@CachePut** requires executing the body of **save(...)**, then storing the return value; **#result** is populated at that stage. The example assumes **Product** is a Java record with two accessors **id()** and **sku()**, a non-null result, and both identifiers properly assigned by the repository.

Things to verify:

- **Do read methods use the same keys?** **findById(id)** must read from **productById[id]**, while **findBySku(sku)** reads from **productBySku[sku]**.
- **Do cached values share the same type/meaning?** If one cache stores Product, another method expecting String cannot use the same key there.
- **Can SKU change?** Writing a new SKU key does not remove the old SKU entry; you must evict the old key or use a different indexing mechanism.
- **What if the method returns null?** You may need **unless = "#result == null"** to skip caching and avoid invoking accessors on null.
- **What if one put fails?** Earlier successful puts are not rolled back automatically.

When caches share the same key, same value, and same policy, **@CachePut(cacheNames = {"A", "B"}, key = "#p0")** can be more concise. When keys differ, **@Caching(put = {...})** is clearer.

## 4. Combining @Caching(put = ..., evict = ...)

A method updating a Product can simultaneously:

1. Write the new Product into **productById** by ID.
2. Write the new Product into **productBySku** by SKU.
3. Clear the **productList** cache, because the list depends on multiple Products.

~~~java
@Caching(
    put = {
        @CachePut(cacheNames = "productById", key = "#result.id()"),
        @CachePut(cacheNames = "productBySku", key = "#result.sku()")
    },
    evict = {
        @CacheEvict(cacheNames = "productList", allEntries = true)
    }
)
public Product rename(String id, String newTitle) {
    return repository.rename(id, newTitle);
}
~~~

This is an easy-to-reason-about use of **@Caching**: two index caches are updated with the new value, while the aggregate cache must be recomputed. Every nested annotation has a clear contract.

Do not intentionally both **put** and **evict** the *exact same cache/key* in a single invocation and rely on detailed ordering to guess whether the final entry exists. Design non-conflicting operations and write tests confirming the desired state.

## 5. @Caching(cacheable = ...): Multiple Conditional Lookups

~~~java
@Caching(cacheable = {
    @Cacheable(
        cacheNames = "catalogPublic",
        key = "#p0",
        condition = "#p1 == true"),
    @Cacheable(
        cacheNames = "catalogInternal",
        key = "#p0",
        condition = "#p1 == false")
})
public Catalog catalog(String category, boolean publicView) {
    return repository.load(category, publicView);
}
~~~

The two **conditions** are mutually exclusive based on publicView, so an invocation intentionally uses only one of the two cache regions. This is an illustrative example, not an authorization mechanism: internal data must still enforce authorization checks before access.

If multiple **@Cacheable** annotations match at once, a cache hit in one region can affect whether the method runs or how remaining caches get populated. Do not group arbitrarily; test both cache A hit / B miss and vice versa. If two methods/data flows are independent, separating methods or using one clear key strategy is often easier to maintain.

### Do not confuse with @CacheConfig

**@CacheConfig** declares class-level defaults such as cacheNames, keyGenerator, or cacheManager. **@Caching** groups multiple annotations on one method. They solve different needs and can be used together when appropriate.

## 6. Why should you not arbitrarily group @Cacheable with @CachePut?

The following configuration has conflicting goals:

~~~java
@Caching(
    cacheable = { @Cacheable(cacheNames = "items", key = "#p0") },
    put = { @CachePut(cacheNames = "items", key = "#p0") }
)
public Item load(String id) {
    return repository.findById(id);
}
~~~

**@Cacheable** allows skipping the method body when data already exists; **@CachePut** aims to run the method to obtain a fresh result. Spring recommends avoiding combining these two annotations on the same method, except for specially designed and tested mutually exclusive **conditions**. Wrapping them inside **@Caching** does not remove the semantic conflict.

The standard structure is clearer:

~~~java
@Cacheable(cacheNames = "items", key = "#p0")
public Item find(String id) {
    return repository.findById(id);
}

@CachePut(cacheNames = "items", key = "#result.id()")
public Item save(Item item) {
    return repository.save(item);
}
~~~

A read method supports cache hit/miss, while a write method always runs and refreshes the cache. Do not place **@Cacheable** on methods that must execute side effects such as payments, sending emails, or updating a DB.

## 7. Runnable Java 17/Spring Example: Two Puts + One Evict

Minimal example using **Spring Framework 6.1.14**, **Java 17+**, and **ConcurrentMapCacheManager**. Source data resides in a Map to clearly observe cache hits/misses; each read method increments a counter **only when the method body executes**. The rename method returns a new Product and has **@Caching(put = {...}, evict = {...})**.

Project layout:

~~~text
spring-caching-demo/
├── settings.gradle
├── build.gradle
├── src/main/java/demo/cache/CachingDemo.java
└── src/test/java/demo/cache/CachingDemoTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-caching-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
    testImplementation 'org.springframework:spring-test:6.1.14'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.10.2'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.10.2'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.CachingDemo'
}

test {
    useJUnitPlatform()
}
~~~

**src/main/java/demo/cache/CachingDemo.java**

~~~java
package demo.cache;

import java.util.HashMap;
import java.util.Map;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.Caching;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CachingDemo {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
                "productsById", "productsBySku", "productList");
    }

    @Bean
    public CatalogService catalogService() {
        return new CatalogService();
    }

    public record Product(String id, String sku, String title) {}

    public static class CatalogService {
        private final Map<String, Product> source = new HashMap<>(
                Map.of("P01", new Product("P01", "SKU-1", "Tea")));

        private int idLoads;
        private int skuLoads;
        private int listLoads;

        @Cacheable(cacheNames = "productsById", key = "#p0")
        public Product byId(String id) {
            idLoads++;
            return source.get(id);
        }

        @Cacheable(cacheNames = "productsBySku", key = "#p0")
        public Product bySku(String sku) {
            skuLoads++;
            return source.values().stream()
                    .filter(p -> p.sku().equals(sku))
                    .findFirst().orElse(null);
        }

        @Cacheable(cacheNames = "productList", key = "'all'")
        public String list() {
            listLoads++;
            return source.get("P01").title() + "|listLoads=" + listLoads;
        }

        @Caching(
            put = {
                @CachePut(
                    cacheNames = "productsById",
                    key = "#result.id()"),
                @CachePut(
                    cacheNames = "productsBySku",
                    key = "#result.sku()")
            },
            evict = {
                @CacheEvict(
                    cacheNames = "productList",
                    key = "'all'")
            }
        )
        public Product rename(String id, String title) {
            Product previous = source.get(id);
            if (previous == null) {
                throw new IllegalArgumentException("Unknown id: " + id);
            }
            Product updated = new Product(previous.id(), previous.sku(), title);
            source.put(id, updated);
            return updated;
        }

        public String loads() {
            return "id=" + idLoads + ",sku=" + skuLoads
                    + ",list=" + listLoads;
        }
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(
                CachingDemo.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println("id1=" + service.byId("P01"));
            System.out.println("idHit=" + service.byId("P01"));
            System.out.println("sku1=" + service.bySku("SKU-1"));
            System.out.println("list1=" + service.list());
            System.out.println("listHit=" + service.list());
            System.out.println("updated=" + service.rename("P01", "Coffee"));
            System.out.println("idAfter=" + service.byId("P01"));
            System.out.println("skuAfter=" + service.bySku("SKU-1"));
            System.out.println("listAfter=" + service.list());
            System.out.println("loads=" + service.loads());
        }
    }
}
~~~

In the project directory, run with an installed Gradle (or the project's Gradle wrapper if present):

~~~bash
gradle run --quiet
~~~

Expected **System.out.println** lines, in exact order:

~~~text
id1=Product[id=P01, sku=SKU-1, title=Tea]
idHit=Product[id=P01, sku=SKU-1, title=Tea]
sku1=Product[id=P01, sku=SKU-1, title=Tea]
list1=Tea|listLoads=1
listHit=Tea|listLoads=1
updated=Product[id=P01, sku=SKU-1, title=Coffee]
idAfter=Product[id=P01, sku=SKU-1, title=Coffee]
skuAfter=Product[id=P01, sku=SKU-1, title=Coffee]
listAfter=Coffee|listLoads=2
loads=id=1,sku=1,list=2
~~~

The second **byId** call hits so **idLoads** remains 1; **bySku** loaded once. **list** hits on the second call so **listLoads** remains 1. After **rename**, the two **@CachePut** annotations place the new Product into caches by ID/SKU, so both read paths hit without incrementing load counts. **@CacheEvict** deletes the **"all"** key of **productList**, causing **list()** to re-run and increment **listLoads** to 2.

The key outcome is **loads=id=1,sku=1,list=2**: proving the two index caches were refreshed via put, while the list cache was invalidated.

**Note:** **#result.id()** and **#result.sku()** invoke the Java record accessors on the return value. The code assumes id/sku do not change and the result is non-null. If an update changes the SKU, the entry with the old SKU would still remain and must be deleted separately.

### Testing Spring with JUnit 5

**src/test/java/demo/cache/CachingDemoTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.CacheManager;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.*;

@SpringJUnitConfig(CachingDemo.class)
class CachingDemoTest {

    @Autowired
    CachingDemo.CatalogService service;

    @Autowired
    CacheManager cacheManager;

    @Test
    void renameRefreshesTwoIndexesAndEvictsTheList() {
        CachingDemo.Product original = service.byId("P01");

        assertEquals(original, service.byId("P01"));
        assertEquals(original, service.bySku("SKU-1"));
        assertEquals("Tea|listLoads=1", service.list());
        assertEquals("Tea|listLoads=1", service.list());
        assertEquals("id=1,sku=1,list=1", service.loads());

        assertNotNull(cacheManager.getCache("productList").get("all"));

        CachingDemo.Product updated = service.rename("P01", "Coffee");

        assertEquals(updated,
                cacheManager.getCache("productsById")
                        .get("P01", CachingDemo.Product.class));
        assertEquals(updated,
                cacheManager.getCache("productsBySku")
                        .get("SKU-1", CachingDemo.Product.class));
        assertNull(cacheManager.getCache("productList").get("all"));

        assertEquals(updated, service.byId("P01"));
        assertEquals(updated, service.bySku("SKU-1"));
        assertEquals("Coffee|listLoads=2", service.list());
        assertEquals("id=1,sku=1,list=2", service.loads());
    }
}
~~~

Run:

~~~bash
gradle test
~~~

**Expected:** one passing JUnit test. The test verifies **all three consequences** of a single rename call: the ID cache is updated, the SKU cache is updated, the list cache loses its stale entry and the next read reloads. Checking only byId would not prove the other two caches are also right.

This is a real Spring project with calls going through a Spring bean, not a single Java file needing only javac. **ConcurrentMapCacheManager** is an in-JVM cache used for illustration, lacking TTL/size-based eviction like separately configured providers.

## 8. Processing Timing, Conditions, and Pitfalls to Watch

### Conditions on nested annotations

Each nested annotation has its own condition. Example:

~~~java
@Caching(put = {
    @CachePut(
        cacheNames = "productsById",
        key = "#result.id()",
        unless = "#result == null"),
    @CachePut(
        cacheNames = "productsBySku",
        key = "#result.sku()",
        unless = "#result == null")
})
public Product save(Product input) {
    return repository.save(input);
}
~~~

**condition** is evaluated based on pre-method context, suited for deciding caching from inputs. **unless** on **@Cacheable/@CachePut** allows evaluating the post-method result. **@CacheEvict** does not have **unless**, but has condition, beforeInvocation, and allEntries. If nested annotations have different conditions, do not assume the entire group always activates together.

### Cache hits and side effects

With **@Caching(cacheable = {...})**, a cache hit can prevent the method from being called. Do not place mandatory side effects inside the method body if it can be short-circuited. With **@Caching(put = {...})**, the method body still runs to produce data, yet that does not guarantee all puts across multiple caches succeed.

### Proxies and self-invocation

Requires **@EnableCaching**, **CacheManager**, and calls passing through a Spring-managed proxy. In proxy mode, **this.method()** from the same bean typically bypasses the cache interceptor; calling directly on **new CatalogService()** also does not trigger annotations. Integration tests must fetch beans from ApplicationContext as in the example.

### Transactions and partial failures

A group of three annotations is not an atomic transaction: if Redis or the second cache fails, the first cache may already have changed. Exception behavior depends on CacheErrorHandler and the provider. The ordering of invalidation relative to DB commit can create race conditions; when strict consistency is required, consider transaction-aware caches, after-commit invalidation, events/outbox, or re-checking the data source.

## 9. Key Rules, Identifier Changes, and Multi-Tenant Data

A common mistake is caching reads with key **id**, while a write method takes parameters **(id, newName)** and omits a key on **@CacheEvict**. The default key of the write method then becomes the tuple **(id, newName)** rather than **id**; the old entry is not deleted.

Similarly, **@CachePut(key = "#result.sku()")** updates the new SKU without deleting the old SKU if the SKU changed. You must capture both **before** and **after** values during an update. If results depend on **tenantId, locale, currency, or permissions**, the key must distinguish those factors; never let two tenants with the same ID share one entry. Including tenant in the key does not replace authorization.

Ensure caches have compatible value types, serializers, TTLs, and lifecycles for their usage. In Redis, check cache-name prefixes, key conversion, and cross-node invalidation mechanisms; in local caches, each JVM maintains separate state. **@Caching** does not automatically broadcast invalidations to local caches on other nodes.

## 10. Comparison for Choosing Annotations

| Requirement | Appropriate Approach |
| --- | --- |
| Only read a cached result | **@Cacheable** |
| Only write a cached result | **@CachePut** |
| Only delete an entry | **@CacheEvict** |
| Same action, same key across multiple regions | One annotation with multiple **cacheNames** |
| Evict multiple regions with different keys/conditions | **@Caching(evict = {...})** |
| Write one result across multiple indexes (id, sku) | **@Caching(put = {...})** |
| Write two indexes, invalidate a list | **@Caching(put = {...}, evict = {...})** |
| Multiple mutually exclusive cacheables by input | **@Caching(cacheable = {...})** when cleanly designed/tested |
| Set default cache name or keyGenerator at class level | **@CacheConfig** |
| Need transactional atomicity across multiple caches | Design consistency/transaction separately; **@Caching is insufficient** |

An overly large annotation group can signal that too many data items are tightly coupled. You may need to split cache boundaries, use invalidation events, or introduce a cleaner business service layer.

## 11. Testing Checklist When Using @Caching

1. **Seed caches before testing:** if the list cache is already empty, asserting it is empty after update does not prove eviction ran.
2. **Invoke methods through Spring beans:** verify annotations are actually handled by the interceptor.
3. **Verify write method execution:** especially with @CachePut, side effects must not be skipped.
4. **Verify every put entry:** correct cache name, key, and Product type.
5. **Verify every evicted entry:** after update, old values are gone; the next read loads current data.
6. **Verify unrelated data:** changing P01 must not affect P02 or another tenant using a wrong entry.
7. **Verify error paths:** method exceptions, beforeInvocation true/false, cache provider disconnects.
8. **Verify transaction/concurrency:** can a concurrent read populate stale data into cache during the commit window?
9. **Verify key changes:** when ID/SKU changes or cache names change, is old-entry deletion in place?
10. **Verify with a production-like provider:** Redis, Caffeine, multiple replicas, serializers/TTLs differing from the demo cache.

Testing only the final value of a single read path is insufficient. A **@Caching** group must be tested **per nested operation** and on overall post-call state.

## 12. Common Mistakes and Self-Check

- **Forgetting a related cache region:** map out all read paths and required invalidations.
- **Wrong keys across read/write/delete:** compare each annotation's expression with the actual read method.
- **Overusing allEntries = true:** can trigger cache-miss storms and spike DB load.
- **Expecting @Caching to be transactional:** handle partial failures, commits, and retries/invalidation.
- **Combining conflicting cacheable and put:** separate read/write methods unless mutually exclusive conditions are proven.
- **Accessing #result before it exists:** use only in appropriate post-method operation phases.
- **Forgetting the old SKU when changing SKU:** old index entries do not vanish on their own.
- **Self-invocation:** annotations can be bypassed when calling methods on the same bean in proxy mode.
- **Not testing exception paths:** beforeInvocation alters eviction timing when a method fails.
- **Confusing @CacheConfig with @Caching:** one sets class-level defaults, the other groups method-level actions.

Review questions:

1. When is **@CacheEvict(cacheNames = {"A", "B"})** sufficient, and when is grouping with **@Caching(evict = {...})** required?
2. Why can **@CachePut** for two caches by ID/SKU use two different **#result** expressions?
3. After changing a SKU, why does putting by the new SKU not guarantee the old SKU entry is deleted?
4. What does **beforeInvocation = true** do if the method throws an exception?
5. Why should **@Cacheable** and **@CachePut** not be unconditionally grouped on the same method?
6. Why does a test checking only **byId** after rename fail to prove the three-operation group works properly?
7. When the second cache operation fails after the first cache was put, does **@Caching** automatically roll back?

**Conclusion:** **@Caching** lets you declare a group of cache actions for a single method, especially useful when **updating multiple indexes and invalidating dependent views**. Correctness depends on keys, cache names, conditions, eviction timing, data-source consistency, and thorough testing of every cache—not merely grouping annotations.

### Official Documentation

- Spring Framework — Annotation-based caching, @Caching, @CachePut, @CacheEvict: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — AOP proxy semantics: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — @Caching Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/Caching.html
- Spring Framework — @CachePut Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Framework — @CacheEvict Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/annotation/CacheEvict.html
