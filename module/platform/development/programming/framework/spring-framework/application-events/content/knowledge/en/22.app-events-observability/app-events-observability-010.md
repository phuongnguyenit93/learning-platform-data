# Linking Events with Trace and Correlation IDs in Spring Application Events

## 1. Goal: tracing an event from publisher to consumer

In a Spring application, a request can mutate data, call `ApplicationEventPublisher.publishEvent(...)`, trigger multiple `@EventListener`s, and emit further events. When these steps cross multiple threads, modules, or services, plain logs are usually insufficient to answer:

- Which request or business action caused the event?
- Which specific event is being processed? Is it a redelivery (retry/replay)?
- Which listener emitted the next event, and why?
- Was the event handled within the same distributed trace, or did it split into a separate trace?
- If the listener runs on an executor, did tracing and logging metadata follow along?
- When an error occurs, which logs, spans, metrics, and event records should we inspect?

**Linking events with trace and correlation IDs** is the design of identifiers and context propagation to connect **business causality** with **technical execution paths**. The two complement each other, yet are not synonymous.

A simple flow:

~~~text
HTTP POST /orders
  |
  | traceId = 4bf92f3577b34da6a3ce929d0e0e4736
  | spanId  = 00f067aa0ba902b7
  | correlationId = order-flow-42
  v
OrderService
  |
  | publish OrderPlaced(
  |   eventId=evt-100,
  |   orderId=ORD-7,
  |   correlationId=order-flow-42,
  |   causationId=cmd-25)
  v
@EventListener OrderAuditListener
  |
  | observation/span: handle OrderPlaced
  | same correlationId, may be a child span
  v
OrderAuditRecorded(
  eventId=evt-101,
  correlationId=order-flow-42,
  causationId=evt-100)
~~~

`correlationId` in the example ties together **steps belonging to the same business journey**. `traceId` links technical spans collected by the tracing system. `eventId` distinguishes individual event occurrences; `causationId` identifies the direct trigger of a new event.

**Spring Application Events does not automatically generate all of the business correlation fields above.** These are values designed into the payload/envelope or metadata by your system, then deliberately surfaced in logs and spans per application conventions.

## 2. Distinguishing trace ID, span ID, correlation ID, event ID

| Identifier | Question answered | Characteristics |
| --- | --- | --- |
| **`traceId`** | Which technical steps belong to the same distributed trace? | Usually assigned by the tracing SDK; many spans share one trace ID. |
| **`spanId`** | Which specific operation is this within the trace? | Each span has its own ID; child spans usually keep the trace ID and get a new span ID. |
| **`correlationId`** | Which events/requests belong to the same business journey or transaction? | System-defined; can span multiple traces, retries, or long durations. |
| **`eventId`** | Which event occurrence is this? | Used for audit, replay, and idempotency/dedup when events are stored/redelivered. |
| **`causationId`** | Which event/command directly produced this event? | Useful for building an event causality graph. |
| **`aggregateId`** | Which order/business entity does this event belong to? | E.g., `orderId`; one aggregate has many events. |
| **`requestId`** | Which inbound system request is this? | May equal `correlationId` in short flows, though not required. |

### Trace ID is not a business correlation ID

A trace typically describes a continuous execution path across spans. Meanwhile, an order-fulfillment workflow spanning hours can pass through an order-creation request, a payment process, retry workers, and shipping callbacks. Those activities may be recorded as **multiple distinct traces**, yet share a single **business correlation ID**.

Therefore, do not force `traceId` to serve as the sole business identifier. If an event is reprocessed after the initial trace has ended, the consumer can start a new trace while keeping the original `correlationId`.

### Span ID is not an event ID

`spanId` represents a technical execution interval: an HTTP request, an event-handling segment, or a database call. `eventId` identifies a business occurrence. A retried event can produce several distinct spans while keeping **the same event ID** when it is genuinely the same occurrence being redelivered.

Do not use `spanId` alone to deduplicate business processing. It can change on every execution.

### Correlation ID may match request ID, but only if the contract defines it that way

In small systems, a correlation ID may be generated at the API gateway/controller and reused across the whole event chain. However, with batches and long-running workflows, one request can spawn multiple business journeys, or one journey can span multiple requests. In those cases, keep `correlationId` independent of `requestId` and define ID generation points explicitly.

## 3. Designing metadata so events are traceable

An internal Spring payload can carry identifier fields:

~~~java
public record OrderPlaced(
        String eventId,
        String orderId,
        String correlationId,
        String causationId) {}
~~~

*This code is an illustrative payload type; `OrderPlaced` does not need to extend `ApplicationEvent`. A complete runnable Java 17+ example is in section 6.*

You can replace those fields with a **metadata envelope** to avoid repeating them on every business event:

~~~java
public record EventMetadata(
        String eventId,
        String eventType,
        String correlationId,
        String causationId,
        Instant occurredAt) {}

public record DomainEvent<T>(
        EventMetadata metadata,
        T payload) {}
~~~

*This snippet requires importing `java.time.Instant`; it is an illustrative model. If you want Spring to dispatch automatically by the generic `DomainEvent<T>` type, verify how `ResolvableType` is resolved by Spring; do not assume generic type arguments survive Java type erasure.*

Depending on the environment, metadata can also carry `traceId` as a **diagnostic reference**. However:

1. Writing a `traceId` string into a payload alone **does not** re-establish tracing context or create child spans in the receiving system.
2. When crossing brokers/HTTP, use the tracing SDK's standard inject/extract mechanisms—such as W3C Trace Context—rather than manually patching `traceId` and expecting complete distributed traces.
3. If events outlive trace retention periods, `correlationId`, `eventId`, and `causationId` matter more because they can be persisted alongside business records.
4. If payloads/events are sent to external partners, evaluate whether internal IDs may be exposed.

A contract can specify `correlationId` as required, `causationId` as optional (for root events), and `eventId` as required. When a new event is derived from a prior event, preserve `correlationId`, assign a new `eventId`, and set `causationId` to the parent event's ID.

## 4. How Spring dispatches events and its impact on tracing

### 4.1. Default synchronous listeners

`ApplicationEventPublisher.publishEvent(...)` hands the event to the multicaster mechanism. With the default `SimpleApplicationEventMulticaster`, listeners typically run **directly on the thread that called publish**, so the publisher's `ThreadLocal` tracing/MDC state can remain active inside the listener.

~~~text
Thread request-1
  current Observation / tracing scope
      |
      +-- publishEvent(OrderPlaced)
              |
              +-- @EventListener.onOrderPlaced(...)
                     (same thread, sees thread-local scope)
      |
      +-- publishEvent returns
~~~

However, **Spring Framework does not automatically wrap each `@EventListener` invocation in its own `Observation`**. Spring's observability documentation explicitly states that listener invocations do not get automatic Observations just from the annotation. To measure individual handler latency/errors as separate spans, the application must **instrument** handlers explicitly or use appropriate tracing/observability infrastructure.

### 4.2. Async multicaster, `@Async`, and executors

When `SimpleApplicationEventMulticaster.setTaskExecutor(...)` is configured or a listener uses `@Async`, work can switch to another thread:

~~~text
publisher-thread                       executor-thread
trace context in ThreadLocal           ThreadLocal initially empty
  |
  +-- submit(task) ----------------------> @EventListener(...)
          |
          +-- does not transfer all ThreadLocals automatically
~~~

Without propagation, the listener can still read the **correlation ID stored directly in the event payload**, yet may lose MDC/tracing scope and log without a trace ID. That is why you should combine **explicit business correlation** with **tracing context propagation** rather than picking only one.

Spring provides `ContextPropagatingTaskDecorator` since Framework 6.1 to help transfer logging/observation context when an executor runs on another thread. This relies on the Micrometer Context Propagation library and registered accessors. It **does not copy arbitrary custom ThreadLocals** and does not move JDBC/JPA transactions to workers.

### 4.3. `@TransactionalEventListener` and transaction phases

A `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` listener reacts only after the corresponding transaction commits successfully. This does not guarantee a tracing scope is still alive, does not guarantee retries, and does not propagate context to executors when downstream work is async.

In imperative transactions, state is usually thread-bound; moving work to a worker should not try to "carry along" a JDBC connection/`EntityManager` just to keep correlation. If post-commit durable work is needed, design dedicated transactions/outboxes.

## 5. Rules for generating and propagating correlation IDs

A solid design should specify clearly:

**Starting a journey**

- If the caller sent a correlation ID via an accepted header, validate length, format, and trust boundaries before using it; never blindly trust arbitrary client headers.
- If no valid ID exists, generate a new one (e.g., UUID).
- Attach that ID to the business context and all related derived events.

**Creating a root event**

