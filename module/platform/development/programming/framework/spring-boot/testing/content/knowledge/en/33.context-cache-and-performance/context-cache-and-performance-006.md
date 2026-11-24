# Measuring Context, Container, and Test Group Startup Times in Spring Boot

## 1. Why can a Spring Boot test suite be slow even when assertions are fast?

A test suite may spend only a few milliseconds checking business logic while waiting tens of seconds for the JVM, Spring context, database, and Docker. The causes typically lie across different phases:

- Gradle configures the project, resolves dependencies, compiles, and launches a forked Test JVM.
- JUnit Platform discovers classes, registers extensions, and creates test instances.
- Spring TestContext Framework checks the cache, builds a context on cache miss, initializes beans, and runs auto-configuration.
- `@SpringBootTest` triggers Flyway, Hibernate, HikariCP, an embedded server, or application runners if configured.
- Testcontainers must locate/pull a Docker image, create/start the container, and wait for service readiness.
- Different profiles, mock beans, dynamic properties, or `@DirtiesContext` across classes can force Spring to load new contexts.
- Test fixtures, SQL cleanup, HTTP calls, and container teardown run outside the test method body.
- Gradle spawns multiple worker JVMs so the context cache cannot be shared across processes.

**The task is not "print a single test duration number", but rather to measure and separate three cost buckets: Spring context startup, container startup, and per-group/test execution.** Once the real bottleneck is identified, you can decide whether to use test slices, reuse contexts/containers, or optimize data/migrations.

### After this lesson, you will be able to

1. Distinguish Gradle build wall time, Test task wall time, test class, method body, context cache lookup/load, Docker startup, first query, and shutdown.
2. Use `System.nanoTime()` to measure elapsed duration instead of a wall-clock timer.
3. Understand Spring TestContext cache keys, cache hits/misses, the default limit of 32, and `@DirtiesContext`.
4. Measure per class/test method via a JUnit Jupiter extension, knowing which points include or exclude fixtures.
5. Measure `TestContext.getApplicationContext()` retrieval using a high-priority `TestExecutionListener`.
6. Define separate Gradle Test tasks for unit/context/container groups and inspect HTML and JUnit XML reports.
7. Explicitly measure `PostgreSQLContainer.start()`, `SpringApplication.run()`, the first SQL query, and `stop()`.
8. Distinguish static/instance `@Container` from a Spring-context-owned Testcontainers container.
9. Use Spring Boot `BufferingApplicationStartup`, Actuator, startup metrics, and JFR to locate slow beans/steps.
10. Design statistically meaningful cold/warm and baseline/after comparisons without fabricating timings or writing flaky assertions.

## 2. Timeline model: do not add measurements mechanically

~~~text
./gradlew test
  |
  +-- Gradle initialization/configuration/task graph
  +-- Dependency resolution / compile
  |
  +-- Gradle Test task wall time ------------------------------+
  |     |
  |     +-- Start test worker JVM
  |     +-- JUnit discovery / extensions
  |     |
  |     +-- Test class A
  |     |     +-- Spring context cache LOOKUP
  |     |     |     +-- HIT: reuse context
  |     |     |     +-- MISS: create/refresh context
  |     |     +-- BeforeAll/BeforeEach
  |     |     +-- method execution
  |     |     +-- AfterEach/AfterAll
  |     |
  |     +-- Test class B, possibly reuse context A
  |     +-- Tear down/reports
  |
  +-- Remaining Gradle tasks/reporting
~~~

If tests use Testcontainers, costs can be broken down further:

~~~text
t0 -> container.start() -> t1
t1 -> SpringApplication.run() -> t2
t2 -> first JDBC query -> t3
t3 -> Spring context close -> t4
t4 -> container.stop() -> t5
~~~

These are **milestones**, not an additive formula valid for every test. For instance, `@SpringBootTest` usually constructs the context in `SpringExtension` callbacks before the test body runs; a stopwatch placed inside `@Test` will miss that cost.

### 2.1 Name metrics precisely

| Name | Start–End | What may be inside the interval |
| --- | --- | --- |
| `build.wall.ms` | Before/after Gradle command | Compile, caches, daemon, test/report |
| `gradle.test.task.ms` | Gradle Test task start/end | Test JVM fork, JUnit, setup, reports |
| `junit.class.ms` | JUnit BeforeAllCallback–AfterAllCallback | Class lifecycle, may exclude context pre-load |
| `junit.method.ms` | BeforeTestExecution–AfterTestExecution | Test method body, excludes `@BeforeEach`/`AfterEach` |
| `spring.lookup_or_load.ms` | Before/after `getApplicationContext()` | Cache lookup or context creation if MISS |
| `container.start.ms` | Before/after `container.start()` | Docker/image/start/wait depending on state |
| `spring.run.ms` | Before/after `SpringApplication.run` | Boot bootstrap until ready, including runners |
| `jdbc.first_query.ms` | Before/after first SQL | May include lazy pool connection |
| `container.stop.ms` | Before/after `container.stop()` | Best-effort Docker teardown |

**Never sum directly** `junit.class.ms + spring.run.ms + container.start.ms` when timers measure overlapping intervals or belong to different JUnit lifecycles. Separate boundaries first, then inspect the real timeline.

## 3. Use System.nanoTime() instead of currentTimeMillis()

To measure elapsed duration within the same JVM:

~~~java
long start = System.nanoTime();

doWork();

double elapsedMs =
        (System.nanoTime() - start) / 1_000_000.0;
~~~

This is an illustrative snippet requiring `doWork()`. `System.nanoTime` is a monotonic-style elapsed-time source, not a calendar timestamp, and must not be compared across processes/machines. `System.currentTimeMillis` is a wall clock that can jump due to NTP or OS adjustments, making it unsuitable for timing short methods.

### 3.1 A stopwatch does not turn a test into a proper benchmark

- Logging every measurement adds overhead, especially when the test body is tiny.
- JIT/class loading, GC, CPU scheduling, and thermal throttling affect results.
- One good run has no statistical significance.
- If you need nano/microsecond microbenchmarks, use **JMH** rather than a JUnit test.
- Never write `assertTrue(elapsedMs < 100)` on shared CI just because a local laptop hit 20ms.

JUnit timing is for **suite diagnostics**, not a substitute for performance SLO testing.

## 4. How does the Spring TestContext cache actually work?

Spring TestContext stores created `ApplicationContext` instances by `MergedContextConfiguration`. When a subsequent test class uses the same cache key and runs in the **same JVM**, the framework can return the existing context.

~~~text
ContextGroupATest -> key K -> CACHE MISS -> create context X
ContextGroupBTest -> key K -> CACHE HIT  -> reuse context X
ContextGroupCTest -> key L -> CACHE MISS -> create context Y
@DirtiesContext  -> evict/close context marked dirty
~~~

