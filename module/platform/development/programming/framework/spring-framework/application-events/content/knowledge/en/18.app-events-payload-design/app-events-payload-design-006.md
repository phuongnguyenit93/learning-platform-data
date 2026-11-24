# Immutable Payloads with Records in Spring Framework Application Events

## 1. Why Use Immutable Payloads?

When a service publishes an `OrderCreated` event, listeners may handle auditing, sending emails, updating statistics, or syncing data. The payload is **a description of an occurrence that already happened**; it should never silently change while listeners are reading it.

Example of a common bug:

```java
List<OrderLine> draftLines = new ArrayList<>();
draftLines.add(new OrderLine("SKU-7", 2, new BigDecimal("75.00")));

publisher.publishEvent(new OrderCreatedEvent(draftLines));

// After publishing, the emitter continues mutating the list.
draftLines.clear();
```

This is a risk-illustration snippet, not standalone code: `OrderLine` and `OrderCreatedEvent` must be defined. If the event holds **the same reference to a mutable list**, an asynchronously executing listener might see an empty list even though the order had one line at publication time. Even in synchronous processing, one listener could corrupt data that another listener is about to read.

Designing immutable payloads brings benefits:

- **Consistency:** listeners observe the exact business data finalized when the event was created.
- **Simpler concurrency:** reduces races caused by mutating one object from multiple threads.
- **Easier testing:** payloads can be compared by value using stable sample data.
- **Separation of responsibilities:** the publisher builds a snapshot; listeners use the snapshot to react without mutating the original event.
- **Traceability:** logs and reconciliation based on event IDs and values are far more reliable.

Java 17 supports `record`, which fits value-oriented payloads very well. However, **records only provide shallow immutability**: if a record contains a `List`, `Map`, array, or mutable object, you must protect them yourself.

## 2. Java 17 Records: Value-Carrying Data Types

A small payload can be written as:

```java
public record OrderCreated(
        String eventId,
        String orderId,
        Instant occurredAt
) {}
```

The record class above has:

- Three components: `eventId`, `orderId`, `occurredAt`.
- A canonical constructor matching the components.
- Accessors named `eventId()`, `orderId()`, and `occurredAt()`.
- Compiler-generated `equals()`, `hashCode()`, and `toString()` unless explicitly overridden.
- `private final` component fields; no setters exist for them.

Usage:

```java
OrderCreated event = new OrderCreated(
        "evt-101",
        "ORD-42",
        Instant.parse("2026-11-01T08:00:00Z")
);
System.out.println(event.orderId()); // ORD-42
```

This illustrative snippet requires importing `java.time.Instant` and declaring the `OrderCreated` record in the project.

**Key characteristics of records:**

1. A record class is `final`; it cannot extend another class such as `ApplicationEvent`. It implicitly extends `java.lang.Record`.
2. Records can `implements` interfaces.
3. No extra instance fields can be declared outside the record components; static fields, methods, constructors, and invariant checks are allowed.
4. `final` prevents reassigning the **field reference**, not mutating the referenced object.
5. Component values participate in `equals/hashCode` semantics; if a component is mutated indirectly, using the record as a map/set key becomes very dangerous.

For application events, a record is a **value-oriented data carrier**, not a JPA entity with a lifecycle and mutable identity.

## 3. Why Do Records Fit Spring Application Events Directly?

Since Spring Framework 4.2, `ApplicationEventPublisher` allows publishing **any non-null object**, without requiring a subclass of `ApplicationEvent`. Because records cannot extend `ApplicationEvent`, this is the natural fit:

```java
publisher.publishEvent(
        new OrderCreated(
                "evt-101",
                "ORD-42",
                Instant.parse("2026-11-01T08:00:00Z")
        )
);
```

When receiving a non-`ApplicationEvent` object, Spring wraps it in a `PayloadApplicationEvent<T>` to route it through the event infrastructure. With annotation-based listeners, Spring can extract the payload and pass it directly to a method with the matching parameter type:

```java
@EventListener
public void onOrderCreated(OrderCreated event) {
    System.out.println("Received: " + event.orderId());
}
```

