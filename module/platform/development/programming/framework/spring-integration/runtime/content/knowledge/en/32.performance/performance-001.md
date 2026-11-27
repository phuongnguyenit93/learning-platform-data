# Measuring send, queue wait, and handler execution time in Spring Integration runtime

## 1. Why is a single “message latency” number not enough?

In **SPRING_INTEGRATION_RUNTIME**, a message travels from a producer through a `MessageChannel`, endpoint, consumer, poller, or executor to a handler, message store, transaction, retry, and downstream system. When an operator says “processing a message takes 200 ms”, the first question must be: **200 ms measured from where to where?**

The three key milestones of the **Performance → Measuring send, queue wait, and handler execution time** chapter are:

- **Send duration:** how long does it take the caller to execute `MessageChannel.send(...)` and receive a result or exception?
- **Queue wait / scheduling delay:** how long does it take from when a message is accepted/placed into the queue until the consumer starts processing it?
- **Handler execution:** the execution time of the handler's processing code; this can measure the method body or the entire framework handler invocation depending on where the probe is placed.

A flow with `ExecutorChannel` may have a very fast `send()` while the worker queue waits for seconds. A `DirectChannel` has a slow `send()` because the handler runs **directly on the sending thread**. A `QueueChannel` has near-zero enqueue time when the queue has space, but the poller only picks up the message after a waiting interval.

**Do not sum the three measurements into end-to-end latency if the intervals overlap.** With `DirectChannel`, send duration usually **encompasses** handler execution. With `QueueChannel`, the time from `preSend` to the handler may include the time the sender was blocked due to a full queue, poller delay, and dispatch overhead — not purely the time “spent in the queue”.

~~~mermaid
flowchart LR
    P["Producer / gateway"] -->|"send()"| C["MessageChannel"]
    C -->|"admission / enqueue / submit"| Q["Queue or executor"]
    Q -->|"consumer ready"| E["Endpoint"]
    E --> H["Handler method"]
    H --> O["DB / HTTP / output"]
    P -.-> TS["T_send"]
    Q -.-> TW["T_wait"]
    H -.-> TH["T_handler"]
~~~

This article builds a clear timing model, shows how to instrument with `System.nanoTime()` and Micrometer, provides a runnable Java 17/Spring Boot example, and guides you through diagnosing contention, backlog, transactions, retries, threads, and correlation.

## 2. Precisely defining the measurement milestones

Define the event milestones:

| Milestone | Point in time | Measurement source |
| --- | --- | --- |
| `t0` | Immediately before the caller calls `send()` | Producer side |
| `t1` | `send()` returns a result or throws | Producer side |
| `ta` | Message is **actually accepted** into the queue/executor/broker | Admission/enqueue hook or defined acknowledgement |
| `td` | Message is dequeued or a worker picks up the task | Consumer/poller instrumentation |
| `th0` | Handler execution starts | Handler boundary |
| `th1` | Handler execution ends (success or failure) | Handler boundary |
| `tc` | Transaction commits, broker acks, or final business result is confirmed | Durable resource / adapter |

From the milestones above:

\[
T_{\text{send}} = t_1 - t_0
\]

\[
T_{\text{queue wait}} = t_d - t_a
\]

\[
T_{\text{handler}} = t_{h1} - t_{h0}
\]

\[
T_{\text{admission→handler}} = t_{h0} - t_a
\]

\[
T_{\text{end-to-end}} = t_c - t_{\text{ingress}}
\]

These are **logical definitions**; not all of them have a uniform callback point across every `MessageChannel` implementation.

### Queue wait is not equal to send time

Example of a `QueueChannel` with available capacity:

~~~text
t0: producer starts send()
t1: send() returns after 0.3 ms
... message sits in queue for 450 ms ...
td: poller receives message
th0: handler starts
th1: handler finishes after 12 ms
~~~

We might measure `T_send ≈ 0.3 ms`, `T_queue wait ≈ 450 ms`, and `T_handler ≈ 12 ms`. These are **illustrative hypothetical numbers**, not a framework benchmark. Looking only at the `send()` timer would lead to the false conclusion that the system is very fast while users still wait nearly half a second.

### Measure the handler body or the entire endpoint?

The two definitions can differ:

- **Handler method body:** the span right at the start/end of the business code you manage, which may not include validation, message conversion, advice, AOP, or sending a reply.
- **Integration handler invocation:** the span Spring Integration instruments on `AbstractMessageHandler` or an endpoint-level observation; may include wrappers and advice depending on implementation/version.
- **Business completion latency:** may extend to DB commit, HTTP response, or broker ack after the handler method returns.

When building dashboards, name timers to match their scope, for example `app.handler.body` separately from `spring.integration.handler` and `app.order.commit`.

## 3. The channel type determines what send() actually measures

| Channel / boundary | What does `send()` usually wait for? | Time after `send()` | When do people misinterpret it? |
| --- | --- | --- | --- |
| `DirectChannel` | Dispatcher invokes subscriber on the **same thread** | Handler may have already completed or thrown an exception before returning | Treating `T_send` as only enqueue cost |
| `ExecutorChannel` | Hands dispatch task to `TaskExecutor` | Worker may not have started yet, still pending in executor queue | Treating a successful `send()` as business success |
| `QueueChannel` with space | Stores message in queue | Message waits for `receive()`/poller | Treating enqueue latency as delivery latency |
| `QueueChannel` full | May **block** until space is available or timeout | If accepted, consumer may still run late | Measuring slow `send()` and blaming the handler |
| `PublishSubscribeChannel` sync | Usually dispatches to subscribers synchronously | May include time of multiple subscribers | Ignoring multi-subscriber/failover portions |
| Broker/network-backed channel | Depends on implementation and ack policy | Broker queue, consumer lag, redelivery | Treating producer acknowledgement as consumer commit |

According to Spring Integration documentation, `ExecutorChannel` breaks the call stack/thread context between sender and receiver; an exception in the handler may occur **after** the `send()` call has already returned. With `QueueChannel`, if the queue is not full, `send()` can return even if there is no consumer yet; if the queue is full, send may block.

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant C as ExecutorChannel
    participant X as TaskExecutor
    participant H as Handler
    P->>C: send(message)
    C->>X: submit dispatch task
    C-->>P: send() returns
    Note over P,H: T_send ends; handler may not have run yet
    X->>H: worker starts
    H->>H: business execution
    H-->>X: returns or throws
~~~

Do not use a single shared timer name to directly compare `DirectChannel` and `ExecutorChannel` without recording **channel type and send boundary**.

## 4. DirectChannel: send duration includes the handler

Example:

~~~java
MessageChannel channel = directChannel;
long started = System.nanoTime();

channel.send(MessageBuilder
        .withPayload("ORD-1")
        .build());

long sendNanos = System.nanoTime() - started;
~~~

If the subscriber performs a synchronous 250 ms HTTP call, `sendNanos` will be roughly 250 ms or more. This is not because “the channel sends slowly”, but because `DirectChannel` hands off the message via **direct invocation**.

