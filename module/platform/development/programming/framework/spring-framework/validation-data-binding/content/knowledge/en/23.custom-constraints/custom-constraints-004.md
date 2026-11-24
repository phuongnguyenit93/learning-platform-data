# ConstraintValidator<A,T>: Roles of initialize() and isValid()

## Lesson Objectives

After this lesson, you can explain how Jakarta Bean Validation binds a custom constraint annotation to its validation class, distinguish one-time configuration in `initialize()` from value evaluation in `isValid()`, build a parameterized constraint yourself, and integrate it with Spring Framework. The focus is on the `ConstraintValidator<A,T>` contract and common mistakes when executing validators in real applications.

## 1. Where does ConstraintValidator fit?

Jakarta Bean Validation lets you declare rules directly on the data model, such as `@NotNull`, `@Size`, or an application-defined annotation. To create a new constraint, two components are usually required:

1. **A constraint annotation** defining the rule name, configuration attributes, error message, and applicable targets.
2. **A `ConstraintValidator` implementation class** containing the validation logic for a specific data type.

For example, an application wants to validate an order code formatted like `ORD-1234`: a configurable prefix followed by exactly four ASCII digits. The `@OrderCode(prefix = "ORD-", digits = 4)` annotation describes the requirement; `OrderCodeValidator` performs the check.

Basic flow:

~~~text
Object/value to validate
    -> @OrderCode on property
    -> Bean Validation provider locates matching validator
    -> create/obtain ConstraintValidator and call initialize(annotation)
    -> call isValid(value, context)
    -> true: valid; false: create ConstraintViolation
    -> caller receives violation set or framework handles errors
~~~

**Distinction:** an annotation does not execute logic by itself. There must be a validation trigger point, such as `Validator.validate(bean)`, `@Valid @RequestBody` in Spring MVC, or configured method validation.

Spring Framework 6 / Spring Boot 3 uses the **`jakarta.validation.*`** namespace. Older examples using `javax.validation.*` belong to the previous ecosystem; do not mix the two namespaces in the same example.

## 2. Reading the two generic parameters and method contract correctly

The interface has the structure:

~~~java
public interface ConstraintValidator<A extends Annotation, T> {
    default void initialize(A constraintAnnotation) { }

    boolean isValid(T value, ConstraintValidatorContext context);
}
~~~

- **`A`**: the constraint annotation type handled by the validator, such as `OrderCode`. The argument passed to `initialize(A)` is the specific annotation instance attached to the property.
- **`T`**: the type of value being validated, such as `String`. Therefore `ConstraintValidator<OrderCode, String>` applies to `@OrderCode` on values compatible with `String`.
- **`initialize(A)`**: empty default method; only override when you need to read/set annotation configuration or prepare shared immutable data.
- **`isValid(T, ConstraintValidatorContext)`**: required method; returns `true` when the value satisfies the constraint, `false` when violated. `context` lets you customize error messages and paths.

For example, if you want the same annotation to validate both `String` and a custom domain type, you can register corresponding validators in `@Constraint(validatedBy = {...})`. Do not use a validator accepting an incompatible type and cast arbitrarily. For generic `T`, Jakarta Validation's type resolution rules also have limitations: do not directly declare a parameterized type like `List<String>` as `T`; if you need to validate an entire collection, consider `List<?>` or element-level constraints.

## 3. Lifecycle: initialize once per instance, isValid many times

The provider (such as Hibernate Validator) orchestrates the lifecycle:

1. Locate the constraint declaration and value type.
2. Create or obtain a `ConstraintValidator` instance via `ConstraintValidatorFactory`.
3. **Ensure `initialize()` is called before using that instance for validation.**
4. Call `isValid()` when a value needs validation; the provider is allowed to retain and reuse the instance.

Do not infer that each request/object gets a fresh validator, or that `initialize()` is called only once for the entire application. Instance count and caching policies depend on the provider. Think of `initialize()` as **per-instance initialization with constraint configuration**, and `isValid()` as **evaluation per check**.

This leads to an important design rule: **`isValid()` must be safe when multiple threads call it concurrently**. Fields assigned in `initialize()` should become read-only configuration state after initialization. Do not store `value`, `context`, request errors, or mutable counters in validator fields. Do not mutate the input object's state inside `isValid()`.

## 4. Complete example: @OrderCode with prefix and digits

We build four Java files in the `com.example.validation` package. This is a standalone example using Java 17+, Jakarta Validation API, and a provider like Hibernate Validator.

