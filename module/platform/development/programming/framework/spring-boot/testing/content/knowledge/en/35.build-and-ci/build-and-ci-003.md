# Source Sets or JVM Test Suites for Integration Tests by Gradle Version

## 1. Goal and Problem Statement

In the **Spring Boot - testing** module, under **Build and CI**, integration tests differ from unit tests in dependency scope and execution time. Ideally, unit tests verify a single class/function using in-memory fixtures and run fast; integration tests may start an `ApplicationContext`, dedicated profiles, databases, HTTP servers, Testcontainers, or brokers. To give each group its own lifecycle and classpath, Gradle offers two approaches:

1. **Source set + custom `Test` task:** manually declare `sourceSets.integrationTest`, configure dependency configurations, `testClassesDirs`, `classpath`, and `useJUnitPlatform()`; works on older Gradle versions that lack the test suites model.
2. **JVM Test Suite:** declare `integrationTest(JvmTestSuite)` inside `testing.suites`; Gradle automatically creates the source set, configurations, and `Test` task for the suite, and then you wire it into the `check` lifecycle.

These two approaches are **alternatives**—never register the same `integrationTest` suite/task twice. This guide presents both completely using identical Java code, outlines Gradle/Spring Boot support boundaries, explains runtime classpath wiring, unit vs. integration fixtures, CI commands, reporting, migration, and subtle breakages across Gradle version upgrades.

Desired final result:

~~~text
./gradlew test             -> 3 unit tests in src/test/java
./gradlew integrationTest  -> 4 integration tests in src/integrationTest/java
./gradlew check            -> both groups, 7 JUnit methods total

src/test/resources/fixtures/unit-only.txt
  -> present in unit test runtime, absent from integration runtime

src/integrationTest/resources/application-it.properties
  -> present in integration runtime, excluded from production bootJar
~~~

**Important:** `@SpringBootTest` does not automatically move a test class from the `test` task to the `integrationTest` task; the **source set or suite** determines which group a Java class belongs to.

## 2. Compatibility Matrix by Gradle Version

| Gradle Wrapper | JVM Test Suite | Spring Boot Gradle Plugin 3.5.16 | Recommendation |
| --- | --- | --- | --- |
| Gradle 6.x, 7.0–7.2 | Not available | Incompatible | If the app uses a supported older Boot version, use source set + Test task |
| Gradle 7.3–7.6.3 | Available since **7.3**, incubating | Below minimum supported version | Upgrade Gradle / pair with matching Boot version |
| **Gradle 7.6.4–7.6.x** | Available, still incubating | **Supported** | Manual source set or JVM suite, preferring the stability the team needs |
| **Gradle 8.4–8.x** | Available, still incubating | **Supported** | Either option; example targets **8.14.3** |
| Gradle 9.x | Available, API still marked incubating | **Boot 3.5 does not declare official support** | Pair with Spring Boot 4.x if Gradle 9 is desired |
| Gradle 8.14+ or 9.x with Boot 4.x | Available | Spring Boot 4.x supports both lines | Migrate and verify plugins/dependencies thoroughly |

The two authoritative references are the Gradle 7.3 release notes (introducing declarative JVM Test Suite) and Spring Boot **3.5.16** system requirements (Gradle 7.x **7.6.4+** or 8.x **8.4+**). Spring Boot 4.x documentation supports Gradle 8.x **8.14+** or Gradle 9.x.

**Do not extrapolate backward or forward**: Gradle 7.3 having JVM Test Suite does not mean Boot 3.5 applies cleanly on Gradle 7.3; Gradle 9 having suites does not mean Boot 3.5 is officially tested on it. Even in Gradle 9 documentation, JVM Test Suite remains an **incubating API** subject to change.

If a legacy project genuinely must run on Gradle 6 or early 7, choose a compatible Spring Boot plugin/Java runtime separately. The Java 17 + Spring Boot 3.5 build scripts in this article are **not** intended for those versions.

## 3. Three Concepts to Distinguish: SourceSet, Test Task, and JvmTestSuite

A **SourceSet** describes the Java classes, resources, and compile/runtime classpaths of a source group. The Java plugin creates `main` and `test` by default, with `src/main/java` and `src/test/java` and their resource counterparts.

Declaring `sourceSets.integrationTest` creates additional Gradle components:

~~~text
compileIntegrationTestJava
processIntegrationTestResources
integrationTestClasses
integrationTestImplementation
integrationTestRuntimeOnly
integrationTestCompileClasspath
integrationTestRuntimeClasspath
~~~

However, creating a source set alone **does not create a Test task that runs JUnit**. You must add:

~~~groovy
tasks.register('integrationTest', Test) {
    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()
}
~~~

This is a **snippet**, not a complete `build.gradle`.

**JvmTestSuite** is a declarative abstraction bundling a `SourceSet`, testing framework, dependencies, and one or more targets. When declaring:

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            useJUnitJupiter()
        }
    }
}
~~~

Gradle creates the corresponding configurations. However, **suites other than the built-in `test` suite do not automatically depend on the production project**; you must declare `implementation project()`. Furthermore, custom suites are not added to `check` automatically.

## 4. Sample Project Layout

A Java 17 Spring Boot 3.5.16 project has this layout:

~~~text
settings.gradle
build.gradle
gradle/wrapper/gradle-wrapper.properties
gradlew
gradlew.bat

src/main/java/com/example/buildci/
  BuildCiApplication.java
  GreetingService.java
src/main/resources/
  application.properties

src/test/java/com/example/buildci/
  GreetingUnitTest.java
src/test/resources/fixtures/
  unit-only.txt

