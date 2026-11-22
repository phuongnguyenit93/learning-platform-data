# Bounded Concurrent Mapping with `Gatherers.mapConcurrent`

## 1. Lesson objectives and real-world scenario

In the **`JAVA_STREAM_API`** module, a Java Stream pipeline usually expresses a data-processing flow with declarative operations: creating a source, `filter`, `map`, `flatMap`, `reduce`, and `collect`. For independent tasks that spend time **waiting on I/O**, such as calling multiple APIs, checking the status of many records, or reading data from a connection-limited service, sequential `map` can spend most of its time simply waiting for each result one by one.

Running everything in unbounded parallel is also unsuitable: the target system may allow only a certain number of in-flight requests, database connection pools are finite, and application memory is not infinite.

**`Gatherers.mapConcurrent(maxConcurrency, mapper)`** is a built-in gatherer that enables:

- Transforming each element with `mapper` in a **one-input → one-output** relationship.
- Running **multiple mapper invocations concurrently**, up to the limit `maxConcurrency`.
- Using **virtual threads** provided by the API to execute the calls.
- **Preserving output order** according to the source stream's encounter order, even when tasks complete out of order.
- Combining with `Stream.gather(...)` to continue with `filter`, `map`, `collect`, or other terminal operations.

This lesson is part of the **Stream Gatherer** chapter. The goal is not only to learn Java 24 syntax, but also to understand how to design concurrency limits, handle errors, short-circuiting, resources, load levels, and testing before bringing concurrency into a system.

After this lesson, you will be able to:

1. Use `Stream.gather(Gatherers.mapConcurrent(...))` with the proper Java version.
2. Explain the differences among **concurrency**, **parallelism**, and **rate limiting**.
3. Verify the limit on concurrent mapper calls using a thread-safe counter.
4. Keep results in source order even when tasks finish out of order.
5. Distinguish `mapConcurrent` from `map`, `parallelStream().map`, and a self-managed executor.
6. Design policies for exceptions, task cancellation, timeouts, and shared state.
7. Evaluate when virtual threads help and when CPU-bound work does not benefit.
8. Write a Java 24+ verification program and recognize the limits of the experiment.

## 2. JDK version and compilation requirements

Important milestones:

| Version | Stream Gatherers | `Gatherers.mapConcurrent` |
| --- | --- | --- |
| Java 8–21 | No standard Gatherers API yet | Method does not exist |
| Java 22 | First preview (JEP 461) | Preview, requires enabling corresponding preview |
| Java 23 | Second preview (JEP 473) | Preview, still requires enabling preview |
| **Java 24 and later** | **Official (JEP 485)** | Available as a standard API, no `--enable-preview` needed |

Examples in this lesson use **Java 24+**, unless an older-JDK alternative is explicitly noted. `Stream.toList()` has existed since Java 16, whereas `Stream.gather` and `Gatherers.mapConcurrent` were only standardized in Java 24.

Check the environment:

```text
java -version
javac -version
```

With the `MapConcurrentIntro.java` file below:

```text
javac MapConcurrentIntro.java
java MapConcurrentIntro
```

If a project uses a Maven/Gradle toolchain or `javac --release 21`, Java 24 Gatherers cannot be used even if JDK 24 is installed in the terminal. Both **the compile API level** and **the actual runtime JDK** must be compatible. Do not just change one version setting and overlook the application host.

## 3. Signature and core contract

In Java 24, the built-in API has the signature:

```java
public static <T, R> Gatherer<T, ?, R> mapConcurrent(
    int maxConcurrency,
    Function<? super T, ? extends R> mapper
)
```

Meaning:

| Component | Role |
| --- | --- |
| `T` | Source element type entering the gatherer |
| `R` | Output element type produced by the mapper |
| `maxConcurrency` | Desired **maximum concurrency** for the mapper, must be ≥ 1 |
| `mapper` | Function converting one `T` into one `R` |
| `Gatherer<T, ?, R>` | Object describing the intermediate transformation |
| `Stream.gather(...)` | Applies the gatherer to the source stream, returning `Stream<R>` |

Pipeline shape example:

```java
Stream<Integer> input = Stream.of(1, 2, 3);

Stream<String> output = input.gather(
    Gatherers.mapConcurrent(
        2,
        n -> "ID-" + n
    )
);

List<String> result = output.toList();
```

The logical result is `[ID-1, ID-2, ID-3]`. `gather` remains an **intermediate operation**; mapper execution is triggered when the pipeline is consumed by a terminal operation such as `toList`.

### 3.1. One input produces one output

`mapConcurrent` has a **one-to-one** element relationship when the mapper completes normally. Do not call `mapConcurrent` to:

- Emit 0 or multiple elements from a single input on its own.
- Group into a `Map` by key.
- Create sliding windows, fixed windows, or prefix scans.

Those needs belong to other APIs such as `filter`, `flatMap`, `mapMulti`, `collect(groupingBy(...))`, `Gatherers.windowSliding`, or `Gatherers.scan`.

Example keeping only even numbers:

```java
List<String> result = Stream.of(1, 2, 3, 4)
    .filter(n -> n % 2 == 0)
    .gather(Gatherers.mapConcurrent(
        2, n -> "N=" + n))
    .toList();

System.out.println(result); // [N=2, N=4]
```

Here **`filter`**, not `mapConcurrent`, removes elements.

### 3.2. Parameter validation

Per the Java 24 API:

- `maxConcurrency < 1` → `IllegalArgumentException`.
- `mapper == null` → `NullPointerException`.

```java
// Rejected:
Gatherers.mapConcurrent(0, (Integer n) -> n * 2);
Gatherers.mapConcurrent(-1, (Integer n) -> n * 2);
Gatherers.<Integer, Integer>mapConcurrent(2, null);
```

Do not accept `0` assuming it means "run sequentially". If a sequential mapper is needed, use `stream.map(mapper)`, or `mapConcurrent(1, mapper)` when keeping the same gatherer shape without expecting a speedup.

**An upper limit** should also have an application policy. The JDK only requires a positive value; configuring `1_000_000` does not mean the target system can handle a million concurrent requests.

## 4. First runnable example (Java 24+)

