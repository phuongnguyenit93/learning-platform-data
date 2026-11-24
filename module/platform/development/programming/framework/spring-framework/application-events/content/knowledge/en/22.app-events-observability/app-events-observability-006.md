# Trace Context for Asynchronous Events in Spring Framework

## 1. Why can a trace "break" when handling events on another thread?

In a **Spring Framework Application Events** system, an event is often published from an HTTP request, background job, or use case carrying observability data such as **trace ID**, **current span**, **correlation ID**, **baggage**, and logger **MDC** fields. When a listener runs **synchronously on the same thread**, values attached to **ThreadLocal** generally remain available.

However, if Spring dispatches the listener to an **executor thread**, or the listener method is annotated with **@Async**, the receiving thread **does not automatically inherit ThreadLocals** from the publishing thread. Common consequences:

- Publisher logs carry **traceId/spanId**, while listener logs lack them or show a new unrelated trace.
- APM/tracing shows a gap between request handling and the event-consuming task.
- Processing time, errors, and spans from the same workflow cannot be linked.
- Correlation/tenant fields stored in ThreadLocal can vanish or, if copied improperly, **leak across tasks** in the thread pool.
- Operators mistakenly assume the listener never ran, even though it completed while losing linkage metadata.

**Trace context propagation** is the process of **capturing context at task submission**, **restoring appropriate context within the scope of execution on the worker thread**, and **restoring the previous state** when processing finishes. In Spring Framework 6.1+, the standard tool for **TaskExecutor**s is **ContextPropagatingTaskDecorator**, paired with the **Micrometer Context Propagation** library.

Lesson goals: understand precisely **why context breaks**, **where to configure propagation**, **verify it with a runnable Java 17+ example**, and **avoid confusing context propagation with span creation, transaction propagation, or guaranteed delivery**.

## 2. Types of "context" easily confused

| Concept | Purpose | Crosses thread pools automatically? |
| --- | --- | --- |
| **Trace ID** | Identifies an end-to-end trace spanning multiple spans | No if stored only in ThreadLocal without propagation |
| **Span ID / current span** | Identifies the current span or span context | Requires proper capture/restore of tracer/observation context |
| **MDC** (Mapped Diagnostic Context) | Adds fields to logs, often `traceId`, `spanId`, `requestId` | Usually thread-local; does not transfer to executors automatically |
| **Correlation ID** | Links operations of the same business action/request; can be an event field | If only in ThreadLocal, no; if a payload field, readable directly |
| **Baggage** | Metadata allowed to travel with trace context | Requires configured propagation; limit size and sensitive data |
| **SecurityContext** | Spring Security authentication/authorization data | Requires a dedicated security mechanism; not automatic via tracing decorator alone |
| **Transaction context** | Transaction manager, resource bindings, and synchronizations | **Not** transferred to worker threads merely because trace context propagated |
| **Reactor Context** | Context of a reactive pipeline | Distinct from ThreadLocal; needs Reactor bridges/mechanisms across reactive–imperative boundaries |

**Trace ID and correlation ID are not fully equivalent.** A trace ID is managed by a tracer and carries trace/span hierarchy semantics. A correlation ID is a business or log-support key that can be carried via event payloads or headers. An example using a String **trace-like ID** demonstrates ThreadLocal propagation capability only; it **does not create a real distributed trace on its own**.

**MDC is not a tracer either.** Copying a **traceId** string into MDC can make logs easier to search, but without a tracer managing the current span, an APM system will not necessarily have spans or parent-child relationships.

## 3. Spring's default: synchronous events, no automatic thread split

Spring `ApplicationContext` typically uses **SimpleApplicationEventMulticaster** to dispatch application events. **By default, the multicaster dispatches synchronously** on the caller's thread; **publishEvent(...)** normally returns only after synchronous listeners finish.

~~~text
HTTP/request Thread                    Default event listener
----------------------------------     -------------------------------
current trace/span = T, S
MDC traceId = T
  |
  +-- publishEvent(OrderCreated)
          |
          +-------------------------> @EventListener on(OrderCreated)
                                      (same thread)
                                      current trace/span may still be available
                                      MDC is also this thread's context
          |
          +-- listener returns
  |
  +-- request continues
~~~

In this configuration, you **do not need a TaskDecorator just to cross a synchronous event listener** because there is no thread boundary. However, Spring Framework **does not create an Observation/span by default for each @EventListener invocation**; preserving context on the same thread only grants access to the current context, and does not mean a dedicated listener span exists.