src/integrationTest/java/com/example/buildci/
  GreetingSpringIntegrationTest.java
src/integrationTest/resources/
  application-it.properties
  fixtures/integration-only.txt
~~~

The source code is **identical** across both `build.gradle` approaches. Use **only one** build approach at a time. No Docker, broker, or database is needed to demonstrate separating tasks/classpaths; the integration test here verifies Spring bean discovery, profile properties, and resource visibility.

**`settings.gradle`:**

~~~groovy
rootProject.name = 'gradle-integration-suites-demo'
~~~

Choose Gradle Wrapper **8.14.3** from the 8.x line supported by Boot 3.5. From an environment with Gradle installed, initialize the wrapper:

~~~bash
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
./gradlew --version
~~~

Windows PowerShell:

~~~powershell
gradle wrapper --gradle-version 8.14.3 --distribution-type bin
.\gradlew.bat --version
~~~

`gradle/wrapper/gradle-wrapper.properties` will point to the corresponding distribution, for example:

~~~properties
distributionUrl=https\://services.gradle.org/distributions/gradle-8.14.3-bin.zip
~~~

Keep other wrapper settings and checksums managed by the project; commit `gradlew`, `gradlew.bat`, the wrapper JAR, and properties. CI must invoke **./gradlew**, never a system `gradle` binary whose version differs from the repository.

## 5. Production Application

**`src/main/java/com/example/buildci/BuildCiApplication.java`:**

~~~java
package com.example.buildci;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BuildCiApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuildCiApplication.class, args);
    }
}
~~~

**`src/main/java/com/example/buildci/GreetingService.java`:**

~~~java
package com.example.buildci;

import java.util.Objects;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    private final String prefix;

    public GreetingService(
            @Value("${demo.prefix:Default}") String prefix
    ) {
        this.prefix = Objects.requireNonNull(prefix);
    }

    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException(
                    "name must not be blank"
            );
        }
        return prefix + ", " + name.strip() + "!";
    }

    public String configuredPrefix() {
        return prefix;
    }
}
~~~

`GreetingService` has no mutable per-request state; pure Java tests can call `new GreetingService("Unit")`, while integration tests inject the real Spring bean. A `@Value` constructor parameter is resolved by Spring when creating the bean; when instantiated manually, unit tests pass a String explicitly.

**`src/main/resources/application.properties`:**

~~~properties
demo.prefix=Default
spring.main.banner-mode=off
~~~

In the default application, `GreetingService.greet("An")` returns `Default, An!`. In integration tests activating the `it` profile, `application-it.properties` takes precedence and overrides the prefix to `Integration`.

Never put integration test config inside main resources: doing so can leak test configuration into the production executable JAR.

## 6. Unit Tests in src/test/java

**`src/test/java/com/example/buildci/GreetingUnitTest.java`:**

~~~java
package com.example.buildci;

