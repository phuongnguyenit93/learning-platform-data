# Encounter Order and Execution Order in Java Stream

When using `Stream`, especially with `parallelStream()`, you need to distinguish **encounter order** from **execution order**. These two concepts are related but not identical: a pipeline can process multiple elements in parallel, out of their original order, and still produce an **ordered result**.

This lesson focuses on the Stream model in Java 17+: where order comes from, which operations preserve or change order, the behavior of terminal operations, and how to avoid depending on thread scheduling.

## 1. Two Types of Order to Distinguish

**Encounter order** is the logical order that the stream source or intermediate steps define for elements as they pass through the pipeline. For example, with `List.of("A", "B", "C")`, the encounter order is `A → B → C`, even when processed with a parallel stream.

**Execution order** is the actual timing and sequence in which functions such as `map`, `filter`, `peek`, or `Consumer` are called when the pipeline executes. With a parallel stream, element-processing functions may run on different threads and in a non-deterministic order.

```text
Encounter order of List:      A --------> B --------> C --------> D

A parallel execution schedule: C executes
                               A executes
                               D executes
                               B executes

Ordered toList() result:      [A, B, C, D]  (if the pipeline is still ordered)
```

The middle diagram is only **one possible execution schedule**, not a schedule guaranteed by Java. `Stream` can compute and combine results to respect encounter order without forcing each callback to execute sequentially in that order.

It is also important to distinguish:

- **Ordered stream**: a stream with a defined encounter order.
- **Unordered stream**: a stream not constrained by an encounter order; results may appear in various orders depending on the source, operations, and execution.
- **Sequential stream**: steps execute in sequential mode.
- **Parallel stream**: execution can be split across multiple threads.

`ordered/unordered` refers to **ordering semantics**; `sequential/parallel` refers to **execution mode**. Therefore, `parallel` is not synonymous with `unordered`, and `unordered` does not automatically enable parallel processing.

## 2. Which Sources Create Encounter Order?

| Source or operation | Encounter order |
| --- | --- |
| `List.stream()`, `List.parallelStream()` | Yes; follows the element order of the list |
| `Arrays.stream(array)` | Yes; follows the index order in the array |
| `LinkedHashSet.stream()` | Yes; follows the iteration order defined by `LinkedHashSet` |
| `HashSet.stream()` | Not guaranteed to have an encounter order |
| `Stream.of(a, b, c)` | Yes; follows the order of the arguments |
| `stream.sorted()` | Imposes a sorted order on the downstream stream |
| `stream.unordered()` | Removes the encounter order constraint, if any |

Do not infer a fixed order from data observed during test runs of `HashSet` or `Set.of(...)`: the implementation may yield one iteration order at the time of observation, but there is no contract guaranteeing that order.

Example:

```java
List<String> names = List.of("Bình", "An", "Chi");
List<String> result = names.parallelStream()
        .map(String::toUpperCase)
        .toList();
// result has encounter order: [BÌNH, AN, CHI]
```

This is an illustrative snippet inside a Java method, with `import java.util.List;`. Because `List` is ordered and `map` does not change encounter order, `Stream.toList()` places elements into the list in the exact encounter order, even though the `toUpperCase` callback may run in parallel.

## 3. A Java 17+ Example with Deterministic Output

Save as `StreamOrderDemo.java`:

```java
import java.util.List;

public class StreamOrderDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(4, 1, 3, 2);

        System.out.println("source = " + numbers);

        List<Integer> mapped = numbers.parallelStream()
                .map(n -> n * 10)
                .toList();
        System.out.println("mapped = " + mapped);

        List<Integer> sorted = numbers.parallelStream()
                .sorted()
                .toList();
        System.out.println("sorted = " + sorted);

        int first = numbers.parallelStream()
                .findFirst()
                .orElseThrow();
        System.out.println("first = " + first);

        numbers.parallelStream()
                .forEachOrdered(n -> System.out.println("ordered = " + n));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac StreamOrderDemo.java
java StreamOrderDemo
```

**Exact stdout:**

