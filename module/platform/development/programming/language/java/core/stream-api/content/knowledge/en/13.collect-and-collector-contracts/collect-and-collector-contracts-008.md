# Implementing a Collector with Accumulation State and a Finisher Step

In the Java Stream API, `collect` transforms many elements into a single result such as a list, map, statistical report, or domain structure. When built-in collectors do not fully express the desired result, we can implement a **`Collector<T, A, R>`** with two distinct types to keep separate: **`A` is the temporary mutable accumulation state**, while **`R` is the result returned after the finishing step** (*finisher*).

This lesson belongs to the **Collect Mechanism and Collector** chapter of the **JAVA_STREAM_API** module. The focus is designing `supplier`, `accumulator`, `combiner`, and `finisher` so that results are correct with lazy pipelines, empty data, parallel splitting, and when results must be immutable. This knowledge directly connects `filter`, `map`, `reduce`, `collect`, `groupingBy`, custom collectors, and constraints on state, resources, and performance; `Spliterator` and Stream Gatherers are mentioned to frame the limits of a collector.

## 1. Why does a collector need accumulation state?

Suppose a sales application needs to generate **one report** from paid orders, containing:

- Total order count.
- Exact total revenue.
- Average value per order, rounded to two decimal places.
- List of order IDs in source encounter order.

If we only use `Collectors.counting()`, we get the count; if we use `Collectors.summingLong(...)`, we get a sum in `long` range; if we use `toList()`, we get a list. The problem demands **a single result object**, combining multiple metrics and handling the zero-order case separately.

A natural design is:

```text
Stream<Order>
     |
     | filter(Order::paid)
     v
Collector<Order, MutableState, SalesReport>
     |
     | supplier: creates empty MutableState
     v
 MutableState (counts, sums total, stores IDs)
     | \
     |  \ combiner: merges states of processed partitions
     v
 finisher: creates SalesReport (immutable, computes average)
     |
     v
 SalesReport
```

Adding elements to a temporary state inside `collect` is completely normal. What matters is that **that state is created and managed by the collector**, unlike updating a shared variable outside the pipeline.

## 2. The `Collector<T, A, R>` contract

The `java.util.stream.Collector` interface is parameterized by three types:

| Type | Role | In the report example |
| --- | --- | --- |
| `T` | Input element type entering the collector | `Order` |
| `A` | Accumulation container/state type | `MutableState` |
| `R` | Return result type | `SalesReport` |

Five components of a collector:

| Method | Functional type | Responsibility |
| --- | --- | --- |
| `supplier()` | `Supplier<A>` | Creates an initial, independent accumulation state |
| `accumulator()` | `BiConsumer<A, T>` | Updates state `A` with one element `T` |
| `combiner()` | `BinaryOperator<A>` | Combines two states into one state |
| `finisher()` | `Function<A, R>` | Converts state `A` into result `R` |
| `characteristics()` | `Set<Characteristics>` | Declares additional guarantees of the collector |

Semantically, sequential processing can be pictured as:

```text
A state = supplier.get()
for each T element selected by the pipeline:
    accumulator.accept(state, element)
R result = finisher.apply(state)
```

When running in parallel, the framework may create **multiple `A` states** and use `combiner` to merge them before finishing:

```text
supplier → A1 → accumulator(items 1..k)   ┐
                                           ├─ combiner(A1, A2) → A → finisher → R
supplier → A2 → accumulator(items k+1..n) ┘
```

This is a semantic model to understand the work; the JVM is entitled to execute differently as long as it obeys Stream and Collector contracts. Never assume there are always exactly two branches, or that `combiner` is always called.

## 3. Starting with a small collector

Before building a multi-field report, let's try implementing a collector that gathers **product names** into an `ArrayList<String>`.

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

