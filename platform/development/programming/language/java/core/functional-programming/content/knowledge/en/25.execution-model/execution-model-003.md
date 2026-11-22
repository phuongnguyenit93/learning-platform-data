# Streams process elements one by one instead of running each step on the entire collection

## 1. Central idea: pipelines instead of stage-by-stage processing loops

When first learning the `Stream API`, a common misconception is that Java always runs **the entire `filter` on all elements first, and then the entire `map` on the filtered elements**, as if each operation immediately creates an intermediate list.

For a **sequential pipeline** consisting of **stateless** *intermediate operations* like `map` and `filter`, a clearer mental model is:

**An element passes through successive operations in the pipeline, and only then does Java move on to the next element when the terminal operation needs a result.**

Example:

```java
List<String> result = Stream.of("a", "bb", "ccc")
        .filter(s -> s.length() >= 2)
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [BB, CCC]
```

One way to visualize this sequential pipeline:

```text
"a"   -> filter(false) -> discarded, map is not called
"bb"  -> filter(true)  -> map("BB")  -> passed to result
"ccc" -> filter(true)  -> map("CCC") -> passed to result
```

There is **not necessarily** a temporary list holding all elements after `filter` before `map` starts. This characteristic is often called **pipeline fusion** or **vertical processing** for stateless operations.

However, this is a **helpful explanatory model**, not a guarantee that *every* Stream pipeline processes one element completely from start to finish before touching the next element. Stateful operations like `sorted`, `distinct`, certain cases of `limit`, and parallel processing make observable behavior more complex. This lesson will distinguish each case precisely.

## 2. Distinguishing source, intermediate operation, and terminal operation

A Stream pipeline has three parts:

1. **Data source:** `List.stream()`, `Stream.of(...)`, `IntStream.range(...)`, `Files.lines(...)`, etc.
2. **Intermediate operations:** `filter`, `map`, `flatMap`, `distinct`, `sorted`, `limit`... usually return a new stream, build a processing description, and are *lazy*.
3. **Terminal operation:** `toList`, `collect`, `sum`, `reduce`, `forEach`, `findFirst`, `anyMatch`... triggers consumption of the pipeline to produce a result or perform an action.

Example:

```java
List<Integer> selected = List.of(1, 2, 3, 4, 5)
        .stream()                 // Source
        .filter(n -> n % 2 == 0)  // Intermediate: keep even numbers only
        .map(n -> n * 10)         // Intermediate: transform
        .toList();                // Terminal: collect

System.out.println(selected); // [20, 40]
```

`filter` and `map` **do not immediately finish building two intermediate lists** at the moment they are called. Actual execution is coordinated when the terminal operation needs results.

Note that `List.of` provides a source with an encounter order, so `toList` returns results in the order of the remaining elements: 2 before 4.

### Lazy does not mean never executed

`lazy` does not mean the pipeline is merely a promise that never runs. It means work is **deferred until there is a demand to consume**, allowing the system to coordinate transformations and avoid processing unnecessary elements in many situations.

```java
Stream<String> pipeline = Stream.of("a", "b", "c")
        .map(String::toUpperCase);

// No terminal operation yet, so the result List has not been created.
List<String> values = pipeline.toList(); // [A, B, C]
```

A stream can only be consumed once; after `toList()`, you must not call `pipeline.toList()` again or attach more processing branches to the same already-used stream. If you want to compute multiple results, create new streams from a re-traversable source.

## 3. Two different processing approaches despite the same result

Suppose there are four products, each with an original price. Requirements:

- Increase each price by 10.
- Keep only products whose increased price is **at least 100**.
- Create a `code=price` label for products that meet the threshold.

### Stage-by-stage loop approach (*stage by stage*)

```java
List<Item> adjusted = new ArrayList<>();
for (Item item : items) {
    adjusted.add(new Item(item.code(), item.price() + 10));
}

List<Item> accepted = new ArrayList<>();
for (Item item : adjusted) {
    if (item.price() >= 100) {
        accepted.add(item);
    }
}

List<String> labels = new ArrayList<>();
for (Item item : accepted) {
    labels.add(item.code() + "=" + item.price());
}
```

This snippet is **illustrative**; `Item`, `items`, and the imports are fully declared in the program in section 5. This approach processes as follows:

```text
All Items -> increase price of every Item
All increased Items -> check threshold
All Items meeting threshold -> create label
```

