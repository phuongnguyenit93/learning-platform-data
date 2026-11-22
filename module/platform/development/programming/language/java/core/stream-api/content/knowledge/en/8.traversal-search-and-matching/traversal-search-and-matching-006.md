# Traversing Results with `forEach` and `forEachOrdered`

In the **Java Stream API**, both `forEach` and `forEachOrdered` are terminal operations (*terminal operations*) used to perform an action on the elements produced by a pipeline. The core difference is **action execution order**: `forEach` makes no commitment to preserve *encounter order*, whereas `forEachOrdered` guarantees execution in encounter order **if the Stream has a defined encounter order**.

This lesson belongs to the **Traversal, Search, and Matching** chapter of the **JAVA_STREAM_API** module. Once you know how to organize lazy pipelines with `filter`, `map`, `reduce`, and `collect`, you need to choose the right way to consume results, especially with parallel Streams. This knowledge also connects to `Spliterator`, grouping, custom collectors, Stream Gatherers, and limits around state, resources, and performance.

## 1. Syntax: Both Accept a `Consumer` and Return `void`

In `java.util.stream.Stream<T>`:

```java
void forEach(Consumer<? super T> action);
void forEachOrdered(Consumer<? super T> action);
```

`Consumer<T>` is a functional interface in `java.util.function` with the abstract method `void accept(T value)`. It describes an action that receives an element without directly returning a transformed value.

Example with an ordered source:

```java
import java.util.Arrays;
import java.util.List;

List<String> names = Arrays.asList("An", "Bình", "Chi");

names.stream()
        .map(String::toUpperCase)
        .forEachOrdered(System.out::println);
// AN
// BÌNH
// CHI
```

In the pipeline above, `map` is an intermediate operation (*intermediate operation*) declaring the transformation, while `forEachOrdered` is the terminal operation that actually triggers traversal.

> `forEach`/`forEachOrdered` are tools for **consuming elements to perform an action**. When you want to produce a list, set, map, or computed value, `collect`, `reduce`, or a more suitable terminal operation is usually the better choice.

## 2. Encounter Order Differs from Thread Completion Order

**Encounter order** is the order of elements defined by the source and pipeline. A `List` is ordered by element position; `IntStream.range(1, 6)` has ascending numeric order; a `Stream` from `HashSet` typically has no guaranteed encounter order. Transformations like `map` and `filter` on an ordered source generally preserve the encounter order of remaining elements.

```text
Source List:       [1, 2, 3, 4, 5]
       |
      filter(n -> n % 2 != 0)
       |
Ordered result:    [1, 3, 5]
       |
    terminal operation
       +-- forEach:        action order is not guaranteed
       +-- forEachOrdered: action runs for 1, then 3, then 5
```

With parallel Streams, workers can process multiple elements simultaneously. **Internal processing order** does not necessarily match encounter order. `forEachOrdered` only guarantees the **action order of the terminal operation** follows encounter order; it does not mean every upstream `map`/`filter` step ran sequentially or on the same thread.

### 2.1. Comparison Table

| Criterion | `forEach(action)` | `forEachOrdered(action)` |
|---|---|---|
| Operation kind | Terminal (*terminal*) | Terminal (*terminal*) |
| Parameter type | `Consumer<? super T>` | `Consumer<? super T>` |
| Return type | `void` | `void` |
| With Stream having encounter order | Action order not guaranteed | Guarantees action executes in encounter order |
| With Stream lacking encounter order | No encounter order to preserve | Does not invent a new business order |
| During parallel execution | Action calls may run on multiple workers in unpredictable order | Actions are ordered by encounter order; not guaranteed to run on a single thread |
| Overhead | Usually easier to exploit parallelism when actions are independent | May require waiting, coordination, and synchronization to preserve order |
| Typical usage | Sending independent events, order-insensitive processing | Exporting reports or writing output that must follow order |

**Note:** `forEach` still works on Streams that have an encounter order; the method simply **has no obligation to respect that order**. With ordinary sequential Streams, you often observe actions occurring one by one in source order, but you should not turn that observation into an assumption that holds if the source, execution mode, or pipeline optimizations change.

## 3. Observing Differences in Sequential and Parallel Execution

### 3.1. Sequential Stream

