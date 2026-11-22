# Fixing Parallel Pipelines with Shared-State Bugs

## 1. Exercise Context: Sequential Works, Parallel Breaks

In the **Java Stream API**, switching `stream()` to `parallelStream()` or calling `parallel()` can distribute some data-processing work across multiple tasks. However, a pipeline that behaves correctly sequentially **does not automatically become safe in parallel**. A common mistake is having lambdas inside `forEach`, `filter`, or `map` simultaneously read and mutate a variable, list, Map, or the traversed source itself.

Counterexample:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

IntStream.range(0, 10_000)
        .parallel()
        .forEach(shared::add); // WRONG: multiple tasks mutate one ArrayList concurrently.

System.out.println(shared.size());
// Not guaranteed to equal 10_000; may even throw an exception.
```

`ArrayList.add` does not support safe concurrent updates. Bugs can manifest as **lost elements**, wrong sizes, corrupted internal structure, or exceptions. A single run printing 10,000 **does not prove the code is right**: task scheduling is non-deterministic.

The best fix is usually **not adding a lock around every `add` call**, but letting the Stream manage collection itself:

```java
List<Integer> result = IntStream.range(0, 10_000)
        .parallel()
        .boxed()
        .toList();

System.out.println(result.size()); // 10000
System.out.println(result.get(0)); // 0
```

With an `IntStream.range` source that has an encounter order, `toList()` preserves that order even though computation may happen in parallel. `Stream.toList()` was introduced in Java 16 and returns an **unmodifiable** list.

This lesson belongs to the **Advanced Exercises and Projects** chapter of the `JAVA_STREAM_API` module. The focus is not merely memorizing API names, but **reading buggy pipelines, identifying shared state, choosing replacement operations, proving correctness, and designing repeatable tests**.

**After this lesson, you will be able to:**

1. Identify data races, interference, and stateful behavior in parallel pipelines.
2. Fix `List`/`Set` collection, summing/counting, grouping, and deduplication using appropriate terminal operations.
3. Distinguish *thread-safe* from *semantically right for business logic*, especially regarding encounter order.
4. Use `collect`, `reduce`, `groupingBy`, `toMap`, or `groupingByConcurrent` according to contract.
5. Write tests asserting results rather than relying on thread count or accidental execution order.

Complete examples in this lesson use **Java 17+** (`record`, `List.of`, `Stream.toList()`). The underlying principles of parallel Streams, stateless lambdas, and Collectors have existed since Java 8.

## 2. Execution Model: Ordered Sources Can Still Execute Out of Order

`parallelStream()` expresses the intent to process in parallel; the Stream can **split data**, process branches, and combine results. It makes no promises about thread count, lambda execution order, or that each element gets its own thread.

```text
                       List: [A, B, C, D]
                               |
                       parallelStream()
                         /           \
                    [A, B]           [C, D]
                      |                |
                   task 1           task 2
                      \                /
                       \              /
                         collect(...)
                               |
                       [A, B, C, D]
```

The diagram above is only **one logical split**. In practice, the framework may split many times, and branches may run on different schedules.

Concepts to distinguish:

| Concept | Meaning |
| --- | --- |
| **Encounter order** | Logical element order defined by the source and pipeline. |
| **Execution order** | Timing and thread executing each callback. Never rely on this in parallel. |
| **Data race** | Multiple threads access the same mutable state, with at least one write, without proper synchronization. |
| **Non-interference** | Lambdas do not modify the data source currently being traversed by the Stream. |
| **Stateless behavior** | Processing one element does not depend on mutable state modified by processing another element. |
| **Mutable reduction** | `collect` creates private result containers, accumulates into them, and combines them per contract. |

Example where an ordered source still yields an ordered result:

```java
List<String> labels = List.of("A", "B", "C", "D");

List<String> mapped = labels.parallelStream()
        .map(String::toLowerCase)
        .toList();

