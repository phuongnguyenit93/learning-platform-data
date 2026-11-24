# Keeping Keys Consistent Between Read and Update with `@CachePut` in Spring Cache

## 1. Goal and Scenario

In Spring Cache, `@Cacheable` reads back a stored result, while `@CachePut` executes the method and updates the cache with the **return value**. The two annotations only coordinate properly when they point to the **exact same cache entry**. After this lesson, you will know how to design shared keys, distinguish keys from cache names, choose between `@CachePut` and `@CacheEvict`, handle differing method signatures, and test post-update results.

Suppose there is a product `P1` in organization `acme`:

~~~text
find("acme", "P1")
    -> Product(name="Pen", version=1)

update("acme", "P1", "Blue Pen")
    -> Product(name="Blue Pen", version=2)

find("acme", "P1")
    -> must return Product(name="Blue Pen", version=2)
~~~

If the final `find` call still returns version 1, the common cause is that the read path and update path generate **different keys**, different cache names, or fail to invalidate the old entry. This is a problem of mapping calls to cache identity; it does not resolve itself by adding a TTL.

## 2. Aligning the Entire Cache Identity

A cache entry is logically identified by:

~~~text
(CacheManager or backend, cacheName, key) -> value
~~~

Example that must align:

~~~text
READ:
  manager: mainCacheManager
  cache:   products
  key:     (acme, P1)
  value:   Product(..., version=1)

PUT:
  manager: mainCacheManager
  cache:   products
  key:     (acme, P1)
  value:   Product(..., version=2)
~~~

After `@CachePut`, the same cache-name/key pair must return the new version. Simply declaring `cacheNames = "products"` on both methods is **not enough**: each method might compute keys differently, or two separate `CacheManager`s might each hold a cache with the same name without sharing data.

| Component | Alignment condition | Wrong example |
| --- | --- | --- |
| Manager/Resolver | Same shared datastore/cache | Reading Redis A while writing to local ConcurrentMap |
| `cacheNames` | Read and put paths target the same region | Reading `productsById`, writing `products` |
| Key | Same type, value, and `equals/hashCode` rules | Reading `SimpleKey(tenant,id)`, putting `SimpleKey(tenant,id,name)` |
| Projection/value | Put value is compatible with the type read expects | Read expects `Product`, update returns `boolean` |
| Business scope | Includes all factors that actually affect the result | Missing `tenantId`, `locale`, `viewerId` when they alter results |

Do not compare only `key.toString()` strings: two Java objects of different types can print identically yet not be equal. With distributed caches, you must also consider the serializer, namespace prefix, and how the provider converts the key object into a physical key.

## 3. Why Do Default Keys Often Break Read and Update?

Without `key`/`keyGenerator` configured, Spring uses `SimpleKeyGenerator`:

- No arguments: `SimpleKey.EMPTY`.
- One non-null, non-array argument: the object itself.
- Two or more arguments: a `SimpleKey` holding all arguments in order.

The following example has a bug despite sharing `cacheNames`:

~~~java
// Illustrative example on a service with a repository and Product class.
@Cacheable(cacheNames = "products")
public Product find(String tenantId, String productId) {
    return repository.find(tenantId, productId);
}

@CachePut(cacheNames = "products")
public Product update(String tenantId, String productId, String newName) {
    return repository.update(tenantId, productId, newName);
}
~~~

Actual logical keys:

~~~text
find("acme", "P1")
    -> SimpleKey("acme", "P1")

update("acme", "P1", "Blue Pen")
    -> SimpleKey("acme", "P1", "Blue Pen")
~~~

`@CachePut` puts the new `Product` into **a different entry** from the one cached by `find`. A subsequent `find` can hit the stale entry. You need a key rule based solely on **the result's identity**; here that is `(tenantId, productId)`. `newName` is the updated payload and must not participate in the product's key.

A similar mistake is `find(String id)` using string key `"P1"`, while `update(ProductRequest dto)` defaults to using the DTO itself as the key. The two keys are not automatically equal even if `dto.productId()` returns `"P1"`.

## 4. Crucial Rule: Define Identity Before Writing Annotations

Before writing `key="#p0"`, determine whether two calls can genuinely share one result.

