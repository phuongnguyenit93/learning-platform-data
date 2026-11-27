# Shutdown timeouts and messages remaining in queues in Spring Integration Runtime

## Lesson objectives

In **SPRING_INTEGRATION_RUNTIME**, an IntegrationFlow typically receives messages from HTTP, a broker, files, or a database, passes them through **channels, endpoints, consumers, pollers, and executors**, and then updates a **MessageStore**, DB, or external service. When deploying a new version, scaling down pods, or closing a JVM, some messages may still sit in a **QueueChannel**, some may have been polled out, and some may be executing mid-flight in worker threads.

If shutdown is too fast, data not yet stored durably can be lost. If waiting indefinitely to drain backlog, the application may fail to stop, get force-killed by the orchestrator, or slow down version rollout. **Shutdown timeouts and messages remaining in queues** is the balancing problem between **stopping new intake, completing what can be completed, preserving what remains unfinished, and recovering safely after restart**.

This lesson belongs to the **Operations** chapter and builds on the module context: IntegrationFlow lifecycle management, transactions, retries, message stores, error handling, correlation, threading, performance, and runtime state.

After this lesson, you can:

- Distinguish **pause ingress, stop consumer, drain queue, graceful shutdown, forced termination**, and **restart recovery**.
- Explain when messages in an **in-memory QueueChannel** risk being lost and when a **persistent ChannelMessageStore** helps preserve them.
- Understand how **poller transactions** determine whether a message already removed from a store is restored on rollback.
- Distinguish **Spring Boot shutdown phase timeout**, **Spring Integration orderly-shutdown timeout**, **Kubernetes termination grace period**, **HTTP/broker deadlines**, and **business processing time**.
- Choose endpoint stop ordering to **stop generating new backlog without immediately stopping consumers that are draining**.
- Check **in-flight tasks, acknowledgements, transactions, retries, outbox, correlation, and idempotency** before declaring safety.
- Write tests for shutdown with queued messages, timeouts, crashes, restarts, and multiple replicas.

> **Principle:** An expired timeout **does not prove the queue is empty**; an empty queue **does not prove all side effects have committed**. You must examine **queued + in-flight + unacked + pending retry/outbox** together with each layer's durability policy.

## 1. What can still exist at shutdown time?

Consider the flow:

~~~mermaid
flowchart LR
    B["Broker / file source"] --> I["Inbound adapter"]
    I --> D["DirectChannel"]
    D --> Q[("ordersQueue<br/>QueueChannel")]
    Q --> P["Polling consumer"]
    P --> E["Executor / handler"]
    E --> DB[("Business DB")]
    E --> H["HTTP / broker outbound"]
    E -. "Failure" .-> R["Retry / errorChannel"]
~~~

At the moment of SIGTERM, work items can be in different states:

| State | Typical location | Risk when process stops |
| --- | --- | --- |
| **Not yet received** | Broker/topic, file directory, DB source | Source can retain them if retention/ack policies are appropriate |
| **Received but not yet enqueued** | Inbound adapter, DirectChannel, transformer | Handoff and ack may not be synchronized; check source and transaction |
| **Waiting in queue** | QueueChannel/MessageStore | Lost if in-memory and JVM dies; recoverable if persistent and committed |
| **Dequeued, currently processing** | Poller, handler, executor | Transaction may commit, roll back, or be cut mid-way; external effect may have occurred |
| **Business DB committed, source not acked** | Handler → inbound adapter | Can be redelivered on restart; requires idempotency |
| **Outbox written, not yet published** | Outbox pending | Publisher must resume after restart |
| **Published, not yet marked published** | Outbox publisher / broker | Can be republished; downstream needs dedup |
| **Waiting for retry/recovery** | Retry queue, DLQ, MessageStore | Needs retention/durability and clear terminal state |

**Queue depth measures only part of the work.** Once a consumer calls receive() and removes a message from QueueChannel, the queued count drops while the handler may hold that message for another 20 seconds calling DB/HTTP. When queued=0 yet in-flight=5, draining is not yet finished.

### Four actions often lumped together as "stop"

- **Pause ingress:** Stop receiving or generating new messages at one or more inbound endpoints. Does not automatically drain existing backlog.
- **Stop consumer:** Stop endpoints pulling messages for processing. If done before draining, backlog may stay untouched.
- **Graceful / orderly shutdown:** Sequentially stop new intake and give existing work a window to finish; then close resources.
- **Forced termination:** Budget expired or process killed; remaining state must be recovered from durable sources.

Do not use **successful stop()** or **isRunning=false** of one inbound endpoint to infer that all workers are idle or all messages are acked.

## 2. A shutdown timeline with backlog

Suppose ordersQueue holds **100 messages**, the polling consumer has **4 workers**, and each message averages 500 ms to process. Ideal throughput with no bottlenecks is roughly **8 messages/second**; draining 100 messages takes at least around **12.5 seconds** assuming no new messages, overhead, or skew.

~~~mermaid
sequenceDiagram
    participant O as Orchestrator
    participant A as Application / ingress
    participant Q as QueueChannel
    participant W as Poller / workers
    participant D as Business DB
    O->>A: SIGTERM / drain request
    A->>A: Stop new ingress
    Note over Q: 100 messages waiting
    loop Within shutdown budget
        W->>Q: receive a message
        Q-->>W: Message
        W->>D: Process + commit
        D-->>W: Commit succeeded
    end
    alt Queue empty and in-flight = 0
        A-->>O: Drained, safe to stop consumer
    else Timeout nearly exhausted
        A-->>O: Undrained: preserve durable state for restart
    end
~~~

**12.5 seconds is not a guarantee**: actual time depends on maxMessagesPerPoll, executor threads, DB pool, lock contention, retries, HTTP timeouts, batch distribution, commits, and acknowledgements. If one message hangs for 30 seconds with only four workers, tail latency can be much longer.

### Two valid but different shutdown outcomes

**A. Complete drain:** Ingress stopped, queue empty, in-flight empty, all effects/commits and required acks reached deterministic states. The process can exit with minimal recovery needed.

**B. Budget exhausted while durability preserved:** Some **unprocessed** messages remain in the persistent store/broker; some in-flight ones roll back/reconcile; the process stops and new workers recover. This can be a valid design when backlog is too large to drain within one pod termination grace period.

Bad design is **treating B as A** in logs/monitoring, or using an in-memory QueueChannel and assuming messages will magically reappear on restart.

## 3. Multiple timeouts: similar names, different contracts

| Clock | What it bounds | What it does **not** guarantee |
| --- | --- | --- |
| **Spring Boot lifecycle timeout** | Wait time when stopping one phase of SmartLifecycle beans via LifecycleProcessor | Does not automatically drain all Spring Integration QueueChannels |
| **Orderly Shutdown stopActiveComponents(howLong)** | Total wait window for Spring Integration's orderly shutdown operation; parameter in **milliseconds** | Does not guarantee all workers finish before deadline, nor persist in-RAM queues |
| **Kubernetes terminationGracePeriodSeconds** | Window allowed for pod/container to stop before termination kill | Does not automatically extend Spring Boot or broker internal timeouts |
| **preStop hook duration** | Execution time of preStop actions | **Consumes the same Kubernetes grace budget**, not extra time |
| **HTTP/gateway timeout** | Client/server wait time for one request | Partner-side request may still execute side effects |
| **Broker ack/visibility/lease timeout** | When the source considers a message done or eligible for redelivery | Does not make DB transaction/HTTP effect atomic |
| **Transaction timeout** | Transaction time limit per transaction manager | Does not roll back external HTTP/broker side effects arbitrarily |
| **Queue receive timeout** | Maximum wait for one consumer receive call | Not the total shutdown deadline |
| **Executor awaitTermination** | Time waiting for executor tasks to finish after stop/shutdown request | Does not persist unstarted in-memory tasks |

**Important:** The property **spring.lifecycle.timeout-per-shutdown-phase** is the timeout **per lifecycle phase**, not one clock for the entire process shutdown. Full shutdown may span multiple phases and other cleanup. Kubernetes watches **total wall-clock time**, including preStop and remaining work.

