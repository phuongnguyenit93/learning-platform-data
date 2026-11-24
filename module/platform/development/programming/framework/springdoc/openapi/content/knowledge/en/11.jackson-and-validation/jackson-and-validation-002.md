# `@JsonProperty`, `@JsonIgnore`, and Reconciling with `@Schema`

In a Spring Boot API, Java property names do not necessarily match the JSON property names seen by clients. Jackson decides how objects are serialized into JSON responses and how JSON requests are deserialized into Java objects. Springdoc-openapi reads model metadata, including many Jackson annotations, to generate the OpenAPI schema. The `@Schema` annotation supplements documentation details such as descriptions, examples, and read-only or write-only status.

These three annotations are often used together, yet each plays a distinct role:

- `@JsonProperty` controls a property's name and read/write access when Jackson processes JSON.
- `@JsonIgnore` excludes a property from serialization and/or deserialization according to the annotation configuration.
- `@Schema` describes how the property appears in the OpenAPI contract; it does not alter Jackson's runtime JSON by itself.

When building API documentation, you must verify both actual JSON and `/v3/api-docs`. Looking only at Java DTOs or Swagger UI can miss cases where a JSON name changed, a property was ignored, or a field appears only in requests or responses.

## 1. Flow from Java DTO to JSON and OpenAPI

A request/response passes through these main steps:

1. The controller receives or returns a Java type.
2. For a request body, Jackson uses `ObjectMapper` and its configurations/annotations to convert JSON into a Java object.
3. For a response body, Jackson uses `ObjectMapper` to convert the Java object into JSON.
4. Springdoc inspects mappings, Java types, Jackson metadata, and Swagger annotations to build OpenAPI schemas.
5. Swagger UI and client generators use those schemas to render or generate requests/responses.

You can visualize the relationship as follows:

```mermaid
flowchart TD
    A[Java DTO and Jackson annotations] --> B[Jackson ObjectMapper]
    B --> C[Actual JSON request/response]
    A --> D[springdoc-openapi]
    D --> E[OpenAPI Schema]
    F[@Schema metadata] --> D
    E --> G[Swagger UI and client generators]
    C --> H[Contract reconciliation]
    G --> H
```

Jackson determines what data is read/written at runtime. Springdoc documents the contract based on the information it detects. `@Schema` fills in missing semantics or adjusts documentation metadata. All three parts must remain consistent.

## 2. Renaming JSON Properties with `@JsonProperty`

### 2.1. Java Name and JSON Name

Suppose a DTO has a Java property `displayName`, but the API wants to use the key `display_name`:

```java
import com.fasterxml.jackson.annotation.JsonProperty;

public class UserResponse {

    @JsonProperty("display_name")
    private String displayName;

    public String getDisplayName() {
        return displayName;
    }

    public void setDisplayName(String displayName) {
        this.displayName = displayName;
    }
}
```

Jackson uses the name `display_name` when writing JSON and accepts that key when reading JSON, subject to the property's default access mode. The response looks like:

```json
{
  "display_name": "Nguyen An"
}
```

The corresponding request body also sends the key `display_name`:

```json
{
  "display_name": "Nguyen An"
}
```

In OpenAPI, the property name should also be `display_name`. Springdoc can read `@JsonProperty` to document the exact JSON name used by Jackson.

### 2.2. Using with Java Records

For records, you can place the annotation on the record component:

```java
public record CreateUserRequest(
        @JsonProperty("display_name") String displayName,
        @JsonProperty("email_address") String emailAddress
) {}
```

Expected JSON:

```json
{
  "display_name": "Nguyen An",
  "email_address": "an@example.com"
}
```

Record components are supported in compatible Jackson versions. In projects using an older Jackson version or custom visibility settings, test actual serialization/deserialization instead of relying solely on examples.

### 2.3. `@JsonProperty` and Naming Strategies

