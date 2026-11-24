# Controlling Command-Line Arguments and Startup Properties by Version

## 1. Lesson objectives

In Spring Boot, an application can receive configuration at startup from **command-line arguments**, **Java system properties**, **environment variables**, **configuration files**, or **properties declared directly on a test**. These sources can share the same property name while carrying **different precedence**. Spring TestContext and `@SpringBootTest` provide mechanisms to control inputs for a single `ApplicationContext` initialization in tests.

This lesson focuses on two questions:

1. How do you control the **raw arguments `SpringApplication` receives**, in order to test code relying on `ApplicationArguments`, `ApplicationRunner`, or `CommandLineRunner`?
2. How do you control the **effective property values in `Environment`**, in order to test beans initialized via `@Value`, `@ConfigurationProperties`, profiles, and startup settings?

Beyond syntax, you need to recognize **Spring Boot version differences**. Specifically, the `args` attribute on `@SpringBootTest` was added in **Spring Boot 2.2.0**, and `useMainMethod` was added in **Spring Boot 3.0.0**. Examples using Boot 3.x APIs cannot be pasted verbatim into a Boot 2.1.x project.

After this lesson, you will be able to:

- Distinguish `--key=value` options, `--flag` options, and non-option arguments.
- Write tests verifying both `ApplicationArguments` and actual values in `Environment`.
- Use `@SpringBootTest(args = ...)`, `@SpringBootTest(properties = ...)`, `@TestPropertySource`, and `@ActiveProfiles` properly.
- Explain why test properties can beat command-line properties while `ApplicationArguments` preserves the original arguments.
- Understand the effect of `useMainMethod` and version-specific `SpringApplication` settings.
- Run equivalent tests from IDE/Gradle/Maven/CI and investigate mismatches caused by sources, timing, or context caching.

**Scope:** modern Java 17+ Spring Boot projects, primarily Boot 3.x/4.x. Compatibility notes cover Boot 1.x/2.x; always verify APIs and dependencies against the exact version your project uses. Never assume an attribute exists in every version simply because a modern online example uses it.

## 2. Three kinds of "startup parameters" that are easily confused

### 2.1. Application arguments — program arguments

When running a packaged JAR:

```bash
java -jar app.jar --demo.mode=fast --demo.retries=3 --feature.flag input.csv
```

Everything **after `app.jar`** is passed as arguments to `main(String[] args)` and forwarded to `SpringApplication.run(..., args)` if `main` forwards them.

- `--demo.mode=fast` and `--demo.retries=3` are **option arguments with values**.
- `--feature.flag` is an **option argument present without a value**.
- `input.csv` is a **non-option argument** (positional argument).

When the application is launched by `SpringApplication` under default behavior, Spring Boot parses these arguments into `ApplicationArguments`. Option names (e.g., `demo.mode`) **omit the `--` prefix** when calling `getOptionValues("demo.mode")`.

By default, options of the form `--key=value` are also added by Spring Boot to `Environment` as a property source with higher priority than config files and Java system properties, though tests may introduce **test property sources** with even higher priority.

### 2.2. Java system properties — JVM parameters

Compare:

```bash
java -Ddemo.mode=from-jvm -jar app.jar --demo.mode=from-cli
```

- `-Ddemo.mode=from-jvm` **precedes `-jar`**: sets a Java system property on the JVM.
- `--demo.mode=from-cli` **follows the JAR name**: is an application argument parsed by `SpringApplication`.
- Without test overrides, `Environment.getProperty("demo.mode")` normally yields `from-cli` because command-line properties outrank Java system properties.
- `System.getProperty("demo.mode")` still returns `from-jvm`: it reads Java system properties directly, **without performing Spring property-source resolution**.

Do not write `java -jar app.jar -Ddemo.mode=from-jvm` expecting a JVM system property: after the JAR name, that token is passed as a **program argument**, not interpreted by the JVM as `-D` before startup.

### 2.3. OS environment variables — process environment

For instance, setting `DEMO_MODE=from-env` in the environment before launching the app. Spring Boot supports **relaxed binding** for property names, though conversion rules, hyphens, and complex structures depend on the property source type. For a simple test key `demo.mode`, the environment representation is typically `DEMO_MODE`.

**Distinction:**

- OS environment variables belong to the **process environment**.
- Java system properties belong to the **JVM**.
- Application arguments belong to the application's **raw argument array**.
- Spring `Environment` is the mechanism that **merges and resolves properties** from multiple sources in precedence order.

Do not use these three terms interchangeably in documentation, tests, or CI.

## 3. Two perspectives: `ApplicationArguments` and `Environment`

A test can read **the same key** in two ways and receive two different values—completely by design.

| API | Answers the question | Example |
|---|---|---|
| `ApplicationArguments.getSourceArgs()` | Which raw argument strings launched the application? | Array `["--demo.mode=fast", "input.csv"]` |
| `containsOption("demo.mode")` | Did this option appear in args? | `true` or `false` |
| `getOptionValues("demo.mode")` | With what values did the option appear? | `List.of("fast")` |
| `getNonOptionArgs()` | What are the positional arguments? | `List.of("input.csv")` |
| `Environment.getProperty("demo.mode")` | What is the **effective** property value after resolution? | Can be `from-test` even if CLI passed `fast` |
| `@Value("${demo.mode}")` | What effective property does a bean receive on injection? | Per `Environment`/placeholder resolution |
| `@ConfigurationProperties` | How does a group of properties bind to a strongly typed object? | Binds `demo.retries` as an integer |

### 3.1. Exact semantics of `getOptionValues`

Per the `ApplicationArguments` API:

- **Option absent:** `getOptionValues("missing") == null`.
- **Option present without `=value`:** returns an **empty list**.
- **Option with one value:** returns a single-element list.
- **Option repeated multiple times:** list can contain multiple values matching the occurrences.

Example:

```text
--demo.mode=alpha --demo.mode=beta --feature.flag report.csv
```

