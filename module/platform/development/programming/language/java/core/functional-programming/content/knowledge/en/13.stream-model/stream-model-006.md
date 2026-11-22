# Sequential Streams and Parallel Streams in Java

The Java Stream API lets you describe how to process a sequence of elements using transformation and terminal operations, instead of writing loops manually for each step. A **sequential stream** processes the pipeline sequentially; a **parallel stream** allows the library to split the work into multiple parts and execute them across multiple threads when appropriate.

Both modes share many of the same APIs such as `filter`, `map`, `reduce`, and `collect`, but **that does not mean they always have the same execution order characteristics, performance, or interaction with side effects**. In particular, switching a pipeline to parallel does not automatically make faulty logic, non-associative reductions, or shared mutable state safe.

After this lesson, you will be able to:
- Create a sequential Stream with `stream()`, and a parallel Stream with `parallelStream()` or `parallel()`.
- Understand *pipelines*, laziness, terminal operations, and mode-switching rules.
- Distinguish **encounter order** from **thread execution order**, and choose the right operation among `forEach`, `forEachOrdered`, `toList`, `findFirst`, and `findAny`.
- Use `reduce` and collectors safely with parallel computation.
- Avoid shared side effects, race conditions, and unfounded performance assumptions.
- Decide when a parallel stream is beneficial and when to choose a sequential stream.

Complete examples use **JDK 17 or later**, with compile commands and deterministic output. Intentionally incorrect code snippets or non-deterministic results will be marked separately.

## 1. How does a Stream pipeline work?

A pipeline typically has three components:

1. **Source:** a collection, array, numeric range, or other source.
2. **Intermediate operations:** `filter`, `map`, `distinct`, `sorted`, `limit`… produce a new Stream describing a processing step. They are usually **lazy**, not traversing the source immediately.
3. **Terminal operation:** `toList`, `collect`, `sum`, `count`, `reduce`, `forEach`, `findFirst`… triggers the execution of the pipeline.

Illustrative example:

```java
List<Integer> result = List.of(1, 2, 3, 4, 5, 6)
        .stream()                 // source and sequential mode
        .filter(n -> n % 2 == 0) // intermediate
        .map(n -> n * n)         // intermediate
        .toList();               // terminal
// [4, 16, 36]
```

This is a **code snippet** that requires `import java.util.List;` and must be placed inside a method. `toList()` was added in Java 16 and runs on Java 17.

**A Stream is not a collection that holds all results in advance.** A Stream represents a pipeline that can be traversed once, and a new Stream must be used if you want to run a terminal operation again. You cannot reuse an already consumed Stream and call a terminal operation a second time.

Sequential/parallel mode determines **how the pipeline is executed** when the terminal operation runs, without changing the mathematical meaning of valid pure transformations.

## 2. Creating Sequential Streams and Parallel Streams

With a standard `Collection<T>`:

```java
List<Integer> numbers = List.of(1, 2, 3, 4, 5);

Stream<Integer> sequential = numbers.stream();
Stream<Integer> parallel = numbers.parallelStream();
```

The snippet above requires `import java.util.List;` and `import java.util.stream.Stream;`.

- `numbers.stream()` creates a Stream in **sequential** mode.
- `numbers.parallelStream()` creates a Stream in **parallel** mode.
- On a Stream, `parallel()` requests parallel mode; `sequential()` requests sequential mode.
- `isParallel()` returns the current mode flag of the Stream; it **does not assert how many threads actually ran**.

Example:

```java
Stream<Integer> s = numbers.stream().parallel();
boolean parallelMode = s.isParallel(); // true
```

You can switch back with `sequential()` while building the pipeline. **The effective mode at the time the terminal operation runs** is what matters; calling `parallel()` at the beginning and then `sequential()` at the end does not create two separate phases of “first half parallel, second half sequential”.

With primitive streams:

```java
int total = java.util.stream.IntStream.rangeClosed(1, 100)
        .parallel()
        .sum();
```

