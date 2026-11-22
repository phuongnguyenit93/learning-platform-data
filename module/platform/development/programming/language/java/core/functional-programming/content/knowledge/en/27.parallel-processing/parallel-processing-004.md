# Associativity, Non-Interference, and No Shared Mutable State When Using Parallel Stream in Java

## 1. Why must you follow these three principles?

Java Stream allows switching many sequential pipelines to parallel processing using `parallel()` or `parallelStream()`:

~~~java
int total = List.of(10, 20, 30, 40).parallelStream()
        .mapToInt(Integer::intValue)
        .sum();
~~~

For simple data, the result is `100`. However, merely adding `parallel()` does not make **all computations and side effects** safe. In a parallel pipeline, the Stream framework can split data into parts, run callbacks on different threads, and combine results. The exact execution path, task count, and callback order are not things a program should rely on.

The three core principles of this lesson:

1. **Associativity:** the partial combining operation must produce valid results when the framework changes how groups are split, e.g. integer addition fits; subtraction in general is not associative.
2. **Non-interference:** callbacks must not modify or cause changes to the data source currently being traversed by the Stream, unless the source and API have special rules allowing it.
3. **Stateless behavioral parameters (no shared mutable state):** `map`, `filter`, `reduce`, and other callbacks should depend on their inputs and stable data, not on shared counters or lists mutated by workers.

The three principles are related but distinct: a lambda may not modify the source yet still be unsafe because it increments a shared counter; a reduction may have no side effects yet produce different results between sequential and parallel because the operator is not associative; a properly associative addition can still break when the source is mutated during traversal.

**Objective:** after this lesson, you will know how to inspect a pipeline for associativity, identity/combiner validity, non-interference, and state dependencies; write `reduce`/`collect` properly; avoid race conditions; distinguish correctness from performance; and know when parallel execution is unnecessary.

Examples use **Java 17+**.

## 2. How parallel Stream execution works

### 2.1. A pipeline can be split and then combined

For summing `[10,20,30,40]`, the conceptual view:

~~~text
Source: [10, 20, 30, 40]
          |
       split work
       /        \
 [10, 20]     [30, 40]
     |             |
    30            70
       \          /
         combine
            |
           100
~~~

This is only a diagram to understand the principle, **not** a promise that the JVM splits into exactly two branches. The framework may use multiple levels of splitting, schedule tasks differently, and optimize the pipeline.

If the combining operation satisfies associativity along with a valid identity, how partitions are split does not change the mathematical result. If the combining operation is not associative, the result can depend on the reduction tree structure and become unpredictable.

### 2.2. Parallel does not mean callbacks run in source order

~~~java
IntStream.range(0, 6)
        .parallel()
        .forEach(System.out::println);
~~~

This is a snippet inside a method with `java.util.stream.IntStream` imported. **There is no fixed-order stdout** for `forEach` on a parallel Stream. Elements still belong to `0..5`, but print statements are side effects that may occur on multiple threads.

If you only need to compute a result, use a terminal operation that supports reduction/collection:

~~~java
List<Integer> numbers = IntStream.range(0, 6)
        .parallel()
        .boxed()
        .toList(); // [0, 1, 2, 3, 4, 5]
~~~

The `range` source has encounter order, and `toList()` collects in that order. The ordered nature of the resulting list **does not mean** callbacks in earlier stages ran sequentially.

### 2.3. Do not use parallel to mask algorithmic bugs

If a pipeline violates data rules, running sequentially might accidentally yield the expected result because callbacks are invoked in an easily observable order; running in parallel exposes the bug. The fix is to **change the operation's contract or remove shared mutable state**, not to fix the thread count, add `sleep`, or lock the entire program to "force order" without fixing the design.

## 3. Associativity: definition and examples

### 3.1. Mathematical definition

A binary operation `⊕` is **associative** if:

~~~text
(a ⊕ b) ⊕ c = a ⊕ (b ⊕ c)
~~~

for all `a`, `b`, `c` in the domain where the operation is defined.

For example, integer addition under Java `int` semantics is associative modulo 2^32 (though the result may overflow relative to the intended mathematical value). `Integer::sum` is suitable when the problem permits it or numeric bounds are controlled. String concatenation is associative in content:

~~~text
("A" + "B") + "C" = "A" + ("B" + "C") = "ABC"
~~~

**Associativity does not mean commutativity:** `"A" + "B"` differs from `"B" + "A"`, yet string concatenation is still associative. For an ordered Stream, a valid reduction must still respect encounter order per the applicable contract.

### 3.2. Subtraction is not associative

~~~text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
~~~

Two groupings produce different results. Therefore, do not use subtraction as an arbitrary combining operation in parallel reduction:

~~~java
int result = IntStream.of(1, 2, 3, 4)
        .parallel()
        .reduce(0, (a, b) -> a - b);
~~~

This is an **anti-pattern example**. Do not write a specific stdout or expect the result to always equal left-to-right sequential reduction, because the combiner does not satisfy associativity and identity requirements. Even if sequential execution yields a predictable value, that does not validate using that operator when the framework splits groups.

### 3.3. Division, stateful comparisons, and time-based concatenation

Integer division is also not associative. Functions using invocation timestamps, uncontrolled random numbers, or global state can yield different results depending on scheduling, even when written like a binary operator.

When an operation is not associative yet the problem demands strict order (such as consecutive subtraction), use a **sequential pipeline and explicit ordering**, or transform the algorithm into an equivalent associative combination if one exists.

### 3.4. Floating-point: consider numerical stability

In mathematics, real-number addition is associative. However, IEEE 754 `double`/`float` involves rounding, so `(a+b)+c` can differ from `a+(b+c)` at the bit level. Thus, do not promise bit-for-bit identical floating-point reduction results across all partition groupings.

Example in machine arithmetic:

~~~text
a = 1e16
b = -1e16
c = 1.0

(a + b) + c  --> 1.0
a + (b + c)  --> 0.0 (due to rounding b + c)
~~~

Define tolerance, precision, reproducibility, and evaluation order according to requirements. For money, prefer an appropriate exact numeric model such as `BigDecimal` and explicit rounding rules rather than assuming parallel `double` addition is exact mathematical arithmetic.

## 4. Identity and `reduce` must be compatible with the combiner

### 4.1. Reduction with a valid identity

~~~java
int sum = IntStream.rangeClosed(1, 10)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(sum); // 55
~~~

The identity for addition is `0` because `0 + x = x` and `x + 0 = x`. `Integer::sum` is a combining operation with the same semantics on every branch. This is an appropriate example for parallel reduction, provided the numeric range fits.

### 4.2. Identity is not an arbitrary initial value

Error-prone example:

~~~java
int result = IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(10, Integer::sum);
~~~

`10` is **not** an identity for addition. It can be injected into multiple reduction branches, making the result depend on how partitions are split. If you want to add `10` exactly once, separate the step:

~~~java
int result = 10 + IntStream.rangeClosed(1, 4)
        .parallel()
        .reduce(0, Integer::sum);

System.out.println(result); // 20
~~~

Do not rely on an accidental result of the first anti-pattern to conclude it is correct across all runs.

### 4.3. `reduce(identity, accumulator, combiner)`

`Stream<T>` has the overload:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner)
~~~

This is a **simplified library method signature**, not a method to write yourself. `accumulator` folds an element `T` into a partial result of type `U`, while `combiner` merges two `U` values. Compatibility and associativity must hold per the `reduce` contract. One key condition takes the form:

~~~text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
~~~

in terms of expected result semantics. This illustrates the combiner/accumulator compatibility law, not reference comparison via `==` for arbitrary objects.

Valid example:

~~~java
int total = Stream.of(10, 20, 30, 40)
        .parallel()
        .reduce(
                0,
                Integer::sum,
                Integer::sum
        );
System.out.println(total); // 100
~~~

`0` is the identity, and `Integer::sum` for accumulator/combiner has the same associative semantics without storing shared state.

### 4.4. Anti-pattern: combiner doing something different from accumulator

~~~java
int wrong = Stream.of(1, 2, 3, 4)
        .parallel()
        .reduce(
                0,
                Integer::sum,
                (left, right) -> left - right
        );
~~~