System.out.println(mapped); // [a, b, c, d]
```

**Do not conclude** that `map("A")` ran before `map("B")`. What is guaranteed here is that the resulting list reflects encounter order when the terminal operation collects it.

## 3. Diagnostic Workflow for Pipelines with Shared State

When facing a bug that appears only with `parallelStream()`, inspect step by step:

1. **Source:** Is any `ArrayList`, `HashMap`, array, or mutable object being mutated while the Stream traverses it?
2. **Lambdas:** Does `filter`, `map`, `peek`, or `forEach` write to external variables, call `add`/`put`/`increment`, or mutate source element fields?
3. **Desired result type:** Do you need a List, Set, Map, count, sum, extremum, or an independent action? Is there a standard terminal operation replacing the side effect?
4. **Ordering:** Do you need the first element by source order, display order, or merely an unordered result set?
5. **Associativity:** When using custom `reduce`/`collect`, do you have a proper identity and associative combiner?
6. **Testing:** Do tests assert right results **regardless of thread scheduling**, or did you just print logs and eyeball one run?

A quick smell test is scanning for mutable variables **outside** the pipeline that are used inside it:

```java
List<String> output = new ArrayList<>();
int[] total = {0};
Map<String, Integer> counts = new HashMap<>();

// Whenever these variables are mutated inside a parallel Stream lambda,
// they are the first places to inspect.
```

Not every variable captured by a lambda is wrong. Reading a shared **immutable** configuration object is completely fine; the danger lies in reading/writing mutable state across elements or interfering with the source.

## 4. Bug #1: Using forEach to Append to a Shared ArrayList

### Buggy Pipeline

```java
List<String> ids = List.of("T01", "T02", "T03", "T04");
List<String> collected = new ArrayList<>();

ids.parallelStream()
        .map(String::toLowerCase)
        .forEach(collected::add); // WRONG
```

Here, multiple `ArrayList.add` calls can overlap. Beyond possible lost elements, `forEach` also **makes no ordering guarantee** on a parallel Stream: even if replaced with a thread-safe Collection, insertion order might not be `T01, T02, T03, T04`.

### Best Fix When You Need a Result List

```java
List<String> safeList = ids.parallelStream()
        .map(String::toLowerCase)
        .toList();

System.out.println(safeList); // [t01, t02, t03, t04]
```

If you need a list that is **modifiable after collection**, specify the container via a collector:

```java
List<String> editableList = ids.parallelStream()
        .map(String::toLowerCase)
        .collect(Collectors.toCollection(ArrayList::new));

editableList.add("t05"); // Valid.
```

`Collectors.toList()` is also commonly used, though the API does not guarantee a specific List implementation or mutability. `toCollection(ArrayList::new)` explicitly expresses the need for an `ArrayList`.

### Writing Three-Argument collect Explicitly

```java
List<String> safeByThreeArgs = ids.parallelStream()
        .map(String::toLowerCase)
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );

System.out.println(safeByThreeArgs);
// [t01, t02, t03, t04]
```

Each `supplier` call creates an **independent** container. The `accumulator` adds elements into its branch's container; the `combiner` merges containers per contract. Therefore, `ArrayList` not being thread-safe **does not break `collect`**: the framework never calls the accumulator concurrently on the same non-concurrent container.

**Bug when returning the same shared List from the supplier:**

```java
List<String> shared = new ArrayList<>();

List<String> broken = ids.parallelStream()
        .collect(
                () -> shared,    // WRONG: does not create a new container.
                List::add,
                List::addAll
        );
```

The supplier may be invoked many times. Always returning `shared` causes branches to write to one List concurrently, and the combiner may even merge a container with itself, severely corrupting data.

## 5. Bug #2: Summing Numbers with an External int or Array

### Buggy Pipeline

```java
int[] total = {0};

IntStream.rangeClosed(1, 1_000)
        .parallel()
        .forEach(n -> total[0] += n); // WRONG: non-atomic read-modify-write.

System.out.println(total[0]);
// Not guaranteed to equal 500500.
```

`total[0] += n` reads the old value, adds, and writes back. Two threads can read the same value and overwrite each other's updates (**lost update**).

### Fix When You Only Need the Sum

```java
long expected = IntStream.rangeClosed(1, 1_000)
        .parallel()
        .asLongStream()
        .sum();

System.out.println(expected); // 500500
```

Using `mapToLong`/`asLongStream` and `sum` expresses the calculation directly without counters or locks. `long` widens range compared to `int`, though it can still overflow if the sum exceeds `long` bounds.

For decimal monetary sums, you can use immutable `BigDecimal` value objects:

```java
List<java.math.BigDecimal> amounts = List.of(
        new java.math.BigDecimal("12.50"),
        new java.math.BigDecimal("7.25")
);