Interval model:

~~~text
Producer thread:
t0 [send()
      dispatcher
      [handler body 10 ms]
      reply handling / downstream sync
   ] t1
~~~

`T_handler` lies **inside** `T_send`. Therefore, if `T_send=15 ms` and `T_handler=10 ms`, do not record end-to-end as 25 ms. The `15 - 10 = 5 ms` portion may be dispatcher/advice/conversion/downstream if the measured intervals align and there is no concurrent work, but subtraction is not a reliable metric by default.

### Do exceptions propagate back to the sender?

On `DirectChannel`, exceptions from the handler usually propagate back up the call stack unless intercepted by `RequestHandlerAdvice`, retry/recoverer, or an error handler. If measuring with:

~~~java
long start = System.nanoTime();
try {
    directChannel.send(message);
}
finally {
    long elapsed = System.nanoTime() - start;
    sendTimer.record(elapsed, TimeUnit.NANOSECONDS);
}
~~~

The `finally` block records duration **even on failure**, but the timer does not automatically carry a `success/failure` tag. If you want the dashboard to separate outcomes, select the timer by result/exception in `catch/finally` or use Spring Integration's existing metrics/observation conventions.

## 5. ExecutorChannel: separating handoff, executor queue wait, and handler

With `ExecutorChannel`, the producer submits the task and usually returns early. A worker executes the handler on an executor thread:

~~~text
sender:
  [MessageChannel.send() ----]                         (T_send)
                         |
                         v
executor:
  [pending task ...........................]            (queue wait)
                                       [dispatch]
worker:
                                          [handler body] (T_handler)
~~~

### Sources of increased wait time

- The worker pool has too few threads compared to the arrival rate.
- Handlers block on HTTP/JDBC, long timeouts, or retry/backoff on the worker.
- The executor queue is too large, so new work is not rejected but waits a very long time.
- Configuring `CallerRunsPolicy` can cause tasks to run **on the sender thread itself** when the pool is full, causing `T_send` to spike suddenly.
- Task executor threads exhaust another connection pool, leaving workers “active” without completing work.
- Thread scheduling/GC and lock contention.

A useful diagnostic question: **`send` is fast, but how late does the handler start?** When that gap grows alongside executor queue depth, the investigation usually points to worker/queue saturation rather than the channel serializer.

### Transactions do not automatically carry over to the worker

`ExecutorChannel` switches threads; imperative transaction contexts such as JDBC/JPA are typically bound to `ThreadLocal` and are not automatically propagated to the handler on the worker thread. A sender-side timer does not prove that the transaction in the handler has completed. You need to instrument the handler + commit boundary, and define separate error channels and retries.

## 6. QueueChannel and poller: queue wait depends on the polling schedule

`QueueChannel` is a pollable channel. With a polling consumer, a message is only processed when the poller calls `receive()` successfully:

~~~mermaid
sequenceDiagram
    participant P as Producer
    participant Q as QueueChannel
    participant S as Poller
    participant H as Handler
    P->>Q: send(M)
    Q-->>P: enqueued
    Note over Q: M waits in the queue
    S->>Q: receive(timeout)
    Q-->>S: M
    S->>H: handle(M)
    H-->>S: done/error
~~~

The wait time may include:

1. Dwell time in the queue;
2. Time until the next poll cycle (`fixedDelay`, `cron`, etc.);
3. Insufficient scheduler/poller resources;
4. The poller processing many previous messages (`maxMessagesPerPoll`);
5. Lock or transaction contention when receiving from a persistent message store.

Spring Integration lets you configure `maxMessagesPerPoll` and `receiveTimeout` for a polling endpoint. `receiveTimeout` is how long to wait **while receiving** when no message is available; it is not a maximum limit on how long a message is allowed to stay in the queue.

| Scenario | `T_send` | `T_queue wait` / enqueue to receive | `T_handler` |
| --- | --- | --- | --- |
| Queue empty, poller waiting for message | Can be small | Can be very small after enqueue | Depends on business work |
| Poller runs every 1 second | Can be small | Can be significant due to poll schedule | Can still be small |
| Queue has 10,000 messages backlog | Can be small if capacity remains | Can be very large | Not necessarily slow |
| Queue full | Can increase due to backpressure/blocking | Can increase | May be slow or not |
| Slow persistent JDBC store | Can increase due to serialization/store write | Can increase due to DB dequeue/lock | Can still be small |

**Do not infer from message timestamps that queue wait is `now - headers.timestamp`.** `MessageHeaders.TIMESTAMP` is generated when the message is created, not when it is enqueued; the message may have passed through several endpoints earlier.

## 7. What built-in measurements exist in Spring Integration?

### 7.1. Micrometer metrics (without observation)

Spring Integration provides metrics support when a `MeterRegistry` is present. In the Micrometer Integration section of the documentation:

- `spring.integration.send` with tag `type=channel` describes send processing time;
- `spring.integration.send` with tag `type=handler` describes handler processing time;
- `spring.integration.receive` with tag `type=channel` is for receive count on pollable channels;
- `spring.integration.channel.queue.size` and `spring.integration.channel.queue.remaining.capacity` are for `QueueChannel` when registered.

The exact meters depend on the version, whether the class supports management, and whether **ObservationRegistry** is used. Do not assume all of these names appear simultaneously in every application.

### 7.2. Micrometer Observation (Spring Integration 6.x+)

Since Spring Integration 6.0, `ObservationRegistry` can instrument channels, handlers, gateways, or inbound sources according to framework conventions. Current documentation highlights key observation timers:

| Observation name | Measured boundary | What is not included automatically |
| --- | --- | --- |
| `spring.integration.producer` | Instrumented channel `send()`/producer operation | Does not automatically measure queue wait time |
| `spring.integration.handler` | Instrumented handler invocation | Does not automatically prove DB commit |
| `spring.integration.gateway` | Gateway request/reply scope | Does not automatically break down all internal stages |
| `spring.integration.handler.active`, corresponding `*.active` | Long-running active operations by convention | Does not turn into a queue dwell metric |

Configuration example (requires importing the appropriate classes):

~~~java
@Configuration
@EnableIntegration
@EnableIntegrationManagement(observationPatterns = "*")
class ObservabilityConfig {

    @Bean
    ObservationRegistry observationRegistry(MeterRegistry registry) {
        ObservationRegistry observations = ObservationRegistry.create();
        observations.observationConfig()
                .observationHandler(
                    new DefaultMeterObservationHandler(registry));
        return observations;
    }
}
~~~

`DefaultMeterObservationHandler` lives in the Micrometer core observation package. This configuration is **illustrative when no other observation bean exists**; with Spring Boot Actuator, the project may already have an auto-configured `ObservationRegistry`. Do not create duplicate beans or arbitrarily replace existing tracing handlers.

