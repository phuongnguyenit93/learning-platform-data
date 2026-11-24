# ConnectableFlux, connect, autoConnect, and refCount

**Context:** Spring Framework Reactive → **Hot and cold sources**.

By default, many publishers in Reactor are **cold**: each subscriber creates a separate subscription, and the source may perform the work from the beginning for that subscriber. This is appropriate when each caller needs an independent result. However, with an expensive source or a continuously updating feed, we may want **multiple subscribers to observe a single upstream run**.

Project Reactor provides `ConnectableFlux<T>` to separate two actions:

1. **Subscribe:** subscribers register on the shared stream and wait for data.
2. **Connect:** explicitly allows the upstream source to begin emitting data.

From this come three common ways to manage connection timing:

- `connect()` — the application decides exactly when to start and can keep the `Disposable` to disconnect.
- `autoConnect(n)` — auto-connects once `n` subscribers arrive; after connecting, does not auto-disconnect just because subscribers leave.
- `refCount(n)` — auto-connects once `n` subscribers arrive and disconnects upstream when subscriber count drops below the threshold.

These operators help share **a single source subscription** across multiple consumers. They do not generate data themselves, do not durably persist events, do not guarantee replay for late subscribers, and do not create new threads.

## 1. Why Share a Subscription?

Suppose there is a cold publisher:

```java
Flux<Long> ticks = Flux.interval(Duration.ofSeconds(1));

ticks.subscribe(value -> System.out.println("A=" + value));
ticks.subscribe(value -> System.out.println("B=" + value));
```

This is a snippet in a project with Reactor and `Duration` imported. Each `subscribe()` call creates a separate subscription. Because `Flux.interval` is a cold source, each subscriber gets its own tick schedule, usually starting from 0 after subscribing.

Conceptual result:

```text
Cold source
   ├── subscription A → 0, 1, 2, 3, ...
   └── subscription B → 0, 1, 2, 3, ...

Two subscriptions may perform twice the upstream work.
```

This is not always bad. If each subscriber needs independent data, this is the right behavior. Now consider these cases:

- Multiple clients watching a single market feed; each client should not open another external source connection.
- Multiple components in an application needing a single status poll.
- A resource-heavy event stream consumed by dashboards, metrics, and notifications.
- Multiple requests needing to observe one running data-emission process together.

If you want subscribers to receive events from **a single source execution**, consider `publish()` or `replay()` to create a `ConnectableFlux`.

## 2. What Is ConnectableFlux?

`ConnectableFlux<T>` is a form of `Flux<T>` whose **upstream connection control is decoupled from subscriber registration**.

Create it with `publish()`:

```java
ConnectableFlux<Integer> shared = Flux.range(1, 3)
        .publish();
```

Or use `replay()` when data needs to be retained for late subscribers:

```java
ConnectableFlux<Integer> replayed = Flux.range(1, 3)
        .replay(1);
```

The snippets above require importing `Flux` and `ConnectableFlux`.

With `publish()`:

- Subscribers can subscribe before the source starts.
- Upstream is activated only when a connect command occurs.
- One upstream connection emits data to currently participating subscribers.
- Late subscribers **do not automatically receive previously emitted items**.
- When the source completes/errors or the connection is disposed, the current connection lifecycle ends.

With `replay(1)`, the operator retains at most the one most recent item for late subscribers within the replay lifecycle. Unbounded `replay()` history can retain a large amount of data; choose a count or time limit when using it with long-lived sources.

**ConnectableFlux is not synonymous with Sinks.** `ConnectableFlux` shares subscriptions to an existing publisher; `Sinks.Many` lets the application actively emit events into a hot publisher. The two tools solve related problems but differ in producer ownership and how data enters the stream.

## 3. connect(): Deciding When to Start Yourself

`connect()` is the manual control approach. Workflow:

1. Create a `ConnectableFlux` from the source.
2. Subscribe all required subscribers.
3. Call `connect()` to start upstream.
4. Keep the returned `Disposable` if you need to explicitly disconnect.

Example:

```java
ConnectableFlux<Integer> shared = Flux.range(1, 3)
        .doOnSubscribe(s -> System.out.println("upstream subscribed"))
        .publish();

shared.subscribe(value -> System.out.println("A=" + value));
shared.subscribe(value -> System.out.println("B=" + value));

Disposable connection = shared.connect();
```

This snippet requires importing `ConnectableFlux`, `Flux`, and `Disposable`.

