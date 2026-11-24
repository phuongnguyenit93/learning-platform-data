# ResourceLock or JUnit's Built-In Locking Mechanism

## 1. Context: Isolating Resources When Spring Boot Tests Run in Parallel

In a Spring Boot project, running each test class separately usually passes, yet enabling JUnit parallel execution causes certain tests to fail intermittently. Often the bug is not in business code, but in **test interference**: multiple tests share mutable state and modify it nearly simultaneously.

Common examples:

- Two tests both call `System.setProperty("app.mode", ...)`.
- Tests mutate `Locale.setDefault(...)`, default timezone, or `System.out`.
- Two `@SpringBootTest` classes share a cached `ApplicationContext` and a stateful singleton.
- Multiple tests write to the same report export file or fixed directory.
- One test wipes a DB table in `@BeforeEach` right as another test reads records.
- Test classes share a Kafka topic/consumer group, RabbitMQ queue, or Redis keys.
- `@MockBean` gets reset or re-stubbed between two in-flight HTTP requests.
- A test returns before an async task finishes, letting a background worker write into the next test's data.

The goal is **not turning off all parallelism**. You must identify which state can avoid sharing, which must remain shared, and synchronize **only the tests contending on the same resource**.

JUnit Jupiter provides `@ResourceLock`, identifying a resource by a **String key**. When a test requests `READ` or `READ_WRITE` on that resource, the JUnit engine uses that metadata to prevent test nodes with conflicting demands from running concurrently. This is a **test execution schedule lock**, not a mutex injected by Spring into production code.

**Main topic:** "ResourceLock or JUnit's Built-In Locking Mechanism", under parent group **Isolation and Parallel Execution**. After this lesson, you should be able to:

1. Understand `@ResourceLock`, `ResourceAccessMode.READ`, `READ_WRITE`, and key identity.
2. Know that `@ResourceLock` also covers `@BeforeEach` and `@AfterEach` of the annotated method.
3. Lock across **multiple distinct test classes** when they share a common resource key.
4. Distinguish method-level vs class-level locks and declare multiple locks on one test.
5. Configure `junit.jupiter.execution.parallel.enabled`, class/method execution modes, and fixed parallelism.
6. Understand that `@Execution(CONCURRENT)` permits concurrent execution without guaranteeing two tests will overlap.
7. Know when to choose `@Execution(SAME_THREAD)`, `@Isolated`, `@TempDir`, or data isolation over `ResourceLock`.
8. Handle JVM globals safely: system properties, stdout/stderr, default locale/timezone; restore initial state.
9. Understand that identical `@SpringBootTest` configurations can share Spring singletons via the TestContext cache.
10. Avoid declaring `READ` if setup/teardown or the operation performs an implicit write.
11. Avoid confusing JUnit locks with database advisory locks, Java locks, or distributed locks.
12. Build a complete **Java 17 + Spring Boot 3.3.5 + Gradle** example containing **12 JUnit Jupiter `@Test` methods**.
13. Know limitations regarding Gradle forks/multi-module CI, `@DirtiesContext`, `@MockBean`, `@Async`, and `@Scheduled`.
14. Evaluate locking effectiveness by flake rate and suite runtime rather than `Thread.sleep` or unmeasured timing claims.

**Pinned stack:** Java 17, Spring Boot **3.3.5**, Spring Framework 6.1, JUnit Jupiter managed by Boot. This lesson uses only `@ResourceLock(value, mode)`, `Resources`, and `@Isolated` already available in the 5.10.x line. Newer `@ResourceLock` options such as `target` and `providers` belong to **JUnit 5.12+** and **are not used in the runnable project** to preserve compatibility with Boot 3.3.

## 2. Distinguishing Four Types of Problems

| Problem | Example | Tool to Consider |
|---|---|---|
| **Test isolation** | Test A leaves a property behind; B sees stale value | Restore state; `ResourceLock` if both share it |
| **Race inside the app itself** | Two requests deducting inventory concurrently lose an update | Atomic DB update, transactions, optimistic locks, and concurrent integration tests |
| **Parallel execution** | Running multiple tests on JUnit workers | JUnit parallel config, `@Execution` |
| **Cross-process contention** | Two Gradle forks or CI jobs sharing a test DB | Unique schemas/containers/namespaces, DB locks, or distributed coordination |

`ResourceLock` addresses **test interference** among JUnit nodes participating under a shared key agreement. It **cannot make a non-thread-safe service thread-safe in production**. If you slap `READ_WRITE` on all tests calling a service and conclude the service is safe under concurrent HTTP requests, that conclusion is invalid: JUnit **serialized** the exact condition you needed to observe.

### 2.1. Unlocked Counter-Example

~~~java
// Two illustrative JUnit test methods; they contend when running concurrently.
@Test
void alpha() {
    System.setProperty("demo.mode", "alpha");
    assertEquals("alpha", System.getProperty("demo.mode"));
}

@Test
void beta() {
    System.setProperty("demo.mode", "beta");
    assertEquals("beta", System.getProperty("demo.mode"));
}
~~~

An interleaving that causes `alpha` to fail:

~~~text
JUnit worker T1                   JUnit worker T2
setProperty("demo.mode","alpha")
                                  setProperty("demo.mode","beta")
getProperty("demo.mode") -> beta
assertEquals(alpha, beta) -> FAIL
                                  assertEquals(beta,beta) -> PASS
~~~

Both methods also leave `demo.mode` set for a third test. Even when concurrency is locked, you must restore state. If Test B uses `synchronized(this)` on a different test instance, the two Java monitors are **not the same object**, so contention remains unsolved.

## 3. How `@ResourceLock` Works in JUnit Jupiter

`org.junit.jupiter.api.parallel.ResourceLock` is an annotation applicable to a **test method or test class**. Resources are identified by an **exact string key** (`value`), paired with an access mode. The default `mode` is `ResourceAccessMode.READ_WRITE`.

