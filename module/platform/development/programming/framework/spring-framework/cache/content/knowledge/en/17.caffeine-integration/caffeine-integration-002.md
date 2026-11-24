# Declaring Caffeine Configuration via Builder or Specification String in Spring Cache

## Lesson Objectives

When using the **Spring Framework Cache Abstraction** with **Caffeine**, you can configure capacity, entry expiration, and statistics in two common ways:

1. **Builder API**: write Java using **Caffeine.newBuilder()**, and pass the builder to **CaffeineCacheManager.setCaffeine(...)**.
2. **Specification string**: declare a string such as **maximumSize=1000,expireAfterWrite=10m,recordStats** and pass it to **CaffeineCacheManager.setCacheSpecification(...)**; or parse it into a **CaffeineSpec** and call **setCaffeineSpec(...)**.

Both configure policies for the native Caffeine cache; they differ in expressiveness, flexibility, testability, and configuration source. This lesson helps you choose the right approach, run a Java 17 example, distinguish Caffeine configuration from Spring Cache annotations, and avoid several very common mistakes.

**Technical context:** Spring Framework **6.2.19**, Caffeine **3.2.4**, Java **17+**. The runnable project uses plain Spring Framework without Spring Boot. The Spring Boot section is presented separately because its auto-configuration mechanism follows a different precedence order than calling multiple setters manually on a single CacheManager.

## 1. Three Layers in Spring Cache – Caffeine Integration

~~~text
Application calls Spring bean @Cacheable / @CachePut / @CacheEvict
                      |
                      v
           Spring CacheInterceptor
              cacheName + key
                      |
                      v
       Spring CacheManager (CaffeineCacheManager)
                      |
              getCache("products")
                      |
                      v
          Spring CaffeineCache adapter
                      |
                      v
        Caffeine native cache in the JVM
    maximumSize / expiry / stats / eviction
~~~

- **@Cacheable, @CachePut, @CacheEvict** define read, write, or delete **operations** and typically specify the cache name, key, and conditions.
- **CaffeineCacheManager** is Spring's manager-level adapter. It creates/registers **CaffeineCache** instances and selects a cache by name.
- **Caffeine.newBuilder()** or **CaffeineSpec** defines the **native cache policy**: entry count limits, expiration timing, statistics collection, etc.
- **CaffeineCache** bridges the **org.springframework.cache.Cache** interface with Caffeine's native implementation.

This layering matters because a line like **@Cacheable(cacheNames="products")** does **not** have a place to set **maximumSize** or **expireAfterWrite** directly. TTL, size, and listeners are configured on the **cache manager/native cache**, not added as attributes to @Cacheable.

### Before Configuring, Two Libraries Are Required

In plain Spring Framework, **spring-context** provides the annotation caching infrastructure, while the **org.springframework.cache.caffeine.CaffeineCacheManager** adapter resides in **spring-context-support**. The actual Caffeine library is the artifact **com.github.ben-manes.caffeine:caffeine**.

You cannot add only Caffeine and expect Spring to auto-create CaffeineCacheManager; conversely, having spring-context-support without the Caffeine artifact prevents using the native Caffeine adapter properly.

Spring Boot provides **spring-boot-starter-cache** for auto-configuration support, yet it also requires **Caffeine on the classpath** to select the provider via auto-configuration.

## 2. Approach 1: Using Caffeine.newBuilder() to Configure in Java

The builder provides fluent Java method calls, IDE autocompletion, and clear structure:

~~~java
import com.github.benmanes.caffeine.cache.Caffeine;
import java.time.Duration;

Caffeine<Object, Object> builder = Caffeine.newBuilder()
    .initialCapacity(64)
    .maximumSize(1_000)
    .expireAfterWrite(Duration.ofMinutes(10))
    .recordStats();
~~~

This is an **illustrative snippet**, not a standalone runnable class. Key parameters:

| Builder API | Meaning |
| --- | --- |
| **initialCapacity(64)** | Initial capacity hint for internal storage structures; not a hard limit |
| **maximumSize(1000)** | Caps entry count by size; Caffeine applies its eviction policy |
| **expireAfterWrite(Duration.ofMinutes(10))** | Entries expire 10 minutes after creation/overwrite, per Caffeine semantics |
| **expireAfterAccess(Duration.ofMinutes(5))** | Expires after a period of no access |
| **recordStats()** | Collects cache statistics: hits, misses, evictions, and related metrics |
| **scheduler(...)** | Allows an appropriate scheduling policy when features need a scheduler |
| **removalListener(...)** | Callback notified when an entry is removed |
| **expireAfter(Expiry<K,V>)** | Custom per-entry expiration based on creation/update/access context |
| **weigher(...) + maximumWeight(...)** | Bounds capacity by custom weight instead of entry count |

**maximumSize** and **maximumWeight** are mutually exclusive size-limiting modes and must not be configured together. **initialCapacity** is not maximumSize; it only provides an initial allocation hint.

### Passing the Builder to CaffeineCacheManager

~~~java
import org.springframework.cache.caffeine.CaffeineCacheManager;

CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCaffeine(
    Caffeine.newBuilder()
        .maximumSize(1_000)
        .expireAfterWrite(Duration.ofMinutes(10))
        .recordStats()
);
manager.setCacheNames(java.util.List.of("products", "categories"));
~~~

This is a snippet inside a CacheManager factory method; imports for Duration, Caffeine, and List are needed. **setCaffeine(...)** sets the builder used for caches created under the manager's **shared configuration**. **setCacheNames(...)** defines the cache names in **static mode**; the manager will then not auto-create arbitrary names outside the list.

With the same shared-configuration builder, **products** and **categories** are **two separate cache regions**: key `"P1"` in products does not collide with key `"P1"` in categories. Both share a **common policy** (maximumSize, TTL, stats), **not a shared pool of entries** or a combined 1,000-entry limit. Each native cache applies the policy to its own region.

### When Does the Builder Excel?

The builder is suitable when:
- You need a custom **Expiry**, **removalListener**, **weigher**, **Ticker**, **Executor**, or other custom Java component that cannot be expressed in a simple specification string.
- You need conditional configuration, such as reading TTL from a validated configuration object.
- You want reusable typed configuration with IDE checks, unit tests, and refactoring support.
- You want to declare multiple distinct native Caffeine caches with different characteristics.

With the builder, avoid calling **Caffeine.newBuilder().build()** manually inside every service if the whole system uses Spring Cache abstraction: creating many independent caches easily leads to mismatched cacheNames and inconsistent configuration.

## 3. Approach 2: Using a CaffeineSpec Specification String

**CaffeineSpec** represents a set of builder settings as a **comma-separated key=value string**:

~~~properties
maximumSize=1000,expireAfterWrite=10m,recordStats
~~~

Values:
- **maximumSize=1000**: caps at approximately 1,000 entries under Caffeine's policy.
- **expireAfterWrite=10m**: expires 10 minutes after write.
- **recordStats**: enables statistics; **no =true is needed** in CaffeineSpec syntax.
- Do not include spaces, Java parentheses, or quotes inside the parsed specification string.

Usage in Spring:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCacheSpecification(
    "initialCapacity=64,maximumSize=1000,"
        + "expireAfterWrite=10m,recordStats"
);
manager.setCacheNames(java.util.List.of("products"));
~~~

Here Java string concatenation is only for multi-line source formatting; the resulting string is still a valid single specification. Unlike the builder, **setCacheSpecification(String)** accepts configuration read from properties/environment without chaining multiple fluent calls.

### CaffeineSpec.parse and setCaffeineSpec

You can parse the string into a CaffeineSpec object before passing it to the manager:

~~~java
import com.github.benmanes.caffeine.cache.CaffeineSpec;

CaffeineSpec spec = CaffeineSpec.parse(
    "maximumSize=1000,expireAfterWrite=10m,recordStats");

CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCaffeineSpec(spec);
manager.setCacheNames(java.util.List.of("products"));
~~~

**setCaffeineSpec(spec)** and **setCacheSpecification(string)** both configure the **common Caffeine policy**, but accept **two different argument types**. There is no need to call both on the same manager. When you already have a parsed/validated CaffeineSpec object from configuration, using setCaffeineSpec is natural; if you have a plain string, use setCacheSpecification.

### Keys Supported by CaffeineSpec

In Caffeine 3.x, the specification covers common groups:

| Key / flag | Example | Notes |
| --- | --- | --- |
| **initialCapacity** | initialCapacity=64 | Initial capacity |
| **maximumSize** | maximumSize=1000 | Entry count limit |
| **maximumWeight** | maximumWeight=100000 | Weight limit; pair with a weigher if custom weight logic is needed |
| **expireAfterWrite** | expireAfterWrite=10m | Expires after write |
| **expireAfterAccess** | expireAfterAccess=5m | Expires after period without access |
| **refreshAfterWrite** | refreshAfterWrite=1m | Refresh policy; **must check loader support requirements** |
| **recordStats** | recordStats | Enables statistics |
| **weakKeys** | weakKeys | Weak references for keys |
| **weakValues** | weakValues | Weak references for values |
| **softValues** | softValues | Soft references for values |

Durations in common strings support suffixes **s**, **m**, **h**, **d**, and CaffeineSpec may also support ISO-8601 duration format; use the syntax matching your library version.

**Cannot be combined**:
- **maximumSize** with **maximumWeight**.
- **weakValues** with **softValues**.

If a string contains an unsupported key or invalid value, **CaffeineSpec.parse(...) / Caffeine.from(...) may throw IllegalArgumentException during configuration**. Validate early at application startup rather than swallowing the exception and falling back to an unbounded cache.

### A Specification String Is Not a Programming Language

You cannot embed lambdas or callbacks in a specification. The following is **invalid syntax**:

~~~properties
removalListener=(key,value,cause)->logger.info(key)
weigher=(key,value)->value.size()
~~~

To use **removalListener**, **weigher**, custom **Expiry**, **Ticker**, **Scheduler**, etc., use the **Java builder**. If you only need maximumSize and simple TTLs, a specification is easier to configure per environment.

## 4. Comparing Builder vs. Specification by Use Case

