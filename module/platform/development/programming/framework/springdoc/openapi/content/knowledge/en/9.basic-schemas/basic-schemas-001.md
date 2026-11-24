# Schema Object and Mapping Java Types to OpenAPI Types

A schema is the part that describes the shape and data rules in an OpenAPI contract. It specifies whether a value is a string, number, boolean, object, or array; what properties an object has; which properties are required; and what format or constraints apply to the value. When using springdoc-openapi, schemas are usually inferred from the Java types of parameters, DTOs, and return types in Spring Boot controllers, and can then be supplemented with annotations and configuration.

Understanding how Java types map to OpenAPI helps verify whether the generated documentation accurately reflects the JSON that the application receives and returns. A Java type does not always translate into a single fixed schema: Jackson may rename or exclude properties, Bean Validation may add constraints, and the `@Schema` annotation may clarify or adjust the public description.

## 1. What Is a Schema Object Used to Describe?

In OpenAPI, a Schema Object describes a data structure based on a subset of JSON Schema rules. It is used in request bodies, responses, parameters, and reusable components.

A simple schema:

```yaml
type: object
required:
  - name
  - age
properties:
  name:
    type: string
    description: User name
  age:
    type: integer
    format: int32
    minimum: 0
```

The schema above describes an object with two properties: `name` and `age`. Both properties are listed in `required`; `name` is a string, and `age` is a 32-bit integer that is not less than 0.

Commonly used fields:

| Field | Meaning |
|---|---|
| `type` | Data type such as `string`, `integer`, `number`, `boolean`, `object`, or `array` |
| `format` | Additional format, such as `date`, `date-time`, `uuid`, `int32`, `int64` |
| `properties` | Properties of an object |
| `required` | List of required property names in an object |
| `items` | Schema of each element in an array |
| `enum` | Allowed set of values |
| `minimum`, `maximum` | Bounds for numeric values |
| `minLength`, `maxLength`, `pattern` | Constraints for strings |
| `minItems`, `maxItems`, `uniqueItems` | Constraints for arrays |
| `description` | Description of the meaning of the data |
| `example` | An illustrative example |
| `$ref` | Reference to a reusable schema or component |
| `readOnly`, `writeOnly`, `deprecated` | Usage characteristics of a property or schema |

A schema describes the data contract; it does not enforce validation inside the application. For example, `minimum: 0` helps tools understand the contract limit; to reject negative values when a request runs, the application still needs corresponding validation or business logic.

## 2. How Are Schemas Generated from Java Types?

Springdoc analyzes Spring endpoints, method signatures, data types, annotations, and related metadata. The library uses information from the Swagger Core, Jackson, and Bean Validation ecosystems to build the OpenAPI model.

