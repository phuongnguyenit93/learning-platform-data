# JUnit Platform, Jupiter, and Test Execution Tools

In a Java project, writing test methods is only part of the workflow. There must be components that discover which tests need to be run, invoke the right framework to execute them, record the results, and pass those results back to the IDE or build system. The JUnit ecosystem separates these responsibilities into **JUnit Platform**, **JUnit Jupiter**, and execution tools that integrate with the Platform.

When testing Spring applications, this separation helps explain why a class with `@Test` is not executed, why the IDE can run tests while Gradle finds none, or why `@Autowired` in a test only works when the Spring Extension is registered. Understanding the architecture also helps in choosing the right dependencies and configuration for each environment.

## 1. The Three Main Components of the JUnit Ecosystem

JUnit Platform, Jupiter, and test runner tools are related, but they are not a single monolithic component.

| Component | Role | Example APIs or Artifacts |
|---|---|---|
| JUnit Platform | Discovery and execution foundation; provides the mechanism for tools to find and run tests through TestEngines | `Launcher`, `TestEngine`, `TestPlan`, `TestExecutionListener` |
| JUnit Jupiter | Modern test programming model: annotations, assertions, extensions, and lifecycle rules | `@Test`, `@BeforeEach`, `@ParameterizedTest`, `@ExtendWith` |
| Jupiter Engine | Engine implementing `TestEngine` so the Platform can discover and execute tests written with Jupiter | `junit-jupiter-engine` |
| Execution Tools | Integrate with the Platform so users can run tests, select scope, and view reports | Gradle, Maven Surefire, IDE, Console Launcher |

You can visualize the dependency flow as follows:

```text
Test code using JUnit Jupiter API
             |
             v
       Jupiter Engine  ---------+
             ^                  |
             |                  v
       JUnit Platform <---- Launcher API
             ^                  ^
             |                  |
      IDE / Gradle / Maven / Console Launcher
```

The diagram emphasizes that execution tools ask the Platform to run tests, while the Platform delegates discovery and execution to the appropriate engine. The Jupiter API is the programming model for writing tests; the Jupiter Engine is the component that actually interprets that model within the Platform.

### 1.1. JUnit Platform

JUnit Platform is the foundation layer for testing frameworks running on the JVM. The Platform does not dictate that every test must use Jupiter's `@Test` annotation. Instead, it provides a common contract for frameworks to register engines and for external tools to discover, run, and receive results.

Important components include:

- **TestEngine:** An SPI (Service Provider Interface) implemented by a framework or engine. The engine is responsible for receiving discovery requests, finding tests belonging to its model, and executing them.
- **Launcher:** The API that IDEs, build tools, or custom programs use to submit test discovery and execution requests.
- **LauncherDiscoveryRequest:** Describes the request to be performed, including selectors and filters.
- **TestPlan:** Represents the discovered test plan, consisting of nodes and parent-child relationships.
- **TestIdentifier:** Identifies a node in the test plan, which can be a container or a test leaf.
- **TestExecutionListener:** Receives events during execution, such as started, succeeded, failed, skipped, or finished.

The Platform also includes components to support discovering engines via service loading. As a result, execution tools can work with multiple engines in a single run without needing to understand the specific annotation details of each framework.

### 1.2. JUnit Jupiter

JUnit Jupiter is JUnit's next-generation test writing model. It provides:

- Annotations defining tests and lifecycle callbacks.
- Assertions and assumptions for verifying conditions.
- Parameterized tests, repeated tests, nested tests, and dynamic tests.
- An Extension API to integrate dependency injection, resource management, or additional behavior.
- Mechanisms for display names, tagging, disabling tests, and configuring instance lifecycles.

Annotations such as `@Test`, `@BeforeEach`, and `@ParameterizedTest` belong to the `org.junit.jupiter.api` package or Jupiter subpackages. They describe tests according to the Jupiter model; the Platform cannot interpret these annotations on its own without the Jupiter Engine.

### 1.3. Jupiter Engine and Other Engines

The Jupiter Engine is the `TestEngine` implementation for Jupiter tests. When the Platform receives a request to run tests, this engine locates classes and methods according to Jupiter rules and executes them.

