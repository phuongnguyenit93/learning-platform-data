# Distinguishing Root Events and Derived Events in Spring Framework Application Events

## 1. Why Distinguish the Two Kinds of Events?

A single business action can initiate an entire **chain of events**. For example, after an order is accepted, the application needs to request inventory reservation, send a confirmation email, and update a read model. Looking only at logs containing many events, it is hard to tell:

- Which event represents the **initiating business occurrence**?
- Which events were **created while handling** an earlier event?
- Do two different event types belong to the same request/workflow?
- When replaying an old event, should **derived events be regenerated**, or should only the read model be updated?
- If a listener receives a duplicate, how do we avoid sending the email or deducting inventory twice?

We define:

**Root/original event:** the event chosen as the starting point for the processing chain under consideration—for example, `OrderAccepted` published by a business service when an order is accepted. It records an independently meaningful fact or state change.

**Derived/follow-up event:** an event created **because an earlier event was processed**—for example, `InventoryReservationRequested` published when a listener receives `OrderAccepted` and decides to request stock reservation.

This distinction is **not two built-in classes in Spring**: Spring does not automatically label all events as “root event” or “derived event”. It is **application-designed semantics**. An event can be a derived event within a larger chain while serving as the starting point of a smaller analytical branch.

> **Key takeaway:** “root/derived” describes **causality and business origin**, not execution priority, required Java types, or whether an event is synchronous or asynchronous.

## 2. Easy-to-Picture Example: One Root Event, Two Derived Branches

Suppose the application has confirmed order `ORD-42`:

```text
OrderAccepted
  eventId = evt-100
  correlationId = flow-7
  causationId = null
         |
         | listener handles OrderAccepted
         |
         +----> InventoryReservationRequested
         |        eventId = evt-101
         |        correlationId = flow-7
         |        causationId = evt-100
         |
         +----> ConfirmationEmailRequested
                  eventId = evt-102
                  correlationId = flow-7
                  causationId = evt-100
```

- `OrderAccepted` is the **root event of the chain** under consideration.
- `InventoryReservationRequested` and `ConfirmationEmailRequested` are **two direct derived events**, with **two separate IDs**.
- All three share `correlationId = flow-7` because they belong to the same workflow.
- Each derived event carries `causationId = evt-100`, pointing to **the event that directly caused it**.
- A derived event does not mean the requested work already succeeded: the `Requested` suffix expresses **a request to act**. Only after inventory is reserved or the email is sent should a corresponding fact event like `InventoryReserved` or `ConfirmationEmailSent` be emitted.

If processing `InventoryReservationRequested` produces `InventoryReserved`, the new event will have `causationId = evt-101`, not `evt-100`, because its direct cause is the inventory reservation request event. Meanwhile, `correlationId` can remain `flow-7`.

The diagram above is **a causal graph**, which can branch rather than being a linear list. When multiple listeners process the same event, multiple independent derived branches can exist.

## 3. Three Key Identifiers: eventId, correlationId, causationId

| Property | Question answered | Common rule |
| --- | --- | --- |
| `eventId` | “Which **occurrence** of an event is this?” | Unique per occurrence; preserved on retry/replay of the same occurrence |
| `correlationId` | “Which events belong to the **same request/workflow**?” | Usually created at the request boundary and **propagated onward** |
| `causationId` | “Which event **directly caused** the current event?” | Equals the parent event's `eventId`; may be `null` on the root event |

Example:

```text
root.eventId        = "evt-100"
root.correlationId  = "flow-7"
root.causationId    = null

derived.eventId        = "evt-101"
derived.correlationId  = "flow-7"
derived.causationId    = "evt-100"
```

**Do not conflate these IDs:**

1. Two events with the **same correlationId** are not duplicates; they are simply related within the same workflow.
2. Two events with the **same causationId** can be **siblings** created from the same parent event.
3. Two events with the **same eventId** in a replay mechanism normally denote **the same event being re-emitted/re-read**, not two distinct business facts.
4. A derived event **must have its own eventId** if it describes a new occurrence, even if it carries the same data as the root event.
5. One business action can produce multiple root events for different aggregates; “root” scope must be defined per workflow.
6. If you also carry `aggregateId`, `aggregateVersion`, `tenantId`, or `traceId`, do not collapse them into one ID; each field has its own meaning.

### A Root Event Does Not Necessarily Have a Null causationId System-Wide

