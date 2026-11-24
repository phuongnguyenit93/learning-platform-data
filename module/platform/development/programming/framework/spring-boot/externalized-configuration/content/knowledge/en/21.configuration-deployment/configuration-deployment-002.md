# Running from IDE, bootRun, and java -jar with the Same Configuration Contract

## 1. Lesson Objective

A Spring Boot application is typically launched in several ways across its development lifecycle:

- **From an IDE:** developers click Run/Debug to develop and set breakpoints.
- **With Gradle `bootRun`:** the development team runs the application from a terminal or automation script.
- **With `java -jar`:** the operations team runs the packaged executable JAR, closely matching real deployment.

Each launch method differs in **launcher, classpath, working directory, argument passing, and process environment**. However, they can—and should—use the **same configuration contract**.

"Configuration contract" here means:

1. The application exposes the **same set of property names**, such as `delivery.endpoint`, `delivery.timeout`, `delivery.max-attempts`, and `delivery.enabled`.
2. Properties bind to the **same Java types**, such as `URI`, `Duration`, `int`, and `boolean`.
3. Required values, default values, validation, and error handling **do not change based on the launcher**.
4. Differences between dev, test, and production come from **configuration source values** and the active profile, not from writing three different property-reading code paths.
5. You can verify which values the application actually sees on each run.

High-level view:

```text
                         SAME CONTRACT
                   delivery.endpoint: URI
                   delivery.timeout: Duration
                   delivery.max-attempts: int
                   delivery.enabled: boolean
                                |
                 +--------------+--------------+
                 |              |              |
                IDE          bootRun         java -jar
                 |              |              |
                 +--------------+--------------+
                                |
                         Spring Environment
                                |
                   ConfigurationProperties Binder
                                |
                    DeliveryProperties bean
                                |
                         DeliveryService
```

**Key idea:** do not write branches like "if running from IDE then read key A, if running JAR then read key B." Let Spring Boot handle configuration sources and keep property names and binding rules consistent.

## 2. What Changes and What Does Not

| Aspect | IDE | Gradle bootRun | java -jar |
| --- | --- | --- | --- |
| How it starts | IDE Run configuration | Gradle task running the app | JVM running the executable JAR |
| Classpath | Project compiled output/resources | Task runtime classpath | Classes and dependencies inside the JAR |
| Program arguments | Program arguments field | `--args=...` of `bootRun` | Arguments after the JAR path |
| JVM system properties | VM options field | Task JVM config, or as Gradle passes to the app process | `-Dkey=value` **before** `-jar` |
| Environment variables | Run configuration Environment field or inherited environment | Gradle and Java app process environment, unless modified | Launching shell/service environment |
| Working directory | Determined by Run configuration | Per Gradle task configuration, usually project directory | Current directory of shell/service |
| Config Data on classpath | From project build output | From Gradle runtime classpath | From resources packaged in the JAR |
| Profiles/source precedence | Per Spring Environment | Per Spring Environment | Per Spring Environment |
| `@ConfigurationProperties`/validation | Same logic | Same logic | Same logic |

The biggest difference is usually the **actual inputs** to the run, not Spring Boot having a separate binder for the IDE and another for the JAR.

In all three cases, Spring Boot can still read `application.yml` on the classpath, receive environment variables, command-line arguments, and appropriate additional configuration locations.

## 3. Building a Single Configuration Contract

Suppose the application has a notification delivery service. We use the prefix `delivery`.

Keys:

| Canonical key | Java type | Required? | Meaning |
| --- | --- | --- | --- |
| `delivery.endpoint` | `URI` | Yes | Endpoint to send requests to |
| `delivery.timeout` | `Duration` | Yes | Wait timeout |
| `delivery.max-attempts` | `int` | Positive value | Number of attempts allowed |
| `delivery.enabled` | `boolean` | Has default | Enable/disable the feature |
| `delivery.channel` | `String` | Yes | Notification channel name |

Names are in **lowercase, kebab-case**. This is the recommended form in YAML/Properties and Spring Boot contract documentation.

In Java code, properties usually use camelCase, such as `maxAttempts`. The Binder supports relaxed binding for valid name variants, though it does not automatically fix every typo.

### 3.1. Defining the configuration record

```java
package com.example.configdemo;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotNull URI endpoint,
        @NotNull Duration timeout,
        @Min(1) int maxAttempts,
        @DefaultValue("true") boolean enabled,
        @NotBlank String channel) {
}
```

Key points:

- `@ConfigurationProperties(prefix = "delivery")` defines a group of properties.
- `@NotNull` requires `endpoint` and `timeout` to have values.
- `@Min(1)` requires `maxAttempts` to be at least 1.
- `@DefaultValue("true")` provides a default for `enabled` if the property is absent in the sources considered by the binder.
- `@NotBlank` rejects `null`, empty strings, or whitespace-only strings for `channel`.
- A record uses constructor binding; no setters are needed for components.

With Spring Boot 3.x, these validation annotations use the `jakarta.validation.*` package; projects typically need `spring-boot-starter-validation` to execute Bean Validation.

This is **a single configuration contract**, used regardless of how the application is launched.

### 3.2. Registering ConfigurationProperties

```java
package com.example.configdemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConfigDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigDemoApplication.class, args);
    }
}
```

Place the record in a package scanned by `@ConfigurationPropertiesScan`.

You can use `@EnableConfigurationProperties(DeliveryProperties.class)` instead if you want explicit registration. Do not annotate the record with `@Component` just so Spring discovers it through normal component scanning.

## 4. Preparing Shared Configuration Files

In a Java/Gradle project:

```text
src/
  main/
    java/
      com/example/configdemo/
        ConfigDemoApplication.java
        DeliveryProperties.java
        DeliveryService.java
        DeliveryConfigPrinter.java
    resources/
      application.yml
      application-dev.yml
      application-prod.yml
build.gradle
settings.gradle
gradlew
gradlew.bat
```

### 4.1. Default configuration

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: config-demo

delivery:
  endpoint: "https://delivery.example.invalid"
  timeout: 5s
  max-attempts: 3
  enabled: true
  channel: "default"
```

This is the base configuration with keys matching the record. The endpoint uses the `example.invalid` domain for illustration; the program does not actually need to connect to that address in this lesson.

### 4.2. Dev configuration

```yaml
# src/main/resources/application-dev.yml
delivery:
  timeout: 2s
  max-attempts: 2
  channel: "development"
```

The dev file specifies values that differ from the defaults. Other keys such as `delivery.endpoint` and `delivery.enabled` can keep the values from the common file if no higher-precedence source overrides them.

### 4.3. Production configuration

```yaml
# src/main/resources/application-prod.yml
delivery:
  timeout: 10s
  max-attempts: 5
  channel: "production"
