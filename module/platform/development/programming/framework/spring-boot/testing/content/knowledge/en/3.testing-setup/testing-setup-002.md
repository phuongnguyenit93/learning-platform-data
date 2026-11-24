# Testing Dependencies in Spring Boot: Understanding `testImplementation` and `testRuntimeOnly`

> **Module:** Spring Boot – testing  
> **Knowledge area:** Testing Setup  
> **Focus:** How Gradle places testing libraries on the **test compile classpath** and **test runtime classpath**, when to use `testImplementation` vs. `testRuntimeOnly`, how to configure JUnit/Spring Boot, and how to self-diagnose errors.

## 1. Why split dependency scopes?

When writing tests for a Spring Boot application, we need several kinds of libraries:

- **APIs used in test code:** `org.junit.jupiter.api.Test`, AssertJ, Mockito, `@SpringBootTest`, `MockMvc`, Testcontainers API, etc.
- **Components needed only at test execution time:** JUnit Platform Launcher, a specialized test engine discovered only at runtime, dynamically loaded JDBC drivers, logging providers, or libraries discovered via Java ServiceLoader.
- **Actual application libraries:** web starter, data JPA, production JDBC driver, domain libraries.

Putting everything in `implementation` blurs the boundary between production code and test code: it easily pulls extra dependencies into the application's classpath/packaging, slows dependency resolution, and increases the chance of version conflicts. Gradle provides **configurations** to specify which phase requires each library.

**Most important rule:**

- **`testImplementation`:** test code **needs it to compile** and **needs it at runtime**.
- **`testRuntimeOnly`:** needed **only** when running tests; not present on the test compile classpath.

These are **Gradle** concepts, not Spring Boot library names or annotations. Spring Boot unit tests, slice tests, and integration tests can all use these two configurations. `testImplementation` also does not mean "unit tests only"; it includes libraries that **any test in the `test` source set** needs to compile and run.

## 2. Understanding classpaths and source sets

The Java compiler (`javac`) needs a classpath to locate the types that source code imports, extends, or calls. When running tests, the JVM and test runner need a **runtime classpath** containing the compiled classes along with libraries for execution.

With the Gradle `java` plugin, the standard structure is:

```text
src/
  main/
    java/           # Production application code
    resources/      # Configuration/resources for the application
  test/
    java/           # Test code compiled separately
    resources/      # application-test.yml, fixtures, sample data, ...
```

There are two default source sets: `main` and `test`. The Gradle `java` plugin sets up `compileJava`, `compileTestJava`, `test`, and their corresponding classpaths.

```text
              DECLARED DEPENDENCIES
                  ┌─────────────────┐
                  │ implementation  │ ───► main compile & runtime
                  │ runtimeOnly     │ ───► main runtime
                  └─────────────────┘

                  ┌────────────────────┐
                  │ testImplementation │ ───► test compile & runtime
                  │ testCompileOnly    │ ───► test compile
                  │ testRuntimeOnly    │ ───► test runtime
                  └────────────────────┘

src/main/java ──compileJava────────────► build/classes/java/main
src/test/java ──compileTestJava────────► build/classes/java/test
                                             │
                                             ▼
                      test task (forked test JVM + JUnit Platform)
                      └─ testRuntimeClasspath + test classes
```

### 2.1. Where is each configuration used?

| Configuration | Compile `main` | Run `main` | Compile `test` | Run `test` | Common cases |
| --- | :---: | :---: | :---: | :---: | --- |
| `implementation` | Yes | Yes | Yes* | Yes* | `spring-boot-starter`, `spring-boot-starter-web`, business libraries |
| `runtimeOnly` | No | Yes | No | Yes* | Application database drivers, runtime-loaded providers |
| `compileOnly` | Yes | No | Not by default | Not by default | APIs needed only at `main` compile time |
| **`testImplementation`** | **No** | **No** | **Yes** | **Yes** | `spring-boot-starter-test`, `spring-security-test`, Testcontainers API |
| `testCompileOnly` | No | No | Yes | No | APIs genuinely used only for compiling tests |
| **`testRuntimeOnly`** | **No** | **No** | **No** | **Yes** | `junit-platform-launcher`, H2 when used only for tests |

