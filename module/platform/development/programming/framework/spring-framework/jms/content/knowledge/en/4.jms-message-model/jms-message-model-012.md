# JMSType, JMSX Properties, and Application-Defined Properties in Jakarta Messaging (JMS)

## 1. Why Does a JMS Message Need Information Outside the Body?

When sending a message such as "order 42 was just created", the body carries the business data; however, the receiver also needs to know **which event type the message represents**, **the contract version**, **the tenant**, **processing priority**, or **whether this is a redelivery**. Jakarta Messaging provides three distinct metadata/payload groups:

1. **Standard headers** on `jakarta.jms.Message`: for example `JMSType`, `JMSMessageID`, `JMSCorrelationID`, `JMSDestination`, `JMSRedelivered`. Each header has dedicated getters/setters or provider-populated mechanics.
2. **Message properties**: simple typed name/value pairs. These include standard properties starting with **JMSX**, provider-specific properties, and application-defined properties.
3. **Body**: `TextMessage`, `BytesMessage`, `MapMessage`, `ObjectMessage`, `StreamMessage`, or a bodyless `Message`; this is the payload read by business logic.

Example `TextMessage`:

~~~text
JMS message
├── Standard headers
│   ├── JMSType          = "order.created.v1"
│   ├── JMSMessageID     = "ID:..."           (assigned by provider)
│   ├── JMSCorrelationID = "trace-123"       (set by application, if needed)
│   └── JMSRedelivered   = false              (assigned by provider on delivery)
├── Message properties
│   ├── JMSXDeliveryCount = 1                 (assigned by provider on receive)
│   ├── JMSXGroupID       = "order-42"        (set by application if using grouping)
│   ├── TenantId          = "acme"            (set by application)
│   ├── SchemaVersion     = 2                 (set by application)
│   └── RequiresAudit     = true              (set by application)
└── Body (TextMessage)
    └── {"orderId":"42","total":250}
~~~

**Note:** values in the diagram are illustrative. `JMSXDeliveryCount` is only meaningful on a **received** message; never assume a producer knows the delivery count of an undelivered message. Broker dashboards may render metadata in their own UI, yet the programming contract here is the Jakarta Messaging API.

| Question | Where to look | Related API |
| --- | --- | --- |
| Which business type is this message? | `JMSType` header | `setJMSType` / `getJMSType` |
| How many times has the provider delivered the message? | JMSX property | `getIntProperty("JMSXDeliveryCount")` |
| Do multiple messages belong to the same logical group? | JMSX property | `setStringProperty("JMSXGroupID", ...)` |
| Tenant, schema version, routing labels? | Application-defined property | `setStringProperty` / `setIntProperty` / `get...Property` |
| Need to find related messages in request-reply? | `JMSCorrelationID` header | `setJMSCorrelationID` / `getJMSCorrelationID` |
| Actual order data? | Body | `TextMessage.getText` or `Message.getBody` |

These three metadata groups do not substitute for one another; nor does a custom property name automatically become a standard JMS header.

## 2. JMSType: Message-Type Identifier in the Standard Header

### 2.1. Meaning and Reading/Writing

**`JMSType`** is a **`String` header** carrying a sender-supplied message type identifier. It is part of the message contract—not a Java class name, not a destination name, and not a JMS body type like `TextMessage` or `MapMessage`.

~~~java
TextMessage message = session.createTextMessage(
        "{\"orderId\":\"42\"}");
message.setJMSType("order.created.v1");

// After receiving at the consumer:
String type = receivedMessage.getJMSType();
~~~

The snippet above illustrates usage with pre-existing `session` and `receivedMessage` variables; the full runnable program is in section 7.

Some providers include a message-definition repository and may use `JMSType` to reference message definitions. Jakarta Messaging **does not require** every provider to support a repository or dictate `JMSType` naming rules; applications must establish their own naming and versioning conventions.

**Easily confused distinctions:**

- **`JMSType = "order.created.v1"`**: application-defined event/message type name.
- **`TextMessage`**: class/interface indicating the body is text; many different `JMSType` values can all use `TextMessage`.
- **`JMSDestination`**: queue/topic to which the broker sends the message.
- **`JMSCorrelationID`**: message correlation key, commonly used for request-reply; does not classify business events.

`JMSType` may be left unset (`null`). Receivers need an explicit policy: accept only valid messages via selectors, or inspect the type and treat `null`/unsupported values as a contract error.

### 2.2. Using JMSType as a Message Selection Criterion

A JMS selector can reference the `JMSType` header directly:

~~~sql
JMSType = 'order.created.v1'
~~~

A selector is a SQL-92–like filter expression evaluated by the provider when dispatching messages to a consumer. Do not write:

~~~java
message.setStringProperty("JMSType", "order.created.v1"); // Not the right API to set the header.
~~~

