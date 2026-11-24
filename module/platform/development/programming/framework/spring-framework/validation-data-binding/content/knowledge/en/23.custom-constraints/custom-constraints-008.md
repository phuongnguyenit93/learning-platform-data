# Class-Level Constraints for Cross-Field Relationships in Spring Framework

## 1. The problem to solve

An individual field may be valid on its own while **the entire object is still invalid** when considering relationships between fields. For example:

- `checkIn` and `checkOut` are both valid dates, yet check-out cannot be on or before check-in.
- `startAmount` and `endAmount` are both valid numbers, yet the lower bound must be less than or equal to the upper bound.
- When `deliveryMethod = HOME`, the delivery address is required; when picking up in store, the address can be left blank.
- In a contact form, at least one of `email` or `phone` must be provided.

These rules are called **cross-field validation**. With Jakarta Bean Validation in Spring Framework, the clearest way to express them is a **custom constraint placed on the class/record**. The validator receives the entire object, checks the related properties, and emits one or more `ConstraintViolation`s when the condition is not met.

For example, two per-field constraints are insufficient to check date ordering:

```java
public record BookingRequest(
    @NotNull LocalDate checkIn,
    @NotNull LocalDate checkOut
) {}
```

`@NotNull` only ensures a value is present. It does not know `checkOut` must come after `checkIn`. To describe a rule across the whole object, we place a class-level annotation, such as `@ValidStayDates`, on `BookingRequest`.

**Scope distinction:** Jakarta Bean Validation validates input data against the object's contract. Rules requiring database queries, authorization checks, inventory checks, or transaction handling normally belong to the service/domain layer; do not cram everything into `ConstraintValidator`.

## 2. Processing flow in Spring MVC

With Spring Framework 6 / Spring Boot 3 using the `jakarta.validation.*` namespace:

1. The client sends JSON to a controller.
2. Spring MVC/Jackson converts JSON into a Java object. Malformed JSON or unconvertible data types are **binding/deserialization errors**, occurring before Bean Validation.
3. `@Valid` or appropriate `@Validated` configuration triggers Bean Validation after object creation.
4. The provider (typically Hibernate Validator when using `spring-boot-starter-validation`) checks field-level and class-level constraints.
5. The class-level constraint's `ConstraintValidator` receives the whole object to compare fields.
6. If violations occur, Spring MVC typically throws `MethodArgumentNotValidException` for a `@Valid @RequestBody` parameter without an accompanying `BindingResult`; errors can be mapped to HTTP 400 with `@RestControllerAdvice`.
7. If there are no errors, the controller proceeds to handle the request.

Brief diagram:

```text
JSON -> Jackson/binding -> BookingRequest
                             |
                        @Valid / @Validated
                             |
                @NotNull on each field
                @ValidStayDates on object
                             |
             valid -> controller / service
             violation -> BindingResult / HTTP 400
```

Note: execution order across constraints is not guaranteed. Class-level validators must handle objects with `null` fields or data already flagged by other constraints.

## 3. Complete example: check-in and check-out dates

Rule chosen for the example: **the check-out date must be at least one day after the check-in date**. Both fields are required. If one field is missing, `@NotNull` is responsible for reporting the missing-data error; the class-level constraint skips the comparison to avoid emitting an extra confusing error.

### 3.1. Project setup

Create a Spring Boot 3.x project with Java 17 or newer. In `build.gradle` (Groovy DSL), the following dependencies are needed; the plugin versions below are concrete examples compatible with Spring Boot 3.3:

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
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

`spring-boot-starter-validation` brings the Jakarta Validation API and provider into the application. Having only the `@Constraint` annotation without a provider is not enough to run validation in a standalone application.

Source structure of the example:

```text
src/main/java/com/example/demo/
  DemoApplication.java
  api/
    BookingRequest.java
    BookingController.java
    ValidationExceptionHandler.java
  validation/
    ValidStayDates.java
    StayDatesValidator.java
src/test/java/com/example/demo/validation/
  StayDatesValidatorTest.java
```

### 3.2. Declaring the class-level annotation

File `src/main/java/com/example/demo/validation/ValidStayDates.java`:

```java
package com.example.demo.validation;

import jakarta.validation.Constraint;
import jakarta.validation.Payload;
import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

@Documented
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = StayDatesValidator.class)
public @interface ValidStayDates {
    String message() default "Check-out date must be after check-in date";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
```

Component explanation:

- `@Target(ElementType.TYPE)` allows attaching the annotation to a class or record instead of a single field.
- `@Retention(RUNTIME)` retains the annotation at runtime so Bean Validation can find it.
- `@Constraint(validatedBy = StayDatesValidator.class)` registers the class implementing the validation logic.
- `message()` is the default message, overridable at the annotation usage site; a message bundle key such as `{booking.dates.invalid}` can also be used.
- `groups()` and `payload()` are mandatory parts of the Jakarta Bean Validation custom constraint declaration contract. `groups` enables selecting validation groups, and `payload` carries optional metadata.

### 3.3. Defining the DTO carrying both fields

File `src/main/java/com/example/demo/api/BookingRequest.java`:

```java
package com.example.demo.api;

import com.example.demo.validation.ValidStayDates;
import jakarta.validation.constraints.NotNull;
import java.time.LocalDate;

@ValidStayDates
public record BookingRequest(
    @NotNull(message = "Check-in date is required")
    LocalDate checkIn,

    @NotNull(message = "Check-out date is required")
    LocalDate checkOut
) {}
```

`@ValidStayDates` is attached to the record so the validator can inspect both components simultaneously. `@NotNull` on each component still checks requiredness independently. These are two complementary constraint levels, not substitutes for each other.

### 3.4. Writing `ConstraintValidator`

File `src/main/java/com/example/demo/validation/StayDatesValidator.java`:

```java
package com.example.demo.validation;

import com.example.demo.api.BookingRequest;
import jakarta.validation.ConstraintValidator;
import jakarta.validation.ConstraintValidatorContext;
import java.time.LocalDate;

public final class StayDatesValidator
        implements ConstraintValidator<ValidStayDates, BookingRequest> {

    @Override
    public boolean isValid(
            BookingRequest request,
            ConstraintValidatorContext context) {

        if (request == null) {
            return true;
        }

        LocalDate checkIn = request.checkIn();
        LocalDate checkOut = request.checkOut();

        // @NotNull handles missing either field.
        if (checkIn == null || checkOut == null) {
            return true;
        }

        if (checkOut.isAfter(checkIn)) {
            return true;
        }

        // Route class-level constraint error to the "checkOut" field.
        context.disableDefaultConstraintViolation();
        context
            .buildConstraintViolationWithTemplate(
                context.getDefaultConstraintMessageTemplate())
            .addPropertyNode("checkOut")
            .addConstraintViolation();

        return false;
    }
}
```

The two generic parameters of `ConstraintValidator<A, T>` are crucial: `A` is the `ValidStayDates` annotation; `T` is the validated object type, here `BookingRequest`. Applying `@ValidStayDates` to another type not supported by this validator may cause the provider to report that no compatible validator was found.

`isValid` returns `true` if valid, `false` if violated. Per the Bean Validation contract, `null` is usually checked by a separate requiredness constraint; that avoids duplicate errors. If business rules genuinely require a class-level error when the whole object is `null`, design a dedicated constraint and trigger point for that case.

The block:

```java
context.disableDefaultConstraintViolation();
context.buildConstraintViolationWithTemplate(
        context.getDefaultConstraintMessageTemplate())
    .addPropertyNode("checkOut")
    .addConstraintViolation();
```

sets the error path to `checkOut` instead of an object-level error. This helps form UIs because the message can be shown next to the check-out date input. The name in `addPropertyNode(...)` must match the DTO's actual property name. If a cross-field relationship has no single sensible field to fix, you can keep the **default class-level violation** by omitting the custom property node block; the error then belongs to `ObjectError` or the root path.

**Do not store per-request data in mutable fields of the validator.** Providers may reuse validator instances; use only local variables inside `isValid` or immutable configuration state initialized in `initialize(...)`.

### 3.5. Triggering in the controller

File `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

File `src/main/java/com/example/demo/api/BookingController.java`:

```java
package com.example.demo.api;

import jakarta.validation.Valid;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/bookings")
public class BookingController {

