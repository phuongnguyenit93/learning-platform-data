# Free-Form Data Types and Undeclared Property Policies

Not every JSON object has a fixed list of properties. An API may accept metadata sent by integrating systems, event-specific extension fields, or configurations whose key names are chosen by users. In such cases, the schema must describe an object with dynamic properties without declaring every key name ahead of time.

OpenAPI uses `additionalProperties` inside a Schema Object to define the policy for properties not listed in `properties`. It can allow any value, constrain values to a schema, or forbid undeclared properties. In Spring Boot applications, types such as `Map<String, T>`, `Map<String, Object>`, and `JsonNode`, alongside Jackson annotations and `@Schema`, help implement and document dynamic data.

## 1. Fixed-Structure Objects vs. Free-Form Data Objects

A fixed-structure object normally declares the name and type of each property in advance:

```yaml
type: object
required:
  - id
  - name
properties:
  id:
    type: string
    format: uuid
  name:
    type: string
  active:
    type: boolean
```

The object above has three known properties. Clients and servers rely on the schema to understand `id`, `name`, and `active`.

In some APIs, an object also needs to accept previously unknown keys. For instance, webhooks may carry varying metadata depending on the provider; events may carry extension properties per event type; configurations may allow administrators to choose key names.

```json
{
  "eventId": "evt-1001",
  "eventType": "order.updated",
  "metadata": {
    "source": "partner-a",
    "region": "ap-southeast-1",
    "retryCount": 2,
    "verified": true
  }
}
```

The properties inside `metadata` have varying names and can hold multiple JSON types. Merely declaring `source`, `region`, `retryCount`, and `verified` under `properties` would fail to express the extensible intent of the field. `additionalProperties` lets you describe the dynamic data section.

## 2. How Does `additionalProperties` Work?

Within an object Schema Object, `properties` describes known keys; `additionalProperties` governs how remaining keys are handled. Its value can be a Boolean or a Schema Object.

| Declaration | Meaning |
|---|---|
| `additionalProperties` omitted | By default, unlisted properties are still permitted |
| `additionalProperties: true` | Permits undeclared properties without placing specific schema constraints on their values |
| `additionalProperties: false` | Forbids undeclared properties |
| `additionalProperties: { ...schema... }` | Permits undeclared properties, provided each property's value conforms to the specified schema |

Example allowing dynamic keys with string values:

```yaml
type: object
properties:
  name:
    type: string
additionalProperties:
  type: string
```

The object can have `name` and any additional properties, yet the value of every additional property must be a string.

Example forbidding keys outside the list:

```yaml
type: object
properties:
  name:
    type: string
  age:
    type: integer
additionalProperties: false
```

Under this schema, `name` and `age` are permitted; keys such as `role` or `internalFlag` are outside the contract.

`additionalProperties` applies only to properties at the same object level. It does not automatically set the policy for nested objects. If `metadata` is a nested object inside `Event`, the dynamic-property policy of `metadata` must be declared inside `metadata`'s schema.

## 3. Allowing Any Value vs. Restricting Value Types

A free-form object may need to accept any JSON value or allow only a specific value type. The two cases require different schemas.

### Any Value

```yaml
type: object
additionalProperties: true
```

Or an empty schema can be used for additional values:

```yaml
type: object
additionalProperties: {}
```

Both forms indicate that dynamic keys are not constrained by a specific value schema. Values can be strings, numbers, booleans, objects, arrays, or null depending on the OpenAPI/JSON Schema version and other applied constraints.

### String Values Only

```yaml
type: object
additionalProperties:
  type: string
```

Valid JSON example:

```json
{
  "labels": {
    "source": "partner-a",
    "region": "ap-southeast-1"
  }
}
```

Numeric or boolean values will not conform to this schema.

### Numeric Values

```yaml
type: object
additionalProperties:
  type: number
```

Suitable for measurement maps or price tables with dynamic keys:

```json
{
  "prices": {
    "standard": 120000,
    "express": 250000
  }
}
```

### Fixed-Structure Object Values

If every dynamic key maps to an object of the same shape, you can specify a schema for the value:

```yaml
type: object
additionalProperties:
  type: object
  required:
    - enabled
  properties:
    enabled:
      type: boolean
    description:
      type: string
```

Each dynamic key is allowed to hold an object with `enabled` and `description` matching this schema. This works well for per-module configuration maps where every entry shares the same structure.

## 4. Mapping Java `Map` to `additionalProperties`

`Map` is the natural Java type for objects with dynamic key names. Keys are represented as JSON property names; the value's generic type supplies information for springdoc to describe `additionalProperties`.

| Java type | Typical OpenAPI schema |
|---|---|
| `Map<String, String>` | Object with `additionalProperties` having `type: string` |
| `Map<String, Integer>` | Object with `additionalProperties` having `type: integer` |
| `Map<String, BigDecimal>` | Object with `additionalProperties` having `type: number` |
| `Map<String, UserMetadata>` | Object with `additionalProperties` referencing schema `UserMetadata` |
| `Map<String, Object>` | Object with free-form values, usually without specific schema constraints |
| `Map<String, JsonNode>` | Object with dynamic JSON values; inspect generated schema and serialization |

DTO example:

```java
public class EventRequest {
    private String eventType;
    private Map<String, String> labels;
    private Map<String, Object> metadata;

    // getters and setters
}
```

Here, `labels` maps to string `additionalProperties`; `metadata` allows more flexible values. Illustrative schema:

```yaml
EventRequest:
  type: object
  properties:
    eventType:
      type: string
    labels:
      type: object
      additionalProperties:
        type: string
    metadata:
      type: object
      additionalProperties: true
```

Declare concrete generic types whenever the value type is known in advance. `Map<String, Object>` is flexible, yet reduces compile-time type checking and makes it hard for clients to know what data each key can contain. Use `Map<String, String>` or `Map<String, MetadataValue>` when the domain can define a clear structure.

## 5. Using `@Schema` to Describe Additional Properties

Springdoc usually infers schemas from Java types and generics. `@Schema` can add descriptions or specify dynamic property policies when default inference does not express the intent accurately.

Example of a `Map` holding only strings:

```java
import io.swagger.v3.oas.annotations.media.Schema;
import java.util.Map;

public class PartnerEvent {

    @Schema(
        description = "Extension labels, each key having a string value",
        type = "object",
        additionalPropertiesSchema = @Schema(implementation = String.class)
    )
    private Map<String, String> labels;

    // getters and setters
}
```

For an object allowing arbitrary values, an open policy can be expressed with `additionalProperties` depending on the Swagger Annotations version in use:

```java
@Schema(
    description = "Extended metadata with dynamic key names",
    type = "object",
    additionalProperties = Schema.AdditionalPropertiesValue.TRUE
)
private Map<String, Object> metadata;
```

If you need to close the schema so undeclared properties are not accepted, you can use:

```java
@Schema(additionalProperties = Schema.AdditionalPropertiesValue.FALSE)
public class StrictUserRequest {
    private String name;
    private String email;

    // getters and setters
}
```

Annotation attribute names and enum values can depend on the `swagger-annotations` version managed by springdoc. When upgrading libraries, check the annotation API in the actual version and inspect the generated YAML. Do not override the Swagger Annotations version independently just to use a new attribute if doing so breaks Spring Boot/springdoc dependency management.

## 6. Free-Form Data with `JsonNode` or `Object`

When dynamic values can be multiple different JSON types, Java `Object` or Jackson `JsonNode` are two common choices.

### `Map<String, Object>`

`Map<String, Object>` fits when the data is an object with string keys whose values can be strings, numbers, booleans, lists, or nested maps.

```java
public class IntegrationPayload {
    private Map<String, Object> attributes;

    // getters and setters
}
```

