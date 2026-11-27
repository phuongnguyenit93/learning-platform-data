# Documenting form validation errors with Spring REST Docs

## 1. Why document form errors?

A REST API that accepts form data does not only produce successful responses. Clients also need to know how the server responds when a required field is missing, an email is malformed, a value is outside the allowed set, or data cannot be converted to the target Java type. If the documentation only covers valid requests and `201 Created` responses, integrators are left guessing how to handle rejected forms.

In the **SPRING_REST_DOCS** module, REST API documentation is generated from HTTP tests using MockMvc, WebTestClient, or REST Assured. For `application/x-www-form-urlencoded` forms, Spring REST Docs can generate parameter snippets with `formParameters(...)` while documenting error responses with `responseFields(...)`, `responseHeaders(...)`, and the corresponding HTTP snippets. Passing tests provide evidence that the documentation reflects the endpoint's actual behavior.

This lesson builds a form-based registration endpoint, standardizes validation errors into a consistent JSON format, and writes tests that generate documentation for both valid and invalid requests.

After this lesson, you will be able to:

1. Distinguish binding errors, validation errors, and business errors.
2. Use Jakarta Bean Validation to validate form data bound to a DTO.
3. Standardize errors via `@RestControllerAdvice` without leaking sensitive data.
4. Use MockMvc to assert status codes, error response structure, and generate Spring REST Docs snippets.
5. Embed error snippets in Asciidoctor/Markdown and integrate verification into CI.

## 2. Types of errors when receiving forms

Suppose the `POST /registrations` endpoint receives the body:

```http
POST /registrations HTTP/1.1
Content-Type: application/x-www-form-urlencoded; charset=UTF-8
Accept: application/json

email=mai%40example.com&plan=pro&seats=2
```

| Error type | Example | Where typically detected |
| --- | --- | --- |
| Missing required field | `email` omitted | Binding or Bean Validation, depending on configuration |
| Empty value | `email=` | `@NotBlank` |
| Invalid format | `email=mai-at-example` | `@Email` |
| Outside allowed set | `plan=enterprise` when only `basic`/`pro` are accepted | `@Pattern` or business validation |
| Out of numeric range | `seats=0` when 1 to 5 is required | `@Min` / `@Max` |
| Wrong data type | `seats=two` for an integer property | Type conversion/binding |
| Cross-field rule violation | End date before start date | Business validator or service layer |

Distinguish clearly between:

- **Binding/conversion:** converting form strings into Java properties. For example, `seats=two` cannot be converted to an `Integer`.
- **Validation:** checking bound values, such as `seats` being less than 1 or a malformed email.
- **Business rule:** conditions depending on system state, such as an expired promo code or an already registered account.

Different error categories can surface at different stages, so do not assume all of them are handled by the same exception. This lesson focuses on Bean Validation errors to keep the example clear; the end outlines how to extend handling for binding and business errors.

## 3. Designing the error response contract

A good error response has a stable structure so clients can handle it programmatically. Example:

```http
HTTP/1.1 400 Bad Request
Content-Type: application/json

{
  "code": "VALIDATION_FAILED",
  "message": "Form data is invalid",
  "errors": [
    {
      "field": "email",
      "code": "INVALID_FORMAT",
      "message": "Invalid email format"
    },
    {
      "field": "seats",
      "code": "OUT_OF_RANGE",
      "message": "Quantity must be between 1 and 5"
    }
  ]
}
```

| Property | Purpose |
| --- | --- |
| `code` | Request-level error code, stable for client branching |
| `message` | General human-readable message |
| `errors` | List of field-level errors |
| `errors[].field` | Field name in the form |
| `errors[].code` | Machine-readable error code for the field |
| `errors[].message` | Message explaining the field error |

Choosing `400 Bad Request` or `422 Unprocessable Content` is an API contract decision; what matters is consistent usage and clear documentation. The examples below use `400` for validation errors. If your system uses `422`, update tests and documentation to match the chosen status rather than mixing both.

Do not include user-submitted values in error responses by default. Input data can contain passwords, tokens, identification numbers, or personal information. A clear field name, error code, and message typically satisfy client needs.

