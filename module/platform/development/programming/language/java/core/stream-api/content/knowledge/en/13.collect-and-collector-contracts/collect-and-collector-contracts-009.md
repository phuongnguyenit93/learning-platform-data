# Testing a Collector When Merging Multiple Intermediate Results

> **Chapter:** Collect Mechanism and Collector  
> **Module:** JAVA_STREAM_API  
> **Focus:** Verify that a `Collector` preserves correct results when the Java Stream API splits data into multiple parts, creates intermediate accumulation states, and uses `combiner` to merge them. This is an essential prerequisite before using `parallelStream()`, `parallel()`, custom collectors, or complex data grouping operations.

## Learning objectives

After this lesson, you will be able to:

1. Describe the roles of `supplier`, `accumulator`, `combiner`, `finisher`, and `characteristics` in `Collector<T, A, R>`.
2. Distinguish the correctness of a Collector when run sequentially versus when intermediate states are merged in multiple ways.
3. Verify the two core laws: **identity** and **associativity**, while checking result equivalence through `finisher`.
4. Write a Collector that uses a mutable accumulator without mistakenly sharing containers across execution partitions.
5. Detect combiners that drop records, duplicate data, reverse merge order, or introduce rounding errors.
6. Design tests that proactively split a source into 2–3 partitions, vary merge trees, check empty sources, and use an independent oracle.
7. Understand the impact of `CONCURRENT`, `UNORDERED`, and `IDENTITY_FINISH` on how a Stream may accumulate and merge state.

Examples use Java 17 or later. `Collector`, `collect`, and the parallel Stream mechanism have existed since Java 8; examples using `record` require Java 16+. The content connects `filter`, `map`, `reduce`, `groupingBy`, sum correctness, and `Spliterator` data sources in the Java Stream API module.

## 1. Why is passing sequentially not enough?

A data collection pipeline may operate as follows:

~~~text
Source with 6 elements: [a, b, c, d, e, f]

Sequential collection:
  supplier() -> A0
  accumulator(A0, a)
  accumulator(A0, b)
  ...
  accumulator(A0, f)
  finisher(A0) -> R

One possibility during parallel execution:
       [a, b]          [c, d]          [e, f]
         |               |               |
   supplier()       supplier()      supplier()
         |               |               |
       A1              A2              A3
         \               /               |
          combiner(A1,A2)                |
                  \                       /
                     combiner(...)
                           |
                       finisher()
                           |
                           R
~~~

In a simple sequential case, only one accumulation container may be used and **the combiner may not need to be called**. When a Stream partitions data for parallel processing, `combiner` can be invoked multiple times to merge containers produced by different branches.

Therefore, a Collector with a correct `accumulator` but a broken `combiner` often passes sequential tests and then fails when switched to `parallelStream()`.

~~~java
import java.util.List;
import java.util.stream.Collector;

List<Integer> numbers = List.of(1, 2, 3, 4, 5, 6);

// Wrong: combiner completely discards the right-hand state.
Collector<Integer, int[], Integer> broken = Collector.of(
        () -> new int[] {0},
        (acc, value) -> acc[0] += value,
        (left, right) -> left,
        acc -> acc[0]
);

System.out.println(numbers.stream().collect(broken)); // 21 in sequential example
// Parallel result IS NOT GUARANTEED to be 21.
System.out.println(numbers.parallelStream().collect(broken));
~~~

The bug lies right in the contract: `(left, right) -> left` drops all results from `right`. Do not rely on a specific number from a parallel run; the environment and source splitting can affect how many times the combiner is called.

**The goal of testing a Collector is to verify intermediate merging**, not merely checking one sequential run and one parallel run that happened to yield the same result.

## 2. Reading the Collector<T, A, R> contract properly

A Collector has three types:

~~~java
Collector<T, A, R>
~~~

- `T`: the Stream's input element type.
- `A`: the **intermediate** accumulation container/state type.
- `R`: the **final** result type of the collection operation.

A Collector has five components:

| Component | Conceptual signature | Responsibility |
|---|---|---|
| `supplier()` | `() -> A` | Creates a new state `A`, initially empty |
| `accumulator()` | `(A, T) -> void` | Incorporates an element `T` into state `A` |
| `combiner()` | `(A, A) -> A` | Merges two accumulation states into one |
| `finisher()` | `A -> R` | Converts final state into the public result |
| `characteristics()` | `Set<Characteristics>` | Tells the framework the Collector's properties |

Example with a list:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

Collector<String, List<String>, List<String>> toMutableList =
        Collector.of(
                ArrayList::new,                   // supplier
                List::add,                       // accumulator
                (left, right) -> {                // combiner
                    left.addAll(right);
                    return left;
                }
                // 3-parameter Collector.of has an identity finisher.
        );

List<String> result = List.of("a", "b", "c")
        .parallelStream()
        .collect(toMutableList);

System.out.println(result); // [a, b, c]
~~~

Here container `A` is also result `R`. In another example, `A` might be a mutable object holding sum and count, while `R` is an immutable `record` describing statistics.

### 2.1. collect is not a simple reduce on a shared variable

`Stream.collect(Collector)` is a **terminal operation**. It consumes the Stream and collects results according to the Collector contract. Creating separate containers per work chunk and merging them with `combiner` is a key mechanism supporting parallelism.

Do not replace it with:

