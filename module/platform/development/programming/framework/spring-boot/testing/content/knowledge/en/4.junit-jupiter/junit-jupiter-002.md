# JUnit Jupiter: @BeforeEach, @AfterEach, @BeforeAll, and @AfterAll

## 1. What are lifecycle callbacks?

In JUnit Jupiter (JUnit 5), **lifecycle callbacks** are methods automatically invoked by JUnit at specific points during the test lifecycle. The four common annotations are:

- `@BeforeEach`: prepare state **before each test execution**.
- `@AfterEach`: clean up or check postconditions **after each test execution**.
- `@BeforeAll`: prepare resources **once before all tests in the class**.
- `@AfterAll`: release resources **once after all tests in the class**.

They help separate **setting up conditions**, **running the behavior under test**, and **cleaning up**. As a result, tests are shorter, less coupled, and easier to reproduce.

For example: each test needs a fresh empty shopping cart, while all tests in the class share a read-only configuration. You can initialize the configuration once in `@BeforeAll`, create a new cart in `@BeforeEach`, clean up the cart in `@AfterEach`, and close the resource created in `@BeforeAll` using `@AfterAll`.

**Distinction:** these annotations are orchestrated by **JUnit Jupiter**. They are not Spring Boot annotations, even though they commonly appear in Spring Boot projects using `spring-boot-starter-test`.

## 2. Comparing the four annotations

| Annotation | When does JUnit invoke it? | Count for N test invocations | What is it used for? | `static` by default? |
| --- | --- | --- | --- | --- |
| `@BeforeAll` | Before executing tests in that class/container | Usually 1 | Open shared resources, prepare shared fixtures | **Yes** for classes using the default `PER_METHOD` lifecycle |
| `@BeforeEach` | Before each test invocation | N | Initialize independent data and state for each test | **No** |
| `@AfterEach` | After each test invocation | N | Clean up per-test resources, reset what is necessary | **No** |
| `@AfterAll` | After tests in that class/container | Usually 1 | Close shared resources created at the start | **Yes** for classes using the default `PER_METHOD` lifecycle |

"N test invocations" means N **invocations**, not necessarily N methods. A `@ParameterizedTest` with three datasets typically creates three invocations and runs `@BeforeEach`/`@AfterEach` three times. `@RepeatedTest` also runs callbacks around each repetition.

`@BeforeAll` and `@AfterAll` are tied to the **corresponding class or test container**; they should not be misunderstood as "once for the entire project" or "once across all classes in the test suite".

### Typical invocation cycle

Suppose a class has two independent tests A and B; the order A/B in the diagram is only an example:

~~~text
@BeforeAll
  @BeforeEach
    @Test A
  @AfterEach
  @BeforeEach
    @Test B
  @AfterEach
@AfterAll
~~~

If JUnit runs B before A, the wrapping structure around each test remains the same. **Do not rely on the default order of test methods.** JUnit has its own mechanisms for determining order, but a proper test must be able to run independently without requiring another test to run first.

In practice, JUnit/Spring extensions also have callbacks at corresponding stages. The diagram above only illustrates the four requested annotations, not all internal events of the test engine.

## 3. @BeforeEach: creating clean state for each test

A method annotated with `@BeforeEach` runs before **each test invocation**, making it suitable for:

- Creating service objects or dummy data for a single test.
- Creating fixtures: an empty cart, sample account, request object, or default mocks.
- Resetting mutable state to a deterministic starting point.
- Preparing common preconditions used by multiple tests.

Example:

~~~java
private List<String> cart;

@BeforeEach
void setUp() {
    cart = new ArrayList<>();
}
~~~

This is an **illustrative code snippet placed inside a test class**, requiring imports for `List`, `ArrayList`, and `BeforeEach`. Each time a test runs, `cart` is assigned a new empty list. Even though JUnit creates a new test class instance per test by default, `@BeforeEach` remains useful to express fixtures clearly and apply them consistently when the test instance lifecycle changes.

**You should not** turn `@BeforeEach` into a long procedure that always creates a database, starts a server, or loads heavy data if most tests do not need it. Overly large fixtures slow down tests and obscure the important preconditions of individual cases.