The Platform is not limited to a single engine. For example:

- **Jupiter Engine** runs tests using JUnit Jupiter.
- **Vintage Engine** allows the Platform to run legacy JUnit 3 and JUnit 4 tests during a migration phase.
- Other frameworks can provide their own engines to integrate with the Platform.

If a project still has JUnit 4 tests, adding the Jupiter API does not automatically cause legacy tests to run with Jupiter. The project needs the corresponding engine (such as Vintage) and compatible configuration. For new projects, it is best to standardize on Jupiter to avoid maintaining multiple test models unless migration is required.

## 2. The Test Discovery and Execution Process

When running tests from an IDE or build tool, there are usually two major phases: **discovery** and **execution**.

### 2.1. Discovery — Finding Tests to Run

First, the execution tool constructs a discovery request. The request can specify:

- Packages to scan.
- A specific class or method.
- A classpath root.
- Engines to include or exclude.
- Tags to include or exclude.
- Other filters supported by the tool.

Selectors indicate the scope or targets the tool wants to find; filters narrow down what gets selected. The Platform forwards this request to the appropriate engines. Each engine discovers its own tests and returns a descriptor tree describing the test structure.

For Jupiter, the engine reads annotations and class structure to identify test methods, lifecycle methods, nested classes, parameterized tests, and related components. The results are combined into a `TestPlan` so the tool can display the test tree before or during execution.

### 2.2. Execution — Running Tests

After discovery, the Launcher instructs the engines to execute the found tests. During execution, the Platform emits events to listeners. Execution tools use these events to update status in the IDE, write XML reports, record timings, and mark failed tests.

General flow:

1. The user chooses to run tests in the IDE or build tool.
2. The tool creates a `LauncherDiscoveryRequest` with appropriate selectors and filters.
3. The Platform locates available `TestEngine` implementations and asks each engine to discover tests.
4. The engines return test descriptors; the Platform builds the `TestPlan`.
5. The Launcher instructs the engines to execute the selected nodes.
6. Each engine runs individual containers/tests, applying lifecycles and extensions according to its framework.
7. The Platform emits execution events; the tool collects results and generates reports.

A test may not be executed even if the source code compiles successfully. For example, the corresponding engine might be missing from the runtime classpath, a filter might exclude the test, the class name might not match the tool's discovery rules, or the test might be marked disabled. Therefore, it is important to distinguish between compilation errors, discovery errors, and execution errors.

## 3. The JUnit Jupiter Test Model

Jupiter supports many types of tests and callbacks. The annotations below are the group commonly used when building a test suite for Spring applications.

| Annotation | Meaning |
|---|---|
| `@Test` | Marks a standard test method |
| `@ParameterizedTest` | Runs the same test with multiple sets of arguments |
| `@RepeatedTest` | Runs a test multiple times according to a specified count |
| `@TestFactory` | Creates dynamic tests or dynamic containers at runtime |
| `@TestTemplate` | Creates test invocations using a corresponding provider and extension |
| `@BeforeEach` / `@AfterEach` | Runs before/after each test method respectively |
| `@BeforeAll` / `@AfterAll` | Runs once before/after all tests in a container |
| `@Nested` | Organizes nested groups of tests inside a test class |
| `@DisplayName` | Sets a human-readable display name for a test or container |
| `@Tag` | Attaches a label to include or exclude a group of tests |
| `@Disabled` | Disables a test or container |
| `@ExtendWith` | Registers one or more extensions |
| `@TestInstance` | Selects the instance lifecycle of the test class |
| `@TempDir` | Provides a temporary directory for the test |
| `@Timeout` | Sets a time limit for a test or container |

### 3.1. Structure of a Test Class

Basic example:

```java
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class PriceCalculatorTest {

    private PriceCalculator calculator;

    @BeforeEach
    void setUp() {
        calculator = new PriceCalculator();
    }

    @Test
    @DisplayName("applies the discount to the original price")
    void appliesDiscount() {
        var result = calculator.discount(100, 10);

        assertEquals(90, result);
    }

    @AfterEach
    void tearDown() {
        calculator = null;
    }
}
```

