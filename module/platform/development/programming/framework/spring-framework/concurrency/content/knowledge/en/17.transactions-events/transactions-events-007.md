# Asynchronous Internal Events Do Not Replace Durable Queues

## 1. The Distinction to Make: Decoupled Execution Timing vs. No Lost Work

In Spring Framework, `ApplicationEventPublisher.publishEvent(...)` lets a bean emit an event for listeners inside the `ApplicationContext` to react to. You can pair `@EventListener` with `@Async` or configure an `ApplicationEventMulticaster` to offload processing to a thread pool. This fits internal notifications, reduces coupling, and moves non-urgent work off the request thread.

However, **"handed work off to another thread" does not mean "persisted work into a durable queue"**. A `ThreadPoolTaskExecutor` typically holds queued `Runnable` tasks in JVM memory. When the JVM crashes unexpectedly, the container is killed, power fails, or the process is replaced before draining, **tasks living only in memory have no automatic recovery guarantee**. If a listener throws an exception, standard Spring event infrastructure also does not provide per-event state persistence, post-restart retries, dead-lettering, or durable auditing out of the box.

Similarly, `@TransactionalEventListener(phase = AFTER_COMMIT)` ensures a listener runs *after the publisher's transaction commits successfully*, yet **does not turn an event into a durable record**. A risk window remains: business data has committed, while the JVM dies before executing the listener or persisting the task safely.

Ask the question in two layers:

1. **Asynchronous execution:** does the caller need to wait for the listener to finish? Do we want to shorten request latency and decouple modules inside the same application?
2. **Durable delivery:** if the process dies at any moment, can we still find unprocessed events, retry under control, avoid duplicate side effects, and monitor progress?

`@Async` primarily addresses the first layer. The second layer requires **durable persistence and delivery design**: a transactional outbox, a durable event publication registry, or a broker/queue configured for durability alongside idempotent consumers.

## 2. Four Concepts That Must Not Be Equated

| Concept | What does it mean? | What does it NOT guarantee? |
| --- | --- | --- |
| Spring application event | Delivers notifications to listeners in `ApplicationContext` | Durable storage, replay after restart, delivery across processes |
| `@Async` or async executor | Hands callbacks to an executor to run on its schedule | Task completed, data committed, task surviving crashes |
| `@TransactionalEventListener(AFTER_COMMIT)` | Binds a callback to the successful transaction commit phase | An event record stored for post-crash recovery |
| Durable broker/queue/event log | Stores messages outside application memory per infrastructure contract | "Exactly once" at business side-effect level, or automatic atomic sync with source DB |
| Transactional outbox / publication registry | Persists intent to emit an event in a durable store, usually within the business data tx | Consumers never seeing duplicates; requires relay, retries, and idempotency |

**Durability is not a binary attribute judged merely by product name.** Whether a broker stores messages durably depends on message persistence settings, replication/quorum, producer acknowledgements, consumer acknowledgements, retention, TTL, and operational policy. Nor does a durable queue automatically guarantee every consumer side effect executes once and only once.

## 3. Spring Events Are Synchronous by Default; @Async Changes Execution Scheduling

In standard Spring Framework, the default `ApplicationEventMulticaster` dispatches events synchronously. When a publisher calls:

```java
events.publishEvent(new OrderPlaced(orderId));
```

an `@EventListener` is normally invoked immediately on **the publisher's thread** before `publishEvent` returns. If the publisher is inside an imperative transaction, a synchronous listener can participate in that same thread and transaction context per configuration. This can be helpful for internal actions that must finish in the same flow, though it can also extend transaction/request duration.

If a listener is marked `@Async("eventPool")` and `@EnableAsync` is enabled, qualifying listener invocations pass through Spring async advice and are submitted to the chosen executor. The caller can proceed before the listener completes.

Two cases to distinguish:

```text
A. Regular @EventListener (default)

publisher --publishEvent--> listener runs on publisher thread
                                |
                                +-- done/error --> publishEvent returns

B. @Async @EventListener (with @EnableAsync, proxy, matching executor)

publisher --publishEvent--> async advice --> submit to executor
           |                                      |
           +-- can continue                       +--> worker runs listener later
                                                       (task may sit queued in RAM)
```

