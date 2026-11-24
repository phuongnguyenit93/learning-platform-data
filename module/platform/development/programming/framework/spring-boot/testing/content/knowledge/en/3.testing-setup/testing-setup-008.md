# Configuring the IDE and Comparing with Command-Line Execution

## 1. Purpose of the comparison

In a Spring Boot project, there are at least two common ways to launch tests:

1. **Running from the IDE:** clicking the Run/Debug icon next to a test method or class in IntelliJ IDEA, Eclipse, or Visual Studio Code; depending on the IDE and settings, execution may be handled by the **IDE's JUnit runner** or delegated to **Gradle/Maven**.
2. **Running from the command line:** using the **Gradle Wrapper** (`gradlew`) or **Maven Wrapper** (`mvnw`) so the build tool discovers and executes tests per project configuration; this is typically how CI runs tests.

The goal is not for both places to look identical or finish in the exact same time. The goal is that **given the same source code, same versions/dependencies, same meaningful configuration, and same test scope, both must produce the same result**. If the IDE shows green while the terminal command or CI shows red, you must find the actual discrepancy between the two environments rather than blindly trusting one side.

After this lesson, you can:

- Configure the JDK, test framework, and build tool so the IDE recognizes JUnit Jupiter tests.
- Distinguish the IDE's runner from Gradle/Maven test tasks or plugins.
- Run the same test class/method in the IDE, terminal, and CI; confirm that tests **actually executed**.
- Compare Java versions, classpaths, profiles, environment variables, working directories, JVM arguments, and test infrastructure.
- Diagnose why a test passes in only one place and establish a reproducible verification workflow.

**Scope:** Spring Boot projects using Java 17+ and JUnit Jupiter, with either Gradle or Maven. Example commands assume a project with a build wrapper and matching dependency configuration; not every project uses both build tools simultaneously.

## 2. Configuration layers that decide test outcomes

"The IDE recognized the test" does not mean the IDE is running the project's exact test pipeline. Distinguish the following layers:

| Layer | Function | What to compare |
|---|---|---|
| **JDK** | Compiles and runs Java | Project SDK, Gradle JVM/Maven JVM, Java toolchain, test JVM |
| **Build tool** | Builds classpath, compiles tests, processes source sets, resources, plugins | Gradle Wrapper/Maven Wrapper, plugin versions, tasks/goals |
| **Test framework** | Test discovery, lifecycle, assertions, extensions | JUnit Jupiter and JUnit Platform/Surefire provider |
| **Runner** | Launches selected tests | IDE JUnit runner vs. Gradle/Maven runner |
| **Spring TestContext** | Creates/loads/caches `ApplicationContext` for Spring tests | `@SpringBootTest`, test slices, `@ActiveProfiles`, property overrides |
| **Environment** | Provides variables, files, DB, Docker, locale, timezone | OS, current directory, environment variables, ports, containers |
| **Test filters** | Decides which tests are selected | Class/method/package, test tags, tasks, source sets, includes/excludes |

Commonly misunderstood behaviors:

- An IDE running Java tests directly may ignore `systemProperty`, JVM args, or source-generation steps declared only inside a Gradle task.
- Gradle may mark `test` as `UP-TO-DATE`, so a command exiting cleanly **does not prove tests just re-executed**.
- A multi-module project may have multiple `test` tasks; running at the root vs. clicking Run in one module can select **different scopes**.
- Integration tests requiring Docker/a database may pass on a machine with that infrastructure and fail when a runner or CI lacks access.

## 3. Setting up a standard project before tuning the IDE

### 3.1. Keep test structure consistent

Common layout for Java + Spring Boot:

```text
project/
├── build.gradle                 # Gradle (or pom.xml for Maven)
├── settings.gradle              # if using Gradle
├── gradlew / gradlew.bat         # if using Gradle Wrapper
├── mvnw / mvnw.cmd               # if using Maven Wrapper
├── src/
│   ├── main/java/com/example/testing/...
│   ├── main/resources/application.yml
│   ├── test/java/com/example/testing/...
│   └── test/resources/application-test.yml
└── ...
```

