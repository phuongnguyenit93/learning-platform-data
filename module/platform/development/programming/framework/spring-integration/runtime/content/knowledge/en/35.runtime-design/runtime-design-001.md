# Intentional Thread Boundary Placement in Spring Integration Runtime

## Lesson Objectives

In the **SPRING_INTEGRATION_RUNTIME** module, messages are received from an inbound adapter, pass through **channels, endpoints, consumers, pollers, and executors**, and may then be written to a DB, MessageStore, broker, or sent to an external API. A seemingly simple decision such as changing a **DirectChannel** to an **ExecutorChannel** can completely alter **the thread executing the handler, transaction scope, exception propagation path, processing order, and when the source acknowledges the message**.

A **thread boundary** is the boundary where work **no longer continues in the same sender thread/call stack**, and is instead handed off to another thread or execution mechanism. In Spring Integration, this boundary is typically created by an **ExecutorChannel, QueueChannel with a polling consumer, PublishSubscribeChannel with an executor**, or adapters/gateways with asynchronous behavior.

The goal of this lesson is to learn how to **place thread boundaries intentionally**, rather than adding an executor merely hoping "the flow will be faster".

After this lesson, you will be able to:

1. Explain that **thread boundary**, **transaction boundary**, and **durability/ack boundary** are three related but non-identical concepts.
2. Compare **DirectChannel, ExecutorChannel, QueueChannel, and PublishSubscribeChannel** by thread, blocking, backpressure, ordering, and error handling.
3. Choose the right **handoff point** matching SLA and zero-message-loss requirements.
4. Understand why Spring transactions and many **ThreadLocals** do not automatically transfer from sender to worker thread.
5. Design **executor pools, bounded queues, rejection policies, retries, and timeouts** without causing overload or silent work loss.
6. Preserve **correlationId, eventId, tracing context** and test ordering/idempotency under concurrent processing.
7. Practice Java DSL with synchronous–asynchronous boundaries that have explicit IDs, observability, and testability.
8. Diagnose runtime incidents: **send() returns true yet the handler has not run, lost exceptions, unrolled-back transactions, duplicates after restart, exhausted pools, and lost messages after shutdown**.

> **Design Principle:** Only create a thread boundary when you can answer: **who owns the message after handoff, where is it stored, who acknowledges the source, how far do errors propagate, what happens under overload, and can it recover after a restart?**

## 1. What Is a Thread Boundary Really?

A synchronous flow:

~~~mermaid
sequenceDiagram
    participant S as Sender thread
    participant C as DirectChannel
    participant H as Handler
    participant D as Database
    S->>C: send(M)
    C->>H: handle(M) same thread
    H->>D: update/commit in transaction
    D-->>H: Result
    H-->>C: return
    C-->>S: send returns
~~~

A flow handed off to an executor:

~~~mermaid
sequenceDiagram
    participant S as Sender thread
    participant C as ExecutorChannel
    participant Q as Executor work queue
    participant W as Worker thread
    participant D as Database
    S->>C: send(M)
    C->>Q: submit handler task
    C-->>S: send may return
    Note over S,W: Sender may finish before business effect
    Q->>W: execute task
    W->>D: update/commit in worker context
    D-->>W: Result
~~~

With **DirectChannel**, the handler is invoked synchronously on the sending thread. With **ExecutorChannel**, dispatching is delegated to a **TaskExecutor**, so the handler **may** run later on a worker thread; the sender typically returns earlier.

This gives rise to three types of boundaries:

| Boundary | Core Question | Example |
| --- | --- | --- |
| **Thread boundary** | Is the handler still on the same thread as the sender? | ExecutorChannel dispatches to a worker |
| **Transaction boundary** | Does a single transaction span both producer and consumer? | A transaction on an inbound poller does not automatically cross an executor |
| **Durability / ack boundary** | Has the message been durably stored/acked before the sender returns? | Enqueuing to an in-memory executor differs from committing to a JDBC message store |

**A thread boundary does not automatically create a durable queue.** Conversely, a persistent QueueChannel can provide durable handoff, yet still requires proper transactions to prevent message loss after dequeue.

### Distinguish Concurrency from Asynchronous Handoff

A flow can have multiple **concurrent sender threads** while each sender still uses a DirectChannel and invokes the handler synchronously on its own thread. Therefore:

~~~text
Thread kafka-consumer-1 → DirectChannel → Handler A
Thread kafka-consumer-2 → DirectChannel → Handler A
~~~

**DirectChannel does not mean there is only one thread across the entire application.** It simply does not create a new thread boundary between send and handler. Shared state in the handler **must still be thread-safe** if multiple adapters/producers call it concurrently.

Conversely, an ExecutorChannel using a single-worker executor can create an **asynchronous handoff** without achieving high parallelism; throughput remains bounded by that single worker.

## 2. Comparing Channels by Runtime Contract

| Channel / Dispatch Mechanism | Where Does the Handler Run? | Does send() Wait for the Handler? | Does the Sender Transaction Automatically Span the Handler? | Where Are Waiting Messages Stored? |
| --- | --- | --- | --- | --- |
| **DirectChannel** | Usually the same sender thread | **Yes**, when the handler is synchronous | Can share the active transaction on the thread | Does not create its own queue |
| **ExecutorChannel** | TaskExecutor, usually a worker thread | **Usually no**; rejection policy exceptions exist | **Not guaranteed**, usually no | Executor queue/task memory per implementation |
| **QueueChannel + polling consumer** | Thread performing the poll/handler | **No**; sender only enqueues | Sender transaction does not automatically continue | In-memory queue or persistent ChannelMessageStore |
| **PublishSubscribeChannel without executor** | Subscribers run on the sender thread, via dispatcher | Usually yes | Can share the thread, depending on handler | Does not create separate task queues |
| **PublishSubscribeChannel with executor** | Can be multiple worker threads | Usually does not wait for all subscribers | Does not automatically span async branches | Executor/task queues |
| **Adapter with built-in async / reactive boundary** | Per adapter/scheduler/reactive execution | Depends on API/flow | Not by default | Depends on transport/buffer/subscription |

**Do not infer behavior from method names or channel names.** For example, **PublishSubscribeChannel** defaults to dispatching to subscribers on the **sender thread** when no executor is configured. Conversely, a **DirectChannel with multiple producer threads** still executes concurrently.

**Important exception for ExecutorChannel:** A TaskExecutor using **CallerRunsPolicy** may execute the task **directly on the sender thread when the pool/queue is full**. Because this only occurs depending on load, **never rely on CallerRunsPolicy to assume a shared transaction between sender and handler**.

### A Thread Boundary Does Not Imply Fan-Out

- **DirectChannel** and **ExecutorChannel** use point-to-point dispatch: with multiple subscribers, the dispatcher can select a handler via load balancing/failover.
- **PublishSubscribeChannel** is used for fan-out to multiple subscribers. With an executor, subscriber branches can run in parallel, and a failure in one branch must be handled according to the async contract.
- **QueueChannel** is a queue for a polling consumer to retrieve messages from; it does not automatically broadcast to all consumers.

Do not add a debug subscriber to a DirectChannel expecting every message to reach both the business handler and the debug handler. When observation is needed, use a **WireTap** or an explicitly designed structure.

## 3. When Should You Create a Thread Boundary?

A thread boundary is useful when **downstream processing cost and timing differ significantly from the work before the boundary**.

**Appropriate examples:**

- Keeping a message listener from waiting on a slow CPU/HTTP/DB operation, **if the source already has an appropriate durable handoff/ack mechanism**.
- Isolating blocking I/O work from request-receiving threads or source polling threads.
- Creating a **dedicated pool** for one workload type so it does not starve the entire application.
- Throttling concurrency: allowing only 8 concurrent requests to a capacity-limited downstream system.
- Using a persistent queue to smooth differing producer/consumer speeds and allow replay after restart.
- Separating independent processing branches with distinct error policies and SLAs.

**Examples where you should NOT add an executor just to "speed things up":**

- The handler is very short and lightweight; scheduling/queue overhead may outweigh any benefit.
- The inbound adapter already uses its own thread pool and concurrency is already sufficient.
- The business transaction must commit or roll back **before the source acks** without an independent durable handoff.
- A synchronous gateway requires an immediate result and still waits for a reply; switching to an executor may merely relocate the wait and complicate timeouts/correlation.
- The flow requires strict global ordering, which a multi-worker executor would break.

### A Quick Decision Flowchart

