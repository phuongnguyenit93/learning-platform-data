# @JsonValue, @JsonFormat, and Representing Enums or Date-Times

Jackson converts Java data into JSON when Spring Boot returns a response and converts JSON into Java objects when receiving a request. For enums and date-time values, the wire representation can differ from how Java stores them internally. An enum might be sent as its constant name or as a business code; a date might be an ISO-8601 string, a custom-formatted string, or a timestamp. Without explicit control, a client may send the right JSON type yet the wrong value expected by the server.

With springdoc-openapi, schemas are generated from Java types, Jackson metadata, and the OpenAPI annotations supported by the library version. Therefore, you need to understand three layers together: Java values, actual JSON, and the published OpenAPI schema. Jackson determines the JSON data; Springdoc describes the contract so clients know what that data means.

## 1. How Does Jackson Determine JSON Shape?

When a controller returns an object, Spring MVC uses an HttpMessageConverter to write the response. For JSON, the converter typically uses a Jackson ObjectMapper. When receiving a request with @RequestBody, the converter reads JSON and maps it to a Java type.

Example:

```java
public record ProductResponse(
    Long id,
    String name,
    ProductStatus status
) {
}
```

If ProductStatus has no special configuration, Jackson normally represents the enum by its constant name:

```json
{
  "id": 42,
  "name": "Mechanical keyboard",
  "status": "AVAILABLE"
}
```

Java enum names can be an implementation detail. If AVAILABLE is renamed to IN_STOCK, clients relying on the old value may break. Public APIs usually need stable wire values designed independently of constant names in source code.

Similarly, a Java property of type LocalDate or OffsetDateTime is typically represented as a date-time string. The exact format depends on the Java Time module, ObjectMapper configuration, and annotations on the property.

## 2. Using @JsonValue to Choose the Representative JSON Value

@JsonValue marks a method or field whose return value is used as the JSON representation of the object. For enums, this is useful when the API needs to send a business code instead of the Java constant name.

Example:

```java
import com.fasterxml.jackson.annotation.JsonValue;

public enum ProductStatus {
    AVAILABLE("available"),
    OUT_OF_STOCK("out-of-stock"),
    DISCONTINUED("discontinued");

    private final String value;

    ProductStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }
}
```

When serialized, the enum value is sent as a string:

```json
"out-of-stock"
```

Instead of:

```json
"OUT_OF_STOCK"
```

The main benefit is decoupling Java constant names from API contract values. You can rename constants or refactor packages without necessarily changing the JSON values clients rely on.

### 2.1. @JsonValue on Enums and Deserialization

For enums, Jackson can use the @JsonValue value to look up the constant when reading JSON, provided the representative values are unique. For example, the string "out-of-stock" can map back to ProductStatus.OUT_OF_STOCK.

Ensure every @JsonValue value is unique. If two constants both return "active", Jackson lacks a clear reverse mapping and the result may be unexpected.

When explicit control over aliases, error handling, or parsing rules is needed, declare @JsonCreator:

```java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;

public enum OrderStatus {
    PENDING_PAYMENT("pending-payment"),
    PAID("paid"),
    CANCELLED("cancelled");

    private final String value;

    OrderStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    @JsonCreator
    public static OrderStatus fromValue(String value) {
        for (OrderStatus status : values()) {
            if (status.value.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Unsupported order status: " + value
        );
    }
}
```

Here @JsonCreator defines how to convert an input string into the enum. In a real API, invalid value errors should be translated into a consistent validation response, such as 400 Bad Request, through the application's exception handling mechanism.

### 2.2. @JsonValue Is Not Only for Enums

This annotation can also be used on value objects when the JSON should be a simple scalar:

```java
public record CurrencyCode(String value) {
    @JsonValue
    public String asJson() {
        return value;
    }
}
```

Then CurrencyCode("VND") can be serialized as the string "VND" instead of the object {"value":"VND"}. If you need to read a JSON string back into the value object, use a constructor or factory method annotated with @JsonCreator.

Use a scalar representation only when it fits the semantics of the data. If an object has multiple properties that need to be exposed independently, keeping the object structure is usually clearer.

## 3. @JsonFormat with Enums

@JsonFormat can alter how Jackson represents an enum. For standard string form, you can declare:

```java
@JsonFormat(shape = JsonFormat.Shape.STRING)
public enum PaymentMethod {
    CARD,
    BANK_TRANSFER,
    CASH
}
```

