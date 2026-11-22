# Stream.min(), Stream.max(), and Comparator in Java

In the **Java Stream API**, the two terminal operations **min()** and **max()** are used to find a minimum or maximum element **according to the passed-in comparison rule**, rather than necessarily finding the smallest number or largest string in a fixed sense.

For an object stream, the signatures are:

~~~java
Optional<T> min(Comparator<? super T> comparator);
Optional<T> max(Comparator<? super T> comparator);
~~~

The result uses **Optional<T>** because a Stream may be empty, having no element to select. The **Comparator** determines the order: if you change the Comparator, the same Stream can produce different min/max results. This lesson explains how to use them, ascending/descending order, multi-criteria comparison, handling ties, null, empty data, primitive streams, and common mistakes. Examples run on **Java 17+**.

## 1. What kind of terminal operations are min() and max()?

A Stream typically has three components: a data source, **intermediate operations** such as filter/map, and a **terminal operation** that executes the pipeline to produce a result or side effect.

~~~java
List<Integer> prices = List.of(120, 20, 450);

Optional<Integer> smallest = prices.stream()
    .min(Comparator.naturalOrder());

Optional<Integer> largest = prices.stream()
    .max(Comparator.naturalOrder());
~~~

These are illustrative statements that need to be placed inside a method with the corresponding imports. With the list above:

- smallest contains 20.
- largest contains 450.
- Stream.min/max terminates the processing pass and consumes the corresponding Stream.
- The operations do not remove or reorder elements of prices.

Key point to remember: **min and max are not intermediate operations**. You cannot write stream.min(...).filter(...) because min returns Optional<T>, not Stream<T>.

### 1.1. Why return Optional?

An empty Stream has no minimum or maximum element:

~~~java
Optional<Integer> emptyResult =
    Stream.<Integer>empty().min(Comparator.naturalOrder());

System.out.println(emptyResult.isEmpty()); // true
~~~

You should not retrieve the result with get() without first verifying that the Optional has a value. With Optional.empty(), get() throws NoSuchElementException.

Appropriate handling:

~~~java
Integer price = products.stream()
    .map(Product::price)
    .min(Integer::compare)
    .orElse(0);
~~~

Here orElse(0) means choosing 0 when empty; the default value **must make business sense**. Do not automatically use 0 for a minimum price if 0 would lead readers to think there is a product priced at 0.

If an empty Stream is an invalid state:

~~~java
Product cheapest = products.stream()
    .min(byPrice)
    .orElseThrow(() -> new IllegalStateException(
        "No products to compare"));
~~~

If an empty Stream is valid, you can return Optional<Product> to the caller so the caller can decide to display a “no data” state.

### 1.2. How much data do min/max need to traverse?

To find a minimum/maximum element in a general source, the system typically needs to compare the relevant elements during reduction. There is no default “looking at the first element is enough” mechanism like findFirst. For an infinite source with no limit, min/max may not terminate.

With n elements and constant-time comparison, the standard reduction approach to pick min/max takes **O(n)** time and can keep a single candidate, so it does not necessarily collect all elements into a new list. However, preceding intermediate operations such as sorted or distinct can add extra cost and memory.

Do not claim that every Stream.min/max always uses constant memory or runs the comparator exactly n−1 times in every pipeline/parallel execution: optimizations, sources, and parallel processors may differ.

## 2. Comparator<T>: an ordering rule, not a boolean condition

Comparator<T> is a functional interface with the core method:

~~~java
int compare(T left, T right);
~~~

The return value is meaningful by its **sign**:

- Negative: left comes **before** right according to the comparison rule.
- 0: the two elements are considered **equal in order** as defined by this comparator.
- Positive: left comes **after** right.

It does not need to return exact −1, 0, +1; only the sign matters.

Example:

~~~java
Comparator<Integer> ascending =
    (left, right) -> Integer.compare(left, right);

Comparator<Integer> descending =
    (left, right) -> Integer.compare(right, left);
~~~

When using ascending, min selects the smallest number naturally and max selects the largest number. When using descending, **the order is reversed**, so min selects the largest number in the original numeric order.

### 2.1. Do not use arbitrary int subtraction

A way of writing that easily causes integer overflow:

~~~java
Comparator<Integer> wrong =
    (left, right) -> left - right;
~~~

If left and right are on opposite sides of int bounds, subtraction can overflow and flip the sign of the result, violating the comparator contract.

Better:

~~~java
Comparator<Integer> safe = Integer::compare;
~~~

For object data with an int field:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);
~~~

**Comparator.comparingInt** avoids having to write subtraction manually and also makes the comparison intent clear. When the price is long or double, there are corresponding comparingLong and comparingDouble overloads.

### 2.2. Important Comparator contract

A proper comparator must define a consistent ordering relation, in which:

- Antisymmetry in sign: compare(a,b) and compare(b,a) have opposite signs.
- Transitivity: if a comes after b and b comes after c, then a must come after c, and similarly in the reverse direction.
- If compare(a,b) equals 0, then for any z, the signs of compare(a,z) and compare(b,z) must be consistent per the Comparator contract.
- Results should be stable when the data used for comparison does not change.

You should not use a comparator based on random values, the current clock, or a mutable field being updated during comparison; min/max can become unpredictable or incorrect.

**Comparator.compare(a,b) == 0 does not necessarily mean a.equals(b).** If comparing only price, two products with different SKUs but the same price will be treated as tied in order, even though the two objects are different. This is especially important when selecting min/max and when using a comparator in TreeSet/TreeMap.

## 3. Comparator.naturalOrder() and reverseOrder()

For types supporting **Comparable**, you can use natural order:

~~~java
List<Integer> values = List.of(7, 3, 10, 4);

int smallest = values.stream()
    .min(Comparator.naturalOrder()).orElseThrow();

int largest = values.stream()
    .max(Comparator.naturalOrder()).orElseThrow();
~~~

The results are 3 and 10.

String also implements Comparable<String>, so with Comparator.naturalOrder(), strings are compared according to String's compareTo rule (lexicographical order based on UTF-16 values). **Do not** assume this rule is natural-language or locale-specific sorting order.

~~~java
String smallest = Stream.of("zebra", "apple", "pear")
    .min(Comparator.naturalOrder()).orElseThrow();
// "apple"
~~~

To reverse the order:

~~~java
Comparator<Integer> reversed = Comparator.reverseOrder();

int selected = Stream.of(3, 9, 5)
    .min(reversed)
    .orElseThrow();
// 9, because 9 comes "first" in the reversed order.
~~~

### 3.1. A reversed comparator does not change the definition of min/max

Fundamental rule:

**min(comparator)** selects the earliest element according to the comparator; **max(comparator)** selects the latest element according to the comparator.

Therefore:

~~~java
int a = Stream.of(1, 5, 9)
    .max(Comparator.naturalOrder()).orElseThrow(); // 9

int b = Stream.of(1, 5, 9)
    .max(Comparator.reverseOrder()).orElseThrow(); // 1
~~~

Do not think the name max always guarantees selecting the numerically largest value, regardless of the comparator. The comparator is the source that defines the order.

### 3.2. Comparator.reversed()

For any comparator:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);

Comparator<Product> byPriceDescending =
    byPrice.reversed();
~~~

byPriceDescending defines higher price as coming before lower price. When calling max(byPriceDescending), the result can be the **lowest price** in the original price order.

In particular, **min(byPrice.reversed())** corresponds to the highest-priced element according to byPrice, while **max(byPrice.reversed())** corresponds to the lowest price. Do not reverse both the comparator and min/max unless the logic has been carefully accounted for.

## 4. Comparator.comparing: comparing by property

In applications, Stream elements are usually objects. For example, a record:

~~~java
record Product(String sku, int price, int score) {}
~~~

If you want to find the cheapest product:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);

Optional<Product> cheapest = products.stream()
    .min(byPrice);
~~~

If you want the product with the highest rating score:

~~~java
Comparator<Product> byScore =
    Comparator.comparingInt(Product::score);

Optional<Product> highestRated = products.stream()
    .max(byScore);
~~~

Both operations use the same data but select by **two different criteria**. This is the benefit of a comparator: changing the rule without changing the source data.

### 4.1. comparing and comparingInt/Long/Double

With a Comparable key:

~~~java
Comparator<Product> bySku =
    Comparator.comparing(Product::sku);
~~~

With a primitive key:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);
~~~

If Product.price() returns long, use comparingLong; if it returns double, use comparingDouble, which has floating-point semantics per Double.compare. Primitive-specific factories generally avoid boxing/unboxing of the key during comparison compared to creating unnecessary wrappers.

### 4.2. Comparing a nullable String field

If sku can be null, Comparator.comparing(Product::sku) is not naturally safe: String's natural order does not compare null like a valid string. You can explicitly specify the position for null:

~~~java
Comparator<Product> byNullableSku =
    Comparator.comparing(
        Product::sku,
        Comparator.nullsLast(Comparator.naturalOrder()));
~~~

With the rule above, a null SKU comes **after** non-null SKUs in ascending comparison. When calling min(), a valid SKU will be preferred over a null SKU if there is at least one non-null element.

It is important to distinguish:

1. **A property field of an element may be null**: comparing combined with nullsFirst/nullsLast can handle it.
2. **The Stream element itself is null**: even if the comparator can handle it, Stream.min/max may throw NullPointerException if the reduction result is null, because Optional does not hold a null value.

In most business designs, you should filter out null elements before selecting min/max or define clear validation instead of expecting min/max to use null as a normal result value.

## 5. thenComparing: breaking ties with secondary criteria

If comparing only by price:

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);
~~~

Two products with the same price are considered **equal in order** by the comparator even if they have different SKUs. When Stream.min/max picks one element among tied elements, **you should not rely on always picking the first element** if the comparator cannot distinguish them, especially when changing the source or using parallel execution.

To make the selection predictable, add one or more tie-breaking criteria:

~~~java
Comparator<Product> byPriceThenSku =
    Comparator.comparingInt(Product::price)
        .thenComparing(Product::sku);
~~~

Rule:

1. Compare price first.
2. If prices differ, the result is decided by price.
3. If prices are equal, compare SKU in natural order.
4. If SKUs are also equal, the comparator still treats the two objects as tied in order.

With the data:

~~~text
Book  : 120
Pen   : 20
Lamp  : 450
Case  : 120
Glass : 450
~~~

min(byPriceThenSku) selects **Pen** (20). max(byPriceThenSku) selects **Lamp** (450, SKU "Lamp" comes after "Glass" in natural order).

**Note:** deterministic tie-breaking is only needed to the extent required by business logic. If SKU is unique per product, thenComparing(sku) is usually enough. If SKU is not unique, you can add another stable identifier. Avoid using random data or the incidental return order of the source as a tie-breaking mechanism.

### 5.1. Comparing more properties

~~~java
Comparator<Product> order =
    Comparator.comparingInt(Product::score)
        .thenComparingInt(Product::price)
        .thenComparing(Product::sku);
~~~

The rule is ascending by score, then price, then sku. Calling max(order) selects the product with the highest score; among those with the same score, it selects the highest price; among those with the same score and price, it selects the SKU that comes last according to the comparator.

This is not necessarily “best rating then cheapest price”. If you want high score but **low price** to be preferred on a tie, you must reverse **only** the price comparator:

~~~java
Comparator<Product> bestScoreThenCheapest =
    Comparator.comparingInt(Product::score)
        .thenComparing(
            Comparator.comparingInt(Product::price).reversed())
        .thenComparing(Product::sku);
~~~

With max(bestScoreThenCheapest), a **lower** price is considered to come later in the reversed price rule, so it is preferred among items with the same score. Naming the comparator after its intent helps avoid ordering mistakes.

### 5.2. Where reversed is placed affects the result

~~~java
Comparator<Product> allReversed =
    Comparator.comparingInt(Product::score)
        .thenComparing(Product::sku)
        .reversed();
~~~

The final reversed reverses the **entire** chain of criteria. If you only want to reverse SKU order while keeping score ascending, you must write it explicitly:

~~~java
Comparator<Product> scoreAscSkuDesc =
    Comparator.comparingInt(Product::score)
        .thenComparing(
            Comparator.comparing(Product::sku).reversed());
~~~

This is an important distinction when using a comparator for min/max, sorted, or ordered data structures.

