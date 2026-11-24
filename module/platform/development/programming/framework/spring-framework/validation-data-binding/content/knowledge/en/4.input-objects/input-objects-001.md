# Designing a Task-Specific DTO or Form Object in Spring Framework

## 1. Why Must an Input Object Follow a Specific Task?

Suppose an application has a task to **register for a workshop**. The user only needs to enter their name, email, and number of seats. The system determines the registration ID, unit price, total amount, and status itself. If a controller receives an entity directly that also contains `id`, `totalVnd`, `status`, and administrative fields, HTTP input can accidentally or intentionally write to properties not meant for the user.

**An input DTO (request DTO) or form object should describe exactly the information a task is allowed to accept**, not the entire database structure.

- **DTO (Data Transfer Object)**: a data structure transferred across a boundary, such as a JSON request, a form submission, or a service call. Calling it a DTO does not require a class with setters; a Java `record` is also a suitable DTO.
- **Form object / command object**: an object representing the fields of a form or business action performed by a user, commonly used with Spring MVC `@ModelAttribute`. A form object can be a JavaBean with a no-arg constructor and getters/setters, or an immutable type using constructor binding.
- **Domain entity / persistence entity**: represents the data and business lifecycle of the system. An entity usually includes an ID, status, auditing information, JPA relationships, and internal invariants.
- **Response DTO**: the contract for returning data to the client; it may differ from both the request DTO and the entity.

Different tasks need different contracts, even when operating on the same entity. For example, `CreateRegistrationForm`, `ChangeRegistrationEmailRequest`, and `CancelRegistrationRequest` should not share a single `RegistrationDto` containing all fields with many nullable values and ambiguous write permissions.

## 2. Starting from the Contract of a Specific Task

**User story:** An attendee submits a workshop registration form, selecting from 1 to 5 seats. The system records the registration in `PENDING` status and calculates the fee at an illustrative unit price of 250,000 VND/seat.

| Field | Source | Suggested Java Type | Rules |
| --- | --- | --- | --- |
| `attendeeName` | User | `String` | Required, not whitespace-only, max 80 characters |
| `email` | User | `String` | Required, valid email syntax, max 120 characters |
| `seats` | User | `Integer` | Required, from 1 to 5 |
| `registrationId` | Server | Not in input form | Generated when saving in a real system |
| `pricePerSeatVnd` | Server | Not in input form | Calculated/looked up per server policy |
| `totalVnd` | Server | Not in input form | Calculated from seats and trusted unit price |
| `status` | Server | Not in input form | Initial status defined by business rules |
| `createdAt`, `createdBy` | Server | Not in input form | Taken from system clock and authenticated identity |

A valid form request has logical content equivalent to:

```text
attendeeName=Lan Nguyen
email=lan@example.com
seats=2
```

Fields such as `status=APPROVED` or `totalVnd=0` **do not belong to the input contract**, even though a client can still send them over HTTP. Hiding an HTML input does not create a security boundary; the server must actively restrict which properties can be bound and always compute or look up sensitive data on the server side.

**The expected result** of the demo application is a confirmation of the name, seat count, total amount, and status. For example, it omits the email to avoid exposing extra unnecessary personal data in the response.

## 3. From Request to Business Logic: What Are Each Layer's Responsibilities?

```text
POST /registrations (application/x-www-form-urlencoded)
          |
          v
CreateRegistrationForm
  - Only attendeeName, email, seats
  - @NotBlank, @Email, @NotNull, @Min, @Max, @Size
          |
          v
Spring MVC @ModelAttribute + WebDataBinder
  - Bind and convert data types
  - Accept only allowedFields
          |
          v
@Valid + BindingResult
  - Catch input structure/format errors
          |
          v
Controller maps each field explicitly
          |
          v
CreateRegistrationCommand
          |
          v
RegistrationService
  - Check business invariants
  - Calculate total amount and status on server
          |
          v
RegistrationReceipt (response DTO)
```

Separating objects along boundaries allows changing forms without breaking the persistence model, avoids exposing internal data externally, and reduces the risk of **overposting / mass assignment**: a client attempting to write properties that the feature does not permit modifying.

