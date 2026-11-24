# Distinguishing Standard Features from Provider-Specific Extensions in Spring Validation

## 1. Why distinguish them?

In a Spring application, both snippets below can run when the project uses **Hibernate Validator**:

```java
@NotNull
@Min(18)
private Integer age;
```

and:

```java
@Range(min = 18, max = 65)
private Integer age;
```

However, they **do not have the same level of library independence**:

- `@NotNull` and `@Min` are constraints belonging to **Jakarta Validation**; any provider compatible with the Jakarta Validation version in use must support their standard contract.
- `@Range` resides in the `org.hibernate.validator.constraints` package; it is a **Hibernate Validator extension**, not specified by Jakarta Validation. If you switch to another provider, the code may fail to compile due to the missing annotation, or the new provider may not know how to enforce that constraint.
- Spring Framework sits at the **integration layer**: receiving data, triggering validation, and translating violations into binding/API errors. Spring does not turn a Hibernate Validator-specific feature into a standard Jakarta Validation feature.

This distinction matters when designing shared libraries, modules with many consumers, upgrading Spring Boot, or switching providers. For an application committed to Hibernate Validator long-term, using extensions deliberately can make sense; what to avoid is **mistaking an extension for a portable contract**.

This lesson focuses on three questions:

1. Which parts are standardized by Jakarta Validation?
2. Which parts only work thanks to a specific provider?
3. How does Spring connect the two, and how do you check the level of coupling?

The examples use Java 17+, Jakarta Validation 3.0, Spring Framework 6 / Spring Boot 3, and Hibernate Validator 8.x. For projects using different versions, check the compatibility matrix before applying.

## 2. Three layers to keep separate

```text
Application / Spring MVC / Spring Service
        |
        | @Valid, @Validated, BindingResult, LocalValidatorFactoryBean
        v
Jakarta Validation API / specification
        |
        | Validator, ValidatorFactory, @Constraint,
        | @NotNull, @Size, @Valid, ConstraintValidator...
        v
Provider implementing the contract
        |
        +-- Hibernate Validator
        |     + standard features
        |     + specific extensions: fail-fast, @Range, DSL mapping...
        |
        +-- Other compatible provider
              + standard features
              + possibly different specific extensions
```

### 2.1. Specification/API: the shared contract

**Jakarta Validation** defines annotations, interfaces, required behaviors, and the bootstrap mechanism. Typical packages:

- `jakarta.validation`: `Validation`, `Validator`, `ValidatorFactory`, `ConstraintValidator`, `ConstraintViolation`, `Valid`, `GroupSequence`.
- `jakarta.validation.constraints`: `NotNull`, `NotBlank`, `NotEmpty`, `Size`, `Min`, `Max`, `Pattern`, `Email`, `Positive`, `Past`, etc.
- `jakarta.validation.metadata`: constraint metadata.
- `jakarta.validation.executable`: validating method and constructor parameters and return values.
- `jakarta.validation.valueextraction`: SPI for extracting values inside containers.

Imports from these packages usually indicate that the code relies on the **standard contract**. Even so, a custom annotation written by the application in its own package can still be a **portable custom constraint** if it uses only standard interfaces and portable validation logic.

### 2.2. Provider: implementing the contract

**Hibernate Validator** is an implementation of Jakarta Validation, with its own library and packages such as:

```java
org.hibernate.validator.HibernateValidator
org.hibernate.validator.HibernateValidatorConfiguration
org.hibernate.validator.constraints.Range
org.hibernate.validator.constraints.Length
org.hibernate.validator.constraints.UniqueElements
org.hibernate.validator.constraintvalidation.HibernateConstraintValidatorContext
```

The provider is responsible for discovering constraints, instantiating validators, traversing the object graph, interpolating messages, and creating `ConstraintViolation`s. Jakarta Validation allows selecting a provider via SPI; calling `Validation.buildDefaultValidatorFactory()` does not guarantee the provider is Hibernate Validator if multiple implementations are on the classpath.

A library can be both a **compliant standard implementation** and a source of **extension APIs**. Therefore, do not equate “Hibernate Validator” with “proprietary features only”: most of what it does is execute Jakarta Validation.

**Hibernate Validator and Hibernate ORM are two distinct components.** Hibernate ORM/JPA is not required to run Hibernate Validator; the validation API can be used in web applications, CLIs, or data-processing jobs.

### 2.3. Spring: the integration layer, not another Jakarta Validation provider

Spring provides components such as:

- `@Valid`: **standard Jakarta** annotation used to request validation/cascading at integration points.
- `@Validated`: **Spring** annotation (`org.springframework.validation.annotation.Validated`), typically supporting validation groups and Spring integration points.
- `org.springframework.validation.Validator`: **Spring's** validator interface, distinct from `jakarta.validation.Validator` despite sharing the same simple name.
- `BindingResult`, `FieldError`, `ObjectError`: error representations at Spring's binding layer.
- `LocalValidatorFactoryBean`: adapter/bridge between Jakarta Validation and the Spring ecosystem.
- `spring-boot-starter-validation`: Spring Boot convenience dependency, typically bringing Hibernate Validator onto the classpath.

Spring's integration can select/configure the provider; it does not redefine `@Min`, nor does it guarantee every Hibernate Validator extension will run on another provider.

## 3. Identification table: standard, provider, Spring

| Feature/API | Belongs to | Provider portability | Notes |
| --- | --- | --- | --- |
| `@NotNull`, `@Size`, `@Min`, `@Max`, `@Email` | Jakarta Validation | High | Specified contract; test edge cases |
| `@NotBlank`, `@NotEmpty` | Jakarta Validation 2.0+ | High on compatible providers | Older docs may describe them as extensions |
| `@Valid` and cascaded validation | Jakarta Validation | High | Must have a validation trigger point |
| `List<@NotBlank String>` and container element constraints | Jakarta Validation 2.0+ | High if provider supports that version | Custom containers may need a `ValueExtractor` |
| `@GroupSequence`, validation groups | Jakarta Validation | High | Static group ordering is standardized |
| `@ReportAsSingleViolation` | Jakarta Validation | High | Single report for composed constraints; **not** a Hibernate extension |
| `@Constraint`, `ConstraintValidator` | Jakarta Validation | High | Portable if logic/metadata use standard APIs only |
| `ValidatorFactory`, `Validator`, `ConstraintViolation` | Jakarta Validation | High | Actual implementation comes from the provider |
| `MessageInterpolator`, `ClockProvider`, `ValueExtractor` | Jakarta Validation | High | Standard SPI; providers may have their own implementations |
| `@Range`, `@Length`, `@UniqueElements` | Hibernate Validator | Low | Additional provider constraints |
| `@ConstraintComposition(OR)` | Hibernate Validator | Low | OR/ALL_FALSE operators are extensions |
| `@GroupSequenceProvider` | Hibernate Validator | Low | Selects Default group sequence dynamically |
| `failFast(true)`, `hibernate.validator.fail_fast` | Hibernate Validator | Low | Stops after first violation; order not guaranteed |
| Fluent `ConstraintMapping` | Hibernate Validator | Low | Declares constraints via programmatic DSL |
| `HibernateConstraintValidatorContext` | Hibernate Validator | Low | Message parameters, expression variables, dynamic payloads |
| `@Validated`, `BindingResult`, `LocalValidatorFactoryBean` | Spring | Spring-dependent | Integration APIs, not provider extensions |

“High provider portability” **does not mean every implementation produces identical messages and violation ordering**. Translation wording, `Set<ConstraintViolation<?>>` iteration order, `@Email` algorithm details, or performance optimizations can differ; business tests should rely on conditions, property paths, and stable error codes.

## 4. How to spot them immediately in code and dependencies

### 4.1. Check imports instead of guessing from annotation names

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Size;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.ConstraintValidator;
```

These are standard Jakarta APIs. The snippet below uses extensions:

```java
import org.hibernate.validator.constraints.Range;
import org.hibernate.validator.constraints.UniqueElements;
import org.hibernate.validator.HibernateValidator;
```

Importing `org.springframework.validation.annotation.Validated` is a **Spring dependency**, neither Jakarta nor a Hibernate Validator extension API.

Seeing “Hibernate” in a dependency name is not enough to conclude coupling: an application can use Hibernate Validator strictly through Jakarta APIs without locking itself into any extension.

### 4.2. Look for vendor-specific properties

Configuration with keys like:

```properties
hibernate.validator.fail_fast=true
```

is vendor-specific. `Configuration#addProperty(String, String)` is a **standard mechanism**, whereas the meaning of the `hibernate.validator.fail_fast` key is a **Hibernate Validator** contract. When switching providers, the new provider may ignore or fail to recognize this key; do not assume it has an equivalent mechanism.

