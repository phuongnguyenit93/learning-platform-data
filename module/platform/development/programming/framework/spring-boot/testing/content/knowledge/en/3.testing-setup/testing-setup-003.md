# Spring Boot Dependency Management and Testing Library Compatibility

## 1. Objectives and core problem

When adding JUnit, Mockito, AssertJ, Spring Test, Testcontainers, or HTTP mocking libraries to a Spring Boot project, the question is not merely "which dependency should I add?". You must also determine **who manages the version**, **which classpath** the library sits on, whether the test runner is compatible, and whether they align with the versions of Spring Boot/Spring Framework/Java/Gradle or Maven in use.

After this lesson, you should be able to:

1. Explain how starters, transitive dependencies, BOMs (*Bill of Materials*), build plugins, version constraints, and test scopes differ.
2. Set up JUnit Jupiter + Mockito + AssertJ using `spring-boot-starter-test` without manually pinning duplicate versions of libraries already managed by Spring Boot.
3. Choose additional dependencies for MVC/WebFlux, JPA, Spring Security, and Testcontainers; know which libraries are needed only at test runtime.
4. Read the actual dependency graph to trace resolved versions, version-management sources, and conflicts.
5. Recognize the differences to check when moving from Spring Boot 3.x to 4.x, especially regarding test modules, JUnit, mock beans, and Testcontainers.
6. Distinguish true dependency/version errors from Spring context, runner configuration, datasource, or test logic errors.

**Guiding principle:** choose one consistent dependency-management path for the module, let Spring Boot manage the libraries it has verified together, and override versions only with a technical reason, regression test, and evidence from the dependency tree.

## 2. Diagram of components involved in version management

```text
Spring Boot version chosen by the project
                 |
                 v
  spring-boot-dependencies (BOM)
  [versions of Spring Framework, JUnit,
   Mockito, AssertJ, Testcontainers...]
                 |
        +--------+----------------+
        |                         |
   Maven parent/BOM        Gradle dependency-management
                           plugin or platform(BOM)
        |                         |
        +------------+------------+
                     |
        declared dependencies
          (direct + transitive)
                     |
          build tool resolves
       versions + scopes + conflicts
                     |
         testCompileClasspath /
          testRuntimeClasspath
                     |
       JUnit Platform runs tests
```

Commonly confused concepts:

| Concept | What is its job? | What does it NOT guarantee on its own? |
| --- | --- | --- |
| `spring-boot-starter-test` | Pulls in common testing libraries such as JUnit Jupiter, Mockito, AssertJ, Spring Boot Test | Does not configure all databases, Docker, or HTTP stub servers for the project |
| `spring-boot-dependencies` BOM | Recommends/manages a compatible set of versions for the selected Boot release | Does not add libraries to the classpath without declaring a dependency |
| Spring Boot Gradle plugin | Assists with building, running/packaging, and coordinating dependency management | Using the Boot plugin alone does not manage all configurations; you must choose the dependency-management plugin or import the BOM via Gradle |
| Maven `spring-boot-starter-parent` | Inherits the BOM and useful plugin/build defaults | Not the only option; projects with a custom parent can import the BOM |
| JUnit Jupiter | `@Test` test API and Jupiter execution engine | Does not replace the JUnit Platform launcher/build runner |
| `testImplementation` / Maven `test` | Places libraries into test scope | Does not put those libraries into the production artifact just because tests use them |
| Transitive dependency | A dependency pulled in by a direct library | Not guaranteed to have the same version across every branch of the dependency graph |

**The declared version is not always the used version.** One starter may pull in library A; another module may also pull in a different version of A. Maven picks via dependency mediation/management rules; Gradle resolves via constraints, conflict resolution, and configurations. Accurate conclusions must come from reading the **resolved test runtime classpath**, not just reading the build file.

## 3. What `spring-boot-starter-test` provides

In Spring Boot 3.x, the common test starter brings in two core Spring Boot test modules along with supporting test libraries:

- **JUnit Jupiter / JUnit Platform:** defines `@Test`, `@BeforeEach`, `@ParameterizedTest`, and runs tests.
- **Spring Test + Spring Boot Test:** creates/injects test contexts, `@SpringBootTest`, test slices, and `MockMvc` when the corresponding web layer is present.
- **Mockito:** creates mocks/stubs, declares `when(...).thenReturn(...)`, and verifies collaborators.
- **AssertJ:** readable assertions such as `assertThat(total).isEqualTo(100)`.
- **Hamcrest, JsonPath, JSONassert:** checks objects, JSON content, and JSON path expressions.
- Additional test utilities may vary by Spring Boot line.

