# `forEach()` and `forEachOrdered()` — Java Stream Terminal Operations

## 1. Nature: consuming elements to perform an action

`Stream.forEach(...)` and `Stream.forEachOrdered(...)` are both **terminal operations** of the Stream API. They accept a `Consumer<? super T>`, which is an action that takes an element of type `T` and **returns no value**:

```java
void forEach(Consumer<? super T> action);
void forEachOrdered(Consumer<? super T> action);
```

These two signatures are a simplified presentation. After calling a terminal operation, the stream has been consumed and should not be reused. They are typically suitable when you need to perform **intentional side effects** such as printing results, logging, or passing each element to an external API.

The most important distinction is **action ordering**:

- **`forEach`:** makes no commitment to execute the action in *encounter order*. Especially in a parallel stream, the action may run on different threads and in an unpredictable order.
- **`forEachOrdered`:** if the stream has an *encounter order*, the action must be executed in that order, even when the stream is marked `parallel()`. For a given element, executing the action has a *happens-before* relationship with the action of the next element in this order.

**Do not misunderstand:** `forEachOrdered` preserves the order of *actions*, which does not mean all intermediate operations such as `map` and `filter` are forced to run sequentially on a single thread. Forcing output actions to be ordered can reduce parallel efficiency.

## 2. What is encounter order?

**Encounter order** is the order of elements defined by the Stream source, or the order established by operations such as `sorted`.

Example:

```java
List<String> names = List.of("Lan", "Minh", "An");
names.stream().forEachOrdered(System.out::println);
```

Output:

```text
Lan
Minh
An
```

`List` has a clear iteration order, so a stream created from a `List` has the encounter order `Lan → Minh → An`. Conversely, sources like `HashSet` **do not guarantee element order in a way an application should rely on**; calling `forEachOrdered` does not create a new business order when the source has no encounter order to begin with.

Some notable sources/operations to remember:

| Source or operation | Encounter order |
| --- | --- |
| `List.stream()` | Follows the iteration order of `List` |
| `Arrays.stream(array)` | Follows index order |
| `IntStream.range(1, 5)` | `1, 2, 3, 4` |
| `Stream.of("A","B","C")` | `A, B, C` |
| `HashSet.stream()` | No guaranteed order |
| `LinkedHashSet.stream()` | Follows the iteration order maintained by the collection |
| `stream.sorted()` | Establishes order by comparator or natural order |
| `stream.unordered()` | Allows the pipeline to drop the encounter order constraint |

`forEachOrdered` preserves encounter order **when it exists**. If you need to print results in a business-defined order such as ascending order ID, establish the order using `sorted(...)` before `forEachOrdered(...)`.

## 3. `forEach`: each element is a `Consumer` call

Example:

```java
List<Integer> numbers = List.of(1, 2, 3);

numbers.stream().forEach(n -> System.out.println(n));
```

With this sequential stream from a `List`, the actual result following iteration order is:

```text
1
2
3
```

However, **the contract of `forEach` does not promise encounter order**. When switching to a parallel stream:

```java
numbers.parallelStream().forEach(System.out::println);
```

You **must not assume** you will see `1`, `2`, `3` in that exact order. Different runs or different environments may print in various orders. Because there is no single guaranteed stdout, do not use this parallel `forEach` example to write tests comparing a fixed printed string.

### Is `forEach` a transformation operation?

No. `forEach` is a terminal operation returning `void`. It does not produce a new `Stream<R>` and is not used to return a transformed list:

```java
// Wrong purpose if you need to get a List<String>:
numbers.stream().forEach(n -> "N=" + n); // Invalid: the expression is not a statement expression.
```

The snippet above is a **compile-time error example** and does not belong to a runnable program. To get a new list, use `map` and `toList`:

```java
List<String> labels = numbers.stream()
        .map(n -> "N=" + n)
        .toList();

System.out.println(labels); // [N=1, N=2, N=3]
```

If the goal is to **print** the labels, terminal `forEach` makes sense:

```java
numbers.stream()
        .map(n -> "N=" + n)
        .forEach(System.out::println);
```

The choice does not lie in whether the lambda is written short or long, but in whether you want **output data** or want to **perform an action**.

## 4. `forEachOrdered`: actions in encounter order

With ordered data:

```java
List<String> codes = List.of("C", "A", "B");

codes.parallelStream()
        .forEachOrdered(System.out::println);
```

The guaranteed output regarding action order is:

```text
C
A
B
```

`forEachOrdered` follows the initial encounter order of the list; it **does not automatically sort** alphabetically. To get A, B, C:

```java
codes.parallelStream()
        .sorted()
        .forEachOrdered(System.out::println);
```

Output:

```text
A
B
C
```

Here, `sorted` establishes the new order, and `forEachOrdered` requires the actions to occur in that order.

### Action order is not the order of all intermediate steps

```java
codes.parallelStream()
        .map(value -> value.toLowerCase(java.util.Locale.ROOT))
        .forEachOrdered(System.out::println);
```

The output is:

```text
c
a
b
```

What is guaranteed at the end is **the invocation order of the `forEachOrdered` action**. Do not infer that the `map` calls ran sequentially for C, A, B on the same thread. In parallel processing, intermediate operations may execute on different threads.

If `map` has side effects such as logging or updating a shared variable, do not use `forEachOrdered` to legitimize those side effects. A safer design rule is to keep mappers from interfering with shared state.

## 5. Complete Java 17 program

This example uses a list of orders with a clear encounter order. The program deliberately **does not print the non-deterministic execution order** of parallel `forEach`; instead, it collects data in parallel through a thread-safe collection and then sorts it in a separate step for deterministic stdout.

Create the file **`ForEachOrderingDemo.java`**:

```java
import java.util.Comparator;
import java.util.List;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.LongAdder;
import java.util.stream.IntStream;

public class ForEachOrderingDemo {
    record Order(String id, int amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A03", 100),
                new Order("A01", 300),
                new Order("A02", 200)
        );

        System.out.println("Sequential forEach:");
        orders.stream()
                .forEach(order ->
                        System.out.println(order.id()
                                + "=" + order.amount()));

        System.out.println("Parallel forEachOrdered:");
        orders.parallelStream()
                .forEachOrdered(order ->
                        System.out.println(order.id()));

        System.out.println("Sorted and ordered:");
        orders.parallelStream()
                .sorted(Comparator.comparing(Order::id))
                .forEachOrdered(order ->
                        System.out.println(order.id()));

        // Parallel forEach does not guarantee order, so do not print
        // queue order; only check the set of elements after completion.
        ConcurrentLinkedQueue<String> received =
                new ConcurrentLinkedQueue<>();
        orders.parallelStream()
                .forEach(order -> received.add(order.id()));

        System.out.println("Parallel forEach count: "
                + received.size());
        System.out.println("Parallel values sorted: "
                + received.stream().sorted().toList());

        // LongAdder handles concurrent additions safely.
        LongAdder accumulator = new LongAdder();
        orders.parallelStream()
                .forEach(order -> accumulator.add(order.amount()));
        System.out.println("Parallel LongAdder total: "
                + accumulator.sum());

        // When only the total amount is needed, reduction expresses intent more clearly.
        int total = orders.parallelStream()
                .mapToInt(Order::amount)
                .sum();
        System.out.println("Reduction total: " + total);

        // map + toList creates a result list in encounter order.
        List<String> ids = orders.parallelStream()
                .map(Order::id)
                .toList();
        System.out.println("Mapped ids: " + ids);

        System.out.println("Range ordered:");
        IntStream.rangeClosed(1, 4)
                .parallel()
                .forEachOrdered(n ->
                        System.out.print(n == 1 ? "1" : " " + n));
        System.out.println();
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac --release 17 ForEachOrderingDemo.java
java ForEachOrderingDemo
```

**Deterministic stdout in the example:**

```text
Sequential forEach:
A03=100
A01=300
A02=200
Parallel forEachOrdered:
A03
A01
A02
Sorted and ordered:
A01
A02
A03
Parallel forEach count: 3
Parallel values sorted: [A01, A02, A03]
Parallel LongAdder total: 600
Reduction total: 600
Mapped ids: [A03, A01, A02]
Range ordered:
1 2 3 4
```

### Why is the result like this?

