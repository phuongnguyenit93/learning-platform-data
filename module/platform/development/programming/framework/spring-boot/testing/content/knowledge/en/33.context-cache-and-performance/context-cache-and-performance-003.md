# Observing Cache Hits, Misses, and Actual Contexts Created

## 1. The problem: why does a Spring Boot test suite start up slowly?

In the **Context cache and performance** section of Spring Boot testing, a common challenge is having a test suite with hundreds of JUnit methods, yet on each run multiple "Starting ..." lines appear, multiple database pools initialize, or containers and embedded servers get recreated. Learners often confuse the **number of test methods** with the **number of ApplicationContexts** created.

The Spring TestContext Framework includes an **ApplicationContext cache** that reuses Spring contexts across tests with **equivalent configuration**. When test A and test B share the same configuration according to the cache key, Spring can keep context A after it starts and let test B use that exact context object instead of bootstrapping all beans again.

However, several situations cause cache misses:

- Tests have different `@SpringBootTest(properties=...)`.
- Profiles or `@TestPropertySource` differ.
- Different classes use different sets of `@MockBean`/`@SpyBean` in Spring Boot 3.3.
- `@DynamicPropertySource` methods or other context customizers differ.
- A test marks `@DirtiesContext`, removing the context from the cache.
- The suite creates more contexts than the LRU cache can hold, leading to eviction and reloading.
- Gradle/Maven launches multiple JVM processes: the cache in one JVM cannot be used by another JVM.

**Goal of this lesson:** learn how to observe **cache hits**, **cache misses**, **the number of contexts currently cached**, **the number of times a new context is actually created**, and why those numbers can differ. You must interpret metrics/logs accurately rather than saying "20 misses means 20 distinct context configurations" or "200 tests means 200 contexts".

The example uses **Java 17, Spring Boot 3.3.0, Spring Framework 6.1, JUnit Jupiter, and Gradle**. It provides a runnable project where `TestContextManager` creates fixture contexts with matching/differing cache keys, a bean tracks initialization count, and dirty marking verifies context reloading. The test numbers described are **expected outcomes**, not a report of Gradle having been executed on your machine.

## 2. Learning outcomes

After this lesson, you will be able to:

1. Distinguish Spring TestContext's **ApplicationContext cache** from `@Cacheable` business caches, Hibernate 2nd-level cache, and Gradle build cache.
2. Explain why Spring can share one `ApplicationContext` across multiple JUnit methods/classes.
3. Read DEBUG logs from `org.springframework.test.context.cache`.
4. Interpret `hitCount`, `missCount`, `size`, `maxSize`, `parentContextCount`, and `failureCount` when present.
5. Understand that the cache key is based on **`MergedContextConfiguration`**, not simply the class name.
6. Distinguish **cache hit request count** from **first-time context creation count**.
7. Distinguish `missCount` from the **number of unique cache keys**, due to eviction and reloading.
8. Know the default cache max size is **32 contexts**, LRU eviction, and configuring `spring.test.context.cache.maxSize`.
9. Know the cache is held in **static state within the same JVM process**; separate forks do not share it.
10. Know that `@DirtiesContext` evicts/closes a context and the next lookup must reload it.
11. Understand why putting `@DirtiesContext` on every test destroys caching benefits.
12. Know that `@MockBean`/`@SpyBean` in Spring Boot 3.3 contribute to changes in the context cache key.
13. Know that `@ActiveProfiles`, inline properties, and `@TestPropertySource` change the key.
14. Understand that `@DynamicPropertySource` typically participates in the key via the **method defining dynamic properties**, not arbitrarily by the value returned by each supplier call.
15. Create a `ContextMarker` bean with a static sequence counter to observe **each time the bean is created in a new context**.
16. Verify that two fixture classes with identical configuration use the **same ApplicationContext instance**.
17. Verify that a different inline property or active profile produces a **different context identity**.
18. Verify that dirtying a context causes it to reload and increments the marker sequence.
19. Understand the limitations of a marker counter: it does not count contexts without the marker or loads that fail before bean creation.
20. Avoid using internal/private cache APIs or reflection to force hit/miss counters in ordinary business tests.
21. Know how to keep tests independent when sharing singleton beans with mutable state.
22. Understand the pros/cons of test slices (`@WebMvcTest`, `@DataJpaTest`) vs. full `@SpringBootTest`.
23. Know where context cache statistics come from and when a log line is only a cumulative snapshot.
24. Understand how Spring 6.1 context failure threshold differs from cache misses/hits.
25. Propose measuring startup overhead via test logs, Gradle test results, and a real profiler rather than fabricating latency numbers.
26. Build a QA checklist for performance, reproducibility, and reliability of Spring tests.

## 3. Nature of the Spring TestContext context cache

```text
JUnit test runner (same JVM)
        |
        v
Spring TestContext Framework
        |
        +-- MergedContextConfiguration -> cache key
        |
        +-- Lookup static ContextCache
               |
               +-- HIT: key exists
               |       return cached ApplicationContext
               |       reuse bean graph / data sources / services
               |
               +-- MISS: key absent
                       load/refresh ApplicationContext
                       cache it under key
                       return to test
        |
        v
Test method uses injected Spring beans
```

The Spring cache holds the previously initialized **ApplicationContext** object, not just a list of bean definitions. Therefore, a cache hit avoids expensive work: component scanning, condition evaluation, bean creation, datasource initialization, connection pooling, embedded server startup, and so on.

However, reusing a context also means that singleton beans, `Environment`, datasources, caches, schedulers, and resources in that context persist across tests. **Reusing a context is not automatic data reset.** Tests must still clean up databases, queues, caches, and business state at the appropriate boundary.

### 3.1. Context cache is not @Cacheable

| Cache | Who operates it? | What does it store? | Goal |
| --- | --- | --- | --- |
| Spring TestContext cache | Spring `spring-test` | `ApplicationContext` objects | Avoid repeated startup |
| Spring Cache `@Cacheable` | Application cache abstraction | Business method results | Reduce processing load |
| Hibernate 1st-level cache | Persistence context | Managed entities | ORM unit-of-work |
| Hibernate 2nd-level cache | ORM cache provider | Entity/query data | Reduce DB reads |
| Gradle build cache | Build system | Compilation/task outputs | Avoid rebuilding |
| Docker image cache | Container runtime | Image layers | Reduce pull/build time |

A `ContextCache hitCount=...` log **does not** mean the application's Redis had a cache hit. Conversely, `@Cacheable` working properly does not guarantee the Spring test context is being reused.

### 3.2. When lookups happen

Spring can look up the context multiple times while preparing the test instance, performing dependency injection, running test lifecycle callbacks, or accessing `TestContext.getApplicationContext()`. Therefore, one JUnit method **does not correspond to exactly one lookup**.

Do not take `hitCount` and subtract total `@Test` methods to compute "number of cached tests". It is a **counter of cache accesses**, not a metric with a one-to-one mapping to tests.

## 4. What makes up the cache key?

Spring determines the cache key from a `MergedContextConfiguration` which can include:

- `locations` and `classes` in `@ContextConfiguration`.
- `contextInitializerClasses`.
- `contextCustomizers`: including Spring Boot test support customizers; `@DynamicPropertySource` methods, `@MockBean`/`@SpyBean` in Boot 3.3, and other test customizers.
- `contextLoader`.
- `parent` in a context hierarchy.
- `activeProfiles` from `@ActiveProfiles`.
- `propertySourceDescriptors`/property source locations in `@TestPropertySource`.
- `propertySourceProperties`, including inline properties from test configuration.
- `resourceBasePath` for web context configuration.

Exact details belong to the Spring Framework version; do not assume this list is an ordered JSON cache key. What matters is that **two tests that "look nearly identical" can still produce two keys** if any component of the configuration differs.

### 4.1. Same test configuration -> reuse

Two fixture classes:

```java
@SpringBootTest(
    classes = CacheStudyApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "study.mode=shared")
class A {}

@SpringBootTest(
    classes = CacheStudyApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "study.mode=shared")
class B {}
```

This is a conceptual example (`CacheStudyApplication` does not belong to the runnable project). If the other cache key components are equivalent and contexts have not been evicted/dirtied, A and B can reuse the same context. **Different test class names alone do not force different contexts** when merged configurations are equivalent.

### 4.2. Different property -> different key

```java
@SpringBootTest(properties = "feature.demo=enabled")
class FeatureOnTest {}

@SpringBootTest(properties = "feature.demo=disabled")
class FeatureOffTest {}
```

Different inline properties mean different merged configurations; sharing the same Spring main class is not enough for a cache hit. Similarly, `@ActiveProfiles("test")` and `@ActiveProfiles("integration")` normally produce two keys.

### 4.3. @MockBean fragments the context key

In Spring Boot **3.3**, `@MockBean`/`@SpyBean` create context customizers matching the mock definitions:

```java
@SpringBootTest
class FirstTest {
    @MockBean PaymentClient paymentClient;
}

@SpringBootTest
class SecondTest {
    @MockBean InventoryClient inventoryClient;
}
```

This is an illustrative snippet requiring mock target classes and imports. Two different mock sets usually result in different cache keys, even if the larger service graph is identical. When hundreds of tests each mock a separate set, context fragmentation becomes significant.

**Version note:** Spring Boot 3.4 deprecates `@MockBean` in favor of Spring Framework's `@MockitoBean`; this learning project pins Boot 3.3, so do not mix in imports from newer versions.

### 4.4. @DynamicPropertySource

A `@DynamicPropertySource` method normally participates in the cache key through a `ContextCustomizer` representing that method. **The value returned at runtime by the supplier does not automatically become a separate cache key element on each read.** This is especially risky with Testcontainers:

```java
@DynamicPropertySource
static void datasource(DynamicPropertyRegistry registry) {
    registry.add("service.url", container::getUrl);
}
```

This is a snippet requiring `container` to be defined. If two test classes share/inherit the same dynamic property method while actually using two container instances with changing hosts/ports, Spring can reuse the context holding a connection to the old container. The fix is to align container lifecycle with context lifecycle, or use `@DirtiesContext` intentionally when the external resource actually differs.

### 4.5. Test slices create different keys

`@WebMvcTest`, `@DataJpaTest`, `@JsonTest`, and `@SpringBootTest` load different scopes/auto-configs. Do not expect slices to share the same cache key; even two `@WebMvcTest` classes with different controllers/imports/mocks can produce different keys.

## 5. Hits, misses, and context count: reading them accurately

| Metric | How to interpret | How NOT to interpret |
| --- | --- | --- |
| `hitCount` | Number of cache lookups that found a context by key | Number of tests executed successfully |
| `missCount` | Number of lookups with no matching cached context | Permanent number of distinct configurations |
| `size` | Number of contexts currently held in the cache | Total contexts ever created |
| `maxSize` | Maximum entry limit of the cache | Total contexts allowed across the whole suite |
| `parentContextCount` | Info on cached parent contexts in hierarchies | Number of parent test classes |
| `failureCount` | Metric related to load failures if displayed | Number of failed assertions/JUnit tests |

### 5.1. One key loaded, reused many times

```text
Lookup key "A" -> MISS -> create Context#1
Lookup key "A" -> HIT  -> reuse Context#1
Lookup key "A" -> HIT  -> reuse Context#1
Lookup key "A" -> HIT  -> reuse Context#1

Requests:      4
Misses:        1
Hits:          3
Contexts made: 1
Current size:  1
```

These numbers are a simplified model with exactly four lookups; in practice Spring TestContext may perform additional internal lookups.

### 5.2. LRU eviction and reload

```text
maxSize = 2 (illustrative example, not default)

Lookup A -> MISS -> create A#1
Lookup B -> MISS -> create B#1
Lookup C -> MISS -> create C#1
           evict least-recently-used A#1

Lookup A -> MISS -> create A#2
           evict another older entry

Distinct cache keys observed: 3 (A,B,C)
Context instances created:   4
Misses in this simple trace:  4
Current cache size:           2
```

**Core point:** even with only three distinct configurations, key A is reloaded after eviction. Therefore `missCount` is not `uniqueDistinctContextCount`, and `size` is not the total initialized.

### 5.3. @DirtiesContext causes the same key to miss again

```text
Load A -> create A#1
Mark A dirty -> remove/close A#1
Load A again -> create A#2
```

Same key, yet two context instances. The creation count increases even without adding another test profile or property.

### 5.4. A load failure is not a successful context creation

A context load can fail due to bean creation, a bad property, missing Kafka/DB, or an unstarted test container. Cache lookup misses can increase even though the context never refreshed successfully. Spring Framework 6.1 includes a **context failure threshold** (default 1 per key) to fail fast on subsequent load attempts. Do not look at `missCount` and claim that many contexts ran successfully.

## 6. Default 32 contexts and LRU policy

The Spring TestContext cache uses a **bounded static cache** per JVM, with a default **maximum size of 32**. When the limit is exceeded, it evicts and closes the least recently used contexts via **LRU**.

Configurable via JVM system property:

```text
-Dspring.test.context.cache.maxSize=64
```

Set from a Gradle test task:

```groovy
tasks.named('test') {
    useJUnitPlatform()
    systemProperty 'spring.test.context.cache.maxSize', '64'
}
```

Or via the appropriate Maven Surefire/Failsafe JVM config; do not put `spring.test.context.cache.maxSize=64` in `application.properties` and assume the JVM system property was set early enough. Documentation allows the `SpringProperties` mechanism, but configuring the test JVM process is the clear path.

### 6.1. Do not automatically crank maxSize very high

Benefit: reduces eviction/reloads when there are many distinct keys.

Trade-off: retains more beans, datasources, Hikari pools, executor threads, network clients, embedded servers, and native memory simultaneously. The JVM may hit heap pressure, port pressure, or memory thrashing. Measure **distinct key count + heap/off-heap/process resources** before increasing it.

### 6.2. Cache is static per JVM, not shared across forks

The TestContext cache lives in static variables. When a build tool spawns **forked JVM processes**, each JVM has an independent cache. The same test class with identical configuration running in two processes will still bootstrap two contexts (one per process).

Options to check:

- Gradle `maxParallelForks` > 1 spawns multiple test workers.
- Gradle `forkEvery` > 0 recycles workers after every N classes.
- Maven Surefire/Failsafe `forkCount` and `reuseForks`.
- The IDE may run each configuration in a separate process.
- CI sharding splits the test suite across different machines/containers.

Do not blame Spring cache misses when build process boundaries actually broke reuse.

