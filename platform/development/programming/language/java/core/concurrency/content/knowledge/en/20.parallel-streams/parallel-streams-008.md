# Parallel Streams: Combiner, identity, and reduction bugs in parallel execution

## 1. The problem: why can the same `reduce` produce different results when run in parallel?

A **reduction** transforms multiple stream elements into a single result: a sum, maximum value, statistics, or an aggregated data structure. With a sequential stream, it is easy to picture an accumulator variable running from left to right:

~~~text
Stream:      [2, 4, 6, 8]
identity:     0
accumulate:  0 → 2 → 6 → 12 → 20
result:      20
~~~

However, `parallelStream()` can split data into multiple parts, process each part separately, and then **merge the intermediate results**. That merging concept is the **combiner**. Every part can be initialized with the **identity** (neutral element).

~~~text
Stream:           [2, 4]             [6, 8]
                     │                  │
identity = 0      0+2+4 = 6        0+6+8 = 14
                     └───── combiner ────┘
                                6+14
                                 │
                                20
~~~

The diagram above is **one partitioning example for illustration**, not a guarantee of the number of groups, thread ordering, group sizes, or actual partitioning strategy. Java reserves the right to change these implementation decisions. If the computation satisfies the `reduce` contract, the result does not depend on how it is split and merged; if it violates the contract, parallel execution can expose bugs that sequential execution did not reveal.

**Three questions that determine correctness:**

1. **Is the identity truly neutral?** When combined with any result, it must leave that result unchanged.
2. **Is the combiner associative across different groupings?** Changing the parenthesization must not change the intended mathematical result.
3. **Are the accumulator and combiner compatible?** Folding an element into an intermediate result must match creating a partial result from the element and then combining.

This article is about **the Java Stream API and Java concurrency in general**. The rules apply whenever a stream runs across multiple threads, regardless of framework.

## 2. The three `Stream.reduce` overloads and the role of the combiner

### 2.1. `reduce(BinaryOperator<T>)` — no identity declared

~~~java
Optional<Integer> max = Stream.of(2, 4, 6, 8)
        .parallel()
        .reduce(Integer::max);
~~~

Each element can serve as the initial result of a group. Because the stream may be empty and no identity is supplied by the caller, the return type is `Optional<T>`: empty if the stream is empty. The binary operator must still be **associative** and stateless/non-interfering to allow safe regrouping. With `Integer::max`, `max(max(a,b),c) == max(a,max(b,c))`, so grouping is safe.

Do not call `Optional.get()` unconditionally if the stream might be empty; use `orElseThrow()` when data is required to be present, or `orElse(...)` for a valid fallback.

### 2.2. `reduce(identity, BinaryOperator<T>)` — one operator for accumulation and combining

~~~java
int sum = Stream.of(2, 4, 6, 8)
        .parallel()
        .reduce(0, Integer::sum);
~~~

`0` is the identity for addition; `Integer::sum` both accumulates within each group and combines groups. The result type is `T` (not `Optional<T>`). If the stream is empty, it returns the identity `0`.

Requirements for this overload:

- `accumulator` is a two-argument function of the same type `T` returning `T`, such as addition.
- It must be **associative**, independent of parenthesization: `op(op(a,b),c) == op(a,op(b,c))`.
- `identity` must be a **two-sided** neutral element: `op(identity,x) == x` and `op(x,identity) == x`.
- The function must be **non-interfering** and **stateless**: it must not modify the stream source and must not rely on mutable state that changes across invocations.

Do not think of the identity as an "initial value applied **once for the entire reduction**". During parallel execution, different parts may each start from the identity. Choosing `10` for addition because you want to "add 10 once" violates the contract.

### 2.3. `reduce(identity, accumulator, combiner)` — different input and result types

General signature:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

Where:

- `T` is the type of the **stream elements**.
- `U` is the type of the **accumulated result**; it may differ from `T`.
- `identity` is the initial empty result value of type `U`.
- `accumulator` takes a `U` and an element `T`, returning a `U` after folding in the element.
- `combiner` merges **two `U` results** coming from different branches.

Example counting the total number of characters across strings:

~~~java
int length = Stream.of("a", "bb", "ccc")
        .parallel()
        .reduce(
                0,                                // U = Integer, identity
                (total, text) -> total + text.length(),  // (U, T) -> U
                Integer::sum);                    // (U, U) -> U
~~~

The result is `6`. A combiner is essential when `T = String` but `U = Integer`; a single same-type `BinaryOperator` cannot perform both roles.

**Special requirements of the three-argument overload** mandated by the Java Stream API:

- The combiner must be associative.
- The identity must be neutral for the combiner: `combiner(identity, u) == u` (and in practice, the merge must preserve neutrality on the appropriate side for every result).
- **Compatibility law:**  
  `combiner(u, accumulator(identity, t)) == accumulator(u, t)`  
  for every valid intermediate result `u` and element `t`.
- The accumulator and combiner must be non-interfering and stateless. A function that returns a mutable object while mutating a shared object across branches violates the semantics of reduction.

The compatibility law states that "adding `t` to an existing result" must be equivalent to "accumulating `t` starting from the identity and then combining that result". This requirement is often overlooked when a developer writes a correct accumulator but a combiner with different semantics.

## 3. Identity is not an arbitrary starting value

The identity is the **neutral element** of the combining operation, not a parameter for adjusting the total.

| Operation | Valid identity | Explanation |
|---|---|---|
| Integer addition (ignoring overflow) | `0` | `0 + x = x = x + 0` |
| Integer multiplication (ignoring overflow) | `1` | `1 × x = x = x × 1` |
| String concatenation with `String::concat` | `""` | Empty string adds no characters |
| Set union | Empty set | Union with the empty set leaves the set unchanged |
| Maximum of any `int` | `Integer.MIN_VALUE` | `max(MIN_VALUE, x) = x` |
| Minimum of any `int` | `Integer.MAX_VALUE` | `min(MAX_VALUE, x) = x` |

When the data is known to be non-empty, `reduce(Integer::max)` returning an `Optional` usually expresses intent more clearly than an artificial identity for `max`. For `double` with `NaN`, `±0.0`, or a specialized domain, check the specific semantics of the operator rather than applying the table above mechanically.

### Wrong example: `reduce(10, Integer::sum)` to add a "surcharge of 10"

If the data is `[1, 2, 3, 4]`, sequential execution yields:

~~~text
10 + 1 + 2 + 3 + 4 = 20
~~~

Suppose, **purely for illustration**, that the parallel stream is split into two groups, each starting from identity `10`:

~~~text
Group A: 10 + 1 + 2 = 13
Group B: 10 + 3 + 4 = 17
Combine: 13 + 17 = 30
~~~

`10` is not the identity of addition, so the result depends on how many parts the stream is partitioned into. The exact number of groups and resulting number at runtime are **not guaranteed by the API**. Do not write a unit test asserting "parallel always produces 30" for this example; `30` is only the hypothetical outcome of the two-group split shown above.

The right way to add the surcharge **once**:

~~~java
int total = 10 + numbers.parallelStream().reduce(0, Integer::sum);
~~~

`numbers` is a `Collection<Integer>` defined in the application. After `reduce(0, sum)`, adding `10` happens outside the reduction exactly once. For integer streams, you can also use `mapToInt(Integer::intValue).sum()` and then add the surcharge.

### A mutable object as identity: an even more dangerous trap

**Incorrect code, for analysis only — do not run**:

~~~java
List<String> identity = new ArrayList<>();

