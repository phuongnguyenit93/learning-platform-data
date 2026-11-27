# Why Describing Constraints Makes Documentation More Useful

## 1. Objectives and Context

A request/response fields table only tells the reader **which fields exist and what each field means**. However, when integrating an API, developers also need to know what data is accepted: the maximum length of a string, which fields are required, what range a number must fall within, whether an email must follow a valid format, whether an end date must be after a start date, or whether a code must be unique in the system.

Those rules are **constraints (data/business constraints)**. When documentation clearly describes constraints, API consumers can construct valid requests from the start, understand why a request is rejected, and handle errors consistently. This is important with **SPRING_REST_DOCS**: producing verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generating snippets for requests, responses, payloads, parameters, and headers; and compiling Asciidoctor/Markdown in build and CI pipelines.

After this lesson, you will be able to distinguish field descriptions from constraints, combine Bean Validation with HTTP tests, include constraints in descriptors/templates, test valid and invalid data, and avoid inaccurate or outdated descriptions.

> Spring REST Docs records the HTTP operation being tested. It does not generate endpoints, fixtures, or business rules on its own. Descriptors verify that documentation matches the payload; they do not replace all assertions.

## 2. Field Descriptions and Constraints Answer Different Questions

Consider an account creation endpoint:

~~~json
{
  "name": "Lan Nguyen",
  "email": "lan@example.com",
  "age": 28,
  "password": "ExamplePass123"
}
~~~

Basic field table:

| Field | Description |
| --- | --- |
| `name` | Display name of the account. |
| `email` | Email address. |
| `age` | User age. |
| `password` | Registration password. |

This table does not state whether `name` can be blank, what format `email` requires, what the minimum `age` is, or what conditions the password must satisfy.

Constraints can be added:

| Field | Description | Example Constraint |
| --- | --- | --- |
| `name` | Display name | Not null/empty; 2–80 characters long. |
| `email` | Email address | Required; valid email format; maximum 254 characters per contract. |
| `age` | User age | Integer from 18 to 120. |
| `password` | Registration password | Required; at least 12 characters and meets product policy. |

These are **example contract rules**, not defaults of Spring REST Docs, Bean Validation, or every API. Real rules must come from the code, domain, and confirmed product decisions.

Good documentation helps readers answer: whether a field is required to be present; what type and value range are accepted; which status/error response invalid data produces; and which layer enforces the rule.

## 3. How Constraints Make Documentation More Useful

### 3.1. Helping Clients Send Valid Requests

If documentation only states that `age` is the user's age, a client might send `-5`, `0`, or a very large number. When limits are published, clients can validate before sending. Similarly, an email description should clarify whether it is required or optional, along with length and format limits.

### 3.2. Clarifying Absent, Null, and Empty

The following three requests do not necessarily have the same meaning:

~~~json
{"name":"Lan"}
~~~

~~~json
{"name":"Lan","nickname":null}
~~~

~~~json
{"name":"Lan","nickname":""}
~~~

- **Absent:** the client does not send `nickname`.
- **Explicit null:** the client sends the field with a JSON `null` value.
- **Empty string:** the client sends an empty string.

`@NotNull` is not synonymous with `@NotBlank`. `@NotBlank` requires a string to contain at least one non-whitespace character. Documentation should state each state accurately instead of lumping everything together as "required".

### 3.3. Explaining Why a Request Was Rejected

If the contract states that `quantity` must be greater than 0, readers understand why `quantity = 0` is rejected. When documentation includes sample error responses, clients also know which field to fix or which error code to handle.

### 3.4. Detecting Contract Changes in CI

When a constraint changes, validation logic, tests, descriptors, and documentation content must all be updated. REST Docs detects when payload fields change or descriptors no longer match. It does not automatically detect every constraint change if the text lives only in manual descriptions; dedicated tests and reviews are needed.

## 4. Common Constraints and How to Interpret Them

