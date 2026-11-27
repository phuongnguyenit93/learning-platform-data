# Documenting Validation Constraints from Bean Validation

## 1. Goal: Making Validation Rules Part of API Documentation

Spring REST Docs produces verifiable REST API documentation from HTTP tests using MockMvc, WebTestClient, or REST Assured. For APIs that accept JSON, integrators need to know which fields are required, maximum lengths, email formats, numeric bounds, and related business rules. These rules are commonly declared using Bean Validation annotations such as `@NotNull`, `@NotBlank`, `@Size`, `@Email`, `@Min`, or `@Positive` on DTOs.

If you only document field names, types, and descriptions, readers know that `email` is a string but not that it must be a valid email format; they know `name` is a string but not its length limit. This practice combines Bean Validation metadata with Spring REST Docs to include constraints in the `request-fields` table.

Desired result:

| Path | Type | Description | Constraints |
| --- | --- | --- | --- |
| `name` | String | Customer's display name | Must not be blank; maximum 80 characters |
| `email` | String | Email address | Must be a valid email format |
| `age` | Number | Age | Must be greater than or equal to 18 |

Spring REST Docs provides the `ConstraintDescriptions` utility to read constraints from classes/properties and produce text descriptions. Tests still must verify requests and validation behavior; including constraints in snippets ensures documentation reflects metadata declared in DTOs.

## 2. Declaring Bean Validation on Request DTOs

Example customer creation API:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
        @NotBlank
        @Size(max = 80)
        String name,

        @NotBlank
        @Email
        String email,

        @Min(18)
        Integer age
) {
}
```

Annotations describing rules:

| Annotation | Meaning |
| --- | --- |
| `@NotNull` | Value must not be `null`. |
| `@NotBlank` | String must not be `null`, empty, or whitespace-only. |
| `@NotEmpty` | String/collection/map/array must not be `null` or empty; whitespace in a string may still be accepted. |
| `@Size(max = 80)` | Size must be within bounds; character count for strings, element count for collections. |
| `@Email` | Value must satisfy email format per the active validator. |
| `@Min(18)` | Numeric value must be greater than or equal to 18. |
| `@Positive` | Value must be greater than 0. |

Note: `@Size` typically permits `null`; if a field is required, combine it with `@NotNull` or `@NotBlank` as appropriate. `@Email` likewise does not replace `@NotBlank` when a field must not be omitted. Choose annotation combinations according to the endpoint's contract.

## 3. Enabling Validation at the HTTP Layer

For constraints to be enforced when clients send requests, the controller must trigger validation on the request body. With Spring MVC:

```java
@RestController
@RequestMapping("/api/customers")
class CustomerController {

    @PostMapping
    ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {
        CustomerResponse created = customerService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(created);
    }
}
```

The application needs a Bean Validation implementation compatible with the Spring/Jakarta Validation version in use. With Spring Boot, the validation starter dependency usually provides the necessary integration.

Do not confuse having annotations on a DTO with validation actually being enforced. If the controller lacks `@Valid`/`@Validated` in the right place, or a validation provider is missing from the classpath, requests may not be rejected as documented.

## 4. Reading Constraint Descriptions with Spring REST Docs

Spring REST Docs provides `ConstraintDescriptions` in the `org.springframework.restdocs.constraints` package:

```java
import org.springframework.restdocs.constraints.ConstraintDescriptions;

ConstraintDescriptions constraints =
        new ConstraintDescriptions(CreateCustomerRequest.class);

