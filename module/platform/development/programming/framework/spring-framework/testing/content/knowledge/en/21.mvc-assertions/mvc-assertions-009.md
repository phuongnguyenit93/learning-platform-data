# BindingResult, Validation Errors, and Field Names

When Spring MVC receives data from a form or request body, the framework must convert the incoming input into a Java object and validate that object's constraints. When errors occur, `BindingResult` holds the details so the controller or error-handling layer can return an appropriate response. In MVC testing, you must assert that errors attach to the right object, the right field, and the right error type; checking only the HTTP status is usually not enough.

`BindingResult` is an interface in `org.springframework.validation` that extends `Errors`. It contains errors produced during data binding and object validation. An error can be associated with a specific field (`FieldError`) or with the whole object (`ObjectError`). Distinguishing these two helps applications display errors next to the right inputs or return form-wide business errors.

## Binding and Validation Flow in Spring MVC

For a controller parameter bound from a request, Spring typically executes these steps:

1. Read input from query parameters, form fields, path variables, or the request body depending on annotations.
2. Convert input values to Java types and bind them onto the target object.
3. If the parameter is annotated with `@Valid` or `@Validated`, run validation.
4. Create or populate `BindingResult` to store binding and validation errors.
5. If the controller declares `BindingResult` or `Errors` immediately after the bound parameter, Spring delegates error handling to the controller. Otherwise, certain validation failures are thrown as exceptions such as `MethodArgumentNotValidException`.

For example, a form submitting `age=abc` for an `Integer` property creates a conversion/binding error. Submitting `age=-2` binds successfully as an integer but violates `@Min(0)`. The two errors have different origins, even though both can appear in `BindingResult`.

| Error Kind | Example | Typical Details |
|---|---|---|
| Binding/conversion error | `age=abc` when field is `Integer` | `FieldError` with `isBindingFailure() == true` |
| Field validation error | `age=-2` violating `@Min(0)` | `FieldError` with `isBindingFailure() == false` |
| Object/global validation error | `startDate` and `endDate` do not form a valid date range | `ObjectError`, not tied to a single field |

## Position of BindingResult in the Controller Signature

`BindingResult` or `Errors` must immediately follow the parameter receiving the errors. Spring uses this adjacent position to determine which bound/validated object the errors belong to.

```java
@PostMapping("/registrations")
String register(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        BindingResult bindingResult) {

    if (bindingResult.hasErrors()) {
        return "registration/form";
    }

    registrationService.register(form);
    return "redirect:/registrations/success";
}
```

In this example, `BindingResult` immediately follows `RegistrationForm`. If another parameter is placed in between, such as:

```java
String register(
        @Valid @ModelAttribute("registration") RegistrationForm form,
        Locale locale,
        BindingResult bindingResult) {
    // ...
}
```

Spring no longer treats that `BindingResult` as the result for `form`; requests can fail with parameter-handling errors instead of letting the controller inspect errors as intended. Always place `BindingResult` immediately after the bound and validated object.

`@Valid` instructs Spring to run Bean Validation on the object. If you omit `@Valid`/`@Validated`, constraints like `@NotBlank` or `@Email` do not run automatically just because the controller declares `BindingResult`. Conversion errors during data binding can still occur, however.

## FieldError and ObjectError

`BindingResult` distinguishes field-level errors from object-level errors:

- `FieldError` describes an error on a property. It carries `field`, `rejectedValue`, `bindingFailure`, and message codes.
- `ObjectError` describes an error on the object as a whole, such as a rule comparing multiple properties. `FieldError` is a specialized subtype of `ObjectError`.

Commonly used methods:

| Method | Meaning |
|---|---|
| `hasErrors()` | Whether there is at least one error |
| `hasFieldErrors()` | Whether there is an error on any field |
| `hasFieldErrors("email")` | Whether the specified field has errors |
| `getFieldError("email")` | Returns the first error for that field or `null` |
| `getFieldErrors("email")` | Returns the list of errors for that field |
| `getGlobalErrors()` | Returns errors not attached to a specific field |
| `getAllErrors()` | Returns all errors, including field and object errors |
| `getFieldValue("email")` | Gets the current/rejected value of the field in the binding result |
| `rejectValue("email", "email.invalid")` | Adds an error to a field using a message code |
| `reject("registration.date.range")` | Adds an object-level error using a message code |

Example reading errors inside a controller:

```java
if (bindingResult.hasFieldErrors("email")) {
    FieldError error = bindingResult.getFieldError("email");
    String rejectedValue = String.valueOf(error.getRejectedValue());
    // Can log or build a response according to application policy.
}

if (!bindingResult.getGlobalErrors().isEmpty()) {
    // Display errors applying to the entire form.
}
```

Do not return `rejectedValue` to clients by default. A rejected value may contain sensitive data or unsafe strings for rendering. Include it in responses only when permitted by the API contract and properly sanitized/masked.

## Producing Field Errors and Global Errors via Validation

Standard Bean Validation constraints produce field errors. Example:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class RegistrationForm {

    @NotBlank(message = "{registration.name.required}")
    private String name;

    @NotBlank(message = "{registration.email.required}")
    @Email(message = "{registration.email.invalid}")
    private String email;

    @Min(value = 0, message = "{registration.age.positive}")
    private Integer age;

    // Constructors, getters, and setters.
}
```

To check relationships across multiple fields, use a class-level constraint. For example, `startDate` must precede `endDate`:

```java
@ValidDateRange
public class BookingForm {

    private LocalDate startDate;
    private LocalDate endDate;

    // Getters and setters.
}
```

The validator for `@ValidDateRange` can report an object-level violation via `ConstraintValidatorContext`, or target a property node if the application wants the error attached to a specific field. When a class-level constraint reports a standard violation, Spring places it in the global errors list of `BindingResult`.

In the controller, you can add business errors after annotation validation runs:

```java
if (bookingService.isUnavailable(form.getStartDate(), form.getEndDate())) {
    bindingResult.reject(
            "booking.period.unavailable",
            "The selected period is unavailable");
}
```

`reject(...)` creates an object error; `rejectValue(...)` creates a field error. Use stable message codes so UIs or APIs can localize messages via `MessageSource`.

## Testing BindingResult with Forms and ModelAttribute

With `@ModelAttribute`, Spring binds request parameters onto the object. When the controller returns a view, `BindingResult` is added to the model alongside the target object. Model attribute names and binding result keys follow a clear convention: for an attribute named `registration`, the binding result is stored under the key prefixed with `org.springframework.validation.BindingResult.registration`.

MockMvc can assert errors by attribute name and field name:

```java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.model;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.view;

@WebMvcTest(RegistrationController.class)
class RegistrationControllerTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void returnsFormWithFieldErrorsWhenEmailIsInvalid() throws Exception {
        mockMvc.perform(post("/registrations")
                        .param("name", "Mai")
                        .param("email", "not-an-email")
                        .param("age", "20"))
                .andExpect(status().isOk())
                .andExpect(view().name("registration/form"))
                .andExpect(model().attributeHasFieldErrors(
                        "registration", "email"));
    }
}
```

`model().attributeHasFieldErrors("registration", "email")` checks that the model attribute named `registration` has errors attached to the `email` field. This matcher verifies the binding/validation outcome returned by the controller rather than checking whether HTML happens to contain text resembling an error message.

Related matchers include:

```java
andExpect(model().attributeHasErrors("registration"));
andExpect(model().attributeHasFieldErrors("registration", "email"));
andExpect(model().attributeHasNoErrors("registration"));
andExpect(model().attributeHasFieldErrorCode(
        "registration", "email", "Email"));
```

The attribute name passed to the matcher must match the name declared by the controller in `@ModelAttribute`. If `@ModelAttribute("form")` is used, assert against `"form"`; do not assume the class name or Java parameter name is used.

You can also inspect error values and types by retrieving `BindingResult` from the model:

```java
import org.springframework.validation.BindingResult;
import org.springframework.validation.FieldError;

MvcResult result = mockMvc.perform(post("/registrations")
                .param("name", "Mai")
                .param("email", "not-an-email")
                .param("age", "20"))
        .andExpect(status().isOk())
        .andReturn();

BindingResult errors = (BindingResult) result.getModelAndView()
        .getModel()
        .get(BindingResult.MODEL_KEY_PREFIX + "registration");

FieldError emailError = errors.getFieldError("email");
assertThat(emailError).isNotNull();
assertThat(emailError.getField()).isEqualTo("email");
assertThat(emailError.isBindingFailure()).isFalse();
```

The snippet above requires importing `MvcResult` and AssertJ. `getModelAndView()` applies when the controller returns a view; for REST controllers returning a response body, there is no `ModelAndView` to inspect this way.

## Distinguishing Binding Errors from Validation Errors

Tests should cover both scenarios to avoid confusion:

**Unconvertible value:** `age=abc` cannot be converted to `Integer`. Spring creates a `FieldError` for `age` and marks it as a binding failure.

```java
mockMvc.perform(post("/registrations")
                .param("name", "Mai")
                .param("email", "mai@example.test")
                .param("age", "abc"))
        .andExpect(status().isOk())
        .andExpect(model().attributeHasFieldErrors(
                "registration", "age"));
