# Event Multicaster and Threading in the Spring Integration Event Adapter

## Lesson Objectives

In the **Event Adapter** chapter of the **SPRING_INTEGRATION_ADAPTERS** module, Spring components can exchange data through `ApplicationEventPublisher` and connect to Spring Integration `MessageChannel` flows. When moving events into or out of an integration flow, **which thread runs the listener** determines processing timing, exception propagation, transaction context, and system throughput.

After this lesson, you will be able to:

- Explain what `ApplicationEventMulticaster` does and why a Spring event is normally processed **synchronously** by default.
- Identify the executing thread of `ApplicationEventPublishingMessageHandler`, `ApplicationEventListeningMessageProducer`, `DirectChannel`, and `ExecutorChannel`.
- Choose among three ways to run asynchronously: an executor on the multicaster, `@Async` on a listener, or an `ExecutorChannel` for a segment of the integration flow.
- Configure a bounded executor, observe errors, protect transaction boundaries, and verify actual runtime behavior.

**Scope:** Spring application events are an event-broadcasting mechanism **within a single Spring `ApplicationContext`**. They can act as a bridge before or after file, SFTP, HTTP, JMS, AMQP, Kafka, or database adapters; the event multicaster itself does not become a durable message broker.

## 1. Where Does the Event Multicaster Sit?

`ApplicationEventPublisher` is the API code calls to publish a Spring event:

~~~java
publisher.publishEvent(new StockReserved("RSV-001"));
~~~

Spring uses an `ApplicationEventMulticaster` to locate matching `ApplicationListener`s and deliver the event to each listener. In a standard Spring Framework application, the default implementation is `SimpleApplicationEventMulticaster`.

~~~mermaid
flowchart LR
    S["Integration flow / Service"] --> P["ApplicationEventPublisher"]
    P --> M["ApplicationEventMulticaster"]
    M --> A["@EventListener"]
    M --> I["ApplicationEventListeningMessageProducer"]
    I --> C["MessageChannel"]
    C --> H["Service Activator / Handler"]
~~~

Two event adapters are directly involved:

| Component | Data direction | Role of the multicaster |
| --- | --- | --- |
| `ApplicationEventPublishingMessageHandler` | Spring Integration `Message<?>` → Spring event | Calls `ApplicationEventPublisher`; multicaster distributes the event to listeners |
| `ApplicationEventListeningMessageProducer` | Spring event → Spring Integration `Message<?>` | Invoked by the multicaster as a listener, then sends the message to its output channel |

On the outbound handler, `publishPayload` affects the **event type**, though it does not switch threads on its own:

- `publishPayload=false` (default): for payloads that are not already `ApplicationEvent`, the handler emits a `MessagingEvent` holding the original message.
- `publishPayload=true`: the handler publishes the payload directly, e.g. `StockReserved`; Spring may use `PayloadApplicationEvent` to represent the POJO.
- When the payload is already an `ApplicationEvent`, the handler publishes that event itself.

Therefore, when changing threading behavior, first confirm that the listener receives the expected **event type**. An event filtered out will not be processed even when the executor is configured properly.

## 2. Default: Synchronous on the Publishing Thread

`SimpleApplicationEventMulticaster` uses a synchronous mechanism by default: it invokes listeners on the thread that published the event. If the publisher is running on an HTTP request thread, the listener runs on that same thread; if the publisher runs on a poller thread or worker thread, the listener runs on that thread.

~~~mermaid
sequenceDiagram
    participant T as "Thread calling publishEvent"
    participant P as ApplicationEventPublisher
    participant M as SimpleApplicationEventMulticaster
    participant L1 as Listener A
    participant L2 as Inbound Event Adapter
    participant C as DirectChannel
    participant H as Service Activator

    T->>P: publishEvent(event)
    P->>M: multicastEvent(event)
    M->>L1: onApplicationEvent(event)
    L1-->>M: return
    M->>L2: onApplicationEvent(event)
    L2->>C: send(message)
    C->>H: handle(message)
    H-->>C: return
    C-->>L2: return
    L2-->>M: return
    M-->>P: return
    P-->>T: return