### Minimal Spring Boot configuration

~~~yaml
spring:
  lifecycle:
    timeout-per-shutdown-phase: 25s

# Depending on Spring Boot version, graceful HTTP shutdown
# may be default or require explicit enabling:
server:
  shutdown: graceful
~~~

This property helps **SmartLifecycle** and web server lifecycle. It is **not** equivalent to calling **IntegrationMBeanExporter.stopActiveComponents(...)** and does not create a transaction spanning source, queue, and downstream. Check your exact Spring Boot version and each endpoint's lifecycle.

### Example pod shutdown budget

Suppose the budget is:

~~~text
Kubernetes termination grace             : 90 s
  - preStop / stop ingress / propagation :  5 s
  - target orderly drain                 : 60 s
  - Spring lifecycle / resource close    : 15 s
  - buffer                               : 10 s
~~~

This is an **illustrative budget table**, not a mandatory sum of Spring durations because stages may **overlap** or span multiple lifecycle phases. In practice, ensure all blocking steps on the termination path do not exceed **total Kubernetes grace**, leaving buffer for DB/client cleanup.

Do not set **orderly-drain=90s** alongside **terminationGracePeriodSeconds=90** while also running preStop=10s: Kubernetes may kill the pod before orderly drain finishes.

## 4. Spring Integration Orderly Shutdown: stop sources first, let flows finish

Spring Integration provides an **Orderly Shutdown** mechanism documented via a JMX operation:

~~~java
// IntegrationMBeanExporter API when this component is configured:
public void stopActiveComponents(long howLong);
~~~

The **howLong** parameter is in **milliseconds** and sets the time budget allowed for the exporter's shutdown sequence. Conceptually, the sequence described in the Spring Integration documentation is:

1. Call **beforeShutdown()** on **OrderlyShutdownCapable** beans so they prepare to stop receiving, such as JMS/AMQP, TCP, or HTTP inbound listeners depending on implementation.
2. Stop certain **active message channels** such as JMS/AMQP-backed channels if any.
3. Stop **MessageSource** instances to prevent generating new data.
4. Stop remaining inbound **MessageProducer** components not implementing OrderlyShutdownCapable.
5. Give **in-flight messages** the remaining time to finish.
6. Call **afterShutdown()** on OrderlyShutdownCapable components to complete final cleanup.

Notable point: the documentation explains this algorithm was improved since Spring Integration 4.1 to **avoid stopping all pollers/executors prematurely**, allowing messages mid-flow in QueueChannels to continue processing during the wait window. <https://docs.spring.io/spring-integration/reference/shutdown.html>

**This is an administrative method invoked intentionally**; do not assume every Spring Boot app invokes it identically on SIGTERM. When integrating with shutdown, verify the exporter is enabled, the trigger is actually called, and how it orders against Spring context close.

### Invoking orderly shutdown programmatically

If the app configures **IntegrationMBeanExporter**, internal management code can be injected with the bean reference:

~~~java
import org.springframework.integration.monitor.IntegrationMBeanExporter;

final class OrderlyShutdownCommand {
    private final IntegrationMBeanExporter exporter;

    OrderlyShutdownCommand(IntegrationMBeanExporter exporter) {
        this.exporter = exporter;
    }

    void requestDrainBeforeShutdown() {
        // 30 seconds, not 30 milliseconds.
        exporter.stopActiveComponents(30_000L);
    }
}
~~~

This is a **management logic snippet**, not a complete application configuration. You need exporter/JMX management compatible with your project version; never expose JMX ports to the public Internet. If invoked from **Control Bus** or a management endpoint, inputs must be allowlisted and authenticated—never execute arbitrary SpEL expressions sent by untrusted clients.

**Do not call stopActiveComponents twice from different lifecycle callbacks** without an idempotency contract or synchronization: two shutdown sequences can contend on the same resources and muddy logs/state.

## 5. Messages left in QueueChannel: local memory vs persistent store

**QueueChannel** is a **PollableChannel**. It accepts messages into a queue and lets consumers call receive() to pull them out for processing. The biggest difference at shutdown is **what backs the queue**:

| Queue type | Do enqueued messages survive process restart? | Assessment |
| --- | --- | --- |
| **Default in-memory QueueChannel** | **No** when JVM actually dies | Acceptable when loss is tolerable, for tests, or when source reliably replays |
| **Bounded in-memory QueueChannel** | **No** | Bounds memory/backpressure, does not add durability |
| **QueueChannel + JdbcChannelMessageStore** | Potentially yes, for properly committed records | Needs tables/schema, transactions, store config, serializer, DB permissions |
| **QueueChannel + Redis/Mongo backed store** | Depends on implementation and backend durability | Inspect consistency, eviction/persistence, store transaction/ack semantics |
| **Broker-backed channel/source** | Depends on broker retention/ack/commit | Not equivalent to in-memory QueueChannel |

~~~mermaid
flowchart TD
    I["Message sent to QueueChannel"] --> Q{"Backing store?"}
    Q -- "In-memory" --> RAM[("JVM heap")]
    Q -- "Persistent" --> DB[("DB / persistent store")]
    RAM --> K["Kill JVM → local state vanishes"]
    DB --> REC["Restart → committed records readable again"]
    REC --> CON["Consumer processing + idempotency"]
~~~

**A bounded QueueChannel is still an in-memory queue** unless configured with a persistent store. Capacity reduces OOM risk, not durability risk. Conversely, when QueueChannel uses a **message-store**, XML queue capacity attributes do not apply the same way as bounded in-memory queues; control capacity/backpressure at the source or via store policy.

### Never use receive() just to "count backlog"

A successful **receive() call removes a message from the queue**. If a management/health checker tries receiving messages to count how many remain and discards them, it can **lose work** or alter transaction boundaries. Use **supported metrics/management APIs or store statistics** to observe queue depth/age, not a dummy consumer that reads and drops.

## 6. Configuring a durable QueueChannel and poller transaction

A common pattern when queues must survive JVM restarts is **JdbcChannelMessageStore**. Spring Integration distinguishes the general **JdbcMessageStore** from **JdbcChannelMessageStore**, which is optimized for channels.

### Java Configuration example with PostgreSQL

~~~java
import javax.sql.DataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.jdbc.store.JdbcChannelMessageStore;
import org.springframework.integration.jdbc.store.channel.PostgresChannelMessageStoreQueryProvider;
import org.springframework.integration.store.MessageGroupQueue;

@Configuration
class DurableQueueConfiguration {

    @Bean
    JdbcChannelMessageStore ordersChannelStore(DataSource dataSource) {
        JdbcChannelMessageStore store =
                new JdbcChannelMessageStore(dataSource);

        // SQL to receive messages compatible with PostgreSQL.
        store.setChannelMessageStoreQueryProvider(
                new PostgresChannelMessageStoreQueryProvider());
        return store;
    }

    @Bean
    QueueChannel ordersQueue(JdbcChannelMessageStore ordersChannelStore) {
        return new QueueChannel(
                new MessageGroupQueue(
                        ordersChannelStore, "ordersQueue"));
    }
}
~~~

**Mandatory prerequisites before putting this example into production:**

1. Requires the **spring-integration-jdbc** dependency, DataSource, and the **INT_CHANNEL_MESSAGE** schema/tables per your version's guide.
2. **MessageGroupQueue groupId="ordersQueue" must stay stable across restarts** to keep the same logical queue. Changing groupId after deploy can leave old records stranded where the new queue never reads them.
3. **JdbcChannelMessageStore needs a ChannelMessageStoreQueryProvider** matching your RDBMS; the example uses PostgreSQL.
4. Configure **region**, table, schema, database account, and indexes appropriately when sharing the store across flows or instances.
5. Payloads/headers must serialize/deserialize across restarts and upgrades; be especially careful with replyChannel/errorChannel holding JVM-local objects.
6. Cap intake concurrency, batches, and backpressure, and monitor backlog; a persistent store does not protect the DB from unbounded queue growth on its own.

