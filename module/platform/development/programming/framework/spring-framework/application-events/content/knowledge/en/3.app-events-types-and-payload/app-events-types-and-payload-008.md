# Should an Event Contain an ID or the Full State?

## 1. The Payload Design Problem

When publishing an event, the publisher must decide what data accompanies the event. There are two common options:

- The event carries only an identifier, such as OrderCreatedEvent(String orderId). The listener receives the ID and queries the order itself when needed.
- The event carries a snapshot of the object's data at publish time, such as order ID, customer, order lines, total amount, and status.

Between those two options lies a hybrid form: the event carries an ID to identify the resource plus a few snapshot fields needed so listeners can process it without querying again.

No single payload structure fits every event. The decision depends on the meaning of the event, how listeners use the data, processing timing, consistency requirements, message size, security, and how the contract evolves over time.

After this lesson, you can:
- Distinguish ID-only events, snapshot events, and hybrid events.
- Choose payloads based on subscribers' data reading needs and processing timing.
- Avoid publishing JPA entities or mutable objects as payloads.
- Understand the impact of transactions, asynchronous processing, and data changing after publishing.
- Design immutable event DTOs with sufficient data and evolvable contracts.

## 2. Three Common Payload Forms

### 2.1. ID-only Event

Example:

~~~java
public record OrderCreatedEvent(String orderId) {
}
~~~

The publisher sends only the order ID. Listeners needing order details use a repository or service to load the data:

~~~java
@Component
public class OrderNotificationListener {

    private final OrderRepository orderRepository;

    public OrderNotificationListener(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        Order order = orderRepository.findById(event.orderId())
                .orElseThrow(() -> new IllegalStateException(
                        "Order not found: " + event.orderId()));

        System.out.println("Send notification for " + order.getId());
    }
}
~~~

An ID-only event is suitable when:
- Listeners only need to know which object changed.
- Listeners need to read the latest state at the time they execute.
- The full data is large, sensitive, or should not be duplicated across many messages.
- Multiple subscribers have different data needs; each subscriber fetches the data it is authorized to access.
- The ID is a stable contract while the aggregate's internal structure may change.

On the other hand, listeners depend on access to the data source. Each subscriber can generate extra queries, increase database load, and encounter errors if the record has already been deleted or is not yet readable.

An important consequence is that a listener may read a state different from the state at the moment the event was published. For example, OrderCreatedEvent is published when the order is in CREATED status, but by the time the listener runs, the order has moved to SHIPPED. An ID-only listener reads SHIPPED because it reads the current state. This is correct behavior if the requirement is “process the current state”, but wrong if the listener needs the exact data at order creation time.

### 2.2. Snapshot Event

A snapshot is a read-only copy of data describing an object at a point in time. Example:

~~~java
public record OrderSnapshot(
        String orderId,
        String customerId,
        String status,
        BigDecimal total
) {
}

public record OrderCreatedEvent(OrderSnapshot order) {
}
~~~

The listener receives the data directly:

~~~java
@Component
public class OrderAuditListener {

    @EventListener
    public void onOrderCreated(OrderCreatedEvent event) {
        OrderSnapshot order = event.order();
        System.out.println(
                "Order " + order.orderId()
                + " created with total " + order.total());
    }
}
~~~

A snapshot event is suitable when:
- Listeners need to know the exact data at the moment the event occurred.
- Subscribers need to process independently without calling back to the event-publishing service.
- Work is processed asynchronously or forwarded through a message broker.
- Auditing, document generation, notification sending, or recording historical data according to the state at publish time is needed.
- The data source might change or disappear before the listener processes the event.

Snapshots free listeners from re-querying to reconstruct historical state. However, payloads are larger and can duplicate data across many events. If a snapshot contains personal information or internal data, every place storing messages becomes a storage location for that data. Limit the published fields and control access, logging, retention, and encryption across related systems.

A snapshot does not have to contain the entire aggregate. Include only the fields that the event contract needs to publish. For example, an email-sending listener might only need orderId, customerEmail, and total amount; an analytics listener might need order lines and product categories. Do not publish every field simply because the source object already has them.

