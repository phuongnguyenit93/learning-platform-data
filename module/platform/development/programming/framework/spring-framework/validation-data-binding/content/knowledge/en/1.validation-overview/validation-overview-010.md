# Learning roadmap from raw input to a valid object in Spring Framework

When a Spring application receives an HTTP request, the initial data is merely strings in the URL, form fields, or JSON bytes. Nothing guarantees the sender supplied the right types, all required fields, valid values, or has permission to perform the action. The ingestion layer's job is to turn that raw data into a structured Java object, check input rules, and forward only conforming requests to business logic.

**Goal of this guide:** see the full journey from HTTP request → argument resolution → data binding/type conversion → validation → error handling → business execution; distinguish the verification layers often lumped together as "validation"; know how to learn and test each stage. "Valid object" here means **an input object valid per the API contract**, not automatically a business entity permitted to be persisted.

## 1. Overall map

```text
Client sends HTTP request
  │  Path/query/form are text; JSON is the HTTP body content
  ▼
Spring MVC: DispatcherServlet selects handler/controller
  ▼
Controller method argument resolution
  ├─ @RequestParam / @PathVariable: extract single values from request
  ├─ @ModelAttribute: bind query/form fields into an object
  │                   via WebDataBinder and conversion mechanisms
  └─ @RequestBody: read body via HttpMessageConverter
                  (e.g., Jackson converts JSON into a Java object)
  ▼
Java object/parameter created and type-converted
  ▼
Input checks when configured/triggered
  ├─ JSON read or type conversion error: desired input could not be built
  ├─ @Valid / Jakarta Bean Validation: check constraints on the DTO
  └─ Errors returned to client or collected into appropriate BindingResult
  ▼
Controller → service/domain
  ├─ Check business rules, access permissions, current state
  ├─ Perform valid operation; protect data invariants
  └─ Persist data when needed
  ▼
HTTP response (success or structured error)
```

This is a **mental map**, not a fixed internal sequence for every parameter type. For instance, `@RequestBody` uses a message converter to decode JSON; `@ModelAttribute` uses data binding for query/form data. Do not think every request goes through the exact same converter.

## 2. Four questions to answer at each stage

| Stage | Question | Example | If it fails |
| --- | --- | --- | --- |
| Reading data | Can the request be read/decoded? | JSON is missing a closing brace | Body-read error, typically HTTP 400 |
| Binding/type conversion | Can the value convert to the target Java type? | `page=abc` needs `Integer` | Type conversion/binding error |
| Input constraint checks | Do the Java values satisfy the DTO contract? | Blank email, age below minimum | Validation error, typically HTTP 400 in APIs |
| Business checks | Is the action allowed in the current state? | Email already exists, user edits another user's resource | Service/domain rejects per rules; HTTP status depends on case |

First you must *construct Java values*, and only then can constraints on those values be checked. Yet "passed `@Valid`" does not mean the data's origin is authenticated, the caller is authorized, or no database conflicts exist.

## 3. Receiving the right data types before validating

### 3.1. URLs, query parameters, and forms

For example, `GET /products?page=2` carries the string `"2"`. If the controller declares `@RequestParam Integer page`, Spring must convert that string to an integer before calling the method. `page=abc` cannot convert to a valid `Integer`.

For multiple related fields, `@ModelAttribute` can bind query/form data into an object like `SearchForm` containing `keyword`, `page`, and `sort`. Spring MVC uses `WebDataBinder` paired with conversion mechanisms like `ConversionService` and `Converter`/`Formatter`. Dates, numbers, and locale-specific formatting may need configuration or matching annotations such as `@DateTimeFormat`.

For MVC forms, declaring `@Valid @ModelAttribute SearchForm form, BindingResult errors` (placing `BindingResult` **immediately after** the parameter being checked) lets the controller inspect binding/validation errors and redisplay the form with specific messages. `BindingResult` is not a global variable usable for arbitrary parameters.

### 3.2. JSON request body

With `Content-Type: application/json` and `@RequestBody RegistrationRequest request`, Spring MVC selects an appropriate `HttpMessageConverter`; in typical Jackson setups, JSON is decoded into a Java DTO. Example:

```json
{
  "name": "Lan",
  "email": "lan@example.com",
  "age": 20
}
```

If JSON has syntax errors, a field cannot be decoded into the target type, or the body is unreadable, failure occurs **before** constraints like `@Min` can inspect a complete DTO. In Spring MVC, a typical body-read failure is `HttpMessageNotReadableException` and is commonly handled as HTTP 400.

