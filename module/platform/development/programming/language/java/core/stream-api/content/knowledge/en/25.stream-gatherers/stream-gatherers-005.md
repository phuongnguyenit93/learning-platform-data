# Accumulating and Emitting State with `Gatherers.scan`

> **Chapter:** Stream Gatherer  
> **Module:** `JAVA_STREAM_API` — declarative data processing with Java Stream API via lazy pipelines, `filter`, `map`, `reduce`, and `collect`; practicing grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers, while recognizing limits around state, resources, and performance.

When summing a list of numbers, `sum()` and `reduce()` normally return only **the final result**. However, some business requirements need **the state after each event**: account balance after each transaction, inventory after each stock in/out, cumulative revenue after each order, or error counts encountered so far while processing logs.

`Gatherers.scan` solves this kind of problem by maintaining an accumulated state, updating it for each input element, and **emitting the new state after each element** into the pipeline. It is a built-in gatherer, making it easy to express a *prefix scan* without writing a custom `Gatherer` from scratch.

**JDK requirement:** `java.util.stream.Gatherers` and `Stream.gather(...)` became official APIs in **Java 24**. The examples below use **JDK 24 or later**; they will not compile on Java 17. In Java 22/23, Gatherers were a preview feature, whose enabling flags and signatures must be checked against the corresponding JDK version.

After this lesson, you will be able to:

1. Explain the two parameters `initial` and `scanner` of `Gatherers.scan`.
2. Distinguish **the initial state** from **the emitted states**, especially with empty sources.
3. Produce sequences of running totals, transaction balances, and multi-field intermediate metrics.
4. Combine `scan` with `filter`, `map`, `limit`, and terminal operations; understand laziness, short-circuiting, and encounter order.
5. Choose properly among `scan`, `reduce`, `collect`, and custom gatherers; avoid shared-state bugs or wrong assumptions under parallel execution.

## 1. Essence: each input element produces a next state

Given an ordered source `x1, x2, x3, ...` and an initial state `s0`, `scan` produces:

```text
s0 = initial.get()
s1 = scanner(s0, x1)     → emit s1
s2 = scanner(s1, x2)     → emit s2
s3 = scanner(s2, x3)     → emit s3
...
```

The key thing to remember is that **`s0` itself is not emitted**. If the input has three elements and every step completes normally, `scan` emits three states: `s1`, `s2`, `s3`.

Running total example:

```text
Input:             2       3       5
                   │       │       │
Initial s0 = 0     │       │       │
                   ▼       ▼       ▼
scan by addition:  2  ───►  5  ───► 10
Output:            2       5      10
```

If you only call `reduce(0, Integer::sum)`, the result is **a single number `10`**, not the three numbers `2, 5, 10`.

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Integer> runningTotals = List.of(2, 3, 5).stream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();

System.out.println(runningTotals); // [2, 5, 10]
```

Here, `List.of(...).stream()` creates a `Stream<Integer>`, `gather(...)` is an intermediate operation producing another `Stream<Integer>`, and `toList()` is the terminal operation triggering evaluation.

## 2. API signature and roles of `initial` and `scanner`

The conceptual method signature is:

```java
public static <T, R> Gatherer<T, ?, R> scan(
        Supplier<R> initial,
        BiFunction<? super R, ? super T, ? extends R> scanner
)
```

This is a signature illustrating the generic types; in code, `Supplier` and `BiFunction` belong to `java.util.function`, while `Gatherer` and `Gatherers` belong to `java.util.stream`.

| Component | Role | Example |
| --- | --- | --- |
| `T` | Input element type | `Integer`, `Order`, `Transaction` |
| `R` | Accumulated state type and also output element type | `Long`, `BigDecimal`, `RunningState` record |
| `Supplier<R> initial` | Creates initial state for **one collection pass** | `() -> 0`, `() -> BigDecimal.ZERO` |
| `BiFunction<R,T,R> scanner` | Receives previous state and new element, returns next state | `Integer::sum`, `(sum, x) -> sum.add(x)` |

The following example shows the output does not have to share the source's type:

```java
import java.util.List;
import java.util.stream.Gatherers;