Its advantage is ease of use with standard Java types. Its downside is that values can become `String`, `Integer`, `Double`, `Boolean`, `List`, `Map`, or other types depending on deserialization. Processing code must check types before casting and cannot assume every value shares the same structure.

### `JsonNode`

Jackson's `JsonNode` represents a JSON tree. It can represent objects, arrays, strings, numbers, booleans, or null. If an API field must be a free-form object, check that the node is an object before processing.

```java
public class WebhookRequest {
    private String eventType;
    private JsonNode payload;

    // getters and setters
}
```

`JsonNode` is useful when preserving nested JSON structures without mapping them to fixed POJOs. It also provides safer traversal APIs than multi-level casting from `Object`. However, the OpenAPI schema may need extra annotations to clarify whether a field is a free-form object, an array, or any JSON value.

Do not use `Object` or `JsonNode` merely to avoid designing DTOs. When data structures are stable, strongly typed POJOs provide better validation, documentation, and client code.

## 7. Capturing Undeclared Properties with Jackson

Jackson provides `@JsonAnySetter` and `@JsonAnyGetter` to handle JSON properties that have no corresponding fixed properties on the Java class.

- `@JsonAnySetter` captures unmapped properties when deserializing JSON.
- `@JsonAnyGetter` emits key/value pairs from a `Map` as top-level sibling properties in JSON when serializing.

Example:

```java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import java.util.LinkedHashMap;
import java.util.Map;

public class EventPayload {
    private String eventType;
    private final Map<String, Object> extensions = new LinkedHashMap<>();

    public String getEventType() {
        return eventType;
    }

    public void setEventType(String eventType) {
        this.eventType = eventType;
    }

    @JsonAnySetter
    public void addExtension(String name, Object value) {
        extensions.put(name, value);
    }

    @JsonAnyGetter
    public Map<String, Object> getExtensions() {
        return extensions;
    }
}
```

Given input JSON:

```json
{
  "eventType": "order.updated",
  "source": "partner-a",
  "retryCount": 2
}
```

Jackson binds `eventType` to the declared property and puts `source` and `retryCount` into the `extensions` map. When serializing, `@JsonAnyGetter` flattens map entries out as sibling properties:

```json
{
  "eventType": "order.updated",
  "source": "partner-a",
  "retryCount": 2
}
```

This differs from an ordinary field like `Map<String, Object> metadata`, which normally serializes as a nested `metadata: { ... }` object. `@JsonAnyGetter` flattens the map to the same level as other properties.

When using `@JsonAnySetter`/`@JsonAnyGetter`, verify whether springdoc generates `additionalProperties` as intended. Depending on the Jackson, Swagger Core, and springdoc versions, inference from Jackson annotations alone may not describe the entire policy. Add `@Schema` on the class or use a customizer to adjust the schema.

## 8. Distinguishing `additionalProperties` from `@JsonIgnoreProperties`

These two mechanisms solve different problems:

| Mechanism | Scope | Outcome |
|---|---|---|
| OpenAPI `additionalProperties: false` | Schema contract | Declares that properties outside `properties` are disallowed |
| OpenAPI `additionalProperties: true` | Schema contract | Allows undeclared properties |
| OpenAPI `additionalProperties: {schema}` | Schema contract | Allows dynamic properties while constraining value types |
| Jackson `@JsonIgnoreProperties(ignoreUnknown = true)` | JSON deserialization | Skips unrecognized properties; does not store them in a Map |
| Jackson `@JsonAnySetter` | JSON deserialization | Captures unrecognized properties into an application-specified handler |

Example:

```java
@JsonIgnoreProperties(ignoreUnknown = true)
public class UserRequest {
    private String name;

    // getters and setters
}
```

If a request includes `"admin": true`, Jackson can ignore that property rather than storing it. This is not equivalent to the API supporting dynamic metadata fields. Nor does the OpenAPI document automatically become `additionalProperties: true` simply because the class has `ignoreUnknown = true`.

