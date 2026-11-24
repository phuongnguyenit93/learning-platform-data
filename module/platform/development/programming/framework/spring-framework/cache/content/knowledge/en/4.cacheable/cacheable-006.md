# @Cacheable: Parameterized Methods and No-Argument Methods

When annotating a method with **@Cacheable**, Spring can store the execution result so subsequent invocations read it back from the cache. What determines whether an invocation can share a stored result is **cache name + cache key**. The number and values of method parameters directly influence how Spring generates the default key. A method with no parameters can still be cached, though all of its invocations default to using the same key in the chosen cache.

This lesson focuses on how **@Cacheable** works with zero-parameter, single-parameter, and multi-parameter methods; how to choose keys when parameters do not fully represent the data; and mistakes that can cause wrong results to be returned.

## 1. From Method Invocation to Cache Key

Each time a call passes through the Spring cache interceptor:

1. Spring resolves the cache based on **cacheNames/value** (or cache resolver configuration).
2. Spring computes the key: using the **key** attribute, **keyGenerator**, or the default **SimpleKeyGenerator**.
3. If the cache contains that key (**hit**), Spring returns the stored value without running the method body.
4. If absent (**miss**), Spring executes the method, receives the result, and stores it in the cache, unless a condition prevents storage or the provider cannot store it.
5. Subsequent calls with the same cache name and key can reuse the result, even if external data has changed when no invalidation/expiration has occurred.

~~~text
Invoke service.method(args)
          |
          v
     Spring proxy
          |
          v
  Select cache name + compute key
          |
          +---- HIT  ------> Return cached result
          |
          +---- MISS ------> Run method ------> Store in cache ------> Return result
~~~

**@Cacheable does not create its own cache engine.** Spring provides the abstraction and interceptor; storage mechanics, TTL, capacity, cross-instance sharing, and error policies depend on the **CacheManager** and provider (ConcurrentMap, Caffeine, Redis...). Thus the key examples below apply to Spring's default mechanism, while entry lifetime must be designed separately.

## 2. Default Key Rules by Parameter Count

Spring defaults to **org.springframework.cache.interceptor.SimpleKeyGenerator**:

| Method signature | Example call | Default key |
| --- | --- | --- |
| No parameters | **loadConfig()** | **SimpleKey.EMPTY** |
| One parameter | **findById("P01")** | The value **"P01"** |
| Multiple parameters | **findByRegion("P01", "vi")** | **SimpleKey("P01", "vi")** |
| Two multi-parameter calls with different order | **findByRegion("P01", "vi")** and **findByRegion("vi", "P01")** | Two different key combinations |
| One parameter that is a complex object | **findByFilter(filter)** | Depends on how the object is used as a key and the correctness of **equals/hashCode** |

These are the common rules. In the **SimpleKeyGenerator** implementation, cases where the sole parameter is **null** or an array type are handled specially rather than always returning the parameter object directly; do not rely on a simplistic assumption that every single-parameter call has a key equal to that object itself.

**The cache name is also part of the lookup scope.** Key **"P01"** in the **products** cache does not automatically collide with key **"P01"** in the **productPrices** cache. Conversely, **Spring does not automatically include the method name or class name in the default key**. Two methods using the same cache name and generating the same key can accidentally reuse each other's results.

For example: **findProduct("P01")** and **findPrice("P01")** both pointing to the **shared** cache will share key **"P01"**. If one method stores **Product** and the other expects **Price**, results can be wrong or trigger type-casting errors. Choose cache names aligned with data types and semantics, or design clearly namespaced keys.

## 3. No-Argument Methods: All Calls Share One Key

~~~java
@Cacheable(cacheNames = "homepageStatistics")
public HomepageStatistics loadHomepageStatistics() {
    return statisticsRepository.calculate();
}
~~~

The first call passing through the Spring proxy is typically a cache miss: the method computes statistics and stores the result under key **SimpleKey.EMPTY** in the **homepageStatistics** cache. Subsequent calls to the same cache/key return from the cache, regardless of when they are called, until the entry is evicted, expires, or is replaced.

### When is this useful?

- The result is an application-wide shared configuration that does not vary by caller.
- A global statistics snapshot that can tolerate update latency.
- Global reference data that is expensive to load and changes infrequently.

Common benefit: only **one key** for that method in the cache; easy to warm up and creates no extra entries across varying arguments.

### Risks to anticipate

**Having no parameters does not mean the result is invariant.** The method body may read the clock, database, environment variables, current tenant, locale, or login context. For example:

~~~java
@Cacheable(cacheNames = "dashboard")
public DashboardData dashboardForCurrentUser() {
    String userId = securityContext.currentUserId();
    return repository.findDashboard(userId);
}
~~~

