# Relationship Between `classes`, `test`, `check`, `assemble`, and `build` in Gradle/Spring Boot

## 1. The big picture: five tasks are five distinct levels of responsibility

When working with **Spring Boot Build Tooling Packaging**, understanding these Gradle commands helps you answer accurately: has the code compiled, have tests run, has quality been verified, has the deployable package been created, and what does the `build` command actually guarantee?

These are **Gradle tasks** (specifically when applying the `java` plugin), not five sequential Maven phases. Gradle builds a *task dependency graph* from plugins and build scripts, then executes the necessary tasks. Therefore, there is no rule saying "you must manually run `classes`, then `test`, then `check`, then `assemble`, then `build`"; invoking one task pulls in the tasks it depends on.

| Task | Question it answers | Primary output | What must **not** be assumed by default |
| --- | --- | --- | --- |
| `classes` | Are main Java sources and resources ready? | Main `.class` files and processed resources in `build/classes`, `build/resources` (by default). | Does not prove tests pass or a JAR was created. |
| `test` | Do the default tests run and pass? | Test compilation, execution of tests discovered by configuration, test reports. | Does not automatically create an executable JAR, nor automatically invoke all integration test suites. |
| `check` | Have the checks wired into the verification cycle passed? | Aggregates `test` and verification tasks wired in by plugins/project. | Not an automatic scanner for every kind of defect; does not require packaging. |
| `assemble` | Have the configured distributable artifacts been packaged? | `jar`/`war`, and `bootJar`/`bootWar` when the Spring Boot plugin is configured. | Does not run `test` by default, so artifacts can be created even when test logic is broken. |
| `build` | Have both the packaging branch and verification branch succeeded? | Depends on **`assemble` and `check`** along with tasks wired into them. | Does not by itself prove the application runs properly in a deployment environment. |

**Core distinction:** `assemble` targets *artifacts*, `check` targets *verification*, and `build` combines both. `classes` and `test` are specific links underneath.

### Gradle's "lifecycle" does not mean linear order

In the Java plugin, the structural rules are:

- `classes` depends on tasks preparing main outputs (usually including `compileJava` and `processResources`).
- `test` depends on preparing test classes and classpath; it requires the project's main output per relationships configured by Gradle.
- `check` depends on `test`; plugins or additional configurations may add more checks.
- `assemble` depends on `jar` in the Java plugin; when the Spring Boot plugin configures a Java application, `assemble` also depends on `bootJar`.
- `build` depends on **both `check` and `assemble`**.

The figure below is a **simplified conceptual diagram** for a Spring Boot application applying the Java plugin. An arrow `A --> B` means "A requires B"; the diagram omits many internal tasks and optional plugins:

~~~mermaid
flowchart TD
    B["build"] --> C["check"]
    B --> A["assemble"]
    C --> T["test"]
    T --> TC["testClasses"]
    TC --> CT["compileTestJava"]
    TC --> PTR["processTestResources"]
    CT -. "uses main output" .-> CL["classes"]
    A --> J["jar (plain archive)"]
    A --> BJ["bootJar (Spring Boot executable)"]
    J --> CL
    BJ --> CL
    CL --> CJ["compileJava"]
    CL --> PR["processResources"]
~~~

Actual tasks may be added or removed depending on plugin versions, languages (Kotlin/Groovy), source sets, disabled tasks, and build scripts. **Dependencies do not force `check` to run before `assemble` or vice versa**: the two branches are prerequisites for `build` to finish. Gradle selects a valid execution schedule based on the graph; do not interpret sample log ordering as a fixed contract.

## 2. `classes`: preparing production code and resources

With the Java plugin and default `main` source set:

- `compileJava` compiles `src/main/java` into `.class` files.
- `processResources` processes/copies `src/main/resources` into the resource output directory.
- `classes` is a **lifecycle task aggregating main output preparation**; usually it produces no extra files of its own.
- Additional tasks (annotation processing, code generation, Kotlin compilation...) can be wired into the source set depending on plugins.

Example:

~~~text
src/main/java/com/example/lifecycle/LifecycleApplication.java
src/main/resources/application.properties
       |
       +--> compileJava ------> build/classes/java/main/...
       |
       +--> processResources -> build/resources/main/...
                              |
                           classes