Note: `publishEvent(...)` is defined as **handing a notification to the event multicaster**, not a receipt stating "every listener has finished and committed side effects". Exact synchronous vs. asynchronous execution depends on the multicaster, listener, and framework configuration.

Spring allows configuring `SimpleApplicationEventMulticaster.setTaskExecutor(...)` to run listeners asynchronously; that differs from placing `@Async` on a specific listener. In Spring 6.2.x, listeners declaring no support for async execution — such as transaction-synchronized listeners — still need processing on the publishing thread to register transaction synchronization properly. Therefore **do not conclude that simply configuring an async multicaster makes every listener run on another thread**.

## 4. Runnable Spring Framework 6.2.9 + Java 17+ Example

This example illustrates an internal event dispatched to a `ThreadPoolTaskExecutor` worker. We use a bounded `CountDownLatch` to wait, because checking a variable right after `publishEvent` could observe the worker before it even starts. Observations are stored in a separate `Probe` bean to avoid confusing AOP proxy internals with target bean state.

Maven layout:

```text
local-event-demo/
├── pom.xml
└── src/main/java/demo/LocalEventDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>local-event-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.9</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/LocalEventDemo.java`:

```java
package demo;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class LocalEventDemo {

    @Bean("eventPool")
    public ThreadPoolTaskExecutor eventPool() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(1);
        pool.setMaxPoolSize(1);
        pool.setQueueCapacity(8);
        pool.setThreadNamePrefix("event-worker-");
        return pool;
    }

    public record OrderPlaced(long id) {}

    // Separate bean for testing, not an outbox or event store.
    public static class Probe {
        final CountDownLatch done = new CountDownLatch(1);
        volatile long seen;
        volatile String worker;
    }

    @Bean
    public Probe probe() {
        return new Probe();
    }

    @Bean
    public Receiver receiver(Probe probe) {
        return new Receiver(probe);
    }

    public static class Receiver {
        private final Probe probe;

        public Receiver(Probe probe) {
            this.probe = probe;
        }

        @Async("eventPool")
        @EventListener
        public void on(OrderPlaced event) {
            probe.seen = event.id();
            probe.worker = Thread.currentThread().getName();
            probe.done.countDown();
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(LocalEventDemo.class)) {
            Probe probe = context.getBean(Probe.class);
            String caller = Thread.currentThread().getName();

            context.publishEvent(new OrderPlaced(7L));

            if (!probe.done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Listener timed out");
            }

            System.out.println("order id = " + probe.seen);
            System.out.println("pool worker = "
                    + probe.worker.startsWith("event-worker-"));
            System.out.println("different thread = "
                    + !caller.equals(probe.worker));
        }
    }
}
```

Run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.LocalEventDemo
```

Stdout printed by the program:

```text
order id = 7
pool worker = true
different thread = true
```

**Explanation:**

1. `@EnableAsync` enables async proxy infrastructure. `@Async("eventPool")` selects the specific executor bean for the listener.
2. `context.publishEvent(new OrderPlaced(7L))` hands the internal event to the application context; the callback is scheduled on `eventPool`.
3. `CountDownLatch` lets `main` wait up to 5 seconds to verify the callback ran. Without waiting, assertions could race against the worker.
4. `Receiver` records the ID and thread name on `Probe`; two checks verify the target listener ran on a pool worker rather than the caller.
5. After `try`, the application context closes and Spring manages the executor bean lifecycle.

An equivalent execution path was verified with Spring 6.2.9/JDK in JShell: all three output lines match. The example **has no database, broker, outbox, or recovery mechanism**, so it only proves the event is handled on a worker **while the application stays alive**, never durable delivery. If another event were sitting in the queue and the process were killed before the worker picked it up, an in-RAM queue has no contract to replay it after restart.

## 5. Failure Windows: Why In-RAM Callbacks Can Be Lost

Consider an order-creation request:

```text
HTTP request
    |
    +-- write order to database
    |
    +-- publishEvent(OrderPlaced)
    |
    +-- worker sends email / updates secondary system
