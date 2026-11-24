# Number of Listeners and Listener Selection Cost in Spring Framework Application Events

## 1. Objective: do many listeners make publishEvent slow?

In the **Performance** section of **Spring Framework Application Events**, the question is not just “how many listeners are registered?”, but **when an event is published, which listeners does Spring need to select, how long does selection take, and how much time does executing them take afterward?**

Suppose an application has 250 listeners:
- 180 listeners handle payment-related events;
- 50 listeners handle inventory events;
- 17 listeners handle account events;
- 3 listeners handle `OrderPlaced`.

When publishing an `OrderPlaced`, you do not want all 250 callbacks invoked only for them to check `if (event instanceof OrderPlaced)`. Spring has a mechanism for **filtering listeners by event type** and **caching selection results** for eligible event/source type combinations. If only 3 listeners actually match, the handler execution cost generally corresponds to those **3 listeners**, not all 250.

However, do not conclude “many listeners always have zero cost”:
- Encountering a **new event type** for the first time may require inspecting many listeners to build the matching set.
- Overly broad listener types, such as accepting `ApplicationEvent` or `Object`, can be selected for many unnecessary events.
- Every matched listener still incurs an invocation, argument/condition resolution, logging/tracing, and side effects.
- If using an async multicaster, one event can spawn multiple executor tasks.
- If listeners are continuously registered/unregistered dynamically, cache effectiveness can drop.
- Bean initialization, annotation processing, and managing many registrations still have startup/memory costs.

**Learning objectives:** understand the listener selection flow, distinguish **candidate filtering** cost from **handler execution** cost, know why cold and warm lookups differ, write a Java 17+ example to verify type-matching behavior, and design meaningful benchmarks.

## 2. Cost model: total N, matched K, and frequency F

Let:

- `N`: total number of listeners registered in the application context.
- `K(e)`: number of listeners that actually match event `e`; always `0 ≤ K(e) ≤ N`.
- `F(e)`: number of times event `e` is published during a measurement window.
- `S(e)`: cost of selecting the matching listener list, including cache lookup or filtering when needed.
- `H_i(e)`: execution duration of the `i`-th listener.
- `D(e)`: dispatch infrastructure cost, e.g., adapter invocation, logging, instrumentation, executor submission.

With a **synchronous** multicaster, an intuitive model:

```text
T_publish_sync(e)
    ≈ S(e) + D(e) + SUM[H_i(e) for i in matched listeners]
```

This is a decomposition model, **not an exact formula guaranteed by Spring**. In practice, JIT, lock contention, GC, class loading, and each handler's code also affect timing.

Once the cache is warmed and no registration changes occur, `S(e)` is typically smaller than on a cold lookup because the matching list can be reused. However, Spring still has to execute/dispatch each **selected** listener, so total time does not become a constant independent of `K(e)`.

With an **async** multicaster, the caller may only observe:

```text
T_publish_async(e)
    ≈ listener selection + task creation/submission + mandatory sync listeners
```

Actual work then happens on the executor:

```text
T_listener_end_to_end
    = queue_wait + handler_execution + actual downstream steps
```

**Do not measure `publishEvent()` and call that figure the async listener's latency.** It may only reflect enqueue speed.

## 3. How does Spring select listeners?

Conceptual flow:

```text
ApplicationEventPublisher.publishEvent(event)
                       |
                       v
          ApplicationEventMulticaster
                       |
             resolve ResolvableType
                       |
             inspect event / source type
                       |
         find matching listener list
              /                 \
        cache hit       filter candidates needed
              \                 /
                       v
             selected listener list
                       |
                 sort when needed
                       |
               dispatch each listener
                  /            \
            synchronous    task executor
```

Components to know:

- `ApplicationEventPublisher` is the publish API used by application code.
- `ApplicationEventMulticaster` is the abstraction coordinating listeners.
- `SimpleApplicationEventMulticaster` is the standard implementation used in an `ApplicationContext`.
- `AbstractApplicationEventMulticaster` provides management logic, listener lookup, and an internal caching mechanism for candidate retrieval.
- `ResolvableType` helps Spring preserve/read generic type metadata of events and listeners.
- `@EventListener` is detected by Spring and registered as an appropriate adapter; application code does not need to invoke each listener directly.
- Listeners can express their own matching criteria via `ApplicationListener<E>`, `SmartApplicationListener`, or `GenericApplicationListener`.

When an event is a plain object that does not extend `ApplicationEvent`, Spring can wrap it in a `PayloadApplicationEvent` for dispatch. When using `@EventListener` with a payload parameter, Spring still determines the target event type; do not conclude that every object event triggers every listener.

**Implementation note:** cache details and cache keys vary across framework versions. In the Spring Framework 6.1 line, listener retrieval considers both event type and source type; caching is used for cases that can be safely reused. Do not assume every publish or every combination is guaranteed to hit the same cache-hit path.

## 4. Event type matching and cost

### 4.1. Specific generic listener

Example:

```java
public final class OrderPlacedListener
        implements ApplicationListener<OrderPlaced> {

    @Override
    public void onApplicationEvent(OrderPlaced event) {
        // Only handle matching OrderPlaced events.
    }
}
```

This is a **code excerpt**, with `OrderPlaced extends ApplicationEvent` and appropriate imports. When Spring resolves the generic `ApplicationListener<OrderPlaced>`, the framework has enough information to select the listener for `OrderPlaced` without invoking listeners for unrelated event types.

### 4.2. Broad listeners get selected more often

A listener for all events:

```java
@Component
public class GeneralAuditListener
        implements ApplicationListener<ApplicationEvent> {

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        if (event instanceof OrderPlaced orderPlaced) {
            auditOrder(orderPlaced);
        }
    }

    private void auditOrder(OrderPlaced event) {
        // Illustrative task, not a standalone file.
    }
}
```

This example is an **integration snippet**. Even with `if (event instanceof OrderPlaced)`, the listener accepts the very broad `ApplicationEvent` type and can therefore be selected/called for many events, including Spring's own lifecycle events. It shifts part of the filtering work from the multicaster into application code and increases `K(e)` for many events.

If you actually only need `OrderPlaced`, register a listener typed to that exact event. Broad listeners can make sense for framework-level auditing/diagnostics, but you should remain aware that they execute across many events.

### 4.3. Supertypes, inheritance, and generics

A listener typed to a **supertype** can receive multiple subtypes; this follows Java semantics and how Spring handles event types. For instance, if you have `DomainEvent extends ApplicationEvent` and `OrderPlaced extends DomainEvent`, a listener for `DomainEvent` can also receive `OrderPlaced`.

Things to consider:
- Using a broad supertype to centralize logic can route **many events** through the same listener.
- Using a generic listener with overly general types or raw types can make early filtering less precise.
- Proxies and generic type resolution can get complex with class hierarchies, `@Async`, AOP, or registering beans via interfaces. You should test the exact event types being dispatched.

Do not force every event to extend a common base class just to “simplify” things if that creates needlessly broad-scope listeners.

### 4.4. SmartApplicationListener / GenericApplicationListener

Spring supports listeners that provide advanced matching criteria, including:
- `supportsEventType(...)`: which event types the listener supports.
- `supportsSourceType(...)`: which source classes the listener supports, when relevant.
- `getOrder()`/`@Order`: priority when sorting listeners.

These advanced interfaces are useful for libraries or framework integrations, but should not be used just to overcomplicate everyday handlers. For most applications, `@EventListener` with an explicit parameter type or `ApplicationListener<MyEvent>` is sufficient.

**Performance point:** the broader or more expensive the matching logic, the more important it is to measure on cache misses, especially when many rare event types are published. However, never put DB queries, network calls, or heavy computation into listener selection; selection should remain lightweight metadata/type inspection.

## 5. @EventListener: type selection vs. SpEL conditions

Example:

```java
@EventListener(condition = "#event.totalCents() > 100000")
public void onLargeOrder(OrderPlacedPayload event) {
    // Only handle large orders.
}
```