Example:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    @GetMapping("/{id}")
    UserResponse getById(@PathVariable UUID id) {
        return userService.findById(id);
    }

    @PostMapping
    UserResponse create(@Valid @RequestBody CreateUserRequest request) {
        return userService.create(request);
    }
}
```

From the method signatures, springdoc can infer:

- `UUID id` is a path parameter with a string schema in UUID format.
- `CreateUserRequest` is the schema of the request body.
- `UserResponse` is the schema of the response content.
- Properties in the DTOs are analyzed to build object schemas, along with recognized constraints.

This is a metadata-based inference process. Java types are an important source of information, but they do not always reflect the entire actual JSON. Custom serializers, Jackson mixins, special getters, views, or property-exclusion configurations can make the payload differ from the Java class structure.

## 3. Mapping Common Scalar Types

Scalar types are single values such as strings, numbers, and booleans. The following table describes common mappings; specific formats may vary depending on the springdoc, Swagger Core, and OpenAPI versions and converter configuration.

| Java Type | Common OpenAPI Type | Notes |
|---|---|---|
| `String` | `string` | Does not automatically infer semantics such as email or postal code without metadata |
| `char`, `Character` | `string` | May require a length constraint if the contract requires exactly one character |
| `boolean`, `Boolean` | `boolean` | Primitive cannot be `null`; wrapper may be absent or null depending on the contract |
| `byte`, `short`, `int`, `Integer` | `integer`, usually `int32` | 32-bit integer in standard descriptions |
| `long`, `Long` | `integer`, usually `int64` | 64-bit integer |
| `float`, `Float` | `number`, usually `float` | Single-precision floating-point number |
| `double`, `Double` | `number`, usually `double` | Double-precision floating-point number |
| `BigDecimal`, `BigInteger` | `number` or `integer` | Format and precision should be confirmed against the serializer, library, and contract |
| `UUID` | `string`, `format: uuid` | UUID identifier string |
| `LocalDate` | `string`, `format: date` | Date without time |
| `LocalDateTime`, `OffsetDateTime`, `Instant` | Usually `string`, `format: date-time` | Requires agreement on time zone and serialization format |
| `LocalTime` | Usually `string` | Can add format and description according to API conventions |
| `byte[]` | Usually a string for binary/base64 representation | Requires defining the media type and how files or binary content are transmitted |

`format` adds meaning to `type`; it does not replace `type`. For example, a UUID still has `type: string`, while `format: uuid` describes the specific format. Similarly, `date-time` is a format of a string rather than a standalone data type.

Some formats are recognized by OpenAPI and common tools, but `format` is generally advisory metadata rather than an automatic runtime validator. If the API has specific rules, describe them clearly using `description`, `pattern`, bounds, or corresponding constraints.

## 4. Mapping Objects, Arrays, Collections, and Maps

### Objects from DTOs or POJOs

A Java class with properties is typically described as `type: object`, with each property placed under `properties`.

```java
public class Address {
    private String street;
    private String city;
    private String postalCode;

    // getters and setters
}

public class UserResponse {
    private UUID id;
    private String name;
    private Address address;

    // getters and setters
}
```

The corresponding schema can be organized using `$ref` to reuse `Address`:

```yaml
components:
  schemas:
    UserResponse:
      type: object
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
        address:
          $ref: '#/components/schemas/Address'
    Address:
      type: object
      properties:
        street:
          type: string
        city:
          type: string
        postalCode:
          type: string
```

Springdoc can generate schemas under `components.schemas` and reference them from operations. Schema names depend on the class name, schema naming configuration, generic types, and the library's model-processing rules.

### Arrays and collections

Java arrays, `List<T>`, `Set<T>`, and similar collections are typically described with `type: array`. The `items` field describes the type of each element.

```java
public class TeamResponse {
    private List<UserResponse> members;
    private Set<String> labels;

    // getters and setters
}
```

Illustrative schema:

```yaml
TeamResponse:
  type: object
  properties:
    members:
      type: array
      items:
        $ref: '#/components/schemas/UserResponse'
    labels:
      type: array
      items:
        type: string
```

For `Set`, the contract may express `uniqueItems: true` if metadata and tools support inferring that characteristic. Do not rely on the Java type name to assume every client tool will preserve set semantics; verify the actual schema and business requirements.

### Maps and objects with dynamic keys

A Map with string keys is typically described by an object with `additionalProperties` indicating the schema of the values:

```java
Map<String, String> labels;
Map<String, BigDecimal> prices;
```

```yaml
labels:
  type: object
  additionalProperties:
    type: string
prices:
  type: object
  additionalProperties:
    type: number
```

If Map keys are not fixed, `properties` cannot list all keys in advance. `additionalProperties` describes the type of dynamic values. If the API only allows a defined set of keys, consider using a DTO with explicit properties or additional constraints to make the contract easier to understand.

## 5. Enums and Valid Value Sets

Java enums are typically serialized as strings and can be described with `type: string` and `enum`.

```java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
```

Illustrative schema:

```yaml
OrderStatus:
  type: string
  enum:
    - PENDING
    - PAID
    - SHIPPED
    - CANCELLED
