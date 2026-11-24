# `@DirtiesContext` and the Cost of Rebuilding the Application in Spring Boot Tests

## 1. The problem: one annotation line can slow down the entire test suite

Suppose a Spring Boot project has 300 integration tests. Every test class declares `@SpringBootTest`, connects to repositories, initializes security, configures Jackson, migrations, message listeners, or clients. You notice a test mutating a field on a singleton bean, causing the next test to occasionally fail. To "be sure it is clean", someone adds `@DirtiesContext` to **every class**. Tests may become less dependent on leftover state, but Spring has to **close and rebuild the ApplicationContext** many times; CI duration increases even when service code stays unchanged.

This is not a black-and-white question of "whether to use the annotation or not". `@DirtiesContext` is the right tool **when the context genuinely can no longer be safely reused**. The key is distinguishing:

- **Context cache**: Spring TestContext Framework retains a loaded `ApplicationContext` for tests with the **same configuration** within the same JVM.
- **Mutable test data/state**: data in a DB, message queue, static fields, or singletons can persist across tests; that state **does not automatically clean itself** simply because a test method finished.
- **`@DirtiesContext`**: instructs Spring to **remove the context from the test context cache and close it** at a specified phase. The next test needing the same context key must build a new context.
- **Restart cost**: component scanning, `BeanFactory`/auto-configuration, bean instantiation/post-processing, proxying, connection pools, JPA EntityManagerFactory, Liquibase/Flyway, embedded web server, and integration resource lifecycles may all have to run again.
- **Lighter reset alternatives**: transaction rollback, `@Sql`, fixture resets, `Mockito` mock resets, cache clearing, proper resource closing; these usually clean **data** without tearing down the entire **ApplicationContext**.

**Learning objectives** (parent group: *Context cache and performance*):

1. Understand the Spring TestContext cache, context keys, reuse, LRU eviction, and single-JVM scope accurately.
2. Understand how `@DirtiesContext` differs from `@Transactional`, `@Rollback`, `@Sql`, `@AfterEach`, and `@MockBean` reset.
3. Master the **two method modes** and **four class modes**, and when the context closes before/after a method/class.
4. Distinguish `@DirtiesContext` **on a method** vs. **on a class**; note how modes can be combined.
5. Understand `hierarchyMode = EXHAUSTIVE/CURRENT_LEVEL` when using `@ContextHierarchy` to avoid accidentally evicting multiple branches.
6. Know why Spring Boot 3.3 `@MockBean`, `@ActiveProfiles`, `@TestPropertySource`, `@SpringBootTest(properties=...)`, and `@DynamicPropertySource` can affect cache keys.
7. Build a **runnable Java 17 / Spring Boot 3.3.5 / JUnit Jupiter project** that accurately observes **bean instance identity** and `@PreDestroy` callbacks.
8. Include **14 JUnit `@Test` methods**, testing reuse, `AFTER_METHOD`, `BEFORE_METHOD`, `BEFORE_EACH_TEST_METHOD`, `AFTER_EACH_TEST_METHOD`, `AFTER_CLASS`, and differing cache keys.
9. Know how to **measure** context cache hits/misses, context startup, and suite runtime before optimizing; avoid fabricating seconds or writing flaky timing assertions.
10. Understand limitations involving out-of-JVM DBs, Testcontainers, real web servers, parallel tests, and Gradle forks.
11. Formulate a suite performance optimization strategy without sacrificing per-test independence.

**Pinned versions:** Java **17**, Spring Boot **3.3.5**, Spring Framework **6.1.x**, JUnit Jupiter. The example opens no HTTP server, no Docker, and no DB; sections on databases, JPA, Spring MVC, and Testcontainers are **supplementary application guidance**, not claimed to be exercised by the small test code.

## 2. Spring TestContext caching mechanism: same configuration, not necessarily same class

When a test uses `@SpringBootTest` or `@ContextConfiguration`, Spring TestContext looks up an `ApplicationContext` in the **static cache** of the JVM running the tests. If the cache holds an entry matching the **context cache key**, Spring reuses the context and its bean instances. If not, the framework initializes the context, adds it to the cache, and supplies it to the test.

~~~text
Test A -- key K1 --> cache miss --> load AppContext #1
Test B -- key K1 --> cache hit  --> reuse AppContext #1
Test C -- key K2 --> cache miss --> load AppContext #2
Test D -- key K1 --> cache hit  --> reuse AppContext #1
Test E -- key K1 --> @DirtiesContext AFTER_METHOD
                           |
                           +--> evict K1 + close #1
Test F -- key K1 --> cache miss --> load AppContext #3
~~~

**The cache key** is not merely the test class name. The framework computes the key from configuration components such as:
- `locations` and `classes` of `@ContextConfiguration`.
- `contextInitializerClasses`.
- `contextCustomizers`: e.g., Boot test customizers, `@DynamicPropertySource`, `@MockBean`/`@SpyBean` (Spring Boot 3.3); other bean overrides in newer versions.
- `contextLoader`.
- `parent` when using `@ContextHierarchy`.
- `activeProfiles` from `@ActiveProfiles`.
- `propertySourceDescriptors`/`propertySourceProperties` from `@TestPropertySource`, `@SpringBootTest(properties=...)`.
- `resourceBasePath` for web application contexts.

Two test classes with the same `@SpringBootTest` and environment can share a context. Two similar-looking classes where one adds `@ActiveProfiles("qa")`, an extra mock bean, or a different inline property can produce **two cache keys**, even without `@DirtiesContext`.

**Do not use `ApplicationContext.getId()` as proof that a new instance was built.** A new context can be assigned the **same ID string** from the application name. In this lesson, we use a `UUID` generated in a Spring singleton bean's constructor and `@PreDestroy` events to observe identity/lifecycle.

### 2.1. The cache belongs to Spring test, not @Cacheable or business caching

`ContextCache` holds **ApplicationContext instances**. It is not a Redis cache, Hibernate second-level cache, or service `@Cacheable` results. `@DirtiesContext` closes the **entire container**, not just `cacheManager.clear()`. A test needing to clear a business cache does not automatically need to dirty the context.

**Example:** You added a record to an in-memory cache to test invalidation logic. Instead of:
~~~java
@DirtiesContext
@Test
void cacheInvalidation() { ... }
~~~

consider clearing that specific cache in `@BeforeEach`/`@AfterEach`, or using a dedicated fixture, if the context and bean definitions remain intact. The snippet above only illustrates annotation placement; it is not a standalone method.

### 2.2. LRU, default max size 32, and single-JVM scope

Spring Framework 6.1 defaults to **context cache max size = 32**. When exceeded, a **Least Recently Used (LRU)** policy evicts and closes the least recently used context. It can be adjusted with **JVM system property** `spring.test.context.cache.maxSize`, e.g., 16 or 64 after measurement.

**Do not confuse** `spring.test.context.cache.maxSize` with a normal application's `application.properties` setting: it is a **system property / `SpringProperties` setting of the Spring TestContext framework**, read in the test JVM. The Gradle example in section 6 configures `systemProperty` on the `test` task.

If Gradle spawns multiple **forked JVMs**, each JVM has its own static cache and does not share bean instances or hits/misses. `forkEvery=1` or multiple test workers can prevent cross-class reuse even with identical configs. Likewise, when an IDE runs each test class in its own process, reuse from a previous run cannot be expected.

**LRU eviction does not mean `@DirtiesContext` was invoked.** Both mechanisms can close a context, but for different reasons. Inspect logs/cache stats to distinguish them.

### 2.3. Cache failure threshold is a separate concept

Starting in Spring Framework **6.1**, `spring.test.context.failure.threshold` (default **1**) limits how many times loading a failing context is attempted for the **same cache key**, preventing dozens of tests from repeatedly trying to boot a broken context. Later tests may receive an `IllegalStateException` stating the context load attempt was skipped.

This is **not cache size**, **not startup duration**, and **not `@DirtiesContext` auto-fixing an error**. When hitting the failure threshold, investigate the **very first initialization error** (unreachable DB, bean config, migration, bad property) rather than raising the threshold or dirtying contexts blindly to mask the cause.

## 3. What does `@DirtiesContext` actually do?

The `org.springframework.test.annotation.DirtiesContext` annotation informs TestContext that the **associated ApplicationContext has been "dirtied"** — for instance, the test mutated a singleton bean, a bean definition, or state that other tests cannot safely reset. The framework will **remove it from the context cache and close the context** at the configured phase. The next time a test needs the same context key, a new instance is created.

