# Designing Field Errors and Object-Level Errors in Spring Framework

In a form or REST API, input data can be invalid at a **specific field** or invalid due to the **relationship between multiple fields**. These two situations should be represented differently:

- **Field error (*field error*)**: an input value has the wrong type or violates a field constraint. For example, `seats=0` violates `@Min(1)`, `customer=""` violates `@NotBlank`, and `startDate=abc` cannot be converted to `LocalDate`.
- **Object-level/global error (*object-level/global error*)**: an object is invalid when multiple fields are evaluated together, even though each field may be valid on its own. For example, `endDate` must be **after** `startDate`; a date range from Dec 20 to Dec 19 is invalid according to business rules.

Spring provides dedicated error types: `FieldError` and `ObjectError`, collected inside `Errors`/`BindingResult`. When designing JSON error responses, you should **preserve this distinction** so the frontend knows which errors to place right under an input and which to display in the general form area.

Example of a custom application response:

~~~json
{
  "type": "https://example.org/problems/invalid-booking",
  "title": "Invalid booking request",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "seats",
      "code": "Min",
      "message": "Seats must be at least 1."
    }
  ],
  "objectErrors": [
    {
      "code": "booking.range.invalid",
      "message": "End date must be after start date."
    }
  ],
  "suppressedFieldCount": 0
}
~~~

This is **not Spring's default JSON**; it is a proposed contract that will be implemented in a Spring Boot application in Section 9. It uses several familiar Problem Details fields and two extension lists `fieldErrors`/`objectErrors`, but the example code returns a Java `record` and does not claim to be using standard RFC 9457 `ProblemDetail`.

This lesson belongs to the **Error Responses** topic of the Spring Framework — validation/data binding module; it focuses on Spring MVC (Servlet stack), Jakarta Validation, Spring `Validator`, i18n, HTTP response consistency, and common pitfalls. The hands-on example uses **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x**.

## 1. Foundations: `ObjectError`, `FieldError`, and `BindingResult`

Spring defines:

~~~java
org.springframework.validation.ObjectError
org.springframework.validation.FieldError
org.springframework.validation.Errors
org.springframework.validation.BindingResult
~~~

`FieldError` **extends** `ObjectError`, carrying additional information for a specific field. `BindingResult` extends `Errors` to combine data binding results with validation.

| API | Meaning | Use case |
|---|---|---|
| `errors.hasErrors()` | At least one field or global error exists | Check whether the request passed binding/validation |
| `errors.hasFieldErrors()` | Field-level errors exist | Display under inputs |
| `errors.hasGlobalErrors()` | Object-level errors exist | Display in the form overview section |
| `errors.getFieldErrors()` | List of `FieldError` | Build `fieldErrors` in JSON |
| `errors.getGlobalErrors()` | List of `ObjectError` at the object level only | Build `objectErrors` in JSON |
| `errors.getAllErrors()` | All object/field errors | Summary counts or safe logging |
| `errors.getFieldError("seats")` | First error of the specified field | Simple UI, though it may miss other errors |
| `errors.getFieldErrors("seats")` | All errors of a single field | When multiple constraints apply to one field |
| `errors.getFieldErrorCount()` | Number of field **error entries** | Not always the number of distinct fields |
| `errors.getGlobalErrorCount()` | Number of global error entries | Number of object-level errors |
| `errors.getObjectName()` | Name of the root object being bound | Affects message codes |
| `bindingResult.getSuppressedFields()` | Names of fields blocked by binding policy | Check for over-posting/mass assignment |

**Note:** `getAllErrors()` also returns `FieldError` instances because `FieldError extends ObjectError`. If you put **all** of `getAllErrors()` into `objectErrors`, you will **mix field errors into object errors**, making it harder for the UI to categorize them.

### Conceptual data structure

~~~text
BindingResult("booking")
|
+-- FieldError(field="seats", code="Min")
|       |
|       +-- objectName = "booking"
|       +-- field = "seats"
|       +-- rejectedValue = 0 (should not be exposed in public API)
|       +-- codes = ["Min.booking.seats", ... , "Min"]
|
+-- FieldError(field="customer", code="NotBlank")
|       |
|       +-- field = "customer"
|
+-- ObjectError(code="booking.range.invalid")
        |
        +-- objectName = "booking"
        +-- no single field
~~~

This is a **composite scenario**; not every request produces all three errors. An object-level error can be registered by a validator via `errors.reject(...)` or by a Jakarta Validation constraint placed at the class level.

## 2. When to use a field error vs. an object error?

**Use a field error** if the user can fix a specific input without checking the state of other fields. For example:

- `customer` is blank → `NotBlank`.
- `seats` is 0 → `Min`.
- `seats=abc` → `typeMismatch`.
- `contact.email` has an invalid format → `Email` or a custom field validator.
- `travellers[0].passportNumber` is missing → nested field path error.

**Use an object error** when an invariant involves multiple fields or the object itself:

- `endDate` must be later than `startDate`.
- Only **one of** `companyTaxId` and `personalId` may be filled in.
- `discountAmount` must not exceed `orderTotal`.
- At least one of `email` or `phone` must be present.
- `minimumPrice` must not be greater than `maximumPrice`.

Practical rule: **place the error where it makes sense to fix**, not based on where the validator code happens to live (class vs. field). A cross-field constraint can intentionally attach a violation to `endDate` if that is a deliberate UI policy, but when the error truly concerns the relationship between two fields, a **global error** usually expresses it more clearly.

| Condition | Appropriate error channel | Why |
|---|---|---|
| `seats=0`, minimum 1 | Field `seats` | This input directly violates the rule |
| `startDate=not-a-date` | Field `startDate` | Value cannot be parsed |
| `startDate=2026-12-20`, `endDate=2026-12-19` | Object `booking` | Both individual dates have valid types |
| `customer=""` | Field `customer` | User immediately knows which input to fix |
| Both `email` and `phone` are blank | Object `contactForm` | Condition spans two fields |
| User permission rule forbids booking | Separate domain/security error | Do not conflate every authorization error with form validation |
| Request contains `admin` field outside allowlist | Binding policy/suppressed fields | **Not automatically** a global error |

Do not force every domain error into Bean Validation: inventory checks, ownership checks, or transaction state checks may require service/domain exceptions and distinct HTTP statuses. `BindingResult` is especially suited for errors detected at the **data binding and object validation** boundary.

## 3. Steps for creating errors in Spring MVC

With the handler:

~~~java
@PostMapping("/preview")
public ResponseEntity<?> preview(
        @Valid @ModelAttribute("booking") BookingForm form,
        BindingResult errors) {
    // ...
}
~~~

Spring MVC executes the following general flow:

~~~text
HTTP request (form/query)
        |
        v
HandlerMethodArgumentResolver
        |
        v
WebDataBinder
  - creates/obtains BookingForm
  - binds request parameters
  - converts types via ConversionService
  - records typeMismatch / binding errors
        |
        v
Bean Validation / Spring Validator
  - @NotBlank on customer
  - @Min(1) on seats
  - custom rule: endDate > startDate
        |
        v