There is no need to declare `onOrderCreated(PayloadApplicationEvent<OrderCreated>)` just to use `@EventListener`. Spring's adapter handles wrapping and unwrapping the payload for the method's parameter type.

Distinguish the following classes/constructs:

| Class / Construct | Role |
| --- | --- |
| `OrderCreated` record | Business snapshot defined by the application |
| `PayloadApplicationEvent<OrderCreated>` | Spring's wrapper when an event is published as a POJO |
| `@EventListener(OrderCreated)` | Listener registration targeting the payload directly |
| `ApplicationListener<E>` | Interface where `E extends ApplicationEvent`; cannot use `E=OrderCreated` directly since records do not extend `ApplicationEvent` |

If using the `ApplicationListener` interface, you can accept `PayloadApplicationEvent<OrderCreated>` or use `ApplicationListener.forPayload(...)` (when registering appropriately). For most applications, an `@EventListener` method accepting the record is simpler and clearer.

**Do not confuse with durability:** regular in-process Spring Application Events are not a message broker and do not automatically persist events to a database. Immutable payloads do not provide retries, durability, or exactly-once delivery.

## 4. Shallow Immutability vs. Deep Immutability

Consider the record:

```java
public record OrderCreated(String orderId, List<String> skuCodes) {}
```

Good point: external code cannot call `event.skuCodes = otherList`.

Problem: `event.skuCodes()` returns the **list reference** stored in the field. If an `ArrayList` is passed to the constructor, both emitter and receiver can mutate the list contents:

```java
List<String> draft = new ArrayList<>(List.of("SKU-7"));
OrderCreated event = new OrderCreated("ORD-42", draft);

draft.add("SKU-8");
event.skuCodes().clear();
```

There are no setters, yet the event data still mutates. This is not an "immutable event" in the value-stability sense.

### 4.1. Defensive Copying with `List.copyOf`

A **compact constructor** on a record can normalize input components:

```java
public record OrderCreated(
        String orderId,
        List<String> skuCodes
) {
    public OrderCreated {
        Objects.requireNonNull(orderId, "orderId");
        skuCodes = List.copyOf(
                Objects.requireNonNull(skuCodes, "skuCodes"));
    }
}
```

Requires importing `java.util.List` and `java.util.Objects`.

Upon record construction, the `skuCodes` parameter is replaced with an unmodifiable list; Java assigns all components from the parameters when the compact constructor finishes. You must not assign `this.skuCodes = ...` directly inside a compact constructor.

Key properties of `List.copyOf(...)`:

- Produces a list that **cannot be modified via the List API**, containing the elements at snapshot time.
- Subsequent changes to the mutable input list do not alter the snapshot list.
- Disallows `null` elements; throws `NullPointerException` if any element is null.
- If the source is already a suitable unmodifiable list, the implementation may reuse it; do not rely on reference identity.
- **Does not deep-copy elements.** A mutable element can still be mutated even though the list structure itself is immutable.

### 4.2. Comparing with `Collections.unmodifiableList`

`Collections.unmodifiableList(draft)` normally creates an **unmodifiable view** backed by `draft`, not an independent snapshot. Any code still holding a reference to `draft` can mutate it, and the view reflects those mutations.

```java
List<String> draft = new ArrayList<>(List.of("A"));
List<String> view = Collections.unmodifiableList(draft);
List<String> snapshot = List.copyOf(draft);

draft.add("B");

System.out.println(view);     // [A, B]
System.out.println(snapshot); // [A]
```

This snippet can run with the corresponding Java Collections imports. This is why `List.copyOf` fits event payloads so well: the snapshot is **isolated from structural mutations of the mutable source**.

### 4.3. `List.copyOf` Does Not Solve Nested Mutability

```java
public final class MutableLine {
    public String sku;
    public int quantity;
}

// Even though lines is List.copyOf(original),
// each MutableLine can still have its quantity modified.
```

With a list of `MutableLine`, `List.copyOf` does not clone each element; the exact same `MutableLine` objects remain shared. To make the payload genuinely stable, you can:

- Represent each element as a record whose **inner components are all immutable**.
- Copy each mutable object into an immutable snapshot before putting it into the list.
- Use built-in value types like `String`, `UUID`, `Instant`, `BigDecimal` instead of holding entities undergoing updates.
- Avoid putting `byte[]`, `Date`, mutable maps, or ORM entities directly into events.

When a field is `List<OrderLine>` and the `OrderLine` record holds only `String`, `int`, and `BigDecimal`, deep immutability becomes far easier to achieve.

## 5. Complete Java 17 + Spring 6.2 Example: Snapshot Record Unchanged After Publishing

The program demonstrates:

1. Creating a draft list of order details from an `ArrayList`.
2. Constructing an `OrderCreated` record whose compact constructor calls `List.copyOf`.
3. Mutating the draft list; the record payload **remains unchanged**.
4. Attempting to mutate `payload.lines()` and catching `UnsupportedOperationException`.
5. Publishing the record directly via `ApplicationContext.publishEvent(...)`.
6. `@EventListener` receives the record payload and computes the total from the snapshot.

The example uses no database, Spring Boot, web server, or thread pool, because the focus here is **payload data stability**.

### 5.1. Project Structure

```text
immutable-payload-event/
├── pom.xml
└── src/main/java/example/ImmutablePayloadDemo.java
```

### 5.2. File `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>immutable-payload-event</artifactId>
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
                <configuration>
                    <mainClass>example.ImmutablePayloadDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 5.3. File `src/main/java/example/ImmutablePayloadDemo.java`

```java
package example;

import java.math.BigDecimal;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicReference;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class ImmutablePayloadDemo {

    // Child record containing only immutable String, int, and BigDecimal.
    public record OrderLine(String sku,
                            int quantity,
                            BigDecimal unitPrice) {
        public OrderLine {
            Objects.requireNonNull(sku, "sku");
            Objects.requireNonNull(unitPrice, "unitPrice");

            if (sku.isBlank()) {
                throw new IllegalArgumentException("sku is blank");
            }
            if (quantity <= 0) {
                throw new IllegalArgumentException(
                        "quantity must be positive");
            }
            if (unitPrice.signum() < 0) {
                throw new IllegalArgumentException(
                        "unitPrice cannot be negative");
            }
        }
    }

    public record OrderCreated(
            String eventId,
            String orderId,
            Instant occurredAt,
            List<OrderLine> lines) {

        // Compact constructor: validate + snapshot inputs.
        public OrderCreated {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(orderId, "orderId");
            Objects.requireNonNull(occurredAt, "occurredAt");

            if (eventId.isBlank() || orderId.isBlank()) {
                throw new IllegalArgumentException(
                        "eventId/orderId cannot be blank");
            }

            lines = List.copyOf(
                    Objects.requireNonNull(lines, "lines"));
            if (lines.isEmpty()) {
                throw new IllegalArgumentException(
                        "Order must have at least one line");
            }
        }
    }

    public static final class Evidence {
        private final AtomicReference<OrderCreated> received =
                new AtomicReference<>();

        public OrderCreated received() {
            return Objects.requireNonNull(
                    received.get(), "Listener did not receive event");
        }
    }

    public static class OrderListener {
        private final Evidence evidence;

        public OrderListener(Evidence evidence) {
            this.evidence = evidence;
        }

        @EventListener
        public void onCreated(OrderCreated event) {
            evidence.received.set(event);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Evidence evidence() {
            return new Evidence();
        }

        @Bean
        public OrderListener orderListener(Evidence evidence) {
            return new OrderListener(evidence);
        }
    }

    public static void main(String[] args) {
        List<OrderLine> draft = new ArrayList<>();
        draft.add(new OrderLine(
                "SKU-7", 2, new BigDecimal("75.00")));

        Instant timestamp =
                Instant.parse("2026-11-01T08:00:00Z");

        OrderCreated event = new OrderCreated(
                "evt-101", "ORD-42", timestamp, draft);

        // The creator can still mutate draft; the event has already snapshotted it.
        draft.add(new OrderLine(
                "SKU-8", 1, new BigDecimal("10.00")));

        boolean blocked = false;
        try {
            event.lines().add(new OrderLine(
                    "SKU-9", 1, new BigDecimal("20.00")));
        } catch (UnsupportedOperationException expected) {
            blocked = true;
        }

        // Records support equals by component values.
        OrderCreated sameValue = new OrderCreated(
                "evt-101", "ORD-42", timestamp,
                List.of(new OrderLine(
                        "SKU-7", 2, new BigDecimal("75.00"))));

        System.out.println("Draft line count: " + draft.size());
        System.out.println("Event line count: " + event.lines().size());
        System.out.println("Mutation rejected: " + blocked);
        System.out.println("Equal payloads: " + event.equals(sameValue));

        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            // Record is a POJO payload, not extending ApplicationEvent.
            context.publishEvent(event);

            OrderCreated received =
                    context.getBean(Evidence.class).received();

            BigDecimal total = received.lines().stream()
                    .map(line -> line.unitPrice().multiply(
                            BigDecimal.valueOf(line.quantity())))
                    .reduce(BigDecimal.ZERO, BigDecimal::add);

            System.out.println(
                    "Listener order: " + received.orderId());
            System.out.println(
                    "Listener total: " + total.toPlainString());
        }
    }
}
```