Not every project needs an intermediate `Command` class. For small tasks, the controller can map validated values directly into a service method with explicit parameters. What matters is **never passing a freshly bound entity directly into a save operation**, and clearly determining which data is decided by the client and which by the server.

## 4. Runnable Spring Boot MVC Example: Creating a Workshop Registration

The example uses **Java 17**, **Spring Boot 3.4.3** (Spring Framework 6), Maven, Bean Validation, and an endpoint accepting URL-encoded HTML forms. To focus on DTOs and binding, the service returns an in-memory calculated receipt, **without database persistence, authentication, or payment**. ID generation and entity persistence would be added in a real system.

File structure:

```text
registration-demo/
├── pom.xml
└── src/main/java/demo/registration/
    ├── RegistrationDemoApplication.java
    ├── CreateRegistrationForm.java
    ├── CreateRegistrationCommand.java
    ├── RegistrationReceipt.java
    ├── RegistrationService.java
    └── RegistrationController.java
```

### 4.1. Declaring Dependencies

**`pom.xml`**

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.3</version>
        <relativePath/>
    </parent>

    <groupId>demo</groupId>
    <artifactId>registration-demo</artifactId>
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

`spring-boot-starter-web` provides Spring MVC and an embedded server; `spring-boot-starter-validation` provides a Bean Validation provider so annotations such as `@NotBlank`, `@Email`, and `@Min` are actually enforced. With Spring Framework 6, use the `jakarta.validation` namespace instead of `javax.validation` from older versions.

### 4.2. Entry Point

**`src/main/java/demo/registration/RegistrationDemoApplication.java`**

```java
package demo.registration;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RegistrationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RegistrationDemoApplication.class, args);
    }
}
```

### 4.3. Form Object with Only Three Editable Fields

**`src/main/java/demo/registration/CreateRegistrationForm.java`**

```java
package demo.registration;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public class CreateRegistrationForm {
    @NotBlank
    @Size(max = 80)
    private String attendeeName;

    @NotBlank
    @Email
    @Size(max = 120)
    private String email;

    @NotNull
    @Min(1)
    @Max(5)
    private Integer seats;

    public String getAttendeeName() {
        return attendeeName;
    }

    public void setAttendeeName(String attendeeName) {
        this.attendeeName = attendeeName;
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
}
```

This is a JavaBean with a default no-arg constructor. Spring MVC can use setters to bind form parameters whose names match the properties: `attendeeName`, `email`, `seats`. Using `Integer` instead of `int` distinguishes **an omitted field** (`null`, caught by `@NotNull`) from **sending the value 0** (caught by `@Min(1)`). With `seats=abc`, Spring cannot convert the string to `Integer` and records a type conversion error during binding.

These annotations only address input structure and format errors. They do not verify whether the workshop still has available seats, whether the user is allowed to book on someone else's behalf, or what the current price is; those conditions belong to the service/domain layer and require trusted data sources.

### 4.4. Command and Response Separated from the Form

**`src/main/java/demo/registration/CreateRegistrationCommand.java`**

```java
package demo.registration;

public record CreateRegistrationCommand(
        String attendeeName,
        String email,
        int seats) {
}
```

**`src/main/java/demo/registration/RegistrationReceipt.java`**

```java
package demo.registration;

public record RegistrationReceipt(
        String attendeeName,
        int seats,
        int totalVnd,
        String status) {
}
```

Java `record` is well suited for immutable data in the sense that its components cannot be reassigned after initialization. It is not a JPA entity and does not need setters. `CreateRegistrationCommand` describes the service input mapped from the form; `RegistrationReceipt` describes the exact fields returned to the client.

### 4.5. Service Retaining Authority over Price and Status

**`src/main/java/demo/registration/RegistrationService.java`**

