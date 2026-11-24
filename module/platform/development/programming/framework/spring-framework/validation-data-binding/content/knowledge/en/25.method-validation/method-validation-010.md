# Cross-Parameter Constraints on Methods

## 1. When Do You Need to Validate *Relationships Between Multiple Parameters*?

In Jakarta Bean Validation, annotations like `@NotNull`, `@Min`, or `@Email` typically validate **a single parameter**. Yet many rules cannot be evaluated on individual parameters in isolation:

- `book(startDate, endDate)`: start date must not be after end date.
- `transfer(fromAccount, toAccount, amount)`: source and destination accounts must differ.
- `changePassword(newPassword, confirmation)`: both parameters must match.
- `schedule(from, to, zone)`: the time interval must be valid in the chosen time zone.

These are **cross-parameter constraints**. The annotation is placed directly on the **method** or **constructor**, and the validator receives **the array of arguments for the entire call**, rather than a single value. It belongs to Jakarta Validation's *executable validation* (method/constructor validation) and works with Spring Framework.

Comparing validation levels:

| Level | Where is the annotation placed? | What does `isValid(...)` receive? | Appropriate when |
| --- | --- | --- | --- |
| Single-parameter constraint | `void book(@NotNull LocalDate start)` | One parameter value (e.g., `LocalDate`) | Requirement on a single value. |
| **Cross-parameter** | `@ValidDateRange void book(LocalDate start, LocalDate end)` | **`Object[]` containing all arguments** | Relationship across multiple parameters in one call. |
| Return-value constraint | `@NotNull String findName()` | Return value, checked by return-value validation API | Output contract. |
| Class-level constraint | `@DatesConsistent class BookingRequest` | One DTO object | Relationship across fields/properties of a bean. |

The `@ValidDateRange` name above is illustrative. Unlike a class-level constraint on a DTO, a cross-parameter constraint validates the call signature directly without forcing you to wrap arguments in a DTO just to compare them.

**Critical point:** an annotation on a method **does not automatically run simply because Java invokes the method**. Something must invoke `ExecutableValidator`, or an integration mechanism such as a Spring proxy/method interceptor must be active.

## 2. Required Anatomy of a Cross-Parameter Constraint

A custom cross-parameter constraint has two parts:

1. **Constraint annotation**: declares where the annotation can be placed, its validator, and the error message.
2. **`ConstraintValidator<Annotation, Object[]>`**: inspects the parameter array and returns `true/false`; annotated with `@SupportedValidationTarget(ValidationTarget.PARAMETERS)`.

General structure:

~~~java
@Target({ElementType.METHOD, ElementType.CONSTRUCTOR,
         ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ConsistentParametersValidator.class)
public @interface ConsistentParameters {
    String message() default "Parameters are inconsistent";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

This is a **template declaration** inside a file with appropriate imports; a complete runnable program appears in section 3.

For the validator:

~~~java
@SupportedValidationTarget(ValidationTarget.PARAMETERS)
public final class ConsistentParametersValidator
        implements ConstraintValidator<ConsistentParameters, Object[]> {

    @Override
    public boolean isValid(Object[] args,
                           ConstraintValidatorContext context) {
        // Check correlation among args elements.
        return true;
    }
}
~~~

These two declarations illustrate the core API and are not standalone source files. Key things to understand:

- `ElementType.METHOD` and `ElementType.CONSTRUCTOR` allow placing the annotation on methods and constructors. `ANNOTATION_TYPE` is useful for constraint composition.
- `@Constraint(validatedBy = ...)` links the annotation to its implementation.
- `message`, `groups`, and `payload` are the standard attributes of a custom constraint.
- `@SupportedValidationTarget(ValidationTarget.PARAMETERS)` tells the provider this validator targets the **parameter list**, not the return value. Import from `jakarta.validation.constraintvalidation`.
- The validated type here is `Object[]` (Jakarta Validation also permits `Object` per contract); a regular `ConstraintValidator<..., LocalDate>` only handles a single value and cannot replace cross-parameter checks.
- `args[0]` is the first argument; `args[1]` is the second. Indexes follow **parameter position** on the annotated method/constructor, not source variable names.
- Null handling should be intentional: typically **return `true` when a parameter being compared is null**, while placing `@NotNull` on individual parameters to avoid two messages for one missing input. Returning `true` here only means the *cross-constraint* does not fail; other constraints can still fail.

### Parameter-Only Constraints vs. Constraints Targeting Both Parameters and Return Values

An annotation defined **strictly** for cross-parameter validation with a `ValidationTarget.PARAMETERS` validator usually does not need a `validationAppliesTo` attribute because the target is unambiguous. However, if an annotation supports **both generic/return-value and cross-parameter** targets, placing it on a method can be ambiguous. In that case the annotation needs:

~~~java
ConstraintTarget validationAppliesTo() default ConstraintTarget.IMPLICIT;
~~~

And callers can specify `validationAppliesTo = ConstraintTarget.PARAMETERS` (or `RETURN_VALUE`), especially when a method has both parameters and a return value so the target cannot be inferred. Import `jakarta.validation.ConstraintTarget`. **Do not add both targets casually** if the constraint only ever checks arguments; a dedicated cross-parameter validator is clearer.

## 3. Spring Boot 3+, Java 17+ Example: Start Date Not After End Date

This example runs with **Java 17+** and a **Spring Boot 3+** project compatible with Jakarta Validation, using Maven. Dependency needed:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Create **`src/main/java/com/example/validation/CrossParameterDemoApplication.java`** with the **full contents**:

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.Validator;
import jakarta.validation.constraintvalidation.SupportedValidationTarget;
import jakarta.validation.constraintvalidation.ValidationTarget;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.executable.ExecutableValidator;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.lang.reflect.Method;
import java.time.LocalDate;

@SpringBootApplication
public class CrossParameterDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(CrossParameterDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner runDemo(Validator validator) {
        return args -> {
            BookingService service = new BookingService();

            Method method = BookingService.class.getMethod(
                    "reserve", LocalDate.class, LocalDate.class);

            ExecutableValidator executable = validator.forExecutables();

            Object[] valid = {
                    LocalDate.of(2026, 11, 10),
                    LocalDate.of(2026, 11, 12)
            };
            Object[] invalid = {
                    LocalDate.of(2026, 11, 12),
                    LocalDate.of(2026, 11, 10)
            };
            Object[] missing = {
                    null,
                    LocalDate.of(2026, 11, 12)
            };

            var validResults =
                    executable.validateParameters(service, method, valid);
            var invalidResults =
                    executable.validateParameters(service, method, invalid);
            var missingResults =
                    executable.validateParameters(service, method, missing);

            System.out.println("valid -> " + validResults.size());
            System.out.println("reversed -> " + invalidResults.size());
            System.out.println("missing -> " + missingResults.size());

            invalidResults.forEach(v ->
                    System.out.println("message -> " + v.getMessage()));
        };
    }

    @Target({ElementType.METHOD, ElementType.CONSTRUCTOR,
             ElementType.ANNOTATION_TYPE})
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = DateRangeValidator.class)
    public @interface ValidDateRange {
        String message() default
                "Start date must not be after end date";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    @SupportedValidationTarget(ValidationTarget.PARAMETERS)
    public static final class DateRangeValidator
            implements ConstraintValidator<ValidDateRange, Object[]> {

        @Override
        public boolean isValid(
                Object[] values, ConstraintValidatorContext context) {

            if (values == null || values.length != 2) {
                throw new IllegalArgumentException(
                        "@ValidDateRange requires exactly 2 parameters");
            }

            // Let @NotNull on individual parameters detect missing data.
            if (values[0] == null || values[1] == null) {
                return true;
            }

            if (!(values[0] instanceof LocalDate start)
                    || !(values[1] instanceof LocalDate end)) {
                throw new IllegalArgumentException(
                        "@ValidDateRange requires 2 LocalDate values");
            }

            return !start.isAfter(end);
        }
    }

    public static class BookingService {

        @ValidDateRange
        public void reserve(
                @NotNull LocalDate start,
                @NotNull LocalDate end) {
            // Booking business logic will be handled here.
        }
    }
}
~~~

Run from the Spring Boot project directory with Maven wrapper and Boot plugin:

~~~bash
./mvnw spring-boot:run
~~~

On Windows use `mvnw.cmd spring-boot:run`; if Maven is installed globally, use `mvn spring-boot:run`.

Excluding startup logs, **four lines printed by `ApplicationRunner`**:

~~~text
valid -> 0
reversed -> 1
missing -> 1
message -> Start date must not be after end date
~~~

Explanation of results:

1. `valid`: Nov 10, 2026 to Nov 12, 2026, valid ordering; zero violations.
2. `reversed`: start date is after end date, `DateRangeValidator#isValid` returns `false`; the provider creates **one** `ConstraintViolation` with `@ValidDateRange`'s `message`.
3. `missing`: the first parameter is null. The cross-parameter validator returns `true` per responsibility split, yet `@NotNull` on the first parameter produces **one** violation.
4. `validateParameters(...)` only checks constraints on the arguments; it **does not invoke** `BookingService#reserve(...)`. Thus no business side effects happen in the example.

**Why check the signature?** The annotation could accidentally be placed on another method with an incompatible parameter count or types. The validator should not index directly into `values[1]` without checking. Throwing `IllegalArgumentException` here is strictly for **programming/signature misuse errors**, not for `start > end` data. Providers may wrap exceptions from custom validators in `ValidationException`. For business rule violations, return `false`.

**Date note:** In the code, `LocalDate.of(2026, 11, 10)` is November 10, 2026. If business rules require strict `start < end`, replace `!start.isAfter(end)` with `start.isBefore(end)` and update the message and tests to match the contract.

## 4. `ExecutableValidator` API and Execution Scope

`jakarta.validation.Validator` exposes `forExecutables()`. The `jakarta.validation.executable.ExecutableValidator` interface provides four validation methods:

| Method | Used to |
| --- | --- |
| `validateParameters(object, method, args, groups...)` | Validate **all constraints on method parameters**, including single-parameter and cross-parameter rules. |
| `validateReturnValue(object, method, returnValue, groups...)` | Validate constraints on the **return value** of a method. |
| `validateConstructorParameters(constructor, args, groups...)` | Validate constructor parameters, including cross-parameter rules. |
| `validateConstructorReturnValue(constructor, createdObject, groups...)` | Validate constraints on the newly constructed object from a constructor. |

`groups...` selects validation groups; when omitted, the `Default` group runs per Jakarta Validation rules.

Explicit method validation flow:

~~~text
Obtain Method via reflection
        |
        v
Validator.forExecutables()
        |
        v
validateParameters(service, method, actualArgs)
        |
        +-- @NotNull on individual parameters
        |
        +-- @ValidDateRange on the entire Object[]
        |
        v
Set<ConstraintViolation<BookingService>>
        |
        +-- empty: safe to invoke business method
        |
        +-- has errors: return response / throw exception per application layer
~~~

Note: `validator.validate(service)` **does not** automatically validate parameters of methods that have not been invoked; that API validates constraints on a **bean/object**. To validate executables, use the corresponding API or a Spring mechanism configured to trigger on method calls.

### Constructor Cross-Parameter Constraints

A custom annotation with `@Target(CONSTRUCTOR)` and a `ValidationTarget.PARAMETERS` validator works with constructors too. **Illustrative** definition (assuming `@ValidDateRange` from the program above):

~~~java
public final class BookingPeriod {
    @ValidDateRange
    public BookingPeriod(LocalDate start, LocalDate end) {
    }
}
~~~

To validate **before instantiation**, obtain the constructor:

~~~java
var constructor = BookingPeriod.class.getConstructor(
        LocalDate.class, LocalDate.class);
var violations = validator.forExecutables()
        .validateConstructorParameters(constructor,
                new Object[] {LocalDate.of(2026, 11, 12),
                              LocalDate.of(2026, 11, 10)});
~~~

These two snippets are illustrative excerpts inside a project with matching imports and annotations, not standalone Java files. `validateConstructorParameters` does not execute `new BookingPeriod(...)`; the application or integration layer decides whether to invoke the constructor.

## 5. Attaching the Error to a Specific Parameter with `ConstraintValidatorContext`

By default, a cross-parameter violation has a **path pointing to the parameter list** of the method, such as a path containing a node with `ElementKind.CROSS_PARAMETER`. This indicates a relationship error across multiple arguments, not an error on `start` or `end` alone.

Sometimes a UI needs to display the error next to the `end` parameter. You can build a custom violation and attach a **parameter node at index 1**. Replace the end of `isValid` in `DateRangeValidator` from section 3 with the following (**code fragment**, not a standalone source file):

~~~java
if (!start.isAfter(end)) {
    return true;
}

context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        context.getDefaultConstraintMessageTemplate())
        .addParameterNode(1)
        .addConstraintViolation();
return false;
~~~

Behavior:

- `disableDefaultConstraintViolation()` suppresses the default cross-parameter-level violation.
- `buildConstraintViolationWithTemplate(...)` sets the message for the new violation; `getDefaultConstraintMessageTemplate()` preserves the message configured on the annotation.
- `addParameterNode(1)` targets the violation at the **second parameter** of the executable (`end`) using zero-based indexing.
- `addConstraintViolation()` is **required** to finalize the builder. If you disable the default and return `false` without adding at least one custom violation, the provider may throw an exception.
- `ConstraintViolation#getPropertyPath()` will reflect a parameter node instead of only a cross-parameter node.

**Parameter names in paths** depend on `ParameterNameProvider` and compilation metadata (such as `-parameters`) or provider integration. You might see `arg1` instead of `end`; in portable tests, check `ParameterNode#getParameterIndex() == 1` instead of hardcoding parameter name strings.

Do not use `addPropertyNode("end")` to represent a **method argument** when your goal is to mark a parameter; the right API is `addParameterNode(index)`. `addPropertyNode(...)` is for bean/object property paths.

## 6. Integrating with Spring: Triggering Method Validation

Jakarta Validation **defines constraints and APIs**, yet does not automatically intercept every Java call. In Spring there are two common paths.

### 6.1. Service Beans via Spring Proxies

In Spring Boot with a Bean Validation provider and method validation enabled, annotate the bean with `@Validated` so Spring uses a method-validation interceptor/proxy. The example below illustrates applying the annotation from section 3:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

@Service
@Validated
public class BookingService {
    @ValidDateRange
    public void reserve(@NotNull LocalDate start,
                        @NotNull LocalDate end) {
        // Business operation.
    }
}
~~~

This is a **snippet for a separate class**; you cannot declare two classes with the same name as in the demo program simultaneously. If placed in a separate file, import `@ValidDateRange`/`@NotNull` from their proper packages. In Spring Boot applications, `MethodValidationPostProcessor` is usually auto-configured when Bean Validation is present. In manual plain Spring Framework setups, register that bean explicitly; when AOP proxying is needed, ensure Spring AOP infrastructure dependencies are present.

Notes:

- You must **call through the Spring bean proxy**; instantiating `new BookingService()` directly or calling `this.reserve(...)` on the same instance bypasses normal proxy method validation.
- Placing `@Validated` alone does not prove every call is intercepted: it still depends on bean lifecycle, proxying, configuration, and invocation path.
- A parameter error in AOP method validation is normally reported as `jakarta.validation.ConstraintViolationException` (unless Spring is configured to adapt it into `MethodValidationException` or another integration applies). Do not assume there is always a single exception type.
- Constraints on overridden/interface methods are also subject to Jakarta Validation method inheritance rules; avoid adding parameter constraints on overrides against the contract.

### 6.2. Controllers in Spring MVC

Since **Spring Framework 6.1**, Spring MVC has built-in method validation for handler methods. When constraint annotations are placed directly on parameters/methods, method validation can run and Spring can throw `HandlerMethodValidationException`.

Spring recommends **omitting `@Validated` on the controller class** if you want to use MVC's built-in mechanism (rather than AOP proxying on the controller). Exactly how a cross-parameter constraint is processed and represented also depends on the signature, Bean Validation configuration, and Spring version. When designing an API, write integration tests against your real setup, including how cross-parameter errors map to HTTP responses.

**Distinction from `@Valid @RequestBody`:** `@Valid` primarily triggers validation on a bound DTO/body; if the relationship to check is **between fields of a single DTO**, a class-level constraint on the DTO is usually clearer than a cross-parameter constraint. If the relationship is **between multiple independent method arguments**, a cross-parameter constraint fits.

## 7. JUnit 5 Tests for Cross-Parameter Constraints

In the example Spring Boot project, add the test starter if not already present:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
~~~

Create **`src/test/java/com/example/validation/CrossParameterDemoApplicationTest.java`**:

~~~java
package com.example.validation;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotNull;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import java.lang.reflect.Method;
import java.time.LocalDate;
import java.util.Set;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest
class CrossParameterDemoApplicationTest {

    @Autowired
    Validator validator;

    private Set<ConstraintViolation<
            CrossParameterDemoApplication.BookingService>> check(
                    LocalDate start, LocalDate end) throws Exception {

        var service =
                new CrossParameterDemoApplication.BookingService();

        Method method = service.getClass().getMethod(
                "reserve", LocalDate.class, LocalDate.class);

        return validator.forExecutables().validateParameters(
                service, method, new Object[] {start, end});
    }

    @Test
    void acceptsChronologicalDates() throws Exception {
        assertTrue(check(
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 12)).isEmpty());
    }

    @Test
    void reportsOneCrossParameterViolation() throws Exception {
        var violations = check(
                LocalDate.of(2026, 11, 12),
                LocalDate.of(2026, 11, 10));

        assertEquals(1, violations.size());
        var violation = violations.iterator().next();

        assertEquals(
                CrossParameterDemoApplication.ValidDateRange.class,
                violation.getConstraintDescriptor()
                        .getAnnotation().annotationType());

        assertEquals("Start date must not be after end date",
                violation.getMessage());
    }

    @Test
    void letsNotNullReportMissingArgument() throws Exception {
        var violations = check(null, LocalDate.of(2026, 11, 12));

        assertEquals(1, violations.size());
        var annotationType = violations.iterator().next()
                .getConstraintDescriptor().getAnnotation()
                .annotationType();

        assertEquals(NotNull.class, annotationType);
    }

    @Test
    void acceptsEqualDatesAccordingToThisRule() throws Exception {
        assertTrue(check(
                LocalDate.of(2026, 11, 12),
                LocalDate.of(2026, 11, 12)).isEmpty());
    }
}
~~~

