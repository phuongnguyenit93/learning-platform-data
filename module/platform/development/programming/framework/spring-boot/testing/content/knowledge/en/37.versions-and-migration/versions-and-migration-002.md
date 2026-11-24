# JUnit 4, SpringRunner, and Migrating to JUnit Jupiter in Spring Boot

## 1. Why Migrate from JUnit 4 to Jupiter?

In many Spring Boot projects, three test generations coexist simultaneously:

- Legacy tests with `org.junit.Test`, `@Before`, `@Rule`, `@RunWith(SpringRunner.class)`.
- Modern tests with `org.junit.jupiter.api.Test`, `@BeforeEach`, `@ExtendWith`, `@ParameterizedTest`.
- CI using **JUnit Platform** to discover and execute both sets, possibly through the **Vintage engine** during the transition period.

Simply changing the import from `org.junit.Test` to `org.junit.jupiter.api.Test` is **not enough**. JUnit 4 Runners and Rules do not automatically work under Jupiter, lifecycle ordering can differ, Gradle can miss tests if an engine is missing, and Spring context dependency injection needs the proper extension. A pipeline reporting green while silently failing to discover 100 legacy tests is more dangerous than an explicit migration failure.

This lesson targets **Java 17+, Spring Boot 3.5, Spring Framework 6.2, and JUnit Jupiter 5.x**, with an option to temporarily retain JUnit 4.13.2/Vintage during the transition. The Gradle examples pin versions for learning reproducibility, not as a claim that those are the latest releases.

### After This Lesson, You Will Be Able To

1. Distinguish JUnit Platform, Jupiter API/engine, Vintage engine, and JUnit 4 runners.
2. Understand that `SpringRunner` and `SpringExtension` both integrate Spring TestContext but use two different extension models.
3. Migrate `@RunWith(SpringRunner.class)` to Jupiter properly, knowing when `@SpringBootTest` already includes `SpringExtension`.
4. Migrate `@Before/@After/@BeforeClass/@AfterClass` lifecycle methods to Jupiter annotations.
5. Replace `@Test(expected=...)`, `ExpectedException`, and timeouts with `assertThrows`, `@Timeout`, or `assertTimeout`.
6. Replace `TemporaryFolder`, `TestName`, `@Category`, `@Ignore`, and JUnit 4 Rules with Jupiter APIs/extensions.
7. Convert JUnit 4's `Parameterized` runner to `@ParameterizedTest`, `@CsvSource`, or `@MethodSource`.
8. Use `@MockitoBean` in Spring Boot 3.5 and `MockitoExtension` for Mockito unit tests.
9. Use Gradle `useJUnitPlatform()`, controlled Vintage usage, and JUnit test reports to avoid losing test coverage.
10. Preserve Spring TestContext caching, transaction rollback, test slices, and functional assertion semantics.
11. Design a class-by-class migration roadmap without forcing every test to change in a single commit.
12. Identify import errors, test discovery issues, extension ordering, constructor injection, and preemptive timeout pitfalls.

## 2. JUnit Architecture: Platform vs. Jupiter vs. Vintage

~~~text
Gradle Test task
      |
      +-- JUnit Platform Launcher
                 |
                 +-- Jupiter TestEngine
                 |     +-- org.junit.jupiter.api.Test
                 |     +-- @BeforeEach, @ParameterizedTest
                 |     +-- @ExtendWith extensions
                 |
                 +-- Vintage TestEngine (temporary)
                       +-- org.junit.Test (JUnit 4)
                       +-- @RunWith(SpringRunner.class)
                       +-- @Rule / @ClassRule
~~~

- **JUnit Platform** is the launcher/discovery and test execution API layer. Gradle `useJUnitPlatform()` builds on this.
- **JUnit Jupiter** includes the programming model/API and the test engine for modern tests.
- **JUnit Vintage** is the test engine that allows legacy JUnit 3/4 tests to run on the Platform.
- **JUnit 4** is the legacy API set such as `org.junit.Test` and `Runner`; the Jupiter engine **does not** execute methods annotated only with `org.junit.Test`.
- **SpringRunner** is the JUnit 4 runner integrating Spring TestContext.
- **SpringExtension** is the JUnit Jupiter extension integrating the same Spring TestContext, not a renamed JUnit 4 runner.

### 2.1 Same Classpath, Different Semantics

The following two imports are **two distinct annotation types**:

~~~java
import org.junit.Test;              // JUnit 4
import org.junit.jupiter.api.Test;  // JUnit Jupiter
~~~

Do not import both in the same Java source file using the simple name `Test`. Java does not allow two single-type imports with the same simple name; even if you use a fully qualified annotation to avoid the conflict, mixing Jupiter and JUnit 4 annotations/methods in one class is an anti-pattern with unpredictable lifecycle behavior.

### 2.2 Running JUnit 4 Under Platform Does Not Mean You Migrated to Jupiter

If Gradle uses `useJUnitPlatform()` and includes the Vintage engine, a `@RunWith(SpringRunner.class)` class still runs **via the JUnit 4 runner**, only orchestrated/discovered by JUnit Platform. Existing `@Rule` and `@Before` annotations still retain JUnit 4 semantics.

To **truly** migrate a class to Jupiter, you must convert imports, lifecycle, assertions, and rule/runner mechanisms accordingly; only then can you remove Vintage once no JUnit 4 tests remain.

## 3. Annotation Map: JUnit 4 → Jupiter

| JUnit 4 | Jupiter | Notes |
| --- | --- | --- |
| `org.junit.Test` | `org.junit.jupiter.api.Test` | Different package/engine |
| `@Before` | `@BeforeEach` | Runs before each test |
| `@After` | `@AfterEach` | Runs after each test |
| `@BeforeClass` | `@BeforeAll` | Static by default |
| `@AfterClass` | `@AfterAll` | Static by default |
| `@Ignore("reason")` | `@Disabled("reason")` | Or conditional annotations |
| `@Category(Fast.class)` | `@Tag("fast")` | Tags are strings, not Classes |
| `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)` | Spring Boot test annotations usually register the extension already |
| `@RunWith(MockitoJUnitRunner.class)` | `@ExtendWith(MockitoExtension.class)` | For pure Mockito unit tests |
| `@RunWith(Parameterized.class)` | `@ParameterizedTest` | Add data sources |
| `@Test(expected=...)` | `assertThrows(...)` | Wrap the code expected to throw |
| `@Test(timeout=...)` | `@Timeout` / `assertTimeout` | Thread/transaction semantics must be checked |
| `@Rule TemporaryFolder` | `@TempDir` | Parameter/field injection |
| `@Rule ExpectedException` | `assertThrows` / `assertThrowsExactly` | Check exception/message as needed |
| `@Rule TestName` | `TestInfo` injection | Provides method name/display name |
| `@Rule / @ClassRule` | Jupiter extensions / `@RegisterExtension` | No 1-to-1 conversion for every rule |
| `@RunWith(Suite.class)` | JUnit Platform suite / Gradle tags | Requires suite module if using `@Suite` |
| `Assert.assertEquals(message,expected,actual)` | `Assertions.assertEquals(expected,actual,message)` | Message moves to the last parameter |
| `Assume.assumeTrue(...)` | `Assumptions.assumeTrue(...)` | Check message order/exception semantics |