There are two intermediate lists `adjusted` and `accepted` existing in between, if the programmer builds them as shown above.

### Sequential Stream approach with stateless operations

```java
List<String> labels = items.stream()
        .map(item -> new Item(item.code(), item.price() + 10))
        .filter(item -> item.price() >= 100)
        .map(item -> item.code() + "=" + item.price())
        .toList();
```

A pipeline lets you describe the rules in a single chain, and the `map`/`filter` operations can be fused element by element during traversal.

Conceptual flow:

```text
Item A -> increase price -> check fails   -> skip label-creating map
Item B -> increase price -> check passes  -> create label B=...
Item C -> increase price -> check fails   -> skip label-creating map
Item D -> increase price -> check passes  -> create label D=...
```

Both approaches **are designed to return the same data**, but **the execution order of the stages** is different. This difference can also matter when operations have side effects, encounter errors, or when the terminal only needs part of the data.

## 4. Why are `map` and `filter` easy to coordinate element by element?

`map` takes one element as input and returns a new value. `filter` receives one element and decides whether to keep or discard it. In the typical case, both are **stateless** operations: how an element is processed does not require remembering all previous elements.

Example:

```java
Stream.of("A", "BB", "CCC")
        .map(String::length)
        .filter(length -> length >= 2)
        .forEachOrdered(System.out::println);
```

Stdout:

```text
2
3
```

When examining `"A"`, `map` produces 1, and `filter` discards 1. Java does not need to store 1 in an intermediate list only to filter everything later in another pass.

**Important condition:** `map` and `filter` should be functions that do not depend on how other elements are being or have been processed. If a mapper modifies shared state or depends on the execution order of multiple elements, lazy evaluation, optimizations, or parallelization can make behavior unpredictable.

### Filtering out elements early reduces downstream work

```java
List<String> labels = Stream.of("A", "BBBB", "CC")
        .filter(s -> s.length() >= 3)
        .map(s -> "Accepted " + s)
        .toList();

System.out.println(labels); // [Accepted BBBB]
```

`map` only needs to process `"BBBB"` because the other two strings have already been discarded by `filter`. This often avoids unnecessary transformation work.

However, you should not assume that reversing the order of `filter` and `map` always yields the same result. If `filter` depends on the **transformed** value, the order is part of the semantics:

```java
List<Integer> afterMap = Stream.of(9, 10)
        .map(n -> n + 1)
        .filter(n -> n >= 11)
        .toList();
// [11]

List<Integer> beforeMap = Stream.of(9, 10)
        .filter(n -> n >= 11)
        .map(n -> n + 1)
        .toList();
// []
```

The two pipelines produce different results because the filter predicate receives values at different points. Only reorder operations when you have verified that the transformation is logically equivalent.

## 5. Complete Java 17 program: observing execution behavior

The program below passes the same data through multiple paths:

- A sequential Stream with stateless `map`/`filter` and a terminal operation.
- Stage-by-stage `for` loops with intermediate lists.
- A lazy pipeline without a terminal operation yet.
- A short-circuiting `findFirst` terminal operation.
- The `sorted` operation and the result of a parallel stream with encounter order.

The trace messages in the example are used **in a controlled way for learning** how sequential execution paths work. In real applications, you should not write business logic that depends on side effects in intermediate operations, because the Stream API is allowed to optimize or skip certain invocations when the result does not change.

