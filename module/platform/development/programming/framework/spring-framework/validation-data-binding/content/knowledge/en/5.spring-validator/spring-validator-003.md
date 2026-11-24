# Spring Validator: `validate()` and Recording Errors into `Errors`

In Spring Framework, an object can **receive type-valid data yet still violate business rules**: a name containing only whitespace, a quantity exceeding a limit, or an end date before a start date. `org.springframework.validation.Validator` lets you place those rules in a dedicated component. The `validate(Object target, Errors errors)` method **does not return a list of errors**; it receives an `Errors` collector and **records discovered errors into it**. Afterward, the controller, `DataBinder`, or service inspects those errors to decide how to proceed.

This article focuses on implementing `validate()`, choosing `rejectValue()` or `reject()`, inspecting errors, and integrating with Spring MVC.

## 1. The `Validator` Contract

Core interface:

~~~java
package org.springframework.validation;

public interface Validator {
    boolean supports(Class<?> clazz);
    void validate(Object target, Errors errors);
}
~~~

- `supports(Class<?> clazz)` indicates whether the validator **supports the requested object type**. The common implementation is `MyForm.class.isAssignableFrom(clazz)` if subclasses are also accepted, or `equals` if only one exact class should match.
- `validate(Object target, Errors errors)` inspects `target`, then calls methods on `errors` to **register each violation**. The return type is `void`; error data lives in the `Errors` instance supplied by the caller.
- Validators should treat ordinary input errors as **validation results**, not throw exceptions for every data violation. Exceptions are better suited for API misuse or abnormal system states.
- `validate()` is not invoked by default merely because you declare a class that implements `Validator`. You must invoke it directly or register the validator with `DataBinder`/Spring MVC so it executes in the corresponding flow.

Flow diagram:

~~~text
Request data / Java object
                 |
        [binding, if any]
                 |
          target created
                 |
        Validator.validate(target, errors)
                 |
       +---------+----------+
       |                    |
  Condition passes     Condition fails
  No error recorded    errors.rejectValue(...)
                       errors.reject(...)
       |                    |
       +----------+---------+
                  |
      Errors / BindingResult
                  |
        hasErrors(), getFieldErrors(),
        getGlobalErrors(), getAllErrors()
                  |
     Render form / return HTTP 400 / proceed
~~~

`Errors` is the **interface for reporting and reading errors**. `BindingResult` **extends `Errors`**, adding binding-related details (such as model name, binding values, field and model info). Thus, a `BindingResult` can be passed to the `Errors` parameter of `validate()`. Recording errors through `Errors` does not depend on whether the controller renders HTML or returns JSON.

## 2. Recording Field Errors with `rejectValue()`

When a violation is tied to **a specific property**, call:

~~~java
errors.rejectValue("customerName", "booking.customerName.required");

errors.rejectValue(
        "seats",
        "booking.seats.range",
        new Object[] {1, 8},
        "Number of seats must be from 1 to 8.");
~~~

Meaning of the arguments:

| Argument | Meaning |
| --- | --- |
| `field` | Property name **on the object being validated**, such as `"customerName"` or `"seats"`; supports nested paths when the model fits |
| `errorCode` | Logical error code such as `booking.seats.range`; used to classify and resolve messages |
| `errorArgs` | Arguments that can be interpolated into a resource bundle message, e.g., min=1, max=8 |
| `defaultMessage` | Fallback message if no translation is found for the error code |

`rejectValue()` creates a `FieldError` and appends it to the error list. It **does not exit `validate()` early**, **does not return HTTP 400 itself**, and **does not modify the field value**. To record multiple violations, continue checking and call further error-registration methods.

`errorCode` is an application-defined code. Spring can expand the code into more specific candidates based on object name, field, and type via `MessageCodesResolver`. For an object named `bookingForm`, an error `booking.seats.range` on field `seats` can be looked up under specific keys like `booking.seats.range.bookingForm.seats`, followed by broader keys. You do not need to pre-concatenate all key segments into the code passed to `rejectValue()`.

To check whether a field has errors:

~~~java
if (errors.hasFieldErrors("seats")) {
    // At least one error related to seats is present.
}
~~~

A single field can have **multiple errors**. `getFieldError("seats")` retrieves only one error, whereas `getFieldErrors("seats")` retrieves the full list. When returning errors to the user, decide explicitly whether to return all errors or a prioritized one; avoid accidentally dropping other errors.

## 3. Recording Object-Level Errors with `reject()`

Some conditions involve **multiple fields together**, so no single field is solely responsible. For example, the departure date must be on or after the arrival date:

~~~java
if (arrivalDate != null && departureDate != null
        && departureDate.isBefore(arrivalDate)) {
    errors.reject(
            "booking.dates.order",
            "Departure date must not be before arrival date.");
}
~~~

`reject(errorCode, defaultMessage)` registers an **`ObjectError`** at the object level. This error appears in `errors.getGlobalErrors()`, whereas single-field errors appear in `errors.getFieldErrors()`. `errors.getAllErrors()` includes both kinds.

Choose where to report the error based on how the user needs to correct the data:

- Empty customer name → field `customerName` → `rejectValue("customerName", ...)`.
- Seats outside range 1–8 → field `seats` → `rejectValue("seats", ...)`.
- Conflicting date pair → object `bookingForm` → `reject(...)`; if the UI design prefers attaching it explicitly to the departure date field, you may choose `rejectValue("departureDate", ...)` instead of a global error.

Do not attach every rule to an arbitrary field just for rendering convenience. Proper categorization helps the client display errors next to the right input or at the top of the form.

## 4. Using `ValidationUtils` for Empty Checks

Spring provides utilities:

~~~java
ValidationUtils.rejectIfEmpty(
        errors, "customerName", "booking.customerName.required");

ValidationUtils.rejectIfEmptyOrWhitespace(
        errors, "customerName", "booking.customerName.required");
~~~

`rejectIfEmpty()` flags `null` or empty string `""`; `rejectIfEmptyOrWhitespace()` also flags whitespace-only strings like `"   "`. Overloads allow supplying `errorArgs` and `defaultMessage` when needed.

The utility reads the field value through `Errors`, so **you do not need to extract the property yourself** to call it. However, it does not replace rules like numeric ranges, cross-date constraints, or complex business checks. For non-string fields, make sure you understand what "empty" means in your data model.

You can also write it directly:

~~~java
if (form.getCustomerName() == null
        || form.getCustomerName().isBlank()) {
    errors.rejectValue("customerName", "booking.customerName.required");
}
~~~

Both approaches are valid; `ValidationUtils` is convenient when checking properties already managed by `Errors`.

## 5. Complete Java 17+ Example: A Validator Recording Three Errors

The example below uses **Spring Framework 6.x** without starting a web server. Place it in `src/main/java/BookingDemo.java` inside a Maven project with the `org.springframework:spring-context` dependency (or a Spring Boot app that already includes `spring-boot-starter-web`). This is **a complete Java file with `main`**, runnable once the classpath includes the corresponding Spring libraries.

~~~java
import java.time.LocalDate;

import org.springframework.validation.BeanPropertyBindingResult;
import org.springframework.validation.BindingResult;
import org.springframework.validation.Errors;
import org.springframework.validation.FieldError;
import org.springframework.validation.ObjectError;
import org.springframework.validation.ValidationUtils;
import org.springframework.validation.Validator;

public class BookingDemo {

    static final class BookingForm {
        private String customerName;
        private Integer seats;
        private LocalDate arrivalDate;
        private LocalDate departureDate;

        public String getCustomerName() {
            return customerName;
        }

        public void setCustomerName(String customerName) {
            this.customerName = customerName;
        }

        public Integer getSeats() {
            return seats;
        }

        public void setSeats(Integer seats) {
            this.seats = seats;
        }

        public LocalDate getArrivalDate() {
            return arrivalDate;
        }

        public void setArrivalDate(LocalDate arrivalDate) {
            this.arrivalDate = arrivalDate;
        }

        public LocalDate getDepartureDate() {
            return departureDate;
        }

        public void setDepartureDate(LocalDate departureDate) {
            this.departureDate = departureDate;
        }
    }

    static final class BookingValidator implements Validator {

        @Override
        public boolean supports(Class<?> clazz) {
            return BookingForm.class.isAssignableFrom(clazz);
        }

        @Override
        public void validate(Object target, Errors errors) {
            BookingForm form = (BookingForm) target;

            ValidationUtils.rejectIfEmptyOrWhitespace(
                    errors, "customerName", "booking.customerName.required");

            Integer seats = form.getSeats();
            if (seats == null) {
                errors.rejectValue(
                        "seats",
                        "booking.seats.required",
                        "Please enter the number of seats.");
            } else if (seats < 1 || seats > 8) {
                errors.rejectValue(
                        "seats",
                        "booking.seats.range",
                        new Object[] {1, 8},
                        "Number of seats must be from 1 to 8.");
            }

            LocalDate arrival = form.getArrivalDate();
            LocalDate departure = form.getDepartureDate();
            if (arrival != null && departure != null
                    && departure.isBefore(arrival)) {
                errors.reject(
                        "booking.dates.order",
                        "Departure date must not be before arrival date.");
            }
        }
    }

