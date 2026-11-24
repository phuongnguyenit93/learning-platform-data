# `combineLatest` and Continuously Updating Data

**Topic:** Spring Framework Reactive → **Combining and Splitting Streams**.

When a screen needs to display data arriving from multiple **independently changing** sources, you usually do not want to wait for a pair of events at the exact same position or exact same instant. For example, product prices update per trade, exchange rates update with the market, and stock status updates from a warehouse system. Whenever any source emits new information, the screen needs to recompute an **aggregated snapshot from the latest known values**.

In Project Reactor, `Flux.combineLatest(...)` solves that need: **once every source has emitted at least one element, each new update from any source can produce a new combined result using the latest element from each source**.

Crucial distinction to remember right away: `combineLatest` combines by the **latest state at event-processing time**; it does not synchronize business time automatically, does not wait for sources to emit simultaneously, and does not pair elements by index like `zip`.

## 1. Problem: Multiple Sources Updating at Different Cadences

Suppose two streams:

- `prices: Flux<Integer>` emits new prices: 100, 120, 130, 140.
- `currencies: Flux<String>` emits currency units: "USD", then "EUR".

We want a display string formatted as `"price currency"`.

Consider the following deterministic sequence of events:

| Step | New event | Latest price | Latest currency | `combineLatest` emits |
|---:|---|---:|---|---|
| 1 | Price = 100 | 100 | Not yet available | Nothing emitted yet |
| 2 | Price = 120 | 120 | Not yet available | Nothing emitted yet |
| 3 | Currency = USD | 120 | USD | **120 USD** |
| 4 | Price = 130 | 130 | USD | **130 USD** |
| 5 | Currency = EUR | 130 | EUR | **130 EUR** |
| 6 | Currency source completes | 130 | EUR already known | No new result |
| 7 | Price = 140 | 140 | EUR already known | **140 EUR** |
| 8 | Price source completes | 140 | EUR | Combined stream completes |

Key points from this example:

1. Before step 3, **there is not enough data yet**: even though the price changed twice, a price–currency pair cannot be produced until the currency stream emits its first value.
2. When currency emits "USD", the operator uses **120**, the latest price, rather than going back to emit "100 USD".
3. Steps 4 and 5 both produce new results; neither source needs to wait for a matching update from the other.
4. When the currency source **has emitted at least one element and then completes**, its latest value can still be reused in combinations until all sources complete.
5. The `onComplete` signal itself is not a value update, so it does not generate another snapshot on its own.

### Timeline diagram

```text
Time       ──────────────────────────────────────────────────────▶

prices       100       120         130                 140       |
currencies                  USD             EUR    complete
                            ▲
                         at least one
                         value from each
                         source available

combined                    120 USD     130 USD   130 EUR  140 EUR |
                            ▲
                       first combination
```

The diagram shows **event order**, without implying fixed time intervals. When multiple sources actually emit on different threads, observed ordering can differ across runs; do not use a timing diagram to promise ordering in a real concurrent system.

## 2. How `Flux.combineLatest` Works

Given `n` sources `S1, S2, ..., Sn`, the operator retains the latest value observed from each source. Conceptually:

1. **Subscribe** to the sources to combine, coordinating demand/backpressure.
2. Wait until **every source has an initial value**. Without all values present, the combinator is not called to emit a complete snapshot.
3. When a source `Si` emits a new item, update `Si`'s latest value.
4. Once all values are present, invoke `combinator` with the current set of latest values, then emit the result downstream.
5. Repeat as sources continue emitting; stop on completion, error, or cancellation.

Conceptual formula:

```text
latest = [last(S1), last(S2), ..., last(Sn)]

onNext(Si, value):
    latest[i] = value
    if every source has a value:
        downstream.onNext(combinator(latest))
```

This is **explanatory pseudocode**, not the full internal API. Reactor also handles requests, prefetch, queues, cancellation, errors, and signal synchronization; do not assume the `latest` array is shared mutable memory that application code can modify.

