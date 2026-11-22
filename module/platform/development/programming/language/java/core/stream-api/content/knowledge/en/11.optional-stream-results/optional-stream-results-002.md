# Using `OptionalInt`, `OptionalLong`, and `OptionalDouble`

## 1. Why Do Stream Results Need Optional?

In the **Java Stream API**, declarative pipelines often combine a data source, lazy intermediate operations such as `filter` and `map`, and end with `min`, `max`, `average`, `findFirst`, or `reduce`. A pipeline cannot always find an element to return. For example: the source is empty, or all elements are removed by `filter`.

Java uses three **primitive Optional** types to express the case where an operation *may or may not have a result*:

- `OptionalInt`: may contain an `int` value.
- `OptionalLong`: may contain a `long` value.
- `OptionalDouble`: may contain a `double` value.

They are not streams and they are not `null`. Each object represents **a present or empty state**. This allows calling code to proactively decide how to handle missing data, instead of assuming a result is always present.

After this lesson, you will be able to:

1. Identify which methods of `IntStream`, `LongStream`, and `DoubleStream` return a primitive Optional.
2. Check and retrieve values using `isPresent`, `ifPresent`, `orElse`, `orElseGet`, and `orElseThrow`.
3. Distinguish **having no result** from a valid result equal to `0`, `0L`, or `0.0`.
4. Handle real-world scenarios: average score, largest transaction, measurement values, and search results.
5. Choose among primitive Optional, `Optional<T>`, default values, and exceptions according to the business contract.

This lesson belongs to the **Optional in Stream Results** chapter of the `JAVA_STREAM_API` module. It provides the foundation for reading results of numeric pipelines, `reduce`, and aggregations in advanced topics such as grouping, custom collectors, or parallel processing.

## 2. Return Type Map of Terminal Operations

Primitive streams were introduced in Java 8:

| Stream type | Operations returning primitive Optional | Operations returning a value directly |
| --- | --- | --- |
| `IntStream` | `min()`, `max()`, `findFirst()`, `findAny()`, `reduce(IntBinaryOperator)` → `OptionalInt`; `average()` → `OptionalDouble` | `sum()` → `int`, `count()` → `long` |
| `LongStream` | `min()`, `max()`, `findFirst()`, `findAny()`, `reduce(LongBinaryOperator)` → `OptionalLong`; `average()` → `OptionalDouble` | `sum()` → `long`, `count()` → `long` |
| `DoubleStream` | `min()`, `max()`, `findFirst()`, `findAny()`, `reduce(DoubleBinaryOperator)`, `average()` → `OptionalDouble` | `sum()` → `double`, `count()` → `long` |

An important note: **`average()` on all three primitive stream types returns `OptionalDouble`**. The average of integers can be a fractional number; therefore, there is no `OptionalInt` or `OptionalLong` for this calculation.

```java
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.DoubleStream;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

OptionalInt minDiem = IntStream.of(7, 8, 9).min();
OptionalLong giaoDichLonNhat = LongStream.of(100L, 300L).max();
OptionalDouble trungBinh = IntStream.of(7, 8, 9).average();
OptionalDouble doLonNhat = DoubleStream.of(1.5, 2.5).max();
```

Reading from source type to result:

```text
IntStream  ── min() / max() / findFirst() ──▶ OptionalInt
LongStream ── min() / max() / findFirst() ──▶ OptionalLong
DoubleStream ── min() / max() / average() ──▶ OptionalDouble

IntStream  ── average() ──────────────────▶ OptionalDouble
LongStream ── average() ──────────────────▶ OptionalDouble
```

When you see a compilation error due to assigning the wrong type, check **the stream type immediately before the terminal operation**, not just the initial data type. For example, `mapToLong` changes the stream type, so a subsequent `findFirst()` returns `OptionalLong`.

## 3. Complete Example: Analyzing Exam Scores

The program below runs on **Java 8 or later**:

```java
import java.util.Arrays;
import java.util.OptionalDouble;
import java.util.OptionalInt;
import java.util.stream.IntStream;

public class ThongKeDiem {
    public static void main(String[] args) {
        int[] diem = {7, 9, 6, 8};

        OptionalInt diemNhoNhat = Arrays.stream(diem).min();
        OptionalInt diemLonNhat = Arrays.stream(diem).max();
        OptionalDouble diemTrungBinh = Arrays.stream(diem).average();

        System.out.println("Min: " + diemNhoNhat.orElse(-1));
        System.out.println("Max: " + diemLonNhat.orElse(-1));
        System.out.println("Average: " + diemTrungBinh.orElse(0.0));

        int[] khongCoDiem = {};
        OptionalDouble trungBinhRong = Arrays.stream(khongCoDiem).average();

        System.out.println("Has scores? " + trungBinhRong.isPresent());
    }
}
```

Output:

```text
Min: 6
Max: 9
Average: 7.5
Has scores? false
```

Explanation:

- `min()`, `max()`, and `average()` are **terminal operations**, which consume the stream.
- `Arrays.stream(diem)` creates an `IntStream`. The program creates **three new streams** from the same array to perform three independent terminal operations.
- `min()` and `max()` return `OptionalInt`; `average()` returns `OptionalDouble`.
- With an empty array, `average()` returns `OptionalDouble.empty()`. There is no valid average to retrieve directly.

In the example, `-1` and `0.0` are default values to demonstrate the API. When applying business logic, **never automatically treat the average of an empty dataset as 0.0**, unless the requirements explicitly define it that way.

## 4. Empty State Differs From a Value of 0

A primitive Optional has two states:

```text
OptionalInt
  ├─ Has a value: OptionalInt.of(0) / OptionalInt.of(42) / ...
  └─ Empty:       OptionalInt.empty()
```

`OptionalInt.of(0)` **has a value**, and that value is 0. `OptionalInt.empty()` **has no value**. The same applies to `OptionalLong.of(0L)` and `OptionalDouble.of(0.0)`.

```java
import java.util.OptionalInt;

OptionalInt coSoKhong = OptionalInt.of(0);
OptionalInt khongCoSo = OptionalInt.empty();

System.out.println(coSoKhong.isPresent()); // true
System.out.println(khongCoSo.isPresent()); // false

System.out.println(coSoKhong.orElse(-1)); // 0
System.out.println(khongCoSo.orElse(-1)); // -1
```

When a stream is empty:

```java
import java.util.stream.IntStream;

OptionalInt ketQua = IntStream.empty().max();
System.out.println(ketQua.isPresent()); // false
```

When a terminal operation has a **default/identity value**, the result can be a direct value even when the source is empty:

```java
int tongRong = IntStream.empty().sum();
long soLuongRong = IntStream.empty().count();

System.out.println(tongRong);    // 0
System.out.println(soLuongRong); // 0
```

This does not make `max()` or `average()` meaningful on an empty set. There is no "largest element" or "arithmetic average" of an empty set under the contracts of those methods.

**A business example:** A transaction count of 0 can be valid data; whereas "no transaction data yet" has a different meaning. If the two states need to be distinguished, returning `OptionalInt` or `OptionalLong` is clearer than using an assumed number.

## 5. Safe Checking: `isPresent`, `ifPresent`, and `getAs...`

The corresponding value retrieval methods:

| Type | Check | Get value | If empty |
| --- | --- | --- | --- |
| `OptionalInt` | `isPresent()` | `getAsInt()` | Throws `NoSuchElementException` |
| `OptionalLong` | `isPresent()` | `getAsLong()` | Throws `NoSuchElementException` |
| `OptionalDouble` | `isPresent()` | `getAsDouble()` | Throws `NoSuchElementException` |

Valid example:

```java
OptionalInt diemMax = IntStream.of(5, 8, 9).max();

if (diemMax.isPresent()) {
    System.out.println("Highest score: " + diemMax.getAsInt());
} else {
    System.out.println("No scores yet to compute");
}
```

If you only need to perform an action **when a result is present**, `ifPresent` is more concise:

```java
OptionalLong max = java.util.stream.LongStream
    .of(1_000L, 2_000L, 1_500L)
    .max();

max.ifPresent(value -> System.out.println("Largest transaction: " + value));
```

`ifPresent` accepts a consumer of the corresponding primitive type: `IntConsumer`, `LongConsumer`, or `DoubleConsumer`. When the Optional is empty, the action does not run.

**Do not call `getAsInt()`, `getAsLong()`, or `getAsDouble()` without being certain the Optional has a value**:

```java
// COMPILES BUT WILL THROW NoSuchElementException.
// int x = java.util.OptionalInt.empty().getAsInt();
```

In problems where a missing result is a normal possibility, calling `getAs...` directly often makes code fragile. Choose `orElse`, `orElseGet`, `orElseThrow`, or handle the empty branch explicitly.

## 6. Fallback Values: `orElse` and `orElseGet`

### 6.1. `orElse`: Having a Fixed Default Value

`orElse` returns the present value if the Optional is not empty; if empty, it returns the fallback value:

```java
int diemMacDinh = IntStream.empty()
    .max()
    .orElse(-1);

long giaoDichMacDinh = java.util.stream.LongStream.empty()
    .max()
    .orElse(0L);

double nhietDoMacDinh = java.util.stream.DoubleStream.empty()
    .average()
    .orElse(Double.NaN);

System.out.println(diemMacDinh);       // -1
System.out.println(giaoDichMacDinh);   // 0
System.out.println(Double.isNaN(nhietDoMacDinh)); // true
```

The fallback value must match the primitive type (`int`, `long`, or `double`) and **must carry business meaning**. `-1` may be a valid special value in one system yet a forbidden value in another. `Double.NaN` is also a special `double` value, not equivalent to an empty Optional state.

If you need to distinguish "no data" from a floating-point number, it is usually better to keep `OptionalDouble` until the consumer decides the policy.

### 6.2. `orElseGet`: Computing the Fallback Value When Needed

`orElseGet` accepts a supplier, which is only called when the Optional is empty. For primitive Optionals, the suppliers are `IntSupplier`, `LongSupplier`, and `DoubleSupplier`, respectively.

```java
OptionalInt ketQua = IntStream.of(4, 7, 2).max();

int giaTri = ketQua.orElseGet(() -> {
    System.out.println("Computing fallback");
    return -1;
});

System.out.println(giaTri); // 7
```

Because `ketQua` has a value, the string `Computing fallback` is not printed. Conversely, `orElse(-1)` is suitable when only a simple constant is needed.

Example of a meaningful fallback such as computing a configuration value:

```java
int gioiHan = IntStream.empty()
    .max()
    .orElseGet(() -> {
        // Compute default configuration when there is no data.
        return 100;
    });
```

Do not use `orElseGet` solely to cause side effects; its primary purpose is **providing a value**.

## 7. Requiring a Result: `orElseThrow`

In some systems, not finding data is a business error: for example, requesting the highest score of a class confirmed to have exam papers, yet the system contains no scores. In that case, you can throw an exception with a clear message:

```java
import java.util.stream.IntStream;

int diemCaoNhat = IntStream.of(6, 9, 8)
    .max()
    .orElseThrow(() -> new IllegalStateException(
        "No exam scores to compute the highest score"
    ));

System.out.println(diemCaoNhat); // 9
```

If the stream is empty, the supplier creates an `IllegalStateException`. This is the **`orElseThrow(Supplier<? extends X>)`** overload available in Java 8.

```java
// Example intentionally throwing a runtime exception:
// int max = IntStream.empty()
//     .max()
//     .orElseThrow(() -> new IllegalStateException("Missing scores"));
```

