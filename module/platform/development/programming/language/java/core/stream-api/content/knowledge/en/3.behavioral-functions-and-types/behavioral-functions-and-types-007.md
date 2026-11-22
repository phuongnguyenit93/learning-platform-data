# Using Comparator to Sort and Select Extreme Elements

In the Java Stream API, `Comparator<T>` is the way to express **a rule for comparing two objects of the same type**. From a single rule, you can sort a list with `sorted(comparator)`, find the minimum/maximum element with `min(comparator)` and `max(comparator)`, or find extremes per group with `Collectors.minBy`/`maxBy`. The key is to determine the **comparison key, ascending/descending direction, tie-breaking rule**, and processing cost before writing the pipeline.

This lesson belongs to the **Behavioral Functions and Types** chapter, **JAVA_STREAM_API** module. It is part of declarative data processing using lazy pipelines, `filter`, `map`, `reduce`, and `collect`; understanding `Comparator` is also useful when moving on to grouping, custom collectors, parallel processing, or problems with performance and state constraints.

## 1. What Is a Comparator?

`Comparator<T>` lives in `java.util` and is a *functional interface* with the method:

```java
int compare(T left, T right);
```

The return value carries meaning in its **sign**, not its absolute magnitude:

| Result | Meaning when sorting ascending by Comparator |
|---|---|
| Negative number | `left` comes before `right` |
| `0` | The two elements are equal **according to the comparison criteria** |
| Positive number | `left` comes after `right` |

Example creating a Comparator from a lambda:

```java
Comparator<String> byLength = (a, b) ->
        Integer.compare(a.length(), b.length());
```

`Integer.compare` explicitly expresses integer comparison and avoids integer overflow that writing `a.length() - b.length()` can cause. A more idiomatic approach is declaring a *sort key* via factory methods:

```java
Comparator<String> byLength = Comparator.comparingInt(String::length);
```

Both examples use `Comparator<String>`; the expression `String::length` is a method reference serving as the key-extraction function from a string.

### Comparator vs. Comparable

| `Comparable<T>` | `Comparator<T>` |
|---|---|
| Defines an object's **natural ordering** via `compareTo` | Defines an **external comparison rule** via `compare` |
| The object's class implements the interface itself | Can use lambdas, method references, and `Comparator` helper methods |
| Suitable when a type has one clear natural order, e.g., `Integer`, `String` | Suitable when a type needs multiple sort orders: price, name, rating... |
| `stream.sorted()` requires elements with a suitable natural ordering | `stream.sorted(comparator)` uses the supplied rule |

A `Product` class does not need to implement `Comparable` in order to be sorted by price, code, or rating using different Comparators.

## 2. Practical Example: Products in a Store

Suppose we have a list of products with code, name, category, price in VND, and rating score. The example below runs on **Java 8 and later** and can be pasted into a `ComparatorStreamDemo.java` file to run directly.