```text
source = [4, 1, 3, 2]
mapped = [40, 10, 30, 20]
sorted = [1, 2, 3, 4]
first = 4
ordered = 4
ordered = 1
ordered = 3
ordered = 2
```

Explanation:

1. `numbers` is a `List` with encounter order `4, 1, 3, 2`.
2. `map(n -> n * 10)` may run on elements under any parallel schedule, but `toList()` preserves encounter order, so the result is `[40, 10, 30, 20]`.
3. `sorted()` defines a **new order** of `1, 2, 3, 4`; the result is then collected in this order.
4. `findFirst()` takes the first element in encounter order, which is `4`, regardless of which element a worker finishes processing earliest.
5. `forEachOrdered()` executes the print action in encounter order, so the four `ordered = ...` lines always appear in the order shown above.

Important: ordered output **does not prove** that computation ran sequentially.

## 4. How Does `forEach()` Differ from `forEachOrdered()`?

Both terminal operations accept a `Consumer<T>` and do not return a result list, but they have different ordering contracts:

| Terminal operation | Sequential ordered stream | Parallel ordered stream |
| --- | --- | --- |
| `forEach(action)` | Under normal sequential execution, actions follow iteration order | **No guarantee** that actions run in encounter order |
| `forEachOrdered(action)` | Actions follow encounter order | **Guaranteed** that actions are executed in encounter order |
| `toList()` | Collects in encounter order | Still collects in encounter order if the stream is ordered |

The following example does not have fixed stdout:

```java
List<Integer> numbers = List.of(1, 2, 3, 4);
numbers.parallelStream().forEach(System.out::println);
```

This is an illustrative snippet inside a method and requires `import java.util.List;`. One run might print `3, 4, 2, 1`; another might print `1, 2, 3, 4`. **Do not rely on any order**. Even if it happens to print in order many times, that is still not guaranteed by `forEach` on a parallel stream.

To force the observable action to follow encounter order:

```java
numbers.parallelStream().forEachOrdered(System.out::println);
```

This statement will print `1`, `2`, `3`, `4` in order, one number per line. With `forEachOrdered`, the action for one element *happens-before* the action for the next element in encounter order, even though actions may be executed by different threads. It **does not guarantee** that every intermediate step such as `map` or `filter` is also called sequentially or in that order.

Do not confuse a collection's `Iterable.forEach` with `Stream.forEach`: `Iterable.forEach` iterates in the iterable's defined order if any; whereas `Stream.forEach` when executed in parallel does not guarantee encounter order.

### Why Not Use `forEachOrdered` Everywhere?

Guaranteeing order requires actions to be coordinated. If each action prints to the console, writes to the network, or waits on a resource, synchronization overhead can reduce the benefits of parallelism. If you need **results arranged in encounter order** without needing side effects per element, `map(...).toList()` usually expresses the intent more clearly than `forEachOrdered` appending into a shared list.

## 5. What Can Intermediate Operations Do to Order?

Some intermediate operations **preserve** the encounter order of an ordered source, while others **create** or **relax** the constraint:

| Operation | With an ordered source | Practical meaning |
| --- | --- | --- |
| `map(f)` | Preserves logical positional order | The first element becomes the first result |
| `filter(p)` | Preserves relative order of selected elements | Does not reverse the order of remaining elements |
| `flatMap(f)` | Matches source order and the order of ordered substreams | Can emit multiple elements for one input element |
| `distinct()` | For ordered streams, keeps the first occurrence of each value by `equals` | The stability constraint can be costly in parallel |
| `sorted()` | Creates a new sorted order | Often requires coordination/buffering before returning results |
| `limit(n)` | Takes the **first n elements** in encounter order | Can be costly on an ordered parallel stream |
| `skip(n)` | Skips the **first n elements** in encounter order | May require coordination to know which elements belong to the prefix |
| `unordered()` | Removes the encounter order constraint | Can open optimization opportunities, but does not mean "random shuffle" |

Example of `filter` and `limit`:

```java
List<Integer> values = List.of(7, 2, 4, 9, 6);
List<Integer> result = values.parallelStream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();
// result: [2, 4]
```

