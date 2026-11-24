# Formatting Time, Time Zones, Numbers, and Enum Values

## Objectives

After this lesson, you will be able to:

- Choose the right Java type to represent instants, calendar dates, local clock times, and time zones.
- Design stable time formats across services, even when running across multiple countries.
- Avoid precision loss when exchanging large integers, decimals, and monetary amounts over JSON.
- Choose enum representations that survive renames, added values, and independent service upgrades.
- Configure Jackson codecs/converters in Spring Messaging and RSocket.
- Test serialization/deserialization contracts to catch incompatible changes.

This lesson belongs to the **Spring Framework - messaging** topic, under the **Message Contracts** branch. Values sent in messages are part of the contract between producer and consumer. Internal Java types do not automatically become a stable wire format: the two sides may use different languages, library versions, locales, and processing rules.

## 1. Why Must the Wire Format Be Explicitly Designed?

A Java object may contain an `Instant`, `BigDecimal`, or enum. When sent via messaging, an encoder converts the object into bytes according to a format such as JSON, CBOR, or another binary format. The consumer decodes those bytes into its own data types.

If producer and consumer interpret the same field differently, the message may still parse successfully yet carry the wrong meaning. For example:

- The producer sends local time, while the consumer interprets it as UTC.
- The producer sends an amount formatted as `1.234,50` according to locale, while the consumer expects a JSON number with a decimal point.
- The producer sends an enum using ordinal `2`, while the consumer has a different enum order after adding a new constant.
- The producer sends a 64-bit integer, and a JavaScript consumer rounds it because `Number` cannot represent that large integer accurately.
- The producer renames an enum or changes a field type without bumping the contract version.

Therefore, a message contract should specify at minimum:

1. Field names and wire types.
2. Units of measurement and precision.
3. Date-time format, timezone, and value semantics.
4. Stable enum codes and how unknown values are handled.
5. Rules for null, missing fields, default values, and validation.
6. Compatibility policy when producers and consumers are deployed at different times.

Do not rely on two services currently sharing the same Java class. The contract must be understandable from the message content and schema, independent of implementation.

## 2. Time: Choosing the Right Type Before Choosing the Format

The Java Time API has multiple temporal types because each describes a different meaning. Choosing the wrong type causes information loss even when serialization succeeds.

| Java Type | Meaning | Use When |
|---|---|---|
| Instant | A single point on the UTC timeline | Event creation time, payment time, logs, updates |
| OffsetDateTime | Date and time with a UTC offset such as +07:00 | Need to preserve the offset sent by the source |
| ZonedDateTime | Date and time bound to a ZoneId and regional rules | Schedules/appointments in a local time zone |
| LocalDateTime | Date and time on a clock without offset/zone | Wall-clock value meaningful only within a known local context |
| LocalDate | Calendar date without time or timezone | Birth date, calendar effective date |
| LocalTime | Time of day without date or timezone | Opening hours or daily recurring time |
| Duration | Amount of time in seconds/nanoseconds | Timeouts, elapsed duration |
| Period | Amount of time in calendar years/months/days | Calendar cycles such as 1 month or 1 year |

### 2.1. Instant for Occurrences That Have Happened

For events that have already occurred, `Instant` is usually the right choice. It represents a single point on the timeline and does not depend on the timezone of the machine running the service.

JSON example:

~~~json
{
  "eventId": "evt-901",
  "occurredAt": "2026-11-07T14:17:00Z"
}
~~~

The ISO-8601 string above represents a UTC instant. If a consumer in Vietnam displays that time in local time, it can convert it to 21:17 in `Asia/Ho_Chi_Minh`. Displaying in the user's timezone is a presentation step; do not alter the instant stored in the event.

### 2.2. An Offset Is Not a Time Zone

An offset such as `+07:00` only indicates the difference from UTC at a specific moment. It does not carry the full historical and future rules of a geographic region.

For example:

- `Asia/Ho_Chi_Minh` is a `ZoneId` from the IANA time zone database.
- `+07:00` is a fixed `ZoneOffset`.
- `OffsetDateTime` holds a date-time and an offset.
- `ZonedDateTime` holds both a `ZoneId` and regional transition rules.

If business logic only needs an instant when something happened, `Instant` is sufficient. If you need to render the exact local time for a chosen region or compute future schedules, keep `ZoneId` separately.

