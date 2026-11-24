# Tests Not Discovered Due to Engine, Classpath, Naming, or Filters

## 1. Symptom: BUILD SUCCESSFUL Yet No Tests Executed

In the **Spring Boot - testing** module, under **Test Troubleshooting**, a dangerous issue occurs when a project has test sources and the IDE sees `@Test` methods, yet the CI command executes zero cases. The build may complete without actually testing any behavior; or only one subset of tests runs while another subset is silently skipped.

Common examples:

- `import org.junit.jupiter.api.Test` is present and the source compiles, but **JUnit Jupiter TestEngine** is missing at runtime.
- Gradle uses `testImplementation 'spring-boot-starter-test'` but omits `useJUnitPlatform()`.
- Files live under `src/integrationTest/java`, while the project only configures the default `test` source set.
- A JUnit 4 class uses `org.junit.Test` while the test task only enables the Jupiter engine, **without JUnit Vintage**.
- Maven Surefire does not pick up `InvoiceSpec.java` under its default naming patterns.
- Tests are discovered, but `@Disabled` or a condition disables them before execution.
- Gradle `--tests`, `includeTags`, `excludeTags`, or file/class include/exclude patterns filter out all tests.
- Task `:moduleA:test` is running, while the tests reside in `moduleB`.
- Gradle reports `UP-TO-DATE` or `FROM-CACHE`: the task did not re-run in the current invocation, which is not proof that "there are no tests."
- The IDE uses a different runner/JDK/classpath than Gradle or Maven, so the two environments see different test sets.

**Goal:** pinpoint the exact stage where tests disappear: source -> compilation -> test runtime classpath -> launcher/engine -> discovery -> filtering -> execution -> report. Do not attempt to fix this by adding `@SpringBootTest` to every class or blindly disabling filters.

This guide uses **Java 17, Spring Boot 3.3.0, Gradle 8.x, JUnit Jupiter 5, and JUnit Platform** for the runnable example; it also includes guidance for **Maven Surefire** and JUnit 4 Vintage. The hands-on section includes positive tests (real tests that execute) and negative diagnostics (misconfigurations shown separately, **not placed in the runnable source**). We distinguish **expected outcomes** from actual executed Gradle/JUnit results.

## 2. Learning Objectives

After this lesson, you will be able to:

1. Distinguish between a test **present in source**, **compiled**, **discovered**, **selected**, **executed**, and **passed**.
2. Recognize that the `@Test` API and the runtime **TestEngine** belong to two separate layers.
3. Explain the three parts: `JUnit Platform`, `JUnit Jupiter`, and `JUnit Vintage`.
4. Understand the role of the JUnit Platform Launcher and the Gradle/Maven/IDE test runners.
5. Use `org.junit.jupiter.api.Test` properly for JUnit Jupiter.
6. Know why JUnit 4 `org.junit.Test` requires Vintage when running via the Platform.
7. Configure `useJUnitPlatform()` and `junit-platform-launcher` in Gradle.
8. Inspect `testRuntimeClasspath`, `testCompileClasspath`, and the dependency tree to locate missing or mismatched engine versions.
9. Check compiled outputs in `build/classes/java/test` and the Gradle `test` source set.
10. Distinguish **Maven Surefire** test naming rules from JUnit Platform/Gradle.
11. Know that JUnit Jupiter test classes/methods do not need to be `public`, but must not be `private`.
12. Write non-`static`, non-value-returning `@Test` methods; know the `@TestFactory` exception that returns dynamic tests.
13. Use `@ParameterizedTest` and `@CsvSource`, and understand that one method produces multiple invocations.
14. Use `@Nested` correctly: a non-static inner class annotated with `@Nested`.
15. Recognize that `@Disabled`/conditions are **skipped after selection/discovery**, not a missing engine.
16. Differentiate include/exclude tags from the Gradle `--tests` filter, and know how to isolate each layer.
17. Understand test task statuses: `UP-TO-DATE`, `NO-SOURCE`, `SKIPPED`, `FROM-CACHE`, and `FAILED`.
18. Use `--info`, `--rerun-tasks`, `--tests`, and XML/HTML reports to investigate.
19. Diagnose Maven Surefire `-Dtest`, naming includes, skip flags, and plugin versions.
20. Verify custom `integrationTest` tasks, source sets, classpaths, and dependencies.
21. Avoid assuming `@SpringBootTest` makes a test discoverable when the test engine is missing.
22. Identify classpath conflicts, `NoClassDefFoundError`, and engine discovery failures.
23. Know when to run the JUnit Platform ConsoleLauncher to separate the runner from the build plugin (depending on dependencies).
24. Build a minimal "sentinel test" to prove the runner works, then isolate issues in other tests.
25. Create a CI guard to prevent a change from dropping executed test counts to zero.
26. Write a diagnostic report containing commands, versions, task, engines, filters, and discovered/executed/skipped counts.

## 3. Pipeline from Source Code to Execution Result

```text
src/test/java/*.java
        |
        v
compileTestJava
        |
        +-- Class file exists in build/classes/java/test?
        |        |
        |        +-- No -> wrong source set/path or compile failure
        |
        v
Gradle Test task / Maven Surefire / IDE runner
        |
        +-- Runtime classpath
        |       junit-jupiter-api?
        |       junit-jupiter-engine?
        |       junit-platform-launcher?
        |       junit-vintage-engine? (if JUnit 4)
        |
        v
JUnit Platform Launcher
        |
        v
TestEngine discovery
        |
        +-- junit-jupiter -> @Test, @Nested,
        |                     @ParameterizedTest, @TestFactory...
        +-- junit-vintage -> JUnit 3/4
        +-- other engines -> corresponding test framework
        |
        v
Filters and selectors
        |
        +-- class, method, package patterns
        +-- Gradle --tests
        +-- tags include/exclude
        +-- engine include/exclude
        |
        v
Execution
        |
        +-- PASS
        +-- FAIL
        +-- SKIPPED / DISABLED
        |
        v
build/test-results/test/*.xml
build/reports/tests/test/index.html
```

"Tests not discovered" is only accurate when failure happens at **discovery**. If `@Disabled` causes a skip or Gradle only selects `@Tag("fast")`, tests **may already have been discovered** but not executed. If `compileTestJava` fails, execution never reaches discovery.

### 3.1. First Four Questions

1. **Are you targeting the right project, module, task, and source set?** For example, `:orders:test` does not automatically run `:billing:test`.
2. **Has the test class been compiled?** Inspect the outputs of `compileTestJava`.
3. **Is the matching TestEngine on the runtime classpath?** Not just the compile API.
4. **Do selectors/filters/conditions allow the test to run?** Remove filters one at a time to verify instead of mixing multiple variables.

### 3.2. Gradle Status Is Not JUnit Status

| Gradle Output | Primary Meaning | Action to Take |
| --- | --- | --- |
| `:test NO-SOURCE` | Task has no matching test input sources | Check source set/paths |
| `:test UP-TO-DATE` | Inputs/outputs unchanged; Gradle skipped re-running task | If a fresh run is needed, use `--rerun-tasks` |
| `:test FROM-CACHE` | Task output restored from the build cache | Check reports/change invocation if fresh execution is needed |
| `:test SKIPPED` | Task skipped due to task condition/skip setting | Check `onlyIf`, `-x test`, skip flags |
| `:test FAILED` | Task failed due to assertion, process, or test detection | Read logs/reports; do not automatically assume "test failure" |
| `BUILD SUCCESSFUL` | Build tasks finished according to Gradle rules | **Does not prove** executed test count is greater than zero |

A `@Disabled` JUnit test can be recorded as skipped in the JUnit report even though the Gradle `test` task does not display `SKIPPED`. These are two completely separate status layers.

## 4. JUnit 5 Is a Multi-Module Architecture

**JUnit 5** is typically described in three components:

- **JUnit Platform:** the discovery/execution foundation and Launcher API/SPI enabling build tools/IDEs to invoke engines.
- **JUnit Jupiter:** the programming API (`@Test`, `@Nested`, `@ParameterizedTest`) **and** the engine implementation `junit-jupiter-engine`.
- **JUnit Vintage:** an engine for running JUnit 3/4 tests on the JUnit Platform, used during legacy project migrations.