```java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 5)
        .forEach(System.out::print);
// On a typical sequential pipeline: 12345

System.out.println();

IntStream.rangeClosed(1, 5)
        .forEachOrdered(System.out::print);
// 12345 (exact encounter order)
```

Both can produce the same order in a simple example. The difference lies in the **API contract**, which becomes clearer when parallelism is enabled.

### 3.2. Parallel Stream: `forEach` Does Not Guarantee Order

```java
IntStream.rangeClosed(1, 10)
        .parallel()
        .forEach(n -> System.out.print(n + " "));
// Possible output: 7 6 9 10 8 3 5 4 2 1
// Exact order varies by runtime and per run.
```

The print action is still invoked for each element, but **the order in which elements appear is not guaranteed**. The sample output merely illustrates one possibility; never use actual printed values to deduce which worker definitely ran first.

### 3.3. Parallel Stream: `forEachOrdered` Preserves Action Order

```java
IntStream.rangeClosed(1, 10)
        .parallel()
        .forEachOrdered(n -> System.out.print(n + " "));
// 1 2 3 4 5 6 7 8 9 10
```

The `rangeClosed` source has ascending encounter order, so `forEachOrdered` maintains the order of print actions. The pipeline is still configured with `parallel()`; this is **not** a request to make all processing sequential.

### 3.4. Testing on a Pipeline with `filter` and `map`

```java
import java.util.Arrays;
import java.util.List;

List<Integer> data = Arrays.asList(8, 3, 10, 7, 2, 5);

data.parallelStream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * 10)
        .forEachOrdered(System.out::println);
// 30
// 70
// 50
```

`filter` retains odd numbers in the `List`'s encounter order (3, 7, 5), and `map` transforms them into 30, 70, 50. `forEachOrdered` guarantees printing these results in that exact order.

## 4. Complete Example: Writing Order IDs in Priority Order

Suppose we need to filter paid orders and output their IDs **by ascending creation date, then ascending ID**. Because this is a business ordering requirement, we must establish the order with `sorted` before consuming. `forEachOrdered` only **preserves** existing encounter order; it does not sort by date or ID fields itself.

Standalone Java 8 example:

```java
import java.time.LocalDate;
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.stream.Collectors;

public class OrderTraversalDemo {
    static final class Order {
        private final String id;
        private final LocalDate createdOn;
        private final boolean paid;

        Order(String id, LocalDate createdOn, boolean paid) {
            this.id = id;
            this.createdOn = createdOn;
            this.paid = paid;
        }

        String getId() {
            return id;
        }

        LocalDate getCreatedOn() {
            return createdOn;
        }

        boolean isPaid() {
            return paid;
        }
    }

    public static void main(String[] args) {
        List<Order> orders = Arrays.asList(
                new Order("DH-03", LocalDate.of(2026, 11, 18), true),
                new Order("DH-02", LocalDate.of(2026, 11, 17), false),
                new Order("DH-04", LocalDate.of(2026, 11, 18), true),
                new Order("DH-01", LocalDate.of(2026, 11, 16), true)
        );

        Comparator<Order> byDateThenId =
                Comparator.comparing(Order::getCreatedOn)
                        .thenComparing(Order::getId);

        System.out.println("Paid orders in order:");

        orders.parallelStream()
                .filter(Order::isPaid)
                .sorted(byDateThenId)
                .map(Order::getId)
                .forEachOrdered(System.out::println);
        // DH-01
        // DH-03
        // DH-04

        // If business logic needs to return data instead of printing,
        // collect produces the result so the caller decides how to display it.
        List<String> orderedIds = orders.parallelStream()
                .filter(Order::isPaid)
                .sorted(byDateThenId)
                .map(Order::getId)
                .collect(Collectors.toList());

        System.out.println(orderedIds);
        // [DH-01, DH-03, DH-04]
    }
}
```

The pipeline has two clear responsibilities: `sorted(byDateThenId)` establishes the business order; `forEachOrdered` maintains that order during output. If replaced with `forEach` on the parallel pipeline, printed IDs **can become out of order** even though `sorted` was called upstream.

If you only want to return a sorted list of IDs for another layer to use, `collect(Collectors.toList())` is usually better than printing or appending elements to an external mutable list.

