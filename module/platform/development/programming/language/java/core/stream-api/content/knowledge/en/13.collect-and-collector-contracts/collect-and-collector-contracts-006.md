# Identity, Associativity, and Equivalence Contracts of Collector

In the Java Stream API, `collect(Collector)` is a *terminal operation* used to **accumulate Stream elements into a result**. It can collect into a `List`, `Set`, `Map`, statistics, string, or a custom aggregated object. However, a custom `Collector` is only correct when it obeys the **identity contract**, **associativity contract**, and **equivalence contract**. These three concepts are especially important when a Stream is processed in parallel, because the runtime is entitled to partition data into parts and then combine partial results.

This lesson belongs to the **Collect Mechanism and Collector** chapter of the **JAVA_STREAM_API** module. The goal is to deeply understand the contracts required before writing a custom collector, using `groupingBy` with downstream collectors, or evaluating results on a parallel stream. This knowledge connects to lazy pipelines, `filter`, `map`, `reduce`, `collect`, `Spliterator`, and algorithmic limits involving state, resources, and performance requirements.

## 1. What parts make up a Collector?

The generic interface is `java.util.stream.Collector<T, A, R>`, with:

- **`T`**: the input element type of the Stream.
- **`A`**: the *mutable accumulation type*.
- **`R`**: the return result type after collection completes.

A collector describes five components:

| Component | Functional type | Responsibility |
|---|---|---|
| `supplier()` | `Supplier<A>` | Creates a new accumulator in an empty state |
| `accumulator()` | `BiConsumer<A, T>` | Incorporates one input element into the accumulator |
| `combiner()` | `BinaryOperator<A>` | Merges two intermediate accumulators |
| `finisher()` | `Function<A, R>` | Converts the accumulator into the result |
| `characteristics()` | `Set<Characteristics>` | Declares properties such as `UNORDERED`, `CONCURRENT`, `IDENTITY_FINISH` |

For example, a list-creating collector can:

1. Create an empty `ArrayList` via the supplier.
2. Add each element to a branch's list via the accumulator.
3. Concatenate lists from branches via the combiner.
4. Return the accumulated list itself as the result (no further conversion needed).

With a sequential Stream, you might observe only one accumulator and never see the combiner called. On a parallel stream, the library has the right to create multiple accumulators, split elements, and merge them back. **A valid collector must produce equivalent results across all contract-compliant partitionings**, regardless of whether a small example invokes the combiner or not.

```text
                     Stream<T>
                         |
                    partitioning
                /         |         \
           supplier   supplier    supplier
                |         |         |
          accumulator accumulator accumulator
                |         |         |
                A1        A2        A3
                \         /         |
                 combiner           |
                     \             /
                       combiner
                          |
                          A
                          |
                       finisher
                          |
                          R
```

The diagram illustrates **one possible execution**, without mandating the exact order or call counts of every implementation. For a collector with the `CONCURRENT` characteristic, the library may even let multiple workers accumulate concurrently into the same container when conditions are met.

## 2. Identity contract: merging with an empty container does not change meaning

Suppose `a` is a valid accumulator already holding some elements and `e = supplier.get()` is **a fresh accumulator in the empty state**. The identity contract requires:

```text
combiner(a, e)  ≈  a
```

The `≈` symbol denotes **equivalence in result**, not necessarily the exact same object reference. The combiner may mutate `a` and return it, or create another accumulator, as long as the final result carries the same meaning.

Example with a list:

```java
List<String> left = new ArrayList<>(Arrays.asList("A", "B"));
List<String> empty = new ArrayList<>();

left.addAll(empty);
System.out.println(left); // [A, B]
```

Appending an empty list does not alter the elements. A collector whose supplier creates an empty list and whose combiner concatenates lists like this has a **valid identity element**.

### 2.1. Collector's identity differs from Stream.reduce's identity

In `stream.reduce(0, Integer::sum)`, `0` is **the initial value of addition**. In `Collector`, the "identity" is typically **the empty accumulation state created by the supplier**:

| Aggregation | Suitable identity |
|---|---|
| `reduce(0, Integer::sum)` | The number `0` |
| List-joining collector | Empty list `[]` |
| Set-joining collector | Empty set |
| String-joining collector | Empty string buffer |
| Counting and summing collector | State `count = 0`, `sum = 0` |

