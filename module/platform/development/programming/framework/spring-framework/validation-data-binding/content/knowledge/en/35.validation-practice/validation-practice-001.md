# Building a Form Validator with Spring Validator and Errors

## 1. Practical Problem

You have a course registration form consisting of participant name, email, course, number of seats, and a coupon code. The rules to validate:

1. **Participant name**: must not be empty or whitespace-only.
2. **Email**: required and must have a basic email structure.
3. **Course**: only accepts `JAVA` or `SPRING`.
4. **Seats**: required and must be between 1 and 5.
5. **Coupon code `GROUP`**: if used, at least 3 seats must be registered. This is a cross-field rule that can be reported as a **form-level (global) error**.
6. **Invalid data types** such as `seats=abc`: must respond with a data conversion error, not mask it with a “seats are required” error.
7. Parameters that do not belong to the form, such as `isAdmin=true`, must not be bound into business data automatically.

Instead of relying only on Jakarta Bean Validation constraints like `@NotBlank` and `@Min`, we will build a validator using the **Spring Framework native validation API**:

```java
org.springframework.validation.Validator
org.springframework.validation.Errors
org.springframework.validation.ValidationUtils
```

When integrating with Spring MVC, also use:

```java
org.springframework.web.bind.WebDataBinder
org.springframework.web.bind.annotation.InitBinder
org.springframework.validation.annotation.Validated
org.springframework.validation.BindingResult
```

The goal is not just knowing how to write `if` statements. After this lesson, you will understand how to record field/global errors into `Errors`, attach a validator to the form binder, avoid duplicating `typeMismatch` errors, resolve error codes via `MessageSource`, return stable JSON, and test both the HTTP API and the standalone validator.

**Reference environment:** Java 17+, Spring Framework 6.1.x, Spring Boot 3.3.6, Servlet Spring MVC. The demo project uses **pure Spring Validator**, without requiring Jakarta Validation annotations to trigger checks. If a real project also uses a Bean Validation provider, how they work together is explained later.

## 2. What Are the Responsibilities of Spring Validator, Errors, and BindingResult?

### 2.1. Validator Is a Two-Method Contract

```java
public interface Validator {

    boolean supports(Class<?> clazz);

    void validate(Object target, Errors errors);
}
```

This is an abbreviated signature for explanation, not a source file to copy. Meaning:

- `supports(Class<?> clazz)`: which object type this validator can validate.
- `validate(Object target, Errors errors)`: applies rules and **records errors** into the passed-in `Errors` object.
- The `validate` method normally does not throw exceptions for routine business input violations; instead it calls `errors.rejectValue(...)` or `errors.reject(...)`.
- Exceptions can still occur due to bugs, misconfiguration, accessing non-existent properties, or infrastructure failures. Do not wrap the entire validator in a `catch (Exception)` and treat every failure as “form invalid”.

Spring `Validator` is not `jakarta.validation.Validator`. The two APIs exist side by side with complementary rather than identical roles.

### 2.2. Errors Is Where Violations Accumulate

`Errors` records both field-level and object-level errors:

```java
errors.rejectValue(
        "email",
        "format",
        "Please enter a valid email address"
);

errors.reject(
        "coupon.minimumSeats",
        new Object[]{3},
        "GROUP coupon requires at least {0} seats"
);
```

The first statement is a **field error**: the `email` field has an invalid format. The second statement is a **global/object error**: the relationship between the coupon and the number of seats is invalid.

Commonly used read methods:

| API | Meaning |
| --- | --- |
| `errors.hasErrors()` | There is at least one error of any kind |
| `errors.hasFieldErrors("email")` | Specifically the email field has an error |
| `errors.getFieldError("email")` | Gets a FieldError for email, may be null |
| `errors.getFieldErrors()` | List of all FieldErrors |
| `errors.getGlobalErrors()` | List of form-level ObjectErrors |
| `errors.getAllErrors()` | List of both field and global errors |
| `errors.getErrorCount()` | Total number of errors |
| `errors.getFieldValue("seats")` | Field value as represented by Errors/binding |
| `errors.pushNestedPath("address")` | Switches context to a nested object |
| `errors.popNestedPath()` | Restores the previous nested path |

Do not assume `getFieldValue` is always the converted Java-typed value. For a `BindingResult` created by a binder, when conversion fails it may hold the raw input value for form re-rendering. Do not directly cast based on `getFieldValue` without knowing the binding state.

### 2.3. BindingResult Extends Errors

`BindingResult` extends `Errors` and adds information about the binding process, including:

- Model attribute name.
- `FieldError`s caused by data conversion failures.
- List of suppressed fields when a binding allowlist is configured.
- Error codes resolved via `MessageCodesResolver`.
- Model containing the target and binding result, used for HTML form rendering.

In Spring MVC, a valid controller signature:

```java
@PostMapping("/register")
public ResponseEntity<?> register(
        @Validated @ModelAttribute("registrationForm") RegistrationForm form,
        BindingResult bindingResult) {
    // ...
}
```

`BindingResult` must be placed **immediately after** the validated/bound argument. Without an adjacent `BindingResult`, Spring MVC may throw `MethodArgumentNotValidException` for standard argument validation errors instead of passing errors to the handler.

**Exact distinction:** `Errors` is the error recording/reading API used by validators; `BindingResult` is the implementation/extension tied to a specific binding process. You can invoke a validator manually with a `BeanPropertyBindingResult` without an HTTP request.

## 3. Three Categories of Errors in a Form

### 3.1. Single-Field Value Errors

Blank name:

```java
errors.rejectValue(
        "participantName",
        "required",
        "Participant name is required"
);
```

Invalid email:

```java
errors.rejectValue(
        "email",
        "format",
        "Please enter a valid email address"
);
```

Invalid seat count:

```java
errors.rejectValue(
        "seats",
        "range",
        new Object[]{1, 5},
        "Seats must be between {0} and {1}"
);
```

The strings `required`, `format`, `range` are **error codes**, not HTTP statuses or translations. You can map them to locale-specific messages via `MessageSource`.

### 3.2. Form-Wide (Global) Errors

A coupon is only valid when `seats >= 3`:

```java
errors.reject(
        "coupon.minimumSeats",
        new Object[]{3},
        "GROUP coupon requires at least {0} seats"
);
```