~~~java
// Incorrect parallel collection design:
// List<String> shared = new ArrayList<>();
// input.parallelStream().forEach(shared::add);
~~~

`ArrayList` is not safe when multiple threads add elements concurrently. A proper Collector coordinates containers and merging according to the appropriate contract.

A `Collector` can hold mutable containers. What matters is **which container is modified, at what stage, and whether it is shared across threads**.

## 3. Two foundational laws: identity and associativity

The `Collector` contract documentation describes constraints on collection results. Let's use the notation:

- `empty()` = `supplier.get()`: a fresh container in the empty state.
- `accumulate(a, t)`: adds element `t` to state `a`.
- `combine(a, b)`: merges two states.
- `finish(a)` = `finisher.apply(a)`: produces the final result.

When testing, **equivalence** means equivalence under the result contract. It does not require two `A` objects to have the same memory address or return `true` from `equals`; many mutable containers do not define `equals` by content.

### 3.1. Identity: merging with an empty container does not change meaning

Given an accumulated state `a`, the contract requires:

~~~text
finish(combine(a, empty()))  ≈  finish(a)

≈ : equivalent in the result exposed by the Collector
~~~

Example of a counting accumulator:

~~~java
final class CountAcc {
    long count;

    void accept(String value) {
        count++;
    }

    CountAcc combine(CountAcc other) {
        count += other.count;  // merge counts
        return this;
    }
}
~~~

A fresh container has `count == 0`. Merging it into an existing state does not change the count.

Common mistake: `supplier` initializes the counter to `1`, or `combiner` adds an off-spec "partition fee". In a parallel Stream, containers can be created many times; the extra value gets multiplied by the number of partitions.

**Specifically:** to compute an average, `supplier` must initialize **sum = 0, count = 0**. Do not initialize `count = 1` to "avoid division by zero"; handle an empty source in `finisher`.

### 3.2. Associativity: merging multiple partitions under any tree gives the same answer

If three source partitions produce states `a`, `b`, and `c`, we must have:

~~~text
finish(combine(combine(a, b), c))
    ≈
finish(combine(a, combine(b, c)))
~~~

This is the **associativity** of merging intermediate results. For an ordered Collector, both merges above maintain the source partition order `a -> b -> c`; they only **change parenthesization**, without reordering source partitions.

Example of proper list merging:

~~~text
a = [A, B]
b = [C]
c = [D, E]

(left + right) in order:
  ((a + b) + c) = [A, B, C, D, E]
  (a + (b + c)) = [A, B, C, D, E]
~~~

`addAll` in left-then-right order fits, assuming independent containers. Conversely, if the combiner always concatenates `right + left`, results get reversed under some splits, violating encounter-order preservation.

### 3.3. Identity/associativity are evaluated at the result level

For a Collector with a `finisher`, two distinct state objects can still produce equivalent results. For example, accumulators storing counts can have different `identityHashCode` values yet return the same `long`.

When testing manually on mutable accumulators, **create fresh containers for each merge tree**. Never reuse a container already mutated by `combine` to compare another merge tree, as the test itself will corrupt its input data.

## 4. Example of a correct Collector: merging count and exact total amount

Suppose we process transactions, where each transaction records an amount in **cents**, which can be positive or negative (refunds). We need a result containing transaction count and total cents, without overflowing `long` addition.

The snippet below is a standalone Java 17 program:

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.stream.Collector;

public class CollectorMergeDemo {
    record Sale(String id, long cents) {}
    record Summary(long count, BigInteger totalCents) {}

    static final class Acc {
        private long count;
        private BigInteger total = BigInteger.ZERO;

        void add(Sale sale) {
            count = Math.addExact(count, 1L);
            total = total.add(BigInteger.valueOf(sale.cents()));
        }

        Acc merge(Acc other) {
            count = Math.addExact(count, other.count);
            total = total.add(other.total);
            return this;
        }

        Summary finish() {
            return new Summary(count, total);
        }
    }

    static Collector<Sale, Acc, Summary> collector() {
        return Collector.of(
                Acc::new,       // supplier
                Acc::add,       // accumulator
                Acc::merge,     // combiner
                Acc::finish     // finisher
        );
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 1_200),
                new Sale("B", -200),
                new Sale("C", 500),
                new Sale("D", 700)
        );

        Summary sequential = sales.stream().collect(collector());
        Summary parallel = sales.parallelStream().collect(collector());

        System.out.println(sequential); // Summary[count=4, totalCents=2200]
        System.out.println(parallel);   // Summary[count=4, totalCents=2200]
    }
}
~~~

Why is this Collector suitable for merging partitions?

- `Acc::new` provides a separate container with **count = 0**, **total = 0**.
- `Acc::add` adds one transaction to the container's own state.
- `Acc::merge` merges **both count and total** from the two containers, omitting no field.
- `Acc::finish` returns an immutable `Summary`; results can be compared using `equals`.
- `BigInteger::add` performs exact integer addition; parenthesizing additions never changes the value.
- `Math.addExact` detects `long` counter overflow. If counts beyond `long` limits are required, choose a different counter type.

In this Collector, `merge` **mutates `this`** and returns `this`. That is a valid pattern: the combiner is allowed to merge into one container and return that container. Creating a new `Acc` object on every merge is not required.

