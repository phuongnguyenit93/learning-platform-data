# Encounter Order Differs from Lambda Execution Order in Java Parallel Streams

## 1. Central question

When calling `parallelStream()` or `stream().parallel()`, multiple elements of a Stream can be processed by concurrently running tasks. This gives rise to an important misconception:

> **Encounter order** is the logical order defined by the source and stages of the Stream; **lambda execution order** is the actual order in which a mapper, predicate, or action is invoked on elements during execution. These two orders are **not identical** when running in parallel.

Example of an ordered list:

```text
Source List:       [1, 2, 3, 4, 5]
Encounter order:   1 → 2 → 3 → 4 → 5

A possible lambda execution schedule could be:
                  map(3) → map(5) → map(1) → map(2) → map(4)

The result of toList() on an ordered stream can still be:
                  [10, 20, 30, 40, 50]
```

The "possible execution schedule" line is **an illustration of one possibility**, not a schedule guaranteed by Java. The JVM may pick a different schedule, or even use fewer threads depending on load and environment. What the API guarantees here is the **semantic ordering of the resulting data**, not the order of individual `map` calls.

Lesson objectives:

- Distinguish encounter order, execution order, output order, and side-effect order.
- Know which operations **preserve result order** and which **do not guarantee callback order**.
- Distinguish `forEach` from `forEachOrdered` and understand the limits of `forEachOrdered`.
- Understand how `findFirst` differs from `findAny`, and the effects of `unordered()`, `sorted()`, and short-circuiting operations.
- Write **stateless**, **non-interfering** lambdas and avoid mutable shared state bugs.
- Test final values rather than treating log order as part of the contract.

## 2. Four "order" concepts to separate

| Concept | Question it answers | What the API guarantees |
| --- | --- | --- |
| **Encounter order** | In what logical order are elements considered to pass through the Stream? | Depends on source and stages; e.g. List is ordered, `sorted` establishes order |
| **Execution order** | When, on which thread, and in what order are lambdas invoked? | For parallel streams, usually **no guarantee** matching encounter order |
| **Result order** | In what order is the terminal operation's result collected/returned? | Depends on the terminal operation and whether the pipeline is ordered |
| **Side-effect order** | In what order do logging, variable updates, or file writes occur? | Do not rely on callback order; only certain APIs, such as `forEachOrdered`, have a specific contract |

An example: `list.parallelStream().map(f).toList()`. If `list` has encounter order, `toList()` returns a list in the encounter order of the mapped results; yet calls to `f.apply(...)` may interleave across multiple threads.

For instance:

```java
List<Integer> squares = List.of(1, 2, 3, 4)
        .parallelStream()
        .map(n -> n * n)
        .toList();
```

The result of this snippet in a Java 17 method with `List` imported is `[1, 4, 9, 16]`. You do not need to know whether the mapper ran on 4 before 1 to deduce this.

**An ordered pipeline does not mean each lambda runs sequentially.** The framework can store results in their corresponding positions and then assemble the final list in the right order.

## 3. Which sources have encounter order?

Not every Stream starts with a defined encounter order.

| Source / stage | Logical order |
| --- | --- |
| `List.of("A","B","C").stream()` | Has encounter order matching List element order |
| `Arrays.stream(array)` | Ordered by array index |
| `IntStream.range(0, 5)` | Ordered 0, 1, 2, 3, 4 |
| `Stream.of("A","B","C")` | Ordered by argument order |
| Stream from `HashSet` | Should not rely on a defined encounter order |
| `stream.sorted(comparator)` | Establishes element order according to comparator |
| `stream.unordered()` | Removes ordered constraint if present; **does not mean random shuffling** |

Setting `parallel()` **does not automatically erase encounter order**. An ordered stream remains ordered when switched to parallel. What changes is primarily **how processing is scheduled**, not automatically changing data semantics to unordered.

Conversely, when a source is already unordered, a terminal operation asking for "the first element" has no meaning relative to an original List order that does not exist. With an ordered List source, `findFirst()` has a clearer meaning.

Do not treat the accidental iteration order observed from a `HashSet` as a guarantee. If ascending order is required, use `sorted()` with an appropriate comparator instead of hoping the hash structure happens to yield the same order on the current run.

