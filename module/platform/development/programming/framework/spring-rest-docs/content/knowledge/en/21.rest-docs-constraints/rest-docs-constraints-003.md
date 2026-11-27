# ValidationConstraints Resolving Constraints from Bean Validation

## 1. Objectives and Context

A request/response fields table shows which fields exist and what each field means, but API consumers also need to know which values are accepted: the maximum length of a string, what range a number must fall within, whether an email must follow a valid format, or whether two dates satisfy a relational condition. Those are **constraints**.

Spring REST Docs provides an API to resolve constraints from Bean Validation and obtain corresponding descriptions. This capability supports the goal of **SPRING_REST_DOCS**: producing verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured; generating snippets for requests, responses, payloads, parameters, and headers; and compiling Asciidoctor/Markdown documentation in build and CI pipelines.

After this lesson, you will be able to use `ConstraintDescriptions`, understand the two types of resolvers, customize descriptions via resource bundles, attach constraints to field descriptors, and recognize limitations with nested, class-level, and domain constraints.

> The title uses "ValidationConstraints", but the core public API in Spring REST Docs is **`ConstraintDescriptions`** along with the resolvers in package `org.springframework.restdocs.constraints`. Do not assume a class named `ValidationConstraints` exists in every version.

## 2. From Bean Validation to API Documentation

Example DTO:

~~~java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public class RegisterMemberRequest {
    @NotBlank
    @Size(min = 2, max = 80)
    private String fullName;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;
}
~~~

| Property | Annotation | Meaning to Communicate |
| --- | --- | --- |
| `fullName` | `@NotBlank` | Not null, empty, or whitespace-only. |
| `fullName` | `@Size(min=2,max=80)` | Length from 2 to 80. |
| `email` | `@NotBlank` | Must not be blank. |
| `email` | `@Email` | Email format per the provider. |
| `email` | `@Size(max=254)` | Maximum 254 characters per the example contract. |

Annotations take effect when Bean Validation is enabled, such as when a controller receives a DTO with `@Valid`. They **do not automatically add a constraints column** to Spring REST Docs' default snippets.

~~~mermaid
flowchart LR
    A["DTO + Bean Validation annotations"] --> B["Bean Validation Validator"]
    B --> C["ConstraintDescriptions"]
    C --> D["Descriptions by property"]
    D --> E["FieldDescriptor"]
    E --> F["REST Docs template"]
    F --> G["request-fields.adoc"]
~~~

The validator/resolver extracts metadata. The description resolver turns metadata into prose. The author places that prose into descriptors/templates. Merely retrieving descriptions does not generate snippets automatically; you must pass them into `requestFields(...)` or `responseFields(...)`.

## 3. Using ConstraintDescriptions

`ConstraintDescriptions` retrieves a list of constraint descriptions for a property:

~~~java
import java.util.List;
import org.springframework.restdocs.constraints.ConstraintDescriptions;

class RegisterMemberConstraints {
    List<String> describeFullName() {
        ConstraintDescriptions descriptions =
            new ConstraintDescriptions(RegisterMemberRequest.class);
        return descriptions.descriptionsForProperty("fullName");
    }

    List<String> describeEmail() {
        ConstraintDescriptions descriptions =
            new ConstraintDescriptions(RegisterMemberRequest.class);
        return descriptions.descriptionsForProperty("email");
    }
}
~~~

`descriptionsForProperty("fullName")` returns a list of constraint descriptions that the resolver finds on the property. The result may correspond to "Must not be blank" and "Must be between 2 and 80 characters"; exact wording depends on the resource bundle, locale, and version.

### 3.1. Default Mechanism

According to Spring REST Docs documentation, the default constructor uses:

- `ValidatorConstraintResolver` to find constraints through a Bean Validation `Validator`.
- `ResourceBundleConstraintDescriptionResolver` to retrieve descriptive sentences from a resource bundle.

The project needs an appropriate Bean Validation provider. Spring Boot typically provides this integration via the validation dependency; projects not using Boot must configure a corresponding provider/Validator.

### 3.2. Default Resolution Scope

Spring REST Docs documentation currently notes that the default mechanism only supports **property constraints**. Therefore:

- Constraints directly on properties such as `@NotBlank` and `@Size` are the primary case.
- Do not assume class-level constraints will be returned by `descriptionsForProperty(...)`.
- Rules in services, repositories, or rule engines are not extracted automatically.
- For nested objects, collections, and custom JSON field names, verify the property path and mapping to the field path.

Cross-field and domain rules must be documented and tested separately. Do not attribute capabilities to `ConstraintDescriptions` that the resolver does not provide.

## 4. Attaching Descriptions to Request Fields

You can append descriptions to the field description:

~~~java
import org.springframework.restdocs.constraints.ConstraintDescriptions;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;

ConstraintDescriptions constraints =
    new ConstraintDescriptions(RegisterMemberRequest.class);

requestFields(
    fieldWithPath("fullName").description(
        "Full name. " + String.join("; ",
            constraints.descriptionsForProperty("fullName"))
    ),
    fieldWithPath("email").description(
        "Contact email. " + String.join("; ",
            constraints.descriptionsForProperty("email"))
    )
)
~~~

This works with the default template because constraints are placed inside the description. If default descriptions are in English, configure the bundle/resolver in the documentation's language rather than mixing languages.

### 4.1. Reusable Helper

~~~java
import java.util.List;
import org.springframework.restdocs.constraints.ConstraintDescriptions;
import org.springframework.restdocs.payload.FieldDescriptor;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

public class ConstrainedFields {
    private final ConstraintDescriptions descriptions;

    public ConstrainedFields(Class<?> inputType) {
        this.descriptions = new ConstraintDescriptions(inputType);
    }

    public FieldDescriptor withPath(String property, String description) {
        List<String> constraints =
            this.descriptions.descriptionsForProperty(property);
        String details = String.join("; ", constraints);
        String fullDescription = details.isBlank()
            ? description : description + " " + details;
        return fieldWithPath(property).description(fullDescription);
    }
}
~~~

`String.isBlank()` requires Java 11 or later. The example assumes the JSON field name matches the Java property. If the JSON uses `full_name` while the DTO uses `fullName`, the helper should accept the JSON field path and Bean Validation property name separately.

## 5. Descriptor Attributes and Custom Templates

Instead of concatenating constraints into the description, you can store separate metadata:

~~~java
import static org.springframework.restdocs.snippet.Attributes.key;
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;

ConstraintDescriptions descriptions =
    new ConstraintDescriptions(RegisterMemberRequest.class);

FieldDescriptor email = fieldWithPath("email")
    .description("Contact email")
    .attributes(key("constraints").value(
        String.join("; ", descriptions.descriptionsForProperty("email"))
    ));
~~~

The `constraints` key is project-defined. The default fields template will not render this key unless it is customized to read it.

The target table can include a dedicated column:

~~~asciidoc
|===
|Field |Description |Constraints

|email
|Contact email
|Must not be blank; valid email format; maximum 254 characters
|===
~~~

To display it, copy the fields template matching your project's version, add a column reading the descriptor attribute, and run tests to verify. Interpolation syntax depends on the actual template; do not assume one placeholder works automatically across all versions.

## 6. Customizing Descriptions via Resource Bundle

By default, Spring REST Docs uses the resource bundle base name:

~~~text
org.springframework.restdocs.constraints.ConstraintDescriptions
~~~

Each key consists of the annotation's fully qualified name and the `.description` suffix. For example:

~~~properties
jakarta.validation.constraints.NotBlank.description=Must not be null, empty, or whitespace-only
jakarta.validation.constraints.Size.description=Length must be within the declared min and max limits
jakarta.validation.constraints.Email.description=Must be a valid email address format
jakarta.validation.constraints.Min.description=Value must not be less than the minimum threshold
jakarta.validation.constraints.Max.description=Value must not be greater than the maximum threshold
~~~

Place the file according to Java `ResourceBundle` rules and the project's locale. With Jakarta Bean Validation, use the `jakarta.validation.constraints` package; legacy projects using `javax.validation` need keys matching their actual package.

### 6.1. Constraint Attributes

Constraints have attributes such as `min`, `max`, and `value`. REST Docs' resolver can use those attributes when building descriptions. When messages need to include specific numbers, configure the bundle/resolver appropriately and **inspect the actual output** with a DTO having known min/max values. Avoid generic phrasing like "within limits" when API consumers need to know what those limits are.

