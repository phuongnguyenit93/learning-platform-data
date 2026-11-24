# JUnit Platform, Jupiter, and Vintage in Test Discovery

## 1. Why distinguish these three components?

In a Spring Boot project, writing a method whose name starts with `test` or attaching a `Test` annotation does not guarantee that the method will run. The test runner must **discover** the method, recognize which JUnit ecosystem it belongs to, and find an engine capable of executing it.

In the JUnit 5 generation commonly used with Spring Boot 3.3.x, distinguish:

| Component | Primary role | Defines test annotations itself? | Responsible for which tests? |
|---|---|---|---|
| **JUnit Platform** | Foundation for build tools/IDEs to discover, filter, plan, execute, and collect results from test engines | No; provides launcher, engine, selector, and listener APIs | Coordinates multiple engines |
| **JUnit Jupiter** | Programming model and engine for JUnit 5-style tests | Yes: `org.junit.jupiter.api.Test`, `BeforeEach`, `ParameterizedTest`, `Nested`… | Tests written with the Jupiter API |
| **JUnit Vintage** | Compatibility engine for running JUnit 3/4 tests on JUnit Platform | Does not introduce a new test style; uses existing JUnit 3/4 APIs | JUnit 3 (`TestCase`) and JUnit 4 (`org.junit.Test`, runners…) tests |

Key point: **JUnit Platform does not natively understand every `Test` annotation.** It locates implementations of the `TestEngine` interface and delegates discovery and execution. Jupiter and Vintage are two separate engines. A project with the JUnit 4 library on the classpath but lacking the Vintage engine will not automatically turn JUnit 4 tests into Jupiter tests.

In JUnit 5, engines typically have these IDs:
- **junit-jupiter:** Jupiter engine.
- **junit-vintage:** Vintage engine.

The name "JUnit 5" is often used for the whole ecosystem of Platform + Jupiter and Vintage compatibility. This article describes the JUnit 5 architecture matching the Spring Boot 3.3.x/Java 17 example; do not assume all future Spring Boot or JUnit versions share the same default dependency list.

## 2. From a test command to the list of discovered tests

Typical flow:

~~~text
IDE / Gradle Test task / Maven Surefire
                 |
                 | creates discovery request and configures launcher
                 v
         JUnit Platform Launcher
                 |
                 | selectors: class, package, method, classpath roots...
                 | filters: engine, tag, package, class name...
                 v
          Available TestEngines
            /              \
           v                v
  Jupiter TestEngine   Vintage TestEngine
  @Jupiter Test        JUnit 3/4 Test
           \                /
            v              v
      TestDescriptor / TestPlan Tree
                 |
                 | execute(request)
                 v
      TestExecutionListener / reports
~~~

There are two distinct phases:

**Discovery:** The Launcher receives a `LauncherDiscoveryRequest`, finds registered `TestEngine`s, and asks each engine to identify tests matching the selectors/filters. The result is a tree: engine → container (usually class/nested class) → test. You can call `launcher.discover(request)` to inspect the plan **without running test method bodies**.

**Execution:** The Launcher delegates execution to the engines per the request; engines handle lifecycle, assertions, exceptions, and report results through listeners. Gradle/Maven/IDE reports are built from test execution events, not simply from counting Java files named `*Test`.

At the API level, a `TestEngine` receives an `EngineDiscoveryRequest` to build a `TestDescriptor` tree, then executes nodes via an `ExecutionRequest`. In typical applications, you do not write an engine yourself; Gradle/Maven/IDE and JUnit Platform handle the orchestration layer.

**Distinguish three filtering layers:**

1. **Test sources:** The build tool compiles and provides classpath/test classes from source sets or test directories. Files that are not compiled, are excluded, or are absent from the test runtime classpath cannot be run by the Platform.
2. **Discovery selectors:** Specify where to search, such as a class, package, method, or classpath roots. A selector does not guarantee that location actually contains tests.
3. **Discovery filters:** Narrow results by engine ID, tag, class/package, name… Gradle-specific filters (such as `--tests`) or Maven filters can further restrict the execution set.

Then the **engine** decides whether a class/method is a test format it supports. Being on the classpath does not mean being discovered.

## 3. What does Jupiter discover?

