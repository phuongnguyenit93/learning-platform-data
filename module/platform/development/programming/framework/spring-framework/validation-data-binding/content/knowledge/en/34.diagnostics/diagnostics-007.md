# `UnexpectedTypeException` Caused by Constraints Not Supporting the Target Data Type in Spring Validation

## 1. Recognizing the Error: `HV000030` Is Not an Ordinary Input Error

When running an API using `@Valid`, you may encounter a stack trace like:

```text
jakarta.validation.UnexpectedTypeException:
HV000030: No validator could be found for constraint
'jakarta.validation.constraints.NotBlank'
validating type 'java.lang.Integer'.
Check configuration for 'quantity'
```

This is a **Hibernate Validator message template**, not actual stdout captured from a run in this article. The code `HV000030` is a **Hibernate Validator log/exception code**, not an HTTP status or a Jakarta standard requirement for other providers.

Code that can trigger this error:

```java
public record CreateOrderRequest(
        @NotBlank Integer quantity) {
}
```

The code above **compiles in Java**, yet declares a constraint on the wrong data type: `@NotBlank` is designed for `CharSequence`, whereas `Integer` is not a `CharSequence`.

When Bean Validation evaluates the constraint, the provider searches for a `ConstraintValidator<NotBlank, T>` capable of handling the declared type of `quantity`. If no compatible validator exists, the provider throws **`jakarta.validation.UnexpectedTypeException`** instead of returning a `ConstraintViolation` as it would when an actual value fails validation.

The proper fix:

```java
public record CreateOrderRequest(
        @NotNull @Min(1) Integer quantity) {
}
```

- `@NotNull`: quantity must be present.
- `@Min(1)`: numeric value must be greater than or equal to 1.
- `Integer`: proper data type for arithmetic and numeric comparison.
- Never attach `@NotBlank` merely to express "a required number."

**This article belongs to the Diagnostics section** of the **Spring Framework — validation-data-binding** module. Its goal is to distinguish type-mismatched constraint declarations from constraint-violating input, understand how Jakarta Validation selects validators, and fix issues thoroughly across DTOs, collections, custom constraints, and Spring MVC. Examples use **Java 17+ / Spring Boot 3.4.5 / Spring MVC / Hibernate Validator 8**.

## 2. Nature of `UnexpectedTypeException`

### 2.1. The System Has a Constraint, Yet Cannot Find a Matching Validator

Jakarta Bean Validation defines that a constraint annotation, such as `@NotBlank`, is bound to one or more implementations of `ConstraintValidator<A, T>`.

- `A`: constraint annotation type.
- `T`: value type validated by the implementation.
- The Bean Validation provider selects a validator based on **the declared type of the constrained element**, factoring in subtype rules, primitives/wrappers, and value extraction where applicable.
- **No compatible validator:** throws `UnexpectedTypeException`.
- **Multiple compatible validators with no single most-specific choice:** can also throw `UnexpectedTypeException`.
- **One compatible validator:** invokes `isValid(...)` returning `true` or `false`.

Mental model:

```text
Constraint attached to field/parameter
                |
                v
Determine declared type of element under validation
                |
                v
Collect ConstraintValidators for the annotation
                |
                v
Is there a single most-specific compatible validator?
           /                      \
          No                      Yes
          |                         |
          v                         v
UnexpectedTypeException       Call isValid(value)
                                  /       \
                               false       true
                                 |           |
                                 v           v
                          ConstraintViolation  valid
```

**Key point:** the error "no validator for data type" does not mean the field's value is **invalid**. It means **the specification of how to validate the field is wrong**.

### 2.2. Where Does This Exception Sit in the Hierarchy?

In Jakarta Validation 3.x:

```text
java.lang.RuntimeException
└── jakarta.validation.ValidationException
    └── jakarta.validation.ConstraintDeclarationException
        └── jakarta.validation.UnexpectedTypeException
```

`UnexpectedTypeException` is not `ConstraintViolationException`. `ConstraintViolationException` typically represents a set of violations in method/JPA environments or when an application throws it explicitly; `UnexpectedTypeException` reports that the provider could not resolve a suitable validator.

A direct call:

```java
Set<ConstraintViolation<CreateOrderRequest>> errors =
        validator.validate(new CreateOrderRequest(0));
```

With the **fixed** DTO using `@NotNull @Min(1)`, the provider returns a set containing a violation for `quantity`. With the **broken** DTO using `@NotBlank Integer`, `validate(...)` itself throws the exception before any violation set is returned.

This explains why a Spring MVC handler may never enter the `BindingResult.hasErrors()` branch: the provider **could not complete validation** to translate violations into field errors.

### 2.3. Not a Java Compilation Error

The Java compiler checks whether an annotation is permitted at a location by its `@Target`—such as FIELD, METHOD, PARAMETER, TYPE_USE, or RECORD_COMPONENT—but **does not enforce Bean Validation's type-compatibility rules**.

For example, `@Size(min=1) Integer count` compiles because `@Size` permits placement on fields/record components; only at runtime when the provider resolves a validator does it discover `Integer` has no size concept supported by the standard validators.

Some static-analysis tools or the Hibernate Validator Annotation Processor can warn early, yet **you must not assume every build's compiler fails before runtime**.

## 3. Constraint Selection Table by Data Type

| Purpose | Java Type | Typically Suitable Constraint | Mistake Causing `UnexpectedTypeException` |
| --- | --- | --- | --- |
| Require non-null reference | `Integer`, `Long`, `String`, object | `@NotNull` | Using `@NotBlank` on `Integer` |
| Non-blank string | `String` / `CharSequence` | `@NotBlank` | Using `@NotBlank` on `List` |
| Non-empty collection/array/map | `List`, `Set`, `Map`, array | `@NotEmpty` | Using `@NotBlank` on collection |
| String length | `String` | `@Size(min=..., max=...)` | Using `@Size` on `Integer` to check "digit count" |
| Collection size | `List`, `Set`, `Map`, array | `@Size(min=..., max=...)` | Using `@Min` on a list |
| Minimum numeric value | `Integer`, `Long`, `BigDecimal`... | `@Min` / `@DecimalMin` | Using `@Size` on numbers |
| Positive numeric value | Numeric types | `@Positive` | Using `@NotBlank` on numbers |
| Regex pattern | `CharSequence` | `@Pattern` | Using `@Pattern` on `Long` |
| Formatted email | `String` / `CharSequence` | `@Email`, often with `@NotBlank` | Using `@Email` on `Integer` |
| Future date/time | `Instant`, `LocalDate`, supported temporal types | `@Future` / `@FutureOrPresent` | Using `@Future` on an unconverted timestamp string |
| Past date/time | Supported temporal types | `@Past` / `@PastOrPresent` | Using `@Past` on `String` |
| Validate nested bean | Domain/command object | `@Valid` on association/element | Using `@NotBlank` directly on a bean |

**Supported types may vary across providers/versions.** For example, Hibernate Validator supports `@Min` or `@Positive` on certain numeric `CharSequence` values as an extension, even though you should normally deserialize into a numeric type in the DTO. Avoid claiming "`@Min String` always throws `UnexpectedTypeException`" when Hibernate Validator may support it. Consult the **supported data types** table in the documentation for your active provider.

