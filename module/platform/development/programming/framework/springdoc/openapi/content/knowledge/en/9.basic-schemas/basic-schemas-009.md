# Required Properties, requiredMode, and Nullability

When describing a request or response schema, two questions are frequently confused: **Must the client send this property?** and **If the property is sent, may its value be null?** OpenAPI expresses those two rules independently. A property can be required while still allowing null; it can also be optional, yet if present must have a non-null value.

With springdoc-openapi, schemas are usually generated from Java DTOs, OpenAPI annotations, and Bean Validation. The **@Schema(requiredMode = ...)** annotation lets you explicitly control whether a property is required. Nullability is described separately depending on the OpenAPI version: OpenAPI 3.0 uses **nullable**, whereas OpenAPI 3.1 uses JSON Schema syntax. Understanding these layers ensures the generated documentation accurately reflects the data the controller actually accepts.

## 1. Two Independent Questions: Must the Field Be Sent and May It Be Null?

Consider a customer creation request with three properties:

```json
{
  "email": "linh@example.com",
  "displayName": "Linh",
  "phone": null
}
```

Email and displayName must be provided. Phone may be omitted; if the client sends phone, the contract allows a null value. The first two properties are required, while phone is both optional and nullable.

In OpenAPI, the required list of an object schema enumerates property names that must appear. This rule does not by itself state whether the property can accept null. Nullability is expressed in the property's own schema.

OpenAPI 3.0 example:

```yaml
type: object
required:
  - email
  - displayName
properties:
  email:
    type: string
    format: email
  displayName:
    type: string
  phone:
    type: string
    nullable: true
```

Here:

- Email and displayName must appear in the object and have string values.
- Phone may be omitted.
- If phone appears, its value may be a string or null.

## 2. Distinguishing requestBody.required and schema.required

OpenAPI has two levels of required that often appear near each other:

| Location | Scope | Meaning |
|---|---|---|
| requestBody.required | Entire request body | Whether the client must send a body at all |
| schema.required | Object properties | Which fields must appear inside the object |

Example of a required body with only one required field:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        required:
          - name
        properties:
          name:
            type: string
          description:
            type: string
```

The client must send a JSON object and it must contain name. The description field may be omitted. If no body is sent, the request violates requestBody.required; if the body is an empty object, the body is present but the object is missing the name field.

Conversely, an operation may allow the body to be absent, yet if the client sends a body it must conform to the schema:

```yaml
requestBody:
  required: false
  content:
    application/json:
      schema:
        type: object
        required:
          - reason
        properties:
          reason:
            type: string
```

In this case, the client may omit the body. If an object is sent, reason must appear. The two levels of required answer different questions and do not replace each other.

## 3. Four States of a Property

Combining requiredness and nullability produces four cases:

| Property | Must Appear? | Allows Null? | Behavior |
|---|---:|---:|---|
| Required, non-nullable | Yes | No | Must send a valid, non-null value |
| Required, nullable | Yes | Yes | Must send the field; value may be null |
| Optional, non-nullable | No | No | Field may be omitted; if sent, must have a non-null value |
| Optional, nullable | No | Yes | Field may be omitted or sent as null |

OpenAPI 3.0 example covering all four cases:

```yaml
type: object
required:
  - id
  - middleName
properties:
  id:
    type: integer
    format: int64
  middleName:
    type: string
    nullable: true
  nickname:
    type: string
  secondaryPhone:
    type: string
    nullable: true
```

- ID: required and non-nullable.
- MiddleName: required but nullable.
- Nickname: optional and non-nullable.
- SecondaryPhone: optional and nullable.

The required-but-nullable case is useful when the contract requires clients to explicitly include the property in every request, even when there is no value yet. The optional-and-nullable case can be useful for certain update conventions, though the difference between omitting a field and sending null must be stated clearly.

## 4. requiredMode in the @Schema Annotation

Swagger Annotations provides requiredMode in @Schema to specify whether a property is required. Commonly used values:

| Value | Meaning |
|---|---|
| Schema.RequiredMode.AUTO | Let the library infer from existing metadata and configuration |
| Schema.RequiredMode.REQUIRED | Mark the property as required |
| Schema.RequiredMode.NOT_REQUIRED | Mark the property as optional |

Example:

```java
import io.swagger.v3.oas.annotations.media.Schema;