### 5.4. Running and Results

From the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

**Six lines printed by the program** in the default configuration, excluding Maven/Spring logs if any:

```text
Draft line count: 2
Event line count: 1
Mutation rejected: true
Equal payloads: true
Listener order: ORD-42
Listener total: 150.00
```

**Why is the output right?**

- `draft` has two lines after `SKU-8` is added.
- `OrderCreated` called `List.copyOf(draft)` when constructed, so `event.lines()` holds only the original `SKU-7` line.
- Attempting `event.lines().add(...)` throws `UnsupportedOperationException`; the program intentionally catches it and prints `true`.
- Two `OrderCreated` instances share identical values across all components, including `OrderLine` and `BigDecimal("75.00")`, so `equals` returns `true`.
- Spring accepts the record via `publishEvent(Object)` and routes it to the `@EventListener` method with parameter `OrderCreated`.
- The listener observes one line with `quantity=2` and `unitPrice=75.00`; `BigDecimal` yields total `150.00` without `double` precision loss.
- The example uses the default synchronous multicaster. Immediately after `context.publishEvent(event)`, the listener has stored the record into `Evidence`, so the program can read the result right away. With async listeners, wait using an appropriate latch/future.

**QA note:** the filename matches `public class ImmutablePayloadDemo` and the Maven command runs a single `main`. The example uses Java 17 records and Spring Framework 6.2.0; Spring Boot is not needed. All objects in the event are immutable under the current design because `OrderLine` has no mutable components and the list is snapshotted.

## 6. How to Write a Compact Constructor Properly

A record allows defining a **compact canonical constructor**:

```java
public record UserRegistered(String userId, String email) {
    public UserRegistered {
        Objects.requireNonNull(userId, "userId");
        Objects.requireNonNull(email, "email");

        userId = userId.trim();
        email = email.trim().toLowerCase(Locale.ROOT);

        if (userId.isBlank() || email.isBlank()) {
            throw new IllegalArgumentException(
                    "userId/email must not be blank");
        }
    }
}
```

This is a standalone illustrative snippet on record syntax, requiring imports for `Objects` and `Locale`. After the compact constructor finishes, Java assigns **the normalized parameter values** to the corresponding components. Validating and normalizing in the constructor prevents callers from creating invalid records that every listener would otherwise have to check again.

Some rules:

1. Do not call setters because records have no default setters.
2. Do not assign `this.field` directly inside a compact constructor; operate only on parameters or call appropriate helpers.
3. Never turn the constructor into a place for I/O, database access, or network calls. Constructors should check invariants and build fast, deterministic snapshots.
4. If the payload carries validation annotations like `@NotBlank`, merely declaring annotations **does not automatically** trigger Bean Validation when calling `new Record(...)`. Integrate a validator explicitly if you want annotation-based checks.
5. Do not mix event validation with stateful business rules. For example, "can the order be paid during these hours?" belongs in service/domain logic, not stuffed into a record constructor.

