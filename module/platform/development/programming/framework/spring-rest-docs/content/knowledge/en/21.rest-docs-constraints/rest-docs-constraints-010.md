# Synchronizing Runtime Validation and Documentation with Spring REST Docs

## 1. Why Must Validation and Documentation Stay in Sync?

A customer creation API might receive JSON like this:

```http
POST /api/customers HTTP/1.1
Content-Type: application/json

{
  "name": "Nguyen An",
  "email": "an@example.test",
  "age": 28
}
```

The contract might specify:

- `name` must not be blank and has a maximum of 100 characters.
- `email` must have a valid email format.
- `age` must be within the range 18 to 120.

If documentation only lists field names without explaining limits, integrators may send data the server rejects. Conversely, if documentation says `age` is optional while the controller actually requires it, documentation and runtime behavior contradict each other.

Spring REST Docs generates snippets from requests/responses in HTTP tests. Descriptors such as `fieldWithPath(...)` describe payload structure; they do not execute Jakarta Bean Validation themselves, do not infer all business limits from annotations, and do not verify that prose descriptions match the validator. To keep documentation trustworthy, you must synchronize:

1. **Runtime validation:** the real rules enforced in the application.
2. **Tests:** valid and invalid requests proving behavior.
3. **Documentation:** descriptors and snippets accurately explaining fields, constraints, and error responses.

The **SPRING_REST_DOCS** module produces verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured, then compiles snippets into Asciidoctor/Markdown and integrates them into build/CI. This lesson belongs to the **Constraints** chapter and walks through synchronizing runtime validation and documentation in that workflow.

After this lesson, you will be able to:

1. Declare validation using Jakarta Bean Validation in request models.
2. Enable validation in controllers and test actual results.
3. Document field limits in Spring REST Docs using descriptor attributes or description text.
4. Document both valid requests and validation error responses.
5. Integrate tests and documentation generation into CI to catch contract drift.

## 2. Runtime Validation and Descriptors Have Different Roles

| Component | Responsibility | Example |
| --- | --- | --- |
| Bean Validation | Enforce rules on objects | `@NotBlank`, `@Email`, `@Size`, `@Min`, `@Max` |
| Spring MVC/WebFlux binding | Convert requests into parameters/objects and trigger validation | `@Valid @RequestBody` |
| HTTP tests | Send data, assert status and response | MockMvc `andExpect(...)` |
| Spring REST Docs descriptor | Describe field, type, meaning, and verified constraints | `fieldWithPath("email").description(...)` |
| Error response snippet | Publish the actual error structure | `responseFields(...)` |
| Asciidoctor/Markdown | Assemble snippets into API guides | `include::{snippets}/...` |

Example descriptor:

```java
fieldWithPath("email")
    .description("Customer email address")
```

only describes the field. It is not equivalent to the validator:

```java
@Email
@NotBlank
String email
```

If the validator changes from maximum 100 characters to maximum 80 characters, the description text must also be reviewed and updated. Spring REST Docs cannot automatically deduce the business semantics of every annotation and guarantee the prose is accurate.

## 3. Declaring Constraints in Request Models

Example using Jakarta Bean Validation:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
        @NotBlank
        @Size(max = 100)
        String name,

        @NotBlank
        @Email
        @Size(max = 254)
        String email,

        @Min(18)
        @Max(120)
        Integer age
) {}
```

Annotations express data-level rules:

| Constraint | Common Rule | Note |
| --- | --- | --- |
| `@NotNull` | Value must not be null | Does not forbid empty strings or whitespace by itself |
| `@NotBlank` | String must not be null and must contain at least one non-whitespace character | Use for required text |
| `@NotEmpty` | String, collection, or array must not be null/empty | Whitespace-only strings may still pass |
| `@Size(min, max)` | Limits string/collection/array size | Does not replace `@NotNull` |
| `@Email` | Checks string per provider's email rules | Does not prove the address exists or can receive mail |
| `@Min`, `@Max` | Limits numeric values appropriately | Test lower/upper bounds |
| `@DecimalMin`, `@DecimalMax` | Limits decimal values | Has `inclusive` attribute |
| `@Positive`, `@PositiveOrZero` | Positive or non-negative value | Choose based on domain |
| `@Pattern` | String must match a regular expression | Regex must accurately reflect the contract |

Not every constraint applies to every data type. Read the Javadoc for the annotations and active provider, and write tests at boundary values.

### 3.1. Required Constraints and Optionality in Documentation

A field annotated with `@NotBlank` generally cannot be sent as null, an empty string, or whitespace-only when validation is enabled. In Spring REST Docs, do not mark that descriptor as optional just because one test fixture omits the field.

Conversely, the `age` field in the example is an `Integer` without `@NotNull`; if the contract allows omission, documentation should state that clearly. However, `@Min(18)`/`@Max(120)` only validate when a non-null value is present; they do not make `age` required by themselves.

For each field, distinguish three aspects:

- **Presence:** is the field allowed to be absent in JSON?
- **Nullability:** if the key is present, is a `null` value accepted?
- **Value constraint:** if a value is provided, what range or format is valid?

`optional()` on a descriptor helps indicate a field may be absent in payload snippets. It does not define nullability or business validation on its own. Descriptions must state these details explicitly when integrators need to know them.

## 4. Enabling Validation in Controllers

With Spring MVC, the request body must be bound and validation triggered, for example:

```java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CustomerController {

    @PostMapping("/api/customers")
    @ResponseStatus(HttpStatus.CREATED)
    CustomerResponse create(@Valid @RequestBody CreateCustomerRequest request) {
        return new CustomerResponse("CUS-100", request.name(), request.email());
    }
}