Example message for an appointment:

~~~json
{
  "appointmentId": "apt-42",
  "localDateTime": "2026-12-15T09:30:00",
  "timeZone": "Asia/Ho_Chi_Minh"
}
~~~

The consumer can construct a `ZonedDateTime` from `localDateTime` and `ZoneId`. For regions with DST rules, also define a policy for non-existent or ambiguous (repeated) local times.

### 2.3. DST: Local Times Can Be Ambiguous or Non-Existent

When a region transitions to daylight saving time, clocks may spring forward past a range of hours. A `LocalDateTime` falling inside that skipped gap maps to no instant at all. When clocks fall back, a `LocalDateTime` may map to two distinct instants.

Therefore, if a message represents a future appointment:

- Send `LocalDateTime` along with `ZoneId`, not just the current offset.
- Define how times falling in a DST gap are handled, such as rejecting and asking the user to pick again, or shifting to the next valid time.
- Define which offset to pick during a DST overlap, such as choosing the earlier or later offset.
- Once an appointment is resolved to a specific instant, also store the resolved `Instant` so all services agree on the result.

Do not assume every day has exactly 24 hours or every time zone has a fixed offset.

### 2.4. Avoid LocalDateTime for System-Wide Events

A `LocalDateTime` like `2026-11-07T21:17:00` does not say whether it is Vietnam time, UTC, or another region. If the producer sends `LocalDateTime` and the consumer attaches the server's default timezone, the result depends on the deployment environment.

Use `LocalDateTime` only when the semantics are genuinely wall-clock time and the timezone is specified elsewhere in the contract. For event timestamps, prefer `Instant`.

### 2.5. Epoch Units Must Be Named Clearly

Some systems use epoch numbers instead of ISO-8601 strings. Epoch values are typically seconds or milliseconds since `1970-01-01T00:00:00Z`. These two units differ by a factor of 1,000.

If using a number, the field name must state the unit clearly:

~~~json
{
  "createdAtEpochMillis": 1794061020000
}
~~~

Do not use ambiguous names like `timestamp` if the schema does not specify the unit. Java `Instant.toEpochMilli()` only retains millisecond precision; if business logic requires nanosecond precision, use an ISO-8601 string or a numeric convention with matching precision.

## 3. Formatting Time in JSON and Jackson

JSON does not define a dedicated date-time type. Timestamps are usually transmitted as strings or numbers. The contract must specify the format and meaning.

For Java Time, Jackson needs the JSR-310 support module. Common configuration for string timestamps:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();
~~~

Related imports:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;
~~~

When `WRITE_DATES_AS_TIMESTAMPS` is disabled, `Instant` is represented as an ISO-8601 string rather than an array or numeric timestamp. Consumers must likewise treat that field as a UTC instant.

Do not rely on the JVM's default timezone to interpret `LocalDateTime`. Nor should you assume calling `ObjectMapper.setTimeZone(UTC)` turns a `LocalDateTime` into an absolute instant; `LocalDateTime` carries no timezone.

If legacy DTOs use `java.util.Date` or `Calendar`, explicitly define the timezone used during conversion. For new code, prefer `java.time` so each type's semantics are unambiguous.

## 4. Locale Does Not Belong in the Wire Format

Locale serves how humans read and enter data. It must not alter machine-to-machine representations.

For example, the same monetary amount can be displayed in different ways:

| Locale | Display String |
|---|---|
| en-US | 1,234.50 |
| de-DE | 1.234,50 |
| vi-VN | 1.234,50 |

These are display strings, not JSON number formats. JSON numbers use a dot as the decimal separator and have no thousands separators:

~~~json
{
  "quantity": 1234.5
}
~~~

If `"1.234,50"` is sent as a string without specifying a locale, the consumer cannot tell whether the dot is a grouping separator or a decimal point.

Rules:

- Do not send locale-formatted numbers in numeric fields.
- Do not send translated month names, weekday names, or localized enum labels when consumers need machine codes.
- Do not depend on the JVM or container default locale.
- Format for users only at the presentation layer.
- For numeric strings in a contract, specify the decimal point, negative sign, scale, and leading-zero rules.

## 5. Integers and Cross-Language Precision Limits

Java has `byte`, `short`, `int`, `long`, and `BigInteger`. JSON has a single `number` syntax, which different languages may parse into different types.