BindingResult
  +-- getFieldErrors(): field issues
  +-- getGlobalErrors(): object issues
  +-- getSuppressedFields(): rejected binding keys
        |
        v
Controller builds HTTP response
  - 200 if valid and allowed by policy
  - 400 if input errors exist
        |
        v
Client / frontend
  - per-input errors
  - form-level errors
~~~

**`BindingResult` must immediately follow** the method argument it describes. Without `BindingResult` in the exact position, Spring MVC may throw `MethodArgumentNotValidException` instead of letting the handler process it directly. If the method also has constraints directly on parameters, Spring MVC 6.1+ may use **`HandlerMethodValidationException`**; do not infer the exception type solely from `@Valid`.

### Distinguishing type conversion errors from constraint errors

~~~text
seats=abc
     |
     +-- Integer conversion FAILED
     |
     +-- FieldError(code="typeMismatch")
~~~

versus:

~~~text
seats=0
     |
     +-- Integer conversion SUCCESS
     |
     +-- @Min(1) FAILED
     |
     +-- FieldError(code="Min")
~~~

Both errors may appear in `fieldErrors`, but their **originating codes differ**. When a value fails type conversion, you should not pile additional business errors onto a number that does not exist yet. A cross-field validator should skip cases where a related input is `null`/invalid in type to avoid overlapping, confusing messages.

## 4. Creating object-level errors with Spring `Validator`

Spring `Validator` has two core methods:

~~~java
boolean supports(Class<?> clazz);

void validate(Object target, Errors errors);
~~~

To create an **object-level** error:

~~~java
errors.reject(
    "booking.range.invalid",
    "End date must be after start date");
~~~

And to create a **field-level** error:

~~~java
errors.rejectValue(
    "endDate",
    "booking.endDate.invalid",
    "End date is invalid");
~~~

Both snippets assume an `errors` variable is already in scope inside `Validator.validate(...)`; they are not standalone Java files. `reject(...)` creates an `ObjectError`. `rejectValue(...)` creates a `FieldError` (except in special cases with an empty nested path handled by Spring according to the `Errors` contract).

### Illustrating a validator checking two dates

~~~java
public void validate(Object target, Errors errors) {
    BookingForm form = (BookingForm) target;

    if (form.getStartDate() == null ||
            form.getEndDate() == null) {
        return; // Missing date errors are handled by @NotNull.
    }

    if (!form.getEndDate().isAfter(form.getStartDate())) {
        errors.reject(
            "booking.range.invalid",
            "End date must be after start date");
    }
}
~~~

The snippet above is an illustrative method; the complete class is in Section 9. When start and end are both valid `LocalDate` values but end is not after start, Spring records **one global error**. Do not generate duplicate `FieldError` entries for both dates if that only repeats the same message.

**Ordering consideration:** validation runs after conversion/binding; if `startDate` cannot be converted, the `typeMismatch` field error already exists. The validator checks for null to avoid reporting a meaningless "end before start" error when there is no start date yet.

### `@InitBinder` registers the validator in the right scope

In the controller:

~~~java
@InitBinder("booking")
public void init(WebDataBinder binder) {
    binder.addValidators(new BookingDatesValidator());
}
~~~

For the model attribute named `booking`, Spring `WebDataBinder` can run the custom validator alongside already-configured validators when validation is triggered by `@Valid` or `@Validated`. Do not casually call `setValidator(...)` to replace the entire default validator if you still need Jakarta Bean Validation for `@Min`/`@NotBlank`. `addValidators(...)` is **additive**.

Do not assume every JSON `@RequestBody` invokes the exact same logic as an `@ModelAttribute` form in all circumstances. Handler resolvers, message decoding, validation phases, and exception types must be verified for the specific web stack.

## 5. Creating object-level errors with Jakarta Bean Validation

Another approach is defining a **class-level constraint**. Example custom annotation:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidBookingRangeValidator.class)
public @interface ValidBookingRange {
    String message() default "Invalid date range";
    Class<?>[] groups() default {};
    Class<? extends Payload>[] payload() default {};
}
~~~

This is an **illustration**; it requires `java.lang.annotation.*`, `jakarta.validation.Constraint`, and `Payload` imports. A `ConstraintValidator<ValidBookingRange, BookingForm>` reads both dates and returns `false` when they do not form a valid range.

By default, a violation from a **class-level** constraint has a property path pointing to the bean, so when Spring's adapter converts it to `BindingResult`, it is typically represented as an **object-level error**. If inside `ConstraintValidatorContext` you explicitly call `addPropertyNode("endDate")`, the violation can be attached to the **`endDate` field** instead of the object.

Key points to remember:

- **Where the constraint is attached** and the **violation's property path** determine whether it becomes a `FieldError` or an `ObjectError`.
- `@AssertTrue` placed on a getter `isRangeValid()` can generate an error for **property `rangeValid`**, not necessarily a global error like a class-level constraint.
- A class-level constraint does not replace explaining to the frontend where to display the message. Design the API contract first, then choose the appropriate violation style.
- Do not place a validator that synchronously queries a database or an HTTP service on every binding if you only need to validate the structure of two dates.

The hands-on example uses Spring `Validator` so learners can clearly see the difference between `reject(...)` and `rejectValue(...)`, without requiring a full class-level annotation setup.

## 6. What should the JSON error response structure contain?

An API serving a frontend might choose this structure:

~~~json
{
  "type": "https://example.org/problems/invalid-booking",
  "title": "Invalid booking request",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "customer",
      "code": "NotBlank",
      "message": "Customer name is required."
    },
    {
      "field": "seats",
      "code": "Min",
      "message": "Seats must be at least 1."
    }
  ],
  "objectErrors": [
    {
      "code": "booking.range.invalid",
      "message": "End date must be after start date."
    }
  ],
  "suppressedFieldCount": 0
}
~~~

Each field carries a distinct responsibility:

| Field | Meaning | Recommendation |
|---|---|---|
| `type` | URI identifying the problem type | Use a stable system-defined URI |
| `title` | Short error type name | Can be localized if the API contract allows |
| `status` | Corresponding HTTP status | Match the actual status; do not hardcode 400 for every exception |
| `code` | Machine-readable response code | Stable, independent of translated text |
| `fieldErrors[]` | Errors located at a field | Allow a field to appear multiple times when violating multiple constraints |
| `objectErrors[]` | Cross-field or whole-object errors | Do not invent a synthetic field |
| `field` | Java/request DTO field path | Map in a controlled way to frontend input names |
| `message` | Human-readable translated message | Locale determined by request/context |
| `suppressedFieldCount` | Count of fields blocked by binding policy | Signals out-of-allowlist input without exposing the input |

**`fieldErrors[]` and `objectErrors[]` should always be present**, even when empty arrays. That lets the frontend handle responses uniformly without distinguishing missing properties, `null`, and empty arrays.

**Do not use element order as an identifier.** A Jakarta validator may return errors in different orders when the constraint set or provider changes. The frontend should inspect `field` and `code`, never assuming `fieldErrors[0]` is always `customer` when a request has multiple errors.

### Technical codes vs. stable API codes

