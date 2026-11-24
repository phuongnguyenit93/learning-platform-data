# MapMessage and Typed Property Sets in JMS

> **Context:** Spring Framework – JMS, **Message Model** knowledge group. This lesson explains two typed data sets on the same JMS message: **name–value pairs inside the `MapMessage` body** and **message properties** outside the body, used for metadata and message selectors. Examples use Java 21, Jakarta Messaging (JMS) 3.1, Spring Boot 3.3, and ActiveMQ Artemis.

## 1. A JMS Message Has Three Distinct Regions

Do not confuse a Map-shaped body with the entire message. JMS organizes a message into three parts:

```text
JMS Message (one send/receive unit)
├── Headers                 <-- defined by JMS
│   ├── JMSMessageID
│   ├── JMSCorrelationID
│   ├── JMSDestination
│   └── JMSRedelivered, ...
├── Properties              <-- typed extension fields
│   ├── eventType = "OrderPaid"       (String)
│   ├── schemaVersion = 1            (int)
│   └── tenantId = "store-a"         (String)
└── Body: MapMessage        <-- name–value business content
    ├── orderId = "ORD-42"           (String)
    ├── amountMinor = 125000L        (long)
    ├── itemCount = 2                (int)
    ├── verified = true              (boolean)
    └── proof = byte[]{1, 35}        (byte[])
```

- **Headers** are standard fields of `jakarta.jms.Message`, such as `getJMSMessageID()` and `getJMSCorrelationID()`. They have their own APIs and are not map entries.
- **Properties** are a typed set of attributes present on **every JMS message type** (`TextMessage`, `BytesMessage`, `MapMessage`, etc.). The broker can use them to filter via **message selectors**.
- **Body** holds the primary data. When the body type is `MapMessage`, we use `setString/getString`, `setInt/getInt`, `setBytes/getBytes`, etc., with field names to read/write.

**Important rule:** `message.getString("orderId")` only exists on `MapMessage` and accesses the **body**; `message.getStringProperty("eventType")` accesses **properties**. Identical names across the two regions still denote **two independent values**. Message selectors **cannot read fields inside a `MapMessage` body**.

## 2. What Is `MapMessage` and How Does It Differ from `java.util.Map`?

`MapMessage` is a subtype of `jakarta.jms.Message` representing the body as a collection of **(String name, typed value)** pairs. The provider creates instances via `Session.createMapMessage()` or `JMSContext.createMapMessage()`. Applications do not instantiate `new MapMessage()` directly because it is an interface implemented by the provider.

Characteristics:

- **Field names** are non-`null`, non-empty `String`s; names serve as keys for random access. Names are **case-sensitive**: `orderId` differs from `OrderId`.
- **Values have explicit types**; the API supports lookup by name, **without requiring positional sequential reading** like `StreamMessage`.
- **No guaranteed iteration order.** `getMapNames()` returns an `Enumeration` of field names, but you must not rely on its iteration order to define a protocol.
- The body is **not** an arbitrary `Map<String,Object>`: only the value types allowed by Jakarta Messaging are supported. Do not put a `List`, nested `HashMap`, `BigDecimal`, `LocalDate`, or domain object directly in and expect the provider to serialize it automatically.
- You can call `getObject(name)` to get the corresponding wrapper (`Integer`, `Long`, `Boolean`, `Character`, etc.), `String`, or `byte[]`; for a non-existent field, `getObject` returns `null`.

Compared to other body types:

| JMS Type | Body | Best suited for |
| --- | --- | --- |
| `TextMessage` | A `String`, often holding JSON/XML/text | Cross-language protocols or JSON schemas with nested objects. |
| **`MapMessage`** | Name–value pairs of **primitives, String, byte[]** | Flat records with strongly typed fields where JMS receivers know the field contract upfront. |
| `BytesMessage` | Stream of bytes | Custom binary protocols requiring manual encoding/schema management. |
| `StreamMessage` | Sequence of typed values read in order | Messages with an agreed sequential layout. |
| `ObjectMessage` | `Serializable` Java object | Cases where both sides control Java serialization; requires compatibility and deserialization security review. |

