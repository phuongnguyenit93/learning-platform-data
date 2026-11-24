# @TransactionalEventListener for Transaction-Outcome-Bound Processing

In Spring Framework, a business operation may **write data inside a transaction** while also needing to send notifications, update caches, create audit records, or dispatch work to another system. Event timing is critical: if a consumer performs side work **before the transaction commits**, an external system may receive a notification about a record that is later rolled back. When you want processing to occur only after a transaction succeeds, Spring provides **`@TransactionalEventListener`**, binding a listener to a **transaction phase** rather than running immediately when the event is published.

By default, `@TransactionalEventListener` runs at `TransactionPhase.AFTER_COMMIT`. It also supports `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. Understanding the differences between these phases, behavior when no transaction exists, and interactions with `@Async` is foundational for building correct concurrent processing.

**Core warning:** "running after commit" **does not mean** "running inside a new transaction" and **does not guarantee durable delivery across a JVM crash**. After commit, some old transaction resources may still remain bound to the thread; if you need to write to the database from a callback, you typically must open **a new transaction** with `REQUIRES_NEW`. For work that must never be lost, use a **transactional outbox** or durable job persistence design.

## 1. Learning Objectives

After this lesson, you will be able to:

- Distinguish `@EventListener` from `@TransactionalEventListener` and describe how callbacks register against the active transaction.
- Explain the four `TransactionPhase` values, listener invocation conditions, and each phase's limitations.
- Understand the default `fallbackExecution=false`: events published **outside a transaction** are ignored by transactional listeners.
- Place `ApplicationEventPublisher.publishEvent(...)` in the right transaction/thread so the listener binds to the intended outcome.
- Explain why `AFTER_COMMIT` does not imply a new transaction, and when `@Transactional(propagation = REQUIRES_NEW)` is needed.
- Combine `@TransactionalEventListener` with `@Async` deliberately without assuming transaction context propagates automatically to workers.
- Distinguish durability of an in-JVM callback from delivery guarantees across shutdowns, crashes, or multiple replicas.
- Test commit, rollback, no-transaction, callback ordering, and rejections without guessing via `Thread.sleep`.
- Recognize reactive transactions in Spring 6.1+ and their different context-propagation requirements compared to thread-bound transactions.
- Choose the right strategy for sending emails, publishing messages, updating audits/caches, and handling tasks requiring retries and idempotency.

## 2. Problem Scenario: Sending Notifications Too Early

Suppose an order-creation feature:

~~~java
@Transactional
public void createOrder(CreateOrderRequest request) {
    orderRepository.save(new Order(request));
    emailGateway.sendConfirmation(request.email());
}
~~~

This is **illustrative code in a Spring service**, requiring `@Transactional`, application types, and dependencies. Sending the email directly inside the method allows the email to succeed **before the database transaction actually commits**. Later, commit may fail or an exception may trigger rollback: the customer receives confirmation for an order that was never persisted.

Instead of sending directly, we can publish a **domain event** inside the transaction:

~~~java
@Transactional
public void createOrder(CreateOrderRequest request) {
    Order order = orderRepository.save(new Order(request));
    publisher.publishEvent(new OrderCreatedEvent(order.getId()));
}
~~~

And handle it when the transaction commits successfully:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void afterOrderCommitted(OrderCreatedEvent event) {
    notifications.notifyOrderCreated(event.orderId());
}
~~~

This is also **illustrative code**, where `publisher` is `ApplicationEventPublisher` and `notifications` is an application service/gateway. Here `@TransactionalEventListener` prevents **running the listener if the transaction rolls back** along the normal execution path. Still, sending an email directly in an after-commit callback can fail; if the JVM dies after commit before sending, the email may never go out. **Never rely on a bare after-commit callback to promise exactly-once or durable delivery.**

## 3. How Do @EventListener and @TransactionalEventListener Differ?

| Criterion | Regular `@EventListener` | `@TransactionalEventListener` |
| --- | --- | --- |
| Default execution timing | When the event is multicast to listeners, per multicaster config (usually synchronous by default) | When the transaction reaches the `AFTER_COMMIT` phase |
| Depends on an active transaction? | Not required | Yes by default |
| If publisher emits inside a transaction that rolls back | Listener usually already ran if multicaster is synchronous | `AFTER_COMMIT` does not run |
| Can target before-commit / after-rollback? | Has no built-in transaction phase binding | Has `BEFORE_COMMIT`/`AFTER_ROLLBACK`/`AFTER_COMPLETION` |
| Event published with no transaction | Regular listener can still receive it | **Not processed** by default; `fallbackExecution=true` changes this |
| Guarantees messages/jobs survive JVM crash? | No | No |
| Thread/context | Depends on multicaster and `@Async` | Transaction registration needs the right context; post-phase execution can be synchronous or async-dispatched |

`@TransactionalEventListener` is itself declared as an event listener with added transaction constraints. **Do not stack `@EventListener` onto the same method** just to receive events. Combining both annotations arbitrarily can confuse configuration readers, and method names do not determine the phase.

### Visualizing a Typical Flow

~~~text
Request thread
   |
   v
Spring @Transactional proxy opens transaction
   |
   +-- INSERT order
   |
   +-- publishEvent(OrderCreated)
   |       |
   |       +-- transactional listener receives event
   |           and registers synchronization for current TX
   |
   +-- service method returns
   |
   +-- transaction manager decides commit / rollback
           |
           +-- COMMIT succeeds --> AFTER_COMMIT listener
           |
           +-- ROLLBACK -------> AFTER_ROLLBACK listener
           |
           +-- finishes -------> AFTER_COMPLETION listener
~~~

**When `publishEvent` returns does not prove the `AFTER_COMMIT` listener has run.** Normally at publish time, the listener has only registered with the transaction. Spring invokes the phase listener when the transaction manager executes synchronizations.

## 4. The Four TransactionPhase Values

`org.springframework.transaction.event.TransactionPhase` provides four values:

| Phase | When? | Common goal | Important note |
| --- | --- | --- | --- |
| `BEFORE_COMMIT` | Before committing the transaction | Checks or preparation required before commit | **Commit is not guaranteed to succeed**; commit may still fail after the callback |
| `AFTER_COMMIT` | After the transaction commits successfully | Emitting signals, triggering secondary work once data is committed | No further commit for the old transaction; extra DB/I/O needs its own plan |
| `AFTER_ROLLBACK` | After the transaction rolls back | Recording rollback, releasing/updating failure state as needed | New DB writes need an independent transaction |
| `AFTER_COMPLETION` | Once the transaction finishes, commit or rollback | Cleanup, metrics, completion auditing | Covers more than success; check actual outcome if logic depends on it |

### 4.1 BEFORE_COMMIT

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void beforeCommit(OrderCreatedEvent event) {
    verifyRequiredMetadata(event.orderId());
}
~~~

This is **integration code** where `verifyRequiredMetadata` is defined by the application. `BEFORE_COMMIT` runs while preparing to commit; the transaction is still finalizing. With a synchronous callback, a runtime exception can disrupt commit and cause rollback per transaction manager rules. However, **a successful callback does not guarantee the database commit succeeds**: constraint errors, network failures, or commit failures can still occur afterward.

Never send irreversible notifications confirming an order succeeded inside `BEFORE_COMMIT`. If the callback sends an email before commit and commit later fails, the original bug remains.

### 4.2 AFTER_COMMIT — The Default Phase

~~~java
@TransactionalEventListener
public void onCommitted(OrderCreatedEvent event) {
    queueNonCriticalNotification(event.orderId());
}
~~~

Equivalent in phase to `@TransactionalEventListener(phase=TransactionPhase.AFTER_COMMIT)`. The prerequisite is that the event is published within a Spring-supported transaction and that transaction **commits successfully**.

By default, the listener does not automatically run on another thread: a transactional phase is a **transaction condition**, not a concurrency setting. If a synchronous listener performs blocking work in its callback, it prolongs the return time of the committing thread and can even time out requests, even though the primary transaction already committed.

### 4.3 AFTER_ROLLBACK

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_ROLLBACK)
public void onRolledBack(OrderCreatedEvent event) {
    recordRollbackMetric(event.orderId());
}
~~~

This is **illustrative code**. `AFTER_ROLLBACK` applies only when the transaction rolls back. If the DB commits successfully, this listener is not invoked for events registered inside that transaction.

Distinguish an actual transaction rollback from a business method returning an error code **while its transaction still commits**; the listener does not infer "business failure" from HTTP status codes or return values. The deciding event is the transaction manager's outcome.

### 4.4 AFTER_COMPLETION

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMPLETION)
public void onCompleted(OrderCreatedEvent event) {
    cleanupTemporaryState(event.orderId());
}
~~~

The callback is invoked when the transaction finishes with either commit or rollback per Spring's contract. Because it receives the same `OrderCreatedEvent` payload without a status in the default signature, **do not infer the outcome merely from the listener running**. If you need to distinguish commit from rollback, use two phase-specific listeners or a transaction synchronization carrying the completion status.

## 5. Standalone Java 17+ Example Modeling the Timeline of Both Outcomes

The program below **does not use Spring and performs no DB transactions**. It simply illustrates the four-phase callback sequence so learners can run it directly with JDK 17. This does not replace an integration test of `@TransactionalEventListener` against a real transaction manager.

File **TransactionPhaseTimelineDemo.java**:

~~~java
import java.util.ArrayList;
import java.util.EnumMap;
import java.util.List;
import java.util.Map;

public final class TransactionPhaseTimelineDemo {
    enum Phase {
        BEFORE_COMMIT, AFTER_COMMIT, AFTER_ROLLBACK, AFTER_COMPLETION
    }

    static final class Timeline {
        private final Map<Phase, List<Runnable>> callbacks =
                new EnumMap<>(Phase.class);
        private boolean active = true;

        Timeline() {
            for (Phase phase : Phase.values()) {
                callbacks.put(phase, new ArrayList<>());
            }
        }

        void register(Phase phase, Runnable callback) {
            if (!active) {
                throw new IllegalStateException("Transaction already finished");
            }
            callbacks.get(phase).add(callback);
        }

        private void fire(Phase phase) {
            for (Runnable callback : callbacks.get(phase)) {
                callback.run();
            }
        }

        void complete(boolean commit) {
            if (!active) {
                throw new IllegalStateException("Already completed");
            }
            if (commit) {
                fire(Phase.BEFORE_COMMIT);
            }
            active = false;
            fire(commit ? Phase.AFTER_COMMIT : Phase.AFTER_ROLLBACK);
            fire(Phase.AFTER_COMPLETION);
        }
    }

    private static String simulate(boolean commit) {
        Timeline tx = new Timeline();
        List<String> observations = new ArrayList<>();

        tx.register(Phase.BEFORE_COMMIT,
                () -> observations.add("before"));
        tx.register(Phase.AFTER_COMMIT,
                () -> observations.add("committed"));
        tx.register(Phase.AFTER_ROLLBACK,
                () -> observations.add("rolledBack"));
        tx.register(Phase.AFTER_COMPLETION,
                () -> observations.add("completed"));

        tx.complete(commit);
        return String.join(">", observations);
    }

    public static void main(String[] args) {
        System.out.println("commit=" + simulate(true));
        System.out.println("rollback=" + simulate(false));
    }
}
~~~

Compile/run:

~~~bash
javac TransactionPhaseTimelineDemo.java
java TransactionPhaseTimelineDemo
~~~

Expected stdout:

~~~text
commit=before>committed>completed
rollback=rolledBack>completed
~~~

**Meaning:** when the model commits, `BEFORE_COMMIT` and `AFTER_COMMIT` fire with no `AFTER_ROLLBACK`. When it rolls back, only `AFTER_ROLLBACK` and `AFTER_COMPLETION` apply. `AFTER_COMPLETION` appears on both paths. This is a **conceptual timeline** model and does not reflect every nuance around exceptions, JTA, nested transactions, timeouts, or ordering of all Spring synchronizations.

## 6. Writing Spring Events and Publishers Properly

The following example shows a typical Spring application structure: an immutable event, a publishing service, and a commit-bound listener bean. These snippets are **Spring classes**; they require Spring dependencies, a transaction manager, and project repositories/gateways, and cannot run standalone with `javac` alone.

### Immutable Event Carrying an ID

File **OrderCreatedEvent.java**:

~~~java
public record OrderCreatedEvent(String orderId) {
}
~~~

With Java 17, `record` is ideal for carrying immutable metadata. The event holds **orderId**, without references to JPA entities with lazy relations, EntityManagers, or transaction-bound objects. Because the listener runs after the data-write moment, passing an ID cleanly separates entity and consumer lifecycles.

### Service Publishing the Event Inside a Transaction

File **OrderCommandService.java**:

~~~java
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final ApplicationEventPublisher publisher;

    public OrderCommandService(
            OrderRepository orders,
            ApplicationEventPublisher publisher) {
        this.orders = orders;
        this.publisher = publisher;
    }

    @Transactional
    public void createOrder(String orderId) {
        orders.insert(orderId);
        publisher.publishEvent(new OrderCreatedEvent(orderId));
    }
}
~~~

`OrderRepository` here is an application interface with `insert(String)`; a real repository bean connected to the DB is required. For callbacks to bind to the transaction, **another bean must call `createOrder(...)` through the Spring transactional proxy**, or code must already have an active transaction through another mechanism. Calling `this.createOrder(...)` inside the same class in proxy mode can bypass `@Transactional`, causing `publishEvent` to run **outside any transaction**.

To ensure the event reflects committed data, `orders.insert` and event publication must occur inside the same manager-backed transaction. Never publish the event on another worker right here expecting that worker to see the request thread's transaction.

### Post-Commit Listener

File **OrderNotificationListener.java**:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class OrderNotificationListener {
    private final OrderNotificationGateway notificationGateway;

    public OrderNotificationListener(
            OrderNotificationGateway notificationGateway) {
        this.notificationGateway = notificationGateway;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        notificationGateway.notifyCreated(event.orderId());
    }
}
~~~

`OrderNotificationGateway` is an application interface/service responsible for sending notifications. This listener is commit-only; if the transaction rolls back, it does not run. **This is not a retry or durable-queue mechanism**: if sending the notification fails inside the callback, the committed order data remains in the DB, and the caller may or may not see an error depending on invocation/logging setup. Handle notification failures via business contracts rather than trying to roll back an already finalized transaction.

## 7. Without a Transaction: fallbackExecution

Annotation attribute:

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = false)
public void listener(OrderCreatedEvent event) {
    // ...
}
~~~

`fallbackExecution=false` is the default. If code executes `publisher.publishEvent(...)` **with no compatible active transaction**, a transactional listener **is not invoked** by default. This is intentional: an "after commit" phase cannot be registered when there is no transaction to commit.

Non-transactional example:

~~~java
public void publishOutsideTransaction(String id) {
    publisher.publishEvent(new OrderCreatedEvent(id));
}
~~~

This is **illustrative code** inside a Spring bean with an injected `publisher`. Without a transaction and with a default `@TransactionalEventListener`, that listener ignores this event, even though a regular `@EventListener` can still receive it.

### When fallbackExecution=true Is Enabled

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        fallbackExecution = true)
public void onCommitOrNoTransaction(OrderCreatedEvent event) {
    // ...
}
~~~

If a transaction exists, the listener still binds to `AFTER_COMMIT`. If no transaction exists, Spring allows **immediate execution via the fallback path**, with no commit to wait for. That is why `onCommitOrNoTransaction` reflects the contract more accurately than `afterCommit`.

**Never enable `fallbackExecution=true` to "fix" a broken `@Transactional` without investigating first.** It can let the listener run outside a transaction and violate the "send only once data is committed" invariant. Whenever self-invocation or transaction manager misconfiguration is suspected, fix the root cause first.

### When Is Enabling Fallback Reasonable?

When an informational event can originate from both transactional and non-transactional paths and immediate non-transactional handling is acceptable to the product. Conversely, if the listener emits messages about records that must definitely exist, **keep the default `false`** and ensure publishing happens inside a transaction. Verify skipped no-tx cases with tests and metrics instead of flipping fallback on automatically.

## 8. After Commit: Old Resources May Still Remain Bound

This is a very easy point to misunderstand when learning `@TransactionalEventListener`.

At `AFTER_COMMIT`, the primary transaction has already committed. However, Spring transaction synchronization may still keep the thread-bound connection/session or resources alive until cleanup completes. Per Spring Javadoc, if data-access code runs at this moment, it **may appear to participate in the old transaction**, yet **there is no subsequent commit** for that transaction.

Hence code like:

~~~java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderCreatedEvent event) {
    auditRepository.save(new AuditRecord(event.orderId()));
}
~~~

is **risky illustrative code**, where `AuditRecord` and `auditRepository` are project-defined. Calling `save` after commit **does not guarantee the new audit record commits to the DB** if it joins the old transaction's resources. That is why Spring recommends **`PROPAGATION_REQUIRES_NEW`** for transactional work triggered inside post-commit/completion callbacks.

### Safer Approach: A Separate Service Opening a New Transaction

File **AuditWriteService.java**:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditWriteService {
    private final AuditRepository auditRepository;

    public AuditWriteService(AuditRepository auditRepository) {
        this.auditRepository = auditRepository;
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeCommittedOrderAudit(String orderId) {
        auditRepository.insertCommittedOrder(orderId);
    }
}
~~~

`AuditRepository` is an application interface with `insertCommittedOrder(String)`. The listener injects the separate service:

~~~java
@Component
public class OrderAuditListener {
    private final AuditWriteService auditWriteService;

    public OrderAuditListener(AuditWriteService auditWriteService) {
        this.auditWriteService = auditWriteService;
    }

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void afterCommit(OrderCreatedEvent event) {
        auditWriteService.writeCommittedOrderAudit(event.orderId());
    }
}
~~~

This is a **Spring snippet requiring `Component`, `TransactionalEventListener`, and `TransactionPhase` imports** as before. Because the call goes through a separate `AuditWriteService` bean, `@Transactional(REQUIRES_NEW)` can be intercepted by the Spring proxy to open an independent transaction. Placing `@Transactional(REQUIRES_NEW)` on a method and calling `this.method()` inside the same bean will not create a new transaction in proxy mode.

**Remember:** `REQUIRES_NEW` gives the audit write its own commit, yet **does not make notification/audit atomic with the primary transaction**. Between the primary transaction committing and the audit transaction committing, the process can crash. If "every committed order always has an audit/message" is required, design an **outbox** in the originating transaction instead of merely adding `REQUIRES_NEW`.

### Same Caution Applies to AFTER_ROLLBACK and AFTER_COMPLETION

During `AFTER_ROLLBACK`/`AFTER_COMPLETION`, resources from the old transaction may still be bound to the thread as well. Any **new database write** from a listener in these phases should use a fresh independent transaction and be verified with real tests. Never assume that because rollback finished, every DAO call automatically starts a fresh transaction.

## 9. BEFORE_COMMIT and Exceptions: Do Not Confuse With a Validation Service

You can use a `BEFORE_COMMIT` listener for logic that must occur during the commit sequence. However, callbacks are an indirect part of transaction synchronization, making error flow and ordering harder to follow than calling validation directly before the service method finishes.

~~~java
@TransactionalEventListener(phase = TransactionPhase.BEFORE_COMMIT)
public void verify(OrderCreatedEvent event) {
    if (!businessRuleIsSatisfied(event.orderId())) {
        throw new IllegalStateException("Order rule violation");
    }
}
~~~

This is an **illustrative example**. In standard synchronous synchronization, a runtime exception in `beforeCommit` can normally fail/roll back the commit. Still, **do not replace mandatory validation at order creation** when business logic needs clear responses or when event publication/ordering might vary. A `BEFORE_COMMIT` listener succeeding still does not prove the database committed.

**Never dispatch non-rollbackable side effects in BEFORE_COMMIT**, because an event "about to commit" is not an event that "has committed".

## 10. Combining @TransactionalEventListener and @Async

A transaction-phase listener is **not asynchronous by default**. If the listener performs network calls or slow work and should not block the completion path, you can consider `@Async`:

~~~java
@Component
public class AsyncOrderNoticeListener {
    private final NoticeSender sender;

    public AsyncOrderNoticeListener(NoticeSender sender) {
        this.sender = sender;
    }

    @Async("notificationExecutor")
    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onOrderCreated(OrderCreatedEvent event) {
        sender.send(event.orderId());
    }
}
~~~

This is an **illustrative Spring class**; it requires `Component`, `Async`, `TransactionalEventListener`, `TransactionPhase` imports, plus a `NoticeSender` bean, an executor named `notificationExecutor`, and `@EnableAsync`. When configured properly, Spring registers the listener against the transaction on the publishing thread; **once AFTER_COMMIT fires**, the target method can be dispatched to the executor via `@Async`.

Implications:

- **The transaction phase** decides **when the listener becomes eligible to run**.
- **The executor** decides **which thread runs the body and when it actually completes**.
- The worker thread **does not automatically inherit** the publisher's transaction or thread-locals.
- If the queue rejects the task, `TaskRejectedException` can occur at dispatch time; failure handling and observability must be designed.
- If the executor uses `CallerRunsPolicy` when saturated, the body can run inline on the calling thread despite `@Async`, increasing commit-path latency.
- Because the job lives in an in-JVM queue, submitted tasks can still be lost if the process dies.

### Contrast With an ApplicationEventMulticaster Having an Executor

In modern Spring versions, transactional listeners must register transaction synchronizations inside the event publication context; `TransactionalApplicationListener` does not let a multicaster arbitrarily move synchronization registration onto another thread. You can make the **target listener** execute asynchronously via an appropriate mechanism (such as `@Async`), rather than configuring `SimpleApplicationEventMulticaster.setTaskExecutor(...)` and assuming transactional listeners will work or receive the right transaction on workers.

A technical point to verify in integration tests: **which transaction and thread registered the event**, and **after which outcome the listener body ran**. In Spring 6.1+, `TransactionalApplicationListener.supportsAsyncExecution()` reflects this distinction: listener synchronization must bind to the source context, whereas the target listener can have its own async execution path.

### Example Executor Configuration

~~~java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class NotificationAsyncConfig {
    @Bean(name = "notificationExecutor")
    public ThreadPoolTaskExecutor notificationExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(32);
        executor.setThreadNamePrefix("notice-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }
}
~~~

This is a **Spring configuration class**, not a standalone `javac` program. Parameters are illustrative and must be sized to load; with `AbortPolicy`, handle rejected tasks when the pool is full or shutting down. `@EnableAsync` is required for `@Async`; placing the annotation on a non-Spring-managed object does not activate proxies.

## 11. When Does an Async Listener Break Transaction Expectations?

### Reading Caller ThreadLocals or Transactions

In traditional Spring with `PlatformTransactionManager`, transactions are bound to threads. When `@Async` moves the body to a worker, the worker does not automatically carry the publisher's transaction context, MDC, or SecurityContext. Calling `TransactionSynchronizationManager.isActualTransactionActive()` inside an async body to conclude "we are still in the original transaction" is a false assumption. Even in a synchronous post-commit callback, transaction resources may stay accessible briefly while no further commit occurs.

**Solution:** pass the ID, correlation ID, and minimal required data in an immutable payload; define a separate transaction in the listener's service when writing to the DB; use deliberate context propagation for logging/security. Never pass EntityManagers, connections, managed JPA entities, or transaction statuses via events.

### Running Outside a Transaction by Publishing From Another Worker

~~~java
@Async
public void publishLater(OrderCreatedEvent event) {
    publisher.publishEvent(event);
}
~~~

This is an illustrative snippet inside a bean with `publisher`. If the main transaction is on thread A while `publishLater` runs on thread B, the event is published **with no transaction bound on B**. A default `@TransactionalEventListener` will skip that event. Always publish events **on the thread holding the transaction**, letting the listener pick the phase and optionally run its body asynchronously **once that phase arrives**.

### Post-Commit Listener Errors Do Not Undo the Original Commit

Once the main transaction has committed, an exception thrown inside `AFTER_COMMIT` cannot "uncommit" it. Whether the exception propagates to the caller or is only logged depends on the synchronization stage, executor, and how Spring invokes the listener. Do not build a contract assuming "a failed request means the transaction rolled back" if a post-commit listener is throwing exceptions.

If side effects need multiple retries, assign explicit job IDs and states. If business consistency is required, use transaction/outbox or saga/compensation designs rather than expecting a post-commit callback to roll back finalized data.

## 12. Reactive Transactions in Spring 6.1+

For traditional transactions managed by `PlatformTransactionManager`, Spring tracks state via a thread-bound context. With `ReactiveTransactionManager`, transaction context lives in the **Reactor Context**, not a ThreadLocal.

Starting in Spring Framework **6.1**, `@TransactionalEventListener` can work with both models, yet for **reactive transactions**, events must carry the necessary context inside the **event source**; Spring introduced `TransactionalEventPublisher` to support proper publication inside reactive pipelines.

Key points to remember:

1. **Do not** call `ApplicationEventPublisher.publishEvent(...)` casually inside a Reactor operator assuming the current thread holds the reactive transaction.
2. Check the `TransactionalEventPublisher` documentation for your Spring version and use the publication path bound to the Reactor transaction context.
3. Do not copy servlet/JPA thread-bound `@Transactional` examples verbatim into R2DBC ignoring context differences.
4. When handling async/reactive work, evaluate executors/schedulers, error propagation, and backpressure separately; transaction events do not automatically make side effects non-blocking.

This section highlights the difference rather than serving as a full Reactor/R2DBC guide. Enabling `fallbackExecution=true` does not fix a missing transaction context: it merely allows the listener to run without a transaction, breaking the "only after commit" requirement if misused.

## 13. Multiple Transactions and Nested Calls

### REQUIRES_NEW Inside a Producer

Suppose outer transaction A is running; another service invoked via a Spring proxy with `@Transactional(propagation=REQUIRES_NEW)` starts transaction B and **publishes an event inside B**. The event binds to transaction B; its `AFTER_COMMIT` listener runs once **B** commits, without waiting for A to commit. Afterward, A can still roll back.

This does not violate the contract: the listener binds to **the transaction actually active at publish time**, not the entire HTTP request or an intuitive "largest transaction". Therefore, if business logic requires the outer transaction's outcome, publish the event at the right boundary or record it in the appropriate transaction's outbox.

### NESTED / Savepoints

A `NESTED` operation may use a savepoint inside the same physical transaction (depending on manager/driver), not an independent physical commit like `REQUIRES_NEW`. Do not assume `@TransactionalEventListener(AFTER_COMMIT)` runs merely upon releasing a nested savepoint. Thoroughly test rollback-to-savepoint conditions and registered events: an event registered with the physical transaction's synchronization may not match the step-level outcome you intended.

### Rollback-Only Transactions

If a transaction has been marked rollback-only, the `@Transactional` method may still run to completion and `publishEvent` will still register the listener. When the transaction manager concludes with a rollback, `AFTER_COMMIT` does not run; `AFTER_ROLLBACK` listeners run per phase. Do not equate "method returned without throwing immediately" with "commit definitely succeeded".

## 14. @Order, condition, and Event Filtering

`@TransactionalEventListener` inherits many capabilities of standard event listeners:

### Ordering Callbacks

~~~java
@Order(10)
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void notifyAfterCommit(OrderCreatedEvent event) {
    // ...
}
~~~

This is illustrative code requiring `import org.springframework.core.annotation.Order`. `@Order` can order priority among related listeners/callbacks, yet it **does not** establish a global delivery order across JVMs, executors, message brokers, or async listeners. Never rely on ordering to ensure side-effect tasks run exactly once.

### Filtering With SpEL Conditions

~~~java
@TransactionalEventListener(
        phase = TransactionPhase.AFTER_COMMIT,
        condition = "#event.orderId() != null")
public void onOrderCreated(OrderCreatedEvent event) {
    // ...
}
~~~

This Spring SpEL example illustrates handling only events with a non-null ID. Parameter names in SpEL depend on parameter-name metadata and Spring configuration; for portable configurations, use Spring-supported argument access expressions and test them. A more maintainable option is validating inside the listener or enforcing non-null values in the event constructor.

### Multiple Phases for the Same Event Type

One event can be registered by several different listeners across `BEFORE_COMMIT`, `AFTER_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. Each listener runs in its phase when the transaction outcome matches. Never assume a single event triggers only one method application-wide.