## 7. Reading DEBUG cache statistics from logs

Enable the log level:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

When using Spring Boot tests and Logback, this can be placed in `src/test/resources/application.properties`. Because cache logging can happen early during bootstrap, you may need to configure the logger via early-activated logging config or JVM/test logging configuration depending on the project. This log level is only for debugging the test suite; do not enable it in production.

An **illustrative** log sample:

```text
Spring test ApplicationContext cache statistics:
[DefaultContextCache@... size = 3, maxSize = 32,
 parentContextCount = 0, hitCount = 18,
 missCount = 3, failureCount = 0]
```

Exact format/order/fields can vary by Spring Framework version. You must read **actual data from your test logs**, not treat 18/3/3 in the example as your run's output.

### 7.1. Cumulative snapshots, not per-method deltas

Cache stats accumulate within the same JVM. A log after test class B includes lookups from test A. Repeated DEBUG lines occur because of multiple accesses; do not sum `hitCount` across lines as incremental deltas — the numbers are already cumulative snapshots.

### 7.2. How to analyze when total method count is known

Suppose a suite has 500 methods, and the final cache log reports 1,600 hits, 12 misses, size 10:

- What is certain: many cache lookups reused contexts; only 10 entries are currently retained; 12 lookups missed.
- You cannot conclude "exactly 488 tests hit the cache".
- You cannot claim there are exactly 12 distinct context configs, because reloads/evictions or failed loads may have occurred.
- To know the actual number of instances created, add another measurement source: startup logs with context identity, a marker bean, controlled diagnostics, or traced load events.

### 7.3. Context cache entries can have parents

With `@ContextHierarchy`, parent contexts and child contexts have special relationships during eviction/dirtying; `parentContextCount` is not a count of parent test classes. When analyzing size/misses, understand hierarchy mode and do not casually mark a child dirty with `EXHAUSTIVE` unless parent/siblings should be affected.

## 8. Counting actual created contexts with a marker bean

To observe a context **actually initializing its bean graph**, we use a singleton `ContextMarker` bean whose factory method increments a static `AtomicInteger`:

```java
private static final AtomicInteger CREATED =
        new AtomicInteger();

@Bean
ContextMarker contextMarker() {
    return new ContextMarker(
            CREATED.incrementAndGet());
}
```

In the demo, `ContextMarker` is an eager singleton bean. Every **successful ApplicationContext refresh** containing that bean creates one marker instance; a reused cached context does not create a new marker.

**Important limitations:**

- The counter only counts contexts **containing the marker** that reached bean creation, not every context type across an entire company.
- If bootstrap fails before the marker bean, the counter does not increment even though a cache miss/load attempt happened.
- With parallel contexts, a static counter reflects the JVM total; order-sensitive assertions must be synchronized/isolated.
- Static counters reset when a new JVM process starts; do not directly combine counters across multiple forks.
- Do not add a test marker bean into production code solely to measure a test suite; use `@TestConfiguration`/dedicated fixtures when needed.

### 8.1. Instance identity vs. Context.getId()

`ApplicationContext.getId()` is typically a diagnostic ID name, not guaranteed to be permanently unique across refreshes/recreations. `System.identityHashCode(context)` can also theoretically collide. To test reuse, use `assertSame(a,b)` and `assertNotSame(a,c)` on Java object references. The marker sequence tells you how many times the bean factory ran in the process.

### 8.2. Do not count contexts using @BeforeAll alone

`@BeforeAll` is called per JUnit test class, not per context startup. One context can serve 20 test classes (20 `BeforeAll` callbacks but one context). Thus the counter must be attached to **bean creation/context refresh**, not to a test lifecycle method.

## 9. Runnable Java 17 + Spring Boot 3.3 project

### 9.1. Directory tree

```text
context-cache-observer/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/contextcache/
    │   └── ContextCacheProbeApplication.java
    └── test/
        ├── java/example/contextcache/
        │   └── ContextCacheBehaviorTest.java
        └── resources/
            └── application.properties
```

The project has just one main class holding a singleton marker bean and one test class using nested configuration fixtures. There is no database, Docker, or HTTP server, making each context startup easy to observe. `TestContextManager` is intentionally used as a **diagnostic harness** to create multiple test contexts sequentially within one JUnit method; normal application tests still use `@SpringBootTest` directly.

### 9.2. settings.gradle

```groovy
rootProject.name = 'context-cache-observer'
```

### 9.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
    // One worker JVM to make cache reuse directly observable.
    maxParallelForks = 1
    forkEvery = 0
}
```

Here there is only **one Gradle test worker process**. To experiment with forks, change `maxParallelForks` or `forkEvery` in a sandbox branch and compare process-level logs; do not enable multiple forks in a test that asserts same-JVM sharing.

### 9.4. Test logging: src/test/resources/application.properties

```properties
spring.main.banner-mode=off
logging.level.org.springframework.test.context.cache=DEBUG
```

This is test-only logging config. If your environment/IDE does not show cache debug logs, inspect the test runtime logger configuration or `logback-test.xml`/Gradle logging system; do not conclude the Spring cache is inactive just because the console filters DEBUG.

## 10. ContextCacheProbeApplication.java

**src/main/java/example/contextcache/ContextCacheProbeApplication.java**

```java
package example.contextcache;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class ContextCacheProbeApplication {

    private static final AtomicInteger MARKER_CREATIONS =
            new AtomicInteger();

    public static void main(String[] args) {
        SpringApplication.run(
                ContextCacheProbeApplication.class, args);
    }

    @Bean
    public ContextMarker contextMarker() {
        return new ContextMarker(
                MARKER_CREATIONS.incrementAndGet());
    }

    public static int markerCreations() {
        return MARKER_CREATIONS.get();
    }

    public record ContextMarker(int sequence) {}
}
```

### 10.1. When is the marker created?

`@Bean` creates a non-lazy singleton by default. In the demo app, each time a new ApplicationContext refreshes and instantiates beans, `contextMarker()` calls `incrementAndGet()` once.

When test B reuses test A's exact context, the bean already lives in context A, so Spring does not recreate it and the counter does not increase. When a context is dirtied/evicted and reloaded, a new `ContextMarker` gets the next sequence number.

### 10.2. Marker is a diagnostic tool, not a public business API

Static `MARKER_CREATIONS` is intentionally used to count **instances within one JVM**. In reality, many test contexts might omit the marker or fail to load. In production, do not store mutable user data in static fields to assess context reuse.

## 11. ContextCacheBehaviorTest.java — 5 JUnit tests

**src/test/java/example/contextcache/ContextCacheBehaviorTest.java**

```java
package example.contextcache;

import java.util.Arrays;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.annotation.DirtiesContext.HierarchyMode;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestContextManager;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNotSame;
import static org.junit.jupiter.api.Assertions.assertSame;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Execution(ExecutionMode.SAME_THREAD)
class ContextCacheBehaviorTest {

    @SpringBootTest(
            classes = ContextCacheProbeApplication.class,
            webEnvironment = SpringBootTest.WebEnvironment.NONE,
            properties = "cache.study.variant=shared"
    )
    static class SharedA {}

    @SpringBootTest(
            classes = ContextCacheProbeApplication.class,
            webEnvironment = SpringBootTest.WebEnvironment.NONE,
            properties = "cache.study.variant=shared"
    )
    static class SharedB {}