## 3. Allowed Value Types in the Body

| Value type | Write method | Read method | Example |
| --- | --- | --- | --- |
| `boolean` | `setBoolean(name, value)` | `getBoolean(name)` | `verified = true` |
| `byte` | `setByte` | `getByte` | `level = (byte) 2` |
| `short` | `setShort` | `getShort` | `batch = (short) 12` |
| **`char`** | `setChar` | `getChar` | `sourceCode = 'W'` |
| `int` | `setInt` | `getInt` | `itemCount = 2` |
| `long` | `setLong` | `getLong` | `amountMinor = 125000L` |
| `float` | `setFloat` | `getFloat` | `ratio = 0.5f` |
| `double` | `setDouble` | `getDouble` | `score = 0.75d` |
| `String` | `setString` | `getString` | `orderId = "ORD-42"` |
| **`byte[]`** | `setBytes` | `getBytes` | `proof = new byte[]{1, 35}` |

`setObject(name, value)` accepts **wrappers** of primitives, `String`, and `byte[]` (not a POJO or nested `Map`). `setBytes(name, bytes, offset, length)` also allows copying a slice of a byte array.

API illustration example (this is a snippet inside a callback that has `jakarta.jms.Session session`; not a standalone program):

```java
MapMessage body = session.createMapMessage();
body.setString("orderId", "ORD-42");
body.setInt("itemCount", 2);
body.setLong("amountMinor", 125_000L);
body.setBoolean("verified", true);
body.setChar("sourceCode", 'W');
body.setBytes("proof", new byte[] { 0x01, 0x23 });

// Equivalent generic form:
body.setObject("retriesAllowed", Integer.valueOf(3));

// The following cases are invalid with MapMessage.setObject:
// body.setObject("items", List.of("A", "B"));
// body.setObject("price", new BigDecimal("12.50"));
```

For monetary amounts, prefer **integer minor units** such as `amountMinor` alongside `currency` where appropriate for the domain; do not rely on binary floating-point precision of `double` for financial math. For timestamps, standardize on `long` epoch milliseconds or ISO-8601 `String` and clearly document units, time zone, and schema version.

### `MapMessage` Does Not Replace Schema Design

Two consumers might both recognize field `amountMinor` yet interpret the unit differently if the contract is vague. Agree on:

1. Field names and exact setter types (e.g. `amountMinor: long`).
2. Required vs. optional fields; meaning of an absent or null field.
3. Units of measurement, enums, value ranges, and constraints.
4. How to evolve schema versions so older workers do not misread values.

## 4. Type Reading and Conversion Rules in `MapMessage`

Not every `getXxx` can convert from every type. The specification defines a **mandatory conversion table** from `row type` (written type) to allowed `getter`s:

| Written as type | Can be read with getter |
| --- | --- |
| `boolean` | `getBoolean`, `getString` |
| `byte` | `getByte`, `getShort`, `getInt`, `getLong`, `getString` |
| `short` | `getShort`, `getInt`, `getLong`, `getString` |
| `char` | `getChar`, `getString` |
| `int` | `getInt`, `getLong`, `getString` |
| `long` | `getLong`, `getString` |
| `float` | `getFloat`, `getDouble`, `getString` |
| `double` | `getDouble`, `getString` |
| `String` | `getString`, and boolean, byte, short, int, long, float, double getters if parseable; **no** conversion to `char` |
| `byte[]` | `getBytes` |

Unsupported combinations must throw `MessageFormatException`. When reading a string as a number and it fails to parse, Jakarta Messaging specifies `NumberFormatException`. For `getBoolean` from `String`, `Boolean.valueOf(String)` rules apply; any string other than `"true"` (case-insensitive) becomes `false`, so validate input if you want to accept only strict `true/false`.

Example:

```java
MapMessage m = session.createMapMessage();
m.setInt("itemCount", 2);
m.setString("retryAfterSeconds", "30");
m.setDouble("ratio", 0.75);

long a = m.getLong("itemCount");              // Valid: int -> long
int b = m.getInt("retryAfterSeconds");        // Valid: String "30" -> int
String c = m.getString("ratio");              // Valid: double -> String

// m.getInt("ratio");                         // MessageFormatException
// m.getChar("retryAfterSeconds");            // MessageFormatException
// m.getBytes("itemCount");                   // MessageFormatException
```

