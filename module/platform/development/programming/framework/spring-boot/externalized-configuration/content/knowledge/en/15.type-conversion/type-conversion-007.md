# Creating Custom Converters with `@ConfigurationPropertiesBinding` in Spring Boot 3.3

## 1. Why Do We Need Custom Converters?

Spring Boot is designed to accept configuration from many sources: `application.properties`, `application.yaml`, external configuration files, environment variables, JVM system properties, `SPRING_APPLICATION_JSON`, and command-line arguments. When a type is annotated with `@ConfigurationProperties`, the Spring Boot Binder reads keys with the matching prefix, applies *relaxed binding* rules, and converts input values to the corresponding Java types.

Standard types like `String`, `int`, `boolean`, `Duration`, `DataSize`, `URI`, enums, and many Java types already have built-in Spring Boot conversion support. However, applications often have **domain-specific types** that the binder does not know how to construct from a string.

Suppose a task-processing system has the configuration:

```properties
app.worker.primary=ap-southeast-1:12
```

The development team wants to represent this value as a Java object:

```java
public record RegionQuota(String region, int capacity) {}
```

`ap-southeast-1:12` is a custom convention: the part before `:` is the region code, and the part after is the maximum processing capacity. The binder cannot infer a rule for splitting two components out of a single string on its own.

In Spring Boot 3.3, you can write:

```java
Converter<String, RegionQuota>
```

and register it as a bean annotated with **`@ConfigurationPropertiesBinding`**. Spring Boot can then use the converter when binding `@ConfigurationProperties` values.

**Lesson objectives:**

- Understand where a converter fits in the **configuration source → Binder → Java object** flow.
- Know when to write a converter and when to rely on built-in conversions.
- Write a `Converter<String, T>` with clear parsing rules and appropriate error messages.
- Register the converter with `@ConfigurationPropertiesBinding` in the right package and at the right initialization time.
- Understand why a `static @Bean` method is recommended when registering a converter via Java configuration.
- Use converters for scalars, `List<T>` elements, and record constructor parameters.
- Distinguish **format conversion** from **business validation**.
- Unit test converters in isolation and integration test that Spring Boot actually uses the converter during binding.
- Handle common pitfalls related to generic types, lifecycle, property names, and source precedence.

Examples use **Java 17+** and **Spring Boot 3.3.x**.

## 2. Where Does the Converter Sit in the Configuration Loading Flow?

A simplified flow:

```text
application.yaml / application.properties
          |
          | app.worker.primary=ap-southeast-1:12
          v
      Spring Environment
          |
          v
   @ConfigurationProperties Binder
          |
          +-- find keys by prefix
          +-- apply relaxed binding
          +-- identify target Java type
          +-- locate suitable converter
                        |
                        v
       Converter<String, RegionQuota>
                        |
                        v
       RegionQuota("ap-southeast-1", 12)
                        |
                        v
        WorkerProperties.primary()
                        |
                        v
     Service consumes the bound config bean
```

Key point: the converter runs **when a configuration source value needs to be converted to a target type**. It does not replace `PropertySource`, replace precedence resolution across sources, or choose profiles.

In the example, Spring Boot can read `"ap-southeast-1:12"` from YAML. The converter simply takes that string and creates `RegionQuota`.

This also means:

- If the key does not exist, the converter will not necessarily be called.
- If a command-line argument overrides the YAML string, the converter receives the **effective value** used by the binder.
- If a value already has a compatible type and the binder does not need `String -> RegionQuota`, the converter may not participate.
- A converter does not resolve value conflicts between sources; it only handles **how one value is interpreted**.

## 3. Check Built-In Converters Before Writing Your Own

Seeing a string in YAML does not automatically mean you need a converter. Spring Boot 3.3 already supports many common configuration types.

Example:

```yaml
app:
  http:
    enabled: true
    connect-timeout: 250ms
    read-timeout: 5s
    max-payload: 10MB
    endpoint: https://api.example.test
```

This binds to:

```java
@ConfigurationProperties(prefix = "app.http")
public record HttpProperties(
        boolean enabled,
        Duration connectTimeout,
        Duration readTimeout,
        DataSize maxPayload,
        URI endpoint
) {
}
```

Imports:

```java
import java.net.URI;
import java.time.Duration;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.util.unit.DataSize;
```

Spring Boot already has built-in conversions for `Duration`, `DataSize`, and many standard value types. Redefining a converter for `Duration` or `String` can alter behavior across the entire configuration, causing a small change to affect unrelated beans.

**Write your own converter when the input has a custom syntax and the target type represents a domain-specific concept.** For values easily modeled as regular child properties, consider nested `@ConfigurationProperties` instead of inventing a custom string format.

Example not needing a converter:

```yaml
app:
  worker:
    primary:
      region: ap-southeast-1
      capacity: 12
```

The binder can bind that YAML structure directly into a nested record:

```java
public record RegionQuota(String region, int capacity) {}
```

However, if there is a requirement to keep configuration compact like:

```yaml
app:
  worker:
    primary: "ap-southeast-1:12"
```

then a `Converter<String, RegionQuota>` makes sense.

## 4. Distinguishing `Converter`, `ConversionService`, and `@ConfigurationPropertiesBinding`

Three related yet distinct concepts:

| Component | Purpose | Scope |
| --- | --- | --- |
| `Converter<S, T>` | Defines how to convert from source type `S` to target type `T` | One source/target type pair |
| `ConversionService` | Service that manages and locates matching converters | Type conversion mechanism |
| `@ConfigurationPropertiesBinding` | Marks a bean used to support `@ConfigurationProperties` binding | Spring Boot's property binding converter set |

Spring Framework interface:

```java
import org.springframework.core.convert.converter.Converter;
```

With the method:

```java
T convert(S source);
```

Where `S` is the input type and `T` is the output type.

For string-based configuration:

```java
Converter<String, RegionQuota>
```

is the natural choice. When Spring Boot needs to create `RegionQuota` from a string, the converter can be found and used during binding.

The exact Spring Boot 3.3 annotation to import:

```java
import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
```

This is a **bean qualifier** serving `@ConfigurationProperties`. It is not an annotation placed on a configuration record to "enable binding", nor a mechanism that implements conversions automatically.

To bind a type from a prefix, you still need:

```java
@ConfigurationProperties(prefix = "app.worker")
```

and you must register the configuration type via `@ConfigurationPropertiesScan` or `@EnableConfigurationProperties`.