\* Default behavior of the Gradle Java plugin: `test` is tested against `main`'s outputs and `main`'s runtime dependencies; specifically `testImplementation` extends `implementation`, and `testRuntimeOnly` extends `runtimeOnly`. The table shows practical effects on standard source-set classpaths and does not describe every custom Gradle configuration.

Do not confuse *configurations used to declare dependencies* with *configurations used to resolve classpaths*:

- Declare in `dependencies { testImplementation ... }` or `testRuntimeOnly`.
- Inspect test compile libraries via **`testCompileClasspath`**.
- Inspect test execution libraries via **`testRuntimeClasspath`**.

`testCompileClasspath` and `testRuntimeClasspath` are **resolvable configurations** used by Gradle to assemble classpaths; you should not declare application dependencies directly on them.

### 2.2. Reading it through a concrete scenario

Suppose a test contains the following line:

```java
import org.junit.jupiter.api.Test;
```

The compiler must see the `Test` class, so the JUnit Jupiter API belongs in `testImplementation` (usually provided transitively by `spring-boot-starter-test`). If placed only in `testRuntimeOnly`, the test cannot compile that import.

Conversely, the Gradle test worker needs a **JUnit Platform Launcher** to orchestrate test discovery/execution. Normal test code does not import launcher classes: placing `org.junit.platform:junit-platform-launcher` in `testRuntimeOnly` makes sense. The test runner uses it at runtime.

## 3. Runnable Spring Boot/Gradle configuration example

The example uses **Java 17, Spring Boot 3.5.16, Gradle 8.14.x, Groovy DSL (`build.gradle`)**. That is a consistent illustrative version set: Spring Boot 3.5 supports Java 17+ and the Gradle 8 line according to official documentation. When a project uses Spring Boot 4 or Gradle 9, check the compatibility matrix for that specific release line; the meaning of the two configurations remains the same.

### 3.1. `settings.gradle`

```groovy
rootProject.name = 'testing-dependency-scopes'
```

### 3.2. `build.gradle`

```groovy
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
    // Application code needs this starter to compile and run.
    implementation 'org.springframework.boot:spring-boot-starter'

    // Tests import @Test, assertions, @SpringBootTest, Mockito...:
    // APIs used when compiling tests and when running tests.
    testImplementation 'org.springframework.boot:spring-boot-starter-test'

    // Gradle/JUnit Platform needs the launcher at test runtime.
    // The test code below does not import any classes from the launcher.
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Exact explanation of each key line:

- `java` creates source sets, `testImplementation` / `testRuntimeOnly` configurations, and the `test` task.
- The `org.springframework.boot` plugin provides Spring Boot build/packaging support.
- The `io.spring.dependency-management` plugin works with the Spring Boot plugin to import the `spring-boot-dependencies` BOM and manage versions of BOM-managed dependencies; hence versions can be omitted for the three libraries in `dependencies`.
- `spring-boot-starter-test` brings in common testing dependencies (Spring Boot Test, JUnit Jupiter, AssertJ, Mockito, Spring Test, ...). Because test code must import these APIs, put it in `testImplementation`.
- `junit-platform-launcher` is for JUnit Platform execution, so put it in `testRuntimeOnly`. This is also Gradle's recommended declaration for an explicit compatible launcher at runtime.
- `useJUnitPlatform()` tells the `test` task to use JUnit Platform to discover/run JUnit Jupiter tests. **Having the dependency does not replace configuring the test runner**.
- Test library versions must be managed consistently with the BOM or declared explicitly. Do not arbitrarily add a different JUnit version to a single artifact while the rest of the stack is managed by the BOM.

### 3.3. Project structure and source code

```text
testing-dependency-scopes/
├── settings.gradle
├── build.gradle
├── gradlew                 # Wrapper if project was created via Initializr/Gradle
├── gradlew.bat
└── src/
    ├── main/java/com/example/testingdeps/
    │   ├── TestingDepsApplication.java
    │   └── GreetingService.java
    └── test/java/com/example/testingdeps/
        ├── GreetingServiceTest.java
        └── ApplicationContextTest.java
