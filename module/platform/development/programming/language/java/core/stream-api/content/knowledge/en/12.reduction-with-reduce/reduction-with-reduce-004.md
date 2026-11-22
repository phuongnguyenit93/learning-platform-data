# Using Three-Parameter reduce to Change the Result Type

In the **Reduction with reduce** chapter of the **Java Stream API**, we have become familiar with declarative pipelines: taking elements from a source, transforming them with `map` or filtering with `filter`, and using a terminal operation to compute a result. `reduce` is the operation used to combine multiple elements into a single value according to a combining rule.

When the input element type and the result type **differ**, the **three-parameter** `reduce` overload is particularly useful. We can transform a `Stream<String>` into a total length of type `Integer`, or transform a `Stream<Sale>` into an `InvoiceStats` summary containing line count, total units, and exact total amount. For the result to be correct in both sequential and parallel execution, the three arguments `identity`, `accumulator`, and `combiner` must obey a strict contract.

This lesson explains that contract, implements a complete example, identifies common mistakes, and clarifies when to use `reduce` versus `collect`.

## 1. Three overloads of reduce and the meaning of the result type

In `java.util.stream.Stream<T>`, the three overloads of `reduce` can be read as follows:

~~~java
// 1. Without identity: result remains type T, and may be absent.
Optional<T> reduce(BinaryOperator<T> accumulator);

// 2. With identity: result remains type T.
T reduce(T identity, BinaryOperator<T> accumulator);

// 3. With identity and combiner: result can have type U different from T.
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

`T` is the **type of elements flowing through the Stream**, while `U` is the **accumulated result type**. With the three-parameter overload, `T` and `U` can differ; if they are the same it still works, but the main benefit is supporting type-changing aggregations.

| Component | Function / value type | Responsibility |
| --- | --- | --- |
| `identity` | `U` | Neutral value, also the result when the source is empty. |
| `accumulator` | `(U, T) -> U` | Takes a partial total and a new Stream element, returning a new partial total. |
| `combiner` | `(U, U) -> U` | Merges two partial totals into one total with the same business meaning. |
| Final value | `U` | Result of the terminal operation after traversal and merging complete. |

Compare:

~~~java
Stream<Integer> numbers = Stream.of(1, 2, 3);

// T = Integer, result is also Integer:
int total = numbers.reduce(0, Integer::sum);
~~~

With a Stream of strings, computing total length requires changing the type:

~~~java
import java.util.List;

List<String> names = List.of("An", "Binh", "Chi");

// T = String, U = Integer.
int totalChars = names.stream()
        .reduce(
                0,
                (sum, name) -> sum + name.length(),
                Integer::sum
        );

System.out.println(totalChars); // 9
~~~

In this snippet `identity = 0`; `accumulator` turns `Integer + String` into an `Integer`; `combiner` adds two integers. You cannot use the two-parameter overload `reduce(0, ...)` directly on `Stream<String>` because then `identity` would have to be a `String`, matching element type `T`.

> **Core point:** The three-parameter overload uses **two combining functions with distinct roles**: folding a `T` into a `U` and merging two `U`s. Even though in sequential execution only the accumulator may appear to be called, the combiner is still a mandatory part of the contract.

## 2. Understanding the execution flow in sequential and parallel modes

With data:

~~~text
["An", "Binh", "Chi"]  -- String (T)
           |
           v
      accumulate
           |
           v
     Total length      -- Integer (U)
~~~

When running sequentially, we can visualize:

~~~text
identity = 0
accumulate(0, "An")   = 2
accumulate(2, "Binh") = 6
accumulate(6, "Chi")  = 9
Result: 9
~~~

When running in parallel, the Stream can split the source into multiple parts. Each part is accumulated independently starting from `identity`, and then the results are merged using `combiner`:

~~~text
Branch A: ["An", "Binh"] -> 0 + 2 + 4 = 6
Branch B: ["Chi"]        -> 0 + 3     = 3

combine(6, 3) -> 9
~~~

That is only **one illustrative split**, not a fixed splitting strategy of the JDK. The number of parts, invocation order, and merging pattern can vary. A correct program must produce the same **result under the contract** regardless of how the work is partitioned.

Parallel execution example:

~~~java
int totalChars = names.parallelStream()
        .reduce(
                0,
                (sum, name) -> sum + name.length(),
                Integer::sum
        );
~~~

Switching to `parallelStream()` does not change the meaning of the result. However, parallel execution should not be assumed faster by default; work that is too small can become slower due to task splitting and merging overhead.

## 3. Mandatory contract of identity, accumulator, and combiner

For a reduction to merge sub-parts safely, the Java Stream API requires the functions to be **non-interfering** with the source, **independent of external mutable state**, and compliant with the proper mathematical relationships.

### 3.1. Identity must be a neutral element of the combiner

For every partial total `u`:

~~~text
combiner(identity, u) = u
~~~

For example, when the result is an integer sum:

~~~java
identity  = 0;
combiner  = Integer::sum;
~~~

Because `0 + u = u`, `0` is a suitable identity. If `10` is used as `identity` just to “pre-add 10”, each parallel branch can add 10, causing the result to change depending on how the work is split.

~~~java
import java.util.List;

List<String> words = List.of("a", "bb");

// Wrong: 10 is not the identity of addition.
int broken = words.parallelStream()
        .reduce(10, (sum, word) -> sum + word.length(), Integer::sum);
~~~

Sequentially, this yields `13`; if split into two branches, each branch starts with `10` and may yield `(10 + 1) + (10 + 2) = 23`. The code **violates the reduce contract**, so the result is not guaranteed.

If you want to add a fixed fee of 10 to the sum, the right way is:

~~~java
int base = 10;
int total = base + words.parallelStream()
        .reduce(0, (sum, word) -> sum + word.length(), Integer::sum);

System.out.println(total); // 13
~~~

### 3.2. Combiner must be associative

For any partial totals `a`, `b`, `c`, we need:

~~~text
combine(combine(a, b), c) = combine(a, combine(b, c))
~~~

Integer addition within valid arithmetic conditions and exact `BigDecimal` addition satisfy this requirement. Adding and then doing **intermediate rounding** may no longer be associative; therefore, do not put rounding inside the combiner if you want an exact total and consistent parallel results.

Associativity **does not mean** commutativity. For example, string concatenation is associative but not commutative: `"ab" + "c"` equals `"a" + "bc"`, whereas `"a" + "b"` differs from `"b" + "a"`. If the operation is order-sensitive, the Stream's *encounter order* must be respected; do not arbitrarily call `unordered()` when the problem requires ordering.

### 3.3. Accumulator and combiner must be compatible

For a partial total `u` and a new element `t`, the contract requires:

~~~text
combine(u, accumulate(identity, t)) = accumulate(u, t)
~~~

Simply put: accumulating element `t` into `u` must match **evaluating that element alone from `identity`** and merging it into `u` via `combiner`.

In the total string length example:

~~~text
combine(5, accumulate(0, "An"))
= combine(5, 2)
= 7

accumulate(5, "An") = 7
~~~

If the accumulator sums lengths while the combiner subtracts or multiplies two totals, parallel branches will merge into an incorrect result:

~~~java
// Wrong: combiner does not share the same semantics as accumulator.
int broken = words.parallelStream()
        .reduce(
                0,
                (sum, word) -> sum + word.length(),
                (left, right) -> left - right
        );
~~~

In a sequential pipeline, this bug can stay hidden because the combiner is not necessarily called. Hence, **passing in sequential mode is not sufficient proof that a three-parameter reduction is correct**.

### 3.4. Do not share mutable state between functions

`accumulator` and `combiner` should operate on independent values, ideally *immutable* ones. Avoid writing into external lists or counters to store totals, because multiple branches may run concurrently.

These principles also apply when combining Streams with `filter`, `map`, custom Spliterators, parallel pipelines, or newer intermediate operations. How work is split can vary, so reduction semantics must never depend on arbitrary invocation order or shared state.

## 4. Practical example: from Sale to InvoiceStats

An invoice consists of multiple line items, each having a product SKU, quantity, and unit price. We want **a single result of a different type from the source**, containing three metrics:

- `lineCount`: number of line items.
- `totalUnits`: total product units.
- `exactAmount`: total amount before rounding.

Use an immutable `record` as the accumulation type `U`.

~~~java
import java.math.BigDecimal;
import java.util.List;