**Very important:** Spring Integration documentation notes that when using `ObservationRegistry`, management components are **not instrumented by default** unless `observationPatterns` is selected; `"*"` is used to enable it broadly in test environments. Having only a registry bean without an appropriate `ObservationHandler` also **will not export timers to Prometheus automatically**.

### 7.3. Queue wait does not appear automatically under a unified metric

`spring.integration.send` or `spring.integration.producer` is not another name for `queue.wait`. The framework cannot infer the wait time of every implementation solely from the send timer because:

- `ExecutorChannel` has its queue inside `TaskExecutor`;
- `QueueChannel` has a polling consumer with its own trigger;
- Brokers have queues on another server with a different clock;
- Messages can be persisted across restarts;
- There may be multiple consumers, priority queues, requeues, and redelivery.

Therefore, create a custom timer **right where messages are enqueued/dequeued**, or name a proxy metric such as `admission_to_handler_lag` when an exact enqueue hook is unavailable.

## 8. Designing instrumentation without distorting latency meaning

A pragmatic approach for an internal flow within the same JVM:

1. The producer uses `System.nanoTime()` before/after `send()` to record `T_send`.
2. `ChannelInterceptor.preSend()` inserts `perf.preSendNano` right before send.
3. The handler starts by reading `perf.preSendNano`, recording a **proxy**: `T_preSend→handlerStart`.
4. The handler measures its method body with `Timer.Sample` or `System.nanoTime()` inside `try/finally`.
5. Measure queue size/executor queue depth and poller duration separately to explain wait time.
6. When you truly need **exact queue dwell**, add hooks right after successful enqueue and at dequeue, or instrument message-store/broker timestamps/acks appropriately.

### Why is a preSend timestamp not the exact enqueue timestamp?

~~~text
preSend stamp
    -> serialization / other channel interceptors
    -> send may BLOCK when queue is full
    -> actual queue insertion
    -> queue waiting
    -> receive()
    -> handler invocation
~~~

If you use:

\[
T_{\text{proxy}} = t_{\text{handler start}}-t_{\text{preSend}}
\]

then `T_proxy` typically includes **send/admission overhead + queue waiting + receive/dispatch overhead**, and can increase when the producer blocks on a full queue. Do not label the metric `queue.wait.exact` or treat it as a raw broker number.

**Separate two levels of observation:**

- **Lightweight proxy:** enough to detect saturation; especially useful within the same JVM without modifying framework internals.
- **Exact measurement:** requires enqueue/dequeue hooks or durable queue/broker metadata with verified clocks and semantics.

### Notes on clocks

- Use `System.nanoTime()` for **elapsed duration within the same JVM**; do not compare absolute values or serialize them to another JVM.
- Do not carry a nanoTime header from a producer JVM to a consumer JVM or across a restart: clock origins are incompatible.
- With brokers/multiple nodes, use UTC timestamps from the producer/broker and account for clock skew/NTP, or use broker timestamps. Clock skew between nodes can be larger than the `queue wait` being measured.
- `MessageHeaders.TIMESTAMP` is usually the message creation time, not synonymous with enqueue.
- Do not use `System.currentTimeMillis()` to measure small durations within the same process when the clock may jump.
- For negative or anomalous values computed from headers, verify clock boundaries, message age, and deployment generation before reporting.

## 9. Java 17 + Spring Boot example: measuring all three latency components

A runnable example using Java 17+, Spring Boot, Spring Integration core, and Micrometer core. Place all code into a single file `LatencyMeasurementsApplication.java` in package `demo.integration`.

Goals:

- An `ExecutorChannel` backed by a `ThreadPoolTaskExecutor`.
- A `QueueChannel` with a poller.
- An interceptor that creates a `perf.preSendNano` timestamp on both channels.
- Measure `demo.send`, `demo.preSend_to_handler` (**queue/scheduling delay proxy**), and `demo.handler.body`.
- Print sample count and mean duration after 24 messages have been processed.

**Intentional limitations:** the queue here is in-memory, runs in **a single JVM**, with no broker or restart; `perf.preSendNano` is not designed to persist or cross nodes. This is an instrumentation demo, **not a production benchmark**.

### 9.1. Complete code

~~~java
package demo.integration;

import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.locks.LockSupport;

import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.core.instrument.Timer;
import io.micrometer.core.instrument.simple.SimpleMeterRegistry;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.annotation.MessageEndpoint;
import org.springframework.integration.annotation.Poller;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.integration.channel.QueueChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.messaging.Message;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.ChannelInterceptor;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@SpringBootApplication
@EnableIntegration
public class LatencyMeasurementsApplication {

    static final int PER_CHANNEL = 12;

    public static void main(String[] args) {
        SpringApplication.run(LatencyMeasurementsApplication.class, args);
    }

    @Bean
    MeterRegistry meterRegistry() {
        return new SimpleMeterRegistry();
    }

    @Bean("ordersExecutor")
    ThreadPoolTaskExecutor ordersExecutor() {
        ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
        pool.setCorePoolSize(4);
        pool.setMaxPoolSize(4);
        pool.setQueueCapacity(32);
        pool.setThreadNamePrefix("perf-worker-");
        pool.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        pool.setWaitForTasksToCompleteOnShutdown(true);
        pool.setAwaitTerminationSeconds(10);
        return pool;
    }

    @Bean("executorOrders")
    MessageChannel executorOrders(
            @Qualifier("ordersExecutor") ThreadPoolTaskExecutor executor) {

        ExecutorChannel channel = new ExecutorChannel(executor);
        channel.addInterceptor(new PreSendNanoInterceptor());
        return channel;
    }

    @Bean("queuedOrders")
    QueueChannel queuedOrders() {
        QueueChannel channel = new QueueChannel(64);
        channel.addInterceptor(new PreSendNanoInterceptor());
        return channel;
    }

    @Bean
    ApplicationRunner benchmark(
            @Qualifier("executorOrders") MessageChannel executor,
            @Qualifier("queuedOrders") MessageChannel queued,
            LatencyHandlers handlers,
            MeterRegistry metrics) {

        return args -> {
            for (int i = 0; i < PER_CHANNEL; i++) {
                sendMeasured(executor, metrics, "executorOrders",
                        "E-" + i);
                sendMeasured(queued, metrics, "queuedOrders",
                        "Q-" + i);
            }

            // Wait for both consumer types to process 24 messages.
            boolean finished = handlers.await(15, TimeUnit.SECONDS);
            if (!finished) {
                throw new IllegalStateException(
                        "Timed out waiting for handlers");
            }

            for (String channel : List.of(
                    "executorOrders", "queuedOrders")) {

                print(metrics, "demo.send", channel);
                print(metrics, "demo.preSend_to_handler", channel);
                print(metrics, "demo.handler.body", channel);
            }
        };
    }