JavaScript `Number` uses IEEE-754 binary64. It accurately represents all integers only within the safe range from `-(2^53 - 1)` to `+(2^53 - 1)`. A Java `long` outside this range may be rounded when a consumer parses it as `Number`.

For example, a 64-bit integer ID can lose digits in a JavaScript consumer. Because an ID is an identifier rather than a quantity for arithmetic, it should usually be sent as a string:

~~~json
{
  "accountId": "9007199254740993"
}
~~~

If a field is genuinely an arithmetic quantity, specify its type, range, and precision in the schema. For very large integers, consumers need `BigInt`/`BigInteger` or an equivalent library instead of `Number`.

Do not use ordinals, sequence indices, or mutable values as the stable identifier of an entity.

## 6. Decimals, BigDecimal, and Monetary Values

### 6.1. double Is Unsuitable for Exact Monetary Calculations

`double` uses binary floating-point arithmetic. Many decimal fractions such as `0.1` have no exact finite binary representation, so calculations can introduce rounding errors.

~~~java
System.out.println(0.1 + 0.2);
~~~

Typical output:

~~~text
0.30000000000000004
~~~

For money or decimals requiring contract-level exactness, use `BigDecimal`:

~~~java
BigDecimal amount = new BigDecimal("1234.50");
BigDecimal taxRate = new BigDecimal("0.08");
BigDecimal tax = amount.multiply(taxRate);
~~~

Construct `BigDecimal` from a normalized decimal string. Avoid `new BigDecimal(0.1)`, because that constructor converts the already-approximated `double` value into `BigDecimal`.

### 6.2. Choosing a Monetary Representation

There are two common approaches:

**Approach A — decimal string**

~~~json
{
  "amount": "1234.50",
  "currency": "USD"
}
~~~

Advantage: preserves scale and prevents consumers from converting it to floating point automatically. The contract must specify that the string is a normalized decimal without thousands separators and using a dot as the decimal point.

**Approach B — integer minor units**

~~~json
{
  "amountMinor": 123450,
  "currency": "USD"
}
~~~

This approach avoids decimals on the wire, but requires knowing the number of decimal digits for each currency. Never assume every currency has two decimal places. Some currencies have zero minor units; some have three. Rules must be based on currency metadata and the system's contract.

Never send a bare monetary amount without a currency. `100` could mean 100 USD, 100 JPY, or 100 units of another currency.

### 6.3. Scale and Rounding Must Be Business Rules

`BigDecimal` preserves scale. For example, `1.0` and `1.00` have equal numeric value, yet `BigDecimal.equals()` returns `false` because their scales differ; `compareTo()` returns `0`.

If scale is meaningful in the contract, preserve and validate it. If comparing only numeric value, use `compareTo()` or normalize according to agreed rules.

When rounding, explicitly specify `RoundingMode`:

~~~java
BigDecimal rounded = amount.setScale(2, RoundingMode.HALF_EVEN);
~~~

Do not pick `HALF_UP` or `HALF_EVEN` by guesswork; rounding policy affects invoices, taxes, and ledgers. Producers and consumers must apply the same business rule.

### 6.4. JSON Numbers Have Practical Limitations

JSON does not impose fixed decimal precision, yet parsers may convert numbers to `double`. When decimal precision must be preserved across multiple languages, decimal strings or integer minor units are usually clearer. If the schema uses JSON numbers, require consumers to parse them into `BigDecimal` or an equivalent decimal type.

Never send `NaN` or `Infinity` as JSON numbers. These are not valid numbers under standard JSON. Represent special states using `null`, a status field, or a dedicated code per the contract.

## 7. Enums: Use Stable Wire Codes, Not Ordinals

Java enums have a name and an ordinal. The ordinal is the constant's declaration position, starting at 0. If a serializer sends the ordinal, inserting a new constant in the middle changes the meaning of previously published numbers.

Unsafe example:

~~~java
enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED
}
~~~

If a producer sends ordinal `1` for `PAID`, and `CANCELLED` is later inserted before `PAID`, ordinal `1` can take on a different meaning. Old and new consumers can interpret the same number in two different ways.

Contracts should use stable string codes:

~~~json
{
  "status": "paid"
}
~~~

Do not use translated display labels such as `"Đã thanh toán"` as wire codes. Labels change with language or UX; codes must remain stable and locale-independent.

