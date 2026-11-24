# Sharing Subscriptions with `share()` and `publish()` in Project Reactor

## 1. The Problem: Should Multiple Subscribers Rerun the Same Source?

In Reactor, a `Flux<T>` is typically a **Publisher**. When a subscriber subscribes, the publisher supplies data under the Reactive Streams contract. With a **cold** source, each subscription usually creates a separate run of the source. That is appropriate when each caller needs an independent result, but wasteful if multiple subscribers want to listen to the same event stream or share an ongoing expensive I/O operation.

Example of a cold source counting three numbers:

~~~java
Flux<Integer> source = Flux.range(1, 3);

source.subscribe(v -> System.out.println("A: " + v));
source.subscribe(v -> System.out.println("B: " + v));
~~~

Each `subscribe()` triggers a separate subscription. The `range` source runs twice: subscriber A receives 1, 2, 3; then subscriber B also receives 1, 2, 3. If the source is an HTTP request, database query, or device connection, each subscriber may cause the source work to be performed again.

When you want **a single upstream subscription to share data with multiple subscribers**, Reactor provides multicast mechanisms such as `share()` and `publish()`. Both share the goal of sharing a running stream, but differ in how the connection starts, how subscribers are tracked, and how lifecycle is managed.

What to clarify before choosing an operator:

- Should the source run once per subscriber or once for the whole listening group?
- When does the source start: immediately when the first subscriber arrives, or after we explicitly connect?
- Do late subscribers need to receive previously emitted elements?
- When all subscribers leave, should the source be cancelled?
- Is the data user/tenant/request-specific, or can it truly be shared safely?

## 2. Cold Publishers and Hot Publishers

A **cold publisher** creates or reads data upon subscription. Each subscriber typically gets an independent run from the start. Common examples:

- `Flux.range(1, 5)`, `Flux.fromIterable(list)`: each subscription traverses the source again.
- `Flux.defer(() -> ...)`: invokes the supplier to create a new publisher per subscription.
- `Mono.fromCallable(...)`: executes the callable per subscription.
- An HTTP/database publisher built so that each subscription initiates a separate request/query.

A **hot publisher** can emit data independently of individual subscribers. A new subscriber joining while the source is running typically sees only elements emitted after its subscription time; past data is not replayed automatically unless the source has a replay/cache mechanism.

Examples of hot sources can come from `Sinks.Many`, an event bus, a sensor device, or an already-connected `ConnectableFlux`.

An easy-to-miss detail: `Flux.just(...)` and `Mono.just(...)` capture values when the publisher is created and then replay those captured values to each subscriber. They do not re-invoke a supplier or re-execute an HTTP request like `defer`. If you want to compute values separately for each subscriber, use `defer`:

~~~java
Mono<String> captured = Mono.just(loadValueNow());

Mono<String> perSubscription = Mono.defer(
    () -> Mono.just(loadValueNow())
);
~~~

This is a structural example; `loadValueNow()` is a hypothetical synchronous method. On the first line, Java calls the method immediately when creating `Mono.just`; on the second, the method is only called on subscribe. **Cold/hot describes how the source attaches to subscribers, not whether the publisher has its own thread.**

## 3. `share()`: Automatically Sharing When the First Subscriber Arrives

`Flux.share()` creates a multicast publisher. When the first subscriber subscribes, the upstream source is subscribed to and begins emitting. Other subscribers joining while the stream is active receive subsequent elements from the same upstream subscription, rather than creating a new subscription.

Key behaviors:

1. **Auto-connects:** no need to call `connect()`; the first subscriber starts the source.
2. **Concurrent sharing:** multiple subscribers concurrently listening to the same `shared` instance receive the same upstream elements during overlapping subscription windows.
3. **No history replay:** later subscribers do not automatically receive elements emitted before they joined.
4. **Cancellation by subscriber count:** when all subscribers have cancelled, `share()` cancels the upstream subscription. This stops the source when no listeners remain.
5. **Source completion:** if upstream completes/errors, current subscribers receive the corresponding terminal signal. `share()` is not a mechanism for storing history so future subscribers can read all past data.