You can expect `getOptionValues("demo.mode")` to contain `["alpha", "beta"]`, `containsOption("feature.flag")` to be `true`, `feature.flag`'s value to be an empty list, and `getNonOptionArgs()` to contain `"report.csv"`.

**Do not equate** an option present without a value with an absent option; those two cases differ. And when an option has multiple values, do not assume `Environment.getProperty(...)` exposes the same `List<String>` shape as `ApplicationArguments`; pick the specific binding/parsing approach you need.

### 3.2. Non-option arguments do not become properties automatically

`report.csv` appears in `getNonOptionArgs()`, yet it **is not equivalent to** `--report.file=report.csv` and does not create property `report.file`. If the app requires a file via property, design a clean CLI contract or handle positional arguments explicitly in an `ApplicationRunner`.

### 3.3. Which runner receives which argument form?

Two common Spring Boot interfaces:

```java
public interface ApplicationRunner {
    void run(ApplicationArguments args) throws Exception;
}

public interface CommandLineRunner {
    void run(String... args) throws Exception;
}
```

These are **illustrative API signatures**, not two standalone runnable source files.

- `ApplicationRunner` receives parsed `ApplicationArguments`.
- `CommandLineRunner` receives the raw `String` argument array.
- Both runner types typically execute after the application starts cleanly. In a `@SpringBootTest` running `SpringApplication`, runners can execute during context startup; tests must ensure runner side effects are isolated.
- Never create an `ApplicationRunner` just to check whether `Environment` read a property; inject `Environment` directly in the test.

## 4. Capability matrix by Spring Boot version

| Spring Boot branch | Notable APIs / points | Compatibility notes |
|---|---|---|
| **1.4.x–2.1.x** | Has `@SpringBootTest` and `properties/value` | **No `@SpringBootTest(args=...)` yet**; to test parsing, use `DefaultApplicationArguments` or build/run a context intentionally |
| **2.2.x–2.3.x** | `@SpringBootTest(args=...)` added in **2.2.0** | Check project dependencies/JUnit engine; `useMainMethod` not yet available |
| **2.4.x–2.7.x** | Still has `args`; Spring Boot **Config Data API** significantly changed loading `application.*`, config imports/locations | File configs from Boot pre-2.4 may need adjustments; `useMainMethod` still unavailable |
| **3.0.x and later** | `useMainMethod` added in **3.0.0**; `args` and `properties` remain | Spring Boot 3 requires Java 17+; check `NEVER/WHEN_AVAILABLE/ALWAYS` choices |
| **4.x** | Verify API/Javadoc and starters/modules on the chosen branch | Do not assume Boot 2/3 test dependencies and layouts match Boot 4 identically |

**Relying solely on the Boot version to pick APIs is not enough.** JUnit Jupiter, Spring Framework, Maven Surefire/Gradle test tasks, and Java toolchains must also align. If the IDE suggests an annotation attribute while Maven/Gradle reports "cannot find symbol," verify **the actual resolved dependencies** and check which Spring Boot branch the build uses.

### 4.1. Directly evidenced version milestones

The `@SpringBootTest` Javadoc documents:

- `args(): String[]` — **Since 2.2.0**.
- `useMainMethod(): SpringBootTest.UseMainMethod` — **Since 3.0.0**, default value **`NEVER`**.

Thus on Boot 2.1, writing `@SpringBootTest(args = {"--mode=test"})` is not "wrong behavior"—simply **the API does not exist**. Likewise, `useMainMethod = ...` will not compile on Boot 2.x.

## 5. Property precedence: why are args present yet overridden?

Spring Boot merges property sources into `Environment`. Per Externalized Configuration docs on modern Boot branches, when two sources share a key, the higher-precedence source determines the effective value.

**A common low-to-high ordering for keys with the same name:**

1. Default properties (e.g., `SpringApplication.setDefaultProperties(...)`).
2. Application configuration sources such as `application.properties` or `application.yaml`, including profile-specific files and appropriate config data locations.
3. OS environment variables.
4. Java system properties.
5. Spring Boot command-line option properties (by default).
6. Test properties declared via `@SpringBootTest(properties = ...)`.
7. Dedicated test overrides such as `@TestPropertySource`/`@DynamicPropertySource` per corresponding Spring rules and versions.

This condensed list covers **this lesson's practical scenarios**, omitting JNDI, servlet init params, `SPRING_APPLICATION_JSON`, and devtools. When combining multiple high-precedence overrides at once, consult documentation for your exact Spring Boot/Spring Framework branch and avoid relying on unverified orderings. The hands-on exercise only uses pairs with clear precedence relationships: `@SpringBootTest(properties)` **beats** command-line properties; `@TestPropertySource(properties)` **beats** the same-named property in `@SpringBootTest`.

### 5.1. Intentional conflict example

Suppose:

- `application-test.properties`: `demo.mode=from-profile-file`.
- Args: `--demo.mode=from-cli`.
- Annotation: `@SpringBootTest(properties = "demo.mode=from-boot-test")`.

When the test asserts:

```java
assertEquals("from-boot-test",
        environment.getProperty("demo.mode"));

assertEquals(List.of("from-cli"),
        arguments.getOptionValues("demo.mode"));
```

Both are **correct**: `Environment` reflects the effective value **after precedence**, while `ApplicationArguments` reflects the raw CLI input. Never "fix" the test by changing `ApplicationArguments`'s expected value to `from-boot-test`.

### 5.2. `@SpringBootTest(properties)` does not create CLI args

If you only declare:

```java
@SpringBootTest(properties = "demo.mode=from-test")
class PropertiesOnlyTest {
}
```

you **cannot conclude** `ApplicationArguments.containsOption("demo.mode")` will return `true`. The property is added only to the test `Environment`; it is not a token in the `args` array. This distinction matters when a service reads config from two paths: one via `@Value/Environment`, another via `ApplicationArguments`.