~~~text
Test method uses Context A
       |
       +-- alters state that cannot/should not be manually reset
       |
       +-- marked dirty per @DirtiesContext
                 |
                 +-- Spring TestContext removes cache entry
                 +-- Context A.close()
                 |      - @PreDestroy / DisposableBean / lifecycle callbacks
                 |      - destroys singleton beans, context-owned pools/resources
                 +-- Next test needing that key -> builds Context B
~~~

**It is not "reset beans in-place".** Spring does not call some `reset()` method on existing beans and reuse the old instance. It closes the old container; recreated beans are brand new instances. Context creation can cost far more than resetting a few rows in a test database.

**It does not guarantee resetting external state.** If the context uses an external PostgreSQL database, Kafka/RabbitMQ broker, or a static Testcontainers container, closing the Spring context **does not automatically wipe all tables, topics, queues, or files**. Resources whose lifecycle lives **outside** the context may persist. Do not pick `@DirtiesContext` just to "wipe data" without verifying the actual owner of that state.

**It does not mean a test fails.** `@DirtiesContext` is not an assertion. It can run even when a test PASSes, changing context lifecycle for subsequent tests.

### 3.1. Default annotation behavior

~~~java
// At method level:
@DirtiesContext
@Test
void someTest() {
    // Default methodMode = AFTER_METHOD
}
~~~

~~~java
// At class level:
@DirtiesContext
@SpringBootTest
class SomeTests {
    // Default classMode = AFTER_CLASS
}
~~~

These two snippets illustrate annotation usage, not standalone runnable classes. The **default** difference is critical: a method dirties **after the method**, while a class dirties **after the entire class**. Never assume putting `@DirtiesContext` on a class loads a fresh context before **every** test method.

### 3.2. All six timing phases

| Level | Parameter | Mode | Behavior |
|---|---|---|---|
| Method | `methodMode` | **`AFTER_METHOD`** (default) | After the current method, close/evict the context; next test reloads if needing the same key |
| Method | `methodMode` | `BEFORE_METHOD` | Before the current method, evict any existing cached context so the method gets a new context |
| Class | `classMode` | **`AFTER_CLASS`** (default) | After the entire test class, evict/close the context |
| Class | `classMode` | `BEFORE_CLASS` | Before the class, start from a new context if the key was already cached |
| Class | `classMode` | `BEFORE_EACH_TEST_METHOD` | Before **each** method, evict/close any previous context and load a fresh one for the method |
| Class | `classMode` | `AFTER_EACH_TEST_METHOD` | After **each** method, evict/close the context; the next method needs a new context |

**Standard syntax:**

~~~java
@DirtiesContext(
        methodMode = DirtiesContext.MethodMode.BEFORE_METHOD)
@Test
void useFreshContext() { ... }
~~~