Call **`message.setJMSType(...)`** instead. `getPropertyNames()` also excludes standard JMS headers, so `JMSType` is read via `getJMSType()`.

### 2.3. Choosing Name and Version Contracts

An intuitive convention:

~~~text
JMSType        = "order.created.v1"
SchemaVersion  = 2
TenantId       = "acme"
~~~

Here `JMSType` `v1` denotes the **event family / message-type version identifier**, while `SchemaVersion=2` denotes the specific payload version per agreement. Both versioning mechanisms may align or be used separately; document them in an agreed contract between producer and consumer. Never assume the broker decodes JSON or validates schemas merely because `JMSType` ends with `v1`.

In multi-consumer environments supporting old and new versions side by side, plan selectors, schema compatibility, fallbacks, and upgrade rollouts. A message with a valid `JMSType` whose body violates the schema is still a business error to handle.

## 3. Message Properties: General Mechanism and Boundary with Body

Properties act like simple typed "extension headers" with name/value pairs. The API supports **`boolean`, `byte`, `short`, `int`, `long`, `float`, `double`, `String`**. Typed setters have matching getters:

~~~java
message.setStringProperty("TenantId", "acme");
message.setIntProperty("SchemaVersion", 2);
message.setBooleanProperty("RequiresAudit", true);
message.setLongProperty("ReceivedAtEpochMillis", 1760000000000L);

// On the receiving side:
String tenant = message.getStringProperty("TenantId");
int version = message.getIntProperty("SchemaVersion");
boolean audit = message.getBooleanProperty("RequiresAudit");
long time = message.getLongProperty("ReceivedAtEpochMillis");
~~~

This is an illustrative snippet. Never send arbitrary Java DTOs as properties via `setObjectProperty("Order", new Order(...))`; **`setObjectProperty`** only accepts spec-allowed primitive wrappers and `String`. Complex data belongs in the body or an external store referenced by the message.

### 3.1. Property Naming Rules

Property names must follow **JMS message selector identifier** syntax: case-sensitive and free of spaces, dots, hyphens, or invalid identifier characters. Avoid selector keywords such as `AND`, `OR`, `TRUE`, `NULL`, `BETWEEN`, `LIKE`, `IN`, `IS`, `ESCAPE`, `NOT`. Property names must not be `null` or empty strings.

~~~text
Valid:     TenantId, SchemaVersion, OrderId, RequiresAudit
Avoid:     tenant-id, order.id, "Tenant Id", AND, 123Name
~~~

Regarding namespaces:

- **`JMSX...`**: names reserved for Jakarta Messaging–defined properties, such as `JMSXDeliveryCount`. Applications must never invent new properties like `JMSXRetryReason`.
- **`JMS_<vendor>...`**: reserved for provider-specific properties, such as broker-published extensions. Never use as portable application properties.
- **Application names**: keep separate from standard/reserved namespaces, e.g. `TenantId`, `SchemaVersion`, `BusinessAction`. Avoid creating properties starting with `JMS` to prevent confusion with reserved API names.

A property's data type is part of the contract: `setIntProperty("SchemaVersion", 2)` creates a numeric value; `setStringProperty("SchemaVersion", "2")` creates a `String`. Selector **`SchemaVersion >= 2`** requires a numeric value and cannot rely on the selector auto-converting `"2"` to a number.

### 3.2. Properties vs. Body

| Aspect | Message properties | Body |
| --- | --- | --- |
| Primary purpose | Metadata, filtering/routing, versioning, grouping, diagnostics | Business payload |
| Values | JMS-supported primitives/wrappers and `String` | Per JMS message type and system-chosen format |
| Referenceable in JMS selectors? | Yes, with valid names/types | No |
| Complex data | Unsuitable | Suitable via JSON/XML/binary/`MapMessage`… |
| Contract evolution | Keep compatible; avoid sudden renames/retypes | Manage schema/version independently |

Messages should keep metadata small, consistent, and stable. Never place sensitive data (tokens, passwords, personal data) into properties just to make filtering convenient; brokers, logs, and monitoring tools can expose metadata.

### 3.3. Properties of a Received Message Are Read-Only

Before sending, the message creator can set properties. After receiving, message properties are in **read-only mode**. Calling `setStringProperty(...)` on a newly received message normally throws `MessageNotWriteableException`.

~~~java
// receivedMessage is a received message:
int version = receivedMessage.getIntProperty("SchemaVersion");
// receivedMessage.setIntProperty("SchemaVersion", 3);
// -> MessageNotWriteableException while properties remain read-only.

receivedMessage.clearProperties(); // Clears ALL properties, re-enabling writes.
receivedMessage.setIntProperty("SchemaVersion", 3);
~~~