**The result is a `Flux<R>`**, because one source can emit multiple updates and trigger multiple combined snapshots. The sources do not need to have equal item counts. A fast source can update continuously while a slow source retains its latest value.

### “Has a value” does not mean “data is still fresh”

The latest value is the **latest one the operator received**, with no guarantee of real-time freshness. If the exchange-rate stream is silent for an hour, `combineLatest` can still combine an updated price with an exchange rate from an hour ago.

Therefore, when business logic requires freshness:

- Attach an observation timestamp (`observedAt`), version number, or sequence number to the data.
- Check latency and time skew between sources before emitting a snapshot considered valid.
- Define a policy for silent sources, disconnects, or missing initial state.
- If you want to warn when data becomes stale solely because time passes, you need a **timer/heartbeat or timeout**: `combineLatest` does not re-run the combinator just because the clock advances.

## 3. Comparing `combineLatest`, `zip`, and `merge`

All three operators process multiple publishers, but they solve different problems.

| Operator | Core rule | When appropriate |
|---|---|---|
| **`Flux.combineLatest`** | Once each source has at least one item, emit a new combination whenever any source emits a new item | Dashboards, independently updating state, multi-field forms |
| **`Flux.zip`** | Pair elements by **position**: 1st item of A with 1st item of B, 2nd with 2nd... | Combining two sequences of correspondingly ordered results |
| **`Flux.merge`** | Push each source's items into a single shared stream as they arrive, without combining values into tuples | Unifying homogeneous events from multiple sources |

Suppose A emits `A1, A2, A3` and B emits `B1, B2`:

```text
zip:
  (A1, B1), (A2, B2)
  No B3 to pair with A3; per completion rules, no further pair is emitted.

combineLatest (if events occur in order A1, A2, B1, A3, B2):
  (A2, B1), (A3, B1), (A3, B2)

merge (same event order):
  A1, A2, B1, A3, B2
```

`zip` requires positionally corresponding data; `combineLatest` can **reuse the same value** of B multiple times as A changes. `merge` does not construct a snapshot containing fields from both sources; if you need to know which source an event came from, tag/label items before merging.

**You cannot replace `combineLatest` with `zip`** on a price-and-exchange-rate screen that updates at different rates: if a new price arrives while the exchange rate has no new update, `zip` may keep waiting, whereas `combineLatest` can update the screen with the known exchange rate.

## 4. Common Overloads of `Flux.combineLatest`

Project Reactor provides several overloads. Example with **two sources of different types**:

```java
Flux<Integer> prices = ...;
Flux<String> currencies = ...;

Flux<String> display = Flux.combineLatest(
        prices,
        currencies,
        (price, currency) -> price + " " + currency
);
```

This **snippet** requires `prices` and `currencies` to be actual publishers. The two-argument lambda receives typed `Integer` and `String` values and returns a non-null `String`.

With **three sources of different types**, you can use the overload taking `Function<Object[], R>`:

```java
Flux<Integer> prices = ...;
Flux<String> currencies = ...;
Flux<Boolean> available = ...;

Flux<String> display = Flux.combineLatest(
        prices,
        currencies,
        available,
        values -> {
            Integer price = (Integer) values[0];
            String currency = (String) values[1];
            Boolean inStock = (Boolean) values[2];

            return price + " " + currency +
                    (inStock ? " | in stock" : " | out of stock");
        }
);
```

This is also a snippet; complete data sources are not included. Positions in `Object[]` match the **order of publishers passed in**. Cast accurately, verify indices, and keep the combinator function concise. For business data, prefer returning a `record`/DTO with meaningful fields rather than concatenating strings.

A general overload:

```java
Flux<Result> combined = Flux.combineLatest(
        listOfPublishers,
        values -> transform(values)
);
```

