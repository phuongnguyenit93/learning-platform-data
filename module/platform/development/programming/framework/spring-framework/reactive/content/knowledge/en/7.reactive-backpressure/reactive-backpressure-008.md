# Handling Overflow and Observing Dropped Data in Reactor

## 1. Goal: What Happens When the Producer Is Faster Than the Receiver?

In **Spring WebFlux** and **Project Reactor**, a **Flux<T>** can receive events from a device, WebSocket, message broker, or computation stream faster than the Subscriber can process them. Reactive Streams addresses this mismatch with **backpressure**: the Subscriber sends **request(n)**, and the Publisher may only emit **onNext** within the unfulfilled demand.

However, not every source can slow itself down. Sensors, callback APIs, or push-based event systems may continue generating data while downstream is busy. In such cases, you need an **intentional decision**: retain data in a buffer, drop excess data, keep only the latest data, or signal an error on overflow. At the same time, you must **observe and clean up discarded data**, especially if elements hold resources such as buffers, file handles, or connections.

This lesson focuses on:

- **onBackpressureBuffer**, **onBackpressureDrop**, **onBackpressureLatest**, **onBackpressureError**.
- Buffer bounds and strategies **BufferOverflowStrategy.ERROR**, **DROP_LATEST**, **DROP_OLDEST**.
- **onOverflow/onDropped** callbacks, **doOnDiscard**, and how they differ from **Hooks.onNextDropped**.
- How to distinguish **overflow**, **normal discard**, **late signals**, and **cancellation**.
- A compilable/runnable Java 17+ example, how to read its output, and principles for Spring WebFlux.

## 2. Reviewing Demand Mechanics Before Choosing an Overflow Policy

A subscription consists of two directions of communication:

~~~text
Subscriber                                      Publisher
    | --------- subscribe(...) -----------------> |
    | <-------- onSubscribe(subscription) ------- |
    | --------- request(2) ---------------------> |
    | <-------- onNext(A) ----------------------- |
    | <-------- onNext(B) ----------------------- |
    |           (current demand exhausted)        |
    | --------- request(1) ---------------------> |
    | <-------- onNext(C) ----------------------- |
    | <-------- onComplete / onError ------------ |
~~~

- **request(2)** grants permission to emit up to two additional elements; it does not force the Publisher to emit both.
- Valid requests accumulate; **request(0)** or negative values violate the Reactive Streams contract.
- **onComplete** and **onError** are terminal signals and do not require a new request to be sent.
- **cancel()** requests cancellation; it is not a successful **onComplete** signal.
- A **protocol-compliant** Publisher does not emit more data than downstream requested. However, buffering or dropping operators may proactively call **request(Long.MAX_VALUE)** from upstream and then manage smaller demand downstream.

That last point explains why an example with **Flux.range(1, 5)**, which honors demand, can still demonstrate dropping or overflow: when placing **onBackpressureDrop** or **onBackpressureBuffer** in the middle, that operator requests unboundedly from **Flux.range**, while the trailing Subscriber requests only one element. The mismatch sits **between the operator and the final Subscriber**; it does not mean `Flux.range` violated Reactive Streams.

## 3. Three Concepts to Distinguish: Overflow, Discard, and Dropped Signals

| Phenomenon | Context | Example | Appropriate Observation Mechanism |
| --- | --- | --- | --- |
| **Backpressure overflow** | Source keeps emitting while downstream lacks demand or queue is full | Buffer max 100 items, 101st item arrives | **onOverflow**, **onBackpressureDrop(callback)**, **onBackpressureError**, metrics |
| **Discard** | Operator actively drops elements as normal logic or clears queues on cancel/error | **filter**, **skip**, **onBackpressureLatest**, cancelled buffer | **doOnDiscard(Class, Consumer)** if the operator supports it |
| **Dropped signal** outside normal flow | A signal arrives when no valid downstream destination remains, often from protocol violation or post-termination race | Publisher sends **onNext** after **onComplete** | **Hooks.onNextDropped**; similarly **Hooks.onErrorDropped** for late errors |

These three situations are not identical. The English word **drop** in **onBackpressureDrop** refers to a normal backpressure-handling policy. It **does not mean** every element dropped by that operator passes through the global **Hooks.onNextDropped** hook. This is a very common monitoring mistake: installing only `Hooks.onNextDropped` and noticing it fails to count elements discarded by `onBackpressureDrop`.

**Discard** is a broad concept: an element existed in the pipeline but is no longer forwarded to the intended consumer. Thus a buffer-overflowing value can be reported via the **overflow callback** *and* via **doOnDiscard** if the operator supports it. Two callbacks observing the same element do not automatically mean two elements were lost.

