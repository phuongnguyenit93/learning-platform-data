# Start, Stop, Shutdown, and In-Flight Messages in DefaultMessageListenerContainer

> **Module:** Spring Framework – JMS  
> **Group:** Default container  
> **Focus:** `DefaultMessageListenerContainer` lifecycle, differences between `start()`, `stop()`, and `shutdown()`, and application/broker responsibilities for **in-flight** messages when stopping a listener.

## Learning Objectives

After this lesson, you can:

1. Describe how `DefaultMessageListenerContainer` (DMLC) creates and coordinates JMS consumers, `Session`s, and polling tasks.
2. Accurately distinguish **initialized/active**, **running/stopped**, and **shut down/destroyed**; know when `start()` can be called again and when it should not.
3. Control `@JmsListener` by endpoint ID via `JmsListenerEndpointRegistry`, while understanding that the registry only manages **containers in the current application context**.
4. Explain how a message delivered to a listener before `stop` may still be running, complete/commit, fail/roll back, or be redelivered by the broker depending on state and configuration.
5. Use `stop(Runnable)` to receive a callback when **listener processing has actually stopped** in DMLC, avoiding treating a stop request as proof all in-flight work finished.
6. Understand `setAcceptMessagesWhileStopping(false/true)`, receive timeout, consumer counts, and their impact on redelivery, stop latency, and accepting new messages during the stopping phase.
7. Configure `setSessionTransacted(true)` and distinguish it from `AUTO_ACKNOWLEDGE`, `CLIENT_ACKNOWLEDGE`, business idempotency, and DB transactions.
8. Plan graceful shutdown in Spring/Spring Boot and orchestration environments: stopping consumption, awaiting active tasks, time budgets, broker connections, and kill deadlines.
9. Analyze consequences for Queues, non-durable Topics, and durable/shared subscriptions when containers stop/restart.
10. Properly test lifecycle, in-flight behavior, broker redelivery, and data preservation without claiming a single Spring setter solves every failure.

## 1. What Is the "Default Container"?

In Spring JMS, `DefaultMessageListenerContainer` is the standard implementation for asynchronous JMS consumption. It runs one or more **consumer invoker tasks**; each task calls `MessageConsumer.receive(...)` cyclically and passes received messages to the listener. It supports self-recovery when the broker temporarily disconnects and can scale consumers up/down within configured bounds.

When using `@JmsListener`, Spring typically creates DMLC via:

```text
org.springframework.jms.config.DefaultJmsListenerContainerFactory
```

This is the **factory that creates containers**, not the running listener container itself. One factory can create many containers for many annotated endpoints.

```text
Spring ApplicationContext
  |
  +-- @EnableJms
  |     |
  |     +-- @JmsListener(id="billing.invoice.v1", ...)
  |                |
  |                v
  |         Listener endpoint
  |                |
  |                v
  |   DefaultJmsListenerContainerFactory
  |                |
  |                v
  |      DefaultMessageListenerContainer  <--- Lifecycle start/stop
  |                |
  |          JMS Session(s)
  |          JMS Consumer(s)
  |                |
  +-- JmsListenerEndpointRegistry
       ("billing.invoice.v1" -> container)
                         |
                         v
                  Broker Queue/Topic
```

The core point is **the container handles polling + lifecycle**, while **the JMS provider handles message delivery, ACK, transactions, persistence, and redelivery per contract and policy**. Business methods decide processing success/failure at the business layer.

### 1.1. DefaultMessageListenerContainer vs. SimpleMessageListenerContainer

| Characteristic | DefaultMessageListenerContainer | SimpleMessageListenerContainer |
| --- | --- | --- |
| Receive mechanism | `MessageConsumer.receive()` loop in invoker tasks | JMS asynchronous `MessageConsumer.setMessageListener(...)` |
| Dynamic consumer scaling | Configurable via `concurrentConsumers` / `maxConcurrentConsumers` | Does not share the dynamic polling model |
| Recovery on temporary broker unavailability | Built-in self-recovery/re-establishment | More limited, depends on provider and container |
| Stop/restart | Documented lifecycle and `stop(Runnable)` support | Must check subclass semantics |
| Transactions | Supports local transacted sessions or external transaction managers | Supports local semantics, unlike DMLC's polling/XA model |
| Default `AUTO_ACKNOWLEDGE` | May ACK **before listener execution**, no redelivery when method throws | Different timing; do not assume identical behavior |

This lesson focuses on **DMLC**, as meant by "Default container". Do not generalize every described behavior as a rule for all JMS listener container implementations.

### 1.2. Three States to Separate

- `isActive()` on `AbstractJmsListeningContainer` indicates the container was initialized and **not yet shut down**. It does not guarantee it is currently consuming.
- `isRunning()` indicates the container is **started, not yet stopped**. It does not guarantee the broker connection is healthy or handlers have finished messages.
- `shutdown()`/`destroy()` releases lifecycle resources; this is the **end of the container's lifecycle** along the normal destruction path, not a routine pause mechanism.

A container can be **`active=true, running=false`** after `stop()`. That state is what allows calling `start()` again without creating a new container. Conversely, after `shutdown()`, do not treat the same object as a pause/resume handle.

## 2. Lifecycle Model: initialize → start → stop → restart or shutdown

Conceptual diagram:

```text
     create / configure
             |
             v
        INITIALIZED
        active = true
             |
       start() / auto-start
             v
          RUNNING
         polls / receives
           |      \
       stop()       \ application context closing
           |         \
           v          v
         STOPPING ---> SHUTDOWN / DESTROY
           |
           | wait for processing / callbacks as applicable
           v
          STOPPED
      active may be true
           |
       start() again
           |
           +-----------------> RUNNING

   STOPPED -- shutdown()/destroy() --> DESTROYED
```

This is a **learning model**, not a public Spring state enum. DMLC has no `getState()` API returning those exact names. Stop events, callbacks, receive timeouts, transaction completions, and connection cleanups may not finish simultaneously.

### 2.1. Table of Actions and Meanings

| Action | Intent | Accepts New Messages? | In-Flight Cleared Immediately? | Can Restart Same Container? |
| --- | --- | --- | --- | --- |
| `initialize()` | Prepare resources & invokers | Depends on subsequent auto-start/lifecycle | No normal processing yet | Yes per lifecycle |
| `start()` | Start/resume consumption | Yes when broker is ready | Not directly applicable | Already running |
| `stop()` | Pause active listener so it can restart | Stops receiving during stopping process; races exist | **Must not be assumed** | **Yes** while active |
| `stop(Runnable)` | Request stop and notify when processing actually stops | Follows stop semantics | Callback arrives after processing stops per DMLC | Yes |
| `shutdown()` | Close container and release JMS resources | No | Waits/closes per implementation; deadlines/failures outside JVM exist | **Do not treat as pause/resume** |
| `destroy()` | Spring bean destruction path, calls shutdown | No | Depends on shutdown path | No |
| JVM `SIGKILL` / power loss | Kills process outside Spring's control | None from dead process | Can be cut off mid-flight | Requires new process |

**Important:** "Container stopped" and "message successfully ACKed/committed" are two separate events. A callback only reports listener processing state, not that the entire DB/JMS/broker/workflow achieved exactly-once.

### 2.2. Why Are Both active and running Flags Needed?

Suppose a listener must pause briefly for backend maintenance:

1. Container initialized: `active=true`.
2. Running: `active=true`, `running=true`.
3. Operator calls `stop()`: container halts its receive loop per lifecycle without destroying all configuration/resources.
4. After maintenance, `start()`: container resumes receiving from the destination, potentially using cached connections or recovering per provider.

If you mistakenly call `shutdown()` instead of `stop()`, you are requesting to **close** the container; resuming work typically requires creating a new container via Spring context/factory. Do not confuse `shutdown()` with a "stronger stop for resuming later".

## 3. Startup: autoStartup, Factory, and Readiness

In Spring Framework, DMLC implements `SmartLifecycle`. Auto-start is enabled by default. For annotated endpoints, the factory typically decides whether containers auto-start upon `ApplicationContext` refresh.

### 3.1. Spring JMS Java 17+ Configuration

**File `BillingJmsConfiguration.java`:**

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jms.annotation.EnableJms;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;

@Configuration
@EnableJms
public class BillingJmsConfiguration {

