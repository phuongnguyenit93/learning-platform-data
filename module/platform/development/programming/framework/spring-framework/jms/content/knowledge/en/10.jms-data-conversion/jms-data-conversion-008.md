# Missing Values, Nulls, Numeric Types, and Time Types in Spring JMS Data Contracts

## 1. Nature of the Problem: A Data Contract, Not Just a Java Class

In a system using Spring Framework JMS, a producer sends a message to a queue/topic; a consumer typically receives the message **after a delay** and may be running on a different application version. `MessageConverter`/Jackson convert between Java objects and data inside a JMS Message, yet cannot infer all the **business semantics** of every field.

Suppose a consumer receives three JSON documents:

~~~json
{"orderId":"O-42","discount":0}
{"orderId":"O-42","discount":null}
{"orderId":"O-42"}
~~~

They are not necessarily equivalent:

1. **`discount = 0`**: may be a valid discount of zero.
2. **`discount = null`**: the producer explicitly sent a null value; depending on the contract, this could mean unknown/uncalculated or a request to clear.
3. **`discount` absent**: the producer did not send the field. In an older event version, the field may be unsupported; in a patch, it may mean "unchanged".

If a developer deserializes all three into a Java primitive `int` with default value `0`, the distinction is lost. Similarly, monetary amounts converted to `double` can lose precision, while timezone-less timestamps can be misinterpreted between two services.

Lesson goals:

- Clearly define **missing**, **explicit null**, **empty**, **zero**, and **default**.
- Choose lossless numeric types and unambiguous time types.
- Design payload contracts when using TextMessage/JSON, MapMessage, and JMS message properties.
- Use Jackson/`JmsTemplate` in their proper roles without letting converters decide business semantics.
- Handle schema compatibility, validation, and conversion errors in asynchronous consumers.
- Practice with Java 17, Spring Boot, Jackson, and ActiveMQ Artemis.

## 2. Separating Three Layers: Payload, JMS Metadata, and Java Objects

~~~mermaid
flowchart LR
    A["Java domain object"] --> B["ObjectMapper / MessageConverter"]
    B --> C["JMS Message: JSON TextMessage or MapMessage"]
    C --> D["Broker: queue/topic"]
    D --> E["JMS Message"]
    E --> F["Parse + validate contract"]
    F --> G["Consumer domain object"]
~~~

A JMS message has:

| Layer | What Does It Contain? | Example | Rule |
| --- | --- | --- | --- |
| Standard JMS headers | JMS transport info | `JMSMessageID`, `JMSTimestamp`, `JMSExpiration`, `JMSType` | Defined by API/protocol; not equivalent to business fields. |
| JMS properties | Simple typed metadata for filtering/routing | `SchemaVersion`, `TenantId`, `EventKind` | JMS-typed names/values; accessible to selectors. |
| Message body | Business payload | JSON in `TextMessage`, key/value in `MapMessage` | Data contract agreed upon by producer/consumer. |
| Java DTO | Representation within one application | `record OrderCreated(...)` | Not a wire format and may evolve over time. |

**`JmsTemplate` does not standardize nulls/numbers/timestamps on its own.** It simply uses the configured `MessageConverter`. The converter builds/reads messages; whether a field may be omitted, may be null, has numeric bounds, or uses a particular timezone is the responsibility of the **contract and validation**.

An illustration with the default `SimpleMessageConverter`:

~~~java
jmsTemplate.convertAndSend("orders.events", jsonText);
String json =
        (String) jmsTemplate.receiveAndConvert("orders.events");
~~~

This snippet requires a `jmsTemplate` bean and `jsonText`. Default `SimpleMessageConverter` converts `String` ↔ `TextMessage`; it **does not parse JSON into business records**. When using `MappingJackson2MessageConverter` or a custom converter, receiving behavior may differ. Never assume Spring automatically understands every JSON schema.

## 3. Different States Must Be Documented in the Contract

| State | JSON Example | Potential Meaning | Bug When Conflated |
| --- | --- | --- | --- |
| Missing field | `{}` | Unsupported, unknown, or "no change" | Silently assigning `0`/`null` loses absence info. |
| Explicit null | `{"note":null}` | No value or explicit clear (per business rules) | Mistaken for missing field; clear command missed. |
| Empty string | `{"note":""}` | Value supplied as empty | Treated as null despite potentially different meaning. |
| Whitespace-only string | `{"note":"   "}` | Invalid data or input needing normalization | Silent trimming loses meaning. |
| Zero | `{"quantity":0}` | Count of zero | Treating `0` as "missing information". |
| `false` | `{"enabled":false}` | State explicitly disabled | Treating `false` as an absent field. |
| Empty array | `{"items":[]}` | Collection of size 0 | Confused with "not loaded/unsupported". |
| Empty object | `{"details":{}}` | Object present with no properties | Confused with null or missing object. |

### 3.1. Golden Rule: Missing Differs from Null

Ask before coding:

- Is the field **required**? If required, both missing and null may be considered invalid.
- If optional, what does **missing** mean? Absent in an older version, use a default, or "unchanged"?
- Can **null** be sent? Does it differ from missing?
- Are **`0`**, **`false`**, **`""`**, and **`[]`** preserved as valid values?
- When the producer bumps versions, what will old consumers do upon seeing a new field?

Avoid blanket rules like "turn all nulls and empties into defaults". That might work for a UI form field yet be completely wrong for a message representing a transaction or update command.

### 3.2. Event Snapshots vs. Partial Updates

Two message patterns often assign different meanings to null:

**Event snapshot:** describes state at a point in time.

~~~json
{
  "eventType": "customer.snapshot.v1",
  "customerId": "C-42",
  "displayName": "An",
  "phone": null
}
~~~

If the contract specifies `phone: null` means "phone number unknown", it can be valid. However, if `phone` is missing in a snapshot, an older producer may not support that field yet. The application needs an explicit policy rather than merging null and missing.

**Partial update/patch:** describes changes to apply:

~~~json
{
  "eventType": "customer.patch.v1",
  "customerId": "C-42",
  "changes": {
    "phone": null
  }
}
~~~

In an **application-defined patch convention**: omitting `phone` from `changes` means keep as-is, `phone: null` means delete, `phone: "..."` means replace. This is an example of *business semantics*, not default JMS or Jackson behavior.

When sending patches like this, a Java DTO having only `String phone` is usually **insufficient** to distinguish an absent field from an explicit null. You need JSON tree parsing, a tri-state wrapper, or a dedicated patch schema.

## 4. Example of a Strictly Typed JSON Contract