## 4. @AfterEach: cleaning up after each test

An `@AfterEach` method runs after each invocation to clean up resources belonging to that individual test or complete related checks. Example:

~~~java
private AutoCloseable temporaryClient;

@AfterEach
void tearDown() throws Exception {
    if (temporaryClient != null) {
        temporaryClient.close();
    }
}
~~~

This is an **illustrative snippet**, assuming `temporaryClient` was initialized in Arrange/`@BeforeEach` or inside the test. The null check prevents errors when initialization did not complete.

During normal test failures such as failed assertions, JUnit still executes teardown callbacks, so `@AfterEach` is the proper place for cleanup. However, there is no guarantee that teardown will run if the JVM is forcibly terminated, the process is killed, or the infrastructure suffers a critical failure.

**Note:** avoid deleting shared data or closing resources used by other tests. If you use `@TempDir` or an automatically managed resource, you do not need to write equivalent manual cleanup; if you use `try-with-resources` for a resource needed only within a single method, you can close it directly inside the test.

## 5. @BeforeAll and @AfterAll: preparing and closing shared resources

These two annotations are for **test-class-level** work:

- `@BeforeAll`: initialize an expensive resource or shared configuration once.
- `@AfterAll`: close the exact resource initialized at the class scope.

Under the default `TestInstance.Lifecycle.PER_METHOD` lifecycle, `@BeforeAll` and `@AfterAll` methods in a standard test class must be declared `static`, because each test can use a different instance.

~~~java
private static SomeResource sharedResource;

@BeforeAll
static void startResource() {
    sharedResource = new SomeResource();
}

@AfterAll
static void stopResource() {
    if (sharedResource != null) {
        sharedResource.close();
    }
}
~~~

The snippet above **illustrates syntax**; `SomeResource` is a placeholder name, not a built-in Java/JUnit class; do not copy this block alone to compile. The **complete, runnable** example in the next section uses only real Java and JUnit APIs.

Shared resources must be designed safely: tests should not mutate shared state in a way that makes results depend on execution order or parallel execution. If a list, object, or mock is only for individual tests, prefer `@BeforeEach` instead of sharing via `static`.

With Spring Boot, **Spring TestContext** manages the lifecycle and caches the `ApplicationContext` according to test configuration. JUnit's `@BeforeAll` does not mean "the Spring context is created here", and `@AfterAll` is not the place to manually close a Spring-managed `ApplicationContext`.

## 6. Complete example in Java 17 and JUnit Jupiter

The following example includes all **four annotations**, one `@Test` method, and easily verifiable output. The test checks adding two numbers after setting up data. This is a **plain Java unit test using JUnit 5**, without needing to start a Spring Boot ApplicationContext.

**File `src/test/java/com/example/testing/LifecycleHooksTest.java`:**

~~~java
package com.example.testing;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class LifecycleHooksTest {
    private static String sharedMode;
    private List<Integer> numbers;

    @BeforeAll
    static void beforeAll() {
        sharedMode = "ready";
        System.out.println("1 beforeAll");
    }

    @BeforeEach
    void beforeEach() {
        numbers = new ArrayList<>();
        numbers.add(1);
        System.out.println("2 beforeEach");
    }

    @Test
    void sum_whenAddingTwo_returnsThree() {
        assertEquals("ready", sharedMode);

        numbers.add(2);
        int sum = numbers.stream().mapToInt(Integer::intValue).sum();

        assertEquals(3, sum);
        System.out.println("3 test");
    }

    @AfterEach
    void afterEach() {
        numbers.clear();
        System.out.println("4 afterEach");
    }

    @AfterAll
    static void afterAll() {
        sharedMode = null;
        System.out.println("5 afterAll");
    }
}
~~~

### Configuration and how to run

In a Gradle project using Spring Boot and JUnit Jupiter, you need `spring-boot-starter-test` (which includes JUnit Jupiter in common Spring Boot 3.x versions) and tests configured to run on the JUnit Platform. Example of the relevant configuration section in `build.gradle` (Groovy DSL):

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
    testLogging {
        showStandardStreams = true
    }
}
~~~

