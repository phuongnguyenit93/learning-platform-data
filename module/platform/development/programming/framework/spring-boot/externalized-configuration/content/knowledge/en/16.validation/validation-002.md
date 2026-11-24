# Preparing Bean Validation and `jakarta.validation` Annotations

## 1. Why Does `@ConfigurationProperties` Need Validation?

Spring Boot supports reading configuration from many sources: `application.yml`, `application.properties`, environment variables, command-line arguments, profile-specific config, and other Config Data sources. With `@ConfigurationProperties`, the Binder converts data from these sources into typed Java objects.

For example, a notification service needs:

```yaml
notification:
  enabled: true
  sender-name: Billing Team
  sender-email: billing@example.invalid
  api-url: https://notify.example.invalid/api
  max-attempts: 3
  connect-timeout: 2s
```

Type conversion solves several issues:

- `"3"` can become `int 3`.
- `"2s"` can become `Duration.ofSeconds(2)`.
- A URL can be converted to `URI`.
- `"true"` can be bound to `boolean true`.

However, **being the right type does not mean being valid**:

```yaml
notification:
  enabled: true
  sender-name: "   "
  sender-email: not-an-email
  api-url: http://localhost:9999
  max-attempts: -5
  connect-timeout: -2s
```

Many values in the second file can still *convert to Java types*: `-5` is a valid `int`, `-2s` is a valid `Duration`, and a string of spaces is still a `String`. Yet they can violate the operational contract.

**Bean Validation** is a mechanism for declaring and checking constraints such as "must not be blank," "must be greater than or equal to 1," or "must be formatted as an email." Combining Bean Validation with `@ConfigurationProperties` lets an application **detect invalid configuration at startup** before services receive unsuitable values.

```text
YAML / ENV / CLI / Config Data
               |
               v
       Spring Environment
               |
               v
     @ConfigurationProperties Binder
               |
       +-------+-------+
       |               |
  Type converted    Conversion failed
       |               |
       v               v
  Java Object      Binding error
       |
       v
  Bean Validation
       |
  +----+----+
  |         |
Valid    Invalid
  |         |
  v         v
Config    Startup/binding
bean used validation failure
```

The goal of this lesson is to set up the dependency, import the right `jakarta.validation` API, add common constraint annotations, enable validation during binding, and observe failures verifiably.

## 2. Three Concepts Not to Confuse

Before writing code, separate three layers of responsibility.

### 2.1. Binding

`@ConfigurationProperties(prefix = "notification")` specifies which group of keys binds to the object. The Binder matches property names using relaxed binding and converts values to target types.

For example:

```yaml
notification:
  max-attempts: 3
```

can bind to the Java component `int maxAttempts`.

### 2.2. Validation

An annotation like `@Min(1)` requires `maxAttempts` to be 1 or greater. `int -5` has the right type, yet fails the constraint.

```java
@Min(1)
int maxAttempts
```

If validation is actually enabled, an object with `maxAttempts=-5` will be rejected while initializing the configuration bean.

### 2.3. Business Rules

Some requirements cannot be expressed completely with simple single-field constraints—for example, "`apiUrl` is required only when `enabled=true`," "the URL must belong to an approved endpoint list," or "timeout must be shorter than the workflow deadline."

Such requirements need object-level constraints, custom validators, or appropriate startup checks. Do not assume that adding `@NotNull` or `@Email` alone enforces every business rule.

Comparison table:

| Input | Binding | Validation | Outcome |
| --- | --- | --- | --- |
| `max-attempts: 3` | Bound as `int 3` | Passes `@Min(1)` | Valid |
| `max-attempts: abc` | Cannot convert to `int` | May not reach validation | Type conversion error |
| `max-attempts: -2` | Bound as `int -2` | Fails `@Min(1)` | Validation error |
| Missing `sender-name` | May be `null` | Fails `@NotBlank` | Missing required value |
| `sender-name: "  "` | Bound as `String` | Fails `@NotBlank` | Blank content value |
| `sender-email: invalid` | Bound as `String` | Fails `@Email` | Invalid format |

## 3. What Is Jakarta Validation?

In modern Spring Boot versions such as Spring Boot 3.x, the Bean Validation API uses the **`jakarta.validation`** package.

Examples of valid imports:

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
```

In Spring Boot 2 tutorials or older Java EE projects, you may see:

```java
import javax.validation.constraints.NotNull;
```

That is the older namespace. **Do not copy `javax.validation.*` imports verbatim from old tutorials into a Spring Boot 3 project using the Jakarta API.** The two namespaces define distinct annotation types; using the wrong package or mixing dependency versions can cause compilation errors or prevent validation from running as expected.

Jakarta Validation has two parts to distinguish:

- **API/contract**: `jakarta.validation.Valid`, `jakarta.validation.constraints.*`, `Validator`, `ConstraintViolation`, etc.
- **Provider/implementation**: the library that evaluates constraints at runtime, commonly Hibernate Validator in Spring Boot projects.

Having annotations in source code does not guarantee a validation provider exists at runtime. The application needs compatible dependencies so the provider executes the checks.

## 4. Installing the `spring-boot-starter-validation` Dependency

When Spring Boot manages dependencies via the Spring Boot parent/BOM, the standard approach is to add **`spring-boot-starter-validation`**. This starter bundles the components required for Bean Validation and avoids manually choosing incompatible API/provider versions.

### 4.1. Maven

In `pom.xml`, under `dependencies`:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

A simple Spring Boot application project also commonly includes:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter</artifactId>
</dependency>
```

Web projects may already include `spring-boot-starter-web` for HTTP support. The validation starter provides **constraint validation capability**; you do not need an HTTP server just to validate a configuration record.

After editing `pom.xml`, sync dependencies in your IDE or run a standard build:

```bash
./mvnw test
```