    @SpringBootTest(
            classes = ContextCacheProbeApplication.class,
            webEnvironment = SpringBootTest.WebEnvironment.NONE,
            properties = "cache.study.variant=different"
    )
    static class DifferentProperty {}

    @SpringBootTest(
            classes = ContextCacheProbeApplication.class,
            webEnvironment = SpringBootTest.WebEnvironment.NONE,
            properties = "cache.study.variant=shared"
    )
    @ActiveProfiles("scenario")
    static class DifferentProfile {}

    @SpringBootTest(
            classes = ContextCacheProbeApplication.class,
            webEnvironment = SpringBootTest.WebEnvironment.NONE,
            properties = "cache.study.variant=dirty-demo"
    )
    static class DirtyFixture {}

    private static TestContextManager manager(
            Class<?> fixtureClass) {
        return new TestContextManager(fixtureClass);
    }

    private static ApplicationContext contextFor(
            Class<?> fixtureClass) {
        return manager(fixtureClass)
                .getTestContext()
                .getApplicationContext();
    }

    private static int markerOf(ApplicationContext ctx) {
        return ctx.getBean(
                ContextCacheProbeApplication.ContextMarker.class)
                .sequence();
    }

    @Test
    void equivalentFixtureKeysReuseSameContext() {
        ApplicationContext first = contextFor(SharedA.class);
        int markersAfterFirst =
                ContextCacheProbeApplication.markerCreations();

        ApplicationContext second = contextFor(SharedB.class);

        assertSame(first, second);
        assertEquals(markerOf(first), markerOf(second));

        assertEquals(
                markersAfterFirst,
                ContextCacheProbeApplication.markerCreations());
    }

    @Test
    void repeatedLookupDoesNotRecreateBeanGraph() {
        ApplicationContext first = contextFor(SharedA.class);
        int beforeRepeats =
                ContextCacheProbeApplication.markerCreations();

        ApplicationContext second = contextFor(SharedA.class);
        ApplicationContext third = contextFor(SharedA.class);

        assertSame(first, second);
        assertSame(first, third);
        assertEquals(
                beforeRepeats,
                ContextCacheProbeApplication.markerCreations());
    }

    @Test
    void changingInlinePropertyCreatesDifferentContext() {
        ApplicationContext shared = contextFor(SharedA.class);
        ApplicationContext other =
                contextFor(DifferentProperty.class);

        assertNotSame(shared, other);
        assertNotEquals(markerOf(shared), markerOf(other));

        assertEquals(
                "shared",
                shared.getEnvironment()
                        .getProperty("cache.study.variant"));
        assertEquals(
                "different",
                other.getEnvironment()
                        .getProperty("cache.study.variant"));
    }

    @Test
    void activeProfileContributesToCacheKey() {
        ApplicationContext base = contextFor(SharedA.class);
        ApplicationContext profiled =
                contextFor(DifferentProfile.class);

        assertNotSame(base, profiled);
        assertNotEquals(markerOf(base), markerOf(profiled));
        assertTrue(
                Arrays.asList(
                        profiled.getEnvironment()
                                .getActiveProfiles())
                        .contains("scenario"));
    }

    @Test
    void dirtyContextIsRemovedAndNextLookupReloads() {
        TestContextManager firstManager =
                manager(DirtyFixture.class);

        ApplicationContext oldContext =
                firstManager.getTestContext()
                        .getApplicationContext();

        int oldMarker = markerOf(oldContext);
        int createdAfterOld =
                ContextCacheProbeApplication.markerCreations();

        firstManager.getTestContext()
                .markApplicationContextDirty(
                        HierarchyMode.EXHAUSTIVE);

        ApplicationContext newContext =
                contextFor(DirtyFixture.class);

        assertNotSame(oldContext, newContext);
        assertNotEquals(oldMarker, markerOf(newContext));

        assertEquals(
                createdAfterOld + 1,
                ContextCacheProbeApplication.markerCreations());
    }
}
```

**5 JUnit methods** in one class, with nested classes acting as **fixture cache keys**, not five independent JUnit test classes. The public `TestContextManager` API is used to build a `TestContext` with `@SpringBootTest`'s bootstrap metadata and then call `getApplicationContext()`; this is a cache instrumentation probe. In real applications, JUnit Jupiter + `SpringExtension` normally manage `TestContextManager` automatically.

### 11.1. Same key on two fixture classes

`SharedA` and `SharedB` have the same app, web environment, inline property, and no other customizers. The test asserts:

- `assertSame(first,second)`: **exact same Java ApplicationContext object**.
- `markerOf(first)==markerOf(second)`: same singleton marker.
- Total marker creations stay unchanged after looking up `SharedB`: **no new bean graph built**.

Different fixture class names do not alter the key when the merged configuration is equivalent.

### 11.2. Repeated lookups may increment hitCount without incrementing marker

In `repeatedLookupDoesNotRecreateBeanGraph`, we access the same fixture key three times. Each subsequent lookup may be recorded in hit stats, yet it remains a single context instance. The test does not assert "hitCount increased by exactly 2" because Spring can perform extra accesses during bootstrap; object identity is stronger evidence.

### 11.3. Different property creates different identity

`DifferentProperty` has `cache.study.variant=different`, so its context key differs from `SharedA`. It must create/hold a separate context and a different marker sequence. The test also queries `Environment` to verify the property was actually applied rather than guessing from the annotation.

### 11.4. Active profile also alters the cache key

`DifferentProfile` uses the same inline property as `SharedA` but has `@ActiveProfiles("scenario")`. The different profile contributes to a different merged key. Hence a suite with many classes enabling different profiles can spawn many contexts.

### 11.5. Controlled @DirtiesContext behavior

In `dirtyContextIsRemovedAndNextLookupReloads`:

1. Load context key `DirtyFixture`, recording the marker id and counter.
2. Call `TestContext.markApplicationContextDirty(HierarchyMode.EXHAUSTIVE)` on that exact context.
3. Spring removes/closes the context from the TestContext cache.
4. Load the same key again, receiving a **different context object** and a **different marker id**.
5. In a project with a single sequential test class, the counter increases by one.

Using `TestContext`'s public method is an **intentional diagnostic test** technique to demonstrate eviction; regular application code should use the `@DirtiesContext` annotation when dirtying is needed, rather than calling this method in every test to unconditionally "get a new context".

### 11.6. Tests do not depend on JUnit method order

Each `@Test` asserts identity directly at the time it calls the fixture, without assuming whether an earlier test loaded it or not. Meanwhile, the dirty fixture uses an independent cache key so it never evicts `SharedA`/`DifferentProperty`. `@Execution(SAME_THREAD)` combined with the one-worker Gradle setup prevents parallel modifications in the lab.

**Limitation:** If another suite runs **concurrently in the same JVM** and also loads contexts containing the marker, the global marker counter can increase independently of the dirty test. This lab has only one test class; in a real suite, do not assert absolute global totals under parallel execution—use per-key marker identities or an isolated suite instead.

## 12. Running the project and reading results accurately

Requires JDK 17, a compatible Gradle wrapper (e.g., Gradle 8.7), and Maven Central/repository cache:

Linux/macOS:

```bash
./gradlew test
./gradlew test --tests example.contextcache.ContextCacheBehaviorTest
```

Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.contextcache.ContextCacheBehaviorTest
```