Here `listOfPublishers` and `transform` are hypothetical components; actual usage also depends on generic types. Overloads for `Iterable` or varargs allow customizing `prefetch`. `prefetch` is the **upfront demand requested from each upstream**, not a count of business records to retain or a guarantee that every event is displayed.

Never return `null` from a combinator. In Reactor, `onNext` elements cannot be null; if the combinator returns null or throws an exception, the resulting stream can terminate with `onError`.

## 5. Runnable Java 17+ Example: Updating via `Sinks.Many`

To observe the exact emission order without relying on `Thread.sleep` or scheduler timing, the example uses **Sinks** to create two manual event sources. The `tryEmitNext` calls run sequentially on the main thread, so there is no race between sources in the demo.

Directory structure:

```text
combine-latest-demo/
├── pom.xml
└── src/main/java/demo/CombineLatestDemo.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>combine-latest-demo</artifactId>
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

File `src/main/java/demo/CombineLatestDemo.java`:

```java
package demo;

import reactor.core.publisher.Flux;
import reactor.core.publisher.Sinks;

public class CombineLatestDemo {

    private static <T> void emit(Sinks.Many<T> sink, T item) {
        Sinks.EmitResult result = sink.tryEmitNext(item);
        if (result != Sinks.EmitResult.OK) {
            throw new IllegalStateException("Emission failed: " + result);
        }
    }

    private static void complete(Sinks.Many<?> sink) {
        Sinks.EmitResult result = sink.tryEmitComplete();
        if (result != Sinks.EmitResult.OK) {
            throw new IllegalStateException("Completion failed: " + result);
        }
    }

    public static void main(String[] args) {
        Sinks.Many<Integer> prices =
                Sinks.many().multicast().directBestEffort();

        Sinks.Many<String> currencies =
                Sinks.many().multicast().directBestEffort();

        Flux<String> snapshots = Flux.combineLatest(
                prices.asFlux(),
                currencies.asFlux(),
                (price, currency) -> price + " " + currency
        );

        snapshots.subscribe(
                value -> System.out.println("snapshot=" + value),
                error -> System.out.println("error=" + error.getMessage()),
                () -> System.out.println("complete")
        );

        System.out.println("price=100");
        emit(prices, 100);

        System.out.println("price=120");
        emit(prices, 120);

        System.out.println("currency=USD");
        emit(currencies, "USD");

        System.out.println("price=130");
        emit(prices, 130);

        System.out.println("currency=EUR");
        emit(currencies, "EUR");

        System.out.println("currency complete");
        complete(currencies);

        System.out.println("price=140");
        emit(prices, 140);

        System.out.println("price complete");
        complete(prices);
    }
}
```

Requires JDK 17+ and Maven. Inside the `combine-latest-demo` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.CombineLatestDemo
```

**Expected standard output of the program** (excluding Maven logs):

```text
price=100
price=120
currency=USD
snapshot=120 USD
price=130
snapshot=130 USD
currency=EUR
snapshot=130 EUR
currency complete
price=140
snapshot=140 EUR
price complete
complete
```

Step-by-step explanation:

1. The two `Sinks.Many` instances are active event emitters. `asFlux()` lets Reactor consume them as `Flux` sources.
2. `snapshots.subscribe(...)` subscribes before emitting events; this `subscribe` overload takes `onNext`, `onError`, and `onComplete` consumers. It requests unbounded data by default, which suits a small demo.
3. `price=100` and `price=120` produce no snapshot yet because `currencies` has not emitted any item.
4. When currency = USD, the latest price is 120, so the first snapshot is `120 USD`.
5. Price and currency change independently; each subsequent update combines with the latest value from the other source.
6. When the currency source completes after EUR, the combination **still retains EUR** to pair with price 140 from the price source.
7. Only after the price source also completes does the combined stream print `complete`.
8. The `emit`/`complete` helpers check `Sinks.EmitResult` to avoid silently ignoring failed emissions.

### Why use `directBestEffort` in the example?

