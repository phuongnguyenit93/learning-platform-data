# `OptionalInt`, `OptionalLong`, and `OptionalDouble` in Java

When processing data with `IntStream`, `LongStream`, and `DoubleStream`, some operations such as `min()`, `max()`, `average()`, `findFirst()`, and `findAny()` do not always have a result. A stream can be **empty**, so Java uses `OptionalInt`, `OptionalLong`, and `OptionalDouble` to explicitly represent either “a primitive value is present” or “no value is present”.

These three types belong to the `java.util` package and were introduced in Java 8. They are similar to `Optional<T>` in expressing optionality, but are specialized for `int`, `long`, and `double`. This lesson covers how to create, retrieve, convert, and safely use these types, especially in **primitive stream terminal operations**.

## 1. Why do primitive streams return primitive Optionals?

Consider these sources:

```java
IntStream.of(3, 8, 5).max(); // Result: 8.
IntStream.empty().max();    // No maximum value.
```

This is an illustrative snippet requiring `import java.util.stream.IntStream;`. On an empty stream, a “maximum value” does not exist; using `0`, `-1`, or `Integer.MIN_VALUE` as a default result directly in the API could be misleading, because those exact numbers can also be valid data.

`OptionalInt` has two states:

- **Present:** holds an actual `int` value, including `0`, negative numbers, and `Integer.MIN_VALUE`.
- **Empty:** holds no value; not synonymous with `0`.

Similarly, `OptionalLong` holds a `long`, and `OptionalDouble` holds a `double`. A present `OptionalDouble` can hold `0.0`, `-0.0`, `Double.NaN`, or infinity: these are still **values**, not the empty state.

| Type | Stores value of type | Retrieve value | Create present | Create empty |
| --- | --- | --- | --- | --- |
| `OptionalInt` | `int` | `getAsInt()` | `OptionalInt.of(10)` | `OptionalInt.empty()` |
| `OptionalLong` | `long` | `getAsLong()` | `OptionalLong.of(10L)` | `OptionalLong.empty()` |
| `OptionalDouble` | `double` | `getAsDouble()` | `OptionalDouble.of(2.5)` | `OptionalDouble.empty()` |

There is no `OptionalFloat`, `OptionalByte`, `OptionalShort`, or `OptionalChar` in Java SE. When you need those types, choose an appropriate API and representation rather than assuming Java provides every specialization.

## 2. Which terminal operations produce which types?

On `IntStream`:

| Operation | Return type | When stream is empty |
| --- | --- | --- |
| `min()` | `OptionalInt` | Empty |
| `max()` | `OptionalInt` | Empty |
| `findFirst()` | `OptionalInt` | Empty |
| `findAny()` | `OptionalInt` | Empty |
| `average()` | `OptionalDouble` | Empty |
| `sum()` | `int` | `0` |
| `count()` | `long` | `0L` |

`LongStream` has `min()`, `max()`, `findFirst()`, and `findAny()` returning `OptionalLong`; `average()` still returns **`OptionalDouble`** because an average can have a fractional part. `DoubleStream` uses `OptionalDouble` for all of `min()`, `max()`, `findFirst()`, `findAny()`, and `average()`.

`sum()` and `count()` have well-defined identity values for an empty stream: the sum is 0 and the count is 0. In contrast, `min()`, `max()`, and `average()` cannot pick a single universal finite value to mean “no result” across all datasets.

Example:

```java
int sum = IntStream.empty().sum();                // 0
long count = IntStream.empty().count();           // 0L
OptionalDouble avg = IntStream.empty().average(); // OptionalDouble.empty()
```

This is an illustrative snippet placed inside a method, using `java.util.OptionalDouble` and `java.util.stream.IntStream`. Do not confuse the **average of an empty set** with `0.0`.

## 3. A compilable and runnable Java 17+ program

Save as `PrimitiveOptionalDemo.java`:

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