## 5. Does `forEachOrdered` Guarantee Running on One Thread?

**No.** For a parallel Stream, the JDK does not promise that all `forEachOrdered` action invocations run on the same thread. What is guaranteed is that for elements in encounter order, **executing the action for one element happens-before executing the action for the next element**. The *happens-before* relationship ensures memory-effect visibility and ordering between those actions.

```java
import java.util.stream.IntStream;

IntStream.rangeClosed(1, 5)
        .parallel()
        .forEachOrdered(n -> System.out.println(
                n + " : " + Thread.currentThread().getName()));
```

Numbers 1 through 5 will appear in encounter order, while thread names may vary. Never assert on a fixed thread name to verify correctness.

Conversely, `forEach` explicitly specifies that the action for an element may run on whichever thread the library chooses; if **synchronization** is needed when accessing shared state, the programmer is responsible for it. Having elements belong to the same Stream creates no automatic rule protecting mutable variables modified by actions.

### 5.1. The `happens-before` Guarantee Applies Only Within Its Defined Scope

`forEachOrdered` guarantees the ordering of **`Consumer` actions** on an ordered Stream; do not overgeneralize this into a promise that every function in every intermediate step runs sequentially in exact encounter order. For example, an expensive `map` computation can still run on another worker, while the final action invocation waits to preserve observable order.

This explains why a pipeline can perform intermediate computations in parallel while still outputting results in exact order.

## 6. Side Effects and Shared State: Common Mistakes with `forEach`

`forEach` is intended for actions with external effects such as logging, sending notifications, or updating another system. However, mutating **the same non-thread-safe mutable structure** from parallel actions is dangerous.

### 6.1. Wrong: Mutating an `ArrayList` from Multiple Workers

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> unsafe = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(unsafe::add); // WRONG: ArrayList is not thread-safe.

// You cannot rely on unsafe.size() or the resulting contents.
```

This example has a data race. The list may lose elements, hold corrupted contents, or throw errors during internal updates.

**Right: let a collector coordinate building the result**

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> safe = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .collect(Collectors.toList());

System.out.println(safe.size()); // 10000
System.out.println(safe.get(0));  // 0
```

With an ordered `IntStream.range` source, `Collectors.toList()` preserves encounter order in the result list. The code needs no external `ArrayList` shared across actions.

### 6.2. Synchronized Collections Prevent Races, Not Business Ordering Issues

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> synchronizedList =
        Collections.synchronizedList(new ArrayList<>());

IntStream.rangeClosed(1, 100)
        .parallel()
        .forEach(synchronizedList::add);
```

`add` operations are synchronized, preventing races during list modification. However, **the insertion order of elements can still differ from 1, 2, ..., 100** because `forEach` does not preserve order. When you simply want a result list following source order, `collect` states intent clearly and is usually more appropriate.

### 6.3. Counting or Aggregating: Use the Proper Terminal Operation

```java
// Avoid manually incrementing a shared variable inside parallel stream forEach:
// long[] total = {0};
// numbers.parallelStream().forEach(n -> total[0] += n);

long total = java.util.stream.LongStream.rangeClosed(1, 1000)
        .parallel()
        .sum(); // 500500

long count = java.util.stream.LongStream.rangeClosed(1, 1000)
        .filter(n -> n % 2 == 0)
        .count(); // 500
```

When the task is summing, counting, finding extrema, grouping, or building a Map or List, the Java Stream API has terminal operations and collectors designed to handle it directly without needing external mutable result variables.

### 6.4. Be Careful with Irreversible Actions

If `forEach` sends emails, records transactions, or calls external APIs, a failure on one element does not automatically roll back actions already executed for other elements. In parallel mode, actions can happen concurrently and in an indeterminate order. Even `forEachOrdered` provides no atomicity, retry, or transaction semantics.

For systems requiring transactions, error handling, retries, or rate limiting, design them at the proper business layer; do not rely on traversal order as a transactional guarantee.

## 7. `forEachOrdered` on Unordered Sources

Not every source has an encounter order. For example, `HashSet` does not guarantee iteration order:

```java
import java.util.Arrays;
import java.util.HashSet;
import java.util.Set;

Set<String> labels = new HashSet<>(
        Arrays.asList("C", "A", "B"));