This approach is **incorrect cache design** if multiple users hit the same cache: every user could receive the first user's result because every call uses **SimpleKey.EMPTY**. The fix is to accept the user identifier as a parameter and include it in the key:

~~~java
@Cacheable(cacheNames = "dashboardByUser", key = "#p0")
public DashboardData dashboardForUser(String userId) {
    return repository.findDashboard(userId);
}
~~~

Tenant identifiers, access permissions, and any factors determining output content must also be represented in the key. Caching does not replace authorization checks. The methods above are **illustrative code in a Spring application with a real repository and security context**, not standalone Java programs.

### Two no-argument methods sharing a cache

~~~java
@Cacheable(cacheNames = "systemInformation")
public String appVersion() { return versionProvider.currentVersion(); }

@Cacheable(cacheNames = "systemInformation")
public String deploymentRegion() { return regionProvider.region(); }
~~~

Both methods compute **SimpleKey.EMPTY** in **systemInformation**. This is a conflict: a call to the second method can receive the result of the first.

There are two sensible fixes:

~~~java
// Approach A: separate caches by data meaning.
@Cacheable(cacheNames = "appVersion")
public String appVersion() { return versionProvider.currentVersion(); }

@Cacheable(cacheNames = "deploymentRegion")
public String deploymentRegion() { return regionProvider.region(); }
~~~

~~~java
// Approach B: keep one cache but assign distinct constant keys.
@Cacheable(cacheNames = "systemInformation", key = "'version'")
public String appVersion() { return versionProvider.currentVersion(); }

@Cacheable(cacheNames = "systemInformation", key = "'region'")
public String deploymentRegion() { return regionProvider.region(); }
~~~

In **key = "'version'"**, the single quotes are **Spring Expression Language (SpEL)** string literal syntax; Spring generates the key as the string **version**, not a variable name.

## 4. Single-Parameter Methods: One Key per Value

~~~java
@Cacheable(cacheNames = "products")
public Product findById(String id) {
    return productRepository.findById(id).orElse(null);
}
~~~

Example:

~~~text
findById("P01") -> miss -> read source and store under key "P01"
findById("P01") -> hit  -> reuse result
findById("P02") -> miss -> key "P02" is different
~~~

If the method takes **Long id**, the default key is a **Long** value; if it takes **String id**, the key is a **String**. Do not assume the characters **"42"** and the number **42L** form the same key. Spring-generated keys may also be converted/serialized by the provider under its own rules, so verify when switching providers or parameter types.

If the parameter is an object whose **equals()/hashCode()** relies on object identity, two objects representing the same request can create two cache entries. An easy-to-control option is to key on a stable property:

~~~java
@Cacheable(cacheNames = "products", key = "#p0.id")
public Product findByQuery(ProductQuery query) {
    return productRepository.findByQuery(query);
}
~~~

**Use this key only when query.id alone determines the result.** If fields like currency, tenant, includeInactive, or effective date alter the data, taking only **id** will cause two distinct requests to share one record. When using objects as keys, prefer immutable value types (such as a Java **record**) or key expressions built from stable, sufficiently distinguishing fields.

## 5. Multi-Parameter Methods: Keys Are Ordered Combinations

~~~java
@Cacheable(cacheNames = "translatedProducts")
public ProductView findView(String productId, String language) {
    return productRepository.findLocalizedView(productId, language);
}
~~~

Invocations:

~~~text
findView("P01", "vi") -> SimpleKey("P01", "vi") -> initial miss
findView("P01", "en") -> SimpleKey("P01", "en") -> different key
findView("P01", "vi") -> same key as first    -> hit
~~~

**SimpleKey** preserves element distinction and ordering; two parameter lists must match according to each element's equality semantics to share an entry.

### Including all parameters in the key by default

Consider:

~~~java
@Cacheable(cacheNames = "prices")
public Price lookup(String sku, String currency, boolean includeTax) {
    return pricingService.lookup(sku, currency, includeTax);
}
~~~

All three parameters affect the result, so generating a key from all three by default is usually right. Taking only **sku** could mix up VND/USD prices or tax-inclusive/tax-exclusive prices.

Conversely:

~~~java
@Cacheable(cacheNames = "productNames")
public String loadName(String productId, String traceId) {
    return productRepository.loadName(productId);
}
~~~

**traceId** is only used for logging and does not affect the result. A default key containing both **productId** and **traceId** causes the same product to spawn pointless separate entries. Once verified that **traceId does not affect the returned content**, we can use:

~~~java
@Cacheable(cacheNames = "productNames", key = "#p0")
public String loadName(String productId, String traceId) {
    return productRepository.loadName(productId);
}
~~~

This way, all calls with the same **productId** can share the result. This is a decision grounded in **real data dependencies**, not a trick to boost hit ratio at any cost.

## 6. Intentional Key Design with SpEL or KeyGenerator

Useful expressions in the annotation:

| Syntax | Meaning |
| --- | --- |
| **#p0** or **#a0** | First parameter (0-based index) |
| **#p1** or **#a1** | Second parameter |
| **#root.args[0]** | First parameter via invocation metadata |
| **#root.methodName** | Name of the method currently being invoked |
| **#p0.id** | The **id** property of the first parameter |
| **'fixed-key'** | Constant string key, useful for no-argument methods |

In Java, **#p0** is generally more resilient than **#productId** when a project is not compiled with parameter name metadata (**-parameters**). Spring can recognize parameter names when metadata is available, but do not assume every build retains them.

~~~java
// Key by productId because the remaining argument is only for tracing.
@Cacheable(cacheNames = "products", key = "#p0")
public Product load(String productId, String requestId) { /* ... */ }

// Reserve a constant key for singleton data in a cache.
@Cacheable(cacheNames = "exchangeRateSnapshot", key = "'latest'")
public RateSnapshot latestRates() { /* ... */ }

// Distinguish methods sharing a cache using a namespace.
@Cacheable(cacheNames = "sharedText", key = "#root.methodName + ':' + #p0")
public String describe(String id) { /* ... */ }
~~~

**Caution when concatenating strings for keys:** ensure the encoding is unambiguous; for instance, both pairs **("a:b", "c")** and **("a", "b:c")** become **a:b:c** if simply joined with a colon. When multiple fields must be distinguished accurately, use a structured key type (record/SimpleKey) or a standardized **KeyGenerator** instead of ad-hoc string concatenation.

Example of a generator that namespaces by class and method name to prevent unintended key sharing:

~~~java
// NamedMethodKeyGenerator.java – component code for use in a Spring application.
package demo.cache;

import java.lang.reflect.Method;
import java.util.Arrays;
import org.springframework.cache.interceptor.KeyGenerator;

public class NamedMethodKeyGenerator implements KeyGenerator {
    @Override
    public Object generate(Object target, Method method, Object... params) {
        return new MethodCallKey(
                target.getClass().getName(),
                method.getName(),
                Arrays.asList(params.clone()));
    }

    public record MethodCallKey(
            String className, String methodName, java.util.List<Object> args) {}
}
~~~

The code above illustrates structured key creation; in a real application you must consider **overloads** (if different signatures can receive visually similar values), arrays/mutable objects, storage overhead, and distributed provider serializers. **target.getClass()** can be a proxy class depending on the mechanism; if keys must stay stable across environments/providers, use an explicit business namespace rather than relying on runtime class names. **key** and **keyGenerator** are mutually exclusive options on the same annotation.

~~~java
@Cacheable(cacheNames = "profiles", keyGenerator = "businessKeyGenerator")
public Profile profile(String tenantId, String userId) {
    return profileRepository.load(tenantId, userId);
}
~~~

Here Spring requires an actual **businessKeyGenerator** bean to exist. The snippets in this section illustrate configuration syntax, not standalone runnable files.

## 7. Complete Spring Example: Observing Hit/Miss with 0, 1, and 2 Parameters

Below is a minimal application using **Spring Framework 6.1.x**, **Java 17+**, and **ConcurrentMapCacheManager** to directly see whether methods re-run. No database is needed; counters increment **only when the method body executes**.

Create the structure:

~~~text
spring-cache-keys-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/cache/CacheKeysDemo.java
~~~

**settings.gradle**:

~~~groovy
rootProject.name = 'spring-cache-keys-demo'
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
    mainClass = 'demo.cache.CacheKeysDemo'
}
~~~

**src/main/java/demo/cache/CacheKeysDemo.java**:

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
public class CacheKeysDemo {

    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("users", "translations", "version");
    }

    @Bean
    public CatalogService catalogService() {
        return new CatalogService();
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(CacheKeysDemo.class)) {
            CatalogService service = context.getBean(CatalogService.class);

            System.out.println(service.user("u1"));
            System.out.println(service.user("u1"));
            System.out.println(service.user("u2"));

            System.out.println(service.translation("hello", "vi"));
            System.out.println(service.translation("hello", "en"));
            System.out.println(service.translation("hello", "vi"));

            System.out.println(service.version());
            System.out.println(service.version());
        }
    }

    public static class CatalogService {
        private int userLoads;
        private int translationLoads;
        private int versionLoads;

        @Cacheable(cacheNames = "users")
        public String user(String id) {
            return "user:" + id + ":load=" + ++userLoads;
        }

        @Cacheable(cacheNames = "translations")
        public String translation(String text, String language) {
            return "text:" + text + ":" + language
                    + ":load=" + ++translationLoads;
        }

        @Cacheable(cacheNames = "version")
        public String version() {
            return "version:load=" + ++versionLoads;
        }
    }
}
~~~