| Operation | Input data | Desired key |
| --- | --- | --- |
| `find(tenantId, productId)` | Organization, product code | `(tenantId, productId)` |
| `update(tenantId, productId, newName)` | Also includes new name | `(tenantId, productId)` |
| `delete(tenantId, productId)` | Organization, product code | `(tenantId, productId)` |
| `findBySku(tenantId, sku)` | SKU-based identifier | Different region or namespace if semantics differ |
| `find(tenantId, productId, currency)` | Price by currency | Add currency if result changes |
| `list(tenantId, category, page)` | List result | Separate query key; not automatically updated by ID-based puts |

Information affecting the **returned content**—such as organization, permission group, locale, currency, or projection version—must be included. Information not affecting the result—such as `requestId`, `traceId`, invocation timestamp, or `auditLogId`—should generally be excluded from the key. Do not rely on a client-supplied tenant identifier without permission checks: verify scope in business logic before returning data, even on cache hits.

At update time, the identifying key must remain stable. If an attribute **used as a key** can change, such as SKU, you must delete or migrate the **old key** in addition to writing the new key; a `@CachePut` to the new key does not clean up the old entry automatically.

## 5. Approach 1: Use the Same `key` (SpEL) Expression

If both methods receive `tenantId` and `productId` in the first two positions, declare them identically:

~~~java
// Illustrative snippet in a service class; repository is an application dependency.
@Cacheable(cacheNames = "products", key = "#p0 + ':' + #p1")
public Product find(String tenantId, String productId) {
    return repository.find(tenantId, productId);
}

@CachePut(cacheNames = "products", key = "#p0 + ':' + #p1")
public Product update(String tenantId, String productId, String newName) {
    return repository.update(tenantId, productId, newName);
}
~~~

`#p0` is the first parameter, `#p1` is the second parameter. `#a0`, `#a1` and `#root.args[0]`, `#root.args[1]` are equivalent ways to access them. Expressions using names like `#tenantId` only work when Spring can discover parameter name metadata; index-based access is more independent of compiler configuration.

**Note on delimiters:** if identifiers can contain `:`, `(tenant="a:b", id="c")` and `(tenant="a", id="b:c")` both produce `"a:b:c"`. That is a key collision. For general inputs, use an encoding with proper escaping/explicit lengths or an immutable structured key object.

If parameter order differs, the expression must change:

~~~java
// productId at index 0, tenantId at index 2.
@CachePut(cacheNames = "products", key = "#p2 + ':' + #p0")
public Product update(String productId, UpdateRequest request,
                      String tenantId) {
    return repository.update(tenantId, productId, request);
}
~~~

Do not copy `#p0 + ':' + #p1` across methods with different signatures. When multiple methods must coordinate, a shared `KeyGenerator` or pure key-factory function is usually easier to maintain.

## 6. Approach 2: A Shared `KeyGenerator` for Read, Put, and Evict

A `KeyGenerator` receives the target object, method, and arguments:

~~~java
// Spring interface signature for reference; do not recreate in your project.
Object generate(Object target, java.lang.reflect.Method method,
                Object... params);
~~~

A generator for this problem takes only the first two identifiers, ignoring `newName` or update metadata:

~~~java
// Illustrative Bean in a configuration class with corresponding Spring imports.
@Bean("productKeyGenerator")
KeyGenerator productKeyGenerator() {
    return (target, method, params) -> {
        if (params.length < 2
                || !(params[0] instanceof String tenant)
                || !(params[1] instanceof String id)) {
            throw new IllegalArgumentException("Expected tenantId and productId");
        }
        return new ProductKey(tenant, id);
    };
}

private record ProductKey(String tenantId, String productId) {}
~~~

`ProductKey` is an immutable Java record with `equals()` and `hashCode()` over both fields. `method.getName()` is **not** included in the key in this example: the names `find`, `update`, and `delete` differ, while all three must target the same entry. The method name only makes sense when you **intentionally** segregate result types, in which case you need a separate invalidation policy.

Using the generator:

~~~java
// Illustrative code showing annotation placement; method bodies depend on repository.
@Cacheable(cacheNames = "products", keyGenerator = "productKeyGenerator")
public Product find(String tenantId, String productId) {
    return repository.find(tenantId, productId);
}