Run:

~~~bash
./mvnw test
~~~

On Windows: `mvnw.cmd test`. The tests do not need to invoke `BookingService#reserve`, since the goal is testing constraint metadata and `ExecutableValidator` directly. Assertions check violation counts and the **actual annotation type producing the violation**, which is more reliable than assuming `Set<ConstraintViolation<?>>` ordering or provider-generated node names.

If you add the custom violation `addParameterNode(1)` from section 5, add a test traversing `violation.getPropertyPath()` and checking for a `Path.ParameterNode` with `getParameterIndex() == 1`. Avoid asserting raw path strings because `ParameterNameProvider` can change parameter names.

## 8. Edge Cases and Common Pitfalls

### 8.1. Wrong Parameter Count or Types

The validator in section 3 supports only methods/constructors with **exactly two `LocalDate` parameters**. Placing `@ValidDateRange` on `reserve(String code)` throws `IllegalArgumentException` when invoked through the provider, typically wrapped in `ValidationException`. That is a developer bug—fix the annotation or signature; **do not return `false` to turn a coding error into an input validation error**.

Pay attention to parameter order. Changing the signature from `(start, end)` to `(end, start)` without updating the validator reverses the comparison logic.

### 8.2. Placing a Cross-Parameter Constraint on a Zero-Argument Method