This is a cross-field relationship error. Attaching it to `couponCode` using `rejectValue` can still make sense for UX, but in this lesson we intentionally use `reject` to demonstrate an **ObjectError**. When building the JSON response, you must read `getGlobalErrors()`; using only `getFieldErrors()` will miss this error.

### 3.3. Binding or Type Conversion Errors

An HTTP form submits:

```text
seats=abc
```

Before business validation runs, `WebDataBinder` tries to convert the String `"abc"` to an `Integer`. When that fails, the binder records a `FieldError` whose primary code is typically `typeMismatch`; afterward, the target bean may still have `seats=null`.

If the custom validator then sees null and calls:

```java
errors.rejectValue("seats", "required", "Seats are required");
```

then the same input ends up with **two conflicting contextual errors**: “wrong type” and “missing”. The solution is **not to create a second business error for a field that already has a binding failure**:

```java
if (!errors.hasFieldErrors("seats")) {
    Integer seats = form.getSeats();

    if (seats == null) {
        errors.rejectValue("seats", "required",
                "Seats are required");
    } else if (seats < 1 || seats > 5) {
        errors.rejectValue("seats", "range",
                new Object[]{1, 5},
                "Seats must be between {0} and {1}");
    }
}
```

This is part of the code that will go into the complete validator. This approach is especially useful when `WebDataBinder` has already processed raw input before calling the Spring Validator.

## 4. ValidationUtils and Checking Required Strings

Spring provides a helper:

```java
ValidationUtils.rejectIfEmptyOrWhitespace(
        errors,
        "participantName",
        "required",
        "Participant name is required"
);
```

The helper checks the property through `Errors`, detects null, empty string, or whitespace-only values (per the helper's semantics), and calls `rejectValue` when needed. It reduces boilerplate for required text fields.

However:

- It does **not** check email format, numeric ranges, or cross-field rules.
- It requires a field/property compatible with the target object and property access mechanism.
- For a value object without suitable property conventions, an appropriate access approach must be chosen.
- Do not apply this helper indiscriminately to all data types. For `Integer seats`, checking `null` after filtering out binding errors is clearer.
- A string `" A "` is not empty; trimming before saving is a separate decision and does not automatically become a validation requirement.

## 5. How Does Spring Validator Differ from Jakarta Bean Validation?

| Aspect | Spring Validator | Jakarta Bean Validation |
| --- | --- | --- |
| Core interface | `org.springframework.validation.Validator` | `jakarta.validation.Validator` |
| Rule definition | Java code in `validate(target, Errors)` | Annotation constraints, class-level constraints, custom `ConstraintValidator` |
| Type selection | `supports(Class<?>)` | Constraint metadata on the bean |
| Result | Errors recorded into `Errors`/`BindingResult` | `Set<ConstraintViolation<T>>` |
| Multi-field logic | `errors.reject(...)` | Class-level custom constraint or service rule |
| MVC integration | `@InitBinder` + `@Validated`, or global validator | LocalValidatorFactoryBean and `@Valid`/`@Validated` |
| Provider dependency | No Jakarta provider needed for custom Spring Validator | Requires a provider to execute Bean Validation |
| Access to binding failures | Directly via `Errors` | Raw Jakarta validator does not inherently know `typeMismatch` from Spring binder |
| Best suited for | Complex form rules, binding-state awareness, workflow-specific validation | Declarative data/constraints and reuse across multiple layers |

They can coexist. Spring MVC usually registers `LocalValidatorFactoryBean` when a Jakarta provider is on the classpath; you can add a custom Spring `Validator` alongside it. However, this lesson chooses **pure Spring Validator** to prove that `supports`/`validate`/`Errors` actually drive the validation rather than accidentally passing because of annotations on the DTO.

**Important note:** Spring's `@Validated` on a `@ModelAttribute` argument triggers validation inside the data binder. It differs in purpose from class-level `@Validated` on a service to enable **AOP method validation**. Do not put `@Validated` on the controller class when you only want to register a form validator, and avoid confusing it with the newer method validation path in Spring MVC 6.1+.

## 6. Runnable Project: Course Registration Form

The project has two endpoints accepting `application/x-www-form-urlencoded`:

- `POST /api/registrations/checked`: has an adjacent `BindingResult`, so the controller decides whether to return 400 or 200.
- `POST /api/registrations/strict`: has no `BindingResult`, so Spring MVC throws `MethodArgumentNotValidException` for form validation errors and `@RestControllerAdvice` builds the response.

Main classes:

- `RegistrationForm`: mutable input DTO with public getters/setters.
- `RegistrationFormValidator`: implements Spring `Validator`.
- `RegistrationController`: `@InitBinder`, `@Validated`, allows binding only declared fields.
- `FormErrorMapper`: normalizes field/global errors into JSON and translates them via `MessageSource`.
- `RegistrationExceptionAdvice`: handles the strict path.
- `RegistrationFormTest`: `MockMvc` and unit-style tests directly against Spring `Errors`/`DataBinder`.

The project intentionally **does not use a JPA entity as the request DTO**. A form object serving the UI should not expose sensitive setters/fields of a domain entity, such as `role`, `ownerId`, `balance`.

### 6.1. Directory Structure

```text
spring-validator-errors-demo/
  settings.gradle
  build.gradle
  src/
    main/
      java/com/example/formvalidation/
        FormValidationApplication.java
        RegistrationForm.java
        RegistrationFormValidator.java
        RegistrationView.java
        FieldIssue.java
        GlobalIssue.java
        ApiError.java
        FormErrorMapper.java
        RegistrationController.java
        RegistrationExceptionAdvice.java
      resources/
        application.properties
        messages.properties
        messages_vi.properties
    test/
      java/com/example/formvalidation/
        RegistrationFormTest.java
```

### 6.2. Gradle

File `settings.gradle`:

```groovy
rootProject.name = 'spring-validator-errors-demo'
```

File `build.gradle`:

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
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}

tasks.named('test') {
    useJUnitPlatform()
}
```

**Omitting `spring-boot-starter-validation` intentionally:** the sample project uses only the application-defined `org.springframework.validation.Validator`, without `jakarta.validation.Validator` or `@NotBlank`. Spring MVC and the Spring Validator interfaces are already included in the Web starter. In a project that uses Jakarta annotations concurrently, you can add `spring-boot-starter-validation`, but you must verify the behavior of all registered validators.

### 6.3. Main Application

File `src/main/java/com/example/formvalidation/FormValidationApplication.java`:

```java
package com.example.formvalidation;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class FormValidationApplication {

    public static void main(String[] args) {
        SpringApplication.run(FormValidationApplication.class, args);
    }
}
```

### 6.4. Input DTO JavaBean

File `src/main/java/com/example/formvalidation/RegistrationForm.java`:

```java
package com.example.formvalidation;