## 4. Java 17 example: ordered source, ordered result despite parallel pipeline

Save file `ParallelResultOrderDemo.java`:

```java
import java.util.List;

public class ParallelResultOrderDemo {
    public static void main(String[] args) {
        List<Integer> source = List.of(6, 2, 4, 1, 5, 3);

        List<Integer> tenTimes = source.parallelStream()
                .map(n -> n * 10)
                .toList();

        List<Integer> oddValues = source.parallelStream()
                .filter(n -> n % 2 != 0)
                .toList();

        List<Integer> ascending = source.parallelStream()
                .sorted()
                .toList();

        System.out.println("source=" + source);
        System.out.println("mapped=" + tenTimes);
        System.out.println("odds=" + oddValues);
        System.out.println("sorted=" + ascending);
    }
}
```

Compile/run:

```bash
javac ParallelResultOrderDemo.java
java ParallelResultOrderDemo
```

Exact output:

```text
source=[6, 2, 4, 1, 5, 3]
mapped=[60, 20, 40, 10, 50, 30]
odds=[1, 5, 3]
sorted=[1, 2, 3, 4, 5, 6]
```

Explanation:

1. `source` is a List with encounter order 6, 2, 4, 1, 5, 3.
2. `map(n -> n * 10)` creates new values and preserves the corresponding source order in the `toList()` result. There is no requirement that the mapper runs in that order.
3. `filter(n -> n % 2 != 0)` removes even numbers, keeping the **relative order** of the remaining elements in the ordered stream: 1, 5, 3.
4. `sorted()` establishes ascending numeric order, so the final result is 1, 2, 3, 4, 5, 6.
5. `toList()` on an ordered stream returns a list in result encounter order, even when computation parts are processed in parallel.
6. Every call above creates a new Stream from the source; the same Stream instance is not reused after a terminal operation.

Do not conclude that `parallelStream()` is "useless" just because the result is still ordered. Gains can come from splitting computation across elements, while the system still merges results per contract.

## 5. Observing execution order: logs may not follow source order

The following example intentionally puts logging inside a mapper to **observe while learning**, not as a production pattern using logs as business results.

Create file `ParallelExecutionLogDemo.java`:

```java
import java.util.List;
import java.util.stream.IntStream;

public class ParallelExecutionLogDemo {
    public static void main(String[] args) {
        List<Integer> source = IntStream.rangeClosed(1, 8)
                .boxed()
                .toList();

        System.out.println("source=" + source);

        List<Integer> result = source.parallelStream()
                .map(n -> {
                    System.out.println("map " + n + " on " +
                            Thread.currentThread().getName());
                    return n * 10;
                })
                .toList();

        System.out.println("result=" + result);
    }
}
```

Run:

```bash
javac ParallelExecutionLogDemo.java
java ParallelExecutionLogDemo
```

**Deterministic first/last lines** (with schedule-dependent log lines in between):

```text
source=[1, 2, 3, 4, 5, 6, 7, 8]
... map 1..8 lines, possibly interleaved across multiple threads ...
result=[10, 20, 30, 40, 50, 60, 70, 80]
```

The middle part is **not fixed stdout**; order and thread names vary per run. Java may execute lambdas on ForkJoinPool worker threads or the calling thread, and is not required to distribute concurrently in every environment.

What can be reliably verified is that `result` data follows the logical order when the source is ordered. Therefore, do not write tests comparing the verbatim full log of a parallel pipeline. Tests should compare final results and guaranteed invariants.

Even in a sequential Stream, do not overgeneralize "exactly once per callback per element" as a rule for every pipeline: short-circuiting and stage-skipping optimizations can still occur.

## 6. `forEach()` does not guarantee action order

The `Stream.forEach` documentation describes it as a terminal operation that is **explicitly nondeterministic** regarding action invocation order for parallel streams: the framework is free to execute the action on a chosen thread and in an order suited to the schedule.

The following illustrates:

```java
IntStream.rangeClosed(1, 5)
        .parallel()
        .forEach(n -> System.out.print(n + " "));
```