`FieldError.getCode()` can return `Min`/`NotBlank`/`typeMismatch`. These codes are great for **learning the mechanism and routing messages**. For public APIs and long-lived clients, you can map them to stable business codes:

| Internal code | Suggested API code | Meaning for client |
|---|---|---|
| `NotBlank` / `NotNull` | `REQUIRED_FIELD` | Input is required |
| `Min` | `VALUE_BELOW_MIN` | Value is below the minimum |
| `typeMismatch` | `INVALID_FORMAT` | Value has wrong type/format |
| `booking.range.invalid` | `BOOKING_DATE_RANGE_INVALID` | Invalid date range |

The hands-on sample keeps `getCode()` in each issue so Spring's behavior is easy to trace; production systems can map these to dedicated public codes. Avoid coupling the frontend to class names, constraint providers, or translated messages.

### Should `rejectedValue` be returned?

`FieldError` has `getRejectedValue()`, but **never unconditionally serialize the entire `FieldError` from a request into the response**. The invalid field could be a password, token, email, personal data, or a huge input string. Return only `field`, code, and a safe message; restrict what gets logged.

### Do global errors need `"field": null`?

No. Using two separate lists keeps the types/schema clean:

- `fieldErrors[]` has `field`.
- `objectErrors[]` does not have `field`.

That way the UI can render `objectErrors` in a banner or at the top of the form, and `fieldErrors` right beneath the corresponding inputs. If using a single list, add a discriminator such as `scope: "FIELD" | "OBJECT"` rather than turning every global error into a fake field.

## 7. Problem Details standard error responses (RFC 9457)

Spring Framework supports `ProblemDetail`, `ErrorResponse`, and `ResponseEntityExceptionHandler` for RFC 9457. Typically `ProblemDetail` contains:

- `type` — URI identifying the problem type.
- `title` — short summary.
- `status` — HTTP status.
- `detail` — specific explanation (if any).
- `instance` — URI of the occurrence (if any).

Extension properties such as `fieldErrors` and `objectErrors` can be added. With Jackson in Spring, entries in `ProblemDetail.properties` are typically unwrapped into top-level JSON fields.

Example **illustrative snippet** inside a response-building method:

~~~java
ProblemDetail detail = ProblemDetail.forStatus(
    HttpStatus.BAD_REQUEST);

detail.setType(URI.create(
    "https://example.org/problems/invalid-booking"));
detail.setTitle("Invalid booking request");
detail.setDetail("One or more fields or form rules are invalid.");
detail.setProperty("code", "VALIDATION_FAILED");
detail.setProperty("fieldErrors", fieldIssues);
detail.setProperty("objectErrors", objectIssues);

return ResponseEntity.badRequest().body(detail);
~~~

This requires imports and the `fieldIssues`/`objectIssues` variables in scope; it is not a standalone class. If you want to return **application/problem+json** and follow the RFC 9457 model directly, `ProblemDetail` is a strong choice. The runnable sample in Section 9 intentionally returns a Java record with explicit JSON so learners can match every field one-to-one; you can switch to `ProblemDetail` in a real project.

**Status warning:** some business/domain errors use 409, not-found errors use 404, authorization errors use 403, and return-value method validation may produce 500. Do not catch every exception and return `"VALIDATION_FAILED"` with HTTP 400. This lesson's example returns 400 **only for form input validation/binding failures**.

## 8. I18n: locale-aware messages, stable codes

Spring lets you turn `FieldError`/`ObjectError` into localized sentences using `MessageSource`:

~~~java
String translated = messageSource.getMessage(
    error, locale);
~~~

Both error types implement `MessageSourceResolvable` with `getCodes()`, `getArguments()`, and `getDefaultMessage()`. `DefaultMessageCodesResolver` generates fallback candidates such as:

~~~text
Min.booking.seats
Min.seats
Min.java.lang.Integer
Min
~~~

and for a global error:

~~~text
booking.range.invalid.booking
booking.range.invalid
~~~

`MessageSource` tries the codes in order to find a matching message in `messages.properties`/`messages_vi.properties`. Do not treat `error.getDefaultMessage()` as proof that your application's translation was used, because the default message may already be interpolated by the Jakarta Validation provider.

A request with:

~~~http
Accept-Language: vi
~~~

can receive:

~~~json
{"field":"seats","code":"Min","message":"Số chỗ phải ít nhất là 1."}
~~~

The same error with:

~~~http
Accept-Language: en
~~~

can receive:

~~~json
{"field":"seats","code":"Min","message":"Seats must be at least 1."}
~~~

**The `Min` code does not change with locale; only the `message` text changes.** This lets the frontend drive logic by code while still displaying localized text.

If the resource bundle lacks a key, Spring may fall back to the default message when available, or throw `NoSuchMessageException` in certain overloads. Real applications should provide safe fallback translations and test both primary locales and missing-key cases.

## 9. Complete Spring Boot 3.5 example: field error + object error

Let's build a **booking preview** endpoint (without database writes):

- Form fields: `customer`, `seats`, `startDate`, `endDate`.
- `customer` must not be blank (`@NotBlank`).
- `seats` must be non-null and at least 1 (`@NotNull`, `@Min(1)`).
- Both dates must have values (`@NotNull`).
- `endDate` must be **after** `startDate` — checked by an **object-level Spring `Validator`**.
- Unknown/disallowed bound fields are recorded in `getSuppressedFields()`.
- The endpoint returns HTTP 200 when valid; HTTP 400 with **two separate lists** when invalid.

Uses Spring MVC Servlet, Java 17+, Spring Boot 3.5.x/Spring Framework 6.2.x. All Java files live in package `com.example.bookingerrors`. The project is generated from Spring Initializr with Spring Web + Validation.

### 9.1. Gradle dependencies

In a project with the Spring Boot Gradle plugin, repositories, and dependency management already configured:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Classes importing Spring/Jakarta cannot be compiled with plain JDK alone without the library classpath. Run through the Gradle wrapper of a valid Spring Boot project.

### 9.2. `BookingErrorsApplication.java`

File `src/main/java/com/example/bookingerrors/BookingErrorsApplication.java`:

~~~java
package com.example.bookingerrors;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BookingErrorsApplication {

    public static void main(String[] args) {
        SpringApplication.run(BookingErrorsApplication.class, args);
    }
}
~~~

`@SpringBootApplication` scans the current package and subpackages, so the controller in the same package is discovered.

### 9.3. `BookingForm.java`

File `src/main/java/com/example/bookingerrors/BookingForm.java`:

~~~java
package com.example.bookingerrors;

import java.time.LocalDate;

import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

import org.springframework.format.annotation.DateTimeFormat;

public class BookingForm {

    @NotBlank
    private String customer;

    @NotNull
    @Min(1)
    private Integer seats;

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate startDate;

    @NotNull
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    private LocalDate endDate;

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
}
~~~

`@DateTimeFormat(ISO.DATE)` lets `WebDataBinder` convert ISO strings such as `2026-12-20` into `LocalDate`. If a client sends `20/12/2026` while the formatter expects ISO, conversion fails and produces a field error.

