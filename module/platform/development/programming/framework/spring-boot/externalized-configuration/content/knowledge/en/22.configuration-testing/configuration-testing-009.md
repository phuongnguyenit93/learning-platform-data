# Testing Real Precedence, Imports, and File Locations via `SpringApplication` — Spring Boot 3.3

## 1. Why Test Configuration with a Real Startup?

In Spring Boot, configuration values can come from many places: `application.properties` or YAML on the classpath, files outside the JAR, profile-specific files, environment variables, Java system properties, command-line arguments, documents imported via `spring.config.import`, and application-added sources.

An example:

```properties
lab252.mode=base
```

in `application.properties`, while an imported file states:

```properties
lab252.mode=imported
```

and the startup command passes:

```bash
java -jar app.jar --lab252.mode=cli
```

What is the final value? Just opening each file does not provide complete proof of **real loading and precedence behavior**. You must verify: was the file actually loaded, did the import resolve relative to the right location, which profile is active, was a location replaced, and is a higher-priority source present?

Therefore, this lesson builds tests that **actually invoke `SpringApplication.run(...)`**, create temporary configuration files, and read the effective values from `ConfigurableApplicationContext#getEnvironment()`.

This belongs to the **Configuration Testing** group in **Spring Boot Externalized Configuration**. Examples use **Java 17+**, **Spring Boot 3.3.x**, **JUnit 5**, Maven or Gradle, and **AssertJ**.

### Learning Outcomes

After this lesson, you will be able to:

1. Explain why an `Environment` test assembling `PropertySource`s manually does not prove Config Data really works.
2. Start a minimal application via `SpringApplication` inside a test and close the context cleanly.
3. Use `@TempDir` to create isolated `.properties` files and directories per test.
4. Verify whether default classpath files are read.
5. Prove `spring.config.location` **replaces** default search locations.
6. Prove `spring.config.additional-location` **adds** locations while preserving defaults and overriding values.
7. Verify `spring.config.import`, relative imports, multiple imports, and optional imports.
8. Verify CLI arguments outrank Config Data.
9. Verify profile-specific files and location groups using `,` vs. `;`.
10. Distinguish "reading the right final value" from "binding the right type" or "passing validation."
11. Diagnose errors from missing files, bad locations, inactive profiles, and differing working directories.
12. Avoid non-isolated tests, polluting system properties, or mistaking `@TestPropertySource` for Config Data processing.

> Focus on **behavioral proof at startup**. Claiming "source A ought to beat source B" is not enough unless you know which sources Spring Boot actually loaded.

## 2. Four Layers to Test Separately

A configuration test can touch four layers:

| Layer | Question | Appropriate proof |
| --- | --- | --- |
| Search locations | Did Spring Boot find and load this file? | Start with temp file and assert a key that exists only in that file |
| Imports | Was the imported file actually loaded with expected precedence? | Root and imported files share a key with different values |
| Precedence | CLI, system property, environment, config data: which wins? | Assert `Environment#getProperty()` when multiple sources set the same key |
| Binding and validation | Does the final value convert to Java models and satisfy constraints? | Assert `@ConfigurationProperties` beans and startup failure cases |

In this lesson, we prioritize the first three layers. The fourth is illustrated to prevent drawing false conclusions from string-only checks.

Diagram:

```text
Minimal @SpringBootConfiguration
                |
                v
        SpringApplication.run(...)
                |
                v
       Config Data is processed
        |         |          |
      search     import    profiles
        |         |          |
        +---------+----------+
                  |
                  v
         MutablePropertySources
                  |
                  v
       Spring Environment resolver
                  |
                  v
       getProperty("lab252.mode")
                  |
                  v
              Assertion
```

`SpringApplication.run(...)` executes Spring Boot bootstrap, letting you observe real Config Data behavior. A simple `MockEnvironment` does not run those steps on its own.

## 3. Spring Boot 3.3 Rules That Tests Must Prove

According to the Spring Boot 3.3 Reference, configuration sources follow a well-defined precedence order. Below is a simplified diagram of common sources, **from highest priority to lowest**:

```text
SpringApplication command-line properties
                |
                v
JVM Java system properties running the app
                |
                v
OS environment variables
                |
                v
Config Data
                |
                v
SpringApplication default properties
```

In practice, there are also `SPRING_APPLICATION_JSON`, test property sources, JNDI, servlet parameters, devtools settings, and custom sources. In tests, control your inputs rather than assuming the simplified diagram covers every possible source.

Inside **Config Data**, additional rules apply:

- `application.properties`/YAML on the classpath.
- Profile-specific files such as `application-prod.properties`.
- Files outside the JAR.
- Files imported via `spring.config.import`.
- Additional locations and replacement locations.
- Location ordering and location groups.
- Multi-document configuration files and profile activation.
- Optional files using the `optional:` prefix.

The following inputs are particularly important:

| Input | Meaning |
| --- | --- |
| `spring.config.name` | Changes the base filename searched in directories |
| `spring.config.location` | Replaces default search locations |
| `spring.config.additional-location` | Adds locations alongside default locations |
| `spring.config.import` | Imports additional config data from files or other locations |
| `optional:` | Permits a location to be missing in supported cases |
| `spring.profiles.active` | Activates profiles, affecting profile-suffixed file selection |
| `,` in location lists | Separates locations in precedence order |
| `;` in location lists | Groups locations at the same priority level for profile resolution |

Properties like `spring.config.location`, `spring.config.name`, and `spring.config.additional-location` are read by Spring Boot **very early**. When testing them, pass them directly as `SpringApplication.run(...)` arguments, Java system properties, or environment variables; do not rely on a source added after Config Data has already run.

## 4. Why Choose `SpringApplication` Instead of Only `@SpringBootTest`?

`@SpringBootTest` is great for testing a real application context. However, a test that needs to **change where configuration files are searched** on each test case may need direct control over startup arguments.

Example:

```java
SpringApplication app = new SpringApplication(TestApplication.class);
app.setWebApplicationType(WebApplicationType.NONE);

try (ConfigurableApplicationContext context = app.run(
        "--spring.config.location=file:/somewhere/application.properties")) {

    assertThat(context.getEnvironment().getProperty("lab252.mode"))
            .isEqualTo("external");
}
```

Here `run(...)` runs Spring Boot startup and lets the test specify a real loadable location.

Comparing approaches:

| Approach | Best when | Limitations to remember |
| --- | --- | --- |
| Unit test with `MockEnvironment` | Testing `PropertySource` handling in your own code | Does not run full Config Data bootstrap |
| `ApplicationContextRunner` | Testing beans, auto-configuration, conditions | Do not assume it simulates full `SpringApplication` Config Data locations/imports |
| `@SpringBootTest` | Integration testing an app under one configuration set | Context caching and test overrides make varying startup locations less direct |
| `SpringApplication.run` | Testing discovery/search/import/precedence at startup | Requires managing contexts, global inputs, and temp files |

No single tool is "best for all tests." We pick `SpringApplication` here because the goal is **verifying the real Config Data startup pipeline**, not checking a manually injected Java value.

### What Must Be Isolated?

- Each test's configuration files.
- File and directory paths.
- Startup arguments.
- System properties or environment variables modified intentionally by a test.
- Opened and closed ApplicationContexts.
- Test resource files on the classpath.
- Active profiles and default properties.
- External side effects such as network calls, databases, and server ports.