**Do not call `clearProperties()` just to edit one field while forgetting the rest.** It wipes all property entries, including metadata you wanted to keep; it leaves the body untouched, and JMS has no standard API to delete a single property. When producing a new outbound message, it is usually better to create a fresh message and selectively copy needed metadata instead of "mutating in place" a received message.

### 3.4. Reading Absent Properties, Iterating, and Type Conversions

- **`propertyExists("Key")`** checks whether a key is actually present on the message.
- **`getObjectProperty("Key")`** returns `null` if the key does not exist; use it to detect missing fields before casting.
- **`getPropertyNames()`** returns an `Enumeration` of message property names (excluding standard JMS headers); order is not guaranteed.
- Primitive getters on an absent key follow specific null-conversion rules and can throw exceptions; never assume all of them return defaults like `0` or `false`.
- JMS defines certain conversions across property types (for instance, many numeric types can be read as `String`), yet not every conversion is valid; to keep selectors and consumers predictable, producers should write **the exact contract type from the start**.

~~~java
if (message.propertyExists("SchemaVersion")) {
    int schema = message.getIntProperty("SchemaVersion");
    // Only process when the contract guarantees this field is an int.
}
~~~

## 4. JMSX: Properties Defined by Jakarta Messaging

The **`JMSX`** prefix is reserved for standard metadata defined by the specification, distinct from application-defined properties. Some are set by the producer, others by the provider on send or on receive. **Not all JMSX properties are guaranteed to appear on every message.**

### 4.1. Standard List per Jakarta Messaging 3.1

| Property name | Type | Set by | Meaning |
| --- | --- | --- | --- |
| `JMSXDeliveryCount` | `int` | Provider on receive | Number of times the message has been delivered. **Mandatory** on received messages. |
| `JMSXGroupID` | `String` | Client | Logical message group name; optional field, provider must support this property. |
| `JMSXGroupSeq` | `int` | Client | Position of message within group, typically 1, 2, 3…; optional field, provider must support this property. |
| `JMSXUserID` | `String` | Provider on send | Sending user identity, if supported/enabled by provider. |
| `JMSXAppID` | `String` | Provider on send | Sending application identity, if supported/enabled by provider. |
| `JMSXProducerTXID` | `String` | Provider on send | Producer transaction ID, if supported. |
| `JMSXConsumerTXID` | `String` | Provider on receive | Consumer transaction ID, if supported. |
| `JMSXRcvTimestamp` | `long` | Provider on receive | Timestamp when message was delivered, if supported. |
| `JMSXState` | `int` | Provider | State of message copy in message-warehouse models; not a normal consumer-facing lookup field. |

**Important nuance:** the spec table lists "Optional" for `JMSXGroupID`/`JMSXGroupSeq` because messages do not have to carry them. That **does not mean a provider may refuse to support those property names**: the spec requires every provider to support these two standard properties. How groups map to consumers, sticky affinity, group handoff, and group sequence handling in operations must be checked in provider documentation.

### 4.2. JMSXDeliveryCount and JMSRedelivered

When a consumer receives a message, **`JMSXDeliveryCount`** reflects how many times the provider has delivered that message:

- First delivery: **`1`**.
- **`2` or higher**: the message has been redelivered one or more times.
- `JMSRedelivered` is a separate **standard boolean header**: when `true`, the provider is marking the message as redelivered. If `JMSRedelivered=true`, `JMSXDeliveryCount` must be 2 or higher.

~~~java
int deliveryCount = message.getIntProperty("JMSXDeliveryCount");
boolean redelivered = message.getJMSRedelivered();

if (deliveryCount >= 2) {
    // Track redeliveries, increment logs/metrics, or apply idempotent handling.
}
~~~

**`JMSXDeliveryCount` is the delivery count, not the exception count in code**, and not the application's own business retry count. Under certain provider/server failures, the spec does not force the counter to be strictly exact across every crash. Therefore do not use this number as the sole source for idempotency, business limits, or monetary logic. For end-to-end deduplication, persist a durable business ID / `orderId` / idempotency key.

`JMSXDeliveryCount` is **set by the provider on receive**. Do not have producers set `JMSXDeliveryCount=0` or write broker-side selectors like:

~~~sql
JMSXDeliveryCount >= 3
~~~

to route messages prior to delivery. The spec states that **selector behavior based on properties assigned at receive time is undefined**. Consumers should read the property after receiving; configure retries/backoff and dead-letter addresses/queues (DLQs) at the broker/container/application level per provider.

### 4.3. JMSXGroupID and JMSXGroupSeq

Both properties relate to **message grouping**: messages sharing a group may need sequential processing and pinning to one consumer to preserve context.

~~~java
TextMessage first = session.createTextMessage("{\"step\":1}");
first.setStringProperty("JMSXGroupID", "order-42");
first.setIntProperty("JMSXGroupSeq", 1);

TextMessage second = session.createTextMessage("{\"step\":2}");
second.setStringProperty("JMSXGroupID", "order-42");
second.setIntProperty("JMSXGroupSeq", 2);
~~~