This map is a starting point, **not** an automated refactoring tool that needs no QA. For custom Runners/Rules, examine what they do: resource setup, retries, instrumentation, rule chaining, or assertion interception.

## 4. What Does SpringRunner Do?

JUnit 4:

~~~java
@RunWith(SpringRunner.class)
@SpringBootTest
public class LegacySpringTest {
    @Autowired SomeService service;

    @Before
    public void setup() { /* ... */ }

    @Test
    public void shouldWork() { /* ... */ }
}
~~~

This is a **snippet**; `SomeService` and imports are not defined. `SpringRunner` (an alias for `SpringJUnit4ClassRunner`) binds the JUnit 4 lifecycle to the Spring TestContext Manager. Spring TestContext provides:

- Loading and caching `ApplicationContext` by merged context configuration.
- Dependency injection into the test instance.
- `TestExecutionListener` callbacks.
- Transactional tests and rollback logic when properly configured.
- `@ActiveProfiles`, `@TestPropertySource`, `@DirtiesContext`, `@ContextConfiguration`.

**Changing the Runner does not mean dropping Spring TestContext.** Under Jupiter, `SpringExtension` provides the corresponding integration through the Jupiter extension model.

### 4.1 JUnit 4 Allows Only One @RunWith per Class

A JUnit 4 class cannot simultaneously declare `@RunWith(SpringRunner.class)` and `@RunWith(Parameterized.class)` as two independent runners. Users previously had to write a custom runner, choose one runner, or split the test.

Jupiter uses the extension model and parameterized tests, allowing `@ExtendWith` to compose with `@ParameterizedTest`, though you must still check lifecycle/parameter resolution interactions when multiple extensions are present.

## 5. Spring Boot 3.5: Often No Need to Write @ExtendWith(SpringExtension.class)

According to **Spring Boot 3.5 Testing Spring Boot Applications**, `@SpringBootTest` and test slice annotations such as `@WebMvcTest` and `@DataJpaTest` are already meta-annotated to register `SpringExtension`. Therefore:

~~~java
@SpringBootTest
class ModernSpringBootTest {
    @Autowired SomeService service;

    @Test
    void shouldWork() { /* ... */ }
}
~~~

is **sufficient for Spring integration** when using Jupiter `@Test`. Adding:

~~~java
@ExtendWith(SpringExtension.class)
@SpringBootTest
class RedundantRegistrationExample { /* ... */ }
~~~

is usually unnecessary, although Jupiter handles duplicate extension registrations. These two snippets are illustrative and are not runnable source files because `SomeService` is omitted.

### 5.1 When Is @ExtendWith(SpringExtension.class) Needed?

When you are not using Spring Boot composed test annotations, for example **plain Spring Framework**:

~~~java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class PlainSpringContextTest {
    // Dependency injection + Spring TestContext
}
~~~

Or use the composed annotation `@SpringJUnitConfig(TestConfig.class)` instead of both `@ExtendWith` and `@ContextConfiguration`. This lesson includes a runnable Spring-only test file in the examples section.

### 5.2 @SpringBootTest Still Has Multiple Web Environments

| Boot test mode | Behavior |
| --- | --- |
| `MOCK` (default) | Mock web context, does not start an embedded server |
| `RANDOM_PORT` | Starts an embedded server on a random port |
| `DEFINED_PORT` | Starts the server on the configured/default port |
| `NONE` | Runs a non-web `ApplicationContext` |

Migrating from JUnit runner to Jupiter should **not** silently change `webEnvironment`. If a migration switches from a `MockMvc` test to `RANDOM_PORT`, you have changed the integration model as well as the test framework, making it harder for QA to isolate regression causes.

## 6. Hands-On Project: Same Business Logic, Two Test Generations

The Java 17+/Spring Boot 3.5 Gradle mini-project includes:

- `DiscountService` calculating post-discount amounts; pure Java 17 is enough to run it.
- `PriceController` HTTP endpoint to demonstrate a test slice.
- `LegacyDiscountServiceTest` using JUnit 4 + `SpringRunner`.
- `DiscountServiceJupiterTest` using JUnit Jupiter + `@SpringBootTest` without repeating `SpringExtension`.
- `DiscountParameterizedTest` using `@ParameterizedTest`/`@CsvSource`/`@ValueSource`.
- `DiscountTempDirTest` using `@TempDir` instead of `TemporaryFolder`.
- `DiscountMvcJupiterTest` using `@WebMvcTest`/`@MockitoBean`.
- `SpringExtensionOnlyTest` using plain `@ExtendWith(SpringExtension.class)`/`@ContextConfiguration`.
- `MockitoJupiterTest` demonstrating `MockitoExtension` without a Spring context.

Structure:

~~~text
junit-migration-demo/
  settings.gradle
  build.gradle
  src/main/java/example/migration/
    MigrationDemoApplication.java
    DiscountService.java
    PriceController.java
  src/test/java/example/migration/
    LegacyDiscountServiceTest.java
    DiscountServiceJupiterTest.java
    DiscountParameterizedTest.java
    DiscountTempDirTest.java
    DiscountMvcJupiterTest.java
    SpringExtensionOnlyTest.java
    MockitoJupiterTest.java
  src/test/resources/
    junit-platform.properties
~~~

With the **transition-phase** configuration including Vintage, both JUnit 4 and Jupiter tests will run. Once JUnit 4 classes are removed, delete the Vintage and JUnit 4 dependencies to become **Jupiter-only**.

## 7. settings.gradle and build.gradle for the Transition Phase

`settings.gradle`:

~~~groovy
rootProject.name = 'junit-migration-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // ONLY while JUnit 4 tests still remain:
    testImplementation 'junit:junit:4.13.2'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'

    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }

    reports {
        html.required = true
        junitXml.required = true
    }
}
~~~

- `spring-boot-starter-test` puts JUnit Jupiter, Mockito, AssertJ, and test infrastructure on the classpath.
- `junit:junit:4.13.2` is needed to compile legacy `org.junit.Test`/`@RunWith` code.
- `junit-vintage-engine` allows JUnit Platform to discover/run JUnit 4 classes.
- `junit-platform-launcher` ensures Gradle uses a launcher aligned with the engine dependencies.
- `useJUnitPlatform()` is the crucial step; without it, Jupiter discovery may not behave as expected.
- The JUnit 4/Vintage dependencies above are **intentionally temporary** and are unnecessary once a project is Jupiter-only.

### 7.1 Without Vintage

If you keep `org.junit.Test` while enabling `useJUnitPlatform()` with only the Jupiter engine, Gradle may fail to discover the legacy class. A "BUILD SUCCESSFUL" outcome **does not prove the JUnit 4 tests ran**.

Always compare the test case counts in JUnit XML/Gradle reports rather than relying on a green task status.

### 7.2 JUnit Vintage Must Be Compatible With Platform/Jupiter Versions

Use Spring Boot BOM dependency management instead of mixing arbitrary JUnit major versions. When upgrading Spring Boot to a new major version, check release notes and JUnit Platform compatibility; JUnit 6 has a different structure/versioning than JUnit 5. This lesson deliberately targets **Boot 3.5/Jupiter 5.x** rather than substituting Boot 4/JUnit 6 APIs.

### 7.3 Gradle Wrapper

Create/commit a Gradle wrapper compatible with Java 17/Spring Boot 3.5, then run:

~~~bash
./gradlew clean test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat clean test
~~~