**Why register subscribers before calling connect?** With a finite synchronous source like `Flux.range`, `connect()` can cause all items to be emitted during that call. If you connect first and subscribe afterward, late subscribers can miss all emitted data. `publish()` has no history to replay.

### 3.1. Connection Disposable vs. Subscriber Disposable

There are two kinds of handles to distinguish:

| Handle | Represents | Used To |
|---|---|---|
| `Disposable` returned from `subscriber.subscribe(...)` | A specific subscriber | Cancel that subscriber's demand |
| `Disposable` returned from `connectable.connect()` | The shared upstream connection | Disconnect the shared source, affecting every subscriber using the connection |

Example:

```java
Disposable subscriberA = shared.subscribe(value -> useA(value));
Disposable subscriberB = shared.subscribe(value -> useB(value));

Disposable connection = shared.connect();

// When the application explicitly stops the shared source:
connection.dispose();
```

This snippet requires declaring `shared` and the handler methods. If you only want one consumer to leave, dispose that consumer's subscription. If you dispose the connection, you are disconnecting **the shared source**, not just one subscriber.

### 3.2. connect(Consumer<Disposable>) to Take Ownership of the Connection

You can receive the connection handle via a callback:

```java
shared.connect(disposable -> {
    connectionRegistry.add(disposable);
});
```

This snippet uses a hypothetical `connectionRegistry` where the application manages connections. The callback is invoked when the connection is established and supplies a `Disposable` for disconnecting later. Manage the registry and cleanup according to the real lifecycle; do not hold handles indefinitely after the source has completed.

**Do not call connect arbitrarily from multiple places.** There should be one component responsible for creating the source, registering consumers, connecting, and stopping the source. If multiple components control the connection, disposing from one place can disrupt everywhere else.

## 4. autoConnect(n): Connecting When Enough Subscribers Arrive

`autoConnect(n)` turns a `ConnectableFlux` into a `Flux` that automatically connects once at least `n` subscribers have subscribed.

```java
Flux<Integer> shared = Flux.range(1, 3)
        .doOnSubscribe(s -> System.out.println("upstream subscribed"))
        .publish()
        .autoConnect(2);
```

This is a snippet. Behavior:

- First subscriber subscribes: upstream has **not** started yet.
- Second subscriber subscribes: threshold 2 is reached, upstream connects.
- Both current subscribers receive the items together.
- After the connection is triggered, subscribers leaving **does not make autoConnect automatically disconnect upstream**.
- If the source completes/errors on its own, the connection ends with the terminal signal.

### 4.1. Threshold 1 and Threshold 0

```java
Flux<Event> startWithFirst =
        eventSource.publish().autoConnect(1);

Flux<Event> startImmediately =
        eventSource.publish().autoConnect(0);
```

- `autoConnect(1)`: connects when the first subscriber appears.
- `autoConnect(0)`: connects immediately without needing any subscriber.

Threshold 0 is useful when intentionally starting a shared source as soon as the publisher is activated, though it can create work **with no consumers**. Use it only when a component owns the source and has a clear stop policy.

### 4.2. autoConnect Is Not refCount

Suppose the source is an infinite `Flux.interval` and the threshold is 1:

- One client connects → upstream starts.
- That client closes its connection → subscriber leaves.
- `autoConnect` **does not automatically dispose the connection** just because no subscribers remain.
- The source can keep ticking and consuming resources without consumers.

To obtain the connection handle, you can use the `autoConnect(n, consumer)` overload. If the requirement is “run while subscribers exist, stop when none remain”, `refCount` is usually better suited.

## 5. refCount(n): Auto-Connecting and Auto-Disconnecting by Subscriber Count

`refCount(n)` tracks the number of active subscribers on a `ConnectableFlux`:

1. When the subscriber count reaches at least `n`, connect upstream.
2. When the subscriber count drops below `n`, the upstream connection is cancelled/disconnected.
3. When enough subscribers return again, the operator can establish a new connection with an appropriate source.

Example:

```java
Flux<Long> sharedTicks = Flux.interval(Duration.ofSeconds(1))
        .publish()
        .refCount(1);
```

This snippet requires importing `Duration`. Meaning:

- When nobody is subscribed, the timer does not need to run.
- First subscriber arrives, the timer starts.
- Multiple concurrent subscribers share the same timer.
- Last subscriber leaves, upstream is cancelled.
- A new subscriber arriving later can trigger a new source subscription; with `Flux.interval`, the new tick sequence restarts from the beginning.

`refCount(1)` suits shared sources that only need to operate while at least one consumer exists. With a higher threshold:

```java
Flux<Event> sharedForPair =
        eventSource.publish().refCount(2);
```

