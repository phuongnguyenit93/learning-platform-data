# Writing a Constraint to Validate a Relationship Between Two Fields in Spring Framework

## 1. Practical Problem

Annotations like `@NotNull`, `@Min`, `@Email`, or `@Past` typically validate **a single value**. Yet many business rules only make sense when inspecting **two fields together**:

- `startDate` must be **before** `endDate`.
- `minPrice` must not exceed `maxPrice`.
- `password` and `confirmPassword` must match.
- `discountedPrice` must not exceed `originalPrice`.
- `validFrom` and `validUntil` must form a valid time range.

A constraint placed on `endDate` does not naturally have convenient, standardized access to `startDate` on the same object; a *class-level constraint* is designed precisely for this kind of relationship. Hibernate Validator, the popular Jakarta Bean Validation provider, also uses class-level constraints to express rules based on correlations across multiple properties. <https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/>

This lesson builds a constraint named `@ValidDateWindow` for the `BookingForm` DTO with the rule:

**When both dates are present and validly typed, `endDate` must be after `startDate` — equality is not allowed.**

Examples:

| startDate | endDate | Result |
| --- | --- | --- |
| 2026-11-20 | 2026-11-23 | Valid |
| 2026-11-20 | 2026-11-20 | Invalid: both dates are equal |
| 2026-11-23 | 2026-11-20 | Invalid: end precedes start |
| 2026-11-20 | null | Violates `@NotNull` on endDate; cross-field validator skips |
| null | 2026-11-23 | Violates `@NotNull` on startDate; cross-field validator skips |
| 2026-99-20 | 2026-11-23 | Cannot parse startDate from request; **binding** error distinct from relationship error |

We will:

1. Create the `@ValidDateWindow` annotation per the Jakarta Bean Validation 3.0 contract.
2. Write `ConstraintValidator<ValidDateWindow, BookingForm>` reading both fields.
3. Record the error at `endDate` using `ConstraintValidatorContext#addPropertyNode(...)` instead of only at object-level.
4. Separate null/blank/date-parsing responsibilities across field constraints, formatters, and the class-level constraint.
5. Run a Spring Boot 3.5.6/Java 17 application accepting both HTML forms and JSON.
6. Test directly with Jakarta `Validator` and over HTTP/MVC with JUnit 5 + MockMvc.
7. Address validation groups, nested DTOs, error messages, and common mistakes.

**Keep in mind:** a cross-field constraint is a **validity check**, not authorization. Two valid dates do not prove the sender is authorized to create or modify that booking.

## 2. Why Not Use Two @NotNulls or an Ad-Hoc @AssertTrue?

### 2.1. Single-Field Constraints Are Not Enough

With:

```java
@NotNull
private LocalDate startDate;

@NotNull
private LocalDate endDate;
```

both properties can be non-null while the date window is still invalid:

```text
startDate = 2026-11-23
endDate   = 2026-11-20
```

`@NotNull` only guarantees presence; it does not check correlation between two fields. `@Future` or `@FutureOrPresent` likewise compare a single instant against the clock, not `endDate` relative to `startDate`.

### 2.2. @AssertTrue Works, but Is Not Always Ideal

A quick approach:

```java
@AssertTrue
public boolean isDateWindowValid() {
    return startDate == null
        || endDate == null
        || endDate.isAfter(startDate);
}
```

This is an **illustrative fragment** inside a class with `startDate` and `endDate` fields. It works for a tiny rule, but has drawbacks:

- It does not clearly express a **reusable business annotation name**.
- The violation may attach to bean property `dateWindowValid` instead of the field the user needs to fix.
- When groups, message templates, metadata, or multiple forms sharing the rule are needed, logic scatters easily.
- The method can be detected by serializers as a boolean bean property in some setups if left unchecked, cluttering the model/API.

A custom **class-level constraint** allows clear naming, standalone testing, custom error paths, and extensible policies.

### 2.3. Cross-Field vs Cross-Parameter

- **Class-level constraint** receives an object like `BookingForm` and reads its fields.
- **Cross-parameter constraint** receives the array of arguments of a method/constructor, typically using `ConstraintValidator<Annotation,Object[]>` with `@SupportedValidationTarget(ValidationTarget.PARAMETERS)`.
- **Class-level validation** fits when request data has already been grouped into a DTO.
- **Cross-parameter validation** fits when a rule truly spans multiple method arguments without a DTO in the design, though it has different target/parameter-name rules.

In this lesson, we only create a class-level constraint for a DTO: simpler and easier to test.

## 3. Validation Architecture

Form request flow:

```text
HTTP form request
    |
    v
Spring MVC @ModelAttribute("booking")
    |
    +--> WebDataBinder + ConversionService
    |       "2026-11-20" --> LocalDate
    |       "wrong-date" --> typeMismatch
    |
    v
@Valid BookingForm
    |
    +--> @NotNull(startDate)
    +--> @NotNull(endDate)
    |
    +--> @ValidDateWindow on BookingForm
              |
              +--> isValid(form, context)
              +--> null? defer to @NotNull
              +--> endDate.isAfter(startDate)?
                      | yes -> valid
                      | no  -> violation at "endDate"
    |
    v
BindingResult
    |
    +--> errors? HTTP 400, perform no write operation
    +--> valid? execute business logic with authorization
```

For JSON, Jackson decodes the body into `BookingForm` and then Bean Validation runs on the object. Unparseable JSON errors can occur in the message converter before the validator is invoked; `@ValidDateWindow` **is not a JSON parser**.

In practice, Spring MVC also has method validation for controller methods with direct method constraints. The sample uses `@Valid` on the DTO with an adjacent `BindingResult` to handle object errors along a clear path.

## 4. Creating a Standards-Compliant Constraint Annotation

A custom constraint must declare its target locations, runtime retention, validator class, message, groups, and payload.