    @Bean("billingListenerFactory")
    public DefaultJmsListenerContainerFactory billingListenerFactory(
            ConnectionFactory connectionFactory) {

        var factory = new DefaultJmsListenerContainerFactory();
        factory.setConnectionFactory(connectionFactory);

        factory.setPubSubDomain(false);    // Queue
        factory.setSessionTransacted(true); // Local JMS transaction
        factory.setConcurrency("2-4");
        factory.setReceiveTimeout(1_000L);

        factory.setAutoStartup(true);
        return factory;
    }
}
```

Prerequisites to run:

- Spring Framework 6.x/7.x, compatible Jakarta Messaging provider, Java 17+.
- `spring-jms` dependency, Spring Context, and a real broker.
- Pre-configured `ConnectionFactory`, valid queue/ACLs.
- Spring/JMS imports and classes belong inside a **Spring project**, not a standalone JDK-only example.

`setReceiveTimeout(1_000L)` means a `receive` call waits at most roughly one second if no message is present, **not** a one-second handler execution timeout or a system-wide shutdown grace period.

`setConcurrency("2-4")` describes two to four concurrent consumers per DMLC, **not** a guarantee that four threads are always working or every message is split 25% per consumer.

### 3.2. Handler with an Explicit ID

**File `InvoiceWorker.java`:**

```java
import org.springframework.jms.annotation.JmsListener;
import org.springframework.stereotype.Component;

@Component
public final class InvoiceWorker {

    private final InvoiceService service;

    public InvoiceWorker(InvoiceService service) {
        this.service = service;
    }

    @JmsListener(
            id = "billing.invoice.worker.v1",
            destination = "billing.invoice.jobs",
            containerFactory = "billingListenerFactory")
    public void handle(String invoiceId) {
        service.process(invoiceId);
    }
}
```

`InvoiceService` is a business service provided by the project; it needs a real implementation with proper retries/idempotency. Spring invokes this method on a consumer worker thread when a message is eligible and conversion succeeds. One unique endpoint ID **does not mean** one consumer thread; the container can have multiple sessions/concurrent listeners.

### 3.3. Manual Start via autoStartup=false

If consumers must wait until database migrations, external dependencies, or warm-up finish:

```java
factory.setAutoStartup(false);
```

Spring still **registers the container** at context startup, yet does not auto-start consumers per the setting. You can start the container via `JmsListenerEndpointRegistry.getListenerContainer(id).start()` once ready.

**Caution:** calling `registry.start()` on the entire registry signals all managed listeners to start, which may violate a "manual-start" policy for a single endpoint. Use explicit IDs and scopes when starting only one container.

### 3.4. isRunning Is Not a Complete Health Probe

`isRunning() == true` only confirms Spring lifecycle was started; it does not prove:

- The broker is currently reachable and consumers registered successfully.
- Queue/topic names and receive permissions are valid.
- At least one active consumer exists.
- Handlers are processing messages within latency SLOs.
- Messages are not stuck due to selector mismatches/slow DB.
- The connection is not stuck in a recovery loop.

When determining readiness for a JMS consumer, combine container state with broker connection/consumer metrics and **successful business processing** history.

## 4. stop(): Stop Fetching More, Not "Killing" Running Methods

A key point to remember:

> `stop()` is a **lifecycle stop**, not `Thread.stop()`; it does not immediately interrupt every handler or roll back every transaction instantly.

Suppose `M1` has been received by DMLC and handler code calls a database taking 8 seconds; at second 3, the operator calls stop:

```text
t=0s    DMLC receives M1, starts handler
t=3s    operator requests stop
t=4s    M1 still inside handler / DB call
t=8s    handler may finish
t≈8s+   JMS session commits (if successful & transacted)
later   stop completion may be signalled
```

This is an **illustrative timeline**, not a promise that every handler finishes or callbacks lag by 5 seconds: it depends on provider, stop semantics, request timeouts, connections, and process deadlines.

### 4.1. Message States at Stop Time

| Message State | What Happens on Stop? |
| --- | --- |
| **Ready/pending on broker**, not yet delivered | Usually stays queued per retention/TTL; provider may deliver to another replica |
| **Received, currently inside handler** | May finish executing and commit if successful; on error/crash/rollback may redeliver |
| **Received yet not dispatched to handler at stop** | Governed by `acceptMessagesWhileStopping`/transactions/provider; may reject/roll back or process |
| **Already ACKed/committed** | JMS transport considers the receive complete; stop does not undo ACK/commit |
| **Broker-delivered/prefetched yet unexecuted** | Check broker/cache/prefetch; do not assume all ran the handler |
| **Newly published after stop** | Queue still accepts from producers; local stopped listener does not actively pull; other replicas may pull |

**Looking only at total queue depth** does not tell you whether messages are ready, in-flight, committed, or cached/prefetched. Combine broker counters and application metrics.

### 4.2. Stopping One Replica Does Not Stop the Whole Cluster

`JmsListenerEndpointRegistry` is a bean inside **one `ApplicationContext`**. Two pods listening on `billing.invoice.jobs`:

```text
Pod A: registry A -> endpoint billing.invoice.worker.v1 -> Consumer A
Pod B: registry B -> endpoint billing.invoice.worker.v1 -> Consumer B
                                         |
                                         v
                                  Same Queue
```

Calling `stop()` in Pod A does not stop Pod B. B may process more messages because A stopped pulling.

If maintenance requires **no replica at all** to consume, coordinate across the whole deployment or broker/destination routing; do not rely on a single local registry call.

### 4.3. Stop Does Not Purge the Queue

Even while the container is stopped, the broker destination can still:

- Receive messages from producers.
- Retain persistent messages in the queue.
- Enforce expiration, retention, and quotas.
- Dispatch to other active consumers.
- Route expired/poison messages per provider policy.

Do not equate `stop()` with clearing/deleting a queue. Never delete pending messages to "help stop finish faster" without business approval.

## 5. stop(Runnable): Knowing When Listener Processing Actually Stops

DMLC provides the overload:

```java
void stop(Runnable callback)
```

Per Javadoc, the callback is invoked **once all listener processing has actually stopped**. This is a much more useful synchronization point when waiting for active work before maintenance or coordinated shutdown.

### 5.1. Registry API for Annotated Listeners

**File `InvoiceListenerAdmin.java`:**

```java
import org.springframework.jms.config.JmsListenerEndpointRegistry;
import org.springframework.jms.listener.MessageListenerContainer;
import org.springframework.stereotype.Service;

@Service
public final class InvoiceListenerAdmin {

    public static final String INVOICE_ID =
            "billing.invoice.worker.v1";

    private final JmsListenerEndpointRegistry registry;

    public InvoiceListenerAdmin(JmsListenerEndpointRegistry registry) {
        this.registry = registry;
    }

    private MessageListenerContainer requiredContainer() {
        MessageListenerContainer container =
                registry.getListenerContainer(INVOICE_ID);
        if (container == null) {
            throw new IllegalStateException(
                    "Unknown listener endpoint: " + INVOICE_ID);
        }
        return container;
    }

    public void startInvoiceConsumer() {
        requiredContainer().start();
    }

    public void requestStopInvoiceConsumer(Runnable onStopped) {
        requiredContainer().stop(onStopped);
    }

    public boolean running() {
        return requiredContainer().isRunning();
    }
}
```

`MessageListenerContainer` extends `SmartLifecycle`, hence exposes `stop(Runnable)`. With DMLC, this overload runs the callback after processing stops. Never expose unauthenticated/unauthorized public HTTP endpoints for production control methods.

**Important:** `requestStopInvoiceConsumer(callback)` only requests a stop in the **current JVM**; the callback does not broadcast to all pods or prove the broker queue has zero backlog.

### 5.2. Race Conditions with Stop Callbacks

DMLC Javadoc warns:

- If you call `stop(callback1)` and then **call `stop(callback2)` again before processing stops**, the later callback may **overwrite the earlier callback**. Do not rely on every callback firing.
- If you call `start()` to restart **before stop completes**, the stop callback may **never be called**.
- The callback signals listener processing stopped; it does **not** mean separate external DB transactions, replication, checkpoints, global broker drain, or multi-replica health checks completed.
- Do not block the callback thread waiting on itself or create deadlocks with lifecycle locks.
- When shutting down the entire `ApplicationContext`, let Spring's `LifecycleProcessor` coordinate `SmartLifecycle` instead of firing chaotic stop/start calls from a controller.

If complex orchestration is needed, build a **stateful control layer**: reject duplicate stops, forbid restarts while stopping, and pair with timeouts and idempotency. Do not assume callbacks run exactly once under arbitrary racing commands.

### 5.3. Example Coordinating with a Bounded Timeout

In an operational workflow, you can use a `CountDownLatch` to await the callback, **never** unbounded:

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

CountDownLatch stopped = new CountDownLatch(1);
container.stop(stopped::countDown);

boolean finished = stopped.await(20, TimeUnit.SECONDS);
if (!finished) {
    // Alert; not yet permitted to report "all messages completed".
}
```

