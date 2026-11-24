# Distinguishing `skipTests`, `maven.test.skip`, and Gradle Test Task Exclusion

## 1. Why "Not Running Tests" Has Multiple Different Meanings

In a Spring Boot project, when developers want to build a JAR quickly for manual testing, they commonly encounter three commands:

~~~bash
./mvnw clean package -DskipTests
./mvnw clean package -Dmaven.test.skip=true
./gradlew clean build -x test
~~~

They all look like "building without tests," yet their mechanisms **are not the same**:

- **Maven -DskipTests**: for **Maven Surefire Plugin**, skips **unit test execution**, while Maven Compiler Plugin still **compiles test sources** per the normal lifecycle.
- **Maven -Dmaven.test.skip=true**: property recognized by Maven Compiler Plugin, Surefire, and Failsafe; it skips **test compilation** as well as **test execution** across those plugins.
- **Gradle -x test** (full form **--exclude-task test**): removes the **test** task from Gradle's execution graph for that invocation, and can also exclude dependency tasks needed solely by the test task. It is **not** a Maven property and does not mean every verification task in the build is excluded.

The important questions are not just "did assertions run?", but also:

1. Is **src/test/java** compiled?
2. Are **src/test/resources** processed/copied?
3. Are **unit tests** executed?
4. Are **integration tests**, **functional tests**, or other custom Test tasks executed?
5. Do other tasks/plugins such as quality checks, packaging, coverage, or verification still run?
6. Can CI claim the build **was tested** based on that outcome?

**Goal:** accurately distinguish each option, understand the Maven lifecycle and Gradle task graph, read log/output signals, practice with a Java 17 + Spring Boot project, and use skip flags responsibly without creating a false sense of security.

## 2. Foundations: Maven Phases Differ from Gradle Tasks

### 2.1. Maven: Running a Lifecycle Up to a Phase

With **jar** packaging, calling **./mvnw package** walks Maven through preceding phases in the **default lifecycle** and their bound plugin goals:

~~~text
validate
   |
process-resources       -> copy/filter main resources
   |
compile                 -> maven-compiler-plugin:compile
   |
process-test-resources  -> copy/filter test resources
   |
test-compile            -> maven-compiler-plugin:testCompile
   |
test                    -> maven-surefire-plugin:test (when bound)
   |
package                 -> create JAR/WAR; Spring Boot may repackage
~~~

The diagram shows only representative phases/goals. Many intermediate phases exist; exact bindings depend on **packaging**, parent POM, plugin executions, and profiles. Crucially, **test-compile precedes test**; skipping only Surefire execution still lets Maven reach test-compile.

In a Spring Boot project inheriting from **spring-boot-starter-parent** and declaring **spring-boot-maven-plugin**, the package phase normally creates the archive and runs **repackage** into an executable JAR. **-DskipTests** and **-Dmaven.test.skip** do not skip main compilation, packaging, or repackaging.

### 2.2. Gradle: Selecting Tasks and Resolving the Dependency Graph

With the Java plugin, common tasks include:

~~~text
classes ----> compileJava, processResources
    |
    +----------------------+
                           |
testClasses ----> compileTestJava, processTestResources
    |                      |
    v                      v
   test ---------------> check --------> build
                                            ^
                                            |
                                assemble / jar / bootJar ...
~~~

This is a **conceptual diagram** to illustrate relationships, not exact Gradle graph output: in practice **test** depends on **testClasses**, **check** depends on **test**, **build** depends on **check** and **assemble**; **testClasses** depends on main classes; **assemble**/bootJar have their own dependencies. Running **./gradlew build** normally triggers the Java plugin's test task. Running **./gradlew bootJar** focuses on packaging the executable archive and **does not automatically run the test task**.

**-x test** changes the **selected task set** for a single invocation. It differs from setting **test.enabled = false** or **test.onlyIf { false }**, because the latter keep the task in the graph while skipping its actions. That distinction affects whether **compileTestJava** still gets selected.

## 3. Comparison Table of the Four Core Options

| Invocation / Control | Compiles main? | Compiles test source? | Executes unit tests? | Other steps? |
| --- | --- | --- | --- | --- |
| **./mvnw clean package** | Yes | Yes | Yes, if Surefire and tests are configured | Packaging and other plugin goals run |
| **./mvnw clean package -DskipTests** | Yes | **Yes** | **No** for Surefire | Packaging still runs; integration tests depend on Failsafe version/config |
| **./mvnw clean package -Dmaven.test.skip=true** | Yes | **No**, for Compiler Plugin honoring property | **No**, for Surefire/Failsafe honoring property | Packaging still runs; custom plugins may vary |
| **./gradlew clean build -x test** | Yes when needed by graph | **Usually no** in standard Java plugin if only test needs it | **No**, because test task is excluded | build/assemble/other check tasks can still run |

**Assumptions of the table:** standard Maven project with Maven Compiler Plugin and Surefire, standard Gradle project applying Java + Spring Boot plugins, with no unusual custom dependency graph. If you have custom test tasks, integration-test plugins, extra source sets, code generation in testCompile, or special profiles, inspect the real build: never assume "all tests are skipped" from a single flag.