### When does a thread boundary appear?

**Case A — multicaster configured with an executor:**

~~~java
@Bean(name = "applicationEventMulticaster")
SimpleApplicationEventMulticaster multicaster(TaskExecutor eventExecutor) {
    SimpleApplicationEventMulticaster m =
            new SimpleApplicationEventMulticaster();
    m.setTaskExecutor(eventExecutor);
    return m;
}
~~~

This is an illustrative snippet in a Spring configuration. With an async **TaskExecutor**, many eligible application listeners run on another thread.

**Case B — individual listener annotated with @Async:**

~~~java
@Async("traceAwareExecutor")
@EventListener
public void on(OrderCreated event) {
    // Method is handed off to the executor instead of always running on the publisher thread.
}
~~~

This snippet requires **@EnableAsync**, a Spring-managed bean, a matching executor name, imports, and the event type. In both cases, the publisher's ThreadLocal values **cannot be assumed present** inside the listener.

**Important exception:** not *every* listener is allowed to run asynchronously when the multicaster has an executor. Spring has **ApplicationListener.supportsAsyncExecution()**; for instance, transaction-synchronized listeners may need to run on the publisher thread to register callbacks on the right transaction. Do not interpret a global executor configuration as "every `@TransactionalEventListener` immediately runs on a worker".

## 4. Why doesn't ThreadLocal propagate automatically?

**ThreadLocal<T>** stores values per thread. The thread calling **publishEvent(...)** may hold the current observation, tracer span, or MDC; a **ThreadPoolTaskExecutor** thread is a different thread with its own ThreadLocal map.

~~~text
Publisher thread [http-42]
  ThreadLocal("trace") = trace-abc
  |
  +-- queue event task ----------------------+
                                            |
                              Worker thread [event-1]
                                ThreadLocal("trace") = null
                                @EventListener begins processing
~~~

When using a thread pool, the worker thread can also be **reused for subsequent events**. If code sets values manually without restoring/clearing them in `finally`, event B can accidentally see event A's data. This is not just a logging bug; it can cause **cross-request/cross-tenant data leaks**.

**InheritableThreadLocal** is not a safe general fix: thread pools can create threads before requests, retain values inherited at thread creation time, and reuse those threads across many tasks. Proper trace context must be **captured when scheduling a specific task** and **restored within that task's scope**.

## 5. Standard solution: ContextPropagatingTaskDecorator

**ContextPropagatingTaskDecorator** (Spring Framework 6.1+) implements **TaskDecorator**. It uses **Micrometer Context Propagation** to capture context values that have a registered **ThreadLocalAccessor**, and restores them within the worker's task execution scope.

Model:

~~~text
Publisher thread
  current trace/observation/baggage
  |
  +-- executor.execute(task)
          |
          v
     ContextPropagatingTaskDecorator
          -> capture ContextSnapshot at the scheduling boundary
          -> wrap Runnable
                    |
                    v
               Worker thread
                 -> restore context
                 -> invoke listener
                 -> restore/cleanup previous worker context
~~~

Required dependencies when using this decorator:

~~~groovy
dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'io.micrometer:context-propagation:1.1.3'
}
~~~

This is an **illustrative dependency snippet**, not a complete build file. Beyond the library, **contexts must have their corresponding accessors registered**. With Spring Boot and Micrometer Tracing configured, the framework/instrumentation typically registers appropriate accessors for Observation/trace context. For custom ThreadLocals, the application must register its own accessor for snapshots to capture it.

**Limitations:** the decorator **does not create spans**, **does not install a tracer/exporter**, **does not move transactions to another thread**, and does not automatically propagate every MDC field. It captures/restores only **context sources** that have a supporting Micrometer Context Propagation accessor. Capturing all of MDC can conflict with tracing-aware MDC management; do not blindly register a second MDC accessor when the tracer already updates MDC.

### 5.1. With an executor-backed ApplicationEventMulticaster

~~~java
@Configuration
class EventMulticasterConfig {

    @Bean
    ThreadPoolTaskExecutor eventExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }

    @Bean(name = "applicationEventMulticaster")
    SimpleApplicationEventMulticaster eventMulticaster(
            ThreadPoolTaskExecutor eventExecutor) {
        SimpleApplicationEventMulticaster multicaster =
                new SimpleApplicationEventMulticaster();
        multicaster.setTaskExecutor(eventExecutor);
        return multicaster;
    }
}
~~~