## 5. Designing a Clear Conversion Syntax

Before writing converter code, establish an input data contract.

In this lesson:

```text
<region>:<capacity>
```

Syntactically valid examples:

```text
ap-southeast-1:12
eu-west-1:6
us-east-1:4
```

Target type:

```java
public record RegionQuota(String region, int capacity) {}
```

Decisions to agree on:

1. The separator is a single `:` character.
2. `region` is the string after trimming leading/trailing whitespace.
3. `capacity` is a base-10 integer after trimming leading/trailing whitespace.
4. If the part before or after the separator is missing, or there are too many `:` characters, the converter reports a syntax error.
5. If the capacity part cannot parse as `int`, the converter reports a type conversion error.
6. The rule *capacity must be greater than 0* is a business rule validated via Bean Validation on the model.

Separating **syntax parsing** from **domain value validation** makes it clear where each error originates.

Examples:

| Value | Parses? | Meets Business Rules? |
| --- | --- | --- |
| `ap-southeast-1:12` | Yes | Yes |
| `eu-west-1:0` | Yes | No if capacity must be ≥ 1 |
| `ap-southeast-1:-3` | Yes | No if capacity must be ≥ 1 |
| `eu-west-1:abc` | No | Object cannot be constructed |
| `eu-west-1` | No | Missing `:` and capacity |
| `us:2:extra` | No | Too many parts |
| `:10` | May create object with empty region if parser permits | Fails `@NotBlank` |
| `bad region:5` | Can parse | May violate region code pattern |
| `ap-southeast-1:999999999999` | Cannot convert to `int` | Fails at conversion step |

This is an intentionally simple example. For URIs with `:` in schemes, IPv6 addresses with `:`, or values containing nested delimiters, design a different syntax instead of blindly calling `split(":")`.

## 6. Step 1 — Create the Custom Java Type

Create the file:

`src/main/java/example/configconversion/RegionQuota.java`

```java
package example.configconversion;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;

public record RegionQuota(
        @NotBlank
        @Pattern(regexp = "[a-z][a-z0-9-]*")
        String region,

        @Min(1)
        int capacity
) {
}
```

In an application with the Bean Validation dependency and validation enabled:

- `@NotBlank` prevents an empty or whitespace-only region.
- `@Pattern` enforces lowercase letters, digits, and hyphens, starting with a lowercase letter.
- `@Min(1)` requires capacity to be at least 1.

This is the **target data model**; it contains no YAML-reading logic. The record has clearly named and typed components that are easy to consume in services.

In a small application that does not need validation, you can use an unannotated record:

```java
public record RegionQuota(String region, int capacity) {}
```

Still, keep converter responsibilities and validation responsibilities separate once the model starts accumulating business rules.

### Why Not Put `String raw` Everywhere?

You could write:

```java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(String primary) {}
```

and let every service split `"ap-southeast-1:12"` on its own. However, that approach causes:

- Parsing logic to be duplicated across many places.
- Services having to know configuration separator details.
- Input typos only surfacing when a real request hits that code path.
- Format changes requiring edits across many code locations.

The `RegionQuota` type bundles "region code + capacity" into one object. The converter centralizes parsing rules in **one single place**.

## 7. Step 2 — Write `Converter<String, RegionQuota>`

Create the file:

`src/main/java/example/configconversion/RegionQuotaConverter.java`

```java
package example.configconversion;

import org.springframework.core.convert.converter.Converter;

public final class RegionQuotaConverter
        implements Converter<String, RegionQuota> {

    @Override
    public RegionQuota convert(String source) {
        String[] parts = source.trim().split(":", -1);

        if (parts.length != 2) {
            throw new IllegalArgumentException(
                    "Expected region:capacity with one ':' separator");
        }

        String region = parts[0].trim();
        String number = parts[1].trim();

        try {
            int capacity = Integer.parseInt(number);
            return new RegionQuota(region, capacity);
        } catch (NumberFormatException ex) {
            throw new IllegalArgumentException(
                    "Capacity must be a valid 32-bit integer", ex);
        }
    }
}
```

### Why Use `split(":", -1)`?

The second argument `-1` tells Java to preserve trailing empty segments.

For example:

```text
"eu-west-1:" -> ["eu-west-1", ""]
```

Then `Integer.parseInt("")` fails as expected. With default `split(":")`, trailing empty segments are discarded, making error reporting less clear.

### Why Use `trim()`?

Users might type:

```properties
app.worker.primary= ap-southeast-1 : 12
```

Within the syntax accepted by the project, the converter can strip whitespace before splitting components. That is a conversion-contract choice; a converter for digital signatures or whitespace-sensitive tokens should **not trim**.

### Why Not Echo the Entire Source String in Error Messages?

Configuration values sometimes contain internal hosts, tokens, or secrets. `region:capacity` has no secrets here, yet a more general converter might process URIs containing credentials. Prefer messages describing the **expected shape** rather than printing raw sensitive values.

### Does This Converter Need State or External Dependencies?

No. The converter only interprets a string using pure Java rules:

```text
String -> RegionQuota
```

It needs no repository, HTTP client, `Environment`, special logger, or external service call. **The fewer dependencies and side effects a converter has, the better it fits early binding.**

## 8. Step 3 — Register the Converter with `@ConfigurationPropertiesBinding`

Create the file:

`src/main/java/example/configconversion/BindingConvertersConfiguration.java`

```java
package example.configconversion;

import org.springframework.boot.context.properties.ConfigurationPropertiesBinding;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.convert.converter.Converter;

@Configuration(proxyBeanMethods = false)
public class BindingConvertersConfiguration {

    @Bean
    @ConfigurationPropertiesBinding
    static Converter<String, RegionQuota> regionQuotaConverter() {
        return new RegionQuotaConverter();
    }
}
```

This is a clear registration approach that fits Spring Boot 3.3.

Breakdown:

- `@Configuration` puts the bean definition class into the Spring context via appropriate component scanning.
- `@Bean` registers the converter object as a Spring bean.
- `@ConfigurationPropertiesBinding` marks this converter as intended for **configuration binding**.
- Making the method `static` avoids eagerly instantiating the configuration class object just to invoke the `@Bean` method.
- The return type `Converter<String, RegionQuota>` exposes the source/target type pair, helping identify the matching converter.

In this case, you do **not** need to define a bean named `conversionService` just to add one converter.

