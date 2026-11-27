# Runbook for queue full, executor rejections, and error spikes

In a live Spring Integration system, three alerts often fire almost simultaneously:

- A <code>QueueChannel</code> reaches its capacity limit; producers slow down, time out, or block.
- A <code>ThreadPoolTaskExecutor</code> runs out of intake capacity, causing an <code>ExecutorChannel</code> to throw task-rejected errors.
- The rate of <code>ErrorMessage</code>s or exceptions spikes, triggering higher retries, redeliveries, DLQs, and latency.

These three signals can form **an amplifying feedback loop**: slow downstreams fill the queue; producers fall back to executors or retry more; the executor saturates; failed retries push the error spike higher. If operators merely raise capacity, enable unbounded retries, or purge queues to "turn the dashboard green", the system can lose messages, duplicate side effects, or overload the database.

This lesson belongs to the **Operations** chapter of the **SPRING_INTEGRATION_RUNTIME** module, focusing on how Spring Integration executes and orchestrates flows across channels, endpoints, consumers, pollers, and executors. We build an on-call-ready runbook combining <code>IntegrationFlow</code> lifecycle, transactions, retries, message stores, error handling, correlation, threading, performance, and recovery testing.

> **Safety rule:** Never purge queues, disable error handlers, route errors to <code>nullChannel</code>, or falsely ACK unfinished messages just to make metrics look clean. Every load-shedding action must preserve processing contracts, retention, and replayability.

## 1. Runbook goals and responsibility boundaries

When an incident hits, the on-call engineer must quickly answer:

1. **Which component saturated first?** Input channel, poller, executor, database, broker, or downstream HTTP service?
2. **How far was the message accepted?** Entered queue, handed to worker, handler finished, DB committed, broker ACKed, or only returned <code>send() == true</code>?
3. **Which thread holds the failure?** Sender, executor worker, scheduled poller, or adapter callback?
4. **Are messages lost or duplicated?** Does the source support redelivery, and does the system have idempotency, a DLQ, and persistent stores?
5. **What is the minimal recovery action?** Throttle ingress, let consumers drain, fix dependency failures, scale resources with verification, or enter degraded mode.

This runbook assumes Spring Integration 6.x, Java 17+, and runtime observability. Choices around ACKs, rollbacks, pause/resume, and hot config changes **must be verified against your exact adapters and versions**. The runbook does not replace disaster recovery planning for databases or brokers.

### Concepts to distinguish

| Term | What actually happened | What must never be inferred |
|---|---|---|
| **Queue full** | A bounded buffer cannot accept more messages under current conditions | All handlers stopped or all messages were lost |
| **Executor reject** | The executor refused to accept a task per policy/capacity | The handler ran and threw a business error |
| **Error spike** | Count/rate of exceptions or <code>ErrorMessage</code>s jumped | Distinct business messages necessarily failed |
| **Backlog** | Messages queued waiting to be processed | Simply adding threads will process faster |
| **Slow consumer** | Completion throughput is lower than arrival rate | It is always caused by insufficient CPU |
| **Redelivery/retry** | One logical event may be retried multiple times | Each attempt represents a new business event |
| **Accepted** | One handoff step accepted the message/task | Committed/ACKed/entire flow completed |

## 2. 60-second decision tree

~~~mermaid
flowchart TD
    A["Alert: lag, rejection, or error rate rising"] --> B["Identify channel/endpoint + start time"]
    B --> C{"First signal?"}
    C -->|Queue at capacity| Q["Branch A: Queue full"]
    C -->|TaskRejectedException| X["Branch B: Executor reject"]
    C -->|onError / ErrorMessage rising| E["Branch C: Error spike"]
    C -->|Unclear| D["Check timeline of queue, executor, DB, broker, and deploys"]
    D --> C
    Q --> R["Safely throttle ingress + inspect consumer/poller"]
    X --> S["Isolate executor + reduce submission rate"]
    E --> T["Classify root cause + stop retry storm"]
    R --> V["Verify ACK/transaction, backlog drain, and SLO"]
    S --> V
    T --> V
    V --> W["Reopen ingress stepwise; watch for recurrence"]
~~~

**Branch selection rule:** Never chase only the highest-count alert. For example, rising <code>MessageDeliveryException</code> counts can simply be a **consequence** of a full queue. Reconstruct the timeline from when p95/p99 latency first climbed, queue depth began rising, executor active threads maxed out, and the first downstream failure appeared.

## 3. First 5-minute checklist: preserve evidence and limit blast radius

In the first few minutes, prioritize **assessing message integrity** before changing configuration.

| Order | Collect or execute | Reason |
|---|---|---|
| 1 | Record incident ID, start time, deployed version, service/instance/pod, affected tenant or partition | Align timelines |
| 2 | Identify channel bean ID, channel type, consumer endpoint ID, and <code>isRunning()</code> | Distinguish full queue from stopped endpoint |
| 3 | Snapshot queue depth/capacity, oldest-message age, ingress rate, and completion throughput | Calculate backlog growth rate |
| 4 | Snapshot executor core/max/pool/active/queue/rejected, scheduler, and thread dumps if blocked | Spot saturation or deadlocks |
| 5 | Snapshot error count/rate **by root category** and total attempts; read a few correlated stack traces | Avoid confusing retry amplification with failed request count |
| 6 | Verify whether source has broker ACK/redelivery, DB commits, or durable stores; pick pause/rate-limit policy | Avoid dropping messages while shedding load |
| 7 | Inspect dependencies: DB pool, HTTP 429/5xx, connection timeouts, broker lag, disk/heap/GC | Find bottlenecks outside the channel |
| 8 | Declare incident and assign owners per recovery track | Prevent multiple operators from editing capacity/pollers simultaneously |

If you do not yet know whether a message is durably persisted, **do not hastily destroy in-memory queues or mass-restart pods**. Confirm the source can replay and business idempotency works first.

### Three impact categories to classify

- **Data integrity:** is there risk of lost messages, duplicate side effects, or out-of-order DB writes?
- **Availability:** are requests timing out, producers blocking, consumers stopped, or retries looping infinitely?
- **Latency:** are queue lag, end-to-end SLA, and drain time still within budget?

Severity and alert thresholds must derive from product SLOs, not a generic industry number. For example, a queue at 80% means something only alongside growth rate, drain capacity, and time to full.

## 4. Branch A — QueueChannel full: accurate identification

<code>QueueChannel</code> is a <code>PollableChannel</code>: it holds messages until a consumer calls <code>receive()</code>. Creating <code>new QueueChannel(capacity)</code> bounds the buffer. Spring Integration documentation recommends setting explicit capacities rather than relying on effectively unbounded defaults in production.

For a bounded in-memory queue:

| Call | When space exists | When queue is full |
|---|---|---|
| <code>send(message)</code> | Typically enqueues message and returns | May **block waiting for space**; check caller/gateway timeouts |
| <code>send(message, 0)</code> | Returns <code>true</code> immediately | Returns <code>false</code> immediately without waiting |
| <code>send(message, timeoutMillis)</code> | Accepts message if space exists or frees before deadline | Returns <code>false</code> when timeout expires |
| <code>receive(0)</code> | Pulls message immediately if present | Returns <code>null</code> if queue is empty |
| <code>receive(timeoutMillis)</code> | Pulls message or waits until deadline | Returns <code>null</code> if none arrives before deadline |

**Queue full is not "Dispatcher has no subscribers".** It needs no direct subscriber; consumption usually happens via a <code>PollingConsumer</code>. Checking subscriber counts and subscribing a handler directly misdiagnoses the channel type.

### Signals confirming queue full

~~~text
queue_size ≈ queue_capacity
  + enqueue rate > successful dequeue rate
  + send latency or send timeouts rising
  + oldest-message age climbing
~~~

Verify metrics match your implementation: an in-memory <code>QueueChannel</code> exposes <code>getQueueSize()</code>; a queue backed by <code>JdbcChannelMessageStore</code> has different semantics and size/metric queries. Never treat queue depth metrics as proof of DB transaction or consumer success.

### Queue-full diagnostic procedure

1. **Locate the real queue.** Check bean type, capacity, queued message count, and instance count. Separate pods may own **separate** queues, leaving one pod full while siblings are empty.
2. **Confirm consumers are started.** For <code>PollingConsumer</code>, check <code>isRunning()</code>, trigger, <code>maxMessagesPerPoll</code>, <code>receiveTimeout</code>, task scheduler, and startup errors.
3. **Measure completion rate.** A poller can dequeue rapidly while downstream fails repeatedly; dequeue throughput is not success throughput.
4. **Find downstream limits.** DB connection pools, locks, HTTP timeouts, CPU, disk, GC, remote rate limits, slow queries, and retry advice.
5. **Assess the source.** Is input a temporary burst or is the producer sustaining rates above processing capacity? Did ACKs occur before entering an in-memory queue?
6. **Apply load shedding.** Pause/rate-limit inbound adapters per source capabilities, keeping messages in durable brokers where available; never drop into <code>nullChannel</code>.
7. **Restore consumption.** Fix the root cause, restart endpoints only if unintended/maintenance ended, or scale consumers safely per key/partition.

### Priority actions and safety conditions

| Action | When helpful | Risks to weigh |
|---|---|---|
| Throttle/rate-limit producers | Enqueue exceeds processing capacity | Sources without pause may need NACK/DLQ or other backpressure |
| Restart **unintentionally stopped** polling endpoint | Queue holds messages, consumer <code>isRunning=false</code> | Do not start during maintenance, tenant DELETING, or unready schema |
| Tune <code>maxMessagesPerPoll</code>/trigger | Poller underutilizes resources and downstream has headroom | Polling too aggressively can exhaust DB pools or hold locks/transactions long |
| Scale consumers/partitions | Independent messages and downstream can handle load | Ordering, correlation groups, duplicates, and lock contention |
| Raise queue capacity carefully | Brief bursts when long-term throughput suffices | Only delays heap/storage exhaustion; does not fix bottlenecks |
| Use persistent store/broker | Need downtime/restart survival and replay | Must design transactions/serializers/retention; does not automatically provide exactly-once |
| Purge queue or skip messages | Only when business policy permits with explicit audit/quarantine | Risks permanent data loss |

## 5. Configuring a bounded queue and bounded poller

Java 17+, Spring Integration 6.x example: a flow pulls orders from <code>orders.backlog</code>, polls up to 10 messages per cycle, and invokes a synchronous service.

**Illustrative payload and business service:**

~~~java
public record OrderCommand(String eventId, String orderId, int quantity) {}

@Service
public class OrderService {
    @Transactional
    public void process(OrderCommand command) {
        if (command.quantity() <= 0) {
            throw new IllegalArgumentException("Quantity must be positive");
        }
        // Validate and update database idempotently by eventId.
        // Transaction wraps only operations compatible with the current manager.
    }
}
~~~

**Channel and polling consumer:**

~~~java
@Configuration
@EnableIntegration
public class BacklogFlowConfig {
    @Bean(name = "orders.backlog")
    QueueChannel ordersBacklog() {
        return new QueueChannel(128);
    }

    @Bean
    IntegrationFlow orderWorkerFlow(OrderService orderService) {
        return IntegrationFlow.from("orders.backlog")
            .handle(orderService, "process", endpoint -> endpoint
                .id("orders.worker")
                .poller(Pollers.fixedDelay(200)
                    .maxMessagesPerPoll(10)
                    .receiveTimeout(0)))
            .get();
    }
}
~~~

<code>OrderService.process(...)</code> is an application-defined business service responsible for validation, transactions, and idempotency. Key APIs: <code>org.springframework.integration.dsl.IntegrationFlow</code>, <code>org.springframework.integration.dsl.Pollers</code>, <code>org.springframework.integration.channel.QueueChannel</code>, <code>org.springframework.integration.config.EnableIntegration</code>.

**Note:** <code>fixedDelay(200)</code> is the delay in milliseconds **after the poll task finishes**; <code>maxMessagesPerPoll(10)</code> caps receive calls per cycle. It is not a guarantee of 10 messages per 200 ms, as handlers may be slow, receives may return empty, or the scheduler may lack workers.

Per Spring Integration documentation, <code>PollingConsumer</code> without an explicit <code>maxMessagesPerPoll</code> defaults to <code>-1</code> (draining until empty), unlike <code>SourcePollingChannelAdapter</code> which defaults to <code>1</code>. Know your endpoint type before tuning. On a continuously fed queue, unbounded polling can hog the scheduler; a finite positive value usually makes fairness and shutdown easier to control.

### Senders must never ignore send outcomes

~~~java
public void submit(PollableChannel backlog, OrderCommand command) {
    Message<OrderCommand> message = MessageBuilder
        .withPayload(command)
        .setHeader("businessEventId", command.eventId())
        .build();

    boolean accepted = backlog.send(message, 500);
    if (!accepted) {
        throw new IllegalStateException("Order backlog full within 500 ms");
    }
}
~~~

This assumes <code>OrderCommand.eventId()</code> is an application-defined business key. On timeout, the **external caller path** must return HTTP 429/503, NACK/requeue, or record a durable retry per contract. Throwing an exception does not guarantee source redelivery if upstream already ACKed.

Never raise timeouts indefinitely on synchronous APIs; doing so piles up blocked request threads and triggers secondary ingress outages.

## 6. Branch B — Executor reject: how does it differ from queue full?

<code>ExecutorChannel</code> calls a <code>TaskExecutor</code> to run subscribers. With a bounded <code>ThreadPoolTaskExecutor</code>, task intake follows:

1. Is a thread below <code>corePoolSize</code> available?
2. If core threads are busy, does the task queue have space?
3. If the task queue is full, can threads expand up to <code>maxPoolSize</code>?
4. If everything is saturated, the **rejection policy** decides whether to throw, run on caller, or drop tasks.

~~~mermaid
flowchart TD
    A["ExecutorChannel submits task"] --> B{"Threads < corePoolSize?"}
    B -->|Yes| C["Worker executes task"]
    B -->|No| D{"Executor queue has space?"}
    D -->|Yes| E["Enqueue task in executor queue"]
    D -->|No| F{"Pool < maxPoolSize?"}
    F -->|Yes| C
    F -->|No| G["RejectionHandler"]
    G --> H["Abort / CallerRuns / Discard / DiscardOldest"]
~~~

**Never confuse the executor queue with a <code>QueueChannel</code>.** The executor queue holds unstarted <code>Runnable</code> tasks, whereas <code>QueueChannel</code> holds <code>Message</code>s waiting for a polling consumer. They differ in capacity, retries, and persistence semantics.

### Identifying exceptions and failure scope

Spring's <code>ThreadPoolTaskExecutor</code> can throw <code>TaskRejectedException</code> when refusing tasks under the default <code>AbortPolicy</code>. Spring Integration's dispatcher may wrap this in a <code>MessagingException</code>/<code>MessageDeliveryException</code> depending on call path and version.

**Cases to separate:**

| Signal | Correct interpretation |
|---|---|
| <code>TaskRejectedException</code> directly inside <code>send()</code> | Task **was never accepted by executor**; caller/adapter must handle failure |
| <code>send()</code> succeeds, handler throws later | Task was accepted; failure happens on **worker**, outside sender's call stack |
| <code>CallerRunsPolicy</code> active | Sender **may execute the handler itself**; latency and transaction/thread boundaries shift |
| <code>DiscardPolicy</code> or <code>DiscardOldestPolicy</code> | Can drop tasks silently without failing like AbortPolicy | Unsuitable for mandatory business messages without separate preservation |
| Executor already shut down | New tasks reject even with low active/queue counts | Inspect lifecycle and deploy/shutdown timelines |

### Deliberately configuring a bounded executor

~~~java
@Configuration
public class WorkerPoolConfig {
    @Bean(name = "ordersWorkerPool")
    ThreadPoolTaskExecutor ordersWorkerPool() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(64);
        executor.setThreadNamePrefix("orders-");
        executor.setRejectedExecutionHandler(
            new ThreadPoolExecutor.AbortPolicy());
        return executor; // Spring manages bean initialization/shutdown.
    }

    @Bean(name = "orders.executor")
    ExecutorChannel ordersExecutor(
            @Qualifier("ordersWorkerPool") ThreadPoolTaskExecutor pool) {
        return new ExecutorChannel(pool);
    }
}
~~~

Types belong to <code>org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor</code>, <code>org.springframework.integration.channel.ExecutorChannel</code>, <code>java.util.concurrent.ThreadPoolExecutor</code>, and <code>org.springframework.beans.factory.annotation.Qualifier</code>. In a real application, attach a consumer endpoint to <code>orders.executor</code>; declaring the channel alone creates **no** subscriber.

This example is an **alternative topology** to the queue + poller in section 5—do not share input names in a way that accidentally processes one message twice.

### Pool snapshot on rejection

~~~java
@Component
public class ExecutorSnapshot {
    private final ThreadPoolTaskExecutor pool;

    public ExecutorSnapshot(
            @Qualifier("ordersWorkerPool") ThreadPoolTaskExecutor pool) {
        this.pool = pool;
    }

    public void logSnapshot() {
        ThreadPoolExecutor delegate = pool.getThreadPoolExecutor();
        log.warn("poolSize={}, active={}, queued={}, remaining={}, " +
                 "completed={}, shutdown={}",
            pool.getPoolSize(),
            pool.getActiveCount(),
            delegate.getQueue().size(),
            delegate.getQueue().remainingCapacity(),
            delegate.getCompletedTaskCount(),
            delegate.isShutdown());
    }
}
~~~

In production, expose the same stats via Micrometer/Actuator or equivalent instrumentation; avoid logging multiple times per second if errors already cause log storms. <code>getThreadPoolExecutor()</code> is valid only after bean initialization; snapshots describe only the instant read, not a promise that the next task will be accepted.

## 7. Executor reject runbook: actions in the field

### Step 1 — Distinguish saturation from shutdown rejections

When <code>TaskRejectedException</code> occurs, capture:

~~~text
executorBeanName, poolSize, corePoolSize, maxPoolSize
activeCount, queueSize, queueRemainingCapacity
isShutdown, isTerminating
channelBeanName, endpointId, threadName
messageId, correlationId, businessEventId
rejectionPolicy, firstSeenAt, requestRate
~~~

If <code>isShutdown=true</code> while producers still send to <code>ExecutorChannel</code>, lifecycle ordering or dynamic flow removal is the likely culprit. If active is at max, queue is full, and downstream latency is rising, it is saturation. If active is low yet tasks reject, inspect custom <code>RejectedExecutionHandler</code>s, executor proxies, shutdown state, or external caps.

### Step 2 — Reduce task submission while preserving recovery

Prefer throttling ingress right at **paths supporting backpressure**:

- HTTP ingress: set timeouts/rate limits, return 429/503 for work **not yet durably persisted**, and include retry hints when the contract permits.
- JMS/Kafka/AMQP: pause consumers, tune concurrency, or nack/requeue per adapter; **never ACK before tasks have guaranteed persistence/completion**.
- Scheduler/poller: slow polling, cap <code>maxMessagesPerPoll</code>, or stop the right adapter orderly; inspect active work.
- Internal producers: use bounded queues/persistent outboxes and backoff retries instead of tight retry loops.

If the producer itself runs on the saturated executor, check for deadlock cycles or thread starvation: a worker blocking on a future it just submitted to **the same full pool** can self-deadlock.

### Step 3 — Find handlers holding threads too long

Inspect thread dumps during saturation and classify:

| What is the worker doing? | Where to investigate |
|---|---|
| JDBC query / waiting on connection pool | Slow queries, pool size, lock-holding transactions, DB saturation |
| Sync HTTP client / TLS / DNS | Timeouts, circuit breakers, remote 429/5xx, connection pooling |
| <code>LockRegistry.obtain()</code> / <code>lock()</code> | Hot business keys, distributed leases, deadlocks, lock hold times |
| <code>Thread.sleep()</code> in retry backoff | Retry advice, excessive backoff, attempt counts |
| Waiting on future of a task in the same pool | Thread starvation/deadlock from nested submissions |
| GC or CPU-bound compute | CPU quotas, GC pauses, payload conversion, encryption, parse/serialize |

Never add threads before understanding the bottleneck: 16 threads contending on 8 JDBC connections do not speed up the DB and can double queue waits or timeouts.

### Step 4 — Choose the rejection policy carefully

