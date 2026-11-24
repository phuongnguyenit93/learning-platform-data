# Listener Caching in Spring Framework's Multicaster

## 1. Why does the multicaster need to cache the listener list?

In the **Spring Application Events** model, code publishes events via `ApplicationEventPublisher.publishEvent(...)`, while `ApplicationEventMulticaster` determines which `ApplicationListener`s match and invokes them. A context can hold very many listeners: listeners for `OrderPlacedEvent`, listeners for `PaymentCapturedEvent`, general listeners for `ApplicationEvent`, `@EventListener` methods, and listeners with generic constraints or specific `source` types.

If Spring had to rescan the entire listener list, analyze each bean's generic types, and check event eligibility on every single publish, **listener selection** could become notable overhead on the hot path. Therefore, standard multicasters based on `AbstractApplicationEventMulticaster` include a mechanism to **cache pre-filtered listener selection results** for encountered event/source types.

The goals of this cache are:

- Reduce how often Spring checks whether listeners support an event type and source type.
- Limit repeating certain generic type inference / listener bean lookup steps.
- Improve efficiency when an application publishes **very many events of the same type** with a rarely changing listener set.
- Still preserve the ability to refresh the list when a listener is added or removed via the multicaster API.

**Listener caching is not an event content cache, not a business result cache, not an event storage system, and does not cause listeners to skip subsequent events.**

Example: publishing 10,000 `OrderPlacedEvent`s with the same source type back-to-back. Spring can reuse the *type-matched listener candidate set* for subsequent publishes; however, `onOrderPlaced(...)` is still invoked for **each event**, `@EventListener(condition=...)` expressions must still be evaluated against **each event's data**, and business logic runs on every actual delivery.

## 2. Where the cache sits in the event dispatch flow

Conceptual flow:

~~~text
ApplicationEventPublisher.publishEvent(event)
    |
    v
ApplicationContext
    |
    v
ApplicationEventMulticaster.multicastEvent(event, eventType)
    |
    v
AbstractApplicationEventMulticaster.getApplicationListeners(...)
    |
    +-- Build key from ResolvableType(event) + sourceType(event)
    |
    +-- Suitable cache hit?
    |       |
    |       +-- Yes -> use pre-filtered listener list
    |       |
    |       +-- No -> check listeners by event/source type
    |                 -> may store result in cache
    |
    v
SimpleApplicationEventMulticaster.invokeListener(...)
    |
    +-- ApplicationListener / GenericApplicationListener
    |       -> process new event
    |
    +-- ApplicationListenerMethodAdapter (@EventListener)
            -> evaluate condition for the current EVENT
            -> invoke method if condition holds
~~~

Classes to distinguish:

| Component | Responsibility |
| --- | --- |
| `ApplicationEventPublisher` | API used by application code to publish events. |
| `ApplicationContext` | Usually acts as the publisher and delegates broadcasting to the multicaster. |
| `ApplicationEventMulticaster` | Manages listeners, selects matching listeners, and dispatches events. |
| `AbstractApplicationEventMulticaster` | Provides listener registration and cached selection/pre-filtering logic. |
| `SimpleApplicationEventMulticaster` | Event broadcasting implementation; invokes listeners synchronously on the publisher thread by default, configurable with an executor. |
| `GenericApplicationListener` | Listener that can declare support for `ResolvableType` and `sourceType`; helpful for explaining matching mechanics. |
| `ApplicationListenerMethodAdapter` | Adapter used for `@EventListener` methods; handles conditions and method arguments. |

**Important separation:** `getApplicationListeners(...)` finds **who is eligible to receive** an event by type/source. It does not necessarily determine that a method satisfies business conditions to run. For instance, a listener with `@EventListener(condition="#p0.amount() > 1000")` can still appear in the cached candidate set for every `PaymentChanged`; on each delivery, it must check that specific event's `amount()`.

## 3. Cache key: event ResolvableType and source Class

In `AbstractApplicationEventMulticaster`'s implementation in the Spring Framework 6.2 line, the listener pre-filter key has two main parts:

1. **`ResolvableType eventType`**: event type metadata; may carry generic type info if known to Spring.
2. **`Class<?> sourceType`**: class of `event.getSource()` (when present).

Example:

~~~text
Key A:
  eventType = OrderPlacedEvent
  sourceType = String
  -> candidate listener list for this event type and this source class

Key B:
  eventType = OrderPlacedEvent
  sourceType = Integer
  -> a different key despite the same event class