public class RegistrationForm {

    private String participantName;
    private String email;
    private Integer seats;
    private String course;
    private String couponCode;

    public RegistrationForm() {
    }

    public String getParticipantName() {
        return participantName;
    }

    public void setParticipantName(String participantName) {
        this.participantName = participantName;
    }

    public String getEmail() {
        return email;
    }

    public void setEmail(String email) {
        this.email = email;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }

    public String getCourse() {
        return course;
    }

    public void setCourse(String course) {
        this.course = course;
    }

    public String getCouponCode() {
        return couponCode;
    }

    public void setCouponCode(String couponCode) {
        this.couponCode = couponCode;
    }
}
```

Because this is a mutable JavaBean, Spring `WebDataBinder` can bind query/form fields via setters. This implementation also lets `ValidationUtils` access properties through `Errors`.

Every property is an **allowed input**. Do not add `isAdmin` or `accountOwnerId` to the DTO just because the real entity has those fields. The sample keeps `Integer` instead of `int` so it can distinguish `seats` not being submitted (null) from the user entering `0`.

### 6.5. RegistrationFormValidator: Core Rules

File `src/main/java/com/example/formvalidation/RegistrationFormValidator.java`:

```java
package com.example.formvalidation;

import java.util.Set;
import java.util.regex.Pattern;
import org.springframework.stereotype.Component;
import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

@Component
public class RegistrationFormValidator implements Validator {

    private static final Set<String> COURSES =
            Set.of("JAVA", "SPRING");

    // Minimal structural check; does not replace email verification.
    private static final Pattern EMAIL = Pattern.compile(
            "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"
    );

    @Override
    public boolean supports(Class<?> clazz) {
        return RegistrationForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        RegistrationForm form = (RegistrationForm) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors,
                "participantName",
                "required",
                "Participant name is required"
        );

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors,
                "email",
                "required",
                "Email is required"
        );

        if (!errors.hasFieldErrors("email")) {
            String email = form.getEmail();
            if (!EMAIL.matcher(email).matches()) {
                errors.rejectValue(
                        "email",
                        "format",
                        "Please enter a valid email address"
                );
            }
        }

        ValidationUtils.rejectIfEmptyOrWhitespace(
                errors,
                "course",
                "required",
                "Course is required"
        );

        if (!errors.hasFieldErrors("course")
                && !COURSES.contains(form.getCourse())) {
            errors.rejectValue(
                    "course",
                    "choice",
                    "Choose JAVA or SPRING"
            );
        }

        // If the binder already added typeMismatch for seats,
        // do not stack an additional required/range error.
        if (!errors.hasFieldErrors("seats")) {
            Integer seats = form.getSeats();

            if (seats == null) {
                errors.rejectValue(
                        "seats",
                        "required",
                        "Seats are required"
                );
            } else if (seats < 1 || seats > 5) {
                errors.rejectValue(
                        "seats",
                        "range",
                        new Object[]{1, 5},
                        "Seats must be between {0} and {1}"
                );
            }
        }

        if ("GROUP".equals(form.getCouponCode())
                && !errors.hasFieldErrors("seats")
                && form.getSeats() != null
                && form.getSeats() < 3) {

            errors.reject(
                    "coupon.minimumSeats",
                    new Object[]{3},
                    "GROUP coupon requires at least {0} seats"
            );
        }
    }
}
```

**Read the validation order carefully:**

1. `supports` declares that the validator supports `RegistrationForm` or its subclasses.
2. `ValidationUtils` produces required errors for name/email/course.
3. Only check email format if the email field does **not** already have a required error.
4. Only check the course list if the course field does not have a required error.
5. Before checking seats for null/range, check whether the binder recorded `typeMismatch` or another error for seats.
6. For the `GROUP` coupon, create a **global error** via `errors.reject` instead of a field error.
7. Do not call `errors.reject...` with client-supplied values in the default message; messages are controlled to avoid leaking arbitrary input.

This email regex is only for the exercise, **not a complete RFC-compliant email validator**. Real-world emails have Unicode/IDN, quotes, provider-specific rules, and require ownership verification by sending a link/OTP; never call a regex “100% safe”.

**A note on `String#trim`:** the code above does not automatically trim email, course, or coupon. `"JAVA"` is accepted while `" java "` is not; `"GROUP"` has special meaning while `"group"` does not. If the product wants case-insensitivity or whitespace trimming, define normalization at the boundary and test it rather than silently altering the input contract.

### 6.6. Success Response DTO

File `src/main/java/com/example/formvalidation/RegistrationView.java`:

```java
package com.example.formvalidation;

public record RegistrationView(
        String participantName,
        String email,
        Integer seats,
        String course,
        String couponCode
) {}
```

The controller returns only validated public form values. Do not return a mutable entity or server-owned fields; actual booking creation/database writes belong in a separate service.

### 6.7. Field, Global, and Aggregate Error DTOs

File `src/main/java/com/example/formvalidation/FieldIssue.java`:

```java
package com.example.formvalidation;

public record FieldIssue(
        String field,
        String code,
        String message
) {}
```

File `src/main/java/com/example/formvalidation/GlobalIssue.java`:

```java
package com.example.formvalidation;

public record GlobalIssue(
        String code,
        String message
) {}
```

File `src/main/java/com/example/formvalidation/ApiError.java`:

```java
package com.example.formvalidation;

import java.util.List;

public record ApiError(
        String code,
        String message,
        List<FieldIssue> fieldErrors,
        List<GlobalIssue> globalErrors
) {}
```

`fieldErrors` is an array for field-specific errors; `globalErrors` is for cross-field errors. Do not collapse everything into a `Map<String,String>` because one field can have multiple violations and error keys are not necessarily unique. JSON arrays preserve complete information, and ordering can be explicitly sorted by the application.

### 6.8. MessageSource and Error Code Resolution

Spring `DefaultMessageCodesResolver` can generate multiple specific codes based on the object name, field, and type from a single `rejectValue("participantName","required",...)`. Example of the typical code order:

```text
required.registrationForm.participantName
required.participantName
required.java.lang.String
required
```

