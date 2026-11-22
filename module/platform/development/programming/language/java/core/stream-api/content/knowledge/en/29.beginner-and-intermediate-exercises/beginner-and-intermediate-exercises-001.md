# Converting Filtering, Mapping, and Summing Loops into Pipelines

> **Chapter:** Beginner and Intermediate Exercises  
> **Module:** `JAVA_STREAM_API` — learn declarative data processing with the Java Stream API through lazy pipelines, `filter`, `map`, `reduce`, and `collect`; progress to grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers, while recognizing limits related to state, resources, and performance.

In many Java programs, a `for` loop is used to iterate over a list, **select matching elements**, **compute the needed value**, and then **accumulate the total**. This is a great opportunity to practice the Java Stream API: the same task can be expressed with a `filter → mapToInt/mapToLong → sum` pipeline. The goal of converting is not to eliminate every loop, but to **preserve the exact business rules and results** while making each processing step explicit.

This lesson includes explanations, complete Java 17+ programs, common variations, and exercises with solutions. You will compare the `for` version and the Stream version on the same dataset to detect differences in values, ordering, or empty-data handling.

## 1. Sample Problem and Correctness Criteria

A sales system stores line items with a product SKU, paid status, quantity, and unit price in **Vietnamese Dong (VND)**. We need to calculate the **revenue of paid lines with a quantity of 3 or more**.

| Product SKU | Paid | Quantity | Unit Price (VND) | Included? | Calculated Line Amount |
| --- | --- | ---: | ---: | --- | ---: |
| `PEN` | Yes | 3 | 12.000 | Yes | 36.000 |
| `NOTE` | No | 5 | 50.000 | No | — |
| `RULER` | Yes | 2 | 8.000 | No | — |
| `ERASER` | Yes | 4 | 7.000 | Yes | 28.000 |
| `PEN` | Yes | 1 | 12.000 | No | — |

**Expected output:** `64_000L` VND, because `3 × 12_000 + 4 × 7_000 = 64_000`. The SKU `PEN` can appear multiple times; the problem calculates **per line**, without merging lines before applying the quantity condition.

Rules to preserve when converting to a Stream:

1. Iterate over the exact input collection.
2. Select only lines where **`paid == true` and `quantity >= 3`**.
3. Each qualifying line contributes **`quantity × unitPriceVnd`**.
4. Sum all amounts of the selected lines.
5. If no line qualifies, the total is **0**.
6. With standard `long` addition, both the loop and `LongStream.sum()` can **overflow**; a later section explains when overflow checks are needed.

## 2. Solving with a `for` Loop First

Here is the imperative solution:

```java
long total = 0L;

for (SaleLine line : lines) {
    if (line.paid() && line.quantity() >= 3) {
        long amount = (long) line.quantity() * line.unitPriceVnd();
        total += amount;
    }
}

System.out.println(total); // 64000
```

`SaleLine` and `lines` will be fully defined in Section 5. For now, note the structure:

- `for`: iterates over each line.
- `if`: keeps the lines matching the condition.
- `amount = ...`: maps a sale line to its line amount.
- `total += amount`: accumulates the amounts.

This loop is completely valid and easy to understand. Switching to a Stream is beneficial when you want to **clearly separate data operations**, making it convenient to add `filter` steps, change transformations, or combine with collectors.

## 3. Converting Step by Step to `filter → mapToLong → sum`

Each part of the loop corresponds to a Stream operation:

| Loop | Pipeline | Effect |
| --- | --- | --- |
| `for (SaleLine line : lines)` | `lines.stream()` | Creates the element source. |
| `if (line.paid() && line.quantity() >= 3)` | `.filter(line -> ...)` | Keeps elements matching the condition. |
| `long amount = ...` | `.mapToLong(line -> ...)` | Converts each sale line to a `long` amount. |
| `total += amount` | `.sum()` | Sums the mapped numbers; terminates the pipeline. |

```java
long total = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line -> (long) line.quantity() * line.unitPriceVnd())
        .sum();

System.out.println(total); // 64000
```

Visualizing the flow:

```text
 List<SaleLine>                     5 lines
       |
       v
    stream()                        Stream<SaleLine>
       |
       v
 filter(paid && quantity >= 3)       PEN x3, ERASER x4
       |
       v
 mapToLong(quantity * price)         36000, 28000
       |
       v
      sum()                          64000 (long)
```

### Why Use `mapToLong`?

