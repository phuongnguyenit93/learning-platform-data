# Distinguishing Single-Field Errors from Object-Wide Errors in Spring Validator

## 1. Two Error Types Answer Two Different Questions

In a Spring application, when validating a form or a business object, not every error belongs to an individual property. For example, a user books a room with fields `guestName`, `checkIn`, and `checkOut`:

- `guestName` contains only whitespace: the error belongs directly to the `guestName` field.
- `checkOut` is not after `checkIn`: the **combined data of the whole booking** is invalid; an object-wide error can be recorded to show a general message.
- If `checkIn` is missing: the error can be attached to `checkIn`, even though the system needs this date to evaluate the cross-date rule.

Spring Validation represents this distinction with two primary kinds:

| | Single-field error (*field error*) | Object-wide error (*global/object error*) |
| --- | --- | --- |
| Question | Which field of the object is invalid? | Which overall rule of the object was not satisfied? |
| Recording API | `Errors.rejectValue(field, code, ...)` | `Errors.reject(code, ...)` |
| Result object | `FieldError` | `ObjectError` |
| Has property name? | Yes: `getField()` | No specific field; only `getObjectName()` |
| Result collection | `getFieldErrors()` | `getGlobalErrors()` |
| Examples | Empty guest name, negative quantity, wrong type for date field | Invalid date range, allocations not summing to 100%, conflicting multi-field state |
| Typical presentation | Next to the corresponding input | At the top of the form or in a general errors section |

Both kinds are **validation errors in the `org.springframework.validation.Errors` model**, typically collected into `BindingResult`. Do not interpret an "object-wide error" as an exception that crashes the application. It is a structured error returned so the application can decide how to display or handle it.

**Pragmatic rule:** record a field error if the user can clearly identify a single input to fix; record a global error when responsibility cannot or should not be pinned on one specific input. A rule depending on multiple fields **does not have** to record a global error: how errors are attached is a validator design decision.

## 2. Interfaces and Classes Used by Spring

Spring provides the object validation contract:

```java
public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
```

This is an abbreviated outline of `org.springframework.validation.Validator`, used solely for explanation. Inside `validate`, the validator inspects `target` and calls one of two approaches:

```java
errors.rejectValue("guestName", "guest.required");
errors.reject("booking.invalidDates");
```

- `rejectValue("guestName", "guest.required")` registers a `FieldError` whose field is `guestName`. The `guest.required` code is used by Spring to look up a message from `MessageSource`.
- `reject("booking.invalidDates")` registers an `ObjectError` for the object being validated, not tied to a specific field.
- Overloads accept `errorArgs` and `defaultMessage` to supply parameters and a fallback message, such as `reject("booking.invalidDates", "Check-out date must be after check-in date")`.
- `ValidationUtils.rejectIfEmptyOrWhitespace(errors, "guestName", "guest.required")` is a Spring utility that adds a field error when the value is null, empty, or whitespace-only.

When using `DataBinder` or Spring MVC, the result is typically a `BindingResult`. Key methods to remember:

```text
errors.hasErrors()
errors.getErrorCount()
errors.getAllErrors()         -> List<ObjectError>, including FieldErrors
errors.hasFieldErrors()
errors.getFieldErrors()       -> List<FieldError>
errors.getFieldErrors("guestName")
errors.getFieldError("guestName")
errors.getFieldErrorCount()
errors.hasGlobalErrors()
errors.getGlobalErrors()      -> List<ObjectError>, object-wide errors only
errors.getGlobalError()
errors.getGlobalErrorCount()
```

`FieldError` **extends** `ObjectError`, so `getAllErrors()` can hold both types. However, `getGlobalErrors()` filters down to object-wide errors only; do not treat every `ObjectError` in `getAllErrors()` as a global error. If you want to render them separately, retrieve `getFieldErrors()` and `getGlobalErrors()`.

Error elements share common properties:

- `getObjectName()`: the object name assigned by Spring during binding, such as `booking`; **not** necessarily the Java class name.
- `getCode()`: the primary error code passed by the validator, e.g., `guest.required`.
- `getCodes()`: prioritized candidate codes used for message resolution, which may include variants with object/field/type.
- `getArguments()`, `getDefaultMessage()`: arguments and fallback message, depending on how the error was registered.
- Specifically `FieldError.getField()`: the relevant property path.
- Specifically `FieldError.getRejectedValue()`: the rejected value if Spring retained it.
- Specifically `FieldError.isBindingFailure()`: indicates whether the error occurred during binding (such as a type conversion failure); an error recorded via `rejectValue` in a normal validator is not a binding failure.

Do not assume `getDefaultMessage()` always has content: if only an error code was passed to `reject`/`rejectValue`, `MessageSource` may be needed to produce a user-friendly message.

## 3. Single-Field Error: When One Property Has a Problem

Consider a registration form requiring a guest name:

```java
@Override
public void validate(Object target, Errors errors) {
    ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "guestName", "guest.required"
    );
}
```

When `guestName` is `"   "`, the helper registers a field error. From `BindingResult result`, we can read:

```java
FieldError error = result.getFieldError("guestName");
if (error != null) {
    System.out.println(error.getField());
    System.out.println(error.getCode());
}
```

Assuming `org.springframework.validation.FieldError` is imported and validation ran on a suitable target, the two printed lines are:

```text
guestName
guest.required
```

Notable characteristics of field errors:

1. **Precise association with an input**: the UI can display the error right beside `guestName` and highlight that field.
2. **Multiple errors can exist on the same field**: `@NotBlank` and `@Size` or custom validators can produce multiple messages. `getFieldError("guestName")` returns only the first; `getFieldErrors("guestName")` returns the list.
3. **Supports nested paths**: e.g., `address.street`. When using `Errors.pushNestedPath(...)`, Spring computes the current path automatically; validators must use the actual property names.
4. **Not solely from constraints**: value conversion failures during binding, such as entering `"abc"` into a numeric field, are also commonly represented as a `FieldError` with a code like `typeMismatch`.
5. **Rejected values should not always be exposed**: the value may be sensitive (passwords, tokens, personal data). Avoid logging or returning `getRejectedValue()` verbatim.

Field errors from **binding/conversion** and field errors from **validation** share the same result type but have different origins. `isBindingFailure()` helps tell them apart, especially when designing API error responses.

## 4. Object-Wide Error: When an Overall Rule Is Violated

Consider a booking form where both individual dates are valid dates, yet `checkOut` is before or equal to `checkIn`. The problem lies in the **relationship between values**:

```java
Booking booking = (Booking) target;
if (booking.getCheckIn() != null
        && booking.getCheckOut() != null
        && !booking.getCheckOut().isAfter(booking.getCheckIn())) {
    errors.reject(
        "booking.invalidDates",
        "Check-out date must be after check-in date"
    );
}
```

`reject(...)` requires no field name. `BindingResult.getGlobalErrors()` will contain an `ObjectError` whose `getObjectName()` matches the bound object; the error code is `booking.invalidDates`.

Situations where a global error is commonly appropriate:

- A booking whose `checkIn` and `checkOut` do not form a valid time range.
- A form requiring at least one of several contact methods to be provided.
- A money transfer whose source, destination, and limit form an invalid combination.
- A configuration whose individual options are valid but conflict when enabled together.
- An order whose line-item percentage allocations do not sum to 100%.

Distinguish **global validation errors** from **application exceptions**. A global error is validation data; the controller can re-render the form with a message and let the user correct it. There is no need to throw an exception just to represent an ordinary validation error.

### Multi-Field Rules Can Still Be Attached to a Single Field

If the UI expects the user to primarily adjust `checkOut`, you can deliberately choose a field error:

```java
errors.rejectValue(
    "checkOut",
    "booking.invalidDates",
    "Check-out date must be after check-in date"
);
```