import org.junit.jupiter.api.Test;
import org.springframework.core.io.ClassPathResource;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class GreetingUnitTest {

    @Test
    void canRenderNameWithoutSpringContext() {
        GreetingService service =
                new GreetingService("Unit");

        assertThat(service.greet(" An "))
                .isEqualTo("Unit, An!");
    }

    @Test
    void rejectsBlankNameAtUnitBoundary() {
        GreetingService service =
                new GreetingService("Unit");

        assertThatThrownBy(() -> service.greet("   "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("name must not be blank");
    }

    @Test
    void unitClasspathContainsOnlyUnitFixture() {
        assertThat(
                new ClassPathResource(
                        "fixtures/unit-only.txt"
                ).exists()
        ).isTrue();

        assertThat(
                new ClassPathResource(
                        "fixtures/integration-only.txt"
                ).exists()
        ).isFalse();
    }
}
~~~

These are **three JUnit Jupiter test methods**. The class does not use `@SpringBootTest`, does not start an application context, and the first method checks only the business behavior of a manually instantiated object.

**`src/test/resources/fixtures/unit-only.txt`:**

~~~text
UNIT_ONLY
~~~

The classpath of the built-in `test` source set includes outputs/resources from `main` and `test`, but does not include `integrationTest` source set outputs by default. The third test catches accidental configuration changes that pull integration-only fixtures into unit runtime.

## 7. Integration Tests in src/integrationTest/java

**`src/integrationTest/java/com/example/buildci/GreetingSpringIntegrationTest.java`:**

~~~java
package com.example.buildci;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.core.env.Environment;
import org.springframework.core.io.ClassPathResource;
import org.springframework.test.context.ActiveProfiles;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

@SpringBootTest(
        classes = BuildCiApplication.class,
        webEnvironment = SpringBootTest.WebEnvironment.NONE
)
@ActiveProfiles("it")
class GreetingSpringIntegrationTest {

    @Autowired
    GreetingService greetingService;

    @Autowired
    ApplicationContext context;

    @Autowired
    Environment environment;

    @Test
    void usesIntegrationProfileConfiguration() {
        assertThat(environment.getProperty("demo.prefix"))
                .isEqualTo("Integration");
        assertThat(greetingService.configuredPrefix())
                .isEqualTo("Integration");
        assertThat(greetingService.greet(" An "))
                .isEqualTo("Integration, An!");
    }

    @Test
    void serviceReallyComesFromSpringContainer() {
        assertThat(context.getBean(GreetingService.class))
                .isSameAs(greetingService);
    }

    @Test
    void integrationClasspathContainsOnlyIntegrationFixture() {
        assertThat(
                new ClassPathResource(
                        "fixtures/integration-only.txt"
                ).exists()
        ).isTrue();

        assertThat(
                new ClassPathResource(
                        "fixtures/unit-only.txt"
                ).exists()
        ).isFalse();
    }

    @Test
    void rejectsBlankInputUsingConfiguredSpringBean() {
        assertThatThrownBy(
                () -> greetingService.greet("  ")
        ).isInstanceOf(IllegalArgumentException.class)
         .hasMessage("name must not be blank");
    }
}
~~~

**Four JUnit Jupiter methods** start a real Spring Boot application context. Two resource files in the `integrationTest` source set:

**`src/integrationTest/resources/application-it.properties`:**

~~~properties
demo.prefix=Integration
~~~

**`src/integrationTest/resources/fixtures/integration-only.txt`:**

~~~text
INTEGRATION_ONLY
~~~

When `@ActiveProfiles("it")` is applied by Spring TestContext, Spring Boot reads profile-specific `application-it.properties` from the `integrationTest` runtime classpath and overrides the main value. This test verifies **Spring configuration integration**, and does not pretend to test databases or HTTP when neither is used.

**Isolation:** `src/integrationTest/resources` must be on the `integrationTest` `runtimeClasspath`, whereas `src/test/resources` is absent by default. If someone attaches `sourceSets.test.output` to the `integrationTest` classpath, the assertion expecting no unit fixture will FAIL—a good signal during code review.

## 8. Option A: Traditional Source Set + Test Task

Option A fits projects with pre-existing custom build logic, needing compatibility with Gradle versions prior to JVM Test Suite, or teams preferring not to depend on an incubating API. With Spring Boot 3.5, you must still stay on Gradle 7.6.4+ (7.x line) or 8.4+ (8.x line).

**Complete `build.gradle`, Groovy DSL, Option A:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

// Third source set. Default paths:
// src/integrationTest/java and src/integrationTest/resources.
sourceSets {
    integrationTest {
        compileClasspath += sourceSets.main.output
        runtimeClasspath += sourceSets.main.output
    }
}

// Inherit TEST LIBRARIES; do not mix output/classes
// or resources of sourceSets.test into integration.
configurations {
    integrationTestImplementation.extendsFrom testImplementation
    integrationTestRuntimeOnly.extendsFrom testRuntimeOnly
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.register('integrationTest', Test) {
    description = 'Runs Spring integration tests.'
    group = 'verification'

    testClassesDirs = sourceSets.integrationTest.output.classesDirs
    classpath = sourceSets.integrationTest.runtimeClasspath
    useJUnitPlatform()

    shouldRunAfter(tasks.named('test'))
    maxParallelForks = 1
    systemProperty 'java.awt.headless', 'true'

    testLogging {
        events 'failed', 'skipped'
    }
}

tasks.named('check') {
    dependsOn(tasks.named('integrationTest'))
}
~~~

**This is a standalone file.** Do not paste Option B into this script.

### Why Is Every Line Above Necessary?

- `sourceSets.integrationTest` causes Gradle to create the `compileIntegrationTestJava` compile task and `processIntegrationTestResources` resource task.
- `compileClasspath += sourceSets.main.output` lets integration Java tests import production `GreetingService`.
- `runtimeClasspath += sourceSets.main.output` makes production classes and `application.properties` visible at runtime.
- `integrationTestImplementation.extendsFrom testImplementation` inherits dependency declarations from unit tests such as JUnit, AssertJ, and Spring Boot starter-test; it **does not** add `src/test` source outputs.
- `integrationTestRuntimeOnly.extendsFrom testRuntimeOnly` brings the JUnit Platform launcher onto the runtime classpath.
- `testClassesDirs` and `classpath` are the two minimum inputs for a custom `Test` task; Gradle 9 especially emphasizes assigning them explicitly.
- `useJUnitPlatform()` is required for JUnit Jupiter when creating a custom `Test` task.
- `shouldRunAfter` only hints ordering when both tasks are in the graph; it does not schedule `test`.
- `check.dependsOn` is the **actual** link that makes `./gradlew check` run integration tests.

### Option A Variant Without Inheriting All Test Libraries

If unit tests carry many mock/benchmark libraries not needed in integration, replace the `configurations` and `dependencies` sections with explicit declarations:

~~~groovy
configurations {
    integrationTestImplementation.extendsFrom implementation
    integrationTestRuntimeOnly.extendsFrom runtimeOnly
}

dependencies {
    integrationTestImplementation 'org.springframework.boot:spring-boot-starter-test'
    integrationTestRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
~~~

This is an **optional variant**, not a block to append to the full script without removing the old configuration inheritance. Keep production/IT dependencies and sourceSet classpaths intact; the test starter dependency receives its version via the Spring Boot BOM/dependency-management plugin.

## 9. Option B: JVM Test Suite on Gradle 8.x

Option B suits projects on recent Gradle versions willing to use the **incubating** test suite API. The Java plugin in modern Gradle integrates with JVM Test Suite. The DSL declares a suite along with its testing framework, dependencies, and target task; do not manually create a source set or task with the same name.

**Complete `build.gradle`, Groovy DSL, Option B — REPLACES all of Option A:**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
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
    implementation 'org.springframework.boot:spring-boot-starter'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

testing {
    suites {
        test {
            useJUnitJupiter()
        }

        integrationTest(JvmTestSuite) {
            useJUnitJupiter()

            dependencies {
                // Project classes are not visible by default
                // inside a non-default JVM test suite.
                implementation project()

                implementation 'org.springframework.boot:spring-boot-starter-test'
                runtimeOnly 'org.junit.platform:junit-platform-launcher'
            }

            targets {
                all {
                    testTask.configure {
                        shouldRunAfter(tasks.named('test'))
                        maxParallelForks = 1
                        systemProperty 'java.awt.headless', 'true'
                        testLogging {
                            events 'failed', 'skipped'
                        }
                    }
                }
            }
        }
    }
}

tasks.named('check') {
    dependsOn(testing.suites.integrationTest)
}
~~~

**This is a standalone file** sharing the same project name, app, resources, and JUnit tests from previous sections. `testing.suites.integrationTest` automatically creates the source set, test task, and dependency configurations.

Key differences to remember:

- With a custom `Test` task, call `useJUnitPlatform()`; with `JvmTestSuite`, call `useJUnitJupiter()` on the suite.
- The built-in `test` suite receives production dependencies by convention; **the `integrationTest` suite does not**, so `implementation project()` must be declared explicitly.
- The `integrationTest` suite is not automatically added to the `check` lifecycle; `dependsOn(testing.suites.integrationTest)` is required.
- Suite `dependencies { implementation ... }` are **scoped dependencies**, not global `dependencies`. They do not automatically inherit `testImplementation`.
- `targets.all { testTask.configure { ... } }` customizes the `Test` task generated by the suite.
- Avoid simultaneously calling `tasks.register('integrationTest', Test)`: Gradle already registers the task for the suite.

Gradle docs note that JVM Test Suite suites other than `test` typically default to JUnit Jupiter, yet **declaring it explicitly** makes the contract clear and avoids relying on convention when reading the build script.

## 10. Controlling Dependencies and Classpaths

| Requirement | Manual Source Set A | JVM Test Suite B |
| --- | --- | --- |
| Production classes | `sourceSets.main.output` added to compile/runtime | `implementation project()` |
| Spring Boot starter-test | Via `integrationTestImplementation.extendsFrom testImplementation` or declared separately | Declared inside suite `dependencies` |
| JUnit Platform launcher | `integrationTestRuntimeOnly` inherited/declared | Explicit suite `runtimeOnly` |
| Test-only resources | `src/integrationTest/resources` | `src/integrationTest/resources` per suite |
| Runtime test classes | `testClassesDirs = ...` | Wired automatically by suite |
| JUnit Platform/Jupiter | `Test.useJUnitPlatform()` | `JvmTestSuite.useJUnitJupiter()` |
| Task registration | `tasks.register('integrationTest', Test)` | Created automatically by suite |
| Check lifecycle | `check.dependsOn integrationTest` | `check.dependsOn(testing.suites.integrationTest)` |

**Especially with Gradle 9:** Gradle changed how custom `Test` tasks receive default test source sets/classpaths. Never define an empty task expecting Gradle to infer them. Even on Gradle 8, setting explicit `testClassesDirs` and `classpath` clarifies the build script and prevents silent test-discovery failures.

Prior to Gradle 9, certain internal Gradle testing libraries could leak onto the runtime classpath and mask a missing JUnit Platform launcher; declaring the launcher explicitly is good practice when preparing for Gradle upgrades.

### How to Inspect Actually Resolved Dependencies

~~~bash
./gradlew dependencies --configuration integrationTestRuntimeClasspath
./gradlew dependencyInsight \
  --configuration integrationTestRuntimeClasspath \
  --dependency junit-jupiter-engine
~~~

Gradle suites and the Spring Boot BOM both govern version resolution. If JUnit artifacts diverge due to hard pinning, use `dependencyInsight` to inspect the resolved dependency graph instead of guessing a JUnit version just to "make it run".

## 11. shouldRunAfter Is Not dependsOn

Three configurations that are easily confused:

~~~groovy
shouldRunAfter(tasks.named('test'))       // prefer order if both are in the graph
dependsOn(tasks.named('test'))            // schedule test as a dependency
check.dependsOn(integrationTest)          // wire integration into check
~~~

These lines are **illustrative snippets**; `check.dependsOn(integrationTest)` is only valid with matching project scope/variables. Both complete `build.gradle` files above use `tasks.named('check')`.

Behavior:

| Command | Under This Article's Config |
| --- | --- |
| `./gradlew test` | Runs unit tests; does not automatically run `integrationTest` |
| `./gradlew integrationTest` | Runs integration tests; does not run `test` solely because of `shouldRunAfter` |
| `./gradlew check` | Task graph includes both `test` and `integrationTest` |
| `./gradlew build` | Java build lifecycle runs `check`, thus both run |
| `./gradlew test integrationTest` | Schedules both; prefers running `test` first |
| `./gradlew integrationTest --tests "*SpringIntegrationTest"` | Filters class inside the integration task |

`shouldRunAfter` is generally preferred over `mustRunAfter` when you simply want unit tests before integration tests if both are scheduled, since Gradle retains scheduling flexibility. `dependsOn(test)` creates an unnecessary hard dependency if you only want ordering and integration tests can run standalone.

If CI wants to skip slow tests when running `./gradlew test`, do not wire `integrationTest` onto the `test` task. Attach it only to `check` or an appropriate CI verification stage.

## 12. Default Source Sets, Resource Directories, and Task Names

The Gradle Java plugin follows conventions:

~~~text
sourceSet name = integrationTest
src/integrationTest/java/
src/integrationTest/resources/
compileIntegrationTestJava
processIntegrationTestResources
integrationTestClasses
integrationTestImplementation
integrationTestRuntimeOnly
~~~

In Option A, you do not need to add:

~~~groovy
java.srcDir 'src/integrationTest/java'
resources.srcDir 'src/integrationTest/resources'
~~~

if following the standard convention. This is just a snippet showing custom paths. Add paths only when the project intentionally moves source directories off the standard layout.

In Option B, the `integrationTest(JvmTestSuite)` suite also uses the source set conventions of the same name. Avoid duplicating Java source directory declarations in both `sourceSets` and `testing.suites`, which causes confusion.

### When Direct Access to Production Java Classes Is Unneeded

Some black-box integration tests only call HTTP endpoints of an already-started process. In that case you do not necessarily need production `classesDirs` on the test compile classpath, though you still need the runtime container/server in CI. The main example calls `GreetingService` directly and therefore **needs** the production code dependency.

## 13. Separating Test Fixtures from Production Runtime

The project has three resource locations:

~~~text
src/main/resources/application.properties
src/test/resources/fixtures/unit-only.txt
src/integrationTest/resources/application-it.properties
src/integrationTest/resources/fixtures/integration-only.txt
~~~

| Task/Lifecycle | Has main resources? | Has unit resources? | Has integration resources? |
| --- | --- | --- | --- |
| `test` | Yes | Yes | No |
| `integrationTest` | Yes | Not by default | Yes |
| `bootJar` application artifact | Yes | Not by default | Not by default |

Two test methods verify isolation via logical paths `fixtures/unit-only.txt` and `fixtures/integration-only.txt`. If anyone attaches `sourceSets.test.output` to the integration runtime, integration test assertions catch that isolation is broken.

**Do not copy `src/test/resources` into `BOOT-INF/classes`** just so integration tests can see shared fixtures. Production packaging could accidentally ship fake credentials mistaken for real ones, JSON fixtures, test-only profiles, or sample payloads.

When you genuinely have shared fixtures, use the `java-test-fixtures` plugin or a dedicated test-support module.

## 14. Shared Test Fixtures Do Not Mean Merging Source Sets

The `java-test-fixtures` plugin provides `src/testFixtures/java` and a shared variant consumable via `testFixtures(project())`.

Example **snippet**:

~~~groovy
plugins {
    id 'java'
    id 'java-test-fixtures'
}
~~~

Then with a JVM suite:

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            dependencies {
                implementation project()
                implementation testFixtures(project())
            }
        }
    }
}
~~~

Do not paste a second `plugins` block into the main `build.gradle` without merging them. The full sample does not currently need test fixtures. When using them, distinguish `testFixturesApi` (exposes compile-time API dependencies to consumers) from `testFixturesImplementation` (implementation-only) to avoid bloating consumers' compile classpaths unnecessarily.

If helpers are needed in both unit and integration tests, test fixtures or a helper module are better than importing backward from `src/integrationTest/java` into `src/test/java` or copying all test outputs.

## 15. How to Verify Gradle Actually Runs the Right Tests

Inspect the task graph and run:

~~~bash
./gradlew --version
./gradlew tasks --all
./gradlew check --dry-run
./gradlew test integrationTest --rerun-tasks
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat tasks --all
.\gradlew.bat check --dry-run
.\gradlew.bat test integrationTest --rerun-tasks
~~~

**`--dry-run` only prints the task graph and does not execute JUnit.** With build cache and up-to-date checks, `BUILD SUCCESSFUL` can occur without re-executing test tasks. Use `--rerun-tasks` when auditing actual execution.

Gradle outputs JUnit XML and HTML reports per task:

~~~text
build/test-results/test/
build/reports/tests/test/

build/test-results/integrationTest/
build/reports/tests/integrationTest/
~~~

In the sample project, expect **3 unit methods + 4 integration methods**. Check testcase counts inside the XML or HTML reports, not just overall status. If a task shows `NO-SOURCE` or `SKIPPED`, that is **not** evidence integration tests were verified.

### Filtering Tests Per Task

~~~bash
./gradlew test --tests "com.example.buildci.GreetingUnitTest"
./gradlew integrationTest --tests "com.example.buildci.GreetingSpringIntegrationTest"
./gradlew integrationTest --tests "*.GreetingSpringIntegrationTest"
~~~

`--tests` does not pull classes from a different source set. `./gradlew test --tests "*SpringIntegrationTest"` may report no matching classes because that class is not in `src/test/java`. That confirms the group split is working.

## 16. When to Use @Tag Instead of Source Sets

JUnit Jupiter offers `@Tag("integration")`. When tests are few, share the same dependencies/resources, and you only want to exclude slow groups from a run, you can configure `Test` tasks to filter tags. However, tags **do not separate compile classpaths or resources**:

~~~groovy
tasks.named('test', Test) {
    useJUnitPlatform {
        excludeTags 'integration'
    }
}
~~~

This is an illustrative snippet, absent from the full build. It only filters execution inside the **test source set**; integration tests still compile alongside unit tests, and resources/dependencies can still bleed across.

Use a source set/JVM suite when you need:
- Different runtime dependencies, such as Testcontainers or a web server.
- Separate CI stages and reports.
- `application-it.properties` profiles that cannot leak into unit tests.
- Different JVM heap/concurrency/timeout settings for integration tests.
- Keeping Docker dependencies out of fast unit `test`.
- Clear confirmation of which tests ran via explicit task names.

Not every project must have multiple suites; choose based on lifecycle and project boundaries.

## 17. Separate JVM Settings for Integration Tests

Integration tests may need different heap, timezone, or fork policies than unit tests. With a manual `Test` task:

~~~groovy
tasks.named('integrationTest', Test) {
    maxHeapSize = '1g'
    maxParallelForks = 1
    systemProperty 'user.timezone', 'UTC'
    jvmArgs '-Dfile.encoding=UTF-8'
}
~~~

This is an **optional snippet** that can go into full Option A. With a JVM suite, put settings inside:

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            targets {
                all {
                    testTask.configure {
                        maxHeapSize = '1g'
                        maxParallelForks = 1
                        systemProperty 'user.timezone', 'UTC'
                    }
                }
            }
        }
    }
}
~~~