This example creates the queue and store, **not yet consumer/transaction configuration**. Adding JdbcChannelMessageStore alone is not enough to guarantee a dequeued message is restored properly if the handler fails.

### XML polling consumer example with transaction

A readable way to see the transaction boundary is:

~~~xml
<int:service-activator
        input-channel="ordersQueue"
        ref="orderProcessor"
        method="handle">
    <int:poller fixed-delay="500" max-messages-per-poll="5">
        <int:transactional
                transaction-manager="transactionManager"/>
    </int:poller>
</int:service-activator>
~~~

This is an **XML configuration fragment**; a full configuration file must declare the integration namespace, orderProcessor, ordersQueue, and a transactionManager compatible with JdbcChannelMessageStore's DataSource.

**Why does a poller transaction matter?** With a transactional persistent store like JdbcChannelMessageStore, if the **poller executes receive() inside a transaction** and processes downstream synchronously within that transaction, message removal commits permanently only when the transaction succeeds. If processing throws an exception causing rollback, the dequeue rolls back so the message can be picked up again. This point is highlighted in the Spring Integration Reference. <https://docs.spring.io/spring-integration/reference/channel/configuration.html>

### Comparing two timelines

~~~mermaid
sequenceDiagram
    participant P as Poller
    participant Q as JDBC Queue Store
    participant H as Handler
    participant D as Business DB
    Note over P,D: Poller transaction wraps both receive and synchronous processing
    P->>Q: receive/remove inside transaction
    Q-->>P: Message EV-42
    P->>H: handle EV-42
    H->>D: update
    alt Handler succeeds
        P->>D: COMMIT transaction
        Note over Q: Dequeue committed
    else Handler throws + rollback
        P->>D: ROLLBACK
        Note over Q: Message remains pollable again
    end
~~~

**Do not extrapolate this to every topology.** If the poller pulls from the DB store and sends the message via **ExecutorChannel** to another thread, the poller's transaction **does not automatically propagate to the worker**. The poller may commit the dequeue before the worker executes business effects. The message has left the persistent queue and exists only as an in-memory executor task; forced shutdown can lose that work.

### A classic gap even with JdbcChannelMessageStore

~~~text
JDBC QueueChannel.receive() (transaction A)
    → ExecutorChannel.submit(task)
    → transaction A COMMITs and deletes row from JDBC queue

Worker B queued in executor (in-memory)
    → process killed
    → task vanishes
    → JDBC QueueChannel has no row left to replay
~~~

To protect the async hop, change the architecture: keep a **durable handoff** to a durable work queue/broker, configure proper transactions/acks, or place workers at a separate durable consumption point. Do not simply raise shutdown timeouts to paper over an atomicity gap between dequeue and in-memory enqueue.

## 7. Correctness when a message is dequeued but not committed

Name the milestones:

~~~text
T0  Message M in JDBC QueueChannel (committed)
T1  Poller begins transaction
T2  QueueChannel.receive() removes M inside transaction
T3  Handler updates business DB
T4  Handler calls external HTTP API
T5  Transaction commits/rolls back
T6  Adapter/broker ack or outbound publish
~~~

### If sharing the same DataSource and transaction

When **queue dequeue + business DB update** share the same compatible transaction, rollback can restore both. Still, the transaction manager, propagation, and actual resources must match; a transaction on a different DataSource is **not automatically atomic**.

### If side effects happen over HTTP

Suppose at T4 the provider succeeded, and then the DB transaction rolls back at T5. The message returns to the queue; next time it could call HTTP again.

~~~text
M remains replayable in JDBC queue
  + provider already charged once
  → redelivery requires a stable idempotencyKey / reconciliation
~~~

Therefore a persistent queue and poller transaction **protect delivery state** inside compatible DBs, **not create exactly-once side effects** on external services.

### If a worker is interrupted during shutdown

A thread can be interrupted while waiting on a lock, sleeping, or doing network I/O. Depending on the adapter/client, interruption can cancel the call or leave remote state **unknown**. Handlers should:

- Restore the interrupt flag when catching InterruptedException, or propagate an exception per contract so the outer transaction rolls back.
- Never catch InterruptedException and **return success** if business work did not finish.
- Distinguish **cancelled before effect** from **unknown outcome after request**.
- Avoid holding a DB transaction open across an unbounded HTTP call.

Example handler interrupted while waiting on a resource:

~~~java
try {
    boolean ready = latch.await(10, java.util.concurrent.TimeUnit.SECONDS);
    if (!ready) {
        throw new IllegalStateException("Operation deadline exceeded");
    }
    persistResult();
} catch (InterruptedException interrupted) {
    Thread.currentThread().interrupt();
    throw new IllegalStateException(
            "Interrupted during shutdown or cancellation", interrupted);
}
~~~

**This is an illustrative fragment**; implement latch and persistResult in your concrete test/application. The goal is **never reporting fake success** when the thread was interrupted before completion.

## 8. Never stop consumers before draining the queue

A broken runbook:

~~~text
1. Stop poller receiving new orders.
2. Immediately stop polling consumer reading QueueChannel.
3. Wait until ordersQueue depth == 0.
~~~

With no consumer left, the queue **cannot drain itself**. A safer runbook:

~~~mermaid
flowchart TD
    A["Start shutdown / pause"] --> B["Stop inbound producers"]
    B --> C["Keep downstream pollers/handlers running"]
    C --> D{"Messages in queue?<br/>Tasks in-flight?"}
    D -- "Yes and budget remains" --> E["Keep processing / bounded retries"]
    E --> D
    D -- "No" --> F["Close downstream & resources"]
    D -- "Yes and budget exhausted" --> G["Record pending state, logs/metrics"]
    G --> H["Stop per contract; prepare restart/replay"]
    F --> I["Process exit"]
    H --> I
~~~

### A concrete pause–drain–stop procedure

1. **Quiesce ingress:** stop inbound endpoints or instruct sources to stop sending more. Account for all replicas and other producers.
2. **Verify:** Inbound rate drops, target endpoints truly stopped receiving new work, and they will not auto-restart.
3. **Keep consumers going:** keep QueueChannel pollers and workers supplied with resources to drain backlog.
4. **Monitor:** queue depth, **oldest queued message age**, in-flight work, active DB transactions, and pending retries/DLQ/outbox.
5. **Meet drain criteria:** no queued messages remain and in-flight work has clear outcomes, with no unconfirmed side effects within the required completion scope.
6. **Stop downstream:** close pollers, executors, and resources in proper order once no work needs to run in the JVM.
7. **If budget expires:** do not claim drain succeeded; preserve persistent state and ensure the next startup has a recovery path.

**Note:** Quiescing ingress does not mean dropping every network connection instantaneously. An inbound adapter with an open request may need to finish or return a response per lifecycle/transport contract. Different adapters stop differently.

### Drain conditions should be application-defined

An illustrative predicate:

~~~text
ingressAcceptingNewMessages == false
AND queueBacklog == 0
AND activeHandlers == 0
AND sourceInFlightUnacked == 0
AND noUnresolvedEffectWithinShutdownScope == true
~~~

These variables are **business/operational metrics you define**, not identical built-in methods on every adapter. If the system allows durable pending outbox rows to survive restart, the condition can treat **outbox rows durably saved** as sufficient rather than forcing all publishes before process exit.

## 9. Measuring in-flight: an empty queue can still be unsafe

A minimal tracker for synchronous handlers or workers:

~~~java
import java.util.concurrent.atomic.AtomicInteger;

final class InFlightTracker {
    private final AtomicInteger active = new AtomicInteger();

    void execute(Runnable work) {
        active.incrementAndGet();
        try {
            work.run();
        } finally {
            active.decrementAndGet();
        }
    }

    int activeCount() {
        return active.get();
    }
}
~~~

Using it in a service activator:

~~~java
@ServiceActivator(inputChannel = "ordersProcessing")
public void handle(Message<OrderCommand> message) {
    inFlightTracker.execute(() -> orderService.process(
            message.getPayload()));
}
~~~

**These two code snippets are fragments**; define OrderCommand, orderService, bean wiring, and imports accordingly. They only measure the window **from method invocation to method return/throw**, excluding:

- Messages sitting in an **executor queue not yet executed**.
- DB transaction commits performed by a proxy **after method return** if the tracker sits inside the method.
- Broker acks happening after the handler.
- HTTP effects executing in a separate async callback.
- Events still pending in an outbox/MessageStore.

If the in-flight metric must represent **committed/acked** state, instrument at real transaction and source boundaries rather than only wrapping a method body with a counter.

### Waiting for drain with a finite deadline

Example helper watching the **tracker**—not equivalent to a full shutdown coordinator:

~~~java
import java.time.Duration;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

final class DrainWaiter {
    static boolean awaitZero(InFlightTracker tracker, Duration limit) {
        long remaining = limit.toNanos();
        long deadline = System.nanoTime() + remaining;

        while (tracker.activeCount() != 0) {
            remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                return false;
            }
            LockSupport.parkNanos(
                    Math.min(remaining, TimeUnit.MILLISECONDS.toNanos(20)));
            if (Thread.currentThread().isInterrupted()) {
                Thread.currentThread().interrupt();
                return false;
            }
        }
        return true;
    }
}
~~~

**Do not call this helper on the sole executor running the handlers being drained**: the waiting thread can occupy a slot needed for processing. Real shutdown also requires stopping ingress, checking queue depth, ack status, and persistence; prefer **CompletableFuture, latches, conditions, or event-driven signals** to avoid tight polling.

## 10. When the shutdown timeout expires with messages still in the queue

At the deadline, **there is no single universal operation to "force all messages to finish" safely**. Decisions depend on queue type and state:

| Remaining state | Appropriate strategy | What must never be assumed |
| --- | --- | --- |
| Unpulled messages in **in-memory QueueChannel** | Drain before shutdown or rely on a durable replay source | Will not survive JVM restart |
| Unpulled messages in **persistent QueueChannel** | Keep committed records, new consumer resumes | Cannot assume messages dequeued outside a transaction still exist |
| Tasks in **in-memory executor queue** | Finish before deadline or rely on prior durable handoff/replay | Stopping executor can lose tasks |
| Messages inside DB poller transaction | Roll back/commit per transaction manager; check connections and interrupts | Timeout does not prove rollback succeeded |
| Unacked broker delivery | Rely on adapter/broker redelivery/offset semantics | Do not assume "handler threw guarantees redelivery" |
| HTTP side effect with unknown outcome | Store UNKNOWN, apply idempotency/reconciliation | Timeout does not prove remote did not process |
| Committed pending outbox | Let new publisher send with stable eventId | Do not delete pending rows just because the app stops |
| Incomplete aggregator group | Keep persistent MessageGroupStore/metadata and expiry policy | Deleted groups cannot be reconstructed without a replay source |

### Budget expiration is not a signal to call queue.clear()

Clearing QueueChannel, truncating INT_CHANNEL_MESSAGE, resetting MetadataStore, or force-acking the broker just to get a queueDepth=0 graph can turn a **recoverable situation** into data loss. Maintain separate runbooks for **poison messages, DLQs, and retention** rather than mixing them into shutdown cleanup.

### Designing shutdown that can exit without losing work

The production goal is not necessarily "drain every backlog cleanly before the pod dies"; with huge backlogs, that may be impossible within termination grace. A stronger goal is:

1. Stop creating new work on the terminating instance.
2. Finish in-flight work if time remains.
3. For unfinished work, preserve **durable state or source replay guarantees**.
4. When a restart or another instance picks it up, **idempotency** blocks duplicate side effects.
5. Maintain observability and reconciliation for uncertain outcomes.

## 11. Impact of brokers, file adapters, and gateways when stopping

A flow with a QueueChannel in the middle may receive messages from many sources. Shutting down the **adapter** decides whether a message is retained by the source, eligible for redelivery, or already marked complete.

| Inbound source | What to verify | Risk if looking only at QueueChannel |
| --- | --- | --- |
| **JMS listener/adapter** | Session transactions, ack mode, listener container stop, redelivery | Message acked on entry to in-memory QueueChannel while worker has not processed it |
| **AMQP/RabbitMQ inbound** | Auto/manual ack, requeue, publisher confirms, consumer cancel, prefetch/unacked | Broker redelivers when connection drops; idempotency must handle duplicates |
| **Kafka inbound** | Offset commit, poll/consumer lifecycle, record processing boundary, rebalance | Offset committed while task remains in executor memory risks losing work |
| **File inbound** | Accept-once filter, file rename/move, source metadata, checkpoint | File marked seen while in-memory payload is lost on kill |
| **FTP/SFTP inbound** | Remote/local filters, download staging, file permissions, remote retention | Download complete does not mean business effect committed |
| **JDBC polling source** | Row selection SQL, status/claim update, transaction | Row marked consumed before durable handoff to processing queue |
| **HTTP inbound gateway** | Open requests, load balancer drain, timeouts, and responses | HTTP response success does not prove async workers finished |

**Every adapter has its own ack/commit contract**, so there is no universal rule that "stopping the consumer guarantees messages come back". Read your adapter's contract, acknowledgement mode, transaction manager, and container/version configuration.

### Example: broker → in-memory QueueChannel

~~~text
Broker record EV-42
   → inbound adapter receives
   → in-memory QueueChannel accepts successfully
   → broker offset/ack may commit per adapter contract
   → process killed before downstream poll
~~~

If the source **already considered delivery into QueueChannel complete**, the broker will not redeliver EV-42; the message stayed in the old heap and is lost. This is a **seam bug between ingress acknowledgement and handoff durability**, not just a small shutdown timeout.

**Architectural fix:** To preserve at-least-once delivery, ensure the source ack point occurs **after a verified durable handoff** or wrap full processing in compatible transactions/acks; use a real broker/durable queue rather than tying acks to an in-memory enqueue.

### Example: unacked broker → redelivery after kill

~~~text
Broker record EV-43 (unacked)
   → handler calls HTTP successfully
   → JVM dies before ACK
   → broker redelivers EV-43
~~~

Here **delivery is not lost**, yet **side effects can duplicate**. Preserve **business eventId/idempotencyKey** across redelivery, use inbox/outbox patterns, or apply business-compatible version/unique checks.

### File adapter: never delete or reset checkpoints arbitrarily

A received file may be recorded in MetadataStore by an AcceptOnce filter. On restart:

- An in-memory store forgets the file and re-reads it; idempotency is needed to avoid duplicate processing.
- A persistent store remembers the file and skips it; if post-filter handoff was not durably persisted, **business work can be lost**.
- A file may have been **moved/deleted** by the workflow before business transactions committed, making replay hard.

The safer option is usually **keeping original files or a staging/replay mechanism** until a durable checkpoint exists, and clearly defining when filter/metadata means "file seen" versus "processing finished".

## 12. Kubernetes: preStop, SIGTERM, and terminationGracePeriodSeconds

When a pod is deleted during rollout/scale-down, Kubernetes begins termination. If a **preStop hook** exists, it runs inside the grace period. Afterward the container runtime tells the process to stop; when the grace period expires, the container can be force-killed.

~~~mermaid
sequenceDiagram
    participant K as Kubernetes
    participant P as Pod / process
    participant I as Spring Integration
    K->>P: Pod Terminating, grace countdown begins
    opt preStop hook
        K->>P: Run preStop
        P->>I: Quiesce ingress if designed
    end
    K->>P: TERM (after preStop)
    P->>I: Spring context shutdown/lifecycle
    I->>I: Finish in-flight within remaining budget
    alt Finished before deadline
        P-->>K: Normal exit
    else Grace period expires
        K->>P: Force kill
        Note over I: Only durable/replay state has a chance to recover
    end
~~~

A pod configuration fragment:

~~~yaml
# Fragment belonging to PodSpec/Deployment.spec.template.spec
terminationGracePeriodSeconds: 90

containers:
  - name: order-worker
    image: example.com/order-worker:1.0
    # Other container fields configured in the real manifest.
~~~

