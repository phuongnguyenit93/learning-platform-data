# Choosing reduce() vs. collect() Based on the Nature of the Result in Java Stream

In the Java Stream API, **`reduce()`** and **`collect()`** are both *terminal operations* used to aggregate multiple elements into a single result. However, they serve two different styles of accumulation. Choosing the right one not only keeps code clear, but also directly affects **correctness under parallel processing**, reusability, memory management, and performance.

- **`reduce()`** is suited for **value-combining operations**: from the elements, computing a sum, product, min/max, immutable merge, or a new aggregated result. Each application of the operator typically returns **a result value** without mutating the passed-in accumulator.
- **`collect()`** is suited for **accumulating into a mutable container**: building a list, set, map, grouped data, a string via `StringBuilder`, summary statistics, or a result described by a `Collector`.
- There is no absolute rule that the final result of `collect` must be mutable or that `reduce` only returns primitives. The difference lies in the **accumulation mechanism and the operator contract**, not simply in the name of the final result type.

As a short example, assuming `numbers` is an already-declared `List<Integer>`:

```java
int sum = numbers.stream().reduce(0, Integer::sum);
List<Integer> copy = numbers.stream().collect(java.util.stream.Collectors.toList());
```

The first line combines the numbers using addition. The second line collects the elements into a container. Because the two goals differ, different terminal operations are chosen.

**Lesson objectives:** master the three overloads of `reduce`, the forms of `collect`, the identity/associativity/combiner rules, choices for lists–maps–grouping–statistics, the mutable identity trap, and how to verify logic on parallel streams. Complete programs use **Java 17+**.

## 1. Thinking from the nature of the result, not from syntax

The first question when choosing a terminal operation is: **Should the result be a computed value or an accumulated structure?**

| Goal | Typical choice | Example |
| --- | --- | --- |
| Sum numbers | `sum()` or `reduce(0, Integer::sum)` | `IntStream` returns `int` |
| Find maximum/minimum value | `max()`, `min()`, or `reduce` | Result may be `Optional` |
| Merge immutable states into a new state | `reduce` | Sum + count in an immutable record |
| Create `List<T>`, `Set<T>` | `toList()` or `collect` | Data is placed into a container |
| Group by key | `collect(groupingBy(...))` | `Map<K,List<T>>` |
| Count each group | `collect(groupingBy(..., counting()))` | `Map<K,Long>` |
| Join strings with a delimiter | `collect(joining(","))` | Collector uses efficient accumulation |
| Collect into a specified mutable `ArrayList` | `collect(toCollection(ArrayList::new))` | Result can be modified |
| Compute multi-metric statistics in one pass | `collect(summarizingInt(...))` | Count/sum/min/max/average |

Just because `reduce` can produce the same return type does not mean it is the best choice. For example, joining 10,000 strings with `reduce("", String::concat)` may create many intermediate strings because `String` is immutable; `Collectors.joining` is usually more suitable. Conversely, computing a sum only needs a single numeric value, so there is no need to build an `ArrayList` and iterate over it again.

## 2. reduce(): reduction based on combining values

For `Stream<T>`, there are three important overload groups.

### 2.1. reduce(BinaryOperator<T>): elements may be absent

```java
Optional<Integer> max = Stream.of(2, 9, 4)
        .reduce(Integer::max);  // Optional containing 9

Optional<Integer> missing = Stream.<Integer>empty()
        .reduce(Integer::max);  // Optional.empty()
```

This is an **illustrative snippet** requiring imports for `java.util.Optional` and `java.util.stream.Stream`, placed inside a method. When the Stream is empty and there is no identity, the API uses `Optional<T>` to represent absence. Do not call `get()` arbitrarily; use `orElse` or `orElseThrow` when appropriate.

An operator such as `Integer::max` is an *associative* combining operation; the result does not depend on how the operations are mathematically grouped.

### 2.2. reduce(identity, BinaryOperator<T>): always produces a result

```java
int total = Stream.of(2, 9, 4).reduce(0, Integer::sum); // 15
int emptyTotal = Stream.<Integer>empty().reduce(0, Integer::sum); // 0
```

`identity` is the **identity element**: combining it with a value leaves that value unchanged. For addition, the identity is `0`; for multiplication, the identity is `1`. If the Stream is empty, `reduce(identity, op)` returns the identity itself.