In Spring Boot 4.x, `spring-boot-starter-test` still provides the common testing foundation; technology-specific testing capabilities are organized into more focused modules/starters, such as `spring-boot-starter-webmvc-test` and `spring-boot-starter-data-jpa-test`. Do not assume the transitive dependency list remains identical across a major version upgrade.

**Do not** simultaneously add these with handwritten versions:

```groovy
// Easy way to create conflicts when the starter already provides these modules:
testImplementation 'org.springframework.boot:spring-boot-starter-test'
testImplementation 'org.junit.jupiter:junit-jupiter:5.9.0'
testImplementation 'org.mockito:mockito-core:4.8.0'
testImplementation 'org.assertj:assertj-core:3.23.1'
```

Those version numbers only illustrate the conflict anti-pattern; they are **not a recommended version set**. The right starting point, once the project has imported the Spring Boot BOM, is:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

If you genuinely need a test API outside the starter, declare that specific module and let the BOM choose the version if the BOM manages it. If the BOM does not manage it, choose and verify a compatible version separately.

## 4. Complete runnable example: Gradle Groovy DSL, Spring Boot 3.3.0

**The example is pinned to Spring Boot 3.3.0 so the snippets share a single version milestone.** This milestone illustrates configuration mechanics, not a recommendation to keep production on an older release. Real projects should use the organization's chosen release, a safely maintained version, and the matching wrapper. This example runs with Java 17+, Gradle 8.5, and dependencies fetched from Maven Central.

Structure:

```text
testing-dependencies/
├── settings.gradle
├── build.gradle
└── src/
    ├── main/java/example/TestingDependenciesApplication.java
    └── test/java/example/
        ├── DependencySmokeTest.java
        └── ApplicationContextTest.java
```

**`settings.gradle`:**

```groovy
rootProject.name = 'testing-dependencies'
```

**`build.gradle`:**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}

group = 'example'
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

tasks.named('test') {
    useJUnitPlatform()
}
```

**`src/main/java/example/TestingDependenciesApplication.java`:**

```java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TestingDependenciesApplication {
    public static void main(String[] args) {
        SpringApplication.run(TestingDependenciesApplication.class, args);
    }
}
```

**`src/test/java/example/DependencySmokeTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class DependencySmokeTest {
    interface RateProvider {
        int rate();
    }

    @Test
    void junitMockitoAndAssertJWorkTogether() {
        RateProvider provider = mock(RateProvider.class);
        when(provider.rate()).thenReturn(25);

        int result = provider.rate() * 4;

        assertThat(result).isEqualTo(100);
    }
}
```

**`src/test/java/example/ApplicationContextTest.java`:**

```java
package example;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextTest {
    @Test
    void contextLoads() {
        // Passes if ApplicationContext initializes successfully.
    }
}
```

Run using the project's wrapper (once the Gradle 8.5 wrapper exists):

```bash
./gradlew test
./gradlew test --tests example.DependencySmokeTest
./gradlew test --tests example.ApplicationContextTest
```

On PowerShell:

```powershell
.\gradlew.bat test
.\gradlew.bat test --tests example.DependencySmokeTest
```

When both tests succeed, Gradle finishes with `BUILD SUCCESSFUL`; task counts and durations vary by environment. This example does not print data to stdout. The first test proves **JUnit + Mockito + AssertJ** are available; the second test proves **Spring Boot Test** can create a context. They do not verify MVC, JPA, or a database, because this project does not declare them.

**Why is the configuration above correct?** `io.spring.dependency-management` works with the Spring Boot Gradle plugin to import the BOM matching Spring Boot 3.3.0. Dependencies managed by the BOM do not need explicit versions. `useJUnitPlatform()` selects the JUnit Platform runner. `junit-platform-launcher` at runtime gives the build/test runner a launcher compatible with the JUnit suite managed by the BOM.

You cannot run these two test files with plain `javac`/`java` without supplying the JUnit/Mockito/AssertJ/Spring test classpath yourself; use the build tool to fetch and link dependencies properly.

## 5. Two ways to manage the BOM in Gradle

### Approach A: `io.spring.dependency-management` plugin

This is the approach used in the complete example above:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
    id 'io.spring.dependency-management' version '1.1.5'
}
```

