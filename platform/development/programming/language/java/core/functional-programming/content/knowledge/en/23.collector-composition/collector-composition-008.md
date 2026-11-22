# Collectors.teeing() to Combine Two Aggregations in Java

## 1. The Problem: Needing Two Statistics from the Same Stream Source

Suppose you have a list of orders and need to generate a report containing the **order count** and **total revenue**. Two separate aggregations can be written as follows:

~~~java
long count = sales.stream().count();
long total = sales.stream().mapToLong(Sale::revenue).sum();
~~~

This is an **illustrative snippet inside a method**; the `Sale` type has a `revenue()` method as in the Java 17 program in Section 8. The code above is clear, but it creates **two separate Streams** from the same Collection, which may require evaluating the data twice. If the source cannot be traversed again or both reports must be built in a single collection pass, we want to express a single aggregation consisting of **two branches**.

Since Java 12, `java.util.stream.Collectors` provides:

~~~java
Collectors.teeing(downstream1, downstream2, merger)
~~~

The name *teeing* evokes the image of a T-shaped junction: incoming data is routed to **two downstream collectors** to compute two separate results, and then the **merger** combines those two results into a single final value.

Example:

~~~java
Summary summary = sales.stream().collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Sale::revenue),
        (count, total) -> new Summary(count, total)
));
~~~

This is **illustrative** code, assuming a `Summary` class/record has a constructor taking `long count, long total`, and `java.util.stream.Collectors` is imported. The two collection branches respectively produce:
- `downstream1 = counting()`: the number of elements.
- `downstream2 = summingLong(...)`: the total revenue.
- `merger`: turns the two results into a structured `Summary`.

**Key point:** `teeing()` does not create an extra data source on its own and does not force you to write two terminal operations. It is **a single Collector** to be used with **one** `stream.collect(...)`, in which each element is fed into both downstreams according to the Collector mechanism.

## 2. Signature and Generic Types of teeing()

Conceptual signature in Java 17:

~~~java
static <T, R1, R2, R> Collector<T, ?, R> teeing(
        Collector<? super T, ?, R1> downstream1,
        Collector<? super T, ?, R2> downstream2,
        BiFunction<? super R1, ? super R2, R> merger)
~~~

This is an **API signature for reading comprehension**, not code you need to declare in your application. The type parameters:

| Symbol | Role |
| --- | --- |
| `T` | Type of elements collected from the Stream |
| `R1` | Final result type of the first downstream |
| `R2` | Final result type of the second downstream |
| `R` | Final result type after the merger combines both branches |
| `downstream1` | Collector applied to source T |
| `downstream2` | Another Collector, also applied to source T |
| `merger` | Function taking `(R1,R2)` and returning `R` |

For example, the two collectors can return **different types**:

~~~java
Collectors.teeing(
        Collectors.counting(),            // Long
        Collectors.toList(),               // List<T>
        (count, elements) -> ...           // Result defined by you
)
~~~

The `...` in the snippet above is a **conceptual placeholder**, not complete Java. The merger can create a record, DTO, project-defined tuple, an appropriate `Map.Entry`, or another domain type.

Unlike `reduce(identity, accumulator, combiner)`, you **do not have to write state-management logic for both branches yourself**. Each downstream collector provides its own supplier/accumulator/combiner/finisher; teeing coordinates both branches and then calls the merger to produce R.

### 2.1. Data Flow Diagram View

~~~text
                Stream<T>
                    |
              collect(teeing)
                    |
          +---------+---------+
          |                   |
    downstream1          downstream2
    counting()           summingLong(...)
          |                   |
       R1: Long             R2: Long
          |                   |
          +---------+---------+
                    |
              merger(R1, R2)
                    |
                Summary
~~~

The diagram describes the **data flow and aggregation contract**, not the thread schedule or the number of calls to each function that the JDK must use. With a parallel stream, the framework may maintain multiple partial collection containers and combine them before producing the two final values R1 and R2.

### 2.2. Argument Order in the Merger

The merger receives the result of the **first downstream first**, followed by the result of the **second downstream**:

~~~java
(count, total) -> new Summary(count, total)
~~~

