# Early Initialization Requirements for Converters and Dependency Limits in Spring Boot

## 1. Why Can a Seemingly Simple `Converter` Prevent an Application from Starting?

In Spring Boot, configuration from `application.yaml`, environment variables, and command-line arguments is typically bound into `@ConfigurationProperties` beans. Spring Boot already knows how to convert many standard types such as `String` to `Duration`, `DataSize`, `URI`, `Enum`, numbers, and booleans. When an application defines a custom value type, you can provide a `Converter`.

For example:

```yaml
routing:
  primary: "ap-southeast-1/payments"
  timeout: 2s
```

In Java, the expected configuration group:

```java
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        NodeRef primary,
        Duration timeout
) {}
```

`NodeRef` is a domain type holding two parts: `region` and `service`. A custom converter can read `"ap-southeast-1/payments"` to construct a `NodeRef` object.

The catch is: **converters supporting configuration binding may be requested by Spring Boot very early in the startup lifecycle**. If a converter or its `ConversionService` depends on beans that have not finished initializing—such as a `DataSource`, business services, HTTP clients, other `@ConfigurationProperties` beans, or proxies relying on bean post-processors—the application context can fail, form circular dependencies, or emit early-initialization warnings.

Spring Boot recommends **limiting the dependencies of beans involved in configuration conversion**. In particular, when declaring a converter via `@Bean` with `@ConfigurationPropertiesBinding`, use a **`static` method** so Spring does not have to eagerly instantiate the enclosing `@Configuration` class itself.

> Core principle: **Configuration data conversion should be a small, pure, deterministic transformation with no I/O and no dependency on a fully started application.**

This lesson belongs to the **Type Conversion** section of **Spring Boot Externalized Configuration**.

After this lesson, you will be able to:

1. Explain why property binding runs while many application beans are still not ready.
2. Distinguish a general `ConversionService`, a converter with `@ConfigurationPropertiesBinding`, and converters used inside business logic.
3. Understand the special significance of a bean named `conversionService`.
4. Write a custom `String -> NodeRef` converter with minimal dependencies.
5. Register a converter using `static @Bean` and `@ConfigurationPropertiesBinding` in Spring Boot 3.3.
6. Explain problems caused by injecting `@ConfigurationProperties`, `DataSource`, or other services into a converter.
7. Fail early when configuration data cannot be converted.
8. Use `ApplicationConversionService` when you genuinely need to supply a `conversionService` bean yourself.
9. Run and test an illustrative Java 21 / Gradle / Spring Boot project.
10. Design a clean boundary between **reading/converting configuration** and **logic requiring runtime resources**.

**Learning environment:** Java 21, Spring Boot 3.3.x. Domain names, regions, and services in the examples are synthetic; no real network connections are made.

## 2. Placing Converters in the Spring Boot Lifecycle Timeline

A simplified view of application startup:

```text
SpringApplication.run(...)
        |
        v
Prepare Environment
        |
        v
Load Config Data and property sources
        |
        v
Prepare ApplicationContext and bean definitions
        |
        v
Certain @ConfigurationProperties beans need creation / binding
        |
        +--> Binder retrieves ConversionService / converters
        |       |
        |       +--> May request them very early
        |
        v
Remaining application beans continue initializing
        |
        v
BeanPostProcessors, initialization callbacks, proxies...
        |
        v
ApplicationRunner / CommandLineRunner
        |
        v
Application ready to serve work
```

This is a **conceptual diagram**, not an exhaustive list of internal callbacks, nor does it mean every bean is created in a strict linear sequence. Beans can be instantiated on demand due to dependencies, lazy behavior, auto-configuration, and context scoping. What matters is that **configuration conversion sits on the initialization path of beans requiring configuration**, while many other dependencies have not yet completed their lifecycle.

For example:

```java
@Service
public class ApiService {
    public ApiService(RoutingProperties properties) {
        // Service can only be created once RoutingProperties is bound.
    }
}
```

To create `ApiService`, Spring needs `RoutingProperties`. To create `RoutingProperties`, the binder must convert `routing.primary` into `NodeRef`. Consequently, the relevant converter must be discovered and usable **before `ApiService` can operate**.

If the converter in turn requires `ApiService`, you introduce a structural dependency cycle:

```text
ApiService
   -> RoutingProperties
       -> NodeRef Converter
           -> ApiService
```

That design flaw cannot be fixed by increasing YAML file precedence. It is an **initialization dependency error**, not a configuration location or profile error.

### 2.1. "Very Early" Does Not Mean "Before Every Bean"

Some infrastructure beans may already exist when the converter is created. Nevertheless, do not rely on a particular service happening to be available on your development machine. Spring Boot warns that dependencies you request may not yet be fully initialized.

Takeaway: instead of asking "can I autowire service X into the converter?", ask "**why would parsing a configuration value need service X?**" Usually, parsing should need nothing beyond the input string and plain Java functions.

### 2.2. Converters Run During Binding, Not Necessarily Just Once

Do not assume `convert()` is invoked only once across the entire application lifetime. The binder may request conversions for multiple properties or contexts. Avoid side effects such as writing to a database, sending requests, or incrementing business counters inside a converter.

Given identical input, a converter should produce identical output or throw the same kind of syntax error, regardless of application bean state.

## 3. Three Options for Type Conversion in Externalized Configuration Binding

Spring Boot supports multiple mechanisms. For this lesson, distinguish:

| Mechanism | Usage Scope | When to Choose? | Key Caveat |
| --- | --- | --- | --- |
| Converter with `@ConfigurationPropertiesBinding` | Conversion serving `@ConfigurationProperties` | Specific application-defined target types | No need to replace global `ConversionService`; created early, keep dependencies minimal |
| Bean named **`conversionService`** | `ConversionService` looked up by name by infrastructure | When you truly need to supply a conversion service for binding or broader use | Can be requested very early; easily causes unintended side effects |
| `CustomEditorConfigurer` and property editors | JavaBeans/PropertyEditor-style conversion | Legacy integrations requiring editors | Must understand scope and lifecycle; not the default for new types |

In practice, before writing a custom converter, check Spring Boot's built-in converters. Types like `Duration` and `DataSize` already have very convenient configuration syntax:

```yaml
client:
  connect-timeout: 500ms
  max-buffer-size: 8MB
```

Java:

```java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        Duration connectTimeout,
        DataSize maxBufferSize
) {}
```

There is no need to write a custom converter just to parse `500ms` or `8MB` in a standard Spring Boot application.

### 3.1. What Is `@ConfigurationPropertiesBinding`?

Annotation:

```java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
```

marks a bean as participating in `@ConfigurationProperties` binding—typically a `Converter` or `GenericConverter`. It is a specialized qualifier, not an annotation that turns an arbitrary class into configuration properties.

Example:

```java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, NodeRef> nodeRefConverter() {
    return new NodeRefConverter();
}
```

This is the preferred choice for our lab because we only need to add one custom conversion without replacing the entire default conversion service.

### 3.2. The Bean Name `conversionService` Has Special Meaning

A bean:

```java
@Bean("conversionService")
ConversionService conversionService() {
    ...
}
```

is not just a regular bean that happens to have a nice name. Spring/Spring Boot infrastructure may look up a bean with this exact name for conversion needs.

When that bean is found and created early, all dependencies required to build it are also pulled into early initialization. If those include a service using a `DataSource`, REST client, transactional proxy, or another config bean, you may pull an entire branch of your application into initialization prematurely.

If you create a `ConversionService` **solely to process data inside a business service** and it is not meant for config binding, give it **another name** such as `businessConversionService`. Do not use the name `conversionService` casually.

### 3.3. Bean Name and Annotations Determine the Path

These two declarations are not equivalent:

```java
@Bean("businessConversionService")
ConversionService businessConversionService() {
    ...
}
```

and:

```java
@Bean("conversionService")
ConversionService conversionService() {
    ...
}
```

The first can be explicitly injected into a business service using a qualifier; the second can be picked up early by the framework by convention.

Similarly, an ordinary `Converter<String, NodeRef>` bean does not necessarily become a converter dedicated to `@ConfigurationProperties` automatically. When the goal is binding, register it via Spring Boot's supported mechanism using `@ConfigurationPropertiesBinding`.

## 4. Which Dependencies Cause Risk?

Consider a poorly designed converter:

```java
public final class BadNodeRefConverter
        implements Converter<String, NodeRef> {

    private final RoutingProperties routingProperties;
    private final ApiClient apiClient;

    public BadNodeRefConverter(
            RoutingProperties routingProperties,
            ApiClient apiClient) {
        this.routingProperties = routingProperties;
        this.apiClient = apiClient;
    }

    @Override
    public NodeRef convert(String source) {
        // Suppose it calls apiClient to verify the region at runtime.
        ...
    }
}
```

This design has two flaws:

1. `RoutingProperties` **needs the converter to be bound**, yet the converter demands `RoutingProperties` in its constructor. That is an immediate circular dependency.
2. `ApiClient` may itself need `RoutingProperties` for its base URL, timeout, or credentials; internally it may also rely on proxies, interceptors, or resources not yet finalized when the converter is requested.

High-risk dependencies include:

- The `@ConfigurationProperties` bean using that very converter.
- `DataSource`, `EntityManager`, repositories, or transaction managers.
- Services making HTTP/gRPC calls to external systems.
- Beans requiring a request security context.
- `@Transactional`, AOP proxies, lazy initialization, or specialized `BeanPostProcessor`s.
- Beans with `@PostConstruct` performing heavy I/O.
- Objects depending on an open server port or live traffic.
- Schedulers or queue consumers meant to start only after boot.

Not every dependency in this list is **guaranteed** to crash. The danger comes from ordering, cycles, side effects, and incomplete initialization. Thus the safer strategy is **keeping them out of the configuration-parsing layer**.

### 4.1. Do Not Verify Remote Entities Inside a Converter

A converter receiving `"ap-southeast-1/payments"` only needs to verify that the string has two syntactically valid parts. It does not need to log into Kubernetes, query a database to see if the service exists, or call a discovery API.

If business rules genuinely require verifying service existence, move that work into a **startup validator/service** that runs after beans and required resources are ready. Separate:

```text
Pure parser:
"ap-southeast-1/payments" -> NodeRef("ap-southeast-1", "payments")

Business logic:
NodeRef -> check region catalog / external system
```

These two tasks belong to different lifecycle phases and resource access levels.

### 4.2. Be Careful Using `Environment` as a Dependency

Reading `Environment` can be valid in certain infrastructure components, but having a converter both parse a source property and query additional properties increases coupling and circular-reference risk.

If the input syntax already contains all needed data, let the converter **accept the input as an argument** without querying `Environment`.

## 5. Complete Example: Converting `"region/service"` to `NodeRef`

Lab goal:

```properties
routing.primary=ap-southeast-1/payments
```

binds to:

```java
NodeRef("ap-southeast-1", "payments")
```

The custom converter will use only pure Java operations: `trim`, `split`, and string checks. It has no constructor injection, `@Autowired`, `@Value`, `DataSource`, network calls, or logger printing sensitive values.

### 5.1. Target Type `NodeRef`

Create `src/main/java/dev/example/earlyconversion/NodeRef.java`:

```java
package dev.example.earlyconversion;

import java.util.Objects;

public record NodeRef(String region, String service) {

    public NodeRef {
        Objects.requireNonNull(region, "region");
        Objects.requireNonNull(service, "service");

        if (region.isBlank() || service.isBlank()) {
            throw new IllegalArgumentException(
                    "region and service must not be blank");
        }
    }
}
```

This is a **record** representing a value object, not a Spring bean. It has two `String` components and a simple invariant. There is no reason for `NodeRef` to know about `ApplicationContext`.

In this example, the slash `/` is a separator chosen by the application itself. It is not a universal Spring Boot property delimiter.

### 5.2. `Converter<String, NodeRef>`

Create `src/main/java/dev/example/earlyconversion/NodeRefConverter.java`:

```java
package dev.example.earlyconversion;

import org.springframework.core.convert.converter.Converter;

public final class NodeRefConverter implements Converter<String, NodeRef> {

    @Override
    public NodeRef convert(String source) {
        if (source == null) {
            throw new IllegalArgumentException(
                    "NodeRef source must not be null");
        }

        String[] pieces = source.trim().split("/", -1);

        if (pieces.length != 2) {
            throw new IllegalArgumentException(
                    "NodeRef must have the format region/service");
        }

        String region = pieces[0].trim();
        String service = pieces[1].trim();

        return new NodeRef(region, service);
    }
}
```

With these inputs:

| Input | Result |
| --- | --- |
| `ap-southeast-1/payments` | `NodeRef("ap-southeast-1","payments")` |
| ` eu-west-1 / billing ` | Both components trimmed |
| `payments` | Format error, missing separator |
| `a/b/c` | Error because more than two segments |
| ` / payments` | Error because region is blank |
| `ap-southeast-1/ ` | Error because service is blank |

Benefits of this converter:

- Identical input produces identical output.
- No side effects.
- Creates no threads or sockets.
- Pulls no business dependencies into startup.
- Easy to unit test with `new NodeRefConverter()` without Spring.
- Error messages focus on **syntax**, without attempting to verify data in external systems.

For real values that might hold secrets, never put the raw input into exception messages or logs. The example only describes the `region/service` shape.

## 6. Registering the Converter with `@ConfigurationPropertiesBinding`

Create `src/main/java/dev/example/earlyconversion/ConversionConfiguration.java`:

```java
package dev.example.earlyconversion;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class ConversionConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    public static Converter<String, NodeRef> nodeRefConverter() {
        return new NodeRefConverter();
    }
}
```

This is the most important technical piece of the lesson.

**Why is `@Bean` marked `static`?**

A `static` method can be invoked by Spring to create the bean **without first instantiating `ConversionConfiguration`**. This reduces the chance that the configuration class or its dependencies are initialized early just to provide the converter.

Spring Boot recommends marking `@Bean` methods annotated with `@ConfigurationPropertiesBinding` as `static` to avoid warnings like:

```text
Bean '...' is not eligible for getting processed
by all BeanPostProcessors
```

Warnings of this kind usually indicate a bean was created too early to pass through all bean post-processors. It does not automatically mean the converter's logic is wrong, but it signals that you should review **initialization lifecycle** and dependencies.

**`static @Bean` is NOT the same as `static field @Value`.**

- `static @Bean` method: a factory method that can produce a **bean instance** without needing an instance of the `@Configuration` class.
- `static field @Value`: a Java class field, not standard dependency injection into a bean instance.

In this lesson, Spring still manages `new NodeRefConverter()` as a regular bean. Only the **factory method** is static—conversion results are not stored in a global variable.

### 6.1. Why Not Inject a Service into the `@Bean` Method?

Avoid:

```java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, NodeRef> nodeRefConverter(
        ApiClient apiClient) {
    return new ClientAwareNodeRefConverter(apiClient);
}
```

Even though the method is `static`, Spring still has to resolve the `ApiClient` parameter before creating the converter. Thus `static` alone does not eliminate early-dependency risk. **The real fix is minimizing dependencies, not just adding a keyword.**

### 6.2. Can You Use `@Component` on the Converter?

You can make a converter bean via component scanning and apply the right qualifier in framework-supported cases. However, when the goal is **property binding and early initialization**, Spring Boot documentation recommends `static @Bean` with `@ConfigurationPropertiesBinding` to reduce the risk of prematurely instantiating configuration classes.

Do not register **the exact same converter** twice via both `@Component` and `@Bean`; that complicates bean selection and can introduce ambiguity.

## 7. Configuration Record to Be Bound

Create `src/main/java/dev/example/earlyconversion/RoutingProperties.java`:

```java
package dev.example.earlyconversion;

import java.time.Duration;

import jakarta.validation.constraints.NotNull;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "routing")
public record RoutingProperties(
        @NotNull NodeRef primary,
        @NotNull Duration timeout,
        boolean enabled
) {}
```

When Spring Boot binds `routing.primary`:

```text
Externalized property: "ap-southeast-1/payments"
                         |
                         v
       @ConfigurationProperties Binder
                         |
                         v
       Converter<String, NodeRef>
                         |
                         v
       NodeRef("ap-southeast-1", "payments")
                         |
                         v
             RoutingProperties.primary()
```

`Duration` is already supported by Spring Boot, so there is no need to write `Converter<String, Duration>`. `@NotNull` helps detect missing `primary` or `timeout` when validation is configured.

### 7.1. Registering `@ConfigurationProperties` Properly

Place on the main class:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class EarlyConversionApplication {
    ...
}
```

`@ConfigurationPropertiesScan` lets Spring Boot register and bind `RoutingProperties`. You do not need and should not put `@Component` on a constructor-bound configuration record merely to get it discovered.

With Spring Boot 3.3, constructor binding for records is inferred automatically; there is no need to add class-level `@ConstructorBinding` from older examples.

## 8. Runnable Gradle Project

Minimal structure:

```text
early-conversion-lab/
├── settings.gradle
├── build.gradle
├── gradlew
├── gradlew.bat
└── src/
    ├── main/
    │   ├── java/dev/example/earlyconversion/
    │   │   ├── EarlyConversionApplication.java
    │   │   ├── ConversionConfiguration.java
    │   │   ├── NodeRef.java
    │   │   ├── NodeRefConverter.java
    │   │   └── RoutingProperties.java
    │   └── resources/
    │       ├── application.yaml
    │       └── application-dev.yaml
    └── test/
        └── java/dev/example/earlyconversion/
            ├── NodeRefConverterTest.java
            └── RoutingBindingTest.java
```

Initialize the project using Spring Initializr with Java 21, Gradle, and Spring Boot 3.3.x. The `gradlew` and `gradlew.bat` wrappers should come from the generated project rather than being written by hand.

### 8.1. `settings.gradle`

```groovy
rootProject.name = 'early-conversion-lab'
```

### 8.2. `build.gradle`

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
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

If your project already uses a version catalog or convention plugins, follow the project's build setup. The snippet above is for a standalone project without web dependencies.

### 8.3. `application.yaml`

```yaml
spring:
  main:
    web-application-type: none

routing:
  primary: "ap-southeast-1/payments"
  timeout: 2s
  enabled: true
```

`routing.primary` is a **scalar string**. The converter turns it into a `NodeRef` record; `routing.timeout` is converted by Spring Boot's built-in converter into `Duration`.

Putting real URLs or credentials into files just to test converters is unnecessary. Using non-sensitive `region/service` labels lets you observe behavior without risking console leaks.

### 8.4. Main Class and `ApplicationRunner`

`src/main/java/dev/example/earlyconversion/EarlyConversionApplication.java`:

```java
package dev.example.earlyconversion;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class EarlyConversionApplication {

    public static void main(String[] args) {
        SpringApplication.run(EarlyConversionApplication.class, args);
    }

    @Bean
    ApplicationRunner printConfiguration(RoutingProperties properties) {
        return args -> {
            System.out.println("=== EARLY CONVERSION LAB ===");
            System.out.println("primary.region = "
                    + properties.primary().region());
            System.out.println("primary.service = "
                    + properties.primary().service());
            System.out.println("timeout = "
                    + properties.timeout());
            System.out.println("enabled = "
                    + properties.enabled());
        };
    }
}
```

The application opens no HTTP server. It simply prints the synthetic properties after `RoutingProperties` has been bound and the context has finished the required initialization.

### 8.5. Project Timeline

```text
SpringApplication.run
       |
       v
Spring Boot reads routing.primary from Environment
       |
       v
Binder needs to construct RoutingProperties
       |
       v
Converter bean is retrieved to convert String -> NodeRef
       |
       +--> static @Bean creates NodeRefConverter
       |         |
       |         +--> requires no ApiClient / DataSource
       |
       v
NodeRef is created via convert(...)
       |
       v
RoutingProperties is constructed and validated
       |
       v
ApplicationRunner receives RoutingProperties bean
       |
       v