When both the Spring Boot plugin and the dependency-management plugin are applied, the Spring Boot BOM matching the Boot plugin version is imported. BOM-supported properties can be used to adjust managed versions, though such changes must be thoroughly verified.

### Approach B: Gradle native BOM via `platform(...)`

Replace the corresponding plugin and dependencies section in **a separate build**; do not combine both approaches into one example:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.0'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES
    )

    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In a standard Java Gradle project, the test configurations inherit what they need from the main configurations, so a BOM declared on `implementation` can affect `testImplementation`. With a **custom test suite/source set** you create yourself, inspect `extendsFrom` and add the BOM to that configuration if needed; do not assume `integrationTestImplementation` automatically receives the BOM.

| Characteristic | Dependency-management plugin | Native `platform(BOM)` |
| --- | --- | --- |
| How versions enter the build | Plugin imports BOM | BOM declared as a dependency in configurations |
| Adjusting managed versions | Possible via BOM properties | Via Gradle version constraints/resolution |
| Scope of effect | Per plugin mechanism and configurations | Only the configuration declaring the BOM and configurations properly extending it |
| Behavior when a transitive requests another version | Follows dependency-management plugin and Gradle resolution | `platform` acts as a recommendation/constraint; Gradle may pick another version from the graph |
| When to choose | Projects standardized on this plugin | Projects using Gradle-native dependency management |

`enforcedPlatform` enforces more aggressively than `platform` and can affect consumer libraries or constraints from other dependencies; use it only after understanding why, never mechanically to "cure" every conflict.

**Important check in multi-project builds:** each module with its own tests must have effective dependencies/BOM on its own classpath. A BOM placed in the root project does not automatically guarantee every subproject uses it unless the build propagates that configuration.

## 6. Maven: `spring-boot-starter-parent` or importing the BOM

### Approach A: Maven parent, suitable for standalone examples

**`pom.xml`** for the same Java 17, Spring Boot 3.3.0 application:

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
        <version>3.3.0</version>
        <relativePath/>
    </parent>

    <groupId>example</groupId>
    <artifactId>testing-dependencies</artifactId>
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
</project>
```

Place the three Java files in `src/main/java` and `src/test/java` as in Section 4, then run:

```bash
mvn test
mvn -Dtest=DependencySmokeTest test
```

When using the project's Maven Wrapper, run `./mvnw test`; on Windows use `.\mvnw.cmd test`. The Maven parent provides dependency management and plugin defaults that help Surefire run JUnit Platform properly. There is no need to redeclare JUnit/Mockito/AssertJ versions when they are already managed.

### Approach B: projects with their own Maven parent

Maven allows only **one direct `<parent>`**. If the organization already has a parent, import the Spring Boot BOM inside `dependencyManagement` in the appropriate POM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

This is an **additional POM snippet**, not a standalone XML file. Afterward, still declare `spring-boot-starter-test` with `<scope>test</scope>` inside `<dependencies>`. Unlike inheriting from the starter parent, importing the BOM **does not** bring along all `pluginManagement` and build defaults from the parent; the organization must configure compiler, Maven Surefire/Failsafe, and plugin versions accordingly.

| Gradle | Maven | Meaning |
| --- | --- | --- |
| `implementation` | `compile` (default) | Used in application code |
| `runtimeOnly` | `runtime` | Needed only at application runtime |
| `testImplementation` | `test` | Compile/run tests, not for main source |
| `testRuntimeOnly` | Usually appropriate `test` dependency | Needed only at test execution; Gradle separates more explicitly |
| `testFixturesImplementation` | No direct default equivalent | Test helper libraries when using the Gradle test-fixtures plugin |

**Maven `dependencyManagement` and Gradle BOMs manage versions; they are not mechanisms that automatically pull every dependency in the BOM.** Declaring the starters, modules, or drivers you actually use remains the module's responsibility.

## 7. Classpaths and scopes: putting libraries in the right place

A common mistake is putting every testing library into `implementation`, accidentally pulling testing tools into the deployed application. Distinguish:

```text
src/main/java   -> compileClasspath / runtimeClasspath
                  implementation + runtimeOnly

src/test/java   -> testCompileClasspath / testRuntimeClasspath
                  main code + testImplementation + testRuntimeOnly