    private static void sendMeasured(
            MessageChannel channel, MeterRegistry metrics,
            String name, String payload) {

        Message<String> message = MessageBuilder
                .withPayload(payload)
                .setHeader("eventId", "evt-" + payload)
                .build();

        long started = System.nanoTime();
        boolean accepted = false;

        try {
            accepted = channel.send(message, 1_000L);
            if (!accepted) {
                throw new IllegalStateException(
                        "Send timed out: " + name);
            }
        }
        finally {
            long elapsed = System.nanoTime() - started;
            metrics.timer("demo.send",
                    "channel", name,
                    "outcome", accepted ? "success" : "failure")
                .record(elapsed, TimeUnit.NANOSECONDS);
        }
    }

    private static void print(
            MeterRegistry metrics, String meter, String channel) {

        Timer timer = metrics.find(meter)
                .tag("channel", channel)
                .timer();

        if (timer == null) {
            System.out.printf("%s %s: NO_SAMPLES%n", meter, channel);
            return;
        }

        System.out.printf(
                "%s %s: count=%d mean=%.3fms max=%.3fms%n",
                meter, channel,
                timer.count(),
                timer.mean(TimeUnit.MILLISECONDS),
                timer.max(TimeUnit.MILLISECONDS));
    }
}

final class PreSendNanoInterceptor implements ChannelInterceptor {

    static final String HEADER = "perf.preSendNano";

    @Override
    public Message<?> preSend(
            Message<?> message, MessageChannel channel) {

        // Before channel admission; not guaranteed to be enqueued yet.
        return MessageBuilder.fromMessage(message)
                .setHeader(HEADER, System.nanoTime())
                .build();
    }
}

@MessageEndpoint
class LatencyHandlers {

    private final MeterRegistry metrics;
    private final CountDownLatch done =
            new CountDownLatch(LatencyMeasurementsApplication.PER_CHANNEL * 2);

    LatencyHandlers(MeterRegistry metrics) {
        this.metrics = metrics;
    }

    @ServiceActivator(inputChannel = "executorOrders")
    public void handleExecutor(Message<String> input) {
        handle("executorOrders", input);
    }

    @ServiceActivator(
            inputChannel = "queuedOrders",
            poller = @Poller(fixedDelay = "50", maxMessagesPerPoll = "8"))
    public void handleQueue(Message<String> input) {
        handle("queuedOrders", input);
    }

    private void handle(String channel, Message<String> message) {

        // Read stamp before starting the business body.
        Long preSend = message.getHeaders().get(
                PreSendNanoInterceptor.HEADER, Long.class);

        if (preSend != null) {
            long lag = System.nanoTime() - preSend;

            if (lag >= 0) {
                metrics.timer("demo.preSend_to_handler",
                        "channel", channel)
                    .record(lag, TimeUnit.NANOSECONDS);
            }
        }

        long handlerStart = System.nanoTime();
        String outcome = "success";

        try {
            // Simulate 10ms I/O without busy-spinning the CPU.
            LockSupport.parkNanos(
                    TimeUnit.MILLISECONDS.toNanos(10));
        }
        catch (RuntimeException ex) {
            outcome = "failure";
            throw ex;
        }
        finally {
            metrics.timer("demo.handler.body",
                    "channel", channel,
                    "outcome", outcome)
                .record(System.nanoTime() - handlerStart,
                        TimeUnit.NANOSECONDS);

            done.countDown();
        }
    }

    boolean await(long timeout, TimeUnit unit)
            throws InterruptedException {
        return done.await(timeout, unit);
    }
}
~~~

### 9.2. Which dependencies should be used to run it?

Gradle snippet matching the **Spring Boot BOM** chosen by the project:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("io.micrometer:micrometer-core")
}
~~~

This snippet does not include a complete build file/plugins; place it in a Spring Boot project that already declares Java 17 and appropriate plugins/dependency management. If Spring Boot auto-configures a `MeterRegistry` via Actuator, avoid creating a duplicate bean in a real application; you can use the existing registry instead of `SimpleMeterRegistry`.

**In STEP 4, this code is for learning and experimentation; Gradle/Content QA has not been run yet.** Before bringing it into a specific project, pin versions and run integration tests, especially if the application uses a different Spring Integration 7.x/Boot generation.

### 9.3. Expected output

For example, the program may print:

~~~text
demo.send executorOrders: count=12 mean=...ms max=...ms
demo.preSend_to_handler executorOrders: count=12 mean=...ms max=...ms
demo.handler.body executorOrders: count=12 mean=...ms max=...ms
demo.send queuedOrders: count=12 mean=...ms max=...ms
demo.preSend_to_handler queuedOrders: count=12 mean=...ms max=...ms
demo.handler.body queuedOrders: count=12 mean=...ms max=...ms
~~~

Actual numbers **depend on the machine, thread scheduling, timer precision, and poller speed**. Do not assign a fixed value to mean/max and do not conclude from 12 messages that you have a reliable benchmark.

Expected trends:

- `demo.send` on `ExecutorChannel` is small when the pool is not saturated; if the queue is full/rejecting, it may fail.
- `demo.send` on `QueueChannel` is small when capacity remains; it may block when full.
- `demo.preSend_to_handler` on `QueueChannel` can be large due to the polling interval/backlog.
- `demo.handler.body` on both paths has nearly the same workload (10 ms simulated), but differs due to the scheduler.

### 9.4. Why use `CountDownLatch`?

An `ExecutorChannel` returns before the handler finishes. If you print the Timer immediately after `send()`, some handler samples **will not have been recorded yet**. `CountDownLatch` ensures the demo waits for every handler to be invoked and measured before printing counts. Do not use `Thread.sleep(2000)` and hope all tasks always finish on a slow CI machine.

**Limitation:** `CountDownLatch.countDown()` happens in the `finally` block of the body. If a message is blocked right before entering the method (e.g., conversion/advice error), `done` may not reach 0; a timeout is a signal to investigate the error path. For flows with transactions/outbound side effects, “handler called countDown” does not necessarily mean the business commit succeeded.

## 10. Improving queue wait measurement accuracy

### 10.1. Using a preSend stamp as a proxy

In the example, `preSend` executes **before** the queue officially accepts the message. Therefore, `demo.preSend_to_handler` measures an **admission-to-handler proxy**, not exact queue residency.

If the goal is capacity planning, the proxy is useful when:

- Both producer and handler are in the same JVM;
- The queue is not frequently full;
- Comparisons across deployments use the same measurement point;
- Queue depth and scheduler metrics are present to explain fluctuations.

### 10.2. Using actual enqueue/dequeue hooks

To obtain `T_queue_wait` matching the definition `td - ta`, measure:

- `ta`: when the queue/store/broker **confirms successful recording**;
- `td`: when the consumer actually **takes the item off the queue**;
- The same logical message ID linking both timestamps;
- Across multiple JVMs, clocks/clock skew are controlled or the backend supplies timestamps from a single source.

Pseudo-code example for an instrumented queue:

~~~java
// Application-designed API sketch, NOT a QueueChannel API.
void onEnqueueCommitted(String eventId, long monotonicNow) {
    enqueueTimes.put(eventId, monotonicNow);
}