1. `orders.stream()` is a sequential stream whose iteration order follows the list A03, A01, A02. The sample program prints in that sequential order.
2. `orders.parallelStream().forEachOrdered(...)` **preserves the encounter order A03, A01, A02**, even though the pipeline is parallel.
3. `sorted(Comparator.comparing(Order::id))` creates the order ID sequence A01, A02, A03; `forEachOrdered` ensures the print action follows that order.
4. `ConcurrentLinkedQueue` is safe when multiple threads call `add`. The actual order in which threads add elements to the queue **is not printed or assumed**. After `forEach` finishes, the queue contains all three IDs. Calling `sorted().toList()` on the queue yields a deterministically ordered list of IDs.
5. `LongAdder` is suitable for summing from multiple threads in the example, so the total amount is `100+300+200 = 600`. However, this usage has a **side effect**; `mapToInt(...).sum()` usually expresses the aggregation task more clearly and avoids manually managing a shared accumulator.
6. `Stream.toList()` preserves encounter order if the stream is ordered, even though the pipeline may compute in parallel. Therefore `Mapped ids` is still `[A03, A01, A02]`.
7. `IntStream.rangeClosed(1, 4)` has the natural numeric order 1, 2, 3, 4; `forEachOrdered` prints it on one line with spaces between the numbers.

**Note:** Printing with `System.out.print` inside `forEachOrdered` is suitable for demonstrating order. In a multi-request application, other outputs may also write to `System.out` at the same time; controlling interleaving between independent parts requires an appropriate logging/output mechanism.

## 6. Quick comparison table

| Criterion | `forEach(action)` | `forEachOrdered(action)` |
| --- | --- | --- |
| Stream operation type | Terminal | Terminal |
| Return type | `void` | `void` |
| Accepts | `Consumer<? super T>` | `Consumer<? super T>` |
| Guarantees encounter order | **No** | **Yes, if the stream has an encounter order** |
| On a sequential stream from `List` | Typically observed in iteration order | Guaranteed in action order |
| On a parallel stream | Actions may occur in any order | Actions follow encounter order |
| Execution thread | Not fixed by the parallel `forEach` contract | Does not force all actions onto the same thread |
| Happens-before between consecutive actions | No equivalent guarantee to `forEachOrdered` | Yes, following the specified action order |
| Potential cost | Can be favorable for parallelism | May require order coordination/synchronization |
| Suitable when | Action order is not needed | Action order is required |

Neither method automatically turns a stream into a collection, and neither guarantees that side effects can be rolled back. If the goal is to build a result, you should usually use a terminal reduction or collector instead of `forEach`/`forEachOrdered` with an external mutable list.

## 7. Sources without encounter order: `forEachOrdered` cannot guess the order you want

Example:

```java
java.util.Set<String> set =
        new java.util.HashSet<>(List.of("A", "B", "C"));

set.parallelStream().forEachOrdered(System.out::println);
```

`HashSet` does not provide an iteration order in the sense of an API guarantee for business logic. Therefore, you must not claim the output will always be A, B, C, or the order in which elements were added to the Set. `forEachOrdered` only constrains actions to encounter order **if one exists**.

If you need an explicit order, establish it:

```java
set.stream()
        .sorted()
        .forEachOrdered(System.out::println);
```

Now the output follows natural order:

```text
A
B
C
```

If the goal is to **preserve insertion order**, a structure like `LinkedHashSet` is more appropriate than `HashSet`. If the goal is ordering by amount/order ID, use an explicit comparator instead of relying on the "default order" of an unconstrained collection.

### What does `unordered()` change?

`stream.unordered()` is an intermediate operation that can **drop the encounter order constraint**. It does not force elements to be shuffled, but allows optimizations that may not preserve order. After `unordered()`, you should not expect `forEachOrdered` to reconstruct the old order:

```java
List<Integer> numbers = List.of(1, 2, 3, 4);

// Do not use the printed order here as a business contract.
numbers.parallelStream()
        .unordered()
        .forEachOrdered(System.out::println);
```

If deterministic order is needed, do not accidentally call `unordered()` in the pipeline, or actively re-establish order with `sorted` when it satisfies business requirements.

## 8. What happens to `map`, `filter`, `sorted` before the terminal operation?

`forEachOrdered` guarantees the order of **action execution**, not that all preceding operations execute in order at the same point in time.

```java
List<Integer> values = List.of(5, 2, 4, 1, 3);

values.parallelStream()
        .filter(n -> n % 2 == 1)
        .sorted()
        .forEachOrdered(System.out::println);
```

