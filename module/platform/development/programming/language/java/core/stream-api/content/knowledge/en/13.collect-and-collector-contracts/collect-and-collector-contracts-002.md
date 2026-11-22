# Using collect with supplier, accumulator, and combiner

## 1. From Stream to a mutable result

In the **Java Stream API**, we build a pipeline consisting of a data source, intermediate operations like `filter` and `map`, and trigger execution with a terminal operation. When you want to **accumulate elements into a mutable result container**, `collect` is a key choice.

In the **Collect Mechanism and Collector** chapter, this lesson focuses on the **three-parameter** overload:

```java
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner
);
```

This is a method on `Stream<T>`. Meaning of the three components:

- **`supplier`:** creates a new result container, such as an `ArrayList` or `HashMap`.
- **`accumulator`:** puts one element from the source into that result container.
- **`combiner`:** merges the contents of two result containers, especially useful when the pipeline is processed in parallel.

Together, the three functions perform **mutable reduction**: accumulating by modifying the result container, rather than having to create a new result object after every element.

Short example:

```java
import java.util.ArrayList;
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

List<String> result = words.stream()
        .collect(
                ArrayList::new,                  // supplier
                (list, word) -> list.add(word),  // accumulator
                (left, right) -> left.addAll(right) // combiner
        );

System.out.println(result); // [Java, Stream, API]
```

The result `result` is a new list; the source `words` is not modified. You can write this more concisely with `Collectors.toList()` or `Collectors.toCollection(ArrayList::new)`. The value of the three-parameter form lies in understanding the accumulation mechanism clearly and when a custom container is needed for the problem.

**After this lesson, you will be able to:**

1. Accurately explain the roles and types of the three `collect` parameters.
2. Write mutable reductions collecting into a `List`, `StringBuilder`, or `Map`.
3. Design a `combiner` that works properly for both sequential and parallel pipelines.
4. Distinguish three-parameter `collect`, `collect(Collector)`, and `reduce`.
5. Avoid shared-container bugs, wrong merging, side effects on the source, and incorrect assumptions about execution order.

The main examples use Java 17+ for `record`, `List.of`, and `Stream.toList()`. The three-parameter overload of `collect` has been available since Java 8.

## 2. Type contract of the three functions

Suppose the source is `Stream<T>` and you want to return a container of type `R`:

| Parameter | Functional interface | What does it accept? | What does it return? |
| --- | --- | --- | --- |
| `supplier` | `Supplier<R>` | No arguments | A new `R` object |
| `accumulator` | `BiConsumer<R, ? super T>` | Container `R` and source element `T` | `void` |
| `combiner` | `BiConsumer<R, R>` | Two result containers of the same type `R` | `void` |

Note that **the accumulator and combiner do not return a new container**. They must mutate the container passed in. The final result of `collect` has type `R`.

```text
Stream<T> ── filter/map ── collect(...)
                               │
             supplier() ───────┤ create R
                               │
             accumulator(R,T) ─┤ add T elements to R
                               │
             combiner(R,R) ────┤ merge partial results
                               ▼
                            result R
```

For example, with `Stream<String>` collecting into `ArrayList<String>`:

```java
ArrayList<String> items = words.stream()
        .collect(
                () -> new ArrayList<String>(),
                (list, element) -> list.add(element),
                (destination, source) -> destination.addAll(source)
        );
```

`destination` and `source` in the combiner **are both partial result containers**, not the Stream's source collection.

## 3. Supplier must provide a new container

`supplier` is allowed to be called multiple times when the framework needs to create partial results. A simple sequential pipeline usually uses just one container; in parallel execution, there may be multiple independent containers. **Do not rely on a fixed number of supplier invocations.**

Correct way:

```java
List<Integer> numbers = List.of(1, 2, 3, 4);

List<Integer> copy = numbers.parallelStream()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );

System.out.println(copy); // [1, 2, 3, 4]
```

Each time `ArrayList::new` runs, it creates an independent list. As a result, tasks can accumulate separately and merge later.

**Wrong way: sharing an external list.**

```java
List<Integer> shared = new ArrayList<>();

// WRONG: supplier returns the same shared object on every call.
List<Integer> invalid = numbers.parallelStream()
        .collect(
                () -> shared,
                List::add,
                List::addAll
        );
```

