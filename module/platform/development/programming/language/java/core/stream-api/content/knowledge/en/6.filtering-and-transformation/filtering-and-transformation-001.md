# Filtering Data with `filter` and Combined Conditions

> **Chapter:** Filtering and Transforming Elements  
> **Module:** `JAVA_STREAM_API` — declarative data processing with the Java Stream API via lazy pipelines, `filter`, `map`, `reduce`, `collect`; extending to grouping, custom collectors, `Spliterator`, parallel processing, and Stream Gatherers, with attention to state, resources, and performance.

`filter` is one of the most frequently used operations in the Stream API. Instead of iterating through a list with a loop and manually adding qualifying elements to another list, we directly describe the **condition for an element to be retained**. In practice, conditions are often not just "price greater than 100" but also combine status, dates, access permissions, keywords, or search options.

After this lesson, you will be able to write `filter` for a single condition, combine multiple conditions using logical operators or `Predicate`, organize complex conditions in a testable way, and avoid errors related to `null`, processing order, and shared state.

## 1. How Does `filter` Work?

The method signature on `Stream<T>`:

```java
Stream<T> filter(Predicate<? super T> predicate)
```

- `Predicate<T>` is a functional interface with the method `boolean test(T value)`.
- When `predicate` returns `true`, the element is **retained**; when it returns `false`, it is **discarded**.
- `filter` is an **intermediate operation**: it returns a Stream so further steps can be chained, and does not itself collect data into a `List`.
- `filter` is a **stateless** and **lazy** operation: each element can be tested independently, and processing typically only begins when a terminal operation is present.
- For sources with an encounter order such as `List`, `filter` preserves the relative order of the remaining elements.

```java
import java.util.List;

List<Integer> numbers = List.of(9, 2, 7, 4, 8);

List<Integer> evenNumbers = numbers.stream()
        .filter(n -> n % 2 == 0)
        .toList();

System.out.println(evenNumbers);  // [2, 4, 8]
System.out.println(numbers);      // [9, 2, 7, 4, 8]
```

In the example, `n -> n % 2 == 0` is a `Predicate<Integer>` expressed as a lambda. `filter` produces the result stream without modifying the `numbers` list; `toList()` (Java 16+) is a terminal operation that creates a list that does not allow modification through methods such as `add` or `remove`.

Logical diagram:

```text
Source List      filter(n -> n % 2 == 0)     toList()
   9          ────────── false ──────×
   2          ────────── true  ───────────→  2
   7          ────────── false ──────×
   4          ────────── true  ───────────→  4
   8          ────────── true  ───────────→  8
                                           [2, 4, 8]
```

## 2. Combining Conditions with `&&`, `||`, and `!`

A `filter` lambda can contain a boolean expression with multiple criteria.

| Operator | Meaning | Example | When is the expression `true`? |
| --- | --- | --- | --- |
| `&&` | AND | `n > 0 && n < 10` | Both conditions are true. |
| `||` | OR | `n < 0 || n > 100` | At least one condition is true. |
| `!` | NOT | `!(n == 0)` | The inner condition is false. |

Example filtering positive, even integers less than 10:

```java
List<Integer> result = List.of(-4, 0, 2, 3, 8, 10, 12).stream()
        .filter(n -> n > 0 && n % 2 == 0 && n < 10)
        .toList();

// [2, 8]
```

Example filtering numbers **outside** the range `[10, 20]`:

```java
List<Integer> outside = List.of(5, 10, 15, 20, 25).stream()
        .filter(n -> n < 10 || n > 20)
        .toList();

// [5, 25]
```

### Using Parentheses to Express Business Rules Accurately

Java evaluates `!` before `&&`, and then `||`. Therefore, the following two expressions are **different**:

```java
// Means: (paid AND high value) OR VIP customer.
paid && highValue || vip

// Means: paid AND (high value OR VIP customer).
paid && (highValue || vip)
```

If the policy requires **all orders to be paid**, the first expression is wrong: an unpaid order from a VIP customer would still be kept. When combining both AND and OR, always write parentheses around business condition groups even if you already remember operator precedence.

### Short-Circuiting of Logical Expressions

`&&` and `||` perform *short-circuit evaluation* **per element**:

- In `a && b`, when `a` is `false`, Java does not need to evaluate `b`.
- In `a || b`, when `a` is `true`, Java does not need to evaluate `b`.