The diagram shows filenames **by project type**; a real project does not need both wrappers. Normally Gradle/Maven recognize `src/test/java` and `src/test/resources` by convention. A directory like `src/integrationTest/java` runs only when the project defines the corresponding source set/task or plugin; creating the folder **does not automatically** make tests discoverable.

In the IDE, open the **root directory containing the build configuration**; import or reload from `build.gradle(.kts)` or `pom.xml`. Do not manually attach JAR libraries inside the IDE when the project uses a dependency-management system.

### 3.2. Gradle/JUnit Jupiter configuration

In a Spring Boot project that **already declares the Spring Boot plugin and needed repositories/dependency management**, the test-related section in `build.gradle` (Groovy DSL) might be:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

- `spring-boot-starter-test` puts common testing tools, including JUnit Jupiter, on the test classpath at the Boot-managed version.
- `useJUnitPlatform()` ensures the Gradle `Test` task runs via JUnit Platform.
- Keep dependencies and versions in **the project's build file**, rather than pinning an arbitrary JUnit version only inside IDE settings.
- In Gradle Kotlin DSL, the equivalent configuration is typically `tasks.test { useJUnitPlatform() }`.

If you need to standardize the Java version for compiling/testing, Gradle Java Toolchains can be configured as in this Java 21 example:

```groovy
java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}
```

**Distinction:** the JDK used to **run Gradle** and the **toolchain** JDK used for compiling/testing can differ. `./gradlew --version` checks the Gradle runtime, which is not enough to prove every test JVM uses the right toolchain; inspect task/toolchain configuration and test execution when in doubt.

### 3.3. Maven/JUnit Jupiter configuration

In a Maven Spring Boot project with appropriate version management, declare the test starter in `pom.xml`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

JUnit Jupiter must be supported by a compatible Maven Surefire version to run during the `test` phase. Projects using a current Spring Boot parent/plugin management generally have sensible defaults; when managing Maven plugins yourself, verify `maven-surefire-plugin` and the JUnit Platform provider instead of relying solely on the IDE.

If the application has **integration tests** wired to Maven Failsafe, those tests typically execute in phases/goals configured for `integration-test`/`verify`, **not automatically** during `mvn test`. The same applies to extra Gradle source sets/tasks. Always compare identical test sets.

### 3.4. Syncing JDK and dependencies

Check three things separately:

1. Does the **JDK used by the IDE to compile/run tests** satisfy the source code's requirements?
2. Are the **build tool's JDK** and **compile/test toolchain** aligned?
3. Does the **dependency list** imported by the IDE match the build file and lockfile/BOM?

A Spring Boot 3.x project requires at least Java 17; if the project sets Java 21, both the IDE and pipeline must provide a matching JDK/toolchain. After changing the JDK, `build.gradle(.kts)`, or `pom.xml`, reload the project and confirm the IDE marks `src/test/java` as a test source root.

## 4. Runnable comparison example with JUnit Jupiter

This example does not boot a Spring context; the goal is to isolate whether **IDE/CLI picked the right Java, dependencies, and runner** from Spring/DB issues. These two files are self-contained and run in any Java 17+ project configured with JUnit Jupiter.

**File `src/main/java/com/example/testing/FeeCalculator.java`:**

```java
package com.example.testing;

public final class FeeCalculator {

    public int total(int subtotal, int fee) {
        if (subtotal < 0 || fee < 0) {
            throw new IllegalArgumentException("Amounts must be non-negative");
        }
        return Math.addExact(subtotal, fee);
    }
}
```

