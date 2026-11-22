# Test Task in Java Build Integration

## Objectives

After this lesson, you will be able to explain the role of the test task in the Java build process; distinguish Gradle tasks from Maven lifecycle phases; understand how build tools compile tests, prepare the classpath, discover tests, and launch the test engine; configure JUnit Platform; run all or a subset of tests; read reports and handle test failures; separate unit tests from integration tests; control forking, parallel execution, and JVM options; integrate tests into CI; and troubleshoot common issues when the build tool does not discover or run tests as expected.

## 1. What is a test task?

A **test task** is a build step used to execute compiled tests and aggregate results. It connects test sources, test libraries, the runtime classpath, the test framework, the test JVM, and result reports.

When running tests from a build tool, the workflow typically includes:

1. Identifying test sources and test resources.
2. Compiling test sources.
3. Preparing the classpath with application code and test libraries.
4. Selecting the test engine corresponding to the framework.
5. Discovering valid test classes and test methods.
6. Launching the test process and executing tests.
7. Collecting results, logs, errors, and execution times.
8. Generating reports for developers and CI.
9. Marking the build as succeeded or failed based on the results.

A build tool is not a test framework. Gradle or Maven orchestrates test execution; JUnit, TestNG, and test engines provide the means to define, discover, and execute tests.

### Components to distinguish

| Component | Role |
|---|---|
| Build tool | Orchestrates tasks/phases and dependencies between steps |
| Test task or test phase | Launches the test execution process |
| Test source set | Groups sources, resources, and dependencies for tests |
| Test framework | API for writing tests such as JUnit Jupiter or TestNG |
| Test engine/provider | Discovers and executes tests according to the framework |
| Test JVM/process | The actual process that runs the tests |
| Test report | Test results in HTML, XML, or log format |

If a test engine is missing, the build may compile test classes but not know how to discover or run tests. If test sources are not in the right source set, the test task may not see the classes even though the files exist in the project.

## 2. How do Gradle tasks and Maven lifecycle phases differ?

The two build tools model builds differently.

- **Gradle:** `test` is a task of type `Test`. A task has its own inputs, outputs, dependencies, and configuration. The Java plugin creates this task and connects it to the test compilation tasks.
- **Maven:** `test` is a lifecycle phase in the default lifecycle. Maven executes preceding phases in order along with plugin goals bound to the `test` phase, typically `surefire:test`.

| Item | Gradle | Maven |
|---|---|---|
| Orchestration unit | Task | Lifecycle phase and plugin goal |
| Test command | `./gradlew test` | `mvn test` |
| Test runner component | Gradle task type `Test` | Maven Surefire Plugin |
| Default unit tests | Task `test` | Phase `test` |
| Integration tests | Can create a separate task such as `integrationTest` | Failsafe Plugin bound to `integration-test` and `verify` |
| Full verification | `check` or `build` | `verify` or `install` |

The key point is that a single test command can trigger many preparation steps. Do not think of `test` as simply calling a method in JUnit.

## 3. Test source locations by Java convention

Both the Gradle Java plugin and Maven use the standard source layout:

~~~text
project/
├── src/
│   ├── main/
│   │   ├── java/
│   │   └── resources/
│   └── test/
│       ├── java/
│       └── resources/
├── build.gradle
└── pom.xml
~~~

| Directory | Contents |
|---|---|
| `src/main/java` | Application source code |
| `src/main/resources` | Resources used when running the application |
| `src/test/java` | Test sources |
| `src/test/resources` | Resources exclusively for tests |

Test classes are usually placed in the same package as the class under test to easily access package-private APIs. Test sources are compiled separately and use a separate classpath, and are not packaged into the production artifact under default Java configuration.

In Gradle, the Java plugin creates the `main` and `test` source sets. In Maven, the directories above are the default project layout convention.

If a project uses different directories, you must configure the corresponding source sets or build plugins. Simply creating a test file in an arbitrary directory does not guarantee that the build tool will automatically find it.

## 4. How does the Gradle Java plugin create the test task?

When adding the Java plugin:

~~~groovy
plugins {
    id 'java'
}
~~~

Gradle creates the core tasks:

| Task | Function |
|---|---|
| `compileJava` | Compiles application sources |
| `processResources` | Copies application resources |
| `classes` | Aggregates steps to produce main classes |
| `compileTestJava` | Compiles test sources |
| `processTestResources` | Copies test resources |
| `testClasses` | Prepares test classes and resources |
| `test` | Runs unit tests |
| `check` | Aggregates verification steps, depends on `test` by default |
| `build` | Executes `check` and `assemble` |