```java
package demo.booking;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = DateWindowValidator.class)
@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidDateWindow {

    String message() default "{demo.dateWindow.invalid}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

This is the **complete file `ValidDateWindow.java`**, used in the runnable project in section 9.

Meaning of each element:

- `@Documented`: annotation appears in generated Javadoc where applicable.
- `@Constraint(validatedBy=DateWindowValidator.class)`: specifies the validator implementation. Without it, the provider may not know how to validate the object type.
- `@Target(TYPE)`: constraint applies to a **class**, not a single `LocalDate` property.
- `ANNOTATION_TYPE`: allows use in composed constraints if extension is needed.
- `@Retention(RUNTIME)`: metadata must remain available at validation runtime.
- `message()`: message key/template; can be interpolated from `ValidationMessages.properties`.
- `groups()`: enables selecting validation groups when the application uses groups; default `{}` places it in the `Default` group when unspecified.
- `payload()`: Bean Validation extension metadata; never carry HTTP request data here.

**Why doesn't the annotation take `startField` and `endField`?** In this first version, the rule is tied to `BookingForm`, so using typed getters is type-safe, easy to refactor, and avoids reflection. If reuse across multiple classes with different field names is needed, section 14 discusses `@FieldsChronological(from="...",to="...")` and its associated risks.

## 5. Writing ConstraintValidator to Compare Two Dates Properly

```java
package demo.booking;

import java.time.LocalDate;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class DateWindowValidator
        implements ConstraintValidator<ValidDateWindow, BookingForm> {

    @Override
    public boolean isValid(
            BookingForm form,
            ConstraintValidatorContext context) {

        // Jakarta Bean Validation does not forbid null beans by default.
        // Treat null as valid per relational constraint convention.
        if (form == null) {
            return true;
        }

        LocalDate start = form.getStartDate();
        LocalDate end = form.getEndDate();

        // Null / missing fields are handled by @NotNull on each field.
        // Do not emit an extra comparison error that confuses users.
        if (start == null || end == null) {
            return true;
        }

        // Rule: end MUST be strictly after start.
        if (end.isAfter(start)) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        context
            .buildConstraintViolationWithTemplate(
                context.getDefaultConstraintMessageTemplate())
            .addPropertyNode("endDate")
            .addConstraintViolation();

        return false;
    }
}
```

This is the **complete file `DateWindowValidator.java`**. It does not need Spring's `@Component` annotation for Hibernate Validator to discover it: the Jakarta provider instantiates the implementation from `@Constraint(validatedBy=...)`. In Spring Boot, `LocalValidatorFactoryBean` is auto-configured whenever the Bean Validation starter is present.

### 5.1. Why Check Null First?

If `startDate=null`, calling `end.isAfter(start)` would throw a `NullPointerException`. More importantly, a user missing only one date should not by default receive both “date is required” **and** “end must be after start”.

Separation of responsibilities:

- `@NotNull`: both dates must be present.
- `@DateTimeFormat` or Jackson: input must parse into `LocalDate`.
- `@ValidDateWindow`: once both dates exist, verify their temporal relationship.

This is a **design policy**, not a rule that every class-level constraint must treat all nulls as valid. If business rules forbid missing a date range altogether, keep dedicated `@NotNull`s so users get an accurate message.

### 5.2. Why Use isAfter Instead of isBefore?

For the rule “end date is after start date”:

```java
end.isAfter(start)
```

is equivalent to:

```java
start.isBefore(end)
```

Equal values yield `false`. If business rules allow starting and ending on the same day, the rule becomes:

```java
!end.isBefore(start)
```

The two expressions express **two different contracts**. Before writing a constraint, clarify whether boundary equality is allowed, whether you are comparing calendar dates or instants (`LocalDate` vs `Instant`/`ZonedDateTime`), and how timezones are handled.

This lab uses the strict rule because it is easy to observe in tests.

### 5.3. Why disableDefaultConstraintViolation?

When a constraint is placed on a class, simply returning `false` creates a default violation on the **object node**. For instance, `getPropertyPath().toString()` is usually an empty string at the root.

Yet users need to know **which field to fix**. After calling:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        context.getDefaultConstraintMessageTemplate())
    .addPropertyNode("endDate")
    .addConstraintViolation();
```

the violation is attached to the `endDate` field path. Thus in Spring MVC, the error appears in `BindingResult#getFieldErrors("endDate")` and binds to the `endDate` form control.

**Do not forget to call `addConstraintViolation()` at the end of the builder chain**: creating a builder without finalizing the node will not register the violation as intended. And after disabling the default violation, returning `false` must register at least one custom violation; otherwise the provider may throw a validation error because no violation was produced.

### 5.4. Avoid Side Effects in isValid

`isValid(...)` should be a pure check:

- Do not mutate `form.setEndDate(...)`.
- Do not write to a database or send events/emails.
- Do not modify the principal/security context.
- Do not log the entire form or sensitive date values.
- Do not rely on shared mutable validator state across concurrent requests.

A `ConstraintValidator` can be cached/reused by the provider. In this example, the validator uses only local variables and is state-thread-safe.

## 6. Creating a DTO with Both Field-Level and Class-Level Constraints

```java
package demo.booking;

import java.time.LocalDate;

import jakarta.validation.constraints.NotNull;
import org.springframework.format.annotation.DateTimeFormat;

@ValidDateWindow
public class BookingForm {

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate endDate;

    public BookingForm() {
    }

    public BookingForm(LocalDate startDate, LocalDate endDate) {
        this.startDate = startDate;
        this.endDate = endDate;
    }

    public LocalDate getStartDate() {
        return startDate;
    }

    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }

    public LocalDate getEndDate() {
        return endDate;
    }

    public void setEndDate(LocalDate endDate) {
        this.endDate = endDate;
    }
}
```

This is the **complete `BookingForm.java` file** in the project.

Interaction among annotations:

- `@NotNull` runs on each `LocalDate` present on the object.
- `@DateTimeFormat(iso=ISO.DATE)` guides **Spring property formatting/binding**, e.g., from form parameter `"2026-11-20"`.
- `@ValidDateWindow` sits on the class and can read **both fields** after binding.
- `@Valid` sits on the controller argument to trigger Bean Validation on the DTO.
- Do not add `@Validated` on the class/controller just to “enable” this annotation; it can alter MVC's method validation path and exception semantics.

