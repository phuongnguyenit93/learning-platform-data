# Partially Bound Data When Errors Exist and How to Prevent Downstream Use in Spring MVC

In Spring MVC, **data binding is not an all-or-nothing transaction**. When `WebDataBinder` receives multiple request parameters, some properties may already be assigned onto the JavaBean before another property hits a type conversion or validation error. Consequently, `BindingResult.hasErrors()==true` **does not mean the target object remained untouched**.

Suppose a form submits:

~~~http
POST /api/reservations HTTP/1.1
Content-Type: application/x-www-form-urlencoded

guestName=Lan&seats=abc&contactEmail=lan%40example.org
~~~

With a JavaBean having `String guestName`, `Integer seats`, and `String contactEmail`, the binder can:

- Successfully bind `guestName = "Lan"`.
- Successfully bind `contactEmail = "lan@example.org"`.
- Fail to convert `"abc"` into `Integer seats`, recording a `FieldError` with code `typeMismatch` in `BindingResult`.
- Leave `seats` at its initial value, e.g., `null` on a fresh form.
- Still pass both the JavaBean and `BindingResult` to the handler **if the handler declares `BindingResult` in the right position and errors can be handled locally**.

**The risk:** downstream code sees `guestName` is populated, assumes the form was "processed," and invokes a service, updates an entity, saves to the DB, sends notifications, or charges fees **while data still has errors**. At that moment, part of the input was technically bound even though the overall request **is not business-valid**.

This lesson belongs to the **Diagnostics** section of the **Spring Framework — validation-data-binding** module. Its goal is to understand **partial binding** precisely, distinguish **binding errors** from **validation errors**, never mistake bound data for valid data, and design a "validation gate" that **invokes business logic only after all errors are cleared**.

Examples use **Java 17+, Spring Boot 3.5.x, Spring Framework 6.2.x, Spring MVC Servlet, Jakarta Bean Validation, and JUnit 5/MockMvc**.

## 1. Three States That Must Not Be Equated

In a request handler receiving a JavaBean form, distinguish:

1. **Bound data**: the binder wrote some properties onto the target object; other properties may have failed type conversion.
2. **Validated data**: constraints such as `@NotBlank`, `@Min`, and cross-field rules were evaluated, with all errors stored in `BindingResult` or thrown by the framework.
3. **Accepted for business action**: binding, validation, allowlist, authorization, and relevant business preconditions all passed.

Satisfying (1) **does not guarantee** (2) or (3). Satisfying (2) also **does not replace** authorization, uniqueness checks, transaction integrity, or other domain invariants.

~~~text
HTTP form/query parameters
          |
          v
@ModelAttribute / WebDataBinder
          |
          +-- Property A converts -> setter A runs
          +-- Property B converts -> setter B runs
          +-- Property C fails conversion -> FieldError(typeMismatch)
          +-- Property D disallowed -> suppressed field
          |
          v
Bean Validation @Valid (if triggered)
          |
          +-- FieldError / ObjectError added
          |
          v
BindingResult
          |
          +-- hasErrors() == true? ----- Yes ----> 400 / form view
          |                                     DO NOT call service
          |
          +-- getSuppressedFields() non-empty?
          |                         ----- Yes ----> Reject per policy
          |
          v
Map to immutable command/snapshot
          |
          v
Authorization + domain checks
          |
          v
Service / transaction / repository / notification
~~~

**Critical takeaway:** gating inside the handler before calling a service only prevents **downstream actions from running**. It **does not undo** setters that already executed on the target during binding. Therefore, the binding target must be a **dedicated request DTO**, never a sensitive managed entity or session object with side effects.

## 2. Binding Errors Differ from Validation Errors

| Aspect | Binding error | Validation error |
|---|---|---|
| When it occurs | Reading/assigning input to a property, especially during conversion | After an eligible object/value exists for rule checking |
| Example | `"abc"` → `Integer seats` fails | `seats=0` violates `@Min(1)` |
| Where stored in MVC forms | `BindingResult` | Also `BindingResult` when handled locally |
| Typical error class | `FieldError` | `FieldError` or `ObjectError` |
| Common error code | `typeMismatch` | `NotBlank`, `Min`, custom code |
| `FieldError.isBindingFailure()` | Typically `true` | Typically `false` |
| Target value | Failing field may retain old/null value | Converted to Java type, yet fails rule |
| Rejected value | Usually raw string from request | Usually violating Java value |
| Invoke service? | No, when policy gates it | No, when policy gates it |

Both error sources can appear together in **one request**. One valid field can be bound while another is rejected. Hence `getFieldErrorCount()` counts error entries, not properties left unbound.

### Concrete State Example

Suppose before binding:

~~~text
ReservationForm:
  guestName    = null
  seats        = null
  contactEmail = null
~~~

After binding `guestName=Lan&seats=abc&contactEmail=lan@example.org`:

~~~text
ReservationForm:
  guestName    = "Lan"              <- bound
  seats        = null               <- conversion failed
  contactEmail = "lan@example.org"  <- bound

BindingResult:
  FieldError(
    field = "seats",
    code = "typeMismatch",
    bindingFailure = true,
    rejectedValue = "abc"
  )
~~~

If a developer logs only `form.getGuestName()`, the data appears received. Yet if `errors.hasErrors()` is true, the overall request **must not create a reservation**.

## 3. `DataBinder.bind(...)` Mutates in Place, Not a Transactional Rollback

Spring's `org.springframework.validation.DataBinder` takes a target and binds `PropertyValues`. With **property binding**, properties are assigned as each conversion and property write succeeds. When one part fails, the result contains the successfully bound values **alongside the errors**.

Simple snippet:

~~~java
ReservationForm form = new ReservationForm();

DataBinder binder =
    new DataBinder(form, "reservationForm");

MutablePropertyValues values =
    new MutablePropertyValues();

values.add("guestName", "Lan");
values.add("seats", "abc");
values.add("contactEmail", "lan@example.org");

binder.bind(values);

BindingResult errors = binder.getBindingResult();
~~~

This is a snippet; complete classes appear in the hands-on section. **`binder.bind(...)` does not automatically run Jakarta `@NotBlank`/`@Min`**. When using `DataBinder` manually and wanting a Spring `Validator` to run, you must register the validator and call `binder.validate()`.

Mental model to keep in mind:

~~~text
bind(PropertyValues)
   |
   +-- convert + set each property
   +-- collect binding failures
   |
   v
BindingResult
   |
   +-- getTarget()
   +-- getFieldErrors()
   +-- getSuppressedFields()
   +-- hasErrors()
~~~

### `BindingResult` Is Not a Safe Copy of the Target

