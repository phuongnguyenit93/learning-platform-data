# How `buffer` and `window` Change the Unit of Demand in Project Reactor

## 1. The Question: What Is `request(n)` Counting?

**Backpressure** in Reactive Streams allows the receiving side to actively request a number of data signals via `Subscription.request(n)`. The number `n` counts **`onNext` elements right at the Publisher–Subscriber interface under consideration**, not inherently original records, bytes, elements inside a list, or I/O calls.

In Spring WebFlux/Project Reactor, both the **`buffer`** and **`window`** operators group a stream into batches/windows. After grouping, however, the element type received by downstream has changed:

```text
                        each onNext is an Integer
Flux<Integer> ──────────────────────────────────┐
                                               │
             buffer(3)                         window(3)
                 │                                 │
                 ▼                                 ▼
        Flux<List<Integer>>                Flux<Flux<Integer>>
        each onNext is a List              each onNext is an inner Flux
        containing at most 3 Integers      (a "window")
                 │                                 │
                 ▼                                 ▼
        request(2) = requests              request(2) = requests
        at most 2 lists                    at most 2 inner Fluxes
```

Therefore, saying "downstream `request(2)`" is **not enough to conclude** that upstream was requested for exactly two original elements. You must determine how the operator sitting between the two sides transforms the unit.

Here are the main takeaways:

- With `buffer(3)`, downstream demand is counted in **numbers of `List<T>`**. In the fixed-size, non-overlapping buffering case, a request for two lists normally translates into requesting up to **six `T` elements** upstream.
- With `window(3)`, **outer** demand is counted in **numbers of inner `Flux<T>`** emitted. Inside each window, there is a **separate subscription and demand** to consume individual `T` elements. You cannot take the number of requested windows and deduce total inner data demand while ignoring the window subscribers.

Both still must honor the Reactive Streams contract: never emit `onNext` beyond each subscriber's valid demand; honor `onComplete`, `onError`, `cancel()`, and the release of resources.

## 2. Recap of Demand Mechanics Before Grouping

A simple sequence:

```java
Flux<Integer> numbers = Flux.range(1, 7);
```

`Flux.range` can emit `1..7`, yet it respects requests received from the subscriber. With a subscriber that initially only calls `request(2)`, the source cannot emit three `onNext` signals before receiving additional demand. A `request` call is **maximum permission to receive**, not a guarantee that the source always has enough elements to send.

When an intermediate operator is present, we have at least **two demand boundaries**:

```text
[Upstream Publisher<T>]
          │
          │ onNext(T), request(k) upstream
          ▼
[buffer(...) / window(...)]
          │
          │ onNext(R), request(m) downstream
          ▼
[Downstream Subscriber<R>]
```

`k` and `m` do not have to be equal. The operator must **translate requests** based on the result type and how it consumes data; that is why demand is said to have "changed units".

At the same time, `request(n)` is not a "fetch n records instantaneously" operation. It can lead to subsequent work, can accumulate, and can pass through operators that use prefetching or queues.

## 3. `buffer(size)`: From Element Demand to List Demand

### 3.1. Output Contract

`Flux<T>.buffer(int maxSize)` emits non-overlapping `List<T>` instances, each containing at most `maxSize` elements. With `maxSize = 3`:

```java
Flux<List<Integer>> batches =
        Flux.range(1, 7).buffer(3);
```

When the entire source is consumed, the downstream values are:

```text
onNext([1, 2, 3])
onNext([4, 5, 6])
onNext([7])
onComplete()
```

**The final output may contain fewer than three elements** because the source completed. With an empty source, `buffer(3)` does not fabricate an empty list to emit; it simply completes. The `size` value must be positive.

The number of resulting elements for a finite, error-free source with simple `buffer(size)` is \(\lceil N/\mathrm{size}\rceil\); with `N = 7`, `size = 3`, that equals 3. This is the number of **lists**, not the number of original elements.

### 3.2. How to Interpret Demand

Consider a simple pipeline without `filter`, `publishOn`, or other demand-altering operators:

```text
Flux.range(1, 7)  ->  buffer(3)  ->  Subscriber<List<Integer>>
                                            |
                                         request(1)
```