Shape.STRING represents the enum as a string. This is also Jackson's common default for enums. This annotation does not automatically turn CARD into "card" or "bank-transfer"; to use custom values, consider @JsonValue or @JsonProperty on individual constants as needed.

Some global Jackson settings also affect enums, such as:

- WRITE_ENUMS_USING_TO_STRING: uses toString() output when serializing enums.
- READ_ENUMS_USING_TO_STRING: uses toString() when deserializing enums.
- READ_UNKNOWN_ENUM_VALUES_AS_NULL: treats unrecognized enum values as null.
- READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE: uses the constant annotated with @JsonEnumDefaultValue if configured and supported.

These are ObjectMapper-level settings that affect many DTOs simultaneously. Enable them only when the convention suits the entire API; if different enums have different contracts, configuring at the enum or property level is easier to control.

### 3.1. Representing an Enum as an Object

Jackson supports @JsonFormat(shape = JsonFormat.Shape.OBJECT) for enums in some usages to serialize the enum's bean properties as a JSON object. For example, an enum with a code and display label can be returned as an object rather than a string.

However, representing an enum as an object changes the shape of the contract:

```json
{
  "code": "pending-payment",
  "label": "Pending payment"
}
```

Test both serialization and deserialization separately with your Jackson version. Reading a JSON object back into an enum does not always infer the identifying key automatically; a @JsonCreator or custom deserializer may be required. For public requests/responses, if clients only need a status code, a scalar string is usually simpler and more stable.

## 4. Documenting Enums in OpenAPI and Springdoc

In OpenAPI, string enums are typically described using a string-type schema with an enum list. Example:

```yaml
ProductStatus:
  type: string
  enum:
    - available
    - out-of-stock
    - discontinued
  description: Commercial status of the product.
```

Springdoc can infer enum schemas from Java types and metadata recognized by swagger-core. However, how the library infers enum values using @JsonValue, @JsonProperty, toString(), or custom serializers can depend on version and configuration. Never assume the schema always matches actual JSON.

When you need to explicitly publish the wire values, you can add @Schema on the DTO property:

```java
public record ProductResponse(
    Long id,

    @Schema(
        type = "string",
        allowableValues = {
            "available",
            "out-of-stock",
            "discontinued"
        },
        example = "available",
        description = "Product status code in the API."
    )
    ProductStatus status
) {
}
```

After configuring, check both ends:

1. Call the actual endpoint to see what JSON values Jackson returns.
2. Open /v3/api-docs to inspect components.schemas and the enum values Springdoc publishes.

If the schema still lists AVAILABLE, OUT_OF_STOCK while the JSON returns available, out-of-stock, the documentation mismatches the contract. Adjust the metadata or customizer appropriately for your library version and test the output after changing it.

## 5. Date and Time in Java: Choosing a Type by Temporal Meaning

Before formatting dates and times, choose the Java type that matches the meaning of the data:

| Java type | Meaning | Has timezone/offset? | Examples |
|---|---|---:|---|
| LocalDate | A calendar date | No | Birth date, expected delivery date |
| LocalTime | Time of day | No | Opening hours |
| LocalDateTime | Local date and time | No | Appointment time without timezone attached |
| OffsetDateTime | Date and time with UTC offset | Has offset | Timestamp sent by client with +07:00 |
| ZonedDateTime | Date and time with time zone | Has zone | Schedule in Asia/Ho_Chi_Minh |
| Instant | A point on the UTC timeline | UTC | Record creation timestamp |

Do not use LocalDateTime to represent a global point in time if the system needs to know the exact instant on the UTC timeline. LocalDateTime carries no offset or timezone; the same value can correspond to different moments in different regions.

For business timestamps such as createdAt, paidAt, expiresAt, consider Instant or OffsetDateTime. For calendar dates such as birthDate, deliveryDate, LocalDate is usually more appropriate.

## 6. Java Time Module and Default Formatting

For Jackson to read and write types in java.time, the application needs the Java Time module (jackson-datatype-jsr310) registered with the ObjectMapper. Spring Boot normally auto-configures modules on the classpath via Jackson auto-configuration. If using a manually created ObjectMapper, verify that the module is registered.

Example creating a standalone mapper:

```java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .build();
```

In a Spring Boot application, avoid creating a separate ObjectMapper for a controller just to format one field because doing so can bypass global modules and settings. Prefer configuring the Spring-managed mapper or using a property-level annotation when only a local change is needed.