For string concatenation, `""` is the identity of concatenation; for a sum of type `long`, use `0L`. Do not choose an identity arbitrarily as a "default value" if it breaks the operation.

### 2.3. reduce(identity, accumulator, combiner): result type differs from element type

This is the overload in conceptual form:

```java
<U> U reduce(
    U identity,
    BiFunction<U, ? super T, U> accumulator,
    BinaryOperator<U> combiner
)
```

The above is an **illustrative signature**, not a top-level method to run standalone. `T` is the Stream element type; `U` is the result type.

- `identity` is the identity value for merging results.
- `accumulator` takes an intermediate result `U` and an element `T`, and **returns a new `U`/result value**.
- `combiner` merges two `U` results when the pipeline is split into multiple parts, especially during parallel processing.

Example of summing the lengths of strings:

```java
int lengthSum = Stream.of("aa", "bbb", "c")
        .reduce(
                0,
                (total, word) -> total + word.length(),
                Integer::sum
        ); // 6
```

The value `0` is the identity, the accumulator adds each word's length, and the combiner adds two intermediate sums. Neither combining step **mutates a shared accumulator object**. This pattern is valid with `parallelStream()` when the functions are stateless and non-interfering as in the example.

## 3. The reduce contract: identity, associativity, and compatibility

For a `reduce` operation to split and merge correctly, it must satisfy foundational conditions.

### 3.1. Identity

For an operator `op`, the identity `e` must satisfy:

```text
op(e, x) = x
op(x, e) = x
```

This is **mathematical notation describing the contract**, not Java code.

Addition: `e = 0`. Multiplication: `e = 1`. For any other operation, you must carefully determine what the true identity element is, rather than defaulting to zero.

### 3.2. Associativity

The operator must be associative:

```text
op(op(a, b), c) = op(a, op(b, c))
```

Integer addition on small example values satisfies this. Ordinary subtraction is **not associative**:

```text
(10 - 5) - 2 = 3
10 - (5 - 2) = 7
```

Therefore `reduce(0, (a, b) -> a - b)` is not a valid reduction if you expect the same result when switching from sequential to parallel. Note that Java integer addition can overflow modulo 2^32 (or 2^64 for `long`), so value ranges must be controlled if the domain requires non-overflowing mathematical sums.

### 3.3. Compatibility for three-argument reduce

With result type `U`, `combiner` must be consistent with how `accumulator` adds an element. The key contract:

```text
combiner(u, accumulator(identity, t)) = accumulator(u, t)
```

This expresses that combining a result `u` with the result computed from a single element `t` must be the same as directly adding `t` to `u`. If `accumulator` sums but `combiner` multiplies, parallel results can be wrong even if sequential testing appears to work.

Some operations such as `double` addition have rounding differences depending on grouping order; you should not require bit-by-bit identical results across all groupings.

**Practical rule:** with `reduce`, prefer an accumulator and combiner with **no side effects**, that do not modify the Stream source, do not mutate a shared mutable container, and have valid identity/associativity.

## 4. Java 17 program: the overloads of reduce

Save as **`ReduceEssentialsDemo.java`**:

```java
import java.util.List;
import java.util.Optional;

public class ReduceEssentialsDemo {
    public static void main(String[] args) {
        List<Integer> numbers = List.of(2, 3, 5);

        int sum = numbers.stream().reduce(0, Integer::sum);
        int product = numbers.stream().reduce(1, (a, b) -> a * b);
        Optional<Integer> max = numbers.stream().reduce(Integer::max);

        Optional<Integer> emptyMax = List.<Integer>of()
                .stream()
                .reduce(Integer::max);

        int totalLength = List.of("aa", "bbb", "c")
                .parallelStream()
                .reduce(0,
                        (length, word) -> length + word.length(),
                        Integer::sum);

        System.out.println("sum=" + sum);
        System.out.println("product=" + product);
        System.out.println("max=" + max.orElse(-1));
        System.out.println("emptyMax=" + emptyMax.orElse(-1));
        System.out.println("lengthSum=" + totalLength);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ReduceEssentialsDemo.java
java ReduceEssentialsDemo
```

**Exact stdout:**

```text
sum=10
product=30
max=5
emptyMax=-1
lengthSum=6
```