On Windows, use `mvnw.cmd test` in an appropriate terminal. For projects without the Maven Wrapper, use your locally installed Maven.

Do not pin an arbitrary Hibernate Validator version when Spring Boot already manages compatible dependency versions.

### 4.2. Gradle Kotlin DSL

In `build.gradle.kts`:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    implementation("org.springframework.boot:spring-boot-starter-validation")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

### 4.3. Gradle Groovy DSL

In `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    implementation 'org.springframework.boot:spring-boot-starter-validation'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

These Gradle snippets assume the project already applies the Spring Boot plugins and dependency management properly. Do not paste a duplicate starter if it is already declared.

### 4.4. Why Use the Starter Instead of Only `jakarta.validation-api`?

`jakarta.validation-api` only provides interfaces and annotations. Without a runtime provider implementation, constraints may not be evaluated as expected or requesting a `Validator` will fail.

`spring-boot-starter-validation` is convenient for Spring Boot applications because it supplies an integrated validation stack whose versions match your Spring Boot release. In a custom setup, you could wire the API and provider manually, taking responsibility for version compatibility and provider configuration.

**Runtime verification matters more than checking imports:** a Java file with `@NotBlank` compiling cleanly does not prove binding actually executes validation.

## 5. Sample Example: `@ConfigurationProperties` as a Record

Let's use a Spring Boot 3.x application, Java 17 or later, with no real external service connection needed. Illustrative layout:

```text
validation-demo/
└── src/
    ├── main/
    │   ├── java/com/example/validationdemo/
    │   │   ├── ValidationDemoApplication.java
    │   │   └── NotificationProperties.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/com/example/validationdemo/
            └── NotificationPropertiesTest.java
```

Addresses ending in `.invalid` are purely placeholder data, not real endpoints.

Create `application.yml`:

```yaml
notification:
  enabled: true
  sender-name: Operations
  sender-email: ops@example.invalid
  api-url: https://notify.example.invalid/api
  max-attempts: 3
  connect-timeout: 2s
```

Create `NotificationProperties.java`:

```java
package com.example.validationdemo;

import java.net.URI;
import java.time.Duration;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(

        boolean enabled,

        @NotBlank
        String senderName,

        @NotBlank
        @Email
        String senderEmail,

        @NotNull
        URI apiUrl,

        @Min(1)
        @Max(10)
        int maxAttempts,

        @NotNull
        Duration connectTimeout
) {
}
```

The annotations on the record serve these purposes:

| Component | Type | Constraint | Intent |
| --- | --- | --- | --- |
| `enabled` | `boolean` | No constraint required in this example | Enable/disable feature |
| `senderName` | `String` | `@NotBlank` | Not null, not empty, not whitespace-only |
| `senderEmail` | `String` | `@NotBlank` and `@Email` | Must be provided and formatted as an email |
| `apiUrl` | `URI` | `@NotNull` | Must be provided |
| `maxAttempts` | `int` | `@Min(1)`, `@Max(10)` | Bounded within 1–10 |
| `connectTimeout` | `Duration` | `@NotNull` | Must be provided |

A few notes:

- `@Validated` is imported from Spring's **`org.springframework.validation.annotation.Validated`**.
- `@NotBlank`, `@Email`, `@Min`, `@Max`, and `@NotNull` are imported from **`jakarta.validation.constraints`**.
- `@ConfigurationProperties` belongs to **`org.springframework.boot.context.properties`**.
- `@NotNull` on `Duration` only checks for non-null; **it does not guarantee the duration is greater than zero**.
- `@NotNull` on `URI` does not mean the URI uses HTTPS, has a valid host, or is reachable.
- When designing with primitive `int`, an omitted value can result in `0` in relevant cases; `@Min(1)` catches values below the requirement.

This is a **typed configuration holder with constraints**, not a place for HTTP calls or business processing.

## 6. Registering the Configuration Class So Validation Can Run

Adding annotations to a record is not enough if the class is never registered as a configuration-properties bean.

Create `ValidationDemoApplication.java`:

```java
package com.example.validationdemo;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
@EnableConfigurationProperties(NotificationProperties.class)
public class ValidationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showNotificationConfig(
            NotificationProperties properties) {
        return args -> {
            System.out.println(
                "enabled = " + properties.enabled());
            System.out.println(
                "senderName = " + properties.senderName());
            System.out.println(
                "maxAttempts = " + properties.maxAttempts());
            System.out.println(
                "connectTimeout = " + properties.connectTimeout());
        };
    }
}
```

`@EnableConfigurationProperties(NotificationProperties.class)` registers the configuration type. When Spring Boot builds the context:

1. Finds active property sources.
2. Binds `notification.*` into the record.
3. Runs Bean Validation on the object when `@Validated` and a matching provider are present.
4. If valid, registers the `NotificationProperties` bean for injection into other beans via constructor.
5. If invalid, can halt startup and report binding/validation errors.

In this example, `ApplicationRunner` prints only **non-sensitive** values. Never print tokens, passwords, or entire configuration objects in a real application.

Instead of listing classes individually in `@EnableConfigurationProperties`, projects with many configuration classes can use:

```java
@SpringBootApplication
@ConfigurationPropertiesScan
public class ValidationDemoApplication {
    // ...
}
```

Remember to import `org.springframework.boot.context.properties.ConfigurationPropertiesScan`. Pick one clear registration mechanism for the record in the example.

**Do not routinely add `@Component` to a constructor-bound `@ConfigurationProperties` record expecting Spring to use the Binder for constructor arguments the same way as `@EnableConfigurationProperties`.** Constructor binding and standard bean constructor injection are different mechanisms.

## 7. First Experiment: Valid and Invalid Configurations

### 7.1. Valid Case

Using the `application.yml` given above:

```yaml
notification:
  enabled: true
  sender-name: Operations
  sender-email: ops@example.invalid
  api-url: https://notify.example.invalid/api
  max-attempts: 3
  connect-timeout: 2s