Using `Integer seats` instead of primitive `int` distinguishes a missing value (`null`) from `0`. `@NotNull` checks for absence, and `@Min(1)` checks for values below 1 when a valid number is present. These choices make error reporting clearer.

The DTO intentionally omits an `admin` field. When a client tries to send `admin=true`, the binder's allowed-fields policy records a suppressed field so we can explicitly reject out-of-contract input.

### 9.4. `BookingDatesValidator.java` — creating a global error

File `src/main/java/com/example/bookingerrors/BookingDatesValidator.java`:

~~~java
package com.example.bookingerrors;

import org.springframework.validation.Errors;
import org.springframework.validation.Validator;

public final class BookingDatesValidator implements Validator {

    @Override
    public boolean supports(Class<?> clazz) {
        return BookingForm.class.isAssignableFrom(clazz);
    }

    @Override
    public void validate(Object target, Errors errors) {
        BookingForm form = (BookingForm) target;

        // When either date is missing, let @NotNull handle the field error.
        if (form.getStartDate() == null ||
                form.getEndDate() == null) {
            return;
        }

        if (!form.getEndDate().isAfter(form.getStartDate())) {
            errors.reject(
                "booking.range.invalid",
                "End date must be after start date");
        }
    }
}
~~~

**Why use `reject`?** A "valid" end date can only be determined when the start date is known. Having valid data types for both dates does not guarantee the whole **`BookingForm`** is valid. `errors.reject(...)` creates an `ObjectError`; `errors.rejectValue(...)` creates a `FieldError` for a specific field.

`supports(...)` declares that this validator can validate `BookingForm`. The class holds no per-request state, so it is safe to reuse. The example instantiates it in `@InitBinder` for simplicity; production code can inject a stateless bean.

**Avoid duplicate errors:** if a date is missing or failed to parse, the validator does not emit an extra date-range error. `@NotNull`/binding handles the specific issue first.

### 9.5. `BookingController.java` — mapping to two JSON lists

File `src/main/java/com/example/bookingerrors/BookingController.java`:

~~~java
package com.example.bookingerrors;

import java.util.List;
import java.util.Locale;

import jakarta.validation.Valid;

import org.springframework.context.MessageSource;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/bookings")
public class BookingController {

    private final MessageSource messages;

    public BookingController(MessageSource messages) {
        this.messages = messages;
    }

    @InitBinder("booking")
    public void configureBookingBinder(WebDataBinder binder) {
        binder.setAllowedFields(
            "customer", "seats", "startDate", "endDate");
        binder.addValidators(new BookingDatesValidator());
    }

    @PostMapping(
        path = "/preview",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE
    )
    public ResponseEntity<?> preview(
            @Valid @ModelAttribute("booking") BookingForm form,
            BindingResult binding,
            Locale locale) {

        int suppressedCount =
            binding.getSuppressedFields().length;

        if (!binding.hasErrors() && suppressedCount == 0) {
            return ResponseEntity.ok(
                new PreviewAccepted("VALID"));
        }

        List<FieldIssue> fieldIssues =
            binding.getFieldErrors()
                .stream()
                .map(error -> toFieldIssue(error, locale))
                .toList();

        List<ObjectIssue> objectIssues =
            binding.getGlobalErrors()
                .stream()
                .map(error -> toObjectIssue(error, locale))
                .toList();

        ValidationProblem problem = new ValidationProblem(
            "https://example.org/problems/invalid-booking",
            "Invalid booking request",
            400,
            "VALIDATION_FAILED",
            fieldIssues,
            objectIssues,
            suppressedCount
        );

        return ResponseEntity.badRequest().body(problem);
    }

    private FieldIssue toFieldIssue(
            FieldError error, Locale locale) {

        return new FieldIssue(
            error.getField(),
            error.getCode(),
            messages.getMessage(error, locale)
        );
    }

    private ObjectIssue toObjectIssue(
            ObjectError error, Locale locale) {

        return new ObjectIssue(
            error.getCode(),
            messages.getMessage(error, locale)
        );
    }

    public record PreviewAccepted(String result) {
    }

    public record FieldIssue(
        String field,
        String code,
        String message
    ) {
    }

    public record ObjectIssue(
        String code,
        String message
    ) {
    }

    public record ValidationProblem(
        String type,
        String title,
        int status,
        String code,
        List<FieldIssue> fieldErrors,
        List<ObjectIssue> objectErrors,
        int suppressedFieldCount
    ) {
    }
}
~~~

### 9.6. Analysis of key design decisions

1. **`@InitBinder("booking")`** limits scope to the `booking` model attribute. `setAllowedFields(...)` enforces an allowlist on property binding, mitigating mass assignment risk; a dedicated DTO remains the primary line of defense.
2. **`binder.addValidators(...)`** adds the Spring validator checking the two dates while still allowing the default Jakarta validator to run for annotations on the DTO.
3. **`@Valid @ModelAttribute("booking")`** triggers validation. **`BindingResult` placed immediately after the DTO** lets the handler inspect results and build a JSON 400 response directly.
4. **`binding.getFieldErrors()`** is used exclusively to build `fieldErrors`. Each entry has `field`, the original code, and the translated message; rejected values are excluded.
5. **`binding.getGlobalErrors()`** is used exclusively to build `objectErrors`. Global errors are never assigned to a synthetic field.
6. **`getSuppressedFields()`** records blocked keys and is not automatically treated as Bean Validation errors. The controller still returns 400 if the client sends a field outside the allowlist, even when `hasErrors() == false`.
7. **`MessageSource.getMessage(error,locale)`** applies the same localization mechanism to both `FieldError` and `ObjectError`.
8. **`ResponseEntity<?>`** allows the handler to return different success and error records; in production APIs you can standardize on a dedicated response type or `ProblemDetail`.
9. The demo app performs no database writes and does not echo customer data, even in success responses. Errors on fields that may contain sensitive data never expose the raw `BindingResult` object.

**Important:** a Spring `Validator` must actually be invoked; simply creating the `BookingDatesValidator` class is not enough. In the demo, `@InitBinder` attaches it to `WebDataBinder` and `@Valid` triggers validation. If you omit `@Valid`, do not assume the custom validator still runs.

### 9.7. Message bundles and i18n

Create `src/main/resources/messages.properties`:

~~~properties
NotBlank.booking.customer=Customer name is required.
NotBlank.customer=This field is required.
NotBlank=Required text is missing.
NotNull.booking.seats=Number of seats is required.
NotNull.booking.startDate=Start date is required.
NotNull.booking.endDate=End date is required.
NotNull=Required value is missing.
Min.booking.seats=Seats must be at least 1.
Min.seats=Value is below the minimum.
Min=Value is too small.
typeMismatch.booking.seats=Seats must be a whole number.
typeMismatch.booking.startDate=Start date must use yyyy-MM-dd.
typeMismatch.booking.endDate=End date must use yyyy-MM-dd.
typeMismatch=Invalid value format.
booking.range.invalid.booking=End date must be after start date.
booking.range.invalid=Invalid booking date range.
~~~

Create `src/main/resources/messages_vi.properties` (UTF-8):