Assume this snippet is in a method importing `java.util.stream.IntStream`. One run might print:

```text
3 5 4 2 1
```

**This is only an example of possible output**, not a value you are guaranteed to get. Another run might print 1, 2, 3, 4, 5 or another order. If multiple actions write to the same output stream, how they interleave also depends on how write calls are synchronized; do not use logs to deduce the exact schedule.

The purpose of `forEach` is to apply an action to consumed elements, **not** to produce an ordered log following encounter order. If business rules require output ordering, use an API with an appropriate contract.

## 7. `forEachOrdered()` guarantees action order, but does not force earlier mappers to run sequentially

For a Stream with encounter order, `forEachOrdered(action)` guarantees that actions execute **in encounter order**. The specification also guarantees that the action on an earlier element *happens-before* the action on the next element; this is a constraint on action order, not a license to share mutable state arbitrarily in upstream stages.

Create file `ForEachOrderedDemo.java`:

```java
import java.util.stream.IntStream;

public class ForEachOrderedDemo {
    public static void main(String[] args) {
        StringBuilder output = new StringBuilder();

        IntStream.rangeClosed(1, 5)
                .parallel()
                .forEachOrdered(n -> output.append(n).append(" "));

        System.out.println("ordered=" + output.toString().trim());

        System.out.println("mapped=" +
                IntStream.rangeClosed(1, 5)
                        .parallel()
                        .map(n -> n * n)
                        .boxed()
                        .toList());
    }
}
```

Compile/run:

```bash
javac ForEachOrderedDemo.java
java ForEachOrderedDemo
```

Deterministic output:

```text
ordered=1 2 3 4 5
mapped=[1, 4, 9, 16, 25]
```

In this example, `StringBuilder` is only mutated inside `forEachOrdered` actions that have a *happens-before* relationship between elements in order, so actions do not run concurrently arbitrarily as in `forEach`. However, in production code, prefer collecting results and formatting in a clear step rather than assuming all side effects in parallel streams are safe.

**Limitation:** if you add `map` or `peek` **before** `forEachOrdered`, there is no guarantee that those upstream callbacks will run in encounter order. `forEachOrdered` applies its ordering guarantee to **the action passed to itself**, not the entire pipeline.

Illustrative example:

```java
IntStream.rangeClosed(1, 5).parallel()
        .map(n -> {
            System.out.println("map " + n); // order not guaranteed
            return n * 10;
        })
        .forEachOrdered(n -> System.out.println("out " + n));
```

The `out ...` lines preserve order 10, 20, 30, 40, 50 on an ordered stream, while the `map ...` lines may appear interleaved before or between them. This snippet is in a method importing `IntStream`; full stdout is non-deterministic and **should not** be used as an exact assertion.

## 8. Comparison table of common terminal operations

| Terminal | Ordered source + parallel | Notes |
| --- | --- | --- |
| `toList()` | List in encounter order | Does not guarantee mapper/peek execution order |
| `collect(Collectors.toList())` | Result preserves encounter order per suitable collector contract | Does not guarantee specific mutable/immutable collection under this API |
| `forEach(action)` | Does not guarantee action order | Typically allows parallel scheduled execution |
| `forEachOrdered(action)` | Actions in encounter order | Does not force all upstream callbacks to run in order |
| `findFirst()` | First element in encounter order | Can make parallelism less flexible |
| `findAny()` | Any matching element | Element choice is not guaranteed, even when source is ordered |
| `anyMatch()`, `allMatch()`, `noneMatch()` | Returns boolean per condition | May stop early; no guarantee on callback order/completeness |
| `count()` | Counts elements | May optimize by skipping stages that do not affect size |
| `min()`/`max()` | Finds extreme value per comparator | Value result does not require ordered logging |

Do not equate **"terminal has a deterministic result"** with **"all callbacks are invoked in a deterministic order"**. A reduction can use intermediate results and merge properly even when groups are processed by different work branches.

## 9. `findFirst()` and `findAny()`: ordered vs. non-ordered selection

With an ordered stream:

- `findFirst()` by contract attempts to retrieve **the first element in encounter order**.
- `findAny()` is allowed to retrieve **any element**, without being required to return the first element. This is a convenient choice when you only need "some result", especially in parallel streams.