This snippet modifies the **existing suite block** of Option B—do not register another suite of the same name. Testcontainers/embedded Kafka can consume significant RAM/CPU; `maxParallelForks` multiplied by concurrent Gradle tasks and CI shards can exceed runner capacity.

Do not take `maxParallelForks=1` as proof that JUnit parallelism is disabled: the JUnit engine can still run tests concurrently inside one fork if `junit-platform.properties` enables it. Design proper test isolation or disable/partition parallel execution intentionally.

## 18. Using Testcontainers Inside integrationTest

A Spring `@SpringBootTest` starting a real context does not necessarily need Docker. When integration tests need PostgreSQL/Kafka, declare Testcontainers only in **integrationTest dependencies**, without forcing unit tests to pull container libraries.

Option A, additional snippet:

~~~groovy
dependencies {
    integrationTestImplementation 'org.testcontainers:junit-jupiter'
    integrationTestImplementation 'org.testcontainers:postgresql'
    integrationTestRuntimeOnly 'org.postgresql:postgresql'
}
~~~

Option B, replace/update `integrationTest.dependencies`:

~~~groovy
testing {
    suites {
        integrationTest(JvmTestSuite) {
            dependencies {
                implementation project()
                implementation 'org.springframework.boot:spring-boot-starter-test'
                implementation 'org.testcontainers:junit-jupiter'
                implementation 'org.testcontainers:postgresql'
                runtimeOnly 'org.postgresql:postgresql'
            }
        }
    }
}
~~~

