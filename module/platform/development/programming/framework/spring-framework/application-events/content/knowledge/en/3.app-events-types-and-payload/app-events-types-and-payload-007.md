# Immutable Payloads and Safe Sharing

In Spring Framework, application events are typically dispatched to one or more listeners within the same ApplicationContext. When an event is published, listeners receive a reference to the event or payload sent by the publisher. If data can be modified after publishing, listeners may observe inconsistent state or overwrite data that another listener is currently using.

Therefore, an **immutable payload** is a solid choice for application events. An immutable payload prevents state changes after creation. When multiple listeners read the payload—even when running on different threads—they can share the data safely without coordinating locks to guard against mutation.

## 1. Payloads in Spring Application Events

A payload is the data describing the event that the application wants to announce. For example, when an order is created, the event may carry the order ID, creation time, order lines, and total amount. Listeners use this data to send notifications, write audit logs, or update a read model.

Spring supports two common approaches:

- **Custom ApplicationEvent:** create a class extending ApplicationEvent and place business data in the subclass's fields.
- **POJO or record:** publish a plain Java object. Since Spring Framework 4.2, Spring automatically wraps this object in PayloadApplicationEvent.

Example of an event extending ApplicationEvent:

~~~java
public class OrderCreatedEvent extends ApplicationEvent {

    private final String orderId;

    public OrderCreatedEvent(Object source, String orderId) {
        super(source);
        this.orderId = orderId;
    }

    public String getOrderId() {
        return orderId;
    }
}
~~~

Example of a POJO payload:

~~~java
public record OrderCreated(String orderId) {
}
~~~

Both approaches can carry data to listeners. Whichever style is used, the design principle remains the same: published data should be treated as a snapshot of the event at the time it was published.

## 2. Why Are Immutable Payloads Needed?

Suppose OrderService publishes an event containing a list of order lines. If the service continues modifying the list after publishing, a listener may observe changed contents. If the first listener modifies the list, a second listener may also see that change because listeners typically receive the same event object.

Common risks:

- **Race conditions:** two threads reading and writing the same collection without proper synchronization.
- **Inconsistent data:** a listener handles an event whose internal values changed after the publish moment.
- **Order dependency:** one listener's side effect alters the data another listener reads.
- **Hard-to-reproduce bugs:** bugs that only surface when the executor, system load, or execution order changes.
- **Difficult testing:** tests depending on listener order and leftover mutable state.

Immutable payloads turn events into stable data messages. The publisher can continue processing, while listeners can read the same snapshot without worrying about one side mutating the other side's data.

## 3. True Immutability Differs from Just Using final

In Java, the final keyword prevents reassigning a reference variable after initialization. It does not automatically make the object pointed to by that reference variable immutable.

The following example is not yet immutable:

~~~java
public final class OrderPayload {

    private final List<String> items;

    public OrderPayload(List<String> items) {
        this.items = items;
    }

    public List<String> getItems() {
        return items;
    }
}
~~~

The items field is final, yet the caller can still modify the original list or modify the list via the getter:

~~~java
List<String> items = new ArrayList<>();
items.add("BOOK");

OrderPayload payload = new OrderPayload(items);

items.add("PEN");             // Mutates data inside the payload.
payload.getItems().clear();  // Also mutates data inside the payload.
~~~

To create a safer payload, you must control both incoming data and returned data:

~~~java
public final class OrderPayload {

    private final List<String> items;

    public OrderPayload(List<String> items) {
        this.items = List.copyOf(items);
    }

    public List<String> getItems() {
        return items;
    }
}
~~~

List.copyOf creates an unmodifiable list and decouples the list structure from the input collection. After creating the payload, adding or removing elements in the original list does not alter the list stored in the payload. The getter returns an unmodifiable list.

However, **List.copyOf only creates a shallow copy**. If an element inside is a mutable object, that object can still be modified. Immutability must be ensured across the entire data graph accessible to listeners.

## 4. Using Java Records for Payloads

Java records fit payloads well because records provide a constructor, accessors, equals, hashCode, and toString based on their components. Components are stored in final fields. However, records are only shallowly immutable: if a component is a mutable List or another mutable object, internal state can still change.

Example of a safe payload with immutable values:

~~~java
import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;
import java.util.Objects;

public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice) {

    public OrderLine {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(unitPrice, "unitPrice");

        if (quantity <= 0) {
            throw new IllegalArgumentException("quantity must be positive");
        }
        if (unitPrice.signum() < 0) {
            throw new IllegalArgumentException("unitPrice must not be negative");
        }
    }
}

public record OrderCreated(
        String orderId,
        Instant occurredAt,
        List<OrderLine> lines) {

    public OrderCreated {
        Objects.requireNonNull(orderId, "orderId");
        Objects.requireNonNull(occurredAt, "occurredAt");
        lines = List.copyOf(lines);

        if (lines.isEmpty()) {
            throw new IllegalArgumentException("lines must not be empty");
        }
    }
}
~~~