```

In real deployments, production endpoints, tokens, and secrets can be supplied from environment variables or a secret system rather than packaged directly in the JAR. The content here only illustrates profile-specific configuration.

**Do not put `spring.profiles.active: prod` inside `application-prod.yml`.** The profile should be activated from an allowed source during configuration preparation, such as launch arguments or an environment variable.

## 5. Creating a Service That Reads the Bound Configuration

```java
package com.example.configdemo;

import org.springframework.stereotype.Service;

@Service
public class DeliveryService {

    private final DeliveryProperties properties;

    public DeliveryService(DeliveryProperties properties) {
        this.properties = properties;
    }

    public boolean canSend() {
        return properties.enabled()
                && properties.maxAttempts() >= 1;
    }

    public String describe() {
        return "endpoint=" + properties.endpoint()
                + ", timeout=" + properties.timeout()
                + ", maxAttempts=" + properties.maxAttempts()
                + ", enabled=" + properties.enabled()
                + ", channel=" + properties.channel();
    }
}
```

Here `DeliveryService` does not care whether the application was launched from the IDE, `bootRun`, or a JAR. It simply receives `DeliveryProperties` via constructor injection.

This reduces the risk of having three different places reading configuration:

```java
// Do not put this kind of logic in a service:
if (isIdeRun()) {
    // Read a separate dev file.
} else if (isGradleRun()) {
    // Read a different variable name.
} else {
    // Read a path relative to the JAR.
}
```

Treat the launcher as the way to start the Java process, and `Spring Environment` as the mechanism that supplies configuration values to the application.

## 6. Observing Actual Configuration at Runtime

For learning and verifying the technique, create a runner that prints **illustrative non-sensitive values**.

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class DeliveryConfigPrinter implements ApplicationRunner {

    private final DeliveryProperties properties;
    private final Environment environment;

    public DeliveryConfigPrinter(
            DeliveryProperties properties,
            Environment environment) {
        this.properties = properties;
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println("activeProfiles="
                + String.join(",", environment.getActiveProfiles()));
        System.out.println("endpoint=" + properties.endpoint());
        System.out.println("timeout=" + properties.timeout());
        System.out.println("maxAttempts=" + properties.maxAttempts());
        System.out.println("enabled=" + properties.enabled());
        System.out.println("channel=" + properties.channel());
    }
}
```

With the base configuration and no specific profile activated, illustrative output:

```text
activeProfiles=
endpoint=https://delivery.example.invalid
timeout=PT5S
maxAttempts=3
enabled=true
channel=default
```

With the `dev` profile:

```text
activeProfiles=dev
endpoint=https://delivery.example.invalid
timeout=PT2S
maxAttempts=2
enabled=true
channel=development
```

With the `prod` profile:

```text
activeProfiles=prod
endpoint=https://delivery.example.invalid
timeout=PT10S
maxAttempts=5
enabled=true
channel=production
```

`PT5S` and `PT2S` are the ISO-8601 representations of `Duration`, rather than the raw YAML strings `5s` or `2s`.

**Do not print the entire configuration bean in real systems if the bean contains passwords, tokens, or access keys.** Log only property names, necessary status, or non-sensitive values.

## 7. Preparing build.gradle for bootRun and bootJar

`bootRun` is a task provided by the **Spring Boot Gradle plugin**. If a project only applies the `java` plugin without the appropriate Spring Boot plugin, the `bootRun` task may not exist.

Illustrative Groovy DSL skeleton:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
    id 'io.spring.dependency-management' version '<compatible-version>'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The snippet above is a **structural skeleton** that intentionally uses version placeholders rather than assuming the project's Spring Boot/Gradle version. In a real project, replace them with compatible versions already managed in the existing build, or use the corresponding official plugin configuration. Do not copy placeholders verbatim into a file and expect Gradle to run.

If the project already has a `build.gradle`, you usually only need to verify the Spring Boot plugin and validation dependency; there is no need to rewrite the whole file.

With the Spring Boot plugin properly configured, common tasks include:

```text
bootRun    run the application via Gradle
bootJar    package an executable JAR
build      run the build lifecycle, including tests and packaging per configuration
```

Run:

```bash
./gradlew tasks
```

to find the tasks present in the project. On Windows PowerShell, use `.\gradlew.bat tasks`.

## 8. Method 1 — Running from an IDE

In IntelliJ IDEA, Eclipse/STS, or VS Code with Java/Spring Boot support, you typically create a **Run configuration** pointing to the main class:

```java
com.example.configdemo.ConfigDemoApplication
```

Common fields may be named things like:

| Run configuration field | Example | Meaning |
| --- | --- | --- |
| Main class | `com.example.configdemo.ConfigDemoApplication` | Entry point |
| Program arguments | `--spring.profiles.active=dev` | Arguments passed to `main(String[] args)` |
| VM options | `-Dspring.profiles.active=dev` | JVM Java system property |
| Environment variables | `DELIVERY_MAXATTEMPTS=4` | Process environment variable |
| Working directory | Project/module directory | Relative root when reading files outside classpath |
| Module/classpath | Module containing the app | Classes and resources when running |

Field names and UI placement vary across IDEs/extensions. What matters is distinguishing **Program arguments**, **VM options**, and **Environment variables**; they are not the same kind of input.

### 8.1. IDE Program arguments

In the Run configuration, set:

```text
--spring.profiles.active=dev --delivery.max-attempts=4
```

When the IDE invokes the main class, these arguments are passed into `SpringApplication.run(..., args)`.

If no higher-precedence source is present, the app uses the `dev` profile, while `delivery.max-attempts=4` from program arguments overrides `max-attempts: 2` in the dev file.

Result:

```text
activeProfiles=dev
timeout=PT2S
maxAttempts=4
channel=development
```

### 8.2. IDE VM options

If instead you set:

```text
-Dspring.profiles.active=dev -Ddelivery.max-attempts=4
```

in the VM options field, the IDE passes **Java system properties** to the JVM.

Technical difference:

- `--spring.profiles.active=dev` is an application argument processed by Spring Boot as a command-line property.
- `-Dspring.profiles.active=dev` is a JVM option, creating a system property.

In Spring Boot's default order, **command-line arguments usually have higher precedence than Java system properties**. Therefore, do not pass the same key with two different values and assume they are completely equivalent.

### 8.3. IDE Environment variables

Example setting:

```text
SPRING_PROFILES_ACTIVE=dev
DELIVERY_MAXATTEMPTS=4
```

Environment variables must be passed into **the exact Java process launched by the IDE**. Setting a variable in a terminal window does not mean an already-open IDE will automatically see that variable.

If the IDE supports an Environment field, declare variables directly there to avoid differences in shell environment inheritance.

### 8.4. IDE Working directory

Some IDEs use the project directory as the working directory; others use the module directory or a user-selected path.

If external configuration outside the JAR is located at:

```text
./config/application.yml
```

then `./` depends on the process working directory. Running the IDE with a different working directory may prevent the app from finding the same file that `java -jar` uses.

Do not rely on a relative path that is undefined in the deployment contract.

## 9. Method 2 — Running with Gradle bootRun