**These snippets are not part of the Greeting demo build and are not standalone build scripts.** Testcontainers artifact versions can shift across majors; rely on the Spring Boot BOM or matching platform constraints. Using `@ServiceConnection` in Spring Boot 3.5 also requires `spring-boot-testcontainers` in `integrationTest` dependencies. Do not assume `spring-boot-starter-test` includes Testcontainers support.

In CI:
1. The runner must have a Docker/container runtime supported by Testcontainers.
2. Tests need bounded startup/readiness timeouts and must avoid public production services.
3. Containers need lifecycle ownership and cleanup.
4. Database/schema/topic IDs must be isolated when running in parallel.
5. Check CI credential/secret handling; never expose production secrets to untrusted PRs.
6. Cap concurrent test JVMs/containers.
7. Test against a production-like backend when business rules rely on DB locking/constraints rather than inferring from H2.

## 19. GitHub Actions: One CI Workflow That Works for Both Options

**`.github/workflows/verify.yml` — illustrative example:**

~~~yaml
name: verify

on:
  push:
  pull_request:

jobs:
  test:
    runs-on: ubuntu-latest
    permissions:
      contents: read

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - uses: gradle/actions/setup-gradle@v4

      - name: Run both test groups
        run: ./gradlew --no-daemon clean check

      - name: Upload XML and HTML reports
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: gradle-test-results
          path: |
            build/test-results/test/
            build/test-results/integrationTest/
            build/reports/tests/test/
            build/reports/tests/integrationTest/
          if-no-files-found: warn
