# Stateless Functions, Side Effects, and Result Observability

## 1. Why is this part of the Stream contract?

The Java Stream API lets you describe **what needs to be computed** using a pipeline consisting of a data source, intermediate transformations, and a terminal operation. The library has the right to defer, fuse, execute in parallel, or skip unnecessary steps, as long as it still preserves the result specified by the Stream contract. Therefore, code inside `filter`, `map`, `flatMap`, `peek`, or element-processing functions should not implicitly depend on how many times it is called, on which thread, or in what order.

This is core content of the **Pipeline Contracts and Lifecycle** chapter in **JAVA_STREAM_API**: learning how to process data declaratively with lazy pipelines, while knowing the boundary between an operation's result and side effects that may occur when running the pipeline.

```text
Data source         Intermediate (lazy)                   Terminal
List<Order>  ────► filter(...) ────► map(...) ─────► collect(...)
                         │               │                 │
                describes condition  describes mapping  triggers processing,
                                                    creates observable result
```

The following example only creates a pipeline; when there is no terminal operation yet, the `map` function does not need to run:

```java
import java.util.List;
import java.util.stream.Stream;

List<Integer> numbers = List.of(1, 2, 3, 4);

Stream<Integer> pipeline = numbers.stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * 10); // Only describes the pipeline, has not processed elements yet.

List<Integer> result = pipeline.toList(); // [20, 40]; terminal triggers processing.
```

The examples use Java 17+ (which has `Stream.toList()`); each Stream should perform only **one** terminal operation. After a terminal operation, the Stream has been consumed and cannot be reused to run another terminal operation.

## 2. Distinguishing stateless, non-interfering, and pure functions

Three properties often go together yet are not synonymous:

| Property | Meaning in a pipeline | Example |
| --- | --- | --- |
| **Stateless** | The result of processing one element does not depend on state that may change from processing other elements of the same pipeline. | `n -> n * 2`; `s -> s.trim()` |
| **Non-interfering** | The processing function does not modify the data source being traversed by the Stream, except for sources supporting concurrent modification under their own contract. | Reading `order.amount()` without adding/removing elements of the source list. |
| **Pure** | Given the same input and the same immutable context, returns the same result and causes no observable side effects. | `n -> Math.abs(n)` for an `int` value. |

The Stream documentation requires that *behavioral parameters* (lambdas/method references passed to operations) generally be **non-interfering** and **stateless**. A stateless lambda can still have side effects, such as `n -> { logger.info("{}", n); return n * 2; }`; hence checking statelessness alone is not enough to rely on safe, easily testable behavior.

### 2.1. Stateless lambdas

```java
import java.util.List;
import java.util.Locale;

List<String> names = List.of(" An ", "Bình", "  ", "Chi");

List<String> normalized = names.stream()
    .map(String::trim)
    .filter(name -> !name.isBlank())
    .map(name -> name.toUpperCase(Locale.ROOT))
    .toList();

// [AN, BÌNH, CHI]
```

Each transformation depends only on the current element and the constant `Locale.ROOT`. A captured variable can also be safe **if the contents used remain immutable throughout execution**:

```java
int minLength = 3;
List<String> selected = names.stream()
    .map(String::trim)
    .filter(name -> name.length() >= minLength)
    .toList();
```

Java requires local variables captured by a lambda to be `final` or *effectively final*, yet this compilation rule **does not make every captured object immutable**. For example, a `Set` reference variable may stay unchanged while the `Set`'s contents are constantly mutated.

### 2.2. Stateful lambdas: one result depending on previous elements

```java
import java.util.HashSet;
import java.util.Set;

Set<String> seen = new HashSet<>();

List<String> unique = names.stream()
    .map(String::trim)
    .filter(name -> seen.add(name)) // WRONG APPROACH: depends on and mutates seen.
    .toList();
```

`seen.add(name)` both checks and mutates state shared across `filter` invocations. On a sequential Stream, the result may look right in a specific scenario, yet the lambda is no longer stateless. Switching to `.parallel()` can create race conditions because `HashSet` is not safe for concurrent access. Using a synchronized collection still does not turn the filter into a stateless function; which element gets accepted also depends on scheduling.

Delegate deduplication to an operation with a clear contract:

```java
List<String> unique = names.stream()
    .map(String::trim)
    .distinct()
    .toList();
```

**Note:** `distinct()`, `sorted()`, `limit()`, and `skip()` are *stateful intermediate operations*: the library itself may need to remember seen elements, hold a buffer, or track position. This **does not contradict** the requirement that lambdas passed by the programmer must be stateless. State is managed internally inside the operation according to its contract; some of these operations have memory overhead or reduced efficiency in parallel execution, especially when encounter order must be preserved.