```text
JUnit Jupiter API jar
       |
       +-- compile: import @Test, Assertions...
       |
JUnit Jupiter Engine jar
       |
       +-- runtime: discovers + executes Jupiter tests
       |
JUnit Platform Launcher
       |
       +-- runner asks engines to discover/run tests
```

### 4.1. Why Does Compilation Succeed While Nothing Runs?

Source contains:

```java
import org.junit.jupiter.api.Test;

class ExampleTest {
    @Test
    void works() {
        org.junit.jupiter.api.Assertions.assertTrue(true);
    }
}
```

If the build only has `junit-jupiter-api` and lacks `junit-jupiter-engine` at runtime, the compiler still recognizes the annotation and compiles. However, the Platform has no Jupiter engine to discover/execute the test. The exact error manifestation depends on the launcher/runner and Gradle version: it may report a missing engine, "Cannot create Launcher without at least one TestEngine", or no tests discovered. **Do not assume a single exact error message** across all environments.

### 4.2. Engine ID

Commonly used:

| Engine ID | Artifact | Discovers |
| --- | --- | --- |
| `junit-jupiter` | `org.junit.jupiter:junit-jupiter-engine` | JUnit Jupiter |
| `junit-vintage` | `org.junit.vintage:junit-vintage-engine` | JUnit 3/4 |
| `junit-platform-suite` | `org.junit.platform:junit-platform-suite-engine` | Declarative JUnit suites |

An engine ID does not necessarily match the Maven artifact name identically. If a build filters with `includeEngines 'junit-vintage'` only, Jupiter test methods may not be selected even when the Jupiter engine is present on the classpath.

### 4.3. TestEngine Is an SPI, Not Just an Annotation

An engine is loaded by JUnit Platform from the runtime classpath via ServiceLoader/engine discovery. When the runtime lacks the engine artifact, or the engine is excluded by an engine filter, the Platform cannot execute tests belonging to that programming model. Mockito, SpringExtension, and `@SpringBootTest` do not provide a substitute TestEngine on their own.

## 5. Java Test Annotations: Wrong Imports Are a Major Source of Errors

There are multiple `@Test` annotations with the same simple name belonging to different frameworks:

| Import | Framework | Matching Runner/Engine |
| --- | --- | --- |
| `org.junit.jupiter.api.Test` | JUnit Jupiter | Jupiter engine |
| `org.junit.Test` | JUnit 4 | JUnit 4 runner or Vintage engine on Platform |
| `org.testng.annotations.Test` | TestNG | Corresponding TestNG runner/provider/engine |
| `org.junit.jupiter.params.ParameterizedTest` | Jupiter | Jupiter engine + params API |

Code annotated with one framework's annotation will not automatically run on another framework's engine.

### 5.1. Accidental JUnit 4 Import in a Jupiter Project

```java
// JUnit 4 annotation -- not Jupiter:
import org.junit.Test;

public class LegacyPaymentTest {
    @Test
    public void checksLegacyCondition() {
        org.junit.Assert.assertEquals(4, 2 + 2);
    }
}
```

This is a **snippet illustrating an engine mismatch**, not part of the runnable project. It compiles if the JUnit 4 API is available; when Gradle uses `useJUnitPlatform()` with only the Jupiter engine, the JUnit 4 test will not execute. To keep legacy tests, add **JUnit Vintage engine + JUnit 4** to the runtime/test classpath, or migrate annotations/assertions to Jupiter.

### 5.2. JUnit 4 and Jupiter Have Different Visibility Rules

JUnit 4 typically requires `public` test classes and `public void` no-arg test methods (unless using a special runner). In JUnit Jupiter, test classes and test methods **do not need to be public**, though they must not be `private`; `@Test` methods must be instance methods (not static) and return `void`. Do not try to fix an "unrecognized" Jupiter test by making every method public when the real cause is a missing engine.

### 5.3. @BeforeEach Does Not Create a Test

`@BeforeEach`, `@AfterEach`, `@BeforeAll`, and `@AfterAll` are lifecycle methods. A class with only `@BeforeEach` and **no test method/factory/template** does not become a suite with executable test cases. Likewise, `@DisplayName` or `@Tag` does not turn a method into a test if the test annotation is missing.

## 6. Minimal, Correct Gradle Configuration for Spring Boot 3.3

In a project using Java 17 and Spring Boot 3.3, a basic configuration looks like:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Three points to verify:

1. `spring-boot-starter-test` brings in the JUnit Jupiter API/engine and Spring testing utilities managed by Boot's dependency management. Do not include only `spring-boot-starter` and expect `@Test` to run.
2. `useJUnitPlatform()` instructs the Gradle Test task to use JUnit Platform. If omitted, Gradle 8.x may fall back to legacy JUnit 4-style runner/detection and ignore Jupiter tests.
3. `junit-platform-launcher` in `testRuntimeOnly` ensures the launcher version is explicitly on the **test runtime classpath**, rather than relying on Gradle's implicit internal provision. Gradle 9 is even stricter about dependencies, though this guide targets Boot 3.3/Gradle 8.x.

The runnable project in section 13 will extend this build file with a tag filter controlled via `-PincludeTestTag=...`.

### 6.1. Do Not Mix Arbitrary JUnit Versions Manually

Dangerous example:

```groovy
testImplementation 'org.junit.jupiter:junit-jupiter-api:5.10.2'
testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine:5.8.2'
```

This is an **illustrative anti-pattern**: mismatched major/minor API and engine versions can trigger discovery/runtime errors due to incompatible platform versions. With Boot's test starter, let the BOM manage versions unless there is a strong reason to override. Use `dependencyInsight` to verify the final resolved version.

### 6.2. Test Runtime Differs from Compile Classpath

A `testCompileOnly` dependency allows Java to compile but does not put the jar on the runtime classpath. A `testRuntimeOnly` dependency supports the runtime runner without exposing types at compile time. Therefore, you must inspect the right configuration during diagnosis.

If the JUnit API is in `testCompileClasspath` while the Jupiter engine is absent from **`testRuntimeClasspath`**, that is likely the root cause.

## 7. How to Inspect the Gradle Dependency Tree