| Policy | Behavior when pool/queue full | Recommendation for critical messages |
|---|---|---|
| <code>AbortPolicy</code> | Throws rejection; sender knows task was refused | Sound when upstream has a failure contract, bounded retries, and idempotency |
| <code>CallerRunsPolicy</code> | Sender executes task itself in some cases | Can create backpressure, yet **unexpectedly changes thread/transaction/latency** semantics |
| <code>DiscardPolicy</code> | Silently drops tasks | Do not use for mandatory business messages |
| <code>DiscardOldestPolicy</code> | Drops oldest queued task | Risks message loss/reordering; very hard to guarantee delivery |
| Custom reject handler | Application-defined, e.g., publish retry or persist | Must prove idempotency, failure handling, and no infinite loops |

**CallerRuns trap:** If <code>ExecutorChannel</code> executes the handler on the sender thread during overload, the sender's thread-bound transaction may wrap the handler **only for some requests**, while under normal load handlers run on worker threads. That unpredictable semantic shift makes CallerRuns unsuitable for "guaranteeing a shared transaction".

### Step 5 — Recover and reopen ingress in stages

1. Fix the underlying dependency or misconfiguration causing blocks/rejections.
2. Confirm completion throughput climbs steadily, task queues shrink, and no thread deadlocks remain.
3. Verify failed messages reached proper retry/DLQ/quarantine paths or will redeliver from source.
4. Reopen ingress incrementally, watching active/queued/rejected counts and p99, rather than snapping straight to 100%.
5. Once error rate and lag return within budget, close the incident while retaining failed-message records for reconciliation.

## 8. Branch C — Error spike: count errors at the right boundary

An **error spike** is a sharp jump in **error rate or frequency**, not the name of a single exception. Symptoms may include:

~~~text
integration handler error count rising
errorChannel receiving many ErrorMessages
HTTP/JDBC timeouts rising
broker redeliveries/retries rising
DLQ ingress rising
executor rejections rising
~~~

One failing source event can spawn many log lines, retry attempts, and <code>ErrorMessage</code>s. For example, 100 failed logical events × 4 attempts = 400 handler failures; if each failure logs at two layers, that yields 800 log lines. Maintain a metric **by business event ID** or logical work unit alongside attempt counts so severity is not misread.

### Sync, async, and poller errors travel different paths

| Boundary | Where errors surface | How to inspect |
|---|---|---|
| <code>DirectChannel</code> → handler | Directly on sender thread; exception unwinds call stack | Gateway/caller logs and cause chains |
| <code>ExecutorChannel</code> → handler | On worker after <code>send()</code> accepted the task | Executor error handling, <code>ErrorMessage</code>, and worker logs |
| <code>QueueChannel</code> → polling consumer | On poller/scheduler thread | Poller error channel, <code>MessagePublishingErrorHandler</code>, transaction rollback |
| <code>SourcePollingChannelAdapter</code> | On scheduled poll task when receive/dispatch fails | Source/adapter logs, error channel, receive and send semantics |
| Reactive endpoint | <code>onError</code> signal in subscription | Subscriber, <code>onErrorResume</code>/<code>retryWhen</code>, context propagation |
| Broker inbound adapter | Callback/listener thread or downstream worker | Adapter-specific ACK/requeue, retry topic/DLQ, and offsets |

In Spring Integration, async error handling typically wraps exceptions into an <code>ErrorMessage</code> sent to the message header's <code>errorChannel</code> or global channel. Scheduled pollers normally use <code>MessagePublishingErrorHandler</code>; when configuring a custom <code>TaskScheduler</code>, verify the error handler policy is wired appropriately.

**Never claim every exception automatically reaches the global errorChannel.** Exceptions thrown in synchronous handlers behind a <code>DirectChannel</code> normally unwind straight to the caller. An <code>ExecutorChannel</code> with a custom executor/error handler, a broker adapter, or a reactive subscription can have its own error boundaries.

### Root causes of error spikes

| Category | Typical signs | Verification |
|---|---|---|
| Dependency outage | Connection refused, HTTP 503, socket timeout | Health/latency of DB, broker, and remote APIs |
| Rate limiting | HTTP 429, quota exceeded | Remote quotas, retry-after headers, current concurrency |
| Poison messages | Same payload or business ID failing repeatedly | Root cause, deserialization/conversion, DLQ records |
| Schema/version drift | ClassCastException, JSON mapping, missing SQL column | Deploy timestamps, serializers, and migrations |
| Thread/queue saturation | <code>TaskRejectedException</code>, send timeouts | Executor queues and handler latency |
| Locks/transactions | Deadlocks, lock wait timeouts, rollback-only | DB locks, transaction logs, retries |
| Lifecycle/wiring | <code>Dispatcher has no subscribers</code>, missing bean | Endpoint IDs, <code>isRunning()</code>, dynamic flows |
| Broken error flow | Secondary errors publishing <code>ErrorMessage</code> | Original exception and nested exceptions |

### Error-spike diagnostic workflow

1. Capture error rates by **endpoint, grouped exception class, result, and time**, keeping total logical attempts/events as the denominator.
2. Identify the **earliest exception on the timeline**, not the last stack trace emitted by a recoverer.
3. Correlate the start time against deploys, config changes, cert/secret rotations, DB migrations, traffic surges, or infra faults.
4. Check whether retries are amplifying load on an already-failing dependency.
5. For poison messages, determine whether to **quarantine** instead of retrying endlessly.
6. For transient failures, enforce bounded retries + exponential backoff + jitter/circuit breakers to avoid synchronized retry storms.
7. Confirm the error flow still has subscribers and log/error sinks have not become a new bottleneck.
8. Reconcile DB state, broker ACK/offsets, outbox, and idempotency before replaying.

### Breaking the retry-storm feedback loop

~~~mermaid
flowchart LR
    A["Downstream returns errors"] --> B["Aggressive retries"]
    B --> C["Pool / queue saturates"]
    C --> D["Timeouts / rejections"]
    D --> E["ErrorMessages and redeliveries spike"]
    E --> B
    F["Bounded attempts + backoff + quarantine"] -. "breaks loop" .-> B
~~~

Suppose a dependency handled 100 requests/s before an incident; if every request immediately retries 3 extra times, generated load can jump to **400 attempts/s** in short bursts. This is an illustrative example; real distribution depends on timeouts, concurrency, backoff, and success/failure mix. Measure **attempt load**, not inbound business events alone.

## 9. Designing a safe observability error flow

The default global <code>errorChannel</code> is a <code>PublishSubscribeChannel</code> with a framework-provided error-logging subscriber. Since Spring Integration 5.4.3, the default global error channel requires at least one subscriber to prevent silently dropping errors. During shutdown, an <code>ErrorMessage</code> emitted after subscribers stop can trigger a **secondary <code>MessageDispatchingException</code>**.

A custom observation consumer:

~~~java
@Component
public class OperationalErrorObserver {
    private final MeterRegistry meters;

