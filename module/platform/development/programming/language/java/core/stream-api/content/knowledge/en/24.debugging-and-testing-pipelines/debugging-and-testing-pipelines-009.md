# Property-Based Testing and Reproducible Random Data Generation

In the **Debugging and Testing Pipelines** chapter of **Java Stream API**, testing a few fixed examples is necessary yet insufficient. A pipeline can work cleanly on a five-element list yet fail when the source is empty, contains duplicates, changes order, spans multiple groups, or switches from `stream()` to `parallelStream()`. In particular, bugs in `reduce`, `collect`, filters, grouping, and stateful operations often appear in **data combinations** the author never anticipated.

**Property-based testing** asks a different question than example-based testing: instead of checking only one predefined input and one hardcoded output, you specify **what must always hold** across a class of valid inputs, then generate many datasets to hunt for counterexamples. Random generation must be **reproducible**: whenever a failure occurs, save the seed, configuration, and failing input so you can rerun the exact case, fix the code, and keep a regression test.

This lesson explains how to design seed-driven data generators, build independent *oracles*, test invariants and property-preserving transformations, compare sequential/parallel pipelines, shrink failing cases, and avoid non-deterministic test pitfalls. Complete examples use **Java 17+**, `SplittableRandom`, and standard JDK APIs; no extra testing frameworks are required.

## 1. From Example-Based Testing to Property-Based Testing

An example-based test might look like:

~~~java
import java.util.List;

long count = List.of(1, 2, 3, 4).stream()
        .filter(n -> n % 2 == 0)
        .count();

if (count != 2L) {
    throw new AssertionError("Expected 2 even numbers");
}
~~~

It verifies one specific case: `[1,2,3,4]` contains two even numbers. Yet many cases remain untested: an empty list, all even numbers, all odd numbers, duplicates, negative numbers, `0`, and very large inputs.

We can elevate this goal into a **property**:

> For any valid list of integers, the number of elements passing `filter(even)` equals the number of even integers counted by an independent reference loop.

That property can be checked across hundreds of automatically generated lists instead of hand-writing hundreds of individual `assert` statements.

Several useful property categories for the Stream API:

| Category | Question checked | Example |
| --- | --- | --- |
| **Output invariant** | Does the output always obey a constraint? | No element fails the `filter` predicate |
| **Reference oracle** | Does output match an independent computation? | `groupingBy + summingLong` vs. a `for` loop |
| **Metamorphic relation** | Does a valid input transform preserve a property? | Shuffling input keeps per-group sums unchanged |
| **Algebraic laws** | Does merging satisfy identity/associativity? | Sum of two halves equals sum of whole sequence |
| **Execution equivalence** | Do sequential and parallel agree semantically? | Identical `Map<region, total>` |
| **Boundary cases** | Are minimal/extreme inputs handled right? | Empty Stream, single element, many duplicate keys |
| **Source lifecycle** | Do resources close on errors/early exits? | `Files.lines` inside `try-with-resources` |

Not every pipeline must satisfy all of these properties. **Derive properties from business requirements and API contracts**, rather than inventing a false property and treating valid behavior as a failure.

## 2. Problem Specification Used Throughout

Suppose a system aggregates revenue by region from a list of transactions:

~~~java
record Sale(
        String region,
        int units,
        long unitPriceCents
) {
    long totalCents() {
        return Math.multiplyExact((long) units, unitPriceCents);
    }
}
~~~

Each transaction has:

- `region`: region code in `{NORTH, SOUTH, CENTRAL}`.
- `units`: item quantity, non-negative.
- `unitPriceCents`: unit price in **integer cents**, non-negative.
- `totalCents`: line total = units × unit price, stored as `long`.

We deliberately use integer cents instead of `double` to avoid floating-point rounding noise in this monetary aggregation example. `Math.multiplyExact` detects overflow if inputs exceed `long` bounds.

Pipeline under test:

~~~java
Map<String, Long> totalsByRegion = sales.stream()
        .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.summingLong(Sale::totalCents)
        ));
~~~

Result requirements:

1. Each region with transactions appears as **exactly one key** in the Map.
2. Each key's value is the sum of line totals for **all transactions in that region**.
3. A transaction with total 0 is still present in its region; that region may have a sum of 0.
4. An empty list produces an empty Map.
5. Because integer addition is bounded to avoid overflow, totals do not depend on traversal order or data partitioning.
6. The `Map` need not preserve key order; tests must compare **key–value mappings**, not printed `HashMap` strings.

This is a concrete contract. If business rules require excluding canceled orders, add the filter to both the pipeline and the oracle; if `null` data is allowed, define an explicit policy instead of silently skipping it.

## 3. Designing a Data Generator: In-Domain, Bounded, Repeatable

A random source must produce data **within the valid domain** of the property being tested. Example:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.SplittableRandom;

static List<Sale> generateSales(long seed) {
    SplittableRandom random = new SplittableRandom(seed);
    String[] regions = {"NORTH", "SOUTH", "CENTRAL"};

    int count = random.nextInt(0, 201);
    List<Sale> result = new ArrayList<>(count);

    for (int i = 0; i < count; i++) {
        String region = regions[random.nextInt(regions.length)];
        int units = random.nextInt(0, 21);
        long price = random.nextLong(0L, 100_001L);

        result.add(new Sale(region, units, price));
    }

    return List.copyOf(result);
}
~~~

