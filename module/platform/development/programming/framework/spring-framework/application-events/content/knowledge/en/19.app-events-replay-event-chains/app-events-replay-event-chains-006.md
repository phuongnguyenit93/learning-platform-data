# Long Event Chains and Traceability Challenges in Spring Application Events

## 1. Why Do Event Chains Become Harder to Control as They Grow?

In Spring, `ApplicationEventPublisher.publishEvent(...)` lets a component publish an event and listeners react without the producer calling each listener directly. This mechanism works very well when an event represents a **domain fact** such as `OrderPlaced` or `PaymentAuthorized`.

However, a listener can also publish another event. After a few extensions, a small process can grow into a multi-level chain:

~~~text
PlaceOrder command
      |
      v
OrderPlaced
      |
      v
PaymentAuthorized
      |
      v
InventoryReserved
      |
      v
FulfillmentReady
      |
      v
CustomerNotificationRequested
~~~

Each step's event may be valid, yet scattering processing across many classes raises tough questions: who owns the workflow, what caused the next step to run, which transaction committed, where did an exception occur, what ordering is guaranteed, and would a replay execute side effects a second time?

A long event chain often increases **implicit control flow depth**. When a controller only calls `orderService.placeOrder()`, a reader might not see that listeners in other modules invoked payment, reservation, and notification. Splitting modules does not automatically equal separation of responsibilities.

The goal of this lesson is to understand **how to identify event chains, map topology, add correlation/causation, block cycles, handle transactions and replay**, and know when to move from choreography to orchestration.

## 2. Dispatch Mechanisms That Create Event Chains in Spring

### 2.1. Default Synchronous Chains

With the default `SimpleApplicationEventMulticaster`, ordinary listeners not configured as async usually run on the **thread calling publish**. If a listener calls `publishEvent` again, the next publication runs nested inside the previous call.

~~~text
OrderService.placeOrder()
  -> publish(OrderPlaced)
     -> listener A onOrderPlaced()
        -> publish(PaymentAuthorized)
           -> listener B onPaymentAuthorized()
              -> publish(InventoryReserved)
                 -> listener C onInventoryReserved()
                    -> ...
     <- listeners return
  <- publish(OrderPlaced) returns
~~~

In a linear chain with one listener per type, observed behavior often resembles **depth-first recursion**. That is worth remembering because errors at the end of the chain can propagate back up to the use case through the call stack, and synchronous chain execution times add directly to request latency.

If an event has multiple listeners, `@Order` can influence the **invocation order of listeners for that event**, but when the first listener publishes a nested event, the nested event's listeners can run before the next listener of the initial event. Thus, `@Order` cannot establish a global total order across the entire graph.

### 2.2. Asynchronous Chains

`@Async` on a listener (when enabled via `@EnableAsync` and proper proxying) or configuring a `TaskExecutor` on the event multicaster can offload work to other threads. Then:

- The publisher can return before the listener finishes.
- Child listeners and sibling listeners can run in parallel or finish out of order.
- Exceptions inside the **body of an already-async task** do not automatically propagate back up the publisher's call stack.
- **Scheduling** failures such as the executor rejecting a task can still surface immediately at publish time.
- MDC, security context, or the source thread's transaction are **not automatically transferred** to every executor.

Consequently, adding async to a long chain makes **ordering and causal paths** harder to trace; it does not by itself turn the chain into a reliable workflow.

### 2.3. An Easily Overlooked Chain Source: Return Values

Spring allows a synchronous `@EventListener` method with a non-`void` return type to be interpreted as a new event to publish. A collection/array can emit multiple events. Illustrative example in a Spring bean with types and services already defined:

~~~java
@EventListener
public PaymentAuthorized onOrderPlaced(OrderPlaced event) {
    return paymentService.authorize(event);
}
~~~

Even without seeing `publisher.publishEvent(...)` inside the method, there is still an edge in the event graph. For `@Async` listeners, publishing events via return values like this **is not supported**; use `ApplicationEventPublisher` explicitly if further publication is needed.

When auditing code, search for both `publishEvent(...)` calls and listeners whose return values have event types.

## 3. Chain Complexity: Depth, Fan-Out, Fan-In, and Cycles