`FieldError#getCode()` returns the original code `required`. `FieldError#getCodes()` may contain the variants used to look up resource bundles. Do not call only `messageSource.getMessage(fieldError.getCode(),...)` if you want field-specific messages to take priority: it skips the `MessageSourceResolvable` code list.

For the global error `coupon.minimumSeats`, Spring can try the form-name-qualified code and then the general code. Use:

```java
messageSource.getMessage(objectError, locale)
```

so Spring traverses the codes and appropriate default message. If it is a conversion error from the binder, **do not expose the raw rejected input** in the response: the mapper will replace it with the public message `registration.typeMismatch`.

File `src/main/resources/application.properties`:

```properties
spring.application.name=spring-validator-errors-demo
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
```

File `src/main/resources/messages.properties`:

```properties
registration.invalid=Registration form contains errors
registration.typeMismatch=Invalid field type

required.registrationForm.participantName=Participant name is required
required.registrationForm.email=Email is required
format.registrationForm.email=Enter a valid email address
required.registrationForm.course=Course is required
choice.registrationForm.course=Choose JAVA or SPRING
required.registrationForm.seats=Seats are required
range.registrationForm.seats=Seats must be between {0} and {1}
coupon.minimumSeats=GROUP coupon requires at least {0} seats
```

File `src/main/resources/messages_vi.properties`:

```properties
registration.invalid=Biểu mẫu đăng ký có lỗi
registration.typeMismatch=Giá trị của trường không đúng kiểu dữ liệu

required.registrationForm.participantName=Tên người tham dự là bắt buộc
required.registrationForm.email=Email là bắt buộc
format.registrationForm.email=Email không đúng định dạng
required.registrationForm.course=Bạn phải chọn khóa học
choice.registrationForm.course=Chỉ được chọn JAVA hoặc SPRING
required.registrationForm.seats=Số chỗ là bắt buộc
range.registrationForm.seats=Số chỗ phải nằm từ {0} đến {1}
coupon.minimumSeats=Mã GROUP yêu cầu ít nhất {0} chỗ
```

**Note:** Spring Boot normally auto-configures `MessageSource` when the base bundle is declared and present (`messages.properties`). Having only `messages_vi.properties` without the base file can prevent auto-configuration from working as intended.

### 6.9. FormErrorMapper: Turning BindingResult into Safe JSON

File `src/main/java/com/example/formvalidation/FormErrorMapper.java`:

```java
package com.example.formvalidation;

import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import org.springframework.context.MessageSource;
import org.springframework.context.NoSuchMessageException;
import org.springframework.context.i18n.LocaleContextHolder;
import org.springframework.stereotype.Component;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;

@Component
public class FormErrorMapper {

    private final MessageSource messages;

    public FormErrorMapper(MessageSource messages) {
        this.messages = messages;
    }

    public ApiError from(BindingResult result) {
        Locale locale = LocaleContextHolder.getLocale();

        List<FieldIssue> fields = result.getFieldErrors()
                .stream()
                .map(error -> new FieldIssue(
                        error.getField(),
                        error.getCode() == null
                                ? "invalid" : error.getCode(),
                        safeMessage(error, locale)
                ))
                .sorted(Comparator.comparing(FieldIssue::field)
                        .thenComparing(FieldIssue::code))
                .toList();

        List<GlobalIssue> globals = result.getGlobalErrors()
                .stream()
                .map(error -> new GlobalIssue(
                        error.getCode() == null
                                ? "invalid" : error.getCode(),
                        safeMessage(error, locale)
                ))
                .sorted(Comparator.comparing(GlobalIssue::code))
                .toList();

        String summary = messages.getMessage(
                "registration.invalid",
                null,
                "Registration form contains errors",
                locale
        );

        return new ApiError(
                "VALIDATION_ERROR", summary, fields, globals
        );
    }

    private String safeMessage(ObjectError error, Locale locale) {

        if (error instanceof FieldError fieldError
                && fieldError.isBindingFailure()) {

            return messages.getMessage(
                    "registration.typeMismatch",
                    null,
                    "Invalid field type",
                    locale
            );
        }

        try {
            return messages.getMessage(error, locale);
        } catch (NoSuchMessageException ignored) {
            // Do not emit raw rejectedValue/exception message.
            return "Invalid value";
        }
    }
}
```

Design rationale:

- `result.getFieldErrors()` isolates per-field errors.
- `result.getGlobalErrors()` ensures multi-field relationships are not dropped.
- `safeMessage` passes the full `ObjectError` as a `MessageSourceResolvable`, receiving the proper code variants.
- For `FieldError#isBindingFailure()`, always use a controlled generic message instead of the conversion error's default message, which could contain raw rejected input.
- `NoSuchMessageException` is caught in the mapper so a missing key in a bundle does not turn a 400 validation response into an unintended server error; the fallback contains no sensitive data.
- Lists are sorted by field/code or code, because the insertion order from the binder/provider is not a guaranteed presentation priority.
- `LocaleContextHolder.getLocale()` retrieves the locale attached to the current request; Spring MVC `LocaleResolver` and filters/interceptors can affect the effective locale. Never mutate JVM-wide `Locale.setDefault(...)` per request.

**Note:** the mapper alone does not solve every internationalization requirement. If you want a Vietnamese fallback message when a key is completely missing, provide a Vietnamese `defaultMessage` or a fallback key. In the demo, the English base bundle acts as the common fallback language; tests verify the Vietnamese keys.

### 6.10. Controller: Registering the Validator via @InitBinder

File `src/main/java/com/example/formvalidation/RegistrationController.java`:

```java
package com.example.formvalidation;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/registrations")
public class RegistrationController {

    private final RegistrationFormValidator validator;
    private final FormErrorMapper errorMapper;

    public RegistrationController(
            RegistrationFormValidator validator,
            FormErrorMapper errorMapper) {

        this.validator = validator;
        this.errorMapper = errorMapper;
    }

    @InitBinder("registrationForm")
    public void initRegistrationBinder(WebDataBinder binder) {

        // Mutable form: allow binding only the exact public fields.
        binder.setAllowedFields(
                "participantName",
                "email",
                "seats",
                "course",
                "couponCode"
        );

        binder.addValidators(validator);
    }

    @PostMapping(
            path = "/checked",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> checked(
            @Validated
            @ModelAttribute("registrationForm") RegistrationForm form,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            return ResponseEntity.badRequest().body(
                    errorMapper.from(bindingResult)
            );
        }

        return ResponseEntity.ok(toView(form));
    }

    @PostMapping(
            path = "/strict",
            consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public RegistrationView strict(
            @Validated
            @ModelAttribute("registrationForm") RegistrationForm form) {

        // If validation fails and there is no adjacent BindingResult,
        // Spring MVC typically throws MethodArgumentNotValidException.
        return toView(form);
    }

    private static RegistrationView toView(RegistrationForm form) {
        return new RegistrationView(
                form.getParticipantName(),
                form.getEmail(),
                form.getSeats(),
                form.getCourse(),
                form.getCouponCode()
        );
    }
}
```