This example assumes the project **already has the Spring Boot Gradle plugin, repositories, and a Java 17+ toolchain/JDK**; the block above is not a full build file. If the project already has the corresponding sections, do not add duplicates.

From the project directory with Gradle Wrapper:

~~~bash
./gradlew test --tests "com.example.testing.LifecycleHooksTest"
~~~

On Windows, use `gradlew.bat test --tests "com.example.testing.LifecycleHooksTest"`.

If the test succeeds, the **five lines emitted by `System.out.println` in the example** have the exact order:

~~~text
1 beforeAll
2 beforeEach
3 test
4 afterEach
5 afterAll
~~~

Gradle may add test names, task headers, and build info around these lines; configuring `showStandardStreams = true` helps observe test stdout. This is output printed by the program, **not Gradle's fixed full stdout**.

### Step-by-step explanation

1. JUnit calls `beforeAll()` **once** to set `sharedMode = "ready"`.
2. Before the test, `beforeEach()` creates a new `ArrayList` with element `1`.
3. `sum_whenAddingTwo_returnsThree()` checks the configuration, adds `2`, computes the sum `3`, and asserts with `assertEquals`.
4. After the test, `afterEach()` clears the list in use.
5. After all tests in the class complete, `afterAll()` clears the shared state.

Here there is only one `@Test`, so there is no risk of confusing execution order across multiple tests. If you add another `@Test` to the same class, JUnit will run `@BeforeEach` and `@AfterEach` once more for the new test, while `@BeforeAll` and `@AfterAll` remain scoped to the class.

**Distinguishing responsibilities:** PASS status is determined by `assertEquals`. The five log lines only help observe the lifecycle; you should not use "log presence" as evidence in place of business assertions.

## 7. Why do @BeforeAll/@AfterAll usually have to be static?

JUnit Jupiter defaults to `@TestInstance(TestInstance.Lifecycle.PER_METHOD)`: each regular test method receives a **new instance** of the test class. Because there is no single instance representing the entire class, `@BeforeAll` and `@AfterAll` on a regular test class must be `static` methods by default.

You can switch the class lifecycle to **`PER_CLASS`**:

~~~java
package com.example.testing;

import java.util.ArrayList;
import java.util.List;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;

import static org.junit.jupiter.api.Assertions.assertEquals;

@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class PerClassLifecycleTest {
    private List<String> sharedLabels;

    @BeforeAll
    void beforeAll() {
        // Valid without static thanks to PER_CLASS.
        sharedLabels = new ArrayList<>();
        sharedLabels.add("default");
    }

    @BeforeEach
    void beforeEach() {
        // Reset mutable data before each test.
        sharedLabels.clear();
        sharedLabels.add("default");
    }

    @Test
    void labels_whenPrepared_containsOnlyDefault() {
        assertEquals(List.of("default"), sharedLabels);
        sharedLabels.add("changed");
    }

    @AfterAll
    void afterAll() {
        sharedLabels.clear();
    }
}
~~~

This is a **standalone Java test class file**, which can also run with JUnit 5 when placed in the right package/source set with dependencies. With `PER_CLASS`, all tests in the class share the **same instance**, so instance fields can retain state from a previous test. The example intentionally resets `sharedLabels` in `@BeforeEach` to avoid state leakage.

Choose `PER_CLASS` only when genuinely needed (such as using instance lifecycle methods, test interfaces, or suitable fixtures). Switching lifecycles just to drop the `static` keyword can make tests harder to isolate, especially if the project enables parallel test execution.

**Rule:** with standard `PER_METHOD`, `@BeforeAll`/`@AfterAll` are `static`; `@BeforeEach`/`@AfterEach` are instance methods. With `PER_CLASS`, the two class-level hooks can be instance methods. JUnit also supports other extensions like test interfaces and extensions, but test instance configuration is the first thing to understand.

## 8. What happens when there are multiple tests or multiple hooks?

### Multiple @Test methods

With three standard test methods, each executing once, the test class typically has:

- 1 run of `@BeforeAll`.
- 3 runs of `@BeforeEach`, each tied to one test.
- 3 runs of `@AfterEach`.
- 1 run of `@AfterAll`.

If tests run in parallel, you cannot use "test A already ran" as a precondition for test B. Each fixture must be independent, or shared data must have safe synchronization.

### Parameterized and repeated tests

A `@ParameterizedTest` with four datasets is four **test invocations**: `@BeforeEach` and `@AfterEach` run for each invocation. `@RepeatedTest(3)` is likewise wrapped per repetition. That is why the name "Each" is more accurate than thinking of it as "before each method declared in the file".

One exception to distinguish: with `@TestFactory` generating **dynamic tests**, JUnit runs `@BeforeEach`/`@AfterEach` around the **factory method**, rather than automatically wrapping each individual child dynamic test. If each dynamic test needs its own setup/cleanup, design the corresponding logic yourself or use parameterized tests when appropriate.

### Inheritance and @Nested

With test class inheritance, valid lifecycle methods in the superclass can be inherited. Regarding typical order: setup runs from **superclass before subclass**, teardown runs from **subclass before superclass**. With `@Nested` test classes, outer and inner hooks are also coordinated according to nesting levels.

If you declare **multiple methods with the same annotation in the same class**, JUnit uses deterministic ordering rules, but you should not rely on the order visible in source code. `@AfterEach` methods are also not necessarily paired 1-to-1 in reverse with `@BeforeEach` methods. A maintainable practice is **one hook per callback type per class**, calling helper methods in your explicit desired order.

Do not use `@TestMethodOrder` or `@Order` on tests to work around missing data isolation; test ordering and lifecycle setup are two separate concerns.

## 9. Combining lifecycle callbacks with Spring Boot Test

When using `@SpringBootTest`, `@WebMvcTest`, `@DataJpaTest`, or other test slices, JUnit Jupiter still invokes the hooks as described above, while the **Spring TestContext Framework** handles creating/injecting beans and managing the context according to the test type's configuration.

| Need in Spring Boot | Usually suitable choice | Reason |
| --- | --- | --- |
| Each test needs a fresh request DTO or input data | `@BeforeEach` | Each case has its own input state |
| Each test needs to stub dependencies for its scenario | `@BeforeEach` or the Arrange section in the test | Mock dependencies reflect the specific case |
| Share constant configuration / read-only fixture | `@BeforeAll` if it needs to be created once | Avoid unnecessary repeated setup |
| Close files/clients/servers **self-created** for the whole class | `@AfterAll` | Clean up resources owned by the class |
| Clean up files/clients **created per test** | `@AfterEach` or managed resources | Avoid affecting other tests |
| Database testing with Spring transactions | According to the test's transaction/rollback mechanism, plus appropriate fixtures | Avoid manual deletion when the framework mechanism already handles it |

Do not assume an `@Autowired` bean can be accessed via an **instance field** inside a `static @BeforeAll` method. If setup requires a bean, consider `@BeforeEach` after the test instance is prepared, or extension-supported parameter injection, instead of manually creating a second Spring context.

For example: in `@WebMvcTest`, `@BeforeEach` can prepare inputs and stub mocked services; then `MockMvc` executes the request and assertions check the HTTP status/body. Do not place the logic that "calls the endpoint under test" inside `@BeforeEach`, because then every test executes the same action regardless of what the test name implies.

With `@DataJpaTest` and tests using Spring TestContext-managed transactions, the default rollback mechanism in those cases helps isolate the database. However, that rollback **does not automatically clean up** files, external resources, messages sent to other systems, or changes made outside the transaction; choose cleanup based on the resources actually owned.

Some Spring Boot tests use Testcontainers or slow-running test services. Whether the container is managed per class or by the framework (e.g., Testcontainers lifecycle support) must be clear; do not stop a container shared by other classes or managed by the framework.

## 10. When a test fails, do hooks still run?

With a normal **assertion failure** or exception in a test method, JUnit still proceeds with post-test cleanup callbacks, because `@AfterEach` is not limited to the happy path. Placing state cleanup there is therefore safer than putting cleanup statements on the last line of the test body: if an assertion throws earlier, direct cleanup will be skipped.