**Do not use:** the accumulator adds while the combiner subtracts, violating compatibility. Results can depend on partitioning and differ from sequential execution. Do not "test on one dataset" and rely on a current implementation's grouping to defend this code.

### 4.5. Do not use a mutable identity in `reduce`

Common mistake:

~~~java
// Avoid: using the same mutable StringBuilder as the identity.
StringBuilder result = Stream.of("A", "B", "C")
        .parallel()
        .reduce(
                new StringBuilder(),
                StringBuilder::append,
                StringBuilder::append
        );
~~~

The overloads of `reduce` are not designed to take a mutable identity and have the accumulator mutate that same object. It can share references across branches, violate identity/combiner requirements, produce wrong results, or cause unpredictable behavior. The right way to collect a `String` is `Collectors.joining()`; to collect a List, use `collect(...)` or `toList()`. With immutable data or fresh values from each accumulator call, `reduce` can be appropriate.

## 5. Non-interference

### 5.1. Stream traverses the source; callbacks must not modify it

**Wrong** example:

~~~java
List<Integer> source = new ArrayList<>(
        List.of(1, 2, 3, 4));

source.parallelStream()
        .forEach(n -> source.add(n * 10));
~~~

The snippet above attempts to modify the `ArrayList` currently being traversed by the Stream. This is **source interference**. Depending on timing, it can throw `ConcurrentModificationException`, lose data, produce abnormal results, or cause undefined behavior per contract. You cannot rely on always getting an exception to detect the bug, and you should not run this in systems with important data.

Even in a sequential pipeline, a callback interfering with an `ArrayList` source during traversal is invalid under Stream API constraints. Parallelism only makes the resulting races more complex.

### 5.2. Do not mutate the source in `filter`/`map`/`peek`

Another anti-pattern example:

~~~java
List<String> names = new ArrayList<>(
        List.of("An", "Binh"));

List<String> result = names.parallelStream()
        .map(name -> {
            names.remove(name); // Wrong: interfering with source.
            return name.toUpperCase();
        })
        .toList();
~~~

Similarly, adding/removing entries in a Map currently being traversed by a Stream, or modifying elements/keys in a way that alters source structure during pipeline evaluation, can violate the contract. `peek` is meant for observation/debugging, **not as a valid shortcut** to mutate the source or guarantee a side effect runs once.

### 5.3. Keep the source stable during execution

~~~java
List<Integer> source = List.of(1, 2, 3, 4);

List<Integer> transformed = source.parallelStream()
        .map(n -> n * 10)
        .toList();

System.out.println(transformed); // [10, 20, 30, 40]
~~~

`List.of` is unmodifiable and holds `Integer` (immutable), significantly reducing the risk of source interference. However, not every unmodifiable `List` guarantees that all **element objects** are immutable: if it holds mutable objects, they can still be updated through other references.

If the source is a mutable collection but processing needs a consistent snapshot, design the lifecycle: create a suitable structural copy when there are no uncontrolled concurrent updates, or coordinate locks/transactions at the boundary where the snapshot is taken per contract. Merely writing `new ArrayList<>(source)` **does not** by itself solve another thread concurrently mutating `source` during the copy.

### 5.4. Exceptions for concurrent sources

Some sources are designed for concurrent updates, such as concurrent collections with suitable spliterator characteristics. The Stream framework permits differences according to the source contract, but guarantees on snapshots, ordering, and visibility **must be read from the specific API**; do not assume every `Collection` is safe to mutate concurrently.

In typical application code, the safest advice remains: **do not modify the source while a stream is traversing it** unless the source and problem intentionally allow it and you accept the semantics documented in that source's Javadoc.

## 6. Stateless callbacks and shared mutable state

### 6.1. Pure lambdas do not depend on externally changing data

Suitable example:

~~~java
int multiplier = 10;

List<Integer> values = IntStream.rangeClosed(1, 5)
        .parallel()
        .map(n -> n * multiplier)
        .boxed()
        .toList();

System.out.println(values); // [10, 20, 30, 40, 50]
~~~

`multiplier` is effectively final locally. Each `map` execution only uses input `n` and a stable constant, without mutating shared state. The same input yields the same output under those conditions.