| Criterion | **Builder API** | **CaffeineSpec / string** |
| --- | --- | --- |
| Declaration style | Java fluent API | Comma-separated configuration text |
| IDE/type checking | Method names checked at compile time | Syntax checked at parse/configure time |
| Basic TTL, size, stats | Yes | Yes |
| Custom listeners and callbacks | Yes | No arbitrary callback objects allowed |
| Custom per-entry expiry | Yes via Expiry | Cannot express Expiry lambda/object |
| Reading from application.properties/YAML | Requires binding data then building | Very convenient |
| Usage in plain Spring Framework | setCaffeine(builder) | setCaffeineSpec(spec) or setCacheSpecification(string) |
| Testing | Test builder/policy in Java | Test spec parsing + native cache policy |
| Dynamic config management | Can rebuild manager/caches by design | Can change string, but must mind existing caches |
| Clarity | Good for complex policies | Good for simple policies externalized from code |

**Two configurations equivalent in intent**:

~~~java
// Builder
Caffeine.newBuilder()
    .maximumSize(500)
    .expireAfterAccess(Duration.ofMinutes(10))
    .recordStats();
~~~

~~~properties
# CaffeineSpec
maximumSize=500,expireAfterAccess=10m,recordStats
~~~

Both express the policy "maximum 500 entries, expire after 10 minutes without access, collect stats". They do **not turn @Cacheable into a distributed tool**, create transactions, or replace invalidation when the source changes.

### Choosing expireAfterWrite or expireAfterAccess?

- **expireAfterWrite**: freshness is anchored to **write time**, suitable when you do not want entries to live too long merely because they are read continuously.
- **expireAfterAccess**: expiration refreshes on **access**, useful for infrequently accessed data, though hot entries may live long if hit continuously.
- No TTL guarantees the cache is immediately fresh after a database update; pair with @CachePut, @CacheEvict, or another consistency strategy.
- Caffeine may run maintenance/expiry during access operations or via a scheduler task; do not infer from expireAfterWrite=10m that a background thread always deletes entries on the exact millisecond even when the cache is idle.

## 5. Creating CaffeineCacheManager in a Real Spring Application

In plain Spring Framework, **@EnableCaching** enables annotation-driven interception. Register CaffeineCacheManager as a bean using **@Configuration + @Bean**:

~~~java
@Configuration
@EnableCaching
public class CacheConfig {
    @Bean
    public CacheManager cacheManager() {
        CaffeineCacheManager manager = new CaffeineCacheManager();
        manager.setAllowNullValues(false);
        manager.setCaffeine(
            Caffeine.newBuilder()
                .maximumSize(500)
                .expireAfterWrite(Duration.ofMinutes(15))
                .recordStats()
        );
        manager.setCacheNames(List.of("products", "categories"));
        return manager;
    }
}
~~~

This is an illustrative class missing imports; refer to section 8 for a complete runnable example. **@EnableCaching** and the cache manager solve **two different concerns**:
- @EnableCaching sets up the Spring AOP infrastructure that processes caching annotations.
- CacheManager provides named cache regions with the defined Caffeine policy.

If you only use the programmatic **Cache API**, @EnableCaching may not be needed; however, if you use @Cacheable/@CachePut/@CacheEvict, annotation caching (or an equivalent mechanism) must be enabled and methods called through a Spring proxy.

### Dynamic and Static Cache Creation Modes

**Dynamic mode**:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCacheSpecification(
    "maximumSize=1000,expireAfterWrite=10m");
Cache discovered = manager.getCache("newName");
~~~

With the no-name constructor and no restricted cacheNames, CaffeineCacheManager can **create caches on demand by name**, so a typo in cacheName sometimes creates a new cache instead of raising an error.

**Static mode**:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCacheSpecification(
    "maximumSize=1000,expireAfterWrite=10m");
manager.setCacheNames(List.of("products", "categories"));
Cache unknown = manager.getCache("typo");
~~~

The snippet above returns **null** when requesting the name **typo** not present in the static list (excluding custom-registered caches). Static mode is useful when you want to control namespaces and catch configuration mistakes early.

**Note:** setCacheNames(null) switches back to dynamic mode in the Spring API; do not use it to represent an empty static cache list.

### Caches in a Manager Share Policy, Not Data

When calling setCaffeine(builder) or setCacheSpecification(spec) on a CaffeineCacheManager, caches **created by the manager under shared configuration** share the same policy structure. However, **products** and **categories** still have separate key namespaces, each with its own statistics, capacity, and eviction.

If **products** needs to expire after 10 minutes while **categories** expires after 1 hour, do not put both names in the same manager and expect Caffeine to differentiate TTLs by cacheName automatically. Use separate managers, or **registerCustomCache** with per-cache policies.

## 6. Per-Cache Configuration: registerCustomCache

Spring supports registering a dedicated native Caffeine Cache via **registerCustomCache**:

~~~java
CaffeineCacheManager manager = new CaffeineCacheManager();
manager.setCaffeine(
    Caffeine.newBuilder()
        .maximumSize(1000)
        .expireAfterWrite(Duration.ofMinutes(10))
);