### 2.3. Hybrid ID and Snapshot Event

A practical option is carrying the ID together with essential snapshot fields:

~~~java
public record OrderCreatedEvent(
        String orderId,
        String customerId,
        BigDecimal total,
        Instant occurredAt
) {
}
~~~

The ID is used for identification and querying when necessary; the snapshot provides a few stable pieces of data at publish time. Simple listeners can process immediately using the available fields. Listeners needing more detailed data can use the ID to query further.

The hybrid form fits when subscribers commonly need a small set of fields yet still require the ability to look up the original resource. Clearly define which fields are snapshot data and which are solely identifiers. If the same information appears twice—such as orderId appearing in both the event and the snapshot—there must be one canonical source or validation ensuring they stay consistent.

## 3. Comparison and How to Choose

| Criterion | ID-only | Snapshot-only | Hybrid ID and snapshot |
|---|---|---|---|
| Event size | Small | Potentially large | Medium |
| Extra queries | Usually required | Usually unnecessary for carried data | Depends on listener |
| Data at publish time | Not preserved if re-reading current state | Preserved for fields in the snapshot | Preserved for snapshot fields |
| Coupling to publisher's database | Higher on listener side | Lower for carried data | Medium |
| Suitability for audit/history | Must store or reconstruct history separately | Good if snapshot has sufficient fields | Good for selective data |
| Data exposure risk | Less data in event | Potentially more data | Requires careful field selection |
| Schema changes | ID is usually stable | Must manage snapshot contract | Must manage both ID and snapshot |

You can apply the following decision rules:

1. If the listener needs the current state, an ID is usually enough.
2. If the listener needs the exact truth at the moment the event occurred, carry a snapshot of the necessary fields.
3. If some listeners need fast processing while others need deep lookups, use the hybrid form.
4. If the event crosses service boundaries or is durably persisted, design the payload as an independent integration contract without depending directly on internal entities.

Before choosing, ask: “If the listener runs a few seconds later, a few minutes later, or after the data has changed, must it process the latest state or the state at publish time?” The answer usually determines most of the payload structure.

## 4. Distinguishing Snapshot Events from Event Sourcing

A snapshot in a payload is not synonymous with event sourcing.

In a typical application, an event is a notification of something that just happened. A snapshot may be a subset of data copied into the event for subscribers to process.

In event sourcing, events are stored as the primary source of truth to rebuild aggregate state. The system must manage ordering, versions, replay, schema compatibility, and state transition rules. An in-memory Spring event does not inherently provide those guarantees.

Therefore, sending OrderSnapshot inside OrderCreatedEvent does not turn an application into an event-sourced one. Conversely, if the architecture truly uses event sourcing, a dedicated event store and event contract must be designed rather than treating ApplicationEventPublisher as a history store.

## 5. Do Not Publish JPA Entities or Mutable Objects Directly

Do not use JPA entities as event payloads, especially when listeners can run asynchronously or after the transaction finishes.

An entity may:
- Contain lazy associations requiring a persistence context to load.
- Have proxies or collections managed by the ORM.
- Be mutated after the event has been published.
- Contain internal fields that should not be shared with subscribers.
- Be tied to transaction and session lifecycles.

If a listener runs after the persistence context closes, accessing a lazy field can throw LazyInitializationException. If the publisher continues mutating the entity, the listener may observe altered values instead of the data at publish time.

Map the entity to a dedicated event DTO before publishing. The DTO should contain only published data and should be immutable.

Java records provide immutability at the component reference level, but do not automatically create deep immutability. For instance, a record containing a List can still reference a mutable list. Create defensive copies:

~~~java
public record OrderSnapshot(
        String orderId,
        List<OrderLineSnapshot> lines
) {
    public OrderSnapshot {
        lines = List.copyOf(lines);
    }
}

public record OrderLineSnapshot(
        String sku,
        int quantity,
        BigDecimal unitPrice
) {
}
~~~

