# @NotNull, @NotBlank, @Size, @Pattern, and @Email

## Learning Objectives

In the **SPRING_REST_DOCS** module, request documentation needs to explain the conditions that input data must satisfy. Bean Validation provides standard annotations to express many common conditions. Five frequently used annotations are **@NotNull, @NotBlank, @Size, @Pattern, and @Email**.

When these annotations are declared on a DTO, Spring REST Docs can resolve the constraints of each property and provide descriptions for the request-fields snippet. This lets API documentation explain whether a field is required or optional, valid lengths, string formats, and email formats.

After this lesson, you will be able to:

- Distinguish the meaning and validation scope of each annotation.
- Choose the right annotation for the data type and business rule.
- Combine multiple constraints on a single property without creating false expectations.
- Declare constraints using Jakarta Validation in Spring Boot 3/4.
- Understand the difference between constraint annotations, running a Validator, and documenting constraints in REST Docs.
- Use ConstraintDescriptions to include constraint descriptions in API snippets.
- Write tests verifying both valid and invalid requests.

## 1. Overview of the Five Annotations

| Annotation | What Does It Check? | Typical Use |
| --- | --- | --- |
| **@NotNull** | Value must not be null | IDs, dates, objects, or required values |
| **@NotBlank** | String must not be null, empty, or whitespace-only | Names, usernames, required text fields |
| **@Size** | Size/length must be within min and max limits | String length, collection element count, map entry count |
| **@Pattern** | String must match a regular expression | Formatted identifiers, postal codes, product codes |
| **@Email** | String has a valid email format according to the validator | Email addresses in requests |

Example imports:

```java
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;
```

The annotations above belong to **Jakarta Bean Validation**. Spring Boot 3/4 typically uses package `jakarta.validation.constraints`. In legacy Spring Boot 2/Spring Framework 5 applications, the namespace is usually `javax.validation.constraints`; do not mix `javax` annotations with a Jakarta provider in the same configuration.

## 2. @NotNull — Rejecting Null Values

### 2.1. Meaning

@NotNull requires the property value not to be null.

```java
public class CreateOrderRequest {

    @NotNull
    private Long customerId;
}
```

For `@NotNull` alone:

| Value | Result |
| --- | --- |
| null | Invalid |
| 0L | Valid for `@NotNull` alone |
| 15L | Valid |

@NotNull does not check for positive numbers, negative numbers, value ranges, or whether the customer exists in the database. If the ID must be positive, add `@Positive`. If the ID must reference an existing record, perform business/service validation or use a custom constraint.

### 2.2. When to Use?

Use `@NotNull` for non-string types such as:

- Long customerId
- LocalDate deliveryDate
- BigDecimal amount
- Address address

For strings, `@NotNull` still allows empty strings and whitespace-only strings. If you want non-empty text that is not whitespace-only, use `@NotBlank`.

### 2.3. Combining with Other Constraints

```java
public class CreateOrderRequest {

    @NotNull
    @Positive
    private Long customerId;
}
```

Here `@NotNull` rejects null; `@Positive` requires a value greater than 0. Both annotations complement each other. `@Positive` generally treats null as valid so it can be combined with `@NotNull` when a value is required; check the constraint definition of your provider/API.

## 3. @NotBlank — String Must Not Be Empty or Whitespace-Only

### 3.1. Meaning

@NotBlank applies to strings. The value must not be null and must contain at least one non-whitespace character according to Bean Validation/provider rules.

```java
public class CreateUserRequest {

    @NotBlank
    private String displayName;
}
```

For `@NotBlank` alone:

| Value | Result |
| --- | --- |
| null | Invalid |
| "" | Invalid |
| "   " | Invalid |
| "An" | Valid |
| " An " | Valid; the annotation does not trim strings automatically |

@NotBlank does not normalize data. If the API should strip leading/trailing whitespace, do so explicitly during processing or use an appropriate normalization mechanism. Do not document that values are automatically trimmed just because the DTO has `@NotBlank`.

