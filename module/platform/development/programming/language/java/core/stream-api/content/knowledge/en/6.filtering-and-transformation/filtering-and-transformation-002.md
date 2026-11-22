# Transforming Elements with `map` and Handling Multi-Step Mapping

## 1. The Role of `map` in a Java Stream Pipeline

In the **Java Stream API**, a pipeline typically consists of a data source, *intermediate operations*, and a *terminal operation*. In the **Filtering and Transforming Elements** chapter, `filter` decides which elements are kept, while `map` decides **how each element is represented as a new value**.

```text
Source Stream<T>
      |
      v
  filter(...)        Select elements to process
      |
      v
   map(T -> R)       Transform each element into a value of type R
      |
      v
  Stream<R>
      |
      v
  toList()/collect() Collect results
```

Example: take usernames, strip leading/trailing whitespace, normalize to lowercase, and create identifiers.

```java
import java.util.List;
import java.util.Locale;

List<String> names = List.of("  An  ", "  Bình ", " CHI  ");

List<String> usernames = names.stream()
        .map(String::strip)
        .map(name -> name.toLowerCase(Locale.ROOT))
        .map(name -> "user-" + name)
        .toList();

System.out.println(usernames);
// [user-an, user-bình, user-chi]
```

The three `map` calls sequentially normalize whitespace, normalize letter case, and add a prefix. That is **multi-step mapping**: the output of the previous step becomes the input of the next step, within the same pipeline.

**Learning outcomes after this lesson:**

- Understand the contract of `Stream.map`, laziness, and element type transformation.
- Know how to organize chains of multiple `map` calls for readability, reusability, and error control.
- Combine `filter`, `map`, `mapToInt`, and `collect` in practical data processing.
- Distinguish `map` from `flatMap`, and avoid side effects, `null` errors, and shared state.
- Choose a processing order suited to the data, correctness, and computational cost.

The main examples use **Java 17+** for `record`, `String.strip`, and `Stream.toList`. `Stream.map` has been available since Java 8.

## 2. The Contract of `Stream.map`

Method signature in `Stream<T>`:

```java
<R> Stream<R> map(Function<? super T, ? extends R> mapper)
```

Where:

| Component | Meaning |
| --- | --- |
| `T` | Element type of the input Stream. |
| `R` | Element type of the transformed Stream; may be the same as or different from `T`. |
| `mapper` | A function taking an element `T` and returning a value `R`. |
| `Stream<R>` | A new Stream describing the transformation; not yet a `List<R>`. |

`map` is an **intermediate operation, stateless by usage contract, and lazily executed**. When the mapper is actually invoked for an element, it returns **one** output value for that element. `map` itself does not drop elements conditionally and does not flatten nested collections.

Example from `String` to `Integer`:

```java
List<String> words = List.of("Java", "Stream", "API");

List<Integer> lengths = words.stream()
        .map(String::length)
        .toList();

System.out.println(lengths); // [4, 6, 3]
```

After `map(String::length)`, the logical type is `Stream<Integer>`. From here on, downstream operations work with lengths rather than directly receiving the original strings.

Note: `map` in `Stream.map(...)` is the **name of the mapping operation**; it is different from the `java.util.Map<K, V>` data structure. The two share the same name but serve distinct roles.

## 3. Single-Step and Multi-Step Mapping

A mapper can be expressed as a lambda or a method reference:

```java
List<String> products = List.of("sách", "bút", "vở");

List<String> upper = products.stream()
        .map(value -> value.toUpperCase(Locale.ROOT))
        .toList();

// Equivalent when calling parameterless toUpperCase():
List<String> upperDefault = products.stream()
        .map(String::toUpperCase)
        .toList();
```

In the next example, data passes through **three transformation stages**, each with a specific responsibility:

```java
List<String> rawCodes = List.of("  SP 01 ", "Sp 02", "  sp 03 ");

List<String> normalizedCodes = rawCodes.stream()
        .map(String::strip)                                // Step 1: strip leading/trailing whitespace
        .map(code -> code.toUpperCase(Locale.ROOT))        // Step 2: uppercase
        .map(code -> code.replace(" ", "-"))                // Step 3: replace spaces
        .toList();

System.out.println(normalizedCodes); // [SP-01, SP-02, SP-03]
```