Jackson can apply a naming strategy at the `ObjectMapper` level, such as converting `displayName` to `display_name` across all DTOs. `@JsonProperty("display_name")` declares an explicit name for a specific property and makes the contract easy to spot.

If the project already configures `PropertyNamingStrategies.SNAKE_CASE`, there is no need to add `@JsonProperty` to every field. Use the annotation when a JSON name differs from the general rule, must remain fixed, or expresses a special wire-format name explicitly.

Naming strategy example:

```java
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;

@Bean
Jackson2ObjectMapperBuilderCustomizer jsonCustomizer() {
    return builder -> builder.propertyNamingStrategy(
            PropertyNamingStrategies.SNAKE_CASE
    );
}
```

When a naming strategy and `@JsonProperty` interact, verify the JSON output from the exact `ObjectMapper` used by Spring. Also inspect the schema generated by springdoc to ensure property names do not diverge.

### 2.4. `@Schema(name = ...)` Does Not Replace `@JsonProperty`

Do not use `@Schema(name = "display_name")` expecting Jackson to rename the JSON key. `@Schema` is OpenAPI metadata; it does not configure serialization. To rename a JSON property, use `@JsonProperty` or a Jackson naming strategy.

You can combine both annotations:

```java
public record UserResponse(
        @JsonProperty("display_name")
        @Schema(description = "User display name", example = "Nguyen An")
        String displayName
) {}
```

Here `@JsonProperty` defines the JSON key; `@Schema` adds a description and example for that key in OpenAPI.

## 3. Hiding Properties from JSON with `@JsonIgnore`

`@JsonIgnore` marks a property that Jackson should not treat as a normal JSON property. A common use case is excluding internal fields or sensitive data from both writing and reading JSON:

```java
import com.fasterxml.jackson.annotation.JsonIgnore;

public class UserAccount {

    private String username;

    @JsonIgnore
    private String passwordHash;

    // getters and setters
}
```

When serializing, `passwordHash` does not appear in the JSON response. When deserializing, sending that key in JSON also will not bind to the ignored property under the annotation's default configuration.

Response:

```json
{
  "username": "an.nguyen"
}
```

Springdoc normally omits properties ignored by Jackson from the schema. This ensures documentation reflects the JSON structure actually exposed by Jackson.

### 3.1. `@JsonIgnore` Is Not an Access Control Mechanism

Hiding a field from JSON does not replace data access control in the service or security layer. If sensitive data must not appear in a response, design a response DTO containing only fields allowed to be exposed. Do not rely on a property being invisible in Swagger UI to protect data.

Similarly, if `passwordHash` is ignored in a request DTO, clients cannot set it via standard JSON. However, an input password is usually write-only data and needs its own field that is validated and hashed on the server; never reuse an internal hash field to accept raw passwords.

### 3.2. When Read-Only or Write-Only Is Needed, Avoid Full Ignore

If a property must be sent in requests but not returned in responses, or vice versa, `@JsonIgnore` may be too broad because it typically excludes the property in both directions. Consider `@JsonProperty(access = ...)` in the next section.

## 4. Controlling Data Direction with `@JsonProperty(access = ...)`

`@JsonProperty` has an `access` attribute to specify which direction a property is read into Java or written to JSON:

| Access mode | Jackson during response serialization | Jackson during request deserialization |
|---|---|---|
| `AUTO` | Follows standard rules | Follows standard rules |
| `READ_ONLY` | Can write property to JSON | Does not accept value from JSON to set the property |
| `WRITE_ONLY` | Does not write property to JSON | Accepts value from JSON |
| `READ_WRITE` | Writes property to JSON | Accepts value from JSON |

The names `READ_ONLY` and `WRITE_ONLY` are named from Jackson's perspective: reading from the Java object to write JSON, or writing into the Java object when reading JSON. For an API, that corresponds to response-only and request-only.

### 4.1. Response-Only Fields