`Sinks.many().multicast().directBestEffort()` delivers items to subscribers that currently have demand; a slow subscriber may miss items. It **does not replay old items to late subscribers** and can return a failure if there are no subscribers or no demand. In this program, a single subscriber subscribes beforehand with unbounded demand and the sources emit sequentially, so every `tryEmitNext` succeeds.

In a real application, sink selection depends on policies for **data loss, buffering, latency, multiple subscribers, and reconnects**. Do not use `directBestEffort` as a durable queue guaranteeing every business event is retained.

**Boundary of the example:** this is a complete Reactor Core program with no Spring Boot required. Prices and currencies are emitted manually to demonstrate `combineLatest` mechanics accurately; it does not connect to a database or market feed.

## 6. `combineLatest` with Continuous Updates and Configuration Sources

Not every source needs to run forever.

### 6.1. One one-shot configuration source, one multi-update source

```java
Mono<String> currency = Mono.just("USD");
Flux<Integer> prices = Flux.just(100, 110, 120);

Flux<String> labels = Flux.combineLatest(
        currency,
        prices,
        (unit, price) -> price + " " + unit
);
```

This is a snippet in a project with Reactor Core. `currency` emits one value and completes. The value "USD" remains usable for combining subsequent prices from `prices` until `prices` completes. Because the example sources run synchronously on subscribe, **do not rely on a specific event order solely from this declaration**; the final result and subscription behavior are affected by actual emission timing. When tests require exact ordering, use controllable sources like `Sinks` in section 5.

If configuration changes continuously, it should be a `Flux<ConfigUpdate>` so results are regenerated whenever a new config version arrives.

### 6.2. Seeding an initial value for a source without events yet

`combineLatest` **cannot emit while any source is missing its first value**. If the UI needs to render immediately, you can seed a genuine business value:

```java
Flux<String> currencyUpdates = ...;

Flux<String> currencyWithInitial =
        currencyUpdates.startWith("USD");
```

This is a snippet. `startWith("USD")` provides an initial value before streaming changes; it does not verify that "USD" is still valid at connection time. Only seed a value that is **known and acceptable** per business rules. If no reliable initial state exists, handle loading/unknown state and timeouts instead of inventing a value to force a snapshot.

Another option is a hot `Sinks.many().replay().latest()` source so new subscribers can receive the **most recent element retained by the sink**. However, replay does not replace persistence, consistent snapshots, or freshness checks; on process restart, in-memory state does not survive automatically.

### 6.3. Combining two update streams for the same entity

```java
record PriceUpdate(String sku, long amount, long version) { }
record StockUpdate(String sku, int quantity, long version) { }
record ProductView(String sku, long amount, int quantity) { }

Flux<PriceUpdate> priceUpdates = ...;
Flux<StockUpdate> stockUpdates = ...;

Flux<ProductView> views = Flux.combineLatest(
        priceUpdates,
        stockUpdates,
        (price, stock) -> new ProductView(
                price.sku(), price.amount(), stock.quantity())
);
```

**Illustrative snippets:** `priceUpdates`/`stockUpdates` must be declared in real code; `record` requires Java 16+.

The implicit precondition here is: **both sources must pertain to the same SKU**. If one source emits prices for SKU-A while the other emits stock for SKU-B, `combineLatest` **does not join by key automatically**, and the code above will produce invalid data. With multiple keys, partition/join by key appropriately or maintain a per-key snapshot map and emit models whose consistency has been verified.

## 7. Lifecycle: No Item Yet, Completed, Errored, or Never Emits

### Case A: All sources have emitted an item

Once every source has emitted at least once, `combineLatest` can emit combinations. Each subsequent `onNext` from any source can trigger another snapshot. One element from A may be reused across **multiple snapshots** alongside different B and C elements.

### Case B: A source completes without emitting any item

If a `Flux.empty()` (or `Mono.empty()`) completes **before emitting an item**, the combination can never build a complete tuple. The combined stream can complete empty; it does not automatically invent a default value or `null` for that source.