### Why Is `static` Recommended?

According to Spring Boot 3.3 documentation, beans participating in configuration conversion are requested **very early** in the application lifecycle. For `@Bean` methods annotated with `@ConfigurationPropertiesBinding`, Spring Boot recommends declaring them `static` to avoid warnings such as:

```text
Bean ... is not eligible for getting processed by all BeanPostProcessors
```

A non-static `@Bean` method normally requires an instance of the `@Configuration` class. If the binder needs the converter early, creating that instance before all `BeanPostProcessor`s are ready can trigger warnings and unpredictable effects in complex setups.

Therefore:

```java
@Bean
@ConfigurationPropertiesBinding
static Converter<String, RegionQuota> regionQuotaConverter() {
    return new RegionQuotaConverter();
}
```

is the preferred pattern.

**This does not mean every `@Bean` must be static.** The recommendation specifically applies to converters used during early configuration binding.

## 9. Can You Register Using `@Component`?

A converter annotated directly with `@Component` and `@ConfigurationPropertiesBinding` can also be scanned by Spring as a bean:

```java
@Component
@ConfigurationPropertiesBinding
public class RegionQuotaConverter
        implements Converter<String, RegionQuota> {

    @Override
    public RegionQuota convert(String source) {
        // Parse configuration data here.
        return ...;
    }
}
```

This pattern **illustrates an alternative registration option**, not a second file to create alongside the full example. If you use the `@Component` approach, put the complete converter implementation in this class and avoid unnecessarily registering another bean for the same converter.

Comparison:

| Registration Style | Advantages | Notes |
| --- | --- | --- |
| `@Bean static` + `@ConfigurationPropertiesBinding` | Explicit, controls bean name and instantiation timing | Requires a configuration class hosting the method |
| `@Component` + `@ConfigurationPropertiesBinding` | Less separate configuration code | Depends on component-scan scope; avoid heavy injection into the converter |
| Custom `ConversionService` | Can manage multiple converters in one place | More complex; requires understanding early invocation and scope |
| Unqualified `@Bean` | Unclear whether the bean participates in specialized binder | Not the pattern to pick for a dedicated configuration converter |

In this hands-on guide, we use **`@Bean static`** to state intent clearly and reduce early-initialization risk.

### Do Not Put the Annotation on the Model Instead of the Converter

Conceptually wrong:

```java
@ConfigurationPropertiesBinding
public record RegionQuota(String region, int capacity) {}
```

This annotation does not turn a record into a converter. The record is the **target type**; the converter is the **bean that takes the source value and produces the target type**.

Proper separation of roles:

```text
RegionQuota                  -> data type
RegionQuotaConverter         -> Converter<String, RegionQuota>
BindingConvertersConfiguration
    @Bean
    @ConfigurationPropertiesBinding
    static ...               -> registers converter for the Binder
WorkerProperties             -> @ConfigurationProperties model using RegionQuota
```

## 10. Step 4 — Create `@ConfigurationProperties` Using the Custom Type

Create the file:

`src/main/java/example/configconversion/WorkerProperties.java`

```java
package example.configconversion;

import java.time.Duration;
import java.util.List;

import jakarta.validation.Valid;
import jakarta.validation.constraints.AssertTrue;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @NotNull @Valid RegionQuota primary,
        @NotEmpty List<@Valid RegionQuota> fallbacks,
        @NotNull Duration timeout
) {
    @AssertTrue(message = "timeout must be greater than zero")
    public boolean isTimeoutPositive() {
        return timeout != null
                && timeout.compareTo(Duration.ZERO) > 0;
    }
}
```

Key details:

1. **`primary` is a `RegionQuota`**, yet its configuration value is a string.
2. `fallbacks` is a `List<RegionQuota>`; each element can be handled by the same converter if its source is a string.
3. `timeout` is a `Duration`; no custom converter is needed because Spring Boot already supports it.
4. `@Validated` + Bean Validation enforce the declared constraints.
5. `@Valid` on `primary` and the list elements cascades validation into `RegionQuota`.
6. `@NotEmpty` requires a non-empty fallback list in this business example.
7. `@AssertTrue` checks that timeout is positive, which is distinct from whether `"5s"` converts to `Duration`.

This is a standard record using constructor binding. Since it has a single canonical constructor, Spring Boot 3.3 does not require adding `@ConstructorBinding`.

### Using `@ConfigurationProperties` with YAML

Create:

`src/main/resources/application.yaml`

```yaml
spring:
  application:
    name: custom-config-converter-demo

app:
  worker:
    primary: "ap-southeast-1:12"
    fallbacks:
      - "eu-west-1:6"
      - "us-east-1:4"
    timeout: 5s
```

The quoted strings are **configuration values**; YAML quotes are not part of the region name. With `RegionQuotaConverter`:

```text
primary   = RegionQuota(region=ap-southeast-1, capacity=12)
fallbacks = [
  RegionQuota(region=eu-west-1, capacity=6),
  RegionQuota(region=us-east-1, capacity=4)
]
timeout   = PT5S
```

For lists, the binder processes each element via `String -> RegionQuota`, rather than joining the whole list into one string and calling the converter once.

### Equivalent in `.properties`

```properties
spring.application.name=custom-config-converter-demo

app.worker.primary=ap-southeast-1:12
app.worker.fallbacks[0]=eu-west-1:6
app.worker.fallbacks[1]=us-east-1:4
app.worker.timeout=5s
```

`WorkerProperties` needs no changes. The converter operates on **the input value and target type**, independent of whether the original source was `.properties` or YAML.

## 11. Step 5 — Register Configuration Properties and Use Them

Create the file:

`src/main/java/example/configconversion/ConverterDemoApplication.java`

```java
package example.configconversion;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@ConfigurationPropertiesScan
public class ConverterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConverterDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showConfiguration(WorkerProperties properties) {
        return args -> {
            System.out.println("primary=" + properties.primary());
            System.out.println("fallbacks=" + properties.fallbacks());
            System.out.println("timeout=" + properties.timeout());
        };
    }
}
```

`ConverterDemoApplication` resides in the same package as or a parent package of `WorkerProperties` and `BindingConvertersConfiguration`, so normal component scanning finds the converter configuration class, and `@ConfigurationPropertiesScan` discovers `WorkerProperties`.

**Distinguish the two scans:**

