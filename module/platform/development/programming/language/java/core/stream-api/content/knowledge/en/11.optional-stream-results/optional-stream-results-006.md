# Designing Results for Empty Sources and `null` Elements

## 1. Why Must Results Be Designed From the Start?

In the **JAVA_STREAM_API** module, declarative pipelines usually flow from a data source through `filter`, `map`, `flatMap`, and end with `findFirst`, `reduce`, `collect`, or a statistical operation. Most intermediate steps are executed lazily (*lazy*). Therefore, the return type of the **terminal operation** must accurately express both the case of **having no elements to process** and the case of **having an element whose value is `null`**.

These two questions are different:

1. **Empty source or result set:** the pipeline has no elements reaching the terminal step, for example when all orders are filtered out by `filter`.
2. **`null` element:** the pipeline has a data slot, yet the value at that slot is `null`; some methods accept it while others throw `NullPointerException`.

Simple example:

```java
import java.util.List;
import java.util.stream.Stream;

List<String> empty = List.of();
System.out.println(empty.stream().findFirst()); // Optional.empty

Stream<String> containsNull = Stream.<String>of((String) null);
// containsNull.findFirst() will throw NullPointerException.
```

Both streams have no usable string, yet their **semantics are not the same**. `Optional.empty()` represents no value found; it cannot hold a `null` value as a present result.

After this lesson, you will be able to:

- Identify the result of each terminal operation when a stream is empty.
- Understand `Optional<T>`, `OptionalInt`, `OptionalLong`, and `OptionalDouble`.
- Distinguish `Stream.ofNullable`, `Optional.ofNullable`, and `filter(Objects::nonNull)`.
- Determine policies to **skip, fail on, replace, or preserve** elements with missing data.
- Design suitable return types: `Optional`, empty collections, identity values, exceptions, or result types with explicit status.
- Write testable pipelines for missing data, empty results, and parallel processing.

## 2. Four States to Distinguish in Business Logic

Consider an operation looking up a customer's email. Common situations:

| State | Business meaning | Suitable representation |
| --- | --- | --- |
| No customer matches the condition | Record not found | `Optional.empty()` or status `NOT_FOUND` |
| Customer exists and email is valid | Value found | `Optional.of(email)` or status `FOUND` |
| Customer exists but email field is `null` | Record exists, attribute missing | Separate status `EMAIL_MISSING`, or a data error if the contract forbids it |
| Unable to access the data source | Operation failed | Exception/error type with cause, never silently turned into "not found" |

If you use only `Optional<String>` for the email, both "no customer" and "customer has `null` email" can collapse into `Optional.empty()`. That is **valid only when business rules intentionally treat both cases as equivalent**.

Similarly, an empty source does not prove that **there is no data in the system**. It only indicates that **the stream fed into the current pipeline has no elements**. A failed query, an overly strict filter, or a normalization step that dropped data are separate issues that must be handled at the appropriate boundary.

## 3. When a Stream Is Empty, What Do Terminal Operations Return?

Different APIs choose different result contracts:

| Terminal operation | Result on an empty stream | Meaning |
| --- | --- | --- |
| `count()` | `0L` | Zero elements |
| `findFirst()` / `findAny()` | `Optional.empty()` | No element found |
| `min(comparator)` / `max(comparator)` | `Optional.empty()` | No extremum exists |
| `reduce(accumulator)` | `Optional.empty()` | No reduction result |
| `reduce(identity, accumulator)` | `identity` | Declared identity value |
| `toList()` | Empty list | No elements to collect |
| `collect(Collectors.toList())` | Empty list | Accumulator yields empty result |
| `collect(Collectors.groupingBy(...))` | Empty map | No groups created |
| `collect(Collectors.counting())` | `0L` | Collector counts zero elements |
| `anyMatch(predicate)` | `false` | No matching element exists |
| `allMatch(predicate)` | `true` | No counterexample element exists |
| `noneMatch(predicate)` | `true` | No matching element exists |
| `IntStream.sum()` | `0` | Sum with additive identity 0 |
| `IntStream.average()` | `OptionalDouble.empty()` | No average exists |
| `IntStream.min()` / `max()` | `OptionalInt.empty()` | No extremum exists |
| `IntStream.summaryStatistics()` | Statistics object with `count == 0` | Must check count before using extrema |

The three operations `anyMatch`, `allMatch`, and `noneMatch` on an empty source are examples of **vacuous truth** (*vacuous truth*): no element falsifies the proposition "all satisfy", so `allMatch` returns `true`. Do not infer that `true` means "at least one element was checked".

Example running on **JDK 17 or later**:

```java
import java.util.List;
import java.util.Optional;
import java.util.stream.Stream;

List<Integer> values = List.of();

System.out.println(values.stream().count());           // 0
System.out.println(values.stream().findFirst());       // Optional.empty
System.out.println(values.stream().reduce(Integer::sum)); // Optional.empty
System.out.println(values.stream().reduce(0, Integer::sum)); // 0
System.out.println(values.stream().toList());          // []
System.out.println(values.stream().allMatch(x -> x > 0)); // true
System.out.println(values.stream().anyMatch(x -> x > 0)); // false

Optional<Integer> first = Stream.<Integer>empty().findFirst();
System.out.println(first.isEmpty()); // true
```

**Point to choose clearly:** returning `0` as the sum of an empty source is **correct by addition convention**. Returning `0` for "latest transaction amount" can be misleading, because `0` is a valid number rather than an existing transaction. For "find an element" problems, `Optional` usually expresses intent more accurately than a default value.

## 4. `Optional<T>`: Representing Presence or Absence of a Result

`Optional<T>` is a container that can hold **a single non-`null` value**, or be empty. Commonly used methods:

| Method | Purpose |
| --- | --- |
| `Optional.empty()` | Creates an Optional with no value |
| `Optional.of(value)` | Creates an Optional with a value; `value == null` causes `NullPointerException` |
| `Optional.ofNullable(value)` | Present if non-`null`, empty if `null` |
| `isPresent()` / `isEmpty()` | Checks presence |
| `ifPresent(consumer)` | Executes an action if a value is present |
| `ifPresentOrElse(action, emptyAction)` | Branches on presence/absence, since JDK 9 |
| `map(function)` | Transforms the present value; mapper returning `null` yields an empty Optional |
| `flatMap(function)` | Transforms using a function returning `Optional<U>`, avoiding `Optional<Optional<U>>` |
| `filter(predicate)` | Keeps the value only if the condition holds |
| `orElse(defaultValue)` | Uses a fallback value when empty |
| `orElseGet(supplier)` | Computes the fallback value **only when empty** |
| `orElseThrow()` / `orElseThrow(supplier)` | Throws an exception when empty |
| `stream()` | Converts into a stream of 0 or 1 element, since JDK 9 |

### 4.1. Designing a Search Method

```java
import java.util.List;
import java.util.Optional;

record User(String id, String displayName) {}

static Optional<User> findUser(List<User> users, String id) {
    return users.stream()
        .filter(user -> user.id().equals(id))
        .findFirst();
}

// In the calling method:
// Optional<User> result = findUser(users, "U-1");
// result.ifPresent(user -> System.out.println(user.displayName()));
```

This snippet assumes the list contains only valid `User` objects and each user's `id` is non-`null`. If the source can contain `null` elements, decide how to handle them **before** accessing `user.id()`.

You do not need to force calling `optional.get()` and handling `NoSuchElementException` manually. Prefer `ifPresent`, `map`, `orElseThrow`, `orElseGet`, or combine `Optional.stream` depending on the situation.

### 4.2. `orElse` and `orElseGet` Differ in Evaluation Timing

```java
import java.util.Optional;

static String expensiveFallback() {
    // In a real application this might perform I/O.
    return "FALLBACK";
}

Optional<String> found = Optional.of("Result");

String a = found.orElse(expensiveFallback());
String b = found.orElseGet(() -> expensiveFallback());

System.out.println(a); // Result
System.out.println(b); // Result
```

`expensiveFallback()` in the `orElse(...)` call is evaluated **before** `orElse` is invoked, even though the Optional already has a value. The Supplier of `orElseGet(...)` is only invoked when the Optional is empty. If the fallback value is a constant like `"Not found"`, simple `orElse` is enough.

### 4.3. `map` on Optional Can Hide `null` From the Mapper

```java
Optional<String> maybeName = Optional.of("An");

Optional<String> hiddenMissingValue = maybeName
    .map(name -> (String) null);

System.out.println(hiddenMissingValue.isEmpty()); // true
```

When the mapper returns `null`, `Optional.map` returns `Optional.empty()`. If `null` indicates **invalid data**, validate or throw an explicit exception before losing the reason for absence. `Optional.flatMap` differs in that the mapper must return a **non-`null`** `Optional`; returning a `null` Optional reference causes `NullPointerException`.

## 5. `null` in the Source: Three Similar-Looking Operations That Are Not Equivalent

### 5.1. `Stream.ofNullable(value)` Takes a Potentially `null` Reference

`Stream.ofNullable(T)` was added in **JDK 9**:

```java
import java.util.List;
import java.util.stream.Stream;

String provided = null;

List<String> a = Stream.ofNullable(provided).toList();
System.out.println(a); // []

List<String> b = Stream.ofNullable("Java").toList();
System.out.println(b); // [Java]
```

`Stream.ofNullable(value)` creates a stream of **0 elements if `value == null`**, or **1 element if non-`null`**. This expresses the policy "a `null` input means no element".

Conversely, `Stream.of((String) null)` can create a stream containing **one `null` element**:

```java
Stream<String> singleNull = Stream.<String>of((String) null);
System.out.println(singleNull.count()); // 1
```

The explicit type witness in the example avoids ambiguity with the varargs array overload of `Stream.of`. `count()` does not need to inspect the element content so it can return `1`; calling another terminal operation such as `findFirst()` on that stream has a different contract.

### 5.2. `filter(Objects::nonNull)` Filters `null` Elements *Inside* a Stream

`Stream.ofNullable` only checks **the single reference passed to it**. It does **not** look inside a collection to drop `null` elements:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> raw = Arrays.asList("An", null, "Bình", null);

List<String> cleaned = raw.stream()
    .filter(Objects::nonNull)
    .toList();

System.out.println(cleaned); // [An, Bình]
```

If you already have a `Stream<T>` containing multiple elements, `filter(Objects::nonNull)` is what filters each element. `List.of("An", null)` throws `NullPointerException` immediately upon **list creation**, whereas `Arrays.asList(...)` and `ArrayList` allow `null`.

### 5.3. The Source Collection Itself May Be `null`

Distinguish a **`null` collection** from a **collection containing `null` elements**:

```java
import java.util.List;
import java.util.stream.Stream;

static Stream<String> itemsOrEmpty(List<String> items) {
    return items == null
        ? Stream.empty()
        : items.stream();
}
```

This is an **intentional API convention**. If a `null` list is a programming or data error, instead of silently turning it into an empty stream, use `Objects.requireNonNull(items, "items")` and fix the data at the source.

## 6. Which Terminal Operations Face Risks With `null` Elements?

Several terminal operations returning `Optional` treat `null` as an invalid state for the **selected element**.

### 6.1. `findFirst` and `findAny`

By the contract of `Stream.findFirst()` and `Stream.findAny()`, if the **selected element** is `null`, the method throws `NullPointerException`:

```java
import java.util.Arrays;
import java.util.List;

List<String> data = Arrays.asList(null, "Java", "Stream");

// data.stream().findFirst(); // NullPointerException: first element is null.

String firstNonNull = data.stream()
    .filter(java.util.Objects::nonNull)
    .findFirst()
    .orElse("None");

System.out.println(firstNonNull); // Java
```

With a stream lacking an encounter order, `findAny()` does not guarantee which element is chosen; if it picks `null`, it can also throw an exception. Do not rely on the stream "having at least one non-`null` element" to conclude `findAny` is always safe.

### 6.2. `min`, `max`, and `reduce`

Extremum-selecting operations typically use a comparator; natural comparators such as `Comparator.naturalOrder()` do not handle `null`. In particular, reductions returning `Optional` also cannot hold a `null` result; by the contract of `reduce(BinaryOperator)`, a reduction result of `null` causes `NullPointerException`.

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<Integer> values = Arrays.asList(null, 4, 9, 2);

int max = values.stream()
    .filter(Objects::nonNull)
    .max(Integer::compareTo)
    .orElseThrow();

System.out.println(max); // 9
```

`Comparator.nullsFirst(...)` and `nullsLast(...)` can define an ordering for `null` during **the comparison step**, yet you still must consider the final result: the `Optional` returned by `min`/`max` cannot represent a `null` extremum as a present value. When `null` has its own meaning, choosing a comparator alone is not enough to design the return contract.

### 6.3. `map`, `sorted`, `toList`, and Collectors

| Step | What can happen when encountering `null`? |
| --- | --- |
| `map(x -> x.toString())` | Throws `NullPointerException` when dereferencing `x` |
| `map(x -> x == null ? "?" : x.toString())` | Substitutes according to an explicit rule |
| `filter(Objects::nonNull)` | Drops all `null` elements passing the filter step |
| `sorted()` using natural order | Natural comparator usually does not accept `null` |
| `Stream.toList()` (JDK 16+) | Can create a list containing `null` elements; the returned list is unmodifiable |
| `Collectors.toUnmodifiableList()` (JDK 10+) | Rejects `null` values with `NullPointerException` |
| `Collectors.toList()` | Makes no guarantees on implementation type or mutability; do not treat it as a "null-accepting contract" |
| `Collectors.groupingBy(classifier)` | Must avoid `null` grouping keys; the default implementation rejects `null` classifier results |

