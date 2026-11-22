# Splitting Sources, Processing Partitions, and Combining Results in Java Parallel Stream

## 1. Divide-and-conquer thinking in parallel Streams

A parallel processing pipeline can split a source into **work partitions** (*partitions/tasks*), process each partition, and then combine the **local results** to produce the final result. This is the *divide and conquer* idea, yet the application does not need to manually create a Java thread for each element.

Conceptual model:

```text
                         Source [1,2,3,4,5,6,7,8]
                                     |
                               split source
                          /                       \
               [1,2,3,4]                         [5,6,7,8]
                 /    \                             /    \
              [1,2] [3,4]                       [5,6] [7,8]
                |     |                           |     |
             subtotal subtotal                 subtotal subtotal
                \     /                           \     /
               combine                           combine
                  \                                /
                   -------- final merge -----------
                               |
                             result
```

When the partitions use addition, the sum is `36`. What matters is not *which thread* each partition is assigned to, but that the transformation and combining rules **preserve the meaning of the result** regardless of how the framework splits the work into different partitions.

In Java, two simple ways to request a parallel pipeline:

```java
numbers.parallelStream()
       .mapToInt(Integer::intValue)
       .sum();
```

or:

```java
numbers.stream()
       .parallel()
       .mapToInt(Integer::intValue)
       .sum();
```

These are illustrative expressions inside a method with variable `numbers: List<Integer>` and import `List`. Both set parallel mode for the pipeline, but **do not force the framework to use a fixed number of threads or a fixed splitting strategy**.

Parallel streams are aimed at solving data-processing problems, not automatically turning every sequential algorithm into a fast and correct multithreaded one.

## 2. From source to result: four stages

A parallel aggregation can be understood in four steps:

1. **Source decomposition:** the framework takes a traversable/splittable source (usually via `Spliterator`) and creates subtasks when appropriate.
2. **Partition processing:** each task executes the corresponding pipeline stages (such as `filter`, `map`, `mapToInt`) on its assigned elements.
3. **Local accumulation:** each partition may produce a subtotal (`reduce`) or a temporary container (`collect`), depending on the algorithm.
4. **Combining:** local subtotals/containers are merged into the overall result according to an appropriate combiner rule.

Note: this is a **mental model**, not a guarantee that every terminal operation must execute these exact four steps with a fixed number of tasks, containers, and order. Optimizations, source size, stateful operations, short-circuiting, or collector structure can cause actual execution to differ.

For example, `stream.parallel().count()` can use the source's size characteristic to compute the result without processing each element. Therefore, do not use side effects in `peek`/`map` to count "how many tasks ran".

## 3. Spliterator: the source-splitting mechanism

`java.util.Spliterator<T>` combines the ability to **traverse elements** and **split work**. Key methods to know:

| API | Meaning |
| --- | --- |
| `tryAdvance(Consumer<? super T>)` | If an element remains, process one element |
| `forEachRemaining(Consumer<? super T>)` | Traverse the remaining elements |
| `trySplit()` | Attempt to split off a portion for independent processing; may return `null` |
| `estimateSize()` | Estimate the number of remaining elements |
| `characteristics()` | Return a bitmask of characteristic flags, e.g. `ORDERED`, `SIZED`, `SUBSIZED` |

Normally a Stream obtains a spliterator from a `Collection`, array, or provided source. Sources that split easily and have known sizes (such as `ArrayList`, arrays, numeric ranges) are generally more favorable than sequential sources that cannot be split efficiently.

**`trySplit()` has no contract to always split into two equal halves.** Many implementations return a *prefix* when there is an encounter order and leave the *remainder*, but partition sizes, number of splits, and conditions for returning `null` are decided by the spliterator.

Distinguish:

- `ORDERED`: has an element encounter order that must be respected by operations that require it.
- `SIZED`: knows the exact number of remaining elements per the source contract.
- `SUBSIZED`: spliterators produced after splitting also have the `SIZED` property.
- `SORTED` or `DISTINCT`: value/source properties that certain operations can leverage.

These flags are **not a switch that turns on parallelism**, but provide information for the framework to decide how to process and optimize.

## 4. Example: splitting a source with trySplit() and inspecting both parts

A visual example inside a method:

```java
List<Integer> values = IntStream.rangeClosed(1, 8).boxed().toList();
Spliterator<Integer> remainder = values.spliterator();
Spliterator<Integer> prefix = remainder.trySplit();

List<Integer> firstPart = StreamSupport.stream(prefix, false).toList();
List<Integer> secondPart = StreamSupport.stream(remainder, false).toList();
```