- Assign a new `eventId` for the business fact that just occurred.
- Set `causationId` to the originating command/request ID if tracked by the system; it can be `null` for root events if allowed by the contract.
- Record the aggregate's ID explicitly, such as `orderId`.
- Record `occurredAt` when the business fact occurred, preferably as UTC `Instant`.

**Creating a derived event**

- **Preserve the `correlationId`** of the journey.
- **Generate a new `eventId`** for the new occurrence.
- Set `causationId` to the prior event's ID if it is genuinely the direct cause.

**Retrying/replaying the same event**

- Keep the original occurrence's `eventId` so consumers can deduplicate.
- `traceId` and `spanId` of the new execution may differ; do not generate a new event ID merely because a worker retried.
- If a **new business event** is emitted during a retry, only then assign a new occurrence/event ID; never merge two distinct facts into one ID.

### Causation chain example

~~~text
Command cmd-12          correlationId=flow-42
   |
   +--> OrderPlaced    eventId=evt-101, causationId=cmd-12
            |
            +--> StockReserved    eventId=evt-102, causationId=evt-101
            |
            +--> InvoiceIssued    eventId=evt-103, causationId=evt-101

After 30 minutes:
PaymentWebhook         correlationId=flow-42 (from persisted business state)
   |
   +--> PaymentCaptured eventId=evt-150, causationId=webhook-77
~~~

The events above can span **multiple traces** yet still belong to the same business correlation. Use `correlationId` to query related records; use `causationId` to understand parent–child relationships; use trace/span IDs to investigate timings and technical calls.

## 6. Runnable Java 17+ example: stable correlation ID across thread switches

This example uses **Spring Framework 6.2.9**, Java 17+, and Maven. It creates two independent `ApplicationContext` instances, each configuring a `SimpleApplicationEventMulticaster` dispatching listeners to a `ThreadPoolTaskExecutor`:

- **Without `TaskDecorator`:** the event still carries `correlationId`, while a **simulated trace marker** in `ThreadLocal` does not transfer to the worker.
- **With `TaskDecorator`:** the worker receives the captured trace marker, while the listener also reads the event's `correlationId`.

**Important:** the string `trace-demo-001` in the program is **illustrative ThreadLocal data only**, not a valid OpenTelemetry/Micrometer trace ID, and this program **does not export spans to a tracing backend**. Its runnable goal is to demonstrate thread boundaries and the benefit of storing `correlationId` directly in the payload. Real tracing integration is covered in section 7.

### 6.1. Project structure

~~~text
event-trace-correlation-demo/
├── pom.xml
└── src/main/java/EventTraceCorrelationDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>event-trace-correlation-demo</artifactId>
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
                <version>3.5.1</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`src/main/java/EventTraceCorrelationDemo.java`:

~~~java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.task.TaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class EventTraceCorrelationDemo {

    // This is only an illustrative trace marker, not a tracing SDK.
    private static final ThreadLocal<String> TRACE_MARKER =
            new ThreadLocal<>();

    // Business correlation is placed directly in the event contract.
    public record OrderPlaced(
            String eventId,
            String orderId,
            String correlationId) {
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public OrderEventListener listener() {
            return new OrderEventListener();
        }
    }

    public static class OrderEventListener {
        private final CountDownLatch done = new CountDownLatch(1);
        private volatile String observation;

        @EventListener
        public void onOrderPlaced(OrderPlaced event) {
            String marker = TRACE_MARKER.get();
            String visibleMarker =
                    marker == null ? "missing" : marker;

            observation = "eventId=" + event.eventId()
                    + " correlationId=" + event.correlationId()
                    + " traceMarker=" + visibleMarker;
            done.countDown();
        }

        public String awaitResult() throws InterruptedException {
            if (!done.await(5, TimeUnit.SECONDS)) {
                throw new IllegalStateException(
                        "Listener did not complete within timeout");
            }
            return observation;
        }
    }

    private static TaskDecorator captureTraceMarker() {
        return task -> {
            // Capture happens when the task is submitted.
            String captured = TRACE_MARKER.get();

            return () -> {
                // Keep the worker's previous value for proper cleanup.
                String previous = TRACE_MARKER.get();
                try {
                    if (captured == null) {
                        TRACE_MARKER.remove();
                    } else {
                        TRACE_MARKER.set(captured);
                    }

                    task.run();
                } finally {
                    if (previous == null) {
                        TRACE_MARKER.remove();
                    } else {
                        TRACE_MARKER.set(previous);
                    }
                }
            };
        };
    }

    private static void runCase(boolean propagate)
            throws InterruptedException {

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(16);
        executor.setThreadNamePrefix("event-worker-");

        if (propagate) {
            executor.setTaskDecorator(captureTraceMarker());
        }
        executor.initialize();

        try {
            try (var context =
                    new AnnotationConfigApplicationContext()) {

                context.register(Config.class);

                // Spring recognizes the bean with this exact name as the multicaster.
                context.registerBean(
                    "applicationEventMulticaster",
                    SimpleApplicationEventMulticaster.class,
                    () -> {
                        var multicaster =
                                new SimpleApplicationEventMulticaster();
                        multicaster.setTaskExecutor(executor);
                        return multicaster;
                    });

                context.refresh();

                TRACE_MARKER.set("trace-demo-001");
                try {
                    context.publishEvent(
                            new OrderPlaced(
                                    "evt-1",
                                    "ORD-7",
                                    "flow-42"));

                    String result = context.getBean(
                            OrderEventListener.class).awaitResult();

                    String mode = propagate
                            ? "WITH_PROPAGATION"
                            : "WITHOUT_PROPAGATION";

                    System.out.println(mode + " " + result);
                } finally {
                    TRACE_MARKER.remove();
                }
            }
        } finally {
            executor.shutdown();
        }
    }

    public static void main(String[] args)
            throws InterruptedException {

        runCase(false);
        runCase(true);
    }
}
~~~

