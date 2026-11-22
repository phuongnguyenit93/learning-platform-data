# collect() and Reduction with a Mutable Accumulation Container

## Lesson Objectives

In Java Streams, **`collect()`** is a *terminal operation* used to gather elements into a structured result. An important capability is **mutable reduction**: instead of computing a completely new value at each step, the program creates a **mutable result container**, adds data to it, and combines partial accumulation containers when needed.

After this lesson, you will be able to:

- Properly understand the `collect(supplier, accumulator, combiner)` mechanism on `Stream<T>`.
- Write the three functions to create a container, accumulate elements, and combine containers without improperly sharing state.
- Use `collect` to create an `ArrayList`, `LinkedHashSet`, `Map`, or a custom business-logic mutable statistics class.
- Compare the three-argument `collect` form with `collect(Collector)` and standard `Collectors`.
- Distinguish **mutable reduction with collect** from **immutable/value reduction with reduce**.
- Identify identity, associativity requirements, ordering characteristics, concurrency errors, exceptions, and resources.
- Compile/run Java 17 examples and predict the results when the source is empty and when using a parallel stream.

## 1. What Is a Mutable Accumulation Container?

Suppose we have a Stream containing `"Book"`, `"Pen"`, `"Tea"`. We want to create an `ArrayList<String>` so we can add/remove elements after collecting. A direct way to think about this is:

1. Create an empty list `new ArrayList<String>()`.
2. For each Stream element, call `list.add(element)` on the list being accumulated.
3. If running in parallel, there may be multiple partial lists; combine the lists using `left.addAll(right)`.
4. Return the accumulation container upon completion.

This is the form of mutable reduction supported by the three-argument overload of `collect`.

```java
ArrayList<String> names = Stream.of("Book", "Pen", "Tea")
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );
```

The result contains `[Book, Pen, Tea]`. The essential point is not the name `ArrayList`, but the workflow: **initialize a new container → update it with elements → merge the containers into the final result**.

Mutable reduction **does not mean modifying the source collection**. It means modifying a **result container** allocated specifically for the collection operation. Intermediate operations like `map` and `filter` should avoid unnecessary side effects and avoid mutating the source being traversed.

## 2. The Two Main Overloads of collect()

### 2.1. collect(supplier, accumulator, combiner)

Signature on `Stream<T>`:

```java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);
```

This is a simplified API signature for learning, not a method you need to redeclare yourself. The three functional interfaces come from `java.util.function`.

| Parameter | Function descriptor | Responsibility |
| --- | --- | --- |
| `supplier` | `() -> R` | Creates a **new** accumulation container `R` in its initial state |
| `accumulator` | `(R, T) -> void` | Incorporates element `T` into accumulation container `R` |
| `combiner` | `(R, R) -> void` | Merges the second container into the first container when needed |
| Return value | `R` | The resulting container or object |

Example:

```java
ArrayList<String> names = Stream.of("A", "B", "C").collect(
        ArrayList::new,      // Supplier<ArrayList<String>>
        ArrayList::add,      // BiConsumer<ArrayList<String>, String>
        ArrayList::addAll    // BiConsumer<ArrayList<String>, ArrayList<String>>
);
```

This form of `collect` is especially easy to understand for types with clear add/merge APIs such as `List`, `Set`, `StringBuilder`, or a custom-defined accumulator class. `combiner` returns `void`; it must perform the merge into the passed-in container, not just create another object and discard it.

In a simple sequential Stream, the runtime may only need one container, so the combiner does not necessarily run. **Do not conclude that the combiner is unimportant**: a parallel Stream or another valid implementation may use it to merge partial results.

### 2.2. collect(Collector)

The other form:

```java
<R, A> R collect(Collector<? super T, A, R> collector)
```

A `Collector` is an object describing the accumulation process, including how to create the container, add elements, combine containers, finish the result, and its characteristics. With `Collector<T,A,R>`, the intermediate type `A` **can differ** from the output type `R`.

```java
List<String> names = Stream.of("A", "B", "C")
        .collect(Collectors.toList());
```