This illustrative snippet requires importing `java.util.*`, `java.util.stream.*`. With this specific List source in the tested Java 17 environment, `prefix` is `[1, 2, 3, 4]` and `remainder` is `[5, 6, 7, 8]`.

**This is an observed result of the example, not a rule that every `Spliterator` must split 4/4.** When calling `trySplit()` on a very small source or a different source type, the result may be `null`. Production code calling `trySplit` directly must check for null; the full example knows in advance that the List source has 8 elements and was tested on JDK 17.

To execute a partition from a spliterator using the Stream API, you can use `StreamSupport.stream(part, false)`. This call **consumes the provided spliterator**; do not reuse that object after it has been traversed.

Normally you **do not need to call `trySplit` manually**: `parallelStream()` pairs the Stream framework with the source spliterator to decide how to split.

## 5. Fork/Join and a non-fixed number of tasks

Parallel streams in Java are typically implemented using **Fork/Join** mechanisms (often involving `ForkJoinPool.commonPool()`). A task can split into smaller tasks (*fork*), and results are combined upon completion (*join*).

However, when writing:

```java
int total = IntStream.rangeClosed(1, 100).parallel().sum();
```

what you can rely on is the **aggregation semantics** for this small data, not "100 elements running on 100 threads". The framework may not create a task per element, and tasks do not necessarily run simultaneously.

Parallelism depends on source splittability, the number and weight of operations, core/resource availability, task creation/joining overhead, and ordering constraints. A pipeline declared parallel may also yield negligible benefit if the source is small or a stage has to wait on others.

**Do not predict log output order or thread count** from a single run: the scheduler and environment can vary. Avoid making business actions depend on thread names, task completion order, or how many times the combiner is called.

## 6. Combining values with reduce(identity, accumulator, combiner)

The three-parameter reduction method on `Stream<T>` has the conceptual signature:

```java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
```

This is an API signature for reading generics, not a standalone Java class.

Meaning:

- **`identity`**: the identity value or initial state suitable for each processing partition. For addition: `0`.
- **`accumulator`**: takes a subtotal of type `U` and an element of type `T`, producing a new subtotal of type `U`.
- **`combiner`**: merges two subtotals of type `U` from different partitions.

Example with `List<Integer>`:

```java
long sum = numbers.parallelStream()
        .reduce(0L,
                (subtotal, number) -> subtotal + number,
                Long::sum);
```

These illustrative statements require `numbers: List<Integer>`. `identity` has type `Long` via boxing, the accumulator folds an `Integer` element into a `Long` subtotal by addition, and the combiner adds two `Long` subtotals.

If the source partitions have sums `10` and `26`, combiner `Long::sum` yields `36`. With data `[1,2,3,4,5,6,7,8]`, the test program returns `36`.

By contract, parallel reduction requires combining functions to be **associative**, have a valid identity, and have `combiner` **compatible** with `accumulator`. Simply passing a combiner argument does not make arbitrary lambdas safe for parallel execution.

## 7. Why is associativity the decisive condition?

An operation `op` is associative when:

```text
op(op(a,b),c) == op(a,op(b,c))
```

Integer addition within a non-overflowing range generally satisfies this; `max`, `min`, set union, or properly ordered list concatenation can also be constructed to be associative.

**Subtraction is not associative:**

```text
(10 - 3) - 2 = 5
10 - (3 - 2) = 9
```

Because the results differ, using something like `reduce(0,(a,b)->a-b)` and expecting the exact same result across all work-splitting strategies is a design error.

In practice, parallel reduction may group partitions according to a reduction tree different from left-to-right sequential evaluation. Even if one run prints the "right" result, that does not prove the reducer is semantically safe.

**Associativity is different from commutativity.** String concatenation can be associative without being commutative: `"A"+"B"` differs from `"B"+"A"`. If the output needs encounter order, you must choose an API/collector with a suitable order-preserving contract; do not assume string concatenation is safe with arbitrary unordered or concurrent collectors.

**Floating-point `double`:** floating-point addition involves rounding, so it is not strictly associative in machine representation; a parallel sum can show slight low-order digit differences depending on grouping order. If exact money/numbers are needed, consider `BigDecimal`, exact numeric types, and appropriate algorithms.

