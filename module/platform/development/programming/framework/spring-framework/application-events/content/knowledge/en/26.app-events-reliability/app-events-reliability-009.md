# Dead-Letter and Compensation Actions in Spring Application Events

## 1. Context and Goal

An event-driven application cannot assume every listener and every external system always succeeds. Payments can time out, shipping APIs can go down temporarily, a message can carry a malformed payload, or a process can crash between updating data and sending notifications. When discussing **reliability**, two critical mechanisms are **dead-lettering** and **compensation actions**.

A **dead-letter queue/topic (DLQ/DLT)** is where a message that cannot be processed under the current policy is routed for retention, tracking, investigation, or controlled replay. A **compensation action** is a new business action intended to handle the consequences of already-succeeded steps in a workflow after a later step fails: releasing inventory, refunding payment, canceling a reservation, or revoking a granted permission.

They are not synonymous: **a message entering a DLQ does not automatically require canceling an order**; conversely, a workflow can proactively compensate right after a business failure without waiting for a DLQ.

In Spring, clearly separate three layers:

1. **Spring Framework Application Events**: `ApplicationEventPublisher`, `@EventListener`, `ApplicationEventMulticaster`, `@TransactionalEventListener`. Dispatches within the same `ApplicationContext`; synchronous in memory by default. Does not inherently provide durable queues, retry/acknowledgment, DLQs, or post-crash replay.
2. **Messaging integration** such as Spring Kafka and Spring AMQP/RabbitMQ: listener containers, brokers, retries, recovery, DLT/DLX, and dedicated message acknowledgment rules.
3. **Durable business design**: transactional outbox/inbox, state machines, sagas/process managers, idempotency, compensation, and redrive operations.

After this lesson, you should be able to explain when to retry, when to dead-letter, when to compensate, and how to avoid introducing extra errors or duplicate side effects during recovery.

## 2. Distinguishing Application Events from Durable Messaging

A Spring bean publishing an event is very simple:

~~~java
// Illustrative snippet inside a Spring-managed service.
publisher.publishEvent(new OrderPlaced(orderId));
~~~

Handling listener:

~~~java
// Illustrative snippet.
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    paymentGateway.charge(event.orderId());
}
~~~

With the default `SimpleApplicationEventMulticaster`, callbacks normally execute **synchronously right on the event-publishing thread**. If `charge` throws a `RuntimeException`, the error can propagate to the caller of `publishEvent`. Spring does not automatically record failed events into a DLQ for replay after a restart.

If using `@Async @EventListener`, callbacks run on another executor, yet `ThreadPoolTaskExecutor`'s queue is still normally **in JVM memory**. Unprocessed tasks when the JVM dies can be lost. `@Async` changes thread and error-handling boundaries; it **does not guarantee durable delivery on its own**.

~~~text
ApplicationEventPublisher
    |
    +-- Default SimpleApplicationEventMulticaster
    |       +-- synchronous callback
    |       +-- exceptions can propagate to publisher
    |
    +-- @Async or multicaster with TaskExecutor
            +-- callback runs on worker thread
            +-- queue is usually in-memory
            +-- no built-in ACK/retry/DLQ across crashes
~~~

If the business requirement is "a message must eventually be processed even if the service restarts", you need durable storage/a broker or an equivalent mechanism, not merely an in-process event listener.

### Terminology

| Term | Meaning |
| --- | --- |
| Event | Information about a fact that occurred, such as OrderPlaced |
| Attempt | One execution pass attempting to process a message |
| Retry | Re-attempting after an error, with a policy and limits |
| DLQ/DLT | Storage destination for messages that cannot be processed under current policy |
| Redrive/replay | Reprocessing messages held in a DLQ/history |
| Compensation | A business action to handle consequences of a previously completed step |
| Idempotency | Not duplicating side effects when the same intent is redelivered |
| Outbox | Event record committed together with business data |
| Inbox/processed-events | Processing trace helping consumers prevent duplicates |
| Saga | Sequence of local transactions with forward continuation or compensation steps |
| Poison message | Message that repeatedly fails, often due to data or program bugs |

Dead-lettering **does not mean successful processing**. It normally marks a transition to "stop automatic retries; a different operational workflow is needed".

## 3. Classifying Failures Before Retrying

Not every exception deserves a retry. Classify by business and technical nature.

### Transient Errors

Examples: HTTP 503, network timeouts, rate-limited partner APIs, recoverable DB deadlocks, or temporary broker disruptions. Use **bounded retries** with backoff, jitter, timeouts, and an overall time limit.

### Permanent Errors Under Current Data

Examples: malformed payload schema, missing required fields, unsupported event version, command violating business rules, or invalid customer ID. Retrying the exact same payload hundreds of times is usually futile. Route straight to DLQ, return a business rejection, or trigger a data-cleanup workflow.

