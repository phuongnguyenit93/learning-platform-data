# Comparing Sequential and Parallel Results

The Java Stream API lets you switch execution modes on many pipelines simply by calling `parallel()` or `parallelStream()`. However, **running without errors** does not mean **producing the right result**. A sequential pipeline can look completely reasonable yet lose elements, miscount, throw intermittent exceptions, or return different values across runs when executed in parallel. To debug effectively, you must first determine **which outputs must be semantically identical**, and only then write the matching comparison.

This lesson belongs to the **Debugging and Testing Pipelines** chapter of the `JAVA_STREAM_API` module. We will build techniques for comparing sequential and parallel results across `filter`, `map`, `reduce`, `collect`, `groupingBy`, ordered operations, and short-circuiting operations. At the same time, we analyze why outputs can diverge due to side effects, shared accumulators, invalid merge functions, floating-point rounding, unguaranteed ordering, or mutating sources—concluding with a reproducible test suite and a diagnostic workflow for parallel-only failures.

Main examples use **Java 8 or higher**, except JUnit Jupiter test illustrations that require the testing library dependency. Top-level Java statements in snippets should be placed inside a method (such as `main`) or run in JShell; helper classes can be saved separately. `Stream` is a declarative, lazy data-processing API; enabling `parallel` does not waive requirements around state safety, I/O resource lifecycles, or performance bounds.

## 1. The Goal Is Not Always Comparing Two Printed Strings

Consider the following pipeline:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> source = Arrays.asList(5, 2, 3, 4, 1);

List<Integer> sequential = source.stream()
        .filter(n -> n % 2 == 1)
        .map(n -> n * n)
        .collect(Collectors.toList());

List<Integer> parallel = source.parallelStream()
        .filter(n -> n % 2 == 1)
        .map(n -> n * n)
        .collect(Collectors.toList());

System.out.println(sequential); // [25, 9, 1]
System.out.println(parallel);   // [25, 9, 1]
```

The source is a `List` with positional **encounter order**. Neither `filter` nor `map` alters encounter order here; `Collectors.toList()` collects elements in encounter order. Therefore, with fixed data and pure functions, both lists **must match in both content and order**.

Now look at a different example:

```java
import java.util.Set;
import java.util.stream.Collectors;

Set<Integer> a = source.stream()
        .map(n -> n % 3)
        .collect(Collectors.toSet());

Set<Integer> b = source.parallelStream()
        .map(n -> n % 3)
        .collect(Collectors.toSet());

System.out.println(a.equals(b)); // true
```

`Set` has no traversal-order requirement in this example. If printing both sets shows different iteration orders, that is **not necessarily a bug**: what matters is **which elements belong to the set**, not display order.

**First principle:** define the **output contract** before choosing how to compare. Never use `toString()` or thread logs as a universal pass/fail oracle for every pipeline.

## 2. Common Result Contracts to Distinguish

| Result shape | What to compare | What never to assume |
| --- | --- | --- |
| `List<T>` from ordered source, order-preserving collector | Same size, same value at every index | Threads ran in chronological order |
| `Set<T>` | Same elements by `equals/hashCode` | Identical iteration or print order |
| `Map<K,V>` counting/summing by key | Same keys and per-key values | Identical Map iteration order |
| `double` aggregation result | Within defined tolerance; handle `NaN`/infinity separately | Always bitwise identical |
| `findFirst` on ordered source | Same first element in encounter order | Same number of predicate invocations |
| `findAny` | **Any** element matching condition, or empty per contract | Same element picked every run |
| `forEach` with side effects | Should not treat side effects as standard output | Fixed callback order or thread |
| `groupingByConcurrent(..., toList())` | Groups and element multisets per group when order isn't required | Element order within each group |

A **multiset** (*bag*) tracks multiplicity as well as membership. For instance, `[A,A,B]` and `[A,B,B]` share the same Set `{A,B}` yet are **not the same multiset**. When order doesn't matter but occurrence counts do, converting blindly to a `Set` discards vital test information.

If business logic needs the "latest record," define an explicit sort key or tie-breaker instead of letting parallel execution pick whichever record happens to finish last.

## 3. Why Can a Pipeline Pass Sequentially Yet Fail in Parallel?

Four common categories of root causes:

1. **Sharing mutable state outside the pipeline**: multiple threads concurrently mutate an `ArrayList`, `HashMap`, counter, or non-thread-safe object.
2. **Invalid reductions**: wrong identity, incompatible accumulator/combiner, or non-*associative* operation.
3. **Unwarranted encounter-order assumptions**: `findAny`, `forEach`, `unordered`, or concurrent/unordered collectors.
4. **Numeric and source discrepancies**: floating-point rounding, overflow, mutating the source mid-traversal, or functions reading clocks, random generators, or external I/O.

`parallel()` only switches the **execution mode**; it does not add locks around external mutable variables, fix a broken combiner, or snapshot a mutable source.

### Illustrating the two collection paths

```text
SEQUENTIAL
  source -> map/filter -> accumulator A -> result

PARALLEL, NON-concurrent collector
  source
    |---- chunk 1 -> A1 --\
    |---- chunk 2 -> A2 ---+--> combiner --> result
    |---- chunk 3 -> A3 --/

