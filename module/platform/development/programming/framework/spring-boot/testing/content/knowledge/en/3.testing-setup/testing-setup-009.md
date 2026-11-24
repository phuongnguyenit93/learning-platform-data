# Classpath, Test Resources, and Differences from the Application Environment in Spring Boot

## 1. Objectives

An application can pass `mvn test` or `gradle test` yet fail when run via `java -jar`: missing JSON/SQL files, wrong configuration, beans that exist only in tests, or libraries declared only in test scope. Conversely, a test can read `application-test.properties`, H2, Mockito, and fixtures that the deployed application does not have at all. To find the root cause, you must understand three distinct things:

1. **The JVM classpath** decides which classes and resources the class loader can find.
2. **Source sets and dependency scopes** decide what enters the classpath during compilation, test execution, application execution, and packaging.
3. **Spring Boot's configuration mechanism** decides the final value of each property after merging files, profiles, environment variables, command-line arguments, and test overrides.

After this lesson, you should be able to distinguish `src/main/resources` from `src/test/resources`, explain why the test classpath differs from the runtime classpath, properly use `@ActiveProfiles`/`@TestPropertySource`/`@SpringBootTest(properties = ...)`, access fixtures without relying on the working directory, and inspect a production artifact to verify whether it includes or excludes expected resources.

The hands-on lab uses **Java 17+, Maven, Spring Boot 3.5.16, and JUnit Jupiter**, with corresponding Gradle equivalents covered as well. Package/plugin names may differ in Spring Boot 4.x, so always check documentation for your exact major version when upgrading.

## 2. What is the classpath really?

The classpath is the list of **directories containing classes/resources** and **JAR files** that a class loader can search. The JVM can load `com.example.App` from `com/example/App.class`, and `ClassLoader.getResource("fixtures/order.json")` resolves `fixtures/order.json` **relative to the classpath root**.

The classpath is NOT the same as:
- The `src/main/java` source directory, because Java must be compiled into `.class` files.
- The working directory where you run commands: `new File("...")` resolves filesystem paths; `classpath:...` resolves resources via a class loader.
- Spring `Environment`: this is the merged set of property sources, of which classpath files are only one source.
- Every dependency in `pom.xml`/`build.gradle`: scopes/configurations determine whether a dependency is present in each phase.
- The JPMS module path (`--module-path`): the Java module system follows different rules than the traditional classpath; many Spring Boot apps still use the classpath when running executable JARs.

Default Maven layout:

```text
PROJECT/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/com/example/.../*.java       -> compile -> target/classes/.../*.class
│   │   └── resources/
│   │       ├── application.properties         -> target/classes/application.properties
│   │       └── templates/email.html            -> target/classes/templates/email.html
│   └── test/
│       ├── java/com/example/.../*Test.java     -> target/test-classes/.../*Test.class
│       └── resources/
│           ├── application-test.properties     -> target/test-classes/application-test.properties
│           └── fixtures/sample.json            -> target/test-classes/fixtures/sample.json
└── target/
    ├── classes/                               # main output
    ├── test-classes/                          # test output
    └── app.jar                                 # runtime artifact (no test-classes)
```

Maven Surefire by default constructs the test runtime classpath in order: **`target/test-classes` → `target/classes` → dependencies → configured additions**. This model is crucial for understanding same-named resources in test environments. Gradle also has separate main/test source sets and outputs, though **you must not assume every launcher/IDE uses Surefire's exact classpath order**; inspect the actual runtime classpath when debugging.

## 3. Distinguishing execution phases and resource visibility