public class SimpleCollectorDemo {
    public static void main(String[] args) {
        List<String> names = List.of("Java", "Stream", "API");

        Collector<String, ArrayList<String>, List<String>> collector =
            Collector.of(
                ArrayList::new,                    // supplier
                ArrayList::add,                    // accumulator
                (left, right) -> {                 // combiner
                    left.addAll(right);
                    return left;
                },
                List::copyOf                       // finisher
            );

        List<String> result = names.stream().collect(collector);
        System.out.println(result); // [Java, Stream, API]
    }
}
```

In this example:

1. `supplier` creates a temporary list, initially empty.
2. `accumulator` appends a name to that list.
3. `combiner` concatenates two temporary lists. It comes into play when a pipeline is split into multiple parts.
4. `finisher` calls `List.copyOf` to produce an **unmodifiable** list as the result.

The two types `A` and `R` are intentionally different: `A = ArrayList<String>`, whereas `R = List<String>`. Although `ArrayList` implements `List`, the finishing step here performs concrete work to create an immutable copy. Therefore this collector does **not** have the `IDENTITY_FINISH` characteristic.

This example mainly serves to explain the contract. If you only need an immutable list, `stream.toList()` or `Collectors.toUnmodifiableList()` is usually shorter. Writing a custom collector pays off when the accumulation and finishing steps encode custom business rules.

## 4. Complete example: Collector for a revenue report

We implement a realistic collector with two stages:

- **During traversal:** counts orders, sums amounts, and stores order IDs in a temporary state.
- **After completion:** creates an immutable report and computes the average; if there are no orders, the average is `Optional.empty()`.

The example below runs on **Java 17 or later**, because it uses `record` and APIs available in that version.

```java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;
import java.util.ArrayList;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collector;
import java.util.stream.Stream;

public class CustomSalesCollectorDemo {

    record Order(String id, String region, long amountVnd, boolean paid) {}

    record SalesReport(
        long count,
        BigInteger totalVnd,
        Optional<BigDecimal> averageVnd,
        List<String> orderIds
    ) {}

    // A: used internally only for accumulation, with mutable state.
    static final class MutableState {
        private long count = 0L;
        private BigInteger total = BigInteger.ZERO;
        private final List<String> ids = new ArrayList<>();

        void add(Order order) {
            count = Math.addExact(count, 1L);
            total = total.add(BigInteger.valueOf(order.amountVnd()));
            ids.add(order.id());
        }

        MutableState merge(MutableState other) {
            count = Math.addExact(count, other.count);
            total = total.add(other.total);
            ids.addAll(other.ids);
            return this;
        }

        SalesReport finish() {
            Optional<BigDecimal> average = count == 0
                ? Optional.empty()
                : Optional.of(new BigDecimal(total).divide(
                    BigDecimal.valueOf(count),
                    2,
                    RoundingMode.HALF_UP
                ));

            return new SalesReport(
                count,
                total,
                average,
                List.copyOf(ids)
            );
        }
    }

    static Collector<Order, MutableState, SalesReport> salesCollector() {
        return Collector.of(
            MutableState::new,     // Supplier<MutableState>
            MutableState::add,     // BiConsumer<MutableState, Order>
            MutableState::merge,   // BinaryOperator<MutableState>
            MutableState::finish   // Function<MutableState, SalesReport>
        );
    }

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("O-01", "Bắc", 120_000L, true),
            new Order("O-02", "Nam",  50_000L, false),
            new Order("O-03", "Bắc", 200_000L, true),
            new Order("O-04", "Nam",  30_000L, true)
        );

        SalesReport report = orders.stream()
            .filter(Order::paid)
            .collect(salesCollector());

        System.out.println(report.count());        // 3
        System.out.println(report.totalVnd());     // 350000
        System.out.println(report.averageVnd());   // Optional[116666.67]
        System.out.println(report.orderIds());     // [O-01, O-03, O-04]

        SalesReport noOrders = Stream.<Order>empty()
            .collect(salesCollector());

        System.out.println(noOrders.count());       // 0
        System.out.println(noOrders.totalVnd());    // 0
        System.out.println(noOrders.averageVnd());  // Optional.empty
        System.out.println(noOrders.orderIds());    // []
    }
}
```

### Why did the example choose these types?

- `Order.amountVnd` is `long` to illustrate money in integer VND units; input data must have validation rules ensuring accurate, business-valid values.
- `MutableState.total` uses `BigInteger` so **summing does not overflow `long` range**. If all input numbers were already stored in `long`, that does not solve errors occurring before `Order` creation.
- `MutableState.count` is `long` and uses `Math.addExact` to detect a count exceeding 64 bits.
- `SalesReport.averageVnd` is `Optional<BigDecimal>`: it can explicitly represent the **no-samples** case. The division sets `scale = 2` and `RoundingMode.HALF_UP` to illustrate a report's rounding rule; real business systems must define this rule.
- `SalesReport.orderIds` receives `List.copyOf(ids)` so it does not expose the mutable list in the accumulator. The example assumes order IDs are non-null; if data is not guaranteed, validate beforehand.

Here, `filter(Order::paid)` handles order selection **before** the collector accumulates. The collector only sees filtered orders; intermediate operators remain lazily evaluated until the `collect` terminal operation is called.

## 5. Analyzing the four implementation steps

### 5.1. `supplier`: creating new, independent state

```java
MutableState::new
```

The supplier must create a state suitable as a starting point for accumulation. For the example, an empty state has:

```text
count = 0
total = BigInteger.ZERO
ids = []
```

What matters is that **each invocation creates an independent instance**. Never use a global `MutableState` as the state for all pipelines, because multiple `collect` calls may run concurrently or in parallel.

Wrong design example:

```java
// Do not use as supplier:
MutableState shared = new MutableState();