This example illustrates the metadata. `JMSXGroupID` is **not** `JMSCorrelationID`: correlation IDs pair request-reply flows, whereas group IDs govern grouping messages for ordered consumption. `JMSXGroupSeq` is a sequence number **set by the client**; the broker does not automatically number 1, 2, 3 on the producer's behalf.

Some brokers support group affinity / sticky consumers; exact ordering guarantees and group-release rules vary by provider and configuration. Do not assume setting `JMSXGroupID` guarantees atomic transactions, exactly-once execution, or global ordering across multiple queues/topics. Business logic must still handle gaps or missing sequence numbers.

### 4.4. Checking Which JMSX Properties a Provider Supports

`ConnectionMetaData.getJMSXPropertyNames()` returns the list of JMSX names advertised as supported by the provider:

~~~java
ConnectionMetaData metadata = connection.getMetaData();
java.util.Enumeration<?> names = metadata.getJMSXPropertyNames();
while (names.hasMoreElements()) {
    System.out.println(names.nextElement());
}
~~~

This snippet requires a `connection` variable. The exact list varies across Artemis, IBM MQ, others, and versions, so do not hardcode expected stdout. A provider **supporting a property** also does not mean it populates it on every message: check `propertyExists` and the "set by" spec rule before reading.

## 5. Application-Defined Properties: System-Designed Metadata Contracts

Applications set non-reserved names/values for domain-specific needs, such as:

| Property | Type | Example | Meaning and notes |
| --- | --- | --- | --- |
| `TenantId` | `String` | `"acme"` | Data partitioning; **does not replace authorization checks**. |
| `SchemaVersion` | `int` | `2` | Payload/contract version used when reading the body. |
| `BusinessEvent` | `String` | `"OrderCreated"` | Supplementary business name if `JMSType` is not used for that. |
| `Region` | `String` | `"vn-south"` | Regional routing if architecture requires it. |
| `RequiresAudit` | `boolean` | `true` | Processing/audit rule; needs an explicit contract. |
| `RetryBudget` | `int` | `3` | Application-set value; not synonymous with `JMSXDeliveryCount`. |
| `CorrelationKey` | `String` | `"job-42"` | Business correlation key if `JMSCorrelationID` header is not chosen. |

You do not need to attach every property to every message. Add only what consumers, selectors, or monitoring actually require; each property increases coupling between producer and consumer.

**Consistent names, consistent types, consistent meaning** matter far more than stuffing lots of metadata. For example, once `TenantId` is standardized, do not sometimes send `TenantId` and other times `tenantId` or `TenantID`: property identifiers are **case-sensitive**.

### 5.1. Properties Are Not a Security Control

Even with a selector `TenantId = 'acme'`, an untrusted producer could craft a message claiming `TenantId='acme'`. The broker filters solely on metadata values without verifying whether the sender is authorized for that tenant. Enforce producer/consumer authentication, queue/topic permissions, business payload validation, and separate trust boundaries.

### 5.2. Versioning and Compatibility

A payload evolution pattern:

1. Producer sends `JMSType='order.created.v1'`, `SchemaVersion=1`, v1 body schema.
2. Updated consumer accepts `SchemaVersion IN (1, 2)`, parses per version, and supplies fallbacks for new fields.
3. While rolling over to v2, producers can send `SchemaVersion=2` within the approved contract, or switch to `JMSType='order.created.v2'` if the type name must change too.
4. Before retiring v1, inspect queue backlogs and legacy subscribers; never tighten selectors too early and strand v1 messages unconsumed.

JMS does not automatically validate JSON schemas or manage schema evolution; `JMSType`/`SchemaVersion` are **application conventions**. Document and independently test contracts on both producer and consumer sides.

## 6. Message Selectors: Combining JMSType and Application Properties

A message selector is a filter string based on **spec-permitted headers** and **message properties**. It is evaluated by the JMS provider to choose which messages are delivered to a `MessageConsumer`.

Example:

~~~sql
JMSType = 'order.created.v1'
AND TenantId = 'acme'
AND SchemaVersion >= 2
~~~

In Jakarta Messaging, the **standard headers** referenceable in selectors are: `JMSDeliveryMode`, `JMSPriority`, `JMSMessageID`, `JMSTimestamp`, `JMSCorrelationID`, `JMSType`. Do not assume other headers (such as `JMSRedelivered`) are valid selector fields. Nor can a selector reach directly into an `orderId` field inside a JSON body.

### 6.1. Useful Filter Expressions

~~~sql
-- Receive only orders belonging to the specified tenant:
TenantId = 'acme'

-- Receive only a specific event type:
JMSType = 'order.created.v1'

-- Type, tenant, and version combined:
JMSType = 'order.created.v1' AND TenantId = 'acme'
  AND SchemaVersion >= 2