```java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Optional;
import java.util.stream.Collectors;

public class ComparatorStreamDemo {
    static final class Product {
        private final String code;
        private final String name;
        private final String category;
        private final int price;
        private final double rating;

        Product(String code, String name, String category,
                int price, double rating) {
            this.code = code;
            this.name = name;
            this.category = category;
            this.price = price;
            this.rating = rating;
        }

        String getCode()     { return code; }
        String getName()     { return name; }
        String getCategory() { return category; }
        int getPrice()       { return price; }
        double getRating()   { return rating; }

        @Override
        public String toString() {
            return code;
        }
    }

    public static void main(String[] args) {
        List<Product> products = Arrays.asList(
                new Product("P01", "Pen", "Office", 15_000, 4.5),
                new Product("P02", "Notebook", "Office", 32_000, 4.8),
                new Product("P03", "Binder", "Office", 15_000, 4.4),
                new Product("P04", "Bag", "Accessories", 90_000, 4.8),
                new Product("P05", "Briefcase", "Accessories", 32_000, 4.7)
        );

        // Price ascending; if tied on price, code ascending.
        Comparator<Product> priceAscThenCode =
                Comparator.comparingInt(Product::getPrice)
                        .thenComparing(Product::getCode);

        List<Product> priceSorted = products.stream()
                .sorted(priceAscThenCode)
                .collect(Collectors.toList());
        System.out.println("Price ascending: " + priceSorted);
        // Price ascending: [P01, P03, P02, P05, P04]

        Optional<Product> cheapest = products.stream()
                .min(priceAscThenCode);
        Optional<Product> mostExpensive = products.stream()
                .max(priceAscThenCode);

        System.out.println("Cheapest: " +
                cheapest.map(Product::getCode).orElse("(none)"));
        System.out.println("Most expensive: " +
                mostExpensive.map(Product::getCode).orElse("(none)"));
        // Cheapest: P01
        // Most expensive: P04

        // Rating descending, price ascending, code ascending.
        Comparator<Product> bestRatedFirst =
                Comparator.comparingDouble(Product::getRating)
                        .reversed()
                        .thenComparingInt(Product::getPrice)
                        .thenComparing(Product::getCode);

        List<Product> ranked = products.stream()
                .sorted(bestRatedFirst)
                .collect(Collectors.toList());
        System.out.println("Ranked: " + ranked);
        // Ranked: [P02, P04, P05, P01, P03]

        Map<String, Optional<Product>> cheapestPerCategory =
                products.stream().collect(
                        Collectors.groupingBy(
                                Product::getCategory,
                                Collectors.minBy(priceAscThenCode)));

        cheapestPerCategory.forEach((category, product) ->
                System.out.println(category + ": " +
                        product.map(Product::getCode).orElse("(none)")));
        // Office: P01; Accessories: P05
        // Group printing order is not guaranteed.
    }
}
```

Key points to read from this example:

- `sorted`, `min`, and `max` all reuse **the same price-ascending, code-ascending rule**; you do not need to write three separate algorithms.
- P01 and P03 both cost 15,000, yet `thenComparing(Product::getCode)` places P01 before P03. This makes order and extreme elements deterministic when primary keys tie.
- P02 and P04 share a rating of 4.8. In the ranking Comparator, price is an ascending secondary key, so P02 comes before P04.
- `groupingBy(..., minBy(...))` finds the product with the smallest key **within each group**. The result value type of `minBy` is `Optional<Product>`.

## 3. Sorting with Stream.sorted

`sorted()` is a **stateful intermediate operation**. It describes the output order and only executes when the pipeline has an appropriate terminal operation. For ordinary finite data, sorting must collect/inspect elements to determine order.

Two common forms:

```java
List<Integer> numbers = Arrays.asList(9, 2, 7, 2);

List<Integer> ascending = numbers.stream()
        .sorted() // Natural order: [2, 2, 7, 9]
        .collect(Collectors.toList());

List<Integer> descending = numbers.stream()
        .sorted(Comparator.reverseOrder()) // [9, 7, 2, 2]
        .collect(Collectors.toList());
```

For objects that do not implement `Comparable` or need ordering by criteria other than natural order, pass a Comparator to `sorted(comparator)`.

### 3.1. Choosing Keys with comparing and thenComparing

| Comparator creation | Meaning |
|---|---|
| `Comparator.comparing(Product::getName)` | By name, using `String`'s natural order |
| `Comparator.comparingInt(Product::getPrice)` | By `int` price, avoiding key boxing |
| `Comparator.comparingLong(...)` | By `long` key |
| `Comparator.comparingDouble(Product::getRating)` | By `double` rating |
| `comparator.thenComparing(Product::getCode)` | If previous key ties, compare further by code |
| `comparator.reversed()` | Reverses the direction of the **entire** Comparator built so far |