| Annotation | General Meaning | What to State Explicitly |
| --- | --- | --- |
| `@NotNull` | Value must not be null | Is the field required to be present, or is only a null value forbidden? |
| `@NotBlank` | String is not null and has at least one non-whitespace character | Cannot be empty or whitespace-only. |
| `@NotEmpty` | String/collection/map/array is not empty for supported types | At least one character or element. |
| `@Size(min, max)` | Size within range | Unit and min/max bounds. |
| `@Min` / `@Max` | Numeric value within limits | Limits and boundary inclusivity. |
| `@DecimalMin` / `@DecimalMax` | Decimal value limits | Whether bounds are inclusive or exclusive. |
| `@Positive` / `@PositiveOrZero` | Positive or non-negative number | Is 0 accepted? |
| `@Email` | String matches the provider's email rule | Does not prove the mailbox exists. |
| `@Pattern` | Value matches a regular expression | Explain in plain, understandable language. |
| `@Past` / `@Future` | Point in time in the past/future according to the validation clock | Reference timestamp/time zone if meaningful. |
| `@Valid` | Triggers validation on nested objects | Nested rules and how errors are returned. |

An annotation does not automatically equal the full contract. `@Email` does not verify that an email actually exists; `@Pattern` may contain hard-to-read regex; `@Size` has different units on strings versus collections. Explain rules in business terms and verify behavior against the active provider.

### 4.1. DTO with Bean Validation Constraints

~~~java
import jakarta.validation.Valid;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record RegisterAccountRequest(
    @NotBlank
    @Size(min = 2, max = 80)
    String name,

    @NotBlank
    @Email
    @Size(max = 254)
    String email,

    @NotNull
    @Min(18)
    @Max(120)
    Integer age,

    @NotNull
    @Valid
    AddressRequest address
) {}

public record AddressRequest(
    @NotBlank @Size(max = 120) String city,
    @NotBlank @Size(max = 20) String postalCode
) {}
~~~

This example uses Jakarta Bean Validation (`jakarta.validation`) and assumes the application has an appropriate provider configured. For nested objects, `@Valid` triggers constraint checks on `AddressRequest` when validation is invoked. Exact behavior also depends on validation groups, the provider, and configuration.

The controller needs validation enabled:

~~~java
@PostMapping("/api/accounts")
public ResponseEntity<AccountResponse> register(
        @Valid @RequestBody RegisterAccountRequest request) {
    AccountResponse created = accountService.register(request);
    return ResponseEntity
        .created(URI.create("/api/accounts/" + created.id()))
        .body(created);
}
~~~

`@Valid` triggers validation for the request object in an appropriately configured Spring MVC setup. Test the actual status/error mapping; do not assume every application returns the exact same error JSON.

## 5. Spring REST Docs Does Not Automatically Display Every Validation Annotation

`requestFields(...)` and `responseFields(...)` document the field paths and descriptions declared by the author. **The default snippet table does not automatically read all Bean Validation annotations and add a constraints column.**

~~~java
requestFields(
    fieldWithPath("email").description("Account email address")
)
~~~

This example documents the field. It does not automatically add `@NotBlank`, `@Email`, or `@Size(max = 254)` to the table.

There are three options:

1. Write constraints directly in the description: simple, requires review to keep in sync.
2. Read Bean Validation metadata using the Spring REST Docs API and attach it to descriptor attributes.
3. Create a custom snippet template to render a dedicated constraint column.

For a few fields, thorough descriptions are usually enough. For large DTOs, metadata and templates can reduce duplication; business constraints not represented by annotations still require review.

## 6. Extracting Constraints with ConstraintDescriptions

Spring REST Docs provides `ConstraintDescriptions` in its core module to retrieve constraint descriptions on a Java type. Example:

~~~java
import org.springframework.restdocs.constraints.ConstraintDescriptions;

public class AccountConstraintDescriptions {
    private final ConstraintDescriptions descriptions =
        new ConstraintDescriptions(RegisterAccountRequest.class);

    public List<String> forEmail() {
        return descriptions.descriptionsForProperty("email");
    }

    public List<String> forAge() {
        return descriptions.descriptionsForProperty("age");
    }
}
~~~

Descriptions can be resolved from message interpolation or a resource bundle. Results may vary depending on the Spring REST Docs version and validation provider; configure clear, user-friendly messages instead of relying on cryptic defaults.

