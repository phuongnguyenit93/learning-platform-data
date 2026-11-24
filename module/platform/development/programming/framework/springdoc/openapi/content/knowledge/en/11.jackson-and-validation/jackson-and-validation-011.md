# Keeping ObjectMapper Configuration Consistent with Documented Data

Springdoc-openapi builds schemas from data types and metadata published by the application, whereas Spring MVC uses Jackson via `HttpMessageConverter` to read JSON requests and write JSON responses. If Jackson settings alter property names, date-time formats, enums, null handling, or polymorphic structures, HTTP payloads may diverge from the OpenAPI schema clients see. Therefore, treat `ObjectMapper` configuration, Jackson annotations, and generated documentation as parts of one API contract; changing one requires re-checking the others.

## 1. Three Layers to Keep Consistent

A DTO can be viewed across three layers:

1. **Java model:** field names, getters/setters, data types, and class annotations.
2. **Runtime JSON:** key names, JSON types, omitted values, string formats, and deserialization rules enforced by Jackson.
3. **OpenAPI schema:** property names, types, formats, enums, required lists, and descriptions published by springdoc.

For example, a Java DTO has a `createdAt` field of type `OffsetDateTime`. Jackson may serialize it under the key `created_at` as an offset date-time string; OpenAPI must document the `created_at` property with string type and matching date-time format. If docs still list `createdAt`, client generators produce models that fail to match payloads.

| Configuration | Impact on JSON | What to Check in OpenAPI |
|---|---|---|
| Property naming strategy | Renames keys, e.g. camelCase to snake_case | Names in `properties`, `$ref`, and examples |
| `@JsonProperty` / `@JsonAlias` | Sets output name or alternate input names | Published property name and names clients must send |
| `@JsonInclude` | Omits null, empty, or default values when serializing | Optionality, nullability, and response examples |
| `@JsonFormat` / Java Time module | Alters date-time format or enum representation | `type`, `format`, `pattern`, and examples |
| `@JsonSerialize` / `@JsonDeserialize` | Alters wire representation or parsing of a type | Schema must reflect actual representation |
| `@JsonTypeInfo` / `@JsonSubTypes` | Adds discriminator and selects subtype when reading/writing | `oneOf`, `discriminator`, and subtype schemas |
| Visibility, mix-in, JsonView | Changes which properties are read or written | Whether properties appear properly in each operation |

Springdoc recognizes many Jackson annotations and uses Jackson metadata when generating schemas. However, how customizers, modules, mix-ins, and converters are reflected depends on library versions and application configuration. Do not assume every runtime customization turns into an exact schema automatically; verify actual JSON and `/v3/api-docs`.

## 2. Configuring `ObjectMapper` in Spring Boot

Spring Boot typically auto-configures `ObjectMapper` and `HttpMessageConverter` beans based on dependencies and application properties. When customizing, extend Boot-managed configuration instead of creating an isolated `ObjectMapper` that accidentally causes controllers to use a different mapper.

Example renaming properties to snake_case and omitting null values on serialization:

```java
import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.databind.PropertyNamingStrategies;
import org.springframework.boot.autoconfigure.jackson.Jackson2ObjectMapperBuilderCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer apiJsonCustomizer() {
        return builder -> {
            builder.propertyNamingStrategy(PropertyNamingStrategies.SNAKE_CASE);
            builder.serializationInclusion(JsonInclude.Include.NON_NULL);
        };
    }
}
```

With this setup, Java field `productCode` normally serializes as `product_code`; properties whose value is `null` are omitted from JSON output. The customization applies to the builder Spring Boot uses to construct the mapper for auto-configured converters.

Avoid declaring a standalone `new ObjectMapper()` bean without understanding how it interacts with the Boot-managed mapper. If the application uses multiple converters or multiple mappers for different media types, identify clearly which endpoint uses which mapper and which representation documentation should describe.

### When to Use Application Properties?

Several Jackson options can be set via `application.yml` or `application.properties`, such as property naming strategy and serialization inclusion. Whether using properties or `Jackson2ObjectMapperBuilderCustomizer`, the goal remains configuring the exact mapper used by HTTP converters. Avoid configuring the same option in multiple places with conflicting values.

## 3. Property Naming Strategies and Schema Field Names

