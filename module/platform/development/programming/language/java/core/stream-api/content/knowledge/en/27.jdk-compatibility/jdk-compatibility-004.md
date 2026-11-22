# Combining Collectors with teeing Since Java 12

In the Java Stream API, we often end a pipeline with a single collection step: counting records, summing amounts, finding the maximum value, or grouping elements. Yet many reports need **two different results over the same set of elements**, such as counting transactions and summing revenue, finding both minimum and maximum values, or counting valid and invalid records together.

Since **Java 12**, `Collectors.teeing(...)` combines **two downstream Collectors** and a **merger** function into **a single new Collector**. Each element enters both collection branches; when both finish, the merger combines the two results into the final output type. This lets you express a two-way report in **one terminal `collect`** rather than re-traversing the source or building a custom accumulator for every scenario.

This lesson belongs to the **JDK Compatibility** chapter of the `JAVA_STREAM_API` module. Beyond syntax, we will analyze version requirements, data types, empty sources, `Optional`, interactions with `groupingBy`/`mapping`/`filtering`, Collector characteristics, parallel processing, arithmetic precision, I/O sources, and alternatives on Java 8–11. Examples build on lazy pipelines with `filter`, `map`, `reduce`, and `collect`.

> **Compatibility milestone:** `Collectors.teeing` is an official API since **Java 12**, unavailable in Java 8–11. Code using `teeing` must compile against Java 12+ APIs and run on a compatible runtime. Examples use regular classes instead of `record` so they do not inadvertently require Java 16.

## 1. Why Combine Two Collectors?

Suppose we have scores:

```text
80, 65, 90, 50
```

We want to report the **total number of scores** and the **average score**. The obvious approach is traversing twice:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> scores = Arrays.asList(80, 65, 90, 50);

long count = scores.stream().count();
double average = scores.stream()
        .mapToInt(Integer::intValue)
        .average()
        .orElse(0.0);

System.out.println(count);   // 4
System.out.println(average); // 71.25
```

For an in-memory `List`, creating two new Streams can be acceptable. However, when the source is a file, a single-pass Iterator, or upstream processing before `collect` is resource-intensive, repeating the pipeline may be inconvenient or infeasible.

What you **must not do** is call two terminal operations on **the same Stream instance**:

```java
// WRONG: the same Stream cannot be consumed twice.
java.util.stream.Stream<Integer> stream = scores.stream();

long numberOfScores = stream.count();
// The following call will be invalid because the stream is already consumed.
long sum = stream.mapToLong(Integer::longValue).sum();
```

`teeing` solves the problem when you want to produce **one composite result** from two Collectors reading the same logical stream of elements.

## 2. API Signature and Three Parameters

The general method signature:

```java
public static <T, R1, R2, R> Collector<T, ?, R> teeing(
        Collector<? super T, ?, R1> downstream1,
        Collector<? super T, ?, R2> downstream2,
        BiFunction<? super R1, ? super R2, R> merger
)
```

Meaning:

| Symbol | Meaning |
| --- | --- |
| `T` | Input element type of the Stream |
| `R1` | Final result of the first Collector |
| `R2` | Final result of the second Collector |
| `R` | Combined result type produced by the merger |
| `downstream1` | Collects the first independent result |
| `downstream2` | Collects the second independent result |
| `merger` | Takes results `R1`, `R2` and produces `R` |

Mental model:

```text
                         Stream<T>
                             |
                      filter / map / ...
                             |
                     collect(teeing)
                             |
                    each input element
                     /               \
                    v                 v
             downstream1         downstream2
               T -> R1             T -> R2
                    \                 /
                     \               /
                           merger
                        (R1,R2) -> R
                             |
                         result R
```

**Every element passing through the combined Collector is accumulated into both downstreams.** However, the merger **does not run per element**: it only receives **the two finished results** to build the final result.

`teeing` is a **Collector factory**, whereas `stream.collect(...)` is the terminal operation triggering execution. `teeing` does not turn into a new intermediate operation like `map` or `filter`.

### First Example: Counting and Averaging

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(80, 65, 90, 50);

Map.Entry<Long, Double> result = scores.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.averagingInt(Integer::intValue),
                Map::entry
        ));

System.out.println(result.getKey());   // 4
System.out.println(result.getValue()); // 71.25
```

Here:

- `Collectors.counting()` returns `Long`.
- `Collectors.averagingInt(...)` returns `Double`.
- `Map::entry` combines the two values into `Map.Entry<Long,Double>`.

`Map.entry(k,v)` is a factory introduced in **Java 9**, so it fits Java 12 examples. This Entry does not support `setValue`. Do not choose it if you need a report object with clearly named fields; `Map.Entry` is mainly suited for brief illustrations.

The core takeaway is that `Map.Entry` represents the pair of results while `Collectors.teeing` executes both collections in a single source consumption.

## 3. One Source Pass Does Not Mean One Computation

Each input element is passed to **both downstream accumulators**:

```text
Element "A" --+--> collector 1: increment count
              |
              +--> collector 2: update total length
```