void onDequeued(String eventId, long monotonicNow) {
    Long started = enqueueTimes.remove(eventId);
    if (started != null) {
        timer.record(monotonicNow - started,
                TimeUnit.NANOSECONDS);
    }
}
~~~

Only use a map/nanoTime timestamp if enqueue and dequeue occur in **the same JVM** without persisting across restarts. For queues with priority/retry/requeue, decide whether each enqueue gets a **delivery attempt ID** or uses a logical event ID: one event may enter the queue multiple times. You must clean up the map on timeout/cancellation to prevent memory leaks.

### 10.3. Why is `postSend` also not enough?

A `ChannelInterceptor.postSend()` is invoked after `send()` completes, but the consumer may have **already dequeued** the message before the callback runs. If you try to attach a timestamp to the message during `postSend`, the immutable message is already sitting in the queue with its old headers. A `ConcurrentHashMap<messageId, timestamp>` updated after `send()` still has a race: the consumer can look up the timestamp before the producer sets it.

To measure queue residency accurately, you must bind the timestamp to an **enqueue/dequeue mechanism with proper synchronization**, not merely a misplaced interceptor.

### 10.4. Brokers and message stores

- **Kafka:** a record timestamp is not by default the time the broker admitted it; it depends on `CreateTime` vs `LogAppendTime`, producer send callbacks, and consumer offsets/times.
- **RabbitMQ:** publisher confirms, delivery properties, and consumer acks have distinct semantics; when the producer is confirmed does not mean the consumer has started.
- **JDBC queue:** you can store `enqueued_at` with the row and measure `dequeued_at` when the consumer claims/receives it, while accounting for transaction commit and clocks.
- **Redis/other stores:** you must instrument the actual write/read operations and TTL/recovery, without assuming the adapter exports queue wait out of the box.

These examples explain general semantics; specific implementations and broker settings must be verified against the exact driver/adapter/version.

## 11. Measuring handler execution with Micrometer Timer

Micrometer `Timer` is suitable for recording latency and operation counts. You can use:

~~~java
Timer handlerTimer = Timer.builder("app.handler.execution")
    .description("Business method execution time")
    .tag("handler", "shipping")
    .publishPercentileHistogram()
    .serviceLevelObjectives(
        Duration.ofMillis(10),
        Duration.ofMillis(50),
        Duration.ofMillis(200))
    .register(meterRegistry);

handlerTimer.record(() -> processShipment(message));
~~~

The snippet requires importing `io.micrometer.core.instrument.Timer`, `java.time.Duration`, and the application's `meterRegistry` and `processShipment(message)`. When the method throws, `Timer.record` still records the duration, but separating outcomes requires additional tag/counter policies.

To distinguish success/failure:

~~~java
long start = System.nanoTime();
String result = "success";

try {
    processShipment(message);
}
catch (RuntimeException ex) {
    result = "failure";
    throw ex;
}
finally {
    meterRegistry.timer("app.handler.execution",
            "handler", "shipping",
            "result", result)
        .record(System.nanoTime() - start, TimeUnit.NANOSECONDS);
}
~~~

Do not put `eventId`, raw `correlationId`, `customerId`, payload, or exception message in metric tags because of **very high cardinality**. Use bounded labels such as `handler`, `channel`, `result`, and `exception.class` (with a controlled value set).

### `Timer.Sample`

A convenient API:

~~~java
Timer.Sample sample = Timer.start(meterRegistry);

try {
    processShipment(message);
}
finally {
    sample.stop(meterRegistry.timer(
            "app.handler.execution", "handler", "shipping"));
}
~~~

`Timer.Sample` relies on the registry's clock and is suitable for the duration of a single operation. Do not put `Timer.Sample` into headers crossing brokers/stores, as it is not designed to be serialized and used across processes.

### Histograms and percentiles

Micrometer supports:

- **Count / total time:** invocation count and total duration.
- **Mean:** total duration / count.
- **Max:** maximum observed value within a window/depending on the registry.
- **Client-side percentiles** (`publishPercentiles`) per meter ID, which usually cannot be accurately aggregated across instances.
- **Percentile histograms** (`publishPercentileHistogram`) for backends that support aggregating buckets (e.g., Prometheus); query `histogram_quantile(...)` over properly summed buckets.

**Do not take `p95(send) + p95(wait) + p95(handler)` as `p95(end-to-end)`.** Percentiles are properties of distributions, samples do not necessarily correspond to the same message, and intervals may overlap.

## 12. Measuring end-to-end latency with event identity

A request may travel through:

~~~mermaid
flowchart LR
    G["Gateway ingress"] --> Q["QueueChannel"]
    Q --> P["Poller"]
    P --> H["Handler"]
    H --> DB["Database commit"]
    DB --> OUT["Reply / acknowledgement"]
~~~

If the SLA is “from message entering the system until the order commits in the DB”, the endpoint must be **after commit**. If the SLA is “from gateway request until the client receives a response”, the endpoint is the gateway reply/HTTP response.

Measure end-to-end using spans/trace context or an application-specific timer at the exact boundaries. With a transaction:

~~~text
handler method returns
   -> transaction interceptor commits
   -> message broker ack
~~~

`T_handlerBody` does not include the commit/ack step if the method returns earlier. An endpoint observation also does not automatically mean “transaction committed”. Only testing against a real DB/broker confirms the milestone.

### What are `eventId` and `correlationId` for?

- `eventId`: identifies the **logical event**, stable across retries/replays.
- `correlationId`: links messages belonging to the same workflow or aggregator group.
- `deliveryAttemptId`: distinguishes redeliveries if you need to measure queue wait per attempt.
- `traceId`: links spans across processes.
- `MessageHeaders.ID`: ID of a single Message instance, which may change when rebuilt.

Use these IDs to correlate **logs/traces**, not as metric tags for time series. If an event is retried multiple times, clarify whether the SLA is measured from **first ingress** or **final successful attempt**.

## 13. Little’s Law, capacity, and backlog

For a **stable** system over a sufficiently representative observation window, Little’s Law states:

\[
L = \lambda W
\]

Where:

- `L`: average number of work items in the system/queue under consideration;
- `λ`: average completion throughput;
- `W`: **average** residence time within that scope.

For example, a stable queue processing 200 messages/s with an average wait time of 0.5 s has:

\[
L \approx 200 \times 0{,}5 = 100 \text{ message}
\]

This does not mean p95 wait equals 0.5 s, nor does it hold verbatim when arrivals exceed the service rate and the queue is **growing continuously**.

If arrivals are 300 messages/s while consumers complete at most 200/s during an overload period:

~~~text
Backlog growth ≈ 300 - 200 = 100 messages/s
After 60 seconds ≈ 6,000 additional queued messages if there is no drop/backpressure.
~~~

The numbers above are an illustrative quantitative model, excluding retries, priorities, and other state-transition sources.

### Estimating required workers

If a handler has an average **worker occupancy time** of `S=50 ms`, each worker ideally completes around 20 tasks/s. To sustain 200 tasks/s requires at least around 10 workers **in a model with no overhead/contention**.

