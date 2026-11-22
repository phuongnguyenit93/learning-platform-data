# Field names, data types, default values, and unknown properties

When upgrading the JDK, serialization frameworks, communication libraries, or storage formats, a seemingly small change can break data already consumed by other systems. Renaming a Java field can unintentionally rename a JSON property. Switching a number from integer to string can break consumers. Adding a required field without a default renders old payloads unreadable. Conversely, ignoring every unknown property may help compatibility with newer versions yet also hide bugs or create data vulnerabilities.

This lesson belongs to **Java Advance Compatibility Migration**, chapter **Data and protocols**. The focus is four schema evolution dimensions: **field names**, **data types**, **default values**, and **unknown properties**. The content is framed in the context of Java DTOs, JSON/Jackson, REST, events, Protobuf, Avro, and databases. The overarching principle: **Java class structure is not identical to the data contract on the wire or in storage**.

## 1. Real-world problem when two versions coexist

Suppose the old application writes:

~~~json
{
  "orderId": "ORD-001",
  "total": 125000,
  "status": "PAID"
}
~~~

After a Java modernization effort, the new producer sends:

~~~json
{
  "orderId": "ORD-001",
  "totalAmount": "125000.00",
  "currency": "VND",
  "status": "SETTLED",
  "traceId": "abc-123"
}
~~~

Although both payloads describe an order, they no longer share the same contract. An old consumer may:

- Fail to find total because the name changed to totalAmount.
- Reject totalAmount because the type changed from number to string.
- Not recognize the enum SETTLED.
- Lack currency in historical data.
- Throw an error upon encountering the undeclared property traceId.

A real-world system also has many consumer groups: legacy Java applications, un-updated mobile apps, partner plugins, batch jobs re-running historical data, and non-Java systems. Therefore, schema compatibility must be viewed in terms of **producers and consumers**, not only a single current build.

## 2. Two compatibility directions: new reader and old reader

To avoid terminology differences across schema registries, we clearly describe two directions:

- **New reader reads data written by old writer:** a need commonly called backward compatibility.
- **Old reader reads data written by new writer:** a need commonly called forward compatibility.
- **Both directions can read:** full compatibility within the committed version range.

~~~text
Writer V1  ---- payload V1 ----> Reader V2
   |                                    |
   +---------- reads old data ----------+

Writer V2  ---- payload V2 ----> Reader V1
   |                                    |
   +---------- reads new data -----------+
~~~

A system with rolling deployments or long event retention typically requires a new reader to read old data. If mobile clients or partners cannot upgrade synchronously, it also needs old readers to read payloads produced by new writers.

| Change | New reader reads old writer | Old reader reads new writer |
|---|---|---|
| Add optional field | Usually easy if default/nullable is reasonable | Depends on unknown fields configuration |
| Add required field | Risk of error because old payload lacks it | Depends on how old reader handles unfamiliar fields |
| Remove field | New reader must drop requirement or have fallback | Old reader may lack information |
| Rename field | Needs alias/mapping or migration | Needs dual-write/alias at consumer |
| Change number type to string | Risk of parse failure | Risk of parse failure |
| Add enum value | New reader usually knows it | Old reader may reject |
| Add unknown property | New reader understands or ignores it | Old reader may be strict |

The table only describes common risks. JSON, Protobuf, Avro, databases, and serialization libraries have different practical rules.

## 3. Java field names and wire names are not one and the same

Field names in Java may be determined by fields, getters/setters, annotations, record components, constructor parameters, or naming strategies. The name on the wire is decided by the serializer and schema.

For example:

~~~java
public final class Order {
    private String customerId;

    public String getCustomerId() {
        return customerId;
    }

    public void setCustomerId(String value) {
        customerId = value;
    }
}
~~~

With a typical Jackson configuration, the data might be:

~~~json
{"customerId":"CUS-001"}
~~~

If the field/getter is refactored to clientId, a convention-based serializer may write:

~~~json
{"clientId":"CUS-001"}
~~~

This is a breaking change for consumers looking for customerId.

### 3.1. Keeping wire names stable with @JsonProperty

~~~java
import com.fasterxml.jackson.annotation.JsonProperty;

public final class OrderDto {
    @JsonProperty("customerId")
    private String clientIdentifier;

    public String getClientIdentifier() {
        return clientIdentifier;
    }

    public void setClientIdentifier(String value) {
        clientIdentifier = value;
    }
}
~~~

The name in source can change while the wire contract keeps customerId. Verify Jackson configuration if getters, setters, constructors, and fields have inconsistent annotations.

### 3.2. Accepting both old and new names with @JsonAlias

~~~java
import com.fasterxml.jackson.annotation.JsonAlias;
import com.fasterxml.jackson.annotation.JsonProperty;

