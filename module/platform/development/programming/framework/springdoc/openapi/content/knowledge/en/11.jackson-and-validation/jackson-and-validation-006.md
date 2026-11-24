# `@NotNull`, `@NotBlank`, `@Size`, and Inferable Information

Bean Validation lets an application validate input data against constraints declared on DTOs. Springdoc can read many common constraints to enrich the OpenAPI schema, such as required properties, string lengths, or collection item counts. Thus, the same set of annotations can both validate requests at runtime and provide metadata for clients through API documentation.

The three annotations `@NotNull`, `@NotBlank`, and `@Size` have different scopes and meanings. Choosing the right annotation prevents situations where documentation marks a field as required yet the application accepts blank input, or where documentation shows bounds that the server never enforces.

## 1. Bean Validation in a Spring Boot Application

Bean Validation is a mechanism for declaring constraints on fields, properties, parameters, or types. When validation is triggered, the provider checks the object and returns any constraint violations.

With Spring Boot 3, standard annotations belong to the `jakarta.validation` package. Spring Boot 2 applications typically use the legacy `javax.validation` namespace. Do not mix both namespaces in the same configuration if your project dependencies do not support both.

With Spring Boot 3, the standard dependency is:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>
```

Spring Boot dependency management handles the appropriate version. This starter brings the Bean Validation API and required provider into the application. If you declare annotations without a validation provider or without triggering validation in the request flow, constraints may not be enforced at runtime.

In Spring MVC, mark the request DTO with `@Valid` to instruct Spring to validate the object after deserialization:

```java
@PostMapping("/api/users")
public ResponseEntity<Void> create(
        @Valid @RequestBody CreateUserRequest request) {
    return ResponseEntity.status(HttpStatus.CREATED).build();
}
```

`@Valid` triggers validation for the object and enables cascading validation into nested objects when their properties are also marked with `@Valid`. For validation groups or method validation, `@Validated` and configuration matching your Spring version may be needed. `@Valid` does not define constraints by itself; constraints must be declared on the DTO or parameter.

## 2. `@NotNull`: Value Must Not Be Null

`@NotNull` requires the value to be non-`null`. This annotation can be applied to many reference types such as `String`, `Integer`, DTOs, collections, and other objects.

```java
import jakarta.validation.constraints.NotNull;

public record UpdateProductRequest(
    @NotNull
    Integer quantity
) {}
```

Values are evaluated as follows:

| Value | Result with `@NotNull` |
| --- | --- |
| `null` | Invalid |
| `0` | Valid |
| `10` | Valid |
| `""` for `String` | Valid |
| `"   "` for `String` | Valid |

`@NotNull` checks only that a non-null value exists. For strings, it does not ensure the string has content. For numbers, it does not ensure the number is positive. If business rules require quantity greater than 0, add an appropriate constraint such as `@Positive` or `@Min(1)`.

In the OpenAPI schema, `@NotNull` typically helps Springdoc mark a property as required or non-nullable depending on the OpenAPI version and configuration in use. Distinguish two ideas: the property must appear in the object, and the property value must not be null. Verify `required` and nullability representation in the generated document.

## 3. `@NotBlank`: String Must Contain a Non-Whitespace Character

`@NotBlank` applies to `CharSequence`, such as `String`. The value must be non-null and, after trimming whitespace characters, must have at least one content character.

```java
import jakarta.validation.constraints.NotBlank;