### 6.2. Running and output

In the directory containing `pom.xml`, run:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=EventTraceCorrelationDemo
~~~

Lines printed by the program, excluding Maven's own logs:

~~~text
WITHOUT_PROPAGATION eventId=evt-1 correlationId=flow-42 traceMarker=missing
WITH_PROPAGATION eventId=evt-1 correlationId=flow-42 traceMarker=trace-demo-001
~~~

Explanation:

1. In both runs, `OrderPlaced` is created with `correlationId=flow-42`, so the listener reads that ID regardless, **independent of ThreadLocal**.
2. In the first case, `TRACE_MARKER` was set only on the publisher thread; the executor's worker thread has no value, so it prints `missing`.
3. In the second case, `TaskDecorator` captures `trace-demo-001` at submit time and assigns it to the worker while the task runs.
4. `finally` guarantees restoring/cleaning up the worker's previous value, preventing context leaks to subsequent tasks in the thread pool.
5. `CountDownLatch` lets `main` wait for the listener to finish before reading the result, avoiding `Thread.sleep(...)` or machine-speed dependencies.
6. Two fresh contexts are created so each case has its own listener and executor. In this setup, only one listener receives `OrderPlaced`, keeping stdout order deterministic across both runs.

**Lesson:** a correlation ID in the event contract preserves business traceability even when tracing context is lost; tracing context propagation connects worker logs/spans back to the execution path. Both must be tested independently.

## 7. Real tracing integration with Spring Boot and Micrometer

In a Spring Boot application with Micrometer Tracing (e.g., an appropriately configured OpenTelemetry or Brave bridge), the tracing SDK manages real spans and trace contexts. Micrometer's `Tracer` can be injected into beans.

### 7.1. Accessing the current trace when publishing an event

The integration snippet below shows how to record the current trace ID **as metadata for diagnostics**, not as a mechanism for cross-process trace injection/extraction:

~~~java
@Service
class OrderService {

    private final ApplicationEventPublisher publisher;
    private final Tracer tracer;

    OrderService(ApplicationEventPublisher publisher, Tracer tracer) {
        this.publisher = publisher;
        this.tracer = tracer;
    }

    public void place(String orderId, String correlationId) {
        Span currentSpan = tracer.currentSpan();
        String traceId = currentSpan == null
                ? null
                : currentSpan.context().traceId();

        publisher.publishEvent(
                new OrderPlacedForDiagnostics(
                        UUID.randomUUID().toString(),
                        orderId,
                        correlationId,
                        traceId));
    }
}

record OrderPlacedForDiagnostics(
        String eventId,
        String orderId,
        String correlationId,
        String originatingTraceId) {
}
~~~

*This is an **integration snippet**, not a standalone program. It requires Micrometer beans `io.micrometer.tracing.Tracer`, `io.micrometer.tracing.Span`, Spring `@Service` and `ApplicationEventPublisher`, and import `java.util.UUID`. Choosing instrumentation, sampling, exporters, and matching dependencies depends on the application's Spring Boot version.*