```

Package the application and run the executable JAR; `app.jar` is an illustrative filename:

```bash
java -jar app.jar
```

Expected output:

```text
enabled = true
senderName = Operations
maxAttempts = 3
connectTimeout = PT2S
```

Here `PT2S` is `Duration.toString()` for two seconds.

### 7.2. Violating `@Min`

Change only `max-attempts`:

```bash
java -jar app.jar --notification.max-attempts=0
```

The value `0` converts to `int` cleanly, yet fails `@Min(1)`. Consequently, Spring Boot can report a startup failure related to validating `NotificationProperties`, naming the `maxAttempts` field, the rejected value, and the violated constraint.

The exact formatting varies across versions, but the content looks similar to:

```text
Failed to bind properties under 'notification'
...
Property: notification.maxAttempts
Value: 0
Reason: must be greater than or equal to 1
```

This is an illustrative example, not a character-for-character log guarantee. **The cause is not that `0` failed to convert to `int`**, but that an integer constraint was violated.

### 7.3. Violating `@NotBlank`

Run:

```bash
java -jar app.jar '--notification.sender-name=   '
```

The argument is quoted to preserve spaces. A string containing only whitespace fails `@NotBlank`. If using another shell, ensure the exact whitespace value reaches the application as intended.

### 7.4. Violating `@Email`

Run:

```bash
java -jar app.jar --notification.sender-email=not-an-email
```

The string binds to `String` but does not satisfy the email format rules of the active validator. The result can be a validation error when Spring builds the context.

`@Email` is a syntax constraint; **it does not prove the email address exists or can receive mail**. Verifying actual email delivery is a separate problem.

### 7.5. Conversion Error Before Validation

Run:

```bash
java -jar app.jar --notification.max-attempts=several
```

`several` cannot be converted to `int`. This is a binding/type conversion error. The `@Min` constraint cannot turn a non-numeric string into a valid number. When reading logs, distinguish the two causes.

## 8. Common `jakarta.validation` Annotations

### 8.1. `@NotNull`

`@NotNull` requires the value not to be `null`.

```java
@NotNull
URI apiUrl;
```

Suitable for reference types like `URI`, `Duration`, and nested objects. On primitive `int`, the type cannot be `null`, so `@NotNull` cannot detect a missing key in the same way.

For example:

```yaml
notification:
  api-url: https://notify.example.invalid/api
```

If the property is absent and the object receives `null`, the constraint fails. However, business-invalid URLs still require dedicated checks; a syntactically valid `URI` does not guarantee the application can call the endpoint.

### 8.2. `@NotEmpty`

`@NotEmpty` requires the value not to be null and not empty. It applies to `CharSequence`, collections, maps, or arrays supported by the provider.

```java
@NotEmpty
List<String> recipients;
```

This requires the list to contain elements, yet does not mean **every element** is non-empty. If you need to validate each email, use appropriate element-level annotations.

### 8.3. `@NotBlank`

`@NotBlank` applies to `CharSequence` strings, requiring them to be non-null and contain at least one non-whitespace character.

```java
@NotBlank
String senderName;
```

Comparison:

| Value | `@NotNull` | `@NotEmpty` | `@NotBlank` |
| --- | --- | --- | --- |
| `null` | Invalid | Invalid | Invalid |
| `""` | Valid | Invalid | Invalid |
| `"   "` | Valid | Valid | Invalid |
| `"Ops"` | Valid | Valid | Valid |

`@NotBlank` fits display names or required text strings. Do not apply `@NotBlank` directly to `URI`, `Integer`, or `Duration`; it is not a universal constraint for all types.

### 8.4. `@Min` and `@Max`

Two annotations for numeric bounds:

```java
@Min(1)
@Max(10)
int maxAttempts;
```

They check `maxAttempts >= 1` and `maxAttempts <= 10`.

Example outcomes:

| Value | `@Min(1)` | `@Max(10)` |
| --- | --- | --- |
| 0 | Invalid | Valid |
| 1 | Valid | Valid |
| 5 | Valid | Valid |
| 10 | Valid | Valid |
| 11 | Valid | Invalid |

For `BigDecimal` or decimal bounds, use `@DecimalMin`, `@DecimalMax`, or another appropriate constraint. Do not assume `@Min` is the right tool for all floating-point/decimal types.

### 8.5. `@Positive` and `@PositiveOrZero`

```java
@Positive
int retryCount;

@PositiveOrZero
long pendingCount;
```

`@Positive` requires strictly greater than 0. `@PositiveOrZero` allows 0. When modeling **maximum** attempts, decide whether `0` validly means "do not retry" before choosing an annotation.

### 8.6. `@Size`

```java
@Size(min = 2, max = 40)
String senderName;

@Size(min = 1, max = 5)
List<String> recipients;
```

`@Size` checks string length or collection/map/array size for supported types. It does not validate the elements inside a collection.

Notably, `@Size(min=1)` on a whitespace-only string can still pass. If you want to reject whitespace-only strings, use `@NotBlank`.

### 8.7. `@Email`

```java
@NotBlank
@Email
String senderEmail;
```

These two annotations complement each other. `@Email` can treat `null` as not violating the format constraint itself; `@NotBlank` requires actual text content.

A syntactically accepted email string **does not prove** the domain has mail servers, the recipient exists, or the address is verified.

### 8.8. `@Pattern`

```java
@Pattern(regexp = "[a-z][a-z0-9-]*")
String clientCode;
```

A regex-based format constraint on strings. In this example, the code starts with a lowercase letter followed by lowercase letters, digits, or hyphens.

If the value is required, combine it with `@NotBlank`. `@Pattern` alone is typically not used to require presence.

### 8.9. `@Valid`

`@Valid` is not a value constraint like `@Min`. It tells validation to **descend into nested objects or elements**, commonly known as *cascaded validation*.

```java
@Valid
@NotNull
RetryPolicy retry;
```

When `retry` is present, `@Valid` causes constraints on its inner fields to be evaluated. `@NotNull` requires the nested object itself not to be missing. These two annotations perform two different jobs.

## 9. Validating Nested Configuration

Real-world applications often have multi-level configuration:

```yaml
notification:
  enabled: true
  sender-name: Operations
  sender-email: ops@example.invalid
  retry:
    max-attempts: 4
    backoff: 250ms