Jupiter test classes and test methods can use package-private visibility. Standard test methods must not be `static`, must return `void`, and cannot accept arbitrary parameters. Parameters are only allowed when provided by a parameterized test, test template, or an appropriate `ParameterResolver`. Test classes must not be `private` or `abstract`.

### 3.2. Default Lifecycle

By default, Jupiter uses the `PER_METHOD` instance lifecycle: each test method gets a new instance of the test class. This limits mutable state shared between tests.

General order for a single test method:

```text
Create test instance
      |
      v
@BeforeEach (in matching inheritance order)
      |
      v
Test method
      |
      v
@AfterEach
      |
      v
Destroy instance
```

`@BeforeAll` and `@AfterAll` run once for the container. With the `PER_METHOD` lifecycle, these methods normally must be `static`. If `@TestInstance(TestInstance.Lifecycle.PER_CLASS)` is declared, they can be instance methods:

```java
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
class SharedFixtureTest {

    private ExpensiveFixture fixture;

    @BeforeAll
    void createFixtureOnce() {
        fixture = ExpensiveFixture.open();
    }

    @AfterAll
    void closeFixtureOnce() {
        fixture.close();
    }
}
```

`PER_CLASS` is useful when a fixture is expensive to initialize or needs to be shared across methods. However, tests can affect one another if they mutate shared state together. Use it only when such sharing is controlled and cleanup is handled explicitly.

### 3.3. Parameterized Tests

Parameterized tests allow describing a single rule with multiple representative inputs. Argument sources can come from `@ValueSource`, `@NullSource`, `@EmptySource`, `@CsvSource`, `@MethodSource`, or custom sources.

```java
@ParameterizedTest
@ValueSource(strings = {"", "   "})
void rejectsBlankEmail(String email) {
    assertThrows(IllegalArgumentException.class,
            () -> registrationService.register(email, "valid-password-123"));
}
```

Commonly used argument source annotations reside in the `org.junit.jupiter.params` and `org.junit.jupiter.params.provider` packages. When only `junit-jupiter-api` is added without the params module, annotations like `@ParameterizedTest` will not be on the classpath. The aggregate dependency `junit-jupiter` typically brings in the API, parameterized tests, and the engine together in the test configuration.

### 3.4. Nested Tests and Display Names

`@Nested` helps group cases by state or context. For example, an `OrderServiceTest` class can contain `WhenOrderIsPending` and `WhenOrderIsShipped` groups, each with its own fixture and tests. Nested classes must not be declared `static` under the Jupiter model.

`@DisplayName` makes reports easier to read than technical method names. Still, you should keep method names meaningful because those names are useful when searching, filtering, and reading logs.

### 3.5. Tags and Assumptions

`@Tag` attaches labels to tests, such as `unit`, `integration`, `database`, or `slow`. Execution tools can include or exclude tests by tag. A test can carry multiple tags.

Assumptions differ from assertions. A failed assertion means the behavior under test did not meet expectations. An unsatisfied assumption can cause a test to be aborted/skipped because environment conditions or scenario preconditions are unsuitable. You should not use assumptions to hide a business logic bug that ought to be detected.

## 4. Extension API and Spring TestContext Integration

A key aspect of Jupiter is its extension model. Extensions add behavior to the test lifecycle without requiring inheritance from a single base class.

Extensions can participate in extension points such as:

- Creating and post-processing test instances.
- Executing callbacks before/after a container or test method.
- Resolving parameters for test methods.
- Handling exceptions.
- Intercepting execution conditions or registering additional test behaviors.

Extensions can be registered using `@ExtendWith`, via automatic registration configuration, or through appropriate programmatic registration APIs. Jupiter provides several built-in extensions; for example, `@TempDir` and `@Timeout` are backed by the framework's extension mechanism.

### 4.1. SpringExtension as the Bridge Between Jupiter and Spring

Spring Framework provides `SpringExtension` in the Spring TestContext Framework. This extension integrates the Jupiter lifecycle with `TestContextManager`, enabling tests to use an ApplicationContext, dependency injection, transaction management, and other Spring testing features.

