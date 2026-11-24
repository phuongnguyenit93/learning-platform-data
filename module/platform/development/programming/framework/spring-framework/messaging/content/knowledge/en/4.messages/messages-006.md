# Distinguishing Envelope Immutability from Payload Mutability

## Learning Objectives

After this lesson, you will be able to:

- Explain that a Message in Spring Messaging consists of a payload and headers.
- Distinguish the immutability of the envelope from the internal state of the payload object.
- Understand why creating a new Message from an old Message does not equate to copying the payload.
- Recognize the risks when multiple handlers or threads reference a mutable payload.
- Create independent snapshots using immutable DTOs or defensive copies.
- Distinguish copying the headers map from deep-copying header values.
- Choose safe ways to pass data when using synchronous channels, executors, or brokers.

## 1. A Message Has Two Distinct Parts

In Spring Messaging, a Message<T> wraps two components:

- **Payload:** the primary data that the producer wants to transmit, of generic type T. The payload can be a String, DTO, record, byte array, collection, or any object appropriate for the application.
- **Headers:** metadata describing the message, such as ID, timestamp, content type, correlation ID, destination, or application-defined information.

The structure can be visualized as follows:

~~~mermaid
flowchart TB
    M["Message<T>"]
    H["MessageHeaders<br/>Message metadata"]
    P["Payload T<br/>Data object"]
    M --> H
    M --> P
    H --> H1["ID, timestamp, content type"]
    H --> H2["Correlation ID, destination"]
    P --> P1["String / DTO / record"]
    P --> P2["List / Map / byte[] / mutable object"]
~~~

Spring designs Message as an immutable envelope. Common implementations such as GenericMessage retain the message's payload and headers after creation. MessageHeaders also provides an immutable headers map.

However, envelope immutability does not mean deep immutability of every object that the envelope references. If the payload is a mutable object, that object can still be modified after the Message is created.

This is the most important takeaway of the lesson:

**A Message can be immutable while the payload inside it remains mutable.**

## 2. What Does Envelope Immutability Mean?

The envelope is the outer shell holding references to the payload and metadata. Its immutability means that after a Message is created, the application does not use that Message as a structure to replace the payload or directly modify the headers map.

For example:

~~~java
Message<String> message = MessageBuilder
        .withPayload("ORD-56")
        .setHeader("eventType", "order.created")
        .build();
~~~

After creation, you can read:

~~~java
String orderId = message.getPayload();
Object eventType = message.getHeaders().get("eventType");
~~~

But you cannot use the Message's headers map to modify it directly:

~~~java
message.getHeaders().put("traceId", "trace-56");
~~~

MessageHeaders is an immutable map; direct mutating operations such as put are rejected with UnsupportedOperationException.

If you need to add or replace a header, create a new Message via MessageBuilder:

~~~java
Message<String> tracedMessage = MessageBuilder
        .fromMessage(message)
        .setHeader("traceId", "trace-56")
        .build();
~~~

The result is a new envelope with new metadata. This approach keeps an already-created Message from being modified in place and helps readers recognize when the data was packaged.

## 3. Payload Can Be Mutable Even Though Message Is Immutable

The payload is an ordinary Java object. Spring does not automatically deep-clone or freeze the internal state of that object when creating a Message.

Common payload examples:

| Payload type | Mutability | Notes |
|---|---|---|
| String | Immutable | Can be safely shared with respect to String's own state |
| Integer, Long, Boolean | Immutable | Wrappers for primitive values |
| Java record | Shallowly immutable | Components can still be mutable objects |
| DTO with setters | Usually mutable | Can be changed after sending |
| ArrayList or HashMap | Mutable | Elements can be added, removed, or replaced |
| byte[] | Mutable | Individual elements can be modified |
| Date | Mutable | Has APIs that mutate the time |
| Custom object | Depends on design | Need to inspect fields and nested objects |

For example, if the payload is a DTO with setters:

~~~java
final class OrderPayload {
    private final String orderId;
    private String status;

    OrderPayload(String orderId, String status) {
        this.orderId = orderId;
        this.status = status;
    }

    String getOrderId() {
        return orderId;
    }

    String getStatus() {
        return status;
    }

    void setStatus(String status) {
        this.status = status;
    }
}
~~~

Creating a Message does not make the setStatus() method disappear. Any component that still holds a reference to OrderPayload can change status.

Therefore, do not infer that "once wrapped in a Message, the data is protected from modification." Message protects the envelope structure by design; the responsibility of protecting payload state remains with the application.

## 4. Creating a New Message Does Not Mean Copying the Payload

A common mistake is thinking that MessageBuilder.fromMessage(existing) creates an independent copy of the entire object graph.