`mapToLong` converts `Stream<SaleLine>` into a `LongStream`. `LongStream` has a terminal operation `sum()` that returns a primitive `long` directly, avoiding boxing into `Long` for every number.

If you use `map`, the result is a `Stream<Long>` (objects), which **does not have** a direct `sum()` method on `Stream<T>`:

```java
// Does not compile because Stream<Long> has no sum():
// long wrong = lines.stream()
//         .map(line -> (long) line.quantity() * line.unitPriceVnd())
//         .sum();
```

You can write `map(...).reduce(0L, Long::sum)`, but when the transformation produces a primitive number, `mapToLong(...).sum()` expresses the intent more concisely.

**Watch out for multiplication types:** if both operands are `int`, the multiplication is performed in `int` **before** converting to `long`, which can overflow. In this example `unitPriceVnd` is `long`; the cast `(long) line.quantity()` emphasizes the intent to compute in `long`.

## 4. Distinguishing Lazy and Terminal Operations

`filter` and `mapToLong` are **intermediate operations**. They configure the pipeline and usually **do not traverse the source immediately**. `sum()` is a **terminal operation**, which triggers pipeline execution to produce a result.

```java
import java.util.stream.LongStream;

LongStream pipeline = lines.stream()
        .filter(line -> line.paid())
        .mapToLong(line -> line.unitPriceVnd());

// At this point the pipeline is built; no terminal operation yet.
long sum = pipeline.sum(); // Starts traversal and closes the Stream.
```

Because a Stream is single-use, calling `pipeline.count()` after `sum()` is invalid. If you need another metric, create a new Stream from a re-traversable source like a `List`, or use an appropriate statistics collector.

Do not place required side effects inside `filter`, `map`, or `peek` assuming every element will always be visited: some terminal operations may short-circuit or optimize away intermediate steps. Writing predicates and mappers that **do not interfere with the source and do not depend on shared mutable state** makes code much easier to test.

## 5. Complete Java 17+ Program with Result Comparison

Save this as `LoopToStreamDemo.java`. This is a standalone runnable example containing sample data, a loop version, a Stream version, a list-building transformation, and checks that throw `AssertionError` on failure.

```java
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public class LoopToStreamDemo {
    record SaleLine(String sku, boolean paid, int quantity, long unitPriceVnd) {
        SaleLine {
            Objects.requireNonNull(sku, "sku");
            if (sku.isBlank()) {
                throw new IllegalArgumentException("SKU must not be blank");
            }
            if (quantity <= 0 || unitPriceVnd < 0) {
                throw new IllegalArgumentException("Invalid quantity/price");
            }
        }
    }

    static List<SaleLine> sample() {
        return List.of(
                new SaleLine("PEN", true, 3, 12_000L),
                new SaleLine("NOTE", false, 5, 50_000L),
                new SaleLine("RULER", true, 2, 8_000L),
                new SaleLine("ERASER", true, 4, 7_000L),
                new SaleLine("PEN", true, 1, 12_000L)
        );
    }

    // Version 1: filter, map, and sum using a for loop.
    static long totalWithLoop(List<SaleLine> lines) {
        long total = 0L;
        for (SaleLine line : lines) {
            if (line.paid() && line.quantity() >= 3) {
                long amount = (long) line.quantity() * line.unitPriceVnd();
                total += amount;
            }
        }
        return total;
    }

    // Version 2: same rules using a Stream.
    static long totalWithStream(List<SaleLine> lines) {
        return lines.stream()
                .filter(line -> line.paid() && line.quantity() >= 3)
                .mapToLong(line ->
                        (long) line.quantity() * line.unitPriceVnd())
                .sum();
    }

    // Example 3: same filter, but mapping to display labels.
    static List<String> labelsWithLoop(List<SaleLine> lines) {
        List<String> labels = new ArrayList<>();
        for (SaleLine line : lines) {
            if (line.paid() && line.quantity() >= 3) {
                labels.add(line.sku() + " x" + line.quantity());
            }
        }
        return labels;
    }

    static List<String> labelsWithStream(List<SaleLine> lines) {
        return lines.stream()
                .filter(line -> line.paid() && line.quantity() >= 3)
                .map(line -> line.sku() + " x" + line.quantity())
                .toList(); // Java 16+, returned list is unmodifiable.
    }

    static void check(boolean condition, String message) {
        if (!condition) {
            throw new AssertionError(message);
        }
    }

    static void selfTest() {
        List<SaleLine> data = sample();

        // Both solutions must produce the same exact result.
        check(totalWithLoop(data) == 64_000L, "Loop total is incorrect");
        check(totalWithStream(data) == 64_000L, "Stream total is incorrect");
        check(totalWithLoop(data) == totalWithStream(data),
                "Loop and pipeline differ");

        // Filtering then mapping to a list preserves the List's encounter order.
        List<String> expectedLabels = List.of("PEN x3", "ERASER x4");
        check(labelsWithLoop(data).equals(expectedLabels), "Loop labels are incorrect");
        check(labelsWithStream(data).equals(expectedLabels), "Stream labels are incorrect");

        // Empty source or no matching elements => total is 0.
        check(totalWithStream(List.of()) == 0L, "Empty source");
        check(totalWithStream(List.of(
                new SaleLine("A", false, 10, 100L),
                new SaleLine("B", true, 1, 100L)
        )) == 0L, "No matching lines");

        // Reversed source: total is unchanged, but label order can change.
        List<SaleLine> reversed = new ArrayList<>(data);
        Collections.reverse(reversed);
        check(totalWithStream(reversed) == 64_000L, "Total after reversing source");
        check(labelsWithStream(reversed).equals(
                List.of("ERASER x4", "PEN x3")), "Label order after reversal");

        // For values within long range, parallel sum must also match.
        long parallelTotal = data.parallelStream()
                .filter(line -> line.paid() && line.quantity() >= 3)
                .mapToLong(line ->
                        (long) line.quantity() * line.unitPriceVnd())
                .sum();
        check(parallelTotal == 64_000L, "Parallel total");

        // Stream.toList() result is unmodifiable.
        boolean rejected = false;
        try {
            labelsWithStream(data).add("OTHER x1");
        } catch (UnsupportedOperationException expected) {
            rejected = true;
        }
        check(rejected, "Stream.toList() list must be unmodifiable");
    }

    public static void main(String[] args) {
        List<SaleLine> data = sample();
        System.out.println("for: " + totalWithLoop(data));
        System.out.println("stream: " + totalWithStream(data));
        System.out.println("labels: " + labelsWithStream(data));

        // Run checks even without Java's -ea flag enabled.
        selfTest();
        System.out.println("TEST PASS");
    }
}
```

