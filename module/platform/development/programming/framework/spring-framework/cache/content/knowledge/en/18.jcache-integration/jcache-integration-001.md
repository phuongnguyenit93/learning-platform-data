# JSR-107, Providers, and JCacheCacheManager in Spring Framework

## 1. What Is JCache?

**JCache**, officially known as **JSR-107**, is a Java specification that defines a standard caching API and a Service Provider Interface (SPI) for caching libraries to implement. Applications use standard types such as `Cache`, `CacheManager`, and `CachingProvider`; the provider decides where caches are stored, how memory is managed, and which operational features are supported.

JCache is a **specification**, not a standalone storage library. The `cache-api` dependency only provides the interfaces. An application still needs a provider that implements the API, such as Ehcache 3, Hazelcast, or Infinispan with JSR-107 support.

In Spring Framework, two bridge classes need to be distinguished:

- `JCacheCache`: an adapter for **a single cache region**, wrapping `javax.cache.Cache` and exposing it as Spring's `org.springframework.cache.Cache`.
- `JCacheCacheManager`: an adapter for **the entire cache manager**, wrapping `javax.cache.CacheManager` and implementing Spring's `org.springframework.cache.CacheManager`.

```text
Service / Controller
       |
       v
Spring CacheInterceptor
       |
       v
org.springframework.cache.CacheManager
       |
       v
JCacheCacheManager
       |
       v
javax.cache.CacheManager
       |
       v
JCache provider (Ehcache / Hazelcast / Infinispan / ...)
       |
       v
Native cache storage
```

Thanks to the adapters, code using Spring annotations such as `@Cacheable` or Spring's `Cache` API can run on a JCache provider. Spring also supports standard JCache annotations such as `@CacheResult` and `@CacheRemove`. Both annotation sets can coexist if keys, null policies, and cache lifecycles are aligned.

## 2. Components in the JSR-107 Specification

| Component | Package | Responsibility |
| --- | --- | --- |
| `CachingProvider` | `javax.cache.spi` | Entry point to obtain a cache manager; each vendor provides an implementation |
| `CacheManager` | `javax.cache` | Create, look up, list, and close caches |
| `Cache<K,V>` | `javax.cache` | Typed key-value store with key and value types |
| `MutableConfiguration<K,V>` | `javax.cache.configuration` | Configure types, store-by-value, expiry, loader/writer, listeners, and statistics |
| `ExpiryPolicy` | `javax.cache.expiry` | Define entry expiration on creation, access, or modification events |
| `CacheLoader` / `CacheWriter` | `javax.cache.integration` | Integrate loading or writing data with external sources |
| `CacheEntryListener` | `javax.cache.event` | Receive entry creation, update, removal, or expiration events |
| Spring `CacheManager` | `org.springframework.cache` | Manager abstraction used by Spring annotations and interceptors |

Be careful because two types share the same simple name `CacheManager` while belonging to different packages:

```java
javax.cache.CacheManager nativeManager;
org.springframework.cache.CacheManager springManager;
```

`nativeManager` interacts with JSR-107 and the provider. `springManager` is Spring's abstraction; when using JCache, the actual object is typically `JCacheCacheManager`.

A cache named `products` is a **region**; inside the region, each key maps to a value. A cache name is not a key, and a key is not a provider name. Two caches with the same name belonging to two different managers can still be two independent stores.

## 3. Providers and Discovery via SPI

### 3.1. A Provider Is Not a CacheManager

A `CachingProvider` creates or retrieves a `javax.cache.CacheManager`. The manager then creates `Cache` instances:

```text
CachingProvider
   |
   +-- getCacheManager(URI, ClassLoader, Properties)
             |
             v
       CacheManager
             |
             +-- createCache("products", configuration)
             +-- getCache("products")
             +-- destroyCache("products")
```

Providers are typically discovered through the Java Service Provider mechanism using `META-INF/services/javax.cache.spi.CachingProvider` metadata inside the JAR. This allows the application to use the standard API without instantiating implementation classes everywhere.

### 3.2. Obtaining the Default Provider

```java
import javax.cache.Caching;
import javax.cache.spi.CachingProvider;

CachingProvider provider = Caching.getCachingProvider();
javax.cache.CacheManager manager = provider.getCacheManager();
```

This approach works when the classpath contains only **one JCache provider**. If multiple providers are present, the default call may fail because the implementation cannot be determined unambiguously. Specify the provider class explicitly:

```java
CachingProvider provider = Caching.getCachingProvider(
    "org.ehcache.jsr107.EhcacheCachingProvider"
);
```

