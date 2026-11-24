# Trace Context for Synchronous Events in Spring Application Events

## 1. The problem: does an event keep the active trace?

When a Spring application uses distributed tracing, a request or background job may be running inside a **trace** with a **current span**. A service publishes a domain event for listeners to perform secondary business logic:

```java
applicationEventPublisher.publishEvent(new OrderSubmitted("O-100"));
```

An important question in **Observability** is: which thread does the listener receive the event on, does it see the publisher's active `traceId`/`spanId`, and does Spring automatically create a new span for the event?

With Spring Framework's default `SimpleApplicationEventMulticaster`, the answer is:

1. **Synchronous, same thread:** regular listeners are invoked directly on the thread that called `publishEvent(...)`. The publisher waits for listeners to finish before the publish call returns.
2. **Current context stays in scope:** if the publisher has an active trace/span via the tracing library's context mechanism, a synchronous listener generally reads **the same active context**, because there is no thread switch.
3. **No separate span is generated automatically:** normal publishing/dispatching **does not mean Spring creates a new observation or child span for each listener**. Spring Framework does not automatically add Observations for `@EventListener` by default.
4. **No trace by default:** if the publisher has no active span, the listener does not suddenly gain a valid trace merely because it was invoked synchronously.
5. **When changing the dispatch mechanism**, especially `@Async` or configuring an async task executor on the multicaster, context propagation must be re-evaluated.

This is a very useful property: logs/telemetry from synchronous listeners can be correlated with the event-publishing operation without manually adding `traceId` to every domain payload. Yet there are boundaries: **same trace does not mean the listener has its own span**, **same thread does not mean the transaction has committed**, and **trace context is not authorization metadata**.

## 2. Distinguishing trace, span, and context

| Concept | Meaning | Relation to synchronous listener |
| --- | --- | --- |
| `traceId` | Identifies a trace, linking spans belonging to the same processing chain | If sharing the active span, the listener sees the same `traceId` |
| `spanId` | Identifies a specific span | If the listener creates no new span, usually the same `spanId` as the publisher |
| `parentSpanId` | Parent–child link in the trace tree | A child span exists only when instrumentation actually creates one |
| **Active/current span** | The span attached to the current execution context | A synchronous listener can access the same active span while the scope stays open |
| **Trace context** | Information such as `SpanContext` and propagation state | Can be read from the tracing API; does not always contain a valid span |
| **Baggage** | Metadata carried along the trace context per app/tracing conventions | Use carefully because it can cross system boundaries |
| **MDC logging context** | Data in a thread-local map added to logs | May match the publisher in a sync listener if logging integration is configured |
| **Business correlation ID** | Application-defined workflow/domain identifier | Can differ from `traceId` and have a longer lifecycle than a single trace |

A trace can contain multiple spans. For example, an HTTP request has a server span and a database call has a child client span. Simply calling an uninstrumented synchronous Java method runs that method **inside the caller's active span**, rather than turning it into a separate span.

Therefore, the following lines do not prove a dedicated span exists for the listener:

```text
traceId=abc... spanId=123...  OrderService publishing
traceId=abc... spanId=123...  OrderListener handling
```

Both logs having the same `spanId` can be completely accurate: the listener is doing work inside the request or use-case span that published the event.

Conversely, if the system intentionally creates a child span inside the listener:

```text
traceId=abc... spanId=123...  OrderService publishing
traceId=abc... spanId=456...  OrderListener handling
parentSpanId=123...         Child span created by explicit instrumentation
```

Then both logs still share the same trace, while the listener has a different `spanId`. You should not enforce a test rule that "`spanId` must always be equal" across every system; that holds only when **no instrumentation layer creates a new span**.

## 3. Why does Spring Application Events preserve context by default?

According to the Spring Framework documentation, when no dedicated task executor is specified, `SimpleApplicationEventMulticaster` dispatches listeners **synchronously on the calling thread**. From the application's perspective:

```text
Thread: http-nio-8080-exec-1
|
+-- HTTP observation/span is active
    |
    +-- OrderService.placeOrder(...)
        |
        +-- publisher.publishEvent(OrderSubmitted)
            |
            +-- OrderAuditListener.on(...)
            |       -> same thread
            |       -> sees the current active span
            |
            +-- OrderMetricsListener.on(...)
            |       -> same thread
            |       -> sees the current active span
            |
            +-- publishEvent(...) returns
        |
        +-- OrderService continues
    |
    +-- HTTP span ends at the corresponding boundary
```

