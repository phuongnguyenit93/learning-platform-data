# Selecting Tests to Run and Reading Failure Reports in Spring Boot

## 1. Objective and Mental Model

When working on a Spring Boot project with Maven or Gradle, you do not always need to run the entire test suite. To fix a bug quickly, you can **select a single test class, a test group, or a single method**; before merging/deploying, you must **run all required checks**. When a build fails, the next step is not guessing from the final `BUILD FAILURE` line, but locating **the first failing test case, assertion/exception message, stack trace, and saved report**.

There are three separate questions:

1. **Which tests are selected?** Filter by class/method name, wildcard, JUnit tag, or Gradle task/module.
2. **Did the tests actually run?** Distinguish `Tests run: 0`, `NO-SOURCE`, `SKIPPED` tests, and Gradle `UP-TO-DATE` from tests that executed and passed.
3. **Why did it fail?** Distinguish an expected-value mismatch (assertion failure) from a test runtime exception, compile error, Spring context failure, external connection error, or runner/plugin error.

```text
Change source code / discover bug
               |
               v
Run smallest test reproducing bug
               |
       +-------+---------+
       |                 |
  Test fails           Test passes
       |                 |
Read report,        Were the right tests
fix root cause      actually discovered?
       |                 |
       +---------+-------+
                 |
       Re-run the fixed test
                 |
       Run full suite / test task
                 |
       Check reports and CI build
```

**Principle:** run a single test for fast iteration, **never use a single passing test as proof that the entire project passes**. Ensure all configured unit tests, integration tests, and checks run in their respective pipelines at the end.

## 2. Distinguishing Testing Layers and Execution Tools

| Test type | Example | Common tool/phase |
|---|---|---|
| Java/JUnit 5 unit test | Testing a calculation without a Spring context | Maven Surefire `test`; Gradle `test` |
| Spring test slice | `@WebMvcTest`, `@DataJpaTest` for a slice of the app | Still runs via JUnit 5 and the corresponding test task/goal |
| Spring integration test | `@SpringBootTest`, multi-bean or resource interactions | May run via Surefire or a dedicated task/Failsafe, depending on config |
| End-to-end / smoke | Verifying the deployed application | Separate task/pipeline; not created automatically by adding starter-test |

A `@SpringBootTest` class does not automatically become an integration-test task: categorization depends on **naming conventions and Maven/Gradle configuration**. Spring Boot's `spring-boot-starter-test` provides common testing libraries (including JUnit Jupiter); it **does not automatically create an e2e pipeline**.

### Maven Lifecycle

In Maven:

- `mvn test` runs up to the `test` phase; Surefire normally executes discovered unit tests.
- `mvn package` executes preceding phases, including `test`, then packages if no blocking error occurs.
- `mvn verify` runs through `package` and integration-test phases; **Failsafe only runs integration tests when its plugin/execution is configured**. Do not assume `verify` generates integration tests on its own.
- Surefire typically writes reports to `target/surefire-reports`.
- Failsafe typically writes reports to `target/failsafe-reports`.

### Gradle Task Graph

In Gradle Java/Spring Boot:

- `./gradlew test` runs the `test` task (the default test source set).
- `./gradlew check` runs verification tasks registered by the project; in the Java plugin this normally includes `test`.
- `./gradlew build` normally depends on `assemble` and `check`; when tests fail, the build fails.
- Tasks such as `integrationTest` **exist only when the build script/plugin creates them**.
- Default HTML reports for the `test` task normally live at `build/reports/tests/test/index.html`; JUnit XML normally lives at `build/test-results/test/`.

**Note:** multi-module builds have separate reports per module. If `service-api:test` fails, open `service-api/build/reports/tests/test/index.html`, not an assumed root `test` report.

## 3. Maven Surefire: Selecting Classes and Test Groups

Assuming a Maven Wrapper is present, open a terminal at the root containing `pom.xml` and `mvnw`. On Linux/macOS:

```bash
# Run all unit tests per project config
./mvnw test

# Run exactly one test class
./mvnw -Dtest=TotalCalculatorTest test

# Use fully qualified class name to avoid name collisions
./mvnw -Dtest=com.example.testing.TotalCalculatorTest test

# Select by naming pattern
./mvnw "-Dtest=*CalculatorTest" test

# Select multiple classes (comma-separated list)
./mvnw "-Dtest=TotalCalculatorTest,TotalCalculatorRegressionTest" test

# Select JUnit 5 tests tagged fast
./mvnw -Dgroups=fast test

# Exclude tests tagged regression
./mvnw -DexcludedGroups=regression test
```

In Windows PowerShell, use `.\mvnw.cmd`, for example:

```powershell
.\mvnw.cmd "-Dtest=TotalCalculatorTest" test
.\mvnw.cmd "-Dtest=TotalCalculatorTest,TotalCalculatorRegressionTest" test
.\mvnw.cmd "-Dgroups=fast" test
```

If there is no Maven Wrapper, replace `./mvnw` with an installed `mvn`. Quote `-D...` arguments when they contain special characters (`*`, `#`, commas, `!`), especially across Bash/PowerShell/CI.

### 3.1. Default Test Discovery Rules

Without `-Dtest` and without custom include/exclude rules, Maven Surefire typically discovers classes matching:

```text
**/Test*.java
**/*Test.java
**/*Tests.java
**/*TestCase.java
```

For example, `TotalCalculatorTest` is discovered; `TotalCalculatorIT` targets Failsafe by default if configured, not Surefire. Nested tests, parameterized tests, custom JUnit engines, and complex patterns may require explicit configuration or specific filtering.

**Selecting by class** is the safest approach when trying out a new JUnit Jupiter project. Surefire also supports method filtering syntax `-Dtest=ClassName#methodName`, though plugin docs note provider/framework nuances for certain method patterns (historically noting JUnit 4/TestNG); with JUnit Jupiter, **check your Surefire version and confirm the actual number of tests executed** before relying on single-method selection. Example syntax:

```bash
./mvnw "-Dtest=TotalCalculatorTest#addsShipping" test
```

When filtering JUnit 5 tests by a stable, CI-reproducible group, use `@Tag` combined with `-Dgroups`/`-DexcludedGroups` or JUnit Platform configuration rather than fragile dynamic name patterns.

### 3.2. Understanding "No Tests Found"

With `-Dtest=MissingTest`, Surefire **fails by default** if the specified test cannot run (`surefire.failIfNoSpecifiedTests=true`). This is a **selection/discovery** error, not an assertion failure.

You can deliberately run:

```bash
./mvnw "-Dtest=MissingTest" test
```

to recognize a mistyped selection. When the tool reports "No tests matching pattern", check the exact package/class, JUnit engine, `src/test/java` path, and task/goal.

In a multi-module Maven reactor, `-pl :service -am -Dtest=SomeTest test` can pass `-Dtest` to upstream dependency modules that do not contain that class. Once you understand the scope, you can pass `-Dsurefire.failIfNoSpecifiedTests=false` so modules **without the named test** do not block the build, while still verifying the target module actually ran the test. Never apply this flag across all pipelines just to hide mistyped class names.

### 3.3. Skipping Tests Is Not Selecting Tests

| Maven option | Result | When to consider |
|---|---|---|
| `-Dtest=SomeTest` | Runs only tests matching the Surefire filter | Local bug reproduction |
| `-Dgroups=fast` | Runs tests with the matching JUnit 5 tag | Managed fast test subset |
| `-DskipTests` | Skips Surefire test execution while typically still compiling test sources | Temporary action, never a substitute for QA |
| `-Dmaven.test.skip=true` | Skips both test compilation and execution per supporting plugins | Only for specific justified cases |
| `-DskipITs` | Skips integration tests via Failsafe | Separating pipelines when needed |

With **Failsafe 3.6.0 and later**, `-DskipTests` no longer automatically skips Failsafe; use `-DskipITs` to skip integration tests, or `-Dmaven.test.skip=true` when intentionally skipping both unit and integration tests. Always check plugin versions and logs, since a parent POM may define custom settings.

**Never accept `BUILD SUCCESS` from a test-skipping command as proof that the test suite passed.** Any skipping must be explicitly recorded in CI/release results.

## 4. Maven Failsafe: Integration Tests and Separate Reports