~~~mermaid
flowchart TD
    A["Want to place a thread boundary?"] --> B{"Is the handler slow or needing isolation?"}
    B -- "No" --> SYNC["Prefer DirectChannel + concurrency limit at source"]
    B -- "Yes" --> C{"Can the source ack before the handler completes?"}
    C -- "No" --> D{"Is there an appropriate durable handoff/transaction?"}
    D -- "No" --> KEEP["Keep synchronous processing or design a durable inbox/queue first"]
    D -- "Yes" --> ASYNC["Separate workers after durable commit"]
    C -- "Yes, semantics accepted" --> E{"How is overload handled?"}
    E -- "Has bounded queue/reject/backpressure" --> ASYNC
    E -- "Not yet" --> PLAN["Design capacity and recovery first"]
    ASYNC --> TEST["Test timeout, restart, redelivery, ordering, and metrics"]
~~~

**The core question is not "how many threads?" but "has responsibility for processing the message been safely handed over?"**

## 4. DirectChannel: Synchronous Path and Transaction Continuity

With **DirectChannel**, invoking the handler on the same thread allows a thread-bound transaction to span multiple steps.

~~~text
Kafka/JMS listener thread (depending on adapter/transaction)
    → DirectChannel
    → validate
    → businessHandler
    → DB update/commit
    → return or throw
    → adapter decides ack/nack per contract
~~~

Advantages:

- Exceptions can propagate back to the sender and trigger source rollback/error handling according to the adapter.
- Avoids creating an in-memory executor queue that is hard to observe.
- Synchronous invocation lets the caller know the handler has **returned/thrown** before send() completes.
- Easier to reason about transactions **provided** the transaction manager and resources are configured properly.

Disadvantages:

- A slow handler holds the sender thread for a long time.
- Multiple sender threads access the handler concurrently; stateful handlers still need thread safety.
- Backpressure can propagate upstream to the listener, HTTP gateway, or polling endpoint.
- If an external API call follows the handler, a DB transaction does not make that API call atomic with the DB.

### Same-Thread Transaction Does Not Make All Side Effects Atomic

~~~java
@Transactional
public void handle(OrderCommand command) {
    orderRepository.save(command.order());
    paymentProvider.charge(command.paymentId());
}
~~~

In this example, **@Transactional** can manage the DB transaction; it does not **roll back** the HTTP payment when the DB transaction rolls back, nor does it guarantee the broker ack participates in the same transaction. You need an **idempotency key, inbox/outbox, or reconciliation** whenever external side effects exist.

**Similarly:** If a **@Transactional** method is invoked via self-invocation where proxy advice is bypassed, what you assume to be a shared transaction may not exist. Test actual active/committed transactions rather than guessing from annotation placement.

## 5. ExecutorChannel: Fast at Handoff, Not Necessarily Fast End-to-End

**ExecutorChannel** submits a task to a **TaskExecutor** to dispatch the message to a subscriber. If the executor has available capacity, send() usually returns early. However, **business** completion time still includes queue wait time and handler execution time.

~~~text
T0   send(message) starts
T1   task accepted by executor
T2   send() returns: ~3 ms
T3   task starts running after queue wait: ~500 ms
T4   handler executes DB/HTTP: ~250 ms
T5   business effect completes: ~753 ms after T0
~~~

**A 3 ms dispatch latency is not a 753 ms business latency.**

### Two Distinct Failure Points

1. **Handoff failure:** Pool shutdown or overloaded queue causes the executor to reject the task. The error may surface immediately at send() depending on the implementation and rejection policy.
2. **Handoff succeeds but handler fails:** The worker throws an exception **after send() has already returned**. The error does not automatically return to the sender thread; an error flow/recovery mechanism must exist.

**Critical risk:** Default executor queues usually reside only in JVM memory. A task submitted to the executor that **has not yet executed** can vanish if the process is killed. If the inbound source already acked at handoff time, **work can be lost** even though the message was initially received successfully.

### Is CallerRunsPolicy a "Safe" Solution?

If the executor uses CallerRunsPolicy, when the pool is saturated, the sending thread may execute the handler directly. This provides simple backpressure, but makes execution mode **load-dependent**:

~~~text
Normal load: sender → worker thread
Full queue:  sender → the sender thread itself
~~~

Do not design transactions, security contexts, or error handling around **some messages unexpectedly running on the sender thread**. If the workload strictly requires the same transaction, use DirectChannel or an explicit transaction boundary. If you want consistent async behavior, choose a rejection policy/backpressure strategy with a clear contract.

## 6. QueueChannel: The Thread Boundary Lies at the Polling Consumer

**QueueChannel** is a PollableChannel. The sender places messages into the queue; a **PollingConsumer** performs receive() and invokes the handler, typically on a thread from the TaskScheduler/poller or a TaskExecutor configured on the poller.

~~~mermaid
sequenceDiagram
    participant S as Sender
    participant Q as QueueChannel
    participant P as Poller thread
    participant H as Handler
    S->>Q: send message
    Q-->>S: send accepted
    Note over S,P: Producer and consumer do not share a call stack
    P->>Q: receive()
    Q-->>P: message
    P->>H: handle()
    H-->>P: success/error
~~~

**No transaction automatically extends from sender to poller.** However, a **poller** can **start a new transaction on the consumer thread**, spanning both receiving from a transactional store and executing the handler synchronously. This is a meaningful way to establish a transaction boundary on the receiving side.

### In-Memory vs. Persistent QueueChannel

| Backing | Survives JVM Restart? | Design Considerations |
| --- | --- | --- |
| **Default QueueChannel** | No, state lives in JVM memory | Requires a replay-capable source or tolerance for message loss |
| **Bounded in-memory QueueChannel** | No | Enforces capacity limits but provides no durability |
| **JDBC ChannelMessageStore** | Can retain committed messages | Requires transactions, schema, serializer, and stable groupId/region |
| **Other persistent backends** | Depends on implementation and durability | Must verify receive/remove/recovery semantics |

### A Poller Transaction Does Not Automatically Span Downstream Handoff Workers

~~~text
Transaction A on poller thread:
    QueueChannel.receive()  [remove pending]
    ExecutorChannel.send()  [enqueue to in-memory task queue]
    COMMIT A

Worker thread:
    BusinessHandler.handle()
    process is killed before completion
~~~

If the message was durably removed from the QueueChannel after COMMIT A and the worker task only exists in RAM, a restart may **have no message left to replay**. Therefore, place the **durable handoff at the exact boundary where it is needed**, rather than just adding a JDBC store "somewhere" in the flow.

### Pollers Must Be Configured Explicitly

A PollableChannel does not consume messages on its own. An endpoint reading from a QueueChannel requires a **poller trigger**; maxMessagesPerPoll, receiveTimeout, advice chains, and transactions determine scheduling, batch size, and processing boundaries.

~~~xml
<int:service-activator input-channel="ordersQueue"
                       ref="orderHandler"
                       method="handle">
    <int:poller fixed-delay="200" max-messages-per-poll="5">
        <int:transactional
                transaction-manager="transactionManager"/>
    </int:poller>
</int:service-activator>
~~~

This is an XML fragment; namespaces, channels, and beans must be fully defined. If a downstream handler uses an ExecutorChannel, the poller's transaction **does not automatically cross that boundary**.

## 7. PublishSubscribeChannel and Asynchronous Fan-Out

A **PublishSubscribeChannel** can broadcast messages to multiple subscribers:

~~~mermaid
flowchart LR
    I["OrderAccepted"] --> P["PublishSubscribeChannel"]
    P --> A["Audit handler"]
    P --> B["Notification handler"]
    P --> C["Analytics handler"]
~~~

When configured **without an executor**, subscribers normally run synchronously on the sender thread. One slow handler can block the sender and delay other branches.

When using **PublishSubscribeChannel(executor)**, dispatching can run asynchronously, even in parallel. The benefit is decoupling branch execution time; the risks are:

- Exceptions do not automatically propagate back to the sender during async dispatch.
- You cannot assume all branches have finished when send() returns.
- The sender's transaction does not automatically span each branch's transaction.
- Subscriber completion order may differ from send order.
- **Success of the Audit branch does not guarantee success of the Notification branch**.
- If events must be durably processed by every branch, you need **durable fan-out** or dedicated outbox/broker/consumers.

### Correlating Messages When Branches Need to Join