Thus `teeing` avoids **two source consumptions**, yet is **not free**: both Collectors do their own work. If they both compute an expensive expression from `T`, that expression may be evaluated twice.

Example avoiding computing normalization twice:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<String> rawNames = Arrays.asList(
        "  An  ", "Binh ", "  Chi"
);

Map.Entry<Long, Long> overview = rawNames.stream()
        .map(String::trim) // shared normalization, before teeing
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(String::length),
                Map::entry
        ));

System.out.println(overview.getKey());   // 3
System.out.println(overview.getValue()); // 9
```

With trimmed names `"An"`, `"Binh"`, `"Chi"`, total length is `2 + 4 + 3 = 9`. `map(String::trim)` is placed **before** teeing so normalization happens once in the shared pipeline rather than repeating in each Collector.

**Design mindset:** place transformations and filters **needed by both branches** before `teeing`. Transformations **needed by only one branch** go inside its downstream via `mapping` or `filtering`.

## 4. Returning a Report DTO Instead of an Anonymous Value Pair

In real applications, `getKey()` and `getValue()` do not clearly describe business intent. Create a report type with explicit field names:

```java
public final class ScoreReport {
    private final long count;
    private final double average;

    public ScoreReport(long count, double average) {
        this.count = count;
        this.average = average;
    }

    public long count() {
        return count;
    }

    public double average() {
        return average;
    }

    @Override
    public String toString() {
        return "ScoreReport{count=" + count
                + ", average=" + average + "}";
    }
}
```

Use a constructor reference as the merger:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(80, 65, 90, 50);

ScoreReport report = scores.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.averagingInt(Integer::intValue),
                ScoreReport::new
        ));

System.out.println(report);
// ScoreReport{count=4, average=71.25}
```

`ScoreReport::new` receives `Long` and `Double`, which Java automatically unboxes to `long` and `double` matching the constructor signature.

This is a standout strength of `teeing`: the two results `R1` and `R2` need not share the same type, and the merger can return any suitable type `R`.

**Java 12 note:** `record ScoreReport(long count, double average)` was not yet official syntax in Java 12. When keeping source compatible with Java 12, use a regular class as shown above.

## 5. Empty Sources: Do Not Mistake 0.0 for Real Data

A common pitfall when designing reports:

```java
import java.util.Collections;
import java.util.stream.Collectors;

ScoreReport emptyReport = Collections.<Integer>emptyList()
        .stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.averagingInt(Integer::intValue),
                ScoreReport::new
        ));

System.out.println(emptyReport.count());   // 0
System.out.println(emptyReport.average()); // 0.0
```

`Collectors.counting()` yields `0L` for an empty source. `Collectors.averagingInt(...)` also returns `0.0` for an empty source. However, **`0.0` is a Collector-defined default**, not necessarily "the true average is 0" in business terms.

If you need to distinguish "no scores" from "an average of 0 over real data", use `OptionalDouble`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.OptionalDouble;
import java.util.stream.Collectors;

List<Integer> scores = Arrays.asList(80, 65, 90, 50);

OptionalDouble average = scores.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingLong(Integer::longValue),
                (count, total) -> count == 0L
                        ? OptionalDouble.empty()
                        : OptionalDouble.of(
                                (double) total / count
                        )
        ));

System.out.println(average.getAsDouble()); // 71.25
```

On an empty source, the merger returns `OptionalDouble.empty()`. This pattern represents a **potentially absent average** much more clearly.

The `summingLong` accumulator still has `long`'s range limit and can overflow on extremely large data; it serves only as an example for small-domain scores. If business logic requires exact decimals or sums exceeding `long`, choose a different data type and addition operation rather than assuming `teeing` solves arithmetic issues automatically.

### Rules for Handling Missing Data

A `List<Integer>` may contain `null`. Neither `Integer::intValue` nor `Integer::longValue` accepts null as a numeric value, so define an explicit policy:

```java
import java.util.Arrays;
import java.util.Objects;

List<Integer> raw = Arrays.asList(80, null, 65, 90);

ScoreReport validOnly = raw.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.averagingInt(Integer::intValue),
                ScoreReport::new
        ));

System.out.println(validOnly.count()); // 3
```

Here `count` is the **number of valid scores**, not the total number of input records. If the report needs the count of missing data, add a separate statistic or design a combined collector capturing full information. Do not silently substitute `0` for null scores if that distorts the meaning of the average.

## 6. Combining minBy and maxBy in One Collector

Another use case for `teeing` is finding **minimum** and **maximum** values while still distinguishing an empty source.

Define the result type:

```java
public final class IntRange {
    private final int min;
    private final int max;

    public IntRange(int min, int max) {
        this.min = min;
        this.max = max;
    }

    public int min() {
        return min;
    }

    public int max() {
        return max;
    }

    @Override
    public String toString() {
        return "[" + min + ", " + max + "]";
    }
}
```

Compute the result:

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

List<Integer> values = Arrays.asList(-2, 11, 7, 20, 4);

Optional<IntRange> range = values.stream()
        .collect(Collectors.teeing(
                Collectors.minBy(Comparator.naturalOrder()),
                Collectors.maxBy(Comparator.naturalOrder()),
                (min, max) -> min.flatMap(
                        low -> max.map(high ->
                                new IntRange(low, high))
                )
        ));

System.out.println(range); // Optional[[-2, 20]]
```

