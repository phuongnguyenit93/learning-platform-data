# Precedence Order Between Global, Class, and Method Configuration in Spring Cache

## Learning Objectives

Spring Cache has multiple places for configuration: shared application infrastructure, the **@CacheConfig** annotation on a class, and direct attributes on **@Cacheable**, **@CachePut**, and **@CacheEvict** on individual methods. When the same choice is declared at multiple levels, you must determine the **final effective configuration of the cache operation** rather than looking at a single annotation.

After this lesson, you will:
1. Explain the **global → class → method** precedence order and why *the level closer to the operation has the right to override defaults*.
2. Accurately determine the effective **cacheNames**, **key/keyGenerator**, and **cacheManager/cacheResolver** for each invocation.
3. Distinguish **overriding a single attribute** from **replacing the entire class configuration**, and distinguish a **valid override** from mutually exclusive attribute pairs on the same operation.
4. Understand the roles of **@EnableCaching**, **CachingConfigurer**, **@CacheConfig**, and what belongs to the cache provider.
5. Run a Java 17 + Maven example to see how cache hits/misses differ when moving from global to class to method.

Scope: Spring Framework Cache Abstraction, using annotation-driven caching with the default proxy. The examples use Spring Framework 6.2.x (Java 17+), without depending on Spring Boot, Redis, or Caffeine. If using Spring Boot, auto-configuration can set up the infrastructure, but it **does not reverse the precedence rules** of cache annotations.

## 1. The Three-Layer Picture

~~~text
    GLOBAL LAYER (global infrastructure defaults)
    @EnableCaching + CachingConfigurer / default CacheManager,
    CacheResolver, KeyGenerator infrastructure
                   |
                   v
    CLASS LAYER (class defaults)
    @CacheConfig(cacheNames=..., keyGenerator=...,
                 cacheManager=..., cacheResolver=...)
                   |
                   v
    METHOD LAYER (operation customization)
    @Cacheable(...), @CachePut(...), @CacheEvict(...)
    cacheNames, key/keyGenerator, cacheManager/cacheResolver ...
                   |
                   v
         Actual cache operation
         -> select store -> compute key -> read/write/evict
~~~

General rule: **global defaults apply if a specific setting has not been chosen at the class or method level; @CacheConfig provides defaults for operations in the class; declarations directly on the operation have the highest precedence**.

This is neither a mechanism that "merges three configurations into one string" nor "a class annotation that automatically creates cache entries." Spring builds the effective configuration **for each cache operation** from its declared attributes and the remaining missing defaults.

Example:

~~~java
@CacheConfig(cacheNames = "products")
public class ProductService {
    @Cacheable
    public String find(String id) {
        return load(id);
    }

    @Cacheable(cacheNames = "premiumProducts")
    public String findPremium(String id) {
        return loadPremium(id);
    }
}
~~~

This is an illustrative snippet requiring imports, classes, and load methods supplied by the application. Selection result:
- **find** does not declare its own cacheNames → inherits **products** from @CacheConfig.
- **findPremium** specifies cacheNames on the method → uses **premiumProducts**, **without automatically adding products**.
- @EnableCaching must be present and calls must go through the Spring cache interceptor for the annotations to affect the cache.

A cache operation can also have a SpEL condition, a specific key, or its own policies. **@CacheConfig only provides defaults for the four attribute groups it supports**, not all attributes of @Cacheable or @CachePut.

## 2. Global Layer: Infrastructure Used When No Override Exists

In Spring, shared infrastructure determines:
- Which **CacheManager** manages the caches.
- Which **CacheResolver** determines the set of caches for an operation.
- The default **KeyGenerator** that builds keys when an operation has no SpEL key or specific generator.
- The **CacheErrorHandler** that handles cache errors; this is also an infrastructure customization, though it has no corresponding attribute on @CacheConfig.
- The proxy/AOP mechanism enabling interception when annotation caching is enabled.

Minimal configuration:

~~~java
@Configuration
@EnableCaching
public class CacheInfrastructure {
    @Bean
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products", "prices");
    }
}
~~~

This illustrative snippet is not standalone because full imports and services are omitted; it defines an in-memory cache manager. Without other customizations, Spring typically uses **SimpleKeyGenerator** and a **SimpleCacheResolver** backed by the default CacheManager. By default, infrastructure does not assign a specific cache name to **every** operation; the cache name must come from the operation/@CacheConfig or be decided by a custom CacheResolver.

