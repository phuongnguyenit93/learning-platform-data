# Testing a Spring Validator with BeanPropertyBindingResult

`BeanPropertyBindingResult` is an essential tool for writing **unit tests for a Spring `Validator` without starting Spring Boot, a Servlet container, or an ApplicationContext**. Instead of sending an HTTP request, you instantiate a JavaBean holding the data to verify, create a `BeanPropertyBindingResult` for that bean, call `Validator.validate(target, errors)`, and inspect the error structure.

Three-step pattern:

~~~java
BookingForm form = new BookingForm();
BeanPropertyBindingResult errors =
    new BeanPropertyBindingResult(form, "booking");

new BookingValidator().validate(form, errors);

boolean invalid = errors.hasErrors();
~~~

This is an illustrative snippet; the complete classes and runnable tests are in section 7. **The constructor does not bind or validate automatically**. It is the `validate` call itself that runs the Spring `Validator` logic you wrote.

This lesson belongs to the **Testing** section of the **Spring Framework — validation-data-binding** module. It covers the `supports/validate` contract, creating fixtures, asserting `FieldError`/`ObjectError`, multiple errors, nested property paths, `ValidationUtils`, message codes and localization, the difference between `BeanPropertyBindingResult` and `DataBinder`, a Java 17+/Spring Framework 6.2/JUnit 5 example, debugging steps, and a checklist.

## 1. When do you need to test a plain Validator?

Spring provides the interface:

~~~java
package org.springframework.validation;

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

This is the **abbreviated signature** of the Spring API. A validator determines which object types it supports, inspects the object, and records errors into `Errors`. It is not an HTTP handler, does not connect to a database on its own, and does not return HTTP status codes directly.

Example rules for a booking:

- `customer` must contain non-whitespace content;
- `seats` must have a seat count and be at least 1;
- `startDate` and `endDate` must not be missing;
- `endDate` must be after `startDate` — this is an **object-wide** error, not a single-field error;
- `contact.email` must not be blank;
- if `contact` is null, report an error on field `contact`, rather than attempting to read email and causing a `NullPointerException`.

A quality unit test should verify **error codes, field paths, error counts, and error types**, instead of merely checking a boolean `hasErrors()==true`.

| Test type | Tool | What does it prove? |
|---|---|---|
| Custom `Validator` logic | `BeanPropertyBindingResult` + JUnit | Which rule rejects which field/object |
| JavaBean binding/type conversion | `DataBinder` + `MutablePropertyValues` | Whether input strings convert to Java properties |
| Jakarta `@NotNull`/`@Min` | `jakarta.validation.Validator` or Spring adapter | Constraint provider runs properly |
| Spring MVC form/JSON | MockMvc | Argument resolution, `@Valid`, `@InitBinder`, HTTP status/advice |
| Localized messages | `StaticMessageSource` or message bundles | Error codes are translated for the right locale |

**Do not confuse Spring `Validator` with Jakarta Bean Validation.** A bean annotated with `@NotNull` is not validated automatically just because you create a `BeanPropertyBindingResult`. Testing a plain Spring `Validator` requires calling `validate`, whereas Jakarta annotations require an enabled provider/adapter.

## 2. `BeanPropertyBindingResult`: class and constructors

Package:

~~~java
org.springframework.validation.BeanPropertyBindingResult
~~~

This class implements `Errors` and `BindingResult`, using **JavaBean property access** to read fields via getters/property descriptors, while also supporting nested paths.

Two constructors:

~~~java
new BeanPropertyBindingResult(target, objectName);

new BeanPropertyBindingResult(
    target, objectName,
    autoGrowNestedPaths,
    autoGrowCollectionLimit);
~~~

Where:

- `target` is the bean to which the errors relate.
- `objectName` is the logical name of the object, e.g., `booking`; this name affects **message codes**.
- `autoGrowNestedPaths` controls whether nested path growth is supported during property access.
- `autoGrowCollectionLimit` limits collection auto-growth, not JSON/request byte size.

For validator unit tests, the two-argument constructor is usually all you need.

### Things the constructor does NOT do

- Does not call `supports` or `validate`.
- Does not read an HTTP request or JSON.
- Does not run `@Valid`/`@Validated` or a Jakarta provider.
- Does not automatically convert `"abc"` into an `Integer`.
- Does not make a `@ControllerAdvice` produce an HTTP error.
- Does not reset errors automatically if an old `BindingResult` object is reused.

Therefore, the standard pattern is:

~~~java
BookingForm fixture = validBooking();
BeanPropertyBindingResult result =
    new BeanPropertyBindingResult(fixture, "booking");

validator.validate(fixture, result);

assertFalse(result.hasErrors());
~~~

The above is a snippet inside a test where those methods/variables are already declared. Each test should create a **new result** to avoid shared mutable state.

## 3. Testing `supports(Class<?>)` before testing logic

A validator for `BookingForm` can be implemented as:

~~~java
@Override
public boolean supports(Class<?> type) {
    return BookingForm.class.isAssignableFrom(type);
}
~~~

With this implementation:

~~~java
assertTrue(validator.supports(BookingForm.class));
assertFalse(validator.supports(String.class));
~~~

Why test this separately? Calling `validator.validate(form, result)` directly **does not automatically execute `supports(...)` beforehand**. Thus `validate` may run in a unit test even if `supports` is implemented incorrectly; when wired into `DataBinder`/the framework, the validator may be rejected because it does not support the target.

`ValidationUtils.invokeValidator(...)` is a helper that checks target/type compatibility, so it can also be used when you need to simulate how the framework invokes a validator, though the walkthrough calls `validate(...)` directly for simplicity and tests `supports` separately.

### Do not put business rules into `supports`

`supports` only confirms the Java type; do not use it to check `seats`, `startDate`, or the state of an instance. Value rules belong in `validate`; if you put logic based on an object instance inside `supports`, you are violating the contract.

## 4. FieldError: an error belonging to a property

When the seat count is invalid:

~~~java
errors.rejectValue(
    "seats",
    "seats.min",
    new Object[] {1},
    "Seats must be at least {0}");
~~~

Spring records a `FieldError` with field name `seats`, base code `seats.min`, arguments, and default message. How to assert:

~~~java
FieldError issue = result.getFieldError("seats");

assertNotNull(issue);
assertEquals("seats", issue.getField());
assertEquals("seats.min", issue.getCode());
assertEquals(0, issue.getRejectedValue());
assertFalse(issue.isBindingFailure());
~~~

**`isBindingFailure()==false`** because this error was created by custom validation `rejectValue`, not a conversion error from data binding. Conversely, if `DataBinder` tries to bind `"abc"` to `Integer seats` and fails, `FieldError.isBindingFailure()` is typically true with code `typeMismatch`.

`FieldError.getRejectedValue()` is useful for synthetic test fixtures, but do not serialize raw rejected values to public APIs or production logs if they may contain passwords, tokens, or private data.

### A field can have multiple errors

`result.getFieldError("seats")` retrieves only **the first error**. If a field violates multiple rules, use `getFieldErrors("seats")`. `getFieldErrorCount()` counts **error entries**, not the number of distinct field names.

For behavioral tests, assert field name + code + count; `assertTrue(result.hasErrors())` is too broad and can PASS even when the error was recorded on the wrong field.

## 5. ObjectError: an error belonging to the relationship between multiple fields

A rule such as "end date must be after start date" should not be blamed on an arbitrary field if you want the frontend to display the error in the general form section.

~~~java
if (form.getStartDate() != null
        && form.getEndDate() != null
        && !form.getEndDate().isAfter(form.getStartDate())) {
    errors.reject(
        "booking.range.invalid",
        "End date must be after start date");
}
~~~

`errors.reject(...)` creates an **`ObjectError`/global error**. `errors.rejectValue(...)` creates a **`FieldError`**. Testing:

~~~java
assertEquals(0, result.getFieldErrorCount());
assertEquals(1, result.getGlobalErrorCount());

ObjectError error = result.getGlobalError();
assertNotNull(error);
assertEquals("booking", error.getObjectName());
assertEquals("booking.range.invalid", error.getCode());
~~~

Do not check the range if either date is null. When a field has not been parsed or is missing, the relational rule lacks sufficient information; let field-level validation/binding record the corresponding error.

### Counting total errors accurately

`FieldError` extends `ObjectError`. Therefore:

- `result.getFieldErrors()`: only field-level errors.
- `result.getGlobalErrors()`: only object-wide errors.
- `result.getAllErrors()`: **both types**.

If there are three field errors and one global error:

~~~text
getFieldErrorCount() = 3
getGlobalErrorCount() = 1
getErrorCount() = 4
getAllErrors().size() = 4
~~~

Do not use `getAllErrors()` to build a separate list of global errors, as that will duplicate or mix in field errors.

## 6. ValidationUtils and nested paths