The source only connects when two subscribers exist; if the count drops to one, the shared connection is disconnected. Therefore, the remaining subscriber **must not be assumed** to keep receiving data like an independent source.

### 5.1. refCount with a Grace Period Before Disconnecting

In systems where clients frequently reconnect, constant connecting/disconnecting can cause churn. You can use a grace period:

```java
Flux<Event> shared = eventSource
        .publish()
        .refCount(1, Duration.ofSeconds(5));
```

When the last subscriber leaves, the operator waits for the configured duration before disconnecting. If a new subscriber returns within the grace period, the connection can continue to be reused. This reduces repeated reconnections; it also means the source may keep running **for a short period with no subscribers**.

Choose the wait duration based on connection setup cost, acceptable latency, and resource budget. A grace period is not a durable storage mechanism or a guarantee that new clients receive data emitted during their absence.

## 6. Comparing connect, autoConnect, and refCount

| Mechanism | Who Decides to Start? | Upstream Disconnect Condition | Level of Control |
|---|---|---|---|
| `connect()` | Manual code call | Source terminates or owner disposes connection | High; suits component-managed lifecycle |
| `autoConnect(n)` | Automatically when `n` subscribers arrive | Source terminates or owner disposes via retained handle | Easy to use; does not auto-disconnect by subscriber count |
| `refCount(n)` | Automatically when `n` subscribers arrive | Subscriber count drops below threshold, or source terminates | Self-managed by consumer presence |
| `refCount(n, gracePeriod)` | Automatically when threshold is reached | After grace period if still short of subscribers | Reduces churn but can keep source running with no listeners |

Quick selection:

- Need to wait for all subscribers to subscribe before emitting: `connect()`.
- Need to start after enough consumers arrive and live for the application lifecycle: `autoConnect(n)`.
- Need to run only while consumers exist and stop when not enough consumers remain: `refCount(n)`.
- Need to keep the connection briefly while clients reconnect: `refCount(n, gracePeriod)`.

**None of these options automatically solves replay, data durability, overflow, or slow-subscriber policies.** Those concerns must be designed separately.

## 7. publish() and replay(): What Do Late Subscribers Receive?

This is the most important difference when choosing a `ConnectableFlux` variant.

### 7.1. publish(): Distributes Events Only While Subscribers Are Participating

```java
ConnectableFlux<Integer> shared = Flux.range(1, 3).publish();

shared.subscribe(value -> System.out.println("A=" + value));
shared.connect();

// Subscriber B arrives after the source has finished emitting:
shared.subscribe(value -> System.out.println("B=" + value));
```

With the synchronous `range` source, A receives 1, 2, 3; B arrives after the terminal signal and does not receive old items. `publish` shares **live emitting events**, without storing history.

With an infinite source, B can receive items emitted after B subscribes, but not items that already passed earlier.

### 7.2. replay(): Replays Stored History

```java
ConnectableFlux<Integer> latest = Flux.range(1, 5).replay(1);

latest.subscribe(value -> System.out.println("early=" + value));
latest.connect();

latest.subscribe(value -> System.out.println("late=" + value));
```

With a finite synchronous source, the early subscriber receives 1..5; a later subscriber can receive the most recent replayed item (5), followed by the terminal signal. `replay(1)` retains at most one historical item.

Some options:

| Creation Method | Retained History |
|---|---|
| `publish()` | Does not replay already-emitted items |
| `replay(1)` | At most the most recent item |
| `replay(100)` | At most the 100 most recent items |
| `replay(Duration.ofMinutes(1))` | Items still within the time window |
| `replay()` | Can retain the entire history of the source |

Unbounded `replay()` on a long-lived source can cause memory to grow continuously. Choose limits by item count/time and payload size; if long-term history is required, use a proper store or message broker.

**In-memory replay is not an event store.** It does not guarantee data survives restarts, does not replace durable offsets/sequences, and does not automatically handle browser reconnection.

## 8. Comparing publish, replay, cache, and Sinks

The following tools are often lumped together as “hot”, yet their behaviors differ:

| Mechanism | Is Source Shared? | Has Replay? | Lifecycle Management |
|---|---|---|---|
| `publish().connect()` | Yes, after connect | No | Explicitly retain connection `Disposable` |
| `publish().autoConnect(n)` | Yes, after threshold | No | Auto-connects, does not auto-disconnect by subscriber count |
| `publish().refCount(n)` | Yes, when threshold is met | No | Connects/disconnects by subscriber count |
| `replay(k)` | Yes | Yes, bounded to k items | Manual connect or combined with autoConnect/refCount |
| `cache()` | Yes, publisher starts on first subscriber | Caches items and terminal signal per configuration | No connect/disconnect control like ConnectableFlux |
| `Sinks.Many` | Application-emitted hot source | Depends on sink type (multicast/replay) | Application manages the sink and producers |

