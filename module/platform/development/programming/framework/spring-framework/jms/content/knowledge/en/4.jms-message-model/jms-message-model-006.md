# ObjectMessage and Dependency on Java Serialization

> **Goal:** Understand what `jakarta.jms.ObjectMessage` transfers through a broker, why payloads depend on Java Serialization and producer/consumer classes, how Spring JMS automatically selects `ObjectMessage` when encountering `Serializable`, compatibility and security risks, and how to design more resilient message formats for integrated systems.

## 1. What Is ObjectMessage?

**`ObjectMessage` is a JMS/Jakarta Messaging `Message` type whose body contains a Java object implementing `java.io.Serializable`.** The API is defined in `jakarta.jms.ObjectMessage` (Spring Framework 6+ uses `jakarta.jms`; older Spring 5/JMS documentation may use `javax.jms`).

Core APIs:

~~~java
// Jakarta Messaging API snippet, requires a valid jakarta.jms.Session.
ObjectMessage message = session.createObjectMessage();
message.setObject(aSerializableObject);
Serializable body = message.getObject();

// Shorter creation form:
ObjectMessage other = session.createObjectMessage(aSerializableObject);
~~~

The two lines `setObject` / `getObject` respectively write and retrieve a Java object. `aSerializableObject` must be declared/instantiated in the application; the snippet above illustrates the API and **is not a standalone Java program**.

Key points to grasp:

- This is a **JMS message body type**, not a language-independent data format.
- `setObject(Serializable)` accepts **one object**; that object may contain an entire reference graph (nested objects, collections) provided it is properly serializable.
- JMS headers (`JMSMessageID`, `JMSCorrelationID`, `JMSRedelivered`, etc.) and message properties exist **outside the body**; `ObjectMessage` does not turn headers into fields on the Java object.
- `setObject` captures a **snapshot** of the object's state at call time; mutating the original object afterward does not alter the message body. Providers may have their own storage/transfer mechanisms, yet must honor this contract.
- `getObject()` returns `Serializable`; the caller can cast it, or use `message.getBody(ExpectedType.class)` where appropriate. Both involve restoring the Java object and do not eliminate deserialization risks.
- A received body is in read-only mode; calling `setObject` again on a received message can throw `MessageNotWriteableException` unless `clearBody` is called per the API.

**Distinguish from other body types:**

| JMS message type | Body | Dependency on Java classes |
| --- | --- | --- |
| `TextMessage` | A text string (usually JSON/XML) | Low when using a language-independent schema |
| `BytesMessage` | Bytes in an agreed format (e.g. Protobuf/Avro) | Depends on codec/schema, does not require Java Serialization |
| `MapMessage` | Name/value fields of JMS-allowed types | Depends on field schema; not an arbitrary object graph |
| `StreamMessage` | Stream of JMS-supported typed values | Requires knowing exact field order/types |
| **`ObjectMessage`** | `Serializable` Java object | **High**: class, package, serial form, classloader, and Java runtime |

Not every payload shaped like a "business object" needs `ObjectMessage`. You can send the **object's data** as JSON in a `TextMessage` or a binary schema in a `BytesMessage`.

## 2. What Actually Happens in Java Serialization?

A Java object in memory has references, fields, and a runtime type. The broker does not share a heap with producers or consumers. When transmitting an `ObjectMessage`, the provider handles a representation suitable for storage/transport; on the receiving side, the Java object must be reconstructed under Java Serialization compatibility rules.

~~~text
Producer JVM (class com.acme.events.InvoiceCreated)
    |
    | session.createObjectMessage(payload)
    | or JmsTemplate.convertAndSend(payload)
    v
ObjectMessage: body is a snapshot of the Serializable object
    |
    | JMS provider/client encodes and sends via broker
    v
Broker: stores/routes message per semantics and configuration
    |
    v
Consumer JMS client / Java classloader
    |
    | deserialize: requires compatible class + allowed object graph
    v
InvoiceCreated object in consumer JVM
    |
    v
Business handler validates ID, schema, and processes
~~~

**`Serializable` is a marker interface** with no methods a class must implement. Java serialization has specific rules for instance fields, nested objects, class hierarchies, `serialVersionUID`, `writeObject`/`readObject`, `Externalizable`, or serialization proxies. An object implementing `Serializable` that holds a field referencing a non-serializable object can still fail during serialization.

Example:

~~~java
import java.io.Serial;
import java.io.Serializable;