### 3.2. Distinguishing @NotBlank, @NotEmpty, and @NotNull

| Annotation | null | Empty String | Whitespace-Only String |
| --- | --- | --- | --- |
| @NotNull | Invalid | Valid | Valid |
| @NotEmpty | Invalid | Invalid | Valid |
| @NotBlank | Invalid | Invalid | Invalid |

Choose based on your requirement:

- Data only needs to be non-null: `@NotNull`.
- String/collection must have elements: `@NotEmpty`.
- String must have actual content, not just whitespace: `@NotBlank`.

@NotBlank is for `CharSequence`, not a general constraint for `List`, `Map`, or numbers. Use `@NotEmpty` or `@NotNull` for the appropriate types.

## 4. @Size — Limiting Length or Element Count

### 4.1. Meaning

@Size requires the size to fall within `min`/`max` bounds. Example:

```java
public class CreateProductRequest {

    @Size(min = 2, max = 80)
    private String name;
}
```

Both `min` and `max` bounds are inclusive:

| Length | Result with @Size(min=2,max=80) |
| --- | --- |
| 0 | Invalid |
| 1 | Invalid |
| 2 | Valid |
| 80 | Valid |
| 81 | Invalid |

For `String`, `@Size` checks string length as defined by the Bean Validation provider. For `Collection`, `Map`, and arrays, it checks the number of elements or entries.

### 4.2. @Size Does Not Make a Value Required

This is a common point of confusion:

```java
@Size(min = 2, max = 80)
private String nickname;
```

The Bean Validation `@Size` constraint accepts null so it can be combined with other constraints. If `nickname` is required, add:

```java
@NotBlank
@Size(min = 2, max = 80)
private String nickname;
```

If the field is optional but must have a valid length when provided, `@Size` alone may match your intent.

### 4.3. Limits for Collections and Maps

```java
public class CreateOrderRequest {

    @NotEmpty
    @Size(max = 20)
    private List<@NotNull Long> productIds;
}
```

In this example, `@NotEmpty` requires the list to be non-null and have at least one element; `@Size(max=20)` limits it to at most 20 elements; `@NotNull` on the element requires each ID to be non-null, provided the provider and configuration support type-use/container element validation.

Placing `@Size` only on the list does not automatically guarantee each element is valid.

### 4.4. String Length Does Not Equal Byte Count

@Size on a string does not express a UTF-8 byte limit on the payload. A single Unicode character may occupy multiple bytes when encoded. If the API enforces byte-length or HTTP body size limits, document and validate them separately at the appropriate layer.

## 5. @Pattern — Validating Strings with a Regular Expression

### 5.1. Meaning

@Pattern requires a string to match a regular expression:

```java
public class CreateProductRequest {

    @Pattern(regexp = "^[A-Z]{3}-[0-9]{4}$")
    private String productCode;
}
```

Valid examples: `ABC-1234`, `XYZ-0007`.

Invalid examples: `abc-1234` (lowercase), `AB-1234` (missing letter), `ABC-123` (missing digit), `ABC-12345` (extra digit), `ABC-1234-extra` (has suffix).

### 5.2. Pattern Does Not Automatically Require a Value

Like many format-checking constraints, `@Pattern` accepts null. If the field must be required:

```java
@NotBlank
@Pattern(regexp = "^[A-Z]{3}-[0-9]{4}$")
private String productCode;
```

If the field is optional, `@Pattern` alone permits null; an empty string does not match the expression above and is still invalid. Clarify whether the API treats an empty string as omitted, an empty value, or invalid data.

### 5.3. Java Regular Expressions

@Pattern uses Java's regular expression syntax (`java.util.regex.Pattern`), not automatically JavaScript, PCRE, or another engine's syntax.

| Syntax | Meaning |
| --- | --- |
| ^ | Start of string |
| $ | End of string |
| [A-Z] | One ASCII uppercase letter |
| [0-9] | One digit |
| {3} | Repeated exactly three times |
| {2,8} | Repeated two to eight times |
| + | One or more times |
| ? | Zero or one time |
| \\d in a Java string | Regex digit character class |