This is an **illustrative code snippet** inside a method that already has a `container` variable of type DMLC/`MessageListenerContainer` and an interruption policy; not a standalone file. `await` can throw `InterruptedException`, which must be handled by propagating or restoring the interrupt flag.

**A timing trap:** the callback-waiting thread's timeout **does not force** the broker, DB, or handler to finish in 20 seconds. If a timeout occurs, mark drain incomplete and execute shutdown/rollout policy; never falsely report success.

## 6. acceptMessagesWhileStopping: Messages Arriving Right at Stop Time

DMLC inherits the configuration:

```java
container.setAcceptMessagesWhileStopping(boolean accept);
```

This is a setter of `AbstractMessageListenerContainer` on the **container**, not a direct method on `DefaultJmsListenerContainerFactory`. To apply it to factory-created containers, customize during container initialization; do not copy `factory.setAcceptMessagesWhileStopping(...)` if your factory version has no such setter.

### 6.1. Default false

`setAcceptMessagesWhileStopping(false)` is the **default**.

When the container is in the middle of stopping and a receive just returned a message, the container attempts to **reject processing that message** by aborting the receive attempt. This limits expanding the set of new messages processed during the stopping phase.

However:

- A race can occur between a completed `receive` and the stop signal.
- The broker may see the message received and then rolled back/recovered; the message's delivery count may increment.
- Spring Javadoc warns that aborting such receive attempts **may decrement the remaining retry count** of the message on the broker. With high concurrency, attempts can climb as multiple consumers stop simultaneously.
- Do not claim messages are "never delivered" or "definitely preserve delivery count" during stop.

### 6.2. Setting true

`setAcceptMessagesWhileStopping(true)` lets DMLC **fully process** messages it receives during the stopping phase.

Benefit: avoids aborting an already-received message, potentially reducing stop-race redeliveries in certain workloads.

Trade-off: **may process newly sent messages while stopping**, if a receive completes before active timeouts expire. Hence drain duration can stretch if producers keep sending continuously, especially with long receive timeouts or high load.

**Neither true nor false is universally best for every system.** Choose based on stop SLAs, broker delivery-attempt policies, receive timeouts, consumer count, and whether producers can pause publishing temporarily.

### 6.3. Applying on a Manually Created DMLC

```java
DefaultMessageListenerContainer container =
        new DefaultMessageListenerContainer();

container.setConnectionFactory(connectionFactory);
container.setDestinationName("billing.invoice.jobs");
container.setMessageListener(message -> {
    // Raw listener logic.
});
container.setSessionTransacted(true);
container.setReceiveTimeout(1_000L);
container.setAcceptMessagesWhileStopping(false);
```

This is a **configuration snippet** assuming a valid `connectionFactory`, Spring JMS imports, and a Jakarta JMS provider/broker; it does not call `afterPropertiesSet()`/`start()` so it is not a complete program. It simply shows where the setter lives.

### 6.4. Customizing the Factory for Annotated Endpoints

When you genuinely need `true` for all containers from a factory, override this hook:

```java
import jakarta.jms.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.jms.config.DefaultJmsListenerContainerFactory;
import org.springframework.jms.listener.DefaultMessageListenerContainer;

@Bean("acceptWhileStoppingFactory")
DefaultJmsListenerContainerFactory acceptWhileStoppingFactory(
        ConnectionFactory cf) {

    var factory = new DefaultJmsListenerContainerFactory() {
        @Override
        protected void initializeContainer(
                DefaultMessageListenerContainer container) {
            super.initializeContainer(container);
            container.setAcceptMessagesWhileStopping(true);
        }
    };

    factory.setConnectionFactory(cf);
    factory.setSessionTransacted(true);
    factory.setReceiveTimeout(1_000L);
    return factory;
}
```

This is a **`@Bean` method inside a `@Configuration` class**, not a standalone Java file. It requires Spring/Jakarta JMS libraries and a provider. Choose it only after understanding stopping-phase trade-offs; **the default `false` is usually a safe starting point to limit accepting extra work**. Test actual behavior against your target broker.

## 7. Receive Timeout Is Not Handler Execution Deadline

DMLC relies on polling `MessageConsumer.receive(timeout)`. `AbstractPollingMessageListenerContainer.setReceiveTimeout(long)` tunes the wait time of **one receive attempt**.

```java
factory.setReceiveTimeout(1_000L);  // 1 second for one polling receive.
```

Differences:

- `receiveTimeout`: waits for a new message when the broker has no matching message yet.
- **Handler execution duration**: time the Java method spends in DB, API, transactions/CPU.
- **stop/drain duration**: time for all active listener work to finish per lifecycle.
- **Spring lifecycle shutdown phase timeout**: budget `ApplicationContext` allocates to the stop phase.
- **Orchestrator termination grace period**: time from SIGTERM to hard kill on the process/pod.

These timeouts **are not interchangeable**. If a handler stalls for 3 minutes because an HTTP client lacks a timeout, lowering `receiveTimeout` from 1 second to 100 ms **will not make the handler return in 100 ms**.

### 7.1. Overly Long Receive Timeout

A blocking receive can force the container to wait/coordinate longer depending on the provider. A long timeout reduces polling overhead, yet can delay reacting to stop signals in some implementations/configs. When the broker is actively sending messages, `receive` may return immediately despite a long timeout; that does not guarantee stopping is fast.

### 7.2. Overly Short Receive Timeout

- Polling wakes up frequently when the queue is empty.
- May increase CPU/overhead/network round-trips depending on provider.
- Does not solve a blocked in-flight handler.
- With some brokers, very short timeouts can affect utilization and startup/recovery.

Choose via benchmarks, workload, and shutdown requirements. For educational examples, `1_000L` is easy to follow, not a mandatory magic number.

### 7.3. Relationship to maxMessagesPerTask

`DefaultMessageListenerContainer` also has `maxMessagesPerTask`, `concurrentConsumers`, `maxConcurrentConsumers`, and `idleTaskExecutionLimit`. They govern how invoker tasks are scheduled and scaled, **not** "process at most N messages then destroy the container".

When using a custom `TaskExecutor`, know whether the executor prefers short-lived tasks; a consumer invoker can hold a thread long-term. Do not assume a thread pool size of 10 means 10 tasks finish promptly on stop.

## 8. Critical Data Concerns: ACK, Transactions, and Crash Windows

`stop` relates to when receives occur; **message loss or duplication** depends on acknowledgment/commit semantics.

### 8.1. AUTO_ACKNOWLEDGE on DMLC

Per Spring Javadoc, with `DefaultMessageListenerContainer` and default `AUTO_ACKNOWLEDGE`, messages may be **ACKed before listener execution**. When a business method throws an exception, the container **gives no guarantee the broker redelivers that message**.

Dangerous example:

```text
receive M
   |
   +-- AUTO_ACK applied before handler (DMLC)
   |
   +-- handler writes DB / calls API
          |
          +-- exception / JVM killed
               |
               +-- M may already be acknowledged
```

An ill-timed hard shutdown can leave business work unfinished with no message left to retry. This is why Spring docs recommend local transacted sessions or an appropriate transaction manager when reliability is required.

### 8.2. sessionTransacted=true

`DefaultJmsListenerContainerFactory.setSessionTransacted(true)` wraps each receive + processing in a **local JMS transaction**:

```text
Broker delivers M
   |
   v
JMS Session transacted
   |
   +-- handler success ----> commit JMS receive
   |
   +-- handler throws -----> rollback JMS receive
                               |
                               +-- provider redelivery policy
```

When the process dies before commit, the JMS broker can redeliver uncommitted messages after recovery per transaction/delivery semantics. Broker specs and persistence remain vital; configure reliable delivery without assuming business transactions are atomic.