### 4.1. Annotation declaration: OrderCode.java

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target({
    ElementType.FIELD,
    ElementType.PARAMETER,
    ElementType.ANNOTATION_TYPE,
    ElementType.RECORD_COMPONENT
})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = OrderCodeValidator.class)
public @interface OrderCode {
    String prefix() default "ORD-";
    int digits() default 4;

    String message() default
            "must start with {prefix} and have exactly {digits} digits";

    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

Meaning of each part:

- `@Constraint(validatedBy = OrderCodeValidator.class)` links the annotation to its implementation class. Missing or mispointing this link prevents the provider from enforcing the rule as expected.
- `@Retention(RUNTIME)` retains the annotation at runtime so the validation engine can read it.
- `@Target` restricts where it can be used: here on fields, parameters, annotation composition, and record components.
- `message` provides the default message. `{prefix}` and `{digits}` are interpolated from the annotation attributes.
- `groups` and `payload` are standard elements of a constraint annotation. `groups` supports validation groups; `payload` carries optional metadata, not input data to validate.
- `prefix` and `digits` are rule-specific configuration passed to `initialize()`.

If the annotation is used on other element kinds (getters, type-use, etc.), `@Target` must be expanded deliberately. If defining a repeatable constraint, you need `@Repeatable` and a suitable container list; this example only needs one annotation per field.

### 4.2. Validator implementation: OrderCodeValidator.java

~~~java
package com.example.validation;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class OrderCodeValidator
        implements ConstraintValidator<OrderCode, String> {

    private String prefix;
    private int digits;

    @Override
    public void initialize(OrderCode annotation) {
        prefix = annotation.prefix();
        digits = annotation.digits();

        if (prefix.isBlank() || digits < 1) {
            throw new IllegalArgumentException(
                    "Invalid @OrderCode configuration");
        }
    }

    @Override
    public boolean isValid(
            String value, ConstraintValidatorContext context) {

        if (value == null) {
            return true;
        }

        if (!value.startsWith(prefix)) {
            return false;
        }

        String suffix = value.substring(prefix.length());
        if (suffix.length() != digits) {
            return false;
        }

        for (int i = 0; i < suffix.length(); i++) {
            char c = suffix.charAt(i);
            if (c < '0' || c > '9') {
                return false;
            }
        }
        return true;
    }
}
~~~

**Analyzing `initialize()`:** it reads the two attributes from the annotation and stores the configuration needed for subsequent validations. Checking `prefix`/`digits` here protects annotation authors from nonsensical configurations. If the configuration is invalid, it is a constraint definition error (reported via a runtime validation error), **not** an invalid user input value. No request data creation or network queries should happen at this step.

**Analyzing `isValid()`:** a `null` value returns `true` following the convention of separating format validation from presence validation; `@NotNull` handles the required check. For non-`null` values, the validator sequentially verifies the prefix, suffix length, and each digit character from `'0'` to `'9'`. This explicit character check is intentional: the code format requires ASCII digits, not arbitrary Unicode characters considered digits.

Assuming configuration `prefix = "ORD-"`, `digits = 4`:

| Value | Individual `isValid()` result | Reason |
| --- | --- | --- |
| `ORD-1234` | `true` | Correct prefix and four digits |
| `ORD-12A4` | `false` | Contains character A |
| `PAY-1234` | `false` | Wrong prefix |
| `ORD-12345` | `false` | One extra digit |
| `ORD-` | `false` | Missing numeric part |
| `null` | `true` | Non-null requirement belongs to `@NotNull` |

Using `String.startsWith` is case-sensitive. If business rules allow case-insensitive codes, design the rule clearly and ensure consistent comparison; do not normalize by **mutating** the object passed into the validator.

### 4.3. Applying to the model: OrderRequest.java

~~~java
package com.example.validation;

import jakarta.validation.constraints.NotNull;

public final class OrderRequest {
    @NotNull
    @OrderCode(prefix = "ORD-", digits = 4)
    private final String code;

    public OrderRequest(String code) {
        this.code = code;
    }

    public String getCode() {
        return code;
    }
}
~~~

The two annotations address two independent concerns:

- `@NotNull`: the code must not be missing.
- `@OrderCode`: if a code is present, its format must be valid.

Do not confuse `isValid(null) == true` with the overall model validation result. When `code == null`, the `@OrderCode` constraint passes, yet `@NotNull` still produces a violation and the entire model is invalid.

If you also want to reject blank strings, add `@NotBlank` or design the constraint to match the requirement; do not assume `null`, empty strings, and blank strings always carry the same meaning.

### 4.4. Running without a Spring container: Demo.java

~~~java
package com.example.validation;

import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;

public final class Demo {
    public static void main(String[] args) {
        try (ValidatorFactory factory =
                     Validation.buildDefaultValidatorFactory()) {

            Validator validator = factory.getValidator();

            String[] samples = {
                "ORD-1234", "ORD-12A4",
                "PAY-1234", "ORD-12345", null
            };

            for (String code : samples) {
                OrderRequest request = new OrderRequest(code);
                boolean valid = validator.validate(request).isEmpty();

                System.out.println(
                        String.valueOf(code) + " -> " +
                        (valid ? "VALID" : "INVALID"));
            }
        }
    }
}
~~~

Place the Java files in `src/main/java/com/example/validation/`. A minimal `pom.xml` for the standalone Maven demo:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>com.example</groupId>
    <artifactId>custom-validation-demo</artifactId>
    <version>1.0.0</version>