public final class OrderDto {
    @JsonProperty("customerId")
    @JsonAlias("clientId")
    private String customerIdentifier;

    public String getCustomerIdentifier() {
        return customerIdentifier;
    }

    public void setCustomerIdentifier(String value) {
        customerIdentifier = value;
    }
}
~~~

In a suitable configuration:

- The reader accepts customerId.
- The reader also accepts clientId.
- The serializer continues using the primary name customerId.

**@JsonAlias mainly supports deserialization; it does not automatically write two names.** If dual-write is needed, that representation must be designed and the deprecation order for the old field determined.

### 3.3. When both names appear together

~~~json
{
  "customerId": "CUS-001",
  "clientId": "CUS-999"
}
~~~

This is an ambiguous payload. If the system has aliases, decide clearly whether to reject when two names conflict or prioritize one name. Do not let property ordering implicitly determine the value for an important field. For sensitive data, rejecting conflicts may be the safe choice.

### 3.4. Global naming strategies are also contracts

If an ObjectMapper switches from camelCase to snake_case, orderId may be written as order_id. Global changes can affect many APIs/events simultaneously. Separate Java refactoring from schema changes and override specific names when compatibility needs to be kept.

## 4. Renaming via the expand–migrate–contract process

A controlled way to transition field names:

**Expand:** New readers accept both oldName and newName, while writers still write oldName so old readers continue working.

**Migrate:** Update each producer/consumer. If needed, writers temporarily write both names and consumers check for conflicts rather than accidentally reading twice.

**Contract:** After verifying no old consumers remain and historical data has been handled, retire support for oldName per policy.

~~~text
V1: writer -> customerId; reader -> customerId
V2: writer -> customerId; reader -> customerId or clientId
V3: writer -> customerId + clientId; reader -> both
V4: writer -> clientId; reader -> clientId
~~~

This is an illustrative roadmap. In public APIs with many consumers, keeping the old wire name permanently is sometimes safer and cheaper than renaming. Event data stored for years may still require readers to accept schema V1 after production is already on V4.

## 5. Wire data types differ from Java types

JSON distinguishes object, array, string, number, boolean, and null. Java has many more specific types:

- byte, short, int, long, float, double.
- BigDecimal and BigInteger.
- String, UUID, char.
- LocalDate, LocalDateTime, OffsetDateTime, Instant.
- Enum.
- List, Set, Map, Optional.
- Record and POJO.
- byte[] and binary data.

One Java type can be serialized into different wire types depending on configuration. For example, Instant can become an ISO-8601 string or an epoch number.

Do not infer two schemas are compatible merely because the Java compiler has an implicit conversion between two types.

### 5.1. int to long

In Java, int can widen to long. However:

- Old JSON readers may still map into int.
- New values outside int range will cause overflow or parse errors.
- INT database columns may not hold them.
- Consumers in other languages have different limits.
- Protobuf/Avro have their own type compatibility rules.

To increase numeric limits, test max/min values and review the entire storage pipeline.

### 5.2. Java long with JavaScript Number

Java long represents a signed 64-bit integer. Regular JavaScript Number only represents integers accurately in the range −(2^53−1) to 2^53−1.

The payload:

~~~json
{"transactionId":9007199254740993}
~~~

can lose precision in JavaScript consumers using Number. If transactionId is an identifier, a string may be more suitable:

~~~json
{"transactionId":"9007199254740993"}
~~~

However, number → string is still a breaking wire change. Versioning, consumer migration, or time-bound parallel fields are needed.

### 5.3. Currency and BigDecimal

Do not use float/double for data requiring exact decimal numbers unless appropriate error rules exist.

~~~java
import java.math.BigDecimal;

BigDecimal subtotal = new BigDecimal("125000.25");
BigDecimal tax = subtotal.multiply(new BigDecimal("0.10"));
~~~

Specify:

- JSON number or string?
- Precision, scale, and rounding mode?
- Monetary unit, currency?
- Are negative amounts allowed?
- Is scientific notation accepted?
- Are minor units (dong, cents) used instead of decimals?

Two representations not equivalent in JSON type:

~~~json
{"amount":125000.25}
~~~

~~~json
{"amount":"125000.25"}
~~~

Parsers may have coercion mechanisms, yet do not rely on them as a compatibility contract.

### 5.4. Boolean and string

~~~json
{"enabled":false}
~~~

~~~json
{"enabled":"false"}
~~~

do not have the same type. One mapping library may convert "false" to a boolean, while another library may reject it. For security requests, strict parsing usually catches configuration mistakes more easily than silent auto-coercion.

## 6. Time, timezones, and timestamp units