Similarly, `Validation.byProvider(HibernateValidator.class)` selects a specific provider. Meanwhile, `Validation.buildDefaultValidatorFactory()` and `Validation.byDefaultProvider()` are standard bootstrap APIs.

### 4.3. Check classpath and versions

For example with Gradle, `spring-boot-starter-validation` normally brings Hibernate Validator and the Jakarta Validation API transitively. When adding Hibernate Validator explicitly:

- Keep the version managed by the Spring Boot BOM unless there is a verified reason to override it.
- Avoid pulling incompatible Jakarta API versions simultaneously or mixing `javax.validation.*` with `jakarta.validation.*`.
- If extension packages appear in source, document the dependency and baseline version explicitly rather than assuming every consumer module has it.

For Spring Boot 3.x, source uses `jakarta.validation.*`. Older Spring Boot 2.x tutorials using `javax.validation.*` will have the wrong namespace on the new classpath.

## 5. Runnable example: same rules, two bootstrap approaches

This example uses **the exact same DTO declared solely with standard annotations**, then validates it via:

1. `Validation.buildDefaultValidatorFactory()` — standard bootstrap API.
2. `Validation.byProvider(HibernateValidator.class).configure().failFast(true)` — enabling a Hibernate Validator extension.

What to observe is that **the data contract stays unchanged**, yet the number of reported errors can differ due to provider configuration.

### 5.1. Gradle and environment

Create a Spring Boot 3.3.x project with Java 17. File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.6'
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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` brings the API and the Hibernate Validator implementation into the project. This example intentionally uses Hibernate Validator 8.x per Spring Boot 3.3 dependency management; using a different provider would require adjusting runtime dependencies.

### 5.2. Complete application

File `src/main/java/com/example/validationdemo/ValidationComparisonApplication.java`:

```java
package com.example.validationdemo;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotNull;
import org.hibernate.validator.HibernateValidator;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ValidationComparisonApplication implements CommandLineRunner {

    public record Candidate(
            @NotNull String name,
            @Min(18) int age
    ) {}

    public static void main(String[] args) {
        SpringApplication.run(ValidationComparisonApplication.class, args);
    }

    @Override
    public void run(String... args) {
        Candidate invalid = new Candidate(null, 16);

        // Use only the standard API to bootstrap and validate.
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {

            int count = factory.getValidator()
                    .validate(invalid)
                    .size();

            System.out.println("Standard API violations: " + count);
        }

        // Select Hibernate Validator and use its provider-specific failFast API.
        try (ValidatorFactory factory =
                Validation.byProvider(HibernateValidator.class)
                        .configure()
                        .failFast(true)
                        .buildValidatorFactory()) {

            int count = factory.getValidator()
                    .validate(invalid)
                    .size();

            System.out.println("Hibernate fail-fast violations: " + count);
        }
    }
}
```

Run:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. Aside from the Spring Boot banner and logs, the two lines printed via `println` will be:

```text
Standard API violations: 2
Hibernate fail-fast violations: 1
```

Explanation:

- `Candidate.name == null` violates `@NotNull`.
- `Candidate.age == 16` violates `@Min(18)`.
- By default, the validator in the example reports **two violations**.
- With `failFast(true)`, Hibernate Validator stops after the **first violation**, reporting one violation. **Do not rely on whether that error is `name` or `age`** because the provider does not guarantee constraint evaluation order.
- Even though the first branch uses the standard API, the actual provider on the example classpath is still typically **Hibernate Validator**. The label “Standard API” refers to the **calling contract**, not proof that the app is running a different provider.
- The demo class intentionally imports `HibernateValidator` to demonstrate the extension. If the goal is a provider-independent module, only the DTO and standard bootstrap branch belong in the core module; Hibernate-specific parts should live in a separate adapter/config.

**Do not create a `ValidatorFactory` on every HTTP request.** The example opens and closes two factories for comparison; in a real Spring application, use the container-managed validator factory/`LocalValidatorFactoryBean`. Factories typically cache metadata and can be shared across threads.

## 6. Writing portable constraints instead of vendor-specific annotations

Suppose you need an SKU code consisting only of ASCII uppercase letters and digits. Hibernate Validator has many extra constraints, but a custom constraint using standard Jakarta APIs lets you share the rule without depending on provider annotations.

### 6.1. Annotation `@UppercaseSku`

File `src/main/java/com/example/validationdemo/UppercaseSku.java`:

```java
package com.example.validationdemo;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target({ElementType.FIELD, ElementType.PARAMETER,
         ElementType.ANNOTATION_TYPE, ElementType.RECORD_COMPONENT})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = UppercaseSkuValidator.class)
