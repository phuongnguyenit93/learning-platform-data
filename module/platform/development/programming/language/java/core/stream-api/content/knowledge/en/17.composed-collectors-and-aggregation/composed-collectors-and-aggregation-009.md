# Combining Two Collections with teeing

A report often needs **multiple metrics over the same dataset**: order count and total revenue, lowest and highest scores, or a list of transaction IDs alongside the transaction count. You could write two independent Stream pipelines and combine their results, yet that forces traversing the source twice if it can be re-created, and does not work when data can only be read once.

Since **Java 12**, `Collectors.teeing(...)` allows **combining two collectors** within a single `collect`. Each element enters **both branch collectors**, and then a `merger` function receives the **two finished results** to produce the final result. This mechanism is especially useful for multi-metric reports and nested aggregations.

This lesson belongs to the **Composed Collectors and Aggregation** chapter of the **JAVA_STREAM_API** module. We will explore the `teeing` contract, using `counting`, `summingLong`, `minBy`, `maxBy`, `groupingBy`, and `filtering` as downstreams, while recognizing constraints around ordering, state, Stream sources, memory, associativity, and parallel performance. These principles also relate to custom collectors, `Spliterator`, and Stream Gatherers.

## 1. Why combine two collectors?

Suppose you have a list of payments and need two metrics for **paid transactions**:

1. **Number of successful transactions**.
2. **Total amount of successful transactions**.

A common approach is creating two Streams:

~~~java
long count = payments.stream()
    .filter(Payment::paid)
    .count();

long total = payments.stream()
    .filter(Payment::paid)
    .mapToLong(Payment::amountVnd)
    .sum();
~~~

These two snippets are valid if `payments` is a re-iterable collection, yet they traverse the list **twice**, run `filter` twice, and manage two independent results. With a single-use source (such as a Stream from a file), you cannot reuse **the same Stream instance** after the first terminal operation.

`teeing` expresses collecting both results in **a single terminal operation**:

~~~java
Stats result = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Payment::amountVnd),
        Stats::new
    ));
~~~

This snippet assumes `record Payment(...)` and `record Stats(long count, long totalVnd)` are declared as in the complete example below.

Crucial point: **`teeing` does not duplicate a Stream**. It constructs **one composite collector** with two branch collectors. Each element is passed to both of their accumulators during a single collection pass.

## 2. Complete example: count and total amount in a single collect

The following code can be placed in `TeeingOverviewDemo.java` and run with **JDK 17+**. `Collectors.teeing` has been available since Java 12; the example also uses `record` and `List.of` for readability.

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class TeeingOverviewDemo {
    record Payment(
        String id,
        String category,
        long amountVnd,
        boolean paid
    ) {}

    record Stats(long count, long totalVnd) {}

    public static void main(String[] args) {
        List<Payment> payments = List.of(
            new Payment("P01", "Văn phòng", 120_000L, true),
            new Payment("P02", "Sách",       70_000L, false),
            new Payment("P03", "Văn phòng",  80_000L, true),
            new Payment("P04", "Sách",      200_000L, true),
            new Payment("P05", "Văn phòng",  50_000L, false),
            new Payment("P06", "Thể thao",   60_000L, false)
        );

        Stats paidStats = payments.stream()
            .filter(Payment::paid)
            .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Payment::amountVnd),
                Stats::new
            ));

        System.out.println(paidStats);
        // Stats[count=3, totalVnd=400000]

        Map<String, Stats> paidStatsByCategory = payments.stream()
            .filter(Payment::paid)
            .collect(Collectors.groupingBy(
                Payment::category,
                Collectors.teeing(
                    Collectors.counting(),
                    Collectors.summingLong(Payment::amountVnd),
                    Stats::new
                )
            ));

        System.out.println(paidStatsByCategory.get("Văn phòng"));
        // Stats[count=2, totalVnd=200000]

        System.out.println(paidStatsByCategory.get("Sách"));
        // Stats[count=1, totalVnd=200000]

        System.out.println(paidStatsByCategory.containsKey("Thể thao"));
        // false: no paid transactions in this group
    }
}
~~~

Explanation:

- `counting()` produces the first result of type `Long`, the count of matching transactions.
- `summingLong(Payment::amountVnd)` produces the second result of type `Long`, the total amount.
- `Stats::new` is the function merging the two results into a `Stats`.
- `groupingBy(Payment::category, teeing(...))` performs the same computation **separately inside each category group**.
- Because `filter(Payment::paid)` runs before `groupingBy`, a category with only unpaid transactions (`Thể thao`) is omitted from the result.

In this example, `Map` key ordering is not guaranteed. We look up specific keys instead of assuming `Map.toString()` prints in a fixed order.

## 3. Signature and the three roles in teeing

The API signature reads:

~~~java
public static <T, R1, R2, R>
Collector<T, ?, R> teeing(
    Collector<? super T, ?, R1> downstream1,
    Collector<? super T, ?, R2> downstream2,
    BiFunction<? super R1, ? super R2, R> merger
)
~~~

| Component | Receives what? | Produces what? | Responsibility |
|---|---|---|---|
| `downstream1` | Elements `T` | Result `R1` | Collects the first metric/information |
| `downstream2` | **The same elements `T`** | Result `R2` | Collects the second metric/information |
| `merger` | Results `R1` and `R2` | Final result `R` | Combines the two results without re-traversing source |

The types `R1`, `R2`, and `R` **do not need to match**. For instance, one branch can produce `List<String>`, the other `Long`, and the final result a custom record.

### 3.1. When does teeing execute?

~~~mermaid
flowchart TD
    S["Stream<Payment>"] --> C["collect(teeing(...))"]
    C --> A["Collector 1: counting"]
    C --> B["Collector 2: summingLong"]
    A --> R1["R1: Long count"]
    B --> R2["R2: Long total"]
    R1 --> M["merger(count, total)"]
    R2 --> M
    M --> R["Stats(count, total)"]
~~~

When `collect` runs, the framework orchestrates collection into both branches. Only **after both branches finish producing their results** does `merger` combine them. It is **not** invoked once per element.

In a parallel pipeline, each branch collector can also maintain its own local containers and *combiner* before producing its final result. Container creation counts and execution scheduling are framework details and should not be relied upon in business logic.

### 3.2. Distinguishing merger from accumulator and combiner

Three easily confused concepts:

- **Accumulator of each downstream collector:** updates accumulation state upon receiving **each element `T`**.
- **Combiner of each downstream collector:** merges **two accumulation states of the same type**, especially during parallel execution.
- **`merger` of `teeing`:** receives the **two final results** `R1` and `R2` and produces `R`.

For example, `Stats::new` runs only at the final result step; it is **not responsible** for directly adding the amounts of individual input elements.

## 4. Type inference when the two branches have different results

Let us write out the types explicitly to see how it works:

~~~java
Collector<Payment, ?, Long> counter =
    Collectors.counting();

Collector<Payment, ?, Long> moneySum =
    Collectors.summingLong(Payment::amountVnd);

Collector<Payment, ?, Stats> both =
    Collectors.teeing(
        counter,
        moneySum,
        Stats::new
    );

Stats result = payments.stream()
    .filter(Payment::paid)
    .collect(both);
~~~

Here `Payment`, `Stats`, and `payments` are declared in the complete example in section 2. Compiling this standalone snippet requires importing `java.util.stream.Collector` and `java.util.stream.Collectors`.

Type table:

| Position | Type |
|---|---|
| Source element | `Payment` |
| Branch 1 result | `Long` |
| Branch 2 result | `Long` |
| `BiFunction` of `merger` | `(Long, Long) -> Stats` |
| Overall result | `Stats` |

With record `Stats(long count, long totalVnd)`, Java can unbox `Long` to `long` when calling the constructor. When the compiler fails to infer generic types inside deeply nested expressions, extract the downstreams and merger into explicitly typed variables rather than adding unsafe casts.

## 5. Example with two different output types: list and total amount

Suppose a report needs a **list of transaction IDs** and the **total amount** for the same group. One branch returns `List<String>`, and the other returns `Long`:

~~~java
record DetailReport(List<String> ids, long totalVnd) {}

DetailReport details = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.mapping(
            Payment::id,
            Collectors.toList()
        ),
        Collectors.summingLong(Payment::amountVnd),
        (ids, total) ->
            new DetailReport(List.copyOf(ids), total)
    ));

System.out.println(details.ids());
// [P01, P03, P04]