manager.registerCustomCache(
    "shortLived",
    Caffeine.newBuilder()
        .maximumSize(100)
        .expireAfterWrite(Duration.ofSeconds(30))
        .build()
);

manager.registerCustomCache(
    "longLived",
    Caffeine.newBuilder()
        .maximumSize(2000)
        .expireAfterWrite(Duration.ofHours(1))
        .build()
);
~~~

This Java snippet illustrates **manager** configuration; imports and enclosing class/method are required. The two caches **shortLived** and **longLived** use the **custom native caches** passed in, rather than the shared policy used for normal manager-created caches. Other names created by the manager (in dynamic mode) use **maximumSize=1000, expireAfterWrite=10 minutes**.

You can use registerCustomCache alongside a static cacheNames list, but verify names and lifecycles when changing configuration. **Do not confuse registerCustomCache with registering a global listener**; it registers a separate native cache instance.

Note:
- Native Caffeine **Cache<K,V>** is different from the **org.springframework.cache.Cache adapter**.
- If a custom cache uses its own listener or Expiry, manage its lifecycle and test its policy separately.
- Manager reset/reconfigure operations may affect regular caches; read the Javadoc of your exact version before changing configuration while the app is serving requests.
- If a provider replaces an existing cache that holds entries with a new cache, warm cache data can be lost; do not treat changing setters as a risk-free "hot" TTL swap.

## 7. Spring Boot Configuration: Precedence Rules to Watch

In Spring Boot with caching auto-configuration, typically add **spring-boot-starter-cache** and the **caffeine** dependency, then enable caching in the app. Boot can automatically create a **CaffeineCacheManager** when an appropriate provider is detected.

Example **application.properties**:

~~~properties
spring.cache.type=caffeine
spring.cache.cache-names=products,categories
spring.cache.caffeine.spec=maximumSize=500,expireAfterWrite=10m,recordStats
~~~

Equivalent in **application.yaml**:

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names: products,categories
    caffeine:
      spec: "maximumSize=500,expireAfterWrite=10m,recordStats"
~~~

These properties are **Spring Boot configuration**, not keys in @Cacheable. For annotations to execute, the app must enable caching appropriately, usually with **@EnableCaching**.

### Selection Order When Boot Auto-Configures Caffeine

Spring Boot documentation lists customization sources considered **in order**:

1. **spring.cache.caffeine.spec** (property) if present.
2. A **CaffeineSpec** bean if present and no higher-precedence source exists.
3. A **Caffeine** builder bean if neither of the above exists.

Therefore, if an application has **both** the **spring.cache.caffeine.spec** property and a **Caffeine** builder bean, do not assume the builder bean will automatically override the property. Under normal auto-configuration, Boot prioritizes the **spec property** according to the list above.

This **differs** from manually constructing a CaffeineCacheManager and calling setters yourself. Choose one clear configuration source instead of relying on "which setter runs last". When you declare a custom CacheManager bean yourself, Spring Boot may back off from creating its default manager, so auto-configuration properties **do not necessarily** govern your custom bean.

### CaffeineSpec Bean in Boot

~~~java
@Bean
CaffeineSpec caffeineSpec() {
    return CaffeineSpec.parse(
        "maximumSize=500,expireAfterWrite=10m,recordStats");
}
~~~

This is a snippet for a @Configuration class or equivalent bean registration; imports are omitted. It is useful if you want to parse a shared configuration before handing it to Boot. However, if **spring.cache.caffeine.spec** is already set, that property source may be chosen before the bean.

### Builder Bean in Boot

~~~java
@Bean
Caffeine<Object, Object> caffeineBuilder() {
    return Caffeine.newBuilder()
        .maximumSize(500)
        .expireAfterWrite(Duration.ofMinutes(10))
        .recordStats();
}
~~~

This is an illustrative snippet. The builder bean is picked up by Boot when no higher-precedence source is present. You should still verify with an **integration test or by inspecting the native cache policy**, rather than just seeing the bean in ApplicationContext and assuming the config took effect.

### The CacheLoader Bean Trap

Boot can pick up a **CacheLoader<Object,Object>** bean and apply it to caches managed by the manager; setting a global loader is not equivalent to a cacheName-specific loader. If each cache needs different loading logic, design custom caches/managers for your needs and test them instead of letting a key-agnostic loader load the wrong data type.

## 8. Complete Java 17 Example: Both Configuration Ways Behave Identically

This is a runnable program using **plain Spring Framework** (no Spring Boot). We create **two separate CaffeineCacheManager beans** to compare:
- **builderManager**: setCaffeine(Caffeine.newBuilder()...).
- **specManager**: setCacheSpecification("...").
- Each manager has one cache and a corresponding @Cacheable method.
- We do not wait for TTL expiration, because real-time delays and scheduling make output non-deterministic; we verify both **hit behavior** and native **policy**.

To give Spring a default CacheManager when multiple beans exist, **builderManager** is marked **@Primary**. Both @Cacheable methods also specify cacheManager explicitly by name, so they do not rely on the default in this demo.

### 8.1. Structure

