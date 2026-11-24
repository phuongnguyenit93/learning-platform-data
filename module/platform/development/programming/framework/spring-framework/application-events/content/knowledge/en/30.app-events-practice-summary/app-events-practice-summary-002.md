# Creating Events with Immutable Records in Spring Framework Application Events

## 1. Objectives

When designing Spring Application Events, an event should describe **something that has already happened** using clear and stable data. For example: `OrderPlaced` stores `eventId`, `orderId`, the timestamp when it occurred, and the order lines that were placed. A listener receiving the event may run immediately on the publisher thread or run later on another executor. Therefore, **the event payload must not silently change after the time of publishing**.

Java `record` (stable since Java 16, works well with Java 17+) is a concise choice for creating such value objects: declare the data components once, and the compiler generates the constructor, accessors, `equals()`, `hashCode()`, and `toString()`. Records are well suited to representing internal domain events, though one important limitation must be understood: **a record is shallowly immutable**. The reference fields are final, but the objects they point to can still be mutable.

Lesson objectives:

1. Understand what an event record is and why **it does not need to inherit from `ApplicationEvent`** to be used in Spring.
2. Know how to use record components, compact constructors, validation, `List.copyOf`, and `Map.copyOf`.
3. Distinguish shallow immutability, unmodifiable collections, and **truly stable event payloads**.
4. Write, publish, and receive `OrderPlaced` using `ApplicationEventPublisher` + `@EventListener`.
5. Run a Java 17+ Spring Framework 6.2 example with deterministic stdout demonstrating **defensive copying**, validation, dispatch, and value equality.
6. Design `eventId`, `occurredAt`, versioning, snapshot data, idempotency, and serialization when integrating outside the application.
7. Avoid common pitfalls when events cross `@Async`, transaction, or message broker boundaries.

**Principle:** an event should be a **meaningful snapshot of data at the moment the event occurred**, not a reference to domain state that continues to mutate.

## 2. What Does a Java Record Provide?

A simple Java record:

~~~java
public record UserRegistered(
        String eventId,
        long userId,
        String email
) {}
~~~

You can instantiate it:

~~~java
UserRegistered event =
        new UserRegistered("evt-101", 42L, "user@example.test");

System.out.println(event.eventId()); // evt-101
System.out.println(event.userId());  // 42
~~~

The compiler generates components equivalent to the following contract:

- A `final` class extending `java.lang.Record`.
- Instance fields corresponding to the record components are `private final`.
- A canonical constructor accepting a value for each component.
- Accessors named **`eventId()`, `userId()`, `email()`** (not default JavaBean getters like `getEventId()`).
- `equals()` and `hashCode()` based on the components.
- `toString()` displaying the components according to record semantics.

A record can have methods, static fields, static nested types, implemented interfaces, and custom constructors subject to record rules. However, you cannot declare arbitrary extra instance fields outside the record components, and it cannot extend another business class because it already extends `java.lang.Record`.

### 2.1. Records Do Not Automatically Make Data Deeply Immutable

An error-prone example:

~~~java
public record WrongOrderPlaced(
        String orderId,
        List<String> productCodes
) {}
~~~

The fields of the record cannot be reassigned, but if the caller passes an `ArrayList`:

~~~java
List<String> original = new ArrayList<>();
original.add("SKU-A");
WrongOrderPlaced event = new WrongOrderPlaced("o-1", original);

original.add("SKU-B"); // event.productCodes() now also contains SKU-B.
event.productCodes().clear(); // Can even clear the data inside original.
~~~

Here `final` only prevents the record from changing the component's **reference**; it does not make the referenced object immutable. If the event is placed on an async queue and the publisher modifies `original` before the listener processes it, the listener can see unintended data or encounter data races.

### 2.2. Defensive Copying with `List.copyOf`

~~~java
public record OrderPlaced(
        String orderId,
        List<String> productCodes
) {
    public OrderPlaced {
        productCodes = List.copyOf(productCodes);
    }
}
~~~

This is a **compact canonical constructor**. Java automatically assigns the validated/replaced parameters to the final components after the constructor body completes. `List.copyOf` returns an **unmodifiable** list: you cannot call `add`, `remove`, or `set` on the list stored inside the event.

If the input is a mutable list, modifying the input afterward **does not change** the copied list inside the record. `List.copyOf` also rejects a `null` list or `null` elements. If the input is already a suitable unmodifiable list, the implementation may reuse the object instead of allocating a new copy; what matters is the unmodifiable contract.

However, `List.copyOf` still only copies **the list structure**, not deep-copying the elements. If `List<MutableLine>` contains mutable objects, calling `line.setQuantity(999)` can still mutate the event's contents. To make the event truly stable, use **immutable element types** such as records with immutable components, or deep-copy/convert elements into value objects.

