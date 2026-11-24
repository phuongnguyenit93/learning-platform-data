# Creation Timestamp and Correlation ID in Event Payload Design

## 1. Purpose of Metadata in Domain Events

A domain event should not only state **what happened**, but also tell consumers **when the event occurred** and **which business processing flow it belongs to**.

For example, an order is placed and then packing begins:

~~~text
HTTP request / command  (correlationId = A)
           |
           v
      OrderPlaced
        eventId = E1
        correlationId = A
        causationId = commandId
        occurredAt = T1
           |
           v
      PackingStarted
        eventId = E2
        correlationId = A
        causationId = E1
        occurredAt = T2
~~~

The two events are distinct because their `eventId`s differ, yet they belong to **the same business flow** because they share `correlationId`. `causationId` indicates which event or command directly triggered the next occurrence. `occurredAt` states the time of each business fact, not when the consumer received the event.

This metadata is especially valuable for auditing, root-cause analysis, distributed workflows, replay, and external system integration. However, **explicit semantics** must be defined: having only a field named `timestamp` or `id` does not tell receivers how to interpret it.

## 2. Distinguishing `occurredAt`, `createdAt`, `publishedAt`, `committedAt`, and `processedAt`

The following timestamps may coincide in small examples, yet **must not be treated as synonymous**.

| Field / Milestone | Recommended Convention | Who Knows and Records It? |
| --- | --- | --- |
| `occurredAt` | Time when the **business fact occurred**, per domain definition | Domain/application service when confirming the state transition |
| `createdAt` or `envelopedAt` | Time when the event object or envelope metadata was constructed | Event/envelope creation code |
| `publishedAt` | Time when the event was published to a specific bus/broker or listener system | Publisher/transport adapter |
| `committedAt` | Time when the transaction containing the business data committed, if reliably observable | Database/transaction layer; not included in payloads by default |
| `receivedAt` | Time when the consumer received the event | Consumer |
| `processedAt` | Time when the consumer finished processing per consumer convention | Consumer |

A scenario might look like this (illustrating relative order only):

~~~text
10:00:00.100  Business accepts order          -> occurredAt
10:00:00.102  Create payload/event envelope   -> createdAt
10:00:00.150  DB transaction commits          -> committedAt
10:00:00.350  Publisher sends to broker       -> publishedAt
10:00:01.000  Consumer reads message          -> receivedAt
10:00:01.250  Consumer finishes processing    -> processedAt
~~~

When using an outbox, the event can be created **inside transaction T1** and saved to the outbox alongside the order data. The worker sends to the broker **after T1 commits**. Thus `occurredAt` of the fact stays unchanged across retries; never overwrite it with `Instant.now()` on each resend.

**Note on truthfulness:** if the transaction rolls back, do not broadcast an `OrderPlaced` externally as if the order had committed. You can create a *candidate/pending domain event* when the domain mutates inside T1, yet only process it as a committed fact under your chosen consistency strategy (e.g., an `AFTER_COMMIT` listener or an outbox).

### Is Spring's `ApplicationEvent.getTimestamp()` the Domain's `occurredAt`?

**Do not automatically equate them.** When instantiating a subclass of `org.springframework.context.ApplicationEvent`, the constructor usually sets the timestamp from `System.currentTimeMillis()`; an overload taking a `Clock` also exists. Therefore `getTimestamp()` reflects when the **`ApplicationEvent` object was constructed according to the clock used**, without automatically knowing when the database committed or when the domain fact occurred.

When the application publishes a **plain payload object** via `ApplicationEventPublisher.publishEvent(Object)`, Spring may wrap it in a `PayloadApplicationEvent`. The wrapper's timestamp metadata also belongs to the Spring event object created, rather than replacing a domain-meaningful `occurredAt` field inside the payload.

Accordingly, if you need a timestamp for auditing or integration, declare **`Instant occurredAt` in the domain event or envelope with a clear contract**. `ApplicationEvent.getTimestamp()` remains useful for understanding the Spring event object's lifecycle, yet is no guarantee of commit time.

## 3. Choosing Time Types and Recording Rules

### Prefer `Instant` or Timestamps with Explicit Offsets

`java.time.Instant` represents a point on the UTC timeline and serializes cleanly to ISO-8601:

~~~json
{
  "type": "OrderPlaced",
  "orderId": 101,
  "occurredAt": "2026-02-03T10:15:30Z"
}
~~~

