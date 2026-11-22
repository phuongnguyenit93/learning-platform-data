# Identity Law, Associativity, and Result Equivalence of a Custom Collector

In Java Streams, a **custom collector** lets you transform multiple source elements into an aggregated result: statistics, a collected list, a report object, or combined records. However, writing `supplier`, `accumulator`, `combiner`, and `finisher` correctly is not enough: those functions must satisfy **compatibility laws** so that the same `collect` operation produces the right result whether executed sequentially or in parallel.

The three focal points of this lesson are **identity**, **associativity**, and **result equivalence**. If violated, a collector might pass sequential tests yet fail when Java splits the stream into multiple branches and merges the intermediate results.

## 1. The `Collector<T, A, R>` Contract

`java.util.stream.Collector<T,A,R>` has three type parameters:

- `T`: the element type from the source stream.
- `A`: the **intermediate accumulation container** type (*accumulation type*).
- `R`: the **final result** type after completion.

A collector typically has four components:

| Component | Function | Typical Form |
| --- | --- | --- |
| `supplier` | Creates a new, initially empty/neutral container `A` | `Supplier<A>` |
| `accumulator` | Incorporates an element `T` into container `A` | `BiConsumer<A,T>` |
| `combiner` | Merges two containers `A` into one container `A` | `BinaryOperator<A>` |
| `finisher` | Transforms `A` into `R` if needed | `Function<A,R>` |

```text
Source:                 t1   t2   t3   t4
                         |    |    |    |
Branch 1: supplier() -> A1 --accumulate(t1,t2)
Branch 2: supplier() -> A2 --accumulate(t3,t4)
                                |
                      combiner(A1, A2) -> A
                                |
                         finisher(A) -> R
```

The diagram shows **one possible way of splitting**. Java is free to split into different groups when executing a parallel stream, with no guarantee of exactly two branches and no guarantee on the chronological execution order of callbacks. However, the observable result must satisfy the collector contract.

The `Collector.of(...)` API is used to create a collector from its component functions. With `Collector.of(supplier, accumulator, combiner, finisher, characteristics...)`, you should not attach `CONCURRENT`, `UNORDERED`, or `IDENTITY_FINISH` flags unless you have proven those properties truly hold.

## 2. The Identity Law: Merging with an Empty Container Must Not Change the Result

According to the collector contract, a container `a` formed by a sequence of accumulator calls and a newly created empty container `e = supplier.get()` must satisfy:

```text
combiner(a, e)  ≡  a
```

The symbol `≡` here means **equivalence of observable results**, not necessarily that the two objects share the same reference. In particular, `combiner` may mutate `a` itself and return `a`.

Example of an accumulator storing a sum and a count:

```java
static final class Acc {
    long sum;
    int count;

    void add(int n) {
        sum += n;
        count++;
    }

    Acc merge(Acc other) {
        sum += other.sum;
        count += other.count;
        return this;
    }
}
```

This is an illustrative class declaration snippet and needs to be placed inside an enclosing Java class. A `new Acc()` has `sum = 0` and `count = 0`, so merging it into another accumulator **does not change** the sum or the count.

Suppose `a` has already processed two values `3` and `5`:

```text
a = (sum=8, count=2)
e = (sum=0, count=0)

combine(a,e) = (sum=8, count=2) = a
```

**The identity element here does not have to be a single number.** For a custom collector, it is usually the **empty state of container `A`** created by the supplier.

### Mistake 1: The supplier includes a fixed fee or default count

```java
// WRONG: each new container already counts itself as having one record.
Acc wrong = new Acc();
wrong.count = 1;
```

If the supplier returns an `Acc` with `count = 1`, a result from `n` elements will easily be overcounted. In a parallel stream, each branch may create its own container, so the extra count can be multiplied by the number of containers.

When business logic requires adding a fixed amount **exactly once**, add that amount **after `collect` completes**, rather than sneaking it into every container produced by the supplier.

### Mistake 2: The combiner adds extra data on its own

```java
// WRONG: adds 1 imaginary record on every merge.
Acc mergeWrong(Acc other) {
    this.sum += other.sum;
    this.count += other.count + 1;
    return this;
}
```

Even when `other` is an empty container, `count` still increases by 1. This immediately violates the identity law. With a sequential stream, `combiner` may not be called and the bug stays hidden; when running in parallel, the combiner may run multiple times so the discrepancy appears.