Given the same `seed`, generation algorithm, and runtime environment, the generator produces the exact same sequence of choices. The domain is intentionally bounded:

| Attribute | Generation range | Reason |
| --- | --- | --- |
| Transaction count | 0 to 200 | Can generate empty sources; keeps tests lightweight in memory |
| Region | Three fixed codes | Creates duplicate keys to exercise `groupingBy` |
| `units` | 0 to 20 | Includes zero-total cases |
| `unitPriceCents` | 0 to 100,000 | Covers 0 and large values |
| Record values | Non-`null` | First property focuses on valid inputs |
| Order | Generation order preserved in `List` | Provides encounter order for ordered operations |

`nextInt(origin, bound)` and `nextLong(origin, bound)` use an **exclusive upper bound**. Thus `nextInt(0, 201)` can produce 200, and `nextLong(0L, 100_001L)` can produce 100,000.

With at most 200 transactions, each line total is at most `20 × 100,000 = 2,000,000` cents, so the grand total never exceeds 400,000,000 cents. This range is small enough that `long` additions in our example never overflow. Overflow handling should be tested in a **dedicated test group**, never mixed into a property that assumes valid non-overflowing sums.

### Why avoid `Math.random()`?

`Math.random()` does not let callers assign an explicit per-case seed as cleanly and transparently as an instantiated generator. `ThreadLocalRandom.current()` is also unsuitable when your goal is reproducing an exact case from a test-owned seed.

`SplittableRandom(seed)` is convenient for seeded generation. Still, **the seed alone is not the entire reproduction state**: you also need the generation algorithm, value ranges, generator call order, and environment/version details for long-term reproducibility across systems.

If you need a fixture that is **100% stable across JDKs/toolchains**, persist the failing input list itself rather than relying solely on a seed.

## 4. Reproducible Randomness vs. "Different Data on Every Run"

An anti-pattern that hurts reproducibility:

~~~java
// Unsuitable for debugging a failure after it happens.
List<Integer> data = Stream.generate(
        () -> (int) (Math.random() * 100)
).limit(100).toList();
~~~

If this test fails on CI, developers cannot reconstruct the exact input that triggered the bug.

Instead, use a **base seed** and derive a deterministic seed per trial:

~~~java
long baseSeed = 20261118L;

for (int trial = 0; trial < 500; trial++) {
    long caseSeed = baseSeed + trial;
    List<Sale> data = generateSales(caseSeed);

    // Check properties on data.
}
~~~

To replay trial 137, you compute `caseSeed = 20261118 + 137` and rerun **that exact case**. This is why each trial should construct its own fresh `SplittableRandom`, rather than advancing one shared generator across every trial.

What to log whenever a test fails:

- Name of the violated property.
- `caseSeed` and trial number.
- Minimal input list or file.
- Expected result and actual result.
- JDK version, code version, and key settings if environment-specific.

**Never print only "Random test failed."** A failing trial without its seed and input is hard to reproduce and usually wastes far more time than fixing the actual bug.

## 5. Independent Oracle: Comparing a Stream Against a Clear Loop

An `oracle` is a reference computation simple enough to trust and reasonably independent of the code under test.

Example computing regional revenue with a loop:

~~~java
import java.util.HashMap;
import java.util.List;
import java.util.Map;

static Map<String, Long> referenceTotals(List<Sale> sales) {
    Map<String, Long> result = new HashMap<>();

    for (Sale sale : sales) {
        long amount = Math.multiplyExact(
                (long) sale.units(), sale.unitPriceCents());

        result.merge(
                sale.region(),
                amount,
                (left, right) -> Math.addExact(left, right)
        );
    }

    return result;
}
~~~

This oracle avoids `groupingBy` and `summingLong`, so if the collector is written wrong, the comparison exposes the difference.

Guidelines for writing an oracle:

1. **Favor readability over speed.** Test datasets are small; an oracle doesn't need production-level optimization.
2. **Avoid sharing helpers that could fail identically on both sides.** Here the oracle computes multiplication itself instead of calling `Sale::totalCents`, reducing the risk of hiding a shared bug.
3. **Follow the exact same business spec.** If output drops `units == 0` transactions, the oracle must too.
4. **Verify the oracle with fixed fixtures.** A buggy oracle leads to false conclusions about the pipeline.
5. **Do not depend on Map traversal order.** `Map.equals` compares key–value pairs properly.

Comparison example:

~~~java
Map<String, Long> expected = referenceTotals(sales);
Map<String, Long> actual = totalsByRegion(sales, false);

if (!expected.equals(actual)) {
    throw new AssertionError(
            "Expected=" + expected + ", actual=" + actual);
}
~~~

Here `totalsByRegion(sales, false)` is the pipeline function defined in our complete program.

## 6. Properties to Verify for Aggregations

### 6.1. Equivalence with the oracle

For every `sales` list in the valid domain:

~~~text
streamTotals(sales) == referenceTotals(sales)
~~~

This is our strongest property because it checks the entire Map against the reference calculation.

### 6.2. Sum of group totals equals grand total

~~~text
sum(totalsByRegion.values())
    == sum(each sale.units * sale.unitPriceCents)
~~~

This invariant catches dropped or double-counted transactions, provided sums do not overflow. Still, checking only the grand total **is not enough**: assigning a transaction to the wrong region leaves the grand total unchanged.

### 6.3. Permutation does not change per-region sums

When only revenue by region matters, transaction order is not part of output semantics:

~~~text
totalsByRegion(sales) == totalsByRegion(shuffle(sales))
~~~