~~~

The diagram illustrates synchronous execution. The actual order between Listener A and the inbound adapter depends on listener registration/ordering; do not assume Listener A always runs first.

In the synchronous case:

1. `publishEvent(...)` returns only after all synchronous listeners finish or an exception interrupts the execution path.
2. A slow listener can extend the response time of the HTTP controller, service, or integration flow publishing the event.
3. Exceptions from a listener can propagate back to the event publisher unless handled by an `ErrorHandler` or a surrounding wrapper.
4. Synchronous listeners share the current thread, yet **execution order should not be treated as a business contract** unless you explicitly configure ordering and understand its limits.

`@Order` can specify the invocation order of listeners; it does not guarantee completion ordering once asynchronous threads are introduced later.

## 3. Complete Example: Tracing Threads Across Both Event Adapters

This example uses Spring Boot, Spring Integration, and Java 17+.

**Gradle dependencies:**

~~~gradle
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-integration")
    implementation("org.springframework.integration:spring-integration-event")
}
~~~

Let Spring Boot manage compatible dependency versions, or use the corresponding Spring Integration BOM if not using Spring Boot.

**Step 1 — Business payload.**

`StockReserved.java`:

~~~java
package com.example.stock;

public record StockReserved(String reservationId) {
}
~~~

**Step 2 — Outbound adapter emits the POJO as a Spring event; inbound adapter receives the same type.**

`StockEventConfig.java`:

~~~java
package com.example.stock;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.integration.channel.DirectChannel;
import org.springframework.integration.config.EnableIntegration;
import org.springframework.integration.event.inbound.ApplicationEventListeningMessageProducer;
import org.springframework.integration.event.outbound.ApplicationEventPublishingMessageHandler;
import org.springframework.messaging.MessageChannel;

@Configuration
@EnableIntegration
public class StockEventConfig {

    @Bean
    public MessageChannel outgoingStockEvents() {
        return new DirectChannel();
    }

    @Bean
    public MessageChannel inboundStockEvents() {
        return new DirectChannel();
    }

    @Bean
    @ServiceActivator(inputChannel = "outgoingStockEvents")
    public ApplicationEventPublishingMessageHandler outboundStockEvents() {
        var handler = new ApplicationEventPublishingMessageHandler();
        handler.setPublishPayload(true);
        return handler;
    }

    @Bean
    public ApplicationEventListeningMessageProducer inboundStockListener(
            @Qualifier("inboundStockEvents") MessageChannel outputChannel) {

        var adapter = new ApplicationEventListeningMessageProducer();
        adapter.setEventTypes(StockReserved.class);
        adapter.setOutputChannel(outputChannel);
        return adapter;
    }
}
~~~

**Note:** the demonstration flow has a clear direction: `outgoingStockEvents → outbound event adapter → Spring event → inbound event adapter → inboundStockEvents`. It terminates at the consumer below. Do not connect the consumer back to `outgoingStockEvents`, as that would create an infinite event-publishing loop.

**Step 3 — Service sending a message into the integration flow.**

`StockCommandService.java`:

~~~java
package com.example.stock;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.messaging.MessageChannel;
import org.springframework.messaging.support.MessageBuilder;
import org.springframework.stereotype.Service;

@Service
public class StockCommandService {

    private final MessageChannel outgoingStockEvents;

    public StockCommandService(
            @Qualifier("outgoingStockEvents") MessageChannel channel) {
        this.outgoingStockEvents = channel;
    }

    public void reserve(String reservationId) {
        System.out.println("SENDER: " + Thread.currentThread().getName());

        boolean sent = outgoingStockEvents.send(
                MessageBuilder.withPayload(
                        new StockReserved(reservationId)).build());

        if (!sent) {
            throw new IllegalStateException("Cannot send StockReserved");
        }
    }
}
~~~