This is a **config snippet** requiring Spring imports. On a Spring-managed **ThreadPoolTaskExecutor** bean, the container automatically handles lifecycle initialization and destruction. In production, tune pool size, queue capacity, rejection policy, timeouts, and shutdown. This configuration is broad: it affects all listeners eligible for async execution across the context.

### 5.2. With individual `@Async @EventListener` methods

When only a few listeners need async execution, you can use a designated executor:

~~~java
@Configuration
@EnableAsync
class AsyncEventConfig {

    @Bean("traceAwareExecutor")
    ThreadPoolTaskExecutor traceAwareExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("trace-event-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
        return executor;
    }
}
~~~

And the listener:

~~~java
@Component
class EmailEventListener {

    @Async("traceAwareExecutor")
    @EventListener
    public void on(OrderConfirmed event) {
        // Current observation/trace context is restored if
        // appropriate Micrometer accessors and tracing configuration exist.
    }
}
~~~

These are **illustrative snippets** requiring imports, event types, and bean wiring. **@EnableAsync** is required for Spring proxy handling of **@Async**. Do not expect the annotation to work on objects instantiated with **new**, or when invoking an annotated method from the same class via self-invocation bypassing the proxy.

**Recommendation:** pick **one execution boundary** for events: either the multicaster dispatches to an executor, or specific listeners use `@Async`. Configuring both without accounting for double scheduling makes context paths, errors, and shutdown harder to reason about.

## 6. Complete Java 17+ example: verifying propagation across an async event listener

The following example runs with **Spring Framework 6.2.9**, **Micrometer Context Propagation 1.1.3**, **JDK 17+**, and **Gradle 8.x**. It deliberately uses a **ThreadLocal holding a correlation ID simulating a trace** so you can clearly observe capture/restore mechanics without setting up a tracing backend or network.

**This illustrates context propagation, not a full distributed trace:** the String **trace-42** is not a W3C trace ID, and there is no Span exporter or parent/child spans. After the demo, the next section shows how to apply this with real Micrometer Tracing.

### 6.1. Structure

~~~text
async-event-trace-demo/
  build.gradle
  src/main/java/demo/AsyncEventTraceDemo.java
~~~

Contents of **build.gradle**:

~~~groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.9'
    implementation 'io.micrometer:context-propagation:1.1.3'
}

application {
    mainClass = 'demo.AsyncEventTraceDemo'
}
~~~

### 6.2. Runnable source code

Contents of **src/main/java/demo/AsyncEventTraceDemo.java**:

~~~java
package demo;

