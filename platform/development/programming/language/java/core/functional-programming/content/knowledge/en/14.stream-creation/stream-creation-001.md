# Creating a Stream from Collection.stream() and parallelStream() in Java

## 1. Why Can Collection Create a Stream?

When you already have a dataset in Java, such as `List<Order>`, `Set<String>`, or `Queue<Integer>`, you often want to filter, transform, and aggregate elements without manually writing loops for each step. The **Java Stream API** lets you describe a data-processing pipeline declaratively.

Two methods on the `java.util.Collection<E>` interface are common starting points:

~~~java
Stream<E> sequential = collection.stream();
Stream<E> possiblyParallel = collection.parallelStream();
~~~

This is **illustrative syntax**, where `collection` is already declared as a `Collection<E>` and `java.util.stream.Stream` needs to be imported. Both return a Stream object backed by the collection as its source, but they differ in the **requested execution mode**:

- `stream()` returns a **sequential stream**.
- `parallelStream()` returns a **possibly parallel stream**. For common standard collections such as `List.of(...)` or `ArrayList` in JDK 17, the resulting stream is in parallel mode; however, the `Collection.parallelStream()` contract **allows** an implementation to return a sequential stream. Do not treat the method name as a guarantee of the number of threads or speedup.

Key point to remember: **A Collection holds data; a Stream describes and executes the processing of that data when needed**. Creating a Stream does not by itself turn the collection into a new result list and usually does not execute `filter` or `map` operations immediately.

## 2. Creating a Sequential Stream with Collection.stream()

### 2.1. Basic Example with List

~~~java
import java.util.List;

List<String> names = List.of("An", "Bình", "Chi");
List<String> selected = names.stream()
        .filter(name -> name.length() >= 3)
        .map(String::toUpperCase)
        .toList();
~~~

This snippet is **illustrative code inside a method**. From a `List<String>`, `names.stream()` creates a `Stream<String>` to chain the steps:

1. `filter(...)` keeps names with a length of 3 or more.
2. `map(...)` converts each matching name to uppercase.
3. `toList()` is a *terminal operation* that produces the result list.

Here, the source collection `names` is not modified simply because the pipeline ran. The `filter` and `map` methods return intermediate Streams and do not add/remove elements in the source by API design. However, user lambdas **can** contain side effects; therefore, you must distinguish the behavior of the Stream API from behavior introduced by custom callbacks.

### 2.2. Other Collection Types

Not just `List`—every object implementing `Collection<E>` provides the corresponding call, including many `Set` and `Queue` types.

~~~java
Set<Integer> distinctNumbers = Set.of(4, 1, 3, 2);
long evenCount = distinctNumbers.stream()
        .filter(number -> number % 2 == 0)
        .count();
~~~

This is an **illustrative snippet** inside a method, requiring `import java.util.Set`. `evenCount` equals 2 because there are two even values, 2 and 4.

**Note on ordering:** you cannot infer that every `Collection` has an *encounter order* like `List`. `List` typically has an index-based order; `LinkedHashSet` maintains iteration order; whereas `HashSet` does not guarantee a fixed, meaningful iteration order by contract. A pipeline that depends on order must check the source type and operations before expecting an ordered output.

### 2.3. Map Does Not Directly Extend Collection

`Map<K,V>` is a different abstraction and does **not** implement `Collection`. Therefore, you cannot call `map.stream()` on a standard `Map`. Instead, choose the appropriate view of the data:

~~~java
Map<String, Integer> scores = Map.of("An", 8, "Chi", 9);

long highScoreCount = scores.values().stream()
        .filter(score -> score >= 9)
        .count();

List<String> highScoreNames = scores.entrySet().stream()
        .filter(entry -> entry.getValue() >= 9)
        .map(Map.Entry::getKey)
        .sorted()
        .toList();
~~~