~~~

Ellipses represent specific files determined by the project. Being able to compile Java classes **does not prove** the Spring application starts, runtime dependencies are complete, or tests have run. Conversely, `./gradlew classes` is useful when fixing compile errors and wanting fast feedback without packaging/testing yet.

~~~bash
# macOS/Linux, inside the Gradle project root directory
./gradlew classes

# Windows
gradlew.bat classes
~~~

When successful, you can inspect the output directories matching the source set in use. If `processResources NO-SOURCE` occurs, that can be a valid result when there are no resources; if the project is supposed to have `application.yml` or templates, investigate the path or source set configuration.

## 3. `test`: running tests, not identical to `classes`

The Java plugin creates the `test` source set and common tasks:

1. `compileTestJava` compiles `src/test/java`, using the test compile classpath and main output.
2. `processTestResources` prepares `src/test/resources`.
3. `testClasses` aggregates the outputs needed to run tests.
4. `test` is a `Test`-type task that executes tests recognized by configuration/engines using the test runtime classpath, then writes results.

Typical dependency order:

~~~text
main compilation/resources
          |
     test compilation/resources
          |
      testClasses
          |
         test
          |
 test report / test result
~~~

For `test` to actually evaluate behavior, **tests must be discovered and the corresponding engine configured**. For instance, JUnit Jupiter requires test dependencies and `useJUnitPlatform()` in many Gradle Java projects. A `test` task returning success with status `NO-SOURCE`, `SKIPPED`, or zero discovered tests is not sufficient evidence of "thoroughly tested".

~~~bash
./gradlew test

# Run only a single test class when fast feedback is needed
./gradlew test --tests com.example.lifecycle.LifecycleApplicationTest
~~~

Java plugin reports are usually at:

~~~text
build/test-results/test/     # test result data (usually XML)
build/reports/tests/test/    # HTML report, if corresponding output is enabled
~~~

Paths can change when a project configures different test tasks/source sets. `test` by default does not guarantee that integration tests against a DB, message broker, Docker, or external systems have run; those may live in a separate `integrationTest` task and must be wired into the appropriate gate.

**Understanding test results:** Gradle may print `UP-TO-DATE` or `FROM-CACHE` if valid results are reused; that is different from "just re-executed every test". When investigating failures, you can explicitly force re-execution with `./gradlew test --rerun-tasks`, without needing to disable caching on every build.

## 4. `check`: the aggregation point for required verifications

`check` is a **lifecycle task** provided by the Base plugin; the Java plugin wires `test` into `check`. When invoking:

~~~bash
./gradlew check
~~~

Gradle selects the verification tasks declared as dependencies, typically including `test`. If the project applies quality-check plugins or adds custom checks, they **are only guaranteed to appear in `check` when actually wired into the graph**.

The Groovy DSL example below is a configuration snippet **only to be used when the project has already registered an `integrationTest` task**:

~~~groovy
// build.gradle — snippet added after the integrationTest task already exists
tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

This snippet **does not create** the `integrationTest` task; if it is not yet registered, the configuration will be invalid. Creating source sets, dependencies, and the integration test runtime setup must be done in the appropriate place before wiring the gate. The same principle applies to Checkstyle, SpotBugs, coverage verification, license scans, or contract tests: do not assume "check will automatically run everything" just because a plugin appears in the build file.

### `dependsOn`, `mustRunAfter`, and `shouldRunAfter` are different

- `dependsOn('integrationTest')`: requires the target task **to be included** in the graph when running `check`.
- `mustRunAfter('test')`: if *both tasks are already selected*, enforces order; **does not pull the other task into the graph**.
- `shouldRunAfter('test')`: soft ordering preference when both tasks run; not equivalent to a mandatory dependency.

Ordering rules alone are not enough to establish a quality gate. If you want `build` to fail when integration tests fail, wire that task into `check` with a real dependency, confirm it has tests, and assert results as expected.

An aggregator task like `check` may not write any file of its own. **Proper evidence** is the results of the underlying verification tasks, test counts, reports, and specific failures; not just a `:check` line.

## 5. `assemble`: gathering distributable deliverables