**Note:** normalizing email via `toLowerCase` in real applications requires checking business rules, especially for the email local-part. The snippet above only illustrates input normalization technique, not a universal email normalization spec.

## 7. What About Arrays, `byte[]`, and Binary Data?

A record containing an array like this is **not immutability-safe**:

```java
public record FileUploaded(String fileId, byte[] checksum) {}
```

The record's fields are final, yet both the constructor caller and callers of the `checksum()` accessor can hold a reference to the same array and mutate elements. Copy both on **input** and on **output**:

```java
public record FileUploaded(String fileId, byte[] checksum) {
    public FileUploaded {
        Objects.requireNonNull(fileId, "fileId");
        checksum = Objects.requireNonNull(
                checksum, "checksum").clone();
    }

    @Override
    public byte[] checksum() {
        return checksum.clone();
    }
}
```

This snippet requires importing `Objects`. It blocks external mutations through the array returned by the accessor. Still, there is another catch: a record's auto-generated `equals/hashCode` **does not compare array contents like `Arrays.equals`**; it uses array reference equality. Two payloads with identical bytes in two separate arrays may not be `equals`.

Therefore, if binary data serves as an important value, consider:

- A dedicated immutable wrapper implementing `Arrays.equals`/`Arrays.hashCode`.
- A normalized digest string (such as a hex hash) instead of `byte[]` when appropriate.
- Overriding `equals/hashCode` carefully if the record must carry an array.

Cloning the array protects contents, **not automatically fixing** array equality semantics.

## 8. Advanced Collections: `Map`, `Set`, and Nested Objects

Depending on the event, you can use `Map.copyOf`, `Set.copyOf`, and `List.copyOf`:

```java
public record ProfileChanged(
        String profileId,
        Map<String, String> fields,
        Set<String> tags
) {
    public ProfileChanged {
        Objects.requireNonNull(profileId, "profileId");
        fields = Map.copyOf(
                Objects.requireNonNull(fields, "fields"));
        tags = Set.copyOf(
                Objects.requireNonNull(tags, "tags"));
    }
}
```

Requires importing `Map`, `Set`, and `Objects`. These `copyOf` methods build collection structures unmodifiable via normal APIs, guarding against structural mutations of mutable source collections. However:

- Values in `Map<K,V>`, if mutable objects, can still be mutated.
- `Set.copyOf` should not be relied upon for stable iteration order. If order matters, model it explicitly, such as with a normalized, snapshotted `List`.
- `Map.copyOf` and `Set.copyOf` reject null keys/values or elements; validate inputs upfront.
- Copying collections incurs memory/CPU cost proportional to element count. For oversized payloads, send identifiers and query versioned snapshot data from durable storage instead of copying an entire object graph.
- If a record nests another record whose inner record holds a mutable entity, the overall payload **is still not immutable**. Inspect from the leaf data inward.

A safe approach for nested data is mapping from mutable entities to **snapshot DTOs** using records:

```java
public record CustomerSnapshot(
        String customerId,
        String displayName
) {}

public record OrderSnapshot(
        String orderId,
        CustomerSnapshot customer,
        List<OrderLine> lines
) {
    public OrderSnapshot {
        lines = List.copyOf(lines);
    }
}
```

This example assumes `OrderLine` is an immutable record as in section 5. This is a type-model snippet, not a standalone program without all definitions/imports.

## 9. Designing Event Fields Around the Business Domain

Payloads should hold **immutable facts** at event publication time, not an object for listeners to freely update.

A record typically needs:

| Field | Role | Suggestion |
| --- | --- | --- |
| `eventId` | Identifies one occurrence of the event | Stable across retries/replays; can use UUID |
| `aggregateId` / `orderId` | Related business object | Immutable string/UUID |
| `occurredAt` | When the business event actually happened | `Instant`, avoid ambiguous local timezones |
| `eventType` or record type | Event meaning | Prefer meaningful class names like `OrderCreated` |
| `version` / `aggregateVersion` | Distinguishes changes over time | Use when consumers need ordering checks |
| Essential field snapshots | Sufficient information for handlers | Include only needed parts, avoid huge object graphs |
| `correlationId` | Links to a request/workflow | Useful for tracing, not a default idempotency key |

