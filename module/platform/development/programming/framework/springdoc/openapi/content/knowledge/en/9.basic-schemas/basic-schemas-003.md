# Schema Name, Description, Type, and Format

A schema is the part of OpenAPI that describes the shape of data an API receives or returns. A schema indicates whether data is an object, string, number, or array; what type each property has; and familiar formats such as UUID, date, or timestamp. A schema also has a name and description so readers understand what data the component represents.

With springdoc-openapi, most schemas are inferred from Java types, generics, Jackson annotations, and Bean Validation. Swagger Core annotations such as @Schema allow supplementing or adjusting metadata so the generated documentation is clearer. It is important to distinguish OpenAPI metadata from runtime behavior: name, description, type, and format publish the contract; they do not by themselves change how Java serializes, deserializes, or validates data.

## 1. Schema Object and Its Place in OpenAPI

A Schema Object describes a data value. It can sit directly inside a request body or response, or be named under components so multiple operations can reference it.

Inline schema example:

~~~yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        type: object
        properties:
          name:
            type: string
          quantity:
            type: integer
~~~

When a data type is used in multiple places, place the schema in components.schemas and reference it using $ref:

~~~yaml
components:
  schemas:
    ProductInput:
      type: object
      properties:
        name:
          type: string
        quantity:
          type: integer
~~~

A response can reuse the schema:

~~~yaml
responses:
  '200':
    description: Product information
    content:
      application/json:
        schema:
          $ref: '#/components/schemas/ProductInput'
~~~

The schema name is the component's identifier in the document. The description explains the component's meaning. Type and format indicate the structure and representation of the data.

## 2. Distinguishing name, title, and description

These three concepts serve different purposes:

| Attribute | Purpose | Example |
| --- | --- | --- |
| name | Schema or component name generated in OpenAPI when placed on a model | ProductView |
| title | Human-readable title of the Schema Object | Product response |
| description | Explains meaning, conventions, and usage | Public data of a product in the catalog |

In Java, you can declare a name and description for a DTO:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.LocalDateTime;
import java.util.UUID;

@Schema(
    name = "ProductView",
    title = "Product response",
    description = "Product information published by the Catalog API."
)
public record ProductView(
    UUID id,
    String name,
    BigDecimal price,
    LocalDateTime createdAt
) {}
~~~

In this example, name sets the schema name to ProductView; title is a human-readable label; description explains the object's contents. Springdoc can reference that component from requests or responses via $ref.

If name is omitted, springdoc usually infers the schema name from the Java type. Explicit naming is useful when internal class names are unclear, when you want a stable contract name, or when multiple classes share the same name across different packages. Choose unique, domain-meaningful names for the API.

Do not confuse the schema name with JSON property names. For example, to rename the Java property code to product_code in JSON, use a Jackson annotation like @JsonProperty:

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;

public record ProductIdentifier(
    @JsonProperty("product_code")
    @Schema(description = "Public product code", example = "KB-01")
    String code
) {}
~~~

Property names in the contract must match the actual JSON serialized by Jackson. @Schema(name = "...") on a class sets the schema name; @JsonProperty on a field or record component controls the JSON property name.

## 3. Writing Useful Descriptions

Description explains what names and data types cannot convey. A good description states what the data represents, what conventions must be followed, and what important limits integrators must know.

Example:

~~~java
@Schema(
    description = "Selling price in the store's currency. Value excludes shipping fees.",
    example = "199000.00"
)
BigDecimal price
~~~

Comparison:

| Weak description | Clearer description |
| --- | --- |
| Product price | Selling price in the store's currency, excluding shipping fees |
| Creation date | Timestamp when the product was first created, expressed in ISO 8601 |
| Status | Public status of the product; allowed values are ACTIVE, INACTIVE, or OUT_OF_STOCK |

Description in OpenAPI can contain CommonMark/Markdown. Short lists or links can be used if they help readers understand the contract. Avoid putting lengthy business guides inside a single field; use externalDocs to link to supplemental documentation when needed.

Do not include sensitive information, internal data, or examples containing real customer information in descriptions. OpenAPI documents are often shared across multiple client teams and environments.