Here the combining operators on small numbers satisfy identity and associativity; therefore running `parallelStream` on the length sum still produces 6. `emptyMax` is `Optional.empty()` and `orElse(-1)` merely provides a fallback for the example.

`List.<Integer>of()` creates an empty list with an explicit `Integer` element type. Do not confuse `max` with taking the last element: `Integer::max` compares numeric values.

## 5. collect(): accumulating via a container or Collector

`collect()` provides a **mutable reduction** mechanism: create a result container, add each element into the container, and then combine partial containers if needed.

There are two main API forms:

```java
<R> R collect(
    Supplier<R> supplier,
    BiConsumer<R, ? super T> accumulator,
    BiConsumer<R, R> combiner
)

<R, A> R collect(Collector<? super T, A, R> collector)
```

These are **illustrative signatures** in `Stream<T>` (with generics simplified for readability). For the three-argument form:

- **supplier** creates a new container, such as `ArrayList::new`.
- **accumulator** takes a container and an element, and **mutates that container**, such as `List::add`.
- **combiner** merges the contents of two containers to produce the combined result, such as `List::addAll`.

Unlike `reduce`, which returns combined values, `collect` is designed to work with containers that **can be mutated during accumulation**. When running in parallel, the framework can create multiple independent containers and combine them. Do not pass in a single pre-created shared `ArrayList` from outside and mutate it from multiple workers.

The form accepting a `Collector` also allows describing **supplier, accumulator, combiner, finisher**, and collector characteristics in a standardized way. A `Collector` can return a final **unmodifiable** result, even though internal accumulation uses mutable state.

## 6. Commonly used standard Collectors

In `java.util.stream.Collectors`, there are many common collectors:

| Collector | Purpose |
| --- | --- |
| `toList()` | Collect into a `List<T>`; makes no guarantee on specific list type or mutability |
| `toSet()` | Collect into a `Set<T>`; makes no guarantee on iteration order |
| `toCollection(ArrayList::new)` | Choose a specific result container type |
| `toUnmodifiableList()` | Return an unmodifiable List; does not accept null elements |
| `joining(",")` | Join `CharSequence` elements with a delimiter |
| `groupingBy(classifier)` | Group elements by key into a Map |
| `groupingBy(classifier, downstream)` | Group and then aggregate each group |
| `toMap(keyMapper, valueMapper, mergeFunction)` | Create a map, handling duplicate keys via merge |
| `counting()` | Count elements as a `Long` |
| `summingInt(mapper)` | Sum an int-typed property |
| `summarizingInt(mapper)` | Summarize count, sum, min, max, average |
| `partitioningBy(predicate)` | Partition data by true/false |

**Do not confuse `Stream.toList()` with `Collectors.toList()`.** Since Java 16, `Stream.toList()` returns a list that is unmodifiable through the API. `Collectors.toList()` **does not guarantee** mutability or a specific implementation; if you specifically need a mutable `ArrayList`, use `Collectors.toCollection(ArrayList::new)`.

Additionally, `Collectors.toSet()` does not promise ordering; if insertion order must be preserved, `Collectors.toCollection(LinkedHashSet::new)` is the clear choice.

## 7. Java 17 program: collecting into list, set, and map

Save as **`CollectContainersDemo.java`**:

```java
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Set;
import java.util.TreeMap;
import java.util.Map;
import java.util.stream.Collectors;

public class CollectContainersDemo {
    public static void main(String[] args) {
        List<String> words = List.of(
                "java", "stream", "java", "lambda", ""
        );

        List<String> mutable = words.stream()
                .filter(s -> !s.isBlank())
                .collect(Collectors.toCollection(ArrayList::new));
        mutable.add("extra");

        Set<String> unique = words.stream()
                .filter(s -> !s.isBlank())
                .collect(Collectors.toCollection(LinkedHashSet::new));

        Map<Integer, Long> byLength = List.of("a", "bb", "ccc", "dd", "e")
                .stream()
                .collect(Collectors.groupingBy(
                        String::length,
                        TreeMap::new,
                        Collectors.counting()));

        String joined = words.stream()
                .filter(s -> !s.isBlank())
                .collect(Collectors.joining(","));

        System.out.println("mutable=" + mutable);
        System.out.println("unique=" + unique);
        System.out.println("byLength=" + byLength);
        System.out.println("joined=" + joined);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 CollectContainersDemo.java
java CollectContainersDemo
```