## 15. Testing Transaction Outcomes Properly

Tests that only invoke a service and inspect logs can miss real transaction behavior. Directly test these scenarios:

| Scenario | Expectation |
| --- | --- |
| Publish in transaction then commit | `AFTER_COMMIT` runs, `AFTER_ROLLBACK` does not run |
| Publish in transaction then rollback | `AFTER_ROLLBACK` runs, `AFTER_COMMIT` does not run |
| Commit or rollback | `AFTER_COMPLETION` runs on both paths |
| Publish outside transaction, default fallback | Transactional listener does not execute |
| Publish outside transaction, `fallbackExecution=true` | Listener executes via fallback without a real transaction commit |
| Publish after transaction already ended | Does not bind to old transaction; follows no-tx/fallback rules |
| Listener writes to DB after commit | Write through a `REQUIRES_NEW` service persists after commit |
| Listener has `@Async` | Verify body runs after outcome and completion is observable |
| Main flow uses `REQUIRES_NEW` where event is published | Callback binds to the transaction active at publication |
| Transaction marked rollback-only | `AFTER_COMMIT` does not run |
| Event published on another worker thread | Without a transaction bound on that worker, default listener skips it |
| Executor rejects async task | Rejection is handled explicitly, never mistaken for primary tx rollback |

### Using TransactionTemplate to Control Commit/Rollback in Integration Tests