In the module containing the tests:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-platform-launcher --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-vintage-engine --configuration testRuntimeClasspath
```

On Windows:

```powershell
.\gradlew.bat dependencies --configuration testRuntimeClasspath
.\gradlew.bat dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
```

**How to read the output:**

- `junit-jupiter-engine` present -> Jupiter engine artifact is resolved; still check the task's filters/launcher/effective classpath.
- `junit-platform-launcher` present -> launcher dependency is resolved.
- `junit-vintage-engine` absent -> JUnit 4 tests will not run on the Platform via Vintage unless another dedicated runner is configured.
- `spring-boot-starter-test` present but engine/transitive modules excluded at runtime -> inspect exclusions/resolution.
- Version conflict -> inspect the dependency graph and BOM; do not guess from source imports.

**Seeing the jar in a dependency report does not guarantee the engine is loaded successfully**: a custom Test task might use a classpath different from `sourceSets.test.runtimeClasspath`. Always inspect the exact task being executed.

### 7.1. An Anti-Pattern with Dependency Exclusions

```groovy
testImplementation(
        'org.springframework.boot:spring-boot-starter-test') {
    exclude group: 'org.junit.jupiter',
            module: 'junit-jupiter-engine'
}
```

This is an **intentionally broken** snippet; do not place it in a runnable build. Removing the engine still allows Java compilation, but Jupiter test discovery will not work as expected.

### 7.2. When Is JUnit Vintage Needed?

If existing test sources contain JUnit 4 imports, with Boot 3.3 and `useJUnitPlatform`:

```groovy
testImplementation 'junit:junit:4.13.2'
testRuntimeOnly 'org.junit.vintage:junit-vintage-engine'
```

This is an **optional addition**, unnecessary for a pure Jupiter runnable project. JUnit Vintage can be removed once all JUnit 4 tests are migrated. Verify that the BOM resolves a Vintage version compatible with Jupiter/Platform.

### 7.3. TestNG Does Not Automatically Become Jupiter

If a class uses `org.testng.annotations.Test`, the Jupiter engine will not recognize it. You must configure a **TestNG runner** or matching TestNG plugin/engine for the version in use. Do not simply add the JUnit Jupiter engine and expect it to run any annotation named `Test`.

## 8. Gradle Source Sets and Output Class Files

The Gradle Java plugin defines default source sets:

```text
src/main/java
src/main/resources
src/test/java
src/test/resources
```

`compileTestJava` compiles Java files in `src/test/java`, typically outputting to `build/classes/java/test`. The `test` task runs test classes from the `test` source set on that source set's runtime classpath by default.

If a file resides at:

```text
src/integrationTest/java/example/InvoiceIT.java
```

without an `integrationTest` source set/task configured, `./gradlew test` **will not compile or execute** that file by default.

### 8.1. 60-Second Diagnosis

```bash
./gradlew compileTestJava --info
./gradlew test --info
./gradlew tasks --all
```

After compiling, check the actual class files. On Linux/macOS:

```bash
find build/classes/java/test -type f -name '*Test*.class'
```

Windows PowerShell:

```powershell
Get-ChildItem build\classes\java\test -Recurse -Filter '*Test*.class'
```

**Note:** this command searches for *class file names* as a diagnostic aid, not as the sole definition of JUnit Platform discovery. A Jupiter test class named `BillingChecks` can still be recognized by the engine if the class is included in a valid selection/classpath.

### 8.2. Packages and Directories

A file with:

```java
package example.discovery;
```

should be placed at `src/test/java/example/discovery/InvoiceCalculatorTest.java` for clean organization, even though `javac` checks the package based on the declaration. Mismatched packages/directories can cause compilation errors, mismatched FQN test filters, or IDEs failing to recognize the source root.

### 8.3. Multi-Module Builds

In a Gradle multi-project build:

```bash
./gradlew :orders:test
./gradlew :billing:test
./gradlew test
```

The third command can run test tasks across multiple subprojects depending on task selectors/configuration; do not read `:orders:test` output alone and conclude tests in `billing` were not discovered. Always note the exact **Gradle task path** and the module containing the file.

### 8.4. Custom Test Tasks Must Declare Inputs

If you define a custom `integrationTest` task, you must configure `testClassesDirs`, the `classpath` from the integration source set, and `useJUnitPlatform()`. Skeleton example (requires the source set to already be created in the build script):

```groovy
tasks.register('integrationTest', Test) {
    description = 'Runs integration test source set'
    testClassesDirs =
            sourceSets.integrationTest.output.classesDirs
    classpath =
            sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
}
```

This snippet **cannot be copied verbatim into a minimal runnable build** unless `sourceSets.integrationTest` has already been created. If `testClassesDirs` is empty, the task has no compiled tests to discover even if the runtime engine is correct.

## 9. Class Naming: Gradle and Maven Differ

### 9.1. Gradle Running JUnit Platform

With `useJUnitPlatform()`, the Jupiter engine discovers tests based on test class structure, annotations, selectors, classpath, and Gradle include/exclude patterns. **Do not treat Maven Surefire's default naming patterns as mandatory rules for every Jupiter test running on Gradle.**

Still, using `*Test`/`*Tests` conventions for test classes is good practice so IDEs, build tools, CI patterns, and teammates can locate them easily. A custom Gradle include/exclude pattern can still filter out a properly annotated Jupiter class if its name does not match.

### 9.2. Maven Surefire Filters by Name by Default

Maven Surefire (without custom includes) typically selects classes matching:

- `**/Test*.java`
- `**/*Test.java`
- `**/*Tests.java`
- `**/*TestCase.java`

For example, `InvoiceTest.java` and `TestInvoice.java` are selected; `InvoiceSpec.java` may be ignored unless includes are configured. Do not mistakenly apply Failsafe `*IT` naming, run `mvn test`, and expect Surefire to pick it up.

Maven Surefire also excludes nested classes under the plugin's default patterns, which is important to keep in mind when using JUnit Jupiter `@Nested`. Check the actual plugin version and rules.

### 9.3. Do Not "Fix" File Names Without Checking Engine/Filters

A properly named `InvoiceCalculatorTest.java` class can still fail to run due to a missing `useJUnitPlatform()`, a JUnit 4 import, a missing runtime engine on the classpath, or a filtered `@Tag`. File naming is only **one selection layer**, not a substitute for verifying the engine.

## 10. Filters: Where Tests Most Easily Disappear

There are multiple filter layers:

| Layer | Example | Symptom |
| --- | --- | --- |
| Gradle class include/exclude | `include '**/*FastTest.class'` | Other classes are excluded from discovery |
| Gradle test filter | `--tests example.discovery.InvoiceCalculatorTest` | Only matching classes/methods are selected |
| JUnit tag filter | `includeTags 'fast'` | Untagged tests or tests with other tags are excluded |
| JUnit engine filter | `includeEngines 'junit-vintage'` | Jupiter tests do not run |
| JUnit conditions | `@Disabled`, `@EnabledOnOs` | Tests are discovered but skipped |
| Maven Surefire file includes | `**/*Test.java` | `InvoiceSpec.java` is ignored |
| Maven Surefire CLI | `-Dtest=InvoiceTest` | Only the selected pattern runs |
| Custom suite select/exclude | `@SelectPackages`, `@ExcludeTags` | Suite intentionally runs only a subset |
| Build task skip | `-x test`, `-DskipTests` | Task does not execute; not a missing engine |

### 10.1. Gradle --tests

```bash
./gradlew test --tests example.discovery.InvoiceCalculatorTest
./gradlew test --tests 'example.discovery.InvoiceCalculatorTest.addsTwoNumbers'
./gradlew test --tests '*TaggedChecksTest*'
```

**Important:** The class/method selector must match an actually discovered test. If the name is wrong, Gradle typically reports something like "No tests found for given includes" when the filter requires a non-existent test. That does not prove the entire suite has no tests; it only proves **the current selection matched nothing**.

### 10.2. Tag Filters

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'fast'
        excludeTags 'slow'
    }
}
```

This snippet is an **illustrative static configuration**, not the main lab build. A method with only `@Tag("slow")` or without `fast` will not run. When an include tag and exclude tag conflict, exclusion wins for tests belonging to the excluded set.

### 10.3. Engine Filters

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeEngines 'junit-vintage'
    }
}
```

This snippet intentionally selects only Vintage: if the project only contains Jupiter tests, the selector filters them all out. Do not use an engine filter unless there is a specific need to separate frameworks; by default, JUnit Platform uses all engines present on the runtime classpath.

### 10.4. Maven Flags and Environment Variables

`mvn -Dtest=SomeTest test` differs from `mvn test`. Similarly, a CI job might pass `-Dgroups`, `-DexcludedGroups`, `-DskipTests`, custom profiles, or Surefire includes. A "green build" might occur because the task was skipped by CI flags. Always inspect the **effective task/plugin configuration** and the exact command that ran.

## 11. Disabled, Aborted, Failed, Undiscovered: Four Distinct States

### 11.1. Undiscovered Test

No test node is created or selected by the engine: missing engine, wrong source set, invalid private/static signature, filtered class, or annotation-engine mismatch. For signature errors, the engine may discover the class and report a **discovery/validation failure** rather than silently ignoring the test. Read the logs instead of applying a single generic label.

### 11.2. Discovered but Skipped

`@Disabled` and certain conditional annotations produce a skipped result; they can still appear in the JUnit XML/IDE test tree. Do not use `skipped=0` to claim every source test compiled and was discovered; it only reflects the tests recorded by the runner.

### 11.3. Executed then Aborted

JUnit assumptions such as `Assumptions.assumeTrue(false)` lead to **aborted**; some runners display "skipped" or an equivalent status in reports. Aborted means the test started and hit a runtime condition, unlike a method never discovered by the engine.

### 11.4. Executed then Failed