Spring provides:

~~~java
ValidationUtils.rejectIfEmptyOrWhitespace(
    errors,
    "customer",
    "required",
    "Customer is required");
~~~

This helper reads the property on the bean via `Errors`; it rejects `null`, `""`, or a string containing only whitespace. Unlike `ValidationUtils.rejectIfEmpty(...)`, the helper without `OrWhitespace` only rejects null/empty strings, not strings consisting of whitespace.

### Testing nested `contact.email`

Suppose `BookingForm` has a `contact` property of class `Contact`, which has `email`. Spring `Errors` supports scoping:

~~~java
errors.pushNestedPath("contact");
try {
    ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "email", "required",
        "Contact email is required");
}
finally {
    errors.popNestedPath();
}
~~~

When the nested path is `contact.`, the error will have `getField()=="contact.email"`. Tests should verify:

~~~java
assertTrue(result.hasFieldErrors("contact.email"));
assertEquals("", result.getNestedPath());
~~~

`finally` ensures the nested path is restored even if an exception occurs. Do not forget `popNestedPath()`, because subsequent errors could receive the wrong prefix.

If `contact==null`, handle it before invoking nested validation; the example below reports `FieldError("contact","required")` so the test does not throw a `NullPointerException`.

## 7. Runnable Java 17 + Spring 6.2 + JUnit 5 project

The example is a **plain Spring Validator unit test**, requiring no server. Create a Gradle project with the structure:

~~~text
validator-unit-tests/
  settings.gradle
  build.gradle
  src/main/java/com/example/validation/
    BookingForm.java
    BookingValidator.java
  src/test/java/com/example/validation/
    BookingValidatorTest.java
    BindingAndMessageTest.java
~~~

### `settings.gradle`

~~~groovy
rootProject.name = 'validator-unit-tests'
~~~

### `build.gradle`

~~~groovy
plugins {
    id 'java'
}

group = 'com.example'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
    testImplementation 'org.junit.jupiter:junit-jupiter:5.11.4'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher:1.11.4'
}

test {
    useJUnitPlatform()
}
~~~

`spring-context` pulls in the Spring dependencies needed for `Validator`, `BeanPropertyBindingResult`, and `StaticMessageSource`. JUnit Jupiter provides the API and engine to run tests. Versions are pinned so the demo is reproducible on Spring 6.2; this does not mean they are always the latest releases. If a project uses the Spring Boot BOM, let the BOM manage Spring versions instead of pinning one that may conflict.

### `BookingForm.java`

`src/main/java/com/example/validation/BookingForm.java`:

~~~java
package com.example.validation;

import java.time.LocalDate;

public class BookingForm {

    private String customer;
    private Integer seats;
    private LocalDate startDate;
    private LocalDate endDate;
    private Contact contact = new Contact();

    public BookingForm() {
    }

    public String getCustomer() {
        return customer;
    }

    public void setCustomer(String customer) {
        this.customer = customer;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
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

    public Contact getContact() {
        return contact;
    }

    public void setContact(Contact contact) {
        this.contact = contact;
    }

    public static class Contact {

        private String email;

        public Contact() {
        }

        public String getEmail() {
            return email;
        }

        public void setEmail(String email) {
            this.email = email;
        }
    }
}
~~~

This is a JavaBean with a no-arg constructor, getters/setters, and a nested object accessible via property paths. `BeanPropertyBindingResult` uses bean-property access, so building clear fixtures keeps tests stable.

### `BookingValidator.java`

`src/main/java/com/example/validation/BookingValidator.java`:

~~~java
package com.example.validation;

import org.springframework.validation.Errors;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public final class BookingValidator implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return BookingForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingForm form = (BookingForm) target;

        ValidationUtils.rejectIfEmptyOrWhitespace(
            errors, "customer", "required",
            "Customer is required");

        if (form.getSeats() == null) {
            errors.rejectValue(
                "seats", "required",
                "Number of seats is required");
        }
        else if (form.getSeats() < 1) {
            errors.rejectValue(
                "seats", "seats.min",
                new Object[] {1},
                "Number of seats must be at least {0}");
        }

        if (form.getStartDate() == null) {
            errors.rejectValue(
                "startDate", "required",
                "Start date is required");
        }

        if (form.getEndDate() == null) {
            errors.rejectValue(
                "endDate", "required",
                "End date is required");
        }

        if (form.getStartDate() != null
                && form.getEndDate() != null
                && !form.getEndDate().isAfter(
                    form.getStartDate())) {
            errors.reject(
                "booking.range.invalid",
                "End date must be after start date");
        }