If the handler already wrote to the DB successfully yet crashes **before JMS commit**, the message can redeliver and repeat the business effect. Thus:

> **Transacted JMS reduces message-loss risk, yet does not automatically provide exactly-once business effects if DB and JMS commit independently.**

### 8.3. Local JMS Transactions Do Not Cover the DB

Timeline:

```text
t0 receive M in JMS tx
t1 update DB & DB commits
t2 JVM crashes before JMS session.commit()
t3 broker redelivers M
t4 handler tries DB update again
```

You need:

- A unique, business-meaningful `businessEventId`.
- An idempotent handler / unique constraint or processed-event table.
- Compatible DB transaction design.
- Outbox/inbox/XA if cross-system atomic coordination is needed, accepting performance trade-offs.
- Retry/DLQ policies for poison messages so processing does not stall forever.

### 8.4. CLIENT_ACKNOWLEDGE, DUPS_OK, transacted

| Mode | Meaning for DMLC on Listener Failure/Stop/Crash |
| --- | --- |
| `AUTO_ACKNOWLEDGE` | ACKs before listener; do not rely on redelivery after errors |
| `DUPS_OK_ACKNOWLEDGE` | Lazy ack; may see duplicates on crash without guaranteed retry on all exceptions |
| `CLIENT_ACKNOWLEDGE` | Container acks after success; best-effort redelivery on exceptions/interruptions |
| `sessionTransacted=true` | JMS transaction, rolls back on listener failure; reliable redelivery per spec/provider |
| External XA/JTA manager | Can coordinate JMS + other resources if XA-aware, increasing complexity and overhead |

These rows describe **Spring DMLC reference/Javadoc**, not every consumer API or all brokers identically. Always verify your Spring/JMS versions, configured container, and test real failures.

### 8.5. When the Handler Catches Exceptions and Returns

```java
@JmsListener(destination = "billing.invoice.jobs")
public void onInvoice(String id) {
    try {
        businessService.process(id);
    } catch (Exception ex) {
        logFailure(ex);
        // return normally
    }
}
```

This is an **anti-pattern snippet** assuming valid service/log methods exist. Catching and returning normally inside a transacted session lets the container **commit the JMS transaction** because it sees no error. A failed message can vanish without quarantine.

If intentional terminal rejection is desired, ensure the message is persisted to DLQ/quarantine or a consistent business outcome is recorded **before commit**. Otherwise, propagate the error so rollback/retry policies take effect.

## 9. "In-Flight Messages" Are the Hardest Boundary During Shutdown

Distinguish four timestamps:

```text
receiveTime  handlerStart       handlerReturn    JMSCommit
    |             |                   |              |
    v             v                   v              v
    +-------------+-------------------+--------------+
             |                 |
         stop requested     DB commit may occur here
```

There is no rule that stop arrives at one convenient point:

- Stop before `receiveTime`: container may skip receiving, though another consumer may still take it.
- Stop after receive, before handler: outcome depends on stopping policy, prefetch, and transactions.
- Stop mid-handler: handler may run to completion; crash or error may cause rollback.
- Stop after handler return yet before JMS commit: delivery outcome is not yet safely finalized.
- Stop after JMS commit: JMS message is already acknowledged/committed; stopping will not replay it automatically.

### 9.1. What Should Graceful Stop Aim For?

A commonly desired strategy:

1. **Do not accept new workload for too long.**
2. **Do not cut off business operations already inside handlers** within bounds.
3. **Explicitly commit or roll back** every JMS transaction.
4. **Do not lose `eventId` / traces / database side effects**.
5. **Release resources before the process is hard-killed**.
6. **Allow uncommitted messages to redeliver** if abruptly terminated.
7. **Do not accidentally pull more messages once the instance is marked terminating**.

Achieving this requires properly configuring lifecycle, QoS, broker retention, DB idempotency, and shutdown deadlines—not just calling `stop()`.

### 9.2. If Business Calls Lack Timeouts

Suppose a handler calls an external API with no read timeout. A thread can hang indefinitely, preventing the stop callback from arriving on schedule and blowing the shutdown budget. You need:

- Explicit HTTP connection/read timeouts.
- Appropriate DB query/transaction timeouts.
- Cancellation/interrupt handling if supported by libraries.
- Circuit breakers/backoff for transient errors.
- Idempotent retries if the process must be killed.
- Not holding DB locks across a long stop window.

`receiveTimeout` only governs polling; it will not rescue a handler blocked in an external call.

### 9.3. If Side Effects Ran Before JMS Commit

A message can **redeliver** even when external business logic succeeded before ack could commit. Therefore in shutdown tests measure:

- Messages attempted/delivered by the broker.
- Handler invocations.
- **Unique business event IDs** committed.
- Duplicate attempts / idempotency skips.
- JMS transactions committed/rolled back.

Checking "processed" log lines alone does not prove the broker committed message receipt.

## 10. stop, shutdown, destroy: Choose the API for the Goal

### 10.1. Use stop() to Pause/Resume

Internal operational example once you have the container:

```java
MessageListenerContainer container =
        registry.getListenerContainer("billing.invoice.worker.v1");

if (container == null) {
    throw new IllegalStateException("Listener not found");
}

container.stop();  // Pause per lifecycle.
container.start(); // Can restart after stop completes.
```

This is a **Spring project snippet** with an injected `registry`; do not call them back-to-back in production without awaiting stop completion. Do not restart while `stop(Runnable)` is still waiting without understanding callback races.

### 10.2. Do Not Call shutdown() to Pause

`shutdown()` on `AbstractJmsListeningContainer`:

- Stops the shared JMS `Connection` if present.
- Calls `doShutdown()` to close registered invokers/resources.
- Closes the lifecycle container.
- Is invoked by `destroy()` when `BeanFactory` destroys the container.

```java
// Illustrative only on a clearly owned/managed instance:
DefaultMessageListenerContainer container = ...;
container.shutdown();
```

This is a **pseudocode fragment**. Never call `shutdown()` directly on a container managed by `JmsListenerEndpointRegistry` just for brief maintenance. Spring context handles destruction; a mistaken manual shutdown can leave the registry holding a key pointing to an inactive container.

### 10.3. Comparing Post-Action Lifecycles

| After Operation | Can DMLC Be Reused? | Who Is Responsible Next? |
| --- | --- | --- |
| stop completed | Can `start()` again | Registry / application |
| shutdown/destroy completed | Not a restartable handle | Recreate container / context |
| Spring context closed | Do not use destroyed managed beans | Restart app / context |
| Pod killed | Entire process gone | Orchestrator restart; broker recovery |
| Durable topic consumer stopped | Subscription may persist on broker | Broker + subscription identity |
| Non-durable topic stopped | Subscription may no longer be active | Producer / consumer lifecycle |

Broker and subscription conditions can yield different message behavior **even when the same stop/shutdown is invoked**.

## 11. Spring SmartLifecycle and ApplicationContext Closing Order

DMLC implements `SmartLifecycle`; in Spring, lifecycle phases govern start/stop order:

- Lower phases **start first**.
- Higher phases **start later**.
- On normal phase-based shutdown, higher phases **stop first** (reverse order).

`AbstractJmsListeningContainer.setPhase(int)` controls phase. Default is `SmartLifecycle.DEFAULT_PHASE`, a very high value; listeners normally start late and stop early in the default order.

### 11.1. When Is Phase Useful?

Suppose handlers rely on an internal executor/service to process messages:

```text
Startup:
  dependencies ready first
         |
         v
  JMS consumers start later

Shutdown:
  JMS consumers stop/drain first
         |
         v
  dependencies/executors shut down later
```

Set phases and bean dependencies so consumers **are no longer running handlers after services those handlers need have been destroyed**. Verify phase behavior in the registry and individual containers rather than treating a `setPhase` number as an absolute guarantee for every dependency.

### 11.2. Phase Config Example

```java
@Bean("invoiceListenerFactory")
DefaultJmsListenerContainerFactory invoiceListenerFactory(
        ConnectionFactory cf) {

    var factory = new DefaultJmsListenerContainerFactory();
    factory.setConnectionFactory(cf);
    factory.setSessionTransacted(true);
    factory.setAutoStartup(true);
    factory.setPhase(100);
    return factory;
}
```

This is **one `@Bean` method** inside a `@Configuration` class with proper imports; not standalone. `100` is an illustrative value, **not a default recommendation**. With `@JmsListener`, `JmsListenerEndpointRegistry` also participates in annotated container lifecycles; verify actual shutdown order via logs/tests on your running Spring version.

