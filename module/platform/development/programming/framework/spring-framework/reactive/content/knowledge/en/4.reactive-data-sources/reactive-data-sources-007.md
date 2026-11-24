# Synchronous Element-by-Element Emission with Flux.generate

**Context:** Spring Framework Reactive → Creating Data Sources.

`Flux.generate(...)` in Project Reactor is used to **programmatically create a sequence of elements turn by turn, synchronously, from a generator function**. Each time downstream has demand to receive data, Reactor can invoke the generator to produce the next signal. The generator uses `SynchronousSink<T>` to emit **at most one `T` element per invocation**; at the same time, it can signal completion or an error.

The key point is **one generation turn → at most one `onNext`**. When you need to compute the next element based on previous state, `generate` is especially useful; when you only need consecutive integers or to traverse a collection, simpler factories like `Flux.range` and `Flux.fromIterable` are usually easier to read.

## 1. What Does “Synchronous Element-by-Element Emission” Mean?

In `Flux.generate`, the generator function is invoked **synchronously** within the subscription/request processing chain (unless external scheduler coordination is applied). The generator must decide the signal for the current turn **before returning**; it does not register a callback to emit via `SynchronousSink` at an arbitrary future time.

Contrast two groups of concepts:

- **Synchronous:** the callback produces a signal immediately within the current call. It can run on the thread executing the subscription/request.
- **One by one:** each turn has only **0 or 1 `next`**, where 0 is valid only if that turn ends with `complete` or `error`.
- **Backpressure:** downstream requests a number of elements via `request(n)`. The generator is driven by demand instead of having to emit an entire large list upfront.
- **Not synonymous with non-blocking:** if code inside the callback performs blocking I/O, the thread running the callback **is still blocked**. `generate` itself does not turn a synchronous database query or `Thread.sleep` into non-blocking.
- **Not synonymous with a new thread:** `Flux.generate` does not by default spawn a separate thread per item or execute in parallel.

Conceptual model:

```text
Assembly (creating the Flux description)
        |
        v
Subscriber subscribes, receives Subscription
        |
        v
downstream request(1)
        |
        v
generator(state, sink)
        |           |
        |           +-- sink.next(item) -- at most once
        |           +-- optional sink.complete() / sink.error(...)
        v
return next state
        |
        v
wait for next demand / termination / cancellation
```

This is a conceptual model. In a stream with `map`, `buffer`, `publishOn`, or other operators, requests may be coalesced/transformed, so do not mechanically deduce that “each final element corresponds to exactly one `request(1)` at the head of the chain”.

## 2. Signal Contract of SynchronousSink

`Flux.generate` uses `SynchronousSink<T>`. Within **each invocation** of the generator:

| Signal | Valid Count | Meaning |
|---|---:|---|
| `sink.next(value)` | **At most 1** | Emits a non-null `T` element |
| `sink.complete()` | 0 or 1, terminates stream | Successful termination |
| `sink.error(throwable)` | 0 or 1, terminates stream | Error termination |

There are three common patterns:

```java
// Valid: produce one element, continue on next turn.
sink.next(item);

// Valid: produce no element, stop successfully.
sink.complete();

// Valid: emit the final element and complete immediately in the same turn.
sink.next(lastItem);
sink.complete();

// Valid: report error and stop, emitting no element in that turn.
sink.error(new IllegalArgumentException("bad input"));
```

These are **illustrative snippets** placed inside a callback with suitable `sink` and `item` variables; they do not run standalone.

**Must not** call `next` twice in one turn:

```java
// WRONG: one generator invocation must not emit two items.
sink.next("A");
sink.next("B");
```

Reactor will report an error for violating the one-`next`-per-turn rule (for example, `IllegalStateException` about multiple `onNext` calls). Do not use a loop to call `sink.next(...)` multiple times inside the **same callback**.

**Must not** return without emitting any signal:

```java
// WRONG: this generator turn has no next, complete, or error.
Flux.generate(sink -> {
    // did nothing
});
```