Example resource bundle:

~~~properties
jakarta.validation.constraints.NotBlank.message=Must not be blank.
jakarta.validation.constraints.Email.message=Must be a well-formed email address.
jakarta.validation.constraints.Size.message=Length must be within the allowed range.
jakarta.validation.constraints.Min.message=Value must not be less than the minimum limit.
jakarta.validation.constraints.Max.message=Value must not be greater than the maximum limit.
~~~

The messages above are general examples; parameterized constraints need message templates that reflect dynamic min/max values. Do not copy default messages if they expose class names or internal terminology.

### 6.1. Adding Constraints to Descriptor Attributes

REST Docs allows attaching metadata to field descriptors via `attributes(...)`:

~~~java
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

ConstraintDescriptions emailConstraints =
    new ConstraintDescriptions(RegisterAccountRequest.class);

FieldDescriptor emailField = fieldWithPath("email")
    .description("Account email address")
    .attributes(key("constraints").value(
        String.join("; ", emailConstraints.descriptionsForProperty("email"))
    ));
~~~

This is project-named metadata and does not appear automatically in the default fields template. If the template does not read `constraints`, the content will not render in the table.

A helper can reduce repetition:

~~~java
public class ConstrainedFields {
    private final ConstraintDescriptions descriptions;

    public ConstrainedFields(Class<?> inputType) {
        this.descriptions = new ConstraintDescriptions(inputType);
    }

    public FieldDescriptor withPath(String path, String description) {
        List<String> constraints = descriptions.descriptionsForProperty(path);
        return fieldWithPath(path)
            .description(description)
            .attributes(key("constraints").value(String.join("; ", constraints)));
    }
}
~~~

This approach assumes JSON paths match Java properties. For nested fields, collections, JSON names differing from Java properties, or separate mapping DTOs, you must map the property path correctly; do not assume every JSON path works directly with Bean Validation metadata.

## 7. Rendering Constraints in a Custom Snippet Template

An Asciidoc target table might look like:

~~~asciidoc
|===
|Field |Description |Constraints

|email
|Account email address
|Must not be blank; must be a valid email format; maximum 254 characters
|===
~~~

To render a constraints column, customize the fields template for your REST Docs version so it reads the `constraints` attribute from the descriptor. Copy the matching template from the project's artifact/version, add the column, and inspect the actual output. Do not modify a template without verifying the template engine syntax.

A simpler approach is writing constraints directly in the description:

~~~java
fieldWithPath("email")
    .description("Email address. Required; must be a valid format; maximum 254 characters.")
~~~

This requires no custom template, though manual text must be updated whenever annotations or domain rules change.

**Do not claim that constraints appear automatically** just because `ConstraintDescriptions` was instantiated. You must attach metadata to descriptors and render it in a template, or write it directly in the description.

## 8. Verifying Constraints with HTTP Tests

### 8.1. Testing Valid Data

~~~java
@Test
void registerAccountWithValidData() throws Exception {
    mockMvc.perform(post("/api/accounts")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "Lan Nguyen",
                  "email": "lan@example.com",
                  "age": 28,
                  "address": {
                    "city": "Ho Chi Minh City",
                    "postalCode": "700000"
                  }
                }
                """))
        .andExpect(status().isCreated())
        .andDo(document("accounts-register-valid",
            requestFields(
                fieldWithPath("name")
                    .description("Display name; 2–80 characters, must not be blank"),
                fieldWithPath("email")
                    .description("Valid email, maximum 254 characters"),
                fieldWithPath("age")
                    .description("Age from 18 to 120"),
                fieldWithPath("address").description("Address"),
                fieldWithPath("address.city")
                    .description("City, maximum 120 characters"),
                fieldWithPath("address.postalCode")
                    .description("Postal code, maximum 20 characters")
            )
        ));
}
~~~

This example assumes the endpoint and fixture return `201 Created`. Constraints are placed in the description to work with the default template. If the project uses metadata/custom templates, replace this with a helper and verify that the constraints column renders.

### 8.2. Testing Invalid Data

~~~java
@Test
void rejectInvalidAccountData() throws Exception {
    mockMvc.perform(post("/api/accounts")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "name": "L",
                  "email": "not-an-email",
                  "age": 15,
                  "address": {
                    "city": "",
                    "postalCode": "700000"
                  }
                }
                """))
        .andExpect(status().isBadRequest())
        .andDo(document("accounts-register-invalid"));
}
~~~

