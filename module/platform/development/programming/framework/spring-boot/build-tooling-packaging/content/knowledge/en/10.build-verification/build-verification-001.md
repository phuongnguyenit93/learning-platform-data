# Integrating Unit Testing with Maven Surefire and Gradle Test in Spring Boot

## 1. Purpose and Why Tests Must Be Integrated into the Build

**Unit tests** verify a small unit of behavior such as a method, class, or service under controlled input conditions. The unit under test should run fast, be reproducible, and not depend on a database, HTTP server, or external services. A Spring Boot project can write unit tests using **JUnit Jupiter** (JUnit 5) and use **Mockito** to replace collaborators, but for tests to actually run during the build, you also need to integrate with Maven's or Gradle's **test execution engine**.

In a Maven project, most Java unit tests are run by the **Maven Surefire Plugin** at the `test` phase. In a Gradle project with the Java plugin, unit tests are run by a task of type **`Test`**, usually named `test`. For JUnit Jupiter, Gradle requires configuring `useJUnitPlatform()`.

After this lesson, you will be able to:

1. Distinguish **JUnit/Mockito** as test authoring libraries from **Surefire/Gradle Test** as the mechanism for discovering, executing, and reporting tests.
2. Place source and test code in standard Maven/Gradle directories; create a Java 17+ unit test that runs on both build systems.
3. Properly configure `spring-boot-starter-test`, Surefire 3.x, or Gradle `useJUnitPlatform()`.
4. Run all tests or a single test class/method on Windows and Linux, and read exit codes, test counts, and XML/HTML reports.
5. Integrate tests into Maven's `package`/`verify` and Gradle's `build`/`check` or CI.
6. Identify skipped tests, undiscovered tests, or slow tests caused by loading the Spring ApplicationContext, and know how to investigate them.

**Running example:** uses Java 17 and Spring Boot 3.3.5 to illustrate configuration. Version numbers are intentional examples and are not assumed to be the latest Spring Boot release; when applying this in practice, use the versions managed by your real project and a compatible Gradle/Maven Wrapper.

## 2. What Roles Do JUnit, Mockito, Surefire, and Gradle Test Play?

| Component | Role | Where does it run? |
| --- | --- | --- |
| **JUnit Jupiter** | `@Test`, `@ParameterizedTest`, assertions, lifecycle callbacks | Runs on **JUnit Platform** via a test engine |
| **Mockito** | Creates mocks/stubs, verifies interactions with dependencies | Inside unit test code |
| **Spring Boot Starter Test** | Bundles JUnit Jupiter, Spring Test, AssertJ, Mockito, and common test tools | Dependency on the **test classpath** |
| **Maven Surefire** | Discovers and executes unit tests at Maven's `test` phase | Maven lifecycle, writes reports to `target/surefire-reports/` |
| **Gradle Test** | Test task of the Java/JVM plugin, filters tests and executes via JUnit Platform when configured | Gradle task graph, reports under `build/` |

For example, a `GreetingServiceTest` class with `@Test` only **describes** tests. It gets executed when Maven Surefire or Gradle Test detects the right JUnit engine and selects that class. **Successfully compiling tests does not prove that tests were run**.

Spring Boot Starter Test manages a compatible set of test libraries aligned with the Boot/BOM version, reducing manual version matching for JUnit, Mockito, and related dependencies. However, Starter Test **does not replace the build tool's plugin/task**. Maven still needs a compatible Surefire, and Gradle still needs `Test` configured to use JUnit Platform.

### Flow of a Unit Test Run

~~~text
Java source: src/main/java
             |
             v
       compileJava / compile
             |
Java tests: src/test/java
             |
             v
       compileTestJava / testCompile
             |
             v
JUnit Jupiter annotations + Test Engine
             |
             +-- Maven Surefire at the test phase
             |      -> target/surefire-reports/
             |
             +-- Gradle test task
                    -> build/test-results/test/
                    -> build/reports/tests/test/
             |
             v
       PASS / FAIL / SKIPPED + build exit code
~~~

In practice, Maven and Gradle name their tasks/goals differently; the diagram above describes the **logical flow**, not verbatim printed logs.

## 3. Shared Directory Structure for Maven and Gradle

The examples in this lesson are placed in a project named `unit-test-demo`:

~~~text
unit-test-demo/
├── pom.xml                     # Used when choosing Maven
├── mvnw
├── mvnw.cmd
├── .mvn/wrapper/
├── build.gradle                # Used when choosing Gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── gradle/wrapper/
└── src/
    ├── main/java/com/example/demo/
    │   ├── DemoApplication.java
    │   ├── GreetingService.java
    │   └── PriceService.java
    └── test/java/com/example/demo/
        ├── GreetingServiceTest.java
        └── PriceServiceTest.java
~~~

The diagram shows **both build options** for comparison; in practice, choose **Maven or Gradle** matching your initialized project. You do not need to maintain both sets of build files/Wrappers in a real project.

Java files can stay identical when switching between Maven and Gradle because both use the standard `src/main/java`, `src/test/java` layout and the `com.example.demo` package. Maven also supports `src/test/resources`; the Gradle Java plugin has an equivalent `test` source set.

### File `src/main/java/com/example/demo/DemoApplication.java`

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

The sample application has a valid Spring Boot main class so both Maven and Gradle Spring Boot JAR packaging tasks have an entry point. Because it only uses `spring-boot-starter`, the application **does not need to open an HTTP port**.

### File `src/main/java/com/example/demo/GreetingService.java`

~~~java
package com.example.demo;

public final class GreetingService {

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        return "Hello, " + name.trim();
    }
}
~~~

This class is Java 17+ code independent of the Spring ApplicationContext. It is an ideal target for unit testing because its input/output logic is clear and requires no external environment connections.

### File `src/test/java/com/example/demo/GreetingServiceTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class GreetingServiceTest {

    private final GreetingService service = new GreetingService();

    @Test
    void greetsAndTrimsName() {
        assertEquals("Hello, An", service.greet(" An "));
    }

    @Test
    void rejectsNull() {
        IllegalArgumentException ex = assertThrows(
                IllegalArgumentException.class,
                () -> service.greet(null)
        );
        assertEquals("Name must not be blank", ex.getMessage());
    }

    @ParameterizedTest
    @ValueSource(strings = {"", "   "})
    void rejectsBlankNames(String value) {
        assertThrows(IllegalArgumentException.class,
                () -> service.greet(value));
    }
}
~~~

**Explanation:**

- `@Test` marks two independent test methods.
- `assertEquals` compares the **actual value** against the expected value.
- `assertThrows` verifies the exception type and allows inspecting the error message.
- `@ParameterizedTest` runs the same logic for **two datasets** `""` and `"   "`; JUnit reports multiple corresponding executions.
- The test does not use `@SpringBootTest` because there is no need to load the Spring container. JUnit Jupiter allows test methods and test classes to omit `public`.

When the runner supports JUnit Jupiter and `junit-jupiter-params` is on the test classpath (provided by Starter Test in the example configuration), all assertions must pass. Do not assume fixed log line counts or execution times: plugins and log verbosity vary by version.

## 4. Maven Option: Integrating with Surefire

### 4.1. A Minimal `pom.xml` for the Example

This is a **standalone POM** for a Maven project using Spring Boot Starter Parent. If a project already has a `pom.xml`, only add the necessary dependencies/plugins to the existing configuration:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>unit-test-demo</artifactId>
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
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Why aren't JUnit/Surefire versions declared here?** `spring-boot-starter-parent` provides dependency management for Starter Test and **plugin management** for common Maven plugins, including Surefire at the corresponding Spring Boot version. With `jar` packaging, the Maven lifecycle already binds Surefire's `test` goal to the `test` phase; you normally do not need to manually add a `surefire:test` execution to the POM.

If a project **only imports the `spring-boot-dependencies` BOM** and does not inherit from Spring Boot Parent, keep this distinction in mind: a BOM import manages **dependency versions**, but **does not bring in all the Maven plugin management** from the Parent. In that case, the project/corporate parent must specify the Maven Compiler Plugin and a **Surefire version that supports JUnit Platform** (typically Surefire 3.x) along with related build plugins. Do not rely on the very old Surefire version provided by Maven by default.

### 4.2. Which Phase Does Surefire Run In?

For typical Maven `jar` packaging, the path when invoking `test` is:

~~~text
validate
  -> generate-sources
  -> process-resources
  -> compile
  -> process-test-resources
  -> test-compile
  -> test  [maven-surefire-plugin:test]