-- Supported versions:
SchemaVersion IN (1, 2)

-- Boolean property:
RequiresAudit = TRUE

-- Skip messages without Region:
Region IS NOT NULL

-- Multiple event types can be combined:
(JMSType = 'order.created.v1' OR JMSType = 'order.updated.v1')
  AND TenantId = 'acme'
~~~

`AND`/`OR`, comparison operators, `IN`, `BETWEEN`, `LIKE`, and `IS NULL` follow a SQL-92–style subset; string literals must use **single quotes**, doubled (`''`) to escape an inner single quote. Identifiers are case-sensitive; selector keywords are case-insensitive.

**Three-valued logic:** when a property is missing, it evaluates to `NULL` in a selector expression. Comparisons with `NULL` generally yield `UNKNOWN`; only `TRUE` matches. Consequently, a typo like `TenantId` vs. `tenantId` or omitting a property can silently prevent delivery to a selector-filtered consumer with no Java error on the producer.

**Data types matter:**

~~~java
message.setStringProperty("SchemaVersion", "2");
~~~

Selector `SchemaVersion >= 2` **will not match as a numeric comparison** because the actual property is a `String`. Use `setIntProperty("SchemaVersion", 2)`, or if the contract specifies `String`, compare as strings in the selector. Never rely on implicit broker type coercion across different providers.

### 6.2. Selectors Filter, They Do Not Re-Route

On a **queue**, a consumer with a selector pulls only matching messages; non-matching messages stay in the queue for another matching consumer or until timeout/expiration/other rules apply. If no consumer matches, a backlog can build up. On a **topic**, subscription/selector combinations affect each subscriber individually; non-matching messages do not automatically route to a "rejected-message queue".

Selectors cannot mutate message metadata, do not mean payloads were validated, and do not replace a Dead Letter Queue. When running multiple consumers partitioned by `JMSType` or `TenantId`, verify what happens to messages **matching no selector** before deploying to production.

### 6.3. Why Not Use JMSXDeliveryCount in Selectors?

`JMSXDeliveryCount` is assigned **on receive**, whereas selectors decide which messages will be delivered. Therefore, selector behavior referencing a provider-on-receive JMSX property is **undefined by the specification**. Configure broker retry/DLQ policies instead, and inspect `JMSXDeliveryCount` after receive for logging or handling decisions.

## 7. Complete Example: Java 17 + Jakarta Messaging 3.1 + Apache Artemis

This example creates a temporary queue and sends four `TextMessage`s with the same body shape yet differing in **`JMSType` / `TenantId` / `SchemaVersion`**. A consumer with a selector receives only the two matching messages. The first two messages also demonstrate `JMSXGroupID`/`JMSXGroupSeq`, and the receiver reads `JMSXDeliveryCount`.

### 7.1. Prerequisites

Requires JDK 17+, Maven, Docker, and port 61616 free. Start a test Artemis broker:

~~~bash
docker run --detach --rm --name jms-property-broker \
  -p 61616:61616 -p 8161:8161 \
  apache/artemis:latest-alpine
~~~

Wait for the broker to finish starting before running Java. The official image defaults to user/password `artemis`/`artemis`; never use demo credentials in real environments.

File layout:

~~~text
jms-property-demo/
├── pom.xml
└── src/main/java/example/jms/MessageMetadataDemo.java
~~~

### 7.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>jms-property-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>jakarta.jms</groupId>
            <artifactId>jakarta.jms-api</artifactId>
            <version>3.1.0</version>
        </dependency>
        <dependency>
            <groupId>org.apache.activemq</groupId>
            <artifactId>artemis-jakarta-client</artifactId>
            <version>2.37.0</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

This is a **pure JMS application to explain the API**, not Spring Boot. Next, section 8 shows those exact metadata operations in Spring's `JmsTemplate` and `@JmsListener`.

### 7.3. MessageMetadataDemo.java

~~~java
package example.jms;

import jakarta.jms.Connection;
import jakarta.jms.ConnectionFactory;
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import jakarta.jms.MessageConsumer;
import jakarta.jms.MessageProducer;
import jakarta.jms.Session;
import jakarta.jms.TemporaryQueue;
import jakarta.jms.TextMessage;
import org.apache.activemq.artemis.jms.client.ActiveMQConnectionFactory;

public final class MessageMetadataDemo {

    private MessageMetadataDemo() {}