PARALLEL, proper concurrent collector
  source -> multiple tasks -> shared thread-safe accumulator A -> result
```

Most standard Collectors do not require sharing one container across branches. The fact that `Collectors.toList()` works on parallel streams **does not mean** `ArrayList` is thread-safe for calling `add` inside `parallel().forEach(...)`.

## 4. Building a Reusable Comparison Helper

To test the same pipeline in both modes, you need **two fresh Streams over the same stable data**. A Stream that has already run a terminal operation cannot run again.

Below is a helper for re-creatable in-memory sources:

```java
import java.util.Objects;
import java.util.function.BiPredicate;
import java.util.function.Function;
import java.util.function.Supplier;
import java.util.stream.Stream;

public final class StreamComparison {
    private StreamComparison() {}

    public static <T, R> void assertEquivalent(
            Supplier<Stream<T>> freshSource,
            Function<Stream<T>, R> pipeline,
            BiPredicate<? super R, ? super R> equivalent) {

        Objects.requireNonNull(freshSource, "freshSource");
        Objects.requireNonNull(pipeline, "pipeline");
        Objects.requireNonNull(equivalent, "equivalent");

        R sequential;
        R parallel;

        try (Stream<T> stream = freshSource.get()) {
            sequential = pipeline.apply(stream.sequential());
        }

        try (Stream<T> stream = freshSource.get()) {
            parallel = pipeline.apply(stream.parallel());
        }

        if (!equivalent.test(sequential, parallel)) {
            throw new AssertionError(
                    "Sequential=" + sequential
                    + ", parallel=" + parallel
            );
        }
    }
}
```

Usage for an ordered `List`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;

List<Integer> values = Arrays.asList(1, 2, 3, 4, 5, 6);

StreamComparison.assertEquivalent(
        values::stream,
        s -> s.filter(n -> n % 2 == 0)
              .map(n -> n * 10)
              .collect(Collectors.toList()),
        Objects::equals
);
```

Things to keep in mind:

- `freshSource.get()` must return **a new Stream each time**, never the same consumed Stream.
- The data across both runs must be **stable and semantically identical**; if the source mutates, the comparison is invalid.
- `pipeline` must not depend on external mutable variables, wall-clock time, or unseeded randomness; it must execute a **terminal operation** and return a completed result, not a lazy Stream tied to a closed source.
- `try-with-resources` ensures the helper closes each Stream. For `List`, `close()` normally releases nothing; for I/O sources, closing truly matters.
- `BiPredicate` allows **semantic comparison** instead of forcing `equals` everywhere.

If the source factory throws a checked `IOException`, `Supplier<Stream<T>>` does not declare `throws IOException`; use a throwing functional interface or open the file separately in two `try` blocks as shown later.

**Never** pass a single-use `Iterator`, an already-closed `BufferedReader`, or a reused Stream instance to this factory expecting both runs to read the same data.

## 5. Testing Pipelines That Preserve Encounter Order

With an ordered source and stateless transformations, output order must be preserved when the terminal operation guarantees ordering.

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> normalize(Stream<String> stream) {
    return stream
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .map(String::toUpperCase)
            .collect(Collectors.toList());
}

List<String> input = Arrays.asList(
        "  apple ", "", "banana ", " apple", "cherry "
);

List<String> a = normalize(input.stream());
List<String> b = normalize(input.parallelStream());

System.out.println(a);         // [APPLE, BANANA, APPLE, CHERRY]
System.out.println(a.equals(b)); // true
```

This compares using `List.equals`, checking both element count and every index. Do not sort both lists before comparing, because sorting **can mask ordering bugs** that business logic needs to catch.

### `sorted` and tie-breaking rules

When sorting objects, the comparator should specify a total order whenever deterministic output is required across equal primary keys.

```java
import java.util.Comparator;

// Example comparator definition for an Employee type with id and score.
Comparator<Employee> order = Comparator
        .comparingInt(Employee::score)
        .reversed()
        .thenComparing(Employee::id);
```

This snippet assumes `Employee` has `score()` and `id()`. If you compare only `score`, multiple employees with equal scores tie. On ordered sources, `sorted` has stability guarantees, yet on unordered sources or pipelines that drop order, adding the secondary key `id` keeps results independent of encounter order.

Never mutate fields used in comparators or `hashCode` while a Stream is traversing elements.

## 6. Comparing `Set`, `Map`, and Group Statistics

### `Set`: compare by elements, not printed string

```java
import java.util.Arrays;
import java.util.Set;
import java.util.stream.Collectors;

Set<String> seq = Arrays.asList(
        "A", "B", "A", "C"
).stream().collect(Collectors.toSet());

Set<String> par = Arrays.asList(
        "A", "B", "A", "C"
).parallelStream().collect(Collectors.toSet());

if (!seq.equals(par)) {
    throw new AssertionError("Distinct values differ");
}
```

Do not use `seq.toString().equals(par.toString())`. Both Sets can hold identical elements while iterating in different orders.

### `Map`: compare by keys and counts

```java
import java.util.Arrays;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentMap;
import java.util.function.Function;
import java.util.stream.Collectors;

List<String> levels = Arrays.asList(
        "ERROR", "WARN", "INFO", "ERROR", "WARN", "ERROR"
);