```

If Jackson uses `@JsonValue`, a custom serializer, or a configuration that converts enums to numbers or other strings, the public JSON values may differ from the enum constant names. In that case, inspect the actual output and add metadata so the schema reflects the serialized representation.

Example of an enum with custom public codes:

```java
public enum OrderStatus {
    PENDING("P"),
    PAID("Y"),
    CANCELLED("X");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String getCode() {
        return code;
    }
}
```

In this case, check how Swagger Core and Jackson configuration are integrated to verify whether the enum in OpenAPI is `P`, `Y`, `X` or the constant names. Do not assume the schema automatically follows every custom serialization approach.

## 6. `required`, Nullable, and Default Values

These three concepts are related but not synonymous:

- **Required:** the property must appear in the JSON object.
- **Nullable:** the property may appear with a `null` value.
- **Default:** the default value documented or applied according to API conventions when data is not provided.

For example, a property may be required to appear while still allowing `null`; another property may be optional to appear, but if present must have a non-null value. How nullability is represented depends on the OpenAPI version.

In OpenAPI 3.0, `nullable: true` is typically used to indicate that a value can be null:

```yaml
type: object
required:
  - nickname
properties:
  nickname:
    type: string
    nullable: true
  description:
    type: string
```

In this example, `nickname` must be present but may have a null value. `description` is not in the required list, so it may be omitted. If `description` is present, this example schema requires it to be a string.

OpenAPI 3.1 aligns more closely with JSON Schema and supports union-type representations with `null`, such as `type: [string, 'null']`. The specific syntax must match the OpenAPI version that springdoc is outputting; do not mix 3.0 and 3.1 syntax in the same schema.

### Java primitives and wrappers

Java primitives such as `int` or `boolean` cannot hold `null`; wrappers such as `Integer` or `Boolean` can hold `null`. However, a wrapper does not automatically mean a property is optional or nullable in every schema. Property presence and nullability also depend on Bean Validation, annotations, Jackson, the OpenAPI version, and library inference rules.

DTO example:

```java
public class CreateUserRequest {
    @NotBlank
    private String name;

    @NotNull
    @Positive
    private Integer age;

    private String nickname;

    // getters and setters
}
```

`@NotBlank` and `@NotNull` can help springdoc describe the corresponding properties as required via Bean Validation integration. `@Positive` can be mapped to a numeric bound if the constraint is supported. However, verify the generated schema rather than assuming every custom validation is translated into OpenAPI.

### Default values

`default` documents the default value according to the contract. It does not necessarily cause Spring to assign the value when a field is missing from a request. If the application needs to apply a default upon receiving a request, that logic must exist in a constructor, setter, binder, or appropriate processing layer.

```yaml
page:
  type: integer
  format: int32
  default: 0
  minimum: 0
```

Do not confuse `default` with `example`: default is the documented default value; example merely illustrates a usable value.

## 7. Data Constraints from Bean Validation

Bean Validation can add constraints to schemas. Common constraints:

| Annotation | Common OpenAPI Constraint |
|---|---|
| `@NotNull` | Property is required or non-nullable depending on location and integration version |
| `@NotBlank` | String must not be null, empty, or whitespace-only; may affect required and minLength |
| `@NotEmpty` | String, collection, or map must not be empty; may map to minLength/minItems or required |
| `@Size(min, max)` | `minLength`/`maxLength` or `minItems`/`maxItems` depending on type |
| `@Min`, `@Max` | `minimum`, `maximum` |
| `@DecimalMin`, `@DecimalMax` | Corresponding numeric bounds |
| `@Positive`, `@PositiveOrZero` | Lower bound for numeric values |
| `@Pattern` | `pattern` |
| `@Email` | Usually describes a string with email format or corresponding constraint |

Example:

```java
public class CreateProductRequest {
    @NotBlank
    @Size(max = 120)
    private String name;

    @NotNull
    @DecimalMin("0.01")
    @DecimalMax("999999999.99")
    private BigDecimal price;

    @Pattern(regexp = "^[A-Z0-9-]+$")
    private String sku;