A failing `assertEquals`, a Spring `ApplicationContext` startup error, or a `NoClassDefFoundError` during test execution is a **failure/error**, not zero tests. Investigate the stack trace and executed test counts instead of changing the TestEngine when discovery already succeeded.

## 12. JUnit Jupiter Class/Method Rules

A typical Jupiter class can be package-private:

```java
package example.discovery;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ArithmeticTest {
    @Test
    void additionWorks() {
        assertEquals(4, 2 + 2);
    }
}
```

**Public is not required.** Common errors to catch:

```java
// WRONG: Jupiter @Test method should not be private.
private @Test void inaccessible() {}

// WRONG: @Test method is not static.
@Test static void notAnInstanceTest() {}

// WRONG: @Test method does not return a value.
@Test int returnsValue() { return 42; }
```

These are **anti-pattern snippets**, not part of the runnable project. Java source syntax like `private @Test` for modifiers/annotations can still be accepted by the compiler, while JUnit Jupiter validation will reject it; place annotations and method declarations according to convention.

### 12.1. Constructors and Visibility

Jupiter test classes must not be abstract or private, and constructors must be compatible with Jupiter parameter resolution. Multiple arbitrary constructors, an unsuitable private constructor, or a constructor parameter lacking a `ParameterResolver` can cause engine/test instantiation to fail.

### 12.2. @Nested Must Be a Non-Static Inner Class

```java
class OuterTest {

    @Nested
    class InnerCases {

        @Test
        void childTest() {}
    }
}
```

This is a valid snippet (imports omitted for brevity). A static nested class is not treated as a `@Nested` container under JUnit Jupiter's nested test contract. If you create a nested Java class without `@Nested`, do not assume every runner will treat it as a nested Jupiter container.

### 12.3. @ParameterizedTest and Invocations

One `@ParameterizedTest` method can generate three, ten, or a hundred invocations. In reports, runners may display each invocation as a child test node. Therefore, "number of `@Test` methods in source" **does not equal** "number of executed test cases." Record both discovered/executed invocations when tracking coverage budgets.

### 12.4. @TestFactory Dynamic Tests

`@TestFactory` is discovered by the engine as a **factory/container**; dynamic test nodes are created when the factory executes. If the factory returns an empty stream, zero dynamic child tests execute even though the factory method ran. If the factory throws, that is an execution error. Do not mistake dynamic tests absent from the initial static IDE tree for "the engine ignored the factory."

## 13. Runnable Project: Java 17 + Spring Boot 3.3 + JUnit Jupiter

### 13.1. Directory Structure

```text
test-discovery-lab/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/discovery/
    │   ├── DiscoveryApplication.java
    │   └── InvoiceCalculator.java
    └── test/java/example/discovery/
        ├── InvoiceCalculatorTest.java
        ├── TaggedChecksTest.java
        └── WiringSmokeTest.java
```

No extra modules, databases, or Docker. The goal is to **isolate discovery/filter issues from external environment issues**. If the Gradle wrapper is not yet present, generate it with a compatible Gradle version (e.g., Gradle 8.7); `./gradlew` is not generated simply by copying `build.gradle`.

### 13.2. settings.gradle

```groovy
rootProject.name = 'test-discovery-lab'
```

### 13.3. build.gradle

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion =
                JavaLanguageVersion.of(17)
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
    useJUnitPlatform {
        if (project.hasProperty('includeTestTag')) {
            includeTags(
                    project.property('includeTestTag').toString())
        }
        if (project.hasProperty('excludeTestTag')) {
            excludeTags(
                    project.property('excludeTestTag').toString())
        }
    }

    testLogging {
        events 'passed', 'failed', 'skipped'
        exceptionFormat 'full'
    }
}
```

**Meaning:**

- Default without `-PincludeTestTag`/`-PexcludeTestTag`: all tagged and untagged tests are eligible for selection.
- `-PincludeTestTag=fast`: only tests tagged `fast` are selected; untagged tests are **excluded from selection**, not marked `@Disabled` by JUnit.
- `-PexcludeTestTag=slow`: excludes tests tagged `slow`.
- `--tests` is a **separate filter** that intersects with tag filters: only tests satisfying **both** will run.
- `testLogging` prints event types; it is optional for running tests, but speeds up diagnosis.
- `testRuntimeOnly junit-platform-launcher` aligns with JUnit Platform runtime; Boot's BOM manages versions.

## 14. DiscoveryApplication.java and InvoiceCalculator.java

**src/main/java/example/discovery/DiscoveryApplication.java**

```java
package example.discovery;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DiscoveryApplication {

    public static void main(String[] args) {
        SpringApplication.run(
                DiscoveryApplication.class,
                args);
    }
}
```

**src/main/java/example/discovery/InvoiceCalculator.java**

```java
package example.discovery;

import org.springframework.stereotype.Service;

@Service
public class InvoiceCalculator {

    public int total(int subtotal, int tax) {
        return Math.addExact(subtotal, tax);
    }

    public boolean isPositive(int amount) {
        return amount > 0;
    }
}
```

`InvoiceCalculator` is annotated with `@Service` so the Spring Boot wiring test confirms the bean is actually created. In unit tests, we use `new InvoiceCalculator()` to avoid starting a Spring context. `Math.addExact` throws `ArithmeticException` on overflow, providing a deterministic negative test case.

## 15. InvoiceCalculatorTest.java: Plain Test, Parameterized, Nested, Dynamic

**src/test/java/example/discovery/InvoiceCalculatorTest.java**

```java
package example.discovery;

import java.util.stream.Stream;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestFactory;
import org.junit.jupiter.api.DynamicTest;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.DynamicTest.dynamicTest;

class InvoiceCalculatorTest {

    private final InvoiceCalculator calculator =
            new InvoiceCalculator();

    @Test
    void addsTwoNumbers() {
        assertEquals(17, calculator.total(12, 5));
    }

    @ParameterizedTest(
            name = "addition {index}: {0} + {1} = {2}")
    @CsvSource({
            "1, 2, 3",
            "4, 5, 9",
            "-1, 1, 0"
    })
    void parameterizedAddition(
            int a,
            int b,
            int expected) {
        assertEquals(expected, calculator.total(a, b));
    }

    @Nested
    class BoundaryCases {

        @Test
        void zeroIsNotPositive() {
            assertFalse(calculator.isPositive(0));
        }

        @Test
        void negativeIsNotPositive() {
            assertFalse(calculator.isPositive(-1));
        }
    }

    @TestFactory
    Stream<DynamicTest> createsDynamicTests() {
        return Stream.of(
                dynamicTest(
                        "zero plus zero",
                        () -> assertEquals(
                                0, calculator.total(0, 0))),
                dynamicTest(
                        "overflow is rejected",
                        () -> assertThrows(
                                ArithmeticException.class,
                                () -> calculator.total(
                                        Integer.MAX_VALUE, 1)))
        );
    }
}
```

### 15.1. Exactly How Many Methods and Cases Are in This Class?

- `addsTwoNumbers`: 1 invocation.
- `parameterizedAddition`: 3 invocations from `@CsvSource`.
- `BoundaryCases.zeroIsNotPositive`: 1 invocation.
- `BoundaryCases.negativeIsNotPositive`: 1 invocation.
- `createsDynamicTests`: factory producing 2 dynamic test cases.

**Logical total: 8 executable test cases** from this class when unfiltered/enabled. Do not count `@TestFactory` as a ninth test case simply because it is a method; it generates dynamic child tests. Runners may display containers/factories differently in reports, but these eight assertions/test executions are the target.

### 15.2. Why Does a Package-Private Class Run?

JUnit Jupiter permits package-private test classes and methods as long as they are not private. This is a positive example countering the habit of assuming "not public means JUnit cannot discover it."

### 15.3. Why Is the Nested Class Non-Static?

`@Nested` uses non-static inner classes to inherit the outer instance's context and lifecycle. This is valid JUnit Jupiter syntax for Java 17.

### 15.4. Why Does @TestFactory Not Return Null?

`@TestFactory` must return a valid dynamic node type such as `Stream<DynamicTest>`, `Collection<DynamicTest>`, or `Iterable`. If the return type or value violates this contract, the test engine can report validation/processing errors. The lab source uses `Stream.of(...)` with two clearly named dynamic tests.

## 16. TaggedChecksTest.java: Filtering and Skipped

**src/test/java/example/discovery/TaggedChecksTest.java**

```java
package example.discovery;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class TaggedChecksTest {

    @Test
    @Tag("fast")
    void taggedFast() {
        assertEquals(4, 2 + 2);
    }

    @Test
    @Tag("slow")
    void taggedSlow() {
        assertEquals(8, 4 + 4);
    }

    @Test
    @Disabled("Demonstrates discovered-but-skipped")
    void knownDisabled() {
        throw new AssertionError(
                "This body must never execute");
    }
}
```

**Three test methods** are recognized by JUnit Jupiter via annotations. When run with default settings, `taggedFast` and `taggedSlow` execute/pass; `knownDisabled` is **skipped** rather than executed. When filtering with `includeTestTag=fast`, only `taggedFast` is selected; the other two tests are **not** reported as "discovered then skipped due to @Disabled" in the filtered selection if excluded by the tag filter.

### 16.1. Tag Inheritance from Class

If `@Tag("fast")` is placed on a class, methods inside inherit the `fast` tag under Jupiter tag semantics. In the lab, tags are placed at the **method level** intentionally to verify each filter path.

### 16.2. Do Not Mix JUnit 4 @Ignore with Jupiter @Disabled

JUnit 4 uses `org.junit.Ignore`; Jupiter uses `org.junit.jupiter.api.Disabled`. Importing the wrong framework annotation can prevent the condition from applying as expected. Check the engine and imports carefully.

## 17. WiringSmokeTest.java: Verifying Spring Context

**src/test/java/example/discovery/WiringSmokeTest.java**

```java
package example.discovery;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.NONE)
class WiringSmokeTest {

