# Dead-Letter Handling for Internal Events in Spring Framework

## 1. Goal and Scope

In a system using Spring Application Events, a listener may handle errors when connecting to external services, encountering invalid data formats, lacking permissions, timing out, or accessing deleted resources. Simply logging and ignoring errors risks **losing required work**. Retrying forever on the publisher thread can stall requests, hold transactions open too long, create duplicate side effects, and cascade failures. One design approach is routing **unprocessable** tasks to a **dead-letter area (DLQ/DL store)** for investigation, remediation, and controlled replay.

**Important:** Spring Framework's `ApplicationEventPublisher`, `@EventListener`, and `SimpleApplicationEventMulticaster` **do not provide an automatic durable dead-letter queue**. For events living only inside the JVM, an "internal DLQ" is a **custom application-designed mechanism**, such as a database table, durable queue, or an in-memory store for development. It is **not the same** as a Kafka/RabbitMQ DLQ or a message broker.

This lesson helps you:

- Understand what dead-lettering means for internal events and why not every listener error belongs in a dead letter.
- Distinguish exceptions propagating to the publisher, the multicaster's `ErrorHandler`, async executors, retries, dead letters, transactional events, and outboxes.
- Design a processing lifecycle with **bounded retries**, transient/permanent classification, sufficient diagnostic metadata, and idempotent replay.
- Implement a Java 17+ example with plain Spring Framework featuring two intentional errors, a temporary in-memory dead-letter store, and a replay operation.
- Choose durable storage, ensure proper transactions, and build operational/monitoring processes for production.
- Test key scenarios: transient errors, permanent errors, duplicates, restarts, rollbacks, and replay.

The scope is **Spring Framework Application Events within a single application**. Sections mentioning brokers/outboxes serve as comparisons and upgrade paths when durability is required.

## 2. What Spring Provides Out of the Box and What It Does Not

### 2.1. Default Event Path

~~~text
ApplicationEventPublisher.publishEvent(event)
               |
               v
ApplicationEventMulticaster
               |
               +--> @EventListener handler A
               |
               +--> @EventListener handler B
               |
               +--> @EventListener handler C
~~~

With the default `SimpleApplicationEventMulticaster`, regular listeners execute **synchronously on the publishing thread**. When a listener throws an unhandled exception and the multicaster has no configured `ErrorHandler`, the exception can halt the current dispatch pass and **propagate back to the publisher**.

When a `TaskExecutor` is configured, listeners supporting async at the multicaster level are handed off to the executor; exceptions may occur on a worker thread, **not automatically surfacing on the publisher's call stack**. `@Async` on a listener also has its own exception-handling paths. Transaction-synchronized listeners may require staying registered on the original thread; do not assume all listeners run async simply because the multicaster has an executor.

Spring provides these extension points:

- `SimpleApplicationEventMulticaster#setErrorHandler(ErrorHandler)`: handles `Throwable` raised by a listener; if the handler **swallows the error**, the publisher may proceed, though event data and listener identity are not automatically passed in full to the error handler.
- `SimpleApplicationEventMulticaster#setTaskExecutor(...)`: selects the execution mechanism for eligible listeners.
- `@EventListener` / `ApplicationListener<T>`: writes event-receiving logic, which may invoke a service with retry/dead-lettering.
- `@TransactionalEventListener`: binds callbacks to a transaction phase, such as `AFTER_COMMIT`.

These APIs **do not mean**: "Spring automatically saves failed events to a queue that can be replayed after restart." Achieving that requires designing storage, transaction boundaries, delivery workers, retry policies, and status observability.

### 2.2. Dead-Letter Differs from Error Logging

A log like "notification failed" helps diagnostics yet may lack data needed to reprocess. A structured dead-letter record typically stores **event identity, handler identity, minimal payload or reference, sanitized error cause, attempt count, status, timestamps, and version**.

| Concept | Meaning | Default guarantee |
| --- | --- | --- |
| Error log | Diagnostic log line | Not a replayable record |
| Multicaster `ErrorHandler` | Receives errors from listeners | Does not automatically save events or retry |
| Retry | Re-attempts a task after failure | Can duplicate side effects if idempotency is missing |
| Dead-letter store | Holds terminally failed work for later handling | Durability depends on implementation |
| Message broker DLQ | Queue/topic for unprocessable messages | Depends on broker and config; not Spring in-process default |
| Transactional outbox | Persists outbound work in the business transaction | Requires delivery worker and consumer idempotency |

**Pragmatic definition:** An event is "dead-lettered" when the system **intentionally stops automatically processing that event/handler under the current policy**, persisting enough information to investigate and optionally replay. It is not a built-in Spring `TransactionPhase` state.

## 3. Why Do Listeners Fail?

An event often has multiple listeners with different goals. For instance, `PaymentCaptured` may have listeners to send an email, record metrics, and sync CRM. If CRM is temporarily down, you may not want to roll back the payment transaction, yet you still need to persist the CRM sync task for later processing. Conversely, if a check **must** succeed before the business operation is accepted, swallowing exceptions and putting them into a DLQ can commit invalid data.

Classifying errors guides policy choices:

| Error type | Example | Appropriate policy |
| --- | --- | --- |
| **Transient** | Timeout, HTTP 503, network reset, temporarily locked resource | Bounded retry, backoff/jitter; if budget exhausted, dead-letter |
| **Rate limit** | HTTP 429, short-term quota | Respect `Retry-After`, rate limits, and backoff; do not retry in lockstep |
| **Permanent / non-retryable** | Invalid schema, malformed email, missing required field | Dead-letter early or reject at validation; data/code fix needed |
| **Permission/config error** | Bad credentials, ACL, endpoint | Can cause widespread failure; investigate config, pause consumer, avoid infinite loops |
| **Duplicate** | Event reprocessed after crash or replay | Idempotency, dedup key, unique constraint |
| **Missing dependency** | Database or core service down | Circuit breaker/bulkhead, stop accepting more under overload, alert operations |
| **Programming bug** | Unexpected `NullPointerException`, broken invariant | Investigate and fix; avoid pointless auto-retries |
| **Infrastructure failure in DLQ storage** | Unable to write dead letter | Must have explicit fallback policy; never report saved successfully |

**Do not catch `Throwable` indiscriminately** to push every error into a DLQ. Severe errors such as `OutOfMemoryError` should not be masked as ordinary business retries. Catch appropriate exceptions and classify based on dependency contracts.

## 4. Choosing the Unit of Failure: Event or Event–Listener?

An event may be dispatched to multiple handlers. If you only store `eventId` and replay by calling `publishEvent(event)` again, **all listeners** may receive it a second time:

~~~text
OrderPaid(eventId = e-42)
          |
          +--> metrics listener: SUCCESS
          +--> email listener: FAILED
          +--> loyalty listener: SUCCESS
~~~

When email fails, replaying the entire event could run metrics and loyalty a second time. Therefore, in many applications, the unit of work to dead-letter is:

**`(eventId, handlerId)`**, not just `eventId`.

Example:

~~~text
dead-letter key = ("evt-42", "send-receipt-email")
status          = DEAD
attempts        = 5
lastError       = "SMTP_UNAVAILABLE"
~~~

Other listeners still retain their succeeded status and do not need to re-run. If you want to replay through a global publisher, **every receiving listener must be idempotent** and able to skip already processed events. For systems with multiple independent subscribers, designing a delivery/handler state table avoids duplicate replays.

You should also store `eventType` and `schemaVersion` to handle old events properly after deploying new code. When payloads evolve, the replay program needs a way to read older events or safely migrate them.

## 5. Recommended Dead-Letter State Lifecycle

A production workflow can be modeled as:

~~~text
NEW / READY
     |
     v
PROCESSING --- success ---> SUCCEEDED / ACKED
     |
     +--- transient failure ---> RETRY_WAIT
     |                            |
     |                     delay / backoff
     |                            |
     |                            +----> PROCESSING
     |
     +--- permanent failure ---------------------\
     |                                            |
     +--- retry budget exhausted ----------------> DEAD
                                                  |
                                             investigate
                                                  |
                                     operator approves replay
                                                  |
                                               REPLAYING
                                                  |
                              success ------------+----> RESOLVED
                              failure -----------------> DEAD
~~~

This is a **reference design**, not a state machine built into Spring. State names should be standardized by the project.

Several principles:

1. **Clear retry budget:** maximum attempts or time limit; no infinite loops.
2. **Backoff:** avoid hammering failing dependencies; use exponential backoff and jitter to avoid thundering herds.
3. **Classification:** permanent data errors should not be retried 20 times like timeouts.
4. **Dead-letter persistence must be confirmed:** only report "dead-lettered" when the store returns success; if the store fails, do not assume work is safe.
5. **Controlled replay:** operations require authorization, tracing, and idempotency; fix the root cause before replaying.
6. **Retention:** define TTL/storage policies and deletion permissions, avoiding keeping PII too long.
7. **Crash recovery:** if a process dies between processing and updating state, use lease/claim timeouts and a mechanism to reclaim abandoned jobs.

Define success criteria **per handler**. "Publisher completed" is not equivalent to "every auxiliary task was truly persisted and processed," especially when async is involved.

## 6. Data Design Pattern for a Dead-Letter Store

A reference PostgreSQL schema (not a mandatory Spring schema):

~~~sql
CREATE TABLE internal_event_dead_letter (
    id                  UUID PRIMARY KEY,
    event_id            VARCHAR(120) NOT NULL,
    handler_id          VARCHAR(120) NOT NULL,
    event_type          VARCHAR(180) NOT NULL,
    schema_version      INTEGER NOT NULL,
    payload_json        JSONB NOT NULL,
    failure_kind        VARCHAR(32) NOT NULL,
    last_error_code     VARCHAR(120),
    last_error_summary  TEXT,
    attempts            INTEGER NOT NULL,
    first_failed_at     TIMESTAMPTZ NOT NULL,
    last_failed_at      TIMESTAMPTZ NOT NULL,
    next_attempt_at     TIMESTAMPTZ,
    status              VARCHAR(32) NOT NULL,
    CONSTRAINT uq_internal_dlq_delivery
        UNIQUE (event_id, handler_id)
);
~~~

**Field rationale:**

- `event_id` identifies the logical event, generated at publish time; never regenerated per retry.
- `handler_id` distinguishes subscribers/handlers with different replay needs.
- `event_type` and `schema_version` support deserialization and upcasting old events.
- `payload_json` is a **minimal, schema-controlled payload**—never stuff entire JPA entities, HTTP requests, streams, secrets, or stack traces into it.
- `failure_kind` classifies transient vs. permanent; `last_error_code` and `last_error_summary` contain sanitized info to avoid PII leaks.
- `attempts` tracks total attempts; `first_failed_at` and `last_failed_at` support operations and SLAs.
- `next_attempt_at` drives the scheduler; `status` distinguishes retrying, dead, and resolved.
- Unique key on `(event_id, handler_id)` prevents creating multiple dead-letter records for the same delivery. Depending on semantics, add `tenant_id`, partition key, or consumer version to the unique key.

