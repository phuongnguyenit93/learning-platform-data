# Mapping Enums, Dates and Times, Currency, and Custom Value Types

Spring Data REST accepts and returns JSON through Spring MVC's HTTP message conversion mechanism, typically using Jackson to convert between JSON and Java objects. Simple types such as String or Boolean usually map directly; enums, dates and times, currencies, and value objects need a clear representation contract so client and server share the same semantics.

Mapping design should answer three questions: what shape does the JSON have, how does Java represent the value, and where are validation rules checked. Serializers/deserializers decide how conversion works; validation decides whether a value is accepted; persistence mapping decides how it is stored in the database. These are related responsibilities, not substitutes for one another.

## 1. Where Does Jackson Fit in the Spring Data REST Flow?

On the request side, Spring MVC selects an `HttpMessageConverter` based on media type and the endpoint's parameter types. For JSON, the converter typically uses Jackson to deserialize the request body into an entity or input object. Spring Data REST then continues with repository handling, validation, and lifecycle events.

On the response side, Spring Data REST builds the resource representation, including properties and hypermedia links. Jackson serializes the representation into JSON to send back to the client.

```text
Request JSON
    |
    v
HttpMessageConverter + Jackson
    |
    v
Java object / entity
    |
    v
Spring Data REST + repository
    |
    v
Resource representation + HAL links
    |
    v
Jackson + HttpMessageConverter
    |
    v
Response JSON
```

Jackson annotations, custom serializers, deserializers, and modules can adjust conversion in both directions. Actual configuration depends on the Spring Boot version, Spring Data REST, and the ObjectMapper used by the application. When customizing ObjectMapper, ensure the configuration applies to the converter serving Spring Data REST, not just a standalone ObjectMapper created in another service.

## 2. Mapping Enums

Enums usually represent a finite set of values, such as order status:

```java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
```

With standard Jackson configuration, an enum is represented by its constant name as a JSON string:

```json
{
  "status": "PAID"
}
```

When receiving JSON, Jackson converts the corresponding string into the enum constant. A value that does not match the enum can cause a deserialization error before the repository performs any operation.

Treat enum names as part of the API contract intentionally. Renaming a Java constant can cause older clients to send values that are no longer recognized. If internal names need to change while keeping the API stable, you can define a dedicated JSON value.

### Using @JsonValue and @JsonCreator

`@JsonValue` indicates the value used when serializing an enum. `@JsonCreator` specifies how to convert a JSON value back into the enum:

```java
public enum OrderStatus {
    PENDING("pending"),
    PAID("paid"),
    SHIPPED("shipped"),
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
    public static OrderStatus fromCode(String code) {
        for (OrderStatus status : values()) {
            if (status.code.equals(code)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Unknown order status: " + code
        );
    }
}
```

JSON now uses a stable code such as `"paid"`, even though the Java constant name is `PAID`. If you want to accept different letter casing, define an explicit normalization rule in the factory method; do not make clients guess.

Do not serialize enums as ordinals such as `0`, `1`, `2`. Constant ordering can change when adding or reordering enum values, causing clients to misinterpret data. If using JPA, `@Enumerated(EnumType.STRING)` is also generally safer than `ORDINAL` for persistence, though that is a database storage setting independent of JSON mapping.

## 3. Mapping Dates and Times

Java date/time types do not carry the same semantics. Choose the right type before deciding on the JSON format:

| Java type | Meaning | Common JSON |
|---|---|---|
| `LocalDate` | A calendar date, without time or time zone | `"2026-11-11"` |
| `LocalTime` | Time of day, without date or time zone | `"09:30:00"` |
| `LocalDateTime` | Local date and time, without offset/time zone | `"2026-11-11T09:30:00"` |
| `OffsetDateTime` | Date and time with a UTC offset | `"2026-11-11T09:30:00+07:00"` |
| `Instant` | An absolute point on the timeline | `"2026-11-11T02:30:00Z"` |
| `ZonedDateTime` | Date and time with a zone ID, e.g. `Asia/Ho_Chi_Minh` | Usually requires an agreed format/zone policy |