Suppose a system exchanges the `order.created.v1` event:

~~~json
{
  "eventId": "evt-0042",
  "schemaVersion": 1,
  "orderId": "O-42",
  "currency": "USD",
  "total": "10.25",
  "quantity": 2,
  "occurredAt": "2026-10-30T10:00:00Z",
  "customerNote": null
}
~~~

The example intentionally uses **`total` as a decimal string** rather than a JSON floating-point number so consumers across languages preserve decimal precision when needed. Another contract might use a JSON number bound into `BigDecimal`, or money in **integer minor units**; what matters is both sides agreeing.

| Field | JSON Type | Recommended Java Type | Required? | Contract Rule |
| --- | --- | --- | --- | --- |
| `eventId` | string | `String` | Yes | Non-empty, unique per domain, invariant across redeliveries. |
| `schemaVersion` | integer | `int` or `Integer` after validation | Yes | Starts at 1; parser must reject String `"1"` if contract specifies integer. |
| `orderId` | string | `String` | Yes | Identifier; never converted to a number for arithmetic. |
| `currency` | string | `String` / controlled enum | Yes | E.g. `USD`; decimal-place rules per contract. |
| `total` | string decimal | `BigDecimal` after parsing | Yes | E.g. `"10.25"`, exact precision/scale, no NaN/Infinity. |
| `quantity` | integer | `long`/`Long` or `int`/`Integer` | Yes | Published range, e.g. `quantity >= 0`. |
| `occurredAt` | ISO-8601 UTC string | `Instant` | Yes | Event timestamp in UTC; has `Z` suffix. |
| `customerNote` | string or null | Tri-state wrapper if needed | Optional | Missing/null/empty carry distinct meanings. |

Do not treat a Java DTO as the sole specification. The contract must specify **wire types**, requiredness, nullability, ranges, time representation, units, and version evolution.

### 4.1. Payload Contract and JMS Properties Must Agree

You can attach JMS metadata:

~~~java
message.setJMSType("order.created.v1");
message.setIntProperty("SchemaVersion", 1);
message.setStringProperty("TenantId", "tenant-a");
~~~

This is a snippet where `message` is a newly created `jakarta.jms.Message`. `JMSType` is a **standard header**; `SchemaVersion`/`TenantId` are **application-set properties**. If the body also contains `schemaVersion=1`, the producer must ensure they match; if they disagree, the consumer should reject or route into a controlled error path.

A selector can filter on `SchemaVersion=1`, yet **cannot automatically verify** that the body has `schemaVersion`, `total`, or `occurredAt` in the right types. Selectors are metadata filters, not a schema validation engine.

## 5. Jackson: Detecting Missing Fields and Explicit Nulls Before Binding DTOs

In Jackson, reading JSON as a **`JsonNode`/`ObjectNode`** preserves those states separately:

~~~java
ObjectMapper mapper = new ObjectMapper();

JsonNode missing = mapper.readTree("{\"noteOwner\":\"n/a\"}");
JsonNode explicitNull = mapper.readTree("{\"customerNote\":null}");
JsonNode empty = mapper.readTree("{\"customerNote\":\"\"}");

// Missing field:
System.out.println(missing.has("customerNote"));         // false

// Field exists but is JSON null:
System.out.println(explicitNull.has("customerNote"));    // true
System.out.println(explicitNull.get("customerNote").isNull()); // true

// Field exists and is an empty string:
System.out.println(empty.hasNonNull("customerNote"));    // true
System.out.println(empty.get("customerNote").asText().isEmpty()); // true
~~~

This is a Java snippet with `com.fasterxml.jackson.databind.JsonNode`/`ObjectMapper` imported and invoked inside a method declaring `throws JsonProcessingException`; not a standalone `main` class. Comments simply show the printed values.

### 5.1. `get`, `path`, `has`, and `hasNonNull`

| API | Missing Field | Field Is JSON null |
| --- | --- | --- |
| `node.has("x")` | `false` | `true` |
| `node.hasNonNull("x")` | `false` | `false` |
| `node.get("x")` | Java `null` | `NullNode` |
| `node.path("x")` | `MissingNode` | `NullNode` |
| `node.path("x").isMissingNode()` | `true` | `false` |
| `node.get("x").isNull()` | `NullPointerException` if `get` is not null-checked first | `true` |

**Common mistake:** calling `node.path("x").asText()` or binding a nullable DTO and treating missing and null as identical. Many convenience methods have defaults/fallbacks that collapse the two states. When business rules distinguish them, first check **whether the key exists**, then inspect its value.

### 5.2. A Tri-State Model

If the contract genuinely requires distinguishing missing/null/value, declare a Java 17 wrapper:

~~~java
sealed interface FieldValue<T>
        permits Absent, ExplicitNull, Present {}

record Absent<T>() implements FieldValue<T> {}
record ExplicitNull<T>() implements FieldValue<T> {}
record Present<T>(T value) implements FieldValue<T> {}
~~~

These records/interface are a snippet; add a parser for each field. For example:

~~~java
static FieldValue<String> readOptionalText(
        JsonNode root, String name) {

    if (!root.has(name)) {
        return new Absent<>();
    }
    JsonNode value = root.get(name);
    if (value.isNull()) {
        return new ExplicitNull<>();
    }
    if (!value.isTextual()) {
        throw new IllegalArgumentException(
                name + " must be string or null");
    }
    return new Present<>(value.textValue());
}
~~~

With this snippet, `value=""` remains **`Present("")`**, never turning into absent/null. In patch handling, the application can apply the policy:

- `Absent` -> keep existing data unchanged.
- `ExplicitNull` -> clear data if permitted by contract.
- `Present("")` -> store empty string or reject, depending on business rules.

Do not assume every event needs a wrapper like this; it fits when tri-state semantics truly matter.

### 5.3. Why Primitives and Records Can Hide Missing Fields

~~~java
record OrderDto(int quantity, boolean confirmed, String note) {}
~~~

If you only bind JSON into this type without validation, consumers easily confuse **`quantity=0`** with a missing/null quantity field; `boolean false` is similarly easy to misinterpret. Under some Jackson settings, null for a primitive can be coerced to a default value, and a missing field can receive Java's default value.

For required fields, **validate the JSON shape first**, or enable Jackson's corresponding strict modes and test with your actual library version:

~~~java
mapper.enable(
        DeserializationFeature.FAIL_ON_NULL_FOR_PRIMITIVES);
mapper.enable(
        DeserializationFeature.FAIL_ON_MISSING_CREATOR_PROPERTIES);