### 8.1. cache() Is Not refCount()

`cache()` is useful when you want a single computation whose result is retained for later subscribers to receive. However, cache retains items/terminal signals and does not auto-disconnect upstream merely because no subscribers remain as in `refCount`.

```java
Mono<Product> cached = productService.loadProduct(id)
        .cache();
```

This is a snippet. `cache()` fits when sharing and retaining results; consider TTL, key cardinality, data size, and invalidation timing. Do not use unbounded cache for an infinite event stream.

### 8.2. Sinks.Many Is an Active Producer

```java
Sinks.Many<Event> sink =
        Sinks.many().multicast().onBackpressureBuffer();

Flux<Event> events = sink.asFlux();

// Elsewhere in the application:
Sinks.EmitResult result = sink.tryEmitNext(event);
```

This is a snippet; `Event` and `event` must be declared. A sink lets the application actively emit data, whereas `ConnectableFlux` shares subscriptions to an existing publisher. Sinks have their own multicast/replay/overflow policies; `EmitResult`, concurrency, and cleanup must be handled properly.

## 9. One Source, Multiple Subscribers: Side Effects Before or After publish?

Operator placement affects how many times side effects run.

### 9.1. Side Effect Before publish: Belongs to the Shared Source

```java
Flux<Event> shared = source
        .doOnNext(event -> metrics.recordSourceEvent())
        .publish()
        .refCount(1);
```

When upstream emits an event on one connection, `recordSourceEvent()` runs once on the shared source branch before distribution to subscribers.

### 9.2. Side Effect After publish: Each Subscriber Can Run Separately

```java
Flux<Event> shared = source
        .publish()
        .refCount(1)
        .doOnNext(event -> metrics.recordClientDelivery());
```

The hook sits after the shared part; each subscriber receiving an item can execute that branch's callback. With three subscribers, one upstream event can lead to three downstream callback invocations.

This also matters for `doOnError`, metrics, and tracing:

- A hook before `publish` observes errors from the shared source once per connection.
- A hook after `publish` can be invoked for each subscriber receiving the error.
- Do not place non-idempotent business side effects after publish unless you want them to run once per consumer.

## 10. Backpressure and Slow Subscribers in Shared Streams

Sharing a source means multiple subscribers jointly influence how the source is consumed. With `publish()`, Reactor coordinates subscriber demand; a subscriber with zero demand can cause upstream to pause emitting to avoid sending data beyond that branch's demand.

This creates a trade-off:

- All subscribers observe one consistent shared stream in emission order.
- One slow subscriber can slow down the entire shared source.
- If a branch needs a different policy (drop/latest/buffer), it must be designed explicitly at the right position.

Example of a dashboard needing only the latest state:

```java
Flux<Metric> sharedLatest = metricsSource
        .onBackpressureLatest()
        .publish()
        .refCount(1);
```

This is a snippet. The latest policy is applied before publish, so data is retained/dropped at the shared source layer. Subscribers receive the same throttled stream.

If per-client policies are needed, operators can be placed on branches after sharing:

```java
Flux<Metric> shared = metricsSource
        .publish()
        .refCount(1);

Flux<Metric> clientView = shared.onBackpressureLatest();
```

This snippet illustrates a consumer branch. Evaluate actual demand and buffering: an operator after publish can change the requests that branch sends to the shared part. If buffering per client, item/byte bounds and an overflow policy are mandatory; unbounded buffers can exhaust memory.

**Do not use latest/drop for mandatory complete events** such as payments, orders, or audits. Subscription sharing does not replace durable queues, acknowledgments, or event logs.

## 11. Lifecycle: subscribe, connect, complete, error, and cancel

A shared source has multiple lifecycles to distinguish:

1. **Subscriber lifecycle:** a consumer subscribes, receives items, and can complete/error/cancel independently.
2. **Connection lifecycle:** the upstream source is connected, emits items, and eventually completes/errors or is disposed/cancelled.
3. **Application lifecycle:** beans/services are initialized, started, and stopped with the application.

### 11.1. Source Completion

When upstream completes, active subscribers receive `onComplete`. No new data arrives from that connection. Behavior for later subscribers depends on the operator (e.g., publish does not replay, while replay/cache can retain history/terminal signals per configuration).

