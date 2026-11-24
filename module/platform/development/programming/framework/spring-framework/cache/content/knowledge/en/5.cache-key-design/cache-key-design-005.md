# Collision Risk Between Multiple Methods Sharing the Same Cache Region

When two or more Spring methods share a cache region (the same **cache name**), they can accidentally generate the **same cache key** even when their return values have completely different meanings. The method called later receives the result stored earlier by the other method, instead of executing its own body. This is a **data correctness bug**: it can display wrong content, cause type errors, or leak data from another context if the key lacks tenant/user information.

In Spring Cache, **@Cacheable** does not automatically attach the class name or method name to the key. Therefore, placing multiple methods into the same cache name is a design decision that must consider both the **key space** and the **value space (type and meaning)**.

## 1. Where Do Collisions Happen?

Consider two methods that both accept **productId** and share the **catalog** cache:

~~~java
@Cacheable(cacheNames = "catalog")
public String productName(String productId) {
    return repository.loadName(productId);
}

@Cacheable(cacheNames = "catalog")
public String productCategory(String productId) {
    return repository.loadCategory(productId);
}
~~~

With the default **SimpleKeyGenerator**, a single **String** parameter normally becomes that string itself. Two invocations:

~~~text
productName("P01")      -> cache "catalog", key "P01"
productCategory("P01")  -> cache "catalog", key "P01"
~~~

look up **the same entry**. If **productName("P01")** is called first, it writes, for example, **"Coffee Maker"**; the next call **productCategory("P01")** may return **"Coffee Maker"** instead of **"Home Appliances"**. The category-loading method does not even run, because Spring encounters a cache hit.

~~~text
                   cacheName = catalog
productName(P01)  ─┐
                    ├─> key = "P01" ─> value = "Coffee Maker"
productCategory(P01)┘       ^
                            └── category() accidentally reads name()'s value
~~~

This situation is easy to miss because both methods return **String**, so no exception is thrown immediately. If one method expects an **Integer** or a different DTO, a wrong cache hit can lead to a **ClassCastException** when returning the result or in caller code, though you should not wait for an exception to notice the bug.

**Critical rule:** Logically, an entry is identified by **(cache region, key)**. Both the region and the key must lead to **a single valid data meaning**. The same key in **two different cache regions** does not inherently collide, even though the cache provider may have its own physical key mapping.

## 2. Why Do Default Keys Easily Collide Across Methods?

Spring uses **SimpleKeyGenerator** when no other **key** or **keyGenerator** configuration is provided:

| Signature | Spring default key | Risk when multiple methods share a cache |
| --- | --- | --- |
| **getVersion()** | **SimpleKey.EMPTY** | Every zero-parameter method sharing the cache collides on keys |
| **findName("P01")** | Value **"P01"** | Collides with any other method also receiving **"P01"** |
| **findPrice("P01", "VND")** | **SimpleKey("P01", "VND")** | Collides with another method having the same parameter tuple |
| **find(query)** | Based on **query** when there is one normal parameter | Depends on how the object represents identity and **equals/hashCode** |

In the case of a single parameter that is **null** or an array, **SimpleKeyGenerator** has special handling instead of always returning the raw object; do not infer key representation from data types using an overly simplistic rule.

Information **not automatically included in the default key**:

- The class name containing the method.
- The method name.
- The return type.
- Parameter names in Java source code.
- The business role of the result, such as **name** vs. **category**.
- Tenant, logged-in user, locale, or permissions if they are not among the parameters participating in key generation.

Consequently, two completely different methods can still share an entry if they use the same cache and produce equal keys.

### Two Zero-Parameter Methods Collide Even More Easily

~~~java
@Cacheable("systemInfo")
public String appVersion() { return buildInfo.version(); }

@Cacheable("systemInfo")
public String deploymentRegion() { return environment.region(); }
~~~

Both calls use the key **SimpleKey.EMPTY** in the **systemInfo** region. If **appVersion()** writes first, **deploymentRegion()** may receive the application version instead of the deployment region name. This also holds true if the two methods reside in **two different beans** yet share that cache name and the same CacheManager.

Changing the call order can change which wrong value is returned. The bug therefore often appears intermittently in environments with concurrent requests.