List.copyOf creates a list that cannot be modified through the returned reference. Elements inside must also be immutable objects or copied separately if they are mutable. BigDecimal, Instant, String, and records containing only immutable fields are convenient choices for payloads.

## 6. Transactions and Data Reading Timing

ID-only payloads have a common problem: the listener queries the database too early.

Suppose a service saves an order inside a transaction and then publishes an event:

~~~java
@Transactional
public void createOrder(Order order) {
    orderRepository.save(order);
    eventPublisher.publishEvent(new OrderCreatedEvent(order.getId()));
}
~~~

With a default synchronous @EventListener, the listener is invoked right inside the publishEvent call while the publisher's transaction is still active. The listener may participate in the same transaction if using the same transaction manager and resources; do not assume every query in a listener behaves like an independent committed transaction.

If a listener must run after the transaction commits, use @TransactionalEventListener:

~~~java
@Component
public class OrderReadListener {

    private final OrderRepository orderRepository;

    public OrderReadListener(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterOrderCreated(OrderCreatedEvent event) {
        Order order = orderRepository.findById(event.orderId())
                .orElseThrow();
        System.out.println("Committed order: " + order.getId());
    }
}
~~~

By default, @TransactionalEventListener uses the AFTER_COMMIT phase. The listener requires the event to be published inside an active transaction; if there is no transaction, the listener is not invoked unless fallbackExecution = true is enabled.

For snapshots, the publisher can construct the DTO after determining the business data to announce. However, publishing an event before commit still means synchronous listeners can run before the transaction completes. If a listener performs external side effects such as sending emails or calling APIs, a subsequent rollback can leave side effects inconsistent with committed data.

If you need guarantees that events are not lost when the process stops between commit and sending messages, consider a transactional outbox: write business data and an outbox record in the same transaction, then have a separate publisher send messages from the outbox. This is an event durability concern; choosing ID versus snapshot alone does not solve it.

## 7. Asynchrony and Consistency Over Time

When listeners run asynchronously, the gap between event publishing and handling can be longer. This makes the difference between ID and snapshot stand out clearly:

- With ID-only, the listener may read data that has changed, been deleted, or no longer exists.
- With a snapshot, the listener still has the data at publish time, but the snapshot may be stale relative to the current state.
- With a hybrid payload, the listener can use the snapshot for decisions based on publish time and use the ID when looking up the latest state.

No choice is automatically right in every case. Name fields and describe the contract clearly—for example occurredAt, orderStatusAtCreation, or totalAtCreation—so listeners do not mistake a snapshot for current state.

With async processing, the payload must be fully constructed and never modified after being submitted to the executor. Avoid passing mutable objects or entities still modified by the publisher. Have retry policies, idempotency, and handling for cases where the source data no longer exists.

## 8. Payload Security and Privacy

Event payloads may be written to logs, tracing, dead-letter queues, brokers, backup files, or analytics systems. Therefore, adding data to an event expands where that data can appear.

Before adding a field to a snapshot, check:
- Does the listener genuinely need that field?
- Does the field contain personal data, secrets, tokens, payment info, or internal data?
- Can an ID or a minimized/surrogate value be sent instead?
- Do logs and message stores have appropriate access, retention, and encryption policies?
- Is the subscriber authorized to receive the full snapshot or only part of the data?

Do not put passwords, access tokens, credentials, or unnecessary sensitive data into events. If a subscriber needs restricted data, use an access-controlled API to fetch data according to the subscriber's identity.

## 9. Designing Evolvable Event Contracts

One event may be consumed by multiple listeners. Changing the payload is therefore a contract change between publisher and subscribers.

Some useful principles:

- Use event names describing an event that occurred, such as OrderCreatedEvent.
- Name fields according to the meaning and timing of the data. totalAtCreation is clearer than total if it is a snapshot value.
- Add eventId if you need to uniquely identify a publish occurrence or support idempotency.
- Add occurredAt to express when the event happened; do not confuse it with when a listener receives or processes it.
- You can add correlationId to link events within the same process.
- For messages integrated over a broker, consider schemaVersion and compatibility rules between producer and consumer.
- Avoid changing the meaning of an existing field. Adding optional fields is usually more compatible than changing types or reusing a field name with a different meaning.

If using internal Java records within the same application, changing components can still affect every place instantiating the record. If events are serialized and durably persisted, backward compatibility with old data must also be managed. Do not assume adding fields to a class is always safe for already-stored messages.

## 10. Runnable Example with Java 17+ and Spring Framework 6.2.0

The example below creates three payload variants for comparison: ID-only, snapshot, and hybrid. In a real application, the three variants are alternative design choices; the example publishes all three solely to observe their structure and corresponding listeners.

### 10.1. Project Structure

~~~text
spring-event-payload-choice/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── events/
                        └── EventPayloadDemo.java
~~~

### 10.2. Maven Configuration

File pom.xml:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>spring-event-payload-choice</artifactId>
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

### 10.3. Creating the Demo Program

File src/main/java/com/example/events/EventPayloadDemo.java:

~~~java
package com.example.events;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.List;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

@Configuration
public class EventPayloadDemo {

