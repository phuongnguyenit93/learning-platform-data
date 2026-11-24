# Configuring Gradle `useJUnitPlatform()` and Running Tests with Gradle Wrapper

## Learning Objectives

After this lesson, you can:
- Understand Gradle's `test` task, JUnit Platform, JUnit Jupiter, and why calling `useJUnitPlatform()` is necessary.
- Declare suitable testing dependencies in a Spring Boot project using **Gradle Groovy DSL** (`build.gradle`).
- Run tests with `gradlew`/`gradlew.bat` on Linux, macOS, or Windows without relying on a globally installed Gradle on the machine.
- Run a complete JUnit 5 example, inspect test reports, filter tests, and handle common configuration errors.
- Distinguish **Gradle Wrapper** (selects the Gradle version) from **Java/JDK** and JUnit libraries (each must be configured separately).

The lesson focuses on **test setup and execution**. Specific business assertions in the tests serve only as examples to verify that the setup works.

## 1. Three components working together when running JUnit 5

A Java/Spring Boot project typically uses the following components:

| Component | Responsibility |
| --- | --- |
| **Gradle Java plugin** | Creates the `main` and `test` source sets and the `test` task to compile and execute tests. |
| **JUnit Platform** | Mechanism for discovering and launching tests through one or more test engines. |
| **JUnit Jupiter** | APIs such as `org.junit.jupiter.api.Test`, `Assertions`, and the Jupiter engine executing JUnit 5 tests. |
| **Gradle Wrapper** | Scripts and configuration that download/select the exact Gradle version specified by the project. |

When the Java plugin is applied, Gradle normally reads production code from `src/main/java` and test code from `src/test/java`. The `test` task sits in the Java plugin's build lifecycle; `check` depends on `test`, and `build` depends on `check` via standard Java tasks.

**`useJUnitPlatform()` configures a `Test` task to run via JUnit Platform.** It does not add the JUnit Jupiter API, create tests, or download the JUnit engine on its own. If dependencies are missing, the task may find no tests or fail at runtime. Conversely, adding Jupiter `@Test` annotations to code without telling Gradle to use JUnit Platform is also an incomplete configuration.

High-level overview:

~~~text
src/test/java/.../*Test.java
           |
           v
   Gradle test task (Test)
           |
           | useJUnitPlatform()
           v
      JUnit Platform
           |
           v
     JUnit Jupiter Engine
           |
           v
    Execute @Test and record results
           |
           +--> build/test-results/test/   (XML)
           +--> build/reports/tests/test/  (HTML)
~~~

The diagram depicts the typical pipeline with the Java plugin and `test` task. In a multi-project build, each subproject writes reports inside **that subproject's own** `build` directory.

## 2. Configuration in an existing Spring Boot project

For a Spring Boot project using **Gradle Groovy DSL**, add or check the following blocks in `build.gradle` of the module containing tests:

~~~groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

This is a **configuration snippet to integrate into a Spring Boot project that already has plugins, repositories, and dependency version management**, not a complete standalone `build.gradle`.

### Line-by-line explanation

- `testImplementation 'org.springframework.boot:spring-boot-starter-test'`: adds the testing bundle for test code, including Spring Test support, JUnit Jupiter, and assertion/mocking libraries matching the project's Spring Boot version.
- `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'`: declares the JUnit Platform launcher at test runtime, following modern Gradle configuration guidance. This dependency does not replace the Jupiter engine; the engine must be present on the test runtime classpath (normally brought in by the test starter).
- `tasks.named('test', Test)`: configures the `test` task created by the Java plugin. This is Groovy DSL syntax; Kotlin DSL (`build.gradle.kts`) uses different syntax.
- `useJUnitPlatform()`: instructs Gradle to run that task via JUnit Platform so Jupiter tests are recognized.

**Version management:** The snippet omits version numbers assuming the project already manages dependencies via Spring Boot dependency management or the Spring Boot BOM. If the project applies no version-management mechanism, versionless dependencies will fail to resolve. In an existing project, follow the project's own version-management system and avoid arbitrarily pinning a JUnit version incompatible with Spring Boot.

If the project already has `tasks.named('test') { useJUnitPlatform() }`, do not add a duplicate block just to call the same method again. If there are **multiple `Test` tasks** (such as a separate integration test task), configure each task that needs to run JUnit 5; configuring only `test` **does not automatically make** newly created tasks use JUnit Platform. One option that applies to all `Test` tasks is:

~~~groovy
tasks.withType(Test).configureEach {
    useJUnitPlatform()
}
~~~

Only choose the global approach when you want every `Test` task to run via JUnit Platform; some tasks may be designed for another framework and require separate configuration.

### Role of dependency scopes

| Scope | When to use | Example |
| --- | --- | --- |
| `implementation` | Production code needs the library at compile/runtime | Application's Spring Boot starters |
| `testImplementation` | Test code needs the API at compile time, and it is also on the test runtime classpath | `spring-boot-starter-test` or JUnit Jupiter |
| `testRuntimeOnly` | Tests need the component at runtime without importing it in test source | JUnit Platform launcher |

Do not put `junit-jupiter` or `spring-boot-starter-test` into application `implementation` just so tests compile. Keep them in test scopes to avoid pulling testing libraries into the production runtime.

## 3. Minimal runnable example with Gradle + JUnit Jupiter

To verify the setup in isolation, you can create a small Java Gradle project. The example below **runs standalone** with Java 17+ and a compatible Gradle version; no Spring `ApplicationContext` is needed. Once you understand it, you can place tests with the same structure into a Spring Boot project.

Directory structure:

~~~text
junit-platform-demo/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
├── gradle/
│   └── wrapper/
│       ├── gradle-wrapper.jar
│       └── gradle-wrapper.properties
└── src/
    ├── main/java/com/example/testing/ShippingFeeCalculator.java
    └── test/java/com/example/testing/ShippingFeeCalculatorTest.java
~~~

The Wrapper files are generated in Step 4; there is no need to copy the `gradle-wrapper.jar` binary manually.

**`settings.gradle`**

~~~groovy
rootProject.name = 'junit-platform-demo'
~~~

**`build.gradle`** — example using JUnit 5.10.2 BOM to align Jupiter and Platform versions; this is a consistent illustrative version, not a requirement that all new projects use that exact version:

~~~groovy
plugins {
    id 'java'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation platform('org.junit:junit-bom:5.10.2')
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

Here `platform('org.junit:junit-bom:5.10.2')` is the **JUnit BOM** so Gradle selects compatible versions for JUnit components without explicit versions. Java toolchain requires JDK 17 to be available or toolchain provisioning to be configured; declaring a toolchain alone does not guarantee the machine already has the JDK installed.

**`src/main/java/com/example/testing/ShippingFeeCalculator.java`**

~~~java
package com.example.testing;

public final class ShippingFeeCalculator {

    public int feeFor(int orderAmount) {
        if (orderAmount < 0) {
            throw new IllegalArgumentException(
                    "orderAmount must not be negative");
        }
        return orderAmount >= 500 ? 0 : 30;
    }
}
~~~

Problem rule: order amounts of `500` or more qualify for free shipping (`0`); amounts below `500` pay a fee of `30`; negative numbers are invalid input. `int` keeps the example focused on test infrastructure; real billing applications should use appropriate numeric types and currency units.

**`src/test/java/com/example/testing/ShippingFeeCalculatorTest.java`**

~~~java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class ShippingFeeCalculatorTest {

    private final ShippingFeeCalculator calculator =
            new ShippingFeeCalculator();

    @Test
    void ordersAtThresholdHaveFreeShipping() {
        assertEquals(0, calculator.feeFor(500));
    }

    @Test
    void ordersBelowThresholdPayShipping() {
        assertEquals(30, calculator.feeFor(499));
    }

    @Test
    void negativeOrderAmountIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.feeFor(-1));
    }
}
~~~

Notice the import **`org.junit.jupiter.api.Test`** from JUnit Jupiter, distinct from `org.junit.Test` from JUnit 4. The three tests check two valid branches and one invalid input; they do not invoke Spring and print nothing to `stdout`. With the code and dependencies right, JUnit Platform discovers **3 tests** in the class.

A test does not need `public` on the class or methods in regular JUnit Jupiter; `class ShippingFeeCalculatorTest` and the package-private methods in the example are valid. Gradle detects tests via the test engine and annotations, not solely because the filename ends with `Test`.

### Running and verifying with the Wrapper

Once the Wrapper is in place, open a terminal in the directory **containing `gradlew`, `gradlew.bat`, and `settings.gradle`**.

On Linux/macOS:

~~~bash
./gradlew test
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

With the example above, all three tests should pass; Gradle completes successfully, typically displaying `BUILD SUCCESSFUL` (exact formatting and task count depend on Gradle version/cached tasks). **The tests do not write to stdout**, so there are no three printed result lines in the console. Determine the actual executed test count from the test report rather than inferring it solely from `BUILD SUCCESSFUL`.

Results normally appear at:

~~~text
build/
├── reports/tests/test/index.html
└── test-results/test/
    ├── TEST-com.example.testing.ShippingFeeCalculatorTest.xml
    └── binary/...
~~~

`index.html` is the human-readable HTML report; XML files serve CI and report aggregators. Nested files may vary by Gradle version; XML filenames reflect the corresponding class name. The example class's XML file records 3 test cases if all three ran without filtering.

## 4. What is the Gradle Wrapper and how is it generated?

The **Gradle Wrapper** consists of scripts that invoke Gradle and a configuration file specifying the Gradle distribution. It ensures developers and CI use **the project's designated Gradle version**, instead of each machine running a different globally installed `gradle`. The Wrapper **does not lock the JDK** or library versions: JDK, dependencies, and repositories still require corresponding configuration.

Files that should be committed with source code:

| File | Role |
| --- | --- |
| `gradlew` | Script invoking Gradle on Linux/macOS |
| `gradlew.bat` | Script invoking Gradle on Windows |
| `gradle/wrapper/gradle-wrapper.jar` | Wrapper launcher code |
| `gradle/wrapper/gradle-wrapper.properties` | Distribution URL configuration and related Wrapper properties |

### When there is no Wrapper yet

The machine needs a working **`gradle`** command to generate the Wrapper the first time. In the Java Gradle project directory, for example generating the Wrapper for Gradle `8.5`:

~~~bash
gradle wrapper --gradle-version 8.5 --distribution-type bin
~~~

This command is an **illustrative bootstrap step**. Real projects must choose a Gradle version compatible with the Java, Spring Boot, and plugins in use; do not blindly downgrade or upgrade just because the example says `8.5`. If the project **already has a Wrapper**, normally just run the existing scripts without regenerating the Wrapper.

A line in `gradle/wrapper/gradle-wrapper.properties` after generation may look like:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.5-bin.zip
~~~

Do not edit `distributionUrl` to point to an untrusted source. On the first run, the Wrapper may require network access to download the Gradle distribution; subsequent runs typically reuse the cached copy if still valid. `--distribution-type bin` selects the binary distribution, sufficient for building/testing; `all` adds Gradle docs and sources.

### Checking active tools

Linux/macOS:

~~~bash
java -version
./gradlew --version
./gradlew tasks
~~~

Windows PowerShell:

~~~powershell
java -version
.\gradlew.bat --version
.\gradlew.bat tasks
~~~

`java -version` shows the JVM found on the shell path; `gradlew --version` shows Gradle and the JVM running Gradle; the **toolchain** JVM for compile/test tasks may be a different JDK than the JVM running Gradle. If the project requires Java 17 or 21, verify the current Gradle version supports that JVM and the corresponding toolchain is found.

On Linux/macOS, if the Wrapper script is denied due to missing execute permission, you may need:

~~~bash
chmod +x gradlew
./gradlew test
~~~

On Windows, use `.\gradlew.bat` rather than Unix's `./gradlew`; PowerShell generally requires the `.\` prefix to run a script in the current directory. No global Gradle installation is needed to run a project **that already has a Wrapper and a suitable Java environment**.

## 5. Common commands for executing tests

The table below uses Linux/macOS `./gradlew` syntax. On Windows PowerShell, substitute `.\gradlew.bat`; arguments after the script stay the same.

| Command | Purpose |
| --- | --- |
| `./gradlew test` | Run the `test` task per current configuration. |
| `./gradlew clean test` | Delete build outputs first, then rebuild/run tests. |
| `./gradlew test --tests 'com.example.testing.ShippingFeeCalculatorTest'` | Run only tests in one class matching the filter. |
| `./gradlew test --tests 'com.example.testing.ShippingFeeCalculatorTest.ordersAtThresholdHaveFreeShipping'` | Run one test method by exact name. |
| `./gradlew test --info` | Display more detailed logs for diagnosis. |
| `./gradlew test --stacktrace` | Display stack traces when Gradle encounters errors. |
| `./gradlew test --no-daemon` | Run without using a long-lived daemon, often useful in some CI environments. |
| `./gradlew :app:test` | Run the `test` task of a subproject whose actual project path is `:app`; substitute the project's real path. |

**`test` does not always re-execute all tests.** Gradle may report `UP-TO-DATE` or `FROM-CACHE` when task outputs are reused. `NO-SOURCE` indicates the task had no test sources to process under that configuration. All three statuses must be understood properly; if you need a fresh run for diagnosis, you can use:

~~~bash
./gradlew test --rerun-tasks
~~~

`--rerun-tasks` can force multiple tasks in the task graph to re-execute, so it should not be used by default on every test run. `clean test` also rebuilds outputs but carries a higher compilation cost.

### Multi-project Gradle builds

When a repository contains multiple Gradle projects, the task path identifies the module under test:

~~~bash
./gradlew :orders:test
~~~

This is a **syntax example**, valid only if `:orders` is a declared project. In a real repo, inspect project paths in `settings.gradle` or run `./gradlew projects`. Do not guess task paths from directory or artifact names without checking the Gradle layout. In composite builds, project and included-build task paths can differ.

### Enabling test event logging when needed

By default, the console shows task status and failures; to make test events easier to see, add to the existing task configuration:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform()

    testLogging {
        events 'passed', 'skipped', 'failed'
    }
}
~~~

Use **one** combined `tasks.named('test', Test)` block if that block already exists. This configuration displays the corresponding events without creating tests or changing test outcomes. For CI, the XML/HTML test reports remain the right source for checking totals and individual failures.

## 6. How to verify the configuration is truly working

After running the example in Section 3, verify in the following order:

1. **Wrapper invokes the right Gradle distribution:** `./gradlew --version` succeeds and matches the project's version.
2. **Right JDK:** Gradle starts cleanly and the task's Java toolchain finds the required JDK.
3. **Dependencies resolve:** no errors fetching `junit-jupiter`, JUnit Platform launcher, or Spring Boot test starter from repositories.
4. **Tests compile:** classes in `src/test/java` can import `org.junit.jupiter.api.Test` and assertions.
5. **JUnit Platform discovers tests:** the example class reports 3 tests rather than 0/`NO-SOURCE`; filtering by one class finds that exact class.
6. **Results are recorded:** HTML/XML reports appear and all assertions pass; intentionally changing an expected value in **a local test edit** makes the test fail, then revert it.

In the example, changing `assertEquals(0, calculator.feeFor(500))` to `assertEquals(1, calculator.feeFor(500))` makes the threshold test fail if the runner actually executes it. That confirms the path from test source to Jupiter to the Gradle test report. **Always revert the experimental edit after verification.**

If you want to verify specifically that Gradle discovers a test in a large project, use `--tests` with the exact class name and inspect the report; this is much more reliable than trusting `BUILD SUCCESSFUL` when a task might be cached or have no sources.

## 7. Common errors: symptoms, causes, and fixes

| Symptom | Common possibilities | How to fix |
| --- | --- | --- |
| `No tests found for given includes…` when using `--tests` | Wrong package/class/method filter, or test not recognized by engine | Verify full name, `src/test/java` location, JUnit Jupiter `@Test` annotation, and `useJUnitPlatform()` |
| `test NO-SOURCE` | No test source attached to the task's source set | Check right module, file path, extension, and `sourceSets` if customized |
| Task passes yet test report has 0 tests | No tests actually discovered or task misconfigured | Inspect engine, dependencies, task path, test filters, and XML/HTML reports |
| Error like `Cannot create Launcher without at least one TestEngine` | Missing test engine on runtime classpath | Add `junit-jupiter`/Jupiter engine via proper dependency and check dependency graph |
| Missing JUnit Platform launcher class error | Launcher dependency missing or version mismatch | Add `testRuntimeOnly 'org.junit.platform:junit-platform-launcher'` and use consistent BOM/version management |
| `Could not find method useJUnitPlatform()` | Called in wrong context or Gradle is too old | Place inside a `Test`-type task, use a Gradle version supporting JUnit Platform |
| Gradle fails to run due to JVM/class version | Gradle, JDK, and plugin version requirements incompatible | Check `java -version` and `gradlew --version`, match actual version compatibility matrix |
| `.\gradlew.bat` not found | Terminal is not at project root or Wrapper is missing | Run from the directory containing `gradlew.bat`; verify Wrapper files are committed in repo |
| `Permission denied` for `./gradlew` | Unix Wrapper script lacks execute bit | Run `chmod +x gradlew` if permitted |
| Unable to download Gradle distribution/dependencies | Network, proxy, repository, or cache unavailable | Check `distributionUrl`, repositories, network/proxy, and CI environment config |
| Spring Boot test fails starting context | Missing bean/config/profile/database or test infrastructure | Read the test stack trace, separate application context errors from runner setup, supply proper test config |

### JUnit 4 and JUnit Jupiter are not the same `@Test`

These two imports look similar yet belong to different frameworks/engines:

~~~java
// JUnit Jupiter (JUnit 5) — used with Jupiter engine
import org.junit.jupiter.api.Test;

// JUnit 4 — requires separate compatibility support when running on JUnit Platform
// import org.junit.Test;
~~~

When writing new tests, use Jupiter annotations and the Jupiter engine. If **migrating legacy JUnit 4 tests**, you may need the JUnit Vintage engine on the test runtime classpath so JUnit Platform runs those JUnit 4 tests. Do not add Vintage if unnecessary; it is not required for Jupiter tests. With Mockito/Spring Test, use Jupiter-compatible extensions like `@ExtendWith`, rather than assuming JUnit 4's `@RunWith` works automatically on Jupiter.

### Application bugs vs. test runner configuration errors

If JUnit discovers and runs a `@SpringBootTest` test yet the Spring context fails to start, that is usually an **application bootstrapping or environment fixture error**: missing bean, misconfiguration, unavailable database, etc. In that case `useJUnitPlatform()` may already be right. Distinguish:
- **Tests do not run/discover** → inspect Gradle test task, engine, launcher, source set, and dependencies.
- **Tests run yet assertions or context fail** → inspect application behavior, input data, test profile, and exact error logs.

`@SpringBootTest` is needed only when testing the Spring context; plain Java unit tests like the example do not need that annotation. Avoid starting a Spring context for every pure calculation because it slows the suite and increases environment coupling.

## 8. Running in CI and practical checklist

In CI, common practice is to check out the source (including the Wrapper), install the right JDK, and run the test task using the **repository's own script**:

~~~bash
./gradlew --no-daemon test
~~~

If the project has multiple modules, select the appropriate task path; if CI needs all checks, `./gradlew check` runs the verification task chain wired by the Java plugin and project plugins (which does not guarantee every custom test task is wired into `check`). When the pipeline fails, collect `build/test-results/test/` and `build/reports/tests/test/` per module as test artifacts. CI also needs repository/dependency cache access and any infrastructure required by integration tests.

Before considering test setup complete, ask yourself:

- Does `build.gradle` contain the right test dependencies and does the Gradle `test` task call `useJUnitPlatform()`?
- Do tests import `org.junit.jupiter.api.Test` with a matching Jupiter engine/launcher?
- Does the Wrapper include all four required files, and is the Gradle distribution compatible with the project's JDK/plugins?
- Are tests in the right source set/module, and are task paths and filters accurate?
- Do HTML/XML reports reflect **the actual executed test count**, and does introducing a wrong assertion make the test fail?
- In CI, are the JDK, repositories, and integration test environment configuration reproducible?

**Remember:** `useJUnitPlatform()` configures **how Gradle runs tests**; `spring-boot-starter-test`/JUnit Jupiter supply the **libraries and engine**, and the Wrapper ensures every environment invokes the **project-selected Gradle version**. A reliable setup needs all three parts, confirmed by test reports and a check that can actually fail.
