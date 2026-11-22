# Distinguishing Sequential Streams, Parallel Streams, and Reactive Programming

When processing data in Java, three concepts—**sequential stream**, **parallel stream**, and **reactive programming**—are easily confused because all three can describe a chain of data transformations. However, they solve different needs:

- **Sequential stream**: describes how to process a data source through a pipeline, typically executed on a single thread.
- **Parallel stream**: still uses the Java Stream API, but allows splitting work across multiple threads to utilize multiple CPU cores.
- **Reactive programming**: a model for handling values/events that arrive over time, commonly used in asynchronous systems; it can support demand-regulation mechanisms (*backpressure*).

This lesson belongs to the **Stream API Overview** chapter of the **JAVA_STREAM_API** module. The goal is to recognize the execution model and limitations of each approach before using `filter`, `map`, `reduce`, `collect`, custom collectors, `Spliterator`, or parallel processing in Java. Here, *Stream* refers primarily to `java.util.stream.Stream`, not `java.io.InputStream`.

## 1. Java Stream API: one pipeline, two execution modes

The Java Stream API (since Java 8) provides a **declarative way to transform data**: stating *what to compute* rather than explicitly writing every loop and accumulator. A pipeline typically has three parts:

1. **Source**: `List`, array, `IntStream.range(...)`, a source backed by a `Spliterator`, etc.
2. **Intermediate operations**: `filter`, `map`, `distinct`, `sorted`, `limit`, ...; usually *lazy*, not traversing data immediately.
3. **Terminal operation**: `sum`, `count`, `reduce`, `collect`, `forEach`, ...; starts traversal and produces a result or side effect.

```text
Data source -> filter -> map -> ... -> terminal operation
                |       |
        lazy intermediate operations
```

The **sequential/parallel** mode is a property of the pipeline. Most operations are written identically; the main difference is how the runtime organizes traversal, work splitting, and result combining when the terminal operation runs.

### Example 1: One computation, two modes

```java
import java.util.Arrays;
import java.util.List;

public class StreamModes {
    public static void main(String[] args) {
        List<Integer> scores = Arrays.asList(10, -3, 7, 12, 0, 4);

        int sequentialTotal = scores.stream()       // sequential
                .filter(score -> score > 0)
                .mapToInt(score -> score * 2)
                .sum();

        int parallelTotal = scores.parallelStream() // parallel
                .filter(score -> score > 0)
                .mapToInt(score -> score * 2)
                .sum();

        System.out.println(sequentialTotal); // 66
        System.out.println(parallelTotal);   // 66
    }
}
```

Both versions share the **same business semantics**: keep positive scores, double them, and sum. Addition in this example is suitable for partial combination, so both results match. This does **not** mean the parallel version is always faster; on six elements, work-splitting overhead typically outweighs the benefit.

You can switch a pipeline between modes using `stream.parallel()` and `stream.sequential()`. For a single pipeline, the sequential/parallel setting takes effect when the terminal operation runs; do not think of `parallel()` as an intermediate operation that immediately creates a new result.

## 2. Direct comparison

| Aspect | Sequential stream | Parallel stream | Reactive programming |
|---|---|---|---|
| Typical API | `collection.stream()` | `collection.parallelStream()`, `stream.parallel()` | `Flow.Publisher`/`Subscriber` (Java 9+), Reactor `Flux`, RxJava |
| Suitable problems | Pipeline-style data transformation and aggregation | Independent, sufficiently large computations that can be split | Receiving and processing data/events arriving over time |
| Execution model | Pipeline is traversed sequentially | Work may be split across multiple workers and then combined | Determined by publisher, subscriber, and the library/pipeline scheduler |
| Asynchrony | Typical terminal operations run synchronously | Typical terminal operations still block waiting for the result despite parallel workers | Often features asynchronous data flows; not every pipeline runs off-thread by default |
| Input data | Finite, or potentially infinite with a custom generator source | Same as sequential Stream | Can be a finite sequence or a continuous stream of events |
| Rate control | Pulls on demand of the terminal operation; no async `request(n)` protocol | Same; splitting work is not backpressure | Reactive Streams/`Flow` uses `request(n)` to signal demand |
| Ordering | Can preserve *encounter order* if the source is ordered | Can preserve order, though some operations add extra cost; `forEach` does not guarantee order | Depends on publisher contract, operators, and concurrency model |
| Error handling | Exceptions typically propagate out of the terminal operation | Exceptions may occur while executing sub-tasks; still handled at the terminal call | Usually has an end-of-stream error signal such as `onError` |
| Termination | Ends after the terminal operation; Stream cannot be reused | Same | Can emit `onComplete`, `onError`, or be cancelled; some sources are long-lived |