With the common ThreadLocal-based mechanism, the value attached to the current thread remains valid as the Java call stack enters the listener and returns. There is no need to place context into a queue for a thread switch, because no thread hand-off happens.

Technology layers that may be involved:

- **OpenTelemetry Java:** `Context.current()` and `Span.current()` access the current context/span; in the default configuration, context storage uses ThreadLocal; `Scope` closes to restore the previous context.
- **Micrometer Tracing:** `Tracer.currentSpan()` accesses the current span; the backend can be OpenTelemetry or Brave.
- **Micrometer Observation:** an `Observation` may be active at the HTTP/service boundary; how it bridges to spans depends on the tracing configuration.
- **SLF4J/Logback MDC:** `traceId`/`spanId` information can be updated by logging integration; merely enabling Spring Events does not automatically populate MDC trace fields.

**The word "generally" matters:** context preservation depends on a valid active context having been created and still being in scope, and on the listener not clearing or replacing the context itself. If the publisher has no active span, the synchronous listener likewise sees an invalid or empty context.

## 4. Three technical consequences of "synchronous"

### 4.1. The listener runs before `publishEvent` returns

Example:

```java
System.out.println("BEFORE");
publisher.publishEvent(new OrderSubmitted("O-100"));
System.out.println("AFTER");
```

If a synchronous listener prints `HANDLED`, the conceptual output order is:

```text
BEFORE
HANDLED
AFTER
```

This illustrates the case with only that listener and no exceptions. With multiple listeners, invocation order can be affected by `@Order`; with async, completion order can differ.

### 4.2. The listener consumes the publisher's time

If the listener makes an external API call that takes 2 seconds, the publish call inside the request can block accordingly. Synchronous execution keeps trace context simple, but **is not free in terms of latency**. Evaluate which listeners genuinely belong on the request path.

### 4.3. Exceptions can propagate back to the publisher

In the default configuration without an `ErrorHandler` to suppress them, exceptions from a synchronous listener can escape `publishEvent(...)` and fail the calling flow. If instrumentation needs to mark the span as errored, the exception must be recorded where responsibility lies, rather than relying on automatic listener span creation.

**Do not assert that a failing listener always rolls back the DB:** rollback also depends on transaction boundaries, exception types, the transaction manager, and previously executed code.

## 5. Spring does not auto-create observations for `@EventListener`

This is a very easy point to misunderstand when viewing a trace UI.

The **Spring Framework Observability Support** documentation states that the framework **does not contribute Observations for `@EventListener` invocations** by default. The reason relates to event listener instrumentation semantics. Having a listener inherit the current observation/span does not mean the framework creates spans such as:

```text
server.request
   |
   +-- application.event.publish (NOT created by default)
        |
        +-- order.listener (NOT created by default)
```

If a dashboard shows an `order.listener` span, determine whether that span was created by **custom instrumentation, `@Observed`, AOP, an agent, or a third-party library**, rather than attributing it to the event framework.

Sensible approaches:

1. **Want the same trace without a new span:** use the default synchronous listener and ensure the publisher has an active context. This is the minimal option.
2. **Want to measure listener duration independently:** explicitly instrument valuable operations using the Observation API or tracing spans with clear scopes.
3. **Want to attach a lightweight event to the current span:** consider span events/annotations with allowed information; avoid creating thousands of spans for trivial events.
4. **Want to measure every listener system-wide:** evaluate overhead, cardinality, semantics, sampling rates, and event types rather than blindly auto-instrumenting every event.

Principle: a new child span should represent **a unit of work worth measuring**, not necessarily every dispatch callback.

## 6. Runnable Java 17, Spring Framework, and OpenTelemetry example

To observe the behavior with verifiable data rather than assumptions, we create an active trace/span directly in code, publish a Java record through Spring, and inspect the span context inside the listener.

Versions used in the example:

- Java 17+.
- Spring Framework `spring-context:6.2.12`.
- OpenTelemetry Java `opentelemetry-api:1.43.0` and `opentelemetry-sdk-trace:1.43.0`.
- Maven.

This is a **standalone demo** using the OpenTelemetry SDK directly; a production Spring Boot application typically configures OpenTelemetry/Micrometer via starters, agents, or appropriate instrumentation infrastructure. The goal of the demo is to verify **in-thread context propagation**, not exporting telemetry to a collector.

### 6.1. Project structure