Prints region/service and timeout information
```

The design goal is that the converter **already operates independently** before services needing `RoutingProperties` are instantiated.

## 9. Run 1: Baseline Configuration

On macOS/Linux:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Key output lines:

```text
=== EARLY CONVERSION LAB ===
primary.region = ap-southeast-1
primary.service = payments
timeout = PT2S
enabled = true
```

`Duration.toString()` displays two seconds as `PT2S`. If you see other Spring Boot startup messages, look for the lines marked `EARLY CONVERSION LAB` to verify.

**Observation goal:** the converter works without any business service, and the `RoutingProperties` bean is completely constructed before `ApplicationRunner` reads it.

### 9.1. Running the JAR Directly

```bash
./gradlew bootJar
java -jar build/libs/early-conversion-lab-0.0.1-SNAPSHOT.jar
```

PowerShell:

```powershell
.\gradlew.bat bootJar
java -jar build\libs\early-conversion-lab-0.0.1-SNAPSHOT.jar
```

If your repository uses custom artifact naming rules, substitute the actual JAR path produced in `build/libs`.

## 10. Run 2: Higher-Precedence Property Source

No Java edits are required to change the region and service.

macOS/Linux:

```bash
./gradlew bootRun --args='--routing.primary=eu-west-1/billing'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--routing.primary=eu-west-1/billing"
```

Expected output:

```text
primary.region = eu-west-1
primary.service = billing
timeout = PT2S
enabled = true
```

CLI arguments can override values from `application.yaml`, while the converter remains the exact same object participating in binding. This illustrates the separation:

```text
Which source supplies the effective value? -> Environment + precedence

How does the string become NodeRef?         -> Converter

Which bean receives the converted value?   -> ConfigurationProperties Binder
```

Do not put profile checks, direct environment variable lookups, or file location queries inside `NodeRefConverter`. The binder already selects the property under external configuration rules.

### 10.1. Using Environment Variables

Bash:

```bash
ROUTING_PRIMARY=ap-northeast-1/reporting ./gradlew bootRun
```

PowerShell:

```powershell
$env:ROUTING_PRIMARY = 'ap-northeast-1/reporting'
.\gradlew.bat bootRun
Remove-Item Env:ROUTING_PRIMARY
```

Expected `NodeRef.region()` is `ap-northeast-1` and service is `reporting`, assuming no higher-precedence source supplies the same key.

`NodeRefConverter` does not need to know whether the string arrived from CLI, YAML, or environment. That is a hallmark of a clean custom converter for type-safe configuration binding.

## 11. Run 3: Profile-Specific Configuration

Create `src/main/resources/application-dev.yaml`:

```yaml
routing:
  primary: "local/mock-service"
  timeout: 500ms
```

Run:

```bash
./gradlew bootRun --args='--spring.profiles.active=dev'
```

PowerShell:

```powershell
.\gradlew.bat bootRun --args="--spring.profiles.active=dev"
```

Expected output:

```text
primary.region = local
primary.service = mock-service
timeout = PT0.5S
enabled = true
```

`routing.enabled` is absent from the dev file, so it is inherited from the base file. Both files are handled by Spring Boot's Config Data mechanism. The converter does not participate in locating profile files—it only receives **the effective property value** and converts it to the required Java type.

When switching profiles, never add conditionals like:

```java
if (profile.equals("dev")) { ... }
```

inside a converter. A converter containing profile-selection logic becomes hard to reuse and coupled to configuration sourcing that the binder already handles.

## 12. Run 4: Invalid Data Must Fail Early

Try:

```bash
./gradlew bootRun --args='--routing.primary=invalid'
```

Now `NodeRefConverter` cannot split into `region/service`. It throws `IllegalArgumentException`, which Spring Boot surfaces during binding, and the application may **fail to start**.

This is good behavior when the configuration is mandatory for the application to run properly.

Other invalid inputs:

```text
routing.primary=
routing.primary=/payments
routing.primary=region/
routing.primary=region/payments/extra
```

In this lab, the application makes no network connections; errors come strictly from **syntax** or **configuration constraints**. Do not mask errors with a fake default and let the app boot when a required value is invalid.

### 12.1. What Should Error Messages Contain?

Good:

```text
NodeRef must have the format region/service
```

Avoid:

```text
Could not parse secret: <full sensitive value>
```

When applying a converter to tokens or structures holding secrets, error messages must avoid printing the raw input. For non-sensitive values, operators can examine the property name and binding failure path to find the cause.

### 12.2. Validation Differs from Conversion

A syntactically invalid string triggers a **conversion** error. A `NodeRef` that converted cleanly yet violates business constraints may require **validation** or a post-binding service check.

In the lab:

- `region/payments` -> syntax parses cleanly.
- `region/` -> converter error due to missing service.
- `region/payments` where the service does not exist on the cluster -> not a parsing error; do not query the cluster from the converter.

Spring Boot Binder and Jakarta Validation solve different layers of problems. Syntax failures belong in the converter; configuration object constraints belong in validation; external checks belong in services once the application is ready.

## 13. Unit Testing the Converter Without Spring

A strong sign of good converter design: it can be unit tested in plain Java without starting an `ApplicationContext`.

Create `src/test/java/dev/example/earlyconversion/NodeRefConverterTest.java`:

```java
package dev.example.earlyconversion;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class NodeRefConverterTest {

    private final NodeRefConverter converter = new NodeRefConverter();

    @Test
    void parsesValidValue() {
        NodeRef parsed = converter.convert("eu-west-1/billing");

        assertEquals("eu-west-1", parsed.region());
        assertEquals("billing", parsed.service());
    }

    @Test
    void trimsWhitespace() {
        NodeRef parsed = converter.convert(
                " eu-west-1 / billing ");

        assertEquals("eu-west-1", parsed.region());
        assertEquals("billing", parsed.service());
    }

    @Test
    void rejectsMissingSeparator() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("billing"));
    }

    @Test
    void rejectsEmptyComponent() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("eu-west-1/"));
    }

    @Test
    void rejectsTooManySegments() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("a/b/c"));
    }
}
```

No mock databases, Kubernetes, network, or Spring container. That is the direct payoff of limiting dependencies in custom converters.

A converter taking `ApiClient` in its constructor would force unit tests to mock the client, manage call order, and handle unexpected exceptions—a sign the parser is taking on inappropriate responsibilities.

## 14. Integration Testing: Proving `@ConfigurationPropertiesBinding` Is Used

Create `src/test/java/dev/example/earlyconversion/RoutingBindingTest.java`:

```java
package dev.example.earlyconversion;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "routing.primary=eu-west-1/invoices",
        "routing.timeout=750ms",
        "routing.enabled=true"
})
class RoutingBindingTest {

    @Autowired
    RoutingProperties routing;