The class name above is the Ehcache 3 provider. When switching vendors, the implementation class name changes as well; keep provider selection in startup configuration rather than business classes.

### 3.3. URI, ClassLoader, and Lifecycle

`CachingProvider` provides overloads accepting `URI`, `ClassLoader`, and `Properties` to select manager configuration and class-loading scope. With Ehcache, the URI can point to an XML file defining cache aliases, heap sizing, expiry, and tiers.

A cache manager is a shared application resource. Do not create and close a manager on every request. When the Spring context shuts down, close the manager/provider according to an appropriate lifecycle; `@Bean(destroyMethod = "close")` can be used so the container handles it.

## 4. Creating Caches with the Standard API

### 4.1. MutableConfiguration

Example creating a cache named `products`:

```java
import javax.cache.Cache;
import javax.cache.CacheManager;
import javax.cache.configuration.MutableConfiguration;

MutableConfiguration<String, Product> config =
        new MutableConfiguration<String, Product>()
            .setTypes(String.class, Product.class)
            .setStoreByValue(false);

Cache<String, Product> products =
        cacheManager.createCache("products", config);
```

This is an illustrative snippet assuming `cacheManager` and the `Product` type already exist. `createCache` typically throws an error if the name already exists; if reuse is needed, call `getCache` or check before creating.

### 4.2. Core Operations

```java
products.put("P1", new Product("P1", "Pen"));
Product product = products.get("P1");

boolean exists = products.containsKey("P1");
products.remove("P1");
products.removeAll();
```

| API | Meaning |
| --- | --- |
| `get(key)` / `getAll(keys)` | Read one or multiple values |
| `put(key, value)` / `putAll(map)` | Insert a new value or replace an existing one |
| `getAndPut(key, value)` | Return the old value and write the new value |
| `putIfAbsent(key, value)` | Insert only if the key is not already present |
| `remove(key)` | Remove a single key |
| `remove(key, oldValue)` | Conditionally remove matching the value |
| `replace(key, value)` | Replace the value when the key already exists |
| `invoke(key, EntryProcessor, args...)` | Execute an entry operation as supported by the provider |
| `iterator()` | Iterate over entries |
| `clear()` | Remove entries while keeping the cache structure |
| `close()` | Close the cache |

JCache uses generic types, but providers may enforce runtime type checks based on configuration. Do not create a cache declared with key type `Long` and write a `String` key, or write an incompatible value.

### 4.3. Store-by-Value and Store-by-Reference

`MutableConfiguration` defaults to store-by-value according to the specification. The provider copies keys/values using its own mechanism; this prevents callers from mutating stored data through mutable objects, but requires objects to be compatible with the copying/serialization mechanism.

You can opt for:

```java
config.setStoreByValue(false);
```

Store-by-reference keeps references according to provider semantics. The runnable example in section 9 chooses `false` so the `Product` record can be used without implementing `Serializable`. This is an intentional decision, not the right choice for every application.

For distributed or off-heap caches, the provider may require custom serializers or copiers. Check vendor and version requirements instead of assuming compatibility solely from generic types.

## 5. Expiry, Loader, Writer, and Statistics

### 5.1. Expiry Policy

JCache defines standard policies:

- `CreatedExpiryPolicy`: calculates duration from the time the entry is created.
- `AccessedExpiryPolicy`: refreshes duration when the entry is read.
- `ModifiedExpiryPolicy`: refreshes when the entry is created or updated.
- `TouchedExpiryPolicy`: refreshes when the entry is created, read, or updated.
- `EternalExpiryPolicy`: does not expire based on time.

Example where entries live for 10 minutes from creation:

```java
config.setExpiryPolicyFactory(
    CreatedExpiryPolicy.factoryOf(
        new Duration(TimeUnit.MINUTES, 10)
    )
);
```

These policies are part of the JCache standard, though physical cleanup timing, timer precision, and tier interactions may still vary across providers.

### 5.2. Loader and Writer

`CacheLoader<K,V>` supports loading values from an external source when requested from the cache; `CacheWriter<K,V>` supports write-through or write-behind depending on configuration and provider. They differ from Spring `@Cacheable`:

- `@Cacheable` is method-level interception in Spring.
- `CacheLoader`/`CacheWriter` integrate the cache with a data source at the provider layer.

Do not configure both loading/writing paths to call the same repository without a clear contract, as that can cause side effects or duplicate queries.

### 5.3. Statistics and Management