    public static void main(String[] args) {
        BookingForm form = new BookingForm();
        form.setCustomerName("   ");
        form.setSeats(0);
        form.setArrivalDate(LocalDate.of(2025, 6, 12));
        form.setDepartureDate(LocalDate.of(2025, 6, 10));

        BindingResult result =
                new BeanPropertyBindingResult(form, "bookingForm");

        Validator validator = new BookingValidator();
        if (!validator.supports(form.getClass())) {
            throw new IllegalArgumentException("Unsupported target type");
        }

        validator.validate(form, result);

        System.out.println("hasErrors=" + result.hasErrors());
        System.out.println("errorCount=" + result.getErrorCount());

        for (FieldError fieldError : result.getFieldErrors()) {
            System.out.println("FIELD " + fieldError.getField()
                    + ": " + fieldError.getCode());
        }
        for (ObjectError objectError : result.getGlobalErrors()) {
            System.out.println("OBJECT " + objectError.getCode());
        }
    }
}
~~~

Exact stdout of the example with compatible Spring Framework 6.x libraries:

~~~text
hasErrors=true
errorCount=3
FIELD customerName: booking.customerName.required
FIELD seats: booking.seats.range
OBJECT booking.dates.order
~~~

Step-by-step explanation:

1. `BeanPropertyBindingResult(form, "bookingForm")` creates an error collector for the form named `bookingForm`. It implements `Errors`, so it can be passed to `validate()`.
2. `"   "` causes `rejectIfEmptyOrWhitespace` to record a `FieldError` for `customerName`.
3. `seats=0` is outside 1–8, so another `FieldError` is recorded for `seats`.
4. `departureDate` is earlier than `arrivalDate`, so an `ObjectError` is recorded via `reject`.
5. `getFieldErrors()` returns two field errors and `getGlobalErrors()` returns one object-wide error; total `getErrorCount()` is 3.

These values are technical codes because the program prints `getCode()`. When paired with `MessageSource`, the same errors can produce Vietnamese or English messages according to locale; translation does not alter how `validate()` records errors.

You can run it inside a Maven application containing Spring as follows (after placing the file at the proper path and adding `spring-context` to dependencies):

~~~bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=BookingDemo
~~~

The command uses installed Maven/Java and requires Spring dependencies on the classpath. This **cannot be run with plain `javac BookingDemo.java`**, because `Errors`, `Validator`, and `BeanPropertyBindingResult` live in the Spring libraries.

## 6. Who Supplies `Errors` When Calling `validate()`?

### 6.1. Calling Directly in a Service or Test

The caller itself can instantiate `BeanPropertyBindingResult` as in the example above and call `validator.validate(form, result)`. This is useful when you need to validate a standalone object without HTTP or a binding step.

Note: if you call `validate()` manually, you are responsible for handling `result.hasErrors()`. Spring **does not automatically turn errors into exceptions or responses** in this manual invocation path.

### 6.2. Through `DataBinder`

`DataBinder` manages binding and maintains an associated `BindingResult`. You register validators and ask the binder to run validation:

~~~java
BookingDemo.BookingForm form = new BookingDemo.BookingForm();
form.setCustomerName("   ");
form.setSeats(0);

DataBinder binder = new DataBinder(form, "bookingForm");
binder.addValidators(new BookingDemo.BookingValidator());
binder.validate();

BindingResult result = binder.getBindingResult();
System.out.println(result.hasErrors()); // true
~~~

This snippet illustrates usage in the **same project** as `BookingDemo`; import `org.springframework.validation.DataBinder` and `org.springframework.validation.BindingResult`. `binder.validate()` invokes registered validators; errors are added to `binder.getBindingResult()`. When property values arrive from a request, the binder can perform binding before validation; conversion errors may also exist in the same `BindingResult`.

You can use `setValidator(...)` to set a single validator, or `addValidators(...)` to add multiple validators. Before registering with a binder, verify `supports(target.getClass())` matches; if the validator does not support the target type, configuration or validation may fail. If the binder already has a validator (such as the Bean Validation checker), consider `addValidators` to keep existing rules.

### 6.3. Through Spring MVC: Controller Receives `BindingResult`

To have Spring MVC use a custom `Validator` for a model attribute, configure it in `@InitBinder` and mark the parameter for validation. The example below is **integration code**: extract `BookingForm` and `BookingValidator` from section 5 into standalone classes in the same package, then use them in the controller.

~~~java
@Controller
class BookingController {

    private final BookingValidator bookingValidator;