## 4. Four Primary Choices When Downstream Is Slow

| Operator | Behavior When Lacking Demand | Data Loss? | Error Due to Overload? | Suitable For |
| --- | --- | --- | --- | --- |
| **onBackpressureBuffer()** | Temporarily holds data; unbounded variant has no app-imposed capacity cap | Not from buffer policy while memory suffices; may discard on cancel/error | Risks running out of memory | Finite streams, backlog clearly bounded elsewhere |
| **onBackpressureBuffer(maxSize, ...)** | Holds up to `maxSize` waiting elements; when full, applies overflow policy | Depends on policy | Yes with `ERROR` policy | Bounded backlog acceptable and explicit full behavior needed |
| **onBackpressureDrop(...)** | Immediately drops arriving elements when downstream has no demand | **Yes** | Normally not due to overflow | Events droppable without breaking business rules |
| **onBackpressureLatest()** | Holds only one newest pending element; replaces old with new | **Yes** | Normally not due to overflow | Current state, progress, position, instantaneous telemetry |
| **onBackpressureError()** | Does not buffer excess elements; signals overflow via `onError` | Stream stops, leaving unprocessed data unhandled | **Yes** | When silent record dropping is forbidden |

**There is no perfect strategy for every business domain.** For financial transactions, exactly-once messages, or mandatory audits, dropping data can be functionally wrong. In those cases, prefer demand-aware sources, ingress rate limiting, durable queues, or concurrency tuning. For real-time charts, the latest state can matter more than every intermediate state.

These operators **do not make downstream faster**. They decide where risk is taken: memory capacity, data loss, or failing fast.

## 5. `onBackpressureBuffer`: Holding Backlog and Handling Full Buffers

### 5.1. Unbounded Variant

~~~java
Flux<Event> adapted = events.onBackpressureBuffer();
~~~

This is a snippet in an application with an **Event** type and an **events** source. The operator requests unboundedly from upstream and holds elements that cannot yet be forwarded downstream. If upstream stays continuously fast, data can accumulate long-term. **Do not use this variant blindly for high-rate infinite sources** because of rising heap usage, GC pressure, and **OutOfMemoryError** risk. It also provides no business policy for when backlog exceeds memory capacity.

### 5.2. Bounded Buffer: Overflow Becomes an Error

~~~java
Flux<Event> bounded = events.onBackpressureBuffer(256);
~~~

The buffer holds at most 256 items waiting for downstream (aside from any item currently being processed). When new data cannot be accepted because it is full, Reactor **signals overflow** and requests upstream cancellation. According to the API documentation, the overflow error may be **deferred from delivery downstream until backlog already in the buffer is requested and processed**. Do not confuse "overflow occurs immediately" with "the Subscriber definitely receives `onError` immediately" while buffered items remain to drain.

Variant with callback:

~~~java
Flux<Event> bounded = events.onBackpressureBuffer(
    256,
    discarded -> recordOverflow(discarded)
);
~~~

The **recordOverflow** callback (hypothetical application function) receives the overflowing element; this overload still applies the error policy when out of space. The callback is only for observation/cleanup; it **does not suppress the error** and does not add capacity.

### 5.3. Choosing an Overflow Strategy on a Bounded Buffer

~~~java
Flux<Event> bounded = events.onBackpressureBuffer(
    256,
    removed -> recordEviction(removed),
    BufferOverflowStrategy.DROP_OLDEST
);
~~~

Requires importing **reactor.core.publisher.BufferOverflowStrategy**. The enum's three options:

- **ERROR**: when the buffer is full, triggers an overflow error; the error may be delivered after already-buffered data drains.
- **DROP_LATEST**: drops the **newly arriving element** when the buffer is full; preserves existing backlog.
- **DROP_OLDEST**: drops the **oldest element in the buffer**, appending the new element to the tail; prioritizes fresher data.

| Current Buffer | New Element | Strategy | Buffer After Processing | Dropped Element |
| --- | --- | --- | --- | --- |
| [A, B] | C | **DROP_LATEST** | [A, B] | C |
| [A, B] | C | **DROP_OLDEST** | [B, C] | A |
| [A, B] | C | **ERROR** | Transitions to overflow/error state | C, plus lifecycle cleanup if applicable |

The name **DROP_LATEST** can be misleading: in **BufferOverflowStrategy**, it drops the **newly arriving item when the buffer is full**. **onBackpressureLatest()** is a different operator that actively keeps the **newest item** and replaces the older waiting value.