**Key distinction:** `@RequestBody` asks to read/decode the body; `@Valid` asks to check constraints on the object after decoding succeeds. Using only one of these annotations does not automatically perform both jobs.

## 4. From Java object to valid DTO

Jakarta Bean Validation describes constraints using annotations on Java objects. When a validation implementation (such as Hibernate Validator) is present, Spring can trigger them via `@Valid` or an appropriate validation mechanism.

| Constraint | What is checked | What is **not** guaranteed |
| --- | --- | --- |
| `@NotNull` | Value is not `null` | Non-empty string |
| `@NotBlank` | String is not `null` and has a non-whitespace character | String has been normalized/trimmed of extra spaces |
| `@Size(min=..., max=...)` | String length/collection size is within bounds | Business meaning |
| `@Email` | String matches the validator's email format rule | Email exists or belongs to the user |
| `@Min(18)` | Numeric value is at least 18 | Value is not `null` |
| `@Valid` on nested field | Requests descending into the nested object | Nested object is required to exist without `@NotNull` |

Two constraints often need to be combined: `@NotBlank @Email String email` to require input and check format; `@NotNull @Min(18) Integer age` to require an age and check its minimum. Using `Integer` instead of `int` distinguishes "age omitted" (`null`) from the number 0.

In Spring Boot 3 / Spring Framework 6, use the **`jakarta.validation.*`** namespace, not the older generation's `javax.validation.*`. For Spring Boot applications with Bean Validation, the standard dependency is `spring-boot-starter-validation`; `spring-boot-starter-web` provides Spring MVC and standard JSON support.

## 5. Hands-on example: an endpoint receiving JSON, binding types, and validating a DTO

Assume a Spring Boot project targeting Java 17+ with Spring Boot plugins and dependency management enabled. Add the corresponding dependencies in the project's `build.gradle`:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Create `src/main/java/demo/validation/ValidationDemoApplication.java` with the full contents below. The `record`s and controller in the same file use package-private access; the filename matches the `public` class:

```java
package demo.validation;

import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class ValidationDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(ValidationDemoApplication.class, args);
    }
}

record RegistrationRequest(
        @NotBlank String name,
        @NotBlank @Email String email,
        @NotNull @Min(18) Integer age
) {}

record RegistrationResponse(String name, String email) {}

@RestController
@RequestMapping("/registrations")
class RegistrationController {
    @PostMapping
    ResponseEntity<RegistrationResponse> register(
            @Valid @RequestBody RegistrationRequest request) {
        // Illustrative result only; does not persist an account in a database yet.
        RegistrationResponse response =
                new RegistrationResponse(request.name(), request.email());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

Run the application with `./gradlew bootRun` in the configured Spring Boot project, or via the equivalent IDE run configuration. Send a valid request:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"Lan","email":"lan@example.com","age":20}'
```

On default port 8080, the expected response has status **201 Created** and the corresponding JSON body:

```json
{"name":"Lan","email":"lan@example.com"}
```

Following each stage: Spring locates `register` → Jackson builds `RegistrationRequest` from JSON → Bean Validation checks name/email/age because of `@Valid` → the controller runs only if those checks pass → the app constructs `RegistrationResponse`. The example does not yet persist data or check duplicate emails, so it is not a complete user registration flow.

Try a body that violates the contract:

```bash
curl -i -X POST http://localhost:8080/registrations \
  -H 'Content-Type: application/json' \
  -d '{"name":"   ","email":"not-an-email","age":16}'
```

This JSON is **readable** and builds a DTO, yet `@NotBlank`, `@Email`, and `@Min` all fail. In typical Spring MVC, validation on `@Valid @RequestBody` triggers `MethodArgumentNotValidException` and **HTTP 400 Bad Request**. The default error JSON shape depends on the Spring Boot version and application error handling configuration; do not assume a fixed default body structure.

To observe a different failure stage, try `"age":"abc"`: Jackson cannot convert a non-numeric string into `Integer`, so the request is typically rejected at the read/conversion step before checking `@Min`. If `age` is omitted completely, `Integer age` can be `null` and is rejected by `@NotNull` during Bean Validation.

## 6. Where are validation errors handled?

**JSON API path:** When a controller declares `@Valid @RequestBody` and does not capture errors itself, Spring MVC usually returns HTTP 400 for requests failing DTO constraints. You can use `@RestControllerAdvice` and `@ExceptionHandler` to build a consistent error shape, such as error code, a list of `field`/`message`, and a trace ID. Avoid dumping all user-submitted data into logs or responses, especially sensitive information.