**File `src/test/java/com/example/testing/FeeCalculatorTest.java`:**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class FeeCalculatorTest {
    private final FeeCalculator calculator = new FeeCalculator();

    @Test
    void addsFee() {
        assertEquals(120, calculator.total(100, 20));
    }

    @Test
    void rejectsNegativeAmounts() {
        assertThrows(
                IllegalArgumentException.class,
                () -> calculator.total(-1, 0)
        );
    }

    @Test
    void rejectsOverflow() {
        assertThrows(
                ArithmeticException.class,
                () -> calculator.total(Integer.MAX_VALUE, 1)
        );
    }
}
```

**Expected result:** IDE/JUnit Platform or the Gradle/Maven runner discovers **three** test methods; all three succeed. `total` prints nothing to stdout. Depending on the IDE/build tool, the console displays counts, passes, and timings in different formats; do not rely on one fixed log line as proof.

**How to run in the IDE:** import/reload the project, open `FeeCalculatorTest.java`, click Run next to the class to run all three or next to `addsFee` to run just one. Verify the execution report shows the exact number of selected methods.

**How to run via Gradle Wrapper on Linux/macOS:**

```bash
./gradlew --version
./gradlew test --tests "com.example.testing.FeeCalculatorTest"
./gradlew test --tests "com.example.testing.FeeCalculatorTest.addsFee"
```

**How to run via Maven Wrapper on Linux/macOS:**

```bash
./mvnw --version
./mvnw -Dtest=FeeCalculatorTest test
./mvnw "-Dtest=FeeCalculatorTest#addsFee" test
```

Pick **one** command set matching your actual build tool. With `--tests`, Gradle filters by fully qualified class/method. With Maven Surefire, `-Dtest=...` selects classes or methods; exact filtering capabilities depend on plugin version/configuration.

**Note on flags:** `-Dtest=...` is a *Maven Surefire test selector*. Do not assume every `-D...` passed to Gradle automatically becomes a system property on the JVM running the tests; Gradle may execute tests in a forked JVM.

## 5. Configuration in popular IDEs

### 5.1. IntelliJ IDEA: pick the right test runner

1. Open the project from the Gradle or Maven build file; wait for indexing and sync to finish.
2. Check **Project SDK**, Java language level, and for Gradle, **Gradle JVM** in the build tool settings. With Java Toolchains, ensure a matching JDK is available.
3. In a Gradle project, open **Settings / Build, Execution, Deployment / Build Tools / Gradle** and check **Run tests using** (exact menu names/paths may vary by version):
   - **Gradle:** uses Gradle to run tests, closer to the CLI/CI path and honors `Test` task configuration.
   - **IntelliJ IDEA:** uses the IDE's JUnit runner, often faster to start and convenient for debugging one test, though it may skip Gradle task customizations.
   - **Choose per test** if your IDE version supports it: pick the runner per run configuration.
4. Click the triangle icon next to the test class/method, inspect the **Run** tool window: which runner executed, which class/method was selected, and did all three methods actually run?
5. Rerun that test via **Gradle tool window → Tasks → verification → test** or a Gradle run configuration; compare with the terminal.
6. When debugging, use **Debug** on the same test; breakpoints must be on compiled/executed code rather than stale IDE/build artifacts.

**Common cause of drift:** learners pick "Run using IntelliJ IDEA", while the project defines `systemProperty`, `jvmArgs`, `environment`, `maxParallelForks`, or code/resource generation tasks only inside the Gradle `Test` task. Tests run by the IDE can receive a different classpath or properties. When results diverge, switch the runner to Gradle first to compare against the CLI, then fix the root cause.

### 5.2. Visual Studio Code: Java Test Runner and terminal are two paths

1. Install the appropriate Java extensions, including **Language Support for Java** and **Test Runner for Java** (usually bundled in **Extension Pack for Java**).
2. Open the right project root/workspace so the Java language server recognizes the Gradle or Maven project, test sources, and dependencies.
3. Check the **Java runtime/JDK** configuration for the workspace, especially when multiple JDKs are installed.
4. In the **Testing** view or the Run icon beside a test, choose Run/Debug for the class or method.
5. For tests needing extension-specific settings, VS Code supports test configurations such as `java.test.config`. Compare JVM args, environment, and working directory there with the build tool.
6. Open a terminal at the project root and run `./gradlew test` or `./mvnw test` as the reference path. Running via a VS Code task that invokes the wrapper still runs the build tool, unlike the extension invoking the Java test runner directly.

**Note:** seeing green in the Testing view alone does not confirm the CI test task ran; the VS Code extension and Gradle/Maven can launch tests differently.

### 5.3. Eclipse: JUnit Run As, Buildship, and m2e

1. Ensure Eclipse knows the right **Installed JRE/JDK** and project compiler compliance matches the project.
2. Import by project type: **Gradle/Buildship** or **Maven/m2e**; resync whenever build files change.
3. Verify `src/test/java` is a test source folder on the classpath and JUnit Jupiter dependencies are resolved.
4. Run `Run As → JUnit Test` (or your Eclipse version's equivalent) to test the IDE runner.
5. When comparing with build config, invoke the `test` task via Gradle tooling/terminal or the `test` goal via Maven tooling/terminal.
6. Use `Debug As → JUnit Test` for breakpoints; inspect VM arguments, environment, and working directory in the Run Configuration.

If a failure occurs only through the build tool, investigate plugins, tasks, source sets, and test execution config; do not blindly rewrite JUnit tests just to appease Eclipse's JUnit runner.

### 5.4. Common rules across all three IDEs

**Running a single method** does not replace **running the class/module/suite**. Maintain two habits:

- **Fast-feedback setup:** run the test you are editing to debug and read assertions close to the failure.
- **CI-equivalent verification:** run the exact wrapper task/goal and test scope used by CI.

You can use the IDE runner to learn and investigate, but the decision that "the test suite passes" should rest on the build tool, configuration, and scope recognized by build/CI.

## 6. Command-line commands you need and their true meaning

### 6.1. Gradle Wrapper

Linux/macOS, run at project root:

```bash
./gradlew --version
./gradlew test
./gradlew test --tests "com.example.testing.FeeCalculatorTest"
./gradlew test --tests "com.example.testing.FeeCalculatorTest.addsFee"
./gradlew test --rerun-tasks
./gradlew clean test
```

Windows PowerShell:

```powershell
.\gradlew.bat --version
.\gradlew.bat test --tests "com.example.testing.FeeCalculatorTest"
.\gradlew.bat test --rerun-tasks
```

Explanation:

- `./gradlew` uses the Wrapper-managed Gradle version, avoiding drift from a globally installed Gradle.
- `test` runs the task named `test` per project config and scope. In multi-project builds, pick the right task path, e.g., `./gradlew :service:test`, to target a specific module.
- `--tests` narrows classes/methods using Gradle's filter. If nothing matches, Gradle may report no matching tests found instead of running the whole suite.
- `--rerun-tasks` forces tasks to re-execute instead of trusting up-to-date state; useful to prove tests **actually ran again**, though it may rerun upstream dependency tasks as well.
- `clean test` deletes build outputs and runs a fresh build/test, which is slower and touches more tasks—not required for every debug cycle.

Gradle typically produces:

- Structured results: `build/test-results/test/`.
- HTML report: `build/reports/tests/test/index.html`.

In multi-project builds or custom tasks, report paths may sit under the module and match the task name. When you see `UP-TO-DATE`, `FROM-CACHE`, or `SKIPPED`, distinguish them from **tests actually executed and passed**.

### 6.2. Maven Wrapper

Linux/macOS, in the directory containing `pom.xml`:

```bash
./mvnw --version
./mvnw test
./mvnw -Dtest=FeeCalculatorTest test
./mvnw "-Dtest=FeeCalculatorTest#addsFee" test
./mvnw clean test
```

Windows PowerShell:

```powershell
.\mvnw.cmd --version
.\mvnw.cmd "-Dtest=FeeCalculatorTest" test
.\mvnw.cmd "-Dtest=FeeCalculatorTest#addsFee" test
```

Explanation:

- `test` runs the Maven lifecycle up to the `test` phase, normally using **Surefire** to find unit tests by naming patterns/configuration.
- `-Dtest=...` narrows tests with Surefire-supported syntax; if a method is not selected, check Surefire version, real method name, and JUnit engine.
- Surefire reports usually reside in `target/surefire-reports/`.
- In multi-module Maven projects, run in the right module or use `-pl`/`-am`; that scope does not automatically match clicking Run in an IDE.
- For **Failsafe integration tests** configured separately, you usually need the corresponding phase/goal, such as `verify`, to execute and check them.

**Do not mix flags:** Gradle `--tests` is not Maven `-Dtest`; Gradle's `test` task is not identical to Maven's `test` lifecycle phase, even though both can run the same JUnit Jupiter tests.

### 6.3. Reading errors instead of only reading `BUILD SUCCESS`

A valid comparison checks all of these together:

1. Did build/compilation succeed?
2. Did the runner discover **the right count and names of tests**?
3. Were any tests skipped, disabled, filtered out, or not run?
4. Did a test fail in assertions, context startup, dependency discovery, or external infrastructure?
5. Does the report file belong to the right module/task and the right run?

When Gradle errors are unclear, run `./gradlew test --stacktrace`; for more task/config detail, add `--info`. Maven provides `./mvnw -e test` for detailed stacktraces. Use verbose logging selectively because high log volume can bury the primary error.

## 7. Profiles, properties, and environment: common sources of IDE/CLI divergence

### 7.1. Where should test configuration live?

Independent tests should keep preconditions inside the test or test-specific configuration, minimizing dependence on how Run was clicked. For Spring integration tests, place test config in `src/test/resources/application-test.yml` and activate the profile via annotation:

**Illustrative snippet in a project with `@SpringBootApplication` discoverable from the package:**

```java
package com.example.testing;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
@ActiveProfiles("test")
class BootContextTest {
    @Autowired
    private ApplicationContext context;

