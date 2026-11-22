# Flattening `Optional` and Eliminating Absent Results

In the Java Stream API, not every transformation produces a valid value. When looking up accounts, parsing numeric strings, reading configuration, or selecting records matching a condition, an input element may yield **one result** or **no result**. `Optional<T>` describes that case without forcing code readers to treat `null` as the signal of absence.

This lesson belongs to the **Filtering and Transforming Elements** chapter of the `JAVA_STREAM_API` module. The focus is combining lazy pipelines with `Optional`: mapping each element to `Optional<T>`, flattening present results via `flatMap(Optional::stream)`, and continuing processing with `filter`, `map`, `reduce`, or `collect`. Beyond syntax, you must understand post-transformation element counts, ordering, pipeline lifecycle, JDK versions, and the boundary between absent data and invalid data.

## 1. Why Flatten `Optional` Inside a Stream?

Suppose you have three strings `"12"`, `"không-phải-số"`, and `"7"`. A function converting strings to integers may return `Optional<Integer>`:

- `Optional.of(12)` when parsing succeeds;
- `Optional.empty()` when the string is not a number;
- `Optional.of(7)` when parsing succeeds.

If you use `map` to invoke the function, you get a **Stream containing Optionals**, i.e., `Stream<Optional<Integer>>`. That still has three elements, including the one representing failure. To drop empty Optionals and continue processing integers, you need to turn each Optional into a Stream of **0 or 1** element and flatten it:

```text
Stream<String>
 ["12", "không-phải-số", "7"]
            │ map(parseInteger)
            ▼
Stream<Optional<Integer>>
 [Optional[12], Optional.empty, Optional[7]]
            │ flatMap(Optional::stream)
            ▼
Stream<Integer>
 [12, 7]
            │ filter / map / collect / sum ...
            ▼
Result containing only present values
```

`Optional.stream()`, introduced in **Java 9**, is this bridge. If the Optional contains a value, it returns a Stream of that single value; if the Optional is empty, it returns an empty Stream.

```java
import java.util.Optional;
import java.util.stream.Stream;

Optional<String> present = Optional.of("hello");
Optional<String> absent = Optional.empty();

System.out.println(present.stream().count()); // 1
System.out.println(absent.stream().count());  // 0
```

Comparison table of operations:

| Expression | Result type | Meaning |
| --- | --- | --- |
| `Stream<T>.map(T -> Optional<R>)` | `Stream<Optional<R>>` | Every input still produces an Optional |
| `Optional<R>.stream()` | `Stream<R>` | One Optional turns into 0 or 1 element |
| `Stream<Optional<R>>.flatMap(Optional::stream)` | `Stream<R>` | Drops empty Optionals and extracts present values |
| `Stream<T>.flatMap(T -> Stream<R>)` | `Stream<R>` | Each input can produce 0, 1, or many elements |
| `Optional<T>.flatMap(T -> Optional<R>)` | `Optional<R>` | Chains transformations **inside one Optional**, avoiding nested Optionals |

The two methods named `flatMap` have different receivers: `Stream.flatMap` flattens sub-Streams, whereas `Optional.flatMap` flattens nested Optionals.

## 2. End-to-End Example: Parsing Numeric Strings

First, write a safe conversion function. This is an example where **a non-numeric string is treated as having no result**, not a system error.

```java
import java.util.Optional;

static Optional<Integer> parseInteger(String text) {
    try {
        return Optional.of(Integer.parseInt(text));
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}
```

`Integer.parseInt` also throws `NumberFormatException` when the input is `null`. In this example, `null` does not appear in the input list; if an API can receive `null`, define clearly whether that is a caller error or an input allowed to be skipped.

Combining with Stream:

```java
import java.util.Arrays;
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

List<String> inputs = Arrays.asList("12", "x", "-3", "7");

List<Integer> numbers = inputs.stream()
        .map(YourClass::parseInteger)
        .flatMap(Optional::stream)
        .collect(Collectors.toList());

System.out.println(numbers); // [12, -3, 7]
```

`YourClass::parseInteger` is an example class name: place `parseInteger` in your class and replace `YourClass` with the actual class name, or use the lambda `text -> parseInteger(text)` in the same scope.

Each step has a distinct role:

1. `inputs.stream()` creates an encounter-ordered source from the `List`.
2. `map(...)` converts **each string** into `Optional<Integer>`; `"x"` produces `Optional.empty()`.
3. `flatMap(Optional::stream)` drops empty Optionals and emits present numbers.
4. `collect(...)` is the terminal operation, triggering execution and storing results in a list.