### 11.2. Source Errors

An upstream error is distributed to active subscribers on the connection. `doOnError` placed before publish observes source errors; placed after publish it can observe errors on each consumer branch. `ConnectableFlux` does not automatically retry or recover from errors.

If you want to retry the shared source, place retry **before sharing** when the goal is one shared retry policy:

```java
Flux<Event> shared = eventSource
        .retryWhen(Retry.backoff(3, Duration.ofSeconds(1)))
        .publish()
        .refCount(1);
```

This snippet requires `Retry` and `Duration`. Upstream retry sits before publish, so subscribers observe a single connection/restart of the source together. Retries still require filtering transient errors, max attempts, jitter, timeouts, and idempotency for side effects.

### 11.3. A Subscriber Cancels

With `refCount(1)`, if other subscribers remain, upstream continues. When the last subscriber leaves, the connection is cancelled. With `refCount(2)`, subscriber count dropping from two to one is below the threshold, so the connection is disconnected.

With `autoConnect(n)`, subscriber cancellation **does not automatically decrement the count to disconnect the source** once the connection has been activated. With manual `connect()`, only the owner disposing the connection or the source itself terminating ends the shared connection.

### 11.4. Cancellation Does Not Roll Back Side Effects

If the source already sent a request to a payment service or wrote to a DB, cancelling the subscription does not guarantee external side effects are rolled back. Use idempotency keys, appropriate transactions, outbox patterns, job statuses, and reconciliation mechanisms according to business requirements.

## 12. Standalone Java 17+ Program: Observing Three Connection Approaches

The following example uses Reactor Core and Maven, without Spring Boot, network, or database. It illustrates:

1. `connect()` waiting for subscribers to register before starting.
2. `autoConnect(2)` connecting when the second subscriber appears.
3. `refCount(2)` connecting at threshold two and disconnecting upstream when subscriber count drops below the threshold.

Directory structure:

```text
connectable-flux-demo/
├── pom.xml
└── src/main/java/demo/ConnectableFluxDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>connectable-flux-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.8.8</version>
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
                <version>3.4.1</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/ConnectableFluxDemo.java`:

```java
package demo;

import reactor.core.Disposable;
import reactor.core.publisher.ConnectableFlux;
import reactor.core.publisher.Flux;

public class ConnectableFluxDemo {

    public static void main(String[] args) {
        manualConnect();
        autoConnect();
        refCount();
    }

    private static void manualConnect() {
        System.out.println("1) manual connect");

        ConnectableFlux<Integer> shared = Flux.concat(
                        Flux.range(1, 3),
                        Flux.<Integer>never())
                .doOnSubscribe(s ->
                        System.out.println("manual:source subscribed"))
                .doOnCancel(() ->
                        System.out.println("manual:source cancelled"))
                .publish();

        shared.subscribe(value ->
                System.out.println("manual A=" + value));
        shared.subscribe(value ->
                System.out.println("manual B=" + value));

        System.out.println("manual:calling connect");
        Disposable connection = shared.connect();

        System.out.println("manual:disposing connection");
        connection.dispose();
    }

    private static void autoConnect() {
        System.out.println("2) autoConnect(2)");

        Flux<Integer> shared = Flux.range(10, 2)
                .doOnSubscribe(s ->
                        System.out.println("auto:source subscribed"))
                .publish()
                .autoConnect(2);

        shared.subscribe(
                value -> System.out.println("auto A=" + value),
                error -> System.out.println("auto A error"),
                () -> System.out.println("auto A complete"));

        System.out.println("auto:first subscriber attached");

        shared.subscribe(
                value -> System.out.println("auto B=" + value),
                error -> System.out.println("auto B error"),
                () -> System.out.println("auto B complete"));

        System.out.println("auto:second subscriber attached");
    }

    private static void refCount() {
        System.out.println("3) refCount(2)");

        Flux<Integer> shared = Flux.<Integer>never()
                .doOnSubscribe(s ->
                        System.out.println("refCount:source connected"))
                .doOnCancel(() ->
                        System.out.println("refCount:source cancelled"))
                .publish()
                .refCount(2);

        Disposable first = shared.subscribe();
        System.out.println("refCount:first subscriber attached");

        Disposable second = shared.subscribe();
        System.out.println("refCount:second subscriber attached");

        first.dispose();
        System.out.println("refCount:first subscriber disposed");

        second.dispose();
        System.out.println("refCount:second subscriber disposed");
    }
}
```