### Ambiguous Outcomes

Especially dangerous are timeouts after calling payment/refund endpoints: the request may have **succeeded externally**, yet the caller never received the response. Retrying with a new ID can charge/refund the customer multiple times.

Safe handling:

1. Persist a stable `operationId`/idempotency key.
2. Query actual status at the provider if an API exists.
3. If already succeeded, finish the workflow without calling again.
4. Only if definitely not executed, retry per policy.
5. If unverifiable, transition to **PENDING_RECONCILIATION** and require appropriate intervention.

Never deduce "timeout = failed" or "HTTP 400 = never retry": the external API's contract decides.

## 4. Designing Retry and Dead-Letter Policies

A sample flow:

~~~text
Delivery Attempt 1
   |
   +-- success -> mark processed / ACK appropriately
   |
   +-- transient failure
   |     |
   |     +-- wait 1s (+ jitter), retry 1
   |     +-- wait 2s (+ jitter), retry 2
   |     +-- wait 4s (+ jitter), retry 3
   |     +-- still failing -> DLQ + alert
   |
   +-- permanent failure -> DLQ / immediate business rejection
   |
   +-- ambiguous outcome -> query status / reconciliation
~~~

Explicitly define:

- **Max attempts**: total executions or retries after the initial try? "3 attempts" usually means 1 initial + 2 retries.
- **Backoff**: increasing wait durations, jitter to prevent retry storms.
- **Timeout**: every attempt must be bounded; hung tasks must not pin workers forever.
- **Deadline/TTL**: stale messages may lose business relevance.
- **Concurrency/rate limits**: retry traffic must not starve fresh requests of resources.
- **Exception classification**: retryable, non-retryable, ambiguous.
- **Recovery**: move to DLQ, continue saga, trigger compensation, or alert operators.
- **Monitoring**: attempts, errors, queue depth, oldest age, and business impact.

One common trap is catching every `Exception`, logging it, and returning normally: the container/broker may think the message succeeded and ACK it, preventing the error from ever being retried or dead-lettered.

## 5. What Data Should a Dead-Letter Record Contain?

An illustrative envelope:

~~~java
// Java snippet: data describing a failed message.
public record DeadLetterEnvelope(
        String originalEventId,
        String eventType,
        int schemaVersion,
        String aggregateId,
        String correlationId,
        String causationId,
        String consumerName,
        int attempts,
        String errorCode,
        String originalDestination,
        String failedAtIso8601,
        String payloadReference
) {}
~~~

**Important fields:**

- `originalEventId` must remain stable across redeliveries.
- `eventType`/`schemaVersion` help when upgrading schemas or fixing messages.
- `aggregateId` identifies the affected business object.
- `correlationId`/`causationId` trace the event chain.
- `consumerName` distinguishes different consumers for the same event.
- `attempts`/`errorCode` aid retry analysis; `errorCode` should be more stable than exception text.
- `originalDestination` records the original topic, partition, or queue when available.
- `failedAt` tracks message age; use a timezone-explicit timestamp.
- `payloadReference` points to safely stored payload data; do not dump all sensitive data into the DLQ by default.

A DLQ must have an **owner**, retention period, access controls, security policies, and operational states such as NEW, INVESTIGATING, READY_TO_REDRIVE, RESOLVED. Otherwise, the DLQ becomes a dumping ground where nobody recovers messages.

### Should Stack Traces Be Stored?

You may retain error details for investigation, but cap size, redact PII/tokens, and enforce retention. With some brokers, repeated redrives and re-dead-lettering can balloon exception headers/history metadata.

## 6. Dead-Lettering and Compensation Are Two Distinct Decisions

Workflow analysis:

~~~text
OrderPlaced
  |
  +-- ReserveInventory       (succeeded)
  |
  +-- ChargePayment
        |
        +-- success -> OrderPaid -> proceed to shipping
        |
        +-- transient -> bounded retry
        |
        +-- ultimately unable to complete
                |
                +-- record failed-message/DLQ
                +-- business decision
                     |
                     +-- CancelAndReleaseInventory
                     +-- or PendingManualReview
                     +-- or ForwardRecovery
~~~

**Do not design a rule like "every DLQ entry cancels the order".**

- If a notification email failed, a `PAID` order can still be completely valid.
- If a payment was permanently declined, releasing inventory may be right.
- If a charge outcome is ambiguous, releasing or refunding immediately may be wrong.
- If items are already `SHIPPED`, "canceling" the order cannot simply undo shipping by default.

A DLQ is a technical signal of **one consumer/operation**. Compensation is a **business workflow** decision given the current state. You can dead-letter first, review, and decide to compensate; or compensate immediately under a safe rule while still retaining a DLQ record for audit.

## 7. Runnable Java 17+ Spring Framework Example

