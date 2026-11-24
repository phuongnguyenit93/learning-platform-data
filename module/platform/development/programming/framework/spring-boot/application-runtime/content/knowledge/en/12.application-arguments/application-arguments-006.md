# Relationship Between --key=value Arguments and Properties in Spring Environment

## 1. The core answer

When you launch a Spring Boot application with:

```bash
java -jar myapp.jar --demo.message=hello --server.port=9090
```

the two parts starting with `--` are **option-style application arguments**, passed into `main`'s `String[] args`. Under Spring Boot 3.3's default configuration, `SpringApplication` **parses those options, converts them into properties, and adds a `PropertySource` to the Spring `Environment`**. As a result, application components can read:

```java
environment.getProperty("demo.message"); // "hello"
environment.getProperty("server.port");   // "9090"
```

If a web application uses standard server configuration, `--server.port=9090` can also make the server listen on port 9090. However, a property appearing in `Environment` **does not guarantee a component consumes it**: in a non-web application, `server.port` can be read without opening an HTTP port.

**Remember three fundamental distinctions:**

1. **`--key=value` is a way to pass options to the application**, not an OS environment variable and not a Java system property.
2. **`Environment` is a collection of multiple property sources with precedence order**. Command-line options go into one of those sources; they can override values of the same key in `application.properties`.
3. **`ApplicationArguments` retains argument details**, including options, option values, and unnamed arguments. Reading `ApplicationArguments` differs from querying `Environment` for **the effective value resolved across multiple sources**.

In Spring Boot, you can separately disable **exposing command-line options to `Environment`**:

```java
SpringApplication application = new SpringApplication(MyApplication.class);
application.setAddCommandLineProperties(false);
application.run(args);
```

Then the options are still passed into `SpringApplication.run(args)` and remain readable via `ApplicationArguments`, yet they **no longer automatically override values in `Environment` through the command-line property source**. Section 7 provides a runnable project showing the difference.

## 2. Path from the command line to Environment

Logical diagram:

```text
Shell / terminal / Gradle bootRun
        |
        |  --demo.message=from-cli
        |  --demo.retries=7
        |  orders.csv
        v
Java main(String[] args)
        |
        v
SpringApplication.run(args)
        |
        +-- DefaultApplicationArguments
        |      |-- option "demo.message" -> ["from-cli"]
        |      |-- option "demo.retries" -> ["7"]
        |      +-- non-option args -> ["orders.csv"]
        |
        +-- adds CommandLinePropertySource by default
               to ConfigurableEnvironment
                    |
                    +-- demo.message = "from-cli"
                    +-- demo.retries = "7"
                    |
                    v
             Environment.getProperty(...)
             @Value(...)
             @ConfigurationProperties(...)
                    |
                    v
             Beans consuming effective configuration
```

These stages do not occur as completely isolated processes; the diagram depicts **two views over the same set of input arguments**:

- `ApplicationArguments` is the API for asking **which arguments were passed to this run**.
- `Environment` is the API for asking **the application's effective properties**, which may come from CLI, system properties, OS environment, config data, default properties, and other sources.

This explains a common situation: if `--demo.message` is not passed while `demo.message` exists in `application.properties`, `ApplicationArguments.containsOption("demo.message")` is `false` while `Environment.getProperty("demo.message")` still returns the value from the file. Both answers are right; they answer **two different questions**.

A timing note: the command-line property source is installed into `Environment` by Spring Boot **during environment preparation**, before ordinary beans are created and receive configuration. Thus, an option passed early can influence `@ConditionalOnProperty`, `@ConfigurationProperties`, active profiles, and other bootstrap decisions depending on the property type.

## 3. --key=value option syntax and non-option arguments

Under the command-line syntax Spring uses, an option has the form:

```text
--optionName[=optionValue]
```

Examples:

| Actual Argument | Type | Parsed Meaning |
|---|---|---|
| `--demo.message=hello` | Valued option | Name `demo.message`, value `hello` |
| `--server.port=9090` | Valued option | Name `server.port`, value `9090` |
| `--debug` | Presence-only option | Name `debug` exists, no explicit value |
| `--demo.message=` | Empty-string option | Has `=`, value is `""` |
| `--demo.message="Hello world"` | Option with space-containing value | Shell merges quoted content into one argument if quoted properly |
| `orders.csv` | Non-option | A positional argument; does not become key `orders.csv` |
| `--demo.message hello` | **Two arguments** | Option `demo.message` without a value; `hello` is a non-option |
| `-Ddemo.message=hello` | Not Spring `--` syntax | Only a JVM system property **if placed in JVM args before `-jar`/main class** |

**Two hyphens are required** for Spring Boot to recognize an option: `--key=value`. A single dash like `-key=value` is not an equivalent alias for a command-line option in this parser.