Every test should run quickly, avoid external services, and never depend on random files on a developer's machine.

## 5. Preparing the Test Project

Maven example with Spring Boot 3.3.x dependency management:

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

`spring-boot-starter-test` normally supplies JUnit Jupiter, AssertJ, and Spring Boot testing utilities matching your Boot version.

Gradle Groovy DSL:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Gradle Kotlin DSL:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.test {
    useJUnitPlatform()
}
```

You do not need Spring Web or a database just to test configuration precedence. To avoid launching an embedded web server, the examples set:

```java
app.setWebApplicationType(WebApplicationType.NONE);
```

### Suggested Directory Structure

```text
config-precedence-lab/
├── pom.xml
└── src/
    ├── main/
    │   └── java/
    │       └── example/
    │           └── configlab/
    │               └── ConfigLabApplication.java
    └── test/
        ├── java/
        │   └── example/
        │       └── configlab/
        │           └── ConfigDataStartupTest.java
        └── resources/
            └── application.properties
```

`ConfigLabApplication` can be a normal Spring Boot application. The test uses a minimal inner configuration class to keep unrelated components out of scope.

## 6. Creating a Baseline Default File with Distinguishable Markers

In `src/test/resources/application.properties`:

```properties
lab252.packaged-only=present-in-classpath
lab252.shared=from-classpath
lab252.mode=classpath-mode
```

This test resource serves as a **baseline** for comparisons:

- Without changing locations, we expect `lab252.packaged-only` to be present.
- When pointing `spring.config.location` directly to an external file, we expect this marker **not to be loaded from default classpath locations**.
- When using `spring.config.additional-location`, the classpath marker remains while the shared key `lab252.shared` is overridden by the additional file.

Using prefix `lab252` instead of generic names like `test.value` reduces accidental interference from unrelated files or environment variables.

**Note:** files under `src/test/resources` sit on the **test classpath**, not inside the production JAR. That makes them ideal for testing classpath Config Data during test runs without copying them into `src/main/resources`.

## 7. Minimal Startup Class for Tests

In `ConfigDataStartupTest.java`, declare a nested class:

```java
@SpringBootConfiguration(proxyBeanMethods = false)
static class MinimalApplication {
}
```

`@SpringBootConfiguration` is a Spring Boot configuration annotation sufficient as a primary source for starting a minimal context.

A helper method:

```java
private static ConfigurableApplicationContext start(String... arguments) {
    SpringApplication application =
            new SpringApplication(MinimalApplication.class);

    application.setWebApplicationType(WebApplicationType.NONE);
    application.setBannerMode(Banner.Mode.OFF);
    application.setLogStartupInfo(false);

    return application.run(arguments);
}
```

Required imports:

```java
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
```

Key points:

- `new SpringApplication(...)` builds the bootstrap coordinator.
- `run(arguments)` receives arguments just like a real application launch.
- `SpringApplication` still runs `Environment` preparation and Config Data loading.
- `WebApplicationType.NONE` avoids starting an HTTP server.
- Disabling the banner and startup info keeps test logs clean.
- `try-with-resources` closes the context after assertions so no resources leak across tests.

Do not replace this helper with `new StandardEnvironment()` expecting imported files to load automatically. `StandardEnvironment` alone does not run Boot's Config Data pipeline.

## 8. Using `@TempDir` for Real Yet Machine-Independent Files

JUnit Jupiter provides:

```java
@TempDir
Path tempDir;
```

This field receives a temporary directory managed by JUnit per test instance.

UTF-8 write helper:

```java
private static Path write(Path file, String content)
        throws IOException {

    Files.createDirectories(file.getParent());
    Files.writeString(file, content, StandardCharsets.UTF_8);
    return file;
}
```

Imports:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.io.TempDir;
```

Example:

```java
Path config = write(
        tempDir.resolve("external/application.properties"),
        "lab252.shared=external\n");
```

The file is created on the real filesystem. From `Path` you can obtain a URI:

```java
String location = config.toUri().toString();
```

A URI typically looks like:

```text
file:///tmp/junit-xyz/external/application.properties
```

or on Windows:

```text
file:///C:/Users/.../Temp/.../external/application.properties
```

Using `Path.toUri()` avoids manually concatenating `file:` with Windows backslashes `\` or unescaped characters.

**Never hardcode a fixed temp filename in the working directory** shared across tests editing the same `application.properties`. That causes cross-test interference and order-dependent failures.

## 9. Test 1 — Classpath `application.properties` Is Loaded

When calling `start()` **without custom locations**, Spring Boot searches default locations.

Example:

```java
@Test
void loadsClasspathApplicationProperties() {
    try (ConfigurableApplicationContext context = start()) {
        assertThat(context.getEnvironment()
                .getProperty("lab252.packaged-only"))
                .isEqualTo("present-in-classpath");

        assertThat(context.getEnvironment()
                .getProperty("lab252.shared"))
                .isEqualTo("from-classpath");
    }
}
```

Here `src/test/resources/application.properties` sits on the test classpath.

Expected outcome:

```text
lab252.packaged-only = present-in-classpath
lab252.shared        = from-classpath
```

What this proves: Spring Boot bootstrap found and loaded the classpath file into `Environment` during a standard test startup.

What this **does not** prove: how external files override it, how relative imports resolve, or whether profile-specific files are read. Each scenario needs its own test.

## 10. Test 2 — `spring.config.location` Replaces Default Locations

Create an external file:

```properties
lab252.shared=from-explicit-location
lab252.external-only=present
```

and run:

```java
@Test
void explicitLocationReplacesDefaultSearchLocations()
        throws IOException {

    Path external = write(
            tempDir.resolve("replacement/application.properties"),
            "lab252.shared=from-explicit-location\n"
            + "lab252.external-only=present\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + external.toUri())) {

        ConfigurableEnvironment environment =
                context.getEnvironment();

        assertThat(environment.getProperty("lab252.shared"))
                .isEqualTo("from-explicit-location");

        assertThat(environment.getProperty("lab252.external-only"))
                .isEqualTo("present");

        assertThat(environment.getProperty("lab252.packaged-only"))
                .isNull();
    }
}
```

This is a presence/absence check:

- `lab252.external-only` proves the external file loaded.
- Absence of `lab252.packaged-only` proves the default classpath file **was no longer loaded via default search locations** once replaced by the explicit location.

Do not assert only `lab252.shared=from-explicit-location`: a shared key would still be overridden even if classpath had also loaded. Separate markers prove **replacement**, not just precedence.

### Does `spring.config.location` Accept Files or Directories?

A file:

```text
file:/path/application.properties
```

is loaded directly (if present).

A directory:

```text
file:/path/config/
```

is treated by Boot as a folder searched using `spring.config.name`; directory locations must end with `/`.

The example above intentionally uses a **file location**, avoiding assumptions about which basename gets appended to a directory.

## 11. Test 3 — `spring.config.additional-location` Keeps Defaults and Adds External Files

Create file:

```properties
lab252.shared=from-additional
lab252.external-only=from-additional
```

Then:

```java
@Test
void additionalLocationKeepsDefaultsAndOverridesSharedKey()
        throws IOException {

    Path external = write(
            tempDir.resolve("additional/application.properties"),
            "lab252.shared=from-additional\n"
            + "lab252.external-only=from-additional\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.additional-location="
            + external.toUri())) {

        ConfigurableEnvironment environment =
                context.getEnvironment();

        assertThat(environment.getProperty("lab252.packaged-only"))
                .isEqualTo("present-in-classpath");

        assertThat(environment.getProperty("lab252.external-only"))
                .isEqualTo("from-additional");

        assertThat(environment.getProperty("lab252.shared"))
                .isEqualTo("from-additional");
    }
}
```

Both sets of markers appear:

- The classpath marker proves default files still loaded.
- The external marker proves the additional file also loaded.
- The `shared` key takes its value from the additional file, demonstrating it overrides default configuration here.

**Key distinction:**

```text
spring.config.location
    -> replaces default locations

