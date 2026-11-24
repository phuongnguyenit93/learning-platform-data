# `java -jar`, JVM System Properties, and Application Arguments

A Spring Boot application after being packaged into an **executable JAR** can usually be started with the command:

```bash
java -jar order-service.jar
```

In a real-world environment, the run command is rarely just a simple single line. You may need to select a Spring profile, change the HTTP port, limit the JVM heap, specify a configuration location, or pass a batch processing mode:

```bash
java -Xms256m -Xmx768m \
  -Dapp.instance=order-a \
  -jar order-service.jar \
  --spring.profiles.active=prod \
  --server.port=8085 \
  --app.startup-mode=serve
```

In this command there are **three different kinds of information**:

1. **JVM/Java launcher options** such as `-Xmx768m` and `-Dapp.instance=order-a`.
2. **The option selecting the program file**, which is `-jar order-service.jar`.
3. **Application arguments** placed after the JAR name, such as `--spring.profiles.active=prod` and `--server.port=8085`.

Confusing the positions of these parts can cause the application not to start, the profile not to be selected, or a property to be passed without being used by Spring Boot. This lesson thoroughly explains how the Java launcher parses the command, how Spring Boot receives configuration, the order of precedence, how to read arguments in Java, and how to diagnose common errors.

> **Most important rule:** options intended for the JVM go **before** `-jar`; arguments intended for the application go **after** the JAR name.

## 1. Reading the Run Command Structure Correctly

General structure:

```text
java [JVM / launcher options] -jar <executable-jar> [application arguments]
```

Example:

```bash
java -Xmx512m -Dserver.port=8081 -jar build/libs/demo.jar --app.mode=import input.csv
```

Breakdown:

```text
java
 |
 +-- -Xmx512m               JVM option: heap limit
 |
 +-- -Dserver.port=8081     Java system property
 |
 +-- -jar                   Selects executable JAR run mode
 |
 +-- build/libs/demo.jar    JAR file path
 |
 +-- --app.mode=import      Spring Boot command-line option
 |
 +-- input.csv              Non-option application argument
```

### 1.1. Argument Position Table

| Syntax | Who receives it? | Correct position | Example |
| --- | --- | --- | --- |
| `-Xmx` | JVM | Before `-jar` | `-Xmx512m` |
| `-Xms` | JVM | Before `-jar` | `-Xms256m` |
| `-Dname=value` | Java launcher/JVM system properties | Before `-jar` | `-Dapp.mode=batch` |
| `-XX:...` | JVM | Before `-jar` | `-XX:MaxRAMPercentage=70` |
| `-jar` | Java launcher | Before the JAR name | `-jar app.jar` |
| `--name=value` | Program argument, which Spring Boot can put into `Environment` | After the JAR name | `--server.port=9090` |
| `--name` | Application option without a value | After the JAR name | `--debug` |
| `file.csv` | Regular program argument | After the JAR name | `input.csv` |

**There is no general mechanism that automatically turns every argument after the JAR name into a JVM option.** From after the JAR name onward, Java passes the remaining strings into the application's `main(String[] args)`.

### 1.2. Valid Examples

```bash
java -Dspring.profiles.active=dev -jar app.jar
```

```bash
java -jar app.jar --spring.profiles.active=dev
```

Both of the above approaches can activate the `dev` Spring profile in a Spring Boot application under default configuration, but they enter the Spring `Environment` from **two different property sources**.

### 1.3. Incorrectly Ordered Examples

```bash
java -jar app.jar -Dspring.profiles.active=dev
```

In this position, `-Dspring.profiles.active=dev` is just **an application argument**. It is not processed by the Java launcher as a JVM system property. Furthermore, the Spring Boot command-line property parser normally recognizes options using the `--key=value` syntax and does not automatically treat a `-D...` string after the JAR as a Spring configuration property.

```bash
java --server.port=9090 -jar app.jar
```

In this position, `--server.port=9090` is given to the Java launcher instead of the application. The Java launcher may report **Unrecognized option** and the JVM will not start the application.

## 2. What Does `java -jar` Actually Do?

`java` is the Java launcher program provided by the JDK/JRE. The `-jar` option instructs the Java launcher to read a JAR file containing sufficient metadata to identify the **main class** and transfer execution control to the program inside.

```bash
java -jar app.jar
```

Basic requirements:

- The machine has an appropriate Java runtime.
- The path `app.jar` exists and the process has read permission.
- The JAR has a manifest or packaging mechanism compatible with `-jar` execution.
- The bytecode and libraries are compatible with the Java version being used.
- The required runtime resources, configuration, and dependencies are available.

### 2.1. A Regular JAR Is Not Guaranteed to Be an Executable JAR

A JAR file may only contain library classes/resources without an entry point:

```text
library.jar
  com/example/Utils.class
  META-INF/MANIFEST.MF
```

Not every file with a `.jar` extension can be run with:

```bash
java -jar library.jar
```

If the manifest lacks an appropriate `Main-Class`, the launcher may report:

```text
no main manifest attribute, in library.jar
```

This is a **JAR packaging** issue, not a `server.port` or `spring.profiles.active` error.

### 2.2. Spring Boot Executable JAR

When using the Spring Boot Maven Plugin or Gradle Boot Plugin to create an executable JAR, the packaging typically includes:

```text
order-service.jar
├── META-INF/
│   └── MANIFEST.MF
├── BOOT-INF/
│   ├── classes/
│   │   └── com/example/orders/OrdersApplication.class
│   └── lib/
│       ├── spring-boot-...jar
│       └── ...
└── org/springframework/boot/loader/...
```

This is a conceptual structure commonly seen in an executable JAR, not an exhaustive listing of every entry or a guarantee that every version uses the exact same launcher package names.

The Spring Boot loader knows how to load classes and dependency JARs inside the packaged structure. Therefore, you can run:

```bash
java -jar order-service.jar
```

without having to write a long classpath listing every dependency individually.

### 2.3. `Main-Class` and `Start-Class`