**Note on test resources:** -Dmaven.test.skip is not a "ignore everything under src/test" command. The Maven lifecycle may still run **process-test-resources** if the resources goal is bound. Likewise, Gradle -x test may omit processTestResources when only test depends on it, unless another task consumes that output. Keep **copying resources**, **compiling tests**, and **running tests** distinct.

## 4. Maven -DskipTests: Skips Surefire Execution, Still Compiles Tests

### 4.1. Commands and Mechanism

~~~bash
./mvnw clean package -DskipTests
./mvnw clean verify -DskipTests=true
~~~

Both boolean forms behave identically for Surefire configurations honoring **skipTests**. Maven passes a **user property** named **skipTests**; Maven Surefire Plugin reads it and skips executing unit tests.

Key points:

- Maven still compiles **src/main/java**.
- In the standard lifecycle, Maven Compiler Plugin still runs **testCompile** and compiles **src/test/java**.
- A **syntax or type error in test code** still fails the build even with **-DskipTests=true**, because test compilation runs.
- Surefire does not execute discovered test methods/classes. No fresh test results prove assertions passed in this build.
- Maven still builds the executable Spring Boot JAR if all other phases/goals succeed.

**Appropriate scenario:** needing a quick JAR for debugging while still verifying **test sources compile**. This is a lower-risk shortcut than skipping test compilation entirely, though it **never replaces testing**.

### 4.2. Why Doesn't skipTests "Skip Everything Test-Related"?

Surefire handles **test execution** in the test phase; Compiler Plugin handles **test compilation** in the test-compile phase. The **skipTests** flag belongs to Surefire and is not the compiler's skip parameter by default. Therefore:

~~~text
-DskipTests=true
      |
      +--> compiler:compile       -> STILL runs
      +--> compiler:testCompile   -> STILL runs
      +--> surefire:test          -> SKIPS test case execution
      +--> package/repackage      -> STILL runs
~~~

These lines describe typical behavior, not verbatim Maven logs. The build can still fail on an earlier error or another plugin before reaching package.

### 4.3. Outputs to Observe

After a successful clean build with **-DskipTests**, Maven typically produces:

~~~text
target/classes/          # application classes
target/test-classes/     # compiled test classes
target/<artifact>.jar    # packaged JAR
~~~

Meanwhile **target/surefire-reports** may not exist after **clean** because Surefire did not execute tests in that run. If you see stale reports when omitting clean, **never count them as evidence that tests ran in the current build**.

Inspect logs for **maven-compiler-plugin:testCompile** and **maven-surefire-plugin:test**. When the plugin reports tests skipped, conclude **execution was skipped**, not that tests passed.

## 5. Maven -Dmaven.test.skip=true: Skips Test Compilation Too

### 5.1. Commands and Mechanism

~~~bash
./mvnw clean package -Dmaven.test.skip=true
./mvnw clean verify -Dmaven.test.skip=true
~~~

**maven.test.skip** is a property honored by **Maven Compiler Plugin**, **Maven Surefire Plugin**, and **Maven Failsafe Plugin** per their documentation. When set to **true**:

- **Compiler Plugin** skips compiling test sources.
- **Surefire** skips executing unit tests.
- **Failsafe** skips integration tests it handles when configured in the build.
- **Main sources** still compile; package/repackage still runs.
- It does **not** verify that code in **src/test/java** even compiles.

This is the major difference from **-DskipTests**. A test calling a nonexistent method, having broken imports, or containing syntax errors will **go undetected** when test compilation is skipped.

### 5.2. Mechanism Diagram

~~~text
-Dmaven.test.skip=true
      |
      +--> compiler:compile       -> STILL runs
      +--> compiler:testCompile   -> SKIPPED
      +--> surefire:test          -> SKIPPED
      +--> failsafe:*             -> SKIPPED related test/verify per config
      +--> package/repackage      -> STILL runs
~~~

**Do not treat maven.test.skip as "disabling every quality/testing plugin."** Custom plugins or quality checks (Checkstyle, SpotBugs, JaCoCo, other IT plugins, frontend tests...) might **ignore this property**. Other phases still run. If the pipeline enforces security scans or custom validations, they can still execute or fail.

### 5.3. When Should It Be Used?

Use it only intentionally for temporary packaging in an environment where test compilation is blocked by an **already-understood issue** and you explicitly accept leaving test code unverified for that run—for example, checking main artifact runtime behavior during diagnostics, **never** for producing a "verified" release artifact.

The risk is producing a successful JAR while test sources no longer compile. This flag should remain visible in build logs and never be silently baked into release policies.

## 6. Maven Failsafe and Integration Tests: Version Differences to Watch

A Spring Boot project with only starter-test **does not automatically run integration tests via Failsafe**. Failsafe must normally be declared and bound to **integration-test** and **verify** in the lifecycle; such tests often use suffixes like **IT** or **ITCase** per plugin conventions.

Three relevant flags:

| Property | Effect on typical plugins |
| --- | --- |
| **-DskipTests=true** | Surefire skips unit test execution. From **Failsafe 3.6.0 onward**, no longer automatically binds this CLI property to skip integration tests |
| **-DskipITs=true** | Failsafe skips executing integration tests while still allowing test compilation |
| **-Dmaven.test.skip=true** | Compiler Plugin skips test compilation; Surefire/Failsafe skip test execution |