```java
Flux<String> combined = Flux.combineLatest(
        Flux.<Integer>empty(),
        Flux.just("USD"),
        (price, currency) -> price + " " + currency
);
// No valid combination from an empty price source.
```

This is a snippet. If empty genuinely means “no price available”, decide explicitly whether to show a loading screen, a no-data notice, or a valid business fallback.

### Case C: A source emits then completes

A source that completed after emitting at least one item leaves its latest value available for the remaining sources to use. The combined stream completes when all required sources have completed, or terminates early on error or cancellation.

Do not equate `onComplete` of **one** source with `onComplete` of the entire combined Flux.

### Case D: A source never emits a first item

A source like `Flux.never()` emits neither `onNext` nor a terminal signal. Without an error or another terminating branch, `combineLatest` can wait forever because **the initial set of values is incomplete**.

For HTTP endpoints or dashboards, define a strategy for missing data: deadlines, timeouts, loading states, verified fallbacks, health checks, or incident alerts. Never assume the subscription will complete on its own.

### Case E: A source emits an error

An unhandled `onError` from any source normally causes the `combineLatest` result to **terminate with an error and cancel remaining sources**. Do not silently swallow errors and keep displaying values as if fresh data were still trustworthy.

```java
Flux<String> source = remoteUpdates()
        .onErrorResume(error -> fallbackUpdates(error));
```

This is a snippet with two hypothetical methods returning `Flux<String>`. Specific handling depends on the error type: bounded retry with backoff, switching to a trusted fallback source, or reporting unhealthy status. Do not blindly use `onErrorComplete()`, as it can turn a failure into a completed source and leave the combination holding **stale values** that are no longer valid.

### Case F: Downstream cancels

When the subscriber cancels (for example, a user closes an SSE connection or the application disposes the subscription), subscriptions to the upstream sources can be cancelled. Cancellation does not guarantee already-started external side effects are rolled back. With a shared `Sinks` source, one subscriber cancelling does not mean the global sink is cancelled for all other subscribers.

## 8. Spring WebFlux in Practice: Continuous Updates over SSE

Spring WebFlux can return `Flux<DTO>` from an endpoint to stream data over time. With Server-Sent Events (SSE), a browser or client can keep a connection open and receive new snapshots.

The following example is a **valid controller** for a Spring Boot application with `spring-boot-starter-webflux`. Both sources use `Flux.interval` to simulate different update cadences rather than connecting to a live feed:

```java
import java.time.Duration;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class LiveDashboardController {

    @GetMapping(path = "/dashboard/live",
            produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public Flux<DashboardSnapshot> live() {
        Flux<Long> fastTicks = Flux.interval(Duration.ofSeconds(1));
        Flux<Long> slowTicks = Flux.interval(Duration.ofSeconds(3));

        return Flux.combineLatest(
                fastTicks,
                slowTicks,
                DashboardSnapshot::new
        );
    }

    public record DashboardSnapshot(long fastTick, long slowTick) { }
}
```

Processing flow when a client connects:

1. WebFlux subscribes to the returned publisher.
2. The fast timer emits one element roughly every second; the slow timer roughly every three seconds.
3. **No snapshot is emitted** until both timers have emitted their first value.
4. Thereafter, each tick from either source combines with the latest tick value from the other source.
5. WebFlux serializes each `DashboardSnapshot` and sends it over the SSE connection. When the client closes the connection, the subscription is typically cancelled.

Do not promise exact timestamps, exact per-second event counts, or specific ordering when timers coincide: the scheduler and system load affect observed timing. `Flux.interval` also has its own behavior when downstream lacks sufficient demand; do not treat it as a tick source that can never drop or lag.

**This is not a standalone application:** it needs a Spring Boot main class, server, dependencies, and runtime environment. With real sources, replace `fastTicks`/`slowTicks` with `Flux` streams receiving prices, stock levels, alerts, etc., and control initial state, keys, errors, reconnects, connection limits, and resources.