List<String> nameConstraints = constraints.descriptionsForProperty("name");
```

`descriptionsForProperty("name")` returns a list of constraint descriptions attached to the `name` property. By default, Spring REST Docs' resolver looks up descriptions based on constraint annotations and the Spring REST Docs resource bundle. When no custom description is provided, the default constraint description is used.

You can quickly inspect the output:

```java
System.out.println(constraints.descriptionsForProperty("name"));
```

Exact output depends on annotations, provider, and resource bundle. Do not rely on default ordering or phrasing if your documentation needs consistent custom wording; define custom descriptions as shown in the next section.

## 5. Customizing Constraint Descriptions with a Resource Bundle

To use consistent custom wording in your documentation, create a resource bundle following Spring REST Docs' constraint description resolver mechanism. A common location is `org/springframework/restdocs/constraints/ConstraintDescriptions.properties` in test resources; you can provide a locale variant such as `ConstraintDescriptions_vi.properties` depending on how the application resolves locales/resource bundles.

Example bundle contents:

```properties
NotBlank=Must not be blank or contain only whitespace
NotNull=Must not be null
NotEmpty=Must not be null or empty
Size=Size must be within allowed bounds
Email=Must be a well-formed email address
Min=Must be greater than or equal to the minimum value
Positive=Must be a positive number
```

Key names must match what the resolver looks up in your project's Spring REST Docs version. If using custom annotations or per-property descriptions, configure an appropriate `ConstraintDescriptionResolver` instead of assuming all resolvers use the same key convention.

With localized descriptions, verify which bundle is actually loaded at test runtime. Place the file at the proper resource path, ensure it is copied to the test classpath, and make sure it is not shadowed by a higher-priority bundle.

## 6. Integrating Constraints into Field Descriptors

Spring REST Docs does not automatically add a "Constraints" column to every `request-fields` snippet merely because a DTO has Bean Validation annotations. You need to retrieve the descriptions and include them in the field descriptor's description or a custom documentation structure.

Helper example:

```java
private static String descriptionWithConstraints(
        String description, List<String> constraints) {
    if (constraints.isEmpty()) {
        return description;
    }
    return description + ". Constraints: " + String.join("; ", constraints);
}
```

Usage in a test:

```java
ConstraintDescriptions constraints =
        new ConstraintDescriptions(CreateCustomerRequest.class);

mockMvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsBytes(request)))
        .andExpect(status().isCreated())
        .andDo(document("customers-create",
                requestFields(
                        fieldWithPath("name")
                                .description(descriptionWithConstraints(
                                        "Customer's display name",
                                        constraints.descriptionsForProperty("name"))),
                        fieldWithPath("email")
                                .description(descriptionWithConstraints(
                                        "Email address",
                                        constraints.descriptionsForProperty("email"))),
                        fieldWithPath("age")
                                .description(descriptionWithConstraints(
                                        "Customer age",
                                        constraints.descriptionsForProperty("age"))))));
```

The `request-fields.adoc` snippet will contain the field description along with constraints in the Description column. This approach is simple and requires no snippet template changes. If you want a dedicated column for constraints, you need a custom snippet template or custom AsciiDoc table built from metadata; no separate column is generated automatically by `ConstraintDescriptions` alone.

## 7. Reusing Descriptors to Avoid Duplication

When multiple tests document the same DTO, encapsulate field descriptors or shared helpers. Example:

```java
final class CustomerRequestDocumentation {

    private static final ConstraintDescriptions CONSTRAINTS =
            new ConstraintDescriptions(CreateCustomerRequest.class);

    private static String describe(String text, String property) {
        List<String> descriptions = CONSTRAINTS.descriptionsForProperty(property);
        return descriptions.isEmpty()
                ? text
                : text + ". Constraints: " + String.join("; ", descriptions);
    }

    static FieldDescriptor[] fields() {
        return new FieldDescriptor[] {
                fieldWithPath("name").description(describe("Customer name", "name")),
                fieldWithPath("email").description(describe("Contact email", "email")),
                fieldWithPath("age").description(describe("Age", "age"))
        };
    }
}
```

In a test:

```java
andDo(document("customers-create",
        requestFields(CustomerRequestDocumentation.fields())));