In Java source code, regex backslashes must be escaped according to string literal rules. For example, a regex using the digit class is written as:

```java
@Pattern(regexp = "\\d{4}")
private String year;
```

### 5.4. Be Careful with Overly Complex Regexes

Long regexes with many branches can be hard to understand, maintain, or expensive to evaluate on adverse inputs. Prefer:

- Defining named constants or custom annotations when expressions are long.
- Writing tests for both matching and non-matching samples.
- Avoiding regexes with dangerous backtracking on very long strings.
- Explaining the rule in plain prose in API docs; do not force consumers to decode regexes themselves.

## 6. @Email — Validating Email Address Format

### 6.1. Meaning

@Email checks whether a string has a valid email format according to the active Bean Validation implementation:

```java
public class CreateUserRequest {

    @NotBlank
    @Email
    private String email;
}
```

Common examples:

| Value | Typical Expectation |
| --- | --- |
| an@example.com | Valid |
| user.name+tag@example.org | Typically valid |
| user@ | Invalid |
| @example.com | Invalid |
| not-an-email | Invalid |

### 6.2. @Email Does Not Verify Email Existence

@Email only checks syntax according to the validator. It does not send an email, verify that the domain has an active mailbox, prove the user owns the address, or check whether the address is allowed in the system. When ownership verification is required, applications usually send a confirmation link or code and test that flow separately.

### 6.3. @Email and @NotBlank

In Bean Validation, `@Email` accepts null so it can be paired with a required constraint. If email is a required field, combine them:

```java
@NotBlank
@Email
private String email;
```

If email is optional, `@Email` alone can be used; clarify the policy for empty strings. An empty string is distinct from null and is generally not considered a valid email.

### 6.4. No Single Simple Email Regex Covers Every Case

Email formatting involves many rules and varies across validators. Do not assume `@Email` only accepts a trivial regex or guarantees support for every address form across all standards. If the API applies a specific policy, configure the validator or write a custom constraint, then document that exact policy.

## 7. Combining Annotations on a DTO

Example account creation DTO:

```java
package com.example.users;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public class CreateUserRequest {

    @NotBlank
    @Size(min = 2, max = 80)
    private String displayName;

    @NotBlank
    @Email
    @Size(max = 254)
    private String email;

    @NotBlank
    @Size(min = 12, max = 72)
    private String password;

    @NotNull
    private Long tenantId;

    @NotBlank
    @Pattern(regexp = "^[A-Z]{2}-[0-9]{6}$")
    private String invitationCode;

    // Getters/setters or record accessors
}
```

Explanation:

| Field | Rules | Meaning to Document |
| --- | --- | --- |
| displayName | NotBlank + Size | Required, 2–80 characters long |
| email | NotBlank + Email + Size | Required, email format, maximum 254 characters |
| password | NotBlank + Size | Required, 12–72 characters |
| tenantId | NotNull | Must not be missing a value |
| invitationCode | NotBlank + Pattern | Required, two uppercase letters, a hyphen, and six digits |

The limits in this example are **illustrative policies of one API**, not universal limits enforced by Bean Validation. Choose min/max and regexes according to real system requirements.

## 8. Does Bean Validation Actually Run on Incoming Requests?