labels.parallelStream()
        .forEachOrdered(System.out::println);
// No guarantee it will print A, B, C or follow insertion order.
```

`forEachOrdered` **does not sort** data and does not invent an encounter order rule that the source lacks.

If alphabetical order is needed, establish it yourself:

```java
labels.parallelStream()
        .sorted()
        .forEachOrdered(System.out::println);
// A
// B
// C
```

Additionally, `BaseStream.unordered()` can remove a Stream's encounter-order constraint to allow more optimization freedom when business logic does not require order. Once `unordered()` has been called, do not use `forEachOrdered` expecting it to restore the original order automatically.

**Distinguish two kinds of ordering:**

- **Business data order**: determined by `sorted(comparator)` or the nature of the source.
- **Observed action order**: determined by whether the terminal operation must respect encounter order.

To export a sorted report on a parallel stream, these two steps usually need to appear together: `sorted(...)` followed by `forEachOrdered(...)`.

## 8. Laziness, Single Consumption, and Relationship to Matching

`filter`, `map`, or `sorted` are declared before `forEach`/`forEachOrdered` but generally do not execute until the terminal operation begins traversing:

```java
import java.util.stream.Stream;

Stream<String> pipeline = Stream.of("Java", "Stream")
        .map(String::toUpperCase);

// map has not yet been consumed to produce output externally.
pipeline.forEachOrdered(System.out::println); // JAVA, STREAM

// pipeline.forEach(System.out::println);
// WRONG: Stream has already been consumed and cannot be reused.
```

Each normal pipeline can only be **consumed once**. If two kinds of output are needed, create a fresh Stream from the source or use a collector to return data for downstream processing.

### 8.1. `forEach` Is Not a Short-Circuiting Search Operation

`forEach` and `forEachOrdered` are meant for traversal, usually acting on every element reaching the terminal operation. If the goal is merely finding one record or checking whether any element matches a condition, use terminal operations with more accurate semantics:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

List<String> names = Arrays.asList("An", "Bình", "Chi");

boolean hasLongName = names.stream()
        .anyMatch(name -> name.length() >= 4); // true

Optional<String> firstLongName = names.stream()
        .filter(name -> name.length() >= 4)
        .findFirst(); // Optional[Bình]
```

`anyMatch` can finish as soon as it finds one matching element; `findFirst` returns the first element in encounter order if present; `findAny` can choose any element, especially useful when order does not matter in a parallel pipeline.

Do not traverse with `forEach` and use an external mutable variable to “stop when found”: this API has no loop-style `break` mechanism, and it creates hard-to-control shared state. For early-stopping needs, use `anyMatch`, `allMatch`, `noneMatch`, `findFirst`, `findAny`, or appropriate limiting operators.

### 8.2. `limit` Before `forEachOrdered`

`limit(n)` is an intermediate operation capping the number of elements passed down to the terminal operation:

```java
java.util.stream.IntStream.rangeClosed(1, 10)
        .parallel()
        .limit(4)
        .forEachOrdered(System.out::println);
// 1
// 2
// 3
// 4
```

With an ordered source, `limit(4)` picks **the first four elements in encounter order**. `forEachOrdered` then outputs them in that exact order. On an ordered parallel stream, maintaining the constraints of both `limit` and `forEachOrdered` can increase overhead compared to order-insensitive processing.

## 9. Performance: Which Approach Should You Choose?

`forEachOrdered` can reduce the benefit of a parallel stream because actions must be coordinated in order. However, you cannot conclude it is always slower: performance also depends on the source, `Spliterator`, cost of each `filter`/`map` step, data size, CPU core count, I/O, and system load. Measure on realistic data when performance is an important requirement.

| Need | Suggestion |
|---|---|
| Print or process a few elements sequentially | `stream().forEachOrdered(...)` if order must be explicit |
| Traverse independent actions, order irrelevant | `forEach(...)` |
| Output data in encounter order despite parallel intermediate work | `parallelStream().forEachOrdered(...)` |
| Produce a result List to return | `collect(Collectors.toList())` |
| Sum, count, find min/max | `sum`, `count`, `min`, `max`, `reduce` |
| Group, build a Map | `collect(groupingBy(...))`, `collect(toMap(...))` |
| Only need to know if an element matches a condition | `anyMatch(...)` |
| Need the first element in order | `findFirst()` |
| Only need any matching element | `findAny()` |

