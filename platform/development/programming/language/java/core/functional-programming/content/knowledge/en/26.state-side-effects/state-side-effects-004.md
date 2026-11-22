# Risks of Adding Results to an `ArrayList` from a Parallel `forEach()` in Java Stream

When switching a Stream pipeline to parallel mode using `parallel()` or `parallelStream()`, a seemingly natural piece of code can become **unsafe**:

~~~java
List<Integer> results = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(results::add); // UNSAFE
~~~

This is an **anti-pattern example** and should not be run in real programs. `ArrayList` is a structure with mutable state that is **not safe for multiple threads to modify structurally at the same time**. When `forEach` is executed in parallel, calls to `results.add(...)` can interleave, causing lost elements, data corruption, or runtime errors. The fact that the program **occasionally** prints exactly 10,000 elements does not prove it is safe.

The most appropriate solution when the goal is to **build a result collection** is: **let the Stream collect it itself using `collect()` or `toList()`**, instead of using `forEach()` to mutate a shared collection.

~~~java
List<Integer> results = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();

System.out.println(results.size()); // 10000
~~~

This snippet uses `IntStream` to generate integers, `boxed()` to convert to `Stream<Integer>`, and `toList()` as the terminal operation to create the list. The `IntStream.range` source has an encounter order from 0 to 9,999; `Stream.toList()` preserves that encounter order even though the pipeline runs in parallel.

## 1. Core Problem: Shared State and Side Effects

In the Stream API, functional-style programming generally favors transformations that **do not depend on external mutable state**:

~~~java
List<String> labels = numbers.parallelStream()
        .filter(n -> n > 0)
        .map(n -> "N=" + n)
        .toList();
~~~

The `numbers` variable is assumed to be a stable source list during processing. `filter` decides based on each element, `map` produces output values, and `toList` collects the results. The code does not modify any external collection during each lambda invocation.

Conversely:

~~~java
List<String> external = new ArrayList<>();

numbers.parallelStream()
        .filter(n -> n > 0)
        .forEach(n -> external.add("N=" + n)); // Wrong if run in parallel
~~~

`external.add(...)` is a **side effect**: it mutates state outside the element being processed and outside the framework's collection mechanism. All tasks reference the same `external`; there is no contract in `forEach` that automatically protects a regular `ArrayList`.

There are two concepts to distinguish:

- **Stateless lambda:** the result depends primarily on the input element; it does not require writing to a shared mutable variable.
- **Thread-safe accumulation:** accumulation state may be mutated, but the framework or data structure is designed to coordinate updates safely.

`collect()` also has a mutable accumulator internally, but accumulation is managed according to the Collector contract. This is fundamentally different from passing an external `ArrayList` into `forEach()`.

## 2. Why Is `ArrayList.add()` Unsafe When Multiple Threads Write Concurrently?

`ArrayList` typically maintains internal state related to its size (`size`) and backing element array. When adding an element, the logical operation involves checking/allocating capacity, writing the element, and updating the size. There is no guarantee that these steps form an atomic operation across multiple threads.

Imagine two threads both reading `size = 5`:

~~~text
Initial state: size = 5

Thread A                           Thread B
--------                           --------
Read size = 5                      Read size = 5
Choose insert index 5              Choose insert index 5
Write element A at index 5         Write element B at index 5
Increment/update size              Increment/update size

Possible consequences: one write overwrites the other, the counter does not
reflect the number of additions, or the internal structure becomes corrupted.
~~~

This is a **race illustration model**, not a strict instruction-by-instruction description for a specific JDK version. Some common failures under concurrent access:

1. **Lost update:** two add operations are not fully reflected, so `list.size()` is smaller than the expected number of elements.
2. **Incorrect or missing content:** the result may contain unexpected positions or missing values, even when the size appears valid.
3. **Exceptions:** in some cases, index errors, resizing exceptions, or other errors may occur due to inconsistent internal state.
4. **Unpredictable order:** even a thread-safe collection that allows multiple concurrent `add` calls does not automatically guarantee source order.
5. **Hard to reproduce:** small datasets or machines with fewer cores may happen to produce the right result, then fail in another environment.