### 11.3. Watch Out for Shutdown Phase Timeout

Spring's `LifecycleProcessor` supports a timeout waiting for stop callbacks per phase. If the wait budget is only 10 seconds while a handler can run 45 seconds, the listener's callback may arrive after the phase expires, and dependencies may proceed to close per policy. Do not tune `receiveTimeout` alone to "solve 45 seconds"—account for worst-case handlers and deployment deadlines.

## 12. Spring Boot Graceful Shutdown Does Not Automatically Guarantee JMS Drain

An easily confused point: Spring Boot's **HTTP server graceful shutdown** configuration and JMS listener shutdown lifecycles are separate parts of a Spring application.

In Spring Boot 3.x, you commonly see:

```yaml
server:
  shutdown: graceful

spring:
  lifecycle:
    timeout-per-shutdown-phase: 40s
```

Spring Boot 4.x has different defaults for embedded web servers, so read docs for **your exact version**. `spring.lifecycle.timeout-per-shutdown-phase` configures how long Spring waits per lifecycle stop phase—it is **not** a promise every JMS transaction finishes within 40 seconds or a setting attached directly to DMLC.

### 12.1. Three Different Time Budgets

| Duration | Where Configured? | Effect |
| --- | --- | --- |
| JMS receive timeout | `factory.setReceiveTimeout(...)` | Wait duration of a single receive |
| Spring lifecycle phase timeout | `spring.lifecycle.timeout-per-shutdown-phase` | Budget Spring `LifecycleProcessor` waits for callbacks in a phase |
| Orchestrator stop grace period | Kubernetes `terminationGracePeriodSeconds` or equivalent | From SIGTERM to potential hard kill |
| Handler timeout | HTTP/DB/client/business logic | Bounds external calls/CPU/transactions individually |
| Broker redelivery delay | Provider policy | Wait before a redelivery/retry |

If Pod termination grace = 15s while Spring lifecycle timeout = 40s, **the orchestrator can kill the process before** Spring finishes waiting. Graceful shutdown cannot be guaranteed by Spring YAML alone.

### 12.2. Example Rolling Deployment Timeline

```text
t=00s  Orchestrator marks pod terminating, sends SIGTERM
t=01s  ApplicationContext begins graceful shutdown
t=02s  JMS container gets stop signal
t=03s  Handler M1 still working
t=08s  Handler M1 completes, JMS commit occurs
t=09s  DMLC stop callback may run
t=10s  Remaining Spring beans shut down
t=12s  Process exits

Hard kill deadline might be at t=30s.
```

This is only a **desired timeline**, not a guaranteed mechanism. If the handler does not finish before the deadline, the OS/orchestrator may force-stop it and the broker handles uncommitted messages per config. Protect business data with idempotency and transactional correctness.

### 12.3. Readiness and Traffic Drain

During a rolling deploy with multiple replicas:

1. Mark the instance not to receive **new HTTP traffic** (if the app has web entry points).
2. Stop/reduce JMS receiving per policy. **HTTP `readiness=false` does not automatically stop JMS listeners**.
3. Wait for in-flight processing to finish within budget.
4. Let the broker redistribute queue messages to remaining active replicas.
5. Close the context and let the process exit.

If you need "stop pulling new JMS messages", you must **stop JMS containers** or control receiving/broker routing; HTTP readiness probes only affect HTTP load balancers.

## 13. Queue vs. Topic When Stopping Default Container

### 13.1. Queue

- **Undelivered** messages usually stay in the Queue per TTL/retention/quota.
- If another consumer on the same Queue is running, the broker can dispatch to it.
- **Received yet uncommitted** messages can redeliver on rollback or connection loss.
- A message may have committed a DB side effect without JMS commit → duplicate on redelivery.
- `stop()` does not clear the Queue and does not guarantee backlog drops to 0.

### 13.2. Non-Durable Topic Subscription

When a non-durable consumer/subscription is inactive, publishers can keep sending events yet **a new subscription does not retroactively receive** events published before it existed. Thus pausing a non-durable listener can lose events, even if the producer uses persistent delivery.

Do not ship "stop then start again will automatically read all published events" with a non-durable Topic. If business logic needs offline replay, design a durable subscription **before** publishing.

### 13.3. Durable Topic Subscription

A durable subscription is identified and retained per Jakarta Messaging/provider rules:

- While the consumer is stopped, matched messages can accumulate pending for the subscription.
- `DeliveryMode`, TTL, broker retention, quotas, and subscription identity still apply.
- Changing `clientId`/`subscription` on restart can make the consumer read a **different** subscription, missing the old backlog.
- Durable does not mean exactly-once business processing.
- With shared durable subscriptions, consumers sharing a subscription split load; with separate subscriptions, each gets its own backlog.

**Do not use `@JmsListener.id` in place of the broker-side durable subscription name**. Container endpoint ID is a Spring registry key, whereas subscription/client ID belongs to JMS transport lifecycle.

### 13.4. Comparison

| Intent | Queue | Non-Durable Topic | Durable Topic |
| --- | --- | --- | --- |
| Pause local listener | Queue backlog may remain, or other consumers pull | Events during unsubscribed period may be lost | Matched events may build subscription backlog |
| Restart | Can receive pending queue messages | Only events after subscription becomes active again | Can read matched backlog per policy |
| Multiple replicas | Competing consumers | Separate subscriptions may each get copies | Shared/unshared identity must be designed explicitly |
| Effect of in-flight rollback | May redeliver | Depends on provider/subscription lifecycle | May redeliver per transaction/subscription state |

## 14. Connection Recovery Is Not an Operator Stop/Restart

DMLC has self-recovery when the broker is temporarily unavailable. If the broker disconnects while running, the container can:

- Log the connection error.
- Wait per `recoveryInterval`/`BackOff`.
- Re-establish Connection/Session/Consumer.
- Resume receiving when infrastructure returns.

Spring DMLC's default `setRecoveryInterval(...)` is **5,000 ms** on the cited versions. This value is the connection recovery retry interval, **not the redelivery delay for a rolled-back message**.

```java
factory.setRecoveryInterval(5_000L);
```

While the broker is down, `container.isRunning()` can stay true even with no active consumer actually connected. Unlike operator `stop()`, the recovery loop means the container wants to keep running while handling an infrastructure outage.

### 14.1. Do Not Look Only at isRunning

Useful DMLC metrics:

- `getActiveConsumerCount()`: active consumer invokers per container.
- `getScheduledConsumerCount()`: scheduled consumers.
- `isRegisteredWithDestination()`: whether a consumer has established a fixed destination registration in applicable cache modes.
- Broker consumer count, connection status, enqueue/deliver/ack rates.
- Listener success/failure, timeouts/latency, DLQ, and oldest message age.

DMLC counts/flags **do not replace broker metrics**, especially with caching, provider prefetch, transacted receives, or connection recovery.

### 14.2. CachingConnectionFactory and Stop/Restart

Spring DMLC Javadoc advises caution when using `CachingConnectionFactory` outside a listener container: DMLC typically has its own session/consumer caching. Stop/restart may need an **isolated local Connection cache**, not an externally shared cache causing unexpected semantics.

If after stopping the broker still shows cached consumers, do not assume the container is still receiving messages; check provider, cache level, external connection factory, and counters, then test on your exact broker version.

## 15. Diagnosing When Stop "Does Not Stop" or Messages Duplicate

### Scenario A — Business Logs Keep Appearing After Stop

Possibilities:

1. Handler started **before** stop.
2. `acceptMessagesWhileStopping=true` allowed a message received during the stopping phase to be processed.
3. Operator stopped only one replica while other replicas kept consuming.
4. Stop callback had not arrived yet; pending work was still finishing.
5. Logger flushed asynchronously/late, not reflecting handler start time.
6. Another listener container on the same destination was not stopped.

Action: record `eventId`, `endpointId`, instance, and receive/start/end/commit timestamps, and await the stop callback before concluding. Do not escalate straight to force-kill without classifying in-flight work.

### Scenario B — Queue Depth Grows After Stop

This is usually **not a bug**: producers keep publishing while consumers paused, so backlog grows. Monitor arrival rate, TTL, disk quotas, broker producer flow control, and whether other consumers can pick up work.

