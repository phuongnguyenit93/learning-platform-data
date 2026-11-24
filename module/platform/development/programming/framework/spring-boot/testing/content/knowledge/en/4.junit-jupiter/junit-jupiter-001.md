# JUnit Jupiter: @Test, @DisplayName, and Test Class Structure

## 1. Why is it necessary to understand test class structure?

JUnit Jupiter is the programming model and extension API for writing tests on the **JUnit Platform**. In a Spring Boot project, Jupiter is typically provided via `spring-boot-starter-test`. For tests to be valuable, you need to know **how JUnit recognizes test methods, how test names are displayed, when state is initialized, and which assertions evaluate the results**.

This lesson focuses on three topics:

1. `@Test` marks a method as a test; the test body is organized according to *Arrange – Act – Assert*.
2. `@DisplayName` assigns human-readable names to classes and methods in the test result tree.
3. A test class contains test methods, lifecycle methods, state/fixtures, and can be organized into groups using `@Nested`.

This is **JUnit Jupiter** knowledge, applicable to both plain Java and Spring Boot code. A plain Java test does not need `@SpringBootTest` or starting an ApplicationContext.

## 2. @Test: which methods are executed as tests?

Declare with the exact import:

~~~java
import org.junit.jupiter.api.Test;
~~~

Minimal example:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        int actual = 2 + 3;
        assertEquals(5, actual);
    }
}
~~~

JUnit Jupiter discovers `addsTwoNumbers()` because it has `@Test`, invokes the method through the test engine, and records **PASS** when there are no failed assertions or unexpected exceptions. If `assertEquals(5, actual)` receives a value other than 5, Jupiter marks it **FAILED** and provides expected/actual details in the report.

**Rules for Jupiter `@Test` methods:**

- Does not need to be `public`; *package-private* visibility as in the example is commonly recommended. Test classes/methods **must not be `private`**.
- `@Test` methods **must not be `static`** and must have a `void` return type.
- A test can accept parameters **if** Jupiter or a registered extension provides a corresponding `ParameterResolver` (for example, a `TestInfo` parameter). Do not arbitrarily add parameters like a regular Java method.
- `@Test` does not accept JUnit 4-style `expected` or `timeout` attributes; use `assertThrows(...)` or Jupiter's appropriate timeout API.
- Annotating with `@Test` alone is **not enough to guarantee the test checks anything**: an empty method can still PASS. Meaningful assertions or verification of an observable behavior are required.

**Distinguishing imports is very important:**

| Jupiter | Legacy JUnit 4 |
| --- | --- |
| `org.junit.jupiter.api.Test` | `org.junit.Test` |
| `org.junit.jupiter.api.Assertions` | `org.junit.Assert` |
| `org.junit.jupiter.api.BeforeEach` | `org.junit.Before` |
| `org.junit.jupiter.api.BeforeAll` | `org.junit.BeforeClass` |

Do not arbitrarily mix annotations between the two generations. `@RunWith` is JUnit 4's runner mechanism; JUnit Jupiter has its own test engine on the Platform and its own extension API. A mixed project can run JUnit 4 via the Vintage Engine, but that does not make the two sets of annotations equivalent.

## 3. @DisplayName: describing behavior for readers of test results

`@DisplayName("...")` specifies the display name in IDEs, test reports, and supported test runners. It can be placed on a **class** or a **method**:

~~~java
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertTrue;

@DisplayName("Age rule validation")
class AgeRuleTest {

    @Test
    @DisplayName("Person aged 18 or older is accepted")
    void acceptsAdult() {
        int age = 18;
        assertTrue(age >= 18);
    }

    @Test
    @DisplayName("Person under 18 is rejected")
    void rejectsMinor() {
        int age = 17;
        assertTrue(age < 18);
    }
}
~~~

In the result tree, instead of having to interpret the technical name `acceptsAdult()`, readers can see:

~~~text
Age rule validation
  ✓ Person aged 18 or older is accepted
  ✓ Person under 18 is rejected
~~~