```

Create the files with the exact paths and class names below.

```java
// src/main/java/com/example/testingdeps/TestingDepsApplication.java
package com.example.testingdeps;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingDepsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingDepsApplication.class, args);
    }
}
```

```java
// src/main/java/com/example/testingdeps/GreetingService.java
package com.example.testingdeps;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {
    public String greet(String name) {
        if (name == null || name.isBlank()) {
            throw new IllegalArgumentException("Name must not be blank");
        }
        return "Hello, " + name.trim() + "!";
    }
}
```

```java
// src/test/java/com/example/testingdeps/GreetingServiceTest.java
package com.example.testingdeps;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

class GreetingServiceTest {
    private final GreetingService service = new GreetingService();

    @Test
    void trimsUserName() {
        assertThat(service.greet("  An  "))
                .isEqualTo("Hello, An!");
    }

    @Test
    void rejectsBlankName() {
        assertThatThrownBy(() -> service.greet("   "))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessage("Name must not be blank");
    }
}
```

```java
// src/test/java/com/example/testingdeps/ApplicationContextTest.java
package com.example.testingdeps;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class ApplicationContextTest {
    @Autowired
    GreetingService service;

    @Test
    void springCreatesServiceBean() {
        assertThat(service.greet("Mai"))
                .isEqualTo("Hello, Mai!");
    }
}
```

**What is being verified?** `GreetingServiceTest` runs only the real Java class without loading a Spring context; `ApplicationContextTest` verifies whether Spring creates/injects the `GreetingService` bean. **What differs in Gradle dependencies?** Nothing: both share the `test` source set and thus receive the same `testImplementation` and `testRuntimeOnly`. Unit/slice/integration are **behavioral testing scopes**, whereas `testImplementation`/`testRuntimeOnly` are **dependency scopes by compile/runtime phase**.

Both tests compile because JUnit/AssertJ/Spring Boot Test APIs are on the test compile classpath. They run via JUnit Platform, and the launcher sits on the test runtime classpath. No code imports the launcher directly.

### 3.4. Running with the Gradle Wrapper

If the project has a Gradle Wrapper (recommended), in the directory containing `build.gradle`:

```bash
./gradlew test
./gradlew test --tests 'com.example.testingdeps.GreetingServiceTest'
./gradlew test --tests 'com.example.testingdeps.ApplicationContextTest'
./gradlew check
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests "com.example.testingdeps.GreetingServiceTest"
.\gradlew.bat check
```

If creating the project manually without a Wrapper yet, use an installed Gradle 8.14.x to generate the Wrapper:

```bash
gradle wrapper --gradle-version 8.14.3
```

Do not copy CLI commands into Java code. When the build succeeds, Gradle may display `BUILD SUCCESSFUL`; task counts, duration, Spring logs, and `UP-TO-DATE` status vary by machine. **Method return values are asserted exactly:** `greet("  An  ")` → `Hello, An!`; `greet("Mai")` → `Hello, Mai!`. These tests do not assert fixed stdout because the code does not call `System.out.println`.

## 4. Which dependencies truly belong in `testImplementation`?

Use `testImplementation` when `src/test/java` or `src/test/kotlin` has **imports, type references, annotations, assertions, or extensions** from the library.

| Dependency | When used | Why it is `testImplementation` |
| --- | --- | --- |
| `org.springframework.boot:spring-boot-starter-test` | JUnit Jupiter, `@SpringBootTest`, AssertJ, Mockito, Spring Test utilities | Tests import these APIs and need them at runtime |
| `org.springframework.security:spring-security-test` | `@WithMockUser`, `SecurityMockMvcRequestPostProcessors`, OAuth2/security filter tests | Test source needs to compile security test annotations/classes |
| `org.testcontainers:junit-jupiter` | `@Testcontainers`, `@Container` | Tests import JUnit extensions |
| `org.testcontainers:postgresql` | Tests directly construct `PostgreSQLContainer` | Tests reference container types/APIs |
| `com.squareup.okhttp3:mockwebserver` (if using Java API directly) | Tests create a mock HTTP server using library classes | Tests import/call its API |

The dependencies in the table are **selective examples**, not a mandatory list for every project. When adding Testcontainers, choose the right modules/versions compatible with the BOM and driver; when using Spring Boot Testcontainers integration, you may also need `org.springframework.boot:spring-boot-testcontainers`.

### 4.1. Why not declare `spring-boot-starter-test` with `implementation`?

`spring-boot-starter-test` contains testing frameworks and helpers; production code should not depend on JUnit, Mockito, AssertJ, or Spring Boot Test just for the application to run. Unsuitable example:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-test' // Wrong purpose
}
```