        if (form.getContact() == null) {
            errors.rejectValue(
                "contact", "required",
                "Contact is required");
        }
        else {
            errors.pushNestedPath("contact");
            try {
                ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "email", "required",
                    "Contact email is required");
            }
            finally {
                errors.popNestedPath();
            }
        }
    }
}
~~~

Intentional decisions in the code:

- `seats=null` and `seats=0` record **different error codes**, without duplicate errors.
- Missing date fields are checked first. The relationship between the two dates is evaluated only when both have values.
- `errors.reject(...)` stores an object-wide error.
- `contact==null` is detected before accessing the nested path.
- `pushNestedPath/popNestedPath` are always balanced via `finally`.
- The validator does not call a database, an HTTP client, or mutate the object.

**There is no `@Valid` annotation in the project**, because we invoke the custom Spring Validator directly in unit tests. Even if you add Jakarta annotations to the bean, those annotations **will not run automatically** in this code.

## 8. JUnit: testing each behavior group

`src/test/java/com/example/validation/BookingValidatorTest.java`:

~~~java
package com.example.validation;

import java.time.LocalDate;

import org.junit.jupiter.api.Test;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.ValidationUtils;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BookingValidatorTest {

    private final BookingValidator validator =
        new BookingValidator();

    static BookingForm good() {
        BookingForm form = new BookingForm();
        form.setCustomer("Lan");
        form.setSeats(2);
        form.setStartDate(LocalDate.of(2026, 12, 20));
        form.setEndDate(LocalDate.of(2026, 12, 22));
        form.getContact().setEmail("lan@example.org");
        return form;
    }

    private BeanPropertyBindingResult check(BookingForm form) {
        BeanPropertyBindingResult errors =
            new BeanPropertyBindingResult(form, "booking");
        validator.validate(form, errors);
        return errors;
    }

    @Test
    void supportsCorrectType() {
        assertTrue(validator.supports(BookingForm.class));
        assertFalse(validator.supports(String.class));
    }

    @Test
    void validFormHasNoErrors() {
        BeanPropertyBindingResult errors = check(good());

        assertFalse(errors.hasErrors());
        assertEquals(0, errors.getErrorCount());
        assertEquals("booking", errors.getObjectName());
    }

    @Test
    void blankCustomerCreatesFieldError() {
        BookingForm form = good();
        form.setCustomer("   ");

        BeanPropertyBindingResult errors = check(form);
        FieldError field = errors.getFieldError("customer");

        assertNotNull(field);
        assertEquals("required", field.getCode());
        assertEquals("customer", field.getField());
        assertEquals("   ", field.getRejectedValue());
        assertFalse(field.isBindingFailure());
        assertEquals(1, errors.getFieldErrorCount());
    }

    @Test
    void missingSeatsIsDifferentFromZero() {
        BookingForm form = good();
        form.setSeats(null);

        BeanPropertyBindingResult errors = check(form);

        assertTrue(errors.hasFieldErrors("seats"));
        assertEquals("required",
            errors.getFieldError("seats").getCode());
        assertEquals(1, errors.getErrorCount());
    }

    @Test
    void zeroSeatsCreatesMinFieldError() {
        BookingForm form = good();
        form.setSeats(0);

        BeanPropertyBindingResult errors = check(form);
        FieldError field = errors.getFieldError("seats");

        assertNotNull(field);
        assertEquals("seats.min", field.getCode());
        assertEquals(0, field.getRejectedValue());
        assertEquals(0, errors.getGlobalErrorCount());
    }

    @Test
    void invalidRangeIsOneGlobalError() {
        BookingForm form = good();
        form.setEndDate(form.getStartDate());

        BeanPropertyBindingResult errors = check(form);

        assertEquals(0, errors.getFieldErrorCount());
        assertEquals(1, errors.getGlobalErrorCount());

        ObjectError global = errors.getGlobalError();
        assertNotNull(global);
        assertEquals("booking", global.getObjectName());
        assertEquals("booking.range.invalid",
            global.getCode());
    }

    @Test
    void missingDatesAreFieldErrors() {
        BookingForm form = good();
        form.setStartDate(null);
        form.setEndDate(null);

        BeanPropertyBindingResult errors = check(form);

        assertTrue(errors.hasFieldErrors("startDate"));
        assertTrue(errors.hasFieldErrors("endDate"));
        assertEquals(2, errors.getFieldErrorCount());
        assertEquals(0, errors.getGlobalErrorCount());
    }

    @Test
    void nestedEmailHasFullFieldPath() {
        BookingForm form = good();
        form.getContact().setEmail(" ");

        BeanPropertyBindingResult errors = check(form);
        FieldError field =
            errors.getFieldError("contact.email");

        assertNotNull(field);
        assertEquals("contact.email", field.getField());
        assertEquals("required", field.getCode());
        assertEquals("", errors.getNestedPath());
    }

    @Test
    void nullContactIsHandledGracefully() {
        BookingForm form = good();
        form.setContact(null);

        BeanPropertyBindingResult errors = check(form);

        assertTrue(errors.hasFieldErrors("contact"));
        assertEquals("required",
            errors.getFieldError("contact").getCode());
        assertFalse(errors.hasFieldErrors("contact.email"));
    }

    @Test
    void multipleFieldAndGlobalErrorsStaySeparate() {
        BookingForm form = good();
        form.setCustomer("");
        form.setSeats(0);
        form.setEndDate(form.getStartDate());
        form.getContact().setEmail("");

        BeanPropertyBindingResult errors = check(form);

        assertEquals(3, errors.getFieldErrorCount());
        assertEquals(1, errors.getGlobalErrorCount());
        assertEquals(4, errors.getErrorCount());
        assertEquals(4, errors.getAllErrors().size());
    }

    @Test
    void messageCodesHaveExpectedPriority() {
        BookingForm form = good();
        form.setCustomer("");

        BeanPropertyBindingResult errors = check(form);
        FieldError field = errors.getFieldError("customer");

        assertNotNull(field);
        assertArrayEquals(
            new String[] {
                "required.booking.customer",
                "required.customer",
                "required.java.lang.String",
                "required"
            },
            field.getCodes());
    }

    @Test
    void constructorDoesNotValidate() {
        BookingForm invalid = new BookingForm();
        BeanPropertyBindingResult result =
            new BeanPropertyBindingResult(invalid, "booking");

        assertFalse(result.hasErrors());
        validator.validate(invalid, result);
        assertTrue(result.hasErrors());
    }

    @Test
    void emptyAndWhitespaceHelpersDiffer() {
        BookingForm form = good();
        form.setCustomer("   ");

        BeanPropertyBindingResult result =
            new BeanPropertyBindingResult(form, "booking");

        ValidationUtils.rejectIfEmpty(
            result, "customer", "required");
        assertFalse(result.hasErrors());

        ValidationUtils.rejectIfEmptyOrWhitespace(
            result, "customer", "required");
        assertTrue(result.hasFieldErrors("customer"));
    }
}
~~~