~~~

This is a starter workflow you can adapt, while checking GitHub Actions policies, action versions, and secret permissions for your organization. It uses the repository's Gradle Wrapper and JDK 17.

In real projects:
- The fast PR lane might run only `./gradlew test`.
- The required integration lane runs `./gradlew integrationTest` or `check`.
- For Docker/Testcontainers, configure a runner that supports them.
- If integration is a required check, never set `continue-on-error: true` and report the pipeline as PASS.
- Upload XML/HTML on failure with `if: always()` to aid diagnosis.
- Never upload only the unit report and forget `integrationTest`.
- When splitting jobs, share/rebuild artifacts properly rather than relying on process-local H2 from another job.

## 20. Gradle 9 and Test Runtime Changes

With Gradle 9:
- The Gradle daemon requires JDK 17+.
- Custom `Test` tasks should not rely on implicit test source sets; specify `testClassesDirs`/`classpath` explicitly.
- JUnit Platform launcher must be on the test runtime classpath; prior to Gradle 9, internal dependency leaks could hide missing launcher configuration.
- JVM Test Suite remains an incubating DSL in current documentation; review release/upgrade guides.
- Spring Boot 3.5 **does not declare Gradle 9 support**; Spring Boot 4.x plugin does, requiring migration/version alignment.

There is no shortcut of "just changing the Wrapper URL" and assuming everything is verified. Upgrading requires verifying `gradlew help`, plugin graphs, compilation, `test`, `integrationTest`, reports, sourceSets, JaCoCo/publishing, and the CI task graph.

**Note on JVM toolchains:** The JDK running the Gradle daemon, the JDK compiling Java 17, and the test runtime JDK are distinct concepts; Gradle Java toolchains let you control several layers. This article selects a shared JDK 17 for reproducibility without claiming every Gradle version runs on every JDK.

## 21. Test Task Orchestration and Coverage Reporting

A project can use `shouldRunAfter` to prefer running unit tests before integration tests in `check`. However, `shouldRunAfter` does not force Gradle to run unit tests if someone runs only `integrationTest`. When CI requires both, run the wired `check` task or invoke both tasks explicitly.