- `@SpringBootApplication` includes component scanning for the converter configuration bean (when within package scope).
- `@ConfigurationPropertiesScan` locates types annotated with `@ConfigurationProperties`.

A `@ConfigurationProperties` type using constructor binding **does not need** `@Component`. Adding `@Component` can cause Spring to instantiate it as a regular bean instead of using binder constructor binding.

### Maven Dependencies

Suppose a Maven project with Spring Boot dependency management; you need `spring-boot-starter` and, since the example uses `@Validated` with Jakarta Bean Validation, add the validation starter:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
</dependencies>
```

In a Spring Boot 3.3 project using the Maven parent or Gradle plugin, corresponding Spring dependency versions are managed by Boot. Do not mix an arbitrary Spring Framework version with your Boot version.

## 12. Running and Observing the Application

In a project with the Maven wrapper:

```bash
./mvnw spring-boot:run
```

Or package it:

```bash
./mvnw package
java -jar target/actual-app-name.jar
```

`actual-app-name.jar` is an illustrative placeholder; replace it with the JAR produced by your build.

Expected main output printed by `ApplicationRunner`:

```text
primary=RegionQuota[region=ap-southeast-1, capacity=12]
fallbacks=[RegionQuota[region=eu-west-1, capacity=6], RegionQuota[region=us-east-1, capacity=4]]
timeout=PT5S
```

The `RegionQuota[...]` format is the default `toString()` generated for a Java `record`. `PT5S` is the string form of a five-second `Duration`.

If these values print as expected, the application has:

1. Located the `app.worker.*` keys.
2. Bound `primary` to the custom `RegionQuota` type.
3. Applied the converter to list elements.
4. Used the built-in converter for `Duration`.
5. Constructed `WorkerProperties`.
6. Executed validation for the declared constraints.

This does not mean `"ap-southeast-1"` is a valid region for a real cloud provider. If using real provider region names, enforce the appropriate policy or reference list.

## 13. Testing Configuration Override from Command-Line Arguments

Command-line arguments normally have higher precedence than `application.yaml`:

```bash
java -jar target/actual-app-name.jar \
  --app.worker.primary=eu-central-1:8
```

With no higher-precedence source and a properly registered converter, `primary` receives:

```text
RegionQuota[region=eu-central-1, capacity=8]
```

The converter does not need to know whether the value came from the command line or YAML. That is the job of `PropertySource` and the binder.

In PowerShell, the corresponding example is:

```powershell
java -jar .\target\actual-app-name.jar `
  '--app.worker.primary=eu-central-1:8'
```

The trailing backtick is PowerShell's line-continuation syntax. You can avoid shell differences by putting it on one line:

```powershell
java -jar .\target\actual-app-name.jar '--app.worker.primary=eu-central-1:8'
```

When passing values containing `&`, spaces, `$`, or shell control characters, quote carefully so Java receives **a single argument**. That is a shell concern, separate from the converter mechanism.

## 14. Testing Invalid Values: Separating Conversion Failures from Validation Failures

### 14.1. Missing Separator

```properties
app.worker.primary=ap-southeast-1
```

The converter receives one element instead of two and throws:

```text
Expected region:capacity with one ':' separator
```

The application can fail to construct `WorkerProperties` because the string cannot be converted to `RegionQuota`.

That is a **syntax conversion error**, not a Bean Validation error.

### 14.2. Non-Numeric Capacity

```properties
app.worker.primary=ap-southeast-1:many
```

`Integer.parseInt("many")` throws `NumberFormatException`, which the converter wraps with the message:

```text
Capacity must be a valid 32-bit integer
```

The binder may display a chain of causes inside binding/conversion exceptions. Do not rely on one exact outer exception class across every context; inspect the root cause and failing property name.

### 14.3. Capacity Equal to 0

```properties
app.worker.primary=ap-southeast-1:0
```

The converter **can construct**:

```text
RegionQuota[region=ap-southeast-1, capacity=0]
```

However, because the model has:

```java
@Min(1) int capacity
```

and validation is enabled, the configuration is rejected due to a **business rule**, not because the parser failed to understand `0`.

### 14.4. Region Violating the Pattern

```properties
app.worker.primary=Bad Region:12
```

The converter can split the string into `"Bad Region"` and `12`. However, `@Pattern(regexp = "[a-z][a-z0-9-]*")` disallows spaces and uppercase letters, so validation rejects it.

### 14.5. Malformed Timeout

```properties
app.worker.timeout=five-seconds
```

`RegionQuotaConverter` is not responsible for this key. Spring Boot tries its **standard `Duration` conversion rules**, and fails because the string is not a supported duration format.

This illustrates two converters with distinct scopes:

```text
String -> RegionQuota  : application's custom converter
String -> Duration     : Spring Boot built-in conversion
```

## 15. `@ConfigurationPropertiesBinding` Is a Qualifier, Not a Prefix

There are several common misconceptions.

### Misconception A — The Annotation Takes a Prefix

Wrong:

```java
@ConfigurationPropertiesBinding(prefix = "app.worker")
```

No such attribute exists. This annotation qualifies a converter bean; it does not declare a property group.

The prefix lives on the model:

```java
@ConfigurationProperties(prefix = "app.worker")
```

### Misconception B — The Converter Runs for Every Property

`Converter<String, RegionQuota>` serves places that need to convert **a string to `RegionQuota`** within the appropriate binding context. It does not run when the binder needs `String -> Duration` or `String -> int`.

Conversely, if multiple configuration beans in the same application have fields of type `RegionQuota`, the converter can be used across **different prefixes**. It is not restricted to `"app.worker.primary"`.

### Misconception C — The Qualifier Exposes the Converter to Every Bean

`@ConfigurationPropertiesBinding` helps Spring Boot recognize a bean intended for configuration properties binding. Do not infer that every API using `ApplicationConversionService`, every `@Value`, or every form formatter in Spring MVC will use this converter in the exact same way.

If another part of the application needs the same conversion, register the converter in that layer's `ConversionService` or call a shared parsing helper. Distinguish **configuration binding conversion** from data conversion at other layers.

### Misconception D — Just Calling `new RegionQuotaConverter()` Is Enough

Without registering a bean or adding the converter to the `ConversionService` used by the binder, Spring Boot has no way to discover a Java object you merely instantiated in some method.

You must declare a qualified bean as shown:

```java
@Bean
@ConfigurationPropertiesBinding
static Converter<String, RegionQuota> regionQuotaConverter() {
    return new RegionQuotaConverter();
}
```