public @interface UppercaseSku {
    String message() default "SKU must contain only A-Z and 0-9";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

The annotation uses only `jakarta.validation.Constraint` and `Payload`. The three attributes `message`, `groups`, and `payload` are the standard contract for custom constraints; it can be placed on fields, parameters, or record components.

### 6.2. `ConstraintValidator` logic

File `src/main/java/com/example/validationdemo/UppercaseSkuValidator.java`:

```java
package com.example.validationdemo;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class UppercaseSkuValidator
        implements ConstraintValidator<UppercaseSku, String> {

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {
        // Let @NotNull or @NotBlank handle missing fields.
        return value == null || value.matches("[A-Z0-9]+");
    }
}
```

Can be used on a DTO:

```java
package com.example.validationdemo;

import jakarta.validation.constraints.NotBlank;

public record ProductRequest(
        @NotBlank @UppercaseSku String sku
) {}
```

Behavior examples:

| Value | `@UppercaseSku` | `@NotBlank` | Overall valid |
| --- | --- | --- | --- |
| `"ABC12"` | Pass | Pass | Yes |
| `"ab12"` | Fail | Pass | No |
| `""` | Fail | Fail | No |
| `null` | Pass | Fail | No |

This validator is **portable at the Jakarta API level** because it does not import `org.hibernate.validator.*` types. Actually running on another provider still depends on that provider properly supporting the spec and the types/annotations declared by the application.

Important note: the regex above accepts only the **ASCII** alphabet, matching the SKU assumption in the example; do not assume it covers “any Unicode uppercase letter”. If business rules require a more complex code format, adjust the regex/algorithm and test explicitly.

### 6.3. Custom field-level violations also have a standard API

If an annotation is placed at the class level and needs to attach an error to a field, use the Jakarta mechanism:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        "{booking.checkOut.invalid}")
    .addPropertyNode("checkOut")
    .addConstraintViolation();
return false;
```

This snippet is **illustrative code inside `ConstraintValidator#isValid`**, not a standalone program. `buildConstraintViolationWithTemplate`, `addPropertyNode`, and `addConstraintViolation` are Jakarta APIs; there is no need to cast to `HibernateConstraintValidatorContext` just to set an error path.

**Practice:** If a requirement can be satisfied cleanly using standard `ConstraintValidatorContext`, prefer the standard API first. Use extensions only when you need capabilities genuinely absent from the standard.

## 7. Commonly encountered Hibernate Validator extensions

### 7.1. Built-in but non-standard constraints

Example:

```java
import org.hibernate.validator.constraints.Length;
import org.hibernate.validator.constraints.Range;
import org.hibernate.validator.constraints.UniqueElements;

public class VendorRequest {

    @Length(min = 4, max = 20)
    String nickname;

    @Range(min = 18, max = 65)
    int age;

    @UniqueElements
    java.util.List<String> tags;
}
```

This is an **illustrative snippet for API identification**, not advice to replace standard constraints with extensions.

Comparison:

- `@Length(min = 4, max = 20)` can be replaced by `@Size(min = 4, max = 20)` on `CharSequence` if the business meaning matches.
- `@Range(min = 18, max = 65)` can be expressed using `@Min(18)` and `@Max(65)` for numeric types supported by standard annotations. **Violation count, messages, and metadata** may differ when rewritten this way.
- `@UniqueElements` checks that elements in a collection are unique per `equals()`. Jakarta Validation has no standard annotation with this name; a portable custom constraint or separate business check is needed if removing the dependency.

Substitutability cannot be judged by annotation name alone: you must examine **null semantics, supported types, messages, groups, API responses, and boundary behavior**.

### 7.2. Fail-fast

Hibernate Validator supports:

```java
ValidatorFactory factory =
        Validation.byProvider(HibernateValidator.class)
                .configure()
                .failFast(true)
                .buildValidatorFactory();
```

It can also be configured via `hibernate.validator.fail_fast=true` (a Hibernate Validator-specific key). Fail-fast stops early when you only care “is there any error?”; it is unsuitable if the frontend needs **all form errors** so users can fix everything in one pass.

**Distinguish from standard group sequences:** `@GroupSequence` runs groups in a defined order and stops before the next group when the current group has violations. It is **not equivalent to fail-fast**, because a single group can still produce multiple violations; swapping one feature for the other alters error-reporting logic.