In the plain Java plugin, `assemble` is wired to `jar` and archive tasks added by other plugins. `jar` usually packages **main classes/resources** into a library/standard JAR. This JAR does not bundle all runtime dependencies and may not run standalone with `java -jar`.

With the Spring Boot Gradle plugin:

- When both the Spring Boot plugin and `java` plugin are applied, there is normally a `bootJar` task that creates an **executable Spring Boot JAR** including the loader structure and runtime dependencies.
- `assemble` automatically depends on `bootJar`; therefore `./gradlew assemble` and `./gradlew build` pull in the Boot JAR packaging task (unless customized/disabled).
- If the `war` plugin is applied for a WAR application, the Spring Boot plugin provides `bootWar` and wires it into `assemble`.
- Normally `jar` still exists and produces a "plain" archive with classifier `plain`, while `bootJar` produces the executable one. Plugins/build scripts can change the classifier, name, or disable the plain JAR.

~~~bash
# Package according to artifacts wired into assemble
./gradlew assemble

# Request only the executable Spring Boot JAR
./gradlew bootJar
~~~

Outputs are normally in `build/libs/`. To tell archives apart, look at the **actual filename and actual contents**:

~~~bash
# Replace artifact name with your project's actual build/libs result
jar tf build/libs/lifecycle-demo-0.0.1-SNAPSHOT.jar
~~~

For a typical executable Spring Boot JAR, you will see `BOOT-INF/classes/`, `BOOT-INF/lib/`, and `META-INF/MANIFEST.MF`. Check the manifest/loader and test `java -jar` when you need to verify it actually runs. Do not mistakenly pick the `*-plain.jar` file to deploy as an executable application.

**Common pitfall:** `assemble` does not depend on `test` by default. A build script can customize this, but **it must not be assumed**. If you edit a test so an assertion fails, `./gradlew assemble` can still succeed as long as production code compiles/packages normally. Thus "having a JAR" does not mean "passed verification".

## 6. `build`: the union of `check` and `assemble`, not magic

The Base/Java plugin sets up:

~~~text
build
  +-- check
  |     +-- test
  |     +-- other wired verification tasks
  |
  +-- assemble
        +-- jar
        +-- bootJar (when Spring Boot + Java plugin are configured)
~~~

When invoking `./gradlew build`, Gradle resolves and executes all necessary dependencies of both branches. The build passes when no required task fails under the chosen execution policy. Key lessons:

1. `build` is **not equivalent** to manually chaining `classes test check assemble build`; overlapping tasks are scheduled and managed by the graph.
2. `build` does not automatically add integration tests, security scans, smoke tests, or deployment. To include them as gates, declare explicit dependencies or pipeline steps.
3. `build` does not force `assemble` to run after all of `check`. If tests fail, an archive file might still appear because the packaging branch ran earlier; **the build verdict must be based on the status of the entire invocation**, not on file existence.
4. Builds are normally **incremental**: Gradle marks tasks `UP-TO-DATE` or uses build cache when inputs/outputs match. `clean` is a separate task, **not automatically part of `build`**.
5. Running `build -x test` or setting `test.enabled` to false can make the command green without running tests; passing quality must be based on proper gates, not just `BUILD SUCCESSFUL`.

~~~bash
# Standard verification, running incrementally
./gradlew build

# Delete old outputs then run the build chain in the same invocation
./gradlew clean build

# Show planned tasks without executing them
./gradlew build --dry-run
~~~

**`--dry-run` is a graph-reading tool, not a test.** In dry-run output you may see tasks labeled `SKIPPED` because it is simulating; do not mistake that for actual test results. `clean build` is useful when old outputs must be cleared for diagnostics, but it does not prove a build is completely network/cache-independent or byte-for-byte "reproducible" if dependencies are uncontrolled.

### Command selection table by objective

| You want to... | Prefer invoking | Why |
| --- | --- | --- |
| Check main code compilation errors fast | `classes` | Avoids unnecessary tests/packaging. |
| Verify unit tests being edited | `test`, optionally `--tests` | Produces test reports; no archive needed. |
| Run all registered verifications | `check` | Includes gates wired into check. |
| Create an executable Spring Boot JAR to test runtime | `bootJar`, or `assemble` | Focuses on packaging; remember to test separately if needed. |
| Create artifacts **and** run project-level verification | `build` | Pulls in both `assemble` + `check` branches. |
| Check if the build invokes the right tasks | `build --dry-run` and `tasks --all` | Reveals real tasks/differences in plugins and config. |

