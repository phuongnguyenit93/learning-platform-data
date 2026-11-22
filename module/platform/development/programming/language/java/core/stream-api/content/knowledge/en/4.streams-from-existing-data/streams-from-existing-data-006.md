# Converting Optional to Stream with Optional.stream

## 1. The Problem: Potentially Having One Value or No Value

In the **Streams from Existing Data** chapter of **JAVA_STREAM_API**, not every data source is a list, set, or array. A query method may return `Optional<T>` to represent **having either one value or no value**. When you want to combine that query result with the declarative pipeline of the Java Stream API, `Optional.stream()` is the direct bridge.

For example, a customer lookup system may find or not find a phone number. For one customer, we have an `Optional<String>`. For many customers, we may have a `Stream<Optional<String>>` and want to receive back a `Stream<String>` containing only the numbers that actually exist.

~~~text
Optional<T>
  ├── Optional.of(value) ──► stream() ──► Stream<T> containing 1 element
  └── Optional.empty() ────► stream() ──► empty Stream<T>

Stream<Optional<T>>
  └── flatMap(Optional::stream) ─────────► Stream<T>
                                           (drops empty Optionals)
~~~

**Main takeaway:** `Optional.stream()` returns a sequential Stream with **0 or 1 element**. This method was introduced in **Java 9**. The lesson also uses `Stream.toList()` (available since Java 16), so the examples can be run with **Java 17+**.

## 2. Syntax and Basic Behavior

Method signature:

~~~java
public Stream<T> stream()
~~~

`Optional<T>.stream()` turns an Optional object into a Stream with two possibilities:

| Input Optional | `stream()` result | `toList()` result |
| --- | --- | --- |
| `Optional.of("An")` | One element `"An"` | `["An"]` |
| `Optional.empty()` | No elements | `[]` |
| `Optional.ofNullable(null)` | No elements | `[]` |

Example:

~~~java
import java.util.List;
import java.util.Optional;

public class BasicOptionalStreamDemo {
    public static void main(String[] args) {
        Optional<String> found = Optional.of("An");
        Optional<String> missing = Optional.empty();

        List<String> one = found.stream().toList();
        List<String> none = missing.stream().toList();

        System.out.println(one);  // [An]
        System.out.println(none); // []
    }
}
~~~

Here there is no need to call `isPresent()` or `get()` to extract the value before creating the Stream. `Optional.stream()` handles the empty case by itself. No `null` element is produced when the Optional is empty.

An `Optional` object **does not hold multiple values**: when a multi-element stream is needed, those values must come from other sources (e.g., `List`, `Set`, `Stream.of(...)`, or a function mapping one value to many values). `Optional.stream()` only bridges the 0–1 element case into the pipeline mechanism.

## 3. Most Important Use Case: Flattening a Stream of Multiple Optionals

Suppose we have a list of lookup results; some results have values, some are empty.

~~~java
import java.util.List;
import java.util.Optional;

List<Optional<String>> maybeNames = List.of(
    Optional.of("An"),
    Optional.empty(),
    Optional.of("Bình"),
    Optional.empty(),
    Optional.of("Chi")
);

List<String> names = maybeNames.stream()
    .flatMap(Optional::stream)
    .toList();

System.out.println(names); // [An, Bình, Chi]
~~~

Pipeline steps:

1. `maybeNames.stream()` creates a `Stream<Optional<String>>`.
2. `Optional::stream` calls the `stream()` method on each `Optional<String>`, producing a 0- or 1-element stream.
3. `flatMap(...)` concatenates the sub-streams into a single `Stream<String>`.
4. `toList()` is the terminal operation that collects the present values.

Illustration:

~~~text
[Some("An"), Empty, Some("Bình"), Empty, Some("Chi")]
       │       │         │       │        │
       ▼       ▼         ▼       ▼        ▼
     ["An"]   []     ["Bình"]    []     ["Chi"]
       └───────┴─────────┴───────┴────────┘
                  flatMap
                     ▼
             ["An", "Bình", "Chi"]
