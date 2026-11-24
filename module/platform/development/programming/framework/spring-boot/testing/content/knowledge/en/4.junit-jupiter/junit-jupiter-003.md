# PER_METHOD, PER_CLASS Lifecycles and Shared State in JUnit Jupiter

A test may pass when run individually today yet fail when running the whole suite because tests are accidentally sharing state. In JUnit Jupiter, `@TestInstance` determines **how many objects of the test class JUnit creates**. However, giving each test its own object **does not automatically isolate** `static` fields, Spring singleton beans, databases, files, caches, or external services. Therefore, you need to understand both the test instance lifecycle and where data is actually stored.

This lesson focuses on `TestInstance.Lifecycle.PER_METHOD` and `PER_CLASS`, the order of lifecycle callbacks, the consequences of mutable shared state, and how to test Spring Boot without depending on which test runs first.

## 1. Concept: which object is the test instance?

Given a test class:

```java
class PriceCalculatorTest {
    private int calls = 0;

    @Test
    void first() {
        calls++;
    }

    @Test
    void second() {
        calls++;
    }
}
```

The `calls` field belongs to the **`PriceCalculatorTest` instance**, not to each individual method. JUnit Jupiter must decide whether to create a new object before running each test, or share a single object across the tests in the class. The answer depends on the **test instance lifecycle**.

| Property | `PER_METHOD` | `PER_CLASS` |
| --- | --- | --- |
| Default in JUnit Jupiter unless configured otherwise | **Yes** | No |
| Number of test class instances | New instance for each test method/invocation | One instance shared across tests in the class |
| Instance fields modified in an earlier test | Do not carry over to the next test instance | Can remain and affect subsequent tests |
| `@BeforeEach` / `@AfterEach` | Run before/after each test | Still run before/after each test |
| `@BeforeAll` / `@AfterAll` | Normally must be `static` | Can be instance methods |
| Risk of order dependency via instance fields | Lower, due to fresh objects | Higher if state changes without being reset |
| Effect on Spring singletons/DB/`static` | Does not isolate automatically | Does not isolate automatically |

JUnit Jupiter defaults to `PER_METHOD` unless the test class or JUnit Platform configuration changes that choice. You can explicitly annotate the lifecycle on the class so readers do not have to guess:

```java
@TestInstance(TestInstance.Lifecycle.PER_METHOD)
class ExampleTest {
    // Each execution of a test method gets a new ExampleTest instance.
}
```

or:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class ExampleTest {
    // Test methods in the class share a single ExampleTest instance.
}
```

**The two examples above are illustrative snippets**, requiring JUnit imports and actual test definitions; section 4 provides complete files.

## 2. Lifecycle sequence and callbacks

For a standard test class, a Jupiter cycle consists of `@BeforeAll`, creating/obtaining the test instance, `@BeforeEach`, running the test, `@AfterEach`, and finally `@AfterAll`. Where instance creation happens differs by lifecycle.

**`PER_METHOD` (default):**

```text
@BeforeAll (static; once for the class)
    ├── new TestClass() -> @BeforeEach -> test A -> @AfterEach
    ├── new TestClass() -> @BeforeEach -> test B -> @AfterEach
    └── new TestClass() -> @BeforeEach -> test C -> @AfterEach
@AfterAll (static; once for the class)
```

**`PER_CLASS`:**

```text
new TestClass()  (once for the class)
@BeforeAll (non-static allowed)
    ├── @BeforeEach -> test A -> @AfterEach
    ├── @BeforeEach -> test B -> @AfterEach
    └── @BeforeEach -> test C -> @AfterEach