~~~java
@Test
@ResourceLock("inventory-fixture")
void modifyInventory() {
    // Defaults to READ_WRITE.
}

@Test
@ResourceLock(
        value = "inventory-fixture",
        mode = ResourceAccessMode.READ)
void inspectInventory() {
    // Read-only, including setup/teardown.
}
~~~

This is an explanatory snippet; imports include JUnit Jupiter `Test`, `ResourceLock`, and `ResourceAccessMode`. `"Inventory-Fixture"` differs from `"inventory-fixture"`. JUnit **does not know both strings refer to the same DB table**: all participating classes/tests must agree on the exact string.

### 3.1. READ / READ_WRITE Matrix

| Test A holds resource X | Test B requests READ(X) | Test B requests READ_WRITE(X) |
|---|---|---|
| `READ(X)` | May run concurrently | B must wait for A |
| `READ_WRITE(X)` | B must wait for A | B must wait for A |
| Does not hold X | No conflict on X | No conflict on X |

**Two `READ` tests are not required to overlap**, only **permitted** when the scheduler has free workers and no other resource conflicts. **`READ_WRITE` guarantees no execution order**: writer A does not necessarily precede writer B, and no public fairness guarantee exists between readers and writers.

**Never pick `READ` solely because the HTTP method is GET.** A GET endpoint might write audit logs, update caches, bump `lastSeenAt`, or lazy-load state. Evaluate actual side effects across the whole test, including `@BeforeEach` and `@AfterEach`.

### 3.2. Locks Span Lifecycle Callbacks

With a method-level annotation:

~~~java
@BeforeEach
void prepare() {
    sharedStore.reset();
}

@Test
@ResourceLock("shared:store")
void verifyStore() {
    assertEquals(1, sharedStore.next());
}

@AfterEach
void cleanup() {
    sharedStore.reset();
}
~~~

This snippet assumes an enclosing class with `sharedStore`; `@ResourceLock` sits on the **`@Test` method**, not the callbacks. JUnit acquires the lock **before** `@BeforeEach` runs and releases it **after** `@AfterEach` completes.

~~~text
Acquire READ_WRITE("shared:store")
  |
  +-- @BeforeEach: reset fixture
  +-- @Test: assertions and mutations
  +-- @AfterEach: cleanup/reset
  |
Release READ_WRITE("shared:store")
~~~

This is a major advantage over placing `synchronized` **only inside the test body**: another test cannot sneak in between setup and cleanup if it declares the same resource key. However, declaring a lock **does not automatically reset** the resource; you must still clean up or roll back.

### 3.3. Class-Level, Method-Level, and Repeatable

When every test method touches the same resource, place the annotation on the class:

~~~java
@Execution(ExecutionMode.CONCURRENT)
@ResourceLock(
        value = "configuration:shared",
        mode = ResourceAccessMode.READ_WRITE)
class ConfigurationChecks {

    @Test
    void scenarioA() { }

    @Test
    void scenarioB() { }
}
~~~

The snippet above is an abbreviated JUnit class. Class-level locking is concise and covers associated lifecycles, yet can **reduce parallelizability** since the entire class counts as holding the resource. When only a few methods mutate, method-level annotations provide finer granularity.

A test touching two shared resources can declare two annotations:

~~~java
@Test
@ResourceLock("database:orders")
@ResourceLock("cache:orders")
void changesDatabaseAndCache() {
    // JUnit knows this test needs both named resources.
}
~~~

Annotations are repeatable; no manual Java `ReentrantLock` is needed per annotation. Never create one catch-all key `"EVERYTHING"` across the suite if two resources are independent: that needlessly serializes unrelated work.

**Version note:** In JUnit Jupiter 5.10.x, `@ResourceLock` supports only the `value`/`mode` attributes used here. Reading latest JUnit docs, you may see `target=CHILDREN` or `providers=...` added in 5.12. **Do not copy those options into Boot 3.3.5 code without upgrading Jupiter**.

## 4. Predefined Keys and Naming Conventions

JUnit defines standard `Resources` constants:

| Constant Name | Target |
|---|---|
| `Resources.SYSTEM_PROPERTIES` | `java.lang.System` properties |
| `Resources.SYSTEM_OUT` | `System.out` |
| `Resources.SYSTEM_ERR` | `System.err` |
| `Resources.LOCALE` | JVM default locale |
| `Resources.TIME_ZONE` | JVM default timezone |

Example:

~~~java
@Test
@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
void temporarilyChangeProperty() {
    String old = System.getProperty("demo.mode");
    try {
        System.setProperty("demo.mode", "test");
        assertEquals("test", System.getProperty("demo.mode"));
    } finally {
        if (old == null) {
            System.clearProperty("demo.mode");
        } else {
            System.setProperty("demo.mode", old);
        }
    }
}
~~~

Snippet requires JUnit and `Resources` imports; the runnable source in Section 8 shows a fuller example. **Use the exact same key** across all tests touching global state. `Resources.SYSTEM_PROPERTIES` is broader than `"demo.mode"`: if tests mutate strictly **independent** properties, granular keys can improve parallelism—provided code under test does not read/mutate other properties or the `System.getProperties()` map as a whole.

For custom resource keys, naming conventions should reflect the **collision scope**:
- `"spring:sequence-fixture"` for a singleton bean shared across classes.
- `"db:shop-test:orders"` for a shared table in a schema.
- `"file:build/shared/export.csv"` for a shared file.
- `"broker:orders-test:queue"` for a queue.
- `"cache:orders-global"` for a cache namespace.

**Too narrow**: Writer A uses `"db:orders:table"` and Writer B uses `"db:orders"` while mutating the same `orders` table → JUnit treats them as distinct. **Too broad**: every test uses `"GLOBAL"` → parallelism nearly vanishes. Centralize resource keys as compile-time constants in large projects to prevent typos. A single test can lock both DB and cache simultaneously when both are affected.

## 5. Parallel Configuration: JUnit vs Gradle Forks