**An equals sign immediately after the key is required** when passing a value. The line:

```bash
java -jar myapp.jar --demo.message hello
```

is not equivalent to:

```bash
java -jar myapp.jar --demo.message=hello
```

In the first line, `--demo.message` is a valueless option; `hello` becomes a non-option. Detecting the option name **does not mean** `Environment` holds `"hello"` for that key.

### Shells process quotes before Java

Example:

```bash
java -jar myapp.jar --demo.message="Hello world"
```

Standard shells turn the quoted segment into a single argument with value `Hello world`, rather than sending quote marks as part of the value. Quoting rules differ across Bash, PowerShell, and Windows `cmd`; when special characters such as spaces, `$`, `&`, `!`, slashes, or nested quotes appear, apply the rules of **the actual shell in use**.

A standalone `--` argument acts as an "end of options" delimiter in POSIX-style command-line parsers; arguments after it are treated as non-options. Even so, do not rely on this delimiter as a way to configure `Environment` with `--`-prefixed values without testing the actual parser.

## 4. Environment is not a copy of String[] args

`org.springframework.core.env.Environment` is the abstraction for querying **application properties and profiles**. `ConfigurableEnvironment` also lets you inspect `PropertySource`s. In a typical Spring Boot runtime, the command-line source is named:

```text
commandLineArgs
```

It takes precedence over standard file configuration sources. Consider an example:

**`src/main/resources/application.properties`:**

```properties
demo.message=from-file
demo.retries=2
```

Then launch:

```bash
java -jar myapp.jar --demo.message=from-cli --demo.retries=7
```

By default, **effective** values are:

| Key | File Value | CLI Value | `Environment.getProperty(...)` |
|---|---|---|---|
| `demo.message` | `from-file` | `from-cli` | `from-cli` |
| `demo.retries` | `2` | `7` | `"7"` when read as `String` |
| `demo.unknown` | Absent | Absent | `null` if no other source exists |
| `demo.other` | `file-only` | Absent | `file-only` if defined in file |

**Spring does not modify `application.properties` on disk.** Spring resolves properties by traversing configuration sources in precedence order. The CLI value is chosen over the file **for that run**; the original file stays untouched.

### Default precedence in Spring Boot runtime

Some common configuration sources, from lowest to highest in typical cases:

```text
SpringApplication defaultProperties
      <
application.properties / application.yaml (config data)
      <
OS environment variables
      <
Java system properties (-Dkey=value)
      <
SPRING_APPLICATION_JSON
      <
Command-line options (--key=value)
```

This is a **simplified diagram**, not an exhaustive list: JNDI, servlet params, random properties, custom property sources, and test-environment sources each have their place. In **tests**, for example `@TestPropertySource` or `@DynamicPropertySource` can outrank command-line arguments; therefore the accurate statement is that **CLI outranks file sources in the default runtime configuration**, not "CLI beats every source in every situation".

With the same key `demo.message`:

```properties
# application.properties
demo.message=from-file
```

```bash
# Java system property + app option in the same run:
java -Ddemo.message=from-jvm -jar myapp.jar --demo.message=from-cli
```

In standard configuration, `Environment.getProperty("demo.message")` returns `from-cli`, because the command-line property source outranks Java system properties. If you omit `--demo.message=...`, `from-jvm` can override `from-file`.

**Do not call `System.getProperty("demo.message")` expecting `from-cli`.** `System.getProperty` reads **JVM system properties**; Spring Boot does not merge its command-line `PropertySource` back into the JVM's system properties table.

## 5. ApplicationArguments: observing the exact arguments the user passed

Spring Boot provides an `ApplicationArguments` bean injectable into components or received in `ApplicationRunner.run(...)`. It lets you distinguish directly passed arguments from values resolved via `Environment`.

Useful methods:

| API | Meaning |
|---|---|
| `getSourceArgs()` | Raw `String[]` array passed to `SpringApplication.run(args)` |
| `getOptionNames()` | Set of option names of the form `--key[=value]` |
| `containsOption("demo.message")` | `true` if an option with this name exists, even without a value |
| `getOptionValues("demo.message")` | List of values for the option; `null` if option name is absent |
| `getNonOptionArgs()` | Arguments not belonging to the option group |

For example, with:

```bash
java -jar myapp.jar --name=Lan --tag=a --tag=b orders.csv
```

`ApplicationArguments` yields:

```text
containsOption("name")  -> true
getOptionValues("name") -> [Lan]
getOptionValues("tag")  -> [a, b]
getNonOptionArgs()      -> [orders.csv]
```

**Distinguishing three cases is crucial:**

- `--name` not passed: `getOptionValues("name")` returns **`null`**.
- `--name` passed without `=`: option name is present, `getOptionValues("name")` is an **empty list**.
- `--name=` passed: option name is present, with **one empty-string value**.