Therefore, do not write a unit test that "runs once and sees the right size" to conclude thread safety. The bug is in the **concurrency contract**, not the probability of a single test run.

### Just Calling `parallel()` Can Change Safety Conditions

The snippet:

~~~java
List<Integer> sink = new ArrayList<>();
IntStream.range(0, 100).forEach(sink::add);
~~~

In a normal sequential pipeline, the add action is invoked sequentially. However, after changing it to:

~~~java
List<Integer> sink = new ArrayList<>();
IntStream.range(0, 100).parallel().forEach(sink::add);
~~~

the action can be invoked from multiple threads. The exact same `sink::add` becomes an unsafe side effect. The two examples above are **independent illustrative snippets**, not placed concurrently in the same scope with the same variable name.

Splitting into multiple `stream()` calls or adding `peek()` should not be treated as a workaround. The point of failure remains the mutable collection shared across concurrent actions.

## 3. `forEach()` Is Not a Result-Collection Tool

`forEach(Consumer<? super T>)` is a **terminal operation** used to perform an action on each element. The Stream documentation describes it as *explicitly nondeterministic* in a parallel pipeline: the action may be invoked on whatever thread the library chooses; execution order is not guaranteed merely because the source has an encounter order.

~~~java
IntStream.range(0, 10)
        .parallel()
        .forEach(System.out::print);
~~~

The snippet above is syntactically valid, but the order of printed digits **has no fixed outcome**. Even if `System.out.print` has appropriate internal synchronization for individual calls, that **does not restore encounter order**.

Distinguish the goals:

| Need | Tool to Use |
| --- | --- |
| Build a `List<T>` from transformed results | `map(...).toList()` |
| Need an `ArrayList<T>` that supports add/remove | `collect(Collectors.toCollection(ArrayList::new))` |
| Build a `Set<T>` of distinct values | `collect(Collectors.toSet())` or an appropriate Set collector |
| Compute a sum | `mapToInt(...).sum()` or `reduce(...)` |
| Write results to an external system in a controlled way | Define ordering, I/O protocol, backpressure, and error handling, rather than defaulting to a shared mutable list |
| Observation/debugging aid only | Consider structured logging; do not use `peek` or `forEach` to produce business results |

If the final goal is a collection, `forEach` paired with `add` is usually the **wrong level of abstraction**. Express the requirement directly using a collection-returning terminal operation.

## 4. Preferred Approach: `toList()` Preserves Results Without Sharing a List

Since Java 16, `Stream.toList()` creates a `List<T>` that does not support structural modification:

~~~java
List<Integer> values = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();
~~~

With an ordered source like `IntStream.range`, the result preserves **encounter order**. The framework manages the collection process; the user does not pass an external `ArrayList` across multiple threads.

**Important note on mutability:** `Stream.toList()` returns an **unmodifiable** List. Calling `values.add(10_000)` throws `UnsupportedOperationException`. If you need to modify the result, choose a collector that returns an appropriate structure or make a copy:

~~~java
List<Integer> mutableCopy = new ArrayList<>(values);
mutableCopy.add(10_000);
~~~

Using a copy is reasonable when a post-processing step needs to mutate data. Do not use `Stream.toList()` and assume it behaves the same as `Collectors.toCollection(ArrayList::new)`.

### `Collectors.toList()` Differs from `Stream.toList()`

~~~java
List<Integer> a = source.stream().collect(Collectors.toList());
List<Integer> b = source.stream().toList();
~~~

This is an illustrative snippet with `source` being an existing `List<Integer>`. Both produce collected results, but **`Collectors.toList()` makes no guarantees about the implementation type or mutability of the returned List**, whereas `Stream.toList()` guarantees it is unmodifiable. If you want an `ArrayList` guaranteed to be mutable, use `toCollection(ArrayList::new)`.

Do not reuse the same `Stream` object for two terminal operations; in the example above, the two `source.stream()` calls create two new Streams.

## 5. Need a Mutable `ArrayList`: `Collectors.toCollection(ArrayList::new)`

If the requirement is to return **specifically an `ArrayList`** to which results can be added or removed:

~~~java
ArrayList<Integer> results = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));