mapper.enable(
        DeserializationFeature.FAIL_ON_NULL_CREATOR_PROPERTIES);
~~~

This snippet requires `ObjectMapper`/`DeserializationFeature` imports. These strict settings affect the entire binding process and must match the schema; they do not replace validation for negative numbers, precision, timestamp formats, empty strings, or optional cases.

**Warning on `@JsonProperty(required=true)`:** it does not enforce every field identically across all binding/setter styles. Use explicit schema validation or custom validation alongside integration tests for the real parsing path.

### 5.4. `@JsonInclude` and Losing the Null Distinction

~~~java
@JsonInclude(JsonInclude.Include.NON_NULL)
record CustomerEvent(String name, String phone) {}
~~~

Above is a snippet. With `NON_NULL`, `phone=null` is omitted from JSON during serialization; if the receiver must distinguish **explicit null** from **missing**, this policy silently erases that information. Other options like `NON_ABSENT`/`NON_EMPTY` can also cause fields to disappear when serializing. Pick include/omit policies per contract rather than enabling them globally without inspecting wire output.

## 6. Numeric Types: Integers, Decimals, Precision, and Range

### 6.1. Zero Is Not Missing

~~~json
{"quantity":0}
~~~

`Quantity=0` is **a transmitted value**. It may be valid (empty cart) or invalid (purchase order requiring `quantity >= 1`), yet must be evaluated by domain rules.

Do not write:

~~~java
int quantity = node.path("quantity").asInt(0);
// Fails to distinguish missing, null, wrong type, and valid 0.
~~~

Validate presence, JSON type, and range:

~~~java
JsonNode q = node.get("quantity");

if (q == null || !q.isIntegralNumber()
        || !q.canConvertToInt()) {
    throw new IllegalArgumentException(
            "quantity must be a 32-bit JSON integer");
}
int quantity = q.intValue();
if (quantity < 0) {
    throw new IllegalArgumentException(
            "quantity cannot be negative");
}
~~~

This snippet rejects `quantity="2"`, `quantity=2.0`, `quantity=null`, missing `quantity`, or numbers too large for `int`. If the contract permits `long`, use `canConvertToLong`/`longValue` and validate business ranges.

### 6.2. Do Not Use `double`/`float` for Monetary Amounts Needing Exact Arithmetic

Java `double` uses binary floating point, so many decimal values such as `0.1` have no exact representation. Example:

~~~java
double x = 0.1 + 0.2;
System.out.println(x == 0.3); // false

BigDecimal a = new BigDecimal("0.10");
BigDecimal b = new BigDecimal("0.20");
System.out.println(a.add(b).toPlainString()); // 0.30
~~~

This snippet imports `java.math.BigDecimal`. For currencies, exchange rates, and measurements needing exact precision, use **`BigDecimal`** or **integer minor units** with explicit units. Never call `new BigDecimal(0.1)`, as it inherits the representation error already inside `double`; use `new BigDecimal("0.1")` or `BigDecimal.valueOf(double)` when the input is necessarily a `double` and semantics are understood.

### 6.3. Choosing a Wire Representation for Decimals

Three common approaches:

**A. JSON number + `BigDecimal` at consumer**

~~~json
{"amount":10.25,"currency":"USD"}
~~~

Valid when every consumer genuinely parses into exact decimals (e.g. Jackson `BigDecimal`) without passing through floating-point types that lose precision. For untyped JSON trees or Maps, consider:

~~~java
mapper.enable(DeserializationFeature.USE_BIG_DECIMAL_FOR_FLOATS);
~~~

Enabling this prevents Jackson from defaulting generic floating-point numbers to `double` in supported binding paths; however, preserving scale/trailing zeros depends on the parse path and config. Test explicitly if `10.20` vs. `10.2` matters in the contract.

**B. Decimal string**

~~~json
{"amount":"10.25","currency":"USD"}
~~~

Parsers read a `String` and call `new BigDecimal(text)`, allowing pattern, range, and scale validation. This avoids risks of JSON numbers being rounded by JavaScript consumers, with the trade-off that the schema must strictly declare **string**—never mix string and number across services.

**C. Integer minor units**

~~~json
{"amountMinor":1025,"currency":"USD","scale":2}
~~~

The value `1025` equals `10.25 USD` when `scale=2`. For JPY or other assets, the minor unit must be explicitly published; never assume every currency has 2 decimal places. Integer minor units require overflow checks and scale rules. Never name a field `amountMinor` while forgetting to document currency/unit.

### 6.4. Scale, Rounding, Range

~~~java
BigDecimal amount = new BigDecimal("10.25");
amount = amount.setScale(2, RoundingMode.UNNECESSARY);
if (amount.signum() < 0) {
    throw new IllegalArgumentException(
            "Amount must be nonnegative");
}
~~~

This snippet requires importing `BigDecimal`/`RoundingMode`. `UNNECESSARY` enforces that no rounding is needed when setting scale, preventing silent truncation of money. For contracts allowing **exactly two decimal digits** on the wire, also run a regex/JSON schema check before `BigDecimal` parsing to distinguish `"10.2"` from `"10.20"` if lexical/canonical form is required.

`BigDecimal.equals(...)` also compares scale: `new BigDecimal("10.0").equals(new BigDecimal("10.00"))` is `false`; `compareTo(...)` indicates numeric equality. Separate business rules for equality, representation, and storage.

### 6.5. Large JSON Integers and JavaScript Limits

Java `long` has 64-bit signed range; JavaScript `Number` only preserves exact integers up to **`2^53 - 1`**. Sending a long numeric ID or epoch nanoseconds exceeding the safe integer limit through JavaScript can alter low-order bits.

**Recommendation:** treat IDs as opaque strings, not numbers for arithmetic. In polyglot systems, consider representing large integers as strings with an explicit schema; if using JSON integer numbers, document exact precision limits and types across all consumers.

### 6.6. NaN, Infinity, and Division by Zero

Standard JSON has no `NaN`, `Infinity`, or `-Infinity` literals. Never use them as "missing amount"; that is an invalid data state. If a sensor has an unmeasurable reading, use a nullable field or dedicated status:

~~~json
{"temperature":null,"quality":"NO_READING"}
~~~

In financial systems, use an enumerated error/status field instead of sentinels such as `-1`, `Double.NaN`, or magic numbers like `999999999`.

## 7. Time Types: `Instant`, `OffsetDateTime`, `LocalDate`, and Zones

Time is a subtle source of bugs: `2026-10-30 10:00` could be 10 AM in Hanoi, Tokyo, or UTC. If producer and consumer interpret it differently, the same timestamp shifts by hours.

