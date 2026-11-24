# Event Listeners and Observability in Spring Framework

**Observability** is the ability to understand the runtime state of an application from the signals it emits while running: **logs, metrics, and traces**. With Spring Framework Application Events, observability helps answer questions such as:

- Which events were **published**, and which events were actually **processed** by listeners?
- Which listeners are slow, failing frequently, timing out, or have stopped receiving events?
- When a request triggers multiple listeners, can you trace from the request to the resulting work?
- Does a listener execute **synchronously** or **asynchronously**, on which thread, and with which trace context?
- Was the event processed **before or after commit**, and did the transaction actually succeed?

An important point in **Spring Framework 6.2**: **Spring does not automatically create a Micrometer Observation for each `@EventListener` invocation**. According to the official documentation, Spring does not instrument these invocations out of the box because of the semantics of Spring application events: by default they run synchronously on the same thread as the publisher and are already within the current call context. If you want to measure **individual listeners**, actively instrument the listener work (or a wrapper layer with a clear contract); if using async, manage context propagation and observe the asynchronous outcome.

This article focuses on **ApplicationEventPublisher**, **`@EventListener`**, **`@TransactionalEventListener`**, **Micrometer Observation**, and **context propagation**, without conflating them with the instrumentation mechanisms of Kafka/JMS or durable queues.

## 1. Which stages need to be observed?

Consider a service that publishes `OrderPlaced` and two listeners:

```text
HTTP request / command
         |
         v
OrderService.placeOrder()
         |
         +-- write data in transaction T1
         |
         +-- ApplicationEventPublisher.publishEvent(OrderPlaced)
                 |
                 +-- AuditListener         (usually runs synchronously)
                 |
                 +-- EmailListener         (may run @Async / after commit)
         |
         +-- COMMIT or ROLLBACK transaction T1
```

In an event-driven system, distinguish **four moments** that are often conflated:

| Concept | Meaning | Must not be inferred |
| --- | --- | --- |
| **Published** | Code called publish; the multicaster was asked to dispatch the event | All listeners have finished |
| **Listener started** | A listener has started processing the event | The listener will succeed |
| **Listener completed** | A listener has finished, either succeeding or failing | The business transaction has committed |
| **Transaction committed** | The transaction manager committed the source changes | Webhooks, emails, or async listeners have finished processing |

If there is a broker/outbox, there is a fifth state: **message delivered/acknowledged**. Spring application events are strictly an in-process communication mechanism; they do not guarantee persistence, retries, or exactly-once delivery on their own.

### Signals to design

- **Logs:** event type, event ID/correlation ID, listener, transaction phase, attempt, outcome, and exception root cause. All sensitive data must be stripped or masked.
- **Metrics:** counts of started/succeeded/failed executions, processing duration, executor queue depth (if any), rejected task count, retries, and outbox processing lag.
- **Traces:** the use case span, data operations, and child spans for listener work worth observing. Trace context reveals causality, but only when context is propagated across the appropriate boundaries.

There is no need to emit all three signals for **every** trivial event. Observability has CPU, memory allocation, storage, and cardinality costs. Instrument critical listeners or those with specific SLAs.

## 2. Why doesn't Spring automatically create an Observation for `@EventListener`?

Within a Spring `ApplicationContext`, `ApplicationEventPublisher.publishEvent(...)` forwards the event to the `ApplicationEventMulticaster`. With the default configuration, `SimpleApplicationEventMulticaster` invokes listeners **synchronously on the publisher thread**. Therefore, a listener called from a request typically runs within the same call stack and request context.

```text
Request span (already exists from HTTP instrumentation)
  |
  +-- OrderService
        |
        +-- publishEvent(...)
              +-- @EventListener A   [same thread]
              +-- @EventListener B   [same thread]
```

This **does not automatically create a new span** per listener; it only means the listener can run within the active observation/trace scope on that thread. If you need to identify "listener A took 200 ms, listener B took 10 ms", create an explicit observation.