**No actual build/test execution was run in this lesson.** Commands are reproducible instructions; the test counts and expected outcomes below are derived from the code examples, not captured logs.

## 8. MigrationDemoApplication.java

`src/main/java/example/migration/MigrationDemoApplication.java`:

~~~java
package example.migration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class MigrationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(MigrationDemoApplication.class, args);
    }
}
~~~

The root package `example.migration` scans `DiscountService` and `PriceController` in the same package. No database, Docker, or external services required.

## 9. DiscountService.java

`src/main/java/example/migration/DiscountService.java`:

~~~java
package example.migration;

import org.springframework.stereotype.Service;

@Service
public class DiscountService {

    public int afterDiscount(int priceCents, int percent) {
        if (priceCents < 0 || percent < 0 || percent > 100) {
            throw new IllegalArgumentException(
                    "price must be non-negative; "
                    + "percent must be within 0..100");
        }

        long result = (long) priceCents * (100 - percent) / 100;
        return Math.toIntExact(result);
    }
}
~~~

Using `long` allows multiplication without overflowing `int` before dividing. For a price of 10,000 cents and a 15% discount, the result is **8,500 cents**. The example uses integer cents; production pricing may require `BigDecimal`, explicit scale/rounding policies, and currency semantics.

## 10. PriceController.java

`src/main/java/example/migration/PriceController.java`:

~~~java
package example.migration;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/prices")
public class PriceController {

    private final DiscountService discountService;

    public PriceController(DiscountService discountService) {
        this.discountService = discountService;
    }

    @GetMapping("/after-discount")
    public int afterDiscount(
            @RequestParam int cents,
            @RequestParam int percent) {

        return discountService.afterDiscount(cents, percent);
    }
}
~~~

The endpoint for the MVC test uses `GET /api/prices/after-discount?cents=10000&percent=15`. Returning an integer from a `@RestController` via Spring MVC/Jackson typically produces the JSON number body `8500`. This controller only serves to compare JUnit migration inside a slice; it is not a production monetary API.

## 11. LegacyDiscountServiceTest.java — JUnit 4 + SpringRunner

`src/test/java/example/migration/LegacyDiscountServiceTest.java`:

~~~java
package example.migration;

import org.junit.Before;
import org.junit.Test;
import org.junit.runner.RunWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.junit4.SpringRunner;

import static org.junit.Assert.assertEquals;
import static org.junit.Assert.assertNotNull;

@RunWith(SpringRunner.class)
@SpringBootTest(
    classes = MigrationDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
public class LegacyDiscountServiceTest {

    @Autowired
    private DiscountService discountService;

    @Before
    public void verifyWiring() {
        assertNotNull(discountService);
    }

    @Test
    public void calculatesDiscount() {
        assertEquals(8500, discountService.afterDiscount(10000, 15));
    }

    @Test(expected = IllegalArgumentException.class)
    public void rejectsInvalidPercentage() {
        discountService.afterDiscount(10000, 150);
    }
}
~~~

This is a JUnit **4** class, using `public` class/methods per JUnit 4 convention. `@Before` runs before each method, and `@Test(expected=...)` marks the test as PASS when the matching exception type is thrown anywhere inside the method.

**Key takeaway:** this class can still run under Gradle `useJUnitPlatform()` if the **JUnit Vintage engine** is present. Vintage does not transform annotations into Jupiter; `SpringRunner` still manages the `TestContext` under the JUnit 4 lifecycle.

### 11.1 Risk With JUnit 4 Expected Exceptions

`@Test(expected=IllegalArgumentException.class)` treats a matching exception thrown on **any line in the method** as a success, not just the line you intended to test. If setup inside the method accidentally throws that exception, the test becomes a false positive. With Jupiter `assertThrows`, wrapping the exact expected operation is much clearer.

## 12. DiscountServiceJupiterTest.java — The Modern Version

`src/test/java/example/migration/DiscountServiceJupiterTest.java`:

~~~java
package example.migration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = MigrationDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE)
class DiscountServiceJupiterTest {

    @Autowired
    DiscountService discountService;

    @BeforeEach
    void verifyWiring() {
        assertNotNull(discountService);
    }

    @Test
    @DisplayName("15% discount on 10,000 cents leaves 8,500 cents")
    void calculatesDiscount() {
        assertEquals(
                8500, discountService.afterDiscount(10000, 15));
    }

    @Test
    void rejectsInvalidPercentage() {
        IllegalArgumentException error =
                assertThrows(IllegalArgumentException.class,
                        () -> discountService.afterDiscount(10000, 150));

        assertTrue(error.getMessage().contains("0..100"));
    }

    @Test
    void rejectsNegativePrice() {
        assertThrows(IllegalArgumentException.class,
                () -> discountService.afterDiscount(-1, 10));
    }
}
~~~

Key points:

- Import `org.junit.jupiter.api.Test`, not `org.junit.Test`.
- Jupiter classes and methods do not need to be `public`, though they cannot be `private`.
- `@BeforeEach` replaces `@Before`.
- `assertThrows` isolates the exact lambda operation that must throw and lets you inspect its message.
- `@DisplayName` provides a readable report name without changing the Java method name.
- **No need to write `@ExtendWith(SpringExtension.class)`**: Spring Boot 3.5 `@SpringBootTest` already meta-annotates it.

### 12.1 Parity With the Legacy Class

The two core tests from the legacy class have Jupiter equivalents; the Jupiter sample adds a negative-price test to illustrate that migration does not reduce coverage. In real migrations, preserve assertion semantics first and optimize/refactor later, avoiding "changed" tests that make regression comparison difficult.

## 13. Parameterized Tests Replacing the JUnit 4 Parameterized Runner

Traditional JUnit 4:

~~~java
@RunWith(Parameterized.class)
public class LegacyPriceCases {
    // @Parameters returns data; fields/constructor receive arguments
}
~~~

This snippet is not standalone runnable. In Jupiter, a single method can have multiple invocations without needing a class-level runner.

`src/test/java/example/migration/DiscountParameterizedTest.java`:

~~~java
package example.migration;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("unit")
class DiscountParameterizedTest {

    private final DiscountService discountService =
            new DiscountService();

    @ParameterizedTest(name =
            "price={0}, discount={1}% -> result={2}")
    @CsvSource({
        "10000, 15, 8500",
        "5000, 25, 3750",
        "1000, 0, 1000",
        "1000, 100, 0"
    })
    void calculatesCases(
            int price, int percent, int expected) {

        assertEquals(
                expected, discountService.afterDiscount(price, percent));
    }

    @ParameterizedTest
    @ValueSource(ints = {-1, 101})
    void rejectsInvalidPercent(int invalidPercent) {
        assertThrows(IllegalArgumentException.class,
                () -> discountService.afterDiscount(10000, invalidPercent));
    }
}
~~~

The demo includes **two `@ParameterizedTest` methods**, running **4** and **2** invocations respectively, totaling 6 parameterized cases. This is a pure JUnit Jupiter test without booting a Spring context because the business logic needs no dependency injection.

### 13.1 Other Useful Data Sources

- `@ValueSource` for primitives, `String`, `Class`, etc.
- `@NullSource`/`@EmptySource`/`@NullAndEmptySource` for null and empty inputs.
- `@EnumSource` for enum values.
- `@MethodSource` for streams/collections/complex `Arguments`.
- `@CsvFileSource` for CSV-formatted datasets.
- `@ArgumentsSource`/`ArgumentsProvider` for custom generators.