In Reactor, `share()` is equivalent to `publish().refCount()` with a threshold of one subscriber. You can picture it as:

~~~text
Subscriber A ----                  Subscriber B ------> Flux.share() ---- one subscription ----> Source
                  /
Subscriber C ----/

A, B, C join while the source is emitting: they share new elements.
No subscribers: upstream is cancelled.
~~~

**Conceptual example:**

~~~java
Flux<Event> sharedEvents = eventSource().share();

sharedEvents.subscribe(this::sendToDashboard);
sharedEvents.subscribe(this::updateMetrics);
~~~

The snippet above illustrates a service with `eventSource()`; both subscribers must use **the same instance** `sharedEvents`. If each call site invokes `eventSource().share()` again and creates two separate publishers, they do not share a subscription with each other.

`share()` is suitable when multiple consumers listen to an active source, such as a shared event stream, a shareable upstream connection, or a shared sensor stream. Do not use it as a result cache or a queue storing every event for latecomers.

## 4. `publish()`: Controlling Connection via ConnectableFlux

`publish()` returns a **`ConnectableFlux<T>`**, unlike a regular `Flux<T>`. Subscribers can subscribe first, while the upstream source is **not subscribed to yet** until `connect()` is called or an auto-connect policy like `autoConnect(n)` or `refCount(n)` is chosen.

Example:

~~~java
ConnectableFlux<Integer> connectable =
    Flux.range(1, 3).publish();

connectable.subscribe(v -> System.out.println("A: " + v));
connectable.subscribe(v -> System.out.println("B: " + v));

// Source starts here; both subscribers are ready.
connectable.connect();
~~~

This ordering guarantees that both A and B are subscribed before the synchronous source begins emitting. When `connect()` runs, the source is subscribed to once and elements are multicast to participating subscribers.

Connection-management methods:

| Method | When Does Upstream Start? | When Subscribers Leave |
| --- | --- | --- |
| `publish().connect()` | When code calls `connect()` | Connection stays alive until upstream terminates or the connection Disposable is disposed |
| `publish().autoConnect(n)` | When `n` subscribers have arrived | Does not auto-disconnect just because subscriber count drops; connection stays open until the source ends or is managed separately |
| `publish().refCount(n)` | When at least `n` subscribers exist | Tracks subscribers; when count drops below threshold, disconnects upstream |
| `publish().refCount(n, gracePeriod)` | When `n` subscribers have arrived | Waits a grace period before disconnecting after subscribers leave, allowing new subscribers to join |

With `connect()`, you can keep the `Disposable` it returns to disconnect manually:

~~~java
Disposable connection = connectable.connect();

// When the application managing the source wants to stop:
connection.dispose();
~~~

This is an API illustration snippet. Disposing the connection stops the shared source and affects **all subscribers** listening to it; only the owner managing the source's lifecycle should perform that action.

### When to Use publish?

- Need to wait for a group of subscribers to finish subscribing before starting the source.
- Want precise control over when the source starts.
- Want to set a subscriber threshold with `autoConnect(n)` or `refCount(n)`.
- Need to decouple downstream registration from upstream subscription timing.

`publish()` does not store history. Subscribers arriving after the source has started only receive data from the time they join, not previously emitted values.

## 5. Comparing `share()`, `publish()`, `autoConnect()`, and `refCount()`

| Criterion | `share()` | `publish()` | `publish().autoConnect(n)` | `publish().refCount(n)` |
| --- | --- | --- | --- | --- |
| Result | Multicast `Flux<T>` | `ConnectableFlux<T>` | Auto-connecting `Flux<T>` | Subscriber-count-managed `Flux<T>` |
| Starts source | First subscriber | Calling `connect()` | `n` subscribers reached | `n` subscribers reached |
| Timing control | Automatic | Explicit | Automatic by threshold | Automatic by threshold |
| Tracks subscriber count to cancel source | Yes, cancels when all subscribers leave | Not automatically like refCount | Does not auto-disconnect just because subscribers drop | Yes, disconnects when count drops below threshold |
| Replays past elements | No | No | No | No |
| Typical use | Share source while listeners exist | Need explicit decision on when to connect | Source must start once enough listeners arrive and keep running | Source only needs to run while enough listeners exist |