This is an **integration pattern**, assuming `OrderPlacedPayload` is a Spring-recognized type with a `totalCents()` method; it requires `@EventListener`, a bean, and Spring expression infrastructure imports.

There are two distinct decision levels:

1. **Selection by event type:** Spring finds adapters/listeners supporting `OrderPlacedPayload`.
2. **Evaluating `condition`:** the adapter evaluates the corresponding SpEL expression upon receiving the event; if false, the method body is not executed.

A false condition **does not necessarily eliminate the entire dispatch and condition-evaluation cost**. If an event is published tens of thousands of times per second across many handlers with complex SpEL expressions, total condition evaluation time can become significant.

Recommendations:
- Prefer clear event types, keeping business logic inside the handler when needed.
- Avoid complex conditions, traversing large object graphs, or calling getters with side effects.
- Consider creating a **specialized event type** if a condition genuinely distinguishes two different business facts; do not invent many event types solely for micro-optimization at the expense of the domain model.
- Benchmark adapter/condition cost separately from business method cost when fine-tuning.

## 6. Listener cache: cold lookups, warm lookups, and registration changes

In `AbstractApplicationEventMulticaster`, Spring manages listener lists and caches matching retrieval results for event type/source combinations. Practical implications:

### 6.1. Cold path

The first time an event type (or eligible type/source combination) appears, the framework may have to:
- Resolve the event's `ResolvableType`.
- Inspect registered listener instances and listener beans.
- Check event type/source type support, including generic metadata when needed.
- Build the result list and prepare invocation order per policy.
- Store the result in the cache if eligible.

Initial cost can depend on `N`, bean count, number of event types, generic/proxy complexity, and JVM warmup state. Consequently, an event published **once at startup** has a different profile from a hot event type published millions of times.

### 6.2. Warm path

When the same event type/source repeats and the cache entry is valid, the framework can reuse the retrieval result instead of filtering all listeners from scratch. However, it still must:
- Iterate through each selected listener.
- Invoke callbacks/adapters or submit tasks.
- Handle errors, instrumentation, logging, and business work.

That is why **large N with small K** does not necessarily create large overhead for hot events. Conversely, **large K** means each event has to dispatch many times even when the cache is warm.

### 6.3. Dynamic listener registration/removal

`ApplicationEventMulticaster.addApplicationListener(...)`, `removeApplicationListener(...)`, and changes to the listener set can require cache updates or invalidation. If an application continually creates dynamic listeners per request/session, it can:
- Increase live object count and management overhead.
- Reduce opportunities to reuse a stable cache.
- Cause retention/memory leaks if removal is forgotten.
- Cause races or inconsistent observed behavior if listener lifecycle is not well managed.

**Do not register a new Spring application listener per order.** Instead, use a stable listener bean whose payload contains `orderId`/`correlationId` and route as needed inside the business layer.

When genuinely dynamic listeners are needed, enforce clear registration/removal policies and load test, as this behaves differently from fixed listener beans.

## 7. Runnable Java 17+ example: 203 listeners yet only the matching type runs

The following example verifies **type-based listener selection**, without attempting nanosecond benchmarking. We register:
- 200 listeners for `OrderCancelled`.
- 3 listeners for `OrderPlaced`.
- Publish two `OrderPlaced` events and one `OrderCancelled` event.

If each `OrderPlaced` invokes exactly 3 listeners and `OrderCancelled` invokes exactly 200 listeners, the counts are deterministic regardless of machine speed. The code uses **Spring Framework 6.1.21** and needs no Spring Boot or database.

### 7.1. Structure

```text
listener-selection-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/ListenerSelectionDemo.java
```

`settings.gradle`:

```groovy
rootProject.name = 'listener-selection-demo'
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
}

application {
    mainClass = 'demo.ListenerSelectionDemo'
}
```