    @Test
    void bindsScalarToCustomRecordUsingConverter() {
        assertEquals("eu-west-1", routing.primary().region());
        assertEquals("invoices", routing.primary().service());
        assertEquals(Duration.ofMillis(750), routing.timeout());
        assertTrue(routing.enabled());
    }
}
```

Run:

macOS/Linux:

```bash
./gradlew test
```

Windows:

```powershell
.\gradlew.bat test
```

This test does two things:

1. Verifies Spring Boot binds a scalar string to `NodeRef` via the registered converter.
2. Verifies built-in types like `Duration` still work alongside the custom converter.

If the converter unit test passes while the binding integration test fails, check bean registration (`@ConfigurationPropertiesBinding`), `@ConfigurationPropertiesScan`, package scanning, property names, and duplicate beans.

### 14.1. What Else Should You Verify?

For critical custom converters, also consider checking:

- Canonical property names match across YAML, CLI, and environment.
- Malformed syntax fails binding.
- Missing values trigger validation errors if configuration is required.
- No network calls or side effects occur in `convert()`.
- The converter has no circular dependencies with the bound bean.
- A second `ApplicationContext` can also create the converter and receive its own context's data.
- Sensitive inputs are never logged.
- The converter bean works alongside Spring Boot's default converters.

This lesson does not need a real database to prove any of these points.

## 15. Why Shouldn't You Replace `conversionService` If You Only Need One Converter?

A team might see that `NodeRef` is not understood by Spring Boot out of the box and try creating:

```java
@Bean("conversionService")
ConversionService customConversionService() {
    ...
}
```

That can work if carefully designed, but it is usually **a much broader change than needed**. You are supplying a bean with a special infrastructure name. It can be invoked early and affect other conversion paths that rely on that service.

Meanwhile:

```java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, NodeRef> nodeRefConverter() {
    return new NodeRefConverter();
}
```

expresses the exact requirement directly: **only add support for binding one configuration type**.

### 15.1. `conversionService` Bean Example Only When Truly Needed

In an application that needs broad customization of the conversion service, you can declare a bean under the standard name. **This is an alternative approach—do not deploy it simultaneously with the converter registration in section 6 of this lab.**

```java
package dev.example.earlyconversion;

import org.springframework.boot.convert.ApplicationConversionService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.ConversionService;

@Configuration(proxyBeanMethods = false)
public class GlobalConversionConfiguration {

    @Bean(name = "conversionService")
    public static ConversionService conversionService() {
        ApplicationConversionService service =
                new ApplicationConversionService();

        service.addConverter(new NodeRefConverter());

        return service;
    }
}
```

Explanation:

- The exact bean name is `conversionService`.
- The factory method is `static` and has **no** dependency parameters.
- `ApplicationConversionService` provides Spring Boot's standard application conversions and formatting, preventing you from accidentally dropping built-in converters when replacing the service with one containing only your app's converters.
- `NodeRefConverter` is added to that service.
- No `DataSource`, `RestClient`, repository, or other config bean participates in constructing the service.
- This approach has a broader blast radius; use it only if you genuinely need full control of the conversion service.

Do not blindly copy this snippet into an arbitrary project that already defines a `conversionService` bean or custom MVC/security/integration conversion without checking impact. When using this broader setup, integration tests should cover standard conversions such as `Duration`.

**In the main lab, keep the `@ConfigurationPropertiesBinding` approach from section 6 and do not add `GlobalConversionConfiguration`.** The two examples illustrate different architectural choices.

### 15.2. Why Not Replace It with an Empty `DefaultConversionService`?

If you construct a minimal conversion service and name it `conversionService`, some default conversions provided by Spring Boot may no longer be configured as expected. For example, `Duration` with `ms`/`s` suffixes and `DataSize` with `MB` suffixes are common Boot expectations.

When providing your own conversion service, start from the conversion foundation appropriate for Spring Boot, add your converters, and test every important configuration type. Never replace the entire service just for one custom value object.

### 15.3. Renaming Conversion Services Intended for Business Logic

If a conversion service only serves a business service after startup:

```java
@Bean("businessConversionService")
ConversionService businessConversionService(...) {
    ...
}
```

then the name makes clear it **is not trying to act as the special infrastructure bean `conversionService`**.

In the consuming service, inject it with the proper qualifier. This reduces the risk of Spring Boot attempting to use a business conversion bean during early binding.

Do not treat renaming as the sole fix if the service still has broken dependency design; it is simply a way to separate scopes cleanly.

## 16. Circular Dependencies: Wrong Model vs. Right Model

### 16.1. Wrong Model

```text
routing.primary
       |
       v
RoutingProperties
       |
       v
Binder needs NodeRefConverter
       |
       v
NodeRefConverter needs RoutingService
       |
       v
RoutingService needs RoutingProperties
       |
       +-----------> cycles back
```

In this setup, no valid bean creation order satisfies all dependencies simultaneously. You can get circular dependency errors or bean initialization failures depending on your configuration.

Do not "fix" this with global static fields, manual `ApplicationContext.getBean()` calls, enabling circular references, or manually instantiating an under-initialized service. Those workarounds mask flawed design and are fragile in production and tests.

### 16.2. Right Model

```text
routing.primary (String)
       |
       v
NodeRefConverter (pure)
       |
       v
NodeRef
       |
       v
RoutingProperties
       |
       v
RoutingService
       |
       +--> can use Repository / HttpClient after binding
```

This is an easy-to-follow directed acyclic graph. The converter knows nothing about the service; the service consumes typed config.

### 16.3. If You Need a Registry to Validate Region Names

Move the check into a bean initialized after binding:

```java
@Service
public class RoutingService {

    private final RoutingProperties properties;
    private final RegionRegistry regionRegistry;

    public RoutingService(
            RoutingProperties properties,
            RegionRegistry regionRegistry) {
        this.properties = properties;
        this.regionRegistry = regionRegistry;
    }