**13 test methods** in this class cover: supports, valid form, whitespace, missing/zero seats, global rule, null dates, nested path, null nested bean, multiple simultaneous errors, message codes, constructor not auto-validating, and helper behavior. Each case creates a **new** `BeanPropertyBindingResult`, keeping tests independent.

The tests do not assert the order of `getAllErrors()` across multiple fields. The Spring Validator here records errors in a specific source order, but testing what matters more—**the right field/code/count**—avoids creating an unnecessary ordering contract.

## 9. Testing DataBinder and MessageSource separately

When you need to distinguish type conversion errors from custom validation errors, use `DataBinder`. When you need to test Vietnamese/English localization, use `StaticMessageSource`.

`src/test/java/com/example/validation/BindingAndMessageTest.java`:

~~~java
package com.example.validation;

import java.util.Locale;
import java.util.Map;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.context.support.StaticMessageSource;
import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;
import org.springframework.validation.ValidationUtils;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class BindingAndMessageTest {

    @Test
    void invalidIntegerIsBindingFailure() {
        BookingForm form = BookingValidatorTest.good();
        DataBinder binder = new DataBinder(form, "booking");

        binder.bind(new MutablePropertyValues(
            Map.of("seats", "not-a-number")));

        BindingResult result = binder.getBindingResult();
        FieldError field = result.getFieldError("seats");

        assertNotNull(field);
        assertTrue(field.isBindingFailure());
        assertEquals("typeMismatch", field.getCode());
        assertEquals("not-a-number",
            field.getRejectedValue());
    }

    @Test
    void directResultDoesNotBindProperties() {
        BookingForm form = BookingValidatorTest.good();
        BeanPropertyBindingResult result =
            new BeanPropertyBindingResult(form, "booking");

        assertEquals(2, form.getSeats());
        assertFalse(result.hasErrors());
        assertEquals(form, result.getTarget());
    }

    @Test
    void translatesFieldErrorToVietnamese() {
        BookingForm form = BookingValidatorTest.good();
        form.setCustomer("");

        BeanPropertyBindingResult result =
            new BeanPropertyBindingResult(form, "booking");

        ValidationUtils.rejectIfEmptyOrWhitespace(
            result, "customer", "required");

        FieldError field = result.getFieldError("customer");
        assertNotNull(field);

        Locale vi = Locale.forLanguageTag("vi");
        StaticMessageSource source = new StaticMessageSource();

        source.addMessage(
            "required.booking.customer",
            vi,
            "Vui lòng nhập tên khách.");
        source.addMessage(
            "required",
            vi,
            "Trường này bắt buộc.");

        assertEquals(
            "Vui lòng nhập tên khách.",
            source.getMessage(field, vi));
    }

    @Test
    void translatesSameCodeToEnglish() {
        BookingForm form = BookingValidatorTest.good();
        form.setCustomer("");

        BeanPropertyBindingResult result =
            new BeanPropertyBindingResult(form, "booking");

        ValidationUtils.rejectIfEmptyOrWhitespace(
            result, "customer", "required");

        FieldError field = result.getFieldError("customer");
        assertNotNull(field);

        StaticMessageSource source = new StaticMessageSource();
        source.addMessage(
            "required.booking.customer",
            Locale.ENGLISH,
            "Customer name is required.");

        assertEquals(
            "Customer name is required.",
            source.getMessage(field, Locale.ENGLISH));
    }
}
~~~