When the project uses the Spring Boot Gradle plugin, you can run the application with:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

`bootRun` launches the Java application using the runtime classpath constructed by Gradle for the app. In development mode, it typically uses the module's compiled class outputs and resources rather than running a packaged executable JAR.

### 9.1. Passing program arguments via --args

With Gradle, the standard way is:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

To add more overrides:

```bash
./gradlew bootRun \
  --args='--spring.profiles.active=dev --delivery.max-attempts=4'
```

The backslash is used for line continuation in Linux/macOS shells. If copying to Windows PowerShell, put the entire command on a single line:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev --delivery.max-attempts=4"
```

Note argument placement:

- `--args=...` is a Gradle option for JavaExec/`bootRun`-type tasks.
- The string inside `--args` contains the actual application arguments, such as `--delivery.max-attempts=4`.

Do not write:

```bash
./gradlew bootRun --delivery.max-attempts=4
```

expecting Gradle to understand it as an application argument. Gradle will attempt to parse it as a Gradle option if the syntax is wrong.

### 9.2. Environment variables with bootRun

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=dev \
DELIVERY_MAXATTEMPTS=4 \
./gradlew bootRun
```

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:DELIVERY_MAXATTEMPTS = "4"
.\gradlew.bat bootRun
```

These variables live in the Gradle process environment and are normally inherited by the Java process launched by the task, unless the task or script actively modifies the child process environment.

In PowerShell, values set with `$env:...` persist in that shell session and are inherited by child programs launched from that shell. Do not expect them to propagate automatically to every IDE or other terminal.

### 9.3. Program arguments vs. Gradle JVM arguments

A common mistake:

```bash
./gradlew -Ddelivery.max-attempts=4 bootRun
```

The `-D...` option on the Gradle command may set a **system property for the Gradle process**, and does not necessarily pass the same system property to the **application JVM** created by the `bootRun` task.

If you want to supply configuration values to the app cleanly and explicitly, prefer:

```bash
./gradlew bootRun --args='--delivery.max-attempts=4'
```

Or explicitly configure `systemProperty`/`jvmArgs` on the `bootRun` task in `build.gradle` if a JVM system property is needed.

Example:

```groovy
tasks.named('bootRun') {
    systemProperty 'delivery.max-attempts', '4'
}
```

This fixes the value when running through the task, so **it should not be used for environment-varying configuration** unless there is an appropriate value-supplying mechanism. Avoid "hard-wiring" production config in Gradle just for local convenience.

## 10. Method 3 — Running the Executable JAR with java -jar

With Gradle, package using:

```bash
./gradlew clean bootJar
```

On Windows:

```powershell
.\gradlew.bat clean bootJar
```

The executable JAR is typically created in:

```text
build/libs/
```

The filename depends on the project name, version, and task configuration. For example, an artifact might be named:

```text
build/libs/config-demo-1.0.0.jar
```

Do not assume this name is always exact in a real project; list the output of `build/libs/` after building.

### 10.1. Running without arguments

```bash
java -jar build/libs/config-demo-1.0.0.jar
```

If the JAR contains `application.yml` on the classpath and no other source overrides it, the application receives the base configuration.

### 10.2. Passing program arguments

```bash
java -jar build/libs/config-demo-1.0.0.jar \
  --spring.profiles.active=dev \
  --delivery.max-attempts=4
```

On PowerShell, use a single line:

```powershell
java -jar .\build\libs\config-demo-1.0.0.jar --spring.profiles.active=dev --delivery.max-attempts=4
```

Here the two arguments after the JAR name are passed to the application's `main(String[] args)` and processed by `SpringApplication.run(..., args)` according to the default mechanism.

**Important:** application arguments go **after** the JAR path.

### 10.3. Passing Java system properties

```bash
java -Dspring.profiles.active=dev \
     -Ddelivery.max-attempts=4 \
     -jar build/libs/config-demo-1.0.0.jar
```

`-D...` are JVM options, so they must appear **before `-jar`** if you want the JVM to process them as Java system properties.

If you write:

```bash
java -jar build/libs/config-demo-1.0.0.jar \
  -Ddelivery.max-attempts=4
```

then `-Ddelivery.max-attempts=4` **after** the JAR is no longer a JVM option under `java` invocation rules. It becomes an argument passed to the application; Spring Boot does not automatically treat it as a Java system property.

This is a frequent mistake when transferring settings from an IDE's VM options box into a shell command.

### 10.4. Passing environment variables

Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=dev \
DELIVERY_MAXATTEMPTS=4 \
java -jar build/libs/config-demo-1.0.0.jar
```

PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = "dev"
$env:DELIVERY_MAXATTEMPTS = "4"
java -jar .\build\libs\config-demo-1.0.0.jar
```

When using systemd, containers, or another deployment platform, environment variables must be declared inside the **service/container configuration** itself. An operator running `export` in another terminal does not guarantee the system-managed service process receives that variable.

## 11. Three Launch Methods, One Concrete Example

Requirement: run the application with the `dev` profile, set `delivery.max-attempts=4`, and still use `delivery.timeout=2s` from `application-dev.yml`.

### IDE

In Program arguments:

```text
--spring.profiles.active=dev --delivery.max-attempts=4
```

### Gradle bootRun

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --delivery.max-attempts=4'
```

### java -jar

```bash
java -jar build/libs/config-demo-1.0.0.jar \
  --spring.profiles.active=dev \
  --delivery.max-attempts=4
```

When all three launch **the same code and equivalent effective configuration sources**, the resulting `DeliveryProperties` should be equivalent:

```text
endpoint=https://delivery.example.invalid
timeout=PT2S
maxAttempts=4
enabled=true
channel=development
```

This result is **expected given the data declared in the lesson**, not a guarantee that every IDE or CI in every project has identical classpath and environment variables. If results differ, check the actual sources and arguments passed into the process.

## 12. Unifying the Contract Does Not Mean Identical Data Sources

The three launch methods can supply values from different sources while still obeying the same contract.

Example:

| Launch method | Source for `delivery.max-attempts` | Value |
| --- | --- | --- |
| IDE | Program arguments | `4` |
| bootRun | Environment variable `DELIVERY_MAXATTEMPTS` | `4` |
| java -jar | Argument `--delivery.max-attempts=4` | `4` |

The essence of the contract remains:

```text
delivery.max-attempts -> int maxAttempts, minimum 1
```

The sources only differ in how the value is represented and transported.

Having the same contract lets the operations team change how configuration is supplied without **modifying business code**.

However, do not rigidly dictate that "IDE always uses program arguments," "Gradle always uses environment variables," or "JAR always uses CLI." All three launch methods can use multiple Spring Boot sources; pick conventions suited to your environment and document them clearly in deployment docs.

## 13. Precedence Order When a Key Appears Multiple Times

Suppose:

```yaml
# application.yml
delivery:
  max-attempts: 3
```

```yaml
# application-dev.yml
delivery:
  max-attempts: 2
```