List<Long> counts = List.of("Java", "Stream", "API").stream()
        .gather(Gatherers.<String, Long>scan(
                () -> 0L,
                (count, ignoredWord) -> Math.addExact(count, 1L)
        ))
        .toList();

System.out.println(counts); // [1, 2, 3]
```

The input is `String`, while state and output are `Long`. The explicit type witness `<String, Long>` makes `T` and `R` clear, although in many expressions the compiler can infer them.

### Why use a `Supplier`?

Instead of passing a shared state object, `scan` accepts a function that **creates the initial state**. This matters when a Gatherer is reused across different pipelines: each execution must have its own state so results from a previous run do not leak into the next.

With immutable records or `BigDecimal` as state, initialization and creating new values are straightforward to control. With mutable state, be especially careful not to return a list or map shared across multiple runs.

## 3. Comparing `scan`, `reduce`, `collect`, and `map`

Suppose the input is `[2, 3, 5]`:

| Approach | Typical result | When to choose |
| --- | --- | --- |
| `map(n -> n * 2)` | `[4, 6, 10]` | Each input turns into one output, **no need to remember the past**. |
| `reduce(0, Integer::sum)` | `10` | Only need **a single final sum**. |
| `collect(Collectors.summingInt(...))` | `10` | Collect into a final result via a collector. |
| `gather(Gatherers.scan(() -> 0, Integer::sum))` | `[2, 5, 10]` | Need **every prefix sum** during traversal. |

These serve four distinct goals. `map` can run independently on each element; `scan` requires the accumulated result of the previous element to compute the next. `reduce` and `collect` mainly build **a final result**, whereas `scan` emits a **Stream of intermediate states** for subsequent steps to process.

If you only need the final sum and do not care about intermediate sums, `sum()` or `reduce()` is usually simpler and easier to optimize. Do not use `scan(...).reduce((a, b) -> b)` just to get the final sum when a plain `sum()` solves it.

## 4. Initial state and empty sources

The initial state is used **before the first element**, yet it is not an extra emitted output:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Integer> one = Stream.of(7)
        .gather(Gatherers.scan(() -> 100, Integer::sum))
        .toList();

List<Integer> empty = Stream.<Integer>empty()
        .gather(Gatherers.scan(() -> 100, Integer::sum))
        .toList();

System.out.println(one);   // [107]
System.out.println(empty); // []
```

| Input | Initial value | Update operation | `scan` output |
| --- | ---: | --- | --- |
| `[]` | 100 | Add | `[]` |
| `[7]` | 100 | Add | `[107]` |
| `[7, 3]` | 100 | Add | `[107, 110]` |
| `[7, 3, -4]` | 100 | Add | `[107, 110, 106]` |

If business logic needs to display the balance **before the first transaction occurred**, add it explicitly in the presentation layer or construct a controlled concatenated Stream. Do not mistake `scan` for prepending the initial value to the output.

### Do not replace `scan` with `Stream.iterate`

`Stream.iterate` generates new elements based on the previous element, but does not consume **transactions from another source** and fold them into each step of the state. `scan` is designed to consume **an existing input source** and update state according to that source.

## 5. Complete example: account balance after each transaction

A customer has an opening balance of **100.00** currency units. Three events occur during the period:

| Transaction | Change | Balance after transaction |
| --- | ---: | ---: |
| TX-01 | +25.50 | 125.50 |
| TX-02 | -10.00 | 115.50 |
| TX-03 | +5.25 | 120.75 |

We need a `List<BalanceRow>` in **exact transaction order**, with each row containing the processing ordinal, transaction ID, and balance **after applying** that transaction.

Save the code below as `GatherersScanDemo.java` on **JDK 24+**:

```java
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

public class GatherersScanDemo {

    record Transaction(String id, BigDecimal change) {
        Transaction {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(change, "change");
            if (id.isBlank()) {
                throw new IllegalArgumentException("ID must not be blank");
            }
        }
    }

    // Intermediate state after a number of processed transactions.
    record RunningState(
            long processed,
            String lastTransactionId,
            BigDecimal balance
    ) {}

    // Record published for report readers.
    record BalanceRow(
            long ordinal,
            String transactionId,
            BigDecimal balance
    ) {}

    static List<Transaction> sample() {
        return List.of(
                new Transaction("TX-01", new BigDecimal("25.50")),
                new Transaction("TX-02", new BigDecimal("-10.00")),
                new Transaction("TX-03", new BigDecimal("5.25"))
        );
    }

    static List<BalanceRow> timeline(
            List<Transaction> transactions,
            BigDecimal openingBalance
    ) {
        Objects.requireNonNull(transactions, "transactions");
        Objects.requireNonNull(openingBalance, "openingBalance");

        return transactions.stream()
                .gather(Gatherers.<Transaction, RunningState>scan(
                        // S0 is not an output yet: state before any transaction.
                        () -> new RunningState(0L, "", openingBalance),

                        // Each transaction produces a new state.
                        (state, tx) -> new RunningState(
                                Math.addExact(state.processed(), 1L),
                                tx.id(),
                                state.balance().add(tx.change()))
                ))
                .map(state -> new BalanceRow(
                        state.processed(),
                        state.lastTransactionId(),
                        state.balance()))
                .toList();
    }

    static void check(boolean actual, String reason) {
        if (!actual) {
            throw new AssertionError(reason);
        }
    }

    static void checkMoney(
            String label, BigDecimal actual, String expected
    ) {
        check(actual.compareTo(new BigDecimal(expected)) == 0,
                label + ": expected " + expected + ", actual " + actual);
    }

    static void selfTest() {
        BigDecimal opening = new BigDecimal("100.00");
        List<Transaction> transactions = sample();
        List<BalanceRow> rows = timeline(transactions, opening);

        // One input produces one output state.
        check(rows.size() == 3, "Must have exactly 3 states");
        check(rows.get(0).ordinal() == 1, "First ordinal");
        check(rows.get(0).transactionId().equals("TX-01"),
                "First transaction ID");
        checkMoney("After TX-01", rows.get(0).balance(), "125.50");
        checkMoney("After TX-02", rows.get(1).balance(), "115.50");
        checkMoney("After TX-03", rows.get(2).balance(), "120.75");

        // Empty source: does not emit opening balance.
        check(timeline(List.of(), opening).isEmpty(), "Empty source");

        // One input gives one state.
        check(timeline(List.of(transactions.get(0)), opening).size() == 1,
                "Single transaction");

        // Another run must have its own initial state.
        List<BalanceRow> other =
                timeline(transactions, new BigDecimal("200.00"));
        checkMoney("Other period", other.get(0).balance(), "225.50");
        checkMoney("Original run", rows.get(0).balance(), "125.50");

        // Final balance equals opening + sum of source changes.
        BigDecimal finalByReduce = transactions.stream()
                .map(Transaction::change)
                .reduce(opening, BigDecimal::add);
        checkMoney("Final reduce total", finalByReduce, "120.75");
        check(rows.get(rows.size() - 1).balance()
                .compareTo(finalByReduce) == 0, "Wrong final state");

        // Reversing encounter order changes intermediate states,
        // even though final addition total stays unchanged.
        List<Transaction> reversed = new ArrayList<>(transactions);
        Collections.reverse(reversed);
        List<BalanceRow> otherOrder = timeline(reversed, opening);
        checkMoney("Reversed source - first state",
                otherOrder.get(0).balance(), "105.25");
        checkMoney("Reversed source - final total",
                otherOrder.get(2).balance(), "120.75");
        check(!rows.get(0).equals(otherOrder.get(0)),
                "Intermediate state must not stay the same when source is reversed");

        // Verify laziness: scanner does not run when only building pipeline.
        AtomicInteger calls = new AtomicInteger();
        Stream<Integer> pipeline = Stream.of(2, 3, 5)
                .gather(Gatherers.scan(
                        () -> 0,
                        (sum, value) -> {
                            calls.incrementAndGet();
                            return sum + value;
                        }
                ));
        check(calls.get() == 0, "Scanner ran before terminal");
        check(pipeline.toList().equals(List.of(2, 5, 10)),
                "Incorrect prefix sums");
        check(calls.get() == 3, "Scanner did not run all three steps");

        // Infinite source can stop once downstream takes enough outputs.
        List<Long> firstFour = Stream.iterate(1L, n -> n + 1L)
                .gather(Gatherers.scan(
                        () -> 0L,
                        Math::addExact
                ))
                .limit(4)
                .toList();
        check(firstFour.equals(List.of(1L, 3L, 6L, 10L)),
                "Scan combined with limit");

        // Result on ordered source still has defined order
        // even if pipeline before scan is set to parallel mode.
        List<Integer> orderedParallel = List.of(2, 3, 5)
                .parallelStream()
                .gather(Gatherers.scan(() -> 0, Integer::sum))
                .toList();
        check(orderedParallel.equals(List.of(2, 5, 10)),
                "Parallel altered ordered prefixes");
    }

    public static void main(String[] args) {
        List<BalanceRow> rows =
                timeline(sample(), new BigDecimal("100.00"));

        rows.forEach(row ->
                System.out.println(row.ordinal() + " | "
                        + row.transactionId() + " | "
                        + row.balance()));

        // This test suite runs without requiring the -ea flag.
        selfTest();
        System.out.println("SCAN TESTS PASS");
    }
}
```

