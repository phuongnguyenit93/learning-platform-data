# Running JUnit Platform and Verifying Accurate Test Discovery

A Spring Boot project can **compile successfully and report BUILD SUCCESS** while still running zero tests. Conversely, a `*Test.java` file might be visible in the IDE while Gradle/Maven fails to detect it, or tests may be **discovered** but `@Disabled`, tag filters, or exclusion rules prevent execution. Therefore, build verification does not stop at typing `test`; you must verify **the right engine was selected, the right tests were found, the expected count executed, and reliable results were recorded**.

This lesson guides you through JUnit Platform with **JUnit Jupiter (JUnit 5)** in a Spring Boot project using **Gradle or Maven**, from dependency configuration and a runnable Java 17 test suite to filtering tests, reading reports, distinguishing skipped tests from undiscovered ones, and setting up CI checks. Examples standardize on **Spring Boot 3.3.13, Java 17, Gradle 8.x, and Maven 3.9.x** to illustrate a concrete configuration; these versions should not be interpreted as the latest release. If your project is on another branch, verify versions/plugins against that branch's documentation.

## 1. What Do JUnit Platform, Jupiter, and the Build Tool Do?

JUnit 5 consists of distinct components, each appearing at a different step:

| Component | Role | What happens if missing/wrong? |
| --- | --- | --- |
| **JUnit Platform** | Infrastructure for **discovering and orchestrating execution** of tests via `TestEngine`s | The build tool cannot run tests through the Platform as expected |
| **JUnit Jupiter API** | Annotations/assertions such as `@Test`, `@ParameterizedTest`, `Assertions.assertEquals` | Test code fails to compile if the API is missing |
| **JUnit Jupiter Engine** | Picks up and executes tests written in the Jupiter model | Tests may compile, but there is **no engine to execute them** |
| **JUnit Platform Launcher** | API used by IDEs/build tools to request test discovery and execution | Depending on tool version, runtime components may fail or be missing |
| **Gradle `Test` task** | Starts test workers, connects to JUnit Platform, and saves reports | May use the wrong test framework if `useJUnitPlatform()` is missing |
| **Maven Surefire Plugin** | Runs unit tests in the `test` phase, selects provider/framework, and emits reports | Tests may be skipped due to naming patterns, filters, or an outdated plugin |
| **`spring-boot-starter-test`** | Bundles helpful test dependencies: Spring Boot Test, JUnit Jupiter, AssertJ, Mockito... | Does not replace proper test task/provider configuration |

Conceptual flow:

```text
src/test/java/*.java
     |
     v
compileTestJava / testCompile
     |
     v
.class on test classpath
     |
     v
Gradle Test / Maven Surefire
     |
     v
JUnit Platform Launcher + TestEngine on classpath
     |
     +--> Discovery (selectors, test classes, methods)
     |
     +--> Filters (class name, method, tag, engine...)
     |
     +--> Execution (pass, fail, aborted, skipped/disabled)
     |
     v
XML / HTML / text reports + build exit code
```

Do not equate **compiled**, **discovered**, and **executed**. A Java class with `@Test` can compile without being on the test runtime classpath; a test recognized by JUnit can be disabled; a `test` command can do nothing if the source set contains no test files.

**JUnit 4 differs from JUnit Jupiter.** Jupiter uses `org.junit.jupiter.api.Test`; JUnit 4 uses `org.junit.Test`. To run JUnit 4 tests on the Platform, you typically need `junit-vintage-engine` and a compatible JUnit 4 dependency. Adding only Jupiter Engine **does not guarantee** legacy JUnit 4 tests will run.

## 2. Project Structure so Tools Find the Right Tests

A Spring Boot project by convention:

```text
testing-demo/
├── settings.gradle / build.gradle      (if using Gradle)
├── pom.xml                              (if using Maven)
└── src/
    ├── main/
    │   └── java/com/example/testing/
    │       ├── CheckBuildApplication.java
    │       └── MathPolicy.java
    └── test/
        ├── java/com/example/testing/
        │   └── MathPolicyTest.java
        └── resources/
            └── junit-platform.properties (only needed if customizing Platform)
```

Four foundational points:
- Application code lives in `src/main/java` and is compiled first.
- Test code lives in `src/test/java`; packages can match the main package to easily access package-private classes/methods in examples.
- `src/test/resources` serves the test runtime and is not automatically packaged into the production executable JAR.
- Test dependencies such as Jupiter have **test scope** (Maven) or **testImplementation/testRuntimeOnly** (Gradle).