Java Time types are typically represented as ISO-8601 strings when the application configures Jackson to write dates as text. Spring Boot typically disables writing dates as timestamps for JSON in its default web setup. You can set it explicitly:

```yaml
spring:
  jackson:
    serialization:
      write-dates-as-timestamps: false
```

Actual behavior still depends on the Spring Boot/Jackson version and application configuration. Verify the returned JSON rather than relying entirely on defaults.

## 7. Using @JsonFormat to Format Dates and Times

@JsonFormat lets you specify shape, pattern, locale, and timezone depending on the data type. For Java Time, patterns are interpreted by the Java Time module's formatter.

### 7.1. LocalDate

LocalDate represents a calendar date, containing no time or timezone:

```java
public record CustomerResponse(
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd"
    )
    LocalDate birthDate
) {
}
```

JSON:

```json
{
  "birthDate": "1995-08-21"
}
```

With LocalDate, there is no need to attach a timezone because the type itself does not represent an instant requiring timezone conversion.

### 7.2. LocalDateTime

LocalDateTime represents a local date and time without an offset:

```java
public record AppointmentRequest(
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd'T'HH:mm:ss"
    )
    LocalDateTime appointmentAt
) {
}
```

JSON:

```json
{
  "appointmentAt": "2026-11-20T14:30:00"
}
```

The value above does not indicate which timezone 14:30 belongs to. If the system needs appointments tied to a location, store or pass the timezone/offset under an explicit contract, or use ZonedDateTime/OffsetDateTime as appropriate.

### 7.3. OffsetDateTime

OffsetDateTime contains a UTC offset:

```java
public record PaymentResponse(
    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd'T'HH:mm:ssXXX"
    )
    OffsetDateTime paidAt
) {
}
```

JSON:

```json
{
  "paidAt": "2026-11-20T14:30:00+07:00"
}
```

The symbol XXX represents an offset such as +07:00. If the client needs to preserve the offset it sent, use an offset-aware type instead of LocalDateTime.

### 7.4. Instant

Instant represents a point on the UTC timeline. ISO-8601 form typically has a trailing Z:

```java
public record AuditResponse(
    Instant createdAt
) {
}
```

Example JSON:

```json
{
  "createdAt": "2026-11-20T07:30:00Z"
}
```

If another format is required, you can apply @JsonFormat after verifying how Jackson handles timezones and Java Time types in your project version. For timestamps used in system integrations, UTC ISO-8601 is generally easy to exchange and avoids ambiguity.

## 8. Pattern, Locale, and Timezone Must Be Used Correctly

The attributes of @JsonFormat serve distinct purposes:

| Attribute | Purpose | Notes |
|---|---|---|
| shape | Selects JSON shape such as STRING or NUMBER | Not all Java types support every shape |
| pattern | Date-time string pattern | Must match the Java type and input data |
| locale | Language/region rules for formatting | Useful for localized month or day names |
| timezone | Timezone used when converting instant-based types | Do not add timezone to LocalDate or LocalDateTime |
| lenient | Adjusts leniency in certain converters | Behavior depends on type and version |

Pattern example:

```java
@JsonFormat(
    shape = JsonFormat.Shape.STRING,
    pattern = "dd/MM/uuuu",
    locale = "vi_VN"
)
LocalDate invoiceDate;
```

The JSON looks like "20/11/2026". This format is readable for some audiences, though international clients are generally more accustomed to ISO-8601. If using a custom pattern, document it clearly in OpenAPI and in request/response examples.

Notes on pattern symbols:

- uuuu is typically suitable for formatting years in Java Time.
- MM is month; mm is minute.
- HH is 24-hour clock; hh is 12-hour clock.
- XXX represents an offset such as +07:00.
- Single quotes escape literal characters, such as the letter T in ISO-8601.

Do not confuse Java Time patterns with every convention of SimpleDateFormat. Although many symbols look similar, several details differ in meaning.

## 9. @JsonFormat Is Not the Same as @DateTimeFormat

Spring provides two annotations typically used in different places:

| Annotation | Primary Scope | Example |
|---|---|---|
| @JsonFormat | Jackson serialization/deserialization of JSON bodies or responses | LocalDate field in a DTO |
| @DateTimeFormat | Spring conversion for query parameters, path variables, form fields | ?from=2026-11-01 |

Query parameter example:

```java
@GetMapping("/reports")
public ReportResponse report(
    @RequestParam
    @DateTimeFormat(iso = DateTimeFormat.ISO.DATE)
    LocalDate from
) {
    return reportService.create(from);
}
```