## 8. Identity and the accumulator/combiner compatibility rule

`identity` is not merely "any arbitrary starting value". For addition, `0` is the identity because `0 + x = x`. For multiplication, `1` is the identity because `1 * x = x`.

**Semantically wrong** snippet:

```java
int wrong = IntStream.of(1, 2, 3)
        .parallel()
        .reduce(10, Integer::sum);
```

This statement compiles inside a method with `IntStream` imported; however, `10` is **not an identity for addition**, because `10 + x != x`. Source partitions can each start from their own identity and be combined, so the result can differ from the intuition of "sum plus 10 once". Correct for summing is `reduce(0, Integer::sum)` or `sum()`.

For the three-argument overload, the Javadoc also requires **compatibility** between accumulator and combiner, of the form:

```text
combiner(u, accumulator(identity, t)) == accumulator(u, t)
```

on valid contract inputs; this allows merging each partition's result without altering the overall computation.

Valid example: `identity=0L`, `accumulator=(subtotal,n)->subtotal+n`, `combiner=Long::sum`. All describe the same addition operation.

Wrong example: the accumulator adds scores while the combiner **multiplies** two subtotals; the result is incompatible and depends on how many partitions were split. No automatic exception reports "semantically wrong combiner"; the code can run and silently produce wrong data.

## 9. How does reduce() differ from collect()?

`reduce` is suitable when the result is a **value** with an appropriate associative operation, such as sum, product, min/max, `BigInteger`, or a well-designed immutable summary type.

`collect` is suitable when the result is a **container that can be mutated** during accumulation, such as `List`, `Set`, `Map`, `StringBuilder`, or statistics objects with accumulation methods.

| Topic | reduce() | collect() |
| --- | --- | --- |
| Typical result | Aggregated value, new subtotal | Container with elements added |
| Accumulation | Returns a new value `U` | Usually mutates a **local container** |
| Merging partitions | `combiner(U,U) -> U` | Combines local containers |
| Typical pattern | `reduce(0,Integer::sum)` | `collect(Collectors.toList())`, `groupingBy` |
| Pitfall | Wrong identity/associativity | Shared mutable state or wrong combiner |

**Do not use `reduce` with a mutable `ArrayList` as the identity and mutate it inside the accumulator**. The reduction identity may be shared across multiple computation branches; doing so violates the non-interfering reduction model and can lead to races, lost data, or duplicated data.

To build a list in a parallel stream, use `toList()` or a properly designed `Collector`.

## 10. Collector: supplier, accumulator, combiner, finisher

A `Collector<T,A,R>` describes how to transform elements of type `T` into a result `R` via an intermediate accumulation container of type `A`:

- **supplier**: creates a new empty container for the partition being processed.
- **accumulator**: adds an element `T` into that partition's container `A`.
- **combiner**: merges **two `A` containers** into one; essential when there are multiple local partitions.
- **finisher** (if present): converts the temporary state `A` into the final result `R`.
- **characteristics**: declares properties such as `CONCURRENT`, `UNORDERED`, `IDENTITY_FINISH`, if genuinely true per contract.

Simple diagram:

```text
Branch 1: supplier() -> [] -> accumulate("A") -> ["A"]
                              accumulate("B") -> ["A","B"]

Branch 2: supplier() -> [] -> accumulate("C") -> ["C"]
                              accumulate("D") -> ["C","D"]

combiner(["A","B"], ["C","D"]) -> ["A","B","C","D"]
finisher(...) (if any) -> desired result
```

This is a **conceptual illustration**, not a promise that the framework will split into exactly two parts or call the combiner only once.

The key point of a regular collector is that **each local container belongs to its own accumulation stream**, so inside the accumulator you can add elements to a private `ArrayList` without multiple tasks concurrently modifying the same list.

## 11. Writing a custom Collector for List

Illustrative method snippet (used inside a class with imports `java.util.*`, `java.util.stream.*`):

```java
static Collector<String, ArrayList<String>, ArrayList<String>> listCollector() {
    return Collector.of(
            ArrayList::new,
            ArrayList::add,
            (left, right) -> {
                left.addAll(right);
                return left;
            });
}
```

Here `ArrayList::new` is the **supplier**, `ArrayList::add` is the **accumulator**, and the lambda merging two lists is the **combiner**.

Even though `ArrayList` is not thread-safe for concurrent writes to **the same instance**, this collector can be used safely in a parallel stream because the framework manages local containers and combines them under the contract of a **non-concurrent** collector. It does **not** share a single pre-created `ArrayList` object across all branches.