System.out.println(details.totalVnd());
// 400000
~~~

The example uses `payments` and `Payment` from section 2, along with imported `List`/`Collectors`.

Important notes:

1. `mapping(Payment::id, toList())` is a **nested collector**: it extracts IDs from `Payment` in the first branch without discarding data needed in the second branch.
2. `summingLong` reads the amount from **the exact same Payment elements**.
3. `List.copyOf(ids)` (Java 10+) produces an unmodifiable result list, protecting the report output from mutations to the intermediate list; it **rejects null elements**.
4. A record holding a `List` does not automatically make the List's contents immutable. Without `List.copyOf`, a mutable list could still be stored inside the record.

If the output must follow the source `List`'s order, `Collectors.toList()` is a downstream that can preserve the encounter order of an ordered source. On unordered Streams or `UNORDERED` collectors, do not impose expectations on ID order.

### 5.1. Need only a set of unique IDs

Replace `mapping(Payment::id, toList())` with:

~~~java
Collectors.mapping(Payment::id, Collectors.toSet())
~~~

and the first branch's result type becomes `Set<String>`. However, `toSet()` **does not guarantee iteration order**; if the report needs a sorted set, use `toCollection(TreeSet::new)` when elements are comparable.

## 6. Finding minimum and maximum in a single collect

A very natural use of `teeing` is combining `minBy` with `maxBy`. Each collector returns an `Optional<T>` because the source set may be empty.

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

public class TeeingExtremesDemo {
    record Score(String student, int point) {}
    record Extremes(
        Optional<Score> lowest,
        Optional<Score> highest
    ) {}

    public static void main(String[] args) {
        List<Score> scores = List.of(
            new Score("An", 8),
            new Score("Bình", 5),
            new Score("Chi", 9),
            new Score("Dũng", 7)
        );

        Comparator<Score> byPoint =
            Comparator.comparingInt(Score::point);

        Extremes result = scores.stream().collect(
            Collectors.teeing(
                Collectors.minBy(byPoint),
                Collectors.maxBy(byPoint),
                Extremes::new
            )
        );

        System.out.println(
            result.lowest().map(Score::student).orElse("None")
        ); // Bình

        System.out.println(
            result.highest().map(Score::student).orElse("None")
        ); // Chi
    }
}
~~~

If the score list is empty:

~~~java
Extremes empty = List.<Score>of().stream()
    .collect(Collectors.teeing(
        Collectors.minBy(byPoint),
        Collectors.maxBy(byPoint),
        Extremes::new
    ));

System.out.println(empty.lowest().isPresent());  // false
System.out.println(empty.highest().isPresent()); // false
~~~

The second snippet uses `Score`, `byPoint`, and `Extremes` from the earlier program scope. Both `minBy` and `maxBy` return empty Optionals, **yet `collect(teeing)` itself still completes and returns an `Extremes` instance** holding two empty Optional fields.

When elements tie under the comparator, do not rely on a specific tied record unless there is a tie-breaking rule. If deterministic results are required, build the comparator with secondary criteria (such as `thenComparing(Score::student)`).

### 6.1. When the output must be a single outer Optional

If business rules do not want an `Extremes` object containing two empty Optionals, the `merger` can check their state and return an `Optional<Extremes>`:

~~~java
Optional<Extremes> result = scores.stream()
    .collect(Collectors.teeing(
        Collectors.minBy(byPoint),
        Collectors.maxBy(byPoint),
        (min, max) ->
            min.isPresent() && max.isPresent()
                ? Optional.of(new Extremes(min, max))
                : Optional.empty()
    ));
~~~

This snippet uses the declarations from the full example. This is a **result presentation policy**, not `teeing`'s default behavior. Depending on the problem, keeping two separate Optionals can also be clearer.

## 7. Empty results: each downstream has its own rules

`teeing` **does not automatically return `Optional.empty()`** when the Stream is empty. It executes the contracts of both downstreams and passes their results to `merger`.

| Downstream | Result when zero elements |
|---|---|
| `counting()` | `0L` |
| `summingLong(...)` | `0L` |
| `averagingLong(...)` | `0.0` |
| `toList()` | Empty list |
| `toSet()` | Empty set |
| `minBy(...)` | `Optional.empty()` |
| `maxBy(...)` | `Optional.empty()` |
| `reducing(BinaryOperator)` | `Optional.empty()` |