According to the **Spring Framework Observability** documentation, Spring does not provide Observations for `@EventListener` invocations as default instrumentation. Do not enable Spring Boot Actuator and assume an `application.event.listener` metric will automatically appear for all listeners.

When using a custom multicaster with a `TaskExecutor`, or annotating a listener with `@Async`, work may run on a different thread; in that case, the publisher's **ThreadLocal, MDC, and observation scope** generally do not appear automatically on the listener side. Proper context propagation must be configured.

## 3. Micrometer Observation: concepts and lifecycle

Micrometer provides `Observation` and `ObservationRegistry`:

- **`Observation`** represents an observed task, such as handling an event in a listener.
- **`ObservationRegistry`** holds the configuration and `ObservationHandler` instances that receive callbacks when an observation starts, errors, stops, or opens/closes a scope.
- **`ObservationHandler`** can turn the observation lifecycle into metrics, spans, logs, or other measurement work, depending on the configured system.
- **`Observation.Scope`** sets the observation scope on the current thread so nested steps can correlate with the active context.

Typical manual lifecycle:

```java
Observation observation = Observation
        .createNotStarted("application.event.listener", registry)
        .lowCardinalityKeyValue("event.type", "OrderPlaced")
        .lowCardinalityKeyValue("listener", "BillingProjection")
        .start();

try (Observation.Scope scope = observation.openScope()) {
    handleBusinessEvent(event);
} catch (RuntimeException | Error ex) {
    observation.error(ex);
    throw ex;
} finally {
    observation.stop();
}
```

This is an **integration illustration snippet**, assuming `registry`, `event`, and `handleBusinessEvent` are provided by the application. Important points:

1. Create the observation with a stable name and add keys before `start()` whenever possible.
2. **Open a scope** around the actual work to be measured; close the scope when finished.
3. On error, call `observation.error(ex)` so handlers know the outcome; **rethrow the original exception** if the error must propagate.
4. Always call `stop()` in `finally`; otherwise completion timing measurements will be missing.
5. Merely creating an observation/registry **does not mean metrics/traces are exported**. Appropriate `ObservationHandler`s and a configured backend/exporter are required.

You can use the `observation.observe(Runnable)`/`observe(Supplier)` helpers to automatically handle start, scope, error, and stop. The manual approach is useful when you want to see each lifecycle step explicitly.

### Low cardinality and high cardinality

Micrometer distinguishes:

| Key | Example | Recommendation |
| --- | --- | --- |
| **Low cardinality** | `event.type=OrderPlaced`, `listener=BillingProjection`, `outcome=success/error` | Suitable as metric labels when the value set is bounded |
| **High cardinality** | `event.id=evt-23f...`, `order.id=ORD-19283`, `correlation.id=...` | Use only for traces or logs needing correlation; do **not** create a metric time series per ID |
| Must not be tagged | Emails, tokens, customer addresses, full payloads, payment details | Security/PII risk and unbounded cardinality |

Do not use exception names containing dynamic data or error message strings as metric tags. For errors, you can attach a **bounded error group** (e.g., `validation`, `database`, `external`); specific exceptions and stack traces belong in logs/traces. An `event.type` taken directly from arbitrary user strings can also cause unbounded cardinality, so keep event type names within a controlled list.

## 4. Runnable Java 17+ example: recording an observation per listener

The simple example below illustrates a Spring `@EventListener` with **Micrometer Observation** without requiring Spring Boot or a tracing backend. To produce easily verifiable output, the program registers an `ObservationHandler` that counts how many observations **finished** and **errored**. This handler is **not a production metrics/traces exporter**; it proves that the observation lifecycle executed.

Two events are published:

- `PaymentCaptured(41)`: listener succeeds.
- `PaymentCaptured(42)`: listener intentionally throws an error; the observation records the error and the exception still propagates to the publisher because of the default synchronous multicaster.

### 4.1. Structure

```text
event-observation-demo/
├── pom.xml
└── src/main/java/EventObservationDemo.java
```

### 4.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-observation-demo</artifactId>
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
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-observation</artifactId>
            <version>1.14.9</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>EventObservationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

### 4.3. `src/main/java/EventObservationDemo.java`