public final class InvoiceEvent implements Serializable {
    @Serial
    private static final long serialVersionUID = 1L;

    private final String invoiceId;
    private final long totalMinor;

    public InvoiceEvent(String invoiceId, long totalMinor) {
        this.invoiceId = invoiceId;
        this.totalMinor = totalMinor;
    }

    public String invoiceId() {
        return invoiceId;
    }

    public long totalMinor() {
        return totalMinor;
    }
}
~~~

This is a **valid standalone Java 17+ class** saved as `InvoiceEvent.java`. `String` is serializable and `long` is primitive, so this simple payload can be encoded by Java Serialization. Marking `implements Serializable` does **not** generate JSON and does **not** define a shared schema version for other languages.

### 2.1. Which Parts Are Stored?

- Instance fields can be serialized according to the class rules; `static` fields are not per-instance state in the serialized stream.
- `transient` fields are normally omitted under default serialization; after deserialization they hold default values unless restored by custom code/methods. `transient` alone is not a complete security control; secrets can still leak via other fields or custom logic.
- The object graph of referenced fields must satisfy serialization requirements or be handled via custom serialization. `implements Serializable` on the outer class alone does not guarantee every nested field is valid.
- Serialization can preserve reference topology/shared references within a single object graph; it does **not** guarantee that the received object and sent object are the same instance across two JVMs.
- The reconstructed object requires the matching class; for regular classes, constructor invocation during deserialization does not work like instantiating every object with `new`. Do not assume constructor/setter business validation always executes when receiving Java serialization.
- Collections, enums, records, and certain JDK classes follow special rules. Records in modern Java support `Serializable` with different restoration/versioning mechanics than regular classes; do not mechanically apply every `serialVersionUID` trick of ordinary classes to records.

### 2.2. A Snapshot Is Not a Live Object

~~~java
// Illustration with class MutablePayload implements Serializable
MutablePayload data = new MutablePayload("draft");
ObjectMessage message = session.createObjectMessage(data);
data.setStatus("approved");

// message still reflects the "draft" state at set/createObjectMessage time.
// Do not rely on mutating data afterward to update the created message.
~~~

This is an illustrative snippet requiring definitions of `MutablePayload` and `Session`. Published events should be treated as **immutable facts valid at publication time**, not pointers to a still-mutating aggregate.

## 3. Standalone Java 17 Example: Serialization and Nested Field Errors

A pure JDK example lets you observe the **core dependency** without a broker or Spring. It uses `ObjectOutputStream` / `ObjectInputStream` over a byte array of a **locally created, trusted object**. This code does not read data from the network or external input.

Create `SerializationProbe.java`:

~~~java
import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.NotSerializableException;
import java.io.ObjectInputStream;
import java.io.ObjectOutputStream;
import java.io.Serial;
import java.io.Serializable;

public final class SerializationProbe {

    public static void main(String[] args) throws Exception {
        InvoiceDraft original = new InvoiceDraft("INV-7", 5500);

        byte[] encoded;
        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(original);
            out.flush();
            encoded = buffer.toByteArray();
        }

        InvoiceDraft restored;
        try (ObjectInputStream in = new ObjectInputStream(
                new ByteArrayInputStream(encoded))) {
            restored = (InvoiceDraft) in.readObject();
        }

        System.out.println("same reference: " + (original == restored));
        System.out.println("restored: " + restored);

        try (ByteArrayOutputStream buffer = new ByteArrayOutputStream();
             ObjectOutputStream out = new ObjectOutputStream(buffer)) {
            out.writeObject(new BadPayload());
        } catch (NotSerializableException e) {
            System.out.println("nested field failure: "
                    + e.getClass().getSimpleName());
        }
    }

    static final class InvoiceDraft implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String invoiceId;
        private final int amountMinor;

        InvoiceDraft(String invoiceId, int amountMinor) {
            this.invoiceId = invoiceId;
            this.amountMinor = amountMinor;
        }

        @Override
        public String toString() {
            return "InvoiceDraft(" + invoiceId + "," + amountMinor + ")";
        }
    }

    static final class BadPayload implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final Object unconvertible = new Object();
    }
}
~~~

Run in the directory containing the file:

~~~bash
javac SerializationProbe.java
java SerializationProbe
~~~

`javac` and `java` must use JDK 17+; the example requires no external libraries. **Exact expected stdout:**