`BindingResult.getTarget()` returns the very object the binder mutated. When the target is mutable, reading the target after an error does not imply it is a snapshot of an accepted "transaction command."

To update domain data, construct a **fresh command** only after errors and policies are verified; never pass the binding target reference directly to a repository.

## 4. Reading `BindingResult` to See What Happened

Useful APIs:

| API | Meaning |
|---|---|
| `hasErrors()` | At least one binding or validation error exists |
| `getErrorCount()` | Total error entries |
| `getFieldErrorCount()` | Number of field error entries |
| `getGlobalErrorCount()` | Number of object-level errors |
| `getFieldError("seats")` | First error associated with `seats` |
| `getFieldErrors("seats")` | All errors for `seats` |
| `getFieldErrors()` | All field errors |
| `getGlobalErrors()` | Errors not tied to a single field |
| `getAllErrors()` | Field + global errors |
| `getSuppressedFields()` | Names of fields blocked from binding |
| `getTarget()` | Target object |
| `getObjectName()` | Model object name used for message resolution |
| `getFieldValue("seats")` | Display/rejected value per BindingResult semantics |
| `getFieldType("seats")` | Known property type |
| `resolveMessageCodes(...)` | Message codes for `MessageSource` lookup |

Pattern for checking a conversion failure:

~~~java
FieldError issue = errors.getFieldError("seats");

assertNotNull(issue);
assertEquals("seats", issue.getField());
assertEquals("typeMismatch", issue.getCode());
assertTrue(issue.isBindingFailure());
assertEquals("abc", issue.getRejectedValue());
~~~

This is a test snippet assuming `errors` exists, using JUnit assertions. `getCode()` is typically the last root code in `getCodes()`; more specific codes include object/field/type names, e.g., `typeMismatch.reservationForm.seats`.

**Never serialize `FieldError.getRejectedValue()` to clients.** On fields carrying passwords, tokens, private form input, or huge payloads, rejected values risk leaks or oversized responses/logs. The test example uses `"abc"` as safe dummy data.

### Be Careful with `getFieldValue(...)`

`BindingResult.getFieldValue("seats")` may favor the rejected value so web forms can re-render prior input. It is **not necessarily** equal to `form.getSeats()` after a conversion failure. To inspect the actual JavaBean value, call the form's getter; to re-render rejected input per policy, use proper view/binding mechanisms and escape output.

## 5. `@ModelAttribute` and `BindingResult` Immediately After the Parameter

Spring MVC handler:

~~~java
@PostMapping("/reservations")
public ResponseEntity<?> create(
        @Valid @ModelAttribute("reservationForm")
        ReservationForm form,
        BindingResult errors) {

    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }

    return ResponseEntity.ok().build();
}
~~~

**`BindingResult` must sit immediately after its corresponding argument.** The framework passes both `form` and `errors` into the method, enabling local handling of validation/binding errors. That is why a handler can still be **invoked even when the form is invalid**.

Without `BindingResult` and local error handling, Spring MVC normally throws `MethodArgumentNotValidException` for binding/validation failures on the validated model attribute. Exact exception type and flow depend on handler signature and any direct method constraints.

### Gating Rule Before Business Calls

~~~java
if (errors.hasErrors()) {
    return invalidResponse(errors);
}

// Reach here only if there are no binding/validation errors.
service.create(toCommand(form));
~~~

Check **before** any side-effecting operation. Calling `service.create(...)` before checking `errors.hasErrors()` makes "returning 400 at the end" arrive too late.

### Is Checking Only `hasErrors()` Enough?

Not necessarily. `DataBinder` supports an **allowlist** and records disallowed fields in `getSuppressedFields()`. Suppressed fields **do not automatically count as `FieldError`s**. If security policy forbids requests containing fields outside the allowlist, check **both**:

~~~java
if (errors.getSuppressedFields().length > 0) {
    return rejectUnexpectedFields();
}
if (errors.hasErrors()) {
    return rejectBindingOrValidationErrors();
}
~~~

Both checks must sit before the service call. Some systems silently ignore unknown fields; that can be valid by contract, provided it is an intentional decision rather than assuming `hasErrors()` catches suppressed fields.

## 6. Partial Binding Does Not Mean a DB Transaction Ran

Separate **in-memory mutation** from **database transaction**:

- `WebDataBinder` may have invoked setters on the JavaBean before hitting a conversion failure.
- `BindingResult` records errors; it is not a transactional undo log.
- `@Transactional` on a service can roll back DB changes under certain rules, yet **does not revert mutations already made to heap objects**.
- If the binder targets a **managed JPA entity**, mutating properties creates dirty state that may flush during a transaction at an unintended moment.
- If a setter has side effects (calling services, publishing events), binding already triggered them **before you checked errors**.
- If `@ModelAttribute` retrieves an object from `@SessionAttributes`, an existing session object can be mutated even when overall input is invalid.
- An object shared outside the request or stored in session can retain partial state if not carefully managed.

**Therefore, the strongest defense is:** bind into a **side-effect-free DTO**, enforce allowlists or constructor binding, gate on errors, and then build an immutable command for the service. Never try to "roll back binding" by calling setters again on an entity.

## 7. Why Binding Directly to a JPA Entity Is Dangerous

Anti-pattern:

~~~java
@PostMapping("/accounts/{id}")
public String update(
        @ModelAttribute AccountEntity entity,
        BindingResult errors) {

    repository.save(entity);
    if (errors.hasErrors()) {
        return "error";
    }
    return "ok";
}
~~~

This is an **anti-pattern**—never use it in production. It has multiple flaws:

- The repository is called **before** checking errors.
- Forms can bind unintended fields if the entity has public setters.
- The entity may expose `role`, `ownerId`, `balance`, `isAdmin`, or foreign keys that must not be user-editable.
- One conversion failure does not guarantee other properties stayed unchanged.
- The entity may be managed by a persistence context, letting dirty checking trigger side effects.
- Authorization checking whether the caller may edit that entity is missing.

**Better model:**

~~~text
HTTP input
  -> Create/UpdateForm DTO containing only accepted fields
  -> allowedFields / constructor binding
  -> bind + validate
  -> reject on error
  -> authenticate + authorize
  -> map to immutable command
  -> service loads entity, verifies invariants
  -> update authorized fields within transaction
  -> commit
~~~

Never bind domain entities directly from HTTP requests; domain entities must not receive arbitrary request fields.

## 8. Restricting Bound Properties with `@InitBinder`

A controller can constrain property binding:

~~~java
@InitBinder("reservationForm")
void initReservationBinder(WebDataBinder binder) {
    binder.setAllowedFields(
        "guestName",
        "seats",
        "contactEmail");
    binder.setAutoGrowCollectionLimit(32);
}
~~~