Map<String, Long> seq = levels.stream()
        .collect(Collectors.groupingBy(
                Function.identity(),
                Collectors.counting()
        ));

ConcurrentMap<String, Long> par = levels.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Function.identity(),
                Collectors.counting()
        ));

System.out.println(seq);            // Do not rely on Map print order
System.out.println(seq.equals(par)); // true
```

`groupingByConcurrent` does not guarantee encounter order for elements inside each group. Here, however, it only stores per-key **counts**, so `Map.equals` is completely valid. With fixed data and non-overflowing counts, `ERROR=3`, `WARN=2`, `INFO=1`.

### When Map values are `List`s and order is not guaranteed

If each group holds a list, direct `List.equals` can fail solely because **element order within a group** differs. When the business ignores intra-group order yet cares about multiplicity, copy and sort each group's list to compare as a **multiset**:

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

static Map<String, List<Integer>> canonicalize(
        Map<String, ? extends List<Integer>> input) {

    Map<String, List<Integer>> normalized = new TreeMap<>();

    input.forEach((key, values) -> {
        List<Integer> copy = new ArrayList<>(values);
        Collections.sort(copy);
        normalized.put(key, copy);
    });

    return normalized;
}
```

`canonicalize` preserves every occurrence's multiplicity by **not deduplicating**. It assumes non-null string keys and non-null integers so `TreeMap`/`Collections.sort` work in natural order; adjust if your data model allows nulls.

Crucially: canonicalize **only** when the contract genuinely ignores order. If intra-group order must be preserved, sorting before comparing masks real bugs.

## 7. `findFirst`, `findAny`, and Short-Circuiting

These two operations have distinct contracts:

- `findFirst()`: on a Stream **with encounter order**, returns the first matching element in that order if one exists.
- `findAny()`: may return **any** matching element, useful when order isn't needed or to reduce parallel coordination.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;

List<Integer> numbers = Arrays.asList(5, 8, 11, 14, 17);

Optional<Integer> firstSequential = numbers.stream()
        .filter(n -> n % 2 == 0)
        .findFirst();

Optional<Integer> firstParallel = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .findFirst();

System.out.println(firstSequential);           // Optional[8]
System.out.println(firstSequential.equals(
        firstParallel));                       // true
```

However:

```java
Optional<Integer> anyParallel = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .findAny();

if (!anyParallel.isPresent()
        || (anyParallel.get() != 8
            && anyParallel.get() != 14)) {
    throw new AssertionError("findAny returned invalid value");
}
```

Since the list contains two even numbers, `findAny` may return 8 or 14; **never require it to always pick 8**. In general tests, verify the returned element **belongs to the valid solution set**, and that presence/absence matches whether the solution set is empty.

### Testing `anyMatch`, `allMatch`, `noneMatch`

With pure predicates and fixed inputs, these boolean results must match between sequential and parallel. However, **how many times the predicate runs need not match**, due to short-circuiting:

```java
boolean seq = numbers.stream().anyMatch(n -> n > 10);
boolean par = numbers.parallelStream().anyMatch(n -> n > 10);

System.out.println(seq == par); // true
```

Never write tests expecting `peek` or a predicate to be called exactly `k` times in a parallel pipeline. One task may find a match while sibling tasks are still evaluating other elements.

### `limit`, `skip`, and `unordered`

On an ordered source, `limit(n)` means taking **the first n elements in encounter order**. If `unordered()` is applied, the chosen elements are permitted to differ:

```java
List<Integer> sample = numbers.parallelStream()
        .unordered()
        .limit(2)
        .collect(java.util.stream.Collectors.toList());
```

A valid test here checks `sample.size() == 2` and every element belongs to the source; **do not require** the result to be `[5,8]`. `unordered()` is not a random shuffle, yet dropping order constraints changes the semantics of taking leading elements.

## 8. Side Effects Are the Most Common Source of Bugs

### Wrong example: multiple threads adding to an `ArrayList`

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

// WRONG: ArrayList is not safe for concurrent add from multiple threads.
IntStream.range(0, 100_000)
        .parallel()
        .forEach(shared::add);

// Never assume shared.size() will always equal 100_000.
```

The result can drop elements, throw exceptions, or occasionally pass by sheer luck. Running 100 times without failing **does not prove thread safety**.

Replace with a collector:

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

List<Integer> safe = IntStream.range(0, 100_000)
        .boxed()
        .parallel()
        .collect(Collectors.toList());

System.out.println(safe.size()); // 100000
System.out.println(safe.get(0));  // 0
```

With an ordered `IntStream.range` source and `toList`, the resulting List preserves encounter order. In the first snippet, `forEach` **does not guarantee** calling in source order; even switching to a synchronized collection to prevent data races wouldn't preserve insertion order.

### Do not use external mutable counters

```java
int[] count = {0};

// WRONG: updating shared count[0]++ is non-atomic.
numbers.parallelStream().forEach(n -> count[0]++);
```

Count properly:

```java
long countEven = numbers.parallelStream()
        .filter(n -> n % 2 == 0)
        .count();