@AfterAll (non-static allowed)
```

The diagrams assume tests run sequentially and do not depict additional callbacks from extensions, superclasses, interfaces, or nested tests. Do not infer an execution order of A/B/C when there is **no** explicit ordering configuration.

Each annotation serves a distinct role:

- **`@BeforeAll`** runs once before the container/class tests, suitable for creating shared fixtures or preparing resources. With `PER_METHOD`, this method must normally be `static`; with `PER_CLASS`, it can access instance fields.
- **`@BeforeEach`** runs before each test execution, used to build or reset state belonging to a single test. It **still** runs for every test under `PER_CLASS`.
- **`@AfterEach`** runs after each test execution, typically cleaning up test-owned resources or checking postconditions.
- **`@AfterAll`** runs once after the container/class tests, typically releasing shared fixtures. The `static` constraint is the same as for `@BeforeAll`.
- **Constructor/instance field initializers** run every time JUnit creates a test instance: multiple times in `PER_METHOD`, once in `PER_CLASS`.

Jupiter lifecycle methods should not be `private` and must have a `void` return type; JUnit also supports parameter injection when an appropriate resolver is available. If you write a **non-static** `@BeforeAll` method in a class still using `PER_METHOD`, JUnit will report a lifecycle validation error when running tests. Switching to `PER_CLASS` solely to "fix the static error" can unintentionally cause mutable fields to be shared; evaluate resource scope first.

## 3. What is actually shared?

Consider each distinct kind of state:

| Where state is stored | Refreshed by JUnit `PER_METHOD`? | Explanation |
| --- | --- | --- |
| Instance field of the test class | **Yes** | Each test gets a new test class object and fresh initializers |
| Instance field of the test class with `PER_CLASS` | **No** | The same object is reused across tests; must be reset manually if needed |
| `static` field | **No** | Belongs to the class, existing independently of the test instance |
| Object held by an application's static cache/singleton | **No** | Creating a new test instance does not refresh this dependency |
| Spring `@Autowired` singleton | **Not guaranteed** | Beans belong to `ApplicationContext`; the context may be cached and reused |
| Database rows, file contents, message queues | **No** | This is state external to the test instance; requires its own isolation/cleanup mechanism |
| Local variable inside a test method | **Created fresh on each call** | Usually the easiest way to avoid tests contaminating each other |

**Distinguish "same instance" from "same dependency":** Two test methods running with two different test objects can still receive the exact same Spring singleton bean via `@Autowired`. If the bean mutates internal data, a subsequent test can observe side effects from the previous test even when the test class uses `PER_METHOD`.

Shared immutable objects (`String`, `List.of(...)`, `Map.of(...)`, or read-only configuration) are usually safer than shared mutable fixtures. "Safer" here is because tests cannot mutate the contents, not because `PER_CLASS` provides isolation on its own.

## 4. Runnable example: JUnit Jupiter and Spring Boot 3.3.x

The sample project uses **Java 17+**, Gradle Groovy DSL, JUnit Jupiter from `spring-boot-starter-test`, and Spring Boot 3.3.5. The example uses only an in-memory counter to clearly show the difference between a test instance and a Spring-managed bean. The tests do not require a database or external services.

Layout:

```text
settings.gradle
build.gradle
src/main/java/com/example/lifecycle/LifecycleApplication.java
src/main/java/com/example/lifecycle/CounterService.java
src/test/java/com/example/lifecycle/PerMethodLifecycleTest.java
src/test/java/com/example/lifecycle/PerClassLifecycleTest.java
src/test/java/com/example/lifecycle/PerClassIsolatedTest.java
src/test/java/com/example/lifecycle/SpringContextSharedTest.java
src/test/java/com/example/lifecycle/SpringIndependentTest.java
```

### 4.1. Project configuration

**`settings.gradle`**

```groovy
rootProject.name = 'junit-lifecycle-evidence'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/com/example/lifecycle/LifecycleApplication.java`**

```java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class LifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }
}
```

**`src/main/java/com/example/lifecycle/CounterService.java`**

```java
package com.example.lifecycle;

import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Service;

@Service
public class CounterService {
    private final AtomicInteger value = new AtomicInteger();

    public int increment() {
        return value.incrementAndGet();
    }

    public int current() {
        return value.get();
    }