**Step 4 — Observe the Spring listener and the Spring Integration consumer.**

`StockEventObservers.java`:

~~~java
package com.example.stock;

import org.springframework.context.event.EventListener;
import org.springframework.integration.annotation.ServiceActivator;
import org.springframework.stereotype.Component;

@Component
public class StockEventObservers {

    @EventListener
    public void onSpringEvent(StockReserved event) {
        System.out.printf(
                "SPRING: %s, id=%s%n",
                Thread.currentThread().getName(),
                event.reservationId());
    }

    @ServiceActivator(inputChannel = "inboundStockEvents")
    public void onIntegrationMessage(StockReserved payload) {
        System.out.printf(
                "INTEGRATION: %s, id=%s%n",
                Thread.currentThread().getName(),
                payload.reservationId());
    }
}
~~~

Call `stockCommandService.reserve("RSV-001")` from a service or controller. With the default multicaster and both channels set to `DirectChannel`, all three labels `SENDER`, `SPRING`, and `INTEGRATION` will print the **same thread name**. For instance, if invoked on an HTTP request thread:

~~~text
SENDER: http-nio-8080-exec-1
SPRING: http-nio-8080-exec-1, id=RSV-001
INTEGRATION: http-nio-8080-exec-1, id=RSV-001
~~~

This output is illustrative; exact thread names and the order of the two listener lines may vary. `DirectChannel` delivers messages to subscribers directly on the thread calling `send(...)`, unless an asynchronous boundary exists **before** the channel.

## 4. Three Ways to Switch to Asynchronous Processing

Not every async requirement should be configured at the same layer.

| Approach | Scope of impact | Where does the thread switch? | When to use |
| --- | --- | --- | --- |
| Attach a `TaskExecutor` to `applicationEventMulticaster` | Multiple Spring application listeners in the context | Multicaster schedules listener invocation | When eligible listeners should be dispatched via a shared executor |
| `@Async` on a single `@EventListener` method | Only the annotated listener | When Spring invokes the listener method | An independent, slow consumer such as sending emails or recording analytics |
| `ExecutorChannel` after the inbound event adapter | One segment of the integration flow | When a message is sent to the executor-backed channel | When controlling load and errors inside the Spring Integration pipeline |

Layers can be combined, though each layer adds another thread hop. Clearly define executor ownership, error reporting, and load bounds.

### Approach A — Using an Executor for the Event Multicaster

Spring looks for a bean named **`applicationEventMulticaster`** to use instead of the default multicaster. You can configure `SimpleApplicationEventMulticaster` with a bounded executor.

`SpringEventMulticasterConfig.java`:

~~~java
package com.example.stock;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.task.TaskExecutor;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
public class SpringEventMulticasterConfig {

    @Bean("springEventExecutor")
    public ThreadPoolTaskExecutor springEventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("spring-event-");
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(10);
        return executor;
    }

    @Bean("applicationEventMulticaster")
    public ApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("springEventExecutor") TaskExecutor executor) {

        var multicaster = new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        multicaster.setErrorHandler(error -> {
            System.err.println(
                    "Application event listener failed: " + error);
        });
        return multicaster;
    }
}
~~~

Spring manages the lifecycle of the `ThreadPoolTaskExecutor` bean, including initialization and shutdown. In real systems, replace `System.err` with centralized logging and metrics; the `ErrorHandler` above only logs the error and lets the listener task end, **without automatic retries**.

After this configuration, Spring listeners and the inbound event adapter **that are eligible for async execution** are scheduled on threads such as `spring-event-1` and `spring-event-2`. Because the inbound adapter then sends the message to a `DirectChannel`, the downstream consumer in the flow can run on the **same worker thread as the inbound adapter**, no longer on the thread calling `reserve(...)`.

**Two limitations to understand:**