After `flatMap`, the remainder of the pipeline works directly with `Integer`, not with `Optional<Integer>`. Filtering does not disturb the encounter order of the input list.

### Converting to a Primitive Stream for Calculations

```java
int total = inputs.stream()
        .map(text -> parseInteger(text))
        .flatMap(Optional::stream)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 16 (12 + -3 + 7)
```

`mapToInt` converts `Stream<Integer>` to `IntStream`, allowing calls to `sum`, `average`, and `summaryStatistics` without writing `reduce` on boxed `Integer`.

It can be written more concisely when the conversion method is in the same class:

```java
long countValid = inputs.stream()
        .map(text -> parseInteger(text))
        .flatMap(Optional::stream)
        .count();

System.out.println(countValid); // 3
```

Here `countValid` counts **successfully parsed values**, not the number of initial strings.

## 3. Combining `map` and `flatMap` During Data Lookups

A business-oriented example: an order stores a customer ID; lookup may fail because the ID does not exist. The repository method returns `Optional<Customer>`:

```java
// record has been officially supported since Java 16.
record Order(String customerId, long amount) {}
record Customer(String id, String email) {}

interface CustomerRepository {
    Optional<Customer> findById(String id);
}
```

Fetch emails of customers that actually exist:

```java
List<Order> orders = List.of(
        new Order("c01", 100),
        new Order("unknown", 200),
        new Order("c03", 150)
);

// repo is an initialized CustomerRepository.
List<String> emails = orders.stream()
        .map(order -> repo.findById(order.customerId()))
        .flatMap(Optional::stream)
        .map(Customer::email)
        .toList();
```

In this example:

- `map` turns each `Order` into `Optional<Customer>`.
- `flatMap` drops lookups where the customer was not found.
- `map(Customer::email)` only receives valid `Customer`s, so no `isPresent()` or `get()` is needed.
- `toList()` has been available since **Java 16**, returning an unmodifiable list. When using Java 8–15, replace with `collect(Collectors.toList())` if needed.

If the lookup hits a database per order, the number of calls can still be large (*N+1 queries*). `flatMap(Optional::stream)` only solves data shape; it does **not** automatically optimize I/O query counts. For large order lists, consider batch loading or joining at the source.

### Dropping Absent Data Then Continuing to Filter

Suppose you only need emails of customers ending with `@example.org`:

```java
List<String> emails = orders.stream()
        .map(order -> repo.findById(order.customerId()))
        .flatMap(Optional::stream)
        .map(Customer::email)
        .filter(email -> email.endsWith("@example.org"))
        .toList();
```

The business expression order is very clear: look up → drop absent results → extract email → filter email. This is a major benefit of **flattening early**, instead of carrying `Optional` through many downstream processing steps.

## 4. Avoiding Nested Optionals: `Optional.flatMap` and `Stream.flatMap`

Two layers of Optional can occur when the input is already `Optional<T>` and the transformation function also returns `Optional<R>`:

```java
Optional<String> raw = Optional.of("42");

// map produces Optional<Optional<Integer>>:
Optional<Optional<Integer>> nested = raw.map(
        text -> parseInteger(text)
);

// flatMap on Optional avoids creating a nested layer:
Optional<Integer> parsed = raw.flatMap(
        text -> parseInteger(text)
);
```

`Optional.flatMap` (Java 8) fits when you are handling **a single optional value**. `Stream.flatMap(Optional::stream)` (Java 9+) fits when you have **multiple optional values** in a pipeline.

Combining two levels in a real-world problem:

```java
record Profile(Optional<String> phone) {}
record Account(String id, Optional<Profile> profile) {}

List<Account> accounts = List.of(
        new Account("u01", Optional.of(
                new Profile(Optional.of("0900000001"))
        )),
        new Account("u02", Optional.empty()),
        new Account("u03", Optional.of(
                new Profile(Optional.empty())
        ))
);

List<String> phones = accounts.stream()
        .map(Account::profile)                 // Stream<Optional<Profile>>
        .flatMap(Optional::stream)             // Stream<Profile>
        .map(Profile::phone)                   // Stream<Optional<String>>
        .flatMap(Optional::stream)             // Stream<String>
        .toList();

System.out.println(phones); // [0900000001]
```

When there are multiple levels of potentially absent values, repeating the `map` + `flatMap(Optional::stream)` pair for each level is easier to understand than calling `get()` where `Optional.empty()` could arrive.

If the data is only **one** account, there is no need to create a Stream:

```java
Optional<String> phone = accounts.get(0)
        .profile()
        .flatMap(Profile::phone);
```

Here `Profile::phone` returns `Optional<String>`, so `Optional.flatMap` is used to avoid getting `Optional<Optional<String>>`.

## 5. Distinguishing `Optional.empty`, `null`, and Empty Streams

The three states below are related but not identical.

| Data form | Value representing absence | How to handle |
| --- | --- | --- |
| `Optional<T>` | `Optional.empty()` | `optional.stream()` produces an empty Stream |
| Nullable `T` | `null` | `Stream.ofNullable(value)` or `filter(Objects::nonNull)` |
| `Stream<T>` | `Stream.empty()` | Already an empty Stream; can be concatenated or flattened directly |

### `Optional.ofNullable` Handles `null` at the Input

```java
import java.util.Optional;
import java.util.stream.Stream;

String email = null;

Optional<String> maybeEmail = Optional.ofNullable(email);
System.out.println(maybeEmail.isPresent()); // false

long count = maybeEmail.stream().count();
System.out.println(count); // 0
```

`Optional.of(nonNullValue)` creates a populated Optional; `Optional.of(null)` throws `NullPointerException`. `Optional.ofNullable(value)` creates an empty Optional when `value == null`.

Note: an `Optional` itself must be a **non-null object**. Never represent an empty Optional by returning `null` from a method declared to return `Optional<T>`. If a Stream actually contains a `null` element where an Optional is expected, `flatMap(Optional::stream)` can throw `NullPointerException`.

### When Input Is a Nullable Value, `Stream.ofNullable` Can Be Used

Since Java 9, `Stream.ofNullable(value)` returns a single-element Stream if `value != null`, or an empty Stream if `value == null`:

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Stream;

List<String> names = Arrays.asList("An", null, "Chi");

List<String> presentNames = names.stream()
        .flatMap(Stream::ofNullable)
        .toList();

System.out.println(presentNames); // [An, Chi]
```

This problem does not need to allocate an `Optional` for every name; the input is already a nullable value. When an API already publicly returns `Optional<T>`, using `Optional::stream` matches the contract.

If you only want to drop `null`, the familiar way since Java 8 is:

```java
import java.util.Objects;

List<String> filtered = names.stream()
        .filter(Objects::nonNull)
        .collect(Collectors.toList());
```

Do not confuse `Optional.empty()` with a `null` value **inside a Stream**. For instance, `Stream<Optional<T>>` has an element that is `Optional.empty()`; filtering with `Objects::nonNull` **does not remove** that element because the Optional object itself is non-null.

## 6. What If `Optional.stream` Is Unavailable on Java 8?

`Optional` existed in **Java 8**, but `Optional.stream()` only appeared in **Java 9**. If a project runs on Java 8, there are two equivalent ways to drop empty Optionals.

**Approach 1: filter then extract the value.**

```java
import java.util.Optional;
import java.util.stream.Collectors;

List<Integer> valid = inputs.stream()
        .map(text -> parseInteger(text))
        .filter(Optional::isPresent)
        .map(Optional::get)
        .collect(Collectors.toList());
```

This pattern is safe because `get()` is only called **after** `isPresent` on the same pipeline. However, if steps are split or reordered without the filter condition, `get()` will throw `NoSuchElementException` on an empty Optional. From Java 9 onward, `flatMap(Optional::stream)` is shorter and less error-prone.

**Approach 2: convert `Optional` to a `Stream` via a lambda.**

```java
List<Integer> valid = inputs.stream()
        .map(text -> parseInteger(text))
        .flatMap(opt -> opt
                .map(Stream::of)
                .orElseGet(Stream::empty))
        .collect(Collectors.toList());
```

This is the Java 8 idiom equivalent in idea to `Optional::stream`: if present, create a single-element Stream; if absent, use an empty Stream.

Never write `.map(Optional::get)` directly on `Stream<Optional<T>>` without first filtering out empty Optionals. Also do not use `.map(Optional::orElse(null))` just to turn absent results into null: that reintroduces the need for null checks in subsequent steps.

## 7. `OptionalInt`, `OptionalLong`, `OptionalDouble`, and Primitive Streams

When processing large amounts of ints, longs, or doubles, Java provides `OptionalInt`, `OptionalLong`, and `OptionalDouble`. Since Java 9, they also have `stream()`, returning `IntStream`, `LongStream`, and `DoubleStream` respectively.

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

static OptionalInt parseNonNegative(String text) {
    try {
        int value = Integer.parseInt(text);
        return value >= 0
                ? OptionalInt.of(value)
                : OptionalInt.empty();
    } catch (NumberFormatException ex) {
        return OptionalInt.empty();
    }
}

int total = Stream.of("10", "bad", "-5", "7")
        .map(text -> parseNonNegative(text))
        .flatMapToInt(OptionalInt::stream)
        .sum();

System.out.println(total); // 17
```