Create `MapConcurrentIntro.java`:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class MapConcurrentIntro {
    static String lookupLabel(int id) {
        return "item-" + id;
    }

    public static void main(String[] args) {
        List<String> labels = IntStream.rangeClosed(1, 6)
            .boxed()
            .gather(Gatherers.mapConcurrent(
                3, MapConcurrentIntro::lookupLabel))
            .toList();

        System.out.println(labels);
        // [item-1, item-2, item-3, item-4, item-5, item-6]
    }
}
```

Reading left to right:

1. `IntStream.rangeClosed(1, 6).boxed()` creates a `Stream<Integer>` with encounter order.
2. `Gatherers.mapConcurrent(3, ...)` configures at most three mapper calls executing concurrently.
3. `gather` builds a pipeline capable of concurrent mapping via virtual threads.
4. `toList` waits for the needed results and collects them into a list.
5. The list is ordered by the **source**, regardless of which callback finished first.

This is a **semantically valid example**, though `lookupLabel` only does fast string concatenation. Do not expect it to be faster than `map(MapConcurrentIntro::lookupLabel)`: coordination overhead can exceed the cost of string concatenation.

## 5. How do virtual threads help with waiting?

A **virtual thread** is a lightweight thread mechanism managed by the Java runtime; many virtual threads can be scheduled onto a smaller number of platform threads. This is especially useful when work frequently **waits on I/O** rather than continuously consuming CPU.

Conceptual model:

```text
Source Stream:   A       B       C       D       E
                  \      |      /
                   mapConcurrent(3)
                  /      |      \
             virtual   virtual   virtual
             thread    thread    thread
                 |        |        |
             wait API  wait API  wait API
                  \       |       /
             receive results in source order
                        |
                     Stream<R>
```

While one task waits for a response, the runtime can run another task. **Virtual threads do not magically make a CPU computation faster**: concurrent compute throughput is still bounded by CPU cores, memory contention, and scheduling.

### 5.1. Why not just use `parallel()`?

`parallelStream` typically splits the source across fork/join work units. That suits many **independent CPU-bound computations on easily splittable sources**. Meanwhile, `mapConcurrent` offers a different benefit: **putting a potentially blocking mapping step onto bounded concurrent execution without converting the entire stream into a parallel stream**.

Do not treat the two APIs as synonymous. The detailed comparison in a later section clarifies when to pick which.

### 5.2. `maxConcurrency` is not CPU core count

Choosing `maxConcurrency = 20` does not require the machine to have 20 cores. It allows up to 20 mapper invocations to be **in progress** concurrently, potentially spending most of their time waiting. For CPU-only tasks, exceeding available CPU capacity may only add overhead.

When the mapper calls a remote service, beyond core count you must consider:

- The number of concurrent connections allowed by the target service.
- The client's HTTP/JDBC connection pool.
- Timeouts, retries, and circuit breakers.
- Memory holding in-flight inputs and outputs.
- Concurrent requests from **other pipelines** in the same application.

## 6. Concurrency differs from parallelism and rate limiting

These three concepts must not be equated:

| Concept | Question | Example |
| --- | --- | --- |
| **Concurrency** | How many tasks are being managed/in progress at the same time? | At most 5 mappers waiting on an API |
| **Parallelism** | How many compute parts are physically executing simultaneously on CPU resources? | Multiple cores processing array slices |
| **Rate limit** | How many requests are initiated or completed within a time window? | At most 100 requests/second |

`mapConcurrent(5, mapper)` limits **the number of concurrent mapper calls**. It **does not guarantee** a maximum rate of 5 requests/second.

For instance, if a service responds in around 10 ms, five slots can be reused many times per second. If the service responds slowly over several seconds, throughput will be substantially lower at the same concurrency level.

### 6.1. Do not use concurrency as a QPS quota

If an API has a quota of **100 requests/second**, simply using:

```java
.gather(Gatherers.mapConcurrent(10, this::callApi))
```

does not control how many requests start per second. To enforce a rate quota, you may need a **token-bucket/time-window rate limiter** combined with a concurrency limit; the two limit layers protect **two different resources**.

### 6.2. One pipeline does not manage an application-wide quota

Two independent web requests, each creating a `mapConcurrent(10, ...)` pipeline, do not automatically share a global budget of 10 requests across the entire application. If upstream only allows 10 total requests, you must enforce a **global limit** at the client layer or via a shared concurrency limiter (e.g., `Semaphore`/pool), in addition to the gatherer's local limit.

You cannot infer from each individual pipeline being valid that the whole service will never overload downstream.

## 7. Preserving encounter order even when mappers finish out of order

Suppose the source is `[1,2,3,4]`, yet the mapper for 1 takes longer than the mappers for 2 and 3. With `mapConcurrent`, the runtime can run multiple mappers concurrently, yet **the output still reflects the encounter order** of an ordered source stream.

Java 24+ example with simulated wait times:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;

public class OrderedConcurrentMap {
    static String delayedLabel(int id) {
        long sleepMillis = (5L - id) * 30L;

        try {
            Thread.sleep(sleepMillis);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Task interrupted", ex);
        }
        return "id-" + id;
    }

    public static void main(String[] args) {
        List<String> result = IntStream.rangeClosed(1, 4)
            .boxed()
            .gather(Gatherers.mapConcurrent(
                4, OrderedConcurrentMap::delayedLabel))
            .toList();

        System.out.println(result);
        // [id-1, id-2, id-3, id-4]
    }
}
```

Data after `toList` **has a stable order** on this source. We deliberately vary the wait time across IDs, without **asserting that actual scheduling or completion order is identical** across every run. `Thread.sleep` is only a simulation tool, not evidence of real application speed.

### 7.1. Result order ≠ side-effect order

Do not use `System.out.println` inside a mapper to guess ordering:

```java
// For diagnostics only; do not treat log order as a contract.
List<String> result = IntStream.rangeClosed(1, 4)
    .boxed()
    .gather(Gatherers.mapConcurrent(3, id -> {
        System.out.println("Processing " + id);
        return "item-" + id;
    }))
    .toList();
```

Log lines may appear in an order different from the source, while `result` still follows encounter order. Avoid relying on log order to compute results or generate a **global sequence number** from concurrently running mappers.

### 7.2. Sources without encounter order

If the source is a `HashSet` or the pipeline calls `unordered()`, `mapConcurrent` cannot invent a fixed business order. If results are needed in ascending ID order, normalize beforehand:

```java
List<String> result = ids.stream()
    .sorted()
    .gather(Gatherers.mapConcurrent(
        4, id -> "item-" + id))
    .toList();
```

`ids` is a collection of integers in a real program. `sorted` establishes value order, though sorting cost on large sets should be weighed. If elements are records and the primary key can tie, add a **stable tie-breaker key** for a total order.

## 8. Result buffering window and the head-of-line blocking problem

Preserving encounter order has a trade-off: a **slow** mapper at an earlier position can force downstream emission of **later** results to wait, even after those mappers have finished.

Conceptual example:

```text
Input:      A    B    C    D
Mapper:     ├───────────────┤
                 ├──┤ ├──┤ ├──┤
Completed:       B    C   D          ... A later
Ordered output:   still needs A before B, C, D
```

This phenomenon is called **head-of-line blocking**. It often matters when mapper latency has a long tail (tail latency) or when a service responds very unevenly.