```

A nested record:

```java
package com.example.validationdemo;

import java.time.Duration;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(

        @NotBlank String senderName,

        @NotBlank String senderEmail,

        @Valid
        @NotNull
        Retry retry
) {
    public record Retry(
            @Min(1) @Max(10) int maxAttempts,
            @NotNull Duration backoff
    ) {}
}
```

When the Binder constructs `NotificationProperties`, it also constructs `Retry` from `notification.retry.*`. `@Valid` on `retry` instructs the provider to continue evaluating constraints inside `Retry`.

If YAML contains:

```yaml
notification:
  sender-name: Operations
  sender-email: ops@example.invalid
  retry:
    max-attempts: 0
    backoff: 100ms
```

then `maxAttempts=0` fails `@Min(1)`. Thanks to nested validation, the failure can be reported at the path `notification.retry.max-attempts`.

**Do not omit `@Valid` merely because the nested class has annotations.** In many Bean Validation setups, constraints on nested objects are not traversed unless cascading or equivalent validation rules are explicitly configured. Use `@Valid` whenever deep validation is intended so behavior stays clear.

### How Do `@NotNull` and `@Valid` Differ?

With:

```java
@Valid
Retry retry;
```

if `retry` is `null`, cascading does not check fields of a non-existent object; `null` does not automatically fail `@Valid`.

With:

```java
@Valid
@NotNull
Retry retry;
```

`@NotNull` requires the object to be present. When present, `@Valid` validates the inner constraints.

This matters especially when a nested configuration group **must be supplied** in every deployment environment.

## 10. Collections and Maps: Validating Elements, Not Just the Group

Suppose configuration lists notification recipient emails:

```yaml
notification:
  recipients:
    - ops@example.invalid
    - audit@example.invalid
```

You can declare:

```java
import java.util.List;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;

@ConfigurationProperties(prefix = "notification")
@Validated
public record NotificationProperties(
        @NotEmpty
        List<@NotBlank @Email String> recipients
) {}
```

Here:

- `@NotEmpty` requires the list not to be empty.
- `@NotBlank` on the generic type parameter requires each string element to have content.
- `@Email` checks the format of each element.

These are Jakarta Validation **container-element constraints**, which require a supporting provider such as the modern Hibernate Validator managed by Spring Boot.

For a list of objects, you can use:

```java
public record NotificationProperties(
        @NotEmpty
        List<@Valid Channel> channels
) {
    public record Channel(
            @NotBlank String name,
            @NotBlank String topic
    ) {}
}
```

`@Valid` on the element type asks validation to check constraints inside each `Channel`. If one channel in the configuration lacks `topic`, the constraint can fail.

For `Map`, similarly you can place constraints on keys or values as supported by your provider:

```java
public record NotificationProperties(
        Map<@NotBlank String, @Valid Channel> channels
) {
    public record Channel(@NotBlank String topic) {}
}
```

If a list or map has dynamic keys, **validation still does not prove those names belong to a business allowlist**. Restricting channel names, regions, or tenants requires an appropriate constraint or custom validator.

## 11. When Do You Need a Custom Constraint?

Standard annotations handle single-field conditions well. Now suppose the requirement is:

> If `notification.enabled=true`, `api-url` must use HTTPS and `max-attempts` must be between 1 and 5. If disabled, no URL needs to be configured.

`@NotNull` on `apiUrl` cannot by itself express "required only when enabled." `@Min` inspects one field and knows nothing about an enable flag on another field.

You can solve this with an object-level constraint, such as a check method annotated with `@AssertTrue`:

```java
package com.example.validationdemo;

import java.net.URI;

import jakarta.validation.constraints.AssertTrue;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        boolean enabled,
        URI apiUrl,
        int maxAttempts
) {
    @AssertTrue(message =
        "when notification is enabled, HTTPS URL "
        + "and 1..5 attempts are required")
    public boolean isEnabledConfigurationValid() {
        if (!enabled) {
            return true;
        }

        return apiUrl != null
            && "https".equalsIgnoreCase(apiUrl.getScheme())
            && apiUrl.getHost() != null
            && maxAttempts >= 1
            && maxAttempts <= 5;
    }
}
```

The JavaBean-convention method `isEnabledConfigurationValid()` returns a boolean so Bean Validation can treat it as a constrained property. When `enabled=true` and the URL is missing or uses HTTP, the constraint fails.

This is a simple example for cross-field rules. In systems with complex rules, you can define a dedicated **class-level constraint** using `@Constraint` and `ConstraintValidator` to return structured error messages, target relevant fields, and reuse rules.

Do not cram heavy business logic or network calls into validation. Configuration validation should check available properties, run quickly, and behave deterministically at startup.

## 12. How Do Defaults and Validation Work Together?

Defaults reduce how many keys must be declared, yet **defaults must also be valid**.

For example, in `application.yml`:

```yaml
notification:
  enabled: false
  max-attempts: 3
```

If the record requires `@Min(1)`, the default value `3` is valid. But if an operator overrides it:

```bash
java -jar app.jar --notification.max-attempts=0
```

then the effective value is `0`, and validation rejects it. There is no rule saying YAML always wins or acts as a fallback when an overriding value is invalid.

With Spring Boot constructor binding, you can use `@DefaultValue` to supply a value when no matching property is present:

```java
import org.springframework.boot.context.properties.bind.DefaultValue;