There is no fixed “too long” number for every system. Look at these characteristics instead:

| Concept | Interpretation | Risk signals |
| --- | --- | --- |
| **Depth** | Number of sequential event edges from the root event | Accumulated latency, deep call stacks, many hops to trace failures |
| **Fan-out** | One event spawns multiple branches via listeners or child events | Many concurrent tasks/side effects, load amplification |
| **Fan-in** | Multiple branches must finish to trigger the next step | Race conditions, uncertainty over “are all conditions met?” |
| **Cycle** | Chain loops back to a prior event/state | Loops, recursion, event storms |
| **Cross-thread hop** | Subsequent step runs on another thread/executor | Context loss, out-of-order results |
| **Cross-transaction hop** | Subsequent step uses a separate/after-commit transaction | Cannot roll back the whole chain as one transaction |
| **Retry/replay** | Event is redelivered or history is intentionally replayed | Duplicate side effects without idempotency |

Fan-out can grow rapidly: if one level generates an average of three events and subsequent levels each generate three more, task counts can grow exponentially with depth. This is only an **illustrative amplification model**, not a mandatory Spring formula. Still, it explains why a small change in a listener can overwhelm queues/executors.

### Real-World Symptoms

- An endpoint responds slowly even though controller code is tiny.
- Logs say “failed in InventoryReserved” with no clue which request or event triggered it.
- An order rolls back because an auxiliary notification listener failed.
- One business action sends an email multiple times for a single request.
- A projection gets overwritten backward because two handlers finished out of order.
- Replaying historical data accidentally re-executes payment operations.
- Many modules have `@EventListener` methods, yet no one knows the end-to-end flow.

When these symptoms appear, raising timeouts does not fix the architectural cause.

## 4. Mapping the Event Graph with Publishers, Listeners, and Transaction Boundaries

A useful diagram should clearly show **who publishes, who listens, whether follow-ups are emitted, and which thread and transaction each step runs in**.

~~~text
[HTTP PlaceOrder]
       |
       v
[OrderService] -- publish --> (OrderPlaced)
                                  |
                  +---------------+----------------+
                  |               |                |
                  v               v                v
               [Audit]       [Payment]        [Search index]
                                  |             async?
                                  v
                           (PaymentAuthorized)
                                  |
                                  v
                           [Inventory handler]
                                  |
                                  v
                           (InventoryReserved)
~~~

Do not draw only event names while ignoring where business state actually changes. For a complete design, annotate `sync/async`, `BEFORE_COMMIT/AFTER_COMMIT`, transaction managers, retries, brokers, and data resources.

Questions to answer whenever adding a listener:

1. Does the input event reflect a fact that already happened or merely a command?
2. Does the listener only react to the fact, or does it decide business workflow and emit child events?
3. Are other listeners subscribed to this event; do branches compete to update the same aggregate?
4. What happens if an intermediate step in the chain fails?
5. Is there any path back to an already-processed event?
6. Which listeners will a replay pass through, and what side effects will it trigger?
7. Is there metadata linking the current event to its immediate cause?

A publisher/listener inventory can be generated automatically from code, but the business diagram and workflow ownership still require review.

## 5. Runnable Java 17+ Example: Tracing a Four-Level Chain

This example uses **Spring Framework 6.2.8**, JDK 17+, and Maven, without Spring Boot. We simulate:

~~~text
OrderPlaced (event e1, hop 0)
  -> PaymentAuthorized (event e2, hop 1)
     -> InventoryReserved (event e3, hop 2)
        -> FulfillmentReady (event e4, hop 3)
~~~

This is an **event-flow simulation**; it does not call a real payment gateway or warehouse system. In real products, never publish `PaymentAuthorized` without business proof that authorization succeeded, and likewise for `InventoryReserved`.

Each event carries immutable metadata:

- `correlationId` remains constant across a business journey.
- `eventId` identifies the event instance.
- `causationId` points to the event that directly triggered this event.
- `hop` counts the number of steps from the root event.

### 5.1. Directory Structure

~~~text
event-chain-demo/
├── pom.xml
└── src/main/java/EventChainDemo.java
~~~