Scaling past 10 workers can still fail if:

- The DB connection pool only has 5 connections;
- The same `LockRegistry` key serializes the critical section;
- Broker/remote API rate limits apply;
- A retry multiplier triples the number of attempts;
- The workload has a very long p99 or heap/GC pauses the scheduler.

Therefore, measure `handler body duration`, executor active/queued, queue wait, and downstream saturation **together**.

## 14. Reading percentiles properly to locate bottlenecks

| Scenario | `T_send` | `T_preSend→handler` | `T_handler` | Investigation direction |
| --- | --- | --- | --- | --- |
| DirectChannel + slow HTTP | High | Not an appropriate queue metric | High | HTTP/downstream |
| ExecutorChannel pool full | May be low or fail | High | Normal | Worker saturation, queue |
| QueueChannel poller runs infrequently | Low | High | Normal | Poll interval, maxMessagesPerPoll |
| QueueChannel capacity full | High due to blocking | May be high | Normal | Backpressure, backlog |
| Handler slow due to DB lock | May be high on DirectChannel | May be high on async backlog | High | DB lock/transaction |
| Slow Redis/JDBC message store | May be high | May be high | Normal | Store I/O, serializer |
| Long retry/backoff inside handler | Depends on channel | Backlog grows | Depends on timer placement | Retry policy/attempts |
| Many events sharing correlation | Depends on channel | Increases | May increase | Aggregator LockRegistry contention |

**Do not compare p95 between two timers collected on different message sets** and directly conclude a root cause. Only matching load, version, label scope, and consistent sampling/retention are valid.

### Head-of-line blocking

A FIFO queue with a single consumer: one message taking 5 s to process can force small messages behind it to wait, even if their handler bodies take only 5 ms. In that case:

~~~text
message A: handler=5000ms
message B: wait=5000ms, handler=5ms
message C: wait=5005ms, handler=5ms
~~~

Increasing concurrency can reduce head-of-line blocking if messages are independent; however, with aggregators/correlation groups sharing state, ordering and locking must be preserved. Do not enable unbounded concurrency when downstream holds shared state.

## 15. Threading, transactions, retries, and measurement pitfalls

### 15.1. Thread boundaries

| Boundary | What happens | Instrumentation consequence |
| --- | --- | --- |
| `DirectChannel` | Usually same producer-handler thread | Can measure synchronously; send duration includes handler |
| `ExecutorChannel` | Handler runs in worker thread | Stamp/trace context must travel with the message or via propagation |
| `QueueChannel` + poller | Handler runs in poller task | Admission and handler occur at different times |
| Reactive publisher | `publishOn`/`subscribeOn` changes scheduler | Reactor Context, lazy subscription, nonblocking |
| Broker | Different process/node | Do not pass System.nanoTime headers across nodes |

Standard MDC/ThreadLocal **does not automatically cross** every asynchronous boundary. Use message headers, Micrometer Observation context propagation, or Reactor Context as appropriate; for cross-process measurement, propagate `traceId`/`eventId` and measure via broker timestamps or traces.

### 15.2. Transactions

Imperative `@Transactional` is thread-bound. An `ExecutorChannel` switches threads so the sender's transaction does not wrap the handler. If the queue accepts a message but the handler rolls back, whether the message is requeued depends on **the source/poller transaction, ack policy, and store**.

Measurement example:

~~~text
t0 send start
t1 QueueChannel stored message
t2 poller receives
t3 handler starts
t4 handler returns
t5 transaction commits
t6 broker ack
~~~

If the SLA target is durable completion, measure up to `t5`/`t6`; the handler body timer only reaches `t4`.

### 15.3. Retries and recovery

When `RequestHandlerRetryAdvice` executes three attempts, determine:

- Does the timer wrap **the entire advice** or each attempt individually?
- Is backoff included in `T_handler`?
- Is the message re-enqueued between attempts?
- If an exception is swallowed by a recovery callback, is the outcome recorded as success or recovered?
- Do events replayed from a broker retain old IDs/timestamps or get new ones?
- Are retries routed to an error channel counted as another handler execution?

Use two metrics when needed:

~~~text
app.handler.attempt.duration    // each business processing attempt
app.handler.logical.duration    // entire retry/recovery boundary
~~~

For a logical event with three attempts, `attempt.count` can be 3 while `logical.count` is 1. Do not use the endpoint timer count as the number of **unique** messages processed.

### 15.4. ErrorMessage

If a handler throws on an `ExecutorChannel` or poller, an error handler may publish an `ErrorMessage`. The failure happens **after** the producer's `send()` has already recorded success, so `demo.send` still has a success outcome in the sense of **handoff accepted**.

To report business outcomes, collect them from the handler/recovery/commit boundary. An `ErrorMessage` is just a message carrying an exception; it does not by itself prove the source rolled back or wrote to a durable DLQ.

## 16. Tracing and message history for wait-time analysis

In production environments, custom latency timers should be combined with:

- **Distributed trace:** spans for inbound → queue boundary → handler → DB/API, with traceId linked cross-process.
- **Message history:** lists tracked components via the `history` header, with timestamps at each hop.
- **Executor/poller metrics:** queue depth, active workers, task rejections, poll duration.
- **Message store metrics:** write/read duration, oldest pending message age.
- **Business event state:** eventId, correlation, transaction commit, and idempotency.

**A message history timestamp gap is not automatically exact queue wait.** Two history entries can be far apart due to polling, retries, I/O, or thread scheduling. History is a routing map, not a handler-time profiler.

### Span hierarchy and queue duration

A publisher span measuring `send()` finishes before the handler span in an async flow. If they lack proper context propagation, traces split into two separate trees. When you need to observe “time in queue”, use **span/event timestamps** created at enqueue/dequeue by contract, not calculated from arbitrary log timestamps.

For cross-node telemetry, UTC clocks can drift and exporters have batching delays; distinguish **event timestamps** from the time the backend receives telemetry.

## 17. Reliable benchmarks differ from console demos

The demo in section 9 only generates 24 messages and runs once; it illustrates instrumentation and cannot establish throughput/p99.

A better benchmarking process:

1. **Start up and warm up** the JVM, JIT, caches, and connection pools before collecting samples.
2. Define the **workload**: payload sizes, CPU/I/O ratio, hot correlation keys, messages/s.
3. Measure the **external** arrival rate and **actual** commit/completion throughput.
4. Collect latency distributions over the same time window: send, queue wait, handler, end-to-end.
5. Record CPU usage, GC, heap, thread counts, executor queue, and DB/Redis connection pools.
6. Separate steady state from ramp-up/ramp-down; do not merge them and take a mean.
7. Run multiple iterations, keep hardware/limits constant, and pin versions and configurations.
8. Test both **open-loop** (arrivals do not wait for responses) and **closed-loop** (clients wait for completion) depending on production traffic.
9. Record errors, timeouts, retries, rejections, and dropped messages — not just successful requests.
10. Have exit criteria: SLA/SLO and sufficient data sources to investigate discrepancies.