**JSON note:** `@DateTimeFormat` is not Jackson's primary mechanism for decoding `@RequestBody`. Spring Boot Web with Jackson Java Time support normally handles ISO `LocalDate` directly. If a JSON time format is non-standard, check Jackson/`@JsonFormat` or a custom deserializer and test it separately. The date-relationship constraint operates on **two already-constructed `LocalDate` values**, whether the data came from a form or JSON.

## 7. Observing Object-Level vs Field-Level Errors

### 7.1. Without Specifying a Property Node

Suppose the validator only did:

```java
@Override
public boolean isValid(BookingForm form,
                       ConstraintValidatorContext context) {
    if (form == null
            || form.getStartDate() == null
            || form.getEndDate() == null) {
        return true;
    }
    return form.getEndDate().isAfter(form.getStartDate());
}
```

This is a **comparison fragment**, not a replacement file. When the two dates violate the relationship, the provider creates a default class-level violation. The property path at root is empty; when Spring converts it into errors, it can appear as an `ObjectError`/global error.

### 7.2. With addPropertyNode("endDate")

The main implementation produces:

```text
ConstraintViolation.getPropertyPath() = endDate
ConstraintViolation.getMessageTemplate() = {demo.dateWindow.invalid}
ConstraintViolation.getConstraintDescriptor().getAnnotation()
    = instance of @ValidDateWindow
```

When integrated into Spring MVC's `BindingResult`, the controller can observe:

```text
field = endDate
code  = ValidDateWindow
```

**These are the typical default error code and path**, which may depend on `MessageCodesResolver`/provider configuration. Tests should assert at least the annotation type, path, and rule; do not rely on the full Vietnamese message if you want less brittle tests.

### 7.3. Attaching Errors to Both Fields?

If the UI requires highlighting both `startDate` and `endDate` when the range is invalid, the validator can add two violations:

```java
context.disableDefaultConstraintViolation();
String template = context.getDefaultConstraintMessageTemplate();

context.buildConstraintViolationWithTemplate(template)
    .addPropertyNode("startDate")
    .addConstraintViolation();

context.buildConstraintViolationWithTemplate(template)
    .addPropertyNode("endDate")
    .addConstraintViolation();

return false;
```

This is an **optional fragment**, not the main code used in the lab. Adding two violations puts two entries into the `ConstraintViolation` set; error counts and HTTP responses change. Pick a single target field consistent with your UX; avoid generating duplicate messages when the user only needs to adjust one field.

### 7.4. Nested Object Paths

If a parent object contains:

```java
public class BookingRequest {
    @Valid
    private BookingForm window;
}
```

this is a fragment requiring getters/imports/constructor. Validation on the parent needs `@Valid` to descend into `window`, and the child's class-level error path becomes:

```text
window.endDate
```

If `window == null`, cascading skips it; add `@NotNull` if the child object is required. Never assume `@Valid` automatically means “must not be null”.

## 8. Testing Directly with Jakarta Validator

A test suite does not need Spring MVC to verify cross-field logic. Jakarta Validation defines:

```java
ValidatorFactory factory =
    Validation.buildDefaultValidatorFactory();
Validator validator = factory.getValidator();

Set<ConstraintViolation<BookingForm>> violations =
    validator.validate(form);
```

This is a fragment that will be expanded into complete JUnit tests in section 10. Crucially, `Validator#validate(object)` returns a **Set** of violations; on normal violations it **does not automatically throw `ConstraintViolationException`**. Exceptions typically occur at the method-validation layer or when code throws them explicitly.

### 8.1. Testing the Exact Three Violation Properties

A thorough test can assert:

```java
ConstraintViolation<BookingForm> error =
    violations.iterator().next();

assertEquals("endDate",
    error.getPropertyPath().toString());

assertEquals(ValidDateWindow.class,
    error.getConstraintDescriptor()
        .getAnnotation()
        .annotationType());

assertEquals("{demo.dateWindow.invalid}",
    error.getMessageTemplate());
```

This is a JUnit fragment requiring imports and setup. The three assertions prove:

- The violation sits at the path the user needs to fix.
- The violation actually came from the **custom annotation**, not `@NotNull`.
- The annotation uses the exact message template.

Asserting only `assertFalse(violations.isEmpty())` is too weak: a `@NotNull` on another field could make the test pass even if the cross-field constraint never ran.

### 8.2. Cases to Test

| Case | startDate | endDate | Expectation |
| --- | --- | --- | --- |
| Happy path | 2026-11-20 | 2026-11-23 | No violations |
| Equal dates | 2026-11-20 | 2026-11-20 | 1 `ValidDateWindow` violation at `endDate` |
| End before Start | 2026-11-23 | 2026-11-20 | 1 `ValidDateWindow` violation at `endDate` |
| Missing Start | null | 2026-11-23 | 1 `NotNull` at `startDate` |
| Missing End | 2026-11-20 | null | 1 `NotNull` at `endDate` |
| Both missing | null | null | Two `NotNull`s, **no** cross-field violation |
| Valid leap day `LocalDate` | 2028-02-28 | 2028-02-29 | Valid |
| Unparseable `LocalDate` from input | "2026-02-30" | 2026-03-01 | Binding/deserialization error; do not call `LocalDate` constructor from raw text |

Using fixed dates keeps tests **independent of the system clock**. If adding `@FutureOrPresent`, tests need a controlled `ClockProvider` to avoid date-dependent failures.

## 9. Runnable Java 17 + Spring Boot 3.5.6 Project

### 9.1. Directory Structure

```text
booking-window-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/demo/booking/
    │   │   ├── BookingApplication.java
    │   │   ├── ValidDateWindow.java
    │   │   ├── DateWindowValidator.java
    │   │   ├── BookingForm.java
    │   │   └── BookingController.java
    │   └── resources/
    │       ├── application.properties
    │       └── ValidationMessages.properties
    └── test/
        └── java/demo/booking/
            ├── DateWindowConstraintTest.java
            └── BookingControllerTest.java
```

This is a **standalone** example. No database is needed; the endpoint merely demonstrates validation and HTTP status codes. A real booking API must use services, verify ownership/room availability, transactions, data synchronization, and other rules before persisting.

### 9.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.6</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>booking-window-lab</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
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

The three dependencies cover HTTP/Spring MVC, Jakarta Bean Validation (Hibernate Validator provider), and JUnit 5/MockMvc. Spring Boot 3.5.x uses the `jakarta.validation.*` namespace, **not `javax.validation.*` from older generations**.