~~~

This is a simplified diagram of the key phases: Maven also has intermediate phases. The `mvn test` command runs all required phases **up to and including `test`**. `mvn package` and `mvn verify` also pass through the `test` phase; therefore they run unit tests unless configured to skip or exclude them.

Distinguish it from the Maven **Failsafe Plugin**: Failsafe is typically used for **integration tests** at the `integration-test` and `verify` phases, with class names like `*IT`. Failsafe is not needed for `GreetingServiceTest` in this lesson.

### 4.3. Intentional Surefire Configuration

To make the build fail when **no unit tests are discovered**, you can configure it inside `<build><plugins>` of a Spring Boot Parent POM:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <failIfNoTests>true</failIfNoTests>
    </configuration>
</plugin>
~~~

This is a **plugin snippet**, not a complete POM. The Parent manages the plugin version; the project only adds configuration. In a POM that does not use the Parent and does not have Surefire managed by a corporate parent, you must declare an appropriate Surefire `<version>` explicitly.

Surefire's default class naming rules typically match `Test*.java`, `*Test.java`, `*Tests.java`, and `*TestCase.java`; `GreetingServiceTest` matches. A class named `GreetingServiceIT` normally does not belong to Surefire's default unit test set; if you want to run integration tests separately, use Failsafe or configure rules intentionally.

**Avoid adding complex includes/excludes when not yet needed:** a wrong pattern can prevent Surefire from finding tests even when the source code is valid. Whenever you add configuration, check the report and the actual number of tests run.

## 5. Gradle Option: Integrating with the `Test` Task

### 5.1. `settings.gradle` and `build.gradle` Using Groovy DSL

File **`settings.gradle`**:

~~~groovy
rootProject.name = 'unit-test-demo'
~~~

File **`build.gradle`**:

~~~groovy
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
~~~

**Role of each part:**

- `id 'java'` creates the `main`/`test` source sets, compilation tasks, and the `test` task; the Spring Boot Gradle plugin provides `bootJar` and `bootRun`.
- `io.spring.dependency-management` works with the Spring Boot plugin to import the BOM, providing the versions of `spring-boot-starter` and Starter Test.
- `testImplementation` places libraries on the test classpath without turning them into runtime dependencies of the application.
- `useJUnitPlatform()` tells the Gradle Test task to use JUnit Platform, which is required for the JUnit Jupiter engine to discover `@Test` methods.
- `java.toolchain` requests JDK 17 for the corresponding Java tasks; JDK 17 may need to be installed or a toolchain resolver configured so Gradle can locate the JDK.

For projects using `dependencyResolutionManagement` in settings with `FAIL_ON_PROJECT_REPOS`, **remove the `repositories { mavenCentral() }` block in `build.gradle`** and declare repositories in settings according to policy. Everything else retains the same meaning.

### 5.2. Equivalent Kotlin DSL

File **`settings.gradle.kts`**:

~~~kotlin
rootProject.name = "unit-test-demo"
~~~

File **`build.gradle.kts`**:

~~~kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.5"
    id("io.spring.dependency-management") version "1.1.6"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

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
}

tasks.test {
    useJUnitPlatform()
}
~~~

Choose **Groovy or Kotlin DSL** to match your existing project files; do not create both sets simultaneously. The Java sources `DemoApplication`, `GreetingService`, and `GreetingServiceTest` from section 3 remain unchanged.

### 5.3. Task Graph and Where Unit Tests Fit

When invoking Gradle `test`, the Java plugin automatically determines the task dependencies needed to compile `main` sources, compile `test` sources, process test resources, and then execute tests. With the standard Java plugin, the `check` task depends on `test`; the `build` task depends on both `assemble` and `check`, so **`build` runs unit tests** unless the user or configuration explicitly disables/skips them.

Unlike Maven Surefire, Gradle uses the `Test` task and the JUnit Platform engine to discover tests; **Surefire's default naming rules** are not automatically the exact rules of Gradle Test. You can restrict classes using `--tests` or filter configuration, but always check actual results to confirm which tests were selected.

## 6. Running Tests for the First Time on Linux and Windows

Run from the directory containing the appropriate Wrapper file. **Choose Maven or Gradle—you do not need to run both for a project that uses only one build tool.**