Splitting into multiple `map` calls has three benefits: reading the pipeline by meaning, easily changing individual rules, and reusing normalization functions.

### Is One Combined Mapper Acceptable?

You can write:

```java
List<String> normalizedCodes = rawCodes.stream()
        .map(code -> code.strip()
                .toUpperCase(Locale.ROOT)
                .replace(" ", "-"))
        .toList();
```

Both approaches yield the same result on this data. Use multiple `map` calls when steps have independent meaning or when you want to interleave `filter` to discard data before an expensive step; combine them if the transformation is short and easy to understand.

**Each `map` does not create an intermediate list.** A typical sequential pipeline fuses the steps and passes each element through them while the terminal operation executes. The result list is only created at `toList()`. Stateful operations like `sorted` may require their own buffer.

## 4. Transforming Types Across Multiple Stages

Multi-step mapping is not limited to `String -> String`. In real applications, data can transition through different types:

```text
Stream<String>          Stream<Integer>        Stream<String>
 ["12", "7", "30"] --map(Integer::parseInt)--> [12, 7, 30]
                              --map(n -> "Điểm: " + n)--> ["Điểm: 12", ...]
```

Corresponding Java code:

```java
List<String> scoreTexts = List.of("12", "7", "30");

List<String> labels = scoreTexts.stream()
        .map(Integer::parseInt)             // Stream<Integer>
        .map(score -> score * 2)            // Stream<Integer>
        .map(score -> "Điểm: " + score)      // Stream<String>
        .toList();

System.out.println(labels); // [Điểm: 24, Điểm: 14, Điểm: 60]
```

The type after each step is inferred from the corresponding `Function`. The compiler verifies that the next step can accept the value returned by the previous step.

If you need multiple properties from an object, map directly to an explicit target data type. For example:

```java
record Customer(String id, String fullName, int age) {}
record CustomerLabel(String id, String displayName) {}

List<Customer> customers = List.of(
        new Customer("C01", "  An ", 21),
        new Customer("C02", " Bình  ", 16),
        new Customer("C03", "Chi", 28)
);

List<CustomerLabel> adultLabels = customers.stream()
        .filter(customer -> customer.age() >= 18)
        .map(customer -> new CustomerLabel(
                customer.id(),
                customer.fullName().strip().toUpperCase(Locale.ROOT)
        ))
        .toList();

System.out.println(adultLabels);
// [CustomerLabel[id=C01, displayName=AN], CustomerLabel[id=C03, displayName=CHI]]
```

Here `filter` excludes customers under 18; `map` turns a domain object into a DTO containing only the information needed for display. The source object is not mutated.

## 5. Extracting Complex Steps into Dedicated Functions

With long mapping chains, nested lambdas are hard to test. You can create *pure functions* with names reflecting their responsibilities:

```java
static String trimAndUppercase(String value) {
    return value.strip().toUpperCase(Locale.ROOT);
}

static String toSlug(String value) {
    return value.toLowerCase(Locale.ROOT).replace(" ", "-");
}

// Inside another method of the same class:
List<String> slugs = List.of("  Java Stream ", "Lambda API ")
        .stream()
        .map(MyClass::trimAndUppercase)
        .map(MyClass::toSlug)
        .toList();

// [java-stream, lambda-api]
```

In the illustration, `MyClass` is the name of the class containing the two `static` methods and the statement creating `slugs`. When used in a project, replace it with the actual class name; if the methods are in the same class, you can use `MyClass::trimAndUppercase` or an appropriate method reference form.

Standalone functions allow testing each normalization rule before chaining them. For logic with multiple branches, using clear function names is usually easier to maintain than a long lambda.

Do not mechanically split every tiny expression. A standalone `map(String::strip)` is already clear enough; extra methods only complicate code if they add no further meaning.

## 6. Combining `filter` and `map` in the Right Order

`filter` retains elements according to `Predicate<T>`, while `map` transforms them into `R`. The order of the two operations affects both **semantics** and **cost**.