Fix it to:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Libraries declared in `testImplementation` **do not automatically enter the production bootJar/JAR or published API dependencies** under standard Java/Spring Boot configurations. If a project configures custom packaging, check that custom configuration.

## 5. Which dependencies belong in `testRuntimeOnly`?

Use `testRuntimeOnly` when a library only needs to exist when the **test worker/JVM runs**, while Java test code does not need to import or reference types from that library to compile.

### 5.1. JUnit Platform Launcher

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

Distinguish three roles:

1. **JUnit Jupiter API:** defines `@Test`, `@BeforeEach`, `Assertions`, and the extension model; test code imports it, so it is needed on the **test compile classpath**.
2. **JUnit Jupiter Engine:** discovers and executes Jupiter tests; required on the **test runtime classpath**. `spring-boot-starter-test` normally brings in the engine via the JUnit Jupiter dependency set, so adding a separate line is not always necessary.
3. **JUnit Platform Launcher:** coordinates test engines, used by Gradle at **test runtime**; should be declared explicitly as `testRuntimeOnly`.

If configuring JUnit **without the starter** by declaring manually, you can use:

```groovy
dependencies {
    testImplementation 'org.junit.jupiter:junit-jupiter'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
tasks.named('test', Test) {
    useJUnitPlatform()
}
```

This snippet is only complete when Gradle already has a **version management** mechanism for JUnit modules (such as the Spring Boot BOM). Without a suitable BOM/version catalog, compatible versions must be declared explicitly. `junit-jupiter` aggregates the API and engine; therefore there is no need to add a redundant `junit-jupiter-engine` if it is already in the runtime graph. You can split into API `testImplementation` and engine `testRuntimeOnly` if you intentionally want tight control over each module.

### 5.2. Test-only H2