### 5.3. `@TestPropertySource` and `@DynamicPropertySource`

- `@TestPropertySource(locations = "classpath:/startup-test.properties")` loads test properties from a resource via Spring TestContext.
- `@TestPropertySource(properties = "demo.mode=inline-test")` defines key/value pairs directly; inlined entries normally outrank resource locations in the same annotation.
- `@DynamicPropertySource` fits when values are only known **after test resources are created**, such as a random Testcontainers port. It has its own precedence influenced by Spring Framework/test bootstrapper version.
- `@ActiveProfiles("test")` is an explicit way to activate `application-test.properties` for Spring integration tests rather than depending on whatever profile happens to be set locally.

When testing a simple value, **never stack all three annotations** on the same key "just to be sure"—that obscures test intent and complicates diagnosis. Only combine multiple sources on the same key when the test **intentionally demonstrates precedence**, as in Section 6.

## 6. Complete Java 17+ example: verifying raw args and effective properties

The following example uses Spring Boot 3.x, Java 17+, JUnit Jupiter, and `spring-boot-starter-test`. It **needs no Docker, database, HTTP server, or mocks**, directly inspecting the boundary between `ApplicationArguments` and `Environment`.

### 6.1. File layout

```text
src/
├── main/
│   └── java/com/example/testing/arguments/
│       └── ArgumentsDemoApplication.java
└── test/
    ├── java/com/example/testing/arguments/
    │   └── StartupArgumentsTest.java
    └── resources/
        └── application-test.properties
```

Place the files exactly as shown; Java packages match the directory paths.

### 6.2. Spring Boot application

**File `src/main/java/com/example/testing/arguments/ArgumentsDemoApplication.java`:**

```java
package com.example.testing.arguments;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ArgumentsDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ArgumentsDemoApplication.class, args);
    }
}
```

This class is the standard entry point. No runner with side effects and no database-backed services are present. In the test below, `@SpringBootTest` by default **does not invoke `main` directly**, yet uses Spring Boot's test bootstrapper to build the context with the specified args.

### 6.3. Profile-specific property file

**File `src/test/resources/application-test.properties`:**

```properties
demo.mode=from-profile-file
demo.count=1
demo.origin=from-profile-file
demo.source=from-profile-file
```

This file is a **test resource**, so the test runtime loads it on the classpath. It is not packaged into the production JAR by default. `@ActiveProfiles("test")` below activates the `test` profile and causes `application-test.properties` to be loaded per Config Data rules.

### 6.4. Complete test suite

**File `src/test/java/com/example/testing/arguments/StartupArgumentsTest.java`:**

```java
package com.example.testing.arguments;

import java.util.Arrays;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.core.env.Environment;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.context.TestPropertySource;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(
    classes = ArgumentsDemoApplication.class,
    webEnvironment = SpringBootTest.WebEnvironment.NONE,
    args = {
        "--demo.mode=from-cli",
        "--demo.count=7",
        "--feature.flag",
        "report.csv"
    },
    properties = {
        "demo.mode=from-boot-test",
        "demo.origin=from-boot-test"
    }
)
@ActiveProfiles("test")
@TestPropertySource(properties =
        "demo.origin=from-test-property-source")
class StartupArgumentsTest {

    @Autowired
    ApplicationArguments arguments;

    @Autowired
    Environment environment;

    @Value("${demo.mode}")
    String injectedMode;

    @Test
    void exposesOriginalApplicationArguments() {
        assertArrayEquals(new String[] {
            "--demo.mode=from-cli",
            "--demo.count=7",
            "--feature.flag",
            "report.csv"
        }, arguments.getSourceArgs());

        assertTrue(arguments.containsOption("demo.mode"));
        assertTrue(arguments.containsOption("demo.count"));
        assertTrue(arguments.containsOption("feature.flag"));
        assertFalse(arguments.containsOption("not-present"));

        assertEquals(List.of("from-cli"),
                arguments.getOptionValues("demo.mode"));
        assertEquals(List.of("7"),
                arguments.getOptionValues("demo.count"));

        // Option present without a value.
        assertEquals(List.of(),
                arguments.getOptionValues("feature.flag"));

        // Option completely absent.
        assertNull(arguments.getOptionValues("not-present"));

        // Token not starting with "--".
        assertEquals(List.of("report.csv"),
                arguments.getNonOptionArgs());
    }

    @Test
    void testPropertySourcesOverrideCliForEnvironment() {
        // @SpringBootTest(properties) beats CLI property.
        assertEquals("from-boot-test",
                environment.getProperty("demo.mode"));
        assertEquals("from-boot-test", injectedMode);

        // No annotation override for demo.count.
        assertEquals("7",
                environment.getProperty("demo.count"));

        // @TestPropertySource beats same-named property
        // declared by @SpringBootTest(properties).
        assertEquals("from-test-property-source",
                environment.getProperty("demo.origin"));

        // Key present only in application-test.properties.
        assertEquals("from-profile-file",
                environment.getProperty("demo.source"));
    }

    @Test
    void profileAndArgumentsRemainDistinct() {
        assertTrue(Arrays.asList(
                environment.getActiveProfiles()).contains("test"));

        String originalCliValue =
                arguments.getOptionValues("demo.mode").get(0);
        String effectiveEnvironmentValue =
                environment.getProperty("demo.mode");

        assertEquals("from-cli", originalCliValue);
        assertEquals("from-boot-test",
                effectiveEnvironmentValue);
        assertNotEquals(originalCliValue,
                effectiveEnvironmentValue);
    }
}
```

**Expected result:** the class has **3 `@Test` methods**; all three pass in a Spring Boot 3.x project set up as described. They intentionally print no stdout. Output formatting for `BUILD SUCCESSFUL`, Surefire summaries, or IDE reports varies by build tool and version, so verify test counts and statuses rather than relying on a fixed log string.

### 6.5. Test dependencies and running

Gradle Groovy DSL example, assuming the project already has the Spring Boot plugin, repositories, and dependency management configured:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