// () -> shared  // Multiple collect runs could mutate the same object!
```

Each `collect(salesCollector())` needs to accumulate its own result. The supplier must never silently share a mutable list or map across collection runs.

### 5.2. `accumulator`: adding one element to one state

In the example:

```java
void add(Order order) {
    count = Math.addExact(count, 1L);
    total = total.add(BigInteger.valueOf(order.amountVnd()));
    ids.add(order.id());
}
```

The accumulator updates the **`MutableState` supplied to it by the framework**. This differs from two-argument `Stream.reduce`, where reduction typically returns a new combined value via a `BinaryOperator<T>`.

With `Collector`, updating an `ArrayList` or `HashMap` inside the state is valid, provided it obeys thread-confinement and merging contracts. Do not modify the Stream source, do not write to global variables, and do not require the accumulator to be called on a specific schedule.

### 5.3. `combiner`: merging two states

```java
MutableState merge(MutableState other) {
    count = Math.addExact(count, other.count);
    total = total.add(other.total);
    ids.addAll(other.ids);
    return this;
}
```

The example's combiner **mutates the left state**, merges the right state into it, and returns the left state. This is a valid strategy when both states are managed by the collector and are not accessed concurrently in violation of the contract.

Illustration of one split:

```text
Branch 1: (count = 1, total = 120000, ids = [O-01])
Branch 2: (count = 2, total = 230000, ids = [O-03, O-04])

merge(branch 1, branch 2)
       |
       v
(count = 3, total = 350000, ids = [O-01, O-03, O-04])
```

With an ordered source and a collector not declaring `UNORDERED`, design the combiner to preserve result ordering semantics. `ids.addAll(other.ids)` places the left part before the right part, fitting encounter-order preservation across combined segments.

### 5.4. `finisher`: converting temporary state into public result

```java
SalesReport finish() {
    Optional<BigDecimal> average = count == 0
        ? Optional.empty()
        : Optional.of(new BigDecimal(total).divide(
            BigDecimal.valueOf(count), 2, RoundingMode.HALF_UP
        ));

    return new SalesReport(count, total, average, List.copyOf(ids));
}
```

The finisher **does not process any more source elements**; it runs on the accumulated state. In the example, this step plays three roles:

1. Computes a derived value (the average).
2. Represents the empty case with `Optional.empty()`.
3. Creates a result that no longer allows updating the order ID list via an external reference.

Because `SalesReport` differs from `MutableState`, this collector **must execute the finisher**; it must not be marked `IDENTITY_FINISH`. Although `record` only holds `final` fields, deep immutability also depends on field types; `BigInteger`, `BigDecimal`, `Optional`, and the `List.copyOf` copy help the example avoid exposing mutable state.

## 6. Correctness contracts: identity and associativity

For the collector to produce equivalent results between sequential traversal and valid partitionings, three core operations must be compatible.

### 6.1. Empty state must be a neutral identity when combining

Let `e = supplier.get()` be a fresh empty state. When `a` already holds data, combining with an empty state must yield a result equivalent to `a` after the finisher:

```text
finish(combine(a, e))  ≡  finish(a)
```

The `≡` symbol means **observationally equivalent to the caller**, not necessarily the same object in memory. With `MutableState` above, merging a state with count 0, total 0, and an empty list leaves the result unchanged.

A typical mistake is having `supplier` initialize `count = 1` or `total = 100` to add a surcharge; if multiple states are created, that surcharge could be added multiple times. A surcharge applied **once to the final report** should go in the finisher or be applied after `collect`, per business requirements.

### 6.2. Merging parts under different groupings must be equivalent

Suppose data is split into three parts `A`, `B`, and `C`. When merging:

```text
combine(combine(A, B), C)
          ≡