Output:

```text
1
3
5
```

`filter` selects the odd numbers 5, 1, 3; `sorted` arranges 1, 3, 5; `forEachOrdered` prints 1, 3, 5. You must not infer the order of **threads running the predicate** or **the order of comparator invocations** solely from the output order.

### `peek` is not a tool for guaranteeing side effects

`peek` is an intermediate operation, commonly used for debugging. It does not commit to executing an action for **every** element regardless of downstream operations. In pipelines with short-circuiting, optimizations, or special sources, the number of times `peek` is called may be counterintuitive.

```java
List<Integer> firstTwo = List.of(1, 2, 3, 4)
        .stream()
        .peek(n -> System.out.println("seen " + n))
        .limit(2)
        .toList();
```

This is only a way to observe during debugging; you should not place database writes or mandatory auditing inside `peek`. If the goal is to perform an action for all elements actually traversed, use an appropriate terminal operation; if the goal is new data, use `map`/`collect`. In particular, `forEachOrdered` at the end does not guarantee that `peek` is called sequentially in encounter order in a parallel pipeline.

## 9. Risks of using `forEach` to manually collect results

A classic counterexample:

```java
List<String> output = new java.util.ArrayList<>();

// NOT SAFE when running in parallel.
List.of("A", "B", "C")
        .parallelStream()
        .forEach(output::add);
```

`ArrayList` is not thread-safe. Multiple workers can call `add` concurrently, causing races, missing elements, indeterminate order, or invalid internal state. **Using a lambda/method reference does not automatically create concurrency safety.**

Another misguided fix is changing `forEach` to `forEachOrdered` and assuming everything becomes the "best result-collection solution":

```java
List<String> output = new java.util.ArrayList<>();

List.of("A", "B", "C")
        .parallelStream()
        .forEachOrdered(output::add);
```

With an ordered source, this executes the action in order and has a happens-before constraint, yet it still uses side effects and an external collection to do work for which the Stream API already has an appropriate terminal operation. **Do not use it in place of a collector just because stdout looks right.**

A clearer approach:

```java
List<String> output = List.of("A", "B", "C")
        .parallelStream()
        .map(String::toLowerCase)
        .toList();

System.out.println(output); // [a, b, c]
```

`toList()` returns results in encounter order when the source is ordered and does not allow modifying the list via `add`/`remove`. If a mutable list is needed, you can create `new ArrayList<>(output)` after the pipeline completes.

### Why is `LongAdder` still used in the example?

`LongAdder` is a tool designed specifically for concurrent additions. It serves as a safer illustration than `int[] total = {0}` or `AtomicInteger` when multiple workers add values. However, if you only need the total amount of a stream, `mapToInt(Order::amount).sum()` is usually shorter, more functional, and fits the library-optimized reduction.

**Principle:** concurrency safety is not enough to conclude a design is good; you must also consider intent, testability, reusability, and whether side effects are necessary.

## 10. `forEachOrdered` and happens-before: exact scope

The Javadoc of `forEachOrdered` states that performing the action for one element **happens-before** performing the action for the subsequent element in encounter order. This helps ensure that the actions of a single terminal call are observed in the desired order.

However:

- It **does not make the entire pipeline sequential**. Upstream steps can compute across multiple threads.
- It **does not automatically synchronize independent side effects** outside the pipeline with all other tasks in the application.
- It **is not a transaction manager**: if the third action throws an exception, the first two actions may already have made changes and will not automatically roll back.
- It **does not create an encounter order** for an inherently unordered source.
- It **does not guarantee performance** equivalent to `forEach`; maintaining order may require coordination and waiting.

When you truly must record a sequence of events in order, you can choose `forEachOrdered`, or collect into a sorted list and coordinate writing in a dedicated layer. For critical I/O, you should clearly define error handling, idempotency, retries, and before/after write mechanisms.

## 11. Exceptions in the action

`Consumer.accept` does not declare checked exceptions. Therefore, neither terminal operation handles checked exceptions for you automatically. A lambda that needs to call I/O declaring `throws IOException` must catch the error or use a designed adapter.

Unchecked exception example:

```java
List<String> values = List.of("A", "STOP", "B");

try {
    values.stream().forEachOrdered(value -> {
        if (value.equals("STOP")) {
            throw new IllegalStateException("cannot continue");
        }
        System.out.println("Processed: " + value);
    });
} catch (IllegalStateException ex) {
    System.out.println("Caught: " + ex.getMessage());
}
```

Output of this sequential example:

```text
Processed: A
Caught: cannot continue
```

When the action encounters `STOP`, it throws an error; `B` is not printed. Side effects that already occurred before the error, such as printing `Processed: A`, are not automatically rolled back. In a **parallel pipeline**, when an error occurs, actions that have already run on other workers may leave side effects behind; do not write logic requiring "no action occurs after an error on another element" without a stronger coordination mechanism.

If you need to **handle errors per element and continue**, you can catch the error inside the action and record the failed result, but you must ensure that approach fits the business logic (especially for financial postings, payments, or non-rollbackable operations).

## 12. When should you choose which method?

### Choose `forEach` when order is not required

Example of updating a thread-safe statistic across multiple records:

```java
java.util.concurrent.atomic.LongAdder counter =
        new java.util.concurrent.atomic.LongAdder();

List.of("A", "B", "C").parallelStream()
        .forEach(value -> counter.increment());

System.out.println(counter.sum()); // 3
```

However, if you simply need the **element count**, `stream().count()` is more direct. The `counter` example mainly illustrates that thread safety of the action and ignoring order are two independent design choices.

### Choose `forEachOrdered` when action order is mandatory

Example of printing report results by sorted order ID:

```java
orders.parallelStream()
        .sorted(java.util.Comparator.comparing(Order::id))
        .forEachOrdered(order ->
                System.out.println(order.id()));
```

This snippet uses `orders`/`Order` as in the complete program. If the requirement is only sorted data to return from an API, `sorted(...).toList()` may be more suitable than printing directly.

### Choose neither when you need to compute a result

| Goal | Usually more suitable API |
| --- | --- |
| Transform elements | `map`, `flatMap` |
| Get a list | `toList`, `collect(Collectors.toList())` |
| Compute a sum | `mapToInt(...).sum()`, `reduce` |
| Count elements | `count()` |
| Check if a matching element exists | `anyMatch` |
| Get the first element in encounter order | `findFirst` |
| Group elements by key | `collect(Collectors.groupingBy(...))` |

Distinguish between a **terminal operation with side effects** and a **terminal operation that produces a result**. Just because Stream supports `forEach` does not mean every problem should use it.

## 13. Comparing `forEach`, `forEachOrdered`, and `Iterable.forEach`

A common confusion is treating all `forEach` calls as the same API.

```java
List<String> names = List.of("Lan", "Minh", "An");

names.forEach(System.out::println);          // Iterable.forEach
names.stream().forEach(System.out::println); // Stream.forEach
names.stream().forEachOrdered(System.out::println);
```

`Iterable.forEach` is a default method on `Iterable` and uses the iterable's iteration order if that order is specified. `Stream.forEach` has its own contract that does not guarantee the encounter order of the terminal action, especially in a parallel pipeline. `Stream.forEachOrdered` is the explicit choice when encounter order needs to be preserved.

`Collection.parallelStream()` creates a parallel stream from the collection; **it does not make the `collection.forEach(...)` method on the collection itself parallel**. Do not infer the execution environment solely from the word `forEach` without knowing whether the receiver of the call is an `Iterable` or a `Stream`.

## 14. Frequently asked questions

**1. "Does a sequential stream with `forEach` always print in order?"** In the sequential example from a `List`, the action occurs while iterating in element order. However, the contract of `Stream.forEach` does not make the same encounter-order promise as `forEachOrdered`, so code that requires order as an invariant should use `forEachOrdered` or collect ordered output.

**2. "Does `forEachOrdered` turn a parallel stream into a sequential stream?"** No. It forces the final action to respect encounter order, but other parts of the pipeline can still execute in parallel.

**3. "If I use a `HashSet`, will `forEachOrdered` print in insertion order?"** No. `HashSet` does not guarantee insertion order; if insertion order is needed, use a structure designed to preserve it, or explicitly call `sorted`.

**4. "Does `forEachOrdered` sort automatically?"** No. It follows the existing encounter order. Sorting is the job of `sorted` or a source that already has the desired order.

**5. "Does `forEach` return the stream so `map` can be called next?"** No. It is a terminal operation that returns `void` and consumes the stream.