java.math.BigDecimal amountTotal = amounts.parallelStream()
        .reduce(java.math.BigDecimal.ZERO, java.math.BigDecimal::add);

System.out.println(amountTotal); // 19.75
```

`BigDecimal.add` does not mutate its operands and guarantees exact addition for the inputs in this example without a `MathContext`. Reduction requires a valid identity and associative combiner so the result does not depend on how the source is split.

### Does AtomicInteger Solve Everything?

`AtomicInteger.addAndGet` guarantees atomic updates, so it prevents lost updates on a counter. However, that **does not** make a counter-based `filter` deterministic, nor does it replace the need to preserve order.

```java
AtomicInteger sequence = new AtomicInteger();

List<Integer> unstable = IntStream.rangeClosed(1, 10)
        .parallel()
        .filter(n -> sequence.incrementAndGet() <= 3)
        .boxed()
        .toList();

// No guarantee that unstable == [1, 2, 3].
```

Here the counter is atomically safe, yet **which elements are evaluated first** depends on thread scheduling. If the requirement is the first three elements from an ordered source, use:

```java
List<Integer> firstThree = IntStream.rangeClosed(1, 10)
        .parallel()
        .limit(3)
        .boxed()
        .toList();

System.out.println(firstThree); // [1, 2, 3]
```

`limit` on an ordered parallel Stream can incur coordination cost, but it satisfies the requirement accurately. Never trade correctness for speed using a shared counter.

## 6. Bug #3: Counting by Key with a Mutable HashMap

### Buggy Pipeline

```java
List<String> teams = List.of("A", "B", "A", "C", "B", "A");
Map<String, Integer> sharedCounts = new HashMap<>();

teams.parallelStream()
        .forEach(team -> sharedCounts.merge(team, 1, Integer::sum));
        // WRONG: HashMap is unsafe when mutated concurrently by multiple threads.
```

`HashMap.merge` does not turn `HashMap` into a concurrent Map. Concurrent branches can lose updates or exhibit undefined behavior.

### Fix with groupingBy + counting

```java
Map<String, Long> counts = teams.parallelStream()
        .collect(Collectors.groupingBy(
                java.util.function.Function.identity(),
                Collectors.counting()
        ));

System.out.println(counts.get("A")); // 3
System.out.println(counts.get("B")); // 2
System.out.println(counts.get("C")); // 1
```

The collector organizes accumulation and combining properly for parallel sources. `groupingBy` does not need to return a `ConcurrentMap` to produce correct results. For large sources where ordering is unneeded, consider `groupingByConcurrent`:

```java
ConcurrentMap<String, Long> concurrentCounts = teams.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                java.util.function.Function.identity(),
                Collectors.counting()
        ));

System.out.println(concurrentCounts.get("A")); // 3
```

`groupingByConcurrent` is a **concurrent, unordered** collector. It fits when encounter order of values within each group is unnecessary; real-world performance still depends on key distribution, source size, and contention.

### Fix with toMap and a Merge Function

```java
Map<String, Integer> countsWithMerge = teams.parallelStream()
        .collect(Collectors.toMap(
                java.util.function.Function.identity(),
                team -> 1,
                Integer::sum
        ));

System.out.println(countsWithMerge.get("A")); // 3
```

The merge function `Integer::sum` explicitly defines how values for duplicate keys combine. If you use the two-argument `Collectors.toMap` when duplicate keys exist, the collector throws `IllegalStateException`; never skip deciding how duplicates behave.

**Note:** `Map` results from the collectors above have no guaranteed deterministic key iteration order. Check entries via `get` or compare Maps by contents, never by `HashMap.toString()`.

## 7. Bug #4: Deduplicating with a Shared HashSet Inside filter

### Buggy Pipeline

```java
Set<String> seen = new HashSet<>();

List<String> unique = List.of("A", "B", "A", "C", "B")
        .parallelStream()
        .filter(seen::add) // WRONG: stateful predicate and non-thread-safe HashSet.
        .toList();
