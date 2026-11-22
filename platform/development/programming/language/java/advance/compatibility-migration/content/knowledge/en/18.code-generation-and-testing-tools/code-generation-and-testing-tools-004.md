# JUnit, Surefire, Failsafe, and Test Engines by Java Version

When upgrading a Java project from JDK 8 to 11, 17, 21, or higher, the test suite can fail even when business code already compiles successfully. Some cases are Java version incompatibilities in test libraries; others stem from the **JUnit test engine** missing from the runtime classpath, Maven Surefire or Failsafe not picking up the right tests, a plugin executing tests on a different JVM from the compiler JVM, or mocking/coverage frameworks not yet supporting module encapsulation in the target JDK.

Even more dangerous than red test failures is **a green build that runs zero tests**. A project can lose hundreds of test cases when moving from JUnit 4 to JUnit Jupiter, renaming test classes, or upgrading Maven plugins. If a team only looks at `mvn test`'s exit code, it can misjudge post-migration compatibility.

This lesson belongs to the **Code Generation and Testing Tools** chapter of the **Java Advance Compatibility Migration** module. Its content focuses on distinguishing **JUnit framework, JUnit Platform, test engine, Maven Surefire, and Maven Failsafe**, choosing JDK-compatible versions, and building a verification workflow reproducible across multiple environments.

## 1. Learning Objectives

After this lesson, learners can:

- Distinguish JUnit 4, JUnit Jupiter, JUnit Platform, and JUnit Vintage.
- Explain why having the test API without a test engine prevents tests from being discovered/executed properly.
- Understand Maven Surefire's role in the `test` phase and Maven Failsafe's role in integration test phases.
- Choose library, plugin, and Java runtime configurations matching the target JDK version.
- Migrate tests from JUnit 4 to Jupiter step by step without silently losing legacy tests.
- Configure Maven or Gradle to run JUnit Platform while managing test-only dependencies.
- Diagnose `NoClassDefFoundError`, `UnsupportedClassVersionError`, `TestEngine` discovery failures, JPMS reflection errors, and “Tests run: 0” outcomes.
- Organize CI matrices to ensure **the right tests, the right JVM, the right engine, and the right environment**.

## 2. Big Picture: JUnit and Build Tools Do Different Jobs

### 2.1. Four Components in a Test Run

A typical testing flow can be pictured as:

```text
Test code (*.java)
      |
      v
JUnit API: @Test, assertions, lifecycle annotations
      |
      v
JUnit Test Engine: discovers and executes tests
      |
      v
JUnit Platform Launcher / build tool provider
      |
      v
Maven Surefire / Maven Failsafe / Gradle Test / IDE
      |
      v
Test-running JVM, classpath/module path, extensions, mocking, reports
```

This is a conceptual model. In practice, engines, launchers, and providers coordinate via mechanisms specific to each tool version. Keep in mind that **a JUnit annotation does not spawn a test runner by itself**, and Maven Surefire is not a JUnit test engine.

### 2.2. What Is JUnit 4?

JUnit 4 uses familiar APIs:

```java
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class CalculatorTest {
    @Test
    public void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
```

Elements like `@Before`, `@After`, `@RunWith`, `@Rule`, and `@Category` belong to the JUnit 4 ecosystem. Execution tools can use JUnit 4's runner or go through the **JUnit Vintage engine** on JUnit Platform.

JUnit 4 remains present in many legacy codebases. Upgrading the JDK does not automatically force converting every annotation to Jupiter; however, you must verify that runners/providers and older JUnit 4 extensions truly support the target JDK.

### 2.3. What Is JUnit Jupiter?

JUnit Jupiter is JUnit 5's modern programming and execution model, and continues to be used in newer JUnit generations matching the required Java versions.

Example:

```java
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        assertEquals(5, 2 + 3);
    }
}
```

Notable differences:

- The annotation is `org.junit.jupiter.api.Test`, **not** JUnit 4's `org.junit.Test`.
- Regular test classes and methods can be package-private; `public` is not required as in many JUnit 4 cases.
- Lifecycle uses `@BeforeEach`, `@AfterEach`, `@BeforeAll`, and `@AfterAll`.
- Extensions use `@ExtendWith` and the Jupiter Extension API.
- Tests are executed by the **JUnit Jupiter TestEngine** when the launcher finds the right engine.

### 2.4. What Is JUnit Platform?

**JUnit Platform** provides the infrastructure to discover and execute tests via the `TestEngine` model. Platform is not synonymous with Jupiter alone; one launcher can discover and run multiple engines coexisting at runtime.

Commonly referenced components:

| Component | Role |
| --- | --- |
| `junit-jupiter-api` | Annotations, assertions, and APIs used when writing Jupiter tests. |
| `junit-jupiter-engine` | `TestEngine` that discovers and executes Jupiter tests. |
| `junit-jupiter-params` | Support for Jupiter parameterized tests. |
| `junit-platform-launcher` | API enabling tools such as IDEs/build runners to request test discovery and execution. |
| `junit-vintage-engine` | `TestEngine` running JUnit 3/4 tests on JUnit Platform to aid migration. |
| `junit:junit` | JUnit 4 framework, required if tests still import JUnit 4 APIs. |

Artifact names and dependency declarations can differ across JUnit generations. Follow the BOM/guide of the **exact version in use** instead of arbitrarily mixing artifacts across major releases.

### 2.5. Why Distinguish “API” from “Engine”?

Suppose a module has `junit-jupiter-api` on the test compile classpath, so the snippet below compiles:

```java
import org.junit.jupiter.api.Test;

class ExampleTest {
    @Test
    void runs() {}
}
```

However, if the runtime lacks the Jupiter engine or the runner is not configured for JUnit Platform, tests may not run or the launcher may throw a discovery error. Hence:

**“Tests compiled cleanly” does not mean “tests actually executed.”**

Evidence to check includes the count of discovered/executed tests, report outputs, and engine/runner logs.

## 3. Choosing Versions by Java: Checking Multiple Compatibility Layers

### 3.1. Components That May Have Different Minimum Java Levels

A test system typically involves multiple components executing inside the JVM:

1. Application source and class files.
2. Test source and class files.
3. JUnit API/Jupiter engine/Vintage engine.
4. JUnit Platform Launcher.
5. Maven Surefire/Failsafe provider or Gradle Test infrastructure.
6. Mocking/proxy/bytecode libraries such as Mockito, Byte Buddy, and ASM.
7. Coverage and instrumentation agents such as JaCoCo.
8. Integration frameworks, testcontainers, database drivers, and the application under test.

Each component can impose its own minimum Java version. A newer test dependency can stop the test JVM from booting, even if the product itself is still designed to support Java 8.

### 3.2. Rules for Common JUnit Lines

For compatibility orientation:

- **JUnit 4.13.x** belongs to the older framework generation, widely used in Java 8 projects; inspect accompanying runners and extensions when moving to newer JDKs.
- **JUnit 5.x** targets a Java 8 baseline and provides Jupiter/Platform/Vintage, fitting many projects that must preserve Java 8 bytecode while raising the execution JVM.
- **JUnit 6.x** raises the minimum Java requirement to Java 17; do not pick this line if the test runtime must still run on Java 8 or 11.

These milestones describe **JUnit line requirements**, without guaranteeing every related plugin and test library is compatible. When picking a concrete release, check release notes and the Java baseline of **each artifact**. Do not assume a Maven plugin or Mockito version supports the target JDK merely because JUnit does.

### 3.3. Orientation Matrix During Migration

| Test-Running JDK | Common Framework Choice | Items to Check |
| --- | --- | --- |
| Java 8 | JUnit 4 or Java 8-compatible JUnit 5 line | Surefire/provider, Jupiter engine, Java bytecode of plugins/test dependencies. |
| Java 11 | JUnit 4 or JUnit 5.x | Engine discovery, Byte Buddy/Mockito/coverage, APIs removed from the JDK. |
| Java 17 | JUnit 5.x or newer JUnit line with fitting Java baseline | Strong encapsulation, JPMS, JDK agents, reflective access. |
| Java 21+ | JUnit, test frameworks, and tooling versions documented to support that JDK | JaCoCo/ASM/Byte Buddy versions, dynamic agents, class-file version, module access. |

This is an **inspection guide**, not a table of “latest versions.” Exact versions must be locked in the build and verified against the JDK executed by CI.

### 3.4. Java Used for Compiling Differs from Java Used to Run Tests

A build may use JDK 21 to compile code with `--release 11`. Product bytecode then targets Java 11, yet tests may still execute on JDK 21.

Conversely, if a test dependency was compiled for Java 17 while the test-executing JVM is Java 11, the runtime throws:

```text
java.lang.UnsupportedClassVersionError
```

Do not inspect only `maven.compiler.release` to infer which JDK runs Surefire. Confirm **the actual JVM executed by Surefire/Failsafe**, including toolchains and fork configuration.

## 4. Maven Surefire: Running Unit Tests in the `test` Phase

### 4.1. Role of Surefire

The **Maven Surefire Plugin** runs tests configured for the `test` phase of the Maven lifecycle. It uses a provider mechanism to delegate execution to the matching framework, such as JUnit Platform when a test engine exists on the runtime classpath.

Common Maven flow:

```text
validate -> compile -> test-compile -> test -> package -> verify
                                        |
                                        +-- Maven Surefire
                                            (unit tests per configuration)
```

Running:

```bash
mvn test
```

normally runs necessary compile/test-compile steps followed by Surefire. However, it **does not automatically run Failsafe integration tests** as might be hoped unless Failsafe is configured in the project.

### 4.2. Test Class Naming and Inclusion Patterns

Surefire applies common default test naming conventions, such as:

```text
Test*.java
*Test.java
*Tests.java
*TestCase.java
```

Actual patterns apply to compiled test classes. If a team renames all classes to `*IT` or `*Spec` without configuring matching includes, Surefire may run zero tests.

Note: test definitions **discovered by the engine** must still be valid. A class selected by Surefire does not ensure the Jupiter engine finds properly annotated test methods inside it.

### 4.3. Where Are Unit Test Reports Located?

In standard Maven setups, Surefire writes reports under:

```text
target/surefire-reports/
```

These typically include XML test report files and text logs. During migration, do not settle for a green build: check counts of `tests`, `failures`, `errors`, `skipped`, and recorded test names.

### 4.4. Configuring Maven Surefire for Jupiter

Illustrative `pom.xml` using concrete pinned versions (not a “latest” recommendation):

```xml
<properties>
    <maven.compiler.release>11</maven.compiler.release>
    <junit.version>5.11.4</junit.version>
    <surefire.version>3.5.2</surefire.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.junit.jupiter</groupId>
        <artifactId>junit-jupiter</artifactId>
        <version>5.11.4</version>
        <scope>test</scope>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
```

`junit-jupiter` is the aggregator artifact in the JUnit 5 line, bringing in matching Jupiter components according to that version's metadata. With other dependency layouts, explicitly declare `junit-jupiter-engine` for test runtime.