Both `minBy` and `maxBy` return `Optional<Integer>`. If there are no elements, both Optionals are empty and the merger produces `Optional.empty()`.

Do not pick `0` as an "initial max value" when the source may contain negative numbers; that approach can invent a value that never existed in the source.

**Simpler option:** if you only need min and max of `int`, `IntStream.summaryStatistics()` (Java 8) already provides `count`, `sum`, `min`, `max`, and `average`. `teeing` is not mandatory when a specialized API already provides all needed statistics.

## 7. Combining counting and reducing with BigDecimal

A business scenario: summarizing **paid transaction count** and **total amount**. Monetary data requires decimal precision, so use `BigDecimal` instead of accumulating `double` values.

Transaction class:

```java
import java.math.BigDecimal;

public final class Payment {
    private final String orderId;
    private final BigDecimal amount;
    private final boolean paid;

    public Payment(String orderId, String amount, boolean paid) {
        this.orderId = orderId;
        this.amount = new BigDecimal(amount);
        this.paid = paid;
    }

    public String orderId() {
        return orderId;
    }

    public BigDecimal amount() {
        return amount;
    }

    public boolean isPaid() {
        return paid;
    }
}
```

Result class:

```java
import java.math.BigDecimal;

public final class PaymentReport {
    private final long paidCount;
    private final BigDecimal paidTotal;

    public PaymentReport(long paidCount, BigDecimal paidTotal) {
        this.paidCount = paidCount;
        this.paidTotal = paidTotal;
    }

    public long paidCount() {
        return paidCount;
    }

    public BigDecimal paidTotal() {
        return paidTotal;
    }
}
```

Applying `teeing`:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Payment> payments = Arrays.asList(
        new Payment("O01", "12.50", true),
        new Payment("O02", "7.25", false),
        new Payment("O03", "3.75", true)
);

PaymentReport paid = payments.stream()
        .filter(Payment::isPaid)
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.mapping(
                        Payment::amount,
                        Collectors.reducing(
                                BigDecimal.ZERO,
                                BigDecimal::add
                        )
                ),
                PaymentReport::new
        ));

System.out.println(paid.paidCount()); // 2
System.out.println(paid.paidTotal()); // 16.25
```

Design points:

1. `filter(Payment::isPaid)` is placed before `teeing` because **both branches** only care about paid transactions.
2. `counting()` counts transactions passing the filter.
3. `mapping(Payment::amount, reducing(...))` extracts amounts and adds them as `BigDecimal`.
4. `PaymentReport::new` combines the two results into a DTO.

If a transaction has `amount == null`, `BigDecimal::add` cannot process it. Define a policy to skip, error, or model absent values **before** collecting.

### Why Can reducing Be Used Here?

`Collectors.reducing(identity, operator)` is a valid downstream Collector. For `BigDecimal` addition, `BigDecimal.ZERO` is the identity element, and `BigDecimal::add` returns a new value without mutating old objects. Thus the operation safely combines separate branch results when the pipeline runs in parallel.

This differs from using `reduce` to mutate a shared `ArrayList`. For mutable containers, `collect` and an appropriate Collector are the safe choice.

## 8. Two Different Conditions: Using filtering in Each Branch

Sometimes both branches inspect **the same source**, yet each branch counts **a different category of records**. For example, counting scores passing and failing a threshold of 60.

`Collectors.filtering(predicate, downstream)` was introduced in **Java 9**, so it is available whenever `teeing` is used on Java 12.

Define the result type:

```java
public final class PassFail {
    private final long passed;
    private final long failed;

    public PassFail(long passed, long failed) {
        this.passed = passed;
        this.failed = failed;
    }

    public long passed() {
        return passed;
    }

    public long failed() {
        return failed;
    }
}
```

Pipeline:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> results = Arrays.asList(90, 45, 70, 60, 10);

PassFail summary = results.stream()
        .collect(Collectors.teeing(
                Collectors.filtering(
                        score -> score >= 60,
                        Collectors.counting()
                ),
                Collectors.filtering(
                        score -> score < 60,
                        Collectors.counting()
                ),
                PassFail::new
        ));

System.out.println(summary.passed()); // 3
System.out.println(summary.failed()); // 2
```

Here you **cannot** place `filter(score -> score >= 60)` before `teeing` because the failing-score branch would **no longer see** scores below 60.

Diagram:

```text
            90 45 70 60 10
                    |
                  teeing
                 /      \
       >= 60 + count    < 60 + count
             |                |
          passed=3         failed=2
                 \          /
                   PassFail
```

If invalid scores such as `-1` or `null` can appear, the two conditions `>=60` and `<60` no longer cover the full data rules. Place a shared domain-validation filter before teeing, or add a dedicated error-statistics branch. `teeing` combines **two** direct downstreams only; for more metrics, `teeing` can be nested, though avoid making nesting hard to read.