Conversely, declaring `additionalProperties: false` in a schema does not automatically configure Jackson to reject requests with unknown fields. Jackson may ignore or reject them depending on `FAIL_ON_UNKNOWN_PROPERTIES`, annotations, and deserialization setup. To enforce the schema policy on the server, configure runtime or a corresponding validator.

## 9. Choosing a Policy for Undeclared Properties

There are three common policies. The choice affects extensibility, data control, and API compatibility.

| Policy | Schema | Fits when | Risks to manage |
|---|---|---|---|
| Fully open | `additionalProperties: true` | Payloads genuinely need to accept arbitrary keys and JSON values | Harder validation, weak client types, risk of unexpected input |
| Typed open | `additionalProperties: { ... }` | Key names vary while value types follow clear rules | Mistyped values must be handled consistently at runtime |
| Closed | `additionalProperties: false` | Contracts need an exact property set with strict control | Adding new fields can break strict clients or older requests |

Example for a typed open configuration:

```yaml
type: object
properties:
  configVersion:
    type: string
required:
  - configVersion
additionalProperties:
  type: string
```

The object has `configVersion` and arbitrary other keys with string values. This policy works well when dynamic keys are configuration property names with uniform value types.

If only part of the data needs extensibility, create an explicit field such as `extensions` or `metadata` rather than leaving the entire top-level object open:

```yaml
type: object
properties:
  id:
    type: string
    format: uuid
  status:
    type: string
  extensions:
    type: object
    additionalProperties: true
additionalProperties: false
```

This design keeps `id` and `status` within a controlled field set while permitting dynamic data inside the `extensions` area. It is often a balanced choice between extensibility and contract clarity.

## 10. Impact of OpenAPI 3.0 and 3.1

`additionalProperties` exists in both OpenAPI 3.0 and 3.1, though their Schema Object foundations differ:

- OpenAPI 3.0 uses a subset and variation of JSON Schema. Schemas support `additionalProperties` as a Boolean or a Schema Object.
- OpenAPI 3.1 aligns more closely with JSON Schema 2020-12 and supports more JSON Schema keywords.

The basic examples (`true`, `false`, and value schemas for `additionalProperties`) can appear in both versions. However, if a schema uses other advanced JSON Schema keywords, verify whether the OpenAPI version and validator/client tools support them.

Do not assume every OpenAPI 3.0 tool fully understands 3.1 schemas. Check the `openapi` field at the top of the document generated by springdoc, the library version, and support across Swagger UI, code generators, mock servers, and pipeline validators.

## 11. Customizing Schemas When springdoc Infers Incorrectly

If springdoc infers a schema that misses your intent, adjust it using `@Schema` or customizers.

For example, a `Map` holding values of shape `MetadataEntry`:

```java
public class MetadataEntry {
    private String value;
    private String source;

    // getters and setters
}

public class EventRequest {
    @Schema(
        description = "Metadata with dynamic keys; each value uses the MetadataEntry structure",
        type = "object",
        additionalPropertiesSchema = @Schema(implementation = MetadataEntry.class)
    )
    private Map<String, MetadataEntry> metadata;

    // getters and setters
}
```

If annotations are insufficient, use an `OpenApiCustomizer` to update schemas in the document. Skeleton example:

```java
@Bean
OpenApiCustomizer dynamicMetadataSchemaCustomizer() {
    return openApi -> {
        // Find the EventRequest schema and adjust additionalProperties.
        // Only modify schemas with clearly identified names/conditions.
    };
}
```

A customizer changes the published OpenAPI model; it does not alter Java types, Jackson, or Spring data binding. If documentation allows strings while the application only accepts numbers, the contract and runtime still conflict. Check both after customizing.

## 12. Verifying Dynamic Property Policies