spring.config.additional-location
    -> preserves default locations and adds more
```

Without unique markers per source, looking only at `lab252.shared` makes it hard to tell those two behaviors apart.

## 12. Test 4 — Command-Line Arguments Beat Config Data

Create an external file:

```properties
lab252.mode=from-file
```

Also pass a CLI option:

```java
@Test
void commandLineOverridesConfigFile() throws IOException {
    Path config = write(
            tempDir.resolve("cli/application.properties"),
            "lab252.mode=from-file\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + config.toUri(),
            "--lab252.mode=from-cli")) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.mode"))
                .isEqualTo("from-cli");
    }
}
```

By default, `SpringApplication` converts `--name=value` options into a command-line property source, which outranks Config Data files.

This differs from calling:

```java
System.getProperty("lab252.mode")
```

Java system properties may be absent or hold something else; `Environment` is where you observe **the final value after Spring combines sources**.

### What If Command-Line Properties Are Disabled?

`SpringApplication` provides:

```java
application.setAddCommandLineProperties(false);
```

When called, `--lab252.mode=...` arguments are still passed to the application, yet **are not added to the Spring Environment** as a command-line property source.

Therefore, tests must state their assumptions clearly: these tests rely on `SpringApplication`'s **default configuration**, without calling `setAddCommandLineProperties(false)`.

## 13. Test 5 — `spring.config.import` Loads Another File and Beats the Declaring File

Suppose a directory contains:

```text
import-case/
├── application.properties
└── shared.properties
```

`application.properties`:

```properties
spring.config.import=shared.properties
lab252.value=from-root
lab252.root-only=present
```

`shared.properties`:

```properties
lab252.value=from-import
lab252.import-only=present
```

Under Spring Boot Config Data, imported documents are registered per import rules and **override** values from the declaring document.

Test:

```java
@Test
void importedFileOverridesDeclaringFile() throws IOException {
    Path dir = tempDir.resolve("import-case");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=shared.properties\n"
            + "lab252.value=from-root\n"
            + "lab252.root-only=present\n");

    write(
            dir.resolve("shared.properties"),
            "lab252.value=from-import\n"
            + "lab252.import-only=present\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri())) {

        ConfigurableEnvironment environment =
                context.getEnvironment();

        assertThat(environment.getProperty("lab252.value"))
                .isEqualTo("from-import");

        assertThat(environment.getProperty("lab252.root-only"))
                .isEqualTo("present");

        assertThat(environment.getProperty("lab252.import-only"))
                .isEqualTo("present");
    }
}
```

This test confirms **both files participated**, while the overlapping key is resolved from the import.

### Why Can `shared.properties` Omit `file:`?

The value:

```properties
spring.config.import=shared.properties
```

is an **import-relative location**, resolved relative to the file declaring the import.

In this example, root lives inside `import-case`, so `shared.properties` is resolved right beside root.

If you write:

```properties
spring.config.import=file:/absolute/path/shared.properties
```

that is a **fixed location**, independent of the declaring file's location.

## 14. Test 6 — Multi-Level Imports Are Relative to Each Declaring File

Structure:

```text
nested/
├── application.properties
└── child/
    ├── child.properties
    └── next/
        └── deep.properties
```

`application.properties`:

```properties
spring.config.import=child/child.properties
lab252.depth=root
```

`child/child.properties`:

```properties
spring.config.import=next/deep.properties
lab252.depth=child
```

`child/next/deep.properties`:

```properties
lab252.depth=deep
```

Test:

```java
@Test
void nestedImportsResolveRelativeToDeclaringDocument()
        throws IOException {

    Path dir = tempDir.resolve("nested");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=child/child.properties\n"
            + "lab252.depth=root\n");

    write(
            dir.resolve("child/child.properties"),
            "spring.config.import=next/deep.properties\n"
            + "lab252.depth=child\n");

    write(
            dir.resolve("child/next/deep.properties"),
            "lab252.depth=deep\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri())) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.depth"))
                .isEqualTo("deep");
    }
}
```

If the engine tried resolving **every** relative import against the shell's working directory, level two would look in the wrong place. Spring Boot Config Data resolves import-relative locations relative to the **document containing the import declaration**.

This is another reason to use temporary directories with explicit paths: tests never depend on the IDE's or CI's current directory.

## 15. Test 7 — Multiple Imports: Later Listed Files Win

`application.properties`:

```properties
spring.config.import=first.properties,second.properties
lab252.level=root
```

`first.properties`:

```properties
lab252.level=first
```

`second.properties`:

```properties
lab252.level=second
```

In Spring Boot 3.3, imports are processed in declared order, with later imports overriding earlier ones.

Test:

```java
@Test
void laterImportHasHigherPrecedence()
        throws IOException {

    Path dir = tempDir.resolve("several-imports");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=first.properties,second.properties\n"
            + "lab252.level=root\n");

    write(
            dir.resolve("first.properties"),
            "lab252.level=first\n");

    write(
            dir.resolve("second.properties"),
            "lab252.level=second\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri())) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.level"))
                .isEqualTo("second");
    }
}
```

**Do not confuse import order with line order inside a single file.** Within one document, placing `spring.config.import` at the top or bottom does not make that file's keys outrank imported data. Config Data rules govern imports rather than "whichever line appears later."

### What About Importing the Same File Multiple Times?

Spring Boot loads each corresponding import source once. Do not repeat identical imports trying to force overrides. If a test must verify duplicate imports, point two declarations to the same resource and check source count and effective values instead of assuming the file applies twice.

## 16. Test 8 — Optional Imports and Missing Files

In real deployments, an extra file may exist only in certain environments—for example, `local-overrides.properties` absent in production or absent on a developer machine.

You can write:

```properties
spring.config.import=optional:local-overrides.properties
lab252.value=base
```

If the imported file does not exist, the application still starts.

Test:

```java
@Test
void optionalMissingImportDoesNotFailStartup()
        throws IOException {

    Path dir = tempDir.resolve("optional-import");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=optional:missing.properties\n"
            + "lab252.value=base\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri())) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.value"))
                .isEqualTo("base");
    }
}
```

Important: `optional:` only changes handling of **missing locations/files**; it does not silently ignore an existing file that contains broken `.properties` or YAML syntax.

### When Removing `optional:`

```properties
spring.config.import=missing.properties
```

Spring Boot fails startup with a Config Data location/resource-not-found exception.

A test can assert:

```java
@Test
void requiredMissingImportFailsStartup()
        throws IOException {

    Path dir = tempDir.resolve("required-import");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=missing.properties\n"
            + "lab252.value=base\n");

    assertThatThrownBy(() -> start(
            "--spring.config.location=" + root.toUri()))
            .isInstanceOf(RuntimeException.class);
}
```

This asserts at the **startup failure** level. For stricter root-cause checking, inspect the cause chain for the specific Config Data exception type, while avoiding brittle assertions on exact error message wording that may change across patches.

### `spring.config.on-not-found=ignore`

Spring Boot also offers a broader setting for handling missing Config Data locations. Avoid applying a blanket "ignore all missing files" policy that masks a **required** production file. When only one file is optional, putting `optional:` on that specific location is much clearer.

## 17. Test 9 — Profile-Specific Files Beat Base Files

Create:

```text
profiles/
├── application.properties
└── application-prod.properties
```

Base file:

```properties
lab252.color=base
```

Profile file:

```properties
lab252.color=prod
```

Test:

```java
@Test
void profileSpecificPropertiesOverrideBase()
        throws IOException {

    Path dir = tempDir.resolve("profiles");

    Path root = write(
            dir.resolve("application.properties"),
            "lab252.color=base\n");

    write(
            dir.resolve("application-prod.properties"),
            "lab252.color=prod\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri(),
            "--spring.profiles.active=prod")) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.color"))
                .isEqualTo("prod");
    }
}
```

With `spring.profiles.active=prod`, Boot finds the matching profile-suffixed file and lets it override the base file.

**Do not manually call `Files.readString` on the profile file and inject properties into Environment.** The test's purpose is letting Config Data discover the profile variant and verifying the result.

### What If Multiple Profiles Are Active?

With `spring.profiles.active=prod,live`, the general rule is that **later profiles override earlier ones** within the same location group.

Do not turn that into a blanket claim that **every `live` file always beats every `prod` file across all locations**, because location groups affect precedence as well.

## 18. Test 10 — Directory Locations and `spring.config.name`

`spring.config.location` can accept a directory. When given a directory, Spring Boot appends basenames from `spring.config.name` to search for configuration files.

Suppose a directory contains:

```text
custom-name/
└── settings.properties
```

If you set:

```text
spring.config.name=settings
spring.config.location=file:/.../custom-name/
```

Boot loads `settings.properties`.

Test:

```java
@Test
void directoryLocationUsesSpringConfigName()
        throws IOException {

    Path dir = tempDir.resolve("custom-name");
    Files.createDirectories(dir);

    write(
            dir.resolve("settings.properties"),
            "lab252.named=settings-file\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.name=settings",
            "--spring.config.location=" + dir.toUri())) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.named"))
                .isEqualTo("settings-file");
    }
}
```

`Path.toUri()` on an existing directory yields a URI with a trailing slash. Distinguish:

```text
file:/some/config/
```

which is a directory location, from:

```text
file:/some/config/application.properties
```

which is a file location.

### Pitfall: Passing a Directory Without a Trailing Slash

Spring Boot requires directories in `spring.config.location` to end with `/` so it knows the target is a directory. If concatenating `file:` strings or building URIs manually, verify trailing slashes and path escaping.

In programmatic tests, call `Files.createDirectories(dir)` before `dir.toUri()` and never tweak the resulting URI string manually.

## 19. Test 11 — Multiple Locations: Later Listed Locations Override Earlier Ones

Create:

```text
locations/
├── base/
│   └── application.properties
└── override/
    └── application.properties