```

When using a plain `@Async @EventListener`, several failure windows exist:

| Failure timing | What can happen | Does default internal Spring event fix it? |
| --- | --- | --- |
| After emitting the event but before the listener starts | Task only sits in an in-RAM queue; crash loses pending tasks | No durable replay |
| After the listener starts but before the side effect | Worker loses progress; no record of in-flight work | No default post-restart retry |
| Listener calls external API successfully, then JVM dies before saving completion state | State is not saved; naive retry could trigger the side effect twice | No automatic idempotency |
| Executor queue is full and pool rejects new tasks | Dispatch path can throw a rejection depending on configuration | Does not turn rejections into a durable backlog |
| Listener throws an exception while running async | Error does not automatically return to caller to roll back business tx | Needs handlers, logs, retries, and business controls |
| Deploy / scale down with slow processing | Graceful shutdown may drain some tasks per config within a time limit | No guarantee under `kill -9`, OOM, or power loss |

Do not conclude that **every restart loses every task**. If shutdown provides a long enough grace period, some tasks can finish. The architectural point is **there is no guarantee of recovering unfinished tasks when a process terminates unexpectedly**.

A successful HTTP response or returning from `publishEvent` only proves what that API itself guarantees; **it is not a receipt from the consumer**, much less proof that data was persisted durably in an independent store.

## 6. Transactions: @EventListener Is Not @TransactionalEventListener

Inside a `@Transactional` method:

```java
@Transactional
public void placeOrder(CreateOrder command) {
    Order order = repository.save(new Order(command.customerId()));
    events.publishEvent(new OrderPlaced(order.getId()));
}
```

This is an **integration snippet for Spring Data/transactions**, not standalone Java. `placeOrder` must genuinely be invoked through a Spring transactional proxy with a transaction manager. With a regular synchronous listener, the listener can execute **before the transaction commits**. If it sends an email immediately and the transaction later rolls back, the email went out for a nonexistent order: a consistency bug.

Adding `@Async` does not fix this automatically. A listener on another thread can still start **before commit**, without the publisher's transaction context, and when querying the database it may fail to see the order under the DB's isolation level.

Spring provides:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onCommitted(OrderPlaced event) {
    // Runs when the publisher's transaction commits successfully.
}
```

This is a **method fragment inside a Spring-managed bean**, requiring `@TransactionalEventListener` and `TransactionPhase` imports. The default phase is `AFTER_COMMIT`, though stating it explicitly makes intent clear to readers.

Other phases are `BEFORE_COMMIT`, `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. If **no transaction is currently running**, a transaction-bound listener **is not invoked** unless `fallbackExecution = true` is set; when fallback is enabled, semantics depend on the scenario and must be clearly specified.

In Spring Framework 6.2.x, transaction-bound listeners use synchronizations registered on the transaction-owning thread. Never assume a `@TransactionalEventListener` automatically runs on a worker merely because a global multicaster is configured as async. If the business listener should run asynchronously after commit, combine `@Async`/an executor properly, remembering that **the after-commit phase does not turn a RAM queue into a durable queue**.

## 7. AFTER_COMMIT Fixes Ordering, Not the Event-Loss Gap

Compare the timeline steps:

```text
T0   Start DB transaction
T1   Write order
T2   Register event / AFTER_COMMIT listener
T3   COMMIT order data succeeds
T4   Spring starts invoking post-commit callback / submitting async task
T5   Worker executes side effect
```

If the process dies **between T3 and T4**, order data has committed, yet the callback has not been handed off to any durable store. If it dies **between T4 and T5**, the task may sit in an executor's RAM without finishing. Neither case has automatic recovery through `@TransactionalEventListener` alone.

This means:

- `AFTER_COMMIT` is very useful for **not reacting to rolled-back transactions** and avoiding pre-commit reads.
- It **does not persist a message to a DB/broker** as part of the source transaction.
- If a post-commit callback writes new data to the DB, understand resource and transaction boundaries. In some thread-bound contexts, old transaction resources can remain attached briefly; you need an explicit new transaction — typically `@Transactional(propagation = REQUIRES_NEW)` on a suitable Spring-managed service/worker — rather than expecting post-commit writes to auto-commit on their own.
- If the event runs on another worker, the publisher's transaction **does not propagate** to the worker. The worker needs its own transactional boundary if business rules require one.

**Never read "after commit" as "already written to a queue".** It only defines callback timing within the transaction lifecycle.

## 8. Durable Pattern: Transactional Outbox

When secondary work must run once an order exists — such as notifying inventory, billing, or an integration system — persist the **intent to emit an event** somewhere recoverable.

Common pattern:

```text
                   SINGLE DB TRANSACTION