public record CreateUserRequest(
    @NotBlank
    String displayName
) {}
```

Example results:

| Value | Result with `@NotBlank` |
| --- | --- |
| `null` | Invalid |
| `""` | Invalid |
| `"   "` | Invalid |
| `"Lan"` | Valid |
| `" Lan Nguyen "` | Valid |

`@NotBlank` differs from `@NotNull` and `@NotEmpty`:

| Annotation | Disallows null | Disallows empty string | Disallows whitespace-only |
| --- | --- | --- | --- |
| `@NotNull` | Yes | No | No |
| `@NotEmpty` | Yes | Yes | No |
| `@NotBlank` | Yes | Yes | Yes |

With `@NotBlank`, Springdoc can typically infer that the field is required and the string has a minimum length greater than 0. However, OpenAPI `minLength: 1` does not fully capture the rule rejecting whitespace-only strings. If documentation should express this more clearly, add a field description or suitable pattern and inspect the generated schema.

Do not use `@NotBlank` on `Integer`, `Long`, `Boolean`, or collections; those types are not `CharSequence` and are incompatible with this constraint.

## 4. `@Size`: Constraining Size or Length

`@Size` sets minimum and maximum bounds on a value. The annotation supports `CharSequence`, collections, maps, and arrays. Both `min` and `max` are inclusive bounds.

```java
import jakarta.validation.constraints.Size;

public record ProfileRequest(
    @Size(min = 2, max = 80)
    String fullName
) {}
```

For strings, `@Size` checks length. For collections or arrays, it checks element count; for maps, it checks entry count.

| Data Type | What `@Size` Checks | Inferable OpenAPI Info |
| --- | --- | --- |
| `String` or `CharSequence` | String length | `minLength`, `maxLength` |
| `List`, `Set`, collection | Element count | `minItems`, `maxItems` |
| Array | Element count | `minItems`, `maxItems` |
| `Map` | Key/value entry count | `minProperties`, `maxProperties` |

An important note: `@Size` allows `null`. If a field must both have a value and stay within size bounds, combine `@NotNull` or `@NotBlank` depending on the data type.

Example:

```java
public record CreateProductRequest(
    @NotBlank
    @Size(min = 3, max = 80)
    String name,

    @NotNull
    @Size(min = 1, max = 10)
    List<String> labels
) {}
```

Here `name` cannot be null, empty, or whitespace-only, and must fall within the size bounds. `labels` must be present and contain 1 to 10 items. If only `@Size(min = 1, max = 10)` were placed on `labels`, a null value would still satisfy the `@Size` constraint.

`@Size` does not constrain numeric values. For example, do not put `@Size(min = 1, max = 100)` on `Integer quantity`; use numeric constraints like `@Min`, `@Max`, or `@Positive`.

## 5. Combining Constraints on One Field

A single field often needs multiple conditions at once. Constraints on the same field apply simultaneously; the data must satisfy all of them.

Example account registration DTO:

```java
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record RegisterUserRequest(
    @NotBlank
    @Size(min = 3, max = 40)
    String username,

    @NotBlank
    @Size(max = 120)
    String fullName,

    @NotNull
    Integer age
) {}
```

Meaning:

- `username` must have non-blank content and be 3 to 40 characters long.
- `fullName` must have non-blank content and not exceed 120 characters.
- `age` must not be null; numeric age bounds need separate numeric constraints if business rules require them.

Springdoc can combine metadata to document required status and bounds. A simplified schema might look like:

```yaml
RegisterUserRequest:
  type: object
  required:
    - username
    - fullName
    - age
  properties:
    username:
      type: string
      minLength: 3
      maxLength: 40
    fullName:
      type: string
      minLength: 1
      maxLength: 120
    age:
      type: integer
```

This is an illustrative structure. The actual schema may vary in `required` lists, nullability, descriptions, and inference details depending on Springdoc, swagger-core, and Bean Validation versions. In particular, `minLength: 1` cannot fully express the “not whitespace-only” rule of `@NotBlank`.

## 6. Constraints on Collections and Their Elements

`@Size` on a collection checks the number of elements, not the content of each element. If every element must also be valid, place constraints on the element type and enable nested validation.

```java
import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotEmpty;
import jakarta.validation.constraints.Size;
import java.util.List;

public record CreateArticleRequest(
    @NotEmpty
    @Size(max = 5)
    List<@NotBlank String> tags,

    @Valid
    @NotNull
    AuthorRequest author
) {}