Compile and run while practicing:

```text
javac GatherersScanDemo.java
java GatherersScanDemo
```

Expected output:

```text
1 | TX-01 | 125.50
2 | TX-02 | 115.50
3 | TX-03 | 120.75
SCAN TESTS PASS
```

The example uses `BigDecimal` to add money accurately in decimal. `new BigDecimal("25.50")` is safer than `new BigDecimal(25.50)` when inputs are represented as business decimal numbers. `Math.addExact` helps detect counter overflow if a sequence has too many transactions, instead of silently wrapping around `long`.

The program and test suite are provided for learners to run themselves; documenting them at this step **does not mean** the code has been compiled or run automatically.

## 6. Using an immutable record to accumulate multiple quantities

The `RunningState` state in the example has three fields:

- `processed`: number of transactions processed so far.
- `lastTransactionId`: ID of the most recently processed transaction.
- `balance`: balance after the latest transaction.

`scanner` creates **a new record** from the previous record and the input element:

```java
(state, tx) -> new RunningState(
        Math.addExact(state.processed(), 1L),
        tx.id(),
        state.balance().add(tx.change())
)
```

An immutable state design brings several benefits:

1. Already-emitted `BalanceRow`s are not altered when the scanner processes the next element.
2. There is no need to place `long count` or `BigDecimal sum` variables **outside** the pipeline.
3. Each run gets its own state from `Supplier`.
4. Checking each intermediate value is straightforward and easy to cross-check against a loop-based run.

If replaced with a mutable object and always emitting **the same state reference**, every result in the list might end up pointing to the final state. `scan` does not automatically turn a shared mutable object into immutable snapshots.

### Running average example

To compute the average after each element, we need **total and count**, not a single average variable that loses information:

```java
record RunningAverage(long count, long total) {
    double average() {
        return (double) total / count;
    }
}

List<Double> averages = List.of(2, 4, 6).stream()
        .gather(Gatherers.<Integer, RunningAverage>scan(
                () -> new RunningAverage(0L, 0L),
                (state, n) -> new RunningAverage(
                        Math.addExact(state.count(), 1L),
                        Math.addExact(state.total(), n))
        ))
        .map(RunningAverage::average)
        .toList();

System.out.println(averages); // [2.0, 3.0, 4.0]
```

The initial state has `count == 0`, yet it is not emitted. `average()` is called **only after the scanner has processed at least one element**, so there is no division by zero in this pipeline. If financial averages or ratios with specific rounding rules are required, use `BigDecimal` and round only at the specified stage.

## 7. Laziness: `scan` only runs when a terminal operation executes

`gather(Gatherers.scan(...))` is an **intermediate operation**. When only constructing the pipeline, state updates do not need to run yet:

```java
AtomicInteger invoked = new AtomicInteger();

Stream<Integer> pipeline = Stream.of(4, 6, 8)
        .gather(Gatherers.scan(
                () -> 0,
                (sum, n) -> {
                    invoked.incrementAndGet();
                    return sum + n;
                }
        ));

System.out.println(invoked.get());   // 0, no terminal operation yet
System.out.println(pipeline.toList()); // [4, 10, 18]
System.out.println(invoked.get());   // 3, sequential source consumed
```

**Scope of this check:** Counting scanner invocations here is an observation for a sequential, finite, fully consumed pipeline. Never assume in **every** pipeline that the lambda invocation count is fixed: short-circuiting, infinite sources, dropping encounter order, or work splitting can make the actual number of processed elements differ from expectations.

Additionally, a `Stream` object can only be used for **one terminal operation**. After `pipeline.toList()`, do not call `pipeline.count()`. When another result is needed, build a new pipeline from a re-traversable source.

## 8. Short-circuiting, `limit`, and infinite sources

Because `scan` emits a new state immediately after each input element, downstream can take **a prefix of the state sequence**:

```java
import java.util.List;
import java.util.stream.Gatherers;
import java.util.stream.Stream;

List<Long> triangular = Stream.iterate(1L, n -> n + 1L)
        .gather(Gatherers.scan(() -> 0L, Math::addExact))
        .limit(5)
        .toList();

System.out.println(triangular); // [1, 3, 6, 10, 15]
```

The `Stream.iterate(1L, ...)` source can be infinite; `limit(5)` requests only **the first five results**, allowing the pipeline to complete. `Gatherers.scan` does not impose an element-count limit on its own: without `limit` or an appropriate termination condition, calling `toList()` on an infinite source will not terminate.

Do not confuse:

```java
// Takes the first 5 states; does not mean taking the final sum of the entire source.
stream.gather(Gatherers.scan(initial, scanner)).limit(5)
```

With an ordered source, `limit(5)` takes the first five states in encounter order. If you swap the positions of `limit` and `scan`, check the semantics carefully: `limit` before `scan` restricts **inputs**, while `limit` after `scan` restricts **outputs**. The two match in value for `scan`, which emits exactly one output per input, though they can differ for other gatherers that emit multiple or zero outputs per input.

### Can `scan` replace `takeWhile`?

`scan` can help **compute a condition on the cumulative balance**, and then `takeWhile` can keep only states still within budget:

```java
List<Integer> withinBudget = List.of(4, 5, 3, 7).stream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .takeWhile(total -> total <= 10)
        .toList();

System.out.println(withinBudget); // [4, 9]
```

The `[4, 9, 12, 19]` sequence produced by scan is cut off at the first state exceeding `10`. If you also need **the element that caused the threshold to be exceeded**, or more complex emission rules, adjust the pipeline or write a custom Gatherer.

## 9. Input order determines the state sequence

Unlike the final sum of addition, **prefix sums depend on order**:

```java
List<Integer> forward = List.of(2, 3, 5).stream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList(); // [2, 5, 10]

List<Integer> reversed = List.of(5, 3, 2).stream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList(); // [5, 8, 10]
```

The two lists have the **same final sum**, yet different intermediate states. For balance reports, ordering must come from an explicit business rule, such as ascending `occurredAt` with `transactionId` as a tie-breaker when multiple events share the same timestamp.

### `sorted()` must come before `scan` if computing in sorted order

```java
List<Integer> running = List.of(5, 2, 3).stream()
        .sorted()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();

System.out.println(running); // [2, 5, 10]
```

If you write `gather(scan(...)).sorted()`, you will **sort the already-computed sums**, rather than changing the order of elements used to compute prefixes. Sorting **after** scan does not recover the state sequence of the sorted source.

### Distinguish ordered sources from unordered sources

`List` has encounter order; `HashSet` does not guarantee a stable business order. If you use `unordered()` or a source without encounter order, intermediate states can depend on the order elements reach the Gatherer, and a fixed prefix sequence should not be expected.