Jupiter does not enable full test parallelism by default. Sample `src/test/resources/junit-platform.properties`:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
~~~

- `enabled=true`: enables JUnit's parallel scheduler.
- `mode.default=concurrent`: methods may run concurrently where appropriate.
- `mode.classes.default=concurrent`: classes may also run concurrently.
- `fixed.parallelism=4`: target parallelism level inside the Jupiter engine.
- `@Execution(CONCURRENT)` opts a class or method into concurrent execution.
- `@Execution(SAME_THREAD)` forces a test node onto its parent's thread per Jupiter semantics. **Never** use it as a global mutex across classes.

`@TestInstance(PER_METHOD)` is JUnit Jupiter's default, giving each test method a **separate test class instance**, though it does not isolate static fields, Spring singletons, or DBs. With `@TestInstance(PER_CLASS)` or `@TestMethodOrder`, JUnit applies exceptions to parallel execution modes; check `@Execution(CONCURRENT)` and real thread safety of instance fields.

### 5.1. Never Use Test Ordering to Fix Races

`@ResourceLock(READ_WRITE)` ensures two tests sharing a key **do not overlap**, not that A runs before B. If A creates data that B depends on, the tests are **order-dependent**. Move data setup into `@BeforeEach` or per-test fixtures, or combine workflow steps into one integration test.

`@TestMethodOrder` controls ordering per JUnit policy without preventing other classes from mutating shared state. With Spring parallel tests, ordered tests also demand care around test independence.

### 5.2. One JUnit JVM vs Multiple Gradle JVMs

`@ResourceLock` operates inside a single JUnit execution plan within one test JVM process. Gradle can spawn multiple JVM workers if `maxParallelForks` exceeds 1 or `forkEvery` recycles workers.

~~~text
JVM #1                                   JVM #2
@ResourceLock("db:test:orders")           @ResourceLock("db:test:orders")
      |                                          |
  Internal JUnit #1 lock                   Internal JUnit #2 lock
      |                                          |
  Queries shared PostgreSQL <---------> Queries shared PostgreSQL

No mutual exclusion across two JVMs even with identical key strings.
~~~

For external DBs/brokers shared across forks/CI jobs, use unique schemas/tenants/test IDs/containers or cross-process coordination. You cannot simply declare matching `@ResourceLock` names and expect a distributed lock.

### 5.3. Parallelism Is Not a Timing Assertion

Do not assume two `READ` tests will *actually overlap* simply because both hold `READ` keys. The scheduler, CI load, and CPU quotas may run them sequentially. Avoid using `Thread.sleep(50)` as proof of concurrency. To test **concurrent algorithms**, use a multi-worker executor, `CountDownLatch`/`CyclicBarrier`, bounded timeouts, and business invariants—a separate test category from locking test fixtures.

## 6. Lock, Isolate Data, or Isolate the Class?

| Mechanism | When to Choose | Limitations |
|---|---|---|
| **`@ResourceLock(K, READ_WRITE)`** | A shared resource genuinely requires exclusive writer access | Applies only among Jupiter test nodes declaring K in the same process/plan |
| **`@ResourceLock(K, READ)`** | Readers genuinely never mutate, including setup/teardown | Can run together, excluded from writers on K |
| **`@Isolated`** | A class must exclude **all other classes** in the Jupiter plan | Broad lock, lowers throughput; does not block external threads/processes |
| `@Execution(SAME_THREAD)` | Need node on parent thread, or per-class test state isn't parallel-safe | Does not serialize other classes |
| **`@TempDir`** | Each test manages its own files | Does not protect files/paths outside the temp dir |
| Dedicated DB schema/container/unique IDs | Multi-process/multi-JVM integration tests | Setup overhead, still needs cleanup |
| `@Transactional` + rollback or `@Sql` | DB test data managed cleanly in transactions | HTTP/async/server writes may run in different transactions |
| Mutex/JVM `synchronized` | Same-JVM threads sharing one lock object | Does not span JUnit setup/teardown if used only inside test body |
| DB advisory lock/distributed lease | Cross-process external resource truly shared | Needs timeouts, crash recovery, consistency design |

**Guideline:** If you can avoid sharing files, records, or queues via per-test fixtures, **no lock is needed** and tests usually run faster. When multiple tests must share a Spring singleton or global property, use the narrowest `@ResourceLock` covering all mutations. Reserve `@Isolated` for global mutations whose readers are too hard to inventory.

## 7. Complete, Runnable Project: Java 17 + Spring Boot 3.3.5

The project includes a mutable Spring singleton **solely to illustrate test interference**, two writer classes, one reader class, system property tests, temp directory tests, and an `@Isolated` class for default locale.

**Example policies:**
- Writers must hold `READ_WRITE("demo:sequence")`.
- Readers use only `READ("demo:sequence")`, **never resetting state**.
- Every writer method resets data in `@BeforeEach`/`@AfterEach` while protected end-to-end by JUnit.
- `SystemPropertiesLockTest` applies the lock at **class level** because the entire class modifies system properties.
- `IndependentTempDirectoryTest` **uses no lock**, because its two files live in distinct paths.
- `GlobalLocaleIsolatedTest` uses `@Isolated` and always restores the default locale.
- No reliance on method or class execution order.
- **12 JUnit Jupiter tests** across 6 classes, with no intentionally failing tests.

### 7.1. Directory Tree

~~~text
settings.gradle
build.gradle
src/main/java/demo/locks/LockingDemoApplication.java
src/main/java/demo/locks/SharedSequence.java
src/test/resources/junit-platform.properties
src/test/java/demo/locks/SpringCounterATest.java
src/test/java/demo/locks/SpringCounterBTest.java
src/test/java/demo/locks/CounterReadersTest.java
src/test/java/demo/locks/SystemPropertiesLockTest.java
src/test/java/demo/locks/IndependentTempDirectoryTest.java
src/test/java/demo/locks/GlobalLocaleIsolatedTest.java
~~~

**settings.gradle**