Do not assume the supplier **always** returns `null` or **always** returns `0`. It must return a valid fresh container whose state is treated as an identity by the combiner.

### 2.2. Example violating the identity contract

```java
// WRONG: combiner appends -1 even when the right branch is empty.
Collector<Integer, List<Integer>, List<Integer>> wrong =
        Collector.of(
                ArrayList::new,
                (list, number) -> list.add(number),
                (left, right) -> {
                    left.addAll(right);
                    left.add(-1);
                    return left;
                });
```

If `left = [10, 20]` and `right = []`, the combiner returns `[10, 20, -1]`, which is no longer equivalent to `[10, 20]`. This collector can produce different results depending on how the Stream is split, even for identical input data.

The identity contract emphasizes **the result after merging**, not merely that the supplier successfully constructs an object.

## 3. Associativity contract: splitting data differently still gives equivalent results

The *associativity* contract is stronger than "the combiner can merge two containers". It requires that **putting elements into one container sequentially** and **splitting across multiple containers and merging** must produce equivalent final results.

Suppose a Stream contains two elements `t1`, `t2` in encounter order:

**Approach A — sequential accumulation**

```text
a = supplier()
accumulator(a, t1)
accumulator(a, t2)
resultA = finisher(a)
```

**Approach B — split into two branches and combine**

```text
left  = supplier()
right = supplier()
accumulator(left,  t1)
accumulator(right, t2)
merged  = combiner(left, right)
resultB = finisher(merged)
```

Requirement:

```text
resultA  ≈  resultB
```

A valid merge must continue to preserve this property if data is split into three, four, or more parts, with merges grouped differently. For an **ordered** collector, merging must preserve the relative order of segments according to encounter order.

### 3.1. Correct example: concatenating lists in order

```java
Collector<Integer, List<Integer>, List<Integer>> toOrderedList =
        Collector.of(
                ArrayList::new,
                (list, value) -> list.add(value),
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });

List<Integer> collected = Stream.of(1, 2, 3, 4)
        .parallel()
        .collect(toOrderedList);

System.out.println(collected); // [1, 2, 3, 4]
```

With a source that has an encounter order and a collector that does not declare `UNORDERED`, the result must preserve the source order. List concatenation in **left-then-right** direction is associative with respect to content:

```text
([1] ++ [2]) ++ [3,4] = [1,2,3,4]
[1] ++ ([2] ++ [3,4]) = [1,2,3,4]
```

Here `++` denotes list concatenation. It is **not commutative**: `[1] ++ [2]` differs from `[2] ++ [1]`. An ordered collector **does not need a commutative merge**; it only needs results consistent with encounter order regardless of how chunks are grouped.

### 3.2. Wrong example: combiner drops one branch

```java
Collector<Integer, List<Integer>, List<Integer>> dropRight =
        Collector.of(
                ArrayList::new,
                (list, value) -> list.add(value),
                (left, right) -> left); // WRONG: drops all elements of right.
```

Accumulating `1` then `2` sequentially yields `[1, 2]`, yet if one branch holds `[1]` and another holds `[2]`, `combiner([1], [2])` leaves only `[1]`. Thus it **fails the associativity contract**, even if tests on a small sequential Stream happen to pass.

### 3.3. Common mistake: merging group averages by averaging again

Suppose we want the average of `[10, 20, 30]`. If split into `[10]` and `[20, 30]`, the group averages are `10` and `25`. Taking the average of those two numbers:

```text
(10 + 25) / 2 = 17.5    // WRONG, because the two groups have different sizes.
(10 + 20 + 30) / 3 = 20 // CORRECT.
```

You cannot merge two **individual averages** into an overall average without **the element count of each group**. The right design stores both sum and count:

```text
left:   sum = 10, count = 1
right:  sum = 50, count = 2
merge:  sum = 60, count = 3
finish: 60 / 3 = 20
```

This is why `A` (intermediate accumulation state) can differ from `R` (final result). A `Collector` is meant to retain the extra information needed so branches combine accurately.

## 4. Equivalence: to what degree must results match?