Do not swap the meaning of the two parameters just because they share the same `Long` type. When both R1 and R2 are numbers, the compiler will still accept a merger with a swapped business order. Naming `count` and `total` to match their corresponding collectors helps avoid hard-to-spot bugs.

## 3. Practical Example: Order Count and Total Amount in a Summary

A simple order class can represent quantity and unit price:

~~~java
record Sale(String region, int units, long unitPrice) {
    long revenue() {
        return Math.multiplyExact((long) units, unitPrice);
    }
}
~~~

This is a Java 17 **type declaration**; the complete program is in Section 8. `Math.multiplyExact` throws `ArithmeticException` when `long` multiplication overflows; it does not make additions in the aggregation step automatically checked for overflow.

The report result:

~~~java
record Summary(long orders, long revenue,
               OptionalDouble averageRevenue) {}
~~~

Here `OptionalDouble` represents an average that may or may not have data. To avoid division by 0 when the Stream is empty, the merger can decide:

~~~java
Summary summary = sales.stream().collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Sale::revenue),
        (count, total) -> new Summary(
                count,
                total,
                count == 0 ? OptionalDouble.empty()
                           : OptionalDouble.of((double) total / count))
));
~~~

This snippet requires importing `Collectors` and `OptionalDouble`, and being placed inside a method that already has the `sales` list. A few points to note:

1. `counting()` returns `Long`, which is auto-unboxed to `long` when constructing the record.
2. `summingLong(Sale::revenue)` returns the `Long` sum.
3. Both branches receive the same Sale objects, but **each branch computes a separate aggregation**.
4. The merger is used to create **one Summary** from the two final values.
5. For an empty list, `count=0`, `total=0`; the average is represented as **having no value**, rather than equating it with an actual average of 0.

If the application wants to display an average of 0 when there are no orders, that is a **presentation or business decision**. The data layer can still keep `OptionalDouble.empty()` to avoid confusing "no observations" with "measured average equal to 0".

### 3.1. Why Isn't This a Simple Division in Each Branch?

Total revenue and order count are independent, but the **average** depends on both simultaneously. If you try to compute the average directly from a single element without both the sum and the count, you need a dedicated statistics collector.

`teeing` is suitable when:
- You need two results computed independently from the same elements.
- You want to combine them into a meaningful result type.
- Collectors already exist for each branch, and you do not want to write custom mutable state.

If you only need the average, `Collectors.averagingLong(Sale::revenue)` may be more direct. `teeing` is valuable when **you also need the other metrics** to build a report at the same time.

## 4. Combining Two Very Different Collectors

The two branches do not have to both return numbers.

Suppose you need **total revenue by region** and **overall total revenue** in one report. The first downstream can be `groupingBy(...)`, and the second branch `summingLong(...)`:

~~~java
record Report(Map<String, Long> revenueByRegion, long grandTotal) {}

Report report = sales.stream().collect(Collectors.teeing(
        Collectors.groupingBy(
                Sale::region,
                TreeMap::new,
                Collectors.summingLong(Sale::revenue)),
        Collectors.summingLong(Sale::revenue),
        Report::new
));
~~~

This is **illustrative code**: declare `record Report` at the type level, and place the `collect` call inside a method. You need to import `java.util.Map`, `java.util.TreeMap`, and `Collectors`.

Suppose the order list is:

~~~text
North: 200
South: 180
North: 150
West:  120
~~~

The two downstreams produce:

~~~text
Branch 1 (TreeMap): {North=350, South=180, West=120}
Branch 2 (Long):    650
Merger:             Report(byRegion, 650)
~~~

**Why use TreeMap?** Because the report wants region keys ordered ascending by String's natural order. The default `groupingBy` does not guarantee the Map type or iteration order, whereas `TreeMap::new` explicitly establishes the key-sorting contract. Note that TreeMap sorts **by key**, not by revenue value.

In the runnable example in Section 8, using `parallelStream()` with this collector also produces a valid result because the downstreams and their combining operations are used according to contract. However, **you should not infer** that a parallel stream is always faster or that region names will be processed in thread order.

### 4.1. Should the Record/Report Be Immutable?