With the **onBackpressureBuffer(maxSize, callback, strategy)** overload, the callback runs on overflow and receives the element **actually evicted**. Under **DROP_OLDEST**, that can be an older item sitting in the buffer, **not** the new item just emitted by the Publisher. This matters when logging event IDs, computing stats, or releasing resources.

### 5.4. Buffer with TTL

Reactor also provides overloads setting a **TTL (time to live)** alongside an element count limit, such as:

~~~java
Flux<Event> ttlBuffer = events.onBackpressureBuffer(
    Duration.ofSeconds(2),
    256,
    expiredOrEvicted -> recordEviction(expiredOrEvicted)
);
~~~

Here **Duration** comes from **java.time.Duration**. This variant evicts stale data or data pushed out of the buffer by capacity. TTL is useful for time-sensitive telemetry; for business events that must not be lost, expiration is **unsafe** without a compensation/recovery mechanism.

Do not interpret TTL as bounding every buffer across the entire pipeline: other operators, HTTP clients, network buffers, and the emitting source may still maintain their own buffers.

## 6. `onBackpressureDrop`: Dropping Excess Elements Immediately and Observing Directly

~~~java
Flux<Event> tolerant = events
    .onBackpressureDrop(event -> countDropped(event));
~~~

When downstream has no demand left, the operator drops the item and invokes **countDropped** (hypothetical application function). A new request **does not resurrect** already-dropped items; it only lets subsequent items arriving later pass downstream, if the source still emits.

This is a reasonable choice for transient UI frames or dense measurements where keeping every point is unnecessary. Unsuitable for transaction histories, payment commands, mandatory state transitions, or any event where losing one item breaks correctness.

**Demand mechanism to remember:** `onBackpressureDrop` can request **unboundedly from upstream**, then decide locally whether to forward an item downstream or drop it. It is a **data-loss decision point**. Even if the upstream Publisher honors backpressure, placing this operator can cause upstream to emit more items than the final Subscriber requested.

Conceptual example:

~~~text
upstream emits: 1 2 3 4 5
downstream requested: 1 element
onBackpressureDrop:
  deliver: 1
  drop:    2 3 4 5
~~~

This scenario is constructed intentionally in the hands-on example in Section 10. With multiple requests issued while the source keeps emitting, which items are received versus dropped depends on when demand arrives; do not hardcode those numbers across all runtimes.

### Observe Per Item or Only by Count?

The per-element callback can increment counters, record event types, or release resources. In high-throughput streams, **do not write a synchronous log line for every dropped element** because logging itself can become a new bottleneck. Typically use **counters**, sampled logs, or categorized metrics, and alert when drop rates exceed thresholds.

## 7. `onBackpressureLatest`: Keeping the Latest State Update

~~~java
Flux<State> updates = stateChanges
    .onBackpressureLatest();
~~~

If downstream is busy, the operator can hold **one waiting item**. When a new item arrives, the older waiting item is **replaced and discarded**. When downstream requests more, it receives the latest held state.

~~~text
Subscriber receives: A     [demand exhausted]         request(1)
Source keeps emitting:     B       C       D
Pending value:             B  ->   C  ->   D
Discard:                       B       C
Subscriber finally receives:                           D
~~~

**onBackpressureLatest** fits current GPS coordinates, progress percentages, displayed temperatures, or screen states. It does not fit if downstream must process **every intermediate change**. If summing deltas, balances, or state transitions, keeping only the final snapshot is insufficient unless each snapshot **already represents the complete state**.

Distinguish:

- **onBackpressureDrop**: when lacking demand, new items are dropped immediately.
- **onBackpressureLatest**: when lacking demand, the new item **replaces** the old waiting item.
- **BufferOverflowStrategy.DROP_LATEST**: when a **bounded buffer is full**, drops the new item and keeps old items in the buffer.
- **BufferOverflowStrategy.DROP_OLDEST**: when the buffer is full, evicts the oldest item to admit the new item, while still holding **multiple items** depending on buffer capacity.

## 8. `onBackpressureError`: Choosing Failure Over Silent Data Loss

~~~java
Flux<Event> strict = events
    .onBackpressureError();
~~~

If an item arrives when downstream has not granted enough demand, the operator signals an overflow **onError** and cancels upstream. This is the choice when business requirements allow **failing and performing controlled retries**, yet forbid silently dropping data. Proper design is needed to handle errors without duplicating side effects.

Error handling example:

~~~java
Flux<Event> monitored = events
    .onBackpressureError()
    .doOnError(error -> reportFailure(error));
~~~