```

`filter(seen::add)` reads and mutates external state. Beyond data race risks, even if replaced with a concurrent Set, deciding **which occurrence comes first** is incompatible with parallel scheduling.

### Fix with distinct

```java
List<String> uniqueOrdered = List.of("A", "B", "A", "C", "B")
        .parallelStream()
        .distinct()
        .toList();

System.out.println(uniqueOrdered); // [A, B, C]
```

On a Stream with an encounter order, `distinct` retains the **first occurrence** of equal values, and `toList` preserves that order. If the source is unordered, do not expect a specific order or representative when distinct object references are equal under `equals`.

`distinct` is a **stateful** intermediate operation managed by the library, unlike a lambda manually mutating a shared `HashSet`. Preserving encounter order in parallel `distinct` can incur memory and coordination overhead.

### Deduplicating by Business Key Instead of Full Object equals

`distinct` uses element `equals`/`hashCode`. If the rule is keeping one order per `id` while objects carry multiple fields, do not treat `distinct()` on full `Order` objects as equivalent to deduplicating by `id`.

```java
record Product(String sku, int version, String name) {}

List<Product> products = List.of(
        new Product("P01", 1, "Old pen"),
        new Product("P01", 2, "New pen"),
        new Product("P02", 1, "Notebook")
);

Map<String, Product> latest = products.parallelStream()
        .collect(Collectors.toMap(
                Product::sku,
                java.util.function.Function.identity(),
                java.util.function.BinaryOperator.maxBy(
                        Comparator.comparingInt(Product::version)
                                .thenComparing(Product::name)
                )
        ));

System.out.println(latest.get("P01").version()); // 2
```

The merge function picks the higher version and uses `name` to break ties. Rules must have a **deterministic tie-breaker** if records can tie on primary criteria yet differ in fields you care about. If you want the first occurrence by List position, choose a strategy honoring encounter order rather than inferring from parallel Map update order.

## 8. Bug #5: Mutating the Source Collection During Stream Traversal

### Buggy Pipeline

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

source.parallelStream()
        .filter(n -> {
            if (n == 2) {
                source.add(99); // WRONG: mutates the source collection.
            }
            return n > 0;
        })
        .toList();
```

This is a **non-interference** violation, not merely `ArrayList` lacking thread safety. It can throw `ConcurrentModificationException`, yield unpredictable data, or break consistency.

### Fix with a Read-Only Source Pipeline

```java
List<Integer> source = new ArrayList<>(List.of(1, 2, 3, 4));

List<Integer> selected = source.parallelStream()
        .filter(n -> n > 0)
        .toList();

List<Integer> updated = new ArrayList<>(source);
updated.add(99);

System.out.println(selected); // [1, 2, 3, 4]
System.out.println(updated);  // [1, 2, 3, 4, 99]
```

In this approach, producing the result and updating the structure are **two separate phases**. If another thread is also mutating the source, separating phases on one thread is not enough: the application needs a consistent snapshot or proper source synchronization/ownership.

`List.copyOf(source)` creates an unmodifiable list for safer reading when the snapshot is taken with no concurrent writes and no `null` elements. That is a **shallow copy**, so mutable element objects can still change elsewhere. Never assume `List.copyOf` solves every race in a concurrently updated system.

## 9. Bug #6: Using reduce with a Mutable Identity

`reduce` is meant for combining **values**, not for updating a shared mutable accumulator.

### Buggy Pipeline

```java
List<String> source = List.of("A", "B", "C");

List<String> incorrect = source.parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, item) -> {
                    list.add(item); // WRONG: mutates a mutable identity.
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
```

`reduce` requires an identity, accumulator, and combiner compatible with the reduction contract. Mutating the identity directly can cause multiple branches to share state and corrupt results, especially in parallel.

### Fix with collect

```java
List<String> correct = source.parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );

System.out.println(correct); // [A, B, C]
```

Three-argument `collect` is **purpose-built mutable reduction**: the supplier creates a fresh container for each accumulation partition, the accumulator mutates that container, and the combiner merges partitions properly.

If you just want to join strings, instead of manually accumulating a `StringBuilder` via `reduce`, use the built-in collector:

```java
String joined = source.parallelStream()
        .collect(Collectors.joining(","));

System.out.println(joined); // A,B,C
```

On an ordered Stream, `joining` preserves encounter order. On an unordered source, do not assume a joining order.

