# MDC and Correlation ID in Spring Framework Application Events

## 1. MDC and Correlation ID in Threads and Context

When a Spring application handles an HTTP request or a business command, it may publish `OrderPlaced`, `PaymentConfirmed`, or several other application events. To investigate incidents, we need to identify which logs belong to **the same processing flow**. A **correlation ID** such as `REQ-42` links logs across the controller, service, publisher, and listeners.

However, a Spring listener may run on the **same thread** or a **different thread** from the publisher. If you put a correlation ID into MDC on the request thread and then dispatch events through an executor, the worker's MDC **does not automatically contain that ID**. If cleanup is forgotten, a reused worker thread may even retain the ID from a previous task, causing logs to be associated with the wrong request.

Example of correct logs:

```text
10:15:30 INFO  cid=REQ-42 [http-worker] Order placed ORD-42
10:15:30 INFO  cid=REQ-42 [event-worker-1] Notification queued
10:15:30 INFO  cid=REQ-42 [event-worker-2] Audit finished
```

The timestamps and thread names here are illustrative only.

**Learning objectives**: understand MDC/ThreadLocal; distinguish correlation ID from trace ID and event ID; how to propagate and restore MDC via `TaskDecorator`; place correlation ID in event payloads; handle `@EventListener`, `@Async`, transactional listeners, and WebFlux properly; test thread reuse, exceptions, retries, and data protection.

MDC is a context supporting **logging/observability**. It is **not** a transaction context, security context, message broker, or durable business data store.

## 2. What Is MDC (Mapped Diagnostic Context)?

`org.slf4j.MDC` is an API for placing string key/value pairs into the current diagnostic context. A logging backend such as Logback can insert those values into a log pattern. For example, the MDC key `correlationId` is displayed via `%X{correlationId}`.

| SLF4J API | Effect | Caution |
| --- | --- | --- |
| `MDC.put("correlationId", value)` | Sets the value on the current thread | May overwrite a previous value |
| `MDC.get("correlationId")` | Reads the value | Returns `null` if missing |
| `MDC.remove("correlationId")` | Removes only this key | Does not restore a previously overwritten value |
| `MDC.clear()` | Clears the entire MDC map of the current thread | Do not use indiscriminately in nested scopes |
| `MDC.getCopyOfContextMap()` | Captures a copy of the current map | May return `null` |
| `MDC.setContextMap(map)` | Replaces the context map with a copy | Must restore the old state after the task |
| `MDC.putCloseable(key, value)` | Sets the value and removes the key on close | Close removes the key rather than restoring the previous value |

MDC in common backends is **thread-bound**: the request thread and executor workers each have their own maps. Thread pools reuse workers, so missing cleanup causes context leaks. Do not rely on `InheritableThreadLocal` to pass MDC in a pre-existing pool.

**Important backend note:** adding `slf4j-api` only provides the facade. For MDC to appear in logs, you need a runtime backend that supports it, such as Logback, and the proper pattern/JSON logging configuration. A provider without MDC support or without displaying the field may cause `MDC.put(...)` not to produce the expected log output.

## 3. Correlation ID, Request ID, Trace ID, Span ID, Event ID

| ID | What does it represent? | Example |
| --- | --- | --- |
| **Correlation ID** | Multiple steps in the same business flow or request | `REQ-42` for a request and its child events |
| **Request ID** | One specific HTTP request or inbound message | A single API call |
| **Trace ID** | Spans belonging to the same distributed trace | Managed by the tracing system |
| **Span ID** | One operation/unit of work within a trace | A processing segment inside a service |
| **Event ID** | One logical event occurrence | `EVT-200` used for dedupe/retry |
| **Aggregate ID** | A business object | `ORD-42` which may emit multiple events |

Correlation ID and trace ID **can be related**, but they are not always identical. Where OpenTelemetry or Micrometer Tracing is already deployed, leverage the trace/span IDs provided by that system, and only introduce a separate correlation ID when required by business or observability contracts.

One correlation ID can appear across multiple domain events. **Do not use correlation ID as an idempotency key for all events**, because multiple valid events in the same workflow would be mistakenly deduplicated. Event ID identifies **a single event**; aggregate ID identifies **the domain object**.

Log IDs are not access tokens. Never infer authorization from a caller supplying a valid correlation ID.