Points to distinguish:

- `mapConcurrent` guarantees **result** ordering, not that every element becomes available to downstream immediately when its mapper completes.
- `maxConcurrency` bounds how many mappers run at once, which **does not mean total memory only holds `maxConcurrency` small objects**; input/output sizes and how downstream retains results also matter.
- When `toList` collects all results, the final list itself must hold all collected elements.
- If the business requirement does not need ordering, other APIs may fit better; do not rely on `mapConcurrent` to emit "whichever finishes first comes out first", because its contract is the opposite.

If the system needs to push results immediately upon completion in arbitrary order, design a separate completion-order model and document that **semantic change**.


## 9. Truly verifying the number of concurrently running mappers

To verify `maxConcurrency`, do not measure by counting total virtual threads in the JVM, and do not use an unsynchronized shared `int`. You need to count **mapper invocations that have started but not yet finished**.

A measurement approach you can use:

- `AtomicInteger active`: number of mappers currently executing.
- `AtomicInteger peak`: highest observed active count.
- Increment `active` when entering the mapper.
- Decrement `active` in `finally` to handle errors or interruption too.
- Update `peak` with an atomic operation, not separate read-write steps.

### 9.1. Concurrency monitoring pattern

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger active = new AtomicInteger();
AtomicInteger peak = new AtomicInteger();

List<String> result = ids.stream()
    .gather(Gatherers.mapConcurrent(4, id -> {
        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);

        try {
            return "item-" + id;
        } finally {
            active.decrementAndGet();
        }
    }))
    .toList();

System.out.println("Peak observed: " + peak.get());
```

This snippet is placed inside a method of a Java 24+ class with `ids` as `List<Integer>` and imports `java.util.List`, `java.util.stream.Gatherers`.

Verify:

```java
if (peak.get() > 4) {
    throw new AssertionError("Exceeded concurrency limit");
}
```

**Do not require `peak == 4`.** With a very fast mapper or few elements, four simultaneous invocations may never happen. `maxConcurrency` is an **upper bound**, not a command forcing the runtime to always fill every slot.

### 9.2. Why is `finally` required?

If a mapper throws an exception, omitting `active.decrementAndGet()` will leave the counter showing an inaccurate count:

```java
int now = active.incrementAndGet();
try {
    return process(value);
} finally {
    active.decrementAndGet();
}
```

`process(value)` here is an illustrative function; it must be declared in the application program. `finally` keeps the counter accurate even when a mapper is interrupted or fails.

In observability systems, you can measure an in-flight request gauge with a similar structure. However, instrumentation must be **thread-safe** and must not become the main bottleneck of the pipeline.

## 10. I/O scenario example: multiple independent calls, results still properly ordered

An external API can look up details for each order ID. Data model:

```text
orderIds = ["O-101", "O-102", "O-103", "O-104"]

Lookup (may wait on I/O):
  O-101 -> PAID
  O-102 -> PENDING
  O-103 -> PAID
  O-104 -> REFUNDED

Result after mapConcurrent:
  ["O-101:PAID", "O-102:PENDING", "O-103:PAID", "O-104:REFUNDED"]
```

Java 24+ illustrative code using a simulated source to avoid network dependencies:

```java
import java.util.List;
import java.util.stream.Gatherers;

public class OrderLookupDemo {

    static String fetchStatus(String orderId) {
        // Simulates a task that waits, no real network call.
        try {
            Thread.sleep(40L);
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Lookup interrupted", ex);
        }

        return switch (orderId) {
            case "O-101", "O-103" -> "PAID";
            case "O-102" -> "PENDING";
            default -> "REFUNDED";
        };
    }

    public static void main(String[] args) {
        List<String> orderIds = List.of(
            "O-101", "O-102", "O-103", "O-104");

        List<String> results = orderIds.stream()
            .gather(Gatherers.mapConcurrent(2, id ->
                id + ":" + fetchStatus(id)))
            .toList();

        System.out.println(results);
        // [O-101:PAID, O-102:PENDING,
        //  O-103:PAID, O-104:REFUNDED]
    }
}
```

Calling `Thread.sleep(40)` only simulates wait time: it **does not prove** HTTP or JDBC client performance. In production, the mapper might call a service through a client supporting timeouts, connection pooling, and resource limits.

### 10.1. Identifying key and result

When making multiple concurrent API calls, return **results paired with their key** rather than keeping bare values that are easy to mix up:

```java
record OrderStatus(String orderId, String status) {}

List<OrderStatus> statuses = orderIds.stream()
    .gather(Gatherers.mapConcurrent(
        3,
        id -> new OrderStatus(id, fetchStatus(id))))
    .toList();
```

This is a Java 24+ example using `record` from Java 16, placed within a class/method with the relevant imports. Even though `mapConcurrent` preserves order, carrying `orderId` inside the result keeps downstream safe when reconciling with other data.

### 10.2. Choosing `maxConcurrency` based on the bottleneck

A process for choosing concurrency level:

1. Determine whether **tasks are independent** and safe to run concurrently.
2. Check limits on the target service (connection pool, quota, concurrency cap, stability).
3. Start with a small level to avoid causing a request cascade.
4. Measure latency, throughput, error counts, timeouts, in-flight count, and memory pressure.
5. Test several concurrency levels in a representative environment.
6. Lower the level if hitting quotas, timeouts, rising p95/p99, or pool exhaustion.
7. Test under **multiple concurrent pipelines**, not just a single isolated request.

A very large `maxConcurrency` can make throughput **worse** due to contention and cascading retry failures. Do not default to a huge number merely because virtual threads are cheaper than platform threads.

## 11. Output has one element per input, unless an error occurs

In terms of data flow, `mapConcurrent` is a one-to-one mapping. If every mapper completes normally, result elements correspond one-for-one to inputs. However, when a mapper throws an exception, **never assume the pipeline returns a result list missing a few elements and treats it as success**.

Per the Java 24 Javadoc, if a result is **ready to be emitted downstream** yet its corresponding mapper completed with an exception, the gatherer rethrows the error as a **`RuntimeException`**, then attempts to cancel the remaining tasks.

Example:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class MapperExceptionDemo {
    public static void main(String[] args) {
        try {
            List<Integer> result = Stream.of(1, 2, 3, 4)
                .gather(Gatherers.mapConcurrent(2, n -> {
                    if (n == 3) {
                        throw new IllegalArgumentException(
                            "Invalid value: " + n);
                    }
                    return n * 10;
                }))
                .toList();

            System.out.println(result);
        } catch (RuntimeException ex) {
            System.out.println("Pipeline failed");
        }
    }
}
```

Do not rely on **the specific exception type inside `RuntimeException`**, thread names, or log order to assert the contract. The API specifies the error-rethrowing mechanism, while wrapping/cause attachment should not be hardcoded when not guaranteed.