Run from the directory containing `pom.xml` with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.ConnectableFluxDemo
```

**Expected standard output** (excluding Maven-specific messages):

```text
1) manual connect
manual:calling connect
manual:source subscribed
manual A=1
manual B=1
manual A=2
manual B=2
manual A=3
manual B=3
manual:disposing connection
manual:source cancelled
2) autoConnect(2)
auto:first subscriber attached
auto:source subscribed
auto A=10
auto B=10
auto A=11
auto B=11
auto A complete
auto B complete
auto:second subscriber attached
3) refCount(2)
refCount:first subscriber attached
refCount:source connected
refCount:second subscriber attached
refCount:source cancelled
refCount:first subscriber disposed
refCount:second subscriber disposed
```

### Output Explanation

**Part 1 — manual connect**

- Both subscribers A and B subscribed, yet the source has not started.
- `manual:calling connect` appears before `manual:source subscribed`.
- `connect()` starts one upstream subscription; both A and B receive the same three items.
- After `Flux.range`, `Flux.never()` keeps the source open. Disposing `connection` cancels upstream and triggers `doOnCancel`.
- This is why you should keep the `Disposable` when actively managing an infinite source.

**Part 2 — autoConnect(2)**

- Subscriber A subscribes first; threshold is not met yet, so no upstream subscription exists.
- `auto:first subscriber attached` appears before the source is subscribed to.
- When B subscribes, threshold 2 is met and the synchronous source emits 10, 11 to both.
- The source completes before B's subscribe call returns, so `auto:second subscriber attached` appears last.

**Part 3 — refCount(2)**

- The first subscriber does not meet the threshold; the source is not connected yet.
- The second subscriber meets the threshold; `Flux.never` is subscribed to.
- Disposing the first subscriber drops the subscriber count from two to one, below threshold 2; the upstream connection is cancelled.
- `refCount:source cancelled` appears before the line confirming the first subscriber was disposed.

Output order is deterministic because the operations in the demo run synchronously, without schedulers, timers, or network calls. The demo illustrates operator lifecycles; it does not prove that every HTTP/DB driver can roll back side effects on cancellation.

## 13. Spring WebFlux: Sharing One SSE Feed Across Multiple Clients

A practical case is multiple browsers watching one live feed. If each request creates a separate `Flux.interval`, each browser gets its own timer. If you want all clients to observe one source, you can place a shared publisher in a Spring singleton bean.

The following example consists of two classes for a Spring Boot application with the `spring-boot-starter-webflux` dependency. This is **application code**, not a standalone project; a Spring Boot main class and server configuration are still required.

File `SharedEventStream.java`:

```java
import java.time.Duration;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.stereotype.Component;
import reactor.core.publisher.Flux;

@Component
public class SharedEventStream {

    private final Flux<ServerSentEvent<Long>> events =
            Flux.interval(Duration.ofSeconds(1))
                    .map(tick -> ServerSentEvent.<Long>builder(tick)
                            .id(Long.toString(tick))
                            .build())
                    .publish()
                    .refCount(1);