Putting tests in `src/main/java` places test classes in the wrong source set, where test dependencies may be unavailable and test code could even end up in the production artifact. Placing tests in an arbitrary directory outside the test source set without registering it with the build tool may let the IDE show the file, while the `test` task will not know to compile or run it.

## 3. Configuring Gradle to Run JUnit Platform

### 3.1. Complete `build.gradle` Groovy DSL

Create `settings.gradle`:

```groovy
rootProject.name = 'testing-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Explanation:

1. `java` creates default tasks `compileJava`, `compileTestJava`, `processTestResources`, and `test`.
2. `spring-boot-starter-test` brings JUnit Jupiter and common testing tools into the test dependency graph.
3. `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` explicitly declares the Platform Launcher on the test runtime classpath, avoiding reliance on a launcher implicitly provided by a Gradle version. Its version is managed by Spring Boot dependency management in this example.
4. `useJUnitPlatform()` **selects JUnit Platform** as the discovery/execution framework for the `test` task. This step is critical when using JUnit Jupiter in this Gradle setup.
5. `org.springframework.boot` provides Boot tasks; **`bootJar` itself does not run tests as a replacement for `test`**. In the verification lifecycle, `check`/`build` typically pulls in the test task via the Java plugin.

You can use Gradle's native `platform(...)` instead of `io.spring.dependency-management` if you want a separate version management strategy. In that case, apply the BOM to the relevant test configurations and verify resolved versions; **do not simply copy the `testImplementation` line and drop version management**.

### 3.2. Equivalent `build.gradle.kts` Kotlin DSL

If your project uses Kotlin DSL, use the alternate syntax:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}

tasks.test {
    useJUnitPlatform()
}
```

This is a `build.gradle.kts` file that **replaces** the Groovy DSL in section 3.1, not a block to paste into `build.gradle`. `tasks.test { useJUnitPlatform() }` and `tasks.named('test') { useJUnitPlatform() }` express the same intent in the two DSLs.

If a project has multiple test tasks, configure JUnit Platform on the **appropriate task**. Putting `useJUnitPlatform()` on the default `test` task does not automatically ensure a custom `integrationTest` task uses the Platform and the right classpath.

## 4. Maven: Configuring Surefire and JUnit Platform

With **Spring Boot starter parent**, Maven typically receives managed plugin versions, including Maven Surefire; starter test brings in Jupiter dependencies. Complete `pom.xml` example:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>testing-demo</artifactId>
    <version>1.0.0</version>

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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

**Surefire is the plugin that executes unit tests in the `test` phase.** With default `jar` configuration, `mvn test` triggers the appropriate Surefire goal. Spring Boot parent provides plugin management; if you have a corporate parent or only import the `spring-boot-dependencies` BOM, inspect the Surefire version/plugin configuration via the **effective POM**.

You do not need `spring-boot-maven-plugin` for JUnit discovery: the Boot plugin handles running/packaging the application, whereas Surefire handles unit tests. The example declares the Boot plugin because it is a Spring Boot app with a main class; **do not treat `spring-boot:run` as a way to run JUnit**.

In Maven Surefire 3.x, when JUnit Platform/Jupiter Engine is on the test classpath, Surefire uses the appropriate Platform provider to run Jupiter tests. Avoid very old Surefire versions that lack proper JUnit 5 support. You can check the actual plugin, provider, and version via `./mvnw help:effective-pom` and the `test` logs.

## 5. Complete Java 17 Example Set to Verify Discovery

This section uses the **same Java code** for either the Gradle or Maven project above.

### 5.1. Application Main Class

`src/main/java/com/example/testing/CheckBuildApplication.java`:

```java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CheckBuildApplication {

    public static void main(String[] args) {
        SpringApplication.run(CheckBuildApplication.class, args);
    }
}
```

Having a main class allows the Spring Boot project to be packaged as an application. The test suite below **does not need to start a Spring application context**.

### 5.2. Business Class Under Test

`src/main/java/com/example/testing/MathPolicy.java`:

```java
package com.example.testing;

public final class MathPolicy {

    private MathPolicy() {
    }

    public static int add(int left, int right) {
        return Math.addExact(left, right);
    }

    public static int divide(int dividend, int divisor) {
        return dividend / divisor;
    }
}
```

`Math.addExact` performs integer addition with overflow checking; `divide` uses Java integer division, throwing `ArithmeticException` when the divisor is 0. The class uses only the JDK, keeping tests independent of databases and the Spring context.