Jackson supports naming strategies such as `LOWER_CAMEL_CASE`, `SNAKE_CASE`, `KEBAB_CASE`, and `UPPER_CAMEL_CASE`. With `SNAKE_CASE`, `productCode` typically becomes `product_code` in JSON.

Illustrative DTO:

```java
public record ProductResponse(
    Long id,
    String productCode,
    String displayName,
    BigDecimal sellingPrice
) {}
```

Actual payload with snake_case naming strategy:

```json
{
  "id": 101,
  "product_code": "P-001",
  "display_name": "Ballpoint pen",
  "selling_price": 12000
}
```

Corresponding OpenAPI schema must use exact JSON names:

```yaml
ProductResponse:
  type: object
  properties:
    id:
      type: integer
      format: int64
    product_code:
      type: string
    display_name:
      type: string
    selling_price:
      type: number
```

Springdoc can retrieve the naming strategy via Jackson introspection in supported configurations. Inspect the generated schema after changing the global naming strategy, especially if the application already has DTOs using `@JsonProperty` or mix-ins.

### Using `@JsonProperty` for Explicit Naming

`@JsonProperty` sets a property's JSON name. Explicit names normally take precedence over the global naming strategy:

```java
public record ProductResponse(
    @JsonProperty("product_code") String productCode,
    @JsonProperty("displayName") String displayName
) {}
```

Here, `productCode` is published as `product_code`, while `displayName` stays camelCase despite the mapper using snake_case. OpenAPI documentation must match the external JSON names clients actually send or receive, not Java component names.

### Using `@JsonAlias` for Legacy Input Names

`@JsonAlias` declares one or more alternative names accepted during deserialization. It does not change the property name when serializing:

```java
public record ProductUpdateRequest(
    @JsonProperty("product_code")
    @JsonAlias({"productCode", "code"})
    String productCode
) {}
```

In this case, the server accepts `product_code`, `productCode`, or `code`, while outputting the canonical name `product_code`. OpenAPI normally documents the canonical name published by the API; input aliases are for backward compatibility and should be explained in `description` if clients need to know.

Do not expose all aliases as separate independent properties in the schema, because they all map to a single Java value. When retiring legacy aliases, evaluate existing clients before changing deserialization behavior.

## 4. `@JsonInclude` and Differences Between Optional, Null, and Required

`@JsonInclude` controls when Jackson writes a property to JSON output. Common modes:

| Value | Serialization Behavior |
|---|---|
| `ALWAYS` | Always writes property per serializer config |
| `NON_NULL` | Omits property if value is `null` |
| `NON_EMPTY` | Omits empty values such as empty strings, empty collections, or null per serializer rules |
| `NON_DEFAULT` | Omits values considered default by Jackson rules |

Can be configured at the class level:

```java
@JsonInclude(JsonInclude.Include.NON_NULL)
public record ProductResponse(
    Long id,
    String name,
    String description,
    List<String> labels
) {}
```

If `description` is `null`, Jackson can omit the `description` key from the response. If `labels` is empty and `NON_EMPTY` is active, the `labels` key may also be omitted.

Distinguish this from OpenAPI concepts:

- **Required:** property must appear in the object. Represented in the schema's `required` list.
- **Optional:** property may be absent from the object.
- **Nullable:** property may appear with JSON value `null`. Exact syntax depends on OpenAPI version.
- **Omitted:** Jackson skips writing the property to JSON output when its value matches the `JsonInclude` condition.

A property missing from `required` does not automatically mean it accepts `null`; it simply is not mandatory to include. Conversely, a property can be marked nullable while still required as a key. In OpenAPI 3.0, `nullable: true` typically expresses null allowance; in OpenAPI 3.1, null can be represented inside `type` per JSON Schema.

Because `NON_NULL` affects response serialization, the schema should mark the property optional if the server can omit it from payloads. Do not infer nullability solely from `@JsonInclude`; examine Java types, validation, generated schemas, and response examples together.

## 5. Date-Time Formatting and the Java Time Module

Jackson requires a module supporting Java date-time types like `LocalDate`, `LocalDateTime`, `OffsetDateTime`, and `Instant`. Spring Boot usually auto-registers the Java Time module when its dependency is on the classpath. For API contracts, pick a clear representation and use ISO 8601 formatting where appropriate.

Example:

```java
public record OrderResponse(
    LocalDate orderDate,
    @JsonFormat(pattern = "yyyy-MM-dd'T'HH:mm:ssXXX")
    OffsetDateTime createdAt,
    Instant processedAt
) {}
```

The payload can look like:

```json
{
  "orderDate": "2026-11-20",
  "createdAt": "2026-11-20T14:30:00+07:00",
  "processedAt": "2026-11-20T07:30:00Z"
}
```

OpenAPI schemas typically describe `orderDate` as `string` with `format: date`, and timestamps as `string` with `format: date-time`. If using a custom pattern, add `description` or `example` so clients understand exact timezone and precision.

`LocalDateTime` carries no timezone information. If business logic requires a global point in time, consider `Instant` or `OffsetDateTime`; using `LocalDateTime` and implicitly assuming a timezone can cause clients to misinterpret data.

## 6. Enums and How Jackson Represents Values

Java enums can serialize as constant names, ordinals, or custom values. Jackson settings and annotations can make the wire representation differ from enum names in source code.

Example enum using public codes:

```java
public enum OrderStatus {
    NEW("new"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String getCode() {
        return code;
    }

    @JsonCreator
    public static OrderStatus fromCode(String value) {
        return Arrays.stream(values())
            .filter(status -> status.code.equalsIgnoreCase(value))
            .findFirst()
            .orElseThrow(() -> new IllegalArgumentException("Unknown status: " + value));
    }
}
```

JSON uses `"paid"` rather than the constant name `"PAID"`. If the OpenAPI schema instead publishes enum values `NEW`, `PAID`, `CANCELLED`, clients may send values rejected by the deserializer.

For enums with `@JsonValue`, `@JsonCreator`, or custom serializers, inspect the generated `enum` schema and examples. If springdoc does not infer the custom representation properly, document the property with `@Schema` or use a dedicated DTO/API enum with a simple, stable representation.

Avoid enabling integer ordinal serialization for enums in public APIs unless a clear compatibility reason exists. Enum ordering can shift when new constants are added, causing old numeric values to be misinterpreted.

## 7. Custom Serializers and Deserializers

Jackson lets you customize how a Java type is read or written via `@JsonSerialize` and `@JsonDeserialize`, or by registering a custom module. This is a major source of drift because a schema inferred from Java types may not reflect the serializer's actual representation.

Example currency type serialized as a string:

```java
public record Money(BigDecimal amount, String currency) {}

public class MoneySerializer extends JsonSerializer<Money> {
    @Override
    public void serialize(
        Money value,
        JsonGenerator generator,
        SerializerProvider provider
    ) throws IOException {
        generator.writeString(value.amount().toPlainString() + " " + value.currency());
    }
}
```

Attaching the serializer:

```java
public record InvoiceResponse(
    Long id,
    @JsonSerialize(using = MoneySerializer.class)
    Money total
) {}
```

Runtime JSON can be:

```json
{
  "id": 501,
  "total": "125000.00 VND"
}
```

If the schema is inferred as an object with `amount` and `currency`, the documentation mismatches the payload. In that case, describe `total` as a string with appropriate format/description/example via annotations or an OpenAPI customizer. For APIs requiring monetary arithmetic, numeric amounts paired with a separate currency field are usually easier for client generation and processing than formatted display strings.

Custom deserializers also need checking on the request side. If the server accepts a custom-formatted string and parses it into an object, the schema must describe the type the client sends. Avoid using a complex Java type when the wire format is primitive without adding matching metadata.

## 8. Polymorphism and Discriminators

A property can hold multiple subtypes. Jackson uses `@JsonTypeInfo` and `@JsonSubTypes` to select subtypes using a discriminator or other metadata.

Example:

```java
@JsonTypeInfo(
    use = JsonTypeInfo.Id.NAME,
    include = JsonTypeInfo.As.PROPERTY,
    property = "kind"
)
@JsonSubTypes({
    @JsonSubTypes.Type(value = CardPayment.class, name = "card"),
    @JsonSubTypes.Type(value = BankTransfer.class, name = "bank_transfer")
})
public sealed interface PaymentMethod
    permits CardPayment, BankTransfer {}

public record CardPayment(String lastFourDigits) implements PaymentMethod {}
public record BankTransfer(String bankCode, String accountNumber) implements PaymentMethod {}
```

JSON can take either form:

```json
{
  "kind": "card",
  "lastFourDigits": "4242"
}
```