    <dependencies>
        <dependency>
            <groupId>org.hibernate.validator</groupId>
            <artifactId>hibernate-validator</artifactId>
            <version>8.0.2.Final</version>
        </dependency>
        <dependency>
            <groupId>org.glassfish</groupId>
            <artifactId>jakarta.el</artifactId>
            <version>4.0.2</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=com.example.validation.Demo
~~~

The **lines printed by `Demo`** (excluding startup logs or Maven/provider logs if present in the environment):

~~~text
ORD-1234 -> VALID
ORD-12A4 -> INVALID
PAY-1234 -> INVALID
ORD-12345 -> INVALID
null -> INVALID
~~~

Here `null -> INVALID` is the **aggregate result on `OrderRequest`**, because `@NotNull` failed. `OrderCodeValidator.isValid(null, ...)` itself still returns `true`.

A Spring Boot 3 project with the `spring-boot-starter-validation` dependency already provides both the API and provider; do not copy the demo `pom.xml` verbatim into a Spring Boot application. The standalone Maven demo uses fixed versions so the example is reproducible.

## 5. ConstraintValidatorContext: when detailed messages are needed

If you simply return `false`, the provider uses the annotation's default `message`. When you need a distinct message per branch, you can use `ConstraintValidatorContext`.

The snippet below illustrates **replacing only the wrong-prefix branch** inside `isValid()`; this is a replacement snippet, not a standalone Java class:

~~~java
if (!value.startsWith(prefix)) {
    context.disableDefaultConstraintViolation();
    context.buildConstraintViolationWithTemplate(
            "Code must start with " + prefix)
           .addConstraintViolation();
    return false;
}
~~~

Meaning:

1. `disableDefaultConstraintViolation()` disables the default violation for this evaluation.
2. `buildConstraintViolationWithTemplate(...).addConstraintViolation()` creates a new violation.
3. After disabling the default message, you **must add at least one violation** if returning `false`.
4. Only build error messages when actually invalid; do not store `context` in an instance variable.

For constraints placed on an entire object (class-level), `context` also lets you attach the error to a specific property via `addPropertyNode("fieldName")` before `addConstraintViolation()`. That case differs from the field-level `@OrderCode` example.

## 6. Spring Framework integration

In a Spring MVC application with a Bean Validation provider on the classpath, `@Valid` or `@Validated` can trigger validation of objects received from an HTTP request:

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;

@RestController
public final class OrderController {
    @PostMapping("/orders")
    public ResponseEntity<Void> create(
            @Valid @RequestBody OrderRequest request) {
        return ResponseEntity.accepted().build();
    }
}
~~~

When the request is deserialized into `OrderRequest` and validation runs, `@OrderCode` invokes the registered validator. For standard validation of an `@RequestBody` object in Spring MVC, errors result in `MethodArgumentNotValidException` and typically return HTTP 400. Method signatures with constraints directly on parameters may go through method validation with a different exception type (such as `HandlerMethodValidationException`), so error handlers need to account for the right case.

For method calls on a Spring bean at the service layer, method validation is a separate mechanism: it requires proper configuration and a trigger point (typically via `@Validated` and Spring's validation infrastructure). Merely writing `@OrderCode` on a parameter of a plain Java method will not make direct calls validate automatically.

**Quick comparison of easily confused components:**

| Component | Role |
| --- | --- |
| `jakarta.validation.ConstraintValidator<A,T>` | Implements a constraint annotation for type `T` |
| `jakarta.validation.Validator` | API to invoke bean validation and obtain `Set<ConstraintViolation<T>>` |
| `jakarta.validation.Valid` | Triggers/cascades validation at supported points, not a validation rule itself |
| `org.springframework.validation.Validator` | Spring's own validation interface working with `Errors`; distinct from the Jakarta API |
| `org.springframework.validation.annotation.Validated` | Supports validation groups and Spring method validation when properly integrated |

Spring can support dependency injection inside custom validators through its integrated factory, but you **should not assume** that the same validator class instantiated via Java SE `Validation.buildDefaultValidatorFactory()` will also receive Spring injection. If logic depends on a service, verify the validator instantiation strategy of the actual runtime.

## 7. Responsibility boundaries and common pitfalls

**What belongs in initialize?** Reading annotation attributes, validating configuration, preparing patterns or shared data structures. For example, compiling a `Pattern` from a configured regex expression and storing it in a read-only field after initialization. Avoid operations tied to a specific request.

**What belongs in isValid?** Deciding whether the current value satisfies the rule. Checks should produce deterministic results based on the value and configuration. Normal malformed values should return `false`; do not abuse exceptions to signal invalid input. If an unexpected exception escapes a validator, the provider usually wraps it in `ValidationException`, which differs from a normal constraint violation.

Situations to watch out for:

- **Swapping `A` and `T`:** `ConstraintValidator<OrderCode, String>` accepts annotation `OrderCode` and data `String`; reversing the generics breaks the contract.
- **Missing implementation/provider:** having the Jakarta API on the classpath is not enough; a Bean Validation provider is required. Without a provider, building a `ValidatorFactory` may fail.
- **Placing the annotation on an unsupported field type:** for example `@OrderCode` on `Integer` when only a `String` validator exists can throw `UnexpectedTypeException`; it is not treated as a normal `false`.
- **Forgetting to trigger validation:** instantiating `new OrderRequest("BAD")` does not call `isValid()`; you need `validator.validate(...)` or the appropriate integration.
- **Treating `initialize()` as per-validation:** it may run only once for a cached instance. Logic relying on invocation counts will be wrong.
- **Using mutable fields for per-call data:** holding request state inside the validator can cause concurrency bugs; `isValid()` must be thread-safe.
- **Mishandling `null` expectations:** separate presence validation (`@NotNull`) from format validation; agree explicitly on requirements if there are exceptions.
- **Mutating input values:** normalizing or modifying the DTO inside `isValid()` violates the contract; do that in a conversion/normalization layer before validation if business logic needs it.
- **Custom message without adding a violation:** after `disableDefaultConstraintViolation()`, you must create at least one violation when returning `false`.
- **Heavy or side-effecting validation:** querying a DB, making HTTP calls, logging sensitive data, or mutating business state inside every `isValid()` increases latency, introduces non-determinism, and complicates testing. For conditions involving system state, clarify which layer owns the check and the data consistency mechanism.
- **Misreading the namespace:** Spring Boot 3+/Spring Framework 6+ uses `jakarta.validation`; `javax.validation` examples from older documentation are not directly compatible if APIs are mixed.

## 8. How to test a custom constraint

At minimum, test: valid values, wrong prefix, wrong length, invalid characters, `null`, and invalid annotation configuration. Separate two testing levels:

1. **Unit testing validator logic:** initialize the validator with a test configuration and check its logic. If calling `isValid()` directly, constructing a proper `ConstraintValidatorContext` can be cumbersome; using a real provider is often more convenient.
2. **Bean Validation integration testing:** use `Validator.validate(bean)` to verify the annotation is read, the validator is selected, messages are interpolated, and combined constraints like `@NotNull` work properly. The `Demo` example above is a smoke test of this path.

When asserting specific `ConstraintViolation` contents, do not assume an ordering of violations in the `Set`; filter by `propertyPath`/`messageTemplate` or sort deterministically before asserting. When testing inside Spring MVC, also verify the HTTP response and exception handler according to the actual Spring version and validation mechanism.

## 9. Takeaways and self-check

Answer these three questions for yourself:

1. Why is `initialize()` suitable for reading `prefix`, while `isValid()` is suitable for checking `ORD-1234`? Because configuration belongs to the annotation on the validator instance, whereas the input value changes across calls.
2. Why can `isValid(null)` return `true` while `Validator.validate(new OrderRequest(null))` still reports an error? Because `@NotNull` is an independent constraint.
3. Why shouldn't `lastValidatedCode` be stored in a field for the next call? Because the provider may cache the validator and invoke `isValid()` concurrently from multiple threads.

**Mental model to remember:** `ConstraintValidator<A,T>` binds *constraint annotation A* to *data type T*; `initialize(A)` prepares configuration for the instance; `isValid(T, context)` checks each value, is safe for concurrent calls, and does not mutate the input. A `false` result is turned by the provider into a violation for the caller or Spring to handle.

## References

- [Jakarta Validation 3.1 specification – Constraint validation implementation](https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.pdf)
- [Jakarta ConstraintValidator API](https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintValidator.html)
- [Hibernate Validator reference guide – Custom constraints](https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html)