A legacy system may use java.util.Date or epoch milliseconds, while new code uses java.time.Instant or OffsetDateTime.

For example:

~~~json
{"createdAt":"2026-11-12T09:30:00Z"}
~~~

and:

~~~json
{"createdAt":1794475800000}
~~~

have different wire types. When migrating, clearly state:

1. Is the epoch in seconds, milliseconds, or microseconds?
2. Does the value carry a timezone/offset?
3. Is it normalized to UTC?
4. What precision is allowed?
5. Does the user's timezone need to be preserved?
6. How is daylight saving time handled?
7. Does historical data exist without a recorded timezone?

Instant represents a point on the timeline; LocalDateTime is a local date and time **without an offset/zone**. Converting LocalDateTime to Instant requires a ZoneId/offset. If taking the server's default timezone, results can change when deploying to another region.

For cross-system event timestamps, define representations with explicit offsets/UTC. For meeting schedules or opening hours, local time with business timezone may be needed.

## 7. New enums and values outside the known set

A new producer may emit:

~~~json
{"status":"PENDING_REVIEW"}
~~~

while an old Java reader only has:

~~~java
public enum OrderStatus {
    NEW,
    COMPLETED
}
~~~

Depending on the library, the deserializer may throw an error upon encountering PENDING_REVIEW. If configured to map unknown enums to null, business logic may fail later when using the enum.

One option is adding UNKNOWN:

~~~java
public enum OrderStatus {
    NEW,
    COMPLETED,
    UNKNOWN
}
~~~

With Jackson, @JsonEnumDefaultValue and READ_UNKNOWN_ENUM_VALUES_USING_DEFAULT_VALUE configuration can be used in supported versions. However, the fallback must have clear business semantics.

**UNKNOWN does not equal NEW.** If a new status indicates an order awaiting moderation, processing it as NEW can corrupt the workflow. A consumer may need to reject or route the event to a separate handling path to preserve correctness.

Similarly, Java switch expressions can run into issues when an enum is expanded and code lacks appropriate handling. Test old consumers with new enum values rather than checking only the schema.

## 8. Missing, null, empty, and default are not the same

The following payloads can carry different meanings:

~~~json
{}
~~~

~~~json
{"name":null}
~~~

~~~json
{"name":""}
~~~

~~~json
{"count":0}
~~~

~~~json
{"enabled":false}
~~~

| State | Possible meaning in contract |
|---|---|
| Property missing | Not sent; use default; keep old value in PATCH |
| Property null | Clear value; unknown; or invalid data |
| Empty string | Intentionally a zero-length string |
| Number 0 | Explicit numeric value |
| Boolean false | Explicit negation |

Do not conflate missing, null, and false if business logic needs to distinguish them.

### 8.1. Java primitives and JVM-created defaults

~~~java
public final class Flags {
    public int retries;
    public boolean enabled;
}
~~~

A new instance of Flags has retries = 0, enabled = false. If JSON lacks those two properties, no-arg + field-assignment deserializers typically leave the corresponding defaults.

However, 0 or false does not tell whether the client sent it intentionally or simply omitted the field. If distinguishing is needed, primitives are insufficient to represent presence.

### 8.2. Wrappers do not completely solve missing vs null

~~~java
public final class Flags {
    public Integer retries;
    public Boolean enabled;
}
~~~

Integer/Boolean can hold null, yet a simple DTO still fails to distinguish a missing property from an explicitly null property if both map to null.

When handling PATCH, a three-state data type may be needed:

~~~text
UNSET -> field omitted, keep old data
NULL  -> null sent, request deletion
VALUE -> new value sent
~~~

JsonNode can be used to check presence, or JSON Merge Patch/JSON Patch, or a dedicated wrapper. Describe exact semantics in the API contract.

### 8.3. Clear PATCH handling example

~~~java
import com.fasterxml.jackson.databind.JsonNode;

public void applyPatch(JsonNode patch, Customer customer) {
    if (!patch.has("name")) {
        return;
    }

    JsonNode value = patch.get("name");

    if (value.isNull()) {
        customer.clearName();
    } else if (value.isTextual()) {
        customer.setName(value.asText());
    } else {
        throw new IllegalArgumentException(
            "name must be string or null");
    }
}
~~~

Customer is an illustrative domain API. The key point is that absence and explicit null lead to two different actions.

## 9. Default values when adding fields

V1:

~~~json
{
  "orderId": "ORD-001",
  "items": 2
}
~~~

V2:

~~~json
{
  "orderId": "ORD-001",
  "items": 2,
  "priority": "NORMAL"
}
~~~

Reader V2 needs a way to read V1 without priority. Options:

- Default to NORMAL if accurate for V1 data.
- Allow null/UNKNOWN and require business logic to handle it.
- Perform data backfill before enabling V2 processing.
- Use schema defaults in formats that support them.
- Version if V1 cannot be interpreted safely.

A good default must satisfy:

1. Agreed upon in meaning by producer and consumer.
2. Does not lose unknown information if that information is important.
3. Distinguishes missing from explicit null if the contract requires it.
4. Does not depend on uncontrolled timezones/environments.
5. Tested with historical data.
6. Does not fabricate sensitive information such as permissions or currency.

For example, currency = USD is not a safe default if old orders did not record currency and could belong to multiple currencies.

### 9.1. Initializer and constructor defaults

~~~java
public final class RetryConfig {
    public int attempts = 3;
    public boolean enabled = true;
}
~~~

If the deserializer constructs the object via a no-arg constructor, missing properties can retain initializer values. Yet explicit attempts = 0 typically overwrites it to 0. Null-handling configuration may differ, and creator-based deserialization has its own behavior.

When upgrading Jackson or converting POJOs to records, re-test payloads missing fields to confirm actual defaults.

## 10. Jackson: unknown properties in JSON

An old reader:

~~~java
public final class CustomerDto {
    public String id;
    public String name;
}
~~~

receives a new payload:

~~~json
{
  "id": "CUS-001",
  "name": "An",
  "preferredLocale": "vi-VN"
}
~~~

If Jackson has FAIL_ON_UNKNOWN_PROPERTIES enabled, it may throw UnrecognizedPropertyException.

### 10.1. Ignoring unknown per DTO

~~~java
import com.fasterxml.jackson.annotation.JsonIgnoreProperties;

@JsonIgnoreProperties(ignoreUnknown = true)
public final class CustomerDto {
    public String id;
    public String name;
}
~~~

In typical Jackson configuration, the reader can read id/name and ignore preferredLocale.

### 10.2. Configuring on ObjectMapper

~~~java
import com.fasterxml.jackson.databind.DeserializationFeature;
import com.fasterxml.jackson.databind.ObjectMapper;

ObjectMapper mapper = new ObjectMapper();

mapper.configure(
    DeserializationFeature.FAIL_ON_UNKNOWN_PROPERTIES,
    false
);
~~~

This can affect many DTOs sharing the same mapper. Do not disable strictness globally just to handle one compatibility error.

For example, a client sends by mistake:

~~~json
{"isAmin":true}
~~~

If isAdmin was expected yet the name has a typo, a reader ignoring unknowns can make the caller think the request was applied. For data involving authorization, payments, or security configuration, rejecting unknown fields is usually more appropriate.

### 10.3. Choosing policy by context

| Data | Potentially suitable policy |
|---|---|
| Event producer upgraded before consumer | Ignore unknown per contract |
| Command API with strict validation | Reject unknown to detect errors |
| Partner changes payload frequently | Ignore or whitelist with monitoring |
| Permission/security configuration | Strict parsing and validation |
| Data requiring lossless round-trip | Bounded preserve unknown |
| Untrusted public payload | Size/depth limits and allowlist |

There is no single right configuration for every endpoint. “Tolerant reader” is only useful when it does not compromise correctness or safety.

## 11. Preserving unknown fields for round-trip

When a service reads and then writes a payload back out, ignoring unknown makes unfamiliar fields **disappear** upon re-serialization.

For example, V2 sends:

~~~json
{
  "id": "CUS-001",
  "name": "An",
  "preferredLocale": "vi-VN"
}
~~~

A reader that understands only id/name yet acts as a forwarding service needs to preserve preferredLocale. An extension map can be used:

~~~java
import com.fasterxml.jackson.annotation.JsonAnyGetter;
import com.fasterxml.jackson.annotation.JsonAnySetter;
import com.fasterxml.jackson.databind.JsonNode;
import java.util.LinkedHashMap;
import java.util.Map;

public final class CustomerEnvelope {
    public String id;
    public String name;

    private final Map<String, JsonNode> extra =
        new LinkedHashMap<>();

    @JsonAnySetter
    public void putExtra(String key, JsonNode value) {
        extra.put(key, value);
    }

    @JsonAnyGetter
    public Map<String, JsonNode> getExtra() {
        return extra;
    }
}
~~~

In a suitable Jackson configuration, unknown properties can be stored in extra and written back out.

However, you need to control:

- Size and depth of extension data.
- Collisions between extra and defined properties.
- Sensitive fields that must not be logged/forwarded.
- Unfamiliar fields today can become official properties tomorrow.
- Whether round-trip preserves required formatting/precision.
- Rejection policies or namespace partitioning for untrusted properties.

Preserving unknowns is not a permitted way to bypass validation or authorization.