A Spring Boot executable JAR typically uses manifest metadata similar to:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.orders.OrdersApplication
```

The actual `Main-Class` name varies across Spring Boot lines; for example, in some older versions, the loader package differs from the example above.

Meaning:

- `Main-Class` is the entry point the Java launcher invokes first.
- The Spring Boot launcher locates and runs `Start-Class`, which is your application class.
- The application class normally contains `public static void main(String[] args)`.

You do not need to edit the manifest manually when the Spring Boot build plugin is properly configured.

## 3. Creating the Executable JAR Before Running

### 3.1. With Gradle

In a project already using the Spring Boot Gradle plugin:

```bash
./gradlew bootJar
```

On Windows:

```powershell
.\gradlew.bat bootJar
```

The artifact is typically written to:

```text
build/libs/
```

For example:

```text
build/libs/order-service-1.0.0.jar
```

The file name depends on the project configuration and task output. Use the file name **that is actually generated**, rather than assuming every project produces `app.jar`.

### 3.2. With Maven

A project using `spring-boot-maven-plugin` with the `repackage` goal properly configured can be built with:

```bash
./mvnw package
```

On Windows:

```powershell
.\mvnw.cmd package
```

The artifact is typically located at:

```text
target/order-service-1.0.0.jar
```

If the build has not configured Spring Boot repackaging, `mvn package` may only produce a plain JAR that does not carry full runtime dependencies for running with `java -jar`.

### 3.3. Distinguishing `jar`, `bootJar`, and `repackage`

| Concept | Role |
| --- | --- |
| Gradle `jar` | Task that packages a plain JAR |
| Gradle `bootJar` | Task that creates an executable Spring Boot JAR |
| Maven `package` | Lifecycle phase that produces an artifact according to plugin configuration |
| Spring Boot Maven `repackage` | Repackages the artifact into an executable Spring Boot archive |

You should not conclude that an artifact is executable solely from its `.jar` extension.

### 3.4. A Complete Run Command Example

Suppose the build creates:

```text
build/libs/order-service-1.0.0.jar
```

Run:

```bash
java -jar build/libs/order-service-1.0.0.jar
```

With configuration:

```bash
java -Xmx512m \
  -Dapp.instance=local-01 \
  -jar build/libs/order-service-1.0.0.jar \
  --spring.profiles.active=dev \
  --server.port=8081
```

Options before `-jar` are processed by the Java launcher. Options after the JAR go into `main(String[] args)` and can be used by Spring Boot.

## 4. What Is a JVM System Property?

**Java system properties** are a key-value set attached to a JVM process. A common way to set them at startup is:

```bash
java -Dapp.mode=batch -jar app.jar
```

In Java:

```java
String mode = System.getProperty("app.mode");
```

If the property has been set properly, `mode` has the value:

```text
batch
```

### 4.1. `-D` Syntax

```text
-D<property-name>=<property-value>
```

Example:

```bash
java -Dapp.instance=worker-02 -Dapp.feature.enabled=true -jar app.jar
```

Each property is a separate JVM launcher argument:

```text
-Dapp.instance=worker-02
-Dapp.feature.enabled=true
```

They must all be placed before `-jar`.

### 4.2. A System Property Is Not an Environment Variable

Compare:

```java
System.getProperty("app.mode")
```

with:

```java
System.getenv("APP_MODE")
```

The two APIs read two different sources.

| Source | How to set | Read in Java via |
| --- | --- | --- |
| JVM system property | `-Dapp.mode=batch` | `System.getProperty("app.mode")` |
| OS environment variable | `APP_MODE=batch` | `System.getenv("APP_MODE")` |
| Spring Boot application argument | `--app.mode=batch` after the JAR | `ApplicationArguments`, or `Environment` when enabled |

Spring Boot can **combine all three** into property sources to configure the application, but that does not make `System.getProperty()` and `System.getenv()` the same API.

### 4.3. Reading a System Property with a Default Value

```java
String instanceName =
        System.getProperty("app.instance", "unnamed");
```

The value `unnamed` is used when the system property does not exist.

This is pure Java logic and does not require an application context.

### 4.4. Can a System Property Be Set in Code?

Java supports:

```java
System.setProperty("app.mode", "batch");
```

However, if you need to change a Spring Boot configuration property, set the value **before the phase where Spring Boot processes the corresponding configuration**. Changing a system property late after the context has refreshed does not automatically re-bind every bean or restart the web server.

In most applications, you should configure via CLI, environment, or Config Data rather than mutating system properties arbitrarily in business code.

## 5. How JVM Options Differ from Java System Properties

All of the following options usually go before `-jar`, yet they do not have the same effect:

```bash
java -Xms256m -Xmx1g -Dapp.mode=batch -jar app.jar
```

### 5.1. `-Xms` and `-Xmx`

Example:

```text
-Xms256m
-Xmx1g
```

Meaning:

- `-Xms`: initial heap size according to the corresponding JVM option.
- `-Xmx`: maximum heap size the JVM is allowed to use.

These options are not Spring Boot properties. They are not used like:

```bash
java -jar app.jar --Xmx1g
```

and cannot be read with:

```java
System.getProperty("Xmx")
```

to retrieve the heap limit.

### 5.2. `-XX` and Other JVM Flags

Example:

```bash
java -XX:MaxRAMPercentage=70 -jar app.jar
```

Some `-XX` options depend on the JVM vendor and Java version. Check the actual runtime, especially when running inside a container.

Not all JVM options can be combined arbitrarily; for instance, an explicit heap limit via `-Xmx` may alter how the JVM uses memory-percentage-based settings.

### 5.3. Do Not Confuse `--debug` with the JVM Debugger

In Spring Boot:

```bash
java -jar app.jar --debug
```

`--debug` is a Spring Boot application option commonly used to increase startup diagnostic output, including the Conditions Evaluation Report.

It is **not equivalent** to enabling the Java remote debugger/JDWP. Debugger options belong to the JVM and must be configured separately, with appropriate protections on the debug port.

## 6. What Are Application Arguments?

Once the Java launcher has read `-jar` and the JAR path, the remaining items are passed to:

```java
public static void main(String[] args)
```

Example:

```bash
java -jar app.jar --app.mode=import customers.csv
```

Conceptually, the strings in `args` are:

```text
args[0] = "--app.mode=import"
args[1] = "customers.csv"
```

They are **application arguments**, not JVM system properties.

### 6.1. Spring Boot's Static `run(...)` Receives These Exact Arguments

A startup class:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

`SpringApplication.run(..., args)` receives the strings that Java passed into `main`.

You do not need to manually split `--server.port=8081` in code for Spring Boot to know the HTTP port under default settings.

### 6.2. Two Groups of Arguments Inside the Application

Spring Boot distinguishes between:

- **Option arguments**: starting with `--`.
- **Non-option arguments**: the remaining strings.

Example:

```bash
java -jar app.jar --app.mode=import --app.dry-run=true input.csv
```

When parsed via `ApplicationArguments`:

```text
Option:
  app.mode = import
  app.dry-run = true

Non-option:
  input.csv