## 10. Are Thread-Safe Containers Always the Right Fix?

No. **Thread-safety** solves only certain concurrent access issues; it **does not automatically guarantee order or business semantics**.

| Approach | What Problem It Avoids | Remaining Limitations |
| --- | --- | --- |
| `Collections.synchronizedList(...)` | Synchronizes individual List operations | `add` order depends on thread scheduling, not necessarily encounter order |
| `ConcurrentLinkedQueue` | Supports concurrent enqueue/dequeue | Task insertion order need not match source order |
| `ConcurrentHashMap` | Concurrent Map operations per contract | Update/combine logic must be semantically valid; no key ordering |
| `AtomicInteger` / `LongAdder` | Concurrent counter updates | Does not make state-dependent predicates deterministic |
| `forEachOrdered` | Runs terminal action in encounter order when ordered | Can reduce parallelism; does not replace `collect` or guard against external threads |
| Standard `collect`/`reduce` | Distributes and merges results per contract | Still requires appropriate accumulation, result type, and ordering |

Example genuinely needing an independent concurrent sink:

```java
java.util.concurrent.ConcurrentLinkedQueue<String> queue =
        new java.util.concurrent.ConcurrentLinkedQueue<>();

List.of("A", "B", "C").parallelStream()
        .forEach(queue::add);

System.out.println(queue.size()); // 3
// No guarantee that iterating the queue yields A, B, C in source order.
```

This `add` operation is thread-safe; however, when the goal is simply **collecting a list**, `toList()` or `collect` expresses the intent far more cleanly. Only use concurrent queues/Maps and side effects when there is a specific need for a concurrent destination.

### forEachOrdered Does Not Fix Everything

```java
List<String> printed = new ArrayList<>();

List.of("A", "B", "C").parallelStream()
        .forEachOrdered(printed::add);

System.out.println(printed); // [A, B, C]
```

Within **a single `forEachOrdered` call** on an ordered source, actions run in encounter order and each action *happens-before* the next. Yet upstream `map`/`filter` stages may still run in parallel, and `printed` is not protected from concurrent mutations by **other** threads.

Therefore, even though this snippet produces the right output within its scope, **prefer `toList`** when the desired output is a List. `forEachOrdered` is more useful when the final action genuinely must occur sequentially, such as writing lines to a channel.

## 11. Concurrent Collectors and Choosing the Right Target

Some collectors can accumulate concurrently, though there are distinctions between:

- **Parallel execution source:** `parallelStream()`.
- **Concurrent-capable collector:** e.g. `groupingByConcurrent` or `toConcurrentMap`.
- **Result is a ConcurrentMap:** not every Map returned from a parallel Stream is concurrent.

Example summing by key into a concurrent Map:

```java
record Event(String team, long points) {}

List<Event> events = List.of(
        new Event("A", 2),
        new Event("B", 3),
        new Event("A", 5)
);

ConcurrentMap<String, Long> totals = events.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Event::team,
                Event::points,
                Long::sum
        ));

System.out.println(totals.get("A")); // 7
System.out.println(totals.get("B")); // 3
```

The merge function `Long::sum` produces results independent of splitting and combination order **within non-overflowing bounds**. By contrast, merge rules like "keep the string from whichever thread updates last" depend on scheduling and are not stable business rules.

With ordered data where you must **retain the first occurrence**, `toConcurrentMap` may be unsuitable if the merge function relies on "whoever arrives first" across threads. Specify explicit record comparison criteria (timestamp, version, business sequence) and use an associative tie-breaking merge, or use an ordered approach.

## 12. Every Side Effect in map or peek Deserves Scrutiny

`forEach` is not the only place that can introduce unsafe behavior:

```java
AtomicInteger calls = new AtomicInteger();

long n = List.of(1, 2, 3, 4)
        .parallelStream()
        .peek(x -> calls.incrementAndGet())
        .count();

// Never use calls.get() as a business count.
System.out.println(n); // 4
```

Certain terminal operations can leverage known source size to return a result **without running side-effect-only intermediate steps** when doing so does not affect the result. `peek` is useful for limited debugging, not for guaranteeing notifications or per-element updates.

If you need a count, use `count`. If you need transformed values, use pure `map`. If you must perform I/O for every element, design actions, idempotency, error handling, and concurrency explicitly rather than assuming `parallelStream` handles everything automatically.