And when running the application:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --delivery.max-attempts=8
```

In standard Spring Boot, the application argument `--delivery.max-attempts=8` takes precedence over the Config Data value in the dev file. The result is `8`.

This does not change between IDE and `bootRun` if they supply the same command-line property.

A simple diagram:

```text
application.yml           delivery.max-attempts = 3
application-dev.yml       delivery.max-attempts = 2
command-line arguments    delivery.max-attempts = 8
                                     |
                                     v
                              Effective value
                                     8
                                     |
                                     v
                              DeliveryProperties
```

**Caution:** Spring Boot's complete precedence order includes many other sources such as test properties, system properties, environment variables, and special sources. This lesson only mentions the relationships relevant to comparing the three launch methods. When resolving concrete conflicts, inspect the actual `PropertySource`s.

## 14. Profiles Are Activated Under the Same Contract

Spring Boot uses profiles to load documents or configuration intended for the appropriate environment.

Example:

```yaml
# application-dev.yml
delivery:
  channel: "development"
```

Activate the profile using one of these mechanisms:

**IDE Program arguments**

```text
--spring.profiles.active=dev
```

**bootRun**

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

**JAR**

```bash
java -jar app.jar --spring.profiles.active=dev
```

Or using an environment variable:

```text
SPRING_PROFILES_ACTIVE=dev
```

All three use the same standard configuration key `spring.profiles.active`, rather than three independent "IDE profile," "Gradle profile," and "JAR profile" mechanisms.

### 14.1. Default profile

If no active profile is declared, Spring Boot has a default profile mechanism (usually named `default`) for applicable cases. `Environment#getActiveProfiles()` may return an empty array when no profile is explicitly activated.

**Do not print an empty `getActiveProfiles()` and conclude Spring did not load `application.yml`.** The base file can still load normally.

### 14.2. Do not mix profile with launch method

A production JAR can still run with the `dev` profile if its startup configuration requests it; this does not depend on the artifact having been built with `bootJar`.

Conversely, an IDE can also run with the `prod` profile when testing production configuration paths—provided the required data and access permissions are supplied safely.

A profile is **a configuration property of a startup run**, not a label automatically inferred from the launch tool.

## 15. Environment Variables: Canonical Naming

Spring Boot has a mechanism to map property names to environment variables.

With the canonical name:

```text
delivery.max-attempts
```

a typical environment variable form is:

```text
DELIVERY_MAXATTEMPTS
```

The standard rule is:

1. Dots `.` become underscores `_`.
2. Hyphens `-` are removed.
3. Letters are converted to uppercase.

Examples:

| Spring Boot key | Environment variable |
| --- | --- |
| `delivery.endpoint` | `DELIVERY_ENDPOINT` |
| `delivery.timeout` | `DELIVERY_TIMEOUT` |
| `delivery.max-attempts` | `DELIVERY_MAXATTEMPTS` |
| `delivery.enabled` | `DELIVERY_ENABLED` |
| `delivery.channel` | `DELIVERY_CHANNEL` |
| `spring.profiles.active` | `SPRING_PROFILES_ACTIVE` |

Example on Linux/macOS:

```bash
SPRING_PROFILES_ACTIVE=dev \
DELIVERY_TIMEOUT=3s \
DELIVERY_MAXATTEMPTS=4 \
./gradlew bootRun
```

When the binder binds `DeliveryProperties`, it can take `timeout=3s` from the environment instead of `2s` from the dev file, because environment variables have higher precedence than Config Data in standard Spring Boot configuration.

**Note:** `DELIVERY_MAX_ATTEMPTS` is not necessarily equivalent to `DELIVERY_MAXATTEMPTS` across every Spring Boot name-mapping rule. Follow the documented canonical form and verify the effective value with a real test.

## 16. Program Arguments, VM Options, and Environment Differ

This is the easiest place to make a mistake when translating an IDE Run configuration to a shell command.

| Mechanism | Syntax | Placement |
| --- | --- | --- |
| Program argument | `--delivery.timeout=4s` | After JAR name or in Program arguments |
| Java system property | `-Ddelivery.timeout=4s` | Before `-jar` or in VM options |
| Environment variable | `DELIVERY_TIMEOUT=4s` | Process environment |
| Config Data | `delivery.timeout: 4s` | Loaded YAML/Properties |

Standard JVM command example:

```bash
java -Ddelivery.timeout=4s \
     -jar app.jar \
     --delivery.max-attempts=5
```

In this command line:

- `delivery.timeout` is supplied as a Java system property;
- `delivery.max-attempts` is supplied as a command-line property.

If the application permits command-line properties by default, they usually take higher precedence than Java system properties when the **same key** appears in both sources.

The crux is that **not every flag appearing after `java` is read by Spring Boot in the same way**.

## 17. Working Directory and External Files Outside the JAR

One common cause of "runs fine in the IDE, but `java -jar` does not read the right config" is the **working directory**.

Suppose you have:

```text
workspace/
  config/
    application.yml
  app/
    build/
      libs/
        config-demo-1.0.0.jar
```

If the shell is in `workspace/` and runs:

```bash
java -jar app/build/libs/config-demo-1.0.0.jar
```

then `./config/application.yml` can be checked by Spring Boot among the default external classpath locations, depending on Config Data rules and layout.

But if you change directories:

```bash
cd app
java -jar build/libs/config-demo-1.0.0.jar
```

then `./config/` now points to:

```text
workspace/app/config/
```

and is no longer `workspace/config/`.

This explains why the **same JAR** run from two different working directories can receive two different sets of configuration.

### 17.1. Recommendations for teams

In deployment documentation, specify:

- Allowed working directory.
- Whether external config outside the JAR lives under `./config/`.
- Whether paths are supplied via environment or command-line property.
- Whether launching from a service/container sets an appropriate working directory.
- Fallback behavior when the file does not exist.

Do not rely on "it works on my machine" when the working directory is not standardized.

## 18. Using spring.config.additional-location to Unify External Files

When you want to add a configuration directory outside the default locations, Spring Boot supports:

```text
spring.config.additional-location
```

For example, placing configuration at:

```text
/opt/config-demo/runtime-config/application.yml
```

On Linux/macOS, run:

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/opt/config-demo/runtime-config/
```

For directory locations, the trailing `/` is meaningful: Spring Boot treats it as a directory and searches for matching `application.*` files according to Config Data rules.

The `optional:` keyword lets the application continue when the config location does not exist in cases permitted by Config Data, instead of failing solely because the location is missing.

**Distinction:**

- `spring.config.location` replaces the default search locations according to Boot's mechanism.
- `spring.config.additional-location` adds locations alongside the standard ones.

If the goal is to supplement configuration outside the JAR **while keeping default files on the classpath**, `additional-location` is usually more suitable.

### 18.1. Using the same location across all three launch methods

If IDE, `bootRun`, and `java -jar` all need to read the same directory, pass the same location value:

**IDE Program arguments**

```text
--spring.config.additional-location=optional:file:/opt/config-demo/runtime-config/
```

**bootRun**

```bash
./gradlew bootRun \
  --args='--spring.config.additional-location=optional:file:/opt/config-demo/runtime-config/'