## 12. Java records and constructor binding

When modernizing code, a POJO may be converted into a Java record:

~~~java
public record UserView(
    String id,
    String displayName,
    int loginCount
) { }
~~~

Records use components and a canonical constructor. Deserialization frameworks may need to map data via the constructor, unlike POJOs with a no-arg constructor and setters.

If an old payload lacks loginCount:

~~~json
{"id":"U-001","displayName":"An"}
~~~

check the Jackson version and creator/missing/null configuration. Some configurations supply primitive default 0; strict modes may reject.

### 12.1. Compact constructor to protect invariants

~~~java
public record UserView(
    String id,
    String displayName,
    int loginCount
) {
    public UserView {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id is required");
        }
        if (loginCount < 0) {
            throw new IllegalArgumentException(
                "loginCount cannot be negative");
        }
    }
}
~~~

Validation prevents the object from taking an invalid state, yet does not solve whether missing loginCount means 0 or UNKNOWN. If the contract must distinguish them, a DTO/schema with presence is needed.

Do not change a Java DTO from a class to a record and change field names/types in the same pass if they can be separated to isolate errors easily.

## 13. Optional and nullable DTOs

Optional<T> in Java APIs helps represent a present or absent result. However, Optional placed as a JSON DTO field does not automatically represent the three states missing, null, and value.

Depending on Jackson version, Jdk8Module, and inclusion settings, Optional.empty may serialize differently. If stable payloads are required, configure and test specifically.

When an API performs partial updates, use a dedicated DTO/command to express presence explicitly. Do not rely on null-checks to infer whether the client omitted the field or requested deleting data.

## 14. Database defaults differ from JSON defaults

A database schema:

~~~sql
ALTER TABLE orders
ADD COLUMN priority VARCHAR(16) DEFAULT 'NORMAL';
~~~

does not automatically ensure every Java object or JSON event has priority.

Many databases apply defaults when INSERT **omits the column** or specifies DEFAULT, yet explicit NULL can behave differently. ORMs sometimes send explicit null so DB defaults are not applied as developers expect.

There are also many boundaries:

- Historical data before migration.
- Snapshots and backups.
- Caches built with the old schema.
- Events published before adding the column.
- Old services still writing during rolling deployments.

### 14.1. Expand–migrate–contract for databases

1. Add the new column in a state readable alongside old code.
2. Deploy readers understanding both new and old schemas.
3. Backfill historical data if valid inference logic exists.
4. Deploy writers writing the new field.
5. Monitor consumers and jobs still using the old column.
6. Add NOT NULL/constraints and remove the old column when safe.

Java defaults, database defaults, and event schema defaults are three separate mechanisms. They must be aligned on **business meaning**, not assumed to take effect automatically across all layers.

## 15. Protobuf: field numbers matter more than names in binary

Protocol Buffers uses field numbers in the binary wire format.

~~~proto
syntax = "proto3";

message Order {
  string order_id = 1;
  int64 total_minor = 2;
  string currency = 3;
}
~~~

### 15.1. Do not reuse removed tags

If removing currency, reserve the tag/name to avoid a later schema using tag 3 for another meaning:

~~~proto
syntax = "proto3";

message Order {
  reserved 3;
  reserved "currency";

  string order_id = 1;
  int64 total_minor = 2;
}
~~~

Historical data may still contain tag 3. Reusing tags can cause misinterpretation.

### 15.2. Renaming in .proto differs from JSON renaming

Keeping field numbers and types can preserve partial binary compatibility. However, renaming can still break:

- Generated Java getters/setters.
- Protobuf JSON mapping.
- Reflection relying on descriptor names.
- Tooling and schema validation.

Do not say “renaming a Protobuf field is always safe”.

### 15.3. Unknown fields in Protobuf

Some Protobuf binary parsers/runtimes can preserve unknown fields when parsing and re-serializing. However, data can be lost when:

- Converting to Protobuf JSON and back.
- Manually mapping to domain DTOs that do not retain unknowns.
- Rebuilding messages solely from known fields.
- Using a runtime/option that discards unknowns.

Test the exact pipeline. Configuring ignoreUnknownFields on a Protobuf JSON parser does not mean unknown properties are preserved automatically.

### 15.4. Defaults and field presence

With proto3 scalar fields using implicit presence, defaults like 0, false, or empty strings cannot distinguish “field absent” from “field has default value”. Fields declared as optional under supported rules can provide explicit presence.

If a use case requires distinguishing missing from zero, design presence in the schema; do not expect Java primitives of generated classes to solve it automatically.

## 16. Avro: writer schema, reader schema, and defaults

Avro has a schema resolution mechanism between the written data's schema and the reader's schema.

Writer V1:

~~~json
{
  "type": "record",
  "name": "Order",
  "fields": [
    {"name": "orderId", "type": "string"}
  ]
}
~~~

Reader V2:

~~~json
{
  "type": "record",
  "name": "Order",
  "fields": [
    {"name": "orderId", "type": "string"},
    {"name": "priority", "type": "string", "default": "NORMAL"}
  ]
}
~~~

When reader V2 reads V1 data lacking priority, the default in the reader schema can be used to supply the value during resolution.

**Avro defaults are not simply an instruction for the writer to automatically write that field into every record.** Distinguish writer schema and reader schema.

### 16.1. Renaming via aliases

Avro supports aliases in some rename scenarios; compatibility also depends on the schema registry, version, and tooling. An alias on a new reader does not automatically make old readers understand a name written by a new writer.

### 16.2. Unions with null

~~~json
{
  "name": "description",
  "type": ["null", "string"],
  "default": null
}
~~~

Check defaults and union branch rules per the Avro spec/version used. A default incompatible with the schema is not a real solution for missing data.

### 16.3. Schema registries do not replace business tests

A registry can detect some schema changes violating compatibility policies, yet cannot know whether priority = NORMAL is right for last year's data, or which enums consumers hard-coded. Contract tests remain necessary.

## 17. JSON Schema and unknown-property policies

JSON Schema can define property names, required fields, types, value constraints, and policies for properties outside the list.

Strict example:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {"type": "string"},
    "quantity": {"type": "integer", "minimum": 0}
  },
  "required": ["orderId"],
  "additionalProperties": false
}
~~~

With additionalProperties: false, the validator can reject fields outside what the schema allows.

More open example:

~~~json
{
  "type": "object",
  "properties": {
    "orderId": {"type": "string"}
  },
  "required": ["orderId"],
  "additionalProperties": true
}
~~~

An open schema can help old readers accept new properties, yet also easily overlook typos. Decide by domain:

- Events may be designed for readers to ignore unknown fields.
- Command APIs or permission configurations may be strict.
- Extension metadata may live under an extensions namespace.
- Untrusted requests must have quotas and depth/size limits.
- For nested objects, open/closed policies must be reviewed at each level.

## 18. Nested objects and collections also evolve schemas

Changing:

~~~json
{
  "shipping": {
    "address": "123 Example St"
  }
}
~~~

to:

~~~json
{
  "shipping": {
    "address": {
      "line1": "123 Example St",
      "country": "VN"
    }
  }
}
~~~

changes shipping.address from a string to an object. Old consumers can fail even though the property name did not change.

Similarly:

~~~json
{"items":["A","B"]}
~~~

differs from:

~~~json
{"items":{"A":1,"B":1}}
~~~

Changing an array to a map alters ordering, duplicate semantics, and element types.

### 18.1. Null lists, empty lists, and missing lists

~~~json
{}
~~~

~~~json
{"items":null}
~~~

~~~json
{"items":[]}
~~~

can carry three meanings. Mapping all three to Collections.emptyList can lose information if business logic distinguishes “no list sent” from “intentionally empty list”.

### 18.2. Map keys

JSON object keys are strings. A Java Map may use UUID, Integer, or enum keys and the serializer converts them to text. When changing key types/naming, round-trips may become inconsistent. A multi-language API may choose an array of entries to represent complex keys via an explicit schema.

## 19. Unknown properties and mass assignment security

An endpoint receiving JSON and mapping it directly onto an entity can accidentally accept fields clients are not allowed to edit.

~~~json
{
  "displayName": "An",
  "role": "ADMIN",
  "accountLocked": false
}
~~~

If the system automatically copies every property from the request to the entity, it can create privilege escalation or modify security state.

Proper solution:

- Request DTOs contain only allowed fields.
- Validate and check authorization by caller.
- Map in a controlled manner from DTO to domain.
- Do not automatically copy unknown properties into entities.
- Do not use ignoreUnknownProperties as a permission guard.
- Reject undeclared sensitive fields when appropriate.

If preserving unknowns to forward, ensure unvetted raw data is not passed across a trust boundary to a higher-privileged service. Also limit object depth, property count, string length, array length, retention, and logging.

## 20. Historical data, replay, and schema versions

Event-driven systems may replay data years after the original producer changed:

~~~text
2023: Event V1 -> orderId, total
2024: Event V2 -> orderId, total, currency
2026: Event V3 -> orderId, totalMinor, currency, tax
~~~

A new reader may have to handle V1, V2, and V3 alike. If currency of old events was not stored, arbitrarily assigning VND or USD can make replay results differ from the original business logic.

### 20.1. Versioned payloads and upcasters