After generating a schema with `additionalProperties`, verify both the document and application behavior:

1. Download `/v3/api-docs` or `/v3/api-docs.yaml`.
2. Locate the DTO schema and identify which objects have `properties` alongside `additionalProperties`.
3. Confirm whether the policy is open, typed open, or closed.
4. Send JSON containing all declared properties.
5. Send an extra undeclared property to verify runtime behavior.
6. For schemas with typed values, test both valid and invalid value types.
7. With `@JsonAnySetter`, confirm unknown fields land in the right `Map`; with `@JsonAnyGetter`, confirm JSON output has the expected shape.
8. Run an OpenAPI validator and verify client tools can process the dynamic schema.

Example testing an open schema with string values:

```json
{
  "labels": {
    "source": "partner-a",
    "region": "ap-southeast-1"
  }
}
```

A numeric value in the same `Map`:

```json
{
  "labels": {
    "retryCount": 3
  }
}
```

does not conform to `additionalProperties: { type: string }`. However, the application will only reject the request if runtime validation or processing actually checks that type.

## 13. Common Pitfalls

| Symptom | Possible cause | Resolution |
|---|---|---|
| `Map` lacks expected `additionalProperties` | Generic type lost, raw `Map` used, or model converter failed to infer | Declare concrete generics and inspect generated schema |
| `Map<String, String>` allows arbitrary values in docs | Metadata overridden or wrong annotation | Specify value schema with `@Schema` and inspect YAML |
| Unknown fields skipped even though intended to be kept | Only used `@JsonIgnoreProperties(ignoreUnknown = true)` | Use `@JsonAnySetter` or an explicit `Map` property |
| Unknown fields emitted as unintended nested object | Used a `Map` property instead of `@JsonAnyGetter` or vice versa | Choose clearly between nested JSON object vs. sibling properties |
| Schema allows unknown fields but server rejects them | Runtime Jackson/validator is stricter than the contract | Align unknown-property handling with the schema |
| Schema forbids unknown fields but server accepts them | `additionalProperties: false` is documentation metadata only | Enable appropriate runtime checks if the API requires rejection |
| Client generator emits overly broad `Object` type | `additionalProperties: true` without a value schema | Use a concrete value schema if business rules allow |
| Swagger UI does not display individual dynamic keys | Key names are unknown beforehand and schema uses additional properties | Document rules, examples, and value schema; test requests manually |

## 14. Design Principles

- Use `Map<String, T>` when key names vary while the value type can be fixed.
- Use `Map<String, Object>` or `JsonNode` only when flexible JSON structures are genuinely needed.
- Use `additionalProperties: true` for unconstrained open data areas; use a concrete schema whenever value types can be restricted.
- Use `additionalProperties: false` for objects requiring a fixed, tightly controlled property set.
- Isolate open data inside a `metadata` or `extensions` field if only part of the object needs extensibility.
- Use `@JsonAnySetter` to capture unknown fields and `@JsonAnyGetter` to emit a `Map` as sibling properties.
- Distinguish ignoring unknown fields via `@JsonIgnoreProperties` from capturing them via `@JsonAnySetter`.
- Do not treat `additionalProperties` as a runtime validator; add corresponding validation or processing logic.
- Account for OpenAPI 3.0/3.1 compatibility and documentation consumers.
- Verify generated schemas, JSON serialization/deserialization, and client behavior after every change.

## Conclusion

`additionalProperties` defines the policy for object properties not listed in `properties`: permitting any value, permitting values matching a specific schema, or forbidding them altogether. In Spring Boot, `Map` and `JsonNode` represent dynamic data; Jackson's `@JsonAnySetter`/`@JsonAnyGetter` control capturing and emitting undeclared properties; springdoc and `@Schema` publish that policy in the OpenAPI contract. Choose an openness level suited to the domain, keep the contract synchronized with runtime behavior, and bound free-form areas so APIs remain controllable, testable, and stable.
