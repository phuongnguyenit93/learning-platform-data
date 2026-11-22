# `reducing()`, `minBy()`, and `maxBy()` Downstream of Another Collector

## 1. Goal: Grouping and Then Reducing **Within Each Group**

In the Java Stream API, an operation often has two levels:

1. **The outer collector** determines how data is partitioned, such as `groupingBy` by product category or `partitioningBy` by a price condition.
2. **The inner collector (downstream collector)** determines the result of each group: total amount, minimum element, maximum element, or a reduced value.

The collectors `Collectors.reducing(...)`, `Collectors.minBy(...)`, and `Collectors.maxBy(...)` are especially useful in the **downstream position** because they do not force creating an intermediate `List` and iterating over it again.

Conceptual example:

```java
Map<String, Integer> revenueByCategory = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.reducing(
                        0,
                        p -> p.price() * p.quantity(),
                        Integer::sum)));
```

`Product::category` selects the group for each `Product`. Within each group, `reducing` transforms each product into that line's revenue (`price × quantity`), then sums the values starting from `0`. The result of the entire `collect` is `Map<String, Integer>` — **each key has only a single total**, not `Map<String,List<Product>>`.

Similarly:

```java
Map<String, Optional<Product>> mostExpensive =
        products.stream().collect(Collectors.groupingBy(
                Product::category,
                Collectors.maxBy(Comparator.comparingInt(Product::price))));
```

The value of each group is an `Optional<Product>` containing the product with the highest price according to the comparator. Even though `groupingBy` only creates groups from keys that actually appear, the downstream type of `maxBy` is still `Optional<Product>` because it must also have a valid result in the case of **no elements** when combined with another outer collector.

Lesson objectives: understand the signatures and results of the three collectors, use them after `groupingBy`/`partitioningBy`/`mapping` or `collectingAndThen`, properly check empty values and comparisons, and avoid pitfalls regarding types, ordering, and performance.

## 2. Distinguishing `Stream.reduce()` and `Collectors.reducing()`

`Stream.reduce(...)` is a **terminal operation** directly on a Stream. It produces **one** value for that Stream:

```java
int sum = java.util.stream.Stream.of(2, 3, 5)
        .reduce(0, Integer::sum); // 10
```

`Collectors.reducing(...)` is a **Collector factory**. It does not execute on data yet; this collector is passed into `collect`, or used as a downstream collector for another collector:

```java
int sum = java.util.stream.Stream.of(2, 3, 5)
        .collect(java.util.stream.Collectors.reducing(0, Integer::sum));
// 10
```

Both examples return the same result; for a simple sum, using `reduce` or `IntStream.sum()` is usually shorter and easier to understand.

The special value of `Collectors.reducing` appears when **composing**:

```text
products.stream()
    │
    ▼
groupingBy(Product::category, downstream)
    ├── Books   → reducing(...) → Books total
    ├── Food    → reducing(...) → Food total
    ├── Office  → reducing(...) → Office total
    └── Tech    → reducing(...) → Tech total
                  │
                  ▼
             Map<Category, Result>
```

If you call `products.stream().reduce(...)` directly, you only reduce the entire Stream into a single value and do not automatically produce a separate result Map for each category. For specialized downstream collectors such as `summingInt`, `counting`, or `averagingInt`, you can choose a more expressive API instead of always using `reducing`.

## 3. The Three Overloads of `Collectors.reducing`

There are three common forms, and they **differ in both input and result type**.

### 3.1. `reducing(BinaryOperator<T>)` — without identity

Signature:

```java
static <T> Collector<T, ?, Optional<T>> reducing(
        java.util.function.BinaryOperator<T> op);
```

This collector combines elements of the same type `T` using the operation `op`, but because there is no initial value when a group is empty, the result is `Optional<T>`.

```java
java.util.Optional<Integer> max = java.util.stream.Stream
        .of(2, 7, 4)
        .collect(java.util.stream.Collectors.reducing(Integer::max));

// Optional[7]
```

If the source is empty, the result is `Optional.empty()`. When inside `groupingBy`, the result of **each group** has type `Optional<T>`:

```java
Map<String, Optional<Product>> latestByCategory =
        products.stream().collect(Collectors.groupingBy(
                Product::category,
                Collectors.reducing((a, b) ->
                        a.price() >= b.price() ? a : b)));
```

This snippet is for illustration, assuming `Product`, `products`, `Map`, `Optional`, and `Collectors` are already declared. When you want to select an extremum, you should use `maxBy(comparator)`/`minBy(comparator)` so the comparison rule is more explicit. A function that picks the left element when prices are equal as above also needs its tie policy and encounter order considered before being used in parallel processing.

