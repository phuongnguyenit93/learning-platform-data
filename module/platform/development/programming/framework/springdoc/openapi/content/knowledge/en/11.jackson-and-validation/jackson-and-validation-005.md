# Java Nullability Differs from Missing Properties in JSON

In a JSON request, an omitted property and a property present with a `null` value are two distinct states. For example, `{"name":"An"}` is not the same as `{"name":"An","nickname":null}`. However, after Jackson converts JSON into a Java object, both states can become `null` in a wrapper field or retain a default value in a primitive field. Without explicitly distinguishing them, an application may update data incorrectly, apply validation improperly, or publish a misleading OpenAPI contract.

With `springdoc-openapi`, you need to separately document whether a property is required to be present and whether a `null` value is accepted. These two concepts correspond to `required` and `nullable` in OpenAPI 3.0, or union types containing `null` in OpenAPI 3.1. Jackson determines how JSON is deserialized; Bean Validation validates object state after binding; OpenAPI documents the contract for clients. All three layers must be designed consistently.

## 1. Missing Properties vs. Properties with a `null` Value

Consider two requests:

```json
{
  "name": "Nguyen Van A"
}
```

```json
{
  "name": "Nguyen Van A",
  "nickname": null
}
```

In the first request, the `nickname` property is absent from the JSON object. In the second request, the property is present and its value is `null`.

This difference often carries business meaning:

- **Missing property:** the client did not send information for that field. The server may keep the current value, apply a default, or follow a specific rule.
- **Property equal to `null`:** the client sent an explicit signal that the value is null. For an update API, this may mean clearing the current value or setting the field to empty.
- **Property with a concrete value:** the client sent a new value to create or update.

Example with a profile update API:

| Sent JSON | Possible API-defined meaning |
|---|---|
| `phoneNumber` omitted | Keep the current phone number |
| `"phoneNumber": null` | Clear the stored phone number |
| `"phoneNumber": "0900000000"` | Change to the new number |

This is an API convention that must be designed and published. JSON and Jackson do not automatically assume that `null` always means clear or that a missing property always means keep unchanged.

## 2. JSON Distinguishes Presence from Value

A JSON object is a collection of name-value pairs. For a given property name, at least three states can occur:

1. The property is omitted.
2. The property is present with the value `null`.
3. The property is present with a non-`null` value.

Example:

```json
{}
```

```json
{"nickname": null}
```

```json
{"nickname": "An"}
```

JSON has no `undefined` keyword to represent an omitted property. In JavaScript, properties with `undefined` are typically omitted from the object when serialized with `JSON.stringify`; properties with `null` remain in the JSON. When reading requests on the server, only the last two JSON shapes exist on the wire: key absent and key present with null.

## 3. What Happens When Jackson Deserializes into Java?

Jackson maps JSON into fields, setters, constructors, or creator parameters. The outcome depends on the Java type, how the object is instantiated, and mapper configuration.

### Wrapper Fields and Missing Properties

For wrappers such as `Integer`, `Boolean`, or `String`, the initial value is typically `null` if there is no initializer. When a property is omitted, Jackson does not need to assign a value to that property; the field keeps the object's initial state. If the initial state is null, the post-binding result is also null.

```java
public class UserRequest {
    private String name;
    private Integer age;
    private Boolean active;

    // getters and setters
}
```

For the request `{}` in the example above, `age` and `active` are typically `null`. For the request `{"age":null}`, Jackson also sets `age` to `null` under its default wrapper behavior.

### Primitive Fields and Missing Properties

Java primitives cannot hold null:

| Primitive | Default field value if unassigned |
|---|---:|
| `boolean` | `false` |
| `byte`, `short`, `int` | `0` |
| `long` | `0L` |
| `float` | `0.0f` |
| `double` | `0.0d` |
| `char` | `\u0000` |

Example:

```java
public class SettingsRequest {
    private boolean enabled;
    private int retryCount;

    // getters and setters
}
```

If a request omits `enabled` and `retryCount`, the primitive fields retain their defaults `false` and `0`. The application cannot tell from these values whether the client explicitly sent `false`/`0` or omitted the properties.