This is a model, not an assertion that Gradle always runs A before B. Whichever class arrives first with key K bears the cold context load.

### 4.1 Factors forming the context cache key

- `@ContextConfiguration` classes, locations, initializers.
- `ContextLoader`, parent context/hierarchy.
- `@ActiveProfiles`.
- `@TestPropertySource` and `@SpringBootTest(properties=...)`.
- Web resource base path/context customizers.
- Bean overrides like `@MockitoBean`, Boot test slice annotations.
- `@DynamicPropertySource` customizer methods and other test customizers.

Two test classes with different names **can** share a context. Two tests both using `@SpringBootTest` yet differing by one mock or one profile normally load two contexts.

### 4.2 Default maxSize is 32

Spring Framework 6.2 defines `ContextCache.DEFAULT_MAX_CONTEXT_CACHE_SIZE = 32`. When full, the cache uses LRU-style eviction and closes older contexts.

Configurable via JVM system property:

~~~text
-Dspring.test.context.cache.maxSize=64
~~~

Set the property on the **forked test JVM**, not just the Gradle daemon. This lesson includes Gradle code forwarding it from the Gradle JVM to the Test task.

**Increasing to 64 is not automatically faster:** keeping extra Hibernate/Hikari/Redis/executor contexts increases memory, GC, and open resources. Measure hits/misses, memory, and full suite time before changing it.

### 4.3 Context cache is intra-process only

- `maxParallelForks=4` can spawn 4 JVMs with 4 independent caches.
- `forkEvery=1` starts a fresh process after each class → drastically reduces reuse opportunities.
- Two separate `./gradlew test` invocations do not share the static Spring TestContext cache even if the Gradle daemon stays alive.
- If Gradle reports `UP-TO-DATE`, tests **may not have run at all**, so never use that total duration to judge context speed.

### 4.4 @DirtiesContext is the right tool, but expensive

`@DirtiesContext` tells Spring a context was mutated such that it cannot be safely reused and must be closed/evicted. Use it when a test truly changes bean definitions or unresettable state/settings, **not** out of habit on every method.

If you can reset DB fixtures, caches, queues, singleton state, and mocks between tests, perform proper cleanup to preserve the context. If isolation cannot be guaranteed otherwise, accept the context reload; correctness outweighs a few seconds.

## 5. Reading Spring context cache statistics

Enable:

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
~~~

Logs from `org.springframework.test.context.cache` report `size`, `maxSize`, `hitCount`, `missCount`, and additional details depending on framework version.

**Illustrative format example, not an actual measured log**:

~~~text
context cache: size=2 maxSize=32 hitCount=17 missCount=2
~~~

Notes:

- `missCount` reflects accesses for a key absent from the cache; usually leads to loading.
- `hitCount` can rise multiple times **within a single test class** because `SpringExtension`/DI/listeners access the context repeatedly.
- Never equate cache hits with the number of test methods.
- `@DirtiesContext` and LRU eviction can cause the same config to reload.
- One context MISS costing 15s for DB migrations matters more than 100 fast cache hits.

To diagnose slowness, examine **cache misses + time-per-miss + group wall time** together.

## 6. Measuring context load: using TestExecutionListener

A `TestExecutionListener` with very high priority (`getOrder()`) can trigger `testContext.getApplicationContext()` right when `beforeTestClass` runs:

~~~text
beforeTestClass:
   t0 = nanoTime
   context = testContext.getApplicationContext()
   elapsed = nanoTime - t0
   log class, context identity, elapsed
~~~

If the context is not loaded yet, the stopwatch includes loading/refreshing; if cached, it measures lookup.

**Do not call this "full Spring Boot startup"**: bootstrap callbacks may already have run before the timer, and this listener actively influences when the context loads. It is a properly scoped diagnostic tool for `lookup_or_load`.

## 7. Measuring class and method with a JUnit Jupiter extension

Two pairs of callbacks:

| Callback pair | Measures | Automatically excludes |
| --- | --- | --- |
| `BeforeAllCallback` / `AfterAllCallback` | Portion of class lifecycle | Entire test process if extension runs after context setup |
| `BeforeTestExecutionCallback` / `AfterTestExecutionCallback` | `@Test` body | `@BeforeEach`, `@AfterEach` |
| `BeforeEachCallback` / `AfterEachCallback` | Lifecycle around each method | Full context startup if it happens earlier |
| `TestReporter.publishEntry` | Emits key/value metric into JUnit execution | Not guaranteed to render in every console reporter |

Registering the extension before/after `SpringExtension` can shift class timestamps. This lesson uses a JUnit extension for class/method and a separate listener for context, without merging the two numbers into one.

## 8. Measuring container startup accurately

Testcontainers' `PostgreSQLContainer.start()` may perform:

1. Checking the Docker daemon/client and environment.
2. Locating the local image or pulling it from a registry if uncached.
3. Creating network/container/helper resources.
4. Starting the PostgreSQL process.
5. Waiting for the container to satisfy the wait strategy/readiness check.
6. Returning control to the test.

This measured time is **not solely PostgreSQL binary startup**. On a clean CI agent, image pull can dominate; on a laptop with a cached image, startup is much faster.

### 8.1 Cold vs. warm

| State | Includes |
| --- | --- |
| Cold image & Docker | Image pull + Docker setup + container start |
| Warm image, new container | No image pull, still create/start/wait |
| Shared static `@Container` | Once per test class, shared across its methods |
| Reusable container | Can keep process alive across runs, requires cleanup management |
| Spring-managed container bean | Lifecycle tied to `ApplicationContext` |

To measure the real container cost, **start the stopwatch right before `container.start()`**, not inside `@BeforeAll` if `@Testcontainers` extension already started a static `@Container` earlier.

### 8.2 Separate application-ready from database-ready

The container may be ready to accept TCP/SQL while Spring is still initializing the Hikari pool, Flyway, Hibernate, and runners.

~~~text
container.start() completes
   |
   +-- PostgreSQL accepts connections
   |
SpringApplication.run()
   +-- context refresh
   +-- JDBC auto-configuration
   +-- DB migration if present
   +-- runners/ready
   |
first JdbcTemplate.queryForObject()
   +-- may initialize lazy connection pool
~~~

Measure milestones separately; never assume "`container.start` = DB migrations" or "Boot ready = first SQL done".

## 9. Complete example: Java 17+ and Spring Boot 3.5

The lab comprises three groups:

- **unit:** plain JUnit, no Spring.
- **context:** two `@SpringBootTest` classes with identical config, observing cache reuse.
- **container:** an opt-in Docker test that starts PostgreSQL itself and then runs a **fresh** `SpringApplication` context.