**Stateless does not mean a lambda is strictly forbidden from reading outer variables.** Reading a stable immutable configuration is completely different from updating a shared `counter` or reading state modified concurrently without a contract.

### 6.2. Shared `ArrayList` is an anti-pattern

~~~java
List<Integer> shared = new ArrayList<>();

IntStream.range(0, 1000)
        .parallel()
        .forEach(shared::add); // Wrong: ArrayList is not thread-safe.
~~~

Here the `IntStream.range` source is not mutated, but the result List **is shared state updated concurrently by tasks**. This can cause races, lost elements, or inconsistent state.

Replace with terminal collection:

~~~java
List<Integer> result = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .toList();
~~~

When a mutable List is needed after collection:

~~~java
List<Integer> result = IntStream.range(0, 1000)
        .parallel()
        .boxed()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

The Stream framework manages accumulation and combining per the collector contract, without requiring every thread to write to **the same external `ArrayList`**.

### 6.3. A shared counter is also stateful

~~~java
AtomicInteger counter = new AtomicInteger();

List<Integer> values = IntStream.range(0, 100)
        .parallel()
        .map(n -> {
            counter.incrementAndGet();
            return n * 2;
        })
        .boxed()
        .toList();
~~~

`AtomicInteger` makes the increment **atomic**, yet the lambda is still a **stateful behavioral parameter** and produces side effects. In Stream, some optimizations can skip unnecessary intermediate operations; callbacks should not be used as the sole source of truth for processing counts. `AtomicInteger` does not automatically turn a pipeline into a stateless design or guarantee invocation order.

If the goal is element count, use:

~~~java
long count = IntStream.range(0, 100)
        .parallel()
        .count(); // 100
~~~

If the goal is summing, use `sum()` or a valid `reduce`. If the goal is numbering in encounter order, use indices from an ordered source, such as `IntStream.range(0, size)`, instead of a counter contended across threads.

### 6.4. "Thread-safe" does not mean "suitable for Stream"

Replacing `ArrayList` with `Collections.synchronizedList(...)` or `ConcurrentLinkedQueue` may reduce certain races, but does not automatically guarantee encounter order, fix non-associative combining logic, or eliminate unwanted side effects. A pipeline relying on callbacks running in an exact order can still be wrong even if the storage collection is synchronized.

**Prefer collecting results with `collect`/`toList` and expressing operations as reductions**, rather than passing a concurrent container into callbacks to coordinate tasks manually.

## 7. `collect` has a mutable accumulator: why is it still safe?

### 7.1. Framework-coordinated mutation differs from arbitrary shared mutation

A collector can use an internal mutable container:

~~~java
List<String> result = Stream.of("A", "B", "C")
        .parallel()
        .collect(Collectors.toCollection(ArrayList::new));
~~~

`ArrayList` is not thread-safe if arbitrarily mutated concurrently by multiple threads, but `collect` has a supplier, accumulator, and combiner that let the framework coordinate containers/partial results per contract. The key is that **the container is managed by the Collector**, not written to by an independent lambda into an external shared List.

The collected result is a mutable `ArrayList`, but **do not infer it is safe when multiple threads write to it afterward**. Correctness of parallel collection and thread safety of the resulting object after collection are two separate issues.

### 7.2. A standard collector for grouped sums

~~~java
Map<String, Integer> totals = orders.parallelStream()
        .collect(Collectors.groupingBy(
                Order::team,
                TreeMap::new,
                Collectors.summingInt(Order::amount)));
~~~

This is a snippet inside a class with `record Order(String team, int amount) {}`, source `orders` of type `List<Order>`, and imports `Map`, `TreeMap`, `Collectors`. `groupingBy` groups elements, downstream `summingInt` sums amounts, and `TreeMap` ensures key order is deterministic when printed.

With data `("A",10),("B",20),("A",30),("B",40)`, the grouped Map is `{A=40, B=60}`. The Collector framework handles accumulation/combining; the author does not need a shared `HashMap` with unsynchronized `merge` inside `forEach`.

### 7.3. `groupingByConcurrent` is not a drop-in replacement