**Important version nuance:** Older Failsafe guides state that **-DskipTests** skips integration tests too. Starting with **Failsafe 3.6.0**, Failsafe **no longer binds** its skipTests parameter to the skipTests user property; official documentation specifies **-DskipITs** to skip integration tests. Thus, if a pipeline runs both Surefire and Failsafe, **do not assume -DskipTests skips both**. Check the **actually resolved** Failsafe version via effective POM and inspect each plugin's logs/reports.

When you want to run only integration tests without unit tests (e.g., an IT suite with full setup), **-DskipTests** works in Failsafe 3.6+ environments; it is not guaranteed in older Failsafe or custom configurations. To skip only Failsafe ITs while still running Surefire unit tests:

~~~bash
./mvnw verify -DskipITs=true
~~~

This still compiles test classes per the normal lifecycle. To inspect plugin versions and executions in a project:

~~~bash
./mvnw help:effective-pom
./mvnw help:describe -Dplugin=org.apache.maven.plugins:maven-failsafe-plugin -Dgoal=integration-test -Ddetail=true
~~~

**Failsafe goal ordering matters:** the plugin uses integration-test to execute tests and verify to evaluate results and fail the build if needed. Run **mvn verify** with Failsafe bound and unskipped for full verification pipelines, rather than stopping at **mvn package** and claiming integration tests were checked.

Official sources:
- https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html
- https://maven.apache.org/surefire/maven-failsafe-plugin/examples/skipping-tests.html
- https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html

## 7. Gradle -x test: Removing a Task from the Execution Graph

### 7.1. Basic Commands

~~~bash
./gradlew build -x test
./gradlew clean build --exclude-task test
~~~

The **-x** flag is shorthand for **--exclude-task**. When Gradle builds the execution graph for **build**, the task named **test** is removed from the tasks to execute within the command's task resolution scope. With the standard Java plugin, when no other consumer needs test outputs, tasks serving only test—such as **compileTestJava** or **processTestResources**—may also be omitted.

However:

- **compileJava**, **processResources**, **classes**, **jar**, **bootJar**, **assemble**... still run according to the dependency graph.
- **build** can still succeed even though test did not run; success **does not prove unit tests passed**.
- If the build has custom **integrationTest**, **functionalTest**, **testSmoke**, or other **Test**-typed tasks, **-x test** does not automatically exclude them; inspect exact task names/paths and the actual graph.
- A test task **explicitly requested by the user** or custom tasks with specialized behavior must be analyzed in the graph rather than guessed by name.
- With multiple subprojects, specify clearly which task to exclude (e.g., **:app:test**) and verify with **--dry-run** or task outputs instead of assuming one argument sets policy across all modules.

### 7.2. -x Also Drops Test-Only Dependency Tasks

Typical Java plugin graph:

~~~text
build
├── assemble
│   └── jar / bootJar / classes
└── check
    └── test
        └── testClasses
            ├── compileTestJava
            └── processTestResources
~~~

When invoking **./gradlew build -x test**, the **test** branch is pruned. Tasks needed exclusively by that branch can disappear from the graph. This **differs** from Maven **-DskipTests**: Maven still executes test-compile, whereas Gradle -x test **usually does not compile test sources** in a standard Java plugin layout.

**Do not state unconditionally** that Gradle -x test always skips test compilation. Another plugin or an explicitly requested CLI task may still depend on **testClasses** or **compileTestJava**, keeping those tasks in the graph. To be certain, inspect the graph for the exact command.

### 7.3. Previewing the Execution Plan Without Running Tests

~~~bash
./gradlew build --dry-run
./gradlew build -x test --dry-run
~~~

Compare the printed task lists. In the first command, test normally appears when the Java plugin is active; in the second, **test** is absent. During Gradle dry-run, remaining tasks may print as **SKIPPED** because Gradle simulates task execution without running task actions—this is **not** proof that code compiled or tests ran. -x removes the task **from the graph**, unlike a task **present in the graph and marked SKIPPED**.

**Warning:** dry-run still evaluates settings/build scripts and plugins; it does not guarantee the configuration phase has zero I/O or side effects. Use it for observing task plans, not as a strict sandbox.

Sources: https://docs.gradle.org/current/userguide/java_testing.html and https://docs.gradle.org/current/userguide/controlling_task_execution.html

## 8. Gradle: -x, enabled=false, and onlyIf Differ

### 8.1. Comparison Table

| Approach | Is test in the task graph? | Do task actions run? | Can test compile dependencies run? |
| --- | --- | --- | --- |
| **build -x test** | **No** (excluded from graph by selection) | No | Only if another task still requires test compilation |
| **test.enabled = false** | Usually remains in graph with status SKIPPED | No | **Possibly**, because task dependencies are still resolved/executed |
| **test.onlyIf { false }** | Task is still selected, actions skipped, logged SKIPPED | No | **Possibly**, because dependency tasks can still execute |
| Normal **build** | Yes under standard Java plugin config | Yes unless UP-TO-DATE/NO-SOURCE/skipped | Yes when test sources exist |

If you want to **skip running tests while keeping test compilation**—closer in spirit to Maven **-DskipTests**—one option is **placing an onlyIf condition on the test task** instead of excluding the task with -x. Even then, check task dependencies and inputs/outputs, and note that projects with no test sources have nothing to compile.