    public Flux<ServerSentEvent<Long>> events() {
        return events;
    }
}
```

File `EventController.java`:

```java
import org.springframework.http.MediaType;
import org.springframework.http.codec.ServerSentEvent;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class EventController {

    private final SharedEventStream stream;

    public EventController(SharedEventStream stream) {
        this.stream = stream;
    }

    @GetMapping(path = "/events",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<ServerSentEvent<Long>> events() {
        return stream.events();
    }
}
```

### What Happens When Clients Connect?

1. Client A calls `GET /events`; WebFlux subscribes to `events`. `refCount(1)` meets its threshold and starts one upstream timer.
2. Client B connects while A is still active; B joins the same `ConnectableFlux` and receives subsequent ticks from the same timer.
3. B does not receive ticks emitted before B connected, because the source uses `publish()` rather than `replay()`.
4. If A closes the tab while B remains, the source keeps running for B.
5. When B also leaves, subscriber count reaches 0; `refCount(1)` cancels the timer.
6. Client C connecting later will create a new source subscription. `Flux.interval` starts a new sequence; in this demo, ticks restart from 0.

**Production note:** SSE IDs in this example are only in-memory ticks. If you need reconnection and event replay via `Last-Event-ID`, you need durable sequences, an event store, or a broker with offsets and replay logic. `publish().refCount(1)` does not automatically provide history or guarantee zero event loss.

### When to Use a Grace Period?

If browsers frequently reconnect within a few seconds, consider:

```java
.publish()
.refCount(1, Duration.ofSeconds(5));
```

The source is kept alive for the grace period after the last subscriber leaves. This reduces repeated upstream setup/teardown, though the source may still emit while no clients are connected. If data during that gap must be delivered to reconnecting clients, replay or separate storage is needed.

### A Shared Feed Can Be Affected by a Slow Client

If every client shares the same `publish`, consumer branch demands can coordinate and a slow subscriber can slow down the shared source. For dashboards, dropping intermediate states may be acceptable; for critical notifications, a reliable storage/replay mechanism is needed. Do not use the same policy for both kinds of data.

## 14. When to Use autoConnect, refCount, or connect in an Application?

| Scenario | Suggestion | Reason |
|---|---|---|
| Polling only needs to run while at least one browser is connected | `publish().refCount(1)` | Auto-starts and stops with consumers |
| Source must run once two workers register and live with the application lifecycle | `publish().autoConnect(2)` | Only needs a startup threshold |
| Application has a service explicitly managing start/stop | `publish()` + `connect()` | Component owns the connection Disposable |
| Only need to retain the latest state for late subscribers | `replay(1)` combined with appropriate lifecycle | Replays one item without holding full history |
| Need to persist every event across restarts | Broker/event store | ConnectableFlux only shares in memory |
| Each subscriber needs a separate upstream call | Keep source cold, do not share | Do not force sharing when semantics do not match |

### Be Careful with Singleton Beans

If creating a `ConnectableFlux` in a singleton bean, decide who owns the lifecycle:

- `refCount` fits when client presence determines whether the source needs to run.
- `autoConnect` fits when the source is started once and lives until completion or application shutdown.
- `connect()` fits when a component must manage connection manually, such as starting after app readiness and disposing on shutdown.

Do not call `connect()` every time a controller handles a request. That makes the lifecycle hard to control and creates races across requests.

## 15. Common Pitfalls

### Pitfall 1 — Assuming publish() Connects Automatically

```java
ConnectableFlux<Integer> shared = Flux.range(1, 3).publish();
shared.subscribe(System.out::println);
// Not connected yet, so the source has not emitted.
```

**Fix:** call `shared.connect()`, or use `autoConnect`/`refCount`.

### Pitfall 2 — Calling connect Before Subscribers Subscribe

With a finite synchronous source, `connect()` can emit and complete before subscribers arrive; `publish()` does not replay past data. **Fix:** subscribe the subscribers first, then connect; or choose `replay` if late subscribers need history.

### Pitfall 3 — Assuming autoConnect Auto-Disconnects When All Subscribers Leave

`autoConnect` only decides when to connect. Once the threshold is reached, it does not auto-disconnect based on subscriber count. **Fix:** use `refCount` or manage the Disposable from the autoConnect overload.

### Pitfall 4 — Using refCount with Too High a Threshold

`refCount(3)` disconnects upstream when the subscriber count drops to two. One remaining consumer does not mean the source keeps running. **Fix:** pick thresholds matching the actual lifecycle; most browser-driven feeds use threshold 1.

### Pitfall 5 — Assuming Late Subscribers Receive History

`publish` does not retain old items. **Fix:** `replay(k)` or a snapshot + delta stream endpoint, depending on the data contract.

### Pitfall 6 — Using Unbounded replay() on an Infinite Source

Every item can be retained, causing memory growth. **Fix:** choose `replay(k)` or a time bound, or persist history in a storage system.

### Pitfall 7 — Confusing ConnectableFlux with Sinks.Many

ConnectableFlux shares an existing source; Sinks let the application emit events. **Fix:** choose based on producer ownership and overflow/replay policies.

### Pitfall 8 — Not Retaining the Disposable from connect()

With an infinite source, there is no handle to explicitly stop the connection. **Fix:** store `Disposable` in the managing component and dispose on shutdown or when the source is no longer needed.

### Pitfall 9 — Disposing the Connection When Only One Client Should Leave

The connection Disposable disconnects the shared source for all subscribers. **Fix:** dispose only that client's subscription; let `refCount` decide when to disconnect the source.

### Pitfall 10 — Thinking Sharing Creates New Threads

`publish`/`replay` do not automatically create schedulers or parallel execution. Subscribers may receive callbacks on the thread emitting signals. **Fix:** if changing execution context is needed, use appropriate schedulers/operators; do not block the event-loop.

### Pitfall 11 — One Slow Subscriber Affecting All Clients

A shared stream coordinates demand; a slow subscriber can slow down upstream. **Fix:** determine whether drop/latest/sample is acceptable; if buffering is required, bound by items/bytes and define overflow. If each client needs complete independence, consider separate pipelines.

### Pitfall 12 — Placing Side Effects on the Wrong Side of publish

Side effects before publish typically run once on the shared source; after publish they can run once per subscriber. **Fix:** clarify whether metrics/logs/side effects belong to the source or each consumer.

### Pitfall 13 — Thinking autoConnect/refCount Provide Durable Replay

These operators manage subscriptions in memory. **Fix:** use Kafka, Redis Streams, a database, or an appropriate event store if replay across restarts, consumer offsets, and durability are needed.

### Pitfall 14 — Assuming Cancel Rolls Back External Work

Cancelling a connection can stop emitting further items, but already-sent side effects may still complete. **Fix:** idempotency, transactions, outbox, and reconciliation.

### Pitfall 15 — Calling connect in Multiple Places Across the Application

Multiple components owning the connection creates a confusing lifecycle. **Fix:** designate one owner; expose the shared Flux to consumers without handing out connect/dispose control everywhere.

## 16. Shared Source Design Checklist

Before using `ConnectableFlux`, answer:

1. Is the initial source cold or hot? How many upstream subscriptions does each subscriber currently create?
2. Do consumers genuinely need the same single upstream run?
3. Should you use `publish` or `replay`? Do late subscribers need history?
4. Who decides when to connect: an owner component, a subscriber threshold, or active consumer count?
5. If using `autoConnect`, who will dispose an infinite source when the application stops?
6. If using `refCount`, is the subscriber threshold appropriate? Is a grace period needed to avoid reconnect churn?
7. Can a slow subscriber slow everyone down? Are there explicit buffer/drop/latest policies and bounds?
8. Are side effects/logs/metrics placed before or after publish? Should they run once or per consumer?
9. When the source completes/errors, what do new subscribers receive? Is retry placed before or after the sharing operator?
10. Is durable replay across restarts needed? If so, is ConnectableFlux sufficient?
11. When a client disconnects, are subscriptions and resources released?
12. Have subscriber thresholds, late subscribers, cancellation, errors, and reconnection been tested?

## 17. Self-Check

**Question 1:** Does `Flux.range(1, 3).publish()` emit data immediately?

→ No. It creates a `ConnectableFlux`; `connect()` or an auto/refCount mechanism is needed.

**Question 2:** A subscribes, B subscribes, then connect. How many source subscriptions exist?

→ One upstream connection shared between A and B.

**Question 3:** Using `autoConnect(2)`, only A subscribes. Has the source started yet?

→ No. A second subscriber is needed to reach the threshold.

**Question 4:** Two subscribers triggered `autoConnect(2)`, then both cancel. Does an infinite source stop automatically?

→ It does not auto-stop just because subscriber count drops to 0. Connection management or `refCount` is needed.

**Question 5:** `refCount(2)` currently has two subscribers, and one leaves. What happens?

→ Count drops to one, below the threshold; the upstream connection is cancelled/disconnected.

**Question 6:** Does `publish()` resend already-emitted items to a late subscriber?

→ No. Use `replay` if in-memory history is needed.

**Question 7:** Is unbounded `replay()` safe for an infinite feed?

→ No. History can grow without bound; choose a count/time limit.

**Question 8:** What does `connect()` return?

→ A `Disposable` representing the upstream connection; disposing it disconnects the shared source.

**Question 9:** Does `refCount(1)` create a new thread per client?

→ No. It shares the source subscription; schedulers and the source determine execution threads.

**Question 10:** If each browser needs its own independent source, should you use publish/refCount?

→ Usually not. Keep the publisher cold if each browser needs an independent source.

**Key takeaway:** `ConnectableFlux` separates **subscriber joining** from **upstream starting**. `connect()` gives manual control, `autoConnect(n)` auto-starts once enough subscribers arrive without auto-disconnecting by count, and `refCount(n)` auto-starts and disconnects when subscriber count drops below the threshold. `publish` shares live items; `replay` retains in-memory history. Choose the right operator based on ownership, late subscribers, cancellation, backpressure, and durability requirements.

## References

- Project Reactor — [Hot Versus Cold: ConnectableFlux, publish, replay](https://projectreactor.io/docs/core/release/reference/advancedFeatures/reactor-hotCold.html).
- Project Reactor — [ConnectableFlux API: connect, autoConnect, refCount](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/ConnectableFlux.html).
- Project Reactor — [Flux API: publish, replay, cache, share](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Backpressure and request reshaping](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Project Reactor — [Sinks: multicast and replay](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html).
- Spring Framework — [WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [Server-Sent Events in WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann-methods/return-types.html).
