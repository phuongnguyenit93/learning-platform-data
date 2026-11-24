# Formatting Dates/Times, Time Zones, Numbers, and Enum Values

## Objectives

After this lesson, you will be able to:

- Design wire representations for instants, calendar dates, local times, and time-zone-aware schedules.
- Distinguish Instant, OffsetDateTime, ZonedDateTime, LocalDateTime, Duration, and Period.
- Specify precision, scale, units, and rounding rules for numbers in messages.
- Avoid precision loss with long, BigInteger, BigDecimal, and JavaScript consumers.
- Design stable enum codes, handle new values, and maintain compatibility across service versions.
- Configure Jackson for Spring Messaging and RSocket.
- Write contract tests to catch serialization changes before release.

This lesson belongs to **Spring Framework - messaging**, under the **Message Contracts** branch. A message is a contract between producer and consumer. Internal Java types do not automatically become a stable wire format: the two sides may use different languages, library versions, locales, and processing rules.

## 1. Wire Format Is Part of the Contract

When an object is sent over messaging, an encoder turns the data into bytes using a format such as JSON or CBOR. The consumer uses a decoder to turn bytes into its own objects.

The same data can be interpreted differently if the contract is not explicit:

- Is 2026-11-07T09:30:00 UTC or local time?
- Is 1,234.50 one thousand two hundred thirty-four point five zero or one point two three four?
- Can 9007199254740993 be preserved intact by JavaScript when parsed into a Number?
- Which enum is 2 if producer and consumer declare enum constants in different orders?
- Does a missing field mean keep the existing value, apply a default, or clear the value?

A message contract should specify:

1. Field names and wire data types.
2. Units of measurement, precision, scale, and rounding rules.
3. Time semantics, time zone, and format.
4. Stable enum codes along with an unknown-value handling policy.
5. Rules for required fields, null, missing fields, and defaults.
6. Versioning and producer/consumer compatibility policies.

Do not treat two services sharing the same Java DTO as proof that the contract is stable. DTOs can change across releases; already-published messages may still sit in a broker or be processed by older consumers.

## 2. Choosing Date/Time Types by Business Meaning

The Java Time API has multiple types because a clock date and time do not always represent an absolute instant on the timeline.

| Type | Information Carried | Appropriate Use Case |
|---|---|---|
| Instant | Point on the UTC timeline | When an event occurred |
| OffsetDateTime | Date and time with UTC offset | When the source-provided offset must be preserved |
| ZonedDateTime | Date and time with ZoneId and region rules | Appointments or schedules tied to a geographic region |
| LocalDateTime | Date and time without zone/offset | Local wall-clock time in a known context |
| LocalDate | Calendar date | Date of birth, effective date |
| LocalTime | Time of day | Opening hours, scheduled recurring task time |
| Duration | Time span in seconds/nanoseconds | Timeouts, elapsed duration |
| Period | Time span in calendar years/months/days | Calendar cycles such as one month |

### 2.1. Past Events: Prefer Instant

An event such as a completed payment, created order, or published message needs a point in time independent of server time zones. Instant is the right choice.

JSON example:

~~~json
{
  "eventId": "evt-901",
  "occurredAt": "2026-11-07T14:17:00Z"
}
~~~

Z denotes UTC. A consumer in another time zone can convert the Instant to local time for display without altering the underlying point in time.

Do not send LocalDateTime for an occurredAt field if the consumer has no way to determine the time zone. A string like 2026-11-07T21:17:00 does not state whether it is Vietnam time or UTC.

### 2.2. Future Appointments: Keep Local Time and ZoneId

An appointment at 09:30 in a city usually has meaning relative to local wall-clock time. Converting it solely to the current offset can lose time-zone transition rules when the appointment lies in the future.

You can send:

~~~json
{
  "appointmentId": "apt-42",
  "localDateTime": "2026-12-15T09:30:00",
  "zoneId": "Asia/Ho_Chi_Minh"
}
~~~