### Customizing defaults with CachingConfigurer

An official way to configure annotation-driven caching is to implement **org.springframework.cache.annotation.CachingConfigurer** in a @Configuration class:

~~~java
@Configuration
@EnableCaching
public class CacheInfrastructure implements CachingConfigurer {
    @Bean
    @Override
    public CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }

    @Bean
    @Override
    public KeyGenerator keyGenerator() {
        return (target, method, params) ->
            "GLOBAL:" + String.valueOf(params[0]);
    }
}
~~~

This is a directional example without imports. Use @Bean for methods providing infrastructure beans; it lets Spring manage their lifecycle. The example generator assumes the operation has at least one parameter; **do not use it verbatim for no-argument methods**. In a real project, when implementing CachingConfigurer, avoid eagerly initializing complex dependencies or circular dependencies since caching infrastructure initializes early.

If a method does not specify key/keyGenerator and the class does not set a default keyGenerator, Spring uses the configured **global KeyGenerator**. If the class or method specifies its own strategy, it can replace the default generator for that operation.

**Do not confuse two meanings of "global":**
- **Spring Cache global:** the KeyGenerator and CacheManager/CacheResolver supplied to the interceptor.
- **Spring Boot/provider properties:** e.g., Redis or Caffeine settings, TTL, cache size, serialization format. Those values affect how the cache operates, **do not become @CacheConfig attributes**, and do not determine method annotation override rules.

## 3. Class Layer: @CacheConfig as Shared Defaults

The **@CacheConfig** annotation is placed on a class and supports exactly four main groups:

| @CacheConfig Attribute | Role |
| --- | --- |
| **cacheNames** | Default cache name(s) for operations in the class |
| **keyGenerator** | Bean name of the class's default KeyGenerator |
| **cacheManager** | Bean name of the CacheManager used to build the default CacheResolver when no resolver takes precedence |
| **cacheResolver** | Bean name of the class's default CacheResolver |

Example:

~~~java
@CacheConfig(
    cacheNames = "catalog",
    keyGenerator = "catalogKeyGenerator",
    cacheManager = "catalogManager"
)
public class CatalogService {

    @Cacheable
    public String get(String sku) {
        return load(sku);
    }
}
~~~

This is an illustrative snippet. For **get**, Spring uses cache **catalog**, bean **catalogKeyGenerator**, and bean **catalogManager** unless overridden on the operation itself. Beans with those names must actually exist in the ApplicationContext with the right types.

**@CacheConfig does not enable caching and does not create operations.** Having only @CacheConfig on a class without an appropriate @Cacheable/@CachePut/@CacheEvict does not store data automatically. @EnableCaching or an equivalent mechanism must activate the infrastructure; method calls must also pass through an appropriate proxy or weaving.

### Class defaults are not applied as an "all-or-nothing copy"

Within the same CatalogService, one method can override **cacheNames**, another can override **key**, and another can override nothing. Each operation is resolved independently.

~~~java
// Illustrative methods inside the class with @CacheConfig above.
@Cacheable
public String a(String sku) { return load(sku); }

@Cacheable(cacheNames = "catalogDetails")
public String b(String sku) { return loadDetail(sku); }

@Cacheable(key = "#p0")
public String c(String sku) { return load(sku); }
~~~

- **a** uses the class cache name, class generator, and class cache manager.
- **b** uses **catalogDetails** from the method, yet because it sets no key/keyGenerator or manager/resolver, it still inherits **catalogKeyGenerator** and **catalogManager** from the class.
- **c** uses **SpEL #p0** instead of the class keyGenerator, while **cacheNames=catalog** and **cacheManager=catalogManager** are still inherited.

Thus, overriding one attribute **does not erase** other defaults on the class.

## 4. Method Layer: Configuration Closest to the Operation Takes Precedence

There are three important groups to examine **individually**, rather than relying on a vague blanket rule.

### 4.1. cacheNames: the method replaces the class's default list

~~~java
@CacheConfig(cacheNames = {"items", "lookup"})
public class ItemService {
    @Cacheable
    public String find(String id) { return fromStore(id); }

    @Cacheable(cacheNames = "oneOff")
    public String findSpecial(String id) { return fromSpecialStore(id); }
}
~~~

Both methods are non-standalone examples. Cases:
- **find** uses the default cacheNames set **items, lookup**.
- **findSpecial** uses **oneOff**. The method's set is not automatically merged with items/lookup.

