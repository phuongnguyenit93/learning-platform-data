# How the Context Cache Reuses ApplicationContext

## 1. Why don't Spring Boot tests usually restart the context after each test?

A single `@SpringBootTest` run can be expensive: Spring scans configuration, analyzes auto-configuration, initializes singleton beans, creates the JPA EntityManagerFactory, DataSource pool, HTTP clients, security chain, and other beans. If you have 80 test methods, restarting the entire context 80 times is usually wasteful and does not help detect additional bugs.

Spring Framework TestContext provides an **ApplicationContext cache** to avoid this cost. After successfully loading a context, the framework stores it in a **JVM-wide static** cache. Tests with an **equivalent configuration key** can receive the **exact same ApplicationContext instance**. Multiple test classes with different names can still share one context; conversely, two adjacent methods can run on different contexts if the configuration differs or the context is marked dirty.

Key point to remember:

> **Reuse is based on the configuration key, not simply on class name, method name, package, or the `@SpringBootTest` annotation alone.**

The cache is a mechanism of the **Spring TestContext Framework**. Spring Boot test support uses this mechanism and adds its own context customizers, bootstrap rules, test slices, and configuration. There is no mandatory rule of "one context per test method".

### What you will learn

- How a context is loaded, cached, looked up, and closed.
- What configuration metadata Spring uses to compute a **cache key**.
- Changes that inadvertently cause cache misses: profiles, inline properties, `@TestPropertySource`, dynamic properties, bean overrides, and web mode.
- The meaning of a static cache **within the same JVM**, the default limit of **32**, the **LRU** policy, and cache statistics.
- How `@DirtiesContext` evicts a context, and how it differs from resetting data, beans, or mocks.
- Why context cache reuse can expose state leakage between tests and how to handle it without hurting performance.
- The role of `@MockitoBean`/`@MockBean`, `@DynamicPropertySource`, `@ServiceConnection`, context hierarchies, and test slices.
- How to observe cache hits/misses and tune max cache size and the failed-context threshold.
- A complete example with Java 17+, Spring Boot **3.5.16**, and JUnit Jupiter featuring **9 test methods** verifying context identity.

**Version scope:** Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, JUnit Jupiter. Spring Boot 4.x / Spring Framework 7.x may change packages, starters, or test behaviors. The explanations of cache keys, 32-entry LRU, static cache, and `@DirtiesContext` here are based on Spring Framework 6.2 documentation.

## 2. Lifecycle: load, cache, reuse, evict

```text
                  TestClass A needs ApplicationContext
                                  |
                                  v
                  TestContext builds configuration KEY
                                  |
                                  v
                           cache lookup
                           /          \
                         HIT          MISS
                          |             |
                          v             v
              reuse cached context  load new context
                          |             |
                          |        startup succeeds?
                          |           /       \
                          |         yes       no
                          |          |         |
                          |       cache put   fail/threshold
                          |          |
                          +----------+
                                  |
                                  v
                         Test uses beans
                                  |
                    next TestClass with same KEY
                                  |
                                  v
                         same context instance

     Eviction: @DirtiesContext / LRU / JVM shutdown
                    -> context removed/closed
                    -> next request reloads for that key
```

**Main stages:**

1. Spring TestContext determines how to bootstrap and configure the test's context.
2. It creates a `MergedContextConfiguration` representing the configuration metadata.
3. The framework looks up the cache entry by that key.
4. **Hit:** returns the existing context without refreshing the bean factory like the first time.
5. **Miss:** creates a new context, runs refresh/startup; if successful, puts it into the cache.
6. The test method uses the context, beans, and dependencies as normal.
7. The context usually stays in the cache after the test method/class so subsequent tests can reuse it.
8. The context can be closed upon `@DirtiesContext`, LRU eviction, or JVM shutdown.

### 2.1. "Reuse" means the same object, not just an identical configuration

On a cache hit, assertions like the following hold true:

```java
assertThat(secondContext).isSameAs(firstContext);
assertThat(secondContext.getBean(MySingleton.class))
        .isSameAs(firstContext.getBean(MySingleton.class));
```

This is a **snippet** and will not compile on its own without variables and imports. A cache hit returns the **same ApplicationContext instance**; therefore, singleton beans are preserved. It does not merely recreate an "identical" context. In section 9, we will use `TestContextManager` and `isSameAs` to prove this in a JUnit test.

### 2.2. Cache vs. singleton scope

A `@Scope("singleton")` bean has only **one instance per ApplicationContext**, not a single instance across the entire JVM. Two different contexts can contain two singleton beans of the same type that are different instances.

The context cache decides which tests share the entire **container**. Singleton scope decides how many instances of a bean exist within **one container**. Do not confuse the two mechanisms.

### 2.3. Context startup vs. method execution

When multiple tests reuse the same context, bean initialization cost is not repeated. However, code inside test methods, `@BeforeEach`, transactions, fixture creation, HTTP requests, SQL cleanup, and application logic still runs according to the JUnit/test listener lifecycle. **The context cache does not cache assertion results, database queries, or HTTP responses**.

## 3. What is the cache key computed from?

Spring Framework 6.2 documentation lists the primary components of the context cache key:

| Key component | Configuration source | Example that changes the key |
|---|---|---|
| `locations` | `@ContextConfiguration` XML/Groovy resource locations | Changing config file |
| `classes` | `@ContextConfiguration` classes | Changing a configuration class |
| `contextInitializerClasses` | Initializers | Adding an `ApplicationContextInitializer` |
| `contextCustomizers` | TestContext ContextCustomizerFactory | `@DynamicPropertySource`, `@MockitoBean`, `@TestBean`, various Boot customizers |
| `contextLoader` | Context loader class | Changing loader/bootstrap mechanism |
| `parent` | `@ContextHierarchy` | Different parent hierarchy |
| `activeProfiles` | `@ActiveProfiles` | `test` vs. `integration` |
| `propertySourceDescriptors` | `@TestPropertySource` files/resources | Changing properties resource |
| `propertySourceProperties` | `@TestPropertySource` inline values and inline test properties included in metadata | Changing a key/value |
| `resourceBasePath` | `@WebAppConfiguration` | Changing web resource base |

With Spring Boot, options such as `@SpringBootTest(properties=...)` and test-slice annotations can also affect the effective configuration key via property metadata and/or context customizers. **Do not assume that simply using the same `@SpringBootTest` annotation guarantees a shared context.**