results.add(-1);
~~~

This snippet requires importing `java.util.ArrayList`, `java.util.stream.IntStream`, and `java.util.stream.Collectors`. This approach differs from `parallel().forEach(external::add)` in two ways:

1. The supplier `ArrayList::new` creates **accumulation containers managed by the Collector**. When needed, the framework creates separate containers for each unit of work, accumulates independently, and then combines the results.
2. The framework operates under the **non-concurrent collector contract**; it does not require multiple threads to concurrently call `add` on the same regular `ArrayList`.

Therefore, a collector can be safe with parallel streams even though the `ArrayList` in each container **is not a thread-safe collection**. Correctness comes from how the framework partitions and merges, not from `ArrayList` secretly supporting multithreading.

### Result Ordering

With an ordered source, a list-based collector, and appropriate combining rules, the result preserves encounter order. `parallel()` does not mean "the resulting list is definitely shuffled." However, if the source itself is marked unordered, you should not infer an output order corresponding to a fixed input order.

### Do Not Create an Invalid Concurrent Collector Yourself

A contract-violating approach:

~~~java
// Do not do this in Collector.of:
// Collector.of(
//     ArrayList::new,
//     List::add,
//     (left, right) -> { left.addAll(right); return left; },
//     Collector.Characteristics.CONCURRENT,
//     Collector.Characteristics.UNORDERED
// );
~~~

If `CONCURRENT` is declared, the framework may have multiple threads update **the same container**; `ArrayList::add` is unsafe in that case. Do not add characteristics on your own merely with the goal of "speeding it up."

## 6. If a Shared Collection Is Required: Choose a Thread-Safe Structure

Sometimes updating a shared sink is genuinely a requirement (for example, collecting results from a callback API). In such cases, an appropriate concurrent data structure and protocol must be used. However, for the problem of simply **collecting data**, the solutions in sections 4–5 remain preferred.

### `Collections.synchronizedList(new ArrayList<>())`

~~~java
List<Integer> shared = Collections.synchronizedList(new ArrayList<>());

IntStream.range(0, 10_000)
        .parallel()
        .forEach(shared::add);
~~~

Here each call to `add` on the wrapper is synchronized; adding elements to the list is protected against calls through the same wrapper. However:

- **Insertion order** depends on execution scheduling, not encounter order.
- Individual operations are synchronized, but a sequence of "check-then-modify" operations still needs a shared synchronization mechanism if atomicity is required.
- Iterating over the list with an iterator while another thread modifies it requires **external synchronization according to the synchronized collection guidelines**.
- Every `add` contending on a single shared lock can create a bottleneck and negate the benefits of parallel execution.

For example, after all tasks complete:

~~~java
List<Integer> display = shared.stream().sorted().limit(5).toList();
// [0, 1, 2, 3, 4]
~~~

Only call `shared.stream()` after the `forEach` terminal operation has finished and no other threads are modifying the list. `sorted` here only serves to display a deterministic result; it does not prove that the list preserved encounter order during insertion.

### `ConcurrentLinkedQueue`

If List indexing is not needed and you only need to write many elements safely:

~~~java
Queue<Integer> queue = new ConcurrentLinkedQueue<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(queue::add);
~~~

`ConcurrentLinkedQueue` supports safe element insertion across multiple threads; however, **the actual insertion order does not necessarily follow source order**. In the example above, after the terminal operation finishes, the element count is 10,000 if every call succeeded. Turning it into a sorted List afterward is a separate task.

Do not use a queue to pretend there is a guarantee that "earlier source elements are added first." A thread-safe queue preserves queue ordering logic according to the calls as they occurred, not by sorting parallel calls according to the Stream's encounter order.

### `CopyOnWriteArrayList` Is Not a Default Option

`CopyOnWriteArrayList` supports thread-safe mutation and suits certain **very read-heavy, very write-light** workloads. With thousands of consecutive `add` calls, copying the array on every modification can be very expensive. Therefore, you should not replace every `ArrayList` with `CopyOnWriteArrayList` just to legitimize `parallel().forEach(...)`.

### Sink Selection Table