`OffsetDateTime` also works if the contract needs to preserve an offset. Avoid `LocalDateTime` to represent global instants when events cross timezones: `2026-02-03T10:15:30` does not say where that time occurred.

Notes:

- Specify **units** when using epochs: epoch milliseconds differ from epoch seconds and microseconds. In Java, `Instant.toString()`/ISO-8601 reduces ambiguity.
- Inject a `Clock` so tests can freeze time; avoid calling `Instant.now()` directly across many places, which makes tests hard to reproduce.
- When one workflow emits two events in rapid succession, timestamps can be **identical** due to clock resolution. Never use a timestamp alone as a unique key.
- Clocks across machines can suffer **clock skew**, so never infer absolute causal order from `occurredAt` across different hosts. If per-aggregate ordering is needed, consider an authoritative version/sequence; to know which event caused which, use `causationId`.
- Assign `occurredAt` only when the fact is genuinely confirmed per domain semantics. Calling `new Event(...)` does not by itself make a business transition succeed.

### Should Timestamps Live in the Payload or Envelope?

Both can make sense if the contract is consistent:

~~~text
Envelope:
    eventId
    eventType
    correlationId
    causationId
    publishedAt / schemaVersion (if needed)

Payload:
    orderId
    customerId
    occurredAt
    totalAmount
~~~

If a contract agrees that `occurredAt` belongs in the envelope instead of the payload, consumers can still apply the right semantics. What matters is **avoiding two same-named fields expressing different moments** or letting transport layers silently overwrite the business occurrence time.

## 4. What Is a Correlation ID?

`correlationId` is an identifier that **groups operations belonging to one processing flow**: from the initial request through services, commands, events, and downstream integration steps.

Checkout example:

~~~text
correlationId = C-123
    |
    +-- CheckoutRequested  (commandId = CMD-1)
    +-- OrderPlaced        (eventId = EVT-1, causationId = CMD-1)
    +-- PaymentCaptured    (eventId = EVT-2, causationId = EVT-1)
    +-- ShipmentRequested  (commandId = CMD-2, causationId = EVT-2)
    +-- ShipmentDispatched (eventId = EVT-3, causationId = CMD-2)
~~~

Each occurrence has its own ID; the **correlation ID remains stable** so the entire journey can be investigated. One correlation ID can attach to many events, requests/messages, or services. It is **not the primary key of individual events**.

Common ways to manage correlation:

1. **Incoming HTTP request:** the boundary can accept a trusted existing correlation ID or generate a new one if absent; validate header format, length, and trust policy.
2. **Initial command:** attach the correlation ID to the command and pass it down to application/domain services.
3. **Domain events:** copy the correlation ID from the business/command context **rather than generating a new ID per event**.
4. **Handlers emitting follow-up commands/events:** keep the original correlation ID, generate a fresh `eventId` for each new occurrence, and set `causationId` to the object that directly triggered it.
5. **Crossing queues or services:** put the correlation ID into message metadata/payload per contract; do not expect `ThreadLocal` or MDC to propagate across processes automatically.

UUIDs are a common choice for these IDs; some systems use ULIDs, prefixed strings, or other identifiers. **Spring imposes no requirement that correlation IDs must be UUIDs.** What is mandatory is that components agree on type and semantics.

## 5. Distinguishing `eventId`, `correlationId`, `causationId`, `traceId`, and `aggregateId`

| Field | Scope of Identification | Key Rule |
| --- | --- | --- |
| `eventId` | **One specific occurrence/event** | Generate new for a new fact; when retrying **the same event**, keep the same ID |
| `correlationId` | **One workflow or related chain** | Keep stable across all steps to be linked |
| `causationId` | **Message/command/event that directly caused this step** | Can point to `commandId` or parent `eventId`; may be omitted/null if there is no direct source |
| `traceId` | **A distributed trace in the observability infrastructure** | Managed by tracing systems like OpenTelemetry; not by default identical to business correlation ID |
| `aggregateId`, `orderId` | **Affected business entity** | Different events on one order can share `orderId` yet belong to different workflows |

An easy rule of thumb:

~~~text
eventId       : "Which specific event is this?"
correlationId : "Which business journey does it belong to?"
causationId   : "What directly led to this event?"
traceId       : "Which distributed execution was traced by the system?"
orderId       : "Which order is being referred to?"
~~~