If there is no wrapper yet, generate one with a compatible Gradle version and keep the wrapper files. Do not fabricate "BUILD SUCCESSFUL" stdout if you have not run it.

| Test | Expected |
| --- | --- |
| `equivalentFixtureKeysReuseSameContext` | Same context object and marker |
| `repeatedLookupDoesNotRecreateBeanGraph` | Repeated lookup does not create a marker |
| `changingInlinePropertyCreatesDifferentContext` | Different context, different property |
| `activeProfileContributesToCacheKey` | Different context when profile is enabled |
| `dirtyContextIsRemovedAndNextLookupReloads` | Dirty -> new context, marker increments |

**Expected result:** 5 JUnit methods pass on Boot 3.3 + Spring 6.1 if code is placed in the right packages/files and no other suite competes for the same marker. This is not an actual executed Gradle measurement. Real `hitCount`/`missCount`/`size` values must be read from the run's DEBUG log, because the framework may access the cache more than once per method.

### 12.1. Can we count "5 contexts"?

Configurationally, the demo's fixture keys include shared, different-property, different-profile, and dirty-demo. The dirty key is loaded twice. Conceptually, running in a clean JVM with nothing else loading them creates **5 context instances**: shared 1, different-property 1, different-profile 1, dirty-demo 2.

However, this is only the **expected model of the standalone program**, not a guarantee that the final DEBUG `missCount` will equal 5 or that JUnit ran all 5. Moreover, test discovery, context loading order, and launcher configuration can change when the suite grows.

### 12.2. If you see the same config yet still get a miss

Check exact versions, equality of the full merged context configuration, context eviction, `@DirtiesContext`, whether the TestContext static cache is in the same JVM, and whether Spring Boot mock definitions/profiles/customizers differ. Do not automatically assume it is a Spring TestContext bug.

## 13. What is TestContextManager and why use it?

`TestContextManager` is the entry point of the Spring TestContext Framework, responsible for managing `TestContext` and invoking registered `TestExecutionListener`s at lifecycle callbacks.

In JUnit 5 with `@SpringBootTest`, `SpringExtension` integrates `TestContextManager` automatically. In this lab, we instantiate it manually:

```java
TestContextManager manager =
        new TestContextManager(SharedA.class);

ApplicationContext ctx =
        manager.getTestContext()
                .getApplicationContext();
```

Reason: we want to check **multiple cache keys and context identities inside a single test method**, rather than relying on JUnit's class execution order or shared static maps collecting data across multiple tests.

**Do not use this pattern to bypass the test lifecycle in production test suites.** This probe intentionally asks only for context loading/cache semantics, skipping `prepareTestInstance`/`beforeTestMethod`/`afterTestMethod` for each fixture. If a fixture relies on a transactional test lifecycle, dependency injection into the test instance, custom `TestExecutionListener`s, or dirty annotations, use real `SpringExtension`/JUnit integration and measure at that boundary.

## 14. @DirtiesContext: when is it needed, when is it not?

`@DirtiesContext` informs Spring TestContext that a context is no longer safe to reuse—for instance, a test mutated a bean definition or shared singleton state that is hard to reset—and asks Spring to close/remove the entry.

Illustrative example:

```java
@SpringBootTest
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ChangesGlobalConfigurationTest {
    @Test
    void modifiesSingletonConfiguration() {
        // Test changes something that cannot be safely reset.
    }
}
```

This snippet requires appropriate imports and an app context; it is **not** a class inside the runnable lab. The annotation supports method/class modes such as `BEFORE_METHOD`, `AFTER_METHOD`, `BEFORE_CLASS`, `AFTER_CLASS`.

### 14.1. @DirtiesContext has a real cost

Marking dirty causes the context to be closed/removed. The next test with the same key must start up again, potentially reopening DB pools/embedded servers and rerunning bean initialization. Marking dirty after every method in a large suite nearly eliminates caching.

**Do not use `@DirtiesContext` as a default way to reset database state.** If only a few rows changed, use cleanup/truncate/transaction rollback/test fixtures. Only dirty the context when the context/bean graph itself was compromised and cannot be safely reset.

### 14.2. Transaction rollback is not context reset

A `@Transactional` test with rollback reverts database modifications within the test-managed transaction. It does **not** recreate the `ApplicationContext`, does not reset external resources/Redis/queues, and does not undo side effects outside the transaction.

Conversely, `@DirtiesContext` recreates the bean graph but does not automatically delete existing data in an external database or Redis. Choose the right tool for the right state.

### 14.3. @ContextHierarchy

When parent/child contexts exist, dirty hierarchy modes can affect parent/sibling children. `HierarchyMode.EXHAUSTIVE` has broad scope; `CURRENT_LEVEL` restricts to the current level per its contract. The lab has only one standalone context per key, so hierarchy interactions do not apply.

## 15. Counting actual created contexts in large projects

No single number can measure every scenario just by looking at test count. Use three sources of evidence:

### 15.1. Cache DEBUG stats

To observe:

- `size`: number of entries currently in the cache.
- `maxSize`: capacity.
- `hitCount`/`missCount`: access counters.
- `failureCount`: context load failures if any.

The official source is `org.springframework.test.context.cache` DEBUG. It is **not a per-test metric** and cannot directly tell you the number of **successful unique instances created** in every situation.

### 15.2. Bean/context marker

Add a test-only marker bean to the configurations under measurement and record how often its factory runs. When a context is reused, the marker ID stays the same. When a context reloads, the marker ID changes.

In a large suite, you can emit test-only logs:

```text
[context-probe] created marker=1 config=alpha
[context-probe] created marker=2 config=beta
[context-probe] created marker=3 config=dirty
[context-probe] created marker=4 config=dirty(reloaded)
```

This is an **illustration** for interpreting identity; the runnable lab does not print logs in this format, instead asserting markers in Java.

### 15.3. Startup logs and profiler

"Started Application in X seconds" lines or Boot startup metrics help reveal how a context bootstraps, but:

- Log lines may not appear if log levels are configured differently.
- Multiple `SpringApplication.run` calls may exist outside TestContext.
- There is not necessarily a single line per child/hierarchy context.
- Startup time depends on machine/CI, warmup, and file/network I/O.
- An app invoking `SpringApplication.run` manually does **not** benefit from the TestContext cache if it bypasses the TestContext loader.

Use timings to measure **real performance**, marker identity to measure **instance count**, and cache DEBUG to inspect **lookup behavior**.

## 16. Observing cache keys without relying on internals

You can use logging and test annotations to investigate differences, while avoiding reflection on `DefaultContextCache` static fields or invoking `clearStatistics()` across the suite in product tests.

A useful mapping table:

| Test class | Test annotation | Profiles | Properties | Mocks | Context group |
| --- | --- | --- | --- | --- | --- |
| OrderServiceTest | @SpringBootTest | test | mode=local | PaymentClient | Full-A |
| InvoiceServiceTest | @SpringBootTest | test | mode=local | PaymentClient | Full-A |
| CheckoutWebTest | @WebMvcTest | test | different | PaymentClient | Web-B |
| JsonSerializationTest | @JsonTest | test | different | None | Json-C |
| OrderJpaTest | @DataJpaTest | test | datasource H2 | None | Data-D |