A mnemonic:

- **`share()`**: “Start when someone listens; cancel when nobody is left.”
- **`publish()`**: “Gather listeners first, then I'll call connect myself.”
- **`autoConnect(n)`**: “Auto-connect once enough listeners arrive and keep the connection.”
- **`refCount(n)`**: “Connect once enough listeners arrive; disconnect below threshold.”

`share()` is usually suitable for a minimum of one subscriber. If you need to wait for two or more subscribers to be ready together, use `publish().refCount(n)` or `publish().autoConnect(n)` depending on the post-connection policy.

## 6. How Does `publish` Coordinate Backpressure?

When multicasting, multiple subscribers can consume at different speeds. `publish()` coordinates the demand (`request(n)`) of subscribers and forwards that demand upstream. According to Reactor documentation, if one subscriber currently has demand of 0, `publish` can pause requesting more data from the source to respect that subscriber.

Consequence: **a slow subscriber can slow down the shared source and affect other subscribers**. This is the trade-off of sharing one stream with coordinated backpressure. If a subscriber never requests more data, the multicast may stop pulling from the source for the entire group.

Things to consider:

- Do subscribers have similar processing capacity?
- Can older events be dropped?
- Does each receiver need its own queue/buffer?
- Does the source support pause/resume or replay?
- When a subscriber is slow, should we slow the entire source, drop elements, or disconnect that subscriber?

Do not solve every case by growing buffers without bound. Large buffers only delay out-of-memory errors and can increase latency. If each subscriber needs an independent backpressure policy, you may need a fan-out/per-subscriber-queue architecture instead of a simple coordinated-backpressure multicast.

## 7. Late Subscribers: share/publish Are Not replay

This is the most important distinction when choosing an operator:

~~~text
Source emits:     A ---- B ---- C ---- D ---- E ---- complete
Subscriber 1:     ^ receives A, B, C, D, E
Subscriber 2:                 ^ receives D, E if joining after C

share/publish: do not replay A, B, C to Subscriber 2.
replay/cache: can replay stored history according to configured limits.
~~~

If late subscribers need past data, consider:

- `replay()`: returns a `ConnectableFlux` capable of storing and replaying history; can limit element count or retention time.
- `replay(n)`: retains at most the `n` most recent elements for replay.
- `replay(Duration)`: retains elements for a TTL duration.
- `cache()` or variants `cache(history, ttl)`: automatically caches signals so later subscribers can receive them; choose limits to avoid unbounded retention.

Example:

~~~java
Flux<Event> recent = eventSource().replay(100).autoConnect(1);
~~~

The source starts when the first subscriber arrives; later subscribers can receive up to the 100 most recent elements per the replay policy. This is a **structural example**; if you need manual connect control, keep the `ConnectableFlux` type and call `connect()`.

Do not use `share()` when the requirement is “every new client must read all events from the beginning”. It is not a message broker with a durable log. For data that must not be lost while clients are offline, you need persistence, an event log, offsets, or a broker with per-consumer replay.

## 8. Runnable Java 17+ Example: cold, share, and publish

The following example uses **Reactor Core 3.8.6** directly, without Spring Boot. It demonstrates:

1. A cold source re-running for each subscriber.
2. `share()` using a single upstream subscription for two subscribers registering close together.
3. `publish()` allowing two subscribers to register first before calling `connect()`.

Structure:

~~~text
reactor-share-publish/
├── pom.xml
└── src/main/java/SharingDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/xsd/maven-4.0.0.xsd https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>reactor-share-publish</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.6</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.2</version>
            </plugin>
        </plugins>
    </build>