### 3.2. `reducing(T identity, BinaryOperator<T>)` — same type, with identity value

Signature:

```java
static <T> Collector<T, ?, T> reducing(
        T identity,
        java.util.function.BinaryOperator<T> op);
```

`identity` is the identity value of `op`, for example `0` for addition or `1` for multiplication. For an empty Stream, the collector returns `identity`, not `Optional.empty()`.

```java
int product = java.util.stream.Stream.of(2, 3, 4)
        .collect(java.util.stream.Collectors.reducing(
                1, (a, b) -> a * b));

// 24
```

If the downstream receives `Product` directly from `groupingBy`, you **cannot** call `reducing(0, Integer::sum)` and expect Java to automatically extract `Product.price()`. This two-parameter form uses `T = Product` when values have not been transformed yet. To reduce a numeric property, use the three-parameter overload with a `mapper` or combine with `mapping`:

```java
// mapping transforms Product to Integer before the reducing downstream:
Map<String, Integer> sums = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.mapping(
                        Product::price,
                        Collectors.reducing(0, Integer::sum))));
```

This is an illustrative snippet inside a class with appropriate imports. `mapping` emits values of type `Integer` so `reducing(0, Integer::sum)` uses the matching type.

### 3.3. `reducing(U identity, Function<T,U> mapper, BinaryOperator<U> op)`

Signature:

```java
static <T, U> Collector<T, ?, U> reducing(
        U identity,
        java.util.function.Function<? super T, ? extends U> mapper,
        java.util.function.BinaryOperator<U> op);
```

This is usually the **most convenient form when used downstream of `groupingBy`**. It consists of three steps:

1. Use `mapper` to transform a `T` element into a `U` value.
2. Accumulate the `U` values using `op`.
3. Use `identity` when the group has no elements and when initializing the reduction.

```java
Map<String, Integer> totalPrice = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.reducing(
                        0, Product::price, Integer::sum)));
```

Here the source `Product` differs from the result type `Integer`. Note that these are the **three parameters of `Collectors.reducing`** (`identity`, `mapper`, `op`), **different** from the three parameters of `Stream.reduce` (`identity`, `accumulator`, `combiner`). They do not have the same signature and their names/behaviors should not be interchanged.

| Form | Accepts elements | Result | When to use |
| --- | --- | --- | --- |
| `reducing(op)` | `T` | `Optional<T>` | Combining without identity, including custom min/max |
| `reducing(identity, op)` | `T` | `T` | Combining elements of the same type |
| `reducing(identity, mapper, op)` | `T`, mapped to `U` | `U` | Aggregating a property of a different type from the source |
| `Stream.reduce(identity, accumulator, combiner)` | `T`, state `U` | `U` | Direct terminal reduction over the entire Stream |

## 4. `Collectors.minBy` and `Collectors.maxBy` as Comparator Downstreams

Signatures:

```java
static <T> Collector<T, ?, Optional<T>> minBy(
        java.util.Comparator<? super T> comparator);

static <T> Collector<T, ?, Optional<T>> maxBy(
        java.util.Comparator<? super T> comparator);
```

A comparator compares two `T` elements. `minBy` selects the smallest element; `maxBy` selects the largest element according to the ordering defined by the comparator.

With products:

```java
Comparator<Product> byPrice =
        Comparator.comparingInt(Product::price);

Map<String, Optional<Product>> cheapest =
        products.stream().collect(Collectors.groupingBy(
                Product::category,
                Collectors.minBy(byPrice)));

Map<String, Optional<Product>> priciest =
        products.stream().collect(Collectors.groupingBy(
                Product::category,
                Collectors.maxBy(byPrice)));
```

- The `Map` key is the category.
- The value is `Optional<Product>`, **not `Product` itself**.
- `minBy`/`maxBy` select the extremum **within each category**, not the global extremum of the entire Stream.
- The comparator can be based on price, date, priority, name length, or a composite property.
- Cases where multiple elements are **equal according to the comparator** require an intentional tie policy if it matters exactly which element is selected.

Use `Comparator.comparingInt(Product::price)` instead of `(a, b) -> a.price() - b.price()`. Subtraction in a comparator can overflow integers when values are very large or negative, producing an incorrect ordering.

### Tie-breakers create a deterministic selection policy

Suppose two products have the same price, and you want to break ties by name. You can use:

```java
Comparator<Product> byPriceThenName =
        Comparator.comparingInt(Product::price)
                  .thenComparing(Product::name);
```

`minBy` will select the product with the **lower price**, then the **lexicographically smaller** name on a tie. `maxBy` will select the product with the **higher price**, then the **lexicographically larger** name on a tie.

If you want the highest price but the *smallest* name on a tie, you need a different comparator with the tie-breaker reversed appropriately; do not assume `maxBy` always picks the first name.

## 5. How Does a Downstream Inside `groupingBy` Work?

Consider the syntax:

```java
Collectors.groupingBy(
        Product::category,
        Collectors.maxBy(byPriceThenName))
```

`groupingBy` operates at the outer layer: creating category keys and distributing each Product into the appropriate group. The inner collector only receives the Products **of the group currently being processed**.

The result has the structure:

```text
Books → Optional[most expensive Product in Books]
Food  → Optional[most expensive Product in Food]
Tech  → Optional[most expensive Product in Tech]
```

`maxBy` does not compute one globally most expensive product and attach it to every key. Each group has its own reduction state.

If you write:

```java
products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.toList()));
```

the result is `Map<String,List<Product>>`: keeping all Products in lists. With `maxBy`, `minBy`, or `reducing` inside, the value only needs to be a single aggregated result and does not need to keep all group elements in the result list.

`groupingBy` is a terminal aggregation when placed in `stream.collect(...)`, not an intermediate step that you can continue calling `map` on over the same old Stream. If you want to transform the Map after collecting, you can iterate over `entrySet()` with a new Stream or place a `collectingAndThen` downstream as in section 8.

## 6. Complete Java 17 Example and Test Results

The practice problem uses `Product` with `name`, `category`, `price`, `quantity`. We compute:

- Total list price of products in each category using `reducing(0, Product::price, Integer::sum)`.
- Total revenue (`price × quantity`) by category using `reducing(0, mapper, Integer::sum)`.
- Cheapest and most expensive product in each category using `minBy`/`maxBy`.
- Most expensive product by category using `reducing(BinaryOperator.maxBy(...))` to compare syntax.
- Names of the cheapest/most expensive products using `collectingAndThen` to convert `Optional<Product>` to `String`.
- Most expensive product in two high/low price partitions using `partitioningBy`.
- Empty Stream results: `groupingBy` returns an empty Map, while `partitioningBy` still has both Boolean keys and corresponding `Optional.empty()` values.

Standalone Java 17 file named **`DownstreamReducingDemo.java`**:

```java
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;
import java.util.TreeMap;
import java.util.function.BinaryOperator;
import java.util.stream.Collectors;
import java.util.stream.Stream;

public class DownstreamReducingDemo {
    record Product(String name, String category,
                   int price, int quantity) {}

    static final Comparator<Product> BY_PRICE_THEN_NAME =
            Comparator.comparingInt(Product::price)
                    .thenComparing(Product::name);

    static List<Product> sample() {
        return List.of(
                new Product("Java", "Books", 120, 2),
                new Product("Clean Code", "Books", 150, 1),
                new Product("Tea", "Food", 40, 3),
                new Product("Coffee", "Food", 70, 2),
                new Product("Mouse", "Tech", 90, 1),
                new Product("Keyboard", "Tech", 200, 1),
                new Product("Pen", "Office", 15, 4));
    }

    static Map<String, Integer> sumPrices(Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.reducing(
                        0, Product::price, Integer::sum)));
    }

    static Map<String, Integer> revenues(Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.reducing(
                        0,
                        p -> p.price() * p.quantity(),
                        Integer::sum)));
    }

    static Map<String, Optional<Product>> cheapest(
            Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.minBy(BY_PRICE_THEN_NAME)));
    }

    static Map<String, Optional<Product>> priciest(
            Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.maxBy(BY_PRICE_THEN_NAME)));
    }

    static Map<String, Optional<Product>> priciestWithReducing(
            Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.reducing(
                        BinaryOperator.maxBy(BY_PRICE_THEN_NAME))));
    }

    static Map<String, String> minimumNames(Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.minBy(BY_PRICE_THEN_NAME),
                        opt -> opt.map(Product::name).orElse("NONE"))));
    }

    static Map<String, String> maximumNames(Stream<Product> input) {
        return input.collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.maxBy(BY_PRICE_THEN_NAME),
                        opt -> opt.map(Product::name).orElse("NONE"))));
    }

    static Map<Boolean, Optional<Product>> pricePartitions(
            Stream<Product> input) {
        return input.collect(Collectors.partitioningBy(
                p -> p.price() >= 100,
                Collectors.maxBy(BY_PRICE_THEN_NAME)));
    }

    static void expect(Object wanted, Object actual, String name) {
        if (!Objects.equals(wanted, actual)) {
            throw new AssertionError(
                    name + ": expected=" + wanted + ", actual=" + actual);
        }
    }

    static void runTests() {
        List<Product> products = sample();
        Map<String, Integer> expectedPrices = Map.of(
                "Books", 270,
                "Food", 110,
                "Office", 15,
                "Tech", 290);
        Map<String, Integer> expectedRevenue = Map.of(
                "Books", 390,
                "Food", 260,
                "Office", 60,
                "Tech", 290);

        expect(expectedPrices,
                sumPrices(products.stream()), "sum prices");
        expect(expectedRevenue,
                revenues(products.stream()), "revenues");
        expect(expectedRevenue,
                revenues(products.parallelStream()),
                "parallel revenues");

        expect(Map.of(
                "Books", "Java",
                "Food", "Tea",
                "Office", "Pen",
                "Tech", "Mouse"),
                minimumNames(products.stream()), "minimum names");

        expect(Map.of(
                "Books", "Clean Code",
                "Food", "Coffee",
                "Office", "Pen",
                "Tech", "Keyboard"),
                maximumNames(products.stream()), "maximum names");

        expect(priciest(products.stream()),
                priciestWithReducing(products.stream()),
                "maxBy equals reducing max");

        Map<String, Optional<Product>> min =
                cheapest(products.stream());
        expect("Java",
                min.get("Books").orElseThrow().name(),
                "minimum Books");

        Map<Boolean, Optional<Product>> partitions =
                pricePartitions(products.stream());
        expect("Keyboard",
                partitions.get(true).orElseThrow().name(),
                "expensive partition maximum");
        expect("Mouse",
                partitions.get(false).orElseThrow().name(),
                "cheap partition maximum");

        expect(Map.of(),
                sumPrices(Stream.<Product>empty()),
                "empty grouping");
        expect(Map.of(),
                cheapest(Stream.<Product>empty()),
                "empty grouping with Optional");
        Map<Boolean, Optional<Product>> emptyPartitions =
                pricePartitions(Stream.<Product>empty());
        expect(true, emptyPartitions.containsKey(true),
                "true partition exists");
        expect(true, emptyPartitions.containsKey(false),
                "false partition exists");
        expect(Optional.empty(), emptyPartitions.get(true),
                "empty true partition");
        expect(Optional.empty(), emptyPartitions.get(false),
                "empty false partition");

        // Each Product remains unchanged; the grouped results are read-only.
        expect(7, products.size(), "input unchanged");
    }

    public static void main(String[] args) {
        runTests();
        List<Product> products = sample();

        System.out.println("sumPrices="
                + sumPrices(products.stream()));
        System.out.println("revenues="
                + revenues(products.stream()));
        System.out.println("minNames="
                + minimumNames(products.stream()));
        System.out.println("maxNames="
                + maximumNames(products.stream()));
        System.out.println("maxViaReducingBooks="
                + priciestWithReducing(products.stream())
                        .get("Books").orElseThrow().name());

        Map<Boolean, Optional<Product>> p =
                pricePartitions(products.stream());
        System.out.println("highPartitionMax="
                + p.get(true).orElseThrow().name());
        System.out.println("lowPartitionMax="
                + p.get(false).orElseThrow().name());

        Map<Boolean, Optional<Product>> empty =
                pricePartitions(Stream.<Product>empty());
        System.out.println("emptyFalse=" + empty.get(false).isEmpty());
        System.out.println("emptyTrue=" + empty.get(true).isEmpty());
        System.out.println("tests=PASS");
    }
}
```

Compile and run commands:

```bash
javac DownstreamReducingDemo.java
java DownstreamReducingDemo
```

Expected stdout:

```text
sumPrices={Books=270, Food=110, Office=15, Tech=290}
revenues={Books=390, Food=260, Office=60, Tech=290}
minNames={Books=Java, Food=Tea, Office=Pen, Tech=Mouse}
maxNames={Books=Clean Code, Food=Coffee, Office=Pen, Tech=Keyboard}
maxViaReducingBooks=Clean Code
highPartitionMax=Keyboard
lowPartitionMax=Mouse
emptyFalse=true
emptyTrue=true
tests=PASS
```

### Value Breakdown