~~~properties
NotBlank.booking.customer=Vui lòng nhập tên khách.
NotBlank.customer=Trường này bắt buộc.
NotBlank=Không được để trống.
NotNull.booking.seats=Vui lòng nhập số chỗ.
NotNull.booking.startDate=Vui lòng nhập ngày bắt đầu.
NotNull.booking.endDate=Vui lòng nhập ngày kết thúc.
NotNull=Thiếu dữ liệu bắt buộc.
Min.booking.seats=Số chỗ phải ít nhất là 1.
Min.seats=Giá trị nhỏ hơn mức tối thiểu.
Min=Giá trị quá nhỏ.
typeMismatch.booking.seats=Số chỗ phải là số nguyên.
typeMismatch.booking.startDate=Ngày bắt đầu phải theo định dạng yyyy-MM-dd.
typeMismatch.booking.endDate=Ngày kết thúc phải theo định dạng yyyy-MM-dd.
typeMismatch=Giá trị sai định dạng.
booking.range.invalid.booking=Ngày kết thúc phải sau ngày bắt đầu.
booking.range.invalid=Khoảng ngày không hợp lệ.
~~~

Create `src/main/resources/application.properties`:

~~~properties
spring.messages.basename=messages
spring.messages.encoding=UTF-8
spring.messages.fallback-to-system-locale=false
~~~

`messages.properties` is the base bundle; `messages_vi.properties` contains the Vietnamese translations. The `Locale` resolved by Spring MVC from the request (typically `Accept-Language` under default configuration) is passed into the controller.

`DefaultMessageCodesResolver` generates more specific codes first. For example, `Min.booking.seats` precedes `Min.seats` and `Min`; `booking.range.invalid.booking` precedes `booking.range.invalid`. If a specific translation exists, it is selected. For a multilingual application, maintain all important keys across all supported locales.

**Do not confuse:** Jakarta Validation's `@Min(message="...")` and Spring's `MessageSource` are two mechanisms that can work together. Spring's `Min.booking.seats` code lets the application override messages per model/field without hardcoding Vietnamese text into annotations.

### 9.8. Running and calling HTTP endpoints with curl

In the Spring Boot project root with the Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

With the default server port 8080, a valid request:

~~~bash
curl -i -X POST "http://localhost:8080/api/bookings/preview" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "customer=Lan" \
  --data-urlencode "seats=2" \
  --data-urlencode "startDate=2026-12-20" \
  --data-urlencode "endDate=2026-12-22"
~~~

Expected HTTP **200 OK**:

~~~json
{
  "result": "VALID"
}
~~~

A request with **one field error and one object error simultaneously**:

~~~bash
curl -i -X POST "http://localhost:8080/api/bookings/preview" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: vi" \
  --data-urlencode "customer=Lan" \
  --data-urlencode "seats=0" \
  --data-urlencode "startDate=2026-12-20" \
  --data-urlencode "endDate=2026-12-19"
~~~

Expected HTTP **400 Bad Request** with JSON:

~~~json
{
  "type": "https://example.org/problems/invalid-booking",
  "title": "Invalid booking request",
  "status": 400,
  "code": "VALIDATION_FAILED",
  "fieldErrors": [
    {
      "field": "seats",
      "code": "Min",
      "message": "Số chỗ phải ít nhất là 1."
    }
  ],
  "objectErrors": [
    {
      "code": "booking.range.invalid",
      "message": "Ngày kết thúc phải sau ngày bắt đầu."
    }
  ],
  "suppressedFieldCount": 0
}
~~~

Both dates still parse to `LocalDate`, but the `endDate > startDate` relationship is invalid. The Spring validator emits **one object error**; `@Min` on `seats` emits **one field error**. Do not view this as two separate exceptions being thrown: the handler reads the errors already accumulated in `BindingResult`.

If you replace `Accept-Language: vi` with `en`, the corresponding messages become:

~~~text
Seats must be at least 1.
End date must be after start date.
~~~

The codes `Min` and `booking.range.invalid` stay unchanged; only the message text changes.

Request missing only the customer name:

~~~bash
curl -i -X POST "http://localhost:8080/api/bookings/preview" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: vi" \
  --data-urlencode "customer=" \
  --data-urlencode "seats=2" \
  --data-urlencode "startDate=2026-12-20" \
  --data-urlencode "endDate=2026-12-22"
~~~

Expected 400 with `fieldErrors` containing `customer`/`NotBlank`; `objectErrors` is an empty array.

Request with an invalid date format:

~~~bash
curl -i -X POST "http://localhost:8080/api/bookings/preview" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Accept-Language: vi" \
  --data-urlencode "customer=Lan" \
  --data-urlencode "seats=2" \
  --data-urlencode "startDate=20/12/2026" \
  --data-urlencode "endDate=2026-12-22"
~~~

Expected HTTP 400 due to a conversion failure on `startDate`. The error code is typically `typeMismatch` and the message is resolved from `typeMismatch.booking.startDate`. Do not expect the date-range validator to emit an additional global error, because the validator code returns early when either date lacks a valid value.

Request attempting to pass a field outside the allowlist:

~~~bash
curl -i -X POST "http://localhost:8080/api/bookings/preview" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "customer=Lan" \
  --data-urlencode "seats=2" \
  --data-urlencode "startDate=2026-12-20" \
  --data-urlencode "endDate=2026-12-22" \
  --data-urlencode "admin=true"
~~~

Expected HTTP 400, `fieldErrors=[]`, `objectErrors=[]`, and `suppressedFieldCount=1`. This is a **binding policy rejection**, not an automatic `FieldError` with code `NotBlank` or an `ObjectError`.

## 10. MockMvc testing: keeping both error types truly separate

With `spring-boot-starter-test`, create `src/test/java/com/example/bookingerrors/BookingControllerTest.java`:

~~~java
package com.example.bookingerrors;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class BookingControllerTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void validRequestIsAccepted() throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("customer", "Lan")
                .param("seats", "2")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-22"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.result").value("VALID"));
    }

    @Test
    void fieldErrorAndObjectErrorStaySeparate()
            throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                .param("customer", "Lan")
                .param("seats", "0")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-19"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.status").value(400))
            .andExpect(jsonPath("$.fieldErrors.length()")
                .value(1))
            .andExpect(jsonPath("$.fieldErrors[0].field")
                .value("seats"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                .value("Min"))
            .andExpect(jsonPath("$.fieldErrors[0].message")
                .value("Số chỗ phải ít nhất là 1."))
            .andExpect(jsonPath("$.objectErrors.length()")
                .value(1))
            .andExpect(jsonPath("$.objectErrors[0].code")
                .value("booking.range.invalid"))
            .andExpect(jsonPath("$.objectErrors[0].message")
                .value("Ngày kết thúc phải sau ngày bắt đầu."));
    }

    @Test
    void onlyFieldErrorHasNoGlobalError() throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "vi")
                .param("customer", "")
                .param("seats", "2")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-22"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors.length()")
                .value(1))
            .andExpect(jsonPath("$.fieldErrors[0].field")
                .value("customer"))
            .andExpect(jsonPath("$.fieldErrors[0].code")
                .value("NotBlank"))
            .andExpect(jsonPath("$.objectErrors").isEmpty());
    }

    @Test
    void onlyGlobalErrorHasNoFieldError()
            throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .header(HttpHeaders.ACCEPT_LANGUAGE, "en")
                .param("customer", "Lan")
                .param("seats", "2")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-20"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors").isEmpty())
            .andExpect(jsonPath("$.objectErrors.length()")
                .value(1))
            .andExpect(jsonPath("$.objectErrors[0].message")
                .value("End date must be after start date."));
    }

    @Test
    void invalidDateIsFieldBindingError()
            throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("customer", "Lan")
                .param("seats", "2")
                .param("startDate", "not-a-date")
                .param("endDate", "2026-12-22"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors").isNotEmpty());
    }

    @Test
    void unapprovedInputIsNotSilentlyAccepted()
            throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("customer", "Lan")
                .param("seats", "2")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-22")
                .param("admin", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors").isEmpty())
            .andExpect(jsonPath("$.objectErrors").isEmpty())
            .andExpect(jsonPath("$.suppressedFieldCount")
                .value(1));
    }

    @Test
    void twoFieldErrorsAndOneObjectError()
            throws Exception {
        mvc.perform(post("/api/bookings/preview")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("customer", "")
                .param("seats", "0")
                .param("startDate", "2026-12-20")
                .param("endDate", "2026-12-19"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.fieldErrors.length()")
                .value(2))
            .andExpect(jsonPath("$.objectErrors.length()")
                .value(1));
    }
}
~~~

Run:

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

With Spring Boot 3.5, Spring MVC, the validation provider, and the bundles presented above, **all seven tests are expected to PASS**. They verify the HTTP status, JSON structure, translations, and specifically that **`fieldErrors`** and **`objectErrors`** are not merged into one.

Tests with a single error of a kind can check index `[0]` reliably. The test with two field errors checks only the **length** to avoid assuming any ordering of constraint violations across fields. In projects with Spring Security/CSRF or custom advice/filters, corresponding test configuration must be added.

**Do not just call `new BookingController(...).preview(...)` directly**: doing so bypasses `WebDataBinder`, conversion, `@Valid`, `@InitBinder`, locale resolution, and Spring MVC's `BindingResult` creation.

## 11. What if the endpoint receives JSON `@RequestBody`?

REST APIs typically use JSON instead of URL-encoded forms. With:

~~~java
@PostMapping("/bookings")
public ResponseEntity<?> create(
        @Valid @RequestBody BookingRequest request) {
    // ...
}
~~~

if there is no `BindingResult` immediately after the DTO, Spring MVC typically throws **`MethodArgumentNotValidException`** when an object argument is invalid. This exception lets you read `ex.getBindingResult().getFieldErrors()` and `getGlobalErrors()` just like in the form example.

If you need consistent responses across multiple controllers, you can extend `ResponseEntityExceptionHandler` in a `@RestControllerAdvice` and override:

~~~java
@Override
protected ResponseEntity<Object> handleMethodArgumentNotValid(
        MethodArgumentNotValidException ex,
        HttpHeaders headers,
        HttpStatusCode status,
        WebRequest request) {

    BindingResult result = ex.getBindingResult();

    // Iterate over result.getFieldErrors()
    // and result.getGlobalErrors()
    // to build the error response according to the application's contract.

    return handleExceptionInternal(
        ex,
        ex.getBody(),
        headers,
        status,
        request);
}
~~~

This is an **illustrative snippet** for a `ResponseEntityExceptionHandler` subclass with appropriate Spring imports, **not** part of the runnable project above. `ex.getBody()` is the default `ProblemDetail`; to include field/object issue arrays in the response, build or add the corresponding properties before calling `handleExceptionInternal(...)`.

**Avoid registering a duplicate `@ExceptionHandler(MethodArgumentNotValidException.class)` in the same `ResponseEntityExceptionHandler` subclass** if the base class already maps that exception type. Override the protected handler method properly to avoid ambiguous handler mappings.

### When direct method validation is present

If a handler has constraints placed **directly** on `@RequestParam`/`@PathVariable` or on the return value, Spring MVC 6.1+ may throw **`HandlerMethodValidationException`**. The results of this exception are grouped by **method parameters**, not always a single form's `BindingResult`. Handle the relevant `ParameterValidationResult` and `ParameterErrors` rather than forcing all errors into `ex.getBindingResult()`.

An error on a **return value** can carry HTTP 500, whereas input errors carry HTTP 400. Do not use a catch-all advice that turns both into 400.

### If using Spring WebFlux

WebFlux `@Valid @RequestBody Mono<Dto>` typically raises `WebExchangeBindException` in the reactive flow. It differs from `MethodArgumentNotValidException` on Servlet MVC. While the same `fieldErrors`/`objectErrors` JSON shape can be used at the API boundary, how you extract error details, the exception type, and when it is handled must match the web stack.

## 12. UI rendering of field errors and object errors

The frontend can process the response as follows (pseudocode):

~~~javascript
const fieldMessages = new Map();

for (const issue of response.fieldErrors ?? []) {
  const messages = fieldMessages.get(issue.field) ?? [];
  messages.push(issue.message);
  fieldMessages.set(issue.field, messages);
}

const formBannerMessages =
  (response.objectErrors ?? []).map(issue => issue.message);
~~~

This is frontend pseudocode, not a Spring API. The idea:

- Attach messages from `fieldErrors` to the corresponding input or input group.
- Display `objectErrors` at the top of the form, in a toast, or in a banner because no single field fully describes the error.
- Keep **multiple errors on the same field** instead of using a `field -> single string` map that overwrites earlier errors.
- If a field path is `participants[0].email`, the UI should map the server field name to the actual form field name; do not assume an index remains valid after the user adds or removes rows.
- Do not show raw `code` values instead of `message` to end users; codes are for the machine contract.

If the UI wants a date-range error to appear right next to the pair of date inputs, it can read the global error code `booking.range.invalid` and render it inside the **form group**, without requiring the backend to emit two duplicate field errors.

### Accessibility design

Field-level errors should be linked to their inputs via `aria-describedby` or an equivalent mechanism, and general messages should be announced by screen readers when submission fails. Do not rely on red color alone to indicate errors. An error summary list at the top of the page can link users directly to the corresponding fields.

Global errors such as "End date must be after start date" should state **what needs to be fixed**, not just "Form is invalid".

## 13. Nested fields, collections, and multiple object errors

A form with collections:

~~~text
travellers[0].email
travellers[1].passportNumber
contact.address.postalCode
~~~

can produce `FieldError.getField()` as a **property path**, including indices. Public APIs must decide whether to expose these paths verbatim or map them to another naming convention, such as JSON Pointer or documented field names.

**With nested lists**, a single field can produce multiple errors if it violates multiple constraints; `getFieldErrorCount()` counts **error entries**, not unique field paths. Do not flatten `List<FieldIssue>` into `Map<String,String>` and drop subsequent errors.

**With object-level nested beans**, a class-level constraint on a child object may be represented as an object/global error or a path related to the nested bean depending on how the Spring adapter represents the violation. If the frontend needs the exact location in the form tree, inspect the actual property path from `BindingResult`/validator rather than assuming every `ObjectError` is always at the root.