    // getters and setters
}
```

Constraints can be represented in the schema so clients understand valid data. However, the validator is the component that enforces them when a request runs. A schema with `minLength: 1` does not guarantee the application will actually reject a whitespace-only string if the validator or runtime logic does not apply the right rule.

## 8. Customizing Schemas with `@Schema`

Springdoc infers schemas from Java types, but the `@Schema` annotation allows adding metadata or adjusting how descriptions are generated.

```java
@Schema(name = "CreateUserRequest", description = "Data for creating a new user")
public class CreateUserRequest {

    @Schema(
        description = "User's display name",
        example = "Nguyen Van A",
        maxLength = 100
    )
    @NotBlank
    private String name;

    @Schema(
        description = "Contact email address",
        example = "user@example.com",
        format = "email"
    )
    @Email
    private String email;

    // getters and setters
}
```

Commonly used `@Schema` attributes:

| Attribute | Purpose |
|---|---|
| `name` | Published schema name or property name |
| `description` | Description of the data's meaning |
| `type`, `format` | Specify type and format |
| `example` | Example value |
| `allowableValues` | Set of allowed values in certain usages |
| `minimum`, `maximum` | Numeric bounds |
| `minLength`, `maxLength` | String length bounds |
| `pattern` | Regular expression |
| `accessMode` | Mark property as read-only, write-only, or read/write |
| `hidden` | Hide schema or property from documentation where supported |
| `implementation` | Specify the implementation type used as the schema |

Do not use annotations to describe a data type different from the actual payload. If `@Schema(type = "string")` is placed on a property that serializes as an object, clients will receive an inaccurate contract. When changing schemas with annotations, verify the runtime JSON.

## 9. `readOnly`, `writeOnly`, and Request/Response DTOs

Some properties only appear in responses or are only sent in requests. OpenAPI supports `readOnly` and `writeOnly` to express this.

Example:

```yaml
User:
  type: object
  properties:
    id:
      type: string
      format: uuid
      readOnly: true
    password:
      type: string
      writeOnly: true
    name:
      type: string
```

In Java, this can be described using `@Schema(accessMode = Schema.AccessMode.READ_ONLY)` or `WRITE_ONLY` depending on the property and annotation version.

However, if requests and responses differ significantly in structure or rules, using two separate DTOs is usually clearer:

```java
public class CreateUserRequest {
    @NotBlank
    private String name;

    @Email
    private String email;

    // getters and setters
}

public class UserResponse {
    private UUID id;
    private String name;
    private String email;
    private Instant createdAt;

    // getters and setters
}
```

Separating DTOs helps avoid accidentally exposing internal fields, reduces confusion around required and nullable, and accurately reflects writable versus returned data.

## 10. Jackson and Actual JSON Types

Schemas must describe the JSON that the application actually serializes or deserializes. Jackson can affect property names and presence through annotations and configuration.

Example:

```java
public class UserResponse {
    @JsonProperty("display_name")
    private String name;

    @JsonIgnore
    private String internalNote;

    // getters and setters
}
```

The public JSON payload may contain `display_name` instead of `name` and omit `internalNote`. Springdoc integrates with Jackson to reflect many of these rules, but with custom serializers, mixins, views, or special serialization logic, you still need to check the generated documentation and actual JSON.

Situations to watch out for:

- `@JsonProperty` can rename a JSON property.
- `@JsonIgnore` can exclude a property from serialization/deserialization depending on configuration.
- `@JsonProperty(access = ...)` can adjust read/write direction.
- `@JsonFormat` can affect date/time or enum formatting.
- Custom serializers/deserializers can make the JSON value differ from the original Java type.
- Polymorphism, inheritance, and Jackson subtype metadata can affect `oneOf`, `allOf`, discriminators, or generated schemas.

Do not look solely at declared fields in a Java class to determine the schema. Check getters/setters, Jackson annotations, `ObjectMapper` configuration, and runtime output.

## 11. Generic Types and Reusable Schemas

Generic types are commonly used for wrapper response structures, such as `PageResponse<UserResponse>` or `ApiResponse<OrderResponse>`. Springdoc can analyze generic types to generate appropriate schemas, though auto-generated schema names can be long or vary across library versions.

```java
public class ApiResponse<T> {
    private T data;
    private String message;

