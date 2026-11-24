# Preserving Traces Across Thread Switches and Reactive Processing Chains

## 1. Traces Belong to Executions, Not Thread Names

An order placement request may start on an HTTP thread, hand work off to an executor, and then continue inside a Reactor pipeline. Looking only at thread names can easily trick you into thinking those three parts belong to three different executions.

What needs to be preserved is the **trace context**:

- **Trace ID** identifies the distributed execution.
- **Span ID** identifies a single operation within that execution.
- **Parent span ID** represents the parent operation when creating a child span.
- **Scope** is the interval during which an observation or span is considered current.

Design example:

```text
HTTP receives order: trace T, span A
    --> stock check task: trace T, span B, parent A
    --> payment call: trace T, span C, parent A
```

Switching threads does not have to change the Trace ID. Creating a child span can keep the same Trace ID yet must get its own Span ID. Conversely, merely propagating context to a task does not automatically create a new span to measure that task.

In Spring Boot, **Micrometer Observation** manages the lifecycle of an observed operation; tracing handlers turn observations into spans. When an observation's scope is opened, the corresponding span becomes the current span. [Micrometer Tracing 1.3: configuring with Observation](https://docs.micrometer.io/tracing/reference/1.3/configuring.html)

This lesson focuses on boundaries within the same process. When calling another service, protocol instrumentation is also required to inject/extract context on the wire.

## 2. Why Does an Active Trace Get Lost on Thread Switches?

### 2.1. ThreadLocal Is Not Request-Wide Context

In sequential processing models, libraries typically use `ThreadLocal` to look up the current context. Each thread has its own value copy; setting a value on thread A does not automatically set it on thread B. [Java 17: ThreadLocal](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ThreadLocal.html)

Consider an executor with reused threads:

```text
HTTP thread:
open request R1 scope
    --> enqueue Runnable

pool thread:
take Runnable to execute
    --> without restoring context, unaware of R1's scope
```

There are two distinct failure modes:

1. **Context loss:** the task has no current span or accidentally starts a new root trace.
2. **Context leak:** a subsequent task sees leftover data from an earlier request.

Therefore, a proper solution must both **restore before running** and **return the previous state after running**, even when exceptions occur.

Do not use a `static Span current` variable to fix this: concurrent requests will overwrite one another. Also do not merely copy a Trace ID string into MDC; that can make logs look right without establishing context for the tracer to link spans.

`InheritableThreadLocal` does not replace per-task context propagation: pools typically create threads before requests arrive and keep reusing them. Virtual threads also do not make an arbitrary executor understand a tracing library's context contract.

### 2.2. Three Moments to Distinguish

| Moment | What Happens | Risk When Capturing Context at the Wrong Time |
| --- | --- | --- |
| Creating task object or assembling Reactor chain | Describes future work | Current context may not belong to the later run |
| Submitting task or subscribing (`subscribe`) | An execution instance is established | This is the boundary where the right context must be selected |
| Executing callback/operator | Work runs on an actual thread | Context must be opened in proper scope right here |

A snapshot taken at application startup cannot represent every later request. Likewise, building a `Mono` while a scope is active and subscribing elsewhere does not mean the scope was carried along.

## 3. Choosing the Propagation Mechanism by Execution Boundary

| Boundary | Suitable Mechanism | What Still Needs Verification |
| --- | --- | --- |
| Self-managed `ExecutorService` | `ContextSnapshot` wrapping tasks or context-aware executor | Capture while context is still right; close scope after run |
| Spring executor/`@Async` | `ContextPropagatingTaskDecorator` | Right executor is used and right accessors are registered |
| `Mono`/`Flux` chain | Reactor Context plus ThreadLocal restoration mechanism | Right subscription, right keys, and right `contextWrite` placement |
| HTTP call to another service | Client wired with observation and protocol propagation | Right context at exact request-send time |
| Callback from external library | Context wrapper right at callback boundary | Do not assume Reactor hooks cover arbitrary callbacks |

One task can cross multiple boundaries. Configuring an executor properly does not solve a callback in another library; enabling Reactor auto-mode does not turn `new Thread(...)` into a context-propagated task.

## 4. Executor: Capture, Restore, Run, Return