- Replacing the `applicationEventMulticaster` bean affects event dispatching for the **entire Spring `ApplicationContext`**, including listeners unrelated to this flow. Verify the impact on all other application listeners.
- Starting with Spring Framework 6.1, some listeners report that they do not support async execution via `supportsAsyncExecution()` and must run on the publishing thread; a classic example is listeners relying on transaction context. Thus you cannot claim **every** listener will move to the executor merely because `setTaskExecutor(...)` is set.

If a worker is slow or the queue fills up, dispatching will be delayed or the executor will reject tasks. Pool/queue bounds are part of the operational contract and must be tuned against real load.

### Approach B — Making a Single @EventListener Asynchronous

If only one listener performs slow work (such as sending emails), using `@Async` leaves the shared multicaster unchanged.

`SelectiveAsyncConfig.java`:

~~~java
package com.example.stock;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class SelectiveAsyncConfig {

    @Bean("notificationExecutor")
    public ThreadPoolTaskExecutor notificationExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("notification-");
        return executor;
    }
}
~~~

`StockNotificationListener.java`:

~~~java
package com.example.stock;

import org.springframework.context.event.EventListener;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Component;

@Component
public class StockNotificationListener {

    @Async("notificationExecutor")
    @EventListener
    public void sendNotification(StockReserved event) {
        System.out.printf(
                "NOTIFY: %s, id=%s%n",
                Thread.currentThread().getName(),
                event.reservationId());

        // Send notification using a client with reasonable timeout and retries.
    }
}
~~~

With the default multicaster:

- `sendNotification(...)` runs on a `notification-*` thread.
- Other listeners, including the inbound event adapter if not configured otherwise, can continue running on the publishing thread.
- Exceptions from a `void @Async` method do not automatically return to `publishEvent(...)`. Configure an `AsyncUncaughtExceptionHandler`, logging/monitoring, or handle errors inside the listener itself.

Do not use the return value of an `@Async @EventListener` method as a mechanism to publish follow-up events. If you need to emit a new event, inject `ApplicationEventPublisher` and call `publishEvent(...)` explicitly after processing.

### Approach C — Asynchronous at MessageChannel in Spring Integration

If the goal is to decouple **integration flow processing** from the thread receiving the Spring event, replace the inbound adapter's `DirectChannel` with an `ExecutorChannel`.

~~~java
import java.util.concurrent.Executor;
import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.context.annotation.Bean;
import org.springframework.integration.channel.ExecutorChannel;
import org.springframework.messaging.MessageChannel;

@Bean
public MessageChannel inboundStockEvents(
        @Qualifier("integrationWorkerExecutor") Executor executor) {
    return new ExecutorChannel(executor);
}
~~~

In this example, define an `integrationWorkerExecutor` bean (such as `ThreadPoolTaskExecutor`) with bounded capacity similar to Approach A or B. This bean **replaces** the `inboundStockEvents()` bean returning `DirectChannel` in Section 3; do not keep two beans with the same name.

When the Spring multicaster remains synchronous:

~~~text
SENDER [thread A]
    -> outbound adapter
    -> multicaster (thread A)
    -> inbound adapter (thread A)
    -> ExecutorChannel.send(...), scheduled on executor
                                          |
                                          v
                              Service Activator [thread B]
~~~

`send(...)` may return once the task is accepted by the executor; that **does not mean** the service activator has finished. If the executor is saturated, sending may also be rejected according to the executor's rejection policy.

Approach C keeps the async decision at the integration flow boundary, which is convenient when only one pipeline needs tuned concurrency, error channels, and parallelism.

## 5. Choosing the Right Threading for Inbound and Outbound

Analyze the **thread path**, because a single event can cross multiple layers:

| Starting point | Multicaster | Channel | Thread typically running final handler |
| --- | --- | --- | --- |
| Service calls `publishEvent` | Default sync | `DirectChannel` | Service thread calling `publishEvent` |
| Service calls `publishEvent` | Async executor | `DirectChannel` | Multicaster worker thread, if listener supports async |
| Service calls `publishEvent` | Default sync | `ExecutorChannel` | Integration executor worker thread |
| Service calls `publishEvent` | Async executor | `ExecutorChannel` | Integration executor worker thread, after multicaster dispatch |
| Integration service sends message to outbound handler via `DirectChannel` | Default sync | No inbound adapter | Synchronous Spring listener runs on message-sending thread |
| Integration service sends message to outbound handler via `ExecutorChannel` | Default sync | No inbound adapter | Synchronous Spring listener runs on `ExecutorChannel` worker thread |