```java
package demo.registration;

import org.springframework.stereotype.Service;

@Service
public class RegistrationService {
    private static final int PRICE_PER_SEAT_VND = 250_000;

    public RegistrationReceipt create(CreateRegistrationCommand command) {
        if (command.seats() < 1 || command.seats() > 5) {
            throw new IllegalArgumentException("seats must be between 1 and 5");
        }

        int total = command.seats() * PRICE_PER_SEAT_VND;
        return new RegistrationReceipt(
                command.attendeeName(),
                command.seats(),
                total,
                "PENDING");
    }
}
```

Price and status are not read from the HTTP request; therefore the client cannot alter them by adding extra fields to the form. Checking the seat count in the service expresses a minimal business invariant even if the service is invoked from another source that bypasses the controller. In a real system, price might be a `BigDecimal` paired with a currency and looked up from configuration or a database; the demo uses whole VND and `int` because the value range here is very small.

### 4.6. Controller: Binding, Validation, Allowlist, and Explicit Mapping

**`src/main/java/demo/registration/RegistrationController.java`**

```java
package demo.registration;

import java.util.List;
import java.util.Map;
import java.util.Objects;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/registrations")
public class RegistrationController {
    private final RegistrationService service;

    public RegistrationController(RegistrationService service) {
        this.service = service;
    }

    @InitBinder("registrationForm")
    void restrictFormFields(WebDataBinder binder) {
        binder.setAllowedFields("attendeeName", "email", "seats");
    }

    @PostMapping(consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE)
    public ResponseEntity<?> create(
            @Valid @ModelAttribute("registrationForm") CreateRegistrationForm form,
            BindingResult bindingResult) {

        if (bindingResult.getSuppressedFields().length > 0) {
            return ResponseEntity.badRequest()
                    .body(Map.of("error", "Unexpected form fields"));
        }

        if (bindingResult.hasErrors()) {
            List<Map<String, String>> errors = bindingResult.getFieldErrors()
                    .stream()
                    .map(error -> Map.of(
                            "field", error.getField(),
                            "message", Objects.toString(
                                    error.getDefaultMessage(), "Invalid value")))
                    .toList();

            return ResponseEntity.badRequest()
                    .body(Map.of("errors", errors));
        }

        CreateRegistrationCommand command = new CreateRegistrationCommand(
                form.getAttendeeName().strip(),
                form.getEmail().strip(),
                form.getSeats());

        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(command));
    }
}
```

Key decisions in the controller:

1. `@ModelAttribute("registrationForm")` instructs Spring to create/bind the object from request parameters, fitting `application/x-www-form-urlencoded`; the name `registrationForm` is also referenced by `@InitBinder`.
2. `@InitBinder("registrationForm")` restricts **setter/property binding** to those exact three fields. `getSuppressedFields()` indicates whether any field names were excluded from binding; the demo endpoint proactively returns `400` if the client sends fields outside the contract.
3. `@Valid` runs Bean Validation after binding. `BindingResult` **must appear immediately after** the form parameter for the controller to handle binding and validation errors. If `BindingResult` is omitted, Spring MVC typically reports errors through request-handling exceptions.
4. The controller maps each field explicitly into `CreateRegistrationCommand`. Avoid mechanisms that copy all properties between a request object and an entity if doing so could leak disallowed properties.
5. `.strip()` removes leading and trailing whitespace after the data has passed validation; it does not silently turn invalid input into valid input. In a real system, normalization before validation can follow a clear policy while avoiding silently altering the meaning of a user's email.
6. The response is a separate DTO. Do not return an entity directly that contains internal data or lazy-loaded relationships.

**Note:** If a request contains extra keys without an allowlist, the form object in this example still has no setters for `status`/`totalVnd`, but declaring allowed fields makes the design intent explicit and prevents unintended write access when the class grows. With constructor binding variants, constructor parameters must be evaluated separately; `setAllowedFields` primarily protects property binding.

## 5. Running and Verifying Output

In the `registration-demo` directory, with JDK 17+ and Maven installed:

```bash
mvn spring-boot:run
```

The application listens on port `8080` by default, provided that port is not already in use by another application. In another terminal (using `curl.exe` in Windows PowerShell or `curl` in Bash), send valid form data:

```bash
curl -i -X POST "http://localhost:8080/registrations" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "attendeeName=Lan Nguyen" --data-urlencode "email=lan@example.com" --data-urlencode "seats=2"
```

**HTTP status:** `201 Created`. **JSON body:**

```json
{
  "attendeeName": "Lan Nguyen",
  "seats": 2,
  "totalVnd": 500000,
  "status": "PENDING"
}
```

This is a deterministic result from `2 × 250000 = 500000`, independent of any price sent by the client. The actual order of JSON properties or headers may vary depending on the serializer, but the values above are what should be verified.

Try sending a seat count beyond the limit:

```bash
curl -i -X POST "http://localhost:8080/registrations" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "attendeeName=Lan Nguyen" --data-urlencode "email=lan@example.com" --data-urlencode "seats=9"
```

The result is **HTTP 400** with `errors` containing an error for the `seats` field (`@Max(5)` constraint); the exact message text may vary by locale and Bean Validation provider.

Try *overposting*:

```bash
curl -i -X POST "http://localhost:8080/registrations" -H "Content-Type: application/x-www-form-urlencoded" --data-urlencode "attendeeName=Lan Nguyen" --data-urlencode "email=lan@example.com" --data-urlencode "seats=2" --data-urlencode "status=APPROVED"
```

The result is **HTTP 400** because `status` is not in `allowedFields`, body:

```json
{"error":"Unexpected form fields"}
```

Trying `seats=abc` produces a *type mismatch* error; omitting `email` produces a `@NotBlank` error. Both cases must return `400` and must not invoke the service to create a receipt.

Note: the demo returns an in-memory receipt and does not persist registrations. When connecting a database, the service must check remaining seats and record the data within an appropriate transaction; do not infer from the `201` JSON in the demo that a durable record was saved.

## 6. How Does the Design Differ for JSON Input?

The task is still **creating a registration**, but the transport differs:

| HTML form | JSON API |
| --- | --- |
| `Content-Type: application/x-www-form-urlencoded` | `Content-Type: application/json` |
| `@ModelAttribute` + `WebDataBinder` | `@RequestBody` + `HttpMessageConverter` (usually Jackson) |
| JavaBean with setters or constructor-bound object | `record`/class supported by the JSON deserializer |
| `BindingResult` can follow the form parameter immediately | `@Valid` also works on `@RequestBody`; errors are handled via an exception handler or appropriate `Errors` |
| `@InitBinder.setAllowedFields` restricts property binding | Does not automatically restrict JSON deserialization; use a strict request DTO and Jackson policies |

Example of an **illustrative signature, not a standalone controller**:

```java
public record CreateRegistrationJson(
        @jakarta.validation.constraints.NotBlank String attendeeName,
        @jakarta.validation.constraints.Email
        @jakarta.validation.constraints.NotBlank String email,
        @jakarta.validation.constraints.NotNull
        @jakarta.validation.constraints.Min(1)
        @jakarta.validation.constraints.Max(5) Integer seats) {
}

@PostMapping(path = "/registrations-json",
             consumes = MediaType.APPLICATION_JSON_VALUE)
public ResponseEntity<RegistrationReceipt> createJson(
        @Valid @RequestBody CreateRegistrationJson request) {
    var command = new CreateRegistrationCommand(
            request.attendeeName(),
            request.email(),
            request.seats());
    return ResponseEntity.status(HttpStatus.CREATED)
            .body(service.create(command));
}
```

This snippet fits into a controller that has `service` and the appropriate imports. It illustrates an immutable record for a JSON request. If validation fails without an accompanying `Errors`/`BindingResult`, Spring MVC can return `400` through its default exception-handling mechanism. The exception type may differ if the endpoint also has constraints requiring method validation.

If you want to **reject JSON keys not present in the DTO**, explicitly configure an unknown-properties policy (for example, Jackson `FAIL_ON_UNKNOWN_PROPERTIES` at the appropriate scope). Merely omitting the `status` field from the DTO does not guarantee the server will return `400` when the client sends it: a JSON deserializer may ignore unknown properties depending on its configuration. The invariant is never transferring ignored fields into an entity or business command.