```

`base/application.properties`:

```properties
lab252.region=base
```

`override/application.properties`:

```properties
lab252.region=override
```

Test:

```java
@Test
void laterLocationCanOverrideEarlierLocation()
        throws IOException {

    Path base = tempDir.resolve("locations/base");
    Path override = tempDir.resolve("locations/override");

    Files.createDirectories(base);
    Files.createDirectories(override);

    write(base.resolve("application.properties"),
            "lab252.region=base\n");

    write(override.resolve("application.properties"),
            "lab252.region=override\n");

    String locations = base.toUri() + "," + override.toUri();

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + locations)) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.region"))
                .isEqualTo("override");
    }
}
```

Commas separate locations in precedence order. Here the later location overrides matching keys from the earlier location.

**Location precedence is not alphabetical by folder name** when listed explicitly. Unlike certain wildcard patterns, list position matters.

### Strengthening the Test When Needed

Beyond the overlapping key, give each file a unique marker to prove both loaded:

```properties
lab252.base-only=yes
```

and:

```properties
lab252.override-only=yes
```

Asserting both markers alongside the shared value verifies both **presence** and **precedence** instead of just one final value.

## 20. Test 12 — Location Groups: Commas vs. Semicolons

This is an advanced case that is very easy to misunderstand.

Per Spring Boot 3.3 documentation:

- Commas `,` separate locations across **different priority levels**.
- Semicolons `;` combine locations into **a single group** so profiles resolve together at the same priority level.

Suppose there are two directories:

```text
groups/
├── cfg/
│   └── application-live.properties
└── ext/
    └── application-prod.properties
```

`cfg/application-live.properties`:

```properties
lab252.variant=cfg-live
```

`ext/application-prod.properties`:

```properties
lab252.variant=ext-prod
```

Activate:

```properties
spring.profiles.active=prod,live
```

### Case A: Comma

```text
spring.config.location=file:/.../cfg/,file:/.../ext/
```

Boot processes locations in order, where files under `ext` outrank files under `cfg`.

With the files above, expect:

```text
lab252.variant=ext-prod
```

### Case B: Semicolon

```text
spring.config.location=file:/.../cfg/;file:/.../ext/
```

Both locations belong to the same group. Within that group, profiles resolve in `prod,live` order; `live` applies after `prod` and wins.

Expected:

```text
lab252.variant=cfg-live
```

### Testing Both Cases

```java
@Test
void commaAndSemicolonCanChangeProfilePrecedence()
        throws IOException {

    Path cfg = tempDir.resolve("groups/cfg");
    Path ext = tempDir.resolve("groups/ext");
    Files.createDirectories(cfg);
    Files.createDirectories(ext);

    write(cfg.resolve("application-live.properties"),
            "lab252.variant=cfg-live\n");

    write(ext.resolve("application-prod.properties"),
            "lab252.variant=ext-prod\n");

    String commaLocations = cfg.toUri() + "," + ext.toUri();
    String groupedLocations = cfg.toUri() + ";" + ext.toUri();

    try (ConfigurableApplicationContext comma = start(
            "--spring.config.location=" + commaLocations,
            "--spring.profiles.active=prod,live")) {

        assertThat(comma.getEnvironment()
                .getProperty("lab252.variant"))
                .isEqualTo("ext-prod");
    }

    try (ConfigurableApplicationContext grouped = start(
            "--spring.config.location=" + groupedLocations,
            "--spring.profiles.active=prod,live")) {

        assertThat(grouped.getEnvironment()
                .getProperty("lab252.variant"))
                .isEqualTo("cfg-live");
    }
}
```

This test is valuable because it shows **you cannot reduce all Config Data precedence to "later profile always wins"** when multiple location groups are present.

Never pass an unquoted string containing `;` in a shell: most shells treat `;` as a command separator. In Java tests, each `--spring.config.location=...` argument is passed directly as a `String`, bypassing shell parsing.

## 21. Test 13 — Imported Profile-Specific Files

When a document declares:

```properties
spring.config.import=feature.properties
```

Config Data also considers profile-specific variants such as `feature-dev.properties`.

Directory:

```text
import-profile/
├── application.properties
├── feature.properties
└── feature-dev.properties
```

Contents:

`application.properties`:

```properties
spring.config.import=feature.properties
lab252.flag=root
```

`feature.properties`:

```properties
lab252.flag=feature-base
```

`feature-dev.properties`:

```properties
lab252.flag=feature-dev
```

Test:

```java
@Test
void profileSpecificVariantOfImportCanWin()
        throws IOException {

    Path dir = tempDir.resolve("import-profile");

    Path root = write(
            dir.resolve("application.properties"),
            "spring.config.import=feature.properties\n"
            + "lab252.flag=root\n");

    write(
            dir.resolve("feature.properties"),
            "lab252.flag=feature-base\n");

    write(
            dir.resolve("feature-dev.properties"),
            "lab252.flag=feature-dev\n");

    try (ConfigurableApplicationContext context = start(
            "--spring.config.location=" + root.toUri(),
            "--spring.profiles.active=dev")) {

        assertThat(context.getEnvironment()
                .getProperty("lab252.flag"))
                .isEqualTo("feature-dev");
    }
}
```

The key insight is that importing is not "reading a file with `Files.readString`." Spring Boot integrates imported resources into Config Data, including profile-specific variants where applicable.

## 22. Combining the Test Code into One Complete Class

All preceding snippets fit inside **one test class** as shown below. Keep this skeleton when assembling the test methods.

`src/test/java/example/configlab/ConfigDataStartupTest.java`:

```java
package example.configlab;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.boot.Banner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.WebApplicationType;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.core.env.ConfigurableEnvironment;