Version numbers here illustrate a concrete setup; in real projects, select Maven plugin and JUnit versions verified against your current JDK/CI, pin them in version management, and inspect the dependency tree.

### 4.5. Maven Providers and Engine Discovery

Surefire 3.x normally supports running JUnit Platform when properly configured. Actual provider selection depends on version and test classpath. Verify:

- `junit-platform` infrastructure and test engine are present at matching versions.
- `org.junit.jupiter:junit-jupiter-engine` resolves into runtime via dependencies.
- No conflicting JUnit Platform/Jupiter versions exist from dependency mediation.
- Test classes match Surefire includes/excludes.
- No tag/engine filters exclude all tests.
- Forked JVMs receive the right classpath/module path.

If the engine is missing, adding `@Test` annotations in source will not fix execution.

## 5. Maven Failsafe: Running Integration Tests and Gating in `verify`

### 5.1. Why Is There a Separate Failsafe Plugin?

The **Maven Failsafe Plugin** is designed for integration tests that may require the packaged artifact, databases, containers, or auxiliary services provisioned earlier in the lifecycle.

Typically the plugin binds two goals:

- `failsafe:integration-test`: runs integration tests.
- `failsafe:verify`: reads results and fails the build on configured test errors.

Typical flow:

```text
package
  |
  v
pre-integration-test -> prepare infrastructure if configured by project
  |
  v
integration-test -> Failsafe executes integration tests
  |
  v
post-integration-test -> tear down infrastructure if configured by project
  |
  v
verify -> Failsafe checks results and marks build failed
```

Merely naming files `*IT` does not make Maven run integration tests automatically; bind the plugin and lifecycle phases properly.

### 5.2. Why Run `mvn verify`?

Example:

```bash
mvn verify
```

When Surefire and Failsafe are configured correctly, this runs the necessary phases and checks integration test outcomes during `verify`.

**Do not use standalone `mvn integration-test` as a final quality gate** while assuming Failsafe results were fully checked: the `verify` goal is what aggregates fail/pass as designed while letting post-integration-test cleanup steps execute in the proper lifecycle order.

### 5.3. Failsafe Test Naming Conventions

Common default patterns:

```text
IT*.java
*IT.java
*ITCase.java
```

If integration tests are named `OrderIntegrationTest`, declare matching includes or adjust naming conventions so Failsafe detects them.

Avoid overlaps between Surefire and Failsafe causing the same test to execute twice unintentionally.

### 5.4. Example Failsafe Setup with Jupiter

```xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-surefire-plugin</artifactId>
      <version>3.5.2</version>
    </plugin>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-failsafe-plugin</artifactId>
      <version>3.5.2</version>
      <executions>
        <execution>
          <goals>
            <goal>integration-test</goal>
            <goal>verify</goal>
          </goals>
        </execution>
      </executions>
    </plugin>
  </plugins>
</build>
```

The JUnit Jupiter engine comes from the project's test dependencies, not automatically from declaring Failsafe. If integration tests need infrastructure access, configure startup, readiness waits, and cleanup in the appropriate lifecycle phases.

Common report directories:

```text
target/surefire-reports/
target/failsafe-reports/
```

During migration, record unit test and integration test counts separately instead of merging them into one vague number.

## 6. Special Concern: Coexistence of JUnit 4, Jupiter, and Vintage

### 6.1. JUnit 4 Tests Do Not Automatically Become Jupiter Tests

Legacy test:

```java
import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class LegacyMathTest {
    private Calculator calculator;

    @Before
    public void setUp() {
        calculator = new Calculator();
    }

    @Test
    public void adds() {
        assertEquals(4, calculator.add(1, 3));
    }
}
```

Switching dependencies to `junit-jupiter-api` while keeping `org.junit.Test` does not make the Jupiter engine execute this test. JUnit 4 and Jupiter APIs are two distinct annotation sets.

Three paths exist:

1. Keep the JUnit 4 runner/provider during the transition phase.
2. Use the **JUnit Vintage engine** to execute JUnit 4 tests on JUnit Platform.
3. Migrate tests incrementally to Jupiter and drop Vintage once finished.

### 6.2. What Is the Vintage Engine For?

Vintage is a `TestEngine` allowing JUnit Platform to run JUnit 3/4 tests. For example, a mixed project might declare:

```xml
<dependency>
    <groupId>junit</groupId>
    <artifactId>junit</artifactId>
    <version>4.13.2</version>
    <scope>test</scope>
</dependency>

<dependency>
    <groupId>org.junit.vintage</groupId>
    <artifactId>junit-vintage-engine</artifactId>
    <version>5.11.4</version>
    <scope>test</scope>
</dependency>
```

This example assumes remaining Jupiter/Platform components share the matching compatible release line. Never mix a Vintage engine from one major version with Jupiter/Platform from another without verifying compatibility.

In newer JUnit lines, Vintage availability or support status may change; review release notes when picking versions. Vintage is a **transitional** bridge, not a goal for keeping JUnit 4 forever.

### 6.3. Warning When One Class Uses Annotations from Both Frameworks

A single class importing both `org.junit.Test` and `org.junit.jupiter.api.Test` easily causes confusion: some methods are discovered by Vintage, others by Jupiter, while lifecycle annotations may fail to match the active engine.

For instance, JUnit 4's `@Before` is not Jupiter's `@BeforeEach`. If a Jupiter test method expects fixtures set up by `@Before`, the test can fail even though sources compile cleanly.

Migrate **class by class** or by clear test suites rather than mechanically rewriting half a class and hoping the runner guesses correctly.