```json
{
  "kind": "bank_transfer",
  "bankCode": "ABC",
  "accountNumber": "001234"
}
```

OpenAPI should describe the base schema using `oneOf` and discriminator `kind`, along with subtype schemas. Example:

```yaml
PaymentMethod:
  oneOf:
    - $ref: '#/components/schemas/CardPayment'
    - $ref: '#/components/schemas/BankTransfer'
  discriminator:
    propertyName: kind
    mapping:
      card: '#/components/schemas/CardPayment'
      bank_transfer: '#/components/schemas/BankTransfer'
```

Not every polymorphic Jackson setup automatically produces the expected `oneOf`/`discriminator` schema. Inspect `/v3/api-docs`; when needed, use `@Schema(oneOf = {...}, discriminatorProperty = "kind")` or a customizer to document the contract. All subtypes must genuinely be supported by the serializer/deserializer.

## 9. Property Visibility, Mix-Ins, and JsonView

Jackson can alter which properties are serialized or deserialized via `@JsonAutoDetect`, `@JsonIgnoreProperties`, mix-ins, and `@JsonView`. Account for these mechanisms when schemas are auto-generated.

### Property Visibility

`@JsonAutoDetect` controls whether Jackson sees fields, getters, setters, or creators. For example, broad field visibility can serialize private fields even if only public getters were exposed previously. If the schema relies on a different property set, documentation may miss fields or expose unintended ones.

### Mix-Ins

Jackson mix-ins let you attach annotations to a class without modifying the original class. This is helpful for third-party library types or uneditable entities. However, whether springdoc sees mix-ins depends on the `ObjectMapper`/model converter used by your version. After registering a mix-in, check both JSON output and the OpenAPI schema.

### JsonView

`@JsonView` selects property subsets per operation view. For instance, a detail response may include more fields than a list response. When controllers use different views, documentation must describe the matching schema for each operation; do not assume one shared schema always covers all views. Consider separate DTOs when views diverge substantially or client generators need distinct models.

## 10. Unknown Property Handling and `additionalProperties`

Jackson has an option controlling whether deserialization fails when JSON includes properties undeclared on the DTO. An application may ignore unknown fields or reject requests depending on `FAIL_ON_UNKNOWN_PROPERTIES` and class-level annotations.

The OpenAPI Schema Object can use `additionalProperties` to specify whether an object allows properties beyond those listed. If runtime rejects unknown fields while the schema defaults to allowing them, clients may send payloads the docs appear to accept only for the server to reject them. Conversely, if runtime ignores unknown fields while the schema sets `additionalProperties: false`, the contract is stricter than actual behavior.

Example schema allowing only listed properties:

```yaml
CreateProductRequest:
  type: object
  additionalProperties: false
  required: [name, price]
  properties:
    name:
      type: string
    price:
      type: number
```

If choosing to reject unknown fields, configure Jackson and test so runtime aligns with the schema. If choosing to ignore unknown fields for compatibility, document that policy clearly. Avoid toggling `FAIL_ON_UNKNOWN_PROPERTIES` solely to make a schema look stricter without evaluating existing clients.

## 11. Do Not Use a Different `ObjectMapper` from the HTTP Converter's Mapper

A common mistake is instantiating `new ObjectMapper()` in tests or business code while Spring MVC uses the Boot-configured mapper. The two mappers can differ in naming strategy, date-time modules, inclusion, enums, or custom serializers.

In Spring tests, inject the application's actual `ObjectMapper` bean:

```java
@SpringBootTest
class JacksonContractTest {

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void writesSnakeCaseAndOmitsNull() throws Exception {
        ProductResponse response = new ProductResponse(
            101L,
            "P-001",
            "Ballpoint pen",
            new BigDecimal("12000")
        );

        JsonNode json = objectMapper.readTree(
            objectMapper.writeValueAsBytes(response)
        );

        assertThat(json.has("product_code")).isTrue();
        assertThat(json.has("productCode")).isFalse();
    }
}
```

This test example assumes the DTO and snake_case configuration are already declared. To test actual HTTP responses, use MockMvc so requests flow through the real `HttpMessageConverter` rather than only calling `ObjectMapper` directly.

## 12. Checking OpenAPI and Runtime JSON Side by Side

After every Jackson configuration change, check both outputs.

**Runtime JSON:**