    @Test
    void startsWithTestProfile() {
        assertNotNull(context);
    }
}
```

**Example `src/test/resources/application-test.yml`:**

```yaml
logging:
  level:
    root: WARN
```

`@ActiveProfiles("test")` is processed by Spring TestContext when creating the context; it has no effect on plain JUnit unit tests that do not use Spring TestContext. `BootContextTest` is a **Spring context test**, runnable only when the project has an actual Spring Boot application configuration and whatever dependencies/infrastructure the context needs. `FeeCalculatorTest` in Section 4 is standalone and needs no application.

You can use `@TestPropertySource`, test-specific properties, or `@DynamicPropertySource` (for dynamic ports from Testcontainers). Pick a clear mechanism and verify actual property precedence. Avoid setups where two runners require different manual tweaks just to pick up the same configuration.

### 7.2. Why adding `-Dspring.profiles.active=test` can still diverge

**Distinguish processes:**

- `./gradlew -Dsome.key=value test` can set a system property on the **Gradle JVM**, whereas Gradle tests usually run in a **forked JVM**. Do not assume the value forwards to tests unless the build task explicitly passes it.
- The IDE JUnit runner has its own **VM options** field. A value set via `systemProperty(...)` in a Gradle task is not automatically present in the IDE runner.
- Maven Surefire also manages test execution and system properties per plugin configuration. Check how the plugin forwards properties to the test JVM.

**Illustrative Gradle config** when you truly need to pass a property into the test JVM:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'app.test.flag', 'enabled'
}
```