`src/main/java/demo/ListenerSelectionDemo.java`:

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.ApplicationEvent;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class ListenerSelectionDemo {

    public static final class OrderPlaced extends ApplicationEvent {
        public OrderPlaced(String orderId) {
            super(orderId);
        }
        public String orderId() {
            return (String) getSource();
        }
    }

    public static final class OrderCancelled extends ApplicationEvent {
        public OrderCancelled(String orderId) {
            super(orderId);
        }
        public String orderId() {
            return (String) getSource();
        }
    }

    public static final class PlacedListener
            implements ApplicationListener<OrderPlaced> {

        private final AtomicInteger calls;

        public PlacedListener(AtomicInteger calls) {
            this.calls = calls;
        }

        @Override
        public void onApplicationEvent(OrderPlaced event) {
            calls.incrementAndGet();
        }
    }

    public static final class CancelledListener
            implements ApplicationListener<OrderCancelled> {

        private final AtomicInteger calls;

        public CancelledListener(AtomicInteger calls) {
            this.calls = calls;
        }

        @Override
        public void onApplicationEvent(OrderCancelled event) {
            calls.incrementAndGet();
        }
    }

    public static void main(String[] args) {
        AtomicInteger placedCalls = new AtomicInteger();
        AtomicInteger cancelledCalls = new AtomicInteger();

        try (var context = new AnnotationConfigApplicationContext()) {
            // Register listener instances before refresh.
            for (int i = 0; i < 200; i++) {
                context.addApplicationListener(
                    new CancelledListener(cancelledCalls)
                );
            }
            for (int i = 0; i < 3; i++) {
                context.addApplicationListener(
                    new PlacedListener(placedCalls)
                );
            }

            context.refresh();

            context.publishEvent(new OrderPlaced("ORD-1"));
            context.publishEvent(new OrderPlaced("ORD-2"));
            context.publishEvent(new OrderCancelled("ORD-3"));

            System.out.println("registered=203");
            System.out.println("placed_calls=" + placedCalls.get());
            System.out.println(
                "cancelled_calls=" + cancelledCalls.get()
            );
        }
    }
}
```

Run with JDK 17+ and Gradle:

```bash
gradle run --quiet
```

**Expected business stdout:**

```text
registered=203
placed_calls=6
cancelled_calls=200
```

Explanation:

1. `AnnotationConfigApplicationContext` receives 203 `ApplicationListener` instances before `refresh()`. Each instance has its own object identity, so they are not deduplicated despite sharing classes.
2. During `refresh()`, the context may publish internal lifecycle events. The two listener groups typed to `OrderPlaced`/`OrderCancelled` do **not** receive `ContextRefreshedEvent`; hence they do not skew the counts.
3. Two `OrderPlaced` events are published synchronously. Each event matches only the 3 `PlacedListener`s, so `placed_calls = 2 × 3 = 6`.
4. One `OrderCancelled` triggers the 200 `CancelledListener`s, so `cancelled_calls = 200`.
5. Listeners typed for cancellation do **not** execute and check `instanceof OrderPlaced` themselves: Spring filters candidates by event type before invocation.
6. No executor is configured, so `SimpleApplicationEventMulticaster` uses default synchronous dispatch and the counters are updated before the `publishEvent()` calls return.

**Testing limitations:** the output proves type matching and invocation counts; it **does not directly measure cache hits or filtering time**. Even if you place `System.nanoTime()` around publish, that number also includes class loading, type resolution, callback increments, and JIT warmup; never use a single run as a benchmark to claim “each listener costs X nanoseconds”.

Real-world scenarios must be tested with production-like `N`/`K` ratios and event frequencies, measured using proper tooling.

## 8. Measuring performance properly: avoiding misleading benchmarks

### 8.1. Three quantities to measure separately

| Quantity | Question | How to observe |
| --- | --- | --- |
| **Selection cost** | How long does finding the matching listener list take? | Profiling multicaster/type filtering, controlled cold vs. warm benchmarks |
| **Dispatch/adapter cost** | How much does invoking each listener or submitting a task cost? | No-op listeners, varying K, profiler or benchmark |
| **Business handler cost** | How long does each handler spend working? | Micrometer `Timer`/tracing around handlers; SQL/I/O profiling |
| **Queue wait** | How long does an async task wait before running? | Instrument executor at submit and task start |
| **End-to-end latency** | From fact to completed outcome? | Domain event lifecycle, tracing/outbox/consumer metrics |

`publishEvent()` does not always allow measuring selection in isolation; accurate decomposition requires a profiler/JFR/JMH or instrumentation at the right layer. Do not arbitrarily “subtract handler duration from total duration” if measurements use different clocks, threads, or scopes.

### 8.2. Cold vs. warm lookup benchmarks

Create two scenarios:
- **Cold:** create a context with a fixed listener set, publish an event type never dispatched before (or an unseen source/type combination), and observe startup/classloading separately.
- **Warm:** keep the context steady, publish **the same event type/source** repeatedly after sufficient warmup to reduce JIT and class-loading effects.

Measure these cases:

```text
Case A: N=20,    K=2, no-op listeners
Case B: N=200,   K=2, no-op listeners
Case C: N=2000,  K=2, no-op listeners
Case D: N=2000,  K=200, no-op listeners
Case E: N=2000,  K=200, each handler doing real work
```

These N/K numbers are an **illustrative test design**, not measured results. Comparing A→C shows the effect of total registrations when K is constant (especially on the cold path). Comparing C→D shows how dispatch cost grows when many listeners actually match. Comparing D→E shows how business work outweighs framework overhead.

Do not recreate a Spring context **inside every warm benchmark iteration** unless startup cost itself is the measurement target; otherwise you are measuring creation/refresh/classpath scanning rather than the publish hot path.

### 8.3. Use JMH instead of manual timing loops

JMH handles warmup, measurement iterations, and forks, avoiding many pitfalls from JIT/optimizations/measurement noise. A skeleton (not a standalone compilable file):

```java
@State(Scope.Benchmark)
public class EventPublishBenchmark {
    private AnnotationConfigApplicationContext context;
    private OrderPlaced event;