    public OperationalErrorObserver(MeterRegistry meters) {
        this.meters = meters;
    }

    @ServiceActivator(inputChannel = "errorChannel")
    public void observe(ErrorMessage error) {
        Throwable cause = error.getPayload();
        String kind = classify(cause); // small label set, never raw exception text

        meters.counter("integration.operation.errors",
            "kind", kind).increment();
    }

    private String classify(Throwable exception) {
        Throwable current = exception;
        while (current.getCause() != null && current.getCause() != current) {
            current = current.getCause();
        }
        if (current instanceof java.util.concurrent.RejectedExecutionException
                || current instanceof org.springframework.core.task.TaskRejectedException) {
            return "executor_rejected";
        }
        if (current instanceof java.net.SocketTimeoutException) {
            return "dependency_timeout";
        }
        if (current instanceof IllegalArgumentException) {
            return "invalid_message";
        }
        return "other";
    }
}
~~~

Key types: <code>org.springframework.integration.annotation.ServiceActivator</code>, <code>org.springframework.messaging.support.ErrorMessage</code>, <code>io.micrometer.core.instrument.MeterRegistry</code>. The <code>classify</code> function merely illustrates **root-cause grouping** and does not replace a production classification policy.

**Business warning:** A subscriber on <code>errorChannel</code> only proves the <code>ErrorMessage</code> was observed. Returning normally from the method **does not mean** the input message was rolled back, requeued, properly ACKed, or recovered in business terms. On some error/recovery paths, swallowing an exception tells callers/advice the error was handled. Retries or DLQs must be explicitly configured and tested per adapter.

Never put <code>cause.getMessage()</code>, tenant IDs, or business event IDs into default meter tags: unbounded values explode cardinality. When investigating specific messages, keep correlation and failed-message metadata inside access-controlled logs/traces or a suitable DLQ.

## 10. Three coupled incidents: finding the first bottleneck

A realistic flow might look like:

~~~text
Broker inbound
   → orders.backlog (bounded QueueChannel)
   → PollingConsumer
   → orders.executor (ExecutorChannel)
   → validation / JDBC / HTTP handler
   → outbound adapter
                 └→ errorChannel or DLQ on failure
~~~

When the HTTP handler slows down abnormally:

~~~mermaid
sequenceDiagram
    participant B as Broker producer
    participant Q as QueueChannel
    participant P as PollingConsumer
    participant X as ExecutorChannel
    participant D as Downstream HTTP/DB
    B->>Q: enqueue M1..Mn
    Q->>P: poll message
    P->>X: submit handler task
    X->>D: slow request
    Note over X,D: Active workers climb, executor queue fills
    P->>X: submit new task
    X--xP: reject
    Note over P,Q: Poller errors, retries/redeliveries may climb
    B->>Q: keeps enqueuing
    Note over B,Q: QueueChannel hits capacity, sends slow/fail
~~~

In this chain, merely raising <code>QueueChannel</code> capacity **cannot fix** a slow HTTP downstream. Merely adding executor threads can crash the HTTP service or DB faster. Merely increasing retry attempts generates even more requests and failures.

### Rules for identifying the origin

| Earliest signal on timeline | High likelihood | Priority action |
|---|---|---|
| DB/HTTP latency rises, then executor active rises | Slow downstream is root cause | Cap concurrency/rate, fix dependency |
| Executor <code>shutdown=true</code> right after deploy | Lifecycle ordering/config | Verify flow registrations and shutdown/restart policy |
| Queue depth grows, poller <code>isRunning=false</code> | Consumer stopped or never started | Inspect startup/error state; start safely |
| Queue depth grows, poller runs yet completions low | Slow handler/retries/DB locks | Measure success throughput and capture thread dumps |
| Error spike starts right after schema change | Incompatible payload/DB | Roll back deploy or apply safe compatibility fix |
| Error spike hits one single event ID repeatedly | Poison message and retry loop | Isolate event, route to DLQ/quarantine, stop infinite replay |
| Only one tenant/key causes queue lag | Hot partition, lock contention | Analyze business keys, partition or throttle per key |

## 11. Calculating backlog, headroom, and drain time

You cannot size capacity solely from "the queue is at 90%". You need ingress rate, **successful completion** throughput, and maximum allowed wait time.

Notation:

- <code>λ</code>: new messages/second arriving at the queue.
- <code>μ</code>: messages/second completed per contract.
- <code>B</code>: current backlog message count.
- <code>C</code>: queue capacity.

When <code>λ > μ</code> long enough:

\[
\frac{dB}{dt} \approx \lambda - \mu
\]

If rates stay steady and <code>B &lt; C</code>, theoretical time until full:

\[
t_{\mathrm{full}} \approx \frac{C-B}{\lambda-\mu}
\]

Once ingress drops below throughput (<code>μ > λ</code>), theoretical drain time:

\[
t_{\mathrm{drain}} \approx \frac{B}{\mu-\lambda}
\]

**Illustrative example:** queue capacity 10,000, currently 4,000 messages; ingress 600 msg/s, completions 450 msg/s. Backlog grows at ~150 msg/s; at constant rates, the remaining 6,000 slots equal **roughly 40 seconds** before full. Cutting ingress to 300 msg/s while keeping completions at 450 msg/s yields a drain time for 4,000 messages of **roughly 27 seconds**.

This is an approximation, **not a guaranteed ETA**: traffic is bursty, retries inflate <code>λ</code>, transaction rollbacks reduce <code>μ</code>, fan-outs multiply tasks, and chained queues carry separate backlogs.

### Using Little's Law to reason about queue latency

In a steady system, average messages waiting/processing <code>L</code> relate to throughput <code>λ</code> and residence time <code>W</code>:

\[
L = \lambda W
\]

At 500 msg/s throughput with 5,000 messages residing in a flow segment, average residence time in that segment is roughly 10 seconds under steady state. Never apply the formula mechanically while queues grow continuously or during retry storms.

**Real SLOs require watching p95/p99 and oldest age**, not averages alone. A key-prioritized queue or poison message can stall a subset of events for a long time even when average throughput looks healthy.

## 12. Action matrix: safety first, speed second

| Action | Queue full | Executor reject | Error spike | Prerequisite before acting |
|---|---|---|---|---|
| Rate-limit ingress | Helpful | Helpful | Helpful if caused by load/retries | Proper feedback/backpressure/NACK path exists |
| Pause adapter | May be needed | May be needed | Needed during downstream outages | Know ACK/offset, poll schedule, and in-flight state |
| Increase consumer concurrency | Potentially | Potentially | Can **make it worse** | DB/broker headroom exists, ordering/keys safe |
| Increase bounded capacity | Short-term relief only | Only extends task intake | Rarely fixes root cause | Heap/storage sufficient, drain plan ready |
| Switch to <code>CallerRunsPolicy</code> | Indirect | May throttle | Can shift failure surface | Transaction/thread semantics evaluated |
| Temporarily trim retries | Reduces pressure | Reduces tasks | Helps during retry storms | Messages have durable recovery/DLQ |
| Restart stopped poller | Helps drain | Indirect | Helps if missing consumer caused errors | Stop was unintended and infra is ready |
| Quarantine poison events | Can shrink backlog | Can shrink failed tasks | Very helpful | Auditing, replay policy, no silent drops |
| Restart app | Risks losing in-memory queues | Frees stuck tasks yet loses in-flight | Does not fix dependencies | Persistence, redelivery, idempotency understood |
| Purge messages/queue | Not recommended | Does not fix root cause | Not recommended | Only per approved data-deletion policy |