System.out.println(countEven); // 2
```

Using `AtomicInteger` avoids lost increments, yet **does not make side-effecting transformations non-interfering, deterministic, or ordered**. When the goal is aggregation, use `count`, `sum`, `reduce`, or `collect`.

### Another bug: mutating the source during traversal

```java
// WRONG: do not structurally modify source while traversing it.
source.parallelStream()
        .forEach(n -> source.remove(n));
```

A source like `ArrayList` cannot tolerate structural interference under the Stream contract. Similarly, reading and mutating the same `HashMap` inside `map` or `filter` leads to unpredictable behavior.

Transform into a **new** structure and replace the source only after the pipeline completes, rather than mutating the source while it is being consumed.

## 9. Debugging `reduce`: Identity, Associativity, Compatibility

Correct parallel reductions must obey identity and associativity contracts.

### Wrong: non-associative subtraction

```java
import java.util.Arrays;
import java.util.List;

List<Integer> values = Arrays.asList(1, 2, 3, 4);

int seq = values.stream()
        .reduce(0, (a, b) -> a - b);

int par = values.parallelStream()
        .reduce(0, (a, b) -> a - b);

System.out.println(seq); // -10
System.out.println(par); // Not guaranteed to equal -10
```

Because:

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Changing how branches are grouped changes the result. A parallel `reduce` can combine partial results differently than sequential execution, so subtraction cannot be used as an associative combiner.

Fix when the real goal is summing:

```java
int sumSeq = values.stream().reduce(0, Integer::sum);
int sumPar = values.parallelStream().reduce(0, Integer::sum);

System.out.println(sumSeq); // 10
System.out.println(sumSeq == sumPar); // true
```

### Wrong: non-identity initial value

```java
// WRONG if trying to sum source elements.
int seqWithWrongIdentity = values.stream()
        .reduce(10, Integer::sum);

int parWithWrongIdentity = values.parallelStream()
        .reduce(10, Integer::sum);
```

Here `10` **is not an identity** for addition. Sequential adds 10 once, whereas parallel can inject the identity across multiple partitions. If summing, the identity must be `0`.

For finding the maximum over negative numbers, use `reduce(Integer::max)` returning `Optional<Integer>` or choose an identity genuinely valid for the domain; never assume `reduce(0, Integer::max)` is always right.

### Three-argument `reduce` also has a combiner

```java
import java.util.Arrays;
import java.util.List;

List<String> words = Arrays.asList("a", "bb", "ccc");

int lengthSeq = words.stream()
        .reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum
        );

int lengthPar = words.parallelStream()
        .reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum
        );

System.out.println(lengthSeq);           // 6
System.out.println(lengthSeq == lengthPar); // true
```

For `reduce(identity, accumulator, combiner)`, verify:

- `identity` is a valid initial state.
- `combiner` is associative.
- `combiner` is compatible with how `accumulator` incorporates each element.
- Neither function interferes with the source or any shared mutable object.

Never confuse immutable `reduce` with mutable `collect` by sharing an `ArrayList` as `identity`; that breaks the contract across multiple branches.

## 10. `collect`: Why Can a Mutable Container Still Be Safe?

`collect(supplier, accumulator, combiner)` lets the framework allocate **separate containers** and merge them via `combiner`. A non-thread-safe `ArrayList` or accumulator class **can still be completely safe** when not shared across branches and not falsely marked concurrent.

Example aggregating count and sum:

```java
import java.util.Arrays;
import java.util.List;

final class Stats {
    private long count;
    private long sum;

    void add(Integer value) {
        count++;
        sum += value;
    }

    void merge(Stats other) {
        count += other.count;
        sum += other.sum;
    }

    long count() {
        return count;
    }

    long sum() {
        return sum;
    }
}

List<Integer> data = Arrays.asList(1, 2, 3, 4, 5);

Stats sequential = data.stream()
        .collect(Stats::new, Stats::add, Stats::merge);

Stats parallel = data.parallelStream()
        .collect(Stats::new, Stats::add, Stats::merge);

System.out.println(sequential.count()); // 5
System.out.println(parallel.count());   // 5
System.out.println(sequential.sum());   // 15
System.out.println(parallel.sum());     // 15
```

Key points:

- `Stats::new` creates a fresh instance each time the Supplier is called.
- `add` updates only the accumulator instance handed to it.
- `merge` combines full state from both partitions without dropping elements.
- `Stats` is read **after** `collect` finishes, with no external task modifying it.

If the Supplier returns the same `Stats` created outside the Stream, that is a shared-state bug. If the combiner returns only one side without merging, parallel runs lose counts or sums.

For custom Collectors, distinguish `Collector.Characteristics.CONCURRENT` from `Spliterator.CONCURRENT` and parallel execution. Never declare `CONCURRENT` unless the accumulator safely supports concurrent calls on a single container.

## 11. Floating-Point Numbers: Business Correctness Does Not Mean Bitwise Equality

Floating-point addition is not strictly associative due to rounding:

```text
(1e16 + 1) + (-1e16) can become 0
1e16 + (1 + (-1e16)) can also become 0
yet different groupings and orders can keep or lose small numbers
```

Comparison example:

```java
import java.util.Arrays;
import java.util.List;

List<Double> amounts = Arrays.asList(
        1.0e16, 1.0, -1.0e16, 1.0
);

double sequential = amounts.stream()
        .reduce(0.0, Double::sum);

double parallel = amounts.parallelStream()
        .reduce(0.0, Double::sum);