After `request(1)` downstream of `buffer`:

1. The subscriber asks for **one `List<Integer>`**.
2. `buffer(3)` needs up to **three `Integer` elements** to close a full list, so it adjusts the upstream request accordingly.
3. Upon receiving numbers 1, 2, 3, the operator emits `onNext([1,2,3])`.
4. If downstream has not requested more, the operator must not emit a second list to that subscriber.
5. When downstream calls `request(1)` again, it has permission to receive one more **list**, not just one number.

Example demand conversion in this fixed-size case:

| Downstream Call | Requested Unit | Upstream Elements Needed for a Full-Size Group |
|---|---|---|
| `request(1)` | 1 `List<T>` | Up to 3 `T` for `buffer(3)` |
| `request(2)` | 2 `List<T>` | Up to 6 `T` for `buffer(3)` |
| `request(1)` after two full lists | 1 more `List<T>` | Possibly only one `T` left at the end of the source |

**Limitation of this table:** this is a simple model to explain non-overlapping `buffer(3)`. Do not treat the `n × size` formula as a law for *every* buffer overload, every chain, or every I/O task. If upstream completes early, the operator may emit a partial final list; if the source is slow, it still has to wait for data.

In a multi-stage pipeline, operators at **each stage** can further alter request counts: `filter` may drop elements, `publishOn` may prefetch, and `flatMap` has multiple inner publishers. Measure demand via actual signals/metrics when optimizing performance.

### 3.3. Where Does `buffer` Store Data?

`buffer(3)` must hold the elements of the **list currently being built** in memory until three elements arrive or a buffer-closing condition occurs. If multiple groups are open, or with time/boundary buffer variants, memory usage can grow with the number and size of groups.

Batching can reduce the number of business-processing calls—for example, a batch DB write—but does not automatically reduce the volume of data that must be held; nor does it mean the backend executes one transaction per `List` unless the application explicitly designs transactions that way.

## 4. `window(size)`: Demand Has Two Levels

### 4.1. Outer `Flux` and Inner `Flux`

`Flux<T>.window(int maxSize)` emits a stream **consisting of inner Publishers**; each inner Publisher represents a group of elements:

```java
Flux<Flux<Integer>> windows =
        Flux.range(1, 7).window(3);
```

Visualizing the result:

```text
Outer Flux<Flux<Integer>>
      |
      +-- onNext(window 1) -> inner Flux: 1, 2, 3
      +-- onNext(window 2) -> inner Flux: 4, 5, 6
      +-- onNext(window 3) -> inner Flux: 7
      +-- onComplete()
```

Unlike `buffer`, the outer stream does not emit `[1,2,3]` as a `List<Integer>`; it emits an **inner `Flux<Integer>`**. Elements inside the inner `Flux` can be processed in a streaming fashion—such as `reduce`, `map`, `filter`, `take`—instead of having to collect everything into a list first.

### 4.2. Two Subscription/Demand Relationships

```text
                                request(w) in WINDOW count
Subscriber<Flux<T>> ────────────────────────────────────┐
       ▲                                                │
       │ onNext(innerFlux)                              ▼
       └─────────────────────── window(3) <──── Upstream<T>
                                      │
                                      └── innerFlux ──> Subscriber<T>
                                                        request(e) in T count
```

We must separate:

1. **Outer demand:** the subscriber to `Flux<Flux<T>>` calls `request(w)` to ask for at most `w` **window objects**.
2. **Inner demand:** when a window is subscribed to, that window's subscriber calls `request(e)` to ask for at most `e` **`T` elements of the window**.
3. **Actual upstream demand** is coordinated by the `window` operator according to window open/close progress, outer demand, inner demand, buffering, and existing requests. Do not interpret an outer `request(1)` as "only one `T` element will be read".

Examples:

- Downstream outer `request(1)` permits emitting **one inner `Flux<Integer>`**.
- If using `concatMap(window -> window.reduce(0, Integer::sum))`, the operator subscribes to the window, accumulates the sum from inner signals, and emits **one sum** per window.
- If windows are emitted but **not consumed**, data/queues may be retained or the pipeline may stall due to lack of demand; emitting a window does not replace consuming the elements inside it.