The following example uses **Java 17+**, Maven, and **Spring Framework 6.2.12**. No Spring Boot, database, Kafka, or RabbitMQ is required.

**Mandatory limitation to understand accurately:** `DeadLetters` in the code is an **in-memory Map simulating a DLQ**, with no persistence. Retries run synchronously without backoff for deterministic output. This is a **semantic demo** of dead-lettering/compensation, not a production solution or a real reliable queue.

### Scenario Requirements

- When placing two orders, inventory is reserved.
- **order-good**: `PaymentGateway` simulates failing twice and succeeding on the third try.
- **order-bad**: `PaymentGateway` simulates failing all three times.
- Upon exhausting retries, the listener records `event-bad` into the dead-letter Map and publishes a compensation request **CancelAndRelease**.
- The compensation listener releases inventory and transitions status to CANCELLED.
- If the same compensation request or original event is resent, a state guard prevents duplicate effects.
- Output is deterministic thanks to the default synchronous multicaster, with no clocks/sleeps.

Structure:

~~~text
dead-letter-compensation-demo/
├── pom.xml
└── src/main/java/demo/DeadLetterCompensationDemo.java
~~~

### 7.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>dead-letter-compensation-demo</artifactId>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
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

### 7.2. src/main/java/demo/DeadLetterCompensationDemo.java