A test with a real Spring context and suitable `PlatformTransactionManager` can control transactions explicitly:

~~~java
import org.springframework.transaction.support.TransactionTemplate;

// Inside a test method with Spring-injected variables:
TransactionTemplate template =
        new TransactionTemplate(transactionManager);

template.executeWithoutResult(status -> {
    publisher.publishEvent(new OrderCreatedEvent("commit-1"));
});
// TransactionTemplate finishes the transaction before the next line runs.
// Assert the AFTER_COMMIT listener synchronously.

template.executeWithoutResult(status -> {
    publisher.publishEvent(new OrderCreatedEvent("rollback-1"));
    status.setRollbackOnly();
});
// Assert the AFTER_ROLLBACK listener, with no AFTER_COMMIT.
~~~

This is a **test fragment** requiring `transactionManager`, `publisher`, listeners/recorders, and an assertion framework. Use it only when both calls start **appropriate new transactions**: if the test method already has an outer transaction, `TransactionTemplate` with default propagation joins that outer transaction, so "commit" only happens at the outer boundary. In Spring Test with `@Transactional` on a test method, the test normally rolls back at the end; therefore **never let a test-wrapping transaction distort after-commit expectations**.

Better yet, use a test method without `@Transactional`, a real transaction manager, and configured repositories. When a test needs post-commit work (if the listener is async), await callback completion using a latch or thread-safe Future/recorder rather than an arbitrary `Thread.sleep(500)`.