With simple `window(3)`, it does not mean every element must enter a materialized `List` before the window appears. However, **do not conclude `window` always uses O(1) memory**: actual behavior depends on open window counts, queues, downstream operators, and consumer speed.

## 5. Comparing the Nature of `buffer` and `window`

| Criterion | `buffer(3)` | `window(3)` |
|---|---|---|
| Source type | `Flux<T>` | `Flux<T>` |
| Result type | `Flux<List<T>>` | `Flux<Flux<T>>` |
| One outer `onNext` contains | One list of elements | One inner Publisher |
| Unit of outer subscriber's `request(1)` | One **List** | One **window** |
| Additional inner demand | No separate Reactive Streams subscription per List | Each inner `Flux` is subscribed/consumed with its own demand |
| When a group ends normally | Emits full List or partial final List if source completes | Inner `Flux` completes; outer completes when no windows remain |
| Common processing pattern | Batch API calls, converting List to summary DTO | `concatMap`/`flatMap` on each inner `Flux`, streaming data inside |
| Memory | Must hold contents of Lists being constructed | Can process as a stream; still has queues and buildup risk if inner is slow |
| Common mistake | Thinking `request(1)` receives a single `T` | Thinking outer `request(1)` has already consumed all `T` in the window |

Both are used to **group data**. They do not turn blocking sources into non-blocking ones, do not spawn threads on their own, and do not replace load-limiting mechanisms when upstream can produce unbounded data.

## 6. Complete Java 17+ Example with Project Reactor

The example uses `Flux.range` (a cold, synchronous, finite source) for clear stdout. The program has three parts:

1. `BaseSubscriber<List<Integer>>` manually calls `request(1)` to illustrate demand in **lists**.
2. `window(3)` is consumed per window by `concatMap` and collected into a `List` **solely to clearly display window boundaries**.
3. `window(3)` combined with `reduce` sums each window without needing to build a `List` at that step.

Create the files:

```text
reactor-demand-groups/
├── pom.xml
└── src/main/java/demo/Main.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>reactor-demand-groups</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.12</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.0</version>
                <configuration>
                    <mainClass>demo.Main</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/demo/Main.java`:

```java
package demo;

import java.util.List;
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class Main {
    public static void main(String[] args) {
        // I. After buffer(3), each request(1) asks for ONE LIST.
        Flux.range(1, 7)
                .buffer(3)
                .subscribe(new BaseSubscriber<List<Integer>>() {
                    @Override
                    protected void hookOnSubscribe(Subscription subscription) {
                        System.out.println("request 1 batch");
                        request(1);
                    }

                    @Override
                    protected void hookOnNext(List<Integer> batch) {
                        System.out.println("buffer: " + batch);

                        // Continue until receiving the final partial buffer.
                        if (batch.size() == 3) {
                            request(1);
                        }
                    }

                    @Override
                    protected void hookOnComplete() {
                        System.out.println("buffer complete");
                    }
                });

        // II. Each window is an inner Flux. collectList is only for viewing contents.
        Flux.range(1, 7)
                .window(3)
                .concatMap(inner -> inner.collectList())
                .subscribe(
                        list -> System.out.println("window: " + list),
                        error -> System.out.println("window error: " + error),
                        () -> System.out.println("window complete")
                );

        // III. Process stream inside each window using reduce.
        Flux.range(1, 7)
                .window(3)
                .concatMap(inner -> inner.reduce(0, Integer::sum))
                .subscribe(
                        total -> System.out.println("sum: " + total),
                        error -> System.out.println("sum error: " + error)
                );
    }
}
```

From the directory containing `pom.xml`, requiring JDK 17+ and Maven:

```bash
mvn -q compile exec:java
```

Stdout printed by the program (excluding environment logs if Maven has custom configuration):

```text
request 1 batch
buffer: [1, 2, 3]
buffer: [4, 5, 6]
buffer: [7]
buffer complete
window: [1, 2, 3]
window: [4, 5, 6]
window: [7]
window complete
sum: 6
sum: 15
sum: 7
```