If you want a method to check two caches, declare them explicitly on the method or use an appropriate multi-name class default. Note that multiple caches on @Cacheable change lookup/put semantics and may behave differently with asynchronous providers; use only when you understand the intent.

**There is no mandatory global cacheNames list** inherited by @CacheConfig from @EnableCaching. When using a custom CacheResolver, cache names may be decided contextually by the resolver, which is the resolver's responsibility rather than automatically pulling names from the class.

### 4.2. key and keyGenerator: strategy chosen by precedence

**key** is a Spring Expression Language (SpEL) expression directly on the operation. **keyGenerator** is the name of a Java bean implementing KeyGenerator. Both serve the same purpose of generating keys, with different syntax.

Typical selection order:

~~~text
Has key = "SpEL expression" on operation?
   Yes -> use SpEL expression
   No  -> has keyGenerator = "beanName" on operation?
             Yes -> use that bean
             No  -> does @CacheConfig have keyGenerator?
                       Yes -> use class-level bean
                       No  -> use global default KeyGenerator
~~~

If no generator is customized, the default is **SimpleKeyGenerator**. With a single ordinary String parameter, the default key is usually that String itself; with multiple parameters, Spring wraps them in a SimpleKey. A business object used as a key needs valid equals()/hashCode(), and fields participating in equality must not mutate while the cache holds the entry.

A common point of confusion:

~~~java
@CacheConfig(keyGenerator = "normalizedKeyGenerator")
public class ProductService {

    @Cacheable(cacheNames = "products", key = "#p0")
    public String findExact(String sku) {
        return load(sku);
    }
}
~~~

**Valid.** Even though the class has a default keyGenerator, the method explicitly sets **key = "#p0"**; Spring **ignores @CacheConfig's default keyGenerator** for this operation. This is an **override between two levels**, not declaring two strategies simultaneously on the same operation.

Conversely:

~~~java
// WRONG: the same cache operation declares both non-empty.
@Cacheable(
    cacheNames = "products",
    key = "#p0",
    keyGenerator = "normalizedKeyGenerator"
)
public String find(String sku) { return load(sku); }
~~~

**Invalid:** key and keyGenerator are **mutually exclusive** at the operation level. Spring rejects this rather than silently picking one. The rule "method overrides class" does not make setting **two conflicting attributes on the method itself** valid.

### 4.3. cacheManager and cacheResolver: selecting where caches are resolved

- **cacheManager**: name of a CacheManager bean; normally, Spring creates/applies a SimpleCacheResolver backed by that manager.
- **cacheResolver**: name of a CacheResolver bean; can dynamically determine the cache set based on the operation and arguments.

An operation **must not simultaneously configure both cacheManager and cacheResolver** as two non-empty choices. Like key/keyGenerator, these are mutually exclusive routing mechanisms on the same operation.

A useful precedence diagram:

~~~text
Does operation specify cacheResolver? -> use operation's resolver
  otherwise, does operation specify cacheManager? -> use operation's manager
  otherwise, does class have @CacheConfig.cacheResolver? -> use class resolver
  otherwise, does class have @CacheConfig.cacheManager? -> use class manager
  otherwise -> use global default resolver/manager
~~~

The diagram assumes non-conflicting configuration at the same level. Remember **cacheResolver has authority to decide target caches**; some custom resolvers do not even need cacheNames on the annotation. When using SimpleCacheResolver, cacheNames takes effect according to the names provided by the operation.

Example overriding only the manager:

~~~java
@CacheConfig(
    cacheNames = "profiles",
    keyGenerator = "profileKeys",
    cacheManager = "primaryManager"
)
public class ProfileService {

    @Cacheable(cacheManager = "secondaryManager")
    public String find(String userId) { return load(userId); }
}
~~~

The **find** method still gets cacheNames=profiles and keyGenerator=profileKeys, but uses **secondaryManager**, not primaryManager. Note that secondaryManager must be able to resolve the **profiles** cache, otherwise the operation can fail when Spring looks up that cache.

### Summary table per attribute group