**Do not use `correlationId` as a per-event deduplication key.** Because multiple valid events share one correlation ID, a consumer deduplicating on that key would accidentally drop events. For retries/at-least-once delivery, normally use `eventId` scoped per consumer, or an appropriate business idempotency key.

`traceId` can change when a workflow spans multiple retries or lasts hours/days, while the business `correlationId` stays constant. Both can be recorded when needed without forcing them to be the same value.

## 6. Semantically Clear Java 17+ Payload Pattern

An event record can hold the fields:

~~~java
import java.time.Instant;
import java.util.UUID;

// Illustrative data type snippet, not a standalone runnable file.
public record OrderPlaced(
    UUID eventId,
    UUID correlationId,
    UUID causationId,
    long orderId,
    Instant occurredAt
) {}
~~~

Meaning:

- `eventId`: identity of **this specific `OrderPlaced`**.
- `correlationId`: the same value passed in from the command/request that created the order.
- `causationId`: ID of the `PlaceOrder` command, if the workflow assigns command IDs.
- `orderId`: aggregate identity; one order can have many distinct events.
- `occurredAt`: when the order placement was accepted by the domain.

**Do not generate one `UUID.randomUUID()` and assign it to every field.** They may share the UUID type, yet each field carries distinct meaning. If there is no direct causal parent, a causation field can be `null` per contract, or use `Optional`/an envelope instead of fabricating a fake ID.

In production, consider schema versions, monetary values, tenant identifier scopes, event types, and data security. Avoid passing mutable/lazy-loading JPA entities as payloads so historical facts cannot mutate after the fact.

## 7. Java 17+ Spring Example: Two Events, One Correlation ID, Two Event IDs

The standalone demo below uses **Spring Framework 6.2.18** and the default synchronous event publisher. A `PlaceOrder` command produces `OrderPlaced`; a listener starts packing **in memory** and then publishes `PackingStarted`.

The goal is to observe the metadata:

- The two events have **different** `eventId`s.
- Both events share the same `correlationId`.
- `OrderPlaced.causationId` is `commandId`; `PackingStarted.causationId` is `OrderPlaced.eventId`.
- Both events have the exact same `occurredAt` under a **fixed test clock**, proving order cannot be inferred from timestamps.
- A duplicate order command is rejected without emitting a third event.

This is a **demo with no database, no transactions, and no broker**. Storing data in a `HashSet` is unsuitable for concurrent processing or production durability.

### File `settings.gradle`

~~~groovy
rootProject.name = 'event-metadata-demo'
~~~

### File `build.gradle`

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

application {
    mainClass = 'demo.EventMetadataDemo'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}
~~~

### File `src/main/java/demo/EventMetadataDemo.java`