If an aggregator/resequencer follows fan-out, branches need appropriate correlation/sequence metadata. Spring Integration supports **applySequence** on PublishSubscribeChannel; you need to understand how it generates sequence headers and how the group is released if one branch fails.

**Do not automatically use correlationId as an idempotency key:** A single order may emit multiple valid events within the same workflow; eventId/operationId must identify a specific business side effect.

## 8. Three Ways to Design Thread Boundaries for an Order Flow

Suppose the application receives **OrderSubmitted** from a broker, validates the data, persists state to PostgreSQL, and calls an external service. Three designs look functionally similar but have different reliability contracts.

### Option A — Synchronous Until Business Processing Completes

~~~mermaid
flowchart LR
    B["Broker consumer"] --> D["DirectChannel"]
    D --> V["Validate"]
    V --> H["Transactional business handler"]
    H --> DB[("PostgreSQL")]
    H --> ACK["Adapter acks after processing<br/>per source contract"]
~~~

**Suitable when** processing latency meets consumer requirements, you want errors to propagate back so the adapter can decide rollback/nack, and no extra async queue is needed. Throughput can still be scaled via **concurrent broker consumers**, even though each delivery passes through the handler synchronously.

**Caution:** HTTP side effects still do not belong to the same DB transaction. A specific adapter may ack at a different point; you must verify the container/ack mode rather than assuming it automatically from DirectChannel.

### Option B — Durable Inbox/Outbox Before Async Handoff

~~~mermaid
flowchart LR
    B["Broker consumer"] --> I["Validate + durable inbox/write"]
    I --> DB[("DB COMMIT")]
    DB --> ACK["Source ACK per policy"]
    DB --> W["Durable work rows / outbox"]
    W --> P["Worker poller"]
    P --> H["Async business processing"]
    H --> E["External API / outbound"]
~~~

**Suitable when** you do not want to tie up broker threads waiting on slow processing, yet cannot afford to lose work on a crash. The source is acknowledged **only after the durable handoff has been committed per contract**. Workers can restart and pick up unfinished work.

**Caution:** "Writing to inbox" must represent a unit of work that **a worker can resume**; do not mark it DONE and move on before downstream effects occur. Use a PENDING/PROCESSING/COMPLETED/UNKNOWN state machine, lease/reclaim when workers die, unique keys, and idempotency.

### Option C — ExecutorChannel Directly After Inbound

~~~mermaid
flowchart LR
    B["Broker consumer"] --> V["Validate"]
    V --> E["ExecutorChannel"]
    E --> Q["Executor queue<br/>in-memory"]
    Q --> H["Worker handler"]
    H --> DB[("DB")]
~~~

**Suitable when** you need isolation/parallelism and have an **explicitly accepted risk contract** or source/handoff coordination such that losing in-memory tasks does not cause business loss. It is **not inherently safe** for at-least-once business processing if the source acks immediately after send().

**Warning:** Do not choose Option C just because send() benchmarks "faster". If the process is killed after the sender receives success but before the worker runs, the message can disappear from the executor queue.

### Architecture Comparison

| Criterion | A: Sync | B: Durable Async | C: In-Memory Async |
| --- | --- | --- | --- |
| Handler blocks sender | Yes | Only during durable write phase | Usually no |
| Durability of pending work | Depends on source and ack | Can be guaranteed via committed durable state | Not provided by ExecutorChannel itself |
| Ingress→handler transaction | Can be shared when same thread/resource | Intentionally separated transactions | Not automatically shared |
| Retry/recovery | Adapter + handler policy | Durable worker retry + idempotency | Worker error flow; crash requires another source to replay |
| Complexity | Lower | Higher | Easy to build, easy to hide bugs |
| Scaling multiple replicas | Consumer concurrency/partitions | Shared work store/broker/leases | Task queue is local to each JVM |

## 9. Java DSL: Creating Thread Boundaries with Explicit Names, Pools, and Limits

The following example illustrates a flow that **intentionally places an ExecutorChannel after validation**, using a **bounded pool** and a business handler with its **own transaction on the worker thread**.

### Defining Channels and Executor

~~~java
import java.util.concurrent.ThreadPoolExecutor;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.dsl.IntegrationFlow;
import org.springframework.messaging.MessageChannel;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableIntegration
class OrderRuntimeFlowConfiguration {

    @Bean("ordersInput")
    MessageChannel ordersInput() {
        return new DirectChannel();
    }

    @Bean("ordersWorkerExecutor")
    ThreadPoolTaskExecutor ordersWorkerExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("orders-worker-");
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        return executor;
    }

    @Bean("ordersAsync")
    MessageChannel ordersAsync(ThreadPoolTaskExecutor ordersWorkerExecutor) {
        return new ExecutorChannel(ordersWorkerExecutor);
    }

    @Bean
    IntegrationFlow orderFlow(OrderValidator validator,
                              OrderProcessor processor) {
        return IntegrationFlow.from("ordersInput")
                .transform(validator, "validate")
                .channel("ordersAsync")
                .handle(processor, "process")
                .get();
    }
}
~~~

The **OrderValidator** and **OrderProcessor** beans must be registered in the context; sample implementations are shown below. A Spring-managed ThreadPoolTaskExecutor follows the bean lifecycle; if instantiated outside the container, you must manage initialize/shutdown yourself.

**Intentional decisions in this example:**

1. **ordersInput** is a DirectChannel; validation runs on the sender thread.
2. **ordersAsync** is an ExecutorChannel, creating an explicit, clearly named handoff point.
3. **ordersWorkerExecutor** is dedicated to the order flow, avoiding capacity contention with other flows.
4. **Core=4, max=8, queue=100** are illustrative parameters, not production defaults. With ThreadPoolExecutor, maxPoolSize generally scales up **only after the queue is full**, rather than running 8 workers immediately at all times.
5. **AbortPolicy** rejects tasks under overload: handoff failures must be handled by the sender/adapter rather than swallowed and falsely acked.
6. **The executor queue itself still resides in RAM**. This example demonstrates an async thread boundary, **not a complete durable processing design**.

### DTOs, Validator, and Handler

~~~java
record OrderCommand(String eventId, String orderId, long amountMinor) {}
record ValidatedOrder(String eventId, String orderId, long amountMinor) {}

class OrderValidator {
    public ValidatedOrder validate(OrderCommand input) {
        if (input.eventId() == null || input.eventId().isBlank()
                || input.orderId() == null || input.orderId().isBlank()
                || input.amountMinor() <= 0) {
            throw new IllegalArgumentException("Invalid order command");
        }
        return new ValidatedOrder(
                input.eventId(), input.orderId(), input.amountMinor());
    }
}

// Spring-managed bean, invoked through an appropriate endpoint/proxy.
class OrderProcessor {
    private final org.springframework.jdbc.core.JdbcTemplate jdbc;