There is no need to write `isPresent` and manually throw an exception when `orElseThrow` expresses the same contract more clearly.

**Quick choice:**

| Situation | Choice |
| --- | --- |
| No data is normal and the caller needs to distinguish it | Keep `OptionalInt` / `OptionalLong` / `OptionalDouble` |
| No data uses an agreed constant | `orElse(defaultValue)` |
| Need to compute a fallback value when data is missing | `orElseGet(supplier)` |
| Missing data violates the business contract | `orElseThrow(exceptionSupplier)` |
| Only run an action if a result exists | `ifPresent(consumer)` |

## 8. Dedicated Examples for `OptionalLong` and `OptionalDouble`

### 8.1. `OptionalLong`: Finding the Largest Transaction

Transaction amounts can exceed the `int` limit, so use `LongStream`:

```java
import java.util.OptionalLong;
import java.util.stream.LongStream;

public class GiaoDichLonNhat {
    public static void main(String[] args) {
        long[] giaoDich = {
            3_000_000_000L,
            5_000_000_000L,
            2_000_000_000L
        };

        OptionalLong lonNhat = LongStream.of(giaoDich).max();

        lonNhat.ifPresent(value ->
            System.out.println("Largest: " + value)
        );

        long ketQua = lonNhat.orElseThrow(
            () -> new IllegalStateException("No transactions yet")
        );
        System.out.println(ketQua); // 5000000000
    }
}
```

If `giaoDich` is actually empty, `max()` returns `OptionalLong.empty()`. Do not automatically interpret this as an amount of `0L`, because a transaction with a value of 0 can still be a real record.

### 8.2. `OptionalDouble`: Sensor Average

`DoubleStream.average()` returns `OptionalDouble`. The result may not exist if there are no measurement samples:

```java
import java.util.OptionalDouble;
import java.util.stream.DoubleStream;

public class TrungBinhCamBien {
    public static void main(String[] args) {
        double[] nhietDo = {24.5, 25.0, 25.5};

        OptionalDouble trungBinh = DoubleStream.of(nhietDo)
            .average();

        if (trungBinh.isPresent()) {
            System.out.println(trungBinh.getAsDouble()); // 25.0
        } else {
            System.out.println("No measurements yet");
        }
    }
}
```

If the source contains `Double.NaN` or infinite values, the arithmetic result can be `NaN` or infinity **even though the Optional still has a value**. Data presence/absence and the validity of a floating-point value are **two different checks**.

```java
OptionalDouble giaTri = DoubleStream.of(Double.NaN).average();

System.out.println(giaTri.isPresent());                 // true
System.out.println(Double.isNaN(giaTri.getAsDouble())); // true
```

If the system only accepts finite numbers, check `Double.isFinite(value)` (Java 8+) or an appropriate data validation policy, instead of assuming `isPresent()` means a valid measurement value.

## 9. `findFirst`, `findAny`, and Search Results

When searching in a primitive stream, the result type depends on the stream **immediately before the terminal operation**:

```java
import java.util.OptionalInt;
import java.util.OptionalLong;
import java.util.stream.IntStream;
import java.util.stream.LongStream;

OptionalInt dauTien = IntStream.of(3, 5, 7)
    .filter(n -> n > 4)
    .findFirst();

OptionalLong batKy = LongStream.of(10L, 20L, 30L)
    .filter(n -> n >= 20L)
    .findAny();

System.out.println(dauTien.orElse(-1)); // 5
System.out.println(batKy.isPresent());  // true
```

`findFirst()` respects the encounter order of an ordered stream; in the example, the result is 5. `findAny()` allows returning **any matching element**, especially useful when the implementation can leverage parallel processing. Therefore **do not assume** `batKy` always contains 20L, even though on a simple sequential pipeline the result is usually the first element encountered.

With an empty stream or when filtering leaves no elements:

```java
OptionalInt khongTimThay = IntStream.of(1, 2, 3)
    .filter(n -> n > 10)
    .findFirst();

System.out.println(khongTimThay.isPresent()); // false
```

`findFirst` and `findAny` are terminal operations that can **short-circuit**, meaning they can stop processing once the result is determined. However, that does not guarantee they will evaluate every lambda in the pipeline or in a specific order in parallel mode. Avoid placing mandatory side effects inside `filter` or `map`.

## 10. `reduce` With and Without Identity

`reduce` clearly illustrates the difference between "always having an aggregated value" and "possibly having no result".

### 10.1. Without Identity: Returns Optional

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt tong = IntStream.of(2, 4, 6)
    .reduce((a, b) -> a + b);

OptionalInt tongRong = IntStream.empty()
    .reduce((a, b) -> a + b);

System.out.println(tong.orElse(-1));       // 12
System.out.println(tongRong.isPresent());  // false
```

In this overload, there is no value to start reducing if the stream is empty, so the result is `OptionalInt.empty()`.

### 10.2. With Identity: Returns a Primitive Value

```java
int tong = IntStream.of(2, 4, 6)
    .reduce(0, (a, b) -> a + b);

int tongRong = IntStream.empty()
    .reduce(0, (a, b) -> a + b);

System.out.println(tong);     // 12
System.out.println(tongRong); // 0
```

`0` is the identity element of addition: `0 + x = x`. Because an identity is provided, this overload returns `int` directly even when the source is empty.

| Operation | Stream with elements | Empty stream |
| --- | --- | --- |
| `reduce((a, b) -> a + b)` | `OptionalInt.of(sum)` | `OptionalInt.empty()` |
| `reduce(0, (a, b) -> a + b)` | `int` equal to sum | `int` equal to 0 |
| `sum()` | `int` equal to sum | `int` equal to 0 |

**Do not pick an arbitrary identity.** It must genuinely be the identity element of the operation. For example, `reduce(1, (a, b) -> a * b)` makes sense for multiplication; using `0` as the identity for multiplication will produce the wrong result.

To use `reduce` safely on a parallel stream, the combining function must also obey requirements such as associativity. If you need ordinary summation, the built-in `sum()` methods are usually easier to read.

## 11. Distinguishing Primitive Optionals From `Optional<T>`

The three primitive Optional types **have no inheritance relationship** with `Optional<Integer>`, `Optional<Long>`, or `Optional<Double>`. Therefore, they cannot be assigned directly:

```java
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;

// DOES NOT COMPILE: OptionalInt is different from Optional<Integer>.
// Optional<Integer> sai = IntStream.of(1, 2).max();

OptionalInt dung = IntStream.of(1, 2).max();
```

`Optional<T>` is a generic type wrapping an object value; for example, `Stream<Integer>.max(Comparator)` can return `Optional<Integer>`, whereas `IntStream.max()` returns `OptionalInt`:

```java
import java.util.Comparator;
import java.util.Optional;
import java.util.OptionalInt;
import java.util.stream.IntStream;
import java.util.stream.Stream;

Optional<Integer> maxDoiTuong = Stream.of(1, 3, 2)
    .max(Comparator.naturalOrder());

OptionalInt maxNguyenThuy = IntStream.of(1, 3, 2)
    .max();
```

Important differences:

| Characteristic | `OptionalInt` / `OptionalLong` / `OptionalDouble` | `Optional<T>` |
| --- | --- | --- |
| Inner value | Primitive `int`/`long`/`double` | Reference value of type `T` |
| Retrieve value | `getAsInt`/`getAsLong`/`getAsDouble` | `get()` |
| No wrapper needed per primitive value | Yes | No |
| Generic `map`, `filter`, `flatMap` | These methods do not exist in the primitive Optional API | Yes |
| Can be empty | Yes | Yes |

To **transform a primitive Optional** in Java 8, you typically handle it with `isPresent` and retrieve the value, or perform `map` on the stream *before* obtaining the Optional.

For example, instead of finding the number first and then doubling it:

```java
OptionalInt ketQua = IntStream.of(4, 7, 9)
    .filter(n -> n > 5)
    .map(n -> n * 2)
    .findFirst();