### 3.1. `@NotNull`, `@NotEmpty`, and `@NotBlank` Are Not Interchangeable

```java
// Correct: Integer is a reference that must have a value.
@NotNull
Integer quantity;

// Correct: String must contain non-whitespace content.
@NotBlank
String customerName;

// Correct: list must contain elements.
@NotEmpty
List<String> tags;

// Correct: validates each String element.
@NotEmpty
List<@NotBlank String> tags2;
```

These are **field fragments**, not a complete class. The annotations differ in scope:

- `@NotNull` ignores empty strings or empty lists; it only forbids null.
- `@NotEmpty` forbids null/empty on supported strings, collections, maps, or arrays.
- `@NotBlank` requires a `CharSequence` with at least one non-whitespace character per the validator; it does not apply to a collection as a whole object.
- `@NotEmpty List<@NotBlank String>` combines **container size** and **element value** to express the exact intent.

If `quantity` is primitive `int`, it cannot hold null; `@NotNull int quantity` will not detect "the client omitted the field" when binding defaults to 0. For HTTP inputs where missing values must be distinguished from 0, use `Integer` with `@NotNull` and a numeric constraint, while understanding Jackson/argument-binder behavior.

### 3.2. `@Size` on a Number Does Not Check Digit Count

Wrong:

```java
@Size(min = 1, max = 3)
Integer code;
```

`@Size` measures the "size" of a `CharSequence`, `Collection`, `Map`, or array. An `Integer` has no `length()`/`size()` supported by `@Size`.

If business rules require **a numeric value from 1 to 999**, use:

```java
@NotNull
@Min(1)
@Max(999)
Integer code;
```

If business rules require **exactly three digits** allowing leading zeros such as `"007"`, that is a **string identifier**, not an arithmetic number:

```java
@NotBlank
@Pattern(regexp = "[0-9]{3}")
String code;
```

If business rules constrain integer/fractional digit counts of a numeric value, consider `@Digits(integer=..., fraction=...)` per its semantics and numeric type. Do not mechanically swap `@Size` for `@Digits` when the business rule truly requires a **range**.

### 3.3. `@Future` on a `String` Does Not Auto-Parse ISO Timestamps

Wrong:

```java
@Future
String departureAt;
```

A `String` that looks like a timestamp such as `"2031-04-02T09:00:00Z"` **still has declared type `String`**. Standard `@Future` applies to provider-supported temporal types and does not treat `String` as an `Instant`.

Correct:

```java
@NotNull
@Future
Instant departureAt;
```

When an API receives JSON, Jackson must deserialize the JSON string into `Instant` first. If the timestamp has invalid syntax, the failure occurs during **HTTP message conversion** as `HttpMessageNotReadableException`, not `UnexpectedTypeException`.

### 3.4. `@Pattern` on `Long` Does Not Auto-Stringify to Match Regex

Wrong:

```java
@Pattern(regexp = "[0-9]{10}")
Long phoneNumber;
```

If a phone number is an identifier with leading zeros, plus signs, or country codes and is never used in arithmetic, use `String`:

```java
@NotBlank
@Pattern(regexp = "\\+?[0-9]{8,15}")
String phoneNumber;
```

In certain cases you could write a custom validator for a numeric type, yet never put `@Pattern` on `Long` expecting Bean Validation to call `toString()`.

## 4. Reading `HV000030` Messages Systematically

Illustrative example:

```text
HV000030: No validator could be found for constraint
'jakarta.validation.constraints.Size'
validating type 'java.lang.Integer'.
Check configuration for 'maxAttempts'
```

Read it in three parts:

1. **Constraint:** `jakarta.validation.constraints.Size` — which annotation is being evaluated?
2. **Validated type:** `java.lang.Integer` — does the declared type of the field/element match that annotation?
3. **Property path:** `maxAttempts` — where in the model/DTO the provider is currently looking.

Checklist:

- Open the exact Java class/record mentioned; verify whether `maxAttempts` is `Integer`, `Long`, `String`, `List`, or another type.
- Check whether the annotation sits on a **field**, **getter**, **record component**, **method parameter**, **return value**, or **container element**.
- Read the supported-types documentation for that specific constraint.
- Check superclasses/interfaces or nested DTOs if the annotation is inherited or cascaded.
- Check custom validators registered via `@Constraint(validatedBy=...)`, XML, or programmatic mappings.
- Fix the **constraint model** to fit the semantics rather than merely catching and ignoring the exception.

**Do not hard-parse `HV000030` log strings to infer root causes across providers.** The code and message format are Hibernate Validator internals; rely on exception class for classification, and inspect property/annotation/type in the stack trace and code review to fix it.

### 4.1. When Does the Error Surface?

Not necessarily at Spring Boot startup. The Jakarta Validation specification allows the error to surface when:

- The provider validates a bean via `Validator#validate(...)`.
- A property is validated via `validateProperty(...)` or `validateValue(...)`.
- Method/constructor parameter or return-value validation runs.
- A nested bean is cascade-validated.
- The provider builds metadata for a bean with an invalid declaration.

Consequently, an API may boot normally and happy-path tests may pass, yet **only when touching a specific DTO or validation group** does `UnexpectedTypeException` occur. That is why tests should cover all declared groups and input structures.

### 4.2. Why Testing `null` Does Not Prove an Annotation Is Valid

Constraints often return true for null so `@NotNull` stays orthogonal, yet **a type-incompatible declaration can be rejected during provider validator resolution even before `isValid` runs on any value**. Never use "passing null did not throw" (if observed in some setup) as proof that `@NotBlank Integer` is valid.

## 5. How `ConstraintValidator` Selection Works by Declared Type

### 5.1. Generic Signature Governs Supported Types

A custom constraint implementation:

```java
public final class StartsWithValidator
        implements ConstraintValidator<StartsWith, CharSequence> {

    @Override
    public boolean isValid(
            CharSequence value,
            ConstraintValidatorContext context) {
        // ...
        return true;
    }
}
```

This is a **fragment**; runnable code for `@StartsWith` appears in Section 8. The provider sees that this implementation can validate **`CharSequence` and compatible subtypes**, such as `String`.

If declared as:

```java
@StartsWith("SKU-")
Integer sku;
```

the provider cannot use `ConstraintValidator<StartsWith, CharSequence>` for `Integer`. It will not convert `Integer` to `String` to satisfy the generic type; misapplying the annotation results in `UnexpectedTypeException`.

### 5.2. The Provider Selects by Declared Type, Not Arbitrary Runtime Subtype

For instance, a custom validator supporting only `String`:

```java
class OnlyStringValidator
        implements ConstraintValidator<MyConstraint, String> {
    // ...
}
```

This illustrative fragment omits `MyConstraint`. If a field is declared as `CharSequence value`, even if the runtime instance is a `String`, having only a `String` validator does not satisfy **declared type `CharSequence`**. Compatibility rules use the annotated element's declared target type rather than opportunistically casting runtime values.

This matters especially when refactoring a DTO field from `String` to an interface/base type or when a custom constraint has multiple implementations.

### 5.3. Both "No Validator" and "Too Many Validators" Can Cause `UnexpectedTypeException`

The Jakarta specification selects the **most specific** compatible validator. If:

- No validator supports the target type ⇒ cannot validate.
- Two implementations both support the target type, yet their supported types have no subtype hierarchy placing one as uniquely most specific ⇒ cannot pick a single winner.

Conceptually, suppose a class implements both `Serializable` and a custom interface, and a custom annotation has validators for both unrelated interfaces. When both match, resolution is **ambiguous**. Never rely on guessing that the provider picks by declaration order in `validatedBy`; declaration order does not resolve ambiguity.

**Resolution approach:** define non-overlapping validators; use a validator targeting a truly appropriate base type or add a uniquely most-specific implementation when semantics permit. You may need to split the annotation if one constraint name is trying to cover unrelated domain concepts.

### 5.4. Do Not Try to Fix It by Casting Inside `isValid()`

If the provider cannot select a validator, `isValid(...)` may **never be invoked**. Writing code like:

```java
String text = String.valueOf(value);
```

inside a validator accepting only `CharSequence` does not make it support `Integer`. You must align the validator's generic type with the target or update the field/annotation.

## 6. Configuration Errors vs. Value Errors vs. Conversion Errors

| Scenario | Where it happens | Typical behavior |
| --- | --- | --- |
| `@NotBlank Integer quantity` | Jakarta constraint resolution | **`UnexpectedTypeException`** |
| `@Min(1) Integer quantity = 0` | `isValid(...)` returns false | **`ConstraintViolation`** / `FieldError` |
| `@NotNull Integer quantity = null` | `isValid(...)` returns false | **`ConstraintViolation`** / `FieldError` |
| Form `quantity=abc` into `Integer` | Spring property conversion | Often `FieldError.isBindingFailure() == true` |
| JSON `{"quantity":{}}` into `Integer` | Jackson HTTP message converter | Typically `HttpMessageNotReadableException` |
| Custom `ConstraintValidator#isValid()` throws bug exception | Validator runtime | May be wrapped in `ValidationException` |
| Constraint annotation has invalid metadata | Bean Validation definition | `ConstraintDefinitionException` |
| Cascaded validation/parameter declaration violates rules | Bean Validation declaration | `ConstraintDeclarationException` or subtype |
| Multiple matching validators ambiguous | ConstraintValidator resolution | **`UnexpectedTypeException`** |

Three paths to distinguish when diagnosing REST APIs:

**A. Value violates constraint:** returns violations ⇒ Spring MVC normally populates `BindingResult` or throws `MethodArgumentNotValidException` ⇒ HTTP 400 per standard contract.

**B. JSON/form could not convert to DTO:** message conversion or binding failure ⇒ handle per its respective error source.

**C. Constraint placed on incompatible type:** provider cannot run validation properly ⇒ configuration/implementation bug; **do not convert it into a client 400 error** and hide a server bug.

### 6.1. HTTP 500 on a Misdeclared Constraint Does Not Mean the Request Is "Malicious"

A misplaced `@NotBlank Integer` is a **server-side programming bug**. Even a completely valid request such as `{"quantity":2}` can cause the validator to throw. Without a dedicated handler for `UnexpectedTypeException` in Spring MVC, the unhandled error typically travels down the **5xx** path.

When investigating, inspect controlled server logs/stack traces, identify the annotation, and fix the code. If a global 5xx fallback is mandatory, return a safe 5xx payload such as `INTERNAL_VALIDATION_CONFIGURATION_ERROR` or `INTERNAL_ERROR`, alert on it, and keep detailed traces in logs. **Never catch `UnexpectedTypeException` and return 400 `INPUT_INVALID`.**

### 6.2. `BindingResult` Cannot Populate Results If the Provider Cannot Validate

In a controller:

```java
@PostMapping("/order")
public String submit(
        @Valid @ModelAttribute("form") OrderForm form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return "form";
    }
    return "done";
}
```

This is a fragment. If `OrderForm` contains `@NotBlank Integer quantity`, Spring can throw `UnexpectedTypeException` while invoking the provider, **before the handler is ever entered**. Having `BindingResult` immediately after the DTO is syntactically valid, yet it cannot turn an invalid constraint declaration into a field violation.

**Right diagnosis:** if the stack trace shows `UnexpectedTypeException`, focus on annotations/types; do not confuse it with a misplaced `BindingResult` (which is a separate MVC issue).

## 7. Nested Structures and Container Elements

### 7.1. `@NotBlank` on an Entire `List` Is Wrong

Wrong:

```java
public record SearchRequest(
        @NotBlank List<String> keywords) {
}
```

For "non-empty list," use `@NotEmpty`:

```java
public record SearchRequest(
        @NotEmpty List<String> keywords) {
}
```

For "non-empty list where each element is a non-blank string," use **both levels**:

```java
public record SearchRequest(
        @NotEmpty List<@NotBlank String> keywords) {
}
```

`@NotEmpty` evaluates the `List` container; `@NotBlank` evaluates each `String` (supported by the provider via container element constraints). Writing `List<@NotBlank Integer>` will cause the provider to throw `UnexpectedTypeException` when validating the `Integer` element type.

### 7.2. `Map` Keys/Values Must Match Constraints on Each Side

A DTO:

```java
public record SettingsRequest(
        @NotEmpty
        Map<@NotBlank String, @NotNull Integer> settings) {
}
```

Meaning:

- `@NotEmpty` checks that the Map is non-null and non-empty.
- `@NotBlank` checks that each **`String` key** is non-blank.
- `@NotNull` checks that each **`Integer` value** is non-null.

This fragment requires importing `java.util.Map` and Jakarta constraints. To require positive values, add `@Positive` or `@Min(1)` on `Integer`—**never** put `@NotBlank` on numeric values.

### 7.3. Nested Objects: Use `@Valid` to Cascade, Constraints on Individual Fields

Wrong:

```java
public record Order(
        @NotBlank Address shippingAddress) {
}
```

`Address` is a Java bean/domain object, not a `CharSequence`. Better:

```java
public record Address(
        @NotBlank String street) {
}

public record Order(
        @NotNull @Valid Address shippingAddress) {
}
```

This fragment requires imports and records in an appropriate package. `@Valid` instructs the provider to descend into `Address.street`, while `@NotNull` requires `shippingAddress` itself to be present. Note that `@Valid` does not forbid null on its own; null references are typically skipped during cascade.

### 7.4. `Optional` and Value Extraction

Wrapper types such as `Optional<String>` rely on **value extraction** in Jakarta Validation/Hibernate Validator. A constraint on the container and a constraint on the type argument are **not always equivalent**. For example:

```java
Optional<@NotBlank String> nickname;
```

This is a fragment. The provider needs a value extractor supporting `Optional` to apply the constraint to the contained element. Custom wrappers lacking an extractor or having ambiguous unwrapping can trigger `ConstraintDeclarationException` about value extraction, not necessarily `HV000030`.

Do not "fix" every container error by slapping on `@Valid` or casting `Optional` to `String`. Identify **whether the constraint applies to container or element**, which extractors exist, and the declared element type.

### 7.5. Constraints on Record Components

Java records support Bean Validation annotations on components and constructor-related declarations depending on the annotation's `@Target`. This does not make `@NotBlank Integer` valid; records go through the exact same validator resolution.

Always test new record DTOs and fields refactored from `String` to `Integer`/enum; **changing a field's type while forgetting to update its annotation** is one of the most common sources of this error.