JaCoCo/test coverage requires extra attention:
- `jacocoTestReport` targets built-in `test` by default.
- A custom `integrationTest` task produces its own execution data, which is not merged into a combined report automatically.
- If KPIs require combined coverage, configure `JacocoReport`/report aggregation with the right execution data and source dirs.
- Never point `reports.junitXml.outputLocation` of two tasks at the same directory.
- Test results may be cached or up-to-date; do not assume every `BUILD SUCCESSFUL` freshly executed integration tests.

To QA build wiring, run:

~~~bash
./gradlew check --dry-run
./gradlew test integrationTest --rerun-tasks
./gradlew dependencyInsight --configuration integrationTestRuntimeClasspath --dependency junit-jupiter-engine
~~~

Never treat `--dry-run` as an integration test PASS; it only proves the task graph is constructed.

## 22. Context Cache, Transactions, and Test Isolation

Separating unit and integration tasks may run them in different forked JVMs, yet **does not automatically isolate** every resource:

- Within the same `integrationTest` JVM, Spring TestContext caches `ApplicationContext` across matching test classes.
- Spring singleton beans with mutable state can still leak between integration methods.
- `@MockitoBean`/`@DirtiesContext` require careful parallel test policy.
- Embedded HTTP servers / `@Async` workers run on separate threads, so `@Transactional` on a JUnit test method does not roll back worker DB writes.
- In-memory H2 with a shared URL name can share state within a JVM/context.
- External Docker PostgreSQL/Kafka/Redis instances may be shared across forks/CI shards.
- A test calling global `TRUNCATE`/`cache.clear()` can break tests running concurrently.

Best practices: unique IDs/schemas/tenants per test, cleaning up only test-owned data, awaiting background work before cleanup, scoping test containers, and bounding parallelism. Source set separation solves **build/test lifecycles**, not business data isolation.

## 23. Common Misconfiguration Errors

| Symptom | Cause | Fix |
| --- | --- | --- |
| `integrationTest` does not exist | Only source set defined, missing Test task | Register custom Test or use JVM suite |
| Gradle reports duplicate task `integrationTest` | Registered both manual Test and suite | Pick one approach |
| `compileIntegrationTestJava NO-SOURCE` | Java file in wrong directory | `src/integrationTest/java` |
| Cannot find `GreetingService` | Missing main output / project dependency | A: add `main.output`; B: `implementation project()` |
| Cannot find `@SpringBootTest` | Missing starter-test on IT compile classpath | Add to proper scope |
| Missing JUnit Platform launcher | Missing runtimeOnly / Gradle 9 change | Add launcher |
| Tests compile but are not discovered | Wrong `testClassesDirs`/`useJUnitPlatform`/filter | Inspect Test task, XML counts |
| `Integration` value never appears | `application-it.properties` missing from IT runtime | `processIntegrationTestResources`/classpath |
| Unit fixture appears in IT | Mixed `sourceSets.test.output` | Separate outputs, use `testFixtures` |
| `./gradlew test` does not run IT | Intended source set separation | `integrationTest`/`check` |
| `./gradlew check` does not run IT | Missing `check.dependsOn` | Attach to lifecycle |
| `shouldRunAfter` mistaken for dependency | Ordering only applies when both tasks are scheduled | Use `dependsOn` when needed |
| Boot plugin rejects Gradle version | Outside compatibility matrix | Pin matching Wrapper/Boot |
| `testing.suites` rejects `JvmTestSuite` | Gradle older than 7.3 or DSL error | Upgrade or use manual source set |
| Gradle 9 custom Test misses classes | Implicit test source set removed | Explicit `classpath`/`classesDirs` |
| Gradle 9 + Boot 3.5 fails | Unsupported version pair | Boot 4 compatible or Gradle 8 |
| Empty test reports | Test tasks skipped/`NO-SOURCE` | Verify paths, `--rerun-tasks` |
| Unit stage requires Docker | Integration tests sitting in `src/test` | Move to proper source set |
| CI uses system Gradle | Local/CI versions drift | `./gradlew` |
| Testcontainers fails due to missing Docker | CI runner lacks engine/permissions | Provision runner, readiness, timeout |
| Outcomes vary under parallel runs | Shared DB/bean/static state | Unique IDs, cleanup, grouping |
| Dependencies added to wrong suite | Unit and IT have distinct classpaths | Run `dependencyInsight` on exact configuration |

Never fix classpath errors by appending `sourceSets.test.output` to the `integrationTest` classpath. That erases the boundary and can make tests PASS falsely due to unpackaged resources.

## 24. Pre-Merge Build/CI Checklist

- [ ] Is the Gradle Wrapper version pinned and compatible with the Spring Boot plugin version?
- [ ] If Gradle is below 7.3, is the JVM Test Suite DSL avoided?
- [ ] If using Boot 3.5, are you on Gradle 7.6.4+/8.4+ rather than assuming Gradle 9?
- [ ] Does only one approach (A or B) register `integrationTest`?
- [ ] Does `src/test/java` contain unit tests and `src/integrationTest/java` contain integration tests?
- [ ] Does `src/integrationTest/resources` hold test profiles and fixtures, never `main`?
- [ ] Does the manual `Test` task set explicit `classesDirs`/`classpath`/`useJUnitPlatform`?
- [ ] Does the JVM suite declare `implementation project()` and `starter-test` in the right scope?
- [ ] Is the JUnit Platform launcher declared directly without version skew?
- [ ] Do `test` and `integrationTest` discover the 3/4 methods as in the sample fixture?
- [ ] Does `./gradlew check` schedule both tasks?
- [ ] Is `shouldRunAfter` never mistaken for `dependsOn`?
- [ ] Are `--rerun-tasks`/XML reports used to verify an actual run?
- [ ] Are unit fixtures absent from integration runtime and vice versa?
- [ ] Are test-only resources excluded from `bootJar`?
- [ ] Does CI run the wrapper instead of system Gradle?
- [ ] Are needed Testcontainers libraries placed in the right suite dependencies?
- [ ] Does the runner provide Docker/DB/broker for real integration tests?
- [ ] Do test data namespaces/cleanup survive concurrency and CI shards?
- [ ] Are source sets/shared fixtures free of accidental credentials?
- [ ] Was Java/Gradle/third-party plugin compatibility evaluated during migration?
- [ ] Do JaCoCo and HTML/XML reports avoid overlapping output directories?
- [ ] Is `BUILD SUCCESSFUL` never reported as "7 tests ran" when tasks were `SKIPPED`/`UP-TO-DATE`?
- [ ] Are claims limited to code review if compilation/execution was not actually run?