combine(A, combine(B, C))
```

For count, sum, and ordered list sequences, addition and list concatenation satisfy this principle under the chosen semantics, assuming values do not hit unexpected overflow.

Choose the accumulator and combiner so that **accumulating on parts and merging** is equivalent to **accumulating everything in encounter order**. This is the core condition so results do not depend on how `Spliterator` splits the source.

### 6.3. Accumulator and combiner must express the same aggregation

If the accumulator increments `count` on each order, the combiner must add the two `count` values. If the accumulator appends an order ID, the combiner must also concatenate order IDs from both states. Summing totals while forgetting to merge order IDs in the combiner can produce a report that looks right sequentially yet misses IDs in parallel.

Avoid storing quantities derivable from other quantities if doing so makes consistency hard to maintain. For instance, computing the average in the finisher from `total / count` combines cleanly compared to maintaining a "running average" and trying to take an unweighted average of two branches.

## 7. `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT`

`Collector.Characteristics` are **behavioral commitments**, not flags to flip on for unconditional speedups.

| Characteristic | Meaning | When it may be declared |
| --- | --- | --- |
| `IDENTITY_FINISH` | Finishing step may be skipped via an unchecked cast from `A` to `R` | Result truly is the accumulation state by contract; no copying, immutability wrapping, or extra field computation needed |
| `UNORDERED` | Result does not depend on source elements' encounter order | Order has no business meaning, e.g., a set where only membership matters |
| `CONCURRENT` | Accumulator allows different threads to call it concurrently on **the same state** | Accumulation structure and all update operations inside accumulator are safe under concurrent execution |

### 7.1. When is `IDENTITY_FINISH` present?

The overload of `Collector.of` that takes no finisher:

```java
public static <T, R> Collector<T, R, R> of(
    Supplier<R> supplier,
    BiConsumer<R, T> accumulator,
    BinaryOperator<R> combiner,
    Collector.Characteristics... characteristics
)
```

Under this overload's contract, result `R` is the accumulation container itself, and `IDENTITY_FINISH` is supplied. Example:

```java
import java.util.ArrayList;
import java.util.stream.Collector;

// Order is the record in the complete example.
Collector<Order, ArrayList<String>, ArrayList<String>> idsCollector =
    Collector.of(
        ArrayList::new,
        (ids, order) -> ids.add(order.id()),
        (left, right) -> {
            left.addAll(right);
            return left;
        }
    );
```

The collected result is a modifiable `ArrayList<String>`. Do not declare `IDENTITY_FINISH` for a collector using `List.copyOf` in its finisher, because skipping the finisher would alter the properties of the result.

### 7.2. When is `UNORDERED` present?

The report in the example keeps an `orderIds` list, so **order ID sequence matters** and the collector does not declare `UNORDERED`. If a problem only computes sum/count and needs no ordering at all, you can design an order-independent collector and declare that characteristic.

Declaring `UNORDERED` may allow the framework to drop encounter-order maintenance. It does not mean results will be randomized on every run, nor does it guarantee faster execution.

### 7.3. When is `CONCURRENT` present?

Using `ArrayList.add` or updating a `long count` field with plain addition on the same container is **unsafe when multiple threads update concurrently**. Therefore `salesCollector()` **does not declare `CONCURRENT`**.

`CONCURRENT` is not needed for a collector to run in a parallel Stream: for a non-concurrent collector, the framework can create multiple separate containers for branches and then merge them with the combiner. If a collector declares `CONCURRENT`, the framework can only perform true concurrent accumulation on the same container when ordering conditions also permit, such as an unordered source or a collector with `UNORDERED`.

Do not add `CONCURRENT` just because one field in the container uses `ConcurrentHashMap`; **every related update** to count, total, lists, cross-field consistency, and finisher must satisfy the corresponding contract.

## 8. Combining a custom collector with `groupingBy`

The built collector can act as a **downstream collector** for `Collectors.groupingBy`. Each group then gets its own accumulation process, and each group is converted into a `SalesReport` in the finisher.

Suppose we reuse `Order`, `SalesReport`, and `salesCollector()` in the complete example class:

```java
import java.util.Map;
import java.util.stream.Collectors;