~~~

With a source having an **encounter order** like `List`, `flatMap(Optional::stream)` preserves the relative order of the remaining elements. If the original source is unordered, the result does not automatically gain an ordering guarantee either.

### Why Must We Use `flatMap` Instead of `map`?

~~~java
// Each Optional is converted into a sub-Stream:
var nested = maybeNames.stream()
    .map(Optional::stream); // Stream<Stream<String>>

// Sub-Streams are joined into one Stream of values:
var flattened = maybeNames.stream()
    .flatMap(Optional::stream); // Stream<String>
~~~

`map` maps **one input element to one output element**: here that output element is itself a `Stream<String>`. `flatMap` both maps to sub-Streams and flattens them. Therefore, the common pattern is:

~~~java
Stream<Optional<T>> input = /* multiple Optional results */;
Stream<T> output = input.flatMap(Optional::stream);
~~~

This example is a template; each `input` variable must be initialized with an actual data source. Do not write `map(Optional::stream).toList()` if the goal is to get a list of `T` values, because that produces a list of **sub-Streams**.

## 4. Combining with `map`, `filter`, and `collect` in Real Problems

Suppose a customer may not have provided an email yet. We want to build a list of valid emails from the available data.

~~~java
import java.util.List;
import java.util.Optional;

record Customer(String name, String email) {}

List<Customer> customers = List.of(
    new Customer("An", " an@example.com "),
    new Customer("Bình", null),
    new Customer("Chi", " "),
    new Customer("Dung", "dung@example.com")
);

List<String> emails = customers.stream()
    .map(customer -> Optional.ofNullable(customer.email())
        .map(String::trim)
        .filter(email -> !email.isBlank()))
    .flatMap(Optional::stream)
    .toList();

System.out.println(emails);
// [an@example.com, dung@example.com]
~~~

At the `map` step, each `Customer` produces an `Optional<String>`. A `null` email becomes `Optional.empty()` via `ofNullable`; a whitespace-only email is also filtered out via `filter` on the Optional. Next, `flatMap(Optional::stream)` drops empty Optionals and sends the remaining values into the same pipeline.

We can also move the lookup into a separate helper method. This separates the **data selection rule** from **how results are combined**:

~~~java
import java.util.Optional;

static Optional<String> normalizedEmail(Customer customer) {
    return Optional.ofNullable(customer.email())
        .map(String::trim)
        .filter(email -> !email.isBlank());
}

// In a method using the customers list:
List<String> emails = customers.stream()
    .map(customer -> normalizedEmail(customer))
    .flatMap(Optional::stream)
    .toList();
~~~

The snippet is an extension of the `Customer` example above: the `normalizedEmail` method must be declared inside the class containing the code that uses it. When a method already returns an Optional, combining `map(...).flatMap(Optional::stream)` avoids nested `if` blocks.

### Comparison with Using `isPresent()` and `get()`

Before Java 9, a common way to write this was:

~~~java
List<String> names = maybeNames.stream()
    .filter(Optional::isPresent)
    .map(Optional::get)
    .toList();
~~~

This approach can yield the same result if all Stream elements are non-`null` Optionals, but it has two separate steps and calls `get()`. Since Java 9, the intent can be written more clearly:

~~~java
List<String> names = maybeNames.stream()
    .flatMap(Optional::stream)
    .toList();
~~~

Do not call `get()` without checking presence; on an empty Optional, `get()` throws `NoSuchElementException`.

## 5. Complete Pipeline: Filtering Input IDs and Summing

A common scenario is converting untrusted string data into numeric values. A parse function returns `Optional<Integer>` because a string may be invalid or fail a condition.

The following example is a standalone compilable and runnable program in Java 17+:

~~~java
import java.util.List;
import java.util.Optional;