### 11.1. Checked exceptions from I/O

`Function<T,R>` does not declare checked exceptions. When a mapper calls an API that throws `IOException` or `InterruptedException`, handle it **inside the mapper**:

```java
static String simulatedBlockingCall(String id) {
    try {
        Thread.sleep(50L);
        return "OK:" + id;
    } catch (InterruptedException ex) {
        Thread.currentThread().interrupt();
        throw new IllegalStateException(
            "Interrupted while processing " + id, ex);
    }
}
```

Do not swallow interruption and keep waiting indefinitely. Preserving the interrupt flag helps cancellation policies and application shutdown work properly.

**However, interrupt is not a transaction rollback.** If the mapper already sent a payment request or database write, interrupting the Java thread does not automatically undo side effects in external systems.

### 11.2. Want to keep error results individually instead of failing the whole pipeline?

Turn the error into **a data value** under an explicit contract:

```java
record LookupResult(
    String id,
    String value,
    String error
) {
    boolean isSuccess() {
        return error == null;
    }
}

static LookupResult safeLookup(String id) {
    try {
        return new LookupResult(
            id, simulatedBlockingCall(id), null);
    } catch (RuntimeException ex) {
        return new LookupResult(
            id, null, "LOOKUP_FAILED");
    }
}
```

Then:

```java
List<LookupResult> all = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, MyClass::safeLookup))
    .toList();
```

This snippet assumes `ids` and `MyClass` are declared in the application. This is **a different business policy**: recording failures per record instead of throwing upon the first failure to be emitted.

When handling errors, do not expose raw exception messages that may contain tokens, URLs with secrets, or personal data in displayed results. Classify errors with codes, log carefully, and preserve correlation IDs.

**Caution:** catching all `RuntimeException`s and returning an error value can mask programming bugs. Only convert expected failure categories into data errors; serious system errors must be logged and handled separately.

## 12. Best-effort task cancellation and short-circuit limits

A terminal operation like `findFirst`, `anyMatch`, or `limit` can stop when no more results are needed.

```java
List<Integer> firstTwo = Stream.of(1, 2, 3, 4, 5)
    .gather(Gatherers.mapConcurrent(
        3, n -> n * 10))
    .limit(2)
    .toList();

System.out.println(firstTwo); // [10, 20]
```

Per the API, when downstream no longer wants more elements, the gatherer **attempts to cancel running tasks on a best-effort basis**. This is **not a guarantee** that:

- Only exactly two mappers ever started running.
- Other mappers have not called external APIs yet.
- All tasks have completely stopped the instant `limit(2)` finishes.
- All side effects have been canceled or rolled back.
- Your HTTP/JDBC client necessarily honors interruption.

Because multiple mappers can be in-flight, the number of started tasks **can exceed the number of retained results**. Therefore, never place an irreversible operation in a mapper and rely on `limit` to promise only a few operations executed.

### 12.1. `findFirst` and `findAny`

`mapConcurrent` preserves encounter order of an ordered source, yet `findFirst` and `findAny` serve different purposes:

- `findFirst` requires the first element in encounter order.
- `findAny` may pick any matching element per the terminal operation's condition.

Do not assume `findAny` on a pipeline using `mapConcurrent` automatically creates a "whichever finishes first wins" mechanism; layered processing and ordering can affect which result is ready. If the product **needs the first result by actual completion time**, design a separate completion-order API.

### 12.2. Do not use short-circuiting to perform bulk writes

Suppose `mapper` calls `saveToDatabase` or `chargeCreditCard`. These calls have critical side effects. A short-circuiting terminal operation leaves unclear **which records succeeded** and which tasks are still pending.

For side-effecting operations, you need:

- An **idempotency key** or deduplication scheme if retrying.
- Visibility into when the operation committed in the external system.
- Timeout and partial-failure management.
- Per-request state tracking and compensation policies when needed.
- Never treating Java task cancellation as a transaction rollback.

`mapConcurrent` is a concurrent mapping tool, **not a distributed transaction manager**.

## 13. Timeouts, retries, backpressure, and quotas

`maxConcurrency` only controls one aspect of load pressure. An infinitely waiting mapper can hold a slot for a very long time; capping to N slots does not create a timeout on its own.

### 13.1. Set timeouts directly on the client

For HTTP, configure connect and request timeouts on the client/request. For JDBC, configure deadlines/query timeouts and bounded pools. These belong to **the I/O layer**, not `mapConcurrent` parameters.

A typical mapper:

```java
static String fetchWithPolicy(String id) {
    // Client already configured with:
    // - request timeout
    // - connection pool
    // - bounded retries for appropriate errors
    // - error classification/metrics
    return remoteClient.lookup(id);
}
```

This is **pseudocode**: `remoteClient` is not a built-in JDK class in the example. Provide an implementation matching your real API/service.

### 13.2. Retries can exceed external service limits

If a mapper itself launches multiple **concurrent** requests during retry/hedging or fans out for a single input, `maxConcurrency` only bounds running mappers, not necessarily total **sub-requests**.

For example, `mapConcurrent(5)` where each mapper spawns 3 parallel HTTP tasks can generate **more than 5** outbound requests. Enforce limits at the exact layer where the resource is consumed.

### 13.3. Do not use unbounded retries

Unbounded retries or tiny backoffs can hold mapper slots for long periods and cause request storms when the target service is degraded. Define:

- Maximum attempt count.
- Whole-task deadline/timeout.
- Bounded backoff with jitter when appropriate.
- Allowlist of retryable errors.
- Idempotency for write operations.
- An independent rate limiter if the service enforces a time-based quota.

**Backpressure** is not synonymous with a single parameter. `maxConcurrency` helps cap in-flight mappers within one gatherer, yet does not automatically manage all queues, buffers, clients, or system-wide workflows.

## 14. Comparing `map`, `mapConcurrent`, and `parallelStream`

Same transformation functionality:

```java
// Sequential: each element's mapper runs in a sequential pipeline.
List<String> a = ids.stream()
    .map(this::fetch)
    .toList();

// Bounded concurrent: virtual threads, still preserves source order.
List<String> b = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, this::fetch))
    .toList();

// Parallel stream: runtime splits pipeline via Spliterator.
List<String> c = ids.parallelStream()
    .map(this::fetch)
    .toList();
```

The snippet illustrates syntax inside **an instance method** with `ids` as `List<String>` and `fetch(String)` returning `String`. All three can yield the same result if the mapper is pure, thread-safe, and error-free.