System.out.println(sequential); // 1.0 under this sequential grouping order
System.out.println(parallel);   // May differ due to grouping order
```

The exact mathematical sum is `2.0`. Some floating-point summation orders round away `1.0` and produce different numbers. Avoid writing tests that unconditionally require two `double`s to be **bitwise identical** across every parallel reduction.

### Comparing with tolerance

```java
static boolean approximatelyEqual(
        double a, double b,
        double absoluteTolerance,
        double relativeTolerance) {

    if (Double.doubleToLongBits(a)
            == Double.doubleToLongBits(b)) {
        return true;
    }

    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        return false;
    }

    double scale = Math.max(Math.abs(a), Math.abs(b));
    double allowed = Math.max(
            absoluteTolerance,
            relativeTolerance * scale
    );

    return Math.abs(a - b) <= allowed;
}
```

This helper:

- Matches bitwise-identical values via `doubleToLongBits`.
- Rejects mismatched `NaN`/infinity cases; when both sides are `NaN`, canonical bit comparison treats them as equal. If your application must treat any `NaN` as a data error, check for `NaN` explicitly first.
- Combines absolute and relative tolerances; **thresholds must come from business requirements**, never chosen arbitrarily to hide bugs.
- Does not solve integer overflow, unit mismatches, or wrong formulas. Tolerance is solely for acceptable numeric rounding.

When monetary calculations require **exact** results, use `BigDecimal` (with an explicit scale/rounding policy) or integer minor units instead of `double`:

```java
import java.math.BigDecimal;
import java.util.Arrays;
import java.util.List;

List<BigDecimal> money = Arrays.asList(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"),
        new BigDecimal("0.30")
);

BigDecimal seq = money.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal par = money.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(seq.compareTo(par) == 0); // true
```

This example uses `BigDecimal.add` without a `MathContext`, so decimal addition is exact; if rounding is applied at intermediate steps, associativity must be re-evaluated.

## 12. Integer Overflow: Two Matching Results Can Still Both Be Wrong

Suppose inputs are large and the sum exceeds `int` range:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> values = Arrays.asList(
        Integer.MAX_VALUE, 1
);

int seq = values.stream().mapToInt(Integer::intValue).sum();
int par = values.parallelStream().mapToInt(Integer::intValue).sum();

System.out.println(seq);          // -2147483648 due to int overflow
System.out.println(seq == par);  // true, yet the business sum is wrong
```

`int` addition wraps on overflow per Java semantics; both pipelines can return the same invalid business total. Thus **sequential-vs.-parallel comparison is a necessary check, not sufficient proof of correctness**.

If the sum fits within `long`, widen before summing:

```java
long safeSum = values.stream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(safeSum); // 2147483648
```

When sums can exceed `Long.MAX_VALUE`, use wider arithmetic or overflow detection. Do not assume `Math.addExact` throws identically under every merge order if intermediate partial sums can exceed bounds even when the final sum fits.

A solid test suite verifies **an independent expected value** using the right numeric model, rather than only asserting `seq.equals(par)`.

## 13. Debugging Pipelines With Controlled Intermediate Steps

When results diverge, don't immediately litter `println` inside every `map` and deduce behavior from log order. In parallel streams, logs from multiple threads interleave and can alter execution timing.

### Sample pipeline

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static List<String> pipeline(Stream<String> lines) {
    return lines
            .map(String::trim)
            .filter(s -> !s.isEmpty())
            .filter(s -> s.startsWith("ERR"))
            .map(String::toLowerCase)
            .distinct()
            .sorted()
            .collect(Collectors.toList());
}
```

Systematic inspection steps:

1. **Source:** element count, immutability, encounter order, and nulls.
2. **Filters:** confirm which elements should survive using a small example with known output.
3. **Transformations:** verify functions are pure, stateless, and do not mutate the source.
4. **Stateful ops:** check memory or ordering requirements of `distinct`/`sorted`/`limit`.
5. **Terminal:** does the result type guarantee order? Does the Collector have a valid combiner?
6. **Comparison:** use a contract-aligned comparison (`List.equals`, `Map.equals`, multiset, tolerance, etc.).

### `peek` helps observe, not serve as a test oracle

```java
long result = Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .peek(n -> System.out.println(
                Thread.currentThread().getName() + ": " + n))
        .count();
```

This does not guarantee `peek` runs four times. Pipelines with a `SIZED` source and `count()` can optimize without traversing every element, so `peek` might not run at all. Even when it does, parallel log order is not data order.

Use `peek` for **temporary diagnostics**, never as business logic and never writing assertions on log line counts or thread names.

## 14. Testing with JUnit: Assert Outcomes Instead of Thread Schedules

The following example uses **JUnit Jupiter** and requires that test dependency in the project; the Java Stream code itself does not depend on JUnit.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;
import java.util.stream.Stream;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class ParallelPipelineTest {

    private static List<Integer> squaresOfEven(
            Stream<Integer> stream) {

        return stream.filter(n -> n % 2 == 0)
                .map(n -> n * n)
                .collect(Collectors.toList());
    }

    @Test
    void parallelMatchesSequentialForOrderedResult() {
        List<Integer> input = IntStream.range(0, 10000)
                .boxed()
                .collect(Collectors.toList());

        List<Integer> seq = squaresOfEven(input.stream());
        List<Integer> par = squaresOfEven(input.parallelStream());

        assertEquals(seq, par);
        assertEquals(5000, seq.size());
        assertEquals(Integer.valueOf(0), seq.get(0));
        assertEquals(Integer.valueOf(9998 * 9998), seq.get(4999));
    }
}
```