**Every change needs explicit rollback criteria:** if cutting concurrency spikes message age, adjust back; if expanding the pool triggers more DB 429s/timeouts, revert and throttle ingress instead. Never change capacity, max threads, and retry policies simultaneously when you would be unable to tell which change helped.

## 13. Transactions, ACKs, retries, and message stores: non-negotiable details

### 13.1. What does a successful send mean?

~~~text
Channel.send() accepted
    ≠ MessageHandler completed
    ≠ JDBC transaction committed
    ≠ Broker message ACKed
    ≠ Outbound side effect done exactly once
~~~

With <code>QueueChannel</code>, accepted usually means the message entered the buffer. With <code>ExecutorChannel</code>, accepted may only mean the executor accepted the task. When handlers run on another thread, the sender's thread-bound JDBC transaction **does not transfer automatically** to the handler. Therefore "send true → ACK upstream" is only safe when the architecture enforces compatible durable persistence/recovery contracts.

### 13.2. Place retries at the right boundary

| Where retry happens | Which errors retry | Risk |
|---|---|---|
| Sender/adapter outside channel | Enqueue failure, no-subscriber, executor reject | Must avoid duplicate submissions when intake state is uncertain |
| <code>RequestHandlerRetryAdvice</code> around handler | Invocation failures of an invoked handler | Cannot catch rejections occurring **before the handler runs** |
| Poller advice / transaction rollback | Receive/handle within poller scope | Source redelivery semantics vary; verify store |
| Broker retry/redelivery | Unacked/NACKed messages per policy | May reprocess the same business event multiple times |
| Reactor <code>retryWhen</code> | Resubscribes upstream publisher | Can repeat partially emitted side effects |

Never enable unbounded retries for permanent validation/schema errors. For transient outages, use finite attempt limits, exponential backoff, jitter, and durable recovery channels as needed. If a transaction is already marked rollback-only, retrying inside that same transaction will not save the commit.

### 13.3. In-memory vs persistent queues across restarts

- <code>new QueueChannel(capacity)</code> uses an in-memory buffer by default; restarts/crashes lose messages remaining in the queue.
- <code>QueueChannel</code> can be backed by a persistent <code>MessageGroupStore</code>; <code>JdbcChannelMessageStore</code> is commonly used for durable queues. Actual commit/receive/rollback semantics depend on the store and transaction configuration.
- A message removed from the queue and executing inside a worker **does not automatically return to the queue** just because the executor shuts down; check source transactions, ACKs, and recovery.
- Delayers, aggregators/resequencers, and outboxes can keep state in **separate stores**; never wipe all tenant/queue rows with an arbitrary SQL statement.
- Broker redeliveries after restarts can duplicate side effects; unique constraints or business idempotency keys are critical safeguards.

**Before restarting during a queue-full incident**, ask: *Where does uncommitted data live? What can the node recover on its own? Did the broker already ACK? Can we drain or quarantine before restarting?*

## 14. Lifecycle, shutdown, and dynamic flows on call

When an endpoint is calling <code>stop()</code> or a dynamic <code>IntegrationFlow</code> is being removed, producers can hit a channel with no remaining subscribers. When an executor shuts down, new tasks reject even if queues just drained. Verify:

1. Is the endpoint bean still in the context? What does <code>SmartLifecycle.isRunning()</code> return?
2. Does the poller/adapter have <code>autoStartup=false</code> due to maintenance or tenant DELETING?
3. Does <code>IntegrationFlowContext.getRegistrationById(flowId)</code> still return a registration?
4. Is a stop/remove command, rolling deploy, or resource lease revocation in progress?
5. Have in-flight tasks finished or moved to recovery?

**Never auto-restart** a deleted tenant's flow merely because subscriber count hit 0. Proper cleanup blocks new intake, drains pending items, stops/destroys the registration, and closes **tenant-specific** resources. Unchecked restarts can create duplicates or run with revoked credentials.

During rolling deploys, quiesce ingress first, drain or confirm durable replay, and only then stop consumers/executors in order. Never scale all replicas to zero simultaneously while unpersisted in-memory queues remain.

## 15. Dashboards and alerts needed before an incident

A runbook is hard to execute if your only alert is named "Integration Errors". A practical dashboard set:

| Group | Metrics or measurements needed | Purpose |
|---|---|---|
| Ingress | Logical events received/s, requests throttled/s | Know source rate and remaining pressure |
| Queue | Current depth, capacity, utilization, oldest age, send timeouts/s | Detect saturation before request timeouts |
| Poller | <code>isRunning</code>, poll cycles/s, receive count, receive errors, maxMessagesPerPoll | Separate stopped consumer from slow handler |
| Executor | Active, pool size, max, queue length/capacity, rejects/s, completed/s | Spot saturation and shutdown rejections |
| Handler | Success/s, error/s, p50/p95/p99 duration, attempt count | Measure completion throughput and latency |
| Error flow | <code>ErrorMessage</code>/s by **low-cardinality** kind, DLQ depth, recovery rate | Catch spikes and recovery status |
| Dependencies | DB pool active/wait, SQL latency, HTTP 429/5xx, broker lag | Pinpoint root cause |
| Data safety | Duplicate business IDs, uncommitted/requeued count, pending outbox | Reconcile lost/duplicate messages |

Spring Integration exposes channel/handler metrics via Micrometer/Observation when enabled. Exact meter names depend on version and instrumentation mode; some queues expose gauges like <code>spring.integration.channel.queue.size</code>, whereas executors usually rely on Micrometer binders/Spring Boot Actuator or custom instrumentation. **Do not assume every figure in the table appears automatically** simply by adding the Actuator dependency.

### Alerts more useful than static thresholds

**Illustrative conditions** (not universal defaults):

- Queue utilization climbs steadily *and* estimated <code>time_to_full</code> is smaller than the on-call response budget.
- Oldest-message age breaches the SLO, even if queue depth looks modest.
- Executor reject rate > 0 across consecutive windows while the system is **not** in an intentional shutdown.
- Error ratio rises above baseline *and* completion throughput drops.
- DLQ grows while replay/consumer capacity is low.
- Poller is not running while expected ACTIVE and the queue holds messages.