**Key distinction:** `parallelStream()` does not turn a pipeline into Reactive Streams. Running multiple threads to speed up a computation and handling an event stream with `request(n)` demand signals are two different problems.

## 3. Sequential stream: default choice for ordinary data processing

In sequential mode, elements flow through the pipeline in sequential traversal order. Lazy intermediate operations allow Java to pass each element through multiple steps without forcing a temporary collection at every step.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> names = Arrays.asList("An", "Bình", "Anh", "Chi");

List<String> result = names.stream()
        .filter(name -> name.startsWith("A"))
        .map(String::toUpperCase)
        .collect(Collectors.toList());

System.out.println(result); // [AN, ANH]
```

Calling `filter` or `map` alone does not execute the full computation; `collect` is the terminal operation. Remember that a `Stream` is typically **consumed only once**: to compute again, create a new pipeline from the source.

Sequential streams are generally suitable when data is small or moderate, per-element work is fast, readability/testability is prioritized, or encounter order matters. Staying sequential also avoids unnecessary parallel coordination overhead.

## 4. Parallel stream: increasing throughput when conditions are met

When a Stream is placed in parallel mode, Java can use a source-splitting mechanism (tied to `Spliterator`), let workers process chunks, and combine the results. Parallel streams commonly use `ForkJoinPool.commonPool()`, so blocking operations or other tasks sharing the pool can affect throughput.

```text
                Large data source
                  /     |     \
              part A  part B  part C
                 \      |      /
                combine results
```

Effectiveness depends on **source splittability**, **element count**, **per-element processing cost**, **combining cost**, and **how much work must preserve order or state**. Arrays and `ArrayList` generally split more easily than sequentially traversed sources or slow I/O sources.

### 4.1. Combining operations must be parallel-safe

A `reduce` operation can be safely split when it has a proper *identity* value and its combining function (*accumulator/combiner*) obeys *associativity*. Integer addition is a familiar example:

```java
int total = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, Integer::sum); // 10
```

**Do not use arbitrary subtraction as a parallel reduction:**

```java
int unstable = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, (left, right) -> left - right);
// Do not treat this as a valid parallel reduce:
// (a - b) - c differs from a - (b - c).
```

Besides associativity, functions in the pipeline should be **non-interfering** and, in most cases, **stateless** without shared state. Never depend on the completion order of individual workers.

### 4.2. Avoid mutating a shared collection from `forEach`

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> source = Arrays.asList(1, 2, 3, 4, 5, 6);

// WRONG: multiple workers concurrently mutating a non-thread-safe ArrayList.
List<Integer> unsafe = new ArrayList<>();
source.parallelStream().forEach(unsafe::add);

// RIGHT: let collect coordinate accumulators and combiners.
List<Integer> safe = source.parallelStream()
        .filter(number -> number % 2 == 0)
        .collect(Collectors.toList());
```

`Collectors.toList()` does not guarantee returning one specific `List` implementation; what matters is that `collect` is coordinated by the Stream API according to the collector's contract. Do not assume you can share and mutate the same `ArrayList` across multiple workers.

### 4.3. Ordering, state, and performance

```java
List<Integer> values = Arrays.asList(1, 2, 3, 4, 5);

values.parallelStream().forEach(System.out::println);
// Print order may differ from 1, 2, 3, 4, 5.

values.parallelStream().forEachOrdered(System.out::println);
// With an ordered List source, prints in encounter order.
```

`forEachOrdered` preserves observable order, but enforcing order can reduce parallel gains. Stateful operations such as `sorted`, `distinct`, `limit` on ordered sources, or grouping can also increase coordination cost. `findAny` is free to select any matching element; `findFirst` must respect the first element in encounter order when order exists.

