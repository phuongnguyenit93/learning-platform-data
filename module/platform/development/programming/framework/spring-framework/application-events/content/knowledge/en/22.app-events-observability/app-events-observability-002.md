# Why doesn't @EventListener automatically create an Observation in Spring Framework?

## 1. Short answer

`@EventListener` is a mechanism for **registering a method to receive Spring application events**; it is not an annotation requesting the creation of a metric, trace span, or `Micrometer Observation`. When calling `ApplicationEventPublisher.publishEvent(event)`, Spring dispatches the event to matching listeners, but **does not automatically create a separate Observation for each `@EventListener` invocation**.

This is an intentional semantic choice, not a missing `ObservationRegistry` bug. According to the official Spring Framework documentation, `@EventListener` invocations are not automatically instrumented with Observations by the framework because they **do not have semantics suitable for instrumentation as an independent operation**. By default, publishing and handling events occur on the same thread synchronously; the event listener is already inside the publisher's call stack, logging context, and often current trace.

To measure event processing time separately or create a dedicated span for a handler, you **actively instrument** the point you want to observe: using `ObservationRegistry` and `Observation` in the listener, a service wrapped by configured AOP/`@Observed`, or a dedicated abstraction matching the architecture.

> Rule to remember: Having `@EventListener` ≠ having an Observation; having an `ObservationRegistry` bean ≠ every method is auto-instrumented; having an HTTP trace that covers the handler ≠ Spring created a dedicated span for the handler.

## 2. Distinguishing three conceptual layers

### Event

An application event is an object representing something that happened. For example:

```java
public record OrderPlaced(String orderId) {}
```

The publisher can emit the record directly via `publishEvent(new OrderPlaced("O-17"))`. Spring supports POJO events and does not require the record to extend `ApplicationEvent`.

### Listener

`@EventListener` marks a method on a Spring-managed bean. `EventListenerMethodProcessor` processes the metadata and corresponding adapter; the multicaster dispatches the event to matching listeners.

```java
@EventListener
public void handle(OrderPlaced event) {
    // Business handler.
}
```

This is an illustrative snippet, not a standalone program. The annotation only specifies *when to invoke the method* based on event type and filter conditions; it does not state that a meter or trace span must be emitted.

### Observation

Micrometer `Observation` represents the lifecycle of an observable action: start, scope, stop, error, and key-values. `ObservationRegistry` coordinates `ObservationHandler`s to process the lifecycle; when appropriate bridges exist, handlers can produce metrics, traces, or log correlation.

```text
publishEvent(event)
    |
    v
ApplicationEventMulticaster
    |
    +--> @EventListener OrderHandler.handle(...)
             |
             +--> NO default Observation for this invocation
             |
             +--> Observation exists if you explicitly create one or
                  use genuinely configured instrumentation
```

**Observation does not equate to a span**: Observation describes an operation at the Micrometer level; metrics/tracing are generated when corresponding handlers are registered. An Observation can be a no-op if the registry/instrumentation lacks suitable handlers.

## 3. Why doesn't Spring create an Observation for every @EventListener?

### 3.1. Event semantics do not always resemble an independent operation

A domain event may be published many times, observed by multiple listeners, or have no listeners at all. Many events simply signal a step in a use case rather than a "unit of work" with consistent semantics for automatic span creation.

For example, an HTTP request executing `placeOrder()`:

```text
HTTP SERVER SPAN: POST /orders
    |
    +-- OrderService.place()
         |
         +-- publishEvent(OrderPlaced)
              |
              +-- @EventListener updateCache()
              +-- @EventListener recordAudit()
              +-- @EventListener updateCounter()
```

If every listener always received an automatic Observation, the system could generate large volumes of spans/timers for tiny tasks without deliberate naming, cardinality, phase, or ownership design. Not every listener shares the same meaning of "success": listener A updates a cache, listener B writes an audit record, listener C increments a metric.

### 3.2. Synchronous and same-thread by default

`SimpleApplicationEventMulticaster` by default invokes compatible listeners on the publisher thread when no async executor is configured. In that case:

- MDC/logging context can be inherited naturally in the call stack.
- The current `ThreadLocal` trace/context remains usable while the listener runs synchronously.
- Listener processing time already contributes to the duration of the enclosing operation, such as an HTTP request Observation if the request is instrumented.
- There is no default need to build a new trace span solely to propagate trace context.