The `test` task depends on `testClasses` and the tasks that produce the test runtime classpath. Therefore, when running:

~~~bash
./gradlew test
~~~

Gradle automatically executes the required dependencies before launching the test process.

You can visualize the task flow as:

~~~text
compileJava -----> classes
                      |
processResources -----+
                      |
                      v
                compileTestJava
                      |
processTestResources-+
                      |
                      v
                  testClasses
                      |
                      v
                    test
                      |
                      v
                    check
                      |
                      v
                    build
~~~

`classes` and `testClasses` are aggregate tasks: they group dependencies to prepare outputs rather than compiling code with a separate compiler themselves.

### Inspecting the task graph

List tasks:

~~~bash
./gradlew tasks --all
~~~

Preview which tasks will run without executing them:

~~~bash
./gradlew test --dry-run
~~~

Enable detailed logging:

~~~bash
./gradlew test --info
~~~

These commands are useful when you need to know why a task runs, which tasks depend on it, or why the test process has not been launched.

## 5. Gradle Test task executes tests in a separate JVM

Gradle uses the task type `org.gradle.api.tasks.testing.Test`. This task requires two core elements:

- Directories containing compiled test classes.
- An execution classpath containing application classes and the required test framework.

Tests typically run in one or more separate JVM processes, isolated from the Gradle daemon. This prevents the test classpath from polluting the build process and allows configuring the test JVM independently.

Some important properties:

| Property | Effect |
|---|---|
| `testClassesDirs` | Directories containing test classes |
| `classpath` | Classpath when running tests |
| `maxParallelForks` | Maximum number of test worker processes running in parallel |
| `forkEvery` | Maximum number of test classes run in one worker before forking a new JVM |
| `maxHeapSize` | Maximum heap size for the test JVM |
| `jvmArgs` | JVM arguments for the test process |
| `systemProperty` | System property passed to the test JVM |
| `environment` | Environment variables for the test process |
| `workingDir` | Working directory when running tests |
| `failFast` | Stops the task on the first failure |
| `ignoreFailures` | Does not fail the build on test failures |
| `failOnNoDiscoveredTests` | Controls whether the task fails when no tests are discovered |

By default, Gradle runs one test worker process for the `test` task. Increasing parallelism can make tests finish faster, but you must ensure tests are independent and do not overwrite shared data.

## 6. Test framework and test engine

The test framework provides the API for writing tests. The test engine is responsible for discovering and running tests at runtime.

JUnit 5 uses JUnit Platform as its foundation:

- **JUnit Platform:** launch and discovery foundation.
- **JUnit Jupiter:** API and engine for JUnit 5-style tests.
- **JUnit Vintage:** engine for running legacy JUnit 3/4 tests on JUnit Platform.

With Gradle, you need to configure the test task to use JUnit Platform and add the engine at runtime:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.13.1'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`testImplementation` provides JUnit Jupiter for compiling tests. `testRuntimeOnly` provides the JUnit Platform Launcher when the test process runs.

If using JUnit 4, you can configure the corresponding engine. If a project mixes JUnit 4 and JUnit 5, the Vintage Engine is needed so JUnit 4 tests run via JUnit Platform.

With Maven Surefire 3.6.0 and later, tests run through a unified JUnit Platform provider. Surefire automatically selects the appropriate engine/provider based on dependencies. Check the dependency tree when tests compile but do not run.

## 7. Discovery: how does the build tool find tests?

Test discovery is the process of finding classes and methods that meet the rules of the framework and build tool.

A test may not run even if the source compiles successfully because:

- The file is in the wrong source directory.
- The test class is not compiled into the output directory used by the task.
- The class name does not match include/exclude patterns.
- The test method is missing annotations or has invalid visibility/structure according to the framework.
- The test engine is not on the runtime classpath.
- A custom task points to the wrong `testClassesDirs` or `classpath`.
- The test is excluded by a filter, tag, or profile.

### Default test naming rules in Maven Surefire

By default, Surefire discovers classes matching common patterns:

- `Test*.java`
- `*Test.java`
- `*Tests.java`
- `*TestCase.java`

For example, `CalculatorTest` is typically discovered. A class named `CalculatorSpec` may not run unless a custom include pattern is configured.