record CustomerResponse(String id, String name, String email) {}
```

For Jakarta Bean Validation to work, the application needs a matching implementation/provider on the classpath, typically via the Spring Boot validation starter dependency. Annotations on the model without a provider or without enabling validation at the entry point are not enough to guarantee requests are validated.

For nested objects, enable cascade validation using `@Valid` on the nested field:

```java
public record AddressRequest(
        @NotBlank String city,
        @NotBlank String countryCode
) {}

public record CreateCustomerRequest(
        @NotBlank @Size(max = 100) String name,
        @NotBlank @Email String email,
        @Valid AddressRequest address
) {}
```

If `address` is required, add an appropriate constraint such as `@NotNull` alongside `@Valid`. `@Valid` requests cascade validation when the object is present; it does not make the object required by itself.

## 5. Documenting Constraints in Spring REST Docs

Spring REST Docs does not have a descriptor that automatically turns every Bean Validation annotation into a complete contract. The clearest approach is using field descriptors and documenting verified limits:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

requestFields(
    fieldWithPath("name")
        .description("Customer name; required, not whitespace-only, maximum 100 characters"),
    fieldWithPath("email")
        .description("Email; required, valid email format, maximum 254 characters"),
    fieldWithPath("age")
        .description("Age; if provided, must be between 18 and 120")
        .optional()
)
```

The `age` descriptor is marked optional in this example because the request model allows null/absence. If the contract requires age, update the model with the proper constraint and remove `optional()` once tests confirm it.

### 5.1. Using Attributes for Structured Metadata

You can attach attributes to field descriptors and use a custom snippet template to render constraints in a dedicated format:

```java
import static org.springframework.restdocs.snippet.Attributes.key;

fieldWithPath("name")
    .description("Customer name")
    .attributes(
        key("constraints").value("Required; not whitespace-only; maximum 100 characters"),
        key("example").value("Nguyen An")
    )
```

Attributes are metadata for snippet templates. They do not invoke validators and do not verify annotations on DTOs. If the default template does not display custom attributes, modify the template or include constraints in `description(...)`.

### 5.2. Avoiding Unsourced Repeated Numbers in Descriptions

If `@Size(max = 100)` changes to `@Size(max = 80)`, numbers in descriptions or attributes can become stale. Reduce that risk by:

1. Keeping constraints in the request model as the enforced source of truth.
2. Writing tests at boundaries such as 100 and 101 characters.
3. Reviewing descriptors whenever validator changes are reviewed.
4. Running strict documentation tests in CI to catch new/missing fields and boundary tests to prove behavior.

Tests cannot automatically prove prose descriptions are right unless descriptions are compared against the constraint source. You can add conventions, custom annotation/documentation metadata, or dedicated tests if your project needs to automate this check.

## 6. Testing Valid Requests and Documenting with MockMvc

Example passing test:

```java
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.springframework.http.MediaType;
import org.springframework.restdocs.RestDocumentationContextProvider;
import org.springframework.restdocs.RestDocumentationExtension;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.documentationConfiguration;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@ExtendWith(RestDocumentationExtension.class)
class CustomerDocumentationTest {

    private MockMvc mockMvc;

    @BeforeEach
    void setUp(RestDocumentationContextProvider restDocumentation) {
        mockMvc = MockMvcBuilders.standaloneSetup(new CustomerController())
                .apply(documentationConfiguration(restDocumentation))
                .build();
    }

    @Test
    void documentsCreateCustomer() throws Exception {
        mockMvc.perform(post("/api/customers")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "name": "Nguyen An",
                                  "email": "an@example.test",
                                  "age": 28
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.id").value("CUS-100"))
                .andExpect(jsonPath("$.email").value("an@example.test"))
                .andDo(document("customer-create",
                        requestFields(
                                fieldWithPath("name")
                                        .description("Customer name; required; maximum 100 characters"),
                                fieldWithPath("email")
                                        .description("Email; required; valid format; maximum 254 characters"),
                                fieldWithPath("age")
                                        .description("Age; if provided, must be from 18 to 120")
                                        .optional()
                        ),
                        responseFields(
                                fieldWithPath("id").description("Created customer ID"),
                                fieldWithPath("name").description("Customer name"),
                                fieldWithPath("email").description("Customer email")
                        )));
    }
}
```

This test sends a request through the controller and creates the `customer-create` snippet. If the request fails validation, the `isCreated()` assertion fails and no success snippet is generated from a failing request.

In a full Spring Boot integration project, use the real application context and filters/security if they affect binding, validation, or error handling. `standaloneSetup(...)` is handy for small examples, but does not replace testing the full application configuration.

## 7. Testing Constraints at Boundary Values

Testing a single valid request is not enough to prove constraints are enforced. Choose values just below, exactly at, and just above each boundary:

| Field/Constraint | Request Value | Expected Result |
| --- | --- | --- |
| `name` `@NotBlank` | `""` or `"   "` | Rejected |
| `name` `@Size(max=100)` | 100 characters | Accepted if other conditions are valid |
| `name` `@Size(max=100)` | 101 characters | Rejected |
| `email` `@Email` | `an@example.test` | Accepted if no other constraints are violated |
| `email` `@Email` | `not-an-email` | Rejected |
| `age` `@Min(18)` | 17 | Rejected |
| `age` `@Min(18)` | 18 | Passes lower bound |
| `age` `@Max(120)` | 121 | Rejected |

Example negative tests:

```java
@Test
void rejectsInvalidCustomerEmail() throws Exception {
    mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Nguyen An",
                              "email": "not-an-email",
                              "age": 28
                            }
                            """))
            .andExpect(status().isBadRequest());
}

@Test
void rejectsCustomerNameLongerThanMaximum() throws Exception {
    String longName = "A".repeat(101);
    String body = """
            {"name":"%s","email":"an@example.test","age":28}
            """.formatted(longName);

    mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(body))
            .andExpect(status().isBadRequest());
}
```

These tests verify the status produced by the application's default or configured error handling. If the application uses `@ControllerAdvice` to convert `MethodArgumentNotValidException` into a custom error format, assert that exact format rather than assuming a default response.

## 8. Documenting Validation Error Responses

A good API tells clients the error structure returned when invalid payloads are sent. Example error contract:

```json
{
  "type": "VALIDATION_ERROR",
  "message": "Request contains invalid fields",
  "violations": [
    {
      "field": "email",
      "code": "Email",
      "message": "must be a well-formed email address"
    }
  ]
}
```

Response model:

```java
record FieldViolation(String field, String code, String message) {}
record ApiValidationError(
        String type,
        String message,
        List<FieldViolation> violations) {}
```

A `@RestControllerAdvice` can map validation errors into a stable schema. Exact handling depends on the Spring version, exception type, and application policy; what matters is that HTTP tests confirm the actual response.

Example descriptors for the error response:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.responseFields;