Jakarta Validation forbids cross-parameter constraints on executables with **0 parameters**; providers may throw `ConstraintDeclarationException` when inspecting metadata or validating. An annotation on a no-arg getter like `getStatus()` is not the way to validate multiple bean fields; use a class-level constraint instead.

### 8.3. Forgetting `@SupportedValidationTarget` or Wrong Generic Type

A cross-parameter validator **must** declare `@SupportedValidationTarget(ValidationTarget.PARAMETERS)`. Using `ConstraintValidator<ValidDateRange, LocalDate>` can cause the provider to misinterpret the target or fail to locate a matching validator. Use `Object[]` (or `Object` per the spec) for the argument array and import from `jakarta.validation.constraintvalidation`.

### 8.4. Nulls, Exceptions, and Duplicate Messages

A null parameter should not necessarily fail the comparison rule: it is common to `return true` in the cross-constraint and put `@NotNull` on required parameters. If both `@NotNull` and the cross-constraint report errors on null, clients receive two messages for the same root cause. Decide on a clear null policy and test it.

When creating custom messages, `disableDefaultConstraintViolation()` must be paired with at least one builder call to `addConstraintViolation()` whenever returning `false`. Never store `ConstraintValidatorContext` or builders in instance fields; they belong to the current invocation. Validators must be thread-safe because providers may reuse instances.

