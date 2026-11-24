# Integers, Numbers, Booleans, Strings, and Any Type

Schemas describe data types and valid values for requests or responses in an OpenAPI contract. When using springdoc-openapi, schemas are usually inferred from Java types in controllers and DTOs, and can then be supplemented with Swagger annotations such as <code>@Schema</code>, Bean Validation constraints, or OpenAPI configuration.

The most frequently occurring basic types are integers, floating-point/decimal numbers, booleans, and strings. In addition, some APIs accept flexible JSON data whose structure cannot be fixed ahead of time; in those cases, it is necessary to clearly describe whether the schema allows any type or is an object with dynamic properties.

## 1. Data Types in OpenAPI

A Schema Object uses the <code>type</code> attribute to describe the data type. For basic types, common values are:

| type | Meaning | JSON Example |
|---|---|---|
| <code>integer</code> | Whole number without a fractional part | <code>42</code> |
| <code>number</code> | Number that may have a fractional part | <code>19.95</code> |
| <code>boolean</code> | Logical value | <code>true</code>, <code>false</code> |
| <code>string</code> | Character string | <code>"Spring Boot"</code> |
| Undeclared <code>type</code> | Not restricted to a specific JSON type | Any valid JSON value |

<code>format</code> can add specific information to a type, such as <code>int64</code> for a 64-bit integer or <code>date-time</code> for a date-time string. <code>format</code> does not replace <code>type</code>: a date-time schema still has <code>type: string</code>.

JSON examples show data types directly. Numbers and booleans are not enclosed in quotation marks; strings must be enclosed in quotation marks. For example, <code>25</code> is a number, whereas <code>"25"</code> is a string.

## 2. Integers: integer

Use <code>type: integer</code> when a value has no fractional part, such as quantity, page number, age, or retry count:

~~~yaml
type: integer
format: int32
minimum: 0
maximum: 1000
example: 25
~~~

Commonly used attributes:

- <code>format: int32</code>: hints at a 32-bit signed integer.
- <code>format: int64</code>: hints at a 64-bit signed integer.
- <code>minimum</code> and <code>maximum</code>: lower and upper bounds, inclusive by default.
- <code>exclusiveMinimum</code> and <code>exclusiveMaximum</code>: specifies exclusive bounds according to the corresponding OAS version.
- <code>multipleOf</code>: requires the value to be a multiple of a given number.

### 2.1. int32 and int64

OpenAPI commonly uses two formats to describe integer sizes:

| Schema | Signed Integer Range |
|---|---:|
| <code>integer / int32</code> | -2,147,483,648 to 2,147,483,647 |
| <code>integer / int64</code> | -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807 |

In Java, <code>int</code> and <code>Integer</code> usually correspond to a 32-bit integer; <code>long</code> and <code>Long</code> usually correspond to a 64-bit integer. <code>BigInteger</code> can represent integers larger than the <code>int64</code> range; do not attach format <code>int64</code> if the API actually allows values exceeding that limit.

Formats help tools understand schema intent, but exact enforcement depends on validators and code generators. If value ranges are part of the contract, declare bounds with <code>minimum</code>/<code>maximum</code> and verify runtime validation as well.

### 2.2. Declaring Integers in a DTO

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;

public record InventoryRequest(
    @Schema(
        description = "Quantity of product in stock",
        type = "integer",
        format = "int32",
        example = "25",
        minimum = "0",
        maximum = "1000"
    )
    @Min(0)
    @Max(1000)
    Integer quantity
) {}
~~~

springdoc reads Java types and annotations to generate the schema. In the example, <code>Integer</code> indicates an integer type; <code>@Schema</code> describes the format and example in documentation; <code>@Min</code> and <code>@Max</code> enforce bounds when Bean Validation is enabled.

<code>@Schema</code> does not replace runtime validation. If you only declare <code>minimum</code> in documentation without the controller validating the data, clients can still send out-of-bounds values.

## 3. Numbers: number