**This is an illustrative fragment**, not a complete deployment manifest. If preStop is used, it **shares the same 90-second budget**. Do not put a long sleep in preStop without understanding drain state: that sleep cuts into the time Spring gets after TERM.

### Readiness, termination, and broker consumers are separate concerns

- Setting **readiness=false** helps load balancers/Services stop routing **new HTTP traffic** to the pod, though propagation and existing connections have delay.
- HTTP readiness **does not stop Kafka/JMS/AMQP consumers**; listeners need their own lifecycle/stop logic.
- In consumer groups, when one replica leaves, the broker can **rebalance** and assign partitions/records to another replica per protocol. Guard against duplicates if prior effects committed before offsets did.
- If using a **preStop HTTP call** to a management API, that endpoint must work while the pod is Terminating, be authenticated, and never accept arbitrary control expressions.

### Managing PID 1 and signals

If Java runs inside a shell wrapper that fails to forward signals properly, SIGTERM may never reach the JVM, preventing graceful shutdown. Check the entrypoint, init process, signal forwarding, and how the container actually receives TERM.

**Never rely on SIGKILL or OOM errors to run cleanup:** when the JVM is force-killed, **@PreDestroy, shutdown hooks, and transaction callbacks** may not run. That is why durable queues/replay and idempotency are independent requirements regardless of graceful shutdown.

### Spring Boot graceful web shutdown does not automatically control pollers

Spring Boot supports graceful shutdown of the embedded web server, with its own connection/request draining and timeout-per-shutdown-phase. For worker apps running both Actuator web endpoints and JMS/Kafka/file pollers:

- The web server refusing new HTTP requests **does not prove** broker/file inbound adapters have stopped.
- Closing ApplicationContext stops SmartLifecycle beans by phase, but does not automatically drain backlogs before consumers stop.
- If using **Spring Integration Orderly Shutdown** in a runbook, explicitly verify when it runs within the overall timeline, avoiding two mechanisms competing over the deadline or stopping in the wrong order.

## 13. Lifecycle, SmartLifecycle, and stop ordering

Spring Framework uses **Lifecycle** and **SmartLifecycle** to start/stop beans across the context. SmartLifecycle provides **phase** and callback-based stop; during context stop, higher-phase beans usually stop before lower-phase beans per the lifecycle processor.

This matters because:

~~~text
ordersInboundAdapter  (source)
   → QueueChannel
   → ordersProcessingPoller (consumer)
   → outbound handler
~~~

Draining requires **the source stops taking new work first**, while **the consumer keeps running** long enough. Yet SmartLifecycle ordering does not automatically know about this ingress→queue→consumer relationship in your business flow.

**Checklist:**

1. Do each endpoint's ID/bean/phase match the running flow?
2. Does an endpoint have **autoStartup=true** when the context restarts?
3. Does stopping prevent **new polls** or leave mid-flight activity running?
4. Is any executor/scheduler stopped before workers finish draining?
5. Do any bean stop callbacks run asynchronously; where does that phase's timeout end?
6. Does a **dynamic IntegrationFlow** registered via IntegrationFlowContext need separate lifecycle/registration management?

**Note:** Calling Control Bus directly with **@ordersInboundEndpoint.stop()** can pause that bean/instance, but it **does not** stop other endpoints in the right order, and a new replica after restart may auto-start unless desired state is persisted.

### Multi-instance management procedures

With three replicas, you need:

~~~text
desiredState(order-import) = DRAINING

replica A: ingress stopped, queued=0, inFlight=0
replica B: ingress stopped, queued=12, inFlight=3
replica C: ingress running, queued=0, inFlight=0
~~~

From this snapshot you cannot declare "the whole cluster is paused". Replica C is still taking messages; B is not drained yet. A **management coordinator** must aggregate state, stop the right instances, handle newly joining nodes, and enforce per-pod deadlines.

When using a **shared persistent QueueChannel**, reading replicas must use compatible store concurrency/locking; never assume replica A's queueDepth represents the whole cluster.

## 14. Shutdown is not a transaction: duplicates, outbox, and correlation

Dangerous scenario:

~~~mermaid
sequenceDiagram
    participant Q as Persistent QueueChannel
    participant W as Worker
    participant D as DB
    participant H as External API
    Q->>W: Dequeue eventId=EV-42
    W->>D: Commit business update
    W->>H: POST external operation
    H-->>W: Success
    Note over W: SIGTERM / worker killed before final checkpoint
    Q->>W: EV-42 may replay after rollback/restart
    W->>H: Re-invoked if lacking idempotency?
~~~

**Redelivered messages are not necessarily errors.** If the source transaction did not commit, replay is normal at-least-once behavior. Side effects outside the transaction may already have occurred.

To stay safe:

- Use a **stable eventId/operationId**, never attemptId or Spring MessageHeaders.ID as an idempotency key.
- For DB updates, use a **transactional inbox/unique constraint** in the same transaction as the business update.
- For outbound events, use a **transactional outbox**; publishers may republish, while downstreams stay idempotent.
- For HTTP payments or external side-effect APIs, use a **target-side idempotency key** and reconcile on timeouts/connection resets.
- Keep **correlationId** to trace multiple attempts, though correlationId is not automatically a deduplication key for a business operation.
- For aggregators/MessageGroupStore, verify release/expiry/late arrival after restart; group completion does not mean downstream effects were confirmed.

### UNKNOWN states must be persisted durably

If shutdown interrupts an external request after sending it:

~~~text
REQUESTED → IN_FLIGHT → UNKNOWN_OUTCOME
                        ↓
                    RECONCILING
                        ↓
                  CONFIRMED / FAILED
~~~

Never flip UNKNOWN_OUTCOME to FAILED just because the JVM was killed before receiving the response. Retrying without idempotency when the provider already committed can cause double charges, duplicate emails, or duplicate external events.

### Which store is the source of truth?

| Source | What does it know? | What does it not know automatically? |
| --- | --- | --- |
| QueueChannel/MessageStore | Messages existing in queue/group | Whether external side effects executed |
| Broker source | Delivery/ack/offset per protocol | Out-of-band DB business commits |
| Business DB/inbox | Committed business updates and eventIds | HTTP provider outcome unless reconciled |
| Outbox | Events recorded awaiting publish or marked sent | Whether downstream consumers applied the effect |
| External provider | Charge/request status by provider reference | Application's internal queue state |

Hence **queue depth=0** is an operational signal, not a ledger proving every operation succeeded.

## 15. Observability: knowing if you actually drained or merely timed out

In operations, observe both **lifecycle state** and **work state**. A dashboard showing only queue size can hide active tasks.

| Metric / signal | Key definition | How to read during shutdown |
| --- | --- | --- |
| **ingress.accepting** | Whether the instance still accepts new messages | Must flip to false at ingress being quiesced |
| **inbound.delivery.rate** | Message delivery rate per adapter | Should drop after pause; does not mean broker stopped publishing |
| **queue.depth** | Messages waiting in a specific queue | Should drop while draining; excludes already-dequeued messages |
| **queue.oldest.age** | Age of oldest waiting message, when measurable | Distinguishes fresh backlog from long-stuck items |
| **poller.running / poll.count** | Whether poller is active and polling | Consumers need to continue while draining |
| **handler.in_flight** | Handlers currently executing | Must reach 0 before in-process work is considered done |
| **executor.active / executor.queued / rejected** | Running tasks, queued tasks, rejected tasks | Never ignore queues outside QueueChannel |
| **transaction.commit / rollback** | Outcome per transactional resource | Check whether messages were durably removed or rolled back |
| **source.unacked** | Delivered yet unacked messages, if adapter exposes it | Can be redelivered when instance stops |
| **retry.pending / DLQ.pending** | Work awaiting recovery | Valid if durably persisted |
| **outbox.pending** | Committed events not yet published | Publisher must resume after restart |
| **shutdown.elapsed / budget.remaining** | Time spent and remaining in current shutdown | Detects overruns and reserves cleanup margin |
| **shutdown.outcome** | drained, timed_out_with_durable_pending, aborted/error | Never use a single Boolean success for all cases |

