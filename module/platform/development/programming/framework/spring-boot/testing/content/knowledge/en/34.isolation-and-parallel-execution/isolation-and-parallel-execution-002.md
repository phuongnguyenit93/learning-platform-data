# JUnit Parallel Execution and Gradle Worker Count: Isolating Spring Boot Tests Properly

## 1. One "Parallel" Setting Can Mean Three Different Things

When a Spring Boot project has hundreds of tests, enabling parallel execution typically reduces total CI time. Yet two projects both configured with "parallel=4" can behave very differently: one runs four **JVM test processes**, one runs four **JUnit worker threads inside a single JVM**, and another combines both.

So the question is not simply "is parallel enabled?" but rather:

1. **How many worker slots is Gradle allowed to use at most?** This is governed by `--max-workers`/`org.gradle.workers.max`.
2. **How many test JVMs is each Gradle `Test` task allowed to fork simultaneously?** This is controlled by `maxParallelForks`, which defaults to 1.
3. **Inside each JVM, does JUnit Jupiter allow test classes/methods to execute concurrently?** This is controlled by `junit.jupiter.execution.parallel.enabled`, execution modes, and pool strategy.
4. **Do those tests share resources?** `static` fields, Spring `ApplicationContext`, embedded databases, schemas, filesystems, Redis/Kafka, Testcontainers, ports, system properties, or a `@MockitoBean` are common conflict boundaries.
5. **If a group is unsafe in parallel, at which layer should it be isolated?** `@Execution(SAME_THREAD)`, `@ResourceLock`, `@Isolated`, `@Tag("serial")`, and a separate Gradle `Test` task do not have the same scope.

This lesson provides a concrete **configuration, verification, and debugging strategy** for Java 17+, Spring Boot 3.5.x, JUnit Jupiter, and Gradle. The hands-on section features a Gradle project with two groups: independent tests permitted to run in parallel, and a "serial" group running in a separate Gradle task. The code uses isolated state, `@TempDir`, `@ResourceLock`, `@TestInstance(PER_CLASS)`, `@Execution`, `@Isolated`, and Spring TestContext; no database, Docker, or external service is required.

## 2. Three Execution Layers: Gradle → Test JVM Process → JUnit Threads

```text
Gradle build / task graph
  |
  +-- Gradle worker slots (--max-workers, org.gradle.workers.max)
        |
        +-- Test task (e.g., :app:test)
              |
              +-- forked test JVM A  [Test task maxParallelForks]
              |      |
              |      +-- JUnit Platform / Jupiter engine
              |           +-- test class X
              |           +-- test class Y
              |           +-- method a, method b
              |                 threads per Jupiter parallel config
              |
              +-- forked test JVM B
                     |
                     +-- JUnit Platform / Jupiter engine
                          +-- other test classes/methods

Different JVM  =>  different heap/static fields/Spring ContextCache
Two threads in same JVM => can share static fields and Spring context
Two different JVMs => can still collide on DB, Redis, file paths, ports...
```

**Distinctions you must not overlook:**

| Setting | Layer affected | What does it increase? | What does it NOT guarantee? |
|---|---|---|---|
| `--max-workers=4` | Gradle build | Caps worker slots for Gradle tasks/workers | Does not automatically run one test method concurrently with another |
| `--parallel` | Gradle multi-project scheduling | Tasks from different projects may run in parallel when allowed | Not equivalent to Jupiter method concurrency |
| `Test.maxParallelForks = 2` | Gradle `Test` task | Up to two test JVMs forked concurrently, subject to total worker budget | Does not control JUnit thread count inside each JVM |
| `Test.forkEvery = 1` | Test JVM lifecycle | New fork after every test class to isolate state across classes | Does not make test methods concurrent by default |
| `junit.jupiter.execution.parallel.enabled=true` | JUnit Jupiter per JVM | Enables parallel execution support | Insufficient if execution modes remain `same_thread` |
| `mode.default=concurrent` | JUnit methods/nodes | Allows concurrent execution per mode | Does not isolate heap, static state, or DB |
| `mode.classes.default=concurrent` | JUnit top-level test classes | Allows multiple classes to be scheduled together | Does not make methods in a class concurrent if method mode is `same_thread` |
| `fixed.parallelism=2` | JUnit desired pool parallelism | Parallelism target for the engine within **one JVM** | Not `maxParallelForks`, and not strictly a hard thread cap |
| `@ResourceLock` | JUnit execution plan | Locks access to a named resource across tests coordinated by the same engine | Does not create a distributed lock across **two Gradle forked JVMs** |
| `@Isolated` | JUnit execution plan | Isolates a test class from other tests in the same execution plan | Does not prevent another JVM or another build from sharing a DB/file |

**Mental model:** Setting `maxParallelForks=2` and Jupiter `fixed.parallelism=3` can allow two JVMs, each running JUnit test nodes concurrently under a three-thread pool configuration. Do not assume the system always runs exactly `2 × 3 = 6` tests at once: ready classes, resource locks, Gradle worker budget, CPU, JUnit fork-join compensation, and the execution plan all affect it. These are **two limits at two different layers**, not a single property.

## 3. Gradle --max-workers, --parallel, and maxParallelForks

### 3.1. --max-workers: Worker Budget for the Entire Build

Gradle CLI supports:

```bash
./gradlew test --max-workers=4
```

or in the project's `gradle.properties`:

```properties
org.gradle.workers.max=4
```

`--max-workers` sets the limit on worker slots Gradle uses for the build. The default value is typically based on available processors. This worker budget is shared across many types of work—not just tests—such as compilation, Worker API tasks, and test worker processes. Hence it is incorrect to deduce "max-workers=4 means four test classes always run together".

**Note on CLI overrides:** If CI runs `./gradlew test --max-workers=1`, having `maxParallelForks=4` in the build script will not force Gradle to run four test JVMs simultaneously. Effective concurrency is bounded by Gradle's total worker budget.

### 3.2. --parallel: Parallelizing Projects, Not JUnit Methods

```bash
./gradlew test --parallel --max-workers=4
```

Depending on project structure and task dependencies, Gradle can execute `:module-a:test` and `:module-b:test` simultaneously. In a single project, `--parallel` is **not** how you enable concurrent test methods within the same class.

`--parallel` can also cause two test tasks in **two different modules** to share the same PostgreSQL container, Redis database, Redis key prefix, mock server port, or Docker network. Thus, a group of `@Isolated` tests in module A does not automatically lock module B.

### 3.3. maxParallelForks: Number of Test JVMs for One Test Task

```groovy
tasks.named('test', Test) {
    maxParallelForks = 2
}
```

This is Gradle Groovy DSL configuration. By default, `maxParallelForks=1`. When greater than 1, Gradle can distribute test classes across multiple **forked test JVMs**.

This provides **process isolation**:
- Each JVM has its own heap, classloader, `static` fields, and JVM system properties.
- One JVM's Spring TestContext cache is not shared with another JVM.
- Two JVMs can still access **external resources** such as the same database server/schema, filesystem, S3 bucket, message broker, or a fixed TCP port.
- Parts of the environment such as environment variables are inherited identically, so it does not automatically isolate database/schema names.

**Caution:** Running two JVMs does not automatically isolate all resources. This is why many CI suites pass with `maxParallelForks=1` but fail when bumped to 4: tests wipe the same table, write to a fixed file, or collide on a TCP port.

### 3.4. forkEvery: Number of Test Classes Before Recycling a JVM

