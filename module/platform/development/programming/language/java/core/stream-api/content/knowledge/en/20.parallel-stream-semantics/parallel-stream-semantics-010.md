# Converting a Sequential Pipeline to Parallel While Preserving Semantics

In the **Parallel Processing Semantics** chapter of the **Java Stream API**, changing `stream()` to `parallelStream()` or adding `parallel()` is a tiny syntactic change. However, a syntactically successful conversion **does not automatically mean** the pipeline remains business-correct. How the source is split, the execution order of lambdas, how many times an operation is called, and the order in which intermediate results are combined can all change.

The goal of this lesson is to know **when a sequential pipeline can be converted to parallel while preserving its intended semantics**. We will examine source and Spliterator contracts, processing-function independence, *encounter order* rules, `reduce`/`collect`, numeric data, and especially unsafe side effects. From there, you can properly evaluate both **correctness** and **performance**, rather than just turning on `parallel()` hoping to go faster.

These principles apply to pipelines involving `filter`, `map`, `flatMap`, `reduce`, `collect`, multi-level collectors, Spliterators, and extensions such as Stream Gatherers: parallelization is only safe when every layer's semantics tolerate split-and-combine execution.

## 1. What does parallelization change?

Example of a sequential pipeline:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4, 5);

List<Integer> squared = values.stream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * n)
        .toList();

System.out.println(squared); // [1, 9, 25]
~~~

Changing only the Stream source:

~~~java
List<Integer> squared = values.parallelStream()
        .filter(n -> n % 2 != 0)
        .map(n -> n * n)
        .toList();

System.out.println(squared); // [1, 9, 25]
~~~

The pipeline uses `filter`/`map` functions free of shared state; the `List` source has encounter order; `toList()` preserves that order. Thus, **the values and order of the resulting list** are preserved in this example.

However, the following are **not guaranteed**:

~~~text
Element 1 is processed before element 3.
The thread processing element 5 must be the thread processing element 4.
Each map/filter call runs strictly in List order.
Each element is processed by a separate thread.
~~~

The Stream API may split the source into parts, process them on different workers, and merge results according to the terminal operation's contract. Internal execution order **is not** encounter order, even when the final result has encounter order.

> **Principle:** Test **the specified result**, not the internal execution order an implementation happens to take.

## 2. Distinguishing encounter order, execution order, and result order

Three concepts that are easily conflated:

| Concept | Meaning | Guaranteed when parallel? |
| --- | --- | --- |
| *Encounter order* | Logical element order of the source/pipeline when the source is ordered | Preserved by operations whose contract maintains encounter order. |
| *Execution order* | When and by which thread a mapper/predicate runs | In general **not** guaranteed. |
| Result order | Order observed at the terminal operation's output | Depends on the terminal operation's contract and whether the source is ordered. |

With a `List`:

~~~java
import java.util.List;

List<String> names = List.of("Lan", "An", "Minh", "Huy");

List<String> result = names.parallelStream()
        .map(String::toUpperCase)
        .toList();

System.out.println(result); // [LAN, AN, MINH, HUY]
~~~

`toList()` returns elements in the source's encounter order. That **does not mean** `toUpperCase` calls ran sequentially Lan → An → Minh → Huy.

If the source has no guaranteed encounter order—for instance, a Stream from certain `Set` types—or the pipeline calls `unordered()`, do not rely on a default output order. If business logic requires ordering by code, date, or priority, define explicit criteria and place `sorted(...)` appropriately.

## 3. Checklist before changing stream() to parallelStream()

Before editing code, answer these questions:

1. **Can the source split safely?** Does its Spliterator support reasonable `trySplit()`, and is it free of illegal concurrent mutation during traversal?
2. **Are lambdas *non-interfering*?** Do they avoid adding/removing source elements during traversal unless the source contractually supports concurrent modification?
3. **Do lambdas avoid shared mutable state (*stateless*)?** Does each `map`/`filter` result avoid depending on external variables mutated by other elements?
4. **Does order matter?** If so, do the intermediate and terminal operations preserve the necessary encounter order?
5. **Is the aggregation valid under splitting/merging?** Is `identity` neutral, `combiner` associative, accumulator compatible, and does the collector obey parallel contracts?
6. **Is exact numeric reproducibility required?** Floating-point arithmetic and intermediate rounding can change results under different groupings.
7. **Are there side effects, I/O, or transactions?** Parallelism does not automatically provide synchronization, commit order, or rollback.
8. **Is parallelization worthwhile?** Are data size, compute cost, and splittability large enough to outweigh overhead?

If you cannot yet answer the **correctness** questions, do not use benchmark timings as proof that code is safe. A fast pipeline that occasionally drops records is still a broken pipeline.

## 4. Stateless and non-interfering: foundational requirements

A `map` or `filter` suitable for parallel execution usually depends only on **the current element** and immutable configuration data.

~~~java
import java.util.List;