## 8. Complete Maven Java 17 Project: Broken, Fixed, and Tested

We build a small Spring Boot MVC project featuring:

1. Misconfigured DTOs **used solely in unit tests** to demonstrate `UnexpectedTypeException` without exposing broken endpoints in production code.
2. Proper DTO using `@NotBlank` on `String`, `@NotNull @Min(1)` on `Integer`, and `@NotEmpty List<@NotBlank String>`.
3. A custom `@StartsWith` constraint using `ConstraintValidator<StartsWith, CharSequence>`, showing generic type matching.
4. REST endpoint `POST /items` accepting `@Valid @RequestBody ItemRequest`, returning 201 when valid and 400 with error codes when invalid.
5. Unit tests proving **wrong type => exception** and **right type, invalid value => violation**.
6. `MockMvc` integration tests proving MVC uses the provider and error handling properly, including undeserializable JSON.

### 8.1. Directory Structure

```text
unexpected-type-demo/
├── pom.xml
└── src/
    ├── main/java/demo/
    │   ├── UnexpectedTypeApplication.java
    │   ├── StartsWith.java
    │   ├── StartsWithValidator.java
    │   ├── ItemRequest.java
    │   ├── ItemController.java
    │   └── InputErrorAdvice.java
    └── test/java/demo/
        ├── ConstraintTypeTest.java
        └── ItemControllerTest.java
```

### 8.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>unexpected-type-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-validation</artifactId>
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

`spring-boot-starter-validation` provides Hibernate Validator aligned with Spring Boot 3.4.x; do not mix legacy `javax.validation.*` APIs with Boot 3.x `jakarta.validation.*`.

### 8.3. `src/main/java/demo/UnexpectedTypeApplication.java`

```java
package demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class UnexpectedTypeApplication {
    public static void main(String[] args) {
        SpringApplication.run(
                UnexpectedTypeApplication.class, args);
    }
}
```

### 8.4. `src/main/java/demo/StartsWith.java`

```java
package demo;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Target({
        ElementType.FIELD,
        ElementType.METHOD,
        ElementType.PARAMETER,
        ElementType.RECORD_COMPONENT,
        ElementType.ANNOTATION_TYPE,
        ElementType.TYPE_USE
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = StartsWithValidator.class)
public @interface StartsWith {

    String value();

    String message()
            default "must start with the configured prefix";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

A valid custom constraint requires appropriate annotation metadata:

- `@Target` specifies where the annotation may be applied.
- `@Retention(RUNTIME)` ensures the provider can read the annotation during validation.
- `@Constraint(validatedBy=...)` declares implementation(s).
- `message`, `groups`, and `payload` follow Jakarta constraint definition requirements.
- `value()` is a custom attribute holding the required prefix.

Including `TYPE_USE` in `@Target` enables use on container elements such as `List<@StartsWith("SKU-") String>`; the element type must still be supported by the validator.

### 8.5. `src/main/java/demo/StartsWithValidator.java`

```java
package demo;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class StartsWithValidator
        implements ConstraintValidator<StartsWith, CharSequence> {

    private String expectedPrefix;

    @Override
    public void initialize(StartsWith annotation) {
        expectedPrefix = annotation.value();
    }

    @Override
    public boolean isValid(
            CharSequence value,
            ConstraintValidatorContext context) {

        // @NotNull is used separately when the field is required.
        if (value == null) {
            return true;
        }

        return value.toString()
                .startsWith(expectedPrefix);
    }
}
```

**Key takeaways:**

- Generic type `CharSequence` is compatible with `String` fields.
- It is incompatible with `Integer` fields; the provider does not automatically call `toString()` before validator selection.
- If business rules require non-empty content, combine with `@NotBlank`.
- `initialize(...)` receives configuration per annotation instance; `isValid(...)` must be thread-safe and never mutate shared request state inside the validator.
- The code performs no external I/O and needs no Spring DI, making it a clean standalone constraint example.

If custom logic must validate an enum, write a `ConstraintValidator<YourConstraint, YourEnum>` or a model-level class constraint—never stick a `String` annotation on an enum hoping "the provider will figure it out."

### 8.6. `src/main/java/demo/ItemRequest.java`

```java
package demo;

import java.util.List;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;

public record ItemRequest(

        @NotBlank
        @StartsWith("SKU-")
        String sku,

        @NotNull
        @Min(1)
        Integer quantity,

        @NotEmpty
        List<@NotBlank String> tags
) {
}
```

**Type-matched annotation design:**

- `sku` is `String`, so both `@NotBlank` and custom `@StartsWith` (`CharSequence`) support it.
- `quantity` is `Integer`, so `@NotNull` and `@Min(1)` support it.
- `tags` is `List`, so `@NotEmpty` applies to the collection.
- `@NotBlank` sits **on the `String` type argument** to check each tag, not on the `List`.

From JSON `{"sku":"SKU-1","quantity":2,"tags":["spring"]}`, Jackson constructs the record and Jakarta Validator evaluates each constraint. In this demo, a null SKU is checked by `@NotBlank`, while the custom validator intentionally treats null as valid to avoid overlapping responsibilities.

### 8.7. `src/main/java/demo/ItemController.java`

```java
package demo;

import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class ItemController {

    @PostMapping("/items")
    public ResponseEntity<Map<String, Object>> create(
            @Valid @RequestBody ItemRequest request) {

        // Runs only when JSON deserializes cleanly
        // and all DTO constraints pass.
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(Map.of(
                        "status", "accepted",
                        "sku", request.sku(),
                        "quantity", request.quantity(),
                        "tagCount", request.tags().size()
                ));
    }
}
```

No direct method constraints are declared on the handler parameter, only `@Valid`; in Spring MVC 6.x, individual argument validation is the typical path here. If DTO constraints fail, `MethodArgumentNotValidException` is normally thrown; if JSON cannot be read, the converter throws `HttpMessageNotReadableException`.

**Never add an endpoint intentionally using `@NotBlank Integer` in production code.** Broken declarations belong in isolated unit tests for learning so real users never hit unnecessary 5xx errors.

### 8.8. `src/main/java/demo/InputErrorAdvice.java`

```java
package demo;

import java.util.List;

import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.context.request.WebRequest;
import org.springframework.web.servlet.mvc.method.annotation
        .ResponseEntityExceptionHandler;

@RestControllerAdvice
public class InputErrorAdvice
        extends ResponseEntityExceptionHandler {

    public record ErrorBody(
            String code,
            List<String> fields) {
    }

    @Override
    protected ResponseEntity<Object>
            handleMethodArgumentNotValid(
                    MethodArgumentNotValidException ex,
                    HttpHeaders headers,
                    HttpStatusCode status,
                    WebRequest request) {

        List<String> fields = ex.getBindingResult()
                .getFieldErrors()
                .stream()
                .map(FieldError::getField)
                .distinct()
                .sorted()
                .toList();

        return new ResponseEntity<>(
                new ErrorBody("INPUT_INVALID", fields),
                headers,
                status
        );
    }

    @Override
    protected ResponseEntity<Object>
            handleHttpMessageNotReadable(
                    HttpMessageNotReadableException ex,
                    HttpHeaders headers,
                    HttpStatusCode status,
                    WebRequest request) {

        return new ResponseEntity<>(
                new ErrorBody(
                        "UNREADABLE_BODY",
                        List.of()
                ),
                headers,
                status
        );
    }
}
```

The handler **maps only concrete request errors**. It does not include:

```java
@ExceptionHandler(UnexpectedTypeException.class)
public ResponseEntity<?> badRequest() {
    return ResponseEntity.badRequest().build();
}
```

This is an **anti-pattern fragment**, not code to add to the project. A `ConstraintValidator` configuration bug must not be disguised as "the client sent invalid data." If production has a global 5xx fallback for unexpected exceptions, still log/monitor the cause without exposing exception details to callers.

### 8.9. `src/test/java/demo/ConstraintTypeTest.java`

```java
package demo;