**Expected-value note:** `9998 * 9998` still fits within `int`, so it does not overflow in this example. When increasing the range further, switch multiplication to `long` and use the appropriate List type.

JUnit's `assertEquals` uses `List.equals`, checking order as well. If requirements ignore order, canonicalize or compare multisets rather than imposing order solely because the framework returned a List.

### Testing multiple datasets with fixed seeds

```java
import java.util.List;
import java.util.Map;
import java.util.Random;
import java.util.stream.Collectors;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GroupingPropertyTest {

    private static Map<Integer, Long> histogram(
            java.util.stream.Stream<Integer> stream) {

        return stream.collect(Collectors.groupingBy(
                value -> Math.floorDiv(value, 10),
                Collectors.counting()
        ));
    }

    @Test
    void groupedCountsMatchAcrossGeneratedInputs() {
        for (int seed = 0; seed < 40; seed++) {
            Random random = new Random(seed);

            List<Integer> values = random
                    .ints(2000, -100, 101)
                    .boxed()
                    .collect(Collectors.toList());

            Map<Integer, Long> seq =
                    histogram(values.stream());

            Map<Integer, Long> par =
                    histogram(values.parallelStream());

            assertEquals(seq, par, "seed=" + seed);
            assertEquals(2000L,
                    seq.values().stream()
                            .mapToLong(Long::longValue)
                            .sum());
        }
    }
}
```

Fixed seeds make failing cases reproducible. `Random.ints` here is consumed **sequentially before** running both pipeline modes over the generated List. Never share a mutable `Random` inside `parallel().map(...)` expecting identical random draws per element across modes.

Testing 40 datasets can catch data-dependent bugs, yet **cannot prove** every interleaving is safe. If a rare race appears, analyze shared state with proper concurrency tools instead of merely raising iteration counts.

## 15. Test Across Varied Sizes and Partitionings

A broken combiner may stay hidden on tiny inputs if the framework never splits work as expected. Test:

| Dataset | Bugs it can expose |
| --- | --- |
| Empty source | Identity, Optional, empty collector behavior |
| One element | Initialization, finisher, combiner-skipped path |
| Two elements | First/last handling, merging two states |
| Odd count | Dropping final element or uneven chunks |
| Many duplicates | `distinct`, group counts, duplicate-key merges |
| Negative, 0, and huge values | Wrong identity, overflow, `floorDiv` |
| Inputs with nulls (if permitted) | Null handling in mapper/classifier |
| Ordered lists and unordered sources | Differing encounter-order requirements |
| 10, 100, 1,000, 100,000 elements | Diverse splitting trees and memory cost |
| Repeated parallel runs | Reproducing intermittent races |

For a sound aggregation, also test **independence from grouping structure**. For addition:

```text
((a + b) + c) == (a + (b + c))
```

For non-overflowing integers, addition is associative. For string joining, operand order matters yet concatenation is associative if order is preserved; for subtraction or division, operations are generally non-associative.

### Changing thread counts is not a test oracle

Never write tests tied to `ForkJoinPool.commonPool().getParallelism()` or expecting specific worker threads to appear. Thread counts, `Spliterator` splitting, and execution schedules belong to the runtime environment and implementation; they can vary across JDKs and machines.

A sound test asserts **result semantics** and safety contracts, not internal thread layouts.

## 16. Comparing on I/O Sources: Open Two Separate Passes

With `Files.lines`, each Stream normally holds a resource requiring closure. Never consume the same Stream twice.

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import java.util.function.Function;
import java.util.stream.Collectors;
import java.util.stream.Stream;

static Map<String, Long> countLogLevels(
        Path path, boolean parallel) throws IOException {

    try (Stream<String> lines =
            Files.lines(path, StandardCharsets.UTF_8)) {

        Stream<String> mode =
                parallel ? lines.parallel() : lines.sequential();

        return mode
                .filter(line -> line.contains(":"))
                .map(line -> line.substring(
                        0, line.indexOf(':')))
                .collect(Collectors.groupingBy(
                        Function.identity(),
                        Collectors.counting()
                ));
    }
}
```

Comparison:

```java
Map<String, Long> sequential = countLogLevels(path, false);
Map<String, Long> parallel = countLogLevels(path, true);