### 8.2. Example Condition Using a Project Property

In **build.gradle** (Groovy DSL), supplementary configuration:

~~~groovy
tasks.named('test') {
    onlyIf("skipUnitTests property is absent") {
        !providers.gradleProperty('skipUnitTests').isPresent()
    }
}
~~~

This is a **snippet added to a project that already has the Java plugin/test task**, not a standalone build.gradle. Passing **-PskipUnitTests**:

~~~bash
./gradlew clean build -PskipUnitTests
~~~

keeps test in the Gradle task graph while **skipping test actions** because the predicate evaluates to false. Task dependencies of test (such as compileTestJava) **can still run** normally; inspect with **--dry-run** or real logs.

When **-PskipUnitTests** is omitted, the condition is true and test runs normally when inputs are present. The advantage is making the skip condition explicit and clearly named rather than an arbitrary exclusion flag. Even so, **never skip unit tests by default in release CI**.

A simpler but much less flexible option is:

~~~groovy
tasks.named('test') {
    enabled = false
}
~~~

This disables the test task unconditionally in that configuration; if committed to mainline without a guard, every subsequent build silently skips tests—a major risk. Prefer conditional configurations controlled by CI policy.

### 8.3. Gradle Does Not Understand Maven Properties by Default

~~~bash
./gradlew build -DskipTests=true
./gradlew build -Dmaven.test.skip=true
~~~

Here, both **-D** flags merely set **JVM system properties for Gradle**; they do not trigger Surefire or Maven Compiler Plugin skipping. A Gradle build reacts to them only if its build script or a plugin **explicitly reads those properties**. Never apply Maven flags to Gradle assuming tests were skipped.

Conversely, **-x test** is not valid syntax for Maven to exclude a test phase: **./mvnw package -x test** is not a Maven equivalent of Gradle.

## 9. Runnable Example: A Spring Boot Project with a Unit Test

We use the same Java sources for both **Maven and Gradle** builds. Pick only one build tool and its corresponding config in your project. The lesson uses Java 17+, Spring Boot 3.5.16, and JUnit Jupiter via Spring Boot starter-test; this example tests a simple addition so the difference between **compiling tests**, **running tests**, and **packaging** stands out clearly.

### 9.1. Source Structure

~~~text
skip-demo/
├── pom.xml                  (Maven only)
│   or build.gradle          (Gradle only)
├── settings.gradle          (Gradle only)
├── mvnw / mvnw.cmd / .mvn/wrapper/...       (Maven Wrapper)
├── gradlew / gradlew.bat / gradle/wrapper/... (Gradle Wrapper)
└── src/
    ├── main/java/com/example/skipdemo/
    │   ├── SkipDemoApplication.java
    │   └── Calculator.java
    └── test/java/com/example/skipdemo/
        └── CalculatorTest.java
~~~

Wrappers must be generated by Spring Initializr or the build tool's wrapper command; creating pom.xml/build.gradle manually does not generate wrapper scripts. Use Maven/Gradle/Java versions supported by the chosen Spring Boot release.

### 9.2. Main Java Code

File **src/main/java/com/example/skipdemo/Calculator.java**:

~~~java
package com.example.skipdemo;

public class Calculator {
    public int add(int a, int b) {
        return a + b;
    }
}
~~~

File **src/main/java/com/example/skipdemo/SkipDemoApplication.java**:

~~~java
package com.example.skipdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class SkipDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(SkipDemoApplication.class, args);
    }
}
~~~

The application omits starter-web and controllers, so **do not expect an HTTP server on port 8080**. When running **java -jar**, the Spring context starts and the app exits normally once there are no non-daemon workers. Startup logs vary by machine and version.

### 9.3. JUnit Test Code

File **src/test/java/com/example/skipdemo/CalculatorTest.java**:

~~~java
package com.example.skipdemo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class CalculatorTest {

    @Test
    void additionWorks() {
        Calculator calculator = new Calculator();
        assertEquals(5, calculator.add(2, 3));
    }
}
~~~

This is a valid test that **compiles** and **PASSES** under JUnit Jupiter. Because assertEquals compares 5 with 2 + 3 = 5, no external dependency affects the outcome.

### 9.4. Option A — Complete Maven pom.xml

File **pom.xml**:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>skip-demo</artifactId>
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
~~~

This is a simple project with no custom Surefire overrides. Spring Boot parent manages compatible versions for common dependencies and plugins; **spring-boot-starter-test** adds JUnit Jupiter to the test classpath. In a standard Maven project, testCompile and Surefire test goal bind to their respective lifecycle phases.

Run on Linux/macOS (Windows uses **mvnw.cmd**):

~~~bash
./mvnw --version
./mvnw clean verify
./mvnw clean package -DskipTests
./mvnw clean package -Dmaven.test.skip=true
~~~

The last three lines are **three independent builds for comparison**, not steps to run sequentially in a production pipeline. Running **clean** before each avoids inspecting leftover test classes/reports and misreading previous results.

### 9.5. Option B — Complete Gradle build.gradle

File **settings.gradle**:

~~~groovy
rootProject.name = 'skip-demo'
~~~