Jupiter recognizes annotations in the **`org.junit.jupiter`** namespace such as `Test`, `RepeatedTest`, `ParameterizedTest`, `TestFactory`, and `TestTemplate`, and handles `Nested` structures and Jupiter extensions.

Minimal example:

~~~java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class SumJupiterTest {
    @Test
    void sumsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
~~~

Here the import is **`org.junit.jupiter.api.Test`**, and both class and method may be package-private; the Jupiter engine identifies tests by annotation rather than requiring method names like `testSomething`.

Several important details when reading a discovery tree:

- **`@Nested`** creates nested container relationships to organize sub-tests; in Jupiter, nested test classes are typically non-static inner classes.
- **`@ParameterizedTest`** is discovered as a test template; each invocation is processed during execution. Do not assume one annotation equals one final test case.
- **`@TestFactory`** describes a factory that produces dynamic tests; dynamic tests can be registered **during execution**, so the test count in `TestPlan` at discovery time may differ from the number of completed tests.
- **`@Disabled`** does not mean "not discovered": the test can still appear in the plan and be reported as skipped during execution.
- Jupiter supports lifecycle callbacks, extensions, enable/disable conditions, and test ordering; none of those mechanisms turn a JUnit 4 class into a Jupiter test.

In Spring Boot, `spring-boot-starter-test` normally supplies Jupiter alongside Mockito, AssertJ, Spring Test, MockMvc support (when a web stack is present), and testing utilities. Having the **Jupiter API** dependency to compile annotations is not enough if the **Jupiter engine** is absent from the runtime classpath.

## 4. What does Vintage discover?

The Vintage engine brings execution of legacy conventions onto JUnit Platform:

- **JUnit 4:** methods annotated with `org.junit.Test`; runners via `@RunWith`, JUnit 4 Rules, `Before`/`After`, and compatible features.
- **JUnit 3:** classes extending `junit.framework.TestCase` and `test*` methods following JUnit 3 conventions.

JUnit 4 example:

~~~java
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class SumLegacyTest {
    @Test
    public void sumsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
~~~

Although `Test` looks similar to the previous example, this is **`org.junit.Test`**, not `org.junit.jupiter.api.Test`. JUnit 4 normally requires the test class and test method to be `public` when using the default runner. JUnit 4 and Jupiter have different annotation/assertion/lifecycle sets:

| Intent | JUnit 4 | Jupiter |
|---|---|---|
| Mark a test | `org.junit.Test` | `org.junit.jupiter.api.Test` |
| Before each test | `@Before` | `@BeforeEach` |
| After each test | `@After` | `@AfterEach` |
| Before all tests | `@BeforeClass`, static method | `@BeforeAll`, usually static (unless configured lifecycle permits) |
| Traditional Spring Test extension integration | `@RunWith(SpringRunner.class)` | `@ExtendWith(SpringExtension.class)`, or Spring Boot annotations meta-annotated with it |
| Assert exception | `@Test(expected = ...)` or `ExpectedException` | `assertThrows(...)` |
| Grouping | `@Category` | `@Tag` |

**Vintage is not a required component for new projects.** It is helpful during migration from JUnit 3/4 to Jupiter. Once no legacy tests remain, removing the Vintage engine and JUnit 4 dependencies simplifies the classpath. However, removing Vintage **before** migrating all tests can silently stop part of the test suite from executing, creating a misleading green build.

JUnit Platform also supports other `TestEngine`s. The two engines in this lesson are common examples, not an exhaustive list. JUnit Platform Suite has its own engine when using the suite API; do not confuse a suite engine with Jupiter/Vintage.

## 5. Runnable example: Spring Boot + Gradle + two engines

Create a Java 17+, Gradle 8.x, Spring Boot 3.3.5 project. File layout:

~~~text
build.gradle
settings.gradle
src/main/java/demo/testing/TestingApplication.java
src/main/java/demo/testing/PriceCalculator.java
src/test/java/demo/testing/PriceCalculatorJupiterTest.java
src/test/java/demo/testing/PriceCalculatorLegacyTest.java
src/test/java/demo/testing/DiscoveryProbe.java
~~~

The example intentionally keeps one JUnit 4 test to demonstrate Vintage; new projects using only Jupiter can omit legacy dependencies.

**settings.gradle**

~~~groovy
rootProject.name = 'junit-engine-discovery-demo'
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

    // Jupiter and test utilities are managed by Spring Boot.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // These two dependencies are needed only while JUnit 4 tests remain.
    testImplementation 'junit:junit:4.13.2'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'

    // The probe below calls the Launcher API directly at compile time.
    testImplementation 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}

// Standalone task to inspect discovery without executing test methods.
tasks.register('discoverTests', JavaExec) {
    dependsOn tasks.named('testClasses')
    classpath = sourceSets.test.runtimeClasspath
    mainClass = 'demo.testing.DiscoveryProbe'
}
~~~

**Why are these declarations necessary?**

- The Gradle test task with **`useJUnitPlatform()`** delegates test execution to JUnit Platform. Omitting it in a Gradle configuration using the legacy JUnit 4 default can prevent Jupiter tests from running.
- `spring-boot-starter-test` supplies testing libraries whose versions Spring Boot manages, including Jupiter. The Spring Boot BOM manages JUnit Platform/Jupiter/Vintage versions when dependency management is applied as above.
- `junit:junit:4.13.2` allows JUnit 4-style tests to compile.
- `junit-vintage-engine` in **`testRuntimeOnly`** lets the Platform find the engine to run JUnit 4 tests.
- `junit-platform-launcher` is in **`testImplementation`** because `DiscoveryProbe` directly imports the Launcher API in test source. If you only run tests via Gradle without writing a custom probe, the launcher is typically only needed on the test runtime classpath.
- Which engines actually run depends on the test runtime classpath and filters; **`useJUnitPlatform()` does not install Vintage automatically**.

**src/main/java/demo/testing/TestingApplication.java**

~~~java
package demo.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingApplication.class, args);
    }
}
~~~