### 9.3. application.properties

```properties
server.address=127.0.0.1
server.port=8080
spring.application.name=booking-window-lab
```

The lab binds only to loopback; it opens no public port. Because no authentication/authorization is configured, do not treat this as a production API.

### 9.4. ValidationMessages.properties

```properties
demo.dateWindow.invalid=Ngày kết thúc phải sau ngày bắt đầu
```

The file lives at `src/main/resources/ValidationMessages.properties`. In Bean Validation, the message template `{demo.dateWindow.invalid}` is looked up in this bundle. When running in an environment with a different message interpolator configuration, localized text may differ; assert **template and constraint type** for more resilient logic tests.

### 9.5. BookingApplication.java

```java
package demo.booking;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookingApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookingApplication.class, args);
    }
}
```

Just create a standard Spring Boot app. When a validator provider is on the classpath, Spring Boot configures integration so `@Valid` works in MVC. There is no need to call `Validation.buildDefaultValidatorFactory()` manually inside controllers.

### 9.6. ValidDateWindow.java

```java
package demo.booking;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;

@Documented
@Constraint(validatedBy = DateWindowValidator.class)
@Target({ElementType.TYPE, ElementType.ANNOTATION_TYPE})
@Retention(RetentionPolicy.RUNTIME)
public @interface ValidDateWindow {

    String message() default "{demo.dateWindow.invalid}";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

### 9.7. DateWindowValidator.java

```java
package demo.booking;

import java.time.LocalDate;

import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;

public final class DateWindowValidator
        implements ConstraintValidator<ValidDateWindow, BookingForm> {

    @Override
    public boolean isValid(
            BookingForm form,
            ConstraintValidatorContext context) {

        if (form == null) {
            return true;
        }

        LocalDate start = form.getStartDate();
        LocalDate end = form.getEndDate();

        if (start == null || end == null) {
            return true;
        }

        if (end.isAfter(start)) {
            return true;
        }

        context.disableDefaultConstraintViolation();
        context
            .buildConstraintViolationWithTemplate(
                context.getDefaultConstraintMessageTemplate())
            .addPropertyNode("endDate")
            .addConstraintViolation();

        return false;
    }
}
```

### 9.8. BookingForm.java

```java
package demo.booking;

import java.time.LocalDate;

import jakarta.validation.constraints.NotNull;
import org.springframework.format.annotation.DateTimeFormat;

@ValidDateWindow
public class BookingForm {

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate endDate;

    public BookingForm() {
    }

    public BookingForm(LocalDate startDate, LocalDate endDate) {
        this.startDate = startDate;
        this.endDate = endDate;
    }

    public LocalDate getStartDate() {
        return startDate;
    }

    public void setStartDate(LocalDate startDate) {
        this.startDate = startDate;
    }

    public LocalDate getEndDate() {
        return endDate;
    }

    public void setEndDate(LocalDate endDate) {
        this.endDate = endDate;
    }
}
```

### 9.9. BookingController.java

```java
package demo.booking;

import java.util.stream.Collectors;

import jakarta.validation.Valid;

import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/bookings")
public class BookingController {

    @InitBinder("booking")
    void restrictFormBinding(WebDataBinder binder) {
        binder.setAllowedFields("startDate", "endDate");
    }