For example, a server-generated `id` that clients must not set on creation:

```java
public record UserDto(
        @JsonProperty(access = JsonProperty.Access.READ_ONLY)
        UUID id,
        String displayName
) {}
```

Jackson can serialize `id` in responses while ignoring any `id` value sent in requests. In OpenAPI, this property corresponds to `readOnly: true`.

### 4.2. Request-Only Fields

For example, a password when creating an account:

```java
public record CreateAccountRequest(
        String username,
        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        String password
) {}
```

Jackson reads `password` from the request body for processing, but omits it from JSON when the object is serialized. In OpenAPI, this property corresponds to `writeOnly: true`.

Never return raw passwords in responses, even when a request succeeds. Use a dedicated response DTO to expose only the required fields.

## 5. Reconciling Access Modes with `@Schema`

The OpenAPI Schema Object has two important metadata flags:

- `readOnly: true`: the property is read-only, typically sent from server to client.
- `writeOnly: true`: the property is write-only, typically sent from client to server.

Swagger Annotations express them with `@Schema(accessMode = ...)`:

```java
public record CreateAccountRequest(
        String username,

        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        @Schema(
                accessMode = Schema.AccessMode.WRITE_ONLY,
                description = "New password; sent in request only"
        )
        String password
) {}
```

`@JsonProperty(access = WRITE_ONLY)` shapes Jackson's behavior. `@Schema(accessMode = WRITE_ONLY)` tells OpenAPI consumers that the property is write-only. Use both when you want both contract layers explicit and consistent.

Similarly for a read-only field:

```java
public record UserResponse(
        @JsonProperty(access = JsonProperty.Access.READ_ONLY)
        @Schema(
                accessMode = Schema.AccessMode.READ_ONLY,
                description = "System-assigned user ID"
        )
        UUID id,
        String displayName
) {}
```

Springdoc can infer some metadata from Jackson access modes, though exact behavior depends on the springdoc version, Swagger Core, and how the model is analyzed. When the schema is a critical part of the contract, verify `readOnly`/`writeOnly` in `/v3/api-docs`.

### 5.1. `@Schema(hidden = true)` Differs from `@JsonIgnore`

`@Schema(hidden = true)` hides a property from OpenAPI documentation. It does not instruct Jackson to exclude the property from runtime JSON.

```java
public class InternalUserView {

    private String username;

    @Schema(hidden = true)
    private String internalNote;

    // getters and setters
}
```

In this case, Jackson can still serialize `internalNote` unless configured otherwise. Swagger UI may omit that property, yet the JSON response can still include it. If a property must never leave the server, use an appropriate response DTO or configure Jackson for runtime exclusion; do not merely hide the schema.

Conversely, `@JsonIgnore` affects runtime JSON and springdoc usually reflects that exclusion. There is no need to add `@Schema(hidden = true)` just to repeat the same intent unless there is a separate documentation reason.

## 6. Choosing Annotations Based on API Requirements

| Requirement | Suitable Annotation | Primary Effect |
|---|---|---|
| Rename `displayName` to key `display_name` in JSON | `@JsonProperty("display_name")` | Jackson renames the JSON property; springdoc can reflect that name. |
| Completely exclude a property from JSON | `@JsonIgnore` | Jackson ignores the property; springdoc usually omits it from the schema. |
| Return `id` only in responses | `@JsonProperty(access = READ_ONLY)` | Jackson serializes it but ignores values from JSON requests. |
| Accept `password` only in requests | `@JsonProperty(access = WRITE_ONLY)` | Jackson reads it from requests but does not serialize the property. |
| Mark property read-only/write-only in contract | `@Schema(accessMode = READ_ONLY/WRITE_ONLY)` | Adds `readOnly`/`writeOnly` for OpenAPI. |
| Hide property from docs while keeping runtime JSON | `@Schema(hidden = true)` | Affects OpenAPI documentation only. |
| Add description, example, format, or limits | `@Schema(...)` | Supplements schema metadata; does not change runtime JSON. |