| Context | Source/output typically used | Visible resources | Typical dependencies |
| --- | --- | --- | --- |
| Main compile | `src/main/java` → `target/classes` | `src/main/resources` copied to main output | Maven `compile`; `provided` for compilation; Gradle `implementation`/`compileOnly` |
| Test compile | `src/test/java` → `target/test-classes`, referencing main | Main and test outputs per build flow | Main dependencies + `test` scope/`testImplementation` needed for compilation |
| Test execution | Test classes + main classes + test/main resources | **Both test fixtures and app resources** | `spring-boot-starter-test`, Mockito, JUnit, test JDBC drivers... if declared accordingly |
| Running from IDE or `spring-boot:run`/`bootRun` | Main output and runtime dependencies; customizable by IDE/plugin | Defaults to **main resources**; custom setup can change this | Runtime classpath, does not include all test dependencies by default |
| Running executable JAR `java -jar` | App classes and resources inside the artifact | `BOOT-INF/classes` + JAR deps in `BOOT-INF/lib` plus external config | Dependencies packaged by the build plugin; test-scope libraries are excluded by default |
| Running in container/deployment | Built artifact + env/mounted files/infra | Artifact contents plus provided external config/mounts | Depends on image, Java runtime, launch command |

Practical conclusions:
- `src/test/resources/fixtures/data.sql` is visible during `mvn test`, yet **does not automatically appear in the production JAR**.
- If tests use H2 in `test` scope while deployment uses PostgreSQL, tests can stay "green" even when production SQL queries/dialects differ.
- You cannot use "tests run from the IDE" as proof that `java -jar` will work: the IDE can inject extra folders, VM options, working directory, or system properties.
- `@SpringBootTest` boots a Spring context, yet still runs on the **test classpath**. It does not reproduce the exact classpath of the packaged artifact.

## 4. Main and test resources: where to place them and how to read them

### 4.1. File placement conventions

| Resource | Recommended path | Reason |
| --- | --- | --- |
| Default app configuration | `src/main/resources/application.properties` or `application.yml` | Packaged for use when running the app |
| Templates/emails, schemas, static files needed at runtime | `src/main/resources/templates/...`, `static/...`, `db/migration/...` | Included in the artifact; follows standard directory conventions |
| Test-specific profile config | `src/test/resources/application-test.properties` | Present only on test classpath; activated with `@ActiveProfiles("test")` or equivalent |
| JSON/XML/CSV fixtures and expected outputs | `src/test/resources/fixtures/...` | Kept separate from production data |
| Test SQL setup/cleanup | `src/test/resources/sql/...` | Referenced via `@Sql("classpath:/sql/setup.sql")` or test code |
| Test logger config | `src/test/resources/logback-test.xml` (when using Logback) | Tunes test logging without entering the app JAR |
| Replacement Spring configs for tests only | `src/test/java/.../*TestConfig.java` or nested `@TestConfiguration` | Lives in test source set; imported intentionally |

Keep these distinctions clear:
- `src/main/resources/config/settings.json` is copied to the classpath root as `config/settings.json`, **not** `src/main/resources/config/settings.json`.
- Java code uses `getResourceAsStream("config/settings.json")` or Spring's `new ClassPathResource("config/settings.json")`; **do not** use the `src/...` source path at runtime.
- `getClass().getResource("/config/settings.json")` has a leading `/` to search from the classpath root; `ClassLoader#getResource("config/settings.json")` has **no** leading `/`. Do not mix the two conventions.
- Resources inside a JAR may lack a regular filesystem path. `ClassPathResource#getInputStream()` works; `getFile()` can fail when the resource resides inside a JAR. Use `Path`/`File` only for genuine external files.

### 4.2. What happens when resource names collide?

Suppose both exist simultaneously:

```text
src/main/resources/application.properties    demo.mode=main
src/test/resources/application.properties    demo.mode=test
```