## 13. Complete Example: Repairing a Parallel Sales Report

Problem: a list of sales orders has an ID, responsible team, unit count, and validity flag. We need:

1. A list of **valid order IDs** in source order.
2. Total units per team.
3. Total units across all valid orders.
4. Count of valid orders.
5. ID lists per team and an equivalent concurrent total map.

### Buggy Pattern to Avoid

```java
List<String> ids = new ArrayList<>();
Map<String, Long> byTeam = new HashMap<>();
long[] sum = {0L};

orders.parallelStream()
        .filter(Order::valid)
        .forEach(order -> {
            ids.add(order.id());                           // WRONG
            byTeam.merge(order.team(), order.units(), Long::sum); // WRONG
            sum[0] += order.units();                       // WRONG
        });
```

All three mutable containers `ids`, `byTeam`, and `sum` are updated from multiple branches without a proper reduction/collection contract. Switching to `synchronizedList` **does not fix** the other two variables and does not guarantee the order of `ids`.

### Repaired Java 17+ Program

```java
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

public class ParallelStateRepairDemo {
    record Order(
            String id,
            String team,
            long units,
            boolean valid
    ) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("S01", "A", 3, true),
                new Order("S02", "B", 5, true),
                new Order("S03", "A", 100, false),
                new Order("S04", "A", 2, true),
                new Order("S05", "B", 4, true)
        );

        List<String> validIds = orders.parallelStream()
                .filter(Order::valid)
                .map(Order::id)
                .toList();

        Map<String, Long> totalsByTeam = orders.parallelStream()
                .filter(Order::valid)
                .collect(Collectors.groupingBy(
                        Order::team,
                        Collectors.summingLong(Order::units)
                ));

        long totalUnits = orders.parallelStream()
                .filter(Order::valid)
                .mapToLong(Order::units)
                .sum();

        long validCount = orders.parallelStream()
                .filter(Order::valid)
                .count();

        Map<String, List<String>> idsByTeam = orders.parallelStream()
                .filter(Order::valid)
                .collect(Collectors.groupingBy(
                        Order::team,
                        Collectors.mapping(
                                Order::id,
                                Collectors.toList()
                        )
                ));

        ConcurrentMap<String, Long> concurrentTotals = orders.parallelStream()
                .filter(Order::valid)
                .collect(Collectors.groupingByConcurrent(
                        Order::team,
                        Collectors.summingLong(Order::units)
                ));

        // Verify correctness against data, not execution schedule.
        List<String> expectedIds = List.of("S01", "S02", "S04", "S05");
        Map<String, Long> expectedTotals = Map.of("A", 5L, "B", 9L);

        if (!validIds.equals(expectedIds)) {
            throw new AssertionError("Incorrect order or contents of validIds");
        }
        if (!totalsByTeam.equals(expectedTotals)) {
            throw new AssertionError("Incorrect totals by team");
        }
        if (totalUnits != 14L || validCount != 4L) {
            throw new AssertionError("Incorrect total or order count");
        }
        if (!idsByTeam.get("A").equals(List.of("S01", "S04"))
                || !idsByTeam.get("B").equals(List.of("S02", "S05"))) {
            throw new AssertionError("Incorrect ID list by team");
        }
        if (!concurrentTotals.equals(expectedTotals)) {
            throw new AssertionError("Incorrect concurrentTotals");
        }

        System.out.println("IDs: " + validIds);
        // IDs: [S01, S02, S04, S05]
        System.out.println("Team A: " + totalsByTeam.get("A")); // 5
        System.out.println("Team B: " + totalsByTeam.get("B")); // 9
        System.out.println("Total: " + totalUnits);           // 14
        System.out.println("Count: " + validCount);           // 4
        System.out.println("PASS");
    }
}
```

### Why Is This Fix Correct?