class ConfigDataStartupTest {

    @TempDir
    Path tempDir;

    @SpringBootConfiguration(proxyBeanMethods = false)
    static class MinimalApplication {
    }

    private static ConfigurableApplicationContext start(
            String... arguments) {

        SpringApplication application =
                new SpringApplication(MinimalApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);
        application.setBannerMode(Banner.Mode.OFF);
        application.setLogStartupInfo(false);

        return application.run(arguments);
    }

    private static Path write(Path file, String content)
            throws IOException {

        Files.createDirectories(file.getParent());
        Files.writeString(file, content, StandardCharsets.UTF_8);
        return file;
    }

    // Place the @Test methods from sections 9-21 here.
}
```

With this skeleton, you only need **one declaration** of `@TempDir`, the `start` helper, the `write` helper, and the nested `MinimalApplication`.

Do not put multiple public classes named `ConfigDataStartupTest` in one Java file. Each section's snippet is a method to add into this class.

### Commands to Run Tests

Maven wrapper:

```bash
./mvnw test
```

Running only this class with Maven Surefire when supported:

```bash
./mvnw -Dtest=ConfigDataStartupTest test
```

Gradle wrapper:

```bash
./gradlew test
```

Running this specific class:

```bash
./gradlew test --tests example.configlab.ConfigDataStartupTest
```

If tests reside in a submodule, include the module path/task prefix when invoking Gradle/Maven from the repository root.

## 23. Do Not Use `System.setProperty` Carelessly

To verify that Java system properties outrank Config Data, it is tempting to write:

```java
System.setProperty("lab252.mode", "from-jvm");
```

The problem: Java system properties are **global state for the test JVM**. Without proper restoration, other tests in the same process see the mutation. Parallel test execution makes intermittent failures even more likely.

If you must test it:

1. Save the previous value before modifying it.
2. Use a test key with a dedicated prefix.
3. Ensure the test does not run concurrently with others touching that key (via JUnit `ResourceLock` or sequential execution).
4. Restore the exact prior state in `finally`.
5. Never mutate global keys like `spring.config.location` while other test contexts may start concurrently.

A protective pattern:

```java
String key = "lab252.mode";
String previous = System.getProperty(key);

try {
    System.setProperty(key, "from-jvm");
    // Start SpringApplication, assert, close context.
} finally {
    if (previous == null) {
        System.clearProperty(key);
    } else {
        System.setProperty(key, previous);
    }
}
```

In a parallel test suite, restoring in `finally` **alone is not enough** to prevent race conditions; synchronization or process isolation is required.

In this lesson, we favor CLI-vs-file tests because everything passes through `run(...)` arguments without altering global state.

## 24. Do Tests Using `SpringApplication.setDefaultProperties` Prove Precedence?

`SpringApplication` supports:

```java
application.setDefaultProperties(Map.of(
        "lab252.mode", "from-default"));
```

This is a default-properties source, normally lower priority than Config Data and CLI.

Illustrative example:

```java
SpringApplication application =
        new SpringApplication(MinimalApplication.class);

application.setWebApplicationType(WebApplicationType.NONE);
application.setDefaultProperties(Map.of(
        "lab252.mode", "from-default"));

try (ConfigurableApplicationContext context = application.run(
        "--lab252.mode=from-cli")) {

    assertThat(context.getEnvironment()
            .getProperty("lab252.mode"))
            .isEqualTo("from-cli");
}
```

Remember to import `java.util.Map`.

If CLI is omitted while a Config Data file sets `lab252.mode=from-file`, the file value overrides the default.

**Do not use `setDefaultProperties` to simulate Java system properties.** They occupy completely different priority tiers in the Spring `Environment`.

## 25. Filesystem Locations and Working Directories

A file referenced by an absolute URI:

```text
file:/opt/service/config/application.properties
```

does not depend on the Java process's working directory the way this does:

```text
file:./config/application.properties
```

Relative paths depend on where the application actually launches. Running:

```bash
java -jar app.jar
```

uses the terminal's current directory. Under `bootRun`, an IDE, or CI, the working directory may differ.

In tests, use:

```java
file.toUri()
```

from `@TempDir` to eliminate ambiguity.

If you specifically want to test **relative path behavior itself**, configure the working directory explicitly—ideally in a separate child process. Do not randomly call `System.setProperty("user.dir", ...)` inside a shared JVM running multiple tests; mutating that property does not guarantee all libraries and filesystem APIs treat it as a real OS chdir.

### `classpath:` Is Not `file:`

Two locations:

```text
classpath:/application.properties
file:/absolute/path/application.properties
```

point to different resource systems:

- `classpath:` searches the classpath (classes/resources directories or JARs).
- `file:` searches the filesystem.

Files with the same name in both places can load or override according to location, profile, and precedence rules.

For external-file tests, use `file:` and a temporary directory directly. For classpath tests, use `src/test/resources`.

## 26. `spring.config.location` Is Read Too Early to Set Late

Suppose a bean does:

```java
@Component
public class LaterBean {
    @PostConstruct
    void init() {
        System.setProperty(
                "spring.config.location",
                "file:/later/application.properties");
    }
}
```

This is far too late to expect Boot to **re-run the entire Config Data search**.

To test file search locations, pass:

```java
start("--spring.config.location=" + file.toUri())
```

right in the startup arguments.

Or in real runtime execution:

```bash
java -jar app.jar \
  --spring.config.location=file:/config/application.properties
```

or:

```bash
java \
  -Dspring.config.location=file:/config/application.properties \
  -jar app.jar
```

Spring Boot documentation stresses that `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are read very early; tests must provide them in a source available at that phase.