When a JSON property is present with `null`, Jackson normally cannot assign null to a primitive. The exact outcome may be applying the default value, skipping, or throwing an error depending on Jackson's coercion and null-handling configuration. Do not rely on this default behavior to define business rules; use wrappers or explicit configuration if null must be detected.

## 4. Field Initializers, Constructors, and Records Change the Outcome

When a property is omitted, Jackson does not necessarily overwrite values already initialized in the object. Example:

```java
public class SearchRequest {
    private int page = 1;
    private int size = 20;
    private String sort = "createdAt,desc";

    // getters and setters
}
```

If Jackson instantiates the object with a no-arg constructor and only assigns properties present in the JSON, omitted properties can retain their initializers (`page = 1`, `size = 20`). If the request sends `{"page":null}`, the outcome depends on the target type and null-handling configuration; for primitives, Jackson may reject it or apply coercion settings.

With constructor/creator parameters, records, or immutable DTOs, missing properties may be handled differently from setter-based beans. Jackson must supply a value for every constructor parameter; defaults, `@JsonProperty(required = true)`, creator configuration, and the Jackson version can all affect the result.

Record example:

```java
public record CreateUserRequest(
        String name,
        Integer age
) {}
```

A record has no mutable fields for Jackson to skip calling a setter on. Jackson invokes the canonical constructor with the decoded values. If `age` is missing, the value passed in depends on how Jackson handles missing creator properties; if it must be required, declare that clearly via validation/metadata and test with your actual library version.

Do not infer required rules solely from whether a Java field is a primitive, wrapper, initialized, or inside a record. Verify the behavior of your DTO and test deserialization.

## 5. Comparison Table of JSON and Java States

The table below describes a simple mutable bean with a no-arg constructor, no initializers, and Jackson defaults for each type:

| Java Type | Property missing in JSON | Property is `null` in JSON | Property has value in JSON |
|---|---|---|---|
| `String` | `null` | `null` | Assigned string |
| `Integer` | `null` | `null` | Assigned integer |
| `Boolean` | `null` | `null` | Assigned boolean |
| `int` | `0` | Depends on config; may fail or use default | Assigned integer |
| `boolean` | `false` | Depends on config; may fail or use default | Assigned boolean |
| `List<String>` | `null` | `null` by default | Assigned list |
| `Map<String, Object>` | `null` | `null` by default | Assigned map |

This table is not a guarantee for every DTO. Initializers, constructors, creator properties, `@JsonSetter`, custom deserializers, and `ObjectMapper` settings can change the outcome.

Key takeaway: if missing and null collapse into the same Java value, the application has lost the information of whether the client sent the key. When business logic needs to distinguish them, preserve presence information or use a representation with explicit states.

## 6. `required` and `nullable` in OpenAPI

OpenAPI describes two independent questions:

- Is the property required to appear in the object?
- If present, is the property allowed to hold a null value?

### OpenAPI 3.0

In OpenAPI 3.0, the `required` list sits at the object level; `nullable: true` is used to allow null on a schema that declares a `type`.

```yaml
type: object
required:
  - name
properties:
  name:
    type: string
    nullable: false
  nickname:
    type: string
    nullable: true
  description:
    type: string
```

Interpretation:

- `name` must be present and cannot be null.
- `nickname` may be omitted; if present, it may be null.
- `description` may be omitted; the schema does not mark it as allowing null.

Therefore, `required: true` does not always mean non-null, and `nullable: true` does not mean the property is required to appear.

### OpenAPI 3.1

OpenAPI 3.1 uses the newer JSON Schema model. A schema allowing a string or null can use a union type:

```yaml
type: object
required:
  - name
properties:
  name:
    type: string
  nickname:
    type:
      - string
      - 'null'
```

Here, `nickname` can still be omitted because it is not in `required`; if present, its value can be a string or null. Do not mix OpenAPI 3.0-style `nullable: true` with 3.1 union-type syntax unless your tools and spec version support it accordingly.

## 7. Bean Validation Does Not Distinguish Missing from Null by Itself

Bean Validation checks object values after binding. For a wrapper property, if both missing JSON and null JSON result in the field becoming null, a constraint such as `@NotNull` sees the exact same state.