### 2.3. `Map.copyOf`, `Set.copyOf`, and Arrays

For small metadata, `Map.copyOf(map)` is a similar choice. It creates an unmodifiable map isolated from mutations to the input mutable map, though it still does not deep-copy **object values**. It rejects `null` keys and values.

`Set.copyOf` can also be useful; when constructed from a collection with duplicate elements, set semantics retain only unique values.

With `byte[]`, `char[]`, or object arrays, **a record directly holds the reference to the mutable array**. For example:

~~~java
public record BadBinaryEvent(byte[] bytes) {}
~~~

Even though the `bytes` field is final, the caller can still modify `bytes[0]`, and the `bytes()` accessor exposes that exact array. If an array must be used, you must `clone()` both on input and on output:

~~~java
public record BinaryEvent(byte[] bytes) {
    public BinaryEvent {
        bytes = bytes.clone();
    }

    @Override
    public byte[] bytes() {
        return bytes.clone();
    }
}
~~~

Additional note: default equality on a record with an array component **does not deep-compare** array contents. If you want data-based equality, another choice such as an immutable `List<Byte>` or a value object with a proper `equals` is usually clearer. For large events, avoid copying big payloads unnecessarily: consider referencing a durably stored blob by ID/hash.

## 3. Why Are Records Especially Well Suited to Spring Events?

Spring Framework 4.2+ allows publishing **any object** as an event via `ApplicationEventPublisher.publishEvent(Object)`. If the object does not extend `ApplicationEvent`, Spring wraps it in a `PayloadApplicationEvent` for distribution. The `@EventListener` method can still receive **the original payload type**.

~~~java
// POJO/record: no need to extend ApplicationEvent.
public record InvoiceIssued(String invoiceId) {}

// In a Spring-managed service:
publisher.publishEvent(new InvoiceIssued("inv-100"));

// In a Spring-managed listener bean:
@EventListener
public void onInvoiceIssued(InvoiceIssued event) {
    System.out.println(event.invoiceId());
}
~~~

Spring selects the method based on the event type/payload type. This is an official mechanism, **not a reflection hack** and not reliant on Jackson serialization.

### 3.1. Why Can't a Record Extend ApplicationEvent?

A Java record already extends `java.lang.Record`; Java does not allow a record to extend another class. Spring's `ApplicationEvent` is a class (extending `EventObject`), so the following **will not compile**:

~~~java
// WRONG: a record cannot extend ApplicationEvent.
// public record OrderPlaced(String orderId) extends ApplicationEvent {}
~~~

You do not need to force a record into a subclass. Just use `publisher.publishEvent(record)` and `@EventListener` with the record parameter type. If you want to implement an interface to mark an event category, a record is still allowed to `implements` that interface.

### 3.2. An Event Object Is Not Persistence or a Message Broker

A record stabilizes **data**, but **does not change delivery semantics**:

- The default `SimpleApplicationEventMulticaster` usually dispatches synchronously on the publisher thread.
- `@Async @EventListener` can offload callbacks to a thread pool, but a record does not make the queue durable.
- `@TransactionalEventListener(AFTER_COMMIT)` controls **the processing phase** after commit; it does not automatically persist events to a durable outbox.
- If you need to send events to Kafka/RabbitMQ, a record can serve as the DTO to serialize, but you must explicitly configure the schema, publisher, broker, ACKs, retries, and idempotency.

An **immutable payload** prevents unexpected data mutations when listeners run at different times; it does not promise that the event will be delivered exactly once or survive a JVM crash.

## 4. Designing an Order Event Record

A practical business event should express something that has happened, avoiding overly generic names like `UpdateEvent` or carrying an entire `OrderEntity` object.

Suppose we want to express: an order has been placed. Meaningful fields include:

| Component | Meaning and choice |
| --- | --- |
| `eventId` | Immutable ID of the event occurrence for deduplication/redrive |
| `orderId` | Aggregate ID of the order |
| `occurredAt` | Timestamp when the business event occurred, using `Instant` |
| `lines` | Snapshot of order lines as `List<OrderLine>` |
| `metadata` | Non-sensitive attributes with immutable keys/values |
| `schemaVersion` (when externalized) | Version of the payload contract for external consumers |

**Using `Instant` instead of mutable `java.util.Date`** avoids many mutation and timezone bugs. When the event occurred (`occurredAt`) does not necessarily equal when the broker received it, the consumer processed it, or the database committed.

For `OrderLine`, choose a value object:

~~~java
public record OrderLine(String sku, int quantity) {
    public OrderLine {
        Objects.requireNonNull(sku, "sku");
        if (sku.isBlank() || quantity <= 0) {
            throw new IllegalArgumentException("Invalid order line");
        }
    }
}
~~~