This **is still a two-field rule**, but recorded as a `FieldError` on `checkOut`. Therefore, you cannot determine error kind merely by counting how many fields a rule inspects. Consider where the UI guides the user to fix the input and how the API/frontend consumes errors.

## 5. Complete Java 17 Example: Producing Both FieldError and ObjectError

The example below uses **Spring Framework `Validator` and `DataBinder`**, without needing a Spring Boot web server or Jakarta Validation provider. Java 17+ and Maven are enough. This shows that both error kinds are part of Spring's own validation model.

Structure:

```text
spring-error-kinds/
├── pom.xml
└── src/main/java/demo/FieldVsGlobalErrorDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>spring-error-kinds</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.14</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/FieldVsGlobalErrorDemo.java`:

```java
package demo;

import java.time.LocalDate;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class FieldVsGlobalErrorDemo {

    public static final class Booking {
        private final String guestName;
        private final LocalDate checkIn;
        private final LocalDate checkOut;

        public Booking(String guestName, LocalDate checkIn,
                       LocalDate checkOut) {
            this.guestName = guestName;
            this.checkIn = checkIn;
            this.checkOut = checkOut;
        }

        public String getGuestName() {
            return guestName;
        }

        public LocalDate getCheckIn() {
            return checkIn;
        }

        public LocalDate getCheckOut() {
            return checkOut;
        }
    }

    public static final class BookingValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Booking.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Booking booking = (Booking) target;

            // Single invalid field -> FieldError.
            ValidationUtils.rejectIfEmptyOrWhitespace(
                errors, "guestName", "guest.required"
            );

            // When a date is missing, report on that specific field for the user to fix.
            if (booking.getCheckIn() == null) {
                errors.rejectValue("checkIn", "checkIn.required");
            }
            if (booking.getCheckOut() == null) {
                errors.rejectValue("checkOut", "checkOut.required");
            }

            // Invalid relationship between two fields -> ObjectError.
            // Compare only when both dates are present.
            if (booking.getCheckIn() != null
                    && booking.getCheckOut() != null
                    && !booking.getCheckOut()
                        .isAfter(booking.getCheckIn())) {
                errors.reject(
                    "booking.invalidDates",
                    "Check-out date must be after check-in date"
                );
            }
        }
    }

    private static void show(String label, Booking booking) {
        DataBinder binder = new DataBinder(booking, "booking");
        binder.addValidators(new BookingValidator());
        binder.validate();

        BindingResult result = binder.getBindingResult();

        System.out.println(label);
        for (FieldError error : result.getFieldErrors()) {
            System.out.println("FIELD " + error.getField()
                    + " -> " + error.getCode());
        }
        for (ObjectError error : result.getGlobalErrors()) {
            System.out.println("GLOBAL " + error.getObjectName()
                    + " -> " + error.getCode());
        }
        System.out.println("counts: field="
                + result.getFieldErrorCount()
                + ", global=" + result.getGlobalErrorCount()
                + ", all=" + result.getErrorCount());
    }

    public static void main(String[] args) {
        show("Invalid", new Booking(
            "   ",
            LocalDate.of(2026, 11, 15),
            LocalDate.of(2026, 11, 14)
        ));

        show("Valid", new Booking(
            "Lan",
            LocalDate.of(2026, 11, 14),
            LocalDate.of(2026, 11, 15)
        ));
    }
}
```