### 5.3. Test Class with Standard, Parameterized, and Disabled Tests

`src/test/java/com/example/testing/MathPolicyTest.java`:

```java
package com.example.testing;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.fail;

import org.junit.jupiter.api.Disabled;
import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.CsvSource;

class MathPolicyTest {

    @Test
    @Tag("smoke")
    void addsTwoNumbers() {
        assertEquals(7, MathPolicy.add(3, 4));
    }

    @ParameterizedTest
    @CsvSource({
            "-1, 1, 0",
            "4, 5, 9"
    })
    @Tag("fast")
    void addsSeveralCases(int left, int right, int expected) {
        assertEquals(expected, MathPolicy.add(left, right));
    }

    @Test
    @Tag("validation")
    void dividingByZeroThrows() {
        assertThrows(ArithmeticException.class,
                () -> MathPolicy.divide(10, 0));
    }

    @Test
    @Disabled("Demonstrates skipped status in reports")
    void intentionallySkipped() {
        fail("This test must stay disabled in the demonstration");
    }
}
```

**Why is this test valid?** JUnit Jupiter allows test classes and test methods to have package-private visibility; declaring `public` is not required. A `@Test` method must not be `private` or return a value, and in this example it is not `static`. Pay attention to importing `org.junit.jupiter.api.Test` rather than JUnit 4's `org.junit.Test`.

The example suite produces **5 recognized test cases**:
- `addsTwoNumbers()`: 1 test, tag `smoke`.
- `addsSeveralCases(...)`: 2 invocations corresponding to 2 `@CsvSource` rows, tag `fast`.
- `dividingByZeroThrows()`: 1 test, tag `validation`.
- `intentionallySkipped()`: 1 **disabled** test whose body does not execute.

With default testing **and no tag filter**, the expected counts are **5 total, 4 passed, 1 skipped, 0 failed, 0 errors**. Gradle and Maven display console lines differently; **use XML/HTML reports** to verify numbers rather than relying on a fixed log message. In production code, important tests should not remain `@Disabled` indefinitely; here it serves only to distinguish "discovered but skipped" from "not discovered."

The Java files above compile with **Java 17** in the stated Gradle/Maven configurations. You cannot run standalone `javac MathPolicyTest.java` without JUnit on the classpath; use the build tool to resolve dependencies, compile, and run tests.

## 6. Running Tests and Confirming Discovery

### 6.1. Gradle

From the project directory containing the Gradle Wrapper:

```bash
./gradlew clean test
```

On Windows PowerShell:

```powershell
.\gradlew.bat clean test
```

The `test` task must compile `src/test/java`, launch a test worker via JUnit Platform, and write results. Default output locations:

```text
build/
├── test-results/
│   └── test/
│       └── TEST-com.example.testing.MathPolicyTest.xml
└── reports/
    └── tests/
        └── test/
            └── index.html
```

Open `build/reports/tests/test/index.html` in a browser; if CI needs to collect reports, gather XML files in `build/test-results/test/`. **Check the total test count and individual methods/invocations**, because `BUILD SUCCESSFUL` alone does not tell you which tests ran.

To re-run when Gradle reports `UP-TO-DATE`/`FROM-CACHE`, use:

```bash
./gradlew test --rerun-tasks
```

`--rerun-tasks` forces Gradle not to skip task execution via up-to-date/cache state for that run; you do not necessarily have to `clean` the entire build for every check.

### 6.2. Maven

From the project directory containing the Maven Wrapper:

```bash
./mvnw clean test
```

On Windows PowerShell:

```powershell
.\mvnw.cmd clean test
```

Maven Surefire outputs reports in:

```text
target/
└── surefire-reports/
    ├── TEST-com.example.testing.MathPolicyTest.xml
    └── com.example.testing.MathPolicyTest.txt
```

A typical report prints something like:

```text
Tests run: 5, Failures: 0, Errors: 0, Skipped: 1
```

These are the **expected counts for the example suite**, not verbatim logs measured in a specific environment. The JUnit parameterized test has **two invocations**, so it counts as two executions; the `@Disabled` test does not have its body executed.

### 6.3. No Wrapper?

You can replace `./gradlew` with `gradle` and `./mvnw` with `mvn` if compatible Gradle/Maven is installed. In shared/CI projects, the Wrapper pins the build tool version. Check:

```bash
java -version
./gradlew --version
./mvnw -version
```