@CachePut(cacheNames = "products", keyGenerator = "productKeyGenerator")
public Product update(String tenantId, String productId, String newName) {
    return repository.update(tenantId, productId, newName);
}

@CacheEvict(cacheNames = "products", keyGenerator = "productKeyGenerator")
public void delete(String tenantId, String productId) {
    repository.delete(tenantId, productId);
}
~~~

`key` and `keyGenerator` are mutually exclusive attributes on the same annotation. `@CacheConfig(cacheNames="products", keyGenerator="productKeyGenerator")` can declare class-level defaults, though it does not enable caching on methods by itself. Even with a shared generator, verify that every method has the identifier parameters in the exact order and types expected by the generator.

## 7. Complete Runnable Example with Java 17 and Spring Boot

This example uses **JDK 17+, Maven, Spring Boot 3.3.5**, and the built-in `ConcurrentMapCacheManager`. A `ConcurrentHashMap` simulates the data source; a counter shows how many times `find` had to read the source. The `CatalogService` bean is invoked from `CommandLineRunner` so Spring's proxy handles the annotations.

Directory structure:

~~~text
consistent-cache-key/
├── pom.xml
└── src/main/java/example/cache/
    ├── DemoApplication.java
    └── CatalogService.java
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
    <artifactId>consistent-cache-key</artifactId>
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

### `src/main/java/example/cache/DemoApplication.java`