~~~java
package demo;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class DeadLetterCompensationDemo {

    // Retries of the same event must keep the same eventId.
    public record OrderPlaced(String orderId, String eventId) {}

    // Compensation action has its own ID, linkable back to the cause.
    public record CancelAndRelease(String orderId, String actionId) {}

    public enum Status { RESERVED, PAID, CANCELLED }

    public static final class TemporaryGatewayFailure
            extends RuntimeException {
        public TemporaryGatewayFailure() {
            super("Temporary gateway failure");
        }
    }

    // In-memory model. Production needs DB/transactions/concurrency guards.
    public static final class OrderState {
        private final Map<String, Status> statuses = new LinkedHashMap<>();
        private final Set<String> reservedInventory = new LinkedHashSet<>();

        public void reserve(String orderId) {
            if (statuses.putIfAbsent(orderId, Status.RESERVED) != null) {
                throw new IllegalArgumentException("Duplicate order");
            }
            reservedInventory.add(orderId);
        }

        public Status status(String orderId) {
            Status status = statuses.get(orderId);
            if (status == null) {
                throw new IllegalArgumentException("Unknown order");
            }
            return status;
        }

        public void markPaid(String orderId) {
            if (status(orderId) != Status.RESERVED) {
                throw new IllegalStateException("Invalid payment state");
            }
            statuses.put(orderId, Status.PAID);
        }

        public boolean cancelAndReleaseOnce(String orderId) {
            if (status(orderId) != Status.RESERVED) {
                return false;
            }
            reservedInventory.remove(orderId);
            statuses.put(orderId, Status.CANCELLED);
            return true;
        }
    }

    // Deterministic stub: good succeeds on attempt 3; bad always fails.
    public static final class PaymentGateway {
        private final Map<String, Integer> attempts = new LinkedHashMap<>();

        public void charge(String orderId) {
            int attempt = attempts.merge(orderId, 1, Integer::sum);

            if ("order-good".equals(orderId) && attempt == 3) {
                System.out.println(
                    "gateway order-good attempt=3 SUCCESS");
                return;
            }

            System.out.println(
                "gateway " + orderId + " attempt=" + attempt + " FAIL");
            throw new TemporaryGatewayFailure();
        }
    }

    public record DeadLetter(
            OrderPlaced original, int attempts, String errorCode) {}

    public static final class DeadLetters {
        private final Map<String, DeadLetter> records =
                new LinkedHashMap<>();

        public void save(OrderPlaced event, int attempts, String errorCode) {
            records.putIfAbsent(
                event.eventId(), new DeadLetter(event, attempts, errorCode));
        }

        public int size() {
            return records.size();
        }
    }

    public static final class PaymentListener {
        private static final int MAX_ATTEMPTS = 3;

        private final OrderState orders;
        private final PaymentGateway gateway;
        private final DeadLetters deadLetters;
        private final ApplicationEventPublisher publisher;

        public PaymentListener(
                OrderState orders,
                PaymentGateway gateway,
                DeadLetters deadLetters,
                ApplicationEventPublisher publisher) {
            this.orders = orders;
            this.gateway = gateway;
            this.deadLetters = deadLetters;
            this.publisher = publisher;
        }

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            Status current = orders.status(event.orderId());

            if (current != Status.RESERVED) {
                System.out.println(
                    "duplicate " + event.orderId()
                    + " ignored status=" + current);
                return;
            }

            // Demo: synchronous retry. Production needs backoff and retry scheduler.
            for (int attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
                try {
                    gateway.charge(event.orderId());
                    orders.markPaid(event.orderId());
                    System.out.println(
                        "payment " + event.orderId() + " captured");
                    return;
                } catch (TemporaryGatewayFailure ex) {
                    if (attempt == MAX_ATTEMPTS) {
                        deadLetters.save(
                            event, attempt, "GATEWAY_UNAVAILABLE");
                        System.out.println(
                            "dlq " + event.eventId()
                            + " attempts=" + attempt);

                        // This is a new compensation command, not a database rollback.
                        publisher.publishEvent(new CancelAndRelease(
                            event.orderId(), "release:" + event.eventId()));
                    }
                }
            }
        }
    }

    public static final class CompensationListener {
        private final OrderState orders;

        public CompensationListener(OrderState orders) {
            this.orders = orders;
        }

        @EventListener
        public void releaseInventory(CancelAndRelease event) {
            if (orders.cancelAndReleaseOnce(event.orderId())) {
                System.out.println(
                    "compensation " + event.orderId()
                    + " inventory-released");
            } else {
                System.out.println(
                    "compensation " + event.orderId() + " skipped");
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderState orderState() {
            return new OrderState();
        }

        @Bean
        public PaymentGateway paymentGateway() {
            return new PaymentGateway();
        }

        @Bean
        public DeadLetters deadLetters() {
            return new DeadLetters();
        }

        @Bean
        public PaymentListener paymentListener(
                OrderState orders,
                PaymentGateway gateway,
                DeadLetters letters,
                ApplicationEventPublisher publisher) {
            return new PaymentListener(orders, gateway, letters, publisher);
        }

        @Bean
        public CompensationListener compensationListener(OrderState orders) {
            return new CompensationListener(orders);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            OrderState orders = context.getBean(OrderState.class);
            DeadLetters dlq = context.getBean(DeadLetters.class);

            orders.reserve("order-good");
            orders.reserve("order-bad");

            context.publishEvent(
                new OrderPlaced("order-good", "event-good"));
            context.publishEvent(
                new OrderPlaced("order-bad", "event-bad"));

            // Duplicate compensation request: do not release a second time.
            context.publishEvent(
                new CancelAndRelease("order-bad", "release:event-bad"));

            // Redelivery of original event after order is already CANCELLED.
            context.publishEvent(
                new OrderPlaced("order-bad", "event-bad"));

            System.out.println(
                "final order-good=" + orders.status("order-good"));
            System.out.println(
                "final order-bad=" + orders.status("order-bad"));
            System.out.println("dlq-count=" + dlq.size());
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=demo.DeadLetterCompensationDemo
~~~

Lines printed by **the program itself**:

~~~text
gateway order-good attempt=1 FAIL
gateway order-good attempt=2 FAIL
gateway order-good attempt=3 SUCCESS
payment order-good captured
gateway order-bad attempt=1 FAIL
gateway order-bad attempt=2 FAIL
gateway order-bad attempt=3 FAIL
dlq event-bad attempts=3
compensation order-bad inventory-released
compensation order-bad skipped
duplicate order-bad ignored status=CANCELLED
final order-good=PAID
final order-bad=CANCELLED
dlq-count=1
~~~

Maven/Spring may print extra logs. The output above is expected from `System.out.println` in the code, not a claim that Maven was executed on a real machine.

### 7.3. Detailed Explanation

- **order-good** has three attempts yet only **one original eventId**. The gateway succeeds on the third attempt; state becomes PAID, with no DLQ/compensation.
- **order-bad** fails all three times. `PaymentListener` saves a `DeadLetter` under `event-bad`, prints status, and publishes `CancelAndRelease`.
- Because the default multicaster is synchronous, `CompensationListener` receives the compensation event immediately. It releases inventory and transitions `order-bad` to CANCELLED.
- The same compensation action is replayed afterward. State is no longer RESERVED, so this time it prints `skipped`. This is an example of an idempotent state guard.
- The same `OrderPlaced` `event-bad` is republished. `PaymentListener` sees CANCELLED state, ignores it, and does not call the payment gateway again.
- The DLQ count remains 1: the failure record is kept for analysis even after compensation finished.

**This simulation does not verify**: durability, database atomicity, concurrency, broker ACKs, asynchronous retries, crash recovery, exactly-once payments, or DLQ persistence when the system dies. Those properties must be designed and tested separately.

### 7.4. Intentional Limitations of the Demo

- All Maps/Sets live only in the JVM and are not thread-safe for multiple writers; real systems need storage, unique constraints, and optimistic locking.
- Retries run immediately without backoff for clear output. Real systems need timeouts, bounded backoff/jitter, and failure classification.
- The payment stub does not charge real money; real payment gateways need external idempotency keys and reconciliation for ambiguous outcomes.
- Compensation is published synchronously in the JVM; if the process crashes between saving the dead-letter and requesting compensation, the compensation action can be lost.
- Status-based state guards are one protection layer; production also needs `actionId` and versions to prevent duplicates at the message/consumer level.

## 8. Compensation Differs from Rollback

A database transaction can roll back **uncommitted** changes within that transaction's scope. However, a distributed workflow has usually committed multiple local transactions already:

~~~text
T1: InventoryService reserves product          COMMITTED
T2: PaymentService charges money               COMMITTED
T3: ShippingService creates shipment           FAILED
~~~

A JDBC rollback in `ShippingService` does not automatically delete T1 or refund T2. The system needs **new** actions:

~~~text
ShippingFailed
    |
    +-- RequestPaymentRefund
    |       +-- RefundCompleted (when actually confirmed)
    |
    +-- RequestInventoryRelease
    |       +-- InventoryReleased
    |
    +-- OrderCancellationCompleted
~~~

Compensation actions can also fail. Refunds can take days; shipments may already be handed to a partner; inventory releases can hit conflicts. Therefore, **compensation is not synonymous with perfectly reversing history**.

### Compensation Needs Idempotency

- Fixed `compensationActionId` across retries.
- Unique constraint on `actionId`/consumer when persisting processed actions.
- Check `expectedState`/`aggregateVersion` and valid transitions.
- Use the payment gateway's idempotency key when refunding.
- On timeout when it is unclear whether a refund succeeded, query status instead of creating a new refund.
- Persist states PENDING, RUNNING, COMPLETED, FAILED so you never infer "request sent = succeeded".

Never execute an old cancellation message on a `SHIPPED` order merely because the message came from an old workflow. Compare current state and action validity.

## 9. Saga Orchestration and Choreography

A **Saga** is a sequence of local transactions; when one step fails, the system can attempt to move forward or run compensation steps.

### Choreography

Services independently listen to events and emit subsequent events:

~~~text
OrderCreated -> InventoryReserved -> PaymentCaptured -> ShipmentCreated
                      |
                      +-- PaymentFailed -> ReleaseInventory -> OrderCancelled
~~~

Advantage: loose coupling. Drawback: hard to observe across many modules; event cycles, duplicates, and compensation choices can scatter across many listeners.

### Orchestration

A **process manager/saga orchestrator** persists durable state:

~~~text
sagaId=checkout-17
state=COMPENSATION_PENDING
failedStep=CHARGE_PAYMENT
nextAction=RELEASE_INVENTORY
attempt=2
nextRetryAt=...
~~~

The orchestrator determines the next action, timeouts, and forward recovery or compensation paths. Crucially, the orchestrator's state must be **persisted**—never use a static Map in a production JVM.

No single annotation in Spring Context automatically turns `@EventListener` into a distributed saga. You must design state machines, transactions, messaging, and monitoring to fit requirements.

## 10. Transactional Outbox and Idempotent Inbox

When `OrderService` commits successfully yet the process dies before publishing the integration event, messages can be lost if relying solely on in-process callbacks.

**Transactional outbox** persists the business change and the event to send **in the same database transaction**:

~~~text
BEGIN
    UPDATE orders SET status = 'RESERVED' ...
    INSERT INTO outbox_events ...
COMMIT
    |
    +-- relay reads outbox
    +-- publishes to broker
    +-- consumer handles (idempotent)
~~~

Illustrative SQL schema (actual data types depend on DB):

~~~sql
CREATE TABLE outbox_events (
    event_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    event_type VARCHAR(100) NOT NULL,
    payload_json TEXT NOT NULL,
    status VARCHAR(30) NOT NULL,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE processed_events (
    consumer_name VARCHAR(100) NOT NULL,
    event_id VARCHAR(100) NOT NULL,
    processed_at TIMESTAMP NOT NULL,
    PRIMARY KEY (consumer_name, event_id)
);

CREATE TABLE compensation_actions (
    action_id VARCHAR(100) PRIMARY KEY,
    aggregate_id VARCHAR(100) NOT NULL,
    status VARCHAR(30) NOT NULL,
    updated_at TIMESTAMP NOT NULL
);
~~~

**Why are an inbox/unique constraint needed?** The relay can publish successfully, then crash before marking the outbox sent. On restart, the same event is published again. Consumers must ensure marking processed and updating business database tables happen in **the same transaction**. Doing `SELECT` to check `eventId` then applying the side effect without a transaction/unique constraint remains vulnerable to races.

For external APIs, the API's own idempotency or a reconciliation step is required; a unique constraint in your DB cannot by itself prevent a partner from executing a side effect twice if remote outcomes are ambiguous.

### When Persisting Compensation

Instead of only publishing `CancelAndRelease` in-process after receiving a failure, you can **persist the compensation intent** alongside transitioning `Order -> CANCELLATION_PENDING`, then let a durable worker pick up and execute the action. If the worker dies, the action remains for retry. Once finished, update status and emit `CompensationCompleted` per contract.

An outbox improves durability, yet **does not automatically guarantee end-to-end exactly-once**; duplicates can still happen at the broker or external API.

## 11. Dead-Lettering in Spring Kafka

**Spring Kafka** offers a framework distinct from Spring Context `@EventListener`. With `@KafkaListener`, you can configure:

- **DefaultErrorHandler** to control retries, classify exceptions, and recover.
- **DeadLetterPublishingRecoverer** to send failed messages to a dead-letter topic.
- **FixedBackOff** or bounded exponential backoff.
- Properly designed container ACK/offset and transaction policies.

**Configuration snippet** example, not part of section 7's Spring Context demo:

~~~java
// Requires spring-kafka, a matching KafkaTemplate, and container config.
@Bean
DefaultErrorHandler errorHandler(KafkaTemplate<Object, Object> template) {
    DeadLetterPublishingRecoverer recoverer =
            new DeadLetterPublishingRecoverer(template);

    // Initial attempt + 2 retries = max 3 attempts.
    return new DefaultErrorHandler(
            recoverer, new FixedBackOff(1_000L, 2L));
}
~~~

Imports are required for `DefaultErrorHandler`, `DeadLetterPublishingRecoverer`, `KafkaTemplate`, and `org.springframework.util.backoff.FixedBackOff`. Importantly: **attach the handler to the Kafka listener container factory actually in use**; do not assume every Kafka listener uses this bean automatically without matching auto-configuration.

Per Spring Kafka docs, `DeadLetterPublishingRecoverer`'s default resolver may use a **-dlt** topic suffix and the original record's partition; ensure the DLT exists with matching partition counts or configure a custom resolver. Watch what happens if publishing to the DLT **also fails**; never ACK/commit the source offset as if recovery completed when policy requires durable dead-letter persistence.

A DLT records failures at the consumer level; business compensation requires the consumer or process manager to decide and emit separate compensation commands or events.

## 12. Dead-Lettering in RabbitMQ/Spring AMQP

With RabbitMQ, you typically use a **dead-letter exchange (DLX)** attached to a queue, a routing key, and a dead-letter queue. Messages can be dead-lettered when a consumer rejects/nacks with `requeue=false`, when TTL expires, or under appropriate queue conditions.

Define clearly:

1. Original queue and consumer acknowledgment mechanism.
2. Dead-letter exchange, dead-letter routing key, and target queue.
3. Retry topology, TTL/delays, and maximum attempts; avoid infinite loops through the DLX.
4. Requeue policy for transient vs. permanent errors.
5. Message IDs, redelivery metadata, idempotency, and ordering.
6. What happens if dead-letter routing/publishing fails.
7. Monitoring, retention, and redrive.

Spring AMQP has its own listener containers, retry interceptors, and recoverers; do not copy Spring Kafka configurations verbatim onto RabbitMQ. A DLX also does not automatically create a DLQ for Spring Context's internal `@EventListener`.

## 13. Redrive: Safely Replaying Messages from a DLQ

Redriving is an **operation capable of creating duplicate side effects**, because business state may have changed while the message sat in the DLQ.

Recommended operational workflow:

1. Identify original `eventId`, `consumerName`, aggregate, schema version, `errorCode`, and attempts.
2. Confirm the bug/downstream/schema is fixed; otherwise, redriving simply starts a new failure loop.
3. Cross-check **current** business state along with compensation state.
4. Check idempotency keys and external outcomes: did the charge/refund/email/booking actually happen?
5. Decide between **replaying the original event**, **issuing a new command**, or **marking resolved**. Do not treat these three options as equivalent.
6. If editing the payload, keep an audit trail: who edited, new version, hash/correlation, and reason.
7. Redrive in small batches with rate limits and a max redrive count.
8. Verify side effects, business state, and close the DLQ entry with evidence.

If an order is already CANCELLED and inventory was released, never blindly republish an old `PaymentRequested` turning the order into PAID. Recovering the transaction usually requires a **new authorized workflow**.

### DLQ Loops

Messages pushed from the DLQ back to the main queue that fail and return to the DLQ can create an infinite loop. Track `redriveAttemptCount`, last attempt time, approver decision, and terminal states to bound cycles.

## 14. When Compensation Also Fails

A compensation step must be treated as seriously as a primary business operation:

~~~text
CancelAndRelease
    |
    +-- success -> OrderCancelled
    |
    +-- InventoryService timeout
           |
           +-- bounded retry with same actionId
           +-- COMPENSATION_PENDING
           +-- retries exhausted -> COMPENSATION_FAILED
                              +-- compensation DLQ/alert/manual recovery
~~~

Meaningful states:

- `BUSINESS_STEP_FAILED`: primary step did not finish.
- `COMPENSATION_REQUESTED`: compensation decided but not yet confirmed.
- `COMPENSATION_RUNNING`: worker is executing/retrying.
- `COMPENSATION_COMPLETED`: compensation effect confirmed.
- `COMPENSATION_FAILED`: cannot complete automatically; action needed.
- `RECONCILIATION_REQUIRED`: unclear outcome, common with payments.

Do not transition an Order to CANCELLED merely because a release command was sent before evidence confirms inventory was released, if the business contract requires that confirmation. Consider **forward recovery** when reversal is no longer viable, such as a shipment past the point of cancellation.

## 15. @TransactionalEventListener Does Not Replace a DLQ

Spring supports listeners bound to transaction phases:

~~~java
// Illustrative snippet in a Spring bean.
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommit(OrderPlaced event) {
    // Runs only after the source transaction commits successfully.
}
~~~

Phases include `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. Default is `AFTER_COMMIT`; without a transaction, listeners normally do not run when `fallbackExecution=false`.

However, **AFTER_COMMIT is not a durable queue**. A process can die after the source commit before the callback finishes, and plain Spring Application Events do not replay automatically. You need an outbox/broker if post-crash recovery is required.

When a post-commit listener needs additional DB writes, old resources may still be bound during completion; you normally need a **new transaction** (e.g., a `@Transactional(propagation = REQUIRES_NEW)` service called via proxy) or to place work requiring atomicity inside the original transaction.

Never copy `TransactionSynchronizationManager` onto a worker to "carry the old transaction" when using `@Async`.

## 16. Distinguishing Identifiers to Prevent Duplicates

| ID | Scope and usage |
| --- | --- |
| `eventId` | One original event occurrence, preserved across redeliveries |
| `deliveryId` | Identifies one broker delivery attempt; may change |
| `correlationId` | Ties together an entire workflow/saga |
| `causationId` | Event/command that directly caused the new event |
| `aggregateId` | Business entity |
| `compensationActionId` | One compensation request, preserved across retries |
| `externalIdempotencyKey` | Deduplication key at a partner API |

If every retry generates a new `eventId`, consumer deduplication by `eventId` treats them as different events. Conversely, compensation is a **new business intent**: it should have its own `actionId`/`eventId` while linking back to the original event via `causationId`/`correlationId`.

The same event can validly be processed by **multiple consumers**; processed-events stores typically key by `(consumerName, eventId)` rather than using a global `eventId` that blocks all other consumers.

## 17. Concurrency and Ordering

Race example:

~~~text
Consumer A receives PaymentCaptured(order-17)
Consumer B receives CancelOrder(order-17)
~~~

If both process concurrently, arrival order alone does not guarantee final state. Use:

- State machines and transitions with preconditions.
- Optimistic locking or appropriate database locks.
- Unique constraints for event/action IDs.
- Partitioning/serialization by `aggregateId` when order is needed.
- Durable saga state/versions.
- Checking `expectedState` before every critical side effect.

A `synchronized` block in one JVM **has no effect across multiple instances**. The in-memory demo in section 7 only illustrates a single-threaded flow.

## 18. Security of DLQs and Redrive Tools

Dead-letter records can contain payloads, headers, personal information, account numbers, or errors from external systems. Require:

- Separate permissions for **viewing the DLQ** vs. **redriving/editing payloads**.
- Redaction of tokens, secrets, and sensitive data.
- Appropriate retention/deletion policies.
- Auditing who approved, edited events, redrove, and closed records.
- Schema validation and authorization checks before replay.
- Avoiding storing raw sensitive stack traces or unbounded headers.
- Restricting automatic refunds/cancellations driven by attacker-controllable error values.

A DLQ is part of operational infrastructure, not a public data store or an open API to freely replay arbitrary commands.

## 19. Observability and Alerting

| Suggested metric | Meaning |
| --- | --- |
| `consumer.processed / failed` | Total succeeded/failed executions |
| `retry.attempts` | Attempt counts by error type |
| `retry.age` | Message age / retry delay |
| `dlq.depth` | Number of messages awaiting resolution |
| `dlq.oldest_age` | Oldest unresolved entry |
| `dlq.redrive.success / failed` | Quality of the replay workflow |
| `compensation.pending / failed` | Workflows not yet brought to a safe state |
| `compensation.duration` | Time from failure to completed compensation |
| `duplicate.skipped` | Duplicate effects prevented |
| `reconciliation.pending` | Business results still ambiguous |

These are **suggested metric names**, not a list emitted automatically in full by Spring Framework.

Alert on oldest age, error rates, pending compensation, and business impact rather than only total DLQ depth. In metrics, avoid attaching `eventId`/`orderId` to high-cardinality labels; put IDs in structured logs/traces.

Minimal runbook: identify event and consumer, classify error, inspect business state, check compensation, decide retry/reconcile/manual approval, rate-limited redrive, verify side effects, and update DLQ status.

## 20. Reliability Testing

### Retry/DLQ

- Transient error N-1 times then succeeds on N: no dead-letter created.
- Always fails: respects policy attempt limits; DLQ retains original ID and errorCode.
- Permanent failure: no futile retries.
- DLT publish fails: do not mistakenly ACK the source and lose the message.
- Heavy retries under load: no retry storms or unbounded queues.

### Compensation

- Payment fails after reserve: inventory released strictly **once**.
- Duplicate `compensationActionId`: no second side effect.
- PAID/SHIPPED order is not wrongly canceled by an old cancellation message.
- Compensation fails: state stays PENDING/FAILED with retry/escalation.
- Refund timeout: query status before retrying with the same key.
- Redriving event after compensation: does not resurrect the old workflow.

### Crash/Concurrency

- Crash after state commit before publish: outbox keeps the record.
- Crash after broker publish before marking SENT: duplicate handled idempotently by consumer.
- Crash after external API succeeds before ACK: outcome query or idempotency key prevents duplicate side effects.
- Two workers on same aggregate: transactions/uniques/versions prevent races.
- Service restarts mid-compensation in a saga: compensation intent remains and workers can resume.

### Testing Spring

- Synchronous `@EventListener` can propagate exceptions to the publisher.
- `@Async @EventListener` lacks durable retries; test completion and worker errors separately.
- `@TransactionalEventListener(AFTER_COMMIT)` does not run on rollback; non-transactional events are skipped by default.
- With Spring Kafka/RabbitMQ, test broker ACK/retry/DLQ via proper integration tests; never treat an in-memory Map as production proof.

## 21. Common Mistakes

| Misconception | Consequence | Right approach |
| --- | --- | --- |
| "Having `@EventListener` gives you a DLQ" | Events lost on process death | Choose durable broker/storage |
| "`@Async` auto-retries after restart" | In-memory queue lost | Outbox/durable messaging |
| "Infinite retries for every error" | Storms, rising costs, and backlog | Bounded retry, jitter, classifier |
| "Any DLQ entry must cancel the order" | Wrong business compensation | Decide based on business state |
| "Sent `RefundRequested` = refunded" | Incorrect state | Confirm `RefundCompleted`/outcome |
| "Compensation is a distributed rollback" | Lost consistency | Local transactions + saga |
| "Timeout = not charged" | Double charge | Idempotency keys and reconciliation |
| "New `eventId` on each retry" | Deduplication defeated | Keep original `eventId` |
| "Check then insert needs no transaction" | Consumer races | Unique constraint + transaction |
| "Redrive entire DLQ after deploy" | Replays corrupt business state | Audits, rate limits, approvals |
| "Compensation cannot fail" | Saga stuck unnoticed | Durable retries and escalation |
| "`AFTER_COMMIT` guarantees replay" | Crash gap still exists | Outbox/broker |
| "DLQ stores raw stack traces/payloads" | Sensitive data leaks | RBAC, redaction, retention |

## 22. Implementation Checklist

1. Is this an **in-memory event** or a **durable message** going through a broker?
2. Are transient, permanent, and ambiguous outcomes classified?
3. Does the retry policy define max attempts, timeouts, backoff, jitter, and deadlines?
4. When retries exhaust, does the DLQ persist durably, and how is DLT publish failure handled?
5. Does the DLQ envelope include original `eventId`, `aggregateId`, schema version, attempts, and correlation?
6. Are there an owner and a DLQ redrive runbook?
7. Is it explicitly decided that **dead-lettering is not synonymous with compensation**?
8. Do compensation actions have stable IDs, state guards, and idempotency?
9. If compensation fails, is there a retry/escalation/alert path?
10. Is there an outbox/inbox or equivalent architecture for crash recovery?
11. Does redrive inspect current state and avoid duplicate side effects?
12. Have concurrency, duplicates, crashes, ambiguous payments, and compensation failures been tested?

**Conclusion:** Dead-lettering retains records of work that could not be processed; compensation is a **conditional business action** to bring a workflow back to a safe state. Internal Spring Application Events do not come with built-in DLQs/durable retries. For critical systems, combine **bounded retries, brokers/outboxes, idempotent consumers, saga state, durable compensation, controlled redrive, and observability**, rather than merely adding `@Async` or hoping an `AFTER_COMMIT` callback is never lost.

## Official Documentation

- Spring Framework 6.2 — Application Events: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework 6.2 — Transaction-bound Events: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework 6.2 — ApplicationEventPublisher Javadoc: https://docs.spring.io/spring-framework/docs/6.2.12/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Kafka — Error handling, retries, DefaultErrorHandler, and DLT: https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring AMQP — RabbitMQ messaging: https://docs.spring.io/spring-amqp/reference/
- RabbitMQ — Dead Letter Exchanges: https://www.rabbitmq.com/docs/dlx