Example:

~~~java
Stats noPayments = java.util.stream.Stream.<Payment>empty()
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Payment::amountVnd),
        Stats::new
    ));

System.out.println(noPayments);
// Stats[count=0, totalVnd=0]
~~~

Here `Payment` and `Stats` come from section 2. **`Stats(0, 0)` can be interpreted as a valid statistics result**, yet it does not automatically distinguish “no transactions” from “transactions exist whose sum is 0”. If the report needs to distinguish them, use `count` to detect data presence.

### 7.1. Computing an average requires handling a zero denominator

If you want to compute an average from `count` and `total`, never divide without checking `count == 0`:

~~~java
import java.util.OptionalDouble;

OptionalDouble average = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.summingLong(Payment::amountVnd),
        Collectors.counting(),
        (total, count) -> count == 0L
            ? OptionalDouble.empty()
            : OptionalDouble.of((double) total / count)
    ));

System.out.println(average.orElse(Double.NaN));
// 133333.33333333334 with three successful transactions
~~~

Here `OptionalDouble.empty()` is the business choice when there are no elements. If you only need a **single average value**, `mapToLong(Payment::amountVnd).average()` already returns `OptionalDouble` and can be shorter. Use `teeing` when you truly need **two distinct collections** or a combined report.

For currency, using `double` can cause rounding errors. Choose integer minor units and explicit rounding policies or `BigDecimal` when exact arithmetic is required.

## 8. Composing teeing inside groupingBy

One strength of `teeing` is that it can serve as the **downstream** of `groupingBy`. Then each group gets its own two-branch statistics:

~~~java
Map<String, Stats> byCategory = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.groupingBy(
        Payment::category,
        Collectors.teeing(
            Collectors.counting(),
            Collectors.summingLong(Payment::amountVnd),
            Stats::new
        )
    ));
~~~

Table corresponding to the example in section 2:

| Category | Paid transaction count | Total amount |
|---|---:|---:|
| Văn phòng | 2 | 200.000 |
| Sách | 1 | 200.000 |
| Thể thao | *No key* | *No key* |

Each group's statistics branch receives only elements **within that group**. `teeing` does not flatten groups or share one `Stats` across all categories.

### 8.1. Keeping groups with zero results via downstream filtering

Suppose you need to show even categories that have transactions yet **have zero paid transactions** (`Thể thao` in this example). Filtering `paid` before `groupingBy` makes that group vanish.

Place **`Collectors.filtering`** (Java 9+) **inside** the group and **outside** `teeing`:

~~~java
Map<String, Stats> includingZero = payments.stream()
    .collect(Collectors.groupingBy(
        Payment::category,
        Collectors.filtering(
            Payment::paid,
            Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Payment::amountVnd),
                Stats::new
            )
        )
    ));

System.out.println(includingZero.get("Thể thao"));
// Stats[count=0, totalVnd=0]
~~~

Here:

1. `groupingBy(Payment::category)` sees **all transactions**, so it creates the `Thể thao` group.
2. `filtering(Payment::paid, ...)` passes only **paid transactions** of each group to the downstream.
3. `teeing` aggregates the count and total amount over the filtered data.
4. A group with zero qualifying transactions still produces `Stats(0, 0)`.

**Note:** If a category **has zero transactions at all in the source**, `groupingBy` does not automatically create a key for it. To include every valid category even when absent from the source, the application needs a standard category list and a step to populate missing groups.

### 8.2. When must filtering be placed separately on each branch?

Two metrics sometimes use **two different conditions**, such as the count of successful transactions and the total amount of failed transactions. Then each branch must filter by its own rule:

~~~java
record TwoStates(long paidCount, long unpaidTotalVnd) {}

TwoStates result = payments.stream().collect(Collectors.teeing(
    Collectors.filtering(
        Payment::paid,
        Collectors.counting()
    ),
    Collectors.filtering(
        p -> !p.paid(),
        Collectors.summingLong(Payment::amountVnd)
    ),
    TwoStates::new
));

System.out.println(result);
// TwoStates[paidCount=3, unpaidTotalVnd=180000]
~~~