```

**JAR**

```bash
java -jar app.jar \
  --spring.config.additional-location=optional:file:/opt/config-demo/runtime-config/
```

This is a Linux path example. On Windows, use valid Windows paths and appropriate URL/Config Data syntax, and remember quoting if paths contain spaces.

If you simply want to avoid working directory differences, **absolute paths** are usually easier to reason about than `./runtime-config/`.

### 18.2. Configuration must be supplied early enough

Properties such as `spring.config.location`, `spring.config.additional-location`, or `spring.config.name` affect the **Config Data loading phase**. They must be supplied from an appropriate source early enough, such as an environment variable, Java system property, or command-line argument.

Do not expect that setting `spring.config.additional-location` inside a `@PostConstruct` bean will make Boot go back to the Config Data loading phase and reload the directory.

## 19. Classpath application.yml vs. External Files Outside the JAR

When a project is built into an executable JAR, a file:

```text
src/main/resources/application.yml
```

is typically packaged under:

```text
BOOT-INF/classes/application.yml
```

in the standard executable JAR layout.

You can inspect it:

```bash
jar tf build/libs/config-demo-1.0.0.jar
```

On Linux/macOS:

```bash
jar tf build/libs/config-demo-1.0.0.jar | grep 'application.yml'
```

On PowerShell:

```powershell
jar tf .\build\libs\config-demo-1.0.0.jar |
    Select-String 'application\.yml'
```

If the expected config file is missing from the JAR, check your source set/resource processing configuration and the actual artifact.

Conversely, even when the JAR contains `application.yml`, an operator can still supply **a higher-precedence source** externally, such as environment variables or Config Data in a higher-precedence location.

**Packaging a file in the JAR does not mean values in that file always win.**

## 20. Same Source Code, Different Artifact Versions

Another issue less related to Spring Environment: the IDE may run the latest code in the project, while `java -jar` is running **a JAR built yesterday**.

Example:

- The IDE reads a record that has the new `delivery.channel` field.
- The old executable JAR still contains a version of `DeliveryProperties` without that field.
- Both use the same `application.yml`, yet the actual class contract is not the same.

Therefore, when comparing the three launch methods, confirm:

1. Source code is saved.
2. The artifact has been rebuilt.
3. You are running the exact JAR just built.
4. You are using the same module/dependency versions.
5. No stale application process is still running on the port or as another service.

A reproducible build command:

```bash
./gradlew clean bootJar
```

helps clear out stale classes/resources from build output, though it does not replace verifying which JAR path is used in deployment.

## 21. Building the JAR and Running the JAR Are Not the Same Thing

Two commands:

```bash
./gradlew bootJar
java -jar build/libs/config-demo-1.0.0.jar
```

perform two separate steps:

1. `bootJar` creates the artifact based on code and build configuration.
2. `java -jar` creates a new Java process and reads configuration sources at runtime.

Environment variables used during the **build process** do not automatically become environment variables of the **JAR execution process** on another machine or container.

Likewise, a value declared in a Gradle script to affect `bootRun` does not necessarily become a default inside the packaged JAR.

If a project wants the same configuration contract in production, ensure the artifact has the same Java model and runtime configuration is provided via a Boot-supported source, rather than relying on side effects of the shell used for building.

## 22. A .env File Is Not Loaded Automatically Just Because It Sits Next to the JAR

A common situation:

```text
project/
  .env
  build/libs/app.jar
```

Contents:

```dotenv
DELIVERY_MAXATTEMPTS=4
SPRING_PROFILES_ACTIVE=dev
```

A file named `.env` is **not automatically loaded by Spring Boot as environment variables** merely because it sits in the project or next to the JAR.

There are development tools, Docker Compose, shell scripts, or external libraries that support reading `.env` files. However, some component must actively read it and inject the data into the **Java process environment** or an appropriate `PropertySource`.

Examples:

- An IDE may support a `.env` plugin, which is a plugin capability, not a default mechanism.
- Docker Compose has its own rules for variable substitution and `env_file` when configured.
- A shell script can export environment variables before invoking Java.
- A dedicated configuration library can load dotenv per project design.

**The right contract is not "always have a .env file," but "the application needs canonical keys, and we must know who is responsible for supplying them to the process."**

For production secrets, do not write tokens or passwords into a `.env` file and commit it to the repository.

## 23. Verifying Consistency via the Same Set of Environment Variables

To test all three launch methods with the same values, you can use environment variables:

```text
SPRING_PROFILES_ACTIVE=dev
DELIVERY_TIMEOUT=3s
DELIVERY_MAXATTEMPTS=4
DELIVERY_CHANNEL=smoke-test
```

From the IDE, supply the four variables in the Run configuration.

From a Linux/macOS terminal:

```bash
SPRING_PROFILES_ACTIVE=dev \
DELIVERY_TIMEOUT=3s \
DELIVERY_MAXATTEMPTS=4 \
DELIVERY_CHANNEL=smoke-test \
./gradlew bootRun
```

With the JAR:

```bash
SPRING_PROFILES_ACTIVE=dev \
DELIVERY_TIMEOUT=3s \
DELIVERY_MAXATTEMPTS=4 \
DELIVERY_CHANNEL=smoke-test \
java -jar build/libs/config-demo-1.0.0.jar
```

When no higher-precedence source overrides them, expected output:

```text
activeProfiles=dev
endpoint=https://delivery.example.invalid
timeout=PT3S
maxAttempts=4
enabled=true
channel=smoke-test
```

**Do not pass `--delivery.timeout=2s` in one launch method and omit it in the other two** and then conclude Spring Boot is inconsistent because the results differ. Those are two different sets of inputs, not equivalent runs.

## 24. Verifying Consistency via Program Arguments

Another way is using the same list of program arguments:

```text
--spring.profiles.active=dev
--delivery.timeout=3s
--delivery.max-attempts=4
--delivery.channel=smoke-test
```

**IDE:** enter these tokens in Program arguments on one line or in the syntax supported by the IDE.

**Gradle:**

```bash
./gradlew bootRun \
  --args='--spring.profiles.active=dev --delivery.timeout=3s --delivery.max-attempts=4 --delivery.channel=smoke-test'
```

**JAR:**

```bash
java -jar build/libs/config-demo-1.0.0.jar \
  --spring.profiles.active=dev \
  --delivery.timeout=3s \
  --delivery.max-attempts=4 \
  --delivery.channel=smoke-test