Key points:

- `setAllowedFields(...)` defines field names permitted for **property binding**.
- Fields outside the allowlist appear in `BindingResult.getSuppressedFields()`.
- `setAutoGrowCollectionLimit(32)` caps collection auto-growth when binding indexed properties; it is **not** a JSON body byte limit.
- `@InitBinder("reservationForm")` applies to the matching model attribute name, not automatically to every attribute.
- Test with the exact `"reservationForm"` name, because if a handler uses another name, the scoped binder config will not run.

Spring recommends a **dedicated form/DTO**, and where property binding is needed, an **allowlist** (`allowedFields`) rather than solely a blocklist. Blocklists easily miss new fields added as objects evolve.

### `setDeclarativeBinding(true)` in Spring 6.1+

Spring `DataBinder` supports:

~~~java
binder.setDeclarativeBinding(true);
~~~

This mode favors **constructor binding**, disallowing open-ended property binding unless appropriate `allowedFields` are declared. It pairs well with immutable DTOs and constructor parameters. Verify command objects, Spring version, parameter names, and conversions in practice; never toggle it globally without integration tests.

**Note:** an allowlist controls which fields may be bound, not whether their values are valid. You still need `@Valid`/`@Validated` and domain checks.

## 9. JSON `@RequestBody` Differs from Form `@ModelAttribute`

Distinguish the two pipelines:

### Form/Query with `@ModelAttribute`

~~~text
Request parameters
  -> WebDataBinder property/constructor binding
  -> BindingResult: conversion + validation errors
  -> Handler (when matching Errors/BindingResult is present)
~~~

This path clearly exhibits **partial binding** because earlier setters succeed even when later ones fail.

### JSON with `@RequestBody`

~~~text
JSON bytes
  -> HttpMessageConverter / Jackson
  -> DTO
  -> validation if @Valid/@Validated
  -> Handler or exception
~~~

When JSON is malformed or cannot be decoded, Jackson/Spring throws `HttpMessageNotReadableException` before any valid argument reaches the handler. **Do not claim** every JSON parse failure produces a `BindingResult` holding partial properties and still invokes the handler.

When JSON parses successfully yet the DTO fails `@Valid`, Spring MVC normally throws `MethodArgumentNotValidException` if no `Errors`/`BindingResult` immediately follows the argument. When `BindingResult` is positioned right after it, the handler can handle validation errors locally depending on method validation and signatures.

For JSON as well, still use a **dedicated request DTO**, validate before business logic, and never let the deserializer bind directly into a managed entity.

## 10. Runnable Example: Spring Boot 3.5 and Java 17+

The sample app exposes `POST /api/reservations` accepting `application/x-www-form-urlencoded`. It demonstrates the exact scenario:

- JavaBean `ReservationForm` has `guestName`, `seats`, `contactEmail`, plus a `vip` field solely to simulate mass assignment.
- `@InitBinder` permits only the first three fields, disallowing `vip`.
- `@Valid` runs Jakarta Bean Validation on the bean.
- The handler checks **suppressed fields** and **`BindingResult` errors** before calling `ReservationService`.
- Once valid, the handler creates an immutable `ReservationService.Command` and invokes the service.
- Error responses include only field name, error code, and binding-failure flag; **never rejected values**.
- Tests prove valid properties already bound even when one field fails type conversion, and prove the service **is never called** on invalid requests.

The project targets Spring Boot **3.5.x**, JDK 17+, and Web/Validation/Test starters. All Java classes live in package `com.example.partialbinding`.

### 10.1. Gradle Dependencies

In a project with the Spring Boot Gradle plugin and dependency management:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Starter Web supplies Spring MVC/Servlet, starter Validation supplies the Jakarta provider, and starter Test supplies JUnit 5, MockMvc, and Mockito. In Spring Boot 3.5/Spring Framework 6.2, `@MockitoBean` resides in `org.springframework.test.context.bean.override.mockito`.

If your project runs Spring Boot 4 or another generation, verify module dependencies and APIs before copying verbatim.

### 10.2. `PartialBindingApplication.java`

`src/main/java/com/example/partialbinding/PartialBindingApplication.java`:

~~~java
package com.example.partialbinding;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PartialBindingApplication {

    public static void main(String[] args) {
        SpringApplication.run(PartialBindingApplication.class, args);
    }
}
~~~

### 10.3. `ReservationForm.java`

`src/main/java/com/example/partialbinding/ReservationForm.java`:

~~~java
package com.example.partialbinding;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;

public class ReservationForm {

    @NotBlank
    private String guestName;

    @NotNull
    @Min(1)
    private Integer seats;

    @NotBlank
    @Email
    private String contactEmail;

    // Illustrates mass-assignment risk.
    // Not among the fields clients are allowed to set.
    private boolean vip;

    public ReservationForm() {
    }

    public String getGuestName() {
        return guestName;
    }

    public void setGuestName(String guestName) {
        this.guestName = guestName;
    }

    public Integer getSeats() {
        return seats;
    }

    public void setSeats(Integer seats) {
        this.seats = seats;
    }

    public String getContactEmail() {
        return contactEmail;
    }

    public void setContactEmail(String contactEmail) {
        this.contactEmail = contactEmail;
    }

    public boolean isVip() {
        return vip;
    }

    public void setVip(boolean vip) {
        this.vip = vip;
    }
}
~~~

`vip` exists with a public setter purely to test the allowlist; an ideal production DTO **should not even contain fields clients are forbidden from editing**. The example keeps it so you can see the difference between a writable object property and a binding-allowed field.

`@NotNull @Min(1)` ensures `seats` is non-null and at least 1; `@Min` alone does not reject null. `@NotBlank @Email` requires non-blank content and basic email format; `@Email` does not prove ownership verification.

### 10.4. `ReservationService.java`

`src/main/java/com/example/partialbinding/ReservationService.java`:

~~~java
package com.example.partialbinding;

import java.util.concurrent.atomic.AtomicLong;

import org.springframework.stereotype.Service;

@Service
public class ReservationService {

    private final AtomicLong sequence = new AtomicLong();

    public Receipt create(Command command) {
        long id = sequence.incrementAndGet();

        // Substitutes for real persistence in this exercise.
        return new Receipt(
            id, command.guestName(), command.seats());
    }

    public record Command(
        String guestName,
        int seats,
        String contactEmail
    ) {
    }

    public record Receipt(
        long id,
        String guestName,
        int seats
    ) {
    }
}
~~~

`Command` is an immutable record containing only **the three accepted fields**. The service holds an in-memory counter simulating state mutation; in production this might insert into a DB or emit an event. What matters is not the specific persistence, but **never calling `create` while `BindingResult` has errors**.