## 7. Principles for Choosing Data Types and Validation Boundaries

### 7.1. Choosing Java Types That Match Input Values

- Use `Integer` when you need to represent "not provided" as `null`; combine `@NotNull` with `@Min`/`@Max`. Use `int` when the input is guaranteed to have a value after a controlled initialization step.
- Use `String` for emails, names, and codes with leading zeros or formatting that must be preserved. Avoid treating an email or phone number as a `long`.
- Use `LocalDate` for date-only values, and `Instant`/`OffsetDateTime` when a point in time is needed; configure `@DateTimeFormat`/`Formatter` for HTML forms if the input format is non-default.
- Use `BigDecimal` for money with fractional units and explicit rounding rules. Amounts, discounts, permissions, and server-controlled statuses should generally **not be writable client inputs**.
- For finite sets of values, you can use an `enum`, while considering the response when a client sends an unsupported value and API compatibility when adding new states.

### 7.2. Distinguishing Three Kinds of Checks

1. **Binding/conversion:** can `"2"` be turned into an `Integer`? `"abc"` causes a type mismatch before a valid numeric object exists.
2. **Input validation:** `@NotBlank`, `@Size`, `@Email`, `@Min`, `@Max` determine whether an input object satisfies the syntactic/structural contract.
3. **Business validation/authorization:** does the workshop still have space, which registration is the caller allowed to modify, and what is the current price? These checks rely on server state and trusted identity and usually live in the service/domain layer.

Do not cram all three kinds into a single DTO, and do not treat `@Valid` as an authorization mechanism or a guarantee that data is safe for every business operation.

### 7.3. DTOs Containing Nested Structures

If a form contains a list of attendees, one design can use `List<AttendeeForm> attendees`, where each element has its own constraints. Use `@Valid` on the nested field to trigger cascade validation and `@Size(max=...)` to limit the number of elements. With property-path binding such as `attendees[0].name`, you must bound structural size/depth and consider `autoGrowCollectionLimit` so user-submitted data cannot create an oversized object graph.

Only add nested structures when the task genuinely requires them; in the workshop example where only seat count is entered, `int seats` is far simpler than inventing a hypothetical attendee list.

## 8. Different Designs for Create, Update, PATCH, and Cancel

| Task | Suggested Input Object | Meaning of Fields |
| --- | --- | --- |
| Create registration | `CreateRegistrationForm` | Name, email, seat count required; no ID/status |
| Change contact email | `ChangeRegistrationEmailRequest` | Only the new email; ID comes from path or context and ownership is verified |
| Adjust seat count | `ChangeSeatCountRequest` | Only the new seat count; checks remaining availability and change conditions |
| Cancel registration | `CancelRegistrationRequest` | Cancellation reason (if needed); cancelled status is determined by the service |
| Partial update | `PatchRegistrationRequest` or dedicated patch model | Must distinguish an absent field from a request to clear a field |

**Do not reuse a creation DTO for PATCH.** With many deserializers, both missing JSON fields and JSON fields assigned `null` can yield a Java `null` value. If business logic needs to distinguish "keep unchanged" from "clear", the design must carry **field-presence information**: a patch structure with flags, an appropriate wrapper, or JSON Patch/Merge Patch with clearly defined conventions.

For editing an existing entity, the typical sequence is: take the ID from the route, authenticate the user, load the entity, verify authorization, validate the update contract, and then apply **the properties permitted to be modified**. Do not bind all request parameters onto an existing managed JPA entity and immediately call `save`.

## 9. When to Use a JavaBean, Constructor Binding, or Record?

- **JavaBean with setters:** straightforward for traditional HTML forms with `@ModelAttribute` and form validation. When using property binding, declare an `allowedFields` set and do not add setters for protected fields.
- **Constructor binding / immutable DTO:** appropriate when fields are determined at object construction time, avoiding public setters. Spring MVC supports binding via constructors, including many record-like types, provided parameter names are preserved in bytecode and type conversion rules match.
- **Record for JSON request/response:** concise, immutable at the field-reference level, and well suited for data transfer. However, a record does not prevent mutable component objects from being mutated and is not mandatory for every form.
- **Entity:** holds business logic and lifecycle; avoid using it as a request DTO that HTTP data can bind to directly.