Use <code>type: number</code> for data that may contain a fractional part, such as temperature, ratios, or measurements:

~~~yaml
type: number
format: double
minimum: 0
maximum: 100
multipleOf: 0.01
example: 19.95
~~~

Common formats:

| Format | Common Meaning |
|---|---|
| <code>float</code> | Single-precision floating-point number |
| <code>double</code> | Double-precision floating-point number |

In Java, <code>float</code>/<code>Float</code> typically correspond to <code>number / float</code>; <code>double</code>/<code>Double</code> typically correspond to <code>number / double</code>. <code>BigDecimal</code> represents decimal numbers with arbitrary size and scale; it should usually be described as <code>number</code> without attaching a floating-point format if you want to preserve exact decimal semantics.

For currency or financial calculations, use <code>BigDecimal</code> in Java and clearly specify the number of decimal places, rounding rules, and value limits. The <code>double</code> type uses binary floating-point representation, so some familiar decimal numbers cannot be represented exactly.

### 3.1. BigDecimal Example

~~~java
import java.math.BigDecimal;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;

public record PriceRequest(
    @Schema(
        description = "Product price in the API's currency",
        type = "number",
        example = "199.90",
        minimum = "0"
    )
    @DecimalMin("0.00")
    BigDecimal price
) {}
~~~

The schema expresses price as a number, not a string containing digits. Valid JSON has the form <code>{"price": 199.90}</code>; the form <code>{"price": "199.90"}</code> is a string and does not match a numeric schema.

## 4. Boolean

A boolean has only two values: <code>true</code> and <code>false</code>. In OpenAPI, use:

~~~yaml
type: boolean
example: true
~~~

In Java, both primitive <code>boolean</code> and wrapper <code>Boolean</code> map to a Boolean schema. The important difference lies in nullability in Java: primitive <code>boolean</code> cannot hold null, whereas <code>Boolean</code> can.

DTO example:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

public record NotificationRequest(
    @Schema(
        description = "Whether email notifications are enabled",
        example = "true"
    )
    Boolean emailEnabled
) {}
~~~

Booleans have no separate format. Do not describe boolean values using strings like <code>"true"</code> or <code>"false"</code> unless the contract truly requires a string type.

If a property is optional, specify the behavior when the client omits it. For example, the server may default to <code>false</code>. Whether a property must be present and whether it can accept null are separate schema decisions; describe them accurately according to API rules.

## 5. Strings: string

Strings are used for names, codes, emails, addresses, serialized dates/times, and many other text values:

~~~yaml
type: string
minLength: 1
maxLength: 120
example: Spring Boot
~~~

Common constraints:

| Attribute | Meaning |
|---|---|
| <code>minLength</code> | Minimum number of characters |
| <code>maxLength</code> | Maximum number of characters |
| <code>pattern</code> | Regular expression the string must satisfy |
| <code>enum</code> | List of allowed values |
| <code>format</code> | Hint for a known string format |

Example of a status code accepting only specific values:

~~~yaml
type: string
enum:
  - PENDING
  - APPROVED
  - REJECTED
example: PENDING
~~~

### 5.1. Common String Formats

| Format | Meaning | Example |
|---|---|---|
| <code>date</code> | Date in full-date form | <code>2026-11-20</code> |
| <code>date-time</code> | Timestamp in RFC 3339 format | <code>2026-11-20T10:30:00Z</code> |
| <code>email</code> | Email address | <code>dev@example.com</code> |
| <code>uuid</code> | UUID identifier | <code>550e8400-e29b-41d4-a716-446655440000</code> |
| <code>uri</code> | URI | <code>https://example.com/items/1</code> |
| <code>hostname</code> | Hostname | <code>api.example.com</code> |
| <code>ipv4</code> / <code>ipv6</code> | IP address | <code>192.0.2.10</code> |
| <code>byte</code> | Base64-encoded binary data | <code>SGVsbG8=</code> |
| <code>binary</code> | Binary data | Commonly used when describing file content |
| <code>password</code> | UI hint for password input | Do not display real values in documentation |