**Safety scope:** `Acc` is not thread-safe if the same instance is updated concurrently. However, the Collector here **does not declare `CONCURRENT`**; the Stream can use separate containers and merge them during parallel execution. Never store an `Acc` in a static field to reuse across `collect` runs.

## 5. Directly testing two intermediate containers

A good test approach is creating independent containers, accumulating each source slice, and calling the combiner, instead of only running `parallelStream()` and hoping the framework picks the desired split structure.

The following methods can be placed **inside the `CollectorMergeDemo` class** from section 4:

~~~java
static Acc fold(List<Sale> partition) {
    Acc acc = new Acc();
    for (Sale sale : partition) {
        acc.add(sale);
    }
    return acc;
}

static void requireEquals(Object expected, Object actual) {
    if (!expected.equals(actual)) {
        throw new AssertionError(
                "Expected " + expected + ", got " + actual
        );
    }
}

static void verifyTwoPartitions(List<Sale> sales) {
    int middle = sales.size() / 2;

    Acc left = fold(sales.subList(0, middle));
    Acc right = fold(sales.subList(middle, sales.size()));

    Summary merged = left.merge(right).finish();

    Summary whole = fold(sales).finish();
    requireEquals(whole, merged);
}
~~~

With a list of four transactions `A, B, C, D`:

~~~text
Part 1: [A, B] -> count=2, total=1000
Part 2: [C, D] -> count=2, total=1200

Correct merge:
  count = 2 + 2 = 4
  total = 1000 + 1200 = 2200
~~~

When testing a real Collector, you can retrieve `supplier()`, `accumulator()`, and `combiner()` directly from the Collector itself to avoid duplicating logic. Section 7 shows how to do that.

### 5.1. Both fields of the result must be checked

If the combiner only adds total cents and forgets to add `count`:

~~~java
// WRONG, illustrative only:
// Acc merge(Acc other) {
//     total = total.add(other.total);
//     return this;  // other's count is forgotten
// }
~~~

A test checking only total amount might still PASS, yet the transaction count is wrong. Likewise, a collector with multiple fields like `sum`, `count`, `min`, `max`, or grouped `Map`s must check **every field** and consistency among them.

## 6. Testing three partitions: two parenthesizations

Split data into three distinct parts:

~~~text
A = [1, 2]
B = [3]
C = [4, 5]

Left tree:  combine(combine(A, B), C)
Right tree: combine(A, combine(B, C))
~~~

With mutable accumulators, each merge tree must be built from separate containers. Add these methods to `CollectorMergeDemo`:

~~~java
static void verifyAssociativity(
        List<Sale> first,
        List<Sale> second,
        List<Sale> third) {

    Summary leftGrouping = fold(first)
            .merge(fold(second))
            .merge(fold(third))
            .finish();

    Summary rightGrouping = fold(first)
            .merge(fold(second).merge(fold(third)))
            .finish();

    requireEquals(leftGrouping, rightGrouping);

    // Also verify the baseline result of the combined input set.
    java.util.ArrayList<Sale> all = new java.util.ArrayList<>();
    all.addAll(first);
    all.addAll(second);
    all.addAll(third);
    Summary whole = fold(all).finish();

    requireEquals(whole, leftGrouping);
}
~~~

You can call:

~~~java
verifyAssociativity(
        sales.subList(0, 2),
        sales.subList(2, 3),
        sales.subList(3, 4)
);
~~~

This test calls the example's `merge` directly. It catches combiners that depend on **grouping structure** and removes the luck factor of parallel scheduling.

**Do not swap the order of A, B, C** when testing associativity of an ordered Collector. The equality `combine(a, b) == combine(b, a)` is **commutativity**, a stronger requirement that does not apply to every valid Collector. A list-concatenating Collector is associative but typically **not commutative**.

## 7. Test helper using the Collector interface directly

To apply across many Collectors, you can write a utility operating strictly through the components provided by `Collector`.

~~~java
import java.util.List;
import java.util.stream.Collector;

final class CollectorChecks {
    private CollectorChecks() {}

    static <T, A, R> A fold(
            Collector<T, A, R> collector,
            List<T> source) {
        A container = collector.supplier().get();

        for (T element : source) {
            collector.accumulator().accept(container, element);
        }
        return container;
    }

    static <T, A, R> R finish(
            Collector<T, A, R> collector,
            A container) {
        return collector.finisher().apply(container);
    }

    static <T, A, R> R mergeInOrder(
            Collector<T, A, R> collector,
            List<T> first,
            List<T> second) {
        A a = fold(collector, first);
        A b = fold(collector, second);

        A merged = collector.combiner().apply(a, b);
        return finish(collector, merged);
    }

    static <T, A, R> void verifyTwoPartitions(
            Collector<T, A, R> collector,
            List<T> source) {
        int middle = source.size() / 2;

        R expected = source.stream().collect(collector);
        R actual = mergeInOrder(
                collector,
                source.subList(0, middle),
                source.subList(middle, source.size())
        );

        if (!java.util.Objects.equals(expected, actual)) {
            throw new AssertionError(
                    "Merge mismatch: " + expected + " vs " + actual
            );
        }
    }
}
~~~

For instance, inside `CollectorMergeDemo.main`:

~~~java
CollectorChecks.verifyTwoPartitions(collector(), sales);
~~~

This helper:

1. Creates **two** `A` containers via `supplier`.
2. Calls `accumulator` for each partition.
3. Forces `combiner` to be called at least once.
4. Uses `finisher` to check the `R`-typed result.
5. Compares against collecting over the whole source.

**Limitation of this comparison:** If sequential collection is also wrong, the test above can give a false PASS. You need an **independent oracle** based on business logic, such as a loop summing with `BigInteger` or a small hand-calculated dataset. The test also uses `Objects.equals`, which only fits if `R` has proper `equals` semantics; for arrays, use `Arrays.equals` or `Arrays.deepEquals` as appropriate.

### 7.1. Testing identity with an empty container

For a custom Collector with an immutable result, you can write:

~~~java
Collector<Sale, Acc, Summary> c = collector();

Acc accumulated = CollectorChecks.fold(c, sales);
Summary before = c.finisher().apply(accumulated);

Acc empty = c.supplier().get();
Acc merged = c.combiner().apply(accumulated, empty);
Summary after = c.finisher().apply(merged);

requireEquals(before, after);
~~~

Here `before` is an immutable `record Summary`, so the fact that `merged` may mutate `accumulated` does not change the value captured in `before`. If `R` itself is a mutable container, you must **snapshot its contents** before merging; comparing two references to the same object after mutation can give a false PASS.

### 7.2. With a valid collector on an empty Stream

~~~java
import java.util.List;

List<Sale> empty = List.of();

Summary s1 = empty.stream().collect(collector());
Summary s2 = empty.parallelStream().collect(collector());

System.out.println(s1); // Summary[count=0, totalCents=0]
System.out.println(s2); // Summary[count=0, totalCents=0]
~~~

An empty source tests whether `supplier` and `finisher` express the empty state properly. **Never** initialize `count = 1` just to avoid division-by-zero errors when averaging; specify the empty-source result explicitly.

## 8. Combiner bugs to catch

### 8.1. Dropping the right-hand result

~~~java
// Wrong:
(left, right) -> left
~~~

When two partial results exist, one is lost. Tests splitting into two non-empty partitions usually catch this immediately.

### 8.2. Merging with the wrong operation

~~~java
// Wrong when aggregating money:
// (left, right) -> {
//     left.total = left.total.subtract(right.total);
//     return left;
// }
~~~

The combiner must have **the same aggregation semantics** as the accumulator. If the accumulator adds amounts while the combiner subtracts them, the result depends on how partitions are split.

### 8.3. Forgetting to merge a field

~~~java
// Wrong if statistics include sum and count:
// left.sum += right.sum;
// return left; // Forgot left.count += right.count
~~~

A test checking only `sum` will miss it. Verify `sum`, `count`, `min`, `max`, and every business attribute simultaneously.

### 8.4. Merging duplicates data

~~~java
// Wrong for lists:
// left.addAll(right);
// left.addAll(right); // duplicates the entire right part
// return left;
~~~

A list with repeated elements can hide bugs if you only compare sets of values. Compare **multiplicity** as well as order when the contract requires it.

### 8.5. Reversing the order of result parts

~~~java
// Wrong if the Collector must preserve encounter order:
// right.addAll(left);
// return right; // [B, C] + [A] can become [B, C, A]
~~~

For a Collector gathering a `List` from an ordered source, the combiner must append in the expected order. `Collectors.toList()` is preferable if you only need a list without custom container requirements.

### 8.6. Each partition incurs an initialization fee

~~~java
// Semantically wrong for supplier:
// () -> new long[] {100L}
~~~

If `100` is a "flat fee for the entire batch", creating multiple containers can add the fee multiple times. Separate flat fees from per-record aggregation and apply them **once after aggregating**, if that matches business rules.

### 8.7. Intermediate rounding

~~~java
// Risk of error when BigDecimal is merged across different groupings:
// left.sum = left.sum.add(right.sum, mathContext);
~~~

When `MathContext` rounds at every step, addition can lose associativity for exact decimal values. If rules allow, accumulate with `BigDecimal::add` **without passing a MathContext**, then round once in the finisher. If each transaction must be rounded upfront, normalize **each transaction** and then sum the normalized values.

## 9. Supplier must create independent containers

A subtle bug is reusing **the exact same instance** for all supplier invocations:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

List<String> shared = new ArrayList<>();

// WRONG: every time supplier is called it returns the same List.
Collector<String, List<String>, List<String>> broken = Collector.of(
        () -> shared,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
~~~

When merging two "containers" that are actually **one object**, `left.addAll(right)` can become `list.addAll(list)`, duplicating elements. In parallel runs, multiple threads can also write to the same `ArrayList` without synchronization.

The right way:

~~~java
Collector<String, List<String>, List<String>> correct = Collector.of(
        ArrayList::new,
        List::add,
        (left, right) -> {
            left.addAll(right);
            return left;
        }
);
~~~

`ArrayList::new` creates a new list for **every supplier invocation**.

**Practical rule:** Do not place accumulators in static fields, singletons, or shared closures and return them from `supplier`. Each collection's containers must be independent so the framework can manage accumulation and merging properly.

## 10. Finisher, result type, and IDENTITY_FINISH

The final result `R` can differ from accumulation type `A`. In the statistics example, `A = Acc` and `R = Summary`; `finisher` converts mutable data into an immutable `record`.

A short example collecting strings and producing a structurally unmodifiable list:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collector;

Collector<String, List<String>, List<String>> immutableList =
        Collector.of(
                ArrayList::new,
                List::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                },
                List::copyOf
        );