    public record OrderLineSnapshot(
            String sku,
            int quantity,
            BigDecimal unitPrice
    ) {
    }

    public record OrderSnapshot(
            String orderId,
            String customerId,
            List<OrderLineSnapshot> lines,
            BigDecimal total,
            String status,
            Instant createdAt
    ) {
        public OrderSnapshot {
            lines = List.copyOf(lines);
        }
    }

    public record OrderCreatedByIdEvent(String orderId) {
    }

    public record OrderCreatedWithSnapshotEvent(OrderSnapshot order) {
    }

    public record OrderCreatedHybridEvent(
            String orderId,
            String customerId,
            BigDecimal total,
            Instant occurredAt
    ) {
    }

    public static class OrderPublisher {

        private final ApplicationEventPublisher eventPublisher;

        public OrderPublisher(ApplicationEventPublisher eventPublisher) {
            this.eventPublisher = eventPublisher;
        }

        public void publishAlternatives(OrderSnapshot order) {
            eventPublisher.publishEvent(
                    new OrderCreatedByIdEvent(order.orderId()));

            eventPublisher.publishEvent(
                    new OrderCreatedWithSnapshotEvent(order));

            eventPublisher.publishEvent(
                    new OrderCreatedHybridEvent(
                            order.orderId(),
                            order.customerId(),
                            order.total(),
                            order.createdAt()
                    ));
        }
    }

    public static class IdOnlyListener {

        @EventListener
        public void handle(OrderCreatedByIdEvent event) {
            System.out.println(
                    "ID-only listener: orderId=" + event.orderId());
        }
    }

    public static class SnapshotListener {

        @EventListener
        public void handle(OrderCreatedWithSnapshotEvent event) {
            OrderSnapshot order = event.order();
            System.out.println(
                    "Snapshot listener: orderId=" + order.orderId()
                    + ", lines=" + order.lines().size()
                    + ", total=" + order.total());
        }
    }

    public static class HybridListener {

        @EventListener
        public void handle(OrderCreatedHybridEvent event) {
            System.out.println(
                    "Hybrid listener: orderId=" + event.orderId()
                    + ", customerId=" + event.customerId()
                    + ", total=" + event.total()
                    + ", occurredAt=" + event.occurredAt());
        }
    }

    @Bean
    OrderPublisher orderPublisher(ApplicationEventPublisher publisher) {
        return new OrderPublisher(publisher);
    }

    @Bean
    IdOnlyListener idOnlyListener() {
        return new IdOnlyListener();
    }

    @Bean
    SnapshotListener snapshotListener() {
        return new SnapshotListener();
    }

    @Bean
    HybridListener hybridListener() {
        return new HybridListener();
    }