### True Key Collisions vs. Hash Code Collisions

In a cache backed by a Java map structure, two keys having the same **hashCode** is not enough to make them the same key: the map also uses **equals** comparison to distinguish them. The problem here is two calls **producing keys that are actually equal in logic/comparison**, not merely colliding on hash codes by chance.

Modern Spring uses **SimpleKey** for multiple parameters to build a composite key considering all components, avoiding older-style keys built solely from combining parameter hash codes. Even so, **SimpleKey** does not automatically distinguish method names.

## 3. Practical Consequences

| Situation | Possible consequence |
| --- | --- |
| Two methods return the same **String** type with different meanings | Returns wrong data while appearing to run smoothly |
| One method returns **Product**, the other returns **Price** | Can cause cast exceptions or wrong DTO handling |
| Two endpoints use key **id** for different tenants | Risks cross-tenant data exposure if sharing the same cache namespace |
| First method returns an old snapshot, second needs fresh data | One data kind inherits the results and lifecycle of another |
| Two business groups share a cache with mismatched TTL/eviction | Important entries are evicted prematurely or retained too long |
| Cache update via **@CachePut** collides with a key from another region/method | Overwrites another method's entry |
| Cache removal via **@CacheEvict** collides on keys | Accidentally deletes an entry another method relies on |

Not every key overlap is wrong: two methods that truly share the exact same data contract, type, computation, and freshness requirements **can intentionally share an entry**. However, such cases must be designed, documented, and tested; never assume methods with identical parameters are equivalent.

## 4. Runnable Spring Example: Reproducing Collisions and Fixes

This example uses **Java 17+**, **Spring Framework 6.1.x**, and **ConcurrentMapCacheManager**. It demonstrates the exact case where two methods share a cache and key while returning two different meanings. A counter in each method body shows whether Spring actually executes it.

Directory structure:

~~~text
spring-cache-collision-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/cache/CacheCollisionDemo.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'spring-cache-collision-demo'
~~~

**build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.14'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.cache.CacheCollisionDemo'
}
~~~

**src/main/java/demo/cache/CacheCollisionDemo.java**:

~~~java
package demo.cache;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class CacheCollisionDemo {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager(
                "shared", "sharedNoArg", "safe", "safeNoArg");
    }

    @Bean
    public CatalogService catalogService() {
        return new CatalogService();
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(CacheCollisionDemo.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println(service.name("P01"));
            System.out.println(service.category("P01"));
            System.out.println(service.category("P02"));
            System.out.println(service.name("P02"));

            System.out.println(service.version());
            System.out.println(service.region());

            System.out.println(service.safeName("P01"));
            System.out.println(service.safeCategory("P01"));
            System.out.println(service.safeName("P01"));

            System.out.println(service.safeVersion());
            System.out.println(service.safeRegion());
        }
    }

    public static class CatalogService {
        private int nameLoads;
        private int categoryLoads;
        private int versionLoads;
        private int regionLoads;
        private int safeNameLoads;
        private int safeCategoryLoads;
        private int safeVersionLoads;
        private int safeRegionLoads;

        // BUG: Two methods share both the cache name and default key.
        @Cacheable(cacheNames = "shared")
        public String name(String id) {
            return "name:" + id + ":" + ++nameLoads;
        }

        @Cacheable(cacheNames = "shared")
        public String category(String id) {
            return "category:" + id + ":" + ++categoryLoads;
        }

        // BUG: Two zero-parameter methods share SimpleKey.EMPTY.
        @Cacheable(cacheNames = "sharedNoArg")
        public String version() {
            return "version:" + ++versionLoads;
        }

        @Cacheable(cacheNames = "sharedNoArg")
        public String region() {
            return "region:" + ++regionLoads;
        }

        // FIX: Both methods still share the cache, but use different namespaces.
        @Cacheable(cacheNames = "safe", key = "'name:' + #p0")
        public String safeName(String id) {
            return "safe-name:" + id + ":" + ++safeNameLoads;
        }

        @Cacheable(cacheNames = "safe", key = "'category:' + #p0")
        public String safeCategory(String id) {
            return "safe-category:" + id + ":" + ++safeCategoryLoads;
        }

        // FIX: Zero parameters, yet each method has its own constant key.
        @Cacheable(cacheNames = "safeNoArg", key = "'version'")
        public String safeVersion() {
            return "safe-version:" + ++safeVersionLoads;
        }

        @Cacheable(cacheNames = "safeNoArg", key = "'region'")
        public String safeRegion() {
            return "safe-region:" + ++safeRegionLoads;
        }
    }
}
~~~