## 4. Spring Application Events and Thread Execution

### 4.1. Default Synchronous Listeners

`SimpleApplicationEventMulticaster` invokes listeners on the **publisher thread** by default:

```text
http-worker  MDC(cid=REQ-42)
  |
  +--> applicationEventPublisher.publishEvent(OrderPlaced)
          |
          +--> @EventListener A (same http-worker)
          +--> @EventListener B (same http-worker)
  |
  +--> publisher continues
```

Synchronous listeners normally see the publisher's MDC. However, if listener A mutates MDC without restoring it, listener B and the publisher will observe the wrong context. Never assume a listener is allowed to alter global MDC without being responsible for cleanup.

### 4.2. Multicaster with TaskExecutor

When configuring `SimpleApplicationEventMulticaster.setTaskExecutor(...)`, listeners that allow async execution can run on a different worker thread:

```text
http-worker  MDC(cid=REQ-42)
  |
  +--> publishEvent(OrderPlaced)
           |
           +--> queue Runnable
                   |
                   v
              event-worker-1
              MDC does not automatically contain REQ-42
```

Spring does not copy MDC from the publishing thread to the worker by default. As of Spring 6.1, `ApplicationListener.supportsAsyncExecution()` indicates whether a listener is suitable for an async multicaster. Transaction-synchronized listeners are a case that needs the original context when registering synchronization, so setting an executor should not be treated as a way to move all transactional event listeners onto a background thread.

### 4.3. Async Multicaster vs. `@Async`

`@Async @EventListener` can execute via a Spring async proxy, with an executor chosen by `@EnableAsync`, `AsyncConfigurer`, or related configuration. This executor **is not necessarily** the multicaster's executor.

Similarly, `CompletableFuture.supplyAsync(...)` on the common pool, a custom scheduler, or a message broker does not automatically inherit MDC. To propagate it, you must configure **the exact executor receiving the task**, or pass the correlation ID in the data and establish a logging scope at the consumer.

## 5. Correlation ID Should Live in the Event Payload When Needed

A domain/application event can use an immutable record:

```java
public record OrderPlaced(
    String eventId,
    String orderId,
    String correlationId
) {}
```

`OrderPlaced` does not contain `MDC`, `ThreadLocal`, or a Servlet request. If the event is processed asynchronously, replayed after a restart, or sent over a broker, the correlation ID remains part of the message.

Distinguish two roles:

1. **Payload** holds metadata/identity needed long-term or across thread/process boundaries: `eventId`, `orderId`, `correlationId`.
2. **MDC** enriches logs wherever code is currently executing. MDC can be reconstructed from `event.correlationId()`.

Putting the raw `MDC.getCopyOfContextMap()` into the payload is usually wrong: the map may contain internal keys, sensitive data, logging-backend details, or values only valid on the current thread. Pass only fields designed as part of the event contract.

If an order emits two distinct domain events, they can share a correlation ID, but each event must have its own event ID. When retrying **the exact same event**, keep the event ID and correlation ID stable so consumers can deduplicate and trace logs.

## 6. Creating and Cleaning Up MDC at the Request Boundary

A system may accept an ID from an `X-Correlation-ID` header or a message envelope. However, client-supplied values are **untrusted input**:
- Limit length, for example to a maximum of 128 characters.
- Restrict characters to alphanumeric and a few simple symbols such as `-` or `_`.
- Reject newline/control characters to prevent log forging.
- If missing or invalid, generate a new UUID or handle per the API contract.
- Never use passwords, tokens, customer emails, or PII as a correlation ID.

A scope in an imperative service or filter:

```java
Map<String, String> previous = MDC.getCopyOfContextMap();
try {
    MDC.put("correlationId", validatedCorrelationId);
    orderService.placeOrder(command, validatedCorrelationId);
} finally {
    if (previous == null) {
        MDC.clear();
    } else {
        MDC.setContextMap(previous);
    }
}
```

This is an **integration snippet**, requiring `java.util.Map`, `org.slf4j.MDC`, `orderService`, and a validated ID. In a servlet filter, wrap `chain.doFilter(...)` in this scope so every branch, including exceptions, cleans up.