In many test runners (including Surefire's default order), the file in `test-classes` is found before the file at the same path in `classes`. With configuration loading, this easily shadows values or the entire main file; exact results also depend on how Spring Boot collects config locations/imports. **Do not design tests around an implicit assumption that two identically named files merge in a desired order**.

A clearer pattern:

```properties
# src/main/resources/application.properties
demo.mode=main
demo.timeout=3s
```

```properties
# src/test/resources/application-test.properties
demo.mode=test
```

Use `@ActiveProfiles("test")` to load the corresponding profile config; non-overridden properties can still come from the base configuration. If the test environment needs vastly different settings, use a complete test profile/config verified by tests checking critical values, rather than relying on subtle resource shadowing.

For files such as `messages.properties`, `schema.sql`, `logback.xml`, `application.properties`, and `META-INF/...`, be extra careful with duplicate names because frameworks apply specific discovery and precedence rules. Some APIs use `getResource` (taking the first match) while others use `getResources` (collecting all matches). Do not generalize one API's rule to another.

## 5. Dependency scopes: why the test classpath is "wider"

### Maven

```xml
<dependencies>
  <!-- Present in code/application runtime -->
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
  </dependency>

  <!-- Used only when compiling/running tests -->
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
```

| Maven scope | Practical meaning |
| --- | --- |
| `compile` (default) | Needed for compilation and runtime, and visible to tests |
| `runtime` | Not required for main compilation; present at application and test runtime |
| `test` | Used for test compilation and test runtime; **not** included in production runtime by default |
| `provided` | Project expects the environment to supply the library; packaging in executable JAR/WAR depends on Spring Boot packaging and plugins, not just the scope name |

Use the Maven BOM/`spring-boot-starter-parent` to align versions. When encountering `NoSuchMethodError`, `ClassNotFoundException`, or `NoClassDefFoundError`, inspect the **actual dependency graph** in test and runtime first; the fault may be a missing library or version conflict rather than a resource file.

```bash
mvn dependency:tree -Dscope=test
mvn dependency:tree -Dscope=runtime
mvn help:effective-pom
```

### Gradle

In a project configured with the Java and Spring Boot plugins:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    // testRuntimeOnly("...") if library is needed only at test runtime
}

tasks.test {
    useJUnitPlatform()
}
```

This is a **dependency configuration snippet** inside `build.gradle.kts`, not a complete build script; Spring Boot version/BOM/plugins must be declared elsewhere in the project. Gradle provides `sourceSets.main` and `sourceSets.test`; the `test` task runs with `sourceSets.test.runtimeClasspath`. You can inspect:

```bash
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew test --info
```

On Windows, use `gradlew.bat` accordingly. If creating a custom `integrationTest` source set or JVM Test Suite, you must explicitly define dependencies, outputs, `runtimeClasspath`, and tasks rather than assuming integration tests see all test fixtures by default.

**Pitfall:** adding mocks/test drivers to `implementation` just to "silence class-not-found errors" bloats production dependencies or alters auto-configuration. Move a dependency to main runtime only if the application **genuinely requires** it at runtime.

## 6. How does Spring Boot read configuration on the test classpath?

Being present on the classpath **does not mean** Spring automatically reads a resource as properties. Spring Boot recognizes `application.properties`/`application.yml` and profile variants; a file named `fixtures/sample.properties` does not become environment properties unless explicitly imported or declared.

### 6.1. Key mechanisms

| Configuration method | Effect | When to use |
| --- | --- | --- |
| `@ActiveProfiles("test")` | Activates a Spring profile, loading `application-test.properties` and `@Profile` beans | Most integration/slice tests needing consistent test configuration |
| `@SpringBootTest(properties = "demo.mode=inline")` | Overrides properties when creating the Spring Boot test context | A single test needing a few explicit values changed |
| `@TestPropertySource(properties = "demo.mode=inline")` | Adds properties directly to the test `Environment` | Testing a Spring context with specific overrides |
| `@TestPropertySource(locations = "classpath:config/override.properties")` | Loads a properties file at the specified location | A group of tests using a dedicated config file |
| `@DynamicPropertySource` | Registers dynamic values (e.g., Testcontainers URL/port) | Values known only after test infrastructure starts |
| `System.setProperty(...)` inside tests | Mutates global JVM state | **Avoid**; easily leaks into other tests or breaks context caching |
| `spring.config.import` | Imports config data via Spring Boot's mechanism | When app/tests need controlled modular config splitting |

Key difference: `@ActiveProfiles("test")` **does not create** `application-test.properties` and does not put files under `src/test/resources` into the production JAR. Profiles only govern how Spring evaluates and applies **already present** configuration sources.

You can use `@TestPropertySource("classpath:config/custom.properties")` to read `src/test/resources/config/custom.properties`. In Spring Framework 6.x, `@TestPropertySource` defaults to supporting `.properties` (and XML properties) files; do not assume `@TestPropertySource("...yml")` works without configuring an appropriate factory. To use YAML through standard Spring Boot mechanics, prefer `application-{profile}.yml` or `spring.config.import`.

### 6.2. There is no single "one-size-fits-all" precedence order

Spring Boot merges configuration sources according to `Environment` precedence. A typical pattern is:
- `application.properties` provides defaults.
- `application-test.properties` overrides matching keys when the `test` profile is active.
- Environment variables, Java system properties, and command-line arguments can override config files (per precedence and launch method).
- Properties declared in test annotations and dynamic test property sources typically override file-based config.
- External config files outside the JAR can override files inside the JAR.

Exact precedence depends on **version**, `ConfigData` rules, test annotations, and custom property sources. Do not guess solely from file locations. If a value is unexpected, read `Environment#getProperty` in a test and inspect provenance via `ConfigurableEnvironment#getPropertySources()`; in real systems, Actuator `env`/`configprops` should only be enabled in appropriate environments under proper security policies.