**Reading the trace:**

- `BaseSubscriber` alters the default pattern by only calling `request(1)` right upon subscription. The requested unit at that point is **one `List<Integer>`**.
- After each full three-number List, `hookOnNext` asks for **one more List**. At the end of the source comes List `[7]` and `onComplete`; there is no need to request more once terminated.
- `window(3)` creates three inner Fluxes. `concatMap` subscribes to them sequentially, and `collectList()` merely gathers **each** window's contents for display.
- In the sum calculation, `reduce(0, Integer::sum)` accumulates an integer per window, receiving elements one by one. This usage demonstrates the benefit of **processing an inner `Flux`**: no final list of all elements needs to be created.

**Distinguish clearly:** stdout shows the **values** and **order** of this synchronous source; it does not by itself prove the number of upstream requests. To inspect actual request counts in a specific pipeline, place `doOnRequest` at each observation point or test with `StepVerifier` and a demand-tracking publisher.

## 7. Observing Demand Changes with `doOnRequest`

An illustrative snippet intentionally placing logs on **both sides of `buffer(3)`**:

```java
Flux<List<Integer>> batches = Flux.range(1, 7)
        .doOnRequest(n -> System.out.println("upstream asks: " + n))
        .buffer(3)
        .doOnRequest(n -> System.out.println("downstream asks: " + n));
```

This is a **code snippet in a context with `Flux` and `List` imported**, not a standalone runnable program until a subscriber is added. If the subscriber calls `request(1)` on `batches`, the log placed after `buffer` reports a request for **one list**, while the log before `buffer` observes a request in **`Integer` elements** (in this simple configuration, one full list requires three numbers).

Note that `doOnRequest` log ordering depends on operator placement and request call sequences; do not infer that every `request` generates exactly one log line or follows a fixed print order across all schedulers. In particular, `doOnRequest` is an **observation tool**, not a method for calculating an entire application's prefetch policy from a single number.

Try placing logs before and after `window(3)`:

```java
Flux<Flux<Integer>> windows = Flux.range(1, 7)
        .doOnRequest(n -> System.out.println("source T request: " + n))
        .window(3)
        .doOnRequest(n -> System.out.println("outer window request: " + n));
```

The outer log measures **the number of inner Fluxes requested**, while the upstream log measures **the number of Integers**. To know how many elements are consumed inside each window, you must observe the *inner publisher* when it is subscribed to—for instance, using `inner.doOnRequest(...)` inside the window handler. Those are two different demand scopes.

## 8. Variants That Make the Demand Formula More Complex

### 8.1. Size and Skip Step: `buffer(size, skip)`

When `skip == size`, groups do not overlap and leave no gaps. When they differ:

- `skip < size`: **overlapping**. One source element can belong to **multiple Lists**.
- `skip > size`: **gapped (dropping)**. Some source elements do not enter any output List.

For example, `buffer(3, 2)` on source `1..6` produces groups starting at 1, 3, 5:

```text
[1, 2, 3]
[3, 4, 5]
[5, 6]       <- final incomplete group when source completes
```

In the overlapping variant, requesting two lists is **not equivalent** to two completely disjoint sets of 3 elements: data is shared. In the gapped variant, upstream also has to advance past elements that do not appear in the output. Thus, upstream requests are translated by the operator according to **both size and skip**; do not mechanically apply `demand × size` across all variants.

`window(size, skip)` can also open overlapping or gapped windows; inner/outer demand must then be examined alongside the window configuration and subscribers.

### 8.2. Time-Based or Boundary-Based Buffer/Window

- `bufferTimeout(maxSize, maxTime)` can close a List when max size is reached **or** time expires; element counts per List are not fixed.
- `windowTimeout(maxSize, maxTime)` can close an inner Flux based on size **or** time.
- Boundary and predicate variants (`bufferUntil`, `windowUntil`, `bufferWhile`, `windowWhile`, ...) have group open/close policies driven by signals or predicates, differing from `buffer(3)`/`window(3)`.

Time and boundaries make actual element counts per group vary; upstream demand cannot be predicted solely from a fixed group size. Some variants take parameters for specific backpressure/buffering strategies—read the exact API you are using.