**src/main/java/demo/testing/PriceCalculator.java**

~~~java
package demo.testing;

public final class PriceCalculator {
    private PriceCalculator() {
    }

    public static long totalWithFee(long price, long fee) {
        if (price < 0 || fee < 0) {
            throw new IllegalArgumentException("Price and fee must be non-negative");
        }
        return Math.addExact(price, fee);
    }
}
~~~

This is a plain Java subject under test inside a Spring Boot project, allowing us to observe test discovery clearly without booting an `ApplicationContext`. Spring context tests such as `@SpringBootTest` are also discovered by their corresponding engine; `SpringExtension` handles Spring integration during execution.

**src/test/java/demo/testing/PriceCalculatorJupiterTest.java**

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class PriceCalculatorJupiterTest {

    @Test
    void addsFee() {
        assertEquals(125L, PriceCalculator.totalWithFee(100L, 25L));
    }

    @Test
    void rejectsNegativeFee() {
        assertThrows(
            IllegalArgumentException.class,
            () -> PriceCalculator.totalWithFee(100L, -1L)
        );
    }
}
~~~

Neither the class nor its methods are `public`, yet Jupiter still discovers both `@Test` methods.

**src/test/java/demo/testing/PriceCalculatorLegacyTest.java**

~~~java
package demo.testing;

import org.junit.Test;

import static org.junit.Assert.assertEquals;

public class PriceCalculatorLegacyTest {

    @Test
    public void addsFee() {
        assertEquals(125L, PriceCalculator.totalWithFee(100L, 25L));
    }
}
~~~

This is a JUnit 4 test. Vintage must be present for the Launcher to run it alongside the two Jupiter tests when using JUnit Platform.

**src/test/java/demo/testing/DiscoveryProbe.java**

~~~java
package demo.testing;

import org.junit.platform.engine.discovery.DiscoverySelectors;
import org.junit.platform.launcher.Launcher;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.TestIdentifier;
import org.junit.platform.launcher.TestPlan;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;

public final class DiscoveryProbe {
    private DiscoveryProbe() {
    }

    public static void main(String[] args) {
        LauncherDiscoveryRequest request =
            LauncherDiscoveryRequestBuilder.request()
                .selectors(
                    DiscoverySelectors.selectClass(
                        PriceCalculatorJupiterTest.class
                    ),
                    DiscoverySelectors.selectClass(
                        PriceCalculatorLegacyTest.class
                    )
                )
                .build();

        Launcher launcher = LauncherFactory.create();
        TestPlan plan = launcher.discover(request);

        plan.getRoots().stream()
            .map(TestIdentifier::getUniqueId)
            .sorted()
            .forEach(System.out::println);

        System.out.println(
            "Discovered test nodes: "
                + plan.countTestIdentifiers(TestIdentifier::isTest)
        );
    }
}
~~~