However, in certain cases you should not claim cleanup always runs:

- The JVM/process is terminated unexpectedly.
- The system crashes before JUnit executes the callback.
- The lifecycle method itself fails; in that case the test may also fail, and error handling follows the JUnit engine.
- A `@Disabled` test may have no invocation to run `@BeforeEach`/`@AfterEach`.

When `@BeforeEach` fails, the test body may not execute; JUnit still finishes the invocation and runs appropriate cleanup callbacks, so `@AfterEach` must be safe even when the fixture was only **partially** created (e.g., check for null).

Do not use `@AfterAll` to "rescue" a failed test result or alter assertions. Teardown's purpose is to preserve the environment and release resources, not to turn a red test green.

## 11. Common mistakes and how to fix them

1. **Confusing `@BeforeAll` with `@BeforeEach`:** wanting a fresh cart for each test but creating it only once. **Fix:** create mutable data in `@BeforeEach` so each case is independent.
2. **Forgetting `static` on `@BeforeAll` or `@AfterAll` under `PER_METHOD`:** JUnit reports an invalid lifecycle method error. **Fix:** add `static` or intentionally declare `@TestInstance(PER_CLASS)`.
3. **Sharing mutable objects across tests:** one test mutates data and another fails depending on run order. **Fix:** use separate fixtures, reset thoroughly, or choose immutable state.
4. **Very heavy setup in `@BeforeEach`:** databases/containers are initialized repeatedly, making the test suite slow. **Fix:** evaluate which resources can be safely shared or managed by the framework; keep per-test data lightweight.
5. **Cleanup only at the end of `@Test`:** early assertion failures skip cleanup. **Fix:** use `@AfterEach` or `try-with-resources` according to scope.
6. **Manually closing the Spring ApplicationContext in `@AfterAll`:** breaks context caching/lifecycle managed by Spring TestContext. **Fix:** only close resources that the test itself created and owns.
7. **Depending on test execution order:** test B needs state created by test A. **Fix:** Arrange for B must be self-sufficient; do not use ordering to share state.
8. **Having multiple lifecycle methods of the same kind and assuming file-order execution:** leads to unpredictable setup/teardown. **Fix:** use one callback method and call helpers in an explicit order.
9. **Deleting or rolling back the wrong scope:** one test's cleanup wipes shared fixtures or data needed by other tests. **Fix:** distinguish per-test, per-class, and framework-managed resources.

## 12. Choosing the right hook: a short workflow

Before writing a lifecycle method, answer three questions:

1. **How many tests does the resource serve?** If only a single test invocation, prefer `@BeforeEach`/`@AfterEach` or direct setup in the test. If the whole class, consider `@BeforeAll`/`@AfterAll`.
2. **Is the resource mutable?** If yes, use independent data per test or reset it explicitly; avoid shared static mutable state.
3. **Who owns closing/cleaning it up?** If Spring, JUnit, `@TempDir`, or a lifecycle-managing library is already responsible, do not clean it up redundantly; if the test opens its own files/sockets/clients, ensure proper teardown.

Checklist before finalizing a test class:

- [ ] Each test has a clear initial state and runs independently.
- [ ] `@BeforeEach` creates/resets the fixtures needed for **each invocation**.
- [ ] `@AfterEach` is safe even when a test fails or setup is incomplete.
- [ ] `@BeforeAll`/`@AfterAll` only handle work genuinely shared at the class level.
- [ ] Class-level methods satisfy `static` or `PER_CLASS` requirements.
- [ ] No mutable state is kept that causes order/parallel test dependencies.
- [ ] Resources managed by Spring/JUnit or other classes are not closed.
- [ ] Assertions live in the test and measure the right business outcome; lifecycle hooks do not replace verification.

**Remember:** `@BeforeAll`/**once before the class**, `@BeforeEach`/**before each invocation**, `@AfterEach`/**after each invocation**, `@AfterAll`/**once after the class**. Choose callbacks according to **the lifetime scope of data and resources**, while keeping each test independent, repeatable, and reliable.