**Why not use `parallelStream().forEachOrdered(...)` for every problem?** If the source has only a few elements or actions are fast, work-splitting and order-preservation overhead can outweigh parallel computation gains. With sequential outputs like a single log stream or console screen, end-of-pipeline speedup is often bounded by the sink's write speed.

## 10. Common Misconceptions

| Claim | Accurate Understanding |
|---|---|
| “Once `sorted` is called, `forEach` is guaranteed to print in order.” | `sorted` establishes encounter order; `forEach` does not guarantee action order on parallel Streams. |
| “`forEachOrdered` always sorts in ascending order.” | It only preserves existing encounter order; for ascending order, use an ordered source or `sorted`. |
| “`forEachOrdered` runs on exactly one thread.” | Not guaranteed; actions are guaranteed happens-before in element order, and may use different threads. |
| “`forEach` on a parallel stream only changes order, with no other risks.” | Side effects mutating shared state can cause data races; the library does not automatically protect mutable external objects. |
| “Using a synchronizedList with `forEach` preserves order.” | Synchronizes element additions, but does not force `forEach` to follow encounter order. |
| “`forEach` can return a List.” | Both methods return `void`; for data output, use a collector or appropriate terminal operation. |
| “A Stream can call `forEach` and then `forEachOrdered`.” | The Stream is already consumed; you must create a new pipeline. |
| “Use `forEach` to search and stop as soon as a match is found.” | Use `findFirst`, `findAny`, or `anyMatch` for short-circuiting search purposes. |

## 11. Practice Exercises

### Exercise 1. Evaluating Parallel Output

```java
java.util.stream.IntStream.range(1, 6)
        .parallel()
        .forEachOrdered(System.out::print);
```

**Answer:** Prints `12345` because `range(1, 6)` emits 1 through 5 in encounter order and `forEachOrdered` guarantees that action order.

### Exercise 2. Is Replacing `forEach` with `forEachOrdered` Enough?

The source is a `HashSet<String>` containing `"B"`, `"A"`, `"C"`. The requirement is to always print `A`, `B`, `C`. Is simply replacing `forEach` with `forEachOrdered` enough?

**Answer:** Not yet. `HashSet` has no stable encounter order matching alphabetical requirements. Call `sorted()` and then `forEachOrdered(System.out::println)`.

### Exercise 3. Collecting Data Safely in Parallel

```java
List<Integer> result = new java.util.ArrayList<>();

java.util.stream.IntStream.range(0, 1000)
        .parallel()
        .forEach(result::add);
```

**Question:** Why should the snippet above not be used, and what should replace it?

**Answer:** `ArrayList` is not thread-safe; concurrent workers writing to it cause data races. Use:

```java
List<Integer> result = java.util.stream.IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .collect(java.util.stream.Collectors.toList());
```

### Exercise 4. Traverse or Search?

Suppose you need to check whether an order list has at least one unpaid order. Should you use `forEach` to update a boolean variable or `anyMatch`?

**Answer:** Use `orders.stream().anyMatch(order -> !order.isPaid())`. It directly expresses an existence check and can stop early.

### Exercise 5. Choosing Business Ordering

A product list has `getPrice()`. The requirement is to print product names by ascending price, and alphabetically by name if prices are equal.

```java
products.stream()
        .sorted(java.util.Comparator
                .comparingInt(Product::getPrice)
                .thenComparing(Product::getName))
        .map(Product::getName)
        .forEachOrdered(System.out::println);
```

This illustration assumes a `Product` type exists with `getPrice()` returning `int` and `getName()` returning a non-null `String`. `sorted` establishes the order; `forEachOrdered` uses that order to output names.

## 12. Key Principles to Remember

When **traversing to produce side effects**, use `forEach` if actions are independent and order does not matter; use `forEachOrdered` when encounter order must be respected. If the business order does not yet exist, establish it via an ordered source or `sorted`. When results must be retained as data, prefer `collect` and dedicated terminal operations. In parallel Streams, avoid shared mutable state and recognize that **action order**, **execution order of intermediate steps**, and **the thread used** are distinct concepts.