    BookingController(BookingValidator bookingValidator) {
        this.bookingValidator = bookingValidator;
    }

    @InitBinder("bookingForm")
    void initBookingBinder(WebDataBinder binder) {
        binder.addValidators(bookingValidator);
    }

    @PostMapping("/bookings")
    String submit(
            @Validated @ModelAttribute("bookingForm") BookingForm form,
            BindingResult errors,
            Model model) {

        if (errors.hasErrors()) {
            model.addAttribute("validationErrors", errors.getAllErrors());
            return "booking-form";
        }

        return "redirect:/bookings/success";
    }
}
~~~

The types and annotations in this integration snippet belong to Spring MVC: `org.springframework.stereotype.Controller`, `org.springframework.web.bind.annotation.InitBinder`, `PostMapping`, `ModelAttribute`, `org.springframework.web.bind.WebDataBinder`, `org.springframework.validation.annotation.Validated`, `BindingResult`, and `org.springframework.ui.Model`. `BookingValidator` must be a Spring bean or be instantiated/registered appropriately for injection.

**Conditions to verify:**

- `@Validated` on the model attribute signals that validation should run after binding; in common cases, Jakarta's `@Valid` also triggers the corresponding validation mechanism. Do not merely declare `@InitBinder` and assume every request will be validated.
- `BindingResult errors` must be placed **immediately after the `BookingForm form` parameter** it serves. Without `BindingResult` in the proper position, Spring MVC's error flow may raise an exception instead of entering the form re-display branch.
- `@InitBinder("bookingForm")` scopes this configuration to the model attribute named `bookingForm`. The name must match `@ModelAttribute("bookingForm")`.
- `BindingResult` can hold both binding/conversion errors and errors recorded by custom validators. The controller should use the combined result.
- When returning a view for a form, the template must display both `getFieldErrors()` and `getGlobalErrors()` appropriately while escaping user-entered content.

If you want to **invoke manually** right inside the handler, you can call `bookingValidator.validate(form, errors)` and then check `errors.hasErrors()`. This gives more explicit control, though you must avoid accidentally running validation twice when automatic validation via `@Validated`/`@Valid` is already enabled.

## 7. Reading Recorded Error Data Accurately

A `FieldError` can provide:

~~~java
FieldError fieldError = result.getFieldError("seats");
if (fieldError != null) {
    String objectName = fieldError.getObjectName(); // "bookingForm"
    String field = fieldError.getField();           // "seats"
    String errorCode = fieldError.getCode();        // "booking.seats.range"
    String[] candidates = fieldError.getCodes();   // resolved codes
    Object rejected = fieldError.getRejectedValue();
    boolean conversionFailed = fieldError.isBindingFailure();
}
~~~

`getCode()` returns the primary error code, while `getCodes()` can contain **multiple candidates** for message lookup. `getRejectedValue()` reflects the value rejected in the binding/validation context, but **should not be logged directly or returned to the client** if it could contain passwords, tokens, or personal information. `isBindingFailure()` helps distinguish errors originating from binding from business validation errors added by `rejectValue()`.

An `ObjectError` has `getObjectName()`, `getCode()`, `getCodes()`, and `getDefaultMessage()`, but has no field or rejected value. Therefore, to produce a uniform response, branch using `instanceof FieldError` rather than forcing all errors into field errors.

Example JSON model that an application might build on its own:

~~~json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {"field": "customerName", "code": "booking.customerName.required"},
    {"field": "seats", "code": "booking.seats.range"},
    {"field": null, "code": "booking.dates.order"}
  ]
}
~~~

This is an **application-defined response shape**, not a JSON structure emitted automatically by `Errors`. Converting `Errors` into an HTTP response is the responsibility of the controller or exception handler.

## 8. Mapping Error Codes to Display Messages

`rejectValue(...)` and `reject(...)` **store an error code and a default message**, rather than producing translated sentences themselves. The presentation layer can pass the `FieldError` or `ObjectError` directly to `MessageSource` to try resolved codes in order:

~~~java
for (ObjectError error : result.getAllErrors()) {
    String userMessage = messageSource.getMessage(error, locale);
    // Use userMessage in the view or response.
}
~~~

This is an integration snippet requiring a `MessageSource` bean, a `Locale` matching the request, and Spring imports. Example resource bundle keys:

~~~properties
booking.customerName.required=Please enter customer name.
booking.seats.required=Please enter the number of seats.
booking.seats.range=Number of seats must be from {0} to {1}.
booking.dates.order=Departure date must not be before arrival date.
~~~