### 7.1. Choosing Types by Business Meaning

| Meaning | Recommended Wire Format | Java Type | Example |
| --- | --- | --- | --- |
| An absolute point in time | ISO-8601/RFC3339 with offset; UTC `Z` recommended | `Instant` / `OffsetDateTime` | `"2026-10-30T10:00:00Z"` |
| Calendar date without time | ISO date | `LocalDate` | `"2026-10-30"` |
| Local wall-clock time for appointments | `LocalDateTime` **paired with** published `ZoneId` or offset | `LocalDateTime` + `ZoneId` | `"2026-10-30T09:00:00"`, `"Asia/Ho_Chi_Minh"` |
| Duration | ISO-8601 duration or number with explicit unit | `Duration` | `"PT15M"` or `durationMs=900000` |
| Absolute epoch timestamp | integer with unit in name/schema | `Instant.ofEpochMilli(...)` | `occurredAtEpochMs:1793354400000` |
| Timezone preserving region/DST rules | IANA Zone ID | `ZoneId` | `"Europe/Paris"` |

The epoch timestamp in the table is only a **format example**; no manual calculation is needed to understand the contract. During implementation, verify specific timestamps with a time library and synchronize system timezones.

### 7.2. Why `Instant` Usually Fits Event Times

~~~java
Instant occurredAt =
        Instant.parse("2026-10-30T10:00:00Z");

System.out.println(occurredAt);
// 2026-10-30T10:00:00Z
~~~

`Instant` represents a point on the timeline, independent of the machine's default timezone. The same `Instant` renders differently in `Asia/Ho_Chi_Minh` and `Europe/Paris`, yet represents the exact same moment.

**Never store a standalone `LocalDateTime` to describe an absolute event time.** `LocalDateTime` lacks an offset/`ZoneId`, so its position on the timeline is unknown. If receiving `LocalDateTime` because a source system only has "local time", pair it with an explicitly specified `ZoneId` and a policy for ambiguous/non-existent hours across DST transitions.

### 7.3. Date-Only Is Not an Instant at 00:00 UTC

Birthdays, delivery dates, or settlement dates are usually **calendar dates**, e.g.:

~~~json
{"deliveryDate":"2026-11-01"}
~~~

Converting `LocalDate` to `Instant` under an arbitrary timezone and deserializing elsewhere can shift the calendar date by a day. Keep `LocalDate` in date-only contracts. When an absolute deadline instant is required (e.g. end-of-day expiration), specify the exact timezone and cutoff time.

### 7.4. Epoch Seconds vs. Milliseconds

~~~java
Instant fromSeconds =
        Instant.ofEpochSecond(1_700_000_000L);
Instant fromMillis =
        Instant.ofEpochMilli(1_700_000_000_000L);

// Both values represent the exact same instant.
System.out.println(fromSeconds.equals(fromMillis)); // true
~~~

This is a Java 17 snippet with sample values. Although both are integers, the units differ by **1,000x**. Avoid timestamp field names that omit units. Name them `occurredAtEpochMs`, `scheduledAtEpochSeconds`, `timeoutMs`, etc., or choose ISO-8601 strings.

Similarly, Kafka timestamps, Unix seconds, database timestamps, JMS headers, and `ZonedDateTime` do not automatically share units or timezones. Convert using tested APIs rather than arbitrary multiplication/division.

### 7.5. `JavaTimeModule` with Jackson

When using `java.time` types in DTOs, configure Jackson properly:

~~~java
ObjectMapper mapper = new ObjectMapper();
mapper.registerModule(new JavaTimeModule());
mapper.disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);

record EventTime(Instant occurredAt) {}
String json = mapper.writeValueAsString(
        new EventTime(
                Instant.parse("2026-10-30T10:00:00Z")));
~~~

This snippet requires importing `ObjectMapper`, `JavaTimeModule`, `SerializationFeature`, `Instant` and declaring `record EventTime` in a valid scope. With this configuration, an ISO-8601 string wire format is readable and portable. When Spring Boot auto-configures an `ObjectMapper` with Jackson Java Time on the classpath, many modules are pre-registered; **never assume a manually constructed `new ObjectMapper()` behaves identically to Boot's `ObjectMapper`**.

### 7.6. Business Timestamps vs. JMS Transport Timestamps

JMS provides `JMSTimestamp`, `JMSExpiration`, and `JMSDeliveryTime` headers. They convey **transport** information; they do not replace fields such as `occurredAt`, `approvedAt`, `paidAt`, or `businessDeadline`.

Example:

~~~json
{
  "occurredAt": "2026-10-30T10:00:00Z",
  "businessDeadline": "2026-10-30T10:05:00Z"
}
~~~

If a message is resent a minute later, `JMSMessageID` and `JMSTimestamp` can change, whereas `occurredAt` remains the original event time. To determine whether a task is still valid, check `businessDeadline`/state rather than relying solely on `JMSExpiration` or receive time.

## 8. JMS `MapMessage` and Message Properties vs. JSON Objects

`MapMessage` is a JMS message kind whose body contains simple typed name–value pairs. It **is not a JSON document** and does not natively support `BigDecimal`, `Instant`, or arbitrary DTOs in the `MapMessage` body.

Example:

~~~java
MapMessage message = session.createMapMessage();
message.setString("eventId", "evt-0042");
message.setInt("quantity", 0);
message.setString("amount", "10.25");
message.setLong("occurredAtEpochMs", 1793354400000L);
~~~

This snippet requires a JMS `Session` and importing `jakarta.jms.MapMessage`. For decimal money, store a `String` in canonical format like `"10.25"` and parse `BigDecimal` on the consumer. When choosing epoch timestamps, specify millisecond units and verify against a concrete `Instant` in tests; **do not** assume `MapMessage` stores `Instant` directly.

### 8.1. `itemExists` Distinguishes Missing Fields

~~~java
if (message.itemExists("quantity")) {
    int qty = message.getInt("quantity");
} else {
    // Field quantity does not exist in the MapMessage body.
}
~~~

Per Jakarta Messaging, `MapMessage.getObject("name")` may return `null` when a field is missing, while `itemExists("name")` distinguishes whether an entry exists. When detecting missing fields, **do not simply call `getInt`/`getLong`/`getString` and guess**. Several primitive getters reading `null` can throw exceptions per JMS type-conversion rules rather than returning zero.

Explicit `null` states in JMS `MapMessage` require checking provider/contract support and how producers set fields. If tri-state missing/null/value is central, JSON inside a `TextMessage` is usually easier to represent and validate explicitly.