Components in the example:

- String is immutable.
- Instant is immutable.
- BigDecimal is immutable.
- OrderLine is a record containing only immutable values.
- List.copyOf creates an unmodifiable list structure and copies element references into the new list.

Because each OrderLine is also immutable, listeners can share OrderCreated without worrying about one listener mutating an order line and affecting others. The constructor checks for nulls and business conditions so payloads cannot be created in an invalid state.

Note that List.copyOf rejects null elements. If business logic allows null, define the meaning of null clearly and use an appropriate copying strategy. Typically, event payloads should avoid null elements to keep listeners simpler.

## 5. Defensive Copies for Collections, Maps, and Arrays

For collections, use immutable copy factories when data contains no nulls:

~~~java
List<String> safeItems = List.copyOf(inputItems);
Set<String> safeTags = Set.copyOf(inputTags);
Map<String, String> safeAttributes = Map.copyOf(inputAttributes);
~~~

These methods create unmodifiable collection structures. They do not make the objects stored inside immutable. For example, a Map<String, CustomerProfile> can still hold a mutable CustomerProfile; a caller can modify the profile and listeners will observe that change.

If you need an ordered collection or need to allow nulls, make your own copy first and wrap it with an unmodifiable wrapper:

~~~java
List<String> copy = new ArrayList<>(inputItems);
List<String> safeView = Collections.unmodifiableList(copy);
~~~

The wrapper must surround your own copy. If you only call Collections.unmodifiableList(inputItems) on the original collection, other code can still mutate inputItems and change what listeners observe.

### Arrays must be copied both on input and on output

Arrays are always mutable. If a payload contains a byte array, clone it when receiving data and when returning data:

~~~java
public final class DocumentPayload {

    private final byte[] content;

    public DocumentPayload(byte[] content) {
        this.content = content.clone();
    }

    public byte[] content() {
        return content.clone();
    }
}
~~~

If you only clone in the constructor while returning the field directly from the accessor, callers can still mutate internal contents. If you only clone on return while keeping the input array as-is, callers can still mutate the payload through the old reference.

For nested objects, apply defensive copying or convert to immutable types at every layer. A shallow copy of a collection is not enough to protect mutable objects inside.

## 6. Snapshot at Publish Time

An event should represent the state at the moment the event occurred. Do not publish a collection or entity that business code will continue mutating afterward.

Example:

~~~java
List<OrderLine> draftLines = new ArrayList<>();
draftLines.add(new OrderLine(
        "BOOK-01", 2, new BigDecimal("12.50")));

OrderCreated event = new OrderCreated(
        "ORD-1001",
        Instant.parse("2026-11-11T03:00:00Z"),
        draftLines);

draftLines.clear();

// The event still retains a snapshot with one order line.
publisher.publishEvent(event);
~~~

In the example, the OrderCreated constructor uses List.copyOf, so clearing draftLines does not remove the order line inside the event.

There are two common snapshot design approaches:

1. **Snapshot containing necessary data:** the event carries ID, timestamp, quantities, and finalized values at publish time. Listeners process the exact historical state.
2. **Event containing only an identifier:** the event carries orderId, and the listener loads the latest data from a repository itself. This reduces payload size, but the listener will see the state at read time, which may differ from the state when the event was published.

Choose based on business semantics. If the listener must process the exact data at order creation time, carry an immutable snapshot. If the listener needs the current state, pass only the ID and re-read from the data source.

## 7. Safety When Sharing Across Multiple Listeners and Threads

ApplicationEventMulticaster dispatches events to matching listeners. In the default flow, listeners are invoked synchronously on the event-publishing thread. When an executor is configured or async execution is used, listeners can run on different threads.

Spring does not deep-copy events or payloads for each listener. Listeners can receive the same event instance or the same reference to the payload inside the wrapper. Therefore:

- Do not mutate fields or collections in a payload after publishing.
- Do not let one listener alter an object that another listener is reading.
- Do not assume an executor automatically makes a mutable payload thread-safe.
- If data needs to be transformed, create a new object instead of mutating the event object.
- If shared mutable state is required, use a separate thread-safe abstraction and manage synchronization where that state is owned.

An immutable object fully constructed inside its constructor without leaking `this` before the constructor finishes can be shared more safely under the Java Memory Model's final-field rules. However, that guarantee does not make mutable objects referenced inside thread-safe. Immutability must cover all data accessible to listeners.

When an async listener needs to access committed data, consider @TransactionalEventListener with the AFTER_COMMIT phase. Async does not automatically propagate the transaction context to another thread. If durable delivery across restarts or across multiple processes is needed, internal application events are insufficient; an appropriate message broker and persistence mechanism are required.