import io.micrometer.context.ContextRegistry;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.event.EventListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncEventTraceDemo {

    // Illustrative trace-like correlation ID string, NOT a real Tracer.
    private static final ThreadLocal<String> TRACE_ID = new ThreadLocal<>();

    public record WorkRequested(String id) {}

    public static final class Probe {
        private final ConcurrentHashMap<String, String> seen =
                new ConcurrentHashMap<>();
        private final ConcurrentHashMap<String, Boolean> onEventThread =
                new ConcurrentHashMap<>();
        private final CountDownLatch done = new CountDownLatch(2);

        @EventListener
        public void on(WorkRequested event) {
            String id = TRACE_ID.get();
            seen.put(event.id(), id == null ? "missing" : id);
            onEventThread.put(
                    event.id(),
                    Thread.currentThread().getName().startsWith("event-"));
            done.countDown();
        }

        public void awaitEvents() throws InterruptedException {
            if (!done.await(10, TimeUnit.SECONDS)) {
                throw new IllegalStateException("event listener timed out");
            }
        }

        public String traceFor(String id) {
            return seen.get(id);
        }

        public boolean wasAsync(String id) {
            return Boolean.TRUE.equals(onEventThread.get(id));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        ThreadPoolTaskExecutor eventExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("event-");
            executor.setTaskDecorator(new ContextPropagatingTaskDecorator());
            executor.setWaitForTasksToCompleteOnShutdown(true);
            return executor;
        }

        @Bean(name = "applicationEventMulticaster")
        SimpleApplicationEventMulticaster eventMulticaster(
                ThreadPoolTaskExecutor eventExecutor) {
            SimpleApplicationEventMulticaster m =
                    new SimpleApplicationEventMulticaster();
            m.setTaskExecutor(eventExecutor);
            return m;
        }

        @Bean
        Probe probe() {
            return new Probe();
        }
    }

    private static String display(String value) {
        return value == null ? "missing" : value;
    }

    public static void main(String[] args) throws Exception {
        // Micrometer needs to know HOW to read/set/clear the custom ThreadLocal.
        ContextRegistry.getInstance().registerThreadLocalAccessor(
                "demo.trace-id", TRACE_ID);

        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            Probe probe = context.getBean(Probe.class);
            var plainExecutor = Executors.newSingleThreadExecutor();

            try {
                TRACE_ID.set("trace-42");

                // Without propagation: another thread does not see TRACE_ID.
                String raw = CompletableFuture.supplyAsync(
                        TRACE_ID::get, plainExecutor)
                        .get(5, TimeUnit.SECONDS);
                System.out.println("plain executor: " + display(raw));

                // The event multicaster's executor HAS TaskDecorator.
                context.publishEvent(new WorkRequested("A"));

                TRACE_ID.remove();
                context.publishEvent(new WorkRequested("B"));

                // Wait for both events so stdout is independent of scheduling order.
                probe.awaitEvents();

                System.out.println("listener A trace: "
                        + probe.traceFor("A"));
                System.out.println("listener A async: "
                        + probe.wasAsync("A"));
                System.out.println("listener B trace: "
                        + probe.traceFor("B"));
                System.out.println("publisher cleared: "
                        + display(TRACE_ID.get()));
            }
            finally {
                TRACE_ID.remove();
                plainExecutor.shutdownNow();
            }
        }
        finally {
            ContextRegistry.getInstance().removeThreadLocalAccessor(
                    "demo.trace-id");
        }
    }
}
~~~

Run command in the **async-event-trace-demo** directory:

~~~bash
gradle --console=plain -q run
~~~

**Stdout printed by the program itself** (ignoring extra Gradle or Spring logs if added by the environment):

~~~text
plain executor: missing
listener A trace: trace-42
listener A async: true
listener B trace: missing
publisher cleared: missing
~~~

### 6.3. Exact explanation

1. **ContextRegistry** registers a **ThreadLocalAccessor** for **TRACE_ID** under key **demo.trace-id** before creating the ApplicationContext.
2. **plainExecutor** has no context propagation. When the main thread sets **trace-42**, the plainExecutor thread still lacks that value, so the first line prints **missing**.
3. **eventExecutor** is a Spring-managed **ThreadPoolTaskExecutor** with **ContextPropagatingTaskDecorator**. At **context.publishEvent(WorkRequested("A"))**, it captures the publisher's current ThreadLocal.
4. **Probe.on(...)** runs on a thread starting with **event-**; the decorator restores **trace-42** within task A's scope so the recorder observes the string accurately.
5. The main thread clears **TRACE_ID** and publishes event B. Task B has no trace ID; the worker was restored to its previous state after task A, so **listener B trace: missing**. This demonstrates preventing ThreadLocal leaks across tasks.
6. **CountDownLatch** waits for the listener to handle both A and B before `main` prints results. Because the listeners do not print to stdout directly, the output line order is deterministic regardless of scheduler timing.
7. **ContextRegistry.removeThreadLocalAccessor(...)** is called after the context closes, cleaning up the demo registration. The Spring-managed executor is shut down by the container lifecycle.

**Checking demo expectations:** if you remove **executor.setTaskDecorator(new ContextPropagatingTaskDecorator())**, event A is no longer guaranteed to see **trace-42**. The demo intentionally omits a real tracer to show that propagation is not a built-in feature of Java `ThreadLocal`.

**An intentional limitation:** the demo does not send data over HTTP or a broker, and has no sampling/OTLP exporter. It only proves the mechanism needed for a **registered context value** to cross a thread boundary.

## 7. Applying to real traces/spans with Micrometer Tracing

When an application uses configured **Spring Boot Actuator + Micrometer Observation/Tracing**, the observability flow typically looks like:

~~~text
HTTP server request
  -> parent observation/span is created
  -> current Observation/Span in request thread
  -> publisher.publishEvent(OrderPlaced)
  -> executor with ContextPropagatingTaskDecorator
  -> event listener can receive current trace context
  -> can create a child Observation/span to measure event handling
  -> log MDC may contain traceId/spanId per tracer configuration
~~~

Prerequisites:

- An appropriate **tracing bridge/provider** (e.g., Micrometer Tracing bridge to OpenTelemetry or Brave), plus sampling and exporter to see traces in APM.
- Accessors for **current Observation/trace context** properly registered in **Micrometer ContextRegistry**.
- **The executor actually running the listener** has the task decorator; do not merely declare a decorator bean while using a different executor.
- The listener needs a **new Observation/span if it should represent a distinct operation**. Propagation only carries the **parent/current context** across the thread boundary; it does not auto-create an **event.consume** span.

**Snippet example in Spring Boot with ObservationRegistry**:

~~~java
@Component
public class TracedBusinessListener {
    private final ObservationRegistry observationRegistry;

    public TracedBusinessListener(ObservationRegistry observationRegistry) {
        this.observationRegistry = observationRegistry;
    }

    @Async("traceAwareExecutor")
    @EventListener
    public void on(OrderPlaced event) {
        Observation.createNotStarted(
                "business.order.placed.listener", observationRegistry)
                .observe(() -> process(event));
    }

    private void process(OrderPlaced event) {
        // Read the event and handle a small step without relying on the caller's transaction.
    }
}
~~~

The snippet above is **not a standalone file**; it requires imports for **io.micrometer.observation.Observation**, **ObservationRegistry**, Spring annotations, **OrderPlaced**, a propagating executor, **@EnableAsync**, and matching tracing/observability configuration. When tracing is wired to `ObservationRegistry`, the observation can create a dedicated span within the current trace. In a small demo without a tracer, merely using `Observation` does not guarantee APM receives spans.

When checking the trace ID from a real tracer:

~~~java
Span current = tracer.currentSpan();
String traceId = current == null
        ? "no-active-span"
        : current.context().traceId();
~~~

This is an **illustrative snippet** requiring **io.micrometer.tracing.Tracer** and **Span** from Micrometer Tracing, plus an application-configured tracer bean. It is the API for reading a **real trace ID**, unlike the demo's ThreadLocal String.

### 7.1. Need a seamless trace or a child span?

If the listener only needs logs in the same trace, **restoring the current context** already provides correlation. If you want to measure the handler step's duration/errors independently, create a **child span/Observation**. Then the trace ID stays the same, while the new operation's span ID **differs from the parent span ID**.

**Do not assert that span IDs must match between publisher and listener** across every architecture. The right target is usually **same trace ID and valid parent/child relationship** per the tracing backend. An event published after a request finishes may still need an async span/link model; semantics depend on instrumentation.

### 7.2. MDC is not the sole integration point

Loggers can pull **traceId/spanId** from MDC managed by the tracer. Do not merely call **MDC.put("traceId", ...)** and assume the tracer has the parent context. Also, do not register an **Slf4jThreadLocalAccessor** that copies all of MDC when the tracing stack already registers an Observation-aware MDC accessor; having **two accessors mutating MDC** can cause context conflicts/corruption. If you need another custom correlation ID, consider putting it in an event field or registering a scoped dedicated accessor.

## 8. Differences between a global async multicaster and `@Async` listeners

| Property | Multicaster with task executor | `@Async("traceAwareExecutor")` |
| --- | --- | --- |
| Scope | Listeners eligible for async across the entire context | Only annotated methods/classes called through a Spring proxy |
| Where decorator goes | Executor passed to **SimpleApplicationEventMulticaster.setTaskExecutor(...)** | Executor selected by **@Async** name/qualifier |
| Publisher thread | Usually does not wait for async listeners to finish | Usually does not wait for the async method to finish |
| ThreadLocal values preserved automatically? | No, unless the executor is equipped with propagation | No, unless the executor is equipped with propagation |
| Listeners not supporting async | May still run on the publisher thread | Annotation/proxy mechanism applies per listener and contract |
| Exception behavior | Listener exceptions on workers do not auto-propagate to publisher | Exceptions on void async methods do not auto-propagate to publisher |
| Completion order | Uncertain across multiple tasks/threads | Uncertain across multiple tasks/threads |
| Return value of `@EventListener` publishing next event | Relies on listener adapter and sync support; do not rely on returns for async chains | **Not supported** to publish via return value of an async listener |
| Transaction propagation | Does not transfer caller's transaction to worker | Does not transfer caller's transaction to worker |