@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(
        @DefaultValue("false") boolean enabled,
        @DefaultValue("3") @Min(1) @Max(10) int maxAttempts
) {}
```

Keep in mind:

- `@DefaultValue` is a Spring Boot **default binding** annotation, not a Jakarta Validation constraint.
- `@Min`/`@Max` check the record's values after binding.
- If the environment explicitly supplies an invalid value, defaults do not auto-correct that data.
- If a primitive field has no value and no default, its post-binding value may be zero/false depending on context; proper constraints catch missing values where positive numbers are required.

Avoid conflicting defaults scattered across YAML, annotations, service code, and deployment manifests. Choose one clear place as the contract.

## 13. Profile-Specific Configuration Must Still Be Valid

Base `application.yml`:

```yaml
notification:
  enabled: false
  sender-name: Operations
  sender-email: ops@example.invalid
  api-url: https://notify.example.invalid/api
  max-attempts: 3
  connect-timeout: 2s
```

`application-prod.yml`:

```yaml
notification:
  enabled: true
  api-url: https://notify-prod.example.invalid/api
  max-attempts: 5
```

When running:

```bash
java -jar app.jar --spring.profiles.active=prod
```

Spring Boot loads the active configuration sources, resolves the effective value of each key, and the Binder creates `NotificationProperties`. Constraints validate the **final post-binding values**, not individual YAML lines in isolation.

This has two consequences:

1. Valid values in a base file can be overridden by invalid values from a higher-precedence source.
2. A profile file declaring only a few keys can still be valid because the remaining keys come from the base source, provided no constraints are violated.

For example:

```bash
java -jar app.jar \
  --spring.profiles.active=prod \
  --notification.max-attempts=-1
```

Command-line arguments can outrank Config Data and cause validation to fail even though `application-prod.yml` specifies `max-attempts: 5`.

Therefore, critical applications should be tested against the actual profiles and property mechanisms used in each environment, rather than testing `application.yml` alone.

## 14. Binding Errors and Validation Errors Look Different in Logs

Reading startup messages sequentially helps narrow down the root cause.

### 14.1. Type Mismatch

```properties
notification.max-attempts=several
```

If the record expects `int`, the failure occurs because no converter can turn that string into `int`. Logs may mention `Failed to bind properties under 'notification.max-attempts' to int` or an equivalent conversion cause.

**Do not fix this by removing `@Min`**; the problem lies in the input data or target type.

### 14.2. Right Type, Violated Constraint

```properties
notification.max-attempts=-1
```

`-1` converts to `int` cleanly; `@Min(1)` rejects it. Logs may display the rejected value and a message like `must be greater than or equal to 1`.

**Do not fix this by changing `int` to `String`**; adjust the attempt count or the validation contract.

### 14.3. Missing Required Value

If `sender-name` is absent from all sources and the record receives `null`, `@NotBlank` can report an error. This differs from an extra property with no target field.

### 14.4. Extra Property

If a file contains `notification.debug-mode` when the record declares no such field, Spring Boot offers `ignoreUnknownFields` on `@ConfigurationProperties` to control whether unbound properties are ignored or rejected.

This is not the job of `@NotBlank`/`@Min`. Field validation and unknown-property checks are two separate rule sets.

### 14.5. A Key with an Empty Value

```properties
notification.sender-name=
```

For `String senderName`, an empty value may bind as an empty string, which `@NotBlank` rejects. For `int maxAttempts`, an empty string may cause a conversion/binding failure rather than a `@Min` violation. The exact behavior depends on the data type and converter used.

## 15. Testing Validation Without Running the JAR Repeatedly

Command-line runs help demonstrate real runtime behavior. For automated tests, Spring Boot Test provides `ApplicationContextRunner`, letting you spin up a minimal context, pass properties, and assert whether startup succeeds or fails.

In a test file, use a focused properties class to concentrate on constraints:

```java
package com.example.validationdemo;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @NotBlank String queueName,
        @Min(1) int batchSize
) {}
```

Write the test:

```java
package com.example.validationdemo;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Configuration;

class WorkerPropertiesTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfig.class);

    @Test
    void acceptsValidConfiguration() {
        runner.withPropertyValues(
                "worker.queue-name=inbox",
                "worker.batch-size=20"
            )
            .run(context -> {
                assertThat(context.getStartupFailure()).isNull();

                WorkerProperties properties =
                    context.getBean(WorkerProperties.class);
                assertThat(properties.queueName()).isEqualTo("inbox");
                assertThat(properties.batchSize()).isEqualTo(20);
            });
    }

    @Test
    void rejectsInvalidBatchSize() {
        runner.withPropertyValues(
                "worker.queue-name=inbox",
                "worker.batch-size=0"
            )
            .run(context -> {
                assertThat(context.getStartupFailure()).isNotNull();
            });
    }

    @Test
    void rejectsBlankQueueName() {
        runner.withPropertyValues(
                "worker.queue-name=   ",
                "worker.batch-size=20"
            )
            .run(context -> {
                assertThat(context.getStartupFailure()).isNotNull();
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(WorkerProperties.class)
    static class TestConfig {}
}
```

These tests require Spring Boot Test and a Jakarta Validation provider on the test classpath. When using `spring-boot-starter-test` and `spring-boot-starter-validation` in a properly configured Spring Boot project, you typically do not need to start a mock HTTP server or database.

Test goals:

- **Valid test** verifies the Binder creates the bean and supplies typed values.
- **Invalid number test** verifies `@Min(1)` rejects `0`.
- **Blank name test** verifies `@NotBlank` rejects whitespace-only strings.

Do not assume every case is covered just because one test passes; each important constraint deserves representative valid and invalid cases.

## 16. Testing Nested Validation

For nested configuration, include tests proving that nested object constraints actually execute. For example:

```java
package com.example.validationdemo;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.validation.annotation.Validated;

@Validated
@ConfigurationProperties(prefix = "jobs")
public record JobProperties(
        @Valid @NotNull Retry retry
) {
    public record Retry(
            @Min(1) int maxAttempts
    ) {}
}
```

A similar test using `ApplicationContextRunner`:

```java
@Test
void validatesNestedRetryObject() {
    runner.withPropertyValues(
            "jobs.retry.max-attempts=0"
        )
        .run(context -> {
            assertThat(context.getStartupFailure()).isNotNull();
        });
}
```

This test requires a matching `@EnableConfigurationProperties(JobProperties.class)` configuration, rather than reusing `TestConfig` from the previous section that only registered `WorkerProperties`.

If the test unexpectedly passes startup, check:

1. Is `JobProperties` registered as a configuration-properties bean?
2. Is `@Validated` present?
3. Is `jakarta.validation.Valid` placed on the `retry` component?
4. Is a compatible Bean Validation provider on the runtime classpath?
5. Are the test property keys actually under the `jobs.retry` prefix?

Writing nested tests is crucial because configuration can bind an object successfully while silently skipping deep validation if miswired.

## 17. Is `@Validated` Always the Same as `@Valid`?

No.

- `@Validated` is a Spring annotation, typically placed on a `@ConfigurationProperties` class to ask Spring Boot to validate the bound configuration object.
- `@Valid` is a Jakarta Validation annotation used for **cascaded validation** of nested properties, objects, or elements.
- Constraints such as `@NotBlank` and `@Min` specify **concrete conditions** to satisfy.

A typical design:

```java
@Validated
@ConfigurationProperties(prefix = "jobs")
public record JobProperties(
        @Valid @NotNull Retry retry
) {
    public record Retry(@Min(1) int maxAttempts) {}
}
```

Here are the three layers of meaning:

```text
@Validated          -> enables validation on the root config object
@Valid              -> descends into Retry when present
@Min(1)             -> rule checked on maxAttempts
```

Do not omit one piece and expect the remaining annotations to perform every step automatically.

## 18. Which Annotation Should Be Used for `Duration`?

A common mistake is putting `@Min(1)` directly on a `Duration`:

```java
@Min(1)
Duration timeout;
```

`@Min` is a constraint for supported numeric types. `Duration` is not an `int`, `long`, or `BigDecimal`. With common providers, applying the wrong constraint type can fail with an error indicating no validator exists for `Duration`.

If you only need a non-null value:

```java
@NotNull
Duration timeout;
```

If you need a **positive timeout**, you have several options:

1. An object-level check with `@AssertTrue` ensuring `timeout != null && !timeout.isZero() && !timeout.isNegative()`.
2. Create a custom constraint specifically for `Duration`.
3. Use an additional framework constraint if your Spring Boot version supports one, such as dedicated duration annotations; confirm the package and conditions for your version.
4. If the input truly represents milliseconds, model it as a numeric type with numeric constraints and document the unit clearly.

Object-level example:

```java
@Validated
@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @NotNull Duration timeout
) {
    @AssertTrue(message = "worker.timeout must be positive")
    public boolean isTimeoutPositive() {
        return timeout != null
            && !timeout.isNegative()
            && !timeout.isZero();
    }
}
```

Remember to import `jakarta.validation.constraints.AssertTrue`. Do not assume `Duration.parse(...)` or Spring Boot's Binder rejects all negative `Duration` values; a type-valid value is not necessarily business-valid.

## 19. Bean Validation Does Not Replace Secret and Endpoint Checks

A `@ConfigurationProperties` object can declare:

```java
@NotBlank
String apiToken;

@NotNull
URI endpoint;
```

If the token has text and the endpoint is a syntactically valid URI, those constraints can pass. Yet nothing guarantees that:

- The token was issued by the right system or has not expired.
- The token is stored securely.
- The endpoint is on an allowed network.
- The server at the endpoint is up and healthy.
- The endpoint enforces proper TLS standards.
- The service account running the app has authorization to connect.

These are security and operational requirements beyond basic Bean Validation. Supply secrets via a secret manager, environment variables, or platform-appropriate mechanisms; never commit real tokens in YAML files just because the class has `@NotBlank`.

Additionally, avoid printing entire `@ConfigurationProperties` instances when a record contains sensitive fields. `record.toString()` can expose field values in logs. Validation error messages can also include rejected values in some situations; consider logging and redaction practices for confidential data.

## 20. Not All Configuration Needs Equally Strict Validation

In a production service, a missing payment endpoint or retry limit may be a fatal error. Yet an optional feature may legitimately be disabled with some keys omitted.

For example:

```yaml
notification:
  enabled: false
```

If the properties class unconditionally puts `@NotNull` on `apiUrl`, it demands a URL even while the feature is disabled. Whether that is right or wrong depends on the contract.

Two design approaches:

**Approach A — every environment must have a URL.** Keep `@NotNull URI apiUrl`. This is simple and fits when the endpoint is a deployment requirement regardless of the `enabled` flag.

**Approach B — URL required only when enabled.** Use a cross-field constraint like `@AssertTrue` or a custom validator. Do not apply `@NotNull` unconditionally to the API URL if the contract genuinely allows null when disabled.

Annotation choices must follow operational requirements; do not automatically slap `@NotNull` onto every nullable field you see.

## 21. `@Validated` and Validation Groups

Jakarta Validation supports *validation groups* to select different sets of constraints in different contexts. Spring's `@Validated` also accepts group parameters.

Conceptually: an API request during creation may have different rules from an update request. For configuration properties, however, too many groups can make the configuration contract hard to read.

An application can split into separate properties classes or clear conditional configurations when different environments have distinct rule sets. Do not rush to create validation groups just to express that `dev` and `prod` use different endpoints. Profiles and config sources handle **value selection**; validation handles **checking the selected values**.

If using groups with `@ConfigurationProperties`, verify how your binding mechanism and framework version activate the intended group. The simplest starting point is default-group validation with constraints that hold across all supported environments.

## 22. When Validation Does Not Run: Troubleshooting Checklist

Suppose `max-attempts=0` yet the application still starts despite `@Min(1)`. Check in order:

### 22.1. Is the Validation Provider Dependency Present?

Open the project's build file and look for `spring-boot-starter-validation`. Having only the annotation API without a compatible provider may leave constraint evaluation unconfigured.

### 22.2. Are You Using the Correct Jakarta Namespace?

For Spring Boot 3.x, import correctly:

```java
import jakarta.validation.constraints.Min;
```

Do not mix annotations from an older project's `javax.validation`.

### 22.3. Is `@Validated` on the Properties Class?

```java
@Validated
@ConfigurationProperties(prefix = "notification")
public record NotificationProperties(...) {}
```

If annotations sit only on a class not created by the Spring Boot Binder, startup validation will not trigger as expected.

### 22.4. Is the Properties Class Registered?

`@EnableConfigurationProperties(NotificationProperties.class)` or `@ConfigurationPropertiesScan` must cover the class in constructor-binding setups.

### 22.5. Are You Validating Nested Objects?

If the constraint lives inside a nested record, verify `@Valid` along the path from root to nested object and verify the nested object's presence.

### 22.6. Are the YAML Keys Accurate?

If a file declares `notification.max-atempt` (typo) while the record defines `maxAttempts`, the bound value may be missing/0 or come from another source. Check relaxed binding and `ignoreUnknownFields`; **validation only sees the object and values produced after binding**.

### 22.7. Is a Higher-Precedence Source Overriding It?

A flag like `--notification.max-attempts=5` can override `max-attempts: 0` in a file. In that case, validation sees the valid value `5` and reports no error. Never conclude validation is broken simply by looking at one YAML file.

### 22.8. Is the Object Being Instantiated with `new` Outside Spring?

```java
new NotificationProperties(true, "Ops", "bad-email", null, 0, null);
```

This Java expression simply invokes the record constructor. Bean Validation does not run automatically just because components carry annotations; to validate an object created manually in code, use a `Validator` or equivalent check. In Spring Boot, binding-time validation integration handles this for configuration beans created through the standard lifecycle.

## 23. Validating an Object Using `jakarta.validation.Validator`

Aside from validation during Spring property binding, you sometimes need to validate an already-constructed object. The Jakarta Validation API provides `Validator` for this.

Consider a brief hypothetical config record:

```java
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public record JobOptions(
        @NotBlank String queue,
        @Min(1) int batchSize
) {}
```

And inside a Spring bean injected with `jakarta.validation.Validator`:

```java
import java.util.Set;
import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;

public class JobOptionsChecker {

    private final Validator validator;

    public JobOptionsChecker(Validator validator) {
        this.validator = validator;
    }

    public Set<ConstraintViolation<JobOptions>> check(
            JobOptions options) {
        return validator.validate(options);
    }
}
```

Calling `validator.validate(new JobOptions("", 0))` lets the provider return violations for `queue` and `batchSize`.

This illustrates that **Jakarta Validation is an independent object-validation mechanism**, not limited to HTTP requests. Spring Boot integrates it into configuration-properties binding when properly configured.

In production applications, avoid logging sensitive rejected values when iterating over `ConstraintViolation` results.

## 24. Is Early Failure Reporting Alone Enough?

Validation helps an application reject unsuitable configuration; yet deployments still require a reliable testing and configuration-management lifecycle.

A practical workflow:

1. **Define the configuration contract:** which fields are required, which have defaults, value ranges, cross-field dependencies.
2. **Model with appropriate Java types:** `URI`, `Duration`, `int`, `List`, nested records.
3. **Add Jakarta constraints:** `@NotBlank`, `@Min`, `@NotNull`, `@Email`, `@Valid` matched to each type.
4. **Register and enable validation:** `@ConfigurationProperties`, `@Validated`, and a valid provider.
5. **Write tests for both valid and invalid cases:** especially defaults, nested objects, and overrides.
6. **Test per profile:** because final values can differ across dev/staging/prod.
7. **Keep configuration sources secure:** do not commit credentials, do not log secrets.
8. **Monitor startup failures:** a fail-fast application still needs actionable messages so operators can fix the key and restart.

Do not suppress validation failures by silently replacing every invalid value with a default. Safe defaults are sometimes appropriate; for critical keys, however, **early failure detection** is usually far better than running with a configuration the operator never intended.

## 25. Common Mistakes When Setting Up Bean Validation

### 25.1. Adding Annotations Without the Starter

The app has `@Min(1)` yet lacks a compatible validation provider. Constraints may not execute as expected. Add the dependency and verify with an invalid-case test.

### 25.2. Importing `javax.validation` from Old Articles

Spring Boot 3 uses the Jakarta API. Do not mix `javax.validation.*` and `jakarta.validation.*` namespaces in a modern Jakarta stack project.

### 25.3. Forgetting `@Validated` on Root Properties

Putting constraints on a record without enabling validation appropriately can let the object bind without running checks. `@Validated` clearly declares validation intent for configuration-properties beans.

### 25.4. Forgetting to Register `@ConfigurationProperties`

`@ConfigurationProperties` alone does not guarantee any given record becomes a bean. Use `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan` in constructor-binding designs.

### 25.5. Using `@NotNull` to Prevent Empty Strings

`@NotNull` permits `""` and `"   "` because neither is null. For strings that must have content, use `@NotBlank`.

### 25.6. Using `@Email` Without Requiring Presence

`@Email` primarily checks format. When an email is mandatory, combine it with `@NotBlank` or an equivalent presence constraint.

### 25.7. Using `@Min` on `Duration`

`@Min` is not a default constraint for `Duration`. Use a supported duration-checking mechanism, `@AssertTrue`, or a custom constraint.

### 25.8. Omitting `@Valid` on Nested Objects

Constraints inside a nested object may not be evaluated as expected unless cascading is declared. Combine `@Valid` with `@NotNull` when the nested object is required.

### 25.9. Confusing Unknown Fields with Validation

`notification.unused-property` may fail to bind into the record, whereas standard constraints only inspect bound object values. `ignoreUnknownFields` governs unbound keys; that is not `@NotBlank`'s job.

### 25.10. Assuming `@NotNull URI` Guarantees a Secure URL

`@NotNull` does not verify the HTTPS scheme, host, certificates, or reachability. For critical endpoints, add structural validation and appropriate access policies.

### 25.11. Testing Only Valid Data

If you only have tests where the context starts successfully with valid values, you do not know whether validation is actually running. Include at least one test that intentionally violates a constraint and asserts startup failure.

### 25.12. Printing the Entire Configuration on Failure

Records can hold tokens or passwords; `toString()` typically prints all fields. Logging the object or rejected values can leak secrets. Display only key names and necessary info through protected logging mechanisms.

## 26. Self-Check Exercises

### Exercise 1: Error Classification

Given:

```java
@Validated
@ConfigurationProperties(prefix = "cache")
public record CacheProperties(
        @NotBlank String host,
        @Min(1) @Max(65535) int port
) {}
```

Classify these inputs:

| Configuration | Outcome |
| --- | --- |
| `cache.host=localhost`, `cache.port=6379` | Valid |
| `cache.host=`, `cache.port=6379` | `@NotBlank` fails |
| `cache.host=localhost`, `cache.port=0` | `@Min(1)` fails |
| `cache.host=localhost`, `cache.port=70000` | `@Max(65535)` fails |
| `cache.host=localhost`, `cache.port=abc` | Conversion error to `int` |

### Exercise 2: Choosing the Right Annotations

A configuration has:

- `displayName`: string that cannot be empty or whitespace-only.
- `email`: required email address.
- `connections`: connection count from 1 to 100.
- `endpoint`: URI that must be present.
- `tags`: list with at least one element, each element non-blank.
- `retry`: required nested object whose inner fields must be validated.

Suggested solution:

```java
@NotBlank String displayName

@NotBlank @Email String email

@Min(1) @Max(100) int connections

@NotNull URI endpoint

@NotEmpty List<@NotBlank String> tags

@Valid @NotNull Retry retry
```

### Exercise 3: Recognizing the `@NotNull Duration` Issue

Given:

```java
@NotNull Duration timeout
```

Can `timeout=-3s` convert to `Duration`? If the converter accepts it, will `@NotNull` fail? Why is a separate positivity check needed?

### Exercise 4: Verifying the Starter

A project uses:

```java
import jakarta.validation.constraints.Min;
```

but lacks `spring-boot-starter-validation`. Identify what to inspect in the dependencies/runtime classpath to ensure constraints are actually evaluated, then add the starter and write a test supplying `max-attempts=0`.

### Exercise 5: Nested Validation

Design:

```yaml
worker:
  retry:
    max-attempts: 0
```

and a record with a nested `Retry` having `@Min(1)`. Add `@Validated` at the root, `@Valid` on the `retry` field, register the bean, and prove the application rejects the configuration.

### Exercise 6: Distinguishing Binding, Validation, and Cross-Field Policy

An email service has `enabled=false` and no `api-url`. Is this an error? Choose one of two contracts: URL is always required, or URL is required only when enabled. Then choose simple field constraints or object-level validation accordingly.

### Exercise 7: Difference Between `@NotEmpty` and `@NotBlank`

Test the string values: `null`, `""`, `"   "`, and `"hello"`. Fill out a result table for `@NotNull`, `@NotEmpty`, and `@NotBlank`, then explain why `@NotEmpty` alone is insufficient for validating usernames.

### Exercise 8: Testing Overriding Sources

YAML has `worker.batch-size: 20` and the record declares `@Min(1)`. Run with `--worker.batch-size=0`. Predict the startup outcome and explain why validation checks the final value after a higher-precedence source overrides YAML.

## 27. Key Takeaways

A proper validation setup for Spring Boot configuration consists of three parts:

```text
1. Dependencies
   spring-boot-starter-validation
              |
              v
2. APIs and Annotations
   jakarta.validation.constraints.*
   jakarta.validation.Valid
   org.springframework.validation.annotation.Validated
              |
              v
3. Validated Binding
   @ConfigurationProperties
   @EnableConfigurationProperties / @ConfigurationPropertiesScan
              |
              v
   Valid -> bean is available for use
   Invalid -> startup failure
```

Key distinctions to remember:

- **`@ConfigurationProperties`** binds configuration sources into a typed Java object.
- **`@Validated`** requests validation of the configuration object within Spring Boot integration.
- **`jakarta.validation.constraints.*`** declares rules such as non-blank, numeric ranges, or format.
- **`@Valid`** triggers deep validation into nested objects or elements.
- **Starter/provider** ensures rules are executed at runtime, not left as passive annotations.
- **Type conversion, unknown fields, and Bean Validation** address different error categories.
- **Safe defaults and validation** complement each other; validation does not replace bad input with a default.
- **Testing invalid cases** is the direct way to confirm validation is active.

The intended outcome is **failing fast on misconfiguration**, so services never start operating with missing endpoints, negative retry counts, blank required names, or contract-violating data.

References: [Spring Boot — Type-safe Configuration Properties and Validation](https://docs.spring.io/spring-boot/reference/features/external-config.html#features.external-config.typesafe-configuration-properties.validation), [Spring Boot — Externalized Configuration](https://docs.spring.io/spring-boot/reference/features/external-config.html), [Jakarta Validation Specification](https://jakarta.ee/specifications/bean-validation/), and [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).