Only run the command for the **build tool actually used by the project**; you do not need both Maven and Gradle in a single project.

## 7. Discovery Has Multiple Layers: Finding the Right Issue

For a `@Test` to execute, all of the following conditions must be satisfied simultaneously:

1. **Source:** the file resides in a test source set known to the build tool.
2. **Compile:** the test class compiles to bytecode in `build/classes/java/test` (Gradle) or `target/test-classes` (Maven).
3. **Classpath:** the test worker has the test classes, Jupiter API/Engine, and required dependencies.
4. **Runner/provider:** Gradle enables `useJUnitPlatform()` or Maven Surefire uses a compatible JUnit Platform provider.
5. **Selection/discovery:** the build tool and JUnit Platform see the class and test descriptors.
6. **Filters/conditions:** not excluded by naming patterns, `--tests`/`-Dtest`, tags, engine filters, or disabled conditions.
7. **Execution/report:** the test runs or is recorded as skipped/aborted with an outcome.

| Observation | What can you conclude? | What still needs verification? |
| --- | --- | --- |
| `compileTestJava`/`testCompile` succeeds | Test code **compiles** | Still must check the engine and executed test count |
| Gradle `:test NO-SOURCE` | Task has no usable test source inputs under current config | File location, source set, invoked subproject |
| Gradle `:test UP-TO-DATE` | Task was determined not to need re-running due to unchanged inputs/outputs | Check existing report or use `--rerun-tasks` if needed |
| Test reported as `skipped` | Test was recognized but its body did not execute under the condition | `@Disabled`, assumptions, conditions, filters |
| Maven `Tests run: 0` | Surefire executed zero tests | Class naming pattern, provider, test classpath, filters |
| `No tests found` reported for filter | No tests matched the specific selector/filter | Package/class/method name, tag, module |
| `TestEngine` or `Launcher` error | JUnit Platform infrastructure on classpath is incompatible/missing | Dependency versions and `testRuntimeClasspath` |
| Green build but XML reports missing | Test task may not have run, report written elsewhere, or tests undiscovered | Build invocation, task graph, report path |

**"No tests" differs from "all tests disabled."** In the section 5 example, `@Disabled` is discovered and produces a skip record. If no tests match a class/method/tag filter, the run count may be 0 or the build may fail depending on the tool/filter; that is a separate condition to handle.

## 8. Test Selection Rules and Class Naming

### 8.1. JUnit Jupiter Does Not Require Class Names to End in `Test`

At the JUnit Jupiter level, `@Test`/`@ParameterizedTest` annotations, valid class/method conditions, and the engine determine test descriptors. However, **the build tool can filter classes before passing them to the engine**.

This is why naming the class `MathPolicyTest` is helpful: it is both descriptive and matches Maven Surefire's conventions.

### 8.2. Maven Surefire Uses Default Naming Patterns

Maven Surefire 3.x by default discovers classes whose names match one of these patterns:

```text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
```

`MathPolicyTest.java` matches. A class named `MathPolicyChecks.java` containing the exact same `@Test` may **not be scanned by Surefire by default**; Gradle and IDEs may discover differently, leading to "green in IDE, 0 tests in Maven."

The preferred solution is to **name test classes by convention**, such as `MathPolicyTest`. If custom names are required, configure Surefire `<includes>` explicitly and make sure you do not accidentally exclude other classes.

For **integration tests** run by Maven Failsafe, names like `*IT.java`/`IT*.java`/`*ITCase.java` are typically used. Surefire and Failsafe are two different plugins/lifecycle goals; do not assume `mvn test` automatically runs integration tests named `*IT.java`.

### 8.3. Valid Jupiter Classes and Methods

JUnit Jupiter permits:
- Standard test classes with package-private access.
- `@Test` methods with package-private access returning `void`.
- Parameterized tests via `@ParameterizedTest` and a valid argument source.
- Nested test classes with `@Nested` when properly structured (typically non-`static` inner classes).
- Dynamic tests via `@TestFactory`, with its specific return type rules.

Common mistakes:
- Forgetting `@Test` or importing JUnit 4's annotation when only Jupiter Engine is present.
- Making a test method `private` or giving it an invalid signature.
- Using `@ParameterizedTest` without providing a valid argument source.
- Misannotating/misstructuring a `@Nested` class or targeting nested classes with an incompatible filter pattern.
- Placing tests in another source set without wiring that source set's classpath into the `test` task.

A recognized test method does not mean every assertion is valid; you still must inspect pass/fail results and verify real behavior.