`MutableConfiguration` can enable statistics and management:

```java
config.setStatisticsEnabled(true);
config.setManagementEnabled(true);
```

Providers may expose metrics/management via JMX or vendor-specific mechanisms. Enabling these flags does not automatically bind metrics to Micrometer/Actuator; verify provider capabilities and monitoring configuration.

## 6. Spring JCacheCacheManager and JCacheCache

### 6.1. JCacheCacheManager as Spring's Adapter

`org.springframework.cache.jcache.JCacheCacheManager` accepts a `javax.cache.CacheManager` and exposes native caches as Spring `Cache` instances. When an interceptor needs the `products` region, the adapter looks up the cache with that name in the native manager and wraps it in a `JCacheCache`.

```java
@Bean
org.springframework.cache.CacheManager cacheManager(
        javax.cache.CacheManager nativeManager) {

    JCacheCacheManager manager =
            new JCacheCacheManager(nativeManager);

    manager.setAllowNullValues(false);
    return manager;
}
```

This is a Spring configuration snippet; `nativeManager` must be created from the JCache provider in another bean. `JCacheCacheManager` is the Spring `CacheManager` bean used by `@EnableCaching`.

### 6.2. JCacheCache as a Per-Region Adapter

`JCacheCache` wraps a specific `javax.cache.Cache` and delegates Spring operations:

- `getName()` returns the region name.
- `getNativeCache()` returns the native JCache cache.
- `get(key)` returns a Spring `Cache.ValueWrapper`.
- `put`, `putIfAbsent`, `evict`, and `clear` delegate to the native cache.
- `get(key, Callable)` uses a loader callback on miss as supported by the implementation.

Example accessing the adapter:

```java
org.springframework.cache.Cache springCache =
        springManager.getCache("products");

if (springCache == null) {
    throw new IllegalStateException("Missing products cache");
}

Object nativeCache = springCache.getNativeCache();
System.out.println(springCache.getName()); // products
```

This illustrative snippet requires `springManager`. Do not cast every `Cache` to `JCacheCache` if the application uses multiple providers.

### 6.3. Cache Names Must Exist in the Native Manager

The standard approach is to create caches beforehand on `javax.cache.CacheManager` so the Spring adapter sees the existing names. If a cache does not exist, `getCache(name)` may fail to resolve the region and annotations cannot use that cache.

Initialization sequence:

1. Select a provider.
2. Create the native `javax.cache.CacheManager`.
3. Create cache names and their configurations.
4. Wrap the native manager with `JCacheCacheManager`.
5. Register the Spring `CacheManager` bean and enable `@EnableCaching`.
6. Test all cache names used by annotations.

## 7. Method-Level JCache Annotations

Spring Framework has supported JSR-107 annotations since Spring 4.1. When the JCache API and the `spring-context-support` module are on the classpath, `@EnableCaching` automatically registers JCache annotation processing alongside Spring annotations.

JCache annotations reside in `javax.cache.annotation`:

| JCache Annotation | Effect | Closest Spring Equivalent |
| --- | --- | --- |
| `@CacheResult` | Check cache first; on miss, execute method and cache result | `@Cacheable` |
| `@CachePut` | Take the `@CacheValue` parameter and write it to cache | `@CachePut` |
| `@CacheRemove` | Remove entry by key generated from parameters | `@CacheEvict` |
| `@CacheRemoveAll` | Remove all entries in a cache | `@CacheEvict(allEntries=true)` |
| `@CacheDefaults` | Class-level default configuration | `@CacheConfig` |
| `@CacheKey` | Mark parameters participating in the key | Parameter selection in SpEL |
| `@CacheValue` | Mark the parameter written to the cache | No direct equivalent |

### 7.1. `@CacheResult`

`@CacheResult` is similar to `@Cacheable`: the cache is checked before invoking the method. If an entry exists, the method can be skipped and the cached value is returned.

Notable specifics:

- `skipGet=true` forces method execution instead of returning a cache hit.
- `exceptionCacheName` together with `cachedExceptions`/`nonCachedExceptions` enables JSR-107 exception caching.
- Keys are generated using `CacheKeyGenerator`; by default, parameters are selected according to `@CacheKey`/`@CacheValue` rules.

```java
@CacheResult(cacheName = "products")
public Product find(@CacheKey String id) {
    return repository.find(id);
}
```

This is an illustrative snippet of a service that already has a repository. If a method has multiple parameters and none are annotated with `@CacheKey`, all eligible parameters may participate in the key by default. When one or more `@CacheKey` annotations are present, only the annotated parameters are used.