There are two common ways to declare it:

```java
@ExtendWith(SpringExtension.class)
@ContextConfiguration(classes = TestConfig.class)
class AccountServiceTest {
    // test fields and test methods
}
```

Or using Spring's composed annotation:

```java
@SpringJUnitConfig(TestConfig.class)
class AccountServiceTest {

    @Autowired
    private AccountService accountService;

    @Test
    void loadsServiceFromApplicationContext() {
        assertNotNull(accountService);
    }
}
```

`@SpringJUnitConfig` combines registering `SpringExtension` with configuring the ApplicationContext. When the test runs, the Spring extension coordinates with the TestContext Framework to prepare the test instance and execute related callbacks. Consequently, `@Autowired` in a test is processed by Spring rather than being natively understood by Jupiter.

### 4.2. Spring Test Annotations

When using SpringExtension, tests can combine it with Spring TestContext annotations such as:

- `@ContextConfiguration`: specifies configuration sources or configuration classes for the ApplicationContext.
- `@WebAppConfiguration`: requests configuration of a web application context in appropriate scenarios.
- `@TestPropertySource`: provides properties specific to the test context.
- `@ActiveProfiles`: selects active profiles when creating the context.
- `@DirtiesContext`: marks that the context needs to be evicted from the cache because the test modified shared state.
- `@Transactional`: runs the test inside a transaction managed by Spring TestContext when supported by configuration.
- `@Sql`: executes SQL scripts during configured phases.

These annotations belong to Spring TestContext, not native JUnit Jupiter. They work in Jupiter tests when SpringExtension is registered and the corresponding configuration requirements are met.

With Spring Boot, `@SpringBootTest` belongs to Spring Boot Test and creates an ApplicationContext according to the Boot application configuration. This is an application-scoped choice; it does not replace the role of the Jupiter Engine or JUnit Platform. Test slices such as `@WebMvcTest` and `@DataJpaTest` are also Spring Boot annotations, commonly used to load only a subset of configuration for testing.

### 4.3. When Do You Need SpringExtension?

Not every test in a Spring project needs to load a Spring context.

- If you are only testing algorithms or pure Java rules, JUnit Jupiter with Mockito may be sufficient.
- If you need to test Spring bean wiring, `@Autowired`, profiles, properties, lifecycle, or transactions, use SpringExtension.
- If you need to test web configuration, persistence, or the full application, choose a test slice or `@SpringBootTest` according to the scope you need to verify.

Loading a context incurs startup overhead and can make tests dependent on environment configuration. Only enable Spring TestContext when the behavior under test genuinely requires those capabilities.

## 5. JUnit Platform Execution Tools

JUnit Platform provides the Launcher API; tools integrate this API to run tests in different environments. The same Jupiter test can be run from an IDE, Gradle, Maven, or the Console Launcher given a suitable classpath and configuration.

### 5.1. IDE

Popular Java IDEs can run Jupiter tests directly from the editor or test explorer. An IDE typically:

- Detects test classes and methods in source sets.
- Builds an execution request for a single method, a class, a package, or an entire test suite.
- Displays the test tree and the status of each node.
- Allows debugging, re-running failed tests, and inspecting stack traces.

IDEs may use a built-in launcher or custom runner configurations. Therefore, the fact that an IDE can run tests does not prove that the Gradle/Maven configuration is complete. When CI fails to find tests, inspect the build configuration independently of IDE settings.

### 5.2. Gradle

Gradle needs to be configured to use JUnit Platform. With the Groovy DSL, the configuration typically looks like:

```groovy
def junitVersion = providers.gradleProperty("junitVersion").get()

dependencies {
    testImplementation(platform("org.junit:junit-bom:$junitVersion"))
    testImplementation("org.junit.jupiter:junit-jupiter")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

The example assumes the project declares the `junitVersion` property in `gradle.properties` or provides it through Gradle configuration. Choose a JUnit BOM version compatible with the project's Java version and dependencies. The BOM keeps JUnit Platform/Jupiter artifact versions synchronized to avoid mixing incompatible modules.

Role of each configuration entry:

- `junit-bom` manages consistent versions for JUnit artifacts.
- `junit-jupiter` is the aggregate dependency commonly used to bring the API, parameterized tests, and Jupiter engine into the test configuration.
- `junit-platform-launcher` provides the Launcher API to execution tools; with modern Gradle, declaring this runtime dependency makes the launcher classpath explicit and compatible with test execution integration.
- `useJUnitPlatform()` tells the `Test` task to use JUnit Platform instead of the legacy default JUnit 4 mechanism.

Run all tests:

```bash
./gradlew test
```

Run a single test class:

```bash
./gradlew test --tests "com.example.account.AccountServiceTest"
```

Run a single test method using Gradle's filter:

```bash
./gradlew test --tests "com.example.account.AccountServiceTest.rejectsDuplicateEmail"
```

You can filter by tags in the task configuration:

```groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform {
        includeTags("unit")
        excludeTags("slow", "external")
    }
}
```

When configuring tags in Gradle, ensure tags are applied in the tests and no other configuration accidentally excludes tests that should run. Task names also matter: `test` usually runs the main test source set, while separate integration source sets or tasks may have different configurations and classpaths.

### 5.3. Maven Surefire and Failsafe

In Maven, the Maven Surefire Plugin typically runs unit tests in the `test` phase. With modern plugin versions, Surefire integrates with JUnit Platform to run the Jupiter Engine. The configuration requires the Jupiter dependency and a Surefire version compatible with the chosen JUnit generation.

Example dependency structure using JUnit BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.junit</groupId>
            <artifactId>junit-bom</artifactId>
            <version>${junit.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
```

`junit.version` must be declared in the project's properties section or managed by a higher-level parent/BOM. At the same time, use a Maven Surefire Plugin version compatible with the JUnit Platform and Java versions used by the project. Do not copy an old plugin version from another project without checking compatibility.

Run tests with Maven:

```bash
mvn test
```

Run only a single test class:

```bash
mvn -Dtest=AccountServiceTest test
```

Surefire is suitable for unit tests running during the test phase. For integration tests that need to run during the verify phase and follow separate naming conventions, the Maven Failsafe Plugin is commonly used to separate the integration test lifecycle from unit tests. Splitting tasks enables the pipeline to run fast unit tests first, followed by integration tests that require databases, containers, or auxiliary services.

### 5.4. JUnit Platform Console Launcher

The Console Launcher is a command-line tool that runs tests via JUnit Platform. It is useful when you need to run tests outside an IDE or build tool, experiment with the classpath, verify discovery independently, or create a simple test-running step in a JVM environment.

The `junit-platform-console-standalone` artifact packages the Console Launcher along with the required Platform components. Once you have the JAR corresponding to the project's JUnit version and a classpath containing the tests and application dependencies, you can scan the classpath to find Jupiter tests:

```bash
java -jar junit-platform-console-standalone.jar execute \
  --class-path "build/classes/java/test;build/classes/java/main" \
  --scan-class-path \
  --include-engine junit-jupiter
```

The classpath in the example must be adjusted according to the operating system, build output, and actual dependencies. On Windows, the classpath separator is `;`; on Linux/macOS it is `:`. If tests depend on Spring, Mockito, or other libraries, the corresponding JARs must also be present on the classpath. Adding only compiled class directories without dependencies may allow tests to be discovered yet fail during instantiation.

The Console Launcher supports selectors and filters to limit execution scope. Depending on the version, command syntax and options may vary; use `--help` from the exact Console Launcher version installed in the project to check current syntax.

### 5.5. Launcher API for Custom Tools

When you need to build a custom test runner, plugin, or reporting tool, you can use the Launcher API directly. Condensed example:

```java
import static org.junit.platform.engine.discovery.DiscoverySelectors.selectPackage;
import static org.junit.platform.launcher.EngineFilter.includeEngines;

import org.junit.platform.launcher.Launcher;
import org.junit.platform.launcher.LauncherDiscoveryRequest;
import org.junit.platform.launcher.core.LauncherDiscoveryRequestBuilder;
import org.junit.platform.launcher.core.LauncherFactory;

LauncherDiscoveryRequest request = LauncherDiscoveryRequestBuilder.request()
        .selectors(selectPackage("com.example"))
        .filters(includeEngines("junit-jupiter"))
        .build();

Launcher launcher = LauncherFactory.create();
launcher.execute(request);
```

This example only demonstrates how to build a request, select a package, and restrict engines. A real tool typically registers a `TestExecutionListener` to receive events, store results, format reports, and handle errors. For ordinary test execution, let Gradle, Maven, or the IDE manage the Launcher instead of writing a custom runner.

## 6. Selecting Test Scope with Selectors, Filters, and Tags

These three concepts help control which set of tests is executed:

- **Selector** indicates where or what to discover, such as a package, class, method, or classpath root.
- **Filter** excludes nodes that do not satisfy a condition, such as engine or tag.
- **Tag** is a label attached by test authors to a container/test to group tests by purpose.

Example:

```java
@Tag("unit")
class PriceCalculatorTest {
    @Test
    void calculatesDiscount() {
        // ...
    }
}

@Tag("integration")
class AccountRepositoryTest {
    @Test
    void persistsAccount() {
        // ...
    }
}
```

Tag groups should describe operational characteristics useful for the pipeline, such as `unit`, `integration`, `slow`, `database`, or `external`. Avoid creating too many overlapping tags or using inconsistent tag names across modules.

You should not rely solely on tags to decide whether tests are safe for parallel execution. A test tagged `unit` might still share a file or static state; an `integration` test might be well isolated. Test selection must align with the environment conditions and resources that the tests use.

## 7. Parallel Execution and Independence

JUnit Jupiter does not enable parallel execution by default. Parallel execution can be configured through a `junit-platform.properties` file placed on the test classpath:

```properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=concurrent
```

When parallel execution is enabled, multiple tests or containers can execute concurrently according to configuration. This can shorten runtimes, but it is only safe when tests are independent and resources are properly managed.

Before enabling parallel execution, consider:

- Do tests modify the same record, file, directory, or shared data?
- Does the database have sufficient schema or transaction isolation between tests?
- Do tests use fixed ports, shared servers, or singleton resources?
- Are mutable fixtures shared across multiple test instances?
- Are extensions and mocking libraries safe when used simultaneously by multiple tests?

With Spring TestContext, an ApplicationContext can be cached and reused across tests with compatible configurations. Tests that mutate singleton state in the context or shared data must be explicitly isolated and cleaned up. `@DirtiesContext` can instruct Spring to evict a context from the cache when a test has altered context state; do not use this annotation as a substitute for proper test data management.

## 8. Reporting and Execution Events

The Platform emits events such as test started, test succeeded, failed, skipped, and container finished. Execution tools translate those events into information suited to the environment:

- IDEs update status in the test explorer, displaying durations and stack traces.
- Gradle generates test reports and data for build scans or CI.
- Maven Surefire writes XML and plain-text reports.
- Console Launcher prints results to the terminal.
- Custom tools can use `TestExecutionListener` to log output, collect metrics, or export custom formats.

When reading reports, distinguish between:

| Status | Meaning |
|---|---|
| Successful | The test executed and all assertions passed |
| Failed | The test was executed, but an assertion or exception caused it to fail |
| Aborted | The test was aborted due to a mechanism such as an assumption or execution condition |
| Skipped | The test was not run by decision of the engine or tool, e.g. disabled or excluded by a filter |

Specific displayed status names may vary between IDEs and build tools. When diagnosing issues, inspect the counts of discovered, executed, and skipped tests as well as reasons in the logs; looking only at a "BUILD SUCCESSFUL" line can overlook the fact that no tests actually ran.

## 9. Common Configuration Errors