If the callback returns without emitting a value **and** without terminating, Reactor reports an error, typically `IllegalStateException` with the message “The generator didn't call any of the SynchronousSink method”. If there is no element on the last turn, explicitly call `sink.complete()` or `sink.error(...)`.

`null` is not a valid value for `sink.next(null)`; it causes an error. If the source cannot find the next item, emit `complete` or handle the situation per the business contract instead of sending null.

### Distinguishing “No Item” from “Item Then Complete”

`sink.complete()` can be called:

1. **Without `next`:** the generation session ends without producing another item.
2. **After one `next` in the same callback:** the final item is emitted and then the stream terminates.

After a terminal signal, do not call `next`/`complete`/`error` again. A Flux can emit many items **across multiple turns**, even though each callback is limited to at most one item.

## 3. Three Overloads of Flux.generate

Conceptual signatures in Reactor:

```java
// 1. No explicit state management:
Flux.generate(Consumer<SynchronousSink<T>> generator);

// 2. A separate state per subscription:
Flux.generate(
        Callable<S> stateSupplier,
        BiFunction<S, SynchronousSink<T>, S> generator);

// 3. Plus state/resource cleanup on completion or cancellation:
Flux.generate(
        Callable<S> stateSupplier,
        BiFunction<S, SynchronousSink<T>, S> generator,
        Consumer<? super S> stateConsumer);
```

These are **illustrative signatures** for reading the API, not Java statements to copy verbatim; `T` and `S` are generic type parameters.

- `T`: the data type emitted by the Flux.
- `S`: the generator's **internal state** type; may differ from `T`.
- `stateSupplier`: runs for **each subscriber**, creating an independent initial state.
- `generator`: receives `state` and `sink`, emits signals for the current turn, and **returns the state to use on the next turn**.
- `stateConsumer`: receives the final state to clean up resources when the sequence terminates or is cancelled.

Do not place shared mutable state outside `stateSupplier` if you want each subscription to run independently. Each subscriber must have its own state session to avoid data leaks, contention, and unpredictable results when multiple HTTP requests subscribe concurrently.

## 4. First Example: One Element per Turn

Suppose we want to emit three integers 1, 2, 3:

```java
Flux<Integer> numbers = Flux.generate(
        () -> 1,
        (state, sink) -> {
            sink.next(state);
            if (state == 3) {
                sink.complete();
            }
            return state + 1;
        });
```

This is a **snippet** inside code that has imported `reactor.core.publisher.Flux`.

When there is sufficient demand, the signal flow is:

```text
Turn 1: state=1 → next(1)            → new state=2
Turn 2: state=2 → next(2)            → new state=3
Turn 3: state=3 → next(3), complete() → stop
Downstream receives: 1, 2, 3, onComplete
```

A few points to read carefully:

- `() -> 1` is the supplier initializing the `Integer` state; called upon subscribe.
- The callback `(state, sink) -> {...}` is a function applied sequentially as demand arrives.
- `sink.next(state)` emits **exactly one number** per turn.
- When `state == 3`, you can emit the final item and call `complete()` in the same callback.
- `return state + 1` supplies the next state. Once completed, the new state does not lead to a fourth generation turn.

For the simple problem of “emit numbers from 1 to 3”, `Flux.range(1, 3)` is shorter and clearer. `generate` becomes useful when producing the next item depends on state logic, state transition conditions, or resources that need management.

### Variant: Completing Only on the Next Turn

```java
Flux<Integer> numbers = Flux.generate(
        () -> 1,
        (state, sink) -> {
            if (state > 3) {
                sink.complete();
            } else {
                sink.next(state);
            }
            return state + 1;
        });
```

This variant emits 1, 2, 3 and then, **when invoked for one more turn**, sends `complete()`. An important difference from the variant above: if downstream only requests exactly three items, there might not be a fourth turn to emit the completion signal. When you know the **last item** right inside the callback emitting that item, calling `sink.complete()` in the same turn usually helps complete promptly.

Do not spend an extra turn just to “check whether it is finished” if the contract requires ending right after the last item and you can already know it.

## 5. Standalone Runnable Java 17+ Program: Observing Demand and Cleanup