From the `spring-error-kinds` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.FieldVsGlobalErrorDemo
```

Lines printed by the program (excluding library logging messages, if any):

```text
Invalid
FIELD guestName -> guest.required
GLOBAL booking -> booking.invalidDates
counts: field=1, global=1, all=2
Valid
counts: field=0, global=0, all=0
```

Step-by-step walkthrough:

1. `DataBinder` wraps the `Booking` object and names the object `booking`. This is the name returned by `ObjectError.getObjectName()`.
2. `binder.addValidators(new BookingValidator())` registers the validator whose `supports(Booking.class)` returns `true`.
3. `binder.validate()` instructs Spring to run the validator; the error collector is passed to `validate`.
4. `guestName` is whitespace-only, so `rejectIfEmptyOrWhitespace` creates a `FieldError`. The error appears via `getFieldErrors()` with field `guestName`.
5. `checkOut` is before `checkIn`, so `reject` creates an object-wide `ObjectError`, returned via `getGlobalErrors()`.
6. `getErrorCount()` is the sum of both kinds: `1 + 1 = 2`. When the booking is valid, all lists are empty.

This example **constructs Java objects and calls validation directly**; it does not perform web binding from an HTTP request. When an actual request flows through Spring MVC, the system may record additional field errors during the binding/conversion phase before validator rules are evaluated.

### Trying a Different Error Attachment

Change only the call:

```java
errors.reject(
    "booking.invalidDates",
    "Check-out date must be after check-in date"
);
```

to:

```java
errors.rejectValue(
    "checkOut", "booking.invalidDates",
    "Check-out date must be after check-in date"
);
```

The program will now report **two field errors** (on `guestName` and `checkOut`) and **no global errors** in the `Invalid` case. The rule code stays identical; the result classification changes solely because of the recording API chosen. This is the simplest way to observe the nature of the two error kinds.

## 6. Checking Results Without Confusing the Two Error Types

Suppose `result` is of type `BindingResult`:

```java
boolean anyError = result.hasErrors();
boolean fieldError = result.hasFieldErrors();
boolean globalError = result.hasGlobalErrors();

int total = result.getErrorCount();
int fieldCount = result.getFieldErrorCount();
int globalCount = result.getGlobalErrorCount();
```

These APIs let you build error-handling logic without parsing `BindingResult.toString()`.

Example of splitting errors into two presentation groups:

```java
for (FieldError field : result.getFieldErrors()) {
    String property = field.getField();
    String code = field.getCode();
    // Route message to the corresponding input.
}

for (ObjectError global : result.getGlobalErrors()) {
    String code = global.getCode();
    // Route message to the form's general error area.
}
```

These are illustrative snippets placed inside a method that already has `result`; they are not a standalone runnable program.

If you only use:

```java
for (ObjectError error : result.getAllErrors()) {
    System.out.println(error.getCode());
}
```

you get **all errors**, but lose the grouping distinction unless you check `error instanceof FieldError`. You cannot call `getField()` directly on a variable typed as `ObjectError`. In practice, `getFieldErrors()` and `getGlobalErrors()` are clearer.

### FieldError Is Not Always From a Custom Validator

In Spring MVC, when a user types `"abc"` into an `Integer` field `age`, the system can create a `FieldError` with `isBindingFailure() == true` during data conversion. An error from `@Min(18)` or `errors.rejectValue("age", ...)` happens once the numeric value has been created and validated; typically `isBindingFailure() == false`.

Therefore, when displaying errors, rely on the API and error codes to produce suitable messages; do not assume **every** `FieldError` came from `Validator.validate`.

## 7. Error Codes, Messages, and How Spring Resolves Them

An error has an **error code** and optionally a **default message**. Avoid hardcoding full sentences everywhere a validator is called if the application needs multi-language support; prefer stable error codes and externalized messages.

Example validator snippet:

```java
errors.rejectValue(
    "guestName", "guest.required",
    "Guest name must not be blank"
);
errors.reject(
    "booking.invalidDates",
    "Check-out date must be after check-in date"
);
```

Spring provides `MessageCodesResolver` to generate code variants. With object name `booking` and field `guestName`, the default resolver can try keys in decreasing specificity, for example:

```properties
guest.required.booking.guestName=Guest name must not be empty
guest.required.guestName=Please enter guest name
guest.required=This field is required