### Using a Latch for Async Listeners

In integration tests, an async event listener can record completion:

~~~java
CountDownLatch received = new CountDownLatch(1);

// Inside the listener callback upon successful execution:
received.countDown();

// Inside the test (after the transaction has committed):
assertTrue(received.await(3, TimeUnit.SECONDS));
~~~

These are **illustrative fragments in two separate places**, not a complete program. Guarding with `CountDownLatch` proves the listener reached the checkpoint without guessing pool timing. If you need to verify an **email was sent successfully**, release the latch after the gateway/mock is called and returns, not the moment the listener begins.

## 16. When Events Must Not Be Lost: Transactional Outbox

`@TransactionalEventListener(AFTER_COMMIT)` only guarantees **listener invocation timing relative to transaction outcome within a running process**, not durable event storage after commit. There is a **failure gap**:

~~~text
Primary TX:
  INSERT order
  COMMIT succeeds
             |
             | JVM crashes before listener sends / enqueues job
             v
  order exists yet notification is never sent
~~~

Similarly, the listener may be invoked while the executor queue is full, shutting down, or the worker fails before sending. `@Async` only switches threads; it does not solve durability.

A **transactional outbox** addresses this by writing business data and an outbox record inside **the same transaction**:

~~~text
BEGIN TRANSACTION
  INSERT orders (...)
  INSERT outbox (event_id, event_type, payload, status=NEW)