Run in the project directory using an installed Gradle (or use the Gradle wrapper if the project already has one generated):

~~~bash
gradle run --quiet
~~~

Expected **System.out.println** lines, in exact order (excluding any build/runtime tool messages):

~~~text
user:u1:load=1
user:u1:load=1
user:u2:load=2
text:hello:vi:load=1
text:hello:en:load=2
text:hello:vi:load=1
version:load=1
version:load=1
~~~

Explanation:

- **user("u1")** misses the first time and hits the second time so **userLoads** stays at 1; **user("u2")** has a new key and increments to 2.
- **translation("hello", "vi")** differs from **translation("hello", "en")** because the key includes both parameters; repeating **("hello", "vi")** hits and does not increment **translationLoads**.
- **version()** has no parameters, so both invocations use **SimpleKey.EMPTY** in the **version** cache, incrementing **versionLoads** only once.
- The bean is obtained via **ApplicationContext**, so calls to **CatalogService** pass through the proxy configured by **@EnableCaching**. Manually instantiating **new CatalogService()** and calling directly bypasses Spring interception.
- **ConcurrentMapCacheManager** is convenient for quickly demonstrating key/hit/miss behavior; by itself it does not provide TTL/size eviction like a dedicated production cache configuration.

This is a **real Spring application**, unlike the per-method snippets above. Spring 6.1.x requires Java 17 or higher; the example pins a specific library version for consistent execution. If your environment already uses a shared Spring Boot/Gradle project, take only the relevant cache configuration and service rather than creating a parallel sample project.

## 8. Invalidation: Evicting the Exact Key of the Same Method

Keys used when reading must match keys used when evicting:

~~~java
@Cacheable(cacheNames = "products", key = "#p0")
public Product getProduct(String id) {
    return repository.load(id);
}

@CacheEvict(cacheNames = "products", key = "#p0")
public void updateProduct(String id, UpdateProductCommand command) {
    repository.update(id, command);
}
~~~

By default, **@CacheEvict** performs eviction after the method finishes normally. Both annotations here use **id** as the key. If the update method has two parameters and omits **key**, the default algorithm creates **SimpleKey(id, command)**, which does not match **getProduct**'s **id**; the stale entry can remain.

Similarly for a no-argument method using a constant key:

~~~java
@Cacheable(cacheNames = "globalSettings", key = "'active'")
public Settings currentSettings() {
    return repository.loadSettings();
}

@CacheEvict(cacheNames = "globalSettings", key = "'active'")
public void changeSettings(Settings newSettings) {
    repository.saveSettings(newSettings);
}
~~~

Because **currentSettings()** uses the constant key **active**, the write method must also evict **active** even though it accepts **Settings newSettings** as a parameter. Separate cache names or use **allEntries = true** only when you genuinely intend to clear all entries in the cache.

**Freshness and transactions:** If the DB update runs inside a transaction, the timing of cache eviction relative to transaction commit must be controlled. Evicting too early can let another thread miss and reload uncommitted DB data, then keep the stale version. With multiple instances, each node's local cache also needs a suitable invalidation strategy. TTL is a provider policy, not a default attribute of **@Cacheable**.

## 9. Cache Conditions and Parameter Scope

**condition** is evaluated before calling the method, so it can inspect parameters; **unless** decides whether to cache the result after the method runs.

~~~java
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    condition = "#p0 != null",
    unless = "#result == null"
)
public Product findById(String id) {
    return repository.findById(id).orElse(null);
}
~~~

This example allows caching only when id is non-null and avoids storing null results. For no-argument methods, **condition** can still rely on invocation metadata, but cannot distinguish users by parameter if user information is not passed into the method. **#result** is unavailable when computing the key of **@Cacheable** before invocation; use **unless** to inspect the result after execution.

Note that **@Cacheable(sync = true)** can reduce duplicate computations for the same key when multiple threads miss concurrently **if the provider supports it**, though behavior and constraints depend on the cache implementation; it does not replace distributed locking. Do not arbitrarily combine **sync = true** with **unless** because Spring restricts this in synchronized mode.

## 10. Design Comparison Table: Which Approach Should You Use?