This is a standalone snippet inside a method. `IntStream` avoids boxing for `int` calculations, but adding `parallel()` by itself **does not guarantee it will be faster**.

## 3. Java 17 Example: same result in both modes

Save as **`SequentialParallelDemo.java`**:

```java
import java.util.List;
import java.util.stream.Stream;

public class SequentialParallelDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

        List<Integer> sequentialSquares = numbers.stream()
                .map(n -> n * n)
                .toList();

        List<Integer> parallelSquares = numbers.parallelStream()
                .map(n -> n * n)
                .toList();

        int sequentialSum = numbers.stream()
                .mapToInt(Integer::intValue)
                .sum();

        int parallelSum = numbers.parallelStream()
                .mapToInt(Integer::intValue)
                .sum();

        Stream<Integer> mode = numbers.stream()
                .parallel()
                .sequential();

        System.out.println("sequential=" + sequentialSquares);
        System.out.println("parallel=" + parallelSquares);
        System.out.println("sum sequential=" + sequentialSum);
        System.out.println("sum parallel=" + parallelSum);
        System.out.println("isParallel=" + mode.isParallel());
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 SequentialParallelDemo.java
java SequentialParallelDemo
```

**Exact stdout:**

```text
sequential=[1, 4, 9, 16, 25, 36]
parallel=[1, 4, 9, 16, 25, 36]
sum sequential=21
sum parallel=21
isParallel=false
```

Explanation: `List.of` has an encounter order matching the original element order. `map` is a transformation without side effects; `toList()` preserves the encounter order of an ordered Stream, even when work is executed in parallel. `sum()` yields the same sum in this integer example. `mode` called `sequential()` after `parallel()`, so the final mode flag is false.

This **does not mean elements must be processed one by one in the order 1, 2, 3… in a parallel stream**. Parallel mode may process elements across multiple threads in a different order, and then combine the results to preserve the output guarantees of the terminal operation.

## 4. Encounter order vs. execution order

**Encounter order** is the order of elements determined by the source and order-preserving operations. For example, `List.of("A","B","C")` has the encounter order `A, B, C`. However, `HashSet` does not guarantee a deterministic encounter order like `List`.

**Execution order** is the order in which operations are actually executed in the pipeline. With a parallel Stream, operations on elements can occur on different threads and at different times. You must not rely on the execution order of `map`, `filter`, or `peek` to infer the order of results.

| API | For a Stream with encounter order | What to understand |
| --- | --- | --- |
| `toList()` | Preserves encounter order in the resulting list | Internal work can still run in parallel. |
| `forEach(action)` | Does not guarantee action invocation order when parallel | Do not use for outputting logs that must be ordered. |
| `forEachOrdered(action)` | Invokes action in encounter order | May incur coordination overhead; does not force all upstream steps to run sequentially. |
| `findFirst()` | Selects the first element in encounter order if present | Can be more expensive than `findAny` in an ordered pipeline. |
| `findAny()` | Allowed to return any matching element | Do not assume it always returns the first element. |
| `sorted()` | Produces a sorted order according to the appropriate comparator/natural ordering | It is a stateful operation and can be expensive. |
| `unordered()` | Drops the requirement to preserve encounter order | Does not mean the result is randomly shuffled. |

Ordering guarantees are only meaningful **when the source/pipeline has an encounter order**. If the source is unordered, `forEachOrdered` cannot invent an “original order” that the source itself does not provide.

## 5. Java 17 Example: ordered output and non-guaranteed behavior

Save as **`StreamOrderDemo.java`**:

```java
import java.util.List;
import java.util.Locale;

public class StreamOrderDemo {
    public static void main(String[] args) {
        List<String> words = List.of("A", "B", "C", "D");

        List<String> lower = words.parallelStream()
                .map(word -> word.toLowerCase(Locale.ROOT))
                .toList();
        System.out.println("toList=" + lower);

        System.out.print("forEachOrdered=");
        words.parallelStream().forEachOrdered(System.out::print);
        System.out.println();

        System.out.println("findFirst="
                + words.parallelStream().findFirst().orElse("-"));

        boolean anyIsInList = words.parallelStream()
                .findAny()
                .filter(words::contains)
                .isPresent();
        System.out.println("findAny belongs=" + anyIsInList);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 StreamOrderDemo.java
java StreamOrderDemo
```

**Exact stdout:**

```text
toList=[a, b, c, d]
forEachOrdered=ABCD
findFirst=A
findAny belongs=true
```

`findAny()` may choose any of the four elements; the example **does not print that value directly** and only checks that it belongs to the source list, so the output is always deterministic and independent of scheduling. `forEachOrdered` preserves action order according to encounter order. With `forEach` on a parallel stream, **you must not expect a fixed stdout** such as `ABCD`, because the order can vary between runs.

You should not use `forEachOrdered` just to force all preceding computation steps to run sequentially; it guarantees the order of the **output action**, not the internal execution sequence of the entire pipeline.

## 6. Lazy evaluation and terminal operations

**Laziness** applies to intermediate operations in both modes. Example:

```java
var pipeline = List.of(1, 2, 3, 4)
        .parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 10);

// Here, the pipeline has not been consumed yet.
List<Integer> result = pipeline.toList(); // [20, 40]
```

This is a snippet that can be placed inside a method, with `import java.util.List;`. Calling `parallelStream()` or declaring `map` does not automatically start all transformations. `toList()` is what triggers the pipeline.

Terminal operations can **short-circuit**:
- `anyMatch` can stop as soon as an element matching the predicate is found.
- `allMatch` can stop as soon as an element not matching the predicate is found.
- `noneMatch` can stop as soon as a matching element is seen.
- `findFirst`, `findAny` can finish once a suitable result is found according to their contracts.

In a parallel stream, multiple elements may be in flight almost simultaneously when an operation decides to stop. Therefore, **there is no promise that lambdas in `filter`, `map`, or `peek` will be called exactly once for every source element**. Some terminal operations may also elide certain steps when optimizations are valid. Avoid required side effects in intermediate operations.

For an empty Stream, `anyMatch` is false; `allMatch` and `noneMatch` are both true. This rule does not change when switching to parallel.

## 7. Reduce: the combining operation must be associative

A parallel stream typically needs to **split the input, compute partial results, and then combine the results**. Therefore, reduction operations like `reduce` require an operator with the appropriate properties:

- **Associative:** `(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)`.
- **Identity:** `identity ⊕ x = x` and `x ⊕ identity = x`.
- Behavior must be **non-interfering** and **stateless** per the Stream contract for predictable results.

For non-overflowing integer addition in the example data, `0` is the identity and addition is associative. Standard subtraction is **not** associative.

Safe pattern:

```java
int sum = java.util.stream.IntStream.rangeClosed(1, 6)
        .parallel()
        .reduce(0, Integer::sum); // 21
```

Pattern that is **unsuitable for expecting identical results across both modes**:

```java
int value = java.util.stream.IntStream.rangeClosed(1, 6)
        .parallel()
        .reduce(0, (a, b) -> a - b);
```

Subtraction is not associative, so different ways of splitting and combining elements can lead to a different result than a sequential chain of subtractions. Do not assume a fixed stdout value for the parallel expression in this snippet.

**Note on floating-point numbers:** IEEE 754 `double` addition has rounding errors; changing how additions are grouped in parallel can produce slight differences compared to sequential execution. When numerical computation requires strict precision/reproducibility, you must design the calculation and error bounds accordingly, rather than just adding `parallel()`.

## 8. Java 17 Example: safe reduce and collect

Save as **`ParallelReductionDemo.java`**:

```java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelReductionDemo {
    public static void main(String[] args) {
        int sequentialSum = IntStream.rangeClosed(1, 8)
                .sum();
        int parallelSum = IntStream.rangeClosed(1, 8)
                .parallel()
                .reduce(0, Integer::sum);

        List<Integer> evens = IntStream.rangeClosed(1, 8)
                .parallel()
                .filter(n -> n % 2 == 0)
                .boxed()
                .toList();

        List<String> names = List.of("a", "bb", "ccc", "dd", "eee");
        Map<Integer, Long> lengthCounts = names.parallelStream()
                .collect(Collectors.groupingBy(
                        String::length,
                        TreeMap::new,
                        Collectors.counting()));

        System.out.println("sequentialSum=" + sequentialSum);
        System.out.println("parallelSum=" + parallelSum);
        System.out.println("evens=" + evens);
        System.out.println("lengthCounts=" + lengthCounts);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 ParallelReductionDemo.java
java ParallelReductionDemo
```

**Exact stdout:**

```text
sequentialSum=36
parallelSum=36
evens=[2, 4, 6, 8]
lengthCounts={1=1, 2=2, 3=2}
```

In `parallelSum`, `Integer::sum` is an associative addition operator with identity 0 on these small inputs. `evens` preserves the encounter order of `IntStream.rangeClosed` through `filter` and `toList`. `groupingBy` uses `TreeMap::new` so the resulting map is displayed in ascending numeric key order; `Collectors.counting()` counts elements in each length group.

Key takeaway: **a properly designed collector** allows the Stream framework to manage intermediate containers and combine results. There is no need to create a shared `ArrayList` manually and have multiple threads call `add` inside `forEach`.

## 9. Side effects and shared mutable state: a common source of bugs

Here is a code snippet that is **unsafe** if switched to parallel:

```java
List<Integer> output = new java.util.ArrayList<>();
java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .forEach(output::add); // UNSAFE: ArrayList is modified concurrently
```

The snippet above is a warning example: `ArrayList` does not support multiple threads concurrently adding elements without proper synchronization. Lost updates, corrupted state, exceptions, or unpredictable results can occur. Do not use it for benchmarking and do not assume the result will always have exactly 1,000 elements.

The right way to write this when you want a result list:

```java
List<Integer> output = java.util.stream.IntStream.rangeClosed(1, 1000)
        .parallel()
        .boxed()
        .toList();
```

This snippet is independent of the one above; if combined into the same method, rename one of the variables. `Stream.toList()` returns a list that is **unmodifiable through its API**. If you need a mutable result, use an appropriate collector such as `collect(Collectors.toCollection(ArrayList::new))` so the framework manages the aggregation.

### Why isn’t `synchronized` a “speed booster”?

Wrapping every operation in a synchronization lock can make individual updates safe, but threads will contend and serialize the critical section. In that case, a parallel stream can be **slower** than a sequential stream. Moreover, making individual updates safe does not guarantee invariants across multiple variables/structures.

Functions passed to `filter`, `map`, and `reduce` should preferably be:
- **Non-interfering:** do not modify the data source being traversed by the Stream.
- **Stateless:** results do not depend on mutable state that changes between invocations.
- **Deterministic when needed:** use operations where the same input produces the same output, avoiding reliance on threads or scheduling order.

For tasks such as writing files, making network calls, updating databases, or emitting events where ordering is critical, design an explicit task/concurrency API instead of trusting `parallelStream().forEach` to provide ordering, retry, backpressure, or transaction semantics.

## 10. forEach, forEachOrdered, collect: choosing by intent

If you want to **compute data**, prefer `map` followed by a terminal operation such as `toList`, `collect`, `reduce`, or `sum`. If you want to **perform an action** for each element, `forEach` is appropriate but does not guarantee order on a parallel stream.

```java
List<String> words = List.of("A", "B", "C");
words.parallelStream().forEachOrdered(System.out::print);
System.out.println(); // prints ABC in encounter order
```

This illustrative snippet requires `import java.util.List;`. If you use `forEach` instead of `forEachOrdered`, do not write tests expecting the log to always be in `ABC` order.