An `OrderAccepted` event may originate from an HTTP request, an external message, or another event. When analyzing an **internal Spring Application Events chain**, we may treat it as root and set `causationId = null`. In a cross-service event system, however, you may retain the `causationId` from the upstream system. Thus “root” is **relative to the observation scope**, not an absolute property of a class.

### Why Not Generate a New UUID on Replay?

Suppose event `evt-100` is re-read from an event store. If replaying that record mints `eventId = evt-999`, consumers relying on `eventId` may treat it as a brand-new occurrence and run side effects a second time. When replaying **the same event**, preserve `eventId` and origin metadata. If the replay is meant to **initiate a new business action**, model it as a new action/command with a new ID rather than calling it a verbatim replay of the original event.

For derived events regenerated during a replay, the ID policy must be explicit: reuse the stored derived ID, or deduplicate using a stable business/causation key. Never assume freshly generated random UUIDs will protect against duplicates.

## 4. Distinguishing Semantics from Spring APIs

Spring Framework Application Events supports publishing:

```java
publisher.publishEvent(someObject);
```

For objects that do not extend `ApplicationEvent`, Spring can wrap them in `PayloadApplicationEvent<T>` for delivery through the event infrastructure. An `@EventListener` method can still accept the payload type directly:

```java
@EventListener
public void onOrderAccepted(OrderAccepted event) {
    // Reads an application-defined record.
}
```

Spring **does not infer** from method names whether an event is root or derived. When a listener creates and publishes a new event, causality comes from **business logic and the event's metadata**.

Pay special attention to these distinctions:

| Concept | Role | Do not confuse with |
| --- | --- | --- |
| `ApplicationEventPublisher.publishEvent(Object)` | Publishes an event object | Persisting an event into an event store |
| `PayloadApplicationEvent` | Spring wrapper for a POJO payload | An identifier for “derived event” |
| `ApplicationEvent.getSource()` | Source object of an `ApplicationEvent` | Business `causationId` |
| `@EventListener` | Registers a method to receive events by type/condition | Automatic causality graph |
| `@Order` | Adjusts invocation order of listeners in the same dispatch | Guaranteeing business completion order under async |
| `@Async` | Offloads execution to an executor | A new event or replay mode |
| `@TransactionalEventListener` | Binds a callback to a transaction phase | Deduplication or durable event storage |

**A common pitfall:** `ApplicationEvent.getSource()` refers to the object Spring used as the source, with no contract that it is the **immediate parent event**. With `PayloadApplicationEvent`, the source can be the context/publisher. To store stable causality across processes and replays, use **explicit metadata** like `causationId` rather than relying on `getSource()`.

## 5. Creating Derived Events from Synchronous Listeners

Spring supports a convenience feature on `@EventListener`: a **synchronous** listener method can **return** a new event, and the adapter publishes the returned value as the next event.

```java
@EventListener
public InventoryReservationRequested derive(OrderAccepted event) {
    return new InventoryReservationRequested(
            /* derived event metadata */,
            event.orderId());
}
```

This snippet illustrates the idea only and needs concrete record types and metadata. In the complete example in section 7, every value is supplied explicitly with no placeholders.

If you want to publish multiple derived events, a synchronous `@EventListener` also supports returning **an array or Collection**; Spring publishes each element in turn:

```java
@EventListener
public List<Object> deriveActions(OrderAccepted event) {
    InventoryReservationRequested inventory = /* created from event */;
    ConfirmationEmailRequested email = /* created from event */;
    return List.of(inventory, email);
}
```

This is a design-sketch snippet, not standalone code. It is **Spring publishing each returned value** that triggers the listeners subscribed to those two event types.

### When Should You Use return?

This is a concise solution when:

- The listener is **synchronous** in the active configuration.
- The derived events are direct, simple outcomes of the input event.
- Complex coordination for errors/retries, transactions, or conditional multi-point publishing is not needed.
- Readers accept that follow-up events are published by `@EventListener`'s adapter without an explicit `publishEvent(...)` call visible in the method.

When workflows are long or publication sites need explicit control, an **explicit** `ApplicationEventPublisher.publishEvent(...)` call is usually easier to manage and observe.

## 6. With @Async: Do Not Use Return Values to Emit Derived Events

Spring has an officially documented limitation: **asynchronous listeners cannot publish follow-up events by returning a value**.

Recommended pattern:

```java
@Async("workflowExecutor")
@EventListener
public void onAccepted(OrderAccepted original) {
    InventoryReservationRequested derived = deriveRequest(original);
    publisher.publishEvent(derived);
}
```

This is an integration snippet; it requires injecting `ApplicationEventPublisher publisher`, declaring `deriveRequest(...)`, enabling `@EnableAsync`, and defining an executor bean named `workflowExecutor`. The listener method returns `void`; the new event comes from the **explicit publish call**, not from a return value.

**Do not assume** `@Async public InventoryReservationRequested onAccepted(...)` will run like a synchronous listener with Spring auto-publishing the result. In proxy-based `@Async` execution, such a business return type also violates the supported `void`/`Future` return contract.

With an async listener, derived events may be published **after** `publishEvent(original)` has already returned. Completion order then depends on the executor and listeners rather than the simple recursive order of a synchronous chain.

## 7. Runnable Java 17 + Spring 6.2 Example: Root Emits Two Derived Events

The console program below uses:

- Three `record`s as immutable payloads: `OrderAccepted` (root), `InventoryReservationRequested`, and `ConfirmationEmailRequested` (derived).
- An `EventMetadata` record containing `eventId`, `correlationId`, `causationId`, and `occurredAt`.
- A listener for `OrderAccepted` that **returns `List<Object>`** containing two derived events.
- Two other listeners receiving each derived event type to record traces.
- `AnnotationConfigApplicationContext` with the default **synchronous** event multicaster.
- Hardcoded IDs **solely so verification output is easy to read**; production must allocate and persist metadata under real policies.

### 7.1. Project Structure

```text
event-lineage-demo/
├── pom.xml
└── src/main/java/example/EventLineageDemo.java
```

### 7.2. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>event-lineage-demo</artifactId>
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
                    <mainClass>example.EventLineageDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 7.3. File src/main/java/example/EventLineageDemo.java

```java
package example;

import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class EventLineageDemo {

    // A null "causationId" is accepted for the root in this demo.
    public record EventMetadata(
            String eventId,
            String correlationId,
            String causationId,
            Instant occurredAt) {

        public EventMetadata {
            Objects.requireNonNull(eventId, "eventId");
            Objects.requireNonNull(correlationId, "correlationId");
            Objects.requireNonNull(occurredAt, "occurredAt");
            if (eventId.isBlank() || correlationId.isBlank()) {
                throw new IllegalArgumentException(
                        "Event identifiers cannot be blank");
            }
        }
    }

    // A fact: the order was accepted.
    public record OrderAccepted(
            EventMetadata metadata,
            String orderId) {}

    // Two requests generated from handling OrderAccepted.
    public record InventoryReservationRequested(
            EventMetadata metadata,
            String orderId) {}

    public record ConfirmationEmailRequested(
            EventMetadata metadata,
            String orderId) {}

    public static final class Trace {
        private final List<String> lines = new ArrayList<>();

        public void add(String line) {
            lines.add(line);
        }

        public int size() {
            return lines.size();
        }

        public void printAll() {
            lines.forEach(System.out::println);
        }
    }

    public static class FlowListeners {
        private final Trace trace;

        public FlowListeners(Trace trace) {
            this.trace = trace;
        }

        @EventListener
        public List<Object> deriveFromRoot(OrderAccepted root) {
            EventMetadata parent = root.metadata();

            trace.add("root OrderAccepted"
                    + " id=" + parent.eventId()
                    + " corr=" + parent.correlationId()
                    + " cause=-");

            EventMetadata inventoryMeta = new EventMetadata(
                    "evt-101",
                    parent.correlationId(),
                    parent.eventId(),
                    Instant.now());

            EventMetadata emailMeta = new EventMetadata(
                    "evt-102",
                    parent.correlationId(),
                    parent.eventId(),
                    Instant.now());

            return List.of(
                    new InventoryReservationRequested(
                            inventoryMeta, root.orderId()),
                    new ConfirmationEmailRequested(
                            emailMeta, root.orderId())
            );
        }

        @EventListener
        public void onInventory(InventoryReservationRequested event) {
            EventMetadata meta = event.metadata();
            trace.add("derived InventoryReservationRequested"
                    + " id=" + meta.eventId()
                    + " corr=" + meta.correlationId()
                    + " cause=" + meta.causationId());
        }

        @EventListener
        public void onEmail(ConfirmationEmailRequested event) {
            EventMetadata meta = event.metadata();
            trace.add("derived ConfirmationEmailRequested"
                    + " id=" + meta.eventId()
                    + " corr=" + meta.correlationId()
                    + " cause=" + meta.causationId());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Trace trace() {
            return new Trace();
        }

        @Bean
        public FlowListeners flowListeners(Trace trace) {
            return new FlowListeners(trace);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            OrderAccepted root = new OrderAccepted(
                    new EventMetadata(
                            "evt-100",
                            "flow-7",
                            null,
                            Instant.parse("2026-11-01T08:00:00Z")),
                    "ORD-42");

            context.publishEvent(root);

            Trace trace = context.getBean(Trace.class);
            trace.printAll();
            System.out.println("Total observations: " + trace.size());
        }
    }
}
```