```

### 6.3. Use `--name=value` for Options with Values

Correct:

```bash
java -jar app.jar --app.mode=import
```

You should not assume that these two strings will be treated by Spring Boot as an option-value pair:

```bash
java -jar app.jar --app.mode import
```

In Spring Boot's default option-parsing mechanism, the explicit form is `--app.mode=import`; the standalone string `import` may be classified as a non-option argument.

### 6.4. Options Without Values

Example:

```bash
java -jar app.jar --debug
```

Spring Boot recognizes `debug` as an option without an explicit value.

However, for a **custom boolean property**, to ensure clear binding you should use:

```bash
java -jar app.jar --app.dry-run=true
```

rather than assuming every binder will interpret an empty option as Boolean `true`.

## 7. `ApplicationArguments`: Reading Arguments the Spring Boot Way

Spring Boot provides the interface:

```java
org.springframework.boot.ApplicationArguments
```

It supports:

```java
args.containsOption("app.mode")
args.getOptionValues("app.mode")
args.getNonOptionArgs()
args.getOptionNames()
args.getSourceArgs()
```

### 7.1. A Complete `ApplicationRunner`

```java
package com.example.demo.startup;

import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportArgumentsRunner implements ApplicationRunner {

    @Override
    public void run(ApplicationArguments args) {
        if (args.containsOption("app.mode")) {
            List<String> modes =
                    args.getOptionValues("app.mode");

            System.out.println("Modes: " + modes);
        }

        List<String> files = args.getNonOptionArgs();
        System.out.println("Input file count: " + files.size());
    }
}
```

Run:

```bash
java -jar app.jar --app.mode=import input.csv
```

Illustrative output:

```text
Modes: [import]
Input file count: 1
```

The example intentionally prints only the file count rather than printing every argument verbatim; CLI arguments can contain sensitive paths or secrets if an operator passes them improperly.

### 7.2. What Can `getOptionValues()` Return?

For a non-existent option:

```java
args.getOptionValues("missing")
```

it normally returns `null`.

For an option that is present without a value, such as `--debug`, the result may be an empty list.

For `--app.mode=import`, the result is a list containing the value `import`.

When writing code, check whether the option exists first, and also handle empty lists or multiple values if that affects business logic.

### 7.3. `ApplicationArguments` Differs from `Environment`

`ApplicationArguments` represents the command-line arguments.

`Environment` represents configuration combined from multiple property sources.

If a property comes from:

```properties
app.mode=serve
```

inside `application.properties`, `Environment` can read it, but `ApplicationArguments.containsOption("app.mode")` does not automatically become `true`.

`ApplicationArguments` only knows about the strings that were passed into the process via the command line.

## 8. `CommandLineRunner`: Receiving Raw Argument Strings

In addition to `ApplicationRunner`, Spring Boot also provides:

```java
org.springframework.boot.CommandLineRunner
```

Example:

```java
package com.example.demo.startup;

import org.springframework.boot.CommandLineRunner;
import org.springframework.stereotype.Component;

@Component
public class RawArgumentsRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println(
                "Argument count: " + args.length
        );
    }
}
```

`CommandLineRunner` receives the exact application argument strings in the order they were passed to the program, without converting them into an option model.

### 8.1. Comparing the Two Runners

| Criterion | `ApplicationRunner` | `CommandLineRunner` |
| --- | --- | --- |
| Parameter | `ApplicationArguments` | `String... args` |
| Distinguishes option/non-option | Yes | You handle it yourself |
| Reads `--name=value` values | Via `getOptionValues()` | Must parse manually if needed |
| Invocation phase | After context refresh, before `ApplicationReadyEvent` | Same phase |
| Useful for | CLI modes, batch options, command configuration | Processing raw arguments or simple applications |

Spring Boot orders supported runners using `@Order` or `Ordered` when multiple runners exist. Do not rely on arbitrary ordering if startup steps have business dependencies.

### 8.2. What Happens If a Runner Fails?

If a runner throws an unhandled exception, Spring Boot may treat startup as failed and not proceed to `ApplicationReadyEvent` in the success flow.

A runner should not run an infinite loop simply because the application needs background work. Use a lifecycle mechanism, scheduler, queue consumer, or managed worker suited to the actual goal.

## 9. Spring Boot Turns Command-Line Options into Configuration Properties

Under default settings, Spring Boot adds options such as:

```text
--server.port=8081
--spring.profiles.active=dev
--app.mode=import
```

into a command-line `PropertySource` inside `Environment`.

Therefore:

```bash
java -jar app.jar --server.port=8081
```

can be equivalent in terms of **the configuration value read from Spring** to:

```properties
server.port=8081
```

in a configuration file, although the two sources have different priorities.

### 9.1. Reading from `Environment`

```java
package com.example.demo.startup;

import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class PortSettings {

    private final Environment environment;

    public PortSettings(Environment environment) {
        this.environment = environment;
    }

    public int configuredPort() {
        return environment.getProperty(
                "server.port",
                Integer.class,
                8080
        );
    }
}
```

The returned value is the property resolved by `Environment` according to the active sources. If `server.port=0` is used to request a random port, `Environment.getProperty("server.port")` may still return `0` even though the embedded server was assigned a different actual port by the operating system.

To determine the actual web server port, you can use the web server initialized event or tools intended for integration testing.

### 9.2. Reading with `@Value`

```java
@Service
public class ModeService {

    private final String mode;

    public ModeService(
            @Value("${app.mode:serve}") String mode) {
        this.mode = mode;
    }

    public String mode() {
        return mode;
    }
}
```

If `app.mode` is absent, the default `serve` is used via placeholder syntax.

### 9.3. Reading with `@ConfigurationProperties`

For multiple related properties, use typed binding:

```java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.import")
public record ImportProperties(
        boolean dryRun,
        int batchSize,
        Duration timeout
) {
}
```

A run command:

```bash
java -jar app.jar \
  --app.import.dry-run=true \
  --app.import.batch-size=100 \
  --app.import.timeout=15s