~~~groovy
rootProject.name = 'spring-junit-resource-lock'
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

    // One worker JVM, with multiple JUnit Jupiter workers inside.
    maxParallelForks = 1
    forkEvery = 0

    testLogging {
        events 'passed', 'failed', 'skipped'
    }
}
~~~

**src/test/resources/junit-platform.properties**

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
junit.jupiter.execution.parallel.config.strategy=fixed
junit.jupiter.execution.parallel.config.fixed.parallelism=4
~~~

`maxParallelForks=1` keeps **one JVM** so classes observe the same JUnit resource keys; `fixed.parallelism=4` lets Jupiter schedule multiple nodes concurrently **within that JVM**. Even with `maxParallelForks=1`, total Spring/GC threads can be higher; it does not mean "only one thread in the JVM".

`spring-boot-starter` suffices to create a Spring `ApplicationContext` without an HTTP server. `spring-boot-starter-test` brings JUnit Jupiter and Spring TestContext; no explicit JUnit engine version declaration is needed.

### 7.2. Spring Boot Main Class

**src/main/java/demo/locks/LockingDemoApplication.java**

~~~java
package demo.locks;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LockingDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(LockingDemoApplication.class, args);
    }
}
~~~

### 7.3. Shared Singleton for Demonstration

**src/main/java/demo/locks/SharedSequence.java**

~~~java
package demo.locks;

import org.springframework.stereotype.Service;

@Service
public class SharedSequence {

    // Intentionally mutable and unsynchronized to create a fixture
    // that JUnit tests must coordinate under the same resource key.
    private int value;

    public void reset() {
        value = 0;
    }

    public int next() {
        return ++value;
    }

    public int current() {
        return value;
    }
}
~~~

**Production warning:** `++value` is not an atomic read-modify-write under real concurrent threads; this is a **demo fixture**, not a singleton to copy into a production backend. When real applications require concurrency, use stateless services, transactions, atomic DB updates, or proper synchronization primitives. JUnit `@ResourceLock` protects only cooperating test nodes declaring the same key.

Two Spring test classes sharing the **exact same `@SpringBootTest(webEnvironment=NONE)`** normally reuse the Spring TestContext cached `ApplicationContext` and thus share the `SharedSequence` singleton. However, differing profiles/test properties/customizers produce different cache keys. **JUnit locks do not prove two classes shared a context**; verify context reuse separately via bean references or Spring context cache stats.

## 8. Two Writer Test Classes: READ_WRITE Across Setup and Teardown

### 8.1. SpringCounterATest: 3 Tests

**src/test/java/demo/locks/SpringCounterATest.java**

~~~java
package demo.locks;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Execution(ExecutionMode.CONCURRENT)
class SpringCounterATest {

    @Autowired
    SharedSequence sequence;

    // All @Test methods below hold the "demo:sequence" lock.
    @BeforeEach
    void prepare() {
        sequence.reset();
        assertEquals(0, sequence.current());
    }

    @AfterEach
    void cleanup() {
        sequence.reset();
    }

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ_WRITE)
    void initialIncrementIsOne() {
        assertEquals(1, sequence.next());
        assertEquals(1, sequence.current());
    }

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ_WRITE)
    void threeCallsProduceConsecutiveNumbers() {
        assertEquals(1, sequence.next());
        assertEquals(2, sequence.next());
        assertEquals(3, sequence.next());
        assertEquals(3, sequence.current());
    }

    @Test
    @ResourceLock("demo:sequence")
    void resettingWithinProtectedMethodIsValid() {
        assertEquals(1, sequence.next());
        sequence.reset();
        assertEquals(0, sequence.current());
        assertEquals(1, sequence.next());
    }
}
~~~

**Exactly 3 `@Test` methods.** The first two explicitly specify `READ_WRITE`, while the last uses the shorthand since `READ_WRITE` is the **default mode**. For each method, the lock is acquired before `@BeforeEach` and released after `@AfterEach`, so Class A's reset never interleaves inside Class B's test body when B declares the same key.

**Why does the class still have `@Execution(CONCURRENT)`?** To permit JUnit's parallel scheduler to execute other tests with independent resources concurrently; **methods sharing the same `WRITE` key still wait for each other**. Never assert that they start simultaneously. Even though all 3 methods share a resource, JUnit guarantees no specific execution order.

### 8.2. SpringCounterBTest: 2 Tests

**src/test/java/demo/locks/SpringCounterBTest.java**

~~~java
package demo.locks;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Execution(ExecutionMode.CONCURRENT)
class SpringCounterBTest {

    @Autowired
    SharedSequence sequence;

    @BeforeEach
    void prepare() {
        sequence.reset();
    }

    @AfterEach
    void cleanup() {
        sequence.reset();
    }

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ_WRITE)
    void otherClassAlsoStartsFromOne() {
        assertEquals(1, sequence.next());
        assertEquals(1, sequence.current());
    }

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ_WRITE)
    void otherClassCanAdvanceAndReset() {
        assertEquals(1, sequence.next());
        assertEquals(2, sequence.next());
        assertEquals(2, sequence.current());
    }
}
~~~

**Exactly 2 `@Test` methods.** B and A do not share a Java test object instance, yet may share the **Spring singleton bean** from the cached context. The resource key `"demo:sequence"` coordinates both; no separate `ReentrantLock` is needed per test class.

A typo like `"demo:sequences"` in B creates a **completely separate resource**; JUnit will not know both keys guard the same bean. In large production test suites, define a compile-time constant `public static final String SEQUENCE = "demo:sequence";` in a test utility class and reference it everywhere.

## 9. Reader Test Class: READ Without Mutating the Shared Fixture

**src/test/java/demo/locks/CounterReadersTest.java**

~~~java
package demo.locks;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.*;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
@Execution(ExecutionMode.CONCURRENT)
class CounterReadersTest {