### 7.2. `@CachePut` and `@CacheValue`

JCache `@CachePut` differs from Spring `@CachePut`. The JCache standard requires the method to have a `@CacheValue` parameter; that parameter is the value placed into the cache.

```java
@CachePut(cacheName = "products")
public void update(
        @CacheKey String id,
        @CacheValue Product product) {

    repository.save(product);
}
```

By default, `@CachePut` writes to the cache **after the method completes successfully**. Setting `afterInvocation=false` writes before the method executes, though the value may remain cached even if the method fails. `cacheFor`/`noCacheFor` control exception handling when writing after invocation.

The `@CacheValue` parameter is automatically excluded from the default key set. If `@CacheKey` is present, only those annotated parameters form the key; for example, `id` is the key and `product` is the value.

### 7.3. `@CacheRemove` and `@CacheRemoveAll`

`@CacheRemove` removes a single entry by key:

```java
@CacheRemove(cacheName = "products")
public void delete(@CacheKey String id) {
    repository.delete(id);
}
```

By default, removal happens after the method completes successfully. `evictFor` and `noEvictFor` control eviction when the method throws an exception. `afterInvocation=false` performs the removal before the method executes.

`@CacheRemoveAll` clears the entire region:

```java
@CacheRemoveAll(cacheName = "products")
public void reloadCatalog() {
    repository.reload();
}
```

Avoid clearing the entire cache for every single-record update when evicting one key suffices; broad invalidation can cause cache misses and increase load on the underlying data source.

### 7.4. `@CacheDefaults`

`@CacheDefaults` sets defaults for JCache annotations within a class:

```java
@CacheDefaults(cacheName = "products")
public class ProductService {

    @CacheResult
    public Product find(@CacheKey String id) {
        return repository.find(id);
    }

    @CacheRemove
    public void delete(@CacheKey String id) {
        repository.delete(id);
    }
}
```

Methods still require operation annotations; adding `@CacheDefaults` alone does not cache every method. Besides cache name, the annotation can configure `cacheKeyGenerator` and `cacheResolverFactory`.

## 8. Comparing JCache Annotations and Spring Annotations

Both annotation sets have similar names, but their semantics are not identical:

| Topic | Spring | JCache |
| --- | --- | --- |
| Cache before method execution | `@Cacheable` | `@CacheResult` |
| Update cache after method | `@CachePut` uses the return value | `@CachePut` uses the `@CacheValue` parameter |
| Evict a single key | `@CacheEvict` | `@CacheRemove` |
| Clear an entire region | `@CacheEvict(allEntries=true)` | `@CacheRemoveAll` |
| Class-level defaults | `@CacheConfig` | `@CacheDefaults` |
| Key selection | SpEL `key` or `KeyGenerator` | `@CacheKey` and `CacheKeyGenerator` |
| Cache selection | A single Spring operation can declare multiple cache names | JCache resolver selects one cache |
| Exception caching | No direct equivalent in standard Spring annotations | `@CacheResult` can cache exceptions by configuration |

Key generation difference to note:

- Spring's default key generator uses the single parameter directly if there is only one parameter, or `SimpleKey` if there are multiple parameters.
- JCache's default generator creates a `GeneratedCacheKey` based on the selected parameters.
- If both annotation styles are used on the same cache, keys may **differ** even when methods receive the same ID string.

Spring example:

```java
@org.springframework.cache.annotation.Cacheable(
    cacheNames = "products",
    key = "#p0"
)
public Product findSpring(String id) {
    return repository.find(id);
}
```

JCache example:

```java
@javax.cache.annotation.CacheResult(cacheName = "products")
public Product findStandard(@javax.cache.annotation.CacheKey String id) {
    return repository.find(id);
}
```

These two snippets do not automatically share the same entry just because they use the same region name and parameter. To interoperate through the same cache, design compatible key generators/representations or stick to one annotation style per region.

## 9. Runnable Example: Spring 6.2.9 + JCache 1.1.1 + Ehcache 3.10.8

This example uses JCache annotations through Spring, with Ehcache 3 as the provider. It demonstrates:

1. Discovering the provider via SPI and creating a native JCache manager.
2. Creating the `products` cache region using JCache configuration.
3. Wrapping the native manager with Spring `JCacheCacheManager`.
4. Using `@CacheResult` to read, `@CachePut` to update, `@CacheRemove` to delete a single key, and `@CacheRemoveAll` to clear the entire region.
5. Counting repository executions and remaining entries.