## 4. Type Describes Basic Data Types

The type field specifies what kind of value the schema accepts. Common types:

| OpenAPI type | Meaning | JSON Example |
| --- | --- | --- |
| string | Character string | "keyboard" |
| integer | Whole number | 42 |
| number | Number that may have a fractional part | 199000.50 |
| boolean | True or false value | true |
| object | Object with properties | {"name":"Keyboard"} |
| array | List of values | ["red","blue"] |

Springdoc typically infers type from Java types:

| Java Type | Commonly Inferred Schema |
| --- | --- |
| String, Character | string |
| Integer, int, Short | integer |
| Long, long | integer, usually with format int64 |
| Float, float | number, usually with format float |
| Double, double | number, usually with format double |
| BigDecimal | number |
| Boolean, boolean | boolean |
| DTO or record | object |
| List<T>, Set<T>, T[] | array with items of type T |
| Map<String, T> | object with additionalProperties of type T |

These are common inference rules; the specific published type may depend on library versions, configuration, and annotations. Inspect the actual JSON/YAML document when the contract requires precision.

DTO example:

~~~java
public record InventoryView(
    String sku,
    int quantity,
    boolean available,
    List<String> labels
) {}
~~~

Corresponding generated schema:

~~~yaml
type: object
properties:
  sku:
    type: string
  quantity:
    type: integer
  available:
    type: boolean
  labels:
    type: array
    items:
      type: string
~~~

Usually you do not need to write type manually if the Java type accurately reflects the structure. Only override it when publishing a special contract and after verifying that actual serialization is compatible.

## 5. Format Adds Meaning to Type

Format refines how a value is interpreted and is typically used together with type. For example, a UUID is still a string but has UUID format; a date is still a string but follows ISO date conventions.

| type | Common format | Meaning |
| --- | --- | --- |
| string | uuid | UUID identifier string |
| string | date | Date in full-date format, e.g., 2026-11-20 |
| string | date-time | Timestamp in date-time format |
| string | byte | Binary data represented as base64 in certain contexts |
| string | binary | Binary content, typically used for files |
| string | password | Password string; tools may display it with masked characters |
| integer | int32 | 32-bit integer |
| integer | int64 | 64-bit integer |
| number | float | Single-precision floating-point number |
| number | double | Double-precision floating-point number |

Example using @Schema annotation:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import java.time.LocalDate;
import java.time.OffsetDateTime;
import java.util.UUID;

public record SubscriptionView(
    @Schema(
        description = "Subscription identifier",
        type = "string",
        format = "uuid",
        example = "7d9c2d0e-8f9d-4a2a-a2c3-0f65b7d2c111"
    )
    UUID id,

    @Schema(
        description = "Effective start date",
        type = "string",
        format = "date",
        example = "2026-11-20"
    )
    LocalDate startsOn,

    @Schema(
        description = "Most recent update timestamp",
        type = "string",
        format = "date-time",
        example = "2026-11-20T10:30:00+07:00"
    )
    OffsetDateTime updatedAt
) {}
~~~

Springdoc usually infers appropriate formats automatically from Java types such as UUID, LocalDate, or OffsetDateTime. Explicit declaration is helpful when you want readable documentation or when the Java type does not fully express the public convention.

## 6. Format Does Not Replace Type or Validation

Type determines the data category; format adds a representation convention. Format does not automatically change Java types, converters, or runtime validation logic.

Example:

- type: string, format: date-time describes a timestamp string.
- type: integer, format: int64 describes a 64-bit integer.
- type: string, format: uuid describes a string shaped like a UUID.

If a controller accepts a String, setting format: date-time only makes the documentation state that the string must follow timestamp conventions. Spring does not automatically parse a String into a time type just because the schema has a format. To parse into a temporal type, use an appropriate Java type or converter/formatter.

Similarly, format: email does not replace email address verification; format: uuid does not replace server-side validation if data is received as a String. OpenAPI tools may also support formats differently: some validators check formats, while others treat format purely as a hint.

When specific data constraints are needed, use appropriate keywords or Bean Validation:

| Requirement | Common Constraint |
| --- | --- |
| Non-empty string | @NotBlank |
| Length-bounded string | @Size |
| Pattern-matching string | @Pattern |
| Number greater than or equal to a value | @Min, @DecimalMin |
| Value must be present | @NotNull |
| Finite set of values | enum or allowableValues |

Example:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Size(max = 80)
    @Schema(description = "Product name", example = "Mechanical Keyboard")
    String name,

    @NotNull
    @DecimalMin("0.01")
    @Schema(description = "Selling price must be greater than 0", example = "199000.00")
    BigDecimal price
) {}
~~~

In Spring Boot 3 and above, validation annotations belong to the jakarta.validation package. The project needs a validation provider and validation enabled at the request entry point, such as using @Valid on the @RequestBody parameter. Validation metadata can be reflected in the schema by springdoc; enforcement remains the responsibility of the Bean Validation runtime.

## 7. Using @Schema on Classes and Properties

The @Schema annotation can be placed on a class, record, or property to add metadata.

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;
import io.swagger.v3.oas.annotations.media.Schema;
import java.math.BigDecimal;
import java.time.OffsetDateTime;
import java.util.List;
import java.util.UUID;

@Schema(
    name = "ProductDetail",
    title = "Product detail",
    description = "Detailed product information in the catalog."
)
public record ProductDetail(
    @Schema(
        description = "Product identifier",
        example = "7d9c2d0e-8f9d-4a2a-a2c3-0f65b7d2c111"
    )
    UUID id,

    @JsonProperty("product_name")
    @Schema(
        description = "Display name of the product",
        example = "Mechanical Keyboard"
    )
    String name,

    @Schema(
        description = "Selling price in the store's currency",
        type = "number",
        example = "199000.00"
    )
    BigDecimal price,

    @Schema(
        description = "Product creation timestamp",
        format = "date-time",
        example = "2026-11-20T10:30:00+07:00"
    )
    OffsetDateTime createdAt,

    @Schema(description = "Labels used for search and categorization")
    List<String> tags
) {}
~~~

In the example:

- Metadata on the record describes the ProductDetail schema.
- Metadata on each component describes the corresponding property.
- @JsonProperty renames the JSON field to product_name.
- UUID, BigDecimal, OffsetDateTime, and List<String> allow springdoc to infer appropriate types; annotations supplement description and example.

Do not set type arbitrarily if it conflicts with the Java type or actual JSON emitted by Jackson. For instance, declaring type: integer for a property serialized as a string will cause code generators and validators to misunderstand the contract.

## 8. Referencing Schemas in Requests and Responses

Once a model has a name, springdoc can reuse it across operations. Example of a controller returning ProductDetail:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping("/{id}")
    ProductDetail getProduct(@PathVariable UUID id) {
        return productService.getDetail(id);
    }
}
~~~

The OpenAPI specification can reference the schema:

~~~yaml
paths:
  /api/products/{id}:
    get:
      responses:
        '200':
          description: Product detail
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductDetail'
components:
  schemas:
    ProductDetail:
      title: Product detail
      description: Detailed product information in the catalog.
      type: object
      properties:
        id:
          type: string
          format: uuid
        product_name:
          type: string
        price:
          type: number
        createdAt:
          type: string
          format: date-time
        tags:
          type: array
          items:
            type: string
~~~

The YAML snippet illustrates the structure. The actual specification may add required, example, constraints, or different property names depending on annotations, Jackson, and project configuration.

If you want explicit control over the response schema, you can use @ApiResponse and @Content:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Product detail",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ProductDetail.class)
    )
)
~~~

This annotation describes the response in OpenAPI. It does not alter the object returned by the controller.

## 9. When Should Explicit type and format Be Used?

Let springdoc infer from Java when Java types already reflect the contract accurately. Only override type or format when there is a clear reason:

| Situation | Approach |
| --- | --- |
| Regular DTO | Let springdoc infer object and properties |
| UUID, LocalDate, OffsetDateTime | Use standard Java types; verify generated format |
| Custom type serialized as string | Use @Schema(type = "string") and format matching the JSON representation |
| File upload or binary data | Describe string/binary and the corresponding media type |
| Integer needing published bit width | Use appropriate Java type or format int32/int64 |
| Model with unclear internal name | Set clear @Schema(name = "...") and description |