Normally, this operation creates a new Message based on the old Message and retains the existing payload reference, unless the application explicitly provides a different payload.

For example:

~~~java
Message<MutableOrder> original = MessageBuilder
        .withPayload(order)
        .setHeader("eventType", "order.created")
        .build();

Message<MutableOrder> withTrace = MessageBuilder
        .fromMessage(original)
        .setHeader("traceId", "trace-56")
        .build();
~~~

The two Messages can be two different envelopes pointing to the same payload object:

~~~text
original -----------+
                    +----> same MutableOrder
withTrace ----------+
~~~

Therefore:

- Changing headers when creating withTrace does not modify original's headers map.
- Mutating the order object is still observed through the payload of both Messages.
- If two consumers process on different threads, concurrently accessing the mutable object can cause a race condition.

You must distinguish **copying the envelope** from **copying the payload data**. These are two separate operations.

## 5. An Immutable Header Map Also Does Not Guarantee All Header Values Are Immutable

MessageHeaders protects the map structure: the application cannot add, remove, or replace mappings directly through the packaged map. Yet a value stored in the map can still be a mutable object.

For example:

~~~java
List<String> tags = new ArrayList<>();
tags.add("new");

Message<String> message = MessageBuilder
        .withPayload("ORD-56")
        .setHeader("tags", tags)
        .build();

tags.add("priority");
~~~

The headers map was not modified via put/remove, yet the List object referenced from the header has changed. When reading message.getHeaders().get("tags"), the application can see both elements.

This is also shallow immutability. If safe metadata is needed, prefer immutable values such as String, numbers, enums, or immutable metadata objects. If a collection must be stored, make a copy and consider the immutability of each element as well.

For example, List.copyOf(tags) creates a list where elements cannot be added/removed via the List API, yet this is still a shallow copy: objects inside the list are not automatically deep-cloned.

## 6. Runnable Java Example: New Envelope, Shared Payload

The complete example below illustrates four things:

1. Creating a Message containing a mutable payload.
2. Using MessageBuilder.fromMessage() to create a new envelope with an additional header.
3. Mutating the payload and observing that both Messages see the new state.
4. Creating a defensive copy of the payload to obtain an independent snapshot.

### 6.1. Maven configuration

The example uses Java 17 and Spring Framework 6.2.8. Use the Spring Framework BOM to manage dependency versions:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>message-payload-mutability</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework</groupId>
                <artifactId>spring-framework-bom</artifactId>
                <version>6.2.8</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-messaging</artifactId>
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

### 6.2. Complete program

Create the file src/main/java/demo/MessagePayloadMutabilityDemo.java:

~~~java
package demo;

import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

public class MessagePayloadMutabilityDemo {

    static final class MutableOrder {
        private final String orderId;
        private String status;

        MutableOrder(String orderId, String status) {
            this.orderId = orderId;
            this.status = status;
        }

        String getOrderId() {
            return orderId;
        }

        String getStatus() {
            return status;
        }

        void setStatus(String status) {
            this.status = status;
        }

        MutableOrder copy() {
            return new MutableOrder(orderId, status);
        }
    }

    public static void main(String[] args) {
        MutableOrder order = new MutableOrder("ORD-56", "CREATED");

        Message<MutableOrder> original = MessageBuilder
                .withPayload(order)
                .setHeader("eventType", "order.created")
                .build();

        Message<MutableOrder> newEnvelope = MessageBuilder
                .fromMessage(original)
                .setHeader("traceId", "trace-56")
                .build();

        System.out.println("sameMessage=" + (original == newEnvelope));
        System.out.println(
                "samePayload="
                        + (original.getPayload() == newEnvelope.getPayload())
        );

        // Both Messages still reference the same order object.
        order.setStatus("PAID");

        System.out.println(
                "original.status=" + original.getPayload().getStatus()
        );
        System.out.println(
                "newEnvelope.status=" + newEnvelope.getPayload().getStatus()
        );

        // Create an independent payload and retain the required metadata.
        Message<MutableOrder> snapshot = MessageBuilder
                .withPayload(original.getPayload().copy())
                .setHeader(
                        "eventType",
                        original.getHeaders().get("eventType")
                )
                .setHeader(
                        "traceId",
                        newEnvelope.getHeaders().get("traceId")
                )
                .build();

        // MessageHeaders does not allow modifying the map directly.
        try {
            original.getHeaders().put("extra", "value");
            System.out.println("headersMutable=true");
        }
        catch (UnsupportedOperationException ex) {
            System.out.println("headersMutable=false");
        }

        // Mutate the original object again.
        order.setStatus("SHIPPED");

        System.out.println(
                "original.status.afterSecondMutation="
                        + original.getPayload().getStatus()
        );
        System.out.println(
                "newEnvelope.status.afterSecondMutation="
                        + newEnvelope.getPayload().getStatus()
        );
        System.out.println(
                "snapshot.status.afterSecondMutation="
                        + snapshot.getPayload().getStatus()
        );
    }
}
~~~