### Coordinated omission

If a load generator sends a new request **only after the previous request finishes**, then when the system stalls/GCs it **stops sending** messages that would have arrived during the stall. Latency samples can look far better than production reality. For an independent real-world arrival rate, simulate open-loop traffic and watch queue backlog/tail latency. Micrometer has pause detection suitable for some cases, but it does not replace a proper load model.

### Instrumentation overhead risks

- Adding a new header to every message increases allocations/serialization.
- Capturing `System.nanoTime()` is usually lightweight, but synchronous logging per message can be very expensive.
- Histogram buckets and high-cardinality tags carry memory and time-series costs.
- AOP/advice and tracing hooks can alter timing; measure the overhead of enabling instrumentation.
- A `SimpleMeterRegistry` keeps metrics in-process, not a production backend exporter.
- Duration from tracer span start/stop may differ from the handler body if the span wraps converters/advice/replies.

## 18. Common measurement mistakes and how to fix them

| Mistake | Why it is wrong | How to fix it |
| --- | --- | --- |
| `send()` is fast so “message processing is fast” | With async channels, only handoff succeeded | Measure from enqueue/receive to handler and completion |
| Slow `send()` must be caused by the queue | DirectChannel may run the handler synchronously | Check channel type and handler body |
| Treating `MessageHeaders.TIMESTAMP` as enqueue time | Timestamp is usually set at message creation | Instrument the actual enqueue point |
| Passing `System.nanoTime()` header across Kafka or restarts | Monotonic clocks differ across JVMs | Use synced clocks/backend timestamps and adjust for skew |
| Calling a `preSend` stamp exact queue wait | Stamped before enqueue/blocking | Call it an admission-to-handler proxy |
| Using a `postSend` map as proof of queue dwell | Consumer may dequeue before postSend runs | Hook atomic enqueue/dequeue |
| `p95(send)+p95(wait)+p95(handler)=p95(total)` | Percentiles do not add linearly; intervals may overlap | Measure end-to-end directly |
| Using `Thread.sleep()` in async integration tests | Flaky, both slow and lacking guarantees | `CountDownLatch`, `QueueChannel.receive(timeout)`, Awaitility |
| Measuring only successes | Misses timeouts/retries/rejections and failed queue dwell | Record outcomes/failures with low cardinality |
| Treating timer count as unique messages | Retries/duplicates inflate counts | Add logical eventId and separate attempt counts |
| Assuming ObservationRegistry alone yields Prometheus timers | Missing ObservationHandler/exporter/patterns | Check metrics/traces wiring |
| Printing full payloads to debug latency | Log I/O distorts throughput | Structured sampling, metrics, traceId |
| Using average instead of p99 | Tail latency can be huge | Histograms/percentiles, service-level buckets |
| Looking only at executor active threads | Workers may be waiting on locks/DB connections | Measure lock wait, DB pool, queue age |
| Changing capacity without checking durability | Full/overflowing queues or restarts lose messages | Bounded queues + backpressure/store/policies |

## 19. Writing non-flaky measurement tests

### Test 1: verify exact sample counts

After the demo finishes 12 messages per channel:

~~~java
Timer executorBody = registry.find("demo.handler.body")
        .tag("channel", "executorOrders")
        .tag("outcome", "success")
        .timer();

assertNotNull(executorBody);
assertEquals(12L, executorBody.count());
~~~

This is an **additional JUnit assertion**, requiring a reference to the application's `registry` and appropriate JUnit imports. It proves the handler recorded samples, not that every message committed an external transaction.

### Test 2: `send()` differs from handler execution

In an `ExecutorChannel` test, use `CountDownLatch` to hold a handler open before completion:

~~~java
CountDownLatch started = new CountDownLatch(1);
CountDownLatch release = new CountDownLatch(1);
CountDownLatch finished = new CountDownLatch(1);

// Test handler:
MessageHandler blocking = message -> {
    started.countDown();

    try {
        if (!release.await(3, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out in test");
        }
    }
    catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException("Interrupted", ex);
    }
    finally {
        finished.countDown();
    }
};
~~~

This is a fragment for a test harness that attaches `blocking` to an `ExecutorChannel` with an appropriate `TaskExecutor`. The test sends a message and asserts `send()` returned while `finished` is not yet complete, then calls `release.countDown()` and `finished.await(...)`. Do not test by comparing two fixed durations in milliseconds.

**Be careful:** if the executor is configured with `CallerRunsPolicy`, the handler may run on the sender thread when the pool is full. In that case `send()` also blocks; the test must use an executor with available capacity and an explicit rejection policy.

### Test 3: queue wait and polling schedule

Use a `QueueChannel` with fixed capacity, send a message while the consumer is **not yet started**, wait/start the poller under test control, then verify the message remained in the queue and the handler was called afterward. Measure the admission-to-handler proxy and assert only **validity/directionality**, never an exact millisecond value dependent on the scheduler.

### Test 4: failures, retries, and telemetry

Create a handler that throws an exception for a few attempts before succeeding. Count:

- `send` accepted/failure per channel;
- Handler attempts and final outcome;
- ErrorMessage/recovery if configured;
- Transaction rollback/commit in the backing DB;
- Retry backoff, queue age, and tail latency.

Do not expect every timer count to be equal: they measure **different scopes**.

## 20. SLOs, dashboards, and alerts for a real-world flow

Example flow receiving orders and writing to a DB:

~~~text
HTTP/JMS source → QueueChannel → Poller → Handler → JDBC commit
~~~

A good dashboard has at least:

| Group | Metrics | Purpose |
| --- | --- | --- |
| Ingress | accepted/s, rejected/s | Inbound load and backpressure |
| Send | p50/p95/p99 `T_send`, failures | Whether producer is blocking/throwing |
| Queue | pending count, oldest age, p95 queue lag | Whether backlog and consumer lag exist |
| Handler | p50/p95/p99 body execution, attempts, failures | Whether business work is slow |
| End-to-end | p95/p99 from ingress to commit/ack | Actual user-facing SLA |
| Runtime | executor active/queued/rejected, poller duration | Thread/scheduler saturation |
| Dependencies | DB pool wait, query latency, HTTP duration | Downstream bottlenecks |
| Reliability | retries, dead-letter, redelivery, duplicates | Whether latency accompanies data loss |
| Correlation | group size/age, lock wait/hold | Whether aggregator has hot keys or deadlocks |

### SLOs must have clear start and end points

Examples (illustrative only):

- `p95(end-to-end accepted→DB commit) < 500 ms`;
- `p99(queue admission→consumer start) < 100 ms` in steady state;
- `99.9%` of accepted messages reach a final outcome within 30 seconds;
- `rejected messages` are tracked and have a retry/dead-letter policy.

Without defining “accepted”, “consumer start”, and “commit” with exact events, a dashboard may look nice while the SLO remains unverifiable.

### Diagnosing in order