The ✓ symbol in the example is an **illustration of a report UI when tests PASS**, not fixed stdout from JUnit or Gradle.

**Naming principles:**

- Use **stable, meaningful Java method names** so they can be found via IDE or build filters: `rejectsMinor`, `calculatesShippingFee`.
- Use **display names that explain business logic and expectations**: "When stock is insufficient, do not create a payment transaction".
- Names can use Unicode characters, spaces, or special characters; they should still be easy to read in CI reports.
- Do not use `@DisplayName` to disguise an ambiguous test. The name must match the assertions; a test named "rejects negative price" must genuinely assert the rejection behavior.

**`@DisplayName` does not rename the class/method in Java, does not add assertions, and does not affect test execution logic.** It only provides presentation metadata. Without `@DisplayName`, Jupiter uses the default name generated by the display-name generator; this can be customized with `@DisplayNameGeneration`, though a name directly assigned via `@DisplayName` takes precedence.

Example with a generator (only apply when bulk name normalization is needed):

~~~java
import org.junit.jupiter.api.DisplayNameGeneration;
import org.junit.jupiter.api.DisplayNameGenerator;
import org.junit.jupiter.api.Test;

@DisplayNameGeneration(DisplayNameGenerator.ReplaceUnderscores.class)
class NamingTest {

    @Test
    void invalid_input_is_rejected() {
        // Illustrates naming mechanism; actual tests must have assertions.
    }
}
~~~

The display name of the method above will be generated as something like "invalid input is rejected"; this is **only a generator syntax example, not a complete business test**.

## 4. Standard structure of a test class

A test class may consist of:

| Component | Function | Timing |
| --- | --- | --- |
| `@BeforeAll` | Prepare shared resources for the class when needed | Before tests in the class |
| `@BeforeEach` | Create/reset fixture for each test | Before each test execution |
| `@Test` | Run an independent scenario and assertions | Each scenario execution |
| `@AfterEach` | Clean up resources/actions after each test | After each test execution |
| `@AfterAll` | Clean up shared resources of the class | After tests in the class |
| `@Nested` | Group tests in an inner class by state/behavior | As a child branch in the test tree |

Example **structural skeleton** to identify component placement (not a standalone business test):

~~~java
import org.junit.jupiter.api.*;

@DisplayName("A feature")
class FeatureTest {

    @BeforeAll
    static void beforeAll() {
        // Shared setup; avoid real connections if unnecessary.
    }

    @BeforeEach
    void setUp() {
        // Prepare fresh data for each test.
    }

    @Test
    @DisplayName("Completes behavior A")
    void behaviorA() {
        // Arrange -> Act -> Assert.
    }

    @AfterEach
    void tearDown() {
        // Clean up per-test resources if any.
    }

    @AfterAll
    static void afterAll() {
        // Release shared resources if any.
    }
}
~~~

Under the default **`PER_METHOD`** lifecycle, JUnit Jupiter creates a new test class instance for each test method. Therefore, state in instance fields is normally not shared across tests. `@BeforeEach` is still useful to make fixture initialization explicit and reusable.

By default, `@BeforeAll` and `@AfterAll` on a regular test class must be `static`; `@BeforeEach` and `@AfterEach` are instance methods. If you deliberately use `@TestInstance(TestInstance.Lifecycle.PER_CLASS)`, Jupiter can invoke non-static `@BeforeAll` and `@AfterAll`, but then instance state can be shared across tests: it must be managed/reset carefully. Do not switch to `PER_CLASS` just to avoid writing a `static` method.

**Do not rely on the order of `@Test` methods.** Execution order should not become a condition for the suite's correctness. If ordering is genuinely required, Jupiter provides `@TestMethodOrder` and `@Order`, though independent tests remain the better choice for standard examples and business logic.

## 5. Complete, runnable example: test structure for a Shopping Cart

Suppose a shopping cart sums amounts in **cents** and rejects non-positive unit prices. Test objectives: a new cart is empty, adding two items increases the total properly, an invalid price throws an error and leaves state unchanged.