+----------------------------------------------------+
| UPDATE orders SET status='PLACED' ...              |
| INSERT INTO outbox(event_id, type, payload, ...)  |
| COMMIT                                             |
+----------------------------------------------------+
                       |
                       v
               Durable outbox rows
                       |
                       v
              Background relay / CDC
                       |
                       v
             Broker persists message (with ack)
                       |
                       v
             Consumer receives, processes, acks
                       |
                       +--> Dedup by event_id
                       +--> Retry / DLQ / monitoring
```

The pivotal requirement: **persist business state and the outbox record in the same transaction on the same storage engine supporting atomic commit**. When the transaction rolls back, both the order and the outbox record roll back; when it commits, both survive durably per DB guarantees. The relay can run afterward, even across restarts.

An outbox row should contain at least: a unique `event_id`, `aggregate_type`, `aggregate_id`, `event_type`, `schema_version`, `payload` or reference, `created_at`, and status/attempt metadata when polling. Generate a stable `event_id` for **one business intent**, rather than generating endless new IDs on every retry.

To illustrate the model, here is **PostgreSQL pseudo-SQL** with illustrative table/column names:

```sql
BEGIN;

UPDATE orders
SET status = 'PLACED'
WHERE id = 42;

INSERT INTO outbox_events (
    event_id, aggregate_id, event_type, payload, status
) VALUES (
    'c44a7b4e-1fd0-4a4e-85c2-f11fa35a8368',
    42,
    'OrderPlaced',
    '{"orderId":42,"version":1}',
    'PENDING'
);

COMMIT;
```

Committing both statements together creates business+outbox atomicity. Do not use two separate DB transactions and call them a consistent outbox; without proper distributed transactions, a window remains where one commits and the other does not.

### The Relay Must Confirm Before Marking Sent

A polling relay typically:

1. Claims a batch of `PENDING` rows with locking/leasing so multiple relays do not pick duplicates uncontrollably.
2. Publishes each message to the broker with appropriate persistence/confirmation settings.
3. **Only after receiving a strong enough producer confirm/ack**, marks the record sent (or transitions it to broker-received).
4. If publish/confirm fails, leaves it unmarked as sent and retries with backoff.
5. Collects metrics on backlog size, oldest event age, retry counts, and persistent failures.

A relay can die **after the broker accepted the message but before marking the outbox row SENT**. After restarting, the relay resends the record. That is one reason **at-least-once delivery normally goes hand in hand with idempotent consumers**. Never mark SENT before broker confirmation, or failed publishes will silently lose events.

Durable queues do not eliminate duplicates; they give you safe replayability when properly engineered.

## 9. Idempotent Consumers: Accepting That Duplicates Happen

Even durable brokers can redeliver:

```text
Consumer receives message E
    |
    +--> DB side effect written successfully
    |
    +--> Consumer dies BEFORE acking broker
    |
    +--> Broker redelivers E
```

Without deduplication, the system could double-charge, send two emails, or double-credit inventory. Design **idempotency** around `event_id` or a business key matching the side effect type:

- For DBs, use a `processed_events(consumer_name, event_id)` table with a **unique constraint**. Inside the same DB transaction as the side effect, insert the marker conditionally; if it already exists, treat the event as processed and skip re-applying the side effect.
- For external APIs, pass an **API-supported idempotency key** or stable business operation ID. Checking only your own DB **cannot prevent** an external API from executing twice if local state and external state do not commit atomically.
- For notifications/emails, consider deduplication at dispatch or provider level, and define how much duplicate risk is acceptable.
- Ack the broker **after** durable processing succeeds, never immediately upon receiving the message.

Conceptual PostgreSQL example for a consumer (illustrative snippet; must run in the same transaction as the side effect):

```sql
BEGIN;

INSERT INTO processed_events (consumer_name, event_id)
VALUES ('inventory', 'c44a7b4e-1fd0-4a4e-85c2-f11fa35a8368')
ON CONFLICT DO NOTHING;

-- Execute UPDATE stock only if the INSERT above
-- actually inserted a new row; on conflict, skip the side effect.