```java
public class CreateUserRequest {
    @NotNull
    private Integer age;

    // getters and setters
}
```

`@NotNull` requires the post-binding Java value to be non-null. It does not indicate whether null resulted from the client omitting the property or explicitly sending `"age": null`.

Common constraints also have specific scopes:

| Constraint | Check |
|---|---|
| `@NotNull` | Java value is not null |
| `@NotBlank` | String is not null, not empty, and contains a non-whitespace character |
| `@NotEmpty` | String/collection/map is not null and not empty |
| `@Positive` | Number is greater than 0; null is normally considered valid by this constraint |
| `@Size` | Size within specified bounds; null is normally considered valid |

If the requirement is “the key must be present in JSON,” `@NotNull` is sufficient only when both missing and null are rejected. If you need to distinguish “not sent” from “sent null to clear,” validation on the final field alone is insufficient; preserve presence information before converting into a plain DTO.

## 8. Controlling Nulls with Jackson `@JsonSetter`

Jackson provides the `@JsonSetter` annotation with a `nulls` attribute to specify how to handle a property when it appears with a null value. Common modes:

| Mode | Behavior on JSON null |
|---|---|
| `Nulls.SET` | Assigns null to the property normally |
| `Nulls.SKIP` | Skips the null value without invoking the setter/updating the property |
| `Nulls.FAIL` | Throws an error when null is encountered |
| `Nulls.AS_EMPTY` | Converts null to an empty value for the target type if supported |
| `Nulls.DEFAULT` | Uses Jackson's default/configured behavior |

Example skipping null:

```java
public class UpdateProfileRequest {
    private String displayName;

    @JsonSetter(nulls = Nulls.SKIP)
    private String phoneNumber;

    // getters and setters
}
```

With this configuration, when a request contains `"phoneNumber": null`, Jackson skips the assignment and keeps the field/object's current value. This can be useful for partial update APIs, but understand that null can no longer be used to clear a value.

Example rejecting null:

```java
public class CreateUserRequest {
    @JsonSetter(nulls = Nulls.FAIL)
    private String name;

    // getters and setters
}
```

When JSON contains `"name": null`, Jackson throws a binding error. A missing property remains a separate situation; if you need to require the key to be present, combine creator requirements, validation, or presence checks.

The meaning of `Nulls.AS_EMPTY` depends on the target type and serializer/deserializer. For example, on a collection, null can become an empty collection; on other types, the “empty value” may be a type-specific default. Verify the concrete behavior rather than assuming everything becomes an empty string.

## 9. Using Wrappers, Initializers, and Validation by Purpose

### Wrappers When Null Detection Is Needed

If you need to know whether a client omitted a value or provided a numeric value, use `Integer` instead of `int` to avoid losing information to the default `0`.

```java
public class UpdateSettingsRequest {
    private Boolean enabled;
    private Integer retryCount;

    // getters and setters
}
```

However, wrappers only represent null; they do not inherently distinguish a missing key from a key with null. On beans without initializers, both typically become null.

### Initializers for Default Values

```java
public class SearchRequest {
    private Integer page = 0;
    private Integer size = 20;

    // getters and setters
}
```

When a property is omitted and Jackson constructs a standard bean, the initializer can be preserved. If the client sends null, behavior may differ. If the API wants to apply a default when missing while rejecting explicit null, configure null handling or validation accordingly.

### Validation for Post-Binding Values

```java
public class CreateOrderRequest {
    @NotNull
    @Positive
    private Integer quantity;

    // getters and setters
}
```

`@NotNull` ensures `quantity` is non-null after binding; `@Positive` ensures it is positive. If both omitted and null yield null, both cases are rejected by `@NotNull`. This is usually appropriate for creation requests.

## 10. PATCH and the Need for Three-State Representation

PATCH APIs often need to distinguish three states:

1. Property omitted: keep the current value.
2. Property sent with null: clear or set the value to null.
3. Property sent with a value: update to the new value.

A typical Java DTO with nullable wrappers usually cannot preserve the difference between cases 1 and 2 after deserialization. Example:

```java
public class UpdateUserRequest {
    private String displayName;
    private String phoneNumber;

    // getters and setters
}
```

After binding, `phoneNumber == null` could mean either the client omitted the key or sent the key with null. If the service layer must distinguish them, choose one of these approaches:

- Use JSON Merge Patch (`application/merge-patch+json`) and implement its semantics consistently; in JSON Merge Patch, null typically indicates removing the member.
- Accept the request as a `JsonNode` or `ObjectNode`, checking `has("phoneNumber")` and `isNull()` before mapping to the domain model.
- Use a wrapper like `JsonNullable<T>` (e.g., from OpenAPITools) to represent undefined, present-null, and present-value states if supported by your project's ecosystem.
- Write a custom deserializer or dedicated patch field type to retain presence.

Example checking with `JsonNode`:

```java
@PatchMapping("/{id}")
UserResponse update(
        @PathVariable UUID id,
        @RequestBody JsonNode body) {

    if (!body.has("phoneNumber")) {
        // Do not update the phone number.
    } else if (body.get("phoneNumber").isNull()) {
        // Clear the phone number.
    } else {
        String phone = body.get("phoneNumber").asText();
        // Update the phone number.
    }

    return userService.updateFromPatch(id, body);
}
```

This snippet illustrates checking presence; in a real application, validate node types, handle malformed values, and guard against unexpected nulls. If using JSON Merge Patch, publish the proper media type and semantics in OpenAPI.

## 11. Describing `required` and Nullability with `springdoc-openapi`

Springdoc generates schemas from DTOs, Jackson metadata, and Bean Validation. Common annotations include:

- `@NotNull`, `@NotBlank`, `@NotEmpty` to express non-null/non-empty constraints.
- `@Schema(nullable = true)` in compatible annotation/OpenAPI versions to document nullability in OpenAPI 3.0.
- `@Schema(requiredMode = Schema.RequiredMode.REQUIRED)` or `NOT_REQUIRED` to adjust property presence requirements when needed.
- `@JsonSetter(nulls = ...)` to control Jackson runtime behavior; this is not a substitute for `required` in OpenAPI.

Example:

```java
public class ProfileRequest {

    @Schema(
        description = "Display name, required and non-null",
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    @NotBlank
    private String displayName;

    @Schema(
        description = "Nickname; may be null",
        nullable = true,
        requiredMode = Schema.RequiredMode.NOT_REQUIRED
    )
    private String nickname;

    // getters and setters
}
```

This is a metadata example; the actual schema still depends on OpenAPI, springdoc, and Swagger Annotations versions as well as Bean Validation integration. For OpenAPI 3.1, verify how your library version represents null under JSON Schema 3.1 instead of assuming `nullable: true` always outputs the exact syntax you expect.

### `@JsonProperty(required = true)` Is Not a General Solution for Every Bean

Jackson provides a `required` attribute on `@JsonProperty`, but its enforcement of required properties primarily applies to creator properties in supported scenarios. Placing it on fields/setters of a mutable bean is not a reliable replacement for Bean Validation or presence checks in all situations.

To document the OpenAPI contract, use appropriate schema metadata. To validate requests at runtime, use validation, creator configuration, `@JsonSetter`, or explicit presence checks as appropriate.

## 12. Example Comparing Three States During an Update

Suppose the current profile has `nickname = "An"`. The API wants to keep it when omitted, clear it when null, and change it when a string is sent.

| Request body | State after binding with a plain wrapper DTO | Desired PATCH meaning |
|---|---|---|
| `{}` | `nickname == null` | Keep `"An"` |
| `{"nickname": null}` | `nickname == null` | Clear, set to null |
| `{"nickname": "Binh"}` | `nickname == "Binh"` | Change to `"Binh"` |

The first two rows yield the exact same Java value when using a plain wrapper bean. Hence the service cannot decide accurately if it only checks `request.getNickname() == null`.

Using `JsonNode`, you can determine the state:

```java
if (!body.has("nickname")) {
    // Keep unchanged
} else if (body.get("nickname").isNull()) {
    // Clear the value
} else {
    // Update with the submitted value
}
```