```

The diagram is a simplified model for standard Java Gradle and does not describe every custom configuration.

Example:

```groovy
dependencies {
    // Real application:
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'

    // Testing only:
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}
```

Here the PostgreSQL driver supports the application at runtime; H2 is an embedded database used only in tests if tests are configured to use it. If verifying SQL compatibility with production PostgreSQL, H2 may **not be enough**, and you should use a test PostgreSQL database/Testcontainers. Having H2 on the test classpath does not automatically prove Spring is connected to the intended datasource.

Scope selection rules:

- `testImplementation` for APIs imported by code in `src/test/java`: JUnit, Mockito, Spring Security Test, Testcontainers annotations, test helpers.
- `testRuntimeOnly` for components loaded only when tests run: JUnit Platform launcher, test-only DB drivers, engines not imported at compile time.
- `runtimeOnly` for drivers/libraries needed only when the application runs; standard Java project test runtimes also see main runtime dependencies.
- `implementation` for libraries that production code needs to compile. Never move Mockito to `implementation` just so tests compile.
- If a separate test suite runs via Gradle JVM Test Suites or an `integrationTest` source set, you must configure the classpath, runner, and test dependencies for **that suite**, rather than assuming everything in `testImplementation` automatically appears.

Beyond scopes, watch out for **transitive excludes**. Excluding a seemingly redundant module like `mockito-core` or `junit-jupiter-engine` can break `@Test`/mock runtime. Exclude only after knowing which artifact pulls it in and verifying the tree before and after.

## 8. Choosing dependencies by test type

### 8.1. Plain JUnit/Mockito unit tests without booting Spring

Usually `spring-boot-starter-test` is enough to run plain Java, Mockito, and AssertJ tests on JUnit Platform. Neither `@SpringBootTest` nor web dependencies are needed when objects are instantiated with `new`.

### 8.2. Spring MVC with `@WebMvcTest`, `MockMvc`

- Spring Boot 3.x: Servlet MVC applications have `spring-boot-starter-web` and `spring-boot-starter-test`, using `@WebMvcTest`/`MockMvc` from the corresponding test suite.
- Spring Boot 4.x: check starters split by technology; use `spring-boot-starter-webmvc` for the application and add `spring-boot-starter-webmvc-test` for MVC tests when needed.
- If using Spring Security filters, configure identity/CSRF in tests; 401/403 assertions are security behavior, not necessarily dependency conflicts.

Example **Spring Boot 4.x dependencies snippet**, applied to a build that already has a valid 4.x BOM:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
}
```

Do not copy the Boot 4.x snippet into a Boot 3.3 project just because the example is newer: module/artifact names differ across the two release lines.

### 8.3. Persistence with `@DataJpaTest`

- Spring Boot 3.x: typically `spring-boot-starter-data-jpa` and `spring-boot-starter-test`; add H2 test runtime if actually using H2.
- Spring Boot 4.x: add the `spring-boot-starter-data-jpa-test` starter for JPA slices.
- JPA needs an appropriate driver/schema/transaction setup. A `DataSource` failure can stem from a missing driver or URL, not necessarily JUnit incompatibility.

### 8.4. Spring Security

If tests use `@WithMockUser`, request postprocessors, or Spring Security Test matchers:

```groovy
dependencies {
    testImplementation 'org.springframework.security:spring-security-test'
}
```

When the BOM manages Spring Security, do not manually pin a `spring-security-test` version from a different major line than the Spring Security runtime modules. Security test annotations do not replace the application's actual `FilterChain` configuration.

### 8.5. Reactive WebFlux

- On 3.x: application depends on `spring-boot-starter-webflux`, the common test starter, and any required Reactor test libraries.
- On 4.x: `spring-boot-starter-webflux-test` exists for WebFlux tests.
- With `StepVerifier`, verify `io.projectreactor:reactor-test` is on the test classpath.
- Do not use `@WebMvcTest` for WebFlux handlers and do not mix Spring MVC/WebFlux just to "borrow" test annotations; the two stacks have different application types and auto-configuration.

### 8.6. Testcontainers and real databases

Spring Boot provides container integration via `spring-boot-testcontainers` and `@ServiceConnection` in supported versions. Testcontainers also requires the specific container module, the JUnit integration when using `@Testcontainers`/`@Container`, and a working container runtime.