| Attribute Group | Global Default | Class @CacheConfig | Operation Annotation |
| --- | --- | --- | --- |
| **cacheNames** | No mandatory common name; depends on resolver | Default list of names | List specified on method replaces class default |
| **key / keyGenerator** | SimpleKeyGenerator or custom global | Default keyGenerator bean | SpEL key or keyGenerator bean overrides |
| **cacheManager / cacheResolver** | Infrastructure CacheManager/CacheResolver | Class default bean | Bean explicitly named on method |
| **condition, unless** | CachingConfigurer is not used for per-operation defaults | @CacheConfig lacks these attributes | Set individually on @Cacheable/@CachePut/@CacheEvict per annotation capabilities |
| **sync (on @Cacheable)** | Not a @CacheConfig attribute | Cannot be set at class level via @CacheConfig | Set on operation and subject to sync constraints |

**Per-attribute precedence** is the accurate way to read this table. If a method only changes cacheNames, all remaining omitted attributes continue to inherit or use their respective global defaults.

## 5. Runnable Java 17 + Spring Cache Example to Verify the Three Layers

The project illustrates **three places where rules are set**:
- **Global**: CachingConfigurer provides a CacheManager and a KeyGenerator normalizing to "G:SKU".
- **Class**: @CacheConfig changes defaults to classManager, classKeyGenerator producing "C:SKU", and cacheNames="classLookup".
- **Method**: one method sets its own cacheNames, cacheManager, and SpEL key; another sets only key to prove **the remaining class attributes stay in effect**.

The calls use two String variants `" sku-7 "` and `"SKU-7"`. The global/class generators normalize them to the same key; SpEL **#p0** on the method keeps the raw string intact and thus treats them as two distinct keys.

### Directory Structure

~~~text
spring-cache-precedence/
├── pom.xml
└── src/main/java/demo/CachePrecedenceDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-cache-precedence</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### src/main/java/demo/CachePrecedenceDemo.java

~~~java
package demo;

import org.springframework.cache.CacheManager;
import org.springframework.cache.annotation.CacheConfig;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.CachingConfigurer;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.cache.interceptor.KeyGenerator;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import java.util.Locale;
import java.util.concurrent.atomic.AtomicInteger;

public class CachePrecedenceDemo {

    private static String normalize(String sku) {
        return sku.trim().toUpperCase(Locale.ROOT);
    }

    // No @CacheConfig: uses global defaults.
    public static class GlobalService {
        private final AtomicInteger loads = new AtomicInteger();

        @Cacheable(cacheNames = "globalLookup")
        public String find(String sku) {
            return "global-load-" + loads.incrementAndGet();
        }
    }

    // Class with defaults different from global.
    @CacheConfig(
        cacheNames = "classLookup",
        keyGenerator = "classKeyGenerator",
        cacheManager = "classManager"
    )
    public static class LayeredService {
        private final AtomicInteger classLoads = new AtomicInteger();
        private final AtomicInteger methodLoads = new AtomicInteger();
        private final AtomicInteger keyOnlyLoads = new AtomicInteger();

        // No attributes set -> receives defaults from @CacheConfig.
        @Cacheable
        public String fromClass(String sku) {
            return "class-load-" + classLoads.incrementAndGet();
        }

        // Explicitly sets cacheNames, cacheManager, key -> method-level override.
        @Cacheable(
            cacheNames = "methodLookup",
            cacheManager = "methodManager",
            key = "#p0"
        )
        public String fromMethod(String sku) {
            return "method-load-" + methodLoads.incrementAndGet();
        }

