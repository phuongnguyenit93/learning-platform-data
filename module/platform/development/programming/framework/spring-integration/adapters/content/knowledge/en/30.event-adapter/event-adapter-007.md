# Transaction-Bound Application Events in Spring Integration

## Lesson Objectives

In the **Event Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, we use Spring Application Events to connect components within the same application to `MessageChannel` flows. A common problem is: **the message was published, yet the business operation's transaction eventually rolled back**. If a listener already sent an email, updated an external system, or published a message to Kafka/JMS before commit, those systems may record a change that was never persisted.

**Transaction-bound application events** solve the requirement of **when to run a listener based on transaction state** via Spring Framework's `@TransactionalEventListener`. This lesson focuses on applying it alongside outbound/inbound event adapters, threading impacts, post-commit processing, and reliability limits when interacting with external systems.

After this lesson, you will be able to:

- Distinguish between `@EventListener` and `@TransactionalEventListener`.
- Choose the right phase among `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`.
- Publish events through `ApplicationEventPublishingMessageHandler` inside an active transaction.
- Forward messages into an integration flow **only after commit** using a transactional listener.
- Recognize when `ExecutorChannel`, `@Async`, or a multicaster executor changes the transaction context.
- Test commit/rollback behavior and choose a **transactional outbox** when durable messaging over JMS, AMQP, Kafka, or HTTP is required.

## 1. The Problem: Events Published Before Data Is Committed

Suppose an order-placement service follows this sequence:

~~~text
BEGIN TRANSACTION
  INSERT order
  publish OrderPlaced event
  UPDATE inventory             <-- fails
ROLLBACK
~~~

If a Spring listener calls the email system as soon as `publishEvent(...)` runs, the customer may receive an "order placed successfully" notification even though the whole transaction rolled back.

With a regular `@EventListener` and the default synchronous Spring event multicaster, the listener runs **immediately when the event is published**, inside the caller's transaction if one exists. This annotation does not wait for commit on its own.

~~~mermaid
sequenceDiagram
    participant S as OrderService
    participant DB as Database
    participant P as ApplicationEventPublisher
    participant L as @EventListener
    S->>DB: BEGIN, INSERT order
    S->>P: publish OrderPlaced
    P->>L: Process immediately
    L-->>P: Notification sent
    S->>DB: UPDATE inventory fails
    S->>DB: ROLLBACK
    Note over L,DB: Notification sent externally yet order does not exist
~~~

Simply replacing the appropriate listener with `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` makes Spring register the callback with the current transaction and invoke the listener **once the transaction commits successfully**.

~~~mermaid
sequenceDiagram
    participant S as OrderService
    participant DB as Database
    participant P as ApplicationEventPublisher
    participant L as @TransactionalEventListener
    S->>DB: BEGIN, INSERT order
    S->>P: publish OrderPlaced
    P-->>S: Register callback for transaction
    S->>DB: COMMIT succeeds
    DB-->>L: AFTER_COMMIT
    L->>L: Process OrderPlaced
~~~

**Distinguish two guarantees:** `AFTER_COMMIT` specifies **when the listener is invoked after commit**. It does **not** make the event durably stored; if the process stops between commit completion and listener completion, the task can still be lost.

## 2. How Does @EventListener Differ from @TransactionalEventListener?

| Criterion | `@EventListener` | `@TransactionalEventListener` |
| --- | --- | --- |
| Execution timing | When the Spring multicaster dispatches the event | According to the transaction phase |
| Requires an active transaction? | No | **Yes** by default |
| Without a transaction | Still processes if the event matches | **Ignores the event** by default unless `fallbackExecution` is enabled |
| Runs only after commit | No | Use `phase = AFTER_COMMIT` |
| When transaction rolls back | May have already executed before rollback | `AFTER_COMMIT` does not run; `AFTER_ROLLBACK` runs |
| Durable delivery across process crashes | No | No |
| Used for | Observation, in-app handling, tasks independent of commit | Actions depending on transaction outcome |

Example of two listeners receiving the same business payload:

~~~java
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderListeners {

    @EventListener
    public void onPublished(OrderPlaced event) {
        System.out.println("Event observed now: " + event.orderId());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onCommitted(OrderPlaced event) {
        System.out.println("Order committed: " + event.orderId());
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRolledBack(OrderPlaced event) {
        System.out.println("Order rolled back: " + event.orderId());
    }
}
~~~

On a successful transaction, `onPublished` runs during publication; `onCommitted` runs after commit; `onRolledBack` does not run. If the transaction rolls back, `onCommitted` does not run while `onRolledBack` runs. This example assumes the event is published **while a transaction is actually active** and Spring uses standard transaction context.

## 3. The Four Transaction Phases

`@TransactionalEventListener` has a `phase` attribute of enum `org.springframework.transaction.event.TransactionPhase`.

| Phase | When it runs | Suitable work | Cautions |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Before commit completes | Additional checks, state sync that must accompany the transaction | Transaction **can still roll back** afterward; do not send irreversible side effects |
| `AFTER_COMMIT` | After transaction commits successfully | Trigger notifications, kick off subsequent processing | Side effects can fail after primary data is already committed |
| `AFTER_ROLLBACK` | After transaction rolls back | Record cancellation, release appropriate external resources | Cannot assume data written in the transaction exists |
| `AFTER_COMPLETION` | After transaction completes, commit **or** rollback | Cleanup or telemetry applicable to either outcome | Cannot tell commit apart from rollback solely from callback invocation |

The default `phase` is **`AFTER_COMMIT`**. Thus the two annotations below are equivalent in phase:

~~~java
@TransactionalEventListener
public void afterCommitA(OrderPlaced event) {
    // ...
}

@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterCommitB(OrderPlaced event) {
    // ...
}
~~~

In the snippet above, if **both** listeners are registered, one committed event triggers both. In practice, register only the listeners actually needed.

### BEFORE_COMMIT Does Not Mean "Guaranteed to Commit"

A `BEFORE_COMMIT` listener can run, and then the commit can still fail due to DB constraints or another callback. If the listener sends an email in this phase, that email cannot be rolled back with the database. Conversely, an exception from a listener running before commit can prevent the transaction from completing; decide clearly which failures should block the main business operation.

### AFTER_COMMIT Does Not Mean Starting a New Transaction

Spring warns that after commit or rollback, transaction resources such as connections/sessions may still be bound to the thread during the callback phase. If a listener tries to write to the database at this point, the operation may "participate" in the old resource context yet have **no subsequent commit** to ensure persistence.

To write an audit record, update a table, or run an independent DB operation after commit, invoke another bean with a method that opens a **new transaction** via `Propagation.REQUIRES_NEW`. See the example in Section 7.

## 4. Example: Outbound Event Adapter Publishing an Event Inside a Transaction

Problem: a service saves an order via JDBC and publishes `OrderPlaced` to Spring listeners. The notification listener must run only after the DB write transaction commits.

### 4.1. Dependencies and Schema

With Spring Boot managing compatible dependency versions:

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-event")
    implementation("org.springframework.boot:spring-boot-starter-jdbc")
    runtimeOnly("com.h2database:h2")
}
~~~

The application needs a configured `DataSource` and JDBC transaction manager; in a standard Spring Boot JDBC project, this configuration is automated when a datasource is present.

Illustrative schema (H2):

~~~sql
CREATE TABLE orders (
    order_id VARCHAR(80) PRIMARY KEY,
    amount DECIMAL(18, 2) NOT NULL
);
~~~

### 4.2. Defining the Business Event

`OrderPlaced.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;

public record OrderPlaced(
        String orderId,
        BigDecimal amount,
        Instant occurredAt) {
}
~~~

This is a business record, not extending `ApplicationEvent`. Spring supports publishing POJOs as application events; listeners can accept `OrderPlaced` directly when the outbound adapter enables payload publishing mode.

### 4.3. Outbound Event Adapter with DirectChannel

`OrderEventIntegrationConfig.java`:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.event.outbound.ApplicationEventPublishingMessageHandler;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class OrderEventIntegrationConfig {

    @Bean
    public MessageChannel orderEvents() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "orderEvents")
    public ApplicationEventPublishingMessageHandler orderEventPublisher() {
        var handler = new ApplicationEventPublishingMessageHandler();
        handler.setPublishPayload(true);
        return handler;
    }
}
~~~

`DirectChannel` invokes the handler on the **sender's thread** by default. Therefore, when the service calls `orderEvents.send(...)` inside a transaction, `ApplicationEventPublishingMessageHandler` publishes `OrderPlaced` **on the same thread** holding the transaction context. `@TransactionalEventListener` can then register its callback with that transaction.

`setPublishPayload(true)` is also crucial: for the `OrderPlaced` record, it ensures a listener declaring an `OrderPlaced` parameter receives the expected event type. If left at default `false`, the outbound handler publishes a `MessagingEvent` wrapping `Message<OrderPlaced>`; in that case the `OrderPlaced` listener in this lesson would not be invoked as intended.

### 4.4. Service Writing to the Database and Sending the Message

`OrderService.java`:

~~~java
package com.example.orders;

import java.math.BigDecimal;
import java.time.Instant;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    private final JdbcTemplate jdbc;
    private final MessageChannel orderEvents;

    public OrderService(
            JdbcTemplate jdbc,
            @Qualifier("orderEvents") MessageChannel orderEvents) {
        this.jdbc = jdbc;
        this.orderEvents = orderEvents;
    }

    @Transactional
    public void placeOrder(String orderId, BigDecimal amount) {
        insertAndPublish(orderId, amount);
    }

    @Transactional
    public void placeOrderThenFail(String orderId, BigDecimal amount) {
        insertAndPublish(orderId, amount);
        throw new IllegalStateException("Simulated failure after publish");
    }

    private void insertAndPublish(String orderId, BigDecimal amount) {
        jdbc.update(
                "INSERT INTO orders (order_id, amount) VALUES (?, ?)",
                orderId,
                amount);

        var message = MessageBuilder
                .withPayload(new OrderPlaced(
                        orderId, amount, Instant.now()))
                .setHeader("correlationId", orderId)
                .build();

        if (!orderEvents.send(message)) {
            throw new IllegalStateException(
                    "Cannot publish OrderPlaced: " + orderId);
        }
    }
}
~~~

Call the two public methods `placeOrder(...)` and `placeOrderThenFail(...)` **through a Spring-managed bean** (do not instantiate with `new`, and do not self-invoke from another method on the same bean expecting the transaction proxy to apply). For example, use `OrderService` injected by Spring into a controller or test.

With `placeOrder("ORD-01", new BigDecimal("120.50"))`:

1. `@Transactional` opens a JDBC transaction.
2. `INSERT` writes the order within the active transaction.
3. The service sends `Message<OrderPlaced>` into `DirectChannel`.
4. The outbound handler publishes `OrderPlaced` via `ApplicationEventPublisher`.
5. `@TransactionalEventListener(AFTER_COMMIT)` registers its callback.
6. The service returns; the transaction manager commits, and then the `AFTER_COMMIT` listener runs.

With `placeOrderThenFail("ORD-02", ...)`, the runtime exception causes the transaction to roll back. The `AFTER_COMMIT` listener does **not** run for `ORD-02`; the `AFTER_ROLLBACK` listener can run.

**Note on headers:** `correlationId` in the message is not automatically included in `OrderPlaced` when `publishPayload=true` is enabled. If Spring consumers need a correlation ID for auditing, add it to the event contract or use `MessagingEvent` mode with listeners accepting the corresponding type. This is a **payload mapping** decision, independent of the transaction phase.

### 4.5. Post-Commit Listeners

`OrderPlacedListeners.java`:

~~~java
package com.example.orders;

import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderPlacedListeners {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onSuccess(OrderPlaced event) {
        System.out.println(
                "Committed order: " + event.orderId());
        // Real implementation example: trigger notification after commit.
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
    public void onRollback(OrderPlaced event) {
        System.out.println(
                "Rolled back order: " + event.orderId());
    }
}
~~~

The example uses logging to make phases easy to observe; when moving to an email system, HTTP, or a message broker, add retries, monitoring, and post-commit failure handling.

## 5. Inbound Flow: Feeding Messages into Spring Integration **After Commit**

There is an important difference between "Spring Integration receives an application event" and "Spring Integration only receives committed events".

`ApplicationEventListeningMessageProducer` is the **inbound event adapter**. It receives Spring application events from the multicaster and sends messages to an output channel. However, this adapter **does not wait for transaction commit on its own**. If an event is published inside a transaction, the inbound adapter by default can forward the message immediately at publish time.

~~~mermaid
flowchart TD
    S["Transactional Service"] --> P["ApplicationEventPublisher"]
    P --> D["ApplicationEventListeningMessageProducer"]
    D --> R["rawEvents channel"]
    R --> H["Integration handler runs before commit"]
    P --> T["@TransactionalEventListener AFTER_COMMIT"]
    T --> C["committedEvents channel"]
    C --> B["Integration handler runs after commit"]
~~~

If downstream must execute only when the transaction commits, use a **transactional event listener as a bridge** to a message channel:

`CommittedOrderFlowConfig.java`:

~~~java
package com.example.orders;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.MessageChannel;

@Configuration
public class CommittedOrderFlowConfig {

    @Bean
    public MessageChannel committedOrderEvents() {
        return new DirectChannel();
    }
}
~~~

`CommittedOrderForwarder.java`:

~~~java
package com.example.orders;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class CommittedOrderForwarder {

    private final MessageChannel committedOrderEvents;

    public CommittedOrderForwarder(
            @Qualifier("committedOrderEvents") MessageChannel channel) {
        this.committedOrderEvents = channel;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void forward(OrderPlaced event) {
        if (!committedOrderEvents.send(
                MessageBuilder.withPayload(event).build())) {
            throw new IllegalStateException(
                    "Failed to forward committed order");
        }
    }
}
~~~

`CommittedOrderConsumer.java`:

~~~java
package com.example.orders;

import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class CommittedOrderConsumer {

    @ServiceActivator(inputChannel = "committedOrderEvents")
    public void handle(OrderPlaced event) {
        System.out.println(
                "Integration flow after commit: " + event.orderId());
    }
}
~~~

Result:

- The service publishes the event before commit to register the callback.
- Only after commit succeeds does `CommittedOrderForwarder` send a `Message<OrderPlaced>` into the channel.
- `CommittedOrderConsumer` executes under Spring Integration's processing model; at this point, the original transaction has already committed.

This is a clean structure when you want to process business events using `ServiceActivator`, `Transformer`, `Router`, or HTTP/JMS/Kafka outbound adapters **after commit**.

**Do not simultaneously configure an inbound `ApplicationEventListeningMessageProducer` listening for the same `OrderPlaced` and pushing straight into `committedOrderEvents`**, because that inbound branch will bypass the post-commit rule and run as soon as the event is published.

## 6. Why Is Threading the Decisive Factor?

With standard **imperative transactions** (JDBC/JPA), Spring holds transaction context in `ThreadLocal`. `@TransactionalEventListener` registers when the event is published on a thread with an active transaction.

Correct example:

~~~text
Thread A:
  @Transactional
    INSERT order
    DirectChannel.send(...)
      -> ApplicationEventPublishingMessageHandler
      -> publishEvent(OrderPlaced)
      -> register AFTER_COMMIT callback
    COMMIT
    callback runs AFTER_COMMIT
~~~

Example at risk of failing:

~~~text
Thread A (has transaction):
  @Transactional
    INSERT order
    ExecutorChannel.send(message)
    COMMIT

Thread B (does not inherit transaction ThreadLocal):
  ApplicationEventPublishingMessageHandler
    -> publishEvent(OrderPlaced)
    -> @TransactionalEventListener sees no transaction
    -> skips event by default
~~~

Even if the worker runs before Thread A commits, Thread B still does not automatically possess Thread A's transaction context. Hence, **simply replacing `DirectChannel` with `ExecutorChannel` before the event publisher** can prevent post-commit listeners from being called.

| Configuration | Context when publishing event | Ability to register AFTER_COMMIT |
| --- | --- | --- |
| `@Transactional` → `DirectChannel` → outbound handler | Same thread, same imperative transaction | Yes, if a transaction is active |
| `@Transactional` → `ExecutorChannel` → outbound handler | Different executor thread | Typically does not see the original transaction |
| `@Transactional` → calling `ApplicationEventPublisher` directly | Same thread | Yes |
| Event published after transactional method ends | Original transaction no longer exists | Cannot register listener by default |
| Multicaster using an executor | Depends on listener type | Transactional listeners must be evaluated separately; do not assume all listeners are async |

Since **Spring Framework 6.1**, `TransactionalApplicationListener` is an example of a listener declaring that it does not support async execution scheduled by the multicaster; **registering the transaction callback** still needs to be bound to the publishing thread. Placing `@Async` on the listener method itself is another matter: its body can be offloaded to an executor **after the phase has occurred**, at which point the old transaction context is no longer present.

**Design principle:** publish transaction-bound events on the synchronous path first, and only then offload post-commit processing to an executor or message broker if needed.

## 7. Saving to the Database After AFTER_COMMIT: REQUIRES_NEW Is Needed

Suppose after an order succeeds, you want to insert a record into `notification_audit`. Extract the DB write into another Spring bean that opens a new transaction:

~~~java
package com.example.orders;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NotificationAuditService {

    private final JdbcTemplate jdbc;

    public NotificationAuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void record(String orderId) {
        jdbc.update(
                "INSERT INTO notification_audit(order_id) VALUES (?)",
                orderId);
    }
}
~~~

With an example schema:

~~~sql
CREATE TABLE notification_audit (
    order_id VARCHAR(80) PRIMARY KEY
);
~~~

Listener calling that bean:

~~~java
@Component
public class NotificationAuditListener {

    private final NotificationAuditService audit;

    public NotificationAuditListener(NotificationAuditService audit) {
        this.audit = audit;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderPlaced event) {
        audit.record(event.orderId());
    }
}
~~~

`NotificationAuditService` and `NotificationAuditListener` live in two separate beans so the `record(...)` call goes through Spring's transaction-managing proxy. `REQUIRES_NEW` creates an independent transaction with its own commit/rollback; a subsequent audit write failure **cannot roll back the already-committed order**.

The snippet above assumes `Component`, `TransactionalEventListener`, and `TransactionPhase` are imported as in earlier examples. In production, decide how failed audit writes are recorded and retried; `REQUIRES_NEW` does not automatically provide retries or durable delivery.

## 8. fallbackExecution: When Events Are Outside a Transaction

By default, `@TransactionalEventListener` **does not process** events published outside a matching transaction.

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    // Does not run if there is no transaction to register a callback.
}
~~~

If you want the listener to also handle cases with no transaction:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void onCommittedOrFallback(OrderPlaced event) {
    // When a transaction exists: follows AFTER_COMMIT.
    // When no transaction exists: executes immediately via fallback branch.
}
~~~

**Semantic warning:** with `fallbackExecution=true`, "AFTER_COMMIT" no longer means **every execution happens after a database commit**. When there is no transaction, there is no commit to wait for. Therefore, do not enable fallback if the business contract strictly requires an actual commit before processing.

In tests, standalone scripts, or calls from non-`@Transactional` components, the listener "not receiving the event" may actually be the intended default behavior. Before enabling fallback, investigate why the event was not published inside a transaction as expected.

## 9. @Async and ApplicationEventMulticaster: Where Should You Split?

There are three places where threads can switch, each with different transactional implications.

### Before Publishing the Event

~~~text
@Transactional service
    -> ExecutorChannel
        -> outbound publisher
            -> @TransactionalEventListener
~~~

This risks losing the transaction context. Avoid this if the goal is to bind the callback to the service's transaction.

### Inside the Spring Multicaster

`SimpleApplicationEventMulticaster` can accept a `TaskExecutor`, allowing eligible listeners to run asynchronously. However, transactional listeners have transaction registration constraints; do not rely on a global executor to "automatically run `@TransactionalEventListener` after commit".

Furthermore, configuring `applicationEventMulticaster` alters the behavior of many listeners in the context. In applications with listeners handling Spring lifecycle events, assess the broad impact before enabling async across the entire multicaster.

### After Commit

If a post-commit listener needs to make a slow HTTP call or send an email, you can move **its execution body** to `@Async`:

~~~java
@Configuration
@EnableAsync
public class AsyncNotificationConfig {

    @Bean("notificationExecutor")
    public ThreadPoolTaskExecutor notificationExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("notification-");
        return executor;
    }
}
~~~

~~~java
@Component
public class AsyncOrderNotificationListener {

    @Async("notificationExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void notifyCustomer(OrderPlaced event) {
        System.out.println(
                "Sending notification for " + event.orderId()
                + " on " + Thread.currentThread().getName());
    }
}
~~~

In this example, import `Configuration`, `Bean`, `EnableAsync`, `ThreadPoolTaskExecutor`, `Component`, `Async`, `TransactionalEventListener`, and `TransactionPhase` accordingly. The listener registers with the transaction at publish time, while the `@Async` body runs on the executor once the post-commit callback fires.

Consequences:

- The caller does not wait for the async listener body to finish.
- The publishing thread's transaction context is not carried over to the worker.
- Errors in a `void @Async` method must be handled/observed via logging, `AsyncUncaughtExceptionHandler`, or another business mechanism.
- If the queue saturates, the task may be rejected right when dispatched after commit; the order remains committed.

For critical notifications, write an **outbox** record in the same transaction as the order and let an independent worker send it after commit.

## 10. After Commit Does Not Mean Message Delivery Succeeded

Several scenarios must be distinguished:

| Scenario | Primary DB state | Event/secondary task state |
| --- | --- | --- |
| Transaction rolls back before commit | Rolled back | `AFTER_COMMIT` does not run |
| Commit succeeds, listener sends HTTP successfully | Committed | Secondary task completed |
| Commit succeeds, listener HTTP call times out | Committed | Secondary task failed; cannot auto-rollback primary transaction |
| Commit succeeds, process crashes before listener | Committed | In-memory event may be lost |
| Commit succeeds, async listener scheduled then process dies | Committed | Queued or in-flight task may be lost |
| Commit succeeds, listener sends to Kafka without ack yet | Committed | Requires transport-specific confirmation, retries, idempotency |

In particular, an exception in a post-commit listener **cannot reach back and undo an already-committed transaction**. Depending on callback/lifecycle details and exception type, the exception may still appear on the thread handling commit or be logged elsewhere. Do not interpret an exception from `placeOrder(...)` as proof that the database rolled back if the failure occurred after commit.

### Transactional Outbox for External Connections

When reliable event delivery to Kafka, JMS, AMQP, HTTP, or external services is needed, the **transactional outbox** pattern is usually more appropriate than relying solely on `@TransactionalEventListener`:

~~~mermaid
flowchart LR
    S["@Transactional OrderService"] --> D["Database: orders"]
    S --> O["Database: outbox_events"]
    D ---|"Same DB transaction"| O
    O --> P["Poller / CDC / Relay"]
    P --> B["Kafka / JMS / AMQP / HTTP"]
    B --> C["Consumer"]
~~~

Steps:

1. In the **same database transaction**, write the business record to `orders` and the event to send to `outbox_events`.
2. Only after the transaction commits does an independent poller, CDC process, or relay read committed outbox rows.
3. The relay sends the event through the appropriate adapter, tracks confirmation from the target system, and updates the send status.
4. If the relay or process dies, the outbox record remains available for retry.
5. Consumers may receive duplicates due to retries, so enforce idempotency via `eventId` or a business key.

`@TransactionalEventListener(AFTER_COMMIT)` can be used as a **wake-up signal for the relay to reduce latency**, but never as the sole data source; the relay must still scan the outbox to recover missed events.

## 11. Transaction-Bound Listeners with Reactive Transactions

The earlier examples use Spring JDBC/JPA and **imperative transactions** backed by `ThreadLocal`.

Since **Spring Framework 6.1**, `@TransactionalEventListener` also supports **reactive transactions**. However, a reactive transaction is carried in the **Reactor Context** rather than `ThreadLocal`; simply calling `ApplicationEventPublisher.publishEvent(...)` does not inform listeners of the active reactive transaction.

For reactive flows:

- Use the Spring-supported mechanism to bind the **transaction context to the event source**.
- Spring provides `org.springframework.transaction.reactive.TransactionalEventPublisher` to support publishing events inside reactive transactions.
- Ensure publishing belongs to the same transactional `Mono`/`Flux` chain; do not arbitrarily call `subscribe()` to fork a chain and expect the transaction to stay attached.
- Verify the Spring Framework version, transaction manager, and APIs in use; the imperative example based on `DirectChannel` in Section 4 cannot be copied verbatim into reactive transactions.

Conceptual flow:

~~~text
Reactive transaction (Reactor Context)
  -> reactive data write
  -> TransactionalEventPublisher (attaches context to event)
  -> transaction-bound listener
  -> phase-based handling
~~~

Whether reactive or imperative, transaction phases still do not provide durable delivery to external systems.

## 12. Testing Commit and Rollback

Tests should assert **actual transaction-dependent behavior**, not merely that `publishEvent(...)` returned without error.

For the `OrderService` example in Section 4:

| Test case | Action | What to verify |
| --- | --- | --- |
| T1 — Commit | `placeOrder("ORD-01", ...)` | Order exists in DB; `AFTER_COMMIT` listener receives once; `AFTER_ROLLBACK` does not |
| T2 — Rollback | `placeOrderThenFail("ORD-02", ...)` | Order does not exist in DB; `AFTER_COMMIT` does not receive; `AFTER_ROLLBACK` receives once |
| T3 — No transaction | Call `publishEvent(new OrderPlaced(...))` outside any transaction | Default transaction-bound listener does not receive it |
| T4 — Fallback | Enable `fallbackExecution=true` and publish outside a transaction | Listener receives immediately via fallback branch |
| T5 — Thread boundary | Switch `orderEvents` to `ExecutorChannel` before publisher | Verify the transaction callback is no longer registered with the original transaction as expected |
| T6 — After commit | Forward event to `committedOrderEvents` | Service activator runs only after commit and does not run on rollback |
| T7 — Post-commit failure | Cause secondary task to fail | Order remains committed; failure must be handled by the post-commit mechanism |

In Spring tests, **test-level `@Transactional` rolls back by default**. Therefore, calling `placeOrder(...)` inside an uncommitted test transaction can keep `AFTER_COMMIT` from running even when the code is correct. To test properly:

- Use `TransactionTemplate` and let the transaction finish explicitly.
- Or with Spring TestContext, use `TestTransaction.flagForCommit()` / `TestTransaction.end()` at the right point.
- Use a probe listener that counts events and stores event IDs in test memory; assert after the transaction completes.
- For async listeners, use `CountDownLatch`/timed condition waits instead of relying solely on `Thread.sleep`.

Illustrative test idea using `TransactionTemplate`:

~~~java
import java.math.BigDecimal;
import org.springframework.transaction.support.TransactionTemplate;

// Inside test method, with transactionTemplate, publisher, and probe injected.
transactionTemplate.executeWithoutResult(status -> {
    publisher.publishEvent(new OrderPlaced(
            "ORD-T1", new BigDecimal("12.00"), java.time.Instant.now()));
    // AFTER_COMMIT probe has not received ORD-T1 inside this block yet.
});

// When executeWithoutResult returns after successful commit:
// AFTER_COMMIT probe has been invoked in the synchronous listener case.
~~~

The snippet above illustrates **callback timing**; DB verification for the service example should sit in a dedicated integration test with a `DataSource`. Do not share one listener counter across parallel tests without thread safety or proper resets.

### Useful Logs for Diagnosis

Log these fields: `orderId`/`eventId`, `phase`, `threadName`, publish timestamp, commit/rollback outcome, listener execution timestamp, and external adapter send result. If the listener does not run, check in order:

1. Did Spring register the listener bean and does the event type match?
2. Was the event published **while a transaction was active**?
3. Was `@Transactional` actually applied through a Spring proxy?
4. Was the event switched to another thread **before publishing**?
5. Is `fallbackExecution` enabled or disabled?
6. Is the listener expecting `OrderPlaced` or `MessagingEvent` based on `publishPayload`?
7. Did a rollback, commit failure, or uncommitted test transaction occur?

## 13. Practical Exercises

**Exercise 1 — Compare phases:** Build four listeners for `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. Use `placeOrder(...)` and `placeOrderThenFail(...)` to record which callbacks execute in each case. Explain why `BEFORE_COMMIT` is not a valid point for guaranteed email delivery.

**Exercise 2 — Post-commit bridge:** Modify the example so `CommittedOrderForwarder` sends `Message<OrderPlaced>` into an integration flow containing a transformer, router, and HTTP outbound adapter. Ensure the flow does not run when the transaction rolls back.

**Exercise 3 — Threading:** Replace `DirectChannel` before the outbound publisher with `ExecutorChannel`. Observe `TransactionSynchronizationManager.isActualTransactionActive()` when the publisher emits the event and explain the result. Then restore `DirectChannel` and move async execution only to the **post-commit channel**.

**Exercise 4 — Writing audit:** Write `notification_audit` using `REQUIRES_NEW` after commit; induce a failure in the audit write and observe why the primary order row is not rolled back.

**Exercise 5 — Outbox:** Create `outbox_events(event_id, aggregate_id, event_type, payload, created_at, published_at)`. Write the event to the outbox in the same transaction as the order, and use a Spring Integration poller plus Kafka/JMS/AMQP adapter to publish it. Describe retry and deduplication strategies by `event_id`.

## References

- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).
- [Spring Framework API — TransactionalEventListener](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html).
- [Spring Framework API — TransactionPhase](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/event/TransactionPhase.html).
- [Spring Integration — Spring ApplicationEvent Support](https://docs.spring.io/spring-integration/reference/event.html).
- [Spring Integration — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html).