```

Spring Boot can bind these values into the record through configuration properties binding if the class is registered in the context, for example with `@ConfigurationPropertiesScan` on the application class.

This is Spring Boot's binding mechanism, unlike manually calling `System.getProperty()` to parse individual strings.

## 10. How Do `-D` and `--` Differ?

This is the part most easily confused.

### 10.1. JVM System Property

```bash
java -Dapp.mode=batch -jar app.jar
```

The Java launcher puts `app.mode=batch` into JVM system properties.

Read in Java:

```java
System.getProperty("app.mode")
```

Spring Boot can also read `app.mode` from `Environment` because JVM system properties are a property source normally integrated by Spring.

### 10.2. Spring Boot Command-Line Property

```bash
java -jar app.jar --app.mode=batch
```

The Java launcher passes the string `--app.mode=batch` into `main(args)`.

Spring Boot recognizes it as a command-line option and can expose its value via `Environment`.

However:

```java
System.getProperty("app.mode")
```

**does not automatically contain** the value `batch` just because you passed `--app.mode=batch`.

### 10.3. Comparison Table

| Question | `-Dapp.mode=batch` before JAR | `--app.mode=batch` after JAR |
| --- | --- | --- |
| Directly handled by the JVM launcher? | Yes | No; passed to the application |
| Appears in `System.getProperty("app.mode")`? | Yes | Not automatically |
| Appears in `ApplicationArguments`? | No, if only `-D` is passed | Yes |
| Can appear in Spring `Environment`? | Yes | Yes, under default configuration |
| Used to configure Spring Boot? | Yes | Yes |
| Typical priority relative to each other | Lower than command-line properties | Higher than JVM system properties |

### 10.4. Same Property Name via Both Mechanisms with Different Values

```bash
java -Dapp.mode=serve -jar app.jar --app.mode=import
```

In the JVM:

```java
System.getProperty("app.mode")  // "serve"
```

In Spring `Environment` by default:

```java
environment.getProperty("app.mode")  // "import"
```

In `ApplicationArguments`:

```java
args.getOptionValues("app.mode")  // ["import"]
```

Reason: Spring Boot's command-line property source typically has higher precedence than the Java system property source, whereas `System.getProperty()` reads strictly from the JVM system properties set.

**Do not confuse an API that reads a single specific source with an API that resolves configuration across multiple sources.**

## 11. Configuration Precedence Order

Spring Boot externalized configuration involves more than just `-D` and `--`.

An application can receive properties from:

- `SpringApplication` default properties.
- `application.properties` / `application.yml` files.
- Profile-specific files such as `application-prod.yml`.
- Operating system environment variables.
- Java system properties (`-D...`).
- JSON application properties via the corresponding mechanism.
- Command-line application arguments (`--...`).
- Property sources dedicated to tests or development environments.

### 11.1. General Order of Common Sources

In a typical Spring Boot application, for a colliding key when no test source or special custom source overrides it, you can picture the order from **lowest to highest**:

```text
Default properties
        |
        v
Config Data: application.*, profile documents
        |
        v
OS environment variables
        |
        v
JVM system properties (-D...)
        |
        v
Spring Boot command-line properties (--...)
```

This is a simplified diagram; Spring Boot has many more property sources with specific precedence positions. If a scenario involves `SPRING_APPLICATION_JSON`, test properties, imports, or custom property sources, consult the complete precedence order for the version in use.

### 11.2. Example with the Same Key in Multiple Sources

`application.properties` file:

```properties
server.port=8080
```

Environment variable:

```text
SERVER_PORT=8081
```

Run command:

```bash
java -Dserver.port=8082 \
  -jar app.jar \
  --server.port=8083
```

With default Spring Boot settings and no higher-precedence source, the effective property is:

```text
server.port=8083
```

Because the `--server.port=8083` option has higher priority than the other sources in the example.

### 11.3. Not Every Configuration Value Takes Effect Dynamically at Runtime

Spring Boot normally binds many properties when creating beans or starting the server. If you change an operating system environment variable after startup, the running JVM **does not automatically reload** and reconfigure every bean.

If dynamic configuration is needed, you must use a dedicated refresh/dynamic configuration mechanism. Do not assume that changing a value outside the process will automatically change the web server port.

## 12. What Does `setAddCommandLineProperties(false)` Change?

Spring Boot lets you instantiate `SpringApplication` to control whether command-line options are added to `Environment`.

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(DemoApplication.class);

        application.setAddCommandLineProperties(false);
        application.run(args);
    }
}
```

When set to `false`, Spring Boot does not add command-line options to the property sources by default.

As a result:

```bash
java -jar app.jar --app.mode=import
```

still supplies the argument to:

```java
ApplicationArguments
```

but it no longer guarantees that:

```java
environment.getProperty("app.mode")
```

will obtain `import` from the command-line option.

### 12.1. Does It Affect `--spring.profiles.active`?

Potentially yes. If command-line options are excluded from `Environment`, the value:

```text
--spring.profiles.active=dev
```

is no longer processed as a property source for selecting a profile in the default manner.

**Only disable the command-line property source when you genuinely want Spring Boot not to use `--...` for environment configuration.**

### 12.2. Does It Affect `-D`?

`setAddCommandLineProperties(false)` is not intended to remove JVM system properties. System properties remain a separate source in Spring `Environment` as usual.

For example:

```bash
java -Dapp.mode=batch -jar app.jar
```

still creates the system property, even if you prevent Spring from adding application options to `Environment`.

## 13. Activating a Spring Profile via the CLI

Profiles often determine which configuration files and beans are applied.

Suppose an application has:

```text
src/main/resources/
├── application.yml
├── application-dev.yml
└── application-prod.yml
```

`application.yml`:

```yaml
spring:
  application:
    name: order-service

server:
  port: 8080
```

`application-dev.yml`:

```yaml
server:
  port: 8081

logging:
  level:
    com.example.orders: DEBUG
```

`application-prod.yml`:

```yaml
logging:
  level:
    root: INFO
```

### 13.1. Selecting `dev` with an Application Argument

```bash
java -jar app.jar --spring.profiles.active=dev
```

### 13.2. Selecting `dev` with a JVM System Property

```bash
java -Dspring.profiles.active=dev -jar app.jar
```

### 13.3. Selecting with an Environment Variable

In Bash:

```bash
SPRING_PROFILES_ACTIVE=dev java -jar app.jar
```

In Windows PowerShell:

```powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
java -jar app.jar
```

All of the above can cause Spring Boot to activate the `dev` profile, provided the configuration source is not overridden by a higher-precedence source.

### 13.4. Multiple Profiles

```bash
java -jar app.jar --spring.profiles.active=prod,cloud
```

Spring Boot can evaluate these profiles together. If multiple files or documents define the same key, you should check the precedence rules across loaded sources and the relevant profile ordering.

### 13.5. Profiles Are Not Secrets

Selecting `prod` does not automatically turn on security, generate secrets, or enforce data authorization. Profiles only participate in selecting configuration and bean conditions.

Do not hard-code production credentials into command lines or profile files merely because the `prod` profile is active.

## 14. The `server.port` Argument in Web Applications

An easily observable example:

```bash
java -jar app.jar --server.port=9090
```

If the application is a Spring Boot web application using an appropriate embedded server, Spring Boot typically configures the server to listen on port 9090.

With a system property:

```bash
java -Dserver.port=9090 -jar app.jar
```

the same configured value can also be achieved if no higher-precedence source overrides it.

### 14.1. What If the Application Is Not a Web Application?

An application running with:

```java
application.setWebApplicationType(WebApplicationType.NONE);
```

does not have an embedded HTTP server to consume `server.port`. Passing:

```text
--server.port=9090
```

does not turn a non-web application into a web application.

A property only takes effect when a suitable component or auto-configuration actually uses it.

### 14.2. Using a Random Port

```bash
java -jar app.jar --server.port=0
```

When supported by the embedded server, port `0` asks the operating system to choose an available port.