All timing values are printed/published at runtime; the lesson **never fabricates seconds** or treats expected numbers as real logs.

Structure:

~~~text
context-timing-demo/
  settings.gradle
  build.gradle
  src/main/java/example/perf/
    BenchmarkApplication.java
    GreetingService.java
  src/test/java/example/perf/
    TimingExtension.java
    ContextLookupTimingListener.java
    PureUnitTimingTest.java
    ContextGroupATest.java
    ContextGroupBTest.java
    PostgresContainerTimingTest.java
  src/test/resources/
    application.properties
~~~

There are **7 JUnit `@Test` methods**: two unit, four context, one Docker. The Docker test is SKIPPED unless the environment variable `RUN_DOCKER_BENCH=true` is set. No external server is required for the unit/context groups.

## 10. settings.gradle

~~~groovy
rootProject.name = 'context-timing-demo'
~~~

## 11. build.gradle: configuring test groups

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'org.postgresql:postgresql'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()

    maxParallelForks = 1
    forkEvery = 0

    // Property must reach the forked test JVM.
    systemProperty 'spring.test.context.cache.maxSize',
            System.getProperty(
                'spring.test.context.cache.maxSize', '32')

    testLogging {
        events 'passed', 'failed', 'skipped'
        showStandardStreams = true
    }

    reports {
        html.required = true
        junitXml.required = true
    }
}

def addBenchGroup = { String taskName, String junitTag ->
    tasks.register(taskName, Test) {
        group = 'verification'
        description = 'Measure JUnit group: ' + junitTag
        dependsOn tasks.named('testClasses')
        testClassesDirs = sourceSets.test.output.classesDirs
        classpath = sourceSets.test.runtimeClasspath

        useJUnitPlatform {
            includeTags junitTag
        }
    }
}

addBenchGroup('unitBench', 'unit')
addBenchGroup('contextBench', 'context')
addBenchGroup('containerBench', 'container')
~~~

The build uses the Spring Boot BOM to manage Testcontainers/JUnit dependency versions. The pinned 3.5.0 and 1.1.7 versions are **illustrative milestones**, not claims that they are the latest.

`maxParallelForks=1`/`forkEvery=0` enables cache reuse within each Gradle Test task. The three tasks `unitBench`, `contextBench`, and `containerBench` **still launch separate test JVMs**; do not expect the Spring cache to persist across the three tasks.

`useJUnitPlatform { includeTags ... }` ensures each task measures only its target group. The default `test` task can run all of them; the Docker test is disabled if the env var is not enabled.

## 12. src/test/resources/application.properties

~~~properties
logging.level.org.springframework.test.context.cache=DEBUG
logging.level.root=WARN
~~~

Enables cache diagnostics in Spring Boot test contexts. For a baseline timing benchmark you can lower DEBUG after collecting cache statistics, since logging overhead can skew timings.

## 13. BenchmarkApplication.java

~~~java
package example.perf;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BenchmarkApplication {
    public static void main(String[] args) {
        SpringApplication.run(BenchmarkApplication.class, args);
    }
}
~~~

Because the app includes the JDBC starter, running `main` without a JDBC URL or excluding `DataSourceAutoConfiguration` can fail. In the two context groups, this lesson **excludes JDBC auto-configuration** via test properties; the Docker group provides real PostgreSQL URL/credentials.

## 14. GreetingService.java

~~~java
package example.perf;

import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String greet(String name) {
        return "Hello, " + Objects.requireNonNull(name);
    }
}
~~~

The business method is intentionally simple and deterministic: the goal is measuring startup overhead, not evaluating `String` concatenation throughput.

## 15. TimingExtension.java: measuring each group/class and method

File `src/test/java/example/perf/TimingExtension.java`:

~~~java
package example.perf;

import java.util.Locale;

import org.junit.jupiter.api.extension.AfterAllCallback;
import org.junit.jupiter.api.extension.AfterTestExecutionCallback;
import org.junit.jupiter.api.extension.BeforeAllCallback;
import org.junit.jupiter.api.extension.BeforeTestExecutionCallback;
import org.junit.jupiter.api.extension.ExtensionContext;

public final class TimingExtension
        implements BeforeAllCallback, AfterAllCallback,
                   BeforeTestExecutionCallback,
                   AfterTestExecutionCallback {

    private static final ExtensionContext.Namespace NAMESPACE =
            ExtensionContext.Namespace.create(TimingExtension.class);

    private static final String CLASS_TIME = "class-start";
    private static final String METHOD_TIME = "method-start";

    @Override
    public void beforeAll(ExtensionContext context) {
        context.getStore(NAMESPACE)
                .put(CLASS_TIME, System.nanoTime());
    }

    @Override
    public void afterAll(ExtensionContext context) {
        Long start = context.getStore(NAMESPACE)
                .remove(CLASS_TIME, Long.class);

        if (start != null) {
            print(context, "CLASS_TIME",
                    context.getRequiredTestClass().getSimpleName(),
                    start);
        }
    }

    @Override
    public void beforeTestExecution(ExtensionContext context) {
        context.getStore(NAMESPACE)
                .put(METHOD_TIME, System.nanoTime());
    }

    @Override
    public void afterTestExecution(ExtensionContext context) {
        Long start = context.getStore(NAMESPACE)
                .remove(METHOD_TIME, Long.class);

        if (start != null) {
            String name = context.getRequiredTestClass()
                    .getSimpleName() + "."
                    + context.getRequiredTestMethod().getName();

            print(context, "METHOD_TIME", name, start);
        }
    }

    private static void print(
            ExtensionContext context,
            String kind,
            String name,
            long start) {

        double ms = (System.nanoTime() - start) / 1_000_000.0;

        String formatted =
                String.format(Locale.ROOT, "%.3f", ms);
        context.publishReportEntry(kind + ".ms", formatted);

        System.out.printf(
                Locale.ROOT,
                "%s name=%s elapsed_ms=%s%n",
                kind, name, formatted);
    }
}
~~~

The extension avoids a shared static mutable stopwatch; `ExtensionContext.Store` scopes timestamps to class/method. `publishReportEntry` emits metadata for JUnit Platform, while `System.out.printf` lets Gradle display results when `showStandardStreams=true`.

**Interpretation:** `METHOD_TIME` excludes `@BeforeEach` and `@AfterEach`. `CLASS_TIME` depends on extension ordering and may omit part of Spring context initialization. It measures duration within the JUnit class lifecycle, not the entire Test task.

## 16. ContextLookupTimingListener.java: measuring the Spring context cache boundary

File `src/test/java/example/perf/ContextLookupTimingListener.java`:

~~~java
package example.perf;

import java.util.Locale;