`Collectors.groupingByConcurrent` can help with concurrent collection in some pipelines, but it differs in ordering and collector characteristics. When a problem **must preserve the encounter order of elements within each group**, do not replace `groupingBy` with `groupingByConcurrent` and expect the same order. Read the collector contract and actual requirements.

A `toConcurrentMap` with duplicate keys must have an appropriate merge function; if the result must be correct when merged out of order, the merge function must also have suitable algebraic properties, usually requiring associativity and possibly commutativity if encounter order cannot be relied upon. Do not use merge logic that only works for one accidental order.

## 8. Standalone Java 17 program

The following example **has no shared side effects in the pipeline** and uses an unmodifiable `List.of` source. The reduction has a valid identity and addition operator; the grouping collector lets the framework handle accumulation.

Create the file **`ParallelRulesDemo.java`**:

~~~java
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

public class ParallelRulesDemo {

    record Order(String team, int amount) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("A", 10),
                new Order("B", 20),
                new Order("A", 30),
                new Order("B", 40)
        );

        int sequential = orders.stream()
                .mapToInt(Order::amount)
                .sum();

        int parallel = orders.parallelStream()
                .mapToInt(Order::amount)
                .sum();

        int reduced = orders.parallelStream()
                .map(Order::amount)
                .reduce(0, Integer::sum);

        Map<String, Integer> totals = orders.parallelStream()
                .collect(Collectors.groupingBy(
                        Order::team,
                        TreeMap::new,
                        Collectors.summingInt(Order::amount)));

        List<String> labels = orders.parallelStream()
                .map(o -> o.team() + ":" + o.amount())
                .toList();

        long evens = IntStream.rangeClosed(1, 10)
                .parallel()
                .filter(n -> n % 2 == 0)
                .count();

        System.out.println("sequential=" + sequential);
        System.out.println("parallel=" + parallel);
        System.out.println("reduced=" + reduced);
        System.out.println("byTeam=" + totals);
        System.out.println("labels=" + labels);
        System.out.println("evens=" + evens);
        System.out.println("sourceSize=" + orders.size());
    }
}
~~~

Compile and run on JDK 17+:

~~~bash
javac -encoding UTF-8 ParallelRulesDemo.java
java ParallelRulesDemo
~~~

**Exact stdout:**

~~~text
sequential=100
parallel=100
reduced=100
byTeam={A=40, B=60}
labels=[A:10, B:20, A:30, B:40]
evens=5
sourceSize=4
~~~

Explanation:

1. `sequential` and `parallel` both return `100` because both add four small integers in a safe range without modifying the source or updating shared state.
2. `reduced=100` uses `reduce(0,Integer::sum)`: identity `0` and associative addition are suitable for combining partial results.
3. `byTeam` has group A totaling 10+30=40 and group B totaling 20+40=60. `TreeMap` makes the printed key order `A` then `B` predictable.
4. `labels` uses a `map` callback depending only on each immutable `Order`; `List.of` has encounter order and `toList()` preserves order, even though callbacks may run on multiple threads.
5. In the inclusive range 1 to 10, there are 5 even numbers: `2,4,6,8,10`.
6. `sourceSize=4` confirms the pipeline did not interfere with the source structure; the source is an unmodifiable List containing records with only `String` and `int`.

The program does **not** print thread names or predict `parallel().forEach` order, because those are not guarantees to rely on for verifying results.

## 9. Analyzing bugs in real-world code

### 9.1. Counting with an invalid captured local variable

~~~java
int counter = 0;

// Does not compile: counter must be final/effectively final.
IntStream.range(0, 100).parallel()
        .forEach(n -> counter++);
~~~

Java does not allow lambdas to reassign captured local variables. Replacing with `AtomicInteger` makes the code compile and the increment atomic, but still creates a stateful behavioral parameter. When the requirement is simply counting elements, use `count()`.

### 9.2. Summing with a shared mutable array

~~~java
int[] total = {0};

IntStream.rangeClosed(1, 1000).parallel()
        .forEach(n -> total[0] += n);
~~~

This is an anti-pattern prone to **races**: updating `total[0]` is not atomic, so multiple threads can read stale values and overwrite each other. It can produce the wrong sum without necessarily throwing an error or exception.

Fix:

~~~java
int total = IntStream.rangeClosed(1, 1000)
        .parallel()
        .sum();

System.out.println(total); // 500500
~~~

This is a standard reduction. If the sum exceeds `int`, switch to `mapToLong` or `LongStream`/an appropriate numeric type; running in parallel does not prevent overflow.

### 9.3. Depending on callback order

~~~java
List<String> messages = List.of("first", "second", "third");

messages.parallelStream()
        .map(String::toUpperCase)
        .forEach(System.out::println);
~~~

There is no fixed-order stdout. If displaying in exact encounter order is required, you can collect `toList()` and print sequentially or use `forEachOrdered`:

~~~java
messages.parallelStream()
        .map(String::toUpperCase)
        .forEachOrdered(System.out::println);
~~~

`forEachOrdered` guarantees action order according to the encounter order of an ordered Stream, but **does not make all external mutable logic thread-safe**, and the ordering requirement may limit parallel gains.

### 9.4. Reading a concurrently modified configuration variable

~~~java
class Config {
    volatile int multiplier = 2;
}
~~~

A lambda reading `config.multiplier` while another thread changes the value may use different values for different elements. `volatile` solves certain visibility issues but **does not make the configuration immutable**, nor does it make the callback stateless. If all elements in a pass must use the same configuration, capture **a consistent configuration snapshot before starting** and capture an immutable value.

### 9.5. Mutating element objects can also cause interference

~~~java
record User(String name, List<String> tags) {}
~~~

The record holds a reference to `tags`; if that list is mutable and one callback modifies `tags` while another reads the same list, races can occur and results depend on timing. Records only make reference fields `final`; they do not automatically make referenced objects deeply immutable.

How to reduce risk: build an immutable model at the data level being read, e.g. creating `List.copyOf(tags)` when constructing the object (after ensuring data is non-null and has no uncontrolled concurrent updates), or separate mutation steps from the pipeline.

## 10. Is associativity always commutativity?

**No.** You must distinguish:

- **Associative:** changing parenthesization does not change the result.
- **Commutative:** swapping two arguments does not change the result.
- **Identity:** there is a neutral element that does not change the result when combined.

For example, string concatenation is **associative** with identity `""`, but not commutative:

~~~text
"A" + "B" = "AB"
"B" + "A" = "BA"
~~~

With an ordered Stream and a contract-compliant reduction, you can expect element order per encounter order in the result. However, if you switch the pipeline to `unordered()` or use a collector with `UNORDERED`/`CONCURRENT` characteristics, you cannot rely on the same order for position-sensitive combining.

For small integer sums, addition is both associative and commutative under Java's modular addition semantics. However, **do not conclude that commutativity alone is enough**: the combiner must still be compatible with the accumulator, the identity must be valid, and callbacks must remain non-interfering without shared mutable state.

## 11. Parallel Stream is not automatically faster

Parallel Stream has overhead:

- Splitting the source into spliterator partitions and distributing work.
- Creating/coordinating tasks and merging partial results.
- Synchronization or encounter-order preservation costs, especially in stateful operations like `sorted`, `distinct`, `limit`.
- Contention for CPU, memory bandwidth, and resources with other tasks.
- Timing depends on source size, element independence, and computation per element.

For a very small list or a simple lambda `n -> n + 1`, running in parallel can be **slower** than sequential. If the source involves blocking I/O operations, parallel Stream is not by default the best concurrency model; you need to control pools, concurrency limits, timeouts, and error policies per problem.

Do not use performance as an excuse to break associativity/non-interference/statelessness principles. Write a correct sequential version first, compare results on real data, and benchmark with meaningful metrics if parallel execution is genuinely needed.

## 12. Quick classification table