    @PostMapping(
        path = "/form",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<String> fromForm(
            @Valid @ModelAttribute("booking") BookingForm booking,
            BindingResult errors) {

        return respond(booking, errors);
    }

    @PostMapping(
        path = "/json",
        consumes = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<String> fromJson(
            @Valid @RequestBody BookingForm booking,
            BindingResult errors) {

        return respond(booking, errors);
    }

    private ResponseEntity<String> respond(
            BookingForm booking,
            BindingResult errors) {

        // @ModelAttribute: fields outside the allowlist may be
        // suppressed; do not treat hasErrors()==false as accepting everything.
        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                .body("INVALID|suppressed");
        }

        if (errors.hasErrors()) {
            // Demo outputs error codes, NEVER rejectedValue or
            // exception messages containing user input.
            String codes = errors.getFieldErrors().stream()
                .map(e -> e.getField() + ":" + e.getCode())
                .distinct()
                .sorted()
                .collect(Collectors.joining(","));

            return ResponseEntity.badRequest()
                .body("INVALID|" + codes);
        }

        // No database/service: merely illustrates the result.
        return ResponseEntity.ok(
            "OK|" + booking.getStartDate()
                + "|" + booking.getEndDate());
    }
}
```

**Why does `BindingResult` come immediately after `BookingForm`?** In Spring MVC, that position delivers binding/validation errors directly to the controller. Without `BindingResult` and without an alternate method-validation path, object-argument validation errors typically result in `MethodArgumentNotValidException`.

**Why is `@InitBinder("booking")` present?** For form binding, only `startDate` and `endDate` properties are permitted. This adds a layer of defense against extra form fields. However, for JSON `@RequestBody`, Jackson handles deserialization via an HTTP message converter; `setAllowedFields` **must not be relied on as the sole defense against JSON over-posting**. Keep input DTOs minimal and test JSON separately.

**Why output only field + code?** In production, return user-friendly messages or a safely designed `ProblemDetail`; never serialize `BindingResult` or `FieldError#getRejectedValue()` directly. The demo deliberately returns a simple text body so the `endDate:ValidDateWindow` error is easy to observe stably.

**Limitation:** This class-level constraint checks only the date relationship. It does not verify whether the user is authorized to create the booking, room availability, night limits, pricing, tenant, or business state validity. Those rules belong in the business layer and authorization checks.

## 10. Standalone Jakarta Validation Tests

### 10.1. File DateWindowConstraintTest.java

```java
package demo.booking;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.time.LocalDate;
import java.util.Set;
import java.util.stream.Collectors;

import jakarta.validation.ConstraintViolation;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import jakarta.validation.constraints.NotNull;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;

class DateWindowConstraintTest {

    private static ValidatorFactory factory;
    private static Validator validator;

    @BeforeAll
    static void setup() {
        factory = Validation.buildDefaultValidatorFactory();
        validator = factory.getValidator();
    }

    @AfterAll
    static void teardown() {
        factory.close();
    }

    private static LocalDate day(String iso) {
        return LocalDate.parse(iso);
    }

    private static Set<String> paths(BookingForm form) {
        return validator.validate(form).stream()
            .map(v -> v.getPropertyPath().toString())
            .collect(Collectors.toSet());
    }

    @Test
    void acceptsEndDateAfterStartDate() {
        BookingForm form = new BookingForm(
            day("2026-11-20"), day("2026-11-23"));

        assertTrue(validator.validate(form).isEmpty());
    }

    @Test
    void rejectsEqualDatesOnEndDateField() {
        BookingForm form = new BookingForm(
            day("2026-11-20"), day("2026-11-20"));

        Set<ConstraintViolation<BookingForm>> errors =
            validator.validate(form);

        assertEquals(1, errors.size());

        ConstraintViolation<BookingForm> error =
            errors.iterator().next();

        assertEquals("endDate",
            error.getPropertyPath().toString());

        assertEquals(ValidDateWindow.class,
            error.getConstraintDescriptor()
                .getAnnotation()
                .annotationType());

        assertEquals("{demo.dateWindow.invalid}",
            error.getMessageTemplate());
    }

    @Test
    void rejectsReverseDates() {
        BookingForm form = new BookingForm(
            day("2026-11-23"), day("2026-11-20"));

        assertEquals(Set.of("endDate"), paths(form));
    }

    @Test
    void missingStartIsOnlyNotNullViolation() {
        BookingForm form = new BookingForm(
            null, day("2026-11-23"));

        Set<ConstraintViolation<BookingForm>> errors =
            validator.validate(form);

        assertEquals(1, errors.size());
        ConstraintViolation<BookingForm> error =
            errors.iterator().next();

        assertEquals("startDate",
            error.getPropertyPath().toString());

        assertEquals(NotNull.class,
            error.getConstraintDescriptor()
                .getAnnotation()
                .annotationType());
    }

    @Test
    void missingEndIsOnlyNotNullViolation() {
        BookingForm form = new BookingForm(
            day("2026-11-20"), null);

        assertEquals(Set.of("endDate"), paths(form));
    }

    @Test
    void missingBothDatesProducesTwoFieldErrors() {
        BookingForm form = new BookingForm(null, null);

        assertEquals(
            Set.of("startDate", "endDate"),
            paths(form));
    }

    @Test
    void leapYearDateCanBeValid() {
        BookingForm form = new BookingForm(
            day("2028-02-28"), day("2028-02-29"));

        assertTrue(validator.validate(form).isEmpty());
    }

    @Test
    void validatePropertyDoesNotEvaluateClassLevelRule() {
        BookingForm form = new BookingForm(
            day("2026-11-23"), day("2026-11-20"));

        assertTrue(
            validator.validateProperty(
                form, "endDate").isEmpty());

        // Only full bean validation checks @ValidDateWindow.
        assertFalse(validator.validate(form).isEmpty());
    }
}
```

The test suite has **8 methods**. They do not open an HTTP server, call Spring MVC, or depend on the current clock. The focus is verifying the annotation, property path, null policy, and actual Jakarta Validator provider results.

**Note:** `validateProperty(form,"endDate")` checks only constraints placed on the `endDate` property itself; it does not evaluate class-level constraints. Therefore, to verify the two-field relationship, call `validator.validate(form)` on the full object. `validateValue(BookingForm.class,"endDate",date)` likewise lacks both properties to check this correlation.

### 10.2. Distinguishing Code and Message

For `@ValidDateWindow`, the property path is asserted as `endDate` and the message template is `{demo.dateWindow.invalid}`. When interpolated, `getMessage()` becomes:

```text
Ngày kết thúc phải sau ngày bắt đầu
```

Logic tests should assert the **message template**, annotation type, and field path rather than hardcoding a localized message that can easily change. If the application needs to test Vietnamese localization, write a dedicated test with explicitly configured locale/message interpolation.

## 11. HTTP Testing with MockMvc

### 11.1. File BookingControllerTest.java

```java
package demo.booking;

import static org.hamcrest.Matchers.containsString;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

@SpringBootTest
@AutoConfigureMockMvc
class BookingControllerTest {

    @Autowired
    MockMvc mvc;

    @Test
    void validFormReturnsOk() throws Exception {
        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "2026-11-20")
                .param("endDate", "2026-11-23"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "OK|2026-11-20|2026-11-23"));
    }

    @Test
    void reversedFormDatesReturnFieldViolation()
            throws Exception {

        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "2026-11-23")
                .param("endDate", "2026-11-20"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                "INVALID|endDate:ValidDateWindow"));
    }

    @Test
    void equalFormDatesAreRejected() throws Exception {
        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "2026-11-20")
                .param("endDate", "2026-11-20"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                "INVALID|endDate:ValidDateWindow"));
    }

    @Test
    void missingEndDateIsNotNullFailure()
            throws Exception {

        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "2026-11-20"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                "INVALID|endDate:NotNull"));
    }

    @Test
    void malformedStartDateIsBindingFailure()
            throws Exception {

        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "invalid-date")
                .param("endDate", "2026-11-23"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                containsString("startDate:typeMismatch")));
    }

    @Test
    void extraFormFieldIsExplicitlyRejected()
            throws Exception {

        mvc.perform(post("/bookings/form")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("startDate", "2026-11-20")
                .param("endDate", "2026-11-23")
                .param("price", "0"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                "INVALID|suppressed"));
    }

    @Test
    void validJsonUsesSameClassLevelConstraint()
            throws Exception {

        mvc.perform(post("/bookings/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"startDate\":\"2026-11-20\","
                    + "\"endDate\":\"2026-11-23\"}"))
            .andExpect(status().isOk())
            .andExpect(content().string(
                "OK|2026-11-20|2026-11-23"));
    }

    @Test
    void reversedJsonReportsEndDateViolation()
            throws Exception {

        mvc.perform(post("/bookings/json")
                .contentType(MediaType.APPLICATION_JSON)
                .content(
                    "{\"startDate\":\"2026-11-23\","
                    + "\"endDate\":\"2026-11-20\"}"))
            .andExpect(status().isBadRequest())
            .andExpect(content().string(
                "INVALID|endDate:ValidDateWindow"));
    }
}
```

The test suite covers **8 HTTP/MVC scenarios**: valid form, reversed dates, equal dates, missing `endDate`, malformed date, extra field, valid JSON, and reversed-date JSON. An integration test goes beyond a unit test by verifying that Spring Boot wired the converter/validator and triggered `@Valid` at the exact controller boundary.

If the controller is modified to add direct constraints on method parameters (e.g., adding `@Min` on a `@RequestParam`), Spring MVC 6.1+ may use whole-method validation and a different exception flow. Adjust tests/handlers for `HandlerMethodValidationException` in that case rather than assuming all errors flow through the same `BindingResult`.

### 11.2. What to Observe in the malformedStartDate Test

Not every invalid date request is caught by `ValidDateWindow`. With `"invalid-date"`, Spring MVC cannot convert the text into `LocalDate`; `BindingResult` can contain a `typeMismatch` error on `startDate`.

Because `startDate` remains null in the new form after the binding failure, our class-level validator **deliberately skips** comparison to avoid emitting an extra relationship error. `@NotNull` may also produce an error depending on the pipeline/provider; the test asserts `startDate:typeMismatch` specifically rather than demanding the entire error list contain only one item.

**This is a key practical point:** a user sees “invalid start date” in all cases, but developers must know whether it is a **parse error**, a **missing-value error**, or a **comparison error** to inspect the right layer.

## 12. Running the Project and Manual Testing

### 12.1. Requirements

- JDK 17 or newer compatible with Spring Boot 3.5.x.
- Maven 3.x.
- Maven repository access on first run to download dependencies.
- No H2/PostgreSQL or separate server required.

### 12.2. Running JUnit

In the directory containing `pom.xml`:

```bash
mvn -q test
```

Success is indicated by **exit code 0**. With `-q`, Maven may omit a fixed summary line; Surefire reports are located in `target/surefire-reports/`. There are **16 test methods** across the two classes in the lesson code: 8 for Jakarta Validator and 8 for MVC.

Note: the assertions and expected outputs in this README are derived from the documented Spring/Jakarta/Hibernate Validator APIs, **not a log of running Maven tests in this environment**. When applying, run actual tests against your project's dependency versions.

### 12.3. Starting the Application

```bash
mvn -q spring-boot:run
```

Local server:

```text
http://127.0.0.1:8080
```

### 12.4. Case 1 — Valid Form

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/bookings/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'startDate=2026-11-20' \
  --data-urlencode 'endDate=2026-11-23'
```

Expected status `200 OK` and the exact body produced by the controller:

```text
OK|2026-11-20|2026-11-23
```

### 12.5. Case 2 — End Date Before Start Date

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/bookings/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'startDate=2026-11-23' \
  --data-urlencode 'endDate=2026-11-20'
```

Expected `400 Bad Request` with body:

```text
INVALID|endDate:ValidDateWindow
```

This proves the custom validator compares the two dates and attaches the error to `endDate` via the property node instead of leaving it as a global error.

### 12.6. Case 3 — Missing endDate

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/bookings/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'startDate=2026-11-20'
```

Expected:

```text
INVALID|endDate:NotNull
```

This is a single-field error, not `ValidDateWindow`. This distinction answers “missing date” differently from “invalid relationship between two dates”.

### 12.7. Case 4 — JSON Also Catches Invalid Date Relationship

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/bookings/json' \
  -H 'Content-Type: application/json' \
  -d '{"startDate":"2026-11-20","endDate":"2026-11-20"}'
```

Expected:

```text
INVALID|endDate:ValidDateWindow
```

The JSON parser/Jackson reads both ISO dates, and Bean Validation runs on `BookingForm`. If JSON contains an unparseable date, an error can occur **before** the controller receives the DTO via `HttpMessageNotReadableException`; this example controller does not define a custom handler for malformed JSON.

### 12.8. Case 5 — Extra Field in Form

```bash
curl -i -X POST \
  'http://127.0.0.1:8080/bookings/form' \
  -H 'Content-Type: application/x-www-form-urlencoded' \
  --data-urlencode 'startDate=2026-11-20' \
  --data-urlencode 'endDate=2026-11-23' \
  --data-urlencode 'price=0'
```

Expected:

```text
INVALID|suppressed
```

The form binder allowlist accepts only `startDate`/`endDate`. The `price` field is suppressed and the handler explicitly rejects it. Never equate `BindingResult#hasErrors()` with concluding that every client-submitted input was accepted.

## 13. Designing Null Policy, Parse Policy, and Validation Groups

### 13.1. Null Policy Is Intentional, Not a Forced Default

There are two options:

- **Skip null in the cross-field validator** (main example): `@NotNull` manages missing fields; the comparison validator runs only when both values are present.
- **Fail the cross-field check even on null**: may suit an atomic business rule, but easily produces confusing duplicate errors or obscures the root cause.

In a form with two required fields, separating `@NotNull` and `@ValidDateWindow` usually makes UX, error codes, and tests easier to manage.

### 13.2. Empty Value vs Unparseable Value

When Spring receives:

```text
startDate=
```

conversion/formatting may treat it as null or a parse error depending on configuration. When receiving:

```text
startDate=2026-99-20
```

it is syntactically invalid ISO date text and can produce `typeMismatch`. Only when both values are valid `LocalDate`s in the wrong order does the custom constraint emit `ValidDateWindow`.

Never make a custom validator parse raw strings. Division of labor:

1. HTTP message converter / form formatter: decode and convert types.
2. Field constraints: per-property rules.
3. Class-level constraint: multi-property relationships.
4. Service/domain: authorization, state, transactions, and rules outside the DTO.

### 13.3. Groups: Run the Constraint Only When Its Group Is Selected

In the main example, `@ValidDateWindow` belongs to `Default`. If a workflow has two steps `Draft` and `Submit`, you can place the constraint in `Submit`:

```java
public interface SubmitChecks {}

@ValidDateWindow(groups = SubmitChecks.class)
public class BookingForm {
    // Fields...
}
```

This is an **illustrative fragment**; do not replace the main source files. When validating with a group:

```java
validator.validate(form, SubmitChecks.class);
```

constraints belonging to `Default` (like `@NotNull` with no group specified) **do not run automatically** alongside `SubmitChecks`. If both are needed:

```java
validator.validate(
    form, Default.class, SubmitChecks.class);
```

or define a group sequence per policy. With Spring MVC, `@Validated(SubmitChecks.class)` on a DTO argument selects the group; `@Valid` normally uses `Default`. Never use an `Admin` group as proof that the caller has admin privileges—groups are not authorization.

### 13.4. Group Sequence When Ordered Validation Is Needed

Conceptual example:

```java
@GroupSequence({
    Default.class,
    SubmitChecks.class
})
public interface CompleteChecks {}
```

In a project with `Default` and `SubmitChecks` declared/imported, this is a fragment rather than a full file. When validating with `CompleteChecks`, if `Default` has errors, the provider skips `SubmitChecks` in that sequence. This can be useful to avoid running a cross-field constraint before basic prerequisites pass, though in the current application our null-safe validator is already clear enough.

**Important:** When defining `@GroupSequence` directly on a bean class to *redefine the Default group sequence*, different rules apply—usually the bean class itself must be included. Never copy a sequence interface verbatim onto a class-level annotation without consulting the Jakarta spec.

## 14. Generic Constraint for Two Field Names: When Should You Build One?

The sample writes a type-safe validator for `BookingForm`. When many DTOs have `LocalDate` pairs with different names, you could design:

```java
@FieldsChronological(
    from = "availableFrom",
    to = "availableUntil")
public class AvailabilityForm {
    private LocalDate availableFrom;
    private LocalDate availableUntil;
}
```

This is a **hypothetical design interface**, not an annotation defined in the runnable code. If implementing a generic validator, you must address:

- Reading properties via `BeanWrapper`/getter metadata or controlled reflection.
- Initializing and caching field names from the annotation inside `initialize(...)`.
- Raising a clear configuration error if a property is missing or mistyped, never swallowing exceptions or silently passing.
- Never letting clients pass arbitrary field names to the annotation/validator.
- Checking null/empty; avoiding silent comparison discrepancies.
- Calling `addPropertyNode(to)` with a verified existing property name.
- Using `Comparable` or specific date types with type safety; avoid lexicographic string comparison of dates unless the contract strictly guarantees a canonical sortable representation.
- If names involve nested paths, traverse property nodes properly instead of passing a dotted string directly into one node; `addPropertyNode` takes a single property node name.
- Never relying on client input/reflection to access sensitive properties.

**When should you avoid generalizing?** When there is only one DTO and one rule, a typed validator like `DateWindowValidator` is clearer, less error-prone at runtime, and easier to refactor. Create a generic constraint only when enough use cases genuinely justify the complexity.

## 15. Another Example: password and confirmPassword

Two-field relationships are not limited to dates. For password changes, you might have:

```java
public class ChangePasswordForm {
    @NotBlank
    private String newPassword;

    @NotBlank
    private String confirmPassword;

    // getters/setters
}
```

And a class-level validator checking:

```java
boolean same = Objects.equals(
    form.getNewPassword(),
    form.getConfirmPassword());
```

These are **fragments**, not a standalone compilable class. If building `@PasswordsMatch`, attach the violation to `confirmPassword` via `addPropertyNode("confirmPassword")`, just like `endDate`.

However:

- Never log password values or rejected values.
- Never embed plaintext passwords in validation messages.
- Password strength/breach checks are separate rules and do not replace matching.
- Authorization, reauthentication, CSRF, and safe password hashing must be handled separately.
- Never use `String.equalsIgnoreCase(...)` to compare passwords. Case sensitivity matters.
- Never turn a password form into a JPA entity for direct binding.

The core of this lesson remains the `LocalDate` pair, as it clearly illustrates both relational rules and HTTP binding.

## 16. Common Pitfalls When Writing Two-Field Constraints

| Symptom | Cause | Fix |
| --- | --- | --- |
| Validator does not run | Forgot `@ValidDateWindow` on class, missing Bean Validation provider, or validation not triggered | Check annotation, `@Valid`, and classpath provider |
| `UnexpectedTypeException` | `ConstraintValidator` generic type mismatches target bean | Use `ConstraintValidator<ValidDateWindow, BookingForm>` for exact DTO |
| `ConstraintDefinitionException` | Annotation missing `message/groups/payload` or wrong retention/target | Follow Jakarta Validation constraint contract |
| Error only appears as global/object | Only returned `false` without adding property node | Call `disableDefaultConstraintViolation()` and `addPropertyNode("endDate")` |
| No violation after disabling default | Forgot `addConstraintViolation()` | Finalize builder chain and return `false` |
| Missing `startDate` causes NPE | Did not guard null before `isAfter` | Add null guard; let `@NotNull` report missing |
| Equal dates still accepted | Used inclusive comparison instead of strict | Choose `end.isAfter(start)` vs `!end.isBefore(start)` per business rules |
| Bad date format expected to trigger custom validator | Parse failure happens before `LocalDate` exists | Check `typeMismatch`/`HttpMessageNotReadableException` |
| Test runs only `validateProperty(endDate)` | Does not evaluate class-level constraints | Call `validator.validate(form)` |
| Test passes due to `@NotNull`, not custom rule | Only asserted `violations.size()>0` | Assert annotation type, property path, and template |
| `@Valid` on JSON input, but rule missing | Class-level annotation missing or group inactive | Check `@ValidDateWindow` and groups |
| `@Validated(Submit)` makes `@NotNull` vanish | `Default` and `Submit` are independent groups | Select both groups or use a sequence |
| Class-level bean validated twice | Direct method constraints present or validator invoked redundantly | Understand MVC 6.1+ method validation and flow |
| Wrong HTTP error handling | `BindingResult` not immediately after DTO, advice overrides, or different method validation path | Test MockMvc against controller signature |
| Rejected values leaked | Serialized full `BindingResult`/exception | Return approved error codes, never secret input |
| Validation hits database arbitrarily | Side effects in `isValid` or unclear transactions | Move DB-dependent rules to service/domain |
| DTO valid, yet user lacks permission | Confusing validation with authorization | Check principal, tenant, and resource in service |
| Validation skips nested `BookingForm` | Parent missing `@Valid` | Add cascade on the right property/collection element |
| Test results depend on current clock/date | Used `@Future` without fixing clock | Test fixed `LocalDate`s or use `ClockProvider` |
| Overusing `@ScriptAssert` | Relies on script engine, hard to maintain | Custom typed `ConstraintValidator` has clearer logic |

## 17. Code Review Checklist for Class-Level Constraints

1. Is the annotation targeted at `TYPE` with `@Constraint(validatedBy=...)`?
2. Does it have `@Retention(RUNTIME)` and the three `message/groups/payload` members with exact signatures?
3. Does the validator's generic type match the exact DTO it annotates?
4. Are strict/inclusive rules, time units, timezones, and boundaries clearly defined?
5. Are nulls handled explicitly to avoid NPEs?
6. Are accompanying field-level constraints declared for required fields?
7. On relationship errors, does `getPropertyPath()` point to the right UI field to fix?
8. Does the builder call both `disableDefaultConstraintViolation()` and `addConstraintViolation()`?
9. Is the message template stable without embedding sensitive data?
10. Does the validator avoid mutating state, writing to DB, or causing side effects?
11. Are happy path, equal, reversed, missing first, missing second, and both missing all tested?
12. Are tests run against the real provider asserting annotation type/path/message template?
13. Is there a `validateProperty()` test illustrating class-level scope?
14. Do MVC integration tests distinguish form conversion from JSON deserialization?
15. Is `BindingResult` placed immediately after the DTO when handling errors in the controller?
16. Are extra input fields or mass assignment outside the DTO blocked?
17. When using groups, are `Default`/Submit/sequences tested separately?
18. Do nested DTOs have `@Valid` on the proper association?
19. Are hardcoded current timestamps eliminated to prevent flaky tests?
20. After validation passes, does the business service still verify authorization and remaining invariants?

## 18. Extension Exercises

### Exercise A — Change Strict Rule to Inclusive Rule

Update the constraint so same-day bookings are valid:

```java
return !end.isBefore(start);
```

Update `rejectsEqualDatesOnEndDateField()` into a test accepting equal dates. Ensure the reversed-dates test still fails. After changing a business rule, it is important to **update tests to match the new contract**, not merely delete failing assertions.

### Exercise B — Min/Max Price Constraint

Create a DTO:

```java
public class SearchPriceForm {
    private BigDecimal minPrice;
    private BigDecimal maxPrice;
}
```

Rule: when both are present, `minPrice.compareTo(maxPrice) <= 0`. Consider adding `@DecimalMin("0")` on each field. `null` carries distinct meaning here: “no lower bound” or “no upper bound”, because this is an optional filter and does not necessarily need `@NotNull`.

This is an illustrative exercise, not part of the runnable source files.

### Exercise C — Custom Violations on Two Nodes

Try producing both `startDate` and `endDate` violations when the relationship fails. Inspect error counts, property paths, and API responses. Then evaluate UX: should the user receive one or two messages? Do not let two `FieldError`s mislead callers into thinking there are two independent business errors.

### Exercise D — Nested DTO

Add `BookingRequest` containing `@Valid BookingForm window` and verify the path `window.endDate` when validating the whole request. Then remove `@Valid` and compare. With `window=null`, verify cascading produces no `window.endDate` error; add `@NotNull` if `window` is mandatory.

### Exercise E — Validation Groups

Move `@ValidDateWindow` into a `SubmitChecks` group and use `@Validated(SubmitChecks.class)` on the submit endpoint. Add a test proving `Default` constraints do not run automatically, then design `@GroupSequence` or select multiple groups to avoid skipping required checks.

## 19. Summary

When a rule depends on **the relationship between two properties of the same DTO**, build a **class-level custom Bean Validation constraint**:

- Annotate `BookingForm` with `@ValidDateWindow`.
- Implement `ConstraintValidator<ValidDateWindow, BookingForm>` reading both `startDate` and `endDate`.
- `@NotNull` checks for missing data; the formatter/Jackson checks whether input can be parsed; the custom validator compares only **two validly typed dates**.
- When the relationship fails, `ConstraintValidatorContext` with `addPropertyNode("endDate")` directs the error to the specific field instead of only creating a global error.
- `validator.validate(form)` is the test for class-level constraints; `validateProperty(form,"endDate")` is no substitute.
- Spring MVC can trigger the same constraint for both `@ModelAttribute` and `@RequestBody` via `@Valid`, while binding errors and JSON deserialization errors must be handled separately.
- Tests should verify annotation type, property path, null semantics, and HTTP status—not just `hasErrors()`.

This pattern applies to date ranges, price bounds, and password confirmation. Even with proper validation, **authorization, data security, and business transactions** remain separate responsibilities.

## 20. References

- Hibernate Validator 8 Reference Guide — Class-level constraints, custom constraints, and custom property paths: https://docs.hibernate.org/validator/8.0/reference/en-US/html_single/
- Jakarta Bean Validation 3.0 specification — Constraint declaration, class-level constraints, custom violation paths, and groups: https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html
- Jakarta Bean Validation 3.0 API — `ConstraintValidator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintValidator.html
- Jakarta Bean Validation 3.0 API — `ConstraintValidatorContext`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/ConstraintValidatorContext.html
- Jakarta Bean Validation 3.0 API — `Validator`: https://jakarta.ee/specifications/bean-validation/3.0/apidocs/jakarta/validation/Validator.html
- Spring Framework 6.2 — Bean Validation integration: https://docs.spring.io/spring-framework/reference/6.2/core/validation/beanvalidation.html
- Spring Framework 6.2 — Validation in Spring MVC controller methods: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html
- Spring Framework 6.2 — `@ModelAttribute` binding/`BindingResult`: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html
- Spring Framework 6.2 — `@RequestBody`, JSON conversion and validation: https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/requestbody.html
- Spring Boot 3.5 — Validation integration: https://docs.spring.io/spring-boot/3.5/reference/io/validation.html
- JUnit 5 User Guide: https://junit.org/junit5/docs/current/user-guide/