In multi-instance deployments, control **concurrency**: workers claim records via lease/lock, using optimistic locking/versioning or `SELECT ... FOR UPDATE SKIP LOCKED` on PostgreSQL within a short claim transaction. Do not rely on a shared `ConcurrentHashMap` in one JVM as a durable queue.

If payloads are too sensitive or too large, store **IDs + approved metadata** and use an access-controlled snapshot/reference; bear in mind referenced data may change or be deleted before replay.

## 7. Runnable Java 17+ Example: Temporary In-Memory Dead-Letter Store

This example uses **plain Spring Framework** only—no Spring Boot, HTTP server, or database. Its goal is to illustrate **bounded retries, error classification, storing failed event/handler pairs, and replaying an individual handler**.

A Spring event `OrderPaid` is handled by a listener:

- Order **101**: notification sent successfully immediately.
- Order **202**: downstream temporarily disconnected; retried twice, then dead-lettered; once downstream recovers, replay succeeds.
- Order **303**: invalid address; treated as a permanent failure, dead-lettered immediately, and **not blindly replayed**.

The code has deterministic output because execution is synchronous, independent of schedulers, and avoids `Thread.sleep`. **The in-memory store loses data when the JVM exits**; never use it as a production DLQ.

### 7.1. Project Structure

~~~text
internal-dead-letter-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── InternalDeadLetterDemo.java
~~~

`settings.gradle`:

~~~groovy
rootProject.name = 'internal-dead-letter-demo'
~~~