Do not routinely use parallel streams for HTTP calls, database queries, or blocking I/O: pool workers end up waiting on the network instead of performing CPU work. Actual speedup or slowdown must be measured on realistic data and environments; for serious Java benchmarking, use a tool like JMH with warm-up and controlled input sizes.

## 5. Reactive programming: handling events over time

Reactive programming models values arriving **over time**: sensor readings, transaction notifications, WebSocket messages, UI events, and asynchronous HTTP responses. A reactive pipeline can transform, combine, filter, or batch events while also managing emission timing, unsubscription, errors, and whether consumers can keep up.

In Java, `java.util.concurrent.Flow` (Java 9+) defines foundational roles conceptually compatible with the Reactive Streams specification:

- **`Flow.Publisher<T>`**: source supplying elements.
- **`Flow.Subscriber<T>`**: receiver of `onSubscribe`, `onNext`, `onError`, and `onComplete` signals.
- **`Flow.Subscription`**: subscription used by the subscriber to call `request(n)` or `cancel()`.
- **`Flow.Processor<T, R>`**: both a subscriber on input and a publisher on output.

```text
Publisher  -- onNext(item) / onError / onComplete --> Subscriber
Publisher  <-- request(n) / cancel() --------------- Subscription (held by Subscriber)
```

With `Flow`/Reactive Streams, a subscriber must signal **demand** via `request(n)` before the publisher is allowed to emit up to that many elements for the subscription. This mechanism is called *backpressure*: the receiver signals its capacity so the source can regulate emission. It does not automatically make every data source infinitely safe; queue policies, buffering, drops, or producer blocking still depend on the implementation.

### Example 2: Publisher and subscriber with demand regulation

The example below uses only the JDK (Java 9+), with `SubmissionPublisher` emitting a sequence of events. The subscriber requests one element at a time.

```java
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Flow;
import java.util.concurrent.SubmissionPublisher;

public class FlowExample {
    public static void main(String[] args) throws InterruptedException {
        CountDownLatch finished = new CountDownLatch(1);

        try (SubmissionPublisher<Integer> publisher =
                     new SubmissionPublisher<>()) {

            publisher.subscribe(new Flow.Subscriber<Integer>() {
                private Flow.Subscription subscription;

                @Override
                public void onSubscribe(Flow.Subscription s) {
                    subscription = s;
                    s.request(1); // Allow sending the first 1 element.
                }

                @Override
                public void onNext(Integer item) {
                    System.out.println("Received event: " + item);
                    subscription.request(1); // Request the next one only after processing.
                }

                @Override
                public void onError(Throwable error) {
                    error.printStackTrace();
                    finished.countDown();
                }

                @Override
                public void onComplete() {
                    finished.countDown();
                }
            });

            for (int value = 1; value <= 5; value++) {
                publisher.submit(value);
            }
            // Closes the publisher on exiting the try block; emits onComplete.
        }

        finished.await(); // Wait for the subscriber to receive the completion signal.
    }
}
```

In this example, `submit` feeds data into `SubmissionPublisher`'s asynchronous delivery mechanism; `onNext` is typically invoked on the executor's worker thread. `request(1)` is a demand signal, **not** a guarantee that the publisher buffers only a single element. `SubmissionPublisher.submit` can block when its buffer is full. Thus, this demo illustrates the subscribe/emit/complete contract rather than a full non-blocking I/O or production pipeline.

Libraries like Project Reactor (e.g., `Flux`) or RxJava provide far more operators for transforming and coordinating events than the built-in `Flow` interfaces. However, merely using a reactive API **does not automatically create asynchrony**: scheduling, the data source, and specific operators determine which threads execute what.

## 6. Laziness, parallelism, and backpressure are three separate properties

Because the word "stream" appears in the name, learners often merge these three ideas into one:

**Lazy evaluation** means deferring work until needed. With Java Streams, many intermediate operations run only when a terminal operation is invoked. In reactive libraries, many publishers start emitting only upon subscription, though this depends on the publisher type (*cold* vs. *hot* sources).