~~~text
same reference: false
restored: InvoiceDraft(INV-7,5500)
nested field failure: NotSerializableException
~~~

Lesson: the deserialized object has a **new identity**; `BadPayload` implemented `Serializable`, yet its `new Object()` field is not serializable, so `ObjectOutputStream` threw `NotSerializableException`. In JMS, the underlying failure may be wrapped by the provider as `MessageFormatException` / `JMSException`, and then wrapped by Spring as a conversion or `JmsException`; **do not write code relying on one fixed exception chain across all providers**.

## 4. Why Does ObjectMessage Create Tight Coupling Between Services?

With JSON messages, consumers typically only need to understand the **data schema**. With Java-serialized objects, consumers usually also need a **compatible Java class definition** matching the serialized class:

1. **Full class name (package + name) and classloader:** the producer serializes `com.example.billing.InvoiceEvent`; if the consumer lacks that class or renames it to `com.example.contract.InvoiceEvent`, deserialization can fail with `ClassNotFoundException`.
2. **`serialVersionUID`:** many standard serializable classes carry an identifier for their serialized form. If the receiver and stream have mismatched UIDs, Java typically throws `InvalidClassException`.
3. **Fields and field types:** renaming, retyping, or adding/removing fields follows compatibility rules; some changes are permitted, yet old data may receive default values, causing incorrect business semantics.
4. **Nested class dependencies:** payloads containing `Money`, `Customer`, `Address`, etc. force consumers to know the entire graph and potentially its library dependencies.
5. **Custom serialization hooks:** `writeObject`, `readObject`, `writeReplace`, `readResolve`, or `Externalizable` can tie the serialized form to specific implementation code.
6. **Message retention time:** messages remain on the broker across deployments; new consumers must still be able to read objects published by older producers.
7. **Language boundaries:** Python, Go, and JavaScript do not automatically gain an equivalent Java Serialization contract merely by connecting to the same broker.

**Two Java classes with the same name are not automatically version-compatible.** Keeping `serialVersionUID` unchanged only passes one part of version checking; structural incompatibility, missing dependencies, or logic errors can still occur. Arbitrarily changing `serialVersionUID` to "fix an error" can completely break reading old backlog messages.

### 4.1. Upgrading Versions with Old Messages Still in the Queue

Suppose yesterday the producer published:

~~~text
com.shop.events.InvoiceReady
serialVersionUID = 1L
fields: invoiceId:String, amountMinor:long
~~~

Today the consumer deploys a new class, changing `amountMinor` to `BigDecimal` or moving the class to a new package. Unprocessed messages in the queue still carry the old serialized form. When the client receives them, reconstruction can fail **before the business handler is ever invoked**.

Common consequences: a poison message is redelivered repeatedly and lands in the DLQ; the new producer sends fine while the consumer cannot drain the backlog; tests running producer and consumer from the same build miss the problem completely.

Safer strategies if you are forced to use `ObjectMessage`:
- Use dedicated, minimal transport DTOs—never serialize ORM entities/proxies, Spring beans, sockets, connections, or dependency-heavy domain aggregates.
- Maintain a versioned shared contract library and test cross-version producer–consumer compatibility.
- Declare a stable `serialVersionUID` when serialized forms are **genuinely** compatible; heed the special rules for records.
- Test **new consumer reading messages serialized by old producer** and vice versa when doing rolling deployments.
- Define lifecycle rules for backlogs, TTL, DLQs, and when old classes may be retired.

### 4.2. Compatibility Comparison with JSON

| Requirement | ObjectMessage | JSON in TextMessage |
| --- | --- | --- |
| Non-Java receiver | Difficult, must understand Java serialized objects | Easier thanks to language-independent format |
| Java package/class refactoring | Can break deserialization | Can keep the JSON schema unchanged |
| Adding optional fields | Depends on Java serialization compatibility and code | Usually backward compatible if schema and consumers handle missing fields |
| Debugging messages in broker | Binary Java stream, hard to inspect and needs classes | Easy to inspect text payloads with authorized tools |
| Safety with malicious payloads | Risks deserialization gadgets / classpath code execution | No native Java deserialization; still must validate, bound schema/size, and configure JSON parsers safely |
| Typed Java DTO in application | Received directly once deserialized | Controlled JSON deserialization into specific DTOs |
| Long-term contract management | Coupled to Java implementation | Encourages language-independent, versioned schemas |