~~~java
@DirtiesContext(
        classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
@SpringBootTest
class ExpensiveTestClass { ... }
~~~

These are illustrative snippets, not standalone compilable code. At class level you must use `classMode`; at method level you must use `methodMode`. Setting `methodMode` on a class-level annotation or `classMode` on a method **does not take effect for the intended phase**.

**Combining modes:** You can place the annotation on both the class and a method; Spring honors both phases. For instance, class `BEFORE_EACH_TEST_METHOD` plus a method `AFTER_METHOD` can close the context both before and after that method — very expensive. Avoid stacking annotations without a reason.

### 3.3. `BEFORE_*` and dependency injection

When a context is dirtied **before a method**, Spring TestContext runs supporting listeners and handles **re-injection** as needed. In Boot 3.3/Framework 6.1, `DirtiesContextBeforeModesTestExecutionListener` and `DependencyInjectionTestExecutionListener` coordinate by listener order so injected test fields point to the new context. That is why this lesson can use `@Autowired StateProbe` in `BEFORE_METHOD`/`BEFORE_EACH_TEST_METHOD` tests.

**Do not cache a Spring bean reference in a static test field and try to use it after the context closes.** The old bean may have received `@PreDestroy` and pools may be closed; invoking it can fail or produce false green tests if the bean lacks state checks. Store an **immutable marker String** from the old bean for comparison, rather than keeping the reference as if it were a live service.

## 4. Why can context rebuilds be so expensive?

A `@SpringBootTest` using a **full application context** may:
- Scan classes and process `@Configuration`, `@Conditional`, `@ConfigurationProperties`, and auto-configuration.
- Instantiate singleton beans, AOP proxies (`@Transactional`, `@Async`, security method interceptors), and validation providers.
- Initialize Jackson `ObjectMapper`, Hibernate ORM `EntityManagerFactory`, connection pools, and caches.
- Start an embedded HTTP server if using `webEnvironment = RANDOM_PORT`, binding a new socket/port.
- Run Flyway/Liquibase migrations or DB initialization, depending on configuration.
- Start message listeners, schedulers, clients, and observability exporters.
- Provision queue/broker resources or start Testcontainers if wired into bean lifecycle/config.
- Execute `@PostConstruct`, `InitializingBean`, `SmartLifecycle`, and startup events.
- Register and tear down resources in `@PreDestroy`/`close()` when the context closes.

**Measured cost = number of context loads × actual startup cost + context close time + resource side effects.** This is an intuitive model, not an exact arithmetic formula (load cost depends on JVM warmup, classloading, resource reuse, parallelism, OS, DB). A tiny app can rebuild very quickly; a system using JPA/Testcontainers/migrations can be noticeably slow. Never quote a fixed number like "each `@DirtiesContext` costs N seconds" without measuring on the real project.

Theoretical comparison example:

~~~text
10 test classes with the same cache key, 5 methods each:

No dirtying:
  Context #1 loads once
  50 test methods share context #1
  (Each method must still reset data properly!)

Dirty AFTER_CLASS on every class:
  Context #1 loads before class 1 -> closes after class 1
  Context #2 loads before class 2 -> closes after class 2
  ...
  At least 10 context loads if all share the same key.

Dirty AFTER_EACH_TEST_METHOD on every class:
  Each method finishes -> context is closed
  Context is reloaded for the next method.
  Potentially ~50 context loads for 50 methods.

The numbers above are load counts under hypothetical config,
not measured timings, and exclude LRU/parallel/forks.
~~~

**The `BEFORE_EACH_TEST_METHOD` case:** The context may be evicted before every method, including a fresh load for the test instance prior to the phase; exact load counts depend on lifecycle/injection details. Do not assume startup counts always equal exact method counts across all configurations/runners; read cache stats and runtime logs.

### 4.1. `@SpringBootTest` does not open a real server by default

Boot `@SpringBootTest` defaults to a **MOCK web environment** when Spring MVC is on the classpath; it does not open a real TCP HTTP server. Only `@SpringBootTest(webEnvironment=RANDOM_PORT)` starts an embedded server on a random port. The runnable project uses **`WebEnvironment.NONE`** to isolate context rebuild effects and avoid unnecessary HTTP server overhead.

**Do not use `@DirtiesContext` to "reset the port"** if the only requirement is sending another test request: Spring MVC `MockMvc` needs no server port. Conversely, if a test genuinely modifies bean definitions/server configuration, context isolation is valid.

### 4.2. Some hidden costs

- **Restarting listeners/schedulers:** Unstopped background threads leave the old task running alongside the new context; check lifecycle rather than just increasing dirty counts.
- **Closing connection pools:** A closed context can cause an in-flight async request from the prior test to hit a closed connection. Ensure async tasks finish and clean up before dirtying.
- **Varying test properties:** Each `@SpringBootTest(properties=...)` combination creates a distinct key, potentially triggering unexpected context loads.
- **Mocks in cache keys:** Two classes with different sets of `@MockBean` in Boot 3.3 will not share a context. Avoid creating pointless mock overrides per class.
- **Context hierarchy:** Dirtying one branch with `EXHAUSTIVE` can affect other contexts sharing an ancestor.
- **LRU churn:** If a suite requires >32 distinct configurations, older contexts get evicted even without dirty annotations.
- **Gradle forks:** Each fork starts a fresh cache; do not assume startup logs in fork A warmed up fork B.

## 5. When is using `@DirtiesContext` legitimate?

Cases where it **may genuinely be needed**:

1. The test **alters bean definitions** or `BeanFactory` in a way that cannot be reverted.
2. The test mutates complex state on a singleton bean with no safe reset API, and subsequent tests require startup state.
3. The test touches Spring-managed context resources such as JMX MBean registration and needs container cleanup to avoid name conflicts (Spring Boot has a JMX + DirtiesContext example).
4. The test alters application configuration/runtime environment tightly coupled to the context without reliable per-test rollback/isolation.
5. A `@ContextHierarchy` test needs to isolate a specific context branch and understands the consequences of `hierarchyMode`.
6. The test is verifying **context startup/shutdown lifecycle**; dirtying is the exact behavior under test.

Cases where it is usually **NOT needed**:

1. **Inserting/updating DB rows**: use transaction rollback, `@Sql`, fixture cleanup, or isolated databases/schemas.
2. **Mockito mock stubbing/calls**: reset mocks between tests; Boot 3.3 `@MockBean` supports auto-reset after each test method by default.
3. **`@Cacheable` data**: clear the specific cache key or `CacheManager`.
4. **Static state**: reset the specific static fixture; dirtying a Spring context **does not reset static variables**.
5. **ThreadLocal/MDC/security context**: clear according to test/request lifecycle; dirtying does not guarantee clearing values across all threads.
6. **Messages in an external broker**: purge test queues/topics or use separate names/consumer groups; dirtying does not "wipe the broker".
7. **Files on disk**: use a temporary directory and clean up.
8. **HTTP test client/session**: create a new client or clear cookies/sessions; do not tear down `ApplicationContext` unnecessarily.
9. **Migrations/external test databases**: reset schema/transactions properly; closing the context does not drop an external DB unless lifecycle is configured that way.
10. **Test order dependency**: fix fixture/test isolation instead of adding dirtying to mask dependencies.

**Decision rule:** Ask "exactly which state was tainted?", "who owns that state?", "can it be verifiably reset/rolled back?", "if reset is infeasible, what is the narrowest dirty phase?", and "how much do cache misses/startups increase after the change?".

## 6. Runnable project: Java 17, Spring Boot 3.3.5, 14 JUnit tests

The example features a singleton **`StateProbe`** with:
- `id()`: a **UUID generated when the bean initializes**.
- `generation()`: the number of `StateProbe` constructions in the **current JVM**, useful for observing increments (do not assert absolute numbers).
- `increment()`/`reset()` simulating mutable bean state.
- `@PreDestroy` recording the UUID in a **static set** so tests can prove the old context was actually closed. This static set is purely **test instrumentation**, not business state.

The test suite includes:
- `ContextReuseTest`: 3 tests, reusing the same context; resets the counter rather than dirtying.
- `DirtiesAfterMethodTest`: 2 ordered illustrative tests; the first dirties `AFTER_METHOD`, the next sees a different marker and that the old marker closed.
- `DirtiesBeforeMethodTest`: 2 ordered illustrative tests; the second dirties `BEFORE_METHOD`, illustrating exact semantics with dependency re-injection.
- `DirtiesBeforeEachTest`: 2 tests, fresh context before each method.
- `DirtiesAfterEachTest`: 2 tests, old context closes after each method.
- `DirtiesAfterClassTest`: 1 test in a class with default `AFTER_CLASS`; illustrates code and lifecycle policy.
- `BlueConfigurationTest` and `RedConfigurationTest`: 1 test per class, different properties → different cache keys even **without** dirtying.

**Total: 3+2+2+2+2+1+1+1 = 14 `@Test` methods.**

### 6.1. Directory tree

~~~text
settings.gradle
build.gradle
src/main/java/demo/cache/CacheDemoApplication.java
src/main/java/demo/cache/StateProbe.java
src/test/resources/junit-platform.properties
src/test/resources/application.properties
src/test/java/demo/cache/ContextReuseTest.java
src/test/java/demo/cache/DirtiesAfterMethodTest.java
src/test/java/demo/cache/DirtiesBeforeMethodTest.java
src/test/java/demo/cache/DirtiesBeforeEachTest.java
src/test/java/demo/cache/DirtiesAfterEachTest.java
src/test/java/demo/cache/DirtiesAfterClassTest.java
src/test/java/demo/cache/BlueConfigurationTest.java
src/test/java/demo/cache/RedConfigurationTest.java
~~~

### 6.2. Gradle

**settings.gradle**

~~~groovy
rootProject.name = 'dirties-context-cost-demo'
~~~

**build.gradle**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    // Single test JVM to observe static ContextCache reuse;
    // changing forks breaks cross-class cache sharing.
    maxParallelForks = 1
    forkEvery = 0

    // JVM system property of the TestContext framework.
    systemProperty 'spring.test.context.cache.maxSize', '32'

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**Explanation:** `spring-boot-starter` suffices for Spring `ApplicationContext` and logging, omitting web/JPA so observations focus cleanly on context lifecycle. `starter-test` brings JUnit Jupiter and Spring TestContext. `maxParallelForks=1`/`forkEvery=0` keeps a single test JVM so cache reuse is visible; when production CI needs parallel forks, change intentionally and accept that each worker has its own cache.

**src/test/resources/junit-platform.properties**

~~~properties
junit.jupiter.execution.parallel.enabled=false
~~~

This disables **JUnit Jupiter method/class parallel execution**, preventing one test from dirtying a context while another concurrently retrieves it from the cache. It does not affect application-created threads; it only controls test scheduling in this lesson. This is not advice that "every project must disable parallel tests"; a suite with data isolation and no dirtying/shared mocks can run in parallel. This particular demo needs unobstructed lifecycle observation.

**src/test/resources/application.properties**

~~~properties
spring.main.banner-mode=off
logging.level.org.springframework.test.context.cache=DEBUG
~~~

The `org.springframework.test.context.cache` logger enables hit/miss/cache size statistics and helps explain why contexts are reused. Since Spring TestContext can log before Boot's logging system initializes, some early logs may not appear in an IDE; if complete statistics are needed, configure logging early via the test logging backend and keep a single JVM. In large projects, enabling DEBUG can emit verbose logs; use only during analysis.

### 6.3. Application

**src/main/java/demo/cache/CacheDemoApplication.java**

~~~java
package demo.cache;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CacheDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CacheDemoApplication.class, args);
    }
}
~~~

There is no embedded HTTP server because the project omits `spring-boot-starter-web`, and tests use `WebEnvironment.NONE`.

### 6.4. Bean with identity stamp and close callback

**src/main/java/demo/cache/StateProbe.java**

~~~java
package demo.cache;

import java.util.Set;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;

import jakarta.annotation.PreDestroy;
import org.springframework.stereotype.Component;

@Component
public class StateProbe {

    private static final AtomicInteger CONSTRUCTED =
            new AtomicInteger();

    private static final Set<String> CLOSED_IDS =
            ConcurrentHashMap.newKeySet();

    private final String id = UUID.randomUUID().toString();

    private final int generation =
            CONSTRUCTED.incrementAndGet();

    private final AtomicInteger counter = new AtomicInteger();

    public String id() {
        return id;
    }

    public int generation() {
        return generation;
    }

    public int increment() {
        return counter.incrementAndGet();
    }

    public int count() {
        return counter.get();
    }

    public void reset() {
        counter.set(0);
    }

    public static boolean wasClosed(String id) {
        return CLOSED_IDS.contains(id);
    }

    public static int totalConstructed() {
        return CONSTRUCTED.get();
    }

    @PreDestroy
    void onDestroy() {
        CLOSED_IDS.add(id);
    }
}
~~~

**Why is the marker more reliable than `context.getId()`?** Every **`StateProbe` bean instance** in each context gets a `UUID.randomUUID()`. If the framework creates a new context, it must instantiate a **new `StateProbe` instance**, yielding a different ID. `@PreDestroy` records the old ID in a set when the bean is destroyed; tests can verify closure occurred. UUID collision is negligible for learning purposes, though if absolute reference identity proof is needed you can compare live bean references directly while both are alive (this lesson stores only the ID to avoid retaining references to closed beans).

**Note on static counters:** `CONSTRUCTED`/`CLOSED_IDS` live per JVM and are **not reset when a Spring context is dirtied**. Do not assert `generation()==1` in a test without controlling class execution order; JUnit/Gradle can reorder classes. Use unique markers and **same/different** relationships rather than absolute context creation numbers.

`@PreDestroy` fires when Spring closes/destroys beans owned by the context. It does not mean the JVM unloads classes or static state. Never use `System.gc()` or `finalize()` to verify context closure.

## 7. First test: reuse the same context, reset state manually