### Gradle rules

The Gradle Java plugin automatically configures the `test` task to use the default test source set. Custom tasks must explicitly specify test class directories and classpath.

If there are no test sources or no candidate classes, the task may be marked `NO-SOURCE` or skipped. If test sources/classes exist but no tests are discovered, the `failOnNoDiscoveredTests` property (true by default) helps the build catch this situation. Read the logs to distinguish the two cases.

## 8. Running all or a subset of tests with Gradle

Run all tests:

~~~bash
./gradlew test
~~~

Run a single class:

~~~bash
./gradlew test --tests com.example.CalculatorTest
~~~

Run a single method:

~~~bash
./gradlew test --tests "com.example.CalculatorTest.addsTwoNumbers"
~~~

Run classes matching a wildcard:

~~~bash
./gradlew test --tests "*Calculator*"
~~~

Test filtering can use a fully-qualified class name or method name. Wildcard patterns let you run a group of tests without modifying the build script.

### Running the verification task

~~~bash
./gradlew check
~~~

`check` is a lifecycle task that aggregates verification steps. The Java plugin attaches `test` to `check` by default; other plugins may add static analysis, code quality, or custom verification tasks.

Run a full build:

~~~bash
./gradlew build
~~~

`build` depends on `check` and `assemble`. Therefore, this command is typically suitable for CI steps that require both artifacts and verification.

### Debugging the test process

You can run the test JVM in debug mode:

~~~bash
./gradlew test --debug-jvm
~~~

An IDE or debugger can attach to the debug port that Gradle opens for the test process. Enable this only when investigating a specific test and close the debug session afterward.

## 9. Configuring Gradle test execution

You can configure logging, JVM settings, system properties, filters, and parallel execution in the build script.

Groovy DSL example:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()

    maxParallelForks = 2
    maxHeapSize = '1g'

    systemProperty 'app.environment', 'test'

    testLogging {
        events 'passed', 'skipped', 'failed'
        exceptionFormat 'full'
        showStandardStreams = true
    }
}
~~~

Explanation:

- `maxParallelForks = 2` allows up to two test worker processes to run in parallel.
- `maxHeapSize` limits the heap size of each test JVM.
- `systemProperty` passes test configuration into the JVM.
- `testLogging` selects which events and level of detail are printed to the console.

Do not increase parallelism just because CI has many cores. Tests that write to the same file, share a port, modify the same database row, or depend on execution order can cause intermittent failures.

### forkEvery and process isolation

`forkEvery` specifies how many test classes are run in one worker process before Gradle starts a new worker.

- Value `0`: reuses the test process for all test classes; this is the default.
- Value `1`: creates a new process for each test class; has high startup overhead.
- Value `N`: creates a new process after every `N` test classes.

Forking a new process can isolate leaked state between test classes, but makes the build slower. Change this only when there is evidence of state leakage or an isolation requirement.

### Parallel tests need isolated data

Gradle provides the `org.gradle.test.worker` property with a unique value for each worker process. You can use this property to create non-overlapping filenames, temporary directories, or resource identifiers.

Tests must manage shared data themselves. Do not rely on test ordering or on one test always running before another.

## 10. Maven test phase and Surefire

Maven uses the default build lifecycle. For projects with JAR packaging, the `test` phase is bound to the `surefire:test` goal.

When running:

~~~bash
mvn test
~~~

Maven executes the phases required before `test`, including validating, processing resources, compiling main sources, processing test resources, and compiling test sources. Then Surefire runs unit tests.

Common phases:

| Phase | Meaning |
|---|---|
| `validate` | Validates the project and build information |
| `compile` | Compiles application sources |
| `test-compile` | Compiles test sources |
| `test` | Runs unit tests with Surefire |
| `package` | Packages the artifact |
| `integration-test` | Runs integration tests in the prepared environment |
| `verify` | Verifies results and quality criteria |
| `install` | Installs the artifact into the local repository |
| `deploy` | Deploys the artifact to a remote repository |

Running `mvn test` does not produce the final JAR. To create a package, use `mvn package`. If the project has integration tests bound to Failsafe, use `mvn verify`.

### Surefire Plugin

Surefire is designed to run unit tests in the `test` phase. It supports JUnit, JUnit Platform, and TestNG depending on plugin version and dependencies.

Surefire generates text and XML reports. Default directory:

~~~text
target/surefire-reports/
~~~