## 9. teeing as a Downstream of groupingBy

A major strength of `teeing` is that it **returns a Collector**. Therefore, this Collector can be used as a downstream of `groupingBy`.

Problem: for each department, return **headcount** and **total payroll**.

### Data Model

```java
public final class Employee {
    private final String department;
    private final long salary;

    public Employee(String department, long salary) {
        this.department = department;
        this.salary = salary;
    }

    public String department() {
        return department;
    }

    public long salary() {
        return salary;
    }
}
```

Group result:

```java
public final class DepartmentReport {
    private final long headcount;
    private final long payroll;

    public DepartmentReport(long headcount, long payroll) {
        this.headcount = headcount;
        this.payroll = payroll;
    }

    public long headcount() {
        return headcount;
    }

    public long payroll() {
        return payroll;
    }
}
```

### Collecting by Department

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Employee> employees = Arrays.asList(
        new Employee("Engineering", 100),
        new Employee("Support", 80),
        new Employee("Engineering", 150)
);

Map<String, DepartmentReport> reports = employees.stream()
        .collect(Collectors.groupingBy(
                Employee::department,
                Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(Employee::salary),
                        DepartmentReport::new
                )
        ));

System.out.println(reports.get("Engineering").headcount()); // 2
System.out.println(reports.get("Engineering").payroll());   // 250
System.out.println(reports.get("Support").payroll());       // 80
```

Each group has a two-component downstream accumulator. When an employee is assigned to `Engineering`, **both branches of `teeing` inside that group** see that employee.

**Empty-group case:** `groupingBy` only creates keys for departments present in the data. If there are no `QA` employees, the Map does not automatically add `QA → DepartmentReport(0,0)`. To show all expected departments, populate missing keys from a department catalog when building the report.

**Null keys:** `groupingBy(Employee::department)` does not allow the classifier to return `null`. If an unknown department is possible, filter it, normalize it with a non-colliding sentinel key, or use a key type like `Optional<String>`. `teeing` does not alter this grouping contract.

## 10. teeing with Two Downstreams Returning Different Types

The two Collectors do not need to return the same type. You can obtain a set of unique statuses and count records simultaneously:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

List<String> states = Arrays.asList(
        "NEW", "PAID", "NEW", "FAILED"
);

Map.Entry<Long, Set<String>> info = states.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.toSet(),
                Map::entry
        ));

System.out.println(info.getKey());              // 4
System.out.println(info.getValue().size());     // 3
System.out.println(info.getValue().contains("PAID")); // true
```

Here `R1 = Long`, `R2 = Set<String>`, `R = Map.Entry<Long,Set<String>>`. However, do not assume the resulting set has a stable iteration order: `Collectors.toSet()` is an unordered collector.

If you need a **sorted set**, pick `toCollection(TreeSet::new)`; if you need a **list including duplicates in encounter order**, use `toList()` instead of `toSet()`.

`Map.Entry` in the example is only unmodifiable at the level of rejecting mapping updates via `setValue`; it does not make the inner `Set` immutable. Do not infer immutability propagating into contained objects.

## 11. Characteristics of the teeing Collector

Every `Collector` has a set of `characteristics()`, including:

- `CONCURRENT`: the accumulator can receive concurrent calls on the same container per contract.
- `UNORDERED`: the Collector does not promise to preserve encounter order.
- `IDENTITY_FINISH`: the accumulation result can be used directly instead of running a finisher.

For `teeing`, the characteristics mean:

| Characteristic | When Does the teeing Collector Have It? | Reason |
| --- | --- | --- |
| `CONCURRENT` | **Both downstreams** have `CONCURRENT` | The combined container is only safe when both branches allow shared concurrent updates |
| `UNORDERED` | **Both downstreams** have `UNORDERED` | The combined result is order-independent only if neither branch needs order |
| `IDENTITY_FINISH` | **Never declared** | Must still finish both downstreams and invoke the merger |

You can think of this as **the intersection of downstream characteristics, excluding `IDENTITY_FINISH`**.

Example:

```java
import java.util.Set;
import java.util.stream.Collector;
import java.util.stream.Collectors;

Collector<String, ?, Long> combined =
        Collectors.teeing(
                Collectors.counting(),
                Collectors.counting(),
                Long::sum
        );

Set<Collector.Characteristics> characteristics =
        combined.characteristics();

System.out.println(
        characteristics.contains(
                Collector.Characteristics.IDENTITY_FINISH
        )
); // false

System.out.println(
        characteristics.contains(
                Collector.Characteristics.CONCURRENT
        )
); // false
```

Even if the merger "merely returns a pair" or performs no extra calculation, `teeing` is still not an identity-finish collector under the API contract.

### Interaction with Parallel Streams

`teeing` can still run on `parallelStream()` without `CONCURRENT`. The framework can create multiple combined accumulators for partitions, then merge **each pair of downstream states** using their combiners.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

List<Integer> numbers = Arrays.asList(1, 2, 3, 4, 5);

Map.Entry<Long, Integer> summary = numbers.parallelStream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingInt(Integer::intValue),
                Map::entry
        ));