## 16. Early Initialization Lifecycle: Avoid Complex Dependencies

This is one of the most important considerations when building converters for `@ConfigurationProperties`.

Per the Spring Boot 3.3 Reference, beans used for configuration type conversion are requested **very early** in the application lifecycle. Therefore, do not design a converter that depends on beans that may not yet be fully initialized.

Example to avoid:

```java
public class RegionQuotaConverter
        implements Converter<String, RegionQuota> {

    private final DatabaseRegionRepository repository;

    public RegionQuotaConverter(DatabaseRegionRepository repository) {
        this.repository = repository;
    }

    // convert() queries the database to decide whether to accept the region...
}
```

Even if DI appears to work in some scenarios, this design carries several problems:

- The repository may not be ready when the converter is needed.
- It can create a circular dependency: configuration needs converter, converter needs bean, bean needs configuration.
- Binding can trigger DB queries, slowing startup and making startup fail on transient network errors.
- Temporary outages of external services become configuration conversion failures.
- Unit testing the converter becomes harder.

A better design:

```text
Converter:
    string syntax -> typed object

Bean Validation:
    value ranges, field relationships, static constraints

Service / readiness:
    live existence checks, database, network, credentials, resources
```

If you need to validate against an up-to-date region list from an external service, design **a separate validation step** instead of turning the converter into a hidden network caller.

## 17. Do Not Create a `conversionService` Bean When You Only Need One Converter

Spring Boot also allows providing a bean named:

```text
conversionService
```

to customize configuration type conversion. However, when you define a global `ConversionService`, you must understand that it can be requested very early and must retain all standard converters that your configuration relies on.

For instance, creating an empty `ConversionService` or one missing standard formatters can break `Duration`, `DataSize`, or enum properties that worked previously.

For a single custom type pair:

```text
String -> RegionQuota
```

the simpler approach is creating **a converter annotated with `@ConfigurationPropertiesBinding`**, letting the binding system add it to the appropriate conversion capabilities.

If the application genuinely needs a custom `ConversionService` for broader purposes beyond configuration properties, keep the bean name and scope distinct so you do not accidentally alter binding behavior across the entire application.

### When to Consider More General Converters?

Spring Framework also offers:

- `ConverterFactory<S, R>` for a family of related target types.
- `GenericConverter` for complex conversions or multiple type pairs.
- `ConditionalGenericConverter` when conversion eligibility depends on type metadata.

These APIs fit advanced requirements. For a clean configuration format, **`Converter<String, RegionQuota>` is easier to read and maintain**.

## 18. A Converter Is Not Validation

The converter is responsible for:

```text
"ap-southeast-1:12"
          |
          v
RegionQuota("ap-southeast-1", 12)
```

Validation is responsible for:

```text
RegionQuota("ap-southeast-1", 12)
          |
          v
is region blank?
does region match pattern?
is capacity >= 1?
```

Two distinct kinds of errors:

| Case | Conversion | Validation |
| --- | --- | --- |
| `eu-west-1:abc` | Cannot construct object | No valid object exists to validate |
| `eu-west-1:0` | Can succeed | Violates `@Min(1)` |
| `Bad Region:12` | Can succeed | Violates `@Pattern` |
| `us-east-1:5` | Succeeds | Satisfies sample constraints |
| `us-east-1:9999999999999` | `Integer.parseInt` fails | Never reaches int range validation |

For formats that must uphold invariants immediately upon construction, the domain type's constructor can enforce its own invariants. Still, when explaining configuration errors, distinguish parser errors, model invariant errors, and Bean Validation errors rather than lumping them into generic messages.

### Do Not Assume `@Validated` Automatically Checks Every Nested Object

In the example, `WorkerProperties.primary` is annotated with:

```java
@NotNull @Valid RegionQuota primary
```

and the list with:

```java
@NotEmpty List<@Valid RegionQuota> fallbacks
```

`@Valid` tells Bean Validation to descend into `RegionQuota`'s constraints. Forgetting cascade validation can result in configuration binding while nested object constraints are never evaluated as expected.

Modeling a dedicated type pays off when its constraints and region semantics are reused in multiple places.

## 19. Using a Converter with `@DefaultValue`

Constructor-bound configuration properties can declare parameter defaults:

```java
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(
        @DefaultValue("ap-southeast-1:4") RegionQuota primary,
        @DefaultValue("5s") Duration timeout
) {
}
```

When `app.worker.primary` is absent, Spring Boot can apply the `@DefaultValue` string and **convert it to the target `RegionQuota` type** using the appropriate conversion mechanism. The default value must also follow the syntax accepted by the converter.

If you write:

```java
@DefaultValue("invalid-default") RegionQuota primary
```

then even when the user configures nothing, the default can cause a binding failure because the converter does not receive `region:capacity`.

Do not use defaults simply to hide missing required configuration in production. If a cluster must supply `primary` explicitly, express that requirement via configuration and validation rather than defaulting to an unintended region.

**Not every string needs a custom converter.** In the example, `@DefaultValue("5s")` for `Duration` uses Spring Boot's built-in converter.

## 20. Collections and Nested Objects: Converters Run at the Element Level

A YAML file:

```yaml
app:
  worker:
    groups:
      primary: "ap-southeast-1:12"
      backup: "eu-west-1:6"
    fallbacks:
      - "us-east-1:4"
      - "eu-west-2:5"
```

A matching configuration model:

```java
@ConfigurationProperties(prefix = "app.worker")
public record GroupedWorkerProperties(
        Map<String, RegionQuota> groups,
        List<RegionQuota> fallbacks
) {
}
```

The binder can combine `Map` / `List` structural binding with the registered converter to create each `RegionQuota` from its string value.

**Do not confuse the two levels:**

1. The binder knows how to locate the keys `primary`, `backup`, and list elements.
2. The converter knows how to turn **one scalar string** into **one `RegionQuota`**.

The converter does not need to traverse the entire YAML tree or inspect `PropertySource`s. Converting a single JSON string into a whole `List<RegionQuota>` is a **different** formatting requirement, not something `Converter<String, RegionQuota>` handles by itself.

### Note on Precedence Across Multiple Sources

If `application.yaml` defines two fallbacks while profile `dev` defines a list with one fallback, the binder generally **replaces the list** from the lower-precedence source with the list from the higher-precedence source, rather than merging all elements. The converter still processes elements of the final bound list.