</project>
~~~

File `src/main/java/SharingDemo.java`:

~~~java
import java.time.Duration;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;

public class SharingDemo {
    public static void main(String[] args) throws InterruptedException {
        // 1. Cold source: each subscription runs the supplier once.
        AtomicInteger coldRuns = new AtomicInteger();

        Flux<Integer> cold = Flux.defer(() -> {
            int run = coldRuns.incrementAndGet();
            System.out.println("cold source run " + run);
            return Flux.just(1, 2);
        });

        cold.subscribe(value -> System.out.println("A: " + value));
        cold.subscribe(value -> System.out.println("B: " + value));

        // 2. share(): both subscribers join before the first tick.
        AtomicInteger sharedStarts = new AtomicInteger();

        Flux<Long> shared = Flux.interval(Duration.ofMillis(500))
            .take(3)
            .doOnSubscribe(s -> sharedStarts.incrementAndGet())
            .share();

        List<Long> first = new CopyOnWriteArrayList<>();
        List<Long> second = new CopyOnWriteArrayList<>();
        CountDownLatch finished = new CountDownLatch(2);
        AtomicReference<Throwable> failure = new AtomicReference<>();

        shared.subscribe(
            first::add,
            error -> {
                failure.compareAndSet(null, error);
                finished.countDown();
            },
            finished::countDown
        );

        shared.subscribe(
            second::add,
            error -> {
                failure.compareAndSet(null, error);
                finished.countDown();
            },
            finished::countDown
        );

        if (!finished.await(5, TimeUnit.SECONDS)) {
            throw new IllegalStateException("Timed out waiting for share()");
        }
        if (failure.get() != null) {
            throw new IllegalStateException("share() failed", failure.get());
        }

        System.out.println("share upstream subscriptions = " + sharedStarts.get());
        System.out.println("share subscriber A = " + first);
        System.out.println("share subscriber B = " + second);

        // 3. publish(): register both subscribers before calling connect.
        AtomicInteger publishStarts = new AtomicInteger();

        ConnectableFlux<Integer> connectable = Flux.range(1, 3)
            .doOnSubscribe(s -> publishStarts.incrementAndGet())
            .publish();

        List<Integer> publishA = new java.util.ArrayList<>();
        List<Integer> publishB = new java.util.ArrayList<>();

        connectable.subscribe(publishA::add);
        connectable.subscribe(publishB::add);

        System.out.println("publish before connect = " + publishStarts.get());
        connectable.connect();

        System.out.println("publish upstream subscriptions = " + publishStarts.get());
        System.out.println("publish subscriber A = " + publishA);
        System.out.println("publish subscriber B = " + publishB);
    }
}
~~~

Run from the `reactor-share-publish` directory with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=SharingDemo
~~~

**Output printed by the program** (excluding Maven messages if the environment displays any):

~~~text
cold source run 1
A: 1
A: 2
cold source run 2
B: 1
B: 2
share upstream subscriptions = 1
share subscriber A = [0, 1, 2]
share subscriber B = [0, 1, 2]
publish before connect = 0
publish upstream subscriptions = 1
publish subscriber A = [1, 2, 3]
publish subscriber B = [1, 2, 3]
~~~

Analysis:

- With the cold source, `Flux.defer` is invoked twice: once for A and once for B. The counter proves there are two upstream subscriptions.
- With `share()`, the `interval` source has its first emission after 500 ms. Both subscribers are registered back-to-back before the first tick, so both receive 0, 1, 2. `doOnSubscribe` sits **before share**, so it counts upstream subscriptions and the result is 1.
- With `publish()`, two subscribers register, yet the source has not started; the counter before `connect()` is 0. After connecting, the source runs exactly once and multicasts three elements to both A and B.
- The example uses `CountDownLatch` to wait for both subscribers to complete in a console program. This waiting is for demo purposes; do not use `block()` or `Thread.sleep()` on the event-loop of a WebFlux application.