import org.springframework.context.ApplicationContext;
import org.springframework.core.Ordered;
import org.springframework.test.context.TestContext;
import org.springframework.test.context.support.AbstractTestExecutionListener;

public final class ContextLookupTimingListener
        extends AbstractTestExecutionListener {

    @Override
    public int getOrder() {
        return Ordered.HIGHEST_PRECEDENCE;
    }

    @Override
    public void beforeTestClass(TestContext testContext) {
        long start = System.nanoTime();

        ApplicationContext context =
                testContext.getApplicationContext();

        double ms = (System.nanoTime() - start) / 1_000_000.0;

        System.out.printf(
                Locale.ROOT,
                "CONTEXT_LOOKUP_OR_LOAD class=%s "
                + "elapsed_ms=%.3f identity=%x%n",
                testContext.getTestClass().getSimpleName(),
                ms,
                System.identityHashCode(context));
    }
}
~~~

This listener is merged with Spring's default listeners in the two context test classes. On a first cache miss it includes load/refresh time; on a subsequent run with the same key it returns quickly.

**Limitation:** `getApplicationContext()` in the listener eagerly triggers context initialization on cache miss. `identityHashCode` only helps recognize objects within the same process—it is not a global identifier and has collision risk. Read cache DEBUG logs as well rather than concluding refresh counts from identity alone.

## 17. PureUnitTimingTest.java: 2 methods without loading Spring

~~~java
package example.perf;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("unit")
@ExtendWith(TimingExtension.class)
class PureUnitTimingTest {

    @Test
    void returnsGreeting() {
        GreetingService raw = new GreetingService();
        assertEquals("Hello, Ada", raw.greet("Ada"));
    }

    @Test
    void rejectsNullName() {
        GreetingService raw = new GreetingService();
        assertThrows(NullPointerException.class,
                () -> raw.greet(null));
    }
}
~~~

The test uses a plain Java object. If business logic needs no Spring DI/config, this provides a useful baseline; do not add `@SpringBootTest` just to test a pure function.

## 18. ContextGroupATest.java: 2 @SpringBootTest methods

~~~java
package example.perf;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.TestExecutionListeners;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("context")
@ExtendWith(TimingExtension.class)
@TestExecutionListeners(
    listeners = ContextLookupTimingListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
@SpringBootTest(
    classes = BenchmarkApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.autoconfigure.exclude="
        + "org.springframework.boot.autoconfigure.jdbc."
        + "DataSourceAutoConfiguration"
    })
class ContextGroupATest {

    @Autowired GreetingService greeting;
    @Autowired ApplicationContext context;

    @Test
    void managedBeanReturnsGreeting() {
        assertEquals("Hello, Ada", greeting.greet("Ada"));
    }

    @Test
    void beanExistsInContext() {
        assertTrue(context.containsBean("greetingService"));
    }
}
~~~

With `WebEnvironment.NONE`, no embedded HTTP server starts. `DataSourceAutoConfiguration` is excluded in the context test because this group has no PostgreSQL. `MERGE_WITH_DEFAULTS` retains Spring's `DependencyInjectionTestExecutionListener` and other default listeners.

## 19. ContextGroupBTest.java: 2 methods sharing the same cache key

~~~java
package example.perf;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.TestExecutionListeners;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@Tag("context")
@ExtendWith(TimingExtension.class)
@TestExecutionListeners(
    listeners = ContextLookupTimingListener.class,
    mergeMode = TestExecutionListeners.MergeMode.MERGE_WITH_DEFAULTS)
@SpringBootTest(
    classes = BenchmarkApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    properties = {
        "spring.autoconfigure.exclude="
        + "org.springframework.boot.autoconfigure.jdbc."
        + "DataSourceAutoConfiguration"
    })
class ContextGroupBTest {

    @Autowired GreetingService greeting;
    @Autowired ApplicationContext context;

    @Test
    void anotherManagedCallWorks() {
        assertEquals("Hello, Linh", greeting.greet("Linh"));
    }

    @Test
    void serviceBeanAlsoExistsHere() {
        assertTrue(context.containsBean("greetingService"));
    }
}
~~~

Both `@SpringBootTest` annotations share identical `classes`, `webEnvironment`, and `properties`, with no `@DirtiesContext` or differing mock beans. Within a single test JVM, the second class using a compatible key can **cache HIT**.

**Never assert that class B runs after class A** or that a context must load under N milliseconds: test discovery/order, machine speed, and GC vary. Measure via logs, correlating cache hits/misses and identity within a run.

## 20. PostgresContainerTimingTest.java: 1 opt-in Docker benchmark

File `src/test/java/example/perf/PostgresContainerTimingTest.java`:

~~~java
package example.perf;

import java.util.Locale;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestReporter;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.boot.WebApplicationType;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

import org.testcontainers.containers.PostgreSQLContainer;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("container")
@ExtendWith(TimingExtension.class)
class PostgresContainerTimingTest {

    @Test
    @EnabledIfEnvironmentVariable(
        named = "RUN_DOCKER_BENCH", matches = "true")
    void measuresContainerBootQueryAndStop(
            TestReporter reporter) {

        PostgreSQLContainer<?> postgres =
                new PostgreSQLContainer<>("postgres:16-alpine");

        try {
            long containerStart = System.nanoTime();
            postgres.start();
            publish(reporter,
                    "container.start.ms", containerStart);

            long bootStart = System.nanoTime();
            try (ConfigurableApplicationContext context =
                    new SpringApplicationBuilder(
                            BenchmarkApplication.class)
                        .web(WebApplicationType.NONE)
                        .properties(
                            "spring.main.banner-mode=off",
                            "spring.datasource.url="
                                    + postgres.getJdbcUrl(),
                            "spring.datasource.username="
                                    + postgres.getUsername(),
                            "spring.datasource.password="
                                    + postgres.getPassword())
                        .run()) {

                publish(reporter,
                        "spring.run.ms", bootStart);

                JdbcTemplate jdbc =
                        context.getBean(JdbcTemplate.class);

                long queryStart = System.nanoTime();
                Integer result = jdbc.queryForObject(
                        "SELECT 1", Integer.class);

                publish(reporter,
                        "jdbc.first_query.ms", queryStart);

                assertEquals(1, result);
            }
        } finally {
            long stopStart = System.nanoTime();
            postgres.stop();
            publish(reporter,
                    "container.stop.ms", stopStart);
        }
    }

    private static void publish(
            TestReporter reporter, String metric, long start) {

        double ms = (System.nanoTime() - start) / 1_000_000.0;
        String value =
                String.format(Locale.ROOT, "%.3f", ms);

        reporter.publishEntry(metric, value);
        System.out.printf(
                Locale.ROOT,
                "BENCH metric=%s elapsed_ms=%s%n",
                metric, value);
    }
}
~~~