For example, `text != null && !text.isBlank()` is safe if `text` is `null` because Java will not call `text.isBlank()` when the left-hand side is false. Avoid replacing `&&` with `&` or `||` with `|` when the goal is boolean short-circuiting: `&` and `|` always evaluate both sides.

This is short-circuiting of a **conditional expression**. It differs from the early-termination capability of an **entire pipeline** when using `limit`, `findFirst`, `anyMatch`, and appropriate terminal operations.

## 3. Real-World Example: Finding Orders Matching Multiple Policies

Suppose we need to select orders according to these rules:

1. Status is `PAID`.
2. Total amount is at least 100.
3. Created date is from **01/10/2026** onward (inclusive).
4. Must also be a priority order **or** have a total amount of at least 200.

The Java 17+ program below runs standalone and can be copied into `FilterOrdersDemo.java`:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.List;

public class FilterOrdersDemo {
    record Order(
            String id,
            String customer,
            String status,
            BigDecimal total,
            LocalDate createdAt,
            boolean priority
    ) {}

    public static void main(String[] args) {
        List<Order> orders = List.of(
                new Order("DH-01", "An", "PAID",
                        new BigDecimal("120.00"), LocalDate.of(2026, 10, 5), true),
                new Order("DH-02", "Binh", "PENDING",
                        new BigDecimal("500.00"), LocalDate.of(2026, 10, 6), true),
                new Order("DH-03", "Chi", "PAID",
                        new BigDecimal("80.00"), LocalDate.of(2026, 10, 6), true),
                new Order("DH-04", "Dung", "PAID",
                        new BigDecimal("250.00"), LocalDate.of(2026, 10, 2), false),
                new Order("DH-05", "Em", "PAID",
                        new BigDecimal("160.00"), LocalDate.of(2026, 9, 30), true),
                new Order("DH-06", "Giang", "PAID",
                        new BigDecimal("180.00"), LocalDate.of(2026, 10, 7), true)
        );

        BigDecimal minimum = new BigDecimal("100.00");
        BigDecimal largeOrder = new BigDecimal("200.00");
        LocalDate startDate = LocalDate.of(2026, 10, 1);

        List<String> selectedIds = orders.stream()
                .filter(o -> "PAID".equals(o.status())
                        && o.total().compareTo(minimum) >= 0
                        && !o.createdAt().isBefore(startDate)
                        && (o.priority()
                            || o.total().compareTo(largeOrder) >= 0))
                .map(Order::id)
                .toList();

        System.out.println(selectedIds);
    }
}
```

Expected output:

```text
[DH-01, DH-04, DH-06]
```

| Order | Status | Total | Created Date | Priority | Result |
| --- | --- | ---: | --- | --- | --- |
| DH-01 | PAID | 120 | 05/10/2026 | Yes | Keep: priority, sufficient total, and valid date. |
| DH-02 | PENDING | 500 | 06/10/2026 | Yes | Discard: not paid. |
| DH-03 | PAID | 80 | 06/10/2026 | Yes | Discard: under 100. |
| DH-04 | PAID | 250 | 02/10/2026 | No | Keep: total at least 200. |
| DH-05 | PAID | 160 | 30/09/2026 | Yes | Discard: before start date. |
| DH-06 | PAID | 180 | 07/10/2026 | Yes | Keep: priority order. |

Note three details in the example:

- Use `"PAID".equals(o.status())` to compare **string content**, avoiding `==` (reference comparison) and avoiding an error if `status` is `null`.
- Using `BigDecimal.compareTo(...) >= 0` compares monetary amounts by value; `BigDecimal.equals(...)` also considers `scale`, so it is not suitable for threshold checks.
- Use `!createdAt.isBefore(startDate)` to include `startDate` itself. Ensure `createdAt` is non-`null` before calling methods on it.

## 4. Extracting Conditions into Reusable `Predicate` Instances

When conditions are long or appear in multiple places, `java.util.function.Predicate<T>` helps name individual rules and combine them clearly:

```java
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.function.Predicate;

BigDecimal minimum = new BigDecimal("100.00");
BigDecimal largeOrder = new BigDecimal("200.00");
LocalDate startDate = LocalDate.of(2026, 10, 1);

Predicate<Order> paid = o -> "PAID".equals(o.status());
Predicate<Order> atLeast100 = o -> o.total().compareTo(minimum) >= 0;
Predicate<Order> fromStartDate = o -> !o.createdAt().isBefore(startDate);
Predicate<Order> priority = Order::priority;
Predicate<Order> atLeast200 = o -> o.total().compareTo(largeOrder) >= 0;