Place the file at `src/test/java/example/CartTest.java`, using **Java 17+** and JUnit Jupiter:

~~~java
package example;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertAll;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@DisplayName("Shopping Cart")
class CartTest {

    private Cart cart;

    @BeforeEach
    void setUp() {
        cart = new Cart();
    }

    @Test
    @DisplayName("New cart has 0 items and total price of 0")
    void startsEmpty() {
        assertAll("New cart",
                () -> assertEquals(0, cart.itemCount()),
                () -> assertEquals(0, cart.totalCents()));
    }

    @Nested
    @DisplayName("When adding items")
    class AddingItems {

        @Test
        @DisplayName("Accumulates price and item count accurately")
        void addsValidPrices() {
            cart.add(1_000);
            cart.add(2_500);

            assertAll("After adding",
                    () -> assertEquals(2, cart.itemCount()),
                    () -> assertEquals(3_500, cart.totalCents()));
        }

        @Test
        @DisplayName("Zero price is rejected and cart remains unchanged")
        void rejectsZeroPrice() {
            IllegalArgumentException error = assertThrows(
                    IllegalArgumentException.class,
                    () -> cart.add(0));

            assertEquals("Price must be positive", error.getMessage());
            assertEquals(0, cart.itemCount());
            assertEquals(0, cart.totalCents());
        }

        @Test
        @DisplayName("Negative price is rejected")
        void rejectsNegativePrice() {
            assertThrows(IllegalArgumentException.class,
                    () -> cart.add(-100));
            assertEquals(0, cart.itemCount());
        }
    }

    // Minimal model so the example runs standalone, without Spring or a DB.
    static final class Cart {
        private int count;
        private int total;

        void add(int priceCents) {
            if (priceCents <= 0) {
                throw new IllegalArgumentException("Price must be positive");
            }
            int newTotal = Math.addExact(total, priceCents);
            total = newTotal;
            count++;
        }

        int itemCount() {
            return count;
        }

        int totalCents() {
            return total;
        }
    }
}
~~~

**Detailed explanation of each part:**

1. `@DisplayName("Shopping Cart")` on the class names the root branch in the report.
2. `private Cart cart` is the test class's fixture. `@BeforeEach` creates a new cart each time so that tests do not depend on which test runs first.
3. `startsEmpty()` uses `@Test` and `assertAll(...)` to check both item count and total price simultaneously; having two independent assertions ensures that if one value is wrong, you still get information for the whole assertion group.
4. `@Nested` creates a **non-static inner class** named `AddingItems`, grouping three scenarios in the same context. The inner class can still use the outer class's `cart` field; `@BeforeEach` on the outer class is invoked for tests inside `@Nested` as well.
5. `addsValidPrices()` establishes state via *Act* and then asserts the exact result: 2 items and 3,500 cents.
6. `rejectsZeroPrice()` uses `assertThrows(...)` to verify the error was thrown while also asserting that state did not change.
7. `Cart` is a simple production-like class placed inside the test file **solely to make the example self-contained**. In real projects, import and test the actual `Cart` implementation or corresponding service from `src/main/java`; you should not copy production logic into a test and treat it as proof of the real implementation.

The result tree looks like:

~~~text
Shopping Cart
  New cart has 0 items and total price of 0           PASS
  When adding items
    Accumulates price and item count accurately       PASS
    Zero price is rejected and cart remains unchanged PASS
    Negative price is rejected                        PASS
~~~

The display order here is illustrative, **not an execution order guarantee**. Tests do not need to print to stdout; the primary evidence lies in the assertions and the JUnit Platform report.

### Why is a Spring Boot context not needed?

The example only tests plain Java objects. `@SpringBootTest` would initialize more context than needed and is usually slower. When the goal is to test Spring dependency injection, MVC, transactions, repositories, or security integration, choose the test annotation appropriate for that scope; `@Test` and `@DisplayName` are still used to mark and describe test methods.

## 6. Running tests in a Gradle/Spring Boot project