Capture/restore preserves the caller's MDC if the logic is nested inside another scope. Calling only `MDC.remove("correlationId")` is appropriate only when the code knows for sure it owns that key and does not need to restore a previous value.

## 7. MDC TaskDecorator: Snapshot, Install, Restore

`ThreadPoolTaskExecutor` provides `setTaskDecorator(TaskDecorator)`. A safe MDC decorator must:
1. Capture a copy of MDC on the **task-submitting thread**, not after the worker has started running.
2. On the worker, save the `previous` MDC map.
3. Set the `captured` map, or clear if the producer had no context.
4. Execute the task.
5. In `finally`, **restore `previous`** to prevent leaks and protect nested scopes.

Class template:

```java
public final class MdcTaskDecorator implements TaskDecorator {
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
```

This is an **illustrative class** requiring `org.slf4j.MDC`, `java.util.Map`, and `org.springframework.core.task.TaskDecorator`. The standalone program in section 8 includes full imports and Spring configuration.

Crucial point: if task A captures `REQ-A` and the main thread clears MDC right after publishing, the worker still has its copy of `REQ-A`. Conversely, if task B is submitted with no MDC, the decorator must clear context before running B so it does not mistakenly read `REQ-A`.

**Limitations:** this decorator only propagates MDC. It does not copy `EntityManager`, transactions, `SecurityContext`, Reactor Context, or tracing context unless they are captured by an appropriate mechanism. Thread pool reuse does not mean transaction reuse.

## 8. Runnable Java 17+ Example with Spring 6.1, SLF4J, and Logback

The program uses:
- Spring Context 6.1.21 and `SimpleApplicationEventMulticaster`.
- `ThreadPoolTaskExecutor` with pool size = 1 to easily observe thread reuse.
- `MdcTaskDecorator` to capture and restore MDC.
- Two `OrderPlaced` events carrying `REQ-A` and `REQ-B`.
- `CountDownLatch` to wait for listeners to complete instead of `Thread.sleep`.

The program does not use Spring Boot, a web server, or a DB. It demonstrates propagation of **logging context**, not transactions or durable delivery.

Structure:

```text
mdc-spring-events/
├── build.gradle
└── src/main/java/demo/MdcEventsDemo.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.1.21'
    implementation 'org.slf4j:slf4j-api:2.0.13'
    runtimeOnly 'ch.qos.logback:logback-classic:1.5.6'
}

application {
    mainClass = 'demo.MdcEventsDemo'
}
```

`src/main/java/demo/MdcEventsDemo.java`:

```java
package demo;

import java.util.Map;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.slf4j.MDC;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.ApplicationEventMulticaster;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.context.support.AbstractApplicationContext;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class MdcEventsDemo {

    public record OrderPlaced(String orderId, String correlationId) {}

    public static final class MdcTaskDecorator implements TaskDecorator {
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

    public static final class Signal {
        private final CountDownLatch latch = new CountDownLatch(2);

        public void handled() {
            latch.countDown();
        }

        public void awaitBoth() throws InterruptedException {
            if (!latch.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("Events not completed");
            }
        }
    }

    public static final class OrderListener {
        private final Signal signal;

        public OrderListener(Signal signal) {
            this.signal = signal;
        }

        @EventListener
        public void on(OrderPlaced event) {
            try {
                System.out.println(
                    "HANDLE order=" + event.orderId()
                    + " payloadCid=" + event.correlationId()
                    + " mdcCid=" + MDC.get("correlationId")
                );
            } finally {
                signal.handled();
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public Signal signal() {
            return new Signal();
        }

        @Bean
        public OrderListener orderListener(Signal signal) {
            return new OrderListener(signal);
        }

        @Bean
        public ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-worker-");
            executor.setTaskDecorator(new MdcTaskDecorator());
            return executor;
        }

        @Bean(name = AbstractApplicationContext
                .APPLICATION_EVENT_MULTICASTER_BEAN_NAME)
        public ApplicationEventMulticaster applicationEventMulticaster(
                ThreadPoolTaskExecutor eventExecutor) {
            SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
            multicaster.setTaskExecutor(eventExecutor);
            return multicaster;
        }
    }

    public static void main(String[] args) throws Exception {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            MDC.clear();

            try {
                MDC.put("correlationId", "REQ-A");
                context.publishEvent(new OrderPlaced("ORD-1", "REQ-A"));
            } finally {
                MDC.remove("correlationId");
            }

            try {
                MDC.put("correlationId", "REQ-B");
                context.publishEvent(new OrderPlaced("ORD-2", "REQ-B"));
            } finally {
                MDC.remove("correlationId");
            }

            context.getBean(Signal.class).awaitBoth();
            System.out.println("MAIN mdcCid="
                    + MDC.get("correlationId"));
            MDC.clear();
        }
    }
}
```