```java
import java.util.concurrent.atomic.AtomicInteger;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.EventListener;

public class EventObservationDemo {

    public record PaymentCaptured(long id) {}

    // Small handler to observe lifecycle; does not export real metrics/traces.
    public static final class CountingHandler
            implements ObservationHandler<Observation.Context> {

        private final AtomicInteger finished = new AtomicInteger();
        private final AtomicInteger errors = new AtomicInteger();

        @Override
        public boolean supportsContext(Observation.Context context) {
            return true;
        }

        @Override
        public void onError(Observation.Context context) {
            errors.incrementAndGet();
        }

        @Override
        public void onStop(Observation.Context context) {
            finished.incrementAndGet();
        }

        public int finishedCount() {
            return finished.get();
        }

        public int errorCount() {
            return errors.get();
        }
    }

    public static final class PaymentListener {
        private final ObservationRegistry registry;

        public PaymentListener(ObservationRegistry registry) {
            this.registry = registry;
        }

        @EventListener
        public void onPaymentCaptured(PaymentCaptured event) {
            Observation observation = Observation
                    .createNotStarted("application.event.listener", registry)
                    .lowCardinalityKeyValue("event.type", "PaymentCaptured")
                    .lowCardinalityKeyValue("listener", "PaymentListener")
                    .highCardinalityKeyValue(
                            "event.id", Long.toString(event.id()))
                    .start();

            try (Observation.Scope scope = observation.openScope()) {
                System.out.println("listener: id=" + event.id());

                if (event.id() == 42L) {
                    throw new IllegalStateException("gateway unavailable");
                }
            } catch (RuntimeException | Error ex) {
                observation.error(ex);
                throw ex;  // Do not swallow the error, preserve the root cause.
            } finally {
                observation.stop();
            }
        }
    }

    public static void main(String[] args) {
        ObservationRegistry registry = ObservationRegistry.create();
        CountingHandler counter = new CountingHandler();
        registry.observationConfig().observationHandler(counter);

        try (var context = new AnnotationConfigApplicationContext()) {
            context.registerBean(
                    PaymentListener.class,
                    () -> new PaymentListener(registry));
            context.refresh();

            System.out.println("publisher: id=41");
            context.publishEvent(new PaymentCaptured(41L));

            System.out.println("publisher: id=42");
            try {
                context.publishEvent(new PaymentCaptured(42L));
            } catch (IllegalStateException ex) {
                System.out.println("caller: " + ex.getMessage());
            }

            System.out.println("observation: finished="
                    + counter.finishedCount()
                    + " errors=" + counter.errorCount());
        }
    }
}
```

Run with Java 17+ and Maven from the directory containing `pom.xml` (dependencies will be downloaded on the first run):

```bash
mvn -q compile exec:java
```

Lines printed by the program, in order (excluding framework/Maven logs):

```text
publisher: id=41
listener: id=41
publisher: id=42
listener: id=42
caller: gateway unavailable
observation: finished=2 errors=1
```

**Why is the output exactly like this?**

1. `context.registerBean(...)` registers the listener bean before `refresh()`; Spring detects the `@EventListener` method.
2. For `id=41`, the observation starts, the scope opens, the listener prints the processing line, the scope closes, and the observation stops; the handler increments `finished`.
3. For `id=42`, the listener prints the line and then throws `IllegalStateException`. The catch block calls `observation.error(ex)`, the handler increments `errors`, and then the **same exception** is rethrown. The finally block calls `stop()`, and the handler increments `finished`.
4. The default multicaster is synchronous, so the publisher catches the exception from the `id=42` listener. The result `finished=2` and `errors=1` is the count of observations that finished and encountered errors, not database record counts.
5. The program does not integrate a meter registry, tracing bridge, or exporter, so it **does not claim to have produced Prometheus metrics or OpenTelemetry spans**. In production applications, the registry is typically managed by Spring Boot and wired to the corresponding handlers.

The example does not use `@Async` and does not open a transaction. Demonstrating a synchronous error here is **not** a rollback test. If you need to prove rollback, you must add a transaction manager and query the database after the transaction completes.