Note that this is **not** valid for every pipeline. Operations like `findFirst`, `limit`, `takeWhile`, and `joining` can depend on encounter order. Apply permutation invariance only to aggregations whose contract is **order-independent**.

### 6.4. Splitting data and merging reports

If you split the list into two contiguous slices `left` and `right`:

~~~text
aggregate(sales)
    == merge(aggregate(left), aggregate(right))
~~~

The `merge` function must sum totals for matching regions. This models how parallel Streams split and merge work, exposing bugs such as a combiner dropping a branch or using the wrong identity.

### 6.5. Sequential and parallel must agree semantically

With `long` and a non-overflowing test domain:

~~~text
sequentialTotals(sales) == parallelTotals(sales)
~~~

Do not require the Maps to share the same implementation class, key iteration order, or worker thread count. **Compare only key-to-value contents.**

### 6.6. `filter` and `map` must preserve order on ordered sources

Suppose we want the list of line totals for `NORTH` transactions:

~~~java
List<Long> northAmounts = sales.stream()
        .filter(s -> "NORTH".equals(s.region()))
        .map(Sale::totalCents)
        .toList();
~~~

On an ordered `List` source, the output must list amounts **in the exact order `NORTH` transactions appear**. Verify this with a separate loop. Never apply a shuffle property to this list if preserving encounter order is required.

## 7. Complete Java 17+ Program, Zero External Libraries

Save the code below as `StreamPropertyTest.java`. It generates 500 seeded datasets, compares the pipeline against the oracle, checks invariants, permutations, split-and-merge, parallel execution, and ordered `filter/map`. It also supports **replaying a single seed** passed on the command line.

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Random;
import java.util.SplittableRandom;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class StreamPropertyTest {

    private static final String[] REGIONS = {
            "NORTH", "SOUTH", "CENTRAL"
    };

    record Sale(String region, int units, long unitPriceCents) {
        long totalCents() {
            return Math.multiplyExact(
                    (long) units, unitPriceCents);
        }
    }

    // Each seed generates an independent, finite dataset.
    static List<Sale> generate(long seed) {
        SplittableRandom random = new SplittableRandom(seed);
        int count = random.nextInt(0, 201);
        List<Sale> data = new ArrayList<>(count);

        for (int i = 0; i < count; i++) {
            String region = REGIONS[
                    random.nextInt(REGIONS.length)];
            int units = random.nextInt(0, 21);
            long unitPriceCents =
                    random.nextLong(0L, 100_001L);

            data.add(new Sale(
                    region, units, unitPriceCents));
        }
        return List.copyOf(data);
    }

    // Code under test: a pipeline that can run
    // sequentially or in parallel with the same algorithm.
    static Map<String, Long> totalsByRegion(
            List<Sale> sales, boolean parallel) {

        Stream<Sale> source = parallel
                ? sales.parallelStream()
                : sales.stream();

        return source.collect(Collectors.groupingBy(
                Sale::region,
                Collectors.summingLong(Sale::totalCents)
        ));
    }

    // Independent oracle: avoids groupingBy/summingLong.
    static Map<String, Long> referenceTotals(
            List<Sale> sales) {

        Map<String, Long> result = new HashMap<>();

        for (Sale sale : sales) {
            long amount = Math.multiplyExact(
                    (long) sale.units(),
                    sale.unitPriceCents());

            result.merge(
                    sale.region(),
                    amount,
                    (left, right) ->
                            Math.addExact(left, right)
            );
        }
        return result;
    }

    // Output has encounter order; check as a List.
    static List<Long> northAmounts(List<Sale> sales) {
        return sales.stream()
                .filter(s -> "NORTH".equals(s.region()))
                .map(Sale::totalCents)
                .toList();
    }

    static List<Long> referenceNorthAmounts(
            List<Sale> sales) {

        List<Long> result = new ArrayList<>();
        for (Sale sale : sales) {
            if ("NORTH".equals(sale.region())) {
                result.add(Math.multiplyExact(
                        (long) sale.units(),
                        sale.unitPriceCents()));
            }
        }
        return result;
    }

    // Print enough details to replay a failing trial.
    static void checkEqual(
            String property,
            Object expected,
            Object actual,
            long seed,
            List<Sale> data) {

        if (!Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "Property: " + property
                    + "\nseed: " + seed
                    + "\ninput: " + data
                    + "\nexpected: " + expected
                    + "\nactual: " + actual
            );
        }
    }

    static void verify(long seed, List<Sale> sales) {
        Map<String, Long> expected =
                referenceTotals(sales);

        Map<String, Long> sequential =
                totalsByRegion(sales, false);

        Map<String, Long> parallel =
                totalsByRegion(sales, true);

        // Property 1: matches reference loop.
        checkEqual(
                "oracle", expected, sequential, seed, sales);

        // Property 2: parallel produces identical values.
        checkEqual(
                "parallel", sequential, parallel, seed, sales);

        // Property 3: reordering does not change per-region sums.
        List<Sale> shuffled = new ArrayList<>(sales);
        Collections.shuffle(
                shuffled,
                new Random(seed ^ 0x5DEECE66DL)
        );

        checkEqual(
                "permutation",
                sequential,
                totalsByRegion(shuffled, false),
                seed,
                sales
        );

        // Property 4: split into two halves and merge matches.
        int mid = sales.size() / 2;

        Map<String, Long> combined = new HashMap<>(
                totalsByRegion(sales.subList(0, mid), false)
        );

        Map<String, Long> second = totalsByRegion(
                sales.subList(mid, sales.size()), false
        );

        second.forEach((region, total) ->
                combined.merge(
                        region,
                        total,
                        (left, right) ->
                                Math.addExact(left, right)
                )
        );

        checkEqual(
                "split-and-merge",
                sequential,
                combined,
                seed,
                sales
        );

        // Property 5: sum of region totals == sum of all sales.
        long overall = 0L;
        for (Sale sale : sales) {
            overall = Math.addExact(
                    overall,
                    Math.multiplyExact(
                            (long) sale.units(),
                            sale.unitPriceCents())
            );
        }

        long groupedTotal = 0L;
        for (long value : sequential.values()) {
            groupedTotal = Math.addExact(
                    groupedTotal, value);
        }

        checkEqual(
                "conservation",
                overall,
                groupedTotal,
                seed,
                sales
        );

        // Property 6: filter/map preserves encounter order.
        checkEqual(
                "ordered-filter-map",
                referenceNorthAmounts(sales),
                northAmounts(sales),
                seed,
                sales
        );
    }

    static void edgeCases() {
        // No transactions.
        verify(-1L, List.of());

        // Transaction with zero revenue: must retain key.
        verify(-2L, List.of(
                new Sale("NORTH", 0, 100L)
        ));

        // Multiple records in same region, zero unit price,
        // multiple regions, and large non-overflowing values.
        verify(-3L, List.of(
                new Sale("SOUTH", 20, 100_000L),
                new Sale("SOUTH", 20, 100_000L),
                new Sale("CENTRAL", 1, 0L),
                new Sale("NORTH", 1, 99L)
        ));
    }

    public static void main(String[] args) {
        // java StreamPropertyTest 12345
        // -> verifies only the dataset generated with seed 12345.
        if (args.length == 1) {
            long seed = Long.parseLong(args[0]);
            verify(seed, generate(seed));
            System.out.println("PASS seed=" + seed);
            return;
        }

        if (args.length != 0) {
            throw new IllegalArgumentException(
                    "Usage: java StreamPropertyTest [seed]");
        }

        edgeCases();

        long baseSeed = 20261118L;
        int trials = 500;

        for (int trial = 0; trial < trials; trial++) {
            long seed = baseSeed + trial;
            verify(seed, generate(seed));
        }

        System.out.println(
                "PASS fixed-cases and "
                + trials + " random cases"
                + "; baseSeed=" + baseSeed
        );
    }
}
~~~