`String` and primitive `int` are stable components; a list containing such immutable `OrderLine` instances can be considered a sufficiently safe snapshot for this simple problem.

### 4.1. Compact Constructor Validating Invariants

~~~java
public record OrderPlaced(
        String eventId,
        String orderId,
        Instant occurredAt,
        List<OrderLine> lines,
        Map<String, String> metadata
) {
    public OrderPlaced {
        if (eventId == null || eventId.isBlank()) {
            throw new IllegalArgumentException("Missing eventId");
        }
        if (orderId == null || orderId.isBlank()) {
            throw new IllegalArgumentException("Missing orderId");
        }
        Objects.requireNonNull(occurredAt, "occurredAt");

        lines = List.copyOf(lines);
        if (lines.isEmpty()) {
            throw new IllegalArgumentException("Order must have lines");
        }
        metadata = Map.copyOf(metadata);
    }
}
~~~

This is a valid constructor in Java 17. Inside a **compact constructor**, you do not need and are not allowed to write an explicit assignment `this.lines = lines` for a component; the compiler performs it at the end of the constructor body. You can validate and reassign **the `lines` parameter** before that implicit assignment step.

The constructor runs whenever an event is created via the canonical path, protecting invariants right at creation time. However, a Java record **does not by itself prove** that the event matches business state in the database; the service must ensure the event is created **after the appropriate business step** and that metadata has been verified.

### 4.2. Do Not Put Too Much Logic Inside the Event

An event record should only hold:

- Small, typed, meaningful snapshot data.
- Basic structural/value validation.
- No side effects.
- No database, network, or Spring bean calls inside the constructor.

Do not put email-sending logic, PaymentGateway calls, repository writes, or new event publishing inside the compact constructor. Events should be easy to construct, compare, serialize, and test.

If the constructor would need to query the DB to know whether `orderId` is valid, move that responsibility to the application/domain service and create the event only once business invariants have been confirmed.

## 5. Complete Java 17+ Maven Example

This example runs with **Spring Framework 6.2.12**, Java 17+, and Maven. No Spring Boot, database, web server, broker, or JUnit is needed to run main.

What it demonstrates:

1. An `ArrayList` and `HashMap` are turned into immutable snapshots inside the record.
2. The publisher mutates the input collections **after creating the event**; the record is unaffected.
3. Calling `add()` on `event.lines()` is blocked.
4. `@EventListener` receives the record directly via the `PayloadApplicationEvent` mechanism.
5. The default synchronous listener records exactly one event.
6. Two distinct record instances with the same component values yield `equals() == true`.
7. The compact constructor rejects a blank `eventId`.

### 5.1. Structure

~~~text
record-event-demo/
├── pom.xml
└── src/main/java/demo/ImmutableRecordEventDemo.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>record-event-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <version>3.13.0</version>
                <artifactId>maven-compiler-plugin</artifactId>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. src/main/java/demo/ImmutableRecordEventDemo.java

~~~java
package demo;