Predicate<Order> eligible = paid
        .and(atLeast100)
        .and(fromStartDate)
        .and(priority.or(atLeast200));

List<String> ids = orders.stream()
        .filter(eligible)
        .map(Order::id)
        .toList();

// [DH-01, DH-04, DH-06]
```

The snippet above uses `record Order` and the `orders` variable declared in the complete example in Section 3. `Predicate` provides three important methods:

| Method | Meaning | Equivalent when testing an element `x` |
| --- | --- | --- |
| `p.and(q)` | Combines two conditions with AND | `p.test(x) && q.test(x)` |
| `p.or(q)` | Combines two conditions with OR | `p.test(x) || q.test(x)` |
| `p.negate()` | Inverts the condition result | `!p.test(x)` |

Like `&&` and `||`, the `and` and `or` methods are defined to evaluate the second condition **only when necessary**. `Predicate` also supports method references, such as `Order::priority`, when the method returns `boolean`.

**A common condition-combining mistake:**

```java
// Wrong if the policy requires all orders to be paid:
Predicate<Order> incorrect = paid.and(atLeast100).or(priority);

// Correct: the OR group must be nested inside the AND condition:
Predicate<Order> correct = paid.and(atLeast100).and(priority.or(atLeast200));
```

The `incorrect` expression accepts `PENDING` orders if `priority` is true. When chaining `.and(...).or(...)`, always verify that the grouping matches the parentheses in the logical expression; if needed, name each `Predicate` group before combining.

### Negation with `negate` and `Predicate.not`

```java
Predicate<Order> cancelled = o -> "CANCELLED".equals(o.status());
Predicate<Order> notCancelled = cancelled.negate();

List<Order> activeOrders = orders.stream()
        .filter(notCancelled)
        .toList();
```

With Java 11+, `Predicate.not(...)` is convenient when you want to negate a method reference inline:

```java
List<String> nonBlank = List.of("Java", "  ", "Stream").stream()
        .filter(Predicate.not(String::isBlank))
        .toList();

// [Java, Stream]
```

To run each snippet separately, declare/import the referenced types and data; the full program in Section 3 does not depend on these extended snippets.

## 5. Checking `null`, Strings, and Missing Data

`filter` only keeps or discards elements according to the predicate you write; it **does not automatically prevent `NullPointerException`**. Filter out `null` before calling methods, or write conditions with a `null` check on the left-hand side of `&&`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.function.Predicate;

List<String> raw = Arrays.asList(" java ", null, " ", "Stream", " api ");

List<String> cleaned = raw.stream()
        .filter(Objects::nonNull)
        .map(String::trim)
        .filter(Predicate.not(String::isBlank))
        .filter(s -> s.length() >= 3)
        .map(String::toLowerCase)
        .toList();

System.out.println(cleaned); // [java, stream, api]
```

Here, `Objects::nonNull` removes `null` values before calling `trim`; `Predicate.not(String::isBlank)` drops empty or whitespace-only strings; the length condition is applied **after** whitespace has been normalized. `Arrays.asList` is used because the sample data contains `null`; `List.of(...)` does not accept `null` elements.

Case-insensitive string filtering can use `equalsIgnoreCase`:

```java
String requestedStatus = "paid";

List<Order> paidOrders = orders.stream()
        .filter(o -> requestedStatus.equalsIgnoreCase(o.status()))
        .toList();
```

If inputs can be `null`, clearly define the handling policy: skip the filter, discard elements with missing data, or report an error to the caller. You cannot assume all three approaches are equivalent in business semantics.

## 6. Dynamic Filters Based on Search Criteria

A search screen often allows leaving the status or price threshold blank. In that case, we can **build a `Predicate` step by step** instead of creating multiple `if/else` branches inside the pipeline:

```java
import java.math.BigDecimal;
import java.util.function.Predicate;

static Predicate<Order> buildOrderFilter(
        String requestedStatus,
        BigDecimal minTotal
) {
    Predicate<Order> result = o -> true;

    if (requestedStatus != null && !requestedStatus.isBlank()) {
        result = result.and(o -> requestedStatus.equals(o.status()));
    }

    if (minTotal != null) {
        result = result.and(o -> o.total() != null
                && o.total().compareTo(minTotal) >= 0);
    }

    return result;
}

// Call inside a class that defines record Order:
Predicate<Order> search = buildOrderFilter("PAID", new BigDecimal("150"));
List<Order> matchingOrders = orders.stream().filter(search).toList();
```