import java.util.List;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.UnexpectedTypeException;
import jakarta.validation.Valid;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.Future;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class ConstraintTypeTest {

    private static ValidatorFactory factory;
    private static Validator validator;

    @BeforeAll
    static void openValidatorFactory() {
        factory = Validation.buildDefaultValidatorFactory();
        validator = factory.getValidator();
    }

    @AfterAll
    static void closeValidatorFactory() {
        if (factory != null) {
            factory.close();
        }
    }

    record BadNotBlank(@NotBlank Integer quantity) {
    }

    record BadSize(@Size(min = 1, max = 3) Integer digits) {
    }

    record BadPattern(
            @Pattern(regexp = "[0-9]+") Long reference) {
    }

    record BadFuture(@Future String startsAt) {
    }

    record BadCustom(@StartsWith("SKU-") Integer sku) {
    }

    record CorrectQuantity(
            @NotNull @Min(1) Integer quantity) {
    }

    record Line(@NotBlank String name) {
    }

    record Shipment(
            @NotEmpty List<@Valid Line> lines) {
    }

    private <T> Set<String> invalidFields(T value) {
        return validator.validate(value)
                .stream()
                .map(v -> v.getPropertyPath().toString())
                .collect(Collectors.toSet());
    }

    @Test
    void notBlankIntegerThrowsUnexpectedType() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(new BadNotBlank(2)));
    }

    @Test
    void sizeIntegerThrowsUnexpectedType() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(new BadSize(12)));
    }

    @Test
    void patternLongThrowsUnexpectedType() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(new BadPattern(123L)));
    }

    @Test
    void futureStringThrowsUnexpectedType() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(
                        new BadFuture("2031-01-01")));
    }

    @Test
    void customStringConstraintOnIntegerThrows() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(new BadCustom(42)));
    }

    @Test
    void correctNumericConstraintsReturnViolation() {
        assertEquals(
                Set.of("quantity"),
                invalidFields(new CorrectQuantity(0))
        );
    }

    @Test
    void correctNumericConstraintsAcceptPositiveValue() {
        assertTrue(invalidFields(
                new CorrectQuantity(3)).isEmpty());
    }

    @Test
    void validDtoProducesNoViolations() {
        ItemRequest input = new ItemRequest(
                "SKU-123", 2, List.of("spring", "mvc")
        );
        assertTrue(validator.validate(input).isEmpty());
    }

    @Test
    void customConstraintReturnsViolationNotException() {
        ItemRequest input = new ItemRequest(
                "ABC-123", 2, List.of("spring")
        );
        assertEquals(
                Set.of("sku"),
                invalidFields(input)
        );
    }

    @Test
    void containerElementConstraintReportsBadTag() {
        ItemRequest input = new ItemRequest(
                "SKU-123", 2, List.of("")
        );

        assertFalse(validator.validate(input).isEmpty());
        assertTrue(invalidFields(input).stream()
                .anyMatch(path -> path.contains("tags")));
    }

    @Test
    void validCascadeTraversesNestedObject() {
        Shipment shipment = new Shipment(
                List.of(new Line(""))
        );

        assertTrue(invalidFields(shipment).stream()
                .anyMatch(path -> path.contains("name")));
    }
}
```

**Eleven unit tests** clearly test two distinct outcomes:

- **5 intentionally misconfigured tests**: `@NotBlank Integer`, `@Size Integer`, `@Pattern Long`, `@Future String`, and custom `@StartsWith Integer` must throw `UnexpectedTypeException`.
- **6 properly configured tests**: verify numeric violations, valid numeric values, valid DTOs, custom `isValid=false` returning violations, invalid container elements, and cascaded nested objects.

These tests invoke Jakarta `Validator` directly without HTTP conversion. They **do not assert the string `HV000030`** so tests are not coupled to one provider version's log wording. The critical assertions are **exception type** for wrong declarations and **violation set** for invalid values.

### 8.10. `src/test/java/demo/ItemControllerTest.java`

```java
package demo;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet
        .AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.hasItem;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders
        .post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers
        .status;

@SpringBootTest
@AutoConfigureMockMvc
class ItemControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validItemReturnsCreated() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "quantity":2,
                              "tags":["spring","mvc"]
                            }
                            """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.status")
                        .value("accepted"))
                .andExpect(jsonPath("$.tagCount")
                        .value(2));
    }

    @Test
    void zeroQuantityIsInputViolation() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "quantity":0,
                              "tags":["spring"]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields",
                        hasItem("quantity")));
    }

    @Test
    void missingQuantityViolatesNotNull() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "tags":["spring"]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("quantity")));
    }

    @Test
    void emptyTagsViolatesNotEmpty() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "quantity":1,
                              "tags":[]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("tags")));
    }

    @Test
    void blankTagViolatesElementNotBlank() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "quantity":1,
                              "tags":[""]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem(containsString("tags"))));
    }

    @Test
    void wrongPrefixIsValidationFailure() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"ABC-123",
                              "quantity":1,
                              "tags":["spring"]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INPUT_INVALID"))
                .andExpect(jsonPath("$.fields",
                        hasItem("sku")));
    }

    @Test
    void blankSkuFailsNotBlank() throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"",
                              "quantity":1,
                              "tags":["spring"]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.fields",
                        hasItem("sku")));
    }

    @Test
    void incompatibleJsonTypeIsConverterError()
            throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                            {
                              "sku":"SKU-123",
                              "quantity":{"nested":true},
                              "tags":["spring"]
                            }
                            """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }

    @Test
    void malformedJsonIsConverterError()
            throws Exception {
        mvc.perform(post("/items")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"sku\":,}"))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("UNREADABLE_BODY"));
    }
}
```

**Nine MockMvc integration tests** prove:

- A valid DTO passes Spring MVC validation cleanly.
- Integer quantity equal to 0 is a **normal validation violation** ⇒ HTTP 400 `INPUT_INVALID`, not `UnexpectedTypeException`.
- Missing quantity is rejected by `@NotNull`.
- Empty List is rejected by `@NotEmpty`.
- Blank String element inside List is rejected by `@NotBlank`.
- A type-compatible custom constraint returning false produces a normal violation.
- Blank String triggers a normal violation.
- A JSON shape unconvertible to Integer produces `UNREADABLE_BODY`.
- Malformed JSON is also a converter failure, not a bean constraint mismatch.

Both test groups run against the same project, yet type mismatches live strictly inside unit tests. Never create an intentionally broken endpoint in production code.

### 8.11. Running the Project

In the `unexpected-type-demo` directory on a machine with **JDK 17+ and Maven**:

```bash
mvn -q clean test
```

**Expected:** 11 unit tests + 9 MockMvc tests = **20 tests** pass, Maven returns exit code 0 in a compatible environment. This is an expectation from the sample code, **not an executed build or stdout observed here**. If an API/provider behaves differently, inspect the exact Spring Boot/Hibernate Validator versions and actual error logs.

Start the server:

```bash
mvn spring-boot:run
```

Valid request:

```bash
curl -i -X POST 'http://localhost:8080/items' \
  -H 'Content-Type: application/json' \
  --data '{
    "sku":"SKU-123",
    "quantity":2,
    "tags":["spring","mvc"]
  }'