~~~json
{
  "schemaVersion": 1,
  "eventType": "OrderCreated",
  "payload": {
    "orderId": "ORD-001",
    "total": 125000
  }
}
~~~

A reader can apply representation conversion steps:

~~~text
Event V1
   |
   v
Upcast V1 -> V2
   |
   v
Upcast V2 -> V3
   |
   v
Domain handling V3
~~~

Upcasters need historical fixtures, repeatable logic, must not silently fabricate missing data, and must document which values are inferred. When using Protobuf/Avro and a schema registry, another schema ID attachment mechanism may exist; it is not necessary to manually add schemaVersion to every payload.

## 21. Requests, responses, and events have different compatibility directions

### 21.1. API requests

The client is the writer; the server is the reader. If a new server adds a required field, old clients cannot send it. Proper defaults, compatibility modes, or versioned endpoints are needed.

Unknown fields in requests can be typos or unsupported behavior, especially in security commands. Do not open schemas by default.

### 21.2. API responses

The server is the writer; the client is the reader. Adding a new field can usually be compatible if clients ignore unknowns. Removing or renaming fields can break old clients.

### 21.3. Events

The producer is the writer; the consumer is the reader. There may be multiple independent consumers and data retained in brokers long-term. Compatibility must consider retention, replay, and rollout order.

### 21.4. Databases

New and old applications may read/write a table concurrently during rolling deployments. Expand–migrate–contract is usually safer than renaming/dropping columns immediately.

## 22. Contract tests for multi-version data

Save a set of representative payload fixtures:

~~~text
fixtures/
  order-v1-minimal.json
  order-v1-full.json
  order-v2-optional.json
  order-v2-unknown-enum.json
  order-v3-unknown-fields.json
  order-invalid-null.json
  order-invalid-type.json
  order-large-integer.json
  order-old-timestamp.json
~~~

Fixtures can be synthetic data or scrubbed of sensitive information. Do not accidentally overwrite old fixtures with the new serializer's output; preserve evidence of the actual wire contract before migration.

### 22.1. Scenarios to test

- New reader reads payloads from old writer.
- Old reader reads new payloads within the supported scope.
- Missing fields receive proper defaults.
- Explicit null differs from absent when the contract requires it.
- Alias renames work; output does not change unexpectedly.
- Unknown fields are ignored/rejected/preserved per policy.
- Large numbers, negative numbers, precision/scale, and overflow.
- New enum values are handled safely.
- Timestamp units, offsets, and timezones.
- Nested objects and array/map element types.
- Schema migration and historical data replay.
- Unknown fields do not cause mass assignment.
- Oversized/overly deep payloads are bounded.
- Round-trip preserves fields that need preservation.

### 22.2. Reader–writer matrix

| Writer | Reader | Objective |
|---|---|---|
| V1 | V1 | Baseline |
| V1 | V2 | Read old data |
| V2 | V1 | Old reader still understands new data if committed |
| V2 | V2 | New behavior |
| V1 fixture | V3 | Historical replay |
| V3 malformed | V3 | Reject invalid data |

Not every system commits to every version pair. The matrix must reflect release policy, client lifecycles, and data retention duration.

## 23. Practical migration process

### Step 1 — Inventory contracts

Clearly record:

- Endpoint, topic, file format, or database table.
- Producers/consumers and running versions.
- JSON/Jackson, Protobuf/Avro, or other serializers.
- Java runtime and dependency versions.
- Schema registry/schema validation.
- Historical data requiring support.
- Cross-language clients or third-party plugins.

### Step 2 — Record the baseline

Save actual payloads for names, types, defaults, nullability, enums, timestamps, unknown fields, collections, and serialization options.

### Step 3 — Classify changes

| Property | Before | After | Risk |
|---|---|---|---|
| Name | customerId | clientId | Consumers lack old name |
| Type | int | long | Overflow in old readers |
| Required | Optional | Required | Old data lacks it |
| Default | null | NORMAL | Reinterpreting history |
| Enum | NEW, DONE | Add REVIEW | Old readers do not understand it |
| Unknown policy | Ignore | Reject | Forward compatibility reduced |
| Time | Epoch ms | ISO string | Parser and timezone |

### Step 4 — Choose compatibility direction

During rolling deployments, it is usually best to ensure new readers can handle old data **before** new writers emit new payloads. If old clients live long, also keep the direction where old readers understand new payloads.

### Step 5 — Apply appropriate mechanisms

- @JsonProperty to keep wire names.
- @JsonAlias on readers to support renames.
- Optional fields and meaningful defaults.
- New DTO/endpoint version for major contract changes.
- Schema compatibility of Avro/Protobuf/JSON Schema.
- Upcasters for historical events.
- Time-limited dual-read/dual-write.
- Database expand–migrate–contract.
- Bounded preserve unknown.
- Strict validation for sensitive commands.