import java.time.Instant;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ImmutableRecordEventDemo {

    // Order line is a value object containing no mutable components.
    public record OrderLine(String sku, int quantity) {
        public OrderLine {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank() || quantity <= 0) {
                throw new IllegalArgumentException("Invalid order line");
            }
        }
    }

    // Event describes a business fact with a data snapshot.
    public record OrderPlaced(
            String eventId,
            String orderId,
            Instant occurredAt,
            List<OrderLine> lines,
            Map<String, String> metadata
    ) {
        public OrderPlaced {
            requireText("eventId", eventId);
            requireText("orderId", orderId);
            Objects.requireNonNull(occurredAt, "occurredAt");

            // Defensive copy: do not retain the publisher's mutable references.
            lines = List.copyOf(lines);
            if (lines.isEmpty()) {
                throw new IllegalArgumentException("Missing order lines");
            }
            metadata = Map.copyOf(metadata);
        }

        private static void requireText(String name, String value) {
            Objects.requireNonNull(value, name);
            if (value.isBlank()) {
                throw new IllegalArgumentException(name + " is blank");
            }
        }
    }

    public static final class OrderPublisher {
        private final ApplicationEventPublisher publisher;

        public OrderPublisher(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void place(OrderPlaced event) {
            publisher.publishEvent(event);
        }
    }

    public static final class OrderListener {
        private final List<OrderPlaced> received = new ArrayList<>();

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            received.add(event);
            System.out.println(
                "listener-event=" + event.eventId()
                + ",lines=" + event.lines().size());
        }

        public int count() {
            return received.size();
        }

        public OrderPlaced first() {
            return received.get(0);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderPublisher orderPublisher(
                ApplicationEventPublisher publisher) {
            return new OrderPublisher(publisher);
        }

        @Bean
        public OrderListener orderListener() {
            return new OrderListener();
        }
    }

    public static void main(String[] args) {
        List<OrderLine> inputLines = new ArrayList<>();
        inputLines.add(new OrderLine("SKU-A", 2));

        Map<String, String> inputMetadata = new HashMap<>();
        inputMetadata.put("source", "web");

        Instant occurredAt = Instant.parse("2026-01-10T00:00:00Z");

        OrderPlaced event = new OrderPlaced(
            "evt-100", "order-100", occurredAt,
            inputLines, inputMetadata);

        // After creating the record, the publisher may still modify the input data.
        inputLines.add(new OrderLine("SKU-B", 1));
        inputMetadata.put("source", "mobile");

        System.out.println("snapshot-lines=" + event.lines().size());
        System.out.println(
            "snapshot-source=" + event.metadata().get("source"));

        boolean mutationBlocked = false;
        try {
            event.lines().add(new OrderLine("SKU-C", 1));
        } catch (UnsupportedOperationException expected) {
            mutationBlocked = true;
        }
        System.out.println("mutation-blocked=" + mutationBlocked);

        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            OrderPublisher publisher = context.getBean(OrderPublisher.class);
            OrderListener listener = context.getBean(OrderListener.class);

            publisher.place(event);

            System.out.println("listener-count=" + listener.count());
            System.out.println(
                "same-payload-reference=" + (listener.first() == event));
        }

        // Record equals() compares components, not object identity.
        OrderPlaced sameData = new OrderPlaced(
            "evt-100",
            "order-100",
            Instant.parse("2026-01-10T00:00:00Z"),
            List.of(new OrderLine("SKU-A", 2)),
            Map.of("source", "web"));
        System.out.println("value-equality=" + event.equals(sameData));

        boolean blankIdRejected = false;
        try {
            new OrderPlaced(
                " ", "order-100", occurredAt,
                List.of(new OrderLine("SKU-A", 2)),
                Map.of("source", "web"));
        } catch (IllegalArgumentException expected) {
            blankIdRejected = true;
        }
        System.out.println("blank-id-rejected=" + blankIdRejected);
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ImmutableRecordEventDemo
~~~

Eight lines printed by **the program itself** upon successful execution:

~~~text
snapshot-lines=1
snapshot-source=web
mutation-blocked=true
listener-event=evt-100,lines=1
listener-count=1
same-payload-reference=true
value-equality=true
blank-id-rejected=true
~~~

Maven or Spring may print additional logs depending on the environment. The lines above reflect the exact order of `System.out.println` in the example using the default synchronous multicaster. The code was designed and reviewed against Java 17/Spring 6.2.12; if Maven has not been run in a specific environment, this is **expected output**, not an executed test transcript.

### 5.4. Explaining Each Result

**snapshot-lines=1**: `inputLines` initially had one line; the constructor ran `List.copyOf`, and then the publisher added SKU-B to `inputLines`. The event stored a one-line snapshot and does not see subsequent changes to the input list.

**snapshot-source=web**: `Map.copyOf` preserved `source=web` at record creation time. Updating `inputMetadata` to `source=mobile` does not affect the event.

**mutation-blocked=true**: the `event.lines()` accessor returns an unmodifiable list, so `add()` throws `UnsupportedOperationException`; the event is not modified.

**listener-event=evt-100,lines=1**: `@EventListener` receives the record from Spring and reads its accessors. For a POJO record, Spring may wrap it internally in `PayloadApplicationEvent`, yet the method still receives `OrderPlaced` directly.

**listener-count=1**: one `publishEvent` call to one matching listener, in the default synchronous configuration with no other publishers for this type.

**same-payload-reference=true**: Spring wraps the payload during dispatch without necessarily cloning the event; in the demo the listener receives the exact `OrderPlaced` instance sent by the publisher. That is why **true immutability matters**: if the payload contains mutable objects, the listener can observe mutated state.

**value-equality=true**: two distinct records have equal `eventId`, `orderId`, `occurredAt`, `lines`, and `metadata`. `List` and `Map` compare by value; `OrderLine` is a record so it has value equality. Using `equals` to assert snapshots in tests is very convenient, but production deduplication should generally rely on a **stable eventId**, not hashing the entire payload.

**blank-id-rejected=true**: the compact constructor throws `IllegalArgumentException` for a whitespace-only `eventId`. By validating at creation time, invalid events are blocked before publishing.

### 5.5. Why the Example Is Usefully Immutable, Yet Does Not Automatically Guarantee Every Other Event

In the example, the components are `String`, `Instant`, `List<OrderLine>`, and `Map<String,String>`; they are sufficiently stable by design. However, if `OrderLine` were replaced with a class that has setters, or metadata values were replaced with `Map<String, Object>`, `List.copyOf` and `Map.copyOf` **do not create a deep copy**. In that case the record could still contain objects capable of mutating.

If using `BigDecimal` for monetary amounts, it is immutable, though scale/currency and business rules should be specified. If using `java.util.Date`, `byte[]`, `AtomicInteger`, mutable `JsonNode`, or a JPA entity, consider switching to value types or performing deep defensive copies.

## 6. Comparing Records with Traditional Classes

Two ways to represent the same data:

~~~java
// Regular class, illustrative; requires writing constructor/accessors/equality manually.
public final class PaymentCaptured {
    private final String eventId;
    private final String paymentId;

    public PaymentCaptured(String eventId, String paymentId) {
        this.eventId = eventId;
        this.paymentId = paymentId;
    }

    public String eventId() {
        return eventId;
    }

    public String paymentId() {
        return paymentId;
    }
}
~~~

And a record:

~~~java
public record PaymentCaptured(
        String eventId,
        String paymentId
) {}
~~~

Records reduce boilerplate, provide value semantics, and express the data contract right in the header. However, not every domain object should be a record:

- **Entities** with identity, lifecycle, controlled mutability, and complex invariants usually suit classes/domain models; JPA entities have specific proxy/constructor requirements.
- **Events/value objects** usually fit records well.
- Objects requiring lazy loading, an internal state machine, or extending another class do not fit records.

Do not replace every class with a record just because the syntax is shorter. Choose based on **the semantics of the data**, not code length.

### 6.1. Differences in Equality

Records compare by components. Therefore:

~~~java
record OrderPaid(String eventId, long orderId) {}

OrderPaid a = new OrderPaid("evt-1", 10L);
OrderPaid b = new OrderPaid("evt-1", 10L);
System.out.println(a.equals(b)); // true
System.out.println(a == b);      // false
~~~

This is very convenient in tests, but requires care if the event ID is a **unique identity**. Two events with the same `eventId` but different payloads should not by default be treated as two valid events; record `equals()` may return false due to differing contents, yet the idempotency system must still detect **a same-eventId conflict** and handle it according to policy.

In tests, using `assertEquals(expected, actual)` is appropriate for value snapshots; in production consumers, use `eventId` and transactions/unique constraints to prevent duplicates.

## 7. Event ID, Timestamps, and Snapshot Data

A good event record should separate:

- **eventId**: a specific event occurrence, kept stable across retries/redeliveries.
- **aggregateId**: the related object, such as `orderId`.
- **occurredAt**: the time the business fact occurred.
- **correlationId**: an ID grouping related workflows/requests.
- **causationId**: the ID of the event/command that directly caused this event.
- **schemaVersion**: the contract version when the event is externalized.
- **payload**: the necessary business data, not a dump of an entire database entity.

### 7.1. When Should eventId Be Generated?

Typically, the application service generates `eventId` **once when the business event occurs**, before persisting intent or publishing the message. If retry or redrive is needed, preserve the original ID. Do not generate a new `eventId` on each delivery attempt, or deduplication by `eventId` will fail.

UUID is a common choice; records do not auto-generate UUIDs. You can use `UUID.randomUUID().toString()`, ULID, or a system-assigned ID depending on distribution, ordering, and tracing requirements.

### 7.2. occurredAt Differs from processedAt

`Instant` stores a UTC point in time and avoids the ambiguity of a zone-less `LocalDateTime`. Distinguish:

~~~text
occurredAt  = when the business fact was recorded
publishedAt = when the publisher/broker accepted sending it
receivedAt  = when the consumer received it
processedAt = when the consumer finished processing it
~~~

Do not collapse everything into one timestamp if the business needs to measure queue latency or handle replays. An event arriving late does not change `occurredAt`.

### 7.3. Event Snapshot Differs from an Entity Reference

Do not do this:

~~~java
// WRONG snapshot design: OrderEntity is a mutable JPA entity.
public record OrderPlaced(OrderEntity order) {}
~~~

An event like this is prone to:

- The entity being modified after publishing.
- An async listener running after the persistence context closes and hitting lazy-loading errors.
- The event serializing incorrectly or accidentally exposing unnecessary data.
- The entity state when the listener runs differing from its state when the event occurred.
- Coupling between the event contract and the ORM implementation.

Instead:

~~~java
// Better approach: minimal, immutable data snapshot.
public record OrderPlaced(
        String eventId,
        long orderId,
        Instant occurredAt,
        List<OrderLine> lines
) {
    public OrderPlaced {
        lines = List.copyOf(lines);
    }
}
~~~

When data can change continuously, consider **passing only the ID and version**, after which the consumer intentionally reads the latest state from the repository. Understand that this is a different model: the event is no longer a full snapshot, and the re-read data may differ from when the event occurred.

## 8. Domain Events vs. Integration Events

Not every internal event must become a message between services.

### Internal Domain Events

- Used within the same `ApplicationContext` or module.
- Can contain appropriate internal value objects.
- May matter only within the current transaction/lifecycle.
- `@EventListener` and `ApplicationEventPublisher` suffice for simple scenarios.

### External Integration Events

- Require clear schema/version contracts.
- Contain only data that must be exchanged between systems.
- Do not depend directly on JPA entities or hard-to-interoperate internal Java classes.
- Require payload serialization, validation, security, and transport selection.
- When durability matters, require a broker, outbox, retries, and idempotency.

An internal event can be **mapped to a separate integration event record**:

~~~java
// Snippet, not part of the standalone Maven example.
public record OrderPlacedIntegrationV1(
        String eventId,
        String orderId,
        String occurredAt,
        List<LineV1> lines,
        int schemaVersion
) {
    public OrderPlacedIntegrationV1 {
        lines = List.copyOf(lines);
    }
}

public record LineV1(String sku, int quantity) {}
~~~

Here `occurredAt` as an ISO-8601 string may be convenient for a JSON contract required by external systems; `Instant` is also valid if the serializer is explicitly configured. Do not confuse the wire-format representation choice with the immutable nature of the record.

### 8.1. Durability Does Not Come from the Record

Simply publishing a record into Spring Application Events provides no durable persistence by default. For critical transactions, save an **outbox record in the same transaction as the business state change**, then relay it to the broker. A `@TransactionalEventListener(AFTER_COMMIT)` helps decide when the callback runs, yet still leaves a crash window between commit and completion.

If the event record is sent to Kafka/RabbitMQ, each consumer must still support **at-least-once delivery and idempotency** if the broker can redeliver.

## 9. `@Async` and Records: Safer Across Thread Transitions

A major purpose of immutable events is reducing race conditions caused by the publisher and listener viewing the same mutable object.

~~~text
Publisher thread
    |
    +-- creates OrderPlaced record with snapshot lines
    +-- publishEvent(record)
    |       +-- @Async listener is scheduled
    |
    +-- mutates publisher's inputLines
    |
Worker thread
    |
    +-- reads record.lines() -> still the snapshot at creation time
~~~

An illustrative listener:

~~~java
// Bean snippet, requires @EnableAsync and an appropriate executor.
@Async("eventExecutor")
@EventListener
public void handle(OrderPlaced event) {
    auditService.save(event.eventId(), event.lines());
}
~~~

Because the record holds snapshot data, the caller modifying `inputLines` after publishing does not alter the event data. Still, keep in mind:

- `record` does not make the listener thread-safe if **the listener bean itself holds unsynchronized mutable state**.
- `@Async` does not automatically propagate transactions, MDC, `SecurityContext`, or `ThreadLocal` values.
- `@Async` does not provide durable retries and does not guarantee the event will finish on a JVM crash.
- All components of the event must truly be stable; `List.copyOf` over mutable elements is not enough.
- If the listener mutates external business state, separate idempotency and error handling are required.

Immutable payloads help with **data safety**, but do not solve every concurrency and delivery requirement.

## 10. Transaction Boundaries: When to Create the Record?

An order-placement use case might be written as:

~~~java
// Illustrative snippet in a Spring-managed application service.
@Transactional
public void place(CreateOrder command) {
    Order order = repository.save(Order.createFrom(command));

    OrderPlaced event = new OrderPlaced(
        eventIdGenerator.newId(),
        order.id(),
        clock.instant(),
        order.snapshotLines(),
        Map.of("source", "checkout"));

    publisher.publishEvent(event);
}
~~~

This is **illustrative**; the `Order`/repository/clock APIs are assumed application APIs, not a standalone program. The event should be constructed from confirmed business state; avoid publishing before knowing whether the order is missing lines or violates invariants.

### Publishing Before Commit

With a default synchronous `@EventListener`, the listener runs immediately upon publish, possibly on the same source thread and transaction. If the listener sends an email or calls an external API, that side effect may occur even if the transaction subsequently rolls back.

### Processing After Commit

`@TransactionalEventListener(phase = AFTER_COMMIT)` can defer the callback until after commit. This avoids one class of consistency bugs, but **does not durably store the event record**. If the process dies after commit and before the callback finishes, there is no default queue to replay it.

### When High Reliability Is Required

Write an outbox record containing `eventId`, `eventType`, `schemaVersion`, and the serialized payload **in the same local transaction** as the order state. After commit, an independent relay sends and retries it. Consumers must be idempotent because the relay/broker may redeliver.

An immutable record helps **serialize a consistent snapshot**, but does not replace a database transaction or a broker.

## 11. Serialization: What Spring Context Does Not Do for You

A `publisher.publishEvent(record)` call inside Spring Context **does not require a JSON serializer**. The framework can wrap the object in a `PayloadApplicationEvent` and dispatch it to matching methods in the JVM.

When sending a record over REST/Kafka/RabbitMQ, you must explicitly determine:

1. **Wire format**: JSON, Avro, Protobuf, schema registry, etc.
2. **Serializer/deserializer**: actual framework versions and configuration.
3. **Schema evolution**: renaming fields, adding fields, defaults, removing fields, version migration.
4. **Java time types**: `Instant` needs an explicit representation; when using Jackson, compatible Java Time support is needed (for example, `jackson-datatype-jsr310`).
5. **Nullability**: `List.copyOf` / `Map.copyOf` reject nulls; older payloads may omit fields.
6. **Validation**: the compact constructor may throw during deserialization if data is invalid.
7. **Security**: do not put secrets, session tokens, full JPA graphs, or unnecessary PII into events.
8. **Idempotency**: a serializer does not automatically create transactions or prevent duplicates.

Java records may be supported by many JSON libraries, but **never assume every Java record serializes and deserializes identically across all versions**. Test with the exact library, version, JavaTime module, and schema contract of your application.

### 11.1. Evolution: Adding a Component Changes the Canonical Constructor

Suppose v1 is:

~~~java
public record CustomerRegisteredV1(
        String customerId,
        String email
) {}
~~~

v2 adds a field:

~~~java
public record CustomerRegisteredV2(
        String customerId,
        String email,
        String locale
) {}
~~~

The two records above are two distinct Java types. When actually evolving the schema of the same integration event, old and new consumers might not simultaneously understand the new field or default. Do not treat "adding a component to a record" as an always backward-compatible change.

In internal code, every call site `new CustomerRegisteredV1(...)` is statically checked and may need updating if you change the header of a single record. For wire contracts, define versioning, optional/default fields, and migration strategies backed by contract tests.

### 11.2. Do Not Expose Sensitive Data in `toString()`

The compiler generates `toString()` from the components. If an event record holds a password or token, accidentally logging `logger.info("{}", event)` can leak secrets. A safe rule is **never include secrets in event payloads**, and log only permitted IDs/fields instead of logging the entire record.

## 12. How Does Value Equality Help with Testing?

Records remove a lot of boilerplate in unit tests:

~~~java
// Unit test snippet, requires JUnit assertions.
OrderPlaced actual = listenerCapturedEvent;

OrderPlaced expected = new OrderPlaced(
    "evt-100", "order-100",
    Instant.parse("2026-01-10T00:00:00Z"),
    List.of(new OrderLine("SKU-A", 2)),
    Map.of("source", "web"));

assertEquals(expected, actual);
~~~

Assume the record types are imported/declared as in Section 5. Because record equality uses components, you do not need to write `equals` for every event DTO.

Still, test more thoroughly:

- Construct from mutable input list/map, mutate the inputs afterward, and verify the event is unchanged.
- Try mutating `event.lines()` and `event.metadata()`, confirming `UnsupportedOperationException`.
- Construct with a blank `eventId`, empty lines, or negative quantity and confirm the constructor rejects them.
- For nested mutable objects, write tests demonstrating the risk and fix with snapshots/deep copies.
- For async listeners, verify results using a latch/`Future`, not arbitrary `Thread.sleep()`.
- For database/outbox setups, test business transaction rollback and atomic event intent.

### 12.1. Unit Testing Without Spring

A plain record can be tested with pure JUnit without starting an `ApplicationContext`. "Record immutability" and "Spring listener dispatch" are two separate responsibilities. Test constructors/copying/validation first; only integration tests need Spring.

### 12.2. Spring TestContext and `ApplicationEvents`

With Spring TestContext, `@RecordApplicationEvents` and `ApplicationEvents` allow tests to record events within the scope of a test method. After calling the service, you can filter by payload type:

~~~java
// Snippet in a @SpringJUnitConfig / @RecordApplicationEvents test.
@Test
void recordsOrderPlaced(ApplicationEvents events) {
    events.clear();
    orderService.place(...); // Application API.

    List<OrderPlaced> actual =
        events.stream(OrderPlaced.class).toList();
    assertEquals(1, actual.size());
}
~~~

`ApplicationEvents.stream(OrderPlaced.class)` can return the record payload even though Spring wrapped it in `PayloadApplicationEvent`. However, an event being recorded **does not prove** that an `@Async` callback has finished or that an integration message has reached a broker.

## 13. Placing Records in the Right Architectural Layer

A suggested package structure:

~~~text
com.example.orders
├── application
│   └── OrderApplicationService.java
├── domain
│   ├── Order.java
│   └── events
│       ├── OrderPlaced.java
│       └── OrderLine.java
└── integration
    ├── OrderPlacedIntegrationV1.java
    └── OrderEventOutboxWriter.java
~~~

Domain event records may use internal value objects; integration records should use stable DTO schemas without directly referencing entities, ORM types, or proxies. Choose locations according to your project's ownership and dependency direction; this structure is not mandatory for every application.

### Domain Facts Differ from Commands

`OrderPlaced` means placing the order has happened; `PlaceOrder` is **a request to perform** order placement. These are two distinct meanings:

~~~text
PlaceOrder command
    |
    +-- validate + execute business operation
    +-- OrderPlaced event
    |
    +-- listeners react
~~~

If a record named `OrderPlaced` is actually a request to start placing an order, readers and consumers will easily misunderstand timing and idempotency. Use past-tense event names for facts, and imperative names for commands.

### Event Ownership and Evolution

A module should own the contract of the events it publishes. Consumers should not ask producers to put entire repository objects or JPA entities into payloads. Keep event fields minimal, document invariants, and maintain contract tests when externalizing.

## 14. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| "Records are deeply immutable" | Nested mutable fields still change | Use immutable components or deep copy |
| Using only `Collections.unmodifiableList(input)` | May only be a **view**; input mutations still show | `List.copyOf(input)` or an independent copy |
| Using `List.copyOf` on `List<MutableEntity>` | Elements remain mutable | Map to `List<ImmutableLine>` |
| Record holds `byte[]` with default accessor | Caller mutates array contents | Clone on both input and output, or pick another type |
| Record holds a JPA entity/session | Lazy-loading, mutation, coupling | Snapshot scalar/value fields |
| Assuming record must extend `ApplicationEvent` | Fails to compile since records extend Record | Publish record as a POJO |
| Assuming `publishEvent` requires Jackson JSON | Confuses JVM dispatch with serialization | Configure serializer only across transport |
| Using an event record to query the database | Side effects in constructor, hard to test | Keep constructor validation simple |
| Mutating the entire record to update state | Confuses event with entity | Events are snapshots; state updates belong to aggregates |
| Using `==` to compare two events with same data | False because of different instances | Record `equals` or ID depending on intent |
| Using full-payload `equals` for deduplication | Same eventId with payload drift is missed | Deduplicate by eventId and check for conflicts |
| Generating a new eventId on each retry | Consumer treats it as a new event | Preserve the original ID across redelivery |
| Assuming records provide retries/durable delivery | Events lost on process crash | Use outbox/broker when durability is required |
| Assuming `@Async` makes the whole listener thread-safe | Mutable bean state still races | Synchronize / manage state separately |
| Logging `toString()` of a record with secrets | Data leak | Exclude secrets from events; log selectively |
| Adding a record component without checking schema | Old consumers fail to deserialize | Versioning + contract tests |
| Counting events via the full framework event stream | Test polluted by lifecycle events | Filter by typed payload class |

## 15. Pre-Production Checklist

1. Does the event name express **a fact that already occurred**?
2. Do all components have clear business meaning, types, and invariants?
3. Are a stable `eventId`, `aggregateId`, and `occurredAt` included where needed?
4. Does the record contain arrays, `Date`, mutable `List`/`Map`, JPA entities, or mutable `JsonNode`?
5. If there are `List`/`Map` fields, does the compact constructor defensively copy them?
6. Are the elements/values of those collections **truly immutable**?
7. Does the constructor validate null/blank/range constraints without performing side effects?
8. Does the listener receive the exact record payload via `@EventListener`?
9. When using `@Async`, are listener context and state managed properly on their own?
10. Do transactions/`AFTER_COMMIT`/outbox match consistency and durability requirements?
11. If externalized, are schema/version/serialization and retention/security policies defined?
12. Do tests prove the snapshot is unchanged after input mutation, equality works, and event dispatch succeeds?

**Conclusion:** Java `record` is a great fit for event payloads in Spring Application Events because it is concise, typed, provides value equality, and has final components. Yet records are only **shallowly immutable**: defensively copy collections, choose nested immutable value objects, validate in the compact constructor, and snapshot business data at the right moment. Spring accepts records directly via `publishEvent(Object)` and `@EventListener`; when async, transactions, or integration messaging are needed, design those boundaries **explicitly**, without attributing guarantees to records that Java/Spring do not provide.

## Official Documentation

- Java SE 17 — Record Classes, canonical/compact constructor: https://docs.oracle.com/en/java/javase/17/language/records.html
- Java SE 17 — Creating Unmodifiable Lists, Sets, and Maps: https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html
- Java SE 17 — Collection, unmodifiable vs immutable: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html
- Spring Framework 6.2 — ApplicationContext events, payloads, async listener: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2.12 — ApplicationEventPublisher: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2.12 — PayloadApplicationEvent: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/PayloadApplicationEvent.html
- Spring Framework 6.2 — Transaction-bound events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