```

Response per demo contract:

```json
{
  "status": "accepted",
  "sku": "SKU-123",
  "quantity": 2,
  "tagCount": 2
}
```

When sending `quantity=0` (as a JSON number):

```bash
curl -i -X POST 'http://localhost:8080/items' \
  -H 'Content-Type: application/json' \
  --data '{
    "sku":"SKU-123",
    "quantity":0,
    "tags":["spring"]
  }'
```

Expected HTTP 400 response:

```json
{
  "code": "INPUT_INVALID",
  "fields": ["quantity"]
}
```

When sending `{"quantity":{"nested":true}}` instead of a JSON number, Jackson cannot construct an Integer from the object under default configuration, so expect HTTP 400 with `UNREADABLE_BODY`. Meanwhile, an intentional `@NotBlank Integer` error **never** appears on this endpoint because the main DTO is fixed.

## 9. When the Error Appears in Spring MVC, How Do You Investigate?

### 9.1. Start from the Exception Class, Not the HTTP Status

For instance, a request may never enter the controller and return 500. Inspect the server stack trace:

- Is `jakarta.validation.UnexpectedTypeException` present?
- Is `HV000030` present?
- Which annotation and which validated type are mentioned?
- Which property/parameter path?
- Is the DTO `@ModelAttribute`, `@RequestBody`, or `@RequestPart`?
- Are there nested List/Map element constraints or custom validators?

When the exception is `UnexpectedTypeException`, do not rush to modify `@RestControllerAdvice` to hide the error, alter `BindingResult`, or disable `@Valid`. Fix the annotation/type mismatch first.

### 9.2. Flow of a JSON Request

```text
HTTP JSON
  |
  v
HttpMessageConverter / Jackson
  |  syntax/type error -> HttpMessageNotReadableException
  v
ItemRequest constructed successfully
  |
  v
Spring MVC invokes Jakarta Validator
  |
  +-- annotation/type mismatch
  |       -> UnexpectedTypeException (server configuration)
  |
  +-- right validator, invalid value
  |       -> ConstraintViolation(s)
  |       -> BindingResult / MethodArgumentNotValidException
  |
  +-- right validator, valid value
          -> controller is invoked