To test the late-subscriber case, you can subscribe the second subscriber **after** the source has already emitted a few elements; that subscriber will only receive new elements from the moment it joins. If you need previous data as well, switch to `replay(...)` or a bounded cache.

## 9. Choosing share/publish in a Spring WebFlux Application

Suppose multiple SSE clients want to listen to a shared event stream. A service can hold **a single publisher instance**:

~~~java
// Structural pattern in Spring Boot WebFlux.
// Event, eventSdk, and dependencies must be defined in the application.
@Service
class EventService {
    private final Flux<Event> sharedEvents;

    EventService(EventSdk eventSdk) {
        this.sharedEvents = eventSdk.events().share();
    }

    Flux<Event> events() {
        return sharedEvents;
    }
}
~~~

Controller returns the publisher to WebFlux:

~~~java
@RestController
class EventController {
    private final EventService eventService;

    EventController(EventService eventService) {
        this.eventService = eventService;
    }

    @GetMapping(value = "/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    Flux<Event> events() {
        return eventService.events();
    }
}
~~~

These two snippets are **SDK- and domain-dependent integration patterns**, not standalone Java programs. Key points:

- The service holds **the same instance** `sharedEvents`, so multiple requests can join the same stream if their subscription lifetimes overlap.
- The first subscriber starts the source; later subscribers receive only new events.
- When all clients disconnect and the server cancels all subscriptions, `share()` cancels the upstream source. The SDK must handle cancellation/cleanup properly.
- The controller **returns the Flux** to the framework; do not call `subscribe()` manually to create a stream detached from the HTTP lifecycle.

### Security and Sharing Scope Notes

Do not share a publisher containing user-, tenant-, token-, or permission-specific data if multiple requests might receive each other's data. Putting `share()` in a singleton service makes the source shared at the service scope; every subscriber in that group can see the same events. If data must be filtered per user, partition the source and check authorization before multicasting, or keep separate publishers per scope.

Nor should `share()` be used to guarantee that a side effect continues even after clients leave. When the last subscriber cancels, upstream may be cancelled. If business logic needs background processing independent of HTTP, manage it with a separate service/queue/job lifecycle rather than depending on whether clients are still listening.

If you want to wait until enough clients have subscribed before starting emission, you can use:

~~~java
Flux<Event> group = eventSdk.events()
    .publish()
    .refCount(2);
~~~

The source only connects when two subscribers are present. When the subscriber count drops below the threshold, upstream may be disconnected. For brief disconnects while a client reconnects, consider the `refCount(2, Duration.ofSeconds(2))` overload to give a new subscriber time to return before disconnecting.

## 10. Common Pitfalls

1. **Assuming `share()` retains history:** wrong; late subscribers do not receive already-emitted elements. Use `replay` or a bounded cache if history is needed.
2. **Creating a new `source.share()` on every service call:** each instance has its own subscriber group and does not share across instances. Keep a single shared instance in the appropriate scope.
3. **Subscribing a second subscriber after a synchronous source has finished running:** the second subscriber may trigger a new subscription per source/ref-count semantics instead of sharing the prior run. Use an async source with join window, or `publish()` and subscribe enough subscribers before `connect()`.
4. **Forgetting to call `connect()` on `ConnectableFlux`:** subscribers wait while upstream never starts. Call `connect()` or use `autoConnect`/`refCount`.
5. **Calling `connect()` too early:** the source may emit before intended subscribers are registered; later subscribers miss initial elements. Subscribe first, connect second.
6. **Using `autoConnect` while expecting auto-disconnect when everyone leaves:** `autoConnect` does not track drops in subscriber count to disconnect like `refCount`. Use `refCount` or hold the connection Disposable manually.
7. **Using `refCount(n)` without understanding the threshold:** if fewer than `n` subscribers are present, the source has not started; when dropping below the threshold, the source may disconnect and restart on the next connection.
8. **One slow subscriber slowing down the entire group:** `publish` coordinates shared demand and may pause upstream if one subscriber has 0 demand. Consider buffering, separate queues, or an explicit drop policy.
9. **Using share for side effects that must finish independently:** the last subscriber cancelling can cancel upstream. Use a background-managed job/queue/service.
10. **Sharing multi-tenant data:** a shared publisher can broadcast the same events to every subscriber. Ensure partitioning and authorization checks before multicasting.
11. **Thinking hot means automatic replay:** hot sources typically emit only new data to late subscribers unless replay is configured.
12. **Not handling source errors/cancellations:** an upstream error terminates the shared stream for all active subscribers; the final cancellation may stop the source. Lifecycle-aligned cleanup, retry/fallback, and observability are required.
13. **Calling `subscribe()` inside a controller:** creates a separate subscription unmanaged by WebFlux, making cancellation and error mapping hard to control. Return the publisher to the framework.