Declaring annotations on a DTO only creates constraint metadata. For Spring MVC to trigger validation on a request body, the controller typically uses `@Valid` or `@Validated` as appropriate:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    @PostMapping
    ResponseEntity<Void> create(
            @Valid @RequestBody CreateUserRequest request) {
        // Save user
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

The application also needs a Bean Validation implementation on the classpath, such as the validation starter matching the Spring Boot version.

If `@Valid` is missing or validation is not enabled, requests can enter the controller even though the DTO has annotations. REST Docs may still read metadata to produce constraint descriptions; that does not prove the endpoint actually rejects invalid data.

### 8.1. Distinguishing Three Steps

| Step | Component | Purpose |
| --- | --- | --- |
| Declare annotations | DTO/model | Describe validation rules |
| Execute validation | Bean Validation + Spring MVC/WebFlux | Validate objects when requests arrive |
| Include descriptions in docs | REST Docs ConstraintDescriptions + field descriptor | Explain rules to API consumers |

These three steps are related but do not replace one another.

## 9. Using ConstraintDescriptions to Write Constraints into REST Docs

Spring REST Docs can resolve a property's constraints and turn them into descriptive sentences.

### 9.1. Creating ConstraintDescriptions

```java
import java.util.List;
import org.springframework.restdocs.constraints.ConstraintDescriptions;

ConstraintDescriptions constraints =
        new ConstraintDescriptions(CreateUserRequest.class);

List<String> emailRules =
        constraints.descriptionsForProperty("email");
```

`emailRules` contains descriptions for constraints found on the `email` property, such as `@NotBlank`, `@Email`, and `@Size`. Default descriptions can be adjusted via a resource bundle.

### 9.2. Attaching to a Request Field Descriptor

Example with MockMvc:

```java
import static org.springframework.restdocs.payload.PayloadDocumentation.fieldWithPath;
import static org.springframework.restdocs.payload.PayloadDocumentation.requestFields;
import static org.springframework.restdocs.mockmvc.MockMvcRestDocumentation.document;

List<String> emailRules =
        new ConstraintDescriptions(CreateUserRequest.class)
                .descriptionsForProperty("email");

this.mockMvc.perform(post("/api/users")
                .contentType(MediaType.APPLICATION_JSON)
                .content("""
                        {
                          "displayName": "An Nguyen",
                          "email": "an@example.com",
                          "password": "StrongPass123",
                          "tenantId": 10,
                          "invitationCode": "AB-123456"
                        }
                        """))
        .andExpect(status().isCreated())
        .andDo(document("users-create",
                requestFields(
                        fieldWithPath("displayName")
                                .description("Display name."),
                        fieldWithPath("email")
                                .description("Email address. " +
                                        String.join(" ", emailRules)),
                        fieldWithPath("password")
                                .description("User password."),
                        fieldWithPath("tenantId")
                                .description("Tenant ID."),
                        fieldWithPath("invitationCode")
                                .description("Invitation code.")
                )));
```

This example illustrates attaching descriptions into descriptors; the actual test class requires imports, MockMvc setup, controller, validation provider, and response assertions. Prefer creating `ConstraintDescriptions` once per DTO and reusing it.

### 9.3. Translating Descriptions into Vietnamese

Default constraint descriptions are typically in English. You can provide a resource bundle to replace them:

```properties
jakarta.validation.constraints.NotNull.description=Must not be null.
jakarta.validation.constraints.NotBlank.description=Must not be empty or contain only whitespace.
jakarta.validation.constraints.Size.description=Length or element count must be within the allowed limits.
jakarta.validation.constraints.Pattern.description=Value must match the specified pattern.
jakarta.validation.constraints.Email.description=Must be a valid email address format.
```

The resource bundle must be on the test/build classpath and follow the base name specified by Spring REST Docs. Key names must match the fully qualified class name of the constraint annotation plus the `.description` suffix. If the project has custom constraints, add corresponding keys or use a custom `ConstraintDescriptionResolver`.

## 10. Testing Each Constraint

You should test boundaries, not just a single valid example:

| Constraint | Valid Case | Invalid Cases to Test |
| --- | --- | --- |
| @NotNull | A non-null value | null |
| @NotBlank | "An" | null, "", "   " |
| @Size(min=2,max=4) | Length 2 and 4 | Length 1 and 5 |
| @Pattern(regexp="^[A-Z]{2}[0-9]{3}$") | AB123 | ab123, A123, AB1234 |
| @Email | user@example.com | user@, @example.com, non-email text |

You can test directly via `Validator`:

```java
Validator validator = Validation
        .buildDefaultValidatorFactory()
        .getValidator();

Set<ConstraintViolation<CreateUserRequest>> violations =
        validator.validate(request);

assertThat(violations).isEmpty();
```

In real tests, manage the `ValidatorFactory` lifecycle or use the Spring-provided `Validator` bean. For HTTP requests, test both error responses and success responses to document endpoint behavior.

## 11. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| `@NotNull` prevents empty strings | It only rejects null; use `@NotBlank` or `@NotEmpty` as intended |
| `@Size` automatically makes a field required | `@Size` accepts null; combine with `@NotNull`/`@NotBlank` if needed |
| `@Pattern` automatically makes a field required | `@Pattern` accepts null; add a required constraint when needed |
| `@Email` verifies the mailbox exists | It only checks format according to the validator |
| `@NotBlank` automatically trims strings | It does not modify input values |
| `@Size` on String is an HTTP byte limit | It does not describe payload byte limits |
| Having annotations means Spring definitely validates requests | Validation must be enabled on the controller with a provider present |
| `ConstraintDescriptions` executes validation | It reads metadata to produce descriptions |
| REST Docs automatically creates all constraint documentation | The application must pass descriptions into descriptors/templates |

## 12. Namespace and Version Notes

- Spring Boot 3/4 uses Jakarta Validation and package `jakarta.validation.*`.
- Spring Boot 2/Spring Framework 5 uses legacy Java EE with package `javax.validation.*`.
- Do not mix `javax.validation` APIs with a Jakarta Validation provider in the same application.
- Check Bean Validation API/provider and JDK versions; annotations in source code must come from the exact API being resolved.
- For custom annotations or constraints, verify the REST Docs resolver receives metadata and the resource bundle has matching descriptions.

## 13. Practice Exercise

1. Create the `CreateUserRequest` DTO with `displayName`, `email`, `password`, `tenantId`, and `invitationCode` per section 7.
2. Write Validator tests checking valid and invalid cases for all five annotations.
3. Enable validation on the controller with `@Valid` and verify error responses match the application's exception handling.
4. Use `ConstraintDescriptions` to retrieve descriptions for each property.
5. Create a localized resource bundle and confirm descriptions in the `request-fields` snippet are translated.
6. Try removing `@NotBlank` from `email` while keeping `@Email`; test null/empty strings and explain why format annotations do not automatically make a field required.
7. Try changing `max` on `@Size` and observe how constraint descriptions and boundary tests change.

**Self-Assessment Questions**

1. How does `@NotNull` differ from `@NotBlank`?
2. Why is `@Size` insufficient to make a field required?
3. What kind of regular expression does `@Pattern` use?
4. Can `@Email` verify whether an address exists?
5. When should you combine `@NotBlank` with `@Email`?
6. Is `@Size` on a String equivalent to a UTF-8 byte count limit?
7. Why do constraint annotations alone not prove an endpoint validates requests?
8. What role does `ConstraintDescriptions` play when generating REST Docs snippets?

## Official References

- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/): built-in constraint definitions, Validator, and metadata.
- [Jakarta Validation API — NotNull](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraints/notnull): `@NotNull` semantics.
- [Jakarta Validation API — NotBlank](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraints/notblank): non-blank string conditions.
- [Jakarta Validation API — Size](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraints/size): size bounds and supported types.
- [Jakarta Validation API — Pattern](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraints/pattern): regular expressions and flags.
- [Jakarta Validation API — Email](https://jakarta.ee/specifications/bean-validation/apidocs/jakarta/validation/constraints/email): email format constraint.
- [Spring REST Docs — Bean Validation Constraints](https://docs.spring.io/spring-restdocs/reference/documenting-your-api/constraints.html): `ConstraintDescriptions`, resolvers, and using constraint descriptions in documentation.
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html): integrating Bean Validation with Spring.

**Practical Takeaway:** Choose constraints according to exact data semantics: `@NotNull` checks for null, `@NotBlank` checks string content, `@Size` controls length/count, `@Pattern` checks regex formatting, and `@Email` checks email syntax. Enable real validation in the application, test boundary cases, and then use `ConstraintDescriptions` to place verified descriptions into Spring REST Docs request-field snippets.