Alert on **business outcomes and integrity**, not raw volume alone. For instance, 10,000 repeated failures on one poison message differ fundamentally from 10,000 distinct business events failing.

## 16. Tests reproducing queue full and executor rejections

Runbooks need tests proving **rejection thresholds, exception paths, and recovery**. Tests using <code>Thread.sleep()</code> to "generate random pressure" flake easily; control timing deterministically with latches and finite timeouts.

### 16.1. Bounded QueueChannel rejects messages exactly when full

~~~java
@Test
void boundedQueueRejectsSecondMessageWithoutWaiting() {
    QueueChannel backlog = new QueueChannel(1);
    Message<String> first = MessageBuilder.withPayload("A").build();
    Message<String> second = MessageBuilder.withPayload("B").build();

    assertTrue(backlog.send(first, 0));
    assertEquals(1, backlog.getQueueSize());
    assertFalse(backlog.send(second, 0));

    assertEquals("A", backlog.receive(0).getPayload());
    assertEquals(0, backlog.getQueueSize());
    assertTrue(backlog.send(second, 0));
    assertEquals("B", backlog.receive(0).getPayload());
}
~~~

This test proves capacity and re-enqueue behavior **inside one JVM**. It proves nothing about transaction rollbacks, broker redelivery, or message persistence across restarts. For store-backed queues, write integration tests with a real database and matching transaction manager.

### 16.2. ExecutorChannel rejects when worker and task queue are full

~~~java
@Test
void executorRejectsWhenWorkerAndTaskQueueAreFull() throws Exception {
    ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
    pool.setCorePoolSize(1);
    pool.setMaxPoolSize(1);
    pool.setQueueCapacity(1);
    pool.setRejectedExecutionHandler(new ThreadPoolExecutor.AbortPolicy());
    pool.initialize(); // Unit test creates pool manually without a Spring container.

    CountDownLatch entered = new CountDownLatch(1);
    CountDownLatch release = new CountDownLatch(1);

    try {
        ExecutorChannel channel = new ExecutorChannel(pool);
        channel.subscribe(message -> {
            entered.countDown();
            try {
                if (!release.await(5, TimeUnit.SECONDS)) {
                    throw new IllegalStateException("Test latch timed out");
                }
            } catch (InterruptedException ex) {
                Thread.currentThread().interrupt();
                throw new IllegalStateException(ex);
            }
        });

        assertTrue(channel.send(
            MessageBuilder.withPayload("first").build()));
        assertTrue(entered.await(2, TimeUnit.SECONDS));
        assertTrue(channel.send(
            MessageBuilder.withPayload("queued").build()));

        assertEquals(1, pool.getThreadPoolExecutor().getQueue().size());
        assertThrows(RuntimeException.class, () -> channel.send(
            MessageBuilder.withPayload("rejected").build()));
    } finally {
        release.countDown();
        pool.shutdown();
    }
}
~~~

Key types: <code>ThreadPoolTaskExecutor</code>, <code>ExecutorChannel</code>, <code>CountDownLatch</code>, <code>TimeUnit</code>, <code>ThreadPoolExecutor</code>, <code>MessageBuilder</code>, and JUnit Jupiter assertions.

The test asserts <code>RuntimeException</code> to avoid coupling to one version's messaging wrapper. In real suites, unwrap causes to confirm <code>TaskRejectedException</code>/<code>RejectedExecutionException</code> matches the chosen executor, and assert rejected tasks **produce no side effects**.

If the test uses <code>CallerRunsPolicy</code>, it no longer rejects: the test thread itself may execute the handler and **block on the latch**. Write a dedicated test for that policy instead of reusing <code>AbortPolicy</code> expectations.

### 16.3. DirectChannel failures do not automatically go to errorChannel

~~~java
@Test
void directChannelFailureIsVisibleToCaller() {
    DirectChannel input = new DirectChannel();
    AtomicInteger attempts = new AtomicInteger();
    input.subscribe(message -> {
        attempts.incrementAndGet();
        throw new IllegalStateException("dependency unavailable");
    });

    Message<String> request =
        MessageBuilder.withPayload("event-42").build();

    assertThrows(MessagingException.class, () -> input.send(request));
    assertEquals(1, attempts.get()); // No retry advice in this test.
}
~~~

This test verifies synchronous exceptions. It has **no** asynchronous error publisher and cannot prove the global error channel received failures. When production runs with an executor or poller, test that exact topology and inspect the configured error sink.

### 16.4. Error-spike scenario with poller and recovery

Design an integration test with an input <code>QueueChannel</code>, polling consumer, controlled-failure handler, and dedicated error <code>QueueChannel</code> or in-memory sink:

1. Send a known business event ID into the test source.
2. Make the handler throw transient failures for the first N attempts, then succeed; enforce a **finite** retry policy.
3. Assert attempt count, <code>ErrorMessage</code> count per policy, failed message/correlation, and final outcome.
4. Force the handler to always fail; confirm the recoverer routes to DLQ/quarantine or exception rollback allows source redelivery.
5. Stop the poller mid-run and restart it; check in-flight messages, transactions, and replay per store type.
6. Repeat with a non-retryable validation error to prove poison events do not cause retry storms.

Use <code>@SpringIntegrationTest</code>, <code>MockIntegrationContext</code>, latches/Awaitility, or deadline-bounded conditional waits. Avoid long <code>Thread.sleep()</code> calls to simulate outages when fake downstreams can be controlled via latches, futures, or deadline-aware stubs.

## 17. Game Day drills before needing the real runbook

A system only truly has a runbook once it has been **exercised** in staging or a representative simulation environment.

| Drill | Controlled fault injection | Success criteria |
|---|---|---|
| Queue full | Small bounded queue, pause poller, ramp test producer | Alert fires, sender timeouts controlled, no false ACKs |
| Executor reject | Small core/max/queue, hold workers with latch | Rejections classified, ingress throttled, zero dropped events |
| DB/HTTP outage | Fake dependency timeout or 503 | Budgeted retries, no retry storm, error flow receives properly |
| Poison message | Undeserializable payload or validation failure | Quarantined/DLQed without blocking entire partition forever |
| Poller stop | Stop exact consumer endpoint | Queue lag climbs visibly, safe restart |
| Shutdown mid-backlog | Stop process with in-memory vs persistent queues per scenario | Clear view of lost vs replayed items and zero double side effects |
| Rolling deploy | Restart replicas sequentially while tasks are in-flight | No unintended no-subscriber errors, no bad ACKs |
| Hot correlation key | Many messages sharing one key/lock | Contention detected without breaking ordering or groups |
| Error sink loses subscriber | Disable observer/error consumer intentionally | Secondary failure detected; original exception trace not lost |

**Preserve evidence:** input IDs, event IDs, attempt counts, ACK outcomes, DB state, before/after metrics, and recovery duration. Never run drills by sending real messages to customers or corrupting production data without proper isolation and authorization.