```java
List<String> words = List.of("A", "B", "C", "D");
List<String> output = words.parallelStream().collect(listCollector());
```

When the collector does not declare `UNORDERED` and the input has encounter order, the collection result preserves order per contract. In the tested Java 17 example, `output = [A, B, C, D]`.

Do not "optimize" the supplier into `() -> sharedList` where `sharedList` is a shared variable; doing so breaks the local accumulation model and creates race risks.

## 12. Custom Collector with finisher: building a CSV string

If the temporary container is `StringBuilder` but the final desired value is `String`, use `Collector.of` with a finisher:

```java
static Collector<String, StringBuilder, String> csvCollector() {
    return Collector.of(
            StringBuilder::new,
            (builder, value) -> {
                if (builder.length() > 0) builder.append(",");
                builder.append(value);
            },
            (left, right) -> {
                if (left.length() > 0 && right.length() > 0) {
                    left.append(",");
                }
                left.append(right);
                return left;
            },
            StringBuilder::toString);
}
```

This is a method included in the complete Java example in section 14.

Understand the two comma checks:

- **accumulator** only appends a comma when the current container already has data;
- **combiner** only appends a comma when **both** parts are non-empty, then appends the right part to the left part.

With `["A","B","C","D"]`, the result is `A,B,C,D` in encounter order. The merge logic is designed so that splitting into 1, 2, or many branches does not introduce extra commas, provided the framework preserves partition order under an ordered collector contract.

`StringBuilder` is **not thread-safe** when two threads concurrently modify the same instance. However, that does not forbid using it as a **local container** in a non-concurrent collector. If you mistakenly mark it `CONCURRENT`, this safety argument no longer holds.

## 13. Standalone Java 17 example: Spliterator and reduce/collect

Create the file `ParallelSplitReduceDemo.java` with the full contents:

```java
import java.util.*;
import java.util.stream.*;

public class ParallelSplitReduceDemo {
    public static void main(String[] args) {
        List<Integer> data = IntStream.rangeClosed(1, 8).boxed().toList();

        Spliterator<Integer> remainder = data.spliterator();
        Spliterator<Integer> prefix = remainder.trySplit();
        List<Integer> left = StreamSupport.stream(prefix, false).toList();
        List<Integer> right = StreamSupport.stream(remainder, false).toList();
        System.out.println("prefix=" + left);
        System.out.println("remainder=" + right);
        System.out.println("covered=" + (left.size() + right.size()));

        int sequential = data.stream().mapToInt(Integer::intValue).sum();
        int parallel = data.parallelStream().mapToInt(Integer::intValue).sum();
        System.out.println("sequentialSum=" + sequential);
        System.out.println("parallelSum=" + parallel);

        long parallelThreeArg = data.parallelStream()
                .reduce(0L, (subtotal, n) -> subtotal + n, Long::sum);
        System.out.println("parallelThreeArg=" + parallelThreeArg);

        int sumSquares = data.parallelStream()
                .map(n -> n * n)
                .reduce(0, Integer::sum);
        System.out.println("sumSquares=" + sumSquares);

        Map<String, Integer> grouped = data.parallelStream()
                .collect(Collectors.groupingBy(
                        n -> n % 2 == 0 ? "even" : "odd",
                        TreeMap::new, Collectors.summingInt(Integer::intValue)));
        System.out.println("grouped=" + grouped);

        IntSummaryStatistics stats = data.parallelStream()
                .collect(Collectors.summarizingInt(Integer::intValue));
        System.out.println("stats=" + stats.getCount()
                + "/" + stats.getSum()
                + "/" + stats.getMin()
                + "/" + stats.getMax());

        List<Integer> transformed = data.parallelStream()
                .map(n -> n * 10).toList();
        System.out.println("orderedResult=" + transformed);

        List<Integer> observed = Collections.synchronizedList(new ArrayList<>());
        data.parallelStream().forEachOrdered(observed::add);
        System.out.println("orderedAction=" + observed);

        System.out.println("associative=" +
                ((10 - 3) - 2) + "/" + (10 - (3 - 2)));
    }
}
```

Compile and run:

```bash
javac --release 17 -encoding UTF-8 ParallelSplitReduceDemo.java
java ParallelSplitReduceDemo
```

Verified output in a Java 17 environment:

```text
prefix=[1, 2, 3, 4]
remainder=[5, 6, 7, 8]
covered=8
sequentialSum=36
parallelSum=36
parallelThreeArg=36
sumSquares=204
grouped={even=20, odd=16}
stats=8/36/1/8
orderedResult=[10, 20, 30, 40, 50, 60, 70, 80]
orderedAction=[1, 2, 3, 4, 5, 6, 7, 8]
associative=5/9
```

Explanation:

1. `Spliterator.trySplit()` in the example yields prefix and remainder, with a total element count of `8`. The split size is **not a promise for every source**.
2. `sequentialSum` and `parallelSum` are both `36`, accurate for small data and non-overflowing integer addition.
3. `parallelThreeArg=36` confirms three-parameter reduction with `identity=0L`, accumulator adding into `long`, and combiner `Long::sum`.
4. `sumSquares=204` confirms computing `n*n` per partition and combining by summing.
5. `grouped={even=20, odd=16}` is the **sum** of even/odd values, not the count of elements.
6. `stats=8/36/1/8` corresponds to `count/sum/min/max`.
7. `orderedResult` and `orderedAction` illustrate cases where the API requires encounter order to be preserved. That **does not mean `map` lambdas always run sequentially in order**.
8. `associative=5/9` illustrates that subtraction is not associative, not unstable output measured from a parallel reduction.

The program only uses the standard library, requiring no data files or network access.

## 14. Standalone Java 17 example: custom Collector and container merging

Create the file `ParallelCollectorDemo.java`:

```java
import java.util.*;
import java.util.stream.*;

public class ParallelCollectorDemo {
    static Collector<String, ArrayList<String>, ArrayList<String>> listCollector() {
        return Collector.of(
                ArrayList::new,
                ArrayList::add,
                (left, right) -> {
                    left.addAll(right);
                    return left;
                });
    }

    static Collector<String, StringBuilder, String> csvCollector() {
        return Collector.of(
                StringBuilder::new,
                (builder, value) -> {
                    if (builder.length() > 0) builder.append(",");
                    builder.append(value);
                },
                (left, right) -> {
                    if (left.length() > 0 && right.length() > 0) {
                        left.append(",");
                    }
                    left.append(right);
                    return left;
                },
                StringBuilder::toString);
    }

    public static void main(String[] args) {
        List<String> words = List.of("A", "B", "C", "D");
        List<String> result = words.parallelStream().collect(listCollector());
        System.out.println("list=" + result);
        System.out.println("csv=" + words.parallelStream().collect(csvCollector()));

        Map<String, Long> counts = words.parallelStream()
                .collect(Collectors.groupingBy(
                        s -> (s.equals("A") || s.equals("C")) ? "odd" : "even",
                        TreeMap::new, Collectors.counting()));
        System.out.println("counts=" + counts);

        Set<String> unique = Stream.of("A", "B", "A", "C")
                .parallel()
                .collect(Collectors.toCollection(TreeSet::new));
        System.out.println("sortedSet=" + unique);

        int all = IntStream.rangeClosed(1, 100)
                .parallel().sum();
        System.out.println("sum100=" + all);
    }
}
```

Test commands:

```bash
javac --release 17 -encoding UTF-8 ParallelCollectorDemo.java
java ParallelCollectorDemo
```

Output:

```text
list=[A, B, C, D]
csv=A,B,C,D
counts={even=2, odd=2}
sortedSet=[A, B, C]
sum100=5050
```

Key points:

- `listCollector` uses **supplier/accumulator/combiner** with local `ArrayList`s.
- `csvCollector` adds a **finisher** to return `String`, avoiding exposing a mutable `StringBuilder` to the caller.
- `groupingBy(..., TreeMap::new, counting())` illustrates grouping by key, merging, and producing a Map with sorted keys. `even=2`, `odd=2` are **element counts** in each group.
- `Collectors.toCollection(TreeSet::new)` creates a sorted set, resulting in `[A, B, C]`.
- `IntStream.rangeClosed(1,100).parallel().sum()` returns `5050`; `parallel` affects how it is computed, not the mathematical sum within the valid `int` range.

Do not try to count supplier/combiner calls using side effects to treat that as a fixed splitting structure. The number of calls depends on size, environment, and execution strategy.

## 15. Collecting results with standard collectors

Before writing a custom collector, check the standard library:

| Need | Usually appropriate API |
| --- | --- |
| Sum of integers | `mapToInt(...).sum()`, `Collectors.summingInt(...)` |
| Count elements | `count()`, `Collectors.counting()` |
| Collect into a list | `toList()`, `Collectors.toList()` |
| Collect into a set | `Collectors.toSet()`, `toCollection(TreeSet::new)` |
| Group by key | `Collectors.groupingBy(...)` |
| Collect into a Map with duplicate keys | `Collectors.toMap(key,value,merge)` |
| Group into multiple buckets with statistics | `groupingBy(..., downstreamCollector)` |
| Truly concurrent collector | Certain `toConcurrentMap`, `groupingByConcurrent` |

If you only need a statistical result, standard collectors are usually shorter and less risky than custom collectors. `groupingBy` is not concurrent by default; a parallel stream may create local maps and merge them. `groupingByConcurrent` has a different contract and can be `UNORDERED`, so ordering requirements must be considered.

**Do not confuse "a Map that can be used by multiple threads after creation" with "a collector that allows multiple threads to update one container concurrently during collection"**. A `CONCURRENT` collector has specific constraints; a `mapFactory` returning `ConcurrentHashMap` does not automatically make an arbitrary collector truly concurrent.

## 16. Encounter order: parallel does not mean chaotic

A `List` source has an encounter order. When calling:

```java
List<Integer> result = numbers.parallelStream()
        .map(n -> n * 10)
        .toList();
```

`result` preserves the corresponding encounter order of the source for this ordered pipeline; with `numbers = [1,2,3]` the result is `[10,20,30]`.

However, **the internal evaluation order** of `map` can differ from the source order; `toList()` gathers data in the requested order. Therefore, do not write:

```text
List<Integer> audit = new ArrayList<>();
numbers.parallelStream().map(n -> {
    audit.add(n);
    return n * 10;
}).toList();
```

This is a **bad-design counterexample**: concurrent writes to a shared `ArrayList` can cause races; moreover, side effects in a `map` stage should not be used for mandatory business logic.

When you genuinely want a **terminal operation** in encounter order, `forEachOrdered` has the appropriate contract:

```java
List<Integer> observed = Collections.synchronizedList(new ArrayList<>());
numbers.parallelStream().forEachOrdered(observed::add);
```

This illustrative snippet is in a method importing `List`, `Collections`, and `ArrayList`. `forEachOrdered` enforces action order according to encounter order on ordered streams, but may reduce parallel benefits. Use `forEach` when **order is not needed**; do not assume action invocation order.

## 17. Stateful operations and speed limits

Not every pipeline splits and merges efficiently. Operations that need to observe many elements or respect order can create barriers:

- `sorted()`: sorting typically needs to hold/evaluate many elements.
- `distinct()`: may need a state set of seen elements; ordered parallel can incur extra overhead.
- `limit()`, `skip()`: on ordered parallel streams, determining the exact prefix to keep/skip can be costly.
- `takeWhile()`, `dropWhile()`: on ordered sources, must determine the exact prefix boundary.
- `findFirst()`: must return the first element in encounter order, which may require coordination across branches.
- `findAny()`: when order is unnecessary, can be more flexible.

There is no rule that "`parallel()` is always faster by the number of cores". Speed depends on data volume, per-element processing cost, source splittability, coordination level, memory latency, combine cost, and runtime environment.

**Some cases where parallel runs slower:** data is too small; each element only performs a simple addition; source is hard to split; `sorted` followed by `findFirst` is needed; or the combiner/collector must copy large amounts of data.

Performance conclusions should only be made after **proper benchmarking** (e.g., JMH, warm-up, representative data), not by taking `System.currentTimeMillis()` of a single small run as proof.

## 18. Ordered sources and unordered sources

Sometimes you can drop the ordering constraint with `unordered()` if the problem **does not need order**. This can help some parallel pipelines optimize more easily. However, `unordered()` only **removes the encounter-order constraint**, and does not guarantee shuffling elements.

If the result must preserve event order, pick the first record, or build a string in exact order, do not arbitrarily call `unordered()`.

With a collector having the `UNORDERED` characteristic, the result may not preserve encounter order even if the source is a `List`. Conversely, a non-`UNORDERED`, properly written collector can merge partitions in a way that produces the right list order, as in the `listCollector` example.

**Result determinism** and **side-effect order** are two different things: `toList()` can return a properly ordered result even when threads ran `map` in a different order.

## 19. Why is a shared mutable accumulator a serious bug?