- Send sample requests and verify key names, value types, date-time formats, enums, and null behavior.
- Inspect JSON responses from endpoints, not just Java objects prior to serialization.
- Confirm custom serializers/deserializers run for actual media types.

**OpenAPI:**

- Fetch `/v3/api-docs` or `/v3/api-docs.yaml`.
- Verify property names and schema types.
- Check enums, formats, patterns, required flags, nullability, and examples.
- Check subtypes, discriminators, `oneOf`, and `additionalProperties` where used.
- Check `$ref` targets in request bodies and responses.

MockMvc example verifying response and documentation:

```java
mockMvc.perform(get("/api/products/101"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.product_code").value("P-001"))
    .andExpect(jsonPath("$.productCode").doesNotExist());

mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.ProductResponse.properties.product_code"
    ).exists())
    .andExpect(jsonPath(
        "$.components.schemas.ProductResponse.properties.productCode"
    ).doesNotExist());
```

Adjust JSONPath expressions to match component names and your application's documentation group settings. If the schema is right yet the HTTP payload is wrong, inspect the runtime converter/`ObjectMapper`. If the payload is right yet the schema is wrong, inspect model converters, Swagger annotations, and springdoc configuration.

## 13. Common Signs of Inconsistency

| Symptom | Possible Cause | Resolution |
|---|---|---|
| JSON uses snake_case while schema uses camelCase | Runtime naming strategy not reflected in schema | Check the mapper springdoc uses, explicit name annotations, and generated schema |
| `@JsonAlias` interpreted as multiple properties | Confusing deserialization aliases with output names | Publish the canonical name; document aliases in `description` if needed |
| Null field disappears yet schema marks it required | Inclusion and requiredness are out of sync | Check `@JsonInclude`, validation, and `required` lists |
| Runtime timestamp differs from schema format | `@JsonFormat` or Java Time module altered representation | Align format/example and verify real JSON |
| Runtime enum returns code while schema lists constant names | `@JsonValue` or custom serializer not reflected | Override enum schema or use a stable representation |
| Custom serializer returns string yet schema is object/number | Schema inferred from Java type | Use `@Schema` or `OpenApiCustomizer` to describe wire format |
| Polymorphic JSON has discriminator yet schema lacks `oneOf` | Model converter did not infer all subtypes | Declare `oneOf`/discriminator and test every subtype |
| Runtime rejects unknown fields while schema allows them | Jackson unknown-property policy differs from `additionalProperties` | Align runtime configuration and schema |
| Unit test serializes differently from HTTP response | Test uses a different `ObjectMapper` than HTTP converters | Inject Spring's mapper or test with MockMvc |

## 14. Safe Workflow for Changing `ObjectMapper`

When modifying the application's JSON configuration, follow this sequence:

1. Identify affected endpoints and DTOs, covering both requests and responses.
2. Record current JSON payloads and current OpenAPI schemas as a baseline.
3. Change one related group of settings, such as naming strategy, inclusion, or date/time formatting.
4. Check whether local annotations like `@JsonProperty`, `@JsonAlias`, `@JsonFormat`, `@JsonValue`, or custom serializers override global settings.
5. Use Spring's actual mapper/converter to serialize and deserialize representative payloads.
6. Fetch `/v3/api-docs` and compare properties, types, enums, formats, required lists, and examples.
7. Run HTTP tests covering valid requests, malformed requests, and responses.
8. Evaluate compatibility impact on client generators and existing API consumers.
9. Document a contract change whenever the wire format changes; do not treat it merely as internal refactoring.

If multiple endpoints have distinct JSON requirements, consider separate DTOs or separate converters with clearly documented contracts. A global `ObjectMapper` applies across the whole application and can alter many endpoints at once.

## 15. References

- [Spring Boot – Jackson](https://docs.spring.io/spring-boot/reference/features/json.html): configuring Jackson and JSON customizations in Spring Boot.
- [Jackson Databind](https://github.com/FasterXML/jackson-databind): `ObjectMapper`, serialization, deserialization, and modules.
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations): `@JsonProperty`, `@JsonAlias`, `@JsonInclude`, `@JsonFormat`, `@JsonView`, and related annotations.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): type, format, enum, required, nullable, discriminator, and additionalProperties.
- [Springdoc OpenAPI](https://springdoc.org/): Jackson metadata integration and OpenAPI schema generation from Spring Boot.