**Parallelism** means multiple tasks can execute concurrently across different processing resources. `parallelStream()` asks the runtime to leverage this when traversing the pipeline; the terminal operation call is still **synchronous to the caller**: the method returns only after computation finishes.

**Asynchrony and backpressure** relate to communication between producer and consumer over time. A reactive API can push signals without forcing the caller to wait for the entire event sequence to finish. `request(n)` in `Flow`/Reactive Streams regulates how many elements are emitted per subscription. There is no equivalent `request(n)` protocol in `java.util.stream.Stream`; Stream's synchronous traversal pulls data from the source as needed.

For example, changing `orders.stream()` to `orders.parallelStream()` does **not** give it `subscribe()`, `onNext()`, or `cancel()`. Conversely, a `Flux` without a scheduler can still execute operators synchronously on the thread calling `subscribe()`.

## 7. When to choose which approach?

| Scenario | Suitable approach | Reason |
|---|---|---|
| Filter a product list, sum invoice totals, generate a small report | Sequential stream | Concise pipeline, minimal execution orchestration overhead |
| Compute an expensive CPU function over millions of independent array elements | Consider parallel Stream, after benchmarking | Source can be split and results combined |
| Receive stock prices or continuous WebSocket events | Reactive programming | Observe events, cancel subscriptions, regulate when consumers are slow |
| Make many network-bound HTTP requests | Async client, `CompletableFuture`, or reactive library with suitable I/O | Waiting on I/O is a different problem from splitting CPU work in a Stream |
| Compute results requiring shared mutable updates or strict ordering at every step | Usually start with sequential Stream or redesign the aggregation | Avoid race conditions and ordering coordination costs |

Practical selection workflow:

1. **Data is already in memory and you need one final result?** Start with a sequential Stream.
2. **Work is primarily CPU-bound, elements are independent, and data is large and easily splittable?** Verify the combining operation's correctness, test `parallel()`, and measure performance.
3. **Data arrives gradually, multiple events must be received, or rate control/cancellation is needed?** Consider `Flow`/Reactive Streams and an appropriate reactive library.
4. **Only need an asynchronous result from a single task?** `CompletableFuture` can be simpler than a multi-element reactive pipeline.

## 8. Misconceptions to avoid

| Common misconception | More accurate understanding |
|---|---|
| "`parallelStream()` is always faster than `stream()`." | Parallelism has splitting, handoff, and combining overhead; small datasets or light tasks rarely benefit. |
| "Sequential and parallel Streams always return the same order." | Correct calculations can yield the same result, but parallel `forEach` does not guarantee order; `forEachOrdered` has different constraints. |
| "Any `reduce` can run in parallel." | It must have a proper identity and an associative combining operation; side effects can break correctness. |
| "Stream API is Reactive Streams." | `java.util.stream` executes pipelines via a terminal operation; `Flow`/Reactive Streams defines a publisher–subscriber protocol with `request(n)` demand. |
| "Reactive always means multi-threaded or non-blocking." | It depends on the source, executor, scheduler, and operators; a reactive chain can still run synchronously or block. |
| "Having backpressure means memory can never fill up." | You must still choose buffering policies and behavior when the producer outpaces the consumer. |
| "Putting side effects in `map`/`peek` to mutate shared variables is fine." | Streams may execute lazily, out of order, or across multiple workers; use stateless functions and proper collectors. |

## 9. Self-check

1. There are 500 records in a `List` to filter by status and count. **What to choose?** Start with a sequential Stream; there is no basis for adding parallel overhead.
2. There are 10 million array elements, each needing an independent heavy math calculation combined with a valid associative operation. **What to choose?** A parallel Stream is a strong candidate to test; benchmark against sequential and verify results.
3. A dashboard continuously receives sensor data and may need to pause or unsubscribe if the user leaves the screen. **What to choose?** A reactive model fits better than a single-use Stream pipeline; verify backpressure support across the full system.

From the examples above, the deciding factor is not whether the pipeline uses `filter`/`map`, but **how data arrives, whether work splits independently, and whether asynchronous execution and demand regulation are needed**. Understanding these boundaries helps you use the Java Stream API properly and recognize when to move to an event-processing model.