`LauncherFactory` locates the `TestEngine`s on the runtime classpath. The request selects **exactly two classes**, so the example does not depend on broader package scanning. `plan.getRoots()` shows the engines with discovered tests; `countTestIdentifiers(TestIdentifier::isTest)` counts test nodes in the plan. The probe calls **`discover`**, not `execute`, so test method bodies do not run.

Run with the project's Gradle Wrapper (if creating manually from the files above, Gradle/Gradle Wrapper must be installed or generated first):

~~~bash
./gradlew discoverTests
./gradlew test
~~~

On Windows PowerShell with Gradle Wrapper:

~~~powershell
.\gradlew.bat discoverTests
.\gradlew.bat test
~~~

Output printed by **DiscoveryProbe** (other Gradle lines may also appear):

~~~text
[engine:junit-jupiter]
[engine:junit-vintage]
Discovered test nodes: 3
~~~

When running the Gradle `test` task, all three tests pass. To view the HTML report, open **`build/reports/tests/test/index.html`**. Gradle's console also prints task statuses and `BUILD SUCCESSFUL` when the build succeeds, though exact formatting depends on Gradle/logging.

You can run selectively:

~~~bash
./gradlew test --tests demo.testing.PriceCalculatorJupiterTest
./gradlew test --tests demo.testing.PriceCalculatorLegacyTest
~~~

When running two commands back-to-back, Gradle may use cache/up-to-date status or rerun depending on filters and task inputs; what matters is checking that the selected tests appear in the report. If you remove the Vintage engine, selecting the JUnit 4 test alone may report no tests matching the filter. Having JUnit 4 source still compile successfully **does not prove it ran**.

## 6. Using selectors and filters properly

The demo used **`selectClass`** to ensure only two classes were searched. In projects with many tests, other selectors can be used:

~~~java
// Example API snippet placed inside code that has LauncherDiscoveryRequestBuilder.
LauncherDiscoveryRequest request =
    LauncherDiscoveryRequestBuilder.request()
        .selectors(
            DiscoverySelectors.selectPackage("demo.testing")
        )
        .build();
~~~

The snippet above **illustrates the API** and is not a standalone Java file; it requires appropriate imports and a configured classpath. It requests test discovery in the package, and the engines determine which classes are tests. Not every class in the package becomes a test.

Common selectors:

| Selector | Intent |
|---|---|
| `selectClass(MyTest.class)` | Target a single candidate class |
| `selectMethod("demo.testing.MyTest#caseName()")` | Target a specific test method |
| `selectPackage("demo.testing")` | Discover within a package |
| `selectClasspathRoots(Set<Path>)` | Discover within specified classpath roots |

You can restrict engines at the Launcher level using **`EngineFilter.includeEngines("junit-jupiter")`** inside `LauncherDiscoveryRequestBuilder.filters(...)`. The ID here is the engine name, not a Maven artifact name.

In Gradle, you can set an engine filter on the test task:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeEngines 'junit-jupiter'
    }
}
~~~

**This is an alternative configuration**, not to be applied alongside the two-engine setup above. When filtering to Jupiter only, JUnit 4 tests will not run even if `vintage-engine` remains in dependencies. To run both, call `useJUnitPlatform()` without filtering or specify both `junit-jupiter` and `junit-vintage`.

Filters on **tags** and **classes/packages** operate during test selection; Jupiter's `@Disabled` normally causes a `skipped` status at execution rather than removing the test from discovery altogether. Do not conflate "discovered", "selected for execution", "executed", "passed", and "skipped".

## 7. TestPlan, TestIdentifier, and counting tests

A `TestPlan` represents nodes:
- **Engine root:** e.g., unique ID `[engine:junit-jupiter]` or `[engine:junit-vintage]`.
- **Container:** test class or group, including nested classes and engine-created intermediate levels.
- **Test node:** a test unit represented in the plan.