    @Autowired
    SharedSequence sequence;

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ)
    void readerObservesCleanBaseline() {
        assertEquals(0, sequence.current());
    }

    @Test
    @ResourceLock(
            value = "demo:sequence",
            mode = ResourceAccessMode.READ)
    void multipleReadsDoNotAlterState() {
        int a = sequence.current();
        int b = sequence.current();

        assertEquals(0, a);
        assertEquals(a, b);
    }
}
~~~

**Exactly 2 `@Test` methods.** Both readers share the `READ` key, may run concurrently with each other, and **never overlap with writers** holding `READ_WRITE` on `"demo:sequence"`. They have no `@BeforeEach` reset because resetting is a write—which would make `READ` invalid.

When a reader acquires the lock after a writer, the writer's `@AfterEach` already ran under the `READ_WRITE` lock and reset the counter to 0. Hence asserting 0 is sound within **this specific fixture set**. If other code spawns background threads mutating `SharedSequence`, or another test omits the lock, this guarantee breaks. `@ResourceLock` does not lock application threads.

**`READ` does not guarantee two tests overlapped.** Verifying overlap requires a dedicated scheduler/concurrency probe using latches and bounded waits, not inference from annotations.

## 10. Class-Level Lock for JVM System Properties

**src/test/java/demo/locks/SystemPropertiesLockTest.java**

~~~java
package demo.locks;

import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;

import static org.junit.jupiter.api.Assertions.*;