### 6.4. JUnit 4 to Jupiter Mapping Table

| JUnit 4 | JUnit Jupiter | Key Points to Note |
| --- | --- | --- |
| `org.junit.Test` | `org.junit.jupiter.api.Test` | Two distinct annotations. |
| `@Before` | `@BeforeEach` | Lifecycle before each test. |
| `@After` | `@AfterEach` | Lifecycle after each test. |
| `@BeforeClass` | `@BeforeAll` | Requires static or `PER_CLASS` lifecycle depending on configuration. |
| `@AfterClass` | `@AfterAll` | Same class-level lifecycle rules. |
| `@Ignore` | `@Disabled` | Verify reason strings and skipped test reporting. |
| `@RunWith` | `@ExtendWith` or corresponding engine mechanism | Not every runner converts 1:1 into an extension. |
| `@Category` | `@Tag` | Update Surefire/CI filters accordingly. |
| `@Rule` / `@ClassRule` | Extension API or compatible library | No automatic mapping exists for every rule. |
| `@Test(expected=...)` | `assertThrows(...)` | Tighten scope of the code expected to throw. |
| `@Test(timeout=...)` | `assertTimeout` / `assertTimeoutPreemptively` | Preemptive timeouts may run code on another thread, affecting thread-locals/transactions. |

Changing test frameworks can shift semantics. Inspect test logic, lifecycles, extension ordering, and reporting rather than running a blind import find-and-replace and calling migration done.

## 7. Controlled Migration of a Test to Jupiter

### 7.1. Before Migration

```java
import org.junit.Before;
import org.junit.Test;
import static org.junit.Assert.assertEquals;

public class OrderTotalTest {
    private OrderCalculator calculator;

    @Before
    public void init() {
        calculator = new OrderCalculator();
    }

    @Test
    public void calculatesTotal() {
        assertEquals(120, calculator.total(100, 20));
    }
}
```

### 7.2. After Migration

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class OrderTotalTest {
    private OrderCalculator calculator;

    @BeforeEach
    void init() {
        calculator = new OrderCalculator();
    }

    @Test
    void calculatesTotal() {
        assertEquals(120, calculator.total(100, 20));
    }
}
```

Here, conversion is straightforward because the test relies only on a simple instance fixture. With custom runners, rules, concurrency, parameterized tests, or Spring contexts, add corresponding extensions/configurations and verify impact.

### 7.3. Testing Exceptions and Timeouts

JUnit 4 can use:

```java
@Test(expected = IllegalArgumentException.class)
public void rejectsInvalidInput() {
    service.process(null);
}
```

Jupiter typically uses:

```java
@Test
void rejectsInvalidInput() {
    assertThrows(IllegalArgumentException.class,
        () -> service.process(null));
}
```

The second approach narrows the exact call expected to throw, reducing false passes where fixture setup accidentally throws the same exception.

For timeouts, choosing between `assertTimeout` and `assertTimeoutPreemptively` affects thread-locals, transaction contexts, and cancellation. Never alter timeout semantics without testing.

### 7.4. Parameterized Tests

JUnit Jupiter supports parameterized tests via `junit-jupiter-params`:

```java
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;
import static org.junit.jupiter.api.Assertions.assertEquals;

class DiscountTest {
    @ParameterizedTest
    @CsvSource({
        "100, 10, 90",
        "200, 20, 160"
    })
    void appliesDiscount(int price, int discount, int expected) {
        assertEquals(expected, price - (price * discount / 100));
    }
}
```

For the engine to discover this test, compatible API/params/engine artifacts are required. The `junit-jupiter` aggregator usually includes them; when declaring artifacts individually, ensure `junit-jupiter-params` is not omitted.

## 8. Maven: Complete Transition-Phase Configuration

Suppose a Java 11 project still contains both JUnit 4 and Jupiter tests. Illustrative setup:

```xml
<project>
  <modelVersion>4.0.0</modelVersion>
  <groupId>com.example</groupId>
  <artifactId>legacy-migration</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>11</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.junit.jupiter</groupId>
      <artifactId>junit-jupiter</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>junit</groupId>
      <artifactId>junit</artifactId>
      <version>4.13.2</version>
      <scope>test</scope>
    </dependency>
    <dependency>
      <groupId>org.junit.vintage</groupId>
      <artifactId>junit-vintage-engine</artifactId>
      <version>5.11.4</version>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-compiler-plugin</artifactId>
        <version>3.13.0</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.5.2</version>
      </plugin>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-failsafe-plugin</artifactId>
        <version>3.5.2</version>
        <executions>
          <execution>
            <goals>
              <goal>integration-test</goal>
              <goal>verify</goal>
            </goals>
          </execution>
        </executions>
      </plugin>
    </plugins>
  </build>
</project>
```

This is a **fixed-version example configuration**, not a set of versions guaranteed to suit every project or be the newest at reading time. Especially if the target JDK is not Java 11, re-verify plugin compatibility and Java baselines.

Once all JUnit 4 tests are migrated, remove JUnit 4 and Vintage dependencies as planned only after confirming no runner/extension/engine still relies on them.

## 9. Gradle: `useJUnitPlatform()` and Runtime Engines

### 9.1. Basic Jupiter Setup

Gradle Groovy DSL example:

```groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

`useJUnitPlatform()` tells Gradle to use JUnit Platform to discover/run tests. It does not automatically supply every required engine dependency. `junit-jupiter` pulls in Jupiter components per dependency metadata, while `junit-platform-launcher` must align with the compatible Platform generation.