List<String> values = List.of("a", "b", "c")
        .parallelStream()
        .collect(immutableList);

System.out.println(values); // [a, b, c]
// values.add("d"); // UnsupportedOperationException
~~~

Here `finisher` matters: it turns a mutable `ArrayList` into a structurally unmodifiable list. **Do not declare `IDENTITY_FINISH`** for this collector.

### 10.1. Meaning of IDENTITY_FINISH

`Collector.Characteristics.IDENTITY_FINISH` allows the framework to treat the finishing step as an identity cast, skipping calling another finisher. This characteristic must be **true by type and behavioral contract**, not merely because "the finisher usually returns the same contents as the accumulator".

Mistake:

~~~java
// DO NOT manually add Characteristics.IDENTITY_FINISH to a Collector
// whose finisher is List::copyOf; the framework may skip the finisher,
// leaving the result no longer guaranteed to be an immutable list.
~~~

With three-parameter `Collector.of(supplier, accumulator, combiner)`, the result is the container itself and the Collector has `IDENTITY_FINISH`. With overloads whose finisher genuinely transforms data, leave this characteristic absent unless an identity cast satisfies the contract.

### 10.2. Do not compare reference identity instead of content

~~~java
import java.util.ArrayList;
import java.util.List;

List<String> first = new ArrayList<>(List.of("a", "b"));
List<String> second = new ArrayList<>(List.of("a", "b"));

System.out.println(first == second);      // false
System.out.println(first.equals(second)); // true
~~~

Two valid Collectors can return two different instances with identical contents. Use business-result equivalence criteria, not memory addresses.

## 11. Ordered Collectors and UNORDERED Collectors

`Characteristics.UNORDERED` states that the collection **does not commit to preserving encounter order**. It is a property of the Collector, not a command saying "reverse the order".

Examples:

- Collecting elements into a `List` usually cares about order if the source is ordered.
- Collecting into a `Set` or `Map` for key lookup usually does not care about iteration order, unless the problem specifies a particular order.
- A summing Collector can be order-independent if the aggregation operation is accurate and order-insensitive.

Verification table:

| Result | Suitable equivalence check |
|---|---|
| Ordered `List<T>` | `List.equals`, checking exact positions and multiplicities |
| Order-independent `Set<T>` | `Set.equals` |
| Order-independent `Map<K,V>` | `Map.equals` and checking each value |
| Exact integer sum | Exact numeric equality |
| `double` sum | Per defined error tolerance / reproducibility policy |
| Result of a Collector declaring `UNORDERED` | Compare contents per contract; do not assume order |

**Merge ordering:** For an ordered Collector, test different parenthesizations while preserving partition order. For a Collector genuinely indifferent to order, you may also test reordering partitions to detect unintended order dependencies.

Do not add `UNORDERED` to a Collector concatenating a `StringBuilder` or `List` when the business requirement is to keep input order.

## 12. CONCURRENT does not mean just using parallelStream()

A Collector declaring `Characteristics.CONCURRENT` indicates its container may be **accumulated into concurrently** by multiple threads. For this characteristic to hold, the data structure and accumulator must support that.

A Collector **not declaring `CONCURRENT`** can still be used validly with `parallelStream()`: the framework can accumulate into multiple separate containers and call `combiner`.

Distinction:

| Situation | What might the framework do? | What must be ensured |
|---|---|---|
| `parallelStream()` + normal Collector | Create multiple containers, accumulate separately, merge | Combiner satisfies identity/associativity |
| `CONCURRENT` Collector on a Stream without encounter order to keep | May call accumulator concurrently on **the same container** | Container and accumulator are thread-safe |
| `CONCURRENT` Collector without `UNORDERED` on an ordered Stream | Framework may choose not to share concurrently to preserve order | Never assume every run uses the same container |
| `UNORDERED` Collector without `CONCURRENT` | Does not require order yet may still use multiple separate containers | Never share containers recklessly because of `UNORDERED` |

Under the Stream collection mechanism, concurrent accumulation in a single container can specifically be used if the Collector has `CONCURRENT` and either the source is **unordered** or the Collector also has `UNORDERED`. Even when eligible, the framework is not obligated to pick a fixed execution schedule.

### 12.1. Example choosing a built-in concurrent API

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

record Payment(String category, long cents) {}

List<Payment> payments = List.of(
        new Payment("BOOK", 100),
        new Payment("PEN", 50),
        new Payment("BOOK", 300)
);

ConcurrentMap<String, BigInteger> sums = payments.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Payment::category,
                p -> BigInteger.valueOf(p.cents()),
                BigInteger::add
        ));

System.out.println(sums.get("BOOK")); // 400
System.out.println(sums.get("PEN"));  // 50
~~~

`Collectors.toConcurrentMap` manages the container and concurrent merging per the API contract. `BigInteger::add` fits because it yields exact integer results. This is usually a clearer choice than writing a shared `HashMap` yourself and declaring the Collector `CONCURRENT`.

**Do not do:**

~~~java
// Wrong if accumulator can run concurrently on the same container:
// Collector.Characteristics.CONCURRENT
// combined with HashMap::new and unsynchronized HashMap.merge(...).
~~~