### 7.3. Constraint composition: standard AND, vendor-specific OR

Jakarta Validation lets you create composed constraints by placing multiple constraints on a new annotation. Under the standard contract, components combine with **AND** logic. `@ReportAsSingleViolation` is also part of Jakarta and collapses error reporting.

Hibernate Validator additionally provides:

```java
import org.hibernate.validator.constraints.ConstraintComposition;
import org.hibernate.validator.constraints.CompositionType;

@ConstraintComposition(CompositionType.OR)
```

These are only the key lines of a composed constraint, **not a complete annotation**. `CompositionType.OR` passes when at least one condition passes; `CompositionType.ALL_FALSE` expresses another extension logic. Other providers are not required to understand them. Do not confuse `@ReportAsSingleViolation` (standard) with `@ConstraintComposition` (Hibernate-specific) just because they often appear next to each other.

### 7.4. Dynamic default group sequence

The Jakarta standard provides `@GroupSequence` for **statically declared group ordering**. Hibernate Validator adds `@GroupSequenceProvider` and `DefaultGroupSequenceProvider<T>` to choose the default group sequence dynamically based on **object state**.

Business example: a record in draft state only needs minimal validation; once submitted for approval, detailed checks must also run. Consider:

- If the group list is decided by the **call flow**, you can use `validator.validate(bean, SomeGroup.class)` or `@Validated(SomeGroup.class)` at the boundary.
- If you must define a dynamic sequence from object state using the Hibernate extension, encapsulate the logic and write clear tests.
- When migrating to another provider, `@GroupSequenceProvider` is not guaranteed by Jakarta; you will need to redesign group selection.

### 7.5. Programmatic constraint mapping

Jakarta Validation supports annotations, standard XML mappings, and bootstrap hooks via `jakarta.validation.Configuration`. Hibernate Validator adds a fluent DSL:

```java
import jakarta.validation.Validation;
import org.hibernate.validator.HibernateValidator;
import org.hibernate.validator.HibernateValidatorConfiguration;
import org.hibernate.validator.cfg.ConstraintMapping;
import org.hibernate.validator.cfg.defs.NotNullDef;

HibernateValidatorConfiguration configuration =
        Validation.byProvider(HibernateValidator.class).configure();

ConstraintMapping mapping = configuration.createConstraintMapping();
mapping.type(Product.class)
       .field("sku")
       .constraint(new NotNullDef());

try (var factory =
        configuration.addMapping(mapping).buildValidatorFactory()) {
    var validator = factory.getValidator();
    // validator.validate(new Product(...))
}
```

This is an **illustrative configuration snippet**, assuming the project defines `Product` with field `sku`. It is not a standalone program. `ConstraintMapping`, `NotNullDef`, and `createConstraintMapping()`/`addMapping(ConstraintMapping)` are Hibernate Validator extensions.

Fluent mapping is useful when constraints depend on application metadata/configuration or when adding rules outside DTO sources. Switching providers may require moving to annotations, standard XML mappings, a custom provider adapter, or another configuration approach.

### 7.6. Dynamic payloads, message parameters, and extended context

Standard Jakarta Validation offers:

```java
ConstraintValidatorContext context;
context.buildConstraintViolationWithTemplate(
        "{app.invalid}").addConstraintViolation();
```

Hibernate Validator adds:

```java
import org.hibernate.validator.constraintvalidation
        .HibernateConstraintValidatorContext;

HibernateConstraintValidatorContext hvContext =
        context.unwrap(HibernateConstraintValidatorContext.class);

hvContext.addMessageParameter("limit", 5);
hvContext.disableDefaultConstraintViolation();
hvContext.buildConstraintViolationWithTemplate(
        "Value exceeds threshold {limit}")
    .addConstraintViolation();
```

This is **code inside `isValid` of a custom validator**. `{limit}` in the example does not come from the annotation, but is added via the `addMessageParameter` extension. On another provider, `unwrap(HibernateConstraintValidatorContext.class)` may fail.

Hibernate Validator also provides:

- `addExpressionVariable(...)` to expose variables to Expression Language (EL) when the appropriate EL mechanism is enabled;
- `withDynamicPayload(...)` to attach arbitrary data to a violation; consumers must use Hibernate Validator APIs to retrieve it;
- `getConstraintValidatorPayload(...)` to read configuration payload passed into the validator. **Constraint-validator payload** for controlling checks differs from **dynamic payload** attached to a violation;
- EL control for custom violations; these features require understanding EL security boundaries.