### 8.2. JMS Message Properties Have Type Restrictions

~~~java
message.setStringProperty("TenantId", "tenant-a");
message.setIntProperty("SchemaVersion", 1);
message.setLongProperty("OccurredAtEpochMs", 1793354400000L);
~~~

JMS properties allow only specification-supported primitive/wrapper types and `String`. **`BigDecimal` and `Instant` are not valid JMS property types**; never pass them directly:

~~~java
// Invalid for standard JMS properties:
message.setObjectProperty("Amount", new BigDecimal("10.25"));
// May throw MessageFormatException.
~~~

That is an anti-pattern, not runnable code. Similarly, `MapMessage.setObject("Amount", BigDecimal)` is not a standard way to send a `BigDecimal` object. Convert to a schema-defined `String`, integer minor units, or a JSON body.

### 8.3. String Property Type Differs from Selector Type

~~~java
message.setStringProperty("SchemaVersion", "1");
~~~

It looks numeric, yet is actually a `String`. If a consumer uses selector `SchemaVersion >= 1` with a numeric literal, matching may fail as intended. Use `setIntProperty("SchemaVersion", 1)` and declare the type in the contract.

Never equate missing/explicit null in message properties with JSON null. JMS selectors use three-valued logic (`TRUE`/`FALSE`/`UNKNOWN`) when a property is missing; JMS setters/getters and data types differ from JSON objects. To validate payloads, read the body via a dedicated converter/parser rather than inferring from selectors.

## 9. `MappingJackson2MessageConverter` in Spring JMS: Accurate and Complete

Spring Framework 6.x provides **`org.springframework.jms.support.converter.MappingJackson2MessageConverter`** to convert Java objects to JSON JMS messages and vice versa.

### 9.1. Surprising Defaults

- By default, the converter **creates a `BytesMessage`**, not a `TextMessage`. For readable JSON text, call `setTargetType(MessageType.TEXT)`.
- For the converter to restore Java objects on receive, you typically must configure the **type-id message property** via `setTypeIdPropertyName(...)`.
- Without configured mappings, the type ID may be the Java class name; use contract-stable IDs instead of forcing consumers to know producer class names.
- The converter **does not validate business schemas** and does not know which missing/null/zero cases are valid.
- `ObjectMapper` governs null inclusion, numeric coercion, and `JavaTimeModule`; align configurations across services.

### 9.2. Configuring the Converter with Type Mappings

~~~java
import java.util.Map;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.support.converter.MappingJackson2MessageConverter;
import org.springframework.jms.support.converter.MessageConverter;
import org.springframework.jms.support.converter.MessageType;

@Bean
MessageConverter messageConverter(ObjectMapper objectMapper) {
    MappingJackson2MessageConverter converter =
            new MappingJackson2MessageConverter();
    converter.setTargetType(MessageType.TEXT);
    converter.setObjectMapper(objectMapper);
    converter.setTypeIdPropertyName("PayloadType");
    converter.setTypeIdMappings(
            Map.of("order-created-v1", OrderCreatedV1.class));
    return converter;
}
~~~

This is a **configuration snippet** inside Spring `@Configuration`, requiring a separate `OrderCreatedV1` class/record declaration. Senders and receivers must use the same type-id mapping and converter config; never assume a custom `JmsTemplate` and a separate listener factory synchronize automatically without attaching the converter to both.

Example DTO:

~~~java
record OrderCreatedV1(
        String eventId,
        BigDecimal total,
        Instant occurredAt,
        String customerNote) {}
~~~

This snippet requires importing `BigDecimal` and `Instant`. This mapping style alone cannot distinguish "missing `customerNote`" from "`customerNote=null`" after binding; validate the JSON tree before losing that information or use a specialized DTO/deserializer. If choosing a decimal-string wire contract, define an explicit mechanism to read `BigDecimal` from `String`; Jackson may coerce under certain configs, yet **you should never rely on implicit coercion**.

### 9.3. Using a JSON Tree at the Boundary When Strict Contracts Are Needed

If a consumer must accurately check missing/null fields, numeric bounds, and timezones, use this approach:

1. Receive `TextMessage`/JSON `String`.
2. Parse via `ObjectMapper.readTree(...)`.
3. Validate requiredness, nullability, JSON types, decimal lexical format, timezone/instant, and range.
4. Convert into a DTO/domain object whose invariants are guaranteed.
5. Process business logic and commit/ack per configuration.

This is also why some systems deliberately use the default `String` ↔ `TextMessage` converter instead of binding straight into a record via the Jackson converter. Either choice is valid as long as the contract is fully controlled.

## 10. Runnable Project: Java 17 + Spring Boot 3.3 + Artemis

This hands-on app sends **three JSON documents** through a JMS queue, then parses and validates them with Jackson:

- Message 1 has `customerNote:null`.
- Message 2 **omits** `customerNote`.
- Message 3 has `customerNote:""` (empty string).

All three use the same `total="0.10"` and `occurredAt` in UTC. The program prints the three states while preserving `BigDecimal` and `Instant` precision. The example uses `JmsTemplate` with the default String/TextMessage converter to **control validation at the boundary** instead of relying on implicit deserialization.

### 10.1. Requirements

- JDK 17+, Maven, Docker.
- TCP port 61616 available.
- Artemis broker allowing use of the demo queue (default learning images usually auto-create).
- Development environment uses demo passwords; never use them in production.

Start the broker:

~~~bash
docker run --detach --rm --name contract-demo-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Wait for the broker to become ready. Check logs via `docker logs contract-demo-broker` if the client cannot connect.

Project structure:

~~~text
jms-contract-demo/
├── pom.xml
└── src/main/
    ├── java/example/jmscontract/JmsContractDemoApplication.java
    └── resources/application.properties
~~~

### 10.2. `pom.xml`

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>jms-contract-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-artemis</artifactId>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-json</artifactId>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Spring Boot 3.3.13 is pinned **to reproduce the Jakarta JMS/Spring 6 API demo**, not as a recommendation to use an end-of-life release as a production dependency. For real deployments, pick a supported Spring Boot/Jackson release and re-run integration tests against that version.

### 10.3. `application.properties`

~~~properties
spring.main.web-application-type=none
spring.artemis.mode=native
spring.artemis.broker-url=tcp://localhost:61616
spring.artemis.user=artemis
spring.artemis.password=artemis
spring.jms.template.receive-timeout=5s
~~~

This configures an external native broker; no HTTP server is needed. Without a custom `MessageConverter` bean declared, Spring Boot/`JmsTemplate` in this project uses the `String` ↔ `TextMessage` converter for `String` data.