Here `map` produces `Stream<OptionalInt>`, while `flatMapToInt` drops empty `OptionalInt`s and produces an `IntStream`. Use `flatMapToLong(OptionalLong::stream)` or `flatMapToDouble(OptionalDouble::stream)` by the same principle.

When data sources and computations can stay primitive end-to-end, primitive Streams can reduce boxing/unboxing compared to `Stream<Integer>` or `Stream<Double>`. That is a data-type and performance choice; it does not change the rule for dropping absent results.

## 8. Alternative: `mapMulti` from Java 16

`Stream.mapMulti`, available since **Java 16**, lets an input element invoke a `Consumer` to emit 0, 1, or more elements. With `Optional`, you can emit the present value directly without creating a sub-Stream:

```java
import java.util.Optional;
import java.util.stream.Stream;

List<Integer> numbers = Stream.of(
        Optional.of(3),
        Optional.<Integer>empty(),
        Optional.of(8)
).<Integer>mapMulti((maybe, downstream) ->
        maybe.ifPresent(downstream)
).toList();

System.out.println(numbers); // [3, 8]
```

`mapMulti` is especially useful when a transformation emits few elements or depends on conditions and you want to avoid creating many sub-Streams. However, when the task is simply dropping `Optional.empty()`, `flatMap(Optional::stream)` is usually the most concise, direct, and recognizable expression.

| Technique | Minimum JDK | Advantage | When to choose |
| --- | --- | --- | --- |
| `filter(Optional::isPresent).map(Optional::get)` | 8 | Compatible with older projects | Need Java 8 |
| `flatMap(opt -> opt.map(Stream::of).orElseGet(Stream::empty))` | 8 | Preserves 0/1 Stream thinking | Need Java 8 but prefer flattening style |
| `flatMap(Optional::stream)` | 9 | Concise, directly expresses dropping empty Optionals | Common choice from Java 9+ |
| `mapMulti((opt, out) -> opt.ifPresent(out))` | 16 | Emits values directly, flexible | Have Java 16+, need multiple emission branches |

There is no rule that one technique is always fastest. In pipelines doing I/O or database queries, time may be dominated by the data source; measure on realistic workloads before optimizing an implementation detail.

## 9. Lazy Behavior, Ordering, and Common Pitfalls

`map` and `flatMap` are intermediate operations, evaluated *lazily* in principle: declaring a pipeline does not immediately invoke `parseInteger` on all data. A terminal operation triggers processing; short-circuiting operators can stop early.

```java
List<String> inputs = List.of("bad", "12", "x", "7", "99");

Optional<Integer> firstValid = inputs.stream()
        .map(text -> parseInteger(text))
        .flatMap(Optional::stream)
        .findFirst();

System.out.println(firstValid); // Optional[12]
```

In a sequential pipeline from an encounter-ordered `List`, `findFirst()` returns the first valid number. Strings after `"12"` do not need to be parsed to return the result. However, Stream execution can vary depending on source characteristics, stateful operations, and parallelism; do not use transformation functions with side effects such as incrementing shared variables, writing important data, or mutating the source structure.

### Filtering Drops Data: Know the Reason

`Optional.empty()` cannot distinguish between "not found", "invalid", and "access denied" if all are mapped to empty. Only use an empty Optional to drop elements when that removal is **intended business behavior**.

For example, `parseInteger` treats `NumberFormatException` as an invalid string, whereas a database connection failure in `findById` should not necessarily be turned into `Optional.empty()`. If you need to count or display failure reasons, use a result model that classifies errors (such as a custom `Result` type), or record error counts/skipped cases explicitly outside the pipeline. Do not abuse `peek` or mutate shared counters as a primary logging mechanism, especially under parallel execution.

### Common Mistakes Table