Map<String, SalesReport> reportByRegion = orders.stream()
    .filter(Order::paid)
    .collect(Collectors.groupingBy(
        Order::region,
        salesCollector()
    ));

System.out.println(reportByRegion.get("Bắc").totalVnd()); // 320000
System.out.println(reportByRegion.get("Nam").totalVnd()); // 30000
```

Here, `groupingBy` handles dispatching elements by `region`; `salesCollector` handles building each group's report. Do not put `region` inside `MutableState` itself just to solve grouping needs, because the collector would lose reusability on ungrouped sources.

**Case to watch out for:** a region with no paid orders normally **does not appear as a key** in the `groupingBy` result, because no elements enter that group. Unlike calling `salesCollector()` on an empty Stream to receive an empty `SalesReport`, `groupingBy` does not automatically create keys for absent groups. If the report requires every region to appear, supply the region list from the business domain source.

## 9. Comparison with three-parameter `collect` and built-in collectors

`Stream.collect` has both an overload taking a `Collector`:

```java
R collect(Collector<? super T, A, R> collector)
```

and an overload taking three functions:

```java
R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
)
```

Example collecting order IDs into an `ArrayList` with the three-parameter overload:

```java
import java.util.ArrayList;
import java.util.List;

ArrayList<String> ids = orders.stream()
    .collect(
        ArrayList::new,
        (result, order) -> result.add(order.id()),
        ArrayList::addAll
    );
```

Here, the accumulation container and result are both `ArrayList<String>`. This overload **has no finisher parameter** to produce a different-typed `SalesReport`. If final processing is needed, either do it after the `collect` call or define a `Collector<T, A, R>`.

When the result only needs normalization from an existing collector, `Collectors.collectingAndThen` often avoids writing the whole contract manually:

```java
import java.util.List;
import java.util.stream.Collectors;

List<String> immutableIds = orders.stream()
    .map(Order::id)
    .collect(Collectors.collectingAndThen(
        Collectors.toList(),
        List::copyOf
    ));
```

`collectingAndThen` attaches a finisher to another collector. When the goal is just an immutable list, `Stream.toList()` on Java 16+ is often even shorter. Prefer built-in collectors when they express business logic adequately, while `Collector.of` shines when multi-field state and a custom finishing step are required.

| Goal | Usually suitable tool |
| --- | --- |
| Create a list | `toList()`, `Collectors.toList()`, or `toCollection(...)` per mutability needs |
| Join strings with a delimiter | `Collectors.joining(delimiter)` |
| Group by key | `Collectors.groupingBy(classifier, downstream)` |
| Create an immutable result after a built-in collector | `Collectors.collectingAndThen(...)` |
| Compute a simple sum | `IntStream.sum()`, `LongStream.sum()`, `summingLong(...)` |
| Build a multi-field report with a business finishing step | `Collector.of(supplier, accumulator, combiner, finisher)` |

## 10. Collector with an empty Stream

With an empty source, a collector can still produce a valid result via the supplier's state and the finishing step:

```text
Empty Stream
    ↓
supplier() → MutableState(count=0, total=0, ids=[])
    ↓