    @Setup(Level.Trial)
    public void setUp() {
        // Initialize context and register fixed listeners.
        // Publish warmup events if targeting warm selection.
    }

    @Benchmark
    public void publish() {
        context.publishEvent(event);
    }

    @TearDown(Level.Trial)
    public void close() {
        context.close();
    }
}
```

This is a **structural template**: you must add JMH dependencies/plugins, event/listener classes, imports, and a complete `setUp()`. There is no reliable fixed benchmark stdout to invent before running it.

When benchmarking:
- Ensure listeners produce observable effects when needed so the compiler does not eliminate dead work.
- Keep listener count and executor configuration constant; document hardware/JDK/GC in your report.
- Inspect distributions/variance, not just a single average from one machine.
- Separate **context startup** time from the publish hot path.
- Monitor allocation rate/GC and JFR profiles to find real bottlenecks.

### 8.4. Measuring in production with Micrometer and tracing

Commonly useful metrics:

| Metric | Purpose | Recommended tags |
| --- | --- | --- |
| `application.events.publish.duration` | Measures publish calls | Bounded `event_type` |
| `application.events.listener.duration` | Measures handler invocations | `event_type`, `listener`, `outcome` |
| `application.events.listener.errors` | Error counts during handler processing | `listener`, bounded `exception_category` |
| `application.events.executor.queue.wait` | Task wait time | `executor` |
| `application.events.executor.rejected` | Enqueue rejection count | `executor`, `reason` |

Do not use `eventId`, `orderId`, `correlationId`, or exception messages as metric tags: **high cardinality** can cost more than the work being measured. Put those IDs in logs/traces to investigate specific executions.

With sync listeners, `publish.duration` can rise solely because one handler runs a slow DB query; therefore **`listener.duration`** is essential to isolate the bottleneck. With async, measure **queue wait + handler duration** rather than publisher duration alone.

## 9. When K is large: invocation usually matters more than lookup

Suppose 100 listeners all listen for `OrderPlaced`. After cached selection, the framework still must process 100 callbacks:
- Invoke methods, adapters, or proxies.
- Evaluate `@EventListener(condition=...)` if configured.
- Create spans/metrics/logs when instrumented.
- Perform real side effects (DB, HTTP, email, cache, broker).
- If async, enqueue the respective tasks and manage threads/queues and context propagation.

**Caching only reduces candidate selection cost**; it does not collapse 100 matched listeners into a single execution. If each handler takes 10 ms and runs sequentially synchronously, total time can be huge. Do not treat 100 × 10 ms as an absolute formula when overhead or parallelism exists, but it is a clear signal to measure individual handlers.

Options:
1. **Keep event semantics intact:** each independent listener handles one clear concern.
2. **Move slow work out of the request:** use an executor or queue if the business contract permits eventual consistency.
3. **Consolidate operations sharing the same responsibility:** avoid 20 listeners redundantly querying the same table just because classes are in separate files.
4. **Batch I/O where appropriate:** if multiple tasks read from the same source, coordinate them or use an appropriate projection.
5. **Use a transactional outbox** if critical side effects must not be lost after commit.
6. **Do not convert events into direct calls purely for speed at the expense of domain boundaries** when the system needs extensibility/decoupling.

Decide based on measured data, not an arbitrary rule like “over 50 listeners is slow”.

## 10. Async multicaster: how N/K affects task and queue counts

When `SimpleApplicationEventMulticaster` has a `TaskExecutor`:
- Async-capable listeners are typically submitted as tasks instead of running everything on the publisher thread.
- **The number of enqueued tasks** can scale with `K`, not `N`.
- The executor has thread/queue limits; many listeners can grow the queue and increase wait times.
- Excessively tiny tasks can suffer queue/context-switch overhead larger than the business work itself.
- Rejected tasks can fail publish or trigger the executor's rejection policy.

Example:

```text
event_type=OrderPlaced, K=40
     |
     +--> 40 listener tasks
             |
             +--> 8 worker threads running
             +--> remaining tasks waiting in queue
             +--> if queue is full: reject / other policy