Keep in mind: `forEachOrdered` can add overhead to maintain order, and it does not mean every preceding `map`/`filter` step runs on only one thread.

With `collect`, the framework can collect into separate containers and then combine results according to the collector. Using a proper collector is usually better than a mutable variable outside the pipeline. `CONCURRENT` collectors have their own rules; **not every collector is concurrent**, but standard collectors like `toList` or `groupingBy` can still be used safely by the framework in parallel reductions in accordance with their contracts.

## 11. findFirst, findAny, and short-circuiting

For an ordered stream, `findFirst()` has a contract to select **the first element in encounter order**. `findAny()` is allowed to select any element, so it can be more efficient when the first element is not needed in parallel mode.

```java
int first = List.of(10, 20, 30)
        .parallelStream()
        .findFirst()
        .orElse(-1); // 10
```

This illustrative snippet requires `import java.util.List;`. If you replace `findFirst` with `findAny`, do not rely on it definitely returning 10 even if a few runs happen to show that.

Operations like `anyMatch`, `allMatch`, `noneMatch`, and `findAny` can **short-circuit**. However, when a pipeline runs in parallel, work may already be underway on other elements before the result is determined. Therefore, do not use side effects in `peek` to infer that a specific number of elements will always be traversed.

## 12. sorted, distinct, limit, and unordered in parallel streams

Some intermediate operations are *stateful* or require coordination:
- `sorted()` must determine the order of the entire relevant set of elements.
- `distinct()` needs to detect duplicate elements via `equals`/`hashCode`; for an ordered parallel stream, preserving the first-encountered element can increase overhead.
- `limit(n)` on an ordered parallel stream needs to preserve **the first n elements**, so it can be more expensive than when order is not needed.
- `unordered()` allows dropping the encounter order requirement, enabling better optimization for some order-independent tasks.

**Do not misunderstand `unordered()` as “shuffling randomly”**. It only removes the pipeline’s ordering constraint; the result might coincidentally retain the original order. If the output requires a stable order, do not add `unordered()` just to speed things up.

`takeWhile` and `dropWhile` on ordered streams also have constraints to preserve prefixes according to encounter order; when run in parallel, maintaining the exact prefix can require costly coordination. If ordering is a business requirement, accept this cost or use a different algorithm rather than sacrificing correctness guarantees.

## 13. When can a parallel stream be faster?

A parallel stream is **not automatically a performance optimization**. Consider several factors:

| Factor | May favor parallel | May be disadvantageous |
| --- | --- | --- |
| Element count | Large datasets | Small datasets, high split/merge overhead |
| Processing cost per element | CPU-bound, heavy enough, independent | Very lightweight operations |
| Source and splittability | Arrays, `ArrayList`, `IntStream.range` are usually easy to split | Sources that are hard to split or costly to traverse |
| Ordering | No need to preserve order at every step | Requires ordered `forEachOrdered`, `findFirst`, `limit` |
| Reduction | Associative, proper identity, appropriate collector | Side effects, non-associative combining operations |
| State | No shared mutable state | Lock contention, race conditions |
| Runtime environment | Many CPU cores and sufficient resources | CPU already busy, resource limits, contended shared pool |

Parallel streams in the JDK typically use a **Fork/Join**-based execution mechanism (usually the common pool in typical contexts). Thread count, work splitting, ordering, and performance gains are not fixed contracts that code should depend on. When threads must wait on I/O or contend for shared resources, parallel streams may be unsuitable; asynchronous architectures or controlled executors may be clearer.

To measure properly:
1. Ensure the algorithm in both modes has the same semantics and results.
2. Use realistic data, sufficiently large element counts, and an environment and configuration matching production.
3. Warm up the JIT, repeat multiple times, and avoid single-shot measurements.
4. Use a rigorous benchmarking tool such as **JMH** instead of drawing conclusions from a single `System.nanoTime()` measurement.
5. Observe CPU, garbage collection, allocation, and contention, not just wall-clock time.