## 9. Filtering by Class or Method: Gradle and Maven

### 9.1. Gradle `--tests`

Run a single entire class:

```bash
./gradlew test --tests 'com.example.testing.MathPolicyTest'
```

Run a single method:

```bash
./gradlew test --tests 'com.example.testing.MathPolicyTest.addsTwoNumbers'
```

Short pattern when the class is unambiguous:

```bash
./gradlew test --tests '*MathPolicyTest'
```

Quotes protect `*` from shell globbing in shells that perform expansion. If the filter matches no tests, Gradle normally reports **No tests found for given includes** and the task may fail under default filter policy. Do not disable that failure just to make the pipeline green; verify the fully qualified class/method name and target subproject.

If a test has `@Disabled`, filtering directly to that method still will not force it to run. `--tests` selects test descriptors; it does not override Jupiter conditional annotations.

### 9.2. Maven Surefire `-Dtest`

Run a single class:

```bash
./mvnw -Dtest=MathPolicyTest test
```

Run a single method:

```bash
./mvnw '-Dtest=MathPolicyTest#addsTwoNumbers' test
```

In Maven, `-Dtest` is **Surefire's test selection property**. Maven Surefire normally fails if an explicit `-Dtest` request matches no tests (depending on version and `failIfNoSpecifiedTests`), even if an unfiltered `mvn test` run with no tests might succeed. Do not confuse the **no tests exist at all** policy with **no tests matched an explicit selector**.

On Windows PowerShell, use `.\mvnw.cmd`. Method/class names containing special characters should be quoted appropriately for your shell. Do not pass `-DskipTests` when trying to verify discovery: it skips test execution.

### 9.3. Running the Right Subproject/Module

In a Gradle multi-project build, tests may live inside `:billing-service`:

```bash
./gradlew :billing-service:test --tests 'com.example.billing.BillingServiceTest'
```

In a Maven multi-module build, you can select a module with `-pl` and build its required dependencies with `-am`:

```bash
./mvnw -pl billing-service -am test
```

The module names above are examples only. Running `test` in the wrong module or in an aggregator module that contains no tests can mislead you into thinking the Platform failed to discover tests.

## 10. Filtering with `@Tag` and `TestEngine`

### 10.1. Tags in Test Code

In the example suite, `@Tag("smoke")` marks `addsTwoNumbers`, `@Tag("fast")` marks the two invocations of `addsSeveralCases`, and `@Tag("validation")` marks the division-by-zero test.

**Gradle Groovy DSL** to run only the `smoke` tag:

```groovy
tasks.named('test') {
    useJUnitPlatform {
        includeTags 'smoke'
    }
}
```

With the example suite, when this filter is enabled, **only the single test `addsTwoNumbers`** is selected and run. This snippet **replaces the existing `test` configuration block**; do not create multiple blocks with conflicting filters. When you remove the filter, the full suite returns to 5 cases, 1 skipped. To exclude a tag from the run:

```groovy
tasks.named('test') {
    useJUnitPlatform {
        excludeTags 'slow'
    }
}
```

With **Gradle Kotlin DSL**:

```kotlin
tasks.test {
    useJUnitPlatform {
        includeTags("smoke")
    }
}
```

**Maven Surefire** filters Jupiter tags via the `groups` parameter, for example:

```bash
./mvnw -Dgroups=smoke test
```

Or configure the plugin if a module always enforces a fixed test policy:

```xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <configuration>
                <groups>smoke</groups>
            </configuration>
        </plugin>
    </plugins>
</build>
```

This POM snippet is an **illustrative `<build>` block**; in the complete POM in section 4, add `maven-surefire-plugin` inside the existing `<plugins>` element rather than creating a second `<build>`. Spring Boot parent manages the plugin version in the example setup. `groups`/`excludedGroups` can accept tag expressions depending on the Surefire version, though you do not need to force every suite into a single tag.

**Effect of combining multiple filters:** if you simultaneously select `--tests MathPolicyTest.dividingByZeroThrows` (tagged `validation`) and `includeTags 'smoke'`, the intersection of the two filters may be empty. That is a filter conflict, not a missing JUnit Engine.

### 10.2. Engine Filtering

If both Jupiter and Vintage are on the classpath, Gradle can restrict engines:

```groovy
tasks.named('test') {
    useJUnitPlatform {
        includeEngines 'junit-jupiter'
    }
}
```