Do not confuse `payload()` of type `Class<? extends jakarta.validation.Payload>[]` on **standard Jakarta** annotations with Hibernate Validator's dynamic payload extension. They solve different problems.

## 8. How does Spring use the provider?

In Spring MVC, the common trigger is:

```java
@PostMapping("/candidates")
public ResponseEntity<Void> create(
        @Valid @RequestBody CandidateRequest request) {
    return ResponseEntity.noContent().build();
}
```

This is an **illustrative controller method** with imports `jakarta.validation.Valid`, `org.springframework.web.bind.annotation.*`, and `org.springframework.http.ResponseEntity`. If the DTO uses `@NotNull`, `@Size`, and portable custom constraints, the controller does not need to know the underlying provider. Spring MVC/Jakarta Validation runs checks after binding; errors can be represented via `BindingResult` or exception handling depending on parameter/method signatures.

### 8.1. LocalValidatorFactoryBean as the integration point

`LocalValidatorFactoryBean` in Spring Framework is the bridge between:

- `jakarta.validation.Validator`/`ValidatorFactory` on the Jakarta side;
- `org.springframework.validation.Validator` and Spring binding mechanisms.

It lets you configure the provider, message interpolator, constraint validator factory, and several standard SPIs. That **does not turn** `@Range` or `failFast(true)` into Jakarta APIs.

If a Spring Boot project already includes `spring-boot-starter-validation` and needs no customization, auto-configuration is preferred in most cases. Creating an extra `LocalValidatorFactoryBean` or standalone factory carelessly can leave controllers and services using **two differently configured validators**.

### 8.2. Two interfaces named Validator are not the same

```java
jakarta.validation.Validator
org.springframework.validation.Validator
```

- `jakarta.validation.Validator#validate(bean, groups...)` returns `Set<ConstraintViolation<T>>`.
- `org.springframework.validation.Validator#validate(Object, Errors)` records errors into `Errors`/`BindingResult` and has `supports(Class<?>)`.
- `LocalValidatorFactoryBean` bridges those two worlds.

Do not name a variable `validator` and assume methods from the other interface apply. When debugging, check the **fully qualified package** to verify which type is injected.

### 8.3. Spring's @Validated and Jakarta's groups

`@Validated` is a Spring annotation, while the **validation groups** concept belongs to Jakarta Validation. For example:

```java
public interface OnCreate {}

public record CandidateRequest(
    @NotNull(groups = OnCreate.class)
    String name
) {}
```

At a Spring boundary, `@Validated(OnCreate.class)` can trigger that group in the appropriate context. When calling the Jakarta API directly, use `validator.validate(bean, OnCreate.class)`. Both rely on **standard** groups; only the activation via Spring's annotation is Spring-specific.

A note on method validation: modern Spring MVC and AOP method validation can go through different mechanisms. Do not assume all errors surface as the same exception or that validation always runs merely because annotations are present on a DTO.

### 8.4. Configuring vendor properties in Spring

If you enable `hibernate.validator.fail_fast` through Spring/Jakarta configuration, treat it as a decision tied to **Hibernate Validator**. `LocalValidatorFactoryBean` can accept validation properties from the application; **the property names and semantics are not part of the Jakarta spec**.

If you replace the provider, review configuration keys, exception types, message translations, groups, and response logic. Do not infer from the application starting up that the new provider applied equivalent settings.

## 9. Bootstrap, unwrap, and provider substitutability

### 9.1. Standard bootstrap

```java
try (ValidatorFactory factory =
        Validation.buildDefaultValidatorFactory()) {
    var validator = factory.getValidator();
    var violations = validator.validate(bean);
}
```

This illustrative snippet assumes a `bean` variable exists. `Validation`, `ValidatorFactory`, and `validate` belong to the Jakarta standard. Providers are discovered via SPI, typically through `META-INF/services/jakarta.validation.spi.ValidationProvider`.

If **no provider exists**, `buildDefaultValidatorFactory()` can throw `NoProviderFoundException`. If multiple providers sit on the classpath, do not rely on an unguaranteed discovery order; choose the provider explicitly when runtime behavior must be deterministic.

### 9.2. Selecting a specific provider

```java
try (ValidatorFactory factory =
        Validation.byProvider(HibernateValidator.class)
                .configure()
                .buildValidatorFactory()) {
    // Explicitly selects Hibernate Validator as the provider.
}
```