Do not rely on `Environment.getProperty("server.port")` as a guaranteed way to learn the actual port when the property is set to `0`; inspect the web server runtime or the web server initialized event instead.

## 15. Environment Variables and Property Names

In container or orchestrator environments, environment variables are often more convenient than manually editing the `java -jar` command:

```text
SERVER_PORT=8081
SPRING_PROFILES_ACTIVE=prod
```

Spring Boot supports relaxed binding rules to map compatible environment variable names to property names.

Example:

```properties
app.import.batch-size=100
```

Under the canonical-to-environment mapping rules used by Spring Boot for configuration binding, the corresponding environment variable name can be:

```text
APP_IMPORT_BATCHSIZE=100
```

For canonical property names in kebab-case, the general rule replaces dots `.` with underscores `_`, removes hyphens `-`, and converts letters to uppercase.

### 15.1. Do Not Assume All Variable Names Are Equivalent

For example:

```text
APP_IMPORT_BATCH_SIZE
```

may be interpreted differently from `app.import.batch-size` depending on mapping/binding rules. When deploying, follow the naming conventions documented for your Spring Boot version and verify them with a binding test.

### 15.2. Environment Variables and `System.getenv`

```java
String port = System.getenv("SERVER_PORT");
```

reads an environment variable named strictly `SERVER_PORT`.

Whereas:

```java
environment.getProperty("server.port")
```

gives Spring the opportunity to resolve `server.port` across multiple sources, including environment variables according to the applicable rules.

Therefore, for business code consuming Spring Boot configuration, `Environment` or `@ConfigurationProperties` is usually more flexible than calling `System.getenv()` directly.

## 16. Specifying Config File Locations When Running a JAR

Spring Boot supports Config Data from default locations as well as additionally specified locations.

Suppose a deployment has:

```text
deploy/
├── order-service.jar
└── config/
    └── application-prod.yml
```

You can supply the config location using an appropriate startup argument.

### 16.1. `spring.config.additional-location`

Example:

```bash
java -jar order-service.jar \
  --spring.profiles.active=prod \
  --spring.config.additional-location=optional:file:./config/
```

Meaning:

- `additional-location` adds locations for Config Data search beyond the default locations.
- `file:./config/` is a directory relative to the working directory.
- The trailing `/` indicates this is a directory where Spring Boot should search for config file names.
- `optional:` allows the location not to exist without causing startup to fail solely due to a missing location.

### 16.2. Using a JVM System Property

Another way to write it:

```bash
java -Dspring.config.additional-location=optional:file:./config/ \
  -jar order-service.jar \
  --spring.profiles.active=prod
```

Properties that control Config Data discovery, such as `spring.config.name`, `spring.config.location`, and `spring.config.additional-location`, must be supplied **early enough** for Spring Boot to know where to look for configuration.

### 16.3. Distinguishing `location` and `additional-location`

| Property | Purpose |
| --- | --- |
| `spring.config.location` | Specifies configuration locations and can replace the default locations |
| `spring.config.additional-location` | Appends locations to the default search list |
| `spring.config.name` | Replaces the default logical name `application` |
| `spring.config.import` | Imports additional Config Data sources from configuration currently being read |

If you replace all locations and forget the default ones, the application may fail to load a configuration file you assumed was still present.

### 16.4. Working Directory Matters

The command:

```bash
java -jar /opt/apps/order-service.jar \
  --spring.config.additional-location=optional:file:./config/
```

resolves `./config/` relative to the **current working directory**, not necessarily the directory containing the JAR.

If a service manager starts the process in `/var/run`, `./config/` may refer to a different path than when you run the command from `/opt/apps`.

In deployments, establish an explicit working directory or use an appropriate absolute path.

## 17. When to Use `-D` vs. `--`?

| Requirement | Usually sensible choice |
| --- | --- |
| Tuning JVM heap | `-Xms`, `-Xmx`, `-XX` before JAR |
| Setting a Java system property for a Java library | `-Dname=value` before JAR |
| Overriding a Spring Boot property for a single run | `--name=value` after JAR |
| Setting the active profile when running the app | `--spring.profiles.active=...`, `-D...`, or environment |
| Passing an input file to a batch CLI | Non-option application argument |
| Reading options from `ApplicationArguments` | `--name=value` |
| Using typed Spring configuration binding | Property sources + `@ConfigurationProperties` |
| Configuring from an orchestrator without editing the JAR command | Environment variables or an appropriate configuration system |

### 17.1. A Design Principle

If a value is **Spring Boot application configuration** (timeout, feature flag, endpoint), you can use `--` or externalized configuration.

If a value is a **JVM operational setting** (heap, garbage collector, or a JVM system property required by the runtime), configure it before `-jar`.

If a value is a **business command argument**, such as an input file name or import mode, `ApplicationArguments` is the appropriate API.

There is no need to force all information into a single source.

## 18. Combined Example: Application with Both Configuration and CLI Mode

Suppose an application can either run a web server or perform an import task.

### 18.1. Application Class

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

### 18.2. Default Configuration

`application.properties`:

```properties
spring.application.name=demo-runner
app.import.batch-size=100
app.import.dry-run=false
app.import.timeout=20s
```

### 18.3. Typed Configuration

`ImportProperties.java`:

```java
package com.example.demo.config;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "app.import")
public record ImportProperties(
        int batchSize,
        boolean dryRun,
        Duration timeout
) {
}
```

### 18.4. Runner Handling Arguments

`ImportRunner.java`:

```java
package com.example.demo.startup;

import com.example.demo.config.ImportProperties;
import java.util.List;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.stereotype.Component;

@Component
public class ImportRunner implements ApplicationRunner {

    private final ImportProperties properties;

    public ImportRunner(ImportProperties properties) {
        this.properties = properties;
    }

    @Override
    public void run(ApplicationArguments args) {
        List<String> modes = args.getOptionValues("app.mode");

        String mode =
                modes == null || modes.isEmpty()
                        ? "serve"
                        : modes.get(0);

        System.out.println("Selected mode: " + mode);

        if ("import".equals(mode)) {
            List<String> files = args.getNonOptionArgs();

            if (files.size() != 1) {
                throw new IllegalArgumentException(
                        "Import mode requires one input file"
                );
            }

            String inputFile = files.get(0);

            System.out.println(
                    "Import started, batchSize=" +
                    properties.batchSize() +
                    ", dryRun=" +
                    properties.dryRun() +
                    ", timeout=" +
                    properties.timeout()
            );

            // Invoke the import service with inputFile in a real application.
            // Do not print the raw file path if it might contain PII or secrets.
        }
    }
}
```

This is an example illustrating API separation. In a real application, `inputFile` must be validated for path safety, permissions, and content type before opening.

In addition, this example **does not automatically shut down the web server in import mode**. If you want an import job to run once and then exit the process, design the startup mode and lifecycle explicitly—for instance, running with `WebApplicationType.NONE` as appropriate or separating the batch application from the web service.