This only selects tests handled by the Jupiter Engine; it does not automatically migrate JUnit 4 tests to Jupiter. To run JUnit 4 tests via the Platform, you must have **Vintage Engine** and a compatible JUnit 4 dependency; once migration is complete, you can exclude Vintage to prevent legacy tests from accidentally running in unintended ways.

**Note:** engine filters, tag filters, class/method filters, and `@Disabled` operate at different layers. Check each layer separately when tests "disappear."

## 11. `@Disabled`, Assumptions, and "Skipped" vs. "Failed"

Four statuses must be clearly distinguished:

| Status | Meaning | Appropriate action |
| --- | --- | --- |
| **Passed** | Test executed with no failed assertions or unexpected exceptions | Record pass, while still reviewing coverage and assertion quality |
| **Failed/Error** | Assertion mismatch or unexpected exception, setup/engine error... | Inspect stack trace and fix root cause |
| **Skipped/Disabled** | Test was selected but body did not run or aborted conditionally | Check `@Disabled`, `@EnabledOnOs`, assumptions, and reason |
| **Not discovered** | Test was not among descriptors seen by runner/engine | Check source sets, file patterns, engine, and selectors |

`@Disabled("reason")` excludes a test from running; the reason may appear in the report. Assumptions such as `Assumptions.assumeTrue(...)` can **abort** a test at runtime, which reporters typically classify as skipped; this differs from an assertion failure.

**Standalone method-level example** (requires JUnit Jupiter imports):

```java
@Test
void requiresUnix() {
    org.junit.jupiter.api.Assumptions.assumeTrue(
            System.getProperty("os.name").toLowerCase().contains("linux")
    );
    org.junit.jupiter.api.Assertions.assertTrue(true);
}
```

This is an **illustrative method snippet to place inside a valid test class**, not a standalone compilable Java file. Do not copy it verbatim into the section 5 example if you want to preserve the 5-case counts. On non-Linux systems, the test can abort; reports will reflect skipped/aborted accordingly.

A test suite where every test is skipped can produce a green build while **verifying zero business behavior**. When checking CI, track both passed and skipped counts; never use `@Disabled` to mask recurring failures.

## 12. Reading Reports with Evidence

### 12.1. Gradle XML and HTML Reports

Gradle typically generates:

```text
build/test-results/test/TEST-com.example.testing.MathPolicyTest.xml
build/reports/tests/test/index.html
```

In JUnit-style XML, the attributes `tests`, `failures`, `errors`, and `skipped` report summary counts; each `<testcase>` represents a specific case. Display names of parameterized invocations may include argument values, so do not assume there is only one case just because Java has one `@ParameterizedTest` method.

When you need to see which tests ran in the console, Gradle Groovy DSL can enable logging:

```groovy
tasks.named('test') {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat = 'full'
    }
}
```

This **replaces/merges into the existing `test` task configuration**. You do not need to print all `System.out` in CI if logs are noisy or sensitive. Changing `testLogging` affects display only, not JUnit discovery.

### 12.2. Maven Surefire Reports

Surefire typically generates:

```text
target/surefire-reports/TEST-com.example.testing.MathPolicyTest.xml
target/surefire-reports/com.example.testing.MathPolicyTest.txt
```

You can read the console summary or the XML. For the unfiltered example suite, expect **5** total, **1** skipped, **0** failures/errors. If you see `Tests run: 0`, do not assume tests passed: trace why tests were not selected.

An XML report records class names, methods, durations, and skip messages. **Both the task exit code and the XML report matter**: normal test failures make Gradle/Surefire return a non-zero exit code; however, configuring `ignoreFailures`, `testFailureIgnore`, or `skipTests` can let the build continue. Also check how CI evaluates pass/fail.

### 12.3. A Filtered Run Reflects Only the Selected Subset

If you run only `smoke`, 1 passed is **accurate for the smoke subset**, which does not mean the other three tests and one skipped test ran. For full module QA, use an unfiltered run or a dedicated job covering the entire required test set.

## 13. Ensuring the Build Does Not Silently Skip All Tests

### 13.1. Gradle

With a source set containing usable tests, Gradle can still complete `test` with `NO-SOURCE` when sources are empty or `testClassesDirs`/classpath are misconfigured. When passing `--tests`, an unmatched filter normally fails thanks to the filter's `failOnNoMatchingTests` mechanism.

You can configure the filter policy explicitly in Gradle:

```groovy
tasks.named('test') {
    useJUnitPlatform()
    filter {
        failOnNoMatchingTests = true
    }
}
```