## 5. Spring Boot Actuator: from Observation to real metrics and traces

In a Spring Boot application with `spring-boot-starter-actuator`, Micrometer infrastructure is typically auto-configured based on dependencies and configuration. You can inject `ObservationRegistry` into services/listeners to instrument work; observations only become **useful metrics/traces** when appropriate `ObservationHandler`s, backends, and exporters are present.

An implementation example:

```java
@Component
public class InvoiceProjectionListener {

    private final ObservationRegistry registry;
    private final InvoiceProjectionService projectionService;

    public InvoiceProjectionListener(
            ObservationRegistry registry,
            InvoiceProjectionService projectionService) {
        this.registry = registry;
        this.projectionService = projectionService;
    }

    @EventListener
    public void onInvoiceIssued(InvoiceIssued event) {
        Observation.createNotStarted(
                        "application.event.listener", registry)
                .lowCardinalityKeyValue("event.type", "InvoiceIssued")
                .lowCardinalityKeyValue("listener", "InvoiceProjection")
                .highCardinalityKeyValue("event.id", event.eventId())
                .observe(() -> projectionService.update(event));
    }
}
```

This is an **illustrative integration snippet**, requiring the `InvoiceIssued`, `InvoiceProjectionService` types and imports for `@Component`, `@EventListener`, `Observation`, `ObservationRegistry`. The `observe(...)` method manages start/scope/error/stop automatically around the measured block and continues to throw the listener's error if processing fails.

Depending on the application and exporter, data can flow to:

- **Micrometer MeterRegistry + Prometheus:** observe listener latency, rate, and errors by low-cardinality keys.
- **Micrometer Tracing / OpenTelemetry:** record spans and link the path from the request to the listener work.
- **Structured logging / MDC:** correlation ID, trace ID, span ID, event ID; avoid printing payloads containing sensitive data.

Simply adding Actuator does not automatically produce `application.event.listener` meters. **There must be an observation created by the application** or specific instrumentation providing it. Before building dashboards, verify the actual metric names after the exporter converts dots/names according to backend conventions.

**`@Observed`** can help instrument methods in applications configured with appropriate Micrometer annotation instrumentation and AOP, though it does not cover every listener by default. In Spring Boot, depending on the version, enabling `management.observations.annotations.enabled=true` and having AspectJ/AOP dependencies may be required. When a method already has other instrumentation, be careful to avoid creating **duplicate spans/metrics**.

## 6. Synchronous vs. asynchronous: why can trace context be lost?

### 6.1. Synchronous listeners

With the default `SimpleApplicationEventMulticaster`:

```text
Thread HTTP-1
  +-- Request Observation / Trace scope
        +-- OrderService
              +-- publishEvent(OrderPlaced)
                    +-- Listener A
                    +-- Listener B
```

The listener runs on the same thread and therefore generally sees the publisher's ThreadLocal logging/observation context. If you instrument an observation inside the listener and open a scope, that observation can be organized as a child operation in the trace, **provided a tracing handler is configured**.

However, *same thread* does not mean a new span is created automatically. If a listener takes a long time and is not instrumented separately, the trace may only show the duration on the outer span. To distinguish the latency of individual listeners, measure them explicitly.

### 6.2. Listeners using `@Async`

Example:

```java
@Async("eventExecutor")
@EventListener
public void handle(OrderPlaced event) {
    // May run on an executor thread.
}
```

This is **illustrative code**, assuming `eventExecutor` is configured, `@EnableAsync` is enabled, and `OrderPlaced` exists.

`@Async` typically moves execution to another thread. ThreadLocals such as the current observation, trace scope, or MDC **do not automatically propagate across every executor**. Common symptoms: logs inside the listener have an empty trace ID or one from a different request; manually created spans no longer maintain the expected parent–child relationship.

Spring Framework recommends using **Micrometer Context Propagation** and `ContextPropagatingTaskDecorator` to copy/contextualize context when a task is submitted:

```java
@Configuration
@EnableAsync
class AsyncEventConfig {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("event-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        executor.initialize();
        return executor;
    }
}
```

This is an **integration configuration snippet**, not part of the runnable demo in section 4. It requires imports for `@Configuration`, `@EnableAsync`, `@Bean`, `ThreadPoolTaskExecutor`, `ContextPropagatingTaskDecorator`, and the `io.micrometer:context-propagation` dependency. In Spring Boot, verify the presence of Micrometer Observation/Tracing and the corresponding `ThreadLocalAccessor`s; the task decorator cannot create traces on its own if the application has no tracing system.

A few notes:

- Wrapping the task at **submission time** is what transfers context from the publisher thread to the worker. If the event is sent across another broker/process, context must be passed via message headers/carriers; an in-JVM task decorator does not work across processes.
- Any new scope on the worker thread must be properly closed/restored so it does not **leak trace context** to another request in the thread pool.
- For certain executors and task scheduling mechanisms, the decorator introduces overhead; enable it only for tasks needing correlation and verify actual cost.
- Using `@Async` **does not guarantee the listener succeeds before the publisher returns**. An exception on the worker does not automatically roll back the transaction on the publisher thread.

### 6.3. Custom multicaster with TaskExecutor

You can configure `SimpleApplicationEventMulticaster` with a dedicated executor:

```java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster eventMulticaster(
        @Qualifier("eventExecutor") TaskExecutor executor) {
    SimpleApplicationEventMulticaster multicaster =
            new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
```

This is an **illustrative integration snippet**, requiring the appropriate imports and the `eventExecutor` bean above; the name `applicationEventMulticaster` is used by Spring to look up a custom-configured multicaster. Do not conclude that every listener will run on the executor: listeners that do not support async execution by contract (notably transaction-bound ones) may still run on the publisher thread.

Configuring a global multicaster can alter exception propagation and completion ordering. Evaluate mandatory synchronous listeners, best-effort listeners, and transactional listeners individually rather than switching everything to async just to reduce response latency.

### 6.4. Reactive context is not like ThreadLocal

In WebFlux/Reactor systems, a reactive pipeline's context is bound to the **subscription**, not automatically tied to a ThreadLocal on a specific thread. With Spring Boot, automatic ThreadLocal restoration in reactive operators depends on the version and configuration, such as `spring.reactor.context-propagation=auto` in supported versions.

Do not assume `publishOn(...)` or `subscribeOn(...)` always drops the Reactor Context: the Reactor Context can travel with the subscription across appropriate operators. However, if you leave the chain, create a separate subscription without inheriting context, or call an API that only knows about ThreadLocal, correlation can be lost.

For **reactive transaction events**, binding events to transactions also requires the proper `TransactionalEventPublisher`/`TransactionContext` per Spring's contract; context propagation for logging/tracing **does not replace** transaction propagation.

## 7. Observability and transaction lifecycle

An event can be published inside an uncommitted transaction:

```text
T1 starts
  |
  +-- INSERT order
  |
  +-- publishEvent(OrderPlaced)
  |     +-- @EventListener runs immediately (synchronous by default)
  |
  +-- commit T1 succeeds / rollback T1
  |
  +-- @TransactionalEventListener(AFTER_COMMIT) runs only on commit
```

Therefore, signals must be named accurately:

- `event.published`: code published the event; **does not mean transaction committed**.
- `listener.executed`: the listener ran; **does not mean all side effects succeeded**.
- `transaction.committed`: the transaction committed; must be based on the transaction manager/database, not merely synchronous callbacks.
- `notification.sent`: an external service confirmed delivery; a completely different state from the commit outcome.