JSON does not guarantee backward compatibility automatically: you still need contracts for data types, optional/required fields, timestamps, monetary values, enums, unknown-field handling, schema versions, and testing.

## 5. Security: Deserialization Is a Trust Boundary

**Never deserialize an `ObjectMessage` from an untrusted source.** Native Java deserialization can invoke class logic while reconstructing the object graph. When suitable gadget classes exist on the classpath, malicious payloads can cause severe damage; even benign payloads can exhaust resources via overly large or deeply nested graphs.

Especially dangerous if:
- A broker/queue is shared among clients whose publishing you do not control.
- Producer and consumer have mismatched classpath versions.
- Data sits in a DLQ for a long time and is later replayed without provenance checks.
- A handler accepts arbitrary `Object` and uses casting/reflection after deserialization has already happened.
- "Trust all packages" is configured just to bypass incompatibility errors.

**`instanceof` after `getObject()` does not stop dangerous deserialization**: classes have already been instantiated before your type check executes.

Multiple layers of defense are needed:

1. **Reduce attack surface:** prefer `TextMessage`/`BytesMessage` with suitable codecs/schemas; avoid Java object deserialization for cross-service integration.
2. **Broker ACLs:** allow only authenticated producers to send to destinations; restrict publish/consume permissions, enable TLS, and isolate environments.
3. **JMS provider class/package allowlists:** check provider-specific settings, permit only genuinely required classes/packages, and test nested object graphs.
4. **JVM serialization filters (JEP 290, `ObjectInputFilter`)** where the deserialization stream/filter is under your control; **do not assume** one application filter configuration covers every provider/client library.
5. **Resource limits:** cap message size, object graph depth, reference counts, backlog, and retry counts; alert on deserialization failures.
6. **Dependency hygiene:** remove unnecessary gadget libraries; keep broker/client/JDK updated and re-test deserialization policies upon upgrades.
7. **DLQ/replay procedures:** do not deserialize arbitrary raw payloads in an app just to view/inspect them; use safe inspection tools, metadata, and access controls.

### 5.1. Differences Between ActiveMQ Artemis and ActiveMQ Classic

These are **product-specific settings**, not universal JMS settings:

- **Apache ActiveMQ Artemis** provides allowlist/denylist settings for `ObjectMessage` deserialization, e.g. system properties `org.apache.activemq.artemis.jms.deserialization.allowlist` and `org.apache.activemq.artemis.jms.deserialization.denylist`; `ConnectionFactory` configuration can override system properties. Check your actual client/broker version and all nested classes needed by the application.
- **ActiveMQ Classic** uses a different trusted-packages policy, notably `org.apache.activemq.SERIALIZABLE_PACKAGES`. **Do not copy Classic's property into Artemis** assuming it will take effect.

Illustrative Artemis property example (not a complete production configuration):

~~~properties
org.apache.activemq.artemis.jms.deserialization.allowlist=com.example.contract
~~~

Do not apply blindly: if the object graph contains valid classes from another package, they may be rejected too. In production, manage policies alongside client versions, test valid payloads, and test payloads outside the allowlist. If Java serialization is no longer strictly required, **migrating to `TextMessage`/`BytesMessage`** is the simpler design path.

## 6. How Does Spring JMS Interact with ObjectMessage?

Spring Framework provides `JmsTemplate` and `@JmsListener` on top of Jakarta Messaging. **The `MessageConverter` decides which JMS message type a business object is turned into**, not whether the method is named `send` or `convertAndSend`.

In Spring 6.x, the default `SimpleMessageConverter` converts:

| Java value passed to `convertAndSend` | JMS body type |
| --- | --- |
| `String` | `TextMessage` |
| `byte[]` | `BytesMessage` |
| `Map` with supported field types | `MapMessage` |
| Other `Serializable` object (e.g. `InvoiceEvent`) | **`ObjectMessage`** |
| Unsupported object type | May throw `MessageConversionException` |

On receive, this converter performs the reverse; for `ObjectMessage` it invokes object extraction/deserialization. **Potential surprise:** changing code from `jmsTemplate.send(...)` to `jmsTemplate.convertAndSend("orders", invoiceEvent)` can silently switch the system to Java serialization if the converter is `SimpleMessageConverter`.

~~~java
// Code snippet inside a Spring-managed service with JmsTemplate template
InvoiceEvent event = new InvoiceEvent("INV-7", 5500);

// Option 1: default converter may create ObjectMessage because InvoiceEvent is Serializable.
template.convertAndSend("invoices.object", event);