### 3.1. Example of two classes that can reuse

```java
@SpringBootTest(
    classes = MyApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "feature.mode=test"
)
class CustomerServiceTest {}

@SpringBootTest(
    classes = MyApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "feature.mode=test"
)
class CustomerRepositoryTest {}
```

The two classes above are **illustrative snippets**: if all other key factors are also equivalent and the context has not been evicted, they can receive the same ApplicationContext. Having different class names does not inherently break sharing.

### 3.2. Even one differing property can create a different context

```java
@SpringBootTest(properties = "feature.mode=fast")
class FastModeTest {}

@SpringBootTest(properties = "feature.mode=safe")
class SafeModeTest {}
```

**These are simplified snippets**, assuming Boot auto-detects the application config as in a real project. Two different sets of inline properties → two different configurations → typically two cache entries. Do not generate a random unique property value per test class unless necessary: you will inadvertently cause constant cache misses.

### 3.3. Method name is not part of the key

Two methods with different names in a test class using the same application config usually share the context, unless `@DirtiesContext`, dynamic test customizations, lifecycle changes, or cache eviction occur. A subsequent test method does not automatically receive fresh beans.

### 3.4. Special attention to dynamic values

`@DynamicPropertySource` is a **context customizer**; the identity/configuration of the method registering dynamic properties affects the key. However, **runtime values returned by the supplier are not automatically compared as immutable fields in the key**. Two classes sharing the same inherited method where the supplier points to different containers/ports may inadvertently reuse a context with values/beans already created from the old source.

According to Spring docs, cases where dynamic properties change between subclasses may require marking the context dirty or separating test configurations. Do not use `@DynamicPropertySource` and assume every random port creates a new key.

## 4. Cache scope: JVM, test suite, forks, and IDE

Spring TestContext's context cache is an **in-process static cache**. It is not Redis, disk, Gradle build cache, Maven repository, JUnit extension store, or a global singleton across JVMs.

```text
JVM process #1: static TestContext cache {Key A -> Context A}
                TestClass A ----------------------> HIT
                TestClass B (same key) -----------> HIT

JVM process #2: static TestContext cache {empty initially}
                TestClass C (same key as #1) -----> MISS + fresh load
```

**Consequences:**

- Running multiple tests **in the same test worker JVM** is required to have a chance to share the cache.
- If Maven Surefire or Gradle is configured to fork/restart the JVM between classes, the static cache does not carry over to another process.
- `maxParallelForks>1` can distribute test classes across multiple workers; each process has its own cache, even if classes share the same configuration.
- The Gradle daemon process and the Gradle test worker JVM are not the same process by default.
- An IDE may use one or multiple test JVMs depending on how it is launched and configured.
- A new build command or a new IDE run generally does not reuse the in-memory Spring TestContext cache from the previous run.

**Do not** use `System.identityHashCode(context)` from two different JVMs to conclude reuse; numbers can collide by chance and do not prove object identity.

### 4.1. Gradle configuration to optimize sharing potential

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()

    // Demo: single test worker JVM, do not refork after N classes
    maxParallelForks = 1
    forkEvery = 0

    // JVM system property of the TEST worker, not just the Gradle daemon:
    systemProperty 'spring.test.context.cache.maxSize', '32'
    systemProperty 'spring.test.context.failure.threshold', '1'
    systemProperty 'logging.level.org.springframework.test.context.cache',
            'DEBUG'
}
```

This is a Gradle snippet for a Boot 3.5-compatible project. It makes inspection clearer in a single test JVM, but **does not mean** all tests will share one context if their cache keys differ. Enabling DEBUG logging for the cache can produce verbose logs; use it during diagnosis rather than logging continuously on every CI job.

### 4.2. Maven Surefire

For Maven, check `forkCount`, `reuseForks`, parallel test execution, and JVM options. If each test class uses a fresh fork, the Spring cache has no opportunity to reuse across classes. In practice, multiple forks may be needed to isolate leaks, but you must accept the startup cost and not blame all slowness on Spring.

## 5. Capacity: default 32 contexts and LRU

Spring Framework 6.2 provides a default cache max size of **32 ApplicationContext entries**. When the number of distinct context configurations exceeds this limit, the default cache implementation uses a **least recently used (LRU)** policy to evict and close the least recently used context.

Conceptual example:

```text
Cache capacity = 3 (illustrative, not default)