public class ParseIdsWithOptionalStream {
    static Optional<Integer> parsePositiveId(String raw) {
        if (raw == null) {
            return Optional.empty();
        }

        try {
            int id = Integer.parseInt(raw.trim());
            return id > 0 ? Optional.of(id) : Optional.empty();
        } catch (NumberFormatException ex) {
            return Optional.empty();
        }
    }

    public static void main(String[] args) {
        List<String> rawIds = List.of("12", "abc", "-5", " 7 ", "0", "30");

        List<Integer> validIds = rawIds.stream()
            .map(ParseIdsWithOptionalStream::parsePositiveId)
            .flatMap(Optional::stream)
            .toList();

        int total = validIds.stream()
            .mapToInt(Integer::intValue)
            .sum();

        System.out.println(validIds); // [12, 7, 30]
        System.out.println(total);    // 49
    }
}
~~~

In this problem:

- `map` converts each string into a possibly absent lookup/conversion result.
- `flatMap(Optional::stream)` keeps the successfully parsed positive integers.
- `toList` returns the list of results; `mapToInt(...).sum()` computes the sum via a separate terminal operation.

If only the sum is needed, you can keep everything in **a single pipeline**:

~~~java
int total = rawIds.stream()
    .map(ParseIdsWithOptionalStream::parsePositiveId)
    .flatMap(Optional::stream)
    .mapToInt(Integer::intValue)
    .sum(); // 49
~~~

Depending on business requirements, a failed parse result may need to be recorded as an error rather than automatically skipped. In that case, do not use `Optional.stream()` to silently drop all absent values; design a result type carrying the error reason or handle invalid data before collecting.

## 6. Distinguishing `Optional.stream()` from `Stream.ofNullable()` and `Optional.flatMap()`

All three methods are useful when dealing with possibly absent data, but their **inputs and outputs differ**.

| Method | Applies to | Result | Use when |
| --- | --- | --- | --- |
| `Optional<T>.stream()` | An `Optional<T>` | `Stream<T>` with 0 or 1 element | Want to feed an Optional into a Stream pipeline. |
| `Stream.ofNullable(value)` | A potentially `null` reference `T` | `Stream<T>` with 0 or 1 element | Direct data source may be `null`. |
| `Optional<T>.flatMap(f)` | An `Optional<T>` | `Optional<U>` | Want to chain Optional-returning lookups and **keep the result as an Optional**. |
| `Stream<T>.flatMap(f)` | A `Stream<T>` | `Stream<U>` | Want to join multiple sub-Streams into one Stream. |

### `Stream.ofNullable` Is for a Potentially `null` Reference

~~~java
import java.util.List;
import java.util.stream.Stream;

String nickname = null;

List<String> values = Stream.ofNullable(nickname).toList();
// []
~~~

`Stream.ofNullable` has also been available since Java 9. This method fits well when a legacy API returns `null`, whereas if you already have an `Optional<String>`, `optional.stream()` expresses it more directly without needing `orElse(null)`.

### `Optional.flatMap` Preserves the Optional Type

~~~java
import java.util.List;
import java.util.Optional;

record Profile(Optional<String> phone) {}

Optional<Profile> maybeProfile = Optional.of(
    new Profile(Optional.of("0900000000"))
);

Optional<String> maybePhone = maybeProfile.flatMap(Profile::phone);
// Optional containing "0900000000"

List<String> phones = maybePhone.stream().toList();
// ["0900000000"]
~~~

Here `Optional.flatMap` does not create a Stream: it chains two computations that return Optionals. Only when switching to a Stream pipeline do you use `Optional.stream()`.

## 7. Primitive Optionals Also Have `stream()`

Java has three specialized Optional types: `OptionalInt`, `OptionalLong`, and `OptionalDouble`. Since Java 9, these types also support `stream()`, returning the corresponding primitive stream.

| Input | Method | Return type |
| --- | --- | --- |
| `OptionalInt` | `stream()` | `IntStream` |
| `OptionalLong` | `stream()` | `LongStream` |
| `OptionalDouble` | `stream()` | `DoubleStream` |