    @PostMapping
    public ResponseEntity<Map<String, String>> create(
            @Valid @RequestBody BookingRequest request) {

        // Validation illustration only; does not persist to a database.
        return ResponseEntity.status(HttpStatus.CREATED)
            .body(Map.of("status", "accepted"));
    }
}
```

`@Valid` on the `@RequestBody` parameter is the critical trigger point. Merely declaring `@ValidStayDates` on the DTO without triggering validation at the input boundary will not make Spring validate automatically in every context.

For `@ModelAttribute` forms, you can put `@Valid` on the argument and accept `BindingResult` immediately afterward to handle errors in the controller. For flows using validation groups, `@Validated(SomeGroup.class)` lets you specify the group. Spring MVC parameter/method validation or service method validation has separate mechanisms and exception types; do not assume every validation error is a `MethodArgumentNotValidException`.

### 3.6. Translating errors into an API response

File `src/main/java/com/example/demo/api/ValidationExceptionHandler.java`:

```java
package com.example.demo.api;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<Map<String, Object>> handle(
            MethodArgumentNotValidException exception) {

        List<Map<String, String>> errors = new ArrayList<>();

        for (FieldError error
                : exception.getBindingResult().getFieldErrors()) {
            errors.add(Map.of(
                "field", error.getField(),
                "message", error.getDefaultMessage()
            ));
        }

        for (ObjectError error
                : exception.getBindingResult().getGlobalErrors()) {
            errors.add(Map.of(
                "field", error.getObjectName(),
                "message", error.getDefaultMessage()
            ));
        }

        Map<String, Object> body = new LinkedHashMap<>();
        body.put("errors", errors);
        return ResponseEntity.badRequest().body(body);
    }
}
```

`getFieldErrors()` includes the violation attached to `checkOut` via `addPropertyNode`. `getGlobalErrors()` receives object-level errors if you keep the default violation. Depending on API requirements, you can normalize into an error list with `field`, `code`, and `message` without relying on the error order returned by the provider. This handler specifically illustrates `MethodArgumentNotValidException`; unparseable JSON errors, method validation errors, and business errors may require separate handlers.

### 3.7. Running and observing

From the project directory with the Gradle wrapper:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. Send a valid request:

```bash
curl -i -X POST http://localhost:8080/bookings \
  -H "Content-Type: application/json" \
  -d '{"checkIn":"2026-11-10","checkOut":"2026-11-12"}'
```

Expected result: HTTP `201 Created` and JSON `{"status":"accepted"}`.

Test an invalid date order:

```bash
curl -i -X POST http://localhost:8080/bookings \
  -H "Content-Type: application/json" \
  -d '{"checkIn":"2026-11-12","checkOut":"2026-11-10"}'
```

Expected result: HTTP `400 Bad Request` with equivalent content (JSON key order does not matter):

```json
{
  "errors": [
    {
      "field": "checkOut",
      "message": "Check-out date must be after check-in date"
    }
  ]
}
```

If `checkIn` is omitted, the error is attached to `checkIn` due to `@NotNull`; the class-level validator returns `true` when one date is absent. If a date is sent in a format that cannot be parsed into `LocalDate`, the error occurs during JSON conversion before the comparison rule runs.

## 4. Automated testing

You can test the validator directly with Jakarta Validation without starting the server or making HTTP calls. File `src/test/java/com/example/demo/validation/StayDatesValidatorTest.java`:

```java
package com.example.demo.validation;