| Category | Products | Total Price | Revenue |
| --- | --- | ---: | ---: |
| Books | Java 120 × 2; Clean Code 150 × 1 | 270 | 390 |
| Food | Tea 40 × 3; Coffee 70 × 2 | 110 | 260 |
| Office | Pen 15 × 4 | 15 | 60 |
| Tech | Mouse 90 × 1; Keyboard 200 × 1 | 290 | 290 |
| **Total** | 7 products | **685** | **1,000** |

`sumPrices` sums **the list price of each line**, while `revenues` sums **price multiplied by quantity** for each line. The two results differ by business contract; do not confuse `summingInt(Product::price)` with revenue.

In the example, `TreeMap::new` guarantees **category key ordering** in the output `Map`, and `Comparator.comparingInt(...).thenComparing(...)` defines the choice when prices are equal. Do not rely on default `HashMap` iteration order or an accidental result in tie cases.

The program uses `expect` to throw `AssertionError` if a result differs from expectations, without depending on the `java -ea` option. When you want to verify actual correctness in your environment, use JDK 17+ with the `javac`/`java` commands above.

## 7. `partitioningBy(..., minBy/maxBy)` and the Case of an Empty Branch

`groupingBy` is not the only collector that accepts a downstream. `Collectors.partitioningBy` splits data into **two Boolean groups** according to a predicate:

```java
Map<Boolean, Optional<Product>> byExpensive =
        products.stream().collect(
                Collectors.partitioningBy(
                        p -> p.price() >= 100,
                        Collectors.maxBy(BY_PRICE_THEN_NAME)));
```

In the main example, `true` is the group with price 100 or higher, where the most expensive product is `Keyboard` (200); `false` is the group with price under 100, where the most expensive is `Mouse` (90).

An important difference:

- `groupingBy(classifier, downstream)` **does not create keys** for groups that never appeared. For an empty Stream, the Map is empty.
- `partitioningBy(predicate, downstream)` **contains both keys** `true` and `false`, even when the corresponding group is empty. Because `maxBy` returns `Optional`, an empty group has the value `Optional.empty()`.

If you use `partitioningBy(predicate, reducing(0, mapper, Integer::sum))`, the empty side will have a sum of **`0`** (the identity), not `Optional.empty()`. This difference helps you choose a downstream based on what you want to express: **“no extremum exists”** or **“the sum of an empty group is 0”**.

You should also not call `map.get(true)` and then `.get()` directly on `Optional` without checking, as it can throw `NoSuchElementException` when the group has no elements. Use `ifPresent`, `orElse`, `orElseGet`, `map`, or `orElseThrow` when absence is considered abnormal by contract.

## 8. `collectingAndThen` Combined with `minBy/maxBy`

An `Optional<Product>` output matches the semantics of an extremum, but sometimes the UI only needs the **name** of the cheapest/most expensive product. `Collectors.collectingAndThen(downstream, finisher)` lets you transform the **final result** of the downstream into another type:

```java
Map<String, String> nameOfCheapest =
        products.stream().collect(Collectors.groupingBy(
                Product::category,
                TreeMap::new,
                Collectors.collectingAndThen(
                        Collectors.minBy(BY_PRICE_THEN_NAME),
                        optional -> optional
                                .map(Product::name)
                                .orElse("NONE"))));
```

Diagram:

```text
Products in a category
          │
          ▼
    minBy(comparator)
          │
          ▼
    Optional<Product>
          │
          ▼
  collectingAndThen:
  opt.map(Product::name).orElse("NONE")
          │
          ▼
        String
```

In `groupingBy`, a key that appears has at least one element, so if the classifier and source are valid, `minBy` for that key is non-empty. Still, the finisher should have clear semantics when reused with another collector or invoked on an empty group, as in `partitioningBy`. Here, `"NONE"` is an illustrative display policy; if a missing extremum is an error, do not hide it with a placeholder—handle it as a business state.

**Note:** `collectingAndThen` runs **after the downstream finishes accumulating**, not per source element. If the goal is to transform each element before or during group collection, use Stream's `map` or the `Collectors.mapping` downstream.

## 9. `mapping` Combined with `reducing`

There are two semantically equivalent ways to sum the price property of each group:

```java
Map<String, Integer> first = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.reducing(0,
                        Product::price, Integer::sum)));
```

And:

```java
Map<String, Integer> second = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.mapping(
                        Product::price,
                        Collectors.reducing(0, Integer::sum))));
```

In the first approach, `reducing` integrates the `mapper` step. In the second approach, `mapping` converts each `Product` to `Integer` and then `reducing` sums the numbers. Both make it clear that groups are determined on **Product** before selecting `price`.