With `@MethodSource`, factory methods are normally `static` under the default `PER_METHOD` lifecycle. With `@TestInstance(PER_CLASS)`, non-static factories can be used. Do not force external CSV files for simple 2–4 row datasets.

### 13.2 Do Not Confuse Method Count With Invocation Count

A JUnit report may display one Java method with multiple test invocations. When comparing test counts between JUnit 4 and Jupiter, count **executed test cases** (including parameterized invocations), not just the number of annotations.

## 14. @Rule TemporaryFolder → @TempDir

JUnit 4:

~~~java
@Rule
public TemporaryFolder folder = new TemporaryFolder();
~~~

Jupiter does not run this JUnit 4 Rule by default. Use the built-in `@TempDir`:

`src/test/java/example/migration/DiscountTempDirTest.java`:

~~~java
package example.migration;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import static org.junit.jupiter.api.Assertions.assertEquals;

class DiscountTempDirTest {

    @Test
    void writesTemporaryReport(@TempDir Path tempDirectory)
            throws Exception {

        Path report = tempDirectory.resolve("discount.txt");
        Files.writeString(
                report, "discount=8500", StandardCharsets.UTF_8);

        assertEquals(
                "discount=8500",
                Files.readString(report, StandardCharsets.UTF_8));
    }
}
~~~

`@TempDir` supports parameter/field injection; Jupiter manages its lifecycle and appropriate cleanup. Do not create files manually under `src/test/resources` or a shared system temp folder when tests need isolation. Each test method uses its own directory; do not hardcode absolute OS paths.

### 14.1 Guidelines for Migrating Other Rules

| JUnit 4 Rule | Typical Jupiter Equivalent |
| --- | --- |
| `TemporaryFolder` | `@TempDir` |
| `ExpectedException` | `assertThrows` / `assertThrowsExactly` |
| `TestName` | `TestInfo` parameter resolver |
| `Timeout` | `@Timeout` or `assertTimeout` |
| `ExternalResource` | `BeforeEach`/`AfterEach`/`BeforeAll`/`AfterAll` callbacks, `AutoCloseable` store |
| `Verifier` | Assertion inside the test or `AfterEachCallback` |
| `RuleChain` | Jupiter extension ordering, explicit composition |
| Custom `@ClassRule` | Class-level extension/`@RegisterExtension` with explicit lifecycle |

There is not always a 1-to-1 conversion. Inspect what resource the old Rule protects and at which lifecycle boundary. A custom Rule that intercepts exceptions, retries, or manages transactions must be rewritten intentionally, not just renamed.

## 15. Mockito: JUnit 4 Runner and Jupiter Extension

JUnit 4 previously used:

~~~java
@RunWith(MockitoJUnitRunner.class)
public class LegacyMockTest {
    @Mock Repository repo;
}
~~~

This is a snippet. Jupiter uses `MockitoExtension` (included in `spring-boot-starter-test`) when a test **does not need a Spring context**:

`src/test/java/example/migration/MockitoJupiterTest.java`:

~~~java
package example.migration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;

import static org.mockito.Mockito.times;
import static org.mockito.Mockito.verify;

@ExtendWith(MockitoExtension.class)
class MockitoJupiterTest {

    @Mock
    Runnable auditCallback;

    @Test
    void verifiesMockInvocation() {
        auditCallback.run();
        verify(auditCallback, times(1)).run();
    }
}
~~~

The example uses `Runnable` as a minimal dependency to illustrate the Mockito lifecycle without an app context. In production, mock real repository/client gateways, verify meaningful interactions, and avoid overmocking.

### 15.1 @Mock vs. @MockitoBean

- `@Mock` is managed by `MockitoExtension` or Mockito initialization on the **test instance**.
- `@MockitoBean` comes from the Spring TestContext bean override mechanism, replacing or adding a **bean in the `ApplicationContext`**.
- Use `@MockitoBean` when a controller/service integration slice needs a mocked Spring bean; do not add `MockitoExtension` to every `@SpringBootTest` out of habit.
- In Spring Boot 3.5/Spring Framework 6.2, Spring Boot's `@MockBean` and `@SpyBean` were **deprecated as of 3.4** in favor of `@MockitoBean` and `@MockitoSpyBean`. When migrating, check imports and reset semantics.

Do not declare a `@Mock` field and expect an `@Autowired` controller inside the Spring context to automatically receive that mock object. The two scopes are different.

## 16. @WebMvcTest + @MockitoBean Illustrating Test Slice Migration

`src/test/java/example/migration/DiscountMvcJupiterTest.java`:

~~~java
package example.migration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(PriceController.class)
class DiscountMvcJupiterTest {

    @Autowired
    MockMvc mockMvc;

    @MockitoBean
    DiscountService discountService;

    @Test
    void endpointReturnsDiscountedPrice() throws Exception {
        when(discountService.afterDiscount(10000, 15))
                .thenReturn(8500);

        mockMvc.perform(get("/api/prices/after-discount")
                        .param("cents", "10000")
                        .param("percent", "15"))
                .andExpect(status().isOk())
                .andExpect(content().string("8500"));
    }
}
~~~

`@WebMvcTest` registers `SpringExtension` via its composed annotation. `@MockitoBean` creates a mock `DiscountService` in the MVC slice so controller constructor injection succeeds. `MockMvc` dispatches a mock request inside the JVM and verifies status/body; it **does not start a real HTTP server**.

For controllers with a Spring Security filter chain, determine whether mock users/CSRF are required; this lesson omits Spring Security. If a legacy JUnit 4 test used `@RunWith(SpringRunner.class)` + `@WebMvcTest`, migration mainly consists of updating imports/lifecycle/test methods, without adding a redundant `@ExtendWith`.

### 16.1 Separate Test Migration From Context Restructuring

Switching from `@SpringBootTest` to `@WebMvcTest` **can make tests faster** but also changes coverage (DB/services/filters). When the goal is "migrate JUnit 4 to Jupiter", keep the existing test slice/configuration first, then optimize layers in a separate PR.

## 17. Plain Spring Framework: Explicit SpringExtension

`src/test/java/example/migration/SpringExtensionOnlyTest.java`:

~~~java
package example.migration;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.test.context.ContextConfiguration;
import org.springframework.test.context.junit.jupiter.SpringExtension;

import static org.junit.jupiter.api.Assertions.assertEquals;

@ExtendWith(SpringExtension.class)
@ContextConfiguration(
    classes = SpringExtensionOnlyTest.DiscountConfig.class)
class SpringExtensionOnlyTest {

    @Autowired
    DiscountService discountService;

    @Test
    void plainSpringContextWiresService() {
        assertEquals(
                3750, discountService.afterDiscount(5000, 25));
    }

    @Configuration(proxyBeanMethods = false)
    static class DiscountConfig {
        @Bean
        DiscountService discountService() {
            return new DiscountService();
        }
    }
}
~~~

This file **does not use `@SpringBootTest`**. `@ExtendWith(SpringExtension.class)` is genuinely required because `@ContextConfiguration` alone does not register the Jupiter extension. It can be shortened to:

~~~java
@SpringJUnitConfig(
    classes = SpringExtensionOnlyTest.DiscountConfig.class)
class AlternativeSpringTest {
    // SpringExtension + ContextConfiguration are composed.
}
~~~

