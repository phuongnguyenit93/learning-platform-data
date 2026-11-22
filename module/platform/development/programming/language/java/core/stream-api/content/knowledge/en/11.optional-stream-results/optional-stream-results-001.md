# Handling Optional Returned by findFirst, findAny, min, max, and reduce

In the Java Stream API, many requirements take the form of "finding an element": finding the first eligible order, finding the largest invoice, getting the lowest score, or combining multiple values into a single result. However, **an element cannot always be found**. A list may be empty, or `filter` steps may filter out all data. If the API only returned a `T` object, how would you distinguish "no result" from a valid value?

Java solves this problem with **`Optional<T>`**. The terminal operations `findFirst()`, `findAny()`, `min(...)`, `max(...)`, and certain overloads of `reduce(...)` return an `Optional` to clearly represent **having a value** or **having no value**. For primitive Streams, Java provides `OptionalInt`, `OptionalLong`, and `OptionalDouble`.

This lesson belongs to the chapter **Optional in Stream Results** of the **JAVA_STREAM_API** module. You will learn how to read Optional results, handle empty cases safely, distinguish search and aggregation methods, understand the impact of encounter order, lazy evaluation, and parallel Streams, while preparing your foundation for `collect`, grouping, custom collectors, `Spliterator`, and Stream Gatherers.

## 1. What does Optional represent?

`Optional<T>` is an object representing one of two states:

- **Has a value (`present`):** contains a non-`null` object `T`.
- **Has no value (`empty`):** contains no object.

Example:

~~~java
import java.util.Optional;

Optional<String> found = Optional.of("DH01");
Optional<String> absent = Optional.empty();

System.out.println(found.isPresent());  // true
System.out.println(absent.isPresent()); // false
~~~

A value can be empty in a business sense while still being **present**: `Optional.of("")` is present and contains an empty string. Only `Optional.empty()` represents the "no value" state. Do not equate an empty string, the number 0, or an empty list with an empty Optional.

With the Stream API, Optional forces the caller **to decide how to handle not finding a result**, such as using a default value, throwing a business exception, or performing no action at all.

~~~mermaid
flowchart LR
    A["Stream<Order>"] --> B["filter: paid orders"]
    B --> C["findFirst()"]
    C --> D{"Optional<Order>"}
    D -->|"present"| E["Process Order"]
    D -->|"empty"| F["Use default / report not found"]
~~~

All five main operations covered in this lesson are **terminal operations**: once invoked, the pipeline is consumed and cannot be run again on the same Stream object.

## 2. Quick Reference Table of Methods Returning Optional

| Operation | Purpose | Result type on `Stream<T>` | If Stream is empty |
|---|---|---|---|
| `findFirst()` | Finds the first element in encounter order if present | `Optional<T>` | `Optional.empty()` |
| `findAny()` | Finds any element | `Optional<T>` | `Optional.empty()` |
| `min(comparator)` | Finds the smallest element according to the comparator | `Optional<T>` | `Optional.empty()` |
| `max(comparator)` | Finds the largest element according to the comparator | `Optional<T>` | `Optional.empty()` |
| `reduce(accumulator)` | Combines elements using an associative operation | `Optional<T>` | `Optional.empty()` |

Two other overloads of `reduce` should be distinguished:

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
<U> U reduce(U identity,
             BiFunction<U, ? super T, U> accumulator,
             BinaryOperator<U> combiner)
~~~

They **have an initial `identity` value**, so they return a value directly rather than an Optional. For an empty Stream, the result is `identity`.

On primitive Streams, the corresponding methods return specialized types: for example, `IntStream.findFirst()`, `IntStream.min()`, and `IntStream.reduce(IntBinaryOperator)` return `OptionalInt`. A detailed table is in section 7.

## 3. Complete Example: Results That May Not Exist

Suppose a system has orders, each containing an ID, customer name, amount, and paid status. We need to find the first paid order, any paid order, the order with the smallest/largest value, and the total amount of paid orders.

The example runs with **JDK 17 or later** because it uses `record` and `List.of`:

~~~java
import java.util.Comparator;
import java.util.List;
import java.util.Optional;
import java.util.OptionalLong;