Here multiple tasks may concurrently mutate the same `ArrayList`, which does not support concurrent updates. Worse, the combiner might merge **a container with itself**, causing duplicate elements or incorrect behavior. Even if the program seems to run sequentially, this supplier does not satisfy the requirement of a fresh independent container for reduction to work properly in all modes.

**Rule:** the supplier must produce a new `R` object each time an accumulation container is needed. Do not keep partial results in a global variable to coordinate manually.

## 4. Accumulator modifies the result, not the source

`accumulator` takes a container `R` and an element `T`. It processes **one element** at a time and adds the necessary information into `R`.

```java
List<String> raw = List.of(" An ", "  Bình", "Chi  ");

List<String> normalized = raw.stream()
        .collect(
                ArrayList::new,
                (result, name) -> result.add(name.strip()),
                (left, right) -> left.addAll(right)
        );

System.out.println(normalized); // [An, Bình, Chi]
```

In the accumulator, `result.add(...)` modifies **the new result list**, not `raw`. This complies with the Stream non-interference contract.

However, ordinary data transformation tasks should sit in `map` so the pipeline expresses its intent clearly:

```java
List<String> normalizedByPipeline = raw.stream()
        .map(String::strip)
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
```

Both are valid approaches; the second clearly separates **element transformation** from **result accumulation**.

Do not modify the source directly inside the accumulator:

```java
List<String> mutableSource = new ArrayList<>(List.of("A", "B"));

// WRONG: traversing mutableSource while also adding to the source itself.
List<String> wrong = mutableSource.stream()
        .collect(
                ArrayList::new,
                (result, value) -> {
                    result.add(value);
                    mutableSource.add("X");
                },
                List::addAll
        );
```

The snippet above can throw `ConcurrentModificationException` or exhibit unreliable behavior. Only mutate the container `R` created by the supplier; update the source in another stage after the terminal operation finishes if business logic requires it.

## 5. Combiner is required for correct parallel results

With a parallel Stream, the framework may split the source into multiple parts:

```text
Ordered source: [A, B, C, D]
              /             \
        [A, B]               [C, D]
          |                    |
       supplier()           supplier()
          |                    |
       add(A), add(B)       add(C), add(D)
          |                    |
      left=[A,B]          right=[C,D]
              \             /
               combiner(left, right)
                        |
                  [A,B,C,D]
```

This is a **logical diagram**, not a guarantee that the Stream always splits into exactly two parts or calls the combiner in this exact sequence. Parallel execution can split and combine across many branches; the combiner might not even be called in a particular execution.

With a list:

```java
List<Integer> output = List.of(1, 2, 3, 4, 5).parallelStream()
        .collect(
                ArrayList::new,
                (list, item) -> list.add(item),
                (left, right) -> left.addAll(right)
        );

System.out.println(output); // [1, 2, 3, 4, 5]
```

When the source has an encounter order like `List`, accumulating with `add` and combining with `addAll` under a compatible contract preserves that logical order. The exact timing of when threads execute the accumulator **is not guaranteed**.

### Combiner must merge into the target object

In this overload, the combiner receives two results `left` and `right` and **mutates `left`** to hold both. For example:

```java
(left, right) -> left.addAll(right)
```

The corresponding method reference is `List::addAll` or `ArrayList::addAll`, depending on type inference. Although `addAll` returns `boolean`, Java allows ignoring that return value when used in a `BiConsumer` context whose return type is `void`.

**You cannot simply reassign the parameter variable:**

```java
// SEMANTICALLY WRONG: only reassigns a local variable, does not merge contents into left.
(left, right) -> {
    left = new ArrayList<>(right);
}
```

The `left` variable in the lambda is a local parameter; reassigning it does not change the container managed by the Stream. The combiner must directly add data into the target container or use an accumulation structure with the proper protocol.

## 6. Three rules to keep: independence, identity, and associativity

For mutable reduction to work properly across different source splits, `supplier`, `accumulator`, and `combiner` must be **compatible**.

**1. Independent containers.** Each supplier call creates a new `R`. The accumulator must not grab a shared external collection to write to instead of the `R` passed in.

**2. Empty partial result is the identity element.** Merging a container `R` with an empty result freshly produced by the supplier must not alter the semantic result:

```text
combine(result, empty) ~ result
```

The `~` symbol denotes **equivalence in result content**, not requiring the same object reference in every accumulation style.

**3. Combining must be associative.** How groups are parenthesized must not change the logical result:

```text
combine(combine(A, B), C) ~ combine(A, combine(B, C))
```

For `List`, concatenating lists in order is associative: `[A] + [B] + [C]` does not depend on parenthesization. For integer addition within valid bounds, summing parts is also associative.

These rules connect to the accumulator: **accumulating one more element into a result** must be equivalent to **merging that result with an independent container holding only the new element**. For example:

```text
accumulate([A,B], C) ~ combine([A,B], [C])
=> [A,B,C]
```

If the accumulator appends elements to the end of the list while the combiner prepends elements to the front, parallel results can scramble the order. If the accumulator adds counts while the combiner takes `max` instead of adding, the result depends on task splitting and will be wrong.

### Example of a broken combiner even though sequential pipeline looks fine

```java
List<Integer> source = List.of(1, 2, 3, 4);

// WRONG: combiner ignores right.
List<Integer> incorrect = source.parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                (left, right) -> { }
        );
```

In a sequential run, the accumulator may add all four elements to a single list, hiding the bug. In parallel, partial results are dropped because the combiner fails to merge `right`. **Do not use a passing sequential run to verify that a combiner is correct.**

## 7. Example with StringBuilder: joining strings without creating a new string every step

`StringBuilder` is a mutable container useful for illustrating mutable reduction:

```java
import java.util.List;
import java.util.Locale;

List<String> codes = List.of("a1", "b2", "c3");

StringBuilder builder = codes.stream()
        .map(code -> code.toUpperCase(Locale.ROOT))
        .collect(
                StringBuilder::new,
                (target, code) -> target.append(code).append(";"),
                (left, right) -> left.append(right)
        );

System.out.println(builder.toString()); // A1;B2;C3;
```

The supplier creates a new `StringBuilder`; the accumulator appends data; the combiner appends the contents of two builders into the left builder. `StringBuilder` is **not thread-safe**, but the proper style uses independent containers, so multiple threads do not need to write to the same builder concurrently.

Do not use a global builder:

```java
StringBuilder shared = new StringBuilder();

// WRONG with parallelStream: all branches share the same shared instance.
String text = codes.parallelStream()
        .collect(
                () -> shared,
                (target, code) -> target.append(code),
                (left, right) -> left.append(right)
        )
        .toString();
```

In application code, if the goal is simply joining strings with a delimiter, `Collectors.joining(";")` is usually cleaner and avoids managing delimiters manually:

```java
String joined = codes.stream()
        .map(code -> code.toUpperCase(Locale.ROOT))
        .collect(java.util.stream.Collectors.joining(";"));

System.out.println(joined); // A1;B2;C3
```

## 8. Example with Map: summing quantities by key

Suppose each record contains a department code and a number of item packages. The goal is to create a Map of total quantities per department.

```java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

record Shipment(String department, int items) {}

List<Shipment> shipments = List.of(
        new Shipment("A", 3),
        new Shipment("B", 5),
        new Shipment("A", 2),
        new Shipment("C", 4)
);

Map<String, Integer> totals = shipments.parallelStream()
        .collect(
                HashMap::new,
                (map, shipment) -> map.merge(
                        shipment.department(),
                        shipment.items(),
                        Integer::sum
                ),
                (left, right) -> right.forEach(
                        (department, items) ->
                                left.merge(department, items, Integer::sum)
                )
        );

System.out.println(totals);
// {A=5, B=5, C=4} (key order is not guaranteed)
```

Analysis:

1. **Supplier:** `HashMap::new` creates a new Map for each partial result.
2. **Accumulator:** `Map.merge` adds the item count to the department key, creating a new key if it does not yet exist.
3. **Combiner:** iterates over each key/value pair of `right` and adds it into `left` using **the same addition rule**.
4. **Terminal operation:** returns an aggregated `Map<String, Integer>`; does not modify `shipments`.

Addition is used in both the accumulator and combiner, so they are compatible. If the combiner used `left.putAll(right)`, overlapping department keys would overwrite instead of summing, producing wrong totals in parallel runs.

`HashMap` does not guarantee key order. If business logic requires sorted display, sort explicitly where the result is consumed, rather than guessing order from when parallel branches finish.

### When should you use a built-in Collector?

For the problem above, the library offers a shorter expression:

```java
Map<String, Integer> byDepartment = shipments.stream()
        .collect(java.util.stream.Collectors.groupingBy(
                Shipment::department,
                java.util.stream.Collectors.summingInt(Shipment::items)
        ));
```