public record AuthorRequest(
    @NotBlank
    @Size(max = 80)
    String name
) {}
```

In this example:

- `@NotEmpty` requires the list to be non-null and contain at least one element.
- `@Size(max = 5)` caps the list at five elements.
- `@NotBlank` on the `String` element requires each tag to have non-blank content.
- `@Valid` on `author` triggers validation on the nested object.

With Springdoc, collection bounds can be represented via `minItems` and `maxItems`; element constraints can be placed inside the `items` schema. Inspect `/v3/api-docs` to confirm the exact structure.

## 7. Enabling Validation on Controllers

Complete controller example:

```java
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    @PostMapping
    public ResponseEntity<Void> create(
            @Valid @RequestBody CreateProductRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).build();
    }
}
```

If the request violates a constraint, Spring MVC normally returns `400 Bad Request` due to request-body validation failure. The exact error JSON structure depends on the exception handler and how the application standardizes errors. Springdoc cannot automatically know a custom error response body unless the team documents it.

You can declare the error response using `@ApiResponse` and `@Content` with the application's error schema. Use the exact error type actually returned by your exception handler; do not document a generic example payload if runtime produces a different structure.

## 8. What Information Does Springdoc Infer?

Springdoc integrates with swagger-core and can read metadata from Bean Validation. Common constraints add restrictions to the schema without repeating every bound in `@Schema`.

| Bean Validation | Inferable OpenAPI schema info |
| --- | --- |
| `@NotNull` | Field/parameter required or non-nullable depending on context |
| `@NotBlank` | Field required; typically minimum string length of 1 |
| `@Size(min, max)` on strings | `minLength`, `maxLength` |
| `@Size(min, max)` on collections/arrays | `minItems`, `maxItems` |
| `@Size(min, max)` on maps | `minProperties`, `maxProperties` |

Exact inference capabilities depend on the Springdoc, swagger-core, and OpenAPI versions, as well as the validation namespace (`jakarta` or `javax`). Annotations can be placed on fields, getters, record components, or type-use positions; how the library discovers metadata can also depend on annotation placement and DTO structure.

Springdoc documents constraints in the contract, but it does not replace the validation provider. Conversely, runtime validation can run even if the schema does not reflect every rule. Always verify both actual validation responses and the OpenAPI specification.

## 9. When Should You Add Explicit `@Schema`?

If inferred metadata is not clear enough, use `@Schema` to supplement descriptions, examples, formats, or desired constraints:

```java
public record CreateProductRequest(
    @NotBlank
    @Size(min = 3, max = 80)
    @Schema(
        description = "Product name, non-blank and 3 to 80 characters",
        example = "Mechanical Keyboard"
    )
    String name
) {}
```

Prefer Bean Validation as the source of enforced constraints; `@Schema` adds explanation for API consumers. If you repeat bounds in both places, they must match. For example, never declare `@Size(max = 80)` alongside `@Schema(maxLength = 100)`, because the docs would permit inputs the server rejects.

If you need to override requiredness when Springdoc does not infer it as desired, you can use `@Schema(requiredMode = Schema.RequiredMode.REQUIRED)` or `NOT_REQUIRED` as needed. Override only after verifying actual behavior; OpenAPI annotations do not alter Bean Validation.

Never use `@Schema` as a substitute for `@NotBlank`, `@NotNull`, or `@Size` when the application needs those constraints enforced at runtime.

## 10. Distinguishing Required, Nullable, and Size Limits

Three concepts are frequently confused:

- **Required:** whether a property or parameter must be provided.
- **Nullable:** whether the value may be `null`.
- **Size/length constraint:** whether the value falls within length or element-count bounds.

For example, a string might be optional, yet if supplied must be 3 to 40 characters long. In that case, the property is omitted from the `required` list while its schema still includes `minLength` and `maxLength`. With `@Size`, null is accepted; to forbid null, combine the appropriate constraint.

`@NotBlank` forbids null, empty strings, and whitespace-only strings. `@NotNull` forbids null but allows empty strings. `@Size` bounds size without forbidding null. Understanding these differences ensures the schema accurately reflects when clients may omit a field, send null, or send an empty string.

## 11. Inspecting the Schema Generated by Springdoc

After starting the application, open `/v3/api-docs` or `/v3/api-docs.yaml` and locate the DTO schema. Check:

1. Fields with `@NotNull` or `@NotBlank` are marked required as expected.
2. `@Size` on strings produces appropriate length limits.
3. `@Size` on collections/arrays produces element-count limits.
4. Collection element constraints appear inside the `items` schema where supported.
5. Descriptions and examples from `@Schema` do not contradict constraints.
6. The request body references the right DTO schema.

Illustrative schema:

```yaml
CreateProductRequest:
  type: object
  required:
    - name
    - labels
  properties:
    name:
      type: string
      minLength: 3
      maxLength: 80
      description: Product name
    labels:
      type: array
      minItems: 1
      maxItems: 10
      items:
        type: string