**Metrics need clear definitions:** Queue depth from JdbcChannelMessageStore may be a snapshot across concurrent transactions/replicas. Tag appropriately with **application, flow, queue, instance/region**; never put **eventId/correlationId** into Micrometer tags due to high cardinality. Business IDs belong in protected logs/traces.

### Structured shutdown log example

~~~text
operation=ORDERLY_SHUTDOWN
application=order-worker
instance=order-worker-2
phase=DRAINING
ingressAccepting=false
queueName=ordersQueue
queued=31
inFlight=4
executorQueued=0
retryPending=2
outboxPending=7
budgetRemainingMs=18000
result=IN_PROGRESS
~~~

When the deadline expires:

~~~text
operation=ORDERLY_SHUTDOWN
instance=order-worker-2
phase=FINALIZING
queued=19
inFlight=2
remainingWorkDurable=true
result=TIMED_OUT_WITH_DURABLE_PENDING
recoveryMode=RESTART_REPLAY
~~~

This is an **application-defined format**, not logs emitted automatically by Spring Integration. Do not set remainingWorkDurable=true solely because JdbcChannelMessageStore is configured: verify whether any work was dequeued to an executor, external side effects remain unconfirmed, or the broker acked early.

### Valuable alerts

- Shutdown phase exceeds deadline; process killed before cleanup completes.
- Queued message count **stops decreasing** even though ingress paused and pollers are running.
- Queue depth=0 yet **in-flight does not reach 0** past deadline.
- Message store cannot read/write; backlog fails to recover after restart.
- Executor queue grows and rejected tasks appear during drain.
- Outbox/retry pending **age** exceeds SLA even after the new pod starts.
- Duplicate **business side effects** appear after rollout, not merely duplicate deliveries.
- A new replica auto-starts ingress while desired state remains PAUSED/DRAINING.

## 16. Estimating drain time and choosing a shutdown budget

A rough estimate:

\[
T_{drain} \approx \frac{Q}{\min(\lambda_{consumer}, \lambda_{DB}, \lambda_{external})} + T_{tail}
\]

Where:

- **Q**: waiting messages, excluding in-flight.
- **lambda_consumer**: effective processing throughput of consumer/poller.
- **lambda_DB, lambda_external**: throughput caps imposed by downstream resources.
- **T_tail**: tail time of running work, retries, commits, and final acknowledgements.

This is only a **capacity estimate** once ingress has stopped. If data keeps entering, use **net drain rate = processing rate – ingress rate**; when the net rate approaches 0, draining may never finish.

Example:

~~~text
Queued = 1200
Steady processing capacity = 40 messages/s
No new ingress
→ Estimated queue drain ~ 30 s

However:
P99 external call = 15 s
Significant retry backlog
→ A 30 s deadline may be insufficient.
~~~

**Never use off-peak average throughput** as a shutdown guarantee. During rollouts, DBs may be under maintenance, brokers rebalance, and multiple replicas drain at once; speeds often differ from normal operation.

### Choosing a realistic budget

1. Measure **p95/p99 handler duration**, queue wait, throughput, retry backoff, and DB commit latency.
2. Decide whether you need to drain **the entire queue** or only **in-flight work**, allowing the rest to replay.
3. Budget for **preStop, ingress quiescence, drain, lifecycle close, and safety margin**.
4. Ensure the orchestrator grants at least the **real wall-clock total**, rather than mistakenly adding independent timeouts assuming they compose automatically.
5. Run chaos/drain tests with worse-than-normal backlog and external latency.
6. Track the ratio of **drained** versus **timed_out_with_durable_pending** across many rollouts, not one happy run.

## 17. Unit tests: stopping consumers does not empty queues automatically

Here is a small test using an in-memory QueueChannel. It **does not simulate a JVM restart**; it only proves messages stay in the queue **when no consumer pulls them**:

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.messaging.Message;
import org.springframework.messaging.support.MessageBuilder;

class QueuePendingTest {

    @Test
    void queuedMessagesRemainUntilAConsumerReceivesThem() {
        QueueChannel queue = new QueueChannel(2);

        assertTrue(queue.send(
                MessageBuilder.withPayload("EV-1").build()));
        assertTrue(queue.send(
                MessageBuilder.withPayload("EV-2").build()));

        // When consumer is stopped or does not exist, the queue does not drain itself.
        Message<?> first = queue.receive(0);
        Message<?> second = queue.receive(0);

        assertNotNull(first);
        assertNotNull(second);
        assertEquals("EV-1", first.getPayload());
        assertEquals("EV-2", second.getPayload());
        assertNull(queue.receive(0));
    }
}
~~~

**Limitation:** The test uses an in-memory QueueChannel so it proves nothing about durability. It says nothing about transactions, broker acks, executor tasks, or SIGTERM. To verify state across a JVM restart, use a **real persistent store**, shut down the process, and boot a fresh process.

### Testing timed in-flight wait

Using the InFlightTracker and DrainWaiter helpers from section 9 with CountDownLatch instead of relying on Thread.sleep:

~~~java
import static org.junit.jupiter.api.Assertions.*;
import java.time.Duration;
import java.util.concurrent.*;
import org.junit.jupiter.api.Test;

class InFlightDrainTest {

    @Test
    void returnsFalseWhenWorkStillRunsAtDeadline()
            throws Exception {
        InFlightTracker tracker = new InFlightTracker();
        ExecutorService executor = Executors.newSingleThreadExecutor();
        CountDownLatch started = new CountDownLatch(1);
        CountDownLatch release = new CountDownLatch(1);

        Future<?> task = executor.submit(() ->
                tracker.execute(() -> {
                    started.countDown();
                    try {
                        release.await();
                    } catch (InterruptedException interrupted) {
                        Thread.currentThread().interrupt();
                    }
                }));

        try {
            assertTrue(started.await(2, TimeUnit.SECONDS));
            assertEquals(1, tracker.activeCount());
            assertFalse(DrainWaiter.awaitZero(
                    tracker, Duration.ofMillis(100)));
        } finally {
            release.countDown();
            task.get(2, TimeUnit.SECONDS);
            executor.shutdownNow();
        }

        assertEquals(0, tracker.activeCount());
    }
}
~~~

This test proves **timed wait does not report drained while a handler is running**. It **does not** prove the queue is empty or side effects committed, because the tracker only counts executing methods.

## 18. Integration tests: killing the process after dequeue or after business commit

For high-reliability systems, tests should use **PostgreSQL + broker/test transport** and run the application twice in **two separate processes/containers**, preserving data in the store.

### Scenario A — Persistent QueueChannel with 20 pending messages

1. Create schema and JdbcChannelMessageStore with a **stable groupId**.
2. Send 20 messages and verify they committed in the store.
3. **Do not start the polling consumer**; stop or kill the application process.
4. Start another process using the **same DB, region/groupId, and serializer**.
5. Start the poller, wait for 20 messages to be processed, and assert each **eventId** completes with exactly one business outcome.
6. Verify no pending rows remain once processing transactions finish.

**What it proves:** Messages durably persisted in the queue survive restarts. Does not prove tasks already dequeued into executor memory survive.

### Scenario B — Poller transaction rolls back on handler failure

1. Configure a poller transaction wrapping both receive from JdbcChannelMessageStore and synchronous processing.
2. Put message EV-42 into the queue and make the handler throw a controlled exception.
3. Verify the transaction rolls back.
4. Let the poller retry per appropriate retry policy; on the next attempt let the handler succeed.
5. Assert the business DB has only one final result and the queue row is deleted upon successful commit.

**What it proves:** Transactional dequeue allows replay after rollback in the configured topology. Does not apply to every MessageStore type or async handoffs.

### Scenario C — Crash after DB commit but before ack

1. Use a broker source whose ack/offset has not committed before the test point.
2. Have the handler commit a business side effect and write inbox/outbox if applicable.
3. Inject a fault checkpoint before ack; **kill the worker process**, not graceful shutdown.
4. Restart the worker or another replica and observe redelivery.
5. Assert **the business side effect is not applied a second time** even if delivery/handler attempt counts increase.