```

If other sources still contain the same keys, program arguments normally take higher precedence than Config Data and environment variables in default Spring Boot.

However, in integration test environments, test-specific property sources with different precedence rules may exist. Do not extrapolate from a `@SpringBootTest(properties=...)` test to every production launch method.

## 25. Writing a Checklist When Values Differ

When encountering "IDE gets timeout=2s but JAR gets timeout=5s," do not rush to change code. Investigate:

| Question | IDE | bootRun | java -jar |
| --- | --- | --- | --- |
| Same main class/artifact version? | Check module | Check Gradle module | Check JAR name and build time |
| Same active profiles? | Program args/env/VM | `--args`/env | CLI/env/-D |
| Where is working directory? | Run configuration | Task `workingDir` | Shell/service directory |
| External Config Data present? | Args/location | Args/location | Args/location |
| Environment variable actually present? | Run Environment | Gradle child process | Shell/service/container |
| Program arguments overriding? | Program arguments | `--args` | After JAR name |
| System property overriding? | VM options | Task JVM | `-D` before `-jar` |
| YAML file built/packaged? | IDE resources | Resource output | `BOOT-INF/classes` |
| Any validation errors? | Startup log | Task log | JVM log |
| Old process still running? | IDE Run sessions | Other Gradle task | Other service/JVM |

The reliable step is **confirming effective values inside the running process itself**, rather than comparing config files on disk and guessing.

## 26. Observing PropertySources Safely

When suspecting an overriding configuration source, you can list source names from `ConfigurableEnvironment`.

```java
package com.example.configdemo;

import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.ConfigurableEnvironment;
import org.springframework.stereotype.Component;

@Component
public class PropertySourceNamePrinter implements ApplicationRunner {

    private final ConfigurableEnvironment environment;

    public PropertySourceNamePrinter(
            ConfigurableEnvironment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        for (var source : environment.getPropertySources()) {
            System.out.println("propertySource=" + source.getName());
        }
    }
}
```

This is a **diagnostic step for dev/test environments**, not something you should necessarily enable in production. Source names can sometimes reveal paths or infrastructure details, so consider what is safe to log.

Do not print all key/value pairs from `PropertySource`s, because they may contain secrets.

### 26.1. Inspect only non-sensitive key values

```java
String channel =
        environment.getProperty("delivery.channel");
```

Use this to observe an illustrative non-secret key. Distinguish direct reads from `Environment` from values already bound into a bean earlier, especially if the application actively modifies configuration sources at runtime.

### 26.2. Actuator env endpoint

If the application includes Spring Boot Actuator, the environment endpoint can help investigate property sources. However:

- this endpoint should not be opened publicly without restriction;
- access controls and sensitive-data masking must be configured;
- display format and detail level depend on Actuator version and configuration;
- do not treat having the endpoint as a reason to skip security controls.

In simple learning examples, a runner printing a few non-sensitive values is enough to compare the three launch methods.

## 27. Validation Keeps the Contract Intact Even When Sources Change

One benefit of `@ConfigurationProperties` with validation is **not having to write separate rules per launch method**.

Suppose the CLI passes:

```bash
java -jar app.jar --delivery.max-attempts=0
```

or the IDE Run configuration sets:

```text
--delivery.max-attempts=0
```

or an environment variable sets:

```text
DELIVERY_MAXATTEMPTS=0
```

In all three cases, if the final bound value is `0` and a validation provider is configured, `@Min(1)` on the record can reject it.

Similarly:

```bash
java -jar app.jar --delivery.timeout=not-a-duration
```

will cause a binding/conversion error when Spring cannot convert the string into a `Duration` under normal rules.

The contract protects the application from **invalid input**, regardless of whether the input provider is the IDE, Gradle, or the JAR process.

### 27.1. Missing required configuration

If `delivery.endpoint` is absent from all sources, a record with `@NotNull URI endpoint` helps detect the missing value.

If `delivery.channel=""`, `@NotBlank` helps detect the empty string.

Understand the limits:

- `@NotNull` does not check whether the URI scheme is HTTPS.
- `@Min(1)` on `int` guarantees the value is at least 1, but does not tell you whether the key was explicitly declared.
- If you want to require users **to supply a numeric value even when 0 is valid**, consider `Integer` combined with `@NotNull` instead of a primitive.

## 28. Testing the Contract Without Depending on an IDE or JAR

If a configuration contract can be tested independently, you catch mistakes before switching launch methods.

Spring Boot Test provides `ApplicationContextRunner` to create a lightweight context with test property sources.

Suppose the record is:

```java
package com.example.configdemo;

import java.time.Duration;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @NotNull Duration timeout,
        @Min(1) int maxAttempts) {
}
```

Test:

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class DeliveryPropertiesBindingTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withUserConfiguration(TestConfiguration.class);

    @Test
    void acceptsTheContract() {
        runner.withPropertyValues(
                "delivery.timeout=3s",
                "delivery.max-attempts=4"
        ).run(context -> {
            assertThat(context).hasNotFailed();

            DeliveryProperties properties =
                    context.getBean(DeliveryProperties.class);

            assertThat(properties.timeout())
                    .isEqualTo(Duration.ofSeconds(3));
            assertThat(properties.maxAttempts()).isEqualTo(4);
        });
    }

    @Test
    void rejectsInvalidAttempts() {
        runner.withPropertyValues(
                "delivery.timeout=3s",
                "delivery.max-attempts=0"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Test
    void rejectsInvalidDuration() {
        runner.withPropertyValues(
                "delivery.timeout=bad-duration",
                "delivery.max-attempts=4"
        ).run(context -> assertThat(context).hasFailed());
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(DeliveryProperties.class)
    static class TestConfiguration {
    }
}
```

**Note:** this record is a **minimal test-only version** for illustration. In a real project, do not declare two classes with the same name and package `DeliveryProperties`. Apply the same testing idea to the full record defined earlier in the lesson.

An `ApplicationContextRunner` test verifies **binding and validation mechanics**, and does not necessarily verify that the executable JAR contains YAML resources in the right structure or that the IDE has the right working directory. Those aspects require integration or deployment checks.

## 29. Integration Testing with a Specific Profile

If you want to confirm profile-specific Config Data loading as well, use a Spring Boot integration test.

```java
package com.example.configdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.ActiveProfiles;

@SpringBootTest
@ActiveProfiles("dev")
class DeliveryDevProfileTest {

    @Autowired
    private DeliveryProperties properties;

    @Test
    void loadsDevChannel() {
        assertThat(properties.channel())
                .isEqualTo("development");
    }
}
```

This test assumes the project has `application-dev.yml` and the full record from the beginning. If a special test configuration source overrides `delivery.channel`, adjust expectations according to the actual effective sources.

This verifies that "activating the `dev` profile actually loads the corresponding values" rather than only testing the binder with directly supplied properties.

However, **a profile test does not guarantee the production JAR was built and deployed properly**. It verifies an important part of the configuration contract at the application level.

## 30. A Smoke Test for the Executable JAR

After building:

```bash
./gradlew clean bootJar
```

you can run a smoke test with non-sensitive properties:

```bash
java -jar build/libs/config-demo-1.0.0.jar \
  --spring.profiles.active=dev \
  --delivery.timeout=3s \
  --delivery.max-attempts=4 \
  --delivery.channel=smoke-test
```