**Spring Boot 3.x + Testcontainers 1.x** (Gradle dependencies snippet, with an appropriate 3.x BOM applied):

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
```

**Spring Boot 4.x + Testcontainers 2.x** renames artifact modules:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.boot:spring-boot-testcontainers'
    testImplementation 'org.testcontainers:testcontainers-junit-jupiter'
    testImplementation 'org.testcontainers:testcontainers-postgresql'
    testRuntimeOnly 'org.postgresql:postgresql'
}
```

The two snippets are **options for two separate lines**, not to be used simultaneously. Testcontainers 2.x also includes package API changes; update imports and APIs per the migration documentation instead of only changing the artifactId. If Docker is required in CI, verify the runtime first; failure to connect to Docker is not a BOM error.

### 8.7. Test libraries not managed by the BOM

For example, a mock HTTP server or a third-party data generator library not listed in managed dependencies. In that case:

1. Check whether it supports the Java, Jakarta/Spring Framework, JUnit, and HTTP client versions in use.
2. Select a compatible version from the library's release notes.
3. Place the dependency in `testImplementation`/Maven `test` if used only by tests.
4. Use `dependencyInsight`/`dependency:tree` to verify that transitive libraries (Jackson, Netty, SLF4J, Byte Buddy...) do not conflict.
5. Keep a real runnable test to catch API linkage conflicts at runtime.

## 9. Compatibility matrix: verify by **release line**

Do not take a snippet from Spring Boot 4.x and drop it verbatim into 3.3.x or vice versa. Essential differences:

| Component | Spring Boot 3.3.x | Spring Boot 3.4–3.5.x | Spring Boot 4.x |
| --- | --- | --- | --- |
| Spring Framework | 6.1.x in 3.3 | 6.2.x | 7.x |
| Minimum Java | 17 | 17 | 17 |
| Main JUnit line | Jupiter/JUnit 5 | Jupiter/JUnit 5 | Jupiter/JUnit 6 |
| Base Boot test starter | `spring-boot-starter-test` | `spring-boot-starter-test` | `spring-boot-starter-test` + technology-specific test starters/modules |
| Mocking Spring beans | Boot's `@MockBean` | `@MockBean` deprecated, transitioning to Framework's `@MockitoBean` | Boot `@MockBean` removed; use `@MockitoBean` |
| MVC test annotation | Boot 3.x package | Boot 3.x package | Dedicated MVC test module/package |
| JPA test annotation | Boot 3.x package | Boot 3.x package | Dedicated JPA test module/package |
| Testcontainers typically managed by Boot BOM | 1.x | Check managed version for actual minor | 2.x, several artifacts renamed |
| Gradle plugin compatibility | Check 3.3 Gradle wrapper | Check specific minor | Gradle 8.x from 8.14+ or 9.x (per Boot 4.0 requirements) |

You must also check the **actual JDK running Gradle/Maven**, compile JDK toolchain, build plugins, third-party libraries, and patch versions. The matrix above highlights major differences; it does not replace checking version requirements for the exact release.

Annotation imports differ across major versions; for example:

```java
// Boot 3.x:
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;

// Boot 4.x:
import org.springframework.boot.webmvc.test.autoconfigure.WebMvcTest;
import org.springframework.boot.data.jpa.test.autoconfigure.DataJpaTest;
```

These are **side-by-side comparison imports**; do not place four duplicate-named imports in one Java file. For mock beans:

```java
// Spring Boot 3.3:
import org.springframework.boot.test.mock.mockito.MockBean;

// Spring Boot 3.4+ with Spring Framework 6.2+, and Boot 4.x:
import org.springframework.test.context.bean.override.mockito.MockitoBean;
```

`@MockitoBean` is not synonymous with Mockito's `@Mock`: the former replaces a bean inside the Spring context, while the latter only creates a plain Mockito mock. When upgrading, check bean replacement conditions, qualifiers, and context hierarchy rather than only renaming the annotation.

**Do not use the numbers "JUnit 5/6" as exact versions to insert into Gradle**. Those are major lines; obtain the minor/patch versions of JUnit Platform, Jupiter, and launcher from the corresponding dependency tree/BOM.

## 10. JUnit Platform, Jupiter, engines, and discovery

JUnit Jupiter provides the annotations/API for writing tests; **JUnit Platform** provides test discovery/execution; the build tool (Gradle Test task or Maven Surefire) integrates with the platform; and **test engines** execute tests of their respective models.