This is an illustrative snippet inside a method and requires `import java.util.List;`. Although finding `6` first in a parallel execution schedule is possible, `limit(2)` on an **ordered stream** still selects the first two even numbers in encounter order, which are `2` and `4`.

### What Does `unordered()` Mean?

`unordered()` indicates that subsequent steps may ignore the requirement to preserve encounter order. It **does not** necessarily change the physical order of data, nor does it guarantee that results will be shuffled.

```java
List<Integer> picked = List.of(1, 2, 3, 4, 5, 6)
        .parallelStream()
        .unordered()
        .limit(2)
        .toList();
```

This snippet may receive any two elements from the input set; **no specific result is fixed**. Removing the ordering constraint is often useful when you only care about count or set of values, such as finding any few matching elements.

If the problem requires "the first two elements in input order", **do not call `unordered()`** before `limit(2)`.

## 6. `findFirst()` vs. `findAny()`: Which Semantics to Prefer?

- `findFirst()`: gets the first element in encounter order, **if the stream has an encounter order**. For an unordered source, there is no predefined "first" element.
- `findAny()`: may choose any element, even when the source has an encounter order. This can allow returning a result sooner during parallel execution.

```java
List<String> values = List.of("red", "green", "blue");

String first = values.parallelStream()
        .findFirst()
        .orElseThrow(); // Guaranteed to be "red"

String any = values.parallelStream()
        .findAny()
        .orElseThrow(); // Cannot guarantee a specific value
```

This is an illustrative snippet inside a method and requires `import java.util.List;`. `findAny` **may** return `"red"`, but does not have to. Both return an `Optional` before calling `orElseThrow()`; on an empty stream, `orElseThrow()` throws `NoSuchElementException`.

To check "whether an element satisfies a condition", usually use `anyMatch(predicate)` instead of `filter(predicate).findFirst()`. `anyMatch` expresses a boolean question and does not impose a requirement to select the first element.

## 7. Callback Order Is Not the Source of Truth for Data

A common mistake is using side effects in `map` to infer processing order or build results:

```java
List<Integer> seen = new java.util.ArrayList<>();

List<Integer> result = List.of(1, 2, 3, 4)
        .parallelStream()
        .map(n -> {
            seen.add(n);  // Wrong: mutating a shared ArrayList from multiple threads.
            return n * 10;
        })
        .toList();
```

This snippet **demonstrates a bug**, not a pattern to run in an application. `ArrayList` is not synchronized for concurrent writes; `seen` may contain unexpected data or have corrupted state. Even if `seen` is replaced with a thread-safe collection, the insertion order into `seen` still reflects the execution schedule, not necessarily encounter order.

The right approach when you need an ordered result list:

```java
List<Integer> result = List.of(1, 2, 3, 4)
        .parallelStream()
        .map(n -> n * 10)
        .toList();
// [10, 20, 30, 40]
```

This is an illustrative snippet with `import java.util.List;`. `map` returns the new value; `toList()` handles combining results in logical order.

Beyond ordering, **side effects in intermediate operations should not be used to guarantee business behavior**. Streams allow optimizations where callbacks in some steps may not be invoked at all if the terminal result is still correct. For example, with a `SIZED` source and `count()`, Java can compute the element count directly without traversing `peek`. The following code must not be used to require printing three lines:

```java
long count = List.of(1, 2, 3)
        .stream()
        .peek(System.out::println)
        .count();
// count == 3, but it may not print any numbers.
```

This is an illustrative snippet inside a method and requires `import java.util.List;`. `peek` is primarily for observation/debugging, not suitable for mandatory logic such as writing to a database, sending emails, or mutating a counter.

**Recommendation:** lambdas in `map`, `filter`, and `reduce` should be *non-interfering* (not modifying the stream source being processed) and *stateless* (not depending on mutable state during execution). This keeps the pipeline correct for both sequential and parallel execution.

## 8. Ordered Results Differ from When Side Effects Occur

Consider a pipeline with `parallelStream().map(this::fetch).toList()`. If `fetch` makes HTTP calls, requests may be sent/completed out of encounter order, even though the resulting list is arranged in the input order. Therefore:

- The order of **results** does not equate to the order of **sending requests**, **writing logs**, or **writing records to the DB**.
- If side effects must happen in order, place the action at a controlled boundary (such as iterating sequentially after computing the results); use `forEachOrdered` when the goal is specifically to invoke an action in encounter order.
- If order is not required, explicitly describe the invariants to preserve (data set, count, relationships between elements) rather than accidentally coupling the system to thread scheduling.
- When an exception occurs in a parallel pipeline, some other elements may already have been processed or caused side effects. Streams do not provide rollback/transactions for those side effects.

Most collection operations like `toList()` or `collect(Collectors.toList())` on an **ordered stream** can maintain encounter order. However, `collect(Collectors.toSet())` does not promise iteration order of the resulting set; if you want an ordered interface, choose the appropriate result type and collector rather than merely observing order during test runs.

## 9. When Does Order Affect Performance?

Order is part of an operation's contract. In parallel pipelines, requiring encounter order to be preserved can force the system to coordinate work across threads, buffer results, or wait for preceding elements. Noticeable operations include `limit`, `skip`, `distinct`, `findFirst`, and `forEachOrdered`.

For example, a task that only needs **any two valid elements**, rather than "the first two elements", can consider `unordered().filter(...).limit(2)`. However, only relax ordering after confirming that business requirements accept any valid selection.

Do not assume `parallelStream()` is faster than `stream()`. For small datasets, lightweight callbacks, slow I/O, resource contention, or processing that requires strict ordering, the overhead of splitting work and coordinating can outweigh the benefits. Measure with a real workload when optimizing.

## 10. Quick Selection Table

| Goal | Appropriate idiom | Key guarantee |
| --- | --- | --- |
| Transform a list while keeping original order | `list.parallelStream().map(f).toList()` | Result follows the list's encounter order |
| Print each element in list order | `list.parallelStream().forEachOrdered(System.out::println)` | Actions execute in encounter order |
| Perform an action where order does not matter | `list.parallelStream().forEach(action)` | Do not rely on execution order |
| Get the first element in source order | `stream.findFirst()` | First in encounter order if defined |
| Get any element | `stream.findAny()` | No guarantee of the first element |
| Get the first n elements | `orderedStream.limit(n)` | Prefix in encounter order |
| Get any n elements when order is unnecessary | `stream.unordered().limit(n)` | No promise of the leading prefix |
| Sort before collecting | `stream.sorted().toList()` | Result order follows the comparator/natural order |
| Observe execution schedule for debugging | Log with thread markers, do not use as business output | Logs may arrive out of encounter order |

## 11. Common Mistakes to Avoid

1. **"Parallel means losing order"**: false. Streams can process in parallel and still preserve result order.
2. **"Ordered output means each callback also ran in order"**: false. `toList()` can restore logical order after callbacks run concurrently.
3. **"forEachOrdered makes all map operations run sequentially"**: false. It constrains action order at the terminal step, not forcing upstream steps to process one by one.
4. **"HashSet is ordered because it prints the same every time"**: there is no contract guaranteeing encounter order.
5. **"unordered() is shuffle()"**: false. It only removes the encounter order requirement; it does not promise to reverse or shuffle elements.
6. **"findAny() and findFirst() always return the same thing"**: false, especially when running in parallel.
7. **"peek() always runs once per element"**: not guaranteed across all pipelines and optimizations.
8. **"Writing to a shared List in parallel map is safe"**: false; risks race conditions and out-of-order results.
9. **"A stream that has run a terminal operation can be reused"**: a stream is a single-use pipeline; to process again, create a new stream from the source.

## Key Takeaways

- **Encounter order** is the logical order of data; **execution order** is the actual schedule in which operations run.
- **Parallel does not automatically lose encounter order**.
- `forEach` on a parallel stream does not guarantee action order; `forEachOrdered` guarantees action order according to encounter order if present.
- `toList`, `findFirst`, and `limit` respect encounter order when it exists; `unordered()` allows dropping that constraint.
- Do not build logic based on callback timing or side effects in intermediate operations. Express results using stateless, non-interfering transformations and choose the terminal operation matching the guarantees the problem requires.