### 9.1. Maven Dependencies

**JDK 17+**, Spring Framework 6.2.9, JCache API 1.1.1, and Ehcache 3.10.8:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-jcache-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.9</version>
        </dependency>
        <dependency>
            <groupId>javax.cache</groupId>
            <artifactId>cache-api</artifactId>
            <version>1.1.1</version>
        </dependency>
        <dependency>
            <groupId>org.ehcache</groupId>
            <artifactId>ehcache</artifactId>
            <version>3.10.8</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context-support` provides Spring's JCache integration adapters and JCache annotation support. `cache-api` is only the API; `ehcache` supplies the concrete provider implementation.

### 9.2. File `src/main/java/JCacheDemo.java`

```java
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.TimeUnit;

import javax.cache.Caching;
import javax.cache.Cache;
import javax.cache.CacheManager;
import javax.cache.configuration.MutableConfiguration;
import javax.cache.expiry.CreatedExpiryPolicy;
import javax.cache.expiry.Duration;
import javax.cache.spi.CachingProvider;
import javax.cache.annotation.CacheDefaults;
import javax.cache.annotation.CacheKey;
import javax.cache.annotation.CachePut;
import javax.cache.annotation.CacheRemove;
import javax.cache.annotation.CacheRemoveAll;
import javax.cache.annotation.CacheResult;
import javax.cache.annotation.CacheValue;

import org.springframework.cache.jcache.JCacheCache;
import org.springframework.cache.jcache.JCacheCacheManager;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableCaching
public class JCacheDemo {

    @Bean(destroyMethod = "close")
    CachingProvider cachingProvider() {
        return Caching.getCachingProvider(
                "org.ehcache.jsr107.EhcacheCachingProvider");
    }

    @Bean(destroyMethod = "close")
    CacheManager nativeCacheManager(CachingProvider provider) {
        CacheManager manager = provider.getCacheManager();

        MutableConfiguration<Object, Product> config =
                new MutableConfiguration<Object, Product>()
                    .setTypes(Object.class, Product.class)
                    .setStoreByValue(false)
                    .setExpiryPolicyFactory(
                        CreatedExpiryPolicy.factoryOf(
                            new Duration(TimeUnit.MINUTES, 10)
                        )
                    );

        manager.createCache("products", config);
        return manager;
    }

    @Bean
    org.springframework.cache.CacheManager cacheManager(
            CacheManager nativeCacheManager) {
        JCacheCacheManager manager =
                new JCacheCacheManager(nativeCacheManager);

        // JCache does not accept null keys/values; the demo uses non-null results.
        manager.setAllowNullValues(false);
        return manager;
    }

    @Bean
    ProductRepository productRepository() {
        return new ProductRepository();
    }

    @Bean
    ProductService productService(ProductRepository repository) {
        return new ProductService(repository);
    }

    public record Product(String id, String name) {}

    public static class ProductRepository {
        private final Map<String, Product> data = new ConcurrentHashMap<>();
        private final AtomicInteger reads = new AtomicInteger();

        public ProductRepository() {
            data.put("P1", new Product("P1", "Pen"));
        }

        public Product find(String id) {
            reads.incrementAndGet();
            return data.get(id);
        }

        public void save(Product product) {
            data.put(product.id(), product);
        }

        public void delete(String id) {
            data.remove(id);
        }

        public void clear() {
            data.clear();
        }

        public int reads() {
            return reads.get();
        }
    }

    @CacheDefaults(cacheName = "products")
    public static class ProductService {
        private final ProductRepository repository;

        public ProductService(ProductRepository repository) {
            this.repository = repository;
        }

        @CacheResult
        public Product find(@CacheKey String id) {
            return repository.find(id);
        }

        @CachePut
        public void update(
                @CacheKey String id,
                @CacheValue Product product) {
            if (!id.equals(product.id())) {
                throw new IllegalArgumentException("ID does not match product");
            }
            repository.save(product);
        }

        @CacheRemove
        public void delete(@CacheKey String id) {
            repository.delete(id);
        }

        @CacheRemoveAll
        public void clear() {
            repository.clear();
        }
    }