Tests relying on that property receive it when run through the **Gradle task**. When running directly via the IDE JUnit runner, configure the equivalent VM option or move that precondition into test code/config. For Spring integration tests, `@ActiveProfiles("test")` usually keeps profile selection consistent regardless of launch command.

Never commit real passwords/tokens into `application-test.yml`. Use dummy test accounts, CI secrets, and controlled local setup whenever external connectivity is genuinely required.

### 7.3. Things to record when two environments produce different results

| Aspect | Example difference | How to narrow down |
|---|---|---|
| Java runtime | IDE uses JDK 21, terminal uses JDK 17 | Compare Project SDK, Gradle JVM, `java -version`, `./gradlew --version`, and toolchain |
| Profile | IDE activates `test`, CLI uses default profile | Put `@ActiveProfiles` on Spring tests or align runner configs |
| JVM properties | Gradle test task adds `-Dapp.test.flag`, IDE lacks it | Check VM options and `Test` task config |
| Environment | IDE has local env vars, CI lacks them | Compare required names/values, use safe test config |
| Working directory | Code reads files by relative path | Prefer classpath resources; check `user.dir` if needed |
| Classpath | IDE has not reloaded dependencies or manually added JARs | Sync build, rely on Gradle/Maven dependencies |
| Encoding/timezone | Default charset or zone differs | Use explicit UTF-8/zone and a controllable clock |
| Spring resources | `application-test.yml` missing from test classpath | Place in `src/test/resources` and verify resource processing |
| Testcontainers | Docker works from IDE, terminal/CI fails to connect | Check Docker engine/socket/permissions and test infra |
| Parallel/fork | CLI runs multiple forks; IDE runs a single test | Compare concurrency settings, remove shared state |