### 10.5. `ReservationController.java`

`src/main/java/com/example/partialbinding/ReservationController.java`:

~~~java
package com.example.partialbinding;

import java.util.ArrayList;
import java.util.List;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
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
@RequestMapping("/api/reservations")
public class ReservationController {

    private final ReservationService service;

    public ReservationController(ReservationService service) {
        this.service = service;
    }

    @InitBinder("reservationForm")
    void configureBinding(WebDataBinder binder) {
        binder.setAllowedFields(
            "guestName", "seats", "contactEmail");
        binder.setAutoGrowCollectionLimit(32);
    }

    @PostMapping(
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE
    )
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("reservationForm")
            ReservationForm form,
            BindingResult errors) {

        // Suppressed fields do not necessarily increment hasErrors().
        if (errors.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                .body(new Problem(
                    "UNEXPECTED_FIELDS", List.of()));
        }

        // Gate before any service call.
        if (errors.hasErrors()) {
            List<Issue> issues = new ArrayList<>();

            for (FieldError field : errors.getFieldErrors()) {
                issues.add(new Issue(
                    field.getField(),
                    field.getCode(),
                    field.isBindingFailure()));
            }

            for (ObjectError global : errors.getGlobalErrors()) {
                issues.add(new Issue(
                    "$object",
                    global.getCode(),
                    false));
            }

            return ResponseEntity.badRequest()
                .body(new Problem(
                    "INVALID_RESERVATION", issues));
        }

        ReservationService.Command command =
            new ReservationService.Command(
                form.getGuestName(),
                form.getSeats(),
                form.getContactEmail());

        ReservationService.Receipt receipt =
            service.create(command);

        return ResponseEntity.status(HttpStatus.CREATED)
            .body(receipt);
    }

    public record Problem(
        String code,
        List<Issue> issues
    ) {
    }

    public record Issue(
        String field,
        String code,
        boolean bindingFailure
    ) {
    }
}
~~~

**This is a complete class** for Spring MVC 6.2 in the project above. Notable points:

1. `BindingResult` sits **immediately after** `@Valid @ModelAttribute("reservationForm") ReservationForm`.
2. `@InitBinder("reservationForm")` scopes the allowlist to the matching object name.
3. `getSuppressedFields()` is checked separately from `hasErrors()`; a client sending `vip=true` is rejected per the demo's policy.
4. Error branches return **400** and exit immediately without calling `service.create(...)`.
5. `FieldError.isBindingFailure()` distinguishes conversion failures from constraint violations; multiple errors on the same field are all preserved.
6. Whole-object errors use `"$object"` per the demo's own schema. In real products, use a dedicated scope field instead of overloading a synthetic field path.
7. Neither `getRejectedValue()` nor the target object is included in responses.
8. Data is mapped into an immutable `Command` **only on the success branch**, after passing the validation gate.
9. Unboxing `form.getSeats()` from `Integer` to `int` is safe here only because `@NotNull` ran and errors were gated; if validator config changes, add domain assertions in the service.
10. If a binding target had a malicious setter, the validation gate arrives too late to undo that setter; hence DTOs must be side-effect-free.

### 10.6. Running the App

At the project root with Gradle wrapper:

~~~bash
./gradlew bootRun
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

Valid form:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/reservations" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "guestName=Lan" \
  --data-urlencode "seats=2" \
  --data-urlencode "contactEmail=lan@example.org"
~~~

Expect HTTP **201 Created**, body with ID starting from 1 on a fresh instance with no prior requests:

~~~json
{
  "id": 1,
  "guestName": "Lan",
  "seats": 2
}
~~~

On a long-running server, ID increases via `AtomicLong`; **never hardcode `1` in standalone integration tests**.

Form with conversion failure:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/reservations" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "guestName=Lan" \
  --data-urlencode "seats=abc" \
  --data-urlencode "contactEmail=lan@example.org"
~~~

Expect HTTP **400 Bad Request**. The response may contain multiple issues if Jakarta validation also records `@NotNull` when the field fails to convert; therefore do not assert `issues.length == 1`. One key entry is:

~~~json
{
  "field": "seats",
  "code": "typeMismatch",
  "bindingFailure": true
}
~~~

The snippet above is **one element in `issues[]`**, not the entire response. Meanwhile, `guestName` and `contactEmail` were already bound onto the JavaBean; the handler blocks before invoking the service.

Form valid on the three fields yet attempting to set `vip`:

~~~bash
curl -i -X POST \
  "http://localhost:8080/api/reservations" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  --data-urlencode "guestName=Lan" \
  --data-urlencode "seats=2" \
  --data-urlencode "contactEmail=lan@example.org" \
  --data-urlencode "vip=true"
~~~

Expect HTTP **400** and:

~~~json
{
  "code": "UNEXPECTED_FIELDS",
  "issues": []
}
~~~

Note: `vip` is blocked **not by `@Min` or `@NotBlank`** but by the allowlist. Checking only `hasErrors()` without checking suppressed fields would let a request carrying disallowed fields pass; the demo enforces rejection.

## 11. `DataBinder` Unit Tests: Proving Partial Binding Directly

These unit tests send no HTTP requests, using only Spring `DataBinder` and the JavaBean. Thus they directly prove the difference between **Java object state** and **`BindingResult`**.

`src/test/java/com/example/partialbinding/PartialBindingDataBinderTest.java`:

~~~java
package com.example.partialbinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.MutablePropertyValues;
import org.springframework.validation.BindingResult;
import org.springframework.validation.DataBinder;
import org.springframework.validation.FieldError;

import static org.junit.jupiter.api.Assertions.assertArrayEquals;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertNull;
import static org.junit.jupiter.api.Assertions.assertTrue;

class PartialBindingDataBinderTest {

    private static DataBinder newBinder(ReservationForm form) {
        DataBinder binder =
            new DataBinder(form, "reservationForm");
        binder.setAllowedFields(
            "guestName", "seats", "contactEmail");
        return binder;
    }

    @Test
    void validFieldsAreAppliedEvenWhenSeatsCannotConvert() {
        ReservationForm form = new ReservationForm();
        DataBinder binder = newBinder(form);

        MutablePropertyValues input =
            new MutablePropertyValues();
        input.add("guestName", "Lan");
        input.add("seats", "abc");
        input.add("contactEmail", "lan@example.org");

        binder.bind(input);

        BindingResult errors = binder.getBindingResult();
        FieldError badSeats = errors.getFieldError("seats");

        // Other properties were still set successfully.
        assertEquals("Lan", form.getGuestName());
        assertEquals(
            "lan@example.org", form.getContactEmail());

        // Conversion failure does not turn "abc" into an Integer.
        assertNull(form.getSeats());
        assertTrue(errors.hasFieldErrors("seats"));

        assertNotNull(badSeats);
        assertTrue(badSeats.isBindingFailure());
        assertEquals("typeMismatch", badSeats.getCode());
        assertEquals("abc", badSeats.getRejectedValue());
        assertEquals("reservationForm",
            errors.getObjectName());
    }