For `Map`, combination rules can differ: child keys from multiple sources may contribute to the map according to precedence rules. That is a **collection binding rule**, not a change in the converter.

## 21. Property Names and Relaxed Binding Still Work Normally

Declaration:

```java
@ConfigurationProperties(prefix = "app.worker")
public record WorkerProperties(RegionQuota primary) {}
```

Canonical key:

```properties
app.worker.primary=ap-southeast-1:12
```

Corresponding environment variable on Unix:

```bash
export APP_WORKER_PRIMARY='eu-west-1:6'
java -jar app.jar
```

In PowerShell:

```powershell
$env:APP_WORKER_PRIMARY = 'eu-west-1:6'
java -jar .\app.jar
```

Spring Boot selects the effective value for `app.worker.primary` across configuration sources by precedence, then invokes the converter to create `RegionQuota`.

If a property contains a hyphen:

```text
app.worker.primary-region
```

the environment variable name following relaxed binding rules is:

```text
APP_WORKER_PRIMARYREGION
```

Replace dots with `_`, remove hyphens, uppercase letters. **The converter does not handle key naming**; the binder handles that.

A common mistake is writing a correct converter while misnaming the environment variable, leading developers to think the converter was never called. Before modifying converter code, verify that the final property was actually matched.

## 22. Writing Unit Tests for the Converter

Because `RegionQuotaConverter` has no dependencies, unit tests do not need to start a Spring context. Using JUnit 5:

`src/test/java/example/configconversion/RegionQuotaConverterTest.java`

```java
package example.configconversion;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class RegionQuotaConverterTest {

    private final RegionQuotaConverter converter =
            new RegionQuotaConverter();

    @Test
    void convertsNormalValue() {
        RegionQuota result =
                converter.convert("ap-southeast-1:12");

        assertEquals("ap-southeast-1", result.region());
        assertEquals(12, result.capacity());
    }

    @Test
    void allowsSurroundingWhitespace() {
        RegionQuota result =
                converter.convert("  eu-west-1 : 6  ");

        assertEquals(new RegionQuota("eu-west-1", 6), result);
    }

    @Test
    void rejectsMissingSeparator() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("eu-west-1"));
    }

    @Test
    void rejectsNonNumericCapacity() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("eu-west-1:many"));
    }

    @Test
    void rejectsMoreThanOneSeparator() {
        assertThrows(
                IllegalArgumentException.class,
                () -> converter.convert("us-east-1:2:extra"));
    }
}
```

These tests verify **pure Java parsing**. They do not prove that Spring Boot registered the converter via `@ConfigurationPropertiesBinding`.

If you want to test that `capacity=0` is rejected by Bean Validation, that is **a different kind of test**: you must invoke Jakarta Validator on the object or test binding inside a Spring context with validation enabled. Do not expect converter unit tests to reject every constraint-violating value when the converter intentionally checks only syntax.

## 23. Integration Testing: Does Spring Boot Actually Use the Converter?

To prove a converter is wired into configuration binding, write a test that starts a Spring context with configuration sources.

A straightforward option is a Spring Boot test:

`src/test/java/example/configconversion/ConverterBindingIntegrationTest.java`

```java
package example.configconversion;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest(properties = {
        "app.worker.primary=eu-central-1:9",
        "app.worker.fallbacks[0]=us-east-1:3",
        "app.worker.timeout=2s"
})
class ConverterBindingIntegrationTest {

    @Autowired
    private WorkerProperties properties;

    @Test
    void usesRegisteredConverterDuringBinding() {
        assertEquals(
                new RegionQuota("eu-central-1", 9),
                properties.primary());

        assertEquals(
                new RegionQuota("us-east-1", 3),
                properties.fallbacks().get(0));

        assertEquals(1, properties.fallbacks().size());
    }
}
```

To use `@SpringBootTest`, the project needs `spring-boot-starter-test` in test scope:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

This test relies on the demo application and component-scanning scope from earlier sections, including `BindingConvertersConfiguration`, `WorkerProperties`, and `ConverterDemoApplication`.

It verifies:

1. The Spring Boot context starts up.
2. `WorkerProperties` is registered.
3. The converter bean is found.
4. The binder converts strings for `primary` and `fallbacks` elements into `RegionQuota`.
5. The resulting values match expectations.

If converter unit tests pass while this test fails, the cause likely lies in **bean registration, package scanning, qualifiers, or Spring configuration**, rather than the `split` algorithm inside the converter.

### Testing Invalid Values in Integration

You can add a test launching a context with:

```properties
app.worker.primary=eu-west-1:abc
```

and assert that context startup fails using an appropriate test tool, such as `ApplicationContextRunner` with the proper bean and validation configuration registered.

Note that a `@SpringBootTest` with intentionally invalid configuration can fail the entire test context before the `@Test` method runs. If you want to assert and inspect startup failures inside a test, use a context runner that can observe `getStartupFailure()` rather than expecting a standard JUnit method to run.

## 24. Common Mistakes When Registering Custom Converters

| Symptom | Possible Cause | How to Fix |
| --- | --- | --- |
| Binder cannot convert `String` to `RegionQuota` | Converter is not registered | Check `@Bean`, qualifier, and scan scope |
| Importing `ConfigurationPropertiesBinding` fails | Wrong package imported | Use `org.springframework.boot.context.properties.ConfigurationPropertiesBinding` |
| Wrote `implements Converter` class with no effect | Class is not a configuration bean | Use `@Bean @ConfigurationPropertiesBinding` or proper registration |
| Warning "not eligible for getting processed..." | Converter bean requested too early, non-static `@Bean`, or early-created dependency | Prefer `static @Bean` and limit dependencies |
| Configuration has value yet converter does not run | Different target type, higher-precedence source, or converted another way | Check `@ConfigurationProperties` field and final value |
| Converter breaks multiple modules | Registered for overly broad type pair such as `String -> String` | Use a dedicated domain type to narrow impact |
| `capacity=0` still converts | Converter only parses numbers | Use Bean Validation for the `>= 1` rule |
| `host:port` string with multiple `:` fails | Delimiter format does not handle IPv6/URIs | Use an explicit format or standard types instead of simple `split` |
| Edited YAML yet bean keeps old value | Higher-precedence source, stale JAR, or process not restarted | Check runtime environment and `PropertySource`s |
| `@Value` does not use converter as expected | Different lookup/injection path from Binder | Check API in use and register conversion in the right scope |
| `@ConfigurationProperties` bean is not created | Missing scan or enable | Use `@ConfigurationPropertiesScan` / `@EnableConfigurationProperties` |
| Converter calls repository and breaks startup | Dependency not ready or circular startup | Keep converter pure parsing; move external checks to another step |
| List not merged across profiles | List binding replaces rather than appends | Declare full list in the higher-precedence source |
| Missing key produces `null` without error | No constraint/mandatory policy | Add `@NotNull`, default, or appropriate checks |