**Total 17 tests in the project:** 13 tests in `BookingValidatorTest` and 4 tests in `BindingAndMessageTest`. This is the intended test design; no claim is made that Gradle was executed in the article environment.

### Running

If you already have the Gradle wrapper:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

If this is a newly created project with only `build.gradle` and Gradle is installed on the machine, you can generate the wrapper:

~~~bash
gradle wrapper
./gradlew test
~~~

The tests use Spring classes without starting a server. `StaticMessageSource` is an in-memory source, so it does not require a `messages_vi.properties` file; it lets you prove message code fallback independently of the CI filesystem/locale.

## 10. `BeanPropertyBindingResult` and `DataBinder` are not the same

A common mistake is treating `BeanPropertyBindingResult` as an HTTP data converter. In reality:

~~~java
BookingForm form = new BookingForm();
BeanPropertyBindingResult result =
    new BeanPropertyBindingResult(form, "booking");
~~~

only creates an error holder. To convert request/form strings into Java properties:

~~~java
DataBinder binder = new DataBinder(form, "booking");
MutablePropertyValues input = new MutablePropertyValues();

input.add("seats", "abc");
binder.bind(input);

BindingResult result = binder.getBindingResult();
~~~

`binder.bind(...)` performs property binding and type conversion. If `"abc"` cannot be converted to `Integer`, a `FieldError` with `typeMismatch`/`isBindingFailure()==true` can appear. If you want to run a custom validator **after** binding:

~~~java
DataBinder binder = new DataBinder(form, "booking");
binder.setValidator(new BookingValidator());

binder.bind(input);
binder.validate();

BindingResult result = binder.getBindingResult();
~~~

This is a snippet in a context where `form`/`input` variables exist. Both binding errors and validation errors can live in the same `BindingResult` of the binder, but that does not mean all errors come from the same source.

**Do not create a separate `BeanPropertyBindingResult` yourself to read DataBinder's results.** Always retrieve `binder.getBindingResult()`.

### Why test across multiple layers?

| Goal | Tool to use |
|---|---|
| Which invalid data `BookingValidator` rejects | `BeanPropertyBindingResult` |
| `"123"` converts to `Integer 123` | `DataBinder` |
| `"abc"` causes `typeMismatch` | `DataBinder` |
| Whether `@InitBinder` attaches the validator to MVC | MockMvc |
| Whether `@Valid @ModelAttribute` executes properly | MockMvc |
| Whether `@RequestBody` parses JSON and returns HTTP 400 properly | MockMvc |
| Whether Jakarta constraints on DTO take effect | Appropriate Jakarta Validator/test context |
| Whether `MessageSource` picks the right translation | `StaticMessageSource` or bundle integration tests |

Unit tests pinpoint bugs in small pieces of logic; integration tests verify wiring and runtime behavior. Do not automatically require `@SpringBootTest` for every `Validator` unit test.