## 7. Runnable practice: tracking the five tasks on a small app

The following example uses **Gradle Groovy DSL, Java 17+, Spring Boot 3.3.13**. This is a standalone project; if you already have a project, use the plugin/JDK versions specified by that project. The goal of this exercise is to observe the task graph, not to require every project to switch to the example versions.

Structure:

~~~text
lifecycle-demo/
  settings.gradle
  build.gradle
  gradlew                  # generated by gradle wrapper and committed to repo
  gradlew.bat
  gradle/wrapper/...
  src/main/java/com/example/lifecycle/LifecycleApplication.java
  src/test/java/com/example/lifecycle/LifecycleApplicationTest.java
~~~

### 7.1. Build definition

`settings.gradle`:

~~~groovy
rootProject.name = 'lifecycle-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

The Java plugin provides `classes`/`test` and wires `jar` into `assemble`, `test` into `check`. The Spring Boot plugin provides `bootJar` and wires it into `assemble`. Dependency management coordinates with the Spring Boot plugin to pull aligned dependency versions; `starter-web` provides the web runtime and `starter-test` provides test tooling. You need a Gradle Wrapper compatible with the plugin version and JDK 17 installed or supplied via toolchain; Wrapper files should be generated/stored in the project according to team conventions.

`src/main/java/com/example/lifecycle/LifecycleApplication.java`:

~~~java
package com.example.lifecycle;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class LifecycleApplication {
    public static void main(String[] args) {
        SpringApplication.run(LifecycleApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

`src/test/java/com/example/lifecycle/LifecycleApplicationTest.java`:

~~~java
package com.example.lifecycle;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class LifecycleApplicationTest {
    @Test
    void pingMethodReturnsExpectedText() {
        assertEquals("pong", new LifecycleApplication().ping());
    }
}
~~~

The test above is a **direct unit test of the `ping()` method**: it verifies the method's output, and **does not verify HTTP request mapping, Spring context, or packaged runtime**. Thereby the exercise deliberately separates `test` responsibilities from `assemble` and the final smoke test.

### 7.2. Run sequentially and record observations

**Step A — `classes`:**

~~~bash
./gradlew clean classes
~~~

Expected: `compileJava`/`processResources` (if sources/resources exist) and `classes` succeed; main classes are generated in `build/classes/java/main/`. There is no basis yet to claim tests ran or an executable JAR was created.

**Step B — `test`:**

~~~bash
./gradlew test
~~~

Expected: Gradle prepares `testClasses` and runs exactly **one** JUnit test in the example (unless the project has other tests or changed config). The report shows `pingMethodReturnsExpectedText` succeeded. If `compileJava` or `classes` shows `UP-TO-DATE`, that is a valid optimization.

**Step C — `check`:**

~~~bash
./gradlew check
~~~

Expected: `check` requires `test`; tests may be `UP-TO-DATE` because they just ran in B. No extra static analysis gates arise when the sample build file declares no corresponding plugins/constraints.

**Step D — `assemble`:**

~~~bash
./gradlew assemble
~~~

Expected: `jar`/`bootJar` are processed per the Spring Boot plugin; an executable JAR exists in `build/libs/`. This step does not use `assemble` to prove tests pass. Inspect contents with `jar tf`; choose the JAR **without the `-plain` classifier** (if keeping default conventions).

**Step E — `build`:**

~~~bash
./gradlew build
~~~

Expected: Gradle treats both `check` and `assemble` as dependencies. Since B–D just created outputs, many tasks may be `UP-TO-DATE`; this is not evidence that they were improperly skipped.

**Step F — verify the artifact actually runs:**

~~~bash
java -jar build/libs/lifecycle-demo-0.0.1-SNAPSHOT.jar --server.port=8085
~~~

In a second terminal, after startup succeeds:

~~~bash
curl -i http://localhost:8085/ping
~~~

Expected: HTTP status `200` and **response body `pong`**. HTTP headers, logs, task ordering, and build times are environment-dependent, so no fixed "exact stdout" is listed. Stop the server with Ctrl+C. If `8085` is already occupied, choose a free port and use the same port in the request command.

Step-by-step conclusions: after A we know main compiled; after B we know the sample unit test passed; after C we know registered verification tasks passed; after D we have the artifact; after E both verification and packaging passed as configured; after F we have additional evidence **that the artifact itself runs and serves HTTP**. These pieces of evidence complement, rather than replace, one another.

### 7.3. Controlled experiment to prove the relationships

**Temporarily** change the assertion in the test from `assertEquals("pong", ...)` to `assertEquals("pang", ...)`, keeping production code unchanged. Then:

~~~bash
./gradlew test
./gradlew check
./gradlew assemble
./gradlew build
~~~

Expected **logical statuses**, with the example's default project:

- `test` **FAILS** because expected `pang` differs from actual `pong`.
- `check` **FAILS** because it depends on test.
- `assemble` can **PASS**, because it only needs to compile/package main output, without depending on test.
- `build` **FAILS** because the `check` branch failed, even if `bootJar` already existed from earlier or could be created.

Try one more time: introduce a syntax error in `LifecycleApplication.java` (e.g., missing a closing brace) and invoke `classes`. When `compileJava` fails, all tasks requiring main output are affected; no need to guess the error solely from a high-level task name. **Restore the original code and assertion after the experiment** so the exercise returns to a passing state.

## 8. How to read task graphs and logs accurately

From a project directory with Gradle Wrapper:

~~~bash
./gradlew tasks --all
./gradlew help --task build
./gradlew build --dry-run
./gradlew build --console=plain
~~~

- `tasks --all` displays invocable tasks, including hidden/ungrouped tasks; the list depends on plugins and modules.
- `help --task build` provides the description of a registered task.
- `build --dry-run` shows scheduled tasks and observable ordering relationships in the current config; **does not execute verification**.
- `build --console=plain` makes logs easier to read in CI/terminals without rich progress, highlighting the first failure more clearly.

Common status markers:

| Status | Correct interpretation |
| --- | --- |
| No label and task output present | The task was executed according to Gradle's actual conditions. |
| `UP-TO-DATE` | Inputs/outputs did not change per incremental mechanism, so Gradle reused prior outputs. |
| `FROM-CACHE` | Outputs were restored from a valid build cache using the task's key. |
| `NO-SOURCE` | The task found no source inputs to work on; check if you expected Java/tests/resources. |
| `SKIPPED` | Task skipped due to configuration/condition or dry-run; inspect the reason before treating as success. |
| `FAILED` | Task failed; the current run cannot be counted as PASS for a gate containing this task. |

**Do not confuse an aggregate task's log with actual work.** For instance, `:classes`, `:check`, or `:assemble` may be lifecycle tasks with almost no action of their own, while the dependencies underneath perform compilation/testing/packaging.

### Multi-project and CI

If a repository has multiple subprojects, running `./gradlew build` at root can affect multiple projects. To inspect a specific application module accurately, use full task paths:

~~~bash
./gradlew :app:classes
./gradlew :app:test
./gradlew :app:check
./gradlew :app:assemble
./gradlew :app:build --dry-run
~~~

`:app` here is an **illustrative subproject name**; replace it with the real path obtained from `./gradlew projects`. Cross-module dependencies may pull tasks from other modules into the run. CI should explicitly specify tasks/modules and archive test reports/artifacts, rather than treating a green line at root as sufficient confirmation for each module.

## 9. Misconceptions and diagnostics

| Claim or symptom | Where is it wrong? | How to verify |
| --- | --- | --- |
| "`classes` is green so there is a JAR to deploy." | `classes` prepares outputs; packaging is `jar`/`bootJar`. | Check `build/libs` and run the proper packaging task. |
| "`test` ran so all integration tests ran." | `test` by default only covers tests it is configured to recognize; separate integration tasks are not auto-added. | Check the task graph, reports, and `check` wiring. |
| "`check` automatically runs every scanner installed in the project." | Only verification tasks actually wired into the graph run. | `check --dry-run`, build script, and plugin docs. |
| "`assemble` succeeded means all tests PASS." | Packaging and verification branches are independent under default Java plugin config. | Induce a controlled test failure and compare `assemble`/`check`. |
| "`build` means compile → test → package in that exact order." | Gradle uses a DAG; `assemble` and `check` are sibling branches; no mandatory linear order. | `build --dry-run` and dependency rules. |
| "There are two JARs so take the smaller/first one." | Plain JARs usually lack Boot launcher/runtime dependencies. | Check classifier names, manifest, `BOOT-INF`, and `java -jar`. |
| "`BUILD SUCCESSFUL` means every test re-ran." | May be `UP-TO-DATE`/cached, skipped, or have no tests. | Read test reports, statuses, and task configuration. |
| "`build` always starts with `clean`." | `clean` is a separate task. | Compare `build --dry-run` and `clean build --dry-run`. |
| "`-x test` is a harmless optimization in CI." | Excluding the test task can make `check`/`build` green while critical verification is skipped. | Only use skip flags when policy allows; inspect pipeline gates. |
| "`build` succeeded means the app can run in production." | Build does not test ports, profiles, DB, secrets, containers, or smoke behavior. | Run the exact artifact in the target environment and test core behavior. |

**Layered troubleshooting approach:**

1. `compileJava`/`classes` error: inspect Java syntax, JDK/toolchain, annotation processors, generated sources, resource paths.
2. `compileTestJava`/`test` error: inspect test dependencies, JUnit engine, fixtures, assertions, classpath, reports.
3. Error in a task running under `check`: find the specific verification task name and gate rules; do not alter `check` just to hide the error.
4. `jar`/`bootJar` error: inspect main class, Spring Boot plugin, duplicate resources, classifier, runtime dependencies, archive task.
5. `build` error: trace back to the **first child task reporting FAILED**; the name `build` is only the aggregating entry point.
6. `java -jar` error after a green build: inspect runtime JDK, manifest, dependencies, profile/port/config, and dependent services; this is a different verification layer from compile/package.

Do not use `-x test` or `enabled = false` to "fix" broken tests; that changes verification scope, not the root cause.

## 10. End-of-lesson checklist and self-assessment

A learner understands the five tasks properly when they can perform both **explanation and verification** as follows:

- [ ] Correctly identify the source creating `classes`/`test` (Java plugin) and the `check`/`assemble`/`build` framework (Base plugin and wired plugins).
- [ ] Accurately draw the two branches of `build`: `check -> test` and `assemble -> jar/bootJar` (per configuration).
- [ ] Explain that `classes` produces main outputs but does not prove tests or packaging.
- [ ] Explain that `testClasses` supports `test` and reports show which tests actually ran.
- [ ] Confirm `check` only covers verification tasks registered into the graph.
- [ ] Distinguish plain `jar` from executable `bootJar` and identify which file to run.
- [ ] Run `build --dry-run` to inspect the task graph, without treating dry-run as a test result.
- [ ] Create a failing test to demonstrate `check`/`build` failing while `assemble` can still pass.
- [ ] Correctly interpret `UP-TO-DATE`, `FROM-CACHE`, `SKIPPED`, `NO-SOURCE`, and `FAILED`.
- [ ] Run the executable JAR and perform a smoke test instead of inferring runtime from `BUILD SUCCESSFUL`.

**Submission exercise:** include a five-row table for `classes`, `test`, `check`, `assemble`, `build`, each row recording (1) the invoked command, (2) subtasks observed from `--dry-run`/logs, (3) outputs or reports, (4) what was proved, (5) what was not yet proved. Attach the executable JAR filename and `GET /ping` result. A complete conclusion must state why `assemble` and `check` are two distinct axes of responsibility combining to form `build`.

## Official references

- [Gradle Java Plugin — source sets and lifecycle tasks](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle Base Plugin — assemble, check, build](https://docs.gradle.org/current/userguide/base_plugin.html)
- [Gradle — Task Basics and dependency graph](https://docs.gradle.org/current/userguide/task_basics.html)
- [Gradle — Controlling Task Execution: dependsOn, mustRunAfter, shouldRunAfter](https://docs.gradle.org/current/userguide/controlling_task_execution.html)
- [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3.13/gradle-plugin/packaging.html)

Examples assume a working Gradle Wrapper, downloadable dependencies, and a compatible JDK. When applying to a real project, **use the actual task graph and build script as the final authority**, as plugins and custom configurations can alter default relationships.