    @Autowired
    InvoiceCalculator calculator;

    @Test
    void springBootInjectsCalculator() {
        assertNotNull(calculator);
        assertEquals(
                22,
                calculator.total(20, 2));
    }
}
```

**One test** runs with `SpringExtension` integrated via `@SpringBootTest`. If the Jupiter engine is absent, `SpringExtension` never gets a chance to initialize the Spring context because the test class is not executed by the engine.

This helps distinguish between errors:

- **Missing discovery:** test method `springBootInjectsCalculator` is never selected/executed.
- **Context bootstrap failure:** the test method is selected, but Spring context initialization fails (e.g., missing bean). That is a **test execution/error**, not "JUnit failed to discover the test."

### 17.1. How Many Test Cases Are in the Entire Lab?

| Class | Executable test cases when unfiltered | Disabled |
| --- | ---: | ---: |
| `InvoiceCalculatorTest` | 8 | 0 |
| `TaggedChecksTest` | 2 | 1 |
| `WiringSmokeTest` | 1 | 0 |
| **Target total** | **11** | **1** |

JUnit/Gradle may display containers/factory nodes differently, but **11 executable cases + 1 disabled case** is the target count for an unfiltered run on the sample source. Do not treat this figure as an **executed report** before actually running the command.

## 18. Running the Hands-On Lab and Reading Reports

Requirements:

- JDK 17.
- Gradle 8.7 or wrapper compatible with Spring Boot 3.3.
- Files at the exact package paths.
- Maven Central/cache with the required artifacts.

Linux/macOS:

```bash
./gradlew clean test
./gradlew test --tests example.discovery.InvoiceCalculatorTest
./gradlew test --tests example.discovery.WiringSmokeTest
./gradlew test --tests 'example.discovery.TaggedChecksTest.taggedFast'
```

Windows PowerShell:

```powershell
.\gradlew.bat clean test
.\gradlew.bat test --tests example.discovery.InvoiceCalculatorTest
.\gradlew.bat test --tests example.discovery.WiringSmokeTest
```

Run a single tag:

```bash
./gradlew test -PincludeTestTag=fast
```

Run all tests except slow:

```bash
./gradlew test -PexcludeTestTag=slow
```

Run a specific method selector:

```bash
./gradlew test --tests 'example.discovery.InvoiceCalculatorTest.addsTwoNumbers'
```

If unsure whether a class/method is discovered, **run unfiltered first**, then add `--tests`/tag filters. Do not apply engine, tag, and name filters all at once and then have to guess which layer dropped the test.

### 18.1. Reading XML and HTML Reports

The Gradle test plugin typically generates:

```text
build/test-results/test/TEST-*.xml
build/reports/tests/test/index.html
```

Inspect `tests`, `failures`, `errors`, and `skipped` counts in the XML from the **corresponding run**. When running a filtered task or a `FROM-CACHE` task, verify which invocation produced the report. Each JUnit dynamic/parameterized case can be reported as a separate test node.

### 18.2. UP-TO-DATE Does Not Mean "No Tests"

If the task ran previously and inputs/outputs have not changed, Gradle may display `:test UP-TO-DATE`. When you **need a fresh execution for diagnosis**, run:

```bash
./gradlew test --rerun-tasks --info
```

You can use `clean test` in a **sandbox project**; in large repositories, cleaning all modules slows builds down and deletes unrelated build outputs. Do not run `--rerun-tasks` unconditionally in CI just to mask caching or flaky tests.

### 18.3. Do Not Use --dry-run to Prove Tests Execute

`./gradlew test --dry-run` only builds the task execution plan; it **does not execute test methods**. It is useful for checking task selection, but does not prove the Jupiter engine discovered any tests.

## 19. Negative Experiment 1: Omitting useJUnitPlatform

In a separate experimental branch, remove:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}
```

In Gradle 8.x, the `Test` task may fall back to legacy JUnit 4 runner defaults so Jupiter test classes are not discovered/executed. The exact error or zero count varies by Gradle version, dependencies, and build config. **Do not conclude the test source is broken** when you simply need to enable the right framework runner.

**Fix:** restore `useJUnitPlatform()` on the **right test task**. If there is an independent `integrationTest` task, add it to that task as well, not just `test`.

### 19.1. Why Can Auto-Enabling JUnit Platform by a Plugin Change Symptoms?

Some Gradle testing suites/plugins auto-configure JUnit Platform; if a test task uses different conventions, `useJUnitPlatform` may already be enabled. Therefore, do not treat "every Gradle version lacks Platform without this line" as an absolute law. Diagnose based on the **effective test task configuration** of the running project.

## 20. Negative Experiment 2: Missing Runtime Engine

In an intentionally broken branch, keep only the JUnit Jupiter API without the runtime engine:

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter-api'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Do not include `starter-test` at the same time since it pulls in the engine; otherwise the engine remains on the runtime classpath. `@Test` sources compile; the runner has Platform Launcher but lacks `junit-jupiter-engine`. Depending on Gradle/Platform version, launch will fail or zero tests will be discovered.

**Fix:** use the full `spring-boot-starter-test`, or add a compatible runtime engine dependency:

```groovy
testRuntimeOnly 'org.junit.jupiter:junit-jupiter-engine'
```

This is an **illustrative fix**; the runnable build uses `starter-test`. When adding the engine directly, let the Boot BOM manage its version unless you perform a compatibility review.

### 20.1. Engine Present in Dependency Graph but Unused

If the engine exists in the project-level runtime graph while a custom task's `classpath` is overridden, JUnit Platform inside that task still cannot load the engine. Inspect the task's `classpath` and `testClassesDirs`, not only `dependencies --configuration testRuntimeClasspath`.

## 21. Negative Experiment 3: Wrong JUnit 4 Import

In a JUnit Jupiter source file, replace:

```java
import org.junit.jupiter.api.Test;
```

with:

```java
import org.junit.Test;
```

Java only compiles if the JUnit 4 artifact is present. Under `useJUnitPlatform` with only the Jupiter engine, `org.junit.Test` is not handled by the Jupiter engine; add Vintage to retain legacy tests or migrate to the proper annotation.

**Do not change annotations just to make it compile** without checking the runner. In Spring Boot 3.3, JUnit Jupiter + `SpringExtension` is the standard path for new test code.

### 21.1. JUnit 4 @RunWith and JUnit Jupiter @ExtendWith