Try an important difference:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<String> nullable = Arrays.asList("A", null, "B");

List<String> preserved = nullable.stream().toList();
System.out.println(preserved); // [A, null, B]

// nullable.stream().collect(Collectors.toUnmodifiableList());
// NullPointerException because the collector forbids null elements.
```

That a list **can hold `null`** does not mean downstream operations accept `null`. When designing results, explicitly document "whether `null` is allowed" and avoid accidental dependence on collection implementations.

## 7. Choosing a Business Strategy for Missing Data

No single policy fits every situation. Choose before writing lambdas:

| Policy | When is it reasonable? | How to express it |
| --- | --- | --- |
| **Reject** invalid data | Missing data makes reports or transactions untrustworthy | Validate and throw an exception / record structured errors |
| **Skip** `null` records | Source allows blank entries and skipping is allowed by spec | `filter(Objects::nonNull)` |
| **Replace** with a meaningful value | An accepted business default convention exists | `map(x -> x == null ? fallback : x)` |
| **Preserve** `null` values | Target API intentionally represents missing attributes | Collection/DTO allowing `null` with clear documentation |
| **Distinguish three states** | Must distinguish "record not found" from "record missing attribute" | Result type with explicit status |

Example grouping by sales channel, with a valid rule that a `null` channel is grouped under `"UNKNOWN"`:

```java
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;

record Sale(String channel, long amountVnd) {}

List<Sale> sales = List.of(
    new Sale("WEB", 1000),
    new Sale(null, 2000),
    new Sale("WEB", 3000)
);

Map<String, Long> totals = sales.stream()
    .collect(Collectors.groupingBy(
        sale -> sale.channel() == null ? "UNKNOWN" : sale.channel(),
        Collectors.summingLong(Sale::amountVnd)
    ));

System.out.println(totals.get("WEB"));     // 4000
System.out.println(totals.get("UNKNOWN")); // 2000
```

If `"UNKNOWN"` could collide with a real business key, use an explicit key type (such as an enum or record) instead of a default string. Do not replace `null` with `0` or an empty string if that fallback value is also valid data and would skew statistics.

## 8. Complete Example: Reporting From a Source With `null` Elements

Suppose a sales system has a list of transactions in recorded order. Problem rules:

- The source collection **must be non-`null`**; a `null` input is an API error.
- The list may contain some `null` slots from data entry; **skip** those slots per reporting convention.
- Only aggregate approved transactions (`approved == true`).
- Present transaction records have valid ID, channel, unit price, and quantity; validate at construction time.
- If there are no valid transactions, the list is empty, the total is `0`, and the first transaction is absent via `Optional.empty()`.

Full code running on **JDK 17 or later**:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;
import java.util.Optional;
import java.util.OptionalLong;
import java.util.stream.Stream;

public class NullableSalesReport {

    public record Sale(
        String id,
        String channel,
        int quantity,
        long unitPriceVnd,
        boolean approved
    ) {
        public Sale {
            Objects.requireNonNull(id, "id");
            Objects.requireNonNull(channel, "channel");
            if (id.isBlank() || channel.isBlank()) {
                throw new IllegalArgumentException("id/channel must not be blank");
            }
            if (quantity <= 0 || unitPriceVnd < 0) {
                throw new IllegalArgumentException("Invalid quantity/price");
            }
        }
    }

    public record SaleView(String id, String channel, long amountVnd) {}

    private static Stream<Sale> approvedSales(List<Sale> source) {
        Objects.requireNonNull(source, "source");
        return source.stream()
            .filter(Objects::nonNull)
            .filter(Sale::approved);
    }

    private static SaleView toView(Sale sale) {
        long amount = Math.multiplyExact(
            (long) sale.quantity(), sale.unitPriceVnd()
        );
        return new SaleView(sale.id(), sale.channel(), amount);
    }

    public static List<SaleView> allApproved(List<Sale> source) {
        return approvedSales(source)
            .map(NullableSalesReport::toView)
            .toList();
    }

    public static Optional<SaleView> firstApproved(List<Sale> source) {
        return approvedSales(source)
            .map(NullableSalesReport::toView)
            .findFirst();
    }

    public static OptionalLong largestApprovedAmount(List<Sale> source) {
        return approvedSales(source)
            .mapToLong(sale -> Math.multiplyExact(
                (long) sale.quantity(), sale.unitPriceVnd()
            ))
            .max();
    }

    public static long totalApprovedAmount(List<Sale> source) {
        return approvedSales(source)
            .mapToLong(sale -> Math.multiplyExact(
                (long) sale.quantity(), sale.unitPriceVnd()
            ))
            .reduce(0L, Math::addExact);
    }

    public static void main(String[] args) {
        List<Sale> source = Arrays.asList(
            new Sale("S1", "WEB", 2, 10_000L, true),
            null,
            new Sale("S2", "STORE", 1, 8_000L, false),
            new Sale("S3", "WEB", 1, 5_000L, true)
        );

        System.out.println(allApproved(source));
        // [SaleView[id=S1, channel=WEB, amountVnd=20000],
        //  SaleView[id=S3, channel=WEB, amountVnd=5000]]

        System.out.println(firstApproved(source));
        // Optional[SaleView[id=S1, channel=WEB, amountVnd=20000]]

        System.out.println(largestApprovedAmount(source));
        // OptionalLong[20000]

        System.out.println(totalApprovedAmount(source)); // 25000

        List<Sale> empty = List.of();
        System.out.println(allApproved(empty)); // []
        System.out.println(firstApproved(empty)); // Optional.empty
        System.out.println(largestApprovedAmount(empty)); // OptionalLong.empty
        System.out.println(totalApprovedAmount(empty)); // 0
    }
}
```

