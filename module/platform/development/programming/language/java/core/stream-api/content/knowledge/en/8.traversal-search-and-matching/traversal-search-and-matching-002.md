# Finding Extrema with `min` and `max`

> **Chapter:** Traversal, Search, and Matching  
> **Module:** `JAVA_STREAM_API` — declarative data processing with the Java Stream API, from lazy pipelines, `filter`, `map`, `reduce`, and `collect` to grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers. Applying it effectively requires understanding limits around state, resources, and performance.

In applications, we frequently need to answer questions such as: **which product is the cheapest**, **which order has the highest value**, **which employee has the longest tenure**, or **what is the smallest value in a stream of numbers**. With the Java Stream API, `min` and `max` express these requirements without manually writing loops to traverse and update an extremum variable.

After this lesson, you will be able to find extrema of objects using `Comparator`, work safely with `Optional`, find extrema on primitive streams, handle tie-breaking cases, and decide when to use `min`/`max` instead of `sorted`.

## 1. What Do `min` and `max` Return?

On `Stream<T>`, the two methods have the signatures:

```java
Optional<T> min(Comparator<? super T> comparator)
Optional<T> max(Comparator<? super T> comparator)
```

They are **terminal operations** belonging to the **reduction** category: after the stream's elements are processed through the pipeline, they combine to select **one extremum element according to the provided `Comparator`**.

| Operation | Which Element Is Selected? | Return Type |
| --- | --- | --- |
| `stream.min(comparator)` | The element considered **smallest** under the comparator's ordering | `Optional<T>` |
| `stream.max(comparator)` | The element considered **largest** under the comparator's ordering | `Optional<T>` |
| `intStream.min()`, `intStream.max()` | Smallest / largest `int` number | `OptionalInt` |
| `longStream.min()`, `longStream.max()` | Smallest / largest `long` number | `OptionalLong` |
| `doubleStream.min()`, `doubleStream.max()` | Smallest / largest `double` number | `OptionalDouble` |

**Why return `Optional`?** Because a Stream can be empty (for example, after `filter` leaves no elements), in which case no extremum exists. Rather than assuming an element exists, the caller must explicitly handle the absent result.

Short example:

```java
import java.util.Comparator;
import java.util.List;

List<Integer> numbers = List.of(7, 2, 9, 4, 2);

int minimum = numbers.stream()
        .min(Comparator.naturalOrder())
        .orElseThrow();

int maximum = numbers.stream()
        .max(Comparator.naturalOrder())
        .orElseThrow();

System.out.println(minimum); // 2
System.out.println(maximum); // 9
```

In this example, `Comparator.naturalOrder()` uses `Integer`'s natural ordering. Both operations require a **fresh** Stream from `numbers.stream()`, because a Stream consumed by a terminal operation cannot be reused.

## 2. `Comparator` Defines “Smallest” and “Largest”

A `Comparator<T>` is a rule for comparing two values of type `T`. The contract of `compare(a, b)`:

- Returns a **negative** number if `a` comes before `b`.
- Returns **0** if they are considered equivalent under the comparison rule.
- Returns a **positive** number if `a` comes after `b`.

Accordingly, `min` picks the element that comes first and `max` picks the element that comes last according to the comparator. “Smaller” does not have to be numeric: you can compare by string length, price, creation date, stock quantity, or multiple consecutive keys.

```java
List<String> words = List.of("Java", "API", "Stream", "JVM");

String shortest = words.stream()
        .min(Comparator.comparingInt(String::length)
                .thenComparing(Comparator.naturalOrder()))
        .orElseThrow();

// "API" (among 3-character strings, API comes before JVM).
```

`comparingInt(String::length)` compares by length first; `thenComparing(...)` defines how to break ties when two strings have the same length. If no secondary criterion is needed, you can write `.min(Comparator.comparingInt(String::length))`, though which element gets picked among tied elements should not be assumed to be the first one encountered.

## 3. Complete Example: Finding the Cheapest, Most Expensive, and Highest-Stock Product

The following Java 17+ program can be saved to `StreamExtremaDemo.java` and run standalone:

```java
import java.math.BigDecimal;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class StreamExtremaDemo {
    record Product(String code, String name, BigDecimal price, int stock) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
                new Product("P-01", "Java Fundamentals",
                        new BigDecimal("210000"), 12),
                new Product("P-02", "Java Stream API",
                        new BigDecimal("295000"), 7),
                new Product("P-03", "JVM Engineering",
                        new BigDecimal("390000"), 5),
                new Product("P-04", "Java Optimization",
                        new BigDecimal("390000"), 9),
                new Product("P-05", "Functional Programming",
                        new BigDecimal("250000"), 18)
        );

        // Compare price first; if prices are equal, compare code for a deterministic result.
        Comparator<Product> byPriceThenCode = Comparator
                .comparing(Product::price)
                .thenComparing(Product::code);

        Optional<Product> cheapest = products.stream()
                .min(byPriceThenCode);

        Optional<Product> mostExpensive = products.stream()
                .max(byPriceThenCode);

        Optional<Product> highestStock = products.stream()
                .max(Comparator.comparingInt(Product::stock));

        // Consider only products priced at no more than 350,000.
        BigDecimal priceCeiling = new BigDecimal("350000");
        Optional<Product> highestPriceUnderCeiling = products.stream()
                .filter(p -> p.price().compareTo(priceCeiling) <= 0)
                .max(byPriceThenCode);

        System.out.println("Cheapest: "
                + cheapest.map(Product::code).orElse("none"));
        System.out.println("Most expensive: "
                + mostExpensive.map(Product::code).orElse("none"));
        System.out.println("Highest stock: "
                + highestStock.map(Product::code).orElse("none"));
        System.out.println("Most expensive under ceiling: "
                + highestPriceUnderCeiling.map(Product::code).orElse("none"));
    }
}
```

Output:

```text
Cheapest: P-01
Most expensive: P-04
Highest stock: P-05
Most expensive under ceiling: P-02
```

Because `P-03` and `P-04` share the same price of 390,000, the secondary key `Product::code` makes `max(byPriceThenCode)` choose `P-04`, which has the larger code in string order. This selection is a **business rule we intentionally defined**, not a behavior of `max` “always picking the last element in the source”.

The example also shows that `filter` can narrow the candidate set **before** finding extrema. After filtering for prices up to 350,000, `P-03` and `P-04` are no longer candidates; the highest price in the allowed set is `P-02`.

## 4. Comparing Objects by a Field Using `comparing`

Common `Comparator` variants:

| API | Purpose | Example |
| --- | --- | --- |
| `Comparator.naturalOrder()` | Compare types with natural ordering (`Integer`, `String`, ...) | `min(Comparator.naturalOrder())` |
| `Comparator.reverseOrder()` | Reverse natural ordering | `max(Comparator.reverseOrder())` |
| `Comparator.comparing(extractor)` | Compare by a `Comparable` key object | `comparing(Product::price)` |
| `Comparator.comparingInt(extractor)` | Compare by an `int` key | `comparingInt(Product::stock)` |
| `Comparator.comparingLong(extractor)` | Compare by a `long` key | `comparingLong(Event::timestamp)` |
| `Comparator.comparingDouble(extractor)` | Compare by a `double` key | `comparingDouble(Item::score)` |
| `thenComparing(...)` | Add a secondary key if the prior key is equal | `comparing(Product::price).thenComparing(Product::code)` |
| `reversed()` | Reverse the ordering of a comparator | `byPriceThenCode.reversed()` |

The examples `Event::timestamp` and `Item::score` are syntax illustrations; they require `Event` and `Item` types to have the corresponding methods in a real program.

Note on `reversed()`:

```java
Comparator<Product> byPrice = Comparator.comparing(Product::price);

// Both operations below select the lowest-priced product,
// given the same set of elements and no other tie-breaking rule.
Optional<Product> a = products.stream().min(byPrice);
Optional<Product> b = products.stream().max(byPrice.reversed());
```

Although `max(byPrice.reversed())` can yield the same price level as `min(byPrice)`, the first form `min(byPrice)` expresses intent more clearly. For elements considered equal by the comparator, add a secondary key if a specific deterministic result is required.

### Comparing `BigDecimal` and Avoiding Faulty Comparators

For monetary values of type `BigDecimal`, use `Comparator.comparing(Product::price)` or `price.compareTo(otherPrice)` to compare **numeric values**. `BigDecimal.equals` also checks `scale`, so `new BigDecimal("1.0").equals(new BigDecimal("1.00"))` is `false` even though `compareTo` returns `0`.

Avoid comparing two `int` numbers by returning their subtraction:

```java
// Can overflow integers; avoid using:
Comparator<Product> unsafe = (a, b) -> a.stock() - b.stock();

// Safer and clearer:
Comparator<Product> safe = Comparator.comparingInt(Product::stock);
```