If queue growth is unacceptable, coordinate upstream throttling/backpressure or durable storage sizing. Never purge a queue just to make a dashboard look clean.

### Scenario C — Same eventId Processed Twice After Restart

Possible causes:

- Earlier JMS receive had not committed when the process stopped/crashed.
- Handler committed DB before JMS commit, and the message redelivered.
- Producer retried and emitted the same business event again.
- Same event appeared multiple times upstream.
- Topic had multiple independent subscriptions and you aggregated logs across replicas.

Fix: business idempotency, inspect `JMSRedelivered`, processed-event tables, transaction logs, and broker delivery policies. Never "fix" by disabling persistence or ACKing early.

### Scenario D — Graceful Shutdown Takes Too Long

Look for:

- Long-running handlers that have not returned.
- Large receive timeouts / slow provider stop.
- `acceptMessagesWhileStopping=true` continuing to process newly received messages.
- External HTTP/DB calls without timeouts.
- High concurrency with many pending in-flight tasks.
- Mismatched lifecycle phase timeout and orchestrator grace period.
- Cross-bean shutdown order closing dependencies before handlers finish.

Change one parameter at a time and measure rather than dropping every timeout near 0 simultaneously.

### Scenario E — Stop Increments Message Redelivery Count

With `acceptMessagesWhileStopping=false`, DMLC can abort receive attempts happening during stop; Spring Javadoc warns this can consume provider retry counts. A broker with a low delivery limit and high concurrency can route messages to DLQ even before business methods run.

Risk mitigation: check broker retry policies, concurrency, stop timing, and evaluate `acceptMessagesWhileStopping` from test results. **Never** configure infinite retries without DLQ/quarantine and observability.

### Scenario F — SIGKILL Before JMS Commit

Spring cannot run normal cleanup; network connections may drop mid-transaction. With transacted receives and a reliable broker, uncommitted messages can redeliver. If code causes side effects, idempotency is mandatory.

Do not claim graceful shutdown works under hard kill, because `SIGKILL` prevents Spring from executing shutdown hooks.

## 16. Designing a Safe Pause/Resume Operational Procedure

Minimum runbook for **one local endpoint**:

1. **Exact identification:** service, env, pod, endpoint ID, Queue/Topic/durable subscription, and broker namespace.
2. **Authorization:** authorized operators only; audit reason and timestamp.
3. **Pre-stop checks:** inspect in-flight tasks, max handler duration, queue backlog, and other active consumers.
4. **Stop request:** use `registry.getListenerContainer(id).stop(callback)` when drain completion must be known.
5. **Bounded wait:** callback arrives or timeout expires; never treat timeout as success.
6. **Verify:** broker consumer/in-flight counts, handler in-progress gauge, JMS commits/rollbacks, and DB side effects.
7. **Evaluate backlog:** if Queue pending grows, confirm whether expected or nearing quota.
8. **Maintenance:** update dependencies/config once no handler uses them.
9. **Restore:** call `start()` on that exact local endpoint or spin up a fresh context.
10. **Post-start:** verify broker registration, successful processing, oldest age/throughput, and error rate.
11. **Distributed:** coordinate across all replicas when a global pause is needed.
12. **Rollback plan:** if stop is incomplete, never delete messages; let provider/JMS transactions recover per policy and watch for duplicates.

### 16.1. Runbook When Deploying Multiple Replicas

For a Queue with 3 replicas A/B/C:

- Mark A terminating and stop A's listener, while letting B/C keep processing.
- Wait for A's in-flight work (within grace budget).
- Replace A with A' and verify A' connects/consumes properly.
- Repeat for B, then C.

**Do not** stop all of A/B/C simultaneously if the queue lacks disk/backlog headroom or upstream keeps publishing heavily. Conversely, if a broker schema migration requires stopping everything, plan for message/quota handling and producer coordination.

### 16.2. Production Must Not Expose Unconditional Stop/Start

An unauthenticated HTTP API `POST /jms/stop?id=...` is an operational and security hazard. If a control plane is needed:

- Strong authentication/authorization and an endpoint ID allowlist.
- Audit every command and requester.
- Block duplicate/racing operations.
- Return **requested / draining / stopped** states, not just "200 OK".
- Do not treat a remote RPC 200 as cluster-wide callback completion.
- Enforce timeouts, idempotency, rollbacks, and clear ownership.

## 17. Lifecycle Integration Testing Against a Real Broker

### Test A — autoStartup=false Then Start

1. Configure a factory with `setAutoStartup(false)`.
2. Start the Spring context; verify the registry holds the endpoint ID while the container is not running.
3. Send a message to the Queue.
4. Verify the message remains pending when no other consumer/expiry applies.
5. Call `start()`; verify the listener receives and processes it.
6. Stop and start again to verify normal pause/resume.

### Test B — Stop Mid-Handler

1. Use a test handler that signals `started` via a latch.
2. Hold the handler before completion with a second latch.
3. Producer sends `M1`.
4. After the `started` latch trips, call `container.stop(callback)`.
5. Verify the callback **has not fired while the handler is still running** (for DMLC and this test config).
6. Release the handler to finish; verify the callback fires after processing stops.
7. Check broker commit/ack and business outcome; do not assert the callback alone.
8. Use timeouts on all latches and clean up test broker resources.

### Test C — Transacted and Failure

1. `setSessionTransacted(true)`; handler records `eventId` and intentionally throws in a controlled case.
2. Verify rollback/redelivery per broker policy.
3. Add business idempotency; prove duplicate attempts produce no duplicate side effects.
4. Verify DLQ/quarantine after exceeding attempts.
5. Repeat with `AUTO_ACKNOWLEDGE` in a separate test queue and document that redelivery may not occur.

### Test D — acceptMessagesWhileStopping

1. Run DMLC with `false` and concurrency > 1.
2. Producer fires messages concurrently with stop; measure callback duration, delivery counts, and DLQ.
3. Repeat with `true`, identical load and receive timeout.
4. Compare messages processed during the stopping phase and retry consumption.
5. Pick the policy from real measurements, not guesswork.

### Test E — Stop 1/3 Replicas

1. Run three app instances connected to the same test Queue.
2. Stop the registry/container on one instance.
3. Verify the other two replicas continue receiving.
4. Verify A processes no new messages after callback completion, logging any prior in-flight work.
5. Restart A and verify consumer counts recover.
6. Do not share unshared durable topic `clientId` across distinct Queue/Topic tests.

### Test F — Non-Durable vs. Durable Topic

1. Create a non-durable Topic listener, publish E1, stop listener.
2. Publish E2 while the subscription is inactive; restart and verify E2 replay is not guaranteed.
3. Create a durable subscription with fixed provider-valid identity and repeat.
4. Observe matched E2 can enter durable backlog per TTL/delivery mode/broker policy.
5. Ensure subscription name/`clientId` never changes between runs.

### Test G — Kill Between DB Commit and JMS Commit

1. Handler receives `eventId` and commits business effect to DB.
2. At a test barrier right before JMS receive transaction commit, hard-kill the process in a test environment.
3. Restart the consumer; inspect redelivery.
4. Verify idempotency prevents duplicating the business effect.
5. Check broker delivery counts and DLQ policies; never test this in production.

### Test H — Shutdown Deadline

1. Simulate handlers taking 5s and 20s with varying grace periods.
2. Trigger Spring `ApplicationContext` close through standard test paths.
3. Observe Spring `SmartLifecycle` stop order, callbacks, bean destruction, and process exit.
4. Simulate a short orchestrator kill deadline; verify incomplete transactions redeliver.
5. Also test broker unavailability during shutdown to observe recovery/timeout behavior.
6. Do not declare success solely because process exit code = 0.

## 18. Standalone Java 17: Simulating In-Flight During Stop

The program below uses **JDK 17 only**, with no JMS broker and no Spring dependencies. It models Queue readiness, an in-flight message, a stop request, completion, and shutdown. **This is a state-machine demo**: it does not reproduce every race, commit timing, or provider behavior.

Create **`ListenerLifecycleDemo.java`**:

```java
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.List;
import java.util.Queue;

public final class ListenerLifecycleDemo {

    enum State { STOPPED, RUNNING, STOPPING, DESTROYED }

    static final class Listener {
        private State state = State.STOPPED;
        private final Queue<String> ready = new ArrayDeque<>();
        private final List<String> committed = new ArrayList<>();
        private String inFlight;

        Listener(String... messages) {
            for (String message : messages) {
                ready.add(message);
            }
        }

        void start() {
            if (state == State.DESTROYED || state == State.STOPPING) {
                throw new IllegalStateException(
                        "Cannot start from " + state);
            }
            state = State.RUNNING;
        }

        String receive() {
            if (state != State.RUNNING || inFlight != null) {
                return null;
            }
            inFlight = ready.poll();
            return inFlight;
        }

        void stop() {
            if (state == State.RUNNING) {
                state = inFlight == null
                        ? State.STOPPED : State.STOPPING;
            }
        }

        String finish() {
            if (inFlight == null) {
                throw new IllegalStateException("No message in flight");
            }
            String id = inFlight;
            committed.add(id);
            inFlight = null;
            if (state == State.STOPPING) {
                state = State.STOPPED;
            }
            return id;
        }

        void shutdown() {
            if (inFlight != null) {
                throw new IllegalStateException("Not drained");
            }
            state = State.DESTROYED;
        }

        State state() { return state; }
        String inFlight() { return inFlight; }
        List<String> ready() { return List.copyOf(ready); }
        List<String> committed() { return List.copyOf(committed); }
    }

    public static void main(String[] args) {
        Listener listener = new Listener("JOB-1", "JOB-2");

        listener.start();
        System.out.println("Received: " + listener.receive());

        listener.stop();
        System.out.println("Stop requested: " + listener.state());
        System.out.println("In-flight: " + listener.inFlight());
        System.out.println("Receive while stopping: "
                + (listener.receive() == null ? "none" : "unexpected"));

        System.out.println("Completed: " + listener.finish());
        System.out.println("State after drain: " + listener.state());
        System.out.println("Pending: " + listener.ready());

        listener.start();
        System.out.println("Restart received: " + listener.receive());
        System.out.println("Completed: " + listener.finish());
        System.out.println("Committed: " + listener.committed());

        listener.shutdown();
        System.out.println("Shutdown state: " + listener.state());

        try {
            listener.start();
        } catch (IllegalStateException ex) {
            System.out.println("Restart after shutdown: REJECTED");
        }
    }
}
```

Run commands:

```bash
javac ListenerLifecycleDemo.java
java ListenerLifecycleDemo
```

**Exact stdout:**

```text
Received: JOB-1
Stop requested: STOPPING
In-flight: JOB-1
Receive while stopping: none
Completed: JOB-1
State after drain: STOPPED
Pending: [JOB-2]
Restart received: JOB-2
Completed: JOB-2
Committed: [JOB-1, JOB-2]
Shutdown state: DESTROYED
Restart after shutdown: REJECTED
```

Explanation:

- `JOB-1` is received before stop.
- Stop transitions to `STOPPING` while in-flight work exists.
- `receive()` refuses new messages while stopping is underway.
- `finish()` models handler completion and JMS commit, transitioning to `STOPPED`.
- `JOB-2` stays in `ready` until restarted.
- `shutdown()` moves to the terminal lifecycle state; subsequent `start()` is rejected.

This is a **sequential simulation**, not running Spring `DefaultMessageListenerContainer`. In a real JVM/JMS setup, commits/rollbacks happen via JMS `Session`/container, and receive timeout/connection/provider races vary; `stop()`/`shutdown()` do not return a `State` enum like the demo. Its goal is showing **in-flight work does not vanish just because stop was requested**.

### 18.1. Exercises Extending the Demo

1. Add `rollback()`: put `inFlight` back at the front of `ready` and increment an attempt counter instead of appending to `committed`.
2. Add `deadline`: if stop takes too long, simulate process kill and JMS redelivery after restart.
3. Add a second listener sharing the Queue: only one consumer receives `JOB-2` per delivery.
4. Add idempotency `Set<String> processedIds` to skip side effects when `JOB-1` is redelivered.
5. Compare the `STOPPING` state in the demo with DMLC's `stop(Runnable)` callback, **without treating this as an implementation of the real callback**.

## 19. Common Mental Errors

**Error 1 — "`stop()` deletes all running messages."**  
No. Stop controls listener lifecycle; in-flight work may continue, commit, roll back, or be interrupted by process failure.

**Error 2 — "`stop()` is the same as `shutdown()`."**  
No. `stop()` is for pause/resume; `shutdown()` closes lifecycle/resources and should not be used to restart the same object.

**Error 3 — "`isRunning=false` means no handler method is still executing."**  
Insufficient. Use stop callbacks/drain monitoring to confirm processing stopped.

**Error 4 — "`isRunning=true` means the broker connection is healthy."**  
Insufficient. DMLC may be retrying recovery while lifecycle stays running.

**Error 5 — "Stopping one Pod stops the entire cluster from consuming."**  
False. The registry is local; other replicas keep receiving.

**Error 6 — "`stop()` purges the Queue."**  
False. Broker queue/pending state is separate.

**Error 7 — "Every message arriving during the stopping phase is guaranteed to be processed."**  
No. Default `acceptMessagesWhileStopping=false` can reject receive attempts.

**Error 8 — "`acceptMessagesWhileStopping=true` is always safer."**  
No. It may keep processing new messages during stop, lengthening drain.

**Error 9 — "`acceptMessagesWhileStopping=false` has no impact on retries."**  
Not quite. Spring Javadoc warns aborting receives can consume provider delivery attempts.

**Error 10 — "`receiveTimeout=1s` times out handlers after 1s."**  
False. It is only the wait time per JMS receive.

**Error 11 — "`stop(callback)` callback always fires even on double stop or early restart."**  
No. DMLC documents callback overwrite/cancellation races.

**Error 12 — "Enabling `sessionTransacted=true` makes DB + JMS commit atomic."**  
No. A local JMS transaction does not automatically include the database.

**Error 13 — "`AUTO_ACKNOWLEDGE` retries if the handler throws."**  
You cannot rely on this with DMLC; it may ACK before the listener runs.

**Error 14 — "JMS transactions guarantee exactly-once business effects."**  
No. Crashing between business commit and JMS commit can cause duplicate processing.

**Error 15 — "`server.shutdown=graceful` suffices to stop JMS safely."**  
No. That is web server shutdown; listener lifecycle, phase timeouts, broker state, and orchestrator grace must also be accounted for.

**Error 16 — "`spring.lifecycle.timeout-per-shutdown-phase=40s` keeps the Pod alive for 40s."**  
No. The orchestrator can kill sooner per its own deadline.

**Error 17 — "Pod `readiness=false` automatically stops `@JmsListener`."**  
No. Readiness normally affects HTTP routing, not JMS polling.

**Error 18 — "Stopping a Topic subscriber cannot lose events if the producer uses `PERSISTENT`."**  
False for non-durable subscriptions while inactive.

**Error 19 — "`shutdown()` can be used to toggle a listener like `stop()`."**  
No. Shutdown is for end-of-lifecycle cleanup, not brief pausing.

**Error 20 — "Firing of the stop callback means all business side effects committed atomically."**  
No. Inspect actual transaction boundaries and data stores.

## 20. Pre-Production Lifecycle Policy Checklist

- [ ] Know the exact listener container class used: `DefaultMessageListenerContainer` or another type?
- [ ] Distinguished factory, registry, endpoint ID, and container instance?
- [ ] Have a stable `@JmsListener.id` to look up the right container?
- [ ] Know what `isActive` and `isRunning` represent, without treating them as broker health?
- [ ] If manual-start is needed, configured `setAutoStartup(false)` and an appropriate start workflow?
- [ ] Does stop need `stop(Runnable)` callback to verify drain?
- [ ] Protected against duplicate stops, early restarts, and overwritten callbacks?
- [ ] Monitoring in-flight handler counts and JMS commits/rollbacks?
- [ ] Verified whether default `acceptMessagesWhileStopping=false` fits broker retry policies?
- [ ] If set to `true`, tested accepting new messages and extended stopping phases?
- [ ] Receive timeout only governs polling; business I/O also has independent timeouts?
- [ ] Bounded worst-case handler execution and DB transaction duration?
- [ ] Listener session uses `sessionTransacted=true` or an appropriate transaction strategy?
- [ ] Verified `AUTO_ACK` behavior on DMLC instead of relying on illusory retries?
- [ ] Business idempotency handles redeliveries after crashes?
- [ ] Tested broker destination persistence, TTL, redelivery, and DLQ/quarantine?
- [ ] Clarified queue/topic/durable/shared subscriptions and offline event loss?
- [ ] Spring lifecycle phases and callback timeouts align with dependencies?
- [ ] Checked exact Spring Boot version and server shutdown behavior?
- [ ] Orchestrator termination grace exceeds worst-case lifecycle/handler duration?
- [ ] Readiness/HTTP drain and JMS consumer stop are coordinated separately?
- [ ] Rolling deploys only stop a subset of replicas while backlog exists?
- [ ] Authorized start/stop runbooks, audit logs, and timeouts/rollbacks in place?
- [ ] Metrics exist for broker queue depth, oldest age, consumer counts, retries, and DLQ?
- [ ] Tested stopping mid-handler, stopping right at receive, broker outages, and `SIGKILL`?
- [ ] Tested multi-replica setups without mistaking the local registry for cluster control?
- [ ] Never calling `shutdown()` to pause/resume registry-managed containers?
- [ ] Never equating callback completion with atomic business commits?