Transaction-bound listener:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlaced event) {
    Observation.createNotStarted(
                    "application.event.after_commit", registry)
            .lowCardinalityKeyValue("event.type", "OrderPlaced")
            .lowCardinalityKeyValue("listener", "Notification")
            .observe(() -> notificationService.send(event));
}
```

This is **illustrative integration code**, not standalone. `registry`, `notificationService`, and `OrderPlaced` are application dependencies. `@TransactionalEventListener` defaults to `fallbackExecution = false`: if the event is published **outside an appropriate transaction**, the listener is skipped, and therefore **no observation will be created** in this method.

If an `AFTER_COMMIT` listener fails, the source transaction **has already committed** and cannot be rolled back by the listener's exception. A trace containing an error span is not sufficient to claim the order was rolled back; you must check the outcome of the original transaction. If post-commit processing needs to write to the database, explicitly start a **new** transaction (e.g., a `REQUIRES_NEW` service in an imperative flow) rather than relying on transaction resources that may still be present during the callback.

When combining `@Async` with an after-commit listener, the start of the async task and actual execution can be separated in time. Measure **scheduled**, **started**, and **completed** milestones instead of using the publish timestamp as a definitive processing latency. Some early event/bean lifecycle cases also require listener registration before context refresh; an unregistered listener cannot be measured.

## 8. Naming Observations and choosing meaningful metrics

A maintainable convention:

| Observation/metric idea | Meaning | Suggested low-cardinality tags |
| --- | --- | --- |
| `application.event.listener` | Execution time of one listener processing invocation | `event.type`, `listener`, `outcome` or `error.group` |
| `application.event.publish` | Duration of the publisher call | `event.type`, `publisher` |
| `application.event.retry` | Each retry attempt | `event.type`, `consumer`, `result` |
| `application.event.backlog` | Queue/buffer length or pending outbox size | `queue.name` or `event.group` with a bounded set of names |

These are **application-suggested names**, not observations created by Spring Framework by default.

In particular:

1. **Publish duration is not always processing duration.** With a synchronous multicaster, they can overlap; with async, publish may only measure enqueuing the task into the executor.
2. **Do not blindly sum the durations of parallel listeners to get request latency.** Use traces or the critical path; the sum of durations is total processing effort, not wall-clock elapsed time.
3. **Do not measure averages alone.** For SLOs, inspect histograms/percentiles when supported by the backend: p95, p99, and error counts by type, alongside throughput.
4. **Do not group metrics by `eventId` or `orderId`**. That creates a number of time series proportional to every message.
5. **Do not let instrumentation throw exceptions that mask business errors.** Custom reporters need fail-safe mechanisms, timeout limits, and appropriate error handling; if rollback is required due to a business error, preserve the original exception.
6. **Measure drops/rejections and queue latency** when using an executor. A submitted task does not mean the listener has started, and a growing queue backlog can be an early warning sign of an incident.

In practice, select a small set of metrics that support operational decisions: listener latency, error rate, backlog, retry exhaustion, and lag from commit to reaction completion.

## 9. Logging and correlation IDs

Logs should answer "where did this event go" without having to expose sensitive payloads.

Structured log example (values are illustrative only, not output from the demo):

```text
level=INFO event.type=OrderPlaced event.id=evt-2f1
listener=InvoiceProjection phase=AFTER_COMMIT
outcome=SUCCESS elapsed.ms=18 trace.id=abc123

level=ERROR event.type=OrderPlaced event.id=evt-2f2
listener=Notification phase=AFTER_COMMIT
outcome=FAILED attempt=3 error.type=ExternalTimeout
trace.id=abc124
```

Recommendations:

- Put `eventId`/`correlationId` in the **event envelope** or payload when the event may be persisted/replayed, so tracing does not depend solely on ThreadLocal.
- With Spring Boot + Micrometer Tracing, trace/span IDs can be added to logs via configured logging integration, but **not every application enables tracing**.
- When MDC is needed in async, use context propagation as in section 6 or pass identifiers in the message; do not rely on `InheritableThreadLocal` to propagate across thread pools.
- Log the exception root cause at the layer responsible for handling the error; avoid logging the same stack trace repeatedly across multiple layers.
- Do not log tokens, passwords, customer emails, or entire event payloads by default.

**A trace ID does not replace an event ID.** A trace may only cover a single request/process; an event may be retried in a different trace. A stable event ID helps link attempts, handle duplicates, and investigate end-to-end flows.

## 10. Observable error handling and retries

With a synchronous `@EventListener`, an exception from the listener **can propagate to the publisher by default** and affect an open transaction. If a custom `SimpleApplicationEventMulticaster` has an `ErrorHandler` or executor, behavior can change. Do not look at logs alone and conclude the publisher received the error.

With `@Async`, listener exceptions are not automatically thrown back to the publisher. For `void` async methods, configure an appropriate uncaught exception handler; for `Future`/`CompletableFuture`, the caller managing the result must observe completion/error per the API contract. Instrumentation must wrap the **execution body on the worker**, not only the submission on the publisher.

When retrying:

```text
eventId = evt-101
  |
  +-- attempt=1 -> FAILED timeout
  |
  +-- attempt=2 -> FAILED timeout
  |
  +-- attempt=3 -> SUCCESS