public class OptionalStreamResultsDemo {
    record Order(String id, String customer, long amountVnd, boolean paid) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
            new Order("DH01", "An",   120_000L, true),
            new Order("DH02", "Bình",  80_000L, false),
            new Order("DH03", "Chi",  250_000L, true),
            new Order("DH04", "Dũng", 250_000L, true)
        );

        // Each terminal operation requires a new Stream from the List source.
        Optional<Order> firstPaid = orders.stream()
            .filter(Order::paid)
            .findFirst();

        Optional<Order> anyPaid = orders.stream()
            .filter(Order::paid)
            .findAny();

        Comparator<Order> byAmount =
            Comparator.comparingLong(Order::amountVnd);

        Optional<Order> cheapestPaid = orders.stream()
            .filter(Order::paid)
            .min(byAmount);

        Optional<Order> mostExpensivePaid = orders.stream()
            .filter(Order::paid)
            .max(byAmount);

        OptionalLong totalPaid = orders.stream()
            .filter(Order::paid)
            .mapToLong(Order::amountVnd)
            .reduce(Long::sum);

        System.out.println(
            "First: " + firstPaid.map(Order::id).orElse("None")
        ); // First: DH01

        System.out.println("Has any order: " + anyPaid.isPresent());
        // Has any order: true; do not assume which order ID it is.

        System.out.println(
            "Lowest: " + cheapestPaid.map(Order::amountVnd).orElse(0L)
        ); // Lowest: 120000

        System.out.println(
            "Highest: " + mostExpensivePaid.map(Order::amountVnd).orElse(0L)
        ); // Highest: 250000

        System.out.println("Total: " + totalPaid.orElse(0L));
        // Total: 620000
    }
}
~~~

There are several important decisions in this example:

1. `findFirst()` takes order `DH01` because the source is a `List` with an encounter order and `DH01` is the first paid order.
2. `findAny()` only guarantees returning **one** matching order if available; do not write tests forcing it to always return `DH01`.
3. `min` finds the lowest amount; `max` finds the highest amount according to `Comparator.comparingLong`.
4. Both orders `DH03` and `DH04` have an amount of 250,000 VND. `max` may pick any representative among tied elements; if business logic requires determining the exact ID, an additional rule must be added to the comparator.
5. `mapToLong(...).reduce(Long::sum)` returns an `OptionalLong`. With the current list, it contains 620,000; when there are no paid orders, it is empty.

In the example, `orElse(0L)` is used when the **display convention** is "show 0 if there is no data". For real-world reports, "no orders", "unknown", and "actual value of 0" may carry different meanings. Choose a clear missing-data policy.

## 4. findFirst: Prioritizing the First Element by Encounter Order

`Stream.findFirst()` has the signature:

~~~java
Optional<T> findFirst()
~~~

This is a **short-circuiting** terminal operation: in many pipelines, it can stop immediately once the first element is determined. "First" is determined by **encounter order** if the source/pipeline is ordered.

~~~java
import java.util.List;
import java.util.Optional;

List<String> names = List.of("An", "Bình", "Chi");

Optional<String> firstLongName = names.stream()
    .filter(name -> name.length() >= 4)
    .findFirst();

System.out.println(firstLongName.orElse("Not found")); // Bình
~~~

Because `List` is ordered, `Bình` is the first element meeting the condition of length at least 4. When there is no matching element:

~~~java
Optional<String> missing = names.stream()
    .filter(name -> name.startsWith("Z"))
    .findFirst();

System.out.println(missing.isPresent()); // false
~~~

### 4.1. "First" Does Not Always Mean "Smallest"

For example, `List.of(9, 3, 5).stream().findFirst()` returns `9`, not `3`. If you want to find the smallest value, use `min` or an equivalent operation based on business criteria. Calling `sorted()` followed by `findFirst()` can retrieve the smallest element, but `min` usually expresses intent more clearly and avoids requiring a full sort of the data.

### 4.2. With Sources Without an Encounter Order

~~~java
Optional<Integer> chosen = java.util.Set.of(3, 1, 2)
    .stream()
    .findFirst();
~~~

Do not guess that `chosen` contains `1` just because it is the smallest value or because one run printed that. A `Set` without a guaranteed encounter order can cause `findFirst` to pick any element. Similarly, if `unordered()` is used on a Stream, the concept of the first element is no longer bound by the source order.

### 4.3. findFirst and Parallel Streams