Example where only paid orders need processing:

```java
record Order(String id, int quantity, boolean paid) {}

List<Order> orders = List.of(
        new Order("O01", 2, true),
        new Order("O02", 5, false),
        new Order("O03", 3, true)
);

List<String> paidLabels = orders.stream()
        .filter(Order::paid)                         // Select first
        .map(order -> order.id() + ": " + order.quantity())
        .toList();

System.out.println(paidLabels); // [O01: 2, O03: 3]
```

If creating labels is expensive and unpaid orders do not need processing, filtering first avoids unnecessary transformations.

Conversely, when the filter condition only makes sense **after** normalization, `map` must come first:

```java
List<String> values = List.of("  ", " An ", "  Bình  ");

List<String> nonEmptyNames = values.stream()
        .map(String::strip)
        .filter(name -> !name.isEmpty())
        .toList();

System.out.println(nonEmptyNames); // [An, Bình]
```

| Pipeline | When to use | Things to note |
| --- | --- | --- |
| `filter(...).map(...)` | The condition can be determined from the original element. | Usually reduces the number of transformations. |
| `map(...).filter(...)` | The condition requires the normalized/transformed value. | Every element goes through the mapping step first. |
| `map(...).filter(...).map(...)` | Need to normalize, drop invalid ones, then build the output type. | Each step has a distinct purpose. |

Do not automatically swap `filter` and `map`. The two orders can produce different results; base your choice on the data types and business conditions.

## 7. From Object Types to Primitive Streams

`map(String::length)` returns `Stream<Integer>`, i.e., boxed integers. When the goal is computing sums, averages, or numeric statistics, using `mapToInt`, `mapToLong`, or `mapToDouble` is usually more suitable.

```java
List<String> words = List.of("Java", "Stream", "API");

int totalLetters = words.stream()
        .mapToInt(String::length)
        .sum(); // 4 + 6 + 3 = 13

double averageLength = words.stream()
        .mapToInt(String::length)
        .average()
        .orElse(0.0);

System.out.println(totalLetters);   // 13
System.out.println(averageLength); // 4.333333333333333
```

Here the pipeline after `mapToInt` has type `IntStream`. It has specialized operations such as `sum`, `average`, `summaryStatistics`, and `max`.

You can further convert the data type:

```java
List<String> labels = words.stream()
        .mapToInt(String::length)       // IntStream
        .map(length -> length * 2)      // IntStream
        .mapToObj(length -> "x2=" + length)  // Stream<String>
        .toList();

System.out.println(labels); // [x2=8, x2=12, x2=6]
```

If you want to return to `Stream<Integer>`, use `boxed()`:

```java
List<Integer> lengths = words.stream()
        .mapToInt(String::length)
        .boxed()
        .toList();
```

`mapToLong` and `mapToDouble` also support the corresponding primitive types. They avoid boxing during numeric calculations but do not replace overflow checks or choosing an appropriate numeric type for the business domain.

## 8. How Does `map` Differ from `flatMap`?

If each input element contains **a sublist**, using `map` produces a Stream of lists:

```java
List<List<String>> teams = List.of(
        List.of("An", "Bình"),
        List.of("Chi"),
        List.of("Dũng", "Hà")
);

List<List<String>> namesByTeam = teams.stream()
        .map(team -> team.stream().map(String::toUpperCase).toList())
        .toList();

// [[AN, BÌNH], [CHI], [DŨNG, HÀ]]
```

When you need **a flat sequence of names**, use `flatMap`:

```java
List<String> allNames = teams.stream()
        .flatMap(List::stream)
        .map(String::toUpperCase)
        .toList();

System.out.println(allNames); // [AN, BÌNH, CHI, DŨNG, HÀ]
```

| Operation | Transformation | Typical result |
| --- | --- | --- |
| `map(f)` | Each element is mapped to **one value** (which may be a collection or Stream). | `Stream<List<String>>` if `f` produces `List<String>`. |
| `flatMap(f)` | Each element is mapped to a sub-Stream, then the sub-Streams are flattened. | `Stream<String>` from multiple lists of names. |