Use `LocalDate` for birth dates or effective dates when only a calendar date matters. Use `Instant` for event timestamps that must be compared consistently across systems. Use `OffsetDateTime` when the API must preserve the submitted offset. `LocalDateTime` lacks sufficient information to pinpoint a unique instant if client and server are in different time zones.

In modern Spring Boot applications, Jackson is typically configured to support Java Time via `JavaTimeModule`. If the application constructs its own ObjectMapper or uses custom configuration, verify that the module is registered.

### Using ISO-8601 as the Interchange Format

Example entity:

```java
@Entity
public class Appointment {

    private LocalDate appointmentDate;

    private Instant createdAt;

    private OffsetDateTime startsAt;

    // getters and setters
}
```

The corresponding JSON can be:

```json
{
  "appointmentDate": "2026-11-11",
  "createdAt": "2026-11-11T02:30:00Z",
  "startsAt": "2026-11-11T09:30:00+07:00"
}
```

ISO-8601 clearly expresses date, time, and offset components. For `Instant`, values are typically represented in UTC with a `Z` suffix. For `OffsetDateTime`, the offset is preserved in the string.

If a custom format is needed, you can use `@JsonFormat`:

```java
public class Person {

    @JsonFormat(shape = JsonFormat.Shape.STRING,
                pattern = "yyyy-MM-dd")
    private LocalDate birthDate;
}
```

The pattern must match the Java type and API contract. Do not use a date-and-time-only format without an offset for an event that needs an absolute point in time.

### Time Zones and Daylight Saving Time

A string `"2026-11-11T09:30:00"` does not state which time zone 09:30 is in. If the server interprets it using the machine's default time zone, the same payload can become different instants when deployed in different environments.

For appointments, you may need to store both the local time and zone ID to handle time zone rules. For timestamps of past events, `Instant` is usually more suitable. Clarify whether the server normalizes to UTC or preserves the original offset, and apply that policy consistently across the API, database, and clients.

## 4. Mapping Currency and Precision

Do not use `float` or `double` for monetary amounts requiring exact calculations. Binary floating-point types cannot represent many decimal values accurately. In Java, `BigDecimal` is more suitable for amounts.

A monetary value needs both an amount and a currency unit. Sending only `100.00` is insufficient if clients do not know whether it is VND, USD, or EUR.

A simple value object:

```java
public record Money(
    BigDecimal amount,
    String currency
) {}
```

JSON can represent this as:

```json
{
  "amount": 125000.00,
  "currency": "VND"
}
```

Use ISO 4217 currency codes, such as `VND`, `USD`, or `EUR`, instead of display symbols like `$` or `đ`. Symbols can be ambiguous or locale-dependent.

### Scale and Rounding

`BigDecimal` preserves decimal precision, but business logic still needs to define scale and rounding policies. For example:

```java
BigDecimal tax = amount
    .multiply(new BigDecimal("0.10"))
    .setScale(2, RoundingMode.HALF_UP);
```

Do not construct BigDecimal from a double literal like `new BigDecimal(0.1)`, because the double value already carries binary floating-point error. Use a decimal string or `BigDecimal.valueOf(...)` when appropriate for the input.

The valid number of decimal places depends on the currency and business rules. Do not assume every currency has two decimal places. For VND, systems typically use whole-dong units; other currencies have different fraction-digit rules. Define rounding in the domain/service layer and validate amounts at the request boundary.

A JSON number may be converted by some JavaScript clients into a Number type with precision limits. If amounts are very large or clients must preserve full decimal precision, the API can choose to represent amounts as decimal strings and document the contract clearly:

```json
{
  "amount": "125000.00",
  "currency": "VND"
}
```

Do not mix number and string representations for the same field across endpoints without a documented compatibility reason.

## 5. Custom Value Types