The second snippet is illustrative and is not added as a file in the mini-project. `@SpringJUnitConfig` is a Spring Framework composed annotation; it is useful for plain Spring contexts when full Boot auto-configuration is unnecessary.

## 18. @Before, @After, @BeforeClass, @AfterClass

JUnit 4:

~~~java
@Before public void beforeEachTest() { }
@After public void afterEachTest() { }
@BeforeClass public static void beforeSuiteClass() { }
@AfterClass public static void afterSuiteClass() { }
~~~

Jupiter:

~~~java
@BeforeEach void beforeEachTest() { }
@AfterEach void afterEachTest() { }
@BeforeAll static void beforeAllTestsInClass() { }
@AfterAll static void afterAllTestsInClass() { }
~~~

These two fragments are annotation mappings, not standalone Java source files because they lack a containing class and imports.

### 18.1 Static Lifecycle

- Jupiter `@BeforeAll` and `@AfterAll` must be `static` by default in a top-level class under the default `PER_METHOD` test-instance lifecycle.
- `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` can be used to allow non-static `@BeforeAll/@AfterAll`.
- JUnit 4 `@BeforeClass`/`@AfterClass` are typically `public static`; Jupiter methods can be package-private.
- `@Nested` test classes and test instance lifecycles have their own rules; do not mechanically toggle static/non-static when tests hold state.

### 18.2 PER_METHOD vs. PER_CLASS

By default Jupiter creates a **new test instance per test method** (`PER_METHOD`), reducing shared mutable fields. `PER_CLASS` uses one test instance for the entire class and can cause state leakage if tests mutate fields. This is unrelated to Spring **`ApplicationContext` caching**: even with new test instances, Spring can reuse a cached context.

### 18.3 Do Not Assume Test Method Ordering

Jupiter does not guarantee arbitrary business-logic ordering between methods. If a test relies on method A creating data for method B, that indicates missing isolation. `@TestMethodOrder` is for specific lifecycle cases, whereas normal migrations should keep tests independent.

## 19. Assertions: Message Argument and assertThrows

JUnit 4:

~~~java
assertEquals("bad total", expected, actual);
~~~

Jupiter:

~~~java
assertEquals(expected, actual, "bad total");
assertEquals(expected, actual, () -> "computed message lazily");
~~~

These are snippets requiring `expected`/`actual` and the respective imports. **The failure message moves from first position to last**, so do not run unchecked search-and-replace.

### 19.1 Exceptions

JUnit 4:

~~~java
@Test(expected = IllegalStateException.class)
public void invalidTransitionFails() {
    stateMachine.transition();
}
~~~

Jupiter:

~~~java
@Test
void invalidTransitionFails() {
    IllegalStateException thrown =
            assertThrows(IllegalStateException.class,
                    () -> stateMachine.transition());
    assertEquals("invalid state", thrown.getMessage());
}
~~~

These are **fragments** requiring `stateMachine` and imports. Jupiter `assertThrows` accepts the expected exception type **or a subclass**, whereas `assertThrowsExactly` requires the exact type. Choose based on the business contract.

### 19.2 assertAll and Grouping Assertions

~~~java
assertAll(
    () -> assertEquals(8500, price),
    () -> assertTrue(statusReady)
);
~~~

Illustrative snippet: assertions are evaluated as a group, reporting multiple failures on the same record instead of stopping at the first failure. Do not use it to mask external setup exceptions or make tests order-dependent.

### 19.3 assertIterableEquals, assertArrayEquals, assertInstanceOf

Jupiter provides additional useful assertions, but **you do not have to rewrite every other assertion library**. AssertJ/Hamcrest continue to work normally if compatible; the migration goal is the right engine/lifecycle while preserving semantic coverage.

## 20. Timeout Migration and Spring Transactions

JUnit 4 `@Test(timeout=1000)` does not map simply 1-to-1 to Jupiter in every case. Jupiter offers:

~~~java
@Timeout(value = 1, unit = TimeUnit.SECONDS)
@Test
void shouldFinishQuickly() {
    operation();
}
~~~

And:

~~~java
assertTimeout(
    Duration.ofSeconds(1),
    () -> operation()
);
~~~

These are snippets requiring imports and `operation()`. `assertTimeout` generally runs code on the same thread; it reports failure **after** the operation exceeds the limit without necessarily interrupting it at the deadline.

### 20.1 Beware of assertTimeoutPreemptively

`assertTimeoutPreemptively` runs the executable on a different thread. Spring TestContext transaction state is typically bound to the current thread via `ThreadLocal`. If a test has `@Transactional`, code running on another thread **may not participate in the test-managed transaction**, and data may not roll back as expected.

Therefore:

- For `@Transactional` tests, prefer `assertTimeout` or design a timeout mechanism that does not break the thread-bound context.
- Do not convert JUnit 4 timeouts to `assertTimeoutPreemptively` en masse without checking transaction boundaries.
- In `@SpringBootTest(RANDOM_PORT)`, the HTTP client and server already run on different threads/transactions; test-managed rollback does not cover server transactions.
- For async/reactive code, test proper completion/cancellation semantics rather than just waiting on a sleep.

### 20.2 Timeouts in CI Are Easily Flaky

A hard-coded 10ms timeout for `@SpringBootTest` can fail due to context/JIT/GC/CI load even when functionality is correct. A **method body** limit differs from application context startup time. If performance criteria are used, measure across multiple runs on a controlled runner rather than unit assertions tied to a laptop timing number.

## 21. @Ignore, Conditions, and Environment-Dependent Tests

JUnit 4:

~~~java
@Ignore("temporarily disabled")
@Test
public void legacyCase() { }
~~~

Jupiter:

~~~java
@Disabled("temporarily disabled")
@Test
void modernCase() { }
~~~

Two illustrative snippets. `@Disabled` marks a skipped test with a reason; it does not prove a test PASS. Jupiter conditions:

- `@EnabledOnOs`/`@DisabledOnOs`.
- `@EnabledOnJre`/`@DisabledOnJre`.
- `@EnabledIfEnvironmentVariable`.
- `@EnabledIfSystemProperty`.
- Custom `ExecutionCondition` extension.

If an integration test requires Docker, do **not** silently disable it in a mandatory release gate. Route it to a Docker-capable CI runner or report a clear pipeline blocker.

## 22. @Category to @Tag and Gradle Selection

JUnit 4:

~~~java
@Category(SlowTests.class)
public class LegacySlowTest { }
~~~

Jupiter:

~~~java
@Tag("slow")
class ModernSlowTest { }
~~~

`@Category` uses a marker Java class/interface; Jupiter `@Tag` uses a string (no spaces/commas per JUnit rules). With Gradle:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'unit'
        excludeTags 'slow'
    }
}
~~~

This is a fragment for when you genuinely want to filter tags. If you apply `includeTags 'unit'` to **the entire test task** when only a few Jupiter tests are annotated, all untagged Spring Boot integration tests can be excluded **without any code failure**.

Tagging rollouts must therefore include a checklist comparing discovered/executed/skipped counts and CI policy. Do not add a global filter and declare migration complete based on a passing test task.

### 22.1 Vintage Categories During Migration

JUnit Platform Vintage can expose JUnit 4 categories as tags. However, selecting tags may require the exact name/metadata matching the category class, not necessarily a Jupiter string like `"slow"`. Check the JUnit Vintage documentation and your repo's Gradle report before using a single filter across both test generations.