The following example demonstrates **creating a Flux**, **subscribing without requesting yet**, **requesting in batches**, **emitting one item/turn**, and **cleaning up state**. This is a complete Java program using Reactor Core, **without Spring Boot**, runnable with Maven.

Directory structure:

```text
generate-demo/
├── pom.xml
└── src/main/java/demo/GenerateDemo.java
```

Contents of `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>generate-demo</artifactId>
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

File `src/main/java/demo/GenerateDemo.java`:

```java
package demo;

import org.reactivestreams.Subscription;
import reactor.core.publisher.BaseSubscriber;
import reactor.core.publisher.Flux;

public class GenerateDemo {

    private static Flux<String> generateValues() {
        return Flux.generate(
                () -> 1,
                (state, sink) -> {
                    sink.next("value-" + state);

                    if (state == 3) {
                        sink.complete();
                    }
                    return state + 1;
                },
                lastState -> System.out.println("cleanup=" + lastState)
        );
    }

    public static void main(String[] args) {
        BaseSubscriber<String> subscriber = new BaseSubscriber<>() {
            @Override
            protected void hookOnSubscribe(Subscription subscription) {
                System.out.println("subscribed");
                // No request yet, so the generator has not produced elements.
            }

            @Override
            protected void hookOnNext(String item) {
                System.out.println("next=" + item);
            }

            @Override
            protected void hookOnComplete() {
                System.out.println("complete");
            }

            @Override
            protected void hookOnError(Throwable error) {
                System.out.println("error=" + error.getClass().getSimpleName());
            }
        };

        generateValues().subscribe(subscriber);
        System.out.println("request(1)");
        subscriber.request(1);
        System.out.println("request(2)");
        subscriber.request(2);
    }
}
```

Run from the directory containing `pom.xml`, with JDK 17+ and Maven able to download Reactor dependencies:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.GenerateDemo
```

**Expected standard output of the program** (excluding Maven-specific messages):

```text
subscribed
request(1)
next=value-1
request(2)
next=value-2
next=value-3
complete
cleanup=4
```

Why is this order deterministic?

1. `BaseSubscriber` overrides `hookOnSubscribe` and does **not** request immediately; therefore subscribing only prints `subscribed`.
2. `subscriber.request(1)` grants demand for one item. The synchronous source runs the generator once, emitting `value-1`.
3. `subscriber.request(2)` grants two more items. The generator emits `value-2` and then `value-3` in **two separate invocations**.
4. When producing `value-3`, the callback calls `sink.complete()`, so the subscriber receives `onComplete` right on the final turn.
5. The callback returns state `4`; `stateConsumer` receives the final state for cleanup. The demo prints `cleanup=4`. In real applications, this callback closes resources or records cleanup instead of only printing to the console.

**About `BaseSubscriber`:** by default, if `hookOnSubscribe` is not overridden, it requests `Long.MAX_VALUE` (unbounded). The example overrides it to supply demand manually in batches. The request calls in the example execute on the main thread, the source is synchronous, and no `publishOn` is added, so no I/O or auxiliary threads affect output order.

`BaseSubscriber` helps visualize backpressure; in **Spring WebFlux controllers**, you normally return `Flux` and let the framework/downstream subscriber manage subscription and demand. Do not call `subscribe` yourself just to “start the Flux” and ignore the HTTP response.

## 6. Internal State: Turning One Call Pattern into Sequential Items

`Flux.generate` is typically used when producing the next item depends on the previous result.

### 6.1. Immutable State

With `Integer` as in the example, each turn returns a new state:

```java
Flux<Integer> squares = Flux.generate(
        () -> 1,
        (state, sink) -> {
            sink.next(state * state);
            if (state == 4) {
                sink.complete();
            }
            return state + 1;
        });
```

Result when subscribed with enough demand: **1, 4, 9, 16**, then `onComplete`. `Integer` here is the state type; `sink` emits an `Integer` which is the square of the state. You can choose a state type different from the emitted data type, such as `S = Position`, `T = OrderEvent`.

### 6.2. Mutable State

You can also store state in a mutable object:

```java
Flux<String> labels = Flux.generate(
        () -> new java.util.concurrent.atomic.AtomicInteger(1),
        (counter, sink) -> {
            int value = counter.getAndIncrement();
            sink.next("item-" + value);
            if (value == 3) {
                sink.complete();
            }
            return counter;
        });
```

This is a snippet. Each subscription receives **a new `AtomicInteger`** from the supplier. You do not need `AtomicInteger` solely to guard against concurrent mutation when the generator runs sequentially; a simple state class or immutable integer works too. What must be preserved is **never sharing a single mutable state across multiple subscribers**.

**Bad example: shared state outside the callback:**

```java
// DO NOT do this if each subscription must start independently from 1.
AtomicInteger shared = new AtomicInteger(1);
Flux<Integer> wrong = Flux.generate(
        sink -> sink.next(shared.getAndIncrement()));
```

This snippet can run forever if given unbounded demand, and subscribers sharing `shared` cause each subscription to observe different positions. There is no `complete`/`error` branch; infinite generation is only appropriate when intentional and demand/cancellation are controlled.

### 6.3. Useful Example: Per-Subscriber Stateful Iterator

```java
Flux<String> colors = Flux.generate(
        () -> java.util.List.of("red", "green", "blue").iterator(),
        (iterator, sink) -> {
            if (iterator.hasNext()) {
                sink.next(iterator.next());
            } else {
                sink.complete();
            }
            return iterator;
        });
```

This source emits exactly three strings when requested enough times; each subscriber gets its own iterator. Still, with an existing `List`, **`Flux.fromIterable(List.of(...))` is clearer**. Use `generate` when the next element requires a state machine or custom algorithm.

The branch with no remaining elements simply calls `sink.complete()`. Do not call `sink.next(null)`, do not busy-spin until the iterator has a new item, and do not call `iterator.next()` after exhaustion.

## 7. Completing and Erroring by State

Choose the right termination point so the stream neither hangs nor emits extra items.

### 7.1. Completing When a Condition Is Met

```java
Flux<String> countdown = Flux.generate(
        () -> 3,
        (remaining, sink) -> {
            sink.next("T-" + remaining);
            if (remaining == 1) {
                sink.complete();
            }
            return remaining - 1;
        });
```

Result: `T-3`, `T-2`, `T-1`, then completion. If `complete` were not called at `remaining == 1`, the generator could continue to 0, -1... when more demand arrives.

### 7.2. Reporting an Error Instead of Emitting Invalid Data

```java
Flux<Integer> checked = Flux.generate(
        () -> 0,
        (state, sink) -> {
            if (state == 2) {
                sink.error(new IllegalStateException("state 2 is invalid"));
            } else {
                sink.next(state);
            }
            return state + 1;
        });
```

Result when subscribed with demand: emits `0`, `1`, then `onError(IllegalStateException)`. There is no `onComplete` after `onError`. When the generator throws an exception, Reactor also turns it into a stream error (except for fatal exceptions per the library contract), but `sink.error(...)` expresses business error branches explicitly.

### 7.3. Empty Sequence

```java
Flux<String> noItems = Flux.generate(sink -> sink.complete());
```

This is a Flux that completes without emitting items. For a fixed empty source, `Flux.empty()` is simpler. `generate` is useful when deciding whether the stream is empty or has data **depends on state checked at subscription**.

## 8. Backpressure: Downstream Determines Generation Pace

At the Reactive Streams level, `request(n)` expresses demand to receive `n` more elements, while `cancel()` stops the subscription. `Flux.generate` fits backpressure naturally because one invocation creates at most one item; it can pause between turns when no demand remains.

Example from the standalone run:

```text
subscribe
  └── no request yet        → 0 generation turns
request(1)
  └── generator turn 1      → next(value-1)
request(2)
  ├── generator turn 2      → next(value-2)
  └── generator turn 3      → next(value-3), complete
```

Note:

- **`request(2)` does not mean the callback is called once and allowed to call `next` twice.** Reactor invokes the generator for separate turns, each with at most one `next`.
- If code uses `subscribe(System.out::println)` or `blockLast()`, downstream normally requests an unbounded amount. With an **infinite and fast-computing** generator, the stream can run continuously, burning CPU and occupying a thread.
- Operators such as `limitRate`, `buffer`, and `publishOn` can reshape how demand propagates upstream (coalescing/batching/prefetch). Analyze demand at the actual position of `Flux.generate`, rather than inferring directly from how many items an HTTP client receives.
- **Backpressure does not automatically make blocking I/O non-blocking**. If one generator turn waits on a database for 3 seconds, the thread running the callback is still held for 3 seconds.

### Cancellation Before Completion

Example taking only two items:

```java
Flux<Integer> upstream = Flux.generate(
        () -> 1,
        (state, sink) -> {
            sink.next(state);
            return state + 1;
        });

Flux<Integer> firstTwo = upstream.take(2);
```

Once downstream consumes two items, `take(2)` completes the result and cancels the upstream subscription; the generator does not need to emit number 3. When holding resources or mutable state, use the overload with `stateConsumer` to clean up on cancel.

**Do not rely solely on `sink.complete()` to clean up resources** if a subscriber can cancel early. Resources must be released across complete, error, and cancel alike.

## 9. stateConsumer: Cleaning Up State on Complete, Error, or Cancel

Three-argument overload:

```java
Flux<Integer> stream = Flux.generate(
        () -> new CounterState(0),      // per-subscriber state
        (state, sink) -> {              // emits at most one item
            if (state.current >= 10) {
                sink.complete();
            } else {
                sink.next(state.current++);
            }
            return state;
        },
        state -> state.close());        // cleanup
```

This is a **snippet**; `CounterState` is a hypothetical class with `int current` and method `close()`. It demonstrates the cleanup API, not a Java program that can run on its own.

`stateConsumer` is invoked by Reactor when the generator completes, errors, or downstream cancels. Its parameter is the final state returned by the generator (or the current state at cancellation time). This is the right place to close closeable iterators/resources, release special buffers, or record cleanup.

Example state managing a resource following standard Java conventions:

```java
final class ResourceState implements AutoCloseable {
    private int next = 1;
    private boolean closed;

    int nextValue() {
        return next++;
    }

    @Override
    public void close() {
        closed = true;
    }

    boolean isClosed() {
        return closed;
    }
}
```

When using this class in the same project:

```java
Flux<Integer> generated = Flux.generate(
        ResourceState::new,
        (state, sink) -> {
            int current = state.nextValue();
            sink.next(current);
            if (current == 3) {
                sink.complete();
            }
            return state;
        },
        ResourceState::close
);
```

Both snippets above must live in a project with Reactor and `Flux` imported; `ResourceState` is a valid standalone class. After the source completes or is cancelled, Reactor invokes cleanup on the corresponding state.

**Important:** `generate` allows state to be `null` in the API, but if you use a cleanup method reference like `ResourceState::close`, you must ensure the supplier returns a valid resource, or check for null in cleanup. For external resources, also note that cleanup may be triggered from the thread executing subscription/cancellation; do not assume it always runs on the same fixed thread.

If your problem is **managing a resource for a stream** and the logic is mainly acquire/use/cleanup, `Flux.using` or `Flux.usingWhen` may be more suitable, especially with asynchronous cleanup. `stateConsumer` fits when the state/resource is directly part of the synchronous generator algorithm.

## 10. When to Use generate Instead of Other Factories?

| Need | Often Suitable Choice | Reason |
|---|---|---|
| An existing list | `Flux.fromIterable(items)` | No need to write a state machine just to iterate |
| Finite consecutive integer sequence | `Flux.range(start, count)` | Concise, easy to read |
| A few fixed values | `Flux.just(a, b, c)` | No generator needed |
| A synchronous, state-based algorithm generating the next element | **`Flux.generate`** | One callback/one item, per-subscriber state |
| Integrating a callback API emitting multiple events, possibly multi-threaded | `Flux.create` or `Sinks.Many` depending on design | Emission mechanism suited for asynchronous sources |
| Callback emitting events from a single dedicated producer thread | `Flux.push` may fit | Single-producer push API; must manage events and lifecycle |
| Clock-based ticks | `Flux.interval` | Scheduler emits time-based events |
| Single result or completion | `Mono`, `Mono.fromCallable`, `Mono.defer` as appropriate | 0..1 contract instead of multiple items |