1. **Scope:** from where to where is the metric calculated? Sync or async channel?
2. **Symptoms:** which increased first—send p99, queue lag p99, or handler p99?
3. **Saturation:** queue depth, executor occupancy, poller interval, DB pool.
4. **Dependencies:** API latency, lock registry, message store read/write, GC.
5. **Failures:** retry attempts, timeouts, channel rejections, errorChannel.
6. **Data correctness:** broker ack, DB commit, duplicate/replayed events.
7. **Intervention:** fix the actual bottleneck (backpressure, worker pool, SQL, concurrency, batch/poller).
8. **Re-measure:** same workload and time windows, with a rollback plan if errors increase.

## 21. Practice exercises

1. **DirectChannel:** attach a handler simulating 100 ms I/O, measure send duration and handler body; explain why they overlap.
2. **ExecutorChannel:** use the program in section 9, increase `PER_CHANNEL` and decrease pool size; measure `preSend_to_handler` and saturation.
3. **QueueChannel:** change `fixedDelay` from 50 ms to 500 ms; observe how queue lag and throughput change.
4. **Backpressure:** reduce queue capacity to 2, send many messages; record send blocked/rejected and how many messages were processed.
5. **CallerRunsPolicy:** change the executor rejection policy and induce saturation; observe when the sender thread executes the handler.
6. **Handler body:** increase simulated work from 10 ms to 100 ms; measure handler duration and queue backlog.
7. **Poller:** change `maxMessagesPerPoll`, recording backlog, completion rate, and error rate simultaneously.
8. **Queue wait semantics:** replace the `preSend` interceptor with enqueue/dequeue hooks in an application-controlled test queue; compare the proxy against actual dwell time.
9. **Timer:** add histogram/SLO buckets; inspect p95/p99 when one group of messages is very slow.
10. **Retry:** make the handler fail two attempts before succeeding; compare the attempt timer and logical operation timer.
11. **Transactions:** write to a DB after the handler; measure up to commit, intentionally roll back, and check the end-to-end outcome.
12. **Executor error:** have the handler throw after send is accepted, verify why `send` still has a success outcome while the handler timer/report shows failure.
13. **Message store:** switch the in-memory QueueChannel to a persistent implementation in a test environment; check behavior across restarts, message age, and header serialization.
14. **Cross-node:** move producer and consumer to two JVMs and try reading the `System.nanoTime` header; analyze why the duration is invalid.
15. **Metrics cardinality:** intentionally tag each eventId on a timer in a test environment, observe the number of meter IDs grow; replace with channel/outcome tags.
16. **Trace:** use Micrometer Observation and tracing to verify context propagation across the executor.
17. **Hot correlation key:** add an aggregator with many messages sharing the same correlationId; measure lock wait, group age, and throughput.
18. **Load test:** compare a closed-loop generator with open-loop arrivals at the same advertised rate; look for coordinated omission.
19. **Operational dashboard:** build 4 rows: send p95, queue lag p95, handler p95, and end-to-end p95; add success/error/retry rates.
20. **Runbook:** simulate queue wait p99 increasing while handler body stays constant; write a root-cause procedure that avoids wrongly modifying the DB.

### Self-check questions

- Why can `DirectChannel.send()` take as long as the handler?
- Why does `ExecutorChannel.send()` returning success not guarantee the handler has finished?
- With a full QueueChannel, can `T_send` increase while `T_handler` stays unchanged?
- Is a `preSend` stamp accurate to the moment of queue admission? Why?
- Why does storing a timestamp in a map during `postSend` still have a race?
- How does `MessageHeaders.TIMESTAMP` differ from an enqueue timestamp?
- Can `System.nanoTime()` be used across two JVMs or across a restart?
- Why is `p95(send) + p95(wait)` not the p95 of the sum?
- Does Little’s Law use **mean** or **p99** queue wait?
- If a handler has three retry attempts, does a timer on an outer advice necessarily record three samples?
- Does ObservationRegistry export timers by default?
- How do you prove a business commit occurred after the handler method returned?

## 22. Checklist before handing off to QA

- Clearly defined `T_send`, `T_queue_wait`, `T_handler`, `T_end-to-end`.
- Metric names and scopes chosen to match `DirectChannel`/`ExecutorChannel`/`QueueChannel`.
- Did not label the preSend-to-handler proxy as exact queue residency.
- Recorded duration samples for both success and failure.
- Used `System.nanoTime` only within the same JVM, never persisted across restarts/brokers.
- Micrometer metrics/Observation patterns and handlers configured properly.
- Queue depth, worker pool, and poller metrics included to interpret queue lag.
- Latency distributions and percentiles measured under the same workload/time window.
- Did not add p95s or overlapping duration intervals together.
- Retries/transactions/acks/idempotency verified at business boundaries.
- Did not use eventId or payload as metric labels.
- Async tests use latches/receive timeouts, not fixed sleeps.
- Included warnings for backpressure, retry storms, and lost-message risk.
- Benchmarks marked as illustrative if not run on target infrastructure.
- Did not run STEP 6/Gradle/Python during this authoring step.

## 23. Official references

- [Spring Integration — Metrics and Management](https://docs.spring.io/spring-integration/reference/metrics.html): `spring.integration.send`, `spring.integration.receive`, Observation API, and conventions for producer/handler.
- [Spring Integration — Message Channel Implementations](https://docs.spring.io/spring-integration/reference/channel/implementations.html): DirectChannel, QueueChannel, ExecutorChannel, and blocking semantics.
- [Spring Integration — Configuring Message Channels](https://docs.spring.io/spring-integration/reference/channel/configuration.html): QueueChannel capacity, executor dispatch, and transaction boundaries.
- [Spring Integration — Message Endpoints / Polling Consumer](https://docs.spring.io/spring-integration/reference/endpoint.html): `maxMessagesPerPoll`, `receiveTimeout`, scheduling, and transaction support.
- [Spring Integration — Message Store](https://docs.spring.io/spring-integration/reference/message-store.html): queue persistence, MessageGroupStore, and durability.
- [Spring Integration — Error Handling](https://docs.spring.io/spring-integration/reference/error-handling.html): errorChannel, exception flow across async boundaries.
- [Spring Integration — Message History](https://docs.spring.io/spring-integration/reference/message-history.html): history header and tracked component timestamps.
- [Micrometer — Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html): `Timer.record`, `Timer.Sample`, duration units.
- [Micrometer — Histograms and Percentiles](https://docs.micrometer.io/micrometer/reference/concepts/histogram-quantiles.html): client percentiles, percentile histograms, and SLO buckets.
- [Micrometer — Observation](https://docs.micrometer.io/micrometer/reference/observation.html): registry, observation handler, and context.
- [Spring Framework — MessageChannel](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/MessageChannel.html): `send(message)` and `send(message, timeout)`.
- [Spring Framework — ChannelInterceptor](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/messaging/support/ChannelInterceptor.html): `preSend`, `postSend`, and `postReceive` callbacks.