Erroneous snippets are clearly marked so they are **not used in applications**.

## 3. The Associativity Law: Changing How Groups Are Split and Merged Must Not Change the Meaning

For three intermediate results `a`, `b`, `c`, associativity means:

```text
combine(combine(a, b), c)  ≡  combine(a, combine(b, c))
```

This is a law about **results**, not requiring identical call counts or object references. Because a collector's accumulator/combiner often **mutates containers**, in tests you must create **independent containers** for both sides; do not reuse objects that have already been merged.

For the pair `(sum, count)`, combining corresponds to adding each field:

```text
a = (sum=3, count=1)
b = (sum=5, count=1)
c = (sum=7, count=1)

(a ⊕ b) ⊕ c = (sum=15, count=3)
a ⊕ (b ⊕ c) = (sum=15, count=3)
```

Thus, both ways of grouping produce the same result.

**An example of a wrong merge operation** is taking the unweighted average of two groups:

```text
Group X has values [1]        -> average = 1
Group Y has values [9,9,9]    -> average = 9

Average of the two averages = (1 + 9) / 2 = 5   (WRONG)
Average of the four elements = (1 + 9 + 9 + 9) / 4 = 7  (CORRECT)
```

To compute an average, the collector should keep **`sum` and `count`** in `A`, and when merging, add the two sums and the two counts. Only in `finisher` should it compute `sum / count`. If `count == 0`, a well-defined policy is needed (for example returning `OptionalDouble.empty()` or an explicit result field) instead of dividing by 0 unintentionally.

### The law is not only for arithmetic

For a collector accumulating a `List<T>`, the combiner can use `left.addAll(right); return left;`. Concatenating lists left-to-right is associative with respect to **element order**:

```text
([A] ++ [B]) ++ [C] = [A,B,C]
[A] ++ ([B] ++ [C]) = [A,B,C]
```

However, reversing the direction to `right.addAll(left)` or reversing the list on every merge can break the encounter order of a collector that must preserve order. The fact that Java runs in parallel does not mean it is allowed to arbitrarily reverse the result order.

## 4. The Equivalence Law: Valid Collection Strategies Must Return the Same Observable Result

Given the same input elements, a correct collector must ensure that:

1. Accumulating sequentially into one container and then calling the finisher.
2. Splitting the source into parts, accumulating each part into a **new container**, merging the parts in permitted ways, and then calling the finisher.

yield **equivalent** results according to the collector's declared characteristics.

```text
supplier -> accumulate(t1,t2,t3,t4) -> finish = R1

supplier -> accumulate(t1,t2) --+
                                 combine -> finish = R2
supplier -> accumulate(t3,t4) --+

Requirement: R1 ≡ R2
```

Do not equate "equivalent" with being **the exact same object**. For an immutable `record`, value-based `equals()` is usually the appropriate check.

You also need to distinguish between results **with an ordering requirement** and **without an ordering requirement**:

- For a collector that preserves encounter order, two `List` results must have the same elements **in the exact same order**; `[A,B]` and `[B,A]` are not equivalent.
- For a collector declared `UNORDERED`, differences solely in observation order can be considered equivalent. For example, if you truly need a set of values, the iteration order of a `Set` has no business significance.
- Do not attach `UNORDERED` to a collector returning a `List` if element order matters; it can cause parallel execution results to differ from requirements.
- When the finisher creates an aggregate object, compare the **business-meaningful fields** of the result.

The equivalence law does not require callbacks to run on the same thread or on the same schedule. It only constrains the **observable result**.

## 5. Complete Java 17+ Example: A Collector Satisfying All Three Laws

Problem: a list of `Sale` transactions with product unit counts. We need a `Summary(count, totalUnits)` result. The accumulation container is `Acc` with two fields `count` and `units`. When processing a Sale, increment count and add the units; when merging two parts, add each field; the finisher returns an immutable record.

Save as `CollectorLawsDemo.java`:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

public class CollectorLawsDemo {
    record Sale(String sku, int units) {}
    record Summary(int count, long totalUnits) {}

    static final class Acc {
        int count;
        long totalUnits;

        void add(Sale sale) {
            count++;
            totalUnits += sale.units();
        }