In a Spring Boot module using Gradle that already has the Spring Boot plugin/BOM, the test configuration typically looks like:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is a **configuration snippet to add to an existing `build.gradle`**, not a complete build file. `spring-boot-starter-test` provides JUnit Jupiter and test support libraries at versions managed by Spring Boot. `useJUnitPlatform()` tells Gradle to run tests via the JUnit Platform, including the Jupiter engine.

Run from the Gradle root appropriate for the configured module:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

**Expectation:** JUnit Platform discovers **4 `@Test` methods** (one in the outer class, three in `@Nested`). All four **PASS** if the code and configuration are correct. With Gradle, a successful task ends with `BUILD SUCCESSFUL` when other build conditions are also met. Line counts, checkmarks, order, and console verbosity depend on the tool/configuration version; do not assume an exact stdout string.

The HTML report generated by Gradle is typically at `build/reports/tests/test/index.html` of the executed module. IDEs like IntelliJ also display the test tree by `@DisplayName`. If you want to run a single class, Gradle's `--tests` filter can select it; for nested classes, pay attention to binary names containing `$` and how the IDE/Gradle filters tests so you do not accidentally omit subgroups.

### What to check when tests are not discovered

1. Is the file in the test source root (usually `src/test/java`), with the right package/directory name and dependencies?
2. Did you import **`org.junit.jupiter.api.Test`** instead of accidentally using `org.junit.Test`?
3. Does the Gradle task have `useJUnitPlatform()` and the right Jupiter engine version?
4. Is the class/method declared `private`, or does the `@Test` method have an invalid signature (e.g., `static` or returning `boolean`)?
5. Is it excluded by `@Disabled`, a `--tests` filter, a tag filter, or IDE configuration?
6. Is there a Java compilation error preventing JUnit from discovering the test?

Do not fix discovery issues by adding `@SpringBootTest`; that annotation is meant for Spring integration testing, not as a substitute for JUnit Platform configuration.

## 7. How to write the body of a quality test

Organize according to **Arrange – Act – Assert**:

~~~java
@Test
@DisplayName("After adding two items, total price is 3,500 cents")
void sumsTwoPrices() {
    // Arrange
    Cart cart = new Cart();

    // Act
    cart.add(1_000);
    cart.add(2_500);

    // Assert
    assertEquals(3_500, cart.totalCents());
}
~~~

This snippet uses `Cart` from the example in section 5: **code illustrating a method, not a standalone file**. In real tests, avoid mixing multiple unrelated scenarios into a single method. Choose assertions that describe the *observable contract* rather than over-testing internal implementation details.

- For results: `assertEquals(expected, actual)`, `assertTrue(condition)`, `assertFalse(condition)`.
- For errors: `assertThrows(ExceptionType.class, executable)`; subtypes of the expected exception are also accepted. If the exact exception type is required, use `assertThrowsExactly` if supported by the Jupiter version.
- For multiple independent assertions: `assertAll(...)` groups assertions for the same behavior.
- For important actions without a direct return value: consider mock/verify in another test; do not overuse interaction testing for things that can be asserted via state.

`@DisplayName` should clearly state the behavior, not simply repeat "test1", "happy path", or the class name. The Java method name should also be meaningful because it helps with grepping, refactoring, and identifying failures in logs.

## 8. How to organize a maintainable test class

**One test class typically corresponds to one subject or one cohesive group of behaviors**, such as `CartTest` testing `Cart`, or `CheckoutServiceTest` testing `CheckoutService`. If the volume grows large, `@Nested` helps group by context:

~~~text
CheckoutServiceTest
  When stock is sufficient
    Creates payment request for correct amount
    Reduces stock after successful payment
  When stock is insufficient
    Rejects order
    Does not send payment request
~~~

However, `@Nested` is not mandatory. With three simple tests that share no common context, a flat class with `@Test` + `@DisplayName` is often easier to read. Avoid deep nesting that makes fixtures and lifecycle hard to follow.