| Expression/behavior | Assessment in parallel | Reason |
| --- | --- | --- |
| `map(n -> n * 2)` on immutable data | Suitable | Does not modify source, stateless |
| `filter(n -> n > 0)` | Suitable | Predicate depends only on input |
| `reduce(0, Integer::sum)` | Suitable if overflow semantics are acceptable | Valid identity and associative addition |
| `reduce(0, (a,b) -> a-b)` | Wrong for general parallel reduction | Non-associative / unsuitable identity |
| `reduce(10, Integer::sum)` | Wrong for intent "add 10 once" | `10` is not the identity |
| `parallel().forEach(sharedArrayList::add)` | Unsafe | Shared mutable state, race |
| `parallel().boxed().toList()` | Suitable | Framework collects per contract |
| `map(x -> { source.add(x); return x; })` | Invalid | Interferes with source being traversed |
| `map(x -> counter.getAndIncrement() + ":" + x)` | State-dependent | Atomic counter does not guarantee encounter order |
| `collect(groupingBy(key, summingInt(value)))` | Suitable per collector contract | Accumulator/combiner managed by framework |
| `peek(x -> sendEmail(x))` | Not a safe way to design business actions | Side effects, optimizations, retries, errors, and invocation count |
| `parallel().forEachOrdered(action)` | Preserves action order per contract | Not a fix for all state races |

## 13. Checklist for inspecting a pipeline before calling `parallel()`

1. **What is the source?** `List`, array, `HashSet`, file, database stream, or concurrent source? Does it have encounter order?
2. **During execution, is the source modified?** Do callbacks, other threads, or external APIs mutate the source? If so, review non-interference and the source contract.
3. **Are callbacks stateful?** Do they read/write `AtomicInteger`, `ArrayList`, `HashMap`, mutable fields, shared random, clock, or object state?
4. **Is the reduction associative?** Does changing grouping change the result? Check subtraction/division/floating point/rounding.
5. **Is the identity truly neutral?** `0` for sum, `1` for multiplication, `""` for string concatenation; do not use arbitrary "initial" values.
6. **Are accumulator and combiner compatible?** For 3-argument `reduce`, both steps must produce the same semantic result.
7. **Is there a mutable identity in `reduce`?** If so, switch to a contract-compliant `collect` or produce immutable values.
8. **Do you want result order or side-effect order?** `toList` and `forEach` have different guarantees; use `forEachOrdered` when business logic requires it.
9. **Is the collector designed for parallel collection?** Prefer built-in collectors and read characteristics of custom collectors.
10. **Does the result need to be thread-safe after collection?** Safe collection does not automatically make the returned List/Map concurrent-safe.
11. **Is high precision required for `double` sums?** Check rounding error, arithmetic, and rounding policy.
12. **Is it actually faster?** Measure metrics and compare with sequential under realistic load.

## 14. Practice exercises

### Exercise 1 — Distinguishing associative operations

Given three operations `a+b`, `a-b`, `a*b` on suitable integers. Try three values `a=10`, `b=3`, `c=2`; compute `(a op b) op c` and `a op (b op c)`. Explain why subtraction is invalid as a combiner for parallel reduction, and why addition's identity differs from multiplication's identity.

### Exercise 2 — Testing identity

Write `IntStream.rangeClosed(1,4).parallel().reduce(0,Integer::sum)` and predict `10`. Then analyze why using identity `10` does not mean "add 10 once", and fix it by adding `10` **after** a reduction with identity `0`.

### Exercise 3 — Refactoring shared ArrayList

Given `List<Integer> result = new ArrayList<>(); IntStream.range(0,1000).parallel().forEach(result::add);`. Convert to `boxed().toList()`. If a mutable List is required, write `collect(Collectors.toCollection(ArrayList::new))`. Explain the difference between thread safety of the result object and proper framework data collection.

### Exercise 4 — Non-interference with source

Create an `ArrayList<String>` and write a pipeline that only does `filter`/`map` without modifying the source. Compare with the anti-pattern having `source.remove(...)` inside `map`. Explain why `ConcurrentModificationException` cannot always be relied on to detect every interference.

### Exercise 5 — Grouped sums

With source record `Order(team, amount)` as in section 8's program, write `parallelStream().collect(groupingBy(Order::team,TreeMap::new,summingInt(Order::amount)))`. Result `{A=40,B=60}` in key order when printing `TreeMap`. Do not create a shared mutable `HashMap` and call `put` in `parallel().forEach`.

### Exercise 6 — Side effects and encounter order

Use `IntStream.range(0,10).parallel().forEach(System.out::println)`; explain why printed lines may be out of order. Try `forEachOrdered` and compare. Explain why `forEachOrdered` does not make every shared structure thread-safe.