Here `TwoStates` is declared as a Java 16+ record. Unpaid transactions are `P02` (70,000), `P05` (50,000), and `P06` (60,000), so the sum is **180,000**.

Key point: both downstreams of `teeing` **receive the full input stream**, yet each `filtering` downstream has its own predicate. You cannot place `stream.filter(Payment::paid)` before `teeing` if the second branch needs to see unpaid transactions.

## 9. Combining three aggregations via nested teeing

`teeing` accepts **exactly two downstreams**. When three or more metrics are needed, you can nest another `teeing` inside one branch and merge the results:

~~~java
record Tail(long totalVnd, long highestVnd) {}
record FullStats(long count, long totalVnd, long highestVnd) {}

FullStats result = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.teeing(
            Collectors.summingLong(Payment::amountVnd),
            Collectors.collectingAndThen(
                Collectors.maxBy(
                    java.util.Comparator.comparingLong(Payment::amountVnd)
                ),
                max -> max.map(Payment::amountVnd).orElse(0L)
            ),
            Tail::new
        ),
        (count, tail) ->
            new FullStats(count, tail.totalVnd(), tail.highestVnd())
    ));

System.out.println(result);
// FullStats[count=3, totalVnd=400000, highestVnd=200000]
~~~

The example uses `Payment` and `payments` from section 2. `Tail` is merely an intermediate object packaging the results of the two inner branch collectors.

This code is valid, yet **not necessarily the best way** to get count, sum, and maximum. When all metrics belong to the same numeric attribute, `Collectors.summarizingLong` is usually simpler:

~~~java
java.util.LongSummaryStatistics stats = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.summarizingLong(Payment::amountVnd));

System.out.println(stats.getCount()); // 3
System.out.println(stats.getSum());   // 400000
System.out.println(stats.getMax());   // 200000
~~~

Choose `teeing` when you want to combine **two distinct results or two different kinds of analysis** into a meaningful result type. Do not nest `teeing` merely because you can.

## 10. How does teeing differ from reduce and custom collectors?

| Scenario | Suitable tool | Why |
|---|---|---|
| Only summing integers | `mapToLong(...).sum()` | Short, direct, avoids intermediate boxing |
| Only need count/sum/min/max/average of one numeric field | `summarizingLong(...)` | Built-in multi-metric statistics object |
| Combining two existing reports, like `counting` and `toList` | `teeing(...)` | Reuses two collectors and merges results cleanly |
| Grouping data, each group returning two metrics | `groupingBy(..., teeing(...))` | Each group gets its own combined report |
| Need specialized accumulation state or more than two coupled metrics | Custom collector | Full control over container, accumulator, combiner, and finisher |
| Combining immutable values with an associative operation | `reduce(...)` | Clear non-mutating reduction contract |

### 10.1. teeing does not replace every custom collector

`teeing` maintains **two separate accumulation mechanisms**. If two metrics share a lot of intermediate data or require tightly coupled statistical fields, a custom collector with **a single container** can reduce allocations or work; however, you must verify the supplier/accumulator/combiner/finisher contract yourself.

Conversely, when two standard collectors already match the goal, `teeing` keeps code readable and avoids re-implementing accumulation logic, especially with complex downstreams.

### 10.2. teeing is not like reduce with a mutable pair

Do not build a mutable `Pair` and pass it into `reduce(identity, accumulator, combiner)` by mutating the same accumulation object. Such a `reduce` easily violates identity/associativity contracts and breaks in parallel runs.

`teeing` fits within **mutable reduction via Collector**: each branch collector manages its intermediate container per contract, while `merger` works only with finalized results.

## 11. Collector characteristics and parallel processing

A collector has **characteristics** such as `UNORDERED`, `CONCURRENT`, and `IDENTITY_FINISH`. With `teeing`, characteristics can be inherited based on the compatibility of **both downstreams**.

In principle:

- Only when **both** downstreams support `CONCURRENT` can the combined collector advertise that concurrency characteristic.
- Only when **both** downstreams are `UNORDERED` can the combined collector advertise unorderedness.
- `teeing` **never carries `IDENTITY_FINISH`**, because the results must pass through `merger`.

Actual characteristics are determined by the downstreams' APIs; **do not guess** that `teeing(toList(), counting(), ...)` can share a single result container across multiple threads.