```text
@Test from org.junit.jupiter.api
            |
       JUnit Jupiter
            |
    Jupiter TestEngine
            |
      JUnit Platform
            |
    Gradle Test / Maven Surefire / IDE
```

In Gradle, remember:

```groovy
tasks.named('test') {
    useJUnitPlatform()
}
```

Depending on Gradle, JUnit, and starter versions, runtime launcher configuration should include:

```groovy
testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
```

When tests "do not run," first check **`import org.junit.jupiter.api.Test`**, the actual task, the test engine on `testRuntimeClasspath`, and `--tests` filters. Do not rush to upgrade all of Spring Boot when the cause is merely the build tool using the wrong platform.

**Legacy JUnit 4:** `org.junit.Test` differs from `org.junit.jupiter.api.Test`. Projects that still have JUnit 4 tests can add the JUnit Vintage Engine matching the JUnit Platform version to run them during migration. Declare the JUnit 4 API for legacy code and Vintage Engine via the BOM/compatible version; do not assume Vintage Engine is included by default in new starters. It is best to migrate tests to Jupiter deliberately and avoid keeping two engines indefinitely if unnecessary.

If using separate JUnit Platform launcher/engine declarations, keep the modules within the same generation managed by the BOM. Overriding the Jupiter API without syncing the engine/launcher easily causes `NoSuchMethodError`, `ClassNotFoundException`, or discovery failures at runtime.

## 11. Diagnosing dependencies with commands instead of guessing

### With Gradle

```bash
./gradlew --version
./gradlew dependencies --configuration testCompileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency junit-jupiter --configuration testRuntimeClasspath
./gradlew dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
./gradlew test --info
```

In multi-project builds, target the right module if needed, for example:

```bash
./gradlew :service:dependencies --configuration testRuntimeClasspath
./gradlew :service:dependencyInsight --dependency mockito-core --configuration testRuntimeClasspath
./gradlew :service:test --tests example.DependencySmokeTest
```

`:service` is an **illustrative module name**, applicable only if it actually exists in the project. On Windows, replace `./gradlew` with `.\gradlew.bat`.

How to read the output:

- `testCompileClasspath`: see the APIs that test files compile against.
- `testRuntimeClasspath`: see engines, launchers, drivers, auto-configuration, and the versions used at runtime.
- `dependencyInsight`: trace **why** a version was selected, which requests took part in conflict resolution, and which branch pulled the dependency in.
- `--info`: inspect the actual test runner, discovered tests, context startup failures, and stack traces; verbose logs are not necessary on every run.

### With Maven

```bash
mvn -version
mvn help:effective-pom
mvn dependency:tree -Dscope=test
mvn dependency:tree -Dscope=test -Dincludes=org.junit.jupiter
mvn test
```

`help:effective-pom` shows versions/plugins/dependency management after inheriting parents and profiles. `dependency:tree` shows resolved dependencies and the branches that pull them in. If using Failsafe for integration tests, also inspect plugin configuration, naming conventions (`*IT`, `*ITCase` depending on config), and the `integration-test`/`verify` goals.

**Read results like an investigator:**

1. Determine whether the error is at **compile**, **test discovery**, **context initialization**, or **runtime invocation**.
2. Note the failing module and the actual Java/build tool versions.
3. Check the resolved version of the artifact appearing in the stack trace along with related modules.
4. Find whether the version came from the BOM, a direct override, a transitive dependency, or a plugin/profile.
5. Change **one well-founded cause**, rerun the reproducing test, and re-inspect the graph.

The dependency tree can change after adding a starter, bumping a patch version, switching profiles, or changing plugins; therefore compare both before and after fixing.

## 12. Common compatibility errors