This is an example classification table. Group "Full-A" is a reuse candidate when **all relevant key components** align; do not decide from 5 high-level columns alone if hidden customizers/parents/initializers exist.

### 16.1. Do not use contextCache internals as public test assertions

`DefaultCacheAwareContextLoaderDelegate`/`DefaultContextCache` have internal APIs/implementation details not recommended as product code contracts. Tests reading internal counters directly can break on Framework upgrades. Use DEBUG stats for measurement, `assertSame` to verify identity, and test-only markers to verify creation.

### 16.2. Do cache hits really improve startup?

In theory yes: they avoid refreshing the bean graph. But to quantify speed, measure actual test run times/startup profiles under the same workload and environment. Do not deduce "cache hit=1000 ⇒ 1000 seconds faster". Context size and startup cost vary widely across keys.

## 17. Spring Boot test slices and speed

Slices reduce bootstrap scope:

- `@WebMvcTest`: MVC controller/web slice, typically requiring mock dependencies.
- `@WebFluxTest`: reactive controller slice.
- `@DataJpaTest`: JPA persistence slice, typically rolling back transactions.
- `@JdbcTest`: JDBC slice.
- `@JsonTest`: JSON serialization slice.
- `@RestClientTest`: REST client slice.

A slice context is usually cheaper than the full application because fewer beans/auto-configurations load. However, if each test class uses a different set of controllers, mocks, or imports, it still creates many cache keys.

### 17.1. Do not mix multiple slices arbitrarily

Spring Boot does not support combining multiple `@...Test` slices as if adding two slices produces a single clean context. If full integration is needed, use `@SpringBootTest`; if a slice needs extra configuration, use `@Import` or auto-config imports intentionally.

### 17.2. Do not reduce context count by giving tests the wrong scope

Merging every class into one `@SpringBootTest` and mocking every service might raise reuse, yet hurts isolation and inflates startup footprint. Balance speed against fidelity; cache optimization must never break verification of security/persistence/serialization.

### 17.3. @MockBean per-method reset does not mean a new context

Boot 3.3 test mocks are normally reset after each test method by the test framework; calling `reset()` does not alter the context cache key. However, **defining different sets of mock beans** between test classes alters the context customizer and can create different cache keys.

### 17.4. Different TestConfigurations

A nested `@TestConfiguration` adding a custom bean, a different `@Import`, or differing `@AutoConfigure...` flags can make context customizers/configurations diverge. When reuse is desired, standardize test configs deliberately while preserving required test semantics.

## 18. Testcontainers and context cache lifecycle

A frustrating failure mode:

```text
Test class A starts RedisContainer A at mapped port 32768
Spring context A creates Lettuce client to port 32768
Class A ends; Testcontainers JUnit stops container A
Spring context A stays in static TestContext cache

Test class B with same key begins
Spring reuses context A
Redis client still points at 32768, but container A is stopped
Test B fails with connection refused
```

This is an example of **external resource lifetime** mismatching context lifetime. Dynamic property method identity/return values can make cache reuse subtle.

Strategies:

1. Use a container lifecycle tied to the Spring `ApplicationContext` where supported.
2. Or use a singleton container living for the entire JVM/suite when contexts should be reused.
3. Or intentionally create separate per-class contexts and ensure no context is reused pointing to a stopped resource.
4. Do not use a shared container whose teardown in class A stops it while the context remains cached.
5. Do not rely on `@DirtiesContext` to wipe database/Redis data inside a surviving container.
6. Do not hardcode container mapped ports; use Spring Boot `@ServiceConnection` or dynamic properties with proper lifecycle.

**Trade-off:** reusing contexts speeds up tests but extends the required lifetime of datasources/containers. Do not just raise `cache.maxSize` if it keeps clients pointing to dead resources.

## 19. Process boundaries: Gradle, Maven, IDE, and CI

A suite with 100 classes sharing the same key can still show 8 context startups if the build splits work across 8 JVMs. That is not a cache miss inside one JVM—it is **8 independent caches**.

### 19.1. Gradle

`maxParallelForks` sets how many worker processes run tests concurrently. `forkEvery` limits the maximum classes processed by one worker before a fresh fork. If you want cross-class context reuse, verify they actually run in the same fork.

### 19.2. Maven

Surefire/Failsafe `forkCount`, `reuseForks`, and parallel settings affect context reuse. `forkCount=0` runs in-process per plugin/version semantics and affects isolation; do not change it blindly just to optimize.

### 19.3. IDE

Running A and B separately via two Run Configurations can spawn two JVMs; you will observe both starting up despite sharing the same merged key. To observe reuse, run the suite together in one test process.

### 19.4. CI matrix/shards

Each shard/CI agent/container has its own JVM. Aggregate startup metrics across shards, but **do not** expect cross-shard context cache sharing. When evaluating end-to-end performance, use pipeline wall-clock time and resource cost, not just unique contexts per process.

## 20. LRU eviction, heap usage, and context leaks

When `maxSize`=32 and a suite has >32 distinct keys, Spring closes LRU contexts. If a test holds a static reference to an evicted bean/context, that reference becomes stale or retains resources so GC cannot collect them.

### 20.1. Do not store injected beans in static fields

A JUnit test class with a field:

```java
static ApplicationContext retainedContext;
```

is an anti-pattern without explicit ownership. Spring can evict/close the context while the static reference lingers; singleton resources may misbehave and memory is not freed as expected.

### 20.2. Cache eviction does not reset external databases

Evicting/closing a Spring context typically stops context-owned beans/resources, yet **does not automatically wipe external PostgreSQL/Redis/Kafka data**. A new context can still read old state. Test data isolation bugs and context reuse bugs are two distinct problems.

### 20.3. Changing max size does not fix root causes

If 300 keys are generated by 300 distinct sets of mock beans/differing properties, raising cache size to 300 can retain too many contexts and trigger OOM. It is better to standardize configurations, reuse common test slices, eliminate unnecessary differences, and measure costs first.

## 21. @DirtiesContext and singleton mutable state

A stateful singleton test fixture:

```java
@Component
class CountingStore {
    private int count;

    void add() { count++; }
    int value() { return count; }
}
```

If two tests reuse the context, `count` from test A can remain when test B begins. That is state leakage, **not a Spring cache bug**. Solutions:

- Reset state in `@BeforeEach`/`@AfterEach` when safe.
- Use test transaction rollback to isolate DB state at the right boundary.
- Use fresh test data IDs and clean up resources owned by each test.
- Separate state into per-request/per-test scope if appropriate.
- Only use `@DirtiesContext` if the singleton/bean graph was altered unrecoverably.

**Do not disable caching globally** just because one test fails to reset state; fix isolation at the proper layer.

## 22. Strategy for analyzing a slow test suite

### Step 1. Collect a baseline

Run under identical workload, JVM, test worker settings, test ordering, and CI machine category. Record:

- Total executed and skipped tests/methods.
- Test task wall time.
- Number of worker JVM processes.
- Total context start events or marker creations.
- Cache DEBUG snapshots: size, hits, misses, max size.
- Expensive dependencies: DB migrations, Testcontainers, embedded servers, Spring Security/ORM.
- Heap/memory and GC metrics if under pressure.

### Step 2. Locate cache-key fragmentation

Group by `@SpringBootTest` vs. slice, profiles, inline properties, `@TestPropertySource`, mocks/customizers. Find nearly identical classes that differ only by an unnecessary property or mock.