    // getters and setters
}
```

Controller:

```java
@GetMapping("/{id}")
ApiResponse<UserResponse> getById(@PathVariable UUID id) {
    return userService.getById(id);
}
```

Semantically, the schema is an object with `data` of type `UserResponse` and `message` as a string. The actual component name generated by springdoc depends on generic resolution and model converter configuration.

If you need a stable schema name for a public contract, you can create a concrete DTO or configure the schema name using an appropriate annotation. Avoid renaming schemas already referenced by clients if the change impacts code generation or versioning.

## 12. Inspecting Schemas Generated by Springdoc

After declaring controllers, DTOs, and annotations, inspect the actual generated documentation:

1. Start the Spring Boot application.
2. Open `/v3/api-docs` or `/v3/api-docs.yaml`.
3. Locate the corresponding operation under `paths`.
4. Follow `$ref` to `components.schemas` to inspect the full definition.
5. Cross-check `type`, `format`, `properties`, `items`, `required`, nullable, and constraints.
6. Send valid and invalid requests to verify binding, serialization, and validation.
7. Compare actual JSON responses against the published schema.
8. Run an OpenAPI validator to detect malformed structures or invalid references.

For example, if a DTO has a `LocalDate`, the schema should represent a date string in the appropriate format; if the actual response serializes as a numeric timestamp instead, review the `ObjectMapper` or adjust the schema to match the actual contract.

Swagger UI is useful for viewing schemas and trying requests, but the UI does not replace checking JSON/YAML and runtime payloads. A well-rendered schema can still describe the wrong data.

## 13. Common Type-Mapping Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `Long` displays as string | Annotation or custom converter changed the type | Verify actual JSON type and schema metadata |
| Date/time is missing format | Custom type, Jackson format, or converter was not fully inferred | Add `@Schema(format = ...)` and check the serializer |
| Enum has values different from constant names | `@JsonValue` or custom serializer | Compare schema against serialized JSON values |
| Property is missing | `@JsonIgnore`, visibility, or mixin | Check Jackson configuration and public DTO |
| Field is not marked required | Constraint not recognized or annotation placed in wrong location | Check Bean Validation and `required` in schema |
| Wrapper misunderstood as nullable/optional | Confusing Java type, property presence, and null | Define required, nullable, and default separately |
| Collection is missing element schema | Generic type erased or raw collection type | Declare concrete generics, e.g., `List<UserResponse>` |
| Map schema does not describe dynamic values | Generic value type is unspecified | Use explicit `Map<String, T>` or a concrete DTO |
| Generic schema has unreadable name | Auto-generated model name from multiple type parameters | Create a concrete DTO or customize the schema name |
| Docs differ from runtime payload | Serializer, view, or Jackson config alters JSON | Test serialization and update metadata |

## 14. Schema Design Principles

- Design public DTOs around the JSON contract; do not let persistence entities dictate API schemas.
- Use concrete Java types and full generics so springdoc infers stable schemas.
- Distinguish `type` from `format`; format adds meaning to the base type.
- Define required, nullable, and default properties separately.
- Use Bean Validation for runtime-enforced constraints and check how they map to OpenAPI.
- Use `@Schema` to add descriptions, examples, and bounds that Java types cannot express.
- Inspect Jackson annotations and custom serializers because they affect the public JSON.
- Use reusable schemas when multiple endpoints share the same data structure.
- Separate request DTOs and response DTOs when read/write permissions or structures differ.
- Inspect the OpenAPI documentation alongside runtime payloads after every change affecting schemas.

## Summary

A Schema Object describes the type, structure, format, and constraints of data in an OpenAPI contract. Springdoc-openapi infers schemas from Java types, DTOs, generics, Jackson, and Bean Validation, and allows supplementing metadata with `@Schema`. Mapping is not just renaming Java types to `string`, `integer`, or `object`; it must also accurately express required, nullable, format, collections, enums, and actual JSON. Always verify the generated schema alongside runtime payloads to ensure the contract seen by clients accurately reflects the Spring Boot application.