`@RunWith(SpringRunner.class)` belongs to JUnit 4; Jupiter uses `@ExtendWith(SpringExtension.class)`, and `@SpringBootTest` already integrates `SpringExtension`. A class with `@RunWith` but without Vintage or a JUnit 4 runner may not run; do not blame `@Autowired`.

## 22. Negative Experiment 4: Wrong Tag/Engine Filter

Try:

```bash
./gradlew test -PincludeTestTag=fast
./gradlew test -PincludeTestTag=slow
./gradlew test -PexcludeTestTag=slow
```

Based on the lab sources:

- Include `fast`: only `TaggedChecksTest.taggedFast` is selected.
- Include `slow`: only `taggedSlow` is selected.
- Exclude `slow`: all other tests can be selected, including untagged Jupiter cases; `knownDisabled` remains skipped if selected.
- Include `fast` together with `--tests example.discovery.WiringSmokeTest`: the intersecting filters match zero methods, which can produce a no-matching-tests outcome depending on Gradle.

**How to diagnose:** run unfiltered; add one filter at a time; inspect the actual CI command rather than `build.gradle` alone (the CLI can also pass `-P` and `--tests`).

### 22.1. Tag Expressions Are Not Class Names

`@Tag("fast")` does not mean the class is named `FastTest`; a class named `FastTest` does not automatically carry the `fast` tag. Tag filters and class name filters are two independent mechanisms.

### 22.2. Do Not Disable fail-on-no-matching to Bypass Errors

Some configurations allow changing `filter.failOnNoMatchingTests`. In a required test suite, **a non-matching filter should be treated as a signal to investigate and fix**. Disabling validation to force a green build can cause CI to silently drop an entire module's tests.

## 23. Maven Surefire: Naming Rules and Providers

If using Maven instead of Gradle, Surefire typically runs in the `test` lifecycle phase (unit tests). An equivalent minimal POM for Java 17/Boot 3.3 could be:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.0</version>
    <relativePath/>
  </parent>

  <groupId>example</groupId>
  <artifactId>test-discovery-lab</artifactId>
  <version>0.0.1-SNAPSHOT</version>

  <properties>
    <java.version>17</java.version>
  </properties>

  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>

  <build>
    <plugins>
      <plugin>
        <groupId>org.apache.maven.plugins</groupId>
        <artifactId>maven-surefire-plugin</artifactId>
        <version>3.2.5</version>
      </plugin>
    </plugins>
  </build>
</project>
```

This is a **Maven alternative**: place it as `pom.xml` and reuse the same Java source files if switching build systems; do not add it alongside Gradle as a mandatory requirement. Maven plugin 3.2.5 supports JUnit Platform via the appropriate provider. If the real project uses a different Surefire version, inspect the effective POM and that version's provider logs.

### 23.1. Maven Diagnostic Commands

```bash
mvn test
mvn -Dtest=InvoiceCalculatorTest test
mvn -Dtest=WiringSmokeTest test
mvn -X test
mvn dependency:tree
mvn help:effective-pom
```

Reports are usually at:

```text
target/surefire-reports/
```

The Maven Surefire filter `-Dtest=...` selects tests by pattern. If a wrong class name is passed, Surefire fails by default when no specified tests match; exact parameters vary by version. Do not conclude "the project has no tests" before running an unfiltered `mvn test` and checking source naming.

### 23.2. Maven *IT Names Are Usually Meant for Failsafe

Maven Surefire defaults typically pick up `*Test`/`*Tests`/`Test*`/`*TestCase`. Many projects use Maven Failsafe with `*IT`/`*ITCase` in the integration-test/verify lifecycle. If a file is named `CheckoutIT.java` and you only run `mvn test`, Surefire may ignore it. Configure includes or the appropriate Failsafe plugin.

**Do not mix Gradle `--tests` with Maven `-Dtest`**: each tool has its own syntax.

### 23.3. Maven Skip Flags

- `-DskipTests` usually skips running tests while still compiling them.
- `-Dmaven.test.skip=true` can skip both test compilation and execution (depending on plugin lifecycle).
- CI profiles/plugin configs may exclude modules or classes.

When `Tests are skipped` appears in logs, the issue is not JUnit engine discovery; inspect flags and plugin execution first.

## 24. JUnit 4 and Vintage: Safe Migration Strategy

If a project has hundreds of JUnit 4 tests that cannot be converted all at once, you can:

1. Keep the `junit:junit` test API.
2. Add `junit-vintage-engine` at runtime.
3. Enable `useJUnitPlatform()`.
4. Run both legacy and Jupiter tests on the same Platform, unless an engine filter restricts them.
5. Use dependency/test reports to verify the number of legacy test cases actually executed.
6. Gradually migrate `@RunWith`/`@Rule`, imports, and lifecycle methods to Jupiter/Extensions.
7. Remove Vintage once no legacy tests remain.

### 24.1. Do Not Assume Vintage and Jupiter Are Identical

JUnit 4 rules, categories, and runners do not automatically convert into Jupiter extensions/tags. During migration, verify the semantics of assertions, expected exceptions, timeouts, temporary folders, and `SpringRunner`. A test that "is discovered" after migration can still have lifecycle differences.

### 24.2. Engine Filters to Run Legacy Tests Separately

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeEngines 'junit-vintage'
    }
}
```

This snippet is useful when running legacy tests separately while Vintage is on the runtime classpath, but **must not** be left on the main suite's task if Jupiter tests are also expected to run.

## 25. Spring Boot Test and TestContext Do Not Fix Discovery Errors

`@SpringBootTest` requires `SpringExtension` and Spring Boot test support at runtime. It bootstraps an `ApplicationContext` once **JUnit Jupiter has already discovered and executed the test method**. However, it does **not**:

- Automatically register the Jupiter TestEngine when the runtime engine is excluded.
- Automatically add files in the wrong source set to the Gradle `test` classpath.
- Automatically bypass a Gradle `--tests` filter.
- Automatically convert JUnit 4 `org.junit.Test` into Jupiter.
- Automatically change Maven Surefire file naming includes.
- Automatically force `@Disabled` methods to run.

### 25.1. Distinguish Context Load Errors from Undiscovered Tests

If the log shows:

```text
Failed to load ApplicationContext
```

then Jupiter/`SpringExtension` already entered execution and attempted to bootstrap the context. That is a **test failure** (or test context load failure threshold), not "tests not recognized." Read the stack trace for missing beans, config, datasource, profile, or component scanning before touching the test engine.

### 25.2. Do Not Add @SpringBootTest to Pure Unit Tests

Plain JUnit Jupiter tests do not need a Spring context. Adding `@SpringBootTest` to every test slows down the suite and increases cache fragmentation without fixing a missing engine. Use pure JUnit tests for business logic; reserve Boot context for DI/config/HTTP/persistence integration.

## 26. Diagnosing Custom Test Tasks and Source Sets

Some projects define `integrationTest`, `functionalTest`, or `acceptanceTest` tasks with source sets separate from `test`. Distinguish:

```text
src/test/java              -> task test
src/integrationTest/java   -> task integrationTest (if created)
src/functionalTest/java    -> task functionalTest (if created)
```

A custom Gradle task must have:

- Its test source directory compiled.
- Source set dependencies and runtime classpath configured.
- `testClassesDirs` pointing to compiled classes.
- `classpath` containing application outputs plus test runtime dependencies/engine.
- `useJUnitPlatform()` if running Jupiter.
- Task wired into CI/check lifecycle if expected to run automatically.
- Filters/tag selectors not excluding all tests.

### 26.1. Do Not Inspect the Wrong Task

A project might have `./gradlew test` succeed while only running unit tests, whereas integration tests live in `integrationTest` and CI never invokes it. That is a **workflow coverage gap**, not a JUnit discovery bug. Add the right task invocation or `check.dependsOn integrationTest` where appropriate, considering runtime cost.

### 26.2. IDEs with Custom Source Sets

The IDE needs `src/integrationTest/java` marked as a test source root or synchronized via the Gradle model. If the IDE runs individual tests while the CLI task lacks the classpath, the IDE may be using its own runner or the custom source set is not wired into the Gradle task. Treat the CI-authoritative Gradle command as the source of truth.