`HashMap` is not thread-safe. Attaching `CONCURRENT` yourself does not make the container safe.

## 13. Testing with groupingBy, mapping, and reducing

A downstream Collector must also merge properly when grouped results are split across multiple parts.

Example aggregating total cents by category:

~~~java
import java.math.BigInteger;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Payment(String category, long cents) {}

List<Payment> payments = List.of(
        new Payment("BOOK", 100),
        new Payment("PEN", 50),
        new Payment("BOOK", -30),
        new Payment("PEN", 70)
);

Map<String, BigInteger> totals = payments.parallelStream()
        .collect(Collectors.groupingBy(
                Payment::category,
                Collectors.mapping(
                        p -> BigInteger.valueOf(p.cents()),
                        Collectors.reducing(BigInteger.ZERO, BigInteger::add)
                )
        ));

System.out.println(totals.get("BOOK")); // 70
System.out.println(totals.get("PEN"));  // 120
~~~

There are two levels of merging:

1. **Group level:** results for the same key from multiple partitions must be merged into the right key.
2. **Value level:** `BigInteger` sums for the same key are added using an exact associative operation.

Tests should verify:

- The key set is right, with no missing or unexpected keys.
- **Each key's** value is right.
- The sum across groups equals the whole-source sum if each record belongs to exactly one group.
- Do not rely on `HashMap`/`ConcurrentHashMap` iteration order without an ordering contract.

### 13.1. Using toMap requires a merge function for duplicate keys

~~~java
Map<String, BigInteger> totals = payments.parallelStream()
        .collect(Collectors.toMap(
                Payment::category,
                p -> BigInteger.valueOf(p.cents()),
                BigInteger::add
        ));
~~~

If two data slices share the same key, `toMap` needs a way to merge values; `BigInteger::add` is a valid merge function. Omitting the merge function when duplicate keys occur causes `IllegalStateException`, regardless of sequential or parallel execution.

Do not use non-associative merge functions like subtraction or division if you want results independent of partitioning.

## 14. Checking numeric data: avoiding a "type-correct" yet arithmetically wrong combiner

A Collector can compile and return the right type `R` while still failing calculation requirements.

### 14.1. Averages must merge sum and count

Two partitions:

~~~text
A = [10, 20]  -> average = 15, count = 2
B = [100]     -> average = 100, count = 1

Wrong:   (15 + 100) / 2 = 57.5
Correct: (10 + 20 + 100) / 3 = 43.333...
~~~

A combiner cannot simply average two averages unless the design adds proper weights. Instead, the accumulator should hold a **(sum, count)** pair, the combiner adds each field, and only the finisher divides.

~~~java
import java.math.BigDecimal;
import java.math.BigInteger;
import java.math.RoundingMode;

record Stats(BigInteger sum, long count) {
    BigDecimal average(int scale) {
        if (count == 0) {
            throw new IllegalStateException("No data");
        }
        return new BigDecimal(sum).divide(
                BigDecimal.valueOf(count),
                scale,
                RoundingMode.HALF_UP
        );
    }
}
~~~

This record is a **final result** usable after collecting `sum` and `count` with a proper Collector. Decisions on scale and rounding mode must come from business requirements.

### 14.2. Integers can overflow

~~~java
import java.util.List;

List<Integer> amounts = List.of(1_500_000_000, 1_500_000_000);

int wrong = amounts.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();

long correctInLong = amounts.parallelStream()
        .mapToLong(Integer::longValue)
        .sum();

System.out.println(wrong);         // -1294967296
System.out.println(correctInLong); // 3000000000
~~~

Even though `int` addition's combiner is associative **modulo** \(2^{32}\), the result can be business-wrong when mathematical integer totals are wanted. Choose `long` or `BigInteger` according to value domain; never treat "sequential == parallel" as sole proof of correctness.

### 14.3. double is not strictly associative

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

If a combiner uses `double` addition or rounds `BigDecimal` at every step, results can vary with the merge tree. Define allowed error tolerance, accumulation algorithm, rounding rules, or pick exact arithmetic if business logic demands it.

## 15. A test suite comprehensive enough to catch intermediate merge bugs

A baseline matrix:

| Case | Why test it? | Expectation |
|---|---|---|
| Empty source | Supplier/finisher handle initial state properly | Empty/0 result matching business rules |
| Single element | Does not invent extra values | Result matches single element |
| Two non-empty partitions | Forces combiner usage | No lost or duplicated data |
| One empty partition | Identity | Merging with empty does not alter result |
| Three partitions | Associativity | Both parenthesizations yield equivalent results |
| Heavily skewed partition sizes | Exposes averaging-of-averages bug | Exact sum/count |
| Duplicate data, duplicate keys | Exposes merge or multiplicity bugs | Preserves full multiplicities |
| Many positive and negative values | Exposes overflow/cancellation | Accurate within business numeric domain |
| Source permutations | Checks order-independent cases | Apply only if contract permits |
| Large source and repeated parallel runs | Detects races or rare bugs | Matches oracle, no shared state |
| Collector with `CONCURRENT` | Accumulator may be called concurrently | Thread-safe and consistent |
| Ordered results | Exposes branch-reversing combiners | Preserves encounter order when required |

Do not stop at `assertEquals(sequential, parallel)`. If the combiner was not called in a run or both execution paths share an arithmetic bug, the comparison can falsely PASS.