**src/test/java/demo/cache/ContextReuseTest.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class ContextReuseTest {

    private static final AtomicReference<String> FIRST =
            new AtomicReference<>();

    @Autowired
    StateProbe probe;

    @Autowired
    ApplicationContext context;

    @BeforeAll
    static void clearLocalObservation() {
        FIRST.set(null);
    }

    @BeforeEach
    void verifyReuseAndResetData() {
        String oldMarker = FIRST.getAndSet(probe.id());

        if (oldMarker != null) {
            assertEquals(
                    oldMarker, probe.id(),
                    "Same class/config should reuse the context");
        }

        assertSame(probe, context.getBean(StateProbe.class));

        // Reset only the test data, do not rebuild the container.
        probe.reset();
    }

    @Test
    void firstOperationUsesFreshData() {
        assertEquals(0, probe.count());
        assertEquals(1, probe.increment());
    }

    @Test
    void anotherOperationIsIndependent() {
        assertEquals(0, probe.count());
        assertEquals(1, probe.increment());
        assertEquals(2, probe.increment());
    }

    @Test
    void thirdOperationDoesNotRequireDirtyContext() {
        assertEquals(0, probe.count());
        assertEquals(1, probe.increment());
    }
}
~~~

**Exactly 3 JUnit `@Test` methods.** This is a useful example when bean state **has a controlled reset API**: each method starts with `counter=0`, while `StateProbe.id()` **stays the same**. No `@DirtiesContext` is needed, avoiding repeated context startups.

`AtomicReference` stores the ID from the previous check to prove reuse **within a non-parallel class**. Tests do not depend on the order of the three test methods: all run `@BeforeEach` to reset data and assert the same context. `@BeforeAll` clears the local observation when the class starts. Other classes in the suite may share the context before/after this class, without interleaving while JUnit parallel execution is disabled.

**Limitation:** This reset is merely resetting an `AtomicInteger` in one bean. With business state spanning multiple caches/DBs/external queues, proper reset can be more complex. If fixture isolation cannot be guaranteed, pick another isolation strategy or dirty intentionally.

## 8. `AFTER_METHOD`: one test dirties, the next gets a fresh context

**src/test/java/demo/cache/DirtiesAfterMethodTest.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class DirtiesAfterMethodTest {

    private static final AtomicReference<String> BEFORE =
            new AtomicReference<>();

    @Autowired
    StateProbe probe;

    @BeforeAll
    static void resetObservation() {
        BEFORE.set(null);
    }

    @Test
    @Order(1)
    @DirtiesContext(
            methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
    void firstTestMarksItsContextDirtyAfterCompletion() {
        BEFORE.set(probe.id());

        probe.reset();
        assertEquals(1, probe.increment());
    }

    @Test
    @Order(2)
    void secondTestGetsRebuiltContext() {
        String old = BEFORE.get();

        assertNotNull(old);
        assertNotEquals(old, probe.id());

        assertTrue(
                StateProbe.wasClosed(old),
                "Old bean must receive @PreDestroy");
        assertEquals(0, probe.count());
    }
}
~~~

**Exactly 2 `@Test` methods.** The first test **does not call `context.close()` itself**: Spring's `DirtiesContextTestExecutionListener` processes the annotation **after the method**, removes the context cache entry, and closes the Spring container. The second test receives a new `StateProbe` without the old instance's `counter=1`. `wasClosed` proves `@PreDestroy` ran on the old bean.

`@TestMethodOrder` is used here solely to **demonstrate the two-step lifecycle intentionally**, not as a recommended pattern for business tests. In real projects, application tests should be order-independent. You can inspect cache behavior via logs and test classes independently instead of building an order-dependent suite.

**Do not infer from "second has counter=0" that dirtying occurred**: a test might simply have reset the counter beforehand. It is specifically the **different marker + closed old marker** that cleanly proves a rebuild in this example.

## 9. `BEFORE_METHOD`: evict context before a specific method

**src/test/java/demo/cache/DirtiesBeforeMethodTest.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class DirtiesBeforeMethodTest {

    private static final AtomicReference<String> EARLIER =
            new AtomicReference<>();

    @Autowired
    StateProbe probe;

    @BeforeAll
    static void resetObservation() {
        EARLIER.set(null);
    }

    @Test
    @Order(1)
    void captureContextBeforeFreshMethod() {
        EARLIER.set(probe.id());
        probe.reset();
        assertEquals(1, probe.increment());
    }

    @Test
    @Order(2)
    @DirtiesContext(
            methodMode = DirtiesContext.MethodMode.BEFORE_METHOD)
    void freshContextIsInjectedBeforeThisMethod() {
        String prior = EARLIER.get();

        assertNotNull(prior);
        assertNotEquals(prior, probe.id());
        assertTrue(StateProbe.wasClosed(prior));
        assertEquals(0, probe.count());
    }
}
~~~

**Exactly 2 `@Test` methods.** Unlike `AFTER_METHOD`, the second method **proactively requests a fresh context before running**. Spring test listeners support dependency re-injection so `@Autowired probe` in the second method points to the new bean when the method body executes.

**When to consider `BEFORE_METHOD`?** A specific test requires a context in its initial state right before performing a config-breaking operation, while earlier methods might have affected the context. This remains an expensive solution. If you only need fresh database rows, use fixture resets or transaction rollback instead.

## 10. Class mode `BEFORE_EACH_TEST_METHOD`: reset the entire container before every test

**src/test/java/demo/cache/DirtiesBeforeEachTest.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(
        classMode =
                DirtiesContext.ClassMode.BEFORE_EACH_TEST_METHOD)
class DirtiesBeforeEachTest {

    private static final AtomicReference<String> PREVIOUS =
            new AtomicReference<>();

    @Autowired
    StateProbe probe;

    @BeforeAll
    static void clearObservation() {
        PREVIOUS.set(null);
    }

    @BeforeEach
    void verifyFreshBean() {
        String earlier = PREVIOUS.getAndSet(probe.id());

        if (earlier != null) {
            assertNotEquals(earlier, probe.id());
            assertTrue(StateProbe.wasClosed(earlier));
        }

        assertEquals(0, probe.count());
    }

    @Test
    void firstOperation() {
        assertEquals(1, probe.increment());
    }

    @Test
    void secondOperation() {
        assertEquals(1, probe.increment());
    }
}
~~~

**Exactly 2 `@Test` methods.** Spring TestContext dirties before each method. `PREVIOUS` is a static demonstration marker not reset by dirtying; thus `@BeforeEach` can check that the old bean had a different ID and was closed. No method ordering is needed because every method exhibits the same behavior.

**Cost note:** Changing a counter is a small task, so using `classMode = BEFORE_EACH_TEST_METHOD` here is **solely for observation**, not an optimal design choice. In a large application, every method could force Spring to rebuild the container, introducing unnecessary CI latency.

## 11. Class mode `AFTER_EACH_TEST_METHOD`: dirty after every method

**src/test/java/demo/cache/DirtiesAfterEachTest.java**

~~~java
package demo.cache;

import java.util.concurrent.atomic.AtomicReference;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext(
        classMode =
                DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class DirtiesAfterEachTest {

    private static final AtomicReference<String> PREVIOUS =
            new AtomicReference<>();

    @Autowired
    StateProbe probe;

    @BeforeAll
    static void clearObservation() {
        PREVIOUS.set(null);
    }

    @BeforeEach
    void verifyLastMethodWasCleanlyClosed() {
        String earlier = PREVIOUS.getAndSet(probe.id());

        if (earlier != null) {
            assertNotEquals(earlier, probe.id());
            assertTrue(StateProbe.wasClosed(earlier));
        }

        probe.reset();
    }

    @Test
    void oneOperationCompletesAndContextWillClose() {
        assertEquals(1, probe.increment());
    }

    @Test
    void anotherOperationGetsANewBean() {
        assertEquals(1, probe.increment());
    }
}
~~~

**Exactly 2 `@Test` methods.** After each method completes, the context is dirtied by **class-level `AFTER_EACH_TEST_METHOD`**. On the next method, the context is no longer in the cache and Spring must reload it. The test verifies a different marker and that the old bean received `@PreDestroy`.

**Difference from `BEFORE_EACH`:** `BEFORE_EACH_TEST_METHOD` evicts the context **right before** the method; `AFTER_EACH_TEST_METHOD` evicts the context **right after** the method. Both generally prevent reuse between methods, yet differ in which lifecycle stage runs, especially with setup/teardown listeners and initialization logging.

**Never use `@DirtiesContext(classMode=AFTER_EACH_TEST_METHOD)` to define "every test starts with a clean DB"** without checking which resource owns the DB. If the database is an external PostgreSQL instance, the new context can still read the exact same rows from the previous method.

## 12. `AFTER_CLASS` and differing cache keys even without dirtying

### 12.1. Dirty after the entire class

**src/test/java/demo/cache/DirtiesAfterClassTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@DirtiesContext
class DirtiesAfterClassTest {

    @Autowired
    StateProbe probe;

    @Test
    void contextIsUsableDuringClass() {
        probe.reset();

        assertEquals(1, probe.increment());
        assertNotNull(probe.id());
    }
}
~~~

**Exactly 1 `@Test`.** Class-level `@DirtiesContext` requires no argument because the **default is `ClassMode.AFTER_CLASS`**: the framework closes the context after the class finishes. The test body itself cannot observe `AFTER_CLASS`, as the callback fires **after** the test class phase. That is why we do not write `assertTrue(StateProbe.wasClosed(probe.id()))` inside the test: the timing would be wrong.

If you genuinely need to verify post-class lifecycle, use a separate test runner/lifecycle harness, listener, or integration test coordinating contexts explicitly. Avoid creating fragile ordering dependencies between two classes.

### 12.2. Changing an inline property creates a new cache key

**src/test/java/demo/cache/BlueConfigurationTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "lab.variant=blue")
class BlueConfigurationTest {

    @Value("${lab.variant}")
    String variant;

    @Test
    void usesBlueTestProperty() {
        assertEquals("blue", variant);
    }
}
~~~

**src/test/java/demo/cache/RedConfigurationTest.java**

~~~java
package demo.cache;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE,
        properties = "lab.variant=red")