COMMIT;
```

This is **not a complete consumer yet**, since the application must check the INSERT's affected row count and update stock only in the inserted branch. Ensure the marker and side-effect transaction are atomic and roll back together on failure. If the broker/driver supports its own transactions, still clarify the atomicity boundary between broker and DB.

Conclusion: the practical target is usually **at-least-once + idempotent processing**, rather than claiming application-level "exactly once" merely because a broker offers a transaction feature.

## 10. Spring Service Example: Writing Order and Outbox in One Transaction

In Spring Data JPA or JDBC, the reliable emission point is not `ApplicationEventPublisher`, but **writing an outbox record** in the business transaction. The architectural snippet below uses hypothetical application classes/repositories and is **not a standalone runnable Java file**:

```java
@Service
public class OrderCommandService {
    private final OrderRepository orders;
    private final OutboxRepository outbox;

    public OrderCommandService(
            OrderRepository orders,
            OutboxRepository outbox) {
        this.orders = orders;
        this.outbox = outbox;
    }

    @Transactional
    public long placeOrder(NewOrderCommand command) {
        Order order = orders.save(Order.newFrom(command));

        OutboxEvent event = OutboxEvent.pending(
                UUID.randomUUID(),
                "OrderPlaced",
                order.getId(),
                1,
                "{\"orderId\":" + order.getId() + ",\"version\":1}"
        );

        outbox.save(event);
        return order.getId();
    }
}
```

`OrderRepository`, `OutboxRepository`, `Order`, `OutboxEvent`, and `NewOrderCommand` are **domain abstractions you must implement**; this snippet only shows **one transactional boundary** covering both business data and the outbox. With JPA, auto-generated IDs must be assigned/flushed before appearing in payloads; real projects should serialize with explicit schemas/versions using Jackson or an equivalent library rather than manual JSON string concatenation.

If `orders.save` succeeds yet `outbox.save` fails the transaction, **the entire transaction rolls back**, avoiding a state where "order saved but event missing" when the transaction manager and DB are configured properly. The caller returns success only once the transaction commits; APIs should also distinguish commit from downstream consumer completion.

Afterward, an independent **outbox relay** handles broker publishing without forcing the request transaction handler to send messages directly. You can use a scheduled job, dedicated worker, or CDC depending on volume and latency needs. To wake the relay quickly, an internal Spring event can still act as a **latency-optimization nudge**, while **the outbox record remains the source of truth**: losing an in-RAM signal must never lose committed work.

```text
DB transaction stores order + outbox
              |
              +-- local event signal (optional, may be lost)
              |
              +-- scheduled relay still scans durable outbox