```text
sync-event-trace/
├── pom.xml
└── src/main/java/demo/SyncEventTraceDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>sync-event-trace</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>io.opentelemetry</groupId>
            <artifactId>opentelemetry-api</artifactId>
            <version>1.43.0</version>
        </dependency>
        <dependency>
            <groupId>io.opentelemetry</groupId>
            <artifactId>opentelemetry-sdk-trace</artifactId>
            <version>1.43.0</version>
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
                    <mainClass>demo.SyncEventTraceDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/SyncEventTraceDemo.java`:

```java
package demo;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanContext;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.context.Scope;
import io.opentelemetry.sdk.trace.SdkTracerProvider;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;

public final class SyncEventTraceDemo {

    public record OrderSubmitted(String orderId) {}

    public static final class AuditListener {
        private SpanContext observed;
        private Thread observedThread;

        @EventListener
        public void onOrderSubmitted(OrderSubmitted event) {
            observed = Span.current().getSpanContext();
            observedThread = Thread.currentThread();
            System.out.println("LISTENER_VALID=" + observed.isValid());
            System.out.println("EVENT_ID=" + event.orderId());
        }

        public SpanContext observed() {
            return observed;
        }

        public Thread observedThread() {
            return observedThread;
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        @Bean
        public AuditListener auditListener() {
            return new AuditListener();
        }
    }

    public static void main(String[] args) {
        SdkTracerProvider provider = SdkTracerProvider.builder().build();
        try {
            Tracer tracer = provider.get("sync-event-demo");

            try (var context =
                    new AnnotationConfigApplicationContext(Config.class)) {
                AuditListener listener = context.getBean(AuditListener.class);
                Span publisherSpan =
                        tracer.spanBuilder("submit-order").startSpan();

                try (Scope ignored = publisherSpan.makeCurrent()) {
                    SpanContext published =
                            Span.current().getSpanContext();
                    Thread publisherThread = Thread.currentThread();

                    System.out.println(
                            "PUBLISHER_VALID=" + published.isValid());
                    context.publishEvent(new OrderSubmitted("O-100"));

                    // Valid immediately after publish only because default dispatch is synchronous.
                    SpanContext observed = listener.observed();
                    if (observed == null) {
                        throw new IllegalStateException(
                                "Listener did not receive event");
                    }
                    System.out.println(
                            "SAME_TRACE=" + published.getTraceId()
                                    .equals(observed.getTraceId()));
                    System.out.println(
                            "SAME_SPAN=" + published.getSpanId()
                                    .equals(observed.getSpanId()));
                    System.out.println(
                            "SAME_THREAD=" + (publisherThread
                                    == listener.observedThread()));
                } finally {
                    publisherSpan.end();
                }
            }
        } finally {
            provider.shutdown();
        }
    }
}
```

Run command:

```bash
mvn -q compile exec:java
```

Lines printed by the program:

```text
PUBLISHER_VALID=true
LISTENER_VALID=true
EVENT_ID=O-100
SAME_TRACE=true
SAME_SPAN=true
SAME_THREAD=true
```

### 6.2. Explaining why the results are true

1. `SdkTracerProvider` is configured as a minimal SDK tracer provider. The demo starts a span named `submit-order` and then calls `publisherSpan.makeCurrent()` to bind it to the active OpenTelemetry context on the main thread.
2. `Span.current().getSpanContext()` in the publisher contains a valid `traceId` and `spanId` because it is within the scope of the newly created SDK span.
3. `AnnotationConfigApplicationContext` uses the default synchronous event multicaster. When `publishEvent(OrderSubmitted)` calls `AuditListener.onOrderSubmitted(...)`, the listener executes on **the same Java thread**.
4. The listener only **reads** `Span.current()` without creating another span, so `traceId` and `spanId` match the publisher. That explains `SAME_TRACE=true` and `SAME_SPAN=true`.
5. The listener finishes before `publishEvent` returns; thus after publishing we can read `listener.observed()` without a latch or future.
6. `try-with-resources` ensures `Scope.close()` restores the previous context; `publisherSpan.end()` ends the span; `provider.shutdown()` releases the SDK provider.

**Note:** the demo does not attach a `SpanExporter`, so it does not send data to Jaeger/Tempo/Zipkin or print raw trace IDs. The output only proves the context is **active in-process**. In a real application, creating spans and exporting traces to a backend also depend on the sampler, exporter, collection pipeline, and tracing instrumentation.

### 6.3. Why check all three: `SAME_TRACE`, `SAME_SPAN`, and `SAME_THREAD`?

If you only print `traceId`, these two situations are easily confused:

- **Same span:** the listener creates no new span and simply inherits the publisher's active span.
- **Child span:** the listener is instrumented and gets a different span ID, while keeping the same trace ID and proper parent.

Checking `SAME_THREAD` confirms synchronous behavior at the execution-thread level. It does not prove every production setup is synchronous: changing `SimpleApplicationEventMulticaster.setTaskExecutor(...)` or adding `@Async` can change the outcome.

Checking `SAME_SPAN` in the demo is **intentional**, to demonstrate that Spring events **do not auto-generate a span**. Do not turn that into a mandatory assertion for listeners that deliberately create their own spans.

## 7. Micrometer Tracing in Spring Boot: inspecting the current span

In a Spring Boot application configured with Micrometer Tracing, you can inject `io.micrometer.tracing.Tracer` into a bean and inspect `currentSpan()`.

Example in a Spring bean with a configured `Tracer` (illustrative snippet, **not part of the Maven program in section 6**):

```java
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.context.event.EventListener;

public class PaymentEventObserver {
    private final Tracer tracer;

    public PaymentEventObserver(Tracer tracer) {
        this.tracer = tracer;
    }

    @EventListener
    public void onPaymentCompleted(PaymentCompleted event) {
        Span span = tracer.currentSpan();
        if (span == null) {
            // No active span at the moment the listener runs.
            return;
        }

        String traceId = span.context().traceId();
        String spanId = span.context().spanId();
        // Record controlled telemetry if genuinely needed.
    }
}
```

This snippet requires the application's `PaymentCompleted` type, proper bean registration, and appropriate Micrometer Tracing dependencies. It **does not** guarantee a span is always present: events may be published from a scheduled job or an uninstrumented entrypoint.

If the application uses the OpenTelemetry API directly, the corresponding syntax is:

```java
SpanContext sc = io.opentelemetry.api.trace.Span
        .current().getSpanContext();
if (sc.isValid()) {
    String traceId = sc.getTraceId();
    String spanId = sc.getSpanId();
}
```

With Micrometer, `currentSpan() == null` is a common indicator of no active span; with OpenTelemetry, `Span.current()` can return an invalid span context instead of `null`. **Do not mix the null/invalid rules of the two APIs.**

### Should a handler read `traceId` and put it back into a domain event?

Usually **no**, if the goal is merely log/trace correlation across synchronous listeners in the same scope. The current context is sufficient for tracing integrations to use.

If the event must be persisted, sent through a queue, or processed after the request finishes, design dedicated correlation/provenance metadata per requirements and use standard tracing propagation at transport boundaries. Do not force business payloads to carry `traceId` just because a synchronous callback runs.

## 8. Preserving trace context does not mean Spring propagates business data

A distinction to maintain:

```text
Execution context: current span, tracing baggage, MDC, security/threadlocals
Domain event payload: orderId, amount, occurredAt, tenantId, actorId
```

In a synchronous listener, execution context on the same thread generally remains intact **within the current scope**. However, the event payload is still business data that must be constructed explicitly. **Never derive `tenantId` or `actorId` merely by inspecting `traceId`**; tracing IDs have no authentication/authorization semantics.

For example, logs may share a trace yet process the wrong tenant if a service reads the tenant from an untrusted header; observability does not enforce data access permissions.

If you need to audit who emitted an event or which tenant owns the transaction, place **verified identifiers** in the appropriate event/envelope. If you only need to track the runtime relationship between publisher and listener, the runtime trace context is usually sufficient.

### Trace context can contain baggage

Baggage can propagate across boundaries and end up in logs/spans depending on configuration. Avoid placing access tokens, sessions, emails, card numbers, PII, or secrets into baggage. Same-thread preservation of baggage does not make that data any safer.

## 9. Spring `@EventListener` is not a dedicated tracing tool

`@EventListener` is a way to register a method to listen for events, for example:

```java
@EventListener
public void on(OrderSubmitted event) {
    // Listener logic; event object is supplied by the publisher.
}
```

This annotation **does not establish a root span**. It does not imply `@Observed` or `@WithSpan` is applied.

To identify a unit of work with its own span, you can use the tracing API when observability value justifies it. OpenTelemetry **illustrative** example:

```java
public void handleWithSpan(OrderSubmitted event, Tracer tracer) {
    Span child = tracer.spanBuilder("order.audit").startSpan();
    try (Scope scope = child.makeCurrent()) {
        // Perform audit; child takes current span as parent by default
        // if the publisher still has an active span.
        writeAudit(event);
    } catch (RuntimeException ex) {
        child.recordException(ex);
        child.setStatus(StatusCode.ERROR);
        throw ex;
    } finally {
        child.end();
    }
}
```