| Symptom | Hypothesis to check | Action |
| --- | --- | --- |
| `package org.junit.jupiter.api does not exist` | Missing test starter or wrong scope/source set | Check `testCompileClasspath` and the right module |
| `No tests found` / 0 tests executed | Missing `useJUnitPlatform()`, JUnit 4 import, wrong filter, missing test engine | Check runner/engine and test discovery |
| `NoClassDefFoundError` / `ClassNotFoundException` at runtime | Missing runtime artifact, wrong scope, or version mismatch | Inspect `testRuntimeClasspath` and stack trace |
| `NoSuchMethodError` from JUnit Platform, Mockito, Jackson... | Possible binary API version mismatch, outdated IDE launcher, unsynced override | Run `dependencyInsight`, remove unneeded overrides, test via wrapper |
| `@MockBean` does not exist after upgrading to Boot 4 | Boot API was removed | Switch to `@MockitoBean` and review bean override approach |
| `@WebMvcTest` / `@DataJpaTest` import error on Boot 4 | Test packages/modules moved | Add technology-specific test starter and update imports |
| Testcontainers `postgresql` fails to resolve after 2.x upgrade | Old 1.x artifactId | Change to `testcontainers-postgresql`; same for JUnit integration |
| `Could not find ...` when resolving dependencies | Wrong coordinates, missing repository, or broken repository access | Check artifact, version, `repositories`/mirror/auth |
| `Unable to find a @SpringBootConfiguration` | Test/configuration package placement, or slice cannot locate main app | Check package structure and how config is specified |
| `No qualifying bean` in `@WebMvcTest` | Slice intentionally does not load real services | Provide appropriate mocks/test config |
| `Failed to configure DataSource` | Missing DB URL, driver, credentials, container, or test profile | Check datasource and runtime dependencies |
| `401 Unauthorized` / `403 Forbidden` in MVC tests | Security filter/CSRF and test identity | Use Spring Security Test matching the policy |
| Mockito agent/Byte Buddy warning on newer JDKs | Instrumentation/mock maker behavior and JVM restrictions | Check BOM-managed Mockito/Byte Buddy, configure agent per official docs |
| Gradle runs on one JDK while source toolchain uses another | `JAVA_HOME`/Gradle daemon differs from Java toolchain | Compare `gradlew --version`, toolchain, and runtime |

Do not handle every issue by clearing caches, forcing the highest version, or adding blanket excludes. Those actions can temporarily mask errors without fixing the root cause in the graph.

### Three sample investigation cases

**Case A — Tests not discovered:** `@Test` is imported from `org.junit.Test`, while the project uses JUnit Platform without Vintage Engine. Write Jupiter tests with `org.junit.jupiter.api.Test` or deliberately configure Vintage. When changing imports, check API differences such as `@Before` → `@BeforeEach`.

**Case B — Mockito compiles but fails at runtime:** another test library pulls in a different Mockito/Byte Buddy version than the BOM. Run `dependencyInsight --dependency mockito-core` and check Byte Buddy on test runtime; cross-check JDK/Mockito release notes. Avoid manually adding standalone Mockito versions without verifying they belong to the same generation.

**Case C — Boot 4 upgrade breaks web test compilation:** code still imports `org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest` with only the general test starter. Read the migration guide, add `spring-boot-starter-webmvc-test`, and update the import to the new MVC test package. After compiling, recheck MockMvc/bean overrides and test behavior.

## 13. Safe workflow for upgrading testing libraries

When a project needs to upgrade Spring Boot or a testing library, prefer **upgrading along a consistent compatible line**, repeatable step-by-step:

1. **Record the baseline:** Boot plugin/parent/BOM version, Java, Gradle wrapper/Maven, explicit library versions, test tasks, CI image.
2. **Inventory test dependencies:** general test starter, Spring Security Test, WebMvc/JPA/WebFlux tests, DB drivers, Testcontainers, and third-party test libraries.
3. **Read the upgrade guide:** Java/Gradle requirements; package/annotation moves; module artifact renames; removed deprecated APIs; JUnit Platform and Testcontainers major versions.
4. **Upgrade Boot/BOM consistently first:** remove manual versions no longer needed; keep overrides only with justification. If Spring Cloud or a second BOM exists, verify compatible release trains and management order.
5. **Resolve graph and compile tests:** fix class/package errors first; verify test engine/launcher and runtime dependencies.
6. **Run in tiers:** plain unit tests → slices (MVC/JPA) → `@SpringBootTest` → database/containers → CI integration; document which tests fail and why.
7. **Compare before/after:** resolved artifacts, number of tests actually run, failures/logs, and execution time. A green build with a sudden drop in test count can indicate a discovery failure.
8. **Update configuration documentation:** align starters, BOM, wrapper, JDK, and new imports; do not leave old build examples around for others to copy mistakenly.