System.out.println(ketQua.orElse(-1)); // 14
```

When you need to integrate with an API expecting `Optional<Integer>`, you can convert explicitly:

```java
OptionalInt primitive = IntStream.of(4, 7).max();

Optional<Integer> boxed = primitive.isPresent()
    ? Optional.of(primitive.getAsInt())
    : Optional.empty();
```

This conversion involves boxing, so only do it when there is a clear reason.

## 12. API Additions by Java Version

The core examples above use APIs from **Java 8**. Several utility methods appeared later:

| Method | Version | Purpose |
| --- | --- | --- |
| `OptionalInt.stream()`, `OptionalLong.stream()`, `OptionalDouble.stream()` | Java 9+ | Converts an Optional into a primitive stream of 0 or 1 element. |
| `ifPresentOrElse(consumer, emptyAction)` | Java 9+ | Handles both the present-value branch and the empty branch. |
| `isEmpty()` | Java 11+ | Checks whether an Optional is empty directly, equivalent to `!isPresent()`. |

Example using `stream()` from Java 9:

```java
import java.util.OptionalInt;
import java.util.stream.IntStream;

OptionalInt lonNhat = IntStream.of(2, 8, 4).max();

int[] mang = lonNhat.stream()
    .map(n -> n * 2)
    .toArray();

System.out.println(java.util.Arrays.toString(mang)); // [16]
```

If `lonNhat` is empty, `lonNhat.stream()` creates an empty `IntStream`, so `toArray()` returns an empty array. This is a convenient way to chain further into pipelines when the Java version supports it.

Java 9+ example for two branches:

```java
IntStream.empty().max().ifPresentOrElse(
    value -> System.out.println("Max: " + value),
    () -> System.out.println("No data")
);

// No data
```

Do not use these methods in projects restricted to Java 8. In Java 8, you can use `isPresent()` and an `if/else` branch as shown in the previous section.

## 13. Common Mistakes

| Issue | Cause | How to handle it |
| --- | --- | --- |
| Calling `getAsInt()` on an empty Optional | No value present; throws `NoSuchElementException` | Use `orElse`, `orElseThrow`, or check `isPresent` |
| Thinking `OptionalInt.empty()` equals `OptionalInt.of(0)` | Confusing missing data state with a valid value of 0 | Rely on `isPresent` to know whether data exists |
| Assigning `IntStream.average()` to `OptionalInt` | `average()` returns `OptionalDouble` | Declare properly as `OptionalDouble` |
| Assigning `IntStream.max()` to `Optional<Integer>` | Primitive Optional differs from generic Optional | Use `OptionalInt` or convert types explicitly |
| Defaulting to `orElse(0)` for all missing cases | 0 can distort business reports | Keep Optional or choose a clear missing-data policy |
| Using `getAsDouble()` after only checking `isPresent` | Floating-point number may be `NaN` or infinity | Check finiteness if required by the problem |
| Passing `null` instead of an empty Optional | Defeats the purpose of Optional and risks `NullPointerException` | Use `OptionalInt.empty()`, `OptionalLong.empty()`, or `OptionalDouble.empty()` |
| Reusing a stream after `max` / `average` / `findFirst` | Terminal operation has already consumed the stream | Create a new stream from the source |
| Assuming `findAny()` always returns the first element | `findAny` does not guarantee a specific element | Use `findFirst` when order matters |
| Using `isEmpty()` in Java 8 | Method only exists from Java 11 | Use `!isPresent()` in Java 8 |

**Key point to remember when diagnosing:** Optional is **the result of an operation**, not proof that the pipeline traversed the entire source. Search operations like `findFirst` can terminate early; do not place mandatory side effects inside lambdas assuming they will always execute.

## 14. Practice Exercises

### Exercise 1 — Empty Result or Equal to 0?

Predict the state and values below:

```java
OptionalInt a = IntStream.of(0).max();
OptionalInt b = IntStream.empty().max();