### 2.3. Non-interference with the source

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> source = new ArrayList<>(List.of(1, 2, 3));

// DO NOT DO THIS: mutating the source while the Stream itself is traversing it.
source.stream()
    .filter(n -> {
        if (n == 2) source.add(4);
        return n % 2 == 0;
    })
    .forEach(System.out::println);
```

The outcome may be `ConcurrentModificationException`, abnormal behavior, or other errors depending on the source and timing; **do not rely on an exception always being thrown**. If elements need to be added or removed, produce a result list first and update the source after the pipeline completes, or use a structure/algorithm with an explicit concurrency contract.

## 3. Side effects: return value differs from what happens externally

A **side effect** is an observable state change or interaction beyond the value a lambda returns: adding an element to an external list, incrementing a counter, writing logs, sending requests, updating a database, writing files, or mutating a shared object.

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> output = new ArrayList<>();

List<Integer> doubled = List.of(1, 2, 3).stream()
    .map(n -> {
        output.add(n);        // Side effect on external state.
        return n * 2;         // Result of the transformation.
    })
    .toList();

// doubled is the declarative result to obtain: [2, 4, 6].
// Do not design algorithms relying on output.
```

Even though the sequential example might produce `output = [1, 2, 3]`, this side result is not part of `map`'s contract. When optimizations, short-circuiting, or parallelization are applied, we should not infer invocation counts, order, or callback execution threads solely from the final result.

Side effects are **not strictly forbidden**. For example, `forEach` is a terminal operation used to perform an action on elements. The point is to place side effects where they are genuinely needed, understand ordering/thread limitations, and avoid using them as an implicit part of a computation that the Stream is permitted to optimize away.

### 3.1. `count()` may skip running `map()` or `peek()`

```java
import java.util.List;

List<String> items = List.of("a", "b", "c");

long count = items.stream()
    .map(item -> {
        System.out.println("map: " + item);
        return item.toUpperCase();
    })
    .count();

// count == 3, but do not expect 3 "map" lines.
```

With a known-size source such as `List`, and operations that do not change element count such as `map`, the Stream can compute `count()` directly from the source size **without traversing elements**. Consequently `map` (and `peek` in a similar case) may not run. This is a valid optimization, not a JDK bug. With `filter`, the library usually needs to evaluate the predicate to know how many elements remain, because `filter` can change the count.

Do not use `map`, `filter`, or `peek` to force external work to execute and then just call `count()` to trigger it. It is better to clearly determine whether you need to **count**, **transform**, or **perform an action** and pick the corresponding terminal operation.

### 3.2. Short-circuiting only needs to process part of the source

```java
boolean hasNegative = List.of(4, 8, -3, 10, 12).stream()
    .anyMatch(n -> n < 0);

// true; no need to examine remaining elements once a matching element is found.
```

`anyMatch`, `allMatch`, `noneMatch`, `findFirst`, `findAny`, operations combined with `limit`, and so on can terminate once enough information is available. In a parallel pipeline, some running tasks may still process additional elements before receiving the stop signal. Thus there is no promise that a callback will run for **exactly N elements** just because you observed a result on a previous run.

## 4. Result observability: what is guaranteed?

In Streams, three layers of observability should be distinguished:

1. **Terminal return value**: for example `List` from `toList()`, `Map` from `collect(...)`, `long` from `count()`; this is the output to assert against.
2. **Intentional terminal side effect**: for example `forEach(System.out::println)`; executing the action is the purpose of the operation, though order and thread still depend on the specific contract.
3. **Side effects inside intermediate steps**: logging, incrementing counters, mutating state inside `map`/`filter`/`peek`; can be optimized away or executed on different threads/orders and therefore are not complete proof of how elements were processed.

| Pipeline | Can be asserted | Cannot be inferred |
| --- | --- | --- |
| `list.stream().map(f).toList()` | Returned list contains the transformation results in encounter order if the source is ordered. | All side effects inside `f` are safe or usable for synchronization. |
| `list.stream().map(f).count()` | Element count per `count()` contract. | `f` was called exactly once for every element. |
| `stream.anyMatch(p)` | At least one element satisfies `p` if it returns `true`. | `p` examined the entire source. |
| `stream.parallel().forEach(action)` | `action` is executed for the elements traversed by the terminal per contract. | Order matches source order, or actions run on the same thread. |
| `stream.forEachOrdered(action)` | If the Stream has encounter order, actions are executed in that order. | All actions run on the same thread or have the same cost as `forEach`. |

`forEachOrdered` also guarantees that executing the action on one element *happens-before* the action on the next element. It is useful when order is genuinely needed, though it can limit parallel execution capability. `forEach` makes no promise to preserve encounter order, especially when using a parallel stream.