### 11.1. Running in parallel does not mean sharing one container

~~~java
Stats parallelStats = payments.parallelStream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Payment::amountVnd),
        Stats::new
    ));

System.out.println(parallelStats);
// Stats[count=3, totalVnd=400000]
~~~

On the sample dataset, the result matches the sequential run. The framework manages local accumulation and merging per collector contract; never use an external mutable `ArrayList` or `HashMap` as a shared variable across two branches.

For instance, **never** write:

~~~java
java.util.ArrayList<String> sharedIds =
    new java.util.ArrayList<>();

// Do not collect via external side effects:
// payments.parallelStream().forEach(p -> sharedIds.add(p.id()));
~~~

`ArrayList` is not thread-safe. Even with a synchronized structure, ordering and performance still must match business goals. If you want a list in one branch of `teeing`, use `mapping(..., toList())` or an appropriate collector.

### 11.2. Do not use merger to mutate the source or trigger external side effects

`merger` should be pure: take two results and construct a clear combined result. Avoid using it to send notifications, write to databases, or mutate shared state. With parallel Streams, intermediate callbacks and combiners can run on different threads/orders; even though `merger` creates the final result, side effects there still make code hard to test and reuse.

When I/O is needed after the report is ready, separate it into a step **after `collect`**. For example:

~~~java
Stats stats = payments.stream()
    .filter(Payment::paid)
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Payment::amountVnd),
        Stats::new
    ));

System.out.println("Report computed: " + stats);
~~~

## 12. Ordering, null, and data stability

### 12.1. Encounter order still matters if one branch collects a List

A `List` source is ordered; `Collectors.toList()` can preserve element order according to encounter order. Yet if the pipeline calls `unordered()` or the source has no encounter order, do not expect the list branch to reflect a specific order.

Downstreams like `counting` and `summingLong` are semantically independent of element order when arithmetic is exact and does not overflow; collectors that pick a representative on ties (like `minBy` with a comparator lacking a tie-breaker) can have stronger requirements on order or priority rules.

### 12.2. Null must be handled according to each branch's contract

`teeing` does not remove `null` automatically. If source elements can be null, a branch like `mapping(Payment::id, ...)` or `summingLong(Payment::amountVnd)` can throw `NullPointerException`.

~~~java
import java.util.Arrays;
import java.util.Objects;

List<Payment> safePayments = Arrays.asList(
    new Payment("P01", "Sách", 100L, true),
    null
);

Stats safeStats = safePayments.stream()
    .filter(Objects::nonNull)
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingLong(Payment::amountVnd),
        Stats::new
    ));
~~~

Beyond null inputs, each downstream has its own policy: `toUnmodifiableList()` rejects null elements, `groupingBy` forbids a classifier from returning null keys under standard Java contracts, and `minBy` with a comparator that cannot handle null can also fail.

Do not assume both branches will always treat null identically. Normalize or validate data **before** collection whenever possible.

### 12.3. Do not mutate the source while collecting

Lambdas such as `Payment::amountVnd` or `Payment::paid` must be non-interfering and not depend on external state changing mid-traversal. If source objects are mutated during parallel execution, the two branches can observe inconsistent data and the report will no longer be consistent.

If a report needs a **snapshot** of continuously changing data, you need a snapshotting or transaction strategy at the source layer. `teeing` unifies two collections within one pipeline, yet **does not guarantee an atomic snapshot** against concurrent external mutations.

## 13. Resources and performance: one pass does not mean the cost of one collector

### 13.1. Advantages

- One `collect` pipeline can build **two metrics** without running two separate Streams.
- Reuses existing collectors, reducing hand-written accumulator/combiner boilerplate.
- Fits single-use sources or sources where re-traversal is expensive.
- Composes easily with `groupingBy` or downstreams like `filtering` and `mapping`.

### 13.2. Limitations

- Every element is processed by **both branches**; it is not a free computation.
- Two collectors can retain **two distinct accumulation states**. If one branch is `toList` and the other is `toSet`, memory grows with the sizes of both results.
- If both branches traverse and build complex structures, a custom collector sharing state may save resources—though you should benchmark rather than guess.
- `teeing` is a terminal collection: on an unbounded infinite source, the collector generally **cannot complete**.
- `summingLong` can overflow `long`; floating-point statistics have rounding errors and can depend on operation order.