Example of a property "changing" because of CI:

```text
application.properties:             demo.mode=main
application-test.properties:        demo.mode=test
CI environment DEMO_MODE:           ci
@SpringBootTest(properties=...):    demo.mode=inline
```

Inspecting each file individually makes the final value hard to predict. Write assertions stating the test's contract and check the impact of override sources. Also avoid putting `spring.profiles.active` inside profile-specific files; profiles should be chosen at launch time, via test annotations, or valid configuration per docs.

## 7. Complete hands-on lab: proving the difference between tests and packaged app

The project below compiles and runs with Maven and Java 17+. The goal is to clearly observe:
- Tests read **main resources + test-only fixtures**.
- `@ActiveProfiles("test")` loads `application-test.properties` from the test classpath.
- Intentional test overrides differ from the profile file value.
- The packaged JAR **does not** contain fixtures or profile configs from `src/test/resources`.
- Activating the `test` profile when running the JAR **cannot magically pull test resources into the JAR**.

### 7.1. File tree

```text
classpath-lab/
├── pom.xml
├── src/main/java/com/example/classpathlab/
│   └── ClasspathLabApplication.java
├── src/main/resources/
│   ├── application.properties
│   └── fixtures/public-message.txt
└── src/test/
    ├── java/com/example/classpathlab/
    │   ├── ClasspathResourceTest.java
    │   ├── ProfileConfigTest.java
    │   └── InlineConfigTest.java
    └── resources/
        ├── application-test.properties
        └── fixtures/test-message.txt
```

### 7.2. `pom.xml`

```xml
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
  <artifactId>classpath-lab</artifactId>
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
```

`spring-boot-starter-test` brings JUnit Jupiter and Spring Test support onto the **test classpath**. The example needs no web server, datasource, or other external libraries.

### 7.3. Main application

`src/main/java/com/example/classpathlab/ClasspathLabApplication.java`:

```java
package com.example.classpathlab;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.Environment;

@SpringBootApplication
public class ClasspathLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ClasspathLabApplication.class, args);
    }

    @Bean
    CommandLineRunner printMode(Environment environment) {
        return args -> System.out.println(
                "MODE=" + environment.getProperty("demo.mode", "missing"));
    }
}
```

The application prints one value and exits (no web server), making classpath differences easy to observe. Spring Boot may still print startup logs, while the **line starting with `MODE=`** is the deterministic output of the example when no external overrides are present.

Exact contents of each file:

```properties
# src/main/resources/application.properties
demo.mode=main
```

```text
# src/main/resources/fixtures/public-message.txt
MAIN_RESOURCE
```

```properties
# src/test/resources/application-test.properties
demo.mode=test
```

```text
# src/test/resources/fixtures/test-message.txt
TEST_FIXTURE
```

**Note:** in the two `text` blocks containing fixtures, the `# src/...` line is only an **illustrative path comment in the documentation**, not content to copy into the fixture file. Each actual fixture contains only the single line `MAIN_RESOURCE` or `TEST_FIXTURE` (optionally with a trailing newline). For `.properties` files, lines starting with `#` are valid comments.

### 7.4. Test #1: both main and test resources sit on the test classpath

`src/test/java/com/example/classpathlab/ClasspathResourceTest.java`:

```java
package com.example.classpathlab;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class ClasspathResourceTest {

    @Test
    void testRuntimeSeesBothResourceSets() throws IOException {
        assertEquals("MAIN_RESOURCE",
                readRequired("fixtures/public-message.txt"));
        assertEquals("TEST_FIXTURE",
                readRequired("fixtures/test-message.txt"));
    }

    private static String readRequired(String path) throws IOException {
        ClassLoader loader = Thread.currentThread().getContextClassLoader();
        try (InputStream stream = loader.getResourceAsStream(path)) {
            assertNotNull(stream, "Resource not found: " + path);
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8)
                    .strip();
        }
    }
}
```

This is a **plain Java JUnit unit test** with no Spring context startup. It verifies that the build placed both resource sets on the test runtime classpath. `InputStream` works for both loose directory files and files inside a JAR. `strip()` trims only leading/trailing whitespace/newlines so fixtures behave consistently on Windows/Linux; if whitespace is part of the contract, do not `strip()` and compare exact bytes or text instead.

If `test-message.txt` were mistakenly placed under `src/test/java` in a project whose build config only processes `src/test/resources`, the test might fail to find it. Do not assume the IDE will always copy files outside resource directories.

### 7.5. Test #2: test profile alters configuration

`src/test/java/com/example/classpathlab/ProfileConfigTest.java`:

```java
package com.example.classpathlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
@ActiveProfiles("test")
class ProfileConfigTest {
    @Autowired Environment environment;

    @Test
    void usesProfileSpecificTestProperties() {
        assertEquals("test", environment.getProperty("demo.mode"));
    }
}
```

`@SpringBootTest` builds the context using Spring Boot mechanics on the test classpath, while `@ActiveProfiles("test")` makes Spring evaluate `application-test.properties`. Passing this test **does not** prove the file exists in the production artifact.

### 7.6. Test #3: explicit annotation override

`src/test/java/com/example/classpathlab/InlineConfigTest.java`:

```java
package com.example.classpathlab;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(properties = "demo.mode=inline")
@ActiveProfiles("test")
class InlineConfigTest {
    @Autowired Environment environment;

    @Test
    void inlineTestPropertyOverridesProfileFile() {
        assertEquals("inline", environment.getProperty("demo.mode"));
    }
}
```

This test shows that with the same test classpath and same profile, a property can still differ due to an annotation. Use this technique for small, assertion-verified adjustments; avoid stacking so many overrides that the source of a value becomes unclear.

### 7.7. Running tests and packaging

In the directory containing `pom.xml`:

```bash
mvn -q clean test
mvn -q package
jar tf target/classpath-lab-0.0.1-SNAPSHOT.jar
java -jar target/classpath-lab-0.0.1-SNAPSHOT.jar
java -jar target/classpath-lab-0.0.1-SNAPSHOT.jar --spring.profiles.active=test
java -jar target/classpath-lab-0.0.1-SNAPSHOT.jar --demo.mode=cli
```

Interpreting expected results:

| Command / observation | Expected |
| --- | --- |
| `mvn -q clean test` | All three test classes pass assertions; Maven exit code 0 (logs vary by environment) |
| `mvn -q package` | Produces executable JAR; Maven runs tests in the lifecycle before packaging by default |
| `jar tf ...` | Contains `BOOT-INF/classes/application.properties` and `BOOT-INF/classes/fixtures/public-message.txt` |
| `jar tf ...` | Does **not** contain `BOOT-INF/classes/fixtures/test-message.txt` or `BOOT-INF/classes/application-test.properties` from `src/test/resources` |
| `java -jar ...` | Log contains `MODE=main` |
| `java -jar ... --spring.profiles.active=test` | In this example still prints `MODE=main` because the JAR contains no test profile file |
| `java -jar ... --demo.mode=cli` | Log contains `MODE=cli` because the CLI argument overrides the config file |

Conditions: run in a clean project directory with no extra external `application-test.properties`/`application.properties` beside the JAR, and no `DEMO_MODE` env var or system property of the same key. External config sources can alter output via normal override mechanics. To isolate only the `MODE=...` line, filter output in the terminal; do not treat Spring banner/log lines as fixed stdout.