`o -> true` is the initial condition allowing all elements to pass through. Each provided criterion is appended with `.and(...)`. If no criteria are provided, every element from the source is retained.

The code snippets in Sections 4 and 6 are extensions based on `Order` from the main example. In real applications, organize predicate builder functions in the class containing the corresponding data type; avoid letting criteria mutate while the Stream is running.

## 7. `filter`, `map`, and Step Order in a Pipeline

Typically, if you only need to transform elements that **satisfy a condition**, filter before performing an expensive transformation, provided the filter condition can still be evaluated on the right data type:

```java
List<String> names = orders.stream()
        .filter(o -> "PAID".equals(o.status()))
        .map(Order::customer)
        .toList();
```

If you transform first, the subsequent condition must operate on the **transformed** data type:

```java
List<String> namesStartingWithA = orders.stream()
        .map(Order::customer)                 // Stream<String>
        .filter(name -> name.startsWith("A")) // Predicate<String>
        .toList();
```

Do not arbitrarily swap `filter` and `map`. For instance, `filter(o -> o.total() >= ...)` needs an `Order` object; if `.map(Order::customer)` runs first, the data has become a `String` and no longer has total amount information to check.

**A subtlety about laziness:** two consecutive `filter` steps can logically be written as a single step with `&&`:

```java
.filter(o -> "PAID".equals(o.status()))
.filter(o -> o.total().compareTo(new BigDecimal("100")) >= 0)

// Equivalent when predicates are pure, independent, and have no side effects:
.filter(o -> "PAID".equals(o.status())
        && o.total().compareTo(new BigDecimal("100")) >= 0)
```

This equivalence is based on **result-returning behavior**, not an absolute guarantee on the exact number of callback invocations across all Stream optimizations. Lambdas should not depend on mutable external state and should not modify the data source during traversal.

## 8. How `filter` Differs from `takeWhile` and Existence Checks

`filter` evaluates each element individually; `takeWhile` (Java 9+) takes the **leading contiguous prefix** satisfying the condition on an ordered Stream. They are not interchangeable:

```java
List<Integer> values = List.of(2, 4, 1, 6, 8);

System.out.println(values.stream()
        .filter(n -> n % 2 == 0).toList());
// [2, 4, 6, 8]

System.out.println(values.stream()
        .takeWhile(n -> n % 2 == 0).toList());
// [2, 4]
```

Additionally, if the goal is simply to **answer yes/no** rather than create a list, use the appropriate terminal operation:

| Goal | How to write | Result |
| --- | --- | --- |
| Get all matching elements | `stream.filter(p).toList()` | `List<T>` |
| Is there at least one matching element? | `stream.anyMatch(p)` | `boolean` |
| Do all elements match? | `stream.allMatch(p)` | `boolean` |
| Do no elements match? | `stream.noneMatch(p)` | `boolean` |
| Get the first matching element by encounter order | `stream.filter(p).findFirst()` | `Optional<T>` |
| Count matching elements | `stream.filter(p).count()` | `long` |

Example:

```java
boolean hasExpensivePaidOrder = orders.stream()
        .anyMatch(o -> "PAID".equals(o.status())
                && o.total().compareTo(new BigDecimal("200")) >= 0);

// true: DH-04 exists.
```

`anyMatch`, `allMatch`, and `noneMatch` can terminate as soon as enough information is available to determine the result. On an empty Stream, `anyMatch` is `false`, while `allMatch` and `noneMatch` are `true` by mathematical definition (*vacuous truth*).

## 9. Lazy Evaluation, Short-Circuiting, and Performance

`filter` is a lazy intermediate operation. The following example only needs to find the first two even numbers:

```java
List<Integer> firstTwo = List.of(1, 2, 3, 4, 5, 6).stream()
        .filter(n -> n % 2 == 0)
        .limit(2)
        .toList();

// [2, 4]
```

With an ordered sequential pipeline, once `2` and `4` are found, `limit(2)` already has enough results so it typically does not need to traverse `5` and `6`. `filter` does not require storing all source elements; it only decides whether to keep or discard each element. In the example above, **`limit`** is the step that bounds the count and enables early termination for the entire pipeline.

A few rules when optimizing:

- Place inexpensive filters or filters likely to eliminate many elements before heavy processing steps, **provided** that evaluation order preserves semantics.
- On very large datasets, consider filtering before stateful steps such as `sorted()` or `distinct()` if the filter condition does not depend on the results of those steps; if step order affects the outcome, prioritize correctness.
- `filter` fits parallel Streams relatively well because it is a stateless operation, yet `parallelStream()` is **not automatically faster**. Data size, cost per predicate, source characteristics, and splitting/merging overhead all matter.
- With ordered Streams like `List`, `filter(...).toList()` preserves the order of retained elements. However, do not rely on the **lambda execution order** when using parallel Streams or when optimizations might skip a step.

Do not use `peek`, counter increments, logging, or updating external objects as a required mechanism to compute a pipeline's result: some callbacks may not execute due to optimization, and a parallel pipeline may execute callbacks on different threads.

## 10. Common Mistakes

| Mistake | Why is it wrong or hard to maintain? | How to handle it |
| --- | --- | --- |
| `status == "PAID"` | `==` compares `String` references. | Use `"PAID".equals(status)` or an appropriate enum comparison. |
| `name.isBlank()` when `name` may be `null` | May throw `NullPointerException`. | Check `name != null` first or `.filter(Objects::nonNull)`. |
| `a && b || c` when `a && (b || c)` is required | OR may allow elements violating a mandatory condition. | Group conditions with parentheses or well-named `Predicate`s. |
| Using `BigDecimal.equals` to filter money by threshold | `equals` checks scale as well; does not express greater-than/less-than relations. | Use `compareTo`. |
| Using `filter(...).count() > 0` just to check existence | May have to count all matching elements. | Use `anyMatch(...)`. |
| Writing to an external list inside `filter` | Creates side effects, unpredictable with lazy or parallel execution. | Use `filter(...).toList()` or `collect(...)`. |
| Using `filter` when a contiguous prefix is needed | `filter` keeps checking elements after a non-matching position. | Consider `takeWhile` when semantically appropriate. |

Example of **not using** mutable external state to select elements:

```java
import java.util.concurrent.atomic.AtomicInteger;

AtomicInteger position = new AtomicInteger();
List<Integer> unstable = numbers.parallelStream()
        .filter(n -> position.getAndIncrement() % 2 == 0)
        .toList();
```

Element selection here depends on the **order in which threads execute the predicate**, not necessarily the original index. `AtomicInteger` ensures atomic updates but does not turn this filter into stable index-based selection. If you truly need indices, express it using `IntStream.range(0, list.size())` on a list with efficient indexed access.

## 11. Self-Practice and Understanding Check

**Exercise 1 — Value range and parity.** Given `List.of(-2, 0, 3, 4, 9, 12)`. Keep even numbers greater than `0` and not exceeding `10`.

```java
List<Integer> answer = List.of(-2, 0, 3, 4, 9, 12).stream()
        .filter(n -> n > 0 && n <= 10 && n % 2 == 0)
        .toList();
// [4]
```

**Exercise 2 — Combining OR conditions in a group.** Select orders that are paid, and are either priority orders **or** have a total of at least 200. Suitable expression:

```java
Predicate<Order> rule = paid.and(priority.or(atLeast200));
```

**Exercise 3 — Recognizing short-circuiting.** What happens with `"abc".equals(s) || s.length() >= 5` when `s` is `null`?

**Answer:** The left-hand side returns `false`; Java continues evaluating `s.length()` and throws `NullPointerException`. Write `s != null && ("abc".equals(s) || s.length() >= 5)` if you want to filter out `null` safely.

**Exercise 4 — Choosing a terminal operation.** If you want to know whether there is any `PAID` order priced over 500, do you need `.filter(...).toList()`?

**Answer:** There is no need to create a list if you only want a boolean. Use `orders.stream().anyMatch(o -> "PAID".equals(o.status()) && o.total().compareTo(new BigDecimal("500")) > 0)`.

## Key Takeaways

- `filter(Predicate<T>)` **keeps elements when the condition is `true`**, does not modify the source, preserves relative order on ordered Streams, and operates lazily.
- Combine conditions with `&&`, `||`, `!`, and **use parentheses** to accurately reflect business rules; `&&`/`||` operators short-circuit per element.
- When conditions are long, use `Predicate.and`, `or`, `negate` and name rules clearly to reduce logical precedence bugs.
- Real-world data filtering requires handling `null` explicitly, comparing strings with `equals`, comparing `BigDecimal` with `compareTo`, and avoiding lambdas with side effects.
- Choose `anyMatch`, `allMatch`, `noneMatch`, `findFirst`, or `count` depending on the desired result type; order pipeline steps for **correctness first, performance second**.