The consumer can build a ZonedDateTime from LocalDateTime and ZoneId. If business logic needs to pinpoint an exact instant, resolve the appointment and store the corresponding Instant as well.

### 2.3. Offset Is Not a ZoneId

+07:00 is a fixed offset at the considered moment. Asia/Ho_Chi_Minh is a ZoneId in the IANA time-zone database. A ZoneId can hold history and regional offset-change rules.

If you only need to know when an event occurred, Instant is usually enough. If you need to know which time zone a user selected for an appointment, store ZoneId separately. You cannot recover a ZoneId from a bare offset alone.

### 2.4. DST and Ambiguous Local Times

In regions with Daylight Saving Time (DST), clocks can jump forward or fall back across a time range:

- **Gap:** certain local times do not exist when clocks spring forward.
- **Overlap:** certain local times occur twice when clocks fall back.

For future appointments, the contract must specify how to handle both cases. You may reject invalid times and ask the user to choose again, or shift to the next valid time. For overlaps, specify whether to choose the earlier or later offset.

Do not automatically rely on the JVM's default time zone to resolve gaps/overlaps. Producer and consumer must apply the same business policy.

### 2.5. Duration and Period Are Not Interchangeable

Duration.ofDays(1) is a 24-hour span. Period.ofDays(1) is one calendar day. When adding one calendar day to a ZonedDateTime across a DST transition, the actual elapsed time may not be 24 hours.

Similarly, "one month" is a calendar interval whose length varies by month, not a fixed number of seconds. The contract must distinguish technical timeouts from business calendar cycles.

## 3. Choosing Wire Formats for Date/Time

JSON does not define a dedicated date/time type. Contracts typically use ISO-8601 strings or epoch numbers.

### 3.1. ISO-8601 Strings

For event timestamps, a UTC string is readable and has an explicit offset:

~~~json
{
  "occurredAt": "2026-11-07T14:17:00Z"
}
~~~

If the contract needs to preserve the source offset, you can send an OffsetDateTime like 2026-11-07T21:17:00+07:00. If it needs to preserve the geographic region, also send a ZoneId such as Asia/Ho_Chi_Minh.

Specify precision. Java Instant can hold nanoseconds; another consumer might retain only milliseconds. If the producer sends 9 fractional digits and the consumer truncates to 3 digits, the data has changed. The contract must decide maximum precision and how to truncate/round.

### 3.2. Epoch Numbers

An epoch value is elapsed time since 1970-01-01T00:00:00Z. The most common forms are epoch seconds or epoch milliseconds.

Field names should state the unit clearly:

~~~json
{
  "createdAtEpochMillis": 1794061020000
}
~~~

Do not use ambiguous names like timestamp if the schema does not clarify seconds vs. milliseconds. Instant.toEpochMilli() retains only millisecond precision. If higher precision is needed, use an ISO-8601 string or an explicit numeric convention.

### 3.3. Jackson and Java Time

Jackson requires the JSR-310 module to handle java.time types. A common configuration to write dates/times as strings instead of numeric/array timestamps:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Imports:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
~~~

This configuration does not turn LocalDateTime into UTC. LocalDateTime still carries no time zone. If the contract requires an instant, use Instant or a type with an appropriate offset/zone.

Do not rely on the JVM's default time zone to parse offset-less strings. Explicitly specify format and semantics in the schema.

## 4. Locale Is Only for Display

Locale changes how humans read numbers, dates, and enum names. Machine-to-machine wire formats must be locale-independent.

For example, an amount can be displayed differently:

| Locale | Display String |
|---|---|
| en-US | 1,234.50 |
| de-DE | 1.234,50 |
| vi-VN | 1.234,50 |

JSON numbers use a period as the decimal separator and have no thousands separators:

~~~json
{
  "quantity": 1234.5
}
~~~

Do not send 1.234,50 as a number unless there is an explicit locale parsing rule. Nor should translated month names or localized enum labels be used as machine codes. Apply locale formatting only in the presentation layer.