Run from the directory containing pom.xml:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=demo.MessagePayloadMutabilityDemo
~~~

Stdout:

~~~text
sameMessage=false
samePayload=true
original.status=PAID
newEnvelope.status=PAID
headersMutable=false
original.status.afterSecondMutation=SHIPPED
newEnvelope.status.afterSecondMutation=SHIPPED
snapshot.status.afterSecondMutation=PAID
~~~

### 6.3. Analyzing the output

sameMessage=false indicates that original and newEnvelope are two different envelopes. The traceId header was added on the new envelope.

samePayload=true indicates that both Messages reference the same MutableOrder object. When order.setStatus("PAID") is called, both read the PAID status.

Next, the program creates snapshot by calling copy() on the payload. Snapshot preserves the PAID status at the time of copying. When the original object transitions to SHIPPED, snapshot's payload still keeps PAID.

headersMutable=false confirms that the MessageHeaders map does not allow direct modification via put.

This example proves that creating a new Message and creating a payload copy are two distinct operations. If you want a message to preserve data as of the moment it occurred, the producer must use an immutable payload or proactively create an independent copy.

## 7. Safer Ways to Create Payloads

There are several ways to reduce the risk of sharing mutable state. Choose the approach suited to data size, performance, and communication boundaries.

### 7.1. Prefer immutable DTOs

An immutable DTO provides no setters and holds only immutable values:

~~~java
public record OrderCreated(
        String orderId,
        String customerId,
        long totalAmount
) {}
~~~

With components being String and primitive types, this record is well suited as an immutable payload. The producer can share it without worrying about a consumer mutating a field.

However, a record only guarantees shallow immutability. If a component is List<MutableItem>, the list or individual MutableItem instances can still change. Make defensive copies and use immutable elements when a deep snapshot is needed.

### 7.2. Use defensive copies when receiving or sending

If business logic needs to keep a snapshot, create a new object instead of passing a reference to an object currently used in multiple places.

~~~java
MutableOrder payloadSnapshot = order.copy();

Message<MutableOrder> message = MessageBuilder
        .withPayload(payloadSnapshot)
        .setHeader("eventType", "order.created")
        .build();
~~~

For collections, understand the depth of the copy:

- new ArrayList<>(source) creates a new list but keeps the same element references.
- List.copyOf(source) creates a list that cannot be modified via the List API, yet does not deep-clone elements.
- A deep copy must also copy nested mutable objects, or convert the data into an appropriate immutable structure.

A deep copy is not always necessary. If the payload is already immutable or data ownership is clearly transferred, copying the entire object graph can consume resources without increasing safety.

### 7.3. Do not let the producer keep mutating a sent object

A useful convention is that after sending a Message, the producer stops mutating the handed-over payload. This convention is easy to follow when the payload is immutable or treated as read-only data.

If the producer still needs to use the data to update state, create a separate payload for the message. Do not rely on the consumer finishing its read before the producer mutates the object, because processing timing can change when a channel switches from synchronous to asynchronous.

### 7.4. Use appropriate data types for headers

Headers should carry small, clearly meaningful, and easily shareable metadata:

- String for correlation ID, event type, or destination.
- Enum or numeric values for types and priority levels.
- Timestamps or content types following application conventions.

Avoid putting mutable business DTOs, mutable collections, or objects with complex lifecycles into headers. If a header value is a mutable object, the immutable map does not protect the internal state of that object.

## 8. Risks When Processing Across Multiple Threads

When a Message is sent over a synchronous channel, the handler may run immediately on the producer thread. When the channel dispatches through an executor, the handler may run on a worker thread. Changing threads does not automatically create a copy of the payload.

If producer and consumer reference the same mutable payload, the following can happen:

- **Race condition:** the producer modifies a field at the exact moment the consumer reads it.
- **Inconsistent snapshot:** the consumer reads some fields before the producer's update and other fields after the update.
- **Unexpected mutation:** the first consumer mutates the object, and the second consumer sees altered data.
- **Hard-to-reproduce bugs:** the program runs fine when the handler is fast, yet fails when the executor is busy or the system is under high load.

A standard executor has memory visibility guarantees upon task submission, ensuring operations that happen-before submission are visible when the task starts. That does not make the object immutable, nor does it protect against concurrent modifications after submission.

Therefore, the safe approach is usually:

1. Finalize payload data before sending.
2. Use immutable DTOs or separate snapshots.
3. Do not share mutable collections or arrays across consumers.
4. If state must be shared, use appropriate synchronization and clearly define ownership.
5. Re-evaluate when switching from a synchronous channel to an executor or broker, because processing timing changes.

## 9. When a Message Crosses a Broker or Process Boundary

Some adapters serialize the payload into bytes before sending over a transport. A consumer in another process usually receives an object deserialized from the transmitted data, so that object is not the same Java reference as the producer's object.

However, this does not mean serialization automatically solves every problem:

- The payload may be mutated by the producer before or during serialization.
- Serialization timing depends on the adapter and configuration.
- Custom serializers may omit fields, alter types, or fail to support certain objects.
- Headers may be mapped to protocol-specific metadata; not every header object can cross the wire.
- If using an in-memory channel, there is no serialize/deserialize boundary, so the payload may still be the exact same reference.

Therefore, design the payload as an event or DTO with a clear schema containing the data needed at the moment it occurs. Do not rely on the broker always creating a proper snapshot without checking the actual serializer and adapter.

## 10. Distinguishing Common Operations

| Operation | Envelope | Payload | Headers |
|---|---|---|---|
| Create Message via withPayload(existingObject) | Creates a new Message | Keeps the passed-in reference | Creates metadata for the Message |
| Create Message via fromMessage(existing) then setHeader | Creates a new Message | Usually keeps the same payload reference | Creates header set for the new Message |
| Call getHeaders().put(...) | Does not create a new Message | Unchanged | Rejected because MessageHeaders is immutable |
| Create new Message with payload.copy() | Creates a new Message | Uses a new payload object copied by the application | Keeps only metadata selected by the application |
| Use an immutable DTO | Creates a new Message | Payload state cannot be changed via the DTO's public API | Independent of payload immutability |

The phrase "copy a Message" should be used carefully. It can mean creating a new envelope, copying the headers map, or deep-copying the payload. Be explicit about which kind of copy is being performed.

## 11. Common Mistakes

1. **Assuming that because Message is immutable, the payload is also immutable:** the envelope and the payload object are two different layers.
2. **Assuming fromMessage() deep-clones the payload:** the builder creates a new Message but does not automatically copy the payload's object graph.
3. **Mutating an object after sending:** the consumer may see the new state if the reference is still shared.
4. **Assuming immutable headers mean immutable header values:** the map forbids modifying mappings, yet values can be mutable objects.
5. **Using a record and assuming everything is immutable:** records are only shallowly immutable; collection and object components can still be mutable.
6. **Using List.copyOf() as a deep copy:** the new list forbids structural modification, yet mutable elements are still shared.
7. **Sharing a byte[] across handlers:** the byte array can be modified after sending.
8. **Switching a channel to an executor without reviewing the payload:** moving processing to another thread exposes race conditions that were hidden in a synchronous flow.
9. **Relying on the broker to create a snapshot:** you must determine when the adapter serializes and what data is actually transmitted.
10. **Copying the entire object graph unnecessarily:** deep copying has a cost; create snapshots only at boundaries where independence must be guaranteed.

## 12. Self-Check Questions

1. What components does a Message<T> consist of?
2. Why can a Message be immutable while its payload still changes?
3. Does MessageBuilder.fromMessage() create a new envelope or deep-clone the payload?
4. Can two different Messages reference the same payload?
5. Why does an immutable MessageHeaders not protect a List stored as a header value?
6. What kind of immutability does a Java record guarantee? When is a defensive copy needed?
7. What is the difference between new ArrayList<>(source) and a deep copy?
8. Why is mutating a payload after sending more dangerous when using an executor?
9. Does serialization through a broker always guarantee an accurate point-in-time snapshot?
10. When should you use an immutable DTO, a defensive copy, or synchronization mechanisms?

## 13. Conclusion

Spring Messaging provides a Message envelope with a payload and headers. MessageHeaders protects the metadata structure, and common Message implementations are designed not to be modified directly after creation. Yet the payload and values inside headers can still be mutable objects.

Creating a new Message with MessageBuilder.fromMessage() helps alter the envelope, such as adding a correlation ID, without by default creating an independent copy of the payload. If producer and consumer both reference a mutable object, changes from one side can appear on the other and cause errors during concurrent processing.

To preserve data accurately as of the time it was produced, prefer immutable payloads or create appropriate defensive copies. At the same time, inspect nested objects inside both payloads and header values; the shallow immutability of a map or record is no substitute for designing clear data ownership.

## Official References

- Spring Framework Messaging API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/package-summary.html
- Message API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/Message.html
- MessageHeaders API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageHeaders.html
- GenericMessage API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/GenericMessage.html
- MessageBuilder API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageBuilder.html
- MessageHeaderAccessor API: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/MessageHeaderAccessor.html