Maven example: with a Spring Boot parent or BOM managing versions, declare the corresponding dependencies:

```xml
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
```

These snippets are **not complete build files**; avoid duplicating dependencies if the project already includes them. For Spring Boot 4.x, check the starter names and module layout in the 4.x documentation before copying Boot 3 config.

Run from the directory containing the project's wrapper:

```bash
# Gradle:
./gradlew test --tests "com.example.testing.arguments.StartupArgumentsTest"

# Or Maven Surefire:
./mvnw -Dtest=StartupArgumentsTest test
```

On Windows PowerShell, use `.\gradlew.bat test --tests "com.example.testing.arguments.StartupArgumentsTest"` or `.\mvnw.cmd "-Dtest=StartupArgumentsTest" test`.

**Note:** the commands above **select which test to run**. They do not pass `"--demo.mode=from-cli"` from the terminal into the test. The application arguments are specified by `@SpringBootTest(args = ...)` **right inside the test source**. That ensures IDE and CI feed the exact same test input, independent of what the user types at the command prompt.

### 6.6. Execution flow explained

1. JUnit Platform discovers `StartupArgumentsTest`.
2. Spring Boot TestContext loads the application class and configures the context with `@ActiveProfiles("test")`.
3. `@SpringBootTest(args=...)` supplies four raw tokens to the `SpringApplication` bootstrap process.
4. Spring Boot builds `ApplicationArguments` with parsed option/non-option values; this holds the raw input.
5. Boot adds command-line option properties to `Environment` per default behavior.
6. Test property sources such as `@SpringBootTest(properties)` and `@TestPropertySource` participate in resolution according to their precedence; effective `demo.mode` becomes `from-boot-test`, not `from-cli`.
7. `@Value("${demo.mode}")` injects from the effective value, receiving `from-boot-test`.
8. The three tests verify **raw arguments**, **resolution outcomes**, and **profiles plus the divergence between the two views**.

There is no contradiction when `arguments.getOptionValues("demo.mode")` holds `from-cli` while `environment.getProperty("demo.mode")` returns `from-boot-test`: that is the deliberate point of the test.

## 7. Choosing how to pass inputs based on test goals

### 7.1. Testing what a parser/runner receives in args

Choose `@SpringBootTest(args = { ... })` when the test genuinely needs to verify how Spring Boot processes input tokens, for example:

- The app has an `ApplicationRunner` reading `getNonOptionArgs()` to pick a file.
- A startup task branches on `arguments.containsOption("dry-run")`.
- A command-line option is converted into an `Environment` property.
- A component reacts to flag presence/absence, distinguishing flags from boolean values.

Illustrative snippet in a test class on Boot 2.2+:

```java
@SpringBootTest(args = {"--job.name=import", "--dry-run"})
class ImportJobArgumentsTest {
}
```

This is **not a standalone example**. It only shows the annotation setup; running requires an application class and test methods. `--dry-run` is a flag **without a value**. When business rules expect an explicit boolean property, `--dry-run=true` binds more cleanly via `@ConfigurationProperties`; never assume every empty flag automatically turns into boolean `true` across all binding mechanisms.

### 7.2. Testing a bean reading a property with a specific value

Choose `@SpringBootTest(properties = "app.retry.max-attempts=2")` when the goal is effective configuration rather than simulating exact CLI tokens.

```java
@SpringBootTest(properties = {
    "app.retry.max-attempts=2",
    "app.remote.enabled=false"
})
class RetryConfigurationTest {
}
```

This decouples the test from CLI parsing. Tests should still assert behavioral outcomes or bound bean values rather than merely checking that the context starts.

### 7.3. Choosing a test profile instead of typing many properties every time

For related settings such as mock datasources, logging, or brokers, put them in `src/test/resources/application-test.properties` or `application-test.yaml` and use:

```java
@ActiveProfiles("test")
@SpringBootTest
class TestProfileIntegrationTest {
}
```

`application-test.*` is profile-specific Config Data; `@ActiveProfiles` belongs to Spring TestContext. They are easier to manage when many tests share context settings, and usually cleaner than an annotation stuffed with dozens of string literals.

### 7.4. Dynamic values from test infrastructure

With Testcontainers, database ports are usually known only after the container starts. Use the dynamic mechanism supported by your framework/version (e.g., `@DynamicPropertySource` in Spring TestContext) instead of hard-coding `jdbc:...:5432` in `args`. This reduces CI port collisions. If you need to verify **CLI overrides**, put that in a separate test without accidentally adding a same-named dynamic property that obscures the effective source.

## 8. `useMainMethod`: a critical change since Spring Boot 3.0

### 8.1. Does `@SpringBootTest` always invoke `main`?

**No.** By default, `@SpringBootTest` does not directly call `main(String[] args)` on the application class; the framework builds the context using its test bootstrapper. This spares tests from side effects or customizations inside `main`, yet also means **configuration applied only inside `main` is not executed**.

Example production `main` with:

```java
public static void main(String[] args) {
    SpringApplication app =
            new SpringApplication(ArgumentsDemoApplication.class);
    app.setAdditionalProfiles("batch");
    app.setDefaultProperties(
            java.util.Map.of("demo.mode", "from-main-default"));
    app.run(args);
}
```

This is an **illustrative snippet to replace `main`'s body in an existing app**, not a standalone source file. It shows how programmatic customizations can be skipped when tests bypass `main`. Do not use the `batch` profile to replace `@ActiveProfiles("test")` everywhere; it is merely a customization example.

### 8.2. The three modes of `SpringBootTest.UseMainMethod`

Since **Spring Boot 3.0.0**, you can specify:

| Value | Meaning |
|---|---|
| `NEVER` | **Default:** do not use the `main` method to create the test application |
| `WHEN_AVAILABLE` | Use `main` when a suitable `main` method is found; otherwise use the normal mechanism |
| `ALWAYS` | Require using `main`; if no suitable `main` exists, bootstrapping cannot satisfy the requirement |