Example of collecting measurements that might be missing:

~~~java
import java.util.List;
import java.util.OptionalInt;

List<OptionalInt> readings = List.of(
    OptionalInt.of(15),
    OptionalInt.empty(),
    OptionalInt.of(27),
    OptionalInt.of(8)
);

int sum = readings.stream()
    .flatMapToInt(OptionalInt::stream)
    .sum();

System.out.println(sum); // 50
~~~

Use `flatMapToInt` instead of `flatMap` because the sub-Streams have type `IntStream`. By the same principle, `Stream<OptionalLong>` can use `flatMapToLong(OptionalLong::stream)` and `Stream<OptionalDouble>` can use `flatMapToDouble(OptionalDouble::stream)`. This keeps data in primitive form, avoiding boxing each element into `Integer`, `Long`, or `Double`.

## 8. Combining with Lazy Pipelines, Terminal Operations, and Element Ordering

`Optional.stream()` creates a Stream, so the lifecycle rules of the Stream API still apply:

- `filter`, `map`, and `flatMap` are intermediate operations; the pipeline is usually processed **lazily** when a terminal operation is present.
- `toList`, `collect`, `count`, `sum`, and `findFirst` are common terminal operations.
- A Stream that has used a terminal operation cannot be reused; if another computation is needed, create a new Stream from the source or store the result in a collection.
- `findFirst`, `anyMatch`, and other short-circuiting operations can terminate early; do not put side effects inside an Optional-mapping function to reliably count how many elements were processed.

Example of finding the first valid email from the list in section 4:

~~~java
Optional<String> firstEmail = customers.stream()
    .map(customer -> Optional.ofNullable(customer.email())
        .map(String::trim)
        .filter(email -> !email.isBlank()))
    .flatMap(Optional::stream)
    .findFirst();

// Optional containing "an@example.com".
~~~

`findFirst()` returns `Optional<String>` because the pipeline might have no emails left after dropping empty Optionals. With an ordered source like `List`, the result is the first matching value in that order. The fact that a Stream is allowed to stop early is why you should not rely on how many times the `map` step executes to record business activity.

### Resources and Parallel Execution

`Optional.stream()` itself does not open files or connections, and contains at most one value. However, if the outer pipeline source is a Stream from a file or I/O resource, the responsibility of closing that resource remains; use `try-with-resources` when the source API requires it.

If the outer Stream runs in parallel, lookup operations producing Optionals must follow the **non-interference** and **stateless** contracts for lambdas used in the Stream API. The fact that `Optional.stream()` creates a 0–1 element stream does not make I/O calls, database updates, or shared-variable writes safe to parallelize. Only use parallel streams when the work is sufficiently large, independent, and shows measured gains.

## 9. Common Mistakes and Misconceptions

### Mistake 1: Thinking `Optional.stream()` Automatically Flattens the Whole Collection

~~~java
List<Optional<Integer>> items = List.of(
    Optional.of(1), Optional.empty(), Optional.of(3)
);

// WRONG GOAL: creates Stream<Stream<Integer>>.
var nested = items.stream().map(Optional::stream);

// RIGHT: creates Stream<Integer>, which can then be collected.
List<Integer> values = items.stream()
    .flatMap(Optional::stream)
    .toList(); // [1, 3]
~~~

### Mistake 2: Returning `null` Instead of `Optional.empty()`

~~~java
// Do not write a method like this:
// Optional<String> lookup(int id) {
//     return id > 0 ? Optional.of("ok") : null;
// }

// A method returning Optional must return an actual Optional:
static Optional<String> lookup(int id) {
    return id > 0 ? Optional.of("ok") : Optional.empty();
}
~~~

`Optional.stream()` handles an **empty Optional**, not a **null Optional reference**. If an element of `Stream<Optional<T>>` is `null`, `flatMap(Optional::stream)` will throw `NullPointerException` when calling the method on that element. The proper API-level fix is to uphold the contract of returning a real Optional.