For PUT APIs that replace the entire resource, the rules usually differ from PATCH: all required fields of the new representation must be submitted; omitted fields may be treated as missing data or assigned contract defaults. Document the semantics of each method clearly rather than sharing one DTO with undefined rules.

## 13. Checking Consistency Across Jackson, Validation, and OpenAPI

When designing a property, inspect all four layers separately:

| Layer | Question to Answer |
|---|---|
| JSON contract | Must the key be present? Is null allowed? |
| Jackson | When the key is missing or null, what value does the field/constructor receive? Does it fail or skip? |
| Bean Validation | What state does the constraint check post-binding? Does it distinguish presence? |
| OpenAPI | Do `required`, nullable/union type, default, and examples accurately describe the rule? |

Verification workflow:

1. Write sample JSON payloads: missing key, null key, valid value, and wrong type.
2. Deserialize with the exact `ObjectMapper` used by Spring Boot.
3. Record the post-binding Java values, including field initializers and constructor defaults.
4. Run Bean Validation and confirm which constraints fail.
5. Check the endpoint's actual status code and error response.
6. Open `/v3/api-docs` or `/v3/api-docs.yaml` and inspect `required`, `nullable`, or union types.
7. Test Swagger UI or client generators if used, ensuring tools interpret the contract accurately.

Write integration tests covering missing/null/value states whenever an endpoint attaches distinct semantics to them, especially for PATCH and fields with default values.

## 14. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Cannot distinguish missing from null | Both collapse to null in a wrapper field | Preserve presence using `JsonNode`, `JsonNullable`, or a custom deserializer |
| Missing value becomes `0` or `false` | Using a Java primitive | Use a wrapper if null or unset state must be detected |
| Sending null still leaves old value intact | Using `@JsonSetter(nulls = SKIP)` or custom handling | Define semantics and choose `SET`, `SKIP`, or `FAIL` accordingly |
| Sending null causes a deserialization error | Primitive type or `Nulls.FAIL`/coercion config | Use a wrapper or document the null-rejection rule clearly |
| `@NotNull` fails to tell missing key from null key | Validation only inspects post-binding value | Check presence prior to binding or use a presence-aware type |
| OpenAPI marks required yet client can still send null | Required only checks presence while schema stays nullable or runtime skips check | Align nullability and validation accordingly |
| OpenAPI does not mark nullable even though Java uses wrapper | Wrappers alone do not define the full nullable contract | Add `@Schema` and verify against your OpenAPI version |
| Default values are not applied | Constructor/initializer and creator binding behave differently than expected | Test with missing-key JSON against actual Jackson configuration |
| PATCH accidentally clears data | DTO fails to preserve missing vs. null distinction | Use a patch representation with explicit presence |

## 15. Design Principles

- Treat missing, null, and present-with-value as three separate contract states whenever business logic needs to distinguish them.
- Use primitives when a default value is valid and you do not need to know whether the client sent the field.
- Use wrappers when null must be represented, remembering that plain wrappers do not preserve presence.
- Use `@NotNull` to validate post-binding values; do not treat it as a JSON key presence check.
- Use `@JsonSetter(nulls = ...)` to specify explicit null handling, without confusing it with missing-property behavior.
- Use `required` to document presence and nullable/union types to document null allowance in OpenAPI.
- Verify how Jackson handles beans, creators, records, initializers, and primitives with your actual runtime configuration.
- For PATCH, use a representation capable of distinguishing missing, null, and value if semantics require three states.
- Separate request/response DTOs or create/update DTOs when field requirements and validation differ.
- Verify the schema generated by springdoc alongside real requests and validation results.

## Conclusion

JSON distinguishes an omitted property from a property present with `null`, but Jackson deserialization into a Java field can erase that distinction. Primitives also carry defaults like `0` or `false`; wrappers typically receive null for both omitted and explicit null unless initializers or other settings apply. Bean Validation checks values after binding, whereas OpenAPI uses `required` and nullability to describe two independent dimensions. For partial update APIs, preserve presence information when you need to distinguish keeping, clearing, and updating; and verify springdoc metadata, Jackson behavior, and validation together so the contract matches runtime.