## 27. The Issue Between `@TestPropertySource` and `spring.config.import`

Some tests write:

```java
@TestPropertySource(properties = {
        "spring.config.import=extra.properties"
})
```

expecting it to behave identically to `spring.config.import` inside `application.properties` during Config Data discovery.

Do not assume that. Test annotations follow Spring TestContext's own lifecycle and precedence. Their **configuration timing** is not equivalent to values read by the Config Data engine during document discovery and import.

If your goal is verifying **real imports inside a file**:

1. Write a temporary `application.properties` containing `spring.config.import=...`.
2. Pass `spring.config.location` via startup arguments.
3. Call `SpringApplication.run(...)`.
4. Assert keys from the imported file.

Likewise, `@PropertySource` on a Spring class does not support full multi-document YAML or Config Data profile activation. It is not a replacement for a startup test.

## 28. Why `ApplicationContextRunner` Is Not Full Proof for All Imports

A simple test:

```java
new ApplicationContextRunner()
        .withPropertyValues("lab252.mode=from-test")
        .run(context -> {
            assertThat(context.getEnvironment()
                    .getProperty("lab252.mode"))
                    .isEqualTo("from-test");
        });
```

proves the value was added to the runner's context. It **does not prove** the engine searched `application.properties`, handled profile-specific files, resolved relative imports, handled `optional:`, or applied `spring.config.location` like a real `SpringApplication`.

`ApplicationContextRunner` is great for testing auto-configuration and bean conditions. This lesson chooses `SpringApplication.run` specifically to traverse the full startup lifecycle.

A passing test must never be interpreted more broadly than the mechanisms it actually exercised.

## 29. Are `.properties` and YAML Tested Identically?

Both work with Config Data, yet use different file syntaxes.

`.properties` file:

```properties
lab252.mode=base
spring.config.import=extra.properties
```

YAML:

```yaml
lab252:
  mode: base

spring:
  config:
    import: extra.properties
```

To test YAML, write a `.yaml` file with `Files.writeString`, point `spring.config.location` to its file URI or a directory with a matching basename, and assert `Environment`.

Example:

```java
Path yaml = write(
        tempDir.resolve("yaml/application.yaml"),
        "lab252:\n"
        + "  mode: yaml\n");

try (ConfigurableApplicationContext context = start(
        "--spring.config.location=" + yaml.toUri())) {

    assertThat(context.getEnvironment()
            .getProperty("lab252.mode"))
            .isEqualTo("yaml");
}
```

Never mistake multi-document properties `#---` syntax for multi-document YAML syntax. YAML uses `---` on its own separator line. Tests for multi-document behavior must write valid syntax for that format and assert activation behavior.

### Both `.properties` and YAML in the Same Location

Spring Boot documents that if both `application.properties` and YAML exist in the same location with the same basename, `.properties` takes precedence. Best practice is **standardizing on one format** per application to avoid confusion.

If a project has both, create both files in the same temp directory, point to that location, and assert overlapping keys resolve from `.properties`. That is distinct from testing classpath-vs-external precedence.

## 30. Distinguishing Import-Relative Files from Relative Filesystem Locations

There are two kinds of "relative":

**A. Relative filesystem location**

```text
file:./config/application.properties
```

resolved against the process's filesystem/working directory.

**B. Import-relative location**

Inside `application.properties`:

```properties
spring.config.import=child/extra.properties
```

This import resolves relative to the declaring document's location, not `user.dir`.

Both are easy to lump together as "relative paths," yet tests must know which one they are testing.

If an import should always point to a fixed location, use an explicit scheme (`file:`, `classpath:`) or a fixed path supported by Spring Boot.

## 31. `optional:` Does Not Mean "Ignore All Configuration Errors"

Example:

```properties
spring.config.import=optional:missing.properties
```

permits the corresponding resource to be absent.

However, if the file **exists** and contains:

```properties
lab252.number=not-a-number
```

and Binder tries converting it to `int`, the application still fails binding/validation. The `optional:` prefix does not excuse invalid value contents.

Similarly, if YAML exists with broken syntax, parse errors fail startup. Critical production configs should also avoid using `optional:` carelessly just so an app boots with missing values.

### Distinguishing Three Test Failure Types

| Type | Example | What the test should verify |
| --- | --- | --- |
| Location not found | `spring.config.import=missing.properties` | Startup fails due to missing resource/location |
| Data parse failure | Broken YAML syntax | Startup fails because file cannot be read |
| Bind/validation failure | `demo.port=abc` or `@Min(1)` with `0` | Startup fails to create configuration bean |

All three make startup fail, yet their root causes and fixes differ completely.

## 32. Separating "File Was Loaded" from "Value Won"

A test doing only:

```java
assertThat(environment.getProperty("lab252.mode"))
        .isEqualTo("from-cli");
```

does not prove any file was loaded, because CLI still wins even if the file does not exist.

Good test design puts a **unique marker** in each source:

Classpath file:

```properties
lab252.classpath-only=yes
lab252.shared=classpath
```

External file:

```properties
lab252.external-only=yes
lab252.shared=external
```

CLI:

```text
--lab252.shared=cli
```

Assertions:

```text
lab252.classpath-only = yes      -> classpath participated
lab252.external-only  = yes      -> external participated
lab252.shared         = cli      -> CLI won
```

This verifies both **presence** and **precedence**. That is especially valuable when analyzing `spring.config.additional-location`, imports, and location groups.

## 33. Do Not Depend on Exact `PropertySource` Names

Spring Boot generates source names like:

```text
Config resource 'file [...]' via location '...'
```

These names help during debugging, yet can change across Spring Boot versions, actual paths, profiles, URIs, loaders, or file formats.

A brittle test:

```java
assertThat(environment.getPropertySources()
        .contains("Config resource '...' via location '...'"))
        .isTrue();
```

When the goal is simply confirming a file loaded, marker properties are far more stable.

When diagnosing sources in detail, you can iterate over sources and print names:

```java
for (PropertySource<?> source :
        environment.getPropertySources()) {
    System.out.println(source.getName());
}
```

Use that strictly for **diagnostics**, never treating internal source names as a stable public API contract.

Never print the full contents of every PropertySource, as they can contain passwords, tokens, connection strings, or other sensitive values.

## 34. Testing via Java System Properties: Locking Global State

If a test must prove:

```text
CLI > Java system property > Config Data
```

pair it with `@ResourceLock` to coordinate parallel execution.

Structure example:

```java
@ResourceLock(value = Resources.SYSTEM_PROPERTIES,
        mode = ResourceAccessMode.READ_WRITE)
@Test
void cliWinsOverJvmProperty() throws IOException {

    String key = "lab252.mode";
    String before = System.getProperty(key);

    Path config = write(
            tempDir.resolve("sys-property/application.properties"),
            "lab252.mode=from-file\n");

    try {
        System.setProperty(key, "from-jvm");

        try (ConfigurableApplicationContext context = start(
                "--spring.config.location=" + config.toUri(),
                "--lab252.mode=from-cli")) {

            assertThat(System.getProperty(key))
                    .isEqualTo("from-jvm");

            assertThat(context.getEnvironment().getProperty(key))
                    .isEqualTo("from-cli");
        }
    } finally {
        if (before == null) {
            System.clearProperty(key);
        } else {
            System.setProperty(key, before);
        }
    }
}
```