To run on JDK 17+:

```text
javac LoopToStreamDemo.java
java LoopToStreamDemo
```

Expected output:

```text
for: 64000
stream: 64000
labels: [PEN x3, ERASER x4]
TEST PASS
```

This lesson provides the code and assertions so you can run it yourself while studying; the program requires no external libraries. `check(...)` throws `AssertionError` if a condition fails, so you do not need to enable the `-ea` flag as with Java's `assert` statement.

## 6. Choosing `map`, `mapToInt`, `mapToLong`, or `reduce`?

The key question when converting a loop is: **after mapping, what value type and result type do we need?**

| Need | Suggested Pipeline | Result |
| --- | --- | --- |
| Filter objects into a list | `filter(...).toList()` | `List<T>` |
| Filter then build display strings | `filter(...).map(...).toList()` | `List<String>` |
| Filter then sum `int` quantities | `filter(...).mapToInt(...).sum()` | `int` |
| Filter then sum `long` values | `filter(...).mapToLong(...).sum()` | `long` |
| Filter then sum `BigDecimal` | `filter(...).map(...).reduce(BigDecimal.ZERO, BigDecimal::add)` | `BigDecimal` |
| Only count matching lines | `filter(...).count()` | `long` |

### Basic Example with `IntStream`

Problem: from numbers `1` through `6`, select the even numbers, square them, and compute the sum.

```java
import java.util.stream.IntStream;

int result = IntStream.rangeClosed(1, 6)
        .filter(n -> n % 2 == 0)
        .map(n -> n * n)
        .sum();

System.out.println(result); // 4 + 16 + 36 = 56
```

`IntStream.rangeClosed(1, 6)` is inclusive at both ends; after `filter` we have `2, 4, 6`; after `map` we have `4, 16, 36`; `sum` returns `56`.

Note that `IntStream.map` differs from `Stream<T>.map`: it maps **from `int` to `int`**, without creating a `Stream<Integer>`. With `Stream<SaleLine>`, you must call `mapToInt` or `mapToLong` to get a primitive stream for summing.

### Example with Decimal Money

When unit prices are decimal numbers requiring exact business precision, you can use `BigDecimal` instead of `double`:

```java
import java.math.BigDecimal;
import java.util.List;

List<BigDecimal> prices = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"),
        new BigDecimal("0.30")
);

BigDecimal total = prices.stream()
        .filter(price -> price.signum() > 0)
        .reduce(BigDecimal.ZERO, BigDecimal::add);

System.out.println(total); // 0.60
```

`BigDecimal` is an object type, so there is no specialized primitive stream for it; `reduce` uses `BigDecimal` addition. Avoid `new BigDecimal(0.1)` when you want the exact decimal value `0.1`.

## 7. Progressive Exercises: Convert Loops Yourself

In each exercise, **write the loop version first**, record the result on the sample data, and then convert to a Stream. Avoid guessing results solely from method names.

### Exercise 1 — Filter, Transform, Sum Integers

Given `List<Integer> numbers = List.of(3, -2, 4, 0, 5)`. Keep only **positive and even** numbers, multiply each by 10, and sum them.

Loop template:

```java
int total = 0;
for (int n : numbers) {
    if (n > 0 && n % 2 == 0) {
        total += n * 10;
    }
}
```

**Pipeline solution:**

```java
int total = numbers.stream()
        .filter(n -> n > 0 && n % 2 == 0)
        .mapToInt(n -> n * 10)
        .sum();

System.out.println(total); // 40
```

Only `4` satisfies the condition, so the result is `4 × 10 = 40`. Do not mistake `-2` for a **positive** even number.

### Exercise 2 — Keep a List Instead of a Sum

Given `List<String> names = List.of(" An ", " ", "Bình", " Chi ")`. Remove names that are only whitespace, trim leading/trailing whitespace, and convert to uppercase using `Locale.ROOT`. You must **preserve order**.

```java
import java.util.Locale;

List<String> cleaned = names.stream()
        .map(String::trim)
        .filter(name -> !name.isBlank())
        .map(name -> name.toUpperCase(Locale.ROOT))
        .toList();

System.out.println(cleaned); // [AN, BÌNH, CHI]
```

Here the terminal operation is `toList()`, not `sum()`, because the goal is **a list of strings**. `Stream.toList()` in Java 16+ returns an unmodifiable list; it does not promise a specific implementation class such as `ArrayList`.

### Exercise 3 — Convert an Inventory Sum Loop

The source contains products `Product(String code, boolean active, int stock)`. Sum the total stock of active products only. Choose an appropriate return type:

```java
record Product(String code, boolean active, int stock) {}

List<Product> products = List.of(
        new Product("A", true, 12),
        new Product("B", false, 100),
        new Product("C", true, 7)
);

long activeStock = products.stream()
        .filter(Product::active)
        .mapToLong(Product::stock)
        .sum();

System.out.println(activeStock); // 19
```

`mapToLong(Product::stock)` handles totals larger than `int`; when input values are small, `mapToInt(Product::stock)` also gives the right result. Still, both `long` and `int` have limits; if the total can exceed `long`, use a big-number solution or overflow detection.

### Exercise 4 — Two Calculations from the Same List

We need both the **total amount** and the **number of matching lines**. Can we reuse a single `Stream` after `sum()`?

```java
long revenue = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line ->
                (long) line.quantity() * line.unitPriceVnd())
        .sum();

long matchingLines = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .count();
```

**Answer:** You cannot reuse the same Stream object; two calls to `lines.stream()` create two fresh Streams from a re-traversable `List`. If the source can only be read once or traversal is expensive, you can build a collector that computes multiple metrics in a single pass. That is covered in the advanced collector lessons.

### Exercise 5 — Filter First or Map First?

We need the list of SKUs for lines where `paid && quantity >= 3`. Are these two approaches equivalent?

```java
// CORRECT: the full SaleLine is still available during filtering.
List<String> result = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .map(SaleLine::sku)
        .toList();

// WRONG: after map(SaleLine::sku), each element is only a String.
// You cannot call paid() or quantity() on a String.
// lines.stream().map(SaleLine::sku).filter(sku -> sku.paid()) ...
```

**Lesson:** the order of `filter` and `map` cannot be swapped arbitrarily if the mapping **discards data needed by the filter predicate**. If you want to filter by the SKU string, write a predicate for `String`.

## 8. Edge Cases to Check During Conversion