### 13.3. Comparison with two separate collects

~~~java
long count = payments.stream().filter(Payment::paid).count();

long total = payments.stream()
    .filter(Payment::paid)
    .mapToLong(Payment::amountVnd)
    .sum();
~~~

Two separate pipelines can be easier to read in some small situations, yet they traverse the source twice. `teeing` combines them in one pipeline; however, it also creates/merges two accumulators and runs the final merger. On small datasets, **never claim** it is always faster. For performance-critical paths, measure with a real benchmark on your application's JDK and source type.

### 13.4. Do not use teeing to solve Stream termination issues

The following example **must not be run**:

~~~java
// Unbounded infinite source with no termination condition.
// java.util.stream.Stream.iterate(1, n -> n + 1)
//     .collect(Collectors.teeing(
//         Collectors.counting(),
//         Collectors.summingInt(Integer::intValue),
//         (count, sum) -> count + ":" + sum
//     ));
~~~

`counting` and `summingInt` must consume the entire source to return a result. When the source never ends, collection cannot produce a final result. If you need a finite window:

~~~java
String firstFive = java.util.stream.IntStream
    .iterate(1, n -> n + 1)
    .limit(5)
    .boxed()
    .collect(Collectors.teeing(
        Collectors.counting(),
        Collectors.summingInt(Integer::intValue),
        (count, sum) -> count + " elements, sum = " + sum
    ));

System.out.println(firstFive);
// 5 elements, sum = 15
~~~

The `limit(5)` bound ensures this pipeline has a finite number of elements.

## 14. Common mistakes when using teeing

| Misconception / mistake | Risk | Fix |
|---|---|---|
| Thinking `teeing` splits a Stream into two independent Streams | Misunderstands lifecycle and traversal | Treat it as **one Collector with two branches** |
| Thinking `merger` runs per element | Misplaces accumulation logic | Put accumulation in downstreams; only combine final results in merger |
| Using `counting` and `summingLong` and dividing by count directly | Division by 0 on empty source | Check `count == 0` and define a policy |
| Using `minBy/maxBy` and calling `Optional.get()` directly | Throws exception if source is empty | Handle Optional via `map`/`orElse`/`orElseThrow` |
| Using `groupingBy` after `filter` while wanting count-0 groups | Groups with all non-matching elements vanish | Use downstream `filtering` inside the group |
| Wanting two different conditions yet filtering once before `teeing` | Second branch loses needed data | Put separate `filtering` on each branch |
| Using `toList` and assuming the list inside a record is immutable | List may be mutable | Wrap with `List.copyOf` if needed, and handle nulls |
| Mutating shared List/Map in `parallelStream` | Race condition | Use a contract-compliant collector |
| Thinking merger decides `CONCURRENT` characteristic | Misunderstands characteristic inheritance from both downstreams | Check both collectors' contracts; never assume arbitrarily |
| Using `teeing` for numeric metrics already covered by `summarizingLong` | Unnecessarily nested, hard-to-read code | Prefer dedicated collectors when appropriate |
| Collecting over an infinite source | Aggregation never terminates | Bound the source or use a finite window |
| Assuming `teeing` takes an atomic snapshot | Both branches still read a potentially mutating source | Stabilize data before the pipeline |
| Believing parallel is always faster | Splitting and merging overhead can dominate | Benchmark and verify thread-safety requirements |

## 15. Exercise: grouped task completion report

A system has tasks with `id`, `team`, `effort`, and `done`. Build a report using `teeing`, then combine it with `groupingBy`.

**Requirements:**

1. Count **completed** tasks and sum their `effort` in a **single `collect`**.
2. Build `Map<String, Metrics>` grouped by `team`, keeping groups with zero completed tasks with `count = 0` and `total = 0`.
3. From `count` and `total`, compute the average effort of completed tasks; when there is no data, represent the missing state explicitly.
4. Do not use mutable lists outside the pipeline to count or collect.
5. Explain why `stream.filter(Task::done)` before `groupingBy` would not keep a group that has only incomplete tasks.

### Reference solution (Java 17+)

~~~java
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.stream.Collectors;