`findFirst` must respect encounter order if the Stream is ordered, even when processed with `parallel()`. This can reduce performance because it needs to determine the first element in order, rather than taking the result of the branch that finishes earliest.

If the business logic only needs **any element**, `findAny` allows more flexible execution.

## 5. findAny: Finding Any Matching Element Without Guaranteeing a Representative

`Stream.findAny()` also returns `Optional<T>`:

~~~java
Optional<T> findAny()
~~~

Unlike `findFirst`, **the API does not guarantee** which element will be returned if there are multiple matching elements. On a sequential Stream, you often see it return the first element, but that is not a rule to rely on for business logic.

~~~java
import java.util.List;

List<String> cities = List.of("Hà Nội", "Đà Nẵng", "Huế");

boolean hasLongName = cities.parallelStream()
    .filter(name -> name.length() >= 5)
    .findAny()
    .isPresent();

System.out.println(hasLongName); // true
~~~

Here the question is **whether any matching element exists**. If you only need a `boolean` result, `anyMatch(...)` expresses this even more directly:

~~~java
boolean hasLongNameDirectly = cities.stream()
    .anyMatch(name -> name.length() >= 5);
~~~

Only choose `findAny` when you **need to use the found element itself**. Suitable cases include picking a sample element from a dataset, or retrieving any resource that meets a condition without order preference.

| Property | `findFirst` | `findAny` |
|---|---|---|
| Result | `Optional<T>` | `Optional<T>` |
| Can terminate early | Yes | Yes |
| Preserves encounter order on ordered sources | Yes | Not guaranteed |
| Flexible branch selection in parallel execution | Less flexible | More flexible |
| Use when | You want the **first representative** | You want **any representative** |

**Common condition:** when there is no element, both return `Optional.empty()`. If the selected element is `null`, the API may throw `NullPointerException`; section 9 explains how to handle this.

## 6. min and max: Comparator Defines the Smallest/Largest Value

Two terminal operations:

~~~java
Optional<T> min(Comparator<? super T> comparator)
Optional<T> max(Comparator<? super T> comparator)
~~~

`Comparator` defines the **comparison order**; `min` takes the lowest element, and `max` takes the highest element according to that rule.

### 6.1. Min/max with Integers and Strings

~~~java
import java.util.Comparator;
import java.util.List;

List<Integer> scores = List.of(8, 5, 10, 7);

int lowest = scores.stream()
    .min(Integer::compareTo)
    .orElseThrow(() -> new IllegalStateException("Empty list"));

int highest = scores.stream()
    .max(Comparator.naturalOrder())
    .orElseThrow(() -> new IllegalStateException("Empty list"));

System.out.println(lowest);  // 5
System.out.println(highest); // 10
~~~

For strings, `Comparator.naturalOrder()` relies on `String.compareTo`, which does **not automatically** correspond to natural language sorting or case-insensitive comparison.

### 6.2. Comparing Objects by Property

Suppose we need the highest-value order:

~~~java
Comparator<Order> byAmount =
    Comparator.comparingLong(Order::amountVnd);

Optional<Order> mostExpensive = orders.stream()
    .max(byAmount);
~~~

`Comparator.comparingLong` is well-suited for `long` properties, avoiding boxing just for comparison. This snippet uses the `Order` type and `orders` variable from the complete program in section 3.

**Tie-breaker:** if multiple orders have the same amount, comparing by `amountVnd` yields 0 between them. If business logic requires choosing the **order with the smallest ID** when amounts are equal, express it with a comparator and choose min/max consistently.

Example: "Get the order with the largest amount; if tied, pick the **smaller** ID":

~~~java
Comparator<Order> byAmountThenPreferredId =
    Comparator.comparingLong(Order::amountVnd)
        .thenComparing(Order::id, Comparator.reverseOrder());

Optional<Order> selected = orders.stream()
    .max(byAmountThenPreferredId);

// For the example in section 3, two orders with amount 250000 have IDs DH03 and DH04.
// max with the comparator above selects DH03.
System.out.println(selected.map(Order::id).orElse("None")); // DH03
~~~

Reason: `max` picks the value ranked **largest** by the comparator; for the order ID part, `reverseOrder()` causes lexicographically smaller IDs to rank larger in the secondary comparison. This approach applies only to the described requirement; there is no single default tie-breaker for all business domains.