responseFields(
    fieldWithPath("type").description("Error category code"),
    fieldWithPath("message").description("General message"),
    fieldWithPath("violations").description("List of validation errors"),
    fieldWithPath("violations[].field").description("Invalid field name"),
    fieldWithPath("violations[].code").description("Constraint or error code"),
    fieldWithPath("violations[].message").description("Message for the field")
)
```

Tests should send an invalid request and document the response:

```java
@Test
void documentsValidationErrorForInvalidEmail() throws Exception {
    mockMvc.perform(post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content("""
                            {
                              "name": "Nguyen An",
                              "email": "not-an-email",
                              "age": 28
                            }
                            """))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.type").value("VALIDATION_ERROR"))
            .andExpect(jsonPath("$.violations[0].field").value("email"))
            .andDo(document("customer-create-invalid-email",
                    responseFields(
                            fieldWithPath("type").description("Error category code"),
                            fieldWithPath("message").description("General message"),
                            fieldWithPath("violations").description("List of validation errors"),
                            fieldWithPath("violations[].field").description("Invalid field name"),
                            fieldWithPath("violations[].code").description("Constraint code"),
                            fieldWithPath("violations[].message").description("Error message")
                    )));
}
```

This is an illustrative example; it assumes the application returns the exact JSON error contract described. Adjust assertions and descriptors to match the actual response; never generate snippets from an imaginary body.

## 9. Nested Validation and Error Lists

For requests with nested objects:

```java
public record AddressRequest(
        @NotBlank String city,
        @Pattern(regexp = "^[A-Z]{2}$") String countryCode
) {}

public record CreateCustomerRequest(
        @NotBlank String name,
        @NotBlank @Email String email,
        @Valid @NotNull AddressRequest address
) {}
```

`@Valid` on `address` triggers cascade validation; `@NotNull` makes `address` required. Without `@Valid`, constraints inside `AddressRequest` may not cascade as intended.

Request documentation:

```java
requestFields(
    fieldWithPath("name").description("Customer name; required"),
    fieldWithPath("email").description("Valid email; required"),
    fieldWithPath("address.city").description("City; required"),
    fieldWithPath("address.countryCode")
        .description("Two-letter uppercase country code")
)
```

Documentation must reflect the nested field structure and constraints on each field. Tests should include an invalid case on a nested path, such as `address.countryCode = "VNM"`, and verify the violation points to the exact path.

If the nested object is optional, you can use `@Valid` without `@NotNull`; when the object is present, child constraints are checked. Corresponding descriptors should use `optional()` on the subsection/field if absence is allowed.

## 10. Cross-Field and Business Constraints

Some rules do not belong to a single field alone:

- `startDate` must precede `endDate`.
- `currency` must match `country`.
- At least one of `email` or `phone` must be provided.
- `discount` must not exceed `total`.

These can be implemented via class-level constraints/custom validators or validated in the service/domain layer. Example:

```java
@ValidDateRange
public record BookingRequest(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate
) {}
```

A custom `@ValidDateRange` constraint needs a validator that inspects both values and attaches violations to the appropriate field or object path. Spring REST Docs does not automatically infer this logic from the annotation name.

In documentation, describe the rule as a condition between fields:

```java
requestFields(
    fieldWithPath("startDate").description("Start date; ISO-8601 format"),
    fieldWithPath("endDate").description("End date; must be after startDate")
)
```

Minimum tests should cover:

1. Valid date range.
2. `endDate` equal to `startDate`.
3. `endDate` before `startDate`.
4. One or both fields missing/null if specified by the contract.

For business constraints, descriptions must clearly state the condition and error response. Do not try to cram a multi-field relationship into a single annotation in the field table.

## 11. Enums, Patterns, and Complex Limits

A field may be constrained to a finite set of values:

```java
public enum CustomerType {
    INDIVIDUAL, BUSINESS
}