```groovy
tasks.named('test', Test) {
    forkEvery = 0
}
```

In Gradle, `forkEvery=0` is the default, meaning **no limit on the number of classes before recycling the JVM due to this property**. `forkEvery=1` means after each test class finishes, a fresh JVM is started for the next class. Using it can isolate `static` state or memory leaks in legacy frameworks, but it is very expensive:
- Repeated JVM startup.
- Spring context cache cannot be reused well across classes.
- Every JVM must reload the classpath and may initialize multiple HTTP/JPA/Testcontainers clients.
- With heavy data loading, overall memory/CPU usage can still spike across multiple forks.

**Do not** use `forkEvery=1` as a "fix-all button for flaky tests" when the real cause is a shared external database or ports: fresh JVMs still contend on those resources.

### 3.5. org.gradle.test.worker Identifies a Test Process

Gradle sets the JVM system property `org.gradle.test.worker` to distinguish test worker processes. It can be used to create per-process file/directory names:

```java
String workerId =
        System.getProperty("org.gradle.test.worker", "IDE");

System.out.println("worker=" + workerId
        + ", pid=" + ProcessHandle.current().pid()
        + ", thread=" + Thread.currentThread().getName());
```

This is a fragment inside a test; when run from an IDE, the property may not be set, so `IDE` serves as a fallback. In Gradle, the worker ID identifies **test processes**, not test thread IDs. Do not hard-code `worker=1` or `worker=2` as assertions, because assignment and scheduling are not business contracts.

## 4. How Is JUnit Jupiter Parallelism Enabled?

### 4.1. Enabling the Engine Is Not Enough to Make All Tests Run Concurrently

Standard file:

```text
src/test/resources/junit-platform.properties
```

A configuration enabling concurrent methods and classes:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

JUnit Jupiter has execution modes:
- `SAME_THREAD`: node executes on the same thread as its parent node per engine rules.
- `CONCURRENT`: node is permitted to execute concurrently unless constrained by a resource lock or other configuration.

**Key point:** By default, Jupiter is sequential/same-thread. Simply setting `parallel.enabled=true` may still leave methods/classes sequential if the default modes remain `same_thread`.

### 4.2. Three Common Configuration Patterns

| Goal | `mode.default` | `mode.classes.default` | Meaning |
|---|---|---|---|
| All tests sequential by default in one JVM | `same_thread` | `same_thread` | Safe default |
| Concurrent classes, sequential methods within each class | `same_thread` | `concurrent` | Often a good starting point for isolated Spring integration tests |
| Sequential classes, concurrent methods within a class | `concurrent` | `same_thread` | Suitable for independent test classes without shared mutable fixtures |
| Both classes and methods concurrent | `concurrent` | `concurrent` | Requires the highest level of isolation |

You can override the default choice for a class or method with `@Execution(ExecutionMode.CONCURRENT)` or `@Execution(ExecutionMode.SAME_THREAD)`.

**Important exception:** JUnit applies specific default behavior to test classes using `@TestInstance(PER_CLASS)` or `@TestMethodOrder`; do not just inspect the default mode and assume methods will run in parallel. If you truly want concurrency in a `PER_CLASS` class, annotate `@Execution(CONCURRENT)` and ensure the shared instance is thread-safe. Never combine `@TestMethodOrder` with concurrent methods when test logic depends on order.

### 4.3. fixed and dynamic Strategies

JUnit reads configuration parameters:

```properties
# Target two worker threads for the JUnit engine in each JVM
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=2

# Java 17 projects can cap pool size
junit.jupiter.execution.parallel.config.fixed.max-pool-size=2
```

Or:

```properties
junit.jupiter.execution.parallel.config.strategy=dynamic
junit.jupiter.execution.parallel.config.dynamic.factor=0.5
```

- `fixed`: requests an explicit desired parallelism, fitting CI jobs with fixed CPU budgets.
- `dynamic`: computed from available processors × factor; default factor is usually 1.
- `custom`: allows a custom `ParallelExecutionConfigurationStrategy`; unnecessary for most projects.

**Do not confuse parallelism with a hard maximum concurrency.** JUnit Jupiter runs on `ForkJoinPool`; blocking/synchronization can cause the pool to spawn extra threads depending on implementation. `fixed.max-pool-size` provides an additional cap when needed, but does not turn improperly synchronized tests into safe ones. Observe actual execution in CI instead of asserting the thread count always equals a fixed number.

### 4.4. System Properties, junit-platform.properties, and Overrides

JUnit Platform reads configuration parameters from several sources: Launcher request parameters, JVM system properties, `junit-platform.properties` on the test runtime classpath, and defaults. In Gradle, a `Test` task can override them for a group of tests:

```groovy
tasks.named('test', Test) {
    systemProperty 'junit.jupiter.execution.parallel.enabled', 'true'
}
```

This is useful when `serialTest` needs to run from the same source set while **disabling concurrency** without editing the suite-wide properties file. Note that IDEs may use a different JUnit launcher config than Gradle; when debugging test concurrency, record the exact command/build task executed.

## 5. What Can Run Concurrently and What Needs Locking?

### 5.1. Test Instance Lifecycle and Shared State

With JUnit Jupiter's default `@TestInstance(PER_METHOD)`, each test method gets its own test class instance, so instance fields are not automatically shared across methods. However, **static fields, singletons, Spring beans, DBs, and external resources** remain shared.

With `@TestInstance(PER_CLASS)`, one instance holds multiple test methods; if `@Execution(CONCURRENT)` is enabled, instance fields are accessed concurrently.

Example of an improperly used counter:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.CONCURRENT)
class UnsafeCounterExample {
    int value = 0;

    @Test
    void a() { value++; }

    @Test
    void b() { value++; }
}
```

This is an **illustrative anti-pattern**, not part of the runnable project. `value++` performs a read, add, and write—it is **not atomic**. Updates can be lost. Use `AtomicInteger`, immutable fixtures, locks, or proper isolation; best of all, avoid shared mutable state between tests.

### 5.2. @ResourceLock Coordinates Resource Usage Within the Same JVM

JUnit provides `@ResourceLock`:

```java
@Test
@ResourceLock(
    value = Resources.SYSTEM_PROPERTIES,
    mode = ResourceAccessMode.READ_WRITE)
void updatesSystemProperty() {
    // Only tests in the same Jupiter execution plan
    // declaring the same resource lock are coordinated.
}
```

Here `Resources.SYSTEM_PROPERTIES` is a standard resource name provided by JUnit; `ResourceAccessMode.READ_WRITE` excludes other tests declaring conflicting locks. `READ` allows multiple readers concurrently, but prevents a writer on the same resource from running in parallel.

**Locks also apply to lifecycle callbacks** such as `@BeforeEach`/`@AfterEach` for that test method. Yet this is strictly **JVM/engine-level coordination**, not a cross-JVM file lock or DB lock.

If Gradle has `maxParallelForks=4`, four independent JVMs **do not coordinate** `@ResourceLock("shared-db")` with each other. To get exclusive access to a shared PostgreSQL schema, separate the test task/fork, use separate schemas/databases, or use a genuine external coordination mechanism.

### 5.3. How Far Does @Isolated Reach?

`@Isolated` on a Jupiter test class requests that it run separately from other tests in the same **JUnit execution plan**. However:
- It does not forbid Gradle from spawning another forked JVM.
- It does not lock tasks of other modules when `--parallel` is enabled.
- It does not prevent another CI process from using the same DB/schema.
- It does not replace resource cleanup and transaction isolation.

Therefore `@Isolated` is a useful tool **at the JUnit layer**, whereas a serial `Test` task with `maxParallelForks=1` and JUnit parallel disabled provides isolation **at the Gradle task layer**.

### 5.4. @Execution(SAME_THREAD) Solves Only Part of the Problem

A test class with:

```java
@Execution(ExecutionMode.SAME_THREAD)
class ClassWithSequentialMethods {
    // Methods of this class are scheduled sequentially
    // per execution mode; other classes can still run concurrently.
}
```

This snippet illustrates the execution mode; it is not a standalone Java file. It protects methods of **that class itself** from running concurrently under JUnit policy, but **does not** prevent another class in the same JVM or another fork from wiping its database or file.

## 6. Spring TestContext Cache and Parallel Execution

Spring Boot tests frequently use `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, and features from the Spring TestContext Framework. Multiple test classes with identical context configurations can share a **cached ApplicationContext within the same JVM**.