Run commands:

~~~bash
javac --release 17 StreamPropertyTest.java
java StreamPropertyTest
~~~

On success:

~~~text
PASS fixed-cases and 500 random cases; baseSeed=20261118
~~~

To replay a single case with `seed = 20261234`:

~~~bash
java StreamPropertyTest 20261234
~~~

If a property fails, `AssertionError` prints the property name, seed, and input data; you can paste the seed into the command line to reproduce it. Here each `Sale` is an immutable record generated before the pipeline runs; no mutable random source is shared across `parallelStream` workers.

**Note:** This is a standalone *test harness* for learning the essence of property-based testing, not a full replacement for JUnit or a test-suite manager. In real projects, integrate checks into your build tool's test framework so the runner handles reporting, statistics, and CI artifacts cleanly.

## 8. Interpreting Failures: Why Each Property Helps

A failing run might break **only one** property:

| Failed property | What to investigate |
| --- | --- |
| `oracle` | Bug in grouping logic, filter, multiplication, or summation |
| `parallel` | Incompatible accumulator/combiner, shared state, order dependence, or non-associative op |
| `permutation` | Used an order-sensitive operator despite an order-independent sum requirement |
| `split-and-merge` | Broken two-part merge, dropped group, or duplicate group |
| `conservation` | Dropped or doubled values; note wrong region assignment can leave grand total unchanged |
| `ordered-filter-map` | Lost encounter order or picked wrong region elements |

**No single property suffices to prove the entire program correct.** For instance, a pipeline could sum amounts accurately while assigning every transaction to `NORTH`: conservation still passes, while the per-region oracle catches the bug.

Similarly, comparing sequential vs. parallel only proves both execution modes **agree on the tested inputs**. If both share the same business-rule bug, comparing them won't catch it. That is why you combine **oracles, invariants, fixed fixtures, and metamorphic relations**.

## 9. Never Reuse One Stream Across Multiple Checks

A `Stream` generally permits only **one terminal operation**. To check multiple properties on the same dataset, keep the data in a `List` or re-openable source and create a fresh Stream for each check.

**Wrong:**

~~~java
Stream<Integer> source = List.of(1, 2, 3).stream();

long count = source.count();
long sum = source.mapToLong(Integer::longValue).sum();
// Cannot continue using the same already-consumed source.
~~~

**Right:**

~~~java
List<Integer> data = List.of(1, 2, 3);

long count = data.stream().count();
long sum = data.stream()
        .mapToLong(Integer::longValue)
        .sum();
~~~

In the full program, each call to `totalsByRegion(...)` opens a fresh Stream from `List<Sale>`. Because `Sale` is an immutable record and `List.copyOf` prevents structural mutation, checks on the same data never interfere with each other.

For I/O-backed Streams like `Files.lines`, **never** reuse a Stream after closing. To run multiple independent algorithms on the same file, reopen it inside separate `try-with-resources` blocks or materialize a bounded, controlled test dataset.