### 4.1. `peek()` is for temporary observation, not an audit mechanism

```java
List<Integer> result = List.of(1, 2, 3, 4, 5).stream()
    .filter(n -> n % 2 == 0)
    .peek(n -> System.out.println("after filter: " + n))
    .map(n -> n * n)
    .toList();

// result == [4, 16]. peek is useful for inspecting data flow during debugging.
```

`peek` is an intermediate operation that only gets a chance to run when elements actually pass through that pipeline segment. It does not guarantee one log per source element, does not guarantee log order on a parallel stream, and can be elided from execution when optimizations do not alter the terminal result. Hence `peek` is unsuitable for mandatory business event logging, auditing, billing, inventory updates, or official statistics.

If events must be recorded **strictly for the selected elements**, determine them with a pure computation first, then perform an intentional recording step along with an error-handling/retry strategy suited to the system:

```java
List<Integer> selected = List.of(1, 2, 3, 4, 5).stream()
    .filter(n -> n % 2 == 0)
    .toList();

selected.forEach(n -> System.out.println("Selected: " + n));
```

In real systems, event recording workflows also require transaction and idempotency management; the Stream API does not provide those guarantees by itself.

## 5. Replace external mutation with terminal results

For most problems, the clear and safe way to process data is using `filter` to select, `map` to transform, `reduce` to combine with an associative operation, or `collect` to gather elements into a result structure.

### 5.1. Avoid using `forEach` to manually assemble results

```java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = List.of(1, 2, 3, 4, 5);

List<Integer> bad = new ArrayList<>();
numbers.stream()
    .filter(n -> n % 2 == 0)
    .forEach(n -> bad.add(n * n)); // Couples result creation to external state.

List<Integer> good = numbers.stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * n)
    .toList(); // [4, 16]
```

In a sequential stream, `bad` may work yet ties the program to mutation. If switched to `parallelStream()`, concurrent `ArrayList.add` calls can cause races and corrupt results. `good` expresses the intent right in the pipeline; the Stream manages gathering the result itself. `Stream.toList()` returns an unmodifiable list; if a mutable list is needed, `collect(Collectors.toCollection(ArrayList::new))` can be used.

### 5.2. `reduce` for combining, `collect` for managed accumulation

```java
import java.util.List;

long sum = List.of(10L, 20L, 30L).stream()
    .reduce(0L, Long::sum); // 60
```

Functions used with `reduce` must obey *associativity* and have an appropriate identity value. Do not use a shared `ArrayList` as the identity of `reduce` and append elements to it: in a parallel pipeline, branches must be able to combine results properly without relying on shared mutation.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

List<Integer> collected = List.of(1, 2, 3, 4).parallelStream()
    .collect(Collector.of(
        ArrayList::new,                    // supplier: creates a new accumulation container
        ArrayList::add,                    // accumulator: adds to the branch's container
        (left, right) -> {                 // combiner: merges results of two branches
            left.addAll(right);
            return left;
        }
    ));

// [1, 2, 3, 4] with this source having encounter order.
```

This is mutation **inside the `Collector` mechanism**, designed via `supplier`, `accumulator`, and `combiner`, rather than lambdas concurrently writing into an external list. A collector can safely use a mutable container in a parallel stream if it satisfies the identity, associativity, splitting/combining constraints, and declared characteristics. When custom logic is not needed, prefer built-in collectors such as `toList`, `groupingBy`, `counting`, and `summingLong`.

### 5.3. Business example: calculating revenue by customer

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Order(String customer, long amount, boolean paid) {}

List<Order> orders = List.of(
    new Order("An", 100, true),
    new Order("Bình", 80, true),
    new Order("An", 120, true),
    new Order("An", 500, false),
    new Order("Chi", -20, true)
);

Map<String, Long> revenueByCustomer = orders.stream()
    .filter(Order::paid)
    .filter(order -> order.amount() > 0)
    .collect(Collectors.groupingBy(
        Order::customer,
        Collectors.summingLong(Order::amount)
    ));

// {An=220, Bình=80} (Map does not guarantee traversal order by default).
```

Here there is no external mutable counter/revenue variable for `filter` or `map` to update. The result is represented as a `Map<String, Long>`, so we can inspect it directly by key, reuse it for downstream processing, or compare it against expected output. If a custom collector is needed, keep the same principle: do not arbitrarily share an accumulation container across parallel branches.

## 6. Parallel execution exposes flawed assumptions

`parallel()` lets a Stream split work, yet **does not automatically make stateful callbacks thread-safe** and does not promise they run on specific threads. For example:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