`Collectors` (in `java.util.stream`) provides useful factories: `toList`, `toSet`, `toMap`, `groupingBy`, `mapping`, `joining`, `counting`, `summarizingInt`, `toCollection`.

Both overloads are terminal operations. However:

- The three-argument overload makes the three functions `supplier/accumulator/combiner` explicit, and the result is the accumulated container `R`.
- The `Collector` overload can perform a **finisher** to convert accumulator `A` into the final result `R`, supports composing Collectors hierarchically, and carries characteristics for optimization.
- If a standard Collector already exists with clear intent, it should usually be preferred before writing a multi-step accumulation mechanism yourself.

**Version note:** `Stream.collect` and `Collectors` have existed since Java 8; the full examples below use Java 17. Do not confuse this with `Stream.toList()` (Java 16+), which returns a List that does not allow structural modification.

## 3. Supplier: Must Create a New Accumulator, Not Share One Object

In a mutable collect, `supplier` may be called multiple times to create separate containers for different parts of the pipeline. Therefore, it must provide **a new result container compatible with an empty state** on every invocation.

**Correct:**

```java
ArrayList<String> collected = Stream.of("A", "B", "C")
        .parallel()
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

`ArrayList::new` creates a different list each time it is called. Partial containers can be merged later.

**Wrong intent:**

```java
ArrayList<String> shared = new ArrayList<>();

List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(
                () -> shared,
                List::add,
                List::addAll
        );
```

The snippet above may compile, but `() -> shared` **always returns the same list**; this violates the requirement for an empty, independent container on each supplier call. In parallel processing, this can cause data loss, write races, or `left.addAll(right)` receiving the same object in both positions and causing erroneous duplication. Even in a sequential pipeline, reusing a container that already holds data breaks the clarity of the contract.

How to fix: use `ArrayList::new`. If you want to start from baseline data, model how each container is initialized and how they are combined so the baseline data is not duplicated across multiple branches. Do not take an external List and share it across all accumulators of a parallel reduction.

**Distinction:** you can use a mutable `StringBuilder` inside each created container, but do not share that same `StringBuilder` across all partial results.

## 4. Accumulator: Modify the Result Container, Not the Source

`accumulator` receives a current container `R` and an element `T`. It should **incorporate the element into the accumulated state** while preserving the result contract.

```java
ArrayList<String> names = Stream.of("A", "B")
        .collect(
                ArrayList::new,
                (list, value) -> list.add(value),
                ArrayList::addAll
        );
```

For `List`, calling `add` returns `boolean`, whereas `BiConsumer.accept` returns `void`. The method reference `ArrayList::add` is still compatible: the return value of a statement expression is ignored in a `void` context.

### 4.1. Adding Data After Transformation

To collect product names, you can map first:

```java
ArrayList<String> names = sales.stream()
        .map(Sale::product)
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

This snippet illustrates with `Sale` defined in the full program. `map` transforms each `Sale` into a `String`, so at `collect` we have `T = String` and `R = ArrayList<String>`.

You can also keep the `Stream<Sale>` source and write the accumulator:

```java
ArrayList<String> names = sales.stream().collect(
        ArrayList::new,
        (list, sale) -> list.add(sale.product()),
        ArrayList::addAll
);
```

Both approaches produce the product names. Which one is clearer depends on complexity; a `map(...).collect(...)` pipeline often yields single-purpose steps that are easy to test.

### 4.2. Callbacks Should Not Have Side Effects Outside the Result

`accumulator` is allowed to mutate the container `R` provided by the collect mechanism; **that does not mean** you should arbitrarily mutate `sales`, write to a database, send emails, or update a shared external counter variable. A parallel pipeline can change how groups are split and the execution order.

If a business operation must execute exactly once, perform it in a controlled orchestration layer rather than hiding it inside an accumulator meant only for counting/collecting data. The existence of mutable reduction does not turn external side effects into transactions.

## 5. Combiner: Correctly Merging Two Partial States

This is the part most easily written incorrectly when first learning `collect`. The `combiner` of the three-argument overload receives two containers `R`, **merges the contents of the second into the first**, and does not return a replacement container:

```java
(left, right) -> left.addAll(right)
```

For `ArrayList`, `addAll` appends elements from `right` into `left`. For a statistics object:

```java
(left, right) -> {
    left.count += right.count;
    left.total += right.total;
}
```

The statistics snippet is illustrative, assuming `left/right` belong to a class with fields `count` and `total`.

### 5.1. Wrong: Combiner Does Not Actually Merge

```java
// Logic error: does not add right's contents into left.
(left, right) -> {
    new ArrayList<>(right);
}
```

This statement creates a temporary List and discards it, so `right`'s data is never added to `left`. With a sequential Stream, this bug may be hidden because the combiner does not run. When running in parallel, part of the data can be lost.

**Rule:** in the three-argument overload, the combiner must mutate the first received accumulation container so that it accurately represents the combined result of both branches.

### 5.2. Identity and Associativity

Each result created by the supplier must be an **empty/identity** state for the accumulation operation. Combining branches must produce an equivalent result regardless of how elements are grouped within allowed ordering:

- For a list with encounter order, `addAll` merges the parts in the proper order.
- For a count, add the two counts.
- For a Map of counts by key, add the corresponding values for the same key.
- For complex statistics, combine all required fields (count, sum, min, max…), without omitting any component.

For example, in a statistics design with `count` and `sum`: if the combiner only adds `sum` and forgets `count`, the average `sum/count` will be wrong in a parallel pipeline.

**Compatibility condition:** accumulating one element and then merging with the rest must match merging partial results that were accumulated separately. This is the basis for the runtime to partition work while preserving the meaning of the collection operation.

## 6. Simple Examples: List, Set, Map, and StringBuilder

### 6.1. Mutable ArrayList

```java
ArrayList<String> names = Stream.of("A", "B", "C")
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );
names.add("D"); // valid
```

When a structurally modifiable List is required, `collect(Collectors.toCollection(ArrayList::new))` also expresses this very clearly. `Stream.toList()`, on the other hand, returns an unmodifiable List.

### 6.2. LinkedHashSet in Insertion Order

```java
LinkedHashSet<String> unique = Stream.of("java", "api", "java")
        .collect(
                LinkedHashSet::new,
                LinkedHashSet::add,
                LinkedHashSet::addAll
        );
```

The result iterates in insertion order: `java`, then `api`. With `Collectors.toSet()`, the Set implementation and iteration order are not guaranteed. When you need a specific type, request it using `toCollection(LinkedHashSet::new)` or the three-argument overload as above.

### 6.3. Map Accumulating Sums by Key

Suppose each `Sale` has `category()` and `units()`:

```java
Map<String, Integer> totals = sales.stream().collect(
        TreeMap::new,
        (map, sale) -> map.merge(
                sale.category(), sale.units(), Integer::sum),
        (left, right) -> right.forEach((key, value) ->
                left.merge(key, value, Integer::sum))
);
```

`supplier` provides a new `TreeMap`. The accumulator adds `units` to the category. The combiner iterates over the right Map and adds the values of corresponding keys into the left Map.

In a parallel example, **each accumulator Map is a partial result**, not a shared TreeMap on which all threads directly call `merge` without synchronization. Container independence is the key point.

In production code, this can often be replaced by a standard Collector that is easier to maintain:

```java
Map<String, Integer> totals = sales.stream().collect(
        Collectors.groupingBy(
                Sale::category,
                TreeMap::new,
                Collectors.summingInt(Sale::units)
        )
);
```

Both snippets produce the same kind of total units per category for the sample data. `groupingBy` expresses the grouping intent more clearly than a hand-written Map merging algorithm.

### 6.4. StringBuilder and Delimiter Bugs

`StringBuilder` is an appropriate mutable accumulation container for concatenating text:

```java
StringBuilder result = Stream.of("Book", "Pen", "Tea").collect(
        StringBuilder::new,
        (sb, text) -> {
            if (sb.length() > 0) sb.append(" | ");
            sb.append(text);
        },
        (left, right) -> {
            if (left.length() > 0 && right.length() > 0) {
                left.append(" | ");
            }
            left.append(right);
        }
);
```