During migration, if you need to try a version override, include a reproducing test, a written rationale, and a plan to remove the override once the BOM releases a fix. Never pin JUnit/Mockito/Testcontainers separately just because a release is "newer" without verifying compatibility with Spring Boot.

## 14. Practice exercises and completion criteria

**Exercise 1 — Read a real dependency graph**

Use the Gradle example in Section 4. Run `dependencies` and `dependencyInsight`, then answer:

- Which library brings `org.junit.jupiter.api.Test` onto the test compile classpath?
- Which version of `mockito-core` is selected, and which dependency path brings it in?
- Why is `junit-platform-launcher` in `testRuntimeOnly`?
- If you remove `useJUnitPlatform()`, is the runner guaranteed to discover Jupiter tests properly? Test it instead of guessing.

**Exercise 2 — Add a test type**

In a Boot 3.x Spring MVC app that already has `spring-boot-starter-web`, add a `@WebMvcTest`. Use the dependency graph to prove `MockMvc` is on the test classpath. Then try in a separate Boot 4.x project using the MVC test starter for that line. Explain why changing BOM/starter/imports is a coupled set of changes that must be tested together.

**Exercise 3 — Create a conflict in a learning sandbox**

On an experimental branch, add an explicit version of a test library lower than the BOM, and run `dependencyInsight` to see whether the resolved version changes. Then remove the override and compare the tree and test results. **Do not merge this version-forcing experiment into a production branch.**

**Exercise 4 — Testcontainers**

Create an integration test using a PostgreSQL container with the right Testcontainers artifact group for the Boot line. Identify which dependency provides the PostgreSQL container, which provides JUnit integration, and which module integrates `@ServiceConnection`. Check why CI might fail if a container runtime is missing. Do not use real production DB data for the exercise.

### Checklist before marking a testing setup as correct

- [ ] Spring Boot, Spring Framework, Java, and Gradle/Maven versions match the documentation of the **actual release**.
- [ ] There is exactly one clear strategy for managing the Spring Boot BOM in the module; any other BOMs are chosen intentionally.
- [ ] BOM-managed libraries are not manually pinned without reason; versions outside the BOM are verified.
- [ ] JUnit API, engine, launcher, and runner belong to the same generation; the build actually discovers and runs the expected number of tests.
- [ ] Mockito, AssertJ, Spring Security Test, and slice test modules appear on the right test classpaths.
- [ ] Testcontainers/DB drivers use the right artifactIds and runtimes without mixing 1.x and 2.x APIs.
- [ ] Test libraries are not pulled into production artifacts due to wrong scopes.
- [ ] Inspected the resolved dependency graph rather than only reading declarations.
- [ ] Ran small tests and at least one context/slice test matching the technologies in use.
- [ ] When upgrading, imports, starters/modules, and CI runners were checked against the migration guide.

## 15. Rules to remember

- **The BOM sets the version frame; starters select library bundles; scopes control where libraries are used; the build tool computes the resolved graph; the JUnit runner determines whether tests actually run.**
- Use `spring-boot-starter-test` as a baseline, but do not assume it replaces every technology-specific test dependency.
- Distinguish **dependency errors** (unresolved/missing class or method) from **test context errors** (beans, profiles, datasources) and **business errors** (wrong assertions).
- For Spring Boot 4, recheck test packages, split test starters, `@MockitoBean`, JUnit 6, Testcontainers 2, and a compatible Gradle wrapper.
- Every time you add a library or override a version, find evidence on `testRuntimeClasspath` and keep a test reproducing the behavior to protect.

## Official sources for version-specific reference

- Spring Boot — Build Systems / Dependency Management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Spring Boot 3.3 — Gradle dependency management: https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html
- Spring Boot 3.3 — Testing: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html
- Spring Boot 4.0 — Test support: https://docs.spring.io/spring-boot/4.0/reference/testing/
- Spring Boot 4.0 — Build Systems and test starters: https://docs.spring.io/spring-boot/4.0/reference/using/build-systems.html
- Spring Boot 4.0 — System Requirements: https://docs.spring.io/spring-boot/4.0/system-requirements.html
- Spring Boot 4.0 Migration Guide: https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide
- JUnit User Guide: https://docs.junit.org/current/user-guide/
- Mockito: https://site.mockito.org/
- Testcontainers Java: https://java.testcontainers.org/
- Gradle — Dependency Management: https://docs.gradle.org/current/userguide/dependency_management.html
- Maven — Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html