### Step 6 — Run on the target JDK and dependencies

Upgrading Java, Jackson, Protobuf runtime, or Avro libraries can change coercion, property naming, null handling, and enum behavior. Test with the exact dependency graph and serializer configuration to be deployed.

Avoid simultaneously changing JDK, HTTP client, serializer, database schema, and wire contract if they can be separated to isolate errors.

### Step 7 — Deploy in order

1. Deploy readers capable of reading both old and new schemas.
2. Monitor clients/consumers still using the old format.
3. Deploy new writers or enable feature flags.
4. Monitor deserialization and business validation failures.
5. Backfill when reliable source data exists.
6. Remove fallbacks only after the support milestone.

### Step 8 — Monitor and roll back

Monitor:

- Unknown-field errors.
- Missing required-field errors.
- Type/coercion failures.
- Enum parsing failures.
- Dead-letter queues and consumer lag.
- Replay/backfill failures.
- Field loss during round-trip.
- Payload ratios by schema version.
- Anomalous business outcomes.

Rollback is not simply reverting to an old binary if a new writer already wrote data that old readers cannot understand. **Reader-first rollout** reduces that risk.

## 24. Common misconceptions

### “Renaming a Java field does not affect the API”

False if the serializer uses field/getter/record-component naming conventions. Keep wire names or version the schema.

### “Adding a JSON field is always safe”

Only if consumers have a suitable unknown policy and new readers do not require a field missing in old data.

### “The parser will automatically convert strings to numbers”

Do not rely on coercion. Newer configurations may be stricter, or data may exceed numeric ranges.

### “Missing and null are the same”

False for PATCH or contracts that need to distinguish “keep unchanged” from “delete”.

### “Defaults solve all legacy data”

Only when the default has accurate business meaning. A wrong default can fabricate nonexistent data.

### “Global ignore unknown is a best practice”

Not true. It can hide typos and invalid request fields.

### “Ignore unknown preserves data during round-trip”

False. Ignored fields are typically not written back out if the DTO is serialized again.

### “Renaming a Protobuf field does not break compatibility”

Binary tags may remain partially intact, yet generated source and JSON mapping can change.

### “Schema registry compatible means the system is safe”

Registries usually evaluate only schema rules, not enum logic, business defaults, authorization, or replay behavior.

### “JSON long is always accurate in every language”

Not true for consumers using JavaScript Number for large integers.

## 25. Compatibility decision profile template

~~~text
CONTRACT
  Endpoint/topic/table:
  Producer:
  Consumer(s):
  Data format:
  Schema and version:
  Serializer/version:
  Current and target JDK:

FIELD CHANGE
  Old wire name:
  New wire name:
  Old type:
  New type:
  Optional/required:
  Missing semantics:
  Explicit null semantics:
  Default and business meaning:
  Enum values:
  Unknown field policy:
  Historical retention:

COMPATIBILITY
  New reader / old writer:
  Old reader / new writer:
  Binary/schema compatibility:
  Generated API compatibility:
  Numeric/time constraints:
  Validation/security:
  Round-trip requirement:

MIGRATION
  Alias/dual-read:
  Dual-write:
  Backfill/upcaster:
  Reader-first rollout:
  Deprecation milestone:
  Rollback strategy:

VALIDATION
  Old/new fixtures:
  Missing and null cases:
  Unknown-field cases:
  Boundary/precision:
  Contract tests:
  Replay tests:
  Canary metrics:
~~~

The record should be saved alongside schemas and artifact versions so future Java upgrades do not have to guess at the meaning of defaults or legacy field names.

## 26. Summary

A stable data contract is not merely a set of Java field names and types. It encompasses wire names, value ranges, missing/null semantics, defaults, unknown-field behavior, and the ability to read data across different versions.

Principles to keep:

1. **Wire names:** Do not change unintentionally during Java refactoring.
2. **Data types:** Do not assume parsers can auto-convert while remaining correct.
3. **Defaults:** Apply only when business semantics are clear.
4. **Missing and null:** Distinguish when they affect updates, permissions, or state.
5. **Unknown fields:** Choose ignore, reject, or preserve per contract and security limits.
6. **Protocol-specific:** JSON, Protobuf, Avro, and databases have different compatibility rules.
7. **Reader–writer tests:** Verify coexisting versions and historical data.
8. **Ordered rollout:** New readers need to be ready before new writers emit new schemas, and only then retire old contracts.

By placing data contracts ahead of Java structural changes, development teams can upgrade JDKs and serialization libraries while preserving the ability to read historical data, communicate with un-upgraded consumers, and handle new properties in a controlled manner.