Example when testing **actual customizations inside `main`**:

```java
@SpringBootTest(
    classes = ArgumentsDemoApplication.class,
    args = "--demo.mode=from-cli",
    useMainMethod = SpringBootTest.UseMainMethod.WHEN_AVAILABLE
)
class MainMethodCustomizationTest {
}
```

This is a **configuration snippet**, not a self-running test. If `main` configures `SpringApplication` in a special way, `WHEN_AVAILABLE` can reproduce that behavior. Still, check for side effects: startup listeners, runners, application events, banners, proxies, and additional profiles. Do not turn on `ALWAYS` for every test just because "it looks more like production"; minimal configurations are often faster and more accurate.

**On Boot 2.x:** `useMainMethod` does not exist. If you must verify logic currently configured only in `main`, extract that configuration into a testable bean/utility, or write a full-application startup test using the API available in your Boot branch. Never copy Boot 3 annotations and randomly hack imports.

## 9. Toggling conversion of command-line args into `Environment` properties

By default, `SpringApplication` adds `--key=value` options into `Environment`. Sometimes an application wants to **keep args for `ApplicationRunner` while preventing CLI options from overriding configuration**. Spring Boot provides:

```java
SpringApplication app =
        new SpringApplication(ArgumentsDemoApplication.class);
app.setAddCommandLineProperties(false);
app.run(args);
```

**This code belongs in `main` or wherever you control `SpringApplication`**, not as a standalone Java snippet. With this setting:

- Arguments are still passed to the application and visible via `ApplicationArguments` under the matching bootstrapper.
- However, `--demo.mode=...` options are not automatically added as a property source in `Environment`.
- `Environment.getProperty("demo.mode")` may come from Java system properties, OS env, config files, or other test overrides.
- If `@SpringBootTest` uses the default `useMainMethod = NEVER`, customizations applied only in `main` **do not automatically apply** in tests. Check the bootstrapper or use `useMainMethod` in Boot 3.0+ when testing `main` customizations.

Do not equate **disabling command-line properties** with **clearing the args array**. Those are two independent behaviors.

## 10. "Very early" startup properties: not every property source arrives in time

Certain keys affect **how configuration itself is selected and loaded**, so they must be present from the very beginning; classic examples are:

- `spring.config.name` — changes the base name of config files.
- `spring.config.location` — replaces default locations where Boot looks for config data.
- `spring.config.additional-location` — adds locations beyond defaults.

Per Spring Boot documentation, these keys must be set **very early** in `Environment`, typically via CLI args, JVM system properties, or OS environment variables. `@PropertySource` on a `@Configuration` class can run **too late** to affect config file discovery and certain `logging.*`/`spring.main.*` options.

Example running a packaged app:

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:./test-config/ \
  --demo.mode=from-cli