### 6.2. Descriptions Differ from Runtime Validation Messages

| Item | Purpose | Example |
| --- | --- | --- |
| Annotation `message` | Report errors for invalid requests | `Email format is invalid` |
| Resource bundle `.description` | Explain the constraint in documentation | `Must provide a valid email` |

Both messages may share similar wording, yet serve different goals. Runtime messages belong to specific violations; documentation descriptions explain the rule to integrators.

## 7. Customizing Resolvers

`ConstraintDescriptions` supports constructors accepting custom resolvers. Two main abstractions:

- `ConstraintResolver` resolves constraints on classes/properties.
- `ConstraintDescriptionResolver` converts a constraint into a description.

~~~java
ConstraintDescriptions descriptions =
    new ConstraintDescriptions(
        RegisterMemberRequest.class,
        constraintResolver,
        descriptionResolver
    );
~~~

Both resolver variables must be implementations compatible with the API/version in use. A custom `ValidatorConstraintResolver` is helpful when a dedicated `Validator`/provider is needed. `ResourceBundleConstraintDescriptionResolver` or a custom `ConstraintDescriptionResolver` implementation is useful when changing wording, locale, or attribute formatting.

A custom resolver does not make every business rule appear automatically. Rules enforced only in the service/domain layer still require separate documentation and tests.

## 8. Nested Properties and Path Mapping

Example nested DTO:

~~~java
public class RegisterMemberRequest {
    @Valid
    private Address address;
}

public class Address {
    @NotBlank
    @Size(max = 120)
    private String city;
}
~~~

JSON:

~~~json
{"address":{"city":"Ho Chi Minh City"}}
~~~

| Path Type | Example | Purpose |
| --- | --- | --- |
| Bean property | `address.city` | Look up property metadata. |
| REST Docs field path | `address.city` | Document JSON field. |
| Array field path | `items[].sku` | Document field inside array elements. |

The first two path types often match in simple DTOs, though not always. If JSON mapping renames fields, map Java properties and JSON fields separately. For collection/container element constraints, do not assume the resolver maps everything to array syntax automatically; verify against your version/provider.

## 9. Class-Level and Cross-Field Constraints

Example rule where end date cannot precede start date:

~~~java
@ValidDateRange
public class BookingRequest {
    private LocalDate startDate;
    private LocalDate endDate;
}
~~~

This is an object-level constraint. Do not assume `descriptionsForProperty("startDate")` will automatically describe the relationship between the two dates.

Documentation should explain:

| Field/Rule | Constraint |
| --- | --- |
| `startDate` | Start date in ISO-8601 format. |
| `endDate` | End date in ISO-8601 format. |
| Relationship between fields | `endDate` must be on or after `startDate`. |

Document cross-field rules in prose or custom descriptors, and write HTTP tests for valid and invalid combinations. Rules such as uniqueness, resource ownership, credit limits, and workflows also need domain-level documentation and testing.

## 10. Combining with HTTP Tests

Example valid test using descriptions in request fields:

~~~java
@Test
void documentRegisterMember() throws Exception {
    ConstraintDescriptions constraints =
        new ConstraintDescriptions(RegisterMemberRequest.class);

    mockMvc.perform(post("/api/members")
            .contentType(MediaType.APPLICATION_JSON)
            .accept(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "fullName": "Lan Nguyen",
                  "email": "lan@example.com"
                }
                """))
        .andExpect(status().isCreated())
        .andDo(document("members-register",
            requestFields(
                fieldWithPath("fullName").description(
                    "Member name. " + String.join("; ",
                        constraints.descriptionsForProperty("fullName"))
                ),
                fieldWithPath("email").description(
                    "Contact email. " + String.join("; ",
                        constraints.descriptionsForProperty("email"))
                )
            )
        ));
}
~~~

This example assumes the endpoint has two fields and the request is valid. The test must reside in a class configured with MockMvc/REST Docs and corresponding imports.

Separate invalid test:

~~~java
@Test
void rejectInvalidMemberEmail() throws Exception {
    mockMvc.perform(post("/api/members")
            .contentType(MediaType.APPLICATION_JSON)
            .content("""
                {
                  "fullName": "Lan Nguyen",
                  "email": "not-an-email"
                }
                """))
        .andExpect(status().isBadRequest())
        .andDo(document("members-register-invalid"));
}
~~~

Status `400` is a contract assumption; the actual error handler may return a different status/body. When the error body has a schema, declare corresponding response fields. Document only outcomes verified by tests.

## 11. Final Documentation and CI

Asciidoctor can include:

~~~asciidoc
= Members API

== Register a Member

=== HTTP request
include::{snippets}/members-register/http-request.adoc[]

=== Request fields and constraints
include::{snippets}/members-register/request-fields.adoc[]

=== Validation error
include::{snippets}/members-register-invalid/http-response.adoc[]
~~~

The fields snippet only contains constraints if descriptions include them or a custom template renders metadata. The `snippets` attribute must point to the output directory. Plain Markdown renderers typically do not process Asciidoctor include syntax directly.

~~~mermaid
flowchart TD
    A["DTO / constraint changes"] --> B["HTTP tests: valid + invalid + boundary"]
    B --> C{"Assertions pass?"}
    C -->|No| D["Fail CI"]
    C -->|Yes| E["ConstraintDescriptions + descriptors"]
    E --> F["Generate REST Docs snippets"]
    F --> G["Render documentation"]
    G --> H{"Docs pass?"}
    H -->|No| D
    H -->|Yes| I["Review and publish"]
~~~

When annotations change, review bundles, descriptions, boundary tests, and documentation. Snippet generation does not automatically keep manual prose in sync. The render task must run after the snippet-generating test task and must not include leftover stale artifacts.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `descriptionsForProperty(...)` returns empty | Property has no constraints or wrong name | Check DTO and property path. |
| No constraints resolved | Missing provider or incompatible `Validator` | Check dependencies/provider/resolver. |
| Custom constraint has no description | Bundle is missing key | Add `.description` key or custom resolver. |
| Description lacks min/max | Incorrect bundle or attribute resolution | Check attributes and output. |
| Descriptions remain in English | Locale/bundle not configured | Create a bundle for the target language. |
| Nested field not found | Java property path differs from JSON field path | Separate mappings for the two path types. |
| Class-level rule does not appear | Default resolver focuses on property constraints | Document separately and write cross-field HTTP tests. |
| Annotation changed but docs did not | Manual description or template does not read metadata | Automate or review docs. |
| Custom attribute does not appear | Template does not render attribute | Update template and inspect snippet. |
| Description is stricter than validator | Misinterpreted semantics/provider | Check constraint and boundary tests. |

## 13. Practice Exercise

Create DTO `CreateProductRequest`:

~~~java
public class CreateProductRequest {
    @NotBlank
    @Size(min = 2, max = 100)
    private String name;

    @NotNull
    @DecimalMin("0.01")
    @DecimalMax("1000000.00")
    private BigDecimal price;

    @NotBlank
    @Pattern(regexp = "[A-Z0-9-]{3,20}")
    private String sku;
}
~~~

Steps:

1. Create `ConstraintDescriptions(CreateProductRequest.class)` and retrieve descriptions for `name`, `price`, and `sku`.
2. Change min/max values in annotations and observe the descriptions.
3. Create a localized resource bundle with `.description` keys; check locale/output.
4. Attach descriptions to `requestFields(...)` via descriptions or attributes.
5. If using attributes, customize a template with a Constraints column and verify the snippet.
6. Write HTTP tests for a valid request, price equal to 0, SKU failing the pattern, and name exceeding length.
7. Cross-check actual status/error responses against documentation, then build Asciidoctor.
8. Add a class-level rule if applicable and explain why separate documentation/tests are needed.

**Completion criteria:** you know how to resolve property constraints using `ConstraintDescriptions`, customize descriptive sentences, and display them in field snippets; understand the limitations of the default mechanism; and ensure documentation reflects validation logic verified by HTTP tests.

## Official References

- [Spring REST Docs — Bean Validation Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html)
- [Spring REST Docs — ConstraintDescriptions API](https://docs.spring.io/spring-restdocs/api/java/org/springframework/restdocs/constraints/ConstraintDescriptions.html)
- [Spring REST Docs — Request and Response Payloads](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/request-response-payloads.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