This test **omits `@SpringBootTest`**, because `SpringExtension` would construct the context before the test method begins. It explicitly starts PostgreSQL and then calls `SpringApplicationBuilder.run()` to time Boot startup separately against an already-ready database.

The context is closed via try-with-resources **before** the container stops. That is proper ownership: beans/DataSource can clean up while the DB is still alive.

### 20.1 When Docker is unavailable

`@EnabledIfEnvironmentVariable` causes the Docker test to be **SKIPPED** unless `RUN_DOCKER_BENCH=true` is set; the remaining 6 tests run without Docker. Never report the Docker benchmark as PASS when the case was skipped. When env=true yet Docker is unavailable, the test fails and surfaces the real error.

### 20.2 What do the measurements mean?

- `container.start.ms`: can include image pull, Docker startup, and wait strategy.
- `spring.run.ms`: from before `SpringApplicationBuilder.run` until Boot context is ready, not just `refresh()`.
- `jdbc.first_query.ms`: can include lazy pool connection setup, not pure SQL execution.
- `container.stop.ms`: cleanup from Testcontainers, excluding any out-of-process cleanup.
- `CLASS_TIME` measures the JUnit class and may include extra setup/teardown overhead.
- `METHOD_TIME` measures the method body including start/run/query/stop because all reside inside `@Test`. **Do not add `METHOD_TIME` to the components above**.

### 20.3 Prerequisites to run

Requires a running Docker daemon, ability to pull `postgres:16-alpine`, JDK 17+, and the PostgreSQL JDBC driver. Spring Boot auto-configures `DataSource`/`JdbcTemplate` because the JDBC starter and real URL/credentials are present. `SELECT 1` checks basic connectivity and does **not** represent Flyway/Hibernate cost or heavy workloads.

## 21. Running the three measurement groups

Linux/macOS:

~~~bash
./gradlew unitBench
./gradlew contextBench
RUN_DOCKER_BENCH=true ./gradlew containerBench
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat unitBench
.\gradlew.bat contextBench

$env:RUN_DOCKER_BENCH="true"
.\gradlew.bat containerBench
Remove-Item Env:RUN_DOCKER_BENCH
~~~

Run all:

~~~bash
./gradlew test
~~~

If the project lacks a wrapper yet, generate the Gradle wrapper or use a compatible Gradle binary. `RUN_DOCKER_BENCH` is an **environment variable**, not a Gradle `-P` property.

If Gradle marks a task `UP-TO-DATE`, no new measurements will be produced. To force the task to re-run:

~~~bash
./gradlew contextBench --rerun-tasks --max-workers=1
~~~

**Note:** `--rerun-tasks` can force dependency tasks to recompile; do not compare the entire command's wall time against a run that executed only the Test task. Inspect context/listener logs for isolated numbers.

### 21.1 Expected results, not executed stdout

| Group | Tests | Expected |
| --- | ---: | --- |
| unitBench | 2 | 2 PASS |
| contextBench | 4 | 4 PASS, with cache lookup/load logs |
| containerBench, env disabled | 1 | 1 SKIPPED |
| containerBench, Docker available and env=true | 1 | 1 PASS if database/config valid |

`elapsed_ms` values are computed **at runtime** and depend on the machine. This lesson provides no fabricated measurements and does not claim Gradle was executed.

## 22. Reading HTML, JUnit XML, and Gradle profiles

Gradle generates HTML/JUnit XML reports per Test task:

~~~text
build/reports/tests/unitBench/index.html
build/reports/tests/contextBench/index.html
build/reports/tests/containerBench/index.html

build/test-results/unitBench/TEST-*.xml
build/test-results/contextBench/TEST-*.xml
build/test-results/containerBench/TEST-*.xml
~~~

JUnit XML testcase `time` reflects Gradle/JUnit reporting semantics, not `container.start.ms` or `context.refresh.ms`. Under parallelism, **the sum of `testcase.time` can exceed task wall time** because tests run concurrently.

**Hypothetical data example solely to illustrate reporting**:

| Group | Sum case time | Gradle task wall | Context misses | Container starts |
| --- | ---: | ---: | ---: | ---: |
| Unit | 0.4s | 3.1s | 0 | 0 |
| Context | 2.0s | 9.5s | 1 | 0 |
| Container | 6.2s | 12.0s | 0 in Spring Test cache | 1 |

Do not infer from this hypothetical table that real applications have these figures. The Docker test's Spring TestContext cache misses show 0 because it uses `SpringApplicationBuilder` directly, even though it still creates **one new context**.

### 22.1 Gradle --profile

~~~bash
./gradlew contextBench --profile
~~~

Gradle `--profile` reports **Gradle task durations**, useful for separating compilation from the Test task. It does not automatically break out context loading, container startup, or JDBC migrations. Build scans/Develocity, if used by your organization, provide deeper timelines, though privacy/authorization should be checked before uploading logs/secrets.

## 23. Spring Boot ApplicationStartup and StartupStep

Spring Framework offers `ApplicationStartup` to record `StartupStep` events during startup/bean initialization. Spring Boot 3.5 provides `BufferingApplicationStartup`.

Instrumentation sample:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.context.metrics.buffering.BufferingApplicationStartup;

SpringApplication app =
        new SpringApplication(BenchmarkApplication.class);

app.setApplicationStartup(
        new BufferingApplicationStartup(2048));

app.run(args);
~~~

This is a **standalone fragment**, requiring `BenchmarkApplication` and `args`. When run outside the Docker test, the app includes the JDBC starter so it still needs a URL/credentials or auto-config exclusion.

`BufferingApplicationStartup` buffers events for later inspection; the Actuator startup endpoint can expose them when Actuator/web dependencies are added and enabled. If an app has thousands of beans, a 2048-step buffer may not hold every event. Adjust capacity accordingly.

### 23.1 Do not sum startup step durations

A `spring.beans.instantiate` step may be nested inside a broader refresh step. Spans/steps carry `parentId` and can overlap. Summing all durations will **double-count**.

`ApplicationStartup` describes **Spring startup steps**, excluding Docker image pulls before `SpringApplication.run`. To locate slow-initializing beans, combine `StartupStep`s with JFR/logs; to time Docker startup, keep a separate stopwatch.

## 24. Actuator startup endpoint and metrics

With `spring-boot-starter-actuator` and `BufferingApplicationStartup` configured, Actuator can expose:

~~~text
GET /actuator/startup
POST /actuator/startup
~~~

GET retrieves a snapshot, while POST can drain recorded steps depending on Boot version. Enable HTTP exposure according to policy:

~~~properties
management.endpoints.web.exposure.include=health,info,startup
~~~