JSON DTO example:

```java
public record ReportRequest(
    @JsonFormat(pattern = "uuuu-MM-dd")
    LocalDate from
) {
}
```

The two annotations do not replace each other. Placing @JsonFormat on a query parameter is not the standard way to control Spring MVC query parameter conversion.

## 10. How Does Springdoc Document Enums and Date-Times?

Springdoc uses metadata from Java types, Jackson, and OpenAPI annotations to build schemas. For standard date-time types, schemas usually look like:

```yaml
birthDate:
  type: string
  format: date

createdAt:
  type: string
  format: date-time
```

For enums, schemas are usually strings with an enum list:

```yaml
status:
  type: string
  enum:
    - available
    - out-of-stock
    - discontinued
```

If @JsonFormat defines a custom pattern, the schema may still only show type string or format date/date-time; not every Jackson pattern translates into a machine-validated OpenAPI constraint. Add @Schema(example = ...) and a description so readers know the exact format.

Example:

```java
public record AppointmentResponse(
    @Schema(
        type = "string",
        format = "date-time",
        example = "2026-11-20T14:30:00"
    )
    @JsonFormat(pattern = "uuuu-MM-dd'T'HH:mm:ss")
    LocalDateTime appointmentAt
) {
}
```

If a pattern has concrete restrictions, you can use @Schema(pattern = "...") when the schema needs to publish the corresponding regex and that regex accurately describes the JSON data. Do not copy a Jackson date pattern mechanically into OpenAPI, because the two pattern syntaxes have different rules and purposes.

## 11. Complete Example: Business-Code Enum and Date-Time in a DTO

The following example uses stable status codes and an offset-aware timestamp:

```java
public enum ShipmentStatus {
    CREATED("created"),
    IN_TRANSIT("in-transit"),
    DELIVERED("delivered");

    private final String value;

    ShipmentStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String getValue() {
        return value;
    }

    @JsonCreator
    public static ShipmentStatus fromValue(String value) {
        for (ShipmentStatus status : values()) {
            if (status.value.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException("Unknown shipment status");
    }
}

public record ShipmentResponse(
    Long shipmentId,

    @Schema(
        type = "string",
        allowableValues = {"created", "in-transit", "delivered"},
        example = "in-transit"
    )
    ShipmentStatus status,

    @JsonFormat(
        shape = JsonFormat.Shape.STRING,
        pattern = "uuuu-MM-dd'T'HH:mm:ssXXX"
    )
    OffsetDateTime updatedAt
) {
}
```

The JSON response can be:

```json
{
  "shipmentId": 701,
  "status": "in-transit",
  "updatedAt": "2026-11-20T14:30:00+07:00"
}
```

The corresponding OpenAPI schema should show status as a string with the three wire values and updatedAt as an offset date-time string. Illustrative example:

```yaml
ShipmentResponse:
  type: object
  properties:
    shipmentId:
      type: integer
      format: int64
    status:
      type: string
      enum:
        - created
        - in-transit
        - delivered
    updatedAt:
      type: string
      format: date-time
      example: "2026-11-20T14:30:00+07:00"
```

Compare the actual JSON with the schema generated by springdoc. If Jackson and OpenAPI disagree on enum values or date-time formats, client generators may produce incorrect types or validation.

## 12. Global Jackson Configuration vs. Local Customization

Jackson can be configured application-wide or for a single property:

| Configuration Method | Scope | When to Use |
|---|---|---|
| spring.jackson.* | Global features supported by Spring Boot | Application-wide conventions |
| Jackson2ObjectMapperBuilderCustomizer | Customizing the Spring Boot-managed mapper | Registering modules or changing global serializers/deserializers |
| @JsonValue, @JsonFormat | Specific enum, class, or property | Contract specific to one data type |
| @JsonSerialize, @JsonDeserialize | Custom serializer/deserializer | Complex conversion rules |

Example customizing the Spring Boot-managed mapper:

```java
@Configuration
public class JacksonConfiguration {

    @Bean
    Jackson2ObjectMapperBuilderCustomizer jacksonCustomizer() {
        return builder -> builder.featuresToDisable(
            SerializationFeature.WRITE_DATES_AS_TIMESTAMPS
        );
    }
}
```

Avoid creating a brand-new ObjectMapper bean just to change one date-time format, because doing so can accidentally drop the Java Time module, parameter-names module, naming strategy, or other application customizers. Prefer customizers or property-level annotations.