File **build.gradle** (Groovy DSL):

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
~~~

Spring Boot Gradle Plugin creates the executable archive via **bootJar**, the Spring dependency-management plugin imports the matching BOM, and the **java** plugin creates the **test** task. Configuring JUnit Platform allows Gradle to discover JUnit Jupiter tests.

With Gradle Wrapper 8.14 (compatible with Java 17 and Boot 3.5.x), run on Linux/macOS (Windows uses **gradlew.bat**):

~~~bash
./gradlew --version
./gradlew clean build
./gradlew clean build -x test
./gradlew clean build -x test --dry-run
~~~

These commands illustrate alternative invocations. The last command prints only the task plan without running compile/test/package actions, so it cannot be treated as evidence that a new artifact was built.

### 9.6. Expected Outcomes of Each Run

With a valid **CalculatorTest**, Maven **clean verify** and Gradle **clean build** run the test and PASS. The test-skipping invocations can also succeed, **but do not prove assertions ran**.

Default build outputs:

| Tool | Main classes | Test classes when compiled | Test reports when tests run | Executable Boot JAR |
| --- | --- | --- | --- | --- |
| Maven | target/classes | target/test-classes | target/surefire-reports | target/skip-demo-1.0.0.jar |
| Gradle | build/classes/java/main | build/classes/java/test | build/test-results/test, build/reports/tests/test | build/libs/skip-demo-1.0.0.jar |

**Do not assume** test reports exist when skipping tests, especially after **clean** clears outputs. With Gradle **-x test**, **build/classes/java/test** is normally not created during a clean build of a simple project because test compilation has no remaining consumer. Without clean, stale outputs may persist; seeing a file on disk does not prove it came from the current build.

To run the JAR:

~~~bash
java -jar target/skip-demo-1.0.0.jar
~~~

or:

~~~bash
java -jar build/libs/skip-demo-1.0.0.jar
~~~

Use only the command matching your chosen build tool. Successful startup proves the artifact can launch in that environment, **not that unit tests ran**.

## 10. Experiment Distinguishing Compile-Test and Run-Test

To observe the difference firsthand, perform this experiment in a **copy/dev branch**, never deliberately breaking your team's main source. The two scenarios below use **test code as an experiment**; they are not test designs meant for production.

### 10.1. Experiment A — Tests Compile, Assertion FAILS

In **CalculatorTest.java**, change:

~~~java
assertEquals(5, calculator.add(2, 3));
~~~

to:

~~~java
assertEquals(6, calculator.add(2, 3));
~~~

The Java code still compiles validly, yet JUnit detects **expected 6, actual 5** at runtime. With the demo configuration:

| Command | Expected result |
| --- | --- |
| **./mvnw clean verify** | FAILS in Surefire/JUnit due to wrong assertion |
| **./mvnw clean package -DskipTests** | Tests still compile; assertions skipped; build can PASS |
| **./mvnw clean package -Dmaven.test.skip=true** | No test compilation/execution; build can PASS |
| **./gradlew clean build** | FAILS in test task due to wrong assertion |
| **./gradlew clean build -x test** | Test task excluded; build can PASS |

"PASS" in the skip rows only means **the build did not run this test**, **not** that addition satisfied the test. After the experiment, revert the assertion to the right value.

### 10.2. Experiment B — Test Source Fails to Compile

Unlike Experiment A, add an intentional type error inside the test method:

~~~java
int invalid = "not-an-int";
~~~

This is an **intentionally broken test snippet** to revert after observing. The compiler reports that String cannot be converted to int. Typical results in a clean build:

| Command | Expected result |
| --- | --- |
| **./mvnw clean package** | FAILS at testCompile |
| **./mvnw clean package -DskipTests** | **Still FAILS** at testCompile; skipTests does not skip test compilation |
| **./mvnw clean package -Dmaven.test.skip=true** | Test compilation skipped; main package can PASS |
| **./gradlew clean build** | FAILS at compileTestJava |
| **./gradlew clean build -x test** | In standard Java plugin, compileTestJava is also omitted; main build can PASS |
| **./gradlew clean testClasses -x test** | **FAILS** at compileTestJava because testClasses was still explicitly requested |

The last row is especially instructive: even with **-x test**, explicitly requesting **testClasses** forces Gradle to compile test sources. This proves Gradle decides via the **task graph**, not a global "test compilation disabled" boolean.

**Note:** these outcomes are expected for the demo project and compatible plugin versions, not measured logs from a specific run. Custom plugins, generated test sources, module dependencies, profiles, caches, or task graphs can alter results.

## 11. "Skip", "Run a Subset", and "Ignore Test Failures" Are Three Different Things

### 11.1. Running a Subset Instead of Skipping Everything

When fixing a bug, **running the relevant tests** is usually better than skipping all tests:

Maven Surefire:

~~~bash
./mvnw test -Dtest=CalculatorTest
./mvnw test -Dtest=CalculatorTest#additionWorks
~~~

Gradle Java/JUnit Platform:

~~~bash
./gradlew test --tests com.example.skipdemo.CalculatorTest
./gradlew test --tests 'com.example.skipdemo.CalculatorTest.additionWorks'
~~~

These commands **actually execute the selected tests** (when the class/method exists in the project) and are not skips. They are great for rapid development loops, followed by running the full suite in CI.