Note: create the `text` fixture contents **exactly as described** (only the value), without copying the path comment line as test data. Once packaged in a JAR, Java reads `fixtures/public-message.txt` by its classpath name at runtime; `src/main/resources` is not a runtime path component.

## 8. Differences also stem from the Spring context, not just resources

Several very common sources of divergence between tests and the packaged app:

### 8.1. Auto-configuration reacts to the classpath

Spring Boot decides many auto-configurations based on **present classes** and **present beans**. When tests add starters or drivers, the context can change:
- H2 test dependency present: embedded database configuration may activate in tests if auto-config conditions match; production lacks H2 and uses another datasource.
- Presence or absence of Spring MVC/WebFlux: the selected web context type can differ. When both are present, Spring Boot follows documented precedence rules.
- Testing libraries or `@MockitoBean`: beans used in tests may be replaced by mocks.
- Slice tests `@WebMvcTest`/`@DataJpaTest` enable only a subset of configuration; `@SpringBootTest` enables more, yet remains affected by the test classpath.

Hence, `@SpringBootTest` "loading the context successfully" is not enough to prove the executable JAR will run with the right profile/driver/config in a container. Whenever behavior depends on PostgreSQL dialect, transactions, brokers, TLS, or native libraries, run integration tests against realistic infrastructure and configuration.

### 8.2. `@TestConfiguration`, unintended bean scanning, and package layout

`@SpringBootTest` normally locates `@SpringBootApplication` by walking up parent packages from the test's package. If a test sits in an unrelated package or multiple root configurations exist, you may need `classes = YourApplication.class`.

You can add test-support beans using a nested `@TestConfiguration` or importing a top-level `@TestConfiguration` in `src/test/java`:

```java
// Illustrative: placed inside a @SpringBootTest class
@TestConfiguration(proxyBeanMethods = false)
static class StubConfiguration {
    @Bean
    ExternalClock externalClock() {
        return () -> java.time.Instant.parse("2026-01-01T00:00:00Z");
    }
}
```

The snippet above **only illustrates the mechanism** and is not a standalone runnable file: `ExternalClock` is an interface the application must define. A nested `@TestConfiguration` augments test configuration; nesting `@Configuration` inside a test can change how Spring Boot picks the root configuration. Top-level test configurations should be imported explicitly and kept from being accidentally picked up by component scanning; never put test stubs inside `src/main/java`.

### 8.3. Properties depending on real environments

Configuration can differ even when the classpath is identical:
- Local test runs have `SPRING_PROFILES_ACTIVE=test` set in the IDE, while CI does not.
- CI has `DATABASE_URL`, `SPRING_DATASOURCE_URL`, `JAVA_TOOL_OPTIONS`, or timezone/locale differing from a developer's laptop.
- Containers mount `/config/application.properties` outside the JAR; external files can override artifact values.
- Testcontainers assigns dynamic ports; hardcoding `localhost:5432` can fail. Use `@DynamicPropertySource` or Spring Boot's supported service connection mechanism, depending on version.
- `@Transactional` test rollback does not mean requests hitting a real web server also roll back: `RANDOM_PORT` runs server-side transactions separate from the client/test thread.

Test environment behavior using the **right context type** and **right infrastructure boundary**. On plain Java unit tests, `@ActiveProfiles` has no effect if no Spring TestContext is started.

## 9. When to use `classpath:`, `file:`, and absolute paths

| Approach | Example | Purpose |
| --- | --- | --- |
| Class loader | `loader.getResourceAsStream("fixtures/order.json")` | Reading fixtures on test classpath or packaged resources |
| Spring resource | `new ClassPathResource("templates/mail.html").getInputStream()` | Reading Spring resources that also works inside a JAR |
| Resource location in annotations | `@Sql("classpath:/sql/seed.sql")` | Locating SQL scripts on the test classpath |
| External file | `Path.of("/etc/myapp/config.json")` | Files outside the JAR that are explicitly deployed/mounted |
| Spring external config | `--spring.config.additional-location=file:./config/` | Loading external configuration via ConfigData rules |