Create the file **`StreamExecutionDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.IntStream;
import java.util.stream.Stream;

public class StreamExecutionDemo {
    record Item(String code, int price) {}

    static List<Item> sample() {
        return List.of(
                new Item("A", 40),
                new Item("B", 120),
                new Item("C", 80),
                new Item("D", 150)
        );
    }

    static List<String> withStream(
            List<Item> items, List<String> trace) {
        return items.stream()
                .map(item -> {
                    trace.add("adjust:" + item.code());
                    return new Item(
                            item.code(), item.price() + 10);
                })
                .filter(item -> {
                    trace.add("check:" + item.code());
                    return item.price() >= 100;
                })
                .map(item -> {
                    trace.add("label:" + item.code());
                    return item.code() + "=" + item.price();
                })
                .toList();
    }

    static List<String> withLoops(
            List<Item> items, List<String> trace) {
        List<Item> adjusted = new ArrayList<>();
        for (Item item : items) {
            trace.add("adjust:" + item.code());
            adjusted.add(new Item(
                    item.code(), item.price() + 10));
        }

        List<Item> accepted = new ArrayList<>();
        for (Item item : adjusted) {
            trace.add("check:" + item.code());
            if (item.price() >= 100) {
                accepted.add(item);
            }
        }

        List<String> labels = new ArrayList<>();
        for (Item item : accepted) {
            trace.add("label:" + item.code());
            labels.add(item.code() + "=" + item.price());
        }
        return labels;
    }

    public static void main(String[] args) {
        List<Item> items = sample();

        List<String> streamTrace = new ArrayList<>();
        List<String> streamResult = withStream(items, streamTrace);
        System.out.println("Stream trace: " + streamTrace);
        System.out.println("Stream result: " + streamResult);

        List<String> loopTrace = new ArrayList<>();
        List<String> loopResult = withLoops(items, loopTrace);
        System.out.println("Loop trace: " + loopTrace);
        System.out.println("Loop result: " + loopResult);

        // Create an intermediate pipeline without triggering processing yet.
        List<String> lazyTrace = new ArrayList<>();
        Stream<String> lazy = items.stream()
                .map(item -> {
                    lazyTrace.add("code:" + item.code());
                    return item.code();
                });
        System.out.println("Before terminal: " + lazyTrace);
        List<String> codes = lazy.toList();
        System.out.println("After terminal: " + lazyTrace);
        System.out.println("Codes: " + codes);

        // A short-circuiting terminal only requests enough elements.
        List<String> shortTrace = new ArrayList<>();
        Optional<Integer> firstEven = Stream.of(1, 2, 3, 4, 5)
                .filter(n -> {
                    shortTrace.add("test:" + n);
                    return n % 2 == 0;
                })
                .map(n -> {
                    shortTrace.add("transform:" + n);
                    return n * 10;
                })
                .findFirst();
        System.out.println("Short trace: " + shortTrace);
        System.out.println("First even x10: "
                + firstEven.orElse(-1));

        // sorted is a stateful operation: it needs to examine data
        // from multiple elements to determine the order.
        List<Integer> sorted = Stream.of(3, 1, 2)
                .sorted()
                .toList();
        System.out.println("Sorted: " + sorted);

        List<Integer> firstTwoEvens = IntStream.rangeClosed(1, 20)
                .filter(n -> n % 2 == 0)
                .limit(2)
                .boxed()
                .toList();
        System.out.println("First two evens: " + firstTwoEvens);

        // Results with encounter order still preserve order,
        // even though the mapper in a parallel pipeline may run out of order.
        List<String> parallel = IntStream.rangeClosed(1, 4)
                .parallel()
                .mapToObj(n -> "X" + n)
                .toList();
        System.out.println("Parallel result: " + parallel);
    }
}
```

Compile and run:

```bash
javac --release 17 StreamExecutionDemo.java
java StreamExecutionDemo
```

**Program stdout with the sequential streams in the trace section:**

```text
Stream trace: [adjust:A, check:A, adjust:B, check:B, label:B, adjust:C, check:C, adjust:D, check:D, label:D]
Stream result: [B=130, D=160]
Loop trace: [adjust:A, adjust:B, adjust:C, adjust:D, check:A, check:B, check:C, check:D, label:B, label:D]
Loop result: [B=130, D=160]
Before terminal: []
After terminal: [code:A, code:B, code:C, code:D]
Codes: [A, B, C, D]
Short trace: [test:1, test:2, transform:2]
First even x10: 20
Sorted: [1, 2, 3]
First two evens: [2, 4]
Parallel result: [X1, X2, X3, X4]
```

**How to read and verify:**