Note: *being inside the request trace* does not mean *having a dedicated Observation for the listener*. In a tracing system, you may see only the HTTP span without a child span named `event.handle`.

### 3.3. Events can be async or in a different transaction phase

A listener may carry `@Async`, the multicaster may have an executor, or it may be a `@TransactionalEventListener` invoked at the commit/rollback phase. In such cases:

- Where the event is published and where the handler runs may belong to **two different threads or two different points in time**.
- Listeners do not necessarily share the same transaction or scope.
- Not every listener can be moved to an executor: some listeners declare that they do not support async execution.
- "Publish duration" and "listener processing duration" are not the same thing.
- Blindly measuring with a single Observation on the publisher can miss asynchronous listener processing time.

Therefore, the application should choose the **operation boundary**: measuring publish time, handler execution time, end-to-end latency, or processing time for a batch from a broker. There is no single default that fits all cases.

## 4. Does Spring automatically create Observations elsewhere?

Yes. Spring Framework instruments certain components with clear semantics, such as HTTP server handling, HTTP clients, `@Scheduled` tasks when configured, and JMS publication/processing with the corresponding instrumentation. Spring Boot and starters/actuator can configure `ObservationRegistry`, metrics, tracing bridges, and exporters.

Points to distinguish:

| Component | Has Observation when properly configured? | Relation to @EventListener |
| --- | --- | --- |
| HTTP server request | Yes, with appropriate instrumentation | Synchronous listeners may run **inside** the HTTP span |
| `RestClient`/`WebClient` HTTP client | Yes, if registry is configured on the client/builder | A listener calling HTTP can create a **client span**, not necessarily a handler span |
| `@Scheduled` | Yes, when the scheduler registrar receives the registry per Framework mechanism | Does not prove `@EventListener` is instrumented |
| JMS publish/process | Yes, with configured integration | Distinct from Spring in-process application events |
| Regular `@EventListener` | **Does not automatically contribute a default Observation** | Must be actively instrumented if needed |
| `@Observed` with AOP set up | Can create an Observation for AOP-intercepted invocations | Does not run automatically if you only add the annotation without configuring aspect/proxy |

Do not infer that "having Micrometer and Actuator on the classpath turns every listener into a span". At the same time, avoid breaking existing HTTP/JMS instrumentation when adding handler spans: having multiple spans at different layers can be correct if they measure **different boundaries**.

## 5. Runnable Java 17 example: no default Observation, explicit Observation

The project below uses Spring Framework 6.2.8 and Micrometer Observation. Two methods receive the same `OrderPlaced`:

1. `plainListener` only receives the event; it opens no Observation.
2. `observedListener` explicitly creates an `Observation` named `app.event.handle` and adds the low-cardinality tag `event.type=order-placed`.

To illustrate the **Observation lifecycle** without needing Prometheus, Zipkin, or OpenTelemetry, we register a simple `ObservationHandler` that prints start/stop messages. **This is a demonstration handler** and does not export real metrics or traces. In production, replace it with appropriate Micrometer meter/tracing handlers.

### Maven structure

```text
event-observation-demo/
├── pom.xml
└── src/main/java/demo/EventObservationDemo.java
```

`pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
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
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-observation</artifactId>
            <version>1.14.8</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.EventObservationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/EventObservationDemo.java`:

```java
package demo;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.core.annotation.Order;

public class EventObservationDemo {

    public record OrderPlaced(String orderId) {}

    public static class OrderHandlers {
        private final ObservationRegistry registry;

        public OrderHandlers(ObservationRegistry registry) {
            this.registry = registry;
        }

        @Order(0)
        @EventListener
        public void plainListener(OrderPlaced event) {
            System.out.println("plain: " + event.orderId());
        }

        @Order(1)
        @EventListener
        public void observedListener(OrderPlaced event) {
            Observation.createNotStarted("app.event.handle", registry)
                    .lowCardinalityKeyValue("event.type", "order-placed")
                    .observe(() -> {
                        System.out.println(
                                "instrumented: " + event.orderId());
                    });
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        ObservationRegistry observationRegistry() {
            ObservationRegistry registry = ObservationRegistry.create();

            registry.observationConfig().observationHandler(
                    new ObservationHandler<Observation.Context>() {
                        @Override
                        public boolean supportsContext(
                                Observation.Context context) {
                            return true;
                        }

                        @Override
                        public void onStart(Observation.Context context) {
                            System.out.println(
                                    "observation.start: " + context.getName());
                        }

                        @Override
                        public void onStop(Observation.Context context) {
                            System.out.println(
                                    "observation.stop: " + context.getName());
                        }
                    });
            return registry;
        }

        @Bean
        OrderHandlers orderHandlers(ObservationRegistry registry) {
            return new OrderHandlers(registry);
        }
    }

    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(Config.class)) {
            context.publishEvent(new OrderPlaced("O-17"));
        }
    }
}
```