1. `Order` is a `record` containing only `String`, primitive numbers, and `boolean`; input data in the example is not mutated during traversal.
2. `filter(Order::valid)` and `map(Order::id)` use no external mutable state.
3. `toList` returns the ID list preserving the `List` source's encounter order.
4. `groupingBy(..., summingLong(...))` accumulates sums per key; it never asks a `HashMap` to self-mutate concurrently inside `forEach`.
5. `mapToLong(...).sum()` and `count()` express sums and counts directly.
6. `groupingBy(..., mapping(..., toList()))` collects per-group ID lists, preserving relative element order within each group from the ordered source.
7. `groupingByConcurrent` builds a `ConcurrentMap` of team totals; because it uses integer addition, aggregated contents are the proper equality criterion—never rely on Map key iteration order.
8. Each statistic builds a **fresh Stream from `orders`**. A Stream already consumed by a terminal operation is never reused.

The example prioritizes **correctness and clarity**; on huge datasets where multiple KPIs are needed in one pass, design a combined collector with a valid combining contract. Never revert to shared mutable state just to avoid multiple passes.

## 14. Focused Testing for Parallel Pipelines

To test a repaired pipeline, divide checks into groups:

| Test Group | What to Verify |
| --- | --- |
| **Correct contents** | All matching elements appear the right number of times; sums and counts match. |
| **Correct order** | When business logic requires it, ordered outputs match encounter order regardless of scheduling. |
| **Empty source** | `count() == 0`, `sum() == 0`, `toList()` empty, `groupingBy` returns an empty Map. |
| **Duplicate keys** | Merge or downstream collectors handle multiple records per key per rules. |
| **Missing data** | Policies for `null`, null keys, and invalid values are explicitly defined. |
| **Sequential vs. parallel** | Compare **semantic** equality, not `toString()` of unordered Maps. |
| **Large data** | Run stress tests to raise bug detection odds, without treating one passing run as absolute proof. |
| **Performance** | Run warmed-up benchmarks on realistic load, measuring time/memory vs. sequential execution. |

Example checking both execution modes on a stable source:

```java
List<Integer> source = IntStream.range(0, 100_000)
        .boxed()
        .toList();

List<Integer> sequential = source.stream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 2)
        .toList();

List<Integer> parallel = source.parallelStream()
        .filter(n -> n % 2 == 0)
        .map(n -> n * 2)
        .toList();

System.out.println(sequential.equals(parallel)); // true
```

If transformations are **non-associative** or order-sensitive (such as left-fold subtraction or floating-point addition with rounding error), add checks aligned with business policy. In a parallel Stream, reductions need a valid identity and combiner; for `double`, addition order can affect the least significant bits. Never check only "did not throw an exception".

## 15. Advanced Exercises: Fix Three Buggy Pipelines Yourself

### Exercise 1 — List of Active Items

Given:

```java
record Item(String id, boolean active) {}

List<Item> items = List.of(
        new Item("I01", true),
        new Item("I02", false),
        new Item("I03", true),
        new Item("I04", true)
);
```

Code to fix:

```java
List<String> sharedIds = new ArrayList<>();
items.parallelStream()
        .filter(Item::active)
        .forEach(item -> sharedIds.add(item.id()));
```

**Prompt:** Fix so the output is `[I01, I03, I04]` in source order, without locks or capturing an external mutable List.

**Solution:**

```java
List<String> safeIds = items.parallelStream()
        .filter(Item::active)
        .map(Item::id)
        .toList();

System.out.println(safeIds); // [I01, I03, I04]
```

### Exercise 2 — Counting by State

Given:

```java
record Job(String state, int points) {}

List<Job> jobs = List.of(
        new Job("OPEN", 2),
        new Job("CLOSED", 1),
        new Job("OPEN", 3),
        new Job("OPEN", 5)
);
```

Code to fix:

```java
Map<String, Integer> counts = new HashMap<>();
jobs.parallelStream().forEach(job ->
        counts.merge(job.state(), 1, Integer::sum));
```

**Prompt:** Use a collector to obtain `OPEN=3` and `CLOSED=1`, without relying on Map key order.

**Solution:**

```java
Map<String, Long> safeCounts = jobs.parallelStream()
        .collect(Collectors.groupingBy(
                Job::state,
                Collectors.counting()
        ));

System.out.println(safeCounts.get("OPEN"));   // 3
System.out.println(safeCounts.get("CLOSED")); // 1
```

### Exercise 3 — Total Points and Selecting One Record per State

A developer wrote:

```java
long[] sum = {0};
jobs.parallelStream().forEach(job -> sum[0] += job.points());
```