**Surefire** normally runs unit tests in the `test` phase. **Failsafe** is designed to run integration tests via the `integration-test` and `verify` goals. Failsafe avoids halting the lifecycle too early when an integration test fails, letting the `post-integration-test` phase clean up resources (if configured).

If a project has integration tests named `*IT` or `IT*`, **add a Failsafe execution**. Insert the following **into `<build><plugins>` of an existing POM**, not as a standalone POM file:

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-failsafe-plugin</artifactId>
    <version>3.6.1</version>
    <executions>
        <execution>
            <goals>
                <goal>integration-test</goal>
                <goal>verify</goal>
            </goals>
        </execution>
    </executions>
</plugin>
```

Then:

```bash
# Includes integration-test and verify/cleanup phases per lifecycle
./mvnw verify

# If selecting a specific IT class for Failsafe:
./mvnw "-Dit.test=TotalCalculatorIT" verify
```

If a Surefire test fails in the `test` phase, Maven stops **before** reaching Failsafe phases. To inspect integration reports, fix the unit test first or run a configuration specifically designed to isolate integration tests. **Never run only the `integration-test` phase as the final step** if the pipeline relies on post-integration-test cleanup and `verify`.

Failsafe report paths are typically:

```text
target/failsafe-reports/
├── TEST-com.example.testing.TotalCalculatorIT.xml
├── com.example.testing.TotalCalculatorIT.txt
└── failsafe-summary.xml
```

Paths, filenames, and file counts vary by configuration; do not assume reports exist if the plugin did not run. `failsafe-summary.xml` records the aggregate status used by `verify` to decide whether the build succeeds or fails.

## 5. Gradle: Selecting Test Classes and Methods with --tests

When a project uses the Gradle Wrapper:

```bash
# Run the full test task
./gradlew test

# Run a single class only
./gradlew test --tests "com.example.testing.TotalCalculatorTest"

# Run a single JUnit Jupiter method
./gradlew test --tests "com.example.testing.TotalCalculatorTest.addsShipping"

# Use simple class name (starting with an uppercase letter)
./gradlew test --tests "TotalCalculatorTest"

# Wildcard for classes ending in CalculatorTest
./gradlew test --tests "*CalculatorTest"

# Multiple --tests filters (union of matched names)
./gradlew test --tests "*CalculatorTest" --tests "*RegressionTest"

# Tests of one module in a multi-project build:
./gradlew :service:test --tests "*CalculatorTest"

# Print more logs when inspecting the runner:
./gradlew test --tests "*RegressionTest" --info
```

PowerShell uses `.\gradlew.bat` instead of `./gradlew`. In Gradle, method filtering uses `ClassName.methodName` (a dot), unlike Maven Surefire's `#` separator. The `--tests` filter is passed by Gradle to the **`Test` task**, not as a Java launcher flag.

**No matching tests** normally causes Gradle to report `No tests found for given includes`: verify the actual method, class/package, framework, Java test source set, and any static filters in `build.gradle`. Never fix this by deleting error checks in CI.

### 5.1. Gradle Incremental Builds and Re-Running

Gradle optimizes tasks via up-to-date checks and build caching. If `test` is marked `UP-TO-DATE`, do not assume it just executed every test in a fresh JVM. When investigating flaky failures or reproducing in a clean run:

```bash
./gradlew test --tests "TotalCalculatorTest" --rerun-tasks
```

`--rerun-tasks` forces re-execution of the task and its task dependencies, without meaning a full `clean` of the build directory. Use `--info`/`--stacktrace` for Gradle diagnostics when needed, noting that **Gradle stack traces** primarily describe task-level errors; assertion causes are usually much clearer in the **HTML/XML test report**.

### 5.2. JUnit 5 Tags in Gradle

Tag a class/method, for example:

```java
@Tag("fast")
@Test
void addsShipping() {
    // test logic
}
```

This is only **a method-level annotation snippet**, not a standalone Java class. In `build.gradle` (Groovy DSL):

```groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        includeTags 'fast'
    }
}
```

This configuration makes the `test` task **run only the `fast` tag** on all subsequent invocations. When you want the full suite, remove/adjust the filter or create a dedicated test task; CLI `--tests` does not necessarily override a configured JUnit tag filter. You can define separate `fastTest`/`integrationTest` tasks to keep filtering policy explicit and avoid "passing tests" that silently skip large parts of the suite.