### 8.1. Why Does the Example Have Multiple Result Types?

| Method | Return type | When there are no approved sales |
| --- | --- | --- |
| `allApproved` | `List<SaleView>` | `[]`: collection with zero rows |
| `firstApproved` | `Optional<SaleView>` | `Optional.empty()`: no first element |
| `largestApprovedAmount` | `OptionalLong` | `OptionalLong.empty()`: no maximum exists |
| `totalApprovedAmount` | `long` | `0L`: identity value of addition |

These are contracts with distinct meanings; do not force all of them into the same type or a "sentinel error code" like `-1`. If business rules need to distinguish **no transactions** from **approved transactions totaling 0**, also return `count` or a summary result type containing that state.

### 8.2. Technical Notes

- `Arrays.asList` in `main` can contain `null` elements, whereas `List.of(...)` forbids them.
- `filter(Objects::nonNull)` must come **before** `filter(Sale::approved)` so `null` elements are never dereferenced.
- `firstApproved` preserves the encounter order of `List`, while `findAny` does not guarantee picking the first row if parallel processing is used.
- `Math.multiplyExact` detects overflow during multiplication, and `Math.addExact` detects overflow during addition. Do not use `LongStream.sum()` if the contract requires throwing an error when the total exceeds `long` range.
- Each method opens a new stream from `source`; a consumed stream is never reused.
- `toList()` returns an unmodifiable list; each `SaleView` is a record with immutable fields in the example.

## 9. Explicit Result Type When Preserving "Record Exists but Attribute Is Missing"

Not every business rule allows dropping rows with missing data. If you must distinguish **not found** from **found but email not provided**, an explicit result type is clearer than `Optional<String>`.

Standalone example running on **JDK 17+**:

```java
import java.util.List;
import java.util.Objects;

public class EmailLookupDemo {

    record Customer(String id, String email) {}

    enum LookupStatus { NOT_FOUND, EMAIL_MISSING, FOUND }

    record EmailLookup(LookupStatus status, String email) {}

    static EmailLookup lookupEmail(List<Customer> customers, String id) {
        Objects.requireNonNull(customers, "customers");
        Objects.requireNonNull(id, "id");

        return customers.stream()
            .filter(Objects::nonNull)
            .filter(customer -> id.equals(customer.id()))
            .findFirst()
            .map(customer ->
                customer.email() == null
                    ? new EmailLookup(LookupStatus.EMAIL_MISSING, null)
                    : new EmailLookup(LookupStatus.FOUND, customer.email())
            )
            .orElseGet(() ->
                new EmailLookup(LookupStatus.NOT_FOUND, null)
            );
    }

    public static void main(String[] args) {
        List<Customer> customers = List.of(
            new Customer("U1", "u1@example.test"),
            new Customer("U2", null)
        );

        System.out.println(lookupEmail(customers, "U1").status()); // FOUND
        System.out.println(lookupEmail(customers, "U2").status()); // EMAIL_MISSING
        System.out.println(lookupEmail(customers, "U3").status()); // NOT_FOUND
    }
}
```

Here `findFirst()` receives a **non-`null` `Customer` object** because we filtered first. Only after finding the customer does `map` inspect whether the `email` field is `null`. Thus the state **record exists but email is missing** is not conflated with **record not found**.