### 7.4. Running the Program

Using JDK 17+ and Maven from the directory containing `pom.xml`:

```bash
mvn -q compile exec:java
```

**Four lines printed by application code** under the default synchronous multicaster:

```text
root OrderAccepted id=evt-100 corr=flow-7 cause=-
derived InventoryReservationRequested id=evt-101 corr=flow-7 cause=evt-100
derived ConfirmationEmailRequested id=evt-102 corr=flow-7 cause=evt-100
Total observations: 3
```

**Why is this order reasonable?**

1. `context.publishEvent(root)` publishes the `OrderAccepted` record.
2. Spring calls `deriveFromRoot`, which matches the payload type; it logs the root line and returns `List.of(inventory, email)`.
3. Spring's `@EventListener` adapter publishes **each element of the returned list in turn**.
4. When the inventory event is published, `onInventory` records the second line; when the email event is published, `onEmail` records the third line.
5. `context.publishEvent(root)` returns after processing the synchronous chain. `main` prints the full trace and line count.

`Trace` uses `ArrayList` because the example **does not enable asynchronous processing**. With a custom multicaster or `@Async`, a thread-safe structure and completion-await mechanism are required; rigid callback order expectations must not be kept then.

**Semantic distinction:** `InventoryReservationRequested` is **a request to reserve stock**, not proof that stock was reserved. `ConfirmationEmailRequested` is **a request to send email**, not proof that the email was sent. The application must perform the task and emit `InventoryReserved` / `ConfirmationEmailSent` only when a reliable outcome is obtained.

**Demo limitations:** the IDs `evt-101` and `evt-102` are hardcoded for clear explanation and reproducible output. Across multiple orders, a real system must generate/look up unique identifiers tied to durable data and replay policies; never reuse constants across orders. The demo code writes to no database and sends no real HTTP/email requests.

## 8. Creating Derived Events Explicitly with ApplicationEventPublisher

Returning values is optional. A listener can inject `ApplicationEventPublisher` and publish a new event directly:

```java
@Component
public class DerivationHandler {
    private final ApplicationEventPublisher publisher;

    public DerivationHandler(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @EventListener
    public void onAccepted(OrderAccepted original) {
        EventMetadata parent = original.metadata();
        EventMetadata childMeta = new EventMetadata(
                UUID.randomUUID().toString(),
                parent.correlationId(),
                parent.eventId(),
                Instant.now());

        publisher.publishEvent(
                new InventoryReservationRequested(
                        childMeta, original.orderId()));
    }
}
```

This is an **integration snippet**, not a standalone runnable program: it requires importing `@Component`, `ApplicationEventPublisher`, `@EventListener`, `UUID`, and `Instant`, and using the records defined in section 7. In production, generating a new UUID when **genuinely creating a derived event** makes sense, but **do not generate a different UUID when replaying the same occurrence** if that re-emission must be recognized as a duplicate.

The advantages of explicit publishing are clear publication points in code, easy conditional publishing based on processing outcomes, and controlled logging and error handling. It is also the required approach when an asynchronous listener needs to emit a follow-up event.

### Multi-Branch Emission Pattern

When a root event can lead to multiple events, they do not all have to come from a single listener. You can register two independent listeners for `OrderAccepted`:

- One inventory-related listener creates `InventoryReservationRequested`.
- One notification-related listener creates `ConfirmationEmailRequested`.

Splitting helps separate features, provided you understand differences in **ordering**, **transactions**, and **error handling**. With a synchronous multicaster, if the first listener throws an uncaught exception, distribution can stop before other listeners run. With an asynchronous multicaster, branch completion order is even less guaranteed.

If the requirement is “only send the email after stock is reserved”, do not emit two sibling events hoping one listener finishes first. Model the causality explicitly:

```text
OrderAccepted
    -> InventoryReservationRequested
        -> InventoryReserved
            -> ConfirmationEmailRequested
```

In this chain, `ConfirmationEmailRequested.causationId` should point to `InventoryReserved.eventId`, because the email is requested **after inventory confirms reservation succeeded**.

## 9. Distinguishing “Derived Events” from Commands and Side Reactions

The term “event” is sometimes applied to every message in an application. Still, two message styles have different semantics:

- **Fact/domain event:** “What happened?” Examples: `OrderAccepted`, `InventoryReserved`, `PaymentCaptured`.
- **Command/request:** “Please do something.” Examples: `ReserveInventory`, `SendConfirmationEmail`, or payloads named `InventoryReservationRequested`.

Spring Application Events can deliver **both kinds of application-defined payloads**. The framework does not enforce domain events vs. commands. In system design, however, naming accurately prevents bugs:

| Payload | Actual meaning | Do not infer |
| --- | --- | --- |
| `OrderAccepted` | Order has been accepted | Payment has completed |
| `InventoryReservationRequested` | Stock reservation was requested | Stock is definitely reserved |
| `InventoryReserved` | Warehouse confirmed reservation succeeded | Email has been sent |
| `ConfirmationEmailRequested` | Sending email was requested | Provider accepted the email |
| `ConfirmationEmailSent` | One send succeeded under defined contract | Recipient opened or read the email |

For derived events, **choose names matching the step actually reached**. If you only scheduled a task, naming it “sent/completed” misleads logs, tests, and business reports.

### Should a Derived Event Carry the Entire Root Payload?

Usually not. The new event should carry **the data needed for its own responsibility**, plus identifiers for tracing:

```java
public record ConfirmationEmailRequested(
        EventMetadata metadata,
        String orderId,
        String templateCode
) {}
```

This is an illustrative schema variant and does not alter the program in section 7. There is no need to copy the entire order entity, card details, HTTP request objects, or live transactional resources. An event should be an immutable snapshot, safe for delayed handling or another thread.

## 10. Replay: Distinguishing Replaying Root Events vs. Regenerating Derived Events

**Replay** is when an application re-reads and reprocesses an existing event (typically from an event store, outbox, broker, or durable source). **Spring `ApplicationEventPublisher` itself does not provide an event store or durable replay.** Storage, replay scoping, checkpointing, and delivery guarantees must be solved by the system architecture.

Two strategies must be distinguished:

### 10.1. Replaying All Stored Events to Rebuild Read Models

Suppose history contains:

```text
evt-100 OrderAccepted
evt-101 InventoryReservationRequested
evt-103 InventoryReserved
evt-104 ConfirmationEmailRequested
```

When rebuilding a read model, the application can **replay the stored records themselves** to the read-model projector. If a listener on `OrderAccepted` simultaneously generates a fresh `InventoryReservationRequested`, two paths end up producing derived actions: the stored `evt-101` record and the newly regenerated one. That easily duplicates events and side effects.

**Appropriate policy:** a replay for projections normally **does not re-trigger external side effects** and does not emit new events by default; projectors consume historical records as existing inputs.

### 10.2. Replaying Root Events to Re-run Workflows

Sometimes a business step genuinely needs to **re-execute** after an earlier failure—for example, an email send request was never executed. Then you must determine:

- Are we reprocessing **the same occurrence** or creating a new business intent?
- Was the derived event already persisted?
- Which idempotency key detects that the task already ran?
- Does the external party support idempotency keys?
- When retrying, are `correlationId` and `causationId` preserved so the trace chain stays intact?
- Should a failure/compensating event be emitted instead of rerunning the entire chain?

A safe replay is never simply:

```java
for (StoredEvent event : history) {
    publisher.publishEvent(event.payload());
}
```

This is pseudocode for reading history; it does not address duplicates, transactions, or external side effects. You must choose which consumers participate in replay and how they behave when seeing historical events.

### Comparison Table

| Purpose | Input | Should new derived events be emitted? | External side effects? |
| --- | --- | --- | --- |
| Rebuild read model | Stored historical events | Usually **no** | No |
| Retry a failed handler | Same event occurrence | Only if the target step is incomplete and idempotency exists | Conditional, must prevent duplicates |
| Start a new business workflow | New command/request | Yes, with new event ID | Per business rules |
| Reprocess to test logic in a test environment | Historical events | Can simulate without real commits/publishes | None or sandbox |
| Resync a consumer after downtime | Events retained in broker/outbox | Do not duplicate already-stored events | Only through idempotent handlers |