### 7.1. Jackson with @JsonValue and @JsonCreator

You can map enums to dedicated wire codes:

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

`@JsonValue` selects the string value during serialization. `@JsonCreator` defines how the enum is constructed during deserialization. This lets you rename internal Java constants without changing wire codes.

### 7.2. Unknown Enum Values

When a newer producer sends a new enum value, older consumers may not recognize it. Several policies exist:

- **Strict:** reject the message with a clear error. Appropriate when an unknown value makes safe business processing impossible.
- **Fallback UNKNOWN:** map to a default value. Appropriate only if business logic can handle an unknown state without causing inaccuracies.
- **Preserve raw string:** store the original code as a string or wrapper so older consumers can forward or record it without losing information.

Simply mapping to `UNKNOWN` and re-serializing as `"unknown"` loses the original code. If round-tripping or message forwarding is needed, preserve the raw code.

When adding a new enum value, consider deployment order: producers may emit the new code before all consumers are upgraded. Choose strict or fallback based on real compatibility needs, not on the wish that every service will deploy simultaneously.

### 7.3. Do Not Change Published Wire Codes

If the Java enum constant `PAID` is renamed to `SETTLED`, keep the wire code `"paid"` if it still represents the same contract concept. If the business meaning genuinely changes, publish a new code and define a migration path. Never reuse an old code for a new meaning.

## 8. Combining Time, Numbers, and Enums in One Message

An event message might have the following structure:

~~~json
{
  "schemaVersion": 1,
  "messageId": "9007199254740993",
  "occurredAt": "2026-11-07T14:17:00Z",
  "amount": "1234.50",
  "currency": "USD",
  "status": "paid"
}
~~~

Contract decisions here:

- `schemaVersion` is a small integer with version-bump rules.
- `messageId` is a string so it does not lose precision in JavaScript consumers.
- `occurredAt` is an ISO-8601 UTC instant.
- `amount` is a decimal string with a decimal dot and scale following currency rules.
- `currency` is a stable currency code.
- `status` is a string enum code, not an ordinal or display label.

A consumer can deserialize the message into its own DTO. The DTO is an implementation detail; the wire values above constitute the contract.

## 9. Configuring Jackson Codecs for Spring Messaging/RSocket

Spring Messaging provides the `Message` and `MessageConverter` abstractions. The transport determines how encoding/decoding is specifically handled:

- With STOMP/WebSocket message brokers, converters in the broker configuration typically convert object payloads to JSON and back. `MappingJackson2MessageConverter` is Spring Messaging's Jackson converter.
- With RSocket, `RSocketStrategies` manages the encoders/decoders used for data and metadata. You can configure a Jackson JSON encoder/decoder sharing the same `ObjectMapper`.
- With other transports or brokers, the corresponding adapter may have its own converter configuration. Do not assume a STOMP configuration automatically applies to RSocket or Kafka.

Example configuring `RSocketStrategies` with an `ObjectMapper` that has `JavaTimeModule`:

~~~java
ObjectMapper mapper = JsonMapper.builder()
    .addModule(new JavaTimeModule())
    .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS)
    .build();

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

Use these strategies when building an `RSocketRequester` or configuring an RSocket server. Ensure both producer and consumer agree on MIME types, `ObjectMapper`, and DTOs/schemas. If the application registers multiple codecs, verify their ordering and MIME types so the intended encoder/decoder is selected.

With STOMP, you can register `MappingJackson2MessageConverter` in `configureMessageConverters` of `WebSocketMessageBrokerConfigurer` and pass the same configured `ObjectMapper`. If keeping default converters, check the return value behavior of the configuration method according to the API of your Spring version.

Avoid creating a global `ObjectMapper` with rules tailored for one message without understanding the impact on HTTP APIs or other message types. You can use dedicated mappers/codecs per boundary when contracts differ.

## 10. Null, Missing Fields, and Default Values

JSON distinguishes a missing field from a field with value `null`. Consumers also need to know what both cases mean.

For example:

~~~json
{
  "status": null
}
~~~

differs from:

~~~json
{}
~~~

Some DTOs may map both to `null` without special configuration, yet the contract must still specify:

- Is a required field allowed to be `null`?
- What default value does an omitted optional field take?
- Does `null` mean clear the value, unknown, or not applicable?
- How must old consumers handle new fields added by producers?
- Can producers stop sending a previously published field?