This illustrative snippet requires importing `java.util.Map` and `java.util.List`. `scores.values()` returns a Collection of values, `scores.entrySet()` returns a Set of entries, and `scores.keySet()` is a Set of keys. With the given data, `highScoreCount` equals 1 and `highScoreNames` equals `[Chi]`. The `sorted()` operation ensures the result has a deterministic order rather than relying on the iteration order of `Map.of`.

## 3. Creating a Parallel-Mode Stream with Collection.parallelStream()

~~~java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

int total = numbers.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

This snippet is **illustrative code inside a method**, requiring `import java.util.List`. The result is 15. Summing numbers is a simple example because integer addition is suitable for splitting the source into parts and combining the results.

When a Stream is in parallel mode and the pipeline is evaluated in parallel, the library can **split the data** into smaller parts, process the parts independently, and then **merge the results**. A *Spliterator* plays the role of supplying/splitting elements. Parallel mode does not mean "one thread per element", nor does it guarantee faster execution.

A conceptual representation:

~~~text
Collection<Integer> [1, 2, 3, 4, 5]
             |
       parallelStream()
             |
       split into parts
        /        |       \
    [1,2]      [3,4]     [5]
       \         |        /
         compute and combine
               |
             sum()
               |
              15
~~~

The diagram illustrates the **split-and-merge idea**, not a JDK-guaranteed partitioning or thread schedule. How splitting happens, the processing order, and the degree of parallelism depend on the implementation, source size, cost of each operation, and execution environment.

### 3.1. When Do Callbacks Execute?

Operations like `filter`, `map`, `mapToInt`, and `sorted` are typically **intermediate operations**. They build the pipeline without forcing evaluation of every element at declaration time.

~~~java
Stream<Integer> pipeline = numbers.parallelStream()
        .filter(n -> n > 2)
        .map(n -> n * 10);

// Only at the terminal step is the result requested:
List<Integer> result = pipeline.toList();
~~~

This is an illustrative snippet, requiring `import java.util.stream.Stream` and a `numbers` variable of an appropriate collection type. With a List containing 1 through 5, the result is `[30, 40, 50]`.

You should not guess how many times a callback is invoked based solely on the number of source elements: some terminal operations can short-circuit or be optimized, and side effects in a pipeline are not a reliable signal for "counting processed elements".

### 3.2. Checking the Mode with isParallel()

~~~java
Stream<Integer> seq = numbers.stream();
Stream<Integer> par = numbers.parallelStream();

System.out.println(seq.isParallel());
System.out.println(par.isParallel());
~~~

This snippet assumes `numbers` is a standard `List<Integer>` that supports parallel streams (such as `List.of(...)`), and `java.util.stream.Stream` is imported. In the Java 17 example environment, the results are `false` and `true`, respectively.

`isParallel()` indicates the **mode of the Stream**, not the actual number of threads running at the moment of the check. Creating a Stream, querying its mode, and then processing it with a terminal operation is valid. However, once a Stream has been consumed or closed, you cannot continue building a new pipeline from the same instance.

## 4. stream() and parallelStream(): How Are They Similar, How Do They Differ?

| Criterion | `collection.stream()` | `collection.parallelStream()` |
| --- | --- | --- |
| Initial mode | Sequential | Possibly parallel, implementation-dependent |
| Return type | `Stream<E>` | `Stream<E>` |
| Element source | Existing Collection | Same existing Collection |
| Operations like `filter`, `map`, `reduce` | Usable | Usable |
| Element *encounter order* | Depends on source | Still depends on source; processing may be out of order |
| Are callbacks allowed to arbitrarily mutate the source? | No | No |
| Work coordination overhead | Usually lower | May add splitting, scheduling, synchronization/merging |
| When to prefer? | Safe, readable default | When the task is suitable, sufficiently large, and measured to be effective |

**There is no difference in "Stream type" in terms of the returned API.** A `Stream<E>` object can be set to sequential or parallel mode; most intermediate operations remain identical in how they are declared.

Besides creating directly from a collection, you can switch a pipeline's mode using `parallel()` or `sequential()`:

~~~java
List<Integer> a = numbers.stream().parallel()
        .map(x -> x * 2).toList();