- For A, the price adjustment produces 50, then `filter` sees 50 is less than 100 and discards it; therefore there is no `label:A`.
- For B, the price becomes 130, passes `filter`, and then creates the label `B=130`.
- For C, the price becomes 90, so it is discarded.
- For D, the price becomes 160, so it creates the label `D=160`.
- The Stream trace is interleaved element by element: `adjust:A, check:A` and then B; whereas the `for`-loop trace has four `adjust` steps before any `check` step runs.
- Both results are `[B=130, D=160]`. The logical order of steps does not change the goal when transformations are defined consistently.
- `lazyTrace` is empty before the terminal operation: merely building the pipeline does not yet need to apply `map`. After `toList`, all four codes have been produced.
- `findFirst` on a sequential Stream only needs the first even number, which is 2: it checks 1, checks 2, and then transforms 2 into 20. It does not need to examine 3, 4, 5.
- `sorted` produces `[1,2,3]` from `3,1,2`; this is an example of an operation that cannot be fully described by the idea "one element passes through every step immediately."
- `limit(2)` is applied after `filter`, so it takes exactly the first two even numbers `[2,4]`.
- `parallel` can process elements across multiple threads, but `toList` preserves the encounter order of the `IntStream.rangeClosed` source, so the result is still `[X1,X2,X3,X4]`.

> **Important note about tracing:** the fundamental contract is the result of the Stream operations, not the exact count or execution order of arbitrary side effects in every intermediate operation. For the specific stateless sequential pipeline above, the trace shows how Java processes through the steps. However, production code should not depend on how many times `map`, `filter`, or `peek` are called across all optimization cases.

## 6. Only the terminal operation causes the pipeline to execute

`Stream` uses a lazy mechanism for most intermediate operations:

```java
Stream<Integer> pipeline = Stream.of(1, 2, 3)
        .map(n -> n * n)
        .filter(n -> n > 2);

// No list is collected or data printed at declaration time.
List<Integer> result = pipeline.toList();
System.out.println(result); // [4, 9]
```

Note: calling `map` in the first part builds a pipeline; `toList` is what requests the result.

Different terminal operations may request different numbers of elements:

| Terminal | Purpose | Does it need to traverse the whole source? |
| --- | --- | --- |
| `toList()` | Collect resulting elements | Usually needs all results, unless there is an upstream limit |
| `collect(...)` | Collect/group/aggregate | Depends on collector; usually processes all elements |
| `forEach(...)` | Perform an action | Usually traverses all remaining elements |
| `sum()` on a primitive stream | Compute sum | Normally needs all elements |
| `findFirst()` | Get the first element in encounter order | Can terminate early |
| `findAny()` | Get any element | Can terminate early |
| `anyMatch(...)` | Does at least one element match? | Can stop as soon as true is found |
| `allMatch(...)` | Do all elements match? | Can stop as soon as false is found |
| `noneMatch(...)` | Do no elements match? | Can stop as soon as true is found |
| `count()` | Count elements | Can be optimized from source size without applying every intermediate step |

**Specifically `count()`:** for certain sources with a known size and a pipeline that does not change the element count, the JDK can compute the count without going through every intermediate operation. For example, you should not use a `map` just to log and expect `count` to always invoke it:

```java
long count = List.of("A", "B", "C").stream()
        .map(s -> {
            System.out.println("map " + s);
            return s;
        })
        .count();

System.out.println("Count: " + count);
```

`count` must return `3`, but you should not assert that the three lines `map A`, `map B`, `map C` are guaranteed to be printed. This illustrates why **side effects in intermediate operations are not an application contract**.

## 7. Short-circuiting: stopping before traversing all elements

An important benefit of building pipelines lazily is that a terminal operation does not always need to process the entire source. If you only need to know "whether a matching element exists," `anyMatch` can stop as soon as it encounters a matching element.

Example:

```java
boolean exists = Stream.of(1, 3, 4, 6)
        .map(n -> n * 2)
        .anyMatch(n -> n >= 8);

System.out.println(exists); // true
```

Explanation in a sequential stream:

- 1 → 2, not yet 8.
- 3 → 6, not yet 8.
- 4 → 8, `anyMatch` sees true and can stop.
- No need to transform 6.

You should not rely on every mapper having run like a full loop. Nor should you assume `findAny` picks the first element: `findAny` can return any element, especially during parallel execution; use `findFirst` when the first element in order is required.

### `filter` before `limit`

```java
List<Integer> evens = IntStream.rangeClosed(1, 100)
        .filter(n -> n % 2 == 0)
        .limit(3)
        .boxed()
        .toList();

System.out.println(evens); // [2, 4, 6]
```

`limit(3)` counts **elements that passed the filter**, not the first three numbers from the source. This illustrates how a downstream operation can cause the pipeline to stop requesting more elements from the source once enough results are received.

Swapping `limit` and `filter` gives a different result:

```java
List<Integer> other = IntStream.rangeClosed(1, 100)
        .limit(3)
        .filter(n -> n % 2 == 0)
        .boxed()
        .toList();

System.out.println(other); // [2]
```

Keep the business logic intact when choosing the order of operations.

## 8. Stateful intermediate operations: when multiple elements must be seen

The model "each element passes through the entire pipeline before moving to the next element" holds best for **stateless** operation chains. Some operations need state or information from other elements.

### `sorted()`: usually needs to see all data before emitting results

To accurately sort an entire finite stream according to a comparator, `sorted` usually has to **gather and sort the elements** before downstream receives the first result. Example:

```java
List<Integer> result = Stream.of(3, 1, 2)
        .map(n -> n * 10)
        .sorted()
        .map(n -> n + 1)
        .toList();

System.out.println(result); // [11, 21, 31]
```

A visual diagram:

```text
Source 3, 1, 2
  -> map(*10): 30, 10, 20
  -> sorted: must determine order 10, 20, 30
  -> map(+1): 11, 21, 31
  -> toList
```

You should not imagine that `3` can immediately go all the way to `toList` before knowing whether `1` or `2` is smaller than it.

An unbounded stream placed before `sorted().toList()` may never terminate, because there is no general way to completely sort an infinite sequence by standard criteria and then return all results.

### `distinct()`: needs to know which elements have already been seen

`distinct` uses information about previously seen elements to remove duplicates:

```java
List<String> unique = Stream.of("A", "B", "A", "C", "B")
        .distinct()
        .toList();

System.out.println(unique); // [A, B, C]
```

It may maintain state to track values already seen. Therefore `distinct` is not like `map` or `filter`, which purely process each element independently of other elements. On an ordered stream, `distinct` is stable with respect to encounter order: it keeps the first occurrence of each value.

For large datasets, especially parallel ordered streams, the cost of maintaining state and order for `distinct` can be high. Do not assume a Stream **always saves more memory** than a hand-written loop.

### `limit()` and `skip()`: count-based state

`limit(n)` counts how many elements have been accepted at its position in the pipeline and stops after n. `skip(n)` discards the first n elements. These operations have state related to order/count, although they usually do not need to buffer the entire source like `sorted`.

```java
List<Integer> result = IntStream.rangeClosed(1, 7)
        .skip(2)
        .limit(3)
        .boxed()
        .toList();

System.out.println(result); // [3, 4, 5]
```

When combining `skip`/`limit` with a parallel ordered stream, Java may need to coordinate to preserve the exact encounter order.

## 9. `flatMap()`: one input element can produce multiple results

`flatMap` is not a one-input-to-one-output `map`. It turns one parent element into **a child stream**, and then concatenates the elements from those child streams into the output pipeline.

```java
List<List<String>> groups = List.of(
        List.of("A", "B"),
        List.of(),
        List.of("C", "D")
);

List<String> flat = groups.stream()
        .flatMap(List::stream)
        .toList();

System.out.println(flat); // [A, B, C, D]
```

In a sequential stream, you can picture processing the first group, passing A and B downstream, then the empty group emitting no elements, and finally the C,D group. However, each parent element can produce 0, 1, or many child elements, so you cannot simply express it as "each input element corresponds to exactly one output element."

`flatMap` also involves the lifecycle of child streams; when the mapper creates streams backed by resources such as files, you need to design I/O management carefully. Only treat it as a pure transformation if the mapper/child source itself performs no dangerous side effects.

## 10. Sequential Streams and Parallel Streams differ

### Sequential: the element-by-element model is usually intuitive

`List.stream()` creates a sequential stream by default. With an ordered source and simple stateless intermediate operations, an element typically flows through the pipeline in encounter order, as in the `withStream` example.

### Parallel: multiple elements are processed concurrently

`List.parallelStream()` or `stream.parallel()` allows work to be split across multiple threads. Example:

```java
List<Integer> result = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(n -> n * 10)
        .boxed()
        .toList();

System.out.println(result); // [10, 20, 30, 40, 50]
```

`toList` preserves the encounter order of the `IntStream.rangeClosed` source. However, `map(n -> n * 10)` **is not necessarily called in the order n=1,2,3,4,5**, nor necessarily on a single thread.

There are three kinds of order to keep separate:

1. **Encounter order:** the logical order of elements from the source or established by `sorted`.
2. **Execution order:** the actual order in which lambdas are invoked; this can vary in a parallel pipeline.
3. **Result order:** the order of result elements produced by a terminal operation whose contract preserves encounter order, such as `toList` from an ordered source.

You must not take the result `[10,20,30,40,50]` as proof that every multiplication executed sequentially in that order.

### `forEach` vs. `forEachOrdered`

`forEach` does not guarantee that the action runs in encounter order, especially on a parallel stream:

```java
IntStream.rangeClosed(1, 5)
        .parallel()
        .forEach(System.out::println);
```

There is no guaranteed fixed stdout for this snippet.

If the final action must follow encounter order:

```java
IntStream.rangeClosed(1, 5)
        .parallel()
        .forEachOrdered(System.out::println);
```

The guaranteed result for the action order is:

```text
1
2
3
4
5
```

`forEachOrdered` does not force all upstream operations to become sequential. It only constrains the terminal action to follow the stream's encounter order.

## 11. Why avoid side effects in intermediate operations?

Although the trace example in this lesson writes to an `ArrayList` for illustration, production code should avoid relying on out-of-band actions inside `map`, `filter`, or `peek`.

Dangerous example when run in parallel:

```java
List<String> messages = new ArrayList<>();

// Anti-pattern: ArrayList is not thread-safe.
IntStream.rangeClosed(1, 1000)
        .parallel()
        .mapToObj(n -> {
            messages.add("N" + n);
            return "N" + n;
        })
        .toList();
```

Even though `toList()` preserves the result order, having multiple threads concurrently call `messages.add(...)` can cause data races, missing elements, or data corruption. Do not use an external mutable list for required logging from a parallel mapper.

A cleaner way:

```java
List<String> messages = IntStream.rangeClosed(1, 1000)
        .parallel()
        .mapToObj(n -> "N" + n)
        .toList();
```

The result is collected by the Stream API, with no need to manually update a shared mutable list. If you need to write to a database, audit, send messages, or call APIs, separate the data computation phase from the side-effect handling phase with an appropriate contract, including retry/idempotency and error management.

### Do not rely on `peek` to force a step to run

`peek` is often useful for debugging, but it is an intermediate operation. If downstream does not request elements or the JDK can optimize without changing the result, you cannot assert that `peek` always runs once for every element.

```java
long count = List.of("a", "b", "c").stream()
        .peek(System.out::println)
        .count();

System.out.println("Count: " + count);
```

`Count: 3` is the result you can rely on; whether a, b, c are printed or not should not be made a correctness condition of the program. Mandatory actions that must execute should not be hidden inside `peek`.

## 12. Exceptions and stopping the pipeline

Suppose a mapper throws an exception on the third element:

```java
List<Integer> values = List.of(1, 2, 3, 4);

try {
    values.stream()
            .map(n -> {
                if (n == 3) {
                    throw new IllegalArgumentException("bad 3");
                }
                return n * 10;
            })
            .forEachOrdered(System.out::println);
} catch (IllegalArgumentException ex) {
    System.out.println("Caught: " + ex.getMessage());
}
```

With the sequential pipeline and ordered source here, stdout is:

```text
10
20
Caught: bad 3
```

Element 4 is not printed after the mapper for element 3 throws. Actions that already occurred for 1 and 2 (printing to the console) **do not automatically roll back**. With a parallel pipeline, other elements may already be in progress or have been processed when the error occurs; do not use a parallel processing flow under the assumption that all work will stop instantaneously without producing side effects.

An exception in `map` can also propagate through the pipeline when the terminal operation runs, rather than necessarily being thrown **at the moment the `map(...)` statement is written**, because mapper evaluation is lazy.

## 13. Optimization: does not mean every operation is always called once

The Stream API guarantees the **result semantics** of the pipeline according to the contracts of the source, intermediate, and terminal operations. It may perform valid optimizations such as skipping steps that do not affect the result.

Therefore, the following statements **are not true in all cases**:

- "Every source element always passes through every operation exactly once."
- "Every element runs `map` first and only then runs `filter`."
- "Simply creating the stream already executes the mapper."
- "`count` always calls `map` on each element."
- "A parallel stream still runs the mapper in encounter order."
- "Putting `sorted` in the middle of a pipeline still finishes processing each element immediately before moving to the next element."
- "Using `forEachOrdered` makes all preceding steps run sequentially."