### 10.4. `JmsContractDemoApplication.java`

~~~java
package example.jmscontract;

import java.math.BigDecimal;
import java.math.RoundingMode;
import java.time.Instant;
import java.util.UUID;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import jakarta.jms.ConnectionFactory;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.core.JmsTemplate;

@SpringBootApplication
public class JmsContractDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(JmsContractDemoApplication.class, args);
    }

    record ParsedEvent(
            String eventId,
            BigDecimal total,
            Instant occurredAt,
            String noteState) {}

    @Bean
    CommandLineRunner demonstrate(
            ConnectionFactory connectionFactory,
            ObjectMapper objectMapper) {

        return args -> {
            JmsTemplate jms = new JmsTemplate(connectionFactory);
            jms.setReceiveTimeout(5_000L);

            // Random queue name to avoid backlog from previous runs.
            String queue = "demo.contract." +
                    UUID.randomUUID().toString().replace("-", "");

            String explicitNull = """
                    {
                      "eventId": "e-1",
                      "schemaVersion": 1,
                      "total": "0.10",
                      "occurredAt": "2026-10-30T10:00:00Z",
                      "customerNote": null
                    }
                    """;

            String absent = """
                    {
                      "eventId": "e-2",
                      "schemaVersion": 1,
                      "total": "0.10",
                      "occurredAt": "2026-10-30T10:00:00Z"
                    }
                    """;

            String empty = """
                    {
                      "eventId": "e-3",
                      "schemaVersion": 1,
                      "total": "0.10",
                      "occurredAt": "2026-10-30T10:00:00Z",
                      "customerNote": ""
                    }
                    """;

            jms.convertAndSend(queue, explicitNull);
            jms.convertAndSend(queue, absent);
            jms.convertAndSend(queue, empty);

            for (int i = 0; i < 3; i++) {
                Object incoming = jms.receiveAndConvert(queue);
                if (!(incoming instanceof String json)) {
                    throw new IllegalStateException(
                            "Expected JSON TextMessage");
                }

                ParsedEvent event = parseContract(
                        objectMapper, json);

                System.out.printf(
                        "%s | note=%s | amount=%s | at=%s%n",
                        event.eventId(),
                        event.noteState(),
                        event.total().toPlainString(),
                        event.occurredAt());
            }
        };
    }

    private static ParsedEvent parseContract(
            ObjectMapper mapper,
            String json) throws JsonProcessingException {

        JsonNode root = mapper.readTree(json);
        if (root == null || !root.isObject()) {
            throw new IllegalArgumentException(
                    "Payload must be a JSON object");
        }

        String id = requiredText(root, "eventId");
        JsonNode version = root.get("schemaVersion");
        if (version == null
                || !version.isIntegralNumber()
                || !version.canConvertToInt()
                || version.intValue() != 1) {
            throw new IllegalArgumentException(
                    "schemaVersion must be integer 1");
        }

        String moneyText = requiredText(root, "total");
        if (!moneyText.matches(
                "(0|[1-9][0-9]*)\\.[0-9]{2}")) {
            throw new IllegalArgumentException(
                    "total must have exactly two decimals");
        }
        BigDecimal money =
                new BigDecimal(moneyText)
                        .setScale(2, RoundingMode.UNNECESSARY);

        String timeText = requiredText(root, "occurredAt");
        if (!timeText.endsWith("Z")) {
            throw new IllegalArgumentException(
                    "occurredAt must be UTC ISO-8601");
        }
        Instant occurredAt = Instant.parse(timeText);

        String noteState;
        if (!root.has("customerNote")) {
            noteState = "missing";
        } else {
            JsonNode note = root.get("customerNote");
            if (note.isNull()) {
                noteState = "null";
            } else if (note.isTextual()) {
                noteState = note.textValue().isEmpty()
                        ? "empty" : "text";
            } else {
                throw new IllegalArgumentException(
                        "customerNote must be string or null");
            }
        }

        return new ParsedEvent(id, money, occurredAt, noteState);
    }

    private static String requiredText(
            JsonNode root, String field) {

        JsonNode value = root.get(field);
        if (value == null || !value.isTextual()
                || value.textValue().isBlank()) {
            throw new IllegalArgumentException(
                    "Missing or invalid text field: " + field);
        }
        return value.textValue();
    }
}
~~~

### 10.5. Running and Expected Stdout

From the directory containing `pom.xml`:

~~~bash
mvn spring-boot:run
~~~

With the broker running, queue auto-creation enabled, and no competing consumers, the lines printed **by `System.out.printf` in the program** are:

~~~text
e-1 | note=null | amount=0.10 | at=2026-10-30T10:00:00Z
e-2 | note=missing | amount=0.10 | at=2026-10-30T10:00:00Z
e-3 | note=empty | amount=0.10 | at=2026-10-30T10:00:00Z
~~~

Spring Boot/provider logs may appear before or after. The demo uses a random queue and a single synchronous consumer to avoid leftover messages from prior runs. If the broker is not ready, auto-create permission is missing, or receive times out, the program fails rather than producing the expected stdout.

Stop the container when done:

~~~bash
docker stop contract-demo-broker
~~~

### 10.6. What to Observe

1. For the same `customerNote` field, the program preserves **three states** because it parses `JsonNode` before binding.
2. Decimal `"0.10"` travels over JMS as a JSON `TextMessage` and becomes `BigDecimal`; `toPlainString()` stays `"0.10"`, with no `double` error.
3. `occurredAt` parses into a UTC `Instant`, independent of the JVM's default timezone.
4. `schemaVersion` is validated as JSON integer `1`; string `"1"` is not silently accepted.
5. `total` requires exactly 2 digits after the decimal point; `null`, missing, floating numbers, and pattern-violating strings are explicitly rejected.
6. If replacing `String` with a Java record in `JmsTemplate.convertAndSend` without configuring a JSON converter, the behavior will no longer match this example automatically; the default converter cannot convert arbitrary records.
7. Producer/consumer still use a **JMS queue**, while contract validation is the application code's responsibility.

### 10.7. Extending the Demo to See Errors Caught

Try replacing one JSON string in the example with:

~~~json
{
  "eventId": "e-invalid",
  "schemaVersion": "1",
  "total": 0.10,
  "occurredAt": "2026-10-30 10:00:00"
}
~~~

The validator rejects it because `schemaVersion` is not a JSON integer; if you fix the version, it next catches that `total` must be a string; fixing that reaches the time format error. Sequential validation does not mean the remaining errors do not exist.