**reportFailure** is a hypothetical function. **doOnError** only observes; it does not consume or replace the error. If handling via **onErrorResume**, you must have an explicit policy: is discarding the rest of the stream allowed, diverting to another queue, or failing the HTTP request?

Do not mechanically use **onErrorComplete()** or **onErrorResume(error -> Flux.empty())** to "fix" overflow if it effectively hides critical data loss. Overflow is a signal that the system cannot sustain the current rate; turning it into a successful completion can mask lost data.

## 9. Tracking Discarded Data: Local Callbacks, `doOnDiscard`, and `Hooks`

### 9.1. Direct Callbacks of the Overflow Policy

When the cause of removal is a **specific policy**, its direct callback is usually the clearest observation point:

~~~java
Flux<Event> dropAware = events
    .onBackpressureDrop(event -> {
        metrics.incrementDrop();
        cleanupIfNeeded(event);
    });
~~~

Or:

~~~java
Flux<Event> bounded = events.onBackpressureBuffer(
    128,
    discarded -> metrics.incrementBufferEviction(),
    BufferOverflowStrategy.DROP_OLDEST
);
~~~

The **Event** type, **metrics** object, and **cleanupIfNeeded** function are application examples. The callback input is the element removed by the overflow policy. For a buffer with **ERROR** strategy, the callback still observes the overflowing element while the pipeline signals an error per policy.

### 9.2. `doOnDiscard`: Cleaning Up Elements Dropped by Operators on the Normal Path

~~~java
Flux<Integer> observed = Flux.range(1, 5)
    .filter(n -> n % 2 == 0)
    .doOnDiscard(Integer.class,
        n -> System.out.println("discarded " + n));
~~~

Here **filter** rejects odd numbers. **doOnDiscard** is placed **downstream** of the operator to be observed; the handler can apply to upstream operators with discard support. The callback runs on values matching **Integer.class**.

Key characteristics:

1. **doOnDiscard** is a **pipeline-local hook**, not a global configuration.
2. It only works for operators documented with **Discard Support**; not every operator or every Publisher library emits discard events this way.
3. It is also useful when operators with queues/prefetch **clear remaining elements after cancel/error**, not just with **filter**.
4. One element can be observed multiple times when multiple hooks or cleanup points exist in a pipeline. Resource-release functions should be **idempotent** and safe if called repeatedly.
5. **doOnDiscard does not emit discarded items downstream**; it is a side callback for observation/cleanup.

Resource cleanup example:

~~~java
Flux<Payload> flow = source
    .onBackpressureLatest()
    .doOnDiscard(Payload.class, Payload::release);
~~~

**Payload** and **release()** are hypothetical application types/methods requiring an idempotent, lifecycle-correct release mechanism. The **doOnDiscard** callback releases resources of old replaced items. For reference-counted resources like **DataBuffer/ByteBuf**, follow the library's retain/release contract strictly; do not blindly call release on objects you do not own.

**Warning about metrics:** if you attach both **onBackpressureDrop(onDropped)** and **doOnDiscard** for the same element type, one item may be reported in both places. Designate **one primary statistics source** to avoid double-counting data-loss rates.

### 9.3. `Hooks.onNextDropped`: Abnormal Signals, Not a Replacement for `onBackpressureDrop`

~~~java
Hooks.onNextDropped(value -> {
    reportProtocolDrop(value);
});
~~~

This snippet requires importing **reactor.core.publisher.Hooks** and an application function **reportProtocolDrop**. It is a **global hook** for observing **onNext signals that can no longer be validly forwarded**, usually from misbehaving Publishers or signals arriving after stream termination/cancellation. **Hooks.onErrorDropped** handles error signals dropped because no valid Subscriber remains to receive them.

Things to remember:

- **Hooks.onNextDropped** is not an accurate counter for items dropped by **onBackpressureDrop** or **filter**.
- Setting a global hook can affect **every pipeline in the JVM**, including other libraries; governance, log data security, and performance impact must be understood.
- In test environments, if a hook is modified, you must **restore/reset** it within the test lifecycle, e.g. **Hooks.resetOnNextDropped()**. Do not set/reset global hooks ad hoc in a running production app without a unified management strategy.
- **Hooks.onErrorDropped** records errors lacking a valid forwarding path; it does not replace **doOnError** in normal streams.
- Use **doOnDiscard** and overflow callbacks for normal discard paths; use global dropped hooks to hunt down abnormal behavior—do not treat them as the same category of events.

## 10. Runnable Java 17+ Example: DROP, BUFFER, LATEST, DISCARD