The accurate model is: Streams **evaluate lazily**, coordinate operations when the terminal requests results, can **fuse** stateless operations per element, but can also **buffer state, short-circuit, optimize, or parallelize** according to the pipeline's rules.

### Does it always save more memory than a loop?

No. For stateless `map`/`filter` operations, Streams often avoid building intermediate lists that a programmer might have created in a stage-by-stage approach. However:

- `sorted` may have to buffer many elements in order to sort.
- `distinct` needs to keep track of values already seen.
- `toList` still needs to hold the final result in memory.
- `flatMap` may create child streams and has its own overhead.
- Parallel streams add overhead for coordination, source splitting, and result merging.

Choose the style based on **clarity, correctness, and actual performance constraints**. Do not claim Streams are always faster or always use less memory than every `for` loop; for performance requirements, benchmark on representative data and JDK.

## 14. Infinite stream sources and termination bounds

For example, `Stream.iterate(1, n -> n + 1)` has a source that is unbounded in principle. If you call `toList` without a stopping point, the pipeline may never complete and will consume resources:

```java
// DO NOT RUN: missing a stopping point for an unbounded source.
// Stream.iterate(1, n -> n + 1).toList();
```

You can add `limit`:

```java
List<Integer> values = Stream.iterate(1, n -> n + 1)
        .limit(5)
        .toList();

System.out.println(values); // [1, 2, 3, 4, 5]
```

Or use the Java 9+ overload with a predicate:

```java
List<Integer> values = Stream.iterate(
        1,
        n -> n <= 5,
        n -> n + 1
).toList();

System.out.println(values); // [1, 2, 3, 4, 5]
```

The two snippets above are **two independent alternatives** using the same variable name `values`; do not combine them in one scope without renaming. The point to remember is that a lazy pipeline can still **fail to terminate** if the terminal must traverse an unbounded source with no stopping condition.

`filter` alone does not cause an infinite source to terminate: it discards non-matching elements rather than marking a stopping point. `takeWhile` or `limit` are the appropriate operations when the stopping logic allows.

## 15. Comparing element-by-element pipelines and stage-by-stage processing

| Criterion | Sequential stateless Stream pipeline | Stage-by-stage loops with temporary lists |
| --- | --- | --- |
| Expression style | Chain of `filter`/`map`/terminal | Multiple `for` loops and intermediate lists |
| When executed | Usually coordinated element by element | One stage finishes on the whole set before moving to the next |
| When computation starts | When the terminal consumes | Immediately when the loop is called |
| Intermediate lists | Not required for each stateless operation | Explicitly created by code |
| Early termination | Supported by `findFirst`/`anyMatch`/`limit` | Must write explicit `break`/`return` logic |
| Step order | Follows the order of operations in the pipeline | Follows the order of separate loops |
| Stateful/short circuit | Needs separate analysis | Expressed directly in hand-written code |
| Concurrency | `parallel()` can distribute across threads | Loops are usually sequential unless manually parallelized |
| Side effects | Should be avoided in intermediate operations | Can be controlled explicitly, though still needs management |
| Optimization | Library/JVM may fuse and legally skip steps | Author controls structure and loops |

Streams are **not necessarily** better than loops in every case. A `for` loop may be more suitable when there is complex evolving state, when you need to break/continue with multiple logic branches, or when performing I/O that requires careful control. Streams are well suited for processing datasets that can be clearly expressed as a chain of transformations, filters, and collection.

## 16. Common mistakes

| Mistake | Problem | How to fix |
| --- | --- | --- |
| Thinking `filter` builds a list before `map` runs | Not true under the typical lazy/stateless model | Understand that the pipeline is consumed when the terminal requests it |
| Thinking a pipeline always runs step by step on the entire collection | Not the typical behavior for stateless operations | Trace the flow passing element by element |
| Thinking one element always completes every operation before the next | `sorted`/`distinct`/parallel/short-circuiting complicate this | Distinguish stateless from stateful |
| Expecting code in `map` to run immediately at declaration | Intermediate operations are usually lazy | Add an appropriate terminal operation |
| Reusing a stream after a terminal operation | A stream can only be consumed once | Create a new stream |
| Swapping `filter` and `map` arbitrarily | Can change the values seen by the predicate | Verify logical equivalence |
| Assuming `count` must invoke every `peek`/`map` | May optimize away running those operations | Do not rely on side effects in intermediate operations |
| Using `peek` for mandatory auditing | Execution count is not a guaranteed contract | Place auditing at a dedicated boundary |
| `parallel()` then adding to an external `ArrayList` | Data race, indeterminate execution order | Use a collector/`toList` or proper synchronization |
| Expecting `findAny` to return the first element | May return any element | Use `findFirst` if encounter order is needed |
| Using `sorted` on an infinite source then `toList` | May not terminate / buffer infinitely | Limit the source before sorting is needed |
| Thinking Streams always reduce memory | Stateful operations and terminals still buffer | Analyze the pipeline and benchmark performance |
| Ignoring side effects before an exception | No automatic rollback | Design transactions/idempotency/compensation |