List<Integer> b = numbers.parallelStream().sequential()
        .map(x -> x * 2).toList();
~~~

Both snippets demonstrate the same transformation with identical results for a stable List input. The `parallel()` and `sequential()` methods change the mode of the pipeline. You should not rely on repeatedly mixing multiple mode-switching calls expecting different stages of the same pipeline to run in independent modes: the execution mode is a property of the evaluated pipeline, not a guarantee that each stage gets its own thread.

## 5. A Complete Java 17 Program

Create the file **CollectionStreamsDemo.java**. The program uses Collection in concrete scenarios:

- Create sequential and parallel Streams from the same `List<Integer>`.
- Verify `isParallel()` on the created Streams.
- Compute sums sequentially and in parallel.
- Transform and filter while preserving result order when collecting into a List with an encounter order.
- Group elements from a parallel stream using a safe collector.
- Use `findFirst()` to retrieve the first element according to source order.

~~~java
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.TreeMap;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class CollectionStreamsDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5);
        Stream<Integer> seq = numbers.stream();
        Stream<Integer> par = numbers.parallelStream();
        System.out.println("seq.isParallel=" + seq.isParallel());
        System.out.println("par.isParallel=" + par.isParallel());

        int seqSum = seq.mapToInt(Integer::intValue).sum();
        int parSum = par.mapToInt(Integer::intValue).sum();
        System.out.println("seq sum=" + seqSum);
        System.out.println("par sum=" + parSum);

        List<Integer> squares = numbers.parallelStream()
                .map(n -> n * n)
                .toList();
        System.out.println("squares=" + squares);

        List<String> names = List.of("an", "binh", "chi", "dung");
        List<String> upper = names.parallelStream()
                .map(name -> name.toUpperCase(Locale.ROOT))
                .filter(name -> name.length() >= 3)
                .toList();
        System.out.println("upper=" + upper);

        List<String> words = List.of("java", "stream", "java", "parallel");
        Map<String, Long> counts = words.parallelStream()
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        TreeMap::new,
                        Collectors.counting()));
        System.out.println("counts=" + counts);
        System.out.println("first=" +
                numbers.parallelStream().findFirst().orElseThrow());
    }
}
~~~

Compile and run using JDK 17 or a higher JDK version supporting target 17:

~~~bash
javac --release 17 CollectionStreamsDemo.java
java CollectionStreamsDemo
~~~

Directly verified stdout:

~~~text
seq.isParallel=false
par.isParallel=true
seq sum=15
par sum=15
squares=[1, 4, 9, 16, 25]
upper=[BINH, CHI, DUNG]
counts={java=2, parallel=1, stream=1}
first=1
~~~

### 5.1. Explanation of Each Result

1. `numbers.stream()` has sequential mode, and `numbers.parallelStream()` has parallel mode in the implementation used in the example. Thus `isParallel()` returns `false` and `true`, respectively. Do not infer that `parallelStream()` must spawn multiple threads for these small five elements.
2. The two pipelines sum `1+2+3+4+5=15`. They do not need to preserve element-by-element execution order to preserve the result of an appropriate addition operation.
3. `squares` is `[1,4,9,16,25]`: `List.of` has an encounter order, `map` preserves encounter order, and `toList()` returns elements in that order. This does not mean the `map` callback ran sequentially on 1,2,3,4,5 when the pipeline was parallel.
4. The source name list is `["an","binh","chi","dung"]`. `map` converts to uppercase; `filter` drops `AN` of length 2; `toList()` outputs `[BINH,CHI,DUNG]` in encounter order.
5. `groupingBy` is supplied a `TreeMap` to store the grouped results, so the map displays keys in natural order: `java`, `parallel`, `stream`. `Collectors.counting()` counts how many times each string appears. The collector is executed by the API according to the appropriate collection mechanism; user code does not need to manually mutate a shared `HashMap` from multiple threads.
6. `findFirst()` on a List source with an encounter order returns the first element, 1, even though the pipeline is in parallel mode. Switching to `findAny()` removes the guarantee of selecting the first element in that order.