### 15.1. Independent oracle

For the `Sale` data in section 4, build an independent computation loop:

~~~java
static Summary oracle(List<Sale> sales) {
    long count = 0;
    java.math.BigInteger total = java.math.BigInteger.ZERO;

    for (Sale sale : sales) {
        count = Math.addExact(count, 1L);
        total = total.add(java.math.BigInteger.valueOf(sale.cents()));
    }

    return new Summary(count, total);
}
~~~

Add this method **inside `CollectorMergeDemo`**. Then verify:

~~~java
Summary expected = oracle(sales);
Summary seq = sales.stream().collect(collector());
Summary par = sales.parallelStream().collect(collector());

requireEquals(expected, seq);
requireEquals(expected, par);
~~~

This oracle uses a loop, never calling the Collector under test. That way, if `accumulator` and `combiner` share a flaw, comparing against the oracle has a chance to catch it.

### 15.2. Try multiple ways of splitting, not just halving

For example, with a six-element list:

~~~text
[A, B, C, D, E, F]

[A] | [B, C, D, E, F]
[A, B] | [C, D, E, F]
[A, B, C] | [D, E, F]
[A, B, C, D] | [E, F]
[A, B, C, D, E] | [F]

[A] | [B, C] | [D, E, F]
[A, B] | [C] | [D, E, F]
...
~~~

Use a helper like `CollectorChecks.mergeInOrder` to test each two-way split. With three partitions, compare both `(A + B) + C` and `A + (B + C)` using fresh containers.

If the Collector is designed as **UNORDERED** and its merge is genuinely order-indifferent, you can test swapping partitions as well. For ordered Collectors, only vary split boundaries and merge trees; do not reverse encounter order.

### 15.3. Use a fixed seed when generating data

~~~java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Random;

List<Integer> original = List.of(2, 5, 1, 2, 9, 5, 4);

for (int trial = 0; trial < 20; trial++) {
    List<Integer> candidate = new ArrayList<>(original);
    Collections.shuffle(candidate, new Random(20261118L + trial));

    long expected = 0;
    for (int n : candidate) {
        expected += n;
    }

    long actual = candidate.parallelStream()
            .mapToLong(Integer::longValue)
            .sum();

    if (expected != actual) {
        throw new AssertionError("Mismatch at trial " + trial);
    }
}
~~~

A fixed seed lets you reproduce inputs when a bug is found. Still, shuffle tests **do not replace** identity and associativity contract checks, and repeating runs does not prove the absence of data races under all conditions.

## 16. Writing tests with JUnit 5

If the project uses JUnit 5, tests should compare against an oracle, try multiple split shapes, and include boundary inputs. The example below builds on `CollectorMergeDemo` from section 4 (place test code in the same package scope or adjust visibility):

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;

import java.math.BigInteger;
import java.util.List;
import org.junit.jupiter.api.Test;

class CollectorMergeDemoTest {
    @Test
    void bothExecutionModesMatchIndependentOracle() {
        List<CollectorMergeDemo.Sale> sales = List.of(
                new CollectorMergeDemo.Sale("A", 1_200),
                new CollectorMergeDemo.Sale("B", -200),
                new CollectorMergeDemo.Sale("C", 500),
                new CollectorMergeDemo.Sale("D", 700)
        );

        CollectorMergeDemo.Summary expected =
                new CollectorMergeDemo.Summary(
                        4, BigInteger.valueOf(2_200)
                );

        assertEquals(expected,
                sales.stream().collect(CollectorMergeDemo.collector()));
        assertEquals(expected,
                sales.parallelStream().collect(CollectorMergeDemo.collector()));
    }

    @Test
    void twoPartitionMergeMatchesWholeInput() {
        List<CollectorMergeDemo.Sale> sales = List.of(
                new CollectorMergeDemo.Sale("A", 1_200),
                new CollectorMergeDemo.Sale("B", -200),
                new CollectorMergeDemo.Sale("C", 500)
        );

        CollectorChecks.verifyTwoPartitions(
                CollectorMergeDemo.collector(), sales);
    }

    @Test
    void emptyInputProducesZeroCountAndTotal() {
        List<CollectorMergeDemo.Sale> empty = List.of();
        var result = empty.parallelStream()
                .collect(CollectorMergeDemo.collector());

        assertEquals(0L, result.count());
        assertEquals(BigInteger.ZERO, result.totalCents());
    }
}
~~~

The first test confirms the expected values computed from the example; the second forces merging two states; the third verifies identity on empty input.

To make this a stronger test suite, add tests for 3 partitions and merge trees, duplicate-key errors, repeated parallel runs, and large boundary values. **Do not write tests that merely reuse the same buggy computation for both expected and actual.**

## 17. Analysis workflow when parallel results do not match

When `parallelStream().collect(customCollector)` returns anomalous results, use this checklist sequence:

1. **Start with small data and a clear oracle.** Record elements, order, and expected result.
2. **Check supplier.** Does each call create an independent state with the right empty values?
3. **Check accumulator.** Does one container receiving every element sequentially produce the right result?
4. **Check combiner directly.** Force creating two non-empty containers, merge them, and compare against the oracle.
5. **Check identity and three partitions.** Merge with an empty container; compare two different merge trees.
6. **Check finisher.** Does it round, convert types, drop state, return a mutable reference mutated later, or misuse `IDENTITY_FINISH`?
7. **Check characteristics.** Do `CONCURRENT`, `UNORDERED`, and `IDENTITY_FINISH` accurately reflect behavior?
8. **Check shared state and numeric precision.** Eliminate shared variables and overflow/rounding bugs.
9. **Test large sources, many partitions, and repeated runs.** Only benchmark performance once correctness holds.