### Step 3. Distinguish misses from configuration vs. eviction

If unique key count is small and current size is stable, misses are mostly initial loads. If distinct keys exceed `maxSize` and contexts reload, LRU churn may add overhead. If tests mark dirty frequently, misses occur even when keys stay constant.

### Step 4. Inspect JVM boundaries

If identical classes run across multiple forks/shards, the static cache is not shared. Changing fork settings can reduce startups but may also reduce parallelism or raise time-to-completion. Compare **pipeline wall time**, not just context count.

### Step 5. Test one optimization at a time

For example, remove an unnecessary `@MockBean` difference, standardize inline properties, consolidate a common `TestConfiguration`, or remove `@DirtiesContext` where state can be reset. Re-run the exact same workload and measure.

### Step 6. Verify correctness did not drop

After optimizing, negative/positive tests must remain intact and tests must not depend on each other's state. A fast suite suffering from test pollution is unacceptable.

## 23. What does cache hit rate mean?

Looking strictly at lookup counters without complex failure/reload effects, we can define:

\[
\text{Lookup hit ratio} =
\frac{\text{hitCount}}
{\text{hitCount}+\text{missCount}}
\]

For a hypothetical hit=90, miss=10 → 90% hit ratio. However, this is a **ratio over cache lookup attempts**, not the share of JUnit methods avoiding bootstrap. Moreover, context startup cost varies wildly across keys, so a 99% hit ratio does not guarantee a fast suite.

A single miss loading a 20-second context can outweigh many hits on a 100ms context. To optimize effectively, weight by **miss cost (context startup time)** when data is available.

### 23.1. Snapshot vs. delta

A DEBUG log may print:

```text
size = 8, hitCount = 300, missCount = 12
size = 8, hitCount = 320, missCount = 12
```

The interval delta is +20 hits, +0 misses—not "620 hits". Do not sum two cumulative snapshots.

### 23.2. Failure threshold 6.1

Since Spring Framework 6.1, the default context failure threshold is **1** per cache key; after the first failed load, subsequent attempts can fail fast instead of booting repeatedly. The JVM property `spring.test.context.failure.threshold` can be tuned for diagnostics when needed.

This differs from `spring.test.context.cache.maxSize` and from JUnit retry behavior. Do not recommend raising the failure threshold in general CI: doing so makes the suite repeatedly boot broken contexts and run slower without improving diagnostics.

## 24. Real-world log reading example

Suppose test suite A produces hypothetical logs:

```text
T0  size=0 maxSize=32 hits=0 misses=0
T1  size=1 maxSize=32 hits=0 misses=1
T2  size=1 maxSize=32 hits=7 misses=1
T3  size=2 maxSize=32 hits=7 misses=2
T4  size=2 maxSize=32 hits=19 misses=2
```

We can interpret:

- T0→T1: one lookup miss and the cache holds one context.
- T1→T2: seven cache hits, size unchanged.
- T2→T3: another lookup miss and size becomes two.
- T3→T4: 12 hits, no additional miss.

**You cannot conclude** there were exactly 19 JUnit tests or 19 service calls. This is a **statistical logic example**, not an actual log from an IDE/Gradle run.

If T5 drops size back to 1, eviction, dirtying, context close, or hierarchy behavior may have occurred; inspect more details instead of jumping to a single cause.

## 25. When should a marker be placed in a separate test configuration?

If you do not want a marker bean inside the main app class, create a `@TestConfiguration` and import it only in the test classes being measured:

```java
@TestConfiguration(proxyBeanMethods = false)
public class CacheProbeConfig {
    private static final AtomicInteger CREATED =
            new AtomicInteger();

    @Bean
    ContextMarker marker() {
        return new ContextMarker(
                CREATED.incrementAndGet());
    }
}
```

This is an illustrative snippet requiring `ContextMarker`, imports, and test config; it is not part of the main runnable project. Adding `@Import(CacheProbeConfig.class)` to tests itself participates in configuration/cache keys. If only some tests import the marker while others do not, the counter does not reflect all contexts.

### 25.1. Do not add a separate nested class marker per test

If each test class defines its own nested `@TestConfiguration`, those can **themselves split the cache key** and skew measurements. Use a single shared test configuration class when measuring reuse without fragmenting configuration.

### 25.2. Count creations, not accesses

The marker does not need mutable singleton business state; the bean carries a fixed sequence. Tests only read the ID. A static `AtomicInteger` increment inside the bean factory measures how many times the bean factory method actually ran, which does not automatically equal the test method count.

## 26. Common mistakes

| Symptom | Cause | How to verify |
| --- | --- | --- |
| Every test class prints Starting... | Different cache keys, forks, dirtying | DEBUG cache stats + JVM settings |
| High HitCount yet task still slow | A few very expensive misses, DB/IO per test | Startup time/profile |
| MissCount higher than unique configurations | LRU eviction, dirtying, failed loads | Logs over time, marker IDs |
| Size=32 yet >32 contexts created | Bounded max cache, LRU churn | Marker, maxSize, key grouping |
| Size=1 yet bean created many times | Context dirty/reload or forks | Static per-process marker |
| Same @SpringBootTest yet different contexts | @MockBean/@SpyBean/customizers/profiles | Merged config differences |
| Identical @DynamicPropertySource yet dead resource | Container lifecycle differs from context lifecycle | Container start/stop logs |
| Tests share context yet data leaks | Singleton/DB/cache not reset | @BeforeEach cleanup |
| @DirtiesContext makes suite very slow | Repeated context startup | Inspect dirty annotations |
| Cache stats not appearing | DEBUG logging not applied properly | logback-test/Boot logging |
| Marker count doesn't rise when context fails | Bean not created before failure | Failure logs/threshold |
| Marker count rises despite same key | Key evicted/dirtied or another JVM | Cache logs and process identity |
| IDE run differs from Gradle | Different process/fork/logger | Compare launch configuration |
| JVM OOM after raising maxSize | Too many pools/beans retained | Heap, threads, process memory |
| @WebMvcTest slower than expected | Custom imports/mocks/slice scope | Compare actual context startup |
| Test count=500, miss=10 | Normal: multiple tests share context | Do not equate lookup count to tests |
| Misread hit/miss snapshots | Cumulative counters added wrongly | Compute deltas |
| Clearing context cache leaves DB populated | External data not reset | Cleanup provider data separately |
| Run with @DirtiesContext appears green | Hides shared state pollution | Prefer explicit fixture cleanup |
| Parallel suite unpredictable marker count | Global static counter across concurrent contexts | Run diagnostic suite isolated |
| @ContextHierarchy changes counts | Parent and child contexts share/evict differently | Hierarchy mode, parentCount |

## 27. Hands-on exercises