## 6. Hands-On Java 17 Spring Boot Project with an Intentional Test Failure

We will create **a runnable example** with two test classes:

- `TotalCalculatorTest`: **two passing tests**.
- `TotalCalculatorRegressionTest`: **one intentionally failing test** due to a wrong expected value, to practice reading failure reports.

After observing the failure, fix the expected value and re-run the entire suite. The example pins **Spring Boot 3.5.0** and **Java 17** for learning purposes without claiming they are the latest versions. Your machine needs a compatible Maven or Maven Wrapper, JDK 17+, and access to dependency repositories.

### 6.1. File Structure

```text
test-report-lab/
├── pom.xml
└── src/
    ├── main/java/com/example/testing/
    │   ├── TestReportApplication.java
    │   ├── TotalCalculator.java
    │   └── CalculatorConsole.java
    └── test/java/com/example/testing/
        ├── TotalCalculatorTest.java
        └── TotalCalculatorRegressionTest.java
```

### 6.2. Complete pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>test-report-lab</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
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
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

Here Surefire **3.6.1** is declared explicitly to stabilize the example; do not assume every Spring Boot parent uses this exact version automatically. `spring-boot-starter-test` provides JUnit Jupiter and the required testing tools.

### 6.3. Application Source and Plain Java Logic

`src/main/java/com/example/testing/TestReportApplication.java`:

```java
package com.example.testing;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestReportApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestReportApplication.class, args);
    }
}
```

No web starter is declared, so the example requires neither a web server nor a database. The unit tests we are creating **do not need to start a Spring context**: they run fast, have minimal environment dependencies, and make assertion failures easy to diagnose.

`src/main/java/com/example/testing/TotalCalculator.java`:

```java
package com.example.testing;

public final class TotalCalculator {
    public int total(int price, int shipping) {
        if (price < 0 || shipping < 0) {
            throw new IllegalArgumentException(
                    "price and shipping must be nonnegative");
        }
        return Math.addExact(price, shipping);
    }
}
```

`src/main/java/com/example/testing/CalculatorConsole.java`:

```java
package com.example.testing;

public final class CalculatorConsole {
    public static void main(String[] args) {
        int result = new TotalCalculator().total(100, 20);
        System.out.println("total=" + result);
    }
}
```

You can verify the **plain Java logic** with JDK 17 without Maven/Spring Boot:

```bash
javac -d out \
  src/main/java/com/example/testing/TotalCalculator.java \
  src/main/java/com/example/testing/CalculatorConsole.java

java -cp out com.example.testing.CalculatorConsole
```

Exact stdout of `java -cp ...`:

```text
total=120
```

On PowerShell, you can write the `javac` command on one line using similar paths; running `java -cp out ...` does not change. `CalculatorConsole` is just a simple logic check, does not start a Spring context, and does not replace unit tests.

### 6.4. Passing Test Class

`src/test/java/com/example/testing/TotalCalculatorTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@Tag("fast")
class TotalCalculatorTest {
    private final TotalCalculator calculator = new TotalCalculator();

    @Test
    void addsShipping() {
        assertEquals(120, calculator.total(100, 20));
    }

    @Test
    void rejectsNegativeAmounts() {
        assertThrows(
                IllegalArgumentException.class,
                () -> calculator.total(-1, 20)
        );
    }
}
```

This class contains **2 test methods**, both passing against the `TotalCalculator` implementation. The `fast` tag supports selection via Surefire or Gradle JUnit Platform configuration.

### 6.5. Intentionally Failing Test Class

`src/test/java/com/example/testing/TotalCalculatorRegressionTest.java`:

```java
package com.example.testing;

import org.junit.jupiter.api.Tag;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

@Tag("regression")
class TotalCalculatorRegressionTest {
    @Test
    void detectsWrongExpectation() {
        TotalCalculator calculator = new TotalCalculator();

        // Intentionally wrong: 100 + 20 = 120, not 130.
        assertEquals(130, calculator.total(100, 20));
    }
}
```