finisher() → SalesReport(0, 0, Optional.empty(), [])
```

The example in section 4 demonstrated this scenario. Choosing `Optional.empty()` for the average distinguishes **no orders** from **an average of 0 VND** over a populated order set.

Different collectors interpret empty data differently. `Collectors.toList()` returns an empty list, `Collectors.counting()` returns `0L`, whereas extremum operations typically use `Optional` to represent missing data. If you want a three-state outcome such as `NO_DATA`, `PASS`, `FAIL`, express it explicitly with a suitable result type `R`, rather than overloading a zero or boolean.

Never assume the accumulator is necessarily called on an empty Stream; there are no elements to call it with. The finishing step must handle the container in its initial state.

## 11. Common design mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Supplier returns the same globally held `ArrayList` | Collection runs share data, risking mixed results | Create a new container on every supplier call |
| Accumulator updates a static variable or Stream source | Side effects, unstable results, race conditions | Only modify the container managed by the collector |
| Combiner omits `count` or `ids` | Parallel runs yield incomplete/wrong results | Merge every state component completely |
| Combiner does not preserve order for ordered results | `orderIds` out of encounter order | Append right after left when semantics require it |
| Computing average as simple mean of two branches | Wrong when branches differ in size | Merge `total` and `count`, then divide in finisher |
| Marking `IDENTITY_FINISH` even though finisher makes an immutable copy | Framework may skip the immutability step | Declare only when converting `A` to `R` is truly identity |
| Marking `CONCURRENT` while updating shared `ArrayList`, `long` | Lost data or wrong results during concurrent accumulation | Remove flag or design a contract-compliant concurrent accumulator |
| Marking `UNORDERED` in an ordered list collector | Encounter-order guarantees may be lost | Do not declare `UNORDERED` when order carries meaning |
| Finisher returns internal mutable list directly while advertising immutability | Callers can mutate report contents | Return a copy like `List.copyOf`, check for nulls |
| Not handling empty source before dividing for average | Division by 0 or meaningless value | Check `count == 0` and pick a suitable result type |
| Calling `collect` and then reusing the same Stream | Stream can only be consumed once | Create a new Stream from the source |
| Using a collector with mutable state and thinking `parallel()` must always be enabled | Extra overhead or bugs if contract is broken | Verify correctness first, measure performance afterward |

## 12. Performance, resources, and parallel processing

### 12.1. Keep state as small as necessary

A collector computing only sum and count typically needs two fields. In the sample report, keeping `orderIds` has memory cost proportional to **the number of retained orders**. If the result does not require the ID list, drop that field to save memory.

`List.copyOf(ids)` in the finisher also creates a result independent of the accumulation list. That cost is a deliberate trade-off to avoid exposing internal state.

### 12.2. Distinguishing addition cost from object creation cost

`BigInteger` keeps exact integer sums when totals could exceed `long`. For problems with well-known bounds safely within `long`, a collector using `long` or `Collectors.summingLong` can be simpler and allocate less. Do not use `BigInteger` or a custom collector solely because they look flexible.

On critical paths, measure **time, allocations, and memory** with representative data, for instance using JMH. Parallel pipelines have overhead for splitting the source via `Spliterator`, creating multiple containers, and combining them; a combiner concatenating large `ArrayList`s can also incur significant cost.

### 12.3. Parallel Streams and ordering

`parallelStream().collect(salesCollector())` works properly because the collector creates containers for work chunks and the combiner merges them. The collector lacking the `CONCURRENT` flag **does not prevent** a parallel Stream from running.

However, parallel is not guaranteed to be faster. Do not benchmark on a handful of elements and extrapolate to millions. If you need order IDs in source order, maintaining order also affects processing cost.

### 12.4. Sources with closable resources

With `Files.lines(path)` or Streams from I/O sources, close the resource using `try-with-resources`. The collector itself does not close the source Stream:

```java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Collectors;
import java.util.stream.Stream;

// Place inside a method declaring throws IOException or handling exceptions.
Path logFile = Path.of("app.log");