Micrometer Context Propagation uses **ThreadLocalAccessor** to read/write a context type, **ContextRegistry** to manage accessors, and **ContextSnapshot** to take a snapshot of registered values. A snapshot can reopen those values in a scope and restore the previous state when the scope closes. [Micrometer Context Propagation 1.1: usage](https://docs.micrometer.io/context-propagation/reference/1.1/usage.html)

Operational flow to maintain:

```text
submitter: capture currently active context
    --> submit wrapped task
runner: restore context
    --> run logic
    --> close scope and restore previous context
```

The snippet below illustrates an executor boundary. It assumes `factory` is a `ContextSnapshotFactory` configured with appropriate accessors and `executor` is an `ExecutorService`; this is not a standalone program:

```java
ContextSnapshot snapshot = factory.captureAll();

Future<Boolean> result = executor.submit(snapshot.wrap(() -> {
    Span current = tracer.currentSpan();
    return current != null;
}));
```

Requires imports `io.micrometer.context.ContextSnapshot`, `io.micrometer.tracing.Span`, and `java.util.concurrent.Future`; `tracer` is a provided Micrometer `Tracer`. The full program in section 8 checks more strictly than merely non-`null`.

Capture the snapshot **before leaving the submitter's context**. Capturing inside a worker that has already lost context only records the worker's empty state.

### 4.1. Continuing Context vs Creating a Child Span Are Two Operations

After restoring the parent observation:

- If you only need correlation for that execution block, you can run inside that context.
- If you need to measure a distinct unit of work, create a child observation inside the task.
- Whoever creates an observation/span is responsible for ending it.
- The task must not end an HTTP observation owned by the framework.

A task can continue after the HTTP request finishes. Preserving trace correlation does not mean keeping the HTTP request, transaction, or HTTP resources alive. For background tasks with independent lifecycles, define an appropriate observation relationship rather than artificially stretching the request scope.

### 4.2. CompletableFuture Does Not Solve This Automatically

Async methods without an executor argument typically use `ForkJoinPool.commonPool()`; callbacks without the `Async` suffix may run on the thread that completes the future. Do not wire a future chain assuming "every step uses the same thread." [Java 17: CompletableFuture](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)

When you have an executor equipped with context propagation, use it intentionally. For a callback registered under context A yet only submitted to an executor when a future completes under context B, explicitly decide which context must be captured. A task-submission decorator cannot restore A if A was already lost beforehand.

## 5. Spring Boot 3.3: Configuring an Executor for @Async

The classes below are **code integrated into an existing Boot 3.3 application**, not a standalone runnable project. The application needs Actuator, Micrometer Tracing with a matching bridge, and `io.micrometer:context-propagation`. When span export is needed, also configure the corresponding exporter and receiver; merely adding context propagation does not create a trace storage system.

`ContextPropagatingTaskDecorator` has been available since Spring Framework 6.1, supporting context restoration when tasks run on different threads with per-task overhead. [Spring Framework 6.1: ContextPropagatingTaskDecorator](https://docs.spring.io/spring-framework/docs/6.1.16/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html)

### 5.1. Executor with Explicitly Declared Observation Accessor

Save as `TraceAsyncConfiguration.java`:

```java
package example.tracing;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class TraceAsyncConfiguration {
    @Bean("traceExecutor")
    public ThreadPoolTaskExecutor traceExecutor(ObservationRegistry registry) {
        ContextRegistry contexts = new ContextRegistry();
        contexts.registerThreadLocalAccessor(
                new ObservationThreadLocalAccessor(registry));

        ContextSnapshotFactory snapshots = ContextSnapshotFactory.builder()
                .contextRegistry(contexts)
                .clearMissing(true)
                .build();

        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("trace-worker-");
        executor.setTaskDecorator(
                new ContextPropagatingTaskDecorator(snapshots));
        return executor;
    }
}
```

Spring manages initializing and shutting down this executor bean. You do not need to call `initialize()` manually inside the bean method.

The example uses a local registry to make clear: it propagates **Observation** bound to the injected `ObservationRegistry`. `clearMissing(true)` instructs clearing accessor values missing from the snapshot during restoration; it is not a command to wipe all `ThreadLocal` values in the application.

If you create spans directly with `Tracer` outside an Observation lifecycle, or create baggage directly, configure the corresponding accessors. Micrometer Tracing provides `ObservationAwareSpanThreadLocalAccessor` and `ObservationAwareBaggageThreadLocalAccessor` for those cases. Do not register duplicates or mutate global configuration per request. [Micrometer Tracing 1.3: Context Propagation](https://docs.micrometer.io/tracing/reference/1.3/configuring.html#_context_propagation_with_micrometer_tracing)

### 5.2. Asynchronous Method Running on the Right Executor

Save as `AsyncStockWorker.java` in the same package:

```java
package example.tracing;

import java.util.concurrent.CompletableFuture;

import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class AsyncStockWorker {
    private final ObservationRegistry registry;
    private final Tracer tracer;

    public AsyncStockWorker(ObservationRegistry registry, Tracer tracer) {
        this.registry = registry;
        this.tracer = tracer;
    }

    @Async("traceExecutor")
    public CompletableFuture<String> inspectStock() {
        String traceId = Observation.createNotStarted("stock.inspect", registry)
                .observe(() -> {
                    Span current = tracer.currentSpan();
                    return current == null
                            ? "missing"
                            : current.context().traceId();
                });
        return CompletableFuture.completedFuture(traceId);
    }
}
```

Another bean calls `inspectStock()` while a parent observation is active. The decorator carries the parent observation to the worker; `observe(...)` creates, opens scope for, and stops the stock-inspection observation.

Integration notes:

- `@Async("traceExecutor")` must match the bean name.
- With normal proxy mechanics, calling `this.inspectStock()` within the same object bypasses the async proxy.
- Do not call `CompletableFuture.supplyAsync(...)` without an executor inside this method, as that introduces another boundary.
- If the caller lacks a parent observation, the child observation can start a new trace; do not treat a non-empty Trace ID as proof the original trace was preserved.

Framework 6.1 supports context propagation for async execution yet does not automatically create observations around every `@Async` method. [Spring Framework 6.1 Release Notes](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-6.1-Release-Notes)

## 6. Reactive: Context Belongs to the Subscription

### 6.1. Reactor Context Differs from ThreadLocal

A Reactor chain can switch threads multiple times. **Reactor Context** carries key-value pairs per subscriber context; it does not need to stay pinned to one thread. `Context` is immutable: `put` returns a new `Context`. [Reactor 3.6: Context API](https://projectreactor.io/docs/core/3.6.6/api/reactor/util/context/Context.html)

Standalone example of data in Context, assuming `reactor.core.publisher.Mono` is imported:

```java
Mono<String> label = Mono.deferContextual(context ->
        Mono.just(context.<String>get("request.label")))
        .contextWrite(context -> context.put("request.label", "checkout"));
```

This is a declarative snippet that can sit inside a method; without a terminal subscription, it does not print or return a result to a caller yet. The `request.label` string is only illustrative data, not a key activating the tracer.

`contextWrite` enriches Context for operators **upstream** of that position; `deferContextual` reads context at subscription time. Do not think Context flows in the same direction as data signals. [Reactor 3.6: Mono API](https://projectreactor.io/docs/core/3.6.6/api/reactor/core/publisher/Mono.html)

Putting an arbitrary key named `traceId` into Context does not automatically set the current span. To integrate with Micrometer, use the accessor and context key that mechanism understands, such as `ObservationThreadLocalAccessor.KEY` for Observation.

### 6.2. Enabling ThreadLocal Restoration in Boot 3.3

```yaml
spring:
  reactor:
    context-propagation: auto
```

Boot 3.3 provides this property to enable automatic restoration of relevant `ThreadLocal` values in reactive chains. By default, not every operator has those values restored automatically. [Spring Boot 3.3: Observability](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html)

Boot's Reactor auto-configuration calls `Hooks.enableAutomaticContextPropagation()` when the mode is `AUTO`. [Boot 3.3.13 ReactorAutoConfiguration source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.13/spring-boot-project/spring-boot-autoconfigure/src/main/java/org/springframework/boot/autoconfigure/reactor/ReactorAutoConfiguration.java)

Distinguish clearly:

- Context carries data for an execution.
- Accessors connect that data to the thread-bound context libraries read.
- Automatic mode restores data across the right operator scopes.

Merely enabling the property does not create nonexistent observations, turn arbitrary keys into tracing context, or fix arbitrary callbacks outside Reactor.

In Boot applications, prefer startup configuration. Do not toggle the global hook per request. The CLI program in section 8 manages the hook itself because it runs in its own JVM.

### 6.3. contextCapture Does Not Mean Capturing at Assembly Time

`contextCapture()` grabs `ThreadLocal` values backed by accessors at **subscription time** and places them into Context. Automatic mode applies to new subscriptions; it should be enabled from startup. In default limited mode, restoration support focuses on operators such as `handle` and `tap`; do not assume an arbitrary `map` will have `ThreadLocal` context. [Reactor 3.6: Context-Propagation Support](https://projectreactor.io/docs/core/3.6.12/reference/index.html#context.propagation)

Example of wrong timing:

```text
open scope A
    --> build Mono with contextCapture
close scope A
    --> pass Mono elsewhere to subscribe
```

When subscription actually occurs, A may no longer be the current context. Having `contextCapture` in the chain cannot fix a source context that was already lost.

If you already have the right `Observation` object for an execution, you can put it into Context using the standard key as shown in section 8's complete example. For a publisher reused multiple times, never grab the first request's observation and hardcode it for all subscriptions.

`publishOn` and `subscribeOn` change where part of the work is scheduled; they are not commands to create or select a trace. Inspect context inside the operator that actually executes after the thread-switch boundary.

## 7. Span Lifecycle in Reactive Chains

Do not wrap an operation that merely **returns** a `Mono` in a synchronous scope and assume that scope lasts until the chain finishes. The scope closes when the method returns, whereas the work may not even have started yet.

For a reactive operation needing its own observation, you can use `reactor-core-micrometer` integration instead of manually holding scopes across threads. The snippet below illustrates integration: `stockLookup` is a provided `Mono<String>`, and `registry` is the application's `ObservationRegistry`.

```java
import reactor.core.observability.micrometer.Micrometer;

Mono<String> observedLookup = stockLookup
        .name("stock.lookup")
        .tap(Micrometer.observation(registry));
```

Place the import at the top of the file and the declaration inside a method. A Boot project needs `io.projectreactor:reactor-core-micrometer` under its version management. The observation here can become a span when the registry has a tracing handler. [Reactor: Observation via Micrometer](https://docs.spring.io/projectreactor/reactor-core/docs/current/reference/html/#_observation)

When choosing manual lifecycle management instead of library integration, clearly determine:

- Does each subscription get its own observation or use a framework-owned one?
- On completion, error, or cancellation, who stops the observation?
- When retries resubscribe, do you need one observation for the whole chain or one per attempt?
- Which subscription does data inside a `flatMap` branch belong to?
- Is Context accidentally stored in a shared variable, cache, or multi-request publisher?

Never stop the framework's HTTP observation from `doFinally` of an inner chain. If you created an observation yourself, stop that observation. Cancellation is also a termination path that must be tested, not only the success path.

## 8. Standalone Java 17 Program: Testing Real Traces

The program below uses Micrometer Tracing with Brave, without Spring Boot and without network export. It directly checks the current tracer, parent-child span relationships, and context cleanup.

Pinned versions for the experiment match Boot 3.3's generation; in a real Boot project, use the project BOM instead of manually copying all these versions.

### 8.1. Structure and build.gradle

Create an isolated test directory:

```text
trace-context-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/TraceContextDemo.java
```

Contents of `settings.gradle`:

```groovy
rootProject.name = 'trace-context-demo'
```

Contents of `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'io.micrometer:context-propagation:1.1.1'
    implementation 'io.micrometer:micrometer-observation:1.13.0'
    implementation 'io.micrometer:micrometer-tracing:1.3.0'
    implementation 'io.micrometer:micrometer-tracing-bridge-brave:1.3.0'
    implementation 'io.zipkin.brave:brave:6.0.3'
    implementation 'io.projectreactor:reactor-core:3.6.6'
}

application {
    mainClass = 'TraceContextDemo'
}
```

You need a Gradle installation compatible with your active JVM, JDK 17 for the toolchain selection, and network access for initial dependency downloads. The Java filename must match the public class name.

### 8.2. Complete TraceContextDemo.java

```java
import java.time.Duration;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

import brave.Tracing;
import brave.handler.MutableSpan;
import brave.handler.SpanHandler;
import brave.propagation.ThreadLocalCurrentTraceContext;
import brave.propagation.TraceContext;
import brave.sampler.Sampler;
import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshot;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import io.micrometer.tracing.Span;
import io.micrometer.tracing.Tracer;
import io.micrometer.tracing.brave.bridge.BraveBaggageManager;
import io.micrometer.tracing.brave.bridge.BraveCurrentTraceContext;
import io.micrometer.tracing.brave.bridge.BraveTracer;
import io.micrometer.tracing.handler.DefaultTracingObservationHandler;
import reactor.core.publisher.Hooks;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class TraceContextDemo {
    private static String traceId(Tracer tracer) {
        Span current = tracer.currentSpan();
        return current == null ? null : current.context().traceId();
    }

    public static void main(String[] args) throws Exception {
        ObservationRegistry registry = ObservationRegistry.create();
        ContextRegistry contexts = ContextRegistry.getInstance();
        contexts.registerThreadLocalAccessor(
                new ObservationThreadLocalAccessor(registry));
        Hooks.enableAutomaticContextPropagation();

        ExecutorService executor = Executors.newSingleThreadExecutor();
        Scheduler scheduler = Schedulers.newSingle("reactive-demo");

        try (Tracing brave = Tracing.newBuilder()
                .currentTraceContext(
                        ThreadLocalCurrentTraceContext.newBuilder().build())
                .sampler(Sampler.ALWAYS_SAMPLE)
                .addSpanHandler(new SpanHandler() {
                    @Override
                    public boolean end(TraceContext context, MutableSpan span,
                            Cause cause) {
                        return true;
                    }
                })
                .build()) {
            Tracer tracer = new BraveTracer(
                    brave.tracer(),
                    new BraveCurrentTraceContext(brave.currentTraceContext()),
                    new BraveBaggageManager());
            registry.observationConfig().observationHandler(
                    new DefaultTracingObservationHandler(tracer));

            Observation parent = Observation.start("checkout", registry);
            try (Observation.Scope scope = parent.openScope()) {
                String expectedTrace = traceId(tracer);
                String expectedParent = tracer.currentSpan().context().spanId();

                boolean rawMissing = executor.submit(
                        () -> tracer.currentSpan() == null).get();

                ContextSnapshot snapshot = ContextSnapshotFactory.builder()
                        .clearMissing(true)
                        .build()
                        .captureAll();

                boolean executorTrace = executor.submit(snapshot.wrap(
                        () -> expectedTrace.equals(traceId(tracer)))).get();

                boolean childLinked = executor.submit(snapshot.wrap(
                        () -> Observation.createNotStarted("worker.step", registry)
                                .observe(() -> {
                                    Span child = tracer.currentSpan();
                                    return child != null
                                            && expectedTrace.equals(
                                                    child.context().traceId())
                                            && expectedParent.equals(
                                                    child.context().parentId())
                                            && !expectedParent.equals(
                                                    child.context().spanId());
                                }))).get();

                boolean reactorTrace = Boolean.TRUE.equals(
                        Mono.delay(Duration.ofMillis(5), scheduler)
                                .map(value -> expectedTrace.equals(traceId(tracer)))
                                .contextWrite(context -> context.put(
                                        ObservationThreadLocalAccessor.KEY,
                                        parent))
                                .block());

                System.out.println("rawMissing=" + rawMissing);
                System.out.println("executorTrace=" + executorTrace);
                System.out.println("childLinked=" + childLinked);
                System.out.println("reactorTrace=" + reactorTrace);
                System.out.println("callerRestored=" + expectedParent.equals(
                        tracer.currentSpan().context().spanId()));
            } finally {
                parent.stop();
            }

            System.out.println("workerClean=" + executor.submit(
                    () -> tracer.currentSpan() == null).get());
            System.out.println("reactorClean=" + Mono.delay(
                    Duration.ofMillis(5), scheduler)
                    .map(value -> tracer.currentSpan() == null)
                    .block());
            System.out.println("callerClean=" + (tracer.currentSpan() == null));
        } finally {
            executor.shutdownNow();
            scheduler.dispose();
            Hooks.disableAutomaticContextPropagation();
            contexts.removeThreadLocalAccessor(ObservationThreadLocalAccessor.KEY);
        }
    }
}
```

`SpanHandler` in the example only receives completion events without sending to storage. Therefore the program does not require Zipkin or a Collector.

### 8.3. Running and Reading Results

In the test directory:

```shell
gradle -q run
```

Program stdout:

```text
rawMissing=true
executorTrace=true
childLinked=true
reactorTrace=true
callerRestored=true
workerClean=true
reactorClean=true
callerClean=true
```

Each line has a distinct meaning:

| Result | What Was Verified |
| --- | --- |
| `rawMissing=true` | An executor with an unwrapped task does not automatically see the submitter's span |
| `executorTrace=true` | The snapshot restored the right Trace ID on the worker |
| `childLinked=true` | The child span shares the Trace ID, has a distinct Span ID, and has the right parent span ID |
| `reactorTrace=true` | An operator running on another scheduler still sees the right trace |
| `callerRestored=true` | After the task and inner chain, the caller remains on the parent span |
| `workerClean=true` | The same worker pool has no leftover span after the wrapped task |
| `reactorClean=true` | A fresh subscription on the same scheduler carries no old span |
| `callerClean=true` | The calling thread has no leftover span after the parent scope closes |

The program does not print concrete Trace IDs because they change per run. Comparing relationships between IDs yields stable results and is more meaningful than expecting a fixed ID string.

`block()` only lets the CLI program wait for results and exit cleanly. Do not put blocking waits onto a WebFlux event loop to fix missing traces. In a reactive endpoint, return the publisher for the framework to manage.

The program registers the accessor and hook once and cleans them up when the test JVM exits. Do not copy removing accessors or disabling hooks into per-request handling in a shared application.

## 9. Verifying in a Real Application

The CLI example tests in-JVM boundaries; it does not yet prove HTTP paths, MDC, cancellation handling, or every application integration pattern. Add test cases covering real scenarios:

| Scenario | What to Observe |
| --- | --- |
| HTTP → `@Async` | Worker shares Trace ID with request; child span has right parent |
| Reactor switches scheduler | Trace ID inside operator after thread switch remains right |
| Two interleaved requests | Trace A does not appear in B's callbacks |
| Task throws exception | Task-owned observation stops; worker retains no context |
| Cancelled subscription | Subscription's observation resources end properly |
| Retry sequence | Observation count and parent-child relationships match design, not closed early |
| Task with no incoming trace | Does not inherit leftover data from an earlier request |
| Outbound HTTP call | Client uses active context at send time to propagate to receiving service |
| Context has data yet logs lack IDs | Check accessors, scope, and logging config, not only Context |
| Spans missing in storage | Check sampling/exporter separately from in-JVM context checks |

For HTTP, use Boot-provided client builders to keep automatic trace propagation. Manually creating clients outside observation configuration can break the link even when preceding code has an active span. [Spring Boot 3.3: Propagating Traces](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html#actuator.micrometer-tracing.propagating-traces)

MDC is supporting evidence for logs. Also check `tracer.currentSpan()`, Trace ID, parent span ID, and finished spans. Seeing the same string in logs alone does not prove the tracing system has the right relationships.

## 10. Common Errors and How to Isolate Them

| Symptom | Cause to Check | Adjustment |
| --- | --- | --- |
| `@Async` does not switch threads | Self-invocation on same bean or bypassed proxy | Call through Spring-managed bean; check executor |
| Has Trace ID yet it is a new trace | Created observation after parent context was already lost | Fix propagation boundary before creating child observation |
| Snapshot is still empty | Captured in worker after context loss, or missing accessor | Capture on submitter side; check registered context types |
| Reactor Context has observation yet current span is intermittent | ThreadLocal restoration not applied to the right scope | Check auto mode, subscription, and accessor configuration |
| Trace lost in a `map` after thread switch | Running in limited mode or data never entered Context | Check restoration mechanism and `contextWrite` placement |
| Logs look right yet spans do not link | Copied only MDC/Trace ID strings | Propagate real tracer/Observation context |
| Next request carries previous trace | Scope never closed or shared state | Restore per scope; retest on the same worker |
| Span already finished upon returning `Mono` | Used synchronous lifecycle for deferred work | Use reactive integration or manage per subscription |
| Context lost in external callback | Callback does not pass through instrumented boundary | Wrap the callback or the executor used by the library |

When investigating, pick one small boundary: record context right before dispatch and right inside the first receiving callback. Once that boundary is right, inspect the next boundary. This separates context-source loss from restoration or span-export failures.

## 11. Practice

1. Remove `snapshot.wrap(...)` from one task in the CLI and observe the trace comparison fail; keep the other tasks intact for contrast.
2. Disable automatic mode before a test subscription and inspect the `map` operator on the scheduler. Do not extrapolate the test program's behavior to an application with different integration without testing.
3. Submit two independent requests to a small worker pool; verify each request's distinct Trace ID and a subsequent task with no incoming context.
4. Create one error case and one cancelled-subscription case; check both finished spans and post-execution context.
5. Append an HTTP call at the end of a task and inspect the receiving service. Distinguish preserving context inside the JVM from propagating over the protocol.

After this lesson, you should be able to answer three questions clearly: where context is captured from, at which boundary it is restored, and who is responsible for closing the observation scope. Those three questions must have concrete answers for each execution path.