This `@Test` **fails intentionally**. `TotalCalculator` itself correctly returns `120`, while the test expects the wrong value `130`. This example distinguishes a "code bug" from a "wrong assertion/specification": reports show expected vs. actual values, yet the engineer still must verify the **business contract** to know whether to fix the code or the expected value.

## 7. Maven Practice: Selecting Tests, Triggering Failure, and Reading Reports

Run from the project root containing `pom.xml`. Use `./mvnw` when a wrapper is present (Windows PowerShell: `.\mvnw.cmd`). If no wrapper exists and Maven is installed, use `mvn`.

### 7.1. Running Only the Passing Class

```bash
./mvnw -Dtest=TotalCalculatorTest test
```

With the exact sources above and no environment issues, Surefire runs the 2 tests in `TotalCalculatorTest`; expected result:

```text
Tests run: 2, Failures: 0, Errors: 0, Skipped: 0
BUILD SUCCESS
```

These are the **summary lines to look for**, not verbatim output of the entire console. Maven/plugin logs, timings, and formatting may vary.

### 7.2. Running All Tests and Observing the Intentional Failure

```bash
./mvnw test
```

Surefire discovers both classes via the `*Test` pattern. Expected result in the example:

```text
Tests run: 3, Failures: 1, Errors: 0, Skipped: 0
BUILD FAILURE
```

The failing method is `TotalCalculatorRegressionTest.detectsWrongExpectation`. Key log output may include:

```text
org.opentest4j.AssertionFailedError: expected: <130> but was: <120>
```

That assertion error line represents the **invariant semantic content** in the example; stack trace layout, timings, and console details depend on the runner/JUnit version. Read the stack trace down to the **Java file and line containing `assertEquals`**, not just the exception class.

### 7.3. Running Only the Failing Class for a Fast Fix

```bash
./mvnw -Dtest=TotalCalculatorRegressionTest test
```

Read the reports:

```text
target/surefire-reports/
├── TEST-com.example.testing.TotalCalculatorRegressionTest.xml
└── com.example.testing.TotalCalculatorRegressionTest.txt
```

Under the report directory, there may also be files for passing classes, fork JVM dump/stream logs if a fork crashed, or reports from prior runs. **Do not sum stale reports** to infer test counts from the current run unless outputs were cleaned. Use `./mvnw clean test` to wipe prior outputs and re-run when a clean baseline is needed.

### 7.4. Fixing the Expected Value and Re-Running the Full Suite

In `TotalCalculatorRegressionTest.java`, change:

```java
assertEquals(130, calculator.total(100, 20));
```

to:

```java
assertEquals(120, calculator.total(100, 20));
```

Then run:

```bash
./mvnw -Dtest=TotalCalculatorRegressionTest test
./mvnw clean verify
```

Expected Surefire suite result once all tests above pass after the fix:

```text
Tests run: 3, Failures: 0, Errors: 0, Skipped: 0
```

Whether `verify` succeeds still depends on any additional project build steps; if Failsafe or integration tests are added later, account for them too. **Never blindly edit assertions just to turn tests green in a real project**: only change an expected value when requirements/business specifications confirm the original expectation was wrong.

## 8. Reading Surefire/Failsafe Reports Step by Step

Maven Surefire reports typically come in two formats:

- `target/surefire-reports/com.example.testing.TotalCalculatorRegressionTest.txt`: plain text summary and stack trace, fast to read in an editor or terminal.
- `target/surefire-reports/TEST-com.example.testing.TotalCalculatorRegressionTest.xml`: XML test report format suited for CI/Jenkins/GitHub Actions or aggregation tools.

### 8.1. Which Fields Matter in the XML?

A test failure typically has a **simplified illustrative** structure:

```xml
<testsuite name="com.example.testing.TotalCalculatorRegressionTest"
           tests="1" errors="0" skipped="0" failures="1">
    <testcase name="detectsWrongExpectation"
              classname="com.example.testing.TotalCalculatorRegressionTest">
        <failure type="org.opentest4j.AssertionFailedError"
                 message="expected: &lt;130&gt; but was: &lt;120&gt;">
            <!-- Stack trace; file location and assertEquals line -->
        </failure>
    </testcase>
</testsuite>
```

This is a **simplified XML schema**, not character-for-character output emitted by Surefire; real XML may include timestamps, durations, properties, CDATA sections, and additional attributes.