## 27. Investigating a Discovery Error in the Shortest Order

### Step 1 — Ensure the Right Task

Run:

```bash
./gradlew tasks --all
./gradlew :test --info
```

In multi-module builds, replace `:test` with the actual task path, e.g., `:orders:test`. If the task reports `NO-SOURCE`, check `src/test/java` and compiled outputs.

### Step 2 — Run a Sentinel Jupiter Test

Add a tiny file in the right directory using `org.junit.jupiter.api.Test` and `assertTrue(true)` without a Spring context. If even that does not run, focus on the Gradle `Test` task, JUnit Platform, runtime engine, and classpath before debugging service code.

### Step 3 — Check the Runtime Engine

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
```

For custom tasks, check that task's classpath. Ensure JUnit Platform/engine versions match the Boot BOM.

### Step 4 — Temporarily Remove Filters in a Sandbox

Run `test` without `--tests` and without include/exclude tags, engines, or class patterns. Only once unfiltered tests run should you add filters back one by one and verify intersections. Do not commit removed filters if slow/security tests require tiering; use intentional configuration instead.

### Step 5 — Verify Annotation Signatures

`import org.junit.jupiter.api.Test`; non-private, non-static, void instance method; valid `@Nested`; valid source for `@ParameterizedTest`; valid return type for `@TestFactory`.

### Step 6 — Read Actual Test Reports

Inspect JUnit XML tests/failed/skipped counts; if zero executed, investigate rather than stopping at `BUILD SUCCESSFUL`. If skipped > 0, check `@Disabled`/conditional logic. If failed > 0, read the failure stack trace.

### Step 7 — Compare Maven/IDE/CI

Maven Surefire naming/filtering differs from Gradle. IDEs may use custom runners. CI may pass task skips, tags, TestEngine includes/excludes, or different JDK/Gradle versions. Record the exact command, branch, dependency lock/BOM, and environment.

## 28. Test Reporting and Anti-"Zero Tests" Policy

A basic quality gate:

1. Know the **expected** total test cases for each module (after approved filters).
2. Read discovered/executed/skipped/failed counts from the **actual run's** JUnit XML.
3. If an important task reports **zero executable tests**, treat it as a configuration/coverage failure to investigate.
4. If tag filters run only the `fast` suite, verify that `slow`/integration suites run in another task or CI job.
5. For `@Disabled`/`@Conditional` cases, record the skipped count and reason.
6. When upgrading JUnit/Gradle/Surefire, compare counts per module/task.
7. When increasing Gradle parallel forks or CI shards, sum counts from **each shard** with clear provenance; do not double-count retried tests.
8. With flaky retries, distinguish unique test cases from execution attempts.

### 28.1. Maven/Gradle Do Not Have Identical Guards Across All Versions

Some Gradle versions do not fail by default when a task has test sources yet discovers zero cases; Gradle 9 introduces changes around `failOnNoDiscoveredTests`. This guide targets **Gradle 8.x**, so do not rely on a Gradle 9 property to guarantee zero-tests failure. Build CI validation using test reports, sentinel cases, and version-appropriate settings.

### 28.2. Do Not Enable ignoreFailures to Turn the Test Task Green

`ignoreFailures=true` lets the build continue despite failing tests; it is **not** a discovery fix. Never use it to hide engine/config errors. Likewise in Maven, do not configure `testFailureIgnore` globally simply because CI is red.

## 29. Symptom -> Failure Layer Mapping Table

| Symptom | Most Likely Layer | First Step |
| --- | --- | --- |
| `:test NO-SOURCE` | Source set/input | Verify `src/test/java` and task |
| No compiled `.class` in `build/classes/java/test` | Compilation/source root | Run `compileTestJava` |
| Source has `@Test` but runtime lacks Jupiter engine | Dependency/engine | `dependencyInsight testRuntimeClasspath` |
| "Cannot create Launcher without at least one TestEngine" | Runtime engine | Add compatible engine |
| `NoClassDefFoundError` junit-platform/Jupiter class | Classpath conflict | BOM/version alignment |
| JUnit 4 tests do not run with `useJUnitPlatform` | Missing Vintage | `junit-vintage-engine` |
| `@Test` imported from `org.testng` | Wrong framework | Use TestNG runner or Jupiter import |
| `@Test` is private/static/non-void | Invalid Jupiter method | Fix signature |
| `@Nested` inner tests not shown | Nested declaration/discovery | Non-static inner class with `@Nested` |
| Parameterized method has 0 invocations | Source/setup failure | `CsvSource`/`MethodSource` validation |
| `@TestFactory` method has no children | Empty/invalid dynamic nodes | Check returned `Stream` |
| `@Disabled` test shows as skipped | Execution condition | Check annotation/reason |
| `includeTags fast` omits untagged test | Tag filter | Check tag policy |
| `--tests` "No tests found for given includes" | Class/method filter | Exact FQN, remove filters |
| `includeEngines vintage` omits Jupiter | Engine filter | Remove/adjust `includeEngines` |
| Maven `InvoiceSpec.java` does not run | Surefire name includes | Rename/configure includes |
| Maven `InvoiceIT` does not run with `mvn test` | Failsafe/source/task split | Check plugin/lifecycle |
| Gradle `:orders:test` misses billing tests | Wrong module | Run right task path |
| Custom `integrationTest` has no inputs | Task classpath/classes | `testClassesDirs`/`classpath` |
| `:test UP-TO-DATE` | Build caching | `--rerun-tasks` for fresh diagnosis |
| `:test FROM-CACHE` | Remote/local build cache | Inspect restored report |
| `BUILD SUCCESSFUL` yet zero tests | Missing guard/selection | Parse test results |
| `Failed to load ApplicationContext` | Execution/Spring wiring | Root cause stack trace |
| IDE green, CI zero | Runner/config divergence | Compare exact CLI, JDK, imports |
| Parallel shards differ in counts | Filters/modules/shards | Per-shard XML and config |

## 30. Hands-On Exercises

### Exercise 1 — Establish a Correct Baseline

Copy the runnable project and run `./gradlew clean test`. Record the **actual** passed/failed/skipped counts from the XML. Do not substitute the README's expected numbers for the real test report.

### Exercise 2 — Verify Package-Private Classes

Keep `InvoiceCalculatorTest` package-private. Do not change it to `public`; run the tests. This proves JUnit Jupiter discovers valid non-public classes.

### Exercise 3 — Remove useJUnitPlatform in a Sandbox

In an experimental branch, remove `useJUnitPlatform()` and run `test`. Observe the behavior, then restore it and verify the executed test count returns.

### Exercise 4 — Exclude junit-jupiter-engine

Create a test build without the engine at runtime. Use `dependencyInsight` to confirm, then run the sentinel test. Restore `starter-test`/engine afterward.

### Exercise 5 — JUnit 4 Import

Write a JUnit 4 `org.junit.Test` in a separate file; run the Platform with Jupiter only and observe it is not executed. Then add Vintage and check the executed count. Keep legacy and Jupiter imports separate from the main demo source.

### Exercise 6 — Wrong Maven Naming

In the Maven alternative, rename a class to `InvoiceSpec.java` and run `mvn test`. Inspect Surefire includes; rename it back or configure includes. Explain why Maven rules should not be applied mechanically to Gradle Jupiter.

### Exercise 7 — Select One Method

```bash
./gradlew test --tests 'example.discovery.InvoiceCalculatorTest.addsTwoNumbers'
```

Verify the JUnit XML contains only the selected method. If the method is renamed in source, the old filter stops matching; update the CLI selector.

### Exercise 8 — Include fast, Exclude slow

Run `-PincludeTestTag=fast` and `-PexcludeTestTag=slow` separately; compare what gets selected. Combine with `--tests` targeting `WiringSmokeTest` and explain the filter intersection.

### Exercise 9 — @Disabled

Remove `@Disabled` from `knownDisabled` in a sandbox: the test body intentionally throws and must fail. Restore `@Disabled`. This distinguishes skipped tests from silently missing tests.

### Exercise 10 — @ParameterizedTest

Change `@CsvSource` from 3 rows to 4 valid rows and observe executable invocations increase despite only one method definition.

### Exercise 11 — @Nested

Remove `@Nested` from `BoundaryCases`, run the unfiltered suite, and inspect the test tree/report. Restore it. Never assume a Java inner class automatically becomes a Jupiter nested test.

### Exercise 12 — @TestFactory

Change `Stream.of(twoDynamicTests)` to an empty stream and observe the factory produces zero child test cases; restore it to avoid zero dynamic coverage.

### Exercise 13 — Wrong Source Set

Move a test to `src/integrationTest/java` without configuring the source set. Run `compileTestJava`/`test` and confirm the class is omitted from the `test` task. Restore it or configure a proper `integrationTest` task.

### Exercise 14 — Custom Test Task

Create a separate `integrationTest` source set, configure `testClassesDirs`/`classpath`/`useJUnitPlatform()`, and run `./gradlew integrationTest`. Ensure CI actually invokes the task if coverage is expected.

### Exercise 15 — Maven Surefire -Dtest

Run `mvn -Dtest=WiringSmokeTest test` in the Maven alternative and observe results. Try a non-existent name and read the failure message rather than blindly changing the engine.

### Exercise 16 — Gradle UP-TO-DATE

Run `./gradlew test` twice on the same checkout and observe the task state. Use `--rerun-tasks` to force fresh execution during diagnosis.

### Exercise 17 — Vintage-Only Engine Include

Set `includeEngines 'junit-vintage'` in a sandbox that only has Jupiter tests; observe the results. Remove the filter so Jupiter runs again.

### Exercise 18 — Spring Context Failure

Intentionally remove `@Service` from `InvoiceCalculator`, run `WiringSmokeTest`, and observe Spring bean injection failing **after the test is discovered**. Restore `@Service`.

### Exercise 19 — Multi-Module

In a multi-module project, run `:orders:test` and `:billing:test` separately and read each module's counts; do not confuse zero tests in one task with tests living in the other module.

### Exercise 20 — CI Fail-on-Zero

Add a check verifying executed JUnit XML test cases (per policy) after the task. In a sandbox, pass a non-matching tag filter to verify the pipeline fails red instead of reporting `BUILD SUCCESSFUL`.

## 31. Pre-Merge QA Checklist

- [ ] Test files are in the right source set/task invoked by CI.
- [ ] `compileTestJava` compiles the files and produces corresponding `.class` outputs.
- [ ] Test runtime classpath includes JUnit Platform Launcher and the matching Jupiter engine.
- [ ] Gradle `Test` task uses JUnit Platform (or an equivalently configured testing suite).
- [ ] JUnit API/engine/platform versions are not overridden out of sync with the BOM.
- [ ] JUnit imports match the intended programming model.
- [ ] Legacy JUnit 4 tests have the Vintage engine or an appropriate runner.
- [ ] Jupiter test methods are not private/static/non-void.
- [ ] `@Nested` classes are valid non-static inner classes.
- [ ] `@ParameterizedTest` methods have a valid argument source.
- [ ] `@TestFactory` produces dynamic nodes when invoked.
- [ ] `@Disabled`/conditional skips are not confused with missing discovery.
- [ ] Gradle `--tests` selectors are reviewed and do not filter out tests by mistake.
- [ ] `includeTags`/`excludeTags`/`includeEngines` match CI policy.
- [ ] Gradle include/exclude file patterns do not omit test classes.
- [ ] Maven Surefire default patterns are understood; custom includes are set when needed.
- [ ] Maven Failsafe/integration task is invoked if `*IT` tests exist.
- [ ] No unintended `-DskipTests`, `maven.test.skip`, or `-x test`.
- [ ] Test task is not merely `UP-TO-DATE`/`FROM-CACHE` when a fresh run is required.
- [ ] Never equate `BUILD SUCCESSFUL` with "all tests passed" without checking test counts.
- [ ] A simple sentinel test exists to separate engine issues from Spring setup issues.
- [ ] Spring context failures are diagnosed from the proper stack trace.
- [ ] XML/HTML reports are collected from the exact module/task/invocation.
- [ ] Discovered, executed, skipped, failed, and test containers are distinguished.
- [ ] Coverage guards detect zero tests according to suite policy.
- [ ] CI shards/forks do not double-count executions/retries in reporting.
- [ ] Positive and negative diagnostics were run in a sandbox without committing anti-patterns.
- [ ] When upgrading Gradle/JUnit/Surefire, test counts and filters are compared before and after.
- [ ] Executed results are reported from actual tool output, not inferred from READMEs.

## 32. Decision Tree

```text
JUnit test not showing up?
       |
       +-- Right task/module?
       |      -> :module:test, integrationTest, IDE vs CI.
       |
       +-- Right source set?
       |      -> src/test/java; compileTestJava; .class files.
       |
       +-- Jupiter engine & launcher on runtime classpath?
       |      -> testRuntimeClasspath / dependencyInsight.
       |
       +-- Right runner?
       |      -> Gradle useJUnitPlatform().
       |         Maven Surefire supported provider.
       |
       +-- Right annotations?
       |      -> org.junit.jupiter.api.Test.
       |         JUnit4 needs Vintage if running on Platform.
       |
       +-- Right signature/nesting?
       |      -> non-private instance void @Test,
       |         @Nested non-static inner,
       |         @ParameterizedTest source.
       |
       +-- Filtered out?
       |      -> --tests, tags, engine filters,
       |         includes/excludes, Maven naming.
       |
       +-- Discovered but skipped?
       |      -> @Disabled/conditional/assumptions.
       |
       +-- Task didn't re-run?
       |      -> UP-TO-DATE/FROM-CACHE;
       |         --rerun-tasks only when needed.
       |
       +-- Executed but failed?
              -> Read JUnit XML/stack trace;
                 Spring ApplicationContext is another layer.