If you only need to normalize one value into another value, `map` is enough. When one input can produce **0, 1, or more elements** and you need a flat output, consider `flatMap` or `mapMulti` (Java 16+). There is no need to use `flatMap` for simple one-to-one transformations.

## 9. `null` Values, Conversion Errors, and `Optional`

### 9.1. `map` Does Not Automatically Remove `null`

`Stream.map` **can return `null`** and continue carrying `null` elements through the pipeline. This differs from `Optional.map`, where a `null` mapping result becomes `Optional.empty()`.

```java
import java.util.Arrays;
import java.util.Objects;

List<String> raw = Arrays.asList(" An ", null, " Chi ");

List<String> clean = raw.stream()
        .filter(Objects::nonNull)
        .map(String::strip)
        .map(String::toUpperCase)
        .toList();

System.out.println(clean); // [AN, CHI]
```

If `filter(Objects::nonNull)` is omitted, `String::strip` will throw `NullPointerException` when encountering the `null` element. The `List.of(...)` factories do not accept `null` elements, so the example intentionally uses `Arrays.asList`.

When a `map` step can produce `null`, you still need to decide what the next step should do:

```java
List<String> mapped = List.of("A", "X", "B").stream()
        .map(code -> code.equals("X") ? null : code.toLowerCase(Locale.ROOT))
        .filter(Objects::nonNull)
        .toList();

System.out.println(mapped); // [a, b]
```

In business code, consider modeling results explicitly with `Optional` or an object representing error state to avoid silently producing `null`.

### 9.2. Parse Errors Stop the Pipeline

`Integer.parseInt` throws `NumberFormatException` if the string is invalid:

```java
List<String> amounts = List.of("10", "oops", "25");

// Will fail at element "oops" when the terminal operation executes.
List<Integer> parsed = amounts.stream()
        .map(Integer::parseInt)
        .toList();
```

For the requirement to **skip unconvertible inputs**, you can write a helper method:

```java
static Optional<Integer> tryParseInt(String raw) {
    try {
        return Optional.of(Integer.parseInt(raw));
    } catch (NumberFormatException exception) {
        return Optional.empty();
    }
}

// Example in the same class:
List<Integer> parsed = List.of("10", "oops", "25").stream()
        .map(MyClass::tryParseInt)        // Stream<Optional<Integer>>
        .flatMap(Optional::stream)        // Keep only non-empty Optionals
        .toList();

System.out.println(parsed); // [10, 25]
```

`MyClass` is the name of the class containing `tryParseInt`. `Optional::stream` has been available since Java 9. When invalid data is an issue that needs reporting, do not just skip it: collect errors into a separate result structure for tracing and notification.

## 10. Laziness and Mapper Side Effects

`map` does not run immediately when declared:

```java
Stream<String> pipeline = List.of("a", "b", "c").stream()
        .map(value -> {
            System.out.println("map: " + value);
            return value.toUpperCase(Locale.ROOT);
        });

// Up to here there is no terminal operation, so mapping has not executed yet.
List<String> result = pipeline.toList();
// Only now are elements processed, yielding [A, B, C].
```

Do not place important data updates inside a mapper. A Stream may terminate early via `findFirst`, `anyMatch`, `limit`, or skip some intermediate operations when the result can be determined without computing every element. For example, with a `SIZED` source and `count()`, an unnecessary `map` may not be invoked.

```java
long count = List.of("a", "b", "c").stream()
        .map(value -> {
            System.out.println("Có thể không in: " + value);
            return value.toUpperCase(Locale.ROOT);
        })
        .count();

System.out.println(count); // 3
```

If you need to transform data, **return a new value** instead of mutating the source collection:

```java
List<StringBuilder> builders = List.of(
        new StringBuilder("A"),
        new StringBuilder("B")
);

// Not recommended: mapper mutates the state of source objects.
List<StringBuilder> changed = builders.stream()
        .map(builder -> builder.append("-done"))
        .toList();

// Recommended: create output Strings without mutating original StringBuilders.
List<String> safe = builders.stream()
        .map(builder -> builder.toString() + "-done")
        .toList();
```