    public static void main(String[] args) throws JMSException {
        ConnectionFactory factory =
                new ActiveMQConnectionFactory("tcp://localhost:61616");

        try (Connection connection =
                     factory.createConnection("artemis", "artemis")) {

            Session session = connection.createSession(
                    false, Session.AUTO_ACKNOWLEDGE);
            TemporaryQueue queue = session.createTemporaryQueue();
            MessageProducer producer = session.createProducer(queue);

            String selector =
                    "JMSType = 'order.created.v1' " +
                    "AND TenantId = 'acme' AND SchemaVersion >= 2";
            MessageConsumer consumer =
                    session.createConsumer(queue, selector);

            // Two matching messages: same JMSXGroupID, sequence 1 and 2.
            send(session, producer, "order.created.v1",
                    "acme", 2, "order-42", 1);
            send(session, producer, "order.created.v1",
                    "acme", 3, "order-43", 2);

            // Does not match TenantId.
            send(session, producer, "order.created.v1",
                    "other", 2, "order-44", 0);

            // Does not match JMSType.
            send(session, producer, "order.cancelled.v1",
                    "acme", 2, "order-45", 0);

            // Newly created Classic Connection starts in stopped state.
            connection.start();

            for (int i = 0; i < 2; i++) {
                Message message = consumer.receive(5_000);
                if (message == null) {
                    throw new IllegalStateException(
                            "Timed out waiting for matching message " + i);
                }
                System.out.printf(
                        "type=%s | tenant=%s | version=%d | body=%s | deliveries=%d%n",
                        message.getJMSType(),
                        message.getStringProperty("TenantId"),
                        message.getIntProperty("SchemaVersion"),
                        ((TextMessage) message).getText(),
                        message.getIntProperty("JMSXDeliveryCount"));
            }
        }
    }

    private static void send(
            Session session,
            MessageProducer producer,
            String type,
            String tenant,
            int version,
            String body,
            int groupSeq) throws JMSException {

        TextMessage message = session.createTextMessage(body);
        message.setJMSType(type);                           // Standard header
        message.setStringProperty("TenantId", tenant);      // App property
        message.setIntProperty("SchemaVersion", version);   // App property
        if (groupSeq > 0) {
            message.setStringProperty("JMSXGroupID", "order-batch-7");
            message.setIntProperty("JMSXGroupSeq", groupSeq);
        }
        producer.send(message);
    }
}
~~~

Observations to make:

1. **`setJMSType`** sets the standard header. No custom property named `JMSType` is created.
2. **`setStringProperty` / `setIntProperty`** set application metadata usable in selectors, **outside the body**.
3. **`JMSXGroupID` and `JMSXGroupSeq`** are set on the first two messages; these are the two client-settable JMSX properties.
4. **`JMSXDeliveryCount`** is read from the received message, populated by the provider.
5. The selector is created **before `start()`**; the consumer receives exactly the first two messages matching the condition.
6. The two non-matching messages may remain in the temporary queue while the consumer runs; when the `Connection` closes, the temporary queue's lifecycle ends too. This is purely a selection demo, not a full backlog-processing workflow.
7. The example uses a single `Connection`/`Session`/consumer on one thread, avoiding dispatch variations across competing consumers.

### 7.4. Run Command and Stdout

From the `jms-property-demo` directory:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=example.jms.MessageMetadataDemo
~~~

When the broker is ready, the selector is active, and messages are delivered for the first time, the lines printed by **`System.out.printf` in the app** are:

~~~text
type=order.created.v1 | tenant=acme | version=2 | body=order-42 | deliveries=1
type=order.created.v1 | tenant=acme | version=3 | body=order-43 | deliveries=1
~~~

Additional library/broker logs may appear depending on configuration. If redelivery occurs or the provider fails to deliver within 5 seconds, delivery counts or run output may differ; the output above represents the **typical happy path**, not a guarantee every run meets exact timing. Stop the container with `docker stop jms-property-broker` when finished.

### 7.5. Experimenting with Selectors and Properties

- Change the selector to `TenantId = 'other'`: only `order-44` matches; change the receive loop from two iterations to one so it does not time out.
- Change the selector to `JMSType = 'order.cancelled.v1'`: only `order-45` matches.
- Change `send(..., "acme", 2, ...)` to `send(..., "acme", 1, ...)`: that message no longer matches `SchemaVersion >= 2`.
- Change `setIntProperty("SchemaVersion", version)` to `setStringProperty("SchemaVersion", String.valueOf(version))`: numeric `>= 2` no longer matches as expected.
- Read `getStringProperty("JMSXGroupID")` on received messages to verify grouping metadata on the first two messages.

Each run creates a new temporary queue. Never compare queue depth across runs as though the previous queue persisted.

## 8. Using Metadata in Spring Framework JMS

In Spring, **`JmsTemplate`** creates/sends JMS messages via `ConnectionFactory` and `MessageConverter`. To populate `JMSType`/properties after body conversion, use a **`MessagePostProcessor`**:

~~~java
import org.springframework.jms.core.JmsTemplate;