Spring MVC supports **declarative binding** configuration and constructor binding to reduce the surface area of setter binding. In versions or configurations that still use property binding, restrict allowed fields and inspect unexpected requests. Never rely on only rendering a few inputs in the HTML UI: a requester can submit any parameter they want.

## 10. Common Design Mistakes

| Mistake | Harm | Fix |
| --- | --- | --- |
| Using `RegistrationEntity` directly as a `@ModelAttribute` parameter | Easily binds ID, status, price, or JPA relationships by mistake | Create a task-specific form/DTO and map fields explicitly |
| Using one giant DTO for create/update/cancel | Many nullable fields, unclear write permissions | Create separate inputs per use case |
| Trusting price and status sent by the client | Client can manipulate money/status | Determine them on the server and exclude from writable input |
| Relying only on HTML `readonly`/`hidden` to protect fields | Forged requests can still send arbitrary values | Enforce on the server via DTOs and a binding whitelist |
| Using `int` for a required field when presence must be detected | Cannot distinguish missing input from default value | `Integer` + `@NotNull` |
| Forgetting `@Valid` or the validation provider dependency | Annotations may never be triggered | Add a Bean Validation provider and enable validation |
| Placing `BindingResult` away from the form parameter | Controller does not receive errors through the expected path | Place it immediately after `@Valid @ModelAttribute` |
| Assuming `@InitBinder.setAllowedFields` also handles JSON | Wrong mechanism: JSON usually goes through `HttpMessageConverter` | Use a dedicated request DTO and Jackson configuration |
| Copying all request properties into an entity via reflection | Overwrites out-of-contract fields, hard to control | Map explicitly or use a mapper with a restricted field list |
| Treating input validation as authorization | Users can still modify someone else's resources | Authenticate and check permissions in the service |
| Equating an omitted field in PATCH with null | Unintentionally clears or overwrites data | Design a patch contract with presence semantics |
| Returning an entity directly in the response | Data leaks, lazy-loading errors, and unintended API changes | Use a dedicated response DTO |

## 11. Checklist When Designing an Input Object for a New Task

1. Write one sentence describing **who performs what action**, on which target; determine whether the task is create, update, cancel, or search.
2. List each field the client is **allowed to provide**; separate fields generated or computed by the server.
3. Choose field names, types, length/range limits, required rules, and the meaning of absence.
4. Choose the appropriate intake mechanism: HTML form via `@ModelAttribute` or JSON via `@RequestBody`. Design an allowlist or constructor binding when needed.
5. Use `@Valid` and handle conversion errors and validation errors; do not call the service when input is invalid.
6. Map explicitly to a command/domain operation; the service verifies permissions, state, inventory/seat availability, price, and business invariants.
7. Return a response DTO containing only the data meant to be exposed; do not serialize entities blindly.
8. Test valid requests, missing fields, wrong types, out-of-bounds values, disallowed fields, another user's ID, repeated requests, concurrency, and the difference between missing and null on updates.
9. Review the contract when task requirements change; never add sensitive fields directly into a form object that is automatically bound.

**Takeaway:** A good input DTO answers three questions: *what is the task*, *what is the client allowed to send*, and *what will the server control*. A form object is the data-intake contract; an entity is the business model; a response DTO is the data-output contract. Keeping these three roles distinct makes Spring Data Binding easier to control, places validation in the right layer, and reduces overposting bugs.

## 12. Official Documentation

- [Spring MVC — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html): how model attribute binding, constructor/property binding, `BindingResult`, and `@Valid` work.
- [Spring MVC — Data Binding](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html): binding modes, `allowedFields`, declarative binding, and model design.
- [Spring MVC — @InitBinder](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-initbinder.html): configuring binders per controller and model attribute.
- [Spring MVC — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html): JSON via `HttpMessageConverter`.
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): constraints, `jakarta.validation`, and validator integration.
- [Spring MVC — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html): controller argument validation and method validation cases.