### Exercise 7 — Floating-point sum

Find a triple of `double` numbers where `(a+b)+c` differs from `a+(b+c)` due to rounding. Compare sequential and parallel reduction over many elements; **do not** write a test requiring the two results to be bitwise equal under all conditions. Propose a tolerance strategy or exact numeric types if business logic requires reproducibility.

### Exercise 8 — Atomic is not enough

Write a pipeline using `AtomicInteger.getAndIncrement()` as a sequence number for elements in `parallel().map(...)`. Explain why the increment is atomic yet not guaranteed to match encounter order. Replace with `IntStream.range(0, list.size()).mapToObj(i -> i+":"+list.get(i))` if the list is stable and has efficient random access.

### Exercise 9 — Custom comparator/collector

Design a per-key aggregation needing a `long` sum result, using `summingLong` or `toMap` with merge `Long::sum`. Check identity/associativity, overflow, and the Map type needed for output order. Do not replace with subtraction merge or side-effecting methods.

### Exercise 10 — Building a checklist for real code

Pick one of your pipelines that uses `parallelStream()`. Note its source, ordering, callbacks, state regions read/written, reduction/collector, identity, exception policy, and output data. Mark which conditions need fixing before running in parallel. If there is no significant benefit, explain why keeping it sequential is the reasonable decision.

## 15. Self-check quiz

**1. What is associativity?** Changing the grouping of combining operations does not change the result in the semantics that must be preserved.

**2. Can subtraction be used as an arbitrary parallel binary reduction?** No, subtraction is not associative.

**3. Is the identity of addition 10 if you want to add 10 to the sum?** No; the identity is 0, so add 10 after the reduction.

**4. Why should you not use a shared `StringBuilder` as the identity in `reduce`?** Because the accumulator mutates the identity, violating the reduction contract and potentially sharing the object across branches.

**5. What does non-interference mean?** Behavioral parameters do not cause modifications to the source being traversed by the Stream in violation of the source contract.

**6. Is it safe to not modify the source while writing to a shared `ArrayList`?** No; there is still a race due to the shared mutable result.

**7. Can a lambda read immutable configuration?** Yes, if the captured data is stable and the callback has no state that changes between elements.

**8. Does `AtomicInteger` automatically make a lambda stateless?** No; it only provides certain atomic operations on shared state.

**9. Do you need to synchronize an external `ArrayList` manually to replace `collect`?** No; use `collect`/`toList` under the appropriate contract.

**10. Does Parallel Stream guarantee `forEach` follows encounter order?** No. `forEachOrdered` is for action ordering requirements.

**11. Is a List returned by parallel `collect` automatically thread-safe?** No, that is a separate question about the resulting object.

**12. Is parallel always faster than sequential?** No; coordination, splitting, combining overhead, and workload determine performance.

## 16. Summary and references

**A correct parallel Stream requires stable source data, non-interfering callbacks that do not depend on shared mutable state, and a reduction with an associative combining operation and compatible identity/combiner.** These are the conditions under which the framework can split data and merge partial results while preserving semantics. Merely adding `parallel()` does not guarantee correct results and does not ensure performance gains.

Prefer pure `map`/`filter`, valid `sum`/`count`/`reduce`, and built-in collectors such as `toList`, `toCollection`, `groupingBy`/`summingInt`. Do not mutate the source in callbacks, do not manually update a shared `ArrayList` or counter, and do not use a mutable identity in `reduce`. When action order is needed, understand `forEachOrdered`; when computed results are needed, prefer reduction/collection over side effects. For `double`, precision and reproducibility are arithmetic requirements that must be evaluated separately.

**Official sources:** Java Stream package documentation (Non-interference, Stateless behaviors, Reduction, Ordering, Side-effects); Java SE 17 Javadoc for `java.util.stream.Stream`, `IntStream`, `java.util.stream.Collectors`, and `java.util.stream.Collector`; Java Language Specification on lambdas and capture rules. The JDK documentation emphasizes non-interfering/stateless behavioral parameters and the identity, associativity, and compatibility conditions when using reduction.