## 8. Runnable Example with Java 17 and Spring Framework

The example uses a record as the payload, defensively copies the order line list, and publishes via ApplicationEventPublisher. The listener receives the payload directly using @EventListener.

### Directory Structure

~~~text
immutable-event-payload-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── ImmutableEventPayloadDemo.java
~~~

### pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>immutable-event-payload-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
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

### ImmutableEventPayloadDemo.java

~~~java
package demo;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ImmutableEventPayloadDemo {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            service.createOrder("ORD-1001");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public OrderService orderService(ApplicationEventPublisher publisher) {
            return new OrderService(publisher);
        }

        @Bean
        public OrderCreatedListener orderCreatedListener() {
            return new OrderCreatedListener();
        }
    }

    public record OrderLine(
            String sku,
            int quantity,
            BigDecimal unitPrice) {

        public OrderLine {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "unitPrice must not be negative");
            }
        }
    }

    public record OrderCreated(
            String orderId,
            Instant occurredAt,
            List<OrderLine> lines) {

        public OrderCreated {
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            lines = List.copyOf(lines);
            if (lines.isEmpty()) {
                throw new IllegalArgumentException(
                        "lines must not be empty");
            }
        }
    }

    public static class OrderService {

        private final ApplicationEventPublisher publisher;

        public OrderService(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        public void createOrder(String orderId) {
            List<OrderLine> draftLines = new ArrayList<>();
            draftLines.add(new OrderLine(
                    "BOOK-01", 2, new BigDecimal("12.50")));

            OrderCreated event = new OrderCreated(
                    orderId,
                    Instant.parse("2026-11-11T03:00:00Z"),
                    draftLines);

            // Modifying the original list does not affect the snapshot inside the event.
            draftLines.clear();

            System.out.println("Publishing " + orderId);
            publisher.publishEvent(event);
        }
    }

    public static class OrderCreatedListener {

        @EventListener
        public void handle(OrderCreated event) {
            System.out.println(
                    "Received " + event.orderId()
                            + " with " + event.lines().size() + " line(s)");
        }
    }
}
~~~

### Compiling and Running

Run in the directory containing pom.xml:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.ImmutableEventPayloadDemo
~~~

Stdout output:

~~~text
Publishing ORD-1001
Received ORD-1001 with 1 line(s)
~~~

Explanation:

1. OrderService creates a mutable ArrayList and adds one order line.
2. The OrderCreated constructor uses List.copyOf to create a separate, unmodifiable list structure.
3. The service removes elements from draftLines; the snapshot inside the event still retains one line.
4. The service publishes the OrderCreated record. Spring wraps the payload in PayloadApplicationEvent and dispatches it to matching listeners.
5. The listener receives OrderCreated directly via @EventListener and reads the immutable payload.
6. Because listeners run synchronously by default, the Received line is printed before publishEvent returns.

The example shows that records help express data, while List.copyOf and immutable element types are what ensure the payload cannot be mutated through nested collections.

## 9. Common Mistakes When Designing Payloads

| Mistake | Consequence | Resolution |
|---|---|---|
| Only using final for a collection | Collection contents remain mutable | Copy and wrap the collection as unmodifiable |
| Using a record containing an ArrayList | Records are only shallowly immutable | Copy the collection in the compact constructor |
| Copying the collection while elements are mutable | Listeners can still mutate inner objects | Use immutable elements or deep copy |
| Returning an internal array directly | Callers can mutate the payload | Clone on input and on output |
| Wrapping the original collection with unmodifiableList | Other code still mutates the original collection | Wrap a separate copy |
| Publishing an entity that continues to change | Listeners observe different states | Publish an immutable snapshot or pass only the ID |
| One listener mutating the payload for another listener | Creates order dependencies and race conditions | Treat payloads as read-only |
| Assuming an async executor makes objects thread-safe | Mutable objects can still have data races | Use deep immutability or synchronize where owned |

## 10. Safe Payload Design Checklist

- Choose event data that accurately reflects the moment the event occurred.
- Prefer records or final classes with final fields.
- Use immutable value types such as String, BigDecimal, Instant, and enums.
- Copy input collections with List.copyOf, Set.copyOf, or Map.copyOf when appropriate.
- Ensure elements inside collections are also immutable.
- Clone arrays both when receiving data and when returning data.
- Do not expose mutable references to internal state.
- Do not modify the payload after publishing.
- Test that mutating input collections does not alter the payload and getters do not allow structural modification.
- When listeners run asynchronously, audit all nested objects and do not rely on the publisher's transaction context.

Immutable payloads turn application events into reliable snapshots. When a publisher and multiple listeners share the same event, deep immutable design reduces race conditions, avoids execution-order dependencies, and makes application behavior easier to test.