// Method inside a Spring bean with an injected JmsTemplate.
void publish(JmsTemplate jmsTemplate) {
    jmsTemplate.convertAndSend(
            "orders.events",
            "{\"orderId\":\"42\"}",
            message -> {
                message.setJMSType("order.created.v1");
                message.setStringProperty("TenantId", "acme");
                message.setIntProperty("SchemaVersion", 2);
                message.setStringProperty("JMSXGroupID", "order-42");
                message.setIntProperty("JMSXGroupSeq", 1);
                return message;
            });
}
~~~

This is a **Spring snippet**, not a standalone Java `main` class: it requires Spring JMS starter/config, `ConnectionFactory`, `JmsTemplate`, and an existing destination. The snippet assumes `JmsTemplate`'s `MessageConverter` turns `String` into `TextMessage`; with default `SimpleMessageConverter`, this is normally true. If a custom converter produces another format, metadata is still attached via `MessagePostProcessor`.

On the receiving side, **`@JmsListener`** allows specifying a selector:

~~~java
import jakarta.jms.JMSException;
import jakarta.jms.Message;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
class OrderEventListener {

    @JmsListener(
        id = "orderCreatedListener",
        destination = "orders.events",
        selector = "JMSType = 'order.created.v1' " +
                   "AND TenantId = 'acme' AND SchemaVersion >= 2")
    public void onMessage(Message message) throws JMSException {
        String type = message.getJMSType();
        int deliveryCount =
                message.getIntProperty("JMSXDeliveryCount");
        String tenant = message.getStringProperty("TenantId");

        // Received business content is inside the body.
        String payload = message.getBody(String.class);

        System.out.printf(
                "type=%s tenant=%s delivery=%d payload=%s%n",
                type, tenant, deliveryCount, payload);
    }
}
~~~

A Spring Boot app needs Spring JMS/provider dependencies and broker config. Registering `@JmsListener` requires JMS infrastructure (Spring Boot auto-configures it when matching dependencies are present). The **listener container** manages connection/session/start/ack/transactions, while the selector runs on the JMS provider before Spring calls `onMessage`. Do not confuse **Jakarta `Message`** with Spring Messaging `MessageHeaders`: in this example the parameter is `jakarta.jms.Message`, so headers/properties are read via the Jakarta JMS API.

To route multiple event types, you can create multiple listeners with distinct selectors or one shared listener dispatching via `getJMSType()`; the choice depends on backlog, scalability, and operational contracts. A queue with multiple selector-filtered consumers must be designed so every valid message group has a receiver, otherwise messages will accumulate.

### 8.1. Preserving Metadata When Forwarding Between Systems

Suppose a listener receives JMS message A and needs to emit message B to another queue. B is a **new message** with its own `MessageID`/`DeliveryCount`; do not blindly copy all properties from A. Explicitly decide which metadata should carry forward: `CorrelationID` or business trace, `TenantId`, `SchemaVersion` per the new contract; **never copy `JMSXDeliveryCount`** from the old message onto the new message.

~~~java
jmsTemplate.convertAndSend("audit.events", payload, outgoing -> {
    outgoing.setJMSType("audit.recorded.v1");
    outgoing.setStringProperty("TenantId", tenant);
    outgoing.setStringProperty("OriginEventType", originalType);
    return outgoing;
});
~~~

This is a snippet: `jmsTemplate`, `payload`, `tenant`, and `originalType` come from the enclosing processing context. The new message created by the converter will have its own send/receive lifecycle.

## 9. Designing Reliable Contracts in Real Deployments

### 9.1. Assigning Metadata Ownership

| Metadata item | Who is responsible? | Consumer verification |
| --- | --- | --- |
| `JMSType` | Producer / contract owner | Valid type with a handler available |
| `SchemaVersion` | Producer per schema registry/contract | Supported version; parse body accurately |
| `TenantId` | Producer and auth layer | Actual authorization, not merely trusting metadata |
| `JMSXGroupID` / `JMSXGroupSeq` | Producer when grouping is needed | Stable group key; clear provider behavior |
| `JMSXDeliveryCount` | Provider on receive | Observe retries; never replace business idempotency |
| `JMSMessageID` | Provider | Transport trace; never replace business ID |
| `JMSCorrelationID` | Producer / application | Link request-reply or trace per convention |

### 9.2. Decisions Worth Documenting

- **`JMSType` catalog**: who owns it, whether names include versions, which consumer handles each type.
- **Property schema**: exact names, exact types, required vs. optional, allowed defaults, whether null/absent is permitted.
- **Consumer selectors**: coverage conditions, where unmatched messages go, upgrade rollout state.
- **Provider-dependent JMSX**: inspect with `getJMSXPropertyNames()`; test grouping, redelivery, broker restarts, and concurrency under deployment conditions.
- **Business keys**: include a business ID in body/properties; guard duplicates with DB/idempotency keys.
- **Permissions and data**: RBAC/ACLs on destinations, logs free of tokens/sensitive data, property size limits.