For simple sums, this option is even more concise:

```java
Map<String, Integer> sums = products.stream()
        .collect(Collectors.groupingBy(
                Product::category,
                Collectors.summingInt(Product::price)));
```

**Prefer specialized collectors** (`counting`, `summingInt`, `summingLong`, `averagingInt`, `summarizingInt`, etc.) when they express the exact intent. Use `reducing` for problems that genuinely combine via an operation with a clear identity/mapper/op, or when an aggregation structure is needed that built-in collectors do not express concisely.

## 10. `minBy`/`maxBy` vs. Grouping and Iterating Again

The two-step approach:

```java
Map<String, List<Product>> grouped = products.stream()
        .collect(Collectors.groupingBy(Product::category));

Map<String, Optional<Product>> maxByCategory =
        new java.util.HashMap<>();

grouped.forEach((category, list) ->
        maxByCategory.put(
                category,
                list.stream().max(BY_PRICE_THEN_NAME)));
```

This approach is valid if you **need to keep the full lists** for another purpose. However, if the problem only needs the most expensive element, it creates many group lists and then scans them again to find the extremum.

Direct downstream:

```java
Map<String, Optional<Product>> maxByCategory =
        products.stream().collect(
                Collectors.groupingBy(
                        Product::category,
                        Collectors.maxBy(BY_PRICE_THEN_NAME)));
```

expresses the intent in a single collect operation and avoids creating a `List<Product>` for each group in the result. However, you should not claim that a downstream is always faster by a fixed factor in every situation; cost depends on data, collector, number of keys, and parallelism characteristics. Evaluate correctness and memory first, and benchmark if performance is a real requirement.

## 11. Rules of Reduction: Identity and Associativity

`reducing(identity, mapper, op)` uses a combining operation `op` on `U` values. For valid behavior when reducing by group and executing in parallel, `identity` must be an identity element, and the combining operation must have **associativity**.

For addition:

```text
identity = 0
combine(a, b) = a + b

combine(0, x) = x
combine(x, 0) = x
combine(combine(a, b), c) = combine(a, combine(b, c))
```

`Integer::sum` fits Java integer addition semantics. However, for values exceeding the range of `int`, the sum can overflow; problems with large money/price values should choose an appropriate numeric type and arithmetic policy, such as `long`, `BigInteger`, `BigDecimal`, or overflow checking.

**Counterexample:**

```java
// Does not follow the reduction contract for a stable result:
int result = java.util.stream.Stream.of(10, 3, 2)
        .collect(java.util.stream.Collectors.reducing(
                0, (a, b) -> a - b));
```

Subtraction does not have `0` as a two-sided identity (`0 - x` is not equal to `x`), and it is also not associative. Groups may be combined differently in parallel, so the result is not guaranteed to preserve the intended meaning.

**Do not use a shared mutable object as the identity and mutate it directly inside the accumulator** of `reducing`. If you need to add elements into an `ArrayList`, `HashMap`, or mutable container, use `collect` with a supplier that creates independent containers or a built-in collector, instead of using `reducing` with unsafe side effects. In parallel processing, this is especially important.

### `minBy` and `maxBy` also require a consistent comparator

The comparator must reflect a consistent rule while the collector is working. Do not use a comparator that has mutable state, reads a mutable variable being modified, or generates random numbers on each comparison. If the comparator is inconsistent, “smallest/largest” can become ambiguous, especially during parallel grouping and reduction.

When prices are equal, specify a tie-breaker if the output requires a specific Product. If you only need the highest/lowest price without caring about the representative record, you can reduce the price directly with `mapping` + `reducing`, or use `summing`/`summarizing`/a specialized collector when appropriate.

## 12. Nulls, Empty Groups, and Optional

### Do not let `groupingBy` receive a `null` classification key

`Collectors.groupingBy` does not accept a classifier returning `null`:

```java
// If category() == null, groupingBy throws NullPointerException.
products.stream()
        .collect(Collectors.groupingBy(Product::category));
```

If `category` can be missing, define a policy: reject the data, put it into an `"UNKNOWN"` group, or use a key type that represents a separate state. There is no way for a downstream `minBy`/`maxBy` to fix a `null` key from the outer grouping step.

### `Optional.empty()` vs. Map `null`

`Map<String, Optional<Product>>` can have two situations:

- **Missing key**: `map.get("Missing")` returns `null` because that category was not created by `groupingBy`.
- **Key present with an empty Optional**: common with `partitioningBy` when a Boolean branch has no elements, or when you apply a downstream that can yield an empty result after filtering.