~~~text
caffeine-config-ways/
├── pom.xml
└── src/main/java/demo/CaffeineConfigWaysDemo.java
~~~

### 8.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>caffeine-config-ways</artifactId>
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
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context-support</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.github.ben-manes.caffeine</groupId>
            <artifactId>caffeine</artifactId>
            <version>3.2.4</version>
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

### 8.3. src/main/java/demo/CaffeineConfigWaysDemo.java

~~~java
package demo;

import com.github.benmanes.caffeine.cache.Caffeine;
import org.springframework.cache.annotation.Cacheable;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.cache.caffeine.CaffeineCache;
import org.springframework.cache.caffeine.CaffeineCacheManager;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

import java.time.Duration;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;

public class CaffeineConfigWaysDemo {

    public static class PriceService {
        private final AtomicInteger builderLoads = new AtomicInteger();
        private final AtomicInteger specLoads = new AtomicInteger();

        @Cacheable(
            cacheNames = "byBuilder",
            cacheManager = "builderManager",
            key = "#p0"
        )
        public String byBuilder(String sku) {
            return "builder-" + builderLoads.incrementAndGet();
        }

        @Cacheable(
            cacheNames = "bySpec",
            cacheManager = "specManager",
            key = "#p0"
        )
        public String bySpec(String sku) {
            return "spec-" + specLoads.incrementAndGet();
        }

        public int builderLoads() {
            return builderLoads.get();
        }

        public int specLoads() {
            return specLoads.get();
        }
    }

    @Configuration
    @EnableCaching
    public static class Config {

        @Bean("builderManager")
        @Primary
        public CaffeineCacheManager builderManager() {
            CaffeineCacheManager manager = new CaffeineCacheManager();
            manager.setAllowNullValues(false);
            manager.setCaffeine(
                Caffeine.newBuilder()
                    .initialCapacity(16)
                    .maximumSize(100)
                    .expireAfterWrite(Duration.ofMinutes(10))
                    .recordStats()
            );
            manager.setCacheNames(List.of("byBuilder"));
            return manager;
        }

        @Bean("specManager")
        public CaffeineCacheManager specManager() {
            CaffeineCacheManager manager = new CaffeineCacheManager();
            manager.setAllowNullValues(false);
            manager.setCacheSpecification(
                "initialCapacity=16,maximumSize=100,"
                    + "expireAfterWrite=10m,recordStats"
            );
            manager.setCacheNames(List.of("bySpec"));
            return manager;
        }

        @Bean
        public PriceService priceService() {
            return new PriceService();
        }
    }

    public static void main(String[] args) {
        try (var ctx =
                 new AnnotationConfigApplicationContext(Config.class)) {
            PriceService service = ctx.getBean(PriceService.class);

            System.out.println("builder-first="
                + service.byBuilder("SKU-1"));
            System.out.println("builder-second="
                + service.byBuilder("SKU-1"));
            System.out.println("spec-first="
                + service.bySpec("SKU-1"));
            System.out.println("spec-second="
                + service.bySpec("SKU-1"));

            System.out.println("builder-loads="
                + service.builderLoads());
            System.out.println("spec-loads="
                + service.specLoads());

            CaffeineCacheManager builderManager = ctx.getBean(
                "builderManager", CaffeineCacheManager.class);
            CaffeineCacheManager specManager = ctx.getBean(
                "specManager", CaffeineCacheManager.class);

            CaffeineCache builderCache = (CaffeineCache)
                Objects.requireNonNull(
                    builderManager.getCache("byBuilder"));
            CaffeineCache specCache = (CaffeineCache)
                Objects.requireNonNull(
                    specManager.getCache("bySpec"));

            System.out.println("builder-max="
                + builderCache.getNativeCache()
                    .policy().eviction().orElseThrow().getMaximum());
            System.out.println("spec-max="
                + specCache.getNativeCache()
                    .policy().eviction().orElseThrow().getMaximum());

            System.out.println("builder-expiry-policy="
                + builderCache.getNativeCache()
                    .policy().expireAfterWrite().isPresent());
            System.out.println("spec-expiry-policy="
                + specCache.getNativeCache()
                    .policy().expireAfterWrite().isPresent());

            System.out.println("unknown-cache="
                + (builderManager.getCache("typo") == null));
        }
    }
}
~~~

**Why does the example compile and run with this structure?**
- CaffeineCacheManager and CaffeineCache are in **spring-context-support**; @Cacheable/@EnableCaching are in **spring-context**.
- **caffeine** is the actual native dependency.
- **Caffeine.newBuilder()** has maximumSize, expireAfterWrite, and recordStats methods; **CaffeineSpec** parses the corresponding string.
- Spring methods are invoked on the **PriceService bean retrieved from the context**, so calls go through the cache interceptor rather than instantiating with `new`.
- @Primary clarifies the default manager when multiple CacheManagers exist; additionally, each @Cacheable specifies the manager name explicitly.
- **Objects.requireNonNull** guards against misconfigured cacheNames before inspecting native policy.
- The native Caffeine Policy API allows checking bounded maximum and the presence of expireAfterWrite without waiting 10 minutes.

### 8.4. Running