**Do not apply Java widening intuition:** `int -> double` is **not in `MapMessage`'s conversion table**, even though normal Java code permits that widening conversion. If the producer intends float/double, send the exact contract type.

### Missing Fields, Nulls, and Checking Before Reading

`itemExists(name)` distinguishes **an unwritten field** from one that is present. `getObject("missing")` returns `null` if the field is absent. Per the specification, reading a missing field via a primitive getter behaves like converting from a null string; for example, `getChar` on a missing field must throw `NullPointerException`, while `getInt` can result in `NumberFormatException`. For booleans, converting `Boolean.valueOf(null)` yields `false`, making it easy to mistake "missing data" for a valid value.

Check existence first and validate the contract type/value:

```java
if (!m.itemExists("itemCount")) {
    throw new IllegalArgumentException("Missing itemCount");
}
Object value = m.getObject("itemCount");
if (!(value instanceof Integer)) {
    throw new IllegalArgumentException("itemCount must be an int");
}
int itemCount = (Integer) value;
if (itemCount < 0) {
    throw new IllegalArgumentException("itemCount must be non-negative");
}
```

This validation block is a **code fragment** using `m` created in the example above. In a production system, data validation errors must be classified to avoid infinite retries on the same malformed message.

## 5. Message Properties: Also Typed, But **Not in the MapMessage Body**

Every `jakarta.jms.Message` exposes this method group:

```java
message.setStringProperty("eventType", "OrderPaid");
message.setIntProperty("schemaVersion", 1);
message.setBooleanProperty("requiresAudit", true);

String type = message.getStringProperty("eventType");
int version = message.getIntProperty("schemaVersion");
boolean audit = message.getBooleanProperty("requiresAudit");
```

**Essential differences between the two typed sets:**

| Criterion | `MapMessage` body entries | `Message` properties |
| --- | --- | --- |
| Purpose | Business data | Routing/filtering metadata, classification, and application-level control |
| Write API | `setInt("itemCount", 2)` | `setIntProperty("schemaVersion", 1)` |
| Read API | `getInt("itemCount")` | `getIntProperty("schemaVersion")` |
| Supported types | `boolean, byte, short, char, int, long, float, double, String, byte[]` | `boolean, byte, short, int, long, float, double, String` |
| Includes `char` and `byte[]`? | **Yes** | **No** |
| Valid names | Non-null, non-empty `String` | Must conform to message selector identifier syntax |
| Iterate names | `getMapNames()` | `getPropertyNames()` |
| Check existence | `itemExists(name)` | `propertyExists(name)` |
| Clear and re-enable writes on received msg | `clearBody()` | `clearProperties()` |
| Visible to message selectors? | **No** | **Yes**, if property is present and selector is valid |

`setObjectProperty` only accepts `Boolean, Byte, Short, Integer, Long, Float, Double, String`. It does not accept `Character`, `byte[]`, `BigDecimal`, or `List`. The property value type set is part of the JMS contract regardless of whether the body is `MapMessage` or `TextMessage`.

Property names must obey identifier rules: they may start with a letter, `_`, or valid Java identifier start character, followed by identifier characters; do not use empty names or selector keywords like `AND`, `NULL`, `TRUE`. For example, `schemaVersion` is valid; `order-status` is unsuitable for direct use as an identifier in a selector. Property names are **case-sensitive**.

### Headers and `JMSX` Standards Are Not Arbitrary Custom Properties

- `JMSMessageID`, `JMSCorrelationID`, `JMSPriority`, `JMSDestination`, etc. are **headers**, with corresponding getters/setters such as `getJMSCorrelationID()`; they do not appear in `getPropertyNames()`.
- Jakarta Messaging reserves the **`JMSX`** prefix for standard properties, such as `JMSXDeliveryCount` (set by the provider on receive, starting at 1) and `JMSXGroupID` (group ID for message grouping). **Do not create application names starting with `JMSX`**.
- The **`JMS_<vendor_name>`** prefix belongs to vendor-specific provider property namespaces. Name application metadata with neutral names like `eventType` or `schemaVersion`.
- `JMSXDeliveryCount >= 2` usually indicates redelivery, but the number itself is not a mechanism to prevent duplicate business side effects; always design consumers to be idempotent.