**Limitation:** `failOnNoMatchingTests` handles cases where **a selection filter was configured and matched nothing**. It does not automatically make a project with zero test sources fail. For modules that must have tests, add a dedicated CI check (such as verifying XML reports exist and test count > 0) rather than assuming every `test` task fails on empty inputs.

When verifying a specific case, `--tests 'com.example.testing.MathPolicyTest.addsTwoNumbers'` acts as a **witness test**: if it is not recognized, the build must report missing tests rather than silently succeeding.

### 13.2. Maven

For Maven Surefire, you can require failure when no tests exist:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
</plugin>
```

Merge this into `<build><plugins>` in the POM; when using Spring Boot parent, the Surefire version is managed. `failIfNoTests` handles **having no tests at all to run**. `failIfNoSpecifiedTests` is a separate parameter covering cases where the user **specifies `-Dtest=...` with no matches**.

Two options commonly confused:
- `-DskipTests`: skips test execution; test sources normally still compile.
- `-Dmaven.test.skip=true`: skips both test compilation and test execution in plugins honoring this property.

Do not use skip options when the goal is verifying build quality. In CI, **ensure reports are archived** and enforce a minimum expected test count in modules required to have tests; any skip/zero policy must be explicitly justified.

## 14. Cases Where "It Runs in the IDE, but Maven/Gradle Finds Nothing"

| Symptom | Likely cause | Resolution |
| --- | --- | --- |
| IDE runs `MathPolicyTest`, Maven reports 0 tests | Class name does not match Surefire default includes, or different profile/plugin | Rename to `*Test`/`*Tests` or declare `<includes>` explicitly |
| `@Test` compiles, but Gradle does not run Jupiter | Forgot `useJUnitPlatform()` on the `test` task | Configure Platform and verify engine classpath |
| Missing JUnit TestEngine error | `junit-jupiter-engine`/runtime dependency missing or incompatible version | Inspect `testRuntimeClasspath` and dependency tree |
| Imported `org.junit.Test` expecting Jupiter to run | Using JUnit 4 without Vintage Engine | Switch to Jupiter API or add Vintage intentionally |
| Test method `private`, wrong signature, or missing annotation | Jupiter does not recognize it as a valid test | Use package-private `void` method with `@Test` from the right package |
| `@ParameterizedTest` runs 0 times or errors on argument source | No valid provider or empty/mismatched argument source | Check `@CsvSource`, `@ValueSource`, converters, and report |
| Ran `smoke`-tagged tests and `validation` disappeared | Tag filter excluded it | Adjust/remove `includeTags` or `-Dgroups`, check report |
| Tests show as skipped | `@Disabled`, OS condition, assumption | Inspect skip reason and complete tests meant to run |
| Gradle `:test NO-SOURCE` | Tests in wrong folder or empty source set | Check `src/test/java` and custom test tasks |
| Gradle reports `UP-TO-DATE` right after viewing test file | Task result was reused | Inspect existing report, use `--rerun-tasks` when needed |
| Maven `test` skips `*IT` | Surefire defaults target unit test patterns; Failsafe differs | Configure Maven Failsafe in `integration-test`/`verify` phases |
| Running `test` from root misses target module tests | Invoked wrong Gradle subproject or Maven module | Invoke `:module:test` or `-pl module` explicitly |
| Green CI, but no test XML files | Task skipped, skip flag set, different report path, or missing inputs | Check task graph/logs, report directories, and CI command |
| Both Jupiter and Vintage present with unexpected results | Different test engines and engine filters | List engines on test runtime classpath, inspect `include/excludeEngines` |
| Tests pass locally, fail in CI | Different JDK/timezone/locale/env vars/DB/ports/test order | Standardize environment and test isolation; do not skip arbitrarily |

If a test is genuinely not discovered, **identify the first layer where it disappears**: source file → class file → runtime classpath → engine → selector/filter → report. This workflow saves more time than randomly changing annotations or plugin versions.

## 15. Inspecting Test Dependencies and Build Configuration

### 15.1. Gradle

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-platform-launcher --configuration testRuntimeClasspath
```

These commands show **resolved versions** and the dependency paths bringing JUnit Engine/Launcher onto the test runtime. Maven or Gradle may pick a different version than you thought you declared if BOMs, constraints, or overrides exist.

### 15.2. Maven