## 10. Testing Ordered vs. Unordered Properties

Never blindly apply permutation properties to **every Stream operation**.

### 10.1. Order-independent aggregations

~~~java
long sum = data.stream()
        .mapToLong(Long::longValue)
        .sum();
~~~

For non-overflowing integers and the same multiset of elements, shuffling does not change the mathematical sum.

### 10.2. First-element selection depends on encounter order

~~~java
List<String> names = List.of("Lan", "An", "Minh");

String first = names.stream()
        .findFirst()
        .orElseThrow();

// "Lan"
~~~

Reordering the list to `[Minh, Lan, An]` makes `"Minh"` the valid answer. A property asserting "shuffling leaves `findFirst` unchanged" is **wrong by definition**.

### 10.3. `distinct` preserves first-seen order on ordered Streams

~~~java
List<Integer> input = List.of(2, 1, 2, 3, 1);

List<Integer> unique = input.stream()
        .distinct()
        .toList();

// [2, 1, 3]
~~~

On a source with encounter order, `distinct` retains the first element matching each value per its stability contract. A valid property is:

~~~text
distinct(distinct(input)) == distinct(input)
~~~

And the resulting list **has no duplicates**, though you must not expect the same output order if the input is shuffled before `distinct`.

### 10.4. `sorted` and `limit` have their own contracts

~~~java
List<Integer> top3 = input.stream()
        .sorted()
        .limit(3)
        .toList();
~~~

If the requirement is "the three smallest numbers," shuffling the input leaves `top3` unchanged for elements that compare equal with no distinguishing fields. When elements are objects compared by a single field, define an explicit tie-breaker if deterministic ordering among equal elements is needed.

Tie ordering properties directly to **encounter order, comparators, and terminal operations**; never rely on whatever order a `HashMap` happens to display.

## 11. Parallel Testing: Associativity, State, and Combiners

Switching from `stream()` to `parallelStream()` changes how data is split and merged. That is where property-based testing shines.

### 11.1. `reduce` must have a valid identity and operator

~~~java
int correct = List.of(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, Integer::sum);
~~~

The identity for addition is `0`, and Java integer addition is associative under modular overflow semantics. Still, if the business forbids overflow, add dedicated overflow checks.

**Never use subtraction for standard parallel reduction:**