**MVC form path:** When using `@Valid @ModelAttribute` with `BindingResult` placed right after the object, the controller can check `errors.hasErrors()` and redisplay the form. This fits input UIs needing field-level highlights. If not handled directly, how Spring turns errors into responses depends on the method signature, configuration, and endpoint style.

When designing error responses, distinguish at least three cases:

1. **Unreadable body/type conversion failed:** explain the expected syntax or data type; avoid misreporting it as a business rule violation.
2. **DTO failed constraints:** point out the field and public rule without leaking secrets or sensitive values.
3. **Business rejection:** return an appropriate error such as conflict or forbidden; HTTP codes and payloads must follow the API contract.

Do not rely on the ordering of validation messages when writing tests, as constraint evaluation order is not a stable contract.

## 7. A valid DTO is still not a valid business state

Suppose JSON has a well-formed email and age at least 18. These questions are **not** answered by simple Bean Validation: is the email already registered, does the caller have permission to create an account for this organization, is the account currently locked, or has a rate limit been exceeded?

Checks depending on databases, identity, and business rules belong to the service/domain alongside the application's security mechanisms. If two requests simultaneously register the same email, merely checking "does not exist" before writing is not enough to prevent races; a database unique constraint and conflict handling remain necessary.

Do not use a persistence entity as `@RequestBody` just for binding convenience: clients could try sending internal fields like `id`, `role`, or `status` that the API never intended to expose for updates. An input DTO declares only fields the client is allowed to supply; the application layer decides how to map onto domain objects. With form binding, pay special attention to properties bindable by field name and configure binding restrictions appropriately to avoid accepting extra fields.

## 8. Step-by-step learning and verification roadmap

| Learning step | What to master | Self-check experiment |
| --- | --- | --- |
| 1. HTTP data sources | Distinguish path, query, form, JSON body, and content types | Change a JSON body to syntactically invalid JSON |
| 2. Argument resolution | Pick `@RequestParam`, `@PathVariable`, `@ModelAttribute`, `@RequestBody` properly | Change query `page=2` to `page=abc` |
| 3. Binding and type conversion | Target Java types, converters/formatters, failures on unconvertible values | Change `age` from a number to alphabetic text |
| 4. Bean Validation | `@Valid`, constraints, nested validation, how validators are triggered | Drop `age`, then set `name` to spaces only |
| 5. Error responses | Distinguish read errors, binding errors, constraint errors, and business errors | Observe HTTP status and check whether controller ran |
| 6. Business boundaries | DTO vs. entity; authorization, state, and persistence consistency | Propose where to check duplicate emails and unique constraints |
| 7. Contract testing | Success, missing fields, wrong types, constraint violations | Write MVC tests asserting 201/400 and no sensitive data leakage |

**Quick review method:** for every request, trace in order: where does data come from → how does Spring decode/bind it and into which type → which constraints run → if it fails, where does it stop → if it passes, what must business logic still check. If you can trace this chain for both JSON and forms, you have the foundation to dive deeper into data binding, conversion, Bean Validation, and exception handling in Spring.

## 9. Common misconceptions

- **Thinking `@RequestBody` performs validation:** this annotation handles reading the body; `@Valid` plus Bean Validation infrastructure are needed to evaluate DTO constraints.
- **Thinking `@Valid` turns any string into the right type:** JSON/type conversion errors can happen before the object is validated.
- **Using only `@Email` to require an email:** combine with `@NotBlank` when the field is required.
- **Using `int` for fields needing to distinguish "omitted":** consider `Integer` and `@NotNull` for clearer feedback.
- **Mistakenly using `javax.validation` in Spring Boot 3:** use `jakarta.validation` and ensure a compatible provider is present.
- **Assuming a request passing validation is cleared to write to the DB:** authentication/authorization, domain rules, and data constraints are still required.
- **Assuming every error yields the same exception or default JSON:** distinguish message conversion, binding, constraint, and business errors; standardize the application's error contract.
- **Letting clients bind directly into entities:** use input DTOs to explicitly define accepted fields.

**Self-assessment:** For `POST /registrations`, JSON `{"name":"Lan","email":"lan@example.com","age":"unknown"}` fails at decoding/type conversion; JSON `{"name":" ","email":"lan@example.com","age":20}` creates a DTO but fails `@NotBlank`; fully valid JSON only qualifies to enter the controller, where the service must still decide whether the operation may proceed.