Two executions do not have to produce **the same object in memory**. What is required is that they produce results **equivalent under the collector's semantics**. Equivalence is evaluated on the result after the finishing step, i.e., `finisher`, not by comparing the memory addresses of two containers.

For a collector **not declaring `UNORDERED`**, two final results are generally considered equivalent under `equals` in the Collector contract, because element order may carry business meaning. For example:

```java
List<Integer> a = Arrays.asList(1, 2, 3);
List<Integer> b = Arrays.asList(1, 2, 3);
List<Integer> c = Arrays.asList(3, 2, 1);

System.out.println(a.equals(b)); // true
System.out.println(a.equals(c)); // false: List.equals checks order.
```

For a collector with the `UNORDERED` characteristic, equivalence is **relaxed with respect to order-only differences**: element encounter order does not contribute to the business result. For instance, a set of product codes is considered the same result if it contains the same elements, even if iteration order of the set differs.

| Collector/output | Result 1 | Result 2 | Equivalent? |
|---|---|---|---|
| Collector creating ordered `List` | `[A, B]` | `[A, B]` | Yes |
| Collector creating ordered `List` | `[A, B]` | `[B, A]` | No |
| Truly `UNORDERED` collector, result is a set | `{A, B}` | `{B, A}` | Yes, because elements match |
| Any valid collector | Sum equals `100` | Sum equals `90` | No |
| Any valid collector | Three valid elements | One element missing | No |

**Do not use `UNORDERED` to legitimize data loss or wrong calculations.** Order differences are the allowed exception; differences in element count, sum, or result members are still violations.

### 4.1. UNORDERED does not mean "random sorting"

`Characteristics.UNORDERED` means the collector **does not commit to preserving encounter order**. It does not require reversing order, shuffling data, or making results vary across runs.

If writing a collector to produce a list meant to preserve positions, such as a transaction report or paginated results, **do not declare `UNORDERED`** solely hoping for a speedup. Only declare it when order genuinely does not alter the result's meaning.

## 5. Complete Java 8 example: contract-compliant averaging Collector

The following example designs a collector to compute average order amount using an accumulator holding **sum** and **count**, then applies it on a sequential Stream, parallel Stream, empty source, and per group. Amounts use `long` in the smallest currency unit; the average returns `OptionalDouble` to distinguish an empty source. This example illustrates the contracts, assuming numbers are small enough not to overflow `long` and `double` precision error is acceptable.

```java
import java.util.Arrays;
import java.util.Collections;
import java.util.List;
import java.util.Map;
import java.util.OptionalDouble;
import java.util.stream.Collector;
import java.util.stream.Collectors;

public class CollectorContractsDemo {
    static final class Sale {
        private final String category;
        private final long amountCents;

        Sale(String category, long amountCents) {
            this.category = category;
            this.amountCents = amountCents;
        }

        String getCategory() {
            return category;
        }

        long getAmountCents() {
            return amountCents;
        }
    }

    static final class SumCount {
        private long sum;
        private long count;

        void add(Sale sale) {
            sum += sale.getAmountCents();
            count++;
        }

        SumCount combine(SumCount other) {
            sum += other.sum;
            count += other.count;
            return this;
        }

        OptionalDouble finish() {
            return count == 0
                    ? OptionalDouble.empty()
                    : OptionalDouble.of((double) sum / count);
        }
    }

    public static void main(String[] args) {
        Collector<Sale, SumCount, OptionalDouble> averageCollector =
                Collector.of(
                        SumCount::new,    // supplier
                        SumCount::add,    // accumulator
                        SumCount::combine,// combiner
                        SumCount::finish  // finisher
                );

        List<Sale> sales = Arrays.asList(
                new Sale("Sách", 10),
                new Sale("Sách", 20),
                new Sale("Sách", 30),
                new Sale("Phụ kiện", 40)
        );

        OptionalDouble sequential = sales.stream()
                .collect(averageCollector);
        OptionalDouble parallel = sales.parallelStream()
                .collect(averageCollector);
        OptionalDouble empty = Collections.<Sale>emptyList()
                .stream()
                .collect(averageCollector);

        System.out.println(sequential.orElse(-1)); // 25.0
        System.out.println(parallel.orElse(-1));   // 25.0
        System.out.println(empty.isPresent());    // false

        Map<String, OptionalDouble> byCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::getCategory,
                        averageCollector));

        System.out.println(byCategory.get("Sách").orElse(-1));
        // 20.0
        System.out.println(byCategory.get("Phụ kiện").orElse(-1));
        // 40.0
    }
}
```