| Pattern or assumption | Why it is wrong or error-prone | How to fix |
| --- | --- | --- |
| `stream.map(parse).map(Optional::get)` | May call `get()` on an empty Optional | Use `flatMap(Optional::stream)` |
| `stream.filter(Objects::nonNull)` on `Stream<Optional<T>>` | Does not remove `Optional.empty()` | Flatten the Optional |
| `stream.map(Optional::stream)` | Produces `Stream<Stream<T>>`, not flat data | Use `flatMap` |
| `opt.map(this::lookup)` where `lookup` returns Optional | Creates an Optional nested inside an Optional | Use `Optional.flatMap` |
| Function returns `null` instead of `Optional.empty()` | Breaks the Optional return contract and can cause NPE | Always return a non-null Optional |
| Using `Optional::stream` on Java 8 | Method does not exist in Java 8 | Use Java 8 fallback |
| Assuming dropped elements are safely ignored errors | May hide business or system failures | Distinguish expected absence from failures needing handling |
| Using `forEach` in parallel and expecting order | `forEach` does not guarantee encounter order | Use `forEachOrdered` if order is required |
| Reusing a `Stream` after a terminal operation | Pipelines are single-use | Create a new Stream from the source to run again |

`flatMap(Optional::stream)` does not automatically close external resources other than the sub-Streams it manages itself. If the outer source is `Files.lines`, `Files.walk`, or an I/O Stream that requires closing, still use `try-with-resources` on the **outer source Stream**. Terminal operations like `collect` or `findFirst` do not automatically close source resources.

## 10. Comprehensive Example: Filtering Valid Quantities and Summing

Suppose a simple CSV file has a first column containing text quantities. The rule for this example: only accept positive integers; blank lines and non-numeric data are dropped per business requirements. Below, input is simulated with a `List` to focus on the pipeline:

```java
import java.util.List;
import java.util.Optional;
import java.util.stream.Collectors;

static Optional<Integer> positiveInteger(String text) {
    try {
        int value = Integer.parseInt(text.trim());
        return value > 0 ? Optional.of(value) : Optional.empty();
    } catch (NumberFormatException ex) {
        return Optional.empty();
    }
}

List<String> quantities = List.of(" 6 ", "unknown", "-2", "3", "0", "11");

List<Integer> accepted = quantities.stream()
        .map(text -> positiveInteger(text))
        .flatMap(Optional::stream)
        .collect(Collectors.toList());

int sum = accepted.stream().mapToInt(Integer::intValue).sum();

System.out.println(accepted); // [6, 3, 11]
System.out.println(sum);      // 20
```

`Optional.empty()` is used for an intentional filtering rule: dropping values that are not positive integers. When the goal is only computing the sum, you can avoid creating the intermediate list:

```java
int total = quantities.stream()
        .map(text -> positiveInteger(text))
        .flatMap(Optional::stream)
        .mapToInt(Integer::intValue)
        .sum();

System.out.println(total); // 20
```

If you need **both** the valid list and the sum, the first example stores `accepted` and runs multiple operations on `accepted.stream()`; that creates a fresh Stream from the List for each use, rather than reusing a consumed pipeline. If the initial source is a single-pass file-reading Stream, consider computing statistics in the same pass or storing needed data within an appropriate memory budget.

## 11. Self-Check Questions

1. What does `Stream.of(Optional.of(1), Optional.empty(), Optional.of(2)).flatMap(Optional::stream).count()` return? **2**, because empty Optionals produce no elements.
2. Why is `map(Optional::stream)` not enough? Because it produces a **Stream of Streams**; `flatMap` is needed to produce a flat Stream.
3. How does `Optional.flatMap` differ from `Stream.flatMap`? One flattens **an Optional inside an Optional**, while the other flattens **sub-Streams inside a Stream**.
4. Can `flatMap(Optional::stream)` be used on Java 8? **No**; use `filter(isPresent).map(get)` or a lambda creating a 0/1 Stream.
5. Does `Objects::nonNull` remove `Optional.empty()`? **No**, `Optional.empty` is still a non-null object.
6. After `flatMap(Optional::stream)`, what type does `findFirst` return? **`Optional<T>`**, because `findFirst` is a terminal operation expressing a potentially absent result of the whole Stream.
7. How do you convert `Stream<OptionalInt>` to a primitive Stream? **`flatMapToInt(OptionalInt::stream)`** on Java 9+.
8. When should you preserve error details instead of skipping with `Optional.empty()`? When the caller needs to know **why** data failed or when the error requires intervention.

**Guiding Principle:** When each input can produce 0 or 1 result, represent intentional absence with `Optional<T>` and use `map(...).flatMap(Optional::stream)` to turn `Stream<T>` into `Stream<R>` containing only valid values. Keep clear boundaries between absent data, reportable errors, and closable resources; that clarity matters more than shortening a line of code.