if (!sequential.equals(parallel)) {
    throw new AssertionError("Log counts differ");
}
```

Both calls **open two separate Streams** and close them with `try-with-resources`. This comparison is meaningful only if the file **is not modified** between passes. In automated tests, use a fixed fixture; on live log files, capture an immutable snapshot before comparing.

`Files.lines` can throw `IOException` on open and `UncheckedIOException` during lazy traversal. Never catch all exceptions and substitute an empty Map: that could make both modes appear "equal" even though both failed to read.

When using `BufferedReader.lines()`, close the Reader where it is owned. `collect`/`count`/`findFirst` do not close I/O sources automatically. Enabling parallel never waives this lifecycle responsibility.

## 17. Performance Testing Differs from Correctness Testing

Comparing elapsed time never answers "do both outputs mean the same thing?" When evaluating parallel execution:

1. **Prove correctness first:** compare against an oracle/expected result and verify sequential–parallel equivalence.
2. **Fix the input:** identical size, value distribution, source, and conditions.
3. **Isolate I/O effects:** benchmarking file reads differs from benchmarking in-memory processing.
4. **Warm up and repeat:** JIT, GC, and scheduling make a single timing meaningless.
5. **Measure memory/throughput/latency:** parallelism may raise throughput while increasing buffering, allocation, and coordination overhead.
6. **Remove `System.out.println` from measured pipelines:** synchronized console logging can dominate runtime.
7. **Evaluate per environment:** CPU cores, JDK, source structure, group counts, and Collector traits all affect performance.

For example, `parallel().sorted().collect(toList())` can incur heavy memory and coordination costs; a cheap `map` over a few hundred elements rarely benefits from splitting.

In Java, use a dedicated microbenchmark harness like JMH when measuring performance. Still, **you never need a benchmark** to verify pipeline correctness; the two activities have separate goals.

## 18. Diagnostic Workflow When Differences Appear

```text
Detected sequential != parallel
               |
               v
  Did both passes see the exact same data?
       | No  -> freeze snapshot / input
       v Yes
  Does the contract permit different ordering?
       | Yes -> compare Set/Map/multiset/solution criteria
       v No, or still wrong
  Is there shared mutable state / side effects?
       | Yes -> remove side effects, use proper collector
       v No
  Are reduce/combiner valid identity & associative?
       | No  -> fix aggregation operation
       v Yes
  Any double/NaN/overflow/parse errors?
       | Yes -> check numeric oracle & tolerance
       v No
  Any unordered/short-circuit/source lifecycle issue?
       | Yes -> align test with contract
       v No
  Shrink input + fix seed + repeat parallel runs
               |
               v
  File bug with fixture, expected, actual, JDK
```

A useful bug report includes: minimal input, expected result rule, pipeline code, sequential/parallel mode, seed if any, Collector type, JDK environment, and whether the failure is **wrong value**, **missing element**, **wrong order**, **exception**, or **non-termination**.

Never blame a "Java parallel stream bug" before verifying that the accumulator, comparator, source, and lambdas all obey their contracts.

## 19. Practice Exercises

### Exercise A: Comparing ordered Lists

Generate numbers from 0 to 999, keep even numbers, square them as `long`, and collect to a List. Compare sequential and parallel outputs by order, then intentionally replace `collect(toList())` with `forEach` writing to a shared List and explain why the second version is invalid.

**Criteria:** Lists compared via `equals`; exact element count; no shared mutable state in the valid pipeline.

### Exercise B: Testing grouping with duplicate keys

From the tokens:

```text
ERROR WARN INFO ERROR ERROR WARN
```

Build `Map<String,Long>` with `groupingBy(..., counting())` and compare against `groupingByConcurrent(..., counting())`. Verify `ERROR=3`, `WARN=2`, `INFO=1`; never compare Map print order.

### Exercise C: Creating an intentional failing test

Use:

```java
Arrays.asList(1, 2, 3, 4)
        .parallelStream()
        .reduce(0, (a, b) -> a - b);