### Comparing generate and create

`Flux.generate` receives **`SynchronousSink`**; you only use the sink within the scope of the **current callback**. Do not store the sink in a field and call `next` after the callback returns.

`Flux.create` receives **`FluxSink`**, designed to bridge asynchronous event-emitting APIs like listeners/callbacks and able to emit multiple signals. When using an external push source, you must manage backpressure/overflow, callback cleanup, and concurrency properly.

```java
// Use generate when items are computed immediately from state:
Flux<Integer> calculated = Flux.generate(
        () -> 1,
        (state, sink) -> {
            sink.next(state * 10);
            if (state == 3) {
                sink.complete();
            }
            return state + 1;
        });

// Conceptual example of create when having an asynchronous listener API:
// Flux.create(sink -> {
//     EventListener listener = event -> sink.next(event);
//     source.register(listener);
//     sink.onDispose(() -> source.unregister(listener));
// });
```

The `Flux.create` block below is **commented pseudocode**; `EventListener` and `source` only illustrate the callback pattern and must be declared with real APIs. Using `create` does not automatically spawn new threads or guarantee non-blocking behavior.

## 11. Connection to Spring WebFlux

When building a WebFlux endpoint, a service/controller can return a `Flux<T>` produced by `generate`. WebFlux manages the subscription and converts elements into an HTTP response according to the HTTP codec and media type.

Example of **a Java 17 controller used in a Spring Boot project with `spring-boot-starter-webflux`**:

```java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import reactor.core.publisher.Flux;

@RestController
public class SequenceController {

    @GetMapping("/squares")
    public Flux<Integer> squares() {
        return Flux.generate(
                () -> 1,
                (state, sink) -> {
                    sink.next(state * state);
                    if (state == 5) {
                        sink.complete();
                    }
                    return state + 1;
                });
    }
}
```

When the application runs normally, `GET /squares` returns data corresponding to elements **1, 4, 9, 16, 25**, encoded by Spring into the response (typically a JSON array if the client requests JSON). This class snippet **is not a standalone Spring Boot application**: it requires a main application, dependencies, server, and proper configuration.

Processing flow:

1. WebFlux calls `squares()` and receives a `Flux<Integer>` object.
2. The framework subscribes when processing the response; the generator starts generating as downstream has demand.
3. Each invocation emits at most one number; when state equals 5, `sink.complete()` signals end of data.
4. The JSON encoder/HTTP response finishes after the Flux sends a successful terminal signal.

### Is generate's Synchronous Nature a Problem for the Event Loop?

Not all synchronous processing is bad. Small multiplications or very fast state transitions are usually fine. However, generator code **can run on latency-sensitive WebFlux threads**; avoid doing the following in the callback:

- `Thread.sleep(...)`, waiting on synchronous network/file I/O, or calling blocking JDBC.
- Busy-wait loops or prolonged heavy CPU computation.
- Running an unbounded loop trying to emit thousands of items in **one callback**.
- Calling `subscribe()` on another publisher and keeping `SynchronousSink` to emit later in an asynchronous callback.

If you genuinely need to connect a blocking I/O source, consider a non-blocking driver instead. When forced to use a blocking library, intentionally isolate it on `Schedulers.boundedElastic()` and control pools, timeouts, and cancellation; switching schedulers does not turn that I/O into non-blocking. For asynchronous callback sources, move to an appropriate `Flux.create`/`Sinks` model.

### Does SSE Automatically “Emit Slowly” Because of generate?

No. `Flux.generate` can emit all items in a very short span when there is demand. Adding `produces = MediaType.TEXT_EVENT_STREAM_VALUE` selects the format/streaming mode, **not automatically adding delays** between items. If periodic emission is required, use `Flux.interval` or time operators designed for that purpose, with cancellation and backpressure strategies.