When ordering is part of the contract, **choose an ordered source or sort explicitly before scan**. Do not use side effects like logging inside scanner to decide "which order was used" merely from callback timing.

## 10. `scan` and parallel processing

`Gatherers.scan` is a stateful gatherer with **ordered prefix scan** semantics. It is not an independent transformation like `map`; computing the next state depends on the previous state. The built-in `scan` gatherer operates under the sequential contract of its own scanning stage.

```java
List<Integer> prefixes = List.of(2, 3, 5).parallelStream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList();

System.out.println(prefixes); // [2, 5, 10]
```

Configuring the source with `parallelStream()` **does not turn** prefix computation into independent additions that can be merged arbitrarily. With an ordered source and an order-preserving pipeline, the prefix results must match the sequence in that order.

However, do not infer from this that:

- Every stage in the pipeline is forced to run on the same thread.
- `parallelStream()` will make `scan` run faster.
- `scan` automatically picks a dedicated `Executor` or enforces blocking I/O bounds.
- You can split accumulated state arbitrarily and concatenate two state lists without adjusting the prefixes of the later branch.

Building a specialized parallel prefix scan requires a segmented algorithm that **adjusts the states of later segments** using the result of earlier segments. That is a different problem and cannot be guaranteed merely by a `combiner` adding two states while ignoring order.

## 11. Accumulating per group: do not confuse with a whole-source scan

`scan` applies to **the Stream passed into it**, keeping **a single state sequence** for that execution. When data contains multiple customers and each customer requires an independent balance, do not run one `scan` over the entire source expecting it to automatically reset state per key.

There are two common approaches:

1. **Group first, scan each group:** classify by `customerId`, sort transactions within each group by `occurredAt` and a tie-breaker, then run `scan` separately for each group.
2. **Hold a state Map inside a custom gatherer:** suitable when data needs continuous multi-key processing without materializing all groups. In that case, you must define reset boundaries, state management, and correctness under parallel data yourself.

Example illustrating the first approach:

```java
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import java.util.stream.Gatherers;

record Payment(String customerId, int amount) {}

List<Payment> payments = List.of(
        new Payment("A", 5),
        new Payment("B", 7),
        new Payment("A", 3),
        new Payment("B", 2)
);

Map<String, List<Integer>> runningByCustomer = payments.stream()
        .collect(Collectors.groupingBy(
                Payment::customerId,
                LinkedHashMap::new,
                Collectors.toList()))
        .entrySet().stream()
        .collect(Collectors.toMap(
                Map.Entry::getKey,
                entry -> entry.getValue().stream()
                        .map(Payment::amount)
                        .gather(Gatherers.scan(() -> 0, Integer::sum))
                        .toList(),
                (oldValue, newValue) -> oldValue,
                LinkedHashMap::new
        ));

System.out.println(runningByCustomer);
// {A=[5, 8], B=[7, 9]}
```

Here, `Collectors.groupingBy` builds a list of transactions per customer, and then **each list opens a scan pipeline with initial state 0**. This approach incurs the cost of storing the groups; on very large sources or time-stream data, evaluate memory and ordering requirements separately.

If a customer has multiple transactions at the same timestamp, do not rely solely on accidental input order: specify a secondary sort criterion such as transaction ID if business logic requires reproducible results.