When using `Comparator.comparing(keyExtractor)`, `keyExtractor` is typically a `Function<T, U>`; while `comparingInt`, `comparingLong`, and `comparingDouble` accept primitive key extractors such as `ToIntFunction<T>`. This connects `Comparator` with Java's family of **behavioral function types**.

### 3.2. Where You Call reversed Matters Greatly

Suppose two products have the same price and we want **price descending, yet code still ascending**:

```java
Comparator<Product> priceDescCodeAsc =
        Comparator.comparingInt(Product::getPrice)
                .reversed()
                .thenComparing(Product::getCode);
// Price descending; products with the same price are ordered by code ascending.
```

If written in a different order:

```java
Comparator<Product> priceDescCodeDesc =
        Comparator.comparingInt(Product::getPrice)
                .thenComparing(Product::getCode)
                .reversed();
// Reverses both the price rule and the code rule: both keys are descending.
```

`reversed()` applies to **the Comparator constructed up to the point where it is called**. The difference often only shows up when multiple records share the same primary key; therefore, sorting test data should include tied cases.

### 3.3. Stable Ordering and Ties According to the Comparator

For Streams with an *encounter order* (such as a Stream from a `List`), `sorted` is **stable**: elements with `compare(a, b) == 0` preserve their original encounter order. For Streams without an encounter order, no such stability guarantee exists.

Still, this only applies to `sorted`. Do not rely on "whichever element appeared first in the list" when calling `min`/`max` with multiple objects sharing the extreme key. If business logic requires selecting one exact record, construct a deterministic secondary key such as a unique code:

```java
Comparator<Product> byPriceThenCode =
        Comparator.comparingInt(Product::getPrice)
                .thenComparing(Product::getCode);
```

This is also the easiest way to ensure results do not depend on differences in traversal order inside a parallel pipeline.

## 4. Finding Extremes with min and max

`Stream.min(comparator)` and `Stream.max(comparator)` are **terminal operations**. They select the smallest/largest element **according to the supplied Comparator**, respectively, and return `Optional<T>` because the source might be empty.

```java
Optional<Integer> smallest = Arrays.asList(8, 3, 11)
        .stream()
        .min(Integer::compare); // Optional[3]

Optional<Integer> largest = Arrays.asList(8, 3, 11)
        .stream()
        .max(Integer::compare); // Optional[11]

Optional<Integer> absent = Collections.<Integer>emptyList()
        .stream()
        .min(Integer::compare); // Optional.empty
```

This snippet requires `import java.util.Collections;` along with the corresponding imports. Do not call `get()` on an `Optional` without checking for presence; prefer `ifPresent`, `orElse`, `orElseGet`, or `orElseThrow` when missing data is a business error.

### 4.1. max and min Always Follow the Comparator's Direction

This is a very common mistake:

```java
Comparator<Product> priceDescending =
        Comparator.comparingInt(Product::getPrice).reversed();

Optional<Product> firstInDescendingOrder =
        products.stream().min(priceDescending);
// Picks the highest price in business terms.

Optional<Product> lastInDescendingOrder =
        products.stream().max(priceDescending);
// Picks the lowest price in business terms.
```

Because the Comparator is reversed, the **minimum element according to the Comparator** is actually the product with the highest price. A more readable approach when you only want the highest price is to keep the Comparator ascending and call `max(Comparator.comparingInt(Product::getPrice))`.

If you want the "top-ranked product" in the `bestRatedFirst` example, use `min(bestRatedFirst)` or `sorted(bestRatedFirst).findFirst()`. The first approach avoids sorting the entire stream when only one element is needed.

### 4.2. min/max or sorted(...).findFirst()?

```java
// Only need the single cheapest element:
Optional<Product> cheapest = products.stream()
        .min(Comparator.comparingInt(Product::getPrice));

// Need the entire list ordered by price:
List<Product> sortedByPrice = products.stream()
        .sorted(Comparator.comparingInt(Product::getPrice))
        .collect(Collectors.toList());
```