**Note:** Some transaction-synchronized listeners intentionally must run on the event-publishing thread to register callbacks. That does not mean business code in post-commit phases may reuse the old transaction. Always distinguish **callback registration**, **handler execution thread**, and **actually available transaction**.

## 9. Do not propagate `TransactionContext` along with trace context

A dangerous misconception:

> "Because I used ContextPropagatingTaskDecorator, `@Transactional` on the publisher also propagates into the async listener."

**False.** Imperative transactions in Spring typically rely on **TransactionSynchronizationManager** and thread-bound resources. Trace propagation does not move database connections or rollback boundaries to worker threads.

~~~text
Publisher thread
  @Transactional
  save(order)
  publishEvent(OrderPlaced)
         |
         +--> Async listener on worker
                  -> can see trace/correlation context
                  -> NOT automatically inside the publisher's DB transaction
  commit / rollback per the original transaction
~~~

If the listener needs database operations, it must establish its own transaction via an appropriate service (e.g., a **@Transactional** service invoked through a Spring proxy). If the reaction must run only when the publisher transaction commits successfully, consider **@TransactionalEventListener(phase=AFTER_COMMIT)** or a **transactional outbox**.

**@TransactionalEventListener** registers a transaction callback when the event is published; it does not create a durable queue by default. When running in post-commit phases, be careful if writing new DB changes: a new transaction (**REQUIRES_NEW**) is typically needed to commit independently. For critical events that must survive crashes, an outbox remains better suited than in-memory-only callbacks.

If a message is processed on another thread while the publisher's transaction rolls back, trace context can still be propagated, leaving logs in the "same trace" even though the business transaction failed. **Trace correlation is not business consistency**.

## 10. In distributed systems: across message brokers, do not use ThreadLocal directly

**ContextPropagatingTaskDecorator** solves **in-JVM TaskExecutor** boundaries. When an event leaves the process via Kafka, RabbitMQ, JMS, HTTP, or gRPC, there is no shared ThreadLocal; **distributed context propagation** matching the transport protocol is required.

Typically:

1. The producer has a current trace/span context.
2. A propagator **injects** context into message headers/carriers (e.g., W3C **traceparent**, **tracestate**, and permitted baggage).
3. The broker transports the message; it does not convert Java ThreadLocals into headers automatically.
4. The consumer **extracts** context from headers.
5. The consumer opens an appropriate span/Observation and processes the message inside that scope.
6. Each hop preserves correlation/trace relationships while recording outcomes, errors, and retries with proper semantics.

~~~text
service A / publisher
   current trace/span
       |
       +-- inject headers { traceparent, tracestate, baggage? }
                       |
                       v
                   message broker
                       |
                       v
service B / consumer
       extract headers
       -> start consumer Observation/span
       -> process event
       -> close scope and finish span
~~~

**Do not serialize raw Span, Tracer, or SecurityContext objects** into messages. Pass only standard/controlled headers, limit sensitive data in baggage, apply trust policies to incoming external headers, and do not assume all downstream systems keep the same sampling decision.

In Spring Boot and the messaging ecosystem, automatic instrumentation for HTTP/messaging may be available depending on starters and configuration. If traces break across a broker, inspect **header inject/extract** and consumer instrumentation first, not just the event multicaster's TaskDecorator.

## 11. Propagating context does not guarantee execution

An async event listener with an accurate trace can still:

- Be rejected by the executor because the pool/queue is full.
- Not have run yet when the application shuts down.
- Throw an exception that the publisher never receives.
- Be killed mid-flight by a process crash.
- Receive duplicate events after retries if sent through a broker.
- Produce side effects before the publisher's DB transaction commits.

Therefore, separate three questions:

| Question | Typical mechanism |
| --- | --- |
| **Do listener logs and spans share the trace/correlation?** | Context propagation, Observation/Tracing, MDC integration |
| **Will the task run and handle errors?** | Executor policy, exception handler, monitoring, retries |
| **Must the task survive crashes and process consistently?** | Persistent queue/outbox, idempotency, transaction boundaries |

If the application must guarantee event publication after commit, consider a **transactional outbox** or a durable mechanism. **@Async** and **ContextPropagatingTaskDecorator** do not replace this.

## 12. Timing, lifecycle, and performance risks

### 12.1. Snapshots are captured at schedule time

With TaskDecorator, context is captured at **the moment the task is handed to the executor**. If the publisher modifies ThreadLocal immediately after **publishEvent(...)**, the decorated task still uses the snapshot captured when scheduled. This is why event A in the demo sees **trace-42** even though `main` cleared ThreadLocal before the worker could run.