Run A -> miss, cache [A]
Run B -> miss, cache [A,B]
Run C -> miss, cache [A,B,C]
Run A -> hit,  A is most recently used
Run D -> miss, evict B, cache [A,C,D]
Run B -> miss (B was closed), reload B, evict LRU
```

**Do not infer LRU behavior solely by measuring elapsed time.** LRU is based on cache access history; Spring docs state the policy explicitly. Increasing max size can reduce evictions but retains more bean graphs, thread pools, caches, or DataSources in RAM. Raising the cache to 100 will not help on its own if every test uses a unique key.

### 5.1. How to configure capacity

JVM system property:

```text
-Dspring.test.context.cache.maxSize=64
```

Or via the `SpringProperties` mechanism per Spring Framework docs. **It must be set early enough before the TestContext cache is used**, typically via Gradle/Maven test worker JVM args. Putting it in `application-test.yml` may not affect cache bootstrap because it is a Spring TestContext cache setting rather than a bean inside the application context.

### 5.2. Is changing 32 to 64 always faster?

No. If a suite has 10 unique contexts, 32 is already sufficient and increasing to 64 is pointless. If a suite has 80 unique contexts, first investigate the cause: varying inline properties, profile combinations, differing mocks, dynamic customizers, duplicate test slices. Increasing cache size only makes sense when the memory budget allows and statistics prove eviction/thrashing is a significant bottleneck.

## 6. Context cache statistics: observe instead of guessing

Spring Framework supports logging under the category:

```properties
logging.level.org.springframework.test.context.cache=DEBUG
```

Set this in the appropriate test logging configuration to see statistics. You can use JVM/Gradle test-worker logging system properties as in the previous snippet.

Debug output typically includes:

- Current cache size.
- Max size.
- Hit count.
- Miss count.
- Parent context count in certain cases.
- Failure count related to the failure threshold in supported versions.

These metrics are **cumulative within a single JVM's cache**; do not treat the hit count from a full suite run as the exact number of times a controller method was invoked. The context can be looked up multiple times while `SpringExtension` listeners prepare each test, so the hit count can be larger than "the number of tests that reused it".

### 6.1. Reading metrics accurately

| Signal | Possible meaning | Further check |
|---|---|---|
| Hits increasing | Framework found context by key | Which tests have equivalent metadata? |
| Misses increasing | Key has no usable cached context | Different configuration, eviction, fork, dirty? |
| Cache size frequently near max | Many unique entries | Is LRU eviction/reload happening? |
| Increased maxSize but still just as slow | Not an eviction bottleneck | Check external fixtures, DB setup, migrations |
| Application restarts many times | Cache miss or dirty/fork | Compare keys and startup logs |
| No cache logs visible | Category not at DEBUG or logger not configured | Test JVM logging config, test runner |

**Performance optimization must be measured on the same CI environment and the same workload.** A cold run differs from a warm run, and image pulls or database migrations can overshadow context cost.

## 7. @DirtiesContext: intentional eviction, not data reset

`@DirtiesContext` signals that the ApplicationContext has been modified by a test in a way that makes reuse unsafe. Spring TestContext will **remove the context from the cache and close it**, so the next request for the same key creates a new context.

Representative modes:

```java
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class ChangesGlobalContextTest {}
```

```java
@Test
@DirtiesContext(
        methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void mutatesSingletonConfiguration() {
    // Test modifies state/definitions making the context unsafe to reuse.
}
```

These are **illustrative snippets**, not complete runnable test classes. Verify that the context is genuinely mutated before using this annotation.

### 7.1. BEFORE vs AFTER

- `ClassMode.AFTER_CLASS`: after the class, the context is marked dirty/closed; the next class with the same key reloads.
- `ClassMode.BEFORE_CLASS`: before the class, evicts any old cached context and the class loads a new context.
- `MethodMode.AFTER_METHOD`: after the test method, marked dirty; the next method with the same key must reload.
- `MethodMode.BEFORE_METHOD`: before the method, marked dirty; the test uses a fresh context.
- If the annotation is present on both class and method, the respective modes are applied according to Spring TestContext listeners.

**Do not use `@DirtiesContext` by default on every test class** to "guarantee cleanliness". Doing so eliminates most caching benefits and lengthens the suite significantly.

### 7.2. When is @DirtiesContext needed?

Usually only when a test:

- Modifies bean definitions or context state that cannot be reset.
- Attaches or alters environment/singleton configuration in a way that makes the context unsafe.
- Uses a lifecycle-sensitive integration object whose shutdown/restart affects the shared context.
- Truly breaks assumptions that other tests using the context will rely on.

**It is not automatically needed** after saving an entity to the DB (transaction rollback/clean fixtures are usually better) or after a mock returns a different response (mock reset is usually sufficient). A mutable bean can expose a `reset()` method in `@AfterEach` instead of closing the entire context.

### 7.3. Context hierarchy

If tests use `@ContextHierarchy`, dirtying a context also accepts `hierarchyMode`. The default `EXHAUSTIVE` can affect **subhierarchies sharing a common ancestor**; `CURRENT_LEVEL` limits eviction further when appropriate. Do not blindly enable `CURRENT_LEVEL` if an ancestor was also modified; the parent context could still hold invalid state.

## 8. Designing a demo that observes object identity

This example uses Java 17, Spring Boot 3.5.16, Spring Framework TestContext, JUnit Jupiter, and AssertJ.

**Idea:** a minimal app creates three beans:

- `ContextStamp`: a record containing a UUID generated when the context starts up (for observation).
- `RequestCounter`: a mutable singleton used to demonstrate state leakage when a context is reused.
- `Clock`: a bean to be mocked with `@MockitoBean`, thereby illustrating how a bean override changes the cache key.

A regular JUnit class (not annotated with `@SpringBootTest` itself) invokes `TestContextManager` with **fixture test classes** annotated with `@SpringBootTest`. This explicitly loads contexts **within the same test method**, so we can assert object identity without depending on which class JUnit runs first.

### 8.1. File tree

```text
src/
├── main/java/com/example/cachelab/
│   └── CacheLabApplication.java
└── test/java/com/example/cachelab/
    └── ContextCacheBehaviorTest.java
build.gradle
settings.gradle
```

The demo has no HTTP server, database, Docker, or network dependency. `webEnvironment=NONE` keeps the scope focused on the TestContext cache.

### 8.2. Build configuration

**File `build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Keep the demo in a single JVM, do not fork per class.
    maxParallelForks = 1
    forkEvery = 0
}
```

**File `settings.gradle`:**

```groovy
rootProject.name = 'context-cache-lab'
```

From the Spring Boot 3.5 BOM, `spring-boot-starter-test` provides JUnit Jupiter, AssertJ, Spring Test, and Mockito needed for the demo. No spring-security, spring-web, or database starter is required.

Note: The Gradle Wrapper is not generated in this content; use Gradle/IDE or initialize a Gradle project with a compatible wrapper. Do not treat `build.gradle` as a standalone shell script.

## 9. Production source code of the demo

**File `src/main/java/com/example/cachelab/CacheLabApplication.java`:**

```java
package com.example.cachelab;

import java.time.Clock;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class CacheLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheLabApplication.class, args);
    }

    @Bean
    ContextStamp contextStamp() {
        return new ContextStamp(UUID.randomUUID());
    }

    @Bean
    Clock appClock() {
        return Clock.systemUTC();
    }

    @Bean
    RequestCounter requestCounter() {
        return new RequestCounter();
    }

    public record ContextStamp(UUID id) {}

    public static final class RequestCounter {
        private final AtomicInteger counter = new AtomicInteger();

        public int value() {
            return counter.get();
        }

        public int increment() {
            return counter.incrementAndGet();
        }

        public void restore(int before) {
            counter.set(before);
        }
    }
}
```

**Key points to understand:**

- Each time a new `CacheLabApplication` context is created, the `contextStamp()` bean method generates a new record/UUID.
- If the context is reused, the existing `ContextStamp` singleton remains.
- `RequestCounter` is not automatically reset between test methods just because JUnit creates a new test instance.
- `Clock` is a tangible bean for Spring Framework 6.2 `@MockitoBean` to override.
- The UUID/identity is only for observation; the UUID is not used to construct the cache key.
- Do not put the mutable counter in a static field in the app; the goal is to prove **state inside the singleton container**, not just Java static state.

## 10. Runnable test suite: 9 JUnit methods

**File `src/test/java/com/example/cachelab/ContextCacheBehaviorTest.java`:**

```java
package com.example.cachelab;