System.out.println(summary.getKey());   // 5
System.out.println(summary.getValue()); // 15
```

The sum and count results here match multi-branch combining. Yet `parallelStream()` is **not automatically faster**; allocating containers, splitting data, running combiners, and invoking the merger all have costs.

In particular, one downstream having `CONCURRENT` is not enough for the whole `teeing` to be concurrent. If only the first branch is thread-safe while the second uses a plain `ArrayList`, declaring the combined container concurrent would be wrong.

## 12. What Should the merger Function Do and Avoid?

`merger` is a `BiFunction<R1,R2,R>`. It runs at the finishing step to combine the results of the two Collectors; do not design it as an accumulator updated after every element.

A good merger should:

1. Accept the two result types exactly as promised by the downstream Collectors.
2. Produce a result with clear business meaning.
3. Define a policy for empty sources or empty Optionals.
4. Avoid writing to global variables, files, or external collections since it is part of a data computation.
5. Not lose or mutate downstream data in ways the caller does not expect.
6. Stay lightweight; if it just constructs a DTO, do so directly with a constructor reference.

### Example of a Merger Performing Extra Computation

Need to compute the pass rate of scores:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> points = Arrays.asList(90, 45, 70, 60, 10);

double passRate = points.stream()
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.filtering(
                        score -> score >= 60,
                        Collectors.counting()
                ),
                (total, passed) -> total == 0L
                        ? Double.NaN
                        : 100.0 * passed / total
        ));

System.out.println(passRate); // 60.0
```

Since 3 out of 5 scores pass, the rate is 60%.

Here `Double.NaN` is chosen for an empty set to represent "no samples to calculate a rate"; in production code you can return `OptionalDouble` or a DTO with an explicit flag.

If the data source can contain invalid scores, define the denominator: if the denominator counts only valid scores, filter them **before** teeing; if you also want the input-error rate, add a corresponding statistic.

## 13. When Should You Not Use teeing?

`teeing` is very useful, but not the best API for every case.

### Only One Number Needed

If you only want the element count, `count()` is shorter:

```java
long count = scores.stream().count();
```

If you only want an integer sum:

```java
int sum = scores.stream()
        .mapToInt(Integer::intValue)
        .sum();
```

Do not introduce `teeing` just to "look modern".

### Same Standard Integer Statistics Set

`IntSummaryStatistics` on `IntStream` has returned count, sum, min, max, and average in a single terminal operation since Java 8:

```java
import java.util.IntSummaryStatistics;

IntSummaryStatistics stats = scores.stream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();

System.out.println(stats.getCount());   // 4
System.out.println(stats.getSum());     // 285
System.out.println(stats.getAverage()); // 71.25
```

When all required outputs fit in a standard statistics object, `summaryStatistics()` is simpler than `teeing`. Note that `getMin()`/`getMax()` on empty statistics have specific sentinel values; check `getCount()` before treating them as actual extrema.

### Result Needs More Than Two Independent Branches

You can nest `teeing`:

```java
// Illustrative code; multiple layers of teeing make code hard to read.
Collectors.teeing(
        Collectors.counting(),
        Collectors.teeing(
                Collectors.summingInt(Integer::intValue),
                Collectors.averagingInt(Integer::intValue),
                Map::entry
        ),
        Map::entry
)
```

However, a nested `Map.Entry<Long,Map.Entry<Integer,Double>>` result is hard to read and easy to misinterpret field meanings. For more than two metrics or interdependent states, a **custom Collector** returning a clearly named DTO is usually easier to maintain.

### Two Branches Need Very Different Source Splits

`teeing` sends **every element** to **both downstreams**. It is not a mechanism to fork into two independent Streams with separate lifecycles. When two branches need different subsets, `Collectors.filtering` can handle it, but if the logic is complex or per-branch cost is high, consider a custom Collector or another processing architecture.

## 14. Java 8–11: Alternatives Without teeing

On JDKs older than Java 12, you cannot just add an import or rename a package to get `Collectors.teeing`. If the project must keep source/runtime on Java 8–11, several options exist depending on data shape.

### 14.1. Use summaryStatistics When Sufficient

For `count + average` like the first example, Java 8 already has:

```java
import java.util.IntSummaryStatistics;

IntSummaryStatistics summary = scores.stream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();

long count = summary.getCount();
double average = summary.getAverage();
```

This does not require `teeing`, avoids boxing after `mapToInt`, and consumes the source only once.

### 14.2. Use Three-Parameter collect with a Custom Accumulator

If you need two independent counts such as passing/failing scores, you can create a mutable accumulator with a parallel-compatible combiner:

```java
final class PassCounter {
    private long passed;
    private long failed;

    void add(Integer value) {
        if (value >= 60) {
            passed++;
        } else {
            failed++;
        }
    }

    void merge(PassCounter other) {
        passed += other.passed;
        failed += other.failed;
    }

    long passed() {
        return passed;
    }

    long failed() {
        return failed;
    }
}
```

Collect:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> points = Arrays.asList(90, 45, 70, 60, 10);

PassCounter result = points.stream()
        .collect(
                PassCounter::new,
                PassCounter::add,
                PassCounter::merge
        );