## 13. Common Pitfalls

| Mistake | Consequence | Resolution |
|---|---|---|
| Renaming Java enum constants and letting them become JSON values | Clients break from internal refactoring | Use stable wire codes with @JsonValue or explicit mapping |
| Two enum constants share the same @JsonValue | Deserialization becomes ambiguous | Ensure representative values are unique |
| Using @Schema alone to change JSON enum output | Documentation changes while Jackson still serializes using old rules | Configure Jackson and OpenAPI in sync |
| Using @JsonValue and assuming the schema is always accurate | Enum values in OpenAPI may differ from runtime JSON | Inspect /v3/api-docs and supplement metadata |
| Using LocalDateTime for a global point in time | Missing offset to identify the instant | Use Instant or OffsetDateTime |
| Setting timezone on LocalDate | Gives the impression a calendar date undergoes timezone conversion | Use LocalDate without a timezone |
| Using @DateTimeFormat on a JSON body | Jackson does not apply the expected format | Use @JsonFormat for JSON |
| Using mm instead of MM in a pattern | Minutes are used instead of months | Verify pattern symbols |
| Declaring a custom pattern without an example | Clients do not know what string to send | Add @Schema(example = ...) and a description |
| Creating a standalone ObjectMapper without JavaTimeModule | Cannot read/write Java Time types or loses other configuration | Use the Spring-managed mapper and verify modules |

## 14. Jackson and OpenAPI Verification Workflow

When adding or changing enums/date-times in a DTO:

1. Choose the Java type matching the data semantics: calendar date, local time, or offset-aware instant.
2. Define the JSON values clients will send and receive.
3. Use @JsonValue, @JsonCreator, or @JsonFormat when custom rules are needed.
4. Add @Schema to document enum values, format, pattern, and examples if necessary.
5. Verify serialization by calling the endpoint or using ObjectMapper.
6. Verify deserialization with both valid and invalid request payloads.
7. Open /v3/api-docs to confirm the schema matches actual JSON.
8. Try the request in Swagger UI and check the displayed examples.

You can write a unit test for the enum:

```java
@Test
void shouldSerializeAndDeserializeOrderStatus() throws Exception {
    ObjectMapper mapper = objectMapper;

    String json = mapper.writeValueAsString(OrderStatus.PENDING_PAYMENT);
    assertThat(json).isEqualTo("\"pending-payment\"");

    OrderStatus value = mapper.readValue(
        "\"pending-payment\"",
        OrderStatus.class
    );
    assertThat(value).isEqualTo(OrderStatus.PENDING_PAYMENT);
}
```

And a test for date-time:

```java
@Test
void shouldUseExpectedOffsetDateTimePattern() throws Exception {
    var response = new PaymentResponse(
        OffsetDateTime.parse("2026-11-20T14:30:00+07:00")
    );

    String json = objectMapper.writeValueAsString(response);

    assertThat(json)
        .contains("2026-11-20T14:30:00+07:00");
}
```

These test examples assume objectMapper is injected by Spring or has the same modules and settings registered as the real environment. If a test constructs its own mapper that differs from the application's mapper, results may not reflect actual HTTP behavior.

## 15. Key Takeaways

- Jackson determines the actual JSON; Springdoc builds the OpenAPI schema from Java types and recognized metadata.
- @JsonValue chooses the representative JSON value, especially useful for enums with stable business codes.
- For enums, @JsonValue values must be unique; use @JsonCreator when you want explicit control over JSON parsing.
- @JsonFormat(shape = STRING) keeps enums as strings; it does not automatically turn constant names into business codes.
- Choose Java Time types by semantics: LocalDate for calendar dates, LocalDateTime for local times, Instant or OffsetDateTime for points in time.
- @JsonFormat controls JSON; @DateTimeFormat primarily controls Spring conversion for query/path/form values.
- OpenAPI typically uses string with format date or date-time; enums use type string and enum.
- Schemas must match actual JSON, especially when using custom enum values or date-time patterns.
- Verify serialization, deserialization, and /v3/api-docs after making changes.

When designing enum and date-time representations, treat JSON values as part of the API contract. Use @JsonValue to decouple public codes from internal enum names, pick Java Time types matching temporal semantics, and use @JsonFormat when custom formatting is required. Finally, verify that Jackson and Springdoc publish the exact same representation so clients can integrate reliably.