## 12. Common mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking `scan` returns one final sum | Misses intermediate states or uses unnecessary API | Use `scan` to emit a state sequence; use `reduce`/`sum` for a final sum. |
| Thinking the `initial` value is the first emitted element | Result count is off by one | Remember output begins after scanner processes the first element. |
| Forgetting the rule for empty sources | Expecting a default state from `scan` | An empty source yields an empty Stream; add separate output if needed. |
| Using an external accumulator variable outside the lambda | State leaks across runs, hard to control in parallel | Hold state only through `initial` and `scanner`. |
| Re-emitting a mutable object and mutating it afterward | Previous results can change as traversal continues | Return an immutable record/snapshot or copy state before emitting. |
| Calling `sorted()` after `scan` to "order the calculation" | Only sorts already-computed results, not input addition order | Sort the source **before** the Gatherer. |
| Running on an unordered source expecting a fixed prefix sequence | Intermediate results can vary | Sort or preserve explicit encounter order. |
| Using `scan` on an infinite source followed by `toList()` | Pipeline never terminates | Use `limit`, `takeWhile`, or an appropriate stopping condition. |
| Thinking parallel configuration automatically makes `scan` split/merge prefixes optimally | Wrong performance expectations, or broken custom algorithm | Understand order dependence; measure on real data. |
| Summing very large integers with `sum`/`Integer::sum` unchecked | Integer overflow possible | Use `long`, `BigInteger`, or `Math.addExact` per business rules. |
| Wanting separate customer balances while scanning all customers together | One customer's state mixes into another's | Group by key then scan separately, or use a Gatherer with per-key state. |
| Reusing a Stream object after a terminal operation | `IllegalStateException` | Create a new Stream from a re-traversable source. |

## 13. Questions and exercises

**Exercise 1 — Prefix sums.** Given `[4, -2, 6]` and `initial = 10`, predict the result after `scan` with addition.

**Answer:** `[14, 12, 18]`. The value `10` does not appear by itself at the start of the result.

**Exercise 2 — Empty.** What does `Stream.<Integer>empty().gather(Gatherers.scan(() -> 100, Integer::sum)).toList()` produce?

**Answer:** An empty list `[]`. Unlike a collector designed to return a default final sum, `scan` does not emit initial on its own.

**Exercise 3 — Testing order.** Given `[3, 1, 4]` and `initial = 0`. Find the result when scanning directly and when sorting ascending before scanning.

```java
List<Integer> direct = List.of(3, 1, 4).stream()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList(); // [3, 4, 8]

List<Integer> sorted = List.of(3, 1, 4).stream()
        .sorted()
        .gather(Gatherers.scan(() -> 0, Integer::sum))
        .toList(); // [1, 4, 8]
```

**Exercise 4 — Running average.** With `[10, 20, 30, 40]`, use state `(count, sum)` to emit the sequence of averages `[10, 15, 20, 25]`. Why not store only a single `average` variable?

**Suggested answer:** Both count and sum are needed to compute the exact average when a new element arrives. If only the average is stored without the count, the weight of the previous result is unknown when updating.

**Exercise 5 — Limit.** On `Stream.iterate(1, n -> n + 1)`, call `scan(() -> 0, Integer::sum).limit(3).toList()`. What is the result?

**Answer:** `[1, 3, 6]`. Downstream `limit` allows stopping after the requested three states.

**Exercise 6 — Multi-customer.** Transactions in order: `A +5`, `B +10`, `A +2`, `B -3`. If both customers have an opening balance of 0, give the cumulative results per customer.

**Answer:** `A=[5,7]`, `B=[10,7]`. Do not use a single scan over the entire list if independent state per customer is needed.

**Exercise 7 — Comparing `reduce`.** With input numbers `[2,3,5]`, verify whether the last element of `scan` equals the result of `reduce(0,Integer::sum)`. Then reverse the source and verify that the final value stays the same while the prefixes change.

**Hint:** Within non-overflowing arithmetic, addition is associative so the final sum does not depend on order. However, the list of **intermediate sums** does depend on order.

## 14. Key takeaways

- `Gatherers.scan(initial, scanner)` turns each input element into **a new accumulated state** and emits that state down the pipeline.
- `initial.get()` initializes the state **before the first element** without becoming an output element itself. An empty source produces **no output**.
- `scan` is an intermediate operation and remains lazy; `toList`, `collect`, `reduce`, or another terminal operation triggers the pipeline.
- Use immutable records or snapshots for multi-field state to prevent earlier results from being mutated; when exact balances are required, prefer `BigDecimal`.
- Prefix states **depend on encounter order**. If reproducible results are required, define order before scanning; `parallelStream()` does not automatically turn a prefix scan into independent additions.
- If only **one final result** is needed, consider `sum`/`reduce`/`collect`; if separate state per key is needed, group first or design a Gatherer with per-key state.