For the `seats` error, arguments `{1, 8}` are passed from `rejectValue` into the message. Do not concatenate messages manually inside the validator; let the resolver and bundle handle translation and fallback selection. When using `MessageFormat`, watch out for placeholder syntax and single-quote escaping rules in messages.

You can use broad keys or object + field keys to tailor wording across screens. Translation results and the `MessageCodesResolver` mechanism do not change the core principle: **the validator only registers errors; the presentation layer chooses the displayed text**.

## 9. Nested Object Errors and Multiple Validators

If an object contains child objects such as `bookingForm.guest.address`, field paths can use dot notation like `"guest.address.city"`, provided the target structure and binding mechanism support it. When delegating to a dedicated validator for a child object, you can use the nested path on `Errors`:

~~~java
try {
    errors.pushNestedPath("guest");
    ValidationUtils.invokeValidator(guestValidator, form.getGuest(), errors);
} finally {
    errors.popNestedPath();
}
~~~

This snippet illustrates usage inside a parent validator, assuming `form.getGuest()` is non-null and `guestValidator.supports(...)` matches. While the nested path is `guest`, a field error `"email"` recorded by the child validator becomes `"guest.email"`. Always restore the path in `finally` so subsequent errors do not receive the wrong prefix. If the child object is `null`, handle the missing-child rule before calling its validator.

**Multiple validators can record into the same `BindingResult`.** Do not clear or recreate the collector inside a validator: doing so can wipe out existing binding errors or errors from another validator. Each validator should only add errors within its own responsibility.

## 10. Common Error Scenarios and Checks

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| `validate()` is never called | Only implements the interface without registering/calling it, or missing validation trigger on controller | Configure `DataBinder`/`@InitBinder` and `@Validated`/`@Valid` in context, or call directly |
| `ClassCastException` at the start of `validate()` | Validator used on a target of the wrong type | Implement `supports()` consistently, use the validator matching the model |
| Exception on `rejectValue("field", ...)` | Field does not exist or nested path is invalid on the object/binder | Check JavaBean properties, actual field names, and nested paths |
| Form has errors but nothing renders | Controller/view reads only one error kind or uses the wrong field name | Check `hasErrors()`, `getFieldErrors()`, and `getGlobalErrors()` |
| Conversion errors mixed with validation | Binder and validator write to the same `BindingResult` | Distinguish using `FieldError.isBindingFailure()` and codes such as `typeMismatch` |
| Same violation appears twice | Custom validator invoked both automatically and manually, or duplicate rules across validators | Trace invocation paths and register each rule only where needed |
| `null` field causes error in condition | Dereferencing before null check | Check required/null first; use separate branches for range comparisons |
| Field error attached to wrong child object | `pushNestedPath` without matching `popNestedPath` | Wrap push/pop pairs in `try/finally` |
| Localized messages fail to display | Missing bundle keys, mismatched object/field names, or missing locale | Inspect `error.getCodes()`, `MessageSource`, and fallback configuration |
| Logs contain sensitive data | Printing full `BindingResult` or `getRejectedValue()` | Log only error codes, non-sensitive fields, and sanitized data |

**Self-test three essential cases:**

1. **Valid input:** `customerName="An"`, `seats=2`, departure date after arrival date → `errors.hasErrors() == false` and `getErrorCount() == 0`.
2. **Multiple field + object errors:** data from `BookingDemo` → exactly 2 `FieldError`s and 1 `ObjectError`, with no exception thrown for business violations.
3. **Conversion error before validation:** submitting `seats=abc` for an `Integer` field → the binder may add `typeMismatch`; custom validators must not assume every field converted successfully. Use the combined `BindingResult` to display accurate error sources.

When writing unit tests with Spring Test or JUnit, you can construct `BeanPropertyBindingResult` directly, invoke `validate`, and assert `hasFieldErrors("seats")`, `getGlobalErrorCount()`, and error codes. Object-level testing catches rule bugs without starting a server.

## 11. Implementation Checklist

- `supports()` accurately identifies target types; `validate()` inspects the object and calls `rejectValue` for fields and `reject` for object-level violations.
- Pass the same `Errors`/`BindingResult` across binding and validation; never discard existing errors.
- Separate missing-value checks, out-of-range checks, cross-field constraints, and type conversion failures; always check for `null` before comparing values.
- Controller proceeds only when `!errors.hasErrors()`; on errors, render or return both field and global errors.
- Keep error codes stable, messages readable, and sensitive data unexposed; test both valid inputs and multiple simultaneous violations.

Official reference documentation: [Validation Using Spring’s Validator Interface](https://docs.spring.io/spring-framework/reference/core/validation/validator.html) and [Java Bean Validation – Configuring a DataBinder](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html).