        Acc merge(Acc other) {
            count += other.count;
            totalUnits += other.totalUnits;
            return this;
        }

        Summary finish() {
            return new Summary(count, totalUnits);
        }
    }

    static Collector<Sale, Acc, Summary> summaryCollector() {
        return Collector.of(
                Acc::new,
                Acc::add,
                Acc::merge,
                Acc::finish
        );
    }

    static Collector<String, List<String>, List<String>> listCollector() {
        return Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 2),
                new Sale("B", 3),
                new Sale("C", 4),
                new Sale("D", 1)
        );

        Summary sequential = sales.stream()
                .collect(summaryCollector());
        Summary parallel = sales.parallelStream()
                .collect(summaryCollector());

        Acc left = new Acc();
        left.add(sales.get(0));
        left.add(sales.get(1));
        Acc right = new Acc();
        right.add(sales.get(2));
        right.add(sales.get(3));
        Summary split = left.merge(right).finish();

        Acc one = new Acc();
        one.add(sales.get(0));
        Summary identity = one.merge(new Acc()).finish();

        Summary empty = List.<Sale>of().stream()
                .collect(summaryCollector());

        List<String> ordered = List.of("A", "B", "C")
                .parallelStream()
                .collect(listCollector());

        System.out.println("sequential = " + sequential);
        System.out.println("parallel = " + parallel);
        System.out.println("split = " + split);
        System.out.println("identity = " + identity);
        System.out.println("empty = " + empty);
        System.out.println("ordered = " + ordered);
    }
}
```

Compile/run with JDK 17 or later:

```bash
javac -encoding UTF-8 CollectorLawsDemo.java
java CollectorLawsDemo
```

Stdout output:

```text
sequential = Summary[count=4, totalUnits=10]
parallel = Summary[count=4, totalUnits=10]
split = Summary[count=4, totalUnits=10]
identity = Summary[count=1, totalUnits=2]
empty = Summary[count=0, totalUnits=0]
ordered = [A, B, C]
```

**Analysis:**

- `Acc::new` creates a separate container each time `supplier` is called; by default `count=0`, `totalUnits=0` is the neutral empty state.
- `Acc::add` only updates the container provided by the framework, without modifying `Sale` or a global variable.
- `Acc::merge` may mutate the left container and return it; this is a permitted pattern. Both fields are added using a proper associative operation.
- `Acc::finish` returns a new `Summary` record, so the final result **does not expose the mutable accumulation container**.
- `identity` demonstrates that merging a single-element result with a new empty `Acc` does not change the result.
- `empty` demonstrates this collector's policy: on an empty stream, the result is `Summary[count=0, totalUnits=0]`. That is an intentionally chosen contract.
- `listCollector()` does not declare `UNORDERED`. With an ordered `List` source and `left.addAll(right)` merging, the list `[A,B,C]` is preserved even when the collector runs on a parallel stream.

Note: in manual testing, `left.merge(right)` **mutates `left`**; after merging, do not reuse `left` and `right` to test another merge branch. Create a fresh set of containers for each scenario.

## 6. Why Combiner Bugs Often Only Surface in Parallel

A sequential collector typically uses the supplier, accumulator, and then finisher **without needing the combiner**. When running a parallel stream, the framework may create multiple accumulators and needs the combiner to merge results.

Example of a buggy combiner:

```java
Acc mergeWrong(Acc other) {
    totalUnits += other.totalUnits;
    count += other.count + 1; // Unjustifiably adds 1 on every merge.
    return this;
}
```

If the list has four Sales, the sequential accumulator computes `count=4`. However, with two containers having `count=2` and `count=2`, the buggy combiner gives `2 + 2 + 1 = 5`. If Java splits into more branches, the number of extra additions can grow further.

Likewise, a buggy supplier:

```java
// WRONG: returns the same mutable instance on every call.
Acc shared = new Acc();
java.util.function.Supplier<Acc> badSupplier = () -> shared;
```

When branches share `shared`, concurrent calls to `add` can cause a race condition, and `merge` may merge an object with itself. The supplier must return a new container appropriate for each call (except for specially designed immutable/stateless cases that properly satisfy the contract).

**A proper test** is not running parallel once, seeing it look "right," and concluding everything is fine. You need to directly test the identity and associativity laws and compare multiple split/merge strategies.

## 7. Two Common Forms of `Collector.of`

If the accumulation type `A` differs from the result type `R`, use the form with a finisher:

```java
Collector.of(supplier, accumulator, combiner, finisher)
```

In our program, `A = Acc` and `R = Summary`, so `Acc::finish` is required.

If `A` is also `R` and you want to return the accumulation container itself, you can use the three-argument form:

```java
Collector.of(supplier, accumulator, combiner)
```

The three-argument form creates a collector with the `IDENTITY_FINISH` characteristic: the finisher is essentially the identity function. For example, `listCollector()` returns the accumulated `List<String>` directly.

**Do not declare `IDENTITY_FINISH` for `summaryCollector()`**, because `Acc` and `Summary` are two different types and the result must go through `Acc::finish`. If marked incorrectly, the framework may skip the finisher and cause a type error or return the wrong result.

## 8. The Three `Collector.Characteristics` and Their Relationship to the Equivalence Law

`Collector.Characteristics` describes properties that are meaningful when the framework executes:

| Characteristic | Meaning | Caution |
| --- | --- | --- |
| `IDENTITY_FINISH` | The accumulated result can be treated as the final result | Only valid when `A` and `R` are truly compatible so no conversion is needed |
| `UNORDERED` | The collector does not require preserving encounter order | Unsuitable if business logic requires a list in source order |
| `CONCURRENT` | The accumulator may be called concurrently on **the same container** | The container, accumulator, and auxiliary structures must be thread-safe per the contract |

`Acc` uses mutable `int`/`long` fields and ordinary increments, so it is **not thread-safe for multiple threads updating the same instance concurrently**. Therefore `summaryCollector()` does not declare `CONCURRENT`, even though it can still be used on `parallelStream()`: the framework can keep separate accumulators for branches and then merge them via the combiner.

This is an easy point to misunderstand:

> **A collector that works on a parallel stream is not necessarily a collector with the `CONCURRENT` characteristic.**

`CONCURRENT` is a stronger commitment about concurrent accumulation on the same container. Only mark it when concurrent operations have genuinely been designed and tested to be safe.

`UNORDERED` does not mean Java will reverse/shuffle elements; it relaxes the requirement to preserve encounter order. If the result is a set of values whose order does not matter, you can consider an unordered collector; if returning a `List` used for display, keep ordered semantics.

## 9. Distinguishing the Laws of `Collector` and `reduce()`

`reduce(identity, accumulator)` typically uses **an identity that is a value of the result type** and an accumulator that is a combining operation without mutating external state. In a custom collector, the supplier creates an **accumulation container** and the accumulator typically mutates that container.

Comparison:

| `reduce` | Custom `Collector` |
| --- | --- |
| Identity is usually a value like `0`, `1`, `""`... | Identity is an empty container created by `supplier` |
| Accumulator usually returns a new value | Accumulator may mutate container `A` |
| Combiner (if using the three-argument form) must match the accumulator | Combiner merges two containers `A` |
| Result is usually a single value reduced from the elements | Finisher may transform the container into a report type `R` |

**Wrong example:** using the same mutable `StringBuilder` as the identity for `Stream.reduce` and calling `append` across multiple branches. That violates the reduce contract. With `Collector`, the proper design is for each branch to have its own builder provided by the supplier and for the combiner to merge the builders.

However, this does not mean every mutable type warrants writing your own collector. Standard collectors such as `toList()`, `joining()`, `groupingBy()`, and `summarizingInt()` are already implemented by the library in accordance with the contract. Prefer them if they solve the problem; use a custom collector when you need specialized accumulation state or a custom result.

## 10. Checking the Laws with Small Groups

Suppose we have a set of Sales with `units` `[2, 3, 4, 1]`. We can compute:

```text
Linear accumulation:
  empty + 2 + 3 + 4 + 1 -> (count=4, units=10)