Key C:
  eventType = PaymentCapturedEvent
  sourceType = String
  -> a different key because the event type differs
~~~

**Source type is not source value.** Two events whose `getSource()` returns different strings (`"checkout-1"` and `"checkout-2"`) still share **the same source class `String`**, and can thus share a key. An event with an `Integer` source produces a different key even if the business payload is unchanged.

For plain payload objects published directly, Spring typically wraps them in `PayloadApplicationEvent<T>`. `ResolvableType` can include the generic payload type `T` to select listeners by payload type. Therefore, do not look solely at `event.getClass() == PayloadApplicationEvent.class` and assume every payload gets the same listener set. **Generic metadata can be a key part of matching.**

This describes Spring 6.2's implementation, **not a public guarantee that every subclass, every Spring version, and every configuration shares the exact same cache-key implementation**. When customizing a multicaster, read the Javadoc/source of your exact version.

## 4. Cache miss, cache hit, and matching cost

### 4.1. First time encountering a key

On the normal path, when the cache lacks an entry for `(eventType, sourceType)`, the multicaster may:

- Retrieve directly registered listener instances.
- Retrieve listener bean names from `BeanFactory` as appropriate.
- Check whether each listener supports the event type.
- For listeners supporting source filtering, check `sourceType`.
- Sort listeners by `Ordered` / `@Order` when needed.
- Store the pre-filtered listener set (or matching bean name info) in a cache structure.

A cache miss does not mean “no listener receives it”. It simply means no precomputed selection exists yet for that key. Even **an empty result set** can be useful to avoid rescanning candidates every time an unsubscribed event type is published.

### 4.2. Subsequent publishes with the same key

On a warm cache hit, Spring can skip repeated candidate selection steps, use the stored list/metadata, and proceed to dispatch. **Each event still needs to be delivered to matching listeners**; the cache is not a deduplication tool and does not reduce business method invocations.

This is especially helpful when the system repeats a small set of event types. For example:

~~~text
10,000 OrderPlacedEvents with the same source class
    |
    +-- first pass: compute candidate set
    +-- later passes: can retrieve pre-filtered candidate set
    |
    +-- listener still receives 10,000 events
~~~

If every event uses a distinct source class or there are very many dynamic event types, cache hit ratios may be lower even when event volume is high.

### 4.3. Not every lookup is guaranteed to be cacheable

Spring takes precautions to avoid caching classes not considered **cache-safe** with respect to the application's bean classloader. In environments with changing classloaders such as hot reload, plugin loading, or complex container deployments, do not assume every event always gets a cache entry.

Under concurrency, one thread may encounter an entry being constructed by another thread; Spring can perform local selection rather than treating an incomplete entry as valid. This protects correctness, meaning **counting matching calls in a multithreaded system is not a measure of “absolute cache hits”**.

## 5. When adding or removing listeners, does the cache stay accurate?

If the listener set changed without updating the cache, the multicaster could dispatch to removed listeners or miss newly added ones. Thus **cache invalidation is a mandatory part of the listener registration mechanism**.

In Spring 6.2's implementation, APIs that mutate the listener set cause the selection cache to refresh:

- `addApplicationListener(listener)`: add a listener instance.
- `addApplicationListenerBean(beanName)`: add a listener by bean name.
- `removeApplicationListener(listener)`: remove an instance.
- `removeApplicationListenerBean(beanName)`: remove a listener bean.
- `removeApplicationListeners(predicate)` and `removeApplicationListenerBeans(predicate)`: conditional removal.
- `removeAllListeners()`: remove all registered listeners.

Diagram:

~~~text
Cache: (TicketEvent, String) -> [TicketListener]
            |
            | multicaster.removeApplicationListener(TicketListener)
            v
      Selection cache refreshed
            |
            | publish new TicketEvent
            v
      Removed TicketListener is not called

multicaster.addApplicationListener(TicketListener)
            |
            v
      Cache refreshed again
            |
            | publish TicketEvent with same old key
            v
      TicketListener can be selected again
~~~

**Do not—and never need to—manipulate `retrieverCache` directly via reflection “just to be sure it is cleared”.** That is an internal implementation detail. Register or remove listeners through the official API.

An important distinction: if you **mutate internal state** of a listener without changing registration, Spring does not treat that as a reason to invalidate. If a listener's `supportsEventType(...)` or `supportsSourceType(...)` depends on mutable state that changes over time, cached results may not reflect your intended usage. Treat these predicates as **relatively stable type-support capabilities**, not per-event dynamic content filters.