    @Test
    void deniedVipFieldIsSuppressedNotApplied() {
        ReservationForm form = new ReservationForm();
        DataBinder binder = newBinder(form);

        MutablePropertyValues input =
            new MutablePropertyValues();
        input.add("guestName", "Lan");
        input.add("seats", "2");
        input.add("contactEmail", "lan@example.org");
        input.add("vip", "true");

        binder.bind(input);

        BindingResult errors = binder.getBindingResult();

        assertFalse(form.isVip());
        assertEquals("Lan", form.getGuestName());
        assertEquals(2, form.getSeats());
        assertArrayEquals(
            new String[] {"vip"},
            errors.getSuppressedFields());

        // Suppression is a separate mechanism, not a FieldError by default.
        assertFalse(errors.hasErrors());
    }

    @Test
    void bindWithoutValidationDoesNotRunNotBlank() {
        ReservationForm form = new ReservationForm();
        DataBinder binder = newBinder(form);

        MutablePropertyValues input =
            new MutablePropertyValues();
        input.add("guestName", " ");
        input.add("seats", "2");
        input.add("contactEmail", "lan@example.org");

        binder.bind(input);

        assertEquals(" ", form.getGuestName());

        // Calling bind() alone does not trigger Bean Validation annotations.
        assertFalse(binder.getBindingResult().hasErrors());
    }

    @Test
    void noValuesDoesNotInitializeFields() {
        ReservationForm form = new ReservationForm();
        DataBinder binder = newBinder(form);

        binder.bind(new MutablePropertyValues());

        assertNull(form.getGuestName());
        assertNull(form.getSeats());
        assertNull(form.getContactEmail());

        // Bean Validation has not run yet, even though @NotBlank/@NotNull fail.
        assertFalse(binder.getBindingResult().hasErrors());
    }
}
~~~

**Four tests** confirm:

- The JavaBean **genuinely mutated partially** when a conversion error occurred.
- `getRejectedValue()` holds raw `"abc"`, while `form.getSeats()` stays null.
- A field with a public setter outside the allowlist is suppressed.
- Suppressed fields **do not increment `hasErrors()` by default**, so security policy must check them separately to reject.
- Manual `DataBinder.bind(...)` does not invoke Jakarta Bean Validation.

These tests use JUnit, Spring `DataBinder`, and the JavaBean, **without needing a Spring Boot application context**.

## 12. MockMvc Tests: Ensuring the Service Is Never Called When Errors Exist

The `DataBinder` unit tests prove partial binding; MockMvc verifies **whether the handler blocks the business action**.

Use `@WebMvcTest(ReservationController.class)` to load the Spring MVC slice and `@MockitoBean` to replace the service with a Mockito mock. That lets `verifyNoInteractions(service)` prove invalid requests never reach the service.

`src/test/java/com/example/partialbinding/ReservationControllerTest.java`:

~~~java
package com.example.partialbinding;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.http.MediaType;
import org.springframework.test.context.bean.override.mockito.MockitoBean;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.hasItem;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.verifyNoInteractions;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ReservationController.class)
class ReservationControllerTest {

    @Autowired
    private MockMvc mvc;

    @MockitoBean
    private ReservationService service;

    @Test
    void invalidNumberCannotReachService() throws Exception {
        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "Lan")
                .param("seats", "abc")
                .param("contactEmail", "lan@example.org"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_RESERVATION"))
            .andExpect(jsonPath("$.issues[*].field",
                hasItem("seats")))
            .andExpect(jsonPath(
                "$.issues[*].bindingFailure",
                hasItem(true)));

        verifyNoInteractions(service);
    }

    @Test
    void invalidMinConstraintCannotReachService()
            throws Exception {
        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "Lan")
                .param("seats", "0")
                .param("contactEmail", "lan@example.org"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("INVALID_RESERVATION"))
            .andExpect(jsonPath("$.issues[*].field",
                hasItem("seats")));

        verifyNoInteractions(service);
    }

    @Test
    void blankGuestCannotReachService() throws Exception {
        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "   ")
                .param("seats", "2")
                .param("contactEmail", "lan@example.org"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[*].field",
                hasItem("guestName")));

        verifyNoInteractions(service);
    }

    @Test
    void deniedVipFieldCannotReachService()
            throws Exception {
        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "Lan")
                .param("seats", "2")
                .param("contactEmail", "lan@example.org")
                .param("vip", "true"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code")
                .value("UNEXPECTED_FIELDS"));

        verifyNoInteractions(service);
    }

    @Test
    void validFormCreatesImmutableCommand()
            throws Exception {

        ReservationService.Receipt fakeReceipt =
            new ReservationService.Receipt(
                17L, "Lan", 2);

        when(service.create(
                any(ReservationService.Command.class)))
            .thenReturn(fakeReceipt);

        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "Lan")
                .param("seats", "2")
                .param("contactEmail", "lan@example.org"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value(17))
            .andExpect(jsonPath("$.guestName").value("Lan"))
            .andExpect(jsonPath("$.seats").value(2));

        verify(service).create(
            new ReservationService.Command(
                "Lan", 2, "lan@example.org"));
    }

    @Test
    void malformedEmailCannotReachService()
            throws Exception {

        mvc.perform(post("/api/reservations")
                .contentType(
                    MediaType.APPLICATION_FORM_URLENCODED)
                .param("guestName", "Lan")
                .param("seats", "2")
                .param("contactEmail", "not-an-email"))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.issues[*].field",
                hasItem("contactEmail")));

        verifyNoInteractions(service);
    }
}
~~~

**Six tests** in this class verify the validation gate across all branches: conversion failure, `@Min`, `@NotBlank`, suppressed field, success path, and email format. In particular, `verifyNoInteractions(service)` proves **no business call occurred**, rather than checking HTTP 400 alone.

**Note:** Mockito mocks are managed/reset by Spring Test per `@MockitoBean`'s default lifecycle. Production tests with Spring Security may require mock authentication/CSRF in the MVC slice depending on the filter chain; this example uses Web + Validation + Test starters without extra security config.

### Running Tests

~~~bash
./gradlew test
~~~

Windows PowerShell:

~~~powershell
.\gradlew.bat test
~~~

Altogether the project contains **10 JUnit test methods**: four `DataBinder` tests and six `MockMvc` tests. With the dependencies and configuration above, they are **designed to PASS**; this is an expectation from code analysis, **not a claim that Gradle was run in this article**.