This speeds up startup, but introduces risks under concurrency:
- Singleton beans with mutable fields may be called by multiple methods/classes simultaneously.
- In-memory caches, queues, static event probes, and fake clocks may be reset by one test while another is using them.
- One test using `@DirtiesContext` can mark the old context closed while another test is still using it.
- Mockito overrides (`@MockitoBean`, `@MockitoSpyBean`) may have stubbing/verification/reset state unsuitable for concurrent context sharing.
- A shared embedded DB or real DB schema can experience competing row deletes/inserts.
- `@DynamicPropertySource`/Testcontainers configurations can direct multiple tests to the same host/port/schema.

Spring Framework **advises against running tests in parallel** when they use `@DirtiesContext`, `@MockitoBean`/`@MockitoSpyBean`, depend on execution ordering, or mutate shared DBs/files/brokers. This guidance is based on race potential, not a claim that every `@SpringBootTest` must be sequential. With stateless singletons and isolated data, parallel Spring tests are completely valid.

### 6.1. The Context Cache Lives Inside One JVM

```text
Gradle fork A: ApplicationContext cache A
  SpringContextSafeTest-1
  SpringContextSafeTest-2

Gradle fork B: ApplicationContext cache B
  AnotherSpringTest

Cache A and cache B do not share Java objects.
Databases/servers outside the JVM can still be shared by both.
```

Increasing `maxParallelForks` can increase how many times similar contexts are bootstrapped, leading to:
- CPU/memory spikes from multiple Hibernate/JPA contexts.
- Multiple Hikari pools opening connections simultaneously.
- Duplicate embedded Kafka/Redis/test servers.
- Testcontainers start/stop contention.
- Running **slower** despite more forks because the system gets overloaded.

Do not tune strictly by CPU count; account for database connection limits, RAM, Docker resources, and initialization costs.

### 6.2. @DirtiesContext in a Concurrent Suite

A test using:

```java
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
```

instructs Spring to close/remove the context when appropriate. If another test is using the same cached context on another thread, it can fail with "ApplicationContext no longer active". Spring docs recommend **excluding such tests from parallel runs**, or replacing state resets with narrower isolation mechanisms.

`@DirtiesContext` does not fix a shared external database or filesystem; it only affects the Spring context lifecycle.

### 6.3. @MockitoBean and Mock Reset

In Boot 3.5 / Spring Framework 6.2, `@MockitoBean`/`@MockitoSpyBean` provide test overrides. If a cached context holds a mock and two tests stub/verify/reset that mock concurrently, race conditions can cause false positives or false negatives. Place this group in a serial task or design appropriate test-specific contexts/fixtures.

Do not assume `@MockitoBean` is a thread-local mock per JUnit method. It is a bean override **inside the ApplicationContext**.

### 6.4. @Transactional in Tests Is Not Global Isolation

When a Spring test method is marked `@Transactional`, TestContext opens a **test-managed transaction** for the running thread and rolls it back by default. Two concurrent tests can have two separate transactions, yet:
- Both may still share the **same database/schema**.
- Unique constraints can collide if test rows use the same business ID.
- `TRUNCATE`, DDL, or manual out-of-transaction cleanup can destroy another test's data.
- Secondary threads from `@Async` or a real HTTP server **do not automatically join** the test thread's transaction.
- `assertTimeoutPreemptively` can run the test block on a different thread, bypassing the transaction boundary and committing data unexpectedly.

Do not treat `@Transactional` as a license to run every DB test in parallel. Use unique IDs, separate schemas/databases, or a serial lane for tests that mutate global state.

## 7. Recommended Strategy Before Enabling Parallel Execution

A controlled rollout process:

1. **Measure the sequential baseline**: `test` duration, actual executed test method count, peak RAM/CPU, and existing flakiness.
2. **Categorize tests**: pure unit tests; Spring slice tests; full-context tests; shared external resources.
3. **Enable parallelism at one layer first**: usually concurrent classes with sequential methods per class, or 2 Gradle forks for independent tests.
4. **Isolate shared resources**: `@TempDir`, separate DB schemas, unique queue/topic prefixes, random ports, unique test data.
5. **Split out a serial lane**: `@DirtiesContext`/Mockito overrides, migrations/DDL, globally shared fixtures, ordered tests.
6. **Use @ResourceLock where meaningful within one JVM**; do not treat it as a distributed lock.
7. **Verify empirically**: logs with worker ID/PID/thread name, Gradle/JUnit reports, repeated CI runs, CPU/RAM.
8. **Increase concurrency gradually**: 1→2 forks, 1→2 JUnit threads, measuring benefit/cost.
9. **Stop tuning when contention rises**: more forks can slow down DB pools, Testcontainers, or the filesystem.
10. **Preserve sequential debugging capability**: a task/command to disable parallelism quickly during failure investigations.

**Key takeaway:** Maximum concurrency is not the end goal. The goal is **reducing wall-clock time while keeping results trustworthy and maintaining test isolation**.

## 8. Sample Project: Java 17+ / Spring Boot 3.5 / Gradle

The project below intentionally distinguishes:
- Two Gradle `test` JVM forks.
- Concurrent JUnit classes, `same_thread` methods by default; select classes opting into concurrent methods.
- Shared system properties locked via `@ResourceLock`.
- `@TestInstance(PER_CLASS)` safely using `AtomicInteger`.
- `@TempDir` creating per-method files instead of one shared path.
- `@SpringBootTest` with a stateless singleton permitted to run concurrently.
- A test using `@DirtiesContext` placed in a separate `serialTest` Gradle task.
- `org.gradle.test.worker`/PID for observing process isolation.

Structure:

```text
build.gradle
src/main/java/com/example/paralleldemo/
    ParallelDemoApplication.java
    MoneyCalculator.java
src/test/resources/
    junit-platform.properties
src/test/java/com/example/paralleldemo/
    ConcurrentMoneyTest.java
    SpringContextSafeTest.java
    ProtectedSystemPropertyTest.java
    PerClassSafeStateTest.java
    UniqueTempDirectoryTest.java
    GradleWorkerInfoTest.java
    IsolatedRuntimeTest.java
    SerialSpringContextTest.java
```

### 8.1. build.gradle: Two Test Tasks with Different Policies

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.8'
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
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    // Do not run tests tagged as serial in this lane.
    useJUnitPlatform {
        excludeTags 'serial'
    }

    // Up to 2 forked test JVMs (subject to --max-workers).
    maxParallelForks = 2

    // Do not recycle the test JVM after each test class.
    forkEvery = 0

    // RAM budget applied per forked test JVM.
    maxHeapSize = '512m'

    testLogging {
        events 'failed'
    }
}