This snippet is not standalone: it requires `Tracer`, `Span`, `Scope`, `StatusCode`, and `writeAudit(...)` in an appropriate class. `child` shares `traceId` with the parent, while having its own `spanId`.

**Timing of child span creation matters:** calling `spanBuilder(...).startSpan()` while the parent is still active causes the new span to inherit the parent automatically. Accidentally creating the child after the parent scope has closed can start a new root span and break the trace.

### Use a span event instead of a child span when minimal data is needed

If you only want to note "the order event was dispatched" on the parent span:

```java
Span.current().addEvent("order.submitted");
```

This is an illustrative OpenTelemetry API snippet. Avoid stuffing the entire `OrderSubmitted` object or private data into span event attributes. This is a **telemetry event** inside a span, **distinct** from Spring's domain `ApplicationEvent`.

Also, if there is no valid recording span at that moment, this call may produce no visible data in the tracing backend.

## 10. Logging configuration: why can `traceId`/`spanId` appear in MDC?

When an application uses a tracing bridge/integration supporting correlation, log formats can add fields:

```text
traceId=4c8d... spanId=a2f1... OrderService publish OrderSubmitted
traceId=4c8d... spanId=a2f1... OrderAuditListener handled OrderSubmitted
```

Within the same scope and same thread, both logs can carry the same values. Yet log MDC and the active span **are not the same API**:

- **Tracing context:** the source tracing libraries use to determine the active span and parent-child relationships.
- **MDC:** a map loggers use to inject fields into logs; many setups use ThreadLocal.
- **Log pattern:** determines which MDC fields actually appear on stdout/in log files.
- **Sampling/export:** determines which span data is actually sent to the tracing backend.

Not seeing `traceId` in logs is not enough to conclude the active span was lost; the log pattern might omit it, the tracing bridge might be unconfigured, or a tool might use different field names. Conversely, seeing `traceId` in MDC does not guarantee a **valid recording span** is currently active: MDC can retain stale values if cleanup fails.

### How to verify accurately

Inside the listener, compare the **tracing API** (`currentSpan()`/`Span.current()`) with **MDC** at the exact same moment. If they disagree, inspect scope lifecycle, instrumentation, and logging integration before blaming Spring Events.

Do not rely on a log screenshot containing a fixed traceId to verify source code; real trace IDs change on every run.

## 11. Trace context can change inside a synchronous callback

Running on the same thread does not mean the context is immutable throughout the call stack.

Example:

```text
Publisher span: order.submit (spanId=P)
    |
    +-- publishEvent(OrderSubmitted)
            |
            +-- AuditListener
                    |
                    +-- startSpan("audit.write")
                            -> current spanId=C inside nested Scope
                    |
                    +-- close Scope
                            -> current spanId=P again
            |
            +-- publishEvent returns
                    -> current spanId=P
```

If child spans are created and closed properly, the parent is restored. However, if a listener:

- forgets to close `Scope`,
- calls a tracing API that binds a new context without restoring it,
- modifies MDC without restoring it,
- triggers nested events inside a different child span,

then subsequent listeners or the publisher may observe unexpected context. **This is not synchronous dispatch breaking**; the listener code itself mutated thread-local context.

A safe rule:

```java
Span span = tracer.spanBuilder("some-operation").startSpan();
try (Scope scope = span.makeCurrent()) {
    doWork();
} finally {
    span.end();
}
```

This is a snippet requiring actual `tracer`/`doWork()` symbols and OpenTelemetry imports. `try-with-resources` guarantees `Scope.close()` even when `doWork()` throws an exception; `finally` ends the span.

**Never cache `Span.current()` in a singleton field for reuse across other requests.** "Current" means at the current scope/moment, not global application state.

## 12. When the publisher has no active trace

Not every event is published from an instrumented HTTP request. Examples:

- A `@Scheduled` job running an uninstrumented operation.
- A CLI command running on a background thread.
- A message consumer not configured with tracing instrumentation.
- A test creating a plain `AnnotationConfigApplicationContext`.
- A domain event emitted after a scope has already closed.

In those cases, a synchronous listener still runs on the same thread, but has no valid span to inherit. Do not "fix" it by generating a random ID and putting it as `traceId` in logs: without a valid span/trace context, that ID will not form a valid trace in the backend.