List<String> codes = List.of(" pen ", "book", "pad");

List<String> normalized = codes.parallelStream()
        .map(String::trim)
        .map(String::toUpperCase)
        .toList();

System.out.println(normalized); // [PEN, BOOK, PAD]
~~~

Each mapper is an independent transformation on a single string. No counter or mutable Map is updated across tasks.

### Bug: using a shared counter for numbering

~~~java
import java.util.List;
import java.util.concurrent.atomic.AtomicInteger;

List<String> names = List.of("A", "B", "C", "D");

AtomicInteger counter = new AtomicInteger();

List<String> numbered = names.parallelStream()
        .map(name -> counter.incrementAndGet() + ":" + name)
        .toList();
~~~

`AtomicInteger` makes the increment operation atomically safe, yet **does not ensure sequence numbers match encounter order**. The program may return names ordered `A, B, C, D` while the numbers attached to each name are not `1, 2, 3, 4`.

Replacing a shared `int[]` with `AtomicInteger` fixes an increment-level race condition, **without fixing the pipeline's semantics**.

If positional numbering is required, take indices from an ordered, sized source:

~~~java
import java.util.stream.IntStream;

List<String> numbered = IntStream.range(0, names.size())
        .parallel()
        .mapToObj(i -> (i + 1) + ":" + names.get(i))
        .toList();

System.out.println(numbered); // [1:A, 2:B, 3:C, 4:D]
~~~

Here index `i` is **element data**, not the order in which a task happened to run. This pattern fits when the source supports stable indexed access, like `List.of(...)` here, and is not mutated during traversal.

## 5. Do not mutate the source while traversing

A non-interfering pipeline avoids modifying input data in ways that break the Iterator or Spliterator contract.

~~~java
import java.util.ArrayList;
import java.util.List;

List<Integer> numbers = new ArrayList<>(List.of(1, 2, 3, 4));

// Wrong: mutating the source itself while Stream traverses it.
numbers.parallelStream()
        .forEach(n -> {
            if (n % 2 == 0) {
                numbers.remove(n);
            }
        });
~~~

Possible outcomes include `ConcurrentModificationException`, skipped elements, or undefined results. This does not become valid merely because one run happens not to throw an exception.

If the goal is removing even numbers, produce a new output:

~~~java
List<Integer> oddNumbers = numbers.parallelStream()
        .filter(n -> n % 2 != 0)
        .toList();
~~~

If the application must update the source collection afterward, perform edits **separate from traversal** using an appropriate mechanism. Sources with `CONCURRENT` may support certain concurrent edits under their own contract, yet never assume an ordinary `ArrayList` or `HashMap` permits it.

## 6. Side effects in forEach: where right, where wrong?

`forEach` is a terminal operation for per-element actions; it does not build a result collection and does not guarantee invocation order in a parallel pipeline.

~~~java
import java.util.List;

List<String> items = List.of("A", "B", "C", "D");

items.parallelStream()
        .forEach(System.out::println);
// May print in a different order than A, B, C, D.
~~~

### Wrong: writing into a shared ArrayList

~~~java
import java.util.ArrayList;

List<String> output = new ArrayList<>();

items.parallelStream()
        .forEach(output::add); // Unsafe.
~~~

`ArrayList` does not guarantee safe concurrent updates. Failures can include lost elements, inconsistent writes, or hard-to-reproduce bugs.

### Right: use a terminal operation with a collection contract

~~~java
List<String> output = items.parallelStream()
        .map(String::toLowerCase)
        .toList();

System.out.println(output); // [a, b, c, d]
~~~

`toList()` preserves the encounter order of an ordered Stream and returns an unmodifiable list (Java 16+). If a mutable list is required, use a collector requesting a new container:

~~~java
import java.util.ArrayList;
import java.util.stream.Collectors;

ArrayList<String> editable = items.parallelStream()
        .map(String::toLowerCase)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

With standard `collect`, Stream coordinates accumulation containers and result merging per the collector contract; multiple tasks never concurrently mutate one external `ArrayList`.

### Thread-safe is not automatically semantically right

Using `Collections.synchronizedList(...)` may eliminate race conditions on individual `add` calls, yet **the order of `add` calls is still not encounter order**. Synchronization can also wipe out parallel speedup.

If the requirement is creating an ordered list, `map(...).toList()` or `collect(...)` fits better. If the requirement is side effects like sending notifications, address idempotency, ordering, and retries separately; Stream provides no transactional contract for external actions.

## 7. forEachOrdered and the limits of ordering guarantees

When an action strictly must execute in encounter order, you can use `forEachOrdered`:

~~~java
import java.util.List;

List<String> names = List.of("Lan", "Minh", "An");

names.parallelStream()
        .forEachOrdered(System.out::println);

// Lan
// Minh
// An
~~~

`forEachOrdered` guarantees actions execute in encounter order on an **ordered Stream**. It also establishes a *happens-before* relationship between consecutive actions in that order. However:

- It **does not** guarantee all upstream `map`/`filter` steps run sequentially in source order.
- It **does not** guarantee all actions run on the same thread.
- Enforcing order can reduce speedup because tasks must coordinate.
- On a Stream without encounter order, you cannot demand a logical order the source never declared.

If you merely need a `List` for later use, collecting with `toList()` usually expresses intent better than emitting side effects via `forEachOrdered`.

## 8. findFirst, findAny, and short-circuiting operations

When switching to parallel, pay special attention to **outputs that the API contract allows to vary**.

~~~java
import java.util.List;
import java.util.Optional;

List<String> names = List.of("A", "B", "C");

Optional<String> first = names.parallelStream().findFirst();
Optional<String> any = names.parallelStream().findAny();

System.out.println(first.orElseThrow()); // A
// any could be A, B, or C.
~~~

`findFirst()` takes the first element in encounter order if the Stream is ordered. `findAny()` intentionally allows picking any matching element to enable more flexible parallel execution.

| Terminal operation | Stopping / result criterion | Under parallel execution |
| --- | --- | --- |
| `findFirst()` | First element in encounter order; unordered has no defined first | May need coordination to select the true first element. |
| `findAny()` | Any matching element in the result | May return different elements across runs. |
| `anyMatch(p)` | Whether at least one element satisfies `p` | Boolean result remains logically consistent when predicate is pure. |
| `allMatch(p)` | Whether all elements satisfy `p` | Boolean result remains logically consistent when predicate is pure. |
| `noneMatch(p)` | Whether no elements satisfy `p` | Boolean result remains logically consistent when predicate is pure. |

Match operations can short-circuit, yet **make no promise about predicate call counts** or the order elements are tested. Even after sufficient evidence is found to return a result, some running tasks may finish or be canceled depending on implementation mechanics.

Therefore, never attach side effects that must run **exactly once per element** inside a predicate passed to `anyMatch`, `allMatch`, or `findAny`.

## 9. limit, skip, takeWhile, dropWhile: preserving prefix semantics

On a Stream with encounter order, prefix-taking or prefix-dropping operations must respect logical order.

~~~java
import java.util.List;
import java.util.stream.IntStream;

List<Integer> firstFive = IntStream.range(0, 100)
        .parallel()
        .limit(5)
        .boxed()
        .toList();

System.out.println(firstFive); // [0, 1, 2, 3, 4]
~~~

`limit(5)` on an ordered Stream returns the **first five elements in encounter order**, not whichever five elements any thread finishes fastest. `skip(5)` similarly drops the first five elements in source order. Enforcing this can incur synchronization cost, particularly on ordered parallel Streams.

~~~java
List<Integer> afterSkip = IntStream.range(0, 10)
        .parallel()
        .skip(5)
        .boxed()
        .toList();

System.out.println(afterSkip); // [5, 6, 7, 8, 9]
~~~

Since Java 9, `takeWhile` and `dropWhile` also enforce **prefix** rules on ordered sources:

~~~java
List<Integer> prefix = IntStream.range(0, 10)
        .parallel()
        .takeWhile(n -> n < 4)
        .boxed()
        .toList();

System.out.println(prefix); // [0, 1, 2, 3]
~~~

If you call `unordered()`, operations such as `limit`, `takeWhile`, or `dropWhile` can behave differently because **the encounter-order prefix constraint no longer applies**. `unordered()` is not a "harmless speedup button"; it alters the guarantees your program may rely upon.

With an inherently unordered source, if you only need **any N elements** for testing or sampling rather than the exact first N, relaxing ordering can make sense. Conversely, if the requirement is "the first 100 orders chronologically," a deterministic chronological order must be present and must not be discarded casually.

## 10. reduce: identity, associativity, and combiner

For `reduce`, the primary condition for correct parallel execution is an **associative** combining operation with an appropriate identity.

Example summing integers from a finite source:

~~~java
import java.util.List;

List<Integer> values = List.of(1, 2, 3, 4);

int sequential = values.stream()
        .reduce(0, Integer::sum);

int parallel = values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(sequential); // 10
System.out.println(parallel);   // 10
~~~

For `int`, addition obeys Java's integer overflow rules; if sums can exceed bounds, pick a wider numeric type or handle overflow per business rules. Either way, `Integer::sum` is a valid associative operation for reduction under Java integer addition semantics.

### A wrong identity causes repeated additions

~~~java
// Wrong: 10 is not an identity for addition.
int bad = values.parallelStream()
        .reduce(10, Integer::sum);
~~~

Sequentially, this computes `10 + 1 + 2 + 3 + 4 = 20`. When split into partitions, however, each branch may start from identity `10`, adding 10 multiple times; the result is not guaranteed to match the intent "add 10 once."

Right approach:

~~~java
int result = 10 + values.parallelStream()
        .reduce(0, Integer::sum);