**Prompt:** Fix using primitive reduction, and explain why `AtomicLong`, though atomic, is not the best expression for computing a sum.

**Solution:**

```java
long safeSum = jobs.parallelStream()
        .mapToLong(Job::points)
        .sum();

System.out.println(safeSum); // 11
```

`AtomicLong.addAndGet` avoids lost updates, yet forces tasks to contend on one shared variable, increasing coordination and making the pipeline less declarative. `mapToLong(...).sum()` uses standard reduction without external state.

**Extension:** If you want a representative `Job` for each state, specify the selection criterion explicitly: highest points, latest timestamp, or source order. When using `toMap` on a parallel Stream, supply an associative merge function rather than arbitrarily picking "whichever arrived first" under thread scheduling.

## 16. Self-Check Exercise: When Does Synchronization Still Fail?

Consider:

```java
List<Integer> synchronizedOutput =
        java.util.Collections.synchronizedList(new ArrayList<>());

IntStream.range(1, 6)
        .parallel()
        .forEach(synchronizedOutput::add);

System.out.println(synchronizedOutput);
```

Appending elements is synchronized, yet **insertion order is not guaranteed** to be `[1, 2, 3, 4, 5]`. If you only need a list containing all five numbers in any order, the code may be safe for individual adds. If you need source order, use `IntStream.range(1, 6).parallel().boxed().toList()`.

Another scenario:

```java
AtomicInteger seenCount = new AtomicInteger();

List<String> firstTwo = List.of("A", "B", "C", "D")
        .parallelStream()
        .filter(x -> seenCount.incrementAndGet() <= 2)
        .toList();
```

Even with an atomic counter, `firstTwo` is **not guaranteed to equal `[A, B]`**. To get the first two elements of the List, use `limit(2)`; to get the first two under a sorting criterion, define that criterion and use the appropriate operation.

**Explain to yourself:** Why can `Collectors.groupingBy(..., toList())` still be correct in a parallel Stream even though ordinary accumulation Lists are not thread-safe? Because the collector creates **separate containers and merges results per contract**, rather than having all threads call `add` on a single user-captured List.

## 17. Handoff Checklist for Repaired Parallel Pipelines

1. **Do not mutate the source:** never call `add`/`remove`/`put` on the collection being traversed by the Stream.
2. **State-clean lambdas:** `filter`/`map` must not rely on shared mutable counters, Lists, or Maps.
3. **Right terminal operation:** List -> `toList`/`collect`; sum -> `sum`/`reduce`; grouping -> `groupingBy`; existence -> `anyMatch`; deduplication -> `distinct`.
4. **Independent supplier:** for custom `collect`, every supplier call must create a fresh container, never a global shared object.
5. **Lawful combiner:** never drop partial results; maintain identity, associativity, and accumulator compatibility.
6. **Clear ordering:** specify encounter order; never rely on `forEach` for order or assume thread execution order.
7. **Valid Map keys:** duplicate-key policies and merge functions are defined; keys are not mutated while stored in a Map.
8. **Safe numeric ranges:** check overflow and rounding error; never pick a smaller numeric type than required.
9. **Stable source:** snapshot or synchronize the source if other components may mutate it concurrently; remember shallow copies do not lock mutable element objects.
10. **Verify results:** assert totals, counts, contents, and order when required; test empty data, duplicates, many keys, and varied sizes.
11. **Measure performance:** compare `stream()` and `parallelStream()` under real load; never assume parallel is always faster.
12. **Resource lifecycle:** for file/connection Streams, close sources with `try-with-resources`; avoid turning parallelism into unbounded blocking I/O.

## Key Takeaways

Shared-state bugs in parallel Streams often start from seemingly harmless expressions such as `forEach(sharedList::add)`, `sharedCount++`, `filter(sharedSet::add)`, or a `map` that mutates the source. Executed in parallel, they cause data races, misordering, lost data, or violations of **stateless** and **non-interfering** contracts.

The preferred fix is **turning side effects into return values**: use `toList`/`collect` for Collections, `sum`/`count`/`reduce` for numbers, `groupingBy`/`toMap` for grouping, and `distinct` for deduplication. Thread-safe containers solve only part of concurrency; they neither preserve encounter order nor establish stable business rules. Verify correctness first, and only then evaluate the gains of parallel execution.