**Do not** do the following for packaged files:
```java
// Fails inside an executable JAR or CI with a different working directory:
var path = java.nio.file.Path.of("src/test/resources/fixtures/order.json");
var text = java.nio.file.Files.readString(path);
```

That file may exist in a source checkout yet not exist inside a container or when running the JAR. Use `getResourceAsStream` for classpath resources; if data genuinely belongs outside the artifact, design an explicit external path and provisioning step.

Another mistake is putting a leading `/` on `ClassLoader#getResourceAsStream`. With a class loader, use `"fixtures/order.json"`; with `Class#getResourceAsStream`, use `"/fixtures/order.json"` to refer to the classpath root.

## 10. Diagnosing errors by symptom

| Symptom | Hypothesis to test | Where to check/fix |
| --- | --- | --- |
| `getResourceAsStream(...) == null` in tests | Wrong folder, wrong casing, skipped `process-test-resources`, path includes `src/...` | Check `target/test-classes`/`build/resources/test` and root-classpath relative path |
| Passes in IDE, fails in Maven/Gradle CI | IDE added resource folders, working directory, or env vars | Run `mvn clean test`/`gradle clean test` in terminal, compare VM options and test tasks |
| Tests read wrong `application.properties` | Same-named file shadowed between main/test or different config import | Separate `application-test.properties`, activate profile, assert keys, inspect property sources |
| `@ActiveProfiles("test")` yet main value persists | `application-test.properties` absent from test classpath; wrong key; higher-precedence override | Inspect `target/test-classes/application-test.properties`, `Environment`, and override sources |
| `java -jar` cannot find fixture | Fixture lives only in `src/test/resources`, not packaged | Check `jar tf`; if app runtime needs it, move to main or provide an external file |
| `ClassNotFoundException` only in production | Runtime-needed dependency declared in `test` or `compileOnly` by mistake | Compare runtime vs. test dependencies; fix scope/configuration |
| `NoSuchMethodError` on CI | Dependency version conflict/classpath ordering | Use dependency tree/`runtimeClasspath` to see which JAR wins |
| Test bean works, production lacks bean | Bean lives only in `src/test/java`/`@TestConfiguration` or test profile | Identify production bean needs and move real definition into main |
| H2 DB tests pass, PostgreSQL fails | Driver/dialect/query/migration environment differences | Test against PostgreSQL Testcontainers with real migrations |
| `getFile()` fails inside executable JAR | Classpath resource resides inside the JAR, not as a regular file | Use `InputStream`, extracting to a temp file if an external API strictly requires `File` |
| Fixture edits do not take effect | Stale resource output, incremental build, or IDE copy missed | Run clean/`process-test-resources`, compare output contents vs. source |
| Passes alone, fails in suite | Global system properties, static state, context cache, shared files | Isolate test data/clocks/properties, avoid global `System.setProperty` |

Minimal debugging workflow:

1. **Identify the failing phase:** test compile, test runtime, dev run, `java -jar`, or container? Each has a different classpath.
2. **Inspect actual outputs:** Maven `target/classes` and `target/test-classes`; Gradle `build/resources/main` and `build/resources/test`. Do not just look at sources.
3. **Inspect the artifact:** `jar tf ...` to see what was packaged; in a Spring Boot executable JAR that is typically `BOOT-INF/classes/...`.
4. **Check the dependency graph:** compare test/runtime configurations; avoid adding libraries blindly.
5. **Verify active configuration:** profiles, external config locations, environment variables, test annotation overrides.
6. **Build the smallest check:** an assertion reading the specific resource or `Environment#getProperty`, instead of immediately enabling DEBUG across the entire app.

When you genuinely need to inspect where a resource is loaded from:

```java
// Place inside a runnable Java method, such as a @Test method.
var loader = Thread.currentThread().getContextClassLoader();
var url = loader.getResource("fixtures/public-message.txt");
System.out.println(url == null ? "NOT_FOUND" : url.toExternalForm());
```

This snippet is **illustrative**: the URL depends on environment and class loader (`file:...` in tests, `jar:...` or another format when run from a JAR), so do not assert a fixed URL string. Print URLs/paths only when they do not expose secrets or tokens.

## 11. Designing test resources for reliable CI and production

### Organization and naming