Writing `words.parallelStream().collect(Collectors.groupingBy(...))` is an example of **controlled collection**, as opposed to each callback mutating a shared mutable `Map`.

## 6. Ordering in Parallel Streams

One of the most common misconceptions is: "parallelStream will always scramble the result order." In practice, you must distinguish three factors:

- **Encounter order**: does the source/pipeline have a defined element encounter order?
- **Callback execution order**: which element is processed first on which thread?
- **Result order**: does the terminal operation commit to any order?

For an ordered `List`, many operations such as `filter` and `map` logically maintain encounter order. `Stream.toList()` returns a list in encounter order **if the Stream has an encounter order**, even when processed in parallel. However, callbacks may run in different orders and on different threads.

| Operation | Points to Remember |
| --- | --- |
| `map`, `filter` | Logical result preserves the encounter order of an ordered source, but there is no guarantee callbacks run in strict chronological order |
| `toList()` | Result follows encounter order if the Stream is ordered; the returned list does not allow structural modification |
| `findFirst()` | Retrieves the first element in encounter order if present; may incur ordering overhead |
| `findAny()` | May return any matching element; suitable when the first position is not needed |
| `forEach(...)` | In a parallel stream, execution order is not guaranteed |
| `forEachOrdered(...)` | Guarantees actions follow encounter order if present, but may reduce parallelism benefits |
| `unordered()` | Removes the encounter order constraint so some operations have optimization opportunities; does not actively shuffle data |

Do not assume a fixed output for `parallelStream().forEach(System.out::print)`: the observed order depends on scheduling. If a lesson requires reliable output, use an aggregation or a terminal operation with an appropriate contract.

**Note on performance:** order-preserving operations such as `limit`, `skip`, `distinct`, or `findFirst` may require more coordination when running in parallel on an ordered source. Sometimes `unordered()` makes sense if the business logic genuinely does not require ordering; do not drop ordering constraints just to go faster when order is required.

## 7. Is a Stream a Copy of a Collection?

**Do not treat `stream()`/`parallelStream()` as a data snapshot operation.** A Stream normally references the source and performs traversal when a terminal operation evaluates the pipeline. It does not copy the entire collection by default upon creation.

Example:

~~~java
List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
Stream<Integer> stream = numbers.stream();
~~~

This is an illustrative snippet requiring `import java.util.ArrayList`, `java.util.List`, `java.util.stream.Stream`. The line creating `stream` has not yet created an independent `List<Integer>` result.

### 7.1. Do Not Modify the Source During Processing

Most Stream sources require **non-interfering** callbacks: they must not modify the source currently being traversed. The example below is a **counter-example that should not be run in real programs**:

~~~java
// INCORRECT STREAM USAGE:
// List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3));
// numbers.stream().forEach(n -> numbers.add(n + 10));
~~~

Structurally modifying a collection during traversal can lead to errors such as `ConcurrentModificationException` or unexpected behavior, depending on the source type and runtime conditions. There is no guarantee that every violation will be caught with an exception.

A better approach when a new list is needed:

~~~java
List<Integer> expanded = numbers.stream()
        .map(n -> n + 10)
        .toList();
~~~

The `expanded` result does not structurally modify the source and contains the transformed element values from the pipeline. `Stream.toList()` returns a list that does not allow structural modification (you cannot call `add`, `remove`, etc. to alter that list). It **does not guarantee that element objects are deeply immutable**.

### 7.2. Collection Changes Between Stream Creation and Consumption

Modifying the source before or during Stream consumption is governed by binding/spliterator rules and the characteristics of each collection. Some sources have a **late-binding** spliterator, while others have their own concurrent or snapshot design.

Therefore, you cannot say "every Stream sees the latest updates" or "every Stream always sees a snapshot at creation time." For logic requiring stable data, design an **intentional snapshot**, appropriate synchronization locks, immutable collections, or a source with a clear concurrent contract.

In most list-processing problems, the clearest choice is to finish building the source data first, then create and consume the Stream without concurrently modifying the source.