public class InvoiceStatsDemo {

    record Sale(String sku, long quantity, BigDecimal unitPrice) {}

    record InvoiceStats(
            long lineCount,
            long totalUnits,
            BigDecimal exactAmount) {

        static InvoiceStats zero() {
            return new InvoiceStats(0, 0, BigDecimal.ZERO);
        }

        InvoiceStats addSale(Sale sale) {
            BigDecimal lineAmount = sale.unitPrice()
                    .multiply(BigDecimal.valueOf(sale.quantity()));

            return new InvoiceStats(
                    lineCount + 1,
                    totalUnits + sale.quantity(),
                    exactAmount.add(lineAmount)
            );
        }

        InvoiceStats merge(InvoiceStats other) {
            return new InvoiceStats(
                    lineCount + other.lineCount(),
                    totalUnits + other.totalUnits(),
                    exactAmount.add(other.exactAmount())
            );
        }
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("PEN", 2, new BigDecimal("12.50")),
                new Sale("BOOK", 1, new BigDecimal("8.75")),
                new Sale("PAD", 3, new BigDecimal("2.40"))
        );

        InvoiceStats stats = sales.stream()
                .reduce(
                        InvoiceStats.zero(),  // U: neutral value
                        InvoiceStats::addSale, // (U, Sale) -> U
                        InvoiceStats::merge    // (U, U) -> U
                );

        System.out.println(stats.lineCount());  // 3
        System.out.println(stats.totalUnits()); // 6
        System.out.println(stats.exactAmount()); // 40.95
    }
}
~~~

Reading the code by data types:

~~~text
Stream<Sale>       T = Sale
identity           U = InvoiceStats
accumulator        (InvoiceStats, Sale) -> InvoiceStats
combiner           (InvoiceStats, InvoiceStats) -> InvoiceStats
reduce result      U = InvoiceStats
~~~

The three line amounts are `2 × 12.50 = 25.00`, `1 × 8.75 = 8.75`, and `3 × 2.40 = 7.20`. The exact total is `40.95`. Each call to `addSale` creates **a new object**, without mutating the received accumulator object. `merge` also creates a new object, summing the corresponding metrics.

If the data has no line items:

~~~java
InvoiceStats emptyStats = List.<Sale>of().stream()
        .reduce(
                InvoiceStats.zero(),
                InvoiceStats::addSale,
                InvoiceStats::merge
        );

System.out.println(emptyStats.lineCount());  // 0
System.out.println(emptyStats.exactAmount()); // 0
~~~

This pattern can run completely in parallel:

~~~java
InvoiceStats parallelStats = sales.parallelStream()
        .reduce(
                InvoiceStats.zero(),
                InvoiceStats::addSale,
                InvoiceStats::merge
        );
~~~

With the sample data and exact additions, all metrics must have the exact same numeric values between sequential and parallel runs.

> **Java version:** `record` has been official since Java 16; on Java 8–15, replace it with an immutable class having a constructor, getters, and methods returning new values. The three-parameter `reduce` overload has existed since Java 8.

## 5. Verifying the contract with the InvoiceStats example

With `InvoiceStats.zero()`:

~~~text
zero = (lineCount=0, totalUnits=0, exactAmount=0)
~~~

If `u` is any partial total, `zero.merge(u)` has the exact same metrics as `u`. This is the identity relationship.

For three partial totals `a`, `b`, `c`, `merge` adds each field component-wise. Because monetary values are added exactly and counts are added, grouping `(a.merge(b)).merge(c)` or `a.merge(b.merge(c))` yields the same arithmetic result (assuming `long` counts do not overflow and data is valid). This is associativity.

Finally, for any line item `sale`:

~~~text
u.merge(zero.addSale(sale)) == u.addSale(sale)
~~~

Here `==` denotes **equality of metric values**, not Java reference comparison via the `==` operator. Two `InvoiceStats` constructions can return two distinct objects with the same values.

In a real program, you also need to agree on policies for `null`, negative quantities, negative unit prices, count overflow, and `BigDecimal` scale. Those policies belong to the business model; `reduce` simply combines results according to the definitions we supply.

## 6. Using a lambda directly instead of an intermediate record