Some logging tools print `[]` identically when an empty-string element appears in a Java list, so to distinguish reliably, check `values == null`, `values.size()`, and `values.get(0).isEmpty()` rather than relying only on the printed string.

### Safe reading pattern

```java
List<String> values = arguments.getOptionValues("name");

String name = (values == null || values.isEmpty())
        ? "guest"
        : values.get(0);
```

This is an **integration snippet** placed in code with an `ApplicationArguments arguments` variable and `java.util.List` imported. If the user passes `--name=`, `values` has one empty element and `name` becomes an empty string; if you want to forbid blank values, additionally check `name.isBlank()`.

### Repeated option with the same name

```bash
java -jar myapp.jar --tag=a --tag=b
```

`ApplicationArguments.getOptionValues("tag")` stores multiple values according to the parser. Meanwhile, `Environment.getProperty("tag")` reads **a single effective property**; Spring Framework's `CommandLinePropertySource` implementation may represent multiple values as a comma-separated string. Therefore, when a parameter **can repeat** and you need a list preserving each value's semantics, `ApplicationArguments` is usually clearer than manually splitting strings returned by `Environment`.

## 6. Ways to read the same configuration value

Assuming `demo.message` exists in `Environment`, there are several ways to access it:

### 6.1. Environment

```java
String message = environment.getProperty("demo.message");
Integer retries = environment.getProperty("demo.retries", Integer.class);
```

`getProperty(String)` normally returns a `String` or `null` when not found; the `Class<T>` overload requests type conversion to `Integer`, `Boolean`, `Duration`, etc., via the conversion service. If the user passes `--demo.retries=abc`, requesting an integer cannot conjure a valid number; handle configuration errors rather than silently falling back to an invented value.

### 6.2. @Value

```java
@Value("${demo.message}")
private String message;
```

This is a **field inside a Spring-managed bean**, requiring `org.springframework.beans.factory.annotation.Value`. Spring resolves placeholders from `Environment` when creating and injecting the bean. If the key is missing and no default is supplied, startup can fail due to an unresolvable placeholder.

You can specify an injection-level fallback:

```java
@Value("${demo.message:guest}")
private String message;
```

However, this fallback is used only when no matching property is found; it **does not replace `Environment` precedence**. For configurations with many properties, prefer binding into a strongly typed configuration object.

### 6.3. @ConfigurationProperties

Spring Boot supports binding multiple properties by prefix into a class/record:

```java
@ConfigurationProperties(prefix = "demo")
public record DemoSettings(String message, int retries) {
}
```

When registered via `@EnableConfigurationProperties(DemoSettings.class)` or appropriate scanning, `demo.message` and `demo.retries` from `Environment` are bound into a strongly typed object.

For larger applications, `@ConfigurationProperties` is preferable to a long list of `@Value` fields: it groups configuration, supports relaxed binding, metadata, and validation when configured fully. It still relies on `Environment`, so CLI options can override file values **for the current run**.

**Important:** `ApplicationArguments` is not automatically `@ConfigurationProperties`. They are two separate APIs; when `setAddCommandLineProperties(false)` is enabled, `@ConfigurationProperties` objects no longer pick up overrides from the command-line property source even though `ApplicationArguments` still sees the options.

## 7. Complete Spring Boot 3.3 + Java 17 example: observing both read paths

This project shows how **one set of arguments** is read through both `ApplicationArguments` and `Environment`, and what changes when the command-line property source is disabled. No web server or database is needed.

### 7.1. File structure

```text
cli-environment-demo/
├── settings.gradle
├── build.gradle
└── src/main/
    ├── java/com/example/clienv/
    │   ├── CliEnvironmentApplication.java
    │   └── DemoSettings.java
    └── resources/
        └── application.properties
```

**`settings.gradle`**:

```groovy
rootProject.name = 'cli-environment-demo'
```

**`build.gradle`** (Gradle Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
}
```

`spring-boot-starter` includes the `ApplicationContext` and external configuration infrastructure needed for the example. `spring-boot-starter-web` is not needed; the program sets `WebApplicationType.NONE` so no HTTP server starts.

**`src/main/resources/application.properties`**:

```properties
spring.application.name=cli-environment-demo
demo.message=from-file
demo.retries=2
```

These are default values from **config data**; when the CLI command-line property source is enabled, callers can override them.

### 7.2. Record for @ConfigurationProperties

**`src/main/java/com/example/clienv/DemoSettings.java`**:

```java
package com.example.clienv;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "demo")
public record DemoSettings(String message, int retries) {
}
```

Java 17 supports `record`; with a single canonical constructor, Spring Boot 3.3 can use constructor binding for this configuration type. `@ConfigurationProperties` **alone does not register a bean** unless scanning is enabled or it is explicitly registered; the main class below uses `@EnableConfigurationProperties(DemoSettings.class)`.

### 7.3. Main class and ApplicationRunner printing results

**`src/main/java/com/example/clienv/CliEnvironmentApplication.java`**:

```java
package com.example.clienv;