## 6. Message Selector Mechanism: Why Metadata Belongs in Properties

A consumer wanting only `OrderPaid` with schema version 1 can declare the selector:

```sql
eventType = 'OrderPaid' AND schemaVersion = 1
```

The producer must set:

```java
message.setStringProperty("eventType", "OrderPaid");
message.setIntProperty("schemaVersion", 1);
```

**It has no effect on the selector** if you only call:

```java
message.setString("eventType", "OrderPaid"); // MapMessage body
message.setInt("schemaVersion", 1);          // MapMessage body
```

Because selectors only look at headers/properties, fields inside the body are **not automatically mapped to properties**.

**Note on types in selectors:** even though `getIntProperty("schemaVersion")` can parse a `"1"` string per getter rules, the selector `schemaVersion = 1` **does not automatically apply getter-style type conversion**. If the producer sends `setStringProperty("schemaVersion", "1")`, that numeric comparison is not equivalent to `setIntProperty(..., 1)`. Standardize property types from the start and test against a real broker.

Selectors use syntax resembling a subset of SQL92; string literals use single quotes. A missing property evaluates to logical `NULL` in a selector, and comparisons against it do not evaluate to `true`. Use `IS NULL`/`IS NOT NULL` when you need to express missing-property conditions explicitly.

**Design note:** only add metadata needed for routing, classification, and tracing into properties; keep order details and large payloads in the body. Many long properties or excessive property counts can increase overhead for the broker and selector evaluation.

## 7. Spring Boot 3.3 + Artemis Example: Sending and Receiving `MapMessage` Properly

This minimal example uses **Java 21**, **Spring Boot 3.3.5**, **Jakarta JMS**, and one **queue** named `orders.typed`. The focus here is the Message model; a queue is used to avoid mixing topic/subscription concepts into the example.

Environment prerequisites: a **running ActiveMQ Artemis broker** at `tcp://localhost:61616`, with queue `orders.typed` or an appropriate auto-create policy. If the broker requires authentication, configure Artemis credentials via environment variables `SPRING_ARTEMIS_USER` and `SPRING_ARTEMIS_PASSWORD`; the example does not hardcode passwords.

### 7.1 Gradle Configuration

`settings.gradle`:

```groovy
rootProject.name = 'typed-map-jms-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain { languageVersion = JavaLanguageVersion.of(21) }
}

repositories { mavenCentral() }

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-artemis'
}
```

`src/main/resources/application.yml`:

```yaml
spring:
  artemis:
    mode: native
    broker-url: tcp://localhost:61616
  jms:
    pub-sub-domain: false
    listener:
      session:
        transacted: true
server:
  port: 8080
```

`session.transacted: true` illustrates receive/commit mechanics at the listener; an unhandled failure before commit causes receipt rollback and potential redelivery per broker configuration. It **does not automatically create a distributed transaction across DB and JMS**.

### 7.2 Complete Java Source

Create `src/main/java/com/example/typedmap/TypedMapJmsApplication.java`:

```java
package com.example.typedmap;

import java.util.Arrays;

import jakarta.jms.JMSException;
import jakarta.jms.MapMessage;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.ResponseEntity;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@EnableJms
public class TypedMapJmsApplication {
    public static void main(String[] args) {
        SpringApplication.run(TypedMapJmsApplication.class, args);
    }
}

@RestController
class TypedOrderSender {
    private final JmsTemplate jmsTemplate;

    TypedOrderSender(JmsTemplate jmsTemplate) {
        this.jmsTemplate = jmsTemplate;
    }

    @PostMapping("/orders/demo")
    ResponseEntity<String> sendDemo() {
        jmsTemplate.send("orders.typed", session -> {
            MapMessage message = session.createMapMessage();

            // BODY: typed business fields
            message.setString("orderId", "ORD-42");
            message.setLong("amountMinor", 125_000L);
            message.setString("currency", "VND");
            message.setInt("itemCount", 2);
            message.setBoolean("verified", true);
            message.setChar("sourceCode", 'W');
            message.setBytes("proof", new byte[] { 0x01, 0x23 });

            // PROPERTIES: metadata for broker selector filtering
            message.setStringProperty("eventType", "OrderPaid");
            message.setIntProperty("schemaVersion", 1);

            // HEADER: standard JMS field, not inside the body
            message.setJMSCorrelationID("req-42");
            return message;
        });

        return ResponseEntity.accepted().body("ENQUEUED ORD-42");
    }
}

@Component
class TypedOrderConsumer {
    @JmsListener(
            destination = "orders.typed",
            selector = "eventType = 'OrderPaid' AND schemaVersion = 1")
    public void receive(MapMessage message) throws JMSException {
        // Raw MapMessage is supported by Spring @JmsListener.
        if (!message.itemExists("orderId")
                || !message.itemExists("amountMinor")) {
            throw new IllegalArgumentException("Missing required body fields");
        }

        System.out.printf(
                "BODY orderId=%s amountMinor=%d currency=%s "
                + "itemCount=%d verified=%b sourceCode=%c proof=%s%n",
                message.getString("orderId"),
                message.getLong("amountMinor"),
                message.getString("currency"),
                message.getInt("itemCount"),
                message.getBoolean("verified"),
                message.getChar("sourceCode"),
                Arrays.toString(message.getBytes("proof")));

        System.out.printf(
                "META eventType=%s schemaVersion=%d correlation=%s%n",
                message.getStringProperty("eventType"),
                message.getIntProperty("schemaVersion"),
                message.getJMSCorrelationID());
    }
}
```

Line-by-line breakdown:

1. `JmsTemplate.send(destination, messageCreator)` invokes the callback with a live `Session` and sends the exact `MapMessage` created. There is no JSON, no `Serializable`, and no custom converter needed.
2. `setString/setLong/setInt/setBoolean/setChar/setBytes` write into the **body**. `setStringProperty/setIntProperty` write into **properties**. `setJMSCorrelationID` writes into the **header**.
3. The listener directly accepts `MapMessage`; Spring JMS supports raw `jakarta.jms.Message` or matching subclass parameters. We read body/properties/header via their three respective API groups.
4. `selector` inspects only properties. Because `eventType` and `schemaVersion` were set in the proper region and with the right types, matching messages are dispatched to the consumer.
5. `@EnableJms` enables annotation-driven listener endpoints. Spring Boot auto-configures `ConnectionFactory`/`JmsTemplate` from the Artemis starter when the environment is set up.
6. Returning HTTP 202 only means the producer handed off the send call successfully as configured. It **does not guarantee** that the listener has finished processing or that downstream systems committed a business transaction.

### 7.3 Running and Observable Output

Start the broker first. In a Gradle project with wrapper:

```bash
# Linux/macOS
./gradlew bootRun

# Windows
gradlew.bat bootRun
```

Send a message:

```bash
curl -i -X POST http://localhost:8080/orders/demo
```

Expected HTTP response contains status `202 Accepted` and body:

```text
ENQUEUED ORD-42
```

A stdout excerpt from the listener **after** the broker delivers the message:

```text
BODY orderId=ORD-42 amountMinor=125000 currency=VND itemCount=2 verified=true sourceCode=W proof=[1, 35]
META eventType=OrderPaid schemaVersion=1 correlation=req-42
```

The two lines have deterministic contents from the fields; **their timing** relative to the HTTP response and Spring startup logs depends on scheduling/broker execution. If the broker is down, authentication fails, or the queue has not been created per policy, the example will not send/receive successfully; those are environment dependencies, not standard output.

### 7.4 Using Spring `convertAndSend` with a Java Map

When using the default `SimpleMessageConverter`, a `java.util.Map` containing JMS-supported types can be converted into a `MapMessage`. A `MessagePostProcessor` adds properties/headers before sending:

```java
Map<String, Object> payload = new LinkedHashMap<>();
payload.put("orderId", "ORD-42");
payload.put("amountMinor", 125_000L);
payload.put("verified", true);

jmsTemplate.convertAndSend("orders.typed", payload, message -> {
    message.setStringProperty("eventType", "OrderPaid");
    message.setIntProperty("schemaVersion", 1);
    return message;
});
```

This is an **illustrative code snippet**, requiring imports for `java.util.Map`, `java.util.LinkedHashMap`, and an existing `JmsTemplate jmsTemplate` variable. It is not equivalent to an arbitrary object-mapping mechanism: `Map<String,Object>` must still hold only **valid `MapMessage` values**; a custom `MessageConverter` may change the wire message type. The complete runnable example above uses `session.createMapMessage()` so it is crystal clear what is sent.

## 8. Iterating Fields, Checking Contracts, and Metadata

When all field names are not known upfront (for example, writing a debugging tool), you can iterate over names:

```java
// Snippet inside a listener, with MapMessage message:
for (java.util.Enumeration<?> names = message.getMapNames();
        names.hasMoreElements();) {
    String name = (String) names.nextElement();
    Object value = message.getObject(name);
    System.out.println("body field: " + name + "=" + value);
}

for (java.util.Enumeration<?> names = message.getPropertyNames();
        names.hasMoreElements();) {
    String name = (String) names.nextElement();
    Object value = message.getObjectProperty(name);
    System.out.println("message property: " + name + "=" + value);
}
```

**Do not rely on print order:** neither `getMapNames()` nor `getPropertyNames()` guarantees ordering. Printing `byte[]` via `Object.toString()` is unreadable; use `Arrays.toString`/hex/Base64 per contract and **do not log sensitive data**. `getPropertyNames()` also does not list standard headers.

In business consumers, dynamic iteration is usually unnecessary: check required fields and read the exact types; reject unsupported schemas. If an evolvable schema is needed, allow **unknown new fields to be ignored** without silently changing types of existing fields; use `schemaVersion` in properties and producer/consumer compatibility tests.

## 9. Read-Only Rules and `clearBody`/`clearProperties`

When a message is **newly created**, both body and properties are writable. When **received from the broker**, body and properties are in **read-only** mode so the provider can manage them safely. Writing directly after receive can throw `MessageNotWriteableException`.

The two state-changing operations are **independent**:

| Method call | What data is cleared? | Which part becomes writable again? |
| --- | --- | --- |
| `message.clearBody()` | All `MapMessage` body entries | Body; existing properties remain intact. |
| `message.clearProperties()` | All properties | Properties; existing body remains intact. |

Do not use `clearBody` to clear metadata or `clearProperties` to clear the body. These calls mutate **the in-memory message object being handled**; they are not a way to "delete a broker-delivered message" or auto-ACK it. When you need to send a new message, normally call `session.createMapMessage()` for a fresh instance and copy validated fields, avoiding accidental mutation/re-sending of a received message.

**There is no standard API to remove a single property** once added; `clearProperties()` removes the whole set. Likewise, for a `MapMessage` body, there is no `remove(field)` equivalent to `java.util.Map.remove`; construct a new body if structural changes are needed.

## 10. Handling Wrong Types, Missing Data, and Compatibility