    public boolean isConfiguredRegionKnown() {
        return regionRegistry.contains(
                properties.primary().region());
    }
}
```

`RegionRegistry` can be a component requiring runtime resources; it participates only when the service runs business checks. `NodeRefConverter` continues simply splitting strings. If policy mandates failing fast when a region is invalid, run an intentional startup check after required dependencies are ready and ensure the app takes no traffic until the check passes.

Never trigger automatic network requests every time Spring invokes the binder.

## 17. `BeanPostProcessor` and the "Not Eligible" Warning

Spring uses bean post-processors for many tasks around bean creation, including annotation processing, proxies, and library hooks. When a bean is instantiated **before all processors are registered**, Spring can warn that the bean is not eligible to be processed by all processors.

Example warning:

```text
Bean 'someBean' is not eligible for getting
processed by all BeanPostProcessors
```

One possible cause is a factory method declaring a converter forcing eager instantiation of its `@Configuration` class. If that configuration class holds other dependencies, early initialization can cascade to even more beans.

Using:

```java
@Bean
@ConfigurationPropertiesBinding
public static Converter<String, NodeRef> nodeRefConverter() {
    return new NodeRefConverter();
}
```

allows Spring to create the converter without creating an **instance of the configuration class** just to invoke the `@Bean` method. That is why official guidance emphasizes `static` for factory methods annotated with `@ConfigurationPropertiesBinding`.

Keep in mind, however:

- A `static` method **does not make arbitrary dependencies safe**.
- If the method takes a service parameter, that service still has to be initialized.
- If `new NodeRefConverter()` opens a network connection in its constructor, early side effects still happen.
- If another class's static initializer performs I/O, loading that class early can still cause errors.
- Do not silence every warning by adding `@DependsOn` or tweaking bean order arbitrarily; find out **which dependency is being pulled in too early**.

Practical takeaway: `static @Bean` is a technique to prevent **unnecessary** early instantiation, while **a converter free of application dependencies** is the long-term architectural fix.

## 18. `@Value`, `Environment`, and `@ConfigurationProperties` Are Not the Same

Distinguish the conversion paths:

| Access Method | Primary Mechanism | Custom Converter Note |
| --- | --- | --- |
| `Environment.getProperty("routing.primary")` | Lookup property by name | When returning `String`, no `NodeRef` converter needed |
| `@Value("${routing.primary}") String` | Placeholder and string injection | Can receive the raw scalar |
| `@Value("${routing.primary}") NodeRef` | Placeholder and bean-factory conversion | Do not assume a converter with only `@ConfigurationPropertiesBinding` applies to every `@Value` |
| `@ConfigurationProperties(prefix="routing")` | Typed Binder | Exactly where `@ConfigurationPropertiesBinding` converters are designed to work |

A common misconception is assuming `@ConfigurationPropertiesBinding` registers a converter globally across every Spring API. It is a mechanism **specialized for configuration property binding**.

If a service needs `NodeRef`, the clean approach is:

```java
@Service
public class PaymentRouteService {

    private final RoutingProperties properties;

    public PaymentRouteService(RoutingProperties properties) {
        this.properties = properties;
    }

    public NodeRef primaryRoute() {
        return properties.primary();
    }
}
```

The service does not need `@Value` and duplicate conversion logic. Avoid creating two separate parsing paths just because some code happens to prefer another annotation.

### 18.1. Do You Need a Converter for Every Record?

No. A nested record bound from hierarchical properties like:

```yaml
routing:
  primary:
    region: ap-southeast-1
    service: payments
```

can use structural constructor binding on the record **without a custom `"region/service"` converter**, as long as root and nested types are properly registered/bound.

A custom converter is only needed when you intentionally define **a specialized scalar format**:

```yaml
routing:
  primary: "ap-southeast-1/payments"
```

Before writing a converter, weigh whether the configuration schema can be expressed more clearly as a YAML nested object. With one or two fields, scalar format is compact; with multi-field objects, nested structure is easier to manage and validate.

## 19. Separating Pure Parsing from Validation and Side Effects

A well-balanced design typically has three layers:

```text
Layer 1: Parser / Converter
  Source string -> Java type
  No I/O, no application state

Layer 2: Configuration properties
  NodeRef + Duration + flags
  Bean Validation / invariants at binding time

Layer 3: Startup / business services
  Check service existence, open connections,
  interact with registries, cache, serve requests