import java.time.Clock;

import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.annotation.DirtiesContext;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.TestContextManager;
import org.springframework.test.context.TestPropertySource;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

import static org.assertj.core.api.Assertions.assertThat;

class ContextCacheBehaviorTest {

    // Fixture classes intentionally have identical configuration metadata
    // except where a test is specifically demonstrating a cache-key change.

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    static class SharedA {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    static class SharedB {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    @ActiveProfiles("alternate")
    static class DifferentProfile {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = {
            "cache.lab.group=shared",
            "cache.lab.variant=inline"
        }
    )
    static class DifferentInlineProperty {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    @TestPropertySource(
        properties = "cache.lab.source=separate"
    )
    static class DifferentTestPropertySource {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    static class DynamicPropertyFixture {
        @DynamicPropertySource
        static void dynamic(DynamicPropertyRegistry registry) {
            registry.add("cache.lab.dynamic", () -> "from-supplier");
        }
    }

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    @MockitoBean(types = Clock.class)
    static class MockClockFixture {}

    @SpringBootTest(
        classes = CacheLabApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "cache.lab.group=shared"
    )
    @DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_CLASS
    )
    static class DirtyAfterFixture {}

    private static ApplicationContext load(Class<?> fixtureClass) {
        return new TestContextManager(fixtureClass)
                .getTestContext()
                .getApplicationContext();
    }

    @Test
    void sameConfigInDifferentClassesReusesExactContext() {
        ApplicationContext first = load(SharedA.class);
        ApplicationContext second = load(SharedB.class);

        assertThat(second).isSameAs(first);
        assertThat(second.getBean(
                CacheLabApplication.ContextStamp.class))
                .isSameAs(first.getBean(
                        CacheLabApplication.ContextStamp.class));
    }

    @Test
    void repeatedLookupOfOneFixtureUsesSameInstance() {
        ApplicationContext first = load(SharedA.class);
        ApplicationContext second = load(SharedA.class);

        assertThat(second).isSameAs(first);
    }

    @Test
    void activeProfileDifferenceCreatesSeparateContext() {
        ApplicationContext base = load(SharedA.class);
        ApplicationContext variant = load(DifferentProfile.class);

        assertThat(variant).isNotSameAs(base);
        assertThat(variant.getEnvironment().getActiveProfiles())
                .contains("alternate");
    }

    @Test
    void inlineTestPropertyDifferenceCreatesSeparateContext() {
        ApplicationContext base = load(SharedA.class);
        ApplicationContext variant =
                load(DifferentInlineProperty.class);

        assertThat(variant).isNotSameAs(base);
        assertThat(variant.getEnvironment().getProperty(
                "cache.lab.variant")).isEqualTo("inline");
    }

    @Test
    void testPropertySourceChangeCreatesSeparateContext() {
        ApplicationContext base = load(SharedA.class);
        ApplicationContext variant =
                load(DifferentTestPropertySource.class);

        assertThat(variant).isNotSameAs(base);
        assertThat(variant.getEnvironment().getProperty(
                "cache.lab.source")).isEqualTo("separate");
    }

    @Test
    void dynamicPropertySourceCustomizerChangesCacheKey() {
        ApplicationContext base = load(SharedA.class);
        ApplicationContext variant =
                load(DynamicPropertyFixture.class);

        assertThat(variant).isNotSameAs(base);
        assertThat(variant.getEnvironment().getProperty(
                "cache.lab.dynamic")).isEqualTo("from-supplier");
    }

    @Test
    void mockitoBeanOverrideChangesCacheKey() {
        ApplicationContext base = load(SharedA.class);
        ApplicationContext variant = load(MockClockFixture.class);

        assertThat(variant).isNotSameAs(base);
        assertThat(Mockito.mockingDetails(
                variant.getBean(Clock.class)).isMock()).isTrue();
        assertThat(Mockito.mockingDetails(
                base.getBean(Clock.class)).isMock()).isFalse();
    }

    @Test
    void mutableSingletonStateIsSharedUntilReset() {
        ApplicationContext first = load(SharedA.class);
        ApplicationContext second = load(SharedB.class);

        CacheLabApplication.RequestCounter counter =
                first.getBean(CacheLabApplication.RequestCounter.class);
        int original = counter.value();

        try {
            int incremented = counter.increment();
            assertThat(incremented).isEqualTo(original + 1);
            assertThat(second.getBean(
                    CacheLabApplication.RequestCounter.class).value())
                    .isEqualTo(original + 1);
        }
        finally {
            // Avoid contaminating other tests sharing this context.
            counter.restore(original);
        }
    }

    @Test
    void dirtiesContextEvictsAndReloadsSameConfiguration()
            throws Exception {
        ApplicationContext oldContext = load(SharedA.class);

        // Drive Spring TestContext lifecycle explicitly for this fixture.
        TestContextManager manager =
                new TestContextManager(DirtyAfterFixture.class);
        manager.beforeTestClass();
        try {
            ApplicationContext dirtyFixtureContext =
                    manager.getTestContext().getApplicationContext();
            assertThat(dirtyFixtureContext).isSameAs(oldContext);
        }
        finally {
            // @DirtiesContext(AFTER_CLASS) closes/evicts this cache key.
            manager.afterTestClass();
        }

        ApplicationContext refreshed = load(SharedB.class);
        assertThat(refreshed).isNotSameAs(oldContext);
    }
}
```

### 10.1. Why is TestContextManager invoked manually?

In a normal JUnit run, `SpringExtension` and Spring TestContext listeners perform the test lifecycle steps automatically. Here we intentionally instantiate `TestContextManager` for different fixture classes **within the same method**, then call `getTestContext().getApplicationContext()`:

- Same configuration metadata → same object identity.
- Different active profile / properties / customizer → different object identity.
- `@DirtiesContext(AFTER_CLASS)` is verified by calling `beforeTestClass()`, `afterTestClass()` on the fixture's manager and then loading the same key again.
- Checking identity in a single method avoids depending on the execution order of two separate JUnit test classes.

**This is an intentional demo of TestContext internals**, not advice to manually instantiate `TestContextManager` in every unit/integration test. In a real application, simply use `@SpringBootTest`, `@Autowired ApplicationContext`, and let `SpringExtension` manage the lifecycle.

### 10.2. What do the 9 tests prove?

| Test method | Expected outcome |
|---|---|
| sameConfigInDifferentClassesReusesExactContext | `SharedA` and `SharedB` share the exact same context instance |
| repeatedLookupOfOneFixtureUsesSameInstance | Looking up the same key multiple times returns the same object |
| activeProfileDifferenceCreatesSeparateContext | Profile is a key component |
| inlineTestPropertyDifferenceCreatesSeparateContext | Inline property changes the key |
| testPropertySourceChangeCreatesSeparateContext | Test property source metadata changes the key |
| dynamicPropertySourceCustomizerChangesCacheKey | DynamicPropertySource method participates in customizer/key |
| mockitoBeanOverrideChangesCacheKey | Bean override is part of context customizers |
| mutableSingletonStateIsSharedUntilReset | Singleton mutable state can leak across tests that reuse the context |
| dirtiesContextEvictsAndReloadsSameConfiguration | Dirty evicts; subsequent lookup creates a new context |

In the four variant comparison tests, the assertions do not claim the variant is created fresh **on every run**: if a variant key is already in the cache from earlier, it may be a cache hit for that variant while still being **different from the baseline key**. This is an important distinction between "different object" and "creating a context for the first time".

### 10.3. Run commands

Linux/macOS:

```bash
./gradlew test --tests "com.example.cachelab.ContextCacheBehaviorTest"
```

Windows PowerShell:

```powershell
.\gradlew.bat test --tests "com.example.cachelab.ContextCacheBehaviorTest"
```

**Code expectation:** 9 JUnit methods pass when dependencies/JDK and the Gradle environment are compatible. This material was reviewed against Spring Framework 6.2 and Spring Boot 3.5 APIs; **it is not a report of actual execution during authoring**. Check the JUnit executed/passed/skipped output rather than only seeing the build task marked UP-TO-DATE or FROM-CACHE.

### 10.4. No need to rely on startup-order stdout

Contexts have their own UUIDs, and startup logs and cache hit counters vary with test order/run. Therefore, the example does not assert UUID ordering or a fixed hit count value. The strongest assertion is `isSameAs/isNotSameAs` when comparing references within the same JVM.

## 11. Context cache and @SpringBootTest in real projects

### 11.1. When do two @SpringBootTest classes share?

Common conditions:

- Same `classes`/bootstrapping configuration and application context type.
- Same active profiles.
- Same inline properties and `@TestPropertySource` declarations.
- Same context initializers/loaders.
- Same mock/spy/test-bean override declarations in context customizers.
- Same dynamic property method/configuration customizers.
- Same parent context/web resource settings, if any.
- Context has not been evicted or dirtied; same test JVM.

**It is not necessary** for all test classes to inherit from the same base class to share; a base class merely helps standardize metadata. If classes declare identical metadata through separate annotations, the cache can still hit.

### 11.2. @SpringBootTest and @WebMvcTest do not share a context by default

`@WebMvcTest` typically loads the MVC slice: controllers, MVC support, relevant filters/configuration; `@DataJpaTest` loads the JPA slice; `@SpringBootTest` loads the full context. These test types usually have different context metadata/customizers, so you should not expect the same cache entry.

Do not force every test to use `@SpringBootTest` just to reduce unique contexts. A small slice context starts fast and provides clear isolation; sometimes multiple small contexts are better than one heavy, complex full context.

### 11.3. WebEnvironment makes a difference

`@SpringBootTest(webEnvironment = MOCK)` typically uses a mock servlet environment (if the web stack is on the classpath); `RANDOM_PORT` runs an embedded server. Context characteristics differ and can affect the key; you cannot assume reuse between the two modes.

If a test only needs service/repository auto-config, choose `webEnvironment=NONE` to avoid starting web infrastructure. However, do not choose `NONE` for tests that need to verify HTTP filters, container ports, or real servlet network flows.

## 12. @MockitoBean, @MockBean, and mock reset

### 12.1. Bean override is part of the key

Spring Framework 6.2 supports `@MockitoBean` and `@MockitoSpyBean`. Bean override configuration is a context customizer; thus two tests with different mock targets/qualifiers can produce different cache keys.

Spring Boot `@MockBean`/`@SpyBean` were deprecated starting in Boot 3.4, in favor of Framework `@MockitoBean`/`@MockitoSpyBean` in Boot 3.5. If a project still uses the legacy annotations, Boot test support can also affect context customizers.

**Do not use different mock field names unnecessarily** when the field name acts as the fallback qualifier in the annotation: Spring Framework docs note that field names/qualifiers can cause different cache keys. Standardize field/target bean names for mocks with the same intent when sharing is desired.

### 12.2. Resetting a mock is not reloading the context

Normally, Spring TestContext/Mockito test listeners can reset mocks between test methods based on the reset mode, clearing old stubbings/interactions. This does **not** mean closing the ApplicationContext. The mock bean remains inside the shared context; only its state is reset.

Check the exact API/version and lifecycle when a project customizes listeners or reset modes. If tests still use `@DirtiesContext` after every mock interaction, evaluate whether mock reset/clear invocations can be used instead to preserve the cache.

### 12.3. Overriding does not verify original infrastructure

A test using a mock service bean removes the service's real behavior, including transactions/retries/caching advice depending on the override strategy. Different cache configurations are not just about speed; they also affect the scope of behavior under test. If you want to verify a real service or DB transaction, use a test that does not override the target under test.

## 13. @DynamicPropertySource, Testcontainers, and @ServiceConnection

Testcontainers typically provides mapped ports/URLs known only after the container starts. Spring test offers:

```java
@DynamicPropertySource
static void registerDatabase(DynamicPropertyRegistry registry) {
    registry.add(
            "spring.datasource.url",
            POSTGRES::getJdbcUrl);
}
```

This is a **snippet**, assuming a static Postgres container `POSTGRES` and dependencies; it is not part of the runnable demo.

### 13.1. Hidden reuse issues when the dynamic supplier changes

Two test subclasses may inherit the same `@DynamicPropertySource` method while using different static container instances/endpoints per subclass. The cache key includes the method customizer metadata; **if the method identity is the same**, it does not automatically key on the URL returned by the supplier during each test.

The consequence can be a reused context with DataSources/clients already initialized with the old URL. Solutions depend on the goal:

- Use a stable container lifecycle, sharing a single endpoint for classes intended to share.
- Separate context configurations/dynamic methods when endpoints must differ.
- Use `@DirtiesContext` on the base/fixture class when values actually change between subclasses, per Spring docs.
- Or configure a test environment with a stable source if the contract permits.

Do not add a random property to every test just to avoid reuse if the goal is the same database/container; doing so increases contexts and consumes memory.

### 13.2. @ServiceConnection in Spring Boot

Spring Boot 3.5 includes Testcontainers `@ServiceConnection`. Spring Boot test support creates connection details and context customizers for appropriately annotated containers. Configuring different containers can make context configurations differ, but **do not** assume the cache key always includes the mapped random port as a literal. Understand lifecycle/container ownership and test context reuse before sharing static/reusable containers.

### 13.3. Container stops while the context remains cached

A common source of flakiness:

1. Test class A starts a static Testcontainers DB.
2. Spring context initializes a DataSource pointing to container A.
3. A JUnit extension stops container A after class A.
4. Test class B has configuration metadata that can reuse context A, but the DataSource still points to the stopped container's endpoint.

This can be managed via a container lifecycle tied to the Spring context, an appropriately scoped shared singleton container, properly scoped `@DirtiesContext`, or proper Boot service connection integration. Do not assume the context cache knows that a Docker container has stopped.

## 14. Shared context carries shared state

Cache reuse is a performance optimization **and** a reminder about test isolation.

### 14.1. Different types of state

| State | Can context reuse retain it? | Appropriate cleanup approach |
|---|---|---|
| Singleton bean mutable fields | Yes | Deliberate bean reset or stateless design |
| In-memory CacheManager | Yes | Evict test cache entries / clear |
| Mockito stubbings/invocations | Yes if not reset | Framework mock reset/listener |
| ThreadLocal/MDC | Can leak via thread reuse | try/finally remove, test cleanup |
| Static fields | Yes within same JVM, independent of context | Clear explicitly; avoid shared global state |
| Embedded DB data | Depends on DB lifecycle/transactions | Rollback, @Sql cleanup, truncate fixtures |
| External database/Kafka | Not in context cache, but clients hold connections | Unique fixtures, transaction/cleanup, consumer group isolation |
| Bean definitions/scope/proxy | Context retains until dirty/closed | Avoid mutating; @DirtiesContext if truly unrecoverable |
| HTTP port/server sockets | Tied to web app context lifecycle | Manage @SpringBootTest webEnvironment and context lifecycle |

**Do not treat `@Transactional` in tests as "reset everything".** Rollback typically applies only to the transaction on the same thread/data source per the test mechanism. It does not automatically reset singleton in-memory state, Kafka messages, remote HTTP actions, or async thread side effects.

### 14.2. Why does the example use try/finally?

In `mutableSingletonStateIsSharedUntilReset`, the test increments `RequestCounter` and then uses `finally { counter.restore(original); }` to restore the state before finishing. Thus the test proves shared state without polluting subsequent methods.

If a test modifies bean definitions or global configuration that cannot be safely reset, use `@DirtiesContext`. If it merely inserts a record into a test DB, rollback/clean fixtures are usually much cheaper.

### 14.3. @TestInstance and cache are two different lifecycles

JUnit Jupiter creates a test instance per method by default, unless `@TestInstance(PER_CLASS)` or other configuration is used. The Spring ApplicationContext cache has a lifecycle tied to configuration/JVM. **A new Java test object does not mean a new Spring bean**.

Similarly, `@BeforeEach` runs for every method, whereas a singleton bean's `@PostConstruct` runs only when the bean/context is newly created. Do not write assertions like "PostConstruct must run N times equal to the number of `@Test`s" when caching is enabled.

## 15. LRU, context hierarchy, and failure threshold

### 15.1. LRU eviction is not @DirtiesContext

- **LRU:** the cache automatically closes the least recently used entry if the number of contexts exceeds max.
- **@DirtiesContext:** the test explicitly declares the context is no longer safe.
- **JVM shutdown:** the static cache disappears with the process, and live contexts are closed per framework mechanisms.

A context evicted by LRU does not prove a test dirtied it; it may simply be cache capacity pressure.

### 15.2. Context hierarchy

When `@ContextHierarchy` creates parent/child contexts, the key includes parent metadata. Dirtying a child context can affect multiple hierarchy branches under the default exhaustive strategy; `hierarchyMode=CURRENT_LEVEL` can narrow the scope when appropriate.

Do not apply `CURRENT_LEVEL` unconditionally if ancestor state was also modified. Per Spring docs, `@MockitoBean` and `@MockitoSpyBean` apply to levels by default in some hierarchy setups; use `contextName` if you must target a specific level.

### 15.3. Context failure threshold (since Spring Framework 6.1)

Spring Framework has a default **failure threshold** of **1** per cache key. If loading a context fails due to configuration, subsequent attempts with the same key in the same suite can be **skipped preemptively** with an `IllegalStateException` instead of spending time starting up and failing again.

JVM property:

```text
-Dspring.test.context.failure.threshold=1
```

This is a **policy to avoid repeating context startup failures**, not caching of a successful ApplicationContext. When seeing "ApplicationContext failure threshold exceeded", look for the **first startup failure** of the same key rather than assuming the later test has its own separate bug. After fixing the config error, re-run the suite/process and verify.

Do not raise the threshold very high to mask a configuration failure's root cause; only adjust it intentionally when debugging transient external dependencies.

## 16. Diagnosing "why does the context keep restarting?"

### 16.1. Ordered checklist

1. Verify whether the tests run in the same JVM/test worker.
2. Identify whether each test uses `@SpringBootTest`, `@WebMvcTest`, or another slice.
3. Compare `classes`/locations/loader/initializers.
4. Compare `@ActiveProfiles`, profile resolvers, and inline test properties.
5. Compare `@TestPropertySource` resource paths and inline properties.
6. Compare `@MockitoBean`/`@MockBean`/`@TestBean` targets, field names, and qualifiers.
7. Compare `@DynamicPropertySource` method registrations and Testcontainers config.
8. Check `@DirtiesContext` (method/class, inheritance, and meta-annotations).
9. Check LRU cache max size and potential cache thrashing.
10. Enable `org.springframework.test.context.cache` DEBUG logging and read hit/miss/size.
11. Inspect startup logs/callbacks and JUnit reports to see whether time is spent in the context or test fixtures.
12. Optimize one factor with evidence; do not alter security/db wiring just to reduce context count.

### 16.2. Troubleshooting table

| Symptom | Common cause | Resolution |
|---|---|---|
| Every test class prints the Boot banner/startup | Different keys or JVM forks | Compare configs/JVMs, debug cache |
| Same @SpringBootTest but no reuse | Different inline properties/profile/mocks | Standardize what is truly equivalent |
| Renaming a mock field adds a context | Bean override fallback qualifier | Use stable field names/explicit qualifiers |
| Testcontainers random port changes, context still uses old URL | Dynamic source method same key but value/lifecycle changes | Stable container owner, dirty/separate key when needed |
| Context closed after test class | @DirtiesContext(AFTER_CLASS) | Remove when not actually dirtying context |
| Cache size frequently hits 32 | Many unique configs, LRU evictions | Reduce unique keys; tune maxSize if RAM permits |
| Increased maxSize but suite remains slow | Bottleneck in DB migration/setup or memory | Measure per phase; do not optimize blindly |
| 401/403 differs across tests | Different profiles/security mocks/filters | Do not force context reuse against test contract |
| Singleton counter retains previous test's value | Reused context retains bean state | Reset/clear/rollback appropriately |
| @Transactional rolls back but cache still dirty | Non-DB singleton/static/async state | Reset the actual resource, not just DB rollback |
| Test 2 gets context load preemptively skipped | Failure threshold=1 after first error | Find the first root startup error |
| Cache hit count does not equal test method count | Multiple lookups per test | Read stats as indicators, not method counts |
| Single class fast in IDE, CI suite slow | Forks/parallel/cache thrash/fixtures | Compare worker processes, suite config |
| CI runs multiple forks without sharing cache | Static cache is per process | Accept isolation/performance tradeoff |
| TestContextManager demo loads context early | Explicit getApplicationContext call | Understand this is for inspection, not production workflow |
| @WebMvcTest context differs from full Boot | Different slice metadata | Do not force same-key across different scopes |
| Context hierarchy dirty causes many reloads | Default exhaustive hierarchy dirtiness | Check hierarchyMode and ancestor behavior |
| Adding @TestConfiguration in every class | Different context customizer | Reuse shared fixture config if semantics match |
| Flaky due to shared singleton state | Tests lack cleanup | Add reset(), state-independent fixtures |

## 17. Optimizing test suite design without changing behavior

### 17.1. Standardize configurations with identical intent

If 30 classes need the exact same application profile, you can create a meta-annotation:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@SpringBootTest(
    classes = MyApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = "feature.mode=test"
)
@ActiveProfiles("integration")
public @interface IntegrationTestConfig {}
```

This is an **illustrative snippet**, requiring imports, the application class, and a separate Java annotation source file. Using a meta-annotation is optional; the goal is to keep configuration metadata consistent.

However, do not merge two profiles or properties if they represent different business behavior. **Correctness first, cache hits second.**

### 17.2. Use slices/runners when beneficial

- Unit tests for pure Java services: no Spring ApplicationContext needed.
- `ApplicationContextRunner` for custom auto-configuration conditions: fast and explicitly creates small contexts; this is **a separate kind of context test**, not proof of sharing Spring TestContext's static cache with `@SpringBootTest`.
- `@WebMvcTest` for the controller slice, `@DataJpaTest` for the repository slice.
- `@SpringBootTest` for full integration behavior.
- `RANDOM_PORT` when real HTTP/servlet container behavior must be verified.

A full-context cache hit can make subsequent startups cheap, but it does not compensate for a test mocking the wrong layer or skipping validations.

### 17.3. Do not use @DirtiesContext as @AfterEach

If a test only mutates database data, use transaction rollback or `@Sql` cleanup. If a bean holds an in-memory cache, invoke controlled eviction/clear. If a mock is stubbed, rely on framework mock reset. `@DirtiesContext` should only be chosen when the context genuinely cannot be safely reused.

### 17.4. Optimize through measurement

A plan:

1. Run a baseline suite on the same CI worker with timing logs.
2. Enable TestContext cache DEBUG, collect size/hits/misses.
3. Record actual application starts, test JVM forks, and `@DirtiesContext` usages.
4. Identify test groups that differ only due to unnecessary properties/fixtures.
5. Consolidate truly equivalent metadata (without changing behavior).
6. Verify singleton/shared state has proper cleanup.
7. Re-run the exact same suite, comparing elapsed time, pass/fail/skipped, and RAM.
8. Only increase `maxSize` if eviction is the bottleneck and memory allows.

A high cache hit rate is not the sole goal: if poor isolation makes tests flaky or hides bugs, high speed is untrustworthy.

## 18. Practice questions with answers

### A. Two differently named classes, same @SpringBootTest

Can they share an ApplicationContext?

**Yes**, if the effective configuration key is equivalent, they run in the same test JVM, and the context has not been dirtied/evicted. Test class name itself is not an independent key component.

### B. Same class, two @Test methods

Must the context be created twice?

**Usually no.** Spring TestContext reuses the context; the JUnit test instance may be new per method, but Spring singleton beans remain the same.

### C. Changing @ActiveProfiles("test") to "ci"

Why is the context different?

**Because activeProfiles participates in the key.** Two profiles can produce different beans/configurations, so sharing is not forced.

### D. Each class adds a random inline property

What is the consequence?

**It can create many unique keys**, reducing hit rate and causing LRU eviction. Only generate random names/ports in configuration when tests truly require that isolation.

### E. @DynamicPropertySource supplier returns a different port

Does it automatically create a different key each time?

**There is no such guarantee.** Method/customizer metadata participates in the key; runtime values are not automatically used as unique keys. Container lifecycle and context dirtiness must be managed.

### F. Adding @MockitoBean to one class

Can it break cache reuse?

**Yes.** The bean override context customizer participates in the key, including target/qualifier metadata. Use consistent mock declarations when classes genuinely need the same configuration.

### G. A @DirtiesContext on a method

What happens after the test finishes?

Under `AFTER_METHOD`, the cached context is evicted/closed; the next method/test needing the same configuration will load a new context.

### H. Test mutates a mutable singleton counter

Does reusing the context automatically reset the counter?

**No.** Manual reset/fixtures are required, or dirtying the context if it cannot be safely restored.

### I. Same key but running in two forked JVMs

Do they share the same ApplicationContext instance?

**No.** The static cache is per-process.

### J. Cache reaches 33 entries at default maxSize 32

What happens?

The default cache uses LRU eviction and closes the least recently used entry to stay within the size limit. A test needing an evicted entry will reload it.

### K. Increasing maxSize from 32 to 64

Does it always improve performance?

**No.** If there are fewer than 32 unique keys or the bottleneck is DB fixtures/test operations, increasing it will not help. If RAM is constrained, it can also cause memory pressure.

### L. Context load error repeats across many classes

Why do later failures report threshold exceeded?

Spring Framework 6.1+ has a default failure threshold of 1 per key. It avoids retrying a broken context repeatedly; find the **first** startup error.

### M. Does @TestInstance(PER_CLASS) mean per-class cache?

**No.** That is the lifecycle of the JUnit test object; the Spring context cache is independent and can be shared across multiple test classes.

### N. Does context cache reuse roll back database records?

**No.** The database transaction test listener/rollback and cleanup fixtures are separate mechanisms. The context cache only retains the container/beans.

### O. Context is not shared between @WebMvcTest and @SpringBootTest

Is this a bug?

**No.** The two test scopes/configuration metadata usually differ. Choose the right layer instead of forcing hits.

## 19. QA checklist for context cache and performance

- [ ] Distinguished context loading from test method execution.
- [ ] Understood the key is MergedContextConfiguration, not simply class name.
- [ ] Reviewed profiles, inline properties, TestPropertySource, and customizers.
- [ ] MockitoBean/MockBean qualifiers and field names are named consistently.
- [ ] DynamicPropertySource methods/values/container lifecycles are clearly managed.
- [ ] Did not assume ServiceConnection random port automatically creates a unique context key.
- [ ] Same JVM/test worker when expecting static cache sharing.
- [ ] Reviewed Maven/Gradle forks/parallel workers.
- [ ] Not applying @DirtiesContext by default to every method.
- [ ] Using @DirtiesContext when the shared context is genuinely unsafe.
- [ ] Singleton bean mutable state is reset or designed to be stateless.
- [ ] Test DB rollback/cleanup is not confused with context refresh.
- [ ] ThreadLocal/static/mock state has appropriate cleanup.
- [ ] Not asserting absolute UUIDs/startup logs/hit counts that depend on test order.
- [ ] Checked TestContext cache DEBUG statistics before increasing maxSize.
- [ ] Aware of default maxSize 32 and LRU policy.
- [ ] Property maxSize is set on the test JVM early enough.
- [ ] Sufficient RAM available if increasing maxSize.
- [ ] Understood context failure threshold differs from successful context caching.
- [ ] Not treating preemptively skipped context loads as the root cause.
- [ ] @ContextHierarchy and hierarchyMode considered when dirtying parent/child.
- [ ] Not forcing reuse of contexts with actually different configuration requirements.
- [ ] Not converting all slice tests into full Boot tests just to share one key.
- [ ] Measured suite time, memory, context miss/hit, and test correctness together.
- [ ] Test methods run independently without relying on shared-state order.
- [ ] CI report shows executed/passed/failed/skipped counts, not just a green build.
- [ ] Java 17+/Boot 3.5/Spring 6.2 imports match the target version.
- [ ] Not using manual demo TestContextManager in production test code when SpringExtension suffices.
- [ ] Lifecycle strategy in place if contexts hold thread pools/connections/container services.
- [ ] No credentials, production endpoints, or PII exposed in cache/debug logs.

## 20. Conclusion

**The Spring TestContext cache reuses the exact ApplicationContext instance by a configuration key**, within a static cache belonging to the JVM running the tests. Two test classes with different names but identical metadata can share a context and singleton beans; changes to profiles, properties, context customizers, bean overrides, or environment scope can produce a different key.

- The cache defaults to **maxSize 32** and evicts via **LRU**.
- `@DirtiesContext` explicitly closes/removes the context; do not use it in place of normal DB/mock/state cleanup.
- `@MockitoBean`, `@DynamicPropertySource`, test slices, and Testcontainers config must be examined when debugging cache misses.
- Forked JVMs do not share the static cache.
- Context reuse improves startup performance but **retains singleton state**, so test isolation is a mandatory companion.
- Inspect debug cache statistics and measure actual execution time rather than extrapolating from a small test run.

The Java 17+ example suite and 9 JUnit tests provide direct proof via object identity that matching keys are reused, differing metadata produces different contexts, and `@DirtiesContext` causes a context reload. For complex systems, combine these insights with profiling DB, Testcontainers, and web/server startup to optimize the true bottleneck.

## Official References

- [Spring Framework 6.2 — Context Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): configuration cache key, static JVM cache, default 32/LRU, stats/debug, shutdown.
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html): class/method modes, eviction, hierarchy mode.
- [Spring Framework 6.2 — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/failure-threshold.html): default threshold 1 since Framework 6.1.
- [Spring Framework 6.2 — Bean Override with @MockitoBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): bean override, qualifiers, field names, and context cache.
- [Spring Framework 6.2 — Dynamic Property Sources](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): @DynamicPropertySource and dynamic values.
- [Spring Framework 6.2 — TestContextManager API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/TestContextManager.html): getTestContext, beforeTestClass, afterTestClass.
- [Spring Framework 6.2 — Context Hierarchies](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/hierarchies.html): parent/child metadata and hierarchy eviction.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): @SpringBootTest, webEnvironment, slices, and test configuration.
- [Spring Boot 3.5 — MockitoBean/MockBean migration](https://docs.spring.io/spring-boot/3.5/api/java/org/springframework/boot/test/mock/mockito/MockBean.html): deprecated legacy Boot mock annotation.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): @ServiceConnection and container-related test configuration.
- [Spring Boot 3.5 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/getting-started.html): Gradle plugin 3.5.16 and build setup.