tasks.register('serialTest', Test) {
    description = 'Run tests with global/shared Spring state sequentially'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath

    useJUnitPlatform {
        includeTags 'serial'
    }

    // Only one test JVM at a time for serialTest.
    maxParallelForks = 1

    // Override junit-platform.properties inside this JVM.
    systemProperty(
        'junit.jupiter.execution.parallel.enabled', 'false')

    // If check pulls both test and serialTest, run serial after test.
    shouldRunAfter tasks.named('test')

    testLogging {
        events 'failed'
    }
}

tasks.named('check') {
    dependsOn tasks.named('serialTest')
}
```

**Read carefully:**
- `test` uses up to 2 forks and excludes tests with `@Tag("serial")`.
- `serialTest` reuses the same test source set output/classpath, but selects only the `serial` tag and sets `maxParallelForks=1`.
- `serialTest` **disables Jupiter parallelism inside the JVM via a system property**, not merely reducing forks.
- `check` executes both the default lane and `serialTest` via the dependency setup.
- `shouldRunAfter` is an **ordering hint**, not a distributed lock across builds or other projects.
- `maxHeapSize='512m'` applies **per JVM fork**, not as a total memory cap across all forks. This number is for demo purposes, not standard sizing for every Spring app.

**Note on multi-project builds:** If multiple modules have test tasks and Gradle runs `--parallel`, a `serialTest` in one module does not block `test` in another module. If modules share a DB, separate environments/schemas or control task ordering/global CI concurrency according to business needs.

### 8.2. junit-platform.properties: JUnit Parallelism per Fork

File `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=same_thread
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=2
junit.jupiter.execution.parallel.config.fixed.max-pool-size=2
```

This configuration means:
- Top-level test **classes** may run concurrently.
- **Methods within the same class** default to same-thread.
- Classes wanting concurrent methods can add `@Execution(CONCURRENT)`.
- Desired JUnit parallelism within each JVM is 2; unrelated to `maxParallelForks=2`.
- `serialTest` overrides `enabled` to false, so JUnit parallelism is disabled in the serial JVM.

Do not place this file in `src/main/resources`; it belongs on the test classpath. When running from an IDE with a different Launcher config, verify the IDE reads the proper test resource.

### 8.3. Spring Boot Application

File `src/main/java/com/example/paralleldemo/ParallelDemoApplication.java`:

```java
package com.example.paralleldemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ParallelDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                ParallelDemoApplication.class, args);
    }
}
```

The demo includes neither `starter-web` nor `starter-data-jpa`, so Spring context bootstrap is lightweight and opens no HTTP server or database.

### 8.4. Stateless Service: Valid for Parallel Tests

File `src/main/java/com/example/paralleldemo/MoneyCalculator.java`:

```java
package com.example.paralleldemo;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.Objects;

import org.springframework.stereotype.Service;

@Service
public class MoneyCalculator {

    public BigDecimal afterDiscount(
            BigDecimal price,
            int percent) {

        Objects.requireNonNull(price, "price");

        if (price.signum() < 0) {
            throw new IllegalArgumentException(
                    "price must not be negative");
        }

        if (percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                    "percent must be between 0 and 100");
        }

        BigDecimal multiplier =
                BigDecimal.valueOf(100 - percent);

        return price.multiply(multiplier)
                .divide(
                    BigDecimal.valueOf(100),
                    2,
                    RoundingMode.HALF_UP);
    }
}
```

`MoneyCalculator` has no mutable instance fields, writes to no DB/file, and uses no global mutable state. Calls with separate inputs can execute concurrently on the same Spring singleton safely.

**Do not turn this test into a benchmark:** BigDecimal math is extremely fast, so timing differences from forks/threads may be smaller than JVM startup overhead. The purpose is illustrating isolation and configuration, not measuring performance.

## 9. Concrete JUnit Classes

### 9.1. ConcurrentMoneyTest: Opt-In Concurrent Methods Without Shared Fixtures

File `src/test/java/com/example/paralleldemo/ConcurrentMoneyTest.java`:

```java
package com.example.paralleldemo;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.assertj.core.api.Assertions.assertThat;

@Execution(ExecutionMode.CONCURRENT)
class ConcurrentMoneyTest {

    @Test
    void tenPercentDiscount() {
        MoneyCalculator calculator = new MoneyCalculator();

        assertThat(calculator.afterDiscount(
                new BigDecimal("100.00"), 10))
            .isEqualByComparingTo("90.00");
    }

    @Test
    void twentyFivePercentDiscount() {
        MoneyCalculator calculator = new MoneyCalculator();

        assertThat(calculator.afterDiscount(
                new BigDecimal("99.99"), 25))
            .isEqualByComparingTo("74.99");
    }

    @Test
    void rejectsInvalidPercent() {
        MoneyCalculator calculator = new MoneyCalculator();

        assertThrows(IllegalArgumentException.class,
            () -> calculator.afterDiscount(
                new BigDecimal("100.00"), 101));
    }
}
```

There are **3 tests**, each method creating its own calculator and touching no shared state. `@Execution(CONCURRENT)` permits Jupiter to schedule methods concurrently, though it does not force all three to run simultaneously on any given CI run—actual scheduling depends on the worker pool and engine.

### 9.2. SpringContextSafeTest: Shared Context with Stateless Bean

File `src/test/java/com/example/paralleldemo/SpringContextSafeTest.java`:

```java
package com.example.paralleldemo;

import java.math.BigDecimal;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
@Execution(ExecutionMode.CONCURRENT)
class SpringContextSafeTest {

    @Autowired
    MoneyCalculator calculator;

    @Test
    void zeroDiscountPreservesAmount() {
        assertThat(calculator.afterDiscount(
                new BigDecimal("19.50"), 0))
            .isEqualByComparingTo("19.50");
    }

    @Test
    void fullDiscountReturnsZero() {
        assertThat(calculator.afterDiscount(
                new BigDecimal("19.50"), 100))
            .isEqualByComparingTo("0.00");
    }
}
```

There are **2 tests**. Within **one JVM fork**, both methods can share the same `ApplicationContext` and singleton bean. Because the service holds no state, `@DirtiesContext` is unnecessary. In **another fork**, Gradle bootstraps an independent context; a cached context never spans processes automatically.

### 9.3. ProtectedSystemPropertyTest: @ResourceLock Handles Shared JVM State

File `src/test/java/com/example/paralleldemo/ProtectedSystemPropertyTest.java`:

```java
package com.example.paralleldemo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Execution(ExecutionMode.CONCURRENT)
class ProtectedSystemPropertyTest {

    private static final String KEY =
            "tutorial.parallel.mode";

    private static void setAndRestore(String value) {
        String previous = System.getProperty(KEY);

        try {
            System.setProperty(KEY, value);
            assertEquals(value, System.getProperty(KEY));
        } finally {
            if (previous == null) {
                System.clearProperty(KEY);
            } else {
                System.setProperty(KEY, previous);
            }
        }
    }

    @Test
    @ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
    void firstChangeDoesNotOverlapLockedSecondChange() {
        setAndRestore("alpha");
    }

