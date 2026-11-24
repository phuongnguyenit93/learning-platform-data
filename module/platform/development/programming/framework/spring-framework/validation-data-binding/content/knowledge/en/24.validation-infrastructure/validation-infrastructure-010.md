# ValidationException, ConstraintDeclarationException, and GroupDefinitionException

## 1. What do these three exceptions say about Jakarta Validation infrastructure?

**Jakarta Bean Validation** checks data using constraints such as `@NotNull`, `@NotBlank`, `@Size`, and custom constraints. Spring Framework/Spring Boot integrates this mechanism to validate DTOs, beans, methods, and request-bound data.

First distinction to make:

- **Input failing a valid constraint** is a normal business scenario. Calling `jakarta.validation.Validator#validate(bean)` returns a `Set<ConstraintViolation<T>>` containing the violations; an empty set means no violations were found for the validated groups.
- **Misconfigured or failing constraints, groups, or validation infrastructure** may throw `ValidationException` or one of its subclasses. This is not an ordinary field error and requires fixing the root cause in source code or configuration.

This lesson focuses specifically on three classes:

1. `jakarta.validation.ValidationException`: base exception for abnormal failures during validation.
2. `jakarta.validation.ConstraintDeclarationException`: a constraint is **declared or applied illegally** on an element, data type, or method contract.
3. `jakarta.validation.GroupDefinitionException`: invalid **group or group sequence definition**.

Examples use **Java 17+, Spring Boot 3+, and `jakarta.validation.*`**. Spring Boot 2.x typically uses the `javax.validation.*` namespace; do not mix the two library generations.

### Invalid data outcomes vs infrastructure exceptions

The snippet below assumes a `validator` variable of type `jakarta.validation.Validator` already exists:

~~~java
class UserForm {
    @jakarta.validation.constraints.NotBlank
    String username = "";
}

var violations = validator.validate(new UserForm());
System.out.println(violations.size()); // 1
~~~

This is an example snippet inside a method, not a standalone Java file. `@NotBlank` on `String` is a valid declaration; when encountering an empty string, the provider returns **one `ConstraintViolation`**. No `ValidationException` is thrown.

## 2. Inheritance hierarchy and comparison table

~~~text
java.lang.RuntimeException
└── jakarta.validation.ValidationException
    ├── ConstraintDeclarationException
    │   └── UnexpectedTypeException
    ├── GroupDefinitionException
    ├── ConstraintDefinitionException
    └── ... other Jakarta Validation subclasses
~~~

| Exception | Meaning | Typical symptom | How to fix |
| --- | --- | --- | --- |
| `ValidationException` | General error when validation infrastructure/engine or extensions cannot fulfill the request. | `isValid` throws a runtime exception, broken provider/factory, invalid mapping. | Inspect `getCause()`, stack trace, and the failing step. |
| `ConstraintDeclarationException` | Invalid placement or application of a constraint. | Subtype adds constraints to an overridden method parameter; invalid group conversion. | Check annotation placement, data types, method inheritance, and group conversions. |
| `GroupDefinitionException` | Invalid group/sequence definition rules. | Cyclic sequence; class-level default sequence omits the class itself. | Fix `@GroupSequence` and group ordering. |

Both specific exceptions extend `ValidationException`. Therefore `catch (ValidationException ex)` catches them, yet the concrete subtype and root cause determine the fix.

**Two additional easily confused types:**

- `ConstraintDefinitionException`: **the custom constraint annotation definition itself** breaks specification rules (for example, missing `message`, `groups`, or `payload`). This differs from misusing an otherwise valid constraint.
- `UnexpectedTypeException`: a subclass of `ConstraintDeclarationException` thrown when the provider cannot resolve a matching/unique `ConstraintValidator` for the annotation and validated type; for example `@NotBlank Integer id`.
- `ConstraintViolation` is an object representing a data error; `ConstraintViolationException` is a separate exception that an integration layer may throw while carrying violations. Do not infer the same cause from similar names.
- Invalid arguments passed directly to API methods (`validate(null)`, certain null/malformed arguments) may throw `IllegalArgumentException` per the method contract, not necessarily `ValidationException`.

## 3. `ValidationException`: errors preventing normal validation