List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                identity,
                (list, item) -> {
                    list.add(item);
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
~~~

The problem: `identity` is **the exact same `ArrayList` object** passed to all branches; the `accumulator` mutates that object via `add`, and the combiner mutates it further via `addAll`. The identity is no longer immutable/neutral as required; branches can concurrently modify the same list, causing data races, duplicated elements, wrong counts, or runtime errors. **Do not "fix" this by replacing `ArrayList` with a synchronized list** and treating the reduction as valid: locking may prevent some races, but it does not fix using a single shared object as the identity across branches and merging it with itself.

To collect into a list, use **mutable reduction `collect`** (Section 7), which provides a `supplier` to create a separate container for each branch.

## 4. A combiner merges partial results, not a "placeholder" function

In the following three-argument reduction, the accumulator and combiner share the exact same semantics:

~~~java
record Stats(long count, long total) {
    Stats add(int value) {
        return new Stats(count + 1, total + value);
    }
    Stats merge(Stats other) {
        return new Stats(count + other.count, total + other.total);
    }
}

Stats stats = values.parallelStream().reduce(
        new Stats(0, 0), // identity
        Stats::add,      // accumulator (Stats, Integer) -> Stats
        Stats::merge);   // combiner    (Stats, Stats) -> Stats
~~~

This is an **in-class snippet** where `values` must be a `Collection<Integer>`; the standalone program in Section 6 has full declarations and runnable code. `Stats` is an **immutable** record: every `add` and `merge` creates a new object, so no mutable accumulator is shared. The combiner sums counts and totals, preserving the result structure.

For example, with `[2,4,6,8]`, two groups can aggregate into:

~~~text
Group A: Stats(count=2, total=6)
Group B: Stats(count=2, total=14)

merge(A, B) = Stats(count=4, total=20)
average = 20.0 / 4 = 5.0
~~~

To compute the average correctly, you must merge **count and total** first and divide only at the end. The average of two averages is not always equal to the overall average, because group sizes can differ:

~~~text
Group A: [1]          average = 1, size = 1
Group B: [5, 9, 13]   average = 9, size = 3
Wrong:   (1 + 9) / 2 = 5
Correct: (1 + 5 + 9 + 13) / 4 = 7
~~~

Instead of storing each group's average and combining by taking their arithmetic mean, carry `sum` and `count` and compute the average at the end.

### Wrong combiner: "return only the left branch"

~~~java
// WRONG — discards the entire result of the right branch
(left, right) -> left
~~~

This code might accidentally produce the expected result in a simple sequential case if the combiner is rarely or never called. In parallel, branch results can be lost; it violates the compatibility law.

### Wrong combiner: using subtraction to merge

~~~java
// WRONG — subtraction is not associative
(left, right) -> left - right
~~~

Because `(8 - 3) - 1 = 4` whereas `8 - (3 - 1) = 6`, changing the grouping changes the result. Merely "preserving element order" does not rescue a reduction with different groupings. A `Stream` with encounter order is still allowed to regroup during parallel reduction.

### Valid combiner, incompatible accumulator

Even when `combiner = Integer::sum` is associative, `accumulator` must produce results compatible with it. The following example is **incompatible**:

~~~java
// WRONG: accumulator multiplies by 2 on each step, while combiner adds.
.reduce(0, (total, n) -> total * 2 + n, Integer::sum)
~~~

Adding `n` to a partial sum `u` gives `2u+n`; whereas computing `accumulator(0,n)=n` and combining with `u` using `sum` gives `u+n`. The two sides differ whenever `u != 0`. This code may run sequentially, but it is not a valid three-argument reduction for parallel execution.

## 5. Associativity vs. commutativity and encounter order

**Associative** means changing parenthesization preserves the result:

~~~text
(a ◦ b) ◦ c = a ◦ (b ◦ c)
~~~

**Commutative** means swapping operands preserves the result:

~~~text
a ◦ b = b ◦ a
~~~

String concatenation is **associative but not commutative**: `("a"+"b")+"c" == "a"+("b"+"c") == "abc"`, yet `"a"+"b" != "b"+"a"`. An operation suitable for reducing an ordered stream does not have to be commutative in every case; correctness also depends on the encounter-order preservation contract of the reduction and the stream source. Do not use `unordered()` or a concurrent collector with `UNORDERED` if order is part of the result's meaning.

For example, `[a,b,c]` concatenated as strings produces `"abc"` under any valid order-preserving grouping. In contrast, a parallel `forEach` appending to a shared `StringBuilder` has no ordering guarantee and is not thread-safe; that is not a valid reduction.

**Floating-point numbers:** mathematically addition is associative, but IEEE 754 precision limits can cause different parenthesizations to produce different results:

~~~text
(1e16 + (-1e16)) + 1.0 = 1.0
1e16 + ((-1e16) + 1.0) = 0.0
~~~

Therefore, a `double` sum computed in parallel and sequentially can differ by a few bits, even when using addition, and must not be compared with `==` when the contract allows rounding tolerance. For business logic requiring decimal precision, consider `BigDecimal` with a well-defined rounding/scale strategy, or design a numerically stable aggregation per domain requirements. With `BigDecimal`, also watch out for `MathContext` and rounding, which can break associativity.

**Integer overflow:** `int`/`long` use two's-complement wraparound addition; if business logic requires exact sums over large ranges, `Integer::sum` may be unsuitable even though modular addition remains associative. Use a sufficiently wide type, `BigInteger`, or overflow checks depending on requirements. Do not equate "same result modulo $2^n$" with "correct business value".

## 6. Standalone Java 17+ example with deterministic output

Create **`ReductionDemo.java`**:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Stream;

public class ReductionDemo {
    record Stats(long count, long total) {
        Stats add(int n) {
            return new Stats(count + 1, total + n);
        }
        Stats merge(Stats other) {
            return new Stats(count + other.count, total + other.total);
        }
    }

    public static void main(String[] args) {
        List<Integer> values = List.of(2, 4, 6, 8);

        int sum = values.parallelStream().reduce(0, Integer::sum);
        System.out.println("sum=" + sum);

        Stats stats = values.parallelStream().reduce(
                new Stats(0, 0),
                Stats::add,
                Stats::merge);
        System.out.println("stats=" + stats.count() + "/" + stats.total());

        int length = Stream.of("a", "bb", "ccc")
                .parallel()
                .reduce(0, (n, s) -> n + s.length(), Integer::sum);
        System.out.println("length=" + length);

        int max = values.parallelStream().reduce(Integer::max).orElseThrow();
        System.out.println("max=" + max);

        List<Integer> collected = values.parallelStream().collect(
                ArrayList::new, ArrayList::add, ArrayList::addAll);
        System.out.println("collected=" + collected.size());

        boolean identityTen = 10 + 5 == 5 && 5 + 10 == 5;
        System.out.println("identityTen=" + identityTen);

        boolean subtractionAssociative = (8 - 3) - 1 == 8 - (3 - 1);
        System.out.println("subtractionAssociative=" + subtractionAssociative);

        double left = (1e16 + -1e16) + 1.0;
        double right = 1e16 + (-1e16 + 1.0);
        System.out.println("floatingGroupingEqual=" + (left == right));
    }
}
~~~

Compile and run with JDK 17 or later:

~~~bash
javac -encoding UTF-8 ReductionDemo.java
java ReductionDemo
~~~

**stdout:**

~~~text
sum=20
stats=4/20
length=6
max=8
collected=4
identityTen=false
subtractionAssociative=false
floatingGroupingEqual=false
~~~

Explanation:

1. `reduce(0, Integer::sum)`: identity `0` is valid, integer addition is associative within modular arithmetic, yielding `20`.
2. `Stats::add` maps `Integer` into a structure with count and total; `Stats::merge` is an associative combiner. Result `count=4`, `total=20`; average is `20/4 = 5`.
3. `length` uses the three-argument overload, distinguishing `T=String` and `U=Integer`; result `1+2+3 = 6`.
4. `reduce(Integer::max)` needs no identity, returns an `Optional`, and extracts the maximum value `8`.
5. `collect(ArrayList::new, ArrayList::add, ArrayList::addAll)` allocates separate mutable containers and then merges them; there are exactly four elements. The program prints only the size, independent of internal work splitting.
6. The last three lines verify the laws: `10` is not neutral for addition; subtraction is not associative; `double` addition can be affected by parenthesization.

The example **does not attempt to print the actual output of a broken reduction on a parallel stream** because that output can vary with implementation and partitioning. Instead, it tests the required laws directly — a more reliable testing approach when teaching correctness.

## 7. When to use `collect` instead of `reduce`?

**Reduce** is natural for aggregating with **immutable** values: integers, `BigInteger`, a new `Stats` record per step, or any value with a clear associative operation. **Collect** is designed for accumulating into **mutable containers** created independently per branch.

With the three-function overload:

~~~java
List<String> result = names.parallelStream().collect(
        ArrayList::new,  // supplier: creates a new container when needed
        ArrayList::add,  // accumulator: adds a name to the branch's container
        ArrayList::addAll // combiner: merges another branch's container
);
~~~

`names` is an application `Collection<String>`; this is an illustrative snippet, not standalone. Structure:

- **Supplier:** allocates a new collection so tasks have separate accumulators.
- **Accumulator:** updates the local container.
- **Combiner:** merges containers when joining branches.
- **No concurrent mutation of a shared `ArrayList` across threads:** proper collection preserves boundaries between intermediate containers.

This is not a guarantee that every custom `Collector` is thread-safe; a `CONCURRENT` collector may allow multiple threads to contribute to a single shared container, in which case both the accumulator and container must actually support concurrent access. `Collector.Characteristics.UNORDERED` indicates that result order does not matter to the collector; `CONCURRENT` is a separate characteristic and must not be attached to a collector that does not satisfy it.

When a custom algorithm is unnecessary, prefer built-in terminal operations or collectors:

~~~java
// Illustrative snippets when numbers is a Stream<Integer>.
long count = numbers.count();

// When source is a Collection<Integer>, create a new stream per terminal operation:
int sum = source.parallelStream().mapToInt(Integer::intValue).sum();

IntSummaryStatistics summary = source.parallelStream()
        .mapToInt(Integer::intValue)
        .summaryStatistics();

List<Integer> list = source.parallelStream().toList();
~~~

`source` is an existing `Collection<Integer>`, and `import java.util.IntSummaryStatistics;` is required. `Stream.toList()` (Java 16+) returns an **unmodifiable** list, unlike collecting into an `ArrayList` with `collect`. A stream can only be used for **one terminal operation**: do not call `count()` and then `sum()` on the same consumed stream.

If combining data incurs heavy allocation, primitive streams (`IntStream`, `LongStream`, `DoubleStream`) and optimized collectors can outperform creating a new immutable record per element. Choose based on profiling, not just shorter syntax.

### Avoid mutating an external variable during reduction

~~~java
// WRONG: writes to a mutable variable outside the stream, race condition in parallel.
int[] sum = {0};
values.parallelStream().forEach(n -> sum[0] += n);
~~~

Even if `values` is an immutable list, `sum[0]` is still shared mutable state. The `+=` operation is not atomic, so updates can be lost. Standard solution:

~~~java
int sum = values.parallelStream().mapToInt(Integer::intValue).sum();
~~~

Do not use side effects just to "produce a result"; reduction expresses aggregation intent more clearly and lets the runtime coordinate execution.

## 8. Parallel reduction bugs: symptoms, causes, and fixes

| Symptom | Common cause | Fix |
|---|---|---|
| Different results between sequential and parallel | Wrong identity or non-associative/incompatible operations | Verify the three laws: identity, associativity, compatibility |
| Duplicated/lost data or `ArrayList` corruption | Mutating a single shared identity object in `reduce` | Use `collect` with a supplier that creates separate containers |
| Result missing data from some branches | Combiner ignores a branch, e.g., `(a,b)->a` | Write a combiner that merges all branches with matching semantics |
| Count and sum are right, but average is wrong | Averaging averages without weighting by group size | Merge `(sum,count)` first, then compute the average |
| Floating-point results differ slightly | Rounding and grouping changes | Use comparison with tolerance or an appropriate numerical algorithm |
| Non-deterministic / random-looking results | Callback uses external mutable state, random/time/I/O side effects | Use stateless, pure data functions; isolate side effects |
| Sequential is fine, parallel is much slower | Task too small, high splitting/combining cost, boxing, contention | Benchmark with realistic data, use primitive streams, reduce allocation |
| Unexpected failure from mapper/accumulator | Function throws an exception in a task; surfaced at terminal operation | Inspect the root cause; do not treat reduction as swallowing errors |
| Empty stream returns unexpected value | Identity is returned by contract, or `Optional.empty` | Define explicit semantics for empty input |
| Cannot reuse stream | Terminal operation already consumed the pipeline | Create a fresh stream from the source before each reduction |

### Exceptions during parallel execution

If an accumulator/combiner lambda throws an exception, the terminal operation may complete exceptionally with that exception (or an internally wrapped exception). Other tasks may have already started; do not rely on "everything stops immediately" or on a specific exception order when multiple tasks fail.

In particular, parallel reduction is **not transactional**: if a lambda calls an external API, writes a file, or updates a database, a failure in one branch does not roll back side effects in other branches. Reduction lambdas should therefore be pure data transformations, while side effects should be handled in a layer with explicit contracts.

### `null` results and sources containing `null`

`Stream.reduce(BinaryOperator)` returns an `Optional` and does not accept a `null` final result as a valid `Optional` element; operations or mappers assuming non-null may throw `NullPointerException`. For streams containing `null`, first decide the domain rule: filter with `Objects::nonNull`, map to a valid sentinel value, or fail fast. Do not pass `null` as the identity and assume it is neutral for every operator.

## 9. Verifying the laws before enabling parallel

Try a **runtime-independent partitioning model**. For `[a,b,c,d]`, write checks for:

~~~text
Sequential reduce: fold(identity, [a,b,c,d])
2-way split:       combine(fold(identity,[a,b]), fold(identity,[c,d]))
3-way split:       combine(combine(fold(identity,[a]), fold(identity,[b,c])), fold(identity,[d]))
Empty input:       identity
~~~

If the results differ, fix the laws before running benchmarks. For ordered string concatenation, also verify grouping order; for floating-point numbers, define an acceptable error tolerance.

Example law checks in Java pseudocode:

~~~java
// Not a standalone program; op is BinaryOperator<T>,
// identity and a,b,c are sample values of the same type T.
boolean leftIdentity = op.apply(identity, a).equals(a);
boolean rightIdentity = op.apply(a, identity).equals(a);
boolean associative = op.apply(op.apply(a, b), c)
        .equals(op.apply(a, op.apply(b, c)));
~~~

When results can be `null`, use `Objects.equals(...)` to avoid NPEs during testing. Testing a few datasets only finds counterexamples; it **does not prove** the laws hold for all values. Property-based/randomized inputs, varying group sizes, and edge cases (empty, single element, extreme values, duplicates, `null` if permitted) are far more valuable than running `parallelStream()` once and seeing it "look right".

For the three-argument overload, also check:

~~~java
// Pseudocode; will not run without u, t, identity,
// accumulator, and combiner.
U left = combiner.apply(u, accumulator.apply(identity, t));
U right = accumulator.apply(u, t);
boolean compatible = Objects.equals(left, right);
~~~

Some types `U` have equivalence semantics different from `equals`; when testing, define the exact equivalence criterion for the business result.

### Workflow for investigating a real parallel bug

1. Create a small, fixed input; run sequentially to understand the expected result.
2. Write out the identity, accumulator, and combiner as three separate functions/expressions.
3. Check two-sided identity, associativity, compatibility, statelessness, and shared data.
4. Trace a few different partitionings by hand; verify the result does not change.
5. Run in parallel multiple times, testing empty input, duplicate elements, and varying sizes; treat those runs only as supporting evidence.
6. If mutable accumulation is involved, switch to `collect` or design an immutable result.
7. Benchmark with representative data, accounting for splitting overhead, boxing, combining, and resource contention.

### Parallel is not automatically faster

`parallelStream()` typically leverages the JVM's Fork/Join framework; pool usage and scheduling depend on the execution context. For small streams, the overhead of splitting work, creating tasks, and merging results can exceed the computation itself. With `reduce` creating many immutable objects, allocation/GC overhead can also be significant. When the source does not split well, parallel processing can be inefficient.

Do not use `parallel()` to "fix" a slow loop before measuring. A reduction must first be **algebraically sound**, and only then evaluated for parallel speedup.

## 10. Choosing the right tool for each requirement

| Requirement | Typical Java approach |
|---|---|
| Simple `int`/`long` sum | Primitive stream `sum()` or `reduce(0, sum)` with proper identity |
| Finding max/min when input may be empty | `reduce(Integer::max)` or primitive `max()` returning `Optional` |
| Aggregating multiple statistics | `summaryStatistics()` or immutable record `(count,sum,...)` with combiner |
| Counting characters from `Stream<String>` into `Integer` | `reduce(0, accumulator, Integer::sum)` |
| Collecting into a mutable list/set/map | `collect(...)` or `Collectors.toList()/toSet()/toMap()` |
| Joining large strings | `Collectors.joining()` is usually better than repeated `String::concat` |
| Result requires specific ordering | Keep an ordered stream and a collector with a matching contract |
| Need side effects per element | Define explicit synchronization and lifecycle; avoid shared mutation in `reduce` |

**Self-check questions:**

- Why is `reduce(10, Integer::sum)` wrong when you want to add 10 exactly once? Because `10` can serve as the identity for **multiple** branches; the identity for addition must be `0`.
- Why is `(a,b)->a-b` unsuitable for parallel reduction? Because subtraction is not associative; different groupings produce different results.
- If an accumulator collects data into an `ArrayList` and mutates it, should you pass a shared identity object to `reduce`? No. Use `collect` with a supplier that creates separate containers.
- Can `combiner` be ignored because test data has only one element? No. It must be valid for all legal partitionings.
- Why can't averages be combined by averaging the averages? Because group sizes can differ; you must combine totals and counts.
- `String::concat` is not commutative, so can it be used when reducing an ordered stream? Yes, if the merge preserves encounter order; concatenation is associative, and order must be preserved per the contract.
- Why can a parallel sum of `double` differ from a sequential sum? Because precision limits and rounding mean floating-point addition is not strictly associative in practice.

## 11. Standard Java references

- [Java 21 Stream API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Stream.html) — contract for the three `reduce` overloads, associativity, identity, compatibility, and stateless/non-interfering requirements.
- [Java 21 package java.util.stream](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/package-summary.html) — reduction principles, mutable reduction, parallelization, and side effects.
- [Java 21 Collector API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collector.html) — supplier, accumulator, combiner, and characteristics.
- [Java 21 Collectors API](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/util/stream/Collectors.html) — standard collectors, joining, grouping, and statistics.

A correct parallel reduction must not rely on the JVM happening to execute in the order observed in a single test run. **A neutral identity + an associative combiner + a compatible accumulator/combiner + no improper shared mutable state** is the foundation for ensuring the same computation has the same meaning sequentially and in parallel.