System.out.println(result); // 20
~~~

The identity must be **neutral for the combiner**; business offsets should be added outside the reduction if they are not an identity element.

### Subtraction is not associative

~~~java
// Do not use this pattern expecting the same result as sequential:
int result = values.parallelStream()
        .reduce(0, (a, b) -> a - b);
~~~

With subtraction, `(a - b) - c` differs from `a - (b - c)`. Changing how elements are grouped changes the result, violating the parallel reduction contract.

If the goal is negating the sum, express it with associative addition and negate afterward:

~~~java
int negativeSum = -values.parallelStream()
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(negativeSum); // -10
~~~

Cases like `Integer.MIN_VALUE` and overflow require separate handling if business rules disallow overflow; rewriting the operation alone does not eliminate all range limits.

## 11. Three-argument reduce: accumulator must be compatible with combiner

Overload:

~~~java
<U> U reduce(
        U identity,
        BiFunction<U, ? super T, U> accumulator,
        BinaryOperator<U> combiner);
~~~

Allows transforming a `Stream<T>` into a result `U` of a different type than the elements.

~~~java
import java.util.List;

List<String> words = List.of("Java", "Stream", "API");

long countLetters = words.parallelStream()
        .reduce(
                0L,
                (sum, word) -> sum + word.length(),
                Long::sum
        );

System.out.println(countLetters); // 13
~~~

Three conditions to remember:

~~~text
combine(identity, u) = u

combine(combine(a, b), c) = combine(a, combine(b, c))

combine(u, accumulate(identity, t)) = accumulate(u, t)
~~~

The first condition is a **neutral identity**, the second is **combiner associativity**, and the third is **compatibility between accumulator and combiner**. For total string length, all three rest on addition.

An easy bug is using addition in the accumulator while multiplying in the combiner, or passing identity `10` for addition. Sequential runs may look fine because the combiner is rarely exercised, whereas parallel runs combine into wrong results.

When computing a single scalar metric, a primitive stream such as `mapToLong(String::length).sum()` is shorter and avoids boxing. The three-argument overload shines when constructing an **immutable multi-field result** with a clear function to merge two partial results.

## 12. Floating-point and rounding: "correct" depends on the arithmetic contract

Not all addition operations share identical properties on a computer.

### 12.1. Double addition can produce small differences

~~~java
double a = 1.0e16;
double b = -1.0e16;
double c = 1.0;

System.out.println((a + b) + c); // 1.0
System.out.println(a + (b + c)); // 0.0
~~~

Although mathematical real-number addition is associative, `double` addition undergoes binary floating-point rounding and is **not strictly associative**. When Stream alters how partial sums are split and merged, results can differ in the trailing digits.

~~~java
double total = valuesAsDoubles.parallelStream()
        .mapToDouble(Double::doubleValue)
        .sum();
~~~

This snippet assumes `valuesAsDoubles` is a `Double` collection. `DoubleStream.sum()` may use accuracy-improving strategies, yet floating-point sums must not be treated as bitwise invariant across all evaluation orders or implementations. Define an acceptable tolerance when business logic uses floating-point numbers.

### 12.2. For money, use BigDecimal and round only at the business boundary

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

List<BigDecimal> amounts = List.of(
        new BigDecimal("0.005"),
        new BigDecimal("0.005"),
        new BigDecimal("0.005")
);

BigDecimal exact = amounts.parallelStream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);

BigDecimal payable = exact.setScale(2, RoundingMode.HALF_UP);

System.out.println(payable); // 0.02
~~~

`BigDecimal::add` without a `MathContext` performs exact decimal addition. Therefore partitions can be summed and merged without losing numerical value. Rounding **after reduction** matches the policy "sum exactly, round the total once."

If the application rounds each item before summing, the result differs (three times `0.005 -> 0.01` gives `0.03`). Both policies can be valid in different business domains, yet they must never be swapped during optimization.

**Avoid rounding inside the combiner/accumulator** if you want addition to remain associative in numerical value. Every intermediate rounding step can make the outcome depend on how elements are grouped.

## 13. collect: distinguishing mutable reduction from shared state

A collector is designed to **accumulate** data and may use mutable internal containers. This differs from creating a shared container yourself and mutating it inside `forEach`.

Example grouping products by category:

~~~java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Product(String sku, String category) {}

List<Product> products = List.of(
        new Product("PEN", "OFFICE"),
        new Product("BOOK", "EDUCATION"),
        new Product("PAD", "OFFICE")
);

Map<String, List<Product>> byCategory = products.parallelStream()
        .collect(Collectors.groupingBy(Product::category));

System.out.println(byCategory.get("OFFICE").size()); // 2
~~~

`groupingBy` is a standard collector that merges intermediate results per contract. However, using `groupingBy` **does not mean** the returned Map is a concurrent Map, nor does it guarantee Map implementation type or thread-safety for later updates by the caller.

When you need a `List`, choose:

~~~java
List<String> codes = products.parallelStream()
        .map(Product::sku)
        .toList();
~~~

Or use a collector requesting a modifiable list:

~~~java
import java.util.ArrayList;

ArrayList<String> editableCodes = products.parallelStream()
        .map(Product::sku)
        .collect(Collectors.toCollection(ArrayList::new));
~~~

### Wrong: reduce with a single mutable container

~~~java
// Wrong for parallel reduction: a mutable identity may be shared.
List<String> wrong = products.parallelStream()
        .reduce(
                new ArrayList<String>(),
                (list, p) -> {
                    list.add(p.sku());
                    return list;
                },
                (left, right) -> {
                    left.addAll(right);
                    return left;
                }
        );
~~~

Three-argument `reduce` requires the accumulator to return a new `U` value according to a combining operation; mutating a shared mutable identity violates the prerequisites when branches combine. Choose `collect` for mutable structures or an immutable result type suited to `reduce`.

## 14. groupingByConcurrent, toConcurrentMap, and ordering trade-offs

Java provides collectors designed for concurrency, such as `groupingByConcurrent` and `toConcurrentMap`:

~~~java
import java.util.concurrent.ConcurrentMap;
import java.util.stream.Collectors;

ConcurrentMap<String, Long> counts = products.parallelStream()
        .collect(Collectors.groupingByConcurrent(
                Product::category,
                Collectors.counting()
        ));

System.out.println(counts.get("OFFICE")); // 2
~~~

`groupingByConcurrent` returns a `ConcurrentMap` and uses a **concurrent, unordered** collector. This fits when the output is counts by key and **preserving appearance order within each group is not required**.

If you must keep lists in a specific order, never replace `groupingBy` with `groupingByConcurrent` assuming element order inside groups stays identical. Faster execution is not guaranteed either, because tasks may contend on the same key.

With `toConcurrentMap`, when multiple elements share a key, provide an associative merge function with a clear business rule:

~~~java
import java.util.concurrent.ConcurrentMap;

ConcurrentMap<String, Integer> occurrences = products.parallelStream()
        .collect(Collectors.toConcurrentMap(
                Product::category,
                p -> 1,
                Integer::sum
        ));
~~~

`ConcurrentMap` does not make a mapper/predicate safe if it mutates external state. The collector organizes internal Map updates per contract, while application-written side effects must still be managed separately.

## 15. distinct, sorted, and stateful operations

Some intermediate operations maintain state or coordinate across multiple elements:

| Operation | Meaning | Parallel considerations |
| --- | --- | --- |
| `distinct()` | Retains distinct elements | On ordered Streams, must keep the first occurrence in encounter order; may need state/coordination. |
| `sorted()` | Sorts by comparator or natural order | May need to buffer data and merge/sort parts. |
| `limit(n)`, `skip(n)` | Takes/drops elements by order when encounter order exists | Can incur coordination cost to respect prefixes. |
| `takeWhile`, `dropWhile` | Processes prefix by predicate on ordered Streams | Hard to partition effectively when exact cut points must be found. |
| `map`, `filter` with pure lambdas | Transforms/evaluates elements independently | Usually favorable for partitioning. |

Stateful operations are **not wrong simply because they run in parallel**. The issue is that they can erode parallel gains or cause the pipeline to buffer more memory.

Example:

~~~java
List<Integer> sortedDistinct = List.of(3, 1, 3, 2)
        .parallelStream()
        .distinct()
        .sorted()
        .toList();

System.out.println(sortedDistinct); // [1, 2, 3]
~~~

The result has clear semantics, though on a tiny set like this, parallel execution is not performance-beneficial.

If you drop `ORDERED` with `unordered()` to optimize, ensure representative selection in `distinct` and subsequent operations still meet requirements. `sorted()` can establish a new output order, yet that does not make all prior behaviors ordered.

## 16. Sources, Spliterator, and splittability

Parallel Streams operate through the source's `Spliterator`. A Spliterator with an effective `trySplit()` generally distributes tasks more evenly.

| Source | Typical splittability | Key reminder |
| --- | --- | --- |
| `ArrayList` or array | Splits by index/range | Usually suitable for pure, sufficiently large compute pipelines. |
| `IntStream.range` / `LongStream.range` | Range-based numeric source, splits into subranges | Favorable for independent per-element work. |
| `HashSet` | Splittable, yet has no guaranteed encounter order | Do not infer stable ordering. |
| `Iterator` wrapped by `Spliterators.spliteratorUnknownSize` | May need to pre-read into batches to split | Reading the underlying Iterator can be a sequential bottleneck. |
| I/O Streams like `Files.lines` | Depends on source, encoding, splittability, and I/O cost | Parallel does not automatically make file reading faster. |

Characteristics such as `SIZED`, `SUBSIZED`, `ORDERED`, `IMMUTABLE`, and `CONCURRENT` influence optimizations the implementation can apply. **Misdeclaring characteristics** in a custom Spliterator is a source bug, not something `parallel()` fixes.