The following example chooses synchronous **Flux.range** to demonstrate overflow policies **without depending on sleep or scheduler timing**. A **BaseSubscriber** requests only one item initially; the intermediate backpressure operator requests unboundedly from the source, creating the exact slow-downstream situation. Each stream creates a fresh `BaseSubscriber`, never reusing an old one.

Structure:

~~~text
overflow-discard-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── OverflowDiscardDemo.java
~~~

File **pom.xml** (Reactor Core 3.6.6, Java 17):

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <groupId>example</groupId>
  <artifactId>overflow-discard-demo</artifactId>
  <version>1.0.0</version>

  <properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
  </properties>

  <dependencies>
    <dependency>
      <groupId>io.projectreactor</groupId>
      <artifactId>reactor-core</artifactId>
      <version>3.6.6</version>
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
      </plugin>
    </plugins>
  </build>
</project>
~~~

File **src/main/java/OverflowDiscardDemo.java**:

~~~java
import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.BufferOverflowStrategy;
import reactor.core.publisher.Flux;

public class OverflowDiscardDemo {

    private static BaseSubscriber<Integer> receiveOneInitially() {
        return new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                request(1);
            }

            @Override
            protected void hookOnNext(Integer value) {
                System.out.println("received " + value);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("complete");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println(
                    "error " + error.getClass().getSimpleName()
                );
            }
        };
    }

    public static void main(String[] args) {
        System.out.println("=== DROP ===");

        Flux.range(1, 5)
            .onBackpressureDrop(n ->
                System.out.println("dropped " + n)
            )
            .subscribe(receiveOneInitially());

        System.out.println("=== BUFFER DROP_OLDEST ===");

        BaseSubscriber<Integer> buffered = receiveOneInitially();
        Flux.range(1, 5)
            .onBackpressureBuffer(
                2,
                n -> System.out.println("evicted " + n),
                BufferOverflowStrategy.DROP_OLDEST
            )
            .subscribe(buffered);

        // By now synchronous upstream has emitted 1..5.
        // Subscriber only received 1; buffer holds 4,5.
        buffered.request(2);

        System.out.println("=== LATEST ===");

        BaseSubscriber<Integer> latest = receiveOneInitially();
        Flux.range(1, 5)
            .onBackpressureLatest()
            .subscribe(latest);

        // Value 5 is the latest pending state.
        latest.request(1);

        System.out.println("=== DISCARD (filter) ===");

        Flux.range(1, 5)
            .filter(n -> n % 2 == 0)
            .doOnDiscard(Integer.class,
                n -> System.out.println("discarded " + n)
            )
            .subscribe(
                n -> System.out.println("received " + n),
                error -> System.out.println("error " + error),
                () -> System.out.println("complete")
            );
    }
}
~~~

Run in the directory containing **pom.xml**, with JDK 17+ and Maven:

~~~bash
mvn -q compile exec:java -Dexec.mainClass=OverflowDiscardDemo
~~~

Expected stdout:

~~~text
=== DROP ===
received 1
dropped 2
dropped 3
dropped 4
dropped 5
complete
=== BUFFER DROP_OLDEST ===
received 1
evicted 2
evicted 3
received 4
received 5
complete
=== LATEST ===
received 1
received 5
complete
=== DISCARD (filter) ===
discarded 1
received 2
discarded 3
received 4
discarded 5
complete
~~~

### Why Does the Output Look Like This?

**DROP:** The Subscriber only called `request(1)`, so element 1 is received. **onBackpressureDrop** still requested unboundedly from upstream; when 2–5 arrive without further downstream requests, they enter the dropped callback. Then the source finishes and emits **onComplete**; a terminal signal requires no new demand.

**BUFFER DROP_OLDEST:** The Subscriber receives 1; the two-element queue holds **2,3**. When 4 arrives, the oldest element **2** is evicted; the buffer becomes **3,4**. When 5 arrives, **3** is evicted; the buffer becomes **4,5**. After `subscribe` returns, `buffered.request(2)` allows receiving 4 and 5, followed by completion.

**LATEST:** The Subscriber receives 1, then has no demand left; pending values overwrite one another up to **5**. Calling `latest.request(1)` after the synchronous source finished emitting receives 5 and completion.

**DISCARD:** **filter** accepts only even numbers; odd numbers are rejected and trigger **doOnDiscard**. They are **not** elements lost to overflow. The final lambda Subscriber receives 2 and 4.

To give the example deterministic output, all sources are synchronous. With WebSockets, message brokers, or `Flux` running on schedulers, request and emission points can interleave differently, so **do not copy the example numbers as absolute expectations** for production environments.

## 11. Predicting ERROR Scenarios and Why the Error Can Arrive Later