For common grouping, counting, summing, or collecting tasks, `Collectors.groupingBy`, `counting`, `summingInt`, and other built-in collectors are usually easier to read and already define an appropriate combining mechanism. The three-parameter overload is useful when the container and accumulation rules truly need direct control.

## 9. Comparing three-parameter collect with collect(Collector)

`Stream` has two commonly used forms of `collect`:

```java
// Mutable reduction with three functions.
<R> R collect(
        Supplier<R> supplier,
        BiConsumer<R, ? super T> accumulator,
        BiConsumer<R, R> combiner);

// Collecting through a Collector containing the full set of rules.
<R, A> R collect(Collector<? super T, A, R> collector);
```

In the three-parameter form, the accumulation container type `R` is also the returned type. With `Collector<T, A, R>`, **`A` is the intermediate accumulation type** and **`R` is the final result type**; they can differ thanks to the **finisher**.

| Aspect | `collect(supplier, accumulator, combiner)` | `collect(collector)` |
| --- | --- | --- |
| Logic specification | Passes three functions directly to the terminal operation | Encapsulates inside a `Collector` object |
| Intermediate container | Same type as result `R` | `A` can differ from `R` |
| Finisher | No separate finisher parameter | Can convert `A` to `R` in the final step |
| Partial merging | `BiConsumer<R, R>`, merges by mutating the container | `BinaryOperator<A>`, returns the merged container |
| Characteristics | Not declared directly | Has `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH` per collector contract |
| Reusability | Three functions usually written at the call site | Collector can be defined once and reused across pipelines |

An equivalent collector for collecting into an `ArrayList`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

List<String> copied = words.stream()
        .collect(Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        ));
```

**Note the combiner difference:** in `Collector.of`, it has type `BinaryOperator<A>` and **must return** the combined result. In three-parameter `collect`, the combiner is `BiConsumer<R,R>` and **returns no value**.

When you want to convert a `StringBuilder` to a `String` at the end of collection, the `Collector.of` form with a finisher is a fitting tool:

```java
String result = words.stream()
        .collect(Collector.of(
                StringBuilder::new,
                (builder, word) -> builder.append(word),
                (left, right) -> {
                    left.append(right);
                    return left;
                },
                StringBuilder::toString
        ));
```

With three-parameter `collect`, you can receive the `StringBuilder` and call `toString()` outside; there is no finisher argument in that `collect` call itself.

Do not arbitrarily assign `CONCURRENT` or `UNORDERED` when building a custom collector if the accumulator or result semantics do not meet the requirements. Declaring wrong characteristics can lead to incorrect behavior when running in parallel.

## 10. collect and reduce: where do they differ?

`reduce` is generally suited for **value reduction** to produce a new result according to combining rules, whereas three-parameter `collect` is suited for **mutating a new result container**:

```java
List<Integer> values = List.of(2, 3, 5);

int sum = values.stream()
        .reduce(0, Integer::sum); // 10