```

Linux/macOS shell syntax; on Windows, use a single line or PowerShell line-continuation syntax. The example assumes `./test-config/` exists or is permitted to be absent via `optional:`.

**Be careful in tests:** do not assume setting any startup-critical key through a test annotation is identical to passing it at **process start**. Bootstrap/test property setup timing varies across versions. When verifying Config Data discovery and loading, write an integration test that genuinely bootstraps the application with the chosen configuration source using version-appropriate APIs, and inspect loaded property sources.

### 10.1. Differences in Spring Boot before and after 2.4

Spring Boot **2.4** introduced the new Config Data mechanism. Older guides handling profiles/config locations in Boot 2.3 and earlier may not match `spring.config.import`, profile activation, and location group logic in newer Boot. When testing early startup properties, consult documentation for your exact Boot branch and set up files/sources explicitly instead of extrapolating from examples written for another version.

### 10.2. `@TestPropertySource` is not a YAML loader by default

`@TestPropertySource(locations = "...")` traditionally reads `.properties` resources. In newer Spring Framework versions, you can supply a custom `PropertySourceFactory` for other formats, yet **do not assume a `.yaml` file will be read like Spring Boot Config Data** simply by writing `@TestPropertySource("classpath:/app-test.yaml")`.

To use an `application-test.yaml` profile config, prefer **Spring Boot Config Data + `@ActiveProfiles("test")`**. When a simple test property resource is all you need, `.properties` is the most predictable choice.

## 11. Comparing runs across IDE, Gradle, Maven, and CI

Controlling **application** CLI args differs from arguments passed to the **build tool**.

### 11.1. Four distinct execution paths

| Run method | Where do arguments go? | Meaning |
|---|---|---|
| `java -jar app.jar --demo.mode=cli` | `SpringApplication` args of the **real app**, if `main` forwards them | Tests runtime bootstrap |
| IDE → Run application, **Program arguments** | The application's `main(String[] args)` array | Mirrors `java -jar` |
| IDE → Run JUnit test | JUnit runner launches the test; `@SpringBootTest(args=...)` supplies app args inside the test | Not the same as typing args into app `main` |
| `./gradlew test ...` or `./mvnw test` | Arguments configuring the **test task/goal** | Do not automatically become `SpringApplication` args |

Example:

```bash
./gradlew test --tests "com.example.testing.arguments.StartupArgumentsTest"
```

The `--tests` option selects the Gradle test class/method; **it is not** `--demo.mode=...` sent to Spring Boot `ApplicationArguments`.

Likewise, Maven Surefire's `-Dtest=StartupArgumentsTest` selects the test class, not application `ApplicationArguments`.

### 11.2. JVM arguments in separate test tasks/forks

Gradle and Maven can run tests in a **forked JVM** separate from the build tool process:

- `./gradlew -Ddemo.mode=from-gradle test` sets the property on the Gradle JVM; **do not assume** it is automatically forwarded verbatim to the test execution JVM.
- Gradle's `Test` task has its own `systemProperty(...)`, `jvmArgs(...)`, and environment-passing configuration.
- Maven Surefire has `systemPropertyVariables`, `argLine`, and fork settings. Maven user properties can interact with plugins, yet you must check the plugin/version rather than assuming `-D...` equals app CLI args.
- IDE JUnit runners have their own **VM options** and **environment variables**. When the IDE delegates test execution to Gradle, the Gradle task configuration may take precedence.

Gradle example (inside `build.gradle`):

```groovy
tasks.named('test', Test) {
    useJUnitPlatform()
    systemProperty 'demo.mode', 'from-test-jvm'
}
```

This is an **additional snippet inside a valid build file**, not a standalone project. In the Section 6 test, `demo.mode` is still overridden in `Environment` by `@SpringBootTest(properties = "demo.mode=from-boot-test")`. So never change the test's expected value from `from-boot-test` to `from-test-jvm` merely because the task defines a system property.

### 11.3. Running the application itself via the build tool

In the Gradle Spring Boot plugin, `bootRun` launches the real app—completely different from `test`:

```bash
./gradlew bootRun --args="--demo.mode=from-cli"
```

This snippet assumes the project uses the Spring Boot Gradle plugin and `bootRun` supports `--args`. It passes arguments to the application when launched via `bootRun`, **and does not make `@SpringBootTest` in a test class automatically read those values**.

With Maven, the Spring Boot plugin can also configure arguments for the `spring-boot:run` goal, though exact syntax and support depend on the plugin version. Do not swap Gradle's `--args` flag into Maven or vice versa.

### 11.4. What should CI record?

In CI, record:

- Java version, Spring Boot version, Gradle/Maven Wrapper version, and resolved test dependencies.
- Actual tasks/goals/modules/test filters invoked.
- Active profiles and **names** of config sources, without printing secrets.
- Executed, skipped, and failed test counts, reports, and stack traces on context startup errors.
- Necessary environment variables—prefer names/sources or non-sensitive values.

If CI is red while your IDE is green, reproduce via the wrapper first and inspect the **test JVM**, **source precedence**, and **test context cache** rather than tweaking assertions to fit one environment before finding the root cause.

## 12. Profile configuration and the boundary between test context and app runtime

### 12.1. `@ActiveProfiles` keeps test environments isolated

If the goal is loading `application-test.properties`, put `@ActiveProfiles("test")` on integration tests. This expresses intent clearly and avoids relying on whatever default profile happens to be active on a developer machine.

**Do not treat**:

```text
@ActiveProfiles("test")
```

as shorthand for:

```text
--spring.profiles.active=test
```

Both can yield similar active profiles in some scenarios, yet **bootstrap paths, configuration sources, and test-context interactions** differ. When a test must prove CLI-driven profile activation at startup, write a dedicated CLI test and inspect the actual context.

### 12.2. Watch out for profiles set in `main`

If production `main` calls `setAdditionalProfiles("staging")` while tests use default `@SpringBootTest` without invoking `main`, `staging` will not appear in tests. Boot 3.0+ adds `useMainMethod = WHEN_AVAILABLE/ALWAYS` to change that. Even so, enabling `main` can trigger unwanted startup customizations in unit/integration tests, so use it only when genuinely needed.

### 12.3. Keys should have clear, unambiguous names

Prefer structured keys such as:

```properties
app.import.enabled=false
app.import.batch-size=100
app.remote.timeout=5s
```

Spring Boot Binder maps these to `@ConfigurationProperties(prefix = "app.import")`, converting types (`boolean`/`int`/`Duration`) as supported. Avoid generic keys like `mode` or `timeout` shared across multiple subsystems, because conflicts among args, env vars, and default configs become hard to trace.

For structured settings, `@ConfigurationProperties` is usually clearer and easier to verify than a scattering of individual `@Value` fields; still, this lesson focuses on **startup sources and precedence**.

## 13. Context caching and test independence

Spring TestContext Framework caches `ApplicationContext` instances to reduce startup cost. Test configurations such as property overrides, profiles, and context customizers contribute to the **cache key**; therefore two test classes with different startup settings normally do not share the exact same context.

### 13.1. Do not change `@SpringBootTest(args)` across individual test methods

`@SpringBootTest(args=...)` is declared at the **class level**; within a class, test methods normally share the built context. If each method needs a different set of args, split them into separate test classes or use an explicit bootstrap mechanism rather than trying to mutate `ApplicationArguments` on an existing context.

Also never assume "run test method A first, mutate a system property, and test method B will get the new startup value"; beans have already been constructed and binding may have already run. Changing a property source after bootstrap **does not automatically recreate beans**.

### 13.2. Do not abuse `System.setProperty`

Dangerous pattern:

```java
@Test
void changesGlobalProperty() {
    System.setProperty("demo.mode", "temporary");
    // This test never restores state ...
}
```

**Anti-pattern snippet**, not recommended practice. Java system properties are JVM-wide state that can leak into other tests or cause races under parallel execution. Prefer test annotations, explicit configuration sources, or extensions/resources that manage and restore values in `finally` if mutating global state is truly unavoidable.

Likewise, avoid mutating OS environment variables during tests as a general strategy: the JVM offers no standard safe API to alter process environment variables independently per test.

### 13.3. When should you use `@DirtiesContext`?

`@DirtiesContext` forces Spring to evict a context from the cache when a test leaves it unsafe for reuse. It is **not** the default way to reload args/properties for every method. When test inputs truly need to differ, separate test classes/configurations are cleaner; never use `@DirtiesContext` to mask state leakage.

### 13.4. Startup side effects are real

If an application has an `ApplicationRunner` calling an external service, running `@SpringBootTest` can trigger that code on context startup. To keep tests reproducible:

- Extract runner logic into a separately testable service and mock the I/O port in appropriate tests.
- Use a property like `app.startup-job.enabled=false` to disable unrelated work in tests, and cover the enabled branch in a dedicated fixture test.
- Never hit a production database or send real HTTP requests just to verify how a flag is parsed.
- For pure argument-string parsing logic, consider unit testing `DefaultApplicationArguments` instead of booting a full Spring context.

## 14. Lightweight parser testing without a Spring context

If you only need to verify token parsing, you can use Spring Boot's `DefaultApplicationArguments` with JUnit **without starting a context**.

Example **test method** inside a JUnit Jupiter class with the Spring Boot dependency:

```java
@Test
void parsesOptionsWithoutStartingSpring() {
    ApplicationArguments args = new DefaultApplicationArguments(
            "--job.name=import",
            "--dry-run",
            "orders.csv");

    assertTrue(args.containsOption("dry-run"));
    assertEquals(List.of(), args.getOptionValues("dry-run"));
    assertEquals(List.of("import"),
            args.getOptionValues("job.name"));
    assertEquals(List.of("orders.csv"),
            args.getNonOptionArgs());
}
```

Requires importing `org.springframework.boot.ApplicationArguments`, `org.springframework.boot.DefaultApplicationArguments`, `org.junit.jupiter.api.Test`, and JUnit assertions; this is a **snippet inside a test class**, not a standalone file.

**Limitation:** this test only verifies `ApplicationArguments` parsing. It **does not** verify that `SpringApplication` added command-line properties to `Environment`, does not instantiate `@ConfigurationProperties` beans, and does not prove `main` customizations work. Use a properly scoped Spring Boot integration test for those goals.

## 15. Troubleshooting common issues by symptom

| Symptom | Likely cause | Investigation / fix |
|---|---|---|
| Annotation lacks `args` attribute | Spring Boot **pre-2.2** or wrong resolved test dependency | Check version; upgrade appropriately or use parser tests/explicit bootstrap |
| Annotation lacks `useMainMethod` | Spring Boot **pre-3.0** | Remove attribute; extract `main` customization or plan controlled upgrade |
| `ApplicationArguments.getOptionValues(...)` returns `null` | Option absent from args, or lookup name misspelled | Check `getSourceArgs()` and option name without `--` |
| `getOptionValues("flag")` returns an empty list | Flag present without `=value` | Usually expected behavior; use `containsOption` to test presence |
| `Environment` differs from `ApplicationArguments` | Same key overridden by test property source or higher-priority source | Check `@SpringBootTest(properties)`, `@TestPropertySource`, and resolved properties |
| Test ignores `application-test.properties` | `test` profile inactive or resource in wrong directory | Add `@ActiveProfiles("test")`, place file in `src/test/resources` |
| JVM `-Dfoo=bar` does not update bean in test | `@SpringBootTest(properties)` overrides it; or `-D` only reached Gradle/Maven JVM | Check effective `Environment` and forked test JVM |
| `@SpringBootTest(args)` skips `main` customizations | Default `useMainMethod=NEVER` | On Boot 3+, consider `WHEN_AVAILABLE` if test must go through `main` |
| Command-line option missing from `Environment` | `setAddCommandLineProperties(false)` or custom bootstrap; malformed token | Inspect `SpringApplication` config and source args |
| Boot 2.3 vs. 2.4 loads config differently | Config Data API changed config data/profile/location logic | Follow docs for exact version, inspect property sources |
| Test passes alone, fails in suite | Leaked global system property, static state, context cache, or runner side effect | Isolate fixtures, drop global mutations, check cache |
| IDE green, CI red | Different JDK/dependencies/profiles/OS env/test runner | Run via wrapper, compare task/goal and effective properties |
| `Could not resolve placeholder` error | Missing property, wrong profile, source loaded too late, or typo | Check actual sources, key name, and load timing |
| `spring.config.location` has no effect | Set too late via `@PropertySource` or wrong path | Pass early via appropriate source, verify Config Data version |
| Only verifies context loads, not args | Assertions do not measure inputs/behavior | Assert `ApplicationArguments` and concrete bean/`Environment` outcomes |

### 15.1. Step-by-step root cause tracing

1. **Confirm versions** via dependency resolution / actual Spring Boot version; verify `args`/`useMainMethod` APIs first.
2. **Confirm execution mode:** real packaged app, IDE JUnit runner, Gradle test task, Maven Surefire, or `SpringBootTest` bootstrap.
3. **Inspect/compare raw args** in a safe test environment: `ApplicationArguments.getSourceArgs()`, option names, non-option args.
4. **Check effective values:** `Environment.getProperty("...")` and actual values injected/bound into beans.
5. **Find overriding sources:** profile files, OS env, Java system props, CLI, `@SpringBootTest.properties`, `@TestPropertySource`, dynamic overrides.
6. **Check early properties and `main` customizations:** some settings must load early; default tests skip `main`.
7. **Check caching/side effects:** was global state mutated, did a runner perform real I/O, are tests running in parallel or reusing a cached context?
8. **Re-run via the wrapper** targeting the exact module and test scope; read the test report rather than just seeing the build command exit 0.

**Tip:** Spring Boot Actuator's `env` and `configprops` endpoints (when enabled, secured, and authorized) help trace property/binding sources. In tests, you can inspect `ConfigurableEnvironment.getPropertySources()` to see active sources—only for safe test keys, never printing secrets or full environments into CI logs.

## 16. Security when controlling command-line arguments

Command-line args frequently show up in process listings, startup logs, shell history, and CI configs. Therefore:

- Never pass access tokens, passwords, private keys, or real secrets via `--secret=...` just for easy test setup.
- Prefer a secret manager, CI protected/masked environment variables, or your organization's approved secure config mechanism.
- Log only **names** of sensitive variables or masked values; tests should never snapshot full `ApplicationArguments.getSourceArgs()` into unrestricted artifacts.
- Examples `demo.mode`, `demo.count`, and `feature.flag` here use dummy values with zero sensitive information.

A test failing due to a missing secret must never be "fixed" by committing a secret into `application-test.properties`. Design dummy fixtures or use managed test-environment secrets.

## 17. Practice exercises and answers

### Exercise A — Pick the right mechanism

You want to test a service reading `app.retry.max-attempts` via `@ConfigurationProperties`, without caring which CLI tokens a user typed. Should you use `@SpringBootTest(properties="app.retry.max-attempts=2")` or `args="--app.retry.max-attempts=2"`?

**Hint:** prefer `properties` since the goal is the effective value with less coupling to CLI parsing. However, if the business requirement is "users passing CLI flags can override the config file," write a dedicated test with `args` and **do not declare a higher-precedence test property with the same key**.

### Exercise B — Predict arguments and `Environment`

Given:

```java
@SpringBootTest(
    args = {"--demo.mode=cli", "report.csv"},
    properties = "demo.mode=inline-test")