import java.util.Arrays;

import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.core.env.ConfigurableEnvironment;

@SpringBootApplication
@EnableConfigurationProperties(DemoSettings.class)
public class CliEnvironmentApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(CliEnvironmentApplication.class);

        application.setWebApplicationType(WebApplicationType.NONE);

        // Demo: enable this mode with a JVM system property before "-jar".
        // It is NOT a Spring Boot "--key=value" option.
        if (Boolean.getBoolean("example.disable-cli-properties")) {
            application.setAddCommandLineProperties(false);
        }

        try (ConfigurableApplicationContext context =
                application.run(args)) {
            // Runner and ReadyEvent completed; close non-web demo.
        }
    }

    @Bean
    ApplicationRunner showEffectiveSettings(
            ConfigurableEnvironment environment,
            DemoSettings settings,
            @Value("${demo.message}") String viaValue) {

        return arguments -> {
            System.out.println("raw args = "
                    + Arrays.toString(arguments.getSourceArgs()));

            System.out.println("has message option = "
                    + arguments.containsOption("demo.message"));

            System.out.println("message option values = "
                    + arguments.getOptionValues("demo.message"));

            System.out.println("non-option args = "
                    + arguments.getNonOptionArgs());

            System.out.println("Environment demo.message = "
                    + environment.getProperty("demo.message"));

            System.out.println("Environment demo.retries = "
                    + environment.getProperty("demo.retries", Integer.class));

            System.out.println("@Value demo.message = " + viaValue);

            System.out.println("@ConfigurationProperties = "
                    + settings.message() + " / " + settings.retries());

            System.out.println("commandLineArgs present = "
                    + environment.getPropertySources()
                            .contains("commandLineArgs"));
        };
    }
}
```

**Code analysis:**

1. `SpringApplication` receives `String[] args` directly in `run`. This is the entry point for both `ApplicationArguments` and exposing options into `Environment` by default.
2. `setWebApplicationType(WebApplicationType.NONE)` merely keeps the demo without an HTTP server; it **does not affect the command-line property source feature**.
3. `Boolean.getBoolean("example.disable-cli-properties")` reads a **Java system property**; when `true`, the program calls `setAddCommandLineProperties(false)` **before `run` starts**.
4. The `@Bean` method returns an `ApplicationRunner` to print results after context initialization. Never invoke the runner's `run` manually.
5. `ApplicationArguments` is passed into the `run(ApplicationArguments)` callback as `arguments`; it reflects raw options and non-options.
6. `ConfigurableEnvironment.getProperty(...)` returns the **effective property by source order**; the `Integer.class` overload shows conversion from text to number.
7. The `@Value("${demo.message}") String viaValue` parameter is resolved when Spring creates the runner bean, and `DemoSettings` is bound from matching properties.
8. Checking `commandLineArgs` illustrates a standard property source in the demo's runtime config. With a custom `Environment` or different bootstrap path, source names/registration may vary, so do not treat this as the sole check for every Spring application.
9. `try-with-resources` closes the context after `SpringApplication.run` returns; real web apps normally keep the context running to serve requests.

### 7.4. Default run and overriding via CLI

From the directory containing **Gradle Wrapper**:

```bash
./gradlew bootRun --args='--demo.message=from-cli --demo.retries=7 orders.csv'
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun --args='--demo.message=from-cli --demo.retries=7 orders.csv'
```

If you do not have a Wrapper yet, generate the project via Spring Initializr or create a Wrapper with a compatible Gradle version; writing `build.gradle` does not automatically create `gradlew`. Java 17+ and compatible plugins are required for the build to succeed.

Lines **printed by the example program**, ignoring Spring Boot and Gradle banners/logs:

```text
raw args = [--demo.message=from-cli, --demo.retries=7, orders.csv]
has message option = true
message option values = [from-cli]
non-option args = [orders.csv]
Environment demo.message = from-cli
Environment demo.retries = 7
@Value demo.message = from-cli
@ConfigurationProperties = from-cli / 7
commandLineArgs present = true
```

Observe the relationship: `ApplicationArguments` sees `--demo.message` passed directly; simultaneously, `Environment`, `@Value`, and `@ConfigurationProperties` all pick **from-cli**, not **from-file**. The integer `7` was type-converted for `DemoSettings.retries()`.

### 7.5. Running without passing options

```bash
./gradlew bootRun
```

Decisive values in this run:

```text
raw args = []
has message option = false
message option values = null
non-option args = []
Environment demo.message = from-file
Environment demo.retries = 2
@Value demo.message = from-file
@ConfigurationProperties = from-file / 2
```

When **no command-line arguments exist**, do not write a rigid assertion that a source named `commandLineArgs` must be added: some startup paths only add the source when arguments are present. What matters is that `demo.message` is read from the file while `ApplicationArguments` has no `demo.message` option.

### 7.6. Disabling CLI injection into Environment while keeping ApplicationArguments

First build the JAR:

```bash
./gradlew bootJar
```

Then run:

```bash
java -Dexample.disable-cli-properties=true \
  -jar build/libs/cli-environment-demo-0.0.1-SNAPSHOT.jar \
  --demo.message=from-cli --demo.retries=7 orders.csv