**Do not pass large mutable objects via a custom ThreadLocalAccessor** expecting the snapshot to be an immutable deep copy. If a context value is mutable, the snapshot may only hold a reference. Choose small/immutable values or copy safely.

### 12.2. Restoring scopes and preventing leaks

A proper propagation implementation must **restore/clear context** after the task finishes, even if the listener throws an exception. Micrometer `ContextSnapshot` provides scope restoration; avoid calling **MDC.setContextMap(...)** manually without saving and restoring the prior state.

If writing a custom TaskDecorator for custom data:

~~~java
TaskDecorator decorator = runnable -> {
    String captured = MY_CONTEXT.get();
    return () -> {
        String previous = MY_CONTEXT.get();
        try {
            if (captured == null) {
                MY_CONTEXT.remove();
            } else {
                MY_CONTEXT.set(captured);
            }
            runnable.run();
        } finally {
            if (previous == null) {
                MY_CONTEXT.remove();
            } else {
                MY_CONTEXT.set(previous);
            }
        }
    };
};
~~~

This is an **illustrative snippet** requiring the **MY_CONTEXT** variable and imports; suitable only for a controlled ThreadLocal. For real tracing (Observation, Span, baggage, MDC), prefer **ContextPropagatingTaskDecorator** and built-in accessors rather than re-implementing trace propagation yourself.

### 12.3. Context propagation has overhead

Snapshotting/capturing/restoring introduces overhead. Per Spring Javadoc, the decorator is particularly useful when executing on another thread, but should not be enabled blindly for millions of tiny tasks without measurement. Measure latency, queue wait, CPU/allocations, sampling, and the number of propagated fields.

A **trace ID** helps trace requests; it does not fix executor bottlenecks. Monitor active threads, queue depth, rejection counts, handler durations, error counts, and shutdown times.

## 13. Testing trace propagation properly

### 13.1. Testing both boundaries

An integration test should verify:

1. When the listener is **synchronous**, current trace context remains available from the publisher thread if instrumentation is active.
2. When dispatched to a **bare executor**, ThreadLocal context exists on the publisher and is typically missing on the worker.
3. When the executor has **ContextPropagatingTaskDecorator** and matching accessors, the correlation ID/trace ID is accurate on the worker.
4. After task A, task B does not inherit A's context if the publisher has no trace.
5. When a listener throws an exception, context is still restored without polluting the next task.
6. With **@Async("traceAwareExecutor")**, verify Spring actually picks the intended executor and the listener runs on the worker.
7. With real Micrometer Tracing, verify matching **trace ID** and proper span relationships, without enforcing identical span IDs.
8. With a message broker, test **traceparent injection/extraction**; an in-process TaskDecorator is insufficient.
9. Test errors/retries/shutdown beyond propagation: rejected tasks, failing listeners, non-waiting callers, duplicates.
10. Test privacy: baggage/headers contain no passwords, tokens, or non-allowlisted user data.

### 13.2. Use CountDownLatch or conditional waiting tools

Async listeners may run before or after **publishEvent(...)** returns; never write tests using `Thread.sleep(100)` and conclude trace propagation works. The section 6 example uses **CountDownLatch** and **ConcurrentHashMap** to assert outcomes after the listener finishes, eliminating scheduling races.

When testing real traces, use a tracing test handler/exporter or an in-memory span collector to verify **span relationships**. Tests should not match log strings alone if tracing backends have different sampling/filtering rules.

### 13.3. What to check in dashboards/APM

For an example trace like **checkout-submit**, verify:

- The publisher/request span has a valid trace ID.
- The async listener operation carries the trace ID linked to the publisher per configuration.
- The listener span (if created) has a clear name, duration, status/error, and sensible parent/link.
- Listener logs have proper correlation; no leftover `traceId` from a previous request due to thread reuse.
- With sampling, do not treat a missing exported span as proof the code didn't run; cross-check metrics/logs.
- Retries and redeliveries may create distinct **attempt spans**, while remaining linked to the workflow/business ID.