        // Overrides only key; cacheNames and manager remain from @CacheConfig.
        @Cacheable(key = "#p0")
        public String keyOnlyOverride(String sku) {
            return "keyonly-load-" + keyOnlyLoads.incrementAndGet();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config implements CachingConfigurer {

        @Bean("globalManager")
        @Override
        public CacheManager cacheManager() {
            return new ConcurrentMapCacheManager("globalLookup");
        }

        @Bean("globalKeyGenerator")
        @Override
        public KeyGenerator keyGenerator() {
            return (target, method, params) ->
                "G:" + normalize((String) params[0]);
        }

        @Bean("classManager")
        public CacheManager classManager() {
            return new ConcurrentMapCacheManager("classLookup");
        }

        @Bean("methodManager")
        public CacheManager methodManager() {
            return new ConcurrentMapCacheManager("methodLookup");
        }

        @Bean("classKeyGenerator")
        public KeyGenerator classKeyGenerator() {
            return (target, method, params) ->
                "C:" + normalize((String) params[0]);
        }

        @Bean
        public GlobalService globalService() {
            return new GlobalService();
        }

        @Bean
        public LayeredService layeredService() {
            return new LayeredService();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                 new AnnotationConfigApplicationContext(Config.class)) {
            GlobalService global = ctx.getBean(GlobalService.class);
            LayeredService layered = ctx.getBean(LayeredService.class);

            System.out.println(global.find(" sku-7 "));
            System.out.println(global.find("SKU-7"));

            System.out.println(layered.fromClass(" sku-7 "));
            System.out.println(layered.fromClass("SKU-7"));

            System.out.println(layered.fromMethod(" sku-7 "));
            System.out.println(layered.fromMethod("SKU-7"));

            System.out.println(layered.keyOnlyOverride(" sku-7 "));
            System.out.println(layered.keyOnlyOverride(" sku-7 "));
            System.out.println(layered.keyOnlyOverride("SKU-7"));

            CacheManager gm = ctx.getBean(
                "globalManager", CacheManager.class);
            CacheManager cm = ctx.getBean(
                "classManager", CacheManager.class);
            CacheManager mm = ctx.getBean(
                "methodManager", CacheManager.class);

            System.out.println("global-key="
                + gm.getCache("globalLookup").get("G:SKU-7", String.class));
            System.out.println("class-key="
                + cm.getCache("classLookup").get("C:SKU-7", String.class));
            System.out.println("method-key="
                + mm.getCache("methodLookup").get("SKU-7", String.class));
            System.out.println("class-raw-key="
                + cm.getCache("classLookup").get("SKU-7", String.class));
        }
    }
}
~~~

### Running the program

Requires JDK 17+ and Maven installed. In the directory containing pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CachePrecedenceDemo
~~~

**Stdout produced by the demo's println statements** (omitting Maven or library logs):

~~~text
global-load-1
global-load-1
class-load-1
class-load-1
method-load-1
method-load-2
keyonly-load-1
keyonly-load-1
keyonly-load-2
global-key=global-load-1
class-key=class-load-1
method-key=method-load-2
class-raw-key=keyonly-load-2
~~~

Exact breakdown by group:

1. **GlobalService.find** specifies only cacheNames. Because there is no @CacheConfig or key on the method, the interceptor uses the global KeyGenerator. Both SKUs become the same **"G:SKU-7"**, the second call hits, outputting "global-load-1".
2. **LayeredService.fromClass** sets no operation-specific config. It picks up **cacheNames=classLookup**, **classManager**, and **classKeyGenerator** from @CacheConfig. Both SKU variants become **"C:SKU-7"**, outputting "class-load-1" for both.
3. **LayeredService.fromMethod** explicitly declares **methodLookup**, **methodManager**, and SpEL **#p0**. With two non-equal Strings, the actual method runs twice, outputting "method-load-1" and "method-load-2". It does not use classKeyGenerator.
4. **LayeredService.keyOnlyOverride** only sets **key = "#p0"**, so the cache name and manager **still come from the class**. Two calls with the same `" sku-7 "` string hit the same entry; the `"SKU-7"` call uses a different key and executes a second time.
5. The three lines **global-key**, **class-key**, and **method-key** directly verify the entries stored in their respective expected cache managers. The final line **class-raw-key** proves the method only overrode the key while still writing into classManager.

In the demo, ConcurrentMapCacheManager is initialized with a fixed list of cache names per manager to avoid ambiguity: **globalLookup**, **classLookup**, and **methodLookup** are not three names on the same manager. Thus, manager differences are verified via getCache on the right bean and key.

**Example limitations:** This is an in-memory cache in a single Java process; it does not simulate transactions, TTL, distributed data, or serialization. The demo strings are used to count actual method executions. The program assumes calls go through Spring proxies via beans obtained from AnnotationConfigApplicationContext, without self-invocation.

## 6. Reading a Real Configuration Attribute by Attribute

Suppose an application has a global KeyGenerator **globalKeys** and a global CacheManager **globalManager**. Applied class:

~~~java
@CacheConfig(
    cacheNames = "orders",
    keyGenerator = "orderKeys",
    cacheManager = "orderManager"
)
public class OrderService {
    @Cacheable
    public String get(String orderId) { return fromStore(orderId); }

    @Cacheable(key = "#p0")
    public String getExact(String orderId) {
        return fromStore(orderId);
    }

    @CachePut(cacheNames = "orderSnapshots")
    public String save(String orderId) { return updateStore(orderId); }