Domain models often include types wrapping a single value with distinct domain meaning, such as `EmailAddress`, `PhoneNumber`, `ProductCode`, or `Money`. Using value types helps the domain express intent and centralize validation.

Example:

```java
public record EmailAddress(String value) {

    public EmailAddress {
        if (value == null || !value.contains("@")) {
            throw new IllegalArgumentException(
                "Invalid email address"
            );
        }
    }
}
```

If you want JSON to represent it directly as a string instead of a nested object:

```json
{
  "email": "an@example.test"
}
```

You can use `@JsonValue` and `@JsonCreator`:

```java
public record EmailAddress(String value) {

    @JsonValue
    public String jsonValue() {
        return value;
    }

    @JsonCreator
    public static EmailAddress fromJson(String value) {
        return new EmailAddress(value);
    }
}
```

Jackson serializes the object as a JSON string and calls the factory method during deserialization. The constructor/factory can reject invalid data; the application should translate this error into an appropriate client response instead of exposing stack traces.

This approach works well for types with a simple JSON structure. For more complex types needing multiple fields or special formatting, custom serializers/deserializers are usually easier to control.

## 6. Writing Custom Serializers and Deserializers

When the JSON contract differs from Jackson's default representation of a Java type, you can write a serializer and deserializer.

For example, a custom `Money` type represented as an object with amount and currency. Serializer:

```java
public class MoneySerializer
        extends JsonSerializer<Money> {

    @Override
    public void serialize(
            Money money,
            JsonGenerator generator,
            SerializerProvider serializers)
            throws IOException {

        generator.writeStartObject();
        generator.writeNumberField(
            "amount",
            money.amount()
        );
        generator.writeStringField(
            "currency",
            money.currency()
        );
        generator.writeEndObject();
    }
}
```

Deserializer:

```java
public class MoneyDeserializer
        extends JsonDeserializer<Money> {

    @Override
    public Money deserialize(
            JsonParser parser,
            DeserializationContext context)
            throws IOException {

        JsonNode node = parser.getCodec()
            .readTree(parser);

        JsonNode amountNode = node.get("amount");
        JsonNode currencyNode = node.get("currency");

        if (amountNode == null || currencyNode == null) {
            throw JsonMappingException.from(
                parser,
                "Money requires amount and currency"
            );
        }

        BigDecimal amount = amountNode.decimalValue();
        String currency = currencyNode.asText();

        return new Money(amount, currency);
    }
}
```

You can attach them directly to the type:

```java
@JsonSerialize(using = MoneySerializer.class)
@JsonDeserialize(using = MoneyDeserializer.class)
public record Money(
    BigDecimal amount,
    String currency
) {}
```

Or register them via a Jackson module to separate configuration from domain classes. Example with Spring Boot:

```java
@Bean
Module moneyModule() {
    SimpleModule module = new SimpleModule("money-module");
    module.addSerializer(Money.class, new MoneySerializer());
    module.addDeserializer(Money.class, new MoneyDeserializer());
    return module;
}
```

Spring Boot typically auto-registers Jackson `Module` beans into the auto-configured ObjectMapper. If the application customizes ObjectMapper or Spring Data REST uses a dedicated converter, verify that the module is applied to the right converter. Avoid constructing new ObjectMapper instances inside individual controllers since their configuration may diverge from the REST API configuration.

Serializers/deserializers only convert representations. They do not themselves guarantee valid currency codes, non-negative amounts, or business-appropriate scale. Those constraints still need to be checked in value object constructors, Bean Validation, or domain services.

## 7. Distinguishing JSON Mapping from Persistence Mapping

A Java type can be represented differently in JSON and in the database:

| Layer | Question | Common Mechanism |
|---|---|---|
| JSON request/response | What shape do clients send and receive? | Jackson annotations, serializers, deserializers, modules |
| Domain model | Is the value valid and semantically meaningful? | Constructors, value objects, Bean Validation, domain logic |
| Database | Which column and format store the value? | JPA mapping, `AttributeConverter`, column definitions |
| HTTP | Which media types are accepted/returned? | `HttpMessageConverter`, Spring MVC content negotiation |