Here the toolchain uses JDK 17 while `junit-jupiter` belongs to the Java 8-baseline line; choose a JDK toolchain aligning with application targets.

### 9.2. When JUnit 4 Tests Exist

To use Vintage during transition:

```groovy
dependencies {
    testImplementation 'junit:junit:4.13.2'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.vintage:junit-vintage-engine:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
```

Without Vintage or a separate JUnit 4 runner, legacy tests can silently stop running when switching tasks to JUnit Platform.

### 9.3. Gradle Does Not Include Failsafe Out of the Box

Surefire and Failsafe are **Maven plugins**, not built-in Gradle tasks. In Gradle, integration tests are typically configured via a separate source set or JVM test suite, with a `Test` task configuring its runtime classpath and `useJUnitPlatform()`.

Conceptual example:

```groovy
tasks.register('integrationTest', Test) {
    useJUnitPlatform()
    // Configure testClassesDirs, classpath, dependencies, and lifecycle
    // per the project's source set or JVM test suite.
}
```

This snippet alone will not execute integration tests unless the source set/test suite and dependencies exist. You cannot substitute a same-named Gradle task for `mvn verify` if the project has not declared the full task setup.

## 10. How Are JUnit Test Engines Discovered?

### 10.1. `TestEngine` Is a Platform Plugin

JUnit Platform defines the `org.junit.platform.engine.TestEngine` API. Engines implement this API to discover and execute tests in their own programming model.

On a traditional classpath, engines are typically discovered via Java's `ServiceLoader` mechanism and metadata under `META-INF/services`. On the module path, discovery also depends on `provides`/`uses`, module resolution, and classloaders.

Consequently, operations like shading, relocation, minimization, or fat-JAR creation can strip resources/providers required for test engines.

### 10.2. Missing Engine, Wrong Engine, or Version Conflicts

Different failure modes must be classified:

| Situation | Possible Symptoms |
| --- | --- |
| Only Jupiter API present, missing Jupiter engine | No matching engine found, or tests fail to run as expected. |
| Incompatible mixed Platform versions at runtime | `NoSuchMethodError`, `NoClassDefFoundError`, or engine discovery failures. |
| Vintage present yet JUnit 4 missing or engine incompatible | Errors discovering/running legacy tests. |
| `META-INF/services` metadata dropped during shading | Launcher cannot see the engine/provider. |
| Engine present yet test classes excluded | Build runs 0 tests in that scope. |
| Engines filtered via include/exclude engine or tags | Only a subset of tests runs. |

Investigate by inspecting the **test runtime classpath**, service metadata, plugin providers, engine selection, and reports rather than guessing another dependency to add.

### 10.3. Engine IDs and Grouping

Jupiter and Vintage have distinct engine IDs (typically `junit-jupiter` and `junit-vintage`, respectively). Launchers/runners may allow including or excluding specific engines.

Enabling a Jupiter-only filter while JUnit 4 tests remain can turn reports green while dropping every legacy test. Disable Vintage only after confirming legacy tests have been migrated or intentionally decommissioned.

## 11. Newer JDKs Impact Mockito, Byte Buddy, ASM, and JaCoCo

### 11.1. JUnit Is Not the Only Source of Test Failures

A simple test using only `assertEquals` may pass while tests involving mocking or bytecode instrumentation fail on a newer JDK. Frequent culprits include dependencies on:

- Mockito and inline mocking.
- Byte Buddy or ASM for reading/generating classes.
- JaCoCo coverage agents.
- Spring Test, Hibernate, CDI, or proxy-generating frameworks.
- Annotation processors or generated test fixtures.
- Testcontainers and other integration libraries.

These tools touch class-file formats, reflection, Java agents, or APIs that evolve across JDKs.

### 11.2. `UnsupportedClassVersionError`

Example when the test JVM is older than the class-file version:

```text
UnsupportedClassVersionError:
  ... has been compiled by a more recent version of the Java Runtime
```

This is not a JUnit annotation bug. Compare the Java class-file versions of application code, tests, engines, and plugins against the executing JDK.

A project compiled with JDK 21 using `--release 11` yet using a Java 17-only test dependency still cannot run tests on Java 11.

### 11.3. Byte Buddy or ASM Errors on Newer Class Files

Some libraries report unsupported class-file versions for the target JDK or recommend upgrading Byte Buddy/ASM. When that occurs, do not throw random `--add-opens` flags at the JVM; upgrade the dependency parsing/generating bytecode.

Note that such dependencies often arrive **transitively** via Mockito or other frameworks. Inspect the dependency tree to see the actual resolved version.

### 11.4. JaCoCo and Code Coverage

On a JDK upgrade, JaCoCo must support the new class-file version and instrumentation mechanics. An outdated JaCoCo release can fail right as the test JVM starts or when its agent instruments newer classes.

In Maven, the JaCoCo plugin typically puts its Java agent into property `argLine`; Surefire/Failsafe must receive and forward that value to forked JVMs. If manual `argLine` settings overwrite instead of appending/merging it, coverage can silently vanish even though tests pass.

Never assume 0% coverage means code did not run; the agent may simply not be attached properly.

### 11.5. Java Agents and Dynamic Attach

Mocking/instrumentation tools may rely on Java agents or dynamic JVM attach. Recent JDK releases issue warnings or tighten restrictions on dynamic agent loading. Check your target JDK policy, Mockito/Byte Buddy/JaCoCo versions, and framework guidance.

When an agent is needed, configure it via supported mechanisms rather than adding flags just to suppress warnings without understanding root causes.

## 12. JPMS, Reflection, and the Module Path When Running Tests