If a comparator is inconsistent or depends on state that mutates during comparison, the extremum result may fail to reflect the intended ordering. Define stable, *transitive* comparison rules and avoid mutating the Stream source.

## 5. Ties: Why Secondary Rules Matter

Consider two products with the same price:

```text
P-03   390000
P-04   390000
```

If you only use:

```java
products.stream().max(Comparator.comparing(Product::price))
```

then both `P-03` and `P-04` are valid maximal elements according to the comparator. The `min`/`max` contract **does not guarantee** picking the earlier or later element when multiple elements tie for the extremum, especially during parallel execution.

When business logic requires reproducible selection, define an extra criterion:

```java
Comparator<Product> byPriceThenCode = Comparator
        .comparing(Product::price)
        .thenComparing(Product::code);

Product selected = products.stream()
        .max(byPriceThenCode)
        .orElseThrow();

// selected.code() = "P-04"
```

If the goal is to **retrieve all** products tied for the highest value, `max` alone is insufficient because it returns only one object. You can find the highest price and then filter elements matching that price:

```java
Optional<BigDecimal> maxPrice = products.stream()
        .map(Product::price)
        .max(BigDecimal::compareTo);

List<Product> tiedForHighestPrice = maxPrice
        .map(price -> products.stream()
                .filter(p -> p.price().compareTo(price) == 0)
                .toList())
        .orElseGet(List::of);

// [P-03, P-04] when displayed by each product's code.
```

This approach traverses the source multiple times, which suits reusable sources like `List`. For single-use sources (such as a Stream backed by an I/O resource), you must design a dedicated collector or reduction to handle ties in a single pass.

## 6. Using `Optional` Properly When a Stream May Be Empty

Example with no matching candidates:

```java
Optional<Product> expensive = products.stream()
        .filter(p -> p.price().compareTo(new BigDecimal("9999999")) > 0)
        .max(Comparator.comparing(Product::price));

System.out.println(expensive.isPresent()); // false
System.out.println(expensive.map(Product::code).orElse("not found"));
// not found
```

Ways to consume the result:

```java
// Perform an action only when an element is present:
expensive.ifPresent(p -> System.out.println(p.name()));

// Provide a fallback value when absent:
String code = expensive.map(Product::code).orElse("N/A");

// Or throw an error when absence is an exceptional condition:
Product required = expensive.orElseThrow(
        () -> new IllegalStateException("No matching product found"));
```

The last snippet **will throw an exception** because `expensive` is empty, so use it only on code paths where a result is strictly required. Avoid calling `get()` without checking, as it throws `NoSuchElementException` on `Optional.empty()`. In larger systems, returning `Optional<Product>` to the caller is usually clearer than inventing a dummy product or defaulting an extremum price to `0`.

**Note:** `Optional` is a container for **zero or one non-null value**. If Stream elements can be `null`, filter them out before computing extrema to avoid unexpected errors.

## 7. `IntStream`, `LongStream`, `DoubleStream`: Finding Extrema Without a Comparator

Primitive streams provide parameterless `min()` and `max()` methods returning `OptionalInt`, `OptionalLong`, or `OptionalDouble`. This is the right choice when you only need the extremum number and do not need to retain the original object.

```java
import java.util.IntSummaryStatistics;
import java.util.List;
import java.util.OptionalInt;

List<Integer> values = List.of(6, 3, 11, 4);

OptionalInt minValue = values.stream()
        .mapToInt(Integer::intValue)
        .min();

OptionalInt maxValue = values.stream()
        .mapToInt(Integer::intValue)
        .max();

System.out.println(minValue.orElseThrow()); // 3
System.out.println(maxValue.orElseThrow()); // 11
```

With `Product` objects, to get the **highest stock count**:

```java
int maxStock = products.stream()
        .mapToInt(Product::stock)
        .max()
        .orElseThrow();

// 18
```

But to get the **product with the highest stock**, you must keep the object:

```java
Product item = products.stream()
        .max(Comparator.comparingInt(Product::stock))
        .orElseThrow();

// item.code() = "P-05"
```

Do not call `.mapToInt(Product::stock).max()` and then try to trace back to the product if the requirement is to return the object itself. When data has multiple tied candidates, tracing back can also introduce ambiguity.

If you simultaneously need `count`, `min`, `max`, `sum`, and `average` of **a numeric stream**, `summaryStatistics()` computes them all in a single pass:

```java
IntSummaryStatistics stats = products.stream()
        .mapToInt(Product::stock)
        .summaryStatistics();

System.out.println(stats.getMin());   // 5
System.out.println(stats.getMax());   // 18
System.out.println(stats.getCount()); // 5
```

For an empty source, `IntSummaryStatistics.getMin()` returns `Integer.MAX_VALUE` and `getMax()` returns `Integer.MIN_VALUE` because those are initial sentinel values, **not real extrema**. Always check `getCount() > 0` before interpreting these values as data results.

## 8. `min`/`max` vs `sorted`, `findFirst`, and `reduce`

Finding just **one** smallest element usually does not require sorting the entire source:

```java
// Find one cheapest product:
Optional<Product> cheapest = products.stream()
        .min(Comparator.comparing(Product::price));

// Sort by price then take the first element:
Optional<Product> firstAfterSort = products.stream()
        .sorted(Comparator.comparing(Product::price))
        .findFirst();
```

Both can yield a product with the **minimum price**, but they are not guaranteed to return the same object when multiple elements tie. For an ordered Stream, `sorted` is a *stable* sort so `findFirst` after `sorted` can retain the first element appearing in the tied price group; `min` makes no commitment to select by encounter order on ties.

| Aspect | `min(comparator)` / `max(comparator)` | `sorted(comparator).findFirst()` |
| --- | --- | --- |
| Primary goal | Select one extremum element | Sort and then select the first element |
| Typical complexity on finite unsorted source | `O(n)` comparisons | Usually `O(n log n)` for sorting |
| Typical extra memory sequentially | Can hold one current candidate: `O(1)` | May need a buffer holding many elements: `O(n)` |
| Result when empty | `Optional.empty()` | `Optional.empty()` |
| Multiple tied elements | Needs a secondary criterion if deterministic object selection is required | Stable sort on ordered Stream, but incurs sorting cost |

These are typical algorithmic characteristics, not assertions that a specific implementation always uses that exact amount of memory or comparisons. Stream implementations may optimize based on source characteristics and execution mode.

`min`/`max` can also be viewed as a reduction. However, `reduce` below is usually more verbose and requires deciding how to handle empty Streams yourself:

```java
Optional<Integer> minimum = List.of(7, 2, 9, 4).stream()
        .reduce(Integer::min);

// Optional[2]
```

If the problem is simply finding an extremum element using a comparator, prefer `min`/`max` to convey intent clearly. `reduce` is more useful when building other accumulation rules.

## 9. Combining `filter`, `map`, and Limiting the Extremum Scope

Operation order can change the meaning of the result:

```java
List<Integer> values = List.of(100, 7, 8, 4);

int minOfFirstTwo = values.stream()
        .limit(2)
        .min(Comparator.naturalOrder())
        .orElseThrow();
// 7

int globalMin = values.stream()
        .min(Comparator.naturalOrder())
        .orElseThrow();
// 4
```

`limit(2)` selects the **first two elements** beforehand, so `min` considers only the data that passed through. Conversely, without `limit`, `min` considers the whole source. Similarly, `filter(...).max(...)` finds the maximum **within the matching subset**, not the global maximum.

When using `map`, also be clear about whether you want to return a **value** or an **object**:

```java
// Get only the highest selling price:
BigDecimal highestPrice = products.stream()
        .map(Product::price)
        .max(BigDecimal::compareTo)
        .orElseThrow();

// Get the product object with the highest selling price:
Product highestPricedProduct = products.stream()
        .max(Comparator.comparing(Product::price)
                .thenComparing(Product::code))
        .orElseThrow();
```

The first example returns `BigDecimal`, while the second returns `Product`. This directly affects what data is available in subsequent steps.

## 10. `null`, Infinite Data, and Parallel Streams

### Handling `null` Before Comparing

A Stream containing `null` elements or a comparison key property with a `null` value easily causes a `NullPointerException`. The clearest approach when missing data is **ineligible** for extremum consideration is to filter it out first:

```java
import java.util.Objects;

Optional<Product> cheapestValid = products.stream()
        .filter(Objects::nonNull)
        .filter(p -> p.price() != null)
        .min(Comparator.comparing(Product::price));
```

If business rules genuinely require keeping elements with `null` keys, `Comparator.nullsFirst(...)` and `Comparator.nullsLast(...)` can define ordering for **null keys**. However, you must explicitly decide whether a null key counts as an extremum; `min` or `max` might pick an object whose price is missing purely due to that ordering rule.