    @Test
    @ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
    void secondChangeDoesNotOverlapLockedFirstChange() {
        setAndRestore("beta");
    }
}
```

There are **2 tests**. Both methods hold the same `READ_WRITE` lock on `SYSTEM_PROPERTIES`, so Jupiter does not run them concurrently within the **same engine execution plan**. They also restore the property in `finally`, even if an assertion fails.

**Do not over-interpret:** Two tests may happen not to run simultaneously due to the scheduler, so a "pass" does not prove real contention occurred. The core guarantee comes from JUnit's `@ResourceLock` contract. If code outside JUnit or another Gradle JVM fork writes to an external resource with the same name, this lock **does not protect** it.

### 9.4. PerClassSafeStateTest: PER_CLASS + Concurrent Requires Thread-Safe State

File `src/test/java/com/example/paralleldemo/PerClassSafeStateTest.java`:

```java
package com.example.paralleldemo;

import java.util.concurrent.atomic.AtomicInteger;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@Execution(ExecutionMode.CONCURRENT)
class PerClassSafeStateTest {

    private final AtomicInteger calls = new AtomicInteger();

    @Test
    void firstMethodIncrementsAtomically() {
        assertTrue(calls.incrementAndGet() >= 1);
    }

    @Test
    void secondMethodIncrementsAtomically() {
        assertTrue(calls.incrementAndGet() >= 1);
    }

    @AfterAll
    void allConcurrentMethodsCompleted() {
        assertEquals(2, calls.get());
    }
}
```

There are **2 tests**. `PER_CLASS` uses **one test class instance**; `@Execution(CONCURRENT)` allows methods to run concurrently, so `AtomicInteger` is appropriate rather than `int`. A non-static `@AfterAll` is permitted by `PER_CLASS`.

Do not assert `calls.get()==1` inside individual tests because execution order/scheduling between the two methods is not guaranteed; instead assert each method increments the counter, then `@AfterAll` verifies the total equals 2.

### 9.5. UniqueTempDirectoryTest: Use @TempDir Instead of a Fixed File

File `src/test/java/com/example/paralleldemo/UniqueTempDirectoryTest.java`:

```java
package com.example.paralleldemo;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Execution(ExecutionMode.CONCURRENT)
class UniqueTempDirectoryTest {

    @Test
    void firstFileIsInsideItsOwnTemporaryRoot(
            @TempDir Path directory) throws IOException {

        Path file = directory.resolve("result.txt");
        Files.writeString(file, "first");

        assertEquals("first", Files.readString(file));
    }

    @Test
    void secondFileIsInsideItsOwnTemporaryRoot(
            @TempDir Path directory) throws IOException {

        Path file = directory.resolve("result.txt");
        Files.writeString(file, "second");

        assertEquals("second", Files.readString(file));
    }
}
```

There are **2 tests**. Both name the file `result.txt`, but each method receives its own `@TempDir` root. JUnit handles cleanup per lifecycle and temp directory scope. This is safer than:

```java
Files.writeString(Path.of("build/result.txt"), "result");
```

The last line is an **illustrative anti-pattern** if multiple tests share that path: it can collide not only across threads, but also across two JVM forks because Gradle test tasks usually share the project working directory.

### 9.6. GradleWorkerInfoTest: Identifying Processes Without Assuming Worker Counts

File `src/test/java/com/example/paralleldemo/GradleWorkerInfoTest.java`:

```java
package com.example.paralleldemo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertFalse;

class GradleWorkerInfoTest {

    @Test
    void reportsProcessAndThreadIdentity() {
        String worker = System.getProperty(
                "org.gradle.test.worker", "IDE-or-non-Gradle");

        long pid = ProcessHandle.current().pid();
        String thread = Thread.currentThread().getName();

        assertFalse(worker.isBlank());
        assertFalse(thread.isBlank());

        System.out.printf(
            "worker=%s pid=%d thread=%s%n",
            worker, pid, thread);
    }
}
```

There is **1 test**. This is diagnostic logging, not a way to enforce worker count. When running `./gradlew test --info`, you can observe Gradle launching test processes; `org.gradle.test.worker` identifies the process according to Gradle. `Thread.currentThread().getName()` identifies the thread within the process; the same worker ID can print multiple threads.

**Do not assert a fixed expected stdout**: PID, test worker ID, thread names, and test output order vary across CI/IDEs.

### 9.7. IsolatedRuntimeTest: @Isolated Only at the Jupiter Layer

File `src/test/java/com/example/paralleldemo/IsolatedRuntimeTest.java`:

```java
package com.example.paralleldemo;

import org.junit.jupiter.api.Isolated;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@Isolated
class IsolatedRuntimeTest {

    @Test
    void javaRuntimePropertyIsVisible() {
        assertNotNull(System.getProperty("java.version"));
    }
}
```

There is **1 test**. `@Isolated` demonstrates the policy that this class does not interleave with other classes **within the same Jupiter execution plan**. However, with `maxParallelForks=2`, another Gradle fork can still run tests at the same time. If a class needs exclusive access to a database or port outside the JVM, move it to the serial task or use another form of isolation.

### 9.8. SerialSpringContextTest: Separating from the Parallel Lane

File `src/test/java/com/example/paralleldemo/SerialSpringContextTest.java`:

```java
package com.example.paralleldemo;

import java.math.BigDecimal;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.annotation.DirtiesContext;

import static org.assertj.core.api.Assertions.assertThat;

@Tag("serial")
@SpringBootTest
@DirtiesContext(
    classMode = DirtiesContext.ClassMode.AFTER_CLASS)
class SerialSpringContextTest {

    @Autowired
    MoneyCalculator calculator;