| Symptom | Common Cause | What to Check |
|---|---|---|
| IDE runs tests, but Gradle reports no tests found | Task has not called `useJUnitPlatform()`, engine is missing, or tests lie outside the source set | Check task configuration, runtime dependencies, and `src/test` paths |
| Maven compiles tests, but does not execute Jupiter | Surefire is too old or the engine dependency is missing from test runtime | Check Surefire version, JUnit BOM, and the `junit-jupiter` dependency |
| `@ParameterizedTest` is not recognized | Missing Jupiter Params or using a dependency that only includes the basic API | Add the `junit-jupiter` aggregate or a compatible `junit-jupiter-params` |
| `@Autowired` in test is `null` or test has no Spring context | SpringExtension is not registered or context configuration is incorrect | Use `@ExtendWith(SpringExtension.class)` and `@ContextConfiguration`, or `@SpringJUnitConfig` |
| JUnit 4 tests stop running after switching to Platform | Vintage Engine was not added or tests still depend on a JUnit 4 runner | Check engines and the migration plan to Jupiter |
| Test does not appear in reports | Tool's selector, tag filter, or include/exclude rules excluded the test | Run a specific class, inspect discovery logs, and review tags/filters |
| `NoSuchMethodError` or runtime compatibility errors | JUnit Platform/Jupiter artifacts have mismatched versions | Use a BOM and inspect the dependency tree to align modules |
| Console Launcher discovers tests, but fails to instantiate them | Classpath is missing application or test runtime dependencies | Add required JARs and verify JDK version |

A useful diagnostic workflow is to check in order: does the test source compile, is the engine on the runtime classpath, does the tool use the Platform, do selectors/filters match the test, and only then examine exceptions thrown during execution.

## 10. Workflow for Setting Up and Running Tests in a Spring Project

When adding JUnit Jupiter to a Spring module, you can follow this sequence:

1. **Identify the build tool and Java version.** Check the Gradle or Maven wrapper and the JDK used for compiling and running tests.
2. **Choose synchronized JUnit versions.** Use the JUnit BOM or existing project dependency management to avoid version mismatches between Platform, Jupiter API, and engine.
3. **Add the engine and API.** Use the `junit-jupiter` dependency or required individual artifacts; ensure the engine is on the test runtime classpath.
4. **Enable JUnit Platform in the build.** For Gradle, configure `useJUnitPlatform()`; for Maven, use a compatible Surefire version.
5. **Run a small test.** Verify that the tool discovers and executes a basic Jupiter test.
6. **Integrate Spring when needed.** Register `SpringExtension` or use `@SpringJUnitConfig`; configure the required context and dependencies.
7. **Categorize tests.** Use tags or separate source sets/tasks for unit tests and integration tests.
8. **Inspect the build tool report.** Check discovered, executed, skipped, and failed counts to confirm the pipeline runs the expected test set.

A minimal Spring Framework test example:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.test.context.junit.jupiter.SpringJUnitConfig;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringJUnitConfig(classes = AccountTestConfiguration.class)
class AccountServiceContextTest {

    @Autowired
    private AccountService accountService;

    @Test
    void injectsServiceFromSpringContext() {
        assertNotNull(accountService);
    }
}
```

The example assumes `AccountTestConfiguration` declares the `AccountService` bean along with any required dependencies. This test verifies integration between Jupiter and Spring TestContext as well as bean injection. To test business behavior, invoke service methods with prepared data and assert specific outcomes.

## 11. Guidelines for Choosing the Right Tool

In daily work, use the IDE to develop and debug individual tests; use the Gradle or Maven wrapper as the execution standard locally and in CI because it is the configuration shared in the repository; use the Console Launcher when you need independent verification of discovery/classpath; and only use the Launcher API directly when genuinely building a custom integration tool.

What matters is that every environment runs the same test model and a compatible set of dependencies. When IDE and CI produce different results, compare the runtime JDK, classpath, engines, selectors, filters, system properties, and Spring context configuration. Differences usually lie in the execution environment or discovery, not in `@Test` changing its meaning between tools.

Once you understand the boundary between the Platform, Jupiter API, Jupiter Engine, and test execution tools, you can trace a test's entire lifecycle: from being written, discovered, having its context prepared by Spring, executed, through to results appearing in the report. This is the foundation for setting up a Spring test suite that runs reliably across IDEs, local builds, and CI.