Requires JDK 17+ and Maven, in the directory containing pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.CaffeineConfigWaysDemo
~~~

**Expected stdout from System.out.println** (excluding separate Maven/library messages):

~~~text
builder-first=builder-1
builder-second=builder-1
spec-first=spec-1
spec-second=spec-1
builder-loads=1
spec-loads=1
builder-max=100
spec-max=100
builder-expiry-policy=true
spec-expiry-policy=true
unknown-cache=true
~~~

Interpretation:
1. **builder-first=builder-1** because the byBuilder cache is initially empty; @Cacheable misses and runs the actual method.
2. **builder-second=builder-1** because key SKU-1 is already in byBuilder; @Cacheable hits and does not increment the counter.
3. **spec-first/spec-second** behave similarly using a separate manager and cache; proving specification configuration also works.
4. **builder-loads=1/spec-loads=1** confirms both actual methods ran only once for the same key in each cache.
5. **builder-max=100/spec-max=100**: both native caches have a maximumSize policy of 100 entries.
6. **...expiry-policy=true**: the native cache has an expireAfterWrite policy; this test **does not measure whether the 10-minute TTL has actually elapsed**.
7. **unknown-cache=true**: builderManager is in static mode declaring only byBuilder, so it does not auto-create a region named typo.

**Do not conclude** that the two caches will have identical cache hits, entry counts, or actual statistics in every application. They are independent and merely share the same max/expiry policy here. In a real environment, TTL and eviction may produce different results if run long enough.

## 9. Reading and Verifying Native Caffeine Policies

To verify the configuration actually took effect, do not just look at properties or beans. You can inspect the native cache:

~~~java
import org.springframework.cache.caffeine.CaffeineCache;
import com.github.benmanes.caffeine.cache.Policy;

CaffeineCache springCache = (CaffeineCache)
    Objects.requireNonNull(cacheManager.getCache("products"));

com.github.benmanes.caffeine.cache.Cache<Object, Object> nativeCache =
    springCache.getNativeCache();

long max = nativeCache.policy()
    .eviction().orElseThrow().getMaximum();
boolean hasWriteExpiry =
    nativeCache.policy().expireAfterWrite().isPresent();
~~~

This is illustrative code requiring a **cacheManager** variable, **Objects** import, and a configured "products" cache. For caches with maximumSize, Policy.eviction() is typically present. If no eviction policy is set, the **Optional** may be empty; calling orElseThrow when no policy exists will throw an error.

**recordStats()** causes Caffeine to collect statistics, readable via:

~~~java
var stats = nativeCache.stats();
System.out.println("hitCount=" + stats.hitCount());
System.out.println("missCount=" + stats.missCount());
~~~

No fixed stats numbers are listed here because lookups/debugging or program execution may generate additional reads; statistics are live runtime data and vary with workload. If **recordStats()** was not called, Caffeine typically uses a no-op stats counter, which can mislead you into thinking the cache is not working. **Not enabling recordStats and not checking metrics** are two separate issues.

### Do Not Test TTL with Arbitrary Thread.sleep

To test expiry accurately and quickly:
- With the builder, you can configure a controllable **Ticker**, provided the provider uses that ticker.
- Use the policy API or virtual time where possible instead of making tests wait 10 minutes.
- After advancing simulated time, perform an appropriate cache operation to observe expiry; do not assume the maintenance scheduler runs instantaneously on an idle cache.
- Since specifications cannot express a Ticker object, use the builder if fake time is needed in tests.

A test that just sleeps with Thread.sleep(10_000) and concludes TTL accuracy can be flaky due to scheduling, GC, and clock drift; also, **10 seconds is not 10 minutes**. Separate **policy config tests** from **expiry behavior tests**.

## 10. Common Mistakes

### Mistake 1: Missing spring-context-support

You add the Caffeine + spring-context dependencies, but Java reports it cannot find **org.springframework.cache.caffeine.CaffeineCacheManager**.

**Solution:** add **org.springframework:spring-context-support** matching your Spring Framework version, along with a compatible **com.github.ben-manes.caffeine:caffeine** artifact. The pom.xml example in section 8 includes all required dependencies.

### Mistake 2: Writing an Invalid Specification

~~~properties
maximumSize: 1000; expireAfterWrite: 10 minutes
~~~

This is human-readable syntax, **not** a CaffeineSpec string. A specification uses a comma-separated list of key=value pairs:

~~~properties
maximumSize=1000,expireAfterWrite=10m,recordStats
~~~

Write a simple validator if configuration comes from an external system; at a minimum, call CaffeineSpec.parse at startup to fail fast on mistakes.

### Mistake 3: Mixing maximumSize and maximumWeight

~~~properties
maximumSize=1000,maximumWeight=100000
~~~

This configuration is invalid. Choose one limit type. If custom domain weighting is needed, use the builder with **weigher** and **maximumWeight**.

### Mistake 4: Thinking initialCapacity Is a Memory Limit

~~~java
Caffeine.newBuilder().initialCapacity(100);
~~~

