# Maps, String Keys, and `additionalProperties`

In Java, `Map<K, V>` stores key-value pairs. When data is represented as a JSON object, each key becomes a property name of the object. OpenAPI describes this data type using `type: object`; the `additionalProperties` field indicates what values dynamic properties are allowed to have.

With springdoc-openapi, declaring explicit generic types is usually enough for the library to infer a schema for a map. For example, `Map<String, Integer>` becomes an object with integer values; `Map<String, ProductAttribute>` becomes an object with values matching the `ProductAttribute` schema. Properly understanding `additionalProperties` helps distinguish an object with a fixed set of fields from an object with keys determined by clients or business data.

## 1. Objects with Fixed Fields vs. Maps with Dynamic Keys

A regular DTO has properties known in advance:

```java
public record CustomerRequest(
    String name,
    String email
) {}
```

The corresponding OpenAPI schema typically has `properties` for `name` and `email`:

```yaml
type: object
properties:
  name:
    type: string
  email:
    type: string
```

Field names are fixed in the model. Clients know the valid properties and the meaning of each property ahead of time.

Conversely, a map allows property names to vary by data:

```java
Map<String, Integer> stockByWarehouse;
```

A JSON value might look like:

```json
{
  "warehouse-hcm": 120,
  "warehouse-hn": 85,
  "warehouse-dn": 42
}
```

Warehouse names are dynamic keys. The API does not declare each warehouse in advance; it only specifies that every value in the object must be an integer. OpenAPI expresses this with `additionalProperties`.

| Concept | Purpose |
| --- | --- |
| `properties` | Describes fields of the object with fixed names. |
| `additionalProperties` | Describes values of additional fields with dynamic names, or indicates whether they are allowed. |

`additionalProperties` is not a list of allowed key names. It describes the schema of the value corresponding to each additional key.

## 2. How `Map<String, V>` Maps to OpenAPI

In JSON, object property names are always strings. Therefore `Map<String, V>` is the most natural map form for JSON objects. The type `V` determines the schema of each value:

| Java Type | Commonly Generated OpenAPI Schema |
| --- | --- |
| `Map<String, String>` | `type: object`, `additionalProperties: { type: string }` |
| `Map<String, Integer>` | `type: object`, `additionalProperties: { type: integer, format: int32 }` |
| `Map<String, BigDecimal>` | `type: object`, `additionalProperties: { type: number }` |
| `Map<String, Boolean>` | `type: object`, `additionalProperties: { type: boolean }` |
| `Map<String, ProductAttribute>` | `type: object`, `additionalProperties` references the `ProductAttribute` schema |
| `Map<String, List<String>>` | `type: object`, additional values are arrays with string items |

Example of a DTO with custom labels:

```java
public record ProductRequest(
    @NotBlank
    String name,

    Map<String, String> labels
) {}
```

The client can send:

```json
{
  "name": "Mechanical keyboard",
  "labels": {
    "color": "black",
    "layout": "US",
    "switch": "linear"
  }
}
```

The schema of `labels` looks like:

```yaml
labels:
  type: object
  additionalProperties:
    type: string
```

Springdoc typically infers the value schema from the generic parameter `String`. There is no need to declare keys `color`, `layout`, or `switch` individually, because they are dynamic data.

## 3. Maps with Object or Dedicated Model Values

Maps do not only hold primitive types. When each value has a well-defined structure, create a dedicated DTO so clients understand the inner fields:

```java
public record ProductAttribute(
    String value,
    String source,
    Instant updatedAt
) {}

public record ProductResponse(
    UUID id,
    String name,
    Map<String, ProductAttribute> attributes
) {}
```

Response example:

```json
{
  "id": "f8a5f7f4-c1ef-4e37-a2b7-c1c3d1d6a120",
  "name": "Mechanical keyboard",
  "attributes": {
    "color": {
      "value": "black",
      "source": "catalog",
      "updatedAt": "2026-11-20T09:30:00Z"
    },
    "layout": {
      "value": "US",
      "source": "supplier",
      "updatedAt": "2026-11-19T15:00:00Z"
    }
  }
}
```

The schema of `attributes` typically looks like:

```yaml
type: object
additionalProperties:
  $ref: '#/components/schemas/ProductAttribute'
```

Each dynamic key maps to a value structured according to `ProductAttribute`. This preserves flexibility for key names while still strictly describing the shape of each value.

If values are lists, such as `Map<String, List<ProductAttribute>>`, the `additionalProperties` schema will be `type: array` with `items` referencing `ProductAttribute`. For nested maps like `Map<String, Map<String, String>>`, the additional value is itself an object with its own `additionalProperties`. Deep nesting is possible, but overly deep structures make clients harder to understand and validate.

## 4. Three Important Ways to Represent `additionalProperties`

In OpenAPI, `additionalProperties` can be a boolean or a Schema Object:

| Value | Meaning |
| --- | --- |
| `true` | Allows additional properties with values unrestricted by a specific schema. |
| `false` | Disallows additional properties beyond the fields declared in `properties`. |
| A schema object | Allows additional properties, but each property's value must match that schema. |

Example allowing arbitrary values:

```yaml
type: object
additionalProperties: true
```

Example forbidding undeclared fields:

```yaml
type: object
properties:
  name:
    type: string
  email:
    type: string
additionalProperties: false
```

Example allowing dynamic keys where all values must be booleans:

```yaml
type: object
additionalProperties:
  type: boolean
```

In OpenAPI, if `additionalProperties` is omitted, the usual default allows additional properties. Therefore, if the contract requires a closed object, explicitly declare `false` and verify how the server handles unknown fields.

## 5. Using `@Schema` to Customize `additionalProperties`

When generic types are clear, springdoc usually generates an appropriate schema automatically. The `@Schema` annotation is helpful when clearer descriptions are needed or Java types do not retain sufficient generic information.

For a map containing only strings:

```java
public class ProductMetadata {

    @Schema(
        description = "Custom labels; all values are strings",
        additionalPropertiesSchema = String.class
    )
    private Map<String, Object> labels;

    public Map<String, Object> getLabels() {
        return labels;
    }

    public void setLabels(Map<String, Object> labels) {
        this.labels = labels;
    }
}
```

In this example, Java declares values as `Object`, but the annotation publishes values on the wire contract as strings. Only use this override if the application truly guarantees every value is a string. If runtime allows objects, numbers, or booleans, the schema must reflect that.

Whenever possible, declare the exact Java type from the start:

```java
private Map<String, String> labels;
```

When you want to close a DTO and forbid unknown properties, you can use:

```java
@Schema(additionalProperties = Schema.AdditionalPropertiesValue.FALSE)
public record CreateCustomerRequest(
    String name,
    String email
) {}
```

`Schema.AdditionalPropertiesValue.FALSE` tells the OpenAPI schema to disallow extra fields. This annotation only alters the generated contract. Jackson may still ignore unknown fields under the application's default configuration; if the server must reject undeclared data, configure and test deserialization behavior, such as `DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES`.

`additionalPropertiesSchema` and `additionalProperties` are two different attributes of `@Schema`: the first specifies the schema for dynamic values; the second chooses whether to allow, forbid, or infer handling of additional properties. Both should be checked in the documentation for the `swagger-annotations` version used by your springdoc branch.

## 6. Distinguishing Free-Form Maps with `Map<String, Object>`

`Map<String, Object>` is flexible because values can be strings, numbers, booleans, lists, or other objects. However, this type makes the contract weaker:

```java
public record EventPayload(
    String eventType,
    Map<String, Object> data
) {}
```

Clients know `data` is an object, but cannot be sure what type each key holds. The schema may represent `additionalProperties` with an empty schema or an unconstrained form, depending on version and how springdoc handles `Object`.

Only use free-form maps when data is truly arbitrary extensions or when the structure cannot be known beforehand. If fields are fixed per event type, consider concrete DTOs or a polymorphic model with `oneOf`/discriminator. For example, an `ORDER_CREATED` event has `orderId` and `total`, while a `USER_REGISTERED` event has `userId` and `registeredAt`; separate DTOs make documentation, validation, and client code much clearer.

Avoid using raw `Map` without generics:

```java
// Not recommended: value type is not explicitly declared.
Map attributes;

// Clearer: value schema is string.
Map<String, String> attributes;
```

Raw types lose type information at compile time and can make generated schemas overly broad. If `Object` is used, clearly document the structure and examples, and verify the actual schema.

## 7. Map Keys Must Fit JSON Property Names

JSON objects use string property names. Therefore, maps using `String` as keys keep contracts simple and compatible across clients:

```java
Map<String, BigDecimal> prices;
```

If another key type is used, such as `Map<Integer, String>` or `Map<UUID, String>`, Jackson may convert keys to strings when serializing JSON and convert back when deserializing. How conversion behaves depends on configured key serializers/deserializers or converters. OpenAPI still describes JSON object property names as strings, so Java key types do not automatically become numeric or UUID types in JSON structure.

A JSON example for a map with UUID keys still looks like:

```json
{
  "550e8400-e29b-41d4-a716-446655440000": "approved"
}
```

If keys represent identifiers, explain the key format convention in `description` and verify actual values after serialization. If clients need a list of items where the key is typed data, you can use an array of objects instead of a JSON object:

```json
[
  {
    "warehouseId": 101,
    "quantity": 120
  },
  {
    "warehouseId": 205,
    "quantity": 85
  }
]
```

Arrays allow `warehouseId` to be described properly as an integer, whereas JSON object keys are always strings.

## 8. Constraining Entry Counts and Map Keys

OpenAPI Schema has `minProperties` and `maxProperties` bounds to describe the number of properties in an object. You can use `@Schema`:

```java
@Schema(
    description = "Up to 20 product labels",
    maxProperties = 20,
    additionalPropertiesSchema = String.class
)
private Map<String, String> labels;
```

`minProperties` and `maxProperties` apply to the number of key/value pairs in the object. They differ from `minLength`/`maxLength`, which apply to strings, and from `minItems`/`maxItems`, which apply to arrays.

Entry counts can be validated at runtime using custom validation or business logic. For example, if the API only allows at most 20 labels, the server must actually reject maps with more than 20 entries. OpenAPI metadata does not enforce this limit by itself.

For key names, you can use Bean Validation container element constraints to validate at runtime:

```java
public record ProductLabels(
    Map<
        @NotBlank @Pattern(regexp = "^[a-z][a-z0-9_-]*$") String,
        @NotBlank @Size(max = 80) String
    > labels
) {}
```

Constraints on keys and values must be activated with appropriate Bean Validation. Whether they are translated into a `propertyNames` schema or value schema in OpenAPI depends on the OpenAPI, springdoc, and swagger-core versions; inspect `/v3/api-docs`. In OpenAPI 3.1, JSON Schema provides `propertyNames` to describe key naming rules. Do not assume every OpenAPI 3.0 configuration or client generator understands that rule.

## 9. Nested Maps and Dynamic Data Structures

A map can contain another map. Example of per-environment settings:

```java
Map<String, Map<String, String>> settingsByEnvironment;
```

JSON:

```json
{
  "development": {
    "logLevel": "DEBUG",
    "featureX": "true"
  },
  "production": {
    "logLevel": "WARN",
    "featureX": "false"
  }
}
```

General schema:

```yaml
type: object
additionalProperties:
  type: object
  additionalProperties:
    type: string
```

Each level of `additionalProperties` describes the values of keys at that level. When maps are nested multiple levels deep, use meaningful names and consider creating DTOs for each level once structure stabilizes. DTOs provide better descriptions, validation, examples, and field control.

## 10. Inspecting Schemas Generated by Springdoc

After declaring maps or customizing `@Schema`, inspect the actual specification:

1. Start the application and open `/v3/api-docs` or the configured URL.
2. Locate the model with the map property under `components.schemas`.
3. Verify the map has `type: object` and `additionalProperties` carries the right value type.
4. For maps whose values are DTOs, verify `additionalProperties` references the right component schema.
5. For closed objects, verify `additionalProperties: false` is emitted.
6. Send JSON with valid keys and valid values; then test wrong-typed values or unknown fields to verify runtime behavior.
7. Test response serialization to ensure actual keys and values match the schema.

| Symptom | Possible Cause | Resolution |
| --- | --- | --- |
| Map appears as an object without a value type | Used raw `Map` or `Map<String, Object>` | Declare concrete generics or describe value schema via `additionalPropertiesSchema`. |
| Map values in Swagger UI have wrong type | Generic type or annotation override mismatches runtime data | Check `additionalProperties` in `/v3/api-docs` and actual Java types. |
| DTO allows extra fields even though schema says `false` | Jackson still ignores unknown properties | Configure strict deserialization and write request tests. |
| Numeric/UUID keys fail to deserialize | Missing key deserializer or invalid string format | Use `String` keys or configure explicit key serializers/deserializers. |
| Entry count limit exists only in documentation | `maxProperties` is not enforced at runtime | Add validation or business checks in the service. |
| Invalid key names are still accepted in requests | No constraint for map keys | Use container element constraints and test validation. |

## 11. Guidelines for Applying

- Use `Map<String, V>` when key names are dynamic data and all values share one type.
- Prefer concrete generics so springdoc generates accurate `additionalProperties`.
- Use DTOs for structured map values and use `Map<String, Object>` only when genuinely free-form data is needed.
- Use `additionalProperties: false` for closed objects when the contract forbids unknown fields; align Jackson configuration if runtime must reject them too.
- Remember that JSON object keys are always strings; use an array of objects if keys need their own data type.
- Use `minProperties`, `maxProperties`, and validation for entry counts; validate key naming rules separately.
- Inspect generated schemas and actual serialization/deserialization before publishing the API.

`additionalProperties` is central to describing objects with dynamic keys in OpenAPI. When generic types, key rules, and value schemas are clearly defined, clients can work with maps flexibly while still knowing what data is valid. Springdoc helps infer most of the schema from Java, while the application must enforce the bounds and rules published in the contract.

## References

- [OpenAPI Specification – Schema Object and `additionalProperties`](https://spec.openapis.org/oas/latest.html)
- [Swagger Annotations – `@Schema`](https://docs.swagger.io/swagger-core/v2.2.46/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)
- [Springdoc OpenAPI – Official Documentation](https://springdoc.org/)
- [Jackson Databind – Handling Maps and JSON Objects](https://github.com/FasterXML/jackson-databind)