**Why does this collector obey the contract?**

- **Identity:** `new SumCount()` has `sum = 0` and `count = 0`; `combine(a, empty)` preserves `a`'s pair of values unchanged.
- **Associativity:** merges pairs by **adding sum to sum, count to count**. Without `long` overflow, the final sum and count do not depend on how merges are parenthesized.
- **Equivalence:** `finish` computes `sum / count` when data exists, or returns `OptionalDouble.empty()` when empty; for the example data, different partitionings produce the same arithmetic result.
- **State isolation:** separate `SumCount` instances are created by the supplier; the collector **does not declare `CONCURRENT`**, so the runtime manages them under container isolation and safe merging rules.
- **Different state and result types:** `A = SumCount`, `R = OptionalDouble`; `IDENTITY_FINISH` is not declared.

Here `SumCount` is mutable during collection, yet never exposed to callers, and each accumulation instance belongs to the collect execution. When calculating money requiring high decimal precision, consider `BigDecimal` and a rounding policy in the finisher instead of `double`.

## 6. Verifying the contract by manually splitting input

To test a collector, you can construct two equivalent accumulation paths: **single-branch** and **multi-branch combined**. The standalone snippet below illustrates this with a valid list collector; it requires importing `java.util.ArrayList`, `java.util.Arrays`, `java.util.List`, and `java.util.stream.Collector`.

```java
Collector<Integer, List<Integer>, List<Integer>> collector =
        Collector.of(
                ArrayList::new,
                (list, number) -> list.add(number),
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });

// Accumulate three elements sequentially.
List<Integer> onePass = collector.supplier().get();
collector.accumulator().accept(onePass, 1);
collector.accumulator().accept(onePass, 2);
collector.accumulator().accept(onePass, 3);

// Split into two branches: [1, 2] and [3].
List<Integer> left = collector.supplier().get();
List<Integer> right = collector.supplier().get();
collector.accumulator().accept(left, 1);
collector.accumulator().accept(left, 2);
collector.accumulator().accept(right, 3);
List<Integer> combined = collector.combiner().apply(left, right);

System.out.println(onePass.equals(combined)); // true
// Both contain [1, 2, 3].

// Merge with a fresh empty container: identity contract.
List<Integer> withEmpty =
        collector.combiner().apply(combined, collector.supplier().get());
System.out.println(withEmpty.equals(onePass)); // true
```

This is a **representative** check, not a formal proof of the contract for all inputs and all splits. For thorough testing, also test empty sources, single elements, multiple split points, various ways of merging three or more branches, duplicate elements, and ordered sources.

If a collector does not have `IDENTITY_FINISH`, you must compare **results after `finisher`** when verifying equivalence. Do not just compare `A.equals(...)` if the intermediate state is an object that does not implement `equals` according to result semantics.

## 7. Characteristics can change how the runtime executes collect

`Collector.Characteristics` describes properties that an implementation may rely on to optimize. Declaring a characteristic **contrary to reality** can break a program on parallel streams even when sequential runs succeed.

### 7.1. IDENTITY_FINISH: A is R itself

`IDENTITY_FINISH` states that the finisher is essentially the identity function and may be skipped: accumulation state type `A` can be used directly as result `R`.

```java
Collector<String, List<String>, List<String>> listCollector =
        Collector.of(
                ArrayList::new,
                (list, value) -> list.add(value),
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
// This 3-component overload carries the IDENTITY_FINISH characteristic.
```

The averaging example in section 5 **must not** declare `IDENTITY_FINISH` because `SumCount` is not `OptionalDouble`. If declared wrongly, the implementation may skip the finisher and attempt to return the intermediate state as the final result, causing type errors or wrong results.

### 7.2. UNORDERED: result does not depend on encounter order

`UNORDERED` is appropriate when result meaning does not rely on order, such as collecting keys into a set. It can allow the library to drop ordering constraints during parallel reduction.

```java
java.util.Set<String> unique = Stream.of("B", "A", "B")
        .parallel()
        .collect(Collectors.toSet());
// Set contents: {"A", "B"}, no guarantee on iteration order.
```