Run with JDK 17+ and Maven:

```bash
mvn -q clean compile exec:java
```

Output printed by the program itself (excluding Maven logs):

```text
plain: O-17
observation.start: app.event.handle
instrumented: O-17
observation.stop: app.event.handle
```

Explanation:

- Both methods are registered by `@EventListener`; `@Order(0)` and `@Order(1)` determine listener precedence order.
- `plainListener` runs but does **not** create an Observation because there is no instrumentation code around it.
- `observedListener` calls `Observation.createNotStarted(...)` and then `observe(...)`: Micrometer starts/stops the Observation and the handler prints the two corresponding lines.
- `event.type` is used as a low-cardinality key: it should be a bounded event type name, not an order ID.
- `ObservationHandler` prints lifecycle events for demonstration; the handler itself does not create real metrics/traces. Metrics require a handler backed by `MeterRegistry`; tracing requires a tracing bridge/handler and the corresponding exporter.
- The synchronous nature of publisher and listener does not change: the manual Observation simply wraps the execution time of the `observedListener` method body.

**Key verification point:** If you remove `Observation.createNotStarted(...).observe(...)` while keeping both `@EventListener` methods, the listeners still receive the event, but the `observation.start/stop` lines no longer appear. Simply adding an `ObservationRegistry` bean also does not automatically create an Observation around methods.

## 6. What to measure: publish, handle, or end-to-end latency?

### 6.1. Measuring publish duration

```java
Observation.createNotStarted("app.event.publish", registry)
        .observe(() -> publisher.publishEvent(event));
```

This is an illustrative snippet; `publisher`, `registry`, and `event` must be available. With a synchronous multicaster, the duration can include the time of invoked listeners. With an asynchronous multicaster, it typically measures only the time to **hand off** to the executor; it does not measure listener completion afterward.

Hence, the name `app.event.publish` must be clearly defined: measuring a single `publishEvent` call, not necessarily the entire event processing.

### 6.2. Measuring handler duration

```java
Observation.createNotStarted("app.event.handle", registry)
        .lowCardinalityKeyValue("event.type", "order-placed")
        .observe(() -> handleBusinessLogic(event));
```

This is an illustrative snippet; `handleBusinessLogic` must be defined in the project. Place the Observation **around the actual processing work**. If the code only enqueues a task and returns, this duration measures enqueuing, not task duration in the worker.

### 6.3. Measuring end-to-end latency

From when an event is created to when the consumer finishes processing, there can be a large gap if it passes through an executor/queue/broker. An Observation opened only on the publisher thread cannot automatically span queue wait time.

To measure end-to-end latency, you need timestamps and correlation/event IDs with a clear purpose, controlled context propagation, and consumer instrumentation at the corresponding boundary. If going through a message broker, use the messaging technology's instrumentation or a deliberately designed tracing mechanism.

## 7. Configuring @Observed and AOP: do not mistake the annotation for automatic instrumentation

Micrometer provides `@Observed` and `ObservedAspect` to create an Observation for **aspect-intercepted method invocations**. However, in a Spring application, merely writing:

```java
@Observed(name = "app.event.handle")
public void handle(OrderPlaced event) {
    // ...
}
```

does not guarantee a span/metric. You need the aspect, appropriate Spring AOP/AspectJ wiring, and an `ObservationRegistry` with handlers. If a Spring proxy does not intercept the invocation (for example, self-invocation or proxy limitations on a method/class), the annotation will not behave as expected.

With `@EventListener`, dispatch goes through a Spring listener adapter and may interact with AOP proxies. You must verify in practice that advice actually runs on the target bean/method being invoked; **do not treat adding `@Observed` to a listener as a universal zero-configuration solution**.

If you want transparency, easy testing, and precise measurement of a handler segment, the manual `Observation.createNotStarted(...).observe(...)` approach is a clear choice. If many handlers must follow the same policy, you can encapsulate an instrumentation helper or an application-layer wrapper; avoid copying start/stop boilerplate everywhere.