Practical guidelines:

- Use Jackson annotations to define the actual JSON.
- Use `@Schema` to describe the semantics and constraints of the contract.
- Use separate request and response DTOs when the two data directions differ significantly.
- Avoid using a documentation annotation to try to alter runtime behavior, or using Jackson annotations in place of business descriptions.

## 7. Complete Example with Separate Request DTO and Response DTO

A clean design separates the request DTO from the response DTO:

```java
public record CreateUserRequest(
        @JsonProperty("display_name")
        @NotBlank
        @Schema(description = "Display name", example = "Nguyen An")
        String displayName,

        @JsonProperty("email_address")
        @Email
        @Schema(description = "Email address", example = "an@example.com")
        String emailAddress,

        @JsonProperty(access = JsonProperty.Access.WRITE_ONLY)
        @Schema(
                accessMode = Schema.AccessMode.WRITE_ONLY,
                description = "Input password"
        )
        @NotBlank
        String password
) {}
```

```java
public record UserResponse(
        @JsonProperty(value = "user_id", access = JsonProperty.Access.READ_ONLY)
        @Schema(description = "System-assigned user ID", accessMode = Schema.AccessMode.READ_ONLY)
        UUID id,

        @JsonProperty("display_name")
        @Schema(description = "Display name", example = "Nguyen An")
        String displayName,

        @JsonProperty("email_address")
        String emailAddress
) {}
```

Controller:

```java
@RestController
@RequestMapping("/api/users")
class UserController {

    @PostMapping
    ResponseEntity<UserResponse> create(
            @Valid @RequestBody CreateUserRequest request) {
        UserResponse response = userService.create(request);
        return ResponseEntity.status(HttpStatus.CREATED).body(response);
    }
}
```

Request JSON:

```json
{
  "display_name": "Nguyen An",
  "email_address": "an@example.com",
  "password": "secret-value"
}
```

Response JSON:

```json
{
  "user_id": "c0a8012e-7f4b-4e7a-9b8d-6e1d5a6a1234",
  "display_name": "Nguyen An",
  "email_address": "an@example.com"
}
```

In this example, `password` belongs solely to the request DTO; the response DTO has no such field. This keeps the data shape clear in both directions, easy to test, and less dependent on how tooling represents read/write schemas for a shared model.

## 8. How Springdoc Reflects Jackson Annotations

Springdoc uses model converters along with Jackson/Swagger metadata to construct schemas. Common cases are typically reflected as follows:

| Jackson metadata | Runtime JSON | Typically expected OpenAPI |
|---|---|---|
| `@JsonProperty("display_name")` | Key is `display_name` | Property named `display_name`. |
| `@JsonIgnore` | Property ignored per direction rules | Property omitted from schema. |
| `@JsonProperty(access = READ_ONLY)` | Written to JSON, not read from JSON | `readOnly: true` when recognized. |
| `@JsonProperty(access = WRITE_ONLY)` | Read from JSON, not written to JSON | `writeOnly: true` when recognized. |
| `@Schema(description = ...)` | Does not change JSON | Includes `description` in schema. |
| `@Schema(example = ...)` | Does not change JSON | Includes example in schema. |
| `@Schema(hidden = true)` | Does not change JSON | Property hidden from documentation. |

These are expected outcomes based on the annotations' intent, not a guarantee that every combination of annotations or library version yields identical output. Jackson mix-ins, custom serializers/deserializers, property naming strategies, visibility configurations, and custom model converters can alter the result.

### 8.1. Inspecting Request and Response Schemas Separately

For an operation with a request body and a response, open `/v3/api-docs` and check:

- The schema referenced in `requestBody.content.application/json.schema`.
- The corresponding response schema in `responses.<status>.content.application/json.schema`.
- Property names match the actual JSON keys.
- Ignored fields do not appear unexpectedly.
- `readOnly` and `writeOnly` are set for the proper direction if sharing a schema.
- Descriptions, examples, formats, and validation constraints are intact.