class RedConfigurationTest {

    @Value("${lab.variant}")
    String variant;

    @Test
    void usesRedTestProperty() {
        assertEquals("red", variant);
    }
}
~~~

**Exactly 1 `@Test` per class.** Neither class carries `@DirtiesContext`. Yet `@SpringBootTest(properties="lab.variant=blue")` and `...red` differ in configuration, so Spring TestContext creates **two cache keys**. If the same suite also has `@SpringBootTest` classes without the inline variant, those form yet another configuration group.

The tests only assert the right property value, **without claiming to have counted exact contexts across the entire JVM**. To observe, inspect DEBUG cache logs and `StateProbe.totalConstructed()` if desired — but avoid asserting an absolute number because test class ordering, LRU, and fork configuration can alter the count.

## 13. Counting tests, running Gradle, and reading results accurately

| Test class | `@Test` | Purpose |
|---|---:|---|
| `ContextReuseTest` | 3 | No dirtying; reuse bean ID; reset counter per method |
| `DirtiesAfterMethodTest` | 2 | `AFTER_METHOD` evict/close and rebuild in next test |
| `DirtiesBeforeMethodTest` | 2 | `BEFORE_METHOD` fresh context + re-injection |
| `DirtiesBeforeEachTest` | 2 | `BEFORE_EACH_TEST_METHOD` |
| `DirtiesAfterEachTest` | 2 | `AFTER_EACH_TEST_METHOD` |
| `DirtiesAfterClassTest` | 1 | Default class-level `AFTER_CLASS` |
| `BlueConfigurationTest` | 1 | Cache key with inline property blue |
| `RedConfigurationTest` | 1 | Cache key with inline property red |
| **Total** | **14** | JUnit Jupiter, no `@Disabled` |

**Run with Gradle Wrapper** if the project already has a wrapper generated:
~~~bash
./gradlew test
~~~

Windows:
~~~powershell
.\gradlew.bat test
~~~

If you only copied `settings.gradle`, `build.gradle`, and source files without **wrapper scripts/JAR**, `./gradlew` will not exist. Use a compatible Gradle installation to generate the wrapper or run `gradle test`. On a machine without cached dependencies, the first run needs Maven Central to resolve the Boot plugin/starters.

**Run each class individually:**
~~~bash
./gradlew test --tests demo.cache.ContextReuseTest
./gradlew test --tests demo.cache.DirtiesAfterMethodTest
./gradlew test --tests demo.cache.DirtiesBeforeMethodTest
./gradlew test --tests demo.cache.DirtiesBeforeEachTest
./gradlew test --tests demo.cache.DirtiesAfterEachTest
./gradlew test --tests demo.cache.DirtiesAfterClassTest
./gradlew test --tests demo.cache.BlueConfigurationTest
./gradlew test --tests demo.cache.RedConfigurationTest
~~~

**Important note:** Running classes one by one in separate Gradle commands **does not share the static `ContextCache` across the separate JVM test workers of those invocations**. If you want to observe cache reuse **across classes** within the suite, run `./gradlew test` for the whole suite **in one test JVM**, as configured in this lesson. To uncover flaky tests, run all of them multiple times and read cache stats rather than only running one isolated method.

**Gradle reports** are typically at `build/reports/tests/test/index.html`. **Expected design outcome** is 14 tests PASS on Java 17/Boot 3.3.5 when the code is created and run properly. This is an **expectation from code/APIs**, not a claim that Gradle was executed on the reader's machine.

**Test lifecycle assumptions:**
- JUnit parallel execution is disabled, so classes do not interleave; static markers are only used for checks within **one class**.
- `@TestMethodOrder(OrderAnnotation.class)` in exactly two classes is an exception to illustrate BEFORE/AFTER phases; it is not recommended to impose test order on business logic.
- `StateProbe.wasClosed(old)` is evaluated after the listener processes dirtying; it does not rely on JVM GC/finalizers.
- The test application uses no `@Transactional`, no external DB, and no unfinished async jobs.
- `StateProbe.generation()` increments when a bean instance is created; **it does not mean the entire JVM has only one application context or only one Spring bean**.
- `DirtiesAfterClassTest` verifies behavior inside the class; post-class closure is confirmed by Spring semantics and cache logs rather than asserting before closure occurs.

## 14. Observing and measuring **cost** instead of guessing

### 14.1. Enable cache DEBUG stats

Spring TestContext cache has the logger:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

This is the log level in the example; for real Logback tests you can configure the logger early in `logback-test.xml`. Cache stats typically mention **size**, **maxSize**, **parentContextCount**, **hitCount**, **missCount**, and **failureCount** (exact fields/formatting may vary by Framework version). The following illustrative figures are **not actual executed logs**:

~~~text
Illustrative cache observation, not actual stdout:

Before adding broad dirties:
  many hits, few misses, fewer context refreshes

After adding @DirtiesContext(AFTER_EACH_TEST_METHOD):
  misses rise, startup/close more frequent
  build total time may increase

After replacing unnecessary dirties by data reset:
  cache reuse returns, hits increase
  tests still isolated by fixture cleanup
~~~

**Do not carelessly equate `hitCount` = number of test methods.** Spring TestContext can invoke `getApplicationContext` multiple times across test lifecycle phases; each lookup can contribute a hit. Read **trends** and correlate context startups rather than converting hits/misses into method counts.

### 14.2. Sensible benchmarking methodology

**Step 1:** Capture a suite baseline in a fixed environment: JDK, CPU/RAM, Gradle version/daemon, Docker/DB resources, Gradle forks/parallel settings. Measure **total test task wall-clock** and how many Spring contexts are created.

**Step 2:** Record differing config keys: `@ActiveProfiles`, `@SpringBootTest(properties)`, test slices, `@MockBean`, test config imports, web environments. Distinguish cache misses caused by **differing keys** vs. **dirtying** vs. **LRU**.

**Step 3:** Remove `@DirtiesContext` where clean reset/rollback exists, keeping it on tests that genuinely mutate bean definitions. Re-run tests and verify **functional correctness** before inspecting timings.

**Step 4:** Compare multiple runs under equivalent conditions, excluding dependency downloads and abnormal environmental spikes. **Do not write assertions like `assertTrue(startup < 500ms)`** in integration tests: on a slow CI runner it can fail even when the application is completely correct.

**Step 5:** Evaluate context cache size vs. memory. Retaining 32 large contexts consumes RAM and increases GC; raising `maxSize` only helps when cache churn is a significant cost and memory headroom exists. Test 16/32/64 against measurements rather than assuming bigger is always faster.

**Step 6:** Check JUnit/Gradle parallelism. A suite running test methods in parallel can share a mutable context, making behavior unsafe even if faster. Spring docs warn against using `@DirtiesContext` in parallel tests because one thread can evict/close a context while another thread is still using it.