COMMIT
        |
        v
Outbox worker / CDC
        |
        +-- publish message / invoke downstream
        +-- retry with backoff on error
        +-- update status and control duplicates
~~~

If the transaction rolls back, both the order and the outbox record roll back. If it commits, the outbox row persists durably so another worker or recovery process can send it after a restart.

### Conceptual Producer Example

~~~java
@Transactional
public void createOrder(CreateOrderRequest request) {
    Order order = orderRepository.save(new Order(request));
    outboxRepository.insert(new OutboxEvent(
            UUID.randomUUID().toString(),
            "OrderCreated",
            order.getId().toString()));
}
~~~

This is **illustrative code requiring application classes/repositories**, not a standalone runnable Spring file. An independent worker polls/publishes `NEW` records and updates status with a retry strategy. An `AFTER_COMMIT` listener can serve as an **early wake-up signal for the worker**, while the outbox row remains the **source of truth**; if the wake-up signal is lost, periodic polling still picks up unsent records.

### At-Least-Once and Idempotency

Even with an outbox, a publisher can send a message successfully and crash **before marking the outbox row SENT**. After restart, the message is sent again. Thus practical solutions rely on **at-least-once delivery + idempotent consumers**, rather than promising end-to-end exactly-once. Use event IDs as idempotency keys, processed-event tracking on receivers, or a transactional inbox when needed.