## 6. Runnable Java 17+ example: observing cached matching

The example below does not touch internal cache fields. Instead, it defines a `GenericApplicationListener` that counts how many times Spring asks **“does this listener support this event type?”**, then publishes several events and mutates registration.

In a standalone `SimpleApplicationEventMulticaster` on the pinned version, repeated publishes of the same type and source class reuse the candidate set, so the type-check counter does not increment on the second call. When the source class changes, the key differs and the counter increments. After removing and re-adding the listener, matching must be recomputed.

The example uses Spring Framework **6.2.9** (pinned version so output is deterministic), Java 17+, and Maven. No `ApplicationContext` is needed because we want to observe **the multicaster directly** without context lifecycle listeners.

### 6.1. Project structure

~~~text
listener-cache-demo/
├── pom.xml
└── src/main/java/ListenerCacheDemo.java
~~~

`pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>example</groupId>
    <artifactId>listener-cache-demo</artifactId>
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

File `src/main/java/ListenerCacheDemo.java`:

~~~java
import org.springframework.context.ApplicationEvent;
import org.springframework.context.event.GenericApplicationListener;
import org.springframework.context.event.SimpleApplicationEventMulticaster;
import org.springframework.core.ResolvableType;

public class ListenerCacheDemo {

    public static final class TicketEvent extends ApplicationEvent {
        private final String ticketId;

        public TicketEvent(Object source, String ticketId) {
            super(source);
            this.ticketId = ticketId;
        }

        public String ticketId() {
            return ticketId;
        }
    }

    public static final class CountingListener
            implements GenericApplicationListener {

        private int typeChecks;
        private int received;

        @Override
        public boolean supportsEventType(ResolvableType eventType) {
            typeChecks++;
            return TicketEvent.class.equals(eventType.toClass());
        }

        @Override
        public void onApplicationEvent(ApplicationEvent event) {
            TicketEvent ticketEvent = (TicketEvent) event;
            received++;
            System.out.println("HANDLE " + ticketEvent.ticketId());
        }

        public int typeChecks() {
            return typeChecks;
        }

        public int received() {
            return received;
        }
    }

    public static void main(String[] args) {
        var multicaster = new SimpleApplicationEventMulticaster();
        var listener = new CountingListener();

        multicaster.addApplicationListener(listener);

        // Two events of the same type + both sources are String.class.
        multicaster.multicastEvent(new TicketEvent("web-1", "T-1"));
        multicaster.multicastEvent(new TicketEvent("web-2", "T-2"));

        System.out.println("TYPE_CHECKS_AFTER_TWO="
                + listener.typeChecks());

        // Same event type, but source is Integer instead of String.
        multicaster.multicastEvent(new TicketEvent(42, "T-3"));

        System.out.println("TYPE_CHECKS_NEW_SOURCE="
                + listener.typeChecks());

        // Remove listener and publish another event: no handler left.
        multicaster.removeApplicationListener(listener);
        multicaster.multicastEvent(new TicketEvent("web-3", "T-4"));
        System.out.println("RECEIVED_WHILE_REMOVED="
                + listener.received());

        // Re-register listener; type-based selection is recomputed.
        multicaster.addApplicationListener(listener);
        multicaster.multicastEvent(new TicketEvent("web-4", "T-5"));

        System.out.println("TYPE_CHECKS_AFTER_READD="
                + listener.typeChecks());
        System.out.println("TOTAL_RECEIVED=" + listener.received());
    }
}
~~~

Run in the directory containing `pom.xml` with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=ListenerCacheDemo
~~~

**Program stdout in the illustrative configuration (Spring Framework 6.2.9, synchronous multicaster, no other listeners):**

~~~text
HANDLE T-1
HANDLE T-2
TYPE_CHECKS_AFTER_TWO=1
HANDLE T-3
TYPE_CHECKS_NEW_SOURCE=2
RECEIVED_WHILE_REMOVED=3
HANDLE T-5
TYPE_CHECKS_AFTER_READD=3
TOTAL_RECEIVED=4
~~~

### 6.2. Reading the results correctly

- `T-1`: Spring must look up the listener set for key `(TicketEvent, String)` for the first time, so it calls `supportsEventType(...)`.
- `T-2`: still `TicketEvent` with source class `String`, so it uses the cached selection; `typeChecks` does not increase, yet `onApplicationEvent(...)` **still runs**.
- `T-3`: event type is unchanged, but source is `Integer`, creating a different key. Spring checks event type support again, incrementing `typeChecks` to 2.
- Removing the listener then publishing `T-4`: the multicaster does not invoke the removed listener; `received` stays 3. Do not confuse this with a business condition filtering out an event.
- Re-adding the listener then publishing `T-5`: the registration set and cache changed; Spring re-evaluates event type support, raising the counter to 3.
- Total `onApplicationEvent(...)` executions is **4**, even though `supportsEventType(...)` was only checked 3 times. This is the exact difference between **matching cache** and **invocation**.

**Measurement limitations:** this counter reflects calls to a matching predicate in the demo configuration; it does not directly measure latency, allocations, or throughput. Nor does it represent exact cache hit/miss counts across all Spring versions or custom multicasters. To inspect real implementation fields, use a profiler or source inspection while investigating, without turning internal fields into application APIs.

## 7. GenericApplicationListener, SmartApplicationListener, and @EventListener

### 7.1. Simple ApplicationListener<E>

~~~java
@Component
class OrderListener implements ApplicationListener<OrderPlacedEvent> {

    @Override
    public void onApplicationEvent(OrderPlacedEvent event) {
        // Business logic for matched events.
    }
}
~~~

*Illustrative integration snippet: requires importing `ApplicationListener`, `@Component`, and defining `OrderPlacedEvent extends ApplicationEvent`.*

With this style of listener, Spring uses the generic type information (`OrderPlacedEvent`) to check event compatibility. Depending on class and bean configuration, `GenericApplicationListenerAdapter` may assist in resolving the listener's generic type.

### 7.2. GenericApplicationListener when filtering event/source types

~~~java
class RegionListener implements GenericApplicationListener {

    @Override
    public boolean supportsEventType(ResolvableType eventType) {
        return OrderPlacedEvent.class.isAssignableFrom(
                eventType.toClass());
    }

    @Override
    public boolean supportsSourceType(Class<?> sourceType) {
        return sourceType != null &&
                RegionEventPublisher.class.isAssignableFrom(sourceType);
    }

    @Override
    public void onApplicationEvent(ApplicationEvent event) {
        // Handle events that passed matching.
    }
}
~~~

*This is illustrative integration code: `OrderPlacedEvent` and `RegionEventPublisher` must be defined, along with imports for `GenericApplicationListener`, `ResolvableType`, and `ApplicationEvent`.*

Here `supportsSourceType(...)` receives a **Class**, not the `source` instance; do not write logic attempting to inspect a `regionId` field on a source object. If you need to filter by per-event data, use a condition or check inside the handler.

### 7.3. @EventListener with condition

~~~java
@EventListener(condition = "#p0.totalMinorUnits() >= 100000")
public void onLargeOrder(OrderPlaced event) {
    // Each event has a different totalMinorUnits value.
}
~~~

*Illustrative snippet for a bean with a method accepting a matching `OrderPlaced` record.*

Spring can cache the determination that **this listener method supports the OrderPlaced type**. However, **the SpEL condition must be evaluated per payload**, because event `A` might have an amount of 120,000 while event `B` might only have 30,000. Thus:

~~~text
Same eventType/sourceType
    |
    +-- listener candidate list: cached
    |
    +-- Event A: total=120000 -> condition true -> handler invoked
    |
    +-- Event B: total=30000  -> condition false -> handler skipped
~~~

This is a common point of confusion: “the listener is in the cache” **does not mean** `@EventListener(condition)` was evaluated to true and cached permanently.

## 8. Listener beans, singletons, and prototypes: what does the cache retain?

The multicaster can register listeners in two ways:

~~~java
multicaster.addApplicationListener(existingListener);
multicaster.addApplicationListenerBean("auditEventListener");
~~~

*Two illustrative calls for a multicaster wired with a BeanFactory if registering by bean name.*

- `addApplicationListener(...)` takes an instance and places it into the listener set managed by the multicaster.
- `addApplicationListenerBean(...)` takes a **bean name**, allowing the multicaster to resolve the bean via `BeanFactory` and avoid unnecessary instantiation during registration.
- In Spring 6.2's implementation, the cache can hold pre-filtered **listener instances** and/or **listener bean names**, rather than permanently pinning every instance across all scopes.
- For non-singleton beans, Spring must preserve bean scope semantics; **do not claim** that every publish with the same key will reuse a single prototype object simply because a cache entry exists.

When debugging prototype listeners, distinguish **listener type selection cost** from **instance creation cost**. Matching caches can reduce the former overhead, while prototype creation still carries its own cost and lifecycle.

**Recommendation:** use singleton, stateless listeners for most domain/application events. If per-event data is needed, pass it in the payload or create local state inside the handler; avoid storing per-event mutable state on a singleton bean without proper synchronization.

## 9. Cache invalidation does not replace dynamic business logic

An architectural mistake is trying to use `supportsEventType` or `supportsSourceType` to filter conditions that vary **per event value** or based on a frequently toggled feature flag:

~~~java
// Conceptual anti-pattern:
@Override
public boolean supportsEventType(ResolvableType type) {
    return featureFlagService.isEnabled() &&
           TicketEvent.class.equals(type.toClass());
}
~~~

*Illustrative snippet without complete class/dependencies.*

If the feature flag changes while the application is running, **matching caches are not required to re-evaluate the predicate for every event sharing the key**. The listener may remain in or stay excluded from the candidate list until the cache changes for another reason.

If a feature flag must be checked per occurrence:

~~~java
@Override
public boolean supportsEventType(ResolvableType type) {
    return TicketEvent.class.equals(type.toClass());
}

@Override
public void onApplicationEvent(ApplicationEvent event) {
    if (!featureFlagService.isEnabled()) {
        return;
    }
    handleTicket((TicketEvent) event);
}
~~~

*Illustrative integration snippet; requires defining `featureFlagService` and `handleTicket`.*

This way, type matching stays stable while the business decision is evaluated **each time an event arrives**. If you genuinely need to stop a listener due to configuration changes, you can remove it via the official registration/removal API and re-add it later, while carefully managing thread-safety, lifecycle, and ownership.

Similarly, never use the matching cache to infer that a listener successfully processed the previous event. If the business handler fails, the candidate cache does not “remember” the failure or automatically retry.

## 10. Generic event types and PayloadApplicationEvent

Spring supports selecting listeners by generic type via `ResolvableType`. That is why `multicastEvent(event, eventType)` accepts an explicit type hint when available.

For example, suppose a system has:

~~~java
public record OrderPlaced(String orderId) {}
public record PaymentCaptured(String paymentId) {}
~~~

When calling:

~~~java
publisher.publishEvent(new OrderPlaced("ORD-1"));
publisher.publishEvent(new PaymentCaptured("PAY-1"));
~~~

*These snippets are illustrative integration patterns with `ApplicationEventPublisher`; appropriate imports and bean context are required.*

Objects not extending `ApplicationEvent` are wrapped by Spring as `PayloadApplicationEvent<OrderPlaced>` or `PayloadApplicationEvent<PaymentCaptured>` for generic typing purposes. Listener methods can declare `onOrderPlaced(OrderPlaced event)` and `onPayment(PaymentCaptured event)` so Spring dispatches accurately.

**Having the same runtime wrapper class does not mean cache matching is identical.** `ResolvableType` carries payload type information when available. If you publish an event whose generic type is erased or whose type hint is incomplete, matching behavior can differ; when designing truly generic events, consider implementing `ResolvableTypeProvider` or supplying a type hint through the appropriate API if Spring requires it.

A practical performance issue arises when there are too many hyper-specific event types or dynamic source classes, which can grow the number of cache keys. However, **do not optimize by collapsing all events into a single `ObjectEvent` and manually switching on type in every listener**, as that sacrifices type safety and makes contracts hard to maintain. Only alter event design when measurements prove a bottleneck.

## 11. Synchronous, asynchronous, and listener ordering

The candidate cache **does not decide** which thread runs a listener. `SimpleApplicationEventMulticaster` invokes listeners on the publisher thread by default. When configured with an executor, it can run listeners on another thread:

~~~java
var multicaster = new SimpleApplicationEventMulticaster();
multicaster.setTaskExecutor(eventExecutor);
~~~

*Integration snippet; requires an appropriate `eventExecutor` and executor lifecycle management.*

Differences to keep clear:

| Property | Listener selection cache | Executor / @Async |
| --- | --- | --- |
| Goal | Reduce overhead of finding matching listeners | Change where and when listeners execute |
| Input | Event type, source type, and registry | Tasks, queue, worker threads |
| Output | Listener candidate set | Listener execution schedule |
| Does it make listener bodies run fewer times? | No, apart from required type filtering | Does not reduce event count; only changes concurrency |
| Does it automatically pass ThreadLocal to workers? | No | Not by default; requires proper context propagation |
| Does it guarantee retries/durable delivery? | No | No |

With an async executor, completion order can differ from publish order even when the listener list is sorted by `@Order`. Spring 6.1+ also provides `supportsAsyncExecution()` so certain listeners (e.g., transaction-synchronized listeners) require execution on the original thread at the multicaster level.

Do not blame **delayed listener execution**, **lost ThreadLocals**, **different log ordering**, or **missing transactions** on the selection cache. Those are almost always matters of scheduling, context propagation, transactions, or lifecycle.

## 12. Performance: how much does matching cache help?

There is no fixed “X% faster” figure for every application. The benefit depends on:

- Number of registered listeners.
- Actual number of event types and source classes.
- Repetition rate of `(eventType, sourceType)` keys.
- Complexity of generic matching, `supportsEventType`, and `supportsSourceType`.
- Singleton/prototype bean resolution.
- Listener body cost: DB queries, HTTP, file writes, serialization, logging, transactions, and retries.
- Executor queuing, context switching, allocations, contention, and GC.
- Frequency of dynamic listener registration/removal causing cache invalidations.

If each listener makes a 200 ms HTTP call, saving a few type checks via matching cache will hardly be the main bottleneck. Conversely, for very short, high-frequency internal events with hundreds of listeners, candidate selection overhead can become noticeable.

### 12.1. Measuring the right things

To evaluate effectiveness, distinguish:

1. **End-to-end publish latency:** from calling `publishEvent` until synchronous listeners finish (does not mean completion if async is involved).
2. **Listener selection overhead:** cost of finding candidates by event/source type.
3. **Listener invocation overhead:** adapter creation/coordination/handler invocation.
4. **Business handler latency:** DB, network, locks, IO, business rules.
5. **Async queue delay:** time spent waiting before a worker starts.
6. **Allocation/GC:** allocations from event instances, adapters, context propagation, and logging.

When profiling, inspect whether stack/frames spend significant time in `AbstractApplicationEventMulticaster.getApplicationListeners(...)`, `GenericApplicationListenerAdapter`, `ApplicationListenerMethodAdapter`, or inside the handler itself.

### 12.2. Reliable benchmarks instead of a single System.nanoTime()

If microbenchmarking is needed, use **JMH** or an equivalent profiler, including:

- Warming up the JVM/JIT and warming up the tested event types.
- Testing one repeated event type, multiple interleaved event types, and diverse source types.
- Comparing different listener counts, such as 10/100/1000.
- Keeping `System.out.println(...)` out of the hot loop: console IO masks selection cost.
- Keeping matched listener counts and business work constant across runs.
- If running async, measuring queueing/backpressure and when all listeners actually finish.
- Collecting p50/p95/p99, throughput, CPU, allocations, and errors instead of a single mean.
- Controlling environment variables: JDK, Spring version, heap, GC, hardware, and CPU affinity.

The example in section 6 illustrates **matching behavior**, not benchmark results. Never infer percentage speedups from the number of `supportsEventType(...)` calls.

## 13. Caching, classloader issues, and hot reload

Cache structures hold references to Java types. In environments where classloaders change (devtools restart, plugin unload, server deploy/undeploy), retaining stale classes can cause memory issues. Therefore, Spring's implementation checks **cache-safety** before storing event/source classes in applicable cases.

Key principles:

- Do not build your own static global map caching `Class<?>` or `ResolvableType` without a lifecycle strategy when the application uses dynamic class loading.
- For each new `ApplicationContext`, treat the listener registry and cache as part of the context lifecycle; do not arbitrarily reuse an old multicaster across reload cycles.
- If a plugin defines its own event classes, define who owns and removes its listeners on plugin unload; do not use reflection on the cache “to try clearing it”.
- During memory profiling, distinguish valid cache keys from leaks caused by classloaders/resources held by the application.
- Do not estimate cache size solely from published event count: keys are tied to **types**, not payload values.

In systems with many distinct source classes, the cache can hold more entries than expected. That is why you should use meaningful source objects and avoid creating random new source types per event.

## 14. Cases blamed on cache where the root cause lies elsewhere

| Symptom | Common wrong guess | Root cause to check |
| --- | --- | --- |
| Listener stops receiving new events | Cache holds stale list | Event type mismatch, unregistered bean, different context, SpEL condition false |
| Listener runs intermittently | Cache is “random” | Changing event data/conditions, transaction phase, async race |
| Still see one log after removing listener | Cache wasn't invalidated | An async task was submitted before removal; or another listener exists |
| Listener receives duplicates | Cache invokes twice | Multiple listeners handling it, context hierarchy propagating via parent, duplicate app-level registration |
| Old events do not appear after adding listener | Cache didn't refresh | Spring Application Events is not an event history/replay store |
| Listener spikes CPU | Cache is “ineffective” | Handler logic, IO/logging/SpEL/serialization/locks are the real bottleneck |
| Generic event routing bug | Wrong cache key | Insufficient generic info in `ResolvableType`, incompatible listener declaration |
| Prototype listener is a different object across events | Cache isn't working | Type-matching cache is separate from bean lifecycle and scope |
| Async listener misses transaction | Cache drops transaction | Thread-bound transactions do not transfer automatically across executors |
| Feature flag toggled yet listener stays in candidate set | Cache is too “sticky” | Dynamic business predicate put in `supportsEventType` instead of the handler |

### Async tasks queued before listener removal

A subtle nuance: even when `removeApplicationListener(...)` refreshes the cache, **tasks already submitted by the multicaster to an executor before removal** may still hold a reference to the listener. Thus, additional logs can appear after removal without proving Spring kept selecting the removed listener for events published *afterward*.

If immediate cessation is required, you must manage executor lifecycle, cancellation, queue draining, shutdown flags, and idempotency as required; cache invalidation alone does not promise “all running tasks stop immediately”.

## 15. Safe usage in real-world applications

### 15.1. Keep listener types stable, place business filters at the right layer

- Use event classes/records that clearly describe business facts.
- Use typed `ApplicationListener<E>` or `@EventListener`; avoid broad `ApplicationListener<ApplicationEvent>` across modules unless needed.
- Never place dynamic feature flags or event content checks inside `supportsEventType(...)`.
- For short rules, use `@EventListener(condition=...)`; for complex rules, handle them in well-tested services/handlers.
- Never try to “precompute business results” during type selection.

### 15.2. Avoid continuously registering/removing listeners on the hot path

Calling `addApplicationListener(...)` and `removeApplicationListener(...)` on every request can negate cache benefits and add contention. For most applications, listeners should be registered at context startup and remain stable.

If business logic truly requires dynamic handlers, consider one stable listener **delegating to an application-owned dynamic handler registry** with proper synchronization/thread-safety and tests, rather than turning Spring's listener list into a per-request mutating structure.

### 15.3. Do not prematurely optimize by rewriting the multicaster

`SimpleApplicationEventMulticaster` already includes matching cache support from `AbstractApplicationEventMulticaster`. Writing a custom multicaster just to “add listener caching” is usually unnecessary and risks breaking type matching, ordering, lifecycle, or transaction semantics.

When profiling proves a bottleneck, revisit event design, listener count, handler bodies, batch processing, or executor usage **before** layering a second cache on top of the internal cache.

### 15.4. Separate the in-process event bus from a broker

The matching cache only helps dispatching **within the same JVM/context**. It does not make events durable, add automatic retries, guarantee exactly-once delivery, track offsets, or coordinate transactions between a database and a broker.

If events must cross process boundaries, use an appropriate broker/outbox/event store and evaluate performance across serialization, network, queues, partitions, consumer handlers, and databases. Never cite listener caching to claim message loss or duplicates are handled.

## 16. Regression testing and diagnosing suspected cache issues

A useful test suite should verify **semantics**, not just internal cache entry counts:

1. Typed listeners receive matching event types and do not receive unrelated types.
2. Publishing the same event type/source type twice still invokes the handler twice.
3. Newly added listeners via `addApplicationListener(...)` receive events published **after** addition.
4. Removed listeners do not receive new events in a synchronous setup without lingering tasks.
5. Listeners with `@EventListener(condition)` still evaluate rules per payload.
6. Listeners filtering with `supportsSourceType(...)` accept matching source classes and reject non-matching ones.
7. With generic events, type matching does not confuse generic payloads across domains.
8. With async, deterministically test in-flight/queued listeners during removal/close without relying on `Thread.sleep(...)`.
9. With prototype beans, verify bean lifecycle matches expectations without relying on internal cache behavior.
10. During context reloads or dynamic plugins, test listener/resource cleanup and verify memory/lifecycle within realistic scope.

**Suggested diagnostic flow:**

~~~text
Event not reaching listener?
  |
  +-- Did the publisher actually publish the right object/type?
  |      |
  |      +-- No -> fix publisher
  |      +-- Yes
  |
  +-- Is the listener registered in the same context?
  |      |
  |      +-- No -> fix bean registration
  |      +-- Yes
  |
  +-- Do event type/source type match the listener?
  |      |
  |      +-- No -> fix declaration / generics / source filter
  |      +-- Yes
  |
  +-- Are @EventListener.condition or transaction phase blocking it?
  |      |
  |      +-- Yes -> test rule, transaction, context
  |      +-- No
  |
  +-- Is the listener running async?
         |
         +-- Yes -> inspect executor, queue, error handler, ordering
         +-- No -> capture stack trace/profile, inspect handler
~~~

Do not reflectively modify `retrieverCache` simply because a listener did not run. If an issue reproduces after adding/removing listeners via the official API, build a **minimal reproducer** for your Spring version and evaluate it with clear tests.

## 17. Self-check exercises

**Question 1.** Does Spring cache candidate lists per event instance or per event/source type?

**Answer:** By type information—in Spring 6.2's implementation, the event's `ResolvableType` and the source's `Class`. Two events with the same type/source class but different payload values typically share a key.

**Question 2.** On a cache hit, is `@EventListener` still called for a new event?

**Answer:** Yes, provided type/source matching and any active condition hold. The cache only reduces candidate lookup steps; it does not skip handling subsequent events.

**Question 3.** Why can `condition="#p0.amount() > 1000"` not be treated as permanently true just because the listener is cached?

**Answer:** Because the condition depends on **each event's** `amount()`. Spring must evaluate it when the event reaches the listener method; type-based selection caching does not include monetary amounts.

**Question 4.** After calling `multicaster.removeApplicationListener(listener)`, is reflection needed to clear `retrieverCache`?

**Answer:** No. The multicaster's removal APIs handle invalidation per implementation; accessing internal fields is discouraged.

**Question 5.** What parameter does `GenericApplicationListener.supportsSourceType(...)` receive, and can it classify by `source.customerId`?

**Answer:** It receives **the source's Class**, not the instance. Therefore, do not use it to compare per-instance `customerId` data; filter inside the handler or event contract instead.

**Question 6.** Two `TicketEvent`s have different source values, both of type `String`. Can they share the same cache key?

**Answer:** Yes, if the event `ResolvableType` is also the same and cache-safety conditions permit. The key inspects the source **class**, not the string content.

**Question 7.** Why can putting a feature flag inside `supportsEventType(...)` lead to unpredictable results after the flag flips?

**Answer:** Because the matching result for that key may already be cached, so the predicate is not necessarily re-invoked for every event. Dynamic business logic belongs in the handler method or an appropriate check layer.

**Question 8.** Why can `TYPE_CHECKS_AFTER_TWO` in the example equal 1 while 2 events were received?

**Answer:** Spring can reuse the matching result on the second publish; both events are still dispatched to the listener, so the business handler runs twice.

**Question 9.** If a removed listener still logs once more in an async app, does that definitively prove a stale cache?

**Answer:** No. The task may have been submitted before removal and was still executing in the executor. Analyze the timestamps of submission, removal, and queueing.

**Question 10.** Does listener caching ensure events are durably persisted and replayed after a JVM restart?

**Answer:** No. It is a listener-selection cache inside the multicaster. Persistence and replay are the responsibility of a separate event store/broker/outbox.

## References

- [Spring Framework 6.2 Javadoc — AbstractApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/AbstractApplicationEventMulticaster.html): registering/removing listeners and `getApplicationListeners(...)` by event type.
- [Spring Framework 6.2 Javadoc — SimpleApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/SimpleApplicationEventMulticaster.html): default synchronous dispatch, executor, and `supportsAsyncExecution`.
- [Spring Framework 6.2 Javadoc — GenericApplicationListener](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/GenericApplicationListener.html): `supportsEventType(ResolvableType)`, `supportsSourceType(...)`.
- [Spring Framework 6.2 Javadoc — ApplicationEventMulticaster](https://docs.spring.io/spring-framework/docs/6.2.9/javadoc-api/org/springframework/context/event/ApplicationEventMulticaster.html): registration/removal and multicasting APIs.
- [Spring Framework source — AbstractApplicationEventMulticaster.java](https://github.com/spring-projects/spring-framework/blob/v6.2.9/spring-context/src/main/java/org/springframework/context/event/AbstractApplicationEventMulticaster.java): implementation details for `ListenerCacheKey`, `CachedListenerRetriever`, invalidation, and classloader cache-safety; when viewing source, select the exact tag matching your running version.
- [Spring Framework Reference — Application Events](https://docs.spring.io/spring-framework/reference/core/beans/context-introduction.html): `@EventListener`, payload-based conditions, generic events, and listener ordering.