```

The example above illustrates code organization; add static imports for `fieldWithPath` and `FieldDescriptor`, and feel free to replace the helper with a builder matching your project's style. Do not create a static cache if tests need different resolvers/locales at runtime; in that case, inject or instantiate descriptions according to test configuration.

## 8. Documenting Nested and Collection Constraints

A DTO can contain nested objects:

```java
public record AddressRequest(
        @NotBlank @Size(max = 120) String street,
        @NotBlank @Size(max = 60) String city,
        @Pattern(regexp = "[0-9]{5}") String postalCode) {
}

public record CreateCustomerRequest(
        @NotBlank @Size(max = 80) String name,
        @Valid AddressRequest address) {
}
```

When documenting `address.street` and `address.city`, read constraints from the class owning those properties, `AddressRequest`, not from the root DTO:

```java
ConstraintDescriptions addressConstraints =
        new ConstraintDescriptions(AddressRequest.class);

fieldWithPath("address.street").description(
        descriptionWithConstraints("Street name", addressConstraints.descriptionsForProperty("street")))
```

For collections, the payload descriptor path might be `items[].quantity`; the class holding the annotations is the collection element type. Retrieve `ConstraintDescriptions` from the corresponding element class. If a property uses a container element constraint or type-use annotations, verify that your Bean Validation/provider version and Spring REST Docs can read that metadata as expected; do not assume every annotation placement is supported identically by the resolver.

## 9. Documenting Constraints for Validation Errors

APIs should also document responses when requests are invalid. For example, a controller returns `400 Bad Request` with a list of field errors:

```json
{
  "code": "VALIDATION_FAILED",
  "errors": [
    {
      "field": "email",
      "message": "Must be a valid email format"
    }
  ]
}
```

Tests can document the error operation separately:

```java
mockMvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":"An","email":"invalid","age":17}
                        """))
        .andExpect(status().isBadRequest())
        .andDo(document("customers-create-validation-error",
                responseFields(
                        fieldWithPath("code").description("Error code"),
                        fieldWithPath("errors[].field").description("Invalid field name"),
                        fieldWithPath("errors[].message").description("Validation message"))));
```

Actual error messages may differ from the resource bundle describing constraints. Constraint descriptions explain field rules; validation error messages report the specific violation in the response. The two are related but should not be conflated.

## 10. Verifying Constraints with Valid and Invalid Tests

Documentation is trustworthy only when tests verify both sides:

**Valid request:**

```java
mockMvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":"An","email":"an@example.com","age":25}
                        """))
        .andExpect(status().isCreated())
        .andDo(document("customers-create",
                requestFields(CustomerRequestDocumentation.fields())));