`ValidationException` is an unchecked exception (subclass of `RuntimeException`), representing an abnormal failure in Jakarta Validation. It is also the superclass of specialized exceptions, so **read the exact runtime type** before analyzing.

Sources of errors include:

- Failure to build `ValidatorFactory`, missing provider, invalid XML configuration or mappings.
- Errors in `ConstraintValidatorFactory`, `MessageInterpolator`, `ValueExtractor`, `ConstraintValidator`, and other extensions.
- Exceptions thrown from `ConstraintValidator#initialize` or `ConstraintValidator#isValid`; the validation engine wraps runtime errors from extensions in `ValidationException`.
- Invalid constraint/group declarations, detected when processing metadata or executing validation.

Example custom validator **intentionally containing a bug**:

~~~java
@Override
public boolean isValid(String value,
                       ConstraintValidatorContext context) {
    throw new IllegalStateException("Dependent service unavailable");
}
~~~

This is only an illustrative method body inside `ConstraintValidator`. When the provider calls `isValid`, the `IllegalStateException` is wrapped in `ValidationException` (Hibernate Validator typically reports the validator execution failure in the message). This differs from `return false`: it signals that infrastructure/logic could not perform the check, rather than producing a normal "invalid field" result.

**Correct way to report failing data**:

~~~java
@Override
public boolean isValid(String value,
                       ConstraintValidatorContext context) {
    if (value == null) {
        return true; // @NotNull can handle the null case.
    }
    return value.startsWith("CUS-");
}
~~~

If you want a custom message, build a violation via `ConstraintValidatorContext` and then return `false`. **Do not throw `ValidationException` just because a user entered an invalid code pattern**; exceptions belong to abnormal failures that validation cannot handle normally.

When investigating, log `ex.getClass().getName()`, `ex.getCause()`, and the full stack trace on the server. A Hibernate Validator code such as `HV000...` helps pinpoint the issue in the implementation, but is not a stable contract for writing business branches based on message strings.

## 4. `ConstraintDeclarationException`: constraint placed illegally or breaking contract

`ConstraintDeclarationException` occurs when **the constraint annotation itself may be valid**, yet its usage falls into a situation forbidden by Jakarta Validation. Common sources:

1. **Method constraints in inheritance hierarchies:** a subtype adds parameter constraints to an overridden method, **tightening preconditions** unknown to callers of the supertype.
2. **Illegal group conversion:** using `@ConvertGroup` outside allowed sites, such as without an accompanying `@Valid` cascade, or declaring duplicate/invalid conversions.
3. **Misplaced cross-parameter constraints:** an annotation expecting multiple parameters is used with the wrong target or `validationAppliesTo` attribute.
4. **Container-element/cascaded validation:** the provider cannot resolve a suitable/unique value extractor.
5. **No validator matching the data type:** typically surfaces as the specific subclass `UnexpectedTypeException`.

### 4.1. Invalid method override example

~~~java
class BaseService {
    public void send(String code) {
    }
}

class StrictService extends BaseService {
    @Override
    public void send(@NotNull String code) {
        // INVALID: subtype adds a constraint to an overridden method parameter.
    }
}
~~~

This snippet requires importing `jakarta.validation.constraints.NotNull` and is not a standalone program. `BaseService#send`'s contract allows callers to pass null; the subclass adding `@NotNull` makes the precondition stricter. Under method validation rules, the provider must throw `ConstraintDeclarationException` when detecting this declaration, such as when inspecting `StrictService` metadata or running executable validation.

Fix by **placing the constraint on the supertype contract** if every implementation requires that rule:

~~~java
class BaseService {
    public void send(@NotNull String code) {
    }
}

class StrictService extends BaseService {
    @Override
    public void send(String code) {
    }
}
~~~

Constraints on the supertype method are inherited in method validation. You do not need (and should not) redeclare them on the overridden parameter. Placing the annotation alone does not make Java validate parameters on direct method calls: you need `ExecutableValidator` or Spring's corresponding method validation integration.

### 4.2. `UnexpectedTypeException`: unsupported type for constraint

~~~java
class BadField {
    @NotBlank
    Integer id = 42; // @NotBlank applies to text, not Integer.
}
~~~