**The current mini-project has no Actuator/Web starter**, so this endpoint **does not work out of the box**; this is extension guidance. In production, the startup endpoint can reveal bean names and configuration details and must be protected via network/security controls.

Spring Boot Actuator/Micrometer also provides metrics:

- `application.started.time`: duration until `ApplicationStartedEvent`, after context refresh.
- `application.ready.time`: duration until `ApplicationReadyEvent`, after `ApplicationRunner`/`CommandLineRunner`.

If a runner warms a cache for 10s, ready time will exceed started time. If Docker starts prior to `SpringApplication`, Boot startup metrics **do not** include image pull. Do not confuse these values with the TestContext cache lookup timer.

## 25. Java Flight Recorder to locate bottlenecks

JDK 17 includes **Java Flight Recorder (JFR)**; Spring supports `FlightRecorderApplicationStartup`:

~~~java
import org.springframework.core.metrics.jfr.FlightRecorderApplicationStartup;

SpringApplication app =
        new SpringApplication(BenchmarkApplication.class);

app.setApplicationStartup(
        new FlightRecorderApplicationStartup());

app.run(args);
~~~

Run an executable JVM with recording:

~~~bash
java -XX:StartFlightRecording=filename=startup.jfr,duration=30s -jar app.jar
~~~

This is a **methodology example**, not a run output. To capture JFR in Gradle tests, pass JVM args **to the forked Test worker** and use a unique filename per fork to prevent overwriting. JFR helps inspect class loading, allocations, CPU/GC, blocking, and startup steps. However, profiling itself adds overhead; keep an unprofiled baseline for comparison.

## 26. Aligning Testcontainers lifecycle with the context cache

### 26.1 Static @Container vs. instance @Container

Illustrative snippet:

~~~java
@Testcontainers
class RepositoryIntegrationTest {
    @Container
    static PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

A static `@Container` typically starts before tests in **the class** and stops after the class. An instance `@Container` starts/stops per method. Both differ greatly from "a single DB for the entire suite". The Testcontainers JUnit 5 extension recommends sequential execution; parallel lifecycles carry risk.

### 26.2 Cached context pointing at a stopped container

A critical failure mode:

~~~text
Class A: static DB container A starts
   +-- @SpringBootTest context X uses JDBC URL of A
Class A ends -> JUnit stops container A
Class B gets cached context X
   +-- DataSource still points at stopped container A
   +-- JDBC query fails
~~~

If a context needs to live across multiple classes, ensure the container lives at least as long as the context. Spring Boot 3.5 supports Spring-managed container beans as well as `@ImportTestcontainers` and `@ServiceConnection`.

### 26.3 @ServiceConnection

Snippet:

~~~java
@Testcontainers
@SpringBootTest
class JdbcIntegrationTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> db =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
~~~

Requires adding:

~~~groovy
testImplementation 'org.springframework.boot:spring-boot-testcontainers'
~~~

`@ServiceConnection` lets Boot generate JDBC connection details, cutting dynamic URL boilerplate. However, **static `@Container` lifecycle is still owned by Testcontainers/JUnit**, so a cached context in another class still needs compatible lifecycle design.

### 26.4 Container as a Spring bean

A pattern tying container lifetime to the context:

~~~java
@TestConfiguration(proxyBeanMethods = false)
class SharedDbTestConfig {

    @Bean
    @ServiceConnection
    PostgreSQLContainer<?> db() {
        return new PostgreSQLContainer<>("postgres:16-alpine");
    }
}
~~~

When imported into `@SpringBootTest` with Boot Testcontainers support, the container bean starts and stops alongside the context instead of closing right at the end of a test class. This is an **extension pattern**, not part of the 7-test runnable codebase.

### 26.5 Dynamic properties

When using `@DynamicPropertySource`:

~~~java
@DynamicPropertySource
static void postgresProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", db::getJdbcUrl);
    registry.add("spring.datasource.username", db::getUsername);
    registry.add("spring.datasource.password", db::getPassword);
}
~~~

Requires static `db`, imports, and matching context. The cache key evaluates the dynamic-property context customizer **without evaluating every future value returned by the supplier**. If a subclass swaps the container/port between tests while the Spring context is reused, it may point to a stale URL. Design explicit isolation or use `@DirtiesContext` when genuinely needed.

## 27. Choosing test slices to reduce Spring context startup

| What is being verified | Appropriate layer | Full context needed? |
| --- | --- | --- |
| Pure parser/domain service | JUnit + fakes/Mockito | No |
| JSON serialize/deserialize | `@JsonTest` | No |
| MVC mapping/validation | `@WebMvcTest` | MVC slice |
| JPA repository/query | `@DataJpaTest` | JPA slice + DB |
| REST client mapping | `@RestClientTest` | Client slice |
| Full security/transactions/events/bean wiring | `@SpringBootTest` | Usually yes |
| Real PostgreSQL migrations/SQL | Testcontainers + integration | Yes, real DB |
| End-to-end request path | Staging-like test | Multiple services |

A slice test can be faster than a full-context test, yet if every class spawns a **distinct slice context** due to differing mocks/imports/profiles, the overall suite stays slow. Measure cache misses and startup duration for **the entire group**, not just one test class.

Never downgrade full integration/security tests into pure unit tests just to boast speed if doing so drops vital coverage.

## 28. Isolation and cleanup determine whether reuse is safe

Separate two kinds of state:

- **Context topology:** keep stable so the Spring cache reuses it.
- **Mutable data/resources:** reset in `@BeforeEach`/`@AfterEach` or at the proper test transaction boundary.

Items needing cleanup:

- DB rows/fixtures and cache entries.
- Message subscriptions, queues/offsets.
- `SecurityContext`/MDC/`ThreadLocal` tenant info.
- HTTP server/client resources.
- Test-created task scheduler/executor tasks.
- Test-owned Testcontainers resources.
- Mock state/invocation histories.

**Do not shut down a Spring-managed shared `DataSource`/executor bean in `@AfterEach`**, because the cached context may reuse that bean. Clean up test-owned tasks/data and let Spring close beans when the context closes. Use `@DirtiesContext` when state cannot be safely restored.

## 29. Cold and warm benchmarks: rules for fair comparisons

A reproducible benchmark should record:

| Metadata | Reason |
| --- | --- |
| Git SHA | Same code/test version |
| JDK vendor/version | Different JIT/GC/classloader |
| Spring Boot/Framework | Different auto-config/cache behavior |
| Gradle and test JVM settings | Different forks/parallel/reporting |
| Docker/Testcontainers versions | Different lifecycle/image policies |
| PostgreSQL image/tag/digest | Different image layers/startup |
| CPU/RAM/OS/architecture | Different baseline performance |
| Container image pre-pulled? | Distinguishes cold/warm |
| Gradle daemon/caches | Assesses compile/build overhead |
| Context maxSize/hit/miss | Measures reuse degree |
| Number of tests/contexts | Do not optimize by dropping tests |
| Runner count and retries | Adds extra startup work |
| Profiling/logging enabled? | Instrumentation overhead |
| Sample count, median, p95 | Prevents cherry-picking |