    public static void main(String[] args) {
        Instant createdAt = Instant.parse("2026-11-11T03:00:00Z");

        OrderSnapshot order = new OrderSnapshot(
                "ORD-1001",
                "CUST-7",
                List.of(
                        new OrderLineSnapshot(
                                "SKU-A", 2, new BigDecimal("25.00")),
                        new OrderLineSnapshot(
                                "SKU-B", 1, new BigDecimal("75.00"))
                ),
                new BigDecimal("125.00"),
                "CREATED",
                createdAt
        );

        try (var context =
                     new AnnotationConfigApplicationContext(
                             EventPayloadDemo.class)) {
            context.getBean(OrderPublisher.class)
                    .publishAlternatives(order);
        }
    }
}
~~~

The nested records inside EventPayloadDemo are implicitly static. OrderSnapshot copies the lines list using List.copyOf to prevent callers from mutating the original list after creating the snapshot. OrderLineSnapshot elements are also records containing only String, int, and BigDecimal.

### 10.4. Running the Program

From the directory containing pom.xml, run:

~~~bash
mvn -q clean compile exec:java -Dexec.mainClass=com.example.events.EventPayloadDemo
~~~

Expected stdout:

~~~text
ID-only listener: orderId=ORD-1001
Snapshot listener: orderId=ORD-1001, lines=2, total=125.00
Hybrid listener: orderId=ORD-1001, customerId=CUST-7, total=125.00, occurredAt=2026-11-11T03:00:00Z
~~~

Spring uses the payload type to select each listener. Each event has its own record, so listeners receive the exact data shape they declare. In the default configuration, synchronous listeners are invoked immediately during each publishEvent call; the publisher completes dispatching one variant before publishing the next.

The program intentionally publishes all three forms for illustration. In real implementations, choose a single contract suited to subscribers' needs rather than publishing three synonymous events for the same operation.

## 11. Common Pitfalls

| Mistake | Consequence | Resolution |
|---|---|---|
| Sending only ID when the listener needs historical data | Listener reads newer state or cannot find the record | Send a snapshot of the fields that need preservation |
| Sending the entire entity | Payload contains lazy proxies, internal data, or mutable references | Map to a dedicated event DTO |
| Snapshot containing too many fields | Large messages, higher data exposure risk, hard-to-change schema | Send only fields subscribers need |
| Sending ID and snapshot without defining canonical source | Duplicate values may contradict each other | Define what point in time snapshot fields represent and validate consistency |
| ID-only listener running before commit | Queries may not see committed data or behavior depends on transaction | Use AFTER_COMMIT when reading after commit is required |
| Async listener receiving a mutable object | Listener may see data mutated after publish | Use immutable DTOs and defensive copies |
| Treating a snapshot as current state | Subscribers process stale data | Name fields to indicate timestamp and re-query if current state is needed |
| Broadcasting sensitive data to all subscribers | Expands storage locations and who can access the data | Data minimization, access control, and retention controls |

## 12. Checklist Before Publishing an Event

- [ ] Determine whether subscribers need current state or data at publish time.
- [ ] Choose ID-only, snapshot, or hybrid based on actual needs.
- [ ] Include in the payload only fields with a clear purpose.
- [ ] Use a dedicated event DTO; do not publish JPA entities directly.
- [ ] Copy collections and avoid mutable references.
- [ ] Name fields to clearly express the meaning and timing of the data.
- [ ] Consider transaction commit/rollback and how listeners read the database.
- [ ] Review personal data, secrets, logging, and retention.
- [ ] Determine whether the event contract needs version, eventId, or correlationId.
- [ ] Test listeners with changed data, deleted records, and asynchronous processing.

## 13. Key Takeaways

ID-only events keep payloads small and let listeners read the current state, but listeners must re-query and may see changed data. Snapshot events preserve selected fields at publish time and allow subscribers to process independently, but increase payload size, shared data scope, and schema management responsibility. The hybrid form combines an ID with a small snapshot when listeners need both immediate data and lookup capability.

Choose the payload based on the point-in-time data subscribers need. Use immutable DTOs instead of entities, publish only necessary fields, and design transactions/durability separately when events must reflect committed data. A snapshot in an event is a data contract; it does not turn an application into an event-sourced one and does not automatically guarantee durable event delivery.