Two sensible paths:

1. **No trace required:** process normally; use a business correlation ID when auditing is needed.
2. **Need to observe background work:** create an observation/root span at a **meaningful boundary**, set its scope, and close it properly; synchronous events inside will inherit it.

If you want a trace linking a request to a batch/job running hours later, do not keep an HTTP request's ThreadLocal or span open for hours. Use context propagation/links and a new unit of work with an explicit tracing contract.

## 13. Comparing sync and async: the key boundary is thread hand-off

| Scenario | Same thread? | Can read publisher's active trace? | Notes |
| --- | --- | --- | --- |
| Default `@EventListener` with `SimpleApplicationEventMulticaster` | **Yes** | **Yes**, if scope is active | Spring does not auto-create a listener span |
| Synchronous listener creating a child span | Yes | Yes, same trace; new spanId inside child scope | Must close scope |
| Event publisher with no active span | Yes | No valid span to inherit | Start a span at a suitable boundary if needed |
| `@Async @EventListener` | **Usually no** | Not guaranteed without propagation | Async proxy/task executor governs execution |
| Custom multicaster with async executor | **Usually no** | Not guaranteed without propagation | Use controlled context propagation |
| `@TransactionalEventListener(AFTER_COMMIT)` | Can be same thread during transaction callback | **Depends on commit timing and scope** | Does not automatically retain old request/span context |
| Event sent to a message broker | Different process/worker | Needs propagation via message metadata | Java ThreadLocal does not cross the network |

Key takeaway: **synchronous execution avoids thread hand-off**, but it is not a permanent guarantee across every listener configuration.

### Can one publish call run listeners across different threads?

By default Spring Framework does not do this. However, an application can register an `applicationEventMulticaster` bean with a different `TaskExecutor`:

```java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster applicationEventMulticaster(
        ThreadPoolTaskExecutor executor) {
    var multicaster = new SimpleApplicationEventMulticaster();
    multicaster.setTaskExecutor(executor);
    return multicaster;
}
```

This is an illustrative configuration snippet requiring Spring `@Configuration`, `@Bean`, a `ThreadPoolTaskExecutor` bean, and imports. Under this setup, listeners **supporting async dispatch** can run on another worker thread. Certain lifecycle/transaction listeners have special semantics, so do not assume every listener moves to the executor.

With Spring Framework's `ContextPropagatingTaskDecorator` and Micrometer Context Propagation, a properly configured executor can capture and restore supported contexts at task submission time. Since this article focuses on **synchronous events**, this decorator is unnecessary here; adding it in the wrong place can add overhead or mislead learners into thinking async context is always preserved automatically.

## 14. The `@TransactionalEventListener` case: same thread does not guarantee same span

A `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` can execute its callback when the transaction commits, not necessarily right on the `publishEvent` line.

Suppose:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderCommitted(OrderSubmitted event) {
    // Runs in the AFTER_COMMIT transaction phase.
}
```

This is an illustrative snippet inside a Spring bean with a transaction manager. If transaction commit happens while the HTTP/service span is still active, the listener can see that context. If the application changes scopes or the callback runs at a different boundary, preservation is not guaranteed solely because of the word "transactional".

Verify:

- Where the callback actually runs relative to the span's scope.
- Whether reactive transactions are used; Reactor Context differs from ThreadLocal and needs appropriate handling.
- Whether the listener uses `@Async` or invokes another executor internally.
- Whether reading `traceId` serves observability or is mistakenly used as transaction identity.
- Whether data requiring long-term retention is stored in a suitable event envelope.

**Do not treat `@TransactionalEventListener` as a mechanism for automatically keeping a tracing scope alive after the publisher ends**, nor infer commit/delivery guarantees from the presence of a trace.

## 15. Handling exceptions, span status, and logs when a listener fails

When a synchronous listener throws an exception, the publish call can fail. If the publisher has an active span, external tracing instrumentation may record the error **if configured**. Spring Events does not commit to attaching exceptions to the current span on its own.

Illustrative example in a listener or service with OpenTelemetry:

```java
try {
    handleOrder(event);
} catch (RuntimeException ex) {
    Span current = Span.current();
    if (current.isRecording()) {
        current.recordException(ex);
        current.setStatus(StatusCode.ERROR);
    }
    throw ex;
}
```

This is a snippet requiring appropriate `handleOrder`, `event`, `Span`, and `StatusCode`. It modifies telemetry only on the **current span**, which may be the publisher's span if the listener does not create its own. Recording an error on the shared span may be what you want, or it may mark the parent span failed even when the application has a recovery policy. Choose semantics based on business rules.

If a listener fails yet the application can continue, evaluate the multicaster's error policy, retries, or handling logic. Never assume "if a listener fails, the trace automatically reports an error" or "same trace means the transaction automatically rolls back".

## 16. Testing synchronous event trace context properly

The complete example in section 6 is an **integration smoke test** of Spring event dispatch and OpenTelemetry context. In a larger project, you can add a JUnit test to prevent regressions if someone switches the multicaster from synchronous to async.

Worthwhile assertions:

- Publisher has a valid active span before publishing.
- Listener is invoked **before** publish returns.
- Listener and publisher share the same `traceId`.
- Without separate listener instrumentation, both share the same `spanId`.
- Listener runs on **the same Java thread**.
- Nested spans created by the listener close properly and restore the current span.
- When the publisher has no span, the listener does not magically see a valid span.
- Listener exceptions are handled per policy and scopes do not leak.
- When async is intentionally enabled in tests, propagation is configured and verified explicitly; do not force async to assert same-thread execution.
- When logging changes, log correlation is not lost due to MDC bridge/pattern issues.

### Testing observable outcomes without depending on specific UUIDs

A robust test never compares `traceId` to a hardcoded hex string: each run generates new IDs. Instead:

```java
assertTrue(publisherContext.isValid());
assertTrue(listenerContext.isValid());
assertEquals(
        publisherContext.getTraceId(),
        listenerContext.getTraceId());