public class TeeingPractice {
    record Task(String id, String team, long effort, boolean done) {}
    record Metrics(long count, long total, OptionalDouble average) {}

    static Metrics toMetrics(long count, long total) {
        OptionalDouble average = count == 0L
            ? OptionalDouble.empty()
            : OptionalDouble.of((double) total / count);
        return new Metrics(count, total, average);
    }

    public static void main(String[] args) {
        List<Task> tasks = List.of(
            new Task("T01", "Backend", 5L, true),
            new Task("T02", "Frontend", 8L, false),
            new Task("T03", "Backend", 3L, true),
            new Task("T04", "QA", 4L, false),
            new Task("T05", "Frontend", 2L, true)
        );

        Metrics allDone = tasks.stream()
            .filter(Task::done)
            .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Task::effort),
                TeeingPractice::toMetrics
            ));

        Map<String, Metrics> byTeam = tasks.stream()
            .collect(Collectors.groupingBy(
                Task::team,
                Collectors.filtering(
                    Task::done,
                    Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Task::effort),
                        TeeingPractice::toMetrics
                    )
                )
            ));

        System.out.println(allDone.count()); // 3
        System.out.println(allDone.total()); // 10
        System.out.println(allDone.average().orElse(Double.NaN));
        // 3.3333333333333335

        System.out.println(byTeam.get("Backend").total()); // 8
        System.out.println(byTeam.get("Frontend").total()); // 2
        System.out.println(byTeam.get("QA").count());       // 0
        System.out.println(byTeam.get("QA").average().isPresent());
        // false
    }
}
~~~

In the solution:

- Completed tasks are `T01`, `T03`, and `T05`, with total effort `5 + 3 + 2 = 10`.
- `toMetrics` is the **merger** reused for both the overall aggregation and per-group aggregation.
- `groupingBy(Task::team)` creates groups Backend, Frontend, and QA from the **entire source**.
- `filtering(Task::done, teeing(...))` forwards only completed tasks into the two-branch collector. QA has no completed tasks, yet still has a group and merges into `Metrics(count=0, total=0, average=empty)`.
- `OptionalDouble.empty()` for the no-data case distinguishes “no average available” from “actual average is 0”.

### Self-check questions

1. Which Java version introduced `Collectors.teeing`? — **Java 12**.
2. How many downstreams and what function does `teeing` take? — **Two downstream collectors** and one **BiFunction merger**.
3. Does `merger` receive each `Payment` or the final results of each collector? — **The two collected results**.
4. Can you use `teeing(counting(), mapping(..., toList()), merger)`? — **Yes**, the two branches can have different result types.
5. Does `teeing(minBy(...), maxBy(...), ...)` return null automatically on an empty source? — **Not by default**; both downstreams return `Optional.empty()` and then the merger decides the result.
6. When should you use `summarizingLong` instead of nesting multiple `teeing` calls? — When you only need standard metrics like count, sum, min, max, and average of **the same numeric field**.
7. Does `teeing` have the `IDENTITY_FINISH` characteristic? — **No**, because it must run the merger.
8. How do you keep the `QA` group if it has only incomplete tasks? — Group first with `groupingBy`, and place `filtering` inside the downstream.
9. Can a Stream source used with `teeing` be consumed again after `collect`? — **No**, you must create a fresh Stream from a reusable source.
10. Is `teeing` guaranteed to run faster than two separate pipelines? — **No**; you must consider element count, branch costs, memory, and execution mode.

## 16. Summary and practical guidance

**`Collectors.teeing(downstream1, downstream2, merger)`** combines **two collections over the same elements** in a single terminal `collect`. The two downstreams can return different types; `merger` turns the two results into a business-meaningful value. Remember this is **collector composition**, not Stream merging or duplication.

When composed with `groupingBy`, each group can return a multi-metric report. Place `filtering` **outside `teeing` but inside `groupingBy`** if groups with count 0 must be kept; place `filtering` **separately on each `teeing` branch** if the two metrics use independent conditions.

Always check **empty sources**, **Optional**, **numeric types and overflow**, **ordering**, **null**, **mutable collector state**, and **parallel accumulation cost**. When standard numeric statistics suffice, prefer `summarizingLong` or primitive Streams; when two downstreams cleanly express the problem, `teeing` builds a clear result without writing a complex custom collector.