## 12. Common Pitfalls

### Mistake 1 — Calling next Multiple Times in the Same Callback

```java
// Wrong: this callback calls next twice.
Flux.<Integer>generate(sink -> {
    sink.next(1);
    sink.next(2);
});
```

**Fix:** store position in state; let Reactor call the callback next time when there is demand, or use `Flux.fromIterable`/`Flux.range` for pre-existing data.

### Mistake 2 — Emitting No Signal at All

```java
// Wrong: no next/complete/error signal.
Flux.generate(sink -> {
    if (false) {
        sink.next("never");
    }
});
```

**Fix:** every callback must emit one item or a terminal signal. If empty, `sink.complete()`.

### Mistake 3 — Using null as an End-of-Data Signal

```java
// Wrong: Reactor does not allow emitting null.
Flux.<String>generate(sink -> sink.next(null));
```

**Fix:** call `sink.complete()` when out of data. With legacy APIs returning nullable values, check for null before emitting.

### Mistake 4 — Omitting a Termination Condition

```java
// Potentially infinite: every new demand creates another item.
Flux<Integer> endless = Flux.generate(
        () -> 0,
        (state, sink) -> {
            sink.next(state);
            return state + 1;
        });
```

With an unbounded subscription, the callback can run for a long time and consume CPU. **Fix:** define a completion condition, bound with `take(n)` when appropriate, and monitor overflow/numeric type limits. Do not increment `int` endlessly if integer overflow has business significance.

### Mistake 5 — Initializing Shared Mutable State

```java
// Wrong when expecting each subscription to start from its own state:
java.util.concurrent.atomic.AtomicInteger global =
        new java.util.concurrent.atomic.AtomicInteger(0);
Flux<Integer> sharedState = Flux.generate(
        sink -> sink.next(global.incrementAndGet()));
```

**Fix:** use the overload with `stateSupplier` that creates fresh state per subscription.

### Mistake 6 — Thinking generate Is Automatically Async or Non-blocking

```java
// WRONG snippet for the event loop: calling blocking I/O inside generator.
Flux<String> blockingSource = Flux.generate(sink -> {
    String value = legacyJdbcQuery();
    sink.next(value);
});
```

`legacyJdbcQuery()` is assumed to be a blocking API; the snippet neither declares the method nor has termination. Moving the task to a scheduler when necessary only addresses which thread is blocked. If code truly needs to emit multiple events from an asynchronous source, `generate` is not the right callback bridge.

### Mistake 7 — Calling SynchronousSink After the Callback Has Returned

```java
// Contract violation: async callback holds sink to emit later.
Flux<String> wrong = Flux.generate(sink -> {
    someAsyncApi(value -> sink.next(value));
});
```

`someAsyncApi` is pseudocode, not an existing method. The `generate` callback returns without emitting a signal, and the code held the sink beyond its valid scope. **Fix:** bridge listener/callback sources via `Flux.create` or `Sinks`, managing unsubscribe and backpressure.

### Mistake 8 — Completing Only When Requested for One Extra Turn

If the generator knows it just emitted the last element but did not call `sink.complete()`, downstream may wait for the terminal signal until the next turn. When you know the endpoint right inside the current callback, terminate in the same turn if the contract allows.

### Mistake 9 — Failing to Clean Up State on Early Cancel

A source can be stopped by `take`, timeout, HTTP connection close, or a subscriber calling `cancel()`. Do not place cleanup only after `sink.complete()` inside the generator body. Use `stateConsumer` or an appropriate resource-management operator.

### Mistake 10 — Assuming “One Callback = One Thread”

Reactor can run many callback turns on the same thread. The scheduler and how downstream subscribes determine the execution context. `generate` does not automatically parallelize turns and a `SynchronousSink` should not be shared across multiple threads.

## 13. Generator Design Checklist

When reviewing a `Flux.generate(...)` call, check:

1. **Why generate manually?** Is there a simpler factory such as `range`, `fromIterable`, `just`, or `empty`?
2. **Does each callback have at most one `next`?** Never called multiple times in a loop.
3. **Does each callback emit at least one signal?** If there is no `next`, there must be `complete` or `error`.
4. **Is the completion condition exact?** Does it miss the last item, emit an extra item, or require an extra request just to complete?
5. **Is state isolated per subscriber?** Is `stateSupplier` called per subscription without mutable globals?
6. **No blocking I/O or heavy CPU loops on the event loop?** If present, choose an appropriate source/scheduler.
7. **Are cancel/error/cleanup handled?** Especially when state owns resources.
8. **Is infinite generation bounded?** Account for unbounded demand, cancellation, numeric limits, and generation rate.
9. **Tested with batched requests?** Observe items, terminal signals, and resource release.
10. **Returned publisher to WebFlux?** No `subscribe()` in controllers that detaches processing from the HTTP lifecycle.

## 14. Self-Check and Applied Scenarios

| Scenario | Conclusion |
|---|---|
| Callback calls `sink.next(a)` then returns state | Valid; next turn can emit the following item |
| Callback calls `sink.next(a); sink.complete();` | Valid; emits the final item then completes |
| Callback calls `sink.complete()` with no `next` | Valid; completes without more items |
| Callback calls none of `next`/`complete`/`error` | Invalid; Reactor reports an error |
| Callback calls `sink.next(a); sink.next(b);` | Invalid; violates one-next-per-call |
| There is `request(5)` | Reactor may invoke the generator for multiple turns; **never** allows 5 `next` calls in the same callback |
| Source holds an `AtomicInteger` in a static field | State may be shared across subscribers; create state inside `stateSupplier` |
| `take(2)` on an infinite generator | Downstream receives only two items and can cancel upstream |
| Generator waits on JDBC for 2 seconds | The thread running the callback still blocks; `generate` is not automatically non-blocking |
| External WebSocket callback source | Look at `Flux.create`/`Sinks`; do not retain `SynchronousSink` across async callbacks |
| `stateConsumer` is provided | Allows cleaning up state on complete, error, or cancel |

**Mini exercise:** Write a generator emitting the Fibonacci sequence `1, 1, 2, 3, 5, 8` with a state object holding `previous`, `current`, and `emittedCount`, completing **in the same turn** when emitting the sixth element. Each callback may call `sink.next(...)` only once; create a fresh state object via supplier so each subscription starts from the beginning. Then try `take(3)` and verify the consumer receives only the first three items.

One Java solution (snippet inside a class with `Flux` imported):

```java
record FibState(int previous, int current, int emittedCount) { }

Flux<Integer> fibonacci = Flux.generate(
        () -> new FibState(0, 1, 0),
        (state, sink) -> {
            sink.next(state.current());
            if (state.emittedCount() == 5) {
                sink.complete();
            }
            return new FibState(
                    state.current(),
                    state.previous() + state.current(),
                    state.emittedCount() + 1);
        });
```

When there is sufficient demand, the results are sequentially **1, 1, 2, 3, 5, 8** and then completion. Because `record` holds immutable integers, each callback invocation returns a new `FibState`. When extending the sequence indefinitely, avoid `int` overflow (consider `long`/`BigInteger`, termination thresholds, and performance).

**Takeaway:** `Flux.generate` is a tool for **synchronous, stateful data generation, at most one `onNext` per callback**. It listens to demand via subscription, supports terminal signals and state cleanup. Choose it when an algorithm computes the next element itself; use asynchronous callback sources or prebuilt factories when the problem fits those models.

## References

- Project Reactor — [Programmatically creating a sequence: Synchronous generate](https://projectreactor.io/docs/core/release/reference/coreFeatures/programmatically-creating-sequence.html).
- Project Reactor — [Flux API: overloads of generate](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/Flux.html).
- Project Reactor — [SynchronousSink API and signal limits](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/SynchronousSink.html).
- Project Reactor — [Backpressure and ways to reshape requests](https://projectreactor.io/docs/core/release/reference/subscribe-backpressure.html).
- Project Reactor — [BaseSubscriber API](https://projectreactor.io/docs/core/release/api/reactor/core/publisher/BaseSubscriber.html).
- Spring Framework — [WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html).