    @Test
    void testThatMarksContextDirtyRunsInSerialLane() {
        assertThat(calculator.afterDiscount(
                new BigDecimal("10.00"), 20))
            .isEqualByComparingTo("8.00");
    }
}
```

There is **1 test**. The class is tagged `@Tag("serial")`, so:
- The default `test` task **excludes** it.
- The `serialTest` task **includes** it.
- `serialTest` runs with `maxParallelForks=1` and Jupiter parallelism disabled.
- `@DirtiesContext` does not threaten a cached context being used concurrently **within that serial JVM**.

**Limit to understand:** If Gradle runs multiple modules or another CI job runs simultaneously, this module's serial lane does not lock global resources. `@DirtiesContext` also does not clean up external DBs/schemas, Kafka topics, or filesystems.

### 9.9. Exact Sample Test Count

| Class | `@Test` count | Lane |
|---|---:|---|
| `ConcurrentMoneyTest` | 3 | `test` |
| `SpringContextSafeTest` | 2 | `test` |
| `ProtectedSystemPropertyTest` | 2 | `test` |
| `PerClassSafeStateTest` | 2 | `test` |
| `UniqueTempDirectoryTest` | 2 | `test` |
| `GradleWorkerInfoTest` | 1 | `test` |
| `IsolatedRuntimeTest` | 1 | `test` |
| `SerialSpringContextTest` | 1 | `serialTest` |
| **Total** | **14** | **13 + 1** |

This is the count of **test methods authored in the sample**, not the number run inside a single JVM. Actual results are confirmed only after Gradle/JUnit discovery and reports verify exact counts/pass/fail/skip.

## 10. Distinguishing "Actually Concurrent" from "Concurrently Permitted"

Having `@Execution(CONCURRENT)` and `fixed.parallelism=2` **permits** parallelism; it is not an assertion that two methods are guaranteed to overlap in time on any specific run.

### 10.1. Avoid Using Thread.sleep Tests to Prove Concurrency

Anti-pattern:

```java
long started = System.nanoTime();
Thread.sleep(100);
assertTrue(System.nanoTime() - started < 150_000_000L);
```

This is an illustrative snippet, not an independent test. It neither proves two test methods ran concurrently nor avoids dependence on the scheduler and CI load. Never treat single-method execution time as a reliable indicator of JUnit parallelism.

**If the goal is to prove two methods can overlap in a diagnostic test class**, you can write a dedicated probe using `CountDownLatch`/barriers with a **deadline** and run **that class alone** with a pool parallelism of at least 2. However:
- Never place a mandatory barrier between two tests in a large suite that CI might run with a single thread.
- Never use a static barrier across multiple forked JVMs—static fields are not shared across JVMs.
- If one test fails before signaling the latch, the other test must have a finite timeout.
- Proving overlap does not automatically guarantee database/file isolation.

In the runnable code, tests are designed so they **do not require two methods to run at the same time to pass**. That is the reliability principle: tests remain correct under any valid scheduler interleaving.

### 10.2. How to Verify the Active Configuration

- Check `junit-platform.properties` on the test runtime classpath.
- Confirm `useJUnitPlatform()` in Gradle.
- Inspect `@Execution`, `@ResourceLock`, and `@Isolated` on test classes.
- Print/log diagnostic `org.gradle.test.worker`, PID, and thread name when needed.
- Inspect `--info`/Build Scan to see Gradle worker processes.
- Check which **task** sets `maxParallelForks`, `--max-workers`, `--parallel`, and `forkEvery`.
- Use JUnit/Test execution reports and profiling rather than inferring from `System.out` ordering (test stdout can be captured/reordered by Gradle).

## 11. Failure Examples Caused by Shared Resources

### 11.1. Database Cleanup Race

Two tests share an H2/PostgreSQL schema:

```text
Test A: INSERT invoice id=A
Test B: DELETE FROM invoice
Test A: assert invoice A exists  --> FAIL
```

`@Transactional` on test A does not protect against `DELETE`/DDL run by test B outside the transaction or in another process, depending on isolation/DB semantics. How to handle:
- Use **unique business IDs per test**.
- Use a separate schema/database per test process when tests cannot coexist.
- When using Testcontainers, manage container lifetimes, ports, and schema ownership.
- Do not truncate-all before every test on a shared DB.
- Consider a serial lane for migrations/DDL/full resets.
- Ensure cleanup never deletes another test's data.

### 11.2. Filesystem Using a Fixed Path

```java
Path report = Path.of("build/reports/current.json");
Files.writeString(report, json);
```

This is an illustrative fragment: the `json` variable must exist. If two forks write to the same path, `@ResourceLock` inside each JVM **does not coordinate** across them. Fix with `@TempDir` or include the worker ID/test ID in the path, and clean up files within the corresponding scope.

### 11.3. Fixed Port and Mock HTTP Server

```text
Fork A: starts server port 8089 -> success
Fork B: starts server port 8089 -> BindException: address in use
```

Use `@SpringBootTest(webEnvironment=RANDOM_PORT)` when a real HTTP server is needed, or bind embedded/mock servers to port 0 and read the assigned port. Never hard-code one port across forks; pass the assigned port to clients via `@LocalServerPort`/DynamicPropertySource.

If an external service forces a fixed port, split out a serial lane or allocate unique ports via CI leases/worker configuration.

### 11.4. Testcontainers, Docker, and JVM Lifecycle

A static singleton test container in **each JVM** is not a singleton for the entire Gradle build. With `maxParallelForks=4`, four containers can start simultaneously:
- CPU/RAM/Docker pull load spikes sharply.
- DB pools/threads on the CI machine can get saturated.
- Fixed container names/network aliases can conflict.
- Container reuse can leave leftover state from a previous run.
- `@DynamicPropertySource` reads the endpoint from that fork's container instance; never hard-code an old endpoint.

When sharing a container across tests in one JVM, parallelize only if state is truly isolated. When desiring a single container across all forks, use external leases/schema partitioning—do not assume a static field crosses process boundaries.

### 11.5. System Properties, Default Locale, Clock, and TimeZone

System properties, global timezones, or JVM default locales are **shared mutable global state within a JVM**. JUnit provides predefined resource keys such as `Resources.SYSTEM_PROPERTIES`, `Resources.TIME_ZONE`, and `Resources.LOCALE`. Use `@ResourceLock` appropriately and restore state after the test.

Across multiple JVM forks, each JVM has its own system properties, but external configuration files or environment services remain shared. Avoid calling `TimeZone.setDefault(...)` in an unlocked concurrent test.

### 11.6. Tests Making HTTP Calls and Transactional Rollback

With `@SpringBootTest(RANDOM_PORT)`, the HTTP server handles requests on a different thread than the JUnit test thread. A test-managed transaction does not cover the service transaction on the request thread, so writes can commit even though the `@Transactional` test rolls back by default. In a parallel suite, this easily causes data bleed between tests without proper cleanup.

## 12. Tuning Workers for CPU, RAM, DB Pools, and CI

A resource estimation model for a project:

- `F` = actual forked test JVMs of a Gradle `Test` task (bounded by `maxParallelForks` and Gradle's scheduling budget).
- `P` = Jupiter desired parallelism per JVM.
- `H` = max heap of each test JVM.
- `C` = DB connections/pool capacity held by each Spring context.

**Rough estimate:**
- Concurrent JUnit nodes can scale **based on F × P** when enough runnable tests exist, though `P` is not always a hard cap and other tasks/forks may run.
- Heap allocations across test JVMs alone can approach **F × H**, plus metaspace, threads, native memory, the Gradle daemon, and Docker containers.
- If each fork boots a Spring application context with a max Hikari pool size `C`, potential total connection demand can approach **F × C** or more with multiple contexts/clients.

Sample settings like `maxParallelForks=2`, `maxHeapSize='512m'`, and Jupiter fixed parallelism 2 are **illustrative parameters**, not a guarantee that total RAM stays at 1 GiB or that exactly four test methods run concurrently. Check actual `-XX:ActiveProcessorCount`, container CPU quotas, memory limits, Spring context counts, and external DB connection limits.

### 12.1. Why More Forks Can Sometimes Be Slower

- Repeated JVM/Spring context startups.
- Classpath scanning and Hibernate bootstrapping contending for CPU.
- Each fork loading the same test fixtures.
- Overlapping Docker/Testcontainers startups.
- PostgreSQL/Redis lock and connection contention.
- Increased GC when RAM is tight.
- Disk I/O bottlenecks when writing logs/test reports.

**Strategy:** measure a baseline of 1 fork, 1 JUnit worker; increase one variable at a time and measure **median and p95** suite duration and failures across multiple runs. Never pick "number of CPU cores" and multiply both forks and threads by it without checking resource costs.

### 12.2. Per-Environment CI Configuration

A powerful local laptop might use 2 forks × 2 JUnit threads; a small CI runner might need 1 fork × 2 threads or even sequential execution. Use Gradle properties to override:

```groovy
tasks.named('test', Test) {
    maxParallelForks = providers
            .gradleProperty('testForks')
            .map { it.toInteger() }
            .getOrElse(2)
}
```

This is a **replacement fragment** for the `maxParallelForks=2` line in `build.gradle` above; do not include both versions at once. Run:

```bash
./gradlew test -PtestForks=1 --max-workers=2
```

To override JUnit parallelism without modifying the resource file, pass JVM system properties into the Test task from a Gradle project property:

```groovy
tasks.named('test', Test) {
    systemProperty(
        'junit.jupiter.execution.parallel.config.fixed.parallelism',
        providers.gradleProperty('junitThreads')
            .getOrElse('2'))
}
```

This is also an **optional fragment**, not included in the main build. Verify `@ResourceLock`/`@Isolated` still apply as threads increase; and do not assume Gradle CLI `-D...` flags are automatically forwarded to the test JVM unless the `Test` task forwards the property.

## 13. Running, Verifying Test Method Counts, and Reading Reports

With a valid Gradle wrapper in the project:

### 13.1. Running the Parallel Lane

Linux/macOS:

```bash
./gradlew test --max-workers=4
```

Windows PowerShell:

```powershell
.\gradlew.bat test --max-workers=4
```

`test` is expected to select **13 test methods** from classes without the `serial` tag. Because this is unbuilt sample code, verify the report for actual counts. `maxParallelForks=2` is the maximum test JVM workers; actual JVMs spawned may be fewer if workload or worker budget is smaller.

### 13.2. Running the Serial Lane

```bash
./gradlew serialTest --max-workers=2
```

Windows:

```powershell
.\gradlew.bat serialTest --max-workers=2
```

`serialTest` selects only `@Tag("serial")`, which is **1 test method** in this project. It runs with **one JVM and Jupiter parallelism disabled**. If there are multiple serial test classes, the task still processes them sequentially inside that JVM per execution mode (unless a test spawns its own background threads, which Jupiter cannot prohibit).

### 13.3. Running Both Lanes

```bash
./gradlew clean check --max-workers=4
```

`check` depends on `test` (from the Java plugin) and `serialTest` (from the build script), with `serialTest.shouldRunAfter(test)` to avoid mixing execution timing of the two lanes in this project. However, ordering across other subprojects remains subject to the task graph/parallel scheduling.

When debugging sequentially:

```bash
./gradlew clean check --max-workers=1 --no-parallel
```

With the command above, Gradle grants only one worker slot so Gradle test forks do not run multiple JVMs simultaneously; **however**, the `test` task still has JUnit Jupiter parallelism enabled with `fixed.parallelism=2` inside that single JVM! To disable **Jupiter parallelism as well**, run `serialTest` or add a debug override `systemProperty('junit.jupiter.execution.parallel.enabled','false')` in a dedicated debug test task.

### 13.4. Running a Single Class for Diagnostics

```bash
./gradlew test --tests "com.example.paralleldemo.ConcurrentMoneyTest" --info
```

Or:

```bash
./gradlew test --tests "com.example.paralleldemo.GradleWorkerInfoTest" --info
```

Running **a single class** cannot serve as proof that `maxParallelForks=2` spawned two JVMs: Gradle only needs one fork for one class. To observe multiple worker IDs, you need enough test classes and sufficient total worker budget.

### 13.5. Reading Reports Properly

- Gradle HTML report: `build/reports/tests/test/index.html`.
- Gradle XML results: `build/test-results/test/`.
- Serial lane report: `build/reports/tests/serialTest/index.html`.
- Serial lane XML: `build/test-results/serialTest/`.

Consider the suite executed only when reports confirm **test count, failures, skips**, and the task actually ran. `BUILD SUCCESSFUL` with `NO-SOURCE` or `UP-TO-DATE` does not prove a new test ran in the current build. If build caching is intentional, understand it represents results from a previous run matching the input fingerprint.

Never fabricate a fixed stdout like `"worker=1 pid=..."`: PIDs and worker IDs vary.

## 14. Anti-Patterns to Avoid

### 14.1. Enabling --parallel and Assuming JUnit Methods Are Concurrent

`--parallel` is Gradle project-level task scheduling. Jupiter requires its own configuration or `@Execution(CONCURRENT)`.

### 14.2. Setting Only parallel.enabled=true

If JUnit's default execution modes remain `same_thread`, you will not see the expected concurrency. Explicitly configure class/method modes and the `fixed/dynamic` strategy.

### 14.3. Setting maxParallelForks to availableProcessors for Every Module

This multiplies JVM bootstraps, connection pools, and Docker resources; Gradle's total worker budget may cap it, yet running many processes remains costly. Tune via profiling.

### 14.4. Using @ResourceLock("database") While Enabling Four Gradle Forks

ResourceLock coordinates only within a single JVM's JUnit engine. Two separate JVMs have two independent lock managers. For a shared DB, use database/schema partitioning or an appropriate serial lane.

### 14.5. Annotating @Isolated and Assuming the Entire CI Build Is Exclusive

`@Isolated` does not block other forks, other modules, or other CI jobs. Resources must be isolated at the appropriate layer.

### 14.6. Using forkEvery=1 to Cure Data Races

Recycling the JVM may hide static leaks, but does not prevent two forks from touching the same file/DB and makes the suite very slow. Fix the root cause.

### 14.7. Shared static List/Map/Counter Under @Execution(CONCURRENT)

`ArrayList`, `HashMap`, and `int++` are not thread-safe by default. Use immutable fixtures, `ConcurrentHashMap`, `AtomicInteger`, or `@ResourceLock` if sharing is truly unavoidable.

### 14.8. @DirtiesContext / @MockitoBean in Parallel Context Tests

Spring TestContext docs recommend against running tests with `@DirtiesContext` or mock bean overrides in parallel when context cache/mock state races are possible. Use a serial lane or isolated fixtures.

### 14.9. Fixed Test Data Identifiers

If two tests both execute `INSERT users(email='alice@example.test')`, a unique constraint can fail one test; if one test wipes the other's table, failures depend on interleaving. Use per-test IDs or schema isolation.

### 14.10. Using Only Thread.sleep to "Wait for the Other Test"

`Thread.sleep(100)` makes tests flaky and establishes no synchronization contract. To test real concurrency, use thread-safe probes, `CountDownLatch`, `CyclicBarrier`, and bounded timeouts rather than relying on CPU speed.

## 15. Root-Cause Diagnosis When the Suite Fails Only in CI

| Symptom | Possible Cause | How to Investigate |
|---|---|---|
| Passes alone, fails in full suite | Shared static state/context/file/DB | Run single JVM vs multiple forks, check resource ownership |
| Fails only when `maxParallelForks>1` | Cross-process collision | Inspect DB schema, file path, port, container name |
| Fails only when Jupiter concurrent | Same-JVM race | Check static fields, singleton beans, shared mocks |
| `ApplicationContext no longer active` | Concurrent `@DirtiesContext`/cache eviction | Move to serial lane, check ContextCache logs |
| Inconsistent Mockito verification counts | Shared mock/reset/stubbing race | Do not run same mock bean concurrently |
| Unique constraint violation in CI | Tests sharing business ID/schema | Unique test fixtures/schema partitioning |
| FileNotFound/overwritten JSON | Two tests using same filename | `@TempDir`/worker-ID-based path |
| Address already in use | Mock server using fixed port | Port 0/RANDOM_PORT |
| More JVMs yet slower suite | Spring startup/GC/DB contention | Profile, reduce forks |
| Test container startup conflict | Multiple forks starting containers | Manage lifecycle, unique resources |
| `@Transactional` rollback misses data | HTTP/async thread in different transaction | Explicit cleanup, test DB isolation |
| Test classes not concurrent as expected | `mode.classes.default=same_thread` | Check Jupiter properties and `@Execution` |
| Methods in class still sequential | `mode.default=same_thread` or `PER_CLASS`/order | Check class annotations/test plan |
| `@ResourceLock` serializes too much | Conflicting `READ_WRITE` locks | Use `READ` for read-only, shrink critical section |
| Same Gradle worker ID appears repeatedly | Multiple test classes in one fork | Normal, not a bug |
| Same PID with different thread names | Jupiter threads inside one JVM | Normal when concurrency is enabled |
| Two PIDs yet same file deleted | Locks only protect within each JVM | Filesystem namespace/external coordination |
| `--max-workers=1` still shows two JUnit threads | Worker budget differs from JUnit thread count | Disable Jupiter parallelism separately |
| Reports missing serial tests | `test` task excludes `serial` tag | Run `check`/`serialTest` separately |
| JUnit tests skipped/NO-SOURCE | Wrong test discovery/filtering | Check task filters, classpath, XML reports |
| Hikari pool exhausted | Multiple contexts/forks opening connections | Reduce forks, use dedicated pools/lower max |
| Timeouts increase under parallel run | CPU throttling, DB contention, GC | Adjust worker budget and timeouts for load |

### 15.1. A Reliable Debugging Sequence

1. Record the exact Gradle command and CI environment.
2. Check `--max-workers`, `--parallel`, `maxParallelForks`, and `forkEvery` on the Test task.
3. Check JUnit parallel enabled, class/method modes, and fixed/dynamic pool config.
4. Identify which tests use `@DirtiesContext`, `@MockitoBean`, `@TestMethodOrder`, `@Isolated`, or `@ResourceLock`.
5. Identify shared **in-JVM** resources and **external** resources.
6. Run single JVM + sequential Jupiter to establish a baseline.
7. Enable JUnit concurrency alone and observe failures; then increase Gradle forks alone.
8. Use `org.gradle.test.worker`, PID, and thread IDs to pinpoint the race layer.
9. Split into a serial lane or fix isolation; do not just increase `Thread.sleep`.
10. Run multiple times in CI before raising concurrency again.

## 16. Key Rules for Module-Level Parallel Execution

In a repository with `:core`, `:api`, `:integration`:
- Unit tests in `:core` typically need no Spring context and can use higher parallelism.
- Slice tests in `:api` can run classes concurrently if mocks/fixtures are not unsafely shared.
- `:integration` using PostgreSQL/Kafka/Redis/Testcontainers is typically constrained by external resources and may require a serial lane or per-worker schemas.
- `--parallel` creates concurrency **across Gradle projects**, so total database/container load for the build is not merely one module's `maxParallelForks`.
- `maxParallelForks` can differ by task: `test`, `integrationTest`, `serialTest`.
- If `check` depends on test tasks across multiple modules, design task graphs and capacity budgets instead of relying on JUnit annotations to isolate the entire system.

A common **strategy-based** setup (not universal magic constants):
- Pure unit tests: high class/method concurrency.
- `SpringBootTest` with no shared mutable resources: few forks, context cache reuse.
- DB/migration/consumer/port-dependent tests: isolated schemas/containers or serial.
- Load/performance tests: separate task, never mixed into correctness suites.
- Tests mutating default timezone/system properties: `@ResourceLock` and `finally` restore.

## 17. QA Checklist Before Enabling Parallel Execution in a Real Project

- [ ] Understand that `--parallel` controls Gradle project task scheduling, not Jupiter mode.
- [ ] Understand that `--max-workers` caps Gradle's worker budget.
- [ ] Understand that `Test.maxParallelForks` is the number of forked JVM test processes, not threads.
- [ ] Understand that `forkEvery` controls JVM recycling, not parallelism.
- [ ] Understand that `junit.jupiter.execution.parallel.enabled` and execution modes must be configured separately.
- [ ] Choose fixed/dynamic parallelism based on actual CPU/RAM/cost.
- [ ] Do not treat desired JUnit parallelism as a hard upper bound on threads.
- [ ] Ensure `useJUnitPlatform()` is configured on the Gradle Test task.
- [ ] Do not rely on execution orders not guaranteed by JUnit.
- [ ] Use test-specific fixtures and avoid shared static mutable state.
- [ ] Concurrent `PER_CLASS` tests use only immutable/thread-safe fields.
- [ ] `@ResourceLock` is trusted only within the same JUnit execution plan.
- [ ] `@Isolated` is not mistaken for a cross-JVM lock.
- [ ] Use `@TempDir` or namespaced paths for file outputs.
- [ ] Databases use per-test data IDs/schemas or an appropriate serial policy.
- [ ] Mock servers/WebServers use dynamic ports instead of shared hard-coded ports.
- [ ] Testcontainers resources are managed according to fork/task lifespan.
- [ ] `@DirtiesContext` and `@MockitoBean` do not race against the cached context.
- [ ] HTTP/async threads are not assumed to join the JUnit test's `@Transactional`.
- [ ] A serial Gradle Test task exists for tests with global/shared state.
- [ ] `@Tag("serial")` is included in the serial task and excluded from the main task.
- [ ] `check` actually executes all required lanes.
- [ ] Do not assume `--max-workers=1` automatically disables Jupiter threads.
- [ ] Log worker ID/PID/thread for investigating CI flakes.
- [ ] Read Gradle/JUnit reports to verify executed test counts, failures, and skips.
- [ ] Measure suite duration, CPU, RAM, and DB connections as concurrency increases.
- [ ] Keep a way to revert to sequential config for quick debugging.

## 18. Official Documentation

- [JUnit Jupiter — Parallel Execution (JUnit 5)](https://docs.junit.org/5.14.2/writing-tests/parallel-execution): `parallel.enabled`, class/method modes, fixed/dynamic strategy, `@Execution`, `@ResourceLock`, `@Isolated`, `PER_CLASS`.
- [JUnit Jupiter — Test Instance Lifecycle](https://docs.junit.org/5.14.2/writing-tests/test-instance-lifecycle): `PER_METHOD` vs `PER_CLASS` and lifecycle.
- [JUnit Jupiter — Tagging and Filtering](https://docs.junit.org/5.14.2/writing-tests/tagging-and-filtering): `@Tag` and include/exclude filtering.
- [Gradle — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html): `maxParallelForks`, `forkEvery`, test worker property, reports.
- [Gradle — Test Task API](https://docs.gradle.org/current/javadoc/org/gradle/api/tasks/testing/Test.html): `getMaxParallelForks`, `setMaxParallelForks`, fork semantics.
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html): `--parallel`, `--max-workers`.
- [Gradle — Build Performance](https://docs.gradle.org/current/userguide/performance.html): tuning test parallelism, profiling.
- [Spring Framework 6.2 — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/parallel-test-execution.html): Spring TestContext guidance on `@DirtiesContext`, Mockito overrides, shared state, and context cache.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): `@Transactional`, rollback, and thread boundaries.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): test slices, `@SpringBootTest`, TestContext.
- [JUnit Jupiter — User Guide](https://docs.junit.org/5.14.2/): test reports, build tool integration.

**Conclusion:** `JUnit parallel execution` and `Gradle maxParallelForks` are **two separate concurrency layers**, while `--max-workers` and `--parallel` belong to Gradle's scheduler. A safe practice is: start with concurrent classes and sequential methods, use `@Execution(CONCURRENT)` for genuinely thread-safe classes, `@ResourceLock` for shared in-plan resources, `@TempDir`/separate schemas for out-of-JVM resources, and a `serialTest` task for cases with `@DirtiesContext`, mocks, or global state. Measure effectiveness via Gradle/JUnit reports and real CI resources rather than guessing from worker counts or an individual test happening to run faster.