### 12.1. When Test Modules Run on the Module Path

If the application uses `module-info.java`, Surefire or Gradle may place tests on the module path with module patching. Tests are then governed by JPMS rules on:

- Module readability.
- Package exports.
- Package opens.
- Whether test classes share the same package/module as production classes.
- Whether runtime engines/launchers resolve and read the module cleanly.

A test can pass on the classpath yet fail on the module path. Never treat IDE classpath runs as proof that modular CI runs work.

### 12.2. `InaccessibleObjectException`

Reflection/mocking frameworks often access non-public fields or constructors. On modern JDKs, missing `opens` or `--add-opens` triggers:

```text
java.lang.reflect.InaccessibleObjectException:
  module ... does not "opens ..." to ...
```

Prefer upgrading the framework or updating module descriptors when you own the module. Only apply targeted `--add-opens` during a controlled transition when truly needed.

Illustrative classpath test JVM flag:

```text
--add-opens java.base/java.lang=ALL-UNNAMED
```

Do not apply this flag blindly across every project. It grants broad access to unnamed modules and does not fix class-file format errors or engine discovery failures.

### 12.3. Which JVM Receives the Flag?

In Maven Surefire, `argLine` typically passes JVM arguments to the forked test JVM:

```xml
<plugin>
  <groupId>org.apache.maven.plugins</groupId>
  <artifactId>maven-surefire-plugin</artifactId>
  <version>3.5.2</version>
  <configuration>
    <argLine>
      --add-opens java.base/java.lang=ALL-UNNAMED
    </argLine>
  </configuration>
</plugin>
```

This merely illustrates configuration placement. If the project uses JaCoCo or other JVM arguments, merge `argLine` properly rather than overwriting it. For Failsafe, inspect integration test JVM settings separately.

Do not pass runtime flags to the compiler plugin expecting them to propagate to the test JVM. They are separate processes/contexts.

### 12.4. `useModulePath` and Workarounds

Some Surefire versions support `useModulePath` to control whether tests execute on the module path or classpath. Forcing everything back onto the classpath can serve as a temporary migration workaround, yet risks masking real module-path bugs that production will hit.

Record the architecture decision explicitly: does the system ship on the classpath or the module path? Your test pipeline should mirror the supported deployment layout.

## 13. False-Green Tests When Zero Tests Execute

### 13.1. Why Is This a Major Risk?

Suppose before migration:

```text
Tests run: 842, Failures: 0, Errors: 0, Skipped: 7
```

After changing JUnit/providers:

```text
Tests run: 0, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

If the pipeline only checks the exit code, it can greenlight an unverified Java release.

Common causes include:

- Surefire includes no longer match class names.
- Test classes moved to an uncompiled directory/source set.
- Only Jupiter API exists while the engine is absent from test runtime.
- Dropping Vintage caused JUnit 4 tests to vanish.
- Tag/engine filters excluded all tests.
- Build profiles inadvertently skipped tests.
- CI ran a different Maven/Gradle task from what was intended.

### 13.2. How to Prevent It

Establish at least three layers of evidence:

1. **Report presence:** XML/test result reports exist in every module expected to contain tests.
2. **Test count:** executed test count does not drop abruptly without explanation.
3. **Known sentinel test:** a simple baseline test definitely gets discovered; if missing, fail the pipeline.

When writing policy rules, remember pure BOM or utility-packaging modules may **intentionally contain zero tests**. Set count thresholds per module rather than mechanically forcing every module to run at least one test.

### 13.3. `failIfNoTests`

Surefire/Failsafe provide options controlling behavior when no tests are found. Example for modules required to have unit tests:

```xml
<configuration>
    <failIfNoTests>true</failIfNoTests>