## 4. Creating a form DTO with Jakarta Bean Validation

To bind a URL-encoded form into a group of fields, Spring MVC can use `@ModelAttribute` with a DTO. The DTO provides getters/setters for the binder to assign values and validation annotations to check them after binding.

```java
package example.docs;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

public class RegistrationForm {
    @NotBlank(message = "Email must not be blank")
    @Email(message = "Invalid email format")
    private String email;

    @NotBlank(message = "Subscription plan must not be blank")
    @Pattern(regexp = "basic|pro",
        message = "Subscription plan accepts only basic or pro")
    private String plan;

    @NotNull(message = "Quantity is required")
    @Min(value = 1, message = "Quantity must be between 1 and 5")
    @Max(value = 5, message = "Quantity must be between 1 and 5")
    private Integer seats;

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }
    public String getPlan() { return plan; }
    public void setPlan(String plan) { this.plan = plan; }
    public Integer getSeats() { return seats; }
    public void setSeats(Integer seats) { this.seats = seats; }
}
```

A few points to note:

- `@NotBlank` rejects `null`, empty strings, and whitespace-only strings.
- `@Email` checks email address syntax according to the configured validator; it does not verify mailbox existence. Combine it with `@NotBlank` because `@Email` typically treats empty values as valid.
- `@Pattern` restricts `plan` to two values; the regular expression is case-sensitive.
- `@Min` and `@Max` validate the numeric range of `seats`. `@NotNull` ensures the field is present; using `Integer` allows representing absence as `null`.

## 5. Standardizing errors with `@RestControllerAdvice`

### 5.1. Error response types

Each public top-level Java type should reside in its own file:

```java
// FieldViolation.java
package example.docs;

public record FieldViolation(String field, String code, String message) {
}
```

```java
// ValidationErrorResponse.java
package example.docs;

import java.util.List;

public record ValidationErrorResponse(
        String code,
        String message,
        List<FieldViolation> errors) {
}
```

### 5.2. Exception handler

```java
package example.docs;

import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.validation.FieldError;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiValidationExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ValidationErrorResponse> handleValidation(
            MethodArgumentNotValidException exception) {
        List<FieldViolation> violations =
                exception.getBindingResult().getFieldErrors()
                    .stream()
                    .map(this::toViolation)
                    .toList();

        ValidationErrorResponse body = new ValidationErrorResponse(
                "VALIDATION_FAILED",
                "Form data is invalid",
                violations);
        return ResponseEntity.status(HttpStatus.BAD_REQUEST).body(body);
    }

    private FieldViolation toViolation(FieldError error) {
        String code = switch (error.getCode() == null ? "" : error.getCode()) {
            case "NotBlank", "NotNull" -> "REQUIRED";
            case "Email" -> "INVALID_FORMAT";
            case "Min", "Max" -> "OUT_OF_RANGE";
            case "Pattern" -> "INVALID_VALUE";
            default -> "INVALID_VALUE";
        };
        return new FieldViolation(
                error.getField(),
                code,
                error.getDefaultMessage() == null
                        ? "Invalid value"
                        : error.getDefaultMessage());
    }
}
```

The handler maps Bean Validation errors to stable API error codes. Clients should not depend directly on exception class names or internal validator codes such as `NotBlank`, as those details can change across libraries or configurations. The mapping can be extended for new constraints and business rules.

Messages in the example are written in English for illustration. Multilingual applications should use a message source/locale while keeping `code` stable. Do not include `FieldError.getRejectedValue()` in the response without a clear reason.

### 5.3. Form-handling controller

Add the validation dependency if the Spring Boot project does not already have it:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
```

Controller and response DTO:

```java
// RegistrationResponse.java
package example.docs;