### Do Not Fix Errors by Ignoring Invalid Fields

`@ConfigurationProperties` has options like `ignoreInvalidFields`, yet ignoring malformed domain strings can leave the application running without essential information. If `RegionQuota` is required, it is usually better to let the binding error surface early and explain the proper format.

Do not invent a fake value like `new RegionQuota("unknown", 0)` just to avoid throwing an exception if business rules forbid it; that turns an input error into a hard-to-diagnose runtime state.

## 25. When Should You Not Use `Converter<String, T>`?

There are situations where a custom converter is not the best option.

### 25.1. Data Is Already Structured

Instead of a string:

```yaml
app:
  worker:
    primary: "ap-southeast-1:12"
```

you can use:

```yaml
app:
  worker:
    primary:
      region: ap-southeast-1
      capacity: 12
```

and model:

```java
public record WorkerProperties(RegionQuota primary) {}
```

with the appropriate prefix on `WorkerProperties`. The binder can bind child fields without parsing a combined string. This form can also be clearer when setting individual keys via environment variables.

### 25.2. Data Types Already Supported by Spring Boot Converters

Example:

```properties
app.worker.timeout=5s
app.worker.max-batch-size=10MB
```

Use `Duration` and `DataSize` with standard conversion; do not invent custom syntax unless clearly needed.

### 25.3. Data Dependent on External Services

If you want to check whether a region exists in a cloud provider's live catalog, a converter is not the right place for remote API calls. Accept region names via string syntax rules and perform business verification in an appropriate layer.

### 25.4. Parsing Large, Deeply Nested Structures

If values are nested JSON, long lists, or varied element types, consider structured YAML/properties, fitting Java types, and the binder. Cramming everything into one scalar and writing a huge converter makes the schema hard to understand.

### 25.5. Conversions Needed Across Multiple Application Layers

If the same conversion is needed for MVC request parameters, messaging, and configuration, extract a **pure parsing function** out of the converter class. Each layer registers its own conversion adapter instead of assuming the configuration qualifier will be picked up automatically by every other mechanism.

## 26. Improving Converter Design for Larger Projects

A well-designed converter generally has these traits:

- **Deterministic:** identical input yields identical output or the same error type.
- **Side-effect free:** no file writes, network calls, or application state mutations.
- **Thread-safe:** holds no unnecessary shared mutable state.
- **Independent of time or environment** unless explicitly designed as a requirement.
- **Informative errors:** describe the expected input shape without leaking secrets.
- **Separate parser and validation:** format recognition differs from business policy enforcement.
- **Consistent:** explicitly defines whitespace, casing, encoding, and delimiter rules.
- **Well-tested:** valid inputs, malformed inputs, missing segments, huge numbers, negatives, empty values.
- **Specific target type:** avoid overly broad converters that cause unintended side effects.
- **Portable across YAML/properties/env:** do not couple converter logic to one specific source format.

In larger codebases, you can extract a pure parser:

```java
public final class RegionQuotaParser {

    private RegionQuotaParser() {
    }

    public static RegionQuota parse(String raw) {
        // Perform syntax checks and conversion here.
        return ...;
    }
}
```

Then `RegionQuotaConverter.convert(...)` simply calls `RegionQuotaParser.parse(source)`. This organizational pattern is **illustrative**; do not create a second parser class if the existing converter is already small and readable.

Separating the parser lets CLI tools or other data-ingestion pipelines reuse it without depending directly on a Spring context.

## 27. Another Domain Example: Parsing Brand Color Codes

Suppose an application accepts:

```properties
app.ui.accent-color=#1A73E8
```

You have a custom type:

```java
public record RgbColor(int red, int green, int blue) {}
```

A converter can accept a `#RRGGBB` `String`, verify six hex characters, and construct the `red`, `green`, and `blue` components.

Conceptual example:

```java
public final class RgbColorConverter
        implements Converter<String, RgbColor> {

    @Override
    public RgbColor convert(String source) {
        if (!source.matches("#[0-9A-Fa-f]{6}")) {
            throw new IllegalArgumentException(
                    "Expected color in #RRGGBB format");
        }

        int value = Integer.parseInt(source.substring(1), 16);
        return new RgbColor(
                (value >> 16) & 0xff,
                (value >> 8) & 0xff,
                value & 0xff);
    }
}
```

This is a fitting use case because `"#{hex}"` has a **clear scalar syntax**, the target type represents a **meaningful object**, and pure parsing requires no external services.

Registration:

```java
@Bean
@ConfigurationPropertiesBinding
static Converter<String, RgbColor> rgbColorConverter() {
    return new RgbColorConverter();
}
```

When `RgbColor` is used in `@ConfigurationProperties`, Spring Boot can bind `#1A73E8` into a typed value.

Note that when typing directly in a shell, `#` can denote a comment in certain contexts; wrap the value in shell quotes. Terminal quoting happens **before** the converter and does not change color-parsing logic.

## 28. Self-Check Exercises

### Exercise 1 — Know When a Converter Is Needed

Given three keys:

```properties
app.timeout=5s
app.max-size=10MB
app.region-quota=ap-southeast-1:12
```

Target types are `Duration`, `DataSize`, and `RegionQuota`.

**Question:** Which value likely needs a custom converter?

**Answer:** `app.region-quota`. `Duration` and `DataSize` already have standard conversion support in Spring Boot 3.3; `RegionQuota` is an application-defined domain type with custom syntax.

### Exercise 2 — Correct Annotation Import

Two packages:

```java
org.springframework.boot.context.properties.ConfigurationPropertiesBinding
```

```java
org.springframework.boot.context.properties.bind.ConfigurationPropertiesBinding
```

**Question:** Which import is right?

**Answer:** the first package, under `org.springframework.boot.context.properties`.

### Exercise 3 — Configuration with Multiple Constructors

