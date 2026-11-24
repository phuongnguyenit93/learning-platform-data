# Publishing Events After Completing a State Change

When a business operation changes state, the event should describe **a state transition that has actually occurred**. Therefore, the application must update the state first, verify that the transition is valid and that a change actually occurred, and only then publish the corresponding event.

In Spring Framework, `ApplicationEventPublisher.publishEvent(...)` passes an object to the listener system in the ApplicationContext. This call does not inherently understand business transactions or wait for a database commit. If state is persisted in a database within a transaction, you must distinguish when code modifies the entity, when SQL is flushed, and when the transaction commits. When listeners must run after commit, use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` or publish the event from a coordinating layer after the transactional call completes.

## 1. Principle: Events Must Reflect Changes That Have Happened

Suppose an order transitions from `PENDING` to `PAID`. An appropriate event is `OrderStatusChanged`, containing which order changed, its previous status, and its new status.

Logical processing flow:

1. Read the current state from the authoritative data source.
2. Validate that the transition is allowed by business rules.
3. If the new status equals the current status, finish without publishing an event.
4. Perform the state change.
5. Persist the change within the business transaction boundary.
6. Publish or dispatch the event at a time matching consistency requirements.
7. Listeners handle supporting tasks such as auditing, projection updates, or sending notifications.

The core rule is **do not publish a "state changed" event before the transition has actually been accepted**. If validation fails, the entity did not change, or the transaction rolls back, the system must not mislead listeners into thinking the new state is in effect.

### Commands and Events Have Different Meanings

- A command is a request to perform an action, such as `ChangeOrderStatus`.
- An event is an occurrence that has already happened, such as `OrderStatusChanged`.

A command can be rejected because the current state does not allow the transition. An event should only be published after business rules accept the transition and the state has been updated according to the data model.

Event names typically use the past tense or express an outcome: `OrderPaid`, `OrderStatusChanged`, `AccountSuspended`. Command names express intent: `PayOrder`, `ChangeOrderStatus`, `SuspendAccount`.

## 2. "State Changed" and "Committed" Are Not the Same

For in-memory data, an assignment statement can make the new state immediately visible on the object. For database data, there are several distinct milestones:

| Milestone | What Has Happened? | Can We Assert the Transaction Succeeded? |
|---|---|---|
| Modifying object/entity | The value in the Java object has changed | Not yet |
| Calling `repository.save(...)` | Spring Data has accepted the save request; the entity may be managed by the persistence context | Not yet |
| SQL flush | SQL has been sent to the database within the transaction | Not yet |
| Transaction commit | The database confirms the transaction completed according to the transaction manager | Yes, for that transaction |
| `AFTER_COMMIT` listener runs | The listener is invoked after the transaction commits successfully | The original transaction has committed |

A common mistake is thinking `repository.save()` or `saveAndFlush()` means commit. Inside an active transaction, flush only synchronizes changes to the database; the transaction can still roll back afterward.

Example:

~~~java
@Transactional
public void markPaid(String orderId) {
    Order order = repository.findById(orderId).orElseThrow();
    order.markPaid();

    repository.saveAndFlush(order);
    publisher.publishEvent(new OrderStatusChanged(orderId, "PENDING", "PAID"));
    // The transaction has not committed yet here.
}
~~~

The snippet above calls `publishEvent` after the entity changes and SQL may have flushed, yet a regular synchronous `@EventListener` can still run before commit. If the transaction later rolls back, the listener has observed an event describing a state that was never durably saved.

Therefore, choose the timing based on what listeners need to know: whether they only need to know the object changed in the current flow, or must be certain the database committed.

## 3. Publishing Events After In-Memory Changes

For an operation that does not use a database transaction, you can update the state first and publish the event right afterward. The following example uses an in-memory store to illustrate the proper sequence of operations:

~~~java
package com.example.events;

import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.context.annotation.Bean;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;
import org.springframework.stereotype.Service;

@SpringBootApplication
public class StateChangeEventDemo {
    public static void main(String[] args) {
        SpringApplication.run(StateChangeEventDemo.class, args);
    }

    @Bean
    CommandLineRunner demo(OrderService service) {
        return args -> {
            service.register("O-100", "PENDING");
            service.changeStatus("O-100", "PAID");
            service.changeStatus("O-100", "PAID");
        };
    }
}

record OrderStatusChanged(
        String orderId,
        String previousStatus,
        String newStatus
) {}

@Service
class OrderService {
    private final Map<String, String> statuses = new ConcurrentHashMap<>();
    private final ApplicationEventPublisher publisher;

    OrderService(ApplicationEventPublisher publisher) {
        this.publisher = publisher;
    }

    public void register(String orderId, String initialStatus) {
        statuses.put(orderId, initialStatus);
    }

    public synchronized void changeStatus(String orderId, String newStatus) {
        String previousStatus = statuses.get(orderId);

        if (previousStatus == null) {
            throw new IllegalArgumentException("Unknown order: " + orderId);
        }

        if (newStatus == null) {
            throw new IllegalArgumentException("newStatus must not be null");
        }

        if (previousStatus.equals(newStatus)) {
            System.out.println("Service: no state change for " + orderId);
            return;
        }

        // Complete the state change before publishing.
        statuses.put(orderId, newStatus);

        publisher.publishEvent(new OrderStatusChanged(
                orderId,
                previousStatus,
                newStatus
        ));

        System.out.println(
                "Service: status is now " + statuses.get(orderId)
        );
    }
}

@Component
class OrderStatusListener {
    @EventListener
    public void onStatusChanged(OrderStatusChanged event) {
        System.out.println(
                "Listener: " + event.orderId()
                        + " " + event.previousStatus()
                        + " -> " + event.newStatus()
        );
    }
}
~~~

Output produced by the example:

~~~text
Listener: O-100 PENDING -> PAID
Service: status is now PAID
Service: no state change for O-100
~~~

Explanation:

1. The service registers the order in the `PENDING` state.
2. The transition to `PAID` updates the map first, then calls `publishEvent`.
3. The listener receives a snapshot containing the previous and new statuses.
4. Because of the default synchronous multicaster, the listener finishes before the service's next log line.
5. The second call requests status `PAID` when the current status is already `PAID`; the service does not publish the event again.

This example runs standalone with Java 17+ and the `spring-boot-starter` dependency. You can run it with the Gradle Wrapper:

~~~bash
./gradlew bootRun
~~~

On Windows PowerShell:

~~~powershell
.\gradlew.bat bootRun
~~~

This is an example of in-memory object update ordering. `ConcurrentHashMap` does not provide database transactions, durable persistence, or protection for a multi-step transition like a real aggregate. The `changeStatus` method is synchronized so reading state, checking for a no-op, and updating occur sequentially in this simple example. In a database-backed system, use transactions and post-commit mechanisms when listeners depend on committed state.

## 4. Using @TransactionalEventListener to Run Listeners After Commit

When state changes are persisted in a database, a common pattern is publishing the event inside the transaction after the aggregate has changed, then using `@TransactionalEventListener` to defer the listener to the appropriate phase.

The snippet below is a fragment assuming the project already has an `Order` entity, `OrderRepository`, `OrderStatus` enum, transaction manager, and the simple `OrderStatusChanged` record from the previous example. Those domain types are omitted to focus on the transaction boundary:

~~~java
@Service
class OrderService {
    private final OrderRepository repository;
    private final ApplicationEventPublisher publisher;

    OrderService(
            OrderRepository repository,
            ApplicationEventPublisher publisher
    ) {
        this.repository = repository;
        this.publisher = publisher;
    }

    @Transactional
    public void changeStatus(String orderId, OrderStatus newStatus) {
        Order order = repository.findById(orderId)
                .orElseThrow(() -> new IllegalArgumentException(
                        "Unknown order: " + orderId
                ));

        OrderStatus previousStatus = order.getStatus();

        if (previousStatus == newStatus) {
            return;
        }

        order.changeStatus(newStatus);
        repository.save(order);

        publisher.publishEvent(new OrderStatusChanged(
                orderId,
                previousStatus.name(),
                newStatus.name()
        ));
    }
}
~~~

The listener runs only after the transaction commits:

~~~java
@Component
class OrderStatusListener {
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderStatusChanged event) {
        System.out.println(
                "Committed status change: " + event.orderId()
                        + " -> " + event.newStatus()
        );
    }
}
~~~

How it works:

1. Spring opens a transaction for the `changeStatus` call via the transaction proxy.
2. The service reads the state, checks rules, and updates the aggregate.
3. The service publishes the event while the transaction is active.
4. Spring records the event for the transactional listener.
5. When the transaction commits successfully, the listener in phase `AFTER_COMMIT` is invoked.
6. If the transaction rolls back, the `AFTER_COMMIT` listener does not run.

Although the annotation name includes "EventListener", here the publisher still calls `publishEvent` inside the transaction. What gets deferred is **listener execution** until after commit. This ensures the listener only processes the event when the state change has successfully committed.

Available phases:

| Phase | When the Listener Runs |
|---|---|
| `BEFORE_COMMIT` | Before the transaction commits |
| `AFTER_COMMIT` | After the transaction commits successfully; this is the default |
| `AFTER_ROLLBACK` | After the transaction rolls back |
| `AFTER_COMPLETION` | After the transaction completes, whether committed or rolled back |

If an event is published with no active transaction, a transactional listener does not run by default. You can enable `fallbackExecution = true`, but only use it when running the listener outside a transaction is valid for business logic:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true
)
public void afterCommitOrWithoutTransaction(OrderStatusChanged event) {
    // Only use fallback if the no-transaction case is also acceptable.
}
~~~

Do not enable fallback just to make sure "the listener always runs" if the business logic requires committed database state. When there is no transaction, there is no commit milestone to confirm.

## 5. Distinguishing Post-Transaction Publication from Post-Commit Listeners

There are two ways to organize code that both generally ensure listeners are invoked after the original transaction completes, but their code boundaries differ.

### Approach A: Publish Inside the Transaction, Listener Uses AFTER_COMMIT

~~~java
@Transactional
public void changeStatus(String orderId, OrderStatus newStatus) {
    // Read, validate, change, and save the state.
    publisher.publishEvent(event);
}
~~~

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void handle(OrderStatusChanged event) {
    // Run only after commit.
}
~~~

The advantage is that the event is bound to the transaction performing the change. Spring invokes the listener in the selected phase only when the transaction completes accordingly. This is usually the cleanest approach when the event is the outcome of a transactional operation.

### Approach B: Publish After the Transactional Method Returns

You can separate writing state and publishing events into two beans/classes:

~~~java
import java.util.Optional;

@Service
class OrderStatusCommand {
    private final OrderRepository repository;

    OrderStatusCommand(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Optional<OrderStatusChanged> changeStatus(
            String orderId,
            OrderStatus newStatus
    ) {
        Order order = repository.findById(orderId).orElseThrow();
        OrderStatus previous = order.getStatus();

        if (previous == newStatus) {
            return Optional.empty();
        }

        order.changeStatus(newStatus);
        repository.save(order);

        return Optional.of(new OrderStatusChanged(
                orderId, previous.name(), newStatus.name()
        ));
    }
}

@Service
class OrderStatusApplicationService {
    private final OrderStatusCommand command;
    private final ApplicationEventPublisher publisher;

    OrderStatusApplicationService(
            OrderStatusCommand command,
            ApplicationEventPublisher publisher
    ) {
        this.command = command;
        this.publisher = publisher;
    }

    public void changeStatus(String orderId, OrderStatus newStatus) {
        Optional<OrderStatusChanged> event = command.changeStatus(orderId, newStatus);

        // The call through the Spring proxy has returned after the transaction committed.
        event.ifPresent(publisher::publishEvent);
    }
}
~~~

In this approach, `OrderStatusApplicationService` calls another bean with a `@Transactional` method. When the call through the proxy returns normally and is not participating in a broader outer transaction, the transaction managed by that method has ended; only then does the coordinating layer publish the event.

Keep the two classes in separate beans so the call goes through the Spring proxy. If a method inside the same object calls another `@Transactional` method directly (self-invocation), the transaction proxy may not be applied as expected.

Approach B reads clearly when you want to highlight a "persist first, then publish" boundary in the orchestration layer. However, a gap still exists between the database commit and the publish call. If the process stops during that gap, the state is committed while the event may never be published. Thus, this approach does not by itself provide durable delivery guarantees.

## 6. Publish Events Only When State Actually Changes

A state event should represent a meaningful transition. If a request sets the new state equal to the current state, you generally should not publish the same event again.

Example:

~~~java
OrderStatus previous = order.getStatus();

if (previous == requestedStatus) {
    return;
}

order.changeStatus(requestedStatus);
publisher.publishEvent(new OrderStatusChanged(
        order.getId(),
        previous,
        requestedStatus
));
~~~

Checking for a no-op avoids:

- Sending duplicate emails or notifications.
- Creating multiple identical audit records.
- Unnecessary projection updates.
- Triggering downstream listeners multiple times.
- Creating event chains without a new business transition.

Not every domain treats an identical state as a no-op. Some systems have a "reconfirm" command or need to record a repeated action as a separate event. In that case, the event must accurately represent that action, such as `PaymentConfirmationRequestedAgain`, instead of pretending the state transitioned again.

## 7. What Should the Event Payload Contain?

An event handled after a state change occurs should carry enough data for listeners to understand the exact transition that took place.

A payload typically includes:

| Field | Purpose |
|---|---|
| `eventId` | Unique identifier, supporting idempotency and tracing |
| `aggregateId` | Identifier of the entity/aggregate that changed |
| `previousStatus` | Status before the transition |
| `newStatus` | Status after the transition |
| `aggregateVersion` | Aggregate version after the change |
| `occurredAt` | Timestamp when the business event occurred |
| `actorId` | Person or system initiating the transition, if applicable |
| `correlationId` | Links the event to a larger request/workflow |

Prefer immutable payloads such as Java records. The snippet below is a metadata-rich version replacing the simple `OrderStatusChanged` record used in earlier examples; in real code, declare only one record with the chosen structure rather than declaring two records with the same name:

~~~java
import java.time.Instant;
import java.util.UUID;

record OrderStatusChanged(
        UUID eventId,
        String orderId,
        String previousStatus,
        String newStatus,
        long aggregateVersion,
        Instant occurredAt
) {}
~~~

Do not pass JPA entities directly inside events. An entity may continue to be modified, contain lazy relationships, depend on a persistence context, or cause listeners to read a state different from the snapshot at the time of transition.

If listeners need the exact state at the moment the event occurred, pass the required snapshot. If listeners need the latest current state, pass the identifier and re-read from the authoritative data source. The two approaches have different semantics when multiple consecutive transitions occur.

## 8. Multiple State Changes and Event Ordering

An aggregate can transition through states multiple times:

~~~text
PENDING → CONFIRMED → SHIPPED → DELIVERED
~~~

Each successful transition produces a separate event:

~~~text
OrderConfirmed
OrderShipped
OrderDelivered
~~~

If events are published synchronously within a single process, listeners generally receive them in that thread's dispatch order. However, when using an async executor, multiple threads, or a broker, completion order can differ from publication order.

For example, the listener processing `OrderConfirmed` takes 500 ms, while the listener processing `OrderShipped` takes only 50 ms. The two async listeners can finish out of order. If ordering is meaningful to business logic:

- Attach `aggregateVersion` or a sequence number to the event.
- Check the version before applying a projection.
- Partition by aggregate key if using a broker that supports per-partition ordering.
- Do not assume `@Order` controls execution order across async tasks.
- Handle late-arriving or duplicate events with an explicit policy.

If a consumer receives version 8 before version 7, the consumer can reject it, buffer it, or re-read the latest state depending on requirements. Do not blindly apply every incoming event without checking ordering when a projection depends on sequential transitions.

## 9. Post-Commit Listeners Can Fail; the Database Does Not Automatically Roll Back

`AFTER_COMMIT` guarantees the listener is invoked after the original transaction commits successfully. It does not turn the listener's processing into something that can roll back together with the original transaction.

Example:

1. The order transitions to `PAID` and the database commits.
2. The post-commit listener calls an email service.
3. The email service times out or the listener throws an exception.

The order status remains committed. Failing to send the email cannot revert the database back to `PENDING` by rolling back an already finished transaction.

Therefore, a post-commit listener should have:

- Sufficient logging of event ID, aggregate ID, and status transition.
- Bounded retries if the task can be retried safely.
- Idempotency so notifications or side effects are not duplicated.
- Tracking of terminal failures and a manual handling mechanism if business rules require it.
- A new transaction if the listener needs to write additional database data after commit.

For ignorable secondary tasks, logging and accepting potential loss may suffice. For critical tasks, a durable storage mechanism is required rather than relying solely on in-memory listeners.

## 10. When Event Loss Is Unacceptable: Transactional Outbox

There is an inherent gap when writing to a database and publishing an event separately:

~~~text
Database COMMIT succeeded
        |
        | process may stop here
        v
publishEvent / send message
~~~

If the application stops after commit but before publishing, the state has changed while listeners or downstream services never receive the event.

Transactional Outbox solves this by persisting the intent to publish the event in the same transaction as the business change:

1. Update the order status.
2. Write an outbox record containing the event ID, aggregate ID, event type, payload, and creation timestamp.
3. Commit both the state change and the outbox record in the same transaction.
4. A relay reads unsent outbox records and publishes them to a broker.
5. The relay marks records as sent after receiving confirmation according to the chosen policy.

If the transaction rolls back, both the state change and the outbox record roll back. If the transaction commits, the outbox record persists so the relay can continue sending even if the application process restarts.

The relay may send duplicates if the broker received the message before the application recorded the sent status. Hence, consumers still need to be idempotent, typically keyed on `eventId`.

You can use a Spring Application Event to wake up the relay after commit, but the outbox record remains the durable source of truth. Do not treat in-memory events as the sole copy of the outbox.

## 11. Common Misconceptions

- **Calling `save()` means committed.** False. Within a transaction, commit occurs when the transaction manager finishes; save/flush is not enough.
- **Changing a field and publishing anywhere is fine.** False. Listeners may run before validation or the transaction completes.
- **Using `@TransactionalEventListener(AFTER_COMMIT)` means the event is durably persisted.** False. It defers the listener until after commit, but does not persist the event for replay after a crash.
- **If the transaction rolls back, all listener side effects roll back automatically.** False. Side effects outside the database or listeners that ran before commit are not automatically undone.
- **Publishing an event every time the same status is received.** Usually creates duplicate notifications and side effects; explicitly decide whether it is a no-op or a meaningful repeated action.
- **Async listeners always finish in publish order.** False. An executor can process and complete tasks in a different order.
- **If a post-commit listener fails, the database automatically reverts.** False. The original transaction has already committed.
- **Publishing after the transactional method returns guarantees no event loss.** False. The process can still stop between commit and publish; an outbox is needed when high durability is required.

## 12. Checklist Before Publishing Events

- [ ] Was the current state read from the authoritative data source?
- [ ] Did the new transition pass business validation?
- [ ] Was the state updated before creating the event?
- [ ] Is the case where the new state equals the current state handled?
- [ ] Did you distinguish object mutation, flush, and commit?
- [ ] Should listeners run right after mutation or only after transaction commit?
- [ ] If using `@TransactionalEventListener`, is the event published inside an appropriate transaction?
- [ ] Do you understand the behavior without a transaction and `fallbackExecution`?
- [ ] Does the payload include previous/new status, ID/version, and required snapshot data?
- [ ] Do async listeners control ordering, errors, and idempotency?
- [ ] If a post-commit listener fails, is there a retry or error-handling strategy?
- [ ] If event loss is unacceptable, is an outbox or durable storage mechanism used?

Spring Application Events are well-suited for notifying components within the same application after a state transition. Create the event after business logic accepts the change, choose listener timing based on commit boundaries, and use immutable payloads that clearly reflect previous and new states. When you must guarantee an event is not lost between database commit and dispatch, persist the event in the same transaction using a Transactional Outbox.