Suppose we use:

~~~java
BaseSubscriber<Integer> slow = new BaseSubscriber<>() {
    @Override
    protected void hookOnSubscribe(Subscription subscription) {
        request(1);
    }

    @Override
    protected void hookOnNext(Integer n) {
        System.out.println("received " + n);
    }

    @Override
    protected void hookOnError(Throwable error) {
        System.out.println("overflow detected");
    }
};

Flux.range(1, 5)
    .onBackpressureBuffer(1)
    .subscribe(slow);

// Grant more demand to drain the element remaining in the buffer.
slow.request(1);
~~~

This is a Java snippet in a context importing **BaseSubscriber**, **Subscription**, and **Flux**. Expected progression with the synchronous source:

1. Item 1 is emitted immediately for the initial demand.
2. Item 2 sits in the capacity-1 buffer.
3. Item 3 arrives and overflows; upstream is cancelled and the stream is marked with an overflow error.
4. Downstream has not yet received item 2, so forwarding **onError** may wait; after `slow.request(1)`, item 2 is delivered followed by the error.

**Do not claim that as soon as the source overflows, the Subscriber always receives `onError` instantaneously** across every buffer configuration. Draining pending buffered data can affect when downstream observes the error.

With **onBackpressureError()**, there is no backlog to drain in that way: when the source emits beyond demand right at the operator, it signals an overflow error. That is the difference between a **direct fail-fast policy** and **overflow on a buffer holding pending data**.

## 12. Cancellation, Discard, and Resource Lifecycle

When a Subscriber cancels a subscription, operators with prefetch or queues may be holding items not yet delivered downstream. Those data must be cleaned up, even without an overflow event.

Example:

~~~java
Flux<Payload> transformed = source
    .publishOn(scheduler, 32)
    .onBackpressureBuffer(
        64,
        removed -> recordEviction(removed),
        BufferOverflowStrategy.DROP_OLDEST
    )
    .doOnDiscard(Payload.class, Payload::release);
~~~

The snippet above is illustrative with hypothetical **Payload**, scheduler, source, and cleanup functions. **publishOn** has its own prefetch/queue mechanism, while the subsequent buffer has capacity 64. Upon cancellation, elements remaining in queues of discard-supporting operators can be passed to **doOnDiscard** to release resources.

Note where to place the hook:

- **doOnDiscard** applies to **upstream** operators supporting discard relative to the hook's position.
- Placing the hook only **before** the operator that drops elements may miss discards from downstream operators.
- If the hook only accepts **Payload.class**, non-matching types will not run this cleanup.
- If an element was successfully consumed downstream, releasing it is the responsibility of normal processing flow. **doOnDiscard** only supports discarded paths and does not replace overall resource-ownership rules.
- Cleanup must be idempotent because the same object can be observed by multiple cleanup paths if overlapping hooks are designed.

In Netty and WebFlux, reference-counted data types require strict retain/release discipline. Releasing too early can cause use-after-release; failing to release can cause memory leaks. Design the lifecycle path first, and then use hooks to handle discarded branches.

## 13. Production Monitoring: Counting the Right Causes of Data Loss

A good observability setup should distinguish **received**, **successfully processed**, **dropped by policy**, **discarded on cancel**, **overflow errors**, and **late abnormal signals**.

Suggested metric set:

| Metric | Valid Data Source | What to Avoid |
| --- | --- | --- |
| **event_received_total** | Ingestion point before loss policies | Do not count downstream after drops and call it "total input" |
| **event_processed_total** | Final successful processing point | Do not increment merely upon `onNext` arrival |
| **backpressure_drop_total** | **onBackpressureDrop** callback | Do not also add the same item from `doOnDiscard` |
| **buffer_eviction_total** | Overflow/eviction callback with clear strategy | Do not confuse evicted old items with newly arrived items |
| **backpressure_overflow_error_total** | Overflow errors received at the operator boundary | Do not count every business error as overflow |
| **discard_total_by_reason** | `doOnDiscard` at cleanup points, properly categorized | Do not assume every discard is caused by backpressure |
| **late_signal_dropped_total** | `Hooks.onNextDropped`/`Hooks.onErrorDropped` for diagnostics | Do not treat as the count of `onBackpressureDrop` elements |

For drop rates or percentages, clearly define the **denominator** and measurement boundary: items received from source or items reaching the operator? A pipeline with multiple operators may drop the same item or transform element counts, so blindly summing independent counters does not accurately reflect lost business items.

Useful log/tracing context: pipeline name, source, event type, overflow strategy, buffer limit, timestamp, consumer group, request/correlation ID, and cancellation state. Avoid logging full sensitive payloads or large data on every drop.