`build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.15'
}

application {
    mainClass = 'demo.InternalDeadLetterDemo'
}
~~~

JDK 17+ and a compatible Gradle version are sufficient to run the demo. Spring Framework 6.2.x has a Java 17 baseline. In a real Spring Boot project, let Boot's dependency management control Spring versions.

### 7.2. Complete Source Code

Save all code into `src/main/java/demo/InternalDeadLetterDemo.java`:

~~~java
package demo;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public class InternalDeadLetterDemo {

    // Small, stable payload; eventId is preserved on replay.
    public record OrderPaid(String eventId, long orderId) {}

    public record DeadLetter(
            OrderPaid event,
            String handlerId,
            int attempts,
            String failureKind,
            String reason) {}

    public static final class TemporaryFailure extends RuntimeException {
        public TemporaryFailure(String message) {
            super(message);
        }
    }

    public static final class PermanentFailure extends RuntimeException {
        public PermanentFailure(String message) {
            super(message);
        }
    }

    // Downstream simulation. Not a real SMTP/API client.
    public static final class DeliveryGateway {
        private boolean recovered = false;

        public void send(OrderPaid event) {
            if (event.orderId() == 202L && !recovered) {
                throw new TemporaryFailure("service unavailable");
            }
            if (event.orderId() == 303L) {
                throw new PermanentFailure("invalid destination");
            }
        }

        public void recover() {
            recovered = true;
        }
    }

    // For single-threaded synchronous demo only: not durable, not concurrent.
    public static final class InMemoryDeadLetterStore {
        private final Map<String, DeadLetter> records =
                new LinkedHashMap<>();

        private String key(String eventId, String handlerId) {
            return eventId + "|" + handlerId;
        }

        public void save(DeadLetter letter) {
            records.put(key(
                    letter.event().eventId(),
                    letter.handlerId()), letter);
        }

        public DeadLetter find(String eventId, String handlerId) {
            return records.get(key(eventId, handlerId));
        }

        public void delete(String eventId, String handlerId) {
            records.remove(key(eventId, handlerId));
        }

        public int size() {
            return records.size();
        }

        public List<String> remainingEventIds() {
            List<String> ids = new ArrayList<>();
            for (DeadLetter letter : records.values()) {
                ids.add(letter.event().eventId());
            }
            return ids;
        }
    }

    public static final class NotificationListener {
        private static final int MAX_ATTEMPTS_PER_RUN = 2;
        private static final String HANDLER_ID = "send-receipt";

        private final DeliveryGateway gateway;
        private final InMemoryDeadLetterStore store;

        public NotificationListener(
                DeliveryGateway gateway,
                InMemoryDeadLetterStore store) {
            this.gateway = gateway;
            this.store = store;
        }

        @EventListener
        public void onOrderPaid(OrderPaid event) {
            deliver(event, 0);
        }

        // In the demo, replay the failed handler directly,
        // do not republish to all listeners.
        public void replay(String eventId) {
            DeadLetter letter = store.find(eventId, HANDLER_ID);
            if (letter == null) {
                throw new IllegalArgumentException(
                        "No dead letter for " + eventId);
            }
            deliver(letter.event(), letter.attempts());
        }

        private void deliver(OrderPaid event, int previousAttempts) {
            for (int localAttempt = 1;
                    localAttempt <= MAX_ATTEMPTS_PER_RUN;
                    localAttempt++) {

                int totalAttempt = previousAttempts + localAttempt;

                try {
                    gateway.send(event);
                    store.delete(event.eventId(), HANDLER_ID);
                    System.out.println(
                            "delivered order=" + event.orderId()
                            + " attempt=" + totalAttempt);
                    return;

                } catch (PermanentFailure ex) {
                    store.save(new DeadLetter(
                            event,
                            HANDLER_ID,
                            totalAttempt,
                            "PERMANENT",
                            ex.getMessage()));

                    System.out.println(
                            "dead-letter order=" + event.orderId()
                            + " attempts=" + totalAttempt
                            + " kind=PERMANENT");
                    return;

                } catch (TemporaryFailure ex) {
                    if (localAttempt == MAX_ATTEMPTS_PER_RUN) {
                        store.save(new DeadLetter(
                                event,
                                HANDLER_ID,
                                totalAttempt,
                                "TRANSIENT",
                                ex.getMessage()));

                        System.out.println(
                                "dead-letter order=" + event.orderId()
                                + " attempts=" + totalAttempt
                                + " kind=TRANSIENT");
                        return;
                    }
                }
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {

        @Bean
        public DeliveryGateway deliveryGateway() {
            return new DeliveryGateway();
        }

        @Bean
        public InMemoryDeadLetterStore deadLetterStore() {
            return new InMemoryDeadLetterStore();
        }

        @Bean
        public NotificationListener notificationListener(
                DeliveryGateway gateway,
                InMemoryDeadLetterStore store) {
            return new NotificationListener(gateway, store);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            NotificationListener listener =
                    context.getBean(NotificationListener.class);
            InMemoryDeadLetterStore deadLetters =
                    context.getBean(InMemoryDeadLetterStore.class);
            DeliveryGateway downstream =
                    context.getBean(DeliveryGateway.class);

            context.publishEvent(new OrderPaid("evt-101", 101L));
            context.publishEvent(new OrderPaid("evt-202", 202L));
            context.publishEvent(new OrderPaid("evt-303", 303L));

            System.out.println("dead-letter count=" + deadLetters.size());

            // Simulate fixing the downstream error and actively replay evt-202.
            downstream.recover();
            listener.replay("evt-202");

            System.out.println(
                    "after replay count=" + deadLetters.size());
            System.out.println(
                    "remaining=" + deadLetters.remainingEventIds());
        }
    }
}
~~~

### 7.3. Running and Exact Program Output

Inside the `internal-dead-letter-demo` directory, with JDK 17+ and Gradle installed:

~~~bash
gradle -q run
~~~

Or use a generated wrapper: `./gradlew -q run` on Linux/macOS, `gradlew.bat -q run` on Windows.

Lines printed by the application itself:

~~~text
delivered order=101 attempt=1
dead-letter order=202 attempts=2 kind=TRANSIENT
dead-letter order=303 attempts=1 kind=PERMANENT
dead-letter count=2
delivered order=202 attempt=3
after replay count=1
remaining=[evt-303]
~~~

**Explanation:**

1. `evt-101` is delivered successfully on the first try. It does not enter the dead-letter store.
2. `evt-202` throws `TemporaryFailure` twice; after the second attempt, the listener saves a record with `eventId=evt-202`, `handlerId=send-receipt`, `attempts=2`, and `failureKind=TRANSIENT`.
3. `evt-303` throws `PermanentFailure` on the very first attempt and is dead-lettered with `attempts=1`. It is not retried because the same input is certain to keep failing per the simulation.
4. Before replay, the store holds two records. After `downstream.recover()`, `listener.replay("evt-202")` retrieves the old event and tries a third time (total attempt=3), succeeds, and removes the record.
5. Exactly one dead letter remains: `evt-303`. This case requires fixing the data/destination before replaying.

**Demo boundaries:** the code intentionally **has no backoff, database transaction, thread pool, distributed lock, durable storage, consumer checkpoint, idempotency marker, or operations API**. Since everything runs synchronously in `main` on a single JVM, `LinkedHashMap` suffices to illustrate state. In production, replace those parts rather than copying the demo verbatim and expecting delivery guarantees.

## 8. Adapting the Pattern for Real Applications: Decouple Delivery from Publisher

A testable design typically consists of these components:

~~~text
Domain service
   |
   +--> publish small event (eventId, aggregateId, type, version)
            |
            +--> Spring listener / adapter
                        |
                        +--> Delivery service
                                |
                                +--> attempt handler
                                +--> classify exception
                                +--> persist retry/dead-letter state
                                +--> metrics / logs
                                |
                                +--> replay worker / operator
~~~

Separating `NotificationListener` from `DeliveryService` keeps the handler from taking on retry, persistence, metrics, and authorization responsibilities. The listener only routes the matching event type to the delivery workflow, while the delivery workflow can be re-executed by a scheduler **without republishing the event to all subscribers**.

In a real product, transactions and persistence should be designed before picking a retry API:

- If the event is non-critical and best-effort suffices, standard sync/async Spring events with logs/metrics can be used, accepting potential job loss.
- If the event is important yet stays in-process, persist a **durable delivery job** at the source and process it with a worker.
- If the event must cross to other services, consider **transactional outbox + message broker** (or another durable queue), rather than relying on in-memory callbacks.
- A durable dead-letter is not just "a list of failed events": it must support claiming, attempt counts, scheduling, replay, auditing, retention, and transactions with source data.

A dead-letter table can be part of the same delivery-job table using a `DEAD` state; a separate physical queue is not always mandatory when the contract is clear.

## 9. Retrying Properly Before Dead-Lettering

### 9.1. Retrying Directly Inside the Listener: Suitable Only for Small Cases

The Section 7 example retries twice back-to-back to keep output deterministic. This is **not a recommended policy** for production network failures, because two immediate retries usually fail the same way and block the publisher.

If the listener is synchronous:

- Inline retries make `publishEvent(...)` return slower.
- If the publisher is inside a transaction, retries extend lock/connection hold times.
- If the callback keeps throwing exceptions, the publisher may receive the error, potentially affecting the transaction depending on the call stack.
- When a dependency is down, many concurrent requests retrying simultaneously can worsen overload.

Therefore, when seconds or minutes of backoff are needed, **persist a work item and let a separate scheduler/worker** handle it; do not call `Thread.sleep` inside a listener.

### 9.2. Backoff, Jitter, and Classification

An illustrative policy:

~~~text
Transient error:
    attempt 1 -> wait 5 seconds + jitter
    attempt 2 -> wait 15 seconds + jitter
    attempt 3 -> wait 45 seconds + jitter
    attempt 4 -> wait 2 minutes + jitter
    attempt 5 -> DEAD

Permanent validation error:
    attempt 1 -> DEAD

Rate limit:
    follow Retry-After when valid,
    otherwise use bounded backoff with rate limiter
~~~

These numbers are **policy examples**, not Spring defaults. In practice, base them on SLAs, dependency behavior, timeouts, throughput, and event validity windows.

Avoid using a single retry loop for every exception. For instance, an invalid email error will not resolve by waiting 30 seconds, while HTTP 503 does not mean a message should be discarded immediately.

### 9.3. Do Not Forget Attempt Budgets During Replay

Distinguish:

- `deliveryAttempts`: actual calls made to the dependency.
- `retryCycles`: worker wakeups.
- `replayAttempts`: operator-initiated retries from the `DEAD` state.

The demo accumulates `attempts` cumulatively. Production can add an attempt history instead of just a counter, though caps are needed to avoid unbounded log growth. Do not let unconditional replays turn into infinite loops.

## 10. Sync, Async, and Limitations of ErrorHandler

### 10.1. Default Sync: Exceptions Can Impact the Publisher

~~~java
@EventListener
public void onOrderPaid(OrderPaid event) {
    downstream.send(event);
}
~~~

This is an illustrative method; `OrderPaid` and `downstream` must be defined. If `downstream.send` throws an unhandled runtime exception and the multicaster uses the default synchronous mode, the exception can propagate back to `publishEvent`. This is **not dead-lettering**: it is simply exception propagation.

### 10.2. Configuring ErrorHandler on the Multicaster

Configuration example:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.SimpleApplicationEventMulticaster;

@Configuration
class EventConfig {

    @Bean(name = "applicationEventMulticaster")
    ApplicationEventMulticaster applicationEventMulticaster() {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();

        multicaster.setErrorHandler(error -> {
            System.err.println(
                    "listener failed: "
                    + error.getClass().getSimpleName());
        });

        return multicaster;
    }
}
~~~

This is an illustrative configuration snippet, not part of the Section 7 program. The bean name must be `applicationEventMulticaster` for the context to use it as the multicaster.

**Do not treat `setErrorHandler(...)` as a complete DLQ** because the `handleError(Throwable)` callback receives an error, **not a standard envelope containing event ID, handler ID, payload, and delivery state**. Simply logging or suppressing can make the publisher think processing succeeded when the side effect never happened. If dead-lettering is needed, persist inside a handler/workflow with full context or build a dedicated adapter.

### 10.3. Async Executor

If `setTaskExecutor(...)` is used, eligible listeners can run on another thread. Consequences:

- The publisher can return **before the listener finishes**.
- Exceptions do not automatically return to the publisher thread; separate tracking for handler/async failures is needed.
- The executor queue can hold events/payloads for a long time, causing memory pressure.
- The publisher's transaction/security/logging ThreadLocals do not transfer automatically.
- Transaction-synchronized listeners may not support async at the multicaster level; Spring 6.1+ provides `ApplicationListener.supportsAsyncExecution()` to express this.

If durable delivery is required, an in-JVM executor **does not replace a durable queue**. A process killed after submission but before execution will lose tasks sitting in the memory queue.

## 11. Transactions, Rollback, and Dead-Lettering: The Easiest Area to Misdesign

### 11.1. Listener Errors Can Roll Back Business Transactions

Suppose:

~~~java
@Transactional
public void capturePayment(Payment payment) {
    paymentRepository.save(payment);
    publisher.publishEvent(
            new PaymentCaptured(payment.getId()));
}
~~~

This is an illustrative snippet requiring `Payment`, repository, Spring proxy transaction, and event type to be defined.

If the `@EventListener` runs synchronously right inside `publishEvent` and throws an unchecked exception, the exception can escape the service call, causing the `@Transactional` interceptor to **mark rollback according to applicable rules**.

Conversely, if the listener catches all errors, logs, and swallows the exception, the transaction can **proceed to commit**. That may be right for an optional notification, yet very dangerous if the listener enforces a mandatory invariant.

**Mandatory design question:** must a failure of this handler cancel the business transaction?

- If **yes**, preserve clear errors so the transaction rolls back; dead-lettering must never silently change the contract to "commit despite failed checks."
- If **no**, decouple secondary side effects from the business transaction, durably record the work to be performed, and process after commit.

### 11.2. Writing Dead Letters in the Rolling-Back Transaction

If a listener throws an error causing transaction A to roll back, and earlier you wrote a DLQ record using **transaction A itself**, the DLQ record can roll back too. Thus a log line saying "saved to DLQ" is not proof the dead letter persisted.

Options to consider:

1. Write the DLQ in **an independent transaction** (e.g., via `REQUIRES_NEW` through a Spring proxy) when you genuinely need to record a failure whose source transaction rolled back. Never accidentally record "event to send" for a business operation that never committed.
2. Use an independent worker/outbox: the business transaction commits the work to be done, and retries/dead-lettering occur in a separate processing transaction.
3. If the business operation rolled back and no valid entity remains, auditing/logging the failure may be preferable to dead-lettering a task that should not continue.

In many cases, **transactional outbox** is the cleanest structure: the same transaction saves the business entity and an outbox work item, and workers only see committed outbox records. Afterward, the worker manages retries/dead-lettering on its own. When the business operation rolls back, **there is no valid outbox record to emit**.

### 11.3. AFTER_COMMIT Is Not Magic

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT)
public void afterCommit(PaymentCaptured event) {
    downstream.call(event);
}
~~~

This snippet runs only when a matching transaction has committed successfully; with default `fallbackExecution=false`, events outside a transaction are skipped. Because the callback runs in the post-commit phase, errors afterward **cannot automatically roll back the commit that already happened**. Yet application events are still **not a durable queue**: if the process dies after commit, before or during the callback, the work can be lost with no record to replay.

For operations needing DB writes in an `AFTER_COMMIT` listener, do not assume old transaction resources will commit new changes. A suitable new transaction or a dedicated worker is required.

### 11.4. Do Not Confuse "Saving Errors" with "Guaranteeing No Lost Events"

A failure can happen across multiple time windows:

~~~text
T1: business commit
T2: listener is invoked
T3: downstream processes successfully
T4: record ACK / delete delivery record
~~~

The application can crash **between any two milestones**. Without a durable work item **before T1 or atomically with T1**, merely catching exceptions at T2 does not close the crash gap before T2. If it crashes after T3 but before T4, retries can **cause duplicate processing**. Therefore, production typically needs **at-least-once delivery + idempotent consumers**, rather than promising end-to-end exactly-once from internal Spring events.

## 12. Designing Safe Replay

Replay is an action **with business side effects**, not just a "retry" button. A workflow can include:

1. Filter dead letters by `handlerId`, time range, error type, and status. Never replay unbounded batches.
2. Investigate the root cause, fix configuration/source data, and evaluate whether the old event is still valid.
3. Check whether `eventType`/`schemaVersion` is compatible with current code; upcast/migrate if needed.
4. Claim records using optimistic locking/leases so two operators cannot replay concurrently.
5. Transition to `REPLAYING` or `RETRY_WAIT` with the original idempotency key.
6. Execute **only the failed handler**; if republishing the whole event, all other handlers must be idempotent.
7. Record success/failure outcomes and audit who ran it, when, and why; distinguish "retry sent" from "side effect succeeded."
8. If it still fails, increment attempts and return to `DEAD` per policy; do not delete failure data just because replay was clicked.

### 12.1. Idempotency

An event can be processed more than once due to retries or crashes. A consumer sending emails, creating invoices, or awarding points must detect already-completed events:

~~~text
idempotency key = eventId + ":" + handlerId

if delivery already SUCCEEDED:
    skip work
else:
    claim and process
    record success durably
~~~

This is a pseudo-workflow; checking and then inserting separately **is not safe enough with multiple workers**. Use unique constraints or atomic claim/insert operations, and consider the side effect's transaction.

For external REST calls, send an idempotency key if supported by the API. If the API lacks support and succeeds before a crash prevents saving the ACK, replay can create duplicate side effects; design reconciliation procedures rather than simply claiming exactly-once.

### 12.2. Do Not Keep Replaying Poison Events

Permanent failures such as invalid schemas, permanently deleted customers, or persistent permission errors require **fixing the root cause**. Otherwise, replaying merely multiplies errors, wastes quota, and obscures the real issue.

### 12.3. Relationship with Access Control and Sensitive Data

A DLQ often holds more sensitive failure data than ordinary logs. Require RBAC for viewing/replaying/deleting, error-message redaction, encryption at rest where required, audit trails, retention policies, and personal data handling procedures. **Do not store full stack traces with tokens/request bodies** in `last_error_summary`.

## 13. Production Implementation: Workers, Claiming, and Result Handling

A database-backed worker can process in cycles:

~~~text
repeat while running:
    claim a bounded batch of due READY/RETRY_WAIT records
    for each claimed job:
        reconstruct versioned event payload
        locate handler by handlerId
        if already processed:
            mark ACKED
        else:
            try side effect with timeout and idempotency key
            on success: durable ACK
            on transient failure: schedule backoff or mark DEAD
            on permanent failure: mark DEAD
    renew/release stale leases and emit metrics
~~~

Implementation notes:

- **Keep claim transactions short**: do not hold a DB lock while waiting 20 seconds on an HTTP call.
- **Time-bounded leases**: a dead worker must not leave a job stuck in `PROCESSING` forever.
- **Bounded memory**: cap batch sizes, queues, concurrency, and payload sizes.
- **Deadlines and backoff**: do not retry infinitely when a dependency is down.
- **Deduplication**: use unique keys on event-handler pairs; handle duplicates and replays safely.
- **Atomic state transitions**: update status and attempt count in the same DB transaction.
- **Handle DLQ storage failures**: if saving a failure fails, report unconfirmed status and alert; never delete work items before persistence succeeds.
- **Kill/restart tests**: restart the worker and verify pending jobs resume.

To simplify, use retry libraries, schedulers, Spring Batch, Spring Integration, or message brokers **when appropriate**. Never confuse a library's features with built-in capabilities of `ApplicationEventPublisher`.

## 14. When Should You Use Spring Integration or a Broker?

**Spring Integration** has message channels, error channels, and message-processing flows; if an application already structures events as integration flows, error-handling flows can route failed messages to a dedicated error channel. This is a **different architecture from** plain Spring `ApplicationEventMulticaster`.

**Kafka/RabbitMQ** provide retry topics/queues, DLT/DLQ, or dead-letter exchanges per their features and configurations. When an application publishes events to a broker via an outbox or adapter, broker-side dead-lettering is the responsibility of **consumers and broker infrastructure**, not an inherent side effect of `@EventListener`.

Selection guide:

| Scale / requirement | Appropriate approach |
| --- | --- |
| Events only for best-effort logging/metrics | Standard Spring events, monitored logs/metrics; accept losing some events |
| Secondary side effects needing in-app retries, moderate volume | Persisted job table + scheduler/worker + dead-letter state |
| Need work persisted with business transaction | Transactional outbox + worker |
| Multiple services subscribing, replay, and retention | Broker with configured delivery/retry/DLQ, plus idempotent consumers |
| Complex integration channel flows within one app | Spring Integration/error channels, storage per durability needs |

You are not forced to deploy Kafka just to use the term "dead letter." Conversely, if losing an event is a severe business risk, **an `ArrayList` or in-process executor queue is not enough**.

## 15. Testing Dead-Letter Handling for Internal Events

A reliable test suite should go through Spring's real event-publishing path and verify the store:

| Test case | Input | What to assert |
| --- | --- | --- |
| Success | Valid event, healthy downstream | Handler runs once, no dead letter |
| Transient error | Recoverable downstream failure | Retried per policy; after budget, one dead letter with attempt count |
| Permanent error | Permanently invalid payload | No futile retries; dead-lettered immediately |
| Replay after fix | Event is `DEAD`, dependency recovered | Handler succeeds; record moves to `RESOLVED`/deleted per policy |
| Replay before fix | Event still invalid | Remains `DEAD`, attempt recorded, record not lost |
| Multiple handlers | Only one handler fails | DLQ keyed by `eventId+handlerId`; succeeded handlers not replayed |
| Duplicate event | Same `eventId+handlerId` received again | No duplicate side effects; uniqueness/idempotency holds |
| Worker crash | Dies between claim and ACK | Lease expires and job is reprocessed without loss |
| DLQ database failure | Persistence fails | Does not report saved; does not wrongly ACK/delete job |
| Transaction rollback | Business transaction does not commit | No delivery job for uncommitted operation, per outbox design |
| AFTER_COMMIT listener fails | Business committed | Do not assume business can be rolled back |
| Startup/restart | JVM stopped and restarted | Durable dead letters remain if using persistent store |
| Security | Unauthorized replay actor | Access denied and properly audited |

### 15.1. Quick Check Using Demo Output

For the Section 7 example, the corresponding assertions are:

~~~text
initial published evt-101 -> 0 DEAD for evt-101
evt-202 -> attempts=2, kind=TRANSIENT
evt-303 -> attempts=1, kind=PERMANENT
dead-letter count before replay = 2
replay evt-202 after recover -> delivered at attempt=3
dead-letter count after replay = 1
remaining eventId = evt-303
~~~

This is an **expected assertion checklist**, not stdout measured by a test runner. The example prints the seven lines in Section 7.3; in a real project, use JUnit and assertions against `InMemoryDeadLetterStore` or the persistent repository.

### 15.2. Flawed Tests That Give False PASS Results

- Calling `NotificationListener.onOrderPaid(...)` directly and concluding Spring event wiring works: this **does not test** bean discovery or the event multicaster.
- Checking only for a `dead-letter` log without reading back the persisted record.
- Calling `Thread.sleep` to wait for async instead of a completion signal with timeout.
- Running tests on `ConcurrentHashMap` and concluding records survive restarts.
- Testing retries without testing duplicates and crash windows.
- Testing business rollback solely by mocking exceptions without checking database state.
- Using a single worker/thread and assuming no race conditions exist across multiple instances.

For integration tests, use a real datasource (H2/Testcontainers depending on scope), publish inside controlled transactions, wait for workers to finish, and inspect state after transactions and restarts. Test external endpoints like SMTP/HTTP via stubs with timeouts and predictable failure scripts.

## 16. Metrics, Alerts, and Operational Runbook

Building a DLQ that nobody monitors only turns "lost work" into "silent backlog." At minimum, you should have:

**Metrics:**

- `dead_letter_total{handler,failure_kind}`: new dead letters by handler and failure kind.
- `dead_letter_backlog{handler,status}`: records currently `DEAD`/`RETRY_WAIT`.
- `dead_letter_oldest_age_seconds`: wait time of the oldest record.
- `delivery_attempt_total{handler,outcome}` and post-retry success rate.
- `delivery_latency_seconds`, queue lag, active workers, worker timeouts.
- `replay_total{actor,outcome}` at aggregate counts; never put personal emails/IDs into metric labels.
- Count of `PROCESSING` records past lease expiration and DB dead-letter persistence failures.

**Runbook:**

1. Receive backlog/age alert exceeding SLA thresholds; distinguish widespread outages from a few poison events.
2. Filter by handler, failure kind, deployment version, and start time.
3. Inspect dependencies, rate limits, schema/migrations, secrets/credentials, and recent deployments.
4. Isolate the handler or lower concurrency if retries are overloading a dependency.
5. Fix the root cause; assess whether event data/versions need updating or resources need restoring.
6. Replay **a small batch** under supervision, comparing success/duplicate/failed counts before expanding.
7. Document root cause, business impact, and decisions to delete/retain dead letters per retention policy.

For errors involving payments, shipping, or customer notifications, establish reconciliation workflows and potentially require approval before bulk replays. Never delete dead letters merely to drive a backlog chart down to zero.

## 17. Common Misconceptions

| Misconception | Reality |
| --- | --- |
| Spring Application Events has a built-in DLQ | No; you must build a store/retry/replay workflow or use other infrastructure |
| `setErrorHandler(...)` automatically persists failed payloads | It only receives `Throwable`; there is no standard event+handler envelope |
| Listener exceptions are always seen by the publisher | Sync may propagate errors; async offers no such guarantee |
| Listener exceptions always cause rollback | Depends on transaction boundaries and error handling; `AFTER_COMMIT` cannot undo commits |
| Catching every exception and saving to DLQ is always safe | Can mask mandatory invariants or swallow severe errors |
| `@TransactionalEventListener(AFTER_COMMIT)` guarantees durable delivery | No; callbacks still run in-JVM and have a crash window |
| In-memory `Map` is a production DLQ | Lost on restart; lacks claiming/leases/RBAC and retention |
| Retrying multiple times guarantees exactly-once processing | Retries can create duplicate side effects; idempotency is required |
| Replay means calling `publishEvent` again to all listeners | Can re-run handlers that already succeeded |
| Writing DLQ inside a rolling-back transaction persists it anyway | The record may roll back with the transaction |
| Error logs alone are enough for replay | Logs may lack event identity, schema version, and required metadata |
| Broker DLQ and application DLQ are the same feature | Features, persistence, and operational ownership differ |
| Attempt limits alone solve retry storms | You also need backoff, jitter, rate limits, concurrency control, and circuit breakers |
| Having a dead-letter table means events can never be lost | Work items must be created atomically before crash windows, confirmed persisted, and ACKed properly |
| Killing a running job and immediately replaying is safe | Claim/lease/idempotency are needed to prevent concurrent execution |

## 18. Practice Exercises

**Exercise 1: Transient retries.** In the demo, change `MAX_ATTEMPTS_PER_RUN` from 2 to 3. Predict the output for order 202 and total attempts on successful replay. Explain why adding one immediate retry does not necessarily improve downstream recovery probability.

**Exercise 2: Poison event.** After publishing `evt-303`, call `listener.replay("evt-303")` without fixing the root cause. Verify the record still exists and attempts increase per policy. Then update the gateway to support a "repair address" action and replay under control.

**Exercise 3: Multiple subscribers.** Add a metrics-recording listener that always succeeds. Why can using `context.publishEvent(event)` to replay a failed event record metrics a second time? Implement deduplication or replay by specific `handlerId`.

**Exercise 4: Durable persistence.** Replace `InMemoryDeadLetterStore` with a JDBC repository having a unique constraint `(event_id, handler_id)`. Write a test that closes and reopens the Spring context, verifying the record survives and can be replayed.

**Exercise 5: Transaction rollback.** Use `TransactionTemplate` to create a business transaction and a pending task. Make the business transaction throw before commit; check whether a DLQ/delivery record created in that transaction rolls back. Propose an outbox when the goal is only emitting events for committed transactions.

**Exercise 6: Concurrent replay.** Simulate two workers claiming `evt-202` simultaneously. Build a unique/delivery lock mechanism with TTL ensuring only one worker processes at a time; check what happens if a worker dies after the side effect but before ACK.

**Exercise 7: Runbook.** Simulate 500 dead letters for an email handler hitting rate-limit errors. Define an alerting policy, replay in small batches, cap concurrency, track success, and classify cases requiring manual intervention.

## 19. Production Readiness Checklist

- [ ] Identified which listeners are **critical** (errors must roll back) and which are **secondary side effects**.
- [ ] Defined `eventId`, `handlerId`, and payload versioning; never dead-letter based solely on log messages.
- [ ] Events are durably persisted **before crash windows that could lose work** if delivery is a business requirement.
- [ ] Defined retry budgets, error classification, backoff/jitter, timeouts, and concurrency limits.
- [ ] Implemented a persistent store, unique constraints, state transitions, and claim/lease if running multiple instances.
- [ ] Clarified transaction boundaries; DLQ records are not rolled back unintentionally.
- [ ] Replay invokes only the failed handler, or all handlers are idempotent with deduplication.
- [ ] Handled duplicates, worker crashes, DLQ DB write failures, and expired records.
- [ ] Payloads/stack traces omit unnecessary secrets/PII; RBAC, auditing, and retention are enforced.
- [ ] Metrics exist for backlog, age, attempts, outcomes, error kinds, and alerts have assigned owners.
- [ ] Tests cover commit/rollback/restart/replay with real storage, not only the in-memory demo.
- [ ] Do not treat in-JVM Spring events as cross-restart delivery guarantees without durable infrastructure.

## 20. References

- Spring Framework 6.2 Javadoc — `ApplicationEventPublisher`, event publishing contract: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/ApplicationEventPublisher.html
- Spring Framework 6.2 Javadoc — `SimpleApplicationEventMulticaster`, `setErrorHandler` and `setTaskExecutor`: https://docs.spring.io/spring-framework/docs/6.2.15/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework Reference 6.2 — Application Events (`@EventListener`): https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Spring Framework Reference 6.2 — Transaction-bound Events and `@TransactionalEventListener`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
- Spring Framework Reference — Transaction propagation and `REQUIRES_NEW`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html
- Spring Integration Reference — Error Handling, error channels: https://docs.spring.io/spring-integration/reference/error-handling.html
- Spring for Apache Kafka Reference — error handlers, dead-letter topics (Kafka listener-specific mechanism): https://docs.spring.io/spring-kafka/reference/kafka/annotation-error-handling.html
- Spring AMQP Reference — RabbitMQ dead-letter exchange/error handling (RabbitMQ-specific mechanism): https://docs.spring.io/spring-amqp/reference/amqp/receiving-messages/async-annotation-driven/error-handling.html