| Scenario | Approach | Why |
| --- | --- | --- |
| One shared result, no-argument method | **@Cacheable("globalSnapshot")** | Defaults to a single **SimpleKey.EMPTY** key for that cache |
| Two no-argument methods with different semantics | Separate cache names or distinct constant keys | Avoids **SimpleKey.EMPTY** collision |
| Single parameter sufficient to identify result | Default key | Simple, readable, minimal configuration |
| Single DTO parameter with many irrelevant fields | Key on the fields that actually determine the result | Avoids pointless duplicate entries |
| Two or more parameters jointly affecting the result | Default **SimpleKey(...)** | Distinguishes parameter combinations |
| One parameter used solely for tracing/logging | Custom key excluding trace/log argument | Increases reuse without corrupting data |
| Result depends on tenant/user/locale not present in signature | Update method contract to pass required context and include it in key | Prevents data leaks or cross-user mixing |
| Multiple methods sharing a cache name | Method/business key namespace or separate caches | Prevents collisions even with identical arguments |
| Write method updating an object | **@CacheEvict** with matching read key, accounting for commit | Prevents returning stale versions |
| Result must always be fresh at transaction time | Re-read/verify at the data source for critical decisions | Cache does not guarantee transactional consistency |

## 11. Common Mistakes and How to Verify

**1. Forgetting to enable Spring caching.** The annotation takes effect only when **@EnableCaching** (or equivalent application configuration) is active, a **CacheManager** exists, and the call is intercepted by a Spring proxy/aspect.

**2. Calling a method within the same bean (self-invocation).** For example, a **run()** method calling **this.findById("P01")** bypasses the proxy in normal proxy mode, so **@Cacheable** on **findById** may not apply. Extract the method into another bean and invoke via the Spring bean, or choose an appropriate interception mechanism.

**3. Same cache name, same key, different meanings.** Two no-argument methods both typically produce **SimpleKey.EMPTY**. Separate caches or set explicit keys.

**4. Omitting a parameter that affects the result.** Using **key = "#p0"** for **loadPrice(sku, currency)** puts different currencies under the same key, which is a data correctness bug rather than just a performance issue.

**5. Including irrelevant parameters in the key.** **traceId**, correlation id, or request timestamps can turn every request into a brand-new key, lowering hit ratio and wasting memory.

**6. Keys built from mutable objects.** If an object mutates fields involved in **equals/hashCode** while serving as a key, lookup or eviction can become unpredictable. Prefer immutable/canonical keys.

**7. Assuming the same arguments always return the latest data.** The cache may serve a version captured prior to a DB change. Eviction, cache updates, TTL, or source re-validation are needed per business requirements.

**8. Reading and evicting with different keys.** **get(id)** caches by **id**, while **update(id, command)** evicts by default using both parameters; as a result, the old version is never removed. Write symmetric **key** expressions.

**9. Not checking the provider.** Local caches per instance are independent; Redis has its own serializers and key conversions. Do not assume complex Java keys have the same format and efficiency across every provider.

**10. Caching results that depend on hidden state.** For current user, tenant, locale, clock, or feature flags, identify which factors alter the return value and ensure they are properly represented in the key or choose not to cache.

When testing, call the same method with: (a) identical parameters twice; (b) different parameters; (c) no parameters twice; (d) two methods sharing a cache; (e) after a source update; and (f) an internal call within the same bean. Observe body execution counts, cache entries, and result correctness—do not measure **hit ratio** alone.

## 12. Self-Check

1. Why is **loadConfig()** cached even without parameters? What is its default key?
2. Why do **find("P01", "vi")** and **find("P01", "en")** produce two different keys?
3. When is excluding **traceId** from the key appropriate? When is excluding **currency** a bug?
4. What happens when two no-argument methods share the same cache name? Name two ways to fix it.
5. Why does **@CacheEvict** on **update(id, command)** need a key expression if the read method only accepts **id**?
6. Why might **@Cacheable** not run when using **new Service()** or self-invocation?

If you can answer these accurately, you have grasped the most important principle: **the cache key must reflect the exact set of factors determining the result, and the cache name must reflect the data's scope and meaning**. Having no parameters is simply a special case of that rule, not an exception to **@Cacheable**.

### References

- Spring Framework — Declarative Annotation-based Caching, Default Key Generation, and SpEL: https://docs.spring.io/spring-framework/reference/integration/cache/annotations.html
- Spring Framework — Cache Abstraction: https://docs.spring.io/spring-framework/reference/integration/cache.html
- Spring Framework — Spring AOP proxy semantics: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — SimpleKeyGenerator Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/cache/interceptor/SimpleKeyGenerator.html