You do not necessarily need to create a statistics record if the result is just a single number. For example, counting total characters across strings:

~~~java
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

long totalCharacters = words.stream()
        .reduce(
                0L,
                (total, word) -> total + word.length(),
                Long::sum
        );

System.out.println(totalCharacters); // 13
~~~

`T = String` and `U = Long`; the three-parameter form expresses transforming strings into a total length. Using `long` provides a larger overflow limit than `int`, though `long` itself can still overflow on huge data.

For this sum, a shorter and usually more efficient pipeline is:

~~~java
long sameTotal = words.stream()
        .mapToLong(String::length)
        .sum();
~~~

Both approaches fit when only one number is needed; the primitive stream form avoids creating intermediate `Long` objects. When **multiple aggregations are needed in a single result type**, such as `InvoiceStats`, the three-parameter overload expresses the `T -> U` model more clearly.

### When there is a filter condition

You can place `filter` before `reduce`:

~~~java
long lengthOfLongWords = words.stream()
        .filter(word -> word.length() >= 5)
        .reduce(
                0L,
                (total, word) -> total + word.length(),
                Long::sum
        );

System.out.println(lengthOfLongWords); // 6 ("Stream")
~~~

`filter` retains the elements passed to the accumulator. Although `filter` and `map` are normally *lazy* intermediate operations, `reduce` is a **terminal operation**, so it triggers traversal and ends the pipeline. That Stream object cannot be reused for another terminal operation.

## 7. Common mistake: reduce with a mutable List or Map

This is how you should **not** build a list from a Stream:

~~~java
import java.util.ArrayList;
import java.util.List;