| Case | `for` Loop | Stream Pipeline | What to Verify |
| --- | --- | --- | --- |
| Empty source | Loop body never executes | `sum()` has no numbers to add | Both return 0 when initialized to 0. |
| No element matches | Every addition is skipped | `filter` produces an empty Stream | Total remains 0. |
| Duplicate SKUs | Processes each line | `filter`/`mapToLong` processes each line | Do not insert `distinct()` unless required by business rules. |
| Reversed source order | Sum is unchanged without overflow | Integer `sum` behaves the same | Label list in encounter order can change. |
| Very large `unitPriceVnd` | Can overflow `long` | `sum()` can also overflow `long` | Do not assume Stream prevents overflow. |
| `null` element in source | Calling getter on null throws | Lambda calling getter on null throws | Define a null-handling policy before transforming. |
| Parallel Stream | Not applied automatically | Lambdas can run on multiple threads | Avoid shared mutable state and keep reduction valid. |

### Intentional `null` Handling

If the source is allowed to contain `null` elements, decide whether to **discard them** or **fail fast**. For example, filtering nulls first:

```java
import java.util.Objects;

long total = lines.stream()
        .filter(Objects::nonNull)
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line ->
                (long) line.quantity() * line.unitPriceVnd())
        .sum();
```

If `null` represents invalid input data, silently skipping it can hide a bug; in that case, validate or use `Objects.requireNonNull` to report the error clearly. `List.of(...)` disallows null elements, but other source types may contain them.

## 9. Integer Overflow and Safe Summation Requirements

Converting a loop to `sum()` does not automatically change arithmetic rules. For example:

```java
int wrong = java.util.stream.IntStream
        .of(2_000_000_000, 2_000_000_000)
        .sum();
System.out.println(wrong); // -294967296, int overflow

long correct = java.util.stream.IntStream
        .of(2_000_000_000, 2_000_000_000)
        .asLongStream()
        .sum();
System.out.println(correct); // 4000000000
```

`LongStream.sum()` can also overflow if the result exceeds the `long` range. If the problem requires **detecting** overflow rather than wrapping silently, you can use `Math.addExact` in `reduce`, and `Math.multiplyExact` when computing line amounts:

```java
long totalExact = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line -> Math.multiplyExact(
                (long) line.quantity(), line.unitPriceVnd()))
        .reduce(0L, Math::addExact);
```

With the sample data, `totalExact == 64_000L`. When multiplication or addition exceeds `long` bounds, `Math.multiplyExact`/`Math.addExact` throws `ArithmeticException`. If inputs can exceed `long` itself, consider `BigInteger` or an appropriate monetary model rather than switching to `double` to avoid overflow.

### Mind Where the Cast Happens

```java
int quantity = 100_000;
int price = 100_000;

long wrong = quantity * price;        // Overflows int BEFORE assigning to long.
long right = (long) quantity * price; // Computed in long: 10000000000.
```

A similar bug can occur inside `mapToLong(line -> line.quantity() * line.price())` when both getters return `int`. Check the types of **the operands**, not just the target variable or `mapToLong`.

## 10. Result Ordering and Pipeline Performance

With a `List` source that has encounter order, `filter(...).map(...).toList()` preserves the relative order of remaining elements. However, **summing** does not return an ordered list; only the arithmetic sum within valid numeric bounds matters.

```java
List<String> labels = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .map(line -> line.sku() + " x" + line.quantity())
        .toList();
// [PEN x3, ERASER x4]
```

If you add `sorted()`, the list is ordered lexicographically by label, **no longer reflecting the original appearance order**. Sort only when required; `distinct()` should only be used when business rules allow dropping elements considered duplicates.

### Should You Use `parallelStream()` to Go Faster?

```java
long totalParallel = lines.parallelStream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line ->
                (long) line.quantity() * line.unitPriceVnd())
        .sum();
```

This is an associative reduction on `long` under Java semantics, so on the sample data the result is `64_000L`. However, parallelism introduces splitting, scheduling, and merging overhead; for small lists, it usually offers no benefit. Transformations should be independent, modifying neither the source list nor a shared sum variable. Do not replace `sum()` with `parallelStream().forEach(line -> sharedTotal += ...)` when `sharedTotal` is a shared variable: that is a race condition.

The standard traversal complexity of both the `for` loop and `filter → mapToLong → sum` on a finite list is **O(n)** time, aside from predicate and mapper costs. `sum` holds only a small accumulator state, whereas `filter(...).map(...).toList()` allocates a result list whose memory grows with the number of retained elements.

Do not judge speed by line count alone. **Choose the approach that is easiest to verify for correctness**, then benchmark on realistic data if this becomes a bottleneck.