## 11. Avoiding Loops, Unbounded Fan-Out, and Overly Deep Chains

If a listener receives `A` and publishes `B`, while a listener receiving `B` publishes `A` with no stopping condition, a loop occurs:

```text
EventA -> EventB -> EventA -> EventB -> ...
```

Under the synchronous multicaster, publishing inside a listener creates nested calls on the same thread and increases stack depth. Switching to async does not make the problem vanish: events can trigger unbounded fan-out, grow queues, and exhaust resources.

Countermeasures:

1. **Define an explicit state machine/workflow:** transition state only along valid steps.
2. **Distinguish facts from requests:** do not emit repeated requests once a completed outcome exists.
3. **Idempotency keys** per handler and critical side effect.
4. **Monitor the causation graph** to detect cycles and abnormal event creation counts.
5. **Limit retries/fan-out/depth** per business requirements.
6. **Extract orchestration** when many dependent branches exist rather than letting listeners mutually trigger each other endlessly.
7. **Monitor queues and errors** when running asynchronously or over a broker.

A stable `correlationId` helps group logs, yet does not stop loops by itself; handlers must use state and idempotency properly.

## 12. Transactions: Root and Derived Events Can Run Before Commit

With the default synchronous multicaster, listeners run on the thread calling `publishEvent`. If the publisher is inside a transaction, synchronous listeners normally see that transaction context.

Illustrative integration example:

```java
@Transactional
public void acceptOrder(String orderId) {
    // repository.save(...) updates state.
    publisher.publishEvent(
            new OrderAccepted(metadata, orderId));
}
```

This snippet requires a transaction manager, repository, `publisher`, and `metadata`. When the root event is published **before commit**, a synchronous listener can immediately construct and emit a derived event **also before commit**. If the transaction later rolls back, an email or external HTTP request executed by a listener may already have happened, causing business inconsistency.

### If Derived Events Should Only Be Published After Commit

You can use `@TransactionalEventListener` on the root-handling step:

```java
@Component
public class CommittedOrderListener {
    private final ApplicationEventPublisher publisher;

    public CommittedOrderListener(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onCommitted(OrderAccepted original) {
        EventMetadata child = createChildMetadata(original);
        publisher.publishEvent(
                new InventoryReservationRequested(
                        child, original.orderId()));
    }
}
```

This is an integration snippet requiring `createChildMetadata(...)` and imports for `@Component`, `TransactionalEventListener`, and `TransactionPhase`. It is not the standalone program from section 7.

**Important:**

- `@TransactionalEventListener` defaults to `AFTER_COMMIT`; `fallbackExecution` defaults to `false`, so without a source transaction the listener normally does not run.
- The callback fires after commit, yet **does not automatically store the derived event in an event store**; a crash can lose work before publishing or before the listener finishes.
- After commit, some old transaction resources may still be bound to the thread. If the callback needs new database writes, start a proper new transaction (for instance `REQUIRES_NEW` via a Spring proxy or `TransactionTemplate`).
- An event published on another thread usually carries no original transaction. A `@TransactionalEventListener` for the derived event may not run if there is no active transaction and `fallbackExecution = false`.
- For workflows that **cannot afford to lose events**, write an outbox record **inside the initial business transaction**, then have a worker read, retry, and publish, rather than relying solely on an in-RAM post-commit callback.

**Do not misunderstand:** `@TransactionalEventListener` controls **timing**; it does not automatically solve duplicates, idempotency, durability, or cross-process ordering.

## 13. Event Deduplication and Per-Handler Side Effects

When root event `evt-100` is replayed, a listener may generate derived events again; or when a derived event is redelivered from a broker, a consumer may run side effects twice. Protect at multiple layers:

### 13.1. Uniqueness per Consumer and Event

A typical marker table:

```sql
CREATE TABLE processed_events (
    consumer_name VARCHAR(80) NOT NULL,
    event_id      VARCHAR(80) NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);
```

`(consumer_name, event_id)` lets two independent handlers process the same event while preventing **any single handler** from processing that occurrence twice. A database unique constraint matters more than doing `SELECT` first and `INSERT` second, since two workers can both see “not present yet”.

### 13.2. Business/Causality Uniqueness