This is a minimal illustrative result type. In a real system, enforce invariants between `status` and `email` (for example, `FOUND` must have a non-`null` email), or design a dedicated sealed type per branch to make invalid states unrepresentable.

## 10. `OptionalInt`, `OptionalLong`, `OptionalDouble`, and Numeric Statistics

Primitive streams have specialized optional results to avoid boxing:

| Source | Operation | Result |
| --- | --- | --- |
| `IntStream` | `min()`, `max()`, `findFirst()` | `OptionalInt` |
| `LongStream` | `min()`, `max()`, `findAny()` | `OptionalLong` |
| `DoubleStream` | `min()`, `max()`, `average()` | `OptionalDouble` |
| `IntStream` | `average()` | `OptionalDouble` |
| `LongStream` | `average()` | `OptionalDouble` |

Example:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt smallest = IntStream.empty().min();
OptionalDouble average = IntStream.empty().average();

System.out.println(smallest.isEmpty()); // true
System.out.println(average.isEmpty());  // true

int fallbackForDisplay = smallest.orElse(0);
System.out.println(fallbackForDisplay); // 0
```

In the example, `orElse(0)` is only a decision for **displaying a default number**, not proof that the minimum equals 0. If computing business values requiring accuracy, it is better to handle the empty branch explicitly.

### 10.1. The Average of an Empty Set Is Not 0

`IntStream.average()` returns `OptionalDouble.empty()` on an empty source, because there are no samples to divide by. If converted to `0.0` with `orElse(0)`, readers may mistakenly believe the system measured an average of 0:

```java
OptionalDouble mean = IntStream.empty().average();

String display = mean.isPresent()
    ? Double.toString(mean.getAsDouble())
    : "No data yet";

System.out.println(display); // No data yet
```

### 10.2. Reading `summaryStatistics()` Properly

`IntSummaryStatistics` has `getCount()`, `getSum()`, `getMin()`, `getMax()`, and `getAverage()`. On an empty source, `count == 0` and `average == 0.0` per the statistics class contract; `min` and `max` use **special initial sentinel values** `Integer.MAX_VALUE` and `Integer.MIN_VALUE`, respectively.

```java
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

IntSummaryStatistics stats = IntStream.empty().summaryStatistics();

System.out.println(stats.getCount()); // 0
System.out.println(stats.getAverage()); // 0.0

if (stats.getCount() == 0) {
    System.out.println("No data to determine min/max");
}
```

**Do not** use `getMin()`/`getMax()` of an empty set as if they were real measured values. `summaryStatistics()` is especially useful if you want to read multiple metrics in a **single pass**; clearly define how to present those metrics when `count == 0`.

## 11. Combining `Optional.stream()` and `flatMap` When There Are Multiple Optional Results

`Optional.stream()` (JDK 9+) converts an Optional into a stream:

- `Optional.of(x).stream()` emits exactly one element `x`.
- `Optional.empty().stream()` emits zero elements.

This is useful when a pipeline produces **one Optional per record**:

```java
import java.util.List;
import java.util.Optional;

record RawProduct(String id, String name) {}

static Optional<String> validName(RawProduct product) {
    if (product == null || product.name() == null
            || product.name().isBlank()) {
        return Optional.empty();
    }
    return Optional.of(product.name().strip());
}

List<RawProduct> source = java.util.Arrays.asList(
    new RawProduct("P1", "Pen"),
    new RawProduct("P2", null),
    null,
    new RawProduct("P3", "Notebook")
);

List<String> names = source.stream()
    .map(product -> validName(product))
    .flatMap(Optional::stream)
    .toList();

System.out.println(names); // [Pen, Notebook]
```

Each product produces an `Optional<String>`; `flatMap(Optional::stream)` keeps only present values. This pattern is reasonable if **"no valid name means omit from the result"** is an accepted business rule. If a record missing a name must be reported as an error, replace `validName` with a validation step and retain the error details.

For `OptionalInt`/`OptionalLong`/`OptionalDouble`, `stream()` also exists since JDK 9 and returns the corresponding primitive stream. They can be combined when collecting multiple optional numeric results without boxing.

## 12. Laziness, Short-Circuiting, and Parallel Streams

When designing `null` handling, keep in mind that a Stream API pipeline only performs the invocations actually needed to produce the terminal result:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> words = Arrays.asList("Java", null, "Stream");

String first = words.stream()
    .filter(Objects::nonNull)
    .findFirst()
    .orElse("None");

System.out.println(first); // Java
```

`findFirst()` is a terminal operation that can **short-circuit**, so the pipeline does not need to process all subsequent elements. Never rely on the number of times `filter`/`map`/`peek` is called to record mandatory business logs or increment shared counters.