`Validation.byProvider(...)` itself is a **standard** bootstrap mechanism; the argument `HibernateValidator.class` is a concrete provider class. This is an intentional coupling point.

### 9.3. Unwrap is standard, but its result may not be portable

```java
var hvFactory = factory.unwrap(
        org.hibernate.validator.HibernateValidatorFactory.class);
```

`unwrap(Class<T>)` belongs to Jakarta. The target type `HibernateValidatorFactory` is Hibernate-specific. When running a provider that does not support that type, `unwrap` can throw `ValidationException`. Hence “accessing via `unwrap`” **does not automatically make an extension portable**.

A helpful design pattern:

- Core/domain: data and constraints use only Jakarta APIs.
- Adapter/framework: Spring MVC handling, client error mapping.
- Provider configuration: parts needing `HibernateValidatorConfiguration`, `ConstraintMapping`, or custom contexts.
- Tests: lock down behavior at boundaries that affect users.

Small applications do not have to split into separate physical modules, but dependency boundaries should be easy to recognize when reading code.

## 10. Tests to detect provider lock-in

With the demo in section 5, you can test violation counts rather than checking “which error appeared first”.

File `src/test/java/com/example/validationdemo/ValidationPortabilityTest.java`:

```java
package com.example.validationdemo;

import jakarta.validation.Validation;
import jakarta.validation.ValidatorFactory;
import org.hibernate.validator.HibernateValidator;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ValidationPortabilityTest {

    private final ValidationComparisonApplication.Candidate invalid =
            new ValidationComparisonApplication.Candidate(null, 16);

    @Test
    void standardBootstrapReportsBothViolations() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            assertEquals(
                    2,
                    factory.getValidator().validate(invalid).size()
            );
        }
    }

    @Test
    void hibernateFailFastReportsExactlyOneViolation() {
        try (ValidatorFactory factory =
                Validation.byProvider(HibernateValidator.class)
                        .configure()
                        .failFast(true)
                        .buildValidatorFactory()) {
            assertEquals(
                    1,
                    factory.getValidator().validate(invalid).size()
            );
        }
    }
}
```

Run:

```bash
./gradlew test
```

Expect both tests to PASS with the dependencies configured in section 5. They verify **behavior on the current Hibernate Validator**. They are **not yet** proof that the module genuinely supports another provider because the test runtime still uses Hibernate Validator.

To verify real portability:

1. Build the **core module** against only the Jakarta Validation API, with no compile dependency on `org.hibernate.validator.*` packages (separating extension demos out of the core module).
2. Swap the runtime provider for a compatible implementation of the same Jakarta Validation version; re-run tests for custom constraints, groups, cascading, messages, and exception mapping.
3. Isolate tests depending on Hibernate-specific behavior into a separate profile/module.
4. Assert **business outcomes**, not raw message strings or `Set<ConstraintViolation<?>>` order; do not assume every provider has identical default messages.
5. Add tests for areas prone to divergence: container element validation, temporal rules with `ClockProvider`, XML mappings, custom validator factories, and EL.
6. For accepted extensions, document the minimum provider version and upgrade policy in the module docs.

If an application intentionally commits to Hibernate Validator and benefits from its extensions, the right test outcome is **transparent dependency coupling**, not blindly deleting useful vendor APIs.

## 11. Common misconceptions

**Misconception 1 — Calling all annotations in Hibernate Validator Hibernate-specific.** `@NotNull`, `@Size`, `@NotBlank`, and `@Email` are all Jakarta Validation in current generations. Using Hibernate Validator as the provider does not make them non-standard.

**Misconception 2 — Seeing the `jakarta.validation` package and claiming runtime provider independence.** Configuration might still set `hibernate.validator.fail_fast`, custom validators might `unwrap` into Hibernate contexts, or a module might depend on implementation-specific default behaviors. You must check source, bootstrap, config, and tests.

**Misconception 3 — Treating Spring `@Validated` as a Hibernate extension.** It is a Spring integration point; the underlying provider simply runs validation through the Jakarta API. The annotation can pass standard groups, yet the annotation itself is not part of Jakarta.

**Misconception 4 — Thinking `@ReportAsSingleViolation` is Hibernate-specific.** It is a Jakarta annotation; conversely, `@ConstraintComposition(OR)` is a Hibernate Validator extension.

**Misconception 5 — Enabling fail-fast and relying on error order.** There is no guarantee which constraint runs first. If you need phased ordering, use standard groups and `@GroupSequence` as intended, not fail-fast.