Run inside the project directory using a Gradle version compatible with JDK 17:

~~~bash
gradle run --quiet
~~~

Lines printed by **System.out.println** in exact order:

~~~text
name:P01:1
name:P01:1
category:P02:1
category:P02:1
version:1
version:1
safe-name:P01:1
safe-category:P01:1
safe-name:P01:1
safe-version:1
safe-region:1
~~~

Reading the output:

1. **name("P01")** runs first and writes **name:P01:1** under key **"P01"** in cache **shared**.
2. **category("P01")** should return a string starting with **category**, yet receives **name:P01:1**; the **category** body never executed.
3. **category("P02")** misses, returning **category:P02:1**. **name("P02")** afterward wrongly hits and returns the same string.
4. **version()** stores **version:1** under **SimpleKey.EMPTY**. **region()** also receives **version:1**, demonstrating zero-argument collisions.
5. **safeName("P01")** and **safeCategory("P01")** share the **safe** region, yet their keys are **"name:P01"** and **"category:P01"**, respectively, so they do not collide. The third call **safeName("P01")** hits the right entry.
6. **safeVersion()** and **safeRegion()** use two distinct constant keys and therefore receive the right values.

**Why do the annotations take effect?** **@EnableCaching** enables the interceptor, **CatalogService** is a Spring-managed bean, and it is retrieved through ApplicationContext. Calls from **main** go through the proxy. If you instantiate the object directly with **new CatalogService()** and call its methods, **@Cacheable** will not be applied in this way.

**Limitations of the example:** **ConcurrentMapCacheManager** is mainly for illustration and does not provide TTL/capacity-based eviction like individually configured Caffeine or Redis. The code uses no database and demonstrates neither transactions nor distributed caching. The counters are tools to observe whether methods run; real applications need appropriate metrics/tests.

## 5. Preferred Fix: Separate Cache Names by Data Meaning

If two methods return different types of data, have different lifecycles, or belong to two independent business domains, the clearest solution is to create **two cache names**:

~~~java
@Cacheable(cacheNames = "productNames")
public String findName(String productId) {
    return repository.loadName(productId);
}

@Cacheable(cacheNames = "productCategories")
public String findCategory(String productId) {
    return repository.loadCategory(productId);
}
~~~

The same **productId = "P01"** remains identity-safe because they are looked up in two different caches. Moreover, separate cache names let you independently manage **TTL, size, eviction, and metrics** when supported by the provider.

~~~text
("productNames",      "P01") -> "Coffee Maker"
("productCategories", "P01") -> "Home Appliances"
~~~

Note: In distributed caches, verify how the provider maps the **logical cache name** to a **physical key/namespace**. For example, Redis cache configurations usually prefix keys with the cache name; if a team disables the prefix mechanism or manually assigns the same physical namespace to multiple logical regions, re-check for collision risks.

**Do not merge caches merely to reduce the number of names.** Having fewer cache names is not a performance goal in itself. Choose boundaries based on data type, lifecycle, security, observability, and update policies.

## 6. When Sharing a Cache Is Required: Put a Namespace in the Key

Some systems intentionally share a cache to share memory budgets and lifecycles. In that case, the key must reflect the **data type/kind**:

~~~java
@Cacheable(cacheNames = "catalog", key = "'name:' + #p0")
public String findName(String productId) {
    return repository.loadName(productId);
}

@Cacheable(cacheNames = "catalog", key = "'category:' + #p0")
public String findCategory(String productId) {
    return repository.loadCategory(productId);
}
~~~

In SpEL, **'name:'** is a constant string; **#p0** is the first parameter. Using different namespaces prevents two methods from sharing keys even when receiving the same ID.

You can use **#root.methodName** to reduce repetition:

~~~java
@Cacheable(cacheNames = "shared", key = "#root.methodName + ':' + #p0")
public String findName(String productId) { /* ... */ }
~~~

This is only a simple option. **#root.methodName** does not automatically distinguish **different classes with identically named methods** or **overloads producing the same key string output**. Renaming a method also changes the cache key, leaving old data unreachable under the new key. When long-term stability is required, especially with Redis or caches shared across multiple services, use versioned business namespaces such as **"catalog:name:v1:"** and **"catalog:category:v1:"**.

### Avoid Ambiguous String Concatenation

Concatenating **tenant + ":" + id** can collide across different data pairs:

~~~text
tenant="a:b", id="c" -> "a:b:c"
tenant="a",   id="b:c" -> "a:b:c"
~~~

If IDs can contain delimiter characters, use a structured key, length-prefixed encoding, or escaping with clear conventions; do not just insert a **":"** and assume uniqueness. For in-JVM caches, an immutable **record** representing a composite key can fit well; for Redis, you must define how it serializes to physical keys and test accordingly.

Example business key definition (used in Java code, independent of a specific provider):

~~~java
public record ProductCacheKey(
        String namespace, String tenantId, String productId) {}
~~~

An application can construct the same key type inside a **KeyGenerator** or helper when using the Cache API directly. Do not send custom DTOs to Redis before verifying serializer support and key format stability across application versions.

## 7. Use KeyGenerator When Many Methods Must Follow the Same Rule

If dozens of methods need consistent namespacing and key formatting, a **KeyGenerator** can centralize the rule. Example building a key containing the method identifier and parameter set:

~~~java
// Configuration code for a Spring application, not a standalone program.
package demo.cache;

import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.cache.interceptor.SimpleKey;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class CacheKeyConfiguration {

    @Bean("methodAwareKeyGenerator")
    public KeyGenerator methodAwareKeyGenerator() {
        return (target, method, params) -> new SimpleKey(
                method.getDeclaringClass().getName(),
                method.toGenericString(),
                new SimpleKey(params));
    }
}
~~~

Usage declaration:

~~~java
@Cacheable(
    cacheNames = "shared",
    keyGenerator = "methodAwareKeyGenerator"
)
public ProductView findView(String id, String locale) {
    return repository.loadView(id, locale);
}
~~~

**Meaning:** the key carries method information and the parameter list, reducing collisions between methods in the same cache. **SimpleKey** performs composite comparison instead of arbitrary string concatenation.

**However, this is not a universal key for every environment:** **method.getDeclaringClass()**, class names, generic signatures, or interfaces/proxies can change during refactoring or when bean creation changes; Java key objects also depend on serializers in distributed caches. If stability across deployments/services is needed, define an explicit **business namespace and key version**, and test round-trip serialization. **key** and **keyGenerator** are mutually exclusive attributes on the same annotation.

With multiple parameters, the key must also include **all factors that actually change the result**. You cannot fix method collisions with a namespace while accidentally omitting **tenantId**, **currency**, **language**, or access permissions.

## 8. Key Symmetry Across Reads, Writes, and Evictions

Suppose the **catalog** region is shared with two namespaces. Read method:

~~~java
@Cacheable(cacheNames = "catalog", key = "'name:' + #p0")
public String findName(String productId) {
    return repository.loadName(productId);
}
~~~

When updating the product name, the key to evict must use **the exact same expression**:

~~~java
@CacheEvict(cacheNames = "catalog", key = "'name:' + #p0")
public void changeName(String productId, String newName) {
    repository.changeName(productId, newName);
}
~~~

If **key** is omitted on **changeName(productId, newName)**, Spring defaults to creating a **SimpleKey(productId, newName)**, not **"name:P01"**. The old name entry will not be evicted. Similarly, if **@CachePut** writes updated data, it must use the exact read key format to update the right entry and avoid overwriting other namespaces.

~~~java
// Same cache, same namespace => overwrites the exact entry of findName().
@CachePut(cacheNames = "catalog", key = "'name:' + #p0")
public String renameAndReturnName(String productId, String newName) {
    repository.changeName(productId, newName);
    return newName;
}
~~~