### 6.1. Linux/macOS with bash

~~~bash
# Maven option
./mvnw --version
./mvnw clean test
./mvnw clean verify

# Gradle option
./gradlew --version
./gradlew clean test
./gradlew clean build
~~~

`clean test` performs a clean unit test run, while `clean verify` (Maven) or `clean build` (Gradle) runs the broader build/verification lifecycle according to configuration. There is no requirement to run both `test` and `verify/build` back-to-back on every CI run; pick one goal/task that covers the required checks.

### 6.2. Windows PowerShell

~~~powershell
# Maven option
.\mvnw.cmd --version
.\mvnw.cmd clean test
.\mvnw.cmd clean verify

# Gradle option
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat clean build
~~~

Windows Command Prompt can invoke `mvnw.cmd` or `gradlew.bat` in the current directory. In PowerShell, `.\` is required to indicate a script in the current directory.

### 6.3. Running a Single Test Class or Method

With Maven Surefire:

~~~bash
./mvnw -Dtest=GreetingServiceTest test
./mvnw -Dtest=GreetingServiceTest#greetsAndTrimsName test
~~~

With Gradle:

~~~bash
./gradlew test --tests 'com.example.demo.GreetingServiceTest'
./gradlew test --tests 'com.example.demo.GreetingServiceTest.greetsAndTrimsName'
~~~

On PowerShell, replace the Wrapper invocation with `.\mvnw.cmd` or `.\gradlew.bat` and keep the arguments. These commands **filter the execution scope** for debugging; they do not replace running the full test suite in CI.

If the test class is in another package, replace `com.example.demo` with the actual package. In a multi-module Maven reactor, restrict with `-pl <module>` when needed; in a Gradle multi-project build, you can use `:app:test`. Selecting a module whose dependent modules have not been built yet may require additional flags (such as Maven `-am`).

## 7. Reading Results: PASS, FAIL, SKIPPED, and Reports

Do not just look at the final `BUILD SUCCESS` or `BUILD SUCCESSFUL` line and assume **all unit tests ran**. Verify the number of tests discovered, executed, failed/errored/skipped, along with the report artifacts that can be reopened in CI.

| Tool | Terminal indicators | Common test reports |
| --- | --- | --- |
| Maven Surefire | Summary `Tests run: ..., Failures: ..., Errors: ..., Skipped: ...`, ending with `BUILD SUCCESS` or `BUILD FAILURE` | `target/surefire-reports/`, including `TEST-*.xml` XML and text reports |
| Gradle Test | Task `:test` executes or is marked `UP-TO-DATE`/cached; failures normally produce `BUILD FAILED` | `build/test-results/test/TEST-*.xml` and `build/reports/tests/test/index.html` |

**Example of a real failing test:** if you change the assertion in `greetsAndTrimsName()` to expect `"Hello, Binh"` while `greet(" An ")` still returns `"Hello, An"`, JUnit reports a comparison failure. Surefire or the Gradle Test task will report a build failure under standard configuration, and CI receives a **non-zero exit code**. That is what turns unit tests into a quality gate rather than just source files sitting in a repository.

**Note on Gradle cache:** `UP-TO-DATE` or `FROM-CACHE` can be a valid outcome when inputs/task outputs have not changed. If you need to force a rerun while investigating, use `./gradlew test --rerun-tasks` when justified. Do not use it by default on every build because you lose incremental build benefits.

**Note on Maven:** running `./mvnw test` skips `clean` and keeps previous outputs per the normal lifecycle; when you need a clean-slate verification, use `clean test` or `clean verify`.

### Inspecting Reports

Linux/bash:

~~~bash
ls -la target/surefire-reports/
ls -la build/test-results/test/
ls -la build/reports/tests/test/
~~~

Windows PowerShell:

~~~powershell
Get-ChildItem .\target\surefire-reports\
Get-ChildItem .\build\test-results\test\
Get-ChildItem .\build\reports\tests\test\
~~~

Each command applies only to its **corresponding build tool**. If the directory does not exist, first check whether the test task/plugin ran, whether valid test classes exist, and whether report writing permissions exist. **Do not fabricate placeholder reports** when tests were not actually discovered.

## 8. Unit Tests with Dependencies: Using Mockito to Keep Tests Isolated

A service often depends on a repository, HTTP client, or gateway. Unit tests do not need to call a real database or HTTP endpoint. Mockito creates mocks to supply controlled results and verifies that the service used the dependency properly.

### File `src/main/java/com/example/demo/PriceService.java`

~~~java
package com.example.demo;

import java.util.Objects;

public final class PriceService {

    public interface DiscountProvider {
        long discountCents(String customerId);
    }

    private final DiscountProvider discountProvider;

    public PriceService(DiscountProvider discountProvider) {
        this.discountProvider = Objects.requireNonNull(discountProvider);
    }

    public long finalCents(String customerId, long subtotalCents) {
        if (subtotalCents < 0) {
            throw new IllegalArgumentException("Subtotal must not be negative");
        }
        long discount = discountProvider.discountCents(customerId);
        if (discount < 0 || discount > subtotalCents) {
            throw new IllegalArgumentException("Invalid discount");
        }
        return subtotalCents - discount;
    }
}
~~~

### File `src/test/java/com/example/demo/PriceServiceTest.java`

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

class PriceServiceTest {

    @Test
    void subtractsDiscountReturnedByProvider() {
        PriceService.DiscountProvider provider =
                mock(PriceService.DiscountProvider.class);
        when(provider.discountCents("A01")).thenReturn(150L);

        PriceService service = new PriceService(provider);
        long actual = service.finalCents("A01", 1_000L);

        assertEquals(850L, actual);
        verify(provider).discountCents("A01");
    }
}
~~~

This test compiles with JUnit Jupiter and Mockito provided by Spring Boot Starter Test. It **does not use** `@SpringBootTest` and does not start an ApplicationContext. `when(...).thenReturn(...)` is stubbing, while `verify` confirms the required interaction. Using integer cents avoids floating-point comparison issues in the example.

**Limitations of mocks:** a unit test proves service logic against mocked behavior; it **does not prove** that the database driver, SQL query, or partner API actually works. Those paths require dedicated integration tests when appropriate.

## 9. Why You Should Not Use `@SpringBootTest` for Every Unit Test

`@SpringBootTest` loads the Spring ApplicationContext and many beans according to configuration. It is useful when you need to verify **Spring Boot integration** (auto-configuration, bean wiring, properties, context startup), but it is typically more resource-intensive, can depend on the environment, and runs slower than tests that simply instantiate Java objects.

Distinction:

| Problem | Appropriate testing approach |
| --- | --- |
| Calculations, validation, value transformation | Plain JUnit Jupiter, instantiating objects directly |
| Service calling a repository/gateway while isolating logic | JUnit + Mockito mock |
| Testing controller logic with Spring MVC infrastructure | Spring test slice such as `@WebMvcTest` if appropriate for the project |
| Testing full application wiring/configuration | `@SpringBootTest` or an appropriately designed integration test |
| Requiring a real database/container/HTTP service | Separate integration test with explicit setup and teardown |

**Do not equate an annotation with a plugin:** a `@SpringBootTest` placed in a class named `SomeTest` can still be run by Surefire in the `test` phase; a framework annotation does not automatically move that class to Maven Failsafe. Similarly, Gradle runs whatever classes are selected by the `Test` task; separating integration tests into their own task/source set requires additional configuration.

The unit tests in sections 3 and 8 run without a database, web server, `application-prod.yml`, or production environment variables. This is a good sign of a fast and stable test suite.

## 10. Selecting Tests, Tagging, and Controlling Skips

### 10.1. JUnit Jupiter Tags

You can mark a test with `@Tag("unit")`:

~~~java
// Snippet placed on a test class or method using JUnit Jupiter
@org.junit.jupiter.api.Tag("unit")
@org.junit.jupiter.api.Test
void calculatesAUnitRule() {
    org.junit.jupiter.api.Assertions.assertEquals(4, 2 + 2);
}
~~~

**The snippet above is a method inside a test class**, not a standalone Java file. You can configure tag-based filtering when a project has multiple test groups. With Gradle Groovy DSL:

~~~groovy
tasks.named('test') {
    useJUnitPlatform {
        includeTags 'unit'
    }
}
~~~

Do not add `includeTags 'unit'` to the base template if existing tests are not tagged yet: doing so could exclude all of them from the run. Maven Surefire 3.x supports JUnit Platform group/tag selection via `groups`/`excludedGroups` configuration when needed; check your plugin version and inspect the test report.

### 10.2. Test-Skipping Commands and Their Risks

| Command | Typical effect | When to use? |
| --- | --- | --- |
| Maven `-DskipTests` | Skips Surefire test **execution**; test sources typically still compile | Temporary investigation, with clear documentation |
| Maven `-Dmaven.test.skip=true` | Skips both test compilation and execution in plugins that honor this property | Special build cases, never as a substitute for CI testing |
| Gradle `-x test` | Excludes the `test` task from the task graph for that invocation | Temporary debugging |
| JUnit `@Disabled` | Skips an annotated test or class | Only with a valid reason and tracking |

**Skipping tests does not prove tests pass.** CI should verify there are no unintended skip flags and that test reports show results. If you use Maven `-Dtest=... test` or Gradle `--tests`, you are only running part of the suite. Do not treat that result as a replacement for full checks before merging.

### 10.3. Zero Tests Can Still Produce a Green Build

If a test class is placed in the wrong package/directory, named so it does not match Surefire's pattern, missing the JUnit Platform engine, or Gradle omits `useJUnitPlatform()`, the build may fail to run the expected tests. Some configurations will still report success if no tests are discovered.

Check **the number of tests discovered and executed**, not just build status. In Maven, you can enable `failIfNoTests` as shown in section 4; in Gradle, inspect the XML/HTML test reports and apply an error policy for unexpectedly empty test suites appropriate for your Gradle version/project.

## 11. Integrating Unit Tests into CI

CI must provide a **compatible JDK**, invoke the right **Wrapper**, and run a lifecycle that includes tests. Below are **two alternative options**; each repository chooses only the variant matching its build system. The GitHub Actions major versions shown illustrate structure; check supported action versions and SHA-pinning policies in your organization before real-world use.

### Maven Option: `.github/workflows/maven-test.yml`

~~~yaml
name: Maven unit tests

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: maven

      - name: Verify tool versions
        run: |
          java -version
          ./mvnw --version

      - name: Run tests and verify build
        run: ./mvnw --batch-mode --no-transfer-progress clean verify
~~~

### Gradle Option: `.github/workflows/gradle-test.yml`

~~~yaml
name: Gradle unit tests

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'
          cache: gradle

      - name: Verify tool versions
        run: |
          java -version
          ./gradlew --version

      - name: Run tests and build
        run: ./gradlew clean build
~~~

If the `mvnw` or `gradlew` Wrapper script lacks the executable bit on Linux CI, the runner reports `Permission denied`. Fix this by committing the executable permission in Git or using a shell invocation permitted by the project; do not misdiagnose it as a JUnit/Surefire issue.

**CI verification:** the job must return a failed status when tests fail. If you need to read or archive reports after the build, use your CI's artifact/report mechanism and configure the collection step to run even when tests fail. Those advanced steps depend on pipeline policy; the templates above keep the core requirement of running unit tests before accepting a build.

## 12. Common Errors and How to Isolate Them

| Symptom | Likely cause | How to check and fix |
| --- | --- | --- |
| Maven build succeeds but `GreetingServiceTest` is missing from report | Test name does not match Surefire patterns, wrong directory, excluded, or plugin too old | Inspect `src/test/java`, `target/surefire-reports`, Surefire version, and effective POM |
| `No tests were executed` / Jupiter not found | Missing JUnit Jupiter engine or runner not configured for JUnit Platform | Use compatible Starter Test/BOM, Surefire 3.x, or Gradle `useJUnitPlatform()` |
| Gradle `test` finds no tests | Java plugin/source set not applied, missing `useJUnitPlatform()`, filters excluding everything | Check `test` task, `testRuntimeClasspath`, `--tests`, XML report, and `build.gradle` |
| Error `package org.junit.jupiter.api does not exist` | Missing JUnit dependencies on test classpath, or test source compiled as main source | Add `spring-boot-starter-test` with `test`/`testImplementation` scope, place files in `src/test/java` |
| Maven reports provider/plugin error when using JUnit 5 | Outdated Surefire version or incompatible dependency | Inspect effective POM and upgrade Surefire to a version supporting JUnit Platform per project matrix |
| `UnnecessaryStubbingException` with Mockito | Unused stub or mock setup incompatible with strictness | Remove unused stubs and fix the test; do not disable strictness globally just to hide the error |
| Tests pass in IDE but fail in Maven/Gradle | IDE uses a different JDK/classpath/runner or test configuration | Run the Wrapper from terminal, verify JDK, dependencies, and reports, then align IDE settings |
| Unit test fails due to missing database/secret | Test is loading the Spring context or calling a real dependency | Decouple unit test from Spring context, mock dependencies, move integration checks to appropriate tests |
| Tests randomly pass/fail in CI | Time, timezone, execution order, shared static state, or network dependency | Make inputs deterministic, isolate state, avoid `Thread.sleep` for synchronization |
| Maven `BUILD SUCCESS` but CI writes no report | Plugin did not run, tests were skipped, or report path is wrong | Check Surefire summary, `skipTests`, and `target/surefire-reports` |
| Gradle `:test UP-TO-DATE` when trying to reproduce an error | Outputs confirmed still valid by Gradle or restored from cache | Use `test --rerun-tasks` for investigation and save test logs |
| JUnit 4 `@Test` does not run under Jupiter | Legacy test uses JUnit 4 runner and lacks Vintage engine | Prefer migrating to JUnit Jupiter; if JUnit 4 must stay, configure Vintage engine intentionally |

When investigating, locate the failure in the **compile main → compile test → discover test → run assertions → generate report** sequence. Do not fix a missing engine by renaming all tests, and do not skip tests when the real failure is an assertion.

### Where to Read Logs?

- Maven: stdout of `mvnw clean test`, `target/surefire-reports/`, `./mvnw help:effective-pom` if plugin/configuration issues are suspected.
- Gradle: stdout of `gradlew test --info` for diagnostics, `build/reports/tests/test/index.html`, XML under `build/test-results/test/`.
- CI: Java setup logs, executed commands, test summary output, and pipeline artifact/report paths.

Do not expose secrets or sensitive connection details from CI logs when asking others for help debugging.

## 13. Hands-On Exercise and Completion Criteria

Practice on **one** Spring Boot Maven **or** Gradle project with a Wrapper and Java 17+:

1. Identify the build tool and check the JDK with `java -version` and `./mvnw --version` or `./gradlew --version`.
2. Add Starter Test and the corresponding runner: Maven Surefire 3.x provided by parent/plugin management, or Gradle `tasks.named('test') { useJUnitPlatform() }`.
3. Create `GreetingService.java`, `GreetingServiceTest.java`, `PriceService.java`, and `PriceServiceTest.java` in the example's package/directories. Keep `DemoApplication.java` if you want to build the Spring Boot executable JAR.
4. Run `clean test`, verify unit tests are discovered and all assertions pass; confirm reports exist.
5. Run `GreetingServiceTest` individually via filtering, then run the full test suite again so `PriceServiceTest` is not omitted.
6. Intentionally change an expected value in an assertion to cause a FAIL; observe Maven Surefire or Gradle Test returning an error and the report pointing to the exact failing test. **Restore the assertion** and run the full suite again.
7. Run `clean verify` (Maven) or `clean build` (Gradle) to verify unit tests are part of the standard build pipeline.
8. Cross-check with CI using the same JDK/Wrapper and confirm the job does not intentionally use skip flags.

You have completed the lesson when you can explain **what discovers and runs JUnit tests**, prove tests were executed via Maven/Gradle, inspect reports, and distinguish assertion failures from discovery, missing dependency, or test framework configuration errors.

## Official Reference Documentation

- [JUnit 5 – User Guide](https://junit.org/junit5/docs/current/user-guide/)
- [Apache Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Surefire – Inclusions and Exclusions](https://maven.apache.org/surefire/maven-surefire-plugin/examples/inclusion-exclusion.html)
- [Maven Surefire – Using JUnit 5 Platform](https://maven.apache.org/surefire/maven-surefire-plugin/examples/junit-platform.html)
- [Gradle – Testing in Java and JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html)
- [Gradle – Test Task](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html)
- [Spring Boot – Testing Reference](https://docs.spring.io/spring-boot/reference/testing/index.html)
- [Spring Boot – Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html)