## 6. Optional<T>: safe usage

Stream.min/max on an object stream returns Optional<T>. Some ways to handle it:

~~~java
Optional<Product> candidate = products.stream().min(byPrice);

candidate.ifPresent(product ->
    System.out.println(product.sku()));

Product fallback = candidate.orElse(defaultProduct);

Product required = candidate.orElseThrow(
    () -> new IllegalStateException("No product found"));
~~~

These are illustrative snippets requiring variables products, byPrice, and defaultProduct to be validly declared.

Choose a strategy based on business meaning:

- **orElse**: always has a valid fallback value; note that the argument expression is evaluated on call.
- **orElseGet**: computes the default value only when Optional is empty, useful if the fallback is expensive.
- **orElseThrow**: when having no element is an error condition.
- **ifPresent**, **map**, **flatMap**: continue processing without unsafe unwrapping.
- **Optional.empty()**: is a valid return value when the problem allows not finding an object.

You should not call Optional.get() immediately after min/max without proving the Stream is non-empty. Distinguish between an empty product list and a product with price 0; they do not have the same meaning.

### 6.1. Filter before min/max

~~~java
Optional<Product> cheapestAvailable = products.stream()
    .filter(product -> product.price() > 0)
    .min(Comparator.comparingInt(Product::price));
~~~

If no Product has price > 0, the result is Optional.empty(), even if the initial source was not empty.

If you need to select an element based on a certain status, filter first and then find min/max; do not pick the min of the entire source and check the status afterward, because the result can be different:

~~~java
// Select the lowest price among the eligible group:
products.stream().filter(this::eligible).min(byPrice);
~~~

This is an illustrative snippet assuming an instance method eligible and a comparator byPrice. What matters is the **business order**: filtering first creates the candidate set, then an element is selected from that candidate set.

## 7. Comparison with sorted().findFirst()

Another way to get the smallest element is to sort and then take the first element:

~~~java
Optional<Product> smallest = products.stream()
    .sorted(byPrice)
    .findFirst();
~~~

In terms of intending to pick the smallest element, it can be equivalent to min(byPrice) in typical cases with a consistent comparator and no tie/null issues. But the technical trade-offs differ:

| Approach | Goal | Typical cost |
| --- | --- | --- |
| min(comparator) | Select one minimum element | O(n) comparisons in general, no need to build a sorted list |
| max(comparator) | Select one maximum element | O(n) comparisons in general |
| sorted(comparator).findFirst() | Sort then take the first | Typically O(n log n) comparisons, may require buffering |
| sorted(comparator).toList() | Get all elements in order | Sorts everything, returns resulting List |
| collect(minBy(comparator)) | Select min via Collector | Useful as a downstream collector |

**Recommendation:** if you only need a single extremum, use **min/max directly**. sorted is useful when you **actually need a sorted list** or a subset of results with additional requirements.

Another point: sorted on an ordered stream is stable per the Stream.sorted contract; for elements tied under the comparator, picking via sorted().findFirst() can reflect source order. Do not extrapolate the tie-breaking behavior of sorted/findFirst to Stream.min/max; if you need deterministic selection across all execution modes, add an explicit tie-breaker.

### 7.1. No need for sorted to find max

~~~java
Product maxPrice = products.stream()
    .max(Comparator.comparingInt(Product::price))
    .orElseThrow();
~~~

Writing sorted(...).reduce(...) or sorted(...).findFirst() just to find max usually makes the code longer and can do unnecessary work. Conversely, if you need the top 5 products by multiple criteria, sorting (or a specialized top-k structure) is appropriate.

## 8. IntStream, LongStream, and DoubleStream have min/max without a Comparator

Object Stream<T> uses a Comparator. Primitive streams have built-in min/max:

~~~java
OptionalInt min = IntStream.of(7, 3, 10).min();
OptionalInt max = IntStream.of(7, 3, 10).max();
~~~

The results contain 3 and 10, respectively. This is **OptionalInt**, not Optional<Integer>.

Similarly:

~~~java
OptionalLong largest = LongStream.of(4L, 8L).max();
OptionalDouble smallest = DoubleStream.of(2.5, 1.5).min();
~~~

Characteristics:

- No Comparator needed on primitive streams.
- No boxing of int/long/double values for the core reduction.
- On an empty source, returns an empty OptionalInt/OptionalLong/OptionalDouble.
- To select an object by an int property while keeping **the whole object**, use Stream<Product>.min(Comparator.comparingInt(Product::price)).
- To get only the minimum number of the property, use products.stream().mapToInt(Product::price).min().

Example:

~~~java
int minPrice = products.stream()
    .mapToInt(Product::price)
    .min()
    .orElseThrow();
~~~

The result is the price, not the Product. This is a reasonable choice when the goal is aggregating a property, avoiding creating/storing unnecessary wrappers.

### 8.1. Floating-point numbers with NaN and signed zero

DoubleStream.min/max has semantics with **NaN** and **-0.0/+0.0** to be aware of. In Java, Double.compare and standard numeric comparison operators are not completely identical in these cases. Per the DoubleStream.min/max contract, if NaN is present then the result is NaN; for zero, min treats -0.0 as smaller than +0.0 and max treats +0.0 as larger than -0.0.

If business data does not allow NaN or Infinity, you should validate beforehand rather than expecting min/max to handle them in a business-meaningful way.

Example:

~~~java
double min = DoubleStream.of(4.0, Double.NaN, 1.0)
    .min()
    .orElseThrow();
// The result is NaN.
~~~

When calculating money, avoid using double arbitrarily if exact decimal digits are required; consider BigDecimal and an appropriate comparator according to currency policy.

## 9. Optional and null in min/max

Do not put null elements into a Stream and expect Optional to hold null:

~~~java
List<String> values = new ArrayList<>();
values.add(null);
values.add("Java");
~~~

If the min/max reduction selects null, creating the resulting Optional can throw NullPointerException. Using a nullsFirst/nullsLast comparator **does not guarantee** that min/max can return null inside Optional.

The clearest way to handle this is usually:

~~~java
Optional<String> result = values.stream()
    .filter(Objects::nonNull)
    .min(Comparator.naturalOrder());
~~~

If business requirements treat null as “no value”, filtering out null before selecting the extremum makes sense. If null is a special state that must be represented in the result, design an explicit wrapper/status-marker type instead of trying to make Optional<T> carry null.

### 9.1. Nullable comparison key vs. null element

~~~java
Comparator<Product> byNullableSku =
    Comparator.comparing(
        Product::sku,
        Comparator.nullsLast(Comparator.naturalOrder()));
~~~

This is suitable when Product is non-null but Product.sku() may be null. If Product itself is null, Product::sku has no valid receiver.

You can use Comparator.nullsFirst/last at the **Product level** with a child comparator, but the min/max result is still constrained by Optional not being able to hold null. In many problems, removing nulls at the source is easier to understand.

## 10. Selecting an extremum in data with duplicate values

Suppose two products have a price of 450. If the comparator compares only price, both are **maximum candidates**.

~~~java
Comparator<Product> byPrice =
    Comparator.comparingInt(Product::price);
~~~

With tied elements, a valid result can be any object sharing the extremum according to the comparator. **Do not rely on a rule of picking “whichever element appears first” as a business contract of min/max**, especially when switching to a parallel stream.

If the problem requires **all** products with the highest price, min/max returning a single object will not be enough. You can do it in two steps over a stable Collection:

~~~java
int maximum = products.stream()
    .mapToInt(Product::price)
    .max().orElseThrow();

List<Product> allMostExpensive = products.stream()
    .filter(product -> product.price() == maximum)
    .toList();
~~~

This snippet creates **two new streams** from the products Collection; it does not reuse a consumed Stream. It is only correct when the source is suitable for re-traversal, the data is not mutated between the two passes, and price is meaningful under the rule under consideration.

If you only need **one** stable representative according to a completely deterministic order, adding thenComparing on a unique identifier is simpler:

~~~java
Comparator<Product> byPriceThenSku =
    Comparator.comparingInt(Product::price)
        .thenComparing(Product::sku);
~~~

If multiple elements are still tied on both price and sku, you need to specify an additional unique key or another tie-breaking policy.

### 10.1. Comparison with reduce

You can express min as a reduction:

~~~java
Optional<Product> cheapest = products.stream()
    .reduce((left, right) ->
        byPrice.compare(left, right) <= 0 ? left : right);
~~~

However, this approach is verbose and error-prone when changing comparison rules, handling null, or running in parallel. When you already have a Comparator, **Stream.min(byPrice)** expresses the intent directly and is easier to review.

## 11. How does Comparator in Stream.max/min differ from Comparator in sorted?

**A Comparator does not change its nature** when used in different APIs. What changes is the goal of the operation:

~~~java
products.stream().min(byPrice);        // Select one element that comes first
products.stream().max(byPrice);        // Select one element that comes last
products.stream().sorted(byPrice);     // Create an ordered pipeline
~~~

Shared comparators are reused in many places; what matters is declaring them with **clear business meaning**. When reviewing APIs or reading code, distinguish:

- **Natural order / comparison value:** the Comparator rule.
- **Which extremum to find:** min or max.
- **Candidate source:** the elements remaining after filter.
- **Ties in rank:** whether there is a secondary criterion or whether all tied candidates must be returned.
- **What result is needed:** a Product or just the price number.

Do not use the same comparator that compares by price and expect it to select by score; you need a different comparator for score.

## 12. Complete runnable Java 17+ program

The program uses a Product record with three fields sku, price, score; and comparators for price, score, and tie-breaking. It directly demonstrates:

- min by price then product SKU.
- max by price then product SKU when multiple products share the highest price.
- max by score then product SKU.
- max on a reversed comparator.
- Empty Stream and Optional.empty.
- Natural order with Integer.
- IntStream min on the price property.
- Input list remains unchanged.

Create the file **StreamMinMaxDemo.java**:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

public class StreamMinMaxDemo {
    record Product(String sku, int price, int score) {}

    public static void main(String[] args) {
        List<Product> products = List.of(
            new Product("Book", 120, 4),
            new Product("Pen", 20, 4),
            new Product("Lamp", 450, 5),
            new Product("Case", 120, 3),
            new Product("Glass", 450, 5)
        );

        Comparator<Product> byPriceThenSku =
            Comparator.comparingInt(Product::price)
                .thenComparing(Product::sku);

        Product cheapest = products.stream()
            .min(byPriceThenSku).orElseThrow();
        Product mostExpensive = products.stream()
            .max(byPriceThenSku).orElseThrow();
        System.out.println("min-price=" + cheapest.sku() + ":" + cheapest.price());
        System.out.println("max-price=" + mostExpensive.sku() + ":" + mostExpensive.price());

        Comparator<Product> byScoreThenSku =
            Comparator.comparingInt(Product::score)
                .thenComparing(Product::sku);
        System.out.println("max-score=" + products.stream()
            .max(byScoreThenSku).orElseThrow().sku());

        System.out.println("max-reversed=" + products.stream()
            .max(byPriceThenSku.reversed()).orElseThrow().sku());

        Optional<Product> missing = Stream.<Product>empty()
            .min(byPriceThenSku);
        System.out.println("empty=" + missing.isEmpty());

        System.out.println("natural=" + Stream.of(7, 3, 10, 4)
            .min(Comparator.naturalOrder()).orElseThrow());

        System.out.println("min-int=" + products.stream()
            .mapToInt(Product::price).min().orElseThrow());

        System.out.println("original-size=" + products.size());
    }
}
~~~

In the directory containing the file, run with JDK 17 or later:

~~~bash
javac StreamMinMaxDemo.java
java StreamMinMaxDemo
~~~

**Exact stdout:**

~~~text
min-price=Pen:20
max-price=Lamp:450
max-score=Lamp
max-reversed=Pen
empty=true
natural=3
min-int=20
original-size=5
~~~

### 12.1. Why are the results like this?

**min-price:** Pen has price 20, which is the lowest in the list.

**max-price:** Lamp and Glass both have price 450, so they are compared by SKU; "Lamp" comes after "Glass" in natural order, so max(byPriceThenSku) selects Lamp.

**max-score:** Lamp and Glass both have score 5; the SKU criterion again puts Lamp after Glass, so it is selected.