**What it proves:** Idempotency and recovery work when commit and ack are not atomic.

### Scenario D — Deadline expires while executor still holds tasks

1. Use a small executor, hold one worker with CountDownLatch, and build a queue backlog.
2. Request shutdown with a finite deadline; verify **TIMED_OUT_WITH_PENDING** status instead of fake DRAINED.
3. Release the latch or kill the process at the designated point.
4. If the system requires replay, check that tasks were stored **durably before handoff**; otherwise, the test must expose the work-loss risk.

**You cannot make an in-JVM task queue durable with tests alone**. If the architecture lacks durable handoff, fix the design rather than weakening assertions.

### Scenario E — Kubernetes rollout with multiple replicas

1. Deploy two or more replicas, build backlog and in-flight messages.
2. Perform a rollout/scale-down to trigger real termination.
3. Verify the pod receives TERM, runs preStop if configured, and transitions through DRAINING.
4. Observe queue depth, in-flight, source unacked, and shutdown budget on each replica.
5. When one pod dies, another replica resumes from the **durable broker/store** without double side effects.
6. Repeat with backlog larger than drain capacity to exercise the **timeout path**, not only the happy path.

**Testing with Ctrl+C in an IDE is insufficient**: IDEs may terminate processes differently from container SIGTERM, and graceful restarts do not simulate forced kills.

## 19. Common troubleshooting scenarios

### Scenario A — Graceful shutdown reports done, yet 300 messages vanished

**Symptoms:**

~~~text
ordersQueue (in-memory): 300 messages
Inbound adapter: stopped
Polling consumer: stopped
ApplicationContext: closed normally
After restart: ordersQueue empty
~~~

**Likely cause:** QueueChannel lives only in the JVM; clean context close does not mean the framework persists queued messages automatically. If the source already acked upon enqueue, it will not redeliver either.

**Remediation:** Use a persistent ChannelMessageStore or durable transport, verify ack/handoff points, and add shutdown state checks. If keeping an in-memory queue, ensure a source replay contract and measure pending work on timeout.

### Scenario B — JdbcChannelMessageStore has data, yet poller sees nothing after restart

**Symptoms:** INT_CHANNEL_MESSAGE still holds rows, yet the new flow receives nothing.

**What to check:**

1. Did **groupId/queue name, region, or table prefix** change after deploy?
2. Is the new app connecting to the **right database/schema** with read permissions?
3. Is the poller endpoint **isRunning=true** and is its scheduler running?
4. Is the QueryProvider compatible with PostgreSQL/your RDBMS?
5. Can the payload/header serializer decode data written by the old version?
6. Do those rows actually belong to the **logical queue** read by the new instance?
7. Are transactions or DB locks from another consumer blocking rows?

**Never truncate tables** to "clear backlog": that can destroy all unprocessed messages.

### Scenario C — ordersQueue depth=0, yet shutdown hangs indefinitely

Possible causes:

- In-flight handler waiting on an HTTP response.
- Executor queue already pulled work from QueueChannel but has not executed it.
- DB transaction blocked on a row/lock.
- RetryAdvice backing off or poller still finishing a batch.
- Kafka/JMS container waiting for commit/ack or rebalance.

**Measure additionally:** handler.inFlight, executor active/queued, transaction age, external call latency, and source unacked. Never conclude "the framework failed to stop" just because queued=0.

### Scenario D — 60 seconds elapsed and Kubernetes still kills before drain completes

**Example timeline:**

~~~text
Kubernetes grace = 60 s
preStop consumes 15 s
Spring lifecycle may need 35 s
Extra cleanup needs 15 s
Total sequential demand = 65 s > grace
~~~

Kubernetes starts the grace countdown **before preStop**. Setting **spring.lifecycle.timeout-per-shutdown-phase=45s** does not create 45 extra seconds outside grace. Measure real durations, shorten preStop if appropriate, prioritize durable pending state, and size budgets with margin.

### Scenario E — Messages processed twice after deploy without data loss

This may be **valid redelivery behavior** from a broker or queue transaction rollback when a worker was interrupted. If an external effect succeeded earlier, the new handler risks duplicating it.

**Fix:** Keep eventId/idempotency keys across restarts, use inbox/unique constraints, optimistic versioning, outbox, and outcome reconciliation. Never "fix duplicates" by acking early before business completion, as that turns duplicates into **lost messages**.

### Scenario F — Stopping both ingress and consumer freezes backlog

**Cause:** No consumer remains to read the queue. **Fix:** Separate STOP_INGRESS state from DRAINING. Keep downstream polling consumers/workers running until criteria are met or budget runs out; only then stop downstream.

### Scenario G — Queue shrinks yet DB sees duplicates

Decreasing queue depth can simply reflect **dequeues**, not successful business completion. If a handler retries after an HTTP timeout, messages can produce duplicate side effects even when pulled from the queue only once.

**Inspect:** eventId, MessageHeaders.ID, transaction commits, retry owner, provider request ID, and idempotency; distinguish **delivery count**, **handler attempts**, and **business operation completion**.

## 20. Operations runbook for shutdown with pending queues

This is a reference procedure for a service with **broker inbound → persistent QueueChannel → polling consumer → DB/outbound**. Adapt to your Spring Integration version, adapter types, and cluster conditions.

### Phase 0 — Before rollout

Record baselines: queue depth/oldest age, in-flight count, throughput, transaction latency, unacked deliveries, pending retry/outbox, replica count, shutdown deadline, and source ack semantics. Verify recovery paths and business idempotency have been tested.

**Critical decision before starting:** If the deadline expires with messages remaining, is there a **verified replay source/durable store**? If the answer is **no** and message loss is unacceptable, do not proceed with a normal stop rollout; fix the architecture or drain backlog first.

### Phase 1 — Quiesce intake

Publish **DRAINING** or PAUSED state to the target instances/flows. Stop required inbound endpoints, lower HTTP readiness if appropriate, and verify adapters stopped accepting new work. With multiple replicas, gather state across all relevant nodes.

**Do not stop queue consumers in this phase.** Keep thread pools, schedulers, and DB connections active to process backlog.

### Phase 2 — Drain within budget

Keep pollers/handlers running and check meters each cycle against a finite deadline. Sum **queued + executorQueued + inFlight + sourceUnacked + unresolved external outcomes** instead of looking only at QueueChannel.

If transient errors occur, allow bounded retries with appropriate backoff; if data is invalid, route to recovery/quarantine per contract. Never allow unbounded retries that prevent draining from ever finishing.

### Phase 3 — Decision at deadline

| Condition | Decision |
| --- | --- |
| Queue empty, in-flight empty, critical commits/acks deterministic | **DRAINED**, close downstream/resources |
| Queue non-empty yet **committed in durable store** with new consumers able to read | **DURABLE_PENDING**, close per recovery plan |
| In-flight rolls back safely, source redelivers, and handlers are idempotent | **REPLAYABLE_PENDING**, continue shutdown with audit |
| External side effects UNKNOWN | **RECONCILE_REQUIRED**, persist state durably and run reconciliation |
| Remaining tasks/queues are **in-memory with no replay** | **DATA_LOSS_RISK**, do not declare shutdown safe |

### Phase 4 — Stop downstream, release resources

Stop downstream endpoints appropriately and terminate executors/schedulers and DB/connection pools **after drainable work finishes or is preserved**. Leave a slice of time for logging, metrics flush, and resource cleanup, without mistaking flushed logs/metrics for business data durability.

### Phase 5 — After restart

1. Confirm the new instance actually connects to **the right source/store/region/groupId**.
2. Inspect pending queues, MessageGroupStore, retry journals, and outbox from committed state.
3. Let new consumers resume with **rate/concurrency limits** so DB/remotes are not overwhelmed.
4. Reconcile eventId/operationId: verify business completions and suppressed duplicates match contracts.
5. Check UNKNOWN_OUTCOME with providers rather than issuing duplicate calls blindly.
6. Transition desired state from DRAINING/PAUSED back to RUNNING once all health conditions pass.