### 7.3. A Stream Can Typically Be Consumed Only Once

~~~java
Stream<Integer> once = numbers.stream();
long count = once.count();

// INTENTIONALLY INVALID AT RUNTIME:
// long second = once.count();
// The stream has already been consumed; reusing it may cause IllegalStateException.
~~~

This is an illustrative snippet inside a method. If you need to process twice, **create two new Streams from the same collection**:

~~~java
long count = numbers.stream().count();
int sum = numbers.stream().mapToInt(Integer::intValue).sum();
~~~

Do not store a consumed Stream instance to reuse repeatedly as if it were a List.

## 8. Conditions for parallelStream to Be Truly Suitable

A parallel stream can help when the work is large enough and can be split independently, but it also has splitting/scheduling/coordination overhead. A sound decision should consider the **data**, the **processing function**, the **aggregation operation**, and the **runtime environment**.

### 8.1. Source Can Be Split Efficiently

Collections with structures that allow efficient access/splitting are generally more favorable than sources that are hard to split evenly. A source with a known size and an appropriate Spliterator helps the system organize work effectively.

For example, a large `ArrayList` can split element ranges by index relatively conveniently. Still, effectiveness depends on processing cost and pipeline characteristics; you cannot conclude every `ArrayList.parallelStream()` is faster than `stream()`.

### 8.2. Callbacks Without Hard-to-Control Shared State

A relatively safe mapping:

~~~java
List<Integer> squares = numbers.parallelStream()
        .map(value -> value * value)
        .toList();
~~~

In this illustrative snippet, the lambda only uses the input value and returns a new value. It does not mutate shared variables and is therefore easy to reason about when running in parallel.

Counter-example to avoid:

~~~java
// UNSAFE with parallel stream:
// List<Integer> shared = new ArrayList<>();
// numbers.parallelStream().forEach(shared::add);
~~~

`ArrayList` is not thread-safe for concurrent writes. Results may lose elements or fail; do not use a shared mutable list as a manual collector.

A better way to produce results:

~~~java
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 2)
        .toList();
~~~

When grouping, summarizing, or mapping is needed, use `collect` with an appropriate collector. That allows the Stream framework to split and combine data according to the Collector contract instead of relying on shared mutation.

### 8.3. Combination Operations Must Satisfy the Reduction Contract

A parallel reduction requires an appropriate combiner, which usually must be **associative** and have the exact identity value so the result does not depend on how elements are grouped.

~~~java
int total = numbers.parallelStream()
        .reduce(0, Integer::sum);
~~~

For small integers in this lesson, addition has the identity element 0 and is associative, so reduction is suitable.

Do not use subtraction as an arbitrary combiner expecting the same sequential and parallel results:

~~~java
// UNSUITABLE for parallel reduction as an associative combination:
// int difference = numbers.parallelStream().reduce(0, (a, b) -> a - b);
~~~

Subtraction is not associative: `(a-b)-c` differs from `a-(b-c)`. The result can change when operations are grouped differently. For floating-point operations, you must also consider addition order and floating-point rounding error; do not assume bit-for-bit identical results across all configurations.

### 8.4. Does the Task Require Strict Ordering?

If ordered processing is required to update a shared resource, parallel execution may be unsuitable or incur heavy synchronization costs. If only independent aggregation over many elements is needed, parallel execution may be a better fit.

Do not use `parallelStream()` for callbacks that inherently rely on order to update state, such as adding to an external mutable variable via `forEach`. Switch to `reduce`, `mapToInt().sum()`, or an appropriate collector.

### 8.5. Performance Must Be Measured with Proper Benchmarks

"Parallel" does not mean "faster." For small lists or very cheap operations, overhead can outweigh the benefits. Speed is also affected by CPU, memory/cache, GC, data source, contention, and what other tasks are running on the system.