## 23. @Rule, @ClassRule, and Custom Extension Migration

JUnit 4 Rules wrap a method/class statement:

~~~text
Rule.enter
  @Before
    @Test
  @After
Rule.exit
~~~

Jupiter extensions offer multiple lifecycle interfaces:

| Legacy Rule Need | Appropriate Jupiter Extension API |
| --- | --- |
| Setup before entire class | `BeforeAllCallback` |
| Cleanup at end of class | `AfterAllCallback` |
| Setup before each method | `BeforeEachCallback` |
| Cleanup after each method | `AfterEachCallback` |
| Before/after test body itself | `BeforeTestExecutionCallback`, `AfterTestExecutionCallback` |
| Intercept invocation | `InvocationInterceptor` |
| Resolve constructor/test parameters | `ParameterResolver` |
| Customize exception handling | `TestExecutionExceptionHandler` |
| Conditional skip | `ExecutionCondition` |
| Resource lifecycle per scope | `ExtensionContext.Store` / `CloseableResource` |
| Field-based extension registration | `@RegisterExtension` |

Do not force a custom `Rule` containing retry logic, thread switching, or a JUnit 4 `Statement` wrapper into a single `BeforeEachCallback` without reviewing its behavior. A rule may inspect exceptions or run cleanup in `finally`; the new extension must ensure cleanup still runs even when assertions or fixtures fail.

### 23.1 JUnit 4 Rule Compatibility Support Is Only a Stepping Stone

Some JUnit Jupiter migration support libraries offer limited JUnit 4 Rule compatibility; scope and versions vary. For new code, prefer native Jupiter APIs/extensions. Do not use a "rule adapter" library as an excuse to keep JUnit 4 indefinitely when `@TempDir` or `assertThrows` is simpler.

## 24. @RunWith(Suite.class) and Test Discovery

JUnit 4 `@RunWith(Suite.class)` + `@Suite.SuiteClasses` groups classes into a suite. Jupiter/JUnit Platform provides the `junit-platform-suite` module with `@Suite`, `@SelectClasses`, `@SelectPackages`, and `@IncludeTags` when suite classes are genuinely needed.

Conceptual example:

~~~java
@Suite
@SelectClasses({
    DiscountServiceJupiterTest.class,
    DiscountTempDirTest.class
})
class MigrationSmokeSuite {
}
~~~

This is a snippet; it requires imports from `org.junit.platform.suite.api` and the dependency `org.junit.platform:junit-platform-suite`. **Do not add a Suite class to the mini-project** when the Gradle test task already discovers all test classes. For many teams' CI, Gradle tags/test filters are clearer than a test suite wrapper.

### 24.1 Test Suites Can Cause Double Execution

If JUnit Platform discovers both the original test classes and a suite class that re-selects them, you can accidentally run the same tests twice. Configure test discovery/selectors properly before adding suites to CI.

## 25. @TestInstance(PER_CLASS) and Constructor Injection

Jupiter can inject parameters into test constructors/methods via `ParameterResolver`, where `SpringExtension` supports Spring TestContext dependency injection.

Illustrative example (not added to the demo):

~~~java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@SpringBootTest
class ConstructorInjectionTest {

    final DiscountService service;

    @Autowired
    ConstructorInjectionTest(DiscountService service) {
        this.service = service;
    }

    @BeforeAll
    void warmup() {
        service.afterDiscount(10000, 10);
    }
}
~~~

You can use `@TestConstructor(autowireMode = TestConstructor.AutowireMode.ALL)` or declare `@Autowired` appropriately. Spring Framework docs specify that test constructor auto-wiring does not default to `ALL` unless configured, so do not strip `@Autowired` automatically.

### 25.1 Implications of PER_CLASS

- Non-static `@BeforeAll` is permitted.
- The test instance lives longer, so mutable fields can leak state across methods.
- With `@DirtiesContext` or switching `ApplicationContext` while holding constructor-injected beans, watch for stale bean references.
- Do not force every test to use `PER_CLASS` just to convert `@BeforeClass`.

## 26. @Nested and Spring Context Inheritance

Jupiter `@Nested` helps group scenarios with dedicated setup:

~~~java
@Nested
class WhenDiscountIsZero {
    @Test
    void returnsOriginalPrice() { /* ... */ }
}
~~~

This snippet requires an enclosing test class and imports. With Spring TestContext, `@NestedTestConfiguration` controls how nested tests inherit the enclosing class's Spring test configuration (`INHERIT`/`OVERRIDE` semantics). Do not assume every nested class loads its own context or isolates data automatically.

When migrating a JUnit 4 inner-class runner/custom suite to `@Nested`, evaluate:

1. Nested test instance/lifecycle.
2. Spring TestContext configuration inheritance.
3. Extension registration/inheritance.
4. Fixture and transaction scope.
5. Mockito bean override changes.
6. Cache key and `@DirtiesContext` behavior.

For a small migration unit, keep flat classes first and refactor to `@Nested` after functional parity is confirmed.

## 27. Spring Transaction Rollback When Changing Test Engines

`@Transactional` on a Spring integration test can be managed by Spring TestContext and rolled back after each method, provided the transaction manager and test setup are properly configured.

~~~java
@SpringBootTest
@Transactional
class RepositoryTest {
    @Test
    void insertsAndRollsBack() {
        // Runs repository inside a test-managed transaction.
    }
}
~~~

This snippet lacks a repository and is a pattern rather than a runnable file. `SpringExtension` integrates the transactional `TestExecutionListener` just like `SpringRunner`, but **a test-managed transaction is bound to the thread**.

- Do not use `assertTimeoutPreemptively` in a transactional test without accounting for `ThreadLocal` transactions.
- With `@SpringBootTest(RANDOM_PORT)`, the HTTP server handles requests on a different thread/transaction; test-thread rollback does not roll back server writes.
- With async jobs/schedulers, transaction contexts do not cross threads automatically.
- For database integration tests, inspect actual DB state before and after rather than inferring from the engine migration.

Migrating JUnit 4 → Jupiter is not a license to alter transaction semantics via an annotation without verification.

## 28. Spring Context Cache and Mockito Bean Overrides

The Spring TestContext cache is keyed by metadata: config classes/locations, active profiles, properties, customizers, and bean overrides. Moving from `SpringRunner` to `SpringExtension` **does not inherently force context rebuilds on every test method**, yet if you simultaneously change:

- `@SpringBootTest` to `@WebMvcTest`.
- `@ActiveProfiles("test")` to another profile.
- `@MockBean` to a mock of a different type/name.
- `@TestPropertySource` by adding properties.
- `@DirtiesContext` class/method modes.
- Different `@MockitoBean` fields across tests.

then the number of contexts/cache misses can rise and slow down the suite. Enable `org.springframework.test.context.cache=DEBUG` when comparing before/after. Keep configurations consistent and test isolation safe.

### 28.1 Test Instance Lifecycle Is Not the Context Cache

Jupiter creates a new test instance per method by default, while Spring can reuse the **`ApplicationContext`**. Do not switch to `@TestInstance(PER_CLASS)` thinking it will "cache the Spring context": those are two separate caches/lifecycles.

## 29. JUnit Platform Configuration and Concurrency

Create `src/test/resources/junit-platform.properties`:

~~~properties
# Baseline migration: keep test execution deterministic.
junit.jupiter.execution.parallel.enabled=false
~~~

While a migration still contains custom Rules, Spring transactions, and shared fixtures, start with Jupiter parallelism disabled to surface framework/lifecycle differences first. Do not claim Vintage engine parallelism is wholly controlled by this setting; Vintage has its own version-specific parameters.

If parallelism is needed later:

- Establish database/fixture independence.
- Bound Gradle forks and Spring context counts.
- Never share un-reset static mutable state.
- Review `@ResourceLock`/`@Execution` and thread-bound transaction semantics.
- Measure CPU/RAM/CI flakiness rather than enabling parallel execution unconditionally.

## 30. Running Tests in Phases and Verifying Discovery

With the Gradle wrapper from the project root:

~~~bash
./gradlew clean test
./gradlew test --tests '*LegacyDiscountServiceTest'
./gradlew test --tests '*DiscountServiceJupiterTest'
./gradlew test --tests '*DiscountParameterizedTest'
~~~

The test task is configured with `useJUnitPlatform()`. While Vintage remains, legacy tests are discovered by Vintage and Jupiter tests by the Jupiter engine.

### 30.1 Expected Counts From the Sample

| Test class | Engine | Java test methods | Executed cases |
| --- | --- | ---: | ---: |
| LegacyDiscountServiceTest | Vintage/JUnit 4 | 2 | 2 |
| DiscountServiceJupiterTest | Jupiter | 3 | 3 |
| DiscountParameterizedTest | Jupiter | 2 parameterized methods | 6 |
| DiscountTempDirTest | Jupiter | 1 | 1 |
| DiscountMvcJupiterTest | Jupiter | 1 | 1 |
| SpringExtensionOnlyTest | Jupiter | 1 | 1 |
| MockitoJupiterTest | Jupiter | 1 | 1 |
| **Total** | — | **11 methods** | **15 cases** |

The count of **15 cases** matches the methods/invocations in the demo source. These are **expected results**, not actual Gradle output. If reports show fewer, check engine/tag/test discovery; if they differ because tests were added, update the baseline.

### 30.2 JUnit XML / HTML Reports

The Gradle `Test` task typically writes:

~~~text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
~~~

In CI, preserve artifacts even when tests FAIL so you know:

- How many tests were discovered, executed, skipped, and failed.
- Whether legacy classes actually ran.
- Whether parameterized methods ran all invocations.
- Whether Jupiter/Vintage test counts maintain parity with the baseline.
- Whether classes were excluded by tags or Gradle filters.

Do not look solely at `BUILD SUCCESSFUL`; a migration can accidentally drop all JUnit 4 tests and still complete the task.

## 31. Maven Surefire/Failsafe and IDE Caveats

If a project uses Maven instead of Gradle, it needs Surefire/Failsafe versions supporting JUnit Platform and the appropriate test engines. `spring-boot-starter-test` alone does not guarantee an outdated Maven plugin will run Jupiter properly.

Run both Maven CI and IDE test run configurations; an IDE may use a different JUnit Jupiter runner than CI, and passing in IntelliJ does not guarantee Gradle/Maven CI discovered the legacy tests.

If a repo uses mixed test naming conventions (`*Test`, `*Tests`, `*IT`), inspect Gradle/Maven includes. `InventoryIT` may not be picked up by Maven Surefire if integration naming belongs to Failsafe; do not blame the Jupiter engine when the root cause is test file patterns.

## 32. Temporary Legacy Support and When to Remove Vintage

A safe migration strategy:

~~~text
Phase 0: Inventory
  +-- Count JUnit 4 + Jupiter tests, rules, runners, CI engines
  +-- Record executed test count and test outcomes

Phase 1: Platform
  +-- Run JUnit Platform with Jupiter + Vintage
  +-- Verify BOTH test generations execute

Phase 2: Incremental migration
  +-- Convert test classes one-by-one
  +-- Keep assertions, fixtures, transactions equivalent
  +-- Replace custom Rules/runners carefully

Phase 3: Jupiter-only
  +-- No org.junit.Test / @RunWith / @Rule sources
  +-- Remove junit:junit and junit-vintage-engine dependencies
  +-- Run clean test, inspect reports

Phase 4: Cleanup
  +-- Refactor test slices, parameterization, extension reuse
  +-- Monitor context cache and CI performance
~~~

### 32.1 Do Not Remove Vintage Too Early

If 200 JUnit 4 tests remain, removing Vintage before migrating them all can cause Gradle to stop executing them. Do not use `@Disabled` or test filters to make counts look reasonable. Set a minimum CI gate on executed test counts or a script checking engines/test source imports during migration.

### 32.2 Once All Tests Are Migrated

`build.gradle` simplifies to:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

`junit:junit` and `junit-vintage-engine` are gone. Delete `LegacyDiscountServiceTest.java` or convert it completely to Jupiter, then run a clean Gradle build. `@RunWith(SpringRunner.class)` is no longer needed in Jupiter.

## 33. Common Mistakes

**1. Changing the `Test` import while keeping `@RunWith(SpringRunner.class)`.**  
A JUnit 4 runner does not drive Jupiter `@Test`; migrate lifecycle/extensions or keep the class on JUnit 4 + Vintage.

**2. Calling `useJUnitPlatform` while forgetting Vintage when JUnit 4 tests still exist.**  
The build may go green because legacy tests are not discovered.

**3. Checking only `BUILD SUCCESSFUL` without verifying test counts.**  
Silent loss of coverage.

**4. Adding `@ExtendWith(SpringExtension.class)` to every `@SpringBootTest`/`@WebMvcTest`.**  
Boot 3.5 already registers `SpringExtension`; this is usually redundant.

**5. Switching `SpringRunner` to `MockitoExtension` in a Spring integration test.**  
`MockitoExtension` does not replace Spring TestContext dependency injection or transactions.

**6. Using `@Mock` and expecting a Spring bean to be overridden automatically.**  
Inside a Spring context, you need `@MockitoBean` or an appropriate config/test override mechanism.

**7. Using deprecated `@MockBean` without knowing the `@MockitoBean` path.**  
Check Framework 6.2/Boot 3.5 APIs and imports before refactoring.

**8. Changing `@Before` to `@BeforeAll`.**  
Wrong lifecycle; `@Before` is per-test and must become `@BeforeEach`.

**9. Forgetting `static` on `@BeforeAll` with `PER_METHOD`.**  
Jupiter throws a validation error without an appropriate `PER_CLASS` configuration.

**10. Moving the `assertEquals` message parameter to the wrong position.**  
JUnit 4 puts the message first; Jupiter puts the message last.

**11. Replacing `@Test(expected)` with `assertThrows` around unguarded setup.**  
Can preserve a false positive; wrap only the exact operation under test.

**12. Using `assertTimeoutPreemptively` in a `@Transactional` test.**  
Running on another thread can bypass Spring test transaction rollback.

**13. Assuming `@SpringBootTest(RANDOM_PORT)` rolls back HTTP server writes via test-thread `@Transactional`.**  
The server runs on a different thread/transaction; clean up the DB explicitly.

**14. Copying `@Rule TemporaryFolder` into Jupiter.**  
The JUnit 4 Rule will not run automatically; use `@TempDir`.