The `changed` snippet is a **counter-example illustration**; do not run it before `safe` if you want to preserve original values. Mappers with side effects cause unpredictable behavior under parallel execution, data reuse, or step composition.

### Parallel Mapping

`parallelStream()` allows the framework to process elements across multiple threads:

```java
List<Integer> squares = List.of(1, 2, 3, 4).parallelStream()
        .map(n -> n * n)
        .toList();

System.out.println(squares); // [1, 4, 9, 16]
```

With a source that has an *encounter order* such as `List`, `toList` preserves that order even when the mapper runs in parallel. **The order in which the mapper is called across threads is not guaranteed.** Do not use shared counters, a shared `ArrayList` inside the mapper, or logic depending on which element finishes first. Transformations should be stateless, non-interfering with the source, and independent of execution order.

For small pipelines and cheap mappers, the added threading overhead can make `parallelStream` slower. Evaluate based on actual workload and transformation cost.

## 11. Mapping Before `collect` or Grouping

`map` is often used to prepare data before `collect`:

```java
List<String> products = List.of("  Bút ", " Sách", " Vở  ");

Set<String> normalized = products.stream()
        .map(String::strip)
        .map(name -> name.toUpperCase(Locale.ROOT))
        .collect(Collectors.toCollection(LinkedHashSet::new));

System.out.println(normalized); // [BÚT, SÁCH, VỞ]
```

When grouping requires keeping the original object for keys while transforming values **within each group**, `Collectors.mapping` is also useful:

```java
record Student(String group, String name) {}

List<Student> students = List.of(
        new Student("A", " An "),
        new Student("B", " Chi "),
        new Student("A", " Bình ")
);

Map<String, List<String>> namesByGroup = students.stream()
        .collect(Collectors.groupingBy(
                Student::group,
                Collectors.mapping(
                        student -> student.name().strip(),
                        Collectors.toList()
                )
        ));

// A -> [An, Bình]; B -> [Chi]. Map key order is not guaranteed.
```

`Stream.map` transforms all elements of the stream **before** the terminal operation; `Collectors.mapping` is a downstream collector that transforms elements **during collection** by another collector, commonly used with `groupingBy` or `partitioningBy`.

If you need a multi-step pipeline with conditional branches, prioritize clearly expressing business intent. Operations such as `sorted`, `distinct`, or `collect` have different state, ordering, and memory requirements than `map`.

## 12. Complete Example: Normalizing and Presenting Orders

A system receives raw orders: order ID, customer name, amount as a string, and payment status. The task is to keep only paid orders, normalize the information, create display objects, and sum totals by customer.

The example compiles and runs with Java 17+:

```java
import java.math.BigDecimal;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.stream.Collectors;

public class MultiStepMappingDemo {
    record RawOrder(String id, String customer, String amountText, boolean paid) {}
    record CleanOrder(String id, String customer, BigDecimal amount) {}
    record OrderView(String id, String customer, BigDecimal amount) {}

    public static void main(String[] args) {
        List<RawOrder> rawOrders = List.of(
                new RawOrder("O-01", " An ", "120000", true),
                new RawOrder("O-02", "Bình", "50000", false),
                new RawOrder("O-03", " Chi ", "80000", true),
                new RawOrder("O-04", " an ", "30000", true)
        );

        List<OrderView> paidOrders = rawOrders.stream()
                .filter(RawOrder::paid)
                .map(raw -> new CleanOrder(
                        raw.id().strip(),
                        raw.customer().strip().toUpperCase(Locale.ROOT),
                        new BigDecimal(raw.amountText().strip())
                ))
                .filter(clean -> clean.amount().signum() > 0)
                .map(clean -> new OrderView(
                        clean.id(),
                        clean.customer(),
                        clean.amount()
                ))
                .toList();

        Map<String, BigDecimal> totalsByCustomer = paidOrders.stream()
                .collect(Collectors.toMap(
                        OrderView::customer,
                        OrderView::amount,
                        BigDecimal::add,
                        LinkedHashMap::new
                ));

        System.out.println(paidOrders);
        // [OrderView[id=O-01, customer=AN, amount=120000],
        //  OrderView[id=O-03, customer=CHI, amount=80000],
        //  OrderView[id=O-04, customer=AN, amount=30000]]

        System.out.println(totalsByCustomer);
        // {AN=150000, CHI=80000}
    }
}
```