A source that only produces elements sequentially from a network or database cursor can struggle to benefit from parallel execution. Even when `map` is heavy, pulling elements from the Iterator can remain the shared bottleneck.

## 17. I/O, transactions, atomicity, and failure behavior

A pipeline may look data-independent while its mapper performs I/O or updates external state:

~~~java
// Illustrative only: sendNotification is an operation with side effects.
orders.parallelStream()
        .forEach(order -> sendNotification(order));
~~~

With this approach, **dispatch order** is not guaranteed. If one task throws an exception, there is no built-in rollback for notifications already sent by other tasks. Running tasks may also have produced side effects before the caller observes the error.

Therefore, consider a two-step design:

1. **Compute and determine what needs processing** using a Stream with pure functions, producing an explicit list of requests.
2. **Execute side effects** using mechanisms suited to transactions, retries, idempotency, concurrency limits, and ordering requirements.

Do not treat parallel Streams as an I/O orchestration framework with timeouts, backpressure, retry counts, or distributed task management. Those properties must be designed at the task layer when the problem requires them.

### Streams from I/O sources still must be closed

~~~java
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.stream.Stream;

Path path = Path.of("events.log");

try (Stream<String> lines = Files.lines(path, StandardCharsets.UTF_8)) {
    long errors = lines.parallel()
            .filter(line -> line.startsWith("ERROR"))
            .count();
}
~~~

`count()` is a terminal operation yet does not replace `close()` on resource-backed streams. `try-with-resources` remains necessary whether the pipeline runs sequentially, in parallel, short-circuits, or throws an exception.

## 18. Complete example: safely parallelizing a revenue report

Suppose a system needs to sum revenue per customer from sales lines. Each line has a customer ID, quantity, and unit price. Requirements:

- Result is `Map<String, BigDecimal>`, independent of processing order.
- Compute line totals using exact decimal arithmetic.
- No intermediate rounding and no mutation of source data.
- When displaying, round per business policy only **after** aggregation.

~~~java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

public class ParallelRevenueDemo {

    record Sale(String customerId, long quantity, BigDecimal unitPrice) {}

    static Map<String, BigDecimal> revenueByCustomer(
            List<Sale> sales, boolean parallel) {

        var source = parallel
                ? sales.parallelStream()
                : sales.stream();

        return source.collect(Collectors.groupingBy(
                Sale::customerId,
                Collectors.reducing(
                        BigDecimal.ZERO,
                        sale -> sale.unitPrice()
                                .multiply(BigDecimal.valueOf(sale.quantity())),
                        BigDecimal::add
                )
        ));
    }

    public static void main(String[] args) {
        List<Sale> sales = List.of(
                new Sale("C-01", 2, new BigDecimal("10.50")),
                new Sale("C-02", 3, new BigDecimal("2.00")),
                new Sale("C-01", 1, new BigDecimal("9.50"))
        );

        Map<String, BigDecimal> sequential =
                revenueByCustomer(sales, false);

        Map<String, BigDecimal> parallel =
                revenueByCustomer(sales, true);

        System.out.println(sequential.equals(parallel)); // true
        System.out.println(parallel.get("C-01"));          // 30.50
        System.out.println(parallel.get("C-02"));          // 6.00

        BigDecimal payableC01 = parallel.get("C-01")
                .setScale(2, RoundingMode.HALF_UP);
        System.out.println(payableC01); // 30.50
    }
}
~~~

Why this can be converted to parallel:

1. **The source** is a `List` unmutated during processing, with an appropriate Spliterator.
2. `sale -> ...` is an independent computation writing to no external mutable variables.
3. `groupingBy` uses a standard collector to accumulate and merge intermediate results.
4. `BigDecimal::add` (without `MathContext`) is exact decimal addition, valid for combining partial sums.
5. **No dependence on Map iteration order**. The problem only asks for a customer → total amount mapping.
6. `setScale` is applied **after** aggregation completes, at the business boundary.

For large datasets, you must still benchmark in a suitable environment to decide whether parallel mode actually performs better. This example proves **semantic preservation**, not speedup.

> **Version note:** `record` and `Stream.toList()` require Java 16+; `var` requires Java 10+. The Java Stream API, `parallelStream`, `Collectors.groupingBy`, and `reducing` have been available since Java 8. On Java 8, replace `record` with a class, declare `Stream<Sale>` instead of `var`, and use `collect(Collectors.toList())` instead of `toList()` where needed.

## 19. Strategy for testing equivalence before and after parallelization

Separate **guaranteed semantics** from implementation details that should not be asserted.

### 19.1. Comparing according to the result contract

For the revenue report:

~~~java
Map<String, BigDecimal> expected = revenueByCustomer(sales, false);
Map<String, BigDecimal> actual = revenueByCustomer(sales, true);