## 5. Integers and Precision Across Languages

A Java long can hold 64-bit integers. However, consumers do not necessarily have an equivalent type.

JavaScript Number uses IEEE-754 binary64 and represents every integer accurately only within the safe range:

\[
-(2^{53}-1) \le n \le 2^{53}-1
\]

An ID larger than this limit can be rounded if parsed as a Number. Because IDs are identifiers, they should usually be sent as strings:

~~~json
{
  "accountId": "9007199254740993"
}
~~~

If a field requires arithmetic, the schema must specify its type and range. JavaScript consumers can use BigInt or an appropriate library; they should not silently convert it to Number.

Numeric fields with units should also state the unit in their name or schema, such as durationMillis, sizeBytes, or amountMinor. Do not send a unitless number and leave each service to guess.

## 6. Decimals and Monetary Values

### 6.1. Why Not Use double for Money?

double represents binary floating-point numbers. A decimal value like 0.1 has no finite binary representation, so arithmetic can introduce rounding errors:

~~~java
System.out.println(0.1 + 0.2);
~~~

Output:

~~~text
0.30000000000000004
~~~

For money or quantities requiring exact decimal precision, use BigDecimal. Construct BigDecimal from a string to preserve the exact decimal value:

~~~java
BigDecimal amount = new BigDecimal("1234.50");
BigDecimal taxRate = new BigDecimal("0.08");
BigDecimal tax = amount.multiply(taxRate);
~~~

Avoid new BigDecimal(0.1), because the double value is already an approximation before being passed to BigDecimal.

### 6.2. Decimal String or Integer Minor Units?

A contract may choose a decimal string:

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

String rules must be explicit: use a decimal period, no grouping separators, no currency symbol, scale matching business rules, and no locale notation.

Or use integer minor units:

~~~json
{
  "amountMinor": 123450,
  "currency": "USD"
}
~~~

This avoids decimals, but the number of minor-unit digits must be known for each currency. Do not assume every currency has two decimal places. For example, JPY normally has zero minor units, while KWD uses three decimal places under ISO 4217.

Do not send an amount without a currency. A value of 100 does not provide enough information to know whether it is 100 USD, 100 JPY, or 100 of another unit.

### 6.3. Scale and Rounding

BigDecimal retains scale. new BigDecimal("1.0") and new BigDecimal("1.00") are numerically equal, yet equals() returns false because their scales differ; compareTo() returns 0.

If scale carries contractual meaning, preserve and validate it. If only numeric comparison is needed, use compareTo or normalize according to a defined rule.

When rounding, choose an explicit RoundingMode:

~~~java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_EVEN);
~~~

Do not pick HALF_UP or HALF_EVEN arbitrarily. Rounding policies affect invoices, taxes, and ledgers; they must be agreed upon across services.

### 6.4. JSON Numbers and Decimal Strings

JSON numbers use decimal syntax, yet consumers may parse them into doubles. If consumers must preserve exact decimals across multiple languages, decimal strings are easier to control. If JSON numbers are used, the contract must require consumers to parse into an exact decimal type such as BigDecimal.

NaN and Infinity are not valid JSON numbers. Represent special states using null, status fields, or a dedicated code per schema.

## 7. Enums: Stable Wire Codes Instead of Ordinals

Java enums have an ordinal representing the constant's declaration position. If a serializer sends the ordinal, inserting a constant in the middle shifts the meaning of every subsequent value.

For example:

~~~java
enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED
}
~~~

If PAID is sent as 1, adding CANCELLED before PAID causes old and new consumers to interpret the same number 1 differently.

Use stable string codes:

~~~json
{
  "status": "paid"
}
~~~

Do not use translated display labels such as "Đã thanh toán" as wire codes. Java constant names can change during refactoring; display labels can change with UX or language. Wire codes must be stable and carry business meaning.

### 7.1. Mapping Enums with Jackson

You can define wire codes independently of Java constant names:

~~~java
enum OrderStatus {
    PENDING("pending"),
    PAID("paid"),
    SHIPPED("shipped"),
    CANCELLED("cancelled");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    @JsonValue
    public String code() {
        return code;
    }

    @JsonCreator
    public static OrderStatus fromCode(String value) {
        for (OrderStatus status : values()) {
            if (status.code.equals(value)) {
                return status;
            }
        }
        throw new IllegalArgumentException(
            "Unsupported order status: " + value
        );
    }
}
~~~

@JsonValue selects the value used during serialization; @JsonCreator defines how to convert a wire value back into an enum. You can rename the Java constant while keeping the wire code paid intact.

### 7.2. Unknown Values and Forward Compatibility

An older consumer may receive a new enum code from an upgraded producer. There are three strategies:

- **Strict:** reject the message with a clear error. Use when unknown states cannot be processed safely.
- **Fallback:** map to UNKNOWN or UNSUPPORTED. Use only if business logic allows handling unknown values.
- **Preserve raw value:** retain the original string so it can be logged, forwarded, or round-tripped without losing information.

If you only map an unknown enum to UNKNOWN and then re-serialize it as unknown, the consumer has lost the original code. If you need to proxy or replay events, preserve the raw code.

Do not reuse an old code for a new meaning. If a business state changes fundamentally, publish a new code and define a migration path.

## 8. Nulls, Missing Fields, and Defaults

JSON distinguishes an absent field from a field with a null value:

~~~json
{
  "status": null
}
~~~

differs from:

~~~json
{}
~~~

Consumers may map both to null depending on DTOs and configuration, yet the contract still needs to specify:

- Are required fields allowed to be null?
- Does a missing field mean use a default, retain the old value, or fail?
- Does null mean clear the value, unknown, or not applicable?
- Can older consumers ignore new fields?
- Can a producer stop sending an already-published field?

Do not silently apply defaults for time zone, currency, or amount when a field is missing. Wrong defaults can make a message syntactically valid yet semantically wrong in business logic.

For events, new fields should usually be added as optional with clear rules for older consumers. For commands, missing required fields must be validated before performing side effects.

## 9. Configuring Jackson in Spring Messaging and RSocket

Spring Messaging provides Message and MessageConverter abstractions. Converter configuration depends on the transport:

- For STOMP/WebSocket, MappingJackson2MessageConverter converts object payloads to JSON and back.
- For RSocket, RSocketStrategies manages Encoders/Decoders for data and metadata. You can register Jackson2JsonEncoder and Jackson2JsonDecoder backed by a configured ObjectMapper.
- For other transports, each adapter may have its own converter. Do not assume STOMP configuration automatically applies to RSocket or every broker.

Example creating an ObjectMapper with Java Time support and string formatting:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .enable(DeserializationFeature.FAIL_ON_NUMBERS_FOR_ENUMS)
    .build();
~~~

Registering the mapper in RSocketStrategies:

~~~java
RSocketStrategies strategies = RSocketStrategies.builder()
    .encoders(encoders -> encoders.add(
        new Jackson2JsonEncoder(mapper)
    ))
    .decoders(decoders -> decoders.add(
        new Jackson2JsonDecoder(mapper)
    ))
    .build();
~~~

Related codec imports:

~~~java
import org.springframework.http.codec.json.Jackson2JsonDecoder;
import org.springframework.http.codec.json.Jackson2JsonEncoder;
import org.springframework.messaging.rsocket.RSocketStrategies;
~~~

Use these strategies when configuring RSocketRequester or the server. Producer and consumer must agree on MIME types, ObjectMapper, schema, and validation rules. If multiple encoders/decoders are registered, check their ordering and MIME types to ensure the right codec is selected.

With STOMP, you can register MappingJackson2MessageConverter in the broker configuration and pass the same ObjectMapper. Check the configuration API for your Spring version, especially regarding whether you are replacing default converters or adding to them.