Never compare a **laptop with a warm Docker image** against a **cold CI agent pulling images** and blame the entire difference on Spring cache config.

### 29.1 Multi-run measurement procedure

1. Fix machine/config/JDK/Git SHA.
2. Perform a warm-up run if targeting warmed performance.
3. Collect multiple runs (e.g., 10) per group; label cold/warm clearly.
4. Record raw durations, context miss counts, and container start counts.
5. Compute median, p95 (stating percentile method), min/max.
6. Change **one** optimization variable per iteration.
7. Re-measure under equivalent conditions.
8. Verify functional tests remain intact with no unexpected skips.
9. If increasing parallelism, report wall time, CPU/memory contention, and duplicated context counts.
10. Never turn a benchmark into a flaky assertion on shared CI.

### 29.2 Savings illustration, not real numbers

Hypothetical:

~~~text
Before: 180 seconds, 20 context misses, 10 container starts.
After:   65 seconds,  3 context misses,  2 container starts.

Saving = 115 seconds, or about 63.9%.
~~~

These are **hypothetical numbers illustrating the calculation**; do not cite them for a real project without corresponding measurements.

## 30. Gradle forks, parallelism, and task time

Gradle supports `maxParallelForks` and `forkEvery`. Increasing `maxParallelForks` can cut wall time when spare CPU is available, but each fork has its own JVM/TestContext cache, causing a Spring context to load multiple times. Lowering `forkEvery` encourages reuse, though if test classes leak static state, a long-lived JVM may face memory pressure.

If class A and B share a context key yet Gradle schedules them on **two different forks**, a cross-class cache HIT **does not occur**. Therefore when comparing before/after:

- Record `maxParallelForks` and `forkEvery`.
- Record actual Spring context misses.
- Record number of worker JVMs.
- Record Docker/DB contention.
- Never infer wall time by summing XML `testcase.time` under parallel execution.

### 30.1 Build daemon does not preserve Spring TestContext across runs

The Gradle daemon speeds up builds/configuration/caching at the Gradle level; Spring TestContext resides in the Test worker JVM. When a new Gradle task spawns a new JVM, the context is recreated. An unusually fast run may simply mean Gradle reported `UP-TO-DATE`, not that the Boot context magically booted faster.

## 31. Database initialization and migrations

Startup time for a Boot context with a JDBC starter can include:

~~~text
SpringApplication.run()
   +-- bean definition / bean creation
   +-- DataSource/Hikari connection pool
   +-- Flyway/Liquibase migration (if enabled)
   +-- JPA/Hibernate metadata validation
   +-- repository/service bean initialization
   +-- ApplicationRunner
   +-- ApplicationReadyEvent
~~~

Some connections are created **lazily**, so the first SQL query can take longer than subsequent queries. To measure Flyway separately, use Spring `StartupStep`/metrics/logs at the migration bean, or instrument the migration phase rather than subtracting two stopwatches with different boundaries.

**Never disable migrations in benchmarks just to go faster if integration tests require a production-like schema.** Optimize by grouping tests sensibly: pure unit tests need no DB, while integration suites use accurate migrations/schemas.

## 32. Container reuse, image caching, and lifecycle

- Image caching eliminates network downloads without removing create/start/wait.
- Static containers can be shared within a class, not automatically across every class.
- `withReuse(true)`/Testcontainers reusable containers carry isolation/data leak trade-offs requiring proper Docker/test policies.
- Spring-managed container beans align lifecycle with cached contexts when implemented properly.
- Multiple parallel forks launching containers concurrently can contend for CPU/RAM and worsen benchmarks.
- Running tests on a Docker host with low quotas can cause wait strategies to time out even when code is correct.
- Never use `Thread.sleep(5000)` to "wait for DB ready"; use proper wait strategies/connection checks.
- Never reuse databases holding real customer data or secrets in unisolated pipelines.

## 33. JFR, profilers, and metrics for deep cost hunting

When `spring.run.ms` is high and the cause is unclear:

- **`BufferingApplicationStartup`**: startup step names/durations and tags.
- **`FlightRecorderApplicationStartup`/JFR**: class loading, allocations, GC, CPU, blocking.
- **Micrometer timers**: ApplicationStarted/Ready, runner/migration custom timings.
- **`Gradle --profile`**: configuration/compile/Test tasks.
- **Spring ContextCache DEBUG**: hit/miss/size statistics.
- **Testcontainers logs/Docker events**: image start/wait/cleanup.
- **JUnit XML parser**: slow methods/classes across large suites.

JFR/profiling adds overhead. Keep an unprofiled baseline and a diagnostic profiled run; never compare a JFR-instrumented run against an uninstrumented baseline to claim an improvement.

## 34. When the whole suite is slow despite fast method times

Check in order:

1. How many context misses occur and how long does each miss take?
2. Which classes spawn new contexts due to differing profiles/mocks/properties?
3. Is `@DirtiesContext` being overused?
4. How many containers is Testcontainers starting, and are images warm or cold?
5. Does the JDBC pool open connections during refresh or on the first query?
6. Are Flyway/Liquibase/Hibernate schema validations running repeatedly?
7. Does `@BeforeEach` seed too many DB rows or make HTTP calls?
8. Is `@AfterEach` cleanup/truncation slow?
9. Does the Gradle Test task spawn many processes or set a low `forkEvery`?
10. Does CPU/memory/Docker DB contention spike under parallel runs?
11. Are scheduled/async threads/consumers staying alive and holding the JVM?
12. Is excessive logging/reporting/profiling overhead present?

Never blindly "downgrade `@SpringBootTest` to unit tests" without knowing what test coverage is lost.

## 35. Common mistakes

**1. Measuring the method body and calling it context startup.**  
`BeforeTestExecution` excludes most Spring setup.

**2. Using `currentTimeMillis` to measure elapsed time.**  
Wall clocks can jump; use `nanoTime`.

**3. Asserting context startup must be under 100ms on shared CI.**  
Flaky; requires controlled SLO benchmarking.

**4. `@SpringBootTest` for a pure domain mapper.**  
No context needed; convert to a unit test when semantics allow.

**5. `@DirtiesContext` after every method.**  
Breaks cache reuse unnecessarily.

**6. Every class has a different `@MockitoBean` or `@ActiveProfiles`.**  
Increases cache key diversity and misses.

