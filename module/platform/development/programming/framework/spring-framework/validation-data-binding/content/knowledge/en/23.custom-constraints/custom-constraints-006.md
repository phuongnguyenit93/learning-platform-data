# ConstraintValidatorContext and Creating Custom Messages

## 1. Purpose and place in Spring Validation

When writing a custom Bean Validation constraint, `ConstraintValidator#isValid(...)` decides whether data is valid. The `ConstraintValidatorContext` parameter lets you control **error messages**, **error count**, and **the property path where an error is attached**. This is a useful tool for rules spanning multiple fields, such as password and confirmation password matching.

Typical processing flow:

1. A data class (DTO/record/bean) is annotated with a constraint annotation, such as `@PasswordMatches`.
2. Spring triggers Jakarta Bean Validation when a parameter is marked with `@Valid` or `@Validated`, or when the application calls `jakarta.validation.Validator#validate`.
3. The provider (typically Hibernate Validator in Spring Boot) calls `isValid(value, context)`.
4. If it returns `false`, the provider creates one or more `ConstraintViolation`s from the default message and/or custom builders.
5. Spring MVC converts violations into binding/validation errors or an HTTP 400 response depending on how the controller handles them.

**Distinction:** `jakarta.validation.ConstraintValidator` and `jakarta.validation.Validator` belong to Jakarta Validation; `org.springframework.validation.Validator` is a different interface using `Errors.reject(...)`/`rejectValue(...)`. `ConstraintValidatorContext` belongs to the former mechanism. In Spring Boot 3+, import `jakarta.validation.*`, not the legacy `javax.validation.*`.

## 2. Key APIs of ConstraintValidatorContext

| API | Role | When to use |
| --- | --- | --- |
| `getDefaultConstraintMessageTemplate()` | Gets the uninterpolated message template from the annotation's `message` attribute. | When you want to keep the message configured by the annotation user, but attach it to a different field. |
| `disableDefaultConstraintViolation()` | Prevents generating the annotation's default violation. | When replacing an object-level error with a specific field error or multiple separate errors. |
| `buildConstraintViolationWithTemplate(String)` | Starts defining a violation with a new message or i18n key. | When changing wording, adding context, or building a different path. |
| `addPropertyNode("fieldName")` | Appends a property to the current error path. | For class-level constraints, attaches the error to a field like `confirmPassword`. |
| `addBeanNode()` | Appends a bean node to the path; used in deep object/container structures. | When needing to point to the child bean itself rather than a property. |
| `addConstraintViolation()` | **Finalizes the builder and registers the violation**. | Mandatory for every custom violation you want to create. |

Methods such as `addContainerElementNode(...)`, `inIterable().atIndex(...)`, and `inIterable().atKey(...)` target paths inside lists/maps. `addParameterNode(index)` is only for cross-parameter constraints on methods/constructors, not arbitrary DTOs.

Short example when a rule is placed at the **class level**:

~~~java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        context.getDefaultConstraintMessageTemplate())
    .addPropertyNode("confirmPassword")
    .addConstraintViolation();
return false;
~~~

Without calling `addPropertyNode(...)`, a class-level error usually has an empty path (an object-wide error). Adding the `confirmPassword` node makes `ConstraintViolation#getPropertyPath()` become `confirmPassword`, helping Spring or the UI point to the right input field.

## 3. Three ways to create error messages

**Approach A — use the default annotation message.** If `isValid` returns `false` without calling any context methods, Bean Validation creates one violation using the annotation's `message` on the element currently being validated.

~~~java
@Override
public boolean isValid(String value, ConstraintValidatorContext context) {
    return value == null || value.startsWith("SPR-");
}
~~~

Here the snippet only illustrates the validator body for a field-level constraint. With annotation `message = "Code must start with SPR-"`, the violation uses that exact message.

**Approach B — replace the message while keeping the path.** Use the builder and disable the default error:

~~~java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate("Code does not match any supported format")
    .addConstraintViolation();
return false;
~~~

**Approach C — customize both message and path.** For constraints on a DTO, add `addPropertyNode(...)` before `addConstraintViolation()`. This is the standard way to surface a cross-field check error next to the field that needs fixing.