### Overall architecture

```text
price events ─────┐
                  ├── combineLatest ── map -> DashboardSnapshot ── SSE client
stock events ─────┘                        │
                                          └── distinctUntilChanged (if appropriate)
```

If new elements **do not change the displayed values**, `distinctUntilChanged()` on a DTO with proper `equals` can suppress consecutive duplicate snapshots. However, if every event must be audited or counted accurately, **do not use distinct**: two events with identical values can still be two distinct business events.

### Hot and cold sources in WebFlux

- **Cold source:** each subscription can start its own work or timer. In the `Flux.interval` example, each client creates a subscription with its own cadence.
- **Hot shared source:** multiple clients can receive events pushed from the system through a sink or message broker. Late subscribers may **miss prior events** if the source does not replay.
- **Per-subscription `combineLatest` state:** each subscriber maintains the latest progression that specific subscriber actually observed. Two clients connecting at different times may see different states until both receive full initial data.

For a production dashboard, explicitly define **how a new client receives its first snapshot**: fetch current snapshot, replay the latest item, or use a snapshot endpoint + delta stream with a strategy avoiding races between snapshot and subscription.

## 9. Freshness, Consistency, and Late-Arriving Events

A major mistake is treating a `combineLatest` snapshot as a consistent transactional read across systems. In reality, it combines the **latest observed value** from each source; sources may have different clocks, different network latencies, and update in separate transactions.

Example:

```text
Price: version=12, observedAt=10:02:05, amount=100
Stock: version= 8, observedAt=10:01:20, quantity=3

combineLatest -> Price v12 + Stock v8
```

The snapshot above is valid under **latest-observed semantics**, yet may not be consistent enough if the business requires matching transactions or versions.

Strategies:

1. **Attach metadata:** include `id`/key, `version`, `observedAt`, and `source` on each item. Do not emit bare numbers if freshness must be checked.
2. **Check before displaying:** if `Duration.between(oldTime, Instant.now())` exceeds a threshold, mark as stale or reject outdated data.
3. **Guard against out-of-order late updates:** an event received later does not necessarily have a newer business version; filter by sequence/version at each source if you need latest **by version**, not merely latest **by arrival**.
4. **If transactional consistency is required:** require APIs/snapshots with synchronized versions, event-time windows, correlation IDs, or appropriate transactional mechanisms; `combineLatest` alone does not perform keyed joins, windowing, or transactions.
5. **Control UI cadence:** you can sample/throttle snapshots when updates are too frequent, understanding that doing so can skip intermediate states.

An illustrative DTO:

```java
import java.time.Instant;

record PriceEvent(String sku, long price, long version, Instant observedAt) { }
record StockEvent(String sku, int quantity, long version, Instant observedAt) { }
record ViewState(String sku, long price, int quantity,
                 Instant priceSeenAt, Instant stockSeenAt) { }

// Both sources must share the same SKU, and events must already be filtered by business version.
Flux<ViewState> states = Flux.combineLatest(
        priceUpdates,
        stockUpdates,
        (price, stock) -> new ViewState(
                price.sku(),
                price.price(),
                stock.quantity(),
                price.observedAt(),
                stock.observedAt()
        )
);
```

This is a snippet; `priceUpdates` and `stockUpdates` must be declared as `Flux<PriceEvent>`/`Flux<StockEvent>` in the application. It illustrates the fields to retain for consistency checks; **it does not verify matching SKUs or freshness by itself**.

## 10. Backpressure, Prefetch, and Update Rate

`combineLatest` keeps latest state, yet **this does not mean “there is never a queue” or “every event is preserved”**.