In this pipeline:

1. `filter(RawOrder::paid)` drops unpaid orders before conversion.
2. `map(RawOrder -> CleanOrder)` normalizes strings and converts the amount to `BigDecimal`.
3. `filter(CleanOrder)` checks for positive amounts on the already-parsed data.
4. `map(CleanOrder -> OrderView)` creates the display form with the required fields.
5. `toList()` is the terminal operation; `Collectors.toMap` on the new list sums amounts for customers with matching normalized names using `BigDecimal::add`.

The example assumes valid inputs and no `null` fields. In real applications, validate fields and handle parse errors before constructing `BigDecimal`; choose a policy to merge customers by a durable identifier (such as customer ID) if names are insufficient to distinguish customers.

## 13. Common Mistakes

| Symptom | Cause | How to address |
| --- | --- | --- |
| Type after `map` does not fit the next step | Not tracking `Stream<T> -> Stream<R>` | Determine the type after each mapping step. |
| `map` yields `Stream<List<T>>` instead of a flat list of elements | Need to expand multiple elements from each input | Consider `flatMap`. |
| `NullPointerException` in a method reference | Source has `null` or a previous step produces `null` | Filter/check `null` and define missing-data rules. |
| `NumberFormatException` from parsing | Malformed input | Validate, separate success/failure results, or use `Optional` intentionally. |
| Source data is mutated after the pipeline | Mapper modifies objects/collections being traversed | Create independent result objects; do not write back to the source. |
| Log count inside mapper is not as expected | Lazy pipeline, early termination, or step elision optimization | Do not rely on mappers for mandatory side effects. |
| Wrong order or wrong totals in parallel runs | Mapper relies on external state or shared counters | Write stateless mapping functions; use appropriate collectors. |
| Pipeline is hard to read | Too many nested expressions, mixed rules | Name steps and extract meaningful transformation functions. |

## 14. Exercise and Reference Solution

Given a list of raw data:

```java
List<String> prices = List.of(" 100 ", " 250 ", " 75 ", " 300 ");
```

**Requirement:** Normalize whitespace, convert to integers, keep only values from 100 upward, apply an illustrative 10% tax increase, and create labels `"Giá sau thuế: ..."`. Assume all strings contain valid integers.

Solution:

```java
List<String> labels = prices.stream()
        .map(String::strip)                       // Stream<String>
        .map(Integer::parseInt)                   // Stream<Integer>
        .filter(price -> price >= 100)            // Keep 100, 250, 300
        .map(price -> price * 110 / 100)          // Illustrative integer calculation
        .map(price -> "Giá sau thuế: " + price)    // Stream<String>
        .toList();

System.out.println(labels);
// [Giá sau thuế: 110, Giá sau thuế: 275, Giá sau thuế: 330]
```

**Extension:** If `prices` contains `"không rõ"`, what happens at `Integer::parseInt`? Use `Optional<Integer>` and `flatMap(Optional::stream)` as in Section 9 to handle invalid data according to an appropriate policy.

Note that `price * 110 / 100` is only to illustrate multi-step integer transformation: it can overflow and truncates downward. For real monetary amounts, use `BigDecimal` and the rounding rules defined by the business domain.

## Key Takeaways

`map` transforms each element of a Stream into a new value, optionally changing its data type. Chaining multiple `map` calls clearly describes each stage of normalization, parsing, and output object creation; `filter` is placed where the condition makes sense before or after the corresponding mapping step. Pipelines remain lazy and do not create a list at each `map`. When one element must produce multiple flattened elements, use `flatMap`; when processing numbers, consider `mapToInt` and primitive streams. Keep mappers stateless, avoid mutating the source, handle `null`/conversion errors explicitly, and only use parallelism when there is a verified benefit.