**Misconception 6 — Replacing `@Range` with `@Min`/`@Max` without checking API responses.** Value-range validity may be equivalent, but violation count, message keys, paths, and metadata can change. Re-test client contract compatibility.

**Misconception 7 — Mixing `javax.validation` and `jakarta.validation`.** Spring Boot 3 uses Jakarta; many legacy Spring Boot 2 examples use javax. The two namespaces cannot simply be swapped by renaming imports without matching dependencies/providers.

**Misconception 8 — Creating a `ValidatorFactory` inside the request loop.** Providers parse metadata, configure, and cache. Use an application-lifecycle-managed factory; manual bootstrapping in the article is only for illustrating differences.

**Misconception 9 — Using `org.hibernate.validator.internal.*` classes.** Internal APIs carry no compatibility guarantee across upgrades; even when extensions are accepted, stick to documented public APIs.

**Misconception 10 — Using dynamic payloads/EL to embed sensitive data in messages.** This extension is powerful but unnecessary for routine errors. Keep templates static, use controlled parameters, and never expose secrets in client responses.

**Misconception 11 — Treating the validation API as a substitute for business invariants.** Boundary validation is useful for input errors; conditions requiring transactions, permissions, or current database state must still be enforced at the domain/service and persistence layers as appropriate.

## 12. Decision checklist

When adding a validation rule or configuration:

1. **Look for a Jakarta option first.** Do `@NotNull`, `@Size`, `@Min`/`@Max`, groups, `@Valid`, custom `@Constraint`, `ValueExtractor`, and standard SPIs cover it?
2. **If an extension is required**, identify the exact provider class/property; justify the concrete benefit such as fail-fast, DSL mapping, or specialized constraints.
3. **Inspect code and dependencies.** `jakarta.validation` vs `org.hibernate.validator` vs `org.springframework.validation`; never guess from simple names alone.
4. **Define dependency boundaries.** Can core logic be shared independently, or does the whole application accept Hibernate Validator?
5. **Protect external contracts.** Error codes, property paths, HTTP status, and validity conditions matter more than message order or provider internals.
6. **Test valid/invalid cases, boundaries, and configuration.** Cover fail-fast, groups, message interpolation, container elements, custom validators, and Spring binding.
7. **When upgrading/swapping providers**, consult the Jakarta Validation–provider–Spring Boot compatibility matrix; run tests before moving to production.

### Quick decision guide

| Need | Default choice |
| --- | --- |
| Required, length, numeric range | Jakarta constraints (`@NotNull`, `@Size`, `@Min`/`@Max`) |
| Cross-field relation, SKU rule | Custom `@Constraint` + `ConstraintValidator` using Jakarta |
| Want all errors returned at once | Standard validator behavior, normalize violation list |
| Want to stop at first error for optimization | Hibernate `failFast(true)`, noting coupling and unguaranteed order |
| Want ordered group validation | Standard `@GroupSequence` |
| Want dynamic Default groups by bean state | Hibernate `@GroupSequenceProvider` or redesign check flow |
| Want constraints without editing annotations | Standard XML mapping; if fluent DSL is needed, Hibernate `ConstraintMapping` |
| Want messages with property paths | Standard `ConstraintValidatorContext` |
| Want advanced message parameters/dynamic payloads | Hibernate context, only when genuinely needed |
| Want request/body/form integration in Spring | `@Valid`, `@Validated`, `LocalValidatorFactoryBean`, and Spring error handling |

**Core takeaway:** `jakarta.validation.*` is the **standard contract**; Hibernate Validator is a **provider implementing** that contract and offering extra vendor features; Spring Framework is the **integration layer** between validation and the application. Keep these boundaries explicit in your design, depend on extensions only when the payoff is worthwhile, and protect behavior with tests.

## References

- [Jakarta Validation 3.0 Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html) — standard contracts, bootstrap, constraints, groups, metadata, and SPIs.
- [Jakarta Validation API](https://jakarta.ee/specifications/platform/10/apidocs/jakarta/validation/package-summary) — look up exact standard packages/interfaces.
- [Hibernate Validator 8 Reference Guide](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/) — “Hibernate Validator Specifics” chapter, fail-fast, programmatic mapping, composition, context extensions.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html) — Jakarta Validation integration.
- [Spring Framework — LocalValidatorFactoryBean](https://docs.spring.io/spring-framework/docs/6.2.10/javadoc-api/org/springframework/validation/beanvalidation/LocalValidatorFactoryBean.html) — adapter and configuration hooks.