Try these values:

- `total="0.1"`: rejected because one decimal digit is missing per the lexical contract.
- `total="0.10"`: valid, `BigDecimal` retains scale 2.
- `total=0.10`: rejected because the wire contract requires a `String`, without silent coercion.
- `total=null` or missing: rejected.
- `customerNote=""`, `null`, or missing: three distinct valid states.
- `customerNote=0`: rejected due to wrong type.
- `occurredAt="2026-10-30T10:00:00Z"`: valid.
- `occurredAt="2026-10-30T10:00:00"`: rejected due to missing `Z`/offset, making timezone unknown.
- `schemaVersion=2`: rejected until producer/consumer agree on a v2 contract.

This sample contract is intentionally strict for clear observation. No JMS rule forces every application to store decimals as Strings or require `Z` on event times; each application decides and tests its own rules.

## 11. Designing Schema Evolution Without Breaking Old Consumers

Producers and consumers may deploy out of sync. Any change involving nulls, numbers, and timestamps can become a breaking change.

### 11.1. Adding a New Field

For example, v1 lacks `couponCode`, and v2 adds:

~~~json
{
  "schemaVersion": 2,
  "eventId": "evt-0043",
  "couponCode": null
}
~~~

Consumer v1 can ignore unknown fields if the contract permits. Consumer v2 must distinguish missing in v1 data from explicit `null` in v2 data if semantics differ. Not every service must upgrade simultaneously, yet a compatibility matrix is required.

### 11.2. Changes Prone to Breaking Consumers

| Change | Risk | Mitigation |
| --- | --- | --- |
| optional → required | Old messages lack the field; new consumers reject | Version-based default, two-step rollout, or schema v2. |
| nullable → non-null field | Old data contains explicit nulls | Migration/compatibility policy; never "coerce" silently. |
| JSON number → string | Old parsers/selectors/schemas see wrong type | Version the contract; never mix wire types in one version. |
| `int` → `long` | Consumers or JS `Number` may lack range | Test bounds and publish numeric range. |
| `double` → `decimal` | Alters precision and rounding rules | Use decimal strings/minor units with explicit migration. |
| local datetime → UTC `Instant` | Different semantics, potential timezone shift | Version and perform verified conversion at the source. |
| timestamp seconds → milliseconds | 1,000x magnitude shift | Rename field with unit or bump `schemaVersion`. |
| `null` → omitted by `NON_NULL` | Clear command lost in patches | Change serialization policy or use tri-state wrapper. |

### 11.3. Safe Rollout Procedure

1. **Define v2**: keep v1 untouched; document the new schema with nullability/range/time formats.
2. **Consumers first**: deploy consumers reading v1 and v2; test with real v1/v2 payloads.
3. **Producers second**: begin sending v2 once all consumers are compatible.
4. **Monitor**: metrics by `schemaVersion`, parse errors, dead-letter queues, lag/backlog; never lump everything into "JMS error".
5. **Retire v1 safely**: inspect queued backlogs, durable subscriptions, and replay streams before dropping v1.

For messages sitting in queues for days, schema backward compatibility is often more critical than synchronous REST payloads that live only for one request.

## 12. Validation, Exceptions, and Retries in Consumers

### 12.1. Distinguishing Contract Errors from Transient Errors

| Error | Typical Category | Appropriate Action |
| --- | --- | --- |
| Missing required field | Permanent contract error | Never infinitely retry the same payload; route to DLQ/quarantine and alert producer. |
| Explicit null on non-nullable field | Permanent contract error | Report contract violation; preserve message for investigation. |
| Malformed decimal, overflow | Permanent contract error | Reject and log reason/correlation ID. |
| Timestamp missing timezone | Permanent contract error or migration | Version-based handling; never guess a timezone. |
| Temporary broker/network outage | Transient transport failure | Retry/reconnect per container/provider settings. |
| Database temporarily unavailable | Transient dependency failure | Retry with backoff, idempotency, and deadline. |
| Business state already changed | Domain conflict | Domain-specific policy: ignore, compensate, alert, or reject. |

In `@JmsListener`, parse/validation exceptions can affect transactions, acknowledgements, and redelivery depending on listener container/broker settings. If a **permanently invalid** message repeatedly rolls back without a retry limit, the system enters a poison-message loop.

Explicitly decide:

- Max delivery attempts and backoff.
- DLQ/quarantine retaining `MessageID`, `eventId`, `schemaVersion`, and validation reason.
- Reprocessing workflow after fixing the producer/parser.
- Masking/redaction when logging payloads containing PII or tokens.
- Idempotency on replay/redelivery; never use `JMSMessageID` as a business ID if an event can be republished.

### 12.2. Never Silently Patch Bad Payloads with Default Coercion

For example, JSON sends `quantity="0"` instead of numeric `0`:

~~~json
{"quantity":"0"}
~~~

If the contract mandates an integer, the consumer should not silently accept strings unless an official backward-compatibility rule exists. Likewise, an `occurredAt` lacking an offset must never be assigned the server's current timezone automatically. Coercion lets things "slip through", yet causes services to interpret data differently in hard-to-detect ways.

## 13. Producer-Consumer Contract Testing

### 13.1. Essential Test Matrix

| Field | Input | Expected Outcome |
| --- | --- | --- |
| Required `eventId` | Missing/null/`""` | Reject with clear reason. |
| Optional `customerNote` | Missing | Record `absent` state. |
| Optional `customerNote` | Explicit `null` | Record `null` state. |
| Optional `customerNote` | Empty string | Record empty value; do not equate with `null`. |
| `quantity` | `0` | Valid or invalid per business rules; never equate with missing. |
| `quantity` | `"2"` | Reject if contract mandates JSON integer. |
| `quantity` | `2147483648` | Reject if Java `int`/range exceeded. |
| `total` | `"0.10"` | Parse exact `BigDecimal`, preserving scale. |
| `total` | `0.1` / `null` / missing | Reject if wire contract requires `String`. |
| `total` | `"-1.00"`, `"1e3"`, `"1.234"` | Reject per canonical non-negative 2-decimal policy. |
| `occurredAt` | UTC ISO-8601 with `Z` | Parse into `Instant`; invariant across JVM timezones. |
| `occurredAt` | Local datetime without offset | Reject if contract specifies UTC instant. |
| `occurredAtEpochMs` | milliseconds | Do not confuse with seconds. |
| `schemaVersion` | `1` / `2` / `"1"` | Route right version; reject unsupported versions or types. |
| Message property `SchemaVersion` | `int` / `String` | Selector matches only under the agreed type. |
| replay/redelivery | Same `eventId` | Side effect executes only once per idempotency policy. |