**max-reversed:** byPriceThenSku.reversed() reverses the entire order, making the last element under the reversed comparator the first element under the original comparator: Pen.

**empty:** Stream.<Product>empty().min(...) finds no product and returns Optional.empty. isEmpty() is true.

**natural:** the smallest natural number among 7, 3, 10, 4 is 3.

**min-int:** mapToInt creates an IntStream of product prices; min() needs no Comparator and returns an OptionalInt with value 20.

**original-size:** min/max operations do not modify the products list, so the size remains 5.

The program uses a record with no null fields and fixed price and score, so comparator results are stable. It does not automatically check all business invariants (such as non-negative prices); real applications need appropriate validation.

## 13. Cases to watch out for in real production code

### 13.1. Comparator may not be consistent with equals

If Product.equals compares all components, but the comparator compares only price, two different Products can yield compare(a,b) == 0. That **does not prevent min/max from finding an extremum**, but it makes identifying a unique Product on ties necessary.

With TreeSet or TreeMap, the comparator also affects key/element identity by order and can cause two different objects to be treated as a single entry. This is additional context reminding you not to equate comparator zero with equals.

### 13.2. Comparator containing mutable state

You should not use a comparator that reads a score changing during the pipeline, or compares against a random clock. Doing so can violate transitivity or consistency, making min/max results unreliable.

### 13.3. Parallel stream processing

Stream.min/max can run on a parallel stream with an appropriate reduction, but the comparator must obey the contract and **have no contending side effects**. Do not modify the source List from callbacks or comparators.

Do not rely on the exact number of compare() calls to update counters or write business data; the number and order of comparisons are not part of the public contract of Stream.min/max.

### 13.4. Do not use a comparator to mutate objects

Wrong intent:

~~~java
Comparator<Product> strange = (left, right) -> {
    updateAudit(left);   // Hypothetical side effect
    return Integer.compare(left.price(), right.price());
};
~~~

This is illustrative code; updateAudit is not a built-in Java API. A comparator should **only compare**. If recording an audit is required, place it in a separate orchestration step with an explicit once/transaction/retry mechanism; do not use the number of times the comparator is called to drive side effects.

### 13.5. Large data and stateful operations

If only one extremum is needed, min/max usually consumes fewer resources than sorted().findFirst(). However, if the source is already indexed or has a database index, a source-side query like SQL ORDER BY ... LIMIT 1 or MIN/MAX can be more efficient than loading all records into Java. Base decisions on business constraints, DB indexes, and profiling, rather than assuming Stream is always optimal.

### 13.6. String and locale

Comparator.naturalOrder() for String does not replace sorting rules appropriate for Vietnamese or other languages. When user-visible comparison by locale is needed, consider **Collator** with an explicit locale policy, while ensuring the comparator is stable and thread-safe if shared.

### 13.7. Monetary amounts and precision

If price is BigDecimal:

~~~java
Comparator<Product> byAmount =
    Comparator.comparing(Product::amount);
~~~

This illustrative snippet assumes Product.amount() returns BigDecimal and is non-null. BigDecimal.compareTo compares numeric value (for example, 2.0 vs. 2.00 can return 0), whereas BigDecimal.equals also considers scale. Therefore, a comparator returning 0 does not necessarily have the same meaning as equals; add a tie-breaker if needed.

## 14. Common mistakes

**Mistake 1 — calling min() or max() without a comparator on Stream<T>.** For an object Stream<T>, you must provide a Comparator<? super T>. No-arg min/max methods only exist on primitive streams such as IntStream.

**Mistake 2 — forgetting Optional.** min/max on Stream<T> returns Optional<T>, not T directly. Calling get() on Optional.empty throws NoSuchElementException.

**Mistake 3 — reversing the comparator and still thinking max is the largest number.** max(reverseOrder()) typically selects the smallest number in natural order. Interpret it as “last according to the comparator” rather than relying on the method name.

**Mistake 4 — comparator returning left.price() - right.price().** int subtraction can overflow. Use Integer.compare or Comparator.comparingInt.

**Mistake 5 — not handling ties.** When multiple products have the same price, a price-only comparator does not uniquely determine which product is selected. Use thenComparing or return all tied extremum elements if the business requires it.