```

Never make the local signal the sole condition for the relay to operate.

## 11. When Do You Need a Broker vs. an Application Event Registry?

Not every system needs Kafka or RabbitMQ right away. The choice depends on process boundaries, throughput, recovery SLAs, and replay requirements.

| Requirement | Typical suitable option | Caveat |
| --- | --- | --- |
| Non-critical internal UI updates that can be recomputed | `@EventListener` or `@Async @EventListener` | Accepts losing a notification on crash |
| Purely optimization-oriented cache invalidation | Local event with cache TTL/rebuild | Never treat cache events as source of truth |
| Simple email where losing an email is a business incident | Durable job record/outbox and retries | Email sent with failed ack can cause duplicates |
| Communication across multiple processes/services | Broker/queue with durable configuration | Needs outbox or atomic publishing on source side |
| Critical workflows inside a modular monolith | Durable event publication registry or outbox | Verify state persistence, recovery, and module idempotency |
| Needs replay, fan-out, long retention | Event log/broker and consumer state | Needs schema evolution, offsets/acks, quotas, and permissions |
| Background tasks that can be lost with no data harm | In-memory executor is sufficient if accepted | Document SLA and recomputation path |

**Spring Modulith Event Publication Registry** is an option in the Spring ecosystem for modular monoliths: the registry can persist publication records for transaction-bound listeners inside the source transaction and mark them completed once the listener succeeds. Versions/options provide a resubmission API; restart recovery and status monitoring must be verified against **the exact version in use**, rather than assuming every starter enables auto-republication. This is an **additional component to install and configure**, not something built into Spring Framework core or `@EventListener` alone.

An external broker also does not solve the dual-write gap by itself. For instance, "DB commits order; Kafka publish fails" still drops the event without an outbox, transaction coordination, or compensating/recovery mechanism. Always examine the source system's transaction boundary.

## 12. Distinguishing Internal Events From Public Inter-Service Messages

A local event can carry Java objects directly:

```java
public record OrderPlaced(long orderId) {}
```

Within a single process, this event needs no serializer or schema registry. When crossing to a broker, an event typically must:

- Have a unique `eventId`, `eventType`, `schemaVersion`, `occurredAt` or timestamp metadata, and `aggregateId`/business key.
- Carry an **ID or immutable data snapshot** — never a JPA entity attached to an `EntityManager`/`Session`, a stream, or a request-lifecycle object.
- Maintain compatible schemas as producers and consumers upgrade independently; field changes need clear versioning policies.
- Exclude secrets, tokens, or unnecessary personal data, since brokers involve retention, replication, and multiple consumers.
- Define ordering: partition by aggregate/partition key when business rules demand it, while **never assuming global ordering across multiple partitions**.
- Define timeouts, retries, and authorization for publishers/consumers.

An event payload carrying only an order ID lets consumers query the DB for the latest state, **not necessarily the state at event time**. If business logic requires a historical snapshot, carry the version or fixed values in the event; if consumers fetch fresh data, account for **eventual consistency**.

## 13. Rejections and Backpressure: Not Just Picking a Bigger Queue

For `ThreadPoolTaskExecutor`, three parameters matter:

- `corePoolSize`: core worker count.
- `maxPoolSize`: ceiling to which the pool can scale threads.
- `queueCapacity`: task queue capacity.

When core threads are busy, the executor normally **enqueues first** while the queue has room. Once full, the pool tries scaling workers up to max; when it cannot accept a task, it can throw `TaskRejectedException` per Spring's contract.

Enlarging the queue only absorbs bounded bursts; **it does not create durability**. A RAM queue holding thousands of events still vanishes if the process crashes suddenly. Overly long queues also raise latency, hold memory, and can make notifications stale.

With a broker, backpressure is also essential:

1. Limit in-flight messages, prefetch/concurrency, and consumer memory.
2. When downstream is overloaded, slow down, retry with backoff/jitter, and cap attempts.
3. Use a DLQ/quarantine for poison messages after retry exhaustion, with controlled replay tooling.
4. Monitor `oldest_unprocessed_age`, queue depth, delivery lag, failure/retry counts, and side-effect durations.
5. Alert when the outbox backlog grows even while HTTP requests keep succeeding.

If internal `publishEvent` hits a rejection, catching and "skipping for now" is acceptable **only when** business rules classify the event as best-effort or a durable outbox will recover it. Never turn lost critical events into meaningless "log warning" noise.

## 14. Errors in @Async Listeners Do Not Return to Callers Like Synchronous Exceptions

Given a listener:

```java
@Component
public class EmailListener {
    @Async("eventPool")
    @EventListener
    public void on(OrderPlaced event) {
        // Suppose an IOException or email-provider error occurs.
        sendEmail(event.id());
    }
}
```

This is an **illustrative snippet needing `@Component`, imports, `eventPool` bean, and `sendEmail` method**, not a standalone program. Once the listener is handed to a worker, exceptions raised during execution **are not rethrown back** to the caller's `publishEvent` call. With `@Async void`, you need an `AsyncUncaughtExceptionHandler` or appropriate logs/metrics.

Pitfalls to avoid:

- **Relying solely on `try/catch` around `publishEvent`:** it can catch dispatch/submission failures, not subsequent worker failures.
- **Treating `@Async` as a retry framework:** Spring does not persist delivery attempts or replay events after restarts.
- **Using an async `@EventListener`'s return value to publish follow-up events:** Spring docs note return-value event publishing is unsupported for async listeners; to emit new events, inject `ApplicationEventPublisher`, publish explicitly, and design reliability separately.
- **Assuming `@Order` enforces synchronous completion order across workers:** listeners may be invoked in dispatch order, yet async completion order is not guaranteed.
- **Assuming the publisher's transaction ThreadLocal appears automatically on the worker:** there is no such guarantee; open a new transaction on the worker if business logic needs one.

For critical work, observing errors via `AsyncUncaughtExceptionHandler` is insufficient without **persistent records and a retry/recovery policy**.

## 15. What Should a Realistic Failure Test Cover?

A test checking "listener runs when everything goes well" proves nothing about delivery guarantees. Mandatory scenarios to consider:

| Test scenario | With local event + @Async | With properly designed outbox + durable delivery |
| --- | --- | --- |
| Listener succeeds while JVM stays up | Usually works | Must work |
| Business transaction rolls back | Listener may run prematurely if not phase-bound | Outbox record rolls back alongside business state |
| Process dies after DB commit before listener runs | Risk of losing the event | Outbox record survives; relay recovers after restart |
| Process dies after broker confirm before outbox marked sent | No durable state to reason from | Relay can resend; consumer must deduplicate |
| Consumer writes DB successfully then dies before broker ack | No matching broker ack | Message can be redelivered; consumer handles idempotently |
| Broker temporarily down | In-memory listener does not persist retries across restarts | Relay keeps outbox PENDING and retries per policy |
| Queue fills up | May reject immediately | Backlog/flow control handles it, though bounds remain needed |
| Multiple instances with rolling restarts | Local events exist only in the current instance's context | Shared event store/broker provides claim/ack and durable storage |

Build fault-injection tests in a permitted environment: stop the process right after commit before relay; sever broker connectivity; kill a consumer after its side effect before acking; deliver the same `eventId` twice; emit an older-schema-version event; restart and reconcile **all committed events** against processed events.

A durability test should verify at least these invariants:

- Every successful business transaction writes **exactly one event intent** in the outbox per defined business key.
- Zero event intents exist when the transaction rolls back.
- Every incomplete intent remains queryable after restart.
- Across retries/redeliveries, external side effects are never duplicated contrary to contract.
- Rows are marked SENT/ACKED only with proper confirmation evidence.
- Backlogs drain back to normal once dependencies recover.

Never induce crashes in production or send uncontrolled load just to prove a pattern; use proper isolation and teardown.

## 16. Monitoring: Observe End-to-End Delivery, Not Just "Event Published" Logs

For internal events, useful metrics include:

- Events published vs. events received by listeners, split by event type.
- Executor active threads, queue size/capacity, rejections.
- Time from publish to listener start and to listener completion.
- Listener failure/timeout rates; context loss/propagation during async execution.

For durable pipelines, also monitor:

- Count of `PENDING`, `PROCESSING`, and `FAILED` outbox records; age of oldest record.
- Producer confirmations, publish errors, retry counts, and retry durations.
- Consumer lag/prefetch/in-flight counts, ack/nack rates, DLQ volume.
- Deduplicated event counts, schema-deserialization failures.
- Latency from **business commit to side-effect completion**, not just HTTP response time.
- Reconciliation data comparing business rows, outbox records, and processed-event markers.

When an event is known to have committed without reaching a handled state, a durable system must have **a replay path and alerting**. A system that only logs "publish successful" without knowing whether listeners finished is **best-effort** and cannot guarantee delivery deadlines.

Because async processing runs side work after commit, the system can be **eventually consistent**: an order is `PLACED` in the DB while its email or inventory projection has not updated yet. APIs/UIs should surface `PENDING`/`IN_PROGRESS`/`FAILED` states when lag matters, rather than returning a blanket "done" flag based solely on business commit.

## 17. Common Mistakes

1. **Calling `@Async` a queue:** it schedules tasks; executor queues are typically in-memory structures without automatic replay.
2. **Saying `@EventListener` is asynchronous by default:** Spring application events are dispatched synchronously by default.
3. **Assuming `publishEvent()` returning means listeners succeeded:** false for async, and even synchronous dispatch is not a durable acknowledgement.
4. **Saying `@TransactionalEventListener(AFTER_COMMIT)` prevents message loss:** it only binds phase; the JVM can still crash before the handler is recorded.
5. **Calling an external API inside a transaction before commit assuming rollback undoes it:** external side effects outside the DB do not roll back automatically.
6. **Writing to the DB then publishing to a broker in two independent steps without handling the dual-write gap:** one can succeed while the other fails.
7. **Marking an outbox row SENT before producer confirmation:** publish failures can lose the event while the DB claims it was sent.
8. **Assuming "at least once" means zero duplicates:** resends after crashes are normal and require idempotency.
9. **Putting the dedupe marker in a different transaction from the DB side effect:** the marker can commit while the side effect fails, or vice versa.
10. **Passing an attached JPA entity as an async event payload:** transactions/persistence contexts do not follow threads, and LAZY getters can fail.
11. **Making `queueCapacity` huge to be "more durable":** this only piles up in-RAM work, raising memory/latency risk and still losing everything on crash.
12. **Not monitoring outbox lag and DLQs:** durable storage without relay/recovery runbooks still misses completion SLAs.
13. **Confusing an event publication registry with Spring core features:** durable registries require separate dependencies, storage, and configuration.
14. **Assuming a broker automatically gives exactly-once for HTTP/DB side effects:** you still need transaction boundaries, idempotency, and recovery design.
15. **Treating graceful shutdown as identical to a crash:** graceful shutdowns can drain queues, but offer no guarantee against sudden failures.
16. **Failing to define a business contract for loss, delay, and duplicates:** technical choices are only right when aligned with acceptable business reliability.

## 18. Case Studies and Self-Check Questions

**Question 1.** A system uses `@Async @EventListener` to send emails after receiving orders. When the JVM is killed before a worker pulls the task from the queue, does Spring automatically resend the email?  
**Answer:** There is no default guarantee. In-memory queues do not survive crashes; durable intent storage and recovery are required.

**Question 2.** Does changing the listener to `@TransactionalEventListener(AFTER_COMMIT)` completely eliminate event loss?  
**Answer:** No. It fixes ordering relative to business commit and skips rolled-back transactions, yet does not persist the publication. A crash right after commit can still lose the callback.

**Question 3.** How can saving an order and recording the intent to emit an event succeed or fail together?  
**Answer:** Persist both the order and the outbox record inside **the same DB transaction** with atomic commit.

**Question 4.** A relay successfully sends to the broker, then crashes before marking SENT. What happens?  
**Answer:** Upon restart, the relay can resend the same event. Consumers must use stable event IDs with idempotency/deduplication.

**Question 5.** A consumer persists a DB side effect and then dies before acking. Can the broker redeliver?  
**Answer:** Yes, under at-least-once semantics. The dedupe marker and DB side effect should commit together in the same appropriate transaction.

**Question 6.** Using a regular `@EventListener` inside `@Transactional` to make an external HTTP call immediately — is this safe if the business transaction rolls back?  
**Answer:** No. The external side effect may already have executed even though the DB transaction rolled back.

**Question 7.** Is the Spring Modulith Event Publication Registry automatically present whenever `@EnableAsync` is enabled?  
**Answer:** No. It is an additional subsystem requiring its own dependencies and persistent store/republication configuration.

**Question 8.** When are local async events still good enough?  
**Answer:** When business rules **tolerate lost signals or have an alternative recomputation path**, replay across restarts is not needed, and executor latency/rejection bounds are well understood.

**Question 9.** Why is calling `publishEvent` not a "publish to Kafka" operation without a dedicated adapter?  
**Answer:** Plain `ApplicationEventPublisher` delivers events to the Spring ApplicationContext. It has no contract to write messages to an external broker; adapters, outboxes, or externalization must be designed explicitly.

**Question 10.** When email delivery must be guaranteed eventually, is retrying the listener infinitely in RAM enough?  
**Answer:** No. RAM cannot survive crashes; unbounded retries also add pressure and duplicates. You need persistent intent, bounded/backoff retries, idempotency, and status observability.

**Takeaway:** **Internal events decouple beans; `@Async` decouples execution timing; `AFTER_COMMIT` aligns with commit timing; properly configured outboxes, registries, or brokers provide durable persistence and recovery.** Always account for crash windows, duplicates, and side effects when reasoning about event reliability.

### References

- [Spring Framework — ApplicationContext Events and @EventListener](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework — ApplicationEventPublisher JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/ApplicationEventPublisher.html)
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html)
- [Spring Framework — TransactionalEventListener JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/transaction/event/TransactionalEventListener.html)
- [Spring Framework — SimpleApplicationEventMulticaster JavaDoc](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Modulith — Working with Application Events / Publication Registry](https://docs.spring.io/spring-modulith/reference/events.html)
- [Java SE 17 — ThreadPoolExecutor](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/ThreadPoolExecutor.html)