    public void reset() {
        value.set(0);
    }
}
```

`CounterService` is a **singleton Spring bean** by default because it is annotated with `@Service`. `AtomicInteger` makes integer updates atomic; it does not mean each test receives its own counter, nor does it solve every concurrency issue across a multi-step scenario.

### 4.2. `PER_METHOD`: new test object, fresh instance fields

**`src/test/java/com/example/lifecycle/PerMethodLifecycleTest.java`**

```java
package com.example.lifecycle;

import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestInstance(TestInstance.Lifecycle.PER_METHOD)
class PerMethodLifecycleTest {
    private static List<String> categories;
    private int calls = 0;

    @BeforeAll
    static void prepareSharedReadOnlyFixture() {
        categories = List.of("standard", "express");
    }

    @BeforeEach
    void prepareEachTest() {
        assertEquals(0, calls);
        calls++;
    }

    @Test
    void firstScenario() {
        assertEquals(1, calls);
        assertEquals("standard", categories.get(0));
    }

    @Test
    void secondScenario() {
        assertEquals(1, calls);
        assertEquals("express", categories.get(1));
    }

    @AfterEach
    void checkEachTest() {
        assertEquals(1, calls);
    }

    @AfterAll
    static void verifySharedFixture() {
        assertEquals(2, categories.size());
    }
}
```

Regardless of which test runs first, `calls` starts at 0 because each test receives a new `PerMethodLifecycleTest` instance. `@BeforeEach` increments `calls` to 1, and both the test and `@AfterEach` assert 1. Conversely, `categories` is `static` so it is shared across test instances; in this example it holds an immutable list and is only read.

This is an important scope example: **`PER_METHOD` refreshes instance fields of the test class, not `static` fields.**

### 4.3. `PER_CLASS`: same object, sees previous mutations

**`src/test/java/com/example/lifecycle/PerClassLifecycleTest.java`**

```java
package com.example.lifecycle;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestMethodOrder;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class PerClassLifecycleTest {
    private int visits;

    @BeforeAll
    void initializeOnce() {
        visits = 0;
    }

    @BeforeEach
    void beforeEachScenario() {
        // Callback still runs before each test even with a single test instance.
    }

    @Test
    @Order(1)
    void firstScenario() {
        visits++;
        assertEquals(1, visits);
    }

    @Test
    @Order(2)
    void secondScenario() {
        visits++;
        assertEquals(2, visits);
    }

    @AfterAll
    void afterAllScenarios() {
        assertEquals(2, visits);
    }
}
```

Here `@BeforeAll` and `@AfterAll` **do not need to be static** because the entire class uses one instance. `visits` is incremented in the first test, and the second test sees that value. `@TestMethodOrder(OrderAnnotation.class)` and `@Order` are used **strictly to make the experiment's order explicit**.

Do not treat this style of order dependency as a standard architectural pattern. If you run a single test from the IDE, `secondScenario` can fail because the first test did not run to increment `visits`. If a test fails before updating state, subsequent tests are affected as well. Reliable test suites should allow every test to run independently.

### 4.4. `PER_CLASS` can still keep tests independent

`PER_CLASS` is appropriate when you have a genuinely expensive fixture that can be shared safely. For mutable state belonging to each scenario, recreate it inside `@BeforeEach`.

**`src/test/java/com/example/lifecycle/PerClassIsolatedTest.java`**

```java
package com.example.lifecycle;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;