Field meanings:

| Field | What to read |
|---|---|
| `tests` | Total test cases recorded for the suite |
| `failures` | Assertions that failed against expected values |
| `errors` | Other errors while running tests, such as unexpected exceptions or setup failures |
| `skipped` | Tests skipped due to `@Disabled`/assumptions/conditions |
| `testcase name` | Method name or display name of the failing test |
| `failure/error message` | Expected/actual values or exception message |
| Stack trace | Class, method, file, and line leading to the failure |
| `time` | Execution duration; useful for spotting slow tests, though insufficient alone to diagnose bottlenecks |

In some frameworks/reports, assertions may be categorized slightly differently; always rely on the **message and stack trace** as the primary source for root cause.

### 8.2. Different Failure Signatures

| Symptom | Initial diagnosis |
|---|---|
| `AssertionFailedError: expected ... but was ...` | Compare spec/test data against actual result; inspect the assertion line |
| `NullPointerException` inside test | Check whether failure stems from test setup, an unstubbed mock, or production code |
| `IllegalStateException: Failed to load ApplicationContext` | Read the deepest `Caused by` in the chain, Spring/test slice config, beans, datasource |
| `UnsatisfiedDependencyException` | Bean failed creation or lacks a dependency; inspect nested cause, not just the outer exception |
| `BeanCreationException` | Missing property config, profile, datasource, migration, or mock |
| `ConnectException` / timeout | External service/database/test container unready or networking issue |
| `NoClassDefFoundError` / `ClassNotFoundException` | Test/runtime classpath, dependency scope, exclusions, plugin version |
| `Tests run: 0` or missing reports | Discovery/filter/scope/task selected zero tests—not proof of passing |
| Forked VM terminated / timeout | JVM OOM, `System.exit`, fork/timeout limits, native crash; inspect dump/stream files |

Spring context errors often wrap **multiple nested exception layers**. Follow `Caused by` down to the root cause, especially at the bottom of the chain; do not try to fix only the outer `Failed to load ApplicationContext` wrapper.

### 8.3. Console Review Workflow

1. Identify which **module/task** failed.
2. Locate the test summary line: `Tests run`, `Failures`, `Errors`, `Skipped`.
3. Locate the failing **class/method** name.
4. Open the `.txt` or `TEST-*.xml` file in the right module under `surefire-reports`/`failsafe-reports`.
5. Locate the expected/actual message, stack trace, and the **first frame inside your own test/application code**.
6. Distinguish **assertion**, **exception**, **initialization**, **fork**, and **zero-selection** errors.
7. Re-run the **smallest failing test** with the same JDK/profile/data.
8. After fixing, re-run the full suite and inspect reports/CI rather than trusting a single passing test.

Surefire HTML reports can be generated using **Maven Surefire Report Plugin** when configured. Surefire itself normally outputs TXT/XML; do not assume `target/surefire-reports` includes HTML like Gradle does.

## 9. Gradle Configuration for the Same JUnit 5 Example

If a project uses **Gradle instead of Maven**, keep the Java/JUnit classes from section 6 unchanged and place `settings.gradle` and `build.gradle` at the root. This is a **complete Groovy DSL configuration for the lesson** (do not leave both Maven and Gradle running unless intentionally maintaining dual builds):

`settings.gradle`:

```groovy
rootProject.name = 'test-report-lab'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.5.0'
    )
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()

    reports {
        html.required = true
        junitXml.required = true
    }

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
    }
}
```

Requirements: JDK 17+, a Gradle version compatible with Spring Boot 3.5 (for instance **Gradle 8.14+** in the 8.x line), and a pre-generated Gradle Wrapper. `spring-boot-starter-test` brings in JUnit Jupiter; `useJUnitPlatform()` is essential so the `test` task runs JUnit Jupiter tests. `junit-platform-launcher` is added to the test runtime classpath with its version managed by the BOM.

### 9.1. Running by Class, Method, or Full Suite

```bash
# Only the 2 passing tests
./gradlew test --tests "TotalCalculatorTest"

# Select one JUnit 5 method
./gradlew test --tests "TotalCalculatorTest.addsShipping"

# Only the wrong-expectation test (intentionally failing task)
./gradlew test --tests "TotalCalculatorRegressionTest"

# Full suite (1 intentional failure until fixed)
./gradlew test
```