Suppose the application uses Spring Data JPA, production connects to PostgreSQL, yet some repository tests use H2:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    // Driver for the application running in real environments.
    runtimeOnly 'org.postgresql:postgresql'

    // Embedded driver present only when running tests.
    testRuntimeOnly 'com.h2database:h2'
}
```

With Spring Boot auto-configuration and appropriate test configuration, H2 can be detected to create a test DataSource. Normal test code calls `JpaRepository`/`JdbcTemplate` and does not directly import `org.h2.Driver`, so H2 is not needed on the test compile classpath.

**Limitation:** H2 does not always replicate PostgreSQL behavior (SQL dialect, JSONB, constraints, locking, transactions). For DB-specific queries or high fidelity, prefer running tests against the real engine, such as PostgreSQL Testcontainers. When the project already configures a specific URL/driver via `application.yml` or profiles, test configuration must select the DB explicitly; **merely adding H2 does not guarantee Spring will use H2**.

If test code itself writes:

```java
import org.h2.Driver;
```

then `org.h2.Driver` is a type required at compile time, and **`testRuntimeOnly 'com.h2database:h2'` is not enough**. When you genuinely need to import that API, move the dependency to `testImplementation`. Most JPA tests should not interact directly with the driver class.

### 5.3. Other runtime engines/providers

An engine discovered at runtime by Java ServiceLoader/JUnit Platform can belong in `testRuntimeOnly` if test code does not import the engine API. Conversely, annotations, extensions, or types used by tests to declare tests must be on `testCompileClasspath`; verify exactly which module holds the API and which holds the engine. Do not assume every library with "test" in its name belongs in `testRuntimeOnly`.

## 6. Concrete comparisons: what happens with the wrong scope?

### Scenario A — Putting JUnit API in `testRuntimeOnly`

```groovy
dependencies {
    testRuntimeOnly 'org.junit.jupiter:junit-jupiter-api'
}
```

Test code:

```java
import org.junit.jupiter.api.Test;
class ExampleTest {
    @Test void verifiesSomething() {}
}
```

With a standard test classpath and **no other source of the JUnit API**, `compileTestJava` fails with an error such as `package org.junit.jupiter.api does not exist` because the API is only available at runtime, not at compile time. Solution: `testImplementation 'org.junit.jupiter:junit-jupiter'` or `spring-boot-starter-test`.

### Scenario B — Putting the launcher in `testImplementation`

```groovy
dependencies {
    testImplementation 'org.junit.platform:junit-platform-launcher'
}
```

This case **does not necessarily fail** because `testImplementation` also contributes to the test runtime classpath; however, the launcher appears unnecessarily on the compile classpath. If test code does not import the launcher, `testRuntimeOnly` expresses the intent more accurately and keeps the classpath tighter.

### Scenario C — Omitting `useJUnitPlatform()`

With a traditional `java`/`test` setup, having the JUnit Jupiter dependency does not automatically switch Gradle to JUnit Platform. You must configure:

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
}
```

If using another configuration such as **Gradle JVM Test Suite `useJUnitJupiter()`**, that plugin may handle the framework selection for you. Check which task actually runs before adding duplicate configuration.

### Scenario D — Adding a JDBC driver via `testRuntimeOnly` yet DataSource still fails

The right scope is a **necessary condition**, not a guarantee that tests have the right URL, credentials, database, schema, and profile. For example, if `@SpringBootTest` points its datasource to PostgreSQL with no PostgreSQL running, adding H2 to runtime will not rewrite the URL. You must check datasource configuration or use Testcontainers/a dedicated test database.

### Scenario E — Seeing a test library on the test classpath and assuming it is in `bootJar`

The test runtime contains both production and test dependencies; that is by design. However, standard Spring Boot `bootJar` packages from **main**'s runtime classpath, not `testRuntimeClasspath`. Check the actual scopes in `build.gradle` and any custom build configuration rather than drawing conclusions from a test dependency report.

## 7. How Gradle resolves dependencies and transitive paths

A declared library can pull in **transitive dependencies**. For example, `spring-boot-starter-test` brings in many testing APIs and JUnit modules. You do not need to redeclare all of them if the dependency graph already includes them. However:

- Even when a dependency appears "indirectly," the **classpath still determines** whether test code can compile and run.
- A module can arrive via multiple paths; Gradle selects versions based on dependency constraints, platforms/BOMs, and resolution rules.
- Spring Boot's dependency management plugin helps align versions that Boot has tested together. Different Gradle/Boot versions may use different BOMs.
- `testRuntimeOnly` does not "strip" runtime transitive dependencies of `testImplementation`. Things needed to run tests and declared with proper metadata can still be included.
- `testImplementation` does not mean "exported as an API" to other modules. These dependencies serve the `test` source set of **the module itself**.

Note: `testImplementation` does not create a separate "unit test" task. If there is a custom `integrationTest` source set or `integrationTest` JVM Test Suite, its dependency configurations may be `integrationTestImplementation`/`integrationTestRuntimeOnly`; do not assume by default that they inherit all of `testImplementation`. Read the project's source set/suite configuration before editing.

## 8. Practical commands to verify the actual classpath

Instead of guessing where a library lives, ask Gradle directly:

```bash
# List what the compiler sees when compiling tests:
./gradlew dependencies --configuration testCompileClasspath

# List what the test JVM has during execution:
./gradlew dependencies --configuration testRuntimeClasspath

# Explain which path brings the JUnit launcher into test runtime:
./gradlew dependencyInsight --dependency junit-platform-launcher --configuration testRuntimeClasspath

# Check why a JUnit Jupiter version was chosen:
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath

# Compile tests (without running assertions):
./gradlew compileTestJava

# Run tests:
./gradlew test

# View detailed logs when tests are not discovered or classes are missing at runtime:
./gradlew test --info
```

On Windows, replace `./gradlew` with `.\gradlew.bat`.

**Simple interpretation:**

- `junit-jupiter-api`/AssertJ appear in `testCompileClasspath` so test sources can import them.
- `junit-platform-launcher` should appear in `testRuntimeClasspath` (if not pulled via another path, it will not appear on the test compile classpath).
- `h2`, when declared with `testRuntimeOnly`, appears in test runtime but not in test compile.
- `spring-boot-starter` and application implementation dependencies can appear in **both** main and test runtime because tests need to execute real application code.
- If the dependency report shows `(*)`, `(c)`, or constraint/version selection markers, those are Gradle report notations; do not infer a missing library from a single abbreviated line.

**Note on Gradle cache:** If Gradle considers a task up-to-date and skips executing tests, use `./gradlew test --rerun-tasks` when you genuinely need to re-verify execution; do not force reruns in CI without reason.

## 9. Same concepts in Kotlin DSL

If the build uses `build.gradle.kts`, configuration names **stay the same**; only the syntax changes:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "0.0.1-SNAPSHOT"

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
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