### 18.5. Data Import Run Command

```bash
java -Xmx512m \
  -Dapp.instance=import-worker-01 \
  -jar demo-runner.jar \
  --app.mode=import \
  --app.import.batch-size=250 \
  --app.import.dry-run=true \
  --app.import.timeout=30s \
  input.csv
```

Breakdown:

| Component | Source / Meaning |
| --- | --- |
| `-Xmx512m` | JVM heap option |
| `-Dapp.instance=import-worker-01` | JVM system property |
| `--app.mode=import` | Application option, read by the runner from `ApplicationArguments` |
| `--app.import.batch-size=250` | Spring property bound into `ImportProperties` |
| `--app.import.dry-run=true` | Spring Boolean property |
| `--app.import.timeout=30s` | Spring property converted to `Duration` |
| `input.csv` | Non-option application argument |

### 18.6. What Can Java and Spring Read?

In the example above:

```java
System.getProperty("app.instance")  // "import-worker-01"
```

```java
args.getOptionValues("app.mode")    // ["import"]
```

```java
properties.batchSize()             // 250
```

```java
properties.dryRun()                // true
```

```java
properties.timeout()               // PT30S
```

These are illustrative values assuming proper configuration properties registration and no startup errors.

## 19. Passing Arguments with Spaces and Special Characters

The shell processes the command **before** Java receives the arguments. Spaces, quotes, and shell control characters can cause a single value to be split into multiple arguments.

### 19.1. Bash: Linux/macOS

Example:

```bash
java '-Dapp.display-name=Order Service' \
  -jar 'build/libs/order-service.jar' \
  '--app.greeting=Hello Team'
```

Quoted segments help the shell pass each element as **a single argument**.

For paths containing spaces:

```bash
java -jar '/opt/apps/Order Service/order-service.jar'
```

### 19.2. Windows PowerShell

Example:

```powershell
java '-Dapp.display-name=Order Service' `
  -jar '.\build\libs\order-service.jar' `
  '--app.greeting=Hello Team'
```

In PowerShell, the line-continuation character is the backtick. The backtick must be at the very end of the line with no trailing space after it.

Environment syntax:

```powershell
$env:SPRING_PROFILES_ACTIVE = 'dev'
java -jar '.\build\libs\order-service.jar'
```

### 19.3. Windows Command Prompt

Single-line example:

```bat
java "-Dapp.display-name=Order Service" -jar "C:\Apps\Order Service\order-service.jar" "--app.greeting=Hello Team"
```

Quoting rules can differ among Bash, PowerShell, and CMD. Avoid copying multiline Bash commands using `\` straight into PowerShell/CMD and assuming all shells interpret them identically.

### 19.4. URLs and the `&` Character

Example URL:

```text
https://example.test/api?mode=full&lang=vi
```

The `&` character has special meaning in several shells. When passing a URL value on the command line, quote the entire argument:

```bash
java -jar app.jar '--app.partner-url=https://example.test/api?mode=full&lang=vi'
```

This is a shell syntax example and does not mean a URL containing a token or secret should be placed in process arguments.

## 20. Do Not Pass Secrets on the Command Line When Safer Ways Exist

Example of what to avoid:

```bash
java -Ddb.password=super-secret -jar app.jar
```

or:

```bash
java -jar app.jar --db.password=super-secret
```

These values can show up in:

- Shell history.
- Process command lines or process monitoring information.
- Diagnostic tools, crash reports, or JVM utilities.
- Deployment scripts and CI/CD logs.
- Screenshots or terminal output during incident investigation.

JVM system properties can also be read by code in the same process and by certain diagnostic tools depending on permissions.

### 20.1. Use Proper Secret Management

Example property in a file:

```properties
spring.datasource.password=${DB_PASSWORD}
```

Or YAML:

```yaml
spring:
  datasource:
    password: "${DB_PASSWORD}"
```

Then provide the secret through the deployment environment's secret management mechanism. Environment variables still require appropriate access permissions and controls; for stronger protection requirements, use mounted secrets or a secrets manager.

**Do not log all of `ApplicationArguments`, `System.getProperties()`, or `Environment`**, as they may contain sensitive information.

### 20.2. Do Not Put Credentials in `--spring.config.location`

A configuration path might not be a secret itself, yet some URLs or location strings can include tokens or authentication details.

Do not generate deployment commands containing secrets in URLs unless designed with proper protection, and avoid printing raw command lines to operational logs.

## 21. Docker and Containers: JVM Options Must Still Be in the Right Place

In containers, the Java launcher rules do not change.

Conceptual Dockerfile example:

```dockerfile
FROM eclipse-temurin:21-jre
WORKDIR /app
COPY build/libs/order-service.jar /app/app.jar
ENTRYPOINT ["java", "-Xmx512m", "-jar", "/app/app.jar"]
```

When running:

```bash
docker run --rm order-service:latest \
  --spring.profiles.active=prod \
  --server.port=8080
```

With an `ENTRYPOINT` in JSON exec form as above, arguments after the image name are appended to the end of the command, **after** `/app/app.jar`, so they become application arguments.

### 21.1. What If You Need to Change the JVM Heap in a Container?

You cannot assume that:

```bash
docker run order-service:latest -Xmx1g
```

will change the JVM heap when the image uses the `ENTRYPOINT`:

```text
java -Xmx512m -jar /app/app.jar
```

Because `-Xmx1g`, when appended at the end, is an application argument, not a JVM option.

Change JVM arguments via an `ENTRYPOINT` designed for that configuration, supported Java launcher environment options such as `JAVA_TOOL_OPTIONS` where appropriate, or suitable deployment configuration.

### 21.2. Using Environment Variables for Spring Config

Example:

```bash
docker run --rm \
  -e SPRING_PROFILES_ACTIVE=prod \
  -e SERVER_PORT=8080 \
  order-service:latest
```

This is a common way to configure Spring Boot inside a container without modifying the command after the JAR name.

### 21.3. Container Memory Limit Differs from Heap Limit

`-Xmx512m` limits the heap, but the JVM also uses non-heap memory for metaspace, native allocations, direct buffers, thread stacks, and other components.

If a container has a 512 MiB limit, setting maximum heap to 512 MiB can cause total process memory to exceed the limit. Design your JVM memory budget around total process memory rather than treating `-Xmx` as an absolute RSS ceiling.

## 22. Running `java -jar` from systemd or a Service Manager

In production, processes are usually managed by a service manager rather than run manually in a terminal.

Illustrative unit file example:

```ini
[Unit]
Description=Order Service
After=network.target

[Service]
WorkingDirectory=/opt/order-service
ExecStart=/usr/bin/java -Xms256m -Xmx768m -jar /opt/order-service/app.jar --spring.profiles.active=prod
Restart=on-failure