```

### 19.1. What Should a Converter Do?

- Trim and normalize per the published contract.
- Split a string into well-defined parts.
- Validate required format.
- Convert scalar to value object.
- Throw a clear exception on invalid input.
- Use basic Java classes so it can be tested without a Spring container.

### 19.2. What Should a Converter Not Do?

- Query a database to verify ID existence.
- Send HTTP requests to validate endpoints.
- Fetch secrets from an external vault just to parse a value.
- Initialize caches or spawn threads.
- Fetch a bean currently being bound from `ApplicationContext`.
- Create schedulers or register consumers.
- Write data or emit business events.
- Depend on request context or user session.
- Log raw sensitive inputs.
- Assume proxy beans are already finalized.

A conversion that requires network calls is no longer configuration type conversion. Move that logic to a component with the right lifecycle.

### 19.3. Startup Checks with Clear Contracts

If an application must verify an endpoint before accepting traffic, run the check after Spring has wired the needed dependencies. Choose the lifecycle hook suited to the framework and application type: a runner, a service-level initializer, or a controlled health/readiness mechanism.

Which hook is right depends on requirements: fail-fast, retries, backoff, readiness, shutdown, startup probes. That belongs to **service startup management**, not scalar property parsing. Never cram those rules into a `Converter`.

## 20. When Is `CustomEditorConfigurer` Needed?

Spring Framework includes `PropertyEditor` and `CustomEditorConfigurer` for certain conversion needs, especially legacy code or framework components using JavaBeans property editors.

In principle, you can register custom editors with the bean factory. Still, note the distinctions:

- Spring's `Converter<S,T>` has an easy-to-test interface tailored to the conversion service model.
- Property editors often involve JavaBeans APIs, stateful editor instances, and different registration scopes.
- Boot's `@ConfigurationProperties` Binder already has a dedicated converter mechanism.
- When maintaining legacy code, know exactly which component uses the editor and which lifecycle phase needs it.

For a new type in a typical Spring Boot application, a custom `Converter<String, T>` with `@ConfigurationPropertiesBinding` is usually much more maintainable than extending legacy JavaBeans editor infrastructure.

Do not conclude that the three options mentioned in Spring Boot's docs are **three steps you must perform together**. They are alternatives depending on your goal.

## 21. Common Problems and How to Diagnose Them

### 21.1. Error Because a Custom `conversionService` Depends on a Config Bean

**Symptom:** startup reports a circular dependency or a bean currently in creation being requested again.

**Possible cause:** `conversionService` or a converter takes a `@ConfigurationProperties` bean that the binder itself needs that conversion service to create.

**Fix:** remove the reverse dependency; write the converter to take raw input and return a value object. Move business logic consuming configuration into services after binding.

### 21.2. Warning That a Bean Does Not Pass Through All Processors

**Symptom:** logs show `not eligible for getting processed by all BeanPostProcessors`.

**Possible cause:** the `@Bean` method providing the converter is non-static, causing the `@Configuration` class or companion beans to initialize early.

**Fix:** use `static @Bean` for `@ConfigurationPropertiesBinding` as recommended by Boot. Also inspect constructors, factory method parameters, and side effects.

### 21.3. Converter Unit Tests Pass, Yet Binding Does Not Apply It

**Symptom:** `new NodeRefConverter().convert(...)` works, yet `RoutingProperties.primary` fails to bind.

**Things to check:**

- Is the converter actually registered as a bean?
- Is `@ConfigurationPropertiesBinding` properly on the factory method?
- Is `ConversionConfiguration` within the application's component-scan packages?
- Is `RoutingProperties` registered via `@ConfigurationPropertiesScan`/`@EnableConfigurationProperties`?
- Does YAML have `routing.primary` and not another key name?
- Is the target type really `NodeRef` and the source a scalar string?
- Is there another converter for the same source/target pair causing ambiguity?

### 21.4. Adding a Converter Breaks `Duration` Conversion

**Symptom:** `client.timeout=2s` used to bind, then after adding a homemade `conversionService` bean, conversion behaves differently or fails.

**Possible cause:** your custom conversion service replaced the default conversion path without retaining all of Boot's converters.

**Fix:** if you only need one custom type, use `@ConfigurationPropertiesBinding`. If you truly need a global service, consider `ApplicationConversionService` and re-test all critical configuration types.

### 21.5. Adding `@Lazy` to a Converter to Avoid Early Creation

**Symptom:** the converter has `@Lazy`, yet during binding it still gets created before other services.

**Explanation:** when the binder needs the converter to create a config bean, the converter must be present. `@Lazy` does not eliminate real dependencies. If a value is required at bind time, the converter cannot be deferred indefinitely.

**Fix:** remove dependencies and separate parsing from side effects.

### 21.6. `@Value` Does Not Recognize Custom Type Even Though `@ConfigurationProperties` Does

**Explanation:** a converter with `@ConfigurationPropertiesBinding` serves the binder; `@Value`'s conversion path is not guaranteed to match identically. Do not assume this qualifier registers the converter for every conversion service.

**Fix:** inject the `RoutingProperties` bean into services, or register the converter in the conversion service matching the other need and test application-wide effects.

### 21.7. `DataSource` or HTTP Client Is Uninitialized When Requested by Converter

**Explanation:** the converter is pulling a runtime dependency into early binding. Even if startup occasionally succeeds by chance, the lifecycle gives no stability guarantee for such a design.

**Fix:** keep the converter pure parsing; run database/network verification after config beans and services are ready.

### 21.8. Converter Logs Raw Values

**Symptom:** logs contain tokens, user info, or URLs with credentials.

**Fix:** never log sensitive inputs; state syntax requirements in errors. For production config, manage secrets with appropriate tooling, access controls, and key classification.

### 21.9. Multiple `ApplicationContext`s in Tests

**Symptom:** a converter or static holder leaks state from a previous test.

**Fix:** keep converters stateless; do not store bound config in global mutable caches. Use context-scoped bean instances or an explicit application-layer cache service after binding.

### 21.10. Editing YAML Does Not Re-Run the Converter

**Explanation:** standard Config Data loads and config beans bind at application startup. Editing an external file does not automatically trigger rebinding/refresh.

**Fix:** restart the app in the lab. If dynamic refresh is needed, design an explicit refresh lifecycle, thread safety, and object-replacement strategy; do not expect converters to watch files.

## 22. Quick Selection Matrix

| Actual Need | Approach | Reason |
| --- | --- | --- |
| Convert `500ms` to `Duration` | Use built-in conversion | Boot already supports common duration formats |
| Convert `"region/service"` to value object | `Converter<String, NodeRef>` + `@ConfigurationPropertiesBinding` | Narrow blast radius, minimal dependencies |
| Customize global service looked up by Binder | Carefully designed `conversionService` bean | Early/wide impact; requires thorough testing |
| Convert data inside a business service | Dedicated business converter/service name | Avoids interfering with infrastructure binding |
| Validate ID against a database | Post-binding service | Needs runtime resources, not parsing |
| Verify route via an API | Startup check or readiness policy | Has side effects; needs retries/timeouts |
| Convert legacy scalar format | Pure converter, or editor if legacy framework mandates it | Match the API consuming the data |
| Bind nested object from YAML | `@ConfigurationProperties` with nested record | Often requires no custom converter |
| Map `String` -> standard enum | Built-in Binder/conversion | Avoids redundant code |
| Supply default for missing property | `@DefaultValue` or base file | Never write a converter to hunt for defaults elsewhere |

### 22.1. A Useful Design Rule of Thumb

If a converter's constructor signature looks like:

```java
public ConverterImpl(Repository repository,
                     ApiClient client,
                     UserService userService) {
    ...
}
```

revisit the design. A configuration converter rarely needs such dependencies.

A more sensible signature is:

```java
public NodeRefConverter() {
}
```

or a constructor taking only **pure, immutable rules** independent of the context. Even with parameters, they must be safe to instantiate during early binding.

## 23. Checklist for Deploying Safe Custom Converters

Before introducing a custom converter into a Spring Boot service:

1. **Confirm a converter is truly needed.** Try built-in conversions and nested `@ConfigurationProperties` first.
2. **Define exact source/target types.** e.g., `String -> NodeRef`, avoiding untyped generic parsers.
3. **Keep `convert()` pure.** No database reads, network calls, or event publishing.
4. **Never inject the bound configuration bean** into the converter.
5. **Never inject services that depend on that configuration bean** indirectly.
6. **Use `@ConfigurationPropertiesBinding`** when the converter only serves the binder.
7. **Declare `static @Bean`** for the converter to curb early instantiation of config classes.
8. **Avoid the name `conversionService`** unless intentionally supplying the shared infrastructure service.
9. **If you must replace the global conversion service**, build on Boot's conversion foundation and re-test standard conversions.
10. **Do not rely on `@Lazy`** to hide circular dependencies of required converters.
11. **Write Spring-free unit tests** covering valid inputs and syntax errors.
12. **Write binding integration tests** against a real config record.
13. **Move business validation and external checks** to appropriate layers.
14. **Never log sensitive values** in converters or exceptions.
15. **Verify lifecycle across profiles, CI, and containers** since runtime sources differ from local ones.
16. **Keep converters stateless and thread-safe** as they may run across multiple bindings.
17. **Use meaningful error messages**, without depending on exact internal framework exception wording.
18. **Do not expect converters to auto-refresh data** when configuration sources change; refresh is a separate system.

## 24. Practice Exercises

### Exercise A — Classify Dependencies

Given three converters:

```java
// A
public class RegionConverter implements Converter<String, Region> {
    public Region convert(String source) {
        return Region.valueOf(source.toUpperCase(Locale.ROOT));
    }
}

// B
public class RegionConverter implements Converter<String, Region> {
    private final RegionRepository repository;
    public Region convert(String source) {
        return repository.findByCode(source).orElseThrow();
    }
}

// C
public class RegionConverter implements Converter<String, Region> {
    private final RoutingProperties properties;
    public Region convert(String source) {
        return parseWithRule(source, properties.defaultRegion());
    }
}
```

Which converter is most suitable for `@ConfigurationPropertiesBinding` during early binding? Explain the risks of the other two.

### Exercise B — Fix the Factory Method

Input:

```java
@Configuration
public class MyConverters {

    private final RoutingService routingService;

    public MyConverters(RoutingService routingService) {
        this.routingService = routingService;
    }