assertEquals(
        publisherContext.getSpanId(),
        listenerContext.getSpanId());
```

This illustrates JUnit assertions requiring JUnit dependencies and two captured `SpanContext` values. For an async listener that intentionally creates a child span, assert matching `traceId` and parent/link relationships per design rather than requiring identical `spanId`s.

### Testing when there is no trace

Publish `OrderSubmitted` outside any span scope in an isolated test. In a clean process using the OpenTelemetry API, `Span.current().getSpanContext().isValid()` is typically false. Avoid assuming it is always false if a test runner agent/instrumentation automatically starts spans; control the test environment and scopes.

## 17. Debugging when a listener's `traceId` differs from the publisher's

An ordered diagnostic checklist:

1. **Read the event multicaster configuration:** is there a custom `applicationEventMulticaster` or task executor?
2. **Check `@Async`:** does the listener method or an inner service offload work to another executor?
3. **Check the current span via API**, not just MDC or log patterns.
4. **Check Scope lifecycle:** did the publisher close the scope before the listener ran?
5. **Check if the listener creates a new span:** same `traceId` with a different `spanId` can be completely valid.
6. **Check nested events:** another callback may temporarily swap the current span and must restore it.
7. **Check instrumentation setup:** are SDK/tracer bridges and samplers configured, or is it just the no-op API?
8. **Check logging correlation:** is the MDC config missing trace/span fields or cleaning up incorrectly?
9. **Do not assume transaction phase** matches publish time.
10. **If crossing a broker/async boundary**, inspect extraction/injection, header propagation, and transport-level context restoration.
11. **Do not use `traceId` to derive user/tenant** if that information lacks a proper contract/protection.

Symptom table:

| Symptom | Possibilities to check | Remediation |
| --- | --- | --- |
| `traceId` present on publisher, missing on listener | Listener ran out of scope or on a worker thread | Check dispatch, scope, task decorator |
| Same `traceId`, different `spanId` | Listener/custom instrumentation created a child span | Check parent/child; do not treat as an error by default |
| Same `traceId` and `spanId`, yet no "listener span" | Framework does not auto-create an Observation for `@EventListener` | Instrument explicitly if duration needs measuring |
| Neither side has a valid span | Tracing instrumentation or scope is missing | Start a trace at a meaningful boundary |
| Logs lack `traceId` while API has a span | MDC bridge/log pattern | Check logging configuration |
| `traceId` changes after callback | Scope not restored or listener opened its own context | Close `Scope` in `finally`/try-with-resources |
| Flaky async test | Reading results before the task finishes | Wait with latch/future and explicit timeout |
| Continuous trace yet wrong tenant | Using trace context instead of auth/tenant logic | Fix authorization and event business metadata |

## 18. Optimizing observability and avoiding redundant telemetry

Not every domain event deserves its own span. When a single request emits hundreds of ultra-fast internal events, instrumenting every dispatch can increase:

- CPU and allocations from creating spans/observations.
- Volume of traces to export and store.
- Attribute cardinality when storing event IDs/user IDs as labels.
- Noise when viewing flame graphs.
- Risk of leaking business data through the tracing backend.

A balanced practice:

- Use the **existing active span** to correlate synchronous listeners.
- Create child spans for genuinely slow listeners, system boundaries, significant I/O operations, or business steps needing timing.
- Use business metrics (counters/timers) with controlled **low-cardinality labels**, without putting raw `orderId` or `userId` into every metric tag.
- Record necessary trace attributes using an allowlist, avoiding secrets.
- Ensure traces have accurate lifecycles (scopes closed, spans ended).
- Distinguish span duration from **total time in `publishEvent`**; listener count and ordering affect total duration.
- Evaluate sampling and storage efficiency before increasing instrumentation granularity.

## 19. Common mistakes

1. **Assuming `@EventListener` creates a span automatically.** Spring Framework does not instrument every event listener with an Observation by default.
2. **Confusing `traceId` and `spanId`.** Same `traceId` with different `spanId` can be a valid parent-child relationship.
3. **Assuming same thread always means a trace exists.** If the publisher has no active span, the listener has nothing to inherit.
4. **Assuming same thread means Spring propagated across the network.** There is no network hand-off in synchronous execution.
5. **Looking only at MDC and declaring a span valid.** MDC may be disconnected from tracing or hold stale values.
6. **Forgetting to close `Scope` after opening a child span.** Corrupts current context for subsequent listeners or the caller.
7. **Storing `Span.current()` in a singleton field.** Mixes requests and causes races.
8. **Enabling `@Async` without checking context propagation.** Current ThreadLocals usually do not cross executor boundaries automatically.
9. **Putting raw `traceId` into domain events solely for synchronous logging.** Increases coupling unnecessarily when current context already suffices.
10. **Using `traceId` as a business key or tenant ID.** Trace is an observability identifier, not business ownership.
11. **Logging full event payloads or baggage.** May leak PII, tokens, or internal data.
12. **Catching exceptions without updating span status.** Can cause traces to report success or failure contrary to desired semantics.
13. **Assuming `@TransactionalEventListener(AFTER_COMMIT)` always keeps the HTTP span.** It runs per transaction phase and does not guarantee tracing scope.
14. **Comparing against fixed raw `traceId` strings in tests.** IDs change per run; compare correlation instead.
15. **Seeing a trace with complete logs and inferring the event was durably saved.** Spring Application Events are an in-process mechanism and do not provide outboxes/retries on their own.
16. **Adding spans to every listener without measuring overhead.** Can raise observability costs without improving diagnostic clarity.

## 20. Checklist for applying to a Spring application

- [ ] Are events dispatched by the default synchronous multicaster or with an executor?
- [ ] Does the listener use `@Async` or spawn tasks itself?
- [ ] Does the publisher have an active span/observation at `publishEvent(...)` time?
- [ ] Have you distinguished the tracing API from MDC/log patterns?
- [ ] Do you need the same trace or a child span to measure duration independently?
- [ ] If a child span is created, is the scope restored and the span ended properly?
- [ ] For transaction-phase listeners, have you checked whether the scope is still active at callback time?
- [ ] If there is a hand-off, is propagation configured at the right boundary?
- [ ] Are event payloads free of secrets, PII, runtime span objects, and thread-local references?
- [ ] Is there a test verifying that the current `traceId` in a synchronous listener matches the publisher?
- [ ] Are there tests for missing active spans and listener exceptions?
- [ ] Are metric/trace attribute cardinality and costs managed?

**Summary:** When Spring Application Events run **synchronously**, regular listeners are invoked directly on the publisher's thread. If a span is active in that scope, listeners can see **the same trace context** without propagating context across an executor; if there is no span, none appears automatically. Spring **does not create an Observation/child span for `@EventListener` by default**, so having the same `traceId` and `spanId` is normal. Adding a separate span requires intentional instrumentation, proper `Scope` management, and separating operational observation from business event semantics.

## References

- [Spring Framework Reference — Observability Support, Application Events and @EventListener](https://docs.spring.io/spring-framework/reference/integration/observability.html)
- [Spring Framework Reference — Additional Capabilities of ApplicationContext](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring Framework 6.2 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [OpenTelemetry Java — Record Telemetry with API](https://opentelemetry.io/docs/languages/java/api/)
- [OpenTelemetry Specification — Context](https://opentelemetry.io/docs/specs/otel/context/)