    private static int countEntries(Cache<?, ?> cache) {
        int count = 0;
        for (Cache.Entry<?, ?> entry : cache) {
            count++;
        }
        return count;
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(JCacheDemo.class)) {

            ProductService service = context.getBean(ProductService.class);
            ProductRepository repository =
                    context.getBean(ProductRepository.class);
            CacheManager nativeManager =
                    context.getBean(CacheManager.class);

            Cache<Object, Product> nativeProducts =
                    nativeManager.getCache(
                            "products", Object.class, Product.class);

            System.out.println("first: " + service.find("P1"));
            System.out.println("second: " + service.find("P1"));
            System.out.println("source reads after repeat: "
                    + repository.reads());

            service.update("P1", new Product("P1", "Blue pen"));
            System.out.println("after update: " + service.find("P1"));
            System.out.println("source reads after update: "
                    + repository.reads());

            service.update("P2", new Product("P2", "Notebook"));
            service.delete("P1");
            System.out.println("entries after remove P1: "
                    + countEntries(nativeProducts));

            service.clear();
            System.out.println("entries after removeAll: "
                    + countEntries(nativeProducts));

            org.springframework.cache.Cache springCache =
                    context.getBean(org.springframework.cache.CacheManager.class)
                            .getCache("products");
            System.out.println("Spring adapter: "
                    + (springCache instanceof JCacheCache));
        }
    }
}
```

### 9.3. Running and Output

From the directory containing `pom.xml`, using JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=JCacheDemo
```

Lines printed by the program (excluding environment-dependent Maven/SLF4J logs):

```text
first: Product[id=P1, name=Pen]
second: Product[id=P1, name=Pen]
source reads after repeat: 1
after update: Product[id=P1, name=Blue pen]
source reads after update: 1
entries after remove P1: 1
entries after removeAll: 0
Spring adapter: true
```

Explanation:

1. The first `find("P1")` is a cache miss; the repository returns `Product(P1, "Pen")`.
2. The second call uses the same JCache key, so `@CacheResult` returns the cached entry; source reads remain 1.
3. `update("P1", product)` always executes the repository and `@CachePut` writes the new product under the key generated from `@CacheKey String id`.
4. The subsequent `find("P1")` receives `Blue pen` from the cache; the repository read count does not increase.
5. `update("P2", ...)` adds another entry. `delete("P1")` runs the repository and `@CacheRemove` removes key P1; P2 remains, so the entry count is 1.
6. `clear()` executes the repository and `@CacheRemoveAll` clears the whole region; the entry count drops to 0.
7. `instanceof JCacheCache` confirms that the Spring manager returns an adapter wrapping the native JCache cache.

**Why is the key type `Object.class`?** JCache annotations generate a `GeneratedCacheKey` by default from `@CacheKey` parameters, rather than necessarily using the raw String `"P1"`. Configuring `Object.class` allows the cache to accept standard-generated keys. If you restrict the key type to `String.class`, the provider may reject the generated key even though the method has only a single String parameter.

The example chooses `setStoreByValue(false)` to store the `Product` record by reference, avoiding the requirement for the record to implement `Serializable`. If switching to store-by-value, ensure that key/value types and copiers/serializers satisfy the provider.

## 10. Advanced Configuration and Vendor Extensions

### 10.1. What MutableConfiguration Standardizes

`MutableConfiguration` supports common properties such as key/value types, store-by-value, expiry policy, loader/writer, listeners, statistics, and management. This is the portable subset across compliant providers.

### 10.2. What Depends on the Provider

Not all operational capabilities have standardized configuration in JCache. For example:
- Heap entry limits or memory weight.
- Off-heap, disk tiers, and persistence directories.
- Cluster replication and distributed topologies.
- Specialized serializers/copiers.
- Eviction algorithms and resilience policies.
- Connections, endpoints, or client modes.

With Ehcache, advanced settings can be defined in `ehcache.xml` or through Ehcache's native builder and wrapped with `Eh107Configuration`. Once vendor extensions are used, that configuration is no longer fully portable to another provider.

### 10.3. Ehcache XML Example

This is an **optional configuration snippet** for Ehcache 3, not a file used by the program in section 9:

```xml
<config xmlns="http://www.ehcache.org/v3">
    <cache alias="products">
        <key-type>java.lang.Object</key-type>
        <value-type>JCacheDemo$Product</value-type>
        <expiry>
            <ttl unit="minutes">10</ttl>
        </expiry>
        <heap unit="entries">1000</heap>
    </cache>
</config>
```

When using XML, create the native manager using the URI to the resource and an appropriate class loader, then retrieve the `products` cache alias. Do not call `createCache("products", ...)` again on the same manager if the XML already created that cache.

### 10.4. Switching Providers Does Not Guarantee Identical Behavior