System.out.println(result.passed()); // 3
System.out.println(result.failed()); // 2
```

This is the `Stream.collect(supplier, accumulator, combiner)` overload available since Java 8. Each accumulator provided by the Supplier is independent; the combiner merges two partial results. Do not create a single `PassCounter` outside and share it across all branches.

The example assumes `points` contains no `null` and negative scores are still classified as failing. If the valid score domain must be 0–100, add appropriate validation.

### 14.3. Traverse Twice Only When the Source Is Re-Creatable

With a `List`, creating two new Streams is simple and sometimes good enough. Yet if the source is a file, socket, or single-use Iterator, **you must not reuse the same Stream** after a terminal operation has consumed it.

When you need two results in a single pass without `teeing`, choose one of these strategies:

- `summaryStatistics` if the problem can be expressed using standard statistics;
- three-parameter `collect` with a custom container;
- a custom Collector via `Collector.of` if a finisher, characteristics, or reusability is needed;
- a clear sequential loop when logic is highly specialized.

Splitting into two intermediate `List`s just to re-collect can increase memory usage unnecessarily.

## 15. Source, Bytecode, and Runtime Compatibility

When upgrading the Java Stream API, separate three concepts:

| Factor | Question to Answer | With teeing |
| --- | --- | --- |
| **Compiler JDK** | Which version is the compiler running? | Needs `javac` recent enough to know Java 12 APIs |
| **API level (`--release`)** | Which standard libraries may the source call? | `--release 11` forbids calling `teeing` |
| **Runtime JDK** | Which JVM version runs the program? | Runtime must support the corresponding API/bytecode |

Example:

```text
javac -version
java -version
```

To compile source using `Collectors.teeing` with a modern JDK supporting the Java 12 target:

```text
javac --release 12 Example.java
```

If that same source is compiled with:

```text
javac --release 11 Example.java
```

the compiler reports it cannot find `Collectors.teeing` (or another API incompatibility error) because this API does not exist in Java 11. **`--release` does not only adjust the bytecode version**; it restricts the set of standard APIs the code is permitted to use.

Running a program compiled for Java 12 on a Java 11 runtime is **not guaranteed** and is typically rejected due to the newer class-file version or missing API. Even if someone tries compiling with an older bytecode target while still linking against newer APIs, the old runtime still does not provide `Collectors.teeing`.

**Environment note:** `--release 12` requires a `javac` version supporting target release 12. Future JDKs may not maintain every very old target; check the list of releases actually supported by your compiler rather than assuming every newer JDK always accepts every target.

### Version Table of Related APIs

| API or Syntax | Introduced in Official Java Release |
| --- | --- |
| `Stream`, `Collectors.groupingBy`, `reducing`, `mapping`, `counting`, `summaryStatistics` | Java 8 |
| `Collectors.filtering`, `flatMapping`, `Stream.takeWhile`/`dropWhile`, `Map.entry` | Java 9 |
| `Collectors.teeing` | **Java 12** |
| `Stream.toList()` | Java 16 |
| `record` (official language syntax) | Java 16 |
| `Stream.gather` and `Gatherers` (official API) | Java 24 |

Because this lesson targets Java 12, examples use `collect(Collectors.toList())` instead of `Stream.toList()`, and regular classes instead of `record`. Do not copy `Stream.gather(...)` into a codebase targeting Java 12 because that is a newer-version API.

To manage policy for a module with multiple JDK targets, you can isolate a compatibility layer: implement with `teeing` on the branch requiring Java 12+, while the Java 8–11 branch uses a custom accumulator returning **the same output DTO type**. This keeps the business API stable across versions.

## 16. Reading an I/O Source and Returning a Report in One Pass

When the source is a file, `teeing` is especially convenient because it can compute two metrics while building **only one line-reading pipeline**.

Example counting non-empty lines and total characters across those lines:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map.Entry<Long, Long> inspectText(Path path)
        throws IOException {

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        return lines
                .map(String::trim)
                .filter(line -> !line.isEmpty())
                .collect(Collectors.teeing(
                        Collectors.counting(),
                        Collectors.summingLong(String::length),
                        Map::entry
                ));
    }
}
```

If the file contains:

```text
Java

Stream
API
```

and no other data lines, after removing blank lines there are `3` lines, with total character count `4 + 6 + 3 = 13`.

`Files.lines` is a lazy I/O source and **holds resources**. `collect`, even with `teeing`, **does not close the Stream automatically**. `try-with-resources` ensures closing the source after the report completes or if an exception occurs.

Read errors during Stream traversal can be wrapped into `UncheckedIOException`. `String::trim` and `filter` do not replace encoding or file-format validation. If you need length in **Unicode code points** rather than UTF-16 code units, `String.length()` is insufficient; use a different counting rule.

### One Logical Pass and Resource Limits

`teeing` helps you avoid writing:

```java
// Do not reopen/reread the file just for another statistic,
// if both can be aggregated in a single pass.
long lines = ...;
long characters = ...;
```