~~~java
int wrong = List.of(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

Subtraction **is not associative**: `(a-b)-c` differs from `a-(b-c)`. Different splits yield different outputs. A sequential-only test would completely miss this bug.

### 11.2. Testing combiner laws directly

When writing a custom collector accumulating multiple metrics, verify:

~~~text
combine(identity, result) == result
combine(combine(a, b), c) == combine(a, combine(b, c))
aggregate(left + right) == combine(aggregate(left), aggregate(right))
~~~

The split-and-merge check in the full program is a form of the third law. For collectors with mutable state, also verify both accumulation containers are **independent** and do not alias an external Map or List.

### 11.3. Avoid side effects inside lambdas

**Wrong:**

~~~java
List<Long> output = new ArrayList<>();

sales.parallelStream()
        .map(Sale::totalCents)
        .forEach(output::add); // ArrayList is not thread-safe for concurrent writes.
~~~

**Right:**

~~~java
List<Long> output = sales.parallelStream()
        .map(Sale::totalCents)
        .toList();
~~~

With an ordered `List` source and `toList()`, the output preserves logical order; yet **mapper invocation order is not guaranteed**.

Do not use `AtomicInteger` to assign sequence numbers inside `map` and treat them as encounter-order indices. Atomicity prevents lost increments, not out-of-order task scheduling.

## 12. Randomness in Parallel Streams: Generate Input First, Process Second

An anti-pattern is placing a mutable generator inside a mapper:

~~~java
SplittableRandom random = new SplittableRandom(123L);

List<Integer> values = source.parallelStream()
        .map(x -> random.nextInt(100))
        .toList();
~~~

`SplittableRandom` is not designed to be shared concurrently across threads. Besides thread-safety hazards, the order in which random numbers are drawn depends on scheduling, so a single seed **never guarantees each element receives the same random value across runs**.

Preferred testing pattern:

~~~java
List<Sale> data = generate(123L); // Generated sequentially, deterministically.

Map<String, Long> result = data.parallelStream()
        .collect(Collectors.groupingBy(
                Sale::region,
                Collectors.summingLong(Sale::totalCents)
        ));
~~~

The input is fixed upfront; the pipeline executes pure computations over that data.

If you genuinely need parallel random generation, design **per-element/per-index or per-branch seeds** with a deterministic mapping rule—for example, iterating over indices and creating fresh generators from index-derived seeds rather than assuming non-deterministic `split()` scheduling will match across runs.

**Correctness testing is not benchmarking.** Generating random data inside a timed section skews measurements with generator overhead; build fixtures before measuring.

## 13. Focus on Boundaries, Not Only Uniform Random Distributions

A purely uniform generator can rarely hit **hard edge cases**. For instance, with `count` from 0 to 200, the probability of generating an empty list in one trial is only `1/201`; even 500 trials do not guarantee it appeared.

Therefore, always pair random tests with **fixed boundary fixtures**:

| Scenario | What to verify |
| --- | --- |
| Empty list | Empty Map, total 0 |
| Single transaction | Exactly one key and amount |
| Multiple transactions in same region | Summed accurately, none dropped |
| Zero revenue | Region still appears if it had a transaction |
| All transactions in one region | No spurious empty groups |
| Some regions absent | No keys synthesized for absent regions |
| Maximum valid values | No overflow inside allowed range |
| Overflowing values | Throws or follows explicit arithmetic policy |
| `null` in region or record | Rejected/accepted per defined contract |
| Unsorted vs. sorted input | Appropriate encounter-order properties |
| Duplicate elements in source | Whether multiplicities are kept or deduplicated |
| Large data across many splits | Parallel equivalence and memory limits |

The main generator here emits no `null`s and stays within `long` bounds. That is **a deliberate choice for one property family**, not proof the pipeline tolerates bad inputs. Write separate tests for invalid inputs with explicit expectations: throwing `IllegalArgumentException`, rejecting the row, or recording a parse error.

### Rule to remember when working with `null`

Standard `Collectors.groupingBy` rejects classifiers returning a `null` key; if a source record has a missing region, `NullPointerException` can occur. Do not let a random generator emit nulls accidentally and label the crash a pipeline bug unless the pipeline's contract requires handling null gracefully.

Good test design **clearly separates the valid input domain from inputs that must be rejected**.

## 14. Shrinking Counterexamples: From 200 Elements Down to a Few

A random trial may fail on a 180-transaction list. Reading 180 records by eye is painful. **Shrinking** or **delta debugging** seeks a smaller input that still triggers the exact same failure.

A practical manual shrinking workflow:

1. Save the failing `seed` and input list.
2. Split the list into chunks and try **removing large chunks**.
3. If removing a chunk still reproduces the bug, keep the smaller input.
4. Shrink chunk size gradually; try narrowing down to one or two records.
5. Shrink field values: smaller amounts, fewer regions, quantities down to `0`/`1`, shorter ID strings.
6. Save the **minimal input** as a fixed regression fixture independent of the generator.

For example, a buggy collector merges only part of the Map in parallel. A 200-element random failure might shrink to:

~~~java
List<Sale> counterExample = List.of(
        new Sale("NORTH", 1, 10L),
        new Sale("SOUTH", 1, 20L)
);
~~~

If the parallel pipeline still drops one key on this tiny input, diagnosing the combiner becomes vastly simpler.

Keep in mind that **the minimal counterexample depends on the bug**. Do not assume a two-element input will always trigger a parallel bug on every JDK; the runtime might skip splitting tiny inputs. For parallel-split-only bugs, test **combiner laws directly** with hand-built accumulation containers in addition to running `parallelStream`.

Property-based testing frameworks with built-in shrinking automate this step; the vital habit remains **saving a readable counterexample as a permanent regression test after fixing the bug**.

## 15. Metamorphic Testing When No Simple Oracle Exists

Sometimes exact outputs are hard to compute with an independent reference algorithm—for example, in pipelines chaining complex domain transformations. **Metamorphic relations** provide additional evidence.

### 15.1. Adding unrelated data

When computing only `NORTH`'s total, adding a `SOUTH` sale must not change `NORTH`'s total:

~~~text
northTotal(sales + [SOUTH sale]) == northTotal(sales)
~~~

This applies only when there are no global cross-region rules such as tier discounts based on overall volume.

### 15.2. Splitting one sale into two equivalent sales

One transaction `(NORTH, 3 units, 100 cents)` can split into `(NORTH, 1, 100)` and `(NORTH, 2, 100)`. If the report only sums line totals by region, `NORTH`'s total stays unchanged.

Do not apply this relation to **transaction counts**, since splitting legitimately increases transaction count by one.

### 15.3. Reordering elements

For per-region sums, permutation leaves results unchanged. For string joining, first-element selection, positional numbering, or `takeWhile`, permutation changes semantics.

### 15.4. Concatenating two inputs

For associative sums within valid bounds:

~~~text
total(A ++ B) = total(A) + total(B)
~~~

For averages, however, you cannot add or average two group averages directly. You must combine **(sum, count)** pairs first and divide only at the end. This is a classic case where an apparently plausible metamorphic relation is missing intermediate state.

### 15.5. Re-running on the same input

A pure pipeline independent of external state must yield the same output content when rerun on the same data snapshot. Still, `findAny` on parallel streams or iteration order of an unordered Map may vary per API contract. Assert only **specified properties**, such as the output element set, rather than demanding identical `toString()` output when order is unspecified.

## 16. Why Testing Side Effects with `peek` Often Misleads

`peek` is handy for **diagnostic observation** in some pipelines, yet unsuitable for mandatory logic.

~~~java
List<String> data = List.of("A", "B", "C");

long count = data.stream()
        .peek(x -> System.out.println("Seen " + x))
        .count();
~~~

Never write a property saying "`peek` must be called exactly three times." Implementations can compute `count` from a `SIZED` source without traversing elements, skipping unnecessary actions altogether.

Short-circuiting operations like `findFirst` and `anyMatch` can also halt before inspecting every element. In parallel streams, side-effect order and timing lack sequential loop guarantees.

**Separate testing concerns:**

- Verify **outputs** using oracles, invariants, and metamorphic relations.
- Use logging/`peek` strictly as temporary observation.
- If an action **must** execute exactly once per record, implement it at a dedicated task layer with its own contract rather than relying on an intermediate operation that may be optimized away or short-circuited.

Never insert `sleep`, log prints, or shared counters into mappers just to "force" parallel bugs to surface; those perturbations can hide or create race conditions.

## 17. Testing Arithmetic Precision and `long` Bounds

Our example's domain avoids `long` overflow, allowing exact equality checks between sequential and parallel sums.

If switched to `double`:

~~~java
List<Double> values = List.of(
        1.0e16, -1.0e16, 1.0
);
~~~

Floating-point addition **is not strictly associative**:

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Because grouping changes, parallel pipelines can produce slight differences in floating-point sums; moreover, JDK summation routines may use specialized error-compensation strategies. Never enforce a `Double.equals` property across arbitrary splits when business requirements specify tolerance-based accuracy.

Instead:

- Define acceptable tolerance; pick relative/absolute error bounds suited to the numeric domain.
- For money, use integer minor units or `BigDecimal` with an explicit rounding policy.
- Do not round inside every accumulator/combiner step when business rules specify rounding **after summing**, because intermediate rounding breaks associativity.
- Test `int`/`long` overflow separately: use `Math.addExact`/`Math.multiplyExact` when failures must surface instead of wrapping silently.

To test a `reduce` with `BigDecimal`, use `BigDecimal.ZERO` and `BigDecimal::add` without a `MathContext` for exact summation, then round at the business boundary. **Never assume every `reduce` is associative**: associativity is a contract the accumulator and combiner author must uphold.

## 18. Testing Pipelines with I/O Sources and Resource Lifecycles

In-memory random generation tests logic quickly and reproducibly, yet **does not prove** I/O sources close properly.

Example:

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.stream.Stream;

static long countNonBlankLines(Path path) throws Exception {
    try (Stream<String> lines = Files.lines(
            path, StandardCharsets.UTF_8)) {
        return lines
                .filter(line -> !line.isBlank())
                .count();
    }
}
~~~

`Files.lines` returns a Stream backed by a file resource; `count()` does not invoke `close()`. Lifecycle tests must cover:

- Normal completion reading the whole file.
- Early exit via `limit`, `findFirst`, or `anyMatch`.
- Exceptions thrown inside a parser/mapper.
- I/O failures when opening or reading the source.
- Source closure after every case, and never using a closed Stream.

You can verify **the closing mechanism** with `onClose`:

~~~java
import java.util.concurrent.atomic.AtomicBoolean;

AtomicBoolean closed = new AtomicBoolean();

try (Stream<Integer> stream = Stream.of(1, 2, 3)
        .onClose(() -> closed.set(true))) {
    stream.findFirst();
}

if (!closed.get()) {
    throw new AssertionError("Stream not closed");
}
~~~

This tests `onClose` on a synthetic Stream; it does not prove an OS file handle was released. Pair it with real-source integration tests or resource monitors when critical.

When a file input serves as an oracle, remember files can be written concurrently or modified between runs; use an immutable fixture or snapshot to guarantee reproducibility.

## 19. Bringing This Method into JUnit and Property-Based Frameworks

Section 7's standalone program uses only standard Java. In projects with JUnit or a property-based testing library like **jqwik**, you can express the same properties across many runner-managed trials.

Responsibility flow:

~~~text
Generator
   |
   +-- pick seed / generate valid data
   |
   v
Property
   |
   +-- invoke code under test
   +-- invoke oracle or input transformation
   +-- assert invariant / output
   |
   v
Test runner
   |
   +-- repeat across trials
   +-- report seed and input on failure
   +-- shrink counterexample (if supported)
   +-- store CI reports / artifacts
~~~

Framework benefits: build integration, test reporting, constrained generation, and built-in shrinking. Still, frameworks don't know **which business property is valid**. Write the wrong property, and the framework will happily find a "counterexample" to your mistaken assumption.

When adopting third-party tools:

- Verify library compatibility with your JDK, JUnit, and build versions.
- Configure seeds, trial counts, size bounds, and shrinking per your exact library version's API.
- Do not hardcode annotations or config names from another version without checking.
- Whenever CI catches a failure, save the **minimal input** as a standard regression test, not merely a random seed.

**Combining three test layers** outperforms relying on just one: fixed boundary fixtures, property-based tests, and integration tests against real sources/resources.

## 20. Designing Tests to Avoid Flakiness

A test can fail intermittently for two very different reasons:

1. **The pipeline is genuinely buggy:** e.g., race conditions, broken combiners, dependence on unguaranteed ordering.
2. **The test itself is flawed or non-reproducible:** unsaved seeds, mutating sources, wall-clock dependence, `HashMap` order in expected strings, or random generation inside parallel mappers.

Design checklist:

| Decision | Do | Avoid |
| --- | --- | --- |
| Seed | Log explicit per-case seed | Printing only "random failed" |
| Generator | Bounded value ranges and sizes | Unbounded or uncontrolled generation |
| Test data | Generate upfront; treat input as immutable | Mutating/generating mid-pipeline |
| Oracle | Clear loop verified with fixed fixtures | Copying the pipeline and calling it a reference |
| Map | Compare `Map.equals` | Comparing `map.toString()` expecting implicit key order |
| Ordered List | Compare content and order | Treating unordered results as ordered |
| Parallel | Assert outputs and combiner laws | Asserting fixed thread counts or thread names |
| Random in mapper | Unneeded in aggregation tests | Sharing mutable `SplittableRandom` across tasks |
| Arithmetic | Bound overflow or test overflow separately | Silent wraparound causing misleading failures |
| Failures | Log seed + input + expected/actual | Just rerunning the whole suite to "catch" flakes |
| Time/I/O | Use fixtures/snapshots, close resources | Depending on live clocks/network for expected values |
| Shrinking | Save minimal input as regression test | Keeping only a huge unreadable failing input |

For performance-sensitive applications, **benchmark only after verifying correctness**. Running 500 random trials proves nothing about speed, and ad-hoc microbenchmarks are skewed by JIT warm-up, GC, and input generation cost. Use proper tools like JMH for serious performance evaluation.

## 21. Practice Exercises

### Exercise 1 — Writing properties for `filter`

Given:

~~~java
List<Integer> actual = data.stream()
        .filter(n -> n >= 0)
        .toList();
~~~

**Task:** State two valid properties.

**Hint/Answer:** (1) Every element in `actual` is non-negative; (2) `actual` equals the list built by a loop appending `n >= 0` elements in `data`'s encounter order. Checking only property (1) is insufficient because a buggy pipeline returning `List.of()` always satisfies (1).

### Exercise 2 — Seeds and reproducibility

A test uses `new SplittableRandom(System.nanoTime())` and prints only `"failed"`. Why is it hard to debug?

**Answer:** The seed wasn't recorded, making it hard to regenerate the exact input. Log the seed, trial index, and failing input; use a constant base seed in CI and support replaying a single seed.

### Exercise 3 — Testing `groupingBy`

For the lesson's `List<Sale>`, state three valid properties for `groupingBy(region, summingLong(amount))`.

**Answer:** Matches a loop-based oracle; sum of group totals equals grand total across all transactions; permuting input leaves the Map unchanged. You can also add split-and-merge and sequential-vs.-parallel checks.

### Exercise 4 — Can we permute before `findFirst`?

A pipeline calls `findFirst()` on a priority-sorted `List`. Is the property "shuffling input preserves the result" valid?

**Answer:** No. `findFirst` returns the first element in encounter order. Shuffling can change the valid result; check the first element of the **transformed input** instead.

### Exercise 5 — Catching a broken combiner

An averaging collector stores only a `double average` per partition and merges via `(a+b)/2`. Which property catches the bug?

**Answer:** `aggregate(A ++ B) == combine(aggregate(A), aggregate(B))` on differently sized slices. The combined average is not the simple average of two group averages when group sizes differ. Store `(sum, count)`, merge pairs, and divide at the end.

### Exercise 6 — Randomness inside parallel `map`

Why is sharing one `SplittableRandom(seed)` across all lambdas in `parallelStream().map(...)` unsuitable for reproducible tests?

**Answer:** The generator holds mutable state unsafe for multi-threaded sharing; call order depends on scheduling, giving elements different values across runs. Generate inputs upfront or derive per-index deterministic generators instead.

### Exercise 7 — Can a passing property test still hide a bug?

A test checks only that every element returned by `filter(even)` is even. Production code has a bug and always returns `List.of()`. Does the test fail?

**Answer:** No. Every element in an empty list satisfies the predicate vacuously. Pair it with an oracle or appropriate cardinality/conservation checks.

### Exercise 8 — Valid domain vs. error testing

A generator emits `region == null` while the pipeline uses `groupingBy(Sale::region)` under a contract requiring non-null regions. The test throws `NullPointerException`. Is this definitely a pipeline bug?

**Answer:** No. If null regions lie outside the valid domain, either expect rejection or exclude nulls from the valid-input generator. If business logic must accept nulls, update the spec and add explicit handling.

### Exercise 9 — Shrinking parallel-only failures

Why might shrinking from 100,000 elements down to 2 elements stop reproducing a `parallelStream` bug?

**Answer:** The runtime may not split tiny inputs across multiple tasks, leaving races or broken combiners unexercised. Test combiner laws directly, or keep enough size to trigger the failure condition while recording environment details.

### Exercise 10 — Resource bugs

A pipeline reads a file with `Files.lines(path)` and calls `limit(5).toList()`. How do you write a more reliable test?

**Answer:** Wrap `Files.lines` in `try-with-resources` and check the first five lines; add tests for exception/short-circuit paths and verified resource closure. Never treat `toList` as an automatic file-closing mechanism.

## 22. Key Takeaways

- **Property-based testing** checks general laws over many inputs, not just a few hardcoded examples.
- Use **controlled seeds** for reproducible random data; log seed, configuration, and failing input.
- Build **independent oracles** whenever possible; add invariants and *metamorphic* relations to reduce the risk of oracle and implementation sharing bugs.
- Pick contract-aligned properties: per-group sums are order-independent, whereas `findFirst`, `limit`, `takeWhile`, and `joining` can depend on encounter order.
- Test **associativity, identity, and merging** whenever reductions/collectors run in parallel; never populate shared mutable collections via `parallelStream().forEach`.
- **Generate data before running pipelines**; avoid shared mutable generators inside parallel mappers.
- Always maintain fixed boundary fixtures: empty, single element, duplicates, invalid nulls, zeros, and extreme values.
- Shrink failing inputs and save them as regression tests; seeds enable replay while minimal inputs reveal root causes faster.
- Separate semantic testing from performance benchmarks and resource-lifecycle tests; `peek` never guarantees exact callback invocation counts.

**Main takeaway:** To debug Stream API pipelines effectively, test **properties that must always hold** across varied inputs while keeping every counterexample **reproducible and shrinkable**. Combining deterministic seeds, clear oracles, group invariants, parallel checks, boundary fixtures, and resource-closure tests gives far stronger evidence than unrecorded random runs.