    OrderProcessor(org.springframework.jdbc.core.JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @org.springframework.transaction.annotation.Transactional
    public void process(ValidatedOrder order) {
        jdbc.update(
                "UPDATE orders SET status='ACCEPTED' WHERE order_id=?",
                order.orderId());
    }
}
~~~

In a real application:

- Register OrderValidator and OrderProcessor as Spring beans; JdbcTemplate/DataSource must be configured.
- The process() handler runs on a **worker thread** when ExecutorChannel dispatches asynchronously. If the **@Transactional proxy** is applied properly, it opens a transaction on the worker.
- The handler's transaction **is not the same** as the sender/inbound adapter transaction. Failures in process() may occur after the sender has already returned success.
- This example does not yet include a durable inbox, idempotency/event version checks, error flow, or outbox state; these must be added before handling financial or zero-loss order processing.
- Validation sits **before** the boundary, so data errors are thrown synchronously; DB errors in process() occur **after** the boundary and require async handling.

### Equivalent XML Configuration for ExecutorChannel

~~~xml
<int:channel id="ordersAsync">
    <int:dispatcher task-executor="ordersWorkerExecutor"
                    failover="false"/>
</int:channel>
~~~

This is an XML fragment; it requires the executor bean and integration namespace. When multiple subscribers exist, **failover/load balancing** can affect handler selection; if business logic should have a single owner, avoid having multiple competing subscribers without an explicit design.

## 10. Transaction Boundary: A Transaction Does Not Jump Across Threads

Standard Spring transactions use a **thread-bound context**. When:

~~~text
Sender thread                          Worker thread
BEGIN TX-A
send(M) → ExecutorChannel.submit()
COMMIT TX-A                            handle(M)
                                       BEGIN TX-B
                                       business update
                                       COMMIT / ROLLBACK TX-B
~~~

**TX-A and TX-B are independent** unless an explicit coordination mechanism is designed. Having @Transactional on the handler does not pull it back into TX-A, and **rolling back TX-B does not roll back an already-committed TX-A**.

### Why Is This Dangerous for Inbound Brokers?

If an adapter treats **send() success** as sufficient to commit the offset/ack:

~~~text
Inbound broker delivery
    → ExecutorChannel accepts task
    → inbound ACK / offset commit
    → worker later fails before business DB commit
~~~

Once the source has acked, it may **not redeliver**. If the task is killed or the error flow does not persist durable recovery, the message can be lost even though ingress logs reported it as processed.

**The deciding factor is the adapter's specific contract:** not every Kafka/JMS/AMQP inbound adapter acks after send in the same way. You must verify ack mode, transaction boundaries, container lifecycle, error handlers, and handoff placement.

### A Safer Durable Inbox Model

~~~sql
CREATE TABLE work_inbox (
    consumer_name TEXT NOT NULL,
    event_id TEXT NOT NULL,
    state TEXT NOT NULL,
    payload_json JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (consumer_name, event_id)
);
~~~

A synchronous inbound handler can:

1. Validate the message and business eventId.
2. **INSERT** the work item using its unique key into the inbox table within a transaction.
3. COMMIT the durable record.
4. Only then allow the adapter to acknowledge the source per contract.
5. A separate worker **polls/claims** PENDING work from the DB and starts a new processing transaction.
6. After effect/commit, transition state to COMPLETED or UNKNOWN/FAILED per workflow; if a worker dies, use lease/recovery.

**Do not mark COMPLETED upon enqueue.** The inbox here records a **durable obligation**: the work must continue until a clear outcome is reached. For external APIs, an UNKNOWN result requires reconciliation and an idempotency key.

### Pollers and Consumer-Side Transactions

If you use a JdbcChannelMessageStore-backed QueueChannel, you can open a transaction on the **poller** to combine dequeue + processing **synchronously on the consumer thread**. When the handler throws and triggers a rollback, the message can be read again. However, if the poller dispatches into an ExecutorChannel and commits before the worker executes, the handoff gap returns.

**Practical rule:** Place the **transaction boundary** where a specific durable commitment can be verified. Do not call a transaction "end-to-end" if a thread boundary or unmanaged external side effect sits inside it.

## 11. Exceptions and errorChannel After Switching Threads

On the synchronous path:

~~~text
input.send()
  → DirectChannel
     → handler throws
  → sender can catch the exception
~~~

On the asynchronous path:

~~~text
input.send()
  → ExecutorChannel
     → task accepted
  → send returns

worker executes:
  → handler throws
  → error handling in worker / ErrorMessage if configured
~~~

A **MessageHandlingException** on the worker may not reach the sender, even if the message was originally sent via a MessagingTemplate or inbound adapter. Spring Integration supports publishing an **ErrorMessage** via its error infrastructure for certain asynchronous endpoints; you must verify the actual path for your adapter/channel/version.

### Do Not Assume Global errorChannel Catches All Errors

Behaviors can differ:

| Location | Error Path to Verify |
| --- | --- |
| DirectChannel handler | Exceptions typically propagate back to the caller |
| ExecutorChannel handler | Error handler/task context, ErrorMessage if a suitable publisher exists |
| QueueChannel polling consumer | Poller error channel, scheduler, and advice |
| PublishSubscribeChannel with executor | Error handler for async subscribers |
| Inbound broker adapter | Listener/container error handling and ack/nack policy |
| Outbound gateway | Client exceptions may be wrapped; async usage needs an error flow |

Even if an ErrorMessage is logged, it is **not guaranteed** the original message will be redelivered by the broker. A recovery callback may have handled the exception, or the sender may have acked before the error occurred.

### Preserving failedMessage and Correlation

An error consumer should try to inspect **MessagingException.failedMessage** or **ErrorMessage.originalMessage** when available, and log stable **eventId/operationId/correlationId** values.

~~~java
import org.springframework.messaging.Message;
import org.springframework.messaging.MessagingException;
import org.springframework.messaging.support.ErrorMessage;

class OrderErrorInspector {
    void inspect(ErrorMessage error) {
        Throwable cause = error.getPayload();
        Message<?> original = error.getOriginalMessage();

        if (cause instanceof MessagingException messaging
                && messaging.getFailedMessage() != null) {
            original = messaging.getFailedMessage();
        }

        String eventId = original == null
                ? "unknown"
                : String.valueOf(original.getHeaders().get("eventId"));

        System.out.println("eventId=" + eventId
                + ", errorType=" + cause.getClass().getSimpleName());
    }
}
~~~

This is a diagnostic illustration—**do not log raw payloads or secrets**, and do not assume failed/original message is always present. Exceptions at the source before constructing a Spring Message may not contain a failedMessage.

### Error Handling Must Have a Durable Outcome

When handling errors after an async handoff:

- Transient: retry with a **budget + backoff/jitter** under the designated retry owner.
- Permanent: durable quarantine/DLQ, do not retry infinitely.
- Uncertain external outcome: record **UNKNOWN_OUTCOME**, use provider queries/idempotency.
- Processed: acknowledge delivery or record COMPLETED state per contract.

**Do not let an error handler merely log and exit** if the source already acked while the worker produced no business outcome: you will end up with "received but unprocessed" work with nowhere left to replay from.

## 12. ThreadLocal, MDC, SecurityContext, and Tracing Across Handoff

Many Java/Spring components store data in **ThreadLocal**, meaning data bound to the **current thread**, which is not part of the message by default:

- **TransactionSynchronizationManager** holds part of the transaction synchronization/resource context.
- **org.slf4j.MDC** commonly holds traceId, correlationId, or logging fields.
- **SecurityContextHolder**, in its default configuration mode, uses a thread-local context.
- **RequestContextHolder** may bind request attributes to the HTTP handling thread.
- Tracing/observation libraries have their own context holders and propagation mechanisms.

When switching from sender thread to worker:

~~~text
sender thread:
  MDC(traceId=A)
  SecurityContext(user=X)
  DB transaction TX-A
  → ExecutorChannel.send(M)

worker thread:
  MDC(?) not guaranteed = A
  SecurityContext(?) not guaranteed = X
  TransactionSynchronizationManager(?) no longer has TX-A
~~~

**Message headers are not ThreadLocals.** An eventId or correlationId header can travel with the message if transformers/adapters preserve it, but MDC/trace context does not automatically transfer just because a header exists.

### Propagate Metadata, Do Not Propagate Transactions

A safe practice:

1. Put **eventId, correlationId, operationId, and required tenant/authorization context** into the message under a validated data contract.
2. On the worker, restore **logging/tracing context** using context propagation mechanisms supported by your framework/tracing library.
3. **Open a new transaction** with the appropriate transaction manager inside the worker.
4. Do not pass a live **JDBC Connection, EntityManager, transaction object, or RequestAttributes** across threads by arbitrarily copying ThreadLocals.
5. If authorization is needed on the worker, use credentials **authenticated and authorized through a trusted path**, rather than trusting role headers sent by an untrusted producer.
6. Clean up context after the worker finishes so pooled threads do not leak data from previous messages.

### TaskDecorator Example for MDC

For applications using SLF4J MDC, a **TaskDecorator** can copy the diagnostic context at task submission time:

~~~java
import java.util.Map;
import org.slf4j.MDC;
import org.springframework.core.task.TaskDecorator;

final class MdcTaskDecorator implements TaskDecorator {
    @Override
    public Runnable decorate(Runnable task) {
        Map<String, String> captured = MDC.getCopyOfContextMap();

        return () -> {
            Map<String, String> previous = MDC.getCopyOfContextMap();
            try {
                if (captured == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(captured);
                }
                task.run();
            } finally {
                if (previous == null) {
                    MDC.clear();
                } else {
                    MDC.setContextMap(previous);
                }
            }
        };
    }
}
~~~

In the ThreadPoolTaskExecutor configuration:

~~~java
executor.setTaskDecorator(new MdcTaskDecorator());
~~~

This is an example for **MDC log context**, **not** a general solution for copying observation context, SecurityContext, or transactions. For Micrometer Observation/Tracing, prefer the **supported context-propagation integration** for your version stack and test traces/spans across actual boundaries.

**Warning:** MDC may contain sensitive data, and capturing context across large queues retains extra objects in memory. Restrict which fields are propagated, clear them after the task, and do not attach eventId/traceId as high-cardinality metric tags.

## 13. Correlation, Ordering, and Parallelism by Business Key

When using multiple workers, **start order** and **completion order** do not necessarily match the order messages were sent:

~~~text
Input:  order O-42 version 1, version 2, version 3

Worker 1 processes v1: HTTP 900 ms
Worker 2 processes v2: DB 100 ms
Worker 3 processes v3: DB 120 ms

Output by completion: v2, v3, v1
~~~

If the final handler overwrites order state, version 1 finishing last can **overwrite newer data with stale state**. This is not merely a performance issue; it can be a business correctness bug.

### Three Strategies Depending on Contract

**1. No ordering required**

Events are independent and side effects are idempotent. Use a multi-threaded worker pool, while designing duplicate handling and consistency separately.

**2. Per-business-key ordering required**

Ensure **the same orderId** is processed sequentially, while **different orderIds** can run in parallel. Options include:

- Broker partitioning by orderId with a consumer processing each partition sequentially **when ack and handoff semantics align**.
- A **partitioned/serial executor** by key, with bounded queues and handling for hot keys.
- **PartitionedChannel** in Spring Integration versions that support it, with a carefully designed partition key function.
- DB **optimistic locking/version checks**, even when ordering is used, to prevent stale updates caused by retries/replays.

**3. Global ordering required**

Limit concurrency, rely on a single authoritative source order, or use a **resequencer**; this trades off throughput and increases head-of-line blocking risk. Do not assume QueueChannel + multiple consumers preserves global completion order.

### Correlation Differs from Ordering and Idempotency

| Concept | Purpose | Interchangeable? |
| --- | --- | --- |
| **correlationId** | Associates parts of a workflow/message group | Not a dedup key by default |
| **sequenceNumber/sequenceSize** | Helps splitter/aggregator/resequencer manage parts and order | Does not guarantee workers finish in order |
| **eventId** | Identifies a specific source event | May suit event dedup, depending on contract |
| **operationId/paymentId** | Identifies a business side effect | Usually the right idempotency key for side effects |
| **business version** | Prevents older updates from overwriting newer state | Does not replace message persistence or retry policies |

### Hot Keys and Partitioning

If 50% of messages share the same orderId/tenant key, "partition by key" can turn one partition into a bottleneck. You need to measure per-shard throughput, queue wait, unusually heavy jobs, and scaling approaches that do not break ordering guarantees.

## 14. Retries and Timeouts Must Match Each Boundary

Adding an executor introduces **multiple deadlines**:

~~~text
Inbound broker visibility / ack deadline
    ├─ TaskExecutor queue wait time
    ├─ worker execution timeout
    ├─ DB transaction timeout
    ├─ outbound HTTP request timeout
    ├─ RetryAdvice backoff / attempts
    └─ gateway reply timeout (if request-reply)
~~~

**send() timeout** is different from **business effect completion timeout**. For example, a TaskExecutor queue may accept a task immediately yet hold it for 40 seconds before a worker runs it. A gateway waiting 10 seconds for a reply may time out even though the task eventually executes and produces a side effect later.

### Retry Amplification Across Independent Layers

~~~text
Broker redelivery: 3 deliveries
Handler retry advice: 4 attempts / delivery
HTTP client retry: 2 calls / handler attempt

Up to 3 × 4 × 2 = 24 HTTP calls
for the same operationId.
~~~

When placing a thread boundary, define the **retry owner** and who performs **durable recovery**:

- **Before the boundary:** If validation or durable write fails, the source may need to retry/redeliver.
- **After the boundary:** Worker errors must have an independent handling path; do not assume errors return to the sender.
- **After external side effects:** Outcome may be unknown, requiring a stable idempotencyKey and reconciliation rather than just RetryTemplate.
- **Attempts exhausted:** Route to a **durable** DLQ/quarantine/retry journal before final ack if the business requires zero loss.

### End-to-End Deadlines

Do not set a 5-second gateway timeout when the downstream worker queue routinely waits 8 seconds without an explicit design decision. If the gateway expires, the caller may resend **the same operation** and cause duplicates.

A solid policy must define:

1. What does **enqueue accepted** mean to the caller?
2. Upon timeout, is the work actually cancelled or does it still run?
3. If the caller retries, does it reuse the **same operationId**?
4. Is there a mechanism to query status by operationId?
5. After a restart, will a new worker resume already-accepted work?

**Interrupt is not a remote rollback.** An HTTP request that has already reached the provider may still execute even if the Java thread is interrupted or the Future is cancelled.

## 15. Messaging Gateway: Async Channels Can Still Make Callers Wait

A **messaging gateway** typically follows a request–reply model:

~~~mermaid
sequenceDiagram
    participant C as REST caller
    participant G as MessagingGateway
    participant E as ExecutorChannel
    participant W as Worker
    C->>G: submit(Order)
    G->>E: requestMessage + replyChannel
    E-->>G: handoff accepted
    Note over G: Gateway still waits for reply
    E->>W: process asynchronously
    W-->>G: reply on completion
    G-->>C: business response
~~~

**Benefit:** Decouples handler threads from callers when isolation is needed; allows multiple workers to execute.

**Limitation:** If the gateway still waits synchronously for a reply, **the request thread can still be blocked** until reply or timeout. Putting an ExecutorChannel in between **does not automatically make an API asynchronous**.

If the business operation takes minutes:

- Return **202 Accepted** after a durable command has committed (if the API/contract adopts this model).
- Provide an **operationId** for a status query endpoint or callback/event.
- Use durable workers/outbox and idempotency instead of an in-JVM Future alone.
- Define client timeouts/retries so they do not create multiple business operations.

### Reply Channels and Headers After Restart

A TemporaryReplyChannel or reply channel object inside a message may live only within a single JVM. If a message is saved in a persistent QueueChannel and processed by a worker after a restart, **replyChannel/errorChannel holding object references may not deserialize/resolve**. Design reply correlation via **persistent business state**, resolver-backed channel names, or a durable reply transport.

**Do not treat sending a Spring Message with a replyChannel header as a durable cross-process request-reply guarantee.**

## 16. Executor Sizing, Capacity, and Backpressure

Treat a dedicated executor as a **budgeted resource**, not "a way to make every task async".

### Parameters to Size Together

| Parameter | Impact | Risk If Chosen Arbitrarily |
| --- | --- | --- |
| **corePoolSize** | Number of baseline workers retained | Too small causes long queue waits |
| **maxPoolSize** | Thread ceiling during expansion | Too large causes context switching/DB overload |
| **queueCapacity** | Number of queued tasks while workers are busy | Too large hides latency and consumes heap |
| **rejection policy** | Behavior when pool/queue are full | Abort produces errors; CallerRuns switches threads; silent discard is dangerous |
| **threadNamePrefix** | Diagnosing thread dumps/logs | Missing prefix makes correlating errors to flows hard |
| **taskDecorator/context propagation** | Preserves tracing/MDC across handoff | Bugs can leak context between tasks |
| **shutdown policy** | Waits for tasks or cancels on process close | Cannot guarantee durability of in-memory tasks |
| **downstream concurrency limit** | Active HTTP/DB calls | A pool larger than the DB connection pool can worsen load |

### A Rough Sizing Rule

By Little's Law under steady-state conditions:

\[
L \approx \lambda W
\]

where:

- **L**: average number of work items in the system (queued + in-flight).
- **λ**: average completion throughput (operations/second).
- **W**: average time spent in the system (seconds).

For example, with **λ = 40 operations/s** and **W = 0.5 s**, the system holds an average of about **20 operations** waiting or running. This is only an **average capacity estimate**, not a formula to automatically choose maxPoolSize for every workload. You must account for P95/P99, variance, retries, and DB/HTTP constraints.

### A Pool of 4–8 Threads and Queue of 100 Does Not Imply Low Latency

If each HTTP call slows from 100 ms to 3 seconds:

~~~text
worker occupancy spikes
→ queue fills up
→ queue wait p95 rises
→ caller timeouts / retries
→ ingress rate increases further
→ task rejections / retry storm
~~~

Merely raising queueCapacity to 10,000 can keep send() fast while every message waits for minutes. **Backpressure must be early and explicit**: throttle intake, reduce concurrency, control retries, apply rate limits/circuit breakers, and consider durable buffering.

### Rejection Policy Is a Business Decision

- **AbortPolicy:** Exposes overload to the sender immediately at handoff. The sender/adapter must handle the error properly instead of falsely acking success.
- **CallerRunsPolicy:** Pushes work back onto the sender thread, creating backpressure, but changes transaction/error/thread context depending on load.
- **DiscardPolicy/DiscardOldestPolicy:** Can silently drop tasks; unsuitable for businesses that **cannot afford message loss** without explicit compensation/recovery.
- **Unbounded queue:** Imposes no hard limit on pending work, increasing memory pressure and unpredictable latency.

Sharing one executor pool across all flows can cause **noisy-neighbor failures**: slow HTTP notifications starve critical payments/fulfillment. When SLAs and failure domains differ, use separate pools/queues **with independent capacity limits and monitoring**.

## 17. Shutdown and Restart: Which Boundaries Can Lose Work?

Graceful shutdown typically follows the sequence: stop ingress, drain in-flight work, stop consumers/executors, and close resources. However, a task sitting in an executor queue **has no durability contract** simply because Spring accepted the task.

~~~mermaid
sequenceDiagram
    participant B as Broker
    participant S as Sender
    participant E as ExecutorChannel
    participant W as Worker
    B->>S: Deliver EV-42
    S->>E: send(EV-42)
    E-->>S: accepted
    S-->>B: Source ACK (in some configurations)
    Note over E: Task waiting in RAM queue
    Note over E,W: JVM killed before W starts
    B-->>S: May not redeliver if already ACKed
~~~

**Risk observation:** The handler did not throw an exception because **it never ran**. ErrorChannel might not receive an error either; only handoff metrics/traces and a missing durable result remain.

### Intentional Shutdown

1. **Stop ingress** across all relevant sources/instances.
2. Keep workers/executors active to drain existing tasks **within a budget**.
3. Monitor **QueueChannel depth, executor queued, active/in-flight, broker unacked, transaction/DB commits, and pending retry/outbox items**.
4. When the shutdown budget expires, declare safety only if remaining work **is durably stored or will be replayed by the source** per contract.
5. Start new workers and verify replay/idempotency rather than assuming in-memory tasks survived.

**Spring Boot lifecycle timeouts**, **Spring Integration orderly shutdown**, and **Kubernetes termination grace periods** run on separate clocks. Do not set all timeouts to the exact same value and assume there is enough time for preStop, draining, and resource cleanup.

### Do Not Use Lifecycle Hooks to Patch Durability Gaps

For instance, configuring **setWaitForTasksToCompleteOnShutdown(true)** and awaitTermination can improve graceful shutdown, yet **SIGKILL, node failure, OOM, power loss, or grace-period expiration** can still cut tasks short. **Durable handoff and business idempotency** are independent architectural designs—they cannot be replaced by "waiting a little longer".

## 18. Observability: Measuring Both Sides of the Thread Boundary

Once an ExecutorChannel is added, evaluating performance with a single Timer around send() can be misleading. You must separate **producer pace**, **boundary wait delay**, and **consumer execution time**.

~~~mermaid
flowchart LR
    P["Producer"] -->|dispatch timer| EC["ExecutorChannel"]
    EC -->|queue wait timer| W["Worker starts"]
    W -->|handler timer| H["Business handler"]
    H --> D[("DB / external API")]
    EC -. "queue depth / rejects" .-> M["Monitoring"]
    W -. "active / in-flight" .-> M
    H -. "success/error" .-> M
~~~

| Metric / Log | Start → End | What It Diagnoses |
| --- | --- | --- |
| **orders.dispatch.duration** | Before send() → send() returns/throws | Is channel/executor handoff fast or blocked? |
| **orders.executor.wait.duration** | Task actually enqueued → handler starts | Is the worker pool overloaded? |
| **orders.handler.duration** | Handler starts → returns/throws | How slow is business/DB/HTTP work? |
| **orders.business.e2e.duration** | Operation accepted → final business state | Real SLA, potentially spanning retries/restarts |
| **orders.executor.queued** | Count of waiting tasks | Tasks leaving QueueChannel may not have started yet |
| **orders.executor.active** | Count of running tasks | Pool utilization |
| **orders.executor.rejected** | Rejected task handoffs | Backpressure that must be addressed |
| **orders.handler.failed** | Handler attempt throws | Attempt failure, not necessarily final operation failure |
| **orders.operation.completed** | Operation confirmed complete | Source of truth must align with DB commit/idempotency |
| **orders.durable.pending** | Committed work not yet completed | Recovery readiness after restart |
| **orders.error.recovered** | Durable recovery completed | Was DLQ/quarantine/outbox written successfully? |

The metric names above are **application-defined examples**, not a list of metrics automatically created by the framework. Check the built-in Micrometer/Observation support in your Spring Integration version to avoid double-measuring the same stage.

### Choose the Right Clock When Measuring Queue Wait

If producer and worker live in the **same JVM**, elapsed duration can be measured with an appropriate monotonic clock. If a message was stored persistently or in a broker and consumed **after a restart or on another host**, you cannot subtract System.nanoTime() from an old JVM from System.nanoTime() on a new JVM. In that case, use timestamps with explicit formats, time synchronization, and a clock-skew handling policy.

**Do not add eventId, orderId, traceId, timestamp, or messageId as metric tags.** Nearly unique values create extremely high cardinality. Put them into access-controlled **structured logs/traces**; use bounded-set dimensions like flow, endpoint, outcome, worker pool, and error category for metrics.

### Symptoms of a Misplaced Boundary

~~~text
Ingress throughput = 500 msg/s
ExecutorChannel send p95 = 2 ms
Executor queue wait p95 = 45 s
Handler p95 = 1.2 s
Rejected tasks = increasing
Gateway timeouts = increasing
~~~

Looking only at send p95 makes the system appear very fast. In reality, the source is feeding work faster than downstream can process it, and timeouts plus retries may amplify the load even further.

## 19. JUnit: Verifying Synchronous and Asynchronous Execution

### Test 1 — DirectChannel Runs Handler on the Calling Thread

This test uses a real Spring Integration channel:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.messaging.support.MessageBuilder;

class ChannelThreadBoundaryTest {