// Option 2: explicitly request ObjectMessage without guessing the converter.
template.send("invoices.object",
        session -> session.createObjectMessage(event));
~~~

The two options above are **alternatives**, and should not be run back-to-back if you only intend to publish one event. With a `JmsTemplate.send` callback, message creation is directly under your control; with `convertAndSend`, always check which converter is actually wired into the template.

### 6.1. At Which Layer Does Deserialization Occur?

A listener such as:

~~~java
@JmsListener(destination = "invoices.object")
public void handle(InvoiceEvent event) {
    System.out.println("Received invoice: " + event.invoiceId());
}
~~~

is a method snippet inside a Spring bean. When conversion is active, the container/adapter can deserialize `ObjectMessage` into `InvoiceEvent` **before invoking `handle`**. Consequently, a `ClassNotFoundException`, UID mismatch, or allowlist rejection can prevent the method from **ever executing**; a `try/catch` inside the handler cannot catch deserialization failures occurring in the preceding layer. Monitor error handlers, transactions/acks, and broker redelivery/DLQs.

This distinction does not depend heavily on whether you use `JMSContext` or `Session`: as long as the body remains a native Java serialized object, the risks persist.

## 7. Lab: Spring Boot 3.x, Java 17+: End-to-End ObjectMessage

This is a lab **in a trusted environment** to demonstrate Spring JMS actually transmitting a Java-serialized object. It uses Java 17+, **Spring Boot 3.x / Spring Framework 6.x** with `jakarta.jms`, Maven, and embedded Artemis. In production, use an external broker, ACLs, and versioned message formats.

### 7.1. Initialize Dependencies