**7. Assuming the context cache shares across Gradle forks.**  
No: the static cache lives inside each test JVM.

**8. Setting `forkEvery=1` without watching context startups spike.**  
Increases both process overhead and lost reuse.

**9. Setting `maxSize` to 128 and assuming it is always faster.**  
Memory/GC/resources can worsen.

**10. Failing to distinguish an `UP-TO-DATE` task from actual test execution.**  
No new measurements exist if JUnit did not run.

**11. Thinking static `@Container` is a build-wide singleton.**  
Normally scoped per class/JUnit extension.

**12. Starting an `@BeforeAll` timer after `@Container` already started.**  
Misses container startup completely.

**13. Cached context pointing to a stopped container.**  
Align lifecycles or isolate properly.

**14. Assuming `@ServiceConnection` handles every lifecycle detail automatically.**  
It supplies connection details; container ownership still matters.

**15. Measuring `container.start` and calling it DB migration time.**  
Different stages need separate timers.

**16. Treating the first query as an SQL throughput benchmark.**  
May include lazy pool connection setup.

**17. Summing all `StartupStep` durations.**  
Nested/overlapping steps cause double counting.

**18. Reporting a false FAIL when the container test is SKIPPED by default.**  
It is an opt-in benchmark; report skips transparently.

**19. Using `TestReporter` without a log/report reader that displays it.**  
Numbers may go unseen; print logs or configure an appropriate CI listener.

**20. Enabling parallel benchmarks without isolating workers/environments.**  
Results suffer from CPU/DB contention.

**21. Hardcoding Postgres port or `localhost:5432`.**  
Testcontainers maps random ports; use `getJdbcUrl()`.

**22. Not closing context/container in `finally`.**  
Resource leaks slow down later tests.

**23. Comparing JUnit `testcase.time` sum with Gradle task wall time as the same metric.**  
They differ in lifecycle/forks/parallelism.

**24. Measuring once and claiming 70% faster.**  
Repeated samples and environment metadata are required.

**25. Fast slice test that drops security/DB integration requirements.**  
Correctness matters more than pretty speed numbers.

**26. Running cold and warm images without labeling them.**  
Cannot conclude a code change sped up startup.

**27. Disabling all caches/migrations/health checks just to cut startup.**  
Can make the suite unrepresentative of production.

**28. Not measuring teardown.**  
Non-daemon threads and Docker cleanup can keep the JVM alive long after tests finish.

## 36. Evidence-based optimization workflow

1. Capture baseline: Gradle task wall time, method times, cache hits/misses, container count.
2. Group tests into unit, MVC/JPA slices, full context, Testcontainers, and E2E.
3. Enable TestContext DEBUG and identify classes/configs causing MISSes.
4. Use the listener to time context lookup/load and the extension to time methods/classes.
5. With Docker, separate `container.start()`, `SpringApplication.run()`, and first SQL.
6. Record Git SHA, JDK/Boot/Gradle/Docker/image versions, and CI machine specs.
7. Measure cold and warm runs under identical conditions.
8. Inspect top slow classes/methods and startup steps with JFR if needed.
9. Change only one variable: reduce context key variants, test slices, fixture strategy, container lifecycle, or forks.
10. Re-measure across multiple runs; use median/p95, not just the fastest run.
11. Confirm functional assertions/test counts did not drop unintentionally.
12. If numbers improve yet tests become order-dependent, roll back the optimization.

### Final checklist

- [ ] Separated build, JUnit, context cache, container, and DB query times.
- [ ] Know default Spring cache `maxSize` 32 and key factors.
- [ ] Measured cache HIT/MISS rather than guessing from class name counts.
- [ ] Context lookup/load instrumentation is not mislabeled as a full Boot run.
- [ ] Test class/method callbacks have clear setup/teardown boundaries.
- [ ] Testcontainers image pull/start/wait runs are clearly labeled cold/warm.
- [ ] Context and container lifecycles prevent cached `DataSource` from pointing to a stopped container.
- [ ] Docker benchmark counted only when `RUN_DOCKER_BENCH=true` with real Docker available.
- [ ] JUnit XML/Gradle task reports collected per group.
- [ ] JVM forks and parallelism controlled and recorded.
- [ ] No hardcoded timing thresholds without statistical SLOs.
- [ ] No important integration tests disabled/dropped just for suite speed.
- [ ] Comparison results include code version, machine metadata, and sample count.

## 37. Conclusion

**To reduce Spring Boot test suite time, first pinpoint where time is actually spent.** The Spring TestContext cache saves refreshes when tests share configurations within the same JVM; Testcontainers adds its own Docker cost; JUnit extensions time test classes/methods; Gradle reports measure the Test task; Spring Boot `ApplicationStartup`/JFR exposes deep bean startup costs.

In the demo, the unit group uses no context, the two context groups demonstrate cache reuse, and the Docker group times container/startup/SQL/stop separately without fabricating fixed millisecond figures. In real work, measure repeatedly, label cold vs. warm, preserve test isolation, and optimize only the component proven to be the bottleneck.

### References

- [Spring Framework 6.2 — TestContext Caching](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/ctx-management/caching.html): cache keys, default `maxSize`, LRU, logging.
- [Spring Framework 6.2 — @DirtiesContext](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-dirtiescontext.html): cache invalidation.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, test slices.
- [Spring Boot 3.5 — Testcontainers](https://docs.spring.io/spring-boot/3.5/reference/testing/testcontainers.html): `ServiceConnection`, dynamic properties, context lifetimes.
- [Spring Boot 3.5 — SpringApplication](https://docs.spring.io/spring-boot/3.5/reference/features/spring-application.html): `BufferingApplicationStartup`, `FlightRecorderApplicationStartup`.
- [Spring Boot 3.5 — Startup Endpoint](https://docs.spring.io/spring-boot/3.5/api/rest/actuator/startup.html): startup steps JSON.
- [Spring Boot — Application Startup Metrics](https://docs.spring.io/spring-boot/3.5/reference/actuator/metrics.html): `application.started.time`, `application.ready.time`.
- [Testcontainers — JUnit 5 Lifecycle](https://testcontainers.com/guides/testcontainers-container-lifecycle/): static vs. instance `@Container`.
- [Testcontainers — JUnit Jupiter](https://java.testcontainers.org/test_framework_integration/junit_5/): `@Testcontainers` extension behavior.
- [Gradle — Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html): Test tasks, `maxParallelForks`, `forkEvery`, HTML/XML.
- [Gradle — Build Performance](https://docs.gradle.org/current/userguide/performance.html): profiler/task performance.
- [JUnit 5 — Extensions](https://docs.junit.org/current/user-guide/#extensions): lifecycle callbacks and `TestReporter`.