To run each group individually:

~~~bash
./gradlew test \
  --tests "com.example.partialbinding.PartialBindingDataBinderTest"
~~~

and:

~~~bash
./gradlew test \
  --tests "com.example.partialbinding.ReservationControllerTest"
~~~

## 13. Why Can `errors.hasErrors()` Be False Even When Data Is Unsafe?

There are at least five independent reasons:

1. **Validation was never run:** manual `DataBinder.bind(...)` only sets fields and records conversion errors; if a converted field violates `@NotBlank` without running a validator, `hasErrors()` stays false.
2. **Missing Jakarta provider:** the project compiles with annotations, yet runtime lacks `spring-boot-starter-validation`/a compatible provider, so validation does not run as expected.
3. **Missing `@Valid`/`@Validated` on MVC parameter:** the DTO carries annotations that are never triggered.
4. **Fields were suppressed** under `setAllowedFields(...)`: suppressed fields **do not automatically become `FieldError`s**.
5. **Business authorization/invariants unchecked:** a form valid in types and constraints can still violate access permissions or business state.

Hence the proceed condition must not be simplified to "`!hasErrors()` means everything is safe"—define explicit checks before the service boundary.

### A Good Validation Gate May Include

~~~text
[ ] Fully parsed/bound per contract
[ ] No policy-violating suppressed fields
[ ] No BindingResult errors
[ ] No unexecuted group/cross-field rules
[ ] Request field allowlist/size limits satisfied
[ ] Authentication and authorization verified
[ ] Mapping copies only allowed fields
[ ] Service re-verifies business invariants
[ ] Only then write to DB or emit side effects
~~~

The final steps belong at the service/transaction boundary; never cram full domain authorization into a `ConstraintValidator` meant for input syntax.

## 14. When to Throw an Exception vs. When to Use `BindingResult`?

Both styles are valid, serving different needs.

### Controller Handles Errors Locally

~~~java
public ResponseEntity<?> submit(
        @Valid @ModelAttribute("form") FormDto form,
        BindingResult errors) {
    if (errors.hasErrors()) {
        return ResponseEntity.badRequest().build();
    }
    // ...
}
~~~

Suited for re-rendering a form view with per-field errors, or building a custom error response inside the handler. Requirement: **`BindingResult` sits immediately after the argument** and every code path gates before side effects.

### Global Exception Handler

If the handler omits `BindingResult`, Spring MVC throws `MethodArgumentNotValidException` when validation of `@ModelAttribute`/`@RequestBody` fails, and `@RestControllerAdvice` or `ResponseEntityExceptionHandler` maps it to an error body.

This pattern reduces the risk of a handler accidentally using an invalid form, **yet does not make binding atomic**; partial property mutation onto the object still happened earlier in the lifecycle before the exception.

Pick the fitting strategy and test it. When using global advice, prefer extending `ResponseEntityExceptionHandler` and overriding the proper `handleMethodArgumentNotValid(...)` hook instead of adding a conflicting `@ExceptionHandler`.

### Do Not Mix Mechanisms Assuming the Same Exception

- JSON parse error: typically `HttpMessageNotReadableException`.
- `@ModelAttribute` form conversion/validation: `BindingResult` or `MethodArgumentNotValidException` depending on signature.
- Direct `@Min @RequestParam`: MVC 6.1+ method validation can raise `HandlerMethodValidationException`.
- `@RequestParam Integer` receiving `abc`: type mismatch during argument resolution, typically `MethodArgumentTypeMismatchException`.
- Multipart upload errors may occur before the handler runs.

Not every HTTP 400 carries the same `BindingResult` or gets intercepted at the same point.

## 15. When Multiple Constraints Exist on One Field

Example:

~~~java
@NotNull
@Min(1)
private Integer seats;
~~~

With `seats=null`, `@NotNull` fails while `@Min` normally treats null as valid. With `seats=0`, `@Min` fails. With form input `seats=abc`, the binder fails to convert to `Integer` and records `typeMismatch`; then the provider may also record `@NotNull` if run against the bean whose `seats` stayed null.

Therefore:

- Never assume a field has at most one error.
- Never assume only one error code appears on conversion failure.
- Never assume the error ordering between Jakarta provider and binder is a durable contract.
- Never use `getFieldError("seats")` to assert **every** error on the field; use `getFieldErrors("seats")` when completeness matters.
- In responses, map errors as a list, optionally normalizing/deduplicating intentionally.
- Never pass rejected raw input into domain commands.

A field with `typeMismatch` does not mean "binding failed for the whole DTO"; other fields may still have been assigned.

## 16. Never Bind Objects with Side Effects Before the Validation Gate

Consider a dangerous setter:

~~~java
public void setAccountStatus(String status) {
    auditService.publish(
        new StatusChangedEvent(status));
    this.accountStatus = status;
}
~~~

This is an **anti-pattern**; types are illustrative. If the binder calls this setter, the event is published **during binding**, before the handler even checks `hasErrors()`. Returning HTTP 400 afterward will not retract the event.

An ideal request DTO JavaBean should:

- Have simple setters that only assign fields.
- Never call repositories, send emails, or publish events.
- Never be a managed JPA entity.
- Have no setters for fields clients are forbidden from modifying.
- Not embed business invariants that belong inside a transaction.
- Be freshly instantiated per request unless state retention is explicitly required.

If you must bind onto an existing object from session/model, evaluate partial mutation impact and lifecycle guards; better yet, bind into a **dedicated copy/command** and apply changes to the domain after validation.

## 17. Field Allowlists, Suppressed Fields, and Mass Assignment

An attacker might also submit:

~~~text
guestName=Lan
seats=2
contactEmail=lan@example.org
vip=true
ownerId=other-user
status=APPROVED
~~~

If you bind directly onto an entity exposing matching setters without an allowlist, fields absent from the UI can still be assigned. A `setDisallowedFields(...)` blocklist easily misses new fields as the domain grows.

Defend in order of priority:

1. **Dedicated request DTO** containing only properties truly meant for input.
2. **Constructor binding** or declarative binding where appropriate.
3. **`setAllowedFields(...)`** wherever property binding remains necessary.
4. **Check `getSuppressedFields()`** if the contract rejects unknown/disallowed fields.
5. **Service-layer authorization** on the actor and target resource.
6. **Never pass a DTO/entity wholesale into `repository.update(...)`** when it carries fields outside the contract.

In the demo, `vip` sits on the DTO only to test the allowlist, whereas real systems should omit sensitive fields from request DTOs altogether.

### Suppressed Does Not Always Mean Illegal