| Approach | Safe for Multi-Threaded Updates? | Preserves Source Encounter Order? | Typically Suitable For |
| --- | --- | --- | --- |
| `new ArrayList<>()` + `parallel().forEach(list::add)` | **No** | **No** | Should not be used |
| `parallel().toList()` | Framework collects safely | **Yes**, if source is ordered | Need an unmodifiable List |
| `parallel().collect(toCollection(ArrayList::new))` | Framework collects safely | **Yes**, if source is ordered and collector preserves order | Need a mutable ArrayList |
| `synchronizedList` + `parallel().forEach(add)` | Yes, per individual `add` via wrapper | **No** | Shared sink with synchronization |
| `ConcurrentLinkedQueue` + `parallel().forEach(add)` | Yes | **No** | Multiple producers, List not required |
| `CopyOnWriteArrayList` + `parallel().forEach(add)` | Yes | **No** | Few writes, many reads |

The safety of **the update operation itself** does not mean the result is in the right business order. These are two independent criteria.

## 7. `forEachOrdered()`: Fixes Ordering but Does Not Replace `collect()`

On a stream with an encounter order, `forEachOrdered(action)` ensures that the action on elements is performed in encounter order. The Javadoc also states that **the action for one element happens-before the action for the subsequent element**. Therefore, the snippet:

~~~java
List<Integer> ordered = new ArrayList<>();
IntStream.range(0, 10)
        .parallel()
        .forEachOrdered(ordered::add);
~~~

produces the result:

~~~text
[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
~~~

The `add` calls within this `forEachOrdered` terminal operation itself are constrained by ordering/happens-before, so they do not suffer from the same kind of unordered concurrent `add` calls as `forEach`. However, **this is not the default choice for building a List**:

- Preserving side-effect ordering can eliminate the benefits of parallelism.
- The action may still run on different threads; do not assume the same thread.
- It does not protect the List from **other threads** that may mutate it concurrently outside the pipeline.
- If the source is unordered, there is no meaningful encounter order for `forEachOrdered` to reproduce.
- `collect()` expresses the intent of collecting results more clearly and avoids relying on side effects.

Do not replace `forEach` with `forEachOrdered` just to "cure" all thread-safety issues. It resolves an ordering constraint of the terminal operation; it **does not automatically synchronize arbitrary external state or arbitrary callbacks**.

## 8. Complete Java 17+ Program Without Executing a Data Race

Save the program as **`ParallelForEachSafeDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Queue;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelForEachSafeDemo {
    public static void main(String[] args) {
        int size = 10_000;

        List<Integer> result = IntStream.range(0, size)
                .parallel().boxed().toList();

        ArrayList<Integer> mutable = IntStream.range(0, size)
                .parallel().boxed()
                .collect(Collectors.toCollection(ArrayList::new));
        mutable.add(-1);

        List<Integer> evens = IntStream.range(0, size)
                .parallel().filter(n -> n % 2 == 0)
                .boxed().toList();

        Queue<Integer> queue = new ConcurrentLinkedQueue<>();
        IntStream.range(0, size).parallel().forEach(queue::add);

        List<Integer> synchronizedList =
                Collections.synchronizedList(new ArrayList<>());
        IntStream.range(0, size).parallel()
                .forEach(synchronizedList::add);

        List<Integer> ordered = new ArrayList<>();
        IntStream.range(0, 10).parallel()
                .forEachOrdered(ordered::add);

        System.out.println("resultSize=" + result.size());
        System.out.println("firstFive=" + result.subList(0, 5));
        System.out.println("mutableSize=" + mutable.size());
        System.out.println("evenSize=" + evens.size());
        System.out.println("queueSize=" + queue.size());
        System.out.println("queueSmallest=" + queue.stream().sorted().limit(5).toList());
        System.out.println("synchronizedSize=" + synchronizedList.size());
        System.out.println("ordered=" + ordered);
        try {
            result.add(-2);
        } catch (UnsupportedOperationException ex) {
            System.out.println("toListMutation=unsupported");
        }
    }
}
~~~

Compile and run with **JDK 17** or later:

~~~bash
javac ParallelForEachSafeDemo.java
java ParallelForEachSafeDemo
~~~

Exact stdout of the program:

~~~text
resultSize=10000
firstFive=[0, 1, 2, 3, 4]
mutableSize=10001
evenSize=5000
queueSize=10000
queueSmallest=[0, 1, 2, 3, 4]
synchronizedSize=10000
ordered=[0, 1, 2, 3, 4, 5, 6, 7, 8, 9]
toListMutation=unsupported
~~~

Explanation of the points to verify:

1. `result` created by `toList()`: has all 10,000 elements, preserving the order of the ordered `IntStream.range` source.
2. `mutable` created by `toCollection(ArrayList::new)` is a mutable `ArrayList`: after adding `-1`, its size is 10,001.
3. `evens` after `filter` has 5,000 even numbers, still collected safely despite running in parallel.
4. `queue` is a concurrent structure, so the `add` calls are safe. To print the five smallest values, the code **explicitly sorts after collecting**; it does not infer natural order from `forEach` calls.
5. `synchronizedList` is only used for one `add` per element, and then its size is read after `forEach` completes. There are no concurrent updates during that size read.
6. `forEachOrdered` produces the list 0..9 in the exact order of the source with an encounter order.
7. `result.add(-2)` throws `UnsupportedOperationException` because `Stream.toList()` returns an unmodifiable List. The exception is caught so the program still completes.

The code **contains no unsafe parallel `ArrayList.add` operations** in its execution flow. The incorrect examples in earlier sections were presented to recognize anti-patterns, not to be used as benchmarks or stress tests.

## 9. Common "Quick Fixes" That Are Usually Wrong

### `volatile List` Does Not Make `ArrayList.add` Safe

~~~java
// Cannot fix the race by declaring the reference volatile:
// volatile List<Integer> results = new ArrayList<>();
~~~

`volatile` governs certain visibility/ordering guarantees for the **field reference** and field reads/writes; it does not turn the internal steps of `ArrayList.add` into an atomic update. Two threads can still contend on the same array/size.

### `AtomicInteger` Does Not Protect the List

An atomic counter can count the number of callback invocations, but it does not synchronize `ArrayList` modifying its own size or array. Even if you see the counter reach 10,000, the List can still be corrupted.

### `Collections.synchronizedList` Does Not Create Encounter Order

Wrapping with synchronization makes each individual add operation safe, but the order in which threads acquire the lock can differ from the source order. If the business logic needs the i-th element to correspond to the i-th input, prefer `toList`/`collect` on an ordered source.

### `parallel()` Does Not Automatically Speed Things Up

Adding `parallel` introduces overhead for splitting work, merging results, and synchronization. If the task is just collecting 10,000 simple values, running sequentially can be cheaper. Measure on representative data and real hardware rather than relying on the intuition that "more threads means faster."

### `peek(...)` Is Still Not the Place to Collect Results

~~~java
// Do not use this side effect to build results:
// List<Integer> external = new ArrayList<>();
// List<Integer> copy = IntStream.range(0, 10_000)
//         .parallel().boxed()
//         .peek(external::add)
//         .toList();
~~~

`peek` is primarily for observation/debugging; the Stream framework is permitted to optimize away certain steps if doing so does not affect the result under the contract. Side effects are not a reliable way to collect results. If `peek` is still invoked concurrently, the race on `external` remains.

### Manual `synchronized(list)` Is Not the Cleanest Choice for Collecting

~~~java
// Can work for individual add calls, but increases contention:
// parallelStream.forEach(x -> {
//     synchronized (list) {
//         list.add(x);
//     }
// });
~~~

This is an **illustrative code snippet** with `parallelStream` and `list` already existing in a method, not a standalone runnable program. When the main task is simply collecting into a list, `collect(Collectors.toCollection(ArrayList::new))` expresses the intent more clearly and avoids locking a shared list on every element.

## 10. Testing and Data Race Analysis

When reviewing code with `parallelStream()` or `parallel()`, look for expressions such as:

~~~java
.forEach(list::add)
.forEach(x -> result.add(x))
.forEach(map::put)
.peek(x -> external.add(x))
~~~

They are not **always** wrong: you need to check whether `list/map` is shared state, whether it is thread-safe, and how conflicts are resolved. However, these are signals to inspect closely:

- Was `list` created outside the pipeline and captured by the lambda?
- Can multiple threads mutate the same object?
- Is there a data structure or synchronization mechanism ensuring atomic operations?
- Is result ordering part of the business contract?
- Is the callback allowed to run multiple times, run on different threads, or be optimized away?
- Can the result be built using `collect`/`reduce` instead of side effects?

A stress test run hundreds of times with many elements can **detect** a race bug, but a passing test **does not prove** the code is correct. Races depend on scheduling. Use reasoning based on the Java Memory Model, collection contracts, analysis tools, and multi-configuration testing to substantiate conclusions.

With fixed data such as `IntStream.range(0, N)`, you can check both the count and the set of values:

~~~java
List<Integer> values = IntStream.range(0, 10_000)
        .parallel().boxed().toList();

boolean sizeCorrect = values.size() == 10_000;
boolean endpointsCorrect = values.get(0) == 0 && values.get(9_999) == 9_999;
~~~

This is an **illustrative snippet**, requiring imports for `List` and `IntStream`. These assertions verify the output of the safe solution. Using an unsafe list with a test that checks the element count still does not substitute for fixing the race design.

## 11. Relation to `reduce()`, `collect()`, and the Non-Interference Principle

A proper Stream pipeline should avoid modifying the source or a shared state during traversal.

- **Non-interference:** behavioral functions should not modify the data source while the stream is operating (except when the source is designed for concurrent modification and the API/contract permits it).
- **Statelessness:** do not let lambda results depend on mutable state that can change across elements or across multiple threads without a proper contract.
- **Associative reduction:** if using parallel `reduce`, the combiner must be properly associative; do not use a shared mutable accumulator with a reduction that appears stateless.
- **Collector isolation:** a non-concurrent collector can be used in a parallel stream because the framework manages the accumulation containers according to the contract, not because the containers are automatically thread-safe.

For example, summing even numbers should use:

~~~java
long evenSum = IntStream.range(0, 10_000)
        .parallel()
        .filter(n -> n % 2 == 0)
        .asLongStream()
        .sum();
~~~

Instead of synchronizing a counter variable from every callback. Using primitive `sum` expresses the aggregation intent and avoids multiple side effects.

Note: `Collectors.toList()` makes no guarantee to return a mutable List; `Stream.toList()` is unmodifiable; `Collectors.toCollection(ArrayList::new)` is chosen when a specific `ArrayList` is needed. All three serve different purposes even though they may produce results containing similar elements.

## 12. Checklist for Fixing Dangerous Code in a Project

| Question | Action to Take |
| --- | --- |
| Is `forEach` writing to an externally declared `ArrayList`? | Prefer replacing with `map/filter + toList/collect` |
| Must the result be a mutable List? | `Collectors.toCollection(ArrayList::new)` |
| Must the result preserve source order? | Use an ordered source and a collector/terminal operation that preserves encounter order |
| Do you only need a set of values? | `Collectors.toSet()` or an appropriate Set, without relying on traversal order |
| Is a shared sink genuinely required? | Choose an appropriate concurrent collection/queue, and manage ordering and contention separately |
| Only need to serialize print/send actions? | Consider `forEachOrdered`, but evaluate cost and I/O characteristics |
| Want multiple threads to populate a list while preserving indices? | Design explicit index/range-based processing instead of shared `forEach(add)` |
| Code still works when run once? | Not enough: check the thread-safety contract and scheduling |
| Is switching `parallel` to `sequential` enough? | It may eliminate the race in that pipeline, but you still must check updates from other threads and side effects |
| Want to optimize performance? | Benchmark with JMH, real data, allocation, and contention; do not trade correctness for speed |

**In summary:** `ArrayList.add()` is not safe when multiple threads concurrently modify the same List. `parallelStream().forEach(list::add)` moves mutable state outside the Stream's collection mechanism, easily causing data races, lost elements, and inconsistent results. When **data results** are needed, use **`toList()` or `collect(toCollection(ArrayList::new))`**. Only use a shared mutable sink when there is a clear requirement and synchronization, ordering, performance, and error handling have been designed accordingly.