    @Test
    void directChannelInvokesHandlerOnCallerThread() {
        DirectChannel channel = new DirectChannel();
        AtomicReference<String> handlerThread = new AtomicReference<>();

        channel.subscribe(message ->
                handlerThread.set(Thread.currentThread().getName()));

        String callerThread = Thread.currentThread().getName();
        assertTrue(channel.send(
                MessageBuilder.withPayload("EV-42").build()));

        assertEquals(callerThread, handlerThread.get());
    }
}
~~~

**What this proves:** When sending to a DirectChannel, the synchronous subscriber is invoked on the sender thread. The test does not prove the entire system has only one thread; multiple concurrent senders can still invoke the same handler.

### Test 2 — ExecutorChannel Dispatches Work to a Worker

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

class ExecutorBoundaryTest {

    @Test
    void executorChannelRunsHandlerOnWorkerThread() throws Exception {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(4);
        executor.setThreadNamePrefix("test-order-worker-");
        executor.afterPropertiesSet();

        try {
            ExecutorChannel channel = new ExecutorChannel(executor);
            CountDownLatch processed = new CountDownLatch(1);
            AtomicReference<String> handlerThread = new AtomicReference<>();

            channel.subscribe(message -> {
                handlerThread.set(Thread.currentThread().getName());
                processed.countDown();
            });

            String senderThread = Thread.currentThread().getName();
            assertTrue(channel.send(
                    MessageBuilder.withPayload("EV-42").build()));

            assertTrue(processed.await(2, TimeUnit.SECONDS));
            assertNotEquals(senderThread, handlerThread.get());
            assertTrue(handlerThread.get().startsWith(
                    "test-order-worker-"));
        } finally {
            executor.shutdown();
        }
    }
}
~~~

**What this proves:** In a fixture with a dedicated executor and without CallerRunsPolicy, the handler can be dispatched to a worker thread. Do not conclude from this single test that every ExecutorChannel always runs on a different thread under all configurations; caller-runs/rejection policies create exceptions.

### Test 3 — Sync Errors Reach the Sender, Async Errors Must Be Observed on the Worker

With DirectChannel:

~~~java
DirectChannel channel = new DirectChannel();
channel.subscribe(message -> {
    throw new IllegalStateException("business failure");
});

assertThrows(RuntimeException.class, () ->
        channel.send(
                MessageBuilder.withPayload("EV-43").build()));
~~~

This is a fragment testing uncaught exceptions on the synchronous path; Spring Integration may wrap the cause in a MessagingException. With ExecutorChannel, **do not reuse assertThrows(send())** to verify late handler failures. Write an **error flow integration test**:

1. Configure an ExecutorChannel with a real consumer.
2. Have the handler throw an exception on the worker thread.
3. Configure the endpoint's errorChannel/error publisher properly.
4. Use a test QueueChannel to receive the ErrorMessage within a bounded timeout.
5. Assert the exception cause, failed/original message if present, correlationId/eventId, and recovery outcome.
6. Verify the sender may return before the worker reports the error, yet the application still achieves durable recovery if required by the business.

Do not assume an ErrorMessage will automatically appear on the global errorChannel unless the test configures the corresponding error handling.

### Test 4 — Verifying Transactions Do Not Follow the Worker

An integration test can use **TransactionTemplate** around send on the sender side and a Spring-managed handler on the worker side to observe:

~~~text
Sender thread:
    TransactionSynchronizationManager.isActualTransactionActive() = true
    → ExecutorChannel.send()

Worker thread:
    before its own @Transactional method:
        no inherited TX-A
    inside handler's @Transactional proxy:
        active TX-B
~~~

The test must use a **real DataSource/PlatformTransactionManager**, invoke through the bean proxy, and use a CountDownLatch to coordinate timing. Do not invoke the handler method directly and conclude Spring AOP transactions worked; nor run the entire test inside a test-managed transaction and assume the worker uses that same transaction.

**Correct assertion:** TX-B can commit or roll back independently of TX-A. When the handler throws after handoff, an already-committed TX-A does not automatically roll back with TX-B.

## 20. Testing Executor Saturation and Work Loss at Async Handoff

A capacity test needs to prove behavior when **the pool and queue are full**, not just the happy path.

### Testing with an Intentionally Blocked Worker

~~~java
import static org.junit.jupiter.api.Assertions.*;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ThreadPoolExecutor;
import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

class ExecutorRejectionTest {