**Exact stdout:**

```text
mutable=[java, stream, java, lambda, extra]
unique=[java, stream, lambda]
byLength={1=2, 2=2, 3=1}
joined=java,stream,java,lambda
```

`ArrayList` is explicitly requested via the supplier so the result supports `add` for additional elements. `LinkedHashSet` deduplicates and preserves the insertion order of sequentially encountered elements. `TreeMap` sorts length keys in ascending order so the map prints deterministically. `joining(",")` joins strings in encounter order without writing a manual reduce that repeatedly creates intermediate strings.

## 8. Why is a mutable identity in reduce dangerous?

This is a very common mistake when first learning `reduce`: the author wants to gather elements into an `ArrayList` or `StringBuilder`, so they pass a mutable container as the **identity** and mutate it inside the accumulator.

**Counter-example — do not use:**

```java
// UNSAFE, especially with parallelStream():
List<String> collected = List.of("A", "B", "C")
        .parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, text) -> {
                    list.add(text);       // mutates the list used as identity
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
```

The snippet above **compiles** when `List` and `ArrayList` are imported, but it violates the reduction contract: the accumulator mutates the object shared as the identity; in parallel execution, the same mutable object can participate in multiple reductions and cause race conditions or wrong/duplicated results. Do not try to patch this with a few `synchronized` blocks while keeping the broken reduction model.

**The fix: use collect** so the framework creates separate containers for each task:

```java
List<String> collected = List.of("A", "B", "C")
        .parallelStream()
        .collect(
                ArrayList::new,
                ArrayList::add,
                ArrayList::addAll
        );
```

This snippet is independent of the one above (if placing both in one method, use different variable names). `collect(supplier, accumulator, combiner)` creates new `ArrayList` instances as needed, adds each value into its own container, and then merges the parts. With an ordered List source, the result preserves encounter order according to the Stream contract; do not use an external `ArrayList` outside the pipeline as the target of a parallel `forEach`.

**Note:** another workaround such as `reduce(new ArrayList<>(), (list, x) -> { List copy = new ArrayList(list); copy.add(x); return copy; }, ...)` avoids mutating the identity, but creates many copies. When the goal is to build a list, `collect` is simpler and more natural.

## 9. Using StringBuilder in collect instead of string-concatenating reduce

String concatenation can be illustrated with `reduce`:

```java
String joined = Stream.of("A", "B", "C")
        .reduce("", String::concat); // "ABC"
```

This snippet requires `import java.util.stream.Stream;`. The syntax is valid, but with many strings each concatenation typically allocates an intermediate `String` because `String` is immutable.

If you only need to join strings, you should usually use:

```java
String joined = Stream.of("A", "B", "C")
        .collect(java.util.stream.Collectors.joining(",")); // "A,B,C"
```

If you need to build a string in a custom way, you can use the three-argument `collect` with `StringBuilder`:

```java
StringBuilder builder = Stream.of("A", "B", "C")
        .collect(
                StringBuilder::new,
                (b, text) -> b.append(text),
                (left, right) -> left.append(right)
        );
String result = builder.toString(); // "ABC"
```

This is an illustrative snippet, with each Stream created fresh. The supplier `StringBuilder::new` provides a container for each accumulation part; the accumulator and combiner can mutate that part's own container. Since the desired result is a `String`, `Collectors.joining` is usually shorter and clearer.

**Do not use `reduce(new StringBuilder(), StringBuilder::append, StringBuilder::append)` for parallel pipelines**: the mutable identity can be reused across branches, violating the side-effect-free operator requirement and reduction correctness.

## 10. Java 17 program: three-argument collect and safe parallel execution

Save as **`ParallelCollectDemo.java`**:

```java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.Collectors;

public class ParallelCollectDemo {
    public static void main(String[] args) {
        List<String> letters = List.of("A", "B", "C", "D");

        List<String> direct = letters.parallelStream()
                .collect(
                        ArrayList::new,
                        ArrayList::add,
                        ArrayList::addAll
                );

        List<String> viaCollector = letters.parallelStream()
                .collect(Collectors.toCollection(ArrayList::new));

        String joined = letters.parallelStream()
                .collect(Collectors.joining("-"));

        int totalLength = letters.parallelStream()
                .reduce(
                        0,
                        (length, letter) -> length + letter.length(),
                        Integer::sum
                );

        System.out.println("direct=" + direct);
        System.out.println("collector=" + viaCollector);
        System.out.println("joined=" + joined);
        System.out.println("length=" + totalLength);
    }
}
```

Compile and run:

```bash
javac -encoding UTF-8 ParallelCollectDemo.java
java ParallelCollectDemo
```

**Exact stdout:**

```text
direct=[A, B, C, D]
collector=[A, B, C, D]
joined=A-B-C-D
length=4
```

The sources in the example are Lists with encounter order. The collect operations respect the ordering contract and combine partial accumulations compatibly, so the results preserve this order even though processing steps may run on multiple threads. `reduce` uses immutable integers and associative addition. No external `ArrayList` is shared across the terminal operations.

Do not infer that parallel streams are always faster; four strings are far too small for a serious performance benchmark. The example is only meant to demonstrate **semantically correct** API usage.

## 11. Collect can return an immutable result

A common misconception is: "collect uses a mutable container, so the final result is always mutable." This is false: a collector can use a mutable container **during accumulation**, and then apply a finisher to produce a different result type, including an immutable object.

Example:

```java
List<String> immutable = Stream.of("A", "B")
        .collect(java.util.stream.Collectors.toUnmodifiableList());
```

This illustrative snippet returns a List that does not support modification through the API; `immutable.add("C")` will throw `UnsupportedOperationException`. It also does not accept null elements. Similarly, `Stream.toList()` (Java 16+) returns an unmodifiable list without calling `collect`.

The `collectingAndThen(downstream, finisher)` collector can transform the downstream result into the intended final form, though you should carefully check the immutability and aliasing requirements of the inner objects. A structurally unmodifiable List can still hold mutable objects.

**Decide based on the accumulation mechanism and output contract:**
- Need a pure transformation to a single value? Usually `reduce`.
- Need to gather/group into a container? Usually `collect`.
- Need an immutable final list? Choose `toList`, `toUnmodifiableList`, or an appropriate collector/finisher, not necessarily `reduce`.

## 12. Same problem, two expressions: sales metrics

Suppose each sales record has `category` and `quantity`. We want to:
- Compute the total quantity across all records.
- Get summary statistics: record count, sum, min, max, average.
- Aggregate total quantity per category.

**Total quantity** is a combined value, so use `reduce` or `mapToInt(...).sum()`.

**Statistics and grouping** require aggregated state and a structured result, so use `collect` with downstream collectors.

Save as **`SalesAggregationDemo.java`**:

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;
import java.util.stream.Collectors;

public class SalesAggregationDemo {
    record Sale(String category, int quantity) {}

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("A", 2),
                new Sale("B", 3),
                new Sale("A", 4)
        );

        int totalReduce = sales.stream()
                .map(Sale::quantity)
                .reduce(0, Integer::sum);

        int totalPrimitive = sales.stream()
                .mapToInt(Sale::quantity)
                .sum();

        IntSummaryStatistics stats = sales.stream()
                .collect(Collectors.summarizingInt(Sale::quantity));

        Map<String, Integer> quantityByCategory = sales.stream()
                .collect(Collectors.groupingBy(
                        Sale::category,
                        TreeMap::new,
                        Collectors.summingInt(Sale::quantity)
                ));

        String categories = sales.stream()
                .map(Sale::category)
                .distinct()
                .collect(Collectors.joining(","));

        System.out.println("reduceTotal=" + totalReduce);
        System.out.println("primitiveTotal=" + totalPrimitive);
        System.out.println("count=" + stats.getCount());
        System.out.println("min=" + stats.getMin());
        System.out.println("max=" + stats.getMax());
        System.out.println("average=" + stats.getAverage());
        System.out.println("byCategory=" + quantityByCategory);
        System.out.println("categories=" + categories);
    }
}
```

Compile/run:

```bash
javac -encoding UTF-8 SalesAggregationDemo.java
java SalesAggregationDemo
```

**Exact stdout:**

```text
reduceTotal=9
primitiveTotal=9
count=3
min=2
max=4
average=3.0
byCategory={A=6, B=3}
categories=A,B
```

`map(Sale::quantity).reduce(0, Integer::sum)` and `mapToInt(...).sum()` both produce 9; using the primitive stream avoids boxing during the sum step. `summarizingInt` is a collector that computes multiple statistics in one terminal operation. `groupingBy` combined with `summingInt` produces totals per category; `TreeMap` makes the key display order deterministic. `joining` is solely responsible for joining category names after deduplication.

**Note:** these `int` sums can overflow when quantities are very large. If the total may exceed the `int` range, use `mapToLong`/`summingLong` and an appropriate overflow-checking policy, rather than only changing the terminal operation name.

## 13. Using reduce with an immutable record for aggregated state

`reduce` is not limited to a single integer. An immutable record can represent an aggregated result; each step creates a new value and the combiner merges two results without mutating a shared object.

Example:

```java
record CountSum(long count, long sum) {
    CountSum addValue(int value) {
        return new CountSum(count + 1, sum + value);
    }