IntStream.range(0, 100_000)
    .parallel()
    .forEach(shared::add); // UNSAFE: ArrayList is written concurrently.

// Cannot trust shared.size() to always be 100_000.
```

Fix it by letting the terminal operation produce the result:

```java
List<Integer> values = IntStream.range(0, 100_000)
    .parallel()
    .boxed()
    .toList();

// values.size() == 100_000; preserves encounter order of IntStream.range.
```

Changing `shared` to `Collections.synchronizedList(...)` only addresses part of access safety; it does not make the completion order of `forEach` calls match source order, and still forces workers to contend on a lock. Similarly, using `AtomicInteger` for a counter only prevents lost concurrent updates; it does **not** guarantee how many times the callback runs when a pipeline short-circuits or optimizes away intermediate steps.

If actions must execute strictly in encounter order:

```java
IntStream.rangeClosed(1, 5)
    .parallel()
    .forEachOrdered(System.out::println); // Prints 1, 2, 3, 4, 5 in order.
```

Do not assume parallel will be faster: small tasks, stateful operations, encounter order requirements, I/O, or resource contention can make splitting/combining overhead outweigh the benefit. Before parallelizing, verify that computations are independent, collectors are appropriate, and measure performance with realistic data volumes.

## 7. Implications for lifecycle, resources, and testing

**Lifecycle.** Intermediate operations are lazy; a terminal operation triggers processing yet may terminate early or skip some stages due to optimization. Once consumed, a Stream cannot be reused. Some I/O sources like `Files.lines` own resources and require closing the Stream with `try-with-resources`:

```java
import java.nio.file.Files;
import java.nio.file.Path;
import java.io.IOException;
import java.util.List;
import java.util.stream.Stream;

static List<String> nonBlankLines(Path path) throws IOException {
    try (Stream<String> lines = Files.lines(path)) {
        return lines.map(String::trim)
            .filter(line -> !line.isEmpty())
            .toList();
    }
}
```

**Testing.** Instead of using log line counts or external variable values to prove a stage ran, compare the terminal result:

```java
List<Integer> actual = List.of(1, 2, 3, 4).stream()
    .filter(n -> n % 2 == 0)
    .map(n -> n * n)
    .toList();

if (!actual.equals(List.of(4, 16))) {
    throw new AssertionError("Unexpected result: " + actual);
}
```

For pipelines involving randomness, time, I/O, or external state updates, separate computational logic into independently testable functions; manage side effects in the corresponding execution layer. If a critical requirement is processing each event exactly once, persisting durably, and recovering on failure, design dedicated transactional/idempotency guarantees at the application layer.

### Self-review checklist when writing Streams

| Question | Sign that refactoring is needed |
| --- | --- |
| Does the lambda read/write a mutable variable shared across elements? | `seen.add(...)`, `counter++`, `result.add(...)` inside `map`/`filter`. |
| Does the lambda modify the source being traversed? | `source.add(...)`, `source.remove(...)` inside a callback. |
| Is code relying on an intermediate stage definitely running? | Mandatory logging in `peek`, business processing in `map` followed only by `count`. |
| Is code relying on callback order or thread? | `parallel().forEach(...)` to build an ordered list or update unsynchronized state. |
| Can the requirement be expressed via a return value? | Use `map` + `toList`, `reduce`, `groupingBy`, `summingLong` instead of external mutation. |
| Are source/resource lifecycles managed? | Unclosed Stream from a file, or attempting to reuse a Stream after a terminal operation. |

## 8. Check your understanding

1. Does a pipeline calling `.map(x -> { log(x); return x; }).count()` on a `List` guarantee logging for every element? **No**: `count` can know the size in advance and skip `map`.
2. Why can `filter(x -> seen.add(x))` run "correctly" sequentially yet still violate the contract? **Because the lambda depends on and mutates shared state across calls**; the result depends on processing order and is unsafe in parallel.
3. `distinct()` has state, so does it violate the stateless requirement? **No**: that is a stateful operation managed by the Stream; what must be avoided is introducing mutable state across lambda invocations yourself.
4. To collect a list from a parallel stream, should you use `forEach(shared::add)` or `collect`/`toList`? **Use a result-returning terminal operation** so the Stream manages accumulation and combining.
5. Does `forEachOrdered` mean the callback always runs on the same thread? **No**: it guarantees encounter order when present and a happens-before relationship between consecutive actions, not a fixed thread.

**Practical principle:** treat the terminal result as the primary contract of the pipeline, keep lambdas stateless and non-interfering with the source, use collectors to gather data, and move mandatory side effects into a clearly controlled execution step. That way the pipeline remains easy to reason about even if the JDK optimizes differently or the program switches from sequential to parallel.