The test assumes the application maps Bean Validation failures to `400 Bad Request`. The payload violates multiple constraints. To document individual errors clearly, split tests by scenario so the cause of each response is unambiguous.

Example error response:

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request contains invalid fields",
  "violations": [
    {
      "field": "email",
      "code": "Email",
      "message": "Must be a well-formed email address."
    },
    {
      "field": "age",
      "code": "Min",
      "message": "Age must be at least 18."
    }
  ]
}
~~~

This body is an **example contract**, not a default format of REST Docs or Spring Boot. An application may use Problem Details (RFC 9457) or a custom schema. Test the status, media type, fields, and messages according to the actual error handler.

### 8.3. Testing Boundary Values

| Constraint | Valid Example | Failure Cases to Test |
| --- | --- | --- |
| `@NotBlank` | `"Lan"` | `""`, `"   "`, null |
| `@Size(min=2, max=80)` | Length 2 and 80 | Length 1 and 81 |
| `@Min(18)` | 18 | 17 |
| `@Max(120)` | 120 | 121 |
| `@Email` | `lan@example.com` | `not-an-email` |
| `@NotNull` | Present with value | null/missing field depending on binding type |

You do not need to test every combination if reasonable equivalence partitioning is used, but key boundaries must be covered. Primitive types such as `int` do not represent null the same way `Integer` does; this affects how missing fields and default values are distinguished after binding.

## 9. Response Constraints Matter Too

Constraints do not apply only to inputs. Responses can also carry guarantees regarding type, format, range, or cross-field relationships:

| Field | Description | Constraint/Guarantee |
| --- | --- | --- |
| `id` | Account ID | Positive, stable integer. |
| `status` | Account status | One of `PENDING`, `ACTIVE`, `LOCKED`. |
| `createdAt` | Creation timestamp | ISO-8601/RFC 3339, UTC per contract. |
| `roles` | Role list | Contains only public roles permitted by the API. |

These guarantees should be protected with response tests. `responseFields(...)` checks documented fields against the payload; it does not automatically verify that a total equals the sum of line items or that an enum contains only allowed values. Use appropriate domain assertions and state the rules clearly in documentation.

## 10. Constraints Are Not Always Bean Validation

Some rules cannot be fully expressed with property-level annotations:

- Email must not already be registered (uniqueness requires querying data).
- Order ID must belong to the authenticated customer.
- Delivery date must align with the shipping schedule.
- Total amount must not exceed the credit limit.
- A status may only transition to the next valid state in a workflow.

These are **domain/business constraints**. They can be enforced in the service/domain layer and tested via HTTP. Documentation must describe the conditions and error responses; `ConstraintDescriptions` cannot extract them automatically.

For example, `@Email` checks string syntax per the provider, not whether the email exists; uniqueness requires separate tests for unused and already-registered emails. Document status codes and error codes as promised by the API.

## 11. Including Constraints in Final Documentation

Asciidoctor can include raw payloads and field tables:

~~~asciidoc
= Accounts API

== Register an Account

Name must be 2–80 characters; email must be validly formatted and within the length limit; age must be from 18 to 120.

=== HTTP request
include::{snippets}/accounts-register-valid/http-request.adoc[]

=== Request fields and constraints
include::{snippets}/accounts-register-valid/request-fields.adoc[]

=== Validation error
include::{snippets}/accounts-register-invalid/http-response.adoc[]

=== Error fields
include::{snippets}/accounts-register-invalid/response-fields.adoc[]
~~~

`request-fields.adoc` only shows constraints if the descriptions already contain them or a custom template renders metadata. The default table does not automatically reflect all Bean Validation annotations.