Prefer:
1. Write a correct, easily testable sequential version.
2. Verify that the pipeline is sufficiently independent and the reduction satisfies its contract.
3. Benchmark using an appropriate tool such as **JMH**, with warm-up, multiple iterations, and representative data.
4. Only choose parallel when measured gains are sufficiently stable and operations are not adversely affected.

Do not write a single `System.currentTimeMillis()` check and draw general conclusions about performance.

## 9. Threads, ForkJoinPool, and Operational Limits

In many common JDK implementations, parallel streams use a fork/join mechanism to split tasks and typically leverage resources like `ForkJoinPool.commonPool()`. However, **do not turn that implementation detail into a contract that every callback must run in a fixed pool/thread**.

Several things must not be assumed:

- There is no guarantee each element runs on a separate thread.
- There is no guarantee of an exact thread count across all environments.
- There is no guarantee `parallelStream()` is faster for blocking I/O operations such as HTTP calls or network reads.
- There is no guarantee "enabling parallel" replaces async design, backpressure, timeouts, or dedicated thread pools.

In a server handling many requests, running parallel streams indiscriminately can compete for CPU with other requests or block shared resources. For long-running I/O operations, the need to control concurrency/timeouts is usually better expressed through executors, asynchronous tasks, or a dedicated concurrency model.

**In summary:** parallel streams are best suited for independent, sufficiently CPU-intensive computations without side effects and with safe combining operations, not for every kind of "work with many elements."

## 10. Distinguishing Parallel Streams from Data Thread Safety

A Stream in parallel mode **does not make the source collection automatically thread-safe**, nor does it cause callbacks to be invoked sequentially in a controlled manner.

If the source is a mutable `ArrayList` and other threads are adding/removing elements while the stream is traversing, using parallel does not solve the race condition. If elements are mutable objects and multiple callbacks modify the same object, consistency still depends on synchronization mechanisms and data design.

Similarly, `Collections.synchronizedList(...)` does not by itself replace the need for coordination when traversing via a Stream while another thread modifies the collection. You must follow the synchronization contract of the specific collection type and context, or switch to a snapshot/concurrent collection with appropriate semantics.

**A principle that works in both modes:** the source should remain stable during traversal, `map`/`filter` operations should be *stateless* and *non-interfering*, and reductions/collectors must be chosen according to aggregation requirements.

## 11. Frequently Asked Questions and Common Mistakes

### 11.1. Does calling stream() twice create two copies of the data?

No. Each call creates a new Stream/pipeline object with the same logical source. Creating a Stream does not copy the entire collection. However, terminal operations such as `toList()` or `toArray()` may allocate a result container.

### 11.2. Does parallelStream() guarantee the same order as stream()?

You must separate the **logical order of the result** from the **chronological order of callback execution**. From a List with an encounter order, many terminal operations like `toList()` preserve the result order; parallel `forEach` does not guarantee callback order.

### 11.3. Is using parallelStream() for a List of a few elements beneficial?

You cannot conclude that in advance. With a few elements and cheap operations, overhead is usually significant relative to the work; therefore, use `stream()` as the default and measure before optimizing.

### 11.4. Does HashSet.parallelStream().toList() have a stable order?

There is no encounter order guarantee for `HashSet` by contract. If you need a list in a deterministic order, apply `sorted()` with elements that have an appropriate comparison order, or choose a source with the desired encounter order.

### 11.5. If running a parallel Stream produces the wrong sum, did Java lose data on its own?

Do not jump to that conclusion. Usually you need to check whether callbacks have side effects, shared variables, a non-associative reduction, or a concurrently modified source. Use a contract-compliant collector/reduction and stable data before suspecting the implementation.

### 11.6. Does switching parallelStream().sequential() create a new collection?

No. It changes the mode of the Stream pipeline, not an element-copying operation. A materialized result is only created when a terminal operation requests it.

### 11.7. Is it mandatory to import java.util.stream.Stream to call list.stream()?

No, if you only chain calls directly such as `list.stream().filter(...).toList()` and the compiler knows the return type from the API. You need to import `java.util.stream.Stream` when declaring the type name `Stream<T>` without using its fully qualified name.