## 11. Message codes, getCode, and localization

`BeanPropertyBindingResult` normally uses `DefaultMessageCodesResolver`. With `errors.rejectValue("customer","required",...)` on object `booking` and Java type `String`, the candidate codes can be:

~~~text
required.booking.customer
required.customer
required.java.lang.String
required
~~~

**Ordered from most specific to most general** for `MessageSource` lookup. Distinguish:

- `error.getCodes()[0]`: the most specific key (under default configuration).
- `error.getCode()`: the base/default code, usually the last element, e.g., `required`.
- `error.getDefaultMessage()`: fallback message when none of the keys resolve.
- `messageSource.getMessage(error, locale)`: the actual localized message.

An object-wide error `booking.range.invalid` on object `booking` typically has:

~~~text
booking.range.invalid.booking
booking.range.invalid
~~~

For nested fields like `contact.email` or indexed properties like `items[0].sku`, the resolver can generate additional key variants with/without the nested index. **Do not assume every field error always has only four keys**.

### Why do i18n tests need to be separated?

If you only assert that `getDefaultMessage()` contains an English sentence, the test **does not prove** the app translates to Vietnamese. `StaticMessageSource` lets you register keys explicitly and call `getMessage(field,Locale.forLanguageTag("vi"))`.

For multi-controller applications, you can use `messages.properties` and `messages_vi.properties` via Spring Boot MessageSource auto-configuration, though that is a different integration layer, not part of plain unit tests.

## 12. Nested paths, JavaBeans, and collections

`BeanPropertyBindingResult` reads nested property paths like `contact.email` via JavaBean access. If a model has `List<Item> items`, a validator can do:

~~~java
for (int i = 0; i < form.getItems().size(); i++) {
    errors.pushNestedPath("items[" + i + "]");
    try {
        ValidationUtils.rejectIfEmptyOrWhitespace(
            errors, "sku", "required");
    }
    finally {
        errors.popNestedPath();
    }
}
~~~

This is a snippet **not belonging to the main project**; it requires a class with `getItems()` and item JavaBeans with `getSku()`. It illustrates how an error gets the field path `items[0].sku`.

You must check null/empty collections, null elements, boundary indices, element counts, and nested path state after the loop. `BeanPropertyBindingResult` can support auto-growing certain nested paths depending on configuration, but you should **not** rely on auto-grow to "patch" fixtures missing objects: construct test data explicitly.

**Bean property access vs direct field:** If a project intentionally binds directly to fields without getters/setters, Spring provides `DirectFieldBindingResult`; do not expect `BeanPropertyBindingResult` to have the same semantics automatically. For immutable records/constructor binding, test the DTO creation/binding mechanism separately.

## 13. Common mistakes and fixes

| Symptom | Cause | How to fix |
|---|---|---|
| `hasErrors()==false` despite invalid fixture | Only instantiated result, never called `validate` | Call `validator.validate(target,result)` |
| Test calling validate directly PASSES, but MVC does not use validator | Wrong `supports`/not registered via binder | Test supports and add integration test |
| Error has field name `email` instead of `contact.email` | Missing nested path | Push `contact`, reject `email`, pop |
| Errors after email become `contact.seats` | Forgot to pop nested path | Use `try/finally` |
| `NullPointerException` when contact is null | Validator does not check child object | Reject field `contact` first |
| `getAllErrors()` is greater than `getFieldErrors()` | Global errors exist | Check the two lists separately |
| Cross-field rule appears under `endDate` | Used `rejectValue` instead of `reject` | Choose global error when rule belongs to the whole object |
| Object-based error codes differ from production | Test uses a different objectName than `@ModelAttribute` | Use the same logical name |
| Unit validator does not report typeMismatch for string `"abc"` | No binding step | Use a `DataBinder` test |
| `isBindingFailure()==false` on custom reject | This is a validation error | Expected behavior; differs from conversion |
| `@NotNull` annotation is not enforced | Jakarta provider not invoked | Test Jakarta Validation separately |
| `getDefaultMessage()` is not in Vietnamese | MessageSource not resolved | Use `messageSource.getMessage(error,vi)` |
| Different tests interfere and cause recurring failures | Shared mutable `BindingResult`/DTO | Create new fixture and result |
| Field tested with two errors but only one seen | Used `getFieldError(field)` | Use `getFieldErrors(field)` |
| Changing `String` to `Integer` breaks code assertions | Fallback key includes Java field type | Check `getCodes()` and the contract |
| MockMvc does not reflect unit test | Different wiring/binding/annotations | Separate logic tests from framework tests |
| Test dumps raw rejected password | Leaks synthetic/real secret in logs | Assert only keys/codes with dummy data |