if (!expected.equals(actual)) {
    throw new AssertionError("Parallel result differs");
}
~~~

Assuming `sales` is the collection with the same data as the previous example. For testing `BigDecimal`, distinguish numerical comparison (`compareTo`) from scale-sensitive comparison (`equals`); in the example, exact addition on identical data yields results suited to direct comparison. If business policy mandates a fixed scale, normalize scale before asserting equivalence.

For `Set`, verify set membership; for `Map`, verify key–value mappings; for `List` with encounter order, verify order too; for `findAny()`, only check that the returned element belongs to the valid set rather than asserting one fixed value.

### 19.2. Testing fragile edge cases

- **Empty, single-element, and very large sources**: verify identity, grouping logic, and data bounds.
- **Many duplicate keys**: verify merge functions, grouping collectors, and accurate sums.
- **Equal elements, nulls, negative numbers, large numbers**: check input contracts; `null` is not automatically safe.
- **Sources with/without encounter order**: verify results do not accidentally rely on unguaranteed ordering.
- **Repeated test runs**: helps expose race conditions, though never proves absence of bugs.
- **Errors in mappers/I/O**: clarify error reporting and what side effects may have already occurred.
- **No source mutation during traversal**: keep input data stable throughout measurements and tests.

Never write tests asserting `Thread.currentThread().getName()` or thread counts: Streams do not promise fixed thread counts, schedules, or degrees of parallelism.

### 19.3. Distinguishing correctness tests from benchmarks

Equivalence tests answer: **Does the result satisfy the contract?**

Benchmarks answer: **On this dataset and environment, is the pipeline faster?**

Both questions must be answered independently; never treat speed as proof of correctness, nor assume a semantically correct pipeline automatically benefits from parallelism.

## 20. When is parallelStream() genuinely worth using?

Speedup opportunities exist when:

- The source is **large, finite, and splits evenly** into independent chunks.
- Each element requires **substantial CPU computation**.
- Mappers and predicates are stateless and independent of invocation order.
- The terminal operation can merge results efficiently.
- Memory and task-management overhead do not become bottlenecks.

Do not expect speedup when:

- The dataset is tiny, e.g., a few dozen elements with lightweight math.
- Sources such as Iterators/cursors must be read sequentially to produce elements.
- The pipeline contains multiple stateful operations or strict encounter-order requirements.
- Lambdas frequently hit synchronized locks, databases, networks, or bounded I/O resources.
- Collectors contend on hot keys, or merging partial results is very costly.
- The program shares CPU resources with many latency-sensitive tasks.

### How to measure?

In Java environments capable of benchmarking, use dedicated tools such as **JMH** to avoid distortions from JIT warm-up, dead-code elimination, CPU load, and GC. A single `System.nanoTime()` measurement is rarely conclusive.

Measure **time**, **allocation/memory rate**, **tail latency**, and impact on other tasks. On servers handling many concurrent requests, parallelizing individual requests can cause resource contention even when an isolated benchmark looks faster.

`parallelStream()` typically uses fork/join and the common pool depending on the JDK implementation, yet business logic must never rely on thread count or pool names. When strict concurrency, timeout, backpressure, or per-request resource isolation is required, consider a dedicated task architecture instead of defaulting everything to parallel Streams.

## 21. Common pitfalls and fixes table

| Symptom | Why it happens | How to fix |
| --- | --- | --- |
| Missing elements when adding to `ArrayList` | Multiple threads call `add` unsafely on the same container | Use `toList` or standard `collect`. |
| Used `AtomicInteger` yet sequence numbers are scrambled | Atomicity does not guarantee encounter order | Derive indices from a stable source, e.g., `IntStream.range`. |
| `forEach` prints out of order | Execution order is unguaranteed when parallel | Use `forEachOrdered` if ordered side effects are truly required; use `toList` for lists. |
| `findAny` sometimes returns a different element | By contract, may pick any matching element | If the first element of an ordered source is needed, use `findFirst`. |
| `limit` returns unexpected subset | Source is unordered or `unordered()` was called | Preserve encounter order or sort explicitly per requirements. |
| `double` sum differs in trailing digits | Floating-point addition is not strictly associative | Define tolerance; use `BigDecimal` if exact decimals are needed. |
| Parallel `reduce` returns wrong answer | Identity is not neutral or combiner is incompatible | Use contract-compliant associative ops; test across groupings. |
| Duplicated/lost data in mutable reduce | Shared mutable identity mutated in place | Use immutable reduction or `collect` for mutable containers. |
| `groupingByConcurrent` alters list order | Unordered collector does not maintain required encounter order | Use `groupingBy`/an order-preserving downstream if order matters. |
| Slower than sequential | Split/merge overhead, stateful ops, small data, or contention | Benchmark after ensuring correctness; consider staying sequential. |
| External queries/writes run out of order or partially | Side effects in mapper/forEach lack shared transactions | Separate pure calculations from orchestrated I/O execution. |
| Files stay open after terminal operation | `parallel` and `count` do not auto-close sources | Use `try-with-resources` for I/O sources. |