## 8. When using @Async or a custom ApplicationEventMulticaster

By default, `SimpleApplicationEventMulticaster` invokes listeners synchronously. When an executor is configured or `@Async` is used, the event is handled on another thread:

```text
publisher thread:
  current Observation / trace scope
  publishEvent(event)
       |
       +-- executor.submit(task)
  return

worker thread:
  [does not inherit ThreadLocal/trace context by default]
  @EventListener handler
       |
       +-- new Observation if instrumented
```

Without trace context propagation, a span created in the worker can become a disconnected root span or fail to link with the publisher's trace. Conversely, if there is only logging MDC on the publisher, the worker may lose the correlation ID.

Spring Framework allows configuring `ContextPropagatingTaskDecorator` on an executor together with the `io.micrometer:context-propagation` library when context propagation is needed. A **conceptual excerpt** example, not a standalone runnable configuration:

```java
SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor();
executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
multicaster.setTaskExecutor(executor);
```

Appropriate imports/classpath and multicaster bean are required. **Context propagation does not automatically create an Observation for @EventListener**; it only carries existing context across the asynchronous boundary. Additionally, not every listener supports async execution in the multicaster, especially listeners requiring thread-bound transactions.

If using `@Async` on a listener, `@EnableAsync`, a configured executor, and clear propagation/error-handling policies are required. Async exceptions do not automatically return to `publishEvent`. The Observation should wrap the **actual work running in the worker**, not merely the submit time.

## 9. Observation, metric, tracing, and logging: how do they differ?

| Concept | Question answered | Example |
| --- | --- | --- |
| Observation | "Which operation is running and what is its outcome?" | `app.event.handle` start/stop/error |
| Metric | "What are the aggregate rate, latency, and errors?" | Timer for `order-placed` processing, tagged by event type |
| Trace/span | "Which components did a request pass through?" | HTTP span containing an intentionally created child handler span |
| Log | "What happened at a point in time?" | Handler logs result code or redacted error |
| Context propagation | "How do we correlate work on another thread?" | Propagating trace/correlation context across an executor |

An Observation can produce a metric or span if the registry has the corresponding handlers. A log with a trace ID does not prove a child span exists for the listener. A metric counter incremented manually by a handler does not prove Micrometer created an `Observation`.

Design tagging carefully:

- **Low-cardinality tags**: bounded event types, outcome (`success`/`error`), fixed handler families.
- **High-cardinality data**: order ID, user ID, email, request ID; do not use as metric tags because they cause series explosion and can expose sensitive data.
- **Observation name**: keep it stable and consistent; do not embed dynamic IDs in the name.
- **Sensitive payloads**: do not pass raw events into `lowCardinalityKeyValue(...)`, `highCardinalityKeyValue(...)`, trace baggage, or logs without an explicit policy.

Even though high-cardinality fields can be useful in spans for investigation, they must still comply with access controls and data security policies. Do not "move PII into tracing" as a way to bypass metrics limits.

## 10. Errors, rollbacks, and Observation timing

An `@EventListener` handler can throw an exception. With a manual callback:

```java
Observation.createNotStarted("app.event.handle", registry)
        .observe(() -> perform(event));
```

Micrometer manages start/stop across the execution branches of `observe(...)` and records exceptions into the Observation lifecycle per the API. However, an Observation ending with an error **does not automatically roll back a transaction**, does not automatically retry the event, and does not mean the event is durably persisted.

When using `@TransactionalEventListener(AFTER_COMMIT)`, the handler runs only in the matching transaction phase. An Observation inside the listener measures execution at that moment, **not the pre-commit transaction duration**. If the listener fails after commit, the Observation may record an error, but **it cannot undo the DB commit that already occurred**. Error monitoring and retries belong in a separate design.

If the listener runs on the publisher thread and in the same transaction, an unhandled exception can propagate back to `publishEvent` and cause the transaction to roll back. Opening an Observation does not change that propagation/rollback policy.

## 11. How to verify you instrumented correctly?

A test suite and checklist should verify both **event delivery** and **Observation placement**:

1. **Event dispatch**: publish `OrderPlaced` properly; the handler runs once per contract.
2. **Observer lifecycle**: the observing handler receives one start and one stop when instrumented; do not confuse the event being called with the observation being invoked.
3. **Name/low-cardinality tags**: `app.event.handle` and `event.type=order-placed` are fixed.
4. **No Observation emitted for the plain listener** in the demo, regardless of the `ObservationRegistry` bean existing.
5. **Exception**: the handler throws an error, yet the Observation is stopped safely; the error is reported to the right boundary.
6. **AOP if used**: prove `ObservedAspect`/proxy actually runs rather than relying solely on the presence of the annotation.
7. **Async**: if using an executor, verify scope, context propagation, and trace correlation explicitly.
8. **No sensitive data added** to tags/traces/logs.
9. **Do not confuse listener phases**: `@TransactionalEventListener` after-commit has different timing semantics than `@EventListener`.
10. **Metrics/traces export**: verify the handler/registry/exporter configuration; a demo printing start/stop does not prove a server received spans.

### Common configuration mistakes

**"There is an ObservationRegistry, yet the dashboard is empty"**: The registry does not auto-instrument listeners. You may also be missing meter/tracing handlers, a `MeterRegistry` exporter, or sampling configuration.

**"@EventListener ran, yet there is no child span"**: Spring does not contribute a default Observation for listeners; if you need a child span, instrument explicitly.

**"@Observed seems to have no effect"**: Aspect not registered, proxy did not intercept, self-invocation, or the listener invocation path bypasses advice.

**"Publish duration is short, yet the handler takes many seconds"**: Publish may only be enqueuing async work. Measure handler duration inside the worker.

**"MDC/trace disappears after @Async"**: Thread-local context does not automatically propagate to workers; check `ContextPropagatingTaskDecorator` and Micrometer Context Propagation, and restrict what data is propagated.

**"Events fire, yet there are no meters"**: The Event API, Observation API, and registry/exporter are separate layers and do not imply one another.

## 12. When should you create a dedicated Observation for a listener?

Create one when the handler is genuinely an independent operation worth measuring: for example, processing a domain event that can fail, is slow, retries multiple times, calls an external dependency, or runs in an async worker.

It may be unnecessary when the listener only updates an in-memory value, is part of an operation already well covered by an HTTP span, and adding a separate span adds noise/cost. There does not have to be a 1:1 mapping from `@EventListener` to span or timer. Decide based on incident investigation needs, SLOs, instrumentation overhead, and operational contracts.

A pragmatic design:

```text
HTTP/server observation (automatic via integration)
   |
   +-- service business logic
        |
        +-- publishEvent(OrderPlaced)
             |
             +-- cheap listener: no extra span
             |
             +-- external integration handler:
                  Observation("app.event.handle")
                    event.type=order-placed
                    result=success/error
                  -> HTTP client observation if client is configured
```

Measuring listeners **does not replace** designing idempotency, a durable outbox, or retries. Observation only tells you what happened; it does not guarantee event delivery or exactly-once processing.

## 13. Knowledge self-check

1. **Does `@EventListener` always create a Micrometer Observation?** — No. Spring Framework does not automatically contribute an Observation for listener invocations.
2. **Why can an HTTP trace have listener logs without a listener child span?** — A synchronous handler can run in the current scope without a dedicated Observation operation.
3. **Is registering an `ObservationRegistry` bean enough to measure all listeners?** — No; explicit instrumentation or an appropriate aspect and handlers are required.
4. **Why aren't all listeners auto-instrumented?** — Semantics differ; same thread, multiple consumers, sync/async/phase differences, and cost/cardinality prevent a single uniform default.
5. **To measure the actual duration of an async handler, where do you instrument?** — Inside the processing worker, not merely around `publishEvent`.
6. **Does `@Observed` work without an aspect/proxy?** — Not by default.
7. **What does context propagation do?** — Carries configured context across thread boundaries; it does not create spans on its own.
8. **Can an order ID be used as a low-cardinality tag?** — No; it has high cardinality and poses data exposure risks.
9. **After commit, does an Observation error roll back the committed transaction?** — No.
10. **To get real metrics/traces, what else is needed besides Observation?** — Registry handlers, meter/tracing bridges, and exporters per application configuration.

## References

- [Spring Framework — Observability Support: Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Micrometer — Observation Concepts](https://docs.micrometer.io/micrometer/reference/observation/components.html)
- [Micrometer — Observation Introduction](https://docs.micrometer.io/micrometer/reference/observation/introduction.html)
- [Spring Framework — Async context propagation](https://docs.spring.io/spring-framework/reference/integration/observability.html#integration.observability.application-events)