One event can have **multiple Spring listeners**. With an executor-backed multicaster, they may execute on different workers and finish at different times.

**Practical rule:** trace the thread at three points: right before calling `publishEvent`, inside the Spring listener/inbound adapter, and inside the service activator. Looking at the thread name only at the publishing site will not tell you how downstream runs.

## 6. Where Do Exceptions Go When Threads Change?

An async boundary usually changes where exceptions surface.

~~~mermaid
flowchart TD
    A["Exception in listener / handler?"] --> B{"Does listener run synchronously?"}
    B -->|Yes| C["Exception can propagate back to publishEvent / send"]
    B -->|No| D["Exception on worker thread"]
    D --> E["ErrorHandler / async handler / error channel"]
    E --> F["Log, record metrics, retry, or recover per design"]
~~~

| Where error occurs | Where it can be observed | Notes |
| --- | --- | --- |
| Synchronous Spring `@EventListener` | Caller of `publishEvent` / outbound handler | Unless the multicaster has an `ErrorHandler` intercepting it |
| Listener executed by multicaster executor | Listener worker thread; `ErrorHandler` if configured | Caller may have already returned before listener finishes |
| `@Async @EventListener` returning `void` | `AsyncUncaughtExceptionHandler` or inside listener | Does not automatically propagate back to caller |
| Service activator on `DirectChannel` | Thread calling `send(...)` | Can propagate back to inbound adapter/multicaster |
| Service activator on `ExecutorChannel` | Worker thread and corresponding Spring Integration error mechanism | Must configure/verify `errorChannel`, logging, or recovery per topology |

**Pay special attention:** `channel.send(message) == true` may only confirm that the message was handed off or accepted at the channel boundary, not that downstream async work completed or that side effects (sending email / writing DB) succeeded.

When handling errors, distinguish:

- **Retryable operational errors**, e.g., HTTP 503 or timeout calling an external service.
- **Invalid data errors**, e.g., event missing `reservationId`, which should be recorded clearly and handled under a poison-message policy.
- **Executor saturation errors**, which can appear immediately at scheduling time and require queue bounds, rejection handling, and backpressure.

Spring application events do not provide durable retries, dead-letter queues, or event persistence across process restarts. If recovery across restarts or reliable cross-service delivery is required, consider a JMS/AMQP/Kafka broker paired with an outbox or appropriate storage mechanism.

## 7. ThreadLocal, MDC, and Transaction Context

Switching threads affects more than performance; it also affects **context** bound to the current thread.

### Transactions

Standard Spring transactions are thread-bound. When an event is published inside a `@Transactional` method:

- A **synchronous** listener can participate in that thread's transaction (depending on operations and transaction settings).
- A listener running on an **executor thread** does not automatically inherit the publishing thread's transaction context.
- If a consumer must run only after commit, use `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` when the event is published while an eligible transaction is active.

Example:

~~~java
import org.springframework.stereotype.Component;
import org.springframework.transaction.event.TransactionPhase;
import org.springframework.transaction.event.TransactionalEventListener;

@Component
public class StockAfterCommitListener {

    @TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
    public void onAfterCommit(StockReserved event) {
        System.out.println("Committed reservation: " + event.reservationId());
    }
}
~~~

`@TransactionalEventListener` by default **does not invoke the listener if there is no active transaction**, unless `fallbackExecution=true` is enabled. In Spring Framework 6.1+, transactional listeners normally do not support async dispatch via the multicaster executor; they need the publishing thread to register transaction synchronization properly. To offload post-commit work to another worker, consider **dispatching the work** from the after-commit listener using a mechanism with explicit lifecycle and error handling.