**15. Trying to combine JUnit 4 `@RunWith(Suite/Parameterized/SpringRunner)` in one class.**  
One JUnit 4 runner cannot satisfy multiple needs; use Jupiter extensions/parameterization.

**16. Converting `@Category` classes to `@Tag` with the wrong string and filtering out all tests.**  
Tags must be verified; CI may exclude classes unexpectedly.

**17. Enabling JUnit parallelism before cleaning up fixtures.**  
Tests sharing DB/static state can flake.

**18. Using `@TestInstance(PER_CLASS)` just to cache the `ApplicationContext`.**  
Different lifecycle; risks leaking mutable fields.

**19. Switching from full-context to a test slice at the same time as migrating the engine.**  
Impossible to separate regressions caused by the test layer vs. Jupiter.

**20. Combining `MockitoExtension` with a Spring Boot test to fix broken bean injection.**  
Spring bean overrides and Mockito test-instance mocks are different scopes.

**21. Forgetting `testRuntimeOnly` launcher/engine alignment in Gradle.**  
Causes engine/version mismatch or discovery failures.

**22. Maven Surefire plugin is too old.**  
IDE passes while Maven CI fails to run Jupiter properly.

**23. Leaving Vintage engine around indefinitely.**  
Blurs migration ownership and keeps carrying legacy custom Rules.

**24. Mixing JUnit 4 and Jupiter `@Test` in the same source file.**  
Import ambiguity and unclear lifecycle; each class should follow one programming model.

**25. Replacing real test assertions with mocks just to match test counts.**  
Equal counts do not prove equivalent behavioral coverage.

## 34. Migration Process Ready for Real Projects

1. Search for `org.junit.Test`, `org.junit.runner.RunWith`, `org.junit.Rule` imports, and custom runners.
2. Record baseline test executions, skips, failures, and build reports.
3. Update the Gradle/Maven test launcher to support JUnit Platform.
4. Temporarily install Vintage so JUnit 4 tests continue running during the mixed phase.
5. Pick a simple JUnit 4 class to migrate first.
6. Switch to `org.junit.jupiter.api.Test` and `@BeforeEach`/`@AfterEach`.
7. For `@SpringBootTest`/slices, rely on the meta-registered `SpringExtension`; for plain Spring use `@ExtendWith` or `@SpringJUnitConfig`.
8. Convert `@Test(expected)` and `ExpectedException` to `assertThrows`.
9. Convert `TemporaryFolder` to `@TempDir`, and `TestName` to `TestInfo`.
10. Convert the parameterized runner to `@ParameterizedTest` with the right sources.
11. Convert `MockitoJUnitRunner`/Rules to `MockitoExtension` for pure unit tests, or `@MockitoBean` when Spring bean overrides are required.
12. Check constructor injection, test instance lifecycle, `@Nested` config, and transaction boundaries.
13. Preserve profiles, bean mocks, test slices, and `@DirtiesContext` semantics.
14. Run the new class individually and the full suite with both engines, verifying expected coverage.
15. Inspect JUnit XML/HTML reports to catch tests omitted by engines/filters.
16. Migrate classes with custom Rules/Suites after understanding their lifecycles.
17. Remove Vintage/JUnit 4 dependencies only when no legacy test sources remain.
18. Run a clean CI pipeline, verifying executed test counts, behavior, and test isolation.
19. Refactor/speed up tests in a separate step after functional parity.
20. Document team migration guidelines: imports, extension policies, `MockitoBean`, and CI engine conventions.

### Final Checklist

- [ ] Gradle/Maven uses JUnit Platform when running Jupiter.
- [ ] Legacy JUnit 4 tests still run via Vintage during transition.
- [ ] JUnit 4/Jupiter `@Test` imports are not mixed improperly.
- [ ] `@Before`/`@After` are converted to `@BeforeEach`/`@AfterEach`.
- [ ] `@BeforeClass`/`@AfterClass` are converted properly to `@BeforeAll`/`@AfterAll`.
- [ ] `@SpringBootTest`/`@WebMvcTest` preserve `SpringExtension` without redundant repetition.
- [ ] Plain Spring TestContext has `@ExtendWith` or `@SpringJUnitConfig`.
- [ ] `@Test(expected)` is converted to `assertThrows` with the proper lambda.
- [ ] `assertTimeoutPreemptively` does not break transactional rollback.
- [ ] `@Rule`/`TemporaryFolder`/`TestName`/`Category` have corresponding migrations.
- [ ] Pure Mockito unit tests and Spring `@MockitoBean` are kept distinct.
- [ ] Parameterized tests preserve full invocation counts.
- [ ] Spring context/test slices/profiles/fixtures retain original behavior.
- [ ] JUnit XML/Gradle reports confirm all tests executed.
- [ ] No accidental skips due to tags/engines.
- [ ] Vintage is removed only after all JUnit 4 tests are gone.
- [ ] CI runs Java 17+, Boot 3.5, and compatible dependencies.
- [ ] Equal test counts are not treated as a substitute for assertions/behavioral coverage.

## 35. Conclusion

**Migrating from JUnit 4/`SpringRunner` to JUnit Jupiter is a shift in both programming model and extension model**, not just changing an import. On Spring Boot 3.5, `@SpringBootTest` and test slice annotations already support Jupiter's `SpringExtension`, keeping new test code concise. Jupiter replaces JUnit 4 runners/rules with extensions, data-driven tests, assertions, and temp-dir injection.

In a large repository, **JUnit Vintage is a temporary bridge**, allowing Gradle `useJUnitPlatform()` to run both JUnit 4 and Jupiter. However, a green build is only meaningful when you verify test discovery, case counts, fixtures, and business assertions. Migrate class by class, preserve Spring context and transaction semantics, and remove Vintage only after every JUnit 4 test has truly been replaced.

### Official References

- [JUnit 5 User Guide — Migrating from JUnit 4](https://docs.junit.org/5.12.0/user-guide/#migrating-from-junit4): JUnit 4 annotations, rules, runners, Vintage.
- [JUnit 5 User Guide — Extensions](https://docs.junit.org/5.12.0/user-guide/#extensions): callbacks, parameter resolution, and lifecycle.
- [JUnit 5 User Guide — Parameterized Tests](https://docs.junit.org/5.12.0/user-guide/#writing-tests-parameterized-tests): data sources and invocations.
- [JUnit 5 User Guide — Parallel Execution](https://docs.junit.org/5.12.0/user-guide/#writing-tests-parallel-execution): test isolation.
- [Spring Boot 3.5 — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): auto-registered Jupiter `SpringExtension`, test environments.
- [Spring Boot 3.5 — Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/index.html): `starter-test`/JUnit testing guidance.
- [Spring Framework 6.2 — Spring JUnit Jupiter Annotations](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-junit-jupiter.html): `SpringJUnitConfig`, `TestConstructor`.
- [Spring Framework 6.2 — TestContext Jupiter Integration](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/support-classes.html#testcontext-junit-jupiter-extension): `SpringExtension` and dependency injection.
- [Spring Framework 6.2 — Transaction Management in Tests](https://docs.spring.io/spring-framework/reference/6.2/testing/testcontext-framework/tx.html): thread-bound test transactions.
- [Spring Framework 6.2 — MockitoBean](https://docs.spring.io/spring-framework/reference/6.2/testing/annotations/integration-spring/annotation-mockitobean.html): bean override.
- [Gradle — Testing in Java Projects](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform`, reports, filters.