For `n` elements and a constant-cost comparison:

| Need | Approach | Typical cost |
|---|---|---|
| Get one extreme element | `min` or `max` | `O(n)` comparisons; no need to retain a sorted list |
| Sort everything for display | `sorted` then `collect` | Typically `O(n log n)` time, plus memory for sorting |
| Get top `k` elements in order | `sorted(comparator).limit(k)` | Concise and correct for finite sources, but not automatically `O(n log k)` cost |

For huge datasets where only the top `k` elements are needed, a bounded heap structure can be more efficient than sorting everything. Do not assume that placing `limit(k)` after `sorted` makes the Stream automatically optimize into a top-k algorithm.

Traversal operations like `min`, `max`, and `sorted` must consume the source to know the result; an infinite source can cause computation never to terminate. Adding `limit` **before** `sorted` caps the input count, yet also changes the semantics: it then selects only among the first elements taken.

## 5. Per-Group Extremes with Collectors.minBy/maxBy

When the problem is "cheapest **in each category**" or "highest rated **by supplier**", a single `min`/`max` is insufficient because it returns one result for the whole Stream. Use a downstream collector:

```java
Comparator<Product> byPriceThenCode =
        Comparator.comparingInt(Product::getPrice)
                .thenComparing(Product::getCode);

Map<String, Optional<Product>> cheapestByCategory =
        products.stream()
                .collect(Collectors.groupingBy(
                        Product::getCategory,
                        Collectors.minBy(byPriceThenCode)));
```

`groupingBy` creates groups by `category`, while `minBy` picks the extreme **within each group**. The value type is `Optional<Product>` per the collector's contract, even though a group formed from input elements is normally non-empty.

Finding the highest-rated product per group:

```java
Comparator<Product> byRatingThenCode =
        Comparator.comparingDouble(Product::getRating)
                .thenComparing(Product::getCode);

Map<String, Optional<Product>> highestRatedByCategory =
        products.stream()
                .collect(Collectors.groupingBy(
                        Product::getCategory,
                        Collectors.maxBy(byRatingThenCode)));
```

With the `byRatingThenCode` rule, on equal ratings the **larger** code is chosen by `max`. If the business rule wants the **smaller** code on tied ratings, adjust the secondary key rather than expecting `max` to "pick the first record automatically".

Collectors like `minBy`/`maxBy` also fit the declarative processing model; there is no need to group manually and write loops over each group.

## 6. Handling Nulls and Special Data

Because `Comparator.comparing(Product::getName)` needs a comparison key, a `null` value can throw `NullPointerException`. `Comparator.nullsFirst` and `Comparator.nullsLast` explicitly state the desired order.

**The name key may be null, while the Product itself is non-null:**

```java
Comparator<Product> byNullableName =
        Comparator.comparing(
                Product::getName,
                Comparator.nullsLast(String.CASE_INSENSITIVE_ORDER));
```

**Product elements in the Stream may be null:**

```java
Comparator<Product> byPriceWithNullProducts =
        Comparator.nullsLast(
                Comparator.comparingInt(Product::getPrice));
```

These two cases differ: the first handles **the key returned by the getter**; the second handles **the object being compared**. If both the object and the key can be null, you can combine both Comparator layers accordingly.

For currency stored as `BigDecimal`, you can use `Comparator.comparing(Product::getAmount)` when `getAmount()` returns a non-null `BigDecimal`; `BigDecimal.compareTo` compares numeric values in natural order. Note that two `BigDecimal` values can compare as `0` even if `equals` differs due to different *scales*.

For `double` keys, `comparingDouble` uses `Double.compare` rules, where `NaN` and `-0.0` have specific ordering rules. If ratings are not allowed to hold these values, validate/normalize data per business rules before sorting.

## 7. Comparator Contract and Subtle Bugs

A correct Comparator must uphold consistency rules, including:

1. **Antisymmetry of sign:** the sign of `compare(a, b)` must be the opposite of `compare(b, a)`.
2. **Transitivity:** if `a > b` and `b > c` under the Comparator, then `a > c`.
3. **Consistency with equivalence (`0`):** if `compare(a, b) == 0`, both objects must have the same ordering relation with any third object.

`compare(a, b) == 0` **does not have to** imply `a.equals(b)`, yet you should understand the consequences. For example, `TreeSet` relies on its Comparator to decide whether two elements are order-duplicates, so two distinct objects comparing as `0` may be treated as the same element in a `TreeSet`. In `Stream.sorted`, they remain two elements in the Stream if the source contains both.

Common mistakes:

```java
// AVOID: subtraction can overflow int.
Comparator<Product> unsafe = (a, b) -> a.getPrice() - b.getPrice();

// PREFER: integer comparison with a clear contract.
Comparator<Product> safe =
        Comparator.comparingInt(Product::getPrice);
```

- Do not use a Comparator that returns random results, depends on the clock, or reads data that can be mutated during sorting.
- Avoid adding side effects such as writing to a shared list inside a Comparator. A comparison may be called multiple times, with no guaranteed call order, and may run across different workers in a parallel Stream.
- Do not expect valid results from non-transitive rules or ordering that changes mid-sort; sorting algorithms can produce nonsensical results or throw `IllegalArgumentException` in certain contract violations.
- Do not call zero-argument `sorted()` on types lacking an appropriate natural ordering; the error may only surface when the terminal operation executes.

## 8. Comparator in Parallel Pipelines

`products.parallelStream().sorted(comparator)` still sorts according to the Comparator rule; for sources with an encounter order, `sorted` continues to guarantee stability. Yet parallel execution is **not automatically faster**:

- Sorting and merging partial results incurs coordination, memory, and synchronization overhead.
- The Comparator must be safe when called from multiple workers. Use pure functions extracting keys from objects that do not change during processing.
- If distinct elements have equal comparison keys, `min`/`max` must not be relied upon to implicitly pick the "first-arriving" element. Add a unique secondary key when deterministic results are needed.
- `sorted(comparator).forEach(...)` on a parallel Stream **does not guarantee action order** because `forEach` does not preserve encounter order. Use `forEachOrdered(...)` if ordering is truly needed, even though it may reduce parallel gains.

For small datasets and cheap key extractors, start with a sequential Stream. Only consider parallelism when data volume is large enough, after checking input data, Comparator correctness, and measuring actual performance.

## 9. Practice Exercises

Given a `Product` list as in the main example:

1. **Sort by price descending, then code ascending on ties.** Hint: `Comparator.comparingInt(Product::getPrice).reversed().thenComparing(Product::getCode)`. Expected codes: `[P04, P02, P05, P01, P03]`.
2. **Pick the cheapest product with rating 4.6 or higher.** Use `filter(p -> p.getRating() >= 4.6)` then `min(byPriceThenCode)`. Result: P02 (P05 has the same price but a larger code).
3. **Take the top two products by rating descending and price ascending.** Use `sorted(bestRatedFirst).limit(2)`. Result: `[P02, P04]`.
4. **Find the most expensive product in each category.** Use `groupingBy(Product::getCategory, maxBy(byPriceThenCode))`. With sample data: Office → P02, Accessories → P04.
5. **What happens if the list is empty?** `min`/`max` return `Optional.empty()`; while `sorted(...).collect(toList())` returns an empty list.

## 10. Takeaways When Designing Pipelines

When you need display ordering, describe the order with `Comparator.comparing...`, chain keys with `thenComparing`, and use `sorted(comparator)`. When you only need **one** smallest/largest element, use `min` or `max` to avoid unnecessary sorting. When you need extremes **per group**, combine `groupingBy` with `Collectors.minBy`/`maxBy`. In all cases, clarify Comparator direction, tie-breaking, null data, comparison contracts, statefulness, and pipeline cost.