public record CustomerCategoryRequest(
        @NotNull CustomerType type,
        @Pattern(regexp = "^[A-Z0-9-]{3,20}$")
        String externalCode
) {}
```

Document:

```java
requestFields(
    fieldWithPath("type")
        .description("Customer type: INDIVIDUAL or BUSINESS"),
    fieldWithPath("externalCode")
        .description("Partner code consisting of 3–20 uppercase letters, digits, or hyphens")
        .optional()
)
```

For long or complex regexes, do not simply paste raw Java expressions into documentation and leave clients to decode them. Describe the rule in clear language and provide valid/invalid examples if helpful. If regexes are a critical contract source, consider publishing a shared OpenAPI/JSON Schema or machine-readable specification.

## 12. Avoiding Contract Drift Between Annotations and Documentation

Common causes of documentation drifting from runtime behavior:

| Runtime Change | Documentation Risk |
| --- | --- |
| `@Size(max=100)` changed to `@Size(max=80)` | Description still states maximum 100 characters |
| `@NotNull` added | Documentation still marks field optional |
| `@Valid` removed from nested object | Documentation still claims child constraints are checked |
| Enum value added | Table of valid values is not updated |
| Error schema changed in `@ControllerAdvice` | `responseFields` or error examples are outdated |
| Cross-field validator changed | Date/value relationship descriptions are no longer accurate |

When modifying request DTOs, validation annotations, custom validators, or error handlers, review all of the following together:

- Valid tests and invalid tests at boundaries.
- Field descriptors and descriptions/attributes.
- Error response descriptors along with HTTP statuses.
- Asciidoctor/Markdown snippets and client examples.

## 13. Strict Documentation and CI

Strict `requestFields(...)` catches undocumented fields in test payloads or missing required descriptors. It is valuable when schemas change, but does not replace validation tests:

- Strict REST Docs verifies the structure of documented fields.
- Bean Validation checks values against runtime constraints.
- HTTP tests verify mapping from violations to status/error payloads.
- Documentation review checks prose meaning, limit examples, and business rules.

A build workflow typically includes:

1. Compile application and tests.
2. Run valid/invalid validation tests.
3. Generate Spring REST Docs snippets.
4. Run Asciidoctor to include snippets and render documentation.
5. Archive documentation artifacts in the pipeline or publish per project workflow.

Gradle example when tasks are configured:

```bash
./gradlew test asciidoctor
```

If the project uses Maven, run the configured lifecycle goal for tests and Asciidoctor. Task/dependency details depend on project configuration; ensure Asciidoctor depends on snippet output from tests and fails when required snippets are missing.

### 13.1. Test Separation Guidelines

| Test Group | Purpose | Snippet Generation Needed? |
| --- | --- | --- |
| Valid request documentation test | Generate successful request/response snippets | Yes |
| Validation boundary tests | Prove min/max, size, pattern | Not necessarily |
| Invalid request documentation test | Document a representative error contract | Yes, if error contract is public |
| Custom/cross-field validator tests | Prove business rules | Not necessarily |

You do not need a snippet directory for every invalid value. Pick representative cases that keep documentation readable, while your test suite covers broader boundaries.

## 14. Practice Checklist

When adding or changing validation on an endpoint:

- [ ] Request DTO has constraints matching data types and contract.
- [ ] Controller actually enables validation via `@Valid` or an equivalent mechanism.
- [ ] Nested objects have cascade validation where needed.
- [ ] Optional, null, and empty states are clearly distinguished.
- [ ] Valid tests and boundary/invalid tests exist.
- [ ] `requestFields(...)` or `requestPartFields(...)` accurately describe fields and limits.
- [ ] Error response has a stable schema and is documented if part of the public contract.
- [ ] Custom/cross-field rules have dedicated descriptions and tests.
- [ ] Snippet tests and Asciidoctor run in CI.

## 15. Practice Exercise

Build a booking creation endpoint:

```http
POST /api/bookings
Content-Type: application/json

{
  "customerEmail": "an@example.test",
  "startDate": "2026-12-01",
  "endDate": "2026-12-05",
  "guestCount": 2,
  "note": "Near the elevator"
}
```

Contract:

- `customerEmail`: required, valid email format.
- `startDate`, `endDate`: required, ISO date format; `endDate` must be after `startDate`.
- `guestCount`: from 1 to 8.
- `note`: optional, maximum 300 characters.

Steps:

1. Create a request record with appropriate `@NotBlank`, `@Email`, `@NotNull`, `@Min`, `@Max`, and `@Size`.
2. Write a class-level validator for the rule that `endDate` is after `startDate`, or implement the rule in the domain layer and explain your choice.
3. Enable validation on the controller.
4. Write MockMvc tests for a valid request, invalid email, out-of-range `guestCount`, overly long `note`, and invalid end date.
5. Document request fields with accurate descriptions of presence, format, and range.
6. Standardize the error response and document one representative error using `responseFields(...)`.
7. Run tests and Asciidoctor in build/CI.

**Completion criteria:** the Validator accurately enforces the contract; tests prove boundary values and errors; descriptors do not mislabel fields as optional; error response snippets match runtime responses.

## 16. Key Takeaways

Runtime validation and Spring REST Docs documentation are two complementary layers. Jakarta Bean Validation together with the controller enforces rules; HTTP tests prove which requests are accepted or rejected; descriptors and response snippets explain that contract to integrators. `fieldWithPath(...)` does not run validators itself, `optional()` does not replace nullability rules, and strict documentation does not replace boundary testing. Keeping all three layers synchronized in build/CI ensures documentation accurately reflects API behavior over time.

### References

- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Validation in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring REST Docs — Request Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-fields.html)
- [Spring REST Docs — Response Fields](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/response-fields.html)