Each `TestIdentifier` has a unique ID, display name, and flags such as `isTest()`/`isContainer()`. Unique IDs identify elements in the tree for engines; display names are for presentation and may change. Do not rely on display name text as a stable key.

One class with two Jupiter `@Test` methods and one class with one JUnit 4 `@Test` method produce three test nodes at discovery time in the example. However, this number **is not a universal formula**: dynamic tests produced by `@TestFactory` can appear at execution time, parameterized/repeated tests have multiple invocations, and engines are free to structure descriptors according to their model. To evaluate how many tests **ran/passed/failed/skipped**, check `TestExecutionSummary`, listeners, or the final test report.

You can register `SummaryGeneratingListener` when using the Launcher API: pass the listener to the launcher, call `execute(request)`, and retrieve the summary. That step actually executes tests; do not confuse it with the `discover(request)` call above.

## 8. Spring Boot Test and engine selection

Spring Boot Test does not replace JUnit Platform. It provides `ApplicationContext` management, dependency injection, transactions, MockMvc/WebTestClient, test slices, and `SpringExtension` depending on annotations.

Example with JUnit Jupiter:

~~~java
package demo.testing;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextJupiterTest {

    @Test
    void contextLoads() {
        // Spring Boot starts ApplicationContext before the test runs.
    }
}
~~~

In Spring Boot 3.3.x, `SpringBootTest` integrates `SpringExtension` for Jupiter. The **Jupiter engine** is still what discovers the `org.junit.jupiter.api.Test` annotation; `SpringExtension` is not an independent `TestEngine`. For Spring tests written in JUnit 4, the old pattern typically uses `@RunWith(SpringRunner.class)` and `org.junit.Test`; when running on Platform, the **Vintage engine** handles those tests. Thus the same Spring Boot project can contain both Jupiter and Vintage during a migration period.

Annotations such as `@MockBean` (within the Spring Boot version scope of this example), `@Transactional`, or `@ActiveProfiles` adjust how a test uses the Spring context; they **do not select the JUnit Platform engine**. Engine selection still depends on the test API/runner type, dependencies, and launcher/filter configuration.

## 9. Maven Surefire and IDEs: same goal, different launch mechanisms

If the project uses Maven instead of Gradle, Maven Surefire supports JUnit Platform (selecting the appropriate provider when a JUnit Platform engine is present); in Spring Boot 3.3.x with the Spring Boot parent/BOM, JUnit versions are managed in sync. Dependencies need Jupiter, adding JUnit 4/Vintage only if legacy tests remain:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>

    <!-- Use only while JUnit 4 tests remain. -->
    <dependency>
        <groupId>junit</groupId>
        <artifactId>junit</artifactId>
        <version>4.13.2</version>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.junit.vintage</groupId>
        <artifactId>junit-vintage-engine</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

This snippet is the **dependencies section of a `pom.xml`**, not a complete POM. You need the Spring Boot parent/BOM and a Maven Surefire version capable of running JUnit Platform. Maven also has default class-naming conventions for finding tests, such as `Test*`, `*Test`, `*Tests`, and `*TestCase`; wrong names or includes/excludes can prevent tests from being selected. Gradle and Maven configure filtering differently, though both can ultimately run via JUnit Platform.

IDEs such as IntelliJ IDEA or Eclipse can build `LauncherDiscoveryRequest`s differently from the build tool (e.g., selecting a single class or method rather than a whole package). Therefore "passes when clicking Run in the IDE" does not necessarily mean "runs in CI". Always verify with the pipeline's exact Gradle/Maven command.

## 10. How to diagnose "no tests found"