## 25. Run Commands and Expected Results

Use the Gradle Wrapper and JDK 17. From the directory containing `build.gradle` and the Java/resource files in sections 4–7:

~~~bash
./gradlew --version
./gradlew clean test
./gradlew clean integrationTest
./gradlew clean check

./gradlew test --tests "com.example.buildci.GreetingUnitTest"
./gradlew integrationTest --tests "com.example.buildci.GreetingSpringIntegrationTest"

./gradlew test integrationTest --rerun-tasks
./gradlew check --dry-run
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat --version
.\gradlew.bat clean test
.\gradlew.bat clean integrationTest
.\gradlew.bat clean check

.\gradlew.bat test --tests "com.example.buildci.GreetingUnitTest"
.\gradlew.bat integrationTest --tests "com.example.buildci.GreetingSpringIntegrationTest"

.\gradlew.bat test integrationTest --rerun-tasks
.\gradlew.bat check --dry-run
~~~

Expected counts by structure and assertions:

| Command | Expected Count | Tests |
| --- | ---: | --- |
| `./gradlew test` | **3** | `GreetingUnitTest` |
| `./gradlew integrationTest` | **4** | `GreetingSpringIntegrationTest` |
| `./gradlew check` | **7** total | `test` + `integrationTest` |
| `./gradlew build` | **7** total unless check excluded | Java build lifecycle |
| `test --tests "...GreetingUnitTest"` | 3 | `test` task only |
| `integrationTest --tests "...GreetingSpringIntegrationTest"` | 4 | `integrationTest` task only |

Expected logical outcomes:

~~~text
Unit: new GreetingService("Unit").greet(" An ") = "Unit, An!"
Unit: unit-only fixture present, integration-only fixture absent
Unit: blank input -> IllegalArgumentException

Integration: @ActiveProfiles("it") -> demo.prefix = Integration
Integration: greetingService.greet(" An ") = "Integration, An!"
Integration: @Autowired service = ApplicationContext bean
Integration: integration-only fixture present, unit-only fixture absent
Integration: blank input -> IllegalArgumentException
~~~

These are **expected results from inspecting the code**, **not actual Gradle/JUnit execution logs**. The code was reviewed against official Gradle/JUnit/Spring APIs but **not compiled or run via `gradlew` during authoring**. If you use a different Gradle/Spring Boot version, verify compatibility, plugin versions, and run CI before reporting an actual pass.

## 26. Conclusion and Official References

**There is no single best syntax for every Gradle version.** For older Gradle versions or explicit build logic, use a manual source set + `Test` task. For Gradle 7.3+ where the team accepts an incubating API, JVM Test Suite makes configuration concise. Remember **Spring Boot plugin compatibility**: Boot 3.5.16 officially supports Gradle 7.6.4+/8.4+ (on the 7/8 lines), whereas Gradle 9 requires Spring Boot 4.x where support is declared.

Six rules to remember:

1. JVM Test Suite arrived in **Gradle 7.3**, but is not automatically stable across versions.
2. A manual `Test` task needs **`testClassesDirs` + `classpath` + `useJUnitPlatform`**.
3. Non-default JVM suites need **`implementation project()`** plus appropriate test dependencies.
4. `shouldRunAfter` **does not** pull a task into the graph; `check.dependsOn(integrationTest)` does.
5. Separate source sets enforce **classpath/CI boundaries**, not isolation for shared databases or global state.
6. Check **JUnit XML test counts**, report paths, wrapper versions, and packaged resources to verify the build ran properly.

### Official Documentation

- [Gradle 7.3 Release Notes — introducing JVM Test Suite](https://docs.gradle.org/7.3/release-notes.html)
- [Gradle — JVM Test Suite Plugin](https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html)
- [Gradle — Testing in Java & JVM projects / integration tests](https://docs.gradle.org/current/userguide/java_testing.html#sec:configuring_java_integration_tests)
- [Gradle — Java Plugin and SourceSet](https://docs.gradle.org/current/userguide/java_plugin.html)
- [Gradle — Java Test Fixtures](https://docs.gradle.org/current/userguide/java_testing.html#sec:java_test_fixtures)
- [Gradle — Upgrading to Gradle 9](https://docs.gradle.org/current/userguide/upgrading_major_version_9.html)
- [Gradle — Wrapper](https://docs.gradle.org/current/userguide/gradle_wrapper.html)
- [Spring Boot 3.5.16 — Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/)
- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html)
- [Spring Boot 4.x — Gradle 9 support](https://docs.spring.io/spring-boot/gradle-plugin/)
- [Spring Boot 3.5 — Spring Boot Testing](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html)
- [JUnit Jupiter — Build Support](https://docs.junit.org/current/user-guide/#running-tests-build-gradle)