booking.invalidDates.booking=Check-out date must be after check-in date
booking.invalidDates=Invalid date range
```

The lines above are example `messages.properties` entries in a Spring application with a configured `MessageSource`. Spring selects messages through the message-code system; actual key formats and order depend on the resolver and context. Do not depend on a specific string without checking the active configuration.

Key difference:

- Field errors can generate codes containing **object name + field name + field type**, enabling input-specific messages.
- Global errors typically involve **object name + rule code**, because there is no specific field.
- `error.getCode()` returns the primary code; `error.getCodes()` returns the resolved candidate array. They serve different purposes.
- `error.getDefaultMessage()` is the fallback message; the UI should consider `MessageSource`/`BindingResult` for locale support instead of displaying raw error codes.

If a REST API returns validation details, a clean structure can be used:

```json
{
  "fieldErrors": [
    {"field": "guestName", "code": "guest.required"}
  ],
  "globalErrors": [
    {"code": "booking.invalidDates"}
  ]
}
```

This is a **custom-designed API format**, not a default JSON response emitted automatically by every Spring application. The backend can include localized messages and a request correlation ID; avoid exposing sensitive rejected values directly.

## 8. Integrating with Spring MVC

In Spring MVC, `WebDataBinder` builds upon the binding and validation mechanism. A custom validator can be added with `@InitBinder`; in the handler method, `BindingResult` is placed **immediately after** the validated argument so the controller can handle errors inline.

The following code skeleton **only illustrates the controller**, assuming the application already defines a JavaBean `BookingForm` with getters/setters and `BookingFormValidator` implementing Spring `Validator` for `BookingForm`:

```java
import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.validation.BindingResult;
import org.springframework.validation.annotation.Validated;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;

@Controller
class BookingController {

    @InitBinder("bookingForm")
    void initBinder(WebDataBinder binder) {
        binder.addValidators(new BookingFormValidator());
    }