However, "one pass" does not mean "reading one byte at a time": Reader buffering and the filesystem govern I/O details. Nor does it mean `teeing` protects against the file being modified mid-processing; that is a data-source consistency concern.

## 17. Performance and Safety When Using teeing

`teeing`'s strength is **organizing two accumulations in one Collector**, not guaranteeing it is faster than every alternative.

### Small Sources and Light Computations

If there are only a few dozen integers in a `List`, creating two Streams can be fast and simple enough; `IntSummaryStatistics` is even cleaner when standard metrics suffice. Do not optimize based solely on API novelty.

### Both Downstreams Have Their Own Cost

Each element goes to **both** downstream accumulators. If each side must hash, parse, or access mutable structures, both costs still exist. Place shared transformations before `teeing` to avoid redundant recomputation.

### Parallel Streams and Ordering

`teeing` is not automatically a concurrent collector. With `parallelStream()`, Java may create multiple containers and merge via combiners. If one downstream needs ordering, do not arbitrarily mark the entire pipeline `unordered()` just for speed.

For example, `teeing(toList(), counting(), ...)` contains a branch requiring encounter order. Because `counting()` does not make `toList()` unordered, the combined result must still respect the list branch's ordering requirement.

### Side Effects and Correctness

Avoid lambdas in downstreams or mergers that mutate an external variable:

```java
// WRONG by design: side effects outside the pipeline are not collection results.
long[] externalCount = {0};

scores.parallelStream()
        .peek(x -> externalCount[0]++)
        .collect(Collectors.teeing(
                Collectors.counting(),
                Collectors.summingInt(Integer::intValue),
                Map::entry
        ));
```

`externalCount[0]++` is unsafe under parallel streams, and `peek` is not how business logic should determine counts. Use the `counting()` result already provided inside `teeing`.

### Resources and Memory

If the first downstream is `toList()`, all elements reaching the Collector can be retained in memory, even if the second downstream only counts. `teeing` does not magically turn a list-collecting Collector into an `O(1)` memory aggregation.

If you only need counts, sums, or extrema, choose downstreams with small state; for massive data, check numeric domain limits, element counts, and source characteristics before enabling parallel execution.

## 18. Common Mistakes

| Mistake | Consequence | How to Fix |
| --- | --- | --- |
| Using `Collectors.teeing` when compiling with `--release 11` | Compiler cannot find the API | Raise target to Java 12+ or use a Java 8 solution |
| Thinking `teeing` has existed since Java 8 like `groupingBy` | Wrong version assumption | Note Java 12 explicitly |
| Using `Stream.toList()` in code requiring Java 12 compatibility | `Stream.toList` appeared in Java 16 | Use `collect(Collectors.toList())` |
| Using `record` in Java 12 source | `record` syntax was not official in Java 12 | Use regular classes/DTOs |
| Calling `count()` then `collect()` on the same Stream | Stream is already consumed | Use `teeing` or create a new Stream from a re-creatable source |
| Thinking `merger` runs on every element | Wrong accumulator design | Merger only combines the two completed downstream results |
| Forgetting empty-source handling | `averagingInt` returns 0.0, easily misread in reports | Check count or use `OptionalDouble` |
| Placing `filter(passed)` before `teeing` when the other branch needs failed items | Failed branch no longer sees the data | Use `Collectors.filtering` inside each branch |
| Inferring `teeing` is always `CONCURRENT` when one branch is concurrent | Breaks thread-safety contract | Both downstreams must be concurrent |
| Inferring `teeing` is always `UNORDERED` if one branch is unordered | The other branch may require encounter order | Unordered only when both are unordered |
| Thinking `teeing` is `IDENTITY_FINISH` if merger creates a pair | Has finishers for both branches plus merger | Never declare `IDENTITY_FINISH` |
| Combining two `toList()` downstreams and thinking memory is low because of one pass | Both lists still occupy memory | Retain only the metrics needed |
| Using `groupingBy(...,teeing(...))` and expecting absent groups to appear | `groupingBy` creates only encountered groups | Backfill from expected group catalog |
| Using `groupingBy` with a null classifier | `NullPointerException` | Normalize keys / reject invalid records |
| Writing side effects to external variables from `peek` in parallel | Races and unreliable results | Put counting inside the Collector |
| Using `Files.lines` without closing because you think `teeing` closes it | I/O resource leak | `try-with-resources` |
| Ignoring overflow in `summingInt`/`summingLong` | Wrong results on huge datasets | Pick appropriate numeric domain / overflow-detection strategy |

## 19. Workflow for Choosing a Collector for a Two-Metric Report

When receiving an aggregation requirement, determine step by step:

1. **Which runtime and target JDK?** If below Java 12, do not pick `teeing` as a required API.
2. **Do both metrics use the same element subset?** If yes, place shared filter/transformation before `teeing`.
3. **Which metrics depend on separate conditions?** Use downstream `filtering`/`mapping` instead of dropping data needed by the other branch.
4. **How should empty results be represented?** Distinguish `0`, `0.0`, and "no data".
5. **Is a specialized collector already sufficient?** For standard count/min/max/sum/average, check `summaryStatistics` first.
6. **What should the output type be?** `Map.Entry` for quick examples; a named-field DTO for business code.
7. **Is grouping needed?** Combine `groupingBy(classifier, teeing(...))`, remembering absent groups.
8. **Are parallelism and encounter order needed?** Inspect characteristics of both downstreams.
9. **Are there memory and resource limits?** Choose collectors holding only needed statistics, and close I/O sources.
10. **Have you tested empty input, single element, multiple elements, nulls, negative numbers, and large data?**