- Group fixtures under `src/test/resources/fixtures/<feature>/...`; name them after inputs, edge cases, and expected outputs, e.g., `fixtures/orders/invalid-quantity.json`.
- Use UTF-8 consistently; avoid tests depending on default charset, CRLF/LF line endings, or filesystem case sensitivity.
- Never include real passwords, API keys, or customer data in committed fixtures/configs. Use synthetic data and supply secrets via controlled CI/test environment mechanisms.
- Separate test configuration from main configuration so packaged contents stay auditable; resist putting `application-test.properties`, mocks, or test drivers into `src/main/resources` "for convenience."
- When production needs a resource (templates, migrations, JSON schemas), place it in main and have tests read that resource; never keep the only copy in test.
- When multiple modules share fixtures, consider a test-fixtures module/test-jar with dedicated dependency, scope, and version control rather than copying files across modules without a clear contract.
- If Maven resource filtering or Gradle `processTestResources` expansion is enabled, ensure `${...}` strings in JSON/YAML/test fixtures are not accidentally substituted and verify output bytes; with Spring Boot Maven parent, filtering delimiters can differ from plain Maven projects.

### CI and build lifecycle

A practical pipeline:
1. Run `mvn clean test` or `./gradlew clean test` to verify the test runtime classpath from a clean checkout.
2. Run `mvn package` or `./gradlew bootJar` and inspect the produced artifact.
3. For critical smoke tests, run the **packaged artifact** under a deployment-like profile/config; this check is distinct from `@SpringBootTest`.
4. Use containers/emulated infrastructure whenever behavior depends on DBs, brokers, caches, filesystems, hostnames, or permissions.
5. Record reproducible environment details: JDK, plugins, active profiles, runtime args, env, and property sources, without logging secrets.

**Test management note:** `@DirtiesContext`, dozens of distinct `@SpringBootTest(properties=...)` combinations, and changing `@DynamicPropertySource` values can reduce Spring test context cache reuse. Optimize build speed with consistent configurations, without sacrificing isolation or faking infrastructure inaccurately.

## 12. End-of-lesson checklist

Before blaming "Spring Boot" or "CI" for an error, ask yourself:

- [ ] Am I looking at the **test classpath**, **main runtime classpath**, or **packaged artifact**?
- [ ] Does the resource live in `src/main/resources` or `src/test/resources`? Where is the actual output file?
- [ ] Do Java paths start from the **classpath root**, not from the source folder?
- [ ] Are there duplicate-named files across main/test outputs or multiple JARs?
- [ ] Was a runtime-required dependency mistakenly declared as `test`/`testImplementation`/`compileOnly`?
- [ ] Do tests rely on profiles, overrides, beans, mocks, H2, logger config, or test-only resources absent in production?
- [ ] Did I inspect `Environment`/property sources rather than reading just one properties file?
- [ ] Did I inspect artifact contents with `jar tf` and test running `java -jar`/container directly?
- [ ] Are fixtures free of real secrets and independent of absolute paths, encoding, execution order, and working directory?
- [ ] For DB/protocol bugs, did I test against sufficiently production-like infrastructure?

**Core takeaway:** `src/test/resources` supplies resources for **testing**; `src/main/resources` supplies resources for the **application**; `@ActiveProfiles` selects configuration from sources **that are present**; and `java -jar` runs with the **artifact/deployment** classpath and config, without carrying along everything the IDE or test runner saw. Knowing the exact execution phase and resource source leads directly to the root cause instead of random annotation or path guesswork.

## 13. Official references

- Spring Boot 3.5 — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html
- Spring Boot 3.5 — Externalized Configuration: https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html
- Spring Framework — Context Configuration with Test Property Sources: https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html
- Maven — Introduction to the Dependency Mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Maven Surefire — Configuring the Classpath: https://maven.apache.org/surefire/maven-surefire-plugin/examples/configuring-classpath.html
- Maven Resources — resources:testResources: https://maven.apache.org/plugins/maven-resources-plugin/testResources-mojo.html
- Gradle — Testing in Java & JVM projects: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Building Java & JVM projects: https://docs.gradle.org/current/userguide/building_java_projects.html