Create file `FindFirstAnyDemo.java`:

```java
import java.util.List;

public class FindFirstAnyDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(10, 20, 30, 40);

        int first = numbers.parallelStream()
                .findFirst()
                .orElse(-1);

        int any = numbers.parallelStream()
                .findAny()
                .orElse(-1);

        System.out.println("first=" + first);
        System.out.println("any-is-member=" + numbers.contains(any));
    }
}
```

Run:

```bash
javac FindFirstAnyDemo.java
java FindFirstAnyDemo
```

Deterministic output:

```text
first=10
any-is-member=true
```

The exact value of variable `any` is **not guaranteed by Java** in this example; it is an arbitrary element of the non-empty list. If you print `any` instead of printing the membership check, stdout can differ across runs.

If the source is unordered (or `unordered()` was called), `findFirst()` no longer has a guaranteed "first per source List", so it may return any element. Do not design business logic around `findAny` accidentally returning a stable value in a specific environment.

## 10. Order of `map`, `filter`, and `sorted` in a parallel pipeline

**With an ordered stream**, `map` and `filter` preserve the corresponding encounter order semantics:

```java
List<Integer> source = List.of(5, 2, 7, 4);

List<Integer> values = source.parallelStream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * 10)
        .toList();
```

The result is `[50, 70]`, because odd numbers 5 and 7 appear in that order in the source. Yet `Predicate.test` on element 7 may still run before element 5 under some parallel schedules.

`sorted()` is a **stateful intermediate operation** and establishes a new logical order according to a comparator. A pipeline:

```java
List<Integer> sorted = source.parallelStream()
        .sorted()
        .toList();
```

returns `[2, 4, 5, 7]`, without needing comparison callbacks or mappers to run in source order. If the comparator has side effects (logging, mutating state), the order and count of comparator calls are generally not a contract to rely on.

With a source having encounter order, `sorted` is stable by contract: elements that compare equal keep their relative order. With an unordered source, there is no stability guarantee for elements with equal keys. To get deterministic output when multiple elements tie on key, add a secondary comparator such as `thenComparing(...)`.

## 11. `unordered()` does not mean `shuffle()`

A common misconception is:

```java
List<Integer> result = List.of(1, 2, 3, 4)
        .parallelStream()
        .unordered()
        .toList();
```

After `unordered()`, the Stream is **no longer constrained to preserve encounter order**, but that does not force Java to permute elements. The result may still be `[1, 2, 3, 4]` across many runs; do not rely on that to say `unordered()` "does nothing" or "shuffles randomly".

When the ordering constraint is removed, some stateful or short-circuiting operations may have more optimization opportunities. For example, `distinct` on an ordered parallel stream must preserve the first element in encounter order, whereas on an unordered stream it can be more flexible. Similarly, `limit(n)` on an ordered parallel stream must take the first `n` elements in order; with unordered, the choice of `n` elements can differ as long as it obeys the corresponding contract.

If you need random order, use an explicit shuffle/sampling mechanism on appropriate data. `unordered()` is not a randomize function.

## 12. `limit()`, `skip()`, and short-circuiting when running in parallel

When the source is ordered:

```java
List<Integer> firstThree = IntStream.rangeClosed(1, 10)
        .parallel()
        .limit(3)
        .boxed()
        .toList();
```

The result is `[1, 2, 3]`. That does **not** mean the framework only ever starts processing the first three elements in every pipeline. Parallel tasks may be split or partially process other parts before the whole process stops; the terminal contract mainly concerns the resulting values, not a specific element-visiting schedule.

With `skip(3)` on an ordered stream of 1..10, the remaining elements start from 4 in encounter order; with an unordered stream, behavior regarding which specific elements are skipped does not have to stick to "the original first three elements".

A commonly considered optimization is allowing unordered when the application **does not care which elements** are selected. However, doing so **changes business constraints**. Do not add `unordered()` just to speed up if the user needs top-N, pagination, or first-element selection in a stable order.

## 13. Side effects in lambdas: more dangerous than log order differences