```

Measure **attempt counts**, per-attempt errors, and the **final outcome** separately; do not record three failures as three independent logical events. Use a stable event ID to correlate them. If processing has non-idempotent side effects, the consumer must have an idempotency/inbox strategy before retrying.

If you need to guarantee events are not lost when a process crashes, consider a **Transactional Outbox**: write to the outbox in the same source transaction, then have a worker pull events and retry with persisted state. `ApplicationEventPublisher` itself does not guarantee persistence or replay; adding Micrometer Observation **does not** turn it into a message broker.

When a system crashes abruptly, there may be no observation **stop**, no final span, or no final log. This is why metrics/traces are not a durable business data store.

## 11. Common pitfalls

**Pitfall 1 — "Actuator is enabled, so every `@EventListener` automatically has a span".**  
Incorrect as of Spring Framework 6.2. Corresponding instrumentation is required: observations created manually in the listener or a separately configured mechanism. Only with handlers/exporters will real metrics/tracing data be produced.

**Pitfall 2 — Measuring `publishEvent` and calling that measurement the processing latency of all listeners.**  
Wrong when using `@Async` or a multicaster with an executor. Measure publish, queue wait, listener processing, and completion separately when the architecture requires it.

**Pitfall 3 — Putting `eventId` into a metric tag.**  
Cardinality grows with the number of events, putting pressure on the metrics system. Use high-cardinality keys in traces/logs, and keep metrics to bounded tag sets.

**Pitfall 4 — Using a thread pool without propagating trace context.**  
Worker logs lack correlation. Configure `ContextPropagatingTaskDecorator` and Micrometer Context Propagation appropriately, or pass the correlation ID via the event.

**Pitfall 5 — Confusing a post-commit listener error with a rollback.**  
A committed transaction cannot be rolled back because an `AFTER_COMMIT` callback failed. Record the side-effect state separately, and apply appropriate retries or compensation.

**Pitfall 6 — Not calling `stop()` on exception.**  
The observation may lack an end time, causing inaccurate or missing data. Use `observe(...)` or `try/finally` across all paths.

**Pitfall 7 — Catching an exception just to increment a counter and then swallowing it.**  
If the listener is a mandatory step in the transaction, business behavior is altered. Call `observation.error(ex)` and propagate the error appropriately.

**Pitfall 8 — Creating duplicate metrics/traces.**  
A manual span, `@Observed`, and automatic instrumentation at another layer measuring the same operation without clear boundaries can distort reports and waste resources. Define who owns which observation.

**Pitfall 9 — Claiming an event was processed because the publisher saw no exception.**  
With async, the listener may still be queued, running, or fail later. Observe actual completion/acknowledgement.

**Pitfall 10 — Treating logs/traces as the source of truth for transactions.**  
Metrics/traces can be sampled, dropped, or cut off mid-flight. Cross-check database transaction outcomes, outbox/inbox states, and business data during investigations.

## 12. How to test listener observability

Test both **behavior** and **telemetry**, rather than merely checking that a logging method was called:

| Scenario | Business verification | Observability verification |
| --- | --- | --- |
| Synchronous listener succeeds | Processes exactly once per contract | Observation starts/stops, no error |
| Synchronous listener throws | Exception propagates along the expected path, transaction rolls back if policy requires | Observation marks error and still stops |
| `@Async` listener | Publisher does not wait if async contract applies; completion tracked separately | Correlation ID/trace propagated properly, latency measured on worker |
| `AFTER_COMMIT` listener | Runs only after commit; does not run on rollback | Observation reflects the right phase, error not conflated with transaction rollback |
| Event not received by listener | No side effects; investigate type/registration/transaction cause | Do not report listener success just because publisher emitted the event |
| Reporter/telemetry outage | Business rules remain intact | Measurement code does not accidentally swallow or alter the original error |
| Multiple retries | Idempotent consumer, no duplicate side effects | Attempts and final outcome clearly distinguished |

With Micrometer, you can use `TestObservationRegistry` in tests by adding the `micrometer-observation-test` dependency, or configure a collecting `ObservationHandler` like the example in section 4. To test real metrics, use `SimpleMeterRegistry` and `DefaultMeterObservationHandler`; to test traces, configure a corresponding tracer/test exporter.

For asynchronous code, do not use `Thread.sleep(...)` to guess when work has finished. Use latches, `CompletableFuture`, test executors, or appropriate testing utilities. For transactions, query the database on a separate connection/transaction after the flow ends to avoid misreading uncommitted data.

A QA checklist before deploying to production:

1. **Signal ownership:** does the observer live in the producer, listener, executor, or outbox worker? Is there duplicate measurement?
2. **Lifecycle:** are start/stop/error covered across all paths (success, throw, cancellation, retry)?
3. **Cardinality:** are only low-cardinality tags used for metrics, and high-cardinality IDs reserved for traces/logs?
4. **Correlation:** do async/thread pool/reactive/broker paths propagate context and `eventId` properly?
5. **Outcome:** are published, started, completed, committed, and delivered distinguished?
6. **Security:** are logs/traces free of secrets, PII, or raw payloads?
7. **Reliability:** does a telemetry outage avoid hiding business errors, and do critical events have appropriate retry/outbox mechanisms?
8. **Dashboards/alerts:** are there realistic thresholds for error rate, p95 latency, queue lag, and backlog?

## 13. Self-check

**1. Does Spring Framework 6.2 automatically create a separate Observation for every `@EventListener`?**  
No. Manual instrumentation or a specific mechanism added by the application is required. Synchronous listeners generally inherit the publisher's context, but do not automatically get a child span.

**2. Why might an `@Async` listener lack a trace ID even though the publisher has a trace?**  
Because current observation/MDC state is typically stored in ThreadLocal; when work moves to an executor thread, context propagation or correlation via the event is needed.

**3. Why should `eventId` not be placed in a low-cardinality key?**  
Each event can have a distinct ID, causing metric time series to explode. IDs are better suited for high-cardinality trace keys or log fields.

**4. Why can an observation be created and still produce no Prometheus metrics?**  
Because `ObservationRegistry` needs a handler that creates meters along with the appropriate registry/exporter; the demo only uses `CountingHandler` and does not produce real metrics.

**5. If an `AFTER_COMMIT` listener fails during processing, does the source transaction roll back?**  
No; the commit has already occurred. Track the state of secondary work separately and use a retry/outbox mechanism if it is critical.

**6. Can `publishEvent` latency be used as the total duration of an async listener?**  
No. The publisher may only be submitting a task. Measure queue wait, execution duration, and completion separately.

**7. When a listener fails, is calling `observation.error(ex)` enough?**  
Not yet. Exception propagation must still follow the business contract (if rollback is needed) and `stop()` must always be called. Recording an observation does not replace error handling.

## 14. Official documentation

- [Spring Framework 6.2 — Observability Support, section Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html)
- [Spring Framework 6.2 — Application Events and multicaster](https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
- [Spring Boot 3.4 — Observability, custom observations and context propagation](https://docs.spring.io/spring-boot/3.4/reference/actuator/observability.html)
- [Micrometer — Observation Components and ObservationHandler](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Observation Instrumentation](https://docs.micrometer.io/micrometer/reference/observation/instrumenting.html)