try (Stream<String> lines = Files.lines(logFile, StandardCharsets.UTF_8)) {
    long errorCount = lines
        .filter(line -> line.contains("ERROR"))
        .collect(Collectors.counting());

    System.out.println(errorCount);
}
```

If the accumulator or finisher can throw exceptions, define error-handling rules at the application layer; for instance, `Math.addExact` in the sample throws `ArithmeticException` if the count exceeds `long`. Do not use exceptions to silently "reinterpret" failures as successful reports.

## 13. Collector does not replace every stateful transformation

A Collector is applied **at the end of a pipeline** to turn a stream of elements into **one result**. If you need to emit an output value after *each* element, such as a running balance over time, a terminal collector could record the full history into a list, yet that is not equivalent to an intermediate operation emitting results one by one.

Problems emitting stateful intermediate results along a pipeline may suit a loop, a specialized `Spliterator`, or Stream Gatherers on supporting JDKs. Those techniques address different needs from a standard collector.

Within the scope of this lesson, focus on the `Collector<T,A,R>` contract: **only use mutable state when it has clear ownership, is combinable, and is finished into the proper result type**.

## 14. Practice exercises

### Exercise 1: Collector counting and summing scores

Given `record Student(String name, int score)`. Create `Collector<Student, A, Report>` returning `Report(count, sum, average)`. Use state `long count`, `long sum`; the finisher returns an `OptionalDouble` average when there are no students. Write examples with empty input and one student.

### Exercise 2: Verifying the combiner

Given paid orders, split the data into two lists. Accumulate each list into two `MutableState` instances, call `merge`, and compare with a single `collect(salesCollector())` pass over the full list. Why must **order count, total amount, and order IDs all** be merged?

### Exercise 3: Creating only an unmodifiable list

Write `Collector<String, ArrayList<String>, List<String>>` using `Collector.of`, with finisher `List.copyOf`. Try calling `result.add("X")` after collecting and explain the outcome. May `IDENTITY_FINISH` be declared?

### Exercise 4: Wrong average when merging branches

The first branch has one order worth 100, and the second branch has three orders worth 200, 300, 400. If you compute each branch's average and then average those two values, is the result right? Compute using `total/count` after merging instead.

### Exercise 5: Grouping reports by region

Extend the revenue example to `Map<String, SalesReport>` by `region` with `Collectors.groupingBy(Order::region, salesCollector())`. Try a region with zero paid orders. Why does that region not appear as a key?

### Exercise 6: Evaluating Collector characteristics

For the following three collectors, state whether `IDENTITY_FINISH`, `UNORDERED`, or `CONCURRENT` may be declared and why:

1. A collector building an `ArrayList<String>` and returning the container as-is.
2. A collector building an ordered list of order IDs, with finisher `List.copyOf`.
3. A collector gathering elements into a concurrent structure where updates to every field are proven thread-safe and the result does not depend on order.

### Exercise 7: Choosing between built-in and custom collectors

Solve three requirements: joining strings with commas, counting elements per group, and building a report with sum, count, and rounded average. Choose among `Collectors.joining`, `groupingBy`, `counting`, `collectingAndThen`, and `Collector.of`. Explain why you should only write a custom contract when it expresses requirements awkward to express with built-in collectors.

## 15. Self-check questions

- How do the three parameters `T`, `A`, and `R` of `Collector<T,A,R>` differ?
- What are the roles of `supplier`, `accumulator`, `combiner`, and `finisher`?
- Why should the supplier not return a shared state across multiple collection runs?
- Why should the average be computed after merging total and count?
- When can `IDENTITY_FINISH` be marked, and why does `List.copyOf` change the answer?
- Can a collector without the `CONCURRENT` characteristic be used with `parallelStream()`?
- When does declaring `UNORDERED` violate business requirements?
- Why does a `groupingBy` result not automatically contain a key for an absent group?
- When should `Collectors.collectingAndThen` be used instead of implementing `Collector.of` manually?
- Why does using `collect` to build a report not imply it is okay to mutate an external variable inside a lambda?
- When must `try-with-resources` be used even though the terminal operation is `collect`?

**Takeaway:** Implementing a Collector properly begins with distinguishing **accumulation state `A`** from **result `R`**, then ensuring `supplier` creates independent state, `accumulator` updates properly, `combiner` merges equivalently, and `finisher` produces the result per contract. Characteristics such as `IDENTITY_FINISH`, `UNORDERED`, and `CONCURRENT` are declared only when their conditions truly hold. That way, a collector can be used in Java Stream API pipelines clearly, safely, and verifiably.