These formats are semantic information for tools. Format checking strictness can vary between validators, Swagger UI, and code generators. If email, UUID, or custom formats need validation, check them at the application layer using Bean Validation or business logic.

### 5.2. Dates and Timestamps

Common Java types:

| Java Type | Common Schema |
|---|---|
| <code>LocalDate</code> | <code>string / date</code> |
| <code>LocalDateTime</code> | <code>string / date-time</code> |
| <code>OffsetDateTime</code> | <code>string / date-time</code> |
| <code>Instant</code> | <code>string / date-time</code> |

Example:

~~~java
import java.time.LocalDate;
import java.time.OffsetDateTime;

public record BookingRequest(
    LocalDate startDate,
    OffsetDateTime createdAt
) {}
~~~

A date is a calendar date without necessarily having a time zone. <code>LocalDateTime</code> does not contain an offset, so its serialized string may not represent a global instant. Timestamps should have a clear time zone convention; use <code>OffsetDateTime</code> or <code>Instant</code> when the API needs to represent a point on the timeline. Inspect the generated JSON to confirm suitable <code>type</code> and <code>format</code>.

## 6. Mapping Java Types to Basic Schemas

springdoc-openapi uses metadata from Spring and swagger-core to infer schemas from Java types. The table below describes common mappings:

| Java Type | OpenAPI Type | Common Format |
|---|---|---|
| <code>byte</code>, <code>short</code>, <code>int</code>, <code>Integer</code> | <code>integer</code> | <code>int32</code> |
| <code>long</code>, <code>Long</code> | <code>integer</code> | <code>int64</code> |
| <code>BigInteger</code> | <code>integer</code> | Not necessarily a fixed format |
| <code>float</code>, <code>Float</code> | <code>number</code> | <code>float</code> |
| <code>double</code>, <code>Double</code> | <code>number</code> | <code>double</code> |
| <code>BigDecimal</code> | <code>number</code> | Inspect and avoid forcing float/double if precision is needed |
| <code>boolean</code>, <code>Boolean</code> | <code>boolean</code> | None |
| <code>String</code>, <code>char</code>, <code>Character</code> | <code>string</code> | None by default |
| <code>UUID</code> | <code>string</code> | <code>uuid</code> |
| <code>LocalDate</code> | <code>string</code> | <code>date</code> |
| <code>OffsetDateTime</code>, <code>Instant</code> | <code>string</code> | <code>date-time</code> |

These are common mappings; library versions, `ObjectMapper` configuration, and custom converters may alter the output. Especially for <code>BigInteger</code>, <code>BigDecimal</code>, temporal types, and custom types, inspect the actual schema at <code>/v3/api-docs</code>.

## 7. Any Type: Schema Without a Restricted Type

Sometimes an API needs to accept a JSON value whose type varies by event kind, configuration, or extension data. In that case, you can use a schema without declaring <code>type</code>:

~~~yaml
components:
  schemas:
    JsonValue: {}
~~~

This empty schema does not restrict the value to a single JSON type. It can represent a string, number, integer, boolean, object, array, or null according to the schema semantics of the OpenAPI/JSON Schema version in use.

Do not confuse an any-type schema with:

~~~yaml
type: object
~~~

The schema above only accepts a JSON object, not any JSON value. Similarly, <code>type: object</code> with <code>additionalProperties</code> describes an object with dynamic properties, not an arbitrary value.

### 7.1. Objects with Dynamic Properties

If the payload is always an object but property names vary, use <code>type: object</code> with <code>additionalProperties</code>:

~~~yaml
type: object
additionalProperties: {}
example:
  source: mobile
  retryCount: 2
  verified: true
~~~

This example allows an object with arbitrary properties, where each property can contain any JSON value. If all values must be strings, describe it more strictly:

~~~yaml
type: object
additionalProperties:
  type: string
example:
  region: south
  language: vi
~~~