### Debugging sequence

1. Does the validator implement `supports(...)` properly?
2. Is the fixture a JavaBean with a getter for the field under test?
3. Was `BeanPropertyBindingResult` created for the **right target and objectName**?
4. Was `validator.validate(...)` called?
5. Was the error recorded with `rejectValue` or `reject`?
6. Do `getFieldErrorCount()`/`getGlobalErrorCount()` reflect the right error types?
7. Was the nested path restored?
8. Do `getCode()` and `getCodes()` mean what you expect?
9. Is this a conversion error, meaning `DataBinder` is needed rather than Validator?
10. If the error only happens over HTTP, is there a MockMvc integration test?

## 14. Practice exercises

**1. Does the `BeanPropertyBindingResult` constructor automatically call `validate`?** No.

**2. Why test `supports` separately?** Because calling `validate` directly does not force a supports check to run.

**3. What does `rejectValue("seats","seats.min")` create?** A `FieldError` on `seats`.

**4. What does `reject("booking.range.invalid")` create?** An `ObjectError`/global error.

**5. Does `getAllErrors()` include field errors?** Yes, because `FieldError` extends `ObjectError`.

**6. Is a string of three spaces rejected by `rejectIfEmpty`?** Not for whitespace alone; `rejectIfEmptyOrWhitespace` handles that.

**7. Under what name is the nested email field stored when pushing `contact`?** `contact.email`.

**8. Why use `try/finally` with `pushNestedPath`?** Ensures popping and avoids corrupting the path of subsequent errors.

**9. Is `getCode()` always the most specific code?** No, it is the default code; `getCodes()[0]` is usually the most specific under the default resolver.

**10. When a client sends text that cannot convert to Integer, is a unit Validator test enough?** No, a `DataBinder`/HTTP binding test is needed.

**11. Is a full Spring ApplicationContext required for `StaticMessageSource`?** No, you can instantiate it and register messages in a unit test.

**12. Why not serialize the raw `BindingResult` to a REST API?** It can expose the target object, rejected values, and internal info/PII.

## 15. Testing checklist

- [ ] Use `org.springframework.validation.BeanPropertyBindingResult` properly.
- [ ] Choose `objectName` matching the model name when message codes need comparison.
- [ ] Test `supports` for both valid and invalid classes.
- [ ] Give each test a fresh fixture/result.
- [ ] Call `validate(target,result)` explicitly.
- [ ] Include a happy-path test with no errors.
- [ ] Include null, blank, whitespace, zero, and boundary values.
- [ ] Assert field path, code, and scope for errors.
- [ ] Assert `getFieldErrors`/`getGlobalErrors` and total count separately.
- [ ] For nested beans, handle null and ensure the nested path is popped.
- [ ] Use `getFieldErrors(field)` when a field has multiple errors.
- [ ] Do not confuse validation with binding/type conversion.
- [ ] If i18n is needed, test `MessageSource` with an explicit locale.
- [ ] Do not rely on unguaranteed error ordering.
- [ ] Do not serialize/log sensitive rejected values.
- [ ] Add DataBinder/MockMvc tests if requirements cover HTTP.
- [ ] Run `./gradlew test` on the actual project before claiming a build PASSED.

**Remember:** `BeanPropertyBindingResult` helps unit-test a Spring `Validator` at the **object → errors** level: build a JavaBean, create a result with the right object name, call `validate`, and assert the recorded `FieldError`/`ObjectError` entries. It does not bind HTTP automatically, does not trigger Jakarta Bean Validation, and does not replace integration tests. Use `DataBinder` for type conversion, `MessageSource` for localization, and MockMvc for the Spring MVC lifecycle.

## Official references

- [Spring 6.2 — BeanPropertyBindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/BeanPropertyBindingResult.html)
- [Spring 6.2 — Validator Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/Validator.html)
- [Spring — Validation with Spring Validator](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring 6.2 — ValidationUtils Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/ValidationUtils.html)
- [Spring 6.2 — Errors Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/Errors.html)
- [Spring 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring 6.2 — DefaultMessageCodesResolver Javadoc](https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/validation/DefaultMessageCodesResolver.html)
- [Spring — Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [JUnit 5.11.4 — User Guide](https://docs.junit.org/5.11.4/user-guide/)