[Install]
WantedBy=multi-user.target
```

This is a minimal configuration illustrating `ExecStart` and working directory; it does not yet include the service user, sandboxing, secret management, health checks, or other production operational requirements.

### 22.1. Why Does `WorkingDirectory` Matter?

If an application argument contains:

```text
--spring.config.additional-location=optional:file:./config/
```

then `./config/` is resolved relative to the process's working directory.

In systemd, `WorkingDirectory` helps prevent the application from loading a different configuration directory than expected.

### 22.2. Do Not Use Command-Line Arguments to Store Secrets

Service managers may store or expose parts of the startup command in metadata. Credentials should flow through an appropriate secret mechanism instead of being written directly in `ExecStart`.

## 23. Diagnosing `java -jar` Run Errors

### 23.1. `Unable to access jarfile`

Example:

```text
Error: Unable to access jarfile app.jar
```

Common causes:

- Wrong path.
- Incorrect working directory.
- File not yet built or artifact name differs from expected.
- Process lacks read permission for the file.

**How to handle:** verify that the file exists at the actual path, use an absolute path when needed, and check read permissions. This is not a Spring profile error.

### 23.2. `no main manifest attribute`

Example:

```text
no main manifest attribute, in app.jar
```

Cause: the JAR does not have an appropriate entry point for `-jar` mode.

**How to handle:** check the build plugin, `bootJar`/`repackage`, and select the executable artifact rather than a library JAR or plain JAR.

### 23.3. `UnsupportedClassVersionError`

For example, an older Java runtime attempts to run bytecode built with a newer Java version.

**How to handle:** identify the build's target bytecode version and the runtime Java version:

```bash
java -version
```

This error cannot be fixed with `--server.port` or by changing the active profile.

### 23.4. `Unrecognized option`

Example:

```bash
java --server.port=8081 -jar app.jar
```

Cause: placing an application option in the position reserved for JVM options.

**How to handle:**

```bash
java -jar app.jar --server.port=8081
```

### 23.5. `-D` Has No Effect

Incorrect:

```bash
java -jar app.jar -Dserver.port=8081
```

Correct:

```bash
java -Dserver.port=8081 -jar app.jar
```

Or:

```bash
java -jar app.jar --server.port=8081
```

### 23.6. `--server.port` Is Ignored

Check:

1. Is the application actually a web application?
2. Is `--server.port=...` placed after the JAR name?
3. Is `SpringApplication.setAddCommandLineProperties(false)` being used?
4. Does the application have a custom property source, profile, or web server factory customization?
5. Was the command line parsed by the shell into a single proper argument?
6. Are you checking the configured port or the actual runtime port?

Do not assume every port issue is a precedence bug.

### 23.7. `prod` Profile Is Not Activated

Verify:

```bash
java -jar app.jar --spring.profiles.active=prod
```

or:

```bash
java -Dspring.profiles.active=prod -jar app.jar
```

If it is still wrong, check the actual active profiles and overriding sources, especially environment variables, other command-line options, or startup logic that configures profiles programmatically.

### 23.8. `ApplicationArguments` Parsing Issue

You passed:

```bash
java -jar app.jar --app.mode import
```

yet `getOptionValues("app.mode")` does not include `import`.

**How to fix:**

```bash
java -jar app.jar --app.mode=import
```

Do not assume `--name value` is handled like `--name=value` in the default parser.

### 23.9. Reading `System.getProperty` Returns `null`

You ran:

```bash
java -jar app.jar --app.mode=import
```

and then called:

```java
System.getProperty("app.mode")
```

The value may be `null` because that is a command-line application argument, not a JVM system property.

Use:

```java
environment.getProperty("app.mode")
```

or:

```java
args.getOptionValues("app.mode")
```

depending on your intent.

### 23.10. Application JAR and Plain Classpath

The Java launcher has specific rules when using `-jar`; you should not assume that adding `-cp` or `-classpath` will replace the classpath mechanism of an executable JAR.

If you need to alter how external dependencies are loaded outside the JAR, use a packaging and launcher approach supported by Spring Boot/JVM rather than arbitrarily combining `-cp` with `-jar`.

## 24. How to Inspect Actual Startup Configuration

### 24.1. Logging Non-Sensitive Configuration via a Runner

Example:

```java
package com.example.demo.startup;

import java.util.Arrays;
import org.springframework.boot.ApplicationArguments;
import org.springframework.boot.ApplicationRunner;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;

@Component
public class StartupReporter implements ApplicationRunner {

    private final Environment environment;