### 13.2. Required Testing Levels

- **Unit tests** for `JsonNode` validation, `BigDecimal`, `Instant`, missing/null/zero.
- **Serialization round-trip tests**: producer object → JSON → consumer DTO, verifying semantics.
- **Golden message fixtures**: versioned sample JSON shared across test suites in multiple services/languages.
- **Broker integration tests**: real `JmsTemplate`/`MessageConverter`, sending to a Queue, receiving and verifying headers/properties/body.
- **Compatibility tests**: new consumer reads old events; old consumer reads new messages if backward/forward compatibility is required.
- **DST/timezone tests**: run under different JVM timezones to verify `Instant`/`LocalDate` values never shift.
- **Retry/DLQ tests**: permanently malformed messages do not stall the queue and are handled per policy.

Even with a schema registry/JSON Schema, schema validation is necessary yet **insufficient** for business rules such as `amount >= 0`, currency scale, deadlines, or state transitions.

## 14. Checklist for Designing a Reliable Contract

1. Identify the message kind (event/command/snapshot/patch) and each field's semantics.
2. Build a table of required, nullable, optional; state whether missing differs from explicit null.
3. Decide whether zero, `false`, `""`, and `[]` are valid values or should be rejected.
4. Never let Java primitive defaults mask unsent required fields.
5. For money, choose `BigDecimal`/decimal string/minor units and enforce scale/range bounds.
6. For IDs, use `String` when arithmetic is unnecessary; prevent precision loss in JavaScript consumers.
7. Choose `Instant`/`OffsetDateTime` for absolute timestamps; `LocalDate` for date-only values.
8. For epoch timestamps, document seconds vs. milliseconds, timezone, and precision.
9. Separate `JMSTimestamp`/`JMSExpiration` from `occurredAt`/`businessDeadline`.
10. Configure `MessageConverter` and `ObjectMapper` consistently, checking target type and type-id property.
11. Avoid applying `NON_NULL`/`NON_EMPTY` globally if the contract relies on explicit nulls.
12. Validate immediately on receive before applying side effects; separate contract errors from infrastructure errors.
13. Version payloads, keep fixtures, and test reading older messages sitting in queues.
14. Use idempotency keys, auditing, monitoring, and DLQ/quarantine for invalid messages.
15. Test the exact wire format through a real JMS broker, not only object serialization/deserialization in unit tests.

## 15. Self-Check Questions

**1. How do missing and null differ?** Missing means the key does not exist; explicit null means the key is present with JSON `null`. Business meaning depends on event/patch type and the contract.

**2. Why is `int quantity` unsuitable for detecting whether a field was omitted?** Because its default can be `0`, colliding with a valid value; validate presence/type before binding or use a suitable wrapper.

**3. Is `total=0` the same as `total=null`?** No. Zero is a numeric value; null is the absence of a value.

**4. Why use `BigDecimal` instead of `double` for money?** To avoid binary floating-point representation errors when exact decimal arithmetic is needed.

**5. Are `BigDecimal("10.0")` and `BigDecimal("10.00")` equal under `equals`?** No, `equals` compares scale as well. `compareTo` shows they are numerically equal.

**6. Does `LocalDateTime` represent an absolute instant?** No. It lacks a zone/offset; representing an absolute instant requires timezone information or `Instant`.

**7. Is epoch `1_700_000_000` in seconds or milliseconds?** You cannot tell from the name `timestamp` alone. The contract must state the unit; `ofEpochSecond` and `ofEpochMilli` yield vastly different dates.

**8. Can JMS `MapMessage` send `BigDecimal` or `Instant` directly?** Not under the standard type set. Use `String`, primitives/integer units, or a JSON payload depending on the contract.

**9. Does `MappingJackson2MessageConverter` create a `TextMessage` by default?** No. In Spring Framework 6.x, the default target type is `BytesMessage`; call `setTargetType(MessageType.TEXT)` if `TextMessage` is needed.

**10. Why can adding `@JsonInclude(NON_NULL)` break a patch contract?** Because it strips explicit nulls from JSON, preventing consumers from distinguishing them from missing keys.

### Exercises

1. Run the Section 10 example and demonstrate that `note=null`, `note=missing`, and `note=empty` print differently.
2. Change `total` to JSON number `0.10`; explain why the validator rejects it despite being mathematically identical.
3. Write a contract variant storing `amountMinor=10`, `currency=USD`, `scale=2`; convert it to `0.10` using `BigDecimal`.
4. Create JSON with `quantity="2"` and then fix it to `quantity=2`; write a unit test confirming the wrong type is rejected.
5. Test `occurredAt` missing `Z`, with `+07:00` offset, and `LocalDateTime` without timezone; note which cases the contract accepts.
6. Create a DTO with `int quantity`, deserialize missing and explicit null under different Jackson configs; explain the risk.
7. Send a `MapMessage` with `quantity=0`, then use `itemExists`/`getInt` to distinguish an existing field from an absent field.
8. Configure `MappingJackson2MessageConverter` with `TEXT` + `PayloadType`, send and receive a valid DTO, then test a missing type-id property.
9. Build a backward-compatibility matrix for v1 lacking `customerNote` and v2 having explicit `null`.
10. Simulate a poison message with `total="invalid"` inside a transacted listener, and design a safe retry limit and quarantine.

## 16. References

- Jakarta Messaging 3.1 specification — Message bodies, MapMessage type conversions, properties: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging — MapMessage API: https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/mapmessage
- Spring Framework 6.2 — Sending a Message / Using JMS Message Converters: https://docs.spring.io/spring-framework/reference/6.2/integration/jms/sending.html
- Spring Framework 6.2 — MappingJackson2MessageConverter: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html
- Spring Framework 6.2 — JmsTemplate API: https://docs.spring.io/spring-framework/docs/6.2.14/javadoc-api/org/springframework/jms/core/JmsTemplate.html
- Jackson Databind JsonNode: https://fasterxml.github.io/jackson-databind/javadoc/2.17/com/fasterxml/jackson/databind/JsonNode.html
- Jackson JavaTimeModule: https://github.com/FasterXML/jackson-modules-java8
- Java 17 — BigDecimal: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/math/BigDecimal.html
- Java 17 — Instant, OffsetDateTime, LocalDate: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/time/Instant.html
- Spring Boot 3.3.13 release (demo version): https://spring.io/blog/2025/06/19/spring-boot-3-3-13-available-now/
- Apache ActiveMQ Artemis — Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