When a test fails, Gradle prints something like:

```text
> Task :test FAILED
There were failing tests.
See the report at: .../build/reports/tests/test/index.html
BUILD FAILED
```

The `...` segment is an **environment-specific path**, not exact verbatim output. After changing the expected value to `120`, re-run:

```bash
./gradlew test --rerun-tasks
./gradlew check
```

On Windows, replace `./gradlew` with `.\gradlew.bat`. Omit `--tests` on the final run when verifying the complete suite.

### 9.2. Reading Gradle Reports

Typical structure after the `test` task:

```text
build/
├── reports/tests/test/
│   ├── index.html
│   ├── classes/
│   └── packages/
└── test-results/test/
    ├── TEST-com.example.testing.TotalCalculatorTest.xml
    └── TEST-com.example.testing.TotalCalculatorRegressionTest.xml
```

Open `build/reports/tests/test/index.html` in a browser to inspect:

- Total **tests**, **failures**, **ignored/skipped**, duration, and success rate.
- Tabs/panels by **class**, **package**, and failed test cases.
- Stack traces with method, file, and line captured by the reporter.
- Standard output/error captured per test when enabled by version/configuration.

XML data is ideal for CI machine parsing, whereas HTML is usually easiest to read while debugging. Do not confuse `:service:test` reports with `:other-module:test`; each task/module has its own directory.

**If HTML reports are not generated**, check whether the `test` task actually executed, `reports.html.required`, write permissions on `build`, or whether the build script redirected report destinations. `--stacktrace` details Gradle task failures, not JUnit assertion reports.

## 10. Selecting Tests by Tag, Condition, and Naming Convention

JUnit Jupiter supports `@Tag("fast")`, `@Tag("regression")`, `@Disabled`, `@EnabledOnOs`, `@EnabledIfEnvironmentVariable`, and more. These affect discovery/execution without automatically creating separate Maven/Gradle tasks.

| Filter | When to use |
|---|---|
| Class name | Quickly fixing a failing class |
| Method name | Checking a single behavior; Gradle `--tests Class.method` supports this directly |
| JUnit tag | Fast/slow/regression suites with clear policies |
| Specific Gradle task | `test`, `integrationTest`, or custom declared tasks |
| Maven Surefire/Failsafe | Splitting unit and integration tests by phase/config |
| Maven/Gradle module selector | Multi-module builds running only affected parts |

A `@Disabled` test is discovered with status **skipped**, unlike a test excluded from discovery by a non-matching filter. A filtered-out test may **not appear in the current report at all**. When auditing test counts, compare **expected suite size** against tests actually executed—not merely `failures = 0`.

### Spring Boot `@SpringBootTest` vs. Plain Unit Tests

`@SpringBootTest` starts the `ApplicationContext`, making it slower and sensitive to environment/profiles/beans. For logic independent of Spring, plain Java unit tests like our example are the right choice. For controllers/repositories, prefer slice tests when only one functional layer is needed. For integration tests needing databases, message brokers, or external services, manage lifecycles, resources, and readiness explicitly.

Therefore, when a test fails:

- Unit test: inspect assertions, inputs/outputs, and mocks first.
- Slice test: inspect slice configuration and mocked/included beans.
- `@SpringBootTest`: trace the stack trace to the root cause, profiles, datasource, and imported configs.
- Integration/e2e: check application logs, container/service logs, timeouts, and test data.

## 11. Common Configuration Mistakes When Selecting and Running Tests