**Prefer sequential streams as the default**, and only switch to parallel when work is independent, results are correct, and benchmarks demonstrate a benefit.

## 14. Common misconceptions

1. **“Parallel streams always run faster.”** False; overhead and contention can outweigh the benefits.
2. **“parallel() immediately runs the pipeline on another thread.”** False; the pipeline remains lazy until the terminal operation and promises no specific thread.
3. **“toList() on parallel always reverses or scrambles order.”** False; with a deterministic encounter order, `toList` preserves the result order.
4. **“forEach() on parallel always follows source order.”** False; use `forEachOrdered` when action order must be guaranteed.
5. **“forEachOrdered makes all upstream steps sequential.”** False; it only constrains the order of the terminal action.
6. **“findAny() always returns the first element.”** False; the result is allowed to be any element.
7. **“Using an ArrayList outside the lambda to collect in parallel.”** Dangerous because multiple threads modify the same collection.
8. **“Just adding synchronized gives parallel speed.”** No; locks can eliminate the benefits of splitting the work.
9. **“Any reduce operation works with parallel.”** False; it requires associativity and a valid identity.
10. **“A Stream can run a terminal operation multiple times.”** False; create a new pipeline each time.
11. **“peek is suitable for recording every element guaranteed to be processed.”** False; optimizations and short-circuiting can make observed behavior differ from expectations.
12. **“Floating-point numbers will always produce the exact same result bits as sequential.”** Not guaranteed with different operation groupings.
13. **“unordered() randomly shuffles the order.”** False; it only removes the requirement to preserve encounter order.
14. **“Having many cores means you should always use parallel.”** False; hard-to-split sources, lightweight operations, or a busy pool can worsen performance.
15. **“Parallel mode replaces concurrency design.”** False; it does not provide transactions, retries, backpressure, or explicit thread lifecycle management.

## 15. Self-check

**Question 1.** What are two ways to create a parallel Stream from `List<Integer> values`?

**Answer:** `values.parallelStream()` and `values.stream().parallel()`.

**Question 2.** Does `values.parallelStream().map(x -> x * 2).toList()` preserve the encounter order of the List?

**Yes.** If the source List has an encounter order, the `toList()` result preserves that order, even though the computation steps may execute in parallel.

**Question 3.** Is `forEach` or `forEachOrdered` appropriate when you want to print elements of a List in exact order?

**Answer:** `forEachOrdered`. Choose `forEach` when action order does not need to be guaranteed.

**Question 4.** Why shouldn’t `reduce(0, (a,b) -> a-b)` be used expecting the same result between sequential and parallel streams?

Because subtraction is **not associative**; splitting the data and combining partial results can change the outcome.

**Question 5.** Is it safe to declare `new ArrayList<>()` outside and then call `parallelStream().forEach(list::add)`?

**No.** `ArrayList` is not safe for concurrent updates by multiple threads. Use `toList()` or an appropriate collector.

**Question 6.** Does `parallel().sequential()` create two phases—first parallel, then sequential—when the terminal operation runs?

**No.** These operations set the pipeline mode; the final mode is sequential, rather than “cutting” the pipeline into two separate execution halves.

**Question 7.** When should `findAny()` be preferred over `findFirst()`?

When you only need **any element** matching the condition without needing to guarantee the first element, especially in an ordered parallel pipeline.

**Question 8.** What should you do to know whether parallel actually benefits your program?

Ensure the logic is correct and there is no uncontrolled shared mutable state, then benchmark on a realistic workload (e.g., with JMH); do not infer from the name `parallel`.

**Remember:** **Sequential streams** are the simple, predictable choice and should usually be the default. **Parallel streams** are suitable when work is independent, splittable, large enough, and reduced/combined using valid operations. Do not trade correctness, required encounter order, or data safety for an unmeasured promise of speed.