A common mistake is creating a mutable variable outside and letting multiple processing partitions modify it simultaneously:

```text
List<Integer> result = new ArrayList<>();
numbers.parallelStream().forEach(result::add);
```

This is a **warning snippet**, not recommended code. `ArrayList` is not safe when multiple threads write concurrently; results can lose elements, corrupt internal state, or exhibit hard-to-reproduce bugs.

Simple alternative:

```java
List<Integer> result = numbers.parallelStream().toList();
```

This is a statement in a method with `numbers: List<Integer>`. The framework is responsible for collecting the result; you do not share an external mutable `ArrayList`.

Even if you use `Collections.synchronizedList` to avoid races, the shared lock can become a bottleneck, and **the order of adding elements via `forEach` is still not the source order**. Using proper `collect` is usually more appropriate.

In particular, **do not use an `ArrayList` as the identity for `reduce` and call `acc.add(x)`**: reduction is not a replacement API for `collect` with mutable containers.

## 20. Correctness with exceptions or impure data

A lambda passed to a parallel stream should be:

- **Non-interfering**: do not modify the data source while the stream is processing it.
- **Stateless**: do not rely on shared mutable state that makes results depend on ordering or scheduling.
- **Thread-safe when necessary**: if state is genuinely used, know how to coordinate it; prefer avoiding state.
- **Clear error contract**: if one branch throws an exception, the terminal operation may fail; do not assume other branches have all completed or that all side effects were rolled back.

For example, actions like sending emails, writing to a database, or deducting money **should not be hidden inside `map` or `peek` of a pipeline** hoping "each element runs exactly once". Parallel streams do not provide transactions or exactly-once semantics for external systems.

If business logic must execute an action for every record, design an **explicit execution step** with error handling, retry/idempotency, and state tracking, rather than letting pipeline optimizations decide which actions get called.

## 21. Common mistakes and misconceptions

| Misconception | Why it is wrong | How to fix |
| --- | --- | --- |
| `parallel()` always uses one thread per element | Framework splits based on source/resources/cost | Do not depend on thread count or task size |
| `trySplit()` always splits in half and is never null | Contract allows different splitting strategies | Check for null, do not hardcode 50/50 parts |
| `reduce(10,Integer::sum)` adds 10 once | 10 is not the identity for addition | Use `identity=0` for sum |
| Subtraction is a suitable reducer for parallel | Not associative | Choose an associative combining operation |
| Accumulator adds while combiner multiplies | Incompatible operations | Use a combiner compatible with the accumulator |
| Using `reduce` with a mutable `ArrayList` | Identity may be shared and mutated | Use `collect` with a supplier providing new containers |
| Collector supplier returns a shared list | Tasks may modify the same list | Supplier creates a **new instance** on each call |
| `parallelStream().toList()` always scrambles order | Ordered results can still preserve encounter order | Distinguish result order from execution schedule |
| `forEach` and `forEachOrdered` are the same | `forEachOrdered` has ordering constraints | Choose based on requirements |
| Every `collect` in parallel updates a Map concurrently | Non-concurrent collectors may use local maps | Check the `CONCURRENT` characteristic |
| Enabling parallel is always faster | Has split/merge/sync overhead | Benchmark with real data |
| A merge function with side effects is safe because it runs in a collector | Call schedule and grouping can vary | Write a pure, contract-compliant merge function |

## 22. Practice exercises and answers

**Exercise 1 — Splitting a source.** A `Spliterator` has `ORDERED`, `SIZED`, `SUBSIZED` and 100 elements. Can you assert that `trySplit()` always creates two 50/50 parts?

Answer: **No**. The characteristics describe ordering/sizing, not a requirement to split exactly in half. `trySplit()` can even return `null` if it cannot split.

**Exercise 2 — Combining subtotals.** Source `[1,2,3,4,5,6,7,8]` splits into `[1,2,3,4]` and `[5,6,7,8]`. What are the subtotals and the final result?

Answer: subtotals `10` and `26`; the combiner adds them to give `36`. Other splits must also yield `36` in this small integer addition problem.

**Exercise 3 — Identity.** Why is `IntStream.of(1,2,3).parallel().reduce(5,Integer::sum)` not the right way to compute the sum plus 5?

Answer: `5` is not the identity for addition. Separate branches can each have their own identity `5`, so the result is not "5 + sum" as intended. Use `reduce(0,Integer::sum)` and add 5 to the final result, or design a different contract-compliant reduction.