`Collectors.toSet()` is an *unordered collector*. Conversely, a collector building a list to preserve transaction order **should not** be marked `UNORDERED`.

### 7.3. CONCURRENT: allows concurrent accumulation into the same container

`CONCURRENT` means `accumulator` **is permitted to be called concurrently** by multiple threads on the same container. This is a concurrency-safety commitment that the collector must genuinely satisfy.

Calling `parallelStream()` does not mean a collector needs `CONCURRENT`. If a collector is **not concurrent**, the framework can still split into separate containers, each handled by a branch, and then merge via the combiner. That mechanism does not require each `ArrayList` or `SumCount` to be a thread-safe object.

Normally, the framework only performs a **concurrent reduction** directly into a shared container when the collector has `CONCURRENT` **and** either the Stream has no encounter order **or** the collector also has `UNORDERED`. Therefore, these two characteristics cannot be added arbitrarily just to "enable parallel execution".

| Characteristics | What does it allow? | Risk if falsely declared |
|---|---|---|
| `IDENTITY_FINISH` | Skipping state-to-result conversion | Returns wrong type or drops mandatory finisher step |
| `UNORDERED` | Not preserving element encounter order in the result | List/report results get reordered |
| `CONCURRENT` | Multiple workers may use the same accumulator container concurrently | Race conditions, lost data, or corrupted structures |

**Wrong example:** declaring `CONCURRENT` on a collector using a plain `ArrayList` without synchronization or a concurrent data structure. When the runtime is permitted to call `list.add(...)` from multiple workers simultaneously, `ArrayList` provides no thread-safety guarantee.

## 8. Other accumulation lifecycle constraints

Beyond the three main contracts, how the runtime manages containers also matters:

1. `supplier` must provide fresh, valid accumulators usable independently. Do not use a `static` field holding a shared list so that every `supplier.get()` returns the same object.
2. `accumulator` should express how to add an element to the state, without modifying the data source, depending on a specific thread, or arbitrarily mutating another branch's container.
3. `combiner` must merge both states semantically and return a state usable going forward. In the common mutable pattern, mutating the left container and returning it is valid if no information is lost.
4. If the combiner or finisher **does not return the exact container passed in**, the collector implementation must not continue using the replaced container under lifecycle rules. Do not write logic expecting an old container to be called for accumulation again.
5. A container once passed to the combiner or finisher must not be fed back into the accumulator; thus counting `accumulator` invocations via global side effects is not a reliable measure of how the framework splits work.

These rules keep accumulation with **local mutable state** safe in parallel streams. They do not license the accumulator or combiner to mutate arbitrary mutable objects outside the pipeline.

## 9. Collector and reduce: similar in combination, different in state

`reduce` and `collect` are both reduction operations, but differ in state management:

| Criterion | `reduce` | `collect(Collector)` |
|---|---|---|
| Accumulation operation | Usually returns a new or existing value per operation | Can mutate intermediate container `A` |
| Accumulation object | Usually same type as result or three-parameter overload for different type | `A` can differ from `R` |
| Parallel organization | Must have valid, associative accumulator/combiner | Supplier creates separate containers; accumulator and combiner obey contract |
| Suitable examples | Sums, products, pure associative min/max | Lists, Maps, grouping, multi-metric statistics, custom collectors |
| What to avoid | Side effects or shared mutable identity | Supplier reusing a shared container, combiner dropping data, wrongly declared Characteristics |

For instance, joining large strings with `Collectors.joining()` is usually more suitable than `reduce(String::concat)` when reducing intermediate string allocations matters. Summing integers with `IntStream.sum()` is clearer than both when you only need addition.

**Note:** mathematical associativity does not guarantee **bit-identical** floating-point results across all merge orders, because `double` addition has rounding error. For money or statistics demanding high precision, choose the appropriate numeric type, summation algorithm, and rounding policy, rather than assuming a contract-compliant Collector guarantees absolute precision.

## 10. Distinguishing contract errors from business logic errors