Example report files:

~~~text
TEST-com.example.CalculatorTest.xml
com.example.CalculatorTest.txt
~~~

XML reports can be used by CI servers to display test results, failures, and statistics.

### Selecting a test class in Maven

~~~bash
mvn -Dtest=CalculatorTest test
~~~

Wildcards can be used:

~~~bash
mvn -Dtest=Calculator*Test test
~~~

With the JUnit Platform provider, prefer filtering by class if compatibility across test engines and plugin versions is needed. Method selection syntax can depend on the provider/framework; check the documentation for your Surefire version before putting it into CI scripts.

## 11. Failsafe for integration tests in Maven

Unit tests typically test logic in a narrow scope. Integration tests verify coordination with the filesystem, database, HTTP server, message broker, or other services.

Maven has a separate plugin, Failsafe, for running integration tests. Failsafe has two goals:

- `failsafe:integration-test` runs integration tests.
- `failsafe:verify` verifies integration test results and fails the build if there are failures.

The integration test lifecycle typically consists of:

1. `pre-integration-test`: prepares the environment, containers, or services.
2. `integration-test`: executes integration tests.
3. `post-integration-test`: cleans up the environment and resources.
4. `verify`: verifies test results.

Failsafe does not fail the build immediately during the `integration-test` phase when a test failure is detected. This allows the `post-integration-test` phase to run and clean up resources before the `verify` phase decides whether the build passes or fails.

Therefore, invoke:

~~~bash
mvn verify
~~~

Do not invoke `mvn integration-test` alone in normal workflows. Stopping at that phase can prevent teardown steps in `post-integration-test` from running.

### Integration test naming

Failsafe has its own naming conventions for integration tests, typically starting with `IT` or ending with `IT`/`ITCase`. In the example below, the plugin explicitly configures an include for `**/*IT.java` so readers do not have to rely on remembering the default patterns.

Integration tests can still reside in `src/test/java` in a Maven project; Failsafe distinguishes tests using include/exclude patterns. In Gradle, you can create a separate source set and task.

## 12. Java 17+ Example: Calculator and test tasks

This example creates a project with a unit test for addition and an integration test for reading/writing files. The same source code can be run with Maven Surefire/Failsafe or Gradle.

### Project structure

~~~text
test-task-demo/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── com/example/
    │           ├── Calculator.java
    │           └── FileTotalStore.java
    └── test/
        └── java/
            └── com/example/
                ├── CalculatorTest.java
                └── FileTotalStoreIT.java
~~~

### Application source: Calculator.java

~~~java
package com.example;

public class Calculator {
    public int add(int left, int right) {
        return left + right;
    }
}
~~~

### Application source: FileTotalStore.java

~~~java
package com.example;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

public class FileTotalStore {
    public void save(Path file, int total) throws IOException {
        Files.writeString(file, Integer.toString(total),
                StandardCharsets.UTF_8);
    }

    public int load(Path file) throws IOException {
        String value = Files.readString(file, StandardCharsets.UTF_8);
        return Integer.parseInt(value);
    }
}
~~~

### Unit test: CalculatorTest.java

~~~java
package com.example;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {
    @Test
    void addsTwoNumbers() {
        Calculator calculator = new Calculator();

        assertEquals(7, calculator.add(3, 4));
    }
}
~~~

### Integration test: FileTotalStoreIT.java

~~~java
package com.example;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.io.IOException;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;

class FileTotalStoreIT {
    @TempDir
    Path tempDir;

    @Test
    void savesAndReadsTotalFromFile() throws IOException {
        Path file = tempDir.resolve("total.txt");
        FileTotalStore store = new FileTotalStore();

        store.save(file, 42);

        assertEquals(42, store.load(file));
    }
}
~~~

`@TempDir` tells JUnit to create an isolated temporary directory for the test and manage its lifecycle. This integration test exercises the real filesystem API, verifying file writing, reading, and encoding.

## 13. Complete Maven POM for the example