</configuration>
```

Apply within the appropriate scope while still inspecting report counts and active engines. This option does not replace checking filters, skips, or partial mismatches where a build still thinks everything is valid.

### 13.4. Count More Than Just Test Classes

A single test class may produce many parameterized invocations or dynamic tests. Execution counts reported in XML may differ from raw `@Test` method counts or `*Test.java` file counts.

When establishing a baseline, state the exact metric tracked by CI (test cases, containers, invocations, or report counts) so comparisons stay consistent.

## 14. Inspecting Real Maven/CI Environments

### 14.1. Checking Java and Maven

On the workstation or CI agent:

```bash
java -version
javac -version
mvn -version
```

These commands show the ambient JDK/JRE and Maven binaries. However, Maven toolchains or forked test setups may use another JDK, so also inspect plugin logs and fork configuration to identify the JVM executing tests.

### 14.2. Maven Toolchains

When supporting multiple JDKs, Maven Toolchains can separate the JVM running Maven from the JDK chosen by plugins. Not every plugin or setup honors the same toolchain automatically.

If CI reports “tested on Java 11,” verify:

- Which JDK ran Maven.
- Which JDK the compiler plugin picked.
- Which JDK Surefire/Failsafe used for the test JVM.
- Which JDK containers or spawned processes in integration tests used.
- Which JDK ran the application under test.

### 14.3. Suggested Build Matrix

Example for a product supporting Java 11, 17, and 21:

| Stage | JDK | Activity | Pass Criteria |
| --- | --- | --- | --- |
| Baseline | JDK 11 | Compile and unit tests at Java baseline | No APIs outside supported release; all tests run. |
| Compatibility | JDK 17 | Unit and integration tests | Engine, mocking, reflection, and data flows behave properly. |
| Target | JDK 21 | Full verify, coverage, core feature testing | No dropped tests, tooling supports class files/JDK, no runtime errors. |

If distributing strictly for Java 17+, adjust the matrix to match commitments. Avoid running every JDK arbitrarily just because it exists: each CI job should have an explicit purpose.

### 14.4. Testcontainers and External Services

Integration tests may depend on Docker, databases, queues, ports, timezones, locales, and TLS. Changing JDKs or CI base images can change these environmental factors too.

To separate test infrastructure failures from application failures:

- Record image versions, service versions, and configs.
- Use proper readiness/health checks.
- Avoid relying solely on fixed `sleep` delays.
- Manage post-test cleanup reliably.
- Collect logs from failed services.
- Archive reports from both Surefire and Failsafe.

## 15. Diagnostic Workflow When Tests Fail to Run or Fail Execution

### Step 1: Capture Pre-Migration Baseline

Record JDK, Maven/Gradle, Surefire/Failsafe, JUnit Platform/Jupiter/Vintage versions, test runtime dependencies, test counts per module, and sample reports.

### Step 2: Identify Existing Test Types

Search source imports:

```text
org.junit.Test                  (JUnit 4)
org.junit.jupiter.api.Test      (Jupiter)
org.junit.jupiter.params.*      (Parameterized Jupiter)
org.junit.runner.RunWith        (JUnit 4 runner)
org.junit.jupiter.api.extension (Jupiter extension)
```

Account for integration frameworks and extra test engines. A codebase may contain more than two test styles.

### Step 3: Verify Test Classes Compile

Ensure `src/test/java` or actual test source sets compile cleanly. Inspect compile errors, excludes, generated test sources, and compiled test output classes.

### Step 4: Verify Engines on the Test Runtime Classpath

With Maven:

```bash
mvn dependency:tree -Dscope=test
```

With Gradle:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

Check for JUnit Jupiter engine, Vintage if needed, Platform Launcher, and conflicting versions.

### Step 5: Inspect Surefire/Failsafe Versions and Configuration

Review includes/excludes, providers, test selection, tags, engine filters, fork settings, `argLine`, `useModulePath`, toolchains, and profiles.

Do not rely only on parent POM declarations if child modules override them.

### Step 6: Run a Small Targeted Scope Confirming Test Counts

Example:

```bash
mvn -Dtest=CalculatorTest test
```

In Gradle:

```bash
./gradlew test --tests com.example.CalculatorTest
```

Pick a test with a clear name and framework. If a test runs individually yet disappears in the full suite, check filters/includes, engine configuration, or cross-module interactions.

### Step 7: Inspect Test JVM and Bytecode/Reflection Errors

On `UnsupportedClassVersionError`, match class-file version against the runtime JVM. On `InaccessibleObjectException`, find the module/package requiring `opens` and the reflecting framework. On engine discovery failures, inspect the root cause in stack traces rather than blindly adding JVM flags.

### Step 8: Run `verify` and Check Reports and Coverage

In Maven projects binding Failsafe:

```bash
mvn clean verify
```

Inspect Surefire reports, Failsafe reports, coverage, and integration service logs. A passing build is insufficient if test counts dropped unexpectedly.

### Step 9: Lock Versions and Update CI

Lock plugin/dependency versions, toolchains, source/target releases, test runtimes, verification reports, and review schedules for `--add-opens` workarounds.

## 16. Common Failure Matrix When Upgrading JDK and Test Tooling

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `Tests run: 0` | Tests fail includes, missing engine, skips/filters, or wrong source set. | Check names, `testRuntimeClasspath`, filters, and reports. |
| Jupiter tests compile yet do not run | Wrong or missing JUnit Platform provider/engine. | Add matching engine/launcher, upgrade plugin, verify discovery. |
| JUnit 4 tests vanish after enabling Jupiter | Missing Vintage or JUnit 4 runner. | Use Vintage for transition or migrate tests to Jupiter. |
| `UnsupportedClassVersionError` | Test engine/dependency/class built for higher JDK than test JVM. | Verify Java baseline of each artifact and runtime. |
| `NoSuchMethodError` in JUnit Platform | Version mismatch across Platform/Jupiter/plugin components. | Align versions via BOM and inspect dependency mediation. |
| `NoClassDefFoundError` | Missing test runtime dependency or incompatible version. | Check test scope and classpath/module path. |
| `ServiceConfigurationError` | Broken or shaded-away engine/provider metadata. | Inspect `META-INF/services`, packaging, and provider discovery. |
| `InaccessibleObjectException` | Framework reflecting into unopened package. | Upgrade framework; add minimal targeted opens if necessary. |
| Mockito/mocking fails on newer JDK | Byte Buddy/agent/Mockito lacks JDK/class-file support. | Upgrade dependencies and verify the test JVM. |
| JaCoCo crashes or skips instrumentation | Outdated agent or overwritten `argLine`. | Upgrade JaCoCo, verify agent args and reports. |
| Unit tests pass, ITs do not run | Failsafe unbound or CI runs only `mvn test`. | Configure Failsafe and invoke `mvn verify`. |
| ITs run yet CI passes despite errors | Failsafe `verify` skipped or results mishandled. | Execute lifecycle through `verify` and check XML outputs. |
| Passes in IDE, fails in Maven | IDE uses different runner/JDK/classpath. | Align JVM, dependencies, engines, module path, and filters. |
| Fails only on CI | Different toolchain, locale, Docker, services, or environment. | Record environment details and reproduce on matching JVM/service runtime. |

## 17. Version Policy and Dependency Management

### 17.1. Use a Consistent Set of JUnit Versions

Jupiter, Vintage, and Platform components must align according to that JUnit generation's version scheme. Particularly in JUnit 5, Jupiter/Vintage versions and Platform versions follow paired series that must match cleanly.

A common approach is adopting the **JUnit BOM** for the chosen release or the dependency management published by frameworks like Spring Boot, rather than pinning some artifacts manually while letting others resolve arbitrarily.

Never patch a single dependency version for a `ClassNotFoundException` without reviewing the full dependency graph.

### 17.2. Pin Compatible Maven Surefire and Failsafe Versions Together

Surefire and Failsafe can be configured in the parent POM's `pluginManagement`. Pick versions verified on the target JDK and avoid module A running an older Surefire while module B uses an upgraded version.

Many organizations pin matching versions for Surefire and Failsafe to keep provider selection and runtime behavior predictable. That is a sensible practice, though real project configurations must still be tested.

### 17.3. Pin Other Test Tooling

Do not overlook:

- Mockito and Byte Buddy.
- JaCoCo and other agents.
- Spring Test and integration frameworks.
- Testcontainers and client libraries.
- Transitive ASM or bytecode tools.
- Compiler plugins and Kotlin/Scala/Groovy compilers if present.
- Maven/Gradle wrappers and JDK toolchains.

On a JDK upgrade, any one of these can break independently. Migration records should capture before/after versions and upgrade rationale.

## 18. Mini-Lab: Catching Silently Dropped Test Suites

### 18.1. Problem Statement

A project has:

```text
src/test/java/com/example/LegacyAccountTest.java
src/test/java/com/example/NewOrderTest.java
src/test/java/com/example/InventoryIT.java
```

- `LegacyAccountTest` uses `org.junit.Test`.
- `NewOrderTest` uses `org.junit.jupiter.api.Test`.
- `InventoryIT` uses Jupiter and requires a test database.

The project recently upgraded from JDK 8 to JDK 17 and adopted JUnit Platform. Running `mvn test` outputs `BUILD SUCCESS` yet executes only `NewOrderTest`.

### 18.2. Analysis

Without the Vintage engine or a matching runner, `LegacyAccountTest` disappears from discovery. Meanwhile, `InventoryIT` follows Failsafe's naming pattern and is not included by Surefire during `mvn test`.

So seeing only `NewOrderTest` does not mean the other two files failed compilation:

- The legacy test requires Vintage or conversion to Jupiter.
- The integration test requires Failsafe configuration and running through `verify`.

### 18.3. Resolution Steps

1. Add a compatible Vintage engine to preserve JUnit 4 tests during migration, or migrate `LegacyAccountTest` to Jupiter.
2. Bind Failsafe `integration-test` and `verify`, verifying `InventoryIT` is picked up.
3. Execute `mvn clean verify` on JDK 17.
4. Read Surefire/Failsafe XML reports and verify **all three test groups** ran.
5. Remove Vintage only once every in-scope JUnit 4 test has a verified replacement path.

### 18.4. Mini-Lab Completion Criteria

Expected proof goes beyond `BUILD SUCCESS`. Reports must show:

- Exact JDK, plugin, and engine versions used.
- Which tests ran under Jupiter vs Vintage (while retained).
- Test counts in Surefire vs Failsafe.
- Integration environment readiness status.
- Confirmation no test was silently dropped by unintended filters or config.

## 19. Checklist Before Finalizing Test Tooling Migration

- [ ] Recorded the JVM executing Maven/Gradle, compiler JDK, and test JVM.
- [ ] Identified Java baselines for JUnit, plugins, engines, and test dependencies.
- [ ] Categorized JUnit 4, Jupiter, parameterized, dynamic, and integration tests.
- [ ] Verified compatible Jupiter engine and Platform Launcher exist at test runtime when using Jupiter.
- [ ] Kept Vintage or a JUnit 4 runner while legacy tests remain.
- [ ] Checked that `org.junit.Test` and `org.junit.jupiter.api.Test` are not mixed improperly.
- [ ] Aligned plugin/dependency versions across modules.
- [ ] Verified includes/excludes, tags, engine filters, and test source sets.
- [ ] Configured Surefire for unit tests and Failsafe for integration tests when using Maven.
- [ ] Executed the lifecycle through `verify` to evaluate Failsafe results.
- [ ] Compared XML reports, executed counts, and skipped counts before and after migration.
- [ ] Evaluated `failIfNoTests` or equivalent quality gates for modules required to contain tests.
- [ ] Upgraded Mockito/Byte Buddy/ASM/JaCoCo to versions supporting the target JDK.
- [ ] Documented required `--add-opens`/`argLine` settings without opening packages unconditionally.
- [ ] Tested JPMS/module path behavior if the application runs modularly.
- [ ] Verified CI matrices and external services used by integration tests.
- [ ] Documented rationale for any deleted, disabled, or temporarily skipped tests.
- [ ] Saved baseline records and rollback steps in case build/test infrastructure changes must be reverted.

## 20. Conclusion

**JUnit** supplies the test programming model and **test engines**; **JUnit Platform** connects engines with launchers; **Maven Surefire** and **Maven Failsafe** determine which tests execute across different Maven lifecycle phases. Upgrading the JDK therefore requires verifying JUnit APIs, engines, build plugins, test JVMs, mocking/coverage libraries, and test discovery configuration together.

In Java Advance Compatibility Migration, the key metric is not merely a “green build,” but **the right test suite discovered, executed by the proper engine, on the target JDK, with reliable reports and integration environments**. When test counts, tool versions, Java toolchains, and runtime results are tracked transparently, your test suite becomes genuine proof of post-upgrade compatibility.