@Execution(ExecutionMode.CONCURRENT)
@ResourceLock(
        value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
class SystemPropertiesLockTest {

    private static final String KEY =
            "demo.resource-lock.sample-mode";

    private String previous;

    @BeforeEach
    void saveOldValue() {
        previous = System.getProperty(KEY);
    }

    @AfterEach
    void restoreOldValue() {
        if (previous == null) {
            System.clearProperty(KEY);
        } else {
            System.setProperty(KEY, previous);
        }
    }

    @Test
    void canSetAlphaForOneMethod() {
        System.setProperty(KEY, "alpha");
        assertEquals("alpha", System.getProperty(KEY));
    }

    @Test
    void canSetBetaForAnotherMethod() {
        System.setProperty(KEY, "beta");
        assertEquals("beta", System.getProperty(KEY));
    }
}
~~~

**Exactly 2 `@Test` methods.** Since the whole class mutates system properties, a class-level lock is simple and clear. `@BeforeEach` saves the previous value and `@AfterEach` restores it; JUnit coordinates with any other tests declaring the predefined `Resources.SYSTEM_PROPERTIES` key.

**Limits:**
- Only JUnit tests participating under the same resource key are synchronized by the scheduler.
- Spring background threads or third-party code do not wait on JUnit locks.
- Modifying a `System` property after Spring constructs `@Value`/`@ConfigurationProperties` beans **does not automatically refresh those beans**. Properties affecting wiring should be configured via test profiles, `@TestPropertySource`, `@SpringBootTest(properties=...)`, or isolated contexts.
- Choose property names that do not collide with JVM/Java security settings in samples.
- If a test genuinely mutates many global properties, prefer the predefined key covering the **whole table** rather than an overly narrow custom key.

## 11. `@TempDir`: Better Not to Share Files at All

**src/test/java/demo/locks/IndependentTempDirectoryTest.java**

~~~java
package demo.locks;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.junit.jupiter.api.parallel.Execution;
import org.junit.jupiter.api.parallel.ExecutionMode;

import static org.junit.jupiter.api.Assertions.*;

@Execution(ExecutionMode.CONCURRENT)
class IndependentTempDirectoryTest {

    @Test
    void firstTestHasOwnReport(@TempDir Path dir)
            throws Exception {

        Path file = dir.resolve("report.txt");

        Files.writeString(
                file, "first", StandardCharsets.UTF_8);

        assertEquals(
                "first",
                Files.readString(file, StandardCharsets.UTF_8));
    }

    @Test
    void secondTestHasOwnReport(@TempDir Path dir)
            throws Exception {

        Path file = dir.resolve("report.txt");

        Files.writeString(
                file, "second", StandardCharsets.UTF_8);

        assertEquals(
                "second",
                Files.readString(file, StandardCharsets.UTF_8));
    }
}
~~~

**Exactly 2 `@Test` methods.** Even though both use `report.txt`, Jupiter injects a **separate temporary directory** for each `@TempDir` method parameter. Physical paths differ; tests never conflict and **need no lock**. This increases parallelizability far better than serializing two writes to one shared path.

If production app code always writes to `build/reports/report.txt` ignoring `@TempDir`, both tests still collide. Integration tests should inject a base output directory so the code under test actually writes to isolated paths. The DB equivalent is unique schemas/test tenants/record IDs; the broker equivalent is unique topic/queue/group identifiers.

## 12. `@Isolated`: When All Other Classes Must Be Excluded

**src/test/java/demo/locks/GlobalLocaleIsolatedTest.java**

~~~java
package demo.locks;

import java.util.Locale;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.parallel.Isolated;

import static org.junit.jupiter.api.Assertions.*;

@Isolated("Temporarily mutates JVM-wide default Locale")
class GlobalLocaleIsolatedTest {

    @Test
    void canChangeDefaultLocaleAndRestoreIt() {
        Locale original = Locale.getDefault();

        try {
            Locale vietnamese =
                    Locale.forLanguageTag("vi-VN");

            Locale.setDefault(vietnamese);

            assertEquals(vietnamese, Locale.getDefault());
            assertEquals("vi", Locale.getDefault().getLanguage());
        } finally {
            Locale.setDefault(original);
        }
    }
}
~~~

**Exactly 1 `@Test` method.** `@Isolated` applies **at the class level**. Within the Jupiter test plan, this class does not overlap with other test classes, even if those classes are unaware of any resource key. This fits a JVM-global mutation whose readers are difficult to inventory exhaustively.

**Key differences:** `@Isolated` still does not exclude **background application threads**, another Gradle test worker JVM, or another CI pipeline job. Nor does it restore `Locale` automatically: `finally` remains essential. If every test reading `Locale` can declare `Resources.LOCALE`, a method-level `@ResourceLock` on that key is narrower and usually preserves higher parallelism.

## 13. Total of 12 JUnit Tests and Run Commands

| Class | `@Test` | What Is Verified |
|---|---:|---|
| `SpringCounterATest` | 3 | Mutate/reset singleton under method-level `READ_WRITE` |
| `SpringCounterBTest` | 2 | Locking the same key across classes |
| `CounterReadersTest` | 2 | `READ`-only, no mutation |
| `SystemPropertiesLockTest` | 2 | Class-level `Resources.SYSTEM_PROPERTIES`, cleanup |
| `IndependentTempDirectoryTest` | 2 | `@TempDir` needing no shared lock |
| `GlobalLocaleIsolatedTest` | 1 | `@Isolated` and restoring JVM default `Locale` |
| **Total** | **12** | No `@Disabled`, order-independent |

Run the project if the Gradle Wrapper is present:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If you only copied the source files, `settings.gradle`, and `build.gradle` without **generating Wrapper scripts/JAR**, `./gradlew` will not exist yet. Run `gradle test` with a compatible Gradle installation or generate the Gradle Wrapper first.

Run individual classes:

~~~bash
./gradlew test --tests demo.locks.SpringCounterATest
./gradlew test --tests demo.locks.SpringCounterBTest
./gradlew test --tests demo.locks.CounterReadersTest
./gradlew test --tests demo.locks.SystemPropertiesLockTest
./gradlew test --tests demo.locks.IndependentTempDirectoryTest
./gradlew test --tests demo.locks.GlobalLocaleIsolatedTest
~~~

The HTML report is normally at `build/reports/tests/test/index.html`. **Expected design outcome**: 12 test methods discovered by JUnit Jupiter and PASS, with no timing/order-dependent assertions. This is the **expected result from source and APIs**, not a claim that Gradle was executed.

**Note:** Running each class in separate Gradle commands does not prove lock coordination **across classes**, because each command may launch a new test JVM. To verify locking between writer classes A/B and readers C, run the **full suite** with `maxParallelForks=1` as configured. Never test "same JVM" by running tests separately and stitching timings together.

No fixed stdout ordering exists when JUnit's parallel scheduler runs. Thread names and test completion order can vary; assert **behavior/invariants**, not ordered log-line snapshots.

## 14. Why Can a Properly Designed Locked Test Still Flake?

### 14.1. One Test Does Not Participate in the Key Contract

If Classes A and B declare `"demo:sequence"` while C uses `"demo:sequences"`, JUnit can schedule C alongside A/B. If C's `@BeforeEach` resets the singleton, A/B's assertions can fail. Inventory **every** test touching a shared fixture, centralize keys as constants, and review when adding new tests.

### 14.2. Declaring READ While Performing an Indirect Write

A test reading a response might hit a GET endpoint that updates `lastAccessedAt`, audit logs, or caches. `@BeforeEach` might truncate the DB. JUnit sees only the `READ` annotation and does not inspect implementations. If an operation mutates, use `READ_WRITE` or remove/isolate the write. `READ` mode does not turn shared state immutable.

### 14.3. Workers Still Running After `@AfterEach`

A `@Test` invokes `@Async void` and returns before the task sends a message or updates the DB. After `@AfterEach`, JUnit releases the resource lock while the background task continues running; the next test can modify the shared fixture while the old worker still writes.

Fixes:
- Prefer `CompletableFuture`/`Future` so you can **await completion with a finite timeout**.
- With message listeners, wait for a specific business condition or use Awaitility/`CountDownLatch` with a deadline.
- Stop/cancel workers and release resources within the right lifecycle.
- Never use a fixed `Thread.sleep(500)` pretending a worker finished.
- Separate schemas/queues/records so concurrent consumers never collide.

**`@ResourceLock` is not propagated to background threads**: it is a test scheduler lock, not a system-wide distributed mutex.

### 14.4. Multiple JVMs or CI Pipelines

JUnit resource locks in JVM A are invisible to JVM B. A setup with Gradle `maxParallelForks=4`, multi-module builds, and CI shards can run four to ten JVMs simultaneously. If all share the `"public"` test DB schema, `ResourceLock` alone is insufficient. Preferred solutions:
- Dedicated schema/database/container per fork/job.
- Unique fixture prefixes/tenant IDs.
- Independent cleanup/transaction boundaries.
- For strictly global resources, **DB/file/distributed coordination** locks with timeouts and crash recovery.

`@DirtiesContext` only evicts the Spring `ApplicationContext`; it does not wipe external DBs or brokers. Never use it to "improve safety" for shared external state when the problem lives outside the JVM.

### 14.5. Mock Resets and Spring TestContext Caching

Spring Boot 3.3 uses `@MockBean`/`@SpyBean` to override or spy on beans in the test context. Two tests sharing a cached context while stubbing/resetting the same mock can interfere. Spring TestContext documentation advises **against arbitrarily parallelizing** tests using `@DirtiesContext`, `@MockBean`/`@SpyBean`, ordering, or shared DBs/brokers/filesystems.

`ResourceLock` can reduce collisions **if every participant declares the exact key**, yet cannot prevent an unaware third test from closing the Spring context or resetting a bean. For context-lifecycle-sensitive test groups, prefer serial execution or a dedicated test task rather than forcing a shared lock key.

### 14.6. Tests Intended to Expose Production Races

If a business service suffers a lost update under two concurrent HTTP requests, never slap the same `READ_WRITE` `ResourceLock` on two test methods sending the requests and assume the race is fixed. That lock **prevents the two JUnit methods from overlapping**, masking the bug.

To test concurrent algorithms:
1. Launch at least two genuinely independent tasks/HTTP requests.
2. Use an executor with sufficient workers.
3. Use `CountDownLatch`/barriers to force the risky interleaving.
4. Await both completions via bounded `Future.get`.
5. Inspect DB state, success/failure counts, unique constraints, and side effects.
6. Run against the appropriate transaction policy and DB vendor.

Thus `@ResourceLock` protects **test fixtures**, whereas concurrency tests verify **business correctness**. These are two distinct goals; never substitute one for the other.

## 15. How Does @Execution(SAME_THREAD) Differ from @Isolated?

**`@Execution(SAME_THREAD)`** controls the execution mode of one JUnit node, commonly keeping methods inside a class from running in parallel with each other or keeping a method on its parent thread. Yet **another class** can still run concurrently and touch the same resource. Thus `SAME_THREAD` cannot isolate a global property or shared DB across classes.

**`@Isolated`** prevents a test class from overlapping with any other class coordinated by Jupiter in the same plan. It provides **broader** protection than a named lock and can create a bottleneck if many classes are marked isolated.

**`@ResourceLock`** coordinates by resource name. If Test A and B touch a file while C performs pure Java math, A and B wait for each other while C can run alongside either of them. That is the main advantage when optimizing parallel suites.

| Need | Choice |
|---|---|
| One class wants sequential methods due to shared instance field | `@Execution(SAME_THREAD)` or remove shared state |
| Tests across different classes mutate the same test table | `@ResourceLock` if single-JVM; better yet, separate schemas |
| JVM-wide locale/default encoding mutated without inventorying readers | `@Isolated` + restore |
| Tests create reports with the same name yet can vary base directory | `@TempDir`, no lock needed |
| Cross-JVM CI jobs sharing a DB | DB/schema isolation or cross-process lock |
| Business service needs race protection | Production synchronization/DB transactions, dedicated concurrency tests |

## 16. Measuring Effectiveness and Keeping the Test Suite Healthy

When introducing `@ResourceLock` to a suite:
1. Measure the baseline: total test runtime, Gradle forks, Jupiter parallelism, reproducible failures.
2. Inventory shared resources. Name keys after the **resource**, not the test.
3. Prefer isolated fixtures before opting for `READ_WRITE`.
4. Choose `READ` strictly when setup, test body, and teardown perform zero mutations.
5. Run the full suite repeatedly in the same JVM to verify stability.
6. Test under real CI settings with multiple forks/jobs; if races persist, switch to cross-process isolation.
7. After locking, re-measure runtime. Overly broad keys can serialize too much and negate concurrency gains.
8. Never put timing assertions like `assertTrue(testFinishedUnder200ms)` in functional tests. CI CPU/GC/network varies.
9. Never interpret N green runs as proof that **zero races remain**.
10. Document the boundary: cooperating Jupiter tests within one execution plan/JVM, excluding background threads or other processes.

**Valid evaluation example:** Before: 10 out of 100 CI runs failed because tests mutated the same JVM property. After: 0 failures across 100 runs with proper property restoration; suite runtime stayed roughly flat or improved due to selective parallelism. That is empirical evidence of improvement. Never invent numbers like these without measuring.

**Invalid evaluation example:** "Added one `@ResourceLock` to Class A, ran Class A alone once and it passed, so the system is thread-safe." Running alone excludes Class B from contention, leaving `@ResourceLock` untested under the exact condition that matters.

## 17. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Test A/B both locked yet still race | Mismatched resource keys or a third class omitted the lock | Standardize names, inventory all participants |
| `READ` test corrupts data | Setup/teardown performs a write | Switch to `READ_WRITE` or isolate/reset fixture |
| Adding locks slows the suite | Overly broad class-level/`GLOBAL` lock | Use method-level locks and specific keys |
| `@ResourceLock` not found | Wrong import or missing JUnit Jupiter | `org.junit.jupiter.api.parallel.ResourceLock` |
| `target=CHILDREN` fails to compile | Using JUnit 5.12 API on Jupiter 5.10 | Remove newer attributes or upgrade stack consistently |
| `@Execution(CONCURRENT)` yet no overlap | Conflicting locks or scheduler lacked workers | Never require overlap as a PASS condition |
| `@Execution(SAME_THREAD)` yet Class B runs concurrently | `SAME_THREAD` is not a global mutex | Use `ResourceLock` or `Isolated` |
| 4 Gradle forks, DB still races | Lock does not span processes | Unique schemas/containers/DB advisory locks |
| System property restored improperly | Not snapshotted before mutation, missing `finally`/`AfterEach` | Distinguish `null` vs value; `clear`/`set` accurately |
| Spring `@Value` unchanged after setting System property | Bean created before property changed | Supply test properties at context bootstrap |
| JUnit test passes yet async task breaks next test | Test returned before worker finished | Await completion/cancel/clean up |
| `@DirtiesContext` closes active context | Context cache evicted inside parallel suite | Do not parallelize that context-lifecycle group |
| `@MockBean` stubbing gets reset mid-test | Shared mock/context | Reset policy, isolate tests, serialize relevant group |
| `@TestMethodOrder` doesn't stop interference | Ordering is not cross-class mutual exclusion | Data independence + locks |
| `build/report.txt` gets overwritten | Shared path | `@TempDir` or shared file lock |
| `@Isolated` still sees external worker mutate state | Isolation covers only Jupiter plan | Cross-process synchronization |
| Singleton test bean unexpectedly shared | Spring Context cache reuse | Reset fixture and agree on resource key |
| Concurrent `READ`/`READ` produces wrong result | Resource wasn't truly read-only | Audit implicit writes/caches |
| Jupiter uses `PER_CLASS` and methods race | Mutable instance fields shared | Use `PER_METHOD`, `SAME_THREAD`, or proper locks |
| Running classes one by one always passes | No concurrent classes per invocation | Run full suite, check CI parallel config |
| Logs appear out of order | Concurrent execution guarantees no log order | Assert state, not ordered log snapshots |

### 17.1. Quick Debugging Sequence

1. Record which test class/method failed and which state it touches.
2. Identify whether the resource lives in **JVM static**, a Spring singleton, a file, DB, or broker.
3. Determine the active number of JUnit workers, Gradle forks, and CI jobs.
4. Inspect every test capable of mutating that state, including `@BeforeEach` and `@AfterEach`.
5. If shared within one JVM and inseparable, standardize the `@ResourceLock` key.
6. Pick `READ` vs `READ_WRITE` from **full-lifecycle side effects**, not method names.
7. Restore global state even when assertions fail.
8. With `@Async`/listeners, await side-effect completion before the test returns.
9. For external resources with multi-process users, isolate at the external resource itself.
10. For business concurrency bugs, write a dedicated concurrency test instead of serializing requests.
11. Audit `@DirtiesContext`/mock resets/test context caching before enabling parallel Spring tests broadly.
12. Re-run the full suite multiple times, measuring stability and duration.

## 18. Hands-On Exercises

**Exercise 1 — Mismatched key:** Class A uses `@ResourceLock("db:orders")`, B uses `"DB:orders"`. Is there mutual exclusion? Why must Java String keys match character-for-character?

**Exercise 2 — Matrix:** A holds `READ`, B holds `READ`, C holds `READ_WRITE` on the same key. Which pairs may overlap? Should you assert that A and B definitely overlap?

**Exercise 3 — BeforeEach:** Add a `reset()` inside `@BeforeEach` of a `READ` reader. Why is this broken? Should you switch to `READ_WRITE` or remove the mutation?

**Exercise 4 — Class-level:** Move `@ResourceLock("demo:sequence")` up to Class A instead of per-method. When is this cleaner, and when does it hurt parallelism excessively?

**Exercise 5 — System Properties:** Remove `@AfterEach` restoration. Why can a later test still observe the leftover value despite the lock?

**Exercise 6 — Isolated:** Compare `@Isolated` with `@ResourceLock(Resources.LOCALE)`. When must all other Jupiter test classes be excluded?

**Exercise 7 — TempDir:** Two tests both write `report.txt`. Switch to `@TempDir` and verify paths are independent; why is `READ_WRITE` no longer needed?

**Exercise 8 — Spring context:** Create two classes sharing `@SpringBootTest` and a mutable singleton, toggling the lock on and off. Why does passing individually fail to prove isolated state?

**Exercise 9 — Gradle forks:** Increase `maxParallelForks` from 1 to 4 with multiple classes touching the test DB. Why is sharing a resource key insufficient?

**Exercise 10 — Async:** A test has `@ResourceLock("queue")`, yet a worker writes to the queue after the test returns. Design appropriate `Future`/latch cleanup.

**Exercise 11 — Retry test:** Share a static fake server to trigger retries. When is `ResourceLock` needed, and when is a dedicated random-port server better?

**Exercise 12 — Mongo/PostgreSQL:** Provision a separate schema/collection per test run; compare performance against locking an entire DB.

**Exercise 13 — Consumer groups:** Share a Kafka topic and group ID across two tests. Separate group/topic names, or choose a shared resource lock within one JVM.

**Exercise 14 — Business race:** Two concurrent transfers from the same account. Why can placing `READ_WRITE` between two test methods mask a lost-update bug? Use a barrier and DB invariants instead.

**Exercise 15 — Optimization:** Run the suite with a single `GLOBAL` key, then split keys by DB/file/cache and measure concurrency/CI time. Never fabricate timings; record actual measurements.

**Exercise 16 — Code review:** Build a resource ownership table for your suite: key names, where fixtures reset, access modes, process scope, and maintainer.

## 19. Official References

- [JUnit Jupiter 5.10.5 User Guide — Parallel Execution](https://docs.junit.org/5.10.5/user-guide/junit-user-guide-5.10.5.pdf): configuring execution modes, resource locks, and isolation.
- [JUnit Jupiter 5.11.3 — ResourceLock API](https://docs.junit.org/5.11.3/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/ResourceLock.html): `value`, `mode`, default `READ_WRITE`, and lifecycle scope.
- [JUnit Jupiter 5.10 — ResourceAccessMode](https://docs.junit.org/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/ResourceAccessMode.html): `READ`/`READ_WRITE` semantics.
- [JUnit Jupiter 5.10 — Resources](https://docs.junit.org/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/Resources.html): `SYSTEM_PROPERTIES`, `SYSTEM_OUT`, `SYSTEM_ERR`, `LOCALE`, `TIME_ZONE`.
- [JUnit Jupiter 5.10 — Isolated](https://docs.junit.org/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/Isolated.html): class-wide isolation.
- [JUnit Jupiter 5.10 — Execution](https://docs.junit.org/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/parallel/Execution.html): `SAME_THREAD` and `CONCURRENT`.
- [JUnit Jupiter 5.10 — TempDir](https://docs.junit.org/5.10.0/api/org.junit.jupiter.api/org/junit/jupiter/api/io/TempDir.html): unique temporary directory per test.
- [Spring Framework — Parallel Test Execution](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/parallel-test-execution.html): limitations with `DirtiesContext`, mocks, ordered tests, and external shared state.
- [Spring Framework — Context Caching](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/caching.html): `ApplicationContext` reuse within a JVM.
- [Spring Boot 3.3 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html): `SpringBootTest`, TestContext, and integration testing.
- [Gradle — Testing in JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform`, `maxParallelForks`, `forkEvery`.
- [Java 17 — ReentrantReadWriteLock](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/locks/ReentrantReadWriteLock.html): distinguishing a Java runtime lock from a JUnit scheduling lock.

**Summary:** When enabling JUnit parallelism, **isolate data before locking**. If a resource must still be shared, declare **the exact same `@ResourceLock` key**, choose **`READ`** for genuinely non-mutating readers and **`READ_WRITE`** for writers, covering both `@BeforeEach`/`@AfterEach`. `@Isolated` is for classes altering hard-to-inventory JVM global state; `@TempDir` solves file conflicts via unique paths. Never use `ResourceLock` to mask business races, and never expect it to synchronize across Gradle JVMs or CI jobs. Tests should be order-independent, clean up after themselves, and assert stable invariants instead of depending on scheduling timing.