public record RegistrationResponse(
        String id, String email, String plan, Integer seats) {
}
```

```java
// RegistrationController.java
package example.docs;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class RegistrationController {

    @PostMapping(
        path = "/registrations",
        consumes = MediaType.APPLICATION_FORM_URLENCODED_VALUE,
        produces = MediaType.APPLICATION_JSON_VALUE)
    public ResponseEntity<RegistrationResponse> create(
            @Valid @ModelAttribute RegistrationForm form) {
        RegistrationResponse response = new RegistrationResponse(
                "reg-demo",
                form.getEmail(),
                form.getPlan(),
                form.getSeats());
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

`@Valid` instructs Spring to run Bean Validation after binding the form into the DTO. With `@ModelAttribute`, validation errors are reported via `MethodArgumentNotValidException` when there is no immediately following `BindingResult` parameter for the controller to handle directly. If a `BindingResult` is present, the controller must handle errors explicitly; in that case, do not expect the exception handler above to automatically receive errors captured in `BindingResult`.

## 6. MockMvc testing and generating error snippets

### 6.1. Test dependencies

Example using Spring Boot 3.x, Spring REST Docs, and Gradle Groovy DSL:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.restdocs:spring-restdocs-mockmvc'
}
```

The project's dependency management must provide compatible versions. If the project does not use Spring Boot, configure MockMvc and `RestDocumentationExtension` according to your Spring REST Docs setup.

### 6.2. Testing a valid request

```java
package example.docs;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.restdocs.AutoConfigureRestDocs;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.context.annotation.Import;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.request.RequestDocumentation.formParameters;
import static org.springframework.restdocs.request.RequestDocumentation.parameterWithName;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(RegistrationController.class)
@Import(ApiValidationExceptionHandler.class)
@AutoConfigureRestDocs(outputDir = "build/generated-snippets")
class RegistrationFormDocumentationTest {

    @Autowired
    private MockMvc mockMvc;

    @Test
    void validFormCreatesRegistration() throws Exception {
        mockMvc.perform(post("/registrations")
                .contentType(MediaType.APPLICATION_FORM_URLENCODED)
                .accept(MediaType.APPLICATION_JSON)
                .param("email", "mai@example.com")
                .param("plan", "pro")
                .param("seats", "2"))
            .andExpect(status().isCreated())
            .andExpect(jsonPath("$.id").value("reg-demo"))
            .andDo(document("registrations/create",
                formParameters(
                    parameterWithName("email")
                        .description("Valid email; required"),
                    parameterWithName("plan")
                        .description("Subscription plan: basic or pro"),
                    parameterWithName("seats")
                        .description("Quantity; integer from 1 to 5")
                )
            ));
    }
}
```

Passing this test generates default request and response snippets along with `form-parameters.adoc`. `formParameters(...)` describes the **valid field names**; it neither describes the error body nor validates value ranges on its own.

### 6.3. Testing validation errors and documenting the response

Add the following test to `RegistrationFormDocumentationTest`:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

@Test
void invalidFormDocumentsValidationErrors() throws Exception {
    mockMvc.perform(post("/registrations")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .accept(MediaType.APPLICATION_JSON)
            .param("email", "not-an-email")
            .param("plan", "enterprise")
            .param("seats", "0"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.errors").isArray())
        .andDo(document("registrations/validation-error",
            formParameters(
                parameterWithName("email")
                    .description("Valid email; required"),
                parameterWithName("plan")
                    .description("Subscription plan: basic or pro"),
                parameterWithName("seats")
                    .description("Quantity; integer from 1 to 5")
            ),
            responseFields(
                fieldWithPath("code").description("Overall error code"),
                fieldWithPath("message").description("Overall error message"),
                fieldWithPath("errors").description("List of field-level errors"),
                fieldWithPath("errors[].field").description("Name of the invalid field"),
                fieldWithPath("errors[].code").description("Stable error code"),
                fieldWithPath("errors[].message").description("Error message")
            )
        ));
}
```

The static imports can be grouped at the top of the class with the existing imports. In response fields, the `errors[]...` path describes each element of the array. Spring REST Docs checks the response structure against descriptors and fails if the response contains undocumented fields or is missing required descriptors.

**Do not depend on error ordering in the array.** Validators can return field errors in different orders depending on provider or configuration. Tests should assert only the status, overall error code, and structure; if you need assertions for individual errors, look them up by field/code instead of hardcoding index `errors[0]`.

### 6.4. Testing missing fields and out-of-range values

```java
@Test
void missingEmailAndSeatsDocumentsRequiredErrors() throws Exception {
    mockMvc.perform(post("/registrations")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .accept(MediaType.APPLICATION_JSON)
            .param("plan", "basic"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
        .andExpect(jsonPath("$.errors").isArray());
}

@Test
void unsupportedPlanIsRejected() throws Exception {
    mockMvc.perform(post("/registrations")
            .contentType(MediaType.APPLICATION_FORM_URLENCODED)
            .param("email", "mai@example.com")
            .param("plan", "enterprise")
            .param("seats", "2"))
        .andExpect(status().isBadRequest())
        .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"));
}
```

These two tests verify server behavior. When documenting multiple error variants, each test can use a distinct identifier (`registrations/missing-fields`, `registrations/invalid-plan`) with the same `responseFields(...)` set. Never share an identifier across tests generating different snippets, as output files risk being overwritten.

### 6.5. Testing type conversion (binding) errors

If `seats=two`, Spring cannot convert the string `"two"` to an `Integer`. That is a binding/conversion error, not an `@Min`/`@Max` violation. Specific exception behavior depends on binding and configuration. To document this error category, add an appropriate handler for `BindException`/`MethodArgumentNotValidException` or the corresponding exception observed in the application, then write tests proving the status and error shape. Do not label type conversion failures as `OUT_OF_RANGE`.

Best practice is to maintain a **shared error contract** for both binding and validation, such as the same `code`, `message`, and `errors[]` shape, while using distinct field-level codes:

| Scenario | Suggested field error code |
| --- | --- |
| Required field not sent | `REQUIRED` |
| Invalid email format | `INVALID_FORMAT` |
| Number outside bounds | `OUT_OF_RANGE` |
| Cannot convert string to number | `INVALID_TYPE` |
| Value not in allowed enum/set | `INVALID_VALUE` |

When extending an exception handler for binding errors, avoid returning raw technical exception text directly to clients; such messages can leak class names, raw inputs, or internal details.

## 7. Inspecting generated snippets

With the tests above, the output directory looks like:

```text
build/generated-snippets/
└── registrations/
    ├── create/
    │   ├── form-parameters.adoc
    │   ├── http-request.adoc
    │   └── http-response.adoc
    └── validation-error/
        ├── form-parameters.adoc
        ├── response-fields.adoc
        ├── http-request.adoc
        └── http-response.adoc
```

The snippets present two sides of the same contract:

- `form-parameters.adoc` clarifies which fields the client sends and their meanings.
- `http-request.adoc` shows the concrete request (in error tests, invalid values serve as illustrative bad input).
- `response-fields.adoc` documents the error JSON structure that clients can parse.
- `http-response.adoc` contains the status, headers, and error body captured from the test.

Example response fields table:

| Field path | Description |
| --- | --- |
| `code` | Overall error code |
| `message` | Overall error message |
| `errors` | List of field-level errors |
| `errors[].field` | Name of the invalid field |
| `errors[].code` | Stable field error code |
| `errors[].message` | Error explanation message |

Snippets are produced from test requests and responses at runtime. If the error contract changes, tests and descriptors must change together; never edit generated snippets manually to make documentation look consistent.

## 8. Authoring Asciidoctor and Markdown documentation

Example `src/docs/asciidoc/index.adoc` page:

```adoc
= Registration API

== Create registration with form

=== Request parameters
include::{snippets}/registrations/create/form-parameters.adoc[]

=== Sample request
include::{snippets}/registrations/create/http-request.adoc[]

=== Validation error
When form data is invalid, the server returns HTTP 400.

==== Failing request
include::{snippets}/registrations/validation-error/http-request.adoc[]

==== Error response fields
include::{snippets}/registrations/validation-error/response-fields.adoc[]

==== HTTP response
include::{snippets}/registrations/validation-error/http-response.adoc[]
```

The `{snippets}` variable must point to the root snippets directory (for example, `build/generated-snippets`). The `include::...[]` directive is Asciidoctor syntax. If the main documentation uses Markdown, link to the HTML generated by Asciidoctor or configure a controlled conversion step; do not assume a default Markdown renderer understands AsciiDoc include syntax.

### 8.1. Connecting tests to the documentation build step

With Gradle Groovy DSL and the Asciidoctor plugin configured:

```groovy
def snippetsDir = file('build/generated-snippets')

tasks.named('test') {
    outputs.dir snippetsDir
}

tasks.named('asciidoctor') {
    dependsOn tasks.named('test')
    inputs.dir snippetsDir
    attributes 'snippets': snippetsDir.absolutePath
}
```

CI can run:

```bash
./gradlew test asciidoctor
```

The workflow must ensure:

1. HTTP tests exercise both valid requests and validation errors.
2. Spring REST Docs checks descriptors and writes the corresponding snippets.
3. Asciidoctor reads snippets from the correct directory and renders the documentation.
4. CI fails if either tests or documentation rendering fail.

Do not rely on stale snippets left over from a previous build as proof that documentation is verified. For strict pipelines, use a clean build workspace or appropriate output cleaning before running.

## 9. Common errors and fixes

| Symptom | Common cause | Resolution |
| --- | --- | --- |
| Missing field produces no custom error response | Controller lacks `@Valid`, missing validation dependency, or exception handler misses the actual exception | Check `spring-boot-starter-validation`, annotations, and exception types |
| `@Email` does not reject empty strings | `@Email` typically permits empty values | Combine with `@NotBlank` |
| `seats=two` does not produce `OUT_OF_RANGE` | Failure occurs during string-to-number conversion before Bean Validation | Handle binding errors separately and write tests |
| Error response has a new field undocumented in snippet | `responseFields(...)` descriptors not updated | Add `fieldWithPath(...)` or intentionally mark internal fields `.ignored()` |
| Test depends on `errors[]` ordering | Validators do not guarantee field error order | Look up errors by field name and code rather than fixed array index |
| Response leaks user-submitted values | Handler returns `rejectedValue` or raw exception messages | Return only controlled field names, error codes, and messages |
| Invalid form test fails to generate snippets | Wrong status assertion or exception not mapped as expected | Inspect actual exception, standardize the handler, and re-run tests |
| Asciidoctor cannot find snippet | Identifier or `{snippets}` mismatch | Check `document(...)` names, output directory, and task dependencies |
| API returns `415` | `Content-Type` does not match `consumes` | Send `application/x-www-form-urlencoded` properly |

## 10. Practice exercise

Create a `POST /feedback` API accepting a URL-encoded form with the fields:

- `email`: required, valid email format.
- `rating`: required, integer from 1 to 5.
- `comment`: optional, maximum 300 characters.
- `category`: required, one of `bug`, `feature`, `docs`.

Steps:

1. Create a DTO and declare appropriate constraints (`@NotBlank`, `@Email`, `@NotNull`, `@Min`, `@Max`, `@Size`, `@Pattern`).
2. Create a standardized error response containing `code`, `message`, and `errors[]`.
3. Write a passing test to generate `form-parameters.adoc`.
4. Write tests for invalid email, out-of-range rating, invalid category, and missing required fields. Use `responseFields(...)` to generate `response-fields.adoc`.
5. Add a binding error test with a non-convertible numeric value and design a dedicated `INVALID_TYPE` error code.
6. Embed request, response, and error tables in Asciidoctor; run tests and render documentation in CI.

**Completion criteria:** clients know which field failed, what kind of error occurred, and how to fix it; error responses have a stable schema; snippets are generated from HTTP tests; when the error contract changes, CI requires updating the corresponding documentation.

## References

- [Spring REST Docs — Form Parameters](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/form-parameters.html)
- [Spring REST Docs — Documenting Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Documenting HTTP Responses](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/http-responses.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Model Attribute Methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Jakarta Bean Validation](https://beanvalidation.org/)
- [Spring REST Docs — Getting Started](https://docs.spring.io/spring-restdocs/tutorial/getting-started/index.html)