## 9. Typical Implementation Mistakes

### Mistake A: Confusing List Demand with Element Demand

Counterexample to the reasoning: "`buffer(100)` received `request(1)`, so it is only allowed to read one record upstream." More accurately: that is a request for **one list**; to build a full list, the operator must request/consume up to **100 records** upstream in the simple grouping case. If a group holds 100 large records, emitting a single List can also contain lots of data and consume significant RAM.

### Mistake B: Producing Inner Windows Without Consuming Them

```java
Flux<Flux<Integer>> windows = Flux.range(1, 100)
        .window(10);

// Type illustration snippet: outer receives Flux<Integer>, elements not yet processed.
// Having only an outer subscriber does not guarantee inner windows are drained.
```

If an application receives window objects and ignores them, the values inside are not processed properly. When inner demand does not advance, some implementations/operators can accumulate data, stall progress, or force cancellation. Clearly define the purpose of each window and consume them with appropriate composing operators.

Commonly used:

```java
Flux<Integer> sums = Flux.range(1, 100)
        .window(10)
        .concatMap(inner -> inner.reduce(0, Integer::sum));
```

`concatMap` processes each inner Publisher in order. `flatMap` can process multiple inner publishers concurrently, though ordering and concurrency levels must be weighed.

### Mistake C: Collecting Every Window into a List and Thinking There Is No Buffering

```java
Flux<List<Integer>> lists = Flux.range(1, 100)
        .window(10)
        .concatMap(inner -> inner.collectList());
```

The result looks similar to `buffer(10)`, because **`collectList()` gathers each window's elements back into a List**. Using `window` does not automatically make the pipeline above list-free streaming. Choose `buffer(10)` if the goal is simply batching, and choose `window` when you need dedicated reactive processing per group.

### Mistake D: Confusing `buffer(n)` with `onBackpressureBuffer()`

Both names contain `buffer`, yet their **purposes differ**:

- `buffer(100)` is **grouping**: one downstream signal carries a `List<T>` of up to 100 elements.
- `onBackpressureBuffer(...)` is an **element-queuing strategy** when source and downstream have mismatched speeds. It does not turn `T` into `List<T>`, and queue bounds/out-of-memory risks must be understood.

Do not choose `buffer(100)` just because you want "overflow protection when downstream is slow"; you must analyze the entire source, rates, buffers, cancellation, and behavior when limits are exceeded.

### Mistake E: Blocking Work Inside Each Group

```java
// Anti-example if saveBlocking performs slow synchronous I/O.
Flux.range(1, 100)
        .buffer(10)
        .map(batch -> repository.saveBlocking(batch));
```

Even though call count is reduced via batching, this is still **blocking** I/O if the repository blocks. In WebFlux, doing so can block the event-loop thread. Use a non-blocking repository and an operator like `concatMap(batch -> repository.saveBatch(batch))` if the API returns a Publisher; if a blocking library is unavoidable, schedule it appropriately (e.g., `Mono.fromCallable(...).subscribeOn(Schedulers.boundedElastic())`) and bound concurrency.

This snippet only illustrates structure; `repository` and its methods are hypothetical project components.

### Mistake F: Uncontrolled Demand Handling Across Both Levels

If outer windows are requested faster than subscribers can process inners, many waiting windows or elements can accumulate. If an inner is retained without being subscribed to, data is not consumed. Choose `concatMap`, `flatMap` with bounded concurrency, or other operators based on ordering and load requirements; monitor metrics/buffers when data volumes are large.

## 10. Real-World Connection to Spring WebFlux

Suppose a system receives events as a `Flux<Event>` from a reactive API and needs to send batches to a storage service supporting non-blocking I/O:

```java
// Illustrative code in an existing service; Event and storageClient are project types.
// saveBatch(List<Event>) returns Mono<Void>.
Mono<Void> saveInBatches(Flux<Event> events) {
    return events
            .buffer(100)
            .concatMap(batch -> storageClient.saveBatch(batch))
            .then();
}
```