```bash
./mvnw dependency:tree
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

Look for `org.junit.jupiter` and `org.junit.platform` in the dependency tree and `maven-surefire-plugin` in the effective POM. With a Maven corporate parent or BOM import, make sure the Surefire version supports the Platform. If you override JUnit/Surefire versions, verify compatibility and retest; avoid pinning an isolated artifact while ignoring the version set managed by Spring Boot.

### 15.3. When Do Spring Boot Tests Differ from Plain JUnit?

Jupiter `@Test` and assertions **do not require starting a Spring context**. Examples like `MathPolicyTest` are fast and self-contained.

`@SpringBootTest` is typically needed when testing the full `ApplicationContext`, DI, configuration, or web stack. It can be slower and introduce environment preconditions. **`@SpringBootTest` is not required for JUnit Platform to recognize a `@Test`**. Conversely, when using `@SpringBootTest` with Jupiter, Spring Test provides the extension integrating the context; `spring-boot-starter-test` normally supplies this.

Run plain tests first to verify **discovery**, then add Spring context tests matching business goals. Do not confuse missing datasource, broker, or external service errors with JUnit Engine failing to discover tests.

## 16. A Reliable Build Verification Pipeline

A suitable verification workflow for a Spring Boot module can follow this order:

1. Identify the **module/test source set** and test suite naming conventions.
2. Verify **JDK, Gradle/Maven, Spring Boot, and JUnit** belong to a compatible version set.
3. Ensure **Jupiter API, Engine, and Launcher/provider** are supplied by test dependencies and build config.
4. Run **one witness test by class/method name** to verify selectors.
5. Run the **entire unfiltered test task** and confirm discovered/executed/skipped counts in the report.
6. If a tag policy exists, run subsets like `smoke`/`fast` separately and document each subset's scope.
7. Run `check`/`build` (Gradle) or `verify` (Maven) per the required lifecycle.
8. Archive XML/HTML reports as CI artifacts and preserve a non-zero exit code on test failures.
9. When adding new tests, confirm the executed test count increases as expected or has a valid reason (parameterized, disabled, nested).
10. For modules required to have tests, check **test count > 0** in reports; do not treat `BUILD SUCCESS` as sufficient.

General commands:

```bash
# Gradle:
./gradlew clean test
./gradlew check
./gradlew build

# Maven:
./mvnw clean test
./mvnw verify
```

In CI, you normally do not need to run all three Gradle commands redundantly in a single pipeline: with the Java plugin, `build` already depends on `check`, and `check` runs `test` by default. Choose **one suitable command** and collect reports; when extra debugging is needed, run `test` directly with clearer logging.

### End-of-Lesson Checklist

- [ ] Tests are in `src/test/java` with class names and packages matching build tool conventions.
- [ ] Tests import `org.junit.jupiter.api.Test`; classes/methods are valid for Jupiter.
- [ ] Gradle `test` uses `useJUnitPlatform()`; Maven Surefire supports the Platform.
- [ ] Jupiter Engine (and Launcher when needed) is present on the **test runtime classpath**.
- [ ] `@ParameterizedTest` has a valid argument source; you understand one method can produce multiple test cases.
- [ ] Tested `--tests` or `-Dtest` for at least one specific method.
- [ ] Reports accurately show **tests/failed/errors/skipped** and do not silently run 0 tests.
- [ ] Checked tag/engine filters, `@Disabled`, assumptions, and skip flags in CI.
- [ ] Distinguished plain JUnit unit tests from Spring context integration tests.
- [ ] Re-ran tests and verified real CI/artifact reports after every build logic change.

**Remember:** To trust that a build has been verified, prove the chain **correct test source → compilation → right JUnit Platform/Engine → accurate discovery and filters → real executions → reliable reports and exit codes**. Seeing `@Test` in source code or a `BUILD SUCCESSFUL` line is not enough.

## References

- [Spring Boot 3.3 — Testing](https://docs.spring.io/spring-boot/3.3/reference/testing/index.html)
- [JUnit 5 User Guide — Test Classes and Methods / Running Tests](https://docs.junit.org/5.12.1/user-guide/index.html)
- [Gradle — Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — useJUnitPlatform](https://docs.gradle.org/current/kotlin-dsl/gradle/org.gradle.api.tasks.testing/-test/use-j-unit-platform.html)
- [Maven Surefire — Using JUnit Platform](https://maven.apache.org/components/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Maven Surefire — Inclusion and Exclusion Patterns](https://maven.apache.org/surefire-archives/surefire-3.2.5/maven-surefire-plugin/examples/inclusion-exclusion.html)