For large APIs, you can normalize a `path` property to a standard like JSON Pointer, but this requires clear mapping rules and integration tests. Avoid coupling clients directly to internal Java property names when domain DTOs might be refactored.

## 14. Multiple errors on the same field: choosing how to display them

A single field can carry `@NotBlank`, `@Size(min=8)`, and `@Pattern(...)`. On an empty input, the provider may produce multiple different constraint violations. Presentation options:

1. **Return the full list**: the frontend chooses to show all or a subset.
2. **Prioritize one error** in an application-defined order: for example, required first, format second.
3. **Group by field and rule**: preserve rich enough data for the UI to handle.

Do not rely on **violation iteration order** to pick the primary error. If prioritization is needed, map codes to explicit ranks and unit-test the selection logic. For a field that is simultaneously missing and invalid in format, you can configure validation groups/sequences or have the validator skip empty input to reduce overlapping messages.

A `FieldError` can have a list of fallback message codes from `DefaultMessageCodesResolver`; those are **multiple candidate codes for one error**, not **multiple `FieldError` entries**. Distinguish the two axes:

- **Number of `FieldError` entries**: how many times a constraint or binding rule reported an error.
- **Number of message codes per `FieldError`**: how many keys `MessageSource` can try for **the same error**.

## 15. Policy errors, security, and rejected fields

`DataBinder.setAllowedFields(...)` restricts writable properties during form binding. If a client sends a key outside the allowlist, `BindingResult.getSuppressedFields()` can include that key. **However, a suppressed field does not automatically appear in `getFieldErrors()` or `getGlobalErrors()`.**

Therefore, the critical check is:

~~~java
int suppressed = binding.getSuppressedFields().length;

if (binding.hasErrors() || suppressed > 0) {
    // Return an appropriate error response.
}
~~~

If you only check `hasErrors()`, the endpoint may accidentally accept requests containing blocked keys. If business policy requires rejecting rather than ignoring them, checking suppressed fields is essential.

Do not return the full names of rejected keys or values to the client if they might contain sensitive data, overly long inputs, or strings capable of log injection. The demo returns only the **count**, illustrating the mechanism without leaking input.

**More importantly:** design dedicated DTOs that omit `admin`/`ownerId`/`price` fields clients should not modify; enforce authorization in the service layer; do not rely on an allowlist alone to solve every business security risk.

## 16. Why should you not serialize `BindingResult` directly?

`BindingResult` is **Spring internal state**, not a public API schema. Some of its contents may include:

- The target object and binding state.
- Rejected values, which may be passwords, tokens, financial numbers, or personal information.
- Java types/property paths and internal message arguments.
- Details tied to specific Spring/validator versions.
- Multiple fallback codes that are not part of a public machine-readable contract.

Returning `BindingResult` directly can cause Jackson to serialize deeply, leak unnecessary information, or hit undesirable object cycles. Always **manually map to a safe error DTO**, including only defined attributes.

You can write a converter:

~~~java
List<FieldIssue> mapFields(
        BindingResult result, Locale locale) {
    return result.getFieldErrors().stream()
        .map(e -> new FieldIssue(
            e.getField(),
            e.getCode(),
            messageSource.getMessage(e, locale)))
        .toList();
}
~~~

This is an illustrative snippet assuming `FieldIssue` and `messageSource` are in scope. Whether you build the response in the controller or a global advice depends on project scale, but the **mapping logic should be consistent** so every endpoint separates field and object errors in the same way.

## 17. When do you need a shared `@RestControllerAdvice`?

For a simple form, `BindingResult` right after `@ModelAttribute` lets you re-render the view or return a response directly in the handler. For multiple REST controllers using `@RequestBody`, creating a global error mapper for consistency is usually better.

A possible architecture is:

~~~text
Validation failure
    |
    +-- @ModelAttribute + BindingResult
    |       |
    |       +-- shared ErrorResponseMapper
    |
    +-- @RequestBody + MethodArgumentNotValidException
    |       |
    |       +-- @RestControllerAdvice
    |               |
    |               +-- shared ErrorResponseMapper
    |
    +-- handler method constraints
    |       |
    |       +-- HandlerMethodValidationException mapper
    |               |
    |               +-- parameter-group aware conversion
    |
    +-- service/domain exception
            |
            +-- domain-specific HTTP response/status
~~~

The error-mapping logic from `BindingResult` can be reused, but **do not force** every exception into a structure assuming they all carry a `BindingResult`. When method validation occurs at the method level, errors may reside in `ParameterValidationResult`/`ParameterErrors`. Service/domain errors require their own codes and statuses.

### `MessageSource`/`ProblemDetail` in `ControllerAdvice`

`ResponseEntityExceptionHandler` supports extension points for `ErrorResponse`/`ProblemDetail`, and Spring provides i18n support for `type`, `title`, and `detail` fields. When switching the response to `ProblemDetail`, you can add:

~~~java
problem.setProperty("fieldErrors", fieldIssues);
problem.setProperty("objectErrors", objectIssues);
~~~

Here `problem` is an initialized `ProblemDetail` and the issue lists are already mapped. Spring's Jackson module typically unwraps properties at the top level of the JSON. This is an additional snippet; you do not need a full global advice infrastructure in the demo program just to demonstrate field/object errors.

## 18. Stability of the error contract

A solid error contract controls:

- **HTTP status**: accurately reflects client vs. server errors.
- **API codes**: stable and documented.
- **Field paths**: clear conventions for nested fields and array indices.
- **Global/object issues**: never disguised as fake fields.
- **Ordering**: do not depend on provider-dependent ordering; sort explicitly if needed.
- **Localization**: stable codes, localized messages, or codes returned so the frontend translates per product policy.
- **Security**: never expose rejected values, internal class names, or stack traces.
- **Traceability**: appropriate correlation/request id if provided; never write sensitive tokens into logs.
- **Extensibility**: allow multiple errors per field and multiple object errors.
- **Consistency**: validation, JSON decoding, type conversion, and domain policies produce appropriate responses without conflating them.

### HTTP 400 or 422?

Both **400 Bad Request** and **422 Unprocessable Content** appear in different API designs. Spring MVC validation failures commonly default to HTTP 400, though an organization may choose 422 for semantic validation in its published contract. What matters is being **consistent, documented, and tested**, rather than assuming Spring turns every `@Valid` violation into 422.

### Do not wrap 404, 403, or 500 errors as "validation"

Missing resources, insufficient permissions, timeouts, or server bugs are distinct from field/object errors. If a service throws an exception because a booking was not found, do not attach a fake `FieldError` just to reuse the error response. You can share a top-level Problem Details structure, while giving each category its proper `type`/`code`/`status`.

## 19. Common implementation mistakes