## 17. When to Choose Which Phase?

| Real requirement | Suitable phase / solution | Why |
| --- | --- | --- |
| Process events only when the transaction committed | Default `AFTER_COMMIT` | Skips rollback paths |
| Perform preparation/checks inside the commit sequence | `BEFORE_COMMIT` if suitable | Callback still runs before commit outcome |
| Observe rollbacks | `AFTER_ROLLBACK` | Runs only when the transaction rolls back |
| Clean up state / record metrics regardless of outcome | `AFTER_COMPLETION` | Covers both commit and rollback |
| Write audit DB records after commit | `AFTER_COMMIT` + `REQUIRES_NEW` service | Opens a fresh transaction to commit the audit |
| Send best-effort email after order creation | `AFTER_COMMIT`, optionally `@Async` | Avoids pre-commit sends while accepting loss risk |
| Guarantee events survive crashes | Transactional outbox / durable job store | Event is persisted inside the primary transaction |
| Handle events even outside transactions | Consider `fallbackExecution=true` | Fallback semantics do not wait for commit |
| Reactive transactions | `TransactionalEventPublisher` per Spring 6.1+ | Context lives in the Reactor Context |
| Event from an inner `REQUIRES_NEW` | Bind listener to the inner transaction | Inner outcome differs from outer outcome |
| Events missed by listener due to no-tx | Fix transaction/publication context first | Avoid "fixing" by misusing fallback |