The difference between encounter order and execution order is not merely about messy-looking logs. If a lambda **writes to a shared mutable variable or collection**, the result can be genuinely wrong.

### Wrong pattern: mutating a shared `ArrayList` from parallel `forEach`

```java
List<Integer> result = new ArrayList<>();
IntStream.rangeClosed(1, 10_000)
        .parallel()
        .forEach(result::add); // UNSAFE
```

This is an **anti-pattern snippet**, requiring imports for `List`, `ArrayList`, `IntStream`. `ArrayList` is not thread-safe; concurrent actions can corrupt state, drop elements, or throw errors. Occasionally running "fine" in small tests does not prove the code is safe.

**Correct way when the goal is collecting results:**

```java
List<Integer> result = IntStream.rangeClosed(1, 10_000)
        .parallel()
        .boxed()
        .toList();
```

This way the framework is responsible for coordinating result accumulation per the terminal contract. With an ordered stream, the list follows encounter order. No side effect into an external container is needed.

### Semantically wrong pattern: numbering by callback execution time

```java
AtomicInteger sequence = new AtomicInteger();

List<String> labels = IntStream.rangeClosed(1, 5)
        .parallel()
        .mapToObj(n -> n + ":" + sequence.incrementAndGet())
        .toList();
```

This is **an illustration of what to avoid when you want encounter-order numbering**, requiring imports for `AtomicInteger`, `List`, `IntStream`. `AtomicInteger` avoids races on the counter variable, but the sequence number still reflects **the order in which callbacks took turns**, not source order. The resulting list may have `n` in ascending order while the counter labels are not ascending with `n`.

If the goal is indexing by source position, use an explicitly indexed source, such as `IntStream.range(0, list.size()).mapToObj(i -> (i + 1) + ":" + list.get(i))`, and collect with `toList()`. This approach relies on **indices**, not on lambda invocation schedules.

## 14. Complete Java 17 example: indexing by index and avoiding shared state

Create file `StableIndexDemo.java`:

```java
import java.util.List;
import java.util.stream.IntStream;

public class StableIndexDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Lan", "An", "Minh", "Hoa");

        List<String> labels = IntStream.range(0, names.size())
                .parallel()
                .mapToObj(i -> (i + 1) + ":" + names.get(i))
                .toList();

        System.out.println(labels);
    }
}
```

Run:

```bash
javac StableIndexDemo.java
java StableIndexDemo
```

Output:

```text
[1:Lan, 2:An, 3:Minh, 4:Hoa]
```

The first element has index 0 but is labeled 1; index-based labels are **invariant with respect to execution schedule**. `IntStream.range(0, n)` has encounter order along the index range. `List.of(...)` provides an unmodifiable list, convenient for read-only examples. With a mutable source modified concurrently, index-based access also needs appropriate synchronization/snapshots.

This pattern suits many position-based processing tasks. However, not every Stream has indices; to generate sequence numbers for complex streams, design an appropriate indexing step or materialize data into a clearly ordered collection first.

## 15. `forEachOrdered` does not make all upstream side effects safe

Consider:

```java
List<String> names = List.of("A", "B", "C");
List<String> mutable = new ArrayList<>();

names.parallelStream()
        .map(s -> {
            mutable.add(s);  // still wrong: mapper can run concurrently
            return s;
        })
        .forEachOrdered(System.out::println);
```

This is a **counterexample regarding concurrency safety**, requiring imports for `List`, `ArrayList`. Even though `forEachOrdered` prints A, B, C in exact encounter order, `mutable.add(s)` in the **upstream mapper** does not become thread-safe. `forEachOrdered` only guarantees the order of the action passed to it.

Therefore:

- Do not mutate a shared mutable collection inside `map`/`filter`/`peek` of a parallel pipeline.
- Avoid lambdas depending on call count, thread ID, or callback execution timing.
- If you need to aggregate data, use `collect`/`reduce` with contract-compliant accumulators and combiners, without a shared mutable accumulator outside the framework.
- If mandatory ordered side effects are needed, consider a sequential pipeline or an API with an appropriate ordering contract; do not place arbitrary side effects in intermediate stages.
- If you need to test ordering, test **the materialized result**, not the log order of a mapper.