**`eventId` should not change when retrying the same event.** If every retry generates a new ID, listeners deduplicating by `eventId` can no longer recognize it as the same event.

Separate `eventId` from `orderId`: one order can undergo multiple valid events (`OrderCreated`, `OrderPaid`, `OrderCancelled`), while `eventId` identifies one specific event. Sharing the same `orderId` does not mean those events are duplicates.

`occurredAt` should represent when the domain event was created, remaining fixed regardless of when listeners run. Avoid timezone-less `LocalDateTime` if the system compares across regions; `Instant` is a clean choice for UTC timestamps.

### Do Not Carry Secrets or Unnecessary Object Graphs

`record.toString()` is auto-generated and normally includes all component values. If a record contains access tokens, passwords, card numbers, or sensitive personal data, a statement like `logger.info("event={}", event)` can leak data.

Include only necessary information in payloads; for sensitive content, use IDs or minimized data and control logging, serialization, and access policies. Never assume "immutable" equals "secure".

## 10. Records, Synchronous, and Asynchronous Events

Immutability becomes especially critical when listeners run on another thread:

```java
@Async("notificationExecutor")
@EventListener
public void onCreated(OrderCreated event) {
    // Read event snapshot on worker thread.
}
```

The snippet above requires `@EnableAsync`, a `notificationExecutor` bean, and a Spring listener bean. It only illustrates how they combine, not part of the runnable program in section 5.

With proper immutable design, the publisher can continue other work without mutating event data. Yet **records do not automatically make everything thread-safe**:

1. A record holding an unprotected mutable reference still suffers data races.
2. Listeners can modify databases or external services; those actions are not made "immutable" by a record.
3. Execution order across async listeners is not guaranteed; handle ordering explicitly if business logic requires it.
4. The publisher does not automatically wait for async listeners to finish; tests need `CountDownLatch`/`CompletableFuture` or appropriate wait mechanisms.
5. In-process Spring events are not durably persisted across crashes. If delivery is mandatory, use an outbox/broker.
6. Exceptions in `@Async void` do not automatically propagate to the publisher; configure an error handler and observability appropriately.

### Do Not Publish Mutable Entities Assuming They Are Snapshots

Design anti-pattern:

```java
@EventListener
public void onPaid(OrderPaid event) {
    event.orderEntity().setStatus("SHIPPED");
}
```

This pattern should be avoided whenever `orderEntity()` returns a mutable entity. It couples the listener to the persistence context and causes other listeners to observe a state different from publication time. Instead, use a record carrying `orderId`, `statusAtEvent`, `aggregateVersion`, or needed value snapshots; the event-handling service will load data and coordinate its own transaction if needed.

## 11. Records with `TransactionalEventListener`

A record payload works well with `@TransactionalEventListener`:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderCreated event) {
    // React after the event-publishing transaction has committed.
}
```

This snippet requires importing `TransactionalEventListener` and `TransactionPhase`; the event must be published within a real transaction managed by the active transaction manager. `@TransactionalEventListener` defaults to `AFTER_COMMIT`; `fallbackExecution` defaults to `false`, so publishing outside a transaction normally skips transaction-bound listeners.

Record payloads help ensure post-commit listeners see the **original snapshot** of IDs, line items, and timestamps even if the publisher continues updating domain objects afterward. Still:

- `AFTER_COMMIT` does not guarantee events will not be duplicated or lost on a process crash.
- The originating transaction has already committed; if the listener writes to the database inside a post-commit callback, it needs a proper new transaction (e.g., `REQUIRES_NEW` via proxy/`TransactionTemplate`) to ensure subsequent changes commit.
- With multi-worker or retry systems, add idempotency keys and unique constraints if side effects must not repeat.
- If you must **guarantee zero lost events between business commit and handlers**, write the outbox record **within the same business transaction** rather than relying solely on an in-memory post-commit listener.

Payload immutability and transaction policies are **complementary responsibilities**, not substitutes for each other.

## 12. Why Shouldn't Records Be Used as JPA Entities?

A data-carrying record can be ideal as an event DTO yet is usually **unsuitable as a JPA entity** under the standard ORM entity model:

- JPA entities require identity tracking and state management inside a persistence context.
- ORMs typically expect constructors and state access/mutation mechanisms; records themselves are final and lack component setters.
- Entities have lazy/proxy associations and mutable lifecycles; event snapshots should stay decoupled from those behaviors.
- Some mapping/projection tools support records, yet **DTO projection** differs from using a record as a managed entity.

Design pattern:

```text
OrderEntity (mutable, part of persistence context)
      |
      |  map to required snapshot
      v