OpenAPI may reuse a schema via `$ref`. When a DTO is shared across multiple operations, check whether springdoc generates a single shared schema or separate schemas per request/response context, depending on configuration and version. If a field has markedly different rules by direction, separate DTOs are usually easier to follow.

## 9. Verifying Runtime JSON with `ObjectMapper`

Do not check annotations in source code alone. Verify the actual JSON using an `ObjectMapper` configured like the application:

```java
@SpringBootTest
class UserJsonMappingTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesJsonPropertyName() throws Exception {
        UserResponse response = new UserResponse(
                UUID.fromString("c0a8012e-7f4b-4e7a-9b8d-6e1d5a6a1234"),
                "Nguyen An",
                "an@example.com"
        );

        String json = objectMapper.writeValueAsString(response);

        assertThat(json).contains("\"user_id\"");
        assertThat(json).contains("\"display_name\"");
        assertThat(json).doesNotContain("\"displayName\"");
    }
}
```

For `WRITE_ONLY`, test both directions: request JSON can populate the property, while JSON serialized from the object omits it. For `READ_ONLY`, check that the property appears in the JSON response while values sent in a request do not overwrite the property per the access mode.

If the application has multiple `ObjectMapper` instances, custom modules, or media-type-specific configurations, inject the exact mapper used by the HTTP message converter. A manually constructed mapper in a test may not reflect real runtime configuration.

## 10. OpenAPI Contract Testing

You can use MockMvc to fetch the OpenAPI JSON and verify property names. Illustrative example:

```java
@SpringBootTest
@AutoConfigureMockMvc
class UserOpenApiSchemaTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void documentsJsonPropertyNames() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.components.schemas.UserResponse.properties.display_name"
                ).exists())
                .andExpect(jsonPath(
                        "$.components.schemas.UserResponse.properties.displayName"
                ).doesNotExist());
    }
}
```

Actual schema names can vary based on how springdoc names models or `@Schema(name = ...)` settings. In project tests, check the schema path matching the generated document or resolve the schema through the operation's `$ref` rather than assuming every model always uses the same component name.

Include dedicated tests for these scenarios:

1. `@JsonProperty` renames properties properly in both JSON requests and responses.
2. `@JsonIgnore` removes the property from runtime JSON and the schema.
3. `READ_ONLY`/`WRITE_ONLY` behaves properly in the corresponding Jackson direction.
4. `@Schema(hidden = true)` hides the property from OpenAPI without mistakenly implying it is excluded from runtime JSON.
5. OpenAPI docs accurately reflect request/response DTOs after naming strategy or `ObjectMapper` configuration changes.

## 11. Edge Cases to Watch Out For

### 11.1. Annotations Placed on Fields, Getters, or Setters

Jackson can merge metadata from fields, getters, setters, and constructor parameters into a single logical property. When the same property has annotations in multiple places, the result depends on introspection rules and visibility settings. If a JSON name or access mode is unexpected, check all related accessors rather than looking only at the field.

Prefer placing annotations consistently in one clear location matching your DTO style. For records, annotate the record component; for JavaBeans, pick either fields or getters/setters per project convention.

### 11.2. `@JsonIgnore` and Bidirectional Configuration

`@JsonIgnore` normally excludes a property from both serialization and deserialization. Jackson provides directional controls such as `@JsonProperty(access = ...)` or related `@JsonIgnoreProperties` options (`allowGetters`, `allowSetters`). These mechanisms have different semantics and should be tested against the actual mapper.

If the goal is a request-only or response-only property, `@JsonProperty(access = WRITE_ONLY/READ_ONLY)` usually expresses intent more clearly than combining `@JsonIgnore` with annotations on another accessor.

### 11.3. Custom Serializers/Deserializers