A metrics callback should be **fast, non-blocking**, and free of complex business side effects. For high-rate workloads, use counters or suitable metrics queues; never call HTTP services or write synchronously to a database from an overflow callback.

## 14. Application in Spring WebFlux

Suppose an endpoint creates a continuous event stream (such as Server-Sent Events). If only the newest state snapshot is needed:

~~~java
@GetMapping(
    value = "/status/stream",
    produces = MediaType.TEXT_EVENT_STREAM_VALUE
)
public Flux<ServerSentEvent<Status>> statusStream() {
    return statusFeed()
        .onBackpressureLatest()
        .doOnDiscard(Status.class, this::cleanupDroppedStatus)
        .map(status -> ServerSentEvent.builder(status).build());
}
~~~

This is a snippet inside a Spring controller where **Status**, **statusFeed()**, and **cleanupDroppedStatus** are hypothetical application components. The return type remains **Flux<ServerSentEvent<Status>>**; Spring WebFlux will subscribe when handling the request. Do not manually call **subscribe()** inside the controller just to trigger the stream, as that detaches the task from the HTTP request lifecycle.

**Be careful:** this example is only suitable when **Status** is a replaceable snapshot and dropping intermediate snapshots causes no harm. If **Status** represents incremental deltas, dropping an item can put the client out of sync. Emit full snapshots or implement a replay/resync mechanism.

For data where every item must be preserved, a pipeline like:

~~~java
Flux<Event> critical = eventSource()
    .onBackpressureBuffer(256);
~~~

does not solve reliability on its own. An in-memory buffer of 256 can still overflow; cancellation, process errors, and crashes can lose data. Think in terms of **durable brokers/queues**, acknowledgments, offset persistence, controlled retries, and idempotent processing. Do not substitute those mechanisms by raising `maxSize` indefinitely.

### Tuning the System Before Actively Dropping Data

Options to check first:

1. **Does the source honor demand?** If so, preserve end-to-end backpressure instead of unnecessarily adding an operator that requests unboundedly.
2. **Is downstream concurrency appropriate?** For independent I/O tasks, **flatMap(mapper, concurrency)** can improve throughput while ensuring connection/resource bounds.
3. **Is anything blocking on the event loop?** Blocking I/O threads creates artificial downstream slowness; review non-blocking design or dedicated schedulers for blocking work.
4. **Are intermediate prefetch/queues too large?** Operators like **publishOn**, **flatMap**, and **buffer** create their own queues. Evaluate the entire pipeline, not just a single `maxSize`.
5. **What is the business policy for losing an item?** If loss is unacceptable, fail or persist durably—do not use DROP/LATEST just to make metrics look pretty.

## 15. Common Mistakes and Fixes

| Symptom or Misconception | Root Cause / Correct Understanding |
| --- | --- |
| "Source honors requests so `onBackpressureDrop` will never drop" | The operator can proactively request unboundedly from the source and manage downstream demand, so drops still occur at the operator. |
| "Default `onBackpressureBuffer()` is safe" | The unbounded form can grow memory indefinitely with fast sources; set appropriate limits and explicit policies. |
| "`BufferOverflowStrategy.DROP_LATEST` keeps the newest item" | With a full buffer, it **drops the new item**; to keep only the newest pending item for downstream, use **onBackpressureLatest()**. |
| "`BufferOverflowStrategy.DROP_OLDEST` always reports the newly arrived item" | The overflow callback receives the **actually evicted item**, which may be an old item in the buffer. |
| "When `onBackpressureBuffer` is full, the Subscriber always sees the error immediately" | Some overloads defer delivering `onError` until the backlog drains. |
| "`onBackpressureLatest` works for every event" | It loses intermediate events. Suitable only when each new item can functionally replace old items. |
| "`Hooks.onNextDropped` will count `onBackpressureDrop`" | Global hook is for abnormal signals; use operator callbacks and **doOnDiscard** for normal discards. |
| "`doOnDiscard` always runs for every operator" | Only operators with documented **Discard Support**; the local hook affects upstream operators. |
| "Every `doOnDiscard` call is a distinct business event" | The same object may be observed at multiple points; avoid double-counting and make cleanup idempotent. |
| "The drop callback is a good place to call a blocking logging service" | The callback can run on a hot signal path. Use fast metrics/sampled logs and avoid blocking. |
| "`cancel` means all buffered elements were processed" | Cancelling can discard pending items, triggering discards; it is not a successful `onComplete`. |
| "Putting `onErrorComplete` after `onBackpressureError` is safe" | It can hide overflow, causing critical sources to lose data without the caller knowing. |
| "A large buffer fixes a producer that is too fast" | It only absorbs temporary backlogs; if long-term input rate exceeds output rate, the queue will fill or cause memory pressure. |