### Minimum shift-handoff log fields

~~~text
shutdownId=rollout-2026-11-22-001
service=order-worker
oldPod=order-worker-b
stopIngressAt=...
drainDeadline=...
finalQueued=19
finalInFlight=0
finalUnacked=0
pendingStore=JDBC
durablePendingVerified=true
outboxPending=7
externalUnknownCount=1
recoveryOwner=order-worker-new-replica
outcome=DURABLE_PENDING_RECONCILIATION_REQUIRED
~~~

These fields are a **runbook template**, not logs emitted by Spring Integration automatically. Protect the data and avoid unnecessary payloads/PII.

## 21. Lab: choosing timeouts and queue strategy during scale-down

**Prompt:** A system runs three replicas. Each replica has an inbound broker adapter; messages flow through QueueChannel to a polling consumer calling PostgreSQL and a payment service. During scale-down, one replica has queue depth=500 and in-flight=8. Kubernetes gives the pod 70 seconds to terminate, while outbound HTTP has P99 up to 12 seconds; some timed-out requests may already have created side effects.

### Tasks

1. Draw a message state diagram: broker-delivered, queued, dequeued, in-flight, business-committed, acked, unknown.
2. Determine whether **QueueChannel is in-memory or JDBC-backed** and where the broker ack occurs.
3. Assess whether 70 seconds suffices to drain all 500 messages **based on measured throughput**; if not, design durable pending/replay.
4. Choose stop order: broker ingress, QueueChannel consumers, executors, and DB/HTTP resources.
5. Explain why queue depth=0 yet inFlight=8 is insufficient to shut down immediately.
6. Propose **crash/rollback/redelivery tests** proving business effects do not duplicate.
7. Write a runbook for when a provider charge succeeded but the response was lost as the pod died.

### Solution outline

**Step 1:** Quiesce broker inbound on the terminating replica while keeping consumers running. Confirm the other two replicas can take over after rebalance.

**Step 2:** If the queue is in RAM and the broker already acked on enqueue, **replay cannot be trusted**. Migrate to durable handoff or fix the ack boundary before scaling down with critical data.

**Step 3:** If the queue is JDBC-backed, confirm messages committed, groupId/region are stable, and the poller transaction wraps receive and synchronous processing. If an intermediate ExecutorChannel exists, evaluate the handoff gap.

**Step 4:** Pick the drain budget after subtracting preStop/cleanup and safety margins. Never assume all 70 seconds go to handlers.

**Step 5:** On timeout, classify each portion: queued in DB can replay; in-flight with rolled-back transactions can retry; external UNKNOWN must reconcile; pending outbox items can be picked up by another publisher.

**Step 6:** When the new replica runs, assert complete business outcomes, no duplicate effects for the same eventId, bounded retries, and shrinking backlog.

### Self-check questions

**1. Does a 30-second Spring Boot graceful shutdown guarantee QueueChannel is empty?**

**No.** It coordinates lifecycle within the configured timeout. Queues may still hold messages; you must design drain/recovery, especially if consumers already stopped.

**2. Does a persistent QueueChannel guarantee messages running on ExecutorChannel survive a kill?**

**Not automatically.** If the dequeue committed and the task exists only in executor memory, the task can be lost. You need durable handoff or matching transaction/ack boundaries.

**3. Why not stop both ingress and consumers immediately on SIGTERM?**

**Because** consumers are still needed to read and drain the backlog. Stopping consumers too early leaves the queue intact until the process dies.

**4. Do terminationGracePeriodSeconds=90 and a 20-second preStop give Spring an extra 90 seconds after TERM?**

**No.** preStop **consumes the same grace period**. Remaining time for Spring and cleanup must fit within the total budget.

**5. If a persistent queue still has messages when shutdown times out, is that always a critical failure?**

**No.** It can be valid **DURABLE_PENDING** if messages committed, new consumers can replay, and business logic is idempotent. Record the state accurately instead of faking drained.

**6. Queue depth=0, yet a handler just POSTed a payment and lost the response; should completion be reported?**

**Not enough.** You need UNKNOWN_OUTCOME state and reconciliation/idempotency. An empty queue tells nothing about the provider-side outcome.

**7. Why can a persistent queue see duplicates after restart even with transactions?**

**Because** rollback/replay or broker redelivery can occur after an external side effect succeeded. Queue/DB transactions do not automatically span all external systems.

## 22. Production checklist

- Clearly distinguish **stop ingress, stop consumer, drain queue, graceful shutdown, and forced termination**?
- Verified whether **QueueChannel is in-memory or persistent**, not just checking the QueueChannel bean type?
- For persistent queues, are DataSource, query provider, schema, region/groupId, and serializers stable across restarts?
- Is there a **poller transaction wrapping receive()** if dequeues must roll back when handlers fail?
- Identified **handoffs across ExecutorChannel** where sender transactions do not propagate automatically?
- Avoided broker ack **before durable handoff**?
- Measuring queue depth, oldest age, executor queued, in-flight, unacked, pending retry/outbox, and unresolved side effects?
- Stopping **inbound producers first** while keeping **consumers draining backlog** up to criteria/drain budget?
- Distinguished **Spring Boot phase timeouts**, **stopActiveComponents(milliseconds)**, and **Kubernetes grace seconds**?
- If using preStop, accounted for its runtime inside the **same termination budget**?
- Does SIGTERM actually reach the Java process instead of being swallowed by a shell wrapper?
- Avoided relying on @PreDestroy/shutdown hooks for SIGKILL/OOM scenarios?
- Are HTTP/DB/lock timeouts and retry budgets tight enough not to hold in-flight work forever?
- Do you have stable eventId/idempotencyKey, transactional inbox/outbox, or provider reconciliation on redelivery?
- Prevented clearing QueueChannel/MessageStore/MetadataStore merely to shrink backlog?
- For multi-replica setups, checked desired vs actual state, consumer rebalance, and store sharing?
- Distinguished **DRAINED**, **DURABLE_PENDING**, **REPLAYABLE_PENDING**, **UNKNOWN_OUTCOME**, and **DATA_LOSS_RISK**?
- Have integration tests for **process kill with pending queues**, dequeue transaction rollback, async handoff, and real restarts?
- Tested shutdown **budget exhaustion**, not just happy paths with tiny queues?
- Have a clear runbook specifying who owns recovery and when to reopen ingress?

## Conclusion

**Shutdown timeouts and messages remaining in queues** is not merely about waiting a few extra seconds. It is about **where messages reside, who owns them, whether state is durable, when transactions/acks finish, and who resumes once the JVM disappears**.

In Spring Integration Runtime, an intentional operational order is **quiesce ingress → keep consumers/pollers running to drain → verify queued and in-flight work → close resources or preserve durable pending items on expiration → replay/idempotent recovery**. **Orderly Shutdown** helps stop sources and give in-flight messages time to finish, but does not replace a durability strategy across QueueChannel, ExecutorChannel, brokers, or external APIs.

A reliable design allows **exhausting the shutdown budget without losing work** when backlogs cannot drain, and allows **redelivery without duplicate business side effects** after restart. That requires suitable MessageStores, accurate transaction boundaries, outbox/inbox patterns, correlation, observability, and real kill/restart tests.

## References

- [Spring Integration Reference — Orderly Shutdown](https://docs.spring.io/spring-integration/reference/shutdown.html)
- [Spring Integration Reference — Configuring Message Channels and Persistent QueueChannel](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — JDBC Message Store](https://docs.spring.io/spring-integration/reference/jdbc/message-store.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration Reference — Transactions](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint/polling-consumer.html)
- [Spring Integration Reference — Control Bus](https://docs.spring.io/spring-integration/reference/control-bus.html)
- [Spring Boot Reference — Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html)
- [Spring Framework API — SmartLifecycle](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/SmartLifecycle.html)
- [Kubernetes — Pod Termination](https://kubernetes.io/docs/concepts/workloads/pods/pod-termination/)
- [Kubernetes — Container Lifecycle Hooks](https://kubernetes.io/docs/concepts/containers/container-lifecycle-hooks/)