In the example, `originatingTraceId` can be absent if there is no current span. When storing it on the event, name it **originating** so it is not confused with the active trace when the event is reprocessed minutes or days later. Do not treat this field as a complete span context.

**The preferred approach within the same JVM** is letting the tracing library hold the active scope while publishing/handling executes. When crossing to an executor, use proper context propagation instead of trying to stuff a trace ID string into a `ThreadLocal` and pretending a real span was created.

### 7.2. Propagation across executors

Per Spring Framework documentation, you can configure an executor:

~~~java
@Configuration
class EventObservabilityConfiguration {

    @Bean("eventExecutor")
    ThreadPoolTaskExecutor eventExecutor() {
        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("observed-event-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator());
        return executor;
    }

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster applicationEventMulticaster(
            @Qualifier("eventExecutor") ThreadPoolTaskExecutor executor) {

        var multicaster = new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(executor);
        return multicaster;
    }
}
~~~

*This is an integration configuration, not a full project. It requires `org.springframework.core.task.support.ContextPropagatingTaskDecorator`, `ThreadPoolTaskExecutor`, `SimpleApplicationEventMulticaster`, `@Configuration`, `@Bean`, `@Qualifier`, and the `io.micrometer:context-propagation` dependency. With Spring Boot, use Boot's BOM/dependency management.*

`ContextPropagatingTaskDecorator` captures and restores contexts known to Micrometer via matching `ThreadLocalAccessor`/`ContextAccessor`s. It helps carry logging/observation contexts across thread hops, yet **does not automatically register every application-defined ThreadLocal**. If the application manages its own ThreadLocal correlation ID, register an accessor or use a custom decorator for that variable.

If a listener uses `@Async("mailExecutor")`, place the decorator on the **executor that actually runs the async method**, not only on the multicaster's executor. Combining both layers of async can introduce two thread hops and extra complexity; design a single clear strategy.

### 7.3. Tracing scope and listener spans

Propagation can carry the **current tracing context** to the worker, yet **does not mean Spring automatically creates a new span for every `@EventListener`**. To measure individual event handling duration separately, instrument explicitly using Micrometer Observation or the tracing API.

Conceptual example using `ObservationRegistry`:

~~~java
@EventListener
public void handle(OrderPlaced event) {
    Observation.createNotStarted("app.event.handle", observationRegistry)
        .lowCardinalityKeyValue("event.type", "order.placed")
        .observe(() -> processOrderPlaced(event));
}
~~~

*This is an illustrative snippet in a Spring bean with `ObservationRegistry` injected; it requires `io.micrometer.observation.Observation`. `processOrderPlaced` is the application's business processing method. For an Observation to produce a span with genuine parent–child relationships, a properly configured tracing handler/bridge is required in `ObservationRegistry`.*

`lowCardinalityKeyValue("event.type", "order.placed")` is appropriate because event type names are typically bounded. **Never use `correlationId`, `eventId`, `orderId`, `traceId`, or `userId` as low-cardinality metric tags**, because those values are nearly unique and cause time-series explosion. Attach IDs needed for tracing to logs, span attributes, or `highCardinalityKeyValue` when operational/security policies permit.

## 8. MDC and log correlation: distinct from business correlation ID

`MDC` (Mapped Diagnostic Context) typically carries values such as `traceId` and `spanId` for logging frameworks. With Micrometer Tracing configured, Spring Boot can automatically include **log correlation** formatted from `traceId` + `spanId` in logs.

Conceptual log example:

~~~text
[traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=00f067aa0ba902b7]
INFO OrderService - placed orderId=ORD-7 correlationId=flow-42 eventId=evt-100

[traceId=4bf92f3577b34da6a3ce929d0e0e4736 spanId=5f2e730bb9b4368e]
INFO AuditListener - processed eventId=evt-100 correlationId=flow-42
~~~

*This is an illustrative log, not stdout from the section 6 example. The `spanId` on the second line assumes the listener was instrumented as a separate span; a synchronous listener does not get a separate span automatically just from `@EventListener`.*

Easy-to-confuse point: in Spring Boot documentation, "logging correlation ID" can refer to **a display string built from trace ID and span ID**, whereas an application defines a **business correlation ID** like `flow-42`. The two identifiers serve different purposes and should have **clear field names**.

If you need to include a business correlation ID in logs, you can scope it in MDC manually:

~~~java
try (MDC.MDCCloseable scope =
        MDC.putCloseable("businessCorrelationId",
                         event.correlationId())) {

    logger.info("Handling OrderPlaced eventId={}", event.eventId());
}
~~~

*Integration snippet using `org.slf4j.MDC` and a declared `SLF4J` logger; not a standalone program. `putCloseable` helps restore/clear state per MDC's API, yet does not create tracing spans or guarantee MDC propagates automatically across executors.*

**Do not put correlation ID only in MDC while omitting it from the payload** if the event must cross brokers, delayed jobs, or replays. MDC belongs to the execution context, while the payload/envelope is the data contract traveling with the event.

## 9. Linking events across multiple services or message brokers

Within the same JVM, Spring dispatches internal event objects. Across Kafka/RabbitMQ/JMS/HTTP, trace context must be **injected on publish** and **extracted on consume** using that technology's instrumentation/propagator.

Two-layer metadata concept:

~~~text
Business envelope:
  eventId: evt-100
  eventType: sales.order.placed
  correlationId: flow-42
  causationId: cmd-25
  occurredAt: 2026-11-11T05:30:00Z

Tracing carrier (header or compatible metadata):
  traceparent: 00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01
~~~

`traceparent` above illustrates the W3C format consisting of version, 32-hex-char trace ID, 16-hex-char parent span ID, and trace flags. Tracing systems should write/read headers via an **SDK propagator**, rather than concatenating strings manually and assuming distributed context is properly established.

An inter-service flow:

1. Producer mutates business state and constructs an event envelope with `eventId`, `correlationId`, `causationId`.
2. Messaging instrumentation injects current tracing context into **headers/carrier**, or an equivalent configured mechanism.
3. Broker receives the message and may redeliver after retries, depending on delivery guarantees.
4. Consumer extracts the tracing carrier when starting processing and creates a processing span (or span link if suited to decoupled/batch handling).
5. Consumer logs `correlationId`, `eventId`, and span/tracing info to query both the message and execution path.
6. If the consumer emits a new event, it preserves the business correlation ID, assigns a new event ID, and sets `causationId` accurately.

**Do not promise that traces are always a simple parent–child tree.** With async queues, delayed processing, batches, or fan-in producers, span links or new traces may be more appropriate; choose based on your tracing SDK's model and system semantics.

Not every sampled request is exported completely as a trace. Thus, a `correlationId` stored with events/logs remains valuable even when a complete trace is unavailable.

## 10. Relation to Reactor Context

In reactive applications using Reactor, tracing/transaction context can travel with the **subscriber context** rather than Java `ThreadLocal` alone. When crossing between imperative code, Reactor pipelines, and non-Reactor executors:

- Context propagation must be configured properly at thread/scheduler boundaries.
- `contextWrite(...)` and `deferContextual(...)` are scoped per subscription; spawning a new subscription may not inherit prior context automatically.
- Micrometer Context Propagation can bridge between Reactor Context and ThreadLocal for registered accessors; it does not copy every global variable.
- Reactive transactions use `ReactiveTransactionManager` and subscriber-bound transaction contexts. Never pass JDBC transaction state across executors just to preserve trace/correlation.

An event should carry its business `correlationId` as immutable data even as tracing context moves across Reactor and different threads. Treat tracing propagation as infrastructure, and correlation/causation as part of the business contract.

## 11. Ensuring no lost events: a trace is not a delivery guarantee

Having a clean trace does not mean an event was durably delivered. Spring's built-in `ApplicationEventPublisher` does not provide persistence, retries, dead-letter queues, or replay out of the box. If a listener fails, the JVM stops, or publication occurred before a commit that later rolled back, the event may not represent a committed business fact.

When the requirement is "deliver the event even if the process dies after DB commit", use a **transactional outbox**:

~~~text
Transaction DB
  |
  +-- UPDATE orders
  +-- INSERT outbox(eventId, correlationId, causationId,
  |                 eventType, payload, createdAt, ...)
  |
  +-- COMMIT
         |
         v
Outbox relay -> broker -> consumer
                  |
                  +--> idempotent processing by eventId
                  +--> trace context may be new/linked
                  +--> correlationId remains flow-42
~~~

To link back to the originating trace when a relay runs later, you can store **standardized, permitted tracing propagation metadata** in the outbox so the SDK can restore/define appropriate links. **Saving only a trace ID string is insufficient** to automatically restore parent spans, sampling state, and other tracing fields.

Also protect metadata: outboxes persist for a long time, and tracing headers/baggage can contain data that should not be stored. Design retention, access controls, and sensitive-data policies before rollout.

If a consumer has at-least-once delivery, use `eventId` to support deduplication via transactions/unique constraints; `correlationId` is usually unsuitable as a deduplication key because many distinct events in the same journey share it.

## 12. Testing observability layer by layer

Do not merely test that `@EventListener` "was called" and conclude traceability is solid.

### 12.1. Contract tests

- Root events have valid `eventId`, `correlationId`, and `aggregateId`.
- Derived events preserve `correlationId` while receiving a new `eventId`.
- `causationId` points to the event/command that triggered the new event.
- Retried events preserve the original `eventId` and do not cause duplicate side effects.
- Events contain no tokens, passwords, or unnecessary payloads.

### 12.2. Thread context tests

- Synchronous listeners see the active logging/tracing scope under default settings.
- Listeners running on an executor must not be assumed to inherit custom ThreadLocals automatically.
- Decorated executors with matching accessors restore context during execution.
- After a listener fails, the worker does not retain the old task's context.
- A second task with a different correlation ID never mixes up with the previous correlation ID.
- If `@Async` uses a different executor from the multicaster, both execution boundaries must be observed.

### 12.3. Tracing integration tests

- When tracing is enabled, event-handling spans have clear names and appropriate attribute cardinality.
- When traces are sampled out or exporters are down, business correlation IDs in logs/events still support investigation.
- When messages cross HTTP/brokers, injection/extraction works with a real propagator.
- On replay, the new execution's trace span is not confused with the original event-publishing span.
- The system can locate events in outbox/broker logs by `eventId` and locate business flows by `correlationId`.

For async tests, use `CountDownLatch`, `CompletableFuture`, or timeout-bounded await utilities; avoid `Thread.sleep(100)` to "wait for logs", which produces flaky tests.

## 13. Logging and measurement strategy

A concise logging/metrics standard per listener should separate three goals:

**Logs:** for investigating individual occurrences; should include `eventType`, `eventId`, `correlationId`, `causationId` if present, handler name, and outcome. Trace/span IDs link to the tracing system. If logs are JSON-formatted, keep field names consistent and guard against exposing sensitive data.

**Traces:** for viewing technical timing/ordering, network calls, and paths across services. Create observations/spans only where useful rather than turning every log line into a span; use trace IDs, span IDs, and span links with proper semantics.

**Metrics:** aggregate counts/latencies/errors by event type, listener, and outcome. Tags like `event.type=order.placed` or `handler=OrderAuditListener` usually have bounded value sets. Avoid placing `eventId`, `correlationId`, or `traceId` into **low-cardinality tags**.

Naming example:

~~~text
Log fields:
  event.type=sales.order.placed
  event.id=evt-100
  business.correlation_id=flow-42
  event.causation_id=cmd-25
  trace_id=4bf92f3577b34da6a3ce929d0e0e4736
  span_id=00f067aa0ba902b7
  listener=OrderAuditListener
  outcome=success

Metric:
  app.event.handle{event.type="sales.order.placed",
                   listener="OrderAuditListener",outcome="success"}
~~~

*This is a suggested convention, not default Spring Boot metric or field names. Map it to the logging/metrics stack in use.*

If searching across services is required, standardize field names across every service. Avoid letting different teams use `requestId`, `corr`, and `transactionRef` with differing semantics without a mapping standard.

## 14. Common mistakes and fixes

1. **Using `traceId` as the sole business key.** Traces can change on retries and do not cover long sagas; an independent business correlation ID is required.
2. **Using `correlationId` to deduplicate all events.** Multiple events in the same workflow share a correlation ID; use the occurrence `eventId` to support idempotency.
3. **Assuming `publishEvent(...)` auto-creates a span per `@EventListener`.** Spring Framework does not instrument these invocations as Observations by default; add instrumentation purposefully.
4. **Putting `correlationId` only into MDC.** Across async, brokers, or replays, context can be lost; place business IDs in the payload/envelope.
5. **Putting only a `traceId` string into the payload and expecting distributed tracing.** A tracing SDK managing spans and injecting/extracting context via proper headers/carriers is required.
6. **Configuring the decorator on the wrong executor.** Multicaster uses one executor while `@Async` uses another; propagation is needed at every active boundary.
7. **Forgetting ThreadLocal/MDC cleanup.** Thread pools reuse workers; stale context can leak into the next request.
8. **Sharing a JDBC transaction or `EntityManager` via a decorator.** Tracing context propagation is not a mechanism for passing transactions across threads.
9. **Assuming the same `correlationId` always has the same `traceId`.** A business workflow can span long durations, multiple traces, replays, and retries.
10. **Assuming different `traceId`s mean events are unrelated.** `correlationId` and the causation chain are the more durable business links.
11. **Putting unique IDs into low-cardinality metric tags.** Inflates time series, costs, and operational risk; individual IDs belong in logs/traces.
12. **Assuming tracing guarantees delivery.** Tracing is for observation and does not replace outboxes, broker retries, and consumer idempotency.
13. **Not validating inbound correlation headers.** Caller-supplied identifiers can be oversized, contain odd characters, or leak data; validate and normalize.
14. **Logging secrets in baggage or MDC.** Metadata propagates and can appear in logs/traces; keep it minimal and safe.
15. **Not defining a causation chain.** Two events sharing a correlation ID do not show which directly led to which; add `causationId` when causality investigation is needed.

## 15. Self-check

**Question 1.** An order workflow includes order creation, payment 10 minutes later, and shipping the next day. Must all of them share the same `traceId`?

**Answer:** No. There can be multiple separate traces across time and system boundaries. Preserve `business correlationId` across the workflow; tracing contexts/links depend on instrumentation design.

**Question 2.** An event is redelivered three times. Should you keep `eventId` or generate a new event ID each time?

**Answer:** Keep the original occurrence's `eventId` so consumers can deduplicate. Each technical execution can have different span/trace contexts.

**Question 3.** Why in the Java example does the `WITHOUT_PROPAGATION` line still show `correlationId=flow-42`?

**Answer:** Because `correlationId` is an immutable field inside the event payload, independent of worker `ThreadLocal`s.

**Question 4.** Does putting `ContextPropagatingTaskDecorator` on an executor automatically propagate every custom `ThreadLocal`?

**Answer:** No. Micrometer Context Propagation needs corresponding accessors/infrastructure; custom `ThreadLocal`s are not discovered automatically.

**Question 5.** If a listener carries a string `traceId` inside the event, is that enough for the tracing SDK to continue the parent span?

**Answer:** No. Continuing a trace requires a propagator/SDK and a tracing carrier containing sufficient valid context, not just a `traceId` string.

**Question 6.** Why should `correlationId` not be used as a metric label for every request?

**Answer:** It has very high cardinality (almost one value per request), multiplying time series. Use it in logs or trace attributes, while keeping metrics to tags with bounded value sets.

**Question 7.** If an event is published only with Spring `ApplicationEventPublisher`, is it automatically persisted and retried after the JVM stops?

**Answer:** No. Durable persistence like an outbox/broker and explicit retry/idempotency strategies are required when business rules demand it.

**Question 8.** Why should a derived event keep `correlationId` yet get a new `eventId`?

**Answer:** Both belong to the same workflow yet are **two distinct business occurrences**. The new `eventId` identifies the new fact; `causationId` links it to the parent event.

## References

- [Spring Framework — Observability Support: Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html): synchronous default listeners, no automatic Observation, and using `ContextPropagatingTaskDecorator` when running async.
- [Spring Framework — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `ApplicationEventPublisher`, `@EventListener`, and event dispatching.
- [Spring Framework 6.2 Javadoc — ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.2.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html): task context capture/restore mechanics and propagation overhead.
- [Spring Boot 3.5 — Tracing and Logging Correlation IDs](https://docs.spring.io/spring-boot/3.5/reference/actuator/tracing.html): Micrometer Tracing, `traceId`/`spanId` in MDC, and log correlation formats.
- [Micrometer Context Propagation — Purpose](https://docs.micrometer.io/context-propagation/reference/purpose.html): `ThreadLocalAccessor`, `ContextRegistry`, `ContextSnapshot`, and transferring context across executors.
- [Micrometer Tracing — API](https://docs.micrometer.io/tracing/reference/api.html): `Tracer`, span scopes, and baggage.
- [W3C — Trace Context](https://www.w3.org/TR/trace-context/): `traceparent`, `tracestate`, and cross-system context propagation structure.