```

This is an illustrative scenario, not Spring's default capacity.

**Do not assume async multicaster = one single task per event** across all configurations. The multicaster dispatches per matching listener; the number of submissions depends on which listeners support async. If you also add `@Async @EventListener`, the async proxy path may use a separate executor, introducing an extra task/handoff layer.

### Tuning the executor

Consider during tuning:
- `corePoolSize`, `maxPoolSize`, `queueCapacity`, and rejection policy.
- Whether handlers are CPU-bound or blocking I/O.
- Queue wait time, active threads, and submitted/completed/rejected tasks.
- Events/second × matching listeners per event.
- Latency targets and backpressure.

Do not endlessly increase thread pools when the DB connection pool and downstream APIs are the bottleneck. An oversized pool can increase contention, context switching, and memory usage without increasing throughput.

## 11. Transactional listeners: selection cost differs from execution timing

`@TransactionalEventListener` commonly uses the `AFTER_COMMIT` phase, and can also choose `BEFORE_COMMIT`, `AFTER_ROLLBACK`, or `AFTER_COMPLETION`. In imperative transactions:
- The listener must be bound to transaction synchronization when the event is published.
- Its body runs in the corresponding phase, usually later than `publishEvent()`.
- If there is no active transaction, the listener does not run by default unless `fallbackExecution=true`.

Therefore, benchmarking `publishEvent()` inside a transaction may measure **registration overhead**, without measuring the full `AFTER_COMMIT` body. You must measure the handler at its execution phase and measure transaction commit separately if needed.

Example:

```java
@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)
public void onOrderPlaced(OrderPlacedEvent event) {
    externalNotificationService.notify(event.orderId());
}
```

This is an **integration snippet**, not a standalone program. `OrderPlacedEvent`, the service, and imports need to be defined. It also carries reliability implications: a post-commit callback is not a durable queue; a crash after DB commit can lose the side effect if not yet sent. When reliable delivery is required, use an outbox and monitor backlog/lag/retry metrics.

**Do not use `@Order` to assume async listeners will finish in order.** Ordering invocation or registration does not guarantee task completion order, transaction ordering, or broker ordering.

## 12. When is optimizing selection actually necessary?

Optimizing selection is worth considering when you observe signs such as:
- `publishEvent()` takes significant CPU in a profiler while handlers are essentially no-ops.
- Events occur at very high frequency (e.g., on a hot data-processing path) requiring very low latency.
- There are very many rare type/source combinations, causing a high rate of cold lookups.
- Code continually creates/destroys listeners, preventing cache stabilization.
- Overly broad generic listeners cause many events to trigger unrelated handlers.
- Many `@EventListener(condition=...)` expressions are evaluated yet rarely execute their bodies.

Conversely, if a profiler shows 90% of time is spent in listener SQL/HTTP/serialization, optimizing generic matching will barely move the needle. Fix the bottleneck at the right layer.

### Decision matrix

| Observation | Hypothesis to verify | Action |
| --- | --- | --- |
| Slow startup, steady runtime publish | Heavy scanning/bean creation | Lazy/lifecycle tuning, reduce duplicate config, profile startup |
| Slow cold publish, fast warm publish | Type matching/class loading/cache | Warmup or reduce dynamic registration if truly needed |
| Slow warm publish, large K | Dispatching many handlers | Consolidate redundant listeners, handle I/O efficiently |
| Slow warm publish, small K | Slow handler or adapter/proxy overhead | Profile per-handler, benchmark the right path |
| Fast async publish, delayed side effects | Executor queue/worker saturation | Measure queue wait, pool sizing, downstream latency |
| Errors rise when queue fills | Rejection/capacity | Bounded queue, retry/outbox, backpressure |
| Low cache hit rate after config changes | Listener set changes frequently | Keep registrations stable and manage lifecycle |

**Do not optimize by stripping error handling, disabling tracing everywhere, or breaking domain correctness** just to achieve a low microbenchmark latency number.

## 13. Testing type matching and scalability

### 13.1. Correctness testing

The example in section 7 verifies:
- `OrderPlaced` only invokes listeners supporting `OrderPlaced`.
- `OrderCancelled` only invokes listeners supporting `OrderCancelled`.
- Invocation counts are exact, not inflated by Spring lifecycle events.

With `@EventListener`:
- Test both event classes and generic payloads if used.
- Test subtype/supertype matching.
- Test true and false SpEL `condition`s.
- Test `supportsSourceType(...)` if implementing custom advanced listeners.
- Test listener beans registered via proxies/AOP if used by the application.

### 13.2. Performance testing

Maintain a separate benchmark suite rather than hardcoding nanosecond thresholds in ordinary unit tests. Benchmarks should:
- Keep Java/JVM and context configuration consistent across variants.
- Measure cold and warm separately; warm up before sampling hot-path numbers.
- Vary K with fixed N, and vary N with fixed K.
- Distinguish sync/async, no-op handlers, and real handlers.
- Ensure no accidental network/DB calls appear in selection microbenchmarks.
- Record allocation rate, GC, CPU profiles, and confidence/variance when comparing.
- Never treat differences below noise level as architectural improvements.

### 13.3. Separate async and transaction tests

If an executor is enabled on the multicaster, await listeners with `CountDownLatch`, `CompletableFuture`, or real completion signals rather than relying on `Thread.sleep()` before asserting. If listening for `AFTER_COMMIT`, actually commit the transaction before awaiting callbacks; Spring Test's `@Transactional` rolls back at the end of tests by default and thus does not trigger `AFTER_COMMIT` automatically.

### 13.4. Load testing and observability

Monitor:
- Event volume and active handler counts.
- p95/p99 `listener.duration` and `publish.duration`.
- Executor queue wait, queue depth, active threads, and rejections.
- Success/error rates and retry counts.
- GC pressure as event/task volume grows.
- Outbox age if critical processing uses durable messaging.

Passing a simple 2-listener test does not prove a system with 200 listeners, many event types, and peak traffic meets its SLA; load test with a production-like workload distribution.

## 14. Common mistakes

1. **Assuming every publish iterates/invokes all listeners.** Spring performs type filtering and candidate retrieval caching; distinguish selection from invocation.
2. **Assuming caching makes matched listener count irrelevant.** Each matched listener still creates work or a task.
3. **Measuring a single `System.nanoTime()` and calling it a framework benchmark.** Cold classloading/JIT/GC easily skews results.
4. **Failing to distinguish N and K.** 500 total listeners with 2 matching is very different from 500 listeners all matching.
5. **Using an `ApplicationEvent` listener to manually filter everything.** Can route massive numbers of events through a broad-scope handler.
6. **Creating dynamic listeners per request.** Increases registrations, memory, and cache invalidations.
7. **Using very complex SpEL conditions as a way to avoid all cost.** The adapter may still evaluate the condition every time.
8. **Assuming `@EventListener` rescans methods on every event.** Annotation processing happens mostly at setup; runtime still has adapter/invocation overhead.
9. **Measuring async publish and concluding handlers are fast.** Publish may only be submitting tasks.
10. **Ignoring queue wait/rejections.** Async lightens the request while building a hidden backlog.
11. **Forcing every listener to be async.** Alters transaction, ordering, and error-handling semantics.
12. **Treating `@Order` as a sequential completion guarantee in a thread pool.** Dispatch order and completion order differ.
13. **Equating `AFTER_COMMIT` with async/durable.** It is a transaction phase, not a broker.
14. **Attaching event ID/correlation ID as metric tags.** High cardinality strains the monitoring system.
15. **Optimizing selection before profiling listener I/O.** Most time is often spent in DB/network rather than the multicaster.

## 15. Design and review checklist

- [ ] Do you know total listeners N and matched listeners K for critical events?
- [ ] Are listeners explicitly typed, avoiding overly broad event types when unnecessary?
- [ ] Is it clear that hot lookup caching does not eliminate invocation cost for K handlers?
- [ ] Do you avoid creating/destroying listeners per request/event without an architectural reason?
- [ ] Are startup/first publish separated from warm steady state?
- [ ] Are `publish.duration` and `listener.duration` measured as two separate quantities?
- [ ] Are event type/subtype/source matching tested when using advanced listeners?
- [ ] Are SpEL conditions lightweight, semantically accurate, and free of I/O?
- [ ] Are optimization decisions never based on a single nanosecond sample?
- [ ] If async, are queue wait, active threads, rejections, and handler completion measured?
- [ ] If transactional, is listener registration separated from commit-phase body execution?
- [ ] Do error/retry/idempotency mechanisms match the event's criticality?
- [ ] Do metrics use only bounded tags, keeping event IDs in logs/traces?
- [ ] Does reducing listener count preserve domain facts, isolation, and maintainability?

**Conclusion:** the total number of registered listeners (`N`) affects management, cold matching, and footprint; the number of **actually matching** listeners (`K`) determines how many callbacks/tasks run per event. Spring Framework Application Events uses type-based selection and retrieval caching, so every publish does not simply call all N listeners. To optimize properly, measure selection, dispatch, handlers, queues, and transactions at **the right boundaries**, and tune architecture to real workloads.

## References

- [Spring Framework Reference — ApplicationContext Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html)
- [Spring 6.1 API — AbstractApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html)
- [Spring 6.1 API — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html)
- [Spring 6.1 API — GenericApplicationListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/GenericApplicationListener.html)
- [Spring 6.1 API — SmartApplicationListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/SmartApplicationListener.html)
- [Spring 6.1 API — ApplicationListener](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/ApplicationListener.html)
- [Spring 6.1 API — EventListener annotation](https://docs.spring.io/spring-framework/docs/6.1.21/javadoc-api/org/springframework/context/event/EventListener.html)
- [OpenJDK Java Microbenchmark Harness (JMH)](https://github.com/openjdk/jmh)
- [Micrometer Timers](https://docs.micrometer.io/micrometer/reference/concepts/timers.html)