For `ConfirmationEmailRequested`, for example, you might need the constraint “one confirmation email per `orderId` and template version” or “one send request per causation event”. Then even a fresh `eventId` cannot bypass business protection.

The key should reflect **the effect being deduplicated**, not arbitrarily using the entire payload or `correlationId`. `correlationId` is too broad: a workflow contains many legitimate events sharing one correlation.

### 13.3. External Side Effects

If you insert the marker first, then call the email provider, and the process dies before sending, a retry may be blocked even though the email never went out. If you send the email before inserting the marker, a crash or timeout can make a retry send a duplicate.

For reliable delivery, use a **transactional outbox** to record work in the same transaction as data changes, worker claiming/retries, and partner-side idempotency keys where available. Never claim “exactly once end-to-end” merely because an event was published once inside a Spring context.

## 14. Root Events and Derived Events in Tracing

To understand an execution chain, logs should display at least:

```text
eventType
eventId
correlationId
causationId
aggregateId / orderId
occurredAt
handlerName
processingAttempt
processingStatus
```

Example:

```text
type=OrderAccepted id=evt-100 corr=flow-7 cause=- order=ORD-42
type=InventoryReservationRequested id=evt-101 corr=flow-7 cause=evt-100 order=ORD-42
type=ConfirmationEmailRequested id=evt-102 corr=flow-7 cause=evt-100 order=ORD-42
```

From this you can:

- Use `correlationId` to group events belonging to one workflow.
- Use `causationId` to build **parent → child edges** on a graph.
- Use `eventId` to identify occurrences and replays/duplicates.
- Use `orderId` to relate to the business aggregate.
- Use processing status and attempt count to tell whether the listener succeeded or was only invoked.

Distinguish OpenTelemetry/Micrometer `traceId` from business `correlationId`. The two IDs can be related, yet **do not necessarily share the same value or lifecycle**. A long-running workflow can span multiple distributed traces while keeping the same correlation ID; conversely, one HTTP trace can touch multiple distinct events.

With `@Async` listeners, `ThreadLocal`/MDC and transaction context do not propagate to worker threads by default. The safe approach is carrying long-lived metadata in **immutable payloads**, while designing deliberate context propagation for technical tracing.

## 15. Designing Immutable Payloads for Event Chains

Java 17 `record`s make event descriptions concise and transparent:

```java
public record EventMetadata(
        String eventId,
        String correlationId,
        String causationId,
        Instant occurredAt) {}

public record OrderAccepted(
        EventMetadata metadata,
        String orderId) {}

public record InventoryReservationRequested(
        EventMetadata metadata,
        String orderId) {}
```

These are data-type examples; the program in section 7 includes full metadata validation. `String` and `Instant` fields are immutable, and records expose no setters for components.

Still, **records only guarantee shallow immutability**. If an event holds a `List<OrderLine>` and `OrderLine` is mutable, you need a snapshot of both the list and nested elements. `List.copyOf(...)` only freezes list structure; it does not deep-copy mutable elements.

For derived events, never pass a mutable JPA entity directly from the root event assuming it acts as a snapshot. Map to IDs or immutable values instead; records clarify contracts, yet do not solve lazy loading, concurrency, or durability by themselves.

### Timestamps on Derived Events

`occurredAt` on the root event records when the original fact happened. `occurredAt` on a derived event should reflect **when the derived event was actually created**, not copy the root timestamp just to match.

Some systems also store `triggeredAt` or `originalOccurredAt` to compare processing latency. During replay, decide whether to preserve the occurrence's original timestamp and record `replayedAt` in processing metadata rather than silently overwriting `occurredAt` on historical records.

## 16. Testing Root–Derived Relationships

A good test asserts not just event counts, but **correct causal relationships**:

| Check | Expectation |
| --- | --- |
| Root published once | Root listener receives the exact `OrderAccepted` |
| Two derived events emitted | Both `InventoryReservationRequested` and `ConfirmationEmailRequested` exist |
| Each derived event has its own `eventId` | `evt-101` differs from `evt-102` and from `evt-100` |
| Correlation preserved | All three have `correlationId=flow-7` |
| Causation accurate | Both direct derived events have `causationId=evt-100` |
| No infinite recursion | Derived listeners do not recklessly re-emit root |
| Async handler | Wait via latch/future; do not guess log ordering |
| Transaction rollback | No side effects violating commit semantics |
| Replay root event | No duplicate side effects when consumer already processed it |
| Replay history | Do not duplicate stored derived events when rebuilding projections |