Using Spring Initializr (https://start.spring.io/), generate a Maven project:

- Group: `com.example`
- Artifact: `objectmessagelab`
- Package: `com.example.objectmessagelab`
- Java: `17` or newer supported by the chosen Boot version
- Dependency: **Spring for Apache ActiveMQ Artemis** (`spring-boot-starter-artemis`)

Add the embedded broker dependency to `<dependencies>` in `pom.xml`:

~~~xml
<dependency>
    <groupId>org.apache.activemq</groupId>
    <artifactId>artemis-jakarta-server</artifactId>
</dependency>
~~~

With the Spring Boot parent/BOM generated by Initializr, let dependency management select compatible versions; do not manually pin an Artemis version mismatched with the client. This configuration targets Boot 3.x and **does not claim every latest Boot version has identical APIs/auto-configuration**.

### 7.2. Broker for the Lab

File `src/main/resources/application.properties`:

~~~properties
spring.artemis.mode=embedded
spring.artemis.embedded.queues=invoices.object
spring.jms.pub-sub-domain=false
~~~

`invoices.object` is just a demo queue name. You do not need to launch a separate Artemis server when embedding works. An embedded demo broker is not a production security/persistence configuration.

### 7.3. Complete Single-File Java Application

Save at `src/main/java/com/example/objectmessagelab/ObjectMessageLabApplication.java`:

~~~java
package com.example.objectmessagelab;

import java.io.Serial;
import java.io.Serializable;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.annotation.JmsListener;
import org.springframework.jms.core.JmsTemplate;
import org.springframework.stereotype.Component;

@SpringBootApplication
@EnableJms
public class ObjectMessageLabApplication {

    public static void main(String[] args) {
        SpringApplication.run(ObjectMessageLabApplication.class, args);
    }

    @Bean
    ApplicationRunner publisher(JmsTemplate template) {
        return args -> {
            InvoiceEvent event = new InvoiceEvent("INV-7", 5500);
            template.convertAndSend("invoices.object", event);
            System.out.println("Published: " + event.invoiceId());
        };
    }

    public static final class InvoiceEvent implements Serializable {
        @Serial
        private static final long serialVersionUID = 1L;

        private final String invoiceId;
        private final long amountMinor;

        public InvoiceEvent(String invoiceId, long amountMinor) {
            this.invoiceId = invoiceId;
            this.amountMinor = amountMinor;
        }

        public String invoiceId() {
            return invoiceId;
        }

        public long amountMinor() {
            return amountMinor;
        }
    }

    @Component
    public static class InvoiceReceiver {
        @JmsListener(destination = "invoices.object")
        public void receive(InvoiceEvent event) {
            System.out.println("Consumed: "
                    + event.invoiceId() + " / " + event.amountMinor());
        }
    }
}
~~~

Lab prerequisites: no custom `MessageConverter` bean replacing `SimpleMessageConverter`; broker/client allow deserializing the demo class; dependencies match Boot 3.x. `InvoiceEvent` lives in namespace `com.example.objectmessagelab` on both sender and receiver (in this lab they share one app).

Run from the project root directory:

~~~bash
./mvnw spring-boot:run
~~~

On Windows PowerShell:

~~~powershell
.\mvnw.cmd spring-boot:run
~~~

Alongside Spring/Artemis logs, expect lines like:

~~~text
Published: INV-7
Consumed: INV-7 / 5500
~~~

**The order of these two lines is not guaranteed** because the listener runs on another thread. `Published` indicates the template sent the message; `Consumed` appears after the Spring consumer deserializes and invokes the listener. Under retries, shutdowns, or reconfiguration, logs alone do not prove exactly-once delivery.

### 7.4. Step by Step from Code to Broker

1. `ApplicationRunner` creates an `InvoiceEvent` instance (which is `Serializable`).
2. `JmsTemplate.convertAndSend` asks `SimpleMessageConverter` to convert the object; the converter builds a Jakarta Messaging `ObjectMessage`.
3. The JMS provider turns the object into wire-transmittable data; the broker stores/routes it in the queue.
4. The Spring listener container receives the message and converts the body back into `InvoiceEvent` via the converter.
5. `InvoiceReceiver.receive` prints the reconstructed data.

If you deliberately add a non-serializable `new Object()` field, or change the UID/class in a separate consumer, you can observe errors at the serialization/deserialization layer. Conduct this experiment only in a local environment; never test malformed payloads against a production broker.

### 7.5. Why Not Use This Example as a Production Pattern?

The lab application places **producer and consumer in the same codebase/classpath**; that setup hides most coupling that surfaces when two independently deployed services split. It also omits ACLs, strict package allowlists, schema migration, idempotency, and backlog management. In multi-service environments, Java Serialization is generally a brittle choice for event contracts.

## 8. Alternative: Versioned JSON TextMessage with DTOs

For transmitting business data across services, it is usually better to define a **contract independent of Java implementation**, such as JSON:

~~~json
{
  "eventId": "evt-001",
  "eventType": "InvoiceCreated",
  "schemaVersion": 1,
  "invoiceId": "INV-7",
  "amountMinor": 5500
}
~~~

An event can be encoded inside a `TextMessage`, keeping key metadata in the body (and, where helpful, repeating type/version in controlled JMS properties). Both sides must agree on the schema and compatibility rules, especially when adding/removing/changing fields.

### 8.1. Sending JSON Strings with Spring JMS

Inside a Spring service with `JmsTemplate template`:

~~~java
String json = """
        {"eventId":"evt-001","eventType":"InvoiceCreated",
         "schemaVersion":1,"invoiceId":"INV-7","amountMinor":5500}
        """;

template.convertAndSend("invoices.json", json, message -> {
    message.setStringProperty("contentType", "application/json");
    message.setIntProperty("schemaVersion", 1);
    return message;
});
~~~

This is a **Java 17+ snippet**; it requires a `JmsTemplate` bean and the corresponding queue. With `SimpleMessageConverter`, `String` becomes a `TextMessage`. The `contentType` property is an application convention (not a mandatory JMS MIME header). The consumer receives `String` and parses it with a JSON library into a strongly typed DTO, validating version and data; **never invoke `ObjectInputStream`**.

### 8.2. When Using MappingJackson2MessageConverter

On Spring Framework 6.x with Jackson 2, you can also register `MappingJackson2MessageConverter` on both `JmsTemplate` **and** the listener factory/container under the same contract to automatically serialize DTOs as JSON in `TextMessage` or `BytesMessage`. Example configuration (a `@Bean` snippet inside `@Configuration`, requiring imports for `Bean`, `MessageType`, `MappingJackson2MessageConverter`, `Map`, and the DTO):

~~~java
@Bean
MappingJackson2MessageConverter jsonConverter() {
    var converter = new MappingJackson2MessageConverter();
    converter.setTargetType(MessageType.TEXT);
    converter.setTypeIdPropertyName("_type");
    converter.setTypeIdMappings(Map.of("invoice-created-v1",
            InvoiceCreatedDto.class));
    return converter;
}
~~~

Key considerations:
- Wire the converter into the **exact** template/listener container; declaring a bean alone does not guarantee every custom-created factory uses it.
- `setTargetType(MessageType.TEXT)` is necessary if you want JSON **`TextMessage`**, because the converter can default to `BytesMessage`.
- `_type` / mappings must be agreed upon by producer and consumer and avoid leaking raw Java class names; permit only expected target DTOs.
- Apply safe JSON parser policies; avoid enabling broad default polymorphic typing or deserializing arbitrary payloads into `Object` without an allowlist.
- On a different Spring Framework generation (e.g. Spring 7 / Jackson 3), **check the version-appropriate converter** rather than copying a class name absent from your classpath.

If automatic conversion is not needed, sending a `String` and parsing JSON explicitly is easier to audit and avoids hiding conversion behavior in implicit configuration.

### 8.3. When to Use BytesMessage?

`BytesMessage` is useful when an organization has adopted Avro, Protobuf, or another binary schema: the message body is a byte array and consumers use matching schemas/codecs. Those binary formats are **not synonymous** with native Java serialized streams. Schema registry/versioning, encoding, content type, maximum size, and cross-version compatibility rules are still required.

## 9. Strategy for Migrating from ObjectMessage to TextMessage

A common mistake is switching the publisher to JSON and updating the consumer immediately while an `ObjectMessage` backlog sits in the queue. The new consumer may fail to process old messages; conversely, an old consumer cannot understand the new `TextMessage`.

Controlled rollout steps:

1. **Map the landscape**: identify all producers/consumers, queues/topics, classes/payloads in use, `serialVersionUID`s, message TTLs, retries, DLQs, longest message retention window, and deployment rollback capabilities.
2. **Define the new contract**: event type, schema version, DTO, contentType, idempotency key, security, and encoding (JSON/Avro/Protobuf).
3. **Deploy updated consumers**: able to read the new format, tested with messages from old producers; if supporting dual formats on the same queue, route safely by type and keep old classes required for the backlog.
4. **Switch producers systematically**: use a new destination/version such as `invoices.v2` where practical so old and new paths stay isolated; if dual-publishing, guard against creating duplicate business effects.
5. **Drain/reconcile backlog and DLQ**: remove old class dependencies only after no object messages remain to be read or they have been migrated via a verified procedure.
6. **Monitor and retire the old path**: track message counts per format, conversion failures, redeliveries/DLQs, and processing latency. Once the new contract stabilizes, stop publishing the old format and revoke old permissions.
7. **Test rolling deployments**: producer v1 → consumer v2, producer v2 → consumer v1 (if overlapping), restarts with queued backlogs, DLQ replay, and failures between publish and ack.

Throughout migration, preserve **idempotency** and transaction boundaries. Changing encoding does not change delivery guarantees or concurrency. A message published twice during dual-publishing must not automatically trigger two business actions.

## 10. Common Incidents and How to Diagnose Them

| Symptom | Possible cause | How to check/resolve |
| --- | --- | --- |
| `NotSerializableException` on send | A nested field is not `Serializable` | Inspect the actual graph; avoid serializing full aggregates/ORM entities |
| `InvalidClassException` on receive | Incompatible `serialVersionUID`/serialized form | Compare artifact versions, UIDs, and backlog data; never change UIDs arbitrarily |
| `ClassNotFoundException` during deserialization | Consumer missing class/package/version | Check deployment classpath and serialized class namespace |
| Allowlist/denylist error | JMS client blocked a class in the graph | Check the **right provider's** policy; allow only genuinely required classes |
| `ClassCastException` after receive | Payload type differs from what handler expects | Set type/version properly, align producer–consumer contract; casts do not guard deserialization |
| `MessageConversionException` / `JmsException` | Converter cannot handle body or underlying error occurred | Check actual message type, converter bean, root cause, and DLQ |
| Listener code never entered, yet queue retries | Failure occurred before listener (deserialization/conversion) | Check container error logs, broker delivery count, error handler, and DLQ |
| New consumer misreads old messages | Changed classes/fields with existing queue backlog | Compatibility test against old payloads; drain/migrate under control |
| Non-Java consumer | Does not support native Java serialized form | Design a language-independent text/binary schema contract |
| Message appears as unreadable binary | It is a Java-serialized graph | Inspect metadata/broker tools safely; never deserialize unknown data just to "peek" |
| Duplicate business side effects after retry | Redelivery, transaction/ack decoupled from business DB | Idempotency keys, inbox/outbox, analyze transaction boundaries |
| Payload exposes sensitive data | Accidentally serialized entire object graph | Use minimal DTOs, restrict fields, enforce ACL/TLS, masking, and retention |

**Error note in Spring:** exceptions from broker/client/JMS APIs may be wrapped across multiple layers; log the root cause and `JMSRedelivered`/delivery count (if supported by the provider). Do not assume identical exception classes or error messages across different brokers.

## 11. Checklist: Choosing ObjectMessage vs. Another Format

**Only consider `ObjectMessage` when** there is a clear rationale: both producer and consumer are Java, within the same trust boundary, sharing the same lifecycle contract, every class in the object graph is understood and controlled, polyglot integration is unneeded, cross-version tests exist, and broker/client support required deserialization policies.

Before adopting it in a real design, answer:

- Are there any producers outside your team's control? Are broker ACLs and publish permissions tight?
- Will consumers always have classes matching object graphs sitting in the broker/DLQ?
- Have `serialVersionUID` and compatibility across rolling deployments been tested?
- Are there `transient` fields, circular references, nested library classes, ORM entities, lazy proxies, or stateful objects that should not be sent?
- Have client/provider applied allowlists and size/depth limits? Is it clear which parts are enforced by JVM filters?
- Are pre-handler deserialization failures logged, bounded in retries, and routed to a DLQ properly?
- Are Node.js/Python/Go consumers, payload inspection, or multi-month event retention required?
- Would switching to JSON `TextMessage` or schema-based binary `BytesMessage` reduce coupling?
- Once messages are published, do you need to remain able to read backlogs across multiple app versions?
- Are message schema/idempotency keys and producer–consumer ownership clearly documented?

**Design conclusion:** `ObjectMessage` can be convenient when trusted Java components need to pass a very short-lived internal DTO, but it embeds **Java serialization format and class coupling into the messaging contract**. For integrations/events between independently deployed services, schema-driven formats decoupled from Java implementation are easier to govern, safer, and easier to evolve.

## 12. Reinforcement Exercises

1. Using `SerializationProbe`, add a field `transient String ephemeral = "abc"`; predict its value after deserialization and explain why.
2. Replace `InvoiceDraft` with an object holding `java.net.Socket` or a custom non-`Serializable` object. Explain where the failure happens and why adding `implements Serializable` to the outer class alone is insufficient.
3. Suppose 50 `ObjectMessage`s of class `com.shop.v1.InvoiceCreated` sit in a queue and the team just renamed the class to `com.shop.v2.InvoiceCreated`. Analyze safe migration steps without losing the backlog.
4. Test `JmsTemplate.convertAndSend` with `String`, `byte[]`, `Map`, and a `Serializable` DTO. Predict the message body type under `SimpleMessageConverter`.
5. Write a JSON schema/contract for `InvoiceCreated` v1 and v2. Define optional new-field rules, `schemaVersion`, idempotency key, and how v1 consumers behave.
6. Suppose the JMS client blocks a class via an allowlist. Why does changing the handler to `receive(Object obj)` or checking `instanceof` after receive fail to secure the deserialization boundary?
7. A producer sends successfully, but the consumer crashes after writing to the database and before ack. Explain why **switching from `ObjectMessage` to `TextMessage` does not eliminate duplicate deliveries**.

## 13. References for Cross-Checking

- Jakarta Messaging 3.1 `ObjectMessage` API: https://jakarta.ee/specifications/platform/11/apidocs/jakarta/jms/objectmessage
- Jakarta Messaging 3.1 Specification, message bodies/object messages: https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html
- Oracle Java 17 `Serializable`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/io/Serializable.html
- Oracle Java Serialization, versioning: https://docs.oracle.com/en/java/javase/17/docs/specs/serialization/version.html
- Spring Framework 6.2 `SimpleMessageConverter` API: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/SimpleMessageConverter.html
- Spring Framework JMS sending/converting: https://docs.spring.io/spring-framework/reference/integration/jms/sending.html
- Spring Framework 6.2 `MappingJackson2MessageConverter` API: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/jms/support/converter/MappingJackson2MessageConverter.html
- Apache ActiveMQ Artemis security/ObjectMessage deserialization: https://artemis.apache.org/components/artemis/documentation/latest/security.html
- Apache ActiveMQ Classic ObjectMessage security: https://activemq.apache.org/components/classic/documentation/objectmessage