`AFTER_COMMIT` guarantees callback timing relative to the transaction while the application is running normally; it **does not guarantee durable delivery** if the process crashes immediately after commit. For critical business workflows, use a transactional outbox or an appropriate event persistence strategy.

### Trace, Security Context, and Locale

`MDC`, `SecurityContext`, locale, and many contexts rely on `ThreadLocal`. Executors do not transfer all of those values to worker threads by default. Therefore:

1. Put required `correlationId`/`traceId` values into the **payload or message headers** per contract rather than relying solely on `ThreadLocal`.
2. If propagation across an executor is needed, configure a `TaskDecorator` or an appropriate context-propagation utility, along with context cleanup after the task finishes.
3. Do not assume a plain Spring event carries all Spring Integration headers. If the outbound adapter uses `publishPayload=true`, headers do not travel automatically with the POJO.

One symptom of a propagation gap is seeing `traceId` in logs on the publishing thread while logs inside an async listener lack it. This is an execution-context issue, distinct from an event being filtered by type or losing its payload.

## 8. Ordering, Concurrency, and Load Limits

**Synchronous does not automatically mean globally sequential across the application.** One synchronous publisher invokes listeners sequentially on its thread, yet multiple publishers from different request threads can still execute concurrently.

When an executor is enabled:

- **Ordering:** `@Order` can determine listener **dispatch** order, but cannot guarantee **completion** order when tasks run in parallel.
- **Concurrency:** a single listener can be invoked concurrently for multiple events. Shared mutable state must be thread-safe; avoid unsynchronized `ArrayList`/`HashMap` as shared state.
- **Queues:** overly large queues hide congestion and increase latency/memory usage. Overly small queues can trigger `TaskRejectedException` when producers outpace consumers.
- **Idempotency:** events re-sent from another layer or manually retried can cause side effects to run multiple times. Design business handlers with idempotency keys where needed.
- **Shutdown:** when the application stops, define policies for awaiting tasks, timeouts, and handling unfinished work. `waitForTasksToCompleteOnShutdown` only aids graceful shutdown within the process; it does not replace durable message storage.

For example, suppose an email-sending listener takes 2 seconds; if 20 events arrive per second with only two workers, pending tasks pile up rapidly. Increasing thread count without bounding queue size, timeouts, and producer rate merely shifts the bottleneck from the caller to the executor.

## 9. Testing Thread Behavior Reliably

Do not rely solely on `Thread.sleep(...)` to "prove" async execution; scheduler timings vary across environments. Use synchronization primitives such as `CountDownLatch` or `CompletableFuture` to wait for the observed event.

Example test listener recording the thread name:

~~~java
package com.example.stock;

import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicReference;
import org.springframework.context.event.EventListener;
import org.springframework.stereotype.Component;

@Component
public class StockEventProbe {

    private final CountDownLatch observed = new CountDownLatch(1);
    private final AtomicReference<String> listenerThread =
            new AtomicReference<>();

    @EventListener
    public void onEvent(StockReserved event) {
        if ("RSV-TEST".equals(event.reservationId())) {
            listenerThread.set(Thread.currentThread().getName());
            observed.countDown();
        }
    }

    public CountDownLatch observed() {
        return observed;
    }

    public String listenerThread() {
        return listenerThread.get();
    }
}
~~~

In tests, use a fresh Spring context for each scenario:

~~~java
String publisherThread = Thread.currentThread().getName();
publisher.publishEvent(new StockReserved("RSV-TEST"));

assertTrue(probe.observed().await(5, TimeUnit.SECONDS));
assertNotNull(probe.listenerThread());

// Only in the scenario configured with a multicaster executor:
assertTrue(probe.listenerThread().startsWith("spring-event-"));
~~~

These lines form the **body** of a test method with `publisher` and `probe` injected; import `TimeUnit` and JUnit assertions per your project setup. A `CountDownLatch` is single-use, so each test should create a new context/probe or design a safely resettable probe.