## 20. Practice Exercises

### Exercise A: Order Statistics by Status

Data includes `paid` and `unpaid` orders. Use `teeing` to return a `PaymentReport` with `paidCount` and `paidTotal`, without including unpaid orders in the total. Test empty sources and multiple orders with identical amounts.

**Hint:** place `filter(Payment::isPaid)` before `teeing`. When you also need to count unpaid orders, use separate `filtering` branches or a multi-state Collector.

### Exercise B: min–max in One Terminal Operation

Write `Collectors.teeing(minBy(...), maxBy(...), merger)` returning `Optional<IntRange>`. Test with sources:

```text
[]
[7]
[-10, -1, -5]
[100, 2, 100]
```

Expected results respectively:

```text
Optional.empty
Optional[7,7]
Optional[-10,-1]
Optional[2,100]
```

The strings shown above are logical descriptions; the exact `toString()` of `Optional<IntRange>` depends on `IntRange.toString()`.

### Exercise C: Statistics by Department

From `List<Employee>`, build `Map<String, DepartmentReport>` with `headcount` and `payroll`, then add the `QA` department if the system requires a complete catalog report.

**Criteria:** do not re-traverse the employee list per department; grouping keys must not be null; unseen groups are handled explicitly.

### Exercise D: Java 8–11 Compatibility

Write `PassCounter` with `add` and `merge` for passed/failed counts without using `teeing`. Compare results against the Java 12 version using `teeing(filtering(...), filtering(...), ...)` on the same data.

**Criteria:** identical results sequentially and in parallel, without sharing a mutable accumulator outside the Supplier.

### Exercise E: Checking Compile Targets

In a development environment with a suitable JDK, compile a class calling `Collectors.teeing` with `--release 12` and with `--release 11`. Explain why the second case cannot access the API.

**Note:** do not use `record`, `Stream.toList()`, or newer APIs when writing Java 12 source.

## 21. Self-Check Questions

1. Which official Java version introduced `Collectors.teeing`? **Java 12**.
2. How many parameters does `teeing` accept? **Three: downstream1, downstream2, merger**.
3. Must the two downstreams return the same type? **No**, they can return different `R1` and `R2`.
4. Does the merger run on each element or on the two completed results? **On the two completed downstream results**.
5. Is `teeing` a terminal operation? **No**, it creates a Collector; `stream.collect(...)` is the terminal operation.
6. With `counting` and `averagingInt` on an empty source, what are the results? **0L and 0.0**.
7. Why might `0.0` from `averagingInt` on an empty source need special handling? **Because there are no samples, unlike a true average of 0 from real data**.
8. What is `Collectors.filtering` inside a teeing branch used for? **Selecting elements for that branch alone without excluding them from the other branch**.
9. Can `teeing` serve as a downstream of `groupingBy`? **Yes**, because it returns a Collector.
10. Does `groupingBy(..., teeing(...))` automatically create groups that never appeared? **No**.
11. If only one downstream is concurrent, does `teeing` have the `CONCURRENT` characteristic? **No**.
12. If both downstreams are unordered, can `teeing` have `UNORDERED`? **Yes**.
13. Does a teeing Collector have `IDENTITY_FINISH`? **No**, because both downstreams must finish and then the merger must run.
14. Can `summaryStatistics` in Java 8 replace `teeing` for counting and averaging? **Yes**, if standard statistics suffice.
15. Does calling `collect(teeing(...))` on a Stream from `Files.lines` automatically close the file? **No**, the Stream must be closed with `try-with-resources`.
16. Does a teeing Collector make the two accumulators cost nothing to compute? **No**, it only organizes both aggregations in a single source pass.
17. Can `record` be used as official syntax when source must be Java 12-compatible? **No**, use a class.
18. With `javac --release 11`, will `Collectors.teeing` compile? **No**, the API is not part of Java 11.
19. When more than two metrics are needed, is infinite nesting of `teeing` required? **No**, you can create a custom Collector or use specialized statistics.
20. Why check merge/combiner behavior when using `teeing` with a parallel stream? **Because each downstream may merge accumulators from multiple branches and must preserve its contract**.

**Guideline for use:** `Collectors.teeing` from Java 12 fits when you need **two distinct aggregation results from a single Stream** combined into a DTO or report structure. Place shared operations before `teeing`, place branch-specific conditions inside downstreams, handle empty sources explicitly, and choose readable result representations. Do not use `teeing` merely because it is newer: `summaryStatistics`, `count`, `sum`, or a custom Collector may be simpler. Finally, verify the target JDK, parallel safety, memory limits, and I/O source lifecycle before putting the solution into production.