Command to run with JDK 17+ and Gradle:

```bash
gradle run --quiet
```

**Expected business stdout**:

```text
HANDLE order=ORD-1 payloadCid=REQ-A mdcCid=REQ-A
HANDLE order=ORD-2 payloadCid=REQ-B mdcCid=REQ-B
MAIN mdcCid=null
```

Explanation:

1. Spring finds the bean named `applicationEventMulticaster` and uses it instead of the default multicaster.
2. The executor has a single worker thread; the listener tasks for the two events are queued in publish order.
3. At each `publishEvent(...)`, the decorator captures MDC on the main thread before `finally` removes the key.
4. The worker installs the captured map, so `MDC.get("correlationId")` in the listener matches `event.correlationId()`.
5. When a task finishes, the decorator restores the worker's previous map, preventing `REQ-A` from leaking into `REQ-B`.
6. `Signal.awaitBoth()` waits for both handlers to reach the countdown point; the main thread already cleaned up, so the last line prints `null`.
7. With one listener, one worker, and two sequential publishes, the `HANDLE` lines appear in the order shown. Applications with multiple threads/listeners do not have the same ordering guarantee.

If the environment enables additional framework logging, extra logs may appear on screen alongside the three business lines. The expected output assertion applies only to those three lines.

## 9. Configuring Logback to Display the Correlation ID

In the demo, `System.out` allows exact comparison. Real applications typically use a `Logger` and an MDC pattern or structured logging. Example **optional** `src/main/resources/logback.xml`:

```xml
<configuration>
    <appender name="CONSOLE" class="ch.qos.logback.core.ConsoleAppender">
        <encoder>
            <pattern>%d{HH:mm:ss.SSS} %-5level [%thread] cid=%X{correlationId:-none} %logger{32} - %msg%n</pattern>
        </encoder>
    </appender>
    <root level="INFO">
        <appender-ref ref="CONSOLE"/>
    </root>
</configuration>
```

Integration logging snippet:

```java
private static final Logger log =
    LoggerFactory.getLogger(OrderListener.class);

// Inside the listener:
log.info("Handled order {}", event.orderId());
```

Requires importing `org.slf4j.Logger`, `LoggerFactory`. The pattern reads MDC from **the thread doing the logging**. If the payload has a correlation ID but MDC has not been set yet, the pattern prints `cid=none`. That shows why both event data and a logging scope are needed.

Do not log the full event object when the event contains PII. In JSON logging, standardize a single `correlationId` key and avoid confusing it with `traceId`. In particular, do not push individual correlation IDs as labels on aggregated metrics without controlling cardinality.

## 10. Reconstructing MDC from the Event Payload at the Consumer

An event processed after a restart, from a broker, or on an executor without a decorator cannot inherit the original request's MDC. If the payload carries a correlation ID, create a new logging scope:

```java
@EventListener
public void onOrderPlaced(OrderPlaced event) {
    Map<String, String> previous = MDC.getCopyOfContextMap();
    try {
        MDC.put("correlationId", event.correlationId());
        // Log or execute business logic.
    } finally {
        if (previous == null) {
            MDC.clear();
        } else {
            MDC.setContextMap(previous);
        }
    }
}
```

This is an **integration snippet** with the `OrderPlaced` record, `MDC`, and `Map` already imported. If the event comes from an external source, validate the correlation ID before placing it into MDC. If the handler publishes child events, it usually preserves the correlation ID to link the workflow, issues a new event ID for each new event, and uses a causation ID when needed to track which event triggered the child event.

You can use both a decorator **and** a payload-derived scope: the decorator handles internal context transfer across an executor, while the payload serves as the long-term tracing contract. However, you must define which source takes precedence if the thread's MDC and the event's correlation ID disagree; any mismatch should be logged and investigated rather than silently switching identifiers.