### 11.2. Letting Tests FAIL While Keeping the Build Green Is a Different Policy

Maven Surefire has **maven.test.failure.ignore**, and the Gradle Test task has **ignoreFailures**. These are not **skip**:

- Tests **still execute** and detect failures.
- The plugin is configured **not to fail the overall build** when tests fail.
- The pipeline may report build success even though reports show failing tests.

Do not use this to legitimize release builds. If failures are temporarily tolerated, document it clearly in CI/reports and set an expiration criterion. **Never confuse `BUILD SUCCESSFUL` with "0 test failures"** when failure-ignoring flags are active.

### 11.3. UP-TO-DATE / FROM-CACHE / NO-SOURCE Are Also Not Intentional Skips

In Gradle logs:
- **UP-TO-DATE**: task did not need to re-run because Gradle considers inputs/outputs unchanged.
- **FROM-CACHE**: Gradle restored matching outputs from the build cache.
- **NO-SOURCE**: task has no configured source files.
- **SKIPPED**: task actions were skipped due to a condition, `enabled = false`, or another reason.
- **-x test**: the `test` task was excluded from selection and normally **does not appear** in the task list.

Each carries a distinct meaning. A cached test task may represent verified results for known inputs, whereas **-x test** actively removes the task. When investigating why tests did not run, inspect CLI flags, task conditions, inputs, and task outcomes.

## 12. Real-World Spring Boot Scenarios

### Scenario A — Quickly Testing Executable JAR Packaging

With Maven, if you still want to verify test sources compile:

~~~bash
./mvnw clean package -DskipTests
~~~

With Gradle, if you only want to test **bootJar** without running the full validation suite:

~~~bash
./gradlew clean bootJar
~~~

**bootJar normally does not depend on the test task**, so **-x test** is usually unnecessary. However, if a custom build script makes bootJar depend on test, check the graph. Building a JAR without running tests must still be noted and followed by a full test pipeline.

### Scenario B — Test Sources Have a Compile Error, Yet You Need to Inspect the Main Artifact

Maven **-DskipTests** will not bypass a test compilation failure. If you truly need a temporary JAR for diagnostics:

~~~bash
./mvnw clean package -Dmaven.test.skip=true
~~~

Use this strictly as a local exception; afterward fix the compilation error and re-run **./mvnw clean verify**. Gradle can run **bootJar** directly or exclude the test task during build, while checking whether other plugins/tasks still require test outputs.

### Scenario C — Run Only Unit Tests While Integration Test Environment Is Unavailable

A Maven project with Failsafe bound to integration-test/verify phases can run:

~~~bash
./mvnw verify -DskipITs=true
~~~

This flag applies only to Failsafe when configured; if the project does not use Failsafe, it will not create or disable integration tests from another tool. In Gradle, integration tests are usually a **custom Test task** or separate test suite; `-x test` does not equal `-x integrationTest`. Check **./gradlew tasks --all** and the task graph, then exclude/condition the appropriate suite.

### Scenario D — CI Builds Still Need Test Verification

A pipeline should explicitly run unit tests and integration tests before releasing. You can separate:
1. **Build/compile/assemble** to catch compile/packaging errors early.
2. **Unit tests** on every change.
3. **Integration/contract tests** in environments providing required dependencies.
4. **Release gate** permitting publish/deploy only from artifacts and commits that passed mandatory checks.

Never let a "fast build" job carrying skip flags be reused automatically as a release job. Job names, status checks, and logs must state **which tests actually ran**, not merely **build success**.

## 13. Multi-Module Builds: Flags and Tasks Must Be Evaluated Separately

### 13.1. Maven Reactor

In a Maven multi-module build, **-DskipTests** is passed across modules participating in the reactor, yet **its exact effect depends on each module's plugin executions and POM configuration**. A module without Java test sources, a **pom**-packaged module, or a module using custom plugins will not behave like a standard Java application module.

For example, building only the `api` module and its required dependencies:

~~~bash
./mvnw -pl api -am package -DskipTests
~~~

**-pl** selects the project, and **-am** adds upstream projects it depends on in the reactor. Surefire in the involved modules honors `skipTests` under standard config. Do not assume this ran tests in unselected modules, or that Failsafe 3.6+ skips ITs solely because `skipTests` was passed.

### 13.2. Gradle Multi-Project

To inspect task paths:

~~~bash
./gradlew tasks --all
./gradlew :api:build --dry-run
./gradlew :api:build -x :api:test --dry-run
~~~

Assuming a subproject named **api** exists, **-x :api:test** specifically targets the `test` task in `:api`; other Test tasks such as **:worker:integrationTest** do not vanish automatically. Depending on cross-module dependencies, required tasks in other subprojects can still run.

If you ever need to omit **all Test tasks** for a special purpose, avoid chaining arbitrary `-x` task names; design clear task lifecycles/groups and inspect the graph. Some plugins provide non-Test verification tasks: static checks, code-generation validation, linting, vulnerability scanning. Skipping tests does not disable all checks.

## 14. Checking Logs and Reports Before Concluding Tests Ran

### 14.1. Maven

In a standard Java Maven project:

~~~text
target/classes/           # main classes
target/test-classes/      # test classes, if compiled
target/surefire-reports/  # Surefire reports when unit tests ran
target/failsafe-reports/  # Failsafe reports if IT plugin ran
~~~

Verify goal order in the output:
- **compiler:compile**
- **compiler:testCompile**
- **surefire:test**
- **failsafe:integration-test** / **failsafe:verify** (if configured)
- **jar:jar**, **spring-boot:repackage** (for Maven Boot applications)

Reports can remain from a previous build if `clean` was omitted. After a clean build with **-Dmaven.test.skip=true**, missing `test-classes` is expected; with **-DskipTests**, `test-classes` usually exists without fresh test reports. **Never** claim tests PASSED just because packaging succeeded.

### 14.2. Gradle

In a typical Java Gradle project:

~~~text
build/classes/java/main/
build/classes/java/test/
build/test-results/test/
build/reports/tests/test/
build/libs/
~~~

Check the **:test** task output and status. With Gradle `-x test`, the `test` task is absent from the execution graph of that invocation. If the task has status **SKIPPED** due to **onlyIf** or `enabled = false`, it appears in the graph without executing actions. If it shows **UP-TO-DATE** or **FROM-CACHE**, inspect inputs/cache and CI policy.

For release pipelines, verify **test reports belonging to the current commit/build ID**, not merely that a report folder exists.

## 15. Decision Table: Which Command for Which Goal?

| Need | Maven | Gradle | Trade-off to accept |
| --- | --- | --- | --- |
| Run unit tests and package | **./mvnw clean verify** | **./gradlew clean build** | Takes longer; actually verifies tests |
| Package while still compiling tests | **./mvnw clean package -DskipTests** | Configure **test.onlyIf** to skip actions when needed | Does not prove assertions PASS |
| Package and skip test compilation too | **./mvnw clean package -Dmaven.test.skip=true** | **./gradlew clean build -x test** in standard layout | Can hide test compilation errors |
| Build executable JAR only for smoke testing | **./mvnw package** (usually runs tests unless configured otherwise) | **./gradlew bootJar** | Do not infer test coverage from task name |
| Run a specific test | **./mvnw test -Dtest=CalculatorTest** | **./gradlew test --tests ...** | Only a subset is verified |
| Skip Failsafe integration tests while keeping unit tests | **./mvnw verify -DskipITs** | Exclude/condition the custom **integrationTest** task | Must check plugin versions and task graph |
| Preview task list without running task actions | Maven: effective POM/lifecycle/plugin help | **./gradlew build --dry-run** | It is a plan, not test evidence |

In this table, **-x test** must not be treated as an exact equivalent of **maven.test.skip**: one alters the **Gradle task graph**, while the other is a **Maven property** honored by specific plugins. Both can yield similar effects in a standard Java project, yet diverge on custom tasks, integration tests, and source sets.

## 16. Common Pitfalls and Misconceptions

| Symptom | Common cause | How to verify |
| --- | --- | --- |
| **-DskipTests** still FAILS in **testCompile** | Broken test source; `skipTests` only skips Surefire execution | Maven log, test compiler errors |
| **-Dmaven.test.skip=true** PASSES while test source fails to compile | Test compilation was skipped | Remove the flag and run **./mvnw clean test** |
| **./gradlew build -x test** PASSES despite failing assertions | The `test` task was excluded from the graph | Run **./gradlew test** and check reports |
| **./gradlew build -x test** still runs compileTestJava | Another task depends on `compileTestJava` | Compare **--dry-run** and inspect the graph |
| **-DskipTests** passed, yet integration tests still run | Failsafe 3.6+ does not bind CLI `skipTests`; or another IT plugin | Check Failsafe version, config, and logs |
| **-DskipITs** passed, yet unit tests still run | Intended behavior: skips Failsafe ITs, not Surefire unit tests | Inspect surefire-reports/failsafe-reports |
| **-x test** passed, yet integrationTest still runs | `integrationTest` is a separate task | Check **tasks --all** and task paths |
| Gradle logs **SKIPPED** | Task skipped via `onlyIf`/disabled/`NO-SOURCE` or `--dry-run` | Check task outcome and CLI flags |
| Reports exist even when tests were skipped | Stale reports from missing `clean` or generated by another task | Check timestamps, build IDs, and task logs |
| Running **bootJar** executes no unit tests | `bootJar` does not depend on `test` by default | Invoke **build** or **test** explicitly |
| Tests PASS, yet build FAILS | Another plugin (packaging/quality/integration test) failed | Check the exact failing task/goal |
| Maven **mvn test -DskipTests=false** still runs zero tests | Undiscovered tests, custom config, absent tests, or profile/plugin override | Inspect Maven Surefire config and test discovery |
| Green CI after enabling `ignoreFailures` | Tests fail without failing the build | Read reports rather than relying only on exit code |

**Troubleshooting principle:** identify whether the failure sits in **compile main, compile test, execute unit tests, execute integration tests, package, or another verification step**. Use skip flags only after knowing exactly what is being bypassed; never use skipping as a long-term fix for a real test failure.

## 17. Checklist for Safe CI and Release Practices