import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class PerClassIsolatedTest {
    private Map<String, Integer> fees;
    private List<String> visited;

    @BeforeAll
    void loadReadOnlyFixtureOnce() {
        fees = Map.of("standard", 30_000, "express", 50_000);
    }

    @BeforeEach
    void resetMutableState() {
        visited = new ArrayList<>();
    }

    @Test
    void standardScenario() {
        visited.add("standard");
        assertEquals(List.of("standard"), visited);
        assertEquals(30_000, fees.get("standard").intValue());
    }

    @Test
    void expressScenario() {
        visited.add("express");
        assertEquals(List.of("express"), visited);
        assertEquals(50_000, fees.get("express").intValue());
    }
}
```

`fees` is initialized once using an immutable `Map.of`. `visited` is a mutable list replaced with a fresh instance before **each** test. Therefore, the two tests do not depend on their execution order, even though they share one `PerClassIsolatedTest` instance. This is a much more intentional use of `PER_CLASS` than leaving a counter incrementing across tests.

### 4.5. Spring Boot case: `PER_METHOD` still shares singletons

**`src/test/java/com/example/lifecycle/SpringContextSharedTest.java`**

```java
package com.example.lifecycle;

import org.junit.jupiter.api.MethodOrderer;
import org.junit.jupiter.api.Order;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.TestMethodOrder;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@TestInstance(TestInstance.Lifecycle.PER_METHOD)
@TestMethodOrder(MethodOrderer.OrderAnnotation.class)
class SpringContextSharedTest {
    @Autowired
    private CounterService counterService;

    private int personalMarker;

    @Test
    @Order(1)
    void firstJUnitInstanceChangesSpringSingleton() {
        assertEquals(0, personalMarker);
        counterService.reset();
        assertEquals(1, counterService.increment());
        personalMarker = 99;
    }

    @Test
    @Order(2)
    void secondJUnitInstanceSeesSameSpringSingleton() {
        assertEquals(0, personalMarker);
        assertEquals(1, counterService.current());
    }
}
```

JUnit creates different `SpringContextSharedTest` objects for each method, so `personalMarker` in the second test is 0 rather than 99. However, `counterService` is injected from the running **Spring ApplicationContext**: both tests receive the same singleton bean from that context. Consequently, the second test can observe the value 1 left behind by the first test.

The experiment intentionally uses `@TestMethodOrder` to observe shared state predictably in a sequential configuration. This is **not** a recommended way to write business tests: it demonstrates the risk of depending on an earlier test. When tests run in parallel or something else modifies the singleton, ordering and outcomes can change.

**`src/test/java/com/example/lifecycle/SpringIndependentTest.java`**

```java
package com.example.lifecycle;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class SpringIndependentTest {
    @Autowired
    private CounterService counterService;

    @BeforeEach
    void resetSingletonBeforeEachScenario() {
        counterService.reset();
    }

    @Test
    void firstScenarioStartsFromZero() {
        assertEquals(0, counterService.current());
        assertEquals(1, counterService.increment());
    }

    @Test
    void secondScenarioAlsoStartsFromZero() {
        assertEquals(0, counterService.current());
        assertEquals(1, counterService.increment());
    }
}
```

In this sequential example, resetting in `@BeforeEach` ensures each scenario starts from 0. Yet in a real system, a singleton accessed concurrently by another class could be reset mid-execution; a stronger approach is to **avoid using mutable singletons for per-request/per-test data**, or to provide dedicated fixtures/isolation mechanisms. Database state, message brokers, and files are not reset by `counterService.reset()`.

### 4.6. How to run and expected evidence

Generate a Gradle Wrapper for the project or use the existing Wrapper in the sample project. From the project root:

```bash
./gradlew test --tests com.example.lifecycle.PerMethodLifecycleTest
./gradlew test --tests com.example.lifecycle.PerClassLifecycleTest
./gradlew test --tests com.example.lifecycle.PerClassIsolatedTest
./gradlew test --tests com.example.lifecycle.SpringContextSharedTest
./gradlew test --tests com.example.lifecycle.SpringIndependentTest
./gradlew test
```

On Windows PowerShell/CMD, replace `./gradlew` with `gradlew.bat`. Without changing parallel execution settings and with the code as shown above, the assertions are designed to **PASS**. This is the **expectation from the sample code**, not an actual captured Gradle log.

`PerMethodLifecycleTest` shows `calls` is always 1 after setup; `PerClassLifecycleTest` shows `visits` going from 1 to 2 under the illustrative order; `PerClassIsolatedTest` shows a fresh `visited` for each test; `SpringContextSharedTest` shows a new test instance still sees singleton state; `SpringIndependentTest` illustrates resetting in `@BeforeEach`.

You can try removing `@TestMethodOrder` on `PerClassLifecycleTest` or running `secondScenario` by itself: expecting "2" immediately becomes unreliable. That is the exact signal to eliminate order dependencies rather than merely adding ordering annotations.

## 5. How does `@TestInstance` affect parameterized and repeated tests?

JUnit Jupiter uses `PER_METHOD` for each execution of a test method, including each invocation of `@ParameterizedTest` or each repetition of `@RepeatedTest`. Therefore, when the same parameterized method runs with multiple inputs, instance fields normally start from their initial values on each invocation. With `PER_CLASS`, all invocations share one instance, so a mutable field can accumulate values.

Additional example for the project above:

```java
package com.example.lifecycle;