When testing, separate:

1. **Default synchronous case:** verify the listener runs on the caller thread without sleeping.
2. **Async multicaster case:** verify the listener runs on `spring-event-*`; await the result with a latch.
3. **`@Async` case:** verify only the annotated listener uses `notification-*`.
4. **`ExecutorChannel` case:** verify the Spring inbound adapter can stay on the publishing thread while the service activator runs on an integration worker.
5. **Error case:** intentionally throw an exception in a listener; verify the caller receives it in sync mode, whereas error handling goes through the async error handler in async setups.
6. **Transaction case:** publish inside a transaction and verify `AFTER_COMMIT` listener timing and rollback behavior.

In async tests, do not assert a **fixed log ordering** between independent listeners. Assert event IDs, payloads, required headers, invocation counts, and completion conditions aligned with business requirements.

## 10. Diagnostic Checklist When Events Are Slow or on the Wrong Thread

| Symptom | Check first | Remediation |
| --- | --- | --- |
| HTTP request slows down after emitting an event | Is a synchronous listener performing slow I/O? | Move the appropriate consumer to `@Async` or `ExecutorChannel` |
| Multicaster executor configured yet a listener still runs on caller thread | Does the listener support async dispatch, especially transactional listeners? | Check `supportsAsyncExecution()` and the listener contract |
| Event published but inbound adapter does not run | Does `eventTypes` match the Spring event/POJO class? | Check runtime type, `publishPayload`, bean registration |
| Async listener fails yet caller sees no exception | Is there an `ErrorHandler` / `AsyncUncaughtExceptionHandler` or integration error flow? | Add logging, metrics, and recovery |
| Worker logs missing `traceId` | Is context stored only in `ThreadLocal`? | Carry metadata in event/message and configure context propagation |
| Events arrive out of order | Multiple executor workers or concurrent publishers? | Design per-key ordering, serialization, or an ordering-capable transport |
| Executor consumes high memory | Unbounded queue or slow consumer? | Bound queue and concurrency; add backpressure and metrics |
| Event processed repeatedly in a row | Does the inbound flow re-emit the same event type to outbound? | Check for loops and separate flow directions |

For production observability, capture `eventId`, `eventType`, `threadName`, publish timestamp, listener start/end timestamps, queue wait time, rejected task count, and processing outcome. Do not rely solely on a "publish succeeded" log.

## 11. Practical Exercises

**Exercise 1 — Measure threads:** Using the `StockReserved` example from Section 3, publish 10 events and record threads in the service, `@EventListener`, and service activator. Explain why all three show the same thread name with the default multicaster and `DirectChannel`.

**Exercise 2 — Switch one boundary:** Replace `inboundStockEvents` with an `ExecutorChannel`. Use a latch to wait for all events to complete; compare worker thread names and completion order. Do not assume 10 events will finish in publish order.

**Exercise 3 — Compare strategies:** Test once enabling `@Async` only on the notification listener, and once enabling an executor on the multicaster. Predict and verify the inbound adapter's thread; describe the impact if the application has many other Spring listeners.

**Exercise 4 — Errors and transactions:** Have a listener throw `IllegalStateException`. Observe the exception path in sync vs. async modes. Then publish an event inside a `@Transactional` method and test an `AFTER_COMMIT` listener on commit/rollback; explain why an outbox is needed if the event affects external services.

**Exercise 5 — Overload:** Restrict the executor to one worker and a small queue, add processing time to the consumer, and increase event publishing rate. Record rejected tasks and define an acceptable backpressure/retry policy.

## References

- [Spring Framework — Standard and Custom Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events).
- [Spring Framework — Asynchronous Listeners](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html#context-functionality-events-async).
- [Spring Framework API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html).
- [Spring Framework — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html).
- [Spring Integration — Spring ApplicationEvent Support](https://docs.spring.io/spring-integration/reference/event.html).
- [Spring Integration — Message Channels](https://docs.spring.io/spring-integration/reference/channel.html).