**Resource paths:** when reading files in `src/test/resources`, prefer `getResourceAsStream(...)` or Spring resource abstractions rather than `new File("src/test/resources/...")`. Relative paths depend on working directory, which easily differs between IDE, Gradle, Maven, and containers.

## 8. Re-running the same scope to pinpoint real discrepancies

A practical workflow using `FeeCalculatorTest`:

1. **Freeze inputs:** save all files, note commit/branch, selected JDK, and wrapper version; reload dependencies in the IDE.
2. **Run via IDE:** select the **entire class**; confirm all 3 tests run and pass. Record the runner: IntelliJ JUnit/Gradle, Eclipse JUnit, or VS Code Java Test Runner.
3. **Run via wrapper:** run the command filtering that exact class and module. For Gradle, if you want proof of fresh execution, add `--rerun-tasks`; for Maven, inspect the Surefire summary/report.
4. **Compare outputs:** identical test list, identical assertions, identical pass/fail/skip statuses. Execution time can differ due to JVM startup, incremental compilation, or context caching.
5. **If there is a discrepancy:** compare in order *scope/runner → JDK/toolchain → classpath/dependencies → profile/properties → resources/data/DB/Docker → parallelism/timing*. Change only one variable at a time to see which change has an effect.
6. **Final confirmation:** run the full test task or pipeline recognized by the project/CI rather than stopping at one filtered method.

For Spring context tests, follow the same steps while also verifying `@SpringBootTest` finds the right application configuration, creates the required beans, and loads test resources/profiles. Add integration tests to this comparison only after plain JUnit tests behave identically, avoiding mixing IDE/CLI drift with database or application startup errors.

### 8.1. Choosing a runner by goal

| Goal | Suitable choice | What to verify |
|---|---|---|
| Quickly debug an assertion | IDE JUnit runner | Classpath/VM args suffice for the test; no critical build setup skipped |
| Reproduce a Gradle CI failure | Gradle runner or `./gradlew ...` | Exact task path, test filter, JVM, properties |
| Reproduce a Maven CI failure | Maven goal via wrapper | Surefire/Failsafe, profile, test selection |
| Verify Spring + DB integration | Project's integration test task/goal | Profile, container, schema/migration, cleanup |
| Verify full suite before handoff | Wrapper with CI's exact task/goal | Test report, skipped tests, pipeline status |

**Do not use fast/slow as proof of right/wrong:** the IDE may be faster due to incremental compilation; Gradle may be faster due to caching; Maven may run with different forking. Timing differences are signals to measure and explain, not conclusions about correctness.

## 9. Diagnosing common scenarios

### 9.1. IDE finds tests, terminal reports "No tests found" or runs 0 tests

Check in order:

- Is `import org.junit.jupiter.api.Test` correct? Did JUnit 4's `org.junit.Test` slip in without a compatible engine?
- Are `spring-boot-starter-test` or JUnit Jupiter dependencies on the build tool's **test runtime classpath**?
- Has Gradle enabled `useJUnitPlatform()` on the right test task? Does Maven Surefire have a compatible version/provider?
- Is the file inside `src/test/java` or the source set actually targeted by the task/goal?
- Do `--tests` or `-Dtest` class/method filters match the exact name and module?
- Does the test have `@Disabled`, tag filters, or execution conditions causing it to be skipped?

**Do not arbitrarily rename tests** before reading discovery messages and reports; identify the missing mechanism so the rest of the tests run properly too.

### 9.2. IDE green, Gradle/Maven red

Common causes:

- IDE JUnit runner skipped settings in the task/plugin (JVM args, system properties, generated resources, test filters).
- Build tool uses a different JDK/toolchain or different dependency versions than the IDE's cached classpath.
- Running the full suite on the CLI exposes order-dependent tests or shared state; running a single test in the IDE masks the bug.
- The CLI runs integration tests, containers, or environments that the IDE did not execute.
- CI/Linux enforces case-sensitive paths that a local development OS masked.

**How to fix:** reproduce that exact class via the wrapper, compare runner/context/parameters, then fix the build configuration or test design. If tests pass individually yet fail together, check shared state/database/caches; do not blindly raise timeouts.

### 9.3. Terminal green, IDE red or IDE cannot see tests

Check whether the IDE imported the project from the build file and synced properly; whether test source roots are marked; whether JDK and dependencies match; whether the workspace opened the wrong submodule; and whether the Java language server/indexing completed. If Gradle passes while the IDE's built-in runner has classpath errors, switch IntelliJ to the Gradle runner or run the Gradle task to verify before tweaking IDE settings.

### 9.4. `Failed to load ApplicationContext`

This message indicates **Spring context startup failed**, not automatically a JUnit/IDE bug. Read the **first meaningful root cause** in the stacktrace:

- Is the right `@SpringBootApplication`/`@SpringBootConfiguration` discovered from the test's package?
- Did the test profile load the right configuration and required placeholders?
- Are database URLs, migrations, bean injection, ports, or external dependencies valid?
- If using Testcontainers, is Docker running and are dynamic connection properties passed via `@DynamicPropertySource` or a supported Spring Boot mechanism?
- Are the IDE and CLI running the same test class, active profiles, and resources?

With `@WebMvcTest` or `@DataJpaTest`, the context differs from `@SpringBootTest`; do not swap annotations just to turn a test green if the test scope requires the original context type.

### 9.5. Tests fail only in the full suite or under parallel execution

Check for static mutable state, singleton caches, shared DBs, colliding file paths, hardcoded ports, mutated timezone/global properties, or unawaited async operations. A single IDE run often targets one class/method, whereas the CLI runs the full suite or multiple forks, exposing non-isolated tests. Fix fixtures/isolate resources; enable parallelism only when prerequisites are met rather than pinning execution order to hide bugs.

### 9.6. Build succeeds yet no proof tests freshly ran

In Gradle, if `test` is `UP-TO-DATE` or `FROM-CACHE`, do not claim "all tests just re-ran"; use `--rerun-tasks` when the goal is verifying fresh execution. In Maven or Gradle, always check test counts and reports; a green build can still have excluded, skipped, or separate-task tests. In Maven, check whether skip-test flags were passed.

### 9.7. Debugger runs yet breakpoints never hit

Identify which JVM is actually executing the tests. When debugging via the IDE JUnit runner, the debugger attaches automatically; when running Gradle/Maven from the terminal, the IDE debugger does not automatically attach to the test worker JVM. With Gradle's `Test` task, depending on version you can pass `--debug-jvm` to pause until the IDE attaches to the test process; read the port message and connect to the right JVM. Also verify classes were rebuilt and the breakpoint sits on a code path actually invoked by the test.

## 10. Establishing a consistent workflow for teams and CI