For command messages, missing required fields should be validated and return diagnosable errors. Do not silently substitute a missing currency or timezone with a server default.

For events, new fields should usually be added compatibly: old consumers can ignore them if not needed; new consumers must have rules for older events lacking the field. Enabling or disabling `FAIL_ON_UNKNOWN_PROPERTIES` must be an intentional decision aligned with the schema evolution policy.

## 11. Schema Evolution and Producer/Consumer Compatibility

In distributed systems, you cannot guarantee all services upgrade at the exact same moment. A new producer may send messages to an old consumer; a new consumer may also read messages stored months earlier.

Safe rules:

1. Add an optional field before starting to depend on it.
2. Define clear, meaningful defaults when consumers read old messages.
3. Never change the wire type of a field currently in use.
4. Never change time units or currency units without releasing a new version or field.
5. Never change published enum codes.
6. Never reuse an old enum value for a different meaning.
7. For incompatible changes, version the schema or route/event type and define a migration plan.
8. Maintain contract tests across supported producer and consumer versions.

For example, if `occurredAt` was previously epoch milliseconds and needs to switch to an ISO string, do not change the same field name in place without a migration. You can introduce `occurredAtIso` in a new version, support reading both during the transition period, and retire the old field on an announced schedule.

## 12. Java 17 Example: Serializing a Message with a Clear Wire Contract

The following example uses Jackson 2 and Java Time to serialize/deserialize a DTO. ID, amount, and enum have stable wire representations.

### Maven dependencies

Add the following dependencies to `pom.xml`. In a Spring Boot project, use the dependency management/BOM managed by the Boot version rather than declaring versions that diverge from the project's platform.

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

### Source code

Save as **MessageContractDemo.java**:

~~~java
import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.fasterxml.jackson.databind.json.JsonMapper;
import com.fasterxml.jackson.datatype.jsr310.JavaTimeModule;

import java.math.BigDecimal;
import java.time.Instant;

public class MessageContractDemo {

    enum PaymentStatus {
        PENDING("pending"),
        PAID("paid"),
        CANCELLED("cancelled");

        private final String code;

        PaymentStatus(String code) {
            this.code = code;
        }

        @JsonValue
        public String code() {
            return code;
        }

        @JsonCreator
        public static PaymentStatus fromCode(String value) {
            for (PaymentStatus status : values()) {
                if (status.code.equals(value)) {
                    return status;
                }
            }
            throw new IllegalArgumentException(
                "Unsupported payment status: " + value
            );
        }
    }

    record PaymentEvent(
        int schemaVersion,
        String messageId,
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

        PaymentEvent event = new PaymentEvent(
            1,
            "9007199254740993",
            Instant.parse("2026-11-07T14:17:00Z"),
            "1234.50",
            "USD",
            PaymentStatus.PAID
        );

        String json = mapper.writeValueAsString(event);
        PaymentEvent restored = mapper.readValue(json, PaymentEvent.class);

        BigDecimal amount = new BigDecimal(restored.amount());

        System.out.println(json);
        System.out.println("instant-preserved="
            + event.occurredAt().equals(restored.occurredAt()));
        System.out.println("amount=" + amount.toPlainString());
        System.out.println("status=" + restored.status().code());
    }
}
~~~

### Compiling and running

With Maven, you can add `exec-maven-plugin` to `pom.xml` and run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=MessageContractDemo
~~~

Exact output:

~~~text
{"schemaVersion":1,"messageId":"9007199254740993","occurredAt":"2026-11-07T14:17:00Z","amount":"1234.50","currency":"USD","status":"paid"}
instant-preserved=true
amount=1234.50
status=paid
~~~

This example demonstrates:

- `Instant` serializes into an ISO-8601 UTC string.
- `messageId` is preserved as a string even though it exceeds JavaScript's safe integer limit.
- `amount` retains its two-digit scale via a decimal string.
- `PaymentStatus` uses the wire code `"paid"`, not the Java enum name or ordinal.
- After deserialization, time, monetary amount, and enum values can be re-validated.

This example is a standalone demo program independent of the Spring container, yet uses the same Jackson module/codec that a Spring application can configure. It does not replace business validation such as checking currency, amount scale, `schemaVersion`, or authorization to emit the event.

## 13. Testing Serialization Contracts

Do not merely check that JSON parses successfully. Verify exact wire values and edge cases.