A `record Report(Map<String,Long>...)` only prevents reassigning the field reference; it **does not automatically make the inner Map immutable**. When a public immutable DTO is needed, create a defensive copy with an appropriate Map choice and consider how to preserve order if the output requires iteration order. For example, `Map.copyOf(...)` creates an unmodifiable Map, but **you should not rely on it to preserve TreeMap iteration order**.

You can use an unmodifiable wrapped `SortedMap`, or convert the report into a sorted list of entries with a clear JSON serialization contract; choose based on actual requirements.

## 5. Combining minBy and maxBy into a Range

Another easy-to-understand case: needing the **minimum and maximum values**.

~~~java
record Range(Optional<Integer> min, Optional<Integer> max) {}

Range range = values.stream().collect(Collectors.teeing(
        Collectors.minBy(Comparator.naturalOrder()),
        Collectors.maxBy(Comparator.naturalOrder()),
        Range::new
));
~~~

This snippet requires importing `java.util.Optional`, `java.util.Comparator`, and `Collectors`. With source `[4,9,2,7]`:

~~~text
Range[min=Optional[2], max=Optional[9]]
~~~

Here:
- Downstream 1 is `minBy`, returning `Optional<Integer>`.
- Downstream 2 is `maxBy`, returning `Optional<Integer>`.
- Merger `Range::new` uses the two Optionals to create a new record.
- The `teeing` form fits because you want a **pair of values**, not just min or max alone.

### 5.1. Empty Source

With `List.<Integer>of().stream()`, both `minBy/maxBy` downstreams produce `Optional.empty()`. Result:

~~~text
Range[min=Optional.empty, max=Optional.empty]
~~~

There is no need to throw an exception just because there are no elements. However, the caller must have a policy: display "no data", use a fallback, or reject the calculation if missing data is a business error.

### 5.2. When Is teeing Not Needed for min/max?

If you are only processing **primitive values** or only need min/max/count/average of the same numeric type, Java has specialized statistics utilities such as `IntSummaryStatistics`, `LongSummaryStatistics`, and the `summarizingInt/Long/Double` collectors. They are usually shorter, clearer, and more optimized for numeric aggregation than manually combining multiple downstreams over the same data.

Example:

~~~java
IntSummaryStatistics stats = values.stream()
        .collect(Collectors.summarizingInt(Integer::intValue));
~~~

This is an illustrative snippet requiring imports for `java.util.IntSummaryStatistics` and `Collectors`. It returns min/max/sum/count/average metrics on IntSummaryStatistics. For an empty number set, check the contract of the getters before displaying min/max (the default statistic values are not necessarily equivalent to an Optional).

**Choose teeing if the two results and the merger accurately express the domain meaning**; do not force teeing everywhere just because the API allows it.

## 6. Nesting teeing Inside groupingBy: Two Statistics per Group

Instead of using `teeing` to compute a single whole-batch report, you can also place it as the **downstream collector** of `groupingBy`.

Suppose each sale has `type` and `amount`:

~~~java
record Sale(String type, int amount) {}
record GroupStat(long count, int total) {}

Map<String, GroupStat> grouped = sales.stream().collect(
        Collectors.groupingBy(
                Sale::type,
                TreeMap::new,
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingInt(Sale::amount),
                        GroupStat::new))
);
~~~

This is **multi-part illustrative** code: the two records must be declared at the type level, while the `collect` call goes inside a method with an appropriate `sales` list; type names may need to avoid colliding with the Sale class in Section 8. A standalone version of this example was verified with Java 17.

If the grouped data is:

~~~text
A: 2
B: 5
A: 3
~~~

then the result is:

~~~text
{A=GroupStat[count=2, total=5], B=GroupStat[count=1, total=5]}
~~~

Here:
- `groupingBy` creates groups by `type`.
- For each group, the downstream is `teeing(counting(), summingInt(...), GroupStat::new)`.
- The result for each group is a `GroupStat`, not a list of elements.
- `TreeMap::new` determines the order of **group keys**, not how the two downstreams aggregate elements.

This is a powerful application of collector composition: **groupingBy + teeing** builds a multi-metric report per key without writing manual merging loops.