- Upstream can emit faster than downstream processes; Reactor must coordinate requests/prefetch and internal buffers depending on version, overload, and operators.
- Overloads with `prefetch` control how much is requested upfront from **each source**, rather than guaranteeing an absolute bound on data across the entire system.
- A hot `Sinks` source has its own policy: buffer, drop, replay, or fail when demand is lacking. Choosing the wrong sink can cause UI updates to be lost before reaching `combineLatest`.
- The combinator runs on every opportunity to build a snapshot; if it performs heavy computation, large serialization, or blocking I/O, it can bottleneck the pipeline.
- The update rate of a fast source can drive most recomputations even if the other sources rarely change.
- Reactor documents `combineLatest` as **unsuitable if you need precise discard/unpropagated-element cleanup guarantees**, because the same item can be reused across multiple combinations. Do not use this operator as a complete store of every event requiring an audit trail.

Example of reducing overly dense updates before sending to the UI:

```java
Flux<DashboardSnapshot> throttledForDisplay = combinedSnapshots
        .sample(java.time.Duration.ofMillis(250))
        .distinctUntilChanged();
```

This is a snippet. `sample` picks only the latest element at a periodic interval; **it intentionally does not preserve every intermediate change**. Suitable for state-based dashboards, not suitable for ledgers, payments, or event auditing. Measure latency and real load before choosing a sampling period.

If downstream needs **every individual event**, design a durable event stream and sequential processing rather than expecting `combineLatest` to return the history of all merged events.

## 11. Common Mistakes When Using `combineLatest` in Applications

### Mistake 1 — Expecting a snapshot as soon as the first source emits

```java
Flux<String> result = Flux.combineLatest(
        priceFlux,
        currencyFlux,
        (price, currency) -> price + " " + currency
);
```

This is a snippet; if `priceFlux` emits while `currencyFlux` has no item yet, there is no output. **How to handle:** provide a reliable initial value, or represent loading/unknown state and timeouts.

### Mistake 2 — Using `zip` for a dashboard that needs the latest data

`Flux.zip(priceFlux, currencyFlux, ...)` waits for positional pairs. If currency is quiet, new prices produce no snapshots. **How to handle:** use `combineLatest` for independent latest state; use `zip` when positional pairing is intended.

### Mistake 3 — Confusing “latest” with latest by business version

A version 7 event arriving **after** version 8 can overwrite latest-observed with version 7 if there is no filter. **How to handle:** validate version and business ordering on each source.

### Mistake 4 — Combining mismatched keys

`combineLatest` knows nothing about SKUs or user IDs. It can combine SKU-A's price with SKU-B's stock if you feed it two global streams. **How to handle:** route/partition by key before combining.

### Mistake 5 — Waiting forever because one source never emits a first value

If source B connects slowly or emits nothing, A can keep updating forever with no snapshot produced. **How to handle:** use valid seeding, timeouts, status reporting, or adjust the upstream contract.

### Mistake 6 — Turning an infrastructure error into completion and keeping stale data

Carelessly using `onErrorComplete` can cause the combination to keep displaying an old exchange rate as if it were still valid. **How to handle:** design error/stale states, retry/backoff, or explicit failure.

### Mistake 7 — Heavy side effects inside the combinator

Never send emails, write to a DB, sleep, or perform synchronous I/O inside the combinator when any small change can trigger recomputation. **How to handle:** make the combinator a pure function building a DTO; move side effects into a managed, bounded pipeline.

### Mistake 8 — Using a mutable object as the latest value

If a publisher emits an object and other code **mutates that object in place** without emitting `onNext`, `combineLatest` has no way to know the data changed and emits no new signal. **How to handle:** use immutable items (such as `record`) and emit a new item when state changes.

### Mistake 9 — Assuming SSE clients all see the same initial snapshot

A `multicast` hot source does not replay by default; a late-joining client may have no value from one of the sources yet. **How to handle:** provide an initial snapshot/replay state appropriately and define reconnect handling.

### Mistake 10 — Expecting transactional consistency in a snapshot

Price v12 and stock v8 can be combined together. **How to handle:** use versions/correlation IDs, snapshots from the same transaction, or appropriate windowed joins.

### Mistake 11 — Assuming `combineLatest` always runs asynchronously