System.out.println(a.isPresent());
System.out.println(b.isPresent());
System.out.println(a.orElse(-1));
System.out.println(b.orElse(-1));
```

Why can't you just compare `orElse(0)` to distinguish the two cases?

### Exercise 2 — Return Type of `average`

Given:

```java
long[] luotXem = {3L, 4L, 5L, 6L};
```

Write a pipeline that produces an Optional containing the average number of views. What type is the Optional? What is the result?

### Exercise 3 — Handling an Optional Result

Given:

```java
int[] diem = {4, 6, 8, 10};
```

Find the first score greater than 7, and print it if found. If none exists, use the fallback value `-1`. Implement using Java 8 APIs.

### Exercise 4 — `reduce` With and Without Identity

Predict the results:

```java
OptionalLong a = java.util.stream.LongStream.empty()
    .reduce((x, y) -> x + y);

long b = java.util.stream.LongStream.empty()
    .reduce(0L, (x, y) -> x + y);
```

Why is `a` empty while `b` equals 0?

### Exercise 5 — Sensor Average With `NaN`

```java
OptionalDouble m = java.util.stream.DoubleStream.of(
    5.0, Double.NaN
).average();
```

Is `m.isPresent()` `true` or `false`? Why do you still need to validate the data before using this value?

### Reference Solutions

**Exercise 1:** `a.isPresent() == true`, `b.isPresent() == false`, `a.orElse(-1) == 0`, `b.orElse(-1) == -1`. If `orElse(0)` is used, both yield 0 even though their states differ.

**Exercise 2:**

```java
OptionalDouble trungBinh = java.util.Arrays.stream(luotXem)
    .average();

System.out.println(trungBinh.orElse(-1.0)); // 4.5
```

`Arrays.stream(long[])` creates a `LongStream`, yet `average()` still returns `OptionalDouble`.

**Exercise 3:**

```java
OptionalInt timDuoc = java.util.Arrays.stream(diem)
    .filter(d -> d > 7)
    .findFirst();

timDuoc.ifPresent(d -> System.out.println("Score: " + d)); // 8

int giaTri = timDuoc.orElse(-1);
System.out.println(giaTri); // 8
```

If all scores are less than or equal to 7, `findFirst()` returns an empty Optional, `ifPresent` prints nothing, and `orElse(-1)` returns -1.

**Exercise 4:** `a.isPresent() == false` because there is no element to start the reduction without identity. `b == 0L` because the identity `0L` is the identity element of addition.

**Exercise 5:** `m.isPresent() == true` because the stream is not empty. However, `m.getAsDouble()` evaluates to `NaN` due to an input sample being `NaN`. `OptionalDouble` only expresses *whether a result exists or not*, not that the result is a finite number.

## 15. Takeaways

- `OptionalInt`, `OptionalLong`, and `OptionalDouble` hold **0 or 1 primitive value**, and are returned by operations such as `min`, `max`, `findFirst`, `findAny`, or `reduce` without identity.
- `average()` on `IntStream`, `LongStream`, and `DoubleStream` all return **`OptionalDouble`**.
- The **no data** case differs from a valid value of `0`, `0L`, or `0.0`.
- Use `isPresent`/`ifPresent` to check, `orElse`/`orElseGet` when there is a fallback value, and `orElseThrow` when missing data is an error.
- Do not call `getAs...` on an empty Optional; do not confuse primitive Optionals with `Optional<T>`.
- When working with floating-point data, also consider `NaN`, infinity, and the precision requirements of the problem.

Handling Optional properly helps Stream API pipelines clearly express data contracts, preserve the meaning of empty cases, and avoid runtime errors in statistics, search, and data aggregation applications.