### 6.1. Can teeing Be Nested with Other Collectors?

Yes, as long as the generic types and contracts are compatible. A downstream of teeing can be:
- `counting()`, `summingLong(...)`, `averagingDouble(...)`.
- `minBy(...)`, `maxBy(...)`.
- `mapping(..., toList())` to collect a list of a single field.
- `filtering(predicate, downstream)` to aggregate only elements matching a condition.
- `groupingBy(...)` to build a Map structure by key.
- A custom `Collector.of(...)`, provided it adheres to the collector contracts.

However, nesting too many collectors can make generic types hard to read. A domain-named helper or a custom statistics Collector may be easier to maintain, especially when three or four metrics and many special rules are needed.

## 7. How Does teeing Differ from Running Two Terminal Operations?

Consider two approaches:

**Approach A — Two separate Streams:**

~~~java
long count = sales.stream().count();
long total = sales.stream().mapToLong(Sale::revenue).sum();
Summary summary = ...;
~~~

The line `Summary summary = ...;` in this snippet is **pseudo-code**, not standalone Java; its purpose is only to express how the results are combined. If the source is a re-traversable Collection, Approach A can be simple and acceptable.

**Approach B — One teeing collect:**

~~~java
Summary summary = sales.stream().collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Sale::revenue),
        (count, total) -> new Summary(
                count, total,
                count == 0 ? OptionalDouble.empty()
                           : OptionalDouble.of((double) total / count))
));
~~~

Approach B describes aggregating into **one result R from a single Stream collection**, without needing to create two Streams. This is useful when data comes from a single-pass stream or when a report needs to package multiple statistics from the same source.

### 7.1. One Pipeline Does Not Mean Only One Operation per Element

`teeing` distributes elements to **both downstreams**, so it can incur the cost of **two aggregations** per element. It does not automatically reduce the number of `Sale::revenue` evaluations if both branches invoke this method; for example, a regional report and a grand total might each compute revenue for their own needs.

If computing from the input is expensive, you can `map` the data into a precomputed intermediate record before teeing:

~~~java
// Concept illustration: one normalization calculation before two downstreams.
// stream.map(this::calculateOnce)
//       .collect(Collectors.teeing(downstream1, downstream2, merger));
~~~

This is **pseudocode** with hypothetical method names. If implemented, ensure the intermediate record holds enough information for both collectors and that the transformation step has no hard-to-control side effects.

### 7.2. teeing Does Not Automatically Guarantee a Speedup

A single `teeing` can traverse the source in one terminal operation, but it still has to maintain **two state containers** and combine them, which has overhead. For simple mathematical metrics, `summarizingLong` or a custom Collector may be more efficient. Choose for clarity first, and benchmark with representative data if performance matters.

### 7.3. Cannot Reuse the Same Stream After collect

~~~java
Stream<Sale> stream = sales.stream();
Summary result = stream.collect(...);

// You cannot reuse the same stream instance to call count()/collect() again.
~~~

This is **illustrative/pseudocode**: `...` represents an appropriate collector. After the `collect(...)` terminal operation, the Stream is consumed; do not reuse the instance. If the source is a List, you can create a new Stream from the same List when you need to do something else.

## 8. Complete, Compilable, and Runnable Java 17 Example

Create the file **TeeingCollectorDemo.java**. The example demonstrates three scenarios:

1. Creating a `Summary` with order count, revenue, and a potentially empty average.
2. Creating a `Report` with regional totals and a grand total using `parallelStream()`.
3. Creating a `Range` with Optional min/max, including an empty source.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.OptionalDouble;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class TeeingCollectorDemo {
    record Sale(String region, int units, long unitPrice) {
        long revenue() {
            return Math.multiplyExact((long) units, unitPrice);
        }
    }

    record Summary(long orders, long revenue,
                   OptionalDouble averageRevenue) {}

    record Report(Map<String, Long> revenueByRegion,
                  long grandTotal) {}

    record Range(Optional<Integer> min, Optional<Integer> max) {}

    static Summary summarize(List<Sale> sales) {
        return sales.stream().collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Sale::revenue),
                (count, total) -> new Summary(
                        count, total,
                        count == 0 ? OptionalDouble.empty()
                                   : OptionalDouble.of((double) total / count))
        ));
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("North", 2, 100),
                new Sale("South", 1, 180),
                new Sale("North", 3, 50),
                new Sale("West", 1, 120)
        );

        System.out.println("summary=" + summarize(sales));
        System.out.println("empty=" + summarize(List.of()));

        Report report = sales.parallelStream().collect(Collectors.teeing(
                Collectors.groupingBy(
                        Sale::region,
                        TreeMap::new,
                        Collectors.summingLong(Sale::revenue)),
                Collectors.summingLong(Sale::revenue),
                Report::new));
        System.out.println("report=" + report);

        Range range = List.of(4, 9, 2, 7).stream()
                .collect(Collectors.teeing(
                        Collectors.minBy(Comparator.naturalOrder()),
                        Collectors.maxBy(Comparator.naturalOrder()),
                        Range::new));
        Range emptyRange = List.<Integer>of().stream()
                .collect(Collectors.teeing(
                        Collectors.minBy(Comparator.naturalOrder()),
                        Collectors.maxBy(Comparator.naturalOrder()),
                        Range::new));
        System.out.println("range=" + range);
        System.out.println("empty range=" + emptyRange);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac --release 17 TeeingCollectorDemo.java
java TeeingCollectorDemo
~~~

**Verified stdout when run with Java 17:**

~~~text
summary=Summary[orders=4, revenue=650, averageRevenue=OptionalDouble[162.5]]
empty=Summary[orders=0, revenue=0, averageRevenue=OptionalDouble.empty]
report=Report[revenueByRegion={North=350, South=180, West=120}, grandTotal=650]
range=Range[min=Optional[2], max=Optional[9]]
empty range=Range[min=Optional.empty, max=Optional.empty]
~~~

### 8.1. Reading the Output

- **Summary:** there are four orders, revenue 200 + 180 + 150 + 120 = **650**, average **162.5** per order.
- **Empty Summary:** order count 0, total 0, average **undefined due to no data** and represented by `OptionalDouble.empty()`.
- **Report:** North region has 200 + 150 = **350**, South = **180**, West = **120**, grand total = **650**. Regional results are kept in a TreeMap with natural key ordering.
- **Range:** min = 2, max = 9; both downstreams return an Optional containing a value.
- **Empty Range:** both min and max are `Optional.empty()`; the merger still creates a Range record containing both empty states.

### 8.2. Why Is the Report Result Using parallelStream Still Correct?

The two branches use the standard collectors `groupingBy(..., summingLong(...))` and `summingLong(...)`, applied according to the collector contract. The framework can partition, collect separately, and combine the aggregated states before the merger creates the Report.

There is no shared mutable counter from an outer lambda, and the sum does not depend on thread order. `TreeMap` was chosen to control **the key order of the result**, not to allow multiple threads to write arbitrarily into the same unsynchronized Map.

This program has no null data and small numbers that do not overflow long. For real business data, you can add unit-price/quantity validation and an overflow-handling policy.

## 9. Empty Sources and the Meaning of Results from Both Downstreams

One benefit of teeing is that each branch has its own result rule on an empty Stream:

| Downstream | Typical Result When Empty |
| --- | --- |
| `counting()` | `0L` |
| `summingLong(...)` | `0L` |
| `toList()` | Empty list |
| `minBy(...)` | `Optional.empty()` |
| `maxBy(...)` | `Optional.empty()` |
| `groupingBy(...)` | Empty Map |

The merger will receive the results **after the finisher** of each downstream, even when the source has no elements. Therefore, deciding the final result R needs to handle valid empty states.

For example, `average = total / count` must avoid division by 0. When a branch returns an Optional, the merger should not call `get()` unconditionally. A "min-max" report can keep the Optionals as-is; another API might decide to return a business error if data is mandatory.

**Important point:** an empty source **does not automatically cause teeing to fail**. Empty behavior depends on the two downstreams and the merger; if the merger itself actively throws an exception on empty input, that is a logic decision of the written code, not a general rule of teeing.