```

If a DTO has multiple constraints, the error may surface on the first annotation the provider fails to resolve. Do not assume constraint traversal order is fixed; fix **all** bad declarations, not just the first one in the stack trace.

### 9.3. Form-Urlencoded Adds a Conversion Layer

With `@ModelAttribute`, `WebDataBinder` converts request parameters into Java properties:

- `quantity=abc` into `Integer`: normally a binding conversion failure, becoming `FieldError.isBindingFailure()`.
- `quantity=0` into `@Min(1) Integer`: conversion succeeds, then the constraint returns false.
- `quantity=2` into `@NotBlank Integer`: conversion succeeds, then validator selection fails.
- `quantity=` into `Integer`: may convert to null; `@NotNull` rejects it, depending on binder configuration.

Hence you must identify **which step failed first**: message conversion, type conversion, validator resolution, or `isValid`.

### 9.4. `@RequestBody` and `BindingResult` Do Not Fix Broken Annotations

A controller with:

```java
@PostMapping("/bad")
public String handle(
        @Valid @RequestBody BadRequest body,
        BindingResult errors) {

    return errors.hasErrors() ? "bad" : "ok";
}
```

This is a fragment; `BadRequest` is undefined. Spring MVC requires the result immediately after the validated argument for local error handling. Even with proper positioning, `@NotBlank Integer` inside `BadRequest` still throws `UnexpectedTypeException` when Bean Validation cannot resolve a validator.

Local `BindingResult` exists to collect **evaluated binding/constraint errors**, not to turn an invalid validator declaration into a field error.

## 10. Custom Constraints: Implementation Pitfalls to Avoid

### 10.1. `@Constraint` Missing a Validator for the Target Type

Suppose you define `@ValidSku` with only:

```java
class SkuValidator
        implements ConstraintValidator<ValidSku, String> {
    // ...
}
```

This is a fragment, not a runnable implementation. Placing `@ValidSku` on a `SkuId` field (value object) where `SkuId` is not a subtype of `String` means the provider cannot apply this validator.

Principled fixes:

- Change the DTO field to `String` if the external representation is a string and the service converts it to a value object.
- Or implement a dedicated `ConstraintValidator<ValidSku, SkuId>` with clear semantics for the value object.
- Or place the constraint on the nested property `SkuId.value` if domain model and validation cascade fit.
- Avoid creating `ConstraintValidator<ValidSku, Object>` just to accept every type with complex runtime `instanceof` checks, unless the constraint truly applies generically to all objects.

### 10.2. Conflicts from Multiple Validators

If a custom annotation declares validators for overlapping interfaces, the provider may be unable to pick a uniquely most-specific implementation. Design a clean generic type hierarchy or split constraint names.

Never rely on **the listing order** of classes in `validatedBy` to resolve ambiguity.

### 10.3. Malformed Constraint Definitions Throw Different Exceptions

If standard `message`/`groups`/`payload` attributes are missing on a constraint annotation, the provider may throw **`ConstraintDefinitionException`**, not necessarily `UnexpectedTypeException`. If executable-method or value-extractor rules are violated, `ConstraintDeclarationException` may occur. Distinguish exception subclasses before editing code.

### 10.4. Do Not Change Generic Types Expecting Spring to Auto-Cast

If the validator is `ConstraintValidator<A, CharSequence>`, Spring will not convert `Long` into `String` for Jakarta Validator after the request already bound to `Long`. Bean Validation inspects the element's type. To validate regexes, use a `String` representation in the DTO or type-appropriate custom validation.

### 10.5. Never Store Per-Request Mutable State in a Singleton Validator

`ConstraintValidator` instances can be cached by the provider and invoked concurrently; `isValid(...)` must be thread-safe. Never store current-request values in instance fields across requests. Annotation configuration from `initialize(...)` can be kept as immutable state—such as the prefix in `StartsWithValidator`—provided `isValid(...)` never mutates it.

## 11. Refactorings That Commonly Trigger `HV000030`

### 11.1. Refactoring `String` to `Integer` While Keeping `@NotBlank`

Before:

```java
@NotBlank
String attemptCount;
```

Broken after refactoring:

```java
@NotBlank
Integer attemptCount;
```

Proper after refactoring:

```java
@NotNull
@Min(1)
Integer attemptCount;
```

Migration tests should invoke Bean Validator on the real DTO, not just test Jackson deserialization. Type-valid JSON can decode cleanly and only fail during the validation phase.

### 11.2. Refactoring `String` Time to `Instant` While Keeping `@Pattern`

Before:

```java
@NotBlank
@Pattern(regexp = "\\d{4}-\\d{2}-\\d{2}")
String date;
```

Broken after refactoring:

```java
@Pattern(regexp = "\\d{4}-\\d{2}-\\d{2}")
LocalDate date;
```

Better:

```java
@NotNull
@Future
LocalDate date;
```

This fragment assumes business rules require a future date; drop `@Future` if any date is allowed. Validating "string matches `yyyy-MM-dd`" no longer applies once the field is `LocalDate`; Jackson handles parsing, and Jakarta Validation enforces domain/date constraints post-decode.

### 11.3. Replacing a List with a Count While Keeping `@Size`

Before:

```java
@Size(max = 10)
List<String> items;
```

Broken after:

```java
@Size(max = 10)
Integer itemCount;
```

Correct after if business rules require 0–10:

```java
@NotNull
@Min(0)
@Max(10)
Integer itemCount;
```

### 11.4. Moving `@NotBlank` from Element to Container

Before (correct):

```java
List<@NotBlank String> names;
```

Broken after:

```java
@NotBlank
List<String> names;
```

Correct after if wanting both a non-empty list and non-blank elements:

```java
@NotEmpty
List<@NotBlank String> names;
```

### 11.5. Replacing a String Code with an Enum While Keeping `@Pattern`

Before:

```java
@Pattern(regexp = "NEW|PAID|CANCELLED")
String state;
```

After refactoring:

```java
@Pattern(regexp = "NEW|PAID|CANCELLED")
OrderState state;
```

If `OrderState` is an enum, `@Pattern` on an enum has no compatible standard validator. Use `@NotNull OrderState state`; Jackson/the mapper controls which strings map to valid enum constants. If business rules allow only a subset of transitions, enforce that rule in the service/domain rather than expecting regexes on enums.

## 12. Distinguishing Type-Mismatched `@NotBlank` from Other Data Failures

### 12.1. Value Error: Type-Compatible Constraint, Invalid Data

```java
@NotBlank
String name = "";
```

The `NotBlank` validator runs on `String` and returns false; the framework records a normal violation. This is when the user needs to fix input.

### 12.2. Constraint Error: Annotation Does Not Support Declared Type

```java
@NotBlank
Integer name = 12;
```

No compatible validator exists; even though 12 is "present," the annotation has no definition for validating `Integer`. This is a server-side configuration bug.

### 12.3. Conversion Error: Request Cannot Construct Java Value

```json
{"quantity":{"unexpected":true}}
```

For a DTO with `Integer quantity`, Jackson normally cannot deserialize a JSON object into `Integer`. This error occurs **before Jakarta Validation** and can be mapped to `UNREADABLE_BODY`. It is not `HV000030`.

### 12.4. Dependency Namespace Mismatch: `javax` vs. `jakarta`

Spring Boot 3.x / Spring Framework 6 use **`jakarta.validation.*`**. If a project still imports legacy `javax.validation.*`, annotations or provider integration may silently fail or clash on the classpath. That is a separate migration/classpath problem; do not assume it produces the same `UnexpectedTypeException` as `@NotBlank Integer`.

Check:

```bash
mvn dependency:tree
```

Ensure all validation dependencies belong to the same Jakarta/Boot generation. Never add an older validator provider onto the classpath as a "fix for `HV000030`."

### 12.5. Annotation Processing and Code Generation Bugs

When using Lombok, MapStruct, Jackson records, Kotlin, or code generators, inspect **the types in the compiled/generated classes** and where annotations end up. A `@NotBlank` annotation may have been copied from a `String` property onto a numeric field. Testing the compiled application catches mismatches invisible in source snippets.

## 13. Preventive Testing: Do Not Test Only the Happy Path

A smoke test sending valid input can catch a mismatch if it exercises DTO validation, yet constraints in **other validation groups**, nested branches, or other object types may stay unexecuted.

At minimum, include:

1. Unit tests for each input DTO via Jakarta `Validator#validate(...)`.
2. Tests for every `@Validated(Group.class)` when using multiple groups.
3. Tests for container elements, nested objects, and subtype/custom constraints.
4. MockMvc tests for both form-urlencoded and JSON requests if the application supports both.
5. Negative tests with invalid values *of the right Java type* to confirm **field violations** occur rather than configuration exceptions.
6. Tests sending valid payloads all the way to the service; never test only errors.
7. Static analysis/annotation processors where available, while keeping runtime tests because real mappings/providers can differ.

### 13.1. A Small, High-Value Mutation Test

A test like:

```java
assertThrows(UnexpectedTypeException.class,
        () -> validator.validate(new BadNotBlank(2)));
```

is minimal proof of a **declaration/type** bug. Once fixed, replace it with:

```java
Set<ConstraintViolation<CorrectQuantity>> violations =
        validator.validate(new CorrectQuantity(0));

assertEquals(1, violations.size());
```

This is a **fragment** based on the nested records in Section 8's test. The lesson is verifying the transition from **exception** to **normal violation**, rather than just seeing HTTP status change from 500 to 400 without checking error semantics.

### 13.2. Never Assert Full Stack Traces or Provider Messages

Hibernate Validator messages include constraint class, type, and property path; quotes, internal class names, line numbers, and translations can vary by version. Unit tests should assert `UnexpectedTypeException.class` or `ConstraintViolation<?>` with the matching property path and constraint annotation.

If observability looks for `HV000030`, treat provider codes in logs as an **operational signal**, never as a public API error code or cross-provider contract.

## 14. Diagnostic Decision Tree

```text
Error occurs while validating a DTO?
        |
        v
Is the exception UnexpectedTypeException?
        |
        +-- Yes
        |    |
        |    v
        |  Identify constraint + declared type + path
        |    |
        |    v
        |  Is there a compatible ConstraintValidator?
        |    |
        |    +-- No  -> change annotation/type or add validator
        |    |
        |    +-- Multiple matches -> resolve ambiguous validators
        |    |
        |    v
        |  Rerun unit validation + MockMvc tests
        |
        +-- No
             |
             v
        ConstraintViolation / MethodArgumentNotValidException?
             |
             +-- Yes -> handle invalid input per API contract
             |
             +-- No
                  |
                  v
        HttpMessageNotReadableException?
             |
             +-- Yes -> inspect JSON shape/conversion
             |
             +-- No  -> check other exceptions/phases
```

**Note:** `ConstraintDeclarationException` has multiple causes; a value-extractor or method-constraint issue may not be `UnexpectedTypeException`. Diagnose using **exception class + stack trace + annotation metadata**, not simply the word "validation" in logs.

## 15. Common Mistakes When Fixing `HV000030`

### 15.1. Removing `@Valid` So the Endpoint Stops Failing

This **turns off validation** instead of fixing the broken constraint. Other fields will stop being validated. The fix is choosing an annotation compatible with the declared type.

### 15.2. Catching `UnexpectedTypeException` and Returning 400 for Every Request

This is a server programming bug, not "the user entered 2 wrongly." Return input errors only for real **`ConstraintViolation`/`FieldError`** or conversion failures. Type mismatches should trigger alerts and be fixed.

### 15.3. Adding `@NotNull` While Keeping `@NotBlank Integer`