- [ ] Identify the tool: Maven or Gradle; never mix CLI flags between them.
- [ ] In Maven, distinguish **-DskipTests** (skips Surefire execution) from **-Dmaven.test.skip=true** (skips test compilation and Surefire/Failsafe execution).
- [ ] If using Failsafe, check its version; **3.6+** uses **-DskipITs** to skip integration tests, while **-DskipTests** affects only Surefire by default.
- [ ] In Gradle, understand **-x test** removes `test` and test-only dependencies from the graph without automatically excluding custom Test tasks.
- [ ] When you need tests to compile without running, consider conditional **onlyIf** and inspect the graph; avoid permanently disabling tests.
- [ ] Never treat `BUILD SUCCESSFUL` or an output JAR as proof tests PASSED if skip flags were present.
- [ ] Distinguish compiled test outputs, fresh test reports, and stale/cached outputs.
- [ ] Release CI enforces mandatory verification, archives test reports, and audits changes to skip flags.
- [ ] After debugging with a skip flag, revert it and re-run appropriate **unit + integration tests** before releasing.
- [ ] When speeding up local dev loops, prefer **running a test subset**, incremental builds, or test caching instead of skipping all tests.

## 18. Quick Self-Check

**Question 1.** Unit test code has a syntax error. Why can **./mvnw package -DskipTests** still FAIL?

**Answer:** Because Compiler Plugin still compiles test sources in the `test-compile` phase; `skipTests` only tells Surefire not to execute tests. To skip test compilation too (only with valid justification), use **-Dmaven.test.skip=true**.

**Question 2.** A **./gradlew clean build -x test** run PASSES. Does that mean `compileTestJava` ran cleanly?

**Answer:** No. With the standard Java plugin, `compileTestJava` may be absent from the graph when `test` is excluded. Check task outputs, or run **./gradlew testClasses** / **./gradlew test** to verify test sources.

**Question 3.** With Failsafe 3.6+, does **-DskipTests** definitely skip integration tests?

**Answer:** No. Since 3.6.0, Failsafe no longer binds its `skipTests` parameter to the CLI `skipTests` property. Use **-DskipITs=true** to skip Failsafe ITs; check actual plugin version/config.

**Question 4.** To skip test execution in Gradle while still having the compiler check test sources, what should you consider?

**Answer:** A **test.onlyIf** condition can skip test actions while leaving dependencies like `compileTestJava` in the graph. Verify the graph in your specific project. **-x test** normally excludes test-only dependency tasks too.

**Question 5.** Should **-Dmaven.test.skip=true** be kept in release CI to speed up builds?

**Answer:** No: release CI loses verification that test sources compile and that unit/integration tests pass. Allow exceptions only with documented justification and block releases until mandatory tests pass.

**Question 6.** If Gradle **bootJar** builds an executable JAR successfully, did unit tests definitely run?

**Answer:** No. **bootJar** is normally a packaging task and does not depend on `test`; run **test**, **check**, or **build** per project verification policy.

**Question 7.** Are Maven **-DskipTests** and Gradle **-x test** strictly equivalent?

**Answer:** No. Maven `skipTests` is a property read by Surefire that normally still compiles tests; Gradle `-x` removes the `test` task and its exclusive dependencies from the task graph. Inspect each plugin/task and every test suite.

## 19. Conclusion and Reference Documentation

Three easy-to-remember summaries:

~~~text
MAVEN -DskipTests
    -> compiles main: yes
    -> compiles test: yes
    -> runs Surefire tests: no

MAVEN -Dmaven.test.skip=true
    -> compiles main: yes
    -> compiles test via Compiler Plugin: no
    -> runs Surefire/Failsafe tests: no

GRADLE build -x test
    -> removes test task from graph
    -> test-only dependencies may also be excluded
    -> other tasks (e.g., integrationTest) are not excluded automatically
~~~

These lines describe standard tool behavior, not a rule covering every plugin. In Spring Boot, the most important rule is knowing **what you are actually proving**: an artifact can be packaged successfully even when tests did not run, and **successful packaging does not equal successful testing**.

### Official Documentation

- Apache Maven Surefire — Skipping Tests: https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html
- Apache Maven Surefire — Goal Test and skipTests property: https://maven.apache.org/surefire/maven-surefire-plugin/test-mojo.html
- Apache Maven Failsafe — Skipping Tests (including 3.6.0 change): https://maven.apache.org/surefire/maven-failsafe-plugin/examples/skipping-tests.html
- Apache Maven Failsafe — integration-test goal parameters: https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html
- Apache Maven Compiler Plugin — testCompile / maven.test.skip: https://maven.apache.org/plugins/maven-compiler-plugin/testCompile-mojo.html
- Apache Maven — Introduction to Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Gradle — Testing in Java and JVM Projects (Skipping the Tests): https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Controlling Task Execution: https://docs.gradle.org/current/userguide/controlling_task_execution.html
- Gradle — Command-Line Interface (-x / --exclude-task): https://docs.gradle.org/current/userguide/command_line_interface.html
- Gradle — Java Plugin Task Dependencies: https://docs.gradle.org/current/userguide/java_plugin.html
- Spring Boot 3.5 — Maven Plugin: https://docs.spring.io/spring-boot/3.5/maven-plugin/
- Spring Boot 3.5 — Gradle Plugin: https://docs.spring.io/spring-boot/3.5/gradle-plugin/