If upstream emits synchronously, the combinator can run synchronously on the subscription/request path. Simply using `Flux` does not create a new thread. **How to handle:** understand schedulers and avoid blocking on the event loop; measure when switching execution contexts is needed.

### Mistake 12 — Assuming every intermediate event is preserved

Hot sources can drop under backpressure; combining latest intentionally prioritizes current state rather than pairing every event like `zip`. **How to handle:** design an event log when completeness is required, and distinguish event data from state data.

## 12. Scenario-Based Logic Checks

**Question 1:** Source A has emitted 10, 20; B has emitted nothing yet. How many snapshots?

→ **0**. There is no first value from B yet.

**Question 2:** B emits "X". Which snapshot is produced first?

→ **(20, "X")**, because 20 is the latest value of A.

**Question 3:** B completes after emitting "X", then A emits 30. Is there a new snapshot?

→ **Yes**, combining `(30, "X")` while the subscription remains active. B's completion does not erase its retained latest value.

**Question 4:** What if B completes empty before emitting any value?

→ A complete set of values can never be formed; the result can complete without emitting any item.

**Question 5:** A is a price feed for many SKUs, B is a stock feed for many SKUs. Can a single `combineLatest(A,B,...)` pair each SKU accurately?

→ **Not automatically**. You must ensure both streams share the same key or partition/join by key.

**Question 6:** System time changes from 10:00 to 10:05 with neither source emitting. Does the combinator re-run automatically to mark data stale?

→ **No**. An external event, timer, timeout, or freshness-checking mechanism is required.

**Question 7:** Source A emits 100 times, B emits once. Are there necessarily 100 1-to-1 paired combinations?

→ **No**. Once B has its first item, subsequent A updates can combine with the **same** latest B. The actual snapshot count also depends on A/B timing and downstream demand.

**Question 8:** You need to store every transaction for auditing. Should you retain only `combineLatest` output?

→ **No**. The output is a stream of aggregated snapshots and may not include each input event exactly once. Persist the raw events reliably according to business requirements.

## 13. Reactive Dashboard Implementation Checklist

Before using `Flux.combineLatest`, answer for yourself:

1. Does each source carry **state** or **events**? Does the business truly need a latest-observed snapshot?
2. Do the sources share the same **key**? Do you need to partition by user, product, tenant, or entity?
3. Where does a new client get its **initial values**? Does the source replay, or must you call a snapshot API?
4. Can data become **stale**? Do you have timestamps, versions, and timeouts?
5. If a source completes empty, disconnects, or errors, what does the UI show?
6. Do your sink, prefetch, and backpressure choices match producer and consumer speeds?
7. Is the combinator pure, fast, and free of blocking I/O?
8. Should you deduplicate snapshots with `distinctUntilChanged` or throttle with `sample`, and is skipping intermediate states acceptable?
9. Will multiple subscribers trigger duplicate connections, timers, or repeated work?
10. Do tests cover **before initial**, **after initial**, **source complete**, **empty**, **error**, **late subscriber**, **cancel**, and **fast/slow sources**?

**Remember:** `Flux.combineLatest` is for **combined snapshots from the latest value received from each source**. It waits for **one initial item from every source**, then recomputes whenever any source emits a new update. It fits continuously updating data such as dashboards and UI state; it does not automatically solve timestamp synchronization, key-based joins, guaranteed delivery of every event, or transactional consistency.

## References

- Project Reactor — [Flux.combineLatest and overloads (API)](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [Which operator do I need? Combining with zip or combineLatest](https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html).
- Project Reactor — [Sinks: multicast, backpressure, replay](https://projectreactor.io/docs/core/release/reference/coreFeatures/sinks.html).
- Project Reactor — [Backpressure and how operators reshape requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Spring Framework — [WebFlux annotated controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller.html).
- Spring Framework — [WebFlux reactive stack](https://docs.spring.io/spring-framework/reference/web/webflux.html).