**Why `binder.addValidators(validator)` instead of `setValidator(...)`?**

- `addValidators(...)` appends the custom Spring Validator to the binder's validator list; if a global validator is already registered, there is no need to replace it.
- `setValidator(...)` sets a single validator and can alter the active list, so use it only when replacement is intentional.
- `@InitBinder("registrationForm")` scopes the configuration to the model attribute named `registrationForm`, rather than applying it to every handler argument.
- `setAllowedFields(...)` helps protect **property binding** on a mutable JavaBean via an allowlist. It does not replace minimal-privilege DTO design, authorization, or constructor-binding controls.
- `@Validated` on the method argument triggers execution of the binder's validators. Registering via `@InitBinder` without a validation annotation can prevent the custom validator from running automatically for that argument.

For an HTML controller instead of REST, the controller can return a template view name and use `BindingResult` to render messages next to input fields, while the error-recording principles with `Errors` remain the same.

### 6.11. Advice for Endpoints Without BindingResult

File `src/main/java/com/example/formvalidation/RegistrationExceptionAdvice.java`:

```java
package com.example.formvalidation;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class RegistrationExceptionAdvice {

    private final FormErrorMapper mapper;

    public RegistrationExceptionAdvice(FormErrorMapper mapper) {
        this.mapper = mapper;
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> invalid(
            MethodArgumentNotValidException exception) {

        return ResponseEntity.badRequest().body(
                mapper.from(exception.getBindingResult())
        );
    }
}
```

The demo only has HTTP form endpoints; `MethodArgumentNotValidException` is the typical exception when `@Validated @ModelAttribute` has no adjacent `BindingResult`. In real-world projects, with direct method constraints from Spring MVC 6.1+, you may encounter `HandlerMethodValidationException`; with JSON parser errors, you may encounter `HttpMessageNotReadableException`. Do not write a catch-all exception handler that blindly assigns `VALIDATION_ERROR`.

## 7. Running with Gradle and curl

If the project already has the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows:

```powershell
.\gradlew.bat bootRun
```

If there is no wrapper yet, you can run `gradle bootRun` with an appropriate Gradle installation or generate the wrapper. Do not run `javac` directly against the whole project because it requires Spring Boot/MVC/JUnit dependencies on the classpath.

### 7.1. Valid Data

```bash
curl -i -X POST http://localhost:8080/api/registrations/checked \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'participantName=Lan' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'seats=2' \
  --data-urlencode 'course=JAVA'
```

Expected HTTP **200 OK** with body:

```json
{
  "participantName": "Lan",
  "email": "lan@example.org",
  "seats": 2,
  "course": "JAVA",
  "couponCode": null
}
```

Omitting `couponCode` means the group discount rule is not applied. There are no Bean Validation annotations on the DTO, yet the request is still validated because `@InitBinder` adds `RegistrationFormValidator` and `@Validated` is on the argument.

### 7.2. Blank Name and Invalid Email

```bash
curl -i -X POST http://localhost:8080/api/registrations/checked \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept-Language: vi' \
  --data-urlencode 'participantName=   ' \
  --data-urlencode 'email=not-an-email' \
  --data-urlencode 'seats=2' \
  --data-urlencode 'course=JAVA'
```

Expected HTTP **400**, payload has two field errors (sorted by field):

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Biểu mẫu đăng ký có lỗi",
  "fieldErrors": [
    {
      "field": "email",
      "code": "format",
      "message": "Email không đúng định dạng"
    },
    {
      "field": "participantName",
      "code": "required",
      "message": "Tên người tham dự là bắt buộc"
    }
  ],
  "globalErrors": []
}
```

The translations come from `messages_vi.properties`; `MessageSource#getMessage(ObjectError, Locale)` resolves the specific code. Error codes `format`/`required` remain locale-independent so the frontend can drive UI behavior reliably.

### 7.3. GROUP Coupon Without Enough Seats

```bash
curl -i -X POST http://localhost:8080/api/registrations/checked \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  -H 'Accept-Language: vi' \
  --data-urlencode 'participantName=Lan' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'seats=2' \
  --data-urlencode 'course=SPRING' \
  --data-urlencode 'couponCode=GROUP'
```

Expected HTTP 400 with `globalErrors`:

```json
{
  "code": "VALIDATION_ERROR",
  "message": "Biểu mẫu đăng ký có lỗi",
  "fieldErrors": [],
  "globalErrors": [
    {
      "code": "coupon.minimumSeats",
      "message": "Mã GROUP yêu cầu ít nhất 3 chỗ"
    }
  ]
}
```

This demonstrates `errors.reject(...)` producing an `ObjectError`. If the application ignores `BindingResult#getGlobalErrors()`, the coupon error will vanish from the API even though the validator detected it.

### 7.4. Invalid Seat Type

```bash
curl -i -X POST http://localhost:8080/api/registrations/checked \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'participantName=Lan' \
  --data-urlencode 'email=lan@example.org' \
  --data-urlencode 'seats=abc' \
  --data-urlencode 'course=SPRING'
```

Expected HTTP 400 with field error `seats` having code `typeMismatch` and safe message `Invalid field type`. Do not add `required` for seats simply because the binder failed to convert it.

In systems using Jakarta/Bean Validation alongside Spring Validator, multiple validators may participate; test exact error counts instead of assuming every Spring version/provider always produces a single error for every invalid input.

## 8. MockMvc and Standalone Spring Validator Test Suite

File `src/test/java/com/example/formvalidation/RegistrationFormTest.java`:

```java
package com.example.formvalidation;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class RegistrationFormTest {

    @Autowired
    MockMvc mvc;

    @Autowired
    RegistrationFormValidator validator;

    @Test
    void supportsExactlyTheIntendedFormType() {
        assertTrue(validator.supports(RegistrationForm.class));
        assertFalse(validator.supports(String.class));
    }

    @Test
    void validFormReturnsOk() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "JAVA"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.participantName").value("Lan"))
            .andExpect(jsonPath("$.seats").value(2))
            .andExpect(jsonPath("$.course").value("JAVA"));
    }

    @Test
    void missingRequiredFieldsAreCollected() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.fieldErrors.length()").value(4))
            .andExpect(jsonPath("$.globalErrors.length()").value(0));
    }

    @Test
    void blankNameProducesRequiredError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "   ")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("participantName"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("required"));
    }

    @Test
    void invalidEmailProducesFormatError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "wrong-email")
                .param("seats", "2")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("email"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("format"));
    }

    @Test
    void unknownCourseProducesChoiceError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "PYTHON"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("course"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("choice"));
    }

    @Test
    void zeroSeatsProducesRangeError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "0")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("seats"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("range"));
    }

    @Test
    void tooManySeatsProducesRangeError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "6")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("range"));
    }

    @Test
    void missingSeatsProducesRequiredError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("seats"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("required"));
    }

    @Test
    void badNumericInputPreservesBindingErrorOnly()
            throws Exception {

        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "abc")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors.length()").value(1))
            .andExpect(jsonPath("$.fieldErrors[0].field")
                    .value("seats"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("typeMismatch"))
            .andExpect(jsonPath("$.fieldErrors[0].message")
                    .value("Invalid field type"));
    }

    @Test
    void groupCouponCreatesGlobalError() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "SPRING")
                .param("couponCode", "GROUP"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors.length()").value(0))
            .andExpect(jsonPath("$.globalErrors.length()").value(1))
            .andExpect(jsonPath("$.globalErrors[0].code")
                    .value("coupon.minimumSeats"));
    }

    @Test
    void groupCouponSucceedsWithThreeSeats() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "3")
                .param("course", "SPRING")
                .param("couponCode", "GROUP"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.couponCode").value("GROUP"))
            .andExpect(jsonPath("$.seats").value(3));
    }

    @Test
    void strictRouteWithoutBindingResultReachesAdvice()
            throws Exception {

        mvc.perform(post("/api/registrations/strict")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", " ")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                    .value("required"));
    }

    @Test
    void fieldsAreSortedByName() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", " ")
                .param("email", "invalid")
                .param("seats", "0")
                .param("course", "BAD"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors.length()").value(4))
            .andExpect(jsonPath("$.fieldErrors[0].field").value("course"))
            .andExpect(jsonPath("$.fieldErrors[1].field").value("email"))
            .andExpect(jsonPath("$.fieldErrors[2].field")
                    .value("participantName"))
            .andExpect(jsonPath("$.fieldErrors[3].field").value("seats"));
    }

    @Test
    void vietnameseBundleLocalizesMessages() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .header("Accept-Language", "vi")
                .param("participantName", " ")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "JAVA"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message")
                    .value("Biểu mẫu đăng ký có lỗi"))
            .andExpect(jsonPath("$.fieldErrors[0].message")
                    .value("Tên người tham dự là bắt buộc"));
    }

    @Test
    void extraClientPropertyIsNotExposed() throws Exception {
        mvc.perform(post("/api/registrations/checked")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .param("participantName", "Lan")
                .param("email", "lan@example.org")
                .param("seats", "2")
                .param("course", "JAVA")
                .param("isAdmin", "true"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.participantName").value("Lan"))
            .andExpect(jsonPath("$.isAdmin").doesNotExist());
    }

    @Test
    void customValidatorWorksWithoutHttpRequest() {
        RegistrationForm form = new RegistrationForm();

        BindingResult errors = new BeanPropertyBindingResult(
                form, "registrationForm"
        );

        validator.validate(form, errors);

        assertTrue(errors.hasErrors());
        assertEquals(4, errors.getFieldErrorCount());
        assertEquals(0, errors.getGlobalErrorCount());
        assertNotNull(errors.getFieldError("seats"));
    }

    @Test
    void dataBinderSeparatesTypeMismatchFromBusinessRules() {
        RegistrationForm form = new RegistrationForm();

        DataBinder binder = new DataBinder(form, "registrationForm");
        binder.setValidator(validator);

        MutablePropertyValues values = new MutablePropertyValues(
                Map.of(
                        "participantName", "Lan",
                        "email", "lan@example.org",
                        "course", "JAVA",
                        "seats", "abc"
                )
        );

        binder.bind(values);
        binder.validate();

        BindingResult errors = binder.getBindingResult();

        assertEquals(1, errors.getFieldErrorCount());
        assertEquals(
                "typeMismatch",
                errors.getFieldError("seats").getCode()
        );
    }
}
```

The test suite has **18 `@Test` methods**. They cover:

- Selecting the right target class with `supports`.
- Valid request through `@InitBinder` and `@Validated`.
- Multiple missing fields, blank field, email format, course choice.
- Missing, out-of-range, or unparseable seats.
- Cross-field coupon producing a global error.
- Eligible coupon succeeding.
- Controller without `BindingResult` reaching the global exception advice.
- Stably sorted JSON `fieldErrors`.
- Vietnamese messages via `Accept-Language`/`MessageSource`.
- Client sending extra fields without creating privileged properties.
- Calling Spring Validator directly with `BeanPropertyBindingResult`.
- Calling Spring `DataBinder` directly, separating `typeMismatch` from business validations.

### 8.1. Test Command

From the project directory with Gradle wrapper:

```bash
./gradlew test
```

On Windows PowerShell:

```powershell
.\gradlew.bat test
```

If the project does not have a wrapper, use an installed Gradle to generate the wrapper or run `gradle test`. **Expect 18 tests to PASS** when dependencies, Java 17, and Spring Boot 3.3.6 match the project.

**Verification status:** these are the code and expected outputs of the hands-on exercise verified statically. No claim is made that Gradle/JUnit was actually executed during content authoring. Run the tests in your own environment to verify behavior for your specific version.

### 8.2. Why Test Both the Pure Validator and the MVC Path?

When testing only `RegistrationFormValidator#validate` directly, we know the business rules are right, but we do not yet know whether `@InitBinder` is invoked, `@Validated` triggers the validator, or `BindingResult` is in the right position.

When testing only with MockMvc, we know the HTTP response, but it may be unclear whether an error came from Spring binding, the custom validator, or the controller exception handler.

Combining both:

1. Unit-style direct validator tests prove `supports` and `validate` work.
2. Direct `DataBinder` tests prove binding failures and the custom validator coordinate properly.
3. `MockMvc` tests prove end-to-end form binding, validation, error mapping, and localization.

## 9. Nested Form: Using Errors.pushNestedPath

A real-world form may contain contact information:

```java
public class AddressForm {

    private String city;

    public String getCity() {
        return city;
    }

    public void setCity(String city) {
        this.city = city;
    }
}
```

If another form contains an `address` property and you have an `AddressValidator`, Spring lets you push a nested path:

```java
AddressForm address = form.getAddress();

if (address != null) {
    try {
        errors.pushNestedPath("address");

        ValidationUtils.invokeValidator(
                addressValidator,
                address,
                errors
        );
    } finally {
        errors.popNestedPath();
    }
}
```

**This is an illustrative snippet**, not part of the runnable `RegistrationForm` project above. It assumes the form has a `getAddress()` method and an `addressValidator` exists.

Key points:

- While the nested path is `address.`, a `rejectValue("city","required")` inside `AddressValidator` can become the field error `address.city`.
- `finally` guarantees the nested path is restored even if the sub-validator throws an exception.
- If `address` is null while business rules require an address, the parent validator should report an appropriate error and not call `invokeValidator` on null.
- When using Jakarta Bean Validation, `@Valid` is a different cascading mechanism, not strictly identical to `pushNestedPath`.
- Note that collections/maps have nested keys/indices and path/auto-grow complexity; never accept any unbounded client-supplied path as an allowed bindable field.

## 10. Using Validator.validateObject from Spring 6.1

Spring Framework 6.1 added a convenience method on `Validator` to validate an object when there is **no data-binding process**:

```java
Errors errors = validator.validateObject(form);

if (errors.hasErrors()) {
    // Handle errors according to the application boundary.
}
```

And you can turn an error state into an exception with `Errors#failOnError`:

```java
validator.validateObject(form)
        .failOnError(IllegalArgumentException::new);
```

Both snippets above are illustrative; they assume a `RegistrationFormValidator validator` and `RegistrationForm form` already exist. This is an option for manual validation in a service/helper, not a replacement for `WebDataBinder` when you need to collect **binding failures** from String → Integer. Given an already constructed Java object, `validateObject` cannot know on its own that the user had sent `seats=abc` in the HTTP request.

In a workflow that needs to return all form field errors, `BindingResult` from MVC and `FormErrorMapper` are already sufficient; you do not have to turn every validation failure into an exception.

## 11. Alternative Architectures to Consider

### 11.1. Controller Using Local @InitBinder

Fits when a form validator is dedicated to a single controller or a single model attribute. This is the demo's design.

Pros: clear scope, does not affect other controllers, works seamlessly with the form's `BindingResult`.

Risks: if multiple controllers share the form, you must reorganize registration or create a shared `@ControllerAdvice`.

### 11.2. Global Validator

You can configure a global validator via `WebMvcConfigurer#getValidator()`. However, this broadly affects argument validation; if a validator only supports one DTO, proper `supports`/scoping is required. In applications already using default Bean Validation, replacing the global validator can inadvertently disable Jakarta constraints; inspect configuration and test thoroughly.

For a single form, local registration with `binder.addValidators(...)` is simpler and has fewer side effects.

### 11.3. Service Validation Instead of HTTP Form Validation

Some rules such as “coupon is still active”, “enough seats remain”, or “unique username” require database state or concurrency handling. A Form Validator can check syntax and pure cross-field business logic, but checking `existsBy...` before inserting **does not guarantee uniqueness** when two requests race. The domain service and database constraints must still enforce the final invariants.

### 11.4. HTML Thymeleaf/JSP Instead of REST JSON

In an MVC page controller, when errors occur:

```java
if (bindingResult.hasErrors()) {
    return "registration-form";
}
```

This is an illustrative snippet for a view-returning controller, not part of the REST demo. The template can display field errors next to inputs and global errors at the top of the form using the binding result stored in the model. For example, with Thymeleaf, `th:errors` renders messages bound to a field when the proper binding result is present.

When using templates, do not immediately redirect to GET without designing flash attributes or proper state handling, because binding errors may no longer be in the model after a redirect.

## 12. Security When Handling Forms and Errors

### 12.1. Do Not Return rejectedValue Indiscriminately

`FieldError#getRejectedValue()` can contain emails, tokens, passwords, or private data. `ObjectError#getDefaultMessage()` generated by conversion exceptions can contain raw input or Java internals. Therefore the demo mapper returns only:

- `field` (public field name).
- `code` (machine-readable error identifier).
- `message` (resolved or controlled fallback).

Do not do:

```java
return Map.of(
        "field", fieldError.getField(),
        "rejected", fieldError.getRejectedValue()
);
```

unless you have a mechanism controlling what information may be returned. For password reset or signup, you must also guard against account/email enumeration.

### 12.2. Allowed Fields and Mass Assignment

A mutable input form should not be an entity with setters for every property. Spring DataBinder can populate any field sent by the client that matches a setter on the target. If the target has a `setIsAdmin` setter and you do not restrict fields, an attacker can try `isAdmin=true`.

The demo uses:

```java
binder.setAllowedFields(
        "participantName",
        "email",
        "seats",
        "course",
        "couponCode"
);
```

An allowlist is only **one layer**. The DTO should have a minimal input surface, the service must verify authorization, and the database must protect invariants.

### 12.3. Do Not Store Errors in a Singleton Field

`@Component RegistrationFormValidator` is typically a singleton and can be invoked concurrently by multiple HTTP requests. Validators should be **stateless**; `Errors` is created per request/binding operation and passed into `validate`.

Wrong:

```java
@Component
public class BadValidator implements Validator {

    private Errors lastErrors; // shared mutable state!

    // ...
}
```

Do not store `Errors`, the current target, or `Locale` in an instance field of a singleton validator. A regex `Pattern` and an immutable `Set` of allowed courses as in the demo can be safely kept as `static final`.

### 12.4. Avoid Running Heavy Queries on Every Validator Invocation

If validation depends on a DB or external service, a request can suffer higher latency or n+1 queries. Separate fast input checks from business operations, authorization, and persistence. Infrastructure failures should be classified differently from an invalid form.

## 13. Common Pitfalls Analysis

**1. Confusing Spring Validator with jakarta.validation.Validator.** The two interfaces do not share the same `supports`/`validate` signature.