## 11. Common Mistakes When Converting Loops to Streams

| Mistake | Why It Is Wrong | Fix |
| --- | --- | --- |
| Writing `map(...).sum()` on `Stream<Long>` | `Stream<T>` has no `sum()`. | Use `mapToLong(...).sum()` or an appropriate `reduce`. |
| `map` to SKU before filtering by `paid` | Loses the fields needed for filtering. | `filter` while elements are `SaleLine`, then `map` to SKU. |
| Using `distinct()` before `sum()` just because SKUs repeat | Drops valid sale lines. | Do not deduplicate when calculating line by line. |
| Multiplying two `int`s and assigning to `long` | Can overflow before the widening conversion. | Cast to `long` before multiplying or use `Math.multiplyExact`. |
| Calling `sum()` and trying to reuse the same Stream | Terminal operation consumes the Stream. | Call `lines.stream()` again or choose a single-pass collector. |
| Using `findFirst()` to get a total | Returns at most one element. | Use `sum()`/`reduce` to combine all elements. |
| Using `peek` to increment a sum variable | Hard-to-control side effect; risk of optimization or race. | Express accumulation with a terminal operation. |
| Assuming Streams are always faster than `for` loops | Pipelines have setup/execution overhead; parallel adds split/merge cost. | Measure on representative data when performance matters. |
| Ignoring empty sources | Wrong assumptions about default values. | `sum()` returns 0; `average()`/`min()` return `Optional`. |
| Mutating the source collection inside `filter` | Violates non-interference; can cause broken behavior. | Traverse a stable source and transform outputs instead of mutating input. |

## 12. End-of-Lesson Review Exercises

**Question 1.** From `IntStream.rangeClosed(1, 10)`, take numbers divisible by 3, double them, and compute the sum. What is the result?

```java
int total = java.util.stream.IntStream.rangeClosed(1, 10)
        .filter(n -> n % 3 == 0)
        .map(n -> n * 2)
        .sum();
// (3 + 6 + 9) * 2 = 36
```

**Question 2.** If all `SaleLine` elements have `paid == false`, what does the pipeline in Section 3 return?

**Answer:** `0L`. After `filter` no elements remain, so `LongStream.sum()` returns the additive identity.

**Question 3.** Why does `lines.stream().map(SaleLine::sku).filter(line -> line.paid())` fail to compile?

**Answer:** After `map(SaleLine::sku)`, the elements are `String`; `String` has no `paid()` method. To filter by status, do it before the `map` step.

**Question 4.** Once an accurate loop and a pipeline produce the same result on sample data, is that enough to prove they are always equivalent?

**Answer:** No. You also need empty inputs, no-match inputs, large numbers, duplicate keys, and checks verifying the Stream version did not inadvertently alter filtering rules, numeric types, or list ordering.

**Question 5.** When you need the average of matching lines instead of the sum, what do you replace `sum()` with and why must you inspect the result?

```java
var maybeAverage = lines.stream()
        .filter(line -> line.paid() && line.quantity() >= 3)
        .mapToLong(line ->
                (long) line.quantity() * line.unitPriceVnd())
        .average();
```

**Answer:** `average()` returns `OptionalDouble`, because no average exists when no element qualifies. Do not call `getAsDouble()` on an empty Optional without checking; only use `orElse(0.0)` if business rules define 0 as an appropriate default.

**Question 6.** Can you keep one Stream and compute both the sum and the line count using two terminal operations on the same variable?

**Answer:** No. A Stream instance can only be used for one terminal operation. If the source is a `List`, create two new Streams; if the source cannot be re-traversed, use an approach that accumulates multiple metrics in one pass.

## Key Takeaways

- Convert `for` to Stream by **separating the operations cleanly**: the `if` condition becomes `filter`, per-line computation becomes `map`/`mapToLong`, and accumulation becomes `sum` or `reduce`.
- `filter` and `map` are usually lazy; `sum` is a terminal operation and consumes the Stream. Use `mapToInt`/`mapToLong` when summing primitive numbers.
- Order steps carefully: filter before discarding fields needed for checks; do not add `distinct()` or `sorted()` unless business rules require them.
- Empty inputs, numeric types, overflow risk, null source elements, and non-interference must be considered **in both the loop and Stream versions**.
- Verify equivalence between the two solutions with repeatable tests; prioritize **correctness and clarity** before optimizing or switching to parallel.