### Mistake 3: Treating Missing Data and Erroneous Data as Equivalent

`flatMap(Optional::stream)` discards `Optional.empty()` results. This is the right behavior when business logic permits skipping missing values (e.g., collecting only emails that were provided). However, if a missing price must report an error to prevent checkout, automatically filtering out the order line is a logic bug.

For example, when failing to find a product price must **halt processing**:

~~~java
import java.util.Map;

Map<String, Long> prices = Map.of(
    "BOOK", 100_000L,
    "PEN", 10_000L
);

List<String> skus = List.of("BOOK", "UNKNOWN", "PEN");

// In this problem, a missing price is an error rather than a skippable value:
List<Long> requiredPrices = skus.stream()
    .map(sku -> Optional.ofNullable(prices.get(sku))
        .orElseThrow(() -> new IllegalArgumentException("Missing price: " + sku)))
    .toList();

// Throws IllegalArgumentException at SKU "UNKNOWN".
~~~

Therefore, before flattening, ask: **Does an empty Optional mean this element is allowed to be skipped?** If the answer is no, handle the error where it occurs or retain the missing information for reporting.

### Mistake 4: Expecting `toList()` to Be a Modifiable List

Since Java 16, `Stream.toList()` returns an unmodifiable list. Thus:

~~~java
List<String> selected = maybeNames.stream()
    .flatMap(Optional::stream)
    .toList();

// selected.add("Dung"); // UnsupportedOperationException.
~~~

If you need to modify the result, use a collector that creates a mutable collection:

~~~java
import java.util.ArrayList;
import java.util.stream.Collectors;

ArrayList<String> mutable = maybeNames.stream()
    .flatMap(Optional::stream)
    .collect(Collectors.toCollection(ArrayList::new));

mutable.add("Dung"); // Valid.
~~~

## 10. When Should You Use `Optional.stream()`?

| Scenario | Suitable approach | Reason |
| --- | --- | --- |
| A query may return no result | `maybeValue.stream()` | Feeds the 0–1 value case into a Stream. |
| List of `Optional<T>` | `list.stream().flatMap(Optional::stream)` | Collects present values into one Stream. |
| Each element needs an optional lookup | `source.stream().map(this::lookup).flatMap(Optional::stream)` | Combines querying and dropping absent values. |
| A Java reference that might be `null` | `Stream.ofNullable(value)` | Creates a 0–1 Stream directly from the reference. |
| Result is `OptionalInt` | `flatMapToInt(OptionalInt::stream)` | Processes integers with a primitive stream. |
| Missing value is a business error | `orElseThrow(...)` or an error-carrying result type | Do not silently drop required data. |

## 11. Self-Check Questions

1. **What does `Optional.empty().stream().count()` return?** Returns `0` because the Stream has no elements.
2. **What type does `Optional.of(42).stream().findFirst()` return?** Returns `Optional<Integer>` containing `42`.
3. **Why is `map(Optional::stream)` not enough to collect the values?** Because the result of `map` is `Stream<Stream<T>>`; use `flatMap` to concatenate the sub-Streams.
4. **When do you use `flatMapToInt(OptionalInt::stream)`?** When the input is `Stream<OptionalInt>` and you want an `IntStream` to compute with primitive types.
5. **Should you use `Optional.stream()` to drop a checkout item whose price was not found?** No, if a missing price is an error to report; flattening removes that item from the result without carrying the reason.
6. **Does using `Optional.stream()` mean the source Stream will automatically close I/O resources?** No; you still need to manage the lifecycle of resource-backed sources, for example with `try-with-resources`.

**Key takeaway:** `Optional.stream()` bridges Optional's **0 or 1 value** model with Stream's **0 to many elements** model. With multiple Optionals, the most important recipe is `streamOfOptionals.flatMap(Optional::stream)`. Combined with `filter`, `map`, `reduce`, or `collect`, this recipe makes declarative pipelines clear and retains only actually present values, provided business rules allow skipping absent ones.