~~~java
package demo;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.HashSet;
import java.util.Objects;
import java.util.Set;
import java.util.UUID;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class EventMetadataDemo {

    // Fixed IDs only so stdout and tests can compare deterministically.
    private static final UUID COMMAND_ID =
        UUID.fromString("11111111-1111-1111-1111-111111111111");
    private static final UUID CORRELATION_ID =
        UUID.fromString("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa");
    private static final UUID ORDER_EVENT_ID =
        UUID.fromString("22222222-2222-2222-2222-222222222222");
    private static final UUID PACKING_EVENT_ID =
        UUID.fromString("33333333-3333-3333-3333-333333333333");

    // Command holding command ID and workflow correlation.
    public record PlaceOrder(
        UUID commandId,
        UUID correlationId,
        long orderId
    ) {}

    // Two business facts sharing the same metadata schema.
    public record OrderPlaced(
        UUID eventId,
        UUID correlationId,
        UUID causationId,
        long orderId,
        Instant occurredAt
    ) {}

    public record PackingStarted(
        UUID eventId,
        UUID correlationId,
        UUID causationId,
        long orderId,
        Instant occurredAt
    ) {}

    public static final class OrderService {
        private final Set<Long> orders = new HashSet<>();
        private final ApplicationEventPublisher events;
        private final Clock clock;

        OrderService(ApplicationEventPublisher events, Clock clock) {
            this.events = events;
            this.clock = clock;
        }

        public void place(PlaceOrder command) {
            Objects.requireNonNull(command);
            Objects.requireNonNull(command.commandId());
            Objects.requireNonNull(command.correlationId());

            if (command.orderId() <= 0) {
                throw new IllegalArgumentException("Invalid order");
            }
            if (!orders.add(command.orderId())) {
                throw new IllegalStateException("Duplicate order");
            }

            events.publishEvent(new OrderPlaced(
                ORDER_EVENT_ID,
                command.correlationId(),
                command.commandId(),
                command.orderId(),
                Instant.now(clock)
            ));
        }

        public int orderCount() {
            return orders.size();
        }
    }

    public static final class PackingListener {
        private final Set<Long> started = new HashSet<>();
        private final ApplicationEventPublisher events;
        private final Clock clock;

        PackingListener(ApplicationEventPublisher events, Clock clock) {
            this.events = events;
            this.clock = clock;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            System.out.println(
                "OrderPlaced: order=" + event.orderId()
                    + ", at=" + event.occurredAt()
            );
            System.out.println(
                "  eventId=" + event.eventId()
                    + ", correlationId=" + event.correlationId()
                    + ", causationId=" + event.causationId()
            );

            // In the demo: record packing-started state
            // in memory before publishing the corresponding fact.
            if (started.add(event.orderId())) {
                events.publishEvent(new PackingStarted(
                    PACKING_EVENT_ID,
                    event.correlationId(), // KEEP correlationId
                    event.eventId(),       // Link causal relationship
                    event.orderId(),
                    Instant.now(clock)
                ));
            }
        }

        @EventListener
        public void onPackingStarted(PackingStarted event) {
            System.out.println(
                "PackingStarted: order=" + event.orderId()
                    + ", at=" + event.occurredAt()
            );
            System.out.println(
                "  eventId=" + event.eventId()
                    + ", correlationId=" + event.correlationId()
                    + ", causationId=" + event.causationId()
            );
        }
    }

    @Configuration
    public static class DemoConfig {
        @Bean
        Clock clock() {
            return Clock.fixed(
                Instant.parse("2026-02-03T10:15:30Z"),
                ZoneOffset.UTC
            );
        }

        @Bean
        OrderService orderService(
                ApplicationEventPublisher events, Clock clock) {
            return new OrderService(events, clock);
        }

        @Bean
        PackingListener packingListener(
                ApplicationEventPublisher events, Clock clock) {
            return new PackingListener(events, clock);
        }
    }

    public static void main(String[] args) {
        try (var ctx = new AnnotationConfigApplicationContext(
                DemoConfig.class)) {

            var service = ctx.getBean(OrderService.class);

            service.place(new PlaceOrder(
                COMMAND_ID, CORRELATION_ID, 101L
            ));

            // Same orderId: rejected, no new event published.
            try {
                service.place(new PlaceOrder(
                    UUID.fromString(
                        "44444444-4444-4444-4444-444444444444"
                    ),
                    CORRELATION_ID,
                    101L
                ));
            } catch (IllegalStateException ignored) {
                System.out.println("duplicate rejected");
            }

            System.out.println("orders=" + service.orderCount());
        }
    }
}
~~~

Run in the project directory with JDK 17+ and Gradle or the existing Gradle Wrapper:

~~~bash
gradle run --quiet
# Linux/macOS if wrapper exists: ./gradlew run --quiet
# Windows if wrapper exists: gradlew.bat run --quiet
~~~

Lines printed by the program itself (excluding environment logging):

~~~text
OrderPlaced: order=101, at=2026-02-03T10:15:30Z
  eventId=22222222-2222-2222-2222-222222222222, correlationId=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa, causationId=11111111-1111-1111-1111-111111111111
PackingStarted: order=101, at=2026-02-03T10:15:30Z
  eventId=33333333-3333-3333-3333-333333333333, correlationId=aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa, causationId=22222222-2222-2222-2222-222222222222
duplicate rejected
orders=1
~~~

Sequence explanation:

1. `OrderService.place(...)` records the order in the `Set` and publishes `OrderPlaced`. The listener receives the payload via `@EventListener`.
2. `PackingListener` prints the metadata and then records packing-started in a separate `Set`. If this is the first time, it publishes a **new `PackingStarted`**.
3. `PackingStarted` has a **new event ID**, preserves `OrderPlaced`'s `correlationId`, and uses `OrderPlaced.eventId` as its `causationId`.
4. `Clock.fixed` gives both events the same timestamp `2026-02-03T10:15:30Z`. Even with equal timestamps, **the causal chain remains clear** thanks to the IDs and flow implementation.
5. The command trying to recreate order ID 101 is rejected, so no further `OrderPlaced` or `PackingStarted` is emitted. Only one order remains in memory.