Regarding `peek()`, the API documentation emphasizes it is primarily useful for debugging. The framework may even **skip certain operations** when they do not affect the final result per contract; for example, `count()` on a sized source can compute quickly without calling `peek`. Using `peek` for mandatory auditing is wrong even when running sequentially, not just in parallel.

## 16. Testing parallelism: focus on deterministic data

A good test must check what Java guarantees:

```java
List<Integer> input = List.of(4, 1, 3, 2);

List<Integer> actual = input.parallelStream()
        .map(n -> n * 2)
        .toList();

if (!actual.equals(List.of(8, 2, 6, 4))) {
    throw new AssertionError(actual);
}
```

This is a snippet in a method with `List` imported. The test relies on encounter order and `map`/`toList` semantics, regardless of which thread ran the mapper.

To test results where order does not matter, compare sets/multisets as appropriate (paying special attention to duplicate counts—avoid converting to a `Set` if duplicates must be preserved). If order is clearly required, do not "fix" a test by converting expected and actual to a `Set`; build a pipeline or comparator that meets the requirement.

For code with side effects, randomly passing a few test runs does not prove thread safety. Designing to avoid shared state remains more important than running multiple times and seeing no errors.

## 17. Parallel is not always faster than sequential

Another misconception: having multiple threads means work is definitely faster. In practice, parallel streams add overhead for source splitting, scheduling, result merging, memory pressure, and synchronization. If callbacks are too light (e.g. `n -> n + 1` on a few elements), this overhead can exceed the benefit.

Some encounter-order-dependent stages like `findFirst()`, `limit()`, `skip()`, or global sorting can make parallelism more complex. If business logic does not require order, dropping the ordered constraint sometimes opens optimization opportunities, but only do so when **it does not change data requirements**.

Prioritize in this order:

1. **Correct semantics**: inputs, results, required ordering, and error handling.
2. **Concurrency safety**: non-interfering, stateless lambdas or proper synchronization.
3. **Determinism**: do you need ordered output or just equivalent values?
4. **Actual performance**: benchmark on representative data, machines, and loads.

Do not infer speed from log order or the number of threads visible on the console.

## 18. Common mistakes

1. **Thinking `parallelStream()` erases a List's order.** False: a List source remains ordered; many terminals preserve result encounter order.
2. **Thinking the mapper ran in List order because `toList()` returned the right order.** False: output order and execution order are two different contracts.
3. **Using `forEach` and asserting exact logs.** Action order of `forEach` on a parallel stream is not guaranteed.
4. **Thinking `forEachOrdered` forces upstream `map`/`peek` to run sequentially.** No; it guarantees the order of the action in the terminal itself.
5. **Treating `findAny()` as `findFirst()` on a parallel stream.** They can differ; `findAny` does not promise the first element.
6. **Using `unordered()` as a shuffle.** It removes ordering constraints rather than randomly shuffling.
7. **Dropping ordering without checking top-N/pagination requirements.** It can change which elements are selected via `limit/skip/findFirst`.
8. **Adding side effects to a mapper to assign sequence numbers.** `AtomicInteger` increment order is execution-schedule order, not encounter order.
9. **Collecting results into an external `ArrayList` via `parallel().forEach(add)`.** Not thread-safe; use collector/`toList`.
10. **Taking `peek` logs as proof of completeness.** Callbacks may be skipped due to short-circuiting/optimizations.
11. **Sorting without a tie-breaker on an unordered source.** Order of elements with equal keys can be non-deterministic.
12. **Using changing mutable state inside a comparator/Predicate.** Easily causes unpredictable results and contract violations.
13. **Assuming multiple threads always run in parallel.** The runtime has the right to split based on environment; do not rely on specific thread counts.
14. **Treating one passing run as proof of correct concurrency.** A race condition may simply not have manifested in that test run.
15. **Assuming every terminal always traverses everything and calls callbacks once.** Short-circuiting, empty sources, and optimizations can alter behavior.
16. **Losing track of ordered/unordered sources.** Check which stages establish/remove encounter order before drawing conclusions about output.

## 19. Self-check exercises