JCache standardizes the API, yet providers still differ in performance, persistence, expiry timing, eviction, loader/writer behavior, transactions, serialization, and clustering. When switching vendors, re-run tests for key/value types, null handling, cache names, concurrency, invalidation, and restart survival.

## 11. Nulls, Transactions, and Key Compatibility

### 11.1. JCache Does Not Store Java Nulls Directly

JSR-107 does not permit Java null keys or values in standard cache operations. Spring's `JCacheCacheManager` allows nulls at the Spring layer by default by converting null into an internal holder/sentinel before writing to the native cache. You can disable this:

```java
JCacheCacheManager manager = new JCacheCacheManager(nativeManager);
manager.setAllowNullValues(false);
```

When a cache configures a strict value type like `Product.class`, the safest approach is not to store nulls. If sentinel adaptation is enabled, the native JCache provider sees a holder object rather than Java null; type restrictions or direct native operations may conflict with application assumptions.

With Spring annotations, you can use `unless="#result == null"` on `@Cacheable` to skip caching null results. JCache `@CacheResult` has no equivalent SpEL `unless` attribute; design non-null return values or a dedicated "not found" model instead.

### 11.2. Store-by-Value and Mutable Objects

If the provider stores by value, objects may be copied/serialized; if by reference, the caller and the cache may observe the same mutable object. Do not mutate cached DTOs in place without an explicit strategy. Prefer immutable values or copy objects before updating.

### 11.3. Transactions Do Not Automatically Span Database and Cache

`JCacheCacheManager` supports transaction awareness through Spring's cache management layer, but that does not turn every provider into an XA transaction or guarantee atomic commits with a database.

If a transaction rolls back, you need to know whether cache put/evict occurred before or after commit. For critical data, design post-commit invalidation, outbox/event mechanisms, or dedicated consistency patterns. Test error and rollback paths; do not treat the cache as the source of truth.

### 11.4. Keys Must Be Consistent Across Both APIs

If a Spring method uses `key="#p0"` producing a String key while a JCache method uses `@CacheResult` producing a `GeneratedCacheKey`, the two operations may write to two different entries in the same region. Choose one annotation style per region, or configure a custom `KeyGenerator`/`CacheKeyGenerator` with compatible semantics. Test cross-API reads, writes, and evictions if the application uses both simultaneously.

## 12. Programmatic API and Spring API Can Coexist

Direct JCache API:

```java
javax.cache.Cache<Object, Product> nativeCache =
        nativeManager.getCache("products", Object.class, Product.class);

nativeCache.put("manual-key", new Product("P9", "Ruler"));
Product product = nativeCache.get("manual-key");
nativeCache.remove("manual-key");
```

Spring API:

```java
org.springframework.cache.Cache springCache =
        springManager.getCache("products");

springCache.put("manual-key", new Product("P9", "Ruler"));
Product product = springCache.get("manual-key", Product.class);
springCache.evict("manual-key");
```

Both can touch the same native cache because `JCacheCache` is an adapter. However, key generation and null adaptation may differ. A String key in the direct API does not equal a `GeneratedCacheKey` produced by JCache annotations.

Do not use the native API to bypass important policies enforced at the Spring adapter layer, such as transaction-aware decoration or null conversion. When provider-specific capabilities are needed, retrieve the native cache intentionally via `getNativeCache()` and clearly document vendor-dependent code.

## 13. Common Pitfalls

1. **Adding only `cache-api` and assuming caching works.** It is just the API; a concrete provider must be on the classpath.
2. **Confusing JCache `CacheManager` with Spring `CacheManager`.** Wrong imports break wiring; name native and spring variables clearly.
3. **Missing `spring-context-support`.** Spring requires this module for JCache adapters and annotation support.
4. **Having multiple providers while calling the default `Caching.getCachingProvider()`.** Specify the provider class explicitly when multiple implementations are on the classpath.
5. **Using a cache name that has not been created.** Create regions in the native manager before the Spring adapter needs to resolve them.
6. **Confusing Spring `@CachePut` and JCache `@CachePut`.** JCache requires a `@CacheValue` parameter; Spring uses the method return value.
7. **Omitting `@CacheKey` on multi-parameter methods.** Unrelated parameters may inadvertently become part of the key.
8. **Using an overly narrow key type.** JCache annotations generate `GeneratedCacheKey`; a cache restricted to `String.class` may reject that key.
9. **Mixing Spring keys and JCache keys.** Same region and same ID do not guarantee the same entry; verify key equality and generators.
10. **Assuming JCache stores nulls.** Native JCache does not accept nulls; Spring provides sentinel adaptation, but value type constraints must be considered.
11. **Closing the manager too early.** The cache manager is a shared resource; closing it per request breaks other requests.
12. **Assuming JCache guarantees identical cluster semantics across providers.** The API standard does not standardize full topology, replication, TTL, or persistence behavior.
13. **Calling `createCache` repeatedly with the same name.** This can throw an exception; manage cache creation/lookup lifecycle consistently.
14. **Overlooking proxies.** JCache annotations in Spring still rely on interception infrastructure; self-invocation in default proxy mode bypasses the interceptor.
15. **Treating the transaction-aware adapter as XA.** Cache and database can still diverge on rollback, timeout, or mistimed invalidation.