public class PrimitiveOptionalDemo {
    public static void main(String[] args) {
        OptionalInt max = IntStream.of(12, 7, 19).max();
        OptionalLong first = LongStream.empty().findFirst();
        OptionalDouble average =
                DoubleStream.of(2.0, 4.0, 6.0).average();

        System.out.println("max present = " + max.isPresent());
        System.out.println("max = " + max.orElse(-1));
        System.out.println("first present = " + first.isPresent());
        System.out.println("first fallback = " + first.orElse(100L));
        System.out.println("average = " + average.orElseThrow());

        OptionalDouble intAverage = IntStream.of(1, 2).average();
        System.out.println("int average = " + intAverage.orElseThrow());

        OptionalInt noMinimum = IntStream.empty().min();
        System.out.println("empty fallback = " + noMinimum.orElse(99));

        max.ifPresent(n -> System.out.println("ifPresent = " + n));

        noMinimum.ifPresentOrElse(
                n -> System.out.println("minimum = " + n),
                () -> System.out.println("minimum absent")
        );

        System.out.println("mapped stream = " +
                max.stream()
                        .map(n -> n * 2)
                        .boxed()
                        .toList());

        OptionalDouble nanValue =
                DoubleStream.of(Double.NaN).findFirst();
        System.out.println("NaN present = " + nanValue.isPresent());
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac -encoding UTF-8 PrimitiveOptionalDemo.java
java PrimitiveOptionalDemo
```

**Deterministic** stdout:

```text
max present = true
max = 19
first present = false
first fallback = 100
average = 4.0
int average = 1.5
empty fallback = 99
ifPresent = 19
minimum absent
mapped stream = [38]
NaN present = true
```

Point-by-point explanation:

1. `max()` finds the largest integer `19`, so `OptionalInt` is present and `orElse(-1)` returns `19`.
2. `LongStream.empty().findFirst()` has no elements: `OptionalLong` is empty, `isPresent()` is `false`, and `orElse(100L)` provides the fallback value.
3. `DoubleStream.average()` of `2.0, 4.0, 6.0` is `4.0`; `IntStream.average()` of `1, 2` is `1.5`, because the average result is a `double`.
4. `noMinimum` is empty, so `orElse(99)` returns `99`; `ifPresentOrElse` runs the second `Runnable` branch.
5. `max.stream()` converts a present `OptionalInt` into a single-element `IntStream`. `map(n -> n * 2)` produces `38`, `boxed()` converts it to `Stream<Integer>`, and `toList()` contains `[38]`.
6. `Double.NaN` is **a present `double` value**, so `OptionalDouble.of(Double.NaN)` or the corresponding `findFirst()` result still has `isPresent() == true`.

## 4. How to retrieve values safely

Key methods:

| API | Behavior when present | Behavior when empty |
| --- | --- | --- |
| `isPresent()` | `true` | `false` |
| `isEmpty()` (Java 11+) | `false` | `true` |
| `getAsInt()`, `getAsLong()`, `getAsDouble()` | Returns the corresponding primitive | Throws `NoSuchElementException` |
| `orElse(defaultValue)` | Returns the present value | Returns the fallback value |
| `orElseGet(supplier)` | Returns the present value | Calls the supplier to produce a value |
| `orElseThrow()` (Java 10+) | Returns the present value | Throws `NoSuchElementException` |
| `orElseThrow(exceptionSupplier)` | Returns the present value | Throws the exception created by the supplier |
| `ifPresent(action)` | Invokes action with the value | Does nothing |
| `ifPresentOrElse(action, emptyAction)` (Java 9+) | Invokes action | Invokes emptyAction |
| `stream()` (Java 9+) | Primitive stream with one element | Empty primitive stream |

For `OptionalLong` and `OptionalDouble`, the suppliers/actions use the corresponding primitive functional types, such as `LongSupplier`, `DoubleSupplier`, `LongConsumer`, and `DoubleConsumer`. This avoids using `Long`/`Double` wrappers just to pass values.

### Do not call `getAsX()` without checking

```java
OptionalInt count = OptionalInt.empty();
int value = count.getAsInt(); // Throws NoSuchElementException!
```

This is an illustrative **mistake to avoid**, using `import java.util.OptionalInt;`. Do not use `getAsInt()` just thinking “it can default to 0”. If missing data is a valid case, choose `orElse`, `orElseGet`, or `ifPresentOrElse`; if missing data is an error, `orElseThrow` is more appropriate.

### `orElse` vs. `orElseGet`

```java
OptionalInt found = OptionalInt.of(10);

int a = found.orElse(0);       // 10
int b = found.orElseGet(() -> computeDefault()); // 10
```

The snippet above is **illustrative code** inside a method where `computeDefault()` returns `int`. With `orElseGet`, the supplier is only invoked when the optional is empty. With `orElse(value)`, **the expression computing the value argument is evaluated before calling the method**, even when the optional is present.

Example of the difference:

```java
int first = found.orElse(expensiveFallback());
int second = found.orElseGet(() -> expensiveFallback());
```

If `found` is present, the `expensiveFallback()` call in the first expression **still runs**; in the second expression, it **does not run**. This is why `orElseGet` is usually preferred when the fallback is expensive, performs I/O, or has side effects. For a constant like `0`, `-1`, or `0.0`, `orElse` is simple and clear.

### Specify context-appropriate errors with `orElseThrow`

```java
int largest = IntStream.of(4, 9, 2)
        .max()
        .orElseThrow(() -> new IllegalStateException("Không có dữ liệu"));
```

This is an illustrative snippet inside a method with `import java.util.stream.IntStream;`. If there are no elements, the caller receives a clear, meaningful exception. If data can legitimately be empty according to business rules, do not turn the empty state into an unnecessary error.

## 5. “No value” is different from “value equals 0”

A common design mistake is using a **sentinel** to signal absence:

```java
// Easy to confuse: -1 can be an actual data value!
int smallest = IntStream.of(-1, 0, 3).min().orElse(-1);
```

The snippet above is illustrative; both the case **with result `-1`** and **with no result** can set the `smallest` variable to `-1`. If the application needs to distinguish them, keep the `OptionalInt`:

```java
OptionalInt smallest = IntStream.of(-1, 0, 3).min();

if (smallest.isPresent()) {
    System.out.println("min = " + smallest.getAsInt());
} else {
    System.out.println("Không có phần tử");
}
```

This is an illustrative snippet with `import java.util.OptionalInt;` and `java.util.stream.IntStream;`. Calling `getAsInt()` inside the `if` branch is safe because `isPresent()` has already been checked.

For floating-point numbers, you should not implicitly use `Double.NaN` to mean “no result”: `NaN` is an actual value that can appear in a `DoubleStream`. `OptionalDouble.empty()` explicitly represents absence, whereas `OptionalDouble.of(Double.NaN)` is present.

## 6. `OptionalDouble` is especially useful for averages

This is the case that is most often confused:

```java
OptionalDouble average = IntStream.of(1, 2, 3, 4).average();
// present, value 2.5
```

Even though the source is an `IntStream`, the average needs to hold a fractional part, so the return type is `OptionalDouble`. Similarly:

```java
OptionalDouble longAverage = LongStream.of(10L, 11L).average();
// present, value 10.5

OptionalDouble absentAverage = DoubleStream.empty().average();
// empty, NOT 0.0
```

These are illustrative snippets requiring imports for `java.util.OptionalDouble`, `java.util.stream.IntStream`, `java.util.stream.LongStream`, and `java.util.stream.DoubleStream`.

For very large datasets, averaging on primitive streams still follows Java's arithmetic behavior, including `double` precision limits; the result cannot always represent every fraction exactly. If monetary calculations require decimal precision according to business rules, consider `BigDecimal` with an appropriate scale/rounding policy instead of defaulting to `DoubleStream.average()`.

## 7. Converting primitive Optionals back to a stream

The three types provide these methods:

- `OptionalInt.stream()` returns an `IntStream` with 0 or 1 element.
- `OptionalLong.stream()` returns a `LongStream` with 0 or 1 element.
- `OptionalDouble.stream()` returns a `DoubleStream` with 0 or 1 element.

Example usage when chaining optional results into a pipeline:

```java
List<Integer> presentValues = List.of(
        OptionalInt.of(3),
        OptionalInt.empty(),
        OptionalInt.of(8)
).stream()
        .flatMapToInt(OptionalInt::stream)
        .boxed()
        .toList();
// [3, 8]
```

This is a snippet placed inside a method, requiring `import java.util.List;` and `import java.util.OptionalInt;`. `flatMapToInt` flattens the three sub-`IntStream`s (each having 0 or 1 element), discarding empty cases without using `null`.

If you are only processing a single `OptionalInt`, you can continue with a primitive stream:

```java
int doubled = OptionalInt.of(9)
        .stream()
        .map(n -> n * 2)
        .findFirst()
        .orElseThrow();
// 18
```

This is a valid Java 17 illustrative snippet. Notably, `OptionalInt` **does not have** the full `map`, `filter`, and `flatMap` methods like `Optional<Integer>`; when you want Stream-style transformations, you can convert via `.stream()` or write explicit logic with `isPresent`/`ifPresent`.

### `OptionalInt` vs. `Optional<Integer>`

`OptionalInt` holds a **primitive `int`**, whereas `Optional<Integer>` holds a **wrapper `Integer`**. For example:

```java
OptionalInt primitive = OptionalInt.of(7);
java.util.Optional<Integer> boxed =
        primitive.isPresent()
                ? java.util.Optional.of(primitive.getAsInt())
                : java.util.Optional.empty();
```

This illustrative snippet uses `import java.util.OptionalInt;`. Converting to a generic optional requires boxing. Generic `Optional<Integer>` is more flexible with `map`, `filter`, and `flatMap`, but requires a wrapper; primitive optionals avoid boxing **for the contained optional value itself** and integrate directly with primitive streams.

You should not assume that primitive optionals are always faster in every context. Wrappers can still appear when storing in generic collections, boxing via `boxed()`, or calling APIs that accept objects. Choose the type based on contract and clarity first, then measure performance if needed.

## 8. `findFirst()`, `findAny()`, and source ordering

An `OptionalInt` from `findFirst()` represents the **first element in encounter order**, when the stream has an order. For example:

```java
OptionalInt first = IntStream.of(5, 2, 9)
        .parallel()
        .findFirst();
// present, value 5.
```

This is a snippet inside a method, requiring `import java.util.OptionalInt;` and `import java.util.stream.IntStream;`.

Conversely, `findAny()` allows selecting any element to support parallel execution. If you write:

```java
OptionalInt any = IntStream.of(5, 2, 9)
        .parallel()
        .findAny();
```

`any` is present because the source is non-empty, but it is **not guaranteed** to always be `5`. You should not write assertions requiring a specific number from `findAny()`.

On an empty source, both `findFirst()` and `findAny()` produce an empty optional. The present/empty state is independent of whether the stream runs sequentially or in parallel.

## 9. Common errors and pitfalls

1. **Calling `getAsInt()`/`getAsLong()`/`getAsDouble()` on empty:** will throw `NoSuchElementException`. Prefer `orElse`, `orElseGet`, `orElseThrow`, or `ifPresentOrElse` according to business rules.
2. **Treating empty as 0:** `OptionalInt.empty()` is different from `OptionalInt.of(0)`. `OptionalDouble.empty()` is also different from `OptionalDouble.of(0.0)`.
3. **Mistaking the return type of `IntStream.average()`:** it returns `OptionalDouble`, not `OptionalInt`.
4. **Assuming every terminal operation returns an Optional:** `sum()` returns a primitive and `count()` returns `long`. `min()`, `max()`, `average()`, and `findFirst()/findAny()` are the common Optional examples.
5. **Using a sentinel that can be a valid value:** `orElse(-1)` is only safe if business rules specify `-1` as an acceptable representation for the empty case.
6. **Calling an expensive fallback inside `orElse(f())`:** the `f()` argument is evaluated even when the optional is present. Choose `orElseGet(() -> f())` if you only want to compute it when empty.
7. **Looking for `map` directly on `OptionalInt`:** the primitive optional API does not have the `map/filter/flatMap` suite like generic `Optional<T>`. Use `.stream()` or explicit logic.
8. **Equating `NaN` with empty:** `OptionalDouble.of(Double.NaN).isPresent()` is `true`.
9. **Confusing `OptionalInt` with `IntStream`:** an optional has at most one value; a stream can have 0, 1, or many values. `stream()` on an optional converts it to a 0/1-element stream.
10. **Using `findAny()` to reliably pick the first element:** there is no such guarantee, especially when running in parallel.
11. **Treating `Optional` as an identity-sensitive object:** Optional types are *value-based classes*; avoid using `==` or synchronizing on Optional objects. Compare using `equals` when you need to check both state and value.
12. **Ignoring empty handling in API boundaries:** if data can be empty by contract, explicitly decide whether to return empty, use a fallback, or report an error. Do not “force” a value with `getAsX()` and hope the source is never empty.

## 10. Self-check

**Question 1.** What number does `IntStream.empty().max().orElse(0)` produce? Does it mean the stream had a maximum number equal to `0`?

**Answer:** It returns `0` due to the fallback. The original stream was **empty**; no maximum number exists. If you need to distinguish, keep the `OptionalInt` and check presence.

**Question 2.** Does `LongStream.of(1L, 2L).average()` return `OptionalLong` or `OptionalDouble`?

**Answer:** `OptionalDouble`, with a present value of `1.5`.

**Question 3.** Can `OptionalInt.of(0).isPresent()` be used to check the value 0?

**Answer:** `true`. Presence indicates **a value exists**, regardless of what that value is.

**Question 4.** What is `OptionalInt.empty().stream().count()` equal to?

**Answer:** `0`. An empty optional produces an `IntStream` with no elements.

**Question 5.** What is `OptionalDouble.of(Double.NaN).isPresent()`?

**Answer:** `true`. NaN is not the empty state.

**Question 6.** When `OptionalInt` is empty, both `orElseGet(supplier)` and `orElse(defaultValue)` can provide a fallback value. What is the most important difference?

**Answer:** `orElseGet` only invokes the supplier when empty; the argument passed to `orElse` is already evaluated before the method runs.

## Key takeaways

- `OptionalInt`, `OptionalLong`, and `OptionalDouble` represent **a primitive value that is either present or absent**, without using `null`.
- `min`, `max`, `findFirst`, and `findAny` on primitive streams return the corresponding optional; `average()` returns **`OptionalDouble`**.
- When empty, `getAsInt`/`getAsLong`/`getAsDouble` throws `NoSuchElementException`; choose the handling approach based on the business contract.
- Use `orElse` for simple fallbacks, `orElseGet` to compute a fallback on demand, and `orElseThrow` when a missing result is an error.
- `stream()` on a primitive optional creates a 0- or 1-element primitive stream, convenient for chaining into a pipeline.
- **Values like 0 or NaN are still present**. Do not use sentinels when you genuinely need to distinguish absence from a valid value.