```

**Convertible value that violates a constraint:** `age=-1` is a valid integer type-wise, but violates `@Min(0)`.

```java
MvcResult result = mockMvc.perform(post("/registrations")
                .param("name", "Mai")
                .param("email", "mai@example.test")
                .param("age", "-1"))
        .andExpect(status().isOk())
        .andExpect(model().attributeHasFieldErrors(
                "registration", "age"))
        .andReturn();

BindingResult errors = (BindingResult) result.getModelAndView()
        .getModel()
        .get(BindingResult.MODEL_KEY_PREFIX + "registration");

assertThat(errors.getFieldError("age").isBindingFailure()).isFalse();
```

In real tests, ensure the controller has `@Valid` so constraints execute and `BindingResult` is in the proper position. Both scenarios may re-render the form, but the messages and user remediation differ.

## Testing BindingResult with JSON Request Bodies

With `@RequestBody`, Spring uses `HttpMessageConverter` to read JSON into an object. You can place `BindingResult` right after a `@Valid @RequestBody` parameter so the controller handles validation errors itself:

```java
@RestController
@RequestMapping("/api/registrations")
class RegistrationApiController {

    @PostMapping
    ResponseEntity<?> create(
            @Valid @RequestBody RegistrationRequest request,
            BindingResult bindingResult) {

        if (bindingResult.hasErrors()) {
            List<ApiFieldError> errors = bindingResult.getFieldErrors()
                    .stream()
                    .map(error -> new ApiFieldError(
                            error.getField(), error.getCode(),
                            error.getDefaultMessage()))
                    .toList();
            return ResponseEntity.badRequest()
                    .body(new ValidationErrorResponse(errors));
        }

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(registrationService.create(request));
    }
}