**Mistake 6 — using sorted just to get min.** Sorting everything is usually unnecessary when the goal is only to select one extremum.

**Mistake 7 — using a comparator on one field while expecting selection by another field.** Comparator.comparingInt(Product::price) selects by price; to select by score you need a different comparator.

**Mistake 8 — allowing null without designing for it.** Optional cannot hold null; min/max with a null result can throw NullPointerException. Filter out nulls or represent the missing state with an explicit type.

**Mistake 9 — thinking Stream.min/max mutates the source.** They select a result from the stream without removing or reordering the source Collection. Callbacks that interfere with the source can still cause errors.

**Mistake 10 — using Comparator.naturalOrder for every type.** Types that do not properly implement Comparable will not satisfy the generic bound; define a comparator based on properties or business rules.

**Mistake 11 — confusing String natural order with locale order.** Default String comparison is not equivalent to sorting Vietnamese words by linguistic rules.

**Mistake 12 — using mapToInt to get the extremum while expecting the object.** IntStream.min returns an int; if you want the whole Product, keep Stream<Product> and compare by property.

**Mistake 13 — reusing the same Stream to find min and then max.** A Stream instance cannot be consumed twice. Call products.stream() twice if the source can be re-traversed, or compute both extrema with a collector/custom reduction when efficiency requires it.

**Mistake 14 — comparator depending on state or side effects.** min/max results become unreliable, especially on parallel streams; do not use a comparator to write audits.

**Mistake 15 — forgetting source data cost.** For I/O-backed or database sources, you may need to close the stream or run a server-side query to avoid loading all data just to find min/max.

## 15. Checklist for choosing an approach

| Goal | Usually appropriate approach |
| --- | --- |
| Find the cheapest Product | products.stream().min(Comparator.comparingInt(Product::price)) |
| Find the most expensive Product | products.stream().max(Comparator.comparingInt(Product::price)) |
| Find one Product by two criteria | comparingInt(...).thenComparing(...) |
| Find the smallest int price | products.stream().mapToInt(Product::price).min() |
| Find min on Integer | Stream<Integer>.min(Comparator.naturalOrder()) |
| Want a result when empty | Optional.orElse/orElseGet or return Optional |
| Empty is an error | Optional.orElseThrow |
| Want all elements sharing the extremum | Find the extremum value then filter the stable source again |
| Want top N by multiple criteria | Sort + limit or an appropriate top-k algorithm |
| Want the entire list ordered | sorted(comparator).toList() |
| Have a nullable String key | Comparator.nullsFirst/nullsLast at the key level, check null elements separately |
| Data is monetary | Numeric type and comparator matching precision rules |

## 16. Self-check questions

1. Why does Stream<Product>.min require a Comparator, while IntStream.min does not?
2. When passing Comparator.reverseOrder to max, what does the result mean compared to natural order?
3. When does Optional.empty appear and why should you not call get directly?
4. For two Products with equal price, does compare(a,b) == 0 guarantee a.equals(b)?
5. How does thenComparing change how tied elements are selected?
6. Why is Comparator.comparingInt better than subtracting two ints for comparison?
7. If all products with the highest price are needed, is min/max returning one object sufficient?
8. Why can sorted().findFirst() be more expensive than min() when only one extremum is needed?
9. What is the difference between the min Product by price and the min int value from mapToInt?
10. If there are null elements, does Comparator.nullsFirst guarantee Optional can return null?
11. Why is varying a Comparator by a mutable field during processing dangerous?
12. Why is String's natural order not the standard sorting order for the Vietnamese locale?
13. In a parallel Stream, should you update a counter variable inside Comparator.compare?
14. How can you reuse a Collection to get both min and max without reusing the same Stream?
15. When there is a database and only the cheapest product is needed, why is an indexed query sometimes more suitable than processing all objects in Java?

**Conclusion:** **min and max select an extremum according to Comparator order**, not according to a fixed meaning of “small” or “large”. For an object Stream, the result is always Optional<T>; empty streams, nulls, data types, and tie-breaking policies must be handled. When only one element is needed, use min/max directly with a clearly named Comparator and tie-breaker; use primitive streams when only numeric values are needed; use sorted when full ordering is truly required.