With `parallelStream()`:

- `findFirst()` preserves encounter order when the source is ordered, though it may require additional coordination across threads.
- `findAny()` may select any element and the result can differ between runs.
- If the source contains `null` elements, handle them **before operations that do not accept `null`**; parallel execution does not make null data valid.
- Predicates, mappers, and accumulators must satisfy **non-interference** and **statelessness** contracts as required by Stream; do not mutate the source collection or unsynchronized counters.
- Parallel mode is not automatically faster; measure on real data and operation costs.

Semantically safe example:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Objects;

List<String> data = Arrays.asList("A", null, "B", "C");

List<String> result = data.parallelStream()
    .filter(Objects::nonNull)
    .map(String::toLowerCase)
    .toList();

System.out.println(result); // [a, b, c]
```

With a `List` source having an encounter order, `toList()` preserves the element order from the source even though transformations may execute at different times. Filtering `null` upfront prevents `String::toLowerCase` from encountering a null reference.

## 13. Empty I/O Sources, I/O Errors, and Resource Lifecycle

Having zero lines of data and **failing to read a file** are two distinct states:

```java
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Optional;
import java.util.stream.Stream;

static Optional<String> firstNonBlankLine(Path path) throws IOException {
    try (Stream<String> lines =
             Files.lines(path, StandardCharsets.UTF_8)) {
        return lines
            .map(String::strip)
            .filter(line -> !line.isEmpty())
            .findFirst();
    }
}
```

For a valid yet empty file (or one with only blank lines), the method returns `Optional.empty()`. If opening/reading the file encounters an I/O error, the method **does not** return an empty Optional; it lets the error propagate according to the API's exception mechanism. `Files.lines` creates a stream holding an I/O resource; `try-with-resources` guarantees closing the resource even when `findFirst()` terminates early.

In applications using `flatMap` to combine multiple file streams, read the closing contract for **inner streams** in `flatMap` and close resource-backed source streams with `try-with-resources`. Do not use `Optional.empty()` as a substitute for data-access exceptions.

## 14. Testing Empty and `null` Cases

The following JUnit 5 tests use the `NullableSalesReport` class from section 8. If creating a separate test file, place the class in a package that can access the report class and add the JUnit Jupiter dependency per your project setup.

```java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import org.junit.jupiter.api.Test;

class NullableSalesReportTest {

    @Test
    void emptySourceHasExplicitEmptyResults() {
        List<NullableSalesReport.Sale> empty = List.of();

        assertEquals(List.of(), NullableSalesReport.allApproved(empty));
        assertEquals(Optional.empty(),
            NullableSalesReport.firstApproved(empty));
        assertTrue(NullableSalesReport.largestApprovedAmount(empty).isEmpty());
        assertEquals(0L, NullableSalesReport.totalApprovedAmount(empty));
    }

    @Test
    void onlyNullRowsAreIgnoredByPolicy() {
        List<NullableSalesReport.Sale> source =
            Arrays.asList(null, null);

        assertEquals(List.of(), NullableSalesReport.allApproved(source));
        assertEquals(Optional.empty(),
            NullableSalesReport.firstApproved(source));
    }

    @Test
    void firstValidResultAfterNullIsPresent() {
        List<NullableSalesReport.Sale> source = Arrays.asList(
            null,
            new NullableSalesReport.Sale(
                "S1", "WEB", 2, 10_000L, true
            )
        );

        assertEquals(
            Optional.of(new NullableSalesReport.SaleView(
                "S1", "WEB", 20_000L
            )),
            NullableSalesReport.firstApproved(source)
        );
    }

    @Test
    void noApprovedRowsMeansNoMatchingResult() {
        List<NullableSalesReport.Sale> source = List.of(
            new NullableSalesReport.Sale(
                "S2", "STORE", 1, 8_000L, false
            )
        );

        assertEquals(List.of(), NullableSalesReport.allApproved(source));
        assertTrue(NullableSalesReport.firstApproved(source).isEmpty());
    }

    @Test
    void nullCollectionIsApiError() {
        assertThrows(
            NullPointerException.class,
            () -> NullableSalesReport.allApproved(null)
        );
    }

    @Test
    void invalidRecordFailsFast() {
        assertThrows(
            IllegalArgumentException.class,
            () -> new NullableSalesReport.Sale(
                "S3", "WEB", 0, 100L, true
            )
        );
    }