import com.example.demo.api.BookingRequest;
import jakarta.validation.Validation;
import jakarta.validation.Validator;
import jakarta.validation.ValidatorFactory;
import java.time.LocalDate;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class StayDatesValidatorTest {

    @Test
    void acceptsValidDateOrder() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            var request = new BookingRequest(
                LocalDate.of(2026, 11, 10),
                LocalDate.of(2026, 11, 12)
            );

            assertTrue(validator.validate(request).isEmpty());
        }
    }

    @Test
    void rejectsWrongDateOrderOnCheckOutField() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            var request = new BookingRequest(
                LocalDate.of(2026, 11, 12),
                LocalDate.of(2026, 11, 10)
            );

            var violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertEquals(
                "checkOut",
                violations.iterator().next().getPropertyPath().toString()
            );
        }
    }

    @Test
    void delegatesMissingDateToNotNull() {
        try (ValidatorFactory factory =
                Validation.buildDefaultValidatorFactory()) {
            Validator validator = factory.getValidator();
            var request = new BookingRequest(
                null,
                LocalDate.of(2026, 11, 12)
            );

            var violations = validator.validate(request);
            assertEquals(1, violations.size());
            assertEquals(
                "checkIn",
                violations.iterator().next().getPropertyPath().toString()
            );
        }
    }
}
```

Run:

```bash
./gradlew test
```

These tests demonstrate the three essential states: valid data, invalid relationship between two fields, and a missing field. In a real system, add cases for equal dates, both fields missing, malformed JSON input, HTTP 400 mapping, validation groups (if used), and multiple simultaneous violations.

## 5. Applying to other cross-field rules

The same annotation + validator pattern can express other dependent conditions:

| Scenario | Whole-object condition | Suggested error location |
| --- | --- | --- |
| Numeric range | `min <= max` | `max` |
| Delivery | If `method = HOME`, `address` is non-empty | `address` |
| Contact registration | At least one of `email`, `phone` present | Object level or both fields |
| Event schedule | `endAt` after `startAt` | `endAt` |
| Purchase order | `discountCode` valid only with matching `promotionType` | `discountCode` |

Example with delivery address: validating the `address` field independently with `@NotBlank` would reject in-store pickup orders too. A class-level constraint accurately expresses *required only when* `deliveryMethod == HOME`. If the error can be fixed on a specific field, set `addPropertyNode("address")`. If multiple errors must be returned from a single check, after `disableDefaultConstraintViolation()` build each property-node violation and finish each branch with `addConstraintViolation()`; do not simply return `false` while forgetting to add violations.

To support the same annotation across multiple object types, design corresponding `ConstraintValidator`s or a suitable abstraction. Do not cast to incompatible DTOs, pass arbitrary field names and rely on reflection everywhere, or cram unrelated rules into one validator merely to reuse an annotation.

## 6. Common misconceptions

**Class-level constraints do not automatically become single-field errors.** By default violations carry the object path; to render next to an input, use `ConstraintValidatorContext` and `addPropertyNode` as shown. In Spring MVC, object-level errors usually appear in `getGlobalErrors()`, whereas errors with a property node appear in `getFieldErrors()`.

**`@Valid` and `@Validated` only take effect where invoked by the framework/validator.** They do not cause every `new BookingRequest(...)` call to throw an exception automatically. When creating objects in services, batch jobs, or tests, you must have an explicit validation point or pass through the proper integration mechanism.

**Do not ignore null and data-type errors.** Relational validators must precisely define partial-missing-data behavior; annotations like `@NotNull`, `@NotBlank`, and `@Email` validate individual fields. Bean Validation cannot fix malformed JSON or date-parsing errors.

**Do not assume constraint ordering.** Providers may check field-level and class-level annotations in varying orders. Rely on a group sequence if you genuinely need ordered evaluation, though usually null-safe logic without duplicate errors is all that is required.

**Do not confuse class-level constraints with cross-parameter constraints.** A class-level constraint compares properties of **a single object**. Cross-parameter validation addresses relationships between **parameters of a method/constructor** and has a different validator contract.

**Do not put side effects in `isValid`.** Avoid mutating the DTO, writing to a database, calling remote APIs, emitting events, or holding per-request state inside the validator. This keeps validation deterministic, reusable, and easy to test.

**Choose the exact business definition.** `checkOut.isAfter(checkIn)` forbids equal dates. If equal dates should be allowed, use `!checkOut.isBefore(checkIn)`. For time-zoned instants, pick the right temporal type and timezone rules; comparing `LocalDate` only compares calendar dates.

**Distinguish Java/Spring versions.** The example applies to Spring Framework 6 / Spring Boot 3 with `jakarta.validation.*`. Spring Boot 2 projects typically use `javax.validation.*` and matching dependencies; do not mix the two namespaces in one project.

**Do not replace domain invariants and data protection.** API-layer checks help fail fast; if a rule must always hold regardless of data entry point, enforce it in the domain/service layer and use appropriate database constraints where feasible.

## 7. Implementation checklist

1. Write the rule in one clear sentence, including boundary operators (`<` vs `<=`, whether empty is allowed).
2. Keep single-field checks on fields; declare a `@Target(TYPE)` annotation for cross-field conditions.
3. Implement `ConstraintValidator<Annotation, DtoType>`, handle null explicitly, and avoid per-request state.
4. Place the class-level annotation on the right DTO, record, or bean; trigger with `@Valid`/`@Validated` at boundaries.
5. Choose where errors are reported (object vs field) and API format; do not assume all validation exceptions share the same type.
6. Test valid cases, invalid relationships, boundary values, missing fields, and invalid input binding.
7. Ensure API validation logic aligns with business invariants; do not use validators to replace checks requiring queries or transactions.

**Key point:** When validity depends on relationships between fields, validate at the object level with a custom Bean Validation constraint; route violations to the appropriate field via `ConstraintValidatorContext`, while keeping single-field constraints and business logic in their rightful responsibilities.