```

**Invalid request:**

```java
mockMvc.perform(post("/api/customers")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {"name":" ","email":"invalid","age":15}
                        """))
        .andExpect(status().isBadRequest())
        .andDo(document("customers-create-invalid",
                requestFields(CustomerRequestDocumentation.fields()),
                responseFields(
                        fieldWithPath("code").description("Error code"),
                        fieldWithPath("errors[].field").description("Invalid field"),
                        fieldWithPath("errors[].message").description("Error message"))));
```

Both tests must align with the application's actual error handling. If validation errors are mapped into a different schema, update the response descriptors accordingly. Ensure tests actually trigger validation via `@Valid` and the validation provider.

## 11. Distinguishing Constraint Descriptions and Validation Messages

Bean Validation can specify `message` on annotations:

```java
@NotBlank(message = "Name must not be blank")
@Size(max = 80, message = "Name must be at most 80 characters")
String name
```

`ConstraintDescriptions` provides constraint descriptions for documentation; the validation provider uses `message` when a constraint fails. The two systems serve different purposes:

| Item | Purpose | Example |
| --- | --- | --- |
| Constraint description | Explains the field rule in the API reference. | "Must not be blank; maximum 80 characters." |
| Validation message | Notifies the client/user when input violates a rule. | "Name must not be blank." |
| Error response | HTTP contract when a request is invalid. | `400` with `field` and `message`. |

If you want identical phrasing in documentation and responses, design your messages/resource bundles deliberately and test both. Do not assume `ConstraintDescriptions` automatically extracts the annotation's `message` across all configurations.

## 12. Limitations to Keep in Mind

- `ConstraintDescriptions` reads constraint metadata; it does not run validators and does not prove the endpoint enforces validation.
- Custom class-level constraints may not attach directly to a single field. Document them at the object level or describe the business rule separately.
- Cross-field validation (such as `startDate` must be before `endDate`) usually requires a class-level validator; do not force it into a single field's constraints if that would be misleading.
- Constraints on getters/property access, field access, container elements, or type-use locations must be verified against your provider and version.
- Length/value constraints may depend on validation groups. `ConstraintDescriptions` does not automatically pick the group used by the controller for a request.
- Custom annotations need an appropriate description resolver/resource bundle; otherwise descriptions may be missing or fall back to unclear defaults.
- Do not document internal constraints outside the public contract if doing so exposes unnecessary implementation details.

## 13. Common Errors

| Symptom | Cause | Resolution |
| --- | --- | --- |
| `descriptionsForProperty` returns an empty list | Property has no constraints, wrong property name, or resolver could not find metadata. | Check the DTO, getter/field access, and property name. |
| Constraint description falls back to default English | Localized resource bundle was not loaded or keys do not match. | Check bundle path, locale, and resolver lookup. |
| Test passes but validation does not run | Controller is missing `@Valid`/`@Validated` or provider is missing. | Check invalid HTTP test and validation dependencies. |
| Request fields snippet has no constraints | Field descriptors still use static descriptions. | Combine `ConstraintDescriptions` into descriptor descriptions. |
| Nested field has no description | Reading constraints from root DTO instead of child class. | Create `ConstraintDescriptions` for the nested type. |
| Optional field documented as required | DTO annotations or descriptions do not reflect the contract. | Check `@NotNull`/`@NotBlank`, groups, and actual optionality. |
| Error response message differs from constraint description | The two systems serve different purposes. | Document rules and error messages separately, and test both. |
| Custom constraint has no description | Resolver/bundle has no mapping for the annotation. | Add a description or custom resolver. |
| Constraint group does not match request | Controller validates a different group than default. | Document the actual group and test the corresponding behavior. |

## 14. Practice Checklist

- [ ] Request DTOs have Bean Validation annotations matching the API contract.
- [ ] Controller enables validation with `@Valid`/`@Validated` appropriately.
- [ ] Validation provider is on the runtime classpath.
- [ ] `ConstraintDescriptions` reads the right class and property.
- [ ] Resource bundle describing constraints uses the right locale/language.
- [ ] Field descriptors include constraint descriptions in snippets.
- [ ] Nested properties pull metadata from the right nested type.
- [ ] Class-level/cross-field constraints are explained at the appropriate level.
- [ ] Valid and invalid request tests verify actual behavior.
- [ ] Validation error responses are documented separately if part of the public contract.
- [ ] Constraint descriptions and validation messages are kept distinct.
- [ ] Generated `request-fields.adoc` and final HTML/PDF display the descriptions accurately.

Combining Bean Validation with Spring REST Docs helps your API reference clearly describe the input rules clients must satisfy. `ConstraintDescriptions` provides descriptions from metadata; field descriptors place that content into snippets; HTTP tests confirm the endpoint actually accepts or rejects requests according to the rules. Keeping constraint descriptions, validation error messages, and error responses separate makes documentation accurate, clear, and verifiable.

## References

- [Spring REST Docs – Constraint Descriptions](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html)
- [Spring REST Docs – ConstraintDescriptions API](https://docs.spring.io/spring-restdocs/docs/current/api/org/springframework/restdocs/constraints/ConstraintDescriptions.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)
- [Spring Framework – Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