| Symptom | Possibilities to check | Action |
|---|---|---|
| Jupiter tests are skipped in Gradle | `test` task does not configure `useJUnitPlatform`; missing Jupiter engine | Enable `useJUnitPlatform`, check Jupiter runtime dependencies |
| JUnit 4 tests compile yet do not run | Missing `junit-vintage-engine` or filtered out excluding `junit-vintage` | Keep Vintage during migration; check engine IDs/filters |
| Running `--tests` for a specific class reports no match | Wrong package/class name, excluded by filter, or engine cannot discover class | Check `testClasses`, classpath, `@Test` import, and pattern |
| Test report shows 0 tests yet build is green | Source set lacks matching test classes, matchers/engines filtered everything out | Check the list of tests **actually executed**, not just exit code |
| JUnit 4 test fails with "No runnable methods" | Wrong import, method/class violates JUnit 4 rules, wrong runner | Check annotation namespace and JUnit 4 `public` requirements |
| Test should have many cases yet discovery counts fewer | Parameterized/dynamic tests register invocations during execution | Compare test report/invocation count after running |
| IDE behavior differs from CI | IDE targets a specific class; CI uses includes/excludes, engine filters, or different dependencies | Rerun the CI build command and compare classpaths and filters |
| Error starting test engine | Platform/Jupiter/Vintage versions misaligned or incompatible manual dependencies | Use Spring Boot BOM/management, inspect dependency graph |

Helpful Gradle commands:

~~~bash
./gradlew test --info
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew test --tests demo.testing.PriceCalculatorLegacyTest
~~~

Note: `--info` mode can print many lines; look for task details, test classes, filters, and actual errors. The test runtime dependency list tells you whether both `junit-jupiter-engine` and `junit-vintage-engine` are present. In multi-module projects, run the test task of the specific module under inspection; do not assume a root task covers every module.

If a test does not run, check in order: **(1) did it compile into the test source set → (2) does the build task cover that scope → (3) is JUnit Platform enabled → (4) is the right engine on runtime → (5) do annotations/runners belong to Jupiter or JUnit 4 → (6) do selectors/filters exclude the test → (7) was the test discovered yet disabled/skipped, or did it execute and fail?** This separates discovery issues from assertion failures or Spring `ApplicationContext` errors.

## 11. Strategy to migrate JUnit 4 to Jupiter without losing tests

1. **Measure a baseline:** Record the actual number of executed tests and pass/fail/skipped counts in CI before making changes. Ensure Vintage is enabled if JUnit 4 tests remain.
2. **Run both engines side by side:** Enable `useJUnitPlatform` and keep both Jupiter and Vintage on the test runtime classpath. Each individual test class should stick clearly to one annotation/runner system.
3. **Migrate deliberately:** Switch `org.junit.Test` imports to `org.junit.jupiter.api.Test`; update lifecycle annotations; convert `@RunWith`/Rules to corresponding Jupiter extensions/APIs; replace expected-exception attributes with `assertThrows` where appropriate. Do not assume changing imports automatically preserves Rule, parameterized runner, or lifecycle semantics.
4. **Compare before and after reports:** Verify test coverage and assertions are preserved. If test counts drop, diagnose via discovery/filters/reports before deleting dependencies.
5. **Remove Vintage last:** After confirming no JUnit 3/4 tests remain to run, remove `junit-vintage-engine` and unused JUnit 4 dependencies. Run tests and verify results in CI again.

In new projects with no legacy tests, choose Jupiter by default. Vintage is a **compatibility bridge**, not a required dependency for "full JUnit Platform".

## 12. Takeaways for self-assessment

- JUnit Platform is the **test discovery/execution infrastructure**; Jupiter and Vintage are **two `TestEngine`s**. A `Test` annotation matters only when the right engine recognizes it.
- **Jupiter** recognizes `org.junit.jupiter.api.Test` and Jupiter APIs; **Vintage** recognizes JUnit 3/4. Spring Boot `starter-test` sets up Jupiter, whereas JUnit 4 tests still need Vintage separately when running on Platform.
- **Selectors** answer "where to look"; **filters** answer "what to keep"; **engines** answer "is this class/method a test I support?". Discovery builds the `TestPlan`; execution actually runs methods and yields pass/fail/skipped.
- Check **actual test counts and reports** in CI; a green build alone does not prove legacy tests were discovered after changing engines or dependencies.
- With `@ParameterizedTest`/`@TestFactory`, do not treat discovery node counts as actual invocation counts; use execution results to judge coverage.

Self-check exercise: in the example, temporarily remove `junit-vintage-engine` from the test runtime classpath, run `discoverTests` and `test` (after recording the baseline), then restore the dependency. Explain why the JUnit 4 class still compiles yet disappears from `TestPlan`. Next, configure `includeEngines` to only `junit-jupiter` and observe the difference between **having an engine on the classpath** and **allowing that engine to participate in discovery**.