tasks.named<Test>("test") {
    useJUnitPlatform()
}
```

This is an **alternative version** of `build.gradle`; do not place both build files side by side in one project expecting Gradle to merge them. Pick one DSL per project.

## 10. How does this differ from Maven `scope=test`?

Maven and Gradle share the idea of classpath management, but **scope names do not map 1-to-1**.

Maven example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

In Maven, the `test` scope makes a dependency available for **test compilation** and **test execution**, fairly close in meaning to `testImplementation`. Maven has no standard scope named `testRuntimeOnly`; do not mechanically translate it to `<scope>runtime</scope>`, because Maven's `runtime` can participate in the application's main runtime.

| Purpose | Gradle (`test` source set) | Standard Maven |
| --- | --- | --- |
| Dependency needed at test compile and runtime | `testImplementation` | `scope=test` |
| Dependency needed at test runtime only | `testRuntimeOnly` | No direct standard equivalent |
| Driver needed at main app runtime | `runtimeOnly` | `scope=runtime` |
| Library for compiling/running main code | `implementation` | Typically default `scope=compile` |

Maven Surefire/Failsafe have their own way of constructing the test runtime classpath; do not extrapolate Gradle configurations directly onto Maven.

## 11. Quick decision rules

Start with **whether Java/Kotlin test code imports classes from the dependency**, and then ask whether that dependency is needed for the production application to run.

1. **Production code directly uses the library to compile and run?** → `implementation`.
2. **Production code only needs it when the JVM runs (e.g., JDBC driver)?** → `runtimeOnly`.
3. **Test source imports APIs/annotations or calls classes from the library?** → `testImplementation`.
4. **Test source does not reference it at compile time, yet the test JVM/runner needs to discover or load it at runtime?** → `testRuntimeOnly`.
5. **Needed only at test compile time, never at runtime?** → consider `testCompileOnly`; this case is rare, and misusing it can cause `NoClassDefFoundError` at runtime.

If test source imports a class and the library is only added to `testRuntimeOnly`, the error typically occurs **in `compileTestJava`**. If source compiles but a driver/engine/provider is missing when running, the error typically occurs **in `test` / test runtime**. The two error types point to two different classpaths to inspect.

## 12. Checklist when configuring Spring Boot tests

- [ ] Applied the `java` plugin or corresponding JVM plugin, with a `test` source set.
- [ ] Placed `spring-boot-starter-test` in `testImplementation` (or declared an equivalent test stack).
- [ ] Enabled `useJUnitPlatform()` on the test task running JUnit Jupiter, unless a test suite plugin already configures it.
- [ ] Declared `junit-platform-launcher` in `testRuntimeOnly` per Gradle guidance.
- [ ] If using Spring Security Test/Testcontainers APIs, their imported classes are on the **test compile classpath**.
- [ ] If using runtime test drivers/engines, they are on the **test runtime classpath** with compatible versions.
- [ ] Distinguished production `runtimeOnly` drivers from test-only `testRuntimeOnly` drivers.
- [ ] Inspected `testCompileClasspath` and `testRuntimeClasspath` via `dependencies` instead of guessing from the build file.
- [ ] Ran `compileTestJava` and `test`; counted executed tests to spot unexpected skips.
- [ ] Did not move unit-testing libraries into `implementation` merely to fix import errors in `src/test/java`.

## 13. Self-check questions

**Question 1:** Why does a test containing `import org.junit.jupiter.api.Test;` fail to compile when the JUnit API is only declared in `testRuntimeOnly`?  
**Answer:** Because the test compiler only sees `testCompileClasspath`, whereas `testRuntimeOnly` only contributes to `testRuntimeClasspath`.

**Question 2:** Why is `testImplementation 'spring-boot-starter-test'` still available when running tests?  
**Answer:** `testImplementation` participates in both test compile and runtime classpaths; "implementation" in its name does not mean compile-only.

**Question 3:** Can the launcher be placed in `testImplementation`?  
**Answer:** From a classpath standpoint, it usually still works because runtime includes `testImplementation`; however, `testRuntimeOnly` states the intent accurately and avoids adding unnecessary entries to the compile classpath.

**Question 4:** Why can `testRuntimeOnly 'com.h2database:h2'` be suitable for JPA tests?  
**Answer:** Spring/DataSource loads the JDBC driver at test runtime, while test code may only import JPA repositories and never import H2.

**Question 5:** If a test needs `@WithMockUser`, which scope should be chosen for `spring-security-test`?  
**Answer:** `testImplementation`, because test code references that annotation at compile time.

**Question 6:** Gradle tests report "No tests found". Is adding the launcher alone enough?  
**Answer:** Not necessarily; you also need to verify `useJUnitPlatform()`, the test engine, source set paths, annotations, and any `--tests` filter.

**Question 7:** Are dependencies in `testRuntimeOnly` automatically packaged into the main `bootJar`?  
**Answer:** No, with standard configuration `bootJar` uses `main`'s runtime classpath, while `testRuntimeOnly` serves only the `test` source set.

## 14. Official documentation

- Gradle – [Dependency configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html): scope concepts, `testImplementation`, and `testRuntimeOnly`.
- Gradle – [Java Plugin](https://docs.gradle.org/current/userguide/java_plugin.html): relationship between declared configurations and the two test classpaths.
- Gradle – [Testing in Java & JVM projects](https://docs.gradle.org/current/userguide/java_testing.html): `useJUnitPlatform()`, test task, JUnit launcher, test source set.
- Spring Boot 3.5 – [Gradle Plugin](https://docs.spring.io/spring-boot/3.5/gradle-plugin/): compatible Gradle versions and plugin configuration.
- Spring Boot 3.5 – [System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): supported Java/Gradle versions.
- Spring Boot – [Managing Dependencies](https://docs.spring.io/spring-boot/3.5/gradle-plugin/managing-dependencies.html): Spring Boot BOM and dependency management.
- JUnit 5 – [User Guide](https://junit.org/junit5/docs/current/user-guide/): JUnit Jupiter/Platform and engines.

**Point to remember:** `testImplementation` answers "*does test code need this library to compile and run?*", whereas `testRuntimeOnly` answers "*is this library only needed when tests are executed?*". Understanding that distinction keeps build configuration clean, avoids leaking test dependencies into the application, and accurately separates compile errors from runtime errors.