## 17. Practice exercises

1. Given `Stream.of("a","bb","ccc").filter(s -> s.length() >= 2).map(String::toUpperCase).toList()`, trace the path through the steps for each element. What is the final result?
2. Write three `for` loops to increase prices, filter by a threshold, and create labels for `Item`. Then replace them with a Stream pipeline. Compare the number of intermediate lists.
3. In `StreamExecutionDemo`, why does the Stream trace start with `adjust:A, check:A, adjust:B` while the `for`-loop trace starts with `adjust:A, adjust:B, adjust:C`?
4. Predict `Stream.of(9,10).map(n -> n+1).filter(n -> n>=11).toList()` and the pipeline with `filter`/`map` swapped. Explain the difference.
5. Create a pipeline with `map` then `filter`, without calling a terminal yet. Write code to verify that a trace variable is still empty; then call `toList` and observe the result in a sequential flow.
6. Given `Stream.of(1,2,3,4,5).filter(n -> n%2==0).map(n -> n*10).findFirst()`. Explain why 3, 4, and 5 do not need to be processed in a sequential pipeline.
7. Use `IntStream.rangeClosed(1,100).filter(n -> n%2==0).limit(3)`. Compare it with the `limit(3).filter(...)` version.
8. Explain why `sorted` may need to collect multiple elements, whereas `map` and `filter` do not necessarily need the entire source.
9. Write `Stream.of("A","B","A").distinct().toList()`. Why does `distinct` need to remember previously seen values?
10. Given `IntStream.rangeClosed(1,5).parallel().map(n -> n*2).boxed().toList()`, determine the result order and distinguish it from the order in which threads invoke the mapper.
11. Run `List.of("A","B","C").stream().peek(System.out::println).count()` and explain why the number of log lines must not be treated as a contract.
12. Design a unit test for pipeline correctness that does **not** depend on the count or order of side effects in intermediate operations.
13. When is a direct `for` loop easier to understand than a Stream? Give an example involving an I/O resource or multiple error-handling branches.
14. For the source `Stream.iterate(1,n -> n+1)`, use `limit(5)` or a Java 9+ predicate to ensure the `toList` terminal terminates.
15. With `parallelStream` and `forEachOrdered`, explain why the order of the final action is guaranteed, yet you must not infer that all upstream operations are sequential.

## 18. Self-check checklist when reading a pipeline

- Have you identified the **source**, **intermediate operations**, and **terminal operation**?
- Before the terminal runs, do any intermediate operations actually need to compute immediately?
- Is each operation **stateless** or **stateful**? Are there `sorted`, `distinct`, `skip`, or `limit`?
- Is there a **short-circuiting** operation so the pipeline does not need all elements?
- Are you confusing "the order of operations" with "finishing one operation on the entire collection"?
- Are you relying on **side effects** of `map`, `filter`, `peek`, or thread scheduling?
- Does the source have an encounter order? Does the result need to preserve order or can it be unordered?
- Does the pipeline run **sequentially** or in **parallel**? If parallel, is shared mutable state protected?
- Is there a risk of an infinite source while the terminal demands all data?
- Have you tested data that fails the filter, empty data, early termination, and stateful operations?

**Remember:** For a sequential Stream pipeline of **stateless** operations, Java typically processes an element by passing it through successive steps as demanded by the terminal, **not** by defaulting to completing one step on the entire collection before running the next. Laziness enables operation fusion and early termination. However, `sorted`, `distinct`, `limit`, terminal optimizations, and `parallel()` create important exceptions to this simple model. Rely on the **result semantics** of the Stream API, not on the order of side effects in intermediate operations.