```

Actual output may include additional `items` constraints, formats, examples, `$ref`, or different nullability representations. Swagger UI can display these limits in the schema section; the JSON/YAML document is the primary source of truth for verifying metadata.

## 12. Verifying Validation at Runtime

Do not check the schema alone—send valid and invalid payloads to confirm Bean Validation is active.

Valid payload example:

```json
{
  "name": "Mechanical Keyboard",
  "labels": ["keyboard", "accessory"]
}
```

Blank-name example:

```json
{
  "name": "   ",
  "labels": ["keyboard"]
}
```

Overlong names or lists with too many elements should also be rejected if they exceed declared constraints. When a request is invalid, verify the status code and error body produced by your application's exception handler.

If the schema shows bounds yet invalid requests are still accepted, check the `spring-boot-starter-validation` dependency, `@Valid` on the controller parameter, and annotation placement. If runtime rejects properly yet the schema lacks constraints, check annotation namespaces, placement, and Springdoc/swagger-core versions.

## 13. Common Pitfalls

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| `@NotBlank` fails to compile on numeric field | Constraint only applies to `CharSequence` | Use a constraint suited to numeric types |
| Null field is still accepted despite `@Size` | `@Size` allows null | Combine with `@NotNull` or `@NotBlank` |
| Whitespace-only string passes validation | Only `@NotNull` or `@Size` was used | Use `@NotBlank` |
| Constraints do not run on API calls | Missing validation provider or `@Valid` | Add validation starter and enable validation |
| Schema lacks `minLength`/`maxLength` | Misplaced constraint, incompatible namespace, or library version | Check imports, DTO, and OpenAPI output |
| Docs mark field required yet server accepts null | Required/nullability metadata and runtime are out of sync | Check constraints and `@Schema` overrides |
| Schema limits differ from runtime | `@Schema` and Bean Validation declare different values | Use Bean Validation as enforced source and sync metadata |
| Nested validation does not run | Missing `@Valid` on nested object property | Annotate the property with `@Valid` |
| Collection has valid size yet contains blank item | Only `@Size` on collection | Add element constraint like `List<@NotBlank String>` |

## 14. Checklist for Constraints and Inferred Schemas

- [ ] Use the proper `jakarta.validation` namespace for Spring Boot 3 or `javax.validation` for legacy generations.
- [ ] Validation provider is present on the runtime classpath when enforcing constraints.
- [ ] Use `@NotNull` when only null needs to be disallowed.
- [ ] Use `@NotBlank` for required strings that must contain non-whitespace content.
- [ ] Use `@Size` for string length, collection/array size, or map entry count.
- [ ] Combine constraints when both presence and size limits are required.
- [ ] Use `@Valid` to enable validation on request DTOs and nested objects.
- [ ] Add `@Schema` for descriptions/examples without contradicting runtime constraints.
- [ ] Verify required, nullability, minLength/maxLength, and minItems/maxItems in `/v3/api-docs`.
- [ ] Test both valid and invalid payloads to confirm runtime enforces the same contract.

`@NotNull`, `@NotBlank`, and `@Size` describe different aspects of data. Spring Boot uses Bean Validation to enforce these rules when requests are validated; Springdoc can infer many constraints into OpenAPI metadata. Keeping constraints, DTOs, `@Valid`, and schemas aligned helps clients know which fields are required and constrain inputs before calling the API.