### 7.2. Using JsonNode for Flexible JSON Data

In Java, Jackson's <code>JsonNode</code> is an appropriate type when working on a JSON tree without knowing the structure beforehand. A <code>JsonNode</code> property can hold an object, array, or scalar.

You can declare an any-type component schema using an OpenAPI bean:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.media.Schema;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class FlexibleJsonSchemaConfiguration {

    @Bean
    OpenAPI flexibleJsonOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Event API")
                .version("1.0.0"))
            .components(new Components()
                .addSchemas("JsonValue",
                    new Schema<>().description("Any valid JSON value")));
    }
}
~~~

Then reference the schema in a DTO:

~~~java
import com.fasterxml.jackson.databind.JsonNode;
import io.swagger.v3.oas.annotations.media.Schema;

public record EventRequest(
    @Schema(ref = "#/components/schemas/JsonValue")
    JsonNode payload
) {}
~~~

The <code>JsonValue</code> component does not declare <code>type</code>, so the schema does not restrict payload to an object or a specific type. If the application already has an OpenAPI bean, add the component to the existing configuration instead of creating a second independent bean.

Do not assume every Java <code>Object</code> or <code>JsonNode</code> type is output by springdoc as an empty schema. Model converters may produce a different schema depending on version and configuration. After using <code>@Schema(ref = ...)</code> or a customizer, verify the actual reference in the generated documentation.

### 7.3. When Should oneOf or anyOf Be Used?

An any-type schema is flexible but provides little information to API consumers. If the payload only has a few known structures, explicitly describe the options with <code>oneOf</code> or <code>anyOf</code>.

~~~yaml
oneOf:
  - $ref: "#/components/schemas/CardPayment"
  - $ref: "#/components/schemas/BankTransfer"
discriminator:
  propertyName: paymentType
~~~

The example above states that the payload must match one of the listed payment schemas. It helps Swagger UI, validators, and code generators understand the structure better than a completely unconstrained schema. Only use <code>discriminator</code> when the payload actually has a discriminating property and schemas are designed accordingly.

## 8. Combining @Schema and Bean Validation

The <code>@Schema</code> annotation adds OpenAPI metadata such as type, format, example, description, minimum, maximum, minLength, maxLength, and pattern. Bean Validation specifies conditions that the application checks at runtime.

Combined DTO example:

~~~java
import java.math.BigDecimal;
import java.util.UUID;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record ProductRequest(
    @Schema(
        description = "Product name",
        example = "Wireless Mouse",
        minLength = 1,
        maxLength = 120,
        requiredMode = Schema.RequiredMode.REQUIRED
    )
    @NotBlank
    @Size(max = 120)
    String name,

    @Schema(
        description = "Stock quantity",
        type = "integer",
        format = "int64",
        example = "250",
        minimum = "0",
        maximum = "1000000"
    )
    @Min(0)
    @Max(1000000)
    Long stock,

    @Schema(
        description = "Product price",
        type = "number",
        example = "1299.95",
        minimum = "0"
    )
    @DecimalMin("0.00")
    BigDecimal price,

    @Schema(
        description = "Whether it is currently on sale",
        type = "boolean",
        example = "true"
    )
    Boolean active,

    @Schema(
        description = "Category ID",
        type = "string",
        format = "uuid",
        example = "550e8400-e29b-41d4-a716-446655440000"
    )
    UUID categoryId
) {}
~~~

The controller enables validation with <code>@Valid</code>:

~~~java
@PostMapping("/products")
ResponseEntity<Void> createProduct(
        @Valid @RequestBody ProductRequest request) {
    // Save product after data is validated
    return ResponseEntity.accepted().build();
}
~~~

Constraints in the schema and Bean Validation must stay consistent. For example, <code>@Schema(maxLength = 120)</code> and <code>@Size(max = 120)</code> describe the same limit. If a limit is declared in only one layer and omitted in the other, documentation and runtime behavior can diverge.