Therefore, the call:

```java
Optional<Product> maybe =
        grouped.getOrDefault("Missing", Optional.empty());
```

is a valid way to handle both a non-existent key and an empty Optional case, provided `grouped` is `Map<String, Optional<Product>>`.

Do not write `grouped.get("Missing").get()` without confirming that the key exists and the Optional has a value. For reductions without identity, the API design should express **the possibility of no result**. For sums with identity, choose a sensible identity like 0 and understand why an empty group's sum has that value.

### Nulls in elements or mapper results

If Stream elements can be `null`, `Product::category` or a comparator accessing properties can throw `NullPointerException`. Validate, transform, or filter intentionally before grouping. If a missing element is an error to report, do not silently ignore it.

`Collectors.minBy`/`maxBy` returns an `Optional` of the result; `Optional` does not allow containing a `null` value. Avoid letting comparators or data ingestion pipelines treat `null` as a valid Product. With `reducing`'s mapper, also ensure the combining operation handles types and `null` states clearly; if business logic requires recording errors, put failure results into the data model rather than letting a sum drop elements without a trace.

## 13. Ordering, Parallelism, and Collector Characteristics

By default, `groupingBy` **does not guarantee the Map type or key order**. In the full example, `TreeMap::new` intentionally ensures the key order `Books`, `Food`, `Office`, `Tech` for stable stdout. If you want order by first encounter of keys in sequential data, consider `LinkedHashMap::new`.

`minBy` and `maxBy` do not sort the entire group: they find the extremum element according to the comparator. When you need **multiple top elements** rather than just one extremum, `maxBy` is not enough; use an appropriate collector/algorithm for top-K.

When using `parallelStream()`:

- Avoid directly updating shared `ArrayList`, `HashMap`, or counter variables from `map`, `filter`, classifier, or comparator.
- Ensure the reduction has a neutral identity and a valid associative combining operation.
- Ensure the comparator is stable; tie-breakers help ensure record selection does not depend on accidental merge order.
- Do not rely on the number of lambda invocations or the order of combiner calls to infer results.
- Parallel execution is not automatically faster; few groups, small sources, and merge costs can make overhead larger than the benefit.

`groupingByConcurrent` has concurrent and unordered characteristics, used when you genuinely need concurrent grouping under suitable conditions. It has different ordering constraints than `groupingBy`; do not substitute it mechanically when the application relies on encounter order. Downstream `reducing`, `minBy`, and `maxBy` can be composed with grouping collectors according to contract, but running concurrently requires considering thread safety and actual performance.

## 14. Common Mistakes

**Mistake 1 — using `Stream.reduce` instead of a downstream.** `Stream.reduce(...)` returns a single Stream-wide result; `Collectors.reducing(...)` returns a Collector to place after `groupingBy` or `partitioningBy`. Do not use the two methods as if they had the same signature.

**Mistake 2 — calling `reducing(0, Integer::sum)` directly on a `Product` group.** The downstream element type is still `Product` if `mapping` has not been applied. Use `reducing(0, Product::price, Integer::sum)` or `mapping(Product::price, reducing(0,Integer::sum))`.

**Mistake 3 — forgetting `Optional` with `minBy` and `maxBy`.** `Map<K, Optional<Product>>` cannot be directly assigned to `Map<K, Product>`. Handle emptiness explicitly or use `collectingAndThen`.

**Mistake 4 — confusing Map print order with price order.** `TreeMap` sorts **category keys**, not products by price; the min/max comparator determines the extremum within each group.

**Mistake 5 — inconsistent tie handling.** `maxBy(comparingInt(Product::price))` does not specify a concrete choice between two equal-priced products. If determinism is needed, add an explicit tie-breaker.

**Mistake 6 — using subtraction in a comparator.** `(a,b) -> a.price()-b.price()` risks overflow; use `comparingInt`.

**Mistake 7 — using a non-neutral identity or non-associative op.** The reduction may produce wrong or different results in parallel.

**Mistake 8 — calling `Optional.get()` without checking.** An empty partition produces `Optional.empty()` and `.get()` throws `NoSuchElementException`.

**Mistake 9 — summing money with an insufficiently wide numeric type.** `price * quantity` can overflow `int` **before** being summed. If using `long`, cast before the multiplication: `(long) p.price() * p.quantity()`, then use `Long::sum` and identity `0L`.

**Mistake 10 — keeping all products in a group just to find min/max.** If you only need an extremum/sum, a direct downstream usually makes code shorter and avoids keeping group Lists in the result.