The **@CachePut** example assumes **newName** is the final value to cache after a successful update. If the DB normalizes or transforms the name, return the actual value written. When transactions are involved, consider **commit timing** relative to cache eviction/update: unsynchronized DB writes and cache updates can cause race conditions. Placing **@CachePut** and **@Cacheable** on the same method is generally discouraged because one annotation always executes the method while the other may skip the invocation.

**@CacheEvict(allEntries = true)** clears the entire region; this is a valid choice when you genuinely want region-wide invalidation, yet using it routinely to work around wrong keys will wipe cache entries for many other methods and increase load on the data source.

### Do Not Try to Fix It by Changing TTL Alone

A shorter TTL may narrow the window during which the bug appears, yet **does not fix collisions**: immediately after one entry is loaded, another method with the same key can still receive the wrong value. Fix the key identification logic or split the caches.

## 9. Multiple Beans, Tenants, and Access Permissions

### Multiple Beans Sharing the Same CacheManager

**@CacheConfig(cacheNames = "shared")** helps declare a cache name at the class level, yet does not automatically add a class namespace to the key. If two beans both point to **shared** and produce key **"A"**, they can still conflict. Likewise, two differently named methods with identical parameters are not automatically isolated by Spring merely because they live in two different services.

### Tenant/User/Locale Missing from Parameters

~~~java
@Cacheable(cacheNames = "reports", key = "#p0")
public Report report(String reportId) {
    String tenantId = tenantContext.currentTenant();
    return repository.loadReport(tenantId, reportId);
}
~~~

If tenants **A** and **B** have the same **reportId**, results can be wrongly shared. A clearer design is passing tenant as a business parameter:

~~~java
@Cacheable(cacheNames = "reports", key = "#p0 + ':' + #p1")
public Report report(String tenantId, String reportId) {
    return repository.loadReport(tenantId, reportId);
}
~~~

This string expression is only an example when **tenantId/reportId** structures are guaranteed unambiguous; in practice, use a structured composite key or standard encoding when identifiers may contain delimiter characters.

Ensure callers cannot arbitrarily request another tenant: **authorization must be checked independently before using data**, even when a request hits the cache. Putting tenant in the key prevents collisions, yet does not by itself prove the user is permitted to access that tenant. Cross-user data leakage carries far higher severity than a collision between two display strings.

### Objects as Keys

When using a DTO as a single parameter, **equals/hashCode** must match the content that truly determines the output, ideally based on immutable data. Using a mutable object as a key can make lookups/eviction erratic; omitting an important field from the key can cause collisions even when two DTOs are distinct objects. For distributed data, serializers and key normalization must also be defined.

## 10. Implications for Local Cache, Redis, or Multi-Level Caches

| Configuration | Collision likelihood | What to verify |
| --- | --- | --- |
| **ConcurrentMapCacheManager** | Same cache name + equal keys share an entry within one instance | Behavior observable via demos and tests |
| **Caffeine** in JVM | Same cache name/key still collides; adding capacity limits/TTL does not solve key logic | Namespace, key objects, capacity, and eviction |
| **RedisCacheManager** | Cache name normally participates in the Redis key prefix by default | Check prefixes, key conversion, and Redis sharing configuration |
| **Multiple replicas with local cache** | Bugs can manifest per JVM depending on each node's request order | Test across multiple replicas and invalidation paths |
| **Multi-level cache** | Can collide at both local and shared layers if key rules are inconsistent | Align naming, key encoding, and invalidation |

Distinguish the **Spring cache region** from the **physical key in the provider**. In a local map, the key is a Java object; in Redis, the key is usually converted into a stored representation on the server. Two unequal Java keys still require serialization testing when configuration changes, because conversion rules can affect the physical key.

In addition, multiple methods sharing a cache may share **capacity**, **TTL**, refresh mechanisms, and statistics. Even when keys are prefixed, two data groups with different sizes and lifecycles can evict each other or face mismatched expiration policies. Consider separating caches if operational policies differ.

## 11. Testing to Catch Collisions Before Release

A simple test calling **findName("P01")** twice and observing a cache hit is **not enough**. You must test **cross-method calls**.

Recommended steps in a Spring integration test:

1. Initialize a clean **CacheManager** before each test; retrieve the service bean from **ApplicationContext** so calls go through the proxy.
2. Call **method A** with key **K**, verify the expected result and method body execution count.
3. Call **method B** with the same parameter **K**, verify it still returns data matching its contract. For an unintended shared cache, this step catches the bug.
4. Reverse the order: call **B before A**. Results can change when whichever method writes the entry first changes.
5. Test zero-parameter methods, overloaded methods, different beans sharing a cache, and the same ID across two tenants.
6. Test **@CachePut/@CacheEvict** after source updates; verify only the intended entry is replaced/removed and stale data does not linger.
7. Run tests with the actual provider (especially when key serialization/prefix settings differ from local cache) and test cold start, concurrency, and multiple replicas.

Example failure scenario to test:

~~~text
Given: cache "catalog" is empty
When:  findName("P01") returns "Coffee Maker"
And:   findCategory("P01") is called
Then:  findCategory("P01") must return "Home Appliances"
       and must never return "Coffee Maker".
~~~

After changing keys, verify directly or via a spy how many times methods run. If the system has metrics, track hits/misses **per cache**, and add controlled logging for **cache name + key type + namespace**. Avoid logging key values containing sensitive data, emails, tokens, or user identifiers where prohibited.

### When Changing Key Formats in an Environment with Existing Data

Changing a key from **"P01"** to **"name:P01"** causes the application to create new entries; old **"P01"** entries may continue existing until eviction/expiration. If multiple application versions are running concurrently, the older version may still write wrong keys into the shared cache region.

Therefore, plan **compatibility between old and new versions** during deployment: switch to a new cache name, use a versioned namespace, perform controlled cleanup of old keys, or coordinate rollouts so all replicas adopt the new rule together. Flushing an entire production cache must account for miss load hitting the data source.

## 12. Safe Key Design Checklist

Before allowing two methods to share a cache name, answer:

- **Do the values have the same meaning?** Same Java type does not guarantee the same business contract.
- **Can the methods ever generate the same key?** Test zero-parameter cases and realistic parameter combinations.
- **Can the key distinguish the required method/domain/tenant?** Do not rely on default method names.
- **Are all fields that change the output included in the key?** For example locale, currency, policy, user, and data version.
- **Is the key stable and unambiguous?** Consider equals/hashCode, immutable values, encoding, and versioning.
- **Do writes/evictions use the same cache and key as reads?** Match **@Cacheable**, **@CachePut**, and **@CacheEvict**.
- **Do all consumers using the same provider/serializer have compatible conventions?** Especially Redis or multi-service caches.
- **Are TTL, capacity, value types, and security boundaries compatible for sharing one region?**

If compatibility cannot be proven, choosing **separate cache names per data kind** is a safer, easier-to-control default. If sharing is necessary, use sufficiently distinct namespaces, align reads/writes/evictions, and add cross-method tests.

## 13. Self-Check Questions

1. Why can **getVersion()** and **getRegion()** collide on keys when both use **@Cacheable("systemInfo")**, even though the two methods have different names?
2. Why can two methods both returning **String** cause a serious bug without throwing a **ClassCastException**?
3. Distinguish **two keys with the same hashCode** from **two keys that are actually equal** in a map-based cache.
4. When should you separate **cacheNames**, and when should you use a **namespace inside the key**?
5. Why might **key = "#root.methodName + ':' + #p0"** not be enough to distinguish two methods across two beans?
6. If reads use key **"name:P01"**, while cache eviction uses the default key of **changeName("P01", "New Name")**, what happens?
7. Why does changing TTL fail to fix a key collision?
8. When a cache holds per-tenant data, does putting the tenant in the key replace authorization checks?

Mindset to keep: **cache name + key must uniquely identify one data type for one context across every read, write, and eviction path**. Only when data equivalence is proven should multiple methods intentionally reuse a single entry.

### Official Documentation

- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Default Key Generation, Custom Key, SpEL, @Cacheable, @CacheEvict: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Spring AOP proxying: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — SimpleKeyGenerator API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html
- Spring Data Redis — Redis Cache configuration and prefix behavior: https://docs.spring.io/spring-data/redis/reference/redis/redis-cache.html