### 5.2. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-chain-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>EventChainDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. src/main/java/EventChainDemo.java

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class EventChainDemo {

    public record EventMeta(
            String correlationId,
            String eventId,
            String causationId,
            int hop
    ) {
        public EventMeta next(String nextId) {
            if (hop >= 3) {
                throw new IllegalStateException("Chain exceeds 3 hops");
            }
            return new EventMeta(
                correlationId, nextId, eventId, hop + 1
            );
        }
    }

    public record OrderPlaced(EventMeta meta, long orderId) { }
    public record PaymentAuthorized(EventMeta meta, long orderId) { }
    public record InventoryReserved(EventMeta meta, long orderId) { }
    public record FulfillmentReady(EventMeta meta, long orderId) { }

    private static void print(int number, String type, EventMeta meta) {
        System.out.printf(
            "%d %s corr=%s id=%s cause=%s hop=%d%n",
            number, type,
            meta.correlationId(), meta.eventId(),
            meta.causationId(), meta.hop()
        );
    }

    public static class Step1 {
        private final ApplicationEventPublisher publisher;

        public Step1(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            print(1, "OrderPlaced", event.meta());
            publisher.publishEvent(
                new PaymentAuthorized(
                    event.meta().next("e2"), event.orderId()
                )
            );
        }
    }

    public static class Step2 {
        private final ApplicationEventPublisher publisher;

        public Step2(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @EventListener
        public void onPaymentAuthorized(PaymentAuthorized event) {
            print(2, "PaymentAuthorized", event.meta());
            publisher.publishEvent(
                new InventoryReserved(
                    event.meta().next("e3"), event.orderId()
                )
            );
        }
    }

    public static class Step3 {
        private final ApplicationEventPublisher publisher;

        public Step3(ApplicationEventPublisher publisher) {
            this.publisher = publisher;
        }

        @EventListener
        public void onInventoryReserved(InventoryReserved event) {
            print(3, "InventoryReserved", event.meta());
            publisher.publishEvent(
                new FulfillmentReady(
                    event.meta().next("e4"), event.orderId()
                )
            );
        }
    }

    public static class Step4 {
        @EventListener
        public void onFulfillmentReady(FulfillmentReady event) {
            print(4, "FulfillmentReady", event.meta());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        Step1 step1(ApplicationEventPublisher publisher) {
            return new Step1(publisher);
        }

        @Bean
        Step2 step2(ApplicationEventPublisher publisher) {
            return new Step2(publisher);
        }

        @Bean
        Step3 step3(ApplicationEventPublisher publisher) {
            return new Step3(publisher);
        }

        @Bean
        Step4 step4() {
            return new Step4();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                 new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(
                new OrderPlaced(
                    new EventMeta("order-42", "e1", "root", 0), 42L
                )
            );
            System.out.println("MAIN publishEvent returned");
        }
    }
}
~~~

Run with JDK 17+ and Maven from the `event-chain-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

Lines printed in order by the program (excluding Maven logs):

~~~text
1 OrderPlaced corr=order-42 id=e1 cause=root hop=0
2 PaymentAuthorized corr=order-42 id=e2 cause=e1 hop=1
3 InventoryReserved corr=order-42 id=e3 cause=e2 hop=2
4 FulfillmentReady corr=order-42 id=e4 cause=e3 hop=3
MAIN publishEvent returned
~~~

### 5.4. Output Explanation

1. `main` publishes `OrderPlaced` with `eventId=e1`, `causationId=root`, `hop=0`.
2. Listener `Step1` processes the event and creates `PaymentAuthorized`. `EventMeta.next("e2")` copies `correlationId`, sets `causationId=e1`, and increments `hop`.
3. `Step2`/`Step3` continue, creating events whose `causationId` points accurately to the parent event.
4. `Step4` receives `FulfillmentReady` and emits nothing further, so the chain stops.
5. Since all listeners are synchronous and each type has one listener, `MAIN publishEvent returned` appears after the four log lines.

`EventMeta.next` prevents the fourth step from **emitting another child event** when `hop>=3`. This limit is illustrative: it does not defend against retries, duplicate delivery, or cycles where a producer resets metadata to `hop=0`. In real applications, event IDs must be unique per event instance (UUID/ULID or a deterministic rule); never hardcode e1/e2 for all requests.

### 5.5. One Extra Edge Can Create a Cycle

Suppose another listener receives `InventoryReserved` and re-publishes `OrderPlaced`:

~~~java
// Illustrative anti-pattern - do not add to the demo class.
@EventListener
public void onInventoryReserved(InventoryReserved event) {
    publisher.publishEvent(
        new OrderPlaced(
            event.meta().next("another-e1"), event.orderId()
        )
    );
}
~~~

The graph now has a backward edge:

~~~text
OrderPlaced -> PaymentAuthorized -> InventoryReserved
      ^                                 |
      |---------------------------------|
~~~

Without guards, a synchronous chain can nest deeply until stack overflow; an async chain can spawn excessive tasks. However, the best fix is not just adding a counter: semantically, `InventoryReserved` should not claim that placing the order just happened again. Move the next step into an orchestrator/command or emit a **genuinely new fact**.

## 6. Identifiers for Reconstructing Cause-and-Effect Relationships

A listener receiving `InventoryReserved` cannot tell precisely which event caused it if the payload only contains `orderId`. The same order can have multiple attempts, retries, parallel workflows, or compensating actions.

| Metadata | Question answered | Example |
| --- | --- | --- |
| `eventId` | Which specific event occurrence is this? | `e3` |
| `correlationId` | Which events belong to the same journey? | `order-42` |
| `causationId` | Which event directly led to this event? | `e2` |
| `aggregateId` | Which business aggregate is involved? | `42` |
| `hop` | How many steps has the event traversed? | `2` |
| `occurredAt` | When was the business fact recorded? | `2026-01-01T00:00:00Z` (example) |
| `schemaVersion` | Which version does the payload follow? | `v1` |
| `attempt` | Which delivery/processing attempt is this? | `2` |

**Distinguish the three key IDs:** correlation ID groups the whole workflow; causation ID points to the immediate parent event; event ID identifies the event itself. If multiple child events are created by one parent event, they have different `eventId` values but the same `causationId`.

### 6.1. Structured Logging

Simple logs like “handling event”, “payment done”, or “inventory failed” are insufficient for tracing. Log these fields instead:

~~~text
event=OrderPlaced eventId=e1 correlationId=order-42 causationId=root hop=0 status=handled
event=PaymentAuthorized eventId=e2 correlationId=order-42 causationId=e1 hop=1 status=handled
event=InventoryReserved eventId=e3 correlationId=order-42 causationId=e2 hop=2 status=failed
~~~

Grouping by `correlationId` and connecting `causationId -> eventId` edges lets you reconstruct the causal graph even when logs arrive out of chronological order. Log at publish time, handler start, handler success/failure, and after retries.

In production, use JSON structured logging and a tracing system where available. Do not log tokens, card numbers, sensitive payloads, or unnecessary PII.

### 6.2. Distinguish Correlation from Distributed Tracing

OpenTelemetry or Micrometer Observation `traceId`/`spanId` serve to observe execution spans. `correlationId` can be a business workflow ID that outlives a single request/trace. Do not assume the two must share the same value.

With `@Async`, message brokers, or thread pools, Spring does not automatically transfer **all** MDC/custom ThreadLocal/security context. Propagate tracing context selectively by policy, while **never copying JDBC/JPA transactions** onto worker threads.

Good logs can also include `producer`, `consumer`, `thread`, `transactionPhase`, `durationMs`, `retryAttempt`, and `topic/partition` when they genuinely exist.

## 7. Loops and Event Storms: Preventing Them by Topology

There are three common scenarios.

### 7.1. Direct Cycles

~~~text
A -> B -> A -> B -> ...
~~~

A handler listens to `OrderStatusChanged`, updates the status to the same value, and emits `OrderStatusChanged` again. If every handling creates a new event, the chain never converges.

### 7.2. Cross-Module Cycles

~~~text
OrderPlaced -> BillingRequested -> PaymentAuthorized
      ^                               |
      +---------- OrderUpdated -------+
~~~

If each module only reads its own code, authors may fail to notice that the combined graph contains a cycle.

### 7.3. Multi-Level Fan-Out

~~~text
                 +-> AuditRecorded
OrderPlaced -----+-> BillingRequested -> PaymentAuthorized
                 +-> NotificationQueued -> EmailAttempted
                 +-> ProjectionUpdated -> SearchIndexed
~~~

Even without cycles, tasks can explode if each handler generates multiple further events. With bounded queues/executors, you need backpressure, retry policies, and handling for rejected tasks.

### Key Countermeasures

1. **Publish only on a new state transition.** Reprocessing an event is not by itself a new business fact.
2. **Draw and review the graph** whenever adding events/listeners; detect cycles before deployment.
3. **Cap hops/TTL** per workflow or specific edges, with logs/alerts when thresholds are exceeded.
4. **Deduplicate by event ID** in consumers using durable storage when needed; an in-JVM `Set` is insufficient across nodes and restarts.
5. **Use aggregate version/expected state** to block repeated, backward, or racing transitions.
6. **Bound retries** and route unrecoverable failures to dead-letter/quarantine.
7. **Set queue limits, worker bounds, and timeouts**, with metrics and overload policies.
8. **Do not publish an event just to say “event processed”** unless it is genuinely a domain fact needed by a consumer.

A hop counter is only a **defensive guardrail**, not a substitute for a sound domain model. A cycle can reset `hop=0` through a new workflow if a producer issues IDs arbitrarily.

## 8. Listener Ordering, Fan-In, and Synchronization Conditions

Suppose `OrderPlaced` has two listeners: one handles payment and one handles inventory. Both must finish before the order is handed off to fulfillment.

~~~text
               +-> PaymentAuthorized --+
OrderPlaced ---+                       +-> FulfillmentReady
               +-> InventoryReserved --+
~~~

You cannot just use `@Order` to turn two branches into “both succeeded, now emit”. `@Order` is no substitute for a conditional state machine. In async execution, start and completion order are not guaranteed by annotation ordering either.

Instead, an orchestrator/aggregate persists `paymentAuthorized` and `inventoryReserved` flags and applies an atomic transition:

~~~text
if paymentAuthorized && inventoryReserved && !fulfillmentReady:
    markFulfillmentReady()
    emit(FulfillmentReady)
~~~

This is **pseudo-code**, not Spring API statements. In a real implementation, guard against race conditions using transactions, optimistic locking, unique constraints, or an appropriate coordinator. Avoid both handlers seeing the condition satisfied simultaneously and emitting the final event twice.

## 9. How Do Transaction Boundaries Affect Chains?

### 9.1. Synchronous Chain Within One Use Case

A `@Transactional` method can publish `OrderPlaced`, and synchronous listeners continue performing JDBC/JPA operations. With the same transaction manager and thread-bound resources, steps can **participate in the same transaction**. If a deep handler throws an unhandled `RuntimeException`, the exception can propagate back to the use case and trigger rollback per rollback rules.

Example:

~~~text
T1 BEGIN
  save(order)
  publish(OrderPlaced)
    -> auditListener
    -> paymentListener publishes PaymentAuthorized
       -> inventoryListener throws RuntimeException
T1 ROLLBACK (when rules apply)
~~~

However, this **does not guarantee** all side effects roll back: emails, HTTP calls, message brokers, `REQUIRES_NEW` transactions, and async workers each have separate boundaries.

If deducting inventory is mandatory for placing an order, consider calling the service synchronously in the use case instead of hiding it in a listener chain where errors might be caught/swallowed.

### 9.2. After Commit

`@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` ensures a listener triggers only when the transaction has committed successfully:

~~~java
@Component
public class SearchProjectionListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderPlaced(OrderPlaced event) {
        projectionService.updateAfterCommit(event);
    }
}
~~~

This is **illustrative** code requiring the corresponding event types, beans, and imports. By default `@TransactionalEventListener` does not invoke the handler if the event is published **outside a transaction**, unless `fallbackExecution=true` is specified. For DB writes inside after-commit, open a new transaction intentionally rather than assuming the original transaction's resources can commit a second time.

Combining `@Async` on an after-commit listener body runs work on an executor **without the publisher's transaction**. Task exceptions also do not roll back the already-committed source transaction.

### 9.3. Pitfalls When Chaining Transactional Listeners

An `AFTER_COMMIT` handler can publish a follow-up event inside its callback. Do not automatically assume another handler also using `@TransactionalEventListener(AFTER_COMMIT)` will trigger for the new event. During the callback, the source synchronization/transaction is already in its completion phase; the new event may **not register with a suitable active transaction**. Define clear boundaries or open a new transaction for the next step as business logic requires.

### 9.4. Multiple Transactions Do Not Equal One Overall Transaction

~~~text
T1: OrderPlaced -> COMMIT
T2: PaymentAuthorized -> COMMIT
T3: InventoryReserved -> FAIL
~~~

Failure of T3 does not automatically roll back committed T1/T2. If business rules require recovery, use retries or **compensating actions** in an explicit workflow. A long event chain spanning multiple transactions fits eventual consistency or an orchestrated saga, not a single atomic call.

## 10. Replay: Spring ApplicationEvent Does Not Store History

`ApplicationEventPublisher` publishes events inside `ApplicationContext`. It **is not an event store, does not maintain a durable event log, and does not replay after restarts**. When replaying to rebuild projections or recover workflows, you need a persisted data source such as an event store, outbox, or log/broker with retention policies.

Two very different kinds of replay:

- **Rebuild projection** from historical facts that already happened: run the projector without producing new business side effects.
- **Resume an incomplete workflow**: know which steps already committed, which are in-flight, and which need retry/compensation.

If all `OrderPlaced` events are replayed through the live pipeline and listeners emit child events again, a search-index rebuild could accidentally send emails or charge payments a second time.

~~~text
Stored OrderPlaced (historical)
        |
        +-> Rebuild search projection    [desired]
        +-> Send confirmation email      [undesired]
        +-> Charge payment               [dangerous]
~~~

A more reliable solution is to **separate the projection-replay pipeline** from the side-effect execution pipeline. An `isReplay` flag on payloads is brittle if listeners forget to check it or still run external API code.

### 10.1. New Events, Duplicates, and Retries

- **New event:** a new state transition with a new `eventId`.
- **Duplicate delivery:** the same `eventId` redelivered; not a new fact.
- **Retry:** adds `attempt` or delivery metadata, without changing the original fact's identity.
- **Historical replay:** re-reads stored events, keeping original identity so projectors restore state.
- **Compensation:** creates a new fact, such as `PaymentRefunded`, without erasing `PaymentCaptured` history.

Consumers must be designed to be **idempotent**. In some cases you can use a `processed_event` table keyed uniquely by `consumer + eventId`, writing the processed status in the same transaction as the projection update. When external side effects exist, a dedicated policy is needed because DB transactions do not roll back emails/payments.

### 10.2. Replay Checklist

| Concern | Question |
| --- | --- |
| Source | Where are events stored, and is the history complete? |
| Ordering | Is there a sequence/version per aggregate? |
| Scope | Replay by aggregate, partition, or time window? |
| Schema | Can new handlers read older payload versions? |
| Consumer | Which handlers are permitted to run during rebuild? |
| Side effects | Have duplicate emails/charges/reservations been prevented? |
| Checkpoint | Can replay resume after a crash without restarting from scratch? |
| Deduplication | Is there a durable key to handle redelivered events? |
| Monitoring | Are there replay run IDs, progress tracking, and alerts? |
| Rollback | Can you revert to the old projection if a rebuild goes wrong? |

**Do not equate an integration test calling `publishEvent` twice with proving safe system replay.** Real replay involves historical data, versioning, ordering, restarts, and idempotency.

## 11. Choreography vs. Orchestration: When to Change Approach?

**Choreography**: listeners react to facts independently and sometimes emit further events, with no central coordinator. It works well for independent side effects like auditing, cache updates, or auxiliary notifications.

**Orchestration**: a workflow owner/state machine holds state, sends commands to steps, and receives outcomes to decide what happens next. It works well when flows have many conditions, retries, timeouts, failure branches, or compensation.

| Need | Design approach to consider |
| --- | --- |
| A few listeners updating independent views | Choreography via domain events |
| A mandatory invariant within one transaction | Direct service calls in the use case |
| Multi-step chain with rollback/compensation branches | Orchestrator or saga/state machine |
| Steps spanning multiple services | Commands/events via broker, outbox, idempotency |
| Rebuilding read models from history | Dedicated projector reading an event store |
| Sending notifications after commit | Transaction-bound events and failure policies |
| Two branches must both succeed before the next step | Aggregate/workflow with explicit state |

If you have to open over a dozen listeners just to understand how a request finishes, or nobody owns answering “what if payment succeeded but inventory reservation failed?”, the event chain is hiding an untraceable workflow. You do not need to eliminate events; assign workflow ownership and keep events as **fact notifications**, not disguised commands.

## 12. Logging, Metrics, and Tracing for Long Chains

A minimal observability strategy includes:

1. Emit structured logs at **publish**, **handle start**, **handle success**, and **handle failure**.
2. Log `eventId`, `correlationId`, `causationId`, `aggregateId`, and `hop` to build graphs.
3. Track **end-to-end** workflow latency; HTTP latency does not capture async tasks running after the response.
4. Count events by type, listener exceptions, retries, deduplications, and skipped events.
5. Measure executor queue depth, active workers, rejected tasks, and dead-letter counts when applicable.
6. Use span-based tracing for handlers and publications when supported; propagate context properly across async boundaries.
7. Alert on abnormal hop counts, excessive fan-out, cycles, or the same event being processed repeatedly.

The names below are **examples of custom metrics**, not metrics automatically generated by Spring:

~~~text
app_event_published_total{type="OrderPlaced"}
app_event_listener_duration_seconds{listener="PaymentStep"}
app_event_listener_failures_total{type="InventoryReserved"}
app_event_chain_hops_max{workflow="order"}
app_event_deduplicated_total{consumer="projection"}
app_event_executor_rejections_total{executor="events"}
~~~

Do not put `eventId` or `orderId` into Prometheus labels because that creates **high cardinality**. Unique IDs belong in logs/traces, while metric labels should have small value sets (event type, consumer, status).

### Reconstructing the Causal Graph

Example from logs:

~~~text
e1 OrderPlaced
  |
  +-- e2 PaymentAuthorized
        |
        +-- e3 InventoryReserved
              |
              +-- e4 FulfillmentReady
~~~

Edges are built from `causationId`, not guessed from timestamps. With fan-out, one parent can have multiple child events. With async, logs may arrive out of order, yet the graph still accurately depicts the causal path.

## 13. Testing to Uncover Hidden Complexity

Beyond direct unit tests of individual handlers, integration tests using real Spring event dispatch are essential.

| Test | What to prove |
| --- | --- |
| Synchronous four-level chain | Logs and metadata match the example; final event stops |
| One listener throws an exception | Error-handling policy and source rollback behave as expected |
| Two listeners subscribed to the same event | No false reliance on completion order |
| One listener switched to `@Async` | Caller does not implicitly wait; task errors are monitored |
| Add a backward edge to the graph | Guard detects cycles or exceeded hops |
| Republish the same `eventId` | Consumer is idempotent with no duplicate side effects |
| Two events for the same aggregate arrive out of order | Projection checks version/sequence |
| Executor rejects tasks | Explicit backpressure/failure policy exists |
| Publish then roll back T1 | `AFTER_COMMIT` handler does not execute for that event |
| Crash after commit | Outbox/retries recover pending work |
| Multi-level fan-out | Load stays within queue/worker budgets |
| Rebuild projection from logs | Does not accidentally send emails or charge payments |

Never use `Thread.sleep(...)` and assume async listeners have finished. Use latches, futures, await utilities with timeouts, or system completion signals. For transaction tests, let transactions actually commit/roll back before asserting durable data.

### Checking Topology with Questions

- Which listeners create new events via `publishEvent` or return values?
- Is there any path leading from event type A back to A?
- Can any step be triggered multiple times for the same aggregate version?
- Do any handlers trigger side effects without checking for duplicates?
- Does an after-commit listener publish a new event whose downstream listener also expects a transaction-bound callback?
- When a branch fails, who owns retry/compensation state?
- Is `@Order` being misused as a false guarantee of distributed ordering?

Automated annotation scanning can help, but it cannot replace understanding publications triggered by runtime conditions.

## 14. Common Mistakes and Fixes

1. **Chains too long with no owner:** move stateful workflow parts to an orchestrator or explicit use case.
2. **Missing causation ID:** you know events share an order, not the immediate parent. Standardize metadata.
3. **Inferring order from timestamps:** async steps can finish out of order. Use causation, sequence, and traces.
4. **An event re-emits itself through another listener:** loops cause stack overflows or task storms. Fix the graph and transition guards.
5. **Ignoring fan-out:** monitor how many events/tasks one input creates and bound resources.
6. **Confusing `@Order` with completion order:** no chain-wide guarantee across executors/brokers.
7. **Assuming sync event chains are automatically atomic:** true only with matching resources and transactions; external side effects do not roll back.
8. **Assuming async listeners share T1:** imperative transactions are normally thread-bound; workers have separate boundaries.
9. **Assuming after-commit equals durable delivery:** crashes and executor failures can still drop work; use a transactional outbox when loss is unacceptable.
10. **Replaying through the live pipeline:** accidentally re-runs payments/emails. Separate projection rebuilds.
11. **No deduplication on retries:** consumers can apply updates twice. Store processed-event keys or enforce idempotency policies.
12. **Using a single-JVM boolean to prevent cluster duplicates:** neither durable nor cross-process.
13. **Swallowing errors in listeners:** workflows fail silently. Add clear logs, metrics, retries, and alerts.
14. **Not versioning event schemas:** replaying old events through new handlers corrupts data.
15. **Too many technical events with no domain value:** names like `RecordTouched` or `CacheUpdated` clutter the graph; ensure genuine consumer need.
16. **Measuring only request latency:** post-response async tasks can still run long.
17. **Not tagging replay environments:** side effects fire mistakenly and become hard to reconcile.
18. **No policy when hops exceed budget:** event storms are only noticed once the system saturates.

## 15. Practice Exercises

1. `OrderPlaced -> PaymentAuthorized -> OrderPlaced` is a cycle. What can happen in synchronous vs. async dispatch?
2. Why can `correlationId` not replace `causationId` when one event produces two child events?
3. In the demo, why does `MAIN publishEvent returned` appear after the four log lines? What changes if `Step2` runs asynchronously?
4. A consumer receives the same `eventId` three times due to retries. Are these three domain facts or three delivery attempts?
5. A workflow may ship only after both payment and inventory succeed. Why is `@Order` not a suitable fan-in mechanism?
6. If T1 commits, T2 commits, and T3 fails, can T3's transaction roll back all three?
7. What timing does `@TransactionalEventListener(AFTER_COMMIT)` address, and why is it not enough to guarantee zero event loss?
8. When replaying one million `OrderPlaced` events to rebuild a search index, how do you prevent sending emails a second time?
9. Why is `app_event_count{eventId="e1"}` a bad metric label?
10. Does Spring's `ApplicationEventPublisher` automatically store events for replay after a restart?

**Guidance:** (1) call-stack overflow or event storm; (2) correlation groups the workflow, causation points to the parent; (3) nested sync dispatch, whereas async stops the caller from waiting; (4) three deliveries of one fact; (5) requires an aggregate/orchestrator and atomic guard; (6) no, use compensation/retries; (7) runs only after commit, yet not durable; (8) dedicated replay projector, block side effects, and idempotency; (9) high cardinality; (10) no.

## 16. Summary

Long event chains are hard to trace because control flow is **scattered across many listeners**, branches may run synchronously or asynchronously, and they do not necessarily share transactions, ordering, or failure policies. Spring `@EventListener` decouples producers from consumers, but it does not automatically provide **causality, idempotency, replay, distributed tracing, durable delivery, or workflow-wide rollback**.

The highest-leverage practices: keep events as clear business facts, map the publisher/listener graph, propagate `eventId`/`correlationId`/`causationId`, block cycles and unbounded fan-out, set explicit transaction boundaries, separate projection replay from side effects, and use orchestration when workflows involve complex state or compensation branches.

## References

- Spring Framework Reference — *Application Events and EventListener*: https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html
- Spring Framework Reference — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html
- Spring Framework Javadoc — *ApplicationEventPublisher*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework Javadoc — *EventListener*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/EventListener.html
- Spring Framework Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.8/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