## 12. Checklist for Choosing stream() or parallelStream()

When starting from a `Collection<T>`, answer these in order:

1. **Do I need a data-processing pipeline or just a simple traversal?** If it is just a short, clear loop, using a Stream is not mandatory.
2. **Is the source large enough and can the work be split efficiently?** If not, try sequential first.
3. **Are the lambdas stateless, non-interfering, and free of shared-variable mutation?** If not, fix the design before running in parallel.
4. **Is the reduction/collector properly associative and independent of operation order?** If not, do not use parallel arbitrarily.
5. **Do I need the result's encounter order?** If yes, choose order-preserving operations and account for their cost.
6. **Is there I/O, blocking, timeouts, rate limits, or shared resources?** If yes, design an appropriate concurrency mechanism rather than treating parallel stream as the default solution.
7. **Have I measured performance with representative data and environment?** Only optimize when there is evidence.
8. **Am I accidentally reusing a Stream after a terminal operation or modifying the Collection during traversal?** If yes, this must be changed.

**Selection conclusion:** for most typical business code, `collection.stream()` is the simpler and more predictable starting point. `collection.parallelStream()` is worth considering when the work is large enough, splittable, has low order dependency, avoids dangerous shared state, and shows measured practical benefit.

## 13. Self-Check Exercises

**Exercise 1.** Given `List<Integer> values = List.of(2,4,6);`, what does `values.stream().mapToInt(Integer::intValue).sum()` return? What is the default mode?

**Answer:** 12 and sequential stream.

**Exercise 2.** Given `List<String> names = List.of("An","Bình","Chi");`, does `names.parallelStream().map(String::length).toList()` guarantee the result list follows the source element order?

**Answer:** Yes, with a List that has an encounter order and the `toList()` terminal operation, the output list preserves encounter order; do not infer that callbacks ran in chronological order.

**Exercise 3.** Why is `new HashMap<...>().stream()` invalid?

**Answer:** `Map` does not implement `Collection`. Use `entrySet().stream()`, `keySet().stream()`, or `values().stream()` as needed.

**Exercise 4.** If you use `parallelStream().forEach(sharedList::add)` with a shared `ArrayList`, what problem can occur?

**Answer:** A race condition and inconsistent state because `ArrayList` is not thread-safe for concurrent writes; use `toList()` or an appropriate collector.

**Exercise 5.** Should you use `reduce(0, (a,b) -> a-b)` on a parallel stream to simulate sequential subtraction?

**Answer:** No, subtraction is not associative, so it does not satisfy the requirements for parallel reduction in that manner.

**Exercise 6.** Does `isParallel() == true` prove that each callback runs on a different thread?

**Answer:** No; it indicates the mode of the Stream, not the number of threads/speed or a specific execution schedule.

**Exercise 7.** If you want to switch a Stream created with `stream()` to parallel, is there another way besides calling `parallelStream()` again?

**Answer:** You can use `collection.stream().parallel()` before a terminal operation. Conversely, `collection.parallelStream().sequential()` sets the pipeline back to sequential mode.

**Exercise 8.** Does a Stream snapshot the entire Collection when `stream()` is called?

**Answer:** Not by default. Semantics when the source changes depend on the source/spliterator; if a stable snapshot is needed, create one explicitly and follow the source's contract.

## 14. References

- [Java SE 17 — Collection.stream() / parallelStream()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Collection.html).
- [Java SE 17 — Stream API and stateless/non-interfering principles](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html).
- [Java SE 17 — BaseStream.isParallel(), sequential(), parallel()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/BaseStream.html).
- [Java SE 17 — Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html).
- [Java SE 17 — Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).

**Remember:** `Collection.stream()` creates a sequential Stream, while `Collection.parallelStream()` requests a possibly parallel Stream without promising the degree of parallelism or speed across all implementations. Both use the same Stream operations; the key differences lie in **how execution happens, order preservation, callback safety, and coordination overhead**. Choose sequential by default, keep source data stable, and only enable parallel when the operation's contract and performance measurements justify it.