**Exercise 4 — Associativity.** What values do `(10-3)-2` and `10-(3-2)` produce? Should subtraction be used as a general combiner?

Answer: `5` and `9`. Because they are unequal, subtraction is not associative; it should not be used as a combining operation that depends on grouping.

**Exercise 5 — Mutable container.** You want to collect strings from a parallel stream into a List. Why is `reduce(new ArrayList<>(), (list,s)->{list.add(s);return list;}, ...)` risky?

Answer: mutating a mutable identity in `reduce` violates the non-interfering reduction requirement; the identity may be used across multiple branches. Choose `collect(Collectors.toList())`, `toList()`, or `Collector.of(ArrayList::new, ...)`.

**Exercise 6 — Collector.** State the roles of `supplier`, `accumulator`, and `combiner` when collecting into a List.

Answer: `supplier` creates a **new** empty List for the partition; `accumulator` adds an element to the local list; `combiner` merges two lists into a combined result. Do not return a shared list from `supplier`.

**Exercise 7 — Finisher.** In a collector producing CSV, why is `StringBuilder::toString` needed?

Answer: `StringBuilder` is a temporary container for efficient concatenation, while the final return value needed is `String`. The finisher performs this conversion.

**Exercise 8 — Ordered.** Can `numbers.parallelStream().map(...).toList()` produce a list in encounter order even if the lambdas execute out of order?

Answer: **Yes**, with an ordered source and a pipeline that retains its ordering constraint. Internal evaluation order and result order are two different things.

**Exercise 9 — API choice.** A large source needs counts by category across many partitions. What should you use?

Answer: `groupingBy(key, counting())` can process in parallel via accumulation/merging; consider `groupingByConcurrent` if encounter order is not needed and it genuinely fits. Measure performance before concluding it is better.

**Exercise 10 — True or false?** "If I use `parallelStream` and `forEachOrdered`, all side effects are guaranteed to be transactional and exactly-once."

Answer: **False**. `forEachOrdered` enforces action order within an ordered traversal; it does not provide transactions, rollback, or idempotency across retries.

## 23. Checklist when designing a parallel pipeline

1. **Does the source split well?** Is it sized with an efficient `Spliterator`, or a sequential I/O stream that is hard to split?
2. **Are per-partition functions pure and independent?** Do they avoid modifying the source and avoid depending on shared mutable state?
3. **Is the combining operation associative?** Verify across different groupings, not just one test suite.
4. **Is the identity correct?** Check the identity element; for three-argument `reduce`, also check accumulator/combiner compatibility.
5. **Use `reduce` or `collect`?** Aggregated values usually use `reduce`; mutable containers use `collect`.
6. **Does the supplier create a new container?** Never use a shared list or mutable singleton.
7. **Is order needed?** Encounter order, `forEachOrdered`, and `UNORDERED` affect correctness and performance.
8. **Are there stateful stages?** `sorted`, `distinct`, `limit`, `takeWhile` can add coordination overhead.
9. **Is there overflow or precision error?** `int`/`long` sums can overflow; `double` has grouping-dependent rounding issues.
10. **How are errors and side effects managed?** Parallel streams do not provide exactly-once or transactions.
11. **Is speed actually better?** Benchmark with representative data, rather than measuring once and extrapolating.
12. **Is the Stream being reused?** A pipeline is consumed only once; create a new stream for another pass.

## 24. Summary

- **Source splitting** is usually backed by `Spliterator`; `trySplit` is a model for understanding decomposition, not a promise of a 50/50 split.
- **Partition processing** allows multiple tasks to compute local data; thread scheduling and task counts are decided by the implementation.
- **Combining results** must use an operation with a **valid identity**, **associativity**, and a **combiner compatible** with the accumulator.
- **`reduce`** suits value-type results; **`collect`** suits mutable containers with supplier/accumulator/combiner/finisher.
- **Do not share mutable containers** across tasks, and do not use `reduce` to mutate an `ArrayList` identity.
- **Parallel does not automatically remove encounter-order constraints**; ordered results can still be properly ordered even when tasks finish differently.
- **Ordering, performance, errors, overflow, and side effects** must still be considered as part of the design.

Official references: [Java 17 Stream](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Stream.html), [Spliterator](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Spliterator.html), [Collector](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collector.html), [Collectors](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/Collectors.html), [Stream package summary — Reduction](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/stream/package-summary.html#Reduction).