**Mistake 11 — misunderstanding `collectingAndThen` as transforming each element.** The finisher runs after the downstream finishes; to convert each `Product` to a price/label, use `mapping` or `reducing`'s mapper.

**Mistake 12 — not distinguishing absent groups from empty groups.** `groupingBy` does not create groups for keys that do not appear; `partitioningBy` creates both true and false. Design Map-reading code based on the appropriate contract.

## 15. Choosing a Collector Based on Required Output

| Requirement | Downstream to consider | Result in each group |
| --- | --- | --- |
| Keep elements as-is | `toList()` | `List<T>` |
| Only need element count | `counting()` | `Long` |
| Sum of an `int` property | `summingInt(mapper)` | `Integer` |
| Sum with custom operation | `reducing(identity, mapper, op)` | `U` |
| Direct combine of `T` without identity | `reducing(op)` | `Optional<T>` |
| Product with lowest price | `minBy(comparator)` | `Optional<T>` |
| Product with highest price | `maxBy(comparator)` | `Optional<T>` |
| Name of highest-priced product | `collectingAndThen(maxBy(...), finisher)` | `String` or other output type |
| Extract property before combining | `mapping(mapper, downstream)` | Depends on downstream |
| Count, min, max, sum, average of numbers | `summarizingInt/Long/Double(mapper)` | Statistics object |

If you only need **one** total across the entire Stream, consider `mapToInt(...).sum()` or terminal `reduce`. If you need **the same aggregation per group**, use `groupingBy` combined with a downstream collector.

## 16. Exercises and Additional Tests

1. With the `Product` list in section 6, write `groupingBy(Product::category, reducing(0, Product::quantity, Integer::sum))` to compute the total quantity per category. Expected Books=3, Food=5, Office=4, Tech=2; total is 14.
2. Write `groupingBy(..., mapping(Product::price, reducing(0,Integer::sum)))` and prove the result matches using the three-parameter overload `reducing(0,Product::price,Integer::sum)`.
3. Add a product `new Product("Java Mini", "Books", 120, 1)`. Which name will `minBy` with the price-then-name comparator select? Explain the comparison policy when prices are equal.
4. Using `partitioningBy(p -> p.price() >= 100, minBy(BY_PRICE_THEN_NAME))`, predict the lowest-priced product in both branches. Also test the case where the source has no high-priced products.
5. Add a `Toys` category with only one element. Verify that `minBy` and `maxBy` return the same product; then test that the Map does not contain the `Toys` key when there is no input belonging to that category.
6. Replace `int price` with `long price` and convert revenue to `long` to avoid `int` multiplication overflow. State clearly where the cast must be placed **before** the multiplication.
7. Write a test for an empty source: `groupingBy(maxBy(...))` returns `{}`, while `partitioningBy(maxBy(...))` has both `true` and `false` with `Optional.empty()`.
8. Write a comparator with an **ascending** name tie-breaker while selecting **descending** price. Test two equal-priced products and compare the result with `maxBy(BY_PRICE_THEN_NAME)`.
9. Try `revenues(products.parallelStream())` and compare with sequential. Explain why `int` addition within a non-overflowing range and without external mutable state yields the same result.
10. If you need count, total price, lowest price, and highest price in the same group, consider `summarizingInt(Product::price)` and state its advantages over computing four separate Maps.

When testing, do not just check the number of groups: you must verify **the right keys, the right extrema, the right sums, the right tie-breakers, and the right empty cases**. For APIs returning `Optional`, clearly verify when a group is absent versus when a group has no matching element.

## 17. Summary

`Collectors.reducing`, `Collectors.minBy`, and `Collectors.maxBy` are important downstream collectors when you need to **reduce each group/partition**:

- `reducing(op)` has no identity, so it returns `Optional<T>`.
- `reducing(identity, op)` combines elements of the same type and returns `T`.
- `reducing(identity, mapper, op)` maps each `T` to `U` and combines them, returning `U`.
- `minBy(comparator)` and `maxBy(comparator)` select an extremum according to a comparison rule, always returning `Optional<T>`.
- `groupingBy` creates groups **only for keys that appear**; `partitioningBy` creates **both Boolean keys**, even if one side is empty.
- `mapping` lets you transform each downstream element; `collectingAndThen` transforms the result **after** the inner collector completes.

Good design requires attention to neutral identity, associativity, stable comparators, numeric types, `Optional`, Map ordering, and missing-data policies. Choose a downstream that expresses the exact result type for each group rather than defaulting to collecting all elements into a `List`.