Additional imports:

```java
import org.junit.jupiter.api.parallel.ResourceAccessMode;
import org.junit.jupiter.api.parallel.ResourceLock;
import org.junit.jupiter.api.parallel.Resources;
```

Locking works only when **other tests honor the same resource lock contract**; it cannot prevent arbitrary non-JUnit code from mutating system properties. Never mutate startup keys like `spring.config.location` in parallel suites without isolation.

For most configuration lessons, testing with CLI args and temp files is easier to maintain because no global state is touched.

## 35. Testing `SpringApplication` vs. `SpringApplicationBuilder`

Both execute the Spring Boot application lifecycle.

`SpringApplicationBuilder` example:

```java
try (ConfigurableApplicationContext context =
        new SpringApplicationBuilder(MinimalApplication.class)
                .web(WebApplicationType.NONE)
                .run("--spring.config.location=" + config.toUri())) {

    assertThat(context.getEnvironment()
            .getProperty("lab252.mode"))
            .isEqualTo("expected");
}
```

`SpringApplicationBuilder` is convenient for hierarchical contexts or fluent configuration. In this lesson, however:

```java
new SpringApplication(MinimalApplication.class).run(args);
```

already makes the tested bootstrap stages clear.

Avoid adding parent/child contexts or multi-level builders just to test a property source. That makes tests harder to follow and can alter environment inheritance relative to the real app.

## 36. Hands-On Verification with `java -jar`

Once programmatic tests pass, you can cross-check by running the real JAR.

Suppose:

```text
config/
├── application.properties
└── extras/
    └── feature.properties
```

`config/application.properties`:

```properties
spring.config.import=extras/feature.properties
lab252.mode=from-root
```

`config/extras/feature.properties`:

```properties
lab252.mode=from-import
```

With an executable JAR, run:

```bash
java -jar app.jar \
  --spring.config.location=file:./config/application.properties
```

When the app inspects `Environment#getProperty("lab252.mode")`, the value is `from-import`.

Try next:

```bash
java -jar app.jar \
  --spring.config.location=file:./config/application.properties \
  --lab252.mode=from-cli
```

The final value is `from-cli` because command-line properties outrank Config Data.

**This is supplemental verification**, not a replacement for automated tests. The commands depend on the current directory, shell, and built JAR artifact.

### PowerShell Equivalent

```powershell
java -jar .\app.jar `
  '--spring.config.location=file:./config/application.properties'
```

Or on a single line:

```powershell
java -jar .\app.jar '--spring.config.location=file:./config/application.properties'
```

When locations contain `;` or spaces, quoting is essential so the shell does not split the argument unexpectedly.

## 37. Design Decisions for Reliable Tests

A solid Config Data test suite should exhibit these traits:

1. **Minimal application:** avoid scanning unrelated beans.
2. **No web server:** use `WebApplicationType.NONE`.
3. **Close contexts:** use `try-with-resources`.
4. **Temp files per test:** use `@TempDir`.
5. **Absolute URIs:** use `Path.toUri()`.
6. **Unique markers:** distinguish loaded files from winning files.
7. **One primary idea per test:** easy root-cause diagnosis on failure.
8. **No global sources:** avoid polluting system properties or environment variables.
9. **No working-directory dependency:** unless testing relative paths explicitly.
10. **Avoid fragile verbatim exception message assertions** when checking startup failures.
11. **Distinguish absent keys from empty strings or null**.
12. **Never put real secrets in temp files.**
13. **Consider child-process tests** when testing JVM flags and real working directories.
14. **Never execute untrusted config contents** as automated scripts in tests.
15. **Match the project's Spring Boot version** so results reflect real runtime behavior.

A test with multiple sources asserting only one key easily leads to overbroad conclusions. Documenting which source wins and why in the test name keeps maintenance clear.

## 38. Common Pitfalls When Writing These Tests

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| Test cannot find external file | Bad URI, missing `file:` prefix | Use `Path.toUri()` |
| Test passes only on developer laptop | Relative path depends on `user.dir` | Use `@TempDir` and absolute URIs |
| `spring.config.location` hides classpath file | Default locations were replaced | Use `spring.config.additional-location` to retain defaults |
| `additional-location` fails to override as expected | Higher-priority CLI/system property exists | Inspect all PropertySources |
| Relative import looks in wrong directory | Assumed relative import always uses shell cwd | Trace relative to declaring file |
| Missing optional file fails startup | Forgot `optional:` on that location | Add `optional:` on the specific location |
| Enabling profile changes nothing | Wrong profile filename or directory | Check `application-<profile>` and path |
| `spring.config.name` has no effect | Set too late or directory lacks trailing slash | Pass at startup and verify trailing `/` |
| Test with `;` breaks in shell | Shell treats `;` as command separator | Quote the entire option value |
| PropertySource name breaks across Boot upgrades | Test coupled to internal source name | Assert marker properties and resolved values |
| `ApplicationContextRunner` passes yet real import fails | Runner skips Config Data bootstrap | Use `SpringApplication.run` |
| `@TestPropertySource` fails to reproduce import | Different test property lifecycle stage | Put import inside a real Config Data file |
| Test runtime slow/broken by DB | Test app scans unrelated beans | Use minimal `@SpringBootConfiguration` |
| Tests interfere with each other | Global `System.setProperty` or shared file | Isolate temp dirs and restore state |
| Test passes even when file never loaded | Only asserted key matching default/CLI | Add unique marker per source |
| Test fails due to shell quoting | String argument split unexpectedly | In Java tests, pass `String... args` directly |
| Test ignores YAML | Wrong extension or YAML syntax | Write valid `.yaml` and full URI |
| Spring app picks unexpected value | Higher-priority source overrides file | Inspect `Environment`, profiles, and active sources |
| `optional:` still fails startup | File exists with broken content or other error | Distinguish missing file from parse/bind failure |
| Multiple profiles yield unexpected value | Location groups altered precedence | Check `,` vs. `;` |
| Setting location via system property after startup | Config Data already ran | Supply location at startup |

## 39. When Should You Also Verify `@ConfigurationProperties`?

If the goal is purely source ordering, `Environment#getProperty()` suffices to determine the winning key.

When proving the value binds into typed models:

```java
@ConfigurationProperties(prefix = "lab252")
public record LabProperties(
        String mode,
        int retryCount,
        Duration timeout
) {
}
```

register the configuration class via:

```java
@EnableConfigurationProperties(LabProperties.class)
```

on the minimal test application, or use `@ConfigurationPropertiesScan` in an appropriate scope.

After startup:

```java
LabProperties properties = context.getBean(LabProperties.class);
```

then assert:

```java
assertThat(properties.mode()).isEqualTo("from-cli");
assertThat(properties.retryCount()).isEqualTo(3);
assertThat(properties.timeout()).isEqualTo(Duration.ofSeconds(5));
```

That test spans:

```text
Config Data -> Environment -> Binder -> typed object
```

**However, do not turn every test in this lesson into a binding test.** Keep precedence tests focused, and add one representative binding test. Separating causes lets you tell file-discovery bugs apart from converter/validation bugs immediately.

## 40. Practice Exercises

### Exercise 1 — Replacement vs. Addition

Classpath has:

```properties
lab252.classpath-only=yes
```

External file has:

```properties
lab252.external-only=yes
```