### 14.3. Reading bean initialization signals

`StateProbe.totalConstructed()` in the demo project tells you **how many `StateProbe` beans were created in the test JVM**. It does not measure "full application build time". You can supplement with `ApplicationStartup`, Java Flight Recorder, or Actuator startup observations to see which beans/steps take the most time at startup. Never embed a fake timer in a test to assert performance as a stable contract.

**Do not confuse Gradle configuration time with Spring context startup time.** `./gradlew test` includes Gradle startup/configuration, compilation, dependency resolution, JUnit discovery, JVM startup, context loads, and actual tests. The context cache optimizes only a slice of that total duration.

## 15. Tainted test data: choose data reset over context rebuild

### 15.1. Database transaction rollback

When using `@DataJpaTest` or tests with `@Transactional` managed by Spring TestContext, the test transaction usually **rolls back** after each test method. This undoes DB changes made by the test method while **retaining the ApplicationContext**.

~~~java
@DataJpaTest
class OrderRepositoryTest {

    @Autowired
    TestEntityManager entityManager;

    @Test
    void findsOrder() {
        // Insert/query inside test-managed transaction.
        // When the test method finishes, the transaction rolls back.
    }
}
~~~

**Illustrative snippet**, not part of the JPA-free runnable project. Requires `starter-data-jpa`, a test DB, and matching entity/repository classes. **Do not assume `@Transactional` on a test always rolls back every server-side write**: with `@SpringBootTest(webEnvironment=RANDOM_PORT)`, the HTTP client and embedded server typically run on **different threads/transactions**; writes on the server do not automatically roll back with the test transaction. Tests using `@Async` also have separate `ThreadLocal` transaction boundaries.

### 15.2. @Sql setup/cleanup or repository fixtures

~~~java
@Sql(
    scripts = "/db/seed-orders.sql",
    executionPhase = Sql.ExecutionPhase.BEFORE_TEST_METHOD)
@Sql(
    scripts = "/db/cleanup-orders.sql",
    executionPhase = Sql.ExecutionPhase.AFTER_TEST_METHOD)
@Test
void testOrderEndpoint() {
    // HTTP assertions...
}
~~~

**Illustrative snippet**, not part of the runnable project because the SQL scripts are not defined in section 6. `@Sql` belongs to Spring Test; verify transaction mode (`ISOLATED`, default inference), cleanup behavior, and that no leftover data remains after the test. On a shared DB, you may need separate schemas, FK-ordered truncation, or a disposable database.

### 15.3. @MockBean and mock state

In **Spring Boot 3.3**, Boot's `@MockBean`/`@SpyBean` can replace/wrap beans. Mock definitions **enter the context customizer/cache key**, so differing mocks across classes prevent context sharing. Mocks in the same context are normally auto-reset between test methods under Boot defaults; `@DirtiesContext` is not needed merely to clear Mockito stubbing/interaction history.

**Version note:** Newer Spring Framework/Spring Boot versions provide `@MockitoBean`/`@MockitoSpyBean` and deprecate legacy Boot mock annotations. This lesson pins Boot 3.3, so do not change imports arbitrarily.

If you mock an external client:
~~~java
@MockBean
ExternalGateway gateway;
~~~

This is a **snippet** assuming an `ExternalGateway` interface exists. Add `when(gateway.call(...))` inside each method or configure an appropriate reset policy; avoid leaking stubbing across tests. Also, if two classes have different mocks, even without dirtying they will produce **separate cache keys**. Use a shared base test configuration to curb variants, without turning the entire suite into one giant context stuffed with dozens of unrelated mock overrides.

### 15.4. Resetting Spring caches and static data

If a test mutates `@Cacheable` data, cleanup can look like:
~~~java
@BeforeEach
void clearCache() {
    cacheManager.getCache("products").clear();
}
~~~

**Illustrative snippet**, requiring `CacheManager` injection and a `products` cache to exist; not part of the runnable project. If there are multiple cache names/tenants, clear exactly what is needed; no need to close the context. For static fields, expose a reset API for test fixtures/data rather than expecting `@DirtiesContext` to wipe static variables.

### 15.5. Why a test turning "green" after dirtying doesn't prove a clean design

If an integration test fails because a singleton retained the user ID from the prior request, adding dirtying can make the test green because each method creates a new bean. Yet in a **long-running production application**, the singleton lives on and can still leak the previous request's user ID — a critical bug! The proper test fixes the singleton to be stateless/request-scoped or concurrency-safe, then verifies consecutive requests within the **same context**.

`@DirtiesContext` can **hide state leakage bugs** instead of fixing them. Before adding the annotation, check whether the tainted state is:
- Business data needing cleanup.
- `ThreadLocal`/MDC/`SecurityContext` needing clearing.
- Wrong bean scope (`@Singleton` holding request data).
- An unreset global static registry.
- Uncleaned external resources.
- Truly mutated Spring context configuration.

Only the last category (and select cases where cleanup is impossible) clearly justifies rebuilding the context.

## 16. Context hierarchy and `hierarchyMode`

When tests use `@ContextHierarchy`, an application can consist of a parent context holding shared infrastructure/config and one or more child contexts (`WebApplicationContext`, servlet MVC, module-specific contexts). The annotation takes a parameter:

~~~java
@DirtiesContext(
        hierarchyMode = DirtiesContext.HierarchyMode.CURRENT_LEVEL)
@Test
void testOnlyThisChildContext() { ... }
~~~

This is an **illustrative snippet**, not part of the runnable project since the lesson does not set up `@ContextHierarchy`. Two modes:

- **`EXHAUSTIVE`** (default): Spring uses an exhaustive algorithm to clear all contexts belonging to sub-hierarchies that share the relevant ancestor context. Dirtying one child can impact sibling branches sharing the parent, triggering many context loads.
- **`CURRENT_LEVEL`**: restricts clearing to the current level in the hierarchy per Spring semantics, avoiding unnecessary impact on siblings when safe; however, you must ensure parent/shared state was not corrupted. Do not overuse `CURRENT_LEVEL` if the mutation already affected a bean in the ancestor.

**Do not assume `CURRENT_LEVEL` evicts only a single bean or skips closing dependent child contexts.** It operates on **context cache entries in the hierarchy**, not individual beans. If tests use custom hierarchies, read the matching Spring version docs and check parent/child logs and identities.

### 16.1. Context cache when using @DynamicPropertySource

`@DynamicPropertySource` typically registers dynamic suppliers such as ports from Testcontainers. The presence of the **method defining dynamic properties** can participate in `contextCustomizers`/cache key; however, values returned by the supplier at different times **do not necessarily** create a new cache key automatically. When a base test class has a dynamic property that changes per subclass/resource lifecycle, Spring can reuse the old context if configuration metadata matches, leaving client beans pointing at the changed port.

In such cases, align **container scope/context scope** consistently; `@DirtiesContext` on the base class may be needed if dynamic properties genuinely differ and the old context is invalid, or avoid changing external endpoints within the same cached context. Do not treat changes to `DynamicPropertyRegistry` as an "auto-refresh" for already initialized beans.

### 16.2. Testcontainers do not automatically restart when a context is dirtied

A **static `@Container`** is normally managed per test class by the JUnit extension; it is not a Spring singleton bean. `@ServiceConnection` feeds connection details from the container into the Spring context, yet `@DirtiesContext` **does not mean a static container will be wiped or restarted**. Conversely, if a container is declared as a Spring-managed bean, its lifecycle ties to the context and is affected when the context closes. Always distinguish the actual owner of the container, connection pools, DB schema, and data volumes.

For example, with a Postgres Testcontainer, a new context may connect to the **same** still-running database container; old data remains. Use proper transactions/schema resets/test isolation rather than treating a context rebuild as a DB truncate.

## 17. `@DirtiesContext` and parallel execution: hard-to-spot races

Spring TestContext supports running tests in parallel to an extent, but official documentation advises **avoiding parallel tests** if tests use `@DirtiesContext`. On one thread, test A may dirty/close a context that thread B is actively using to run another test. Result: closed beans/pools, `ApplicationContext` no longer active, flaky failures, and difficult debugging.

**Independent risk:** Two tests sharing a cached context while mutating a singleton or DB rows can also race even without dirtying. Parallelism requires **data isolation** and minimizing shared state, not merely omitting the annotation.