Setting initialCapacity does not prevent the cache from growing beyond 100. To bound entries use maximumSize; to bound by proportional cost use maximumWeight/weigher. For an in-JVM reference cache, a cache without size/expiry bounds can retain entries too long and impact memory.

### Mistake 5: Putting TTL in @Cacheable

~~~java
// There is no ttl attribute in Spring's @Cacheable annotation.
@Cacheable(cacheNames = "products")
public Product find(String id) { return repository.find(id); }
~~~

This is illustrative and not standalone runnable. **@Cacheable only selects the operation/cacheName**. Caffeine TTL is set on the manager/native cache used. If different cacheNames need different TTLs, use multiple managers or registerCustomCache.

### Mistake 6: Calling Both Builder and Specification and Expecting Them to Merge

~~~java
manager.setCaffeine(Caffeine.newBuilder().maximumSize(1000));
manager.setCacheSpecification("expireAfterWrite=10m");
~~~

This snippet should **not** be relied upon as "maximumSize from builder + expiry from specification". Both setters configure the source for building common native caches; **do not assume the two policies merge**. Choose one complete configuration style; if you need both maximumSize and expiry, put **both in the builder** or **both in the spec**. Reconfiguring the manager after caches have been created may also replace existing caches and warm cache data.

### Mistake 7: Changing Specification at Runtime and Expecting Old Entries to Remain

You call setCacheSpecification with a new string while traffic is running. Spring's CaffeineCacheManager refreshes/recreates common caches depending on method and version; this cannot be treated as atomically adjusting per-entry TTL on a live native cache. Plan rollouts, testing, and monitoring of hits/misses/cache warmup.

**If you need dynamic policy changes**, design an appropriate mechanism (such as controlled cache rebuilding, feature rollout, or native policy APIs within provider capabilities), rather than arbitrarily calling setters on a manager shared across threads.

### Mistake 8: Misspelled Cache Name in Static Mode

~~~java
manager.setCacheNames(List.of("products"));
Cache cache = manager.getCache("product"); // Wrong name.
~~~

**getCache("product")** returns null in static mode when that cache does not exist. Similar names are not aliases. Verify cacheNames in both @Cacheable and the manager.

### Mistake 9: Adding Only the Caffeine Dependency and Expecting Every @Cacheable to Cache

You need **@EnableCaching** (or equivalent annotation caching infrastructure), a valid CacheManager bean, and calls **through a Spring proxy**. Self-invocation within the same bean typically bypasses cache advice in default proxy mode.

### Mistake 10: Assuming recordStats Is Enabled by Default

Caffeine does not enable full statistics collection on every new cache by default. If you want to observe hits/misses via Caffeine stats, enable **recordStats** on the builder/spec and inspect the right cache. Spring Boot Micrometer metrics may require additional dependencies/binders and observability config; do not infer from recordStats that dashboards appear automatically.

### Mistake 11: Confusing Caffeine Local Cache with Distributed Cache

Caffeine caches are typically **local memory per JVM**. If there are two application instances, each instance has its own cache entries, TTLs, and stats. Builders/specs do not emit cross-node invalidation events. If data must remain consistent on updates across multiple nodes, design events, versioning, or use a suitable shared cache store.

### Mistake 12: Putting refreshAfterWrite in a Spec Without Considering the Loader

**refreshAfterWrite** is a loading-cache refresh policy, not just a regular TTL. You must determine how the loader is supplied and understand refresh semantics. Do not treat **refreshAfterWrite=1m** as a command to automatically reload every entry in a cache without a loading mechanism.

### Mistake 13: Configuring allowNullValues Mismatched with Business Values

Native Caffeine caches do not store **Java null values** the way an ordinary map might. Spring's CaffeineCacheManager can use an adapter to allow **cached-null** via the **setAllowNullValues** policy; in our demo we **chose false** to keep the contract simple. If a @Cacheable method returns null while the manager disallows it, a cache put error may occur. Set the policy based on your domain and test with the provider; do not confuse absence with cached-null.

## 11. Choosing a Production Configuration

Before choosing builder or spec, determine:
1. How stale can data be? Choose appropriate expireAfterWrite/Access and an invalidation mechanism on updates.
2. What is the maximum number of keys per region? Set maximumSize/Weight based on load and memory.
3. Is reloading on miss or background refresh needed? Caffeine CacheLoader/AsyncCacheLoader can affect how Spring Cache accesses the cache.
4. Are removalListener, weigher, or custom Expiry needed? If yes, usually choose the **builder**.
5. Do you want Dev/Staging/Prod to use different policies without code changes? A **spec property** is convenient.
6. How many caches have different TTLs? Use multiple managers/custom caches rather than blindly applying one setting to every cache.
7. Do you need to measure hit rate/eviction? Enable recordStats and configure appropriate observability.
8. Do multiple instances need synchronized invalidation? Local Caffeine cache does not handle this by itself.
9. Is memory protection needed? Caffeine does not necessarily have a default maximumSize; set explicit bounds.
10. Will changing configuration in production cause cold caches, stampedes, or memory spikes? Prepare monitoring and rollback plans.
11. Is a CaffeineSpec property set alongside a builder bean or custom manager anywhere? Verify **which configuration actually takes effect**.
12. Test on the exact provider and JDK version rather than copying snippets from another version.