    @PostMapping("/bookings")
    String submit(
            @Validated @ModelAttribute("bookingForm") BookingForm form,
            BindingResult errors,
            Model model) {

        if (errors.hasErrors()) {
            model.addAttribute("fieldErrors", errors.getFieldErrors());
            model.addAttribute("globalErrors", errors.getGlobalErrors());
            return "booking-form";
        }

        // Persist the booking according to application business logic.
        return "booking-success";
    }
}
```

Notes for the controller example:

- `BookingForm` and `BookingFormValidator` must be defined in the application; this snippet does not replace the standalone program in section 5.
- `@Validated` requests validation at this entry point; validators registered via `@InitBinder` participate when the binder performs validation.
- The name in `@InitBinder("bookingForm")` must match the target model attribute name; `supports` must match the received object type.
- Place `BindingResult` immediately after `@ModelAttribute`. Misplacing it prevents Spring from binding the result as expected, and validation errors may flow through an exception path instead.
- The `booking-form` view decides how to render them. Display field errors next to the corresponding fields, and global errors in a general alert area.

If the controller uses Jakarta Validation (`@Valid`, `@NotBlank`, custom class-level constraints), Spring can translate `ConstraintViolation` instances into errors in `BindingResult` via the `LocalValidatorFactoryBean` adapter. Usually property-level violations become field errors and object-level violations without a property path become global errors. However, **the violation's property path determines the mapping**: a custom class-level constraint can produce a violation attached to a field by building a property node.

Therefore, do not confuse:

- `org.springframework.validation.FieldError`/`ObjectError`: **Spring's error reporting model**.
- `jakarta.validation.ConstraintViolation`: **Jakarta Validation's result model**.
- An adapter can bridge the two models, but they are not the same classes.

## 9. Choosing Field Error vs. Global Error in Tricky Cases

### Case A: Malformed Email Address

The rule only reads `email` and has a matching input. Record `rejectValue("email", "email.invalid")` so the user fixes that exact input.

### Case B: End Date Must Follow Start Date

The rule reads `startDate` and `endDate`. If the form is designed for the user to adjust the end date, attaching to `endDate` via `rejectValue` can be intuitive. If the rule describes an overall period, recording `reject("dateRange.invalid")` is also reasonable. No framework rule forces every cross-field validation to be global.

### Case C: At Least One of Two Contact Channels Is Required

If both `phone` and `email` are empty, a global error clearly expresses "provide at least one contact method". If the UI wants to highlight both fields, you can record two field errors, though you should avoid misleading users into thinking both fields are mandatory.

### Case D: Coupon Code Invalid for the Whole Order

If the failure stems from order status, total amount, and coupon policy, a global error can make sense. If the user only needs to change the code in the `couponCode` input, a field error can also be helpful. How you guide the user to fix the issue is the deciding factor.

### Case E: System Failure or Unavailable Database

This is usually an **application/infrastructure failure**, not a user-input validation error. Do not force it into `errors.reject("system.failure")` merely to reuse `BindingResult`; use proper exception handling and error responses instead.

A short checklist when choosing:

1. Can you identify **one field that the user should edit**?
2. Does the error describe **invalidity of the entire object or a combination of properties**?
3. Where will the UI and API present the error so the user understands it clearly?
4. Is the error code stable and clear enough to localize and test?
5. Is there any risk of leaking sensitive data via `rejectedValue` or error messages?

## 10. Common Mistakes

1. **Calling `reject(...)` when you want to highlight an input.** The error is recorded as global, with no `getField()` to point to the input.
2. **Calling `rejectValue(...)` with the wrong field name.** The path must match a property Spring can access; a mismatch can cause property access errors or misplaced errors.
3. **Assuming object-level rules must create global errors.** Multi-field rules can be attached to a field if that helps the user fix the right place.
4. **Calling only `getFieldErrors()` and concluding the form is valid.** Global errors may still exist; use `hasErrors()` to check overall validity.
5. **Iterating `getAllErrors()` and casting every element to `FieldError`.** The list also contains genuine `ObjectError` instances; unchecked casts can throw `ClassCastException`.
6. **Assuming `getObjectName()` is the offending property name.** The object name identifies the binding target (e.g., `booking`), not `guestName`.
7. **Mixing up binding errors and validation errors.** A `typeMismatch` error can be created prior to validation; `FieldError.isBindingFailure()` provides useful distinction.
8. **Placing `BindingResult` in the wrong parameter position.** Spring MVC requires the result to follow the corresponding bound/validated argument if handled inline.
9. **Rendering only field errors and ignoring global errors.** Overall rules can be hidden from the user.
10. **Exposing raw error codes or rejected values to the client.** Use `MessageSource` to translate messages; avoid logging or returning sensitive data in APIs.

## 11. Self-Check

1. What error kind does `errors.rejectValue("quantity", "quantity.invalid")` create? Which API retrieves that list?
2. How does `errors.reject("order.totalMismatch")` differ? What does `getObjectName()` mean?
3. Why can `getAllErrors()` return `FieldError` instances even though its declared element type is `ObjectError`?
4. When `startDate` and `endDate` are out of order, when does it make sense to attach the error to `endDate` instead of creating a global error?
5. When a user enters letters into a numeric field, what kind of error does Spring typically record, and how does `isBindingFailure()` help?
6. If `getFieldErrorCount() == 0` but `getGlobalErrorCount() == 1`, what will `hasErrors()` return?
7. In Spring MVC, where must `BindingResult` be placed to handle errors for an `@ModelAttribute` inside the controller?

**Conclusion:** Field errors pinpoint an invalid *property* and are typically created with `rejectValue(...)`; global errors express an invalid *object or overall rule* and are created with `reject(...)`. Both reside in `BindingResult`. When processing and rendering, always inspect both groups and choose error placement based on what the user needs to fix.

## References

- Spring Framework — Validation, Data Binding, and Type Conversion: https://docs.spring.io/spring-framework/reference/core/validation.html
- Spring Framework — Resolving Error Codes to Error Messages: https://docs.spring.io/spring-framework/reference/core/validation/error-code-resolution.html
- Spring Framework 6.1 — `Errors` interface: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/Errors.html
- Spring Framework — `FieldError` and `ObjectError`: https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/FieldError.html and https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/validation/ObjectError.html