During validation, the provider finds no matching `ConstraintValidator<NotBlank,Integer>`, so it throws `UnexpectedTypeException`, a specialized `ConstraintDeclarationException`. Fix with `@NotNull`, `@Min(1)`/`@Positive` for numeric checks, or write a custom constraint supporting that type.

**Distinguish definition errors:** a custom constraint missing `groups()`, `payload()`, or `message()` is a `ConstraintDefinitionException` issue. By contrast, a valid `@NotBlank` annotation applied to `Integer` is a validator-resolution/declaration issue.

## 5. `GroupDefinitionException`: invalid group sequence definition

Validation groups allow grouping constraints. When ordering is needed, `@GroupSequence` defines groups to run sequentially. If an earlier group produces violations, subsequent groups do not run. An invalid group definition can throw `GroupDefinitionException`.

Two typical causes:

- A cycle in group ordering definitions (via sequences or group relationships).
- Redefining a class's `Default` group with `@GroupSequence` while **omitting the class itself from the sequence**.

### 5.1. Class-level default group sequence must include the class itself

~~~java
interface ExtraChecks {
}

@GroupSequence({ExtraChecks.class}) // INVALID: missing Order.class
class Order {
    @NotNull String code;
}
~~~

`@GroupSequence` placed **on class `Order`** redefines the `Default` group for that class. Per the specification, the sequence must include `Order.class`. If omitted, the provider throws `GroupDefinitionException` when validating the class or querying its metadata.

Fix:

~~~java
interface ExtraChecks {
}

@GroupSequence({Order.class, ExtraChecks.class})
class Order {
    @NotNull String code;
}
~~~

Here constraints belonging to the class's default group run in the `Order.class` step, followed by `ExtraChecks.class` only if the earlier step produced no violations. Do not replace `Order.class` with `Default.class` when the goal is to **redefine Default on the class itself**.

Conversely, when defining a sequence **on a group interface** for standalone use, the syntax can be:

~~~java
@GroupSequence({Default.class, ExtraChecks.class})
interface OrderedChecks {
}
~~~

This is a separate sequence group, invoked for instance via `validator.validate(order, OrderedChecks.class)`; the “must include class Order” rule of default-sequence redefinition does not apply.

### 5.2. Cyclic sequences

~~~java
@GroupSequence({GroupB.class})
interface GroupA {
}

@GroupSequence({GroupA.class})
interface GroupB {
}
~~~

When evaluating `GroupA`, group A depends on B, and B depends back on A, causing `GroupDefinitionException`. Design the group sequence graph with no cyclic dependencies. Do not guess the evaluation order of constraints not belonging to an explicitly declared sequence: the specification does not guarantee arbitrary groups run in any hoped-for order.

## 6. Runnable demo: 5 scenarios in one Spring Boot application