record ApiFieldError(String field, String code, String message) {}
record ValidationErrorResponse(List<ApiFieldError> errors) {}
```

MockMvc verifies the status and field name in the JSON response:

```java
mockMvc.perform(post("/api/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "name": "Mai",
                          "email": "invalid",
                          "age": 20
                        }
                        """))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.errors[0].field").value("email"));
```

Error ordering in the list should not be treated as a stable contract unless the application explicitly sorts errors. When multiple field errors are possible, assert presence by content or field using appropriate matchers, or sort the list in the response before asserting order.

### When JSON Cannot Be Deserialized

Not every request-body error enters `BindingResult`. If JSON has syntax errors, missing braces, or cannot be deserialized into Java types, `HttpMessageConverter` fails before a complete object is passed to the controller. Spring typically throws `HttpMessageNotReadableException`; the controller is not invoked, and an adjacent `BindingResult` cannot catch parse failures.

```java
mockMvc.perform(post("/api/registrations")
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"name\": "))
        .andExpect(status().isBadRequest());
```

Handle parse/deserialization errors in `@RestControllerAdvice` or an appropriate exception-handling mechanism. Do not write tests expecting the controller to read `BindingResult` when the request body could not even be converted into an object.

## Asserting Field Names and Nested Properties

The field name in `FieldError` is the property path Spring uses during binding and validation. For nested objects, the field name may include dots; for collection elements, it may contain indices or map keys.

Example DTO:

```java
class OrderForm {
    @Valid
    private CustomerForm customer;

    @Valid
    private List<OrderLineForm> lines;

    // Getters and setters.
}

class CustomerForm {
    @NotBlank
    private String email;
    // Getters and setters.
}

class OrderLineForm {
    @Min(1)
    private Integer quantity;
    // Getters and setters.
}
```

If the customer's email is blank, the error typically has field path `customer.email`. If the quantity of the second line is invalid, the field path may be `lines[1].quantity`.

```java
andExpect(model().attributeHasFieldErrors(
        "orderForm", "customer.email"));
```

For collections, use indices matching the test input sent. If the public API exposes field names under a different convention, such as `lines[1].quantity` or `lines.1.quantity`, define that convention clearly in the application's error-mapping layer and assert the exact response contract.

Field names in errors are an important part of the UI and API contract. If a DTO renames a property or uses `@JsonProperty` to change the external JSON name, the field path in `BindingResult` may differ from the external JSON key name. Do not assume the two names are always identical; verify the application's actual output.

## Message Codes and Error Messages

`FieldError` and `ObjectError` hold message codes, arguments, and default messages. `MessageSource` can resolve message codes for the current locale to produce localized messages. When a test only cares about validation logic, assert the field and error code rather than coupling to full translated sentences:

```java
andExpect(model().attributeHasFieldErrorCode(
        "registration", "email", "Email"));
```

When testing the presentation contract, assert the final message via `content().string(...)`, `jsonPath(...)`, or the corresponding model attribute. For multiple locales, pass the locale via MockMvc and verify the localized content.

Spring normally generates a list of message codes ordered from most specific to most general. For example, an email error can have codes based on object name, field, and error type before falling back to a generic code. Therefore, when a test needs to verify exact codes, use `attributeHasFieldErrorCode` with a code configured in the application, or inspect `FieldError#getCodes()` to assert the codes relevant to the test's objective.

## Object-Level Errors in MockMvc

Form-wide errors are not attached to a specific field. For views, you can verify that `BindingResult` has no field errors yet has global errors by reading the binding result from the model:

```java
MvcResult result = mockMvc.perform(post("/bookings")
                .param("startDate", "2030-06-10")
                .param("endDate", "2030-06-01"))
        .andExpect(status().isOk())
        .andExpect(view().name("booking/form"))
        .andReturn();

BindingResult errors = (BindingResult) result.getModelAndView()
        .getModel()
        .get(BindingResult.MODEL_KEY_PREFIX + "booking");

assertThat(errors.hasErrors()).isTrue();
assertThat(errors.getFieldErrors()).isEmpty();
assertThat(errors.getGlobalErrors()).isNotEmpty();
```

This test assumes `BookingForm` has a class-level validator and the controller names the model attribute `booking`. If the validator intentionally attaches the error to `endDate`, that error becomes a `FieldError`, and the assertions should match the validator's design.

For JSON APIs, map global errors to response entries with a clear identifier, such as `field: null` or `scope: "object"`. Do not arbitrarily assign form-wide errors to the first field merely for display convenience.

## Matchers and Inspection APIs to Remember

| Goal | How to Check |
|---|---|
| Model attribute has errors | `model().attributeHasErrors("registration")` |
| A field has errors | `model().attributeHasFieldErrors("registration", "email")` |
| A field has a specific error code | `model().attributeHasFieldErrorCode("registration", "email", "Email")` |
| Attribute has no errors | `model().attributeHasNoErrors("registration")` |
| Assert JSON response has a field error | `jsonPath("$.errors[0].field").value("email")` |
| Read all errors in controller/test | `BindingResult#getAllErrors()` |
| Read errors only for a field | `BindingResult#getFieldErrors("email")` |
| Distinguish binding vs. validation errors | `FieldError#isBindingFailure()` |

When deeper inspection is needed, retrieve `MvcResult` via `.andReturn()` and read the model or response body. For view-returning controllers, use `getModelAndView()`; for REST controllers, read `getResponse().getContentAsString()` or use JSONPath matchers directly.

## Common Mistakes When Writing Tests

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Controller does not receive `BindingResult` | `BindingResult` does not immediately follow the bound/validated object | Place `BindingResult` or `Errors` immediately after that parameter |
| No validation errors despite invalid constraints | Missing `@Valid`/`@Validated` or missing validation provider | Check annotations and Bean Validation dependencies |
| Matcher cannot find the model attribute | Name passed to matcher differs from `@ModelAttribute` | Use the exact attribute name declared in the controller |
| Field error has an unexpected name | DTO uses nested properties, collection indices, or JSON aliases | Check `FieldError#getField()` and the application's field-naming convention |
| Value `abc` fails before validation | Data type conversion error | Check `FieldError#isBindingFailure()` and type-mismatch messages |
| Malformed JSON never enters the controller | Message converter failed to deserialize the request body | Handle `HttpMessageNotReadableException` in an exception handler |
| Test depends on field error ordering | Error order can vary by validator or object structure | Assert by field/code, or intentionally sort the response |
| Global error mistaken for a field error | Validator attached the wrong property node or test only reads `getFieldErrors()` | Also check `getGlobalErrors()` and constraint design |

A meaningful MVC test verifies the HTTP status, where errors are stored, and the exact field names clients or views need to know. By properly checking `BindingResult`, `FieldError`, `ObjectError`, and message codes, tests can catch defects from data conversion, validation annotations, and business rules through to how the controller reports errors to users.