## 10. Teeing with Conditionally Filtered Downstreams

The two branches can aggregate **two different subsets** of the same input Stream via `Collectors.filtering(...)`:

~~~java
record Check(long accepted, long rejected) {}

Check result = orders.stream().collect(Collectors.teeing(
        Collectors.filtering(Order::valid, Collectors.counting()),
        Collectors.filtering(order -> !order.valid(), Collectors.counting()),
        Check::new
));
~~~

This is **multi-part illustrative** code; the record must be placed at the type level, with an `Order` class providing `valid()` and `Collectors` imported. For a valid source, the first branch counts valid elements; the second branch counts invalid elements. The merger creates a `Check(accepted,rejected)`.

The advantage is that both rules are expressed via collector composition rather than two separate Streams. However:
- Both predicates may be evaluated separately for the same element.
- If `valid()` has side effects or reads mutable state, the two checks could be inconsistent.
- If the dataset is very large and the predicate is expensive, consider a dedicated aggregation state or normalizing the data before collecting.
- Ensure the two conditions are truly mutually exclusive in business terms; if there is a third "unknown" state, a two-branch accepted/rejected model can lose information.

`Collectors.filtering(...)` in the example is just a **downstream operation** of teeing, unlike `Stream.filter(...)` in the outer pipeline (which would drop elements before either branch receives them).

## 11. teeing in Parallel Streams: Safety Contract

A collector may be used by the Stream framework under partitioning and combining rules when the source is a parallel stream. Whether `teeing` is safe and efficient depends on both downstreams:

1. **Downstreams must obey the Collector contract**: the supplier creates proper containers, accumulator and combiner merge validly, and finisher returns the right result.
2. **Inputs must not be concurrently modified in violation of the source contract**; classifiers, mappers, and predicates should be stateless and non-interfering.
3. **The merger should not depend on thread order** or external state. The merger receives the two final aggregated downstream results and produces one R.
4. **Collector characteristics** (*characteristics*) must be understood in terms of both downstreams. Do not assume teeing is always concurrent, always unordered, or has an identity finisher.
5. **Results using mutable containers** may need copying/defensive protection at the return boundary if clients are not allowed to modify them.

### 11.1. Collector Characteristics Cannot Be Inferred from the Name teeing

`Collectors.teeing` derives its characteristics from the common characteristics of the two downstreams; there is no `IDENTITY_FINISH` for the resulting collector because the merger must be called to produce R. Characteristics such as `UNORDERED` or `CONCURRENT` can only be retained when the corresponding conditions are met by **both downstreams**.

Do not write code assuming `teeing(toList(), counting(), ...)` automatically becomes a concurrent collector just because the Stream is in parallel mode. How the framework invokes the downstreams is part of the Collector contract and Stream implementation.

### 11.2. Side Effects and Exceptions

If a downstream mapper throws an unhandled exception, `collect(teeing(...))` may fail; teeing **does not automatically turn errors into a Failure result** or roll back side effects that already occurred.

If both downstreams call external systems (sending HTTP requests, writing to a database), feeding every element into both branches can double the cost and risk of side effects. Collectors are designed for **data aggregation**, not as multi-service transaction coordinators. If all-or-nothing semantics are required, transaction/commit design must sit outside collector selection.

### 11.3. Do Not Mistake Execution Order for Output Order

With an ordered Map collector like TreeMap, the **key iteration order of the resulting Map** is determined by TreeMap. Do not infer from this that an element belonging to North was processed before South across worker threads.

If a downstream uses a list and the source has an encounter order, the collector's result must be evaluated according to the specific contract of the downstream and pipeline. When a stable report order is needed, choose a structure with an explicit ordering contract rather than relying on logging from callbacks to guess.