Question: how do `spring.config.location` and `spring.config.additional-location` differ?

**Answer:** `location` replaces default search locations; `additional-location` preserves defaults and loads extra locations. Assert unique markers to prove both.

### Exercise 2 — Import Beats Declaring File

Root file:

```properties
spring.config.import=extra.properties
lab252.value=root
```

Imported file:

```properties
lab252.value=extra
```

Question: what is the effective value at startup if no higher source exists?

**Answer:** `extra`, since imported Config Data outranks the file declaring the import.

### Exercise 3 — CLI Override

External file:

```properties
lab252.mode=external
```

Args:

```text
--lab252.mode=cli
```

Question: what does `Environment#getProperty("lab252.mode")` return?

**Answer:** `cli` under default SpringApplication settings.

### Exercise 4 — Missing Required File

Root file:

```properties
spring.config.import=missing.properties
```

Question: expected outcome?

**Answer:** Startup fails with a Config Data not-found error, unless a matching missing-location policy is configured.

### Exercise 5 — Missing Optional File

Root file:

```properties
spring.config.import=optional:missing.properties
lab252.value=base
```

Question: expected outcome?

**Answer:** The app starts and resolves `base`, assuming no other errors exist.

### Exercise 6 — Multi-Level Imports

Root imports `sub/first.properties`, which imports `next/second.properties`.

Question: where does the second import resolve from?

**Answer:** Relative to the directory of `first.properties`, which declared the second import.

### Exercise 7 — Multiple Imports

Root:

```properties
spring.config.import=a.properties,b.properties
```

Both define `lab252.x`.

Question: which file typically wins?

**Answer:** The later import, `b.properties`, when no higher-priority source exists.

### Exercise 8 — Profiles

`application.properties` has `x=base`, `application-prod.properties` has `x=prod`, active profile `prod`.

**Answer:** The profile-specific file overrides base to `prod`.

### Exercise 9 — Location Groups

Two directories: one holds `application-live.properties` with `cfg-live`, the other holds `application-prod.properties` with `ext-prod`. Active profiles `prod,live`.

Question: can `,` and `;` produce different outcomes?

**Answer:** Yes. Comma processes locations as separate priority tiers; semicolon groups them into one tier where profile ordering decides within the group.

### Exercise 10 — Mock Unit Test

A test calls `new StandardEnvironment()`, manually adds a `MapPropertySource`, and observes `x=value`.

Question: has it proven `spring.config.import` works properly?

**Answer:** No. That only tests manual source addition; a real `SpringApplication` startup is needed to verify Config Data.

### Exercise 11 — Working Directory

Why does `file:./config/application.properties` sometimes work in a terminal yet fail inside an IDE?

**Answer:** The process's working directory differs. Use explicit paths or inspect `workingDir` and `user.dir`.

### Exercise 12 — Marker Present While Another Key Wins

Classpath has `lab252.marker=classpath`, external has `lab252.value=external`, CLI has `--lab252.value=cli`.

Question: is having the classpath marker present while `value=cli` contradictory?

**Answer:** No. The marker proves the file loaded; `value=cli` proves precedence. The two checks answer different questions.

### Exercise 13 — Real App vs. Minimal Test

If the minimal test passes yet the production app still fails to start, can we conclude Config Data is broken?

**Answer:** Not yet. The real app may have additional `@ConfigurationProperties` validation, beans, connection dependencies, different profiles, system/env properties, or runtime paths.

### Exercise 14 — Invalid Timeout Test

If `lab252.timeout=invalid` loads as a `String`, `Environment#getProperty` still succeeds. What happens to a bean with `Duration timeout`?

**Answer:** Binding fails on type conversion. The two layers require separate tests.

## 41. Checklist for a Reliable Config Data Test Suite

- [ ] Tests run against the same Spring Boot line as the app, here 3.3.x.
- [ ] Real startup tests run via `SpringApplication.run`.
- [ ] Test app is minimal, needing no web server or DB.
- [ ] Context is closed after each test.
- [ ] Configuration files are written inside `@TempDir`.
- [ ] Test paths use `Path.toUri()` to avoid Windows/Unix differences.
- [ ] A classpath marker file is placed in `src/test/resources`.
- [ ] A test verifies `spring.config.location` replaces default locations.
- [ ] A test verifies `spring.config.additional-location` keeps defaults and loads extras.
- [ ] A test verifies `spring.config.import` and that imported values beat the declaring file.
- [ ] A test verifies nested import-relative paths.
- [ ] A test verifies multiple imports and their order.
- [ ] Tests cover `optional:` vs. missing required files.
- [ ] A test verifies profile-specific variants.
- [ ] A test verifies CLI overrides Config Data.
- [ ] Tests cover both file locations and directory locations.
- [ ] A test covers `spring.config.name` where needed.
- [ ] Tests cover location groups if the system uses multiple profiles.
- [ ] Global system properties are never mutated without proper isolation.
- [ ] Tests do not depend on internal `PropertySource` names or brittle exception messages.
- [ ] Unique markers prove each file actually loaded.
- [ ] Sensitive values are never written to logs.
- [ ] Binder and validation tests are separated from precedence tests where appropriate.
- [ ] Build/tests pass on both Windows and Unix with valid paths.
- [ ] Tests can run repeatedly without manual file cleanup.

## 42. Summary

A rigorous empirical workflow for **Spring Boot Externalized Configuration** goes beyond reading precedence documentation. It **constructs controlled conflict scenarios**, starts Spring Boot for real, and asserts the outcome.

```text
Create temporary files with @TempDir
          |
          v
Write application.properties and imported files
          |
          v
Pass spring.config.location / additional-location
          |
          v
SpringApplication.run(...)
          |
          v
Config Data resolves files, profiles, imports, precedence
          |
          v
ConfigurableApplicationContext#getEnvironment()
          |
          v
Assert markers + conflicting keys
          |
          v
Close ApplicationContext
```

Most important rules:

1. **Use `SpringApplication.run`** when proving file discovery and `spring.config.import` during startup.
2. **`spring.config.location` replaces**, whereas **`spring.config.additional-location` supplements** default locations.
3. **Imported data outranks the declaring document**; import-relative paths resolve from the declaring file.
4. **CLI `--key=value` carries high priority** under default SpringApplication settings.
5. **Profile-specific files and location groups** alter precedence; `,` and `;` are not equivalent.
6. **`@TempDir` and absolute URIs** make tests reproducible across machines and working directories.
7. **Use unique markers per source** to prove loading, and shared keys to prove which source wins.
8. **Separate input-source testing from binding/validation and operational dependency checks**, since a passing startup config test does not prove the entire production app is ready.

Practicing these tests turns knowledge of precedence, imports, and locations into **reproducible proof**, helping development and operations teams avoid elusive bugs when the same JAR runs across environments.

## References

- Spring Boot 3.3 Reference — Externalized Configuration (PropertySource Order, Config Data, Import, Optional Locations, Profile Specific Files): https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 API — SpringApplication: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Spring Boot 3.3 Reference — Testing Spring Boot Applications: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3 Reference — Profiles: https://docs.spring.io/spring-boot/3.3/reference/features/profiles.html
- Spring Framework API — ConfigurableEnvironment: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html
- JUnit 5 User Guide — @TempDir: https://junit.org/junit5/docs/current/user-guide/