| Symptom | Cause to check | Resolution |
|---|---|---|
| Maven runs `test` with 0 tests | Name does not match Surefire patterns or missing engine | Check `src/test/java`, class names, and JUnit dependencies |
| `-Dtest=FooTest` reports not found | Wrong name/package or test compilation skipped | Verify actual class name, target module/POM, and discovery logs |
| Maven method filter behaves unexpectedly | Surefire provider/version and `#method` syntax | Select the whole class or use tags; confirm executed count |
| Gradle `No tests found for given includes` | Wrong `--tests` pattern, extra filter, or test not discovered | Use FQN class name; check `test` config and JUnit Platform |
| Gradle `UP-TO-DATE` | Task was deemed unnecessary to re-run | Pass `--rerun-tasks` when observing a fresh run is needed |
| Maven `BUILD SUCCESS` despite running nothing | Skip flag, no tests, or overly narrow filter | Check `Tests run`, `skipTests`, `maven.test.skip` |
| One test passes locally, yet CI is still red | Another suite failed, IT failed, or another plugin failed | Run full `verify`/`check` and inspect the right report |
| Spring context fails | Wrong profile, missing bean, datasource/test config issue | Read the root `Caused by`, not just the wrapper exception |
| Passes locally, fails in CI | Different Java version, timezone, locale, concurrency, paths, env/secrets, external services | Align JDK, args, profiles, data, and inspect logs |
| Random test failures | Shared state, ordering, races, timing, external services | Reproduce systematically, isolate state; do not rely solely on retries |
| Reading stale reports | Task did not run or outputs were not cleaned | Verify timestamps/logs; use `clean` or `--rerun-tasks` appropriately |
| Gradle produces no HTML report | Reporting disabled or task did not execute | Check `reports.html.required` and correct module directory |
| Maven has Failsafe configured, yet skips ITs | Goals unbound or only `test` invoked | Configure Failsafe executions and run `verify` |
| CI reports failure while local run showed 3 passes | Different task/module/profile or broader suite | Compare exact commands, selectors, and XML/HTML artifacts |

### What Is a Flaky Test?

A **flaky test** can pass or fail without code changes due to environment, timing, ordering, concurrency, or data issues. Surefire offers a mechanism to re-run failing tests (`surefire.rerunFailingTestsCount` in supported versions), but retries **do not fix root causes** and can hide failure signals if only final pass status is inspected.

When triaging a flaky test:
1. Record the test class/method, seed, JDK, runner, CI configuration, and timestamp.
2. Run the test alone and together with its suite (to uncover order dependence).
3. Inspect shared databases/files, clocks, networking, parallelism, and static mocks.
4. Collect reports from every retry attempt; never discard evidence.
5. Fix the nondeterminism and re-run the full suite.

## 12. Build Verification Workflow Before Merge/Release

1. **Reproduce narrowly:** select the failing class/method/tag.
2. **Explain the failure:** open the report and compare expected/actual values and stack trace.
3. **Fix root cause:** update logic or assertion only after confirming the true contract.
4. **Verify locally:** re-run the exact test and confirm it passes.
5. **Run related group:** service tests, slice tests, database tests...
6. **Run required suite:** Maven `verify` or Gradle `check`/`build` per project configuration.
7. **Audit counts:** are total tests/failed/errors/skipped counts reasonable?
8. **Archive CI reports:** upload/publish JUnit XML and HTML if needed so failures remain traceable.
9. **Never mask failures:** avoid skip flags, `ignoreFailures`, `testFailureIgnore`, or filters selecting only passing tests.
10. **Verify environment:** JDK, build tool version, test profiles, external services, credentials.

**Self-assessment checklist:**

- [ ] Know whether tests are selected via Surefire `-Dtest` or Gradle `--tests`.
- [ ] Know whether class names and method names are discoverable by the framework.
- [ ] Checked actual executed test counts rather than relying solely on a green build.
- [ ] Located the right report in `target/surefire-reports`, `target/failsafe-reports`, or `build/reports/tests/test`.
- [ ] Read the failing testcase name, assertion/exception, and stack trace down to project code lines.
- [ ] Distinguished assertion failures, runtime errors, Spring context errors, and discovery failures.
- [ ] After fixing, re-ran **the entire required test suite**, not just one method.
- [ ] Did not skip integration tests merely because Surefire unit tests passed.
- [ ] Did not publish sensitive information from test logs, reports, or stack traces.

**Remember:** Test filtering speeds up the dev loop, **reports pinpoint failures accurately**, and only **re-running the required suite/phase/task** proves the build is ready to proceed.

### Official Reference Documentation

- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/)
- [Maven Surefire — Running a Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html)
- [Maven Surefire — Test Goal Parameters](https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html)
- [Maven Surefire — Introduction and Reports](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Failsafe — Integration Tests and Reports](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Gradle — Testing in Java/JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html)