    @Bean
    @ConfigurationPropertiesBinding
    Converter<String, NodeRef> converter() {
        return new ClientAwareConverter(routingService);
    }
}
```

Refactor it into a `static @Bean` factory method taking no runtime dependencies and a pure converter. Explain why merely adding `static` while keeping the dependency parameter is insufficient.

### Exercise C — Choose Between Nested Object and Scalar Format

Compare:

```yaml
routing:
  primary: "ap-southeast-1/payments"
```

with:

```yaml
routing:
  primary:
    region: ap-southeast-1
    service: payments
```

Design the Java records for each approach. Which needs a custom scalar converter? Which can use nested binding directly?

### Exercise D — Global Conversion Service

A project has a bean named `conversionService` used solely for formatting UI values inside a business service. Based on this lesson, how would you consider adjusting the bean name and why?

### Exercise E — Add a New Type

Define a `FeatureCode` with `group` and `name` using scalar `"group:name"`. Write a pure `String -> FeatureCode` converter, register it with `static @Bean @ConfigurationPropertiesBinding`, and bind:

```yaml
features:
  primary: "billing:new-flow"
```

Provide at least three malformed inputs the converter should reject.

### Exercise F — Unit Test and Integration Test

Write a pure Java test proving your parser handles `"ap-southeast-1/payments"`. Then write a `@SpringBootTest` using:

```properties
routing.primary=eu-west-1/invoices
```

to verify `RoutingProperties.primary()` holds the two expected components.

Explain why the two test types verify different responsibilities.

### Exercise G — Circular Dependency

Draw the dependency chain if `RoutingProperties` uses `NodeRefConverter`, `NodeRefConverter` injects `ApiClient`, and `ApiClient` injects `RoutingProperties`. Does a valid bean creation order exist? Which dependency would you move into the service layer?

### Exercise H — Prevent Secret Exposure

Suppose the format is `"provider/key-id"` where `key-id` is sensitive data. Update error messaging and logging so the converter never prints raw input when parsing fails.

## 25. Self-Check Questions

**1.** Why can a converter serving `@ConfigurationProperties` be instantiated before several application services?

**2.** How does a bean named `conversionService` differ from a `ConversionService` given a business-specific name?

**3.** Why are `@Bean` methods annotated with `@ConfigurationPropertiesBinding` advised to be `static`?

**4.** Does adding `static` fix everything if the factory method still injects `DataSource` or `ApiClient`?

**5.** Why is a converter that needs the very `RoutingProperties` it helps bind a flawed design?

**6.** For common `Duration` and `DataSize` values, do you always have to write new converters?

**7.** Does `@ConfigurationPropertiesBinding` guarantee the converter works directly for every `@Value`?

**8.** If `"region/service"` is syntactically valid but the service does not exist in Kubernetes, should the parser call the Kubernetes API immediately?

**9.** When a converter fails due to bad format, should the application silently substitute an arbitrary default just to start?

**10.** If a `ConversionService` only processes business data, is there a reason to avoid naming it `conversionService`?

**11.** Why is a Spring-free unit test a healthy indicator for a configuration converter?

**12.** If Spring logs `not eligible for getting processed by all BeanPostProcessors`, what should you inspect?

**13.** Does `@Lazy` eliminate a dependency when the binder strictly needs the converter?

**14.** In applications with multiple `ApplicationContext`s, why shouldn't configuration state be stored in static mutable fields on a converter?

**15.** When editing YAML outside a running process, is the converter re-invoked automatically?

### Reference Answers

1. Because binding occurs while creating configuration beans, before other services finish startup.
2. The special bean name can be requested early by infrastructure; a specifically named business bean does not automatically take on that role.
3. To create the converter without instantiating the `@Configuration` class, reducing unnecessary early instantiation and related warnings.
4. No; the actual dependency still has to be resolved.
5. Because it forms a circular dependency among binder, converter, and bound bean.
6. No; Spring Boot provides built-in converters.
7. No; it is a qualifier for configuration binding, not a global registration for every conversion path.
8. No; external verification belongs in a service at the right lifecycle stage.
9. Not for required configuration; invalid data should fail early.
10. Yes; avoid triggering infrastructure conventions when the bean only serves business logic.
11. Because the converter has minimal dependencies and parsing is deterministic from input/output.
12. Check whether a bean or config class was instantiated early, whether the factory method is `static`, and what dependencies it pulls in.
13. No; the binder still has to construct the converter when needed.
14. Because static state belongs to the class/JVM, leaking across contexts/tests and risking concurrency issues.
15. Not by default; Config Data/bean binding typically runs at startup, and refresh requires its own mechanism.

## 26. Applying This in Real Projects

In a multi-environment application, architecture should preserve this data flow:

```text
application.yaml / environment / CLI
                 |
                 v
        Config Data / Environment
                 |
                 v
             Binder
                 |
      +----------+----------+
      |                     |
  Built-in conversion   Pure custom converter
      |                     |
      +----------+----------+
                 |
                 v
       @ConfigurationProperties
                 |
                 v
       Typed configuration bean
                 |
                 v
    Services / Repositories / Clients
                 |
                 v
    Startup and business operations
```

Never invert the arrow so the converter depends on a service requiring bound configuration. Converters sit at the **configuration input edge**, ready to execute while the application context is still forming.

During code reviews, ask:

```text
Can this converter run with `new` in a unit test?
Does it truly just parse/convert, or is it running business logic?
Does any configuration bean depend backward on the converter?
Do we really need to supply a bean named conversionService?
If using @ConfigurationPropertiesBinding, is the @Bean method static?
Do Spring Boot's default conversions still work?
Are malformed inputs caught and reported clearly without leaking secrets?
```

If these questions are resolved during design, you will avoid one of the hardest-to-debug startup failures: valid YAML, valid property names, yet a converter pulling unready dependencies into initialization.

## 27. References

- [Spring Boot 3.3 — Externalized Configuration](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html): *Properties Conversion* section, early-initialization requirements, `conversionService`, `@ConfigurationPropertiesBinding`, `static @Bean` recommendation.
- [Spring Boot 3.3 — Type-safe Configuration Properties](https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html#features.external-config.typesafe-configuration-properties): binder, constructor binding, validation, and standard conversions.
- [Spring Framework — Type Conversion](https://docs.spring.io/spring-framework/reference/core/validation/convert.html): `Converter`, `ConverterFactory`, `GenericConverter`, and `ConversionService`.
- [Spring Boot 3.3 API — `ConfigurationPropertiesBinding`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBinding.html): qualifier for configuration binding converters.

**Short conclusion:** Converters used for externalized configuration must be ready whenever the binder needs them—often very early. Keep converters focused purely on data conversion, register scoped converters with `@ConfigurationPropertiesBinding` and `static @Bean`, limit dependencies, avoid replacing global `conversionService` unless truly necessary, and move business checks into services after binding.