### 6.3. min/max on an Empty Stream

~~~java
Optional<Integer> min = List.<Integer>of().stream()
    .min(Integer::compareTo);

System.out.println(min.isPresent()); // false
~~~

There is no smallest value when the set of elements is empty. That is why `min` and `max` return an Optional, rather than picking a default number that might be inappropriate.

In addition, **`min` and `max` usually have to examine all elements of a finite source** to determine the final result, unlike `findFirst` which can stop early. With an infinite source, an operation that needs to inspect the entire source may not terminate. If the comparator or data-generating function has side effects, do not rely on the number of comparator invocations to drive business logic.

### 6.4. Do Not Confuse min/max Order with equals

`min` and `max` operate according to the `Comparator`. Two objects can be considered equal by the comparator even if their `equals` implementations differ. For example, two orders with the same amount of 250,000 but different IDs are distinct objects; they still tie under `comparingLong(Order::amountVnd)`.

## 7. reduce: When an Aggregation May Have No Result

`reduce` combines multiple elements into a single result: computing a sum, product, accumulated value, or combining immutable structures. There are **two important forms** when considering empty results.

### 7.1. reduce Without Identity Returns Optional

~~~java
Optional<T> reduce(BinaryOperator<T> accumulator)
~~~

Example computing a sum:

~~~java
import java.util.List;
import java.util.Optional;

List<Integer> numbers = List.of(4, 6, 10);

Optional<Integer> total = numbers.stream()
    .reduce(Integer::sum);

System.out.println(total.orElse(0)); // 20
~~~

With three elements, the reduction `Integer::sum` produces `4 + 6 + 10 = 20`. With an empty Stream, there is no element to serve as an initial value, so:

~~~java
Optional<Integer> emptyTotal = List.<Integer>of()
    .stream()
    .reduce(Integer::sum);

System.out.println(emptyTotal.isPresent()); // false
~~~

Even though mathematics may define the sum of an empty set as 0, the **overload without identity** still returns an empty Optional. The application itself must decide whether to use 0 as the default value.

### 7.2. reduce With Identity Returns the Value Directly

~~~java
T reduce(T identity, BinaryOperator<T> accumulator)
~~~

Example:

~~~java
int total = numbers.stream()
    .reduce(0, Integer::sum);

int emptyTotal = List.<Integer>of()
    .stream()
    .reduce(0, Integer::sum);

System.out.println(total);      // 20
System.out.println(emptyTotal); // 0
~~~

`identity` is the identity element of the combining operation:

- For arithmetic addition, identity is **0**.
- For arithmetic multiplication, identity is **1**.
- For string concatenation, identity is typically **""**.

Choosing the wrong identity breaks even non-empty data. For example, `Stream.of(5, 8).reduce(0, Integer::min)` gives `0`, because 0 is smaller than both 5 and 8. Therefore, to find the minimum, you should normally use **`min(...)` returning Optional** or `reduce(Integer::min)` without identity, instead of defaulting to starting at 0.

### 7.3. The Combining Operation Must Guarantee Associativity

For `reduce` to work properly, especially when split for parallel processing, the accumulator must be **associative**:

`(a ◦ b) ◦ c = a ◦ (b ◦ c)`.

Integer addition is a familiar example within Java's integer arithmetic rules; **subtraction is not associative**:

~~~java
List<Integer> values = List.of(10, 3, 2);

// Do not use this style if you want a stable reduction in parallel.
int sequential = values.stream()
    .reduce((a, b) -> a - b)
    .orElse(0); // (10 - 3) - 2 = 5
~~~

If grouped and combined in a different order, subtraction can yield a different result. With `double`, addition also suffers from **rounding order** and floating-point arithmetic issues: parallel processing or changing the reduction order can produce slight differences. For monetary totals requiring exact precision, consider the smallest integer currency unit or `BigDecimal` according to business policy.

### 7.4. Primitive Streams Use Specialized Optionals

To avoid boxing, you can choose `IntStream` or `LongStream`:

~~~java
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

OptionalInt intTotal = IntStream.of(2, 3, 5)
    .reduce(Integer::sum);

OptionalLong longTotal = LongStream.of(1_000_000_000L, 2_000_000_000L)
    .reduce(Long::sum);