~~~text
Parallel result wrong?
       |
       v
Does sequential match oracle?
   |-- No --> check supplier / accumulator / finisher
   |
   v
Does manual two-container merge work?
   |-- No --> check combiner, lost / duplicated data
   |
   v
Do merging with empty and changing 3-partition trees work?
   |-- No --> identity / associativity / rounding
   |
   v
Is a single container shared or CONCURRENT misdeclared?
   |-- Yes --> fix structure and concurrency contract
   |
   v
Compare per result contract (ordering, arithmetic, error threshold)
       |
       v
Rerun edge cases and oracle; only then measure performance
~~~

## 18. Self-check exercises (with answers)

### Exercise 1. Shared supplier

**Prompt:** Why is `() -> sharedList` a wrong supplier for a normal Collector if `sharedList` is a reused mutable `ArrayList`?

**Answer:** Every container is supposed to be independent. When two branches use the same list, `accumulator` calls can write concurrently and `combiner` may merge a list into itself. Use `ArrayList::new` so each supplier call creates a separate list.

### Exercise 2. Combiner dropping data

~~~java
Collector<Integer, int[], Integer> c = Collector.of(
        () -> new int[1],
        (a, n) -> a[0] += n,
        (left, right) -> left,
        a -> a[0]
);
~~~

**Prompt:** Given two parts `[1, 2]` and `[3, 4]`, what is the result of manual merging?

**Answer:** `left = 3`, `right = 7`. The combiner only returns `left`, so the result is `3` instead of the sum `10`. Fix to `left[0] += right[0]; return left;`.

### Exercise 3. Associativity and order

**Prompt:** Does a Collector concatenating lists via `left.addAll(right)` need to satisfy `combine(left, right) == combine(right, left)`?

**Answer:** No. It needs to preserve order when re-parenthesized: `(A+B)+C` and `A+(B+C)` both equal `A+B+C`. Concatenating `B+A` can alter encounter order. Commutativity is not a general requirement for every Collector.

### Exercise 4. Finisher and IDENTITY_FINISH

**Prompt:** A Collector gathers an `ArrayList` and uses `List.copyOf` to return a structurally unmodifiable list. Should `IDENTITY_FINISH` be declared?

**Answer:** No. The finisher genuinely changes the type/contract of the result, from a mutable list to a structurally unmodifiable list. `IDENTITY_FINISH` could cause the finisher to be skipped.

### Exercise 5. Average of two groups

**Prompt:** Groups `A = [10, 20]` and `B = [100]`. If the combiner takes the average of the two group averages, how is the result wrong?

**Answer:** It yields `57.5`, whereas the overall average is `130/3 ≈ 43.3333`. Merge **sum** and **count**, then divide in the finisher.

### Exercise 6. Collector and overflow

**Prompt:** An `int`-summing Collector has the proper combiner `Integer::sum`, yet the true sum exceeds `Integer.MAX_VALUE`. Is a test checking only that sequential equals parallel sufficient?

**Answer:** No. Both can overflow identically under `int` arithmetic. You need a `long`/`BigInteger` oracle and numeric-range checks before claiming the business result is correct.

### Exercise 7. Concurrent collector

**Prompt:** Can you use `HashMap` and unsynchronized `HashMap::merge` and simply declare `CONCURRENT`?

**Answer:** No. If multiple threads call accumulator concurrently on one container, `HashMap` is not thread-safe. Use a standard concurrent collector like `toConcurrentMap` or build a genuinely thread-safe structure with the appropriate contract.

### Exercise 8. Testing the empty case

**Prompt:** Why does an empty source need its own test?

**Answer:** An empty source tests whether the supplier initializes properly and the finisher handles unaccumulated state. It catches bugs like `count = 1`, invalid default `min`, or division by zero when averaging.

### Exercise 9. Ordered source

**Prompt:** Data `[A, B, C, D]` needs an ordered List result. What risk does a combiner returning `right.addAll(left)` carry?

**Answer:** When partitioned, it can place a later group before an earlier group. The result can become `[C, D, A, B]`, violating encounter-order requirements. Use `left.addAll(right)` in the order the combiner receives the parts.

### Exercise 10. Choosing the right verification check

**Prompt:** A Collector aggregates total cents per key `BOOK` and `PEN`. How should the result be verified?

**Answer:** Check the exact same key set, the sum for **each key**, the grand total across groups, and total record count if counts are tracked. Do not rely on `Map` print order. For large monetary values, use a numeric type with sufficient range or `BigInteger`.

---

**Takeaway:** A `Collector` is only trustworthy when **supplier creates independent empty states, accumulator inserts data into the right container, combiner preserves identity and associativity, finisher returns results per contract, and characteristics accurately reflect behavior**. Proactively merge **two and three** intermediate states, compare against an independent oracle, and test empty sources, ordering, overflow, and duplicate data. A passing sequential run or a single successful parallel run is not enough to prove a Collector will always be right when the Stream splits work differently.