    @Test
    void boundedExecutorRejectsAtCapacity() throws Exception {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(0);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.afterPropertiesSet();

        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);
        try {
            ExecutorChannel channel = new ExecutorChannel(executor);
            channel.subscribe(message -> {
                started.countDown();
                try {
                    release.await();
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            });

            assertTrue(channel.send(
                    MessageBuilder.withPayload("EV-A").build()));
            assertTrue(started.await(2, TimeUnit.SECONDS));

            // Worker is busy, and the executor has no pending queue.
            assertThrows(RuntimeException.class, () ->
                    channel.send(
                            MessageBuilder.withPayload("EV-B")
                                    .build()));
        } finally {
            release.countDown();
            executor.shutdown();
        }
    }
}
~~~

The test uses **AbortPolicy** and queueCapacity=0 for a deterministic rejection condition. If CallerRunsPolicy is used, the second message may run on the sender thread instead of throwing; the test must be adjusted to match the chosen contract.

**Do not call a failed handler "the message was retried".** When handoff is rejected, check where the exception is caught on the sender, adapter acknowledgement, and durable recovery. In production, an adapter might roll back/redeliver when send fails; this only holds true for specific source and transaction configurations.

### Hard Crash Test for Work Loss After ACK

An integration test worth more than a unit test:

1. Use a broker or test source with a **deterministic ack policy**.
2. Send event EV-42, inserting a checkpoint right after the **executor accepts the task** but before the worker executes.
3. Verify whether the source has ACKed; if it has ACKed, **kill the process**.
4. Restart the process with the same broker/DB store.
5. Check whether EV-42 is replayed and the final business effect is correct.

If the source already ACKed while the task existed only in executor RAM, the test may expose **the lack of any replay mechanism**. In that case, fix the **durable handoff/ack boundary**—do not change the test to ignore the failure.

### Testing Ordering and Correlation

With two events sharing the same orderId and a worker pool > 1:

- Use a latch to make the worker process **version 1 slower than version 2**.
- Verify that outputs can arrive out of order without an ordering design.
- If the business requires per-order sequentiality, add partition-by-key or DB optimistic locking/version checks.
- Assert **eventId/operationId remain stable** across retries and **correlationId** is preserved in logs/traces.
- Verify that an aggregator/resequencer does not treat **group size** naively as just the number of distinct event types.

## 21. Checklist for Deciding Where to Place Boundaries

| Requirement | Preferred Approach | What Must Be Verified |
| --- | --- | --- |
| Very fast processing, need exceptions to propagate to source | DirectChannel | Transaction scope and source ack |
| Need async isolation, controlled acceptance of in-memory task risk | ExecutorChannel + bounded executor | Rejection, context/error propagation, shutdown |
| Source faster than consumer, buffering needed | QueueChannel + poller | Queue capacity, backing store, recovery |
| Work must survive restarts | Durable inbox/outbox or persistent MessageStore/broker | Atomic durable handoff, ack/rollback, and idempotency |
| DB update must roll back with dequeue | Transactional poller + same DB resource | Do not put an ExecutorChannel between receive and commit |
| Fan-out to subscribers with different SLAs | PublishSubscribeChannel or durable multi-consumer transport | Per-branch failure/commit, replay, and ordering |
| Synchronous gateway requiring reply | DirectChannel or async with explicit deadline | Reply correlation, timeout, late results, duplicates |
| Sequential processing per orderId needed | Partition-by-key or version control | Hot keys, order guarantees, crash/restart |
| Downstream easily overloaded | Isolated bounded pool + backpressure | Queue wait, rejection, retry budget |
| Long-running external API | Durable command + status query | Timeout does not auto-cancel effects, unknown outcomes |
| Multiple replicas | Shared durable state/partitioning and coordination | Do not rely on RAM/JVM locks across the cluster |

## 22. Anti-Patterns: Architectural Mistakes When Creating Boundaries "For Speed"

### Anti-Pattern 1 — Swapping DirectChannel for ExecutorChannel Without Checking ACK

~~~text
Inbound adapter
  → ExecutorChannel.accept()
  → source ACK
  → worker later handles business logic
~~~

When the process dies in the middle, the source may not redeliver and the task existed only in RAM. **Fix:** verify the adapter's ack boundary, add durable handoff, or stay synchronous until work is durably persisted.

### Anti-Pattern 2 — Putting a Transaction on the Sender Expecting Workers to Share It

~~~text
@Transactional service
  → async channel
     → worker updates DB
  → sender commits
~~~

Standard Spring transactions are **thread-bound** and do not transfer to workers automatically. **Fix:** design transactions per stage on the corresponding thread; if atomicity is required, do not split the transaction with an uncoordinated async handoff.

### Anti-Pattern 3 — Using Unbounded Queues Instead of Backpressure

Large queues can keep send() fast for minutes while creating extreme P99 queue wait times, inflating heap usage, and causing client timeouts and retries. **Fix:** bounded capacity, meaningful rejections, rate limits, intentional load shedding, or proper durable buffering as required.

### Anti-Pattern 4 — Using CallerRunsPolicy as a Transaction Guarantee

Under normal load, worker thread; under overload, sender thread. **Fix:** do not rely on load-dependent runtime behavior to define transaction/security/error semantics; establish independent error/backpressure policies.

### Anti-Pattern 5 — Forgetting Context Propagation

Worker logs miss traceId/correlationId or, worse, retain MDC from a previous message on the pooled thread. **Fix:** use supported propagation, clean up ThreadLocals in finally blocks, and pass business keys via reliable headers/payloads.

### Anti-Pattern 6 — Relying on "Faith-Based" Ordering

Multiple workers process the same orderId without partitioning or version checks. **Fix:** per-business-key ordering, version guards, and tests for out-of-order completion and retries.

### Anti-Pattern 7 — One Executor Shared by All Branches

Slow email/analytics exhaust workers; critical payments starve, or even the control plane gets congested. **Fix:** isolate pools by SLA/failure domain, size capacity, and limit each workload type.

### Anti-Pattern 8 — Using @Async/Future Yet Waiting Immediately for Results

The caller creates a Future and calls get() immediately, still blocking while also having to manage timeouts/context/errors across a new boundary. **Fix:** if synchronous results with low latency are needed, keep DirectChannel; if truly async, use durable commands + operation status instead of an in-JVM Future.

### Anti-Pattern 9 — Catching Exceptions and Returning Success to Avoid Red Logs

The handler catches an error, logs it, and returns normally, allowing upstream to ack the message and lose replay opportunities. **Fix:** classify errors, propagate/roll back when appropriate, and persist durable recovery/DLQ before signaling completion.

### Anti-Pattern 10 — Stopping Ingress and Consumers Together Expecting the Queue to Drain

Backlog inside QueueChannel remains stranded once consumers stop. **Fix:** quiesce inbound first, keep pollers/workers running until drained or budget expires; if pending items remain, ensure durable recovery after restart.

## 23. Design Workshop: Placing Boundaries for an Order Fulfillment Service

**Scenario:** A service receives around **300 OrderSubmitted events/second** from a broker, validates payloads, writes to PostgreSQL, and calls inventory/payment providers. Some requests take 2–5 seconds. The service runs four replicas and must:

- Never lose an operation ACKed as accepted.
- Never charge or deduct inventory twice on retries/redeliveries.
- Return an acceptance response quickly without waiting for payment completion.
- Preserve status update order **per orderId**, without requiring global ordering.
- Limit concurrent requests to downstream providers.
- Recover cleanly after deployments, SIGTERM, and unexpected crashes.
- Provide error flows, DLQ/quarantine, metrics, and correlation sufficient for investigation.

### Step 1 — Define the Producer Contract

Define **eventId**, **orderId**, **operationId**, schema version, and delivery semantics. The broker may redeliver events; all business effects must be idempotent.

**Do not** confirm "accepted" merely because an in-memory ExecutorChannel accepted the task.

### Step 2 — Durable Handoff Before the Boundary

~~~mermaid
flowchart TD
    B["Broker event"] --> V["Validate + preserve IDs"]
    V --> TX["Transactional Inbox / work table"]
    TX --> DB[("PostgreSQL COMMIT")]
    DB --> ACK["Broker ACK per adapter contract"]
    DB --> W["Durable work queue / worker poller"]
    W --> K{"Partition/orderId"}
    K --> P1["Worker partition 1"]
    K --> P2["Worker partition 2"]
    K --> P3["Worker partition N"]
    P1 --> EXT["Payment / inventory APIs"]
    P2 --> EXT
    P3 --> EXT
    EXT --> OUT[("Business state + outbox")]
    OUT --> PUB["Outbox publisher"]
~~~

Only once the durable work row has committed is the adapter allowed to treat the handoff as successful under the chosen policy. For two deliveries with the same eventId, a **unique constraint** ensures only one logical work item exists.

### Step 3 — Partitioned Processing by orderId

Workers pull work from the durable store, ensuring:

- Updates for the same **orderId** do not apply out of committed order.
- Different orderIds can run in parallel.
- If a worker dies, leases/pending work can be reclaimed.
- Optimistic versions/unique business operation keys guard against replays.

### Step 4 — Limit External Concurrency

Configure separate pools or rate limiters for payment and inventory. APIs use timeouts and idempotency keys; UNKNOWN responses trigger reconciliation rather than blind retries.

If queues overload, the system can **hold items durably pending**, throttle ingress, or apply backpressure to the source per contract. Never allow an in-memory executor queue to grow unboundedly.

### Step 5 — Choose Post-Boundary Error Flows

| Situation | Appropriate Recovery |
| --- | --- |
| Invalid payload / missing eventId | Quarantine immediately, do not retry infinitely |
| Temporary DB connection exhaustion | Bounded retry/backoff, keep durably pending |
| Payment provider read timeout | UNKNOWN_OUTCOME, query provider/idempotency |
| Worker process crash | Reclaim durable work after lease timeout |
| Outbox publish succeeded but crashed before marking sent | Safe to republish; downstream is idempotent |
| Consumer receives duplicate eventId | Inbox recognizes existing logical work, skips duplicate side effect |

### Step 6 — Define Observability

Include at minimum ingress rate, durable pending age, queue wait p95, worker duration p95, active/rejected, retry attempts, duplicates suppressed, business completions, UNKNOWN reconciliations, and per-order latency. Traces/logs keep eventId/orderId/operationId, while metrics do not use these IDs as high-cardinality tags.

### Step 7 — Mandatory Test Scenarios

1. Send a valid event; verify **inbox commits before source ACK**.
2. Send two deliveries with the same eventId; only one business operation takes effect.
3. Kill a worker while work is pending; another worker reclaims and finishes it.
4. Kill after payment side effect but before recording CONFIRMED; reconciliation does not double-charge.
5. Force two events for the same orderId to finish out of order; business version/order remains valid.
6. Saturate executor/worker capacity; the system maintains clear backpressure and recovery.
7. Shut down one replica; remaining replicas continue processing without losing or duplicating side effects.
8. Deliberately trigger an ErrorMessage lacking failedMessage; the system still logs sufficient available source/request metadata for investigation.

## 24. Production Readiness Checklist Before Shipping a Thread Boundary

- Have you clearly identified the **thread boundary location** and why it is needed, rather than just wanting send() to return quickly?
- Have you distinguished **producer thread, poller thread, executor worker thread**, and adapter callback thread?
- If the source has an active transaction, have you accounted for the boundary **breaking transaction sharing**?
- Do you know **when the source ACKs/commits offsets** relative to when downstream business effects commit?
- If ACK occurs before the worker runs, is a **durable inbox/queue/broker handoff** committed beforehand?
- If using QueueChannel, is the store **in-memory or persistent**, and does the poller have an appropriate transaction wrapping dequeue?
- If using a persistent queue, have you verified **groupId, region, serializer, schema, and restart behavior**?
- Are there any **committed dequeue → task only in executor RAM** gaps?
- Does the executor have a **bounded queue, max concurrency, and explicit rejection policy**?
- If CallerRunsPolicy is used, is it treated strictly as **backpressure behavior**, not a transaction contract?
- Are pools separated for workloads with different SLAs/failure domains to avoid noisy-neighbor issues?
- Are **dispatch latency, queue wait, handler duration, and business end-to-end latency** measured separately?
- Are **active workers, executor queued/rejected, pending durable items, unacked, and in-flight** monitored?
- Are **eventId/operationId/correlationId** stably propagated across transformers/adapters?
- Is propagation and cleanup for **MDC/tracing/security context** verified, without passing transaction objects across threads?
- With multiple workers, is out-of-order execution acceptable or guarded by **partition-by-key/version checks**?
- Do gateways requiring replies have explicit timeouts, late-result handling, and idempotency?
- Do you distinguish **handler attempts, deliveries, and business operations**, avoiding double-counting during retries?
- Is the post-async errorChannel/recovery genuinely configured and tested, rather than just logging and dropping?
- Do retries have budgets/backoff, and do UNKNOWN external side effects have reconciliation?
- Have you tested **DirectChannel same-thread**, **ExecutorChannel worker thread**, overload/rejection, error flow, and transaction boundaries?
- Do you have hard crash/restart tests for pending tasks and durable handoff before ACK?
- Does the shutdown runbook quiesce ingress, drain within budget, and recover durable pending items?

## Conclusion

**Intentional thread boundary placement** is a **message-processing architectural decision**, not merely a performance tweak. In Spring Integration Runtime, **DirectChannel** preserves the synchronous call stack; **ExecutorChannel** decouples dispatch via a TaskExecutor; **QueueChannel** buffers messages in a queue for a poller to consume; and **PublishSubscribeChannel** can create parallel branches when configured with an executor.

Every boundary alters **transaction continuity, error propagation, reply semantics, ordering, context propagation, backpressure, and shutdown recovery**. A message successfully enqueued into **RAM** is not guaranteed to have been processed, durably persisted, or replayable; a handler running on a worker cannot automatically roll back a transaction already committed on the sender.

A solid design should answer six questions: **Who owns the message? Is the handoff durable? Who ACKs the source? Where are errors handled? What happens under overload? Who resumes work if the process dies?** Only when those questions have clear answers—verified through concurrency, fault injection, and restart tests—do thread boundaries help you scale without compromising flow correctness.

## References

- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Orderly Shutdown](https://docs.spring.io/spring-integration/reference/shutdown.html)
- [Spring Integration Reference — Testing Support](https://docs.spring.io/spring-integration/reference/testing.html)
- [Spring Integration Reference — Messaging Gateways](https://docs.spring.io/spring-integration/reference/gateway.html)
- [Spring Framework — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework — TransactionSynchronizationManager](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/support/TransactionSynchronizationManager.html)
- [Micrometer Reference — Context Propagation](https://docs.micrometer.io/context-propagation/reference/)