**Decision tip:** answer three separate questions: (1) Does the event **need to wait for successful commit?** (2) Does the listener **need its own thread/transaction?** (3) Must the task **complete across crashes/restarts?** `@TransactionalEventListener` primarily answers the first; `@Async`/`REQUIRES_NEW` address the second; outbox/durable queues solve the third.

## 18. Common Mistakes

1. **Using `@EventListener` for work that must only happen after commit** and assuming the listener waits for the transaction to finish.
2. **Confusing `AFTER_COMMIT` with "having a new transaction".** Old resources may stay thread-bound with no further commit.
3. **Writing directly to the DB inside `AFTER_COMMIT`** without `REQUIRES_NEW` and assuming changes will definitely commit.
4. **Putting a whole JPA entity into an event** and calling lazy relations after commit; resources and entity state may no longer be valid.
5. **Publishing events outside a transaction** expecting a default transactional listener to receive them.
6. **Setting `fallbackExecution=true` to stop events from being dropped** without considering pre/non-committed execution consequences.
7. **Self-invocation bypassing the `@Transactional` proxy**, leaving the publisher without an active transaction.
8. **Publishing events from an `@Async` worker** assuming the worker inherited the request thread's transaction.
9. **Putting `@Async` on a listener thinking it creates a durable queue.** In-memory executor queues do not survive crashes.
10. **Configuring `SimpleApplicationEventMulticaster.setTaskExecutor` arbitrarily** and moving synchronization registration off the transaction thread.
11. **Treating `BEFORE_COMMIT` as proof commit succeeded.** Commit failures or rollbacks can still occur after the callback.
12. **Treating `AFTER_COMPLETION` as always meaning commit.** It also fires on rollback.
13. **Using `AFTER_ROLLBACK` while the listener opens a default transaction bound to old resources**, preventing audit writes from committing.
14. **Assuming an after-commit listener exception can roll back the main transaction.** The outcome is already finalized.
15. **Having no listener error-tracking path**, leaving failed notifications undetected while business state shows success without reconciliation.
16. **Using `@Order` to guarantee absolute ordering across threads or JVMs.** The annotation only orders related Spring callbacks.
17. **Assuming an event from an inner `REQUIRES_NEW` transaction waits for the outer transaction.** Events bind to the active transaction at publication time.
18. **Ignoring reactive transaction context**, even though R2DBC does not rely on ThreadLocals like JDBC transaction managers.
19. **Putting `@Transactional` on a test method and asserting AFTER_COMMIT before the test transaction finishes**; tests usually roll back by default.
20. **Using `Thread.sleep` in tests to guess when async listeners ran.** Use latches/recorders and deadlines.
21. **Assuming an outbox eliminates all duplicates.** Producers can redeliver if crashing after publish before ack; consumers must be idempotent.
22. **Sending emails inside `BEFORE_COMMIT`** even though emails cannot roll back with a DB transaction.
23. **Not measuring synchronous callback latency**, slowing down requests even after data committed.
24. **Checking `TransactionSynchronizationManager` in after-completion and concluding a committable transaction exists.** Bound resources do not imply a future commit.
25. **Using the event publisher as an inter-JVM message broker.** `ApplicationEventPublisher` by default only dispatches within a Spring ApplicationContext/JVM with no durable replication.