An example choosing **spec** when only basic policies are needed:

~~~properties
spring.cache.caffeine.spec=maximumSize=2000,expireAfterWrite=15m,recordStats
~~~

An example choosing **builder** when the policy needs Java callbacks:

~~~java
Caffeine.newBuilder()
    .maximumSize(2000)
    .expireAfterWrite(Duration.ofMinutes(15))
    .recordStats()
    .removalListener((key, value, cause) -> {
        // Safe logging/metrics or cleanup; the listener should be designed
        // so it does not block the cache path.
    });
~~~

**Warning:** The listener snippet is illustrative and needs proper imports and type context. Listeners often run under the provider's concurrency conditions; code inside a listener must not block for long, create re-entrant cache call cycles, or expose sensitive data.

## 12. Self-Check Questions

**1.** In Spring Cache with Caffeine, you want to limit to 500 entries and expire 10 minutes after write. Which two approaches can you use?

**Answer:** Builder **Caffeine.newBuilder().maximumSize(500).expireAfterWrite(Duration.ofMinutes(10))** or spec **maximumSize=500,expireAfterWrite=10m**, passed to CaffeineCacheManager via the corresponding API.

**2.** Does setting **initialCapacity(500)** limit the cache to only 500 entries?

**No.** That is an initial capacity hint and does not replace **maximumSize(500)**.

**3.** Can **removalListener** be set using a standard CaffeineSpec string?

**No.** CaffeineSpec only supports a defined set of text options; callbacks/lambdas must be configured via the builder.

**4.** Can you combine **maximumSize=100,maximumWeight=1000** in a spec?

**No.** These two bounds are mutually exclusive.

**5.** If Spring Boot already has **spring.cache.caffeine.spec**, and the app also defines a Caffeine builder bean, which source generally takes precedence in auto-configuration?

**The spec property** is evaluated before a CaffeineSpec bean and a Caffeine builder bean, according to Spring Boot documentation.

**6.** Does @Cacheable(cacheNames="products") automatically apply a TTL from the Java class?

**No.** TTL is supplied by the selected CaffeineCacheManager/native cache. If the manager has no TTL, @Cacheable does not establish one on its own.

**7.** With CaffeineCacheManager configured with static cacheNames=["products"], what does getCache("product") return?

**Typically null** when "product" is not in the list and not separately registered.

**8.** Do two cache names on one CaffeineCacheManager share a combined total of maximumSize=1000?

**No.** They are two separate native cache regions; each region receives the manager's shared configuration.

**9.** Why does the Maven program need spring-context-support?

Because Spring's **CaffeineCacheManager** is provided by the **spring-context-support** module. The native Caffeine artifact is a separate dependency.

**10.** When calling setCacheSpecification after setCaffeine, are the two configurations automatically merged?

**Do not assume so.** Both configure the common cache policy; choose one complete source and test the resulting policy.

**11.** Does using expireAfterAccess=10m for a continuously read key guarantee it expires 10 minutes after the last write?

**No.** Accesses can extend its lifetime, unlike expireAfterWrite.

**12.** Does recordStats automatically create a production dashboard?

**No.** It instructs Caffeine to collect statistics; exporting metrics to an observability system requires additional integration (e.g., via Actuator/Micrometer in Spring Boot when configured).

## Conclusion

- **Builder** is the strong choice when you need Java callbacks, custom Expiry/Weigher/Listener, and programmatic policy control.
- **CaffeineSpec or specification string** suits configuring **maximumSize, expiry, recordStats** via properties/YAML and changing across environments.
- In **plain Spring Framework**, use **CaffeineCacheManager.setCaffeine(builder)** or **setCaffeineSpec(spec)** / **setCacheSpecification(string)**; do not assume these sources merge automatically.
- In **Spring Boot auto-configuration**, understand the selection order **spring.cache.caffeine.spec → CaffeineSpec bean → Caffeine builder bean** and that declaring your own CacheManager may alter the configuration branch.
- Whichever style you choose, keep **cacheName/key** consistent, configure **maximumSize/TTL** intentionally, verify the actual policy on the native Caffeine cache, and measure behavior through **@Cacheable** on proxy beans.

### Official Documentation

- Spring Framework 6.2 – CaffeineCacheManager Javadoc, setters and registerCustomCache: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/caffeine/CaffeineCacheManager.html
- Spring Framework 6.2 – CaffeineCache Javadoc and getNativeCache: https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/cache/caffeine/CaffeineCache.html
- Spring Framework – Annotation-driven caching: https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html
- Caffeine Wiki – Specification string: https://github.com/ben-manes/caffeine/wiki/Specification
- Caffeine Wiki – Eviction (size, time, and reference policies): https://github.com/ben-manes/caffeine/wiki/Eviction
- Spring Boot Reference – Caffeine configuration and customization source ordering: https://docs.spring.io/spring-boot/reference/io/caching.html
- Maven Central – caffeine artifact: https://central.sonatype.com/artifact/com.github.ben-manes.caffeine/caffeine/3.2.4