### 16.1. Testing Ordering in Synchronous Setups

The Java example in section 7 uses a single listener to receive root and return a two-element `List.of(...)`. Thus the trace recorded by the app has a deterministic order under the **default synchronous multicaster**. Do not keep that rigid expectation if listeners move to async.

When testing async, use `CountDownLatch`, `CompletableFuture`, or synchronization tools with timeouts, and verify **the collected set of events** and metadata rather than asserting completion order.

### 16.2. Testing Real Idempotency

To prove retries do not duplicate emails, do not merely mock `publishEvent` and assert it ran once. Test DB markers with unique constraints, outbox state, and two workers/connections racing on the same key. An immutable event record alone does not protect against duplicates.

### 16.3. Testing When a Listener Fails

With the default synchronous multicaster, an unhandled listener exception can propagate to the publisher and halt the chain before other branches finish. With async, exceptions in `void` listeners can be reported to an async error handler without returning to the caller; other branches may still run.

Inject failures at each step to verify exactly which events were published, which steps caused side effects, and where retries can resume. Never assume “`publishEvent` returned” means every external task succeeded.

## 17. Common Mistakes

1. **Calling every handler-emitted event a root event.** When tracing is needed, record the direct link to the parent event.
2. **Using `correlationId` as the unique event key.** A workflow holds many distinct events sharing a correlation.
3. **Reusing the same `eventId` for a new derived event.** Mixes occurrences and breaks idempotency.
4. **Minting a new `eventId` when replaying the same occurrence.** Consumers cannot detect duplicates by `eventId` alone.
5. **Using `ApplicationEvent.getSource()` instead of `causationId`.** The framework source is not a parent-event contract.
6. **Confusing requests with completed outcomes.** `InventoryReservationRequested` is not `InventoryReserved`.
7. **Assuming root and derived events always run on one thread.** With `@Async` or a custom multicaster, threads can differ.
8. **Using the return value of `@Async @EventListener` to emit derived events.** Spring does not support it; publish explicitly.
9. **Believing `@Order` guarantees async tasks complete in order.** It only relates to dispatch order under matching conditions, not completion.
10. **Replaying all history while simultaneously regenerating stored derived events.** Easily duplicates processing.
11. **Leaving loops/fan-out unbounded.** Listeners can recurse infinitely or flood queues.
12. **Triggering side effects before commit assuming rollback will undo them.** HTTP/email does not roll back with the database.
13. **Treating Spring in-process events as a durable event store.** `publishEvent` neither persists nor replays.
14. **Putting mutable JPA entities inside payloads.** Data can mutate mid-flight and hit lazy-loading errors.
15. **Missing idempotency on downstream consumers.** Even if the root event is never emitted twice, a derived event can be retried by an outbox/broker.
16. **Keeping the root timestamp on all derived events.** Distorts step creation times and latency metrics.

## 18. Event System Design Checklist

- [ ] Defined **root** within the workflow scope being observed.
- [ ] Every occurrence has a stable `eventId`; new derived events get new IDs.
- [ ] Derived events preserve `correlationId` and point `causationId` to the **immediate parent event**.
- [ ] Event names distinguish facts that occurred from newly created requests.
- [ ] Payloads are immutable snapshots without uncontrolled resources or mutable entities.
- [ ] For synchronous `@EventListener`, you know when to return an event or `Collection`.
- [ ] For `@Async` listeners, `ApplicationEventPublisher.publishEvent(...)` is called explicitly.
- [ ] Transaction timing is decided: before commit, after commit, or outbox.
- [ ] Projection replays do not automatically re-emit critical side effects.
- [ ] Idempotency strategies exist for each handler and external system.
- [ ] Monitoring covers `eventId` / `causationId` / `correlationId` links, retries, and outcomes.
- [ ] Tests cover duplicates, rollbacks, replays, multithreading, and multi-branch chains.

**Key takeaway:** a root event marks the start of a chain; a derived event is a **new event whose direct cause** is an earlier event. Use `eventId` to identify each occurrence, `correlationId` to group workflows, and `causationId` to reconstruct parent–child links. Spring helps publish and dispatch events, while managing causality, replay, durability, and idempotency remains the application's design responsibility.

## References

- [Spring Framework — ApplicationContext Events and returning events from @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 — @EventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/event/EventListener.html)
- [Spring Framework 6.2 — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.0/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