Depending on the application, the smoke test can confirm:

1. The JVM starts the right main class.
2. The executable JAR contains the required classes and resources.
3. Spring Boot loads configuration.
4. The Binder creates `DeliveryProperties`.
5. Validation does not reject valid data.
6. The application prints or exposes appropriate status information.
7. There are no early errors due to file paths or dependencies.

If the application is a web server, have an appropriate way to check readiness and stop the process cleanly after the smoke test. For long-running applications, `java -jar` may keep running until you stop the process; this is normal.

Do not use a smoke test to call external endpoints that are not part of the test environment; `example.invalid` is used in this lesson to avoid implying that a real connection must succeed.

## 31. Spring Boot DevTools and Development-Mode Differences

In an IDE or `bootRun`, a project may use Spring Boot DevTools to support automatic restarts or development conveniences.

This can give classpath/source runs auxiliary behavior different from an executable JAR. For example, a class change may trigger a restart in development mode.

However, DevTools differences **do not change the goal of the configuration contract**:

```text
delivery.timeout -> Duration
delivery.max-attempts -> int >= 1
```

If DevTools triggers a restart, Spring may reinitialize the context and rebind configuration in certain cases. Do not infer from this that changing a YAML file automatically refreshes a singleton bean in every production application.

DevTools, refresh scope, and dynamic configuration mechanisms are separate topics; they are not a separate set of key-naming rules for the IDE.

## 32. IDE Run Is Not Equivalent to bootRun

Some IDEs allow you to launch:

1. **The main class directly** using the IDE's Java launcher;
2. **The Gradle `bootRun` task** right inside the IDE.

Although both are triggered by clicking the IDE's Run button, they can use **two different launch mechanisms**.

For example:

- Running the main class directly: the IDE determines classpath, Program arguments, and working directory.
- Running Gradle `bootRun` inside the IDE: the Gradle task determines classpath and argument passing; the IDE mostly launches a Gradle process.

When debugging differences, check which type of Run configuration you selected. Do not treat everything clicked in the IDE UI as an "IDE Java Application run."

For this lesson, "running from the IDE" primarily means launching the main class directly. If the IDE actually invokes `bootRun`, treat it as the Gradle `bootRun` case and inspect the task parameters.

## 33. Be Careful When Configuring the bootRun JVM

Gradle has a **JVM running Gradle**, and the `bootRun` task can launch an **application JVM**. The two processes do not always share the same set of Java system properties.

A configuration:

```groovy
tasks.named('bootRun') {
    jvmArgs '-Ddelivery.timeout=4s'
}
```

targets the application JVM created by the task.

Conversely, when running:

```bash
./gradlew -Ddelivery.timeout=4s bootRun
```

do not automatically assume that value will be copied to the application JVM. If needed, configure system property forwarding explicitly or use `--args`.

When documenting team workflows, pick **one primary delivery mechanism** for each kind of input to reduce having the same key appear in multiple places. For example:

- Use environment variables for deployment settings.
- Use Program arguments for temporary test scenarios.
- Use Config Data files for profile-based configuration.
- Use VM/system properties only when there is a specific technical reason.

This is a practical convention, not a Spring Boot limitation.

## 34. Relative Paths in IDE, bootRun, and JAR

Suppose the application has a key:

```properties
delivery.template-file=./templates/email.txt
```

If code uses:

```java
Path.of(properties.templateFile());
```

then `./templates/email.txt` is typically resolved relative to the process's working directory.

In an IDE, the working directory may be the project root. With Gradle `bootRun`, it follows task configuration. With a JAR run from another directory, it follows the shell/service.

**Standardizing property names does not guarantee a relative path points to the same file.**

To avoid mistakes:

1. Use an absolute path passed via configuration if the file is an external resource outside the application.
2. Or ensure the working directory is identical across all three launch methods.
3. If the file is truly a packaged resource, consider using a classpath resource instead of a relative filesystem path.
4. Do not construct paths assuming the JAR is always launched from the directory containing the JAR itself.

Running:

```bash
java -jar /opt/apps/config-demo.jar
```

does not automatically set the working directory to `/opt/apps`. It remains the directory of the launching shell/service unless the launcher actively changes it.

## 35. Configuring per Environment Without Duplicating Logic

Suppose dev wants a 2-second timeout and production wants a 10-second timeout.

Reasonable approach:

```yaml
# application-dev.yml
delivery:
  timeout: 2s
```

```yaml
# application-prod.yml
delivery:
  timeout: 10s
```

and one record:

```java
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(Duration timeout) {
}
```

No need for:

```java
if (isRunningFromIde()) {
    timeout = Duration.ofSeconds(2);
} else if (isRunningFromJar()) {
    timeout = Duration.ofSeconds(10);
}
```

Because the IDE can also run `prod` and the JAR can also run `dev`. The deployment environment is described by profiles and data sources, not by the launch tool.

**In this way, the application achieves something important: the same artifact can be used across many environments**, provided appropriate configuration inputs are supplied.

## 36. Do Not Hard-Code Secrets per Launch Method

If the application needs a token:

```text
delivery.api-token
```

do not:

- commit the production token into `application-prod.yml`;
- put the token in `build.gradle` and package or log it;
- paste the token into Program arguments and share screenshots/logs containing the full command;
- write the token into an unprotected shared script;
- log the entire `Environment` or a configuration record containing the token.

Instead, use environment variables, a secret manager, or an organization-approved secret management mechanism.

The contract can still be:

```text
delivery.api-token: String, required, sensitive
```

but the **actual value** must be supplied from a secure source at runtime.

Using the same contract for IDE, `bootRun`, and JAR **does not mean sharing a single secret** between dev and production.

## 37. Common Mistakes and Causes

### 37.1. IDE runs fine, JAR reports missing property

Possible causes:

- The IDE has its own environment variables.
- The IDE has Program arguments not passed to `java -jar`.
- The JAR is missing `application.yml` or is an old build.
- A different working directory prevents loading an external file outside the JAR.
- Different active profiles.

**Resolution:** compare process inputs, artifact, profile, Config Data, and effective values before modifying the record.

### 37.2. bootRun reads different values than the IDE

Possible causes:

- The Gradle task received different `--args`.
- The IDE Java Application run has its own VM options or environment variables.
- The Gradle JVM and app JVM do not receive the same system properties.
- Different working directory or module.

**Resolution:** check the Run configuration type and the variable/argument set of the application process itself.

### 37.3. java -jar does not read external files next to the JAR

Usually caused by the working directory or Config Data location not being what was assumed.

**Resolution:** use absolute paths, appropriate `spring.config.additional-location`, and verify directory locations end with `/`.

### 37.4. Putting -D after the JAR name

```bash
java -jar app.jar -Ddelivery.timeout=4s
```

does not pass `-D...` as a JVM option. Fix to:

```bash
java -Ddelivery.timeout=4s -jar app.jar
```