The demo solution uses `ApplicationEventPublisher` and the default synchronous multicaster. In real runs with an asynchronous executor, queue, or broker, callback ordering and context propagation may differ. **Fixed UUID values are only for the demo; real systems must generate a unique ID for each new occurrence**, while keeping the same `eventId` when replaying the same event.

## 8. Publishing Events in Transactions: Timestamps and Correlation Do Not Guarantee Commit

Even with clean metadata, bugs occur if notifications go out **before the fact is committed**.

Suppose the business code is:

~~~java
// Illustrative anti-pattern; not a standalone program.
@Transactional
public void placeOrder(PlaceOrder command) {
    orderRepository.save(new Order(...));
    eventPublisher.publishEvent(new OrderPlaced(...));
    // If an error occurs afterward, T1 may roll back.
}
~~~

If the consumer runs immediately and performs side effects outside T1, it may process a fact absent from the DB after rollback. `occurredAt` or `correlationId` **do not make an event transactional**.

When side actions should run only after T1 commits successfully, one option is:

~~~java
// Illustrative snippet using matching event type and Spring beans.
@TransactionalEventListener(
    phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(OrderPlaced event) {
    // T1 has committed. Invoke post-commit handling per use case.
}
~~~

Note that `@TransactionalEventListener` by default runs only when the event is published inside an appropriate transaction. A post-commit callback **does not automatically open a new transaction** for DB writes; if writing to the DB from the listener, a separate transaction such as `REQUIRES_NEW` is usually required. For reactive transactions, use Spring's `TransactionContext` propagation mechanisms such as `TransactionalEventPublisher`.

For requirements demanding **reliable event delivery to a broker**, use a transactional outbox:

~~~text
BEGIN T1
  INSERT orders(...)
  INSERT outbox(
    event_id,
    correlation_id,
    causation_id,
    occurred_at,
    event_type,
    payload
  )
COMMIT T1

Outbox worker (later):
  read committed records
  send message
  mark as sent or retry on failure
~~~

The above is **pseudocode**, not valid SQL for a specific schema. Production systems must define their own locking/claiming, retries, duplicate-send behavior, and completion criteria. The key point is that **the outbox preserves `eventId`, `correlationId`, and `occurredAt` across retries**, while `publishedAt` (if present) may reflect each publish attempt or the first publish per contract.

Do not confuse event timestamps with commit time: commit may happen after `occurredAt`, and not every database exposes reliable commit timestamps in the same way.

## 9. Propagating Correlation ID Across HTTP, Async, and Message Brokers

A typical design:

- **Ingress (HTTP/RPC):** read correlation headers per trust policy or generate an ID; pass it explicitly into the request context/command.
- **Application service:** create domain events, copy `correlationId` into the event/envelope, and assign a new `eventId`.
- **Event handler:** reuse the received correlation ID when spawning follow-up work; use the current event as causation.
- **Broker adapter:** place the correlation ID in message headers or payloads using agreed keys/casing; on receipt, decode and pass it down to business logic.
- **Logger/tracer:** you can add the correlation ID to MDC/log fields or tracing baggage as appropriate, yet business metadata should continue to be passed explicitly rather than relying solely on logging context.

Important notes for asynchronous paths:

- `ThreadLocal`/MDC **do not automatically follow** across `@Async`, executor tasks, Reactor subscriptions, queues, or process boundaries. Configure context propagation or pass IDs via payloads/headers.
- Tracing and correlation can be linked yet have different lifetimes. For example, the initial HTTP request trace may end, while the order processing correlation spans hours.
- Never treat a client-supplied correlation ID as proof of authentication/authorization. It is linking metadata, **not an access token**. Limit length, characters, log cardinality, and sensitive data handling.
- Never stuff personal info like emails, customer names, or tokens into `correlationId` to make logs "easier to read"; use opaque IDs or controlled identifiers.
- If an event is replayed due to retries, preserve the original occurrence's `eventId`; generate a fresh `attemptId` or transport metadata if per-attempt tracking is needed without breaking deduplication.

### What If One Workflow Has Multiple Correlation IDs?

Normally pick **one correlation ID** per transaction/business flow with a clear scope. However, when workflows merge or one event fans out into multiple independent workflows, you can start a new correlation and **record a link to the source correlation** via another metadata field/contract. Do not rigidly enforce "one correlation ID for everything forever"; correlation scope should be decided by the domain and tracing goals.

## 10. Testing Timestamp and Correlation Design

A worthwhile test suite should verify:

| Test Case | What to Verify |
| --- | --- |
| Valid command | Event has `occurredAt` from `Clock`/agreed domain moment |
| Two events in one workflow | Same `correlationId`, different `eventId`s |
| Event B triggered by event A | `B.causationId == A.eventId` |
| Rejected command | No fact published claiming the command succeeded |
| Resending the same event | Preserves original `eventId`, `occurredAt`, `correlationId`, payload |
| Transaction rollback | No committed fact broadcast externally; after-commit/outbox strategy works properly |
| Listener on another thread/process | Correlation ID stays intact via payload/headers without relying solely on MDC |
| Clocks with equal/skewed timestamps | Never uses timestamp as sole deduplication key or causal proof |
| Integration across versions/schemas | Contract still parses `occurredAt` and metadata per published rules |

Common real-world mistakes:

1. **Creating a new correlation ID for every event:** logs no longer link steps in the same workflow. Fix by copying correlation from the incoming context when creating follow-up events.
2. **Setting `eventId` equal to `correlationId`:** makes distinct events indistinguishable. Design two fields with two scopes.
3. **Setting `occurredAt = Instant.now()` on the consumer:** turns receipt time into occurrence time. Consumers should record `receivedAt` separately.
4. **Changing `eventId` on every retry:** event-ID deduplication fails to recognize redeliveries of the same fact.
5. **Storing correlation only in MDC:** async/brokers lose context and consumers cannot recover it. Pass metadata in payloads/headers.
6. **Believing `ApplicationEvent.getTimestamp()` is commit time:** event constructors have no commit information. Use an explicitly defined business field.
7. **Ordering distributed events by timestamp alone:** clock skew and varying receipt times break ordering. When truly required, use sequence/version, partition ordering, or proper causal metadata.
8. **Treating correlation ID as user identity:** it only links steps, never use it for authentication or authorization.
9. **Confusing "publish succeeded" with "consumer processed successfully":** publishing to a Spring local event, outbox, or broker carries different guarantees; monitoring, retries, and idempotency are needed.

## 11. Checklist Before Finalizing Payload Schema

Before publishing a new event, answer clearly:

1. What domain confirmation does `occurredAt` represent? Can it be created before commit?
2. Is the time format `Instant`/ISO-8601 UTC or epoch numbers? If numeric, what unit?
3. Are `createdAt` or `publishedAt` also needed, or are those strictly transport metadata?
4. At which boundary is `correlationId` created? Who is responsible for preserving it across steps?
5. Is `eventId` unique per occurrence and stable across retries?
6. Does `causationId` point to the exact message/command that directly caused the event?
7. Are IDs and timestamps passed across HTTP, async, brokers, and outboxes without accidental regeneration?
8. Do consumers deduplicate by `eventId` instead of dropping an entire workflow by correlation ID?
9. Are `traceId`, `orderId`, or personal data confused with `correlationId`?
10. Are there tests using `Clock.fixed` verifying metadata after serialization/deserialization, rollback, and retries?

### Remember

~~~text
occurredAt    -> When did the business fact occur?
eventId       -> Which specific event?
correlationId -> Which workflow does this event belong to?
causationId   -> What directly caused it?
traceId       -> Which execution did observability tracing capture?
publishedAt   -> When did the transport publish the event?
processedAt   -> When did the consumer finish?
~~~

**Good design is not cramming every metadata field into every payload.** Keep the fields useful for the contract, while always defining timestamp semantics and ID scopes clearly. In Spring Framework, `ApplicationEventPublisher` and `@EventListener` handle publishing/receiving events; preserving semantic `occurredAt` and `correlationId` is the application's responsibility.

## Official Documentation

- [Spring Framework — ApplicationEvent Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEvent.html)
- [Spring Framework — ApplicationEventPublisher Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — ApplicationContext Events and EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [OpenTelemetry — Trace API Concepts](https://opentelemetry.io/docs/concepts/signals/traces/)