    CountSum combine(CountSum other) {
        return new CountSum(count + other.count, sum + other.sum);
    }
}
```

This is a valid record declaration in Java 17, placed at top-level or nested inside a class. When used inside a method:

```java
CountSum statistics = List.of(2, 3, 5)
        .parallelStream()
        .reduce(
                new CountSum(0L, 0L),
                (result, value) -> result.addValue(value),
                CountSum::combine
        );
// CountSum[count=3, sum=10]
```

Here the identity `CountSum(0,0)` is immutable; the accumulator returns a new record with count incremented by 1 and value added to sum; the combiner merges two records. This design is **semantically valid** for parallel `reduce`.

However, if the dataset is very large and merging allocates new objects too frequently, a summary collector can reduce allocations. **Semantically correct does not automatically mean performance-optimal**. Choose the API based on your goal and measure if throughput/latency matters.

## 14. Collect and parallel processing: safety rules

A parallel Stream can split data into work units and then aggregate results in an order compatible with the Stream contract. Therefore:

1. **Do not mutate an externally supplied container** from multiple `forEach` callbacks. For example, `List<String> result = new ArrayList<>(); source.parallelStream().forEach(result::add);` is unsafe.
2. **With three-argument `collect`**, the supplier must create independent containers, the accumulator must update only the given container, and the combiner must merge two containers meaningfully. Avoid holding a singleton accumulator outside.
3. **With built-in Collectors**, such as `toList`, `groupingBy`, `toCollection`, let the Stream framework manage containers; there is no need to add `synchronized` around every operation.
4. **Do not assume every Collector has the `CONCURRENT` characteristic**. Many ordinary collectors still work with parallel Streams by creating multiple containers and merging them. Concurrent collectors have specific rules regarding shared containers, unorderedness, and accumulator thread-safety.
5. **Preserve encounter order when the business logic requires it.** If the source is an ordered List, appropriate collectors typically preserve result order; if the source is unordered, do not assume the first element will always be kept.
6. **A reduce operation must be associative and have a valid identity.** For `double`, differences in grouping order can cause rounding differences; the application must define acceptable tolerance.

Thread count and speedup are not guaranteed. Benchmark on real data with an appropriate tool (such as JMH) instead of assuming `parallelStream()` is always better.

## 15. Common mistakes

1. **Using `reduce(new ArrayList<>(), ...)` and mutating the identity list itself:** violates the contract and is dangerous in parallel.
2. **Assuming collect only returns a mutable List:** `toUnmodifiableList`, `collectingAndThen` can return unmodifiable results.
3. **Assuming `Collectors.toList()` is always an `ArrayList`:** the API does not guarantee the implementation or mutability.
4. **Assuming `Stream.toList()` and `Collectors.toList()` are identical:** they differ in their output contract.
5. **Using subtraction with parallel reduce:** not associative.
6. **Choosing the wrong identity:** using 0 for multiplication turns every result into 0.
7. **Inconsistent combiner logic:** accumulator adds while combiner multiplies; sequential may appear to work while parallel fails.
8. **Keeping a mutable accumulator in a field/variable outside the pipeline:** shared mutable state can cause race conditions.
9. **Using `reduce` to concatenate many Strings:** can create many intermediate Strings; `joining` is more suitable.
10. **Using `collect` just to sum a number:** `sum` or `reduce` is usually simpler.
11. **Using `toSet` and expecting the source List's order:** Set collectors do not guarantee order; choose `LinkedHashSet` or an appropriate structure.
12. **Unwrapping `Optional` with `get()` after a reduce without identity:** an empty Stream will make `get()` throw an exception.
13. **Believing all collectors are thread-safe for external mutation:** the framework manages container lifecycles; do not freely mutate the same container from multiple threads.
14. **Failing to handle null:** `toUnmodifiableList` rejects null; some other collectors and mappers also have specific restrictions.
15. **Using parallel just because reduce/collect supports it:** overhead and data characteristics determine actual benefit.
16. **Mixing immutable reduction steps with I/O side effects:** hard to test, hard to guarantee order, and error-prone in parallel.

## 16. Final decision table

| Requirement characteristic | Preferred choice |
| --- | --- |
| Pure, associative value-combining operation with valid identity | `reduce` |
| Only need sum/min/max/count from a primitive stream | `sum`/`min`/`max`/`count` |
| Want a set/list from multiple elements | `toList()` or `collect` |
| Need a specific mutable container (`ArrayList`, `LinkedHashSet`) | `collect(toCollection(...))` |
| Need to group/count by key | `collect(groupingBy(...))` |
| Need to build a Map and handle duplicate keys | `collect(toMap(..., mergeFunction))` |
| Need to join strings with a delimiter | `collect(joining(delimiter))` |
| Need multiple statistics in one pass | `collect(summarizingInt(...))` |
| Want to reduce elements into an immutable record | `reduce` with pure accumulator/combiner |
| Accumulating by mutating a container object | `collect` instead of a mutable identity in `reduce` |

**Quick decision path:** If the answer is "**combine values using a pure operator**", look at `reduce`. If the answer is "**create or update a result container**", look at `collect` or a specialized terminal operation. When a clearer specialized API exists (such as `sum`, `toList`, `joining`, `groupingBy`), prefer that expression.

## 17. Self-check and answers

**Question 1.** What does `Stream.of(1,2,3).reduce(0, Integer::sum)` return?

**Answer:** `6`, because 0 is the identity of addition.

**Question 2.** What does `Stream.<Integer>empty().reduce(Integer::max)` return?

**Answer:** `Optional.empty()`; there is no identity and no elements.

**Question 3.** You need to create an `ArrayList<String>` that can have elements added after collection. Use `reduce` or `collect`?

**Answer:** `collect(Collectors.toCollection(ArrayList::new))`. This is a requirement to build a mutable container.

**Question 4.** Why is `parallelStream().reduce(new ArrayList<>(), (list,x) -> { list.add(x); return list; }, ...)` unsafe?

Because mutating a mutable identity violates the reduction contract and parallel tasks can concurrently affect the same object. Use `collect` with a supplier that creates new containers.

**Question 5.** Does `Collectors.toList()` promise to return a mutable `ArrayList`?

**No.** If you need an `ArrayList`, use `toCollection(ArrayList::new)`. `Stream.toList()` is specified to return an unmodifiable list.

**Question 6.** What should be used to compute the total `quantity` for each `category`?

**Answer:** `collect(groupingBy(Sale::category, summingInt(Sale::quantity)))` or a variant selecting a specific Map. This is grouped aggregation, not a single reduction to one number.

**Question 7.** What relationship must the combiner of `reduce(identity, accumulator, combiner)` have with the accumulator?

**Answer:** It must semantically merge `U` results, be associative, have the proper identity, and be compatible with how the accumulator adds a single element: `combiner(u, accumulator(identity,t))` is equivalent to `accumulator(u,t)`.

**Question 8.** When you need to join very many strings with a comma, is `reduce("", String::concat)` or `Collectors.joining(",")` more appropriate?

**Answer:** `Collectors.joining(",")`, because it expresses the delimiter directly and avoids unnecessary intermediate strings.

**Remember:** **`reduce()` is for value-combining operations that obey the laws (identity, associativity, compatibility); `collect()` is for accumulating via a container/collector.** Do not use a mutable container as the identity and mutate it in `reduce`. Choose a terminal operation based on the nature of the result and safety when splitting/combining, not just because one syntax looks shorter.