| Scenario | Consequence | Resolution |
| --- | --- | --- |
| Producer `setDouble("amountMinor", 125000.0)`; consumer `getLong` | `MessageFormatException` because conversion table forbids double → long. | Standardize on `long` from the schema onward; test actual types. |
| Producer `setString("itemCount", "two")`; consumer `getInt` | `NumberFormatException` on parse. | Validate data at sender; do not send numbers as text unnecessarily. |
| Consumer calls `getBoolean("verified")` when field is missing | May return `false` via null conversion, masking missing data. | Check `itemExists("verified")` first. |
| Producer sends `List` or `BigDecimal` via `setObject` | `MessageFormatException` due to unsupported type. | Design a flat scalar schema or use `TextMessage`/JSON with a clear schema. |
| Producer puts `eventType` in body while consumer uses selector | Selector cannot see the body; message is not selected by that rule. | Put metadata in `setStringProperty`. |
| Producer uses `setStringProperty("schemaVersion", "1")` while selector is `schemaVersion = 1` | Type mismatch in selector; getter conversion is not applied automatically. | Use `setIntProperty` and test the selector. |
| Consumer tries to edit body of received message | `MessageNotWriteableException`. | Respect read-only mode; create a new message if transformation and re-publishing are needed. |
| Adding new field while renaming/retyping old field without bumping version | Old consumers may misread or crash. | Version the schema and deploy backward/forward-compatible changes. |
| Setting `JMSXDeliveryCount` as an application property | Hijacks a provider-managed standard name. | Use application-named properties; read `JMSXDeliveryCount` only to observe delivery attempts. |
| Using `double` for money without units or currency | Precision loss or consumer unit mismatch. | Use integer minor units or string decimals per an agreed schema. |

### MapMessage Solves Data Typing, Not Automatic Reliability

`MapMessage` itself does not decide whether a message is persistent, whether it is redelivered, whether it enters a DLQ, processing order, or exactly-once business outcomes. Those properties depend on JMS delivery mode, broker, transaction/ACK, retries, and idempotency design. If a consumer updates a DB successfully and fails before JMS ACK, the entire message (headers/properties/body) may be redelivered; carry a stable `eventId` and deduplicate where business results are persisted.

For long-term exchanges across multiple versions or languages, evaluate provider/protocol compatibility, choose a versioned schema, and consider `TextMessage` JSON or a binary schema with a concrete contract. `MapMessage` is convenient for JMS clients exchanging **flat typed fields**, but it does not replace a schema evolution strategy.

## 11. Practice Exercises and Review Questions

1. Modify the example to add `createdAtEpochMs: long` to the body and `tenantId: String` to properties. Write a selector accepting only `tenantId = 'store-a' AND schemaVersion = 1`. Why cannot `createdAtEpochMs` be used directly in the selector?
2. Change `itemCount` from `int` to `String` with value `"2"`. Can `getInt("itemCount")` succeed? Why should you still avoid silently changing types in a contract?
3. Use `setChar("sourceCode", 'W')`, then try `getString("sourceCode")`. Why does `char` exist in `MapMessage` but not in the property API?
4. Add field `proof: byte[]`; why is `setObjectProperty("proof", new byte[]{...})` invalid? If you need to filter on proof status, what property should you use instead of raw bytes?
5. Distinguish `itemExists("verified")` and `propertyExists("verified")` when the same name appears in both body and properties.
6. State the difference between `clearBody` and `clearProperties` on a received message; why should they not be used to "patch" newly received data for error recovery?
7. Test a missing field and a wrong-type field; state the exceptions/values possible for `getObject`, `getInt`, `getBoolean`, and `getChar`. Why must consumers validate required fields?
8. Explain why `JMSXDeliveryCount=2` does not mean business logic has processed it twice already; what mechanism is needed for deduplication?

**Key takeaway:** `MapMessage` stores a **body of flat typed fields**; message properties are **typed metadata on any JMS message**, usable by the broker in selectors; headers are **standard JMS fields**. Choosing the right region, right setter/getter, consistent schema types, and checking for missing fields prevents most interoperability bugs between producers, consumers, and brokers.

### References

- [Jakarta Messaging 3.1 – MapMessage API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/mapmessage) — body types, accessors, conversions, and `itemExists`.
- [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html) — sections 3.5, 3.8, 3.11: properties, selectors, read-only body, conversions.
- [Jakarta Messaging 3.1 – Message API](https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message) — headers, properties, `clearBody`, `clearProperties`, `JMSXDeliveryCount`.
- [Spring Framework – Annotation-driven Listener Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html) — raw `MapMessage` parameter, `@JmsListener`, and `selector`.
- [Spring Framework – Sending a Message](https://docs.spring.io/spring-framework/reference/integration/jms/sending.html) — `JmsTemplate.send`, `SimpleMessageConverter` map-to-`MapMessage`, and `MessagePostProcessor`.