import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestInstance(TestInstance.Lifecycle.PER_METHOD)
class ParameterizedLifecycleTest {
    private int seen;

    @ParameterizedTest
    @ValueSource(ints = {1, 2, 3})
    void freshInstanceForEachInvocation(int input) {
        assertEquals(0, seen);
        seen++;
        assertEquals(1, seen);
        assertEquals(1, Integer.signum(input));
    }
}
```

With `@TestInstance(TestInstance.Lifecycle.PER_METHOD)`, the `seen == 0` assertion at the start of the invocation always holds; `input` takes 1, 2, 3, though the test logic does not depend on invocation order. If switched to `PER_CLASS` **without resetting `seen`**, the test above can fail from the second invocation onward because state changed. `@BeforeEach` still runs for each invocation to build separate state when needed.

One advanced exception worth remembering: tests generated with `@TestFactory` (`DynamicTest`) have different lifecycle rules from standard tests; `@BeforeEach` and `@AfterEach` wrap the **factory method**, rather than running automatically for each generated `DynamicTest`. So do not use the mental model "each dynamic test gets its own callback" when designing state resets.

## 6. Distinguishing test instance lifecycle from Spring TestContext cache

These are two mechanisms with different scopes and owners:

| Mechanism | Who manages it? | Unit of reuse | How to actively control it |
| --- | --- | --- | --- |
| `PER_METHOD` / `PER_CLASS` | JUnit Jupiter | **Test class object** | `@TestInstance`, `@BeforeEach`, `@BeforeAll` |
| Spring TestContext cache | Spring Test | **`ApplicationContext` and beans inside it** | Context configuration, `@DirtiesContext`, avoiding shared mutable beans |
| Transactions in integration tests | Spring transaction/test framework or DB | **Data and transactions** | Fixtures, rollback when appropriate, explicit cleanup |
| Static/caches outside Spring | JVM or libraries | **Classloader/process/resource** | Clear/restore or design statelessly |

When two `@SpringBootTest` classes have equivalent context configurations, the Spring TestContext framework can reuse the cached context. Test methods in the same class also typically share that context. `@TestInstance(PER_METHOD)` only affects the test object; **it does not force Spring to create a new context**.

In certain cases where a fresh context is needed because a test modified configuration or beans that cannot be reset, you can use:

```java
@DirtiesContext(classMode = DirtiesContext.ClassMode.AFTER_EACH_TEST_METHOD)
```

(Annotation snippet; import from `org.springframework.test.annotation.DirtiesContext`.) This instructs Spring to evict the context marked dirty from the cache and rebuild it when needed; it can make tests **noticeably slower**, so it is not the default way to achieve isolation. For DB state, `@DirtiesContext` also **does not automatically wipe all data** from an independent database.

Some Spring integration tests use `@Transactional` and roll back the test-managed transaction after the method by default; however, rollback depends on the test transaction actually wrapping the operation. When a test starts a real web server and makes HTTP calls over another thread/transaction, do not assume the server request runs inside the test's transaction and rolls back automatically. You must verify setup, commits, cleanup, and transaction boundaries for that specific scenario.

**Especially with `PER_CLASS` + Spring:** injection into the instance only occurs during that instance's lifecycle. If a test intentionally dirties/replaces the context between methods, bean references stored on the shared instance can become stale depending on injection style and context recreation. Prefer `PER_METHOD` for tests requiring frequent context changes, or design appropriate fixtures and verify dependencies are re-injected accurately.

## 7. How to avoid flaky tests and order-dependent tests?

An independent test must be able to run alone or within the full suite and produce the same outcome given the same input conditions. Practical strategies:

1. **Choose `PER_METHOD` by default** unless there is a solid reason to use `PER_CLASS`. Place varying data in local variables, constructors of the object under test, or `@BeforeEach`.
2. **If choosing `PER_CLASS`, separate shared read-only resources from per-case state.** Build expensive fixtures once in `@BeforeAll`, but reset or recreate mutable collections before each test.
3. **Do not use `@Order` to mask test dependencies.** Ordering makes sense for teaching examples or an intentional state-sequence test, but it does not fix the flaw where the second test only passes when the first runs before it.
4. **Control state outside the test instance.** Do not let static counters, Spring singletons, caches, databases, queues, or temp files leak data to other tests. Choose resets, unique keys/namespaces, verified rollbacks, or independent fixtures as needed.
5. **Clean up resources with clear lifecycles.** `@AfterEach` cleans up resources belonging to one test; `@AfterAll` cleans up shared fixtures. Cleanup should ensure it does not delete another test's data, especially under parallel execution.
6. **Try running each test individually, the whole class, and the full suite.** If outcomes vary depending on which tests run together, check for state leaks before suspecting JUnit is "behaving wrongly".
7. **Enable parallel execution intentionally.** A test that passes sequentially may have a race condition when multiple tests touch the same singleton or static field.

With JUnit Jupiter, parallel execution can be configured using `junit.jupiter.execution.parallel.*` properties. However, `PER_CLASS` and test method ordering have more conservative default concurrency rules; when intentionally using `@Execution(ExecutionMode.CONCURRENT)` or equivalent settings, you must protect mutable shared state with isolation or appropriate synchronization. **An `AtomicInteger` only makes individual increment operations atomic; it does not prevent "reset → increment → assert" sequences of two independent tests from interleaving.**

If you need to test a multi-step stateful workflow, consider placing all ordered steps **inside a single test method** with assertions at each milestone, or using a fresh fixture/object for each scenario. Only split a workflow into multiple dependent `@Test` methods if truly necessary and you accept the limitations on single-test execution, retries, and parallelism.

## 8. Suite-wide default configuration: when needed and risks

JUnit Jupiter supports setting the default lifecycle in `src/test/resources/junit-platform.properties`:

```properties
junit.jupiter.testinstance.lifecycle.default = per_class
```

When this property takes effect, test classes **without `@TestInstance`** receive `PER_CLASS`; classes with an explicit annotation still follow their annotation. You can use `per_method` to choose the corresponding default. A suite-level setting can heavily impact existing tests: instance fields that were previously refreshed will start retaining state across tests, and assumptions about `@BeforeAll` may change.

If you use global configuration, ensure IDEs, command-line/CI, and test runners all load the same configuration. Otherwise, tests passing in one environment and failing in another can stem from **different lifecycle defaults**. In most projects, keep `PER_METHOD` as the default and only annotate `PER_CLASS` on classes that genuinely need shared fixtures, along with an explanation.

## 9. Common errors and how to diagnose them

| Symptom | Likely cause | Investigation/fix |
| --- | --- | --- |
| Test B only passes after test A | B depends on a `PER_CLASS` instance field, singleton, or DB prepared by A | Run B alone; have B build its own fixture; remove order dependency |
| Non-static `@BeforeAll` is rejected | Class still uses `PER_METHOD` | Make callback static, or choose `PER_CLASS` after evaluating shared state |
| Instance field unexpectedly equals 0 in the next test | `PER_METHOD` creates a new instance | Each case must prepare its own data; if sharing fixtures, use an intentional mechanism |
| `@Autowired` singleton retains values from previous test | Spring context/bean is reused | Reset in fixture, design beans statelessly, or isolate context when truly needed |
| Test passes alone but fails in the full suite | Static state, cache, DB, or external resource leaked | Compare before/after state, test data, profiles, and class order |
| Test fails randomly when parallel is enabled | Race condition on mutable shared state or cross-cleanup | Use separate state, synchronization, or resource locks where appropriate |
| Using `@DirtiesContext` makes the suite very slow | Spring has to rebuild the context repeatedly | Prefer proper state cleanup; mark dirty only when necessary |
| Parameterized test with `PER_CLASS` accumulates a counter | All invocations share one instance | Reset in `@BeforeEach` or choose `PER_METHOD` |
| Dynamic tests do not get per-case callbacks | `@TestFactory` has no per-dynamic-test lifecycle callbacks | Create state directly inside each dynamic test's executable |

A helpful diagnostic technique is identifying the **exact kind of object holding stale data**: test instance field, static field, Spring bean, database, or external system. Then choose the appropriate setup/teardown scope, rather than blindly switching `PER_CLASS` to `PER_METHOD` when the actual leak comes from a singleton or DB.

## 10. Self-check exercises

**Scenario A — same instance or not?** A test class has `private int count = 0;`, each test calls `count++`, with no `@BeforeEach` reset. What will two tests see? With `PER_METHOD`, each test starts from 0 and gets 1 after one increment. With `PER_CLASS`, the same instance can keep `count` incrementing across tests; do not assume order unless ordering is configured.

**Scenario B — one singleton, two test instances.** Two `@SpringBootTest` methods receive the same `@Autowired CounterService`. The first test increments `CounterService` to 1; the second test uses `PER_METHOD`. Is the second test guaranteed to see 0? **No**. The JUnit instance lifecycle and the bean lifecycle in the Spring context are two separate mechanisms.

**Scenario C — no sharing wanted, but expensive setup needed.** There is a fixed configuration lookup table used by 30 tests and a `List` recording events mutated by each test. Choose to build the table once (immutable) via `@BeforeAll` under `PER_CLASS` if appropriate, while creating a new `List` in `@BeforeEach`. Do not let events from an earlier test leak into a later test.

**Scenario D — parallel execution.** Two tests both call `counter.reset()`, `counter.increment()`, and assert 1 on the same singleton. Can both FAIL even though `AtomicInteger` is thread-safe? **Yes**: individual operations are atomic, but the full sequence is not atomic; one test can reset while the other has already incremented.

### Checklist before writing or reviewing tests

- Is the test instance default `PER_METHOD` or `PER_CLASS`? Does the choice come from an annotation or `junit-platform.properties`?
- Do `@BeforeAll`, `@BeforeEach`, `@AfterEach`, `@AfterAll` act on the right resource scope?
- Which fields are instance fields, which are static, and which dependencies are cached/reused by Spring?
- Does each test build its own inputs and expected outcome without needing another test to run first?
- When mutable state exists, who resets/cleans it up, and is that reset safe when running the whole suite or in parallel?
- If `@DirtiesContext` is used, are context restart costs and limitations regarding DB/external resources understood?
- Have you tested running individual tests, the entire class, and the whole suite under the same conditions?

**Core takeaway:** `PER_METHOD` refreshes the **test class object** for each execution; `PER_CLASS` keeps **one test class object** and allows instance lifecycle callbacks to share fixtures. Neither option automatically resets all state in Spring Boot or the test environment. Writing reliable tests requires identifying the exact scope of data and cleaning up/initializing at that exact scope.