If you need a custom format not in the common list, OpenAPI allows extended formats. However, client generators and validators may not understand custom formats. Explain the meaning in description, standardize the representation, and test tools that consume the documentation.

## 10. Support Differences Between OpenAPI 3.0 and 3.1

OpenAPI 3.0 uses type and format sets based on the OAS 3.0 Schema Object model. OpenAPI 3.1 aligns the Schema Object more closely with JSON Schema 2020-12 and supports richer ways of representing certain structures.

Key points to remember:

- Common formats such as date, date-time, uuid, int32, and int64 are recognized by many tools, though validation strictness may vary.
- Format supplements type; do not use format to turn a string into a number or object.
- In OpenAPI 3.1, format may be treated as an annotation depending on vocabulary and validator; do not assume every tool enforces format checks.
- How null values are described differs between OpenAPI 3.0 and 3.1. Do not use format to describe nullability; choose a schema structure compatible with the OpenAPI version being output.

The actual specification version depends on springdoc configuration. Check the openapi field at the top of /v3/api-docs before applying specific JSON Schema keywords.

## 11. Inspecting Generated Schemas

After adding annotations, fetch the OpenAPI JSON or YAML specification from the application:

~~~bash
curl -sS http://localhost:8080/v3/api-docs
curl -sS http://localhost:8080/v3/api-docs.yaml
~~~

Check:

1. Are component names under components.schemas as expected?
2. Do title and description appear properly at the schema level?
3. Does each property have the correct JSON name, type, and format?
4. Do arrays have items of the right type?
5. Are schemas reused via $ref or unexpectedly generated inline?
6. Do examples and constraints match runtime data?
7. Does Swagger UI display descriptions and formats clearly enough for integrators?

If schema names are unexpected, check @Schema(name = "...") on models and classes with duplicate names. If property names are wrong, check Jackson annotations and naming strategy configuration. If format is missing, check Java types, annotations, swagger-core version, and the OpenAPI specification version in use.

Do not look solely at Swagger UI. JSON/YAML is the published contract; verify the generated output directly and check actual requests/responses to be sure the schema matches serialization.

## 12. Common Pitfalls

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Schema has unwanted Java class name | Public name not set or model name collision | Use @Schema(name = "...") with a unique name |
| Swagger UI only shows schema name without explanation | Missing title or description | Add class-level metadata |
| UUID described as generic string | Type or format not inferred as expected | Use UUID or @Schema(format = "uuid") |
| Date/time has wrong format | Incompatible Java type or converter | Choose LocalDate/OffsetDateTime and verify serialization |
| Schema says number but JSON emits string | Overridden type mismatches Jackson serializer | Synchronize Java type, serializer, and annotation |
| Client generator ignores format | Tool does not support that format | Use common formats, describe further, and test generator |
| Property name differs from documentation | Jackson renamed via @JsonProperty or naming strategy | Inspect actual JSON and OpenAPI together |

## 13. Schema Design Workflow

When publishing a DTO as an API schema, proceed in order:

1. Choose a stable schema name meaningful to clients; use @Schema(name = "...") when the default name is unsuitable.
2. Write title and description explaining the role of the data.
3. Use Java types that accurately reflect the serialized JSON.
4. Choose appropriate type and format; do not use format to replace validation or conversion.
5. Describe properties with description, example, and necessary constraints.
6. Use $ref to reuse models in requests/responses where appropriate.
7. Inspect JSON/YAML generated by springdoc and compare against runtime payloads.

A good schema helps integrators understand component names, data meaning, and how each value is represented. When name, description, type, and format are consistent with DTOs and actual JSON, OpenAPI becomes a reliable contract for reading documentation, testing, and generating clients.

## References

- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Data Types](https://spec.openapis.org/oas/latest.html#data-types)
- [Swagger Core – @Schema Annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html)
- [Jackson Annotations – @JsonProperty](https://github.com/FasterXML/jackson-annotations)
- [springdoc-openapi – Documentation](https://springdoc.org/)