OrderCreated record (immutable)
      |
      |  publishEvent
      v
@EventListener(OrderCreated)
      |
      +--> Audit / metrics / notifications
```

Avoid placing `OrderEntity` directly in a record component because the record freezes only the **entity reference**, not the entity's state. In a listener running after the transaction or on a worker thread, lazy relations can also trigger access errors.

## 13. Data Compatibility, Serialization, and Versioning

A record used as an internal Spring event payload **does not automatically mean** it suits every wire transport format. When integrating Kafka/RabbitMQ/HTTP:

- Serializers/deserializers must be configured to understand records and types like `Instant` and `BigDecimal`.
- Modern versions of Jackson support records well in many cases, yet you must test the actual JSON output and project dependencies.
- Adding/removing/renaming a record component can alter the canonical constructor, payload schema, and consumer compatibility.
- Staggered service deployments may require schema evolution rules, default values, and backward/forward compatibility tests.
- Do not dump complex object graphs into events just because records support nested data; prefer small schemas with clear field names.
- Records **do not automatically implement `Serializable` merely by being records**. If using Java Serialization, evaluate the contract and declare it intentionally; for microservice integration, JSON/Avro/Protobuf schemas are usually explicit design decisions.

When changing payload contents in a system with durably stored events, define versioning, compatibility tests, and how old consumers handle new fields. **Instance immutability** does not equate to **schema immutability across releases**.

## 14. `equals`, `hashCode`, and Value Traps

Records generate `equals/hashCode` from their components, which is handy for comparing data in tests. Still, component semantics matter:

- Two `BigDecimal` values with equal mathematical magnitude but different scales, e.g., `new BigDecimal("75.0")` and `new BigDecimal("75.00")`, **are not equal under `BigDecimal.equals`**. Records delegate to component equality, so normalize scale if business rules require it.
- A `List` compares elements in order; reordering lines can make two payloads unequal even when totals match.
- An array component compares by reference, not by element content.
- A mutable object inside a component can cause `hashCode` to shift after the record has been inserted as a key in a `HashMap`.
- Do not mechanically use the entire record payload as an idempotency key; a stable `eventId` and consumer namespace are usually better.

Scale example:

```java
BigDecimal a = new BigDecimal("75.0");
BigDecimal b = new BigDecimal("75.00");
System.out.println(a.compareTo(b) == 0); // true: same numeric value
System.out.println(a.equals(b));         // false: different scales
```

This is a standalone Java snippet importing `BigDecimal`. This discrepancy is not a record bug, but the semantics of the component type.

## 15. Testing Payload Immutability

A record payload test should not merely assert "there are no setters". Test these scenarios:

| Scenario | What to Verify |
| --- | --- |
| Built from an `ArrayList`, then source list mutated | `record.lines()` remains unchanged |
| Attempt to add/remove via `record.lines()` accessor | Throws `UnsupportedOperationException` |
| Input list contains `null` | Constructor rejects per `List.copyOf` contract |
| Mutable nested elements | Must deep-copy or use immutable elements |
| Array/`byte[]` inside record | Both constructor and accessor perform defensive copies |
| Invalid payload | Constructor rejects blank IDs, invalid quantities, negative prices |
| Two snapshots with identical content | `equals/hashCode` match per component rules |
| Published via Spring `publishEvent(Object)` | `@EventListener(RecordType)` listener receives the exact payload |
| Async listener | Cannot be corrupted by caller mutations while queued |
| Event stored/sent to another system | Serialization and schema compatibility are verified |

**Four essential tests** can start from the program in section 5: source list size after mutation, record list size, mutation via accessor rejected, and listener computing the expected total. No web server is needed just to test POJO events.

For unit tests proving snapshotting, use JUnit to build the record first, mutate the source list afterward, and assert the original elements stay intact. For Spring integration tests, let Spring actually publish the event rather than calling the handler method directly and claiming the event infrastructure works.

## 16. Common Pitfalls

1. **Assuming every record is deeply immutable.** Final record components can hold mutable `List`s or entities.
2. **Passing an `ArrayList` straight into a record without copying.** Both publisher and consumer can mutate the data.
3. **Using `Collections.unmodifiableList` on a list still referenced elsewhere.** A view is not a snapshot.
4. **Calling `List.copyOf` and forgetting mutable nested elements.** Only the list structure is protected.
5. **Holding `byte[]` without copying in both directions.** Callers can mutate the array through the accessor.
6. **Believing records with array fields compare array contents.** Default array equality is by reference.
7. **Putting a JPA entity inside an event record.** Freezes only the reference, not entity state, and risks lazy-loading errors.
8. **Putting an entire customer object with sensitive data into the payload.** `toString`/logs/serialization can leak data.
9. **Forgetting null and business invariant checks.** Default record constructors do not automatically know IDs cannot be blank or prices cannot be negative.
10. **Confusing records with `ApplicationEvent` subclasses.** Records do not extend `ApplicationEvent`; use `publishEvent(Object)` and payload `@EventListener`s.
11. **Confusing immutable events with durable delivery.** In-memory Spring events do not replace an outbox or broker.
12. **Failing to manage schema versions.** Adding a component can prevent old consumers from deserializing.
13. **Relying on async ordering.** Immutability does not guarantee listeners finish in order.
14. **Regenerating timestamps on every retry.** An event replay should preserve the original `eventId` and business occurrence time for accurate tracing.

## 17. Checklist When Designing Event Records

- [ ] Event name expresses a fact that occurred (e.g., `OrderCreated`, `PaymentCaptured`).
- [ ] Uses clearly immutable components: `String`, `UUID`, `Instant`, `BigDecimal`, enums, or nested records with immutable contracts.
- [ ] Uses `List.copyOf`/`Map.copyOf`/`Set.copyOf` on mutable collection inputs and checks nested elements.
- [ ] For arrays/`Date`/mutable objects, performs defensive copies on both input and output.
- [ ] Constructor validates IDs, quantities, amounts, timestamps, and nulls per required invariants.
- [ ] Does not embed ORM entities, connections, transactions, service objects, or entire mutable graphs into the payload.
- [ ] Uses a stable `eventId`, semantically clear `occurredAt`, and correlation/version where needed.
- [ ] Avoids putting unnecessary secrets/PII into payloads or unguarded `toString` logs.
- [ ] Spring listeners accept the record directly via `@EventListener` after `publishEvent(Object)`.
- [ ] Tests verify payload stability after mutating inputs, rejected mutations, and accurate data received by listeners.
- [ ] If async/transactions/outbox are used, error handling, ordering, idempotency, and durability are designed separately.
- [ ] If payloads travel over a broker/JSON, serialization and versioned schema evolution are tested.

**Takeaway:** `record` helps write payloads that are **concise, clear, and easy to compare by value**. Yet records provide only shallow immutability. For truly safe snapshots in Spring Application Events, build payloads from immutable values, defensively copy collections/arrays, and keep the data contract stable. Spring can publish records directly via `ApplicationEventPublisher.publishEvent(Object)` and deliver them to `@EventListener` by payload type.

## References

- [Oracle Java 17 — Records](https://docs.oracle.com/en/java/javase/17/language/records.html)
- [Oracle Java 17 — Creating Unmodifiable Copies of Collections](https://docs.oracle.com/en/java/javase/17/core/creating-immutable-lists-sets-and-maps.html)
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Javadoc — ApplicationEventPublisher](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Javadoc — PayloadApplicationEvent](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/PayloadApplicationEvent.html)