## 14. Implementation and Testing Checklist

| Area | Question to Verify |
| --- | --- |
| API | Are you using `javax.cache`/JCache 1.1 or another API? Any Jakarta namespace confusion? |
| Provider | Which provider is selected by SPI? Are multiple providers on the classpath? |
| Manager | Which URI/ClassLoader does the native manager use, and where is it closed? |
| Region | Have all cache names used by annotations been created? |
| Types | Do key/value types match the key generator and actual runtime objects? |
| Storage | Store-by-value or store-by-reference? Are serialization/copiers required? |
| Expiry | Do TTL/expiry policies match the data lifecycle? |
| Null | Are nulls allowed via the Spring adapter? Does the native cache allow them? |
| Annotation | Have `@CacheResult`/`@CachePut`/`@CacheRemove` been distinguished from Spring annotations? |
| Keys | Do read, write, and delete paths produce compatible keys? |
| Transaction | Do put/evict execute before or after commit? How is rollback handled? |
| Operations | Are metrics, listeners, management, eviction, and memory limits configured appropriately? |
| Lifecycle | Does context shutdown close the manager/provider in the proper order? |

Minimum test cases:

1. Call the same key twice and verify the second call does not invoke the repository.
2. Call `@CachePut` then `@CacheResult` with the same key and verify the new value is returned.
3. Call `@CacheRemove` and verify the entry is gone.
4. Call `@CacheRemoveAll` and verify the entire region is empty.
5. Verify generated keys with one parameter, multiple parameters, and a subset marked with `@CacheKey`.
6. Test with a provider disallowing nulls and verify the application handles missing results properly.
7. Initialize the context multiple times to test existing caches, manager lifecycle, and provider cleanup.
8. Test the same data through both the Spring API and native JCache API if the application uses both.
9. If running across multiple JVMs, test the real provider/topology rather than extrapolating from a single process.
10. Simulate provider errors, serialization failures, expiration, and transaction rollbacks.

## 15. When Should You Choose JCache?

JCache is suitable when an organization needs a vendor-neutral API, shares caching across multiple modules, or wants to reduce coupling to a single library's proprietary API. It is also useful when the ecosystem already relies on JSR-107 annotations or compliant providers.

Using a provider's native API makes sense when the application needs features absent from standard JCache, such as specific topologies, tiering, eviction, or custom loaders. In exchange, code becomes more tightly coupled to the vendor.

In Spring, you can choose:

- Spring annotations + `JCacheCacheManager`: use Spring's abstraction and SpEL on top of a JCache provider.
- JCache annotations + `@EnableCaching`: use standard `javax.cache.annotation`; Spring handles interception.
- Native JCache API: explicitly invoke `CachingProvider`, `CacheManager`, and `Cache` in code.
- Controlled combination: only when keys, null policies, lifecycles, and access-path semantics are unified.

**Selection principle:** standardizing the API does not eliminate differences between providers. Clearly decide who owns the cache lifecycle, key generation, expiry/sizing, null policy, invalidation, and multi-node operability.

## Official Documentation

- Spring Framework 6.2 — JCache (JSR-107) Annotations: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/jsr-107.html
- Spring Framework 6.2.8 — `org.springframework.cache.jcache` package Javadoc: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/cache/jcache/package-summary.html
- Spring Framework — `JCacheCacheManager` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/cache/jcache/JCacheCacheManager.html
- JCache API 1.1.1 — `javax.cache.annotation`: https://javadoc.io/static/javax.cache/cache-api/1.1.1/javax/cache/annotation/package-summary.html
- JSR-107 specification project: https://github.com/jsr107/jsr107spec
- Ehcache 3 — JSR-107 provider documentation: https://www.ehcache.org/documentation/3.9/107.html
- Ehcache 3.10.8 artifact: https://central.sonatype.com/artifact/org.ehcache/ehcache/3.10.8