Strategies:
1. Run context-dirtying classes sequentially or isolate them in a separate task/fork.
2. Never close a context while background tasks still reference beans from the old context.
3. Never assume `@DirtiesContext` locks out other tasks using the same cache key.
4. When parallel speedup is needed, prefer per-test data fixtures/schema namespaces and context reuse over rebuilding.
5. Use `@ResourceLock`/JUnit parallel settings deliberately for shared resources; locks must cover every test touching that resource.
6. Log cache and shutdown stacks to tell whether a context closed via `DirtiesContext` or LRU.
7. Never use `Thread.sleep` to "wait for context close"; rely on Spring test listener phases or proper latches/lifecycle callbacks.

**CI benchmarks must compare under equal concurrency conditions.** For example, 10 test forks may cut elapsed time while multiplying total contexts, DB connections, and memory. One fast or slow run proves nothing on its own.

## 18. Practical test suite optimization plan

### 18.1. Categorize tests by objective

| Test objective | Context choice | State reset | When to Dirty |
|---|---|---|---|
| Pure service logic | JUnit + Mockito, **no Spring context** | Instantiate new object per test | Never |
| Spring MVC controller mapping | `@WebMvcTest` | Mocks/fixture methods | Rarely |
| JPA repository | `@DataJpaTest`, rollback | Transactions/DB fixtures | Rarely |
| Application wiring/integration | `@SpringBootTest` sharing key | `@BeforeEach`, `@Sql`, transactional cleanup | Only if context truly tainted |
| Real HTTP server | `@SpringBootTest(RANDOM_PORT)` | DB setup/cleanup, client state | When server/context resources altered |
| Kafka/RabbitMQ | Context + test broker/container | Distinct queue/topic/group names; purge | Only if Spring infrastructure broken/changed |
| Spring context lifecycle | TestContext/Boot context | No equivalent cleanup | Deliberately |
| Security with `@MockBean` | Boot mock reset between tests | Reset stubbing, request state | Rarely |

**Do not use `@SpringBootTest` for every pure function test.** If you are just summing prices with Java inputs/outputs, invoke the service logic via `new` or Mockito instead of booting a container. The context cache helps *the second time*, but **the first time** loading the whole app still costs more than a context-free unit test.

### 18.2. Reduce the number of context cache keys

- Use a shared `@ActiveProfiles("test")` for classes with the same needs instead of dozens of arbitrary variants.
- Consolidate truly identical inline properties instead of giving every class arbitrary `@SpringBootTest(properties={"feature=x"})`.
- Avoid differing `@MockBean` sets across classes if merely testing unit logic; move unit tests to standalone Mockito where appropriate.
- Use test slices (`@WebMvcTest`, `@DataJpaTest`) while keeping in mind each slice/config is still a separate context key; avoid spawning too many tiny custom contexts.
- Avoid importing unique nested `@TestConfiguration` classes unnecessarily, as they can alter the context customizer key.
- Ensure `@DynamicPropertySource`/Testcontainers lifespans align with cache reuse.
- Avoid plastering `@DirtiesContext` across tests just because each class has a non-idempotent setup method.
- Observe `hitCount/missCount/size` before and after changes.

**Optimizing does not mean cramming everything into one giant application context.** The goal is **sensible** reuse while preserving state isolation and saving RAM. A small slice test can be faster than the full context even though it introduces its own key.

### 18.3. Choose the narrowest dirty phase necessary

If a single method mutates bean definitions, annotate:
~~~java
@Test
@DirtiesContext(methodMode = DirtiesContext.MethodMode.AFTER_METHOD)
void modifiesBeanFactory() { ... }
~~~

instead of placing:
~~~java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
class EveryTestInClass { ... }
~~~

Where possible, isolate context-mutating tests into a small dedicated class instead of forcing the whole suite to rebuild. If **every method** truly needs a fresh Spring context to verify lifecycle, `BEFORE_EACH`/`AFTER_EACH` is valid — but that must be the **test objective**, not a reflex to patch flaky tests.

## 19. Mutation experiments: how to verify tests test the right thing

| Trial mutation | Expected evidence |
|---|---|
| Remove `@DirtiesContext` from the first method in `DirtiesAfterMethodTest` | Second test sees the **same marker**; difference assertion fails |
| Change `AFTER_METHOD` to `BEFORE_METHOD` on the first method | Next test can still reuse the first method's context; wrong phase |
| Remove `BEFORE_METHOD` on the second method | Old marker matches new marker; test fails |
| Change `BEFORE_EACH_TEST_METHOD` to `AFTER_CLASS` | Methods in the class reuse marker; freshness assertion fails |
| Change `AFTER_EACH_TEST_METHOD` to `AFTER_CLASS` | Second test sees old marker; test fails |
| Remove `probe.reset()` in `ContextReuseTest` | Some tests can become order/state dependent; reset invariant fails |
| Use `ApplicationContext.getId()` instead of probe UUID | New context can carry the same ID string; false confidence |
| Add `@SpringBootTest(properties="x=1")` to one class | Different cache key, cache miss even without dirtying |
| Add a different `@MockBean` in every class | More context customizers/keys |
| Run each class in a separate Gradle fork | Loses cross-class reuse because static caches aren't shared |
| Enable parallel tests while using `DirtiesContext` | Possible race when one test closes a context another is using |
| Only "reset DB" via `DirtyContext` on external PostgreSQL | Old rows can still persist |
| Change `maxSize` from 32 down to 1 with multiple keys | LRU eviction rises even without dirtying |
| Disable `@PreDestroy` callback on `StateProbe` | `wasClosed(old)` test loses proof the bean was destroyed |
| Use `@Transactional` with real HTTP server expecting server-write rollback | Separate threads/transactions; false assumption |

These are **optional mutation experiments**, not changes to keep in the main project. Run each mutation in a sandbox branch and revert; never leave intentionally failing tests in a production suite. A real dirtying test checks **new marker + old closed**, rather than relying on elapsed seconds or log ordering.

## 20. Troubleshooting

| Symptom | Possible cause | How to verify/fix |
|---|---|---|
| `@SpringBootTest` gets slower over time | Too many context cache misses | Enable cache DEBUG, inspect keys and `DirtiesContext` |
| Every class restarts the app | Widespread `@DirtiesContext(AFTER_CLASS)` | Reset fixtures instead of dirtying where possible |
| Every test method restarts | `AFTER_EACH`/`BEFORE_EACH` class mode | Confirm actual need; lighter state reset |
| Two similar test classes don't reuse | Different profiles/properties/mocks/test customizers | Compare metadata config; reduce variants |
| An earlier test breaks a later test | Uncleaned mutable singleton/DB/broker state | Trace state source, reset specifically |
| Test passes in isolation but fails in full suite | Shared state or context cache behavior | Run full suite in same JVM, check lifecycle |
| Context ID doesn't change after dirtying | Context ID is a logical name that can repeat | Compare bean instance UUID/identity |
| `StateProbe.wasClosed` false inside dirtying test | Asserting **before** the listener phase runs | Assert in subsequent test or lifecycle listener |
| `@DirtiesContext` doesn't reset static counter | Statics live for the whole JVM | Reset static test fixture explicitly |
| DB still has rows after dirtying | External DB is outside context lifecycle | Transaction rollback / schema cleanup |
| Static Testcontainers still running after dirtying | Container managed by JUnit/static | Distinguish container lifecycle ownership |
| Shutdown causes connection closed errors in async test | Dirtied before worker completed | Await task completion/cleanup before dirtying |
| Cache hit count exceeds test count | TestContext looks up context multiple times per test | Read trends/hits/misses, don't divide 1:1 |
| Second context load failure skipped immediately | Spring 6.1 failure threshold=1 | Investigate first load error; don't raise threshold blindly |
| `ApplicationContext is no longer active` in parallel run | Another test dirtied or LRU evicted | Avoid parallel `DirtiesContext`, tune cache size |
| CI uses many JVM workers | Each JVM has its own static `ContextCache` | Check Gradle forks / `forkEvery` |
| Cache consumes high RAM | Too many large contexts / `maxSize` too high | Benchmark memory vs. reload trade-off |
| Tests differ only due to `@MockBean` | Mock customizer alters key | Consolidate config or use plain Mockito unit tests |
| `@DynamicPropertySource` property points to old port | Supplier/resource lifecycle mismatches cache | Align lifespan, dirty when needed, verify |
| JMX MBean name collision across tests | Spring-managed JMX resource needs closing | Scoped `@DirtiesContext` may be appropriate |
| `@Sql` cleanup not running as expected | Wrong transaction mode/order/scripts | Inspect actual DB state after cleanup |
| Unit test slow because it boots Spring | `@SpringBootTest` unnecessary | Instantiate objects and mocks in plain Java |
| Dirtying masking a singleton bug | Fresh context hides production memory/state leak | Fix bean state/scope; test multiple requests on same context |
| Startup logs appear under another test | Context init/close sits in listener lifecycle | Read by phases/cache logs, not just runner grouping |