```

Compare with the sequential version. Explain using non-associativity of subtraction. Then switch to `Integer::sum` with identity 0 and verify against the expected sum 10.

### Exercise D: Testing element-selection operations

Use source `[5,8,11,14,17]` and an even-number predicate. Test that `findFirst` returns 8 in both modes; test that `findAny` returns an element in `{8,14}`. Test a source with no even numbers and verify `Optional.empty()`.

### Exercise E: Generated data with a fixed seed

Generate 50 integer datasets containing negative numbers, 0, positive numbers, and duplicates. Verify histogram `value -> Math.floorDiv(value, 10)` using `groupingBy(counting())` in both modes. Add an independent check that total bucket counts equal the source length.

### Exercise F: Summarizing an I/O source

Create a small log file containing `INFO:...`, `WARN:...`, and `ERROR:...` lines. Run `countLogLevels(path,false)` and `countLogLevels(path,true)` over the same immutable snapshot. Verify the Map is right, the file is closed, and read failures are surfaced clearly.

## 20. Common Mistakes

| Mistake | Why it leads to wrong conclusions | Fix |
| --- | --- | --- |
| Comparing `Map.toString()` or `Set.toString()` | Iteration order is not part of the result contract | Compare `Map.equals`/`Set.equals` |
| Sorting output Lists when order is required | Masks order-loss bugs | Compare `List.equals` directly |
| Converting to `Set` when duplicates exist | Discards element frequencies | Compare multisets or sorted copies preserving duplicates |
| Requiring `findAny` to return the same value | `findAny` may pick any valid match | Assert solution criteria / membership |
| Asserting predicate call counts in `anyMatch` | Short-circuiting has no fixed schedule | Assert the boolean result |
| Seeing out-of-order `peek` logs and reporting a bug | Logs interleave; `peek` may be skipped | Assert output, not logs |
| Using `parallel().forEach(sharedList::add)` | `ArrayList` is not thread-safe | `collect(toList())` |
| Using `reduce` with subtraction | Non-associative | Use a valid associative op or different design |
| Wrong `reduce` identity | Identity may be applied across multiple splits | Use the true mathematical identity |
| Combiner ignores one branch | Loses data in parallel | Merge both accumulators completely |
| Supplier returns the same mutable container | Races/double-counting across branches | Allocate a fresh container per Supplier call |
| Bitwise-comparing `double` everywhere | Rounding varies with grouping order | Principled tolerance or exact decimal/integer math |
| Passing when both modes overflow identically | Both suffer the same overflow bug | Compare against an appropriately typed oracle |
| Running sequential then parallel on one Stream | Stream is already consumed | Open a fresh Stream from source |
| Reading a live log file being written during comparison | Two runs see different inputs | Immutable snapshot/fixture |
| Enabling `unordered()` for speed then expecting first items via `limit` | Order contract was dropped | Keep order if business needs it |
| Treating one parallel run as thread-safety proof | Races can be rare | Audit contracts and test varied splits |
| Benchmarking before verifying correctness | Fast yet wrong | Verify results first, benchmark later |
| Forgetting to close `Files.lines` | I/O resource leak | `try-with-resources` |

## 21. Checklist Before Accepting a Parallel Pipeline

1. Do both comparison runs read **identical** data without mid-traversal mutation?
2. Are `filter`, `map`, classifiers, and comparators **stateless and non-interfering**?
3. Is any external mutable `ArrayList`/`HashMap`/counter accessed by multiple threads?
4. Does `reduce` have valid identity, accumulator, combiner, and associativity?
5. Does `collect` have a fresh-container Supplier, complete combiner, and accurate characteristics?
6. Is the output an ordered List, Set, Map, multiset, single extreme, or floating-point number? **Does the comparison match its semantic contract?**
7. With `findAny`, `limit`, or `unordered()`, are we imposing ordering guarantees the API does not make?
8. Have we handled empty sources, single elements, duplicate keys, nulls, negatives, overflow, and `NaN`/infinity where needed?
9. Does the test have an **independent expected-value oracle**, rather than only comparing two runs that could fail together?
10. Have we tested multiple sizes and reproducible seeds without depending on thread names or schedules?
11. For I/O sources, did both passes open valid streams and close resources properly?
12. Once correctness is established, do empirical measurements show parallelism actually helps the real workload?

## 22. Self-Check Questions

1. Can two runs reuse the same `Stream` instance after a terminal operation? **No**, create a fresh Stream.
2. With an ordered `List` and `Collectors.toList()`, what should you compare? **Count, values, and order**, e.g. via `List.equals`.
3. With a `Set`, is a different print order across runs a bug? **No**, compare membership via `Set.equals`.
4. When a Map stores only `Long` counts per key, how should Maps be compared? **`Map.equals`**, not print order.
5. If a Map holds unordered lists with duplicate elements, is converting values to `Set` valid? **No**, that loses frequencies; use multisets or sorted copies.
6. Does `findFirst` on an ordered source preserve first-element semantics in parallel? **Yes**, by encounter order.
7. Must `findAny` return the same element as `findFirst`? **No**.
8. Why avoid asserting predicate invocation counts in `anyMatch`? **Because short-circuiting and work splitting can vary**.
9. Why is `parallel().forEach(arrayList::add)` dangerous? **Multiple threads mutate a non-thread-safe List**.
10. Can `Collectors.toList()` run safely on parallel streams even though `ArrayList` isn't thread-safe? **Yes**, the collector manages per-branch containers per contract.
11. Is subtraction suitable as a combiner in parallel reduction? **No**, because it is not associative.
12. What must the identity for addition be? **`0`**, never an arbitrary value like 10.
13. What is wrong with a combiner that only returns the left branch? **It drops the right branch's data**.
14. Why can two `double` sums differ slightly? **Grouping order and floating-point rounding**.
15. Why is `seq == parallel` insufficient to prove integer sums are right? **Both can overflow identically**.
16. When should `BigDecimal` replace `double`? **When exact decimal results are required by business rules**.
17. Is `peek` a reliable way to count processed elements? **No**, pipelines may optimize away calls.
18. Are tests asserting thread names or worker counts portable across JDKs? **No**.
19. With `Files.lines`, what must you do when comparing two execution modes? **Open two separate Streams, read the same snapshot, and close each source**.
20. Do correctness tests and performance tests share the same goal? **No**; verify correctness before measuring speed.
21. What should you do for a parallel-only bug? **Freeze input/seed, shrink the case, inspect state/combiner/order, and save a reproducible fixture**.
22. What is the strongest evidence when comparing outputs? **The semantic output contract paired with an independent expected-value oracle**.

**Rule of thumb:** Comparing sequential and parallel execution does not mean diffing two log streams or `toString()` outputs. **Freeze the data**, open **two fresh Streams**, define the **output semantics**, and verify every factor governing correctness: pure lambdas, unshared state, valid identity/associativity/combiners, ordering requirements, floating-point tolerances, overflow bounds, and I/O resource lifecycles. Even when sequential and parallel agree **per contract**, keep an independent oracle so both cannot fail identically—and only then benchmark whether parallelism actually pays off.