| Criterion | `stream().map(...)` | `gather(mapConcurrent(...))` | `parallelStream().map(...)` |
| --- | --- | --- | --- |
| Java milestone | Java 8 | Java 24 official | Java 8 |
| Mapper concurrency | None, in sequential stream | Yes, up to `maxConcurrency` | Per parallel stream splitting/scheduling |
| Underlying mechanism | Sequential pipeline | Virtual threads | Fork/join in common JDK implementations |
| Direct mapper cap | Not needed | Yes: `maxConcurrency` | No equivalent direct parameter |
| Ordered data with encounter order | Preserves order | **Preserves order** | Appropriate terminal preserves order |
| Behavior with blocking I/O | Each mapper waits in turn | Good candidate when many independent tasks wait | Can stall worker pool threads |
| Pure CPU-bound | Good baseline | No guaranteed benefit | Can speed up with easily splittable, heavy sources |
| Needs timeout/quota management | Yes | Yes | Yes |
| Guarantees higher speed | No | No | No |

There is no universal speed ranking across all applications. A mapper doing simple addition typically does not benefit from launching virtual threads. A mapper with substantial network wait time can benefit from concurrency, yet **the target service and connection pool** still determine effective parallelism.

### 14.1. `maxConcurrency = 1` vs. `map`

`mapConcurrent(1, mapper)` limits execution to one mapper at a time. However, it **is not a promise** of identical overhead, exception handling, or scheduling as sequential `map(mapper)`.

When virtual-thread mapping is unnecessary, `map` is usually simpler. When benchmarking, treat `mapConcurrent(1)` as a **distinct baseline configuration**, not completely identical to `map`.

### 14.2. Do not stack `parallel()` blindly

`parallelStream().gather(Gatherers.mapConcurrent(...))` can combine concurrency mechanisms, yet should not be viewed as "double parallelism" or automatically better.

Choose a clear benchmarking model:

- **CPU-bound** mapper: compare sequential loop/Stream against parallel stream.
- Independent **I/O-bound** mapper: compare sequential Stream against `mapConcurrent` at various limits.
- Mixed CPU + I/O: identify bottlenecks, bandwidth, pools, and side effects before adding concurrency.

When working with different data sources, also check whether `Spliterator` splits efficiently and whether each source has encounter order.


## 15. Ensuring mappers are thread-safe and non-interfering

Concurrent execution means multiple `mapper` invocations may run at the same time. Therefore, the Stream API rules for **stateless, non-interfering, and thread safety** must be strictly followed.

### 15.1. Wrong: writing to a shared `ArrayList`

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Gatherers;

List<String> shared = new ArrayList<>();

List<String> result = ids.stream()
    .gather(Gatherers.mapConcurrent(4, id -> {
        shared.add(id);  // UNSAFE.
        return "OK:" + id;
    }))
    .toList();
```

`ArrayList` is not safe for concurrent writes from multiple threads. `mapConcurrent` can run multiple mappers simultaneously, causing lost data, wrong order, or exceptions. Adding `Collections.synchronizedList` may partially address synchronization, yet **does not make write order** match encounter order.

The right way: have the mapper **return the result**, then use a terminal operation:

```java
List<String> result = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, id -> "OK:" + id))
    .toList();
```

This is an easy-to-test one-to-one pattern requiring no external list.

### 15.2. Do not modify the source inside mapper

Wrong in principle:

```java
// DO NOT:
// ids.stream()
//     .gather(Gatherers.mapConcurrent(4, id -> {
//         ids.remove(id); // Interferes with source being traversed.
//         return id;
//     }))
//     .toList();
```

Even on a `List` with no other threads, mutating the source structure during traversal can cause undefined results or `ConcurrentModificationException`. If data updates are required, build new results and run an explicit update step **after the pipeline completes**, with an appropriate transaction policy.

### 15.3. Observation counters differ from business state

`AtomicInteger` can be suitable for measuring `active/peak` in a test. However, do not use a shared counter to **determine ordered output values**:

```java
AtomicInteger sequence = new AtomicInteger();

List<String> result = ids.stream()
    .gather(Gatherers.mapConcurrent(4, id ->
        sequence.incrementAndGet() + ":" + id))
    .toList();
```

The counter increments in **mapper execution order**, not encounter order. Even though `result` is placed in source order, the sequence numbers attached to IDs may not increase consecutively by position.

If deterministic sequence numbers are needed, assign indices **before** running the mapper, or rely on an existing key. Never use thread scheduling as a generator of business keys.

## 16. Memory, throughput, and tail latency

`maxConcurrency` can help control the number of in-flight tasks, yet does not guarantee a RAM ceiling or response time.

### 16.1. Resource-consuming components

- Unprocessed inputs or results waiting to be emitted.
- Virtual threads and execution state of each mapper.
- HTTP/JDBC connections, request/response buffers, and native resources.
- Completed mapper results waiting for earlier elements to preserve encounter order.
- Collections retained by terminal operations such as `toList`.
- Internal structures of other stages: `sorted`, `distinct`, `groupingBy`.

Hence "only four concurrent mappers" **does not mean** "only needs memory for four small strings". A mapper may receive or create huge objects; a downstream `toList` still retains all output data.

### 16.2. Approximate concurrency and throughput model

In steady state, if a mapper takes an average of `W` seconds and `C` mapper slots stay continuously busy, a rough estimate is:

\[
\text{Ideal throughput} \approx \frac{C}{W}
\]

Mathematical example: `C = 5`, `W = 0.1` seconds gives an approximate ceiling of 50 tasks/second. This is **not an actual measurement** and not an enforced rate limit. Throughput can be lower due to head-of-line blocking, external service limits, timeouts, GC, or the source not supplying data fast enough.

Increasing `C` does not guarantee linear throughput scaling. When an external service becomes overloaded, `W` can grow; adding more concurrency then enlarges queues and worsens tail latency.

### 16.3. When does CPU-bound work not benefit?

Example:

```java
List<Long> squares = values.stream()
    .gather(Gatherers.mapConcurrent(
        100, x -> x * x))
    .toList();
```

If `values` is a small list and the mapper only multiplies two `long`s, the cost of preparing and scheduling many virtual threads can outweigh any gain. Compared to `values.stream().map(x -> x * x)`, `mapConcurrent` has no default advantage.

For CPU-heavy work on large sources, benchmark `parallelStream` or a suitable executor model, checking core count and work splitting. Virtual threads primarily improve **managing many waiting tasks**, not adding CPU capacity.

## 17. Combining with other Java Stream API stages

`mapConcurrent` is an intermediate step in a pipeline; it does not replace filtering, collecting, or aggregating.

### 17.1. Filtering before lookup to reduce I/O calls

```java
List<String> result = orders.stream()
    .filter(order -> order.isActive())
    .gather(Gatherers.mapConcurrent(
        4, order -> lookup(order.getId())))
    .toList();