```

On Windows PowerShell, write it on a single line to avoid shell line-continuation mismatches:

```powershell
java -Dexample.disable-cli-properties=true -jar build/libs/cli-environment-demo-0.0.1-SNAPSHOT.jar --demo.message=from-cli --demo.retries=7 orders.csv
```

Exact output from the lines printed by code, with `application.properties` unchanged:

```text
raw args = [--demo.message=from-cli, --demo.retries=7, orders.csv]
has message option = true
message option values = [from-cli]
non-option args = [orders.csv]
Environment demo.message = from-file
Environment demo.retries = 2
@Value demo.message = from-file
@ConfigurationProperties = from-file / 2
commandLineArgs present = false
```

This is the decisive experiment: **with the exact same `String[] args`**, `ApplicationArguments` still parses the **from-cli** option, yet `Environment` does not receive overrides from the command-line property source and falls back to **from-file**. `@Value` and `@ConfigurationProperties` follow `Environment`, not `getOptionValues` directly.

**The position of `-D` matters.** In the Java command, `-Dexample.disable-cli-properties=true` must appear before `-jar` for the JVM to treat it as a **Java system property**. If moved after the JAR name, it becomes an application argument and will not trigger `Boolean.getBoolean(...)` as written.

## 8. Comparing four channels for supplying a property

The same logical setting `demo.message` can be supplied through different channels:

| Channel | Example | Where read directly | Appears in `ApplicationArguments`? |
|---|---|---|---|
| Config file | `demo.message=from-file` in `application.properties` | Spring `Environment` | No |
| OS environment variable | `DEMO_MESSAGE=from-os` | OS process environment; Spring binder supports name mapping | No, unless you also pass it as an app arg |
| Java system property | `-Ddemo.message=from-jvm` **before `-jar`** | `System.getProperty` and Spring `Environment` | No |
| Spring Boot command-line option | `--demo.message=from-cli` **after JAR** | `ApplicationArguments`; by default also Spring `Environment` | Yes |

When multiple sources define the same key, `Environment` selects **the highest-precedence source**, regardless of which code happens to read the property first. In standard configuration, command-line options outrank Java system properties, OS environment variables, and files.

### Example using JVM system property

```bash
java -Ddemo.message=from-jvm -jar build/libs/cli-environment-demo-0.0.1-SNAPSHOT.jar
```

Without `--demo.message`, `ApplicationArguments.containsOption("demo.message")` remains `false`; yet `Environment.getProperty("demo.message")` can be `from-jvm`, overriding `from-file`.

### Example passing both simultaneously

```bash
java -Ddemo.message=from-jvm -jar build/libs/cli-environment-demo-0.0.1-SNAPSHOT.jar --demo.message=from-cli
```

In standard configuration, `Environment` picks `from-cli`, while `System.getProperty("demo.message")` remains `from-jvm`. **Spring does not write CLI options back into JVM system properties.**

### Gradle bootRun caveat

`./gradlew bootRun --args='--demo.message=from-cli'` passes options to **the application**. Meanwhile:

- `-Pname=value` is a Gradle project property and does not automatically become a Spring `Environment` property.
- `-Dname=value` is passed to the JVM running Gradle depending on context and is not always forwarded to the child JVM running the app under `bootRun`.
- Gradle options and application options are handled by two distinct parser layers.

To verify a Java system property accurately on **the application JVM**, the clearest approach is running the JAR via `java -D... -jar ...` as shown, or explicitly configuring `systemProperty` on Gradle's `bootRun` task.

## 9. Using --key=value to control the Spring Boot runtime

Not just custom properties: many Spring Boot keys use the exact same mechanism:

```bash
java -jar myapp.jar --spring.profiles.active=dev
```

```bash
java -jar myapp.jar --spring.application.name=order-service
```

```bash
java -jar myapp.jar --server.port=9090
```

```bash
java -jar myapp.jar --spring.main.web-application-type=none
```

Meaning:

- `spring.profiles.active` selects active profiles, which can affect which config data groups are loaded and which `@Profile` beans are created.
- `spring.application.name` sets the application name used across integrations/logging.
- `server.port` configures the web server port if the app initializes a supported web server.
- `spring.main.web-application-type` influences the application type when Spring Boot applies that configuration.

**Timing is essential.** Some keys like `spring.config.name`, `spring.config.location`, and `spring.config.additional-location` are read **very early** to locate config files. Passing them via CLI at launch is more appropriate than mutating `Environment` late after beans have been created.

If you call `application.setAddCommandLineProperties(false)`, do not be surprised when options present only on the CLI **no longer participate in setting up `Environment`**. Removing the command-line property source can affect bootstrap configuration as well, not just business `demo.*` properties.

Note: an explicit Java setter on `SpringApplication` and a property in `Environment` may interact according to specific Spring Boot binding/startup rules. **Do not infer precedence between a setter and a CLI property from `PropertySource` ordering**, because they are not two `PropertySource`s of the same kind. To study the exact `--key=value` to `Environment` relationship, isolate it from other bootstrap setters.

## 10. When to use ApplicationArguments instead of Environment?

**Use `ApplicationArguments` when the question is "what did the caller pass?"**

- Checking whether the operator explicitly passed `--dry-run`.
- Reading a positional argument like `report.csv`.
- Handling multiple occurrences of an option like `--tag=a --tag=b`.
- Distinguishing an absent option from a present valueless option.
- Reading the raw list of arguments passed to `SpringApplication.run(...)`, after applying necessary security checks.

**Use `Environment`, `@Value`, or `@ConfigurationProperties` when the question is "what is the effective application configuration?"**

- A property has a fallback from `application.properties`.
- A setting can be overridden via OS environment, Java `-D`, or CLI.
- Binding types like `int`, `Duration`, `DataSize`, enums, or a multi-field configuration object.
- Conditional bean/auto-configuration creation based on properties.
- Needing identical logic whether configuration comes from files, container environment, or command line.

Common pitfall:

```java
// Conceptual anti-pattern:
if (arguments.containsOption("demo.message")) {
    // Does not mean this is the only source providing demo.message.
}
```

If the property exists in a file or OS environment without a CLI option, `containsOption` is `false` yet the application still has configuration.

Conversely:

```java
// Conceptual anti-pattern:
String option = environment.getProperty("demo.message");
// This is not necessarily a value the operator passed on the CLI.
```

That value may come from a file or system properties, even when the command-line property source is disabled.

## 11. Edge cases: flags, empty values, repeats, typos, and data types

### 11.1. --flag is not synonymous with --flag=true

```bash
java -jar myapp.jar --dry-run
```

`ApplicationArguments.containsOption("dry-run")` is `true`; `getOptionValues("dry-run")` is an empty list because there is no `=value`. Do not claim `@ConfigurationProperties.booleanField` always becomes `true` under every parser just because the option appeared. If you need to check **flag presence**, `containsOption` is clearest; if you want boolean configuration via properties, use explicit syntax:

```bash
java -jar myapp.jar --demo.dry-run=true
```

and bind the corresponding boolean field. Also distinguish `--flag=`, where the value is an empty string that may not convert validly to the target type.

### 11.2. Repeating the same key

```bash
java -jar myapp.jar --tag=red --tag=blue
```

`ApplicationArguments.getOptionValues("tag")` returns a list containing both `red` and `blue`. If you need a list with clear semantics, process via `ApplicationArguments` or bind a proper collection type; do not assume single-valued CLI arguments always follow a "last value wins" rule as when merging multiple config files.

### 11.3. Misspelled property names

Spring Boot does not treat unrecognized options as errors by default. For example:

```bash
java -jar myapp.jar --demo.mesage=typo
```

If code only queries `demo.message`, it does not auto-correct `mesage` to `message`. An unknown option can exist in `Environment` with **no consumer** using it. Use consistent property names, generate configuration metadata when using `@ConfigurationProperties`, and verify/test critical keys.

Relaxed binding supports valid naming variants during binding, but **does not fix arbitrary typos** and does not mean every property-access API interprets every name form identically. With `@Value`, prefer canonical lowercase kebab-case names where appropriate.

### 11.4. Wrong data types

```bash
java -jar myapp.jar --demo.retries=banana
```

If `demo.retries` binds to the `int` in `DemoSettings` from section 7, Spring Boot cannot convert `"banana"` to an integer and startup may fail with a binding/conversion error. `Environment.getProperty("demo.retries")` as a string may still return `"banana"` prior to binding, which does not guarantee a numeric consumer will succeed.

Thus "property exists" and "property is valid for business configuration" are **two separate steps**. To fail fast with clear messages, add appropriate validation to `@ConfigurationProperties` in real projects; do not swallow errors and fall back silently to unchecked defaults.

### 11.5. Option names with dashes and dots

Property names should be grouped consistently:

```text
--demo.max-retries=5
--demo.api-timeout=3s
```

These keys express properties in readable canonical form and bind to matching fields when `@ConfigurationProperties` is configured properly. Calling `Environment.getProperty(...)` directly with a name differing in case/dashes may follow different rules than Boot's **relaxed binding**. To avoid confusion, the `demo.message` illustration uses the exact same name across CLI, file, `Environment`, `@Value`, and record.

### 11.6. Non-options do not override named properties automatically

```bash
java -jar myapp.jar orders.csv
```

`orders.csv` appears in `ApplicationArguments.getNonOptionArgs()`, yet does not automatically create a property `demo.file=orders.csv`. Some `CommandLinePropertySource` implementations can aggregate non-option args under a special property name; do not mistake that mechanism for **every positional argument automatically becoming an arbitrarily named property**.

### 11.7. Double-dash `--` in special positions

If a program uses the `--` separator argument, subsequent strings must not be treated arbitrarily as Spring options. When a command passes through multiple layers such as Gradle, a Docker entrypoint, a shell script, or a launcher, identify **which layer processes `--` first**. What matters most is the actual values reaching the application's `String[] args`—inspectable via `ApplicationArguments.getSourceArgs()` in a secret-free test environment.

## 12. Troubleshooting when CLI does not override configuration

When you ran `--demo.message=from-cli` yet the service still receives `from-file`, check systematically:

1. **Was the option passed properly?** Does the command place `--demo.message=from-cli` **after the JAR name** or inside `bootRun --args`? Or did you mistakenly pass `-D...`, `-P...`, or `--demo.message from-cli`?
2. **Did you call `SpringApplication.run(args)` properly?** A custom `main` calling `run(new String[0])` discards the CLI arguments received from the JVM.
3. **Was `setAddCommandLineProperties(false)` called?** If so, `ApplicationArguments` may still see the option, yet `Environment` receives no override from the CLI source.
4. **Is the key exact?** Check `demo.message`, dots, dashes, casing, and typos; with `@Value`, use the canonical name when relaxed binding applies.
5. **Did some consumer overwrite or freeze the value earlier?** Did a bean read the property early, copy it to a fixed field, or did other code modify/remove the property source?
6. **At what lifecycle phase are you measuring?** Checking inside a bean after `Environment` is prepared reflects runtime values. Do not read `Environment` at `ApplicationStartingEvent` before it is prepared.
7. **Are test/devtools/custom property sources active?** Test environments can add sources outranking CLI; do not assume runtime precedence applies unchanged to every test.
8. **Are multiple processes/replicas running?** You might be viewing logs or responses from a different instance than the one that received the new CLI args.

### Selectively inspecting sources in Environment

In a bean/test with `ConfigurableEnvironment environment`:

```java
for (var source : environment.getPropertySources()) {
    if (source.containsProperty("demo.message")) {
        System.out.println(
                source.getName() + " -> "
                + source.getProperty("demo.message"));
    }
}
```

This is an **integration snippet**, not a standalone runnable Java program. It is useful when finding which sources define a property. Printing all properties can expose secrets; **inspect only non-sensitive keys** and never enable configuration dumps in production.

If the project has Actuator configured and secured properly, the `/actuator/env` and `/actuator/configprops` endpoints help identify configuration sources/bindings; they may mask sensitive values by default and must be access-controlled. Never expose these endpoints publicly just to debug a parameter.

## 13. Security: command-line options leak more easily than you think

Do not pass passwords, private keys, tokens, or connection secrets on the CLI when safer mechanisms exist. Process arguments can show up in process listings, shell history, application/CI logs, deployment config files, operations scripts, or observability tools. Reading via `ApplicationArguments` or `Environment` **does not automatically make sensitive data safe**.

In the section 7 example code, we print args because all of them are non-sensitive dummy data. In real applications:

- Never log all of `getSourceArgs()` in production.
- Never print all of `Environment.getPropertySources()` or `SPRING_APPLICATION_JSON`.
- Use a secret-management mechanism, environment injection, or protected secret files depending on your platform (which also need permission and log controls).
- Use validation and error messages that omit sensitive values.
- Restrict external users from arbitrarily controlling sensitive properties such as management endpoints, logging, or profiles.

`--key=value` is **a convenient configuration mechanism**, not an authorization or security boundary.

## 14. Self-verification exercises

Use the `cli-environment-demo` project from section 7. Run each exercise separately and compare **both channels** `ApplicationArguments` and `Environment`:

**Exercise A — no CLI arguments:** run `./gradlew bootRun`. Explain why `containsOption("demo.message") == false` while `Environment` still returns `from-file`.

**Exercise B — overriding the file:** run with `--demo.message=from-cli --demo.retries=7 orders.csv`. Verify `ApplicationArguments`, `Environment`, `@Value`, and `DemoSettings` all reflect their proper data sources; distinguish positional `orders.csv`.

**Exercise C — CLI precedence vs. JVM system property:** run the JAR with `-Ddemo.message=from-jvm` and `--demo.message=from-cli`. Read both `System.getProperty("demo.message")` and `Environment.getProperty("demo.message")` inside the runner; explain why the two results can differ.

**Exercise D — disabling the command-line property source:** run the `-Dexample.disable-cli-properties=true` example from section 7. Explain why `ApplicationArguments` still has `from-cli` while the config object and `@Value` still use `from-file`.

**Exercise E — option missing a value:** pass `--demo.message other-file.csv`. Inspect `getOptionValues("demo.message")` and `getNonOptionArgs()`. Observe how config binding reacts to a valueless option; do not assume `other-file.csv` becomes the value of `demo.message`.

**Exercise F — wrong type:** pass `--demo.retries=not-a-number`. Identify the exception and failing binding step rather than interpreting it as "Environment ignored the option".

**Exercise G — adding a new setting:** add `demo.feature-enabled=false` in the file and a matching boolean field to the record. Override with `--demo.feature-enabled=true`, and read via `Environment` and `@ConfigurationProperties`. Ensure property/field names follow relaxed binding rules.

**Exercise H — repeating options:** pass `--tag=a --tag=b` and read via `ApplicationArguments.getOptionValues("tag")`. Explain why having a two-value list does not mean every consumer automatically gets a typed array as expected.

### Self-assessment questions

1. By what mechanism is `--server.port=9090` added to `Environment` by default?
2. If both `application.properties` and the CLI define `demo.message`, which source wins in default runtime? Is the original file modified?
3. Why can `ApplicationArguments.containsOption("demo.message")` be `false` while `Environment.getProperty("demo.message")` has a value?
4. What is the difference between `--key=value`, `-Dkey=value`, and an OS environment variable?
5. Is `--name Lan` equivalent to `--name=Lan`? How does the parser classify `Lan`?
6. When calling `setAddCommandLineProperties(false)`, is `ApplicationArguments.getSourceArgs()` cleared?
7. Why does key `demo.retries` hold `"banana"` in `Environment` while binding to `int` fails?
8. When should you use `@ConfigurationProperties` instead of manually parsing `String[] args`?
9. Does a CLI-supplied property guarantee an effect in every module? Why or why not?
10. Why should arguments containing secrets never be printed to logs?

Answering these questions and verifying them with the program helps you distinguish **command-line inputs**, **Spring property sources**, **override precedence**, and **consuming bound configuration**.

## 15. Decision summary

| What you need to know | Appropriate API/mechanism |
|---|---|
| Did the user explicitly pass `--dry-run`? | `ApplicationArguments.containsOption("dry-run")` |
| Which multiple `--tag=value` values did the user pass? | `ApplicationArguments.getOptionValues("tag")` |
| What are unnamed parameters like filenames? | `ApplicationArguments.getNonOptionArgs()` |
| Effective property after considering files, env, and CLI? | `Environment.getProperty("key")` |
| Bind a group of properties into a typed object? | `@ConfigurationProperties` |
| Inject a single property into a bean? | `@Value("${key}")` |
| Prevent CLI from auto-overriding `Environment`? | `SpringApplication.setAddCommandLineProperties(false)` **before run** |
| Know which source supplied a property? | Inspect `ConfigurableEnvironment.getPropertySources()`, with security controls |
| Add a property source earlier than bean creation? | `EnvironmentPostProcessor` or an appropriate Spring Boot config mechanism |

**Conclusion:** under default configuration, `--key=value` enters `SpringApplication.run(args)`, is parsed into an option, and is placed into a `PropertySource` of `Environment` that outranks configuration files. Therefore `Environment`, `@Value`, and `@ConfigurationProperties` see the overridden value. `ApplicationArguments` is the API for reading **raw/parsed arguments**, not a mirror of effective configuration; disabling the command-line property source does not erase those arguments.

## Official references

- Spring Boot 3.3, Externalized Configuration — source order and *Accessing Command Line Properties*: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3, `SpringApplication` — *Accessing Application Arguments*: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html
- Spring Boot 3.3, `ApplicationArguments` API: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/ApplicationArguments.html
- Spring Framework 6.1, `SimpleCommandLinePropertySource`: https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/core/env/SimpleCommandLinePropertySource.html
- Spring Framework, `Environment` and `ConfigurableEnvironment`: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/core/env/ConfigurableEnvironment.html