System.out.println(intTotal.orElse(0));   // 10
System.out.println(longTotal.orElse(0L)); // 3000000000
~~~

`IntStream.reduce(IntBinaryOperator)` returns `OptionalInt`; `LongStream.reduce(LongBinaryOperator)` returns `OptionalLong`; `DoubleStream.reduce(DoubleBinaryOperator)` returns `OptionalDouble`. If you use the overload with an identity, they return primitive `int`, `long`, or `double`.

For ordinary summation, `sum()` is more concise. However, `sum()` returns a primitive and has its own result rule for empty Streams (sum equals 0), whereas `reduce(operator)` returns an empty Optional. Choose the API based on the need to represent the "no data" state.

### 7.5. reduce Is Not Meant for Mutating a Shared Collection

Do not use `reduce` to repeatedly mutate a shared accumulating `ArrayList` or `HashMap`. The combining operation in a reduction should adhere to the associativity contract and avoid side effects. When you want to build a `List`, `Map`, or group data, use **`collect` and `Collector`**; when you want to aggregate multiple properties, you can use an appropriate collector or a custom collector with contract-compliant thread-safe combination.

## 8. Handling Optional Safely and According to Business Logic

Obtaining an `Optional<T>` is only the first half of the story. The important part is **deciding what to do when there is no value**.

### 8.1. orElse: Providing a Default Value

~~~java
Optional<String> first = List.<String>of().stream()
    .findFirst();

String label = first.orElse("Not found");

System.out.println(label); // Not found
~~~

`orElse(defaultValue)` is suitable when the default value is already available, cheap to create, and meaningful in the domain. Do not default to `null` or a number like 0 if doing so hides invalid input errors.

### 8.2. orElseGet: Computing the Default Only When Needed

`orElseGet(Supplier<? extends T>)` invokes the supplier **only when the Optional is empty**. In contrast, the expression passed to `orElse(...)` is evaluated by Java **immediately when the method is called**, even if the Optional has a value.

~~~java
import java.util.Optional;
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger calls = new AtomicInteger();
Optional<String> present = Optional.of("DH01");

String a = present.orElse("Code-" + calls.incrementAndGet());
System.out.println(calls.get()); // 1: the default expression was evaluated

String b = present.orElseGet(() -> "Code-" + calls.incrementAndGet());
System.out.println(calls.get()); // Still 1: supplier was not called

System.out.println(a + ", " + b); // DH01, DH01
~~~

The counter merely illustrates the evaluation mechanism. In real code, `orElseGet` is suitable for fetching fallback data or creating expensive objects. When the supplier performs I/O or has state, error handling and side-effect scope still need to be managed.

### 8.3. orElseThrow: Requiring a Value to Be Present

If not finding a value is a business error, express it directly:

~~~java
String required = List.of("A", "B").stream()
    .filter(value -> value.equals("B"))
    .findFirst()
    .orElseThrow(() -> new IllegalArgumentException("Missing value B"));

System.out.println(required); // B
~~~

The `orElseThrow(Supplier<? extends X>)` overload has existed since Java 8; the no-argument `orElseThrow()` appeared in Java 10. In Java 8, `get()` also exists, but when empty it throws `NoSuchElementException` with little context. In business code, `orElseThrow(() -> new ...("specific message"))` is usually easier to diagnose.

### 8.4. ifPresent and ifPresentOrElse: Branch-Based Handling

~~~java
import java.util.Optional;

Optional<String> result = Optional.of("DH01");

result.ifPresent(id -> System.out.println("Found: " + id));
// Found: DH01
~~~

`ifPresent(Consumer)` only runs when a value is present. If you need a branch for the empty case, Java 9+ supports `ifPresentOrElse(Consumer, Runnable)`:

~~~java
result.ifPresentOrElse(
    id -> System.out.println("Found: " + id),
    () -> System.out.println("Not found")
);
~~~

In Java 8, you can use `ifPresent` combined with other handling at the caller, or use `orElse`/`orElseGet` depending on the need to return a result.

### 8.5. map, filter, and flatMap on Optional

`Optional` also has declarative operations for working with **at most one value**:

~~~java
Optional<String> normalizedId = orders.stream()
    .filter(Order::paid)
    .findFirst()
    .map(Order::id)
    .map(String::trim)
    .filter(id -> !id.isEmpty());