class StartupTest {
}
```

Assuming no other test source overrides `demo.mode`, what are the right values?

1. `arguments.getOptionValues("demo.mode")`
2. `arguments.getNonOptionArgs()`
3. `environment.getProperty("demo.mode")`

**Answer:** `List.of("cli")`, `List.of("report.csv")`, and `"inline-test"`, respectively. `@SpringBootTest(properties)` outranks command-line properties while raw args remain intact.

### Exercise C — Recognize a valueless flag

You receive `args = {"--dry-run"}`. Compare:

```java
assertTrue(arguments.containsOption("dry-run"));
assertEquals(List.of(),
        arguments.getOptionValues("dry-run"));
assertNull(arguments.getOptionValues("missing"));
```

These assertions capture three distinct states: flag present, flag present without a value, and option absent.

### Exercise D — Capabilities by version

A project uses Spring Boot **2.1.x** and Java 8; a sample snippet uses `@SpringBootTest(args = "--job=sync", useMainMethod = ALWAYS)`. Why won't it compile?

**Answer:** `args` requires Boot **2.2+**; `useMainMethod` requires Boot **3.0+**, and Boot 3 requires Java 17+. You cannot conjure those APIs by adding JUnit 5 or importing an enum. Test `DefaultApplicationArguments` without starting a context, or plan a controlled upgrade before using the newer annotation attributes.

### Exercise E — Ignored `main` configuration

The application's `main` calls `setAddCommandLineProperties(false)`, yet the test uses default `@SpringBootTest(args = "--demo.mode=cli")`. Is the test's `Environment` guaranteed to ignore CLI?

**Answer:** **not guaranteed / do not assume so.** Tests default to `useMainMethod=NEVER` on Boot 3+, so if `main` is the only place disabling CLI properties, that customization may not execute. Configure the right bootstrap scope—such as `useMainMethod=WHEN_AVAILABLE` in Boot 3+—and verify both `ApplicationArguments` and `Environment`.

## 18. Final test-verification checklist

- [ ] Verified exact **Spring Boot version**, Java toolchain, and test dependencies.
- [ ] Know that `@SpringBootTest(args)` exists since **2.2.0** and `useMainMethod` since **3.0.0**.
- [ ] Distinguished JVM `-D`, OS env vars, Java application args, and Spring `Environment`.
- [ ] Know `--key=value`, `--flag`, and positional arguments carry distinct semantics.
- [ ] Checked `getOptionValues` returns `null` when absent and an empty list for a valueless flag.
- [ ] Did not use `@SpringBootTest(properties)` as a stand-in for raw `ApplicationArguments`.
- [ ] Did not expect `ApplicationArguments` to change when overridden by test property sources.
- [ ] Know property resolution prioritizes test overrides over CLI and config files on matching keys.
- [ ] Used `@ActiveProfiles`/test resources instead of relying on uncontrolled local profiles.
- [ ] Understand default tests skip `main`; enable `useMainMethod` only when testing `main` customizations.
- [ ] Placed config-location/early properties in early sources so they take effect on time.
- [ ] Did not pass Gradle/Maven test runner flags expecting them to become application CLI args.
- [ ] Avoided mutating system properties/global state causing order-dependent tests.
- [ ] Kept per-class args/configs clear when relying on context caching.
- [ ] Never wrote real secrets into args, test files, logs, or CI artifacts.
- [ ] Tests assert inputs and behavior, not merely `assertNotNull(context)`.
- [ ] Verified test counts, detailed failures, and consistent results across IDE/CLI/CI.

## 19. Conclusion

**Command-line arguments** are the raw input tokens passed to the application; **startup properties** are the effective values after merging multiple `PropertySource`s. Spring Boot Test lets you control both separately via `@SpringBootTest(args)` and `@SpringBootTest(properties)`, while `@TestPropertySource`/`@ActiveProfiles` manage test configuration with clearer intent. Hence an app can receive `--demo.mode=cli` while beans see `demo.mode=from-boot-test`—the expected outcome when test overrides take precedence.

To keep tests trustworthy, **choose APIs that exist in your actual version**, know whether the test bootstrap invokes `main`, respect early-loading property timing, and assert **both raw arguments and effective configuration** whenever both are part of the contract.

## Official references

- [Spring Boot Javadoc — SpringBootTest (3.4 branch)](https://docs.spring.io/spring-boot/3.4/api/java/org/springframework/boot/test/context/SpringBootTest.html): `args` since Boot 2.2.0, `useMainMethod` since Boot 3.0.0, `properties`, and `webEnvironment`.
- [Spring Boot — Testing Spring Boot Applications](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html): Using Application Arguments, Testing With a Mock Environment, Using the Main Method.
- [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html): property-source order, command-line properties, config files, early bootstrap keys, and relaxed binding.
- [Spring Boot Javadoc — ApplicationArguments](https://docs.spring.io/spring-boot/api/java/org/springframework/boot/ApplicationArguments.html): option names/values, non-option args, and source args.
- [Spring Framework — Test Property Sources](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/ctx-management/property-sources.html): `@TestPropertySource`, resource locations, precedence, and inheritance.
- [Spring Boot — Spring Boot 2.2 Release Notes](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.2-Release-Notes): context behind changes between Boot 2.1 and Boot 2.2.