For example, `OrderStatus` can be persisted in the database with `@Enumerated(EnumType.STRING)` while simultaneously serialized to the `"paid"` code via `@JsonValue`. These two representations are independent: one serves persistence, the other serves the API contract.

Similarly, `Money` can be serialized as a JSON object while stored across two columns `amount` and `currency`. If a JPA `AttributeConverter` is used, that converter does not automatically alter Jackson's JSON representation.

Do not use Jackson serializers to solve database storage layout; likewise, do not expect a JPA converter to alter the request body sent by clients.

## 8. Mapping Errors and Validation

Errors typically occur at different stages:

| Situation | Stage | Handling Approach |
|---|---|---|
| Unrecognized enum code | Request deserialization | Publish valid values and handle unknown codes |
| Malformed date/time | Request deserialization | Standardize on ISO-8601 or `@JsonFormat` |
| Timestamp missing offset when an instant is needed | Contract/domain semantics | Use `Instant` or `OffsetDateTime` as appropriate |
| Amount is not a valid decimal | Deserialization/validation | Use `BigDecimal`, check scale and range |
| Invalid currency code | Domain validation | Check against supported currency list |
| Custom value object missing fields | Custom deserializer | Return an informative mapping error |
| Valid JSON violating business rules | Bean Validation/domain layer | Return validation errors before persisting |

Parse or deserialization errors typically happen before the repository lifecycle. Validation errors occur after the object is constructed but fails constraints. Database constraint errors may only surface on write. Distinguishing these stages helps clients understand whether to fix payload syntax, field values, or business state.

Do not include sensitive details or internal stack traces in responses. Return stable error codes, field names, and brief descriptions so clients can correct the data.

## 9. Testing Bidirectional Mapping

Every custom mapping should have serialization and deserialization tests. Example:

```java
@Test
void moneyRoundTripsAsJson() throws Exception {
    Money original = new Money(
        new BigDecimal("125000.00"),
        "VND"
    );

    String json = objectMapper.writeValueAsString(original);

    Money restored = objectMapper.readValue(
        json,
        Money.class
    );

    assertEquals(original, restored);
}
```

Additional cases to test:

- Valid enums, unknown enums, and letter-casing rules.
- `LocalDate`, `Instant`, and `OffsetDateTime` at boundary values.
- Timestamps with different offsets representing the same instant.
- Amounts with scale, high precision, and rounding.
- Unsupported currencies.
- Custom types with missing fields or invalid values.
- Actual Spring Data REST responses, not just a standalone ObjectMapper created in a unit test.

Testing at the web/repository layer confirms that the right ObjectMapper and HttpMessageConverter are being used by endpoints. This is especially important when the application has multiple converters or custom Jackson configurations.

## 10. JSON Contract Design Checklist

1. Choose a stable JSON representation for enums; prefer meaningful string codes over ordinals.
2. Use Java Time types matching semantics: `LocalDate` for calendar dates, `Instant` for absolute instants, `OffsetDateTime` when offsets must be preserved.
3. Agree on time zones and formats, preferring ISO-8601 for date/time exchange.
4. Use `BigDecimal` for amounts and include the currency code alongside the amount.
5. Clearly define precision, scale, and rounding policies in the domain.
6. Use value objects for values with distinct domain meaning; pick `@JsonCreator`/`@JsonValue` or custom serializers/deserializers based on complexity.
7. Register Jackson modules on the right ObjectMapper serving Spring Data REST.
8. Separate JSON mapping from JPA persistence mapping and business validation.
9. Test round-trips and real requests/responses through endpoints.

When enums, dates and times, currencies, and custom value types have clear JSON contracts, clients and Spring Data REST can exchange data consistently. Jackson handles representation conversion, the domain model protects value meaning and validity, and JPA handles storage. Properly separating these three layers enables controlled API format changes without mixing business logic with serialization details.