When a `@Nested` group needs additional state setup, you can place a dedicated `@BeforeEach` inside it: Jupiter runs the outer class's setup first and then the inner class's setup. Ensure the setup does not depend on other tests. With Java 17+ and a compatible Jupiter version, some `@BeforeAll` lifecycle rules inside nested classes differ from very old Java versions; in basic tests, prefer `@BeforeEach` and simple fixtures.

Do not use `@TestInstance(PER_CLASS)` or `@TestMethodOrder` as the default solution for sharing state across tests. Doing so can make tests order-dependent and cause single-method runs to fail. If there is a genuinely expensive resource that must be shared, design the fixture with an explicit lifecycle and ensure proper cleanup.

## 9. Common mistakes and how to avoid them

**Adding `@DisplayName` while forgetting `@Test`.** A method with only a display name does not become a test. It must have an appropriate test annotation such as `@Test` or `@ParameterizedTest`; do not arbitrarily put both types on the same scenario.

**Using the wrong import.** `org.junit.Test` is JUnit 4. In a Jupiter project, use `org.junit.jupiter.api.Test` and `org.junit.jupiter.api.DisplayName`.

**Tests without assertions.** A method that just calls a function without checking the outcome can PASS even if business logic is broken. At least one clear observable criterion is needed: return value, state, exception, or required interaction.

**One test depending on another test.** Mutable static fields, shared DB data, and relying on execution order cause flaky results. Create independent fixtures, reset state in `@BeforeEach`, and do not rely on method order.

**Invalid test signatures.** A `static`, `private`, or value-returning `@Test` method violates Jupiter's contract. Use an instance method, non-private, and `void`.

**Using cryptic names.** `test1`, `caseA`, or `shouldWork` make reports far less useful. Combine concise Java names with display names describing "condition → outcome".

**Nesting `@Nested` too deeply.** Many levels make it hard to tell which fixture is created and what state is active. Only group when it genuinely improves context readability.

**Creating a Spring context for simple calculations.** You do not need `@SpringBootTest` just to run `@Test`. Choose unit tests for plain objects; choose Spring slice/integration tests when you want to verify framework wiring and behavior.

**Ignoring differences between JUnit 4 and Jupiter.** Copying JUnit 4's `@Test(expected = ...)` or `@Before` into Jupiter will fail. Use `assertThrows`, `@BeforeEach`, `@BeforeAll`, and Jupiter's extension APIs.

## 10. Checklist before finishing a test class

- [ ] Test class and test methods are in `src/test/java` with proper package and Jupiter imports.
- [ ] Each test has `@Test` (or an appropriate Jupiter test annotation), is neither `private` nor `static`, and returns `void`.
- [ ] `@DisplayName` describes behavior and expectations, consistent with assertions.
- [ ] Each method is independent, with clear fixtures and Arrange – Act – Assert.
- [ ] `@BeforeEach` only prepares state; `@AfterEach` only cleans up when needed.
- [ ] If `@Nested` is used, inner classes are non-static and outer lifecycle inheritance is understood.
- [ ] Test ordering or shared mutable state is not relied upon for correctness.
- [ ] Gradle is configured for JUnit Platform; tests are discovered and report PASS/FAIL as expected.
- [ ] Tests verify the real implementation of the feature under study; do not replace it with a copy in real tests.

**Key takeaways:** `@Test` tells the test engine **which method to run**; `@DisplayName` helps humans understand **what the test proves**; structuring classes with fixtures, lifecycle callbacks, and `@Nested` keeps each scenario **independent, readable, and maintainable**.

### References

- [JUnit 5 User Guide – Writing Tests](https://docs.junit.org/5.10.0/user-guide/index.html#writing-tests): rules for test methods, lifecycle, display names, and nested tests.
- [JUnit 5 User Guide – Display Names](https://docs.junit.org/5.10.0/user-guide/index.html#writing-tests-display-names): `@DisplayName` and display behavior.
- [JUnit 5 User Guide – Test Instance Lifecycle](https://docs.junit.org/5.10.0/user-guide/index.html#writing-tests-test-instance-lifecycle): `PER_METHOD` and `PER_CLASS`.
- [Gradle User Manual – Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform()` configuration and test reports.