## 18. On-call workflow by operational phase

Treat the phases below not as rigid SLAs, but as an immediately actionable **priority sequence**.

### Detection and preservation phase (T0)

1. Acknowledge the alert, open an incident record, and note deploy version and impact scope.
2. Identify which failure occurred first: queue full, executor rejected, or dependency/handler error.
3. Confirm whether messages sit in an in-memory queue, durable store, broker, or only an executor task queue.
4. Capture a few correlated traces/stack traces and thread/pool/queue snapshots without dumping secret payloads.
5. Decide whether to throttle ingress if message loss risk exists or requests already breach SLO.

### Mitigation phase

1. Assign owners for ingress throttling, dependencies, app flows, and data reconciliation.
2. Apply **one** lowest-risk mitigation: pause/throttle producers or isolate poison events based on evidence.
3. Break retry storms using backoff and attempt caps; confirm DLQ/quarantine works.
4. Restore handlers/pollers/dependencies after verifying transactions and ownership.
5. Watch completion throughput, queue age, reject rate, and error rate across consecutive windows.

### Recovery and reconciliation phase

1. Reopen ingress incrementally per measured headroom.
2. Recalculate drain time using observed throughput rather than configured limits alone.
3. Reconcile ACKs/offsets, DB rows, outbox/inbox, and unique business event IDs.
4. Check late messages, retried items, partial groups, and Delayer/aggregator schedules if used.
5. Close the incident only once SLOs stabilize, backlog stops growing, no unresolved loss/duplication risks remain, and recovery data has an owner.

### Shift-handoff evidence template

~~~text
INCIDENT_ID:
STARTED_AT / CURRENT_TIME:
DEPLOY_VERSION / PODS / TENANTS_AFFECTED:
PRIMARY_SYMPTOM: QUEUE_FULL | EXECUTOR_REJECT | ERROR_SPIKE
ROOT_CAUSE_CATEGORY:
CHANNEL_BEAN / ENDPOINT_ID / EXECUTOR_BEAN:
INGRESS_RATE / COMPLETED_RATE:
QUEUE_SIZE / CAPACITY / OLDEST_AGE:
EXECUTOR_ACTIVE / MAX / QUEUED / REJECTS:
ERROR_ATTEMPTS / UNIQUE_BUSINESS_EVENTS / DLQ_DEPTH:
ACK_AND_TRANSACTION_BEHAVIOR_VERIFIED:
MITIGATION_APPLIED / ROLLBACK_PLAN:
REPLAY_OR_RECONCILIATION_OWNER:
RECOVERY_CRITERIA:
NEXT_CHECK:
~~~

This template intentionally asks only for **essential operational data**, never pasting full payloads/message headers or secret credentials into tickets.

## 19. Anti-patterns to avoid

| Anti-pattern | Why it is dangerous | Better alternative |
|---|---|---|
| Raising queue capacity infinitely | Heap/storage fills later while the bottleneck stays | Bounded queues, admission control, drain plans |
| Raising executor maxPoolSize without checking queueCapacity | With a large un-full queue, pool may never grow past core | Understand ThreadPoolExecutor policy and downstream bottlenecks |
| Switching to <code>DiscardPolicy</code> to reduce rejections | Messages drop silently | Explicit failures, durable retry/DLQ, throttling |
| Enabling <code>CallerRunsPolicy</code> without testing | Blocks senders, shifts transaction/thread semantics | Load-test overload and document tradeoffs |
| Retrying continuously on downstream 503 | Amplifies outage and fills queues faster | Exponential backoff, jitter, circuit breakers |
| Purging queues or resetting offsets arbitrarily | Loses messages or creates duplicates | Reconcile + replay/idempotency policies |
| Stopping all consumers immediately on queue full | Backlog cannot drain | Throttle sources, let healthy consumers finish work |
| Restarting all pods with in-memory queues | Unpersisted messages are lost | Drain, durable handoff, or verify source redelivery |
| Swallowing exceptions in error flows to quiet logs | Upstream may think processing succeeded | Structured error routing and explicit recovery |
| Putting message IDs/order IDs in metric tags | Explodes cardinality and collector costs | Low-cardinality error categories; correlation in traces/logs |
| Monitoring only <code>send()</code> success | Misses handler failures after async handoffs | Completion/ACK/commit telemetry |

## 20. Production checklist: closing incidents and preventing recurrence

- [ ] Maintain a diagram of channel → poller/consumer → executor → handler → outbound/error flow using stable bean IDs.
- [ ] Queues have explicit capacities and senders have timeouts/failure policies; never block indefinitely unintentionally.
- [ ] Dashboards track queue depth **and oldest age**, completion throughput, executor saturation/rejections, and error ratios.
- [ ] Documented <code>PollingConsumer</code> vs <code>SourcePollingChannelAdapter</code>, <code>maxMessagesPerPoll</code>, triggers, and receive timeouts.
- [ ] Bounded executors have appropriate core/max/queue/rejection policies, and thread pools do not exceed downstream DB/HTTP limits.
- [ ] Distinguish sender errors from worker/poller errors; <code>errorChannel</code> and recoverers have clear owners.
- [ ] Every retry has finite limits, backoff/jitter, and a stop path for poison events.
- [ ] ACK/commit/redelivery verified for exact adapters and transaction managers rather than inferred from <code>send() == true</code>.
- [ ] Business events carry idempotency keys; DLQ/quarantine and replay have reconciliation procedures.
- [ ] Know exact message state on stop/restart and the difference between in-memory and persistent queues.
- [ ] Dynamic flow lifecycles/tenant deletions enforce admission gates and never restart unintentionally.
- [ ] Game-day tests cover queue full, executor rejections, error spikes, shutdown, and retry amplification.
- [ ] Post-incident closure requires stable throughput, drained backlog, falling errors/rejections, recovered SLOs, and no unowned data needing reconciliation.

**Conclusion:** In Spring Integration, **queue full** is a backpressure signal at message storage, **executor reject** is a task-intake failure in a worker pool, and an **error spike** reflects exceptions/attempts across distinct failure boundaries. A useful runbook does not merely "quiet alerts"—it finds the first bottleneck, protects ACK/transaction/idempotency invariants, sheds load safely, restores consumers, and reconciles data. Safe operations rely on **evidence of message completion**, not send counts or log volume.

## References

- [Spring Integration Reference — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html)
- [Spring Integration Reference — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html)
- [Spring Integration Reference — Message Endpoints and Pollers](https://docs.spring.io/spring-integration/reference/endpoint.html)
- [Spring Integration Reference — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html)
- [Spring Integration Reference — Transaction Support](https://docs.spring.io/spring-integration/reference/transactions.html)
- [Spring Integration Reference — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html)
- [Spring Integration 6.5 Javadoc — Pollers](https://docs.spring.io/spring-integration/docs/6.5.0/api/org/springframework/integration/dsl/Pollers.html)
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Integration Reference — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html)