### Exercise 1: Predict deterministic output

```java
List<Integer> values = List.of(5, 1, 4, 2, 3);

List<Integer> a = values.parallelStream()
        .map(n -> n + 10)
        .toList();

List<Integer> b = values.parallelStream()
        .filter(n -> n % 2 != 0)
        .toList();

List<Integer> c = values.parallelStream()
        .sorted()
        .limit(3)
        .toList();
```

This is code inside a method with `List` imported. Determine `a`, `b`, `c` and answer: is the mapper guaranteed to run in the order 5, 1, 4, 2, 3?

**Answer:** `a = [15, 11, 14, 12, 13]`, `b = [5, 1, 3]`, and `c = [1, 2, 3]`. There is no guarantee the mapper runs in source order; `toList()` on an ordered stream preserves result order.

### Exercise 2: Choose `forEach` or `forEachOrdered`

Requirement: print numbers 1 to 5 in exact order in a parallel stream:

```java
IntStream.rangeClosed(1, 5)
        .parallel()
        .forEachOrdered(System.out::println);
```

With `IntStream` imported, each line will be 1, 2, 3, 4, 5 in order. Replacing with `forEach` does not guarantee that print order.

### Exercise 3: Can you trust `findAny` to return 10?

```java
int x = List.of(10, 20, 30)
        .parallelStream()
        .findAny()
        .orElse(-1);
```

**Answer:** No. Because the source is non-empty, `x` is an element in the list, but there is no guarantee it is 10. If business logic needs the first element in encounter order, use `findFirst()` on an ordered stream.

### Exercise 4: Why is `AtomicInteger` still wrong for numbering?

A parallel mapper assigns labels with `sequence.incrementAndGet()` at callback execution time. Why can the resulting List still be ordered while the number labels are scrambled?

**Answer:** because the result is arranged in encounter order, whereas the counter increments in **execution order**. `AtomicInteger` only guarantees atomic increments, not turning execution order into encounter order. Use data indices if positional numbering is needed.

### Exercise 5: Upstream risk

```java
Stream.of("A", "B", "C")
        .parallel()
        .peek(System.out::println)
        .forEachOrdered(s -> save(s));
```

This illustration assumes an existing `save(String)` method with a specific contract. Is `peek` guaranteed to print A, B, C in order? What about `save`?

**Answer:** there is no guarantee on the callback order of `peek`. If the pipeline has encounter order, `forEachOrdered`'s action calls `save` in the order A, B, C. You still need error handling, idempotency, and resource management for `save` per business logic; action order does not replace those requirements.

## 20. Parallel Stream design checklist

Before switching from `stream()` to `parallelStream()`, ask yourself:

- Does the source have encounter order? Does it come from a List, array, SortedSet, or an unordered structure?
- Does the result need ordering? If so, which terminal preserves that order?
- Are callbacks pure, independent of mutable state, and non-modifying on the source?
- Are any side effects placed in `map/filter/peek` just to log, count, or update external variables?
- Are `findAny/findFirst/limit/skip` and a "first" requirement involved?
- Are `sorted/distinct` and comparator stability/tie-breaker factors involved?
- If using `forEachOrdered`, does anyone mistakenly think all upstream operations also run sequentially?
- Are there tests only comparing logs or checking thread IDs instead of data results?
- Does the runtime actually benefit from splitting the source and merging results?
- If dropping encounter order with `unordered()`, is that permitted by business requirements?

**Conclusion:** **Encounter order describes the logical order of data; execution order describes the callback schedule.** In a parallel stream, those two can be very different. Write independent lambdas without mandatory side effects; use `toList` to collect results in encounter order when the source is ordered, `forEachOrdered` when the action itself must be ordered, and `findFirst` when the first element in source order is needed. For everything else, do not infer lambda invocation schedules from result data order.

**References:** Java SE API `java.util.stream.Stream` (`parallel`, `unordered`, `map`, `filter`, `sorted`, `forEach`, `forEachOrdered`, `findFirst`, `findAny`, `toList`); package specification `java.util.stream` on encounter order, non-interference, and stateless behaviors; `java.util.stream.IntStream`.