**2. Writing only validate() without implementing supports() properly.** The binder will reject the validator for incompatible target types.

**3. Forgetting @InitBinder or binding to the wrong model attribute name.** The custom validator may never be registered on the binder for that form.

**4. Registering binder.addValidators without requesting validation.** `@Validated` or `@Valid`/an equivalent validation trigger must activate the validation step.

**5. Placing BindingResult non-adjacently to the form argument.** Spring will not pass the binding errors into the handler parameter properly.

**6. Handling only errors.hasFieldErrors and ignoring global errors.** `errors.reject(...)` does not appear in field-only lists.

**7. Using errors.rejectValue for form-wide rules without considering UI placement.** It can be reasonable, but when multiple fields are involved, define a clear UX contract.

**8. Checking seats==null after typeMismatch and adding a required error.** Produces overlapping messages that misrepresent the root cause.

**9. Assuming Jakarta @NotBlank runs even without a provider in the project.** The demo does not use Jakarta annotations; validation comes from Spring Validator.

**10. Trusting a simple email regex as proof of email ownership.** You still need verification emails and a dedicated policy.

**11. Testing only HTTP 400.** Does not prove which field failed, which code was emitted, or whether a global error was included.

**12. Relying on error traversal order to assert JSON array indices.** The adapter should sort errors if presentation order must be stable.

**13. Using only FieldError#getCode() to translate messages.** Ignores more specific codes qualified by object/field/type.

**14. Omitting messages.properties and creating only messages_vi.properties.** Boot auto-configuration may fail to register the `MessageSource` bundle as expected.

**15. Not handling NoSuchMessageException when a key message is missing.** The error handler itself could fail, losing the original 400 response.

**16. Using exception.getMessage() as a public error response.** Can leak rejected values, class names, SQL, or server details.

**17. Binding directly to a JPA entity.** Mass assignment and tight coupling make data binding hard to control.

**18. Using controller-wide @InitBinder without controlling scope.** A validator meant for one form can affect other model attributes.

**19. Invoking a validator for an incompatible subclass.** `supports` and downcasting must follow clear rules.

**20. Forgetting nested paths when validating child objects.** `errors.rejectValue("city",...)` may record the wrong field name if `address` is not pushed/popped properly.

**21. Catching RuntimeException from a validator and returning "Invalid form".** Hides bugs/dependency errors, produces wrong HTTP statuses, and hurts observability.

**22. Returning a Map<String,String> keyed by field and overwriting multiple errors on the same field.** Use a List or define explicit rule priority.

**23. Failing to test missing separately from blank, range, and conversion failure.** These cases have distinct semantics.

**24. Treating Errors as reusable across requests.** `Errors` is state tied to a single validation/binding invocation and must not be stored in a singleton.

**25. Relying solely on Validator to enforce business uniqueness/concurrency.** It does not replace unique constraints or transactional invariants in the database.

## 14. Production Readiness Checklist

1. Does the form DTO contain only fields the user is allowed to control?
2. Does the Spring Validator's `supports(Class<?>)` return true for the intended target?
3. Does `validate` record field errors with `rejectValue` and global errors with `reject` where appropriate?
4. Is `ValidationUtils.rejectIfEmptyOrWhitespace` used appropriately for required text?
5. Is `hasFieldErrors("seats")` checked before adding range/required errors after binding?
6. Are missing, blank, invalid format, invalid range, and `typeMismatch` each tested separately?
7. Is `binder.addValidators(...)` registered via `@InitBinder` with the exact attribute name?
8. Is `@Validated @ModelAttribute` declared to trigger validation?
9. Is `BindingResult` placed immediately after the corresponding argument?
10. Are both `getFieldErrors()` and `getGlobalErrors()` handled in the response?
11. Is `MessageSource#getMessage(ObjectError,Locale)` used to leverage the full error code list?
12. Are base/locale message bundles present, with a fallback that does not leak data?
13. Are error lists sorted if JSON ordering is part of the contract?
14. Are raw rejected input, stack traces, and exception internals hidden from responses?
15. Is `setAllowedFields` used for mutable property binding when needed?
16. Are there tests submitting extra fields to verify no mass assignment occurs?
17. Are there tests calling the validator without HTTP via `BeanPropertyBindingResult` or `DataBinder`?
18. Are there realistic `MockMvc` tests verifying Spring Context wiring?
19. Are global coupon rules tested around the boundary values of 2/3 seats?
20. Is the distinction between Spring Validator vs Jakarta Bean Validation and provider dependencies clear?
21. Are rules depending on the database/concurrency separated into the service/storage layer?
22. Are locale, special characters, and input sizes tested according to product requirements?
23. Is there a logging/metrics policy for errors that does not expose sensitive information?
24. Are tests re-run after upgrading Spring Framework/Spring Boot?
25. If using MVC HTML, is there a way to display both field/global errors and preserve valid user input when re-rendering the form?

**Conclusion:** To build a form validator with **Spring Validator**, write a class implementing `supports` and `validate`, accumulate violations into `Errors` using `rejectValue`/`reject`, then register it via `@InitBinder` and trigger it with `@Validated` on `@ModelAttribute`. `BindingResult` bridges **data binding** (which can fail due to type errors) and **business validation** (which can fail due to field or form-wide rules). When returning API errors, preserve both field and global errors, avoid duplicating `typeMismatch`, translate messages safely, and write tests at both the Validator and HTTP levels. This provides a clear, extensible form validation foundation tailored for Spring MVC.

## 15. Official References

- [Spring Framework — Validation Using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html): `Validator`, `Errors`, `ValidationUtils`, nested validators, and `validateObject`.
- [Spring Framework — Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html): `DefaultMessageCodesResolver`, `MessageSource`, and field-based error code variants.
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): controller validation, `BindingResult`, `MethodArgumentNotValidException`, and method validation.
- [Spring Framework — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): configuring `WebDataBinder` and registering local validators.
- [Spring Framework — MVC Validation Configuration](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-config/validation.html): global/local validators and `binder.addValidators`.
- [Spring Framework 6.1 — Errors Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/validation/Errors.html): `reject`, `rejectValue`, nested paths, and reading errors.
- [Spring Framework — Data Binding](https://docs.spring.io/spring-framework/reference/core/validation/data-binding.html): `DataBinder`, `BindingResult`, and type conversion errors.
- [Spring Framework — MVC Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): setting up allowlists and form-binding behavior.