Use a **Spring Boot 3+**, Java 17+ Maven project with the following dependency in `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Create **`src/main/java/com/example/validation/ValidationExceptionDemoApplication.java`**. All runnable source sits in one file; the intentionally invalid classes demonstrate the exceptions:

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.GroupSequence;
import jakarta.validation.Payload;
import jakarta.validation.ValidationException;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@SpringBootApplication
public class ValidationExceptionDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationExceptionDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runExamples(Validator validator) {
        return args -> {
            System.out.println("ordinary -> violations="
                    + validator.validate(new UserForm()).size());

            show("declaration", () -> {
                validator.getConstraintsForClass(StrictService.class);
            });

            show("group", () -> {
                validator.validate(new BadDefaultSequence());
            });

            show("type", () -> {
                validator.validate(new WrongConstraintType());
            });

            show("execution", () -> {
                validator.validate(new BrokenData());
            });
        };
    }

    private static void show(String label, Runnable operation) {
        try {
            operation.run();
            System.out.println(label + " -> no exception");
        } catch (ValidationException ex) {
            System.out.println(label + " -> "
                    + ex.getClass().getSimpleName());
        }
    }

    static final class UserForm {
        @NotBlank
        String username = "";
    }

    static class BaseService {
        public void send(String code) {
        }
    }

    static final class StrictService extends BaseService {
        @Override
        public void send(@NotNull String code) {
        }
    }

    interface ExtraChecks {
    }

    @GroupSequence({ExtraChecks.class})
    static final class BadDefaultSequence {
        @NotNull
        String code = "OK";
    }

    static final class WrongConstraintType {
        @NotBlank
        Integer id = 42;
    }

    @Target(ElementType.FIELD)
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = BrokenValidator.class)
    public @interface BrokenCheck {
        String message() default "Invalid";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    public static final class BrokenValidator
            implements ConstraintValidator<BrokenCheck, String> {
        @Override
        public boolean isValid(
                String value, ConstraintValidatorContext context) {
            throw new IllegalStateException("Demo: runtime failure");
        }
    }

    static final class BrokenData {
        @BrokenCheck
        String value = "test";
    }
}
~~~

Run in the project root directory configured with the Spring Boot Maven plugin:

~~~bash
./mvnw spring-boot:run
~~~

On Windows: `mvnw.cmd spring-boot:run`; or `mvn spring-boot:run` if Maven is installed globally. Aside from Spring Boot logs, with **default Hibernate Validator** following Jakarta Validation rules, expect these lines:

~~~text
ordinary -> violations=1
declaration -> ConstraintDeclarationException
group -> GroupDefinitionException
type -> UnexpectedTypeException
execution -> ValidationException
~~~

Explanation:

1. `ordinary`: invalid data produces a `ConstraintViolation`.
2. `declaration`: the provider inspects `StrictService` metadata and detects the added parameter constraint on the override.
3. `group`: `BadDefaultSequence` places `@GroupSequence` on the class but omits `BadDefaultSequence.class` itself.
4. `type`: `@NotBlank` applied to `Integer` is incompatible, throwing `UnexpectedTypeException`.
5. `execution`: `BrokenValidator#isValid` throws `IllegalStateException`; the provider wraps the extension error in `ValidationException`.

`show(...)` catches `ValidationException` **solely for demonstration** so the remaining cases can run. Do not swallow exceptions like this in production systems. Providers may detect some declaration errors when querying metadata or when validating; internal codes/messages can vary by version and configuration.

## 7. JUnit 5 tests to verify exact exception types

Add `spring-boot-starter-test` in `pom.xml`:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create **`src/test/java/com/example/validation/ValidationExceptionDemoApplicationTest.java`**:

~~~java
package com.example.validation;

import jakarta.validation.ConstraintDeclarationException;
import jakarta.validation.GroupDefinitionException;
import jakarta.validation.UnexpectedTypeException;
import jakarta.validation.ValidationException;
import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class ValidationExceptionDemoApplicationTest {

    @Autowired
    Validator validator;

    @Test
    void wrongInputReturnsViolations() {
        assertEquals(1, validator.validate(
                new ValidationExceptionDemoApplication.UserForm()).size());
    }

    @Test
    void wrongOverrideThrowsDeclarationException() {
        assertThrows(ConstraintDeclarationException.class,
                () -> validator.getConstraintsForClass(
                        ValidationExceptionDemoApplication.StrictService.class));
    }

    @Test
    void wrongSequenceThrowsGroupDefinitionException() {
        assertThrows(GroupDefinitionException.class,
                () -> validator.validate(
                        new ValidationExceptionDemoApplication
                                .BadDefaultSequence()));
    }

    @Test
    void wrongTypeThrowsUnexpectedTypeException() {
        assertThrows(UnexpectedTypeException.class,
                () -> validator.validate(
                        new ValidationExceptionDemoApplication
                                .WrongConstraintType()));
    }

    @Test
    void thrownValidatorFailureBecomesValidationException() {
        assertThrows(ValidationException.class,
                () -> validator.validate(
                        new ValidationExceptionDemoApplication.BrokenData()));
    }
}
~~~

Run `./mvnw test` (Windows: `mvnw.cmd test`). These tests assert **exception types and contrast with violations**, instead of relying on message text. They also explicitly request metadata/validation of the classes to trigger the errors: you cannot assume the provider will eagerly detect every error at Spring Boot startup.

In CI, you can write dedicated metadata tests for critical DTOs/methods and group sequences to catch misconfigurations before deploying to production.

## 8. Spring MVC: when is it HTTP 400 vs a server error?