With data consisting only of **non-empty** strings in the example, the result is `Book | Pen | Tea`.

Note: **do not copy this rule mechanically for all strings**: an empty string `""` can be a valid element, but `StringBuilder.length() == 0` does not distinguish between “no elements yet” and “one empty string has been added”. If you need exact joining regardless of empty strings, use `Collectors.joining(" | ")` or an accumulator class that also tracks the element count to manage delimiters.

```java
String result = Stream.of("Book", "Pen", "Tea")
        .collect(Collectors.joining(" | "));
```

The `joining` Collector is the more readable choice when the task is simply joining strings. There is no need to create a custom mutable result container if the library already has a suitable standard implementation.

## 7. Complete Java 17 Program

The following program demonstrates the three main functions, combining data in a parallel stream, computing statistics with a mutable class, and equivalent Collectors. All results are printed in deterministic order.

Save to the file **`MutableCollectDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class MutableCollectDemo {
    record Sale(String product, String category, int units,
                long unitPriceCents) {}

    static final class Stats {
        long count;
        long units;
        long revenueCents;

        void add(Sale sale) {
            count++;
            units += sale.units();
            revenueCents += sale.units() * sale.unitPriceCents();
        }

        void merge(Stats other) {
            count += other.count;
            units += other.units;
            revenueCents += other.revenueCents;
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("Book", "office", 2, 1_250),
                new Sale("Pen", "office", 3, 200),
                new Sale("Tea", "food", 1, 700)
        );

        ArrayList<String> names = sales.stream()
                .map(Sale::product)
                .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
        names.add("Extra");
        System.out.println("Names: " + names);

        LinkedHashSet<String> categories = sales.stream()
                .map(Sale::category)
                .collect(LinkedHashSet::new, LinkedHashSet::add,
                        LinkedHashSet::addAll);
        System.out.println("Categories: " + categories);

        Stats stats = sales.parallelStream()
                .collect(Stats::new, Stats::add, Stats::merge);
        System.out.println("Stats: count=" + stats.count
                + ", units=" + stats.units
                + ", revenue=" + stats.revenueCents);

        Map<String, Integer> unitTotals = sales.parallelStream().collect(
                TreeMap::new,
                (map, sale) -> map.merge(
                        sale.category(), sale.units(), Integer::sum),
                (left, right) -> right.forEach((key, value) ->
                        left.merge(key, value, Integer::sum))
        );
        System.out.println("By category: " + unitTotals);

        StringBuilder joined = sales.stream()
                .map(Sale::product)
                .collect(
                        StringBuilder::new,
                        (sb, name) -> {
                            if (sb.length() > 0) sb.append(" | ");
                            sb.append(name);
                        },
                        (left, right) -> {
                            if (left.length() > 0 && right.length() > 0)
                                left.append(" | ");
                            left.append(right);
                        });
        System.out.println("Joined: " + joined);

        List<String> standard = sales.stream()
                .map(Sale::product)
                .collect(Collectors.toList());
        System.out.println("Standard: " + standard);

        System.out.println("Empty stats: " +
                List.<Sale>of().stream()
                        .collect(Stats::new, Stats::add, Stats::merge).count);
    }
}
```

Compile/run with JDK 17 or higher:

```bash
javac MutableCollectDemo.java
java MutableCollectDemo
```

**Exact stdout:**

```text
Names: [Book, Pen, Tea, Extra]
Categories: [office, food]
Stats: count=3, units=6, revenue=3800
By category: {food=1, office=5}
Joined: Book | Pen | Tea
Standard: [Book, Pen, Tea]
Empty stats: 0
```

### Result Analysis