Tests should cover:

- `Instant` serializes to valid UTC ISO-8601 and deserializes back to the same instant.
- `LocalDate` preserves the exact calendar date without shifting due to timezone.
- `LocalDateTime` does not have a default timezone implicitly attached.
- `ZoneId` is preserved if business logic needs regional schedule calculations.
- Epoch timestamps clearly state seconds vs. milliseconds.
- Large integers are not converted to JavaScript `Number` if they exceed the safe integer range.
- `BigDecimal` is not routed through `double`.
- Money always travels with currency and valid scale.
- Enums serialize to stable codes.
- Unknown enum codes are handled according to the strict/fallback/preserve policy.
- Missing fields, `null`, and new fields are handled per schema.
- Old payloads remain readable by new consumers per the compatibility policy.

A golden JSON fixture helps catch unintended changes. You can store sample payloads in test resources, serialize DTOs, and compare JSON structurally or in canonical form. If exact byte comparison is needed for signing or hashing, you must also specify canonical JSON, field ordering, UTF-8 encoding, and escaping rules; ordinary property order should not be treated as JSON semantics.

## 14. Common Mistakes

- **Using `LocalDateTime` for event timestamps:** lacks offset and timezone, so consumers may misinterpret the instant.
- **Sending `+07:00` and assuming consumers know the geographic region:** an offset does not contain a `ZoneId` or DST rules.
- **Relying on the server's default timezone:** results can differ across deployment environments.
- **Sending locale-formatted dates:** strings like `07/11/2026` are ambiguous between day/month and month/day.
- **Using `double` for money:** calculations can introduce rounding errors.
- **Sending `long` IDs as JSON numbers to JavaScript:** large integers can be rounded.
- **Sending `BigDecimal` as JSON numbers without specifying the parser:** consumers may parse them as floating point.
- **Sending enum ordinals:** adding or reordering constants alters wire meanings.
- **Using translated enum labels:** translation changes break the contract.
- **Rejecting every new enum without a rollout strategy:** new producers can cause old consumers to stop processing messages.
- **Mapping unknown enums to `UNKNOWN` and losing the raw code:** messages cannot round-trip intact.
- **Changing units or field types in place:** producers and consumers on different versions interpret the same data in two different ways.

## 15. Pre-Release Message Contract Checklist

- [ ] Every temporal field has a clear type and meaning: instant, local date, local time, or timezone-aware schedule.
- [ ] Event timestamps use UTC/ISO-8601 or epoch with explicitly documented units.
- [ ] `ZoneId` is stored if business rules need regional/DST logic.
- [ ] Locale does not affect the wire format.
- [ ] Large IDs are represented as strings or an integer type safe across all consumers.
- [ ] Decimals have defined precision, scale, and rounding rules.
- [ ] Money always includes currency; minor-unit scale is determined per currency.
- [ ] Enums use stable string codes, not ordinals/labels.
- [ ] A policy exists for unknown enum values.
- [ ] Null, missing fields, and defaults are specified.
- [ ] Producers and consumers use compatible codecs/MIME types.
- [ ] Golden payloads and contract tests exist for old and new versions.
- [ ] Incompatible changes are versioned and have a migration plan.

## Conclusion

Formatting for time, numbers, and enums determines a message's meaning once it crosses service boundaries. Use `Instant` for occurrences that have happened, retain `ZoneId` when local schedules are needed, use `BigDecimal` or decimal strings for decimal accuracy, and use stable enum wire codes. Configuring Jackson in Spring converters/codecs is only one part; producers and consumers still must agree on schemas, validation, null semantics, and evolution strategy.

## References

- [Spring Framework Reference - Messaging](https://docs.spring.io/spring-framework/reference/messaging.html)
- [Spring Framework Reference - RSocket](https://docs.spring.io/spring-framework/reference/rsocket.html)
- [Spring Framework Reference - Data Buffers and Codecs](https://docs.spring.io/spring-framework/reference/core/databuffer-codec.html)
- [Jackson Datatype JSR-310](https://github.com/FasterXML/jackson-modules-java8/tree/2.17/datetime)
- [Java Date-Time API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/package-summary.html)
- [JSON Data Interchange Syntax (RFC 8259)](https://www.rfc-editor.org/rfc/rfc8259)
- [IANA Time Zone Database](https://www.iana.org/time-zones)