For a controller using `@Valid @RequestBody`:

~~~java
@PostMapping("/register")
ResponseEntity<?> register(@Valid @RequestBody UserRequest input) {
    return ResponseEntity.ok().build();
}
~~~

This is a **snippet**, assuming a controller, DTO `UserRequest`, and appropriate Spring MVC/Jakarta imports exist. When input violates a properly declared constraint, Spring MVC normally reports a request validation error. The typical case is `MethodArgumentNotValidException` resulting in an HTTP 400 response. To handle manually, place a `BindingResult` parameter right after the validated parameter and read field/object errors.

However, when the provider throws `ValidationException` due to a code/configuration bug, **do not default to returning 400 as if the user sent bad input**. Instead:

- Log the full exception type, stack trace, cause, and related constraint/group/method on the server.
- Return a safe server error response per application policy without leaking class names, stack traces, or internal details.
- Fix the bug in the annotation, validator, group sequence, or dependencies; never treat the exception as an empty violation set.
- Verify the Spring mechanism in use: with method validation, you may encounter `HandlerMethodValidationException` or `ConstraintViolationException` at another integration layer, distinct from direct `Validator#validate` results.

Do not write a global handler that catches every `ValidationException` and returns 400: that turns server bugs into errors blamed on clients and obscures operational monitoring.

## 9. Diagnostic workflow and troubleshooting checklist

When encountering an exception in validation infrastructure:

1. **Classify the runtime type**: inspect `ex.getClass().getName()`; is it a subclass of `ValidationException`?
2. **Follow the cause chain**: for a plain `ValidationException`, check `getCause()`; this often points straight to the failing extension or dependency.
3. **Identify the phase**: provider bootstrap, metadata lookup (`getConstraintsForClass`), `validate`, or executable validation.
4. **If `ConstraintDeclarationException`**: check data type vs annotation compatibility; inspect method overrides/interfaces, cross-parameter rules, `@ConvertGroup`, and cascading.
5. **If `GroupDefinitionException`**: verify `@GroupSequence` has no cycles, and class-level sequences include the class itself.
6. **Write a reproducer test**: one small class + one metadata/validate call + `assertThrows` for the exact exception class.
7. **After fixing**: re-run both configuration-error tests and normal valid/invalid data tests; ensure `validate` does not unexpectedly throw.

| Symptom | Common cause | Fix |
| --- | --- | --- |
| `UnexpectedTypeException` on `@NotBlank Integer` | Mismatched annotation and data type. | Use `@NotNull` or an appropriate numeric constraint. |
| `ConstraintDeclarationException` on method override | Subtype adds constraints to parameter. | Place on the supertype contract; do not tighten preconditions in subtypes. |
| `GroupDefinitionException` on class `@GroupSequence` | Missing the class itself, or cyclic sequence. | Include the class; break cycles. |
| `ValidationException` with cause from `isValid` | Validator or dependency threw a runtime exception. | Fix the bug/infrastructure issue; use `return false` for normal invalid data. |
| `ConstraintViolation` returned in Set | Input failed a valid constraint. | Handle and display input validation errors. |

### Common pitfalls

- Thinking **every validation issue is an exception**: invalid input against valid constraints normally only produces violations.
- Catching broad `ValidationException` and swallowing it or returning HTTP 400 for everything.
- Confusing **constraint definition** (malformed custom annotation) with **constraint declaration** (valid annotation used illegally).
- Putting `@GroupSequence({Default.class, Extra.class})` on a class to replace Default; class-level sequences must name the class itself.
- Guessing errors from an `HV000...` message instead of checking the exception class and root cause.
- Testing only good/bad inputs without verifying metadata, group sequences, and exception handling in custom validators.
- Mixing legacy `javax.validation.*` with modern `jakarta.validation.*` in Spring Boot 3+.

## References

- Jakarta Validation 3.1 specification — **Exception model**: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Jakarta Validation API 3.1.1 — exceptions in package `jakarta.validation`: https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.1.1/jakarta/validation/package-summary.html
- Hibernate Validator 8 Reference Guide — method constraints, groups, and custom constraints: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Spring Framework — Bean Validation: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC — request-body validation: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html