An API may intentionally allow extra client fields and silently ignore them per contract. Then `getSuppressedFields()` feeds metrics/troubleshooting without returning 400. The demo enforces a **strict** policy: suppressed fields trigger rejection. Which approach fits depends on compatibility, security, and API versioning; what matters is **deciding deliberately**.

## 18. Do Not Confuse Partial Binding with Partial Persistence

Distinguish three concepts:

| Concept | When it happens | Auto-rolls back? |
|---|---|---|
| Partial property binding | When the binder sets some properties on the object | Not by default |
| Partial business processing | When controller/service executes partial work before noticing errors | Not automatically |
| Partial persistence | When DB/external systems receive some writes | Depends on transaction/consistency design, not guaranteed by BindingResult |

Inside a DB transaction, an exception can trigger rollback per propagation/rollback rules. Yet:

- Returning `400` without throwing an exception inside the transaction does not trigger rollback just because the HTTP status is 400.
- External side effects such as emails, outbound HTTP calls, or message publishing do not necessarily participate in a DB transaction.
- JPA dirty checking may flush changes on a managed entity even without calling `save` explicitly, depending on context/transaction.
- In-memory field mutations persist on the current object reference even if the DB rolls back.

**Best practice: never start a business transaction or side effects for a request that has not cleared the binding and validation gate.** Transactional invariants still need protection inside the service.

## 19. Validation Groups and Custom Spring Validators Also Need Activation

`@Valid` normally requests the Jakarta Bean Validation `Default` group. If using `@Validated(SomeGroup.class)` while a rule belongs to another group, `BindingResult` will lack the expected error.

A custom Spring `Validator`:

~~~java
public final class FormRules implements Validator {

    @Override
    public boolean supports(Class<?> type) {
        return ReservationForm.class.isAssignableFrom(type);
    }

    @Override
    public void validate(Object target, Errors errors) {
        // errors.rejectValue(...) or errors.reject(...)
    }
}
~~~

This snippet requires `org.springframework.validation.Validator`/`Errors` imports and the class in scope. Creating the class alone does not make `DataBinder.bind(...)` invoke it. With a manual binder:

~~~java
binder.addValidators(customValidator);
binder.validate();
~~~

In Spring MVC, use `@InitBinder` to register the validator and trigger validation on the argument. Never accidentally replace the global Jakarta validator with a custom validator that skips annotations.

If `hasErrors()==false` on a blank form, verify that both validation provider and trigger are active rather than staring only at `bind(...)`.

## 20. Designing a Stable Error API Without Leaking Input

Responses should inform clients of:

- A stable public error code, e.g., `INVALID_RESERVATION`.
- Publicly exposable field names that failed.
- Categorized error codes, e.g., `INVALID_NUMBER`, `REQUIRED_FIELD`, `VALUE_BELOW_MIN`.
- Localized messages resolved via `MessageSource` if required.
- Object-level errors without dropping them.

Never send:

- The entire `BindingResult`.
- `getTarget()` (the form/managed object).
- `FieldError.getRejectedValue()` for every field.
- Internal Java class names, stack traces, or undisclosed database IDs.
- Raw suppressed field names when they could expose sensitive internal property names.

Example schema:

~~~json
{
  "code": "INVALID_RESERVATION",
  "issues": [
    {
      "field": "seats",
      "code": "typeMismatch",
      "bindingFailure": true
    }
  ]
}
~~~

This is a learning schema using Spring's raw code; production APIs may map `typeMismatch` to a stable code like `INVALID_NUMBER` and localize messages. Do not mistake this example for Spring Boot's default output.

### Why Not Echo Rejected Input?

On conversion errors, rejected raw values can be huge or contain secrets. To re-populate user input in HTML forms, use proper template/form-binding mechanisms with output encoding rather than forcing public APIs to echo arbitrary raw input.

## 21. Observability and Logging for Binding Errors

Useful metrics:

- Rate of requests with `typeMismatch`.
- `BindingResult.getFieldErrorCount()` per endpoint and allowed field.
- Count of requests with suppressed fields.
- Share of HTTP 400s from binding vs. validation vs. domain rules.
- Count of business calls blocked before the service.
- p95/p99 latency of binding and validation.
- Count of requests exceeding parameter/body/collection limits.

Avoid logging full request bodies and rejected values, especially on endpoints accepting personal data. For investigation, log request IDs, route templates, and error codes rather than arbitrary raw input.

### Smoke Test for Production

After changing a DTO, framework version, or binder configuration, write a regression test submitting a form with one valid field and one invalid field, and assert **the service is never called**. A test asserting only HTTP 400 misses bugs where the service runs **before returning 400**.

When `@Transactional` is used, include integration tests verifying no DB rows were inserted on invalid requests and mock external events were not published, placed at the right boundary; `MockMvc` + `@MockitoBean` suffices to teach the no-service-call principle.

## 22. Common Implementation Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| `hasErrors()==true` yet `guestName` is set | Partial binding is expected | Do not use target before validation gate |
| One field failed yet controller calls service | Error check too late or missing | Early return before service |
| Form has `BindingResult` and handler still runs | Handler opted into local error handling | Check `errors.hasErrors()` |
| `getSuppressedFields()` non-empty yet `hasErrors()==false` | Suppression is distinct from FieldError | Gate separately under strict input policy |
| Client sends `vip=true` despite UI omitting it | Mass assignment attempt | Dedicated DTO + `allowedFields` |
| Valid email, `seats=abc` leaves DTO invalid | Conversion failed only on seats | Reject whole request; never "accept half" |
| `getFieldValue("seats")` differs from `form.getSeats()` | Rejected input retained for display | Distinguish field value vs. target getter |
| `@Min` missing when `seats=abc` | Conversion failed earlier | Check `typeMismatch` |
| `@NotBlank` missing after manual bind | Validator never called | Call `binder.validate()` or MVC `@Valid` |
| Global errors dropped from response | Mapping only `getFieldErrors()` | Map `getGlobalErrors()` too |
| Service called before returning 400 | Wrong validation gate order | Gate before side effects |
| Returns 400 yet DB changed | Entity managed/saved before validation | Dedicated DTO + service transaction after gate |
| `@Transactional` did not undo setter | In-memory mutation outside DB rollback | Never bind entities/domain objects |
| Custom setter emitted event during binding | Setter has side effect | Use side-effect-free DTOs |
| HTTP 400 test PASSES yet service still called | Never verified no interactions | Mock service + `verifyNoInteractions` |
| `@InitBinder` does not apply allowlist | Attribute name/scope mismatch | Test `"reservationForm"` and binder config |
| Malformed JSON never reaches handler | `@RequestBody` decoder failed | Handle `HttpMessageNotReadableException` |
| `BindingResult` placed far from argument | Not paired with target model parameter | Place immediately after validated argument |
| Multiple errors yet test checks only first | `getFieldError` returns one entry | Use `getFieldErrors(field)` |
| Formatter/conversion differs between unit and MVC | Different DataBinder setup | Add MockMvc test for binder config |
| JavaBean exposes admin/owner setters | Poor DTO design | Remove fields from request DTO |
| Validator class exists yet annotations do not run | Missing provider/entry point/group | Test provider + `@Valid`/`@Validated` |