<code>requiredMode</code> controls property presence in the OpenAPI schema. <code>@NotBlank</code>, <code>@Min</code>, or <code>@DecimalMin</code> validate values at runtime when validation is enabled. Do not treat these two mechanisms as one.

## 9. Inspecting Schemas Generated by Springdoc

After starting the application, fetch the specification:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Verify the following items:

1. Integers are output as <code>type: integer</code>, and decimal numbers as <code>type: number</code>.
2. Booleans are output as <code>type: boolean</code>, not string.
3. Strings have appropriate <code>format</code> such as <code>date</code>, <code>date-time</code>, or <code>uuid</code>.
4. Numeric bounds, lengths, patterns, and enums accurately reflect validation.
5. Any-type schemas are not mistakenly generated as <code>type: object</code> if the API allows scalars or arrays.
6. Component references are not missing or pointing to the wrong target.

You can test representative payloads for each type:

~~~json
{
  "quantity": 25,
  "price": 199.95,
  "active": true,
  "name": "Wireless Mouse"
}
~~~

For any-type schemas, test payloads such as numbers, strings, booleans, arrays, objects, and null if permitted by the API. This helps verify that the schema accurately describes the range of data the endpoint accepts.

## 10. Common Pitfalls

**Declaring a number but using a string example.** <code>example: "25"</code> can mislead readers about the type. For numbers, use unquoted numeric examples such as <code>example: 25</code> in YAML.

**Using integer for data with fractional parts.** Prices or ratios with fractional parts should use <code>number</code>. Choose a Java type and constraints suited to the required precision.

**Attaching a format incompatible with the value range.** <code>int64</code> does not accurately describe a <code>BigInteger</code> that exceeds 64-bit bounds. <code>double</code> does not express the exact decimal intent of <code>BigDecimal</code>.

**Assuming format validates data automatically.** <code>format: email</code> or <code>format: uuid</code> is metadata for tools. Add runtime validation if the API needs to reject invalid data.

**Confusing booleans with strings.** JSON booleans are unquoted <code>true</code>/<code>false</code>. The string <code>"true"</code> is a different data type.

**Using type object for all JSON.** <code>type: object</code> does not allow scalars or arrays. If the API accepts any JSON value, use a schema without a type restriction; if it only accepts objects with dynamic keys, use <code>additionalProperties</code>.

**Assuming Object or JsonNode always generates the desired schema.** Inspect springdoc's output and use a component schema or customizer to express intent clearly if needed.

## 11. Pre-Publication Checklist

- [ ] Integers use <code>integer</code> and a format matching the value range.
- [ ] Decimals use <code>number</code>; currency types consider <code>BigDecimal</code>.
- [ ] Booleans use <code>boolean</code>, not strings.
- [ ] Strings have appropriate length, pattern, enum, or format when needed.
- [ ] Format is treated as metadata with corresponding runtime validation if needed.
- [ ] Any-type schemas are clearly distinguished from objects with dynamic properties.
- [ ] Flexible data uses <code>JsonNode</code> or an appropriate type with a verified schema.
- [ ] <code>@Schema</code> annotations are consistent with Bean Validation.
- [ ] Inspected actual documentation at <code>/v3/api-docs</code>.

## References

- [OpenAPI Specification – Data Types](https://spec.openapis.org/oas/latest.html#data-types): data types, formats, and schemas in OpenAPI.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): Schema Object structure and constraints.
- [JSON Schema – Numeric Types](https://json-schema.org/understanding-json-schema/reference/numeric): integer, number, and numeric bounds.
- [JSON Schema – String](https://json-schema.org/understanding-json-schema/reference/string): string length, pattern, and format.
- [Swagger Core – Schema annotation](https://docs.swagger.io/swagger-core/v2.2.0/apidocs/io/swagger/v3/oas/annotations/media/Schema.html): attributes of the <code>@Schema</code> annotation.
- [springdoc-openapi](https://springdoc.org/): Spring Boot integration and OpenAPI specification generation.