| Symptom | Cause | Fix |
|---|---|---|
| Out-of-order date error appears under both fields | Validator calls `rejectValue` repeatedly per field | Use `reject(...)` when the error concerns the relationship between two dates |
| `getAllErrors()` produces two mixed lists | `FieldError` extends `ObjectError` | Use `getFieldErrors()` and `getGlobalErrors()` separately |
| Global error has no field path | By design, it belongs to the whole object | Display in a form banner/group; do not invent a fake field |
| `@NotBlank` present but no error reported | Missing validation provider or `@Valid`, validator not executed | Check starter/annotations/`BindingResult` |
| Custom Spring `Validator` does not run | Not registered via `@InitBinder`/global validator | Use `addValidators(...)` and test with `MockMvc` |
| Cross-field validator emits an error when one date has the wrong type | Validator does not skip null/invalid input | Check values first and let `typeMismatch` handle it |
| JSON message shows English despite `Accept-Language: vi` | `MessageSource` not called or bundle missing | Use `getMessage(error,locale)` and create `vi`/`en` bundles |
| `getDefaultMessage()` is not localized as expected | Default message is not Spring code-based localization | Resolve `MessageSourceResolvable` via `MessageSource` |
| One field has two violations but UI shows only one | `field -> String` map overwrites entries | Use an array/list of messages per field |
| Tests fail when `fieldErrors` order changes | Depending on provider ordering | Assert by `field`/`code` or sort deterministically in mapper |
| Type mismatch wrongly reports `Min` | Mixing pre- and post-conversion errors | Distinguish `typeMismatch` binding errors |
| `BindingResult` does not receive errors in handler | Wrong parameter position or different method validation path | Place immediately after the validated argument |
| Invalid `@RequestBody` JSON prevents controller from running | Argument validation throws exception before handler | Use `@RestControllerAdvice`/appropriate handler |
| Advice always returns HTTP 400 for all method validations | Ignoring return-value violation status 500 | Respect `getStatusCode()` |
| Unknown field does not create a `FieldError` | It was suppressed by allowed-fields policy | Check `getSuppressedFields()` |
| API returns rejected password | Serializing `FieldError`/`BindingResult` directly | Map to a safe DTO, stripping rejected values |
| Frontend does not know where to show object-level errors | Contract lacks a global issues list | Separate `objectErrors[]`/form-level banner |
| Using MVC examples in WebFlux | Different exception/argument resolvers | Confirm the web stack before implementing |

### Quick debugging checklist

1. Is the controller using `@ModelAttribute`, `@RequestBody`, or direct method constraints?
2. Did the input decode/bind to the expected type, or is it a `typeMismatch`?
3. Which validator emitted the error? `@NotBlank`/`@Min` or Spring `Validator.reject(...)`?
4. Is `BindingResult` in the right position and is validation enabled?
5. What do `getFieldErrors()` and `getGlobalErrors()` actually contain?
6. Does `getSuppressedFields()` contain any blocked names?
7. Which locale and message codes is `MessageSource` using?
8. Does the mapper leak rejected values or mix the two error types?
9. Do MockMvc/HTTP tests verify status, shape, and i18n?
10. Are service errors returning the wrong code/status due to a catch-all handler?

## 20. Self-check exercises

**Question 1.** `seats=0` violates `@Min(1)`. Should this be a field error or an object error?

A field error on `seats`, because the user can fix that exact field.

**Question 2.** `startDate=2026-12-20`, `endDate=2026-12-19`, both are valid dates. Where does the error belong?

An object-level/global error on `booking`, because the relationship between the two fields is invalid.

**Question 3.** How do `errors.reject("booking.range.invalid")` and `errors.rejectValue("endDate","booking.range.invalid")` differ?

`reject` creates a global error, whereas `rejectValue` creates a field error. Choose between them based on UI/domain semantics.

**Question 4.** Why should `getAllErrors()` not be used to build `objectErrors` on its own?

Because it also includes `FieldError` instances, causing field errors to be mixed into global errors.

**Question 5.** A field fails two constraints; can there be two `FieldError` instances?

Yes. Do not collapse them into a map that keeps only one message.

**Question 6.** Should `FieldError.getRejectedValue()` be returned to the client?

Not by default. The data may be sensitive; expose only curated fields/codes/messages.

**Question 7.** If a client sends `admin=true` and the binder blocks it via `allowedFields`, is `hasErrors()` guaranteed to be true?

No. You must check `getSuppressedFields()` separately when policy requires rejecting the input.

**Question 8.** Do two requests with the same `Min` violation but different locales need different technical codes?

No. Codes can stay the same; `MessageSource` returns the message appropriate for the locale.

**Question 9.** A handler with `@Valid @RequestBody` has no `BindingResult` right after it and receives an invalid DTO; will the controller method always run?

No. Spring MVC can throw `MethodArgumentNotValidException` before invoking the method.

**Question 10.** Why is `MockMvc` better than calling `validator.validate` directly to test the whole flow?

`MockMvc` exercises Spring MVC binding, conversion, `@InitBinder`, Bean Validation, locale resolution, and response rendering. Calling the validator directly tests only one component.

## 21. Error response design checklist

- [ ] Distinguish field errors and object/global errors right from the data model.
- [ ] Use `getFieldErrors()` and `getGlobalErrors()` separately; do not classify by guessing from message text.
- [ ] Place `BindingResult` immediately after the validated argument when the handler wants to process it inline.
- [ ] Use `errors.rejectValue(...)` for single-field errors; `errors.reject(...)` for whole-object invariants.
- [ ] Have cross-field validators skip missing/unparseable inputs to avoid duplicate messages.
- [ ] Clearly define HTTP status, type/code, field path, message, and i18n policy.
- [ ] Allow multiple errors on the same field; do not rely on unguaranteed ordering.
- [ ] Include explicit `fieldErrors[]` and `objectErrors[]` arrays, even when empty.
- [ ] Check `getSuppressedFields()` when using allowed fields.
- [ ] Never serialize `BindingResult`/`FieldError` and rejected values directly to the client.
- [ ] Use `MessageSource` for Vietnamese/English and test fallback message codes.
- [ ] When using JSON `@RequestBody`, handle `MethodArgumentNotValidException` in the proper scope.
- [ ] When using method validation, handle `HandlerMethodValidationException` with appropriate statuses.
- [ ] When RFC 9457 is needed, consider `ProblemDetail` rather than merely mimicking field names.
- [ ] Write `MockMvc` tests for success, field-only, object-only, mixed, type mismatch, locale, and suppressed fields.
- [ ] Keep business authorization and server errors separate from input validation errors.

**Remember:** **`FieldError` answers "which field is invalid?"**, while **`ObjectError` answers "where is the object or cross-field relationship invalid?"**. A `BindingResult` can contain both. When building REST error responses, separate them into two clear lists, localize messages with `MessageSource`, never leak rejected values, and return consistent HTTP statuses and error codes.

## Official references

- [Spring Framework — Validation Using Spring's Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html)
- [Spring Framework — Resolving Error Codes to Error Messages](https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html)
- [Spring Framework — BindingResult API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework — Errors API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/Errors.html)
- [Spring Framework — FieldError API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework — ObjectError API](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/ObjectError.html)
- [Spring Framework — MVC @ModelAttribute and BindingResult](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Error Responses and Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Boot 3.5 — Internationalization](https://docs.spring.io/spring-boot/3.5/reference/features/internationalization.html)