## 19. Self-Check Questions

1. Which phase does `@TransactionalEventListener` use by default? Do you need to declare `phase` to wait for commit?
2. What is the biggest difference between `@EventListener` and `@TransactionalEventListener` when a transaction rolls back?
3. If an event is published without a transaction, does the default listener run? What does `fallbackExecution=true` change?
4. Does a `BEFORE_COMMIT` listener succeeding guarantee the DB commit succeeds?
5. Why can `AFTER_COMPLETION` not by itself prove the transaction committed?
6. What is the risk of calling `auditRepository.save(...)` inside `AFTER_COMMIT` without opening a new transaction?
7. Why should you call **another bean** with `@Transactional(REQUIRES_NEW)` to write audit records?
8. If an `@Async` worker publishes an event while the original JDBC transaction lives on the request thread, which transaction does the listener bind to?
9. With `@Async` on a transactional listener, which thread awaits the transaction outcome and which thread receives the body execution?
10. If the main transaction already committed yet the async listener fails, can the old commit be rolled back?
11. If an inner method invoked via `REQUIRES_NEW` publishes an event and commits, and the outer transaction later rolls back, what will the inner event's listener do?
12. In Spring 6.1+, what context do reactive transactions use and why is `TransactionalEventPublisher` needed?
13. Why does `@TransactionalEventListener` not replace a transactional outbox when messages must never be lost?
14. If an outbox worker crashes after sending a message but before marking it sent, how must the system handle duplicates?
15. Why should you avoid putting `@Transactional` on a test method when expecting after-commit assertions to run immediately?
16. How can you test that a listener does not run on rollback without arbitrary time waits?
17. Which data sources distinguish "transaction committed" from "notification sent successfully"?
18. When a publisher legitimately runs outside a transaction, what criteria allow enabling `fallbackExecution` without breaking business invariants?

## 20. Official References

- [Spring Framework Reference — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — TransactionalEventListener Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — TransactionPhase Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/event/TransactionPhase.html)
- [Spring Framework — TransactionSynchronization Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/support/TransactionSynchronization.html)
- [Spring Framework — TransactionTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework — TransactionalApplicationListener Javadoc](https://docs.spring.io/spring-framework/docs/6.2.6/javadoc-api/org/springframework/transaction/event/TransactionalApplicationListener.html)
- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — TransactionalEventPublisher (Reactive)](https://docs.spring.io/spring-framework/docs/6.1.12/javadoc-api/org/springframework/transaction/reactive/TransactionalEventPublisher.html)

**Takeaway:** `@TransactionalEventListener` binds **listener invocation timing to transaction outcomes**: `AFTER_COMMIT` by default, alongside `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. It does not automatically create a new transaction or a durable queue. When you need post-commit DB writes, explicitly open **`REQUIRES_NEW`**; when events must not be lost, persist an **outbox in the originating transaction**; when combining with `@Async`, check threads/contexts, submission failures, and executor lifecycles.