**6. "Does a single thread in parallel `forEachOrdered` handle all actions?"** There is no such guarantee. Actions are executed in encounter order, but not necessarily on the same thread.

**7. "Does `forEachOrdered` make `ArrayList.add` safe for all parallel workloads?"** You must not infer that for independent concurrent updates. Executing the terminal action in order is a property of that call; it does not protect the collection from other threads or external tasks accessing it simultaneously. If a result collection is needed, prefer `toList`/`collect`.

**8. "Can I rely on the log order in `map` when `forEachOrdered` is at the end of the chain?"** No. The order of the `forEachOrdered` action does not impose an execution order on intermediate mappers.

**9. "Is `parallelStream().forEach` always faster than `forEachOrdered`?"** That cannot be stated for every problem. Speed depends on the workload, action cost, data size, resource contention, and pipeline splittability. Benchmark under realistic conditions.

**10. "If I want to test stream logic, how should I test stdout?"** For ordering requirements, use an ordered source + `forEachOrdered`, or better yet test the data with `toList`. For `parallel forEach`, test properties such as the set of elements, sum, or count, rather than comparing random log order.

## 15. Practice exercises

1. Using `List.of("C","A","B")`, call `parallelStream().forEachOrdered(System.out::println)`. Predict the print order and explain why it does not automatically become A,B,C.
2. Add `sorted()` before `forEachOrdered` in exercise 1, and predict stdout again.
3. With `IntStream.rangeClosed(1,5).parallel()`, try `forEach` multiple times and note the observable order changes. **Do not** write an assertion that the order must change on every run.
4. Create a `ConcurrentLinkedQueue<Integer>`, use `parallel().forEach(queue::add)`, then verify that the size is 5 and the sorted set of elements is [1,2,3,4,5]. Do not rely on insertion order.
5. Replace the queue in exercise 4 with a shared `ArrayList`. Analyze the race risk, then change the collection approach to `toList()`.
6. Using `orders` from the sample program, create a list of order IDs with `map(Order::id).toList()`. Why is the list in encounter order even when using `parallelStream()`?
7. Write a pipeline that `filter`s for orders with an amount over 150, `sorted` by ID, and then `forEachOrdered` to print the ID. With the sample data, the result should be A01 then A02.
8. From a `HashSet<String>`, write code to print results in alphabetical order. Explain the roles of `sorted()` and `forEachOrdered()`.
9. Write an action that throws `IllegalStateException` when encountering ID A01; test `forEachOrdered` on a sequential stream and identify which operations happened beforehand.
10. Explain why `forEachOrdered` is not suitable for replacing `mapToInt(...).sum()` just to compute the total amount, even when using a thread-safe `LongAdder`.
11. Write two different operations: one that creates a `List<String>` of order labels using `map(...).toList()`, and one that prints those labels using `forEachOrdered`. Distinguish the return value of each terminal operation.
12. Use `List.of(3,1,2)` and then call `unordered().parallel().forEachOrdered(...)`. Why should you not write an expected stdout with an order based on the original source?

## 16. Application checklist

- Is the goal an **action returning `void`** or **returning data results**?
- Does the source have an encounter order? If not, is `sorted` or another data structure needed?
- Is the **action execution order** a business requirement, or is having all elements sufficient?
- If running `parallel`, does the action touch shared mutable state? Is there a thread-safe plan in place?
- Are there side effects in `map`/`filter`/`peek` with a misconception that `forEachOrdered` will order them?
- Are `LongAdder` or an external collection being used just to replace `sum`/`toList`/`collect`?
- If the action fails midway, do the side effects that already occurred need recovery/idempotency handling?
- Are tests accidentally assuming a fixed order for `parallel forEach` or `HashSet`?
- Has the cost of preserving order been evaluated if the data is large and the workload is parallel?

**Conclusion:** `forEach()` and `forEachOrdered()` are both terminal operations that accept a `Consumer` to perform an action on each element. `forEach` does not guarantee encounter order; `forEachOrdered` preserves action order when the stream has an encounter order, even on a parallel stream, without making the entire pipeline run sequentially. When you need to **compute or collect results**, prefer `map`/`reduce`/`toList`/`collect`; when performing side effects, actively choose an ordering policy and protect shared state.