List<Integer> copy = values.stream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
```

For an integer sum, `mapToInt(Integer::intValue).sum()` or `reduce` expresses the goal directly. There is no need to build an `ArrayList` just to compute a sum.

**Common anti-pattern:** using `reduce` with a mutable list as the identity and mutating it in the accumulator:

```java
// WRONG under the reduction contract, especially dangerous in parallel.
List<Integer> bad = values.parallelStream()
        .reduce(
                new ArrayList<Integer>(),
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

With `reduce`, identity is a value used across computation parts, and reduction must not mutate a shared identity. Updating this `ArrayList` can corrupt the result. **For mutable accumulation tasks, use `collect` with a supplier creating new containers.**

## 11. Lazy pipelines and the non-interference requirement

`collect` is a **terminal operation**: it triggers the intermediate operations built before it.

```java
List<String> source = List.of("a", "bb", "ccc");

Stream<String> pipeline = source.stream()
        .filter(word -> word.length() >= 2)
        .map(String::toUpperCase);

// Source has not been traversed by the pipeline at the lines above.
List<String> collected = pipeline.collect(
        ArrayList::new,
        List::add,
        List::addAll
);

System.out.println(collected); // [BB, CCC]
```

After `collect` has completed, `pipeline` must not be reused for another terminal operation. To process again, create a new Stream from `source`.

The `supplier`, `accumulator`, and `combiner` functions are not the place to update a mutable source being traversed; they should only create/accumulate/combine **the result container**. With sources like `ArrayList` and `HashMap`, mutating the source during traversal violates non-interference. In parallel processing, also avoid shared state without an appropriate synchronization contract.

When flattening, grouping, or generating reports, you can pair `filter`/`map` with `collect`; for concurrent sources or I/O sources, read the lifecycle and consistency contract of each source carefully. `collect` does not automatically turn a mutating source into an atomic snapshot of data.

## 12. Ordering, memory, and performance

### Result ordering

With a Stream that has an encounter order, a `List` collection using compatible `add` and `addAll` can preserve source order even when split for parallel execution. However, if the source is unordered, such as certain `Set` implementations, do not assume the resulting list has a stable order.

For a `HashMap` accumulated by groups, key iteration order is not guaranteed, regardless of how many times the supplier or combiner is called.

### Memory cost

`collect` into a `List` or `Map` generally requires storing the result in memory. If you only need an aggregate number, `count`, `sum`, `reduce`, or `summaryStatistics` can avoid building a large result set.

In a parallel Stream, there may be **multiple temporary accumulation containers** before merging. For example, a `HashMap` per branch must hold temporary keys, adding memory and combiner overhead. Do not assume by default that `parallelStream()` is faster.

### Computationally expensive combiners

If a combiner copies all data on every merge or always creates a new collection, combining can incur significant allocation and copying. For `ArrayList`, `left.addAll(right)` is generally preferable to repeatedly creating a new list containing both old lists.

### Precision and associativity

Not every operation combines with exact precision. With `double`, addition has rounding error; changing how additions are grouped can cause the last digits to differ. With `int` and `long`, summing beyond the numeric type's range can overflow. When collecting monetary data or needing exact sums, choose `BigDecimal` or an appropriate data type and policy, and ensure the accumulator and combiner use **the same arithmetic rules**.

## 13. Complete business example: aggregating paid orders

The Java 17+ example below demonstrates collecting into both a list and a Map, properly using the three parameters. Problem: filter paid orders, normalize customer codes, get the list of valid transactions, and compute total product quantity per customer.

```java
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class ThreeArgumentCollectDemo {
    record Order(String id, String customer, int quantity, boolean paid) {}
    record PaidOrder(String id, String customer, int quantity) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("O-01", " An ", 3, true),
                new Order("O-02", "Bình", 8, false),
                new Order("O-03", " Chi ", 4, true),
                new Order("O-04", "an", 2, true)
        );

        List<PaidOrder> paidOrders = orders.stream()
                .filter(Order::paid)
                .map(order -> new PaidOrder(
                        order.id(),
                        order.customer().strip().toUpperCase(Locale.ROOT),
                        order.quantity()
                ))
                .collect(
                        ArrayList::new,
                        List::add,
                        List::addAll
                );

        Map<String, Integer> totalsByCustomer = paidOrders.parallelStream()
                .collect(
                        HashMap::new,
                        (map, order) -> map.merge(
                                order.customer(),
                                order.quantity(),
                                Integer::sum
                        ),
                        (left, right) -> right.forEach(
                                (customer, quantity) ->
                                        left.merge(customer, quantity, Integer::sum)
                        )
                );

        System.out.println(paidOrders);
        // [PaidOrder[id=O-01, customer=AN, quantity=3],
        //  PaidOrder[id=O-03, customer=CHI, quantity=4],
        //  PaidOrder[id=O-04, customer=AN, quantity=2]]

        System.out.println(totalsByCustomer);
        // {CHI=4, AN=5} or the same key/value pairs in a different order

        System.out.println(orders.size()); // 4: source is not modified.
    }
}
```

Technical decisions in the example:

1. `filter` selects paid orders to avoid processing unnecessary orders.
2. `map` creates a new `PaidOrder`, containing only fields needed for reporting.
3. `collect(ArrayList::new, List::add, List::addAll)` builds the result list in encounter order.
4. The second collection uses `HashMap::new` for an independent container in each branch.
5. Both accumulator and combiner use `Integer::sum`, so quantities for customers with multiple orders are not lost.
6. `orders` remains intact. Production software must check for missing data, valid customer codes, and quantity ranges before computing.

In systems requiring large exact totals, replace `int` with a numeric type of sufficient range and design explicit overflow rules. For problems with multiple groups or complex values, a custom `Collector` with a finisher or built-in collectors may be easier to reuse.

## 14. Common errors

| Symptom | Cause | Solution |
| --- | --- | --- |
| Wrong result when switching from `stream()` to `parallelStream()` | Combiner ignores or wrongly merges partial results | Use the same accumulation rule, verify identity and associativity. |
| List exhibits duplicate elements | Supplier returns the same collection or combiner merges a collection with itself | Every supplier must create a new, independent container. |
| `ConcurrentModificationException` | Accumulator modifies the source collection being traversed | Only mutate the result container; update the source after the terminal operation. |
| Combiner creates a new collection but result does not change | `BiConsumer<R,R>` does not take a return value | Mutate target container `left` directly. |
| Map has wrong totals in parallel run | Combiner uses `putAll`, losing values for shared keys | Use `merge` with addition or the proper merge rule. |
| Keeping state in an external variable to count invocations | No guarantee on invocation count or callback order | Use the supplier's container `R` and the terminal operation result. |
| Mistakenly assuming result always preserves order | Unordered source or accumulation operation does not preserve order | Determine encounter order and result requirements before choosing structures. |
| Wanting to convert result type directly in three-parameter `collect` | This overload has no finisher | Use `collect(Collector)` with a finisher or convert after collecting. |
| Using `reduce` with a mutable `ArrayList` identity | Reduction violates identity and shared mutation contracts | Use mutable reduction via `collect`. |
| Parallel is slower than sequential | Too many partial containers and combiner overhead | Benchmark in practice, simplify accumulation, consider built-in collectors. |

## 15. Practice exercise

Given a list of scores:

```java
record Score(String group, int value, boolean valid) {}

List<Score> scores = List.of(
        new Score("A", 8, true),
        new Score("B", 5, true),
        new Score("A", 7, true),
        new Score("C", 2, false)
);
```

**Requirements:**

1. Use `collect(supplier, accumulator, combiner)` to collect valid scores into a `List<Integer>`.
2. Use three-parameter `collect` to create a `Map<String, Integer>` storing the total score of each group.
3. Try switching the Stream to `parallelStream()`. Explain why the combiner must merge values for matching groups.
4. Intentionally replace the Map combiner with `left.putAll(right)` and analyze why the result can be wrong.
5. Rewrite task 2 using `Collectors.groupingBy` and `Collectors.summingInt`.

**Reference solution:**

```java
List<Integer> validScores = scores.stream()
        .filter(Score::valid)
        .map(Score::value)
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
// [8, 5, 7]

Map<String, Integer> totals = scores.parallelStream()
        .filter(Score::valid)
        .collect(
                HashMap::new,
                (map, score) ->
                        map.merge(score.group(), score.value(), Integer::sum),
                (left, right) -> right.forEach(
                        (key, value) -> left.merge(key, value, Integer::sum)
                )
        );
// A=15, B=5 (key order is not guaranteed)

Map<String, Integer> totalsWithCollector = scores.stream()
        .filter(Score::valid)
        .collect(java.util.stream.Collectors.groupingBy(
                Score::group,
                java.util.stream.Collectors.summingInt(Score::value)
        ));
```

Explanation for task 4: `putAll` keeps only one value for key `A` if `A` appears in two different containers. Business rules require **summing** scores for `A`, so `merge(key, value, Integer::sum)` is needed. Do not rely on small data or a single parallel run to prove a combiner right/wrong; consider all valid ways the source can be split.

**Self-extension:** Write a collect operation that creates a list of group codes in encounter order while removing duplicates. Compare this with `distinct()` and `Collectors.toCollection(LinkedHashSet::new)`: which expresses the goal more clearly? When using a set for deduplication, explain clearly the ordering properties of the chosen Set type.

## Takeaways

`Stream.collect(supplier, accumulator, combiner)` performs **mutable reduction**: the supplier creates a new container, the accumulator adds each element to the container, and the combiner merges partial results. The combiner must mutate the target container, be compatible with the accumulator, and satisfy the identity and associativity rules so task splitting does not alter the result. Callbacks must not modify the source being traversed or depend on shared mutable state.

When you need a mutable collection, Map, or buffer, the three-parameter overload gives direct control over the mechanism. For common tasks or when a finisher and characteristics are required, `collect(Collector)` and built-in `Collectors` are usually clearer. Prioritize correctness of the combining operation first, and only then measure gains from parallel processing.