Note: `disableDefaultConstraintViolation()` does not create a new error on its own. If you return `false` after disabling the default error without completing at least one builder with `addConstraintViolation()`, the provider has no valid violation to report and may throw `ValidationException`. If you do not disable the default error, a custom error may appear **alongside** the default error, causing duplicate messages.

## 4. Complete example: confirmation password must match

The example uses **Java 17+**, Spring Boot 3+ or a newer Jakarta Validation-compatible version. In a Spring Boot project configured with Maven, add the following dependency if not already present:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
~~~

Place the following program at `src/main/java/com/example/validation/ValidationDemoApplication.java`. This is a complete Java file: the annotation, validator, data record, and `main` entry point are all inside the file.

~~~java
package com.example.validation;

import jakarta.validation.Constraint;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import jakarta.validation.Payload;
import jakarta.validation.Validator;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Comparator;
import java.util.Objects;

@SpringBootApplication
public class ValidationDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }

    @Bean
    ApplicationRunner showValidation(Validator validator) {
        return args -> validator.validate(
                        new Registration("abc123", "xyz456"))
                .stream()
                .sorted(Comparator.comparing(
                        violation -> violation.getPropertyPath().toString()))
                .forEach(violation -> System.out.println(
                        violation.getPropertyPath() + ": "
                                + violation.getMessage()));
    }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @Constraint(validatedBy = PasswordMatchesValidator.class)
    public @interface PasswordMatches {
        String message() default "Confirmation password does not match";
        Class<?>[] groups() default {};
        Class<? extends Payload>[] payload() default {};
    }

    public static final class PasswordMatchesValidator
            implements ConstraintValidator<PasswordMatches, Registration> {

        @Override
        public boolean isValid(
                Registration value, ConstraintValidatorContext context) {
            // Let @NotBlank handle null/blank; avoid overlapping errors.
            if (value == null
                    || value.password() == null
                    || value.confirmPassword() == null
                    || value.password().isBlank()
                    || value.confirmPassword().isBlank()) {
                return true;
            }

            if (Objects.equals(
                    value.password(), value.confirmPassword())) {
                return true;
            }

            context.disableDefaultConstraintViolation();
            context.buildConstraintViolationWithTemplate(
                    context.getDefaultConstraintMessageTemplate())
                    .addPropertyNode("confirmPassword")
                    .addConstraintViolation();
            return false;
        }
    }

    @PasswordMatches
    public record Registration(
            @NotBlank String password,
            @NotBlank String confirmPassword) {
    }
}
~~~

Run from the Spring Boot project directory with Maven wrapper using `./mvnw spring-boot:run` (Windows: `mvnw.cmd spring-boot:run`), or `mvn spring-boot:run` when Maven is installed. Apart from startup logs, the program prints the exact line produced by `showValidation`:

~~~text
confirmPassword: Confirmation password does not match
~~~

Part-by-part explanation:

- `@Target(ElementType.TYPE)` specifies the constraint is for a class/record because **two** fields must be compared. `@Retention(RUNTIME)` allows reading the annotation at runtime.
- `@Constraint(validatedBy = PasswordMatchesValidator.class)` links the annotation to the validator; the three standard attributes `message`, `groups`, `payload` are required elements of a custom constraint.
- The validated type in `ConstraintValidator<PasswordMatches, Registration>` matches the annotated record. `isValid` is called by the provider, no direct call is needed.
- When either field is blank, `@NotBlank` is responsible for reporting its own error. The class-level constraint treats it as valid for now to avoid producing a noisy second message.
- When both values have content but differ, the validator disables the class-level violation and builds a violation at `confirmPassword`. The result is **one error attached to the exact field**, even though the annotation sits on the entire record.
- `getDefaultConstraintMessageTemplate()` preserves the annotation's `message` configuration. If the annotation message or resource bundle changes later, the validator does not need editing.
- `Validator#validate(...)` returns `Set<ConstraintViolation<Registration>>`. A set **guarantees no order**; the example uses `sorted(...)` before printing for readable output. With the sample data there is only one error.

Changing `confirmPassword` to `"abc123"` produces zero violations. If `confirmPassword` is blank, `@NotBlank` produces an error on that field, while `PasswordMatchesValidator` skips the pairing check.

## 5. Creating multiple errors from a single check

A class-level validator can report multiple distinct reasons, as long as each builder ends with `addConstraintViolation()`. The snippet below only illustrates **the logic inside `isValid`** for a DTO with `start`/`end` properties; it is not a standalone program:

~~~java
boolean missingStart = value.start() == null;
boolean missingEnd = value.end() == null;

if (!missingStart && !missingEnd) {
    return true;
}

context.disableDefaultConstraintViolation();

if (missingStart) {
    context.buildConstraintViolationWithTemplate(
            "Start date is required")
        .addPropertyNode("start")
        .addConstraintViolation();
}

if (missingEnd) {
    context.buildConstraintViolationWithTemplate(
            "End date is required")
        .addPropertyNode("end")
        .addConstraintViolation();
}

return false;
~~~

If both values are missing, the result has **two** violations, one with path `start` and one with path `end`. In practice, if you only need to check non-`null`, prefer `@NotNull` on each field; use class-level context when the rule needs to inspect **relationships** between fields or construct dynamic paths per business logic.

For nested properties, from a class-level constraint you can build path `address.postalCode` with:

~~~java
context.buildConstraintViolationWithTemplate("Invalid postal code")
    .addPropertyNode("address")
    .addPropertyNode("postalCode")
    .addConstraintViolation();
~~~

Node names must match the model structure. For a constraint already placed on a property, the builder **appends** nodes to the existing path; do not assume every path starts from the root. For lists/maps, use the corresponding container/iterable API to preserve indices/keys with proper semantics.

## 6. Connecting with Spring MVC and handling responses

Assuming the application also includes `spring-boot-starter-web`, a controller can receive data via `@Valid @RequestBody`:

~~~java
package com.example.validation;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.annotation.*;

import java.util.Map;
import java.util.Objects;

@RestController
@RequestMapping("/registrations")
class RegistrationController {

    @PostMapping
    ResponseEntity<?> create(
            @Valid @RequestBody ValidationDemoApplication.Registration input,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            var details = bindingResult.getFieldErrors().stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "message", Objects.toString(
                                    error.getDefaultMessage(), "")))
                    .toList();
            return ResponseEntity.badRequest().body(details);
        }

        return ResponseEntity.ok(Map.of("status", "accepted"));
    }
}
~~~

With request:

~~~json
{
  "password": "abc123",
  "confirmPassword": "xyz456"
}
~~~

HTTP 400 response produced by the controller above:

~~~json
[
  {
    "field": "confirmPassword",
    "message": "Confirmation password does not match"
  }
]
~~~

Place `BindingResult` **immediately after** the `@Valid @RequestBody` parameter. If you do not accept `BindingResult` directly and have no other special method validation mechanism, Spring MVC typically throws `MethodArgumentNotValidException` when the request object is invalid and returns HTTP 400 by default. If validation is applied across multiple parameters/methods, `HandlerMethodValidationException` may occur; error handling must account for the validation style in use.

Important distinction between error paths:

- Property-level errors (e.g. `confirmPassword`) are typically mapped to `FieldError`, accessed via `bindingResult.getFieldErrors()`.
- Object-level errors without a property node usually become `ObjectError`/global errors, inspected via `bindingResult.getGlobalErrors()` or `getAllErrors()`. A controller reading only field errors as in the example will miss these global errors.
- `ConstraintValidatorContext` creates **validation violations**; it does not decide HTTP status codes, JSON formats, or UI translations on its own. Those belong to the Spring MVC and application layers.

## 7. Message interpolation and internationalization

The string passed to `buildConstraintViolationWithTemplate(...)` is a **template**, not necessarily the final displayed message. Jakarta Validation interpolates the template according to the provider and message interpolator configuration.

You can change the annotation attribute to:

~~~java
String message() default "{registration.password.mismatch}";
~~~

Define `src/main/resources/ValidationMessages.properties`:

~~~properties
registration.password.mismatch=Confirmation password does not match
~~~

And the Vietnamese version in `src/main/resources/ValidationMessages_vi.properties`:

~~~properties
registration.password.mismatch=Mật khẩu xác nhận không trùng khớp
~~~

The validator continues using:

~~~java
context.buildConstraintViolationWithTemplate(
        context.getDefaultConstraintMessageTemplate())
    .addPropertyNode("confirmPassword")
    .addConstraintViolation();
~~~