// Wrong example, do not use in applications:
List<String> result = words.parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, word) -> {
                    list.add(word);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
~~~

Why is it wrong?

1. `identity` is **a mutable list object**, used as the starting value for reductions. When functions mutate this object directly, branches can share the same state and cause race conditions.
2. `accumulator` mutates its input directly instead of returning an independent partial result; applying or merging sub-parts can duplicate elements or make results execution-dependent.
3. `combiner` continues mutating a list that may alias another list or the identity. The identity contract and compatibility are no longer guaranteed.

To accumulate into a **mutable container**, the Java Stream API has the dedicated `collect` terminal operation:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

List<String> result = words.parallelStream()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

Or use the three-parameter overload of `collect`, which takes a `supplier` creating a fresh container, a `BiConsumer` `accumulator`, and a `BiConsumer` `combiner`:

~~~java
List<String> result = words.parallelStream()
        .collect(
                ArrayList::new,
                List::add,
                List::addAll
        );
~~~

Important comparison:

| `reduce(identity, accumulator, combiner)` | `collect(supplier, accumulator, combiner)` |
| --- | --- |
| `identity` is a **value `U`**. | `supplier` is a function creating a **new container**. |
| Accumulator returns `U`. | Accumulator typically mutates the container and returns `void`. |
| Combiner returns a `U`. | Combiner takes two containers and returns `void` in the three-parameter overload of `Stream.collect`. |
| Suited for immutable results and pure combining operations. | Suited for lists, maps, builders, and mutable structures. |

Distinguish this from `Collector` used by `collect(Collector)`: that type has its own specification for supplier, accumulator, combiner, finisher, and characteristics. For grouping data, `Collectors.groupingBy`, `partitioningBy`, or custom collectors are usually better suited than building a mutable Map with `reduce`.

If you write a custom collector for parallel processing, you still must follow contracts on associativity, containers, and ordering.

## 8. Bugs that cause sequential and parallel results to differ

| Symptom | Cause | Fix |
| --- | --- | --- |
| Result has an “initial fee” added multiple times | `identity` is not the neutral element | Use a neutral identity, and add the fixed amount **after** the reduction. |
| Sequential passes, parallel fails | `combiner` has different semantics from `accumulator` | Ensure `combine(u, accumulate(identity, t)) = accumulate(u, t)`. |
| Result depends on how groups are split | Combiner is not associative, e.g. performs intermediate rounding | Combine exactly; perform rounding at a clearly defined business step. |
| Duplicated or lost data in parallel execution | Shared mutable accumulation variable | Use an immutable value `U` or switch to `collect`. |
| Empty Stream handled incorrectly | Identity does not represent an empty result | Define the proper neutral element: 0 for sum, 1 for product, empty record for stats. |
| `NullPointerException` inside accumulator | `null` elements or nullable fields | Validate input; define clear rules for filtering, defaulting, or rejecting. |
| String concatenation changes order | Unordered pipeline with order-sensitive combining | Preserve encounter order or adjust the operation model appropriately. |
| Total overflows or computation is slow | Boxing, allocating many `U`s, parallelizing too small a workload | Consider primitive streams or an optimized collector, and benchmark actual performance. |

### Do not round inside every BigDecimal addition

The following example risks violating associativity:

~~~java
// Not recommended when the goal is an exact monetary total:
BigDecimal total = sales.parallelStream()
        .reduce(
                BigDecimal.ZERO,
                (subtotal, sale) -> subtotal
                        .add(sale.unitPrice()
                                .multiply(BigDecimal.valueOf(sale.quantity())))
                        .setScale(2, RoundingMode.HALF_UP),
                (left, right) -> left.add(right)
                        .setScale(2, RoundingMode.HALF_UP)
        );
~~~

Rounding in each branch or each merge step can change the final result. If the business rule is **sum exactly and then round once**, do:

~~~java
BigDecimal exactTotal = sales.parallelStream()
        .reduce(
                BigDecimal.ZERO,
                (sum, sale) -> sum.add(
                        sale.unitPrice()
                                .multiply(BigDecimal.valueOf(sale.quantity()))),
                BigDecimal::add
        );

BigDecimal payable = exactTotal.setScale(
        2, RoundingMode.HALF_UP);
~~~

This snippet assumes `java.math.BigDecimal` and `java.math.RoundingMode` are imported, `Sale` records have `unitPrice()` and `quantity()` accessors, and rounding once at the invoice level is permitted by the business rules.

## 9. When should you not use three-parameter reduce?

Although flexible, the three-parameter overload is not always the optimal choice.

### 9.1. Summing primitive integers or floating-point numbers

With `Stream<String>`, if you only need to sum string lengths:

~~~java
long length = words.stream()
        .mapToLong(String::length)
        .sum();
~~~

This approach is concise, avoids boxing during aggregation, and expresses the intent clearly. Similarly, use `mapToInt`, `mapToDouble`, and `sum`, `average`, `summaryStatistics` when appropriate.

### 9.2. Need a built-in statistics collector

~~~java
import java.util.IntSummaryStatistics;
import java.util.stream.Collectors;

IntSummaryStatistics stats = words.stream()
        .collect(Collectors.summarizingInt(String::length));

System.out.println(stats.getCount()); // 3
System.out.println(stats.getSum());   // 13
~~~

This collector already provides count, sum, min, max, and average length. When the needed statistics are already offered by the library and match requirements, using a built-in collector reduces custom code.

### 9.3. Need to group data or produce a mutable result

~~~java
import java.util.Map;
import java.util.stream.Collectors;

Map<Integer, List<String>> byLength = words.stream()
        .collect(Collectors.groupingBy(String::length));
~~~

`groupingBy` creates a Map containing lists of strings grouped by length, without manually constructing a mutable `Map` via `reduce`. For lists, `toList()` or `Collectors.toList()` is also more suitable.

### 9.4. Only need to convert type once and use the two-parameter overload

If elements can be converted to the result type via `map`, you can separate the conversion step:

~~~java
BigDecimal total = sales.stream()
        .map(sale -> sale.unitPrice()
                .multiply(BigDecimal.valueOf(sale.quantity())))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
~~~

This is `Stream<Sale> -> Stream<BigDecimal> -> BigDecimal`. It is very readable and allows using the two-parameter overload because at the time of `reduce`, the element type is already `BigDecimal`.

Conversely, if you want to directly produce a multi-field result from each element and merge intermediate results, three-parameter `reduce` with an immutable type `U` like `InvoiceStats` is a reasonable choice.

## 10. Stream lifecycle, resources, and performance limits

`reduce` is a **terminal operation**: even though upstream steps like `filter` and `map` are *lazy*, calling `reduce` starts traversing the source to compute the result. Afterward, no other terminal operation can be called on the same Stream object.

To aggregate all data, a reduction normally must consume every emitted element. On an infinite Stream without a stopping point, `reduce` cannot know on its own when enough data has been seen; a finite bound like `limit` or a clearly terminating source design is required.

~~~java
long sumFirstTen = java.util.stream.LongStream.iterate(1, n -> n + 1)
        .limit(10)
        .sum();

System.out.println(sumFirstTen); // 55
~~~

`reduce` can avoid holding every element in a `List`, yet a large `U` or expensive merge step can still consume substantial CPU and memory. With `InvoiceStats`, each accumulator call creates a new record and possibly a new `BigDecimal`; this is a trade-off between immutability, ease of proving correctness, and allocation cost. On very large datasets, benchmark performance before deciding between a custom reduction and an optimized collector.

If the source is a file or I/O resource, such as a Stream from `Files.lines`, use `try-with-resources` to close the source. `reduce` finishes the computation but does not replace the resource-closing contract.

When running in parallel, remember `reduce` does not magically make lambdas with side effects thread-safe, does not overcome source/`Spliterator` limitations, and does not guarantee speedup in all cases.

## 11. Self-check

**Exercise 1 — Types T and U**

~~~java
List<String> words = List.of("A", "BC", "DEF");

long result = words.stream()
        .reduce(0L, (total, s) -> total + s.length(), Long::sum);
~~~

What are types `T`, `U`, and the result value?

**Answer:** `T = String`, `U = Long`, and the result is `1 + 2 + 3 = 6`.

**Exercise 2 — Find the identity bug**

~~~java
long result = words.parallelStream()
        .reduce(100L, (total, s) -> total + s.length(), Long::sum);
~~~

Why can the result be wrong?

**Answer:** `100L` is not neutral with respect to `Long::sum`. Each branch can start from 100; to add a fixed amount of 100, reduce from `0L` and add 100 after obtaining the result.

**Exercise 3 — Choose reduce or collect**

You need to create a `List<String>` containing uppercased elements from a `Stream<String>`. Should you use `reduce(new ArrayList<>(), ...)` and mutate the list inside the accumulator?

**Answer:** No. Use:

~~~java
List<String> upper = words.stream()
        .map(String::toUpperCase)
        .toList();
~~~

If a mutable list is needed, you can use `collect(Collectors.toCollection(ArrayList::new))`.

**Exercise 4 — Check the combiner**

~~~java
int total = words.parallelStream()
        .reduce(
                0,
                (sum, word) -> sum + word.length(),
                (left, right) -> left * right
        );
~~~

Why is the combiner wrong?

**Answer:** The accumulator sums lengths, whereas the combiner multiplies partial totals, failing compatibility. Moreover, `0` is the neutral element of addition, not multiplication. The right combiner matching sum semantics is `Integer::sum`.

**Exercise 5 — Result for an empty Stream**

~~~java
InvoiceStats stats = List.<Sale>of().stream()
        .reduce(
                InvoiceStats.zero(),
                InvoiceStats::addSale,
                InvoiceStats::merge
        );
~~~

What is the result?

**Answer:** `InvoiceStats.zero()`: 0 lines, 0 units, exact amount equal to 0. Because there are no elements to accumulate, the reduction returns the identity per contract.

## 12. Key takeaways

- `reduce(U identity, BiFunction<U, ? super T, U> accumulator, BinaryOperator<U> combiner)` allows aggregating a `Stream<T>` into a result of type `U`.
- **Identity** must be neutral with the combiner; **combiner** must be associative; **accumulator** must be compatible with the combiner.
- Sequential execution can hide combiner bugs; in parallel execution, partial totals must merge to the same business result.
- Use an **immutable type `U`** when you want a pure reduction, especially for multi-field statistics records.
- Do not use `reduce` to jointly mutate an `ArrayList`, `HashMap`, or builder; use `collect` when mutable reduction is needed.
- For simple problems, consider `mapToInt`/`mapToLong` and `sum`, statistics collectors, `groupingBy`, or `map` followed by two-parameter `reduce`.

**Main takeaway:** The three-parameter `reduce` overload is a tool to **change the result type during reduction**. Correctness lies not only in how the accumulator processes each element, but also in **merging intermediate results via the combiner** under the same rule, independent of how the Stream partitions work.