## 14. Common mistakes and fixes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking **@Async auto-copies MDC/traces** | Listener runs yet logs lack traces | Use a propagating executor with configured tracer/accessors |
| Putting the decorator on an unused executor | Nothing changes | Verify the exact executor of the multicaster or **@Async** qualifier |
| Using **InheritableThreadLocal** with thread pools | Wrong/stale data or cross-request leaks | Capture at the scheduling boundary and restore per scope |
| Copying a **traceId** string and assuming distributed tracing exists | Logs match yet there is no span hierarchy | Use a tracer/Observation, propagators, and instrumentation |
| Registering an MDC accessor that conflicts with tracing integration | Causes MDC/context corruption | Check existing accessors; add only what is needed |
| Assuming the decorator also propagates **@Transactional** | Listener mistakenly thinks it is in the old transaction | Use separate transactions and `AFTER_COMMIT`/outbox when needed |
| Combining `@TransactionalEventListener` + `@Async` without understanding timing | Confuses callback registration with handler execution | Separate transaction phase, async executor, and commit result |
| Propagating all baggage and user secrets | Privacy/security risk, oversized headers | Allowlist fields, redact, and enforce size limits |
| Forgetting scope cleanup in a custom decorator | Worker thread retains the previous request's context | Use `try/finally` to restore before/after tasks |
| Not waiting for the listener in tests | Flaky tests or false conclusions | Use `CountDownLatch`/Awaitility and in-memory trace exporters |
| Assuming an accurate trace means events cannot be lost | Async tasks can still be killed/dropped | Use queues/outboxes, retries, and idempotency |
| Forgetting broker header propagation | Traces break across microservices | Inject/extract W3C headers at producer/consumer |
| Using one shared span for everything without child spans | Cannot see handler execution time | Create an Observation/span for steps needing measurement |
| Adding too many context fields and decorators to every microtask | Latency/allocation overhead | Benchmark, trim fields, choose key boundaries |
| Reading MDC only while no tracer is installed | "Fake" `traceId` strings appear with no traces on dashboards | Verify Micrometer Tracing bridge and exporter |

## 15. Production deployment checklist

Before deploying an async event listener, answer:

1. **Is the event handled synchronously or asynchronously?** Multicaster executor or **@Async**?
2. **Does the actual executor have ContextPropagatingTaskDecorator?** Are the exact bean name and qualifier used?
3. **Are trace/Observation/ThreadLocal accessors registered?** Do not assume every MDC key is captured automatically.
4. **Is the trace a real tracer context or just a String correlation ID?** They are two different things.
5. **Do you create a separate Observation/span for the handler when latency visibility is needed?**
6. **When the thread pool reuses threads, is previous context restored/cleared in `finally`?**
7. **Does it depend on the publisher's transaction?** If so, redesign the transaction boundary.
8. **Does it cross a broker/HTTP boundary?** If so, inject/extract trace headers; TaskDecorator is not enough.
9. **Are sensitive baggage/metadata protected?** Allowlists, size limits, no full-payload logging.
10. **If the executor rejects, the listener fails, or the process dies, can business state recover?** Use appropriate monitoring/outbox/queues.
11. **Has async behavior been tested deterministically?** With latches, trace exporter tests, and trace relationship checks?
12. **Have overhead and queue behavior been measured?** Avoid adding decorators/tracing to every tiny task without purpose.

**Conclusion:** When Spring event listeners run on another thread, **ThreadLocal/MDC/current spans do not follow automatically**. In Spring Framework, attach **ContextPropagatingTaskDecorator** to the **TaskExecutor that actually executes the listener** and provide matching **Micrometer Context Propagation accessors**; for real tracing, also configure **Micrometer Tracing/instrumentation** and optionally create a dedicated span for the listener. **Context propagation only preserves observability linkage**; it does not transfer transactions or guarantee durable task execution.

### Official documentation

- Spring Framework 6.2 — *Observability Support, Application Events and @EventListener*: https://docs.spring.io/spring-framework/reference/6.2/integration/observability.html
- Spring Framework 6.2.9 Javadoc — *ContextPropagatingTaskDecorator*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html
- Spring Framework 6.2.9 Javadoc — *SimpleApplicationEventMulticaster*: https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html
- Spring Framework 6.2 — *Asynchronous Event Listeners*: https://docs.spring.io/spring-framework/reference/6.2/core/beans/context-introduction.html
- Micrometer Context Propagation — *Purpose*: https://docs.micrometer.io/context-propagation/reference/purpose.html
- Micrometer Context Propagation — *Usage*: https://docs.micrometer.io/context-propagation/reference/usage.html
- Spring Framework 6.2 — *Transaction-bound Events*: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html