Split into two groups:
  empty + 2 + 3 -> (count=2, units=5)
  empty + 4 + 1 -> (count=2, units=5)
  combine        -> (count=4, units=10)

Split into three groups:
  empty + 2     -> (count=1, units=2)
  empty + 3,4   -> (count=2, units=7)
  empty + 1     -> (count=1, units=1)
  combine       -> (count=4, units=10)
```

To test more rigorously, create multiple ways of splitting and merging, then compare results **after the finisher**. In particular, be sure to include:

1. **Empty source:** `supplier.get()` followed by `finish()` must produce a result permitted by the policy.
2. **Single element:** verify the accumulator makes exactly one contribution.
3. **Identity:** merge a populated accumulator with a new empty container; the result must be equivalent to the original state.
4. **Associativity:** merge three groups in both ways using independent sets of containers, and compare the final results.
5. **Sequential versus parallel:** compare results on a sufficiently large dataset with varied distributions.
6. **Ordering:** if it is an ordered collector, feed clearly ordered data to catch a combiner that reverses the list.
7. **Thread-safety:** if planning to mark `CONCURRENT`, you must test for data races, especially `count++` operations and map/list updates.

Testing a few cases does not prove the laws for all data, so you also need **reasoning from the mathematical structure** of the combining operation.

## 11. Common Mistakes

| Mistake | Why It Is Wrong | How to Fix |
| --- | --- | --- |
| Supplier initializes `count = 1` | Empty container already contains a phantom contribution; identity is not neutral | Initialize state with `count=0` |
| Combiner adds a fixed fee on every merge | Number of merges depends on how the stream is split | Add the fixed amount once **after collect** |
| Combiner merges only `sum`, forgetting `count` | Branch state is not fully combined | Merge all relevant state fields |
| Merging `average` by averaging two averages | Groups of different sizes are given equal weight | Merge `sum` and `count`, compute average in finisher |
| Supplier returns a shared mutable instance | Data race or combiner merges an object with itself | Create a new container on every call |
| Combiner reverses `List` order | Violates equivalence when encounter order matters | Concatenate left-to-right in the proper order |
| Marking `CONCURRENT` on a non-thread-safe container | Accumulator may be called concurrently on the same container | Only mark when true concurrency guarantees exist |
| Marking `IDENTITY_FINISH` when `A != R` | Conversion step may be skipped | Use a real finisher and do not mislabel |
| Adding `UNORDERED` hoping for better speed | May lose the result's ordering requirement | Only drop the constraint when business logic does not need order |
| Testing only sequentially | Combiner may not have run, hiding bugs | Test manual split/merge and parallel execution |
| Assuming two containers must be `==` to be equivalent | Mutable collectors may create multiple distinct instances | Compare post-finisher results per the contract |

## 12. Self-Check Questions

**Question 1.** For a counting collector, why must `supplier` create `count=0`?

**Answer:** Because 0 is the state that contributes no records; merging an empty container must preserve the count of the other container.

**Question 2.** A custom collector has a correct `accumulator`, but its `combiner` adds 1 on every merge. Why can it still pass sequential tests?

**Answer:** Sequential execution may not need to call the combiner; the bug only surfaces when combining groups, especially in a parallel stream.

**Question 3.** Why shouldn't you average group averages by dividing evenly by the number of groups?

**Answer:** Because groups can have different sizes; a weighted total is needed. Keep `sum` and `count`, then compute the average after merging.

**Question 4.** Can a custom collector that does not declare `CONCURRENT` be used on a parallel stream?

**Answer:** Yes, if the collector laws hold. The framework can use separate accumulators for branches, then merge them with the combiner.

**Question 5.** For a collector returning an ordered `List`, are `[A,B]` and `[B,A]` equivalent?

**Answer:** No. They differ in encounter order, so that is wrong if the collector must preserve source order.

**Question 6.** Is `IDENTITY_FINISH` valid when `A` is the mutable container `Acc` and `R` is the record `Summary`?

**Answer:** No. The finisher must convert `Acc` into `Summary`; marking identity finish is wrong.

## Key Takeaways

- **Identity:** `combiner(a, supplier.get()) ≡ a` for any valid accumulator `a`.
- **Associativity:** different ways of splitting/merging accumulators must produce equivalent results, regardless of how groups are organized.
- **Equivalence:** sequential and parallel collection must yield equivalent observable results according to the collector's ordering guarantees.
- The supplier must create a new container in the proper empty state; the accumulator must update all data; the combiner must merge all state; the finisher must convert to the final result type.
- Do not attach `CONCURRENT`, `UNORDERED`, or `IDENTITY_FINISH` unless the contract is satisfied.
- When in doubt, test **empty, identity, multiple split/merge strategies, and sequential vs parallel** before putting a custom collector into production code.