## 12. Common Mistakes with teeing

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Passing an already computed result instead of a Collector to a downstream | Type error / syntax error | Pass `Collectors.counting()`, `Collectors.summingLong(...)`, etc. |
| Swapping the semantic order of R1/R2 in the merger | Report fields assigned wrongly even though types match | Name merger parameters to match the two downstreams |
| Assuming teeing only needs Java 8 | API not found on JDK 8/11 | Use Java 12+; this article targets Java 17 |
| Using `count==0 ? total/count : ...` with the wrong condition | Division by 0 | Return Optional/handle branch when count=0 |
| Calling `Optional.get()` unchecked in the merger | Can fail on empty sources | Use Optional according to its contract |
| Assuming teeing automatically evaluates an expensive mapper only once | Both downstreams may invoke the computation separately | Precompute in a map step if reasonable |
| Assuming teeing is always faster than two Streams | Collector has overhead; speed is not guaranteed | Benchmark on real data |
| Assuming teeing always processes in parallel | Depends on the Stream and collector | Choose the right source/mode; do not overuse parallel |
| Using the default Map and expecting key order | Not guaranteed | Use an appropriate `TreeMap`/`LinkedHashMap` mapFactory |
| Modifying external objects inside the accumulator | Races, side effects, and hard to test | Keep collectors/predicates stateless and non-interfering |
| Treating a record containing a Map as deeply immutable | The inner Map can still be mutable | Design appropriate defensive copy/unmodifiable view |
| Reusing the Stream after collect | Stream is already consumed | Create a new Stream if the Collection is re-traversable |

### 12.1. Merger Order Bugs Easily Slip Past the Compiler

If both downstreams return `Long`:

~~~java
Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Sale::revenue),
        (total, count) -> new Summary(count, total, OptionalDouble.empty())
)
~~~

This is a **semantic counterexample**; the snippet lives inside code where Summary/Sale records are already defined. It compiles because both parameter types are Long, but the two names `total` and `count` have been **placed in reversed positions** relative to the collectors. The resulting Summary will contain swapped data.

Write instead:

~~~java
(count, total) -> new Summary(
        count,
        total,
        count == 0 ? OptionalDouble.empty()
                   : OptionalDouble.of((double) total / count))
~~~

Clear field-name examples and output tests help catch this kind of bug.

## 13. When to Use teeing, and When to Choose Another Approach?

| Problem | Suggestion |
| --- | --- |
| Need **two statistics** simultaneously from the same Stream and combine them into a record | `Collectors.teeing(...)` |
| Need min/max at the same time without requiring a custom structure | `summarizingInt/Long/Double(...)` may be clearer |
| Need per-group statistics, each group having two metrics | `groupingBy(..., teeing(...))` |
| Need only a single sum | `mapToLong(...).sum()` or `summingLong(...)` |
| Want to aggregate more than two branches | Nest teeing while still readable, or design a dedicated Collector/statistics object |
| Need to update a specialized mutable container | `collect(Collector.of(...))`/custom Collector if truly needed |
| Need to run multiple side effects per element | Do not use teeing as a transaction; use an explicit action-processing flow |
| Project must run on Java 8/11 | Do not use JDK teeing; use a compatible alternative |

### 13.1. Is Multi-Level Nesting of teeing Good?

You can nest it to combine three aggregations:

~~~java
// Structural illustration:
Collectors.teeing(
    firstCollector,
    Collectors.teeing(secondCollector, thirdCollector, Pair::new),
    (first, pair) -> ...
)
~~~

This is **pseudocode**; `firstCollector`, `Pair`, and `...` need to be defined in the project. Type-wise, nesting teeing works because each branch takes a Collector and returns R, but for complex reports, a custom Collector with a clear statistics structure is usually easier to read, easier to test, and can avoid repeated computation.

### 13.2. Can a Record Be Used as the Merger?

Yes. If the record constructor's types match R1 and R2, a method reference like `Report::new` or `Range::new` is a valid merger. This is a way to reduce boilerplate and keep the data shape clear.

If you need additional validation, unit conversion, or an empty-value policy, use a lambda with clear parameter names instead of `::new` to express that logic.

## 14. Checklist for Implementing a teeing Collector

Before writing `collect(Collectors.teeing(...))`, ask yourself:

1. **What are the two needed results?** Does each downstream compute the exact statistic required?
2. **Are the R1/R2/R types appropriate?** Does the merger's argument order match the downstream order?
3. **Can the source be empty?** What do the two downstreams return, and how should the merger handle Optional/0?
4. **Does output order matter?** For Maps, choose a mapFactory; for Lists, check encounter order.
5. **Is there a better specialized API for the problem?** Check `summarizing...`, `counting`, `summing...`.
6. **Do both branches repeat an expensive computation?** If so, consider creating intermediate data once.
7. **Are the collector and lambdas stateless/non-interfering?** Avoid mutating the source or shared mutable state.
8. **Will it run in parallel?** Check collector characteristics, combiner, and do not rely on thread scheduling.
9. **Does the merger produce a safe state for API return?** A record containing a List/Map is not necessarily deeply immutable.
10. **Are there overflow or numeric precision concerns?** Choose types/exceptions/rounding according to business rules.
11. **Is Java 8/11 support required?** `Collectors.teeing` was introduced in Java 12.
12. **Have you tested empty sources, single elements, and multi-group data?** These cases often expose merger bugs.

## 15. Self-Check Exercises

**Exercise 1.** To compute both the element count and the sum of a numeric field in a list, which components should you use?

**Answer:** two collectors such as `counting()` and `summingLong(...)`, plus a merger to create a record/DTO holding both results.

**Exercise 2.** In `teeing(downstream1, downstream2, merger)`, is the first argument of the merger R1 or R2?

**Answer:** R1, the result of the first downstream. The second parameter is R2.

**Exercise 3.** If the source is empty, does `teeing(minBy(...), maxBy(...), Range::new)` automatically throw an exception?

**Answer:** No; the two `minBy/maxBy` downstreams return Optional.empty, and the merger receives both Optionals to create Range. It only fails if the merger code does not handle them properly or actively throws an error.

**Exercise 4.** Why does a Summary having both `count` and `revenue` make computing the average easier?

**Answer:** the merger has both results to compute `revenue/count` and detect count=0, avoiding equating missing data with an average of 0.

**Exercise 5.** To both group by `region` and compute the total across all regions, can this be done in one collect?

**Answer:** Yes, using `teeing(groupingBy(...), summingLong(...), Report::new)`.

**Exercise 6.** To have a record containing count and total for each region key, which collector should be nested?

**Answer:** `groupingBy(Sale::region, mapFactory, teeing(counting(), summingLong(...), GroupStat::new))`.

**Exercise 7.** Does `teeing` guarantee double the speedup compared to running two separate pipelines?

**Answer:** No. It coordinates two downstreams in a single collect, but it still computes both aggregations and has overhead. Benchmark when performance is a requirement.

**Exercise 8.** If both downstreams have a Long result type, will the compiler catch swapping the names `count` and `total` in the merger?

**Answer:** Not necessarily. Both have the same type so it can compile even with fields assigned wrongly; value tests and proper naming are very important.

**Exercise 9.** Does using teeing to write to two databases in one transaction automatically guarantee all-or-nothing?

**Answer:** No. teeing is a Collector for aggregating data; transactional consistency must be designed separately.

**Exercise 10.** Why does `record Report(Map<String,Long> totals, long grandTotal)` not yet guarantee deep immutability?

**Answer:** the record protects the reference from being replaced, but the Map can still be a mutable container. To prevent a public DTO from being modified, an appropriate copying/wrapping policy is needed.

## 16. References

- [Java SE 17 — Collectors.teeing](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html#teeing(java.util.stream.Collector,java.util.stream.Collector,java.util.function.BiFunction)).
- [Java SE 17 — Collector: supplier, accumulator, combiner, finisher, and characteristics](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html).
- [Java SE 17 — Collectors.groupingBy, counting, summingLong, minBy, maxBy](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html).
- [Java SE 17 — Stream.collect](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html#collect(java.util.stream.Collector)).
- [Java SE 17 — Optional and OptionalDouble](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Optional.html).

**Remember:** **`Collectors.teeing(downstream1, downstream2, merger)`** lets you pass the same Stream elements through two aggregations and **combine the two R1/R2 results into one R in a single collect**. It is well suited for two-metric reports, min/max, nested group statistics, or combining a Map with a global total. Choose the right downstreams, check empty sources, keep merger parameter order explicit, keep callbacks safe, and do not treat teeing as a guaranteed speedup or a transaction mechanism.