Create `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>test-task-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.junit</groupId>
                <artifactId>junit-bom</artifactId>
                <version>5.13.1</version>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.6.0</version>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.6.0</version>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                        <configuration>
                            <includes>
                                <include>**/*IT.java</include>
                            </includes>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The BOM keeps versions synchronized across JUnit artifacts. The `junit-jupiter` dependency provides the Jupiter API and engine needed for the tests.

Surefire runs `CalculatorTest` in the `test` phase. Failsafe selects `FileTotalStoreIT` via the include pattern in the `integration-test` phase and then verifies the results in the `verify` phase.

### Running with Maven

Run unit tests:

~~~bash
mvn test
~~~

Run a specific unit test:

~~~bash
mvn -Dtest=CalculatorTest test
~~~

Run unit tests, packaging, and integration tests:

~~~bash
mvn verify
~~~

After running, check:

~~~text
target/surefire-reports/
target/failsafe-reports/
~~~

In a successful run, the unit test report shows one passing test and the integration test report shows one passing test. Console summary lines may vary by Maven/plugin version, but the build must finish with `BUILD SUCCESS`.

## 14. Running the same example with Gradle

With Gradle, you can keep the Java files as-is and place test sources according to source sets.

Create `build.gradle`:

~~~groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter:5.13.1'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Gradle uses `src/test/java` for unit tests by default. To run only unit tests:

~~~bash
./gradlew test
~~~

Run a specific test class:

~~~bash
./gradlew test --tests com.example.CalculatorTest
~~~

Run all verification tasks:

~~~bash
./gradlew check
~~~

Default Gradle HTML report:

~~~text
build/reports/tests/test/index.html
~~~

XML test results:

~~~text
build/test-results/test/
~~~

### Creating a separate integrationTest task in Gradle

By default, the Java plugin only creates the `test` task for the `test` source set. If you need to separate integration tests, create an `integrationTest` source set and a task of type `Test`.

Move `FileTotalStoreIT.java` to:

~~~text
src/integrationTest/java/com/example/FileTotalStoreIT.java
~~~

Add to `build.gradle`:

~~~groovy
sourceSets {
    integrationTest {
        java.srcDir 'src/integrationTest/java'
        resources.srcDir 'src/integrationTest/resources'

        compileClasspath += sourceSets.main.output
        compileClasspath += configurations.testRuntimeClasspath

        runtimeClasspath += output + compileClasspath
    }
}

configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.register('integrationTest', Test) {
    description = 'Runs integration tests.'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath

    useJUnitPlatform()
    shouldRunAfter tasks.named('test')
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
~~~

The custom task uses the outputs of the integration test source set and its corresponding runtime classpath. `shouldRunAfter` orders execution when both tasks are requested; `dependsOn` attaches integration tests to the `check` lifecycle task.

Run integration tests:

~~~bash
./gradlew integrationTest
~~~

Run full verification:

~~~bash
./gradlew check
~~~

This example uses a custom source set and task to illustrate Gradle's mechanics. For larger projects, consider the JVM Test Suite DSL to model multiple test suites using Gradle's standard structure.

## 15. Test reports and how to read results

Reports help distinguish build failures caused by compilation, test assertions, test discovery, or the environment.

### Gradle

By default, Gradle generates:

- HTML report at `build/reports/tests/test/index.html`.
- XML results at `build/test-results/test/`.
- Internal binary results for generating reports.

Reports show test suites, classes, methods, durations, failures, and stack traces. Custom tasks can have their own reports based on the task name.

### Maven Surefire and Failsafe

Surefire:

~~~text
target/surefire-reports/
~~~

Failsafe:

~~~text
target/failsafe-reports/
~~~

Both plugins generate text and XML reports. Failsafe also generates a summary report to verify integration tests.

### Distinguishing test results from build results

| Result | Meaning |
|---|---|
| Tests passed | Discovered tests all passed |
| Tests failed | Assertion or test logic failed |
| Tests errored | Test encountered an exception/execution error other than an assertion failure |
| Tests skipped | Test was skipped via annotation/configuration |
| No tests discovered | Build tool found no valid tests |
| Test JVM crashed | The test process failed to start or terminated abnormally |
| Compilation failed | Test sources failed to compile; test task did not execute |

A build can fail before a single test runs. Always read the first failing task/phase and its related report.

## 16. Selective test execution and controlling test skipping

During development, running a single test class gives faster feedback. However, CI pipelines should run the full test suite according to project policy.

### Gradle

Run a single class:

~~~bash
./gradlew test --tests com.example.CalculatorTest
~~~

Run a single method:

~~~bash
./gradlew test --tests "com.example.CalculatorTest.addsTwoNumbers"
~~~

Re-run the task regardless of up-to-date status:

~~~bash
./gradlew test --rerun-tasks
~~~

Exclude the test task:

~~~bash
./gradlew build -x test
~~~

`-x test` excludes the `test` task from that run's build graph. Use this intentionally, as verification steps that depend on tests will no longer check what is required.

### Maven

Run a specific class:

~~~bash
mvn -Dtest=CalculatorTest test
~~~

Skip test execution while still compiling test sources:

~~~bash
mvn -DskipTests package
~~~

Skip both compiling test sources and executing tests:

~~~bash
mvn -Dmaven.test.skip=true package
~~~

These two Maven options are not the same. `skipTests` keeps the test compilation step; `maven.test.skip` skips both compiling and running tests.

Do not include skip options in regular CI commands if the pipeline requires tests as a quality gate. When skipping tests is unavoidable in a special situation, document the reason clearly and re-run full verification before releasing.

## 17. Test tasks in CI pipelines

CI typically runs test tasks after checking out sources and setting up the JDK/build tool.

A basic pipeline:

1. Check out the exact commit.
2. Install or select the JDK/toolchain.
3. Use the repository's Gradle Wrapper or Maven Wrapper.
4. Resolve dependencies.
5. Compile main and test sources.
6. Run unit tests.
7. Run integration tests if the pipeline has the required environment.
8. Collect XML/HTML reports even when tests fail.
9. Mark the job as succeeded/failed based on the exit code.
10. Proceed to publish/deploy only after mandatory quality gates pass.

Common Gradle command:

~~~bash
./gradlew clean check
~~~

Common Maven command:

~~~bash
./mvnw clean verify
~~~

On Windows, use the corresponding wrappers:

~~~powershell
gradlew.bat clean check
mvnw.cmd clean verify
~~~

Wrappers ensure CI uses the exact build tool version declared by the project, reducing differences between developer machines and runners.

### Multi-module projects

Gradle can run a task on a specific module:

~~~bash
./gradlew :service:test
~~~

Maven can select a project/module and build its required dependencies:

~~~bash
mvn -pl service -am test
~~~

`-am` tells Maven to also build the modules that the selected module depends on. This prevents the module tests from accidentally using stale artifacts from the local repository.

### Preserving reports when a job fails

CI should configure test report uploads in a step that always runs, even if the test task exits with a non-zero code. If reports are only uploaded after a successful build, the failures that most need investigation will have no reports available.

## 18. Incremental builds and task outcomes in Gradle

Gradle tracks task inputs and outputs to avoid repeating unnecessary work when existing results are still valid.

Common task outcomes:

| Outcome | Meaning |
|---|---|
| EXECUTED | The task executed |
| UP-TO-DATE | Inputs/outputs did not change, so re-running was unnecessary |
| FROM-CACHE | Outputs were restored from the build cache |
| NO-SOURCE | No matching sources for the task to process |
| SKIPPED | The task was skipped by condition or configuration |
| FAILED | The task executed and failed |

Do not confuse `UP-TO-DATE` with tests being disabled. Gradle may determine that current outputs are still valid relative to declared inputs.

However, tests that depend on external state such as a shared database, remote service, or files modified outside the build may not be fully described in task inputs. In that case, `UP-TO-DATE` does not necessarily reflect the latest state of the external system.

How to handle this:

- Declare required inputs/outputs and dependencies explicitly.
- Prepare fixtures/databases in a repeatable way.
- Use `--rerun-tasks` to verify whether the task runs again.
- Avoid tests that depend on external state outside the build without setup/cleanup.
- Do not manually delete build outputs to force tests to run when an appropriate Gradle command exists.

## 19. Parallel execution and test isolation

Running tests in parallel can reduce total duration, but introduces interactions between tests.

Common risks:

- Two tests writing to the same file or database record.
- Tests sharing a port or queue name.
- Tests depending on execution order.
- Static mutable state persisting between tests.
- Tests using uncontrolled clocks or randomness.
- Cleanup not finishing before another test uses the resource.

In Gradle, `maxParallelForks` controls the number of worker processes for a `Test` task. A build can also run multiple different `Test` tasks concurrently; Gradle still caps total processes according to the build's worker configuration.

In Maven Surefire, `forkCount` and `reuseForks` control the number of forked JVMs and process reuse. Parallel execution also depends on the test framework/provider and plugin configuration.

Start with sequential execution. Enable parallelism only after tests have clear isolation and repeatable, stable results.

## 20. Configuring the test JVM and environment

The test JVM may need different settings from the build JVM or the production application JVM.

Gradle example:

~~~groovy
tasks.named('test') {
    useJUnitPlatform()

    minHeapSize = '256m'
    maxHeapSize = '1g'

    jvmArgs '-Dfile.encoding=UTF-8'
    systemProperty 'app.environment', 'test'

    environment 'APP_TEST_MODE', 'true'
    workingDir = project.projectDir
}
~~~

Maven Surefire can configure JVM arguments via `argLine` and system properties via `systemPropertyVariables` when running forked test processes.

Do not put production secrets in test JVM arguments or logs. Use dedicated test credentials and provide them through CI's secret management mechanism.

If tests need a database or HTTP service, control endpoints and ports, credentials, dedicated databases/schemas, timeouts, setup and teardown, network availability, and resource cleanup when tests fail.

A test that depends on an external service not declared as a pipeline dependency may pass on a laptop and fail in CI.

## 21. Distinguishing unit tests, integration tests, and end-to-end tests

The test task is where execution happens; the test type is determined by the test's scope and dependencies.

| Test type | Scope | Example |
|---|---|---|
| Unit test | A single class or small piece of logic, with isolated dependencies | Calculator adding two numbers |
| Integration test | Multiple components working together with real resources or test instances | Reading/writing files, database repository |
| Component test | A component or service with controlled dependencies | REST controller + service + test database |
| End-to-end test | Business workflow across multiple systems | Logging in and completing an order over HTTP |

Not every test placed in the `test` task is a unit test. Build tools do not infer the test type from method contents; naming, source sets, tags, tasks, and plugin configuration determine where tests run.

Separating suites by runtime and dependencies helps CI organize pipelines effectively: unit tests run frequently, integration tests run in a prepared environment, and end-to-end tests run at the appropriate stage.

## 22. Common issues and troubleshooting

### Test class compiles successfully but does not run

**Cause:** Class name does not match patterns, wrong source directory, missing test engine, or a filter is excluding the test.

**Fix:** Check the compiled test classes output; check Surefire include/exclude patterns or Gradle filters; confirm JUnit Platform/Jupiter Engine is on the runtime classpath.

### Gradle reports NO-SOURCE

**Cause:** The source set has no matching sources or the task points to the wrong directory.

**Fix:** Check `src/test/java`, `sourceSets`, and `testClassesDirs`; confirm the task uses the right source set.

### Gradle does not discover tests even though classes exist

**Cause:** Classes are not compiled, annotations are invalid, the engine is missing, or a custom `Test` task is missing its classpath.

**Fix:** Run `compileTestJava` and inspect the output; check `useJUnitPlatform()`; for custom tasks, configure both `testClassesDirs` and `classpath`.

### Maven test does not run classes with non-conventional names

**Cause:** The class does not match Surefire's default patterns.

**Fix:** Rename following conventions such as `*Test.java` or explicitly configure includes/excludes in the plugin.

### JUnit 5 tests compile but are not executed

**Cause:** JUnit Jupiter engine or JUnit Platform provider is not on the runtime classpath; the plugin is too old or framework configuration does not match.

**Fix:** Inspect the dependency tree; use `junit-jupiter`; configure `useJUnitPlatform()` for Gradle; use a Surefire/Failsafe version compatible with JUnit Platform.

### Maven verify runs integration tests but the environment is not cleaned up

**Cause:** Calling the `integration-test` phase directly or setup/teardown plugins are not bound to the right lifecycle phases.

**Fix:** Run `mvn verify` so both `post-integration-test` and `verify` execute; check execution bindings of Failsafe and environment-management plugins.

### Tests pass locally but fail in CI

**Cause:** Differences in JDK, timezone, locale, environment variables, filesystem, dependent services, or test data.

**Fix:** Pin toolchains and environments; use wrappers; provide isolated test data; inspect XML reports and test JVM logs; avoid relying on local machine state.

### Tests fail intermittently

**Cause:** Race conditions, shared resources across tests, fixed sleeps, uncontrolled clocks/randomness, or incomplete cleanup.

**Fix:** Make tests deterministic; use proper synchronization and timeouts; create isolated resources per worker; do not depend on test order; repeat tests to reproduce.

### Test task takes too long

**Cause:** Integration tests calling real services, overly long timeouts, blocked tests, or inappropriate parallelism.

**Fix:** Review reports by duration; split suites; identify slow tests; use reasonable timeouts; enable parallelism only when isolation is guaranteed.

### Build fails before running tests

**Cause:** Main source compilation, test source compilation, dependency resolution, or task setup failed.

**Fix:** Read the first failing task/phase; fix compilation or dependency issues first; do not diagnose this as a test assertion failure if the test process never ran.

### CI reports BUILD SUCCESS even though tests did not run

**Cause:** Tests were skipped, tasks were excluded, a Maven skip property was enabled, or test discovery was not checked.

**Fix:** Check command-line arguments and environment properties; inspect the task graph; enable appropriate no-discovered-tests checks; ensure CI runs `check` or `verify` as the quality gate.

## 23. Workflow for using test tasks in projects

### When developing a feature

1. Write tests in the test source set.
2. Run the relevant test class for fast feedback.
3. Run all unit tests before finishing the change.
4. Inspect reports when failures occur.
5. Add integration tests when logic crosses boundaries with real resources.
6. Run verification tasks before creating a commit/PR.

### When fixing a bug

1. Create a test that reproduces the bug.
2. Run the test and confirm it fails before fixing.
3. Fix the code.
4. Re-run the relevant test.
5. Run the full suite.
6. Check regression and integration tests if the change affects multiple components.

### When configuring CI

1. Use wrappers and a consistent JDK/toolchain.
2. Run Gradle `check` or Maven `verify`.
3. Do not enable test skipping in quality gate jobs.
4. Collect reports even when the job fails.
5. Publish artifacts only after mandatory tests pass.
6. Separate slow suites or suites requiring dedicated services into appropriate stages.
7. Monitor flaky tests and execution times across builds.

## 24. Test task checklist

### Project configuration

- [ ] Correct JDK and build tool versions.
- [ ] Test sources are in the configured source set/directory.
- [ ] Test dependencies have the appropriate scope.
- [ ] Test engine/provider is on the runtime classpath.
- [ ] Test naming and discovery patterns match.
- [ ] Gradle custom tasks have the correct `testClassesDirs` and `classpath`.
- [ ] Maven Surefire/Failsafe versions are explicitly pinned.

### Execution

- [ ] The intended task/phase is invoked.
- [ ] Tests compile successfully.
- [ ] Test discovery finds the expected number of tests.
- [ ] Filters do not accidentally exclude tests that should run.
- [ ] Test JVM uses the right arguments, environment, and working directory.
- [ ] Parallelism does not cause data conflicts.
- [ ] Integration environment has setup/teardown.

### Results and CI

- [ ] HTML/XML reports have been reviewed.
- [ ] Assertion failures, errors, and compilation failures are distinguished.
- [ ] Test reports are saved when the CI job fails.
- [ ] No unintended skip properties are set.
- [ ] CI uses wrappers and the same JDK/toolchain.
- [ ] Quality gate invokes `check` or `verify` as appropriate.
- [ ] Build publishes/deploys only when mandatory tests have passed.

## 25. Official references

- [The Java Plugin — Gradle 9.9](https://docs.gradle.org/9.9.0/userguide/java_plugin.html) — `test`, `testClasses`, source sets, `check`, `build`, and dependency configurations.
- [Testing in Java & JVM Projects — Gradle 9.9](https://docs.gradle.org/9.9.0/userguide/java_testing.html) — test execution, discovery, filtering, reports, and parallel execution.
- [Test — Gradle DSL Reference](https://docs.gradle.org/current/dsl/org.gradle.api.tasks.testing.Test.html) — `Test` task configuration, JVM options, workers, filters, and reports.
- [Introduction to the Build Lifecycle — Maven](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html) — default lifecycle, `test` phase, `verify`, and execution order.
- [Maven Surefire Plugin](https://maven.apache.org/surefire/maven-surefire-plugin/) — running unit tests, reports, and test configurations.
- [Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/) — `integration-test`, `verify`, and teardown management.
- [JUnit 5 User Guide — Build Support](https://docs.junit.org/5.13.1/user-guide/) — JUnit Jupiter, JUnit Platform, dependencies, and Gradle/Maven configuration.

The test task is the bridge between test code and the build process. Check source sets, classpath, test engine, discovery, test JVM, and reports together to know exactly which tests ran. With Gradle, use `test` and `check` according to the task graph; with Maven, use `test` for unit tests and `verify` when Failsafe integration tests are needed. When a build fails, identify the first failing task or phase before modifying tests or configuration.