## 11. MDC Is Not a Transaction or Security Context

Copying an MDC `Map<String,String>` does not propagate:
- JDBC connection, JPA `EntityManager`, or Hibernate Session.
- `TransactionSynchronizationManager` / transaction status.
- `SecurityContext` or user permissions.
- Reactor Context and reactive transactions.
- Event durability, retries, and idempotency policies.

Therefore, an async listener may **log the right correlation ID** while executing outside the publisher's transaction. If database operations are needed, the listener must have its own transaction designed for that case.

### @TransactionalEventListener

`@TransactionalEventListener` supports phases `BEFORE_COMMIT`, `AFTER_COMMIT` (default), `AFTER_ROLLBACK`, and `AFTER_COMPLETION`. For imperative transactions, the listener must register synchronization while a transaction is active. In Spring 6.1, transactional listeners are not offloaded to an executor by the multicaster regardless of async support; do not treat `setTaskExecutor(...)` as a way to make transactional event handling "automatically post-commit and asynchronous".

If the handler itself triggers an `@Async` task after commit, MDC and transactions on the new thread must be designed separately. Errors after commit cannot roll back the original transaction.

For events that must be delivered reliably, `ApplicationEventPublisher` + MDC is not enough. The **transactional outbox** pattern records the intent to send an event in the DB within the same transaction, so a worker can retry and consumers can deduplicate by event ID. Correlation ID helps trace across retries; it does not turn an event into a durable message.

## 12. Reactor/WebFlux and Micrometer Context Propagation

In Spring WebFlux, a `Mono`/`Flux` may switch threads multiple times within the same subscription. Reactive transactions reside in the **Reactor Context**, not in MDC ThreadLocal. Calling `MDC.put(...)` before constructing a `Mono` does not guarantee that logging statements in downstream operators will see the same map.

Illustrative Reactor Context:

```java
Mono<String> operation = Mono.deferContextual(ctx -> {
    String cid = ctx.get("correlationId");
    return Mono.just("request=" + cid);
}).contextWrite(c ->
    c.put("correlationId", validatedCorrelationId)
);
```

This is **integration code** requiring Reactor types, a validated ID, and a subscription. Values in the Reactor Context can travel along the reactive chain, but for Logback `%X{correlationId}` to see them, an appropriate bridge between Reactor Context and MDC is needed.

Spring Framework 6.1 provides `ContextPropagatingTaskDecorator`, which uses Micrometer Context Propagation for logging/observation context when tasks switch threads. To use it effectively, you must configure the right dependencies, registries, and accessors; do not assume every MDC key or reactive transaction is transferred automatically. Snapshotting/restoring carries overhead, especially with many short-lived tasks.

If the project already uses Micrometer Observation/Tracing and Reactor automatic context propagation, prefer official observability integrations rather than installing custom global hooks that could pollute MDC between signals. The manual `TaskDecorator` in section 7 solves executor threads; it does **not** automatically solve the entire reactive chain.

## 13. Decision Table by Scenario

| Scenario | Does MDC follow automatically? | Solution |
| --- | --- | --- |
| Synchronous `@EventListener` | Yes on the same thread, if the scope exists | Restore if modifying MDC |
| Async multicaster | No | `TaskDecorator` on the multicaster executor |
| `@Async @EventListener` | Not by default | Decorator on the actual `@Async` executor |
| `CompletableFuture` common pool | No | Pass an executor with a decorator or explicit context |
| Message broker | Not across process boundaries | Correlation ID in header/payload, recreate MDC at consumer |
| Transactional listener | Depends on thread/scope | Keep ID in payload, do not infer transaction from MDC |
| WebFlux/reactive | Not via ThreadLocal alone | Reactor Context + observability bridge |
| Event retry/replay | Does not keep old MDC | Keep event ID and correlation ID stable, create new scope |

## 14. Common Mistakes