~~~java
package example.cache;

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
        return new ConcurrentMapCacheManager("products");
    }

    @Bean("productKeyGenerator")
    KeyGenerator productKeyGenerator() {
        return (target, method, params) -> {
            if (params.length < 2
                    || !(params[0] instanceof String tenant)
                    || !(params[1] instanceof String id)) {
                throw new IllegalArgumentException(
                        "Expected tenantId and productId");
            }
            return new ProductKey(tenant, id);
        };
    }

    private record ProductKey(String tenantId, String productId) {}

    @Bean
    CommandLineRunner demo(CatalogService catalog) {
        return args -> {
            System.out.println(catalog.find("acme", "P1"));
            System.out.println(catalog.find("acme", "P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            System.out.println(catalog.update("acme", "P1", "Blue Pen"));
            System.out.println(catalog.find("acme", "P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            System.out.println(catalog.find("beta", "P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());

            catalog.delete("acme", "P1");
            System.out.println(catalog.find("acme", "P1"));
            System.out.println("sourceReads=" + catalog.sourceReads());
        };
    }
}
~~~

### `src/main/java/example/cache/CatalogService.java`

~~~java
package example.cache;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.cache.annotation.CacheEvict;
import org.springframework.cache.annotation.CachePut;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class CatalogService {
    private final ConcurrentMap<Identity, Product> store =
            new ConcurrentHashMap<>();
    private final AtomicInteger reads = new AtomicInteger();

    public record Product(String tenantId, String productId,
                          String name, int version) {}
    private record Identity(String tenantId, String productId) {}

    public CatalogService() {
        store.put(new Identity("acme", "P1"),
                new Product("acme", "P1", "Pen", 1));
        store.put(new Identity("beta", "P1"),
                new Product("beta", "P1", "Marker", 1));
    }

    @Cacheable(cacheNames = "products", keyGenerator = "productKeyGenerator")
    public Product find(String tenantId, String productId) {
        reads.incrementAndGet();
        return store.get(new Identity(tenantId, productId));
    }

    @CachePut(cacheNames = "products", keyGenerator = "productKeyGenerator")
    public Product update(String tenantId, String productId, String newName) {
        Identity identity = new Identity(tenantId, productId);
        return store.compute(identity, (key, previous) -> {
            if (previous == null) {
                throw new IllegalArgumentException("Product does not exist");
            }
            return new Product(tenantId, productId, newName,
                    previous.version() + 1);
        });
    }

    @CacheEvict(cacheNames = "products", keyGenerator = "productKeyGenerator")
    public void delete(String tenantId, String productId) {
        store.remove(new Identity(tenantId, productId));
    }

    public int sourceReads() {
        return reads.get();
    }
}
~~~

### Running and observing the output

From the `consistent-cache-key` directory:

~~~bash
mvn -q spring-boot:run
~~~

Lines printed by `CommandLineRunner` (Spring startup logs may also appear):

~~~text
Product[tenantId=acme, productId=P1, name=Pen, version=1]
Product[tenantId=acme, productId=P1, name=Pen, version=1]
sourceReads=1
Product[tenantId=acme, productId=P1, name=Blue Pen, version=2]
Product[tenantId=acme, productId=P1, name=Blue Pen, version=2]
sourceReads=1
Product[tenantId=beta, productId=P1, name=Marker, version=1]
sourceReads=2
null
sourceReads=3
~~~

**Step-by-step reading:**

1. The first `find(acme,P1)` misses, reads the source (`sourceReads=1`), and caches `Pen/v1`. The second call hits, still returning `v1` without incrementing the counter.
2. `update(acme,P1,Blue Pen)` **always runs** and returns `Blue Pen/v2`. `@CachePut` writes the new result under key `(acme,P1)`, because the generator ignores the `newName` parameter.
3. `find(acme,P1)` right after the update hits `v2`, so `sourceReads` stays `1`. This is the behavior to verify when building read/update paths.
4. `find(beta,P1)` belongs to a different tenant, so it misses, returns `Marker/v1`, and increments reads to `2`; it does not mistakenly return Acme's result.
5. `delete(acme,P1)` removes the source data and `@CacheEvict` deletes the exact entry. Reading again misses, sees `null`, and increments reads to `3`. Under `ConcurrentMapCacheManager`'s default configuration, `null` results can be cached; negative caching policy is a separate concern.

This example uses an in-memory source and cache within a single JVM, and does not simulate database transactions, TTL, multiple replicas, or real concurrency. Those conditions must be tested additionally with your chosen provider.

## 8. Is using `#result` in `@CachePut` valid?

Unlike `@Cacheable`, which must compute the key for **lookup before running the method**, `@CachePut` computes the key in a post-return context and can use the SpEL variable `#result`.

~~~java
// Illustrative: Product has an id() method, SaveRequest is application-defined.
@CachePut(cacheNames = "productsById", key = "#result.id()")
public Product save(SaveRequest request) {
    return repository.save(request);
}

@Cacheable(cacheNames = "productsById", key = "#p0")
public Product findById(String id) {
    return repository.findById(id);
}
~~~

If `save` returns a `Product` with `id() == "P1"`, `findById("P1")` and `save` share the same key `"P1"` in the `"productsById"` region. This approach is useful when the database generates the ID **upon saving**.

Conditions for safe use:

- `id()` returns the **exact same key type** that the read method uses (e.g., both `String`); a record key and a string are not automatically equal.
- If data is scoped by tenant/scope, the key must also include tenant/scope or use appropriately separated cache names.
- `#result` can be `null`; do not invoke `#result.id()` without guaranteeing a valid result. Design the method to return a valid object or throw an exception, or apply appropriate conditions and test them.
- `#result` in `@CachePut` refers to the value after method completion; supported wrappers like `Optional` are handled according to cache abstraction semantics.
- If a rename changes an old ID to a new ID, putting under the new ID **does not delete the old key**.

A `@Cacheable(key="#result.id()")` is conceptually invalid, because before lookup the method has no new result yet. The read path must construct identity from available input or context. Nor should you put `@Cacheable` and `@CachePut` on the same method: the first can skip the method on a hit, while the second requires the method to always execute.

## 9. `@CachePut` is not always better than `@CacheEvict`

When an update returns **exactly the complete DTO** that reads need, `@CachePut` lets the next read see the fresh result immediately without re-querying the source. However, if the update returns only a status, payload, or something other than the read projection, putting it can leave the wrong data type in the cache.

~~~java
// Counter-example: update returns boolean, while find expects Product.
@CachePut(cacheNames = "products", key = "#p0")
public boolean updateName(String productId, String name) {
    return repository.updateName(productId, name);
}
~~~

Here a `Boolean` gets stored in the cache and could be read by `find` as a `Product`, causing errors. If a method only returns `boolean`/`void`, `@CacheEvict` is usually better:

~~~java
// Illustrative: simply remove the cache entry after the update succeeds.
@CacheEvict(cacheNames = "products", key = "#p0")
public void updateName(String productId, String name) {
    repository.updateName(productId, name);
}
~~~

This snippet assumes the key is `productId` with no multi-tenancy; in real systems you still must align identity with reads.

| Update result | Usually appropriate choice | Why |
| --- | --- | --- |
| Complete new DTO, same read projection | `@CachePut` | Can replace the entry with exact content |
| No new DTO, only `void`/`boolean` | `@CacheEvict` | Subsequent read reloads the exact data type |
| One update affects multiple views | Put the certain region, evict dependent regions | Avoid leaving list/detail caches stale |
| Resource changes ID or moves tenant | Evict old key and put/evict new key | A single put does not clean up the old key |
| Result is sometimes `null` | Explicitly define negative caching, veto, and eviction | Prevent old entries from lingering unintentionally |

`@CacheEvict` deletes after the method succeeds by default. `beforeInvocation=true` changes the execution timing, which should be chosen based on policy when source operations fail. `allEntries=true` clears the entire region, ignoring per-entry keys. On a cache shared across multiple tenants, clearing the whole region may be too broad.

If you use `@CachePut(unless="#result == null")`, the `unless` expression can **veto the put** when the result is null, yet **does not delete the old entry**. If null indicates the data was just deleted or became invalid, merely vetoing the put can leave stale data; key-based eviction is needed.

## 10. Do not overlook indirectly affected caches

For example, product P1 appears in:

~~~text
productsById(acme, P1)
productsByCategory(acme, stationery, page=0)
productsBySearch(acme, "pen", sort=price)
dashboardCounts(acme, today)
~~~

`@CachePut` on `productsById(acme,P1)` **does not automatically refresh** other regions. If name or price changes, lists/searches/stats can go stale. Identify dependent operations and pick a policy:

- `@CacheEvict` on the exact keys of affected results if identifiable.
- `@Caching` to group multiple annotations when one update must affect several known regions.
- Controlled full-region eviction when enumerating all query keys is impossible.
- Use versioning, event invalidation, TTL, or dedicated synchronization mechanisms per business requirements.

Two projections like `ProductSummary` and `ProductDetail` do not necessarily share a cache name/key either; even for the same product, value types differ. Separate regions/namespaces and update or delete each required projection.

## 11. Transactions, concurrency, and distributed caches

Consistent keys **do not guarantee** that database and cache stay consistent under multiple threads or rollbacks.

A race can happen:

~~~text
T1: Reader A starts fetching product v1 from the database (not yet put).
T2: Writer B writes product v2 to the database and puts v2 into the cache.
T3: Reader A finishes slowly, putting v1 into the same key.
T4: Subsequent calls may hit v1 even though the DB is now at v2.
~~~

`@CachePut` does not provide atomicity between database and cache on its own. Check consistency requirements, transaction configuration, advice ordering, and the actual provider. You can use data versioning/optimistic locking, post-commit write policies, a transaction-aware cache manager, `AFTER_COMMIT` events, or outbox patterns if business requirements demand them. Do not assume annotating a method with `@Transactional` makes all cache puts wait for commit by default.

With multiple JVM replicas, the example's `ConcurrentMapCacheManager` is **per-instance local**; putting in one JVM does not automatically update another JVM. When switching to Redis or a distributed cache, verify serializers, key codecs, namespaces, TTLs, and cross-instance visibility of the same cache. Avoid using mutable objects or raw hash codes as keys.

For authorization-sensitive data, a key containing the right tenant/user does not replace per-request authorization checks. `@Cacheable` can return a cache hit without running the method; do not put the sole authorization check inside the read method body and assume it always executes.

## 12. Essential test suite

Do not check only that two annotations share `cacheNames`; test **post-update behavior** through a Spring-managed proxy.

| Test case | Action | Expectation |
| --- | --- | --- |
| Normal hit | `find(acme,P1)` twice | Source read only once |
| Put same identity | `update(acme,P1,newName)` then `find(acme,P1)` | New value appears, no extra source read |
| Different tenant | `find(beta,P1)` | Does not receive Acme's update |
| Extra update parameter | `update(acme,P1,newName,auditId)` | Does not change key if auditId does not affect data |
| Evict | `delete(acme,P1)` then `find(acme,P1)` | Does not return deleted entry |
| Same name, different manager | Put in manager A, read manager B | Must not assume shared data |
| Wrong type | Update returns Boolean, read expects Product | Catches wrong put/evict choice |
| Update failure | Method throws exception | No successful update result to put |
| Transaction rollback | Source data not committed | Cache must not expose uncommitted data |
| Read/write race | Slow read and update run concurrently | Upholds declared consistency level |

In the runnable example, observing `sourceReads` is a useful test: after the first read, `update` increments version, and the subsequent `find` keeps source reads at `1`, proving the cache already holds the new DTO. You can write integration tests with `@SpringBootTest` and `CacheManager`, but use the official key factory when inspecting an entry directly; do not hand-construct a key of a different type.

In production systems, add tests against the provider used in production, especially when keys are records or complex objects; key conversion in Redis/Caffeine can differ.

## 13. Common issues and troubleshooting

| Symptom | Common cause | Check |
| --- | --- | --- |
| Update succeeds, read still stale | Update includes payload in default key | Compare logical keys of read and put |
| Shared generator produces different keys | Generator uses `method.getName()` or wrong parameter position | Inspect record/key components |
| Two keys print identically but miss | Different types, missing `equals/hashCode` | Compare key objects and serializers |
| Same key yet update not seen | Different cache name, manager/resolver/backend | Controlled logging of cacheName, manager, key |
| Product turns into Boolean | `@CachePut` on a status-returning method | Use eviction or return full DTO |
| Wrong tenant data | Key omits tenant or scope | Isolate identity and verify permissions |
| `@CachePut` never triggers | Missing `@EnableCaching`, self-invocation, bean not Spring-managed | Call via bean proxy from another bean |
| Detail cache fresh, list page stale | Put only one entry by ID | Evict/version related query caches |
| Put v2 but later see v1 | Race condition or cache written before rollback | Check transactions/concurrency/versioning |
| Key changes after refactor | Method signature altered or out-of-sync codec | Use shared identity and plan migration |

In default proxy mode, calling `this.update(...)` or `this.find(...)` from **the same bean** does not pass through the cache interceptor. The runnable demo invokes `CatalogService` from another bean (`CommandLineRunner`) so the annotations take effect.

## 14. Self-check exercises

**Exercise 1.** `find(String id)` uses `"products"` with no `key` declared. `update(String id, String name)` uses the same region and also omits `key`. Why can staleness occur?  
**Answer:** `find` defaults to string key `id`, while `update` uses `SimpleKey(id,name)`. You need a shared key based solely on data identity.

**Exercise 2.** Reader uses `(tenantId,productId)`, updater uses `(productId,tenantId)`. Can the two tuples be considered equal?  
**Answer:** No; component order participates in `equals`. Standardize order and types in a single key factory or generator.

**Exercise 3.** When can `@CachePut(key="#result.id()")` be appropriate?  
**Answer:** When a reliable ID is only available after save returns and readers use the same cache name and key type. With multiple tenants, add scope.

**Exercise 4.** `updateName` only returns `boolean`. Should that value be put into the cache where `findById` returns `Product`?  
**Answer:** No. Use `@CacheEvict` or change update to return a full `Product`.

**Exercise 5.** `@CachePut` writes the exact P1 detail record. Why might `searchProducts` results still be stale?  
**Answer:** Query caches have their own keys and regions. Affected projections need invalidation.

**Exercise 6.** A generator adds the method name into the key for both `find` and `update`. Outcome?  
**Answer:** The two methods have different names, so the keys are not equal; put will not replace the entry used by read.

## Official References

- Spring Framework – Declarative Annotation-based Caching (`@Cacheable`, `@CachePut`, `@CacheEvict`, key generation, `@CacheConfig`, proxy): https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework – Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework – `@CachePut` Javadoc, `key`, `#result`, `unless`: https://docs.spring.io/spring-framework/docs/6.1.14/javadoc-api/org/springframework/cache/annotation/CachePut.html
- Spring Boot – Caching provider configuration: https://docs.spring.io/spring-boot/reference/io/caching.html

**Remember:** `@Cacheable` and `@CachePut` must align on **manager/backend, cache name, key type/value, and stored projection**. Keys should rest on stable business identity; test by updating and re-reading through the Spring proxy, while planning invalidation for dependent results.