When the provider selects the Vietnamese locale, `ConstraintViolation#getMessage()` contains the interpolated sentence; `getMessageTemplate()` retains the original template. The exact locale depends on the message interpolator/provider setup and how the application manages locale; do not assume the HTTP locale automatically applies to every validation pass running outside a web request.

Some templates can use annotation parameters, such as `{min}` in a constraint with a `min` attribute. Avoid concatenating untrusted user input directly into templates: it can lead to unpredictable messages or alter interpolation syntax meaning. If data-dependent text is needed, choose safe wording or handle parameters/escaping through provider-supported mechanisms. Do not rely on Hibernate Validator proprietary extension APIs when standard Jakarta Validation suffices.

## 8. Testing behavior and common pitfalls

Tests must verify **both message content and property path**. JUnit 5 example in a Spring Boot project with `spring-boot-starter-test`:

~~~java
package com.example.validation;

import jakarta.validation.Validator;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest
class PasswordMatchesTest {
    @Autowired
    Validator validator;

    @Test
    void mismatchIsAttachedToConfirmationField() {
        var input = new ValidationDemoApplication.Registration(
                "abc123", "xyz456");

        var violations = validator.validate(input);

        assertEquals(1, violations.size());
        var violation = violations.iterator().next();
        assertEquals("confirmPassword",
                violation.getPropertyPath().toString());
        assertEquals("Confirmation password does not match",
                violation.getMessage());
    }

    @Test
    void matchingPasswordsHaveNoViolations() {
        var input = new ValidationDemoApplication.Registration(
                "abc123", "abc123");
        assertEquals(0, validator.validate(input).size());
    }
}
~~~

Run `./mvnw test` (Windows: `mvnw.cmd test`) in a project with test dependencies and valid Spring Boot configuration.

Common mistakes to avoid:

1. **Forgetting `addConstraintViolation()`:** the builder has not registered the violation yet; finish every error branch.
2. **Disabling default without adding an error:** returning `false` from `isValid` with no violations is an invalid state.
3. **Forgetting to disable default when replacing:** produces two messages (default and custom) for the same cause.
4. **Wrong annotation level or path:** a class-level constraint does not automatically become a field error; call `addPropertyNode(...)` if you want a field error.
5. **Using `@Valid` on objects without a provider/dependency:** the annotation alone is not enough if Bean Validation is not configured; in Spring Boot use the validation starter.
6. **Confusing `javax.validation` with `jakarta.validation`:** Spring Boot 3+ uses the Jakarta namespace; avoid mixing the two generations.
7. **Reading only `getFieldErrors()` when errors are global:** use `getAllErrors()`/`getGlobalErrors()` or fix the path to match intent.
8. **Wrong generic types or assuming violation order:** generic parameters of `ConstraintValidator<A,T>` must match the target type, and `Set<ConstraintViolation<?>>` guarantees no order.
9. **Side-effecting validators or unsafe shared state:** `isValid` should check and build violations deterministically; validator instances may be reused by the provider, so avoid per-request mutable state.
10. **Treating client validation as sufficient:** server-side rules must still execute, especially for multi-field relationships and business data.

### Quick application checklist

- Annotation has `@Constraint`, `@Target`, `@Retention(RUNTIME)`, and the three attributes `message/groups/payload`.
- Validator handles `null`/blank intentionally, matches the exact data type, and returns `true/false` per the rule.
- When replacing the message, call `disableDefaultConstraintViolation()` and fully build at least one custom violation.
- When targeting a specific field, add `addPropertyNode("fieldName")`; when creating multiple errors, use a fresh builder for each error.
- Test `propertyPath`, `message`, valid cases, and missing-data cases; if integrated with MVC, also test the HTTP response.

## References

- Jakarta Validation API — `ConstraintValidatorContext`: https://jakarta.ee/specifications/platform/10/apidocs/jakarta/validation/constraintvalidatorcontext
- Jakarta Validation API — `ConstraintViolationBuilder`: https://javadoc.io/static/jakarta.validation/jakarta.validation-api/3.1.1/jakarta/validation/ConstraintValidatorContext.ConstraintViolationBuilder.html
- Spring Framework — `@RequestBody` and validation handling: https://docs.spring.io/spring/reference/7.1/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Framework — MVC validation: https://docs.spring.io/spring-framework/reference/7.1/web/webmvc/mvc-controller/ann-validation.html