1. **Mistaking MDC for a property of the Spring event:** MDC belongs to the execution thread, not the event.
2. **Missing cleanup in the request or worker:** leads to leaking correlation IDs into other requests.
3. **Calling `MDC.clear()` in a nested scope without restoring:** wipes out the caller's MDC.
4. **Recording correlation ID only in MDC, not in the event:** workers after a restart will not know the original ID.
5. **Putting the entire MDC map into the payload:** accidentally exposes internal data or backend-specific keys.
6. **Using correlation ID as event ID:** causes wrong deduplication when one request emits multiple events.
7. **Attaching the decorator to the wrong executor:** multicaster, `@Async`, scheduler, and common pool may differ.
8. **Copying MDC and thinking the transaction follows automatically:** transaction state does not travel with ThreadLocal strings.
9. **Assuming trace ID is always equal to correlation ID:** the two identification schemes have distinct lifecycles/contracts.
10. **Not validating IDs from HTTP headers:** risks log injection and log flooding.
11. **Using `Thread.sleep` to wait for listeners in tests:** unreliable and prone to flakiness.
12. **Not monitoring async exceptions:** logging the right ID does not prove the task succeeded.
13. **Setting MDC arbitrarily inside Reactor operators:** easily lost or leaked when switching threads.
14. **Treating Spring events plus MDC as a durable queue:** a process crash can lose tasks.
15. **Passing authentication tokens in correlation ID:** compromises data security.

## 15. Thorough Testing

### Same Thread

Set MDC `REQ-A`, publish the event synchronously, and assert the listener reads it correctly. Have the handler modify MDC and assert the caller's scope is restored. Also test exception branches.

### Executor Reusing a Single Worker Multiple Times

Publish `REQ-A` and `REQ-B`, verifying each listener reads the ID of its corresponding event. Use a `CountDownLatch` or future to await completion; do not rely on sleep durations.

### Task Without MDC

After the `REQ-A` task, submit a task with no MDC through the same executor. Assert the worker reads `null` for correlation ID; there must be no context leak from the previous task.

### Exception in Task

Have a task throw an exception and then run a subsequent task on the same worker. Assert MDC is restored in `finally` and the error is forwarded to the appropriate monitoring mechanism.

### Different Executor

Create an `@Async` listener with its own executor. Verify that a decorator attached to the multicaster executor does not automatically apply to this pool; design a separate propagation configuration.

### Broker/Retry

Serialize the ID per the message contract, and have the consumer validate it and establish an MDC scope. Retrying the same event keeps `eventId` unchanged; a new event in the same workflow uses a new event ID while optionally keeping the correlation ID.

### Security

Test long correlation IDs or ones containing newlines or control characters. Confirm the validation mechanism rejects or replaces the ID; logs must not contain tokens, emails, or PII against policy.

## 16. Implementation Checklist

- [ ] Correlation ID is generated/validated consistently at the request or message boundary.
- [ ] Correlation ID is not an auth token and contains no personal data.
- [ ] MDC is set in a scoped manner and restored in `finally`.
- [ ] Events requiring deferred or cross-service processing carry an explicit correlation ID.
- [ ] `eventId` and `correlationId` serve distinct purposes; keep both stable when retrying the exact same event.
- [ ] Synchronous `@EventListener` does not pollute the MDC of the caller or other listeners.
- [ ] The actual async executor has a `TaskDecorator` if propagation is needed.
- [ ] The decorator captures on the submitting thread and restores on the worker.
- [ ] Tests cover thread reuse, tasks missing MDC, exceptions, and cleanup.
- [ ] MDC is not confused with transaction, security, or reactive context.
- [ ] With WebFlux, Reactor Context and proper tracing integration are used.
- [ ] Logging patterns or JSON output display the correlation ID without leaking PII.
- [ ] If events must be delivered durably, an outbox/queue and retry/idempotency mechanism exist.

**Remember:** correlation ID is data that links **steps in the same processing flow**; MDC is the mechanism that exposes that data to loggers on the **current thread**. Spring Application Events can process listeners synchronously or asynchronously. When crossing threads, propagate and clean up MDC explicitly; also place the correlation ID in an immutable event payload whenever long-term or cross-process tracing is required.

## References

- [Spring Framework 6.1.21 — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring Framework 6.1.21 — ThreadPoolTaskExecutor](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/scheduling/concurrent/ThreadPoolTaskExecutor.html)
- [Spring Framework 6.1.21 — ApplicationListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring 6.1 — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)
- [SLF4J MDC API](https://www.slf4j.org/apidocs/org/slf4j/MDC.html)
- [Logback MDC Manual](https://logback.qos.ch/manual/mdc.html)