1. **Same key:** Run `equivalentFixtureKeysReuseSameContext` and verify `SharedA`/`SharedB` share the same context object.
2. **Repeated lookup:** Increase calls to `contextFor(SharedA.class)` from 3 to 10; marker count stays unchanged after the first load.
3. **Property value:** Change `cache.study.variant=different` to `shared` in `DifferentProperty`; before changing expected assertions, check identity/key equality and explain what changes.
4. **Profile:** Remove `@ActiveProfiles("scenario")` and check whether the cache key still differs.
5. **DirtiesContext:** Use the Dirty fixture; call mark dirty then reload, assert a different context and incremented marker.
6. **Count contexts:** In a clean JVM, compare marker sequences across `SharedA`, `DifferentProperty`, `DifferentProfile`, and `Dirty` before/after; do not use total test count as a proxy.
7. **Read stats:** Enable DEBUG and record final hit/miss/size at the end of a run; do not invent numbers.
8. **Max size:** Try `-Dspring.test.context.cache.maxSize=2` in a sandbox branch and observe LRU eviction/reloading across multiple keys. Ensure test assertions do not assume fixed startup counts if order changes.
9. **Forks:** Change Gradle `maxParallelForks=2` with multiple classes and distinguish per-JVM static context caches.
10. **Mock customization:** Create two test classes with different `@MockBean` definitions (Boot 3.3) and observe separate contexts.
11. **Common test config:** Use one shared test configuration class instead of a distinct config per class and compare startup cost.
12. **Dirties vs cleanup:** Build a singleton counter fixture and compare `@BeforeEach` reset vs. `@DirtiesContext(AFTER_METHOD)`; measure startup overhead and correctness.
13. **Testcontainers:** Create a shared Redis container kept alive for the context lifecycle, then measure cache hits; avoid stale connections from class teardown.
14. **Different slices:** Compare `@JsonTest` with full `@SpringBootTest` in terms of bootstrapped beans/time without confusing scopes.
15. **Debug snapshot:** From three cumulative logs, compute hit/miss deltas between timestamps accurately.
16. **Failure threshold:** Intentionally create a broken bean config in an isolated test and observe Spring 6.1 fail-fast; do not alter global CI just to suppress errors.
17. **One-key-many-tests:** Create 10 JUnit methods with the same `@SpringBootTest` config; observe one reused context and multiple cache lookups.
18. **CI shards:** Run the same tests on two workers/shards and explain why each process sees an initial miss.
19. **Marker limitations:** A context not importing the marker will not increment the counter; explain why marker count does not represent all contexts.
20. **Memory cost:** Increase `cache.maxSize` and monitor heap, Hikari pools, and process threads; measure the trade-off instead of raising blindly.

## 28. Pre-optimization QA checklist

- [ ] Distinguished TestContext cache from business `@Cacheable`/Redis cache.
- [ ] Used matching Spring Boot/Spring Framework versions.
- [ ] Understood the cache key is merged configuration, not just test class name.
- [ ] Accounted for `@ActiveProfiles`, `@TestPropertySource`, and inline properties.
- [ ] Accounted for `@MockBean`/`@SpyBean` and context customizers.
- [ ] `@DynamicPropertySource` method/lifecycle does not reuse stale clients.
- [ ] Enabled DEBUG for `org.springframework.test.context.cache` during analysis.
- [ ] Understood `hitCount` as lookup hits, not number of test methods.
- [ ] Understood `missCount` as cache-key-missing accesses, not necessarily unique instances.
- [ ] Understood `size` as current cache entries, not historical total.
- [ ] Understood default `maxSize` 32 and LRU eviction.
- [ ] Distinguished Spring 6.1 failure threshold from misses/evictions.
- [ ] Recorded process/fork settings; static cache is shared only within one JVM.
- [ ] Marker counter counts only contexts that contain and instantiate the marker bean.
- [ ] Tests compare `ApplicationContext` object identity via `assertSame`/`assertNotSame`.
- [ ] Did not assert `context.getId()` is always unique upon reload.
- [ ] Tested one key varying a property and one varying a profile.
- [ ] `@DirtiesContext` used only when context state cannot be reset.
- [ ] DB/Redis/queue data cleaned separately without relying on context close.
- [ ] Not holding static `ApplicationContext`/bean references that leak resources after eviction.
- [ ] Not exploiting private `ContextCache` internals/reflection to write product tests.
- [ ] Not taking multiple cumulative snapshots and summing them as deltas.
- [ ] Not hardcoding uncontrolled startup milliseconds.
- [ ] Test slices/full contexts chosen according to test scope.
- [ ] Not sacrificing correctness unconditionally for speed.
- [ ] When parallel, global markers and reuse assertions have proper isolation.
- [ ] When reporting performance, included real executed/skipped counts, wall time, and process count.
- [ ] If Gradle was not run, results are explicitly labeled as expected/not executed.

## 29. Quick diagnostic rules

```text
Seeing multiple "Starting Application" lines?
      |
      +-- Are test classes truly in the same JVM?
      |      -> Check Gradle/Maven forks, CI sharding.
      |
      +-- Is MergedContextConfiguration identical?
      |      -> Profiles, properties, mocks, test imports,
      |         dynamic properties, context customizers.
      |
      +-- Is @DirtiesContext evicting?
      |      -> Use only when state cannot be reset at the right layer.
      |
      +-- Unique keys > maxSize?
      |      -> LRU churn, same key may reload.
      |
      +-- Did context fail to load?
      |      -> Spring 6.1 failure threshold / bean errors.
      |
      +-- Need to inspect stats?
      |      -> DEBUG org.springframework.test.context.cache.
      |
      +-- Need to prove same instance?
      |      -> assertSame(ApplicationContext a,b).
      |
      +-- Need to count actual contexts created?
      |      -> Test-only eager marker bean sequence,
      |         with known scope and no concurrent extra loads.
      |
      +-- Need to know if suite is faster?
             -> Benchmark repeated runs + startup logs,
                process/heap/GC/CI wall-clock metrics.
```

## 30. Conclusion

A **cache hit** means Spring TestContext found a previously loaded `ApplicationContext` matching an equivalent cache key. A **cache miss** means the lookup found no matching entry—either because the key appeared for the first time, the context was dirtied/evicted, or it ran in a new process cache. **Current cached context count** (`size`) does not equal total contexts ever created. **Actual created instances** should be observed with an appropriate marker bean/startup instrumentation while clearly noting process, scope, and failure limitations.

Good Spring Boot testing performance comes from designing the **right test scope**, reusable cache keys where safe, proper state cleanup at each layer, and real measurements. Do not force every test to share one context if that creates inter-test data dependencies; and do not slap `@DirtiesContext` onto every method merely to hide state pollution.

## 31. Official Documentation

- Spring Framework — Context Caching: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html
- Spring Framework 6.1 — Context Caching (versioned reference): https://docs.spring.io/spring-framework/docs/6.1.x/reference/html/testing.html
- Spring Framework — Context Failure Threshold: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/failure-threshold.html
- Spring Framework — Spring Testing Annotations: https://docs.spring.io/spring-framework/reference/testing/annotations/integration-spring/annotation-dirtiescontext.html
- Spring Framework — TestContext Framework overview: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework.html
- Spring Framework 6.1 — TestContext Javadoc (getApplicationContext/markApplicationContextDirty): https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/test/context/TestContext.html
- Spring Framework — TestContextManager Javadoc: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/test/context/TestContextManager.html
- Spring Framework — TestContext cache key, @ContextConfiguration and customizers: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/context-customizers.html
- Spring Framework — @DynamicPropertySource: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Testcontainers/service connection integration: https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html
- Gradle — Java testing (maxParallelForks/forkEvery): https://docs.gradle.org/current/userguide/java_testing.html
- JUnit Jupiter — Lifecycle, parallel tests, and test suites: https://docs.junit.org/current/user-guide/