```

This is **domain-typed pseudocode**: `orders`, the Order class, and `lookup` must be defined in an application. Meaning: skip records that do not need an API call **before** launching potentially I/O-heavy mappers.

Moving the filter after lookup to filter on retrieved data makes the system perform more calls. That may be a genuine requirement, but it must be stated explicitly.

### 17.2. Filtering after lookup when the condition is only known from the result

```java
List<String> paid = orderIds.stream()
    .gather(Gatherers.mapConcurrent(
        4, id -> fetchStatus(id)))
    .filter(status -> status.equals("PAID"))
    .toList();
```

This step must look up first because the predicate inspects the result. **Do not equate** `filter` after the mapper with skipping external calls; excluded orders were already looked up.

### 17.3. Collecting a summary report after mapping

```java
Map<String, Long> countByStatus = orderIds.stream()
    .gather(Gatherers.mapConcurrent(
        4, id -> fetchStatus(id)))
    .collect(java.util.stream.Collectors.groupingBy(
        status -> status,
        java.util.stream.Collectors.counting()));
```

Here `groupingBy` is a terminal collector, while `mapConcurrent` is an intermediate gatherer. Although mappers may run concurrently, the collector **does not automatically become a concurrent collector**; that is unnecessary for correctness.

If explicit display order is needed, sort `entrySet()` by value and key after grouping; do not rely on `HashMap` order.

### 17.4. Empty results

With an empty source, the mapper has no inputs to process:

```java
List<String> empty = Stream.<Integer>empty()
    .gather(Gatherers.mapConcurrent(
        3, n -> "ID-" + n))
    .toList();

System.out.println(empty); // []
```

Empty data is a valid case and should not fabricate placeholder results. If "not found" information is needed, define a result type or `Optional` per business rules.

## 18. Comprehensive Java 24+ verification program

This example checks **observed actual concurrency**, ordered results, one-to-one cardinality, empty source, invalid parameters, exceptions, and mappers running on virtual threads.

Create `MapConcurrentCheck.java`:

```java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Gatherers;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class MapConcurrentCheck {

    static void check(boolean ok, String message) {
        if (!ok) {
            throw new AssertionError(message);
        }
    }

    static String fakeLookup(
            int id,
            AtomicInteger active,
            AtomicInteger peak) {

        int now = active.incrementAndGet();
        peak.accumulateAndGet(now, Math::max);

        try {
            // Simulates requests with varying latencies.
            Thread.sleep(8L + (id % 3) * 4L);
            return "ID-" + id;
        } catch (InterruptedException ex) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(
                "Lookup interrupted", ex);
        } finally {
            active.decrementAndGet();
        }
    }

    public static void main(String[] args) {
        List<String> expected = IntStream.range(0, 20)
            .mapToObj(id -> "ID-" + id)
            .toList();

        for (int limit : new int[] {1, 2, 4}) {
            AtomicInteger active = new AtomicInteger();
            AtomicInteger peak = new AtomicInteger();

            List<String> actual = IntStream.range(0, 20)
                .boxed()
                .gather(Gatherers.mapConcurrent(
                    limit,
                    id -> fakeLookup(id, active, peak)))
                .toList();

            check(actual.equals(expected),
                "Wrong cardinality/order at limit=" + limit);

            check(peak.get() >= 1,
                "Non-empty source must invoke mapper");

            check(peak.get() <= limit,
                "Exceeded maxConcurrency=" + limit);

            check(active.get() == 0,
                "Mappers still active");
        }

        AtomicInteger called = new AtomicInteger();

        List<Integer> empty = Stream.<Integer>empty()
            .gather(Gatherers.mapConcurrent(
                2, n -> {
                    called.incrementAndGet();
                    return n + 1;
                }))
            .toList();

        check(empty.isEmpty() && called.get() == 0,
            "Empty source must not call mapper");

        List<Boolean> virtualThreads = Stream.of(1, 2, 3)
            .gather(Gatherers.mapConcurrent(
                2, n -> Thread.currentThread().isVirtual()))
            .toList();

        check(virtualThreads.equals(
                Arrays.asList(true, true, true)),
            "Mapper must use virtual thread");

        boolean rejectedZero = false;
        try {
            Gatherers.mapConcurrent(
                0, (Integer n) -> n * 2);
        } catch (IllegalArgumentException expectedError) {
            rejectedZero = true;
        }
        check(rejectedZero,
            "Must reject maxConcurrency = 0");

        boolean rejectedNullMapper = false;
        try {
            Gatherers.<Integer, Integer>mapConcurrent(
                2, null);
        } catch (NullPointerException expectedError) {
            rejectedNullMapper = true;
        }
        check(rejectedNullMapper,
            "Must reject null mapper");

        boolean mapperFailed = false;
        try {
            Stream.of(1, 2, 3)
                .gather(Gatherers.mapConcurrent(
                    2,
                    n -> {
                        if (n == 2) {
                            throw new IllegalStateException(
                                "Simulated failure");
                        }
                        return n * 10;
                    }))
                .toList();
        } catch (RuntimeException expectedError) {
            mapperFailed = true;
        }
        check(mapperFailed,
            "Failing mapper must cause pipeline to fail");

        List<Integer> shortResult = Stream.of(
                1, 2, 3, 4, 5)
            .gather(Gatherers.mapConcurrent(
                3, n -> n * 10))
            .limit(2)
            .toList();

        check(shortResult.equals(Arrays.asList(10, 20)),
            "limit did not preserve encounter order");

        System.out.println("PASS: Gatherers.mapConcurrent");
    }
}
```

When run successfully on Java 24+:

```text
PASS: Gatherers.mapConcurrent
```

The program **does not require `peak` to equal `limit`**, because actual concurrency depends on scheduling and callback speed. It also **does not measure throughput**: `Thread.sleep` simulates waiting rather than fully modeling an I/O client or service load.

### 18.1. Why not assert the exact number of mapper runs after `limit`?

The test only verifies that the first two results are in the right order. It **intentionally does not assert** that the mapper was called exactly twice, because the gatherer may launch additional in-flight tasks before downstream stops. This is a key aspect of the best-effort cancellation contract.

### 18.2. Checking equivalence with a sequential mapper

For a pure mapper, results can also be compared directly:

```java
List<String> reference = ids.stream()
    .map(id -> "ID-" + id)
    .toList();

List<String> concurrent = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, id -> "ID-" + id))
    .toList();