### Debugging in Order

1. Determine whether the endpoint uses `@ModelAttribute` or `@RequestBody`.
2. Confirm whether the target object is freshly created or pulled from session/model/entity.
3. Verify `BindingResult` sits immediately after the argument.
4. Check whether errors are conversion (`typeMismatch`) or Jakarta constraints (`Min`, `NotBlank`).
5. After binding, compare populated target properties against rejected fields.
6. Check `getSuppressedFields()` independently of `hasErrors()`.
7. Review code order: is any service/repository invoked before the error branch?
8. Review DTO setters: are there side effects or disallowed writable fields?
9. Check `@InitBinder`/`allowedFields`/declarative binding and scope.
10. Check provider and `@Valid`/groups if validation errors should have occurred.
11. Use MockMvc and `verifyNoInteractions(service)` for invalid requests.
12. Add a DB integration test if proving zero persistence side effects is required.

## 23. Self-Practice Questions

**1. Does `BindingResult.hasErrors()==true` guarantee every field kept its pre-request value?**

No. Properties that bound cleanly may already have been assigned on the target even though another field failed.

**2. Does `DataBinder.bind(...)` automatically roll back every setter upon hitting `typeMismatch`?**

No. It is not a transaction rollback mechanism.

**3. Why can `getRejectedValue()` differ from the JavaBean getter?**

`BindingResult` retains the rejected raw input for error reporting/re-display; the Java property cannot hold a value of the wrong type.

**4. Is it a Spring bug when a handler with `@Valid @ModelAttribute` and `BindingResult` is invoked on invalid input?**

No. That is local error handling; the handler is responsible for checking and returning early.

**5. Does checking only `hasErrors()` catch every field blocked by an allowlist?**

Not necessarily; suppressed fields have their own `getSuppressedFields()` API.

**6. Why should you never bind directly to a managed JPA entity?**

Partial binding can mutate the entity inside the persistence context before validation finishes; combined with mass assignment and dirty checking, it risks unintended side effects.

**7. Does `@Transactional` automatically undo an event emitted by a setter during binding?**

No. A DB transaction does not guarantee rollback of external side effects or arbitrary in-memory mutations.

**8. When should an immutable command be constructed from the form?**

Only after confirming zero binding/validation errors and zero input-policy violations.

**9. With `seats=abc` and `@Min(1)`, where does the primary error originate?**

Type conversion fails while trying to construct an `Integer`, typically producing `typeMismatch`; `@Min` does not evaluate on the raw string.

**10. Which test proves a handler causes no business side effects on invalid input?**

MockMvc sending an invalid request plus Mockito `verifyNoInteractions(service)`.

**11. Does malformed JSON on `@RequestBody` always pass a partial DTO into the handler?**

No. The decoder typically throws an exception before the handler receives a valid argument.

**12. Do `setAllowedFields(...)` and `@Valid` replace each other?**

No. One restricts which fields may be bound; the other validates constraints on values.

**13. When a field has multiple errors, is `getFieldError(field)` enough?**

No if you need all of them; use `getFieldErrors(field)`.

**14. Why separate suppressed-field errors from constraint errors?**

They enforce different policies; suppressed fields are not necessarily represented as `FieldError`s.

## 24. Checklist to Prevent Partial-Data Misuse

- [ ] Use dedicated DTOs; never bind directly to managed entities.
- [ ] Keep DTO setters completely free of side effects.
- [ ] Audit whether model objects are reused from session/model.
- [ ] Place `BindingResult` immediately after the validated argument for local handling.
- [ ] Check `hasErrors()` **before** every service/persistence call.
- [ ] Check `getSuppressedFields()` if the API rejects out-of-allowlist fields.
- [ ] Use `setAllowedFields(...)` and/or declarative/constructor binding properly.
- [ ] Never rely solely on a `setDisallowedFields(...)` blocklist.
- [ ] Verify `@Valid`/`@Validated` and the provider actually run.
- [ ] Distinguish conversion failures from constraint violations.
- [ ] Never treat `getFieldValue(...)` as a guaranteed bound JavaBean property.
- [ ] Never pass rejected raw values into immutable business commands.
- [ ] Map field/global errors in a structured form without leaking targets or secrets.
- [ ] Enforce authorization and invariants inside domain services.
- [ ] Ensure commits/side effects happen only after an adequate validation gate.
- [ ] Add checks for idempotency, retries, and concurrency per domain needs.
- [ ] Test partial binding using real `DataBinder`.
- [ ] Test that invalid requests never call services using Mockito/MockMvc.
- [ ] Test allowlists using a field that has a setter yet must not be client-editable.
- [ ] Re-run processing-order regression tests whenever Spring/Boot/DTOs change.
- [ ] Never assume data rolled back merely because HTTP 400 was returned.
- [ ] Run Gradle and verify real test results before deploying.

**Remember:** In Spring MVC, **partial binding is an expected state**, not an atomic guarantee of `DataBinder`. Some fields are already populated while `BindingResult` records errors on others. Always **bind into a side-effect-free request DTO**, restrict bindable fields, check **`getSuppressedFields()` and `hasErrors()`**, and only then map to an immutable command and invoke the service. A truly valuable test verifies not just **HTTP 400**, but also **zero calls to business services when a request still has errors**.

## Official References

- [Spring Framework 6.2 — Model Attribute Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework 6.2 — @InitBinder and Model Design](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-initbinder.html)
- [Spring Framework 6.2 — DataBinder Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/DataBinder.html)
- [Spring Framework 6.2 — BindingResult Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/BindingResult.html)
- [Spring Framework 6.2 — FieldError Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/validation/FieldError.html)
- [Spring Framework 6.2 — Data Binding](https://docs.spring.io/spring-framework/reference/6.2/core/validation/data-binding.html)
- [Spring Framework 6.2 — MVC Validation](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework 6.2 — Method Arguments](https://docs.spring.io/spring-framework/reference/6.2/web/webmvc/mvc-controller/ann-methods/arguments.html)
- [Spring Boot 3.5 — Validation](https://docs.spring.io/spring-boot/3.5/reference/io/validation.html)
- [Spring Framework 6.2 — MockitoBean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/test/context/bean/override/mockito/MockitoBean.html)