In Spring Boot, prefer the dependency management and customizer/bean mechanisms supported by that Boot version. Do not arbitrarily pin a separate Jackson version if the project's BOM already manages versions. Avoid creating a new ObjectMapper per message; mappers should be configured once and reused.

## 10. Java 17 Example: Explicitly Formatted Messages

The following example uses Jackson 2, Java Time, and enum wire codes. Amount is sent as a decimal string so consumers do not need to parse through floating point.

### Maven Dependencies

Add these dependencies in a standalone Maven project. In Spring Boot, use the project's BOM to manage versions instead of picking different versions manually:

~~~xml
<dependencies>
    <dependency>
        <groupId>com.fasterxml.jackson.core</groupId>
        <artifactId>jackson-databind</artifactId>
        <version>2.17.2</version>
    </dependency>
    <dependency>
        <groupId>com.fasterxml.jackson.datatype</groupId>
        <artifactId>jackson-datatype-jsr310</artifactId>
        <version>2.17.2</version>
    </dependency>
</dependencies>
~~~

### Source Code

Save as **MessageFormatDemo.java**:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.math.BigDecimal;
import java.time.Instant;

public class MessageFormatDemo {

    enum PaymentStatus {
        PENDING("pending"),
        SETTLED("settled"),
        REJECTED("rejected");

        private final String wireCode;

        PaymentStatus(String wireCode) {
            this.wireCode = wireCode;
        }

        @JsonValue
        public String wireCode() {
            return wireCode;
        }

        @JsonCreator
        public static PaymentStatus fromWireCode(String value) {
            for (PaymentStatus status : values()) {
                if (status.wireCode.equals(value)) {
                    return status;
                }
            }
            throw new IllegalArgumentException(
                "Unknown payment status: " + value
            );
        }
    }

    record PaymentMessage(
        int schemaVersion,
        String paymentId,
        Instant occurredAt,
        String amount,
        String currency,
        PaymentStatus status
    ) {}

    public static void main(String[] args) throws Exception {
        ObjectMapper mapper = JsonMapper.builder()
            .addModule(new JavaTimeModule())
            .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
            .build();

        PaymentMessage original = new PaymentMessage(
            1,
            "9007199254740993",
            Instant.parse("2026-11-07T14:17:00Z"),
            "1234.50",
            "USD",
            PaymentStatus.SETTLED
        );

        String json = mapper.writeValueAsString(original);
        PaymentMessage restored =
            mapper.readValue(json, PaymentMessage.class);

        BigDecimal amount = new BigDecimal(restored.amount());

        System.out.println(json);
        System.out.println("same-instant="
            + original.occurredAt().equals(restored.occurredAt()));
        System.out.println("amount=" + amount.toPlainString());
        System.out.println("status=" + restored.status().wireCode());
    }
}
~~~

### Compiling and Running

With Maven, you can use exec-maven-plugin to run the class after compiling:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=MessageFormatDemo
~~~

Exact output:

~~~text
{"schemaVersion":1,"paymentId":"9007199254740993","occurredAt":"2026-11-07T14:17:00Z","amount":"1234.50","currency":"USD","status":"settled"}
same-instant=true
amount=1234.50
status=settled
~~~

The example proves:

- Instant is serialized as an ISO-8601 UTC string.
- paymentId is a string, so it does not depend on JavaScript's safe integer limit.
- amount preserves scale via a decimal string.
- status uses the code settled instead of an ordinal or Java enum name.
- After deserialization, the values can be compared again.

This is a standalone Jackson demo without requiring a Spring container. In a real application, the same ObjectMapper can be used in Spring converters/codecs after checking MIME types and appropriate configuration.

## 11. Schema Evolution and Compatibility

Producers and consumers are often deployed independently. An older consumer may receive messages from a newer producer; a newer consumer may read older messages stored in a broker.

Useful rules:

1. Add optional fields before depending on them.
2. Specify defaults when reading older messages missing new fields.
3. Do not change the wire type of a field already in use.
4. Do not change the unit or precision of a field in place.
5. Do not change already-published enum codes.
6. Do not reuse old enum codes for new meanings.
7. For incompatible changes, release a new schemaVersion or a new field.
8. Keep consumers able to read versions still within their support window.
9. Test newer producers against older consumers and newer consumers against older payloads.

For example, if occurredAt used to be epoch milliseconds and you want to switch to an ISO string, do not change the type in place on the same field while old consumers are still active. You can publish occurredAtIso, read both during the transition period, and retire the old field on an agreed schedule.

## 12. Contract Tests and Golden Payloads

Internal serializer/deserializer tests only prove that one version of the code can read data written by itself. They do not prove that producers and consumers on different versions still understand each other.

Store golden payloads in test resources and verify:

- Old payloads deserialize cleanly on newer consumers.
- New payloads still contain the expected wire codes and formats.
- Missing/null fields are handled per schema.
- Unknown enum codes follow the strict/fallback/preserve policy.
- Instants do not shift time zones or precision beyond limits.
- Decimal strings do not change scale or get parsed through double.
- Long IDs preserve every digit.
- JSON numbers do not contain NaN/Infinity.
- Actual message MIME types and codecs are selected properly in integration tests.

If messages are digitally signed or hashed across raw bytes, canonicalization is also needed: UTF-8, escaping rules, number representation, and property ordering. JSON objects should not be assumed to have meaningful field order unless the contract defines a canonical form.

## 13. Common Mistakes

- Using LocalDateTime for event instants and relying on the server's time zone.
- Sending only a UTC offset when needing to recover a ZoneId.
- Using epochs without stating seconds vs. milliseconds.
- Losing nanoseconds when a consumer retains only milliseconds without a precision rule.
- Formatting numbers according to locale before serializing.
- Using double for money or exact decimal calculations.
- Sending long IDs as JSON numbers to JavaScript consumers.
- Sending BigDecimal as a JSON number while a consumer parses it as floating point.
- Omitting currency alongside amount.
- Using enum ordinals or translated display labels as wire values.
- Having no policy when a consumer receives a new enum code.
- Renaming fields, changing units, or changing types without a migration plan.
- Relying on implicit per-environment defaults for time zone, locale, or ObjectMapper configuration.
- Testing round-trips only within the same producer/consumer version.

## 14. Contract Release Checklist

- [ ] Time fields clearly distinguish instants, local date/time, and region-based schedules.
- [ ] Event timestamps use UTC ISO-8601 or epochs with explicitly documented units.
- [ ] ZoneId is preserved if business logic requires local schedules/DST.
- [ ] Time precision and truncate/round rules are agreed upon.
- [ ] Locale does not alter wire representation.
- [ ] Large IDs have safe representation across all consumers.
- [ ] Decimal numbers have precision, scale, and rounding policies.
- [ ] Money always includes currency and minor-unit rules.
- [ ] Enums use stable codes with an unknown-value policy.
- [ ] Nulls, missing fields, and defaults have explicit semantics.
- [ ] Spring converters/codecs use the right ObjectMapper and MIME types.
- [ ] Golden payloads and cross-version contract tests exist.
- [ ] Breaking changes have a versioning/migration plan.

## Conclusion

A message is reliable only when producer and consumer agree not only on data types but also on their meaning. Use Instant for event time, ZoneId for local schedules, locale-independent number formatting, exact decimals for money, and stable enum codes. Jackson and Spring Messaging provide the conversion tools; long-term compatibility still depends on the schema, validation, and evolution process defined by the system.

## References

- [Spring Framework Reference - Messaging](https://docs.spring.io/spring-framework/reference/messaging.html)
- [Spring Framework Reference - RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference - Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Jackson Datatype JSR-310](https://github.com/FasterXML/jackson-modules-java8/tree/2.17/datetime)
- [Java 17 Date-Time API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [JSON Data Interchange Syntax (RFC 8259)](https://www.rfc-editor.org/rfc/rfc8259)
- [IANA Time Zone Database](https://www.iana.org/time-zones)