    @CacheEvict(key = "#p0", cacheManager = "archiveManager")
    public void invalidateArchive(String orderId) {
        updateArchiveIndex(orderId);
    }
}
~~~

This is an illustrative class, not standalone (missing imports and business methods). Do not treat it as a complete design: the four operations could collide on keys or produce stale data without clear conventions. The goal is to **compute the effective configuration**:

| Operation | cacheNames | Key Generation | Cache Manager/Resolver |
| --- | --- | --- | --- |
| get | orders (class) | orderKeys (class) | orderManager (class) |
| getExact | orders (class) | SpEL #p0 (method) | orderManager (class) |
| save | orderSnapshots (method) | orderKeys (class) | orderManager (class) |
| invalidateArchive | orders (class) | SpEL #p0 (method) | archiveManager (method) |

Specifically, **save** specifies a new cache name but **does not change the class manager**. To run properly, the orderManager bean must be able to resolve both orders **and orderSnapshots**. **invalidateArchive** selects archiveManager while still using cacheNames=orders from the class; the archiveManager bean must contain the orders cache or have an appropriate dynamic cache creation policy. If missing, errors usually come from the resolver/manager rather than precedence order.

If operations are meant to read/write/delete the same entry, you must ensure **cache name, manager/resolver, and key logic all match**, instead of relying solely on them residing in the same class.

## 7. Not All Attributes Have Three Levels of Customization

An important aspect of the annotation architecture: **@CacheConfig does not have condition, unless, sync, beforeInvocation, or allEntries**. Therefore, there is no @CacheConfig.class.condition or "global condition" automatically inherited by every @Cacheable.

Example:

~~~java
@Cacheable(
    cacheNames = "prices",
    condition = "#p1",
    unless = "#result == null"
)
public String price(String sku, boolean allowCaching) {
    return loadPrice(sku);
}
~~~

This is an illustrative method. condition and unless belong only to the operation according to that annotation's rules. Class defaults **do not fill in** condition or unless when a method leaves them blank. To apply a conditional policy across many methods, another design approach is needed (such as a properly built and tested composed annotation), rather than putting condition on @CacheConfig.

### @CacheConfig does not handle provider configuration

The following belong to the **cache implementation**, not the annotation override mechanism:
- TTL or time-to-idle of each cache.
- Entry limits / Caffeine eviction strategies.
- Serializer, prefix, and TTL for Redis.
- Transaction awareness of CacheManager.
- Null-value policies or namespace naming conventions in distributed systems.

For example, a method with **@Cacheable(cacheNames = "shortTtl")** selects the cache named shortTtl. However, the method **does not implicitly "override TTL"** via this annotation; TTL must be configured in the corresponding provider/cache manager. Changing the cache name can cause the method to pick a cache with a different TTL, yet the annotation itself carries no ttl attribute.

## 8. Conflicts vs. Valid Overrides

Comparison table to avoid confusion:

| Configuration | Verdict |
| --- | --- |
| Global keyGenerator + @CacheConfig(keyGenerator="classKeys") | Valid; class overrides global default |
| Class keyGenerator="classKeys" + method key="#p0" | Valid; method uses SpEL instead of class generator |
| Class cacheManager="classManager" + method cacheManager="methodManager" | Valid; method uses specified manager |
| Class cacheNames={"a","b"} + method cacheNames="c" | Valid; method replaces class list with c |
| Method key="#p0", keyGenerator="classKeys" | **Invalid:** conflict directly on the operation |
| Method cacheManager="x", cacheResolver="y" | **Invalid:** conflict directly on the operation |
| Method keyGenerator="missingBean" | **Runtime misconfiguration:** bean missing/wrong type |
| Only @CacheConfig without operations | No automatic cache operations |
| Annotations present without @EnableCaching or equivalent configuration | No caching interceptor as expected |
| @Cacheable called from another method in the same instance | Typically not intercepted by proxy in default proxy mode |

**Note on class-level conflicts:** If class configuration sets a custom cacheResolver and a method picks a specific cacheManager, by the operation customization principle, the method's choice takes precedence; still, keep the design clean and avoid declaring mutually exclusive options simultaneously **on a single operation**. When writing a custom dynamic CacheResolver, confirm how it handles cacheNames.

### Do not look for "a single precedence order" for every situation

For example, "method specifies new cacheNames" only chooses the cache name; it does not mean the method replaced all keys/managers. Conversely, "method sets key" causes **the class keyGenerator to be ignored** because they are two mutually exclusive strategies in **the same key-generation group**. When debugging, inspect **the attribute group** and **the operation**, not merely which level appears last in the Java file.

## 9. How to Determine the Effective Configuration When Debugging

For any cache operation, proceed step by step:

1. **Identify the actual operation:** which method has @Cacheable, @CachePut, or @CacheEvict? Are multiple operations grouped via @Caching or a composed annotation? Execution mechanics differ per operation.
2. **Determine cacheNames:** does the method declare any? If not, does @CacheConfig supply them? If not, how might the resolver decide the cache name?
3. **Determine key generation:** does the method have a SpEL key? If not, which method/class/global keyGenerator applies? How are inputs normalized?
4. **Determine the store:** does the method have cacheManager/cacheResolver? If not, what does the class choose? If the class chooses neither, which global resolver/manager is active?
5. **Check beans by name:** keyGenerator, cacheManager, and cacheResolver are **bean names in the container**. Even if spelled correctly, if the bean is missing from the context or has the wrong type, the operation cannot run properly.
6. **Check the proxy:** is the bean actually managed by the container and called externally through the proxy? If instantiated with `new` or via self-invocation, annotations may not fire.
7. **Observe behavior:** log actual method execution, cache config, keys, and hit/miss outcomes for several input pairs. Never deduce hit/miss solely from annotation names.
8. **Compare related operations:** do @CachePut or @CacheEvict share the same manager, cacheName, and key strategy as @Cacheable?

A helpful technique: in test environments, inspect entries directly from the right CacheManager bean using **getCache(cacheName).get(key)**. In production systems, only log **sanitized** keys/metadata, avoiding putting tokens, sensitive userIds, or confidential data into logs.

### Distinguishing layering from bean visibility

When an application has multiple ApplicationContexts (e.g., root/child contexts), the @EnableCaching bean and annotated services must be configured in the appropriate context. A keyGenerator in another context or shadowed by a bean with the same name can produce unexpected behavior. "Precedence" attributes cannot bypass bean resolution rules and ApplicationContext scoping. When using Spring Boot, check beans created by auto-configuration when multiple CacheManagers/KeyGenerators exist, rather than assuming "a bean named cacheManager" always wins over explicit CachingConfigurer configurations.

## 10. Real-World Scenarios: Configuration Changes Causing Cache Misses

### Scenario A: Global normalized key, method switches to raw key

Global infrastructure previously produced the key **"SKU-7"**. A new method declares **key="#p0"** while the argument can be `" sku-7 "`. Despite sharing the same cacheName, the method uses the raw String key and misses existing entries.

Solution: standardize normalization across all operations using intentional SpEL normalization or a shared KeyGenerator. Do not update only the find method and forget @CacheEvict.

### Scenario B: Class manager writes to local cache, one method switches to Redis

The class uses localManager, while a method specifies redisManager. Even with the same cacheNames and key logic, **they are still two different stores**. Callers using the old configuration cannot read entries from the new manager. When changing production environments, plan an appropriate migration/warmup/invalidation strategy.

### Scenario C: Method changes cacheNames but class manager lacks that cache

Class `@CacheConfig(cacheManager="fixedManager", cacheNames="known")` uses a manager with a static cache set. A method specifies `cacheNames="newName"`. Because the method **did not change the manager**, fixedManager is still used and may fail to find cache newName. This is a compatibility issue between **the effective cache name** and **the effective manager**, not Spring ignoring precedence order.

### Scenario D: Assuming @CacheConfig automatically enables caching

A class has @CacheConfig and @Cacheable, but no caching annotation infrastructure, or the service was created with `new` and does not go through a proxy. The method executes every time, not because of selecting the wrong keyGenerator tier. Fix: enable @EnableCaching and obtain the bean from the container; avoid self-invocation in proxy mode.

### Scenario E: @CachePut and @CacheEvict override inconsistently

A read method uses class cacheName **products** and class keyGenerator; an update method sets a new cacheName **productsV2** and its own SpEL key. You assume they update/delete the same cache, yet they target two different entries or caches. Tabulate every operation across the three groups—cacheName, key, manager/resolver—and ensure they share the same cache identity when business logic requires it.

## 11. Testing and Configuration Review Checklist

| Test Case | Expected Result |
| --- | --- |
| Class without @CacheConfig, operation without custom key | Global KeyGenerator is used |
| Class with @CacheConfig(keyGenerator="classKeys"), operation leaves it blank | Class generator is used |
| Method in the class above sets key="#p0" | Method SpEL beats class generator |
| Method changes only cacheNames | KeyGenerator and manager from class stay in effect |
| Method changes only cacheManager | key/cacheNames from class stay in effect |
| Method has both key and keyGenerator non-empty | Rejected; does not silently pick one |
| Method has both cacheManager and cacheResolver non-empty | Rejected; does not silently pick one |
| New cacheName missing in static manager | Cache resolution may fail; add cache or change manager |
| Method with @Cacheable called via Spring proxy | Actual hit/miss observable |
| @CacheConfig alone, without @Cacheable/@CachePut/@CacheEvict | No automatic cache action |

When there are multiple services, write **integration tests** using ApplicationContext to verify each operation. Unit testing a KeyGenerator only tests the key algorithm; it **does not prove Spring picks that generator according to precedence**. To confirm the actual selection, invoke the proxied bean and/or inspect entries in the right CacheManager.

Add tests for cases where read and update methods touch the same data: in an application, **consistency across read/write/evict** is just as important as each method working individually.

## 12. Self-Check Questions

**Question 1.** Global KeyGenerator is globalKeys, the class sets @CacheConfig(keyGenerator="classKeys"), and the method sets @Cacheable(cacheNames="products"). Which KeyGenerator is used?

**Answer:** **classKeys**; because the method sets no custom key or keyGenerator, and the class overrides the global default.

**Question 2.** The class sets @CacheConfig(keyGenerator="classKeys"), and the method sets @Cacheable(key="#p0"). Is this an error for declaring two key strategies?

**Answer:** **No**. The method uses the SpEL key; classKeyGenerator is merely a default and is ignored for this operation. An actual conflict is setting both **key** and **keyGenerator** non-empty directly on **the same operation**.

**Question 3.** The class sets cacheNames={"a","b"}, and the method sets cacheNames="c". Will all three caches be checked?

**Answer:** **Not automatically**. The method list **c** replaces the class default for this operation.

**Question 4.** The class chooses classManager and classKeys, and the method only sets cacheManager="otherManager". Which key is generated?

**Answer:** **classKeys** is still used if there is no SpEL key or other keyGenerator on the method. Only the manager is changed.

**Question 5.** A method declares cacheManager="x" and cacheResolver="y" at the same time. Does Spring pick one by precedence?

**Answer:** **No**. These are mutually exclusive choices on a single cache operation; the configuration is invalid.

**Question 6.** A class has @CacheConfig(cacheNames="orders") but no @Cacheable or other cache operation annotation. Does it automatically store data?

**Answer:** **No**. @CacheConfig only sets defaults; specific operations and enabled cache annotation infrastructure are required.

**Question 7.** A method changes cacheName from "orders" to "orderPreview" without changing cacheManager. Is it guaranteed to work?

**Answer:** **Not yet**. The manager or resolver must still be able to resolve a cache named **orderPreview**; otherwise, cache resolution will fail.

## Summary

- Default customization order is **global < class @CacheConfig < operation annotation**, evaluated **per attribute group**.
- **@CacheConfig** has four default groups: **cacheNames**, **keyGenerator**, **cacheManager**, **cacheResolver**; it **does not enable caching on its own**.
- A method setting a **SpEL key** validly overrides the **class-level default keyGenerator**. However, putting **both key and keyGenerator on the same operation** is invalid; **both cacheManager and cacheResolver on the same operation** is also invalid.
- When a method overrides only one setting, other class/global defaults can still apply; **do not treat an override as wiping out all class configuration**.
- To debug accurately, always identify **the effective cache name, effective key, effective resolver/manager, and the path through the Spring proxy**.
- Even with correct configuration precedence, cached data can still be wrong if **read, write, and delete operations do not agree on the storage location and key rules**.

### Official References

- Spring Framework 6.2 – Annotation-driven caching and configuration order: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Spring Framework – @CacheConfig API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/CacheConfig.html
- Spring Framework – CachingConfigurer API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/CachingConfigurer.html
- Spring Framework – @EnableCaching API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/annotation/EnableCaching.html
- Spring Framework – CacheResolver API: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/interceptor/CacheResolver.html