### 8.5. Method Constraints and Proxy Issues

Calling `new BookingService().reserve(...)` does not trigger validation automatically. Section 3 calls `ExecutableValidator` explicitly; with Spring method validation, you need a properly proxied Spring bean and calls going **through the proxy**. Self-invocation can bypass the interceptor. For controllers, activation differs across Spring generations, so write integration tests for your target version.

### 8.6. Confusing Return-Value Errors with Parameter Errors

Cross-parameter constraints read the input `Object[]` and run inside `validateParameters(...)`. Constraints on the **return value** use separate validators and run inside `validateReturnValue(...)`. If an annotation supports both, disambiguate the target using `validationAppliesTo` whenever ambiguous.

### 8.7. Breaking Inheritance Contracts

Overriding methods may not add parameter constraints that strengthen a parent method's preconditions (per Jakarta Validation rules). Cross-parameter constraints are parameter constraints; misplacing them in interface/superclass hierarchies can raise `ConstraintDeclarationException`. Declare contracts at the right API level and avoid duplicating annotations on overrides.

## 9. Implementation Checklist

- [ ] The rule truly compares two or more arguments, rather than checking a single value or multiple fields inside a DTO.
- [ ] Annotation has `@Target(METHOD/CONSTRUCTOR)`, `@Retention(RUNTIME)`, `@Constraint`, `message`, `groups`, `payload`.
- [ ] Validator declares `@SupportedValidationTarget(ValidationTarget.PARAMETERS)` and `ConstraintValidator<..., Object[]>`.
- [ ] Count, positions, and types of arguments are clearly verified; signature misuse throws a clear programming error.
- [ ] Returns `true/false` for business rules; null semantics align with `@NotNull` on parameters.
- [ ] If building custom violations for a parameter, use `addParameterNode(index)` rather than relying on parameter names in paths.
- [ ] An actual trigger mechanism is in place: `ExecutableValidator` or appropriate Spring method validation.
- [ ] Tests cover valid order, reversed order, equal values, nulls, annotation metadata, groups, and Spring integration if proxied.
- [ ] Checked method overrides, zero-arg cases, constructors, return-value targets, and Jakarta/Spring namespace versions.

## References

- Jakarta Validation specification 3.1 — method and constructor constraints, cross-parameter constraints, executable validation: https://jakarta.ee/specifications/bean-validation/3.1/jakarta-validation-spec-3.1.html
- Hibernate Validator Reference Guide — **Cross-parameter constraints** and `@SupportedValidationTarget`: https://docs.hibernate.org/stable/validator/reference/en-US/html_single/
- Jakarta Validation API — `ExecutableValidator`: https://jakarta.ee/specifications/bean-validation/3.1/apidocs/jakarta/validation/executable/executablevalidator
- Spring Framework Reference — **Method validation**: https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html
- Spring MVC Reference — **Validation** and `HandlerMethodValidationException`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html