Custom `@JsonSerialize`, `@JsonDeserialize`, `JsonSerializer`, or `JsonDeserializer` implementations can make runtime JSON differ from the schema inferred from the Java type. For instance, a Java object might serialize into a string or custom format. In that case, add `@Schema(type = ..., format = ...)` or an appropriate customizer so OpenAPI describes the actual representation.

Do not assume springdoc can infer every JSON structure produced by custom serializers. Verify the JSON output and the schema side by side.

### 11.4. `@JsonInclude` Is Not `@JsonIgnore`

`@JsonInclude(Include.NON_NULL)` can cause Jackson to omit a property when its value is null during serialization. It does not mean the property is removed from the model or never appears. The schema may still describe that property, with optionality/nullability depending on configuration.

If an API can omit a property when null, distinguish among:

- Property absent from JSON due to null value and inclusion policy.
- Property unsupported by the contract.
- Property supported but optional in requests.

These three cases have different meanings to clients.

## 12. Workflow for Reconciling Jackson and OpenAPI

When adding or modifying annotations on a DTO, follow this workflow:

1. **Define the JSON contract**: specify which keys are accepted in requests and which keys are returned in responses.
2. **Choose the right DTOs**: split request and response DTOs if their fields differ.
3. **Configure Jackson**: use `@JsonProperty`, `@JsonIgnore`, access modes, or naming strategies to produce the desired runtime JSON.
4. **Add OpenAPI metadata**: use `@Schema` for descriptions, examples, readOnly/writeOnly, or hidden when needed.
5. **Test serialization/deserialization**: use the application's mapper to verify actual JSON.
6. **Inspect `/v3/api-docs`**: check property names, schemas, `$ref` targets, access modes, and constraints.
7. **Run HTTP integration tests**: send real requests and inspect responses through controllers to confirm message converters use the same configuration.
8. **Update contract tests**: protect the JSON names and fields that clients depend on.

## 13. Review Checklist

- [ ] JSON names are defined using `@JsonProperty` or an appropriate naming strategy.
- [ ] Property names in OpenAPI match runtime JSON.
- [ ] `@JsonIgnore` is used only when Jackson should genuinely ignore the property.
- [ ] Request-only/response-only fields use an appropriate access mode or separate DTOs.
- [ ] `@Schema(accessMode = ...)` is consistent with the Jackson access mode.
- [ ] `@Schema(hidden = true)` is not mistaken for hiding data at runtime.
- [ ] `@Schema(name = ...)` is not used as a substitute for renaming JSON properties.
- [ ] Custom serializers/deserializers and naming strategies have been verified.
- [ ] `/v3/api-docs` accurately reflects names, read/write direction, and excluded properties.
- [ ] Integration tests cover both runtime JSON and the OpenAPI schema.

## 14. References

- [Jackson `@JsonProperty` Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonProperty.html)
- [Jackson `@JsonIgnore` Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnore.html)
- [Jackson `@JsonIgnoreProperties` Javadoc](https://javadoc.io/doc/com.fasterxml.jackson.core/jackson-annotations/latest/com/fasterxml/jackson/annotation/JsonIgnoreProperties.html)
- [OpenAPI Specification 3.1.2 – Schema Object](https://spec.openapis.org/oas/v3.1.2.html#schema-object)
- [Swagger Annotations – `@Schema`](https://javadoc.io/doc/io.swagger.core.v3/swagger-annotations/latest/io/swagger/v3/oas/annotations/media/Schema.html)
- [springdoc-openapi FAQ](https://springdoc.org/faq.html)

`@JsonProperty` and `@JsonIgnore` shape the JSON that Jackson actually reads and writes. `@Schema` helps describe the contract that clients see. When each is used for its intended role and both runtime JSON and `/v3/api-docs` are verified, the OpenAPI documentation will much more accurately reflect property names, excluded fields, and write-only or read-only properties.