    @Test
    void overflowIsNotSilentlyAccepted() {
        List<NullableSalesReport.Sale> source = List.of(
            new NullableSalesReport.Sale(
                "S4", "WEB", 2, Long.MAX_VALUE, true
            )
        );

        assertThrows(
            ArithmeticException.class,
            () -> NullableSalesReport.totalApprovedAmount(source)
        );
    }
}
```

### 14.1. Test Matrix to Add

| Input | What to verify |
| --- | --- |
| Empty collection | Each terminal operation yields the contract-compliant empty/identity result |
| Collection containing only `null` elements | Filtering/error policy is applied consistently |
| `null` at the start, middle, and end | Mappers/terminals do not accidentally dereference `null` |
| Elements exist but all are rejected by `filter` | Result matches an empty source per the search contract |
| Valid value equal to `0` | Not mistaken for "no value" |
| Mapper returns `null` | Distinguish `Optional.map` result from a stream containing a `null` element |
| Differently ordered sources | `findFirst` obeys encounter order; do not infer order for `findAny` |
| Source access fails | Error is reported, not turned into `Optional.empty()` |
| Numeric arithmetic overflow | Overflow error policy or larger numeric type is tested |

Do not write unit tests requiring a mapper to be called **an exact number of times equal to the source length**: laziness, short-circuiting, and Stream optimizations can invalidate that assumption.

## 15. Practice Exercises

**Exercise 1 — Empty source and three result types.** Given `List<Integer> values = List.of()`. Write three pipelines using `findFirst`, `reduce(Integer::sum)`, and `reduce(0, Integer::sum)` respectively. Explain why the first two results are `Optional.empty()` while the last is `0`.

**Exercise 2 — `null` elements and `findFirst`.** Create a `List<String>` with three elements `null`, `"A"`, and `"B"` using `Arrays.asList`. Predict the result of `findFirst` on the raw stream and with `filter(Objects::nonNull)` before it. Test the exception in the first case.

**Exercise 3 — Designing Optional.** Write `Optional<String> findCode(List<String> codes, String prefix)`. Specify whether `null` elements should be skipped or treated as errors; write tests for an empty source, a matching code, and no matching code. Do not use `null` as the return value of the method itself.

**Exercise 4 — Average and valid 0.** Given `IntStream.empty()` and `IntStream.of(0)`. Get `average()` of each stream. Demonstrate why `orElse(0.0)` can lose the ability to distinguish "no samples" from "actual average of 0".

**Exercise 5 — Three email states.** Rewrite the `EmailLookupDemo` example so the result type disallows the `FOUND` state with a `null` email. Hint: use a sealed interface and three record types representing `Found`, `EmailMissing`, and `NotFound` (JDK 17+).

**Exercise 6 — Grouping with missing keys.** Given sales data with `null` channels, explicitly choose among: rejecting the order, skipping the order, or grouping into `UNKNOWN`. Write a `groupingBy` pipeline for the chosen policy and test the result when all channels are `null`.

**Exercise 7 — Resources.** Write a method returning `Optional<String>` for the first non-blank line in a file using `Files.lines`. Test an empty file and a non-empty file. Explain why a nonexistent file must report an error instead of returning `Optional.empty()`.

## 16. Decision Table When Designing Results

| Question | Suggested decision |
| --- | --- |
| Should the result be **one** element that may not be found? | `Optional<T>` or corresponding primitive Optional |
| Is the result **multiple** elements? | Empty collection when there are no elements |
| Does the computation have a business-valid identity? | `reduce(identity, ...)` or dedicated terminal operation |
| Does a record exist but lack an attribute? | Consider whether a separate status, validation, or explicit default is needed |
| Does a `null` input mean "no single value"? | `Stream.ofNullable` or `Optional.ofNullable` |
| Does a stream contain `null` elements? | `filter(Objects::nonNull)` when policy allows |
| Does a later step return `Optional` but may encounter null? | Handle `null` before `findFirst`/`findAny`/reduction |
| Numeric data has no samples? | `OptionalInt`/`OptionalLong`/`OptionalDouble`, distinct from 0 |
| Need to collect Optionals produced inside a pipeline? | `flatMap(Optional::stream)` if absent values may be dropped |
| I/O source fails? | Propagate/return error explicitly and close the stream; do not equate with empty source |
| May the pipeline run in parallel? | Keep mappers/predicates non-interfering with no shared mutable state |

Designing results for empty sources and `null` elements is part of the **data contract** in the Java Stream API. `Optional` expresses the presence or absence of a **non-`null` value**; an empty list expresses zero collection elements; an identity value fits reduction operations; and `null` in the source requires an explicit policy. When those distinctions are reflected directly in the return types, `filter`, `map`, `reduce`, `collect`, and grouping pipelines become both easier to test and protected against distorted metrics caused by lost information or swallowed errors.