## 11. Quick Decision Table

| Requirement | Choice |
| --- | --- |
| Each subscriber must run the source independently | Keep the publisher cold; do not share |
| Multiple concurrent subscribers listening to the same source; auto-start when the first arrives | `share()` |
| Register all subscribers first before starting the source | `publish()` + `connect()` |
| Auto-connect once a number of subscribers arrive, then keep connected | `publish().autoConnect(n)` |
| Connect when enough subscribers arrive and disconnect when count drops below threshold | `publish().refCount(n)` |
| Allow reconnect within a grace period | `publish().refCount(n, duration)` |
| Late subscribers need to receive a number of most recent events | `replay(n)` or `replay(Duration)` |
| Want to cache results for reuse by later subscriptions | `cache(...) ` with appropriate history/TTL bounds |
| Work must continue even when no subscribers remain | Separate lifecycle into a background job/service, not dependent on share/refCount |

## 12. Self-Check

**1.** How many times does a cold `Flux.range(1, 3)` run when subscribed to twice? **Two**, once per subscription.

**2.** How many upstream subscriptions exist when two subscribers subscribe to the same `source.share()` instance while the source is emitting? **One** within the sharing subscriber group.

**3.** Does a late subscriber to `share()` receive previously emitted A and B? **No**; it only receives elements from the time it joins.

**4.** What type does `publish()` return? **`ConnectableFlux<T>`**, requiring `connect()` or an auto-connect policy.

**5.** How do you register two subscribers before the source runs? Create a `ConnectableFlux`, subscribe both, then call `connect()`; or use `autoConnect(2)` if you want threshold-based auto-connect.

**6.** Does `autoConnect(2)` auto-disconnect when the last subscriber leaves? **No**, it does not track subscriber drops to disconnect like `refCount`.

**7.** What does `share()` do when all subscribers cancel? **Cancels upstream** while the source is active.

**8.** What should you choose if new subscribers must receive the 100 most recent events? **`replay(100)`** or an appropriately bounded cache, not share.

**9.** Can one `sharedFlux` containing per-user private data be used for all requests? **No**, unless partitioned/authorized to guarantee each subscriber only sees permitted data.

**10.** Why can `publish` be affected by a slow subscriber? Because it coordinates shared demand; if one subscriber has demand of 0, upstream may pause emitting.

**Key takeaway:** `share()` is an automatic multicast suited for subscribers listening together to an active source; it starts when the first subscriber arrives and cancels upstream when all subscribers leave. `publish()` returns a `ConnectableFlux` for explicit `connect()`, or threshold-based `autoConnect`/`refCount`. Neither replays history. If late subscribers need past data, use `replay`/bounded cache; if work must outlive clients, manage its lifecycle at a separate service/queue layer.

**Official documentation:** [Project Reactor 3.8 — Hot Versus Cold](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html), [Broadcasting to Multiple Subscribers with ConnectableFlux](https://projectreactor.io/docs/core/release/reference/advancedFeatures/advanced-broadcast-multiple-subscribers-connectableflux.html), [Flux API — share/publish](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).