```

**Conclusion:** Test discovery is a chain of consecutive conditions: right source -> successful compilation -> right **TestEngine** at runtime -> runner using JUnit Platform -> valid class/method -> filters allowing selection -> actual test execution. You cannot diagnose it from a single `BUILD SUCCESSFUL` line. Use a sentinel Jupiter test, `testRuntimeClasspath`, `useJUnitPlatform()`, the right test task, per-layer selectors/filters, and XML reports. Most importantly, **JUnit Jupiter/Gradle and Maven Surefire select tests differently**; understanding the exact tool in use lets you pinpoint errors quickly without dropping CI coverage.

## 33. Official References

- Gradle — Testing in Java & JVM Projects, JUnit 5, test filtering, test detection, engines: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Test task DSL, filters, classpath, testClassesDirs: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html
- Gradle — Upgrading to 9.0, change to fail-on-no-discovered-tests: https://docs.gradle.org/current/userguide/upgrading_major_version_9.html
- Gradle — Dependency Insight: https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html
- JUnit Jupiter 5.11 User Guide — Test classes, methods, nested and dynamic tests: https://docs.junit.org/5.11.4/user-guide/index.html
- JUnit 5 User Guide — Platform, engines, filtering, tags, legacy migration: https://docs.junit.org/5.11.4/user-guide/index.html
- JUnit Jupiter API — @Test: https://junit.org/junit5/docs/5.11.4/api/org.junit.jupiter.api/org/junit/jupiter/api/Test.html
- JUnit Platform — Launcher API: https://junit.org/junit5/docs/5.11.4/api/org.junit.platform.launcher/org/junit/platform/launcher/Launcher.html
- Maven Surefire Plugin — Default inclusions/exclusions: https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion
- Maven Surefire Plugin — JUnit Platform: https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html
- Maven Surefire Plugin — Test mojo/flags: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo
- Maven Failsafe Plugin — Integration test naming/lifecycle: https://maven.apache.org/surefire/maven-failsafe-plugin/examples/inclusion-exclusion.html
- Spring Boot 3.3 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 — Testing features and annotations: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
- JUnit Platform engine SPI and user guide: https://junit.org/junit5/docs/5.11.4/user-guide/index.html