```java
@NotNull
@NotBlank
Integer quantity;
```

Adding `@NotNull` does not disable the type-incompatible `@NotBlank`. The provider still must resolve a validator for `NotBlank`. **You must remove the incompatible annotation.**

### 15.4. Swapping `@Size(Integer)` for `@Digits` Without Understanding Business Rules

`@Digits` validates integer/fractional digit counts as defined by the annotation. It does not mean numeric range; if business rules want `1 ≤ quantity ≤ 999`, use `@Min(1) @Max(999)`.

### 15.5. Putting `@NotBlank` on an Enum or Nested Bean

`@NotBlank` is for `CharSequence`. Enums/beans normally use `@NotNull`; for nested beans add `@Valid` and constraints on their fields. Never auto-stringify an enum to check for a "valid name."

### 15.6. Fixing Only One Field When Multiple Mismatches Exist

The provider may abort at the first unresolvable annotation. After fixing one, a second bug in another DTO may surface. Run tests across all related DTOs and validation groups.

### 15.7. Writing a Generic `Object` Validator to Hide Every Mismatch

A `ConstraintValidator<A, Object>` accepting every type can silence the error while muddying semantics. Use it only when the constraint genuinely applies to all `Object`s; normally **type-specific validators** are far easier to maintain.

### 15.8. Assuming Supported Types from Another Blog or Provider

Hibernate Validator extensions may not be portable across providers. Verify against your exact Jakarta spec/provider version; for common constraints, stick to standard supported types.

### 15.9. Believing the Java Compiler Catches All Annotation/Type Bugs

`@Target(FIELD)` does not restrict a field to `String` or `Integer`. The compiler permits many declarations that are invalid in Bean Validation. Runtime validation tests and static tooling are both needed.

### 15.10. Confusing `@Pattern String` with `@Future Instant`

If the input represents date/time, use a proper temporal type with `@Future`; if the input is a text identifier, use `@Pattern`. Do not substitute regexes for temporal semantics or vice versa.

### 15.11. Switching `BindingResult` to `Errors`

`BindingResult` and `Errors` both represent Spring validation results; changing the parameter type does not add a `ConstraintValidator` for `Integer`. If the root exception is `UnexpectedTypeException`, fix the DTO or custom validator.

### 15.12. Errors Surfacing Only During JPA Flush

Hibernate ORM can integrate Bean Validation at pre-persist/update. An entity with a type-mismatched annotation can throw on persist/flush, not only when a REST controller invokes `@Valid`. Place proper constraints on entities and back final state with database constraints; never assume fixing a controller DTO covers every entity-level declaration.

### 15.13. Exposing Raw Exception Content in REST Responses

Stack traces can leak internal classes, packages, property paths, or sensitive data. Return a concise server-error response, log safely, and deploy a fix rather than letting clients depend on `HV000030` messages.

## 16. Pre-Deployment Review Checklist

### Constraint/Type Matching

- [ ] `@NotBlank` is applied only to `CharSequence` or compatible `String` elements.
- [ ] `@Size` is applied to compatible `CharSequence`/Collection/Map/array types.
- [ ] Numeric ranges use `@Min/@Max`, `@Positive`, or appropriate numeric variants.
- [ ] `@Pattern` is applied to `CharSequence`, never numeric/enum/object types.
- [ ] Temporal constraints are applied to supported temporal types, never raw `String`s.
- [ ] `@NotNull` is declared when reference fields are required.
- [ ] Collections place container and element constraints at their respective levels.
- [ ] Nested objects use `@Valid` to cascade rather than string constraints on beans.
- [ ] Custom constraints have `ConstraintValidator<A,T>` compatible with the declared type.
- [ ] No ambiguous multiple custom validators exist for the same target type.
- [ ] Annotation `message/groups/payload` conform to Jakarta rules.
- [ ] Provider and namespace are consistent with Spring Boot 3.x.

### Controller and Exception Handling

- [ ] Distinguish `UnexpectedTypeException` from `ConstraintViolationException`.
- [ ] Never map invalid constraint declarations to client HTTP 400.
- [ ] Handle `MethodArgumentNotValidException` for DTO constraint violations.
- [ ] Handle `HttpMessageNotReadableException` for JSON decoding failures.
- [ ] When using method-level constraints, handle `HandlerMethodValidationException` in Spring MVC 6.1+.
- [ ] Keep `BindingResult` immediately after the object when handling local field errors.
- [ ] Never expose raw validation/exception details or rejected values in API responses.

### Testing

- [ ] Direct Jakarta Validator tests cover every DTO/record.
- [ ] Negative tests confirm invalid values yield violations, not configuration exceptions.
- [ ] Tests cover container elements and nested cascades.
- [ ] Tests cover custom validator target types.
- [ ] MockMvc integration tests cover the fixed DTOs.
- [ ] No test asserts exact `HV000030` message strings.
- [ ] Regression tests run after refactoring `String` → `Integer`/enum/`LocalDate`.
- [ ] Infrequently executed validation groups, routes, or methods are tested.
- [ ] CI catches mismatches before users ever encounter HTTP 500.

## 17. Conclusion

**`UnexpectedTypeException` means no compatible validator could be selected for the declared type**, classically seen with `@NotBlank Integer` or `@Size Integer`. It differs from normal constraint failures: **the provider could not evaluate the annotation**, rather than merely flagging a bad value.

To fix it:

1. Identify **annotation + declared Java type + property path** from the exception.
2. Choose a constraint matching both semantics and type—e.g., `@NotNull @Min(1) Integer` instead of `@NotBlank Integer`.
3. For custom constraints, fix `ConstraintValidator<A,T>`, `validatedBy`, or the type hierarchy so a unique best validator exists.
4. For nested `List`/`Map`, place annotations on the proper **container or type argument**, and use `@Valid` to cascade.
5. Distinguish configuration bugs from `MethodArgumentNotValidException`, JSON conversion errors, and normal field violations.
6. Protect with Jakarta Validator unit tests and MockMvc tests rather than masking bugs by removing `@Valid` or returning 400 for every exception.

Once fixed properly, a request with `quantity=0` produces a **validation violation returning HTTP 400**, while `quantity=2` succeeds—eliminating **HTTP 500 caused by type-mismatched constraint annotations**.

## References

- [Jakarta Bean Validation 3.0 — Specification, ConstraintValidator resolution algorithm and UnexpectedTypeException](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html)
- [Jakarta Validation — UnexpectedTypeException API](https://javadoc.io/doc/jakarta.validation/jakarta.validation-api/3.0.2/jakarta/validation/UnexpectedTypeException.html)
- [Hibernate Validator 8 — Reference Guide: supported constraints and supported data types](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
- [Hibernate Validator — Annotation Processor Reference](https://docs.jboss.org/hibernate/stable/validator/reference/en-US/html_single/#validator-annotation-processor)
- [Spring Framework — Core Validation](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — MVC @RequestBody and Bean Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — MethodArgumentNotValidException API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/bind/MethodArgumentNotValidException.html)
- [Spring Framework — ResponseEntityExceptionHandler API](https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/web/servlet/mvc/method/annotation/ResponseEntityExceptionHandler.html)
- [Spring Boot 3.4 — Validation](https://docs.spring.io/spring-boot/3.4/reference/io/validation.html)