1. `names` is collected into a mutable `ArrayList`, so `names.add("Extra")` succeeds and prints four elements.
2. `categories` is a `LinkedHashSet`: deduplicates category `office`, preserving first-seen order `office` then `food`.
3. `Stats::new` creates state with three `long` fields defaulting to 0. `Stats::add` updates for each Sale, `Stats::merge` sums partial results. The three Sale items have `units = 2,3,1` so total units is `6`; revenue in cents is `2*1250 + 3*200 + 1*700 = 3800`.
4. `TreeMap` sorts category keys in natural order, so the Map prints `{food=1, office=5}`. `office` has `2+3 = 5`, `food` has `1`.
5. `StringBuilder` accumulates product names and the `" | "` delimiter. Since all three names are non-empty strings, the result `Book | Pen | Tea` is correct.
6. `Collectors.toList()` collects the list of names. The program only prints the result, **not assuming the List from this collector is mutable**.
7. An empty Stream still receives a `Stats` from the supplier with the default `count = 0`, so `Empty stats: 0`.

The two `parallelStream()` operations in the example **do not share a global Stats or TreeMap**. Each time the supplier needs a container, it creates a separate container; the combiner defines how to merge them. The result of summing numbers does not depend on how the work is split into branches.

If monetary amounts can exceed the `long` range, the program needs overflow checking or a larger numeric type; in the example data, all calculations stay within valid range.

## 8. collect() vs. reduce(): Difference in How Accumulation Is Represented

`reduce` is typically used when you need to produce **a new value** from the previous result and the next element:

```java
int sum = Stream.of(2, 3, 1)
        .reduce(0, Integer::sum); // 6
```

Whereas `collect` is appropriate when you need **a mutable accumulation object**:

```java
ArrayList<Integer> values = Stream.of(2, 3, 1)
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

Comparison:

| Criterion | `reduce` | `collect` with mutable container |
| --- | --- | --- |
| Typical goal | Sum, product, max/min, aggregated string, immutable value | List, Set, Map, multi-field statistics |
| Accumulator | Usually returns a new result value | `BiConsumer` mutating the passed-in container |
| Identity | Neutral value for the merge operation | New empty container from supplier |
| Combining | `BinaryOperator` returning merged value | `BiConsumer<R,R>` mutating the first container |
| Building a List by mutating identity | Wrong model | A common use case |
| Parallel processing | Requires associative combiner and proper identity | Requires supplier providing independent containers, valid accumulator/combiner |

### Anti-pattern: reduce with a Mutable ArrayList

```java
// Should not be used as a way to collect a List, especially on a parallel Stream.
List<String> wrong = Stream.of("A", "B", "C").parallel()
        .reduce(
                new ArrayList<>(),
                (list, value) -> {
                    list.add(value);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
```

This is **code illustrating a flawed design**, not a pattern to copy. The identity object `new ArrayList<>()` is not designed to be mutated concurrently by multiple branches. The accumulator both mutates the object's state and returns that same object, violating the principles required for `reduce` to work correctly under arbitrary partitioning.

**Correct approach:**

```java
List<String> collected = Stream.of("A", "B", "C").parallel()
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
```

Note that `reduce` with **immutable values** can be completely valid and appropriate, such as `reduce(0L, Long::sum)`. This does not mean `reduce` is always slow or wrong; just use the right reduction model.

## 9. Rules for Parallel Execution

### 9.1. No Need for a Thread-Safe ArrayList If Each Branch Has an Independent Container

In `collect(ArrayList::new, ArrayList::add, ArrayList::addAll)`, the framework orchestrates creating and combining accumulation containers to perform the reduction. The programmer **does not have to put a shared `ArrayList` in a static variable** or write `synchronized` around every `add` in every case.

What must be ensured is:

- The supplier creates a fresh, empty container each time it is needed.
- The accumulator only updates the container assigned to its branch, not a shared container captured from outside.
- The combiner properly merges two containers; it must not drop or duplicate elements.
- The functions do not depend on uncontrolled mutable external state.
- If ordering is required, the result must preserve encounter order according to Collector/Stream rules.

This **does not make the resulting ArrayList thread-safe for later use**. If multiple threads modify the list after collection, the application still needs synchronization or an appropriate data structure.

### 9.2. The Combiner May Not Run in a Sequential Pipeline

Do not test only with a sequential Stream and assume the combiner is correct. A buggy combiner might never be invoked on that execution path. Test cases where data is split into separate branches, run `parallelStream` with independently computable results, and test empty streams.

**Do not use lambda execution order logs as proof of correctness** in parallel: the order and number of container creations can depend on runtime strategy, data size, and source structure.

### 9.3. collect Does Not Mean Collector.CONCURRENT

These are two different concepts:

1. `collect(supplier, accumulator, combiner)` creates and merges containers, and can be used with parallel Streams when the functions satisfy the contract.
2. A `Collector` with the `CONCURRENT` characteristic indicates that the Collector's container can be updated concurrently by the accumulator from multiple threads under the API's conditions.

`Collectors.toConcurrentMap` and `groupingByConcurrent` are examples that create collectors for concurrent structures in appropriate situations. However, **do not manually declare `Collector.Characteristics.CONCURRENT`** for an accumulator using a regular `ArrayList` or `HashMap` and hope the runtime synchronizes it. If this characteristic is declared, the accumulation logic must genuinely support concurrent updates according to the contract.

A Collector having `UNORDERED` is also not the same as a Map or Set output “happening to print out of order”. Collector characteristics are hints for the runtime that affect optimization conditions; understand them thoroughly before defining a custom Collector.

### 9.4. Associativity and Data Ordering

`List.addAll` and per-group summation have the properties needed to merge partial results when grouped properly. However, not every mutation on a mutable object is safe: for example, a combiner subtracting `left.count -= right.count` will yield wrong results under different groupings.

If you want a specific output order, `LinkedHashSet`/`LinkedHashMap` and an ordered source can be part of the design. For a Map ordered by key comparator, use `TreeMap` as in the main program. If you only need totals, do not rely on branch merge order.

## 10. Stream.collect() Does Not Replace Resource Management

`collect` triggers the pipeline, but **does not automatically close all source Streams backed by I/O resources**. For example, `Files.lines(path)` can keep a file open. When collecting data from a file:

```java
// Illustration: path is a declared java.nio.file.Path;
// the enclosing method must handle/declare IOException.
try (Stream<String> lines = Files.lines(path)) {
    List<String> content = lines
            .filter(s -> !s.isBlank())
            .collect(Collectors.toList());
}
```

`try-with-resources` is what guarantees closing the Stream. Do not assume the terminal operation `collect` implies `close()`.

**Do not collect an infinite Stream into an infinite list**: `Stream.generate(...)` creates a semantically unbounded source, so `collect(toList())` without a stopping condition may run forever or run out of memory. Use `limit` or an appropriate stopping strategy before collecting.

If you only need **statistics**, you can avoid retaining all elements by collecting into a small statistics object. This is a key design benefit of mutable reduction.

## 11. Nulls, Exceptions, and Correctness

### 11.1. Nulls in the Input Stream

A `Stream<String>` can contain `null` elements if the source allows them. `ArrayList::add` accepts null; however, an accumulator calling `value.length()` will throw a `NullPointerException` if `value` is null.

```java
ArrayList<String> values = Stream.of("A", null, "B")
        .collect(ArrayList::new, ArrayList::add, ArrayList::addAll);
// [A, null, B]
```

If null is invalid data, validate it, filter it intentionally, or report an error. Do not simply pick an accumulator that silently ignores nulls when business logic requires detecting missing data.

### 11.2. Supplier, Accumulator, and Combiner Can Throw Runtime Exceptions

If the accumulator throws `IllegalArgumentException` or another error, the terminal operation may terminate abnormally. Changes **already made to external objects** do not automatically roll back. Do not use mutable collect as a database transaction; design separate error-handling and compensation policies.

`Supplier.get()` and `BiConsumer.accept()` do not declare checked exceptions. If the accumulator calls an API that throws `IOException`, handle it inside the callback, translate the exception type according to application rules, or separate I/O operations from the collection step.

### 11.3. Null Containers and Result Types

The supplier must return an appropriate container. `() -> null` can cause errors in the accumulator/combiner and violate the expected contract. A `Collector` with a finisher must not arbitrarily return null if callers do not accept it; define the result contract clearly.

When the result is a Map, the key mapper may produce duplicate keys. If you use `toMap` without a merge function, duplicate keys may throw `IllegalStateException`. If the goal is accumulation, use the `toMap` overload with a merge function or `groupingBy` with an appropriate downstream collector.

### 11.4. Numeric Overflow and Large Data

In the sample `Stats`, count, units, and revenue use `long`. However, `long` still has limits. If data can exceed its range, use overflow-checked arithmetic, `BigInteger`, or `BigDecimal` as required by business logic, rather than assuming `collect` results are automatically arithmetic-safe.

Especially for currency, avoid `double` if exactness to small units or specific rounding rules are required; the sample data uses **cents as `long`** for easy verification.

## 12. When to Use Which Approach?

| Need | Suitable approach | Notes |
| --- | --- | --- |
| Read-only list, no modification needed | `stream.toList()` | Unmodifiable List, Java 16+ |
| Need a mutable ArrayList | `collect(toCollection(ArrayList::new))` | Explicitly states result type |
| Want to understand or customize List add/merge | `collect(ArrayList::new, List::add, List::addAll)` | Three explicit functions |
| Need a deduplicated Set of a specific type | `collect(toCollection(LinkedHashSet::new))` | Can preserve insertion order |
| Need a Map of sums by key | `groupingBy(..., summingInt(...))` | Usually clearer than manual Map merging |
| Need sum, product, min/max | `reduce(...)` or primitive `sum/min/max` | Reduced value, no large container needed |
| Need multiple statistics in a single pass | `summaryStatistics()` or custom mutable collector | Can avoid retaining all elements |
| Need a joined string with a delimiter | `Collectors.joining(delimiter)` | Handles empty strings semantically |
| Need an immutable record output | Collector with finisher or collect then convert | Keep accumulator internal, public result immutable |
| Need to update a shared cache/database | Dedicated synchronized/transactional API | Do not turn collect into a side-effect tool |

A practical rule of thumb: **use a standard Collector if it expresses your need accurately; write a custom mutable collect only when you need custom accumulation rules or are learning the API mechanics**. Code written with short lambdas is not automatically correct when run in parallel.

## 13. Common Mistakes

1. **Supplier returning the same mutable container** on every call → shared state, wrong results when combining, and potential race conditions.
2. **Forgetting the combiner** or having a combiner that does not add the right container's data → bug only surfaces when merging parts.
3. **Combiner mutating an external object instead of the received container** → wrong result, violates contract.
4. **Using `reduce` to `add` into an identity ArrayList** → violates the reduction model; use `collect`.
5. **Assuming `Collectors.toList()` is always mutable** → not guaranteed by the API; use `toCollection(ArrayList::new)`.
6. **Assuming `Stream.toList()` is mutable** → it is actually unmodifiable.
7. **Sharing an external ArrayList or HashMap across parallel accumulators** → not automatically thread-safe.
8. **Putting side effects like sending emails inside the accumulator** → execution timing and threads depend on the pipeline; no transaction guarantees.
9. **Forgetting to merge all statistics fields** → count, sum, or other metrics may be wrong.
10. **Using `StringBuilder.length()` to infer element count** when elements can be empty strings → wrong delimiters.
11. **Forgetting empty sources** → Supplier must still create a meaningful empty state; do not assume the accumulator ran if there are no elements.
12. **Confusing collect with resource closing** → terminal operation does not auto-close file/network Streams.
13. **Assuming fixed output order when the source is unordered** → choose clear data structures and ordering rules.
14. **Forgetting potential numeric overflow or parsing errors** → corrupts statistics even if collect follows the contract.
15. **Assuming every Collector is CONCURRENT** → only collectors that declare and properly implement the characteristic support concurrent accumulation.

## 14. Practice Exercises

**Exercise 1.** Create an `ArrayList<Integer>` from `Stream.of(2, 4, 6)` using the three-argument collect. Clearly state the roles of `supplier`, `accumulator`, and `combiner`.

**Exercise 2.** Given `Stream.of("java", "api", "java")`, create a `LinkedHashSet<String>`. Why is `LinkedHashSet` beneficial if first-appearance order is needed?

**Exercise 3.** Given `record Item(String group, int count) {}`, create a `TreeMap<String,Integer>` summing `count` by group using the three-argument collect. Write the combiner so that two partial Maps with overlapping keys still produce the correct sum.

**Exercise 4.** Define a `Summary` class with `long count` and `long sum`. Write `add(int value)` and `merge(Summary other)`; use `collect(Summary::new, ..., ...)` and state the result when the source is empty.

**Exercise 5.** Why is `() -> sharedList` an unsuitable supplier for parallel collect? Even if `Collections.synchronizedList` is used, what issue remains regarding the identity/combiner contract?

**Exercise 6.** Compare `stream.collect(ArrayList::new, ArrayList::add, ArrayList::addAll)` and `stream.collect(Collectors.toCollection(ArrayList::new))` in terms of result type and clarity of intent.

**Exercise 7.** If `combiner` only performs `left.addAll(left)` instead of `left.addAll(right)`, what bug can occur when running in parallel?

**Exercise 8.** Should you use `reduce(new ArrayList<>(), ...)` to create a List and mutate the identity in the accumulator? Why or why not?

**Exercise 9.** For a source of strings that may contain `""`, choose `Collectors.joining(" | ")` instead of using `StringBuilder.length()` to detect an empty list. Why?

**Exercise 10.** You need to compute total rows, total units, and total revenue from a `Stream<Sale>`. When is a custom mutable accumulator preferable to `toList()` followed by another loop?

**Exercise 11.** You run a collect operation on `parallelStream()` and find that the result is missing some elements. Which components should you check first? Should you assume the runtime has a bug?

**Exercise 12.** A Stream read from `Files.lines(path)` is collected into a List. Why is `try-with-resources` still needed? How can memory usage be reduced if you only need count and sum?

### Answer Hints

1. `Stream.of(2,4,6).collect(ArrayList::new, ArrayList::add, ArrayList::addAll)` → `[2,4,6]`; the three components respectively create a new List, add an element, and merge Lists.
2. `collect(LinkedHashSet::new, LinkedHashSet::add, LinkedHashSet::addAll)` → `java`, `api` in order, without duplicates.
3. Supplier `TreeMap::new`, accumulator `map.merge(item.group(), item.count(), Integer::sum)`, combiner iterates `right.forEach((k,v) -> left.merge(k,v,Integer::sum))`.
4. `count++`, `sum += value` in accumulator; combiner adds both fields; an empty Stream returns a summary with count and sum equal to 0.
5. The same container is shared, so it is no longer a fresh neutral container; `synchronized` alone does not fix the bug of merging a container with itself.
6. Both can create a mutable `ArrayList`; the standard Collector form is usually shorter and clearer, while the three-argument form lets you customize each step.
7. It may duplicate data from the left branch and lose data from the right branch.
8. No; a shared mutable identity violates `reduce` rules; use `collect`.
9. `length() == 0` is not enough to tell whether an empty element has already been added; `joining` handles delimiter semantics per element.
10. When only a few totals are needed, a custom accumulator avoids retaining all `Sale` objects, reduces memory usage, and avoids re-traversing a hard-to-reuse source.
11. Check that the supplier provides a fresh container, the accumulator updates properly, the combiner merges properly, and check side effects and ordering compatibility before blaming the runtime.
12. `collect` does not automatically `close()` the I/O source; use try-with-resources. If only statistics are needed, collect into a small accumulator instead of a large List.

## Conclusion

**Mutable reduction with `collect()`** consists of three core tasks: **creating a new container**, **adding each element to the container**, and **merging partial containers**. The `collect(supplier, accumulator, combiner)` overload expresses these three tasks directly; the `collect(Collector)` overload packages them together with an optional finisher and characteristics to produce various result types.

Clearly distinguish `collect` from `reduce`: **collect is suited for accumulating into a mutable container managed by the collection operation; reduce is suited for using an identity value and an associative merge operation to produce a single value**. Writing an independent supplier, a properly scoped accumulator, and a contract-compliant combiner is the key to keeping pipelines accurate in both sequential and parallel execution.