With Markdown, the Asciidoctor directive `include::{snippets}/...[]` is not understood directly by all Markdown renderers; an appropriate template or conversion/embedding step is required.

## 12. CI and Controlling Constraint Changes

When a constraint changes, review all of the following together:

1. DTO/Bean Validation annotations or domain rules.
2. Error handler and response contract.
3. HTTP tests for valid, invalid, and boundary data.
4. Field descriptors and constraint descriptions.
5. Raw snippets and final documentation.

~~~mermaid
flowchart TD
    A["Constraint changes"] --> B["Update validation/domain logic"]
    B --> C["Run HTTP tests: valid + invalid + boundary"]
    C --> D{"Assertions pass?"}
    D -->|No| E["Fail CI"]
    D -->|Yes| F["Spring REST Docs generates snippets"]
    F --> G["Render Asciidoctor/Markdown"]
    G --> H{"Constraints and error docs complete?"}
    H -->|No| E
    H -->|Yes| I["Review and publish"]
~~~

If the age limit changes from 18–120 to 21–100 and only the annotation is updated, manual descriptions might still state 18–120. CI only catches mismatches if tests/descriptors/templates check them; manual prose requires review. Documentation tasks must depend on snippet-generating tests and publish only when both tests and rendering succeed.

## 13. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Docs only state field meaning without limits | Description lacks constraints | Add value ranges, units, and bounds. |
| Annotation changed but table did not | Default template does not render annotations automatically | Use ConstraintDescriptions, custom attributes/templates, or update the description. |
| Messages expose Java terms | Default/provider messages are unsuitable | Configure user-friendly messages. |
| `@NotNull` understood as field always required to be present | Confusing value validation with JSON presence/binding | Document absent/null separately and test each case. |
| Optional field misdescribed | Confusing optional with null/empty | Verify contract and distinguish absent/null/empty. |
| Validation status differs from expectation | Exception handler/configuration changed mapping | Verify the actual HTTP response. |
| `@Email` described as verifying email existence | Confusing format check with mailbox verification | Document format checking only; test uniqueness separately. |
| Relaxed descriptors hide new fields | Using relaxed just to keep tests green | Review schema changes and update descriptors. |
| ConstraintDescriptions returns an empty list | Missing provider, wrong class/property path, or unrecognized metadata | Check dependencies/provider, paths, and resolver. |
| Custom attribute does not appear | Template does not render the attribute | Update the template and check the output. |
| Docs fall behind logic | No tests/reviews tied to validation changes | Add boundary tests and CI gates. |

## 14. Practice Exercise

Design the `POST /api/members` endpoint:

~~~json
{
  "fullName": "Lan Nguyen",
  "email": "lan@example.com",
  "age": 28,
  "phone": "0901234567"
}
~~~

Assumed contract:

- `fullName`: required, 2–80 characters, not whitespace-only.
- `email`: required, valid format, maximum 254 characters.
- `age`: integer from 18 to 120.
- `phone`: required, matching the product's published phone format.

Steps:

1. Create a DTO with Bean Validation constraints and a custom validator if required by the contract.
2. Write HTTP tests for a valid request and invalid cases: blank name, invalid email, age 17, invalid phone format.
3. Assert status/error payloads against the real exception handler.
4. Use `requestFields(...)`; write constraints in descriptions or use `ConstraintDescriptions` + custom attributes/templates.
5. Generate snippets for the valid request and error response; open the raw snippets and include them in Asciidoctor.
6. Change the age/name length limits; verify that boundary tests and documentation update together.
7. Run the pipeline and ensure it does not publish if assertions, descriptors, or rendering fail.

**Completion criteria:** readers understand what each field means and which values are valid; constraints reflect tested logic; error responses are usable by clients; validation changes produce clear diffs and checks in CI.

## References

- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring REST Docs — Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html)
- [Spring REST Docs — Customizing Requests and Responses](https://docs.spring.io/spring-restdocs/reference/customizing-requests-and-responses.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
- [RFC 9457 — Problem Details for HTTP APIs](https://www.rfc-editor.org/rfc/rfc9457.html)