or use:

```bash
java -jar app.jar --delivery.timeout=4s
```

### 37.5. Passing --delivery.timeout directly to Gradle

```bash
./gradlew bootRun --delivery.timeout=4s
```

is not the standard way to pass program arguments to `bootRun`. Fix to:

```bash
./gradlew bootRun --args='--delivery.timeout=4s'
```

### 37.6. .env file exists, but the application does not pick it up

Spring Boot does not automatically read a `.env` file by default. Tooling/deployment must actively export environment variables or use a supported `PropertySource`/Config Data source.

### 37.7. Dev config overrides, yet base YAML value is seen

The `dev` profile may not be activated, the dev file was not loaded, or another source has higher precedence.

### 37.8. Environment variable name uses incorrect underscores

For example, `DELIVERY_MAX_ATTEMPTS` may not match the canonical key under the active environment variable mapping rules. Follow the canonical `DELIVERY_MAXATTEMPTS` form and verify the binding result.

### 37.9. Missing Bean Validation provider

The record has `@NotNull` or `@Min`, but the project lacks a suitable provider. Check `spring-boot-starter-validation` and build configuration.

### 37.10. Printing all configuration to debug

Printing all properties can expose secrets. Instead, log non-sensitive keys, source names, and necessary status.

## 38. Repeatable Diagnostic Procedure

When results differ across the three launch methods, follow this procedure:

**Step 1.** Confirm identical source commit, dependency versions, and artifact.

**Step 2.** Confirm the main class and launch method: IDE Java Application, Gradle `bootRun`, or JVM JAR.

**Step 3.** Confirm the active profiles inside each process.

**Step 4.** Record **non-sensitive** program arguments, VM options, and environment variables.

**Step 5.** Confirm the working directory and additional Config Data locations.

**Step 6.** Read non-sensitive keys through `Environment` and the `@ConfigurationProperties` bean.

**Step 7.** If the key name is right but the value is wrong, check higher-precedence `PropertySource`s.

**Step 8.** If the bean fails to instantiate, distinguish missing values, conversion errors, and validation errors.

**Step 9.** Write binding and profile tests to reproduce.

**Step 10.** Fix the configuration at the **source causing the issue**, then rerun with the same inputs to verify.

This procedure encourages evidence-based diagnosis rather than creating three separate configuration sets for each launcher.

## 39. Exercise A — Predicting Values Across Three Launch Methods

Given:

```yaml
# application.yml
delivery:
  timeout: 5s
  max-attempts: 3
```

```yaml
# application-dev.yml
delivery:
  timeout: 2s
  max-attempts: 2
```

And three launches:

**IDE Program arguments:**

```text
--spring.profiles.active=dev --delivery.max-attempts=4
```

**bootRun:**

```bash
./gradlew bootRun --args='--spring.profiles.active=dev --delivery.max-attempts=4'
```

**JAR:**

```bash
java -jar app.jar --spring.profiles.active=dev --delivery.max-attempts=4
```

Assume no other source overrides them.

**Answer:** all three receive `timeout=2s` and `maxAttempts=4` after binding.

Explanation: the `dev` profile provides the 2-second timeout; the application argument overrides `max-attempts` from the dev file.

## 40. Exercise B — Distinguishing VM Options and Program Arguments

Someone sets in the IDE:

```text
VM options: -Ddelivery.timeout=3s
Program arguments: --delivery.timeout=4s
```

**Question:** Which timeout will Spring Boot normally use if no higher-precedence source exists?

**Answer:** `4s` from the command-line property, because it normally takes precedence over a Java system property for the same key.

This illustrates that the two fields in the IDE are not just UI differences; they create two different data sources.

## 41. Exercise C — Explaining the -D After JAR Mistake

Someone runs:

```bash
java -jar app.jar -Ddelivery.timeout=3s
```

and wonders why the configuration did not change.

**Answer:** `-D` after the JAR is no longer processed by the JVM as a system property. Fix it to:

```bash
java -Ddelivery.timeout=3s -jar app.jar
```

Or use an application argument:

```bash
java -jar app.jar --delivery.timeout=3s
```

## 42. Exercise D — External Files Outside the JAR and Working Directory

An application has `./config/application.yml` located at `/opt/team/config/application.yml`.

- Person A runs `java -jar /opt/team/app.jar` from `/opt/team`.
- Person B runs the same command from `/home/user`.

**Question:** Can we be sure both people load the same external file outside the JAR?

**No.** `./config` depends on each process's working directory. If you want to use the exact file at `/opt/team/config`, standardize the working directory or pass an appropriate absolute location.

## 43. Exercise E — Not Confusing Profiles with Launch Methods

**Question:** Does `bootRun` always use the `dev` profile, and does `java -jar` always use the `prod` profile?

**No.** Those are two launch methods. The profile is determined by effective configuration sources, such as `--spring.profiles.active=...` or `SPRING_PROFILES_ACTIVE`. Both launch methods can activate any valid profile when configured.

## 44. Exercise F — Catching Errors Early Across All Three Launch Methods

Record:

```java
@Validated
@ConfigurationProperties(prefix = "delivery")
public record DeliveryProperties(
        @Min(1) int maxAttempts) {
}
```

If IDE, `bootRun`, and JAR all receive the final value:

```text
delivery.max-attempts = 0
```

then when Spring Boot properly registers, binds the bean, and executes Bean Validation, all three can fail at startup. This is the desired behavior of **a single shared configuration contract**.

If one launch method does not fail, check whether it is actually using the same class, annotations, validation provider, and final value.

## 45. Key Takeaways

- **IDE, bootRun, and java -jar are three launch methods, not three separate configuration systems.**
- Define a single contract via `@ConfigurationProperties`: same prefix, same key names, same Java types, same defaults and validation.
- `Spring Environment` unifies property sources and the binder builds Java objects; services do not need to know which tool supplied the values.
- **IDE:** Program arguments, VM options, environment variables, and working directory are distinct settings.
- **bootRun:** use `--args='--key=value'` to pass program arguments; do not confuse Gradle's JVM with the application's JVM.
- **java -jar:** use `--key=value` after the JAR or `-Dkey=value` before `-jar`; building the JAR and running the JAR are two separate steps.
- **Profiles** are activated via properties such as `spring.profiles.active`, never inferred from IDE/Gradle/JAR.
- **Source precedence** explains why a CLI/env value can override YAML. Identical effective inputs must yield identical binding results.
- **Working directory** determines the meaning of relative file paths; use explicit external locations and `spring.config.additional-location` when appropriate.
- **A .env file is not loaded automatically by Spring Boot** merely by existing; the process must actually receive the corresponding variables or configuration source.
- **Validation** rejects missing, mistyped, or constraint-violating data across all three launch methods.
- Test across three layers: binder/validation tests, profile-specific Config Data tests, and executable JAR smoke tests.
- When results differ, check **artifact, profile, working directory, arguments, system properties, environment variables, and effective sources** before changing code.