## 21. Code review checklist for choosing `@DirtiesContext`

1. **Is the test about context lifecycle or business data?** If business data, consider reset/rollback first.
2. **Is there genuinely unresettable state?** Pinpoint the exact tainted bean/resource.
3. **Is closing the context proven necessary?** Do not use the annotation as a vague fix.
4. **Pick the right phase:** method `BEFORE`/`AFTER` vs. class `BEFORE`/`AFTER_EACH`/`AFTER_CLASS`.
5. **Method vs. class defaults differ:** `AFTER_METHOD` vs. `AFTER_CLASS`.
6. **Any overlapping annotations?** Avoid closing both before and after the same test unnecessarily.
7. **`@ContextHierarchy`:** `EXHAUSTIVE` can spread to siblings; `CURRENT_LEVEL` requires understanding scope.
8. **External DB/broker/files:** dirtying does not clean them automatically.
9. **Mockito mocks:** Boot 3.3 auto-reset may suffice; mock definitions still affect keys.
10. **Dynamic ports/Testcontainers:** context cache scope must match resource lifecycle.
11. **Parallel execution:** never dirty a context while another test is using the same instance.
12. **Gradle forks:** one JVM shares cache, multiple JVMs mean multiple caches.
13. **Startup cost:** measure context loads/cache misses and suite runtime before/after; never hard-assert durations.
14. **Cache size:** default 32; tune when evidence shows LRU churn and memory headroom exists.
15. **Test independence:** never use method ordering as a workaround for business tests.
16. **Transaction boundaries:** test-managed rollback does not cover server/async threads by default.
17. **Singleton state:** reset/test at the right scope instead of hiding bugs via rebuilds.
18. **No false performance claims:** logs/metrics can vary across test runners/JVMs/CI.
19. **Version compatibility:** match Boot 3.3/Spring 6.1 APIs; do not assume Boot 4 uses the exact same bean override annotations.
20. **Completion:** merge optimization changes only when all functional tests still PASS and the suite shows measured improvement.

## 22. Practice exercises

**Exercise 1 — Cached context:** Run `ContextReuseTest` and observe the three `@Test` methods sharing `StateProbe.id()`. Why does each method stay independent when using `@BeforeEach reset()`?

**Exercise 2 — `AFTER_METHOD`:** Remove the annotation from the first test in `DirtiesAfterMethodTest`. What ID does the second test observe? Why is that an isolation regression?

**Exercise 3 — `BEFORE_METHOD`:** Change the annotation on the second test to `AFTER_METHOD`. Why is the second test no longer guaranteed a fresh context **before** its body?

**Exercise 4 — `BEFORE_EACH`:** Increase the number of tests in `DirtiesBeforeEachTest` to five. Semantically, how many dirty events happen? Why can the actual number of context loads be affected by the injection lifecycle?

**Exercise 5 — `AFTER_EACH`:** Read Spring cache DEBUG logs and correlate them with `@PreDestroy` markers after each method.

**Exercise 6 — `AFTER_CLASS`:** Place `@DirtiesContext` at class level only, with none on methods. How do lifecycle and cost compare to `AFTER_EACH`?

**Exercise 7 — `BEFORE_CLASS`:** Replace the class annotation with `@DirtiesContext(classMode=BEFORE_CLASS)`. How does "fresh context before class" differ from "close after class"?

**Exercise 8 — Cache keys:** Add `@ActiveProfiles("test")` to one class. When that profile is absent on another class, are the keys identical?

**Exercise 9 — Mock customizer:** Two classes share `@SpringBootTest`, yet one adds `@MockBean`. Is cache reuse guaranteed? Propose how to organize mocks without multiplying context variants.

**Exercise 10 — DB rollback:** Write a `@DataJpaTest` using a test-managed transaction, insert and query. Run a second test to prove the DB is clean without dirtying.

**Exercise 11 — HTTP server:** Use `@SpringBootTest(webEnvironment=RANDOM_PORT)`, POST to create a record over HTTP, plus `@Transactional` on the test. Why might the server-side write not roll back?

**Exercise 12 — External database:** Use a static PostgreSQL Testcontainer and `DirtiesContext`. Check records before/after context rebuild; why is explicit schema cleanup needed?

**Exercise 13 — LRU:** Create 35 distinct test context keys in one JVM while keeping `maxSize=32`. Observe LRU evictions/close callbacks; do not alter a production test suite.

**Exercise 14 — Gradle forks:** Run the same suite with `maxParallelForks=1` and then a multi-worker configuration. Compare total cache hits/misses and runtime. Conclude the trade-off instead of looking solely at context counts.

**Exercise 15 — Hierarchy:** Build a parent context + two child contexts. Compare `HierarchyMode.EXHAUSTIVE` and `CURRENT_LEVEL`, verifying exactly which contexts close.

**Exercise 16 — Failure threshold:** Create a bean that intentionally fails during init in a sandbox. When multiple tests share that key, why does "preemptively skipped" appear? Identify the first root error.

**Exercise 17 — DynamicPropertySource:** Use two test classes with the same method metadata yet changing container ports. Write a test verifying the client does not point to a stopped resource, aligning lifecycle with the cache.

**Exercise 18 — Parallel risk:** Enable JUnit parallel execution in a sandbox containing `DirtiesContext`. What error can occur when one thread closes a context another thread is using? How can it be avoided?

**Exercise 19 — Mutating singleton:** Change `StateProbe` into a singleton storing request data; run multiple requests in one context to expose the leak. Why is dirtying the context per method the wrong fix for production?

**Exercise 20 — Benchmark:** Measure the suite before/after replacing several `@DirtiesContext` annotations with `@Sql`/resets; record total duration, context startup count, max cache size, GC/memory, and stability.

## 23. Official Documentation

- [Spring Framework 6.1 — Context Caching](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/caching.html): cache keys, reuse, static cache, LRU, `maxSize`, and DEBUG logging.
- [Spring Framework 6.1 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.1/testing/annotations/integration-spring/annotation-dirtiescontext.html): `methodMode`/`classMode`, before/after test, and context close.
- [Spring Framework 6.1 — Context Hierarchies](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/hierarchies.html): parent/child contexts, `hierarchyMode`.
- [Spring Framework 6.1 — Context Failure Threshold](https://docs.spring.io/spring-framework/reference/6.1/testing/testcontext-framework/ctx-management/failure-threshold.html): default failure threshold 1 and property.
- [Spring Framework — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html): warning on using `DirtiesContext` with parallel tests.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `SpringBootTest`, mocking, cache reuse, `webEnvironment`.
- [Spring Framework — Test-Managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, `ThreadLocal` transaction boundaries.
- [Spring Framework — Executing SQL Scripts with @Sql](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/executing-sql.html): SQL setup/cleanup.
- [Spring Framework — @DynamicPropertySource](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/dynamic-property-sources.html): dynamic values and cache key implications.
- [Spring Boot — Testcontainers](https://docs.spring.io/spring-boot/3.3/reference/testing/testcontainers.html): container lifecycle and `@ServiceConnection`.
- [Spring Framework 6.1 API — DirtiesContext](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/test/annotation/DirtiesContext.html): all enum phases/defaults.
- [JUnit Jupiter — Test Order & Lifecycle](https://junit.org/junit5/docs/current/user-guide/): `TestMethodOrder`, `BeforeEach`, and parallel settings.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): forks, parallel tests, test JVM system properties.

**Conclusion:** **`@DirtiesContext` is a tool to evict and close a tainted ApplicationContext, not a "reset all data" button.** A dirtied context will not be reused from the Spring TestContext cache, and another test with the same cache key must load a new context at its full startup cost. Use the annotation at the right phase when a context genuinely cannot be reused; for routine data changes, prefer transaction rollback, fixture resets, mock resets, or clearing business caches. **Observe new bean UUIDs, `@PreDestroy` markers, and cache hits/misses** to prove lifecycle, and measure suite time instead of guessing. Designing tests that are both independent and sensibly share configuration is what delivers real performance gains.