| Symptom | Common cause | Remedy |
|---|---|---|
| Sequential run has all elements, parallel run loses some | Combiner drops one branch or supplier shares a mutable container | Merge both branches completely; supplier creates independent state |
| Same source yields wrong sum/count depending on split | Accumulator incompatible with combiner or numeric overflow | Design mergeable state, guard numeric range |
| Parallel average wrong when groups have different sizes | Merging branch averages without keeping count | Merge `(sum, count)` pairs, divide in finisher |
| Result list reordered though business logic needs order | Incorrectly marked `UNORDERED` | Keep encounter-order constraint, merge left then right |
| Result throws `ClassCastException` or skips type conversion | Marked `IDENTITY_FINISH` when `A` differs from `R` | Declare only when finisher is truly the identity |
| `ArrayList` corrupted during concurrent collection | Marked `CONCURRENT` on an unsafe container | Remove characteristic or use a genuinely concurrent design |
| Empty source returns an unreasonable value | Supplier does not create identity state or finisher has wrong empty policy | Explicitly design empty result and verify identity |
| Results differ solely due to `Set` iteration order | Business logic depended on an unguaranteed order | Sort explicitly or design order-independent results |

## 11. Self-check exercises with answers

### Exercise 1. Identity element of a summing collector

A collector uses state `SumCount(sum, count)`, and the accumulator increments `sum` and `count`. What state should the supplier return?

**Answer:** `sum = 0` and `count = 0`. Merging a populated state with this state preserves both the sum and the count unchanged.

### Exercise 2. Bug in the combiner

```java
(left, right) -> {
    left.addAll(right);
    left.add("END");
    return left;
}
```

**Question:** If `right` is empty, which contract is violated?

**Answer:** **Identity**, because `combiner(left, empty)` introduces an extra `"END"`. Furthermore, adding an element on every combine makes the result depend on merge count, violating the associativity contract.

### Exercise 3. Associative but not commutative

Concatenating `[A]` with `[B]` gives `[A, B]`, whereas swapping branches gives `[B, A]`. Can list concatenation serve as the combiner for an ordered collector?

**Answer:** **Yes**. List concatenation is associative even though it is not commutative. An ordered collector must merge segments in encounter order, without requiring arbitrary branch swapping.

### Exercise 4. Characteristics for an averaging collector

A collector has `A = SumCount` and `R = OptionalDouble`, using a finisher to divide `sum / count`. May `IDENTITY_FINISH` be declared?

**Answer:** **No**, because the intermediate state and final result have different types, and the finisher must run.

### Exercise 5. Average after splitting groups

Branch A contains `[10]`, branch B contains `[20, 30]`. Is merging branch averages by taking the average of `10` and `25` correct?

**Answer:** **Wrong**, giving `17.5`. You must merge `(sum=10, count=1)` and `(sum=50, count=2)` into `(sum=60, count=3)`; the right result is `20`.

### Exercise 6. Does parallel require CONCURRENT?

A collector uses a separate `ArrayList` on each partition, and the combiner merges lists with `addAll`. Do you need to declare `CONCURRENT` to use `parallelStream().collect(...)`?

**Answer:** **No**. The framework can accumulate on independent containers and combine them afterward. Only declare `CONCURRENT` when the design genuinely allows multiple workers to safely update one container simultaneously.

## 12. Checklist when designing a custom Collector

Before putting a collector into an application, check:

1. **Identity:** is the state created by `supplier` truly "empty", and does merging it into an accumulated result leave its meaning unchanged?
2. **Associativity:** do all valid input splits, accumulations, and merges lead to the same post-finisher result? Does the combiner preserve all elements, sums, counts, and required order?
3. **Equivalence:** are result comparison criteria clear? If declaring `UNORDERED`, are order differences truly irrelevant to business logic?
4. **Types and characteristics:** if `A` differs from `R`, is the finisher mandatory? Are `IDENTITY_FINISH` and `CONCURRENT` genuinely guaranteed?
5. **Resources and state:** does the supplier create independent accumulators, do the functions avoid modifying the source and shared variables, and could numeric data overflow or lose precision?

Start with built-in collectors such as `Collectors.toList`, `toSet`, `groupingBy`, `summingLong`, or `summarizingLong` when they meet requirements. When you must build a custom collector, **identity, associativity, and equivalence** are the standard ensuring your program keeps producing right results even as Stream partitioning and execution change.