A `WorkerProperties` record uses `RegionQuota primary`. Must the converter be annotated with `@ConstructorBinding`?

**Answer:** No. `@ConstructorBinding` relates to how the binder chooses a constructor for a configuration model when needed, whereas a converter is registered as a bean via `@ConfigurationPropertiesBinding`.

### Exercise 4 — static `@Bean`

You write:

```java
@Bean
@ConfigurationPropertiesBinding
Converter<String, RegionQuota> converter() {
    return new RegionQuotaConverter();
}
```

**Question:** Why does Spring Boot recommend adding `static`?

**Answer:** binding converters can be requested very early. A `static` method avoids eagerly instantiating the configuration class and prevents `BeanPostProcessor` warnings as noted in Spring Boot documentation.

### Exercise 5 — Distinguishing Parsing and Validation

```properties
app.worker.primary=eu-west-1:0
```

The converter creates `RegionQuota("eu-west-1", 0)`, and the model uses `@Min(1)`.

**Question:** Does conversion succeed, and does validation pass?

**Answer:** syntax and type conversion can succeed; validation fails because capacity is 0.

### Exercise 6 — Key from Another Source

YAML declares `primary=ap-southeast-1:12`, while the launch command passes:

```bash
java -jar app.jar --app.worker.primary=us-east-1:4
```

**Question:** Which string does the converter receive under normal settings?

**Answer:** the string from the higher-precedence source (`us-east-1:4`) selected by the binder; the converter does not select sources.

### Exercise 7 — Combining with Lists

YAML:

```yaml
app:
  worker:
    fallbacks:
      - "eu-west-1:6"
      - "us-east-1:4"
```

Java type:

```java
List<RegionQuota> fallbacks
```

**Question:** What input does the converter receive?

**Answer:** the converter can be invoked for **each scalar element** to construct each `RegionQuota`; the binder handles building the list structure.

### Exercise 8 — `NumberFormatException` Error

```properties
app.worker.primary=eu-west-1:large
```

**Question:** How should this be handled?

**Answer:** report the invalid number format clearly, preserving the exception cause when helpful; do not silently return a default capacity to mask configuration mistakes.

### Exercise 9 — External Dependencies

A converter needs to fetch the default region from a database. Should you inject a repository into the binding converter and query the DB inside `convert()`?

**Answer:** avoid doing so whenever possible, since converters are requested very early during startup and can cause circular dependencies or unstable initialization. Choose pure parsing rules and perform business verification in an appropriate layer.

### Exercise 10 — Testing

A unit test `new RegionQuotaConverter().convert(...)` passes. Is that enough to prove Spring Boot will bind `WorkerProperties.primary`?

**Answer:** Not yet. Unit tests only verify the parsing algorithm. You need a Spring context test proving that the qualified converter bean is registered and used by the binder.

## 29. Real-Project Implementation Checklist

Before adding a configuration converter, ask yourself:

- [ ] Is the target type truly a custom domain type, or is it already supported by Spring Boot?
- [ ] Could configuration be modeled cleanly with nested fields instead of a custom scalar?
- [ ] Is the input syntax (delimiter, whitespace, casing, range) documented?
- [ ] Does `Converter<S,T>` have concrete, appropriate generic type parameters?
- [ ] Are parsing errors clear without exposing secrets?
- [ ] Is the converter pure data transformation, free of network, database, and mutable state?
- [ ] Is the converter registered as a bean for configuration properties?
- [ ] When using `@Bean`, did you apply `@ConfigurationPropertiesBinding` and consider `static`?
- [ ] Does `@ConfigurationProperties` have the right prefix and is it scanned/enabled?
- [ ] Does the model validate business rules separately from conversion?
- [ ] Do nested objects and list elements have proper cascade validation?
- [ ] Do unit tests cover valid values, malformed syntax, out-of-range numbers, and empty parts?
- [ ] Does an integration test prove Spring Boot uses the converter during binding?
- [ ] Have environment variable names and source precedence been verified?
- [ ] Are stored secrets protected from being logged if the converter fails?

This checklist helps keep the converter as a **focused conversion unit** rather than turning it into a dumping ground for unrelated startup logic.

## 30. Summary

`@ConfigurationPropertiesBinding` is an essential tool when Spring Boot Binder must convert configuration values into **application-defined Java types**.

Standard workflow:

```text
1. Define domain type T
          |
          v
2. Write Converter<String, T>
          |
          v
3. Register the bean:
   @Bean
   @ConfigurationPropertiesBinding
   static Converter<String, T> ...
          |
          v
4. Declare T in @ConfigurationProperties
          |
          v
5. Register configuration properties via scan/enable
          |
          v
6. Binder applies the converter when needed
          |
          v
7. Bean Validation checks business rules
          |
          v
8. Service consumes typed configuration
```

Core takeaways:

1. **Do not write converters when Spring Boot already supports the type**, such as `Duration` or `DataSize`.
2. **`Converter<String, T>` handles the format of a single value**, not replacing `PropertySource` or the binder.
3. **`@ConfigurationPropertiesBinding` qualifies a converter bean for configuration properties binding**; it does not declare a prefix.
4. **Use `static @Bean` when registering converters via Java configuration** to reduce early-initialization lifecycle risks.
5. **Converters should be simple with minimal dependencies**; avoid network/DB calls during parsing.
6. **Separate type conversion from business validation**; `"region:0"` can parse cleanly yet still be invalid.
7. **Test both the parser and the actual binding path** to confirm both algorithm correctness and Spring Boot integration.

Once you understand the boundary between Converter, Binder, and Validation, you can extend Spring Boot 3.3's configuration capabilities while keeping Java code typed, testable, decoupled, and reliable in production.

## References

- Spring Boot 3.3 Reference — Externalized Configuration, section **Properties Conversion**: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Boot 3.3 API — `ConfigurationPropertiesBinding`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/context/properties/ConfigurationPropertiesBinding.html
- Spring Boot 3.3 Reference — `@ConfigurationProperties` Validation and Type-safe Configuration Properties: https://docs.spring.io/spring-boot/3.3/reference/features/external-config.html
- Spring Framework Reference — Type Conversion (`Converter`, `ConversionService`): https://docs.spring.io/spring-framework/reference/core/validation/convert.html
- Spring Boot 3.3 Reference — Testing (`@SpringBootTest`, `ApplicationContextRunner`): https://docs.spring.io/spring-boot/3.3/reference/testing/index.html