## 21. Self-Check Questions

**Question 1.** By what mechanism does `DefaultMessageListenerContainer` receive messages?

**Answer:** DMLC uses invoker tasks calling `MessageConsumer.receive()` to poll, invoke listeners, and manage JMS sessions/consumers; unlike `SimpleMessageListenerContainer`, which uses `setMessageListener`.

**Question 2.** How do `stop` and `shutdown` differ?

**Answer:** `stop` allows pausing/resuming an active container; `shutdown` is end-of-lifecycle cleanup/close and should not be treated as a pause operation for normal restarting.

**Question 3.** A message entered the handler before `stop()`. Is it guaranteed to cancel immediately?

**Answer:** No. The handler may finish or fail/roll back depending on state, container, provider, and process deadlines.

**Question 4.** How do you get notified when listener processing has actually stopped in DMLC?

**Answer:** Use `stop(Runnable callback)`; the callback fires after processing stops. Account for timeouts and races from duplicate stops or early restarts.

**Question 5.** What is the default of `acceptMessagesWhileStopping`?

**Answer:** `false`, meaning the container attempts to reject messages received during the stopping phase. This can affect provider retry counts.

**Question 6.** Why can enabling `acceptMessagesWhileStopping(true)` prolong stopping?

**Answer:** It allows processing messages received during stopping, including newly published messages arriving before receive timeouts finish.

**Question 7.** Does `receiveTimeout=1000` kill a business method running longer than 1 second?

**Answer:** No. That is only the polling receive timeout; business methods need their own timeouts.

**Question 8.** What does `setSessionTransacted(true)` provide?

**Answer:** JMS receive is committed after listener success; failures/crashes can roll back/redeliver per JMS transaction/broker policy. It does not include the DB in the same local JMS transaction.

**Question 9.** Does `AUTO_ACKNOWLEDGE` on DMLC guarantee retries when the handler throws?

**Answer:** No. DMLC may ACK before listener execution, so do not rely on redelivery on exceptions.

**Question 10.** Wrote to DB then crashed before JMS commit. Can the message repeat?

**Answer:** Yes. The broker can redeliver uncommitted messages. Idempotent business effects are needed.

**Question 11.** What does `registry.getListenerContainer(id)` return if the ID does not exist?

**Answer:** `null`; check before calling `start`/`stop`.

**Question 12.** Does stopping a listener on Pod A stop Pod B?

**Answer:** No. Registry and container lifecycles live inside each `ApplicationContext`/JVM.

**Question 13.** Does stopping a non-durable Topic consumer automatically save events published while offline?

**Answer:** No. Non-durable subscriptions do not guarantee replaying messages published while inactive.

**Question 14.** Why can a durable topic retain backlog while the container is stopped?

**Answer:** The broker maintains the durable subscription identity and matched messages per retention/delivery policy, provided the subscription was properly created/configured.

**Question 15.** Does `isRunning()==true` prove the broker is delivering messages properly?

**Answer:** No. You need broker metrics, connection/recovery state, and business processing counters.

**Question 16.** What does `spring.lifecycle.timeout-per-shutdown-phase=40s` guarantee?

**Answer:** It is Spring's wait budget for phase-based lifecycle stop; it does not force the orchestrator to extend its grace period and does not guarantee handlers finish in 40s.

**Question 17.** Can you call `shutdown()` on a registry-managed container to pause and then `start()`?

**Answer:** You should not. `shutdown` closes resources/lifecycle; use `stop`/`start` to pause/resume.

**Question 18.** If `stop(callback)` is called twice in a row, do both callbacks fire?

**Answer:** Not guaranteed. DMLC may overwrite the old callback before processing stops; early `start` can also cancel the callback.

**Question 19.** On stop, queue depth climbs. Is that definitely a container bug?

**Answer:** No. Producers keep sending while consumers stop, so queue backlog grows normally per broker mechanics.

**Question 20.** Which metrics matter more than a single `isRunning` flag?

**Answer:** In-flight handlers, commits/rollbacks, broker active consumers, queue depth/oldest age, redeliveries, DLQ, throughput, and business event IDs.

**Question 21.** Why must `terminationGracePeriodSeconds` be considered in Kubernetes?

**Answer:** If the hard kill deadline is shorter than drain time and Spring lifecycle timeout, the process may be killed before callbacks/JMS commits finish.

**Question 22.** When producers keep publishing heavily, is enabling `acceptMessagesWhileStopping(true)` always better?

**Answer:** No. It can keep receiving/processing during the stopping phase, making drain deadlines hard to predict.

## Conclusion

`DefaultMessageListenerContainer`'s lifecycle must be understood across **three independent yet interacting layers**:

1. **Spring lifecycle:** `initialize/start/stop/shutdown`, `SmartLifecycle` phases, registry endpoint IDs, and stop callbacks.
2. **JMS delivery:** received/ready/in-flight, ACK/transactions, commit/rollback, redelivery, and queue/topic subscription behavior.
3. **Business execution:** handler I/O duration, DB transactions, side effects, idempotency, retries, and timeouts.

**`stop()` does not kill in-flight tasks; `shutdown()` is not a pause; `stop(Runnable)` tells you when processing stopped yet is not proof of exactly-once business completion.** Safe stopping requires bounded draining, local JMS transactions or proper XA coordination, broker retries/DLQ, business I/O timeouts, orchestrator grace periods, and idempotency.

### Official References to Cross-Check

1. [Spring Framework – DefaultMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/DefaultMessageListenerContainer.html): polling consumers, scaling, auto-recovery, stop callbacks, caching, and receive timeout.
2. [Spring Framework – AbstractJmsListeningContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractJmsListeningContainer.html): `initialize/start/stop/shutdown/destroy`, `isActive/isRunning`, `autoStartup/phase`.
3. [Spring Framework – AbstractMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractMessageListenerContainer.html): `acceptMessagesWhileStopping`, `AUTO_ACK`/`CLIENT_ACK`/transacted semantics, and exception handling.
4. [Spring Framework – AbstractPollingMessageListenerContainer Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/listener/AbstractPollingMessageListenerContainer.html): `receiveTimeout` and JMS polling lifecycle.
5. [Spring Framework – DefaultJmsListenerContainerFactory Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/DefaultJmsListenerContainerFactory.html): factory settings for DMLC.
6. [Spring Framework – JmsListenerEndpointRegistry Javadoc](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/jms/config/JmsListenerEndpointRegistry.html): managing annotated listener containers, `getListenerContainer`, and lifecycle.
7. [Spring Framework – Annotation-driven JMS Endpoints](https://docs.spring.io/spring-framework/reference/integration/jms/annotated.html): `@EnableJms`, `@JmsListener`, factory/registry.
8. [Spring Framework – Using Spring JMS](https://docs.spring.io/spring-framework/reference/integration/jms/using.html): `MessageListenerContainer`s, JMS acknowledgment, transactions, and recovery.
9. [Spring Boot – Graceful Shutdown](https://docs.spring.io/spring-boot/reference/web/graceful-shutdown.html): web server lifecycle, `spring.lifecycle.timeout-per-shutdown-phase`, and Boot versions.
10. [Jakarta Messaging 3.1 Specification](https://jakarta.ee/specifications/messaging/3.1/jakarta-messaging-spec-3.1.html): JMS Session transactions, acknowledgments, queue/topic semantics, durable/shared subscriptions.