### Infinite Sources

To confirm a maximum or minimum over an unbounded source, you generally must inspect every element; an infinite pipeline like `Stream.generate(...).min(...)` typically never terminates. If business logic only needs an extremum within a finite window, bound the source first:

```java
Optional<Integer> lowestOfFirst100 = java.util.stream.Stream
        .generate(() -> (int) (Math.random() * 100))
        .limit(100)
        .min(Comparator.naturalOrder());
```

This example only illustrates bounding the element count; random data generation makes the concrete result vary per run. If reproducible results are needed, use a deterministic data source.

### Parallel Processing

`min`/`max` can run with `parallelStream()`:

```java
Optional<Product> expensive = products.parallelStream()
        .max(Comparator.comparing(Product::price)
                .thenComparing(Product::code));
```

When the comparator is correct, stable, and defines an ordering among the candidates to compare, the extremum results under that rule can be combined across branches. However, **parallel is not automatically faster**: you must account for source size, comparison cost, task splitting, and result merging. Do not write comparators with side effects or dependencies on shared variables mutated while the pipeline runs.

## 11. Common Mistakes

| Mistake | Consequence | How to Handle |
| --- | --- | --- |
| Calling `.get()` on an `Optional` that may be empty | May throw `NoSuchElementException` | Use `orElseThrow`, `orElse`, `ifPresent`, or pass `Optional` to the caller. |
| Assuming `max` always picks the “last” element on tied prices | Concrete winner among tied elements is not guaranteed | Add a secondary criterion with `thenComparing`. |
| Using `mapToInt(...).max()` when the original object is needed | Only the maximum number remains; product reference is lost | Use `max(Comparator.comparingInt(...))`. |
| Using `sorted().findFirst()` just to find one extremum | Usually sorts and allocates more than necessary | Use `min`/`max`. |
| Using integer subtraction in a comparator | Can overflow and produce wrong ordering | Use `Integer.compare` or `comparingInt`. |
| Failing to filter `null` keys before `comparing` | May throw `NullPointerException` | Define a missing-data policy and filter or handle nulls intentionally. |
| Calling `min`/`max` multiple times on the same Stream variable | Stream is already consumed, may cause `IllegalStateException` | Create a new Stream from the source for each terminal operation. |
| Finding extrema on an infinite Stream without a stopping point | Pipeline may never terminate | Bound the scope with `limit` or design around a finite window. |

## 12. Self-Check

**Question 1.** Given `[7, 2, 9]`, what numeric value do `.min(Comparator.naturalOrder())` and `.max(Comparator.reverseOrder())` return?

**Answer:** Both return `2` (wrapped in `Optional<Integer>`), because `reverseOrder` reverses the definition of which element comes last.

**Question 2.** Why does `products.stream().max(Comparator.comparing(Product::price))` not always guarantee returning the exact same product when multiple products share the highest price?

**Answer:** The comparator treats them as equivalent, and the `max` contract does not specify which tied element to choose. For determinism, add a secondary key such as product code.

**Question 3.** If no product satisfies `filter`, what does `max` return?

**Answer:** `Optional.empty()`. Do not call `get()` without confirming an element is present.

**Question 4.** To get the product with the largest `stock`, which expression is right?

```java
// A: returns only the highest stock quantity
products.stream().mapToInt(Product::stock).max();

// B: returns the Product object with the highest stock
products.stream().max(Comparator.comparingInt(Product::stock));
```

**Answer:** B is right if you need the `Product`; A is right if you only need the integer.

**Question 5.** Why does `limit(3).min(...)` differ from `min(...)` on a source with more than three elements?

**Answer:** `limit(3)` changes the input set to the extremum search: `min` only considers the first three elements in encounter order, not the entire source.

## Key Takeaways

- `Stream.min(comparator)` and `Stream.max(comparator)` are **terminal reductions**, returning `Optional<T>`, even when the Stream is empty.
- `Comparator` defines the ordering for extrema. Use `comparing`, `comparingInt`, and `thenComparing` to express exact criteria, especially when multiple candidates tie.
- If you only need a numeric extremum, use primitive stream `min()`/`max()`; if you need to keep the object, call `min`/`max` on `Stream<T>` with a comparator.
- On finite unsorted sources, finding a single extremum typically scans data in one pass and uses less memory than sorting the whole dataset.
- Check empty cases, null keys, scope after `filter`/`limit`, and parallel overhead before applying to real-world data.