public record CreateCustomerRequest(
    @Schema(
        description = "Login email address.",
        requiredMode = Schema.RequiredMode.REQUIRED,
        example = "linh@example.com"
    )
    String email,

    @Schema(
        description = "Customer display name.",
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    String displayName,

    @Schema(
        description = "Secondary phone number, may not be provided yet.",
        requiredMode = Schema.RequiredMode.NOT_REQUIRED
    )
    String secondaryPhone
) {
}
```

AUTO is the default mode in many modern annotation versions. The library can infer from Java types, validation annotations, and other metadata. Inference results depend on the swagger-core/springdoc version and how the DTO is declared. For public contracts, explicitly set REQUIRED or NOT_REQUIRED on important fields and inspect the generated documentation.

requiredMode only controls whether the field must appear in the object. It is not a flag allowing null. To express nullability, use the representation suited to the OpenAPI version output by the application.

### 4.1. Do Not Confuse requiredMode with the Old required Attribute

Older versions of Swagger Annotations had a boolean required attribute on @Schema. In newer versions, requiredMode is the clearer declaration and replaces the old boolean usage in APIs where it has been marked deprecated. When upgrading dependencies, check the Javadoc for the version in use and prefer requiredMode if available.

Do not declare both required and requiredMode with conflicting values. When annotations, Bean Validation, and custom configuration conflict, the resulting documentation can be unpredictable.

## 5. Combining requiredMode with Bean Validation

Bean Validation checks data when a request is bound to a DTO. Some common annotations:

| Annotation | Validation Rule |
|---|---|
| @NotNull | Value must not be null |
| @NotBlank | String must not be null, empty, or whitespace-only |
| @NotEmpty | String, collection, or array must not be null and not empty |
| @Size(min, max) | Size limits for string, collection, or array |
| @Email | Validates value according to the validator's email rules |

DTO example:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
    @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank
    @Email
    String email,

    @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank
    @Size(max = 100)
    String displayName,

    @Schema(requiredMode = Schema.RequiredMode.NOT_REQUIRED, nullable = true)
    @Size(min = 1, max = 30)
    String phone
) {
}
```

Here, @NotBlank ensures email and displayName are non-null, non-empty, and not whitespace-only. @Email adds email format validation. This example uses OpenAPI 3.0 and allows phone to be omitted or null; if a non-null value is present, @Size requires a length from 1 to 30 characters.

For validation to run when the controller receives a request, enable validation—typically with @Valid on the @RequestBody parameter and the appropriate Bean Validation dependency:

```java
@PostMapping
public CustomerResponse create(
    @Valid @RequestBody CreateCustomerRequest request
) {
    return customerService.create(request);
}
```

OpenAPI annotations describe the contract for tools and readers. Bean Validation is what enforces constraints when handling requests. Do not declare only @Schema(requiredMode = REQUIRED) and assume Spring will automatically reject null values.

### 5.1. required and @NotNull Have Different Roles

requiredMode = REQUIRED tells API consumers that the field must appear in the JSON object. @NotNull is a validation rule on the value after Jackson converts JSON into a Java object.

Example:

- If the client omits the email field, Jackson may construct the DTO with null; @NotNull or @NotBlank will catch it when validation runs.
- If the client sends email as null, the post-binding value is also null; @NotNull will reject it.
- If the client sends an empty string, @NotNull does not reject an empty string; @NotBlank checks that case.

Using @NotNull on a field that is nullable by business rules creates a contradictory contract. Keep schema annotations, validation, and controller behavior aligned.

## 6. Distinguishing Nullability in OpenAPI 3.0 and 3.1

The syntax for allowing null depends on the specification version.

### 6.1. OpenAPI 3.0: using nullable

In OpenAPI 3.0, a schema can declare nullable: true alongside type:

```yaml
type: object
required:
  - note
properties:
  note:
    type: string
    nullable: true
```

The note field must appear, but its value may be a string or null. If nullable: true is omitted, a normal string schema does not accept null.

### 6.2. OpenAPI 3.1: using JSON Schema type

OpenAPI 3.1 is based on JSON Schema 2020-12. You can describe a string or null type using a union type:

```yaml
type: object
required:
  - note
properties:
  note:
    type:
      - string
      - "null"
```

Or use anyOf:

```yaml
note:
  anyOf:
    - type: string
    - type: "null"
```

In OpenAPI 3.1, do not use nullable: true as the standard way to add null to a data type. Use the corresponding JSON Schema syntax. Also check whether your Swagger UI, validator, and client generator versions support OpenAPI 3.1.

## 7. Declaring Nullability with Springdoc

Springdoc generates documentation according to the OpenAPI version configured and supported by the project. For OpenAPI 3.0, @Schema(nullable = true) can be used to describe a nullable property:

```java
public record CustomerProfile(
    @Schema(
        description = "Middle name; property must appear but may be null.",
        requiredMode = Schema.RequiredMode.REQUIRED,
        nullable = true
    )
    String middleName,

    @Schema(
        description = "Secondary phone number; may be omitted and may be null.",
        requiredMode = Schema.RequiredMode.NOT_REQUIRED,
        nullable = true
    )
    String secondaryPhone
) {
}
```

This example illustrates syntax for OpenAPI 3.0 documents. If the project outputs OpenAPI 3.1, verify how the springdoc/swagger-core version in use represents union types with null. Do not assume nullable = true in the annotation will automatically produce the desired 3.1 schema.

To check the document version, open /v3/api-docs and inspect the openapi field at the top of the JSON. Depending on the springdoc version, you can configure the API docs version using the springdoc.api-docs.version property with a value supported by the library. After changing it, verify the actual output rather than relying solely on configuration.

## 8. Java Primitives, Wrappers, and Nullability

Java types directly affect null representation after binding:

| Java type | Can Hold Null? | Default Value When Missing in Many Binding Cases |
|---|---:|---|
| int | No | 0 |
| long | No | 0 |
| boolean | No | false |
| Integer | Yes | null |
| Long | Yes | null |
| Boolean | Yes | null |
| String | Yes | null |
| BigDecimal | Yes | null |

If a numeric field is truly required and you need to detect when a client omits it, wrapper types like Integer or Long combined with @NotNull usually express intent more clearly than primitives. With primitives, a missing value can become the type's default value, making it hard for the application to distinguish a client omitting the field from sending 0 or false.

Example:

```java
public record UpdateSettingsRequest(
    @NotNull
    Integer pageSize,

    Boolean emailNotifications
) {
}
```

pageSize is required and must not be null. emailNotifications may be omitted or null if permitted by the contract. If the application needs to distinguish those two cases, the DTO and binding logic must preserve information about field presence.

## 9. Missing Fields vs. Sending Null on Updates

For PATCH operations, distinguishing an absent field from a field with a null value is especially important:

```json
{
  "displayName": "Linh Nguyen"
}
```

This request may mean updating only displayName while keeping other fields unchanged.

```json
{
  "displayName": "Linh Nguyen",
  "phone": null
}
```

The second request may mean clearing the phone number. However, if both cases map to a DTO with `String phone`, Jackson usually produces null both when the field is omitted and when the field is explicitly sent as null. Code then cannot distinguish the two intents solely from the property value.

There are several solutions:

- Use a patch DTO with a mechanism that records whether the field appeared in JSON.
- Use a standard format such as JSON Merge Patch if the contract needs a clear convention between omitting a field and null.
- Use a specialized wrapper type such as `JsonNullable<T>` with the corresponding Jackson module if the project has adopted that library.
- Split operations or design explicit request commands if updates have distinct business rules.

Do not claim that null means deleting a field if current binding cannot distinguish an omitted field from a field sent as null.

## 10. RequiredMode, Validation, and Schemas Can Create Contradictions

Certain configurations easily produce inconsistent documentation:

| Configuration | Contradiction |
|---|---|
| requiredMode = REQUIRED while DTO has no validation and code accepts null | Docs say field is required, but backend may accept null |
| requiredMode = NOT_REQUIRED alongside @NotNull | Schema says field may be omitted, but validation rejects null after binding |
| nullable = true alongside @NotNull | Schema allows null, but validation rejects it |
| Java primitive for a field documented as nullable | Java type cannot hold null |
| Non-required field with default in schema, backend applies no default | Docs suggest behavior the server does not perform |

When resolving contradictions, determine the business contract first, then align three layers:

1. OpenAPI Schema: required and nullability.
2. DTO/Bean Validation: Java types and constraints.
3. Processing logic: how the application interprets missing fields, null, and default values.

## 11. Complete Example: DTO and Schema for Customer Profile

Suppose a profile creation API has these rules:

- Email is required, must not be null, and must be a valid format.
- DisplayName is required and must not be null or whitespace-only.
- MiddleName must appear, but is allowed to be null.
- Phone is optional and nullable; if a non-null value is provided, length must be 1 to 30 characters.

In OpenAPI 3.0, the schema can be described as:

```yaml
type: object
required:
  - email
  - displayName
  - middleName
properties:
  email:
    type: string
    format: email
  displayName:
    type: string
    minLength: 1
  middleName:
    type: string
    nullable: true
  phone:
    type: string
    nullable: true
    minLength: 1
```

The Java DTO can be declared as:

```java
public record CreateProfileRequest(
    @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank
    @Email
    String email,

    @Schema(requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank
    String displayName,

    @Schema(
        requiredMode = Schema.RequiredMode.REQUIRED,
        nullable = true
    )
    String middleName,

    @Schema(
        requiredMode = Schema.RequiredMode.NOT_REQUIRED,
        nullable = true
    )
    @Size(min = 1, max = 30)
    String phone
) {
}
```

@Size allows null values and only checks length when the value is non-null. Thus this example is consistent with the contract for an optional and nullable phone: the field may be omitted or sent as null; if a string is sent, its length must be 1 to 30 characters. If business rules also forbid whitespace-only strings while still allowing null, a custom constraint with matching semantics is needed.

The example shows why required and nullable cannot be inferred from a single annotation alone. They must be coordinated according to business intent.

Specifically, middleName is a required yet nullable field. You cannot use @NotNull to check presence because that constraint also rejects a valid null value. If the backend must distinguish an omitted field from a field explicitly sent as null, check presence during deserialization. For records or constructor properties, consider Jackson metadata such as @JsonProperty(required = true) on the creator property, or use a custom deserializer; verify behavior with your project's Jackson version and write integration tests for both payloads. @Schema only describes the contract; it does not enforce field presence by itself.

## 12. Inspecting Schemas Generated by Springdoc

After starting the application, open the OpenAPI endpoint, typically /v3/api-docs. Find the corresponding schema under components.schemas and check:

1. Does the required list match the fields that must be present?
2. Is a required-yet-nullable field listed in required while also allowing null?
3. Was an optional field mistakenly added to required by annotations or validation?
4. Do Java primitive types produce schemas incompatible with nullability?
5. Does the null syntax match OpenAPI 3.0 or 3.1?
6. Do JSON examples accurately reflect both omitted fields and null fields?

You can use Swagger UI to try different payloads, but inspect the raw JSON/YAML because that is the contract consumed by client generators and validators.

### 12.1. Creating Validation Tests for DTOs

Constraints can be tested with Bean Validation in unit or integration tests. Example:

```java
@SpringBootTest
class CreateCustomerRequestValidationTest {

    @Autowired
    Validator validator;

    @Test
    void emailMustNotBeNull() {
        var request = new CreateCustomerRequest(
            null,
            "Linh",
            null
        );

        var violations = validator.validate(request);

        assertThat(violations)
            .anyMatch(v -> v.getPropertyPath().toString().equals("email"));
    }
}
```

This example assumes CreateCustomerRequest has the three components email, displayName, and phone as shown earlier, and the project has Bean Validation and AssertJ configured. This test verifies DTO constraints; it does not by itself verify the OpenAPI schema. Separate checks on the JSON/YAML document are needed to verify required and nullability.

## 13. Common Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Assuming required means non-null | Required-yet-nullable fields are misdescribed | Declare required and nullability independently |
| Using requestBody.required to mark a field | Entire body is mistakenly treated as required or optional | Put the required list inside the object schema |
| Using requiredMode to allow null | Schema fails to express nullability | Use nullable for OAS 3.0 or union type for OAS 3.1 |
| Using only @Schema(requiredMode = REQUIRED) for validation | Backend can still receive null | Add Bean Validation or checking logic |
| Using primitives where missing vs. null must be distinguished | Default values mask missing state | Use wrappers and appropriate constraints |
| Using @NotNull for strings that must also reject empty strings | Empty strings can still pass validation | Use @NotBlank or appropriate constraint |
| Using nullable: true in a 3.1 schema | Validators or generators may misinterpret it | Use JSON Schema union type or anyOf |
| Using a plain DTO for PATCH when missing/null must be distinguished | Jackson may map both to null | Use a presence-tracking type or patch format |
| Assuming AUTO always infers the intended contract | Results may vary by dependencies and metadata | Declare explicitly and inspect generated docs |

## 14. Takeaways

- requestBody.required determines whether the entire body is required.
- schema.required determines which properties of an object must appear.
- A field can be required yet nullable; it can also be optional yet non-nullable.
- @Schema(requiredMode = REQUIRED/NOT_REQUIRED/AUTO) controls field requiredness in the schema, not nullability.
- Bean Validation annotations such as @NotNull, @NotBlank, and @NotEmpty validate values when the application handles requests.
- OpenAPI 3.0 uses nullable: true; OpenAPI 3.1 uses JSON Schema syntax to allow null.
- Java primitives cannot hold null; wrappers express an unset state more clearly.
- For PATCH, clearly define the difference between an omitted field and a field sent with null.
- Always inspect JSON/YAML generated by springdoc and cross-check with validation and controller behavior.

When designing schemas for Spring Boot, decide two things separately: whether a field must appear in the request and whether null values are accepted. Then express that decision with appropriate requiredMode, nullability, Bean Validation, and binding logic. Consistency across these layers keeps Swagger UI, client generators, and the backend aligned on the same data contract.