## 22. Self-check exercises

### Exercise 1 — Which pipeline preserves result order?

~~~java
List<Integer> values = List.of(4, 1, 3, 2);

List<Integer> a = values.stream()
        .map(n -> n * 2)
        .toList();

List<Integer> b = values.parallelStream()
        .map(n -> n * 2)
        .toList();
~~~

**Answer:** Both `a` and `b` are `[8, 2, 6, 4]`. The `List` source has encounter order; `map` is an independent transformation; `toList()` preserves encounter order. Mapper execution order cannot be inferred from result order.

### Exercise 2 — Race condition or semantic error?

~~~java
AtomicInteger counter = new AtomicInteger();

List<String> ids = names.parallelStream()
        .map(name -> counter.incrementAndGet() + "-" + name)
        .toList();
~~~

**Answer:** `AtomicInteger` prevents lost increments from counter races, yet the numbers attached to names are not guaranteed to match encounter-order positions. This is a **numbering semantics bug**, not just an update-safety bug. Choose a source with deterministic indices or assign sequence numbers in a separate step.

### Exercise 3 — Identity in reduce

~~~java
int sum = List.of(1, 2, 3).parallelStream()
        .reduce(5, Integer::sum);
~~~

**Answer:** `5` is not an identity for addition; this reduction violates the contract for "sum of elements plus 5 once." Use `5 + stream.reduce(0, Integer::sum)`.

### Exercise 4 — Choosing findFirst or findAny

A system needs the **first customer in a sorted priority list**. Can you replace `findFirst()` with `findAny()` to go faster?

**Answer:** No, if "first" is a business requirement. `findAny` is allowed to return any element; use `findFirst` on an appropriately ordered Stream.

### Exercise 5 — Should unordered be placed before limit?

~~~java
List<Integer> first = IntStream.range(0, 10)
        .parallel()
        .unordered()
        .limit(3)
        .boxed()
        .toList();
~~~

**Answer:** You cannot require the result to always be `[0, 1, 2]`. `unordered()` drops the encounter-order constraint on the first three elements; `limit(3)` may select three different elements. If the first three numbers of the range are needed, remove `unordered()`.

### Exercise 6 — Should synchronizedList be used?

A developer replaces `new ArrayList<>()` with `Collections.synchronizedList(new ArrayList<>())` and runs `parallelStream().forEach(list::add)`. Does that guarantee the result follows encounter order?

**Answer:** Not yet. The `add` calls are synchronized at the collection level, yet still arrive in non-deterministic execution order. If a list in source order is needed, use `toList()` or an appropriate collector.

### Exercise 7 — Money sum and rounding

Three amounts are all `0.005`. A sequential pipeline rounds after summing to get `0.02`. Can it be converted to a parallel stream?

**Answer:** Yes, provided `reduce` uses `BigDecimal.ZERO` and **exact** `BigDecimal::add`, and `setScale(2, HALF_UP)` runs only **after** reduction. Do not put rounding inside each accumulator/combiner because it can break associativity.

### Exercise 8 — I/O task

A pipeline calls a payment API inside `forEach`, and is switched from `stream()` to `parallelStream()`. Is that sufficient for safe speedup?

**Answer:** Not yet. You must consider idempotency, concurrency limits, transactions, processing order, timeouts, retries, and partial side effects occurring before another task throws an error. Parallel Streams do not handle those contracts automatically.

## 23. Takeaway

- `parallel()` or `parallelStream()` changes **how work executes**, without permitting arbitrary changes to business semantics.
- Lambdas in `map`, `filter`, and processing stages should be **stateless and non-interfering**, never mutating the source or relying on external mutable state.
- Distinguish **encounter order**, **execution order**, and **result order**. `forEach` does not preserve order; `forEachOrdered` enforces action order; `toList` preserves encounter order of an ordered Stream.
- `findFirst` and `findAny` have different contracts; `unordered()` can change the meaning of `limit`, `takeWhile`, and prefix operations.
- `reduce` needs a neutral identity, an associative combiner, and compatible accumulator/combiner. `collect` suits mutable reduction; never pass a shared mutable identity to `reduce`.
- `double` addition can diverge due to grouping; for exact decimals such as money, use `BigDecimal` appropriately and round at the right business boundary.
- Spliterators, stateful operations, concurrent collectors, side effects, and I/O sources determine suitability and performance of parallel pipelines.
- **Test correctness first, benchmark second.** Never assume a parallel Stream is always faster, even when semantically valid.

**Key point:** Converting a sequential pipeline to parallel is safe when the result **does not depend on execution scheduling or work split–combine boundaries** beyond differences permitted by the API contract. Clarify required ordering, keep lambdas free of shared state, use contract-compliant reductions/collectors, and measure performance only after verifying correctness.