if (!reference.equals(concurrent)) {
    throw new AssertionError("Mapping result mismatch");
}
```

In this snippet `ids` is an externally created `List<Integer>`. Comparing with `List.equals` checks **element count, values, and positions**; do not use `Set.equals` because it ignores occurrence counts of duplicate values.

## 19. Benchmarking and system observability

A benchmark should compare the same workload, not just syntax:

| Test case | What to measure | Notes |
| --- | --- | --- |
| Lightweight CPU mapper | Latency/throughput of `map` vs. `mapConcurrent` | Virtual threads can add overhead. |
| Simulated waiting mapper | Completion time across concurrency levels | Do not extrapolate to real HTTP performance. |
| Mapper calling real read API | Latency p50/p95/p99, QPS, timeouts, errors | Watch rate limits and connection pools. |
| Multiple concurrent pipelines | Whole-service throughput, resource contention | Each pipeline has its own budget. |
| Mapper with large results | Heap, allocation, GC, head-of-line buffering | Output ordering can increase hold times. |

### 19.1. Do not infer real-world speed from `Thread.sleep`

An example with `Thread.sleep(100)` only shows that **waiting tasks can overlap**. It does not mean an external service will allow the same concurrency, or that every request takes 100 ms.

When measuring a real application, record:

- JDK, JVM flags, hardware, container limits, and network environment.
- `maxConcurrency` and number of concurrent pipelines.
- Connection pool, timeouts, retry count, and rate limits.
- Source element count, mapper latency distribution, and result sizes.
- Throughput, mean/p95/p99 latency, timeout/error rate, and GC.
- Error cases, empty data, and mutated sources.

### 19.2. With large data sizes, avoid collecting everything if unnecessary

`toList` collects all output data into memory. If only statistics are needed, use a terminal aggregation instead:

```java
long successCount = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, this::lookup))
    .filter(Result::isSuccess)
    .count();
```

This is an illustrative snippet inside an instance method with `ids` and the application's `Result` type. Even without retaining every result in a list, the mapper and in-flight results still consume resources. A `count` after `filter` needs to know which elements pass the predicate; however, do not put mandatory side effects inside the mapper and treat callback count as a general contract across all terminal operations.

## 20. Common mistakes and misconceptions

| Misconception / error | Consequence | Fix |
| --- | --- | --- |
| Using `mapConcurrent` on JDK 21 | No standard API exists | Use Java 24+ or an alternative model. |
| Forgetting `--enable-preview` on Java 22/23 | Compile/runtime error | Enable preview accordingly or upgrade to JDK 24+. |
| `maxConcurrency = 0` | `IllegalArgumentException` | Require limit ≥ 1. |
| Passing a null mapper | `NullPointerException` | Provide a valid mapper. |
| Treating `maxConcurrency` as requests/second | Easily exceeds service quota | Separate rate limiter from concurrency cap. |
| Treating one gatherer's limit as a system-wide budget | Multiple pipelines overload downstream together | Enforce a shared limiter at the service/client layer. |
| Thinking virtual threads add CPU cores | CPU-bound tasks do not speed up as expected | Identify the bottleneck and benchmark. |
| Thinking results arrive in mapper completion order | Logic relying on completion order breaks | `mapConcurrent` preserves encounter order. |
| Generating sequence numbers with a counter inside mapper | Sequence numbers/IDs do not match source order | Assign indices beforehand or use a source key. |
| Writing to a shared `ArrayList` inside mapper | Race condition, lost/corrupted data | Return results and use a terminal collector. |
| Mutating the source inside mapper | Violates non-interference | Process on a stable source, write afterward. |
| Using `limit(2)` to guarantee only two external requests | In-flight tasks may already have started | Cancellation is only best-effort. |
| Treating interrupt as rollback | Remote side effects may already have committed | Use idempotency and separate transaction/compensation. |
| No timeout configured | Mapper slot can hang indefinitely | Set deadlines/timeouts on the client. |
| Unbounded retries | Request storms, held slots | Bounded retries, backoff, circuit breaker. |
| Limiting mappers while each mapper fires multiple sub-requests | Exceeds concurrency on external systems | Enforce limits at the actual resource layer. |
| `HashSet` source while expecting ID order | No deterministic encounter order | Use `sorted` with a stable key. |
| Observing `mapConcurrent` slower than `map` for multiplying numbers | Overhead exceeds work | Use `map` for lightweight CPU tasks. |
| Holding huge results with `toList` | Heap and GC pressure | Collect only needed results, batch/stream carefully. |
| Measuring only one pipeline on an idle machine | Fails to reflect concurrent load | Measure realistic throughput and latency. |

## 21. Practice exercises

### Exercise 1 — Predicting order

Source `[1,2,3,4]` has a mapper for 1 that is slower than for 2, 3, and 4. Must the result of `gather(mapConcurrent(4, n -> "N-" + n)).toList()` come out in mapper completion order?

### Exercise 2 — Maximum limit

Does `mapConcurrent(3, mapper)` always run three mappers concurrently? Give two reasons why the actual `peak` might be lower than three.

### Exercise 3 — Distinguishing QPS

A service allows only 20 requests/second. Explain why `mapConcurrent(5, callApi)` is not enough to stay within quota. What other component is needed?

### Exercise 4 — Choosing a solution for CPU-bound work

A problem needs to square one million integers in RAM. Explain why you should not default to `mapConcurrent(100, mapper)` and list two alternatives to benchmark.

### Exercise 5 — Task cancellation

There is `limit(2)` right after `mapConcurrent(6, remoteCall)`. Is it guaranteed that only two remote calls execute? If the calls have money-transfer side effects, what policy is required?

### Exercise 6 — Writing a concurrency counter

Use `AtomicInteger active` and `AtomicInteger peak` to verify `maxConcurrency = 4`. Why must the decrement be placed inside `finally`?

### Exercise 7 — Unordered source

A `HashSet<Integer>` holds IDs 5, 1, 4, 2, 3. Obtain mapping results in ascending ID order while still using `mapConcurrent`.

### Exercise 8 — Exceptions

A mapper throws `IllegalStateException`. State the error-propagation contract of `mapConcurrent` and explain why you should not assert an exact unpromised wrapper/cause type.

### Exercise 9 — Concurrent execution of multiple pipelines

A server handles 20 concurrent web requests, each using `mapConcurrent(10, ...)`. Can more than 10 requests hit the backend system-wide? Where should the limiter be placed?

### Exercise 10 — Filtering before and after map

If an element already has an `active` flag in the original data, why does `filter(active)` before `mapConcurrent(fetch)` usually save I/O? When must filtering happen afterward?

### Exercise 11 — Comparing APIs

Contrast `Stream.map`, `mapConcurrent`, `parallelStream`, and a dedicated `CompletableFuture`/executor regarding concurrency control, ordering, and lifecycle.

### Exercise 12 — Designing a benchmark

Design an experiment to choose `maxConcurrency` from `{1,2,4,8,16}` when querying a connection-limited API. List at least six metrics/settings to record and criteria for stopping increases.

## 22. Answers and guidance

**Exercise 1.** No. On an ordered stream, `mapConcurrent` preserves **encounter order** of results, so the output is `[N-1,N-2,N-3,N-4]` when all mappers succeed. Execution scheduling and mapper completion order may differ.

**Exercise 2.** No. `3` is an **upper bound**; the source may have only one element, or mappers may be too fast or upstream too slow to keep three active simultaneously. Scheduling and downstream steps can also affect this.

**Exercise 3.** Concurrency is the number of **in-flight** requests, whereas a 20 requests/second quota is a **rate**. If requests respond fast, five slots can send far more than 20 requests/second. Use a time-based rate limiter alongside the concurrency cap and timeouts.

**Exercise 4.** Virtual threads do not add CPU cores, and dispatching many mappers has overhead. Compare a sequential loop or `Stream.map` against `parallelStream`/an appropriate primitive stream; verify correctness and benchmark on real data and hardware.

**Exercise 5.** No. Some calls may already be in-flight and cancellation is best-effort. You need idempotency, commit-status visibility, bounded retries, and partial-failure/compensation handling where appropriate.

**Exercise 6.**

```java
int now = active.incrementAndGet();
peak.accumulateAndGet(now, Math::max);
try {
    return process(id);
} finally {
    active.decrementAndGet();
}
```

`finally` keeps metrics accurate on success, exception, or interruption; `peak <= 4` is what should be verified, not necessarily `peak == 4`.

**Exercise 7.**

```java
List<String> labels = ids.stream()
    .sorted()
    .gather(Gatherers.mapConcurrent(
        3, id -> "ID-" + id))
    .toList();