### 9.3. Common Mistakes

| Symptom | Root cause error | Fix |
| --- | --- | --- |
| `getJMSType()` returns `null` | Producer only called `setStringProperty("JMSType", ...)` or forgot header | Call `setJMSType` directly on the message before send |
| Selector misses messages | Case mismatch: `tenantId` vs. `TenantId` | Standardize property names and test selectors |
| Numeric selector fails to match | `setStringProperty("SchemaVersion", "2")` | Use `setIntProperty(..., 2)` |
| Messages pile up in queue | No consumer has a matching selector | Audit all consumers and backlogs |
| Reading `JMSXDeliveryCount` on producer | Property is set by provider on receive | Read only at the consumer after receive |
| Using `JMSXDeliveryCount` to pre-filter delivery | Selector behavior undefined per spec | Configure retry/DLQ on provider/container; read count on receive |
| Trusting `JMSXGroupID` for exactly-once | Message groups are not distributed transactions | Idempotency and transactions in the business store |
| Mixing `javax.jms` and `jakarta.jms` | Dependencies/APIs from two different generations | Pick one consistent namespace (Spring 6/Boot 3 uses `jakarta.jms`) |
| Editing property on received message throws exception | Properties are read-only | Create a new message, or understand `clearProperties` before using |
| Dots/hyphens in property names | Name violates selector identifier syntax | Use names like `EventVersion`, `TenantId` |
| Putting JSON inside a property | JMS properties do not support arbitrary DTOs | Put JSON in a `TextMessage` body |
| Copying `JMSXDeliveryCount` to outbound message | Confusing provider metadata with business metadata | Do not copy; outbound has its own delivery lifecycle |

## 10. Self-Check Scenarios

**Scenario A — Two messages share the same body but have different `JMSType`s.** One is `order.created.v1`, the other `order.cancelled.v1`. A consumer with selector `JMSType = 'order.created.v1'` receives only the first despite identical bodies. Lesson: `JMSType` is a header the provider can filter independently of the body.

**Scenario B — Producer sends `setStringProperty("SchemaVersion", "3")`.** Consumer uses selector `SchemaVersion >= 2`. Because the property has type `String`, numeric comparison cannot rely on integer literal `2`; the proper design is using an `int` property (or string-based selector per contract).

**Scenario C — Redelivery after rollback.** The consumer can observe `JMSXDeliveryCount=2` and `JMSRedelivered=true`; these properties aid delivery diagnostics, yet idempotency must still rely on a business key because side effects may have completed before ack/commit.

**Scenario D — Consumer receives messages without `TenantId`.** Selector `TenantId = 'acme'` evaluates to `UNKNOWN`, so the message does not match. That does not automatically send the message to a DLQ. Check the producer contract and unmatched-message handling policy.

**Scenario E — Two competing consumers on the same queue sharing `JMSXGroupID`.** Use grouping if the provider supports the required semantics to reduce the risk of messages in the same group landing on different workers. However, test real affinity, failover, and ordering; `JMSXGroupID` does not automatically turn everything into sequential/exactly-once processing.

**Scenario F — Listener receives a message and calls `clearProperties()`.** All property entries are deleted and properties become writable; the body remains, yet existing `TenantId`, `SchemaVersion`, and `JMSX` fields are no longer preserved as originally received. Never invoke this inadvertently.

### Exercises

1. Run the section 7 example, varying `JMSType`, `TenantId`, and `SchemaVersion` one by one to see which messages the selector picks.
2. Add boolean property `RequiresAudit` and test selector `RequiresAudit = TRUE`.
3. Iterate `getPropertyNames()` before/after receive; verify `JMSType` is absent from the `Enumeration` because it is a header.
4. Use `connection.getMetaData().getJMSXPropertyNames()` to list JMSX names advertised by Artemis. Identify which are supported yet not necessarily present on every message.
5. Write a test handler that performs a business action idempotently keyed by `OrderId`; simulate redelivery and prove no duplicate side effects occur.
6. In Spring JMS, change the selector on `@JmsListener` to match a different `JMSType`; observe queue depth when no listener matches.

## 11. Authoritative References

- Jakarta Messaging 3.1 specification, §§3.4.8, 3.5, 3.8: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Jakarta Messaging 3.1 API, `jakarta.jms.Message`: https://jakarta.ee/specifications/messaging/3.1/apidocs/jakarta.messaging/jakarta/jms/message
- Jakarta EE Tutorial — JMS concepts and message properties: https://jakartaee.github.io/jakartaee-documentation/jakartaee-tutorial/current/messaging/jms-concepts/jms-concepts.html
- Spring Framework — Sending a Message/MessagePostProcessor: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework — Annotation-driven Listener Endpoints: https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html
- Apache ActiveMQ Artemis — Docker: https://artemis.apache.org/components/artemis/documentation/latest/docker.html