~~~

This snippet uses `Order` and `orders` from section 3. Each `map` runs only when the Optional has a value. If the mapper returns `null`, `Optional.map` produces an empty Optional by contract, but you should avoid using `null` as a control signal when the result can be clearly defined.

`flatMap` is used when the mapper **already returns an Optional**, avoiding `Optional<Optional<T>>`:

~~~java
import java.util.Optional;

Optional<String> input = Optional.of("42");
Optional<Integer> parsed = input.flatMap(value -> {
    try {
        return Optional.of(Integer.parseInt(value));
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
});

System.out.println(parsed.orElse(-1)); // 42
~~~

Note that `Optional.flatMap` does not accept a mapper returning `null`: that case throws `NullPointerException`. Catching `NumberFormatException` here serves to illustrate optional parsing rules; in systems requiring error diagnostics, detailed errors should be reported rather than always turning parse failures into "absent".

### 8.6. Optional.stream to Rejoin a Stream (Java 9+)

If you have multiple Optionals and want to extract all present values:

~~~java
import java.util.List;
import java.util.Optional;

List<String> presentValues = List.of(
        Optional.of("A"),
        Optional.<String>empty(),
        Optional.of("B")
    ).stream()
    .flatMap(Optional::stream)
    .toList(); // [A, B]
~~~

`Optional.stream()` is available from Java 9, and `Stream.toList()` from Java 16. For Java 9–15, replace `toList()` with `collect(Collectors.toList())`. When using `Optional.stream()`, an empty Optional contributes **0 elements**, and a present Optional contributes **1 element**.

## 9. OptionalInt, OptionalLong, and OptionalDouble

Primitive Streams do not return `Optional<Integer>`, `Optional<Long>`, or `Optional<Double>` in single-value lookup operations. They return **specialized** types, avoiding boxing:

| Source | `findFirst` / `findAny` | `min` / `max` | `reduce(operator)` | `average` |
|---|---|---|---|---|
| `IntStream` | `OptionalInt` | `OptionalInt` | `OptionalInt` | `OptionalDouble` |
| `LongStream` | `OptionalLong` | `OptionalLong` | `OptionalLong` | `OptionalDouble` |
| `DoubleStream` | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` | `OptionalDouble` |

Example:

~~~java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt min = IntStream.of(4, 7, 2).min();
OptionalDouble average = IntStream.of(4, 7, 2).average();

System.out.println(min.orElse(-1));           // 2
System.out.println(average.orElse(Double.NaN)); // 4.333...
~~~

`OptionalInt` has `getAsInt()`, `orElse(int)`, `orElseGet(IntSupplier)`, `orElseThrow(...)`, and several methods for checking/consuming the value. Similarly, `OptionalLong` has `getAsLong()`, and `OptionalDouble` has `getAsDouble()`. These types **do not have the full set of `map`/`flatMap` transformation methods like `Optional<T>`**; do not write `optionalInt.map(...)` out of habit from object Optional.

If you need to convert to objects or continue with `Stream<T>`, consider creating a Stream from the primitive Optional via `stream()` (Java 9+) followed by `mapToObj`, or performing an explicit conversion when a value is present.

~~~java
int[] values = IntStream.of(8, 3, 6)
    .min()
    .stream() // IntStream of 0 or 1 element, Java 9+
    .toArray();

System.out.println(java.util.Arrays.toString(values)); // [3]
~~~

With an empty Optional, the primitive Optional's `stream()` also creates an empty Stream.

## 10. Optional and null: Distinguishing "Absent" from "Having null"

`Optional<T>` **cannot contain `null`**. The two ways of creating an Optional differ:

~~~java
Optional<String> absent = Optional.ofNullable(null);
System.out.println(absent.isPresent()); // false

// Optional.of(null); // Throws NullPointerException.
~~~

For Stream lookup operations, two situations must be separated:

1. **The Stream has no matching elements:** `findFirst`, `findAny`, `min`, `max`, and `reduce(accumulator)` return an empty Optional.
2. **The Stream has a `null` element selected as the result:** some operations like `findFirst`/`findAny` may throw `NullPointerException`, instead of returning an Optional containing null.

Example:

~~~java
import java.util.Arrays;
import java.util.Objects;

// This source contains a null element:
List<String> values = Arrays.asList(null, "Java");

// values.stream().findFirst(); // Throws NullPointerException.

String firstNonNull = values.stream()
    .filter(Objects::nonNull)
    .findFirst()
    .orElse("None");

System.out.println(firstNonNull); // Java
~~~

`List.of(null, "Java")` is not an equivalent way to create the source, because `List.of` itself rejects null. If business logic needs to preserve the special meaning of missing data, use a data model that explicitly represents the missing state rather than letting null flow implicitly through the pipeline.

With `reduce(accumulator)`, the accumulator **should not return null**; if the reduction result is null, some overloads may throw `NullPointerException`. Similarly, comparators and other operations do not necessarily handle null. Define rules for filtering, normalizing, or reporting data errors before aggregating.

## 11. Laziness, Resources, and Termination

`findFirst`, `findAny`, `min`, `max`, and `reduce` are terminal operations: they **trigger** the lazy pipeline. However, the amount of data they need to traverse is not the same:

~~~java
import java.util.stream.IntStream;

int firstMultipleOfSeven = IntStream.rangeClosed(1, 1_000_000)
    .filter(n -> n % 7 == 0)
    .findFirst()
    .orElse(-1);

System.out.println(firstMultipleOfSeven); // 7
~~~

Here `findFirst` can stop as soon as it finds 7, without checking all one million numbers. `findAny` can also terminate early.

Conversely, `min`, `max`, and `reduce` generally need to process **the entire finite source** to determine the result. With an infinite source, such as `IntStream.iterate(0, n -> n + 1).max()`, an operation requiring the final value may not finish. Do not expect laziness alone to turn an infinite source into a terminating computation.

### 11.1. Operation Order Changes the Result

~~~java
List<Integer> values = List.of(10, 2, 8, 4);

int firstOfFirstTwo = values.stream()
    .limit(2)
    .min(Integer::compareTo)
    .orElse(-1); // 2

int globalMinThenLimited = values.stream()
    .min(Integer::compareTo)
    .orElse(-1); // 2
~~~

The two values happen to be the same with this data; change the list to `List.of(10, 8, 2, 4)` and the first returns **8**, while the second returns **2**. The meaning of `limit(2).min(...)` is **the min of the first two elements**, whereas `min(...)` is **the min of the entire source**.

With `sorted()` and `findFirst()`, the `sorted` operation typically has to inspect the finite source before returning the first element; do not infer that `findFirst` always makes the pipeline terminate early at any position.

### 11.2. A Stream Can Only Be Consumed Once

~~~java
var stream = List.of(3, 6, 9).stream();
Optional<Integer> first = stream.findFirst();

// stream.max(Integer::compareTo); // Invalid: Stream has already been consumed.
~~~

You must create a **new Stream** from the `List` for each terminal operation. If the source is an I/O Stream such as `Files.lines(...)`, you also need to close the resource properly, for example using `try-with-resources`. Optional only represents **whether a result is present or not**; it **does not manage closing the Stream**.

### 11.3. Do Not Rely on Side Effects in Callbacks

Predicates, mappers, and accumulators in a pipeline should not interfere with the source and should not rely on mutable external state. Streams may terminate early, process in parallel, or skip steps unnecessary for the final result. Therefore, do not use those callbacks as places for mandatory logging, sending notifications, or updating critical data.

## 12. Common Mistakes and How to Fix Them

| Problematic pattern | Why it is dangerous | How to handle it |
|---|---|---|
| `stream.findFirst().get()` without checking | When empty, throws `NoSuchElementException` | Use `orElse`, `orElseGet`, or `orElseThrow` with a message |
| `findAny()` then asserting equality with the first element | `findAny` does not guarantee which representative is picked | If you need the first, use `findFirst` on an ordered source |
| `min(comparator)` with reversed comparator direction | Actual min may be the max of the intended criterion | Define and test the comparator rules |
| `reduce(0, Integer::min)` to find min | Identity 0 may be smaller than all values | Use `min` or `reduce(Integer::min)` |
| `orElse(expensiveCall())` | Calls the fallback function even when data is present | Use `orElseGet(() -> expensiveCall())` |
| `Optional.of(nullableValue)` | Throws an exception if `null` | Use `ofNullable` when absence is intentional |
| Calling `findFirst` on a source starting with null | Optional cannot hold null | Normalize/filter with `Objects::nonNull` |
| `reduce` with an accumulator using shared variables | Depends on state and can fail in parallel execution | Use an associative combining operation without mutating state |
| Calling another terminal operation on the same Stream | Stream has already been consumed | Create a new Stream from a reusable source |
| Using `orElse(0)` without considering business semantics | Can hide the difference between "absent" and "equal to 0" | Choose a missing-data policy and communicate it clearly |

Prefer Optional on **return values where a result may be absent**, rather than overusing Optional in every field, parameter, or collection. For business domains that need to know **why** an operation failed (validation error, invalid data, disconnected source), Optional does not carry error details; use an appropriate result type or exception.

## 13. Practice Exercise: Analyzing Test Scores

A course has assessment scores from a `List<Integer>`. Requirements:

1. Find the first score of 8 or above.
2. Find the lowest score and the highest score.
3. Compute the total score using `reduce` without an identity.
4. Handle an empty list with a clear policy.
5. Do not call `get()` without handling Optional.

**Reference solution (Java 8+):**

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;
import java.util.Optional;

public class ScoreOptionalPractice {
    public static void main(String[] args) {
        List<Integer> scores = Arrays.asList(6, 9, 7, 10, 8);

        Optional<Integer> firstHigh = scores.stream()
            .filter(score -> score >= 8)
            .findFirst();

        Optional<Integer> minimum = scores.stream()
            .min(Comparator.naturalOrder());

        Optional<Integer> maximum = scores.stream()
            .max(Comparator.naturalOrder());

        Optional<Integer> total = scores.stream()
            .reduce(Integer::sum);

        System.out.println("First high score: "
            + firstHigh.map(String::valueOf).orElse("None"));
        System.out.println("Lowest score: "
            + minimum.map(String::valueOf).orElse("None"));
        System.out.println("Highest score: "
            + maximum.map(String::valueOf).orElse("None"));
        System.out.println("Total score: "
            + total.map(String::valueOf).orElse("No scores yet"));
    }
}
~~~

Output:

~~~text
First high score: 9
Lowest score: 6
Highest score: 10
Total score: 40
~~~

If `scores` is replaced with an empty list, all four results will be `Optional.empty()` and the program prints messages according to each policy instead of throwing an error. If business rules specify "the sum of an empty list is 0", use `scores.stream().reduce(0, Integer::sum)` or `mapToInt(Integer::intValue).sum()` and clearly document that convention.

**Self-check questions:**

1. What does `findFirst()` return on an empty Stream? — **`Optional.empty()`**.
2. Does `findAny()` guarantee preserving the first element of a `List`? — **No**.
3. What does `min(Comparator.naturalOrder())` return on `List.of(9, 2, 5)`? — **An Optional containing 2**.
4. What does `Stream.of(5, 8).reduce(0, Integer::min)` return? — **0**, because the identity is unsuitable for min over positive numbers.
5. What does `Stream.<Integer>empty().reduce(Integer::sum)` return? — **An empty Optional**, not an Optional containing 0.
6. What type does `IntStream.of(2, 4).average()` return? — **`OptionalDouble`**.
7. Does `orElseGet` invoke the supplier when the Optional has a value? — **No**.
8. Does `findFirst` always traverse all the data? — **No**, it can terminate early; preceding operations may cause it to do more work.

## 14. Key Takeaways Before Learning Advanced Aggregations

**`findFirst`** gets the first element when an encounter order exists; **`findAny`** gets any element; **`min`/`max`** select an element according to a comparator; and **`reduce(accumulator)`** combines elements when no identity is provided. They return **Optional** because the result may not exist.

Think of Optional as a **contract that forces the caller to confront the empty case**: use `orElse` for simple defaults, `orElseGet` for defaults computed on demand, `orElseThrow` when a result is mandatory, or `ifPresent` and Optional transformations when you want to continue declarative processing. For primitive numbers, use the appropriate `OptionalInt`, `OptionalLong`, or `OptionalDouble`.

When designing a pipeline, check **empty semantics**, **element selection order and criteria**, **source termination**, **associativity in reduce**, and **side effects in callbacks**. Mastering these helps you transition to `collect`, grouping, custom collectors, `Spliterator`, parallel Streams, and Stream Gatherers while keeping results clear and testable.