// [ID-1, ID-2, ID-3, ID-4, ID-5]
```

`ids` is the `HashSet<Integer>` in the problem. `sorted` establishes encounter order before the mapper.

**Exercise 8.** When a mapper's result is due downstream yet the mapper completed with an exception, the gatherer rethrows it as a `RuntimeException` and attempts to cancel remaining tasks. Check error behavior at the contract level without relying on wrapper/cause names or side-effect ordering if unpromised by the API.

**Exercise 9.** Yes. Each gatherer enforces only a local cap, so 20 pipelines can simultaneously run many mappers. If the application-wide quota is 10, a shared limiter is needed at the client/backend adapter or outbound dispatcher, not just `mapConcurrent(10)` per pipeline.

**Exercise 10.** Filtering first avoids calling `fetch` for inactive elements. If the condition is only known after calling the API, you must map first and filter on the result, accepting the cost of the calls already made.

**Exercise 11.** Sequential `map` runs one after another; `mapConcurrent` maps on virtual threads with a cap while preserving encounter order; `parallelStream` splits the pipeline without an equivalent mapper cap parameter; `CompletableFuture`/custom executors give fine-grained control but require managing ordering, errors, cancellation, and shutdown yourself.

**Exercise 12.** Keep the same ID set, background load, client, and timeouts; test `C={1,2,4,8,16}`, recording throughput, p50/p95/p99 latency, timeout/error rate, pool utilization, in-flight count, retries, CPU, allocation/GC, and response size. Stop increasing when errors/wait times rise, backend nears quota, or throughput stops improving meaningfully. Measure both single-pipeline and multi-pipeline concurrency.

## 23. Checklist for bringing `mapConcurrent` into an application

- [ ] Compile and runtime JDK support **Java 24+** or proper preview flags on older releases.
- [ ] Clear understanding of the **one input → one output** relationship on mapper success.
- [ ] `maxConcurrency >= 1` with a practical upper bound.
- [ ] Concurrency cap distinguished from **QPS/rate limit**.
- [ ] Shared limiter exists if multiple pipelines share a downstream service with a global quota.
- [ ] Mapper is independent, thread-safe, and non-interfering; never modifies source or shared collections.
- [ ] `mapConcurrent` chosen for many **independent waiting** tasks, not merely to "run fast".
- [ ] Do not rely on log order or completion order to define encounter order.
- [ ] If source is unordered, business ordering is established/sorted when needed.
- [ ] Accounted for head-of-line blocking caused by preserving order.
- [ ] I/O mappers have timeouts/deadlines and appropriately sized client pools.
- [ ] Retries, idempotency, and rate limits are designed separately.
- [ ] Do not treat interruption/cancellation as rollback for committed side effects.
- [ ] Do not assume `limit(n)` ensures exactly n mappers were invoked.
- [ ] Considered result sizes and `toList`/buffering costs.
- [ ] Tested empty source, limits 1/2/N, throwing mapper, null mapper, and duplicate inputs.
- [ ] Verified `peak <= maxConcurrency`, without requiring all slots to be filled.
- [ ] Compared results against sequential `map` on pure mappers.
- [ ] Measured latency, throughput, errors, and resources under representative load.
- [ ] Do not combine `parallel()` with `mapConcurrent` based on guesswork.
- [ ] Clarified who owns closing resources if the source is `Files.lines`/a cursor.
- [ ] Never log sensitive data, API keys, or secret payloads inside mapper logs.

## 24. Summary and references

`Gatherers.mapConcurrent(maxConcurrency, mapper)` brings bounded concurrency into a Java Stream API pipeline:

```java
List<String> result = ids.stream()
    .gather(Gatherers.mapConcurrent(
        4, id -> fetchStatus(id)))
    .toList();
```

The sample snippet assumes `ids` and `fetchStatus` belong to the application program.

Key mindset to keep:

1. **One-to-one:** a normal mapper produces one result per input.
2. **Bound:** `maxConcurrency` is a **ceiling on concurrent mapper invocations**, not QPS.
3. **Virtual threads:** helpful for many independent waiting tasks; they do not add CPU cores.
4. **Ordering:** output preserves source encounter order when the source is ordered, not completion order.
5. **Cancellation:** when downstream stops requesting more, cancellation is **best-effort** and does not roll back external tasks.
6. **Errors:** mapper failures surface via `RuntimeException` when the corresponding result is due to be emitted.
7. **Resources:** configure timeouts, rate limiters, connection pools, memory limits, and lifecycle management.
8. **Verification:** measure peak concurrency, compare against sequential results, and benchmark on realistic workloads.

Official references:

- [Javadoc Java 24 — Gatherers.mapConcurrent](https://docs.oracle.com/en/java/javase/24/docs/api/java.base/java/util/stream/Gatherers.html#mapConcurrent(int,java.util.function.Function))
- [Oracle Java 24 — Stream Gatherers](https://docs.oracle.com/en/java/javase/24/core/stream-gatherers.html)
- [OpenJDK JEP 485 — Stream Gatherers](https://openjdk.org/jeps/485)

When these contracts are well understood, you can use Java Stream Gatherers to process many independent lookups with controlled concurrency, keep output ordering predictable, and avoid confusing parallelism, rate limiting, cancellation, and resource safety.