A Spring Boot project should publish at least:

1. **Standard Wrapper:** commit valid Gradle/Maven Wrapper files; use the wrapper in docs, IDE imports, and CI.
2. **Java version:** declare release/toolchain or compiler config; CI provides the right JDK, IDE picks a compatible one.
3. **Test dependencies and runners:** declare in build files; configure JUnit Platform and Surefire/Failsafe consistently.
4. **Official tasks/goals:** document commands for unit tests, integration tests, and full suite runs; multi-module repos must note task paths/module selection.
5. **Self-contained test config:** prefer `@ActiveProfiles`, test resources, and clear fixtures; never rely on secret VM args existing only on one developer's laptop.
6. **Reports and failure policy:** CI reads test reports, fails on test errors, distinguishes skipped/disabled/no-tests; never treat "0 tests" as a pass.
7. **Test infrastructure:** define Docker/DB/test services, seed/cleanup, and timeouts for integration tests.
8. **IDE guide:** state which runner reproduces CI; the IDE runner works for quick debugging but does not replace final verification.

**Example team policy:** on a Gradle project, developers can click Run on `FeeCalculatorTest` for quick feedback; before opening a pull request, run `./gradlew test` (or the project's designated task). CI uses the wrapper with the same configuration and archives reports. When checking for flaky failures, force fresh execution with `--rerun-tasks` instead of relying on caches.

## 11. Self-assessment checklist

Before confirming "IDE and command-line setup match," verify:

- [ ] Project was imported from the Gradle/Maven build file, and IDE synced dependencies/test sources.
- [ ] JDK/Java toolchain matches; understand the difference between the Gradle JVM and the test JVM.
- [ ] `spring-boot-starter-test`/JUnit Jupiter and the build test runner are declared in the project.
- [ ] Know whether the IDE runs JUnit directly or delegates to Gradle/Maven.
- [ ] Can run the exact same test class and method in both the IDE and the wrapper.
- [ ] Both execution paths discover the right test count; do not confuse skipped/cached runs with fresh execution.
- [ ] Verified matching module, task/goal, test filter, package, and source set.
- [ ] Spring integration tests use the right active profile, test resources, and context configuration.
- [ ] No uncontrolled discrepancies in environment, JVM properties, working directory, timezone, or Docker/DB.
- [ ] Can locate test reports and root errors on failure in either execution path.
- [ ] CI runs the agreed test pipeline and stores results for traceability.

**Technical conclusion:** the IDE is an excellent tool for writing, selectively running, and debugging tests; **the build tool with its wrapper and project configuration is the reproducible source of truth**. Only when identical inputs and test scopes produce identical outcomes across both paths can we trust that the development environment is not masking suite failures.

## References

- [Spring Boot Reference — Testing](https://docs.spring.io/spring-boot/reference/testing/) — test starters, JUnit, and Spring Boot testing support.
- [Spring Boot Reference — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html) — `@SpringBootTest`, configuration, and test slices.
- [Gradle User Manual — Testing in Java & JVM Projects](https://docs.gradle.org/current/userguide/java_testing.html) — Test tasks, JUnit Platform, and filtering.
- [Gradle User Manual — Command-Line Interface](https://docs.gradle.org/current/userguide/command_line_interface.html) — Wrapper task execution, `--rerun-tasks`, and reporting.
- [Apache Maven Surefire — Running a Single Test](https://maven.apache.org/surefire/maven-surefire-plugin/examples/single-test.html) — `-Dtest` and method filtering.
- [IntelliJ IDEA — Testing in Gradle](https://www.jetbrains.com/help/idea/work-with-tests-in-gradle.html) — choosing between Gradle runner and IntelliJ IDEA runner.
- [Visual Studio Code — Testing Java](https://code.visualstudio.com/docs/java/java-testing) — Java Test Runner, Test Explorer, and test configurations.
- [JUnit User Guide](https://docs.junit.org/current/user-guide/) — JUnit Jupiter, discovery configuration, and test lifecycle.