    public StartupReporter(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void run(ApplicationArguments args) {
        System.out.println(
                "Active profiles: " +
                Arrays.toString(environment.getActiveProfiles())
        );

        System.out.println(
                "Configured port: " +
                environment.getProperty("server.port", "default")
        );

        System.out.println(
                "Mode: " +
                environment.getProperty("app.mode", "serve")
        );

        System.out.println(
                "Has mode CLI option: " +
                args.containsOption("app.mode")
        );
    }
}
```

The example only reads properties judged to be non-sensitive. Do not print the entire `Environment` or `ApplicationArguments` for debugging in environments that may contain secrets.

### 24.2. Inspecting the Conditions Evaluation Report

When you need to see why an auto-configuration was applied or skipped, you can run:

```bash
java -jar app.jar --debug
```

This helps diagnose Spring Boot conditions; it is not a tool for listing every value across property sources.

### 24.3. Actuator in Controlled Environments

Spring Boot Actuator can provide endpoints for environment and configuration properties when dependencies and exposure are properly configured:

```text
/actuator/env
/actuator/configprops
```

These endpoints can contain sensitive metadata. Do not expose them publicly just to check `server.port`; apply proper authentication/authorization, masking, and network restrictions.

### 24.4. Verifying by Actual Behavior

If you want to confirm that the HTTP server is running on port 8081, check the startup logs or send an actual HTTP request to that port.

If you want to confirm that import runs with batch size 250, inspect the typed configuration value and processing behavior rather than only looking at the string in the shell command.

## 25. Practical Scenarios and How to Choose the Command

| Requirement | Illustrative command |
| --- | --- |
| Run default JAR | `java -jar app.jar` |
| Limit heap to 512 MiB | `java -Xmx512m -jar app.jar` |
| Select `dev` profile | `java -jar app.jar --spring.profiles.active=dev` |
| Select `prod` profile via system property | `java -Dspring.profiles.active=prod -jar app.jar` |
| Change HTTP port | `java -jar app.jar --server.port=9090` |
| Run on a random port | `java -jar app.jar --server.port=0` |
| Enable Spring Boot debug report | `java -jar app.jar --debug` |
| Set a system property for a library | `java -Dapp.instance=worker-1 -jar app.jar` |
| Pass import mode and file | `java -jar app.jar --app.mode=import input.csv` |
| Add external config location | `java -jar app.jar --spring.config.additional-location=optional:file:./config/` |
| Combine JVM and Spring options | `java -Xmx512m -Dapp.instance=a -jar app.jar --server.port=8081` |

All examples assume a valid executable JAR and properties actually supported by the application or Spring Boot.

## 26. Practice Exercises

### Exercise 1 — Classify Each Part of the Command

Given:

```bash
java -Xms128m -Xmx512m \
  -Dapp.node=node-01 \
  -jar order-service.jar \
  --spring.profiles.active=staging \
  --server.port=8181 \
  --app.mode=serve
```

Classify each part as a JVM option, JVM system property, executable JAR path, or application argument. Explain why `-Dapp.node=node-01` and `--app.mode=serve` do not go into the same configuration source.

### Exercise 2 — Fix an Out-of-Order Command

Incorrect command:

```bash
java -jar order-service.jar -Xmx1g -Dspring.profiles.active=dev
```

Fix it so the JVM has a 1 GiB heap limit and Spring Boot runs the `dev` profile. Also write a version using `--spring.profiles.active=dev`.

### Exercise 3 — Compare Java and Spring APIs

Run:

```bash
java -Dapp.mode=serve -jar app.jar --app.mode=batch
```

Predict:

```java
System.getProperty("app.mode")
environment.getProperty("app.mode")
applicationArguments.getOptionValues("app.mode")
```

Explain why the different results are expected behavior rather than a bug.

### Exercise 4 — Reading Arguments with `ApplicationArguments`

Run:

```bash
java -jar app.jar --app.mode=import --app.dry-run=true input.csv
```

Write an `ApplicationRunner` that prints the number of non-option arguments and inspects `app.mode` and `app.dry-run`. Do not print the raw file path if it might contain sensitive data.

### Exercise 5 — `CommandLineRunner`

Write a `CommandLineRunner` that counts the elements in `String... args`.

Explain how it differs from `ApplicationRunner` and when to choose each interface.

### Exercise 6 — Overriding `server.port`

Set:

```properties
server.port=8080
```

In the environment, set `SERVER_PORT=8081`. Start with:

```bash
java -Dserver.port=8082 -jar app.jar --server.port=8083
```

Predict the value under default precedence. Then remove each source one by one and observe the changes.

### Exercise 7 — `setAddCommandLineProperties(false)`

Switch from static `SpringApplication.run(...)` to a `SpringApplication` instance and call:

```java
application.setAddCommandLineProperties(false);
```

Run with `--app.mode=import`, and inspect `ApplicationArguments` and `Environment`.

Explain why one API still knows about the option while the other may no longer use that option's value.

### Exercise 8 — Selecting a Profile from Three Sources

Create `application-dev.yml` and `application-prod.yml` with different log levels or ports.

Activate the profile in turn using:

1. `--spring.profiles.active=dev`.
2. `-Dspring.profiles.active=dev`.
3. `SPRING_PROFILES_ACTIVE=dev`.

Check the active profiles and describe the differences in how they are passed.

### Exercise 9 — Configuring `@ConfigurationProperties`

Create an `ImportProperties` record with `batchSize`, `dryRun`, and `timeout`.

Run:

```bash
java -jar app.jar \
  --app.import.batch-size=500 \
  --app.import.dry-run=true \
  --app.import.timeout=45s
```

Verify that typed binding receives `500`, `true`, and `Duration.ofSeconds(45)`.

### Exercise 10 — External Configuration Path

Create a `config/` directory next to where you run the process and place an `application-dev.yml` file inside it.

Run:

```bash
java -jar app.jar \
  --spring.profiles.active=dev \
  --spring.config.additional-location=optional:file:./config/
```

Then change the working directory and run it again. Explain why `./config/` may point to a different place.

### Exercise 11 — Shell Quoting

Pass the value:

```text
app.display-name=Order Management Service
```

as a JVM system property and as a Spring Boot application argument.

Write appropriate commands for Bash and PowerShell, ensuring each string containing spaces is passed as **a single argument**.

### Exercise 12 — Handling Executable JAR Errors

Suppose you run:

```bash
java -jar library.jar
```

and receive `no main manifest attribute`.

Identify what needs to be checked in Gradle/Maven packaging, distinguishing between a plain JAR and a Spring Boot executable JAR.

### Exercise 13 — Container Entrypoint

Given a Dockerfile with:

```dockerfile
ENTRYPOINT ["java", "-Xmx512m", "-jar", "/app/app.jar"]
```

Explain what happens if you run:

```bash
docker run demo-image -Xmx1g --spring.profiles.active=prod
```

Which part is an application argument, and which part is actually a JVM option? Suggest an appropriate way to manage the JVM heap and active profile for containers.

### Exercise 14 — Avoiding Secret Exposure

An operator proposes:

```bash
java -jar app.jar --spring.datasource.password=my-password
```

Explain the risks regarding the process command line, shell history, and logs. Suggest using a secret manager or protected secret-delivery mechanism, and verify that code does not dump `ApplicationArguments`.

### Exercise 15 — Designing Application Run Documentation

Write an operational guide for a Spring Boot service covering:

- Command to build the executable JAR.
- Command to run with `dev`.
- Command to run with `prod`.
- Example JVM heap configuration.
- How to specify external config.
- How to check active profiles.
- How to detect options placed on the wrong side of `-jar`.
- The rule against passing secrets on the command line.

Clearly state which values are examples and which parameters must be adjusted for the actual environment.

## 27. Summary

`java -jar` is the Java launcher mode used to run an **executable JAR**. In Spring Boot, an executable artifact is typically created using Gradle `bootJar` or Maven `repackage` through the corresponding plugin.

A run command has the structure:

```text
java [JVM options] -jar app.jar [application arguments]
```

JVM options such as `-Xmx`, `-Xms`, and Java system properties of the form `-Dname=value` must appear **before** `-jar`. Strings such as `--spring.profiles.active=dev`, `--server.port=9090`, or `--app.mode=import` go **after** the JAR name so they are passed into `main(String[] args)` and processed by Spring Boot where applicable.

`System.getProperty()` only reads JVM system properties; `ApplicationArguments` reads application arguments; and Spring `Environment` can resolve a property across multiple sources with an order of precedence. Under default settings, Spring Boot command-line properties generally take precedence over Java system properties and `application.*` files.

When deploying, distinguish between **JVM operational options**, **Spring Boot configuration**, and **business arguments**. Place arguments in the right positions, control property precedence, verify the actual configuration after startup, and avoid passing passwords, tokens, or sensitive information as command-line arguments. Mastering these principles helps you run, package, and operate Spring Boot applications predictably locally, on servers, and in containers.