## 16. Self-Check and Exercises

**Question 1.** Downstream requests one element; upstream synchronously emits 1,2,3,4 through **onBackpressureDrop**. What can the result be?  
**Answer:** Receives 1, drops 2–4, then completes. Key point to recognize: the drop operator proactively requests more data than downstream.

**Question 2.** A capacity-2 buffer currently holds [A,B], and C arrives while downstream has no demand. How do **DROP_LATEST** and **DROP_OLDEST** differ?  
**Answer:** `DROP_LATEST` drops C, keeping [A,B]; `DROP_OLDEST` drops A, keeping [B,C].

**Question 3.** For a GPS stream needing only current location, what should you choose?  
**Answer:** **onBackpressureLatest()** can fit if each value is a full position capable of replacing older positions.

**Question 4.** For a transactional stream requiring complete processing, should `onBackpressureDrop` be used?  
**Answer:** No. Preserve data via source throttling, durable queues, or explicit failure and retries per business contract.

**Question 5.** What is the core difference between **doOnDiscard** and **Hooks.onNextDropped**?  
**Answer:** `doOnDiscard` observes supporting operators intentionally discarding data during normal flow/cancel/error; `Hooks.onNextDropped` is a global hook for abnormal `onNext` signals that cannot be forwarded, usually due to protocol violations or late arrival.

**Question 6.** When using both the **onBackpressureDrop** callback and **doOnDiscard** for the same item, should both be added into one "lost events" counter?  
**Answer:** Do not double-count; keep one primary metrics source and one separate cleanup source when needed.

**Hands-on A:** In the Section 10 program, change **DROP_OLDEST** to **DROP_LATEST**. Predict the two pending items after emitting 1–5 with buffer 2 and initial downstream `request(1)`. **Answer:** the buffer keeps 2,3; items 4 and 5 are dropped. After `request(2)`, the Subscriber receives 2,3 and completes.

**Hands-on B:** Change the **LATEST** section to **onBackpressureError()**, keeping the initial Subscriber requesting only `request(1)`. Observe the stream stopping via the **hookOnError** callback when an element exceeds demand; verify there is no `onComplete`.

**Hands-on C:** Add **doOnDiscard** after **onBackpressureLatest** and count replaced intermediate items. Compare that counter with the **onBackpressureDrop** callback in another example. Conclude why the two counts should not be mixed without a clear strategy.

## 17. Implementation Principles

Choose a policy by asking **"when unable to keep up, which items are allowed to be lost and how do we know they were lost?"**:

- **Zero loss tolerated**: prefer demand-aware sources and durable queues; if termination is required, use **onBackpressureError** or bounded buffers with explicit error handling.
- **Individual excess events droppable**: **onBackpressureDrop** with counting/diagnostic callbacks.
- **Only newest state needed**: **onBackpressureLatest** paired with **doOnDiscard** to clean up replaced resources.
- **Bounded backlog desired**: **onBackpressureBuffer(maxSize, ...)**, explicitly choosing **DROP_LATEST**, **DROP_OLDEST**, or **ERROR**, and measure evictions.
- **Need to clean up operator-discarded items**: **doOnDiscard** at the right position and type; check Discard Support docs.
- **Need to diagnose abnormal signals**: **Hooks.onNextDropped/Hooks.onErrorDropped** under centralized management, not as a normal drop counter.

Finally, treat **backpressure, memory, latency, data-loss rate, errors, and cancellation** as linked metrics. A pipeline reporting no errors may still be dropping items; a pipeline dropping no items may be accumulating memory. Only when data policies and observability are designed together can you evaluate whether the system behaves correctly.

## 18. References

- Project Reactor **Flux API**, **onBackpressureBuffer / onBackpressureDrop / onBackpressureLatest / onBackpressureError** group: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html
- Project Reactor **BufferOverflowStrategy API**: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BufferOverflowStrategy.html
- Project Reactor **Hooks API**: https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Hooks.html
- Reactor Reference Guide, **Operator Choice**: https://projectreactor.io/docs/core/release/reference/apdx-operatorChoice.html
- Reactor Reference Guide, **Using Global Hooks and doOnDiscard**: https://projectreactor.io/docs/core/release/reference/advancedFeatures/hooks.html
- Reactive Streams Specification for the JVM: https://github.com/reactive-streams/reactive-streams-jvm