When downstream requests a result cycle from `concatMap`, `buffer(100)` supplies **one List**; that is where the demand unit changes from 100 `Event`s to one batch. `concatMap` waits until the current batch finishes processing before continuing sequentially, though actual prefetch strategies along the chain still need observation/tuning under high load.

If **streaming computation per group** is needed, `window` may fit better:

```java
// Illustration: each Event has an amount() method returning BigDecimal.
// sumWindow is an application-defined reactive processing function.
Flux<BigDecimal> totals = events
        .window(100)
        .concatMap(window -> window
                .map(Event::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add));
```

In the second example, each window is processed value by value, accumulating a `BigDecimal`; no List of 100 events is needed like in a batch API input. `Event`, `BigDecimal`, and `events` belong to the application and require importing `java.math.BigDecimal`; this is an **illustrative snippet inside a service**, not a standalone compilable file.

Using WebFlux does not make `BigDecimal` calculations run in parallel automatically. Concurrency depends on upstream, scheduling, and operators. Retry, transaction, timeout, and cancellation policies must be designed separately according to business requirements.

## 11. Guidelines for Testing and Measurement

To be sure you are not mistaking "grouped" for "load-controlled", inspect the boundaries:

1. **Element type at each stage:** `T`, `List<T>`, or `Flux<T>`?
2. **Unit of demand:** does `request(1)` ask for one original element, one List, or one window?
3. **How each inner window is consumed:** is there a subscriber or `concatMap`/`flatMap`, and is demand advancing?
4. **Actual group size:** the last group may be smaller; timeout/boundary variants may close early.
5. **Memory and latency:** open group count, largest List, upstream/inner queues, and source wait time.
6. **Cancellation and errors:** when downstream calls `cancel()` or upstream signals `onError`, are there resources needing cleanup or buffered elements being discarded?

To test demand for a specific configuration, you can use `reactor-test` and `StepVerifier` with `initialRequest(0)` followed by `thenRequest(...)`. Choose a controllable source publisher and test both levels of `window`. `StepVerifier` belongs to the `io.projectreactor:reactor-test` dependency, separate from `reactor-core` in the main example; do not assume every project already includes it.

## 12. Self-Check Exercises

**Exercise 1.** How many `onNext` signals does `Flux.range(1, 8).buffer(3)` emit downstream, and what is each signal?

**Answer:** Three `onNext` signals corresponding to `[1,2,3]`, `[4,5,6]`, `[7,8]`. Each `onNext` is a **List**, so three signals do not mean the source only contains three `Integer`s.

**Exercise 2.** With the source above, if a subscriber immediately after `buffer(3)` only calls `request(1)`, at most how many Lists is it allowed to receive at that moment?

**Answer:** One List. The first full list requires three `Integer`s upstream; to receive the second List, it must request more.

**Exercise 3.** What element type does `Flux.range(1, 8).window(3)` emit on the outer stream? What does outer `request(2)` mean?

**Answer:** Outer emits elements of type `Flux<Integer>`. Outer `request(2)` requests at most **two inner Fluxes**, not directly two `Integer`s. Each inner Flux must also be subscribed to and consumed separately.

**Exercise 4.** Why can `window(100).concatMap(w -> w.collectList())` still retain data in memory?

**Answer:** `collectList()` accumulates a window's elements into a List before emitting. Even with `window` upstream, this stage still must store data for each List.

**Exercise 5.** With `buffer(5, 2)`, can you multiply downstream demand by 5 to compute exact upstream requests?

**Answer:** No. Groups can overlap (starting every two elements with size five), and elements can be reused across multiple groups. Upstream requests depend on operator policy and configuration.

**Exercise 6.** Does `buffer(100)` completely replace protection against a source that is too fast?

**Answer:** No. It creates lists of maximum size 100 in the basic variant, yet does not automatically control buffers/rates at other layers, does not fix blocking I/O, and does not replace concurrency limits or resource monitoring.

**Key takeaway:** `buffer` turns demand from **elements → lists**; `window` turns outer demand from **elements → inner Publishers** plus **separate demand inside each Publisher**. When designing backpressure, always identify the `onNext` type at each pipeline segment before concluding how much original data `request(n)` represents.
