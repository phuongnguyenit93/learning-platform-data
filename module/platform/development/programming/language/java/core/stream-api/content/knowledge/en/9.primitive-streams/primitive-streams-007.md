# Type Conversion with `asLongStream` and `asDoubleStream`

## 1. Lesson objectives

In the **`JAVA_STREAM_API`** module, we process data through declarative pipelines: acquire a source, chain lazy intermediate operations like `filter` and `map`, and finish with `reduce` or `collect`. When handling numbers, the Java Stream API offers three specialized stream types for primitive values:

- `IntStream` holds `int` elements.
- `LongStream` holds `long` elements.
- `DoubleStream` holds `double` elements.

Sometimes a pipeline currently using `IntStream` needs the `long` value range for subsequent calculations, or a `LongStream` pipeline needs to produce `double` floating-point results. The two methods **`asLongStream()`** and **`asDoubleStream()`** support *primitive numeric widening* directly on the stream.

After this lesson, you will be able to:

1. Identify which conversion methods exist on `IntStream` and `LongStream`.
2. Read the pipeline type before and after `asLongStream()` or `asDoubleStream()`.
3. Explain why these conversions are lazy intermediate operations and do not require boxing into wrappers.
4. Place type conversions at the right position to avoid `int` overflow before computation.
5. Recognize the risk of precision loss when converting `long` to `double`.
6. Choose among `asLongStream`, `asDoubleStream`, `mapToLong`, `mapToDouble`, and `boxed` based on processing goals.

This lesson belongs to the **Primitive Streams** chapter. The principles regarding types, state, resources, and performance here also serve as the foundation for handling large or parallel streams; they do not replace measuring performance on actual programs.

## 2. Three widening methods to remember

The following methods have existed since **Java 8**:

```java
// Methods on IntStream
LongStream asLongStream();
DoubleStream asDoubleStream();

// Method on LongStream
DoubleStream asDoubleStream();
```

Conversion table:

| Source | Method | Target | Per-element conversion |
| --- | --- | --- | --- |
| `IntStream` | `asLongStream()` | `LongStream` | `int` → `long` |
| `IntStream` | `asDoubleStream()` | `DoubleStream` | `int` → `double` |
| `LongStream` | `asDoubleStream()` | `DoubleStream` | `long` → `double` |

There is no `LongStream.asLongStream()` because it is already `long`. `DoubleStream` also has neither `asLongStream()` nor `asIntStream()`: converting `double` back to an integer is a **narrowing conversion**, which can drop the fractional part or overflow the value range. If converting back is genuinely needed, design an explicit transformation and rounding/validation rule.

Each operation above preserves the **element count** and **encounter order** of an ordered source; it only changes the numeric representation type. They are **intermediate operations**: they create a new stream without consuming the source themselves.

Model:

```text
IntStream
   │ asLongStream()
   ├────────────────────────────► LongStream
   │                                  │
   │                                  └── asDoubleStream()
   │                                              │
   │ asDoubleStream()                              ▼
   └───────────────────────────────────────► DoubleStream
```

## 3. First example: from `int` to `long`

Let us sum the transaction counts across three branches. Each branch stores its count as an `int`, yet the total can exceed the `int` range:

```java
import java.util.stream.IntStream;

public class TongGiaoDich {
    public static void main(String[] args) {
        long tong = IntStream.of(
                1_500_000_000,
                1_500_000_000,
                100
            )
            .asLongStream()
            .sum();

        System.out.println(tong); // 3000000100
    }
}
```

Reading by data type:

```text
IntStream.of(...)    → IntStream
.asLongStream()      → LongStream
.sum()               → long
```

The `asLongStream()` conversion promotes each `int` element to `long` **before** `LongStream.sum()` performs addition. Consequently, the total `3_000_000_100` fits within `long`.

If `asLongStream()` is omitted:

```java
int tongSai = IntStream.of(
        1_500_000_000, 1_500_000_000, 100
    )
    .sum();

System.out.println(tongSai); // -1294967196 (int overflow)
```

`IntStream.sum()` returns `int`, so it risks overflow. **`LongStream.sum()` can also overflow `long`** if the true total exceeds the `long` range; widening only expands the limit and does not eliminate all risk. For gigantic sums or exact precision beyond `long`, consider `BigInteger` with a suitable algorithm/collector.

### Why not use `boxed()`?

Another approach converts `IntStream` into `Stream<Integer>`:

```java
IntStream.of(1, 2, 3)
    .boxed(); // Stream<Integer>
```

However, `boxed()` turns each primitive element into an `Integer` wrapper object; it **does not** produce a `LongStream`. When only primitive `long` arithmetic is needed, `asLongStream()` states the intent clearly and avoids unnecessary boxing.

## 4. From `int` to `double` with `asDoubleStream()`

Use `asDoubleStream()` when you want to process `int` values via the `DoubleStream` API:

```java
import java.util.stream.IntStream;

public class PhanTram {
    public static void main(String[] args) {
        double[] tyLe = IntStream.of(15, 20, 35)
            .asDoubleStream()
            .map(n -> n / 100.0)
            .toArray();

        System.out.println(java.util.Arrays.toString(tyLe));
        // [0.15, 0.2, 0.35]
    }
}
```

Type changes at each step:

| Step | Stream type | Result |
| --- | --- | --- |
| `IntStream.of(15, 20, 35)` | `IntStream` | `15`, `20`, `35` |
| `.asDoubleStream()` | `DoubleStream` | `15.0`, `20.0`, `35.0` |
| `.map(n -> n / 100.0)` | `DoubleStream` | `0.15`, `0.2`, `0.35` |
| `.toArray()` | — | `double[]` |

Numerically, **every `int` value can be represented exactly as a `double`** because `double` has enough significant digits for the entire 32-bit `int` domain. However, subsequent division, multiplication, or other `double` operations can introduce floating-point error; for instance, `0.1` has no exact finite binary representation.

### Example: average

```java
import java.util.OptionalDouble;
import java.util.stream.IntStream;

OptionalDouble trungBinh = IntStream.of(6, 7, 9)
    .asDoubleStream()
    .average();

System.out.println(trungBinh.getAsDouble());
```

The printed value is close to `7.333333333333333`. `average()` returns `OptionalDouble` because the stream may be empty. In practice, you can write it safely as:

```java
double trungBinh = IntStream.of(6, 7, 9)
    .asDoubleStream()
    .average()
    .orElse(0.0);
```

**You do not have to call `asDoubleStream()` just to compute an average**: `IntStream.average()` itself already returns `OptionalDouble`. The conversion proves valuable when you need to continue with operations accepting or returning `double`.

## 5. From `long` to `double`: beware of precision loss

`LongStream.asDoubleStream()` widens primitive `long` to `double`:

```java
import java.util.Arrays;
import java.util.stream.LongStream;

public class LongSangDouble {
    public static void main(String[] args) {
        double[] giaTri = LongStream.of(2L, 4L, 8L)
            .asDoubleStream()
            .toArray();

        System.out.println(Arrays.toString(giaTri));
        // [2.0, 4.0, 8.0]
    }
}
```

For small values, the output is easy to inspect. Yet **not every `long` can be represented exactly by `double`**.

`long` is a 64-bit signed integer. `double` is a 64-bit binary floating-point number with **53 bits of significand precision** (including the implicit bit). Thus, every integer from `-(2^53)` to `2^53` can be represented exactly; outside this range, some integers are representable, but not all.

Example:

```java
import java.util.Arrays;
import java.util.stream.LongStream;

public class MatDoChinhXac {
    public static void main(String[] args) {
        long a = 9_007_199_254_740_992L; // 2^53
        long b = 9_007_199_254_740_993L; // 2^53 + 1

        double[] ketQua = LongStream.of(a, b)
            .asDoubleStream()
            .toArray();

        System.out.println(Arrays.toString(ketQua));
        // [9.007199254740992E15, 9.007199254740992E15]

        System.out.println(ketQua[0] == ketQua[1]); // true
    }
}
```

Two **distinct** `long` values become the same `double` value due to rounding during conversion. If the result is used to compare identifiers, count accurately, distinguish transactions, or calculate money, logic bugs can occur without compiler warnings.

**Selection rule:** keep `LongStream` and `long` arithmetic when exact integer precision in the `long` domain is required. For monetary rules or huge integers needing exact precision, consider `BigDecimal`/`BigInteger` as appropriate. Use `DoubleStream` when the mathematical model tolerates floating-point error, such as sensor measurements, approximate statistics, or ratio calculations.

### Can it overflow to infinity?

When converting a finite `long` value to `double`, the maximum absolute value of `long` is still far smaller than the magnitude limit of `double`. Hence the `long` → `double` conversion itself **does not produce `Infinity` simply because a number is too large**; the immediate risk is **loss of integer precision**. Subsequent `double` operations can still overflow and produce `Infinity` or `NaN` depending on the data.

## 6. Both `asLongStream` and `asDoubleStream` are lazy

Both conversion methods are **intermediate operations**. Writing them does not traverse the source; the pipeline executes only when a terminal operation requests the result.

```java
import java.util.List;
import java.util.stream.Collectors;
import java.util.stream.IntStream;

IntStream nguon = IntStream.rangeClosed(1, 5);

LongStream chuyenKieu = nguon.asLongStream(); // Has not pulled data yet.

List<Long> ketQua = chuyenKieu
    .map(n -> n * n)
    .boxed()
    .collect(Collectors.toList());

System.out.println(ketQua); // [1, 4, 9, 16, 25]
```

> The code above needs `import java.util.stream.LongStream;` if placed inside a standalone Java class declaring a `LongStream` variable.

Explanation:

- `IntStream.rangeClosed(1, 5)` generates integers from 1 to 5.
- `asLongStream()` converts each number to `long` when processing is needed.
- `map(n -> n * n)` performs multiplication in `long`.
- `boxed()` converts `LongStream` to `Stream<Long>`, needed here to collect a `List<Long>` using `Collectors.toList()`.
- `collect` is the terminal operation requesting the result.

Type-conversion operations do not alter the element count, so they still combine cleanly with `filter`, `limit`, `skip`, `sum`, `average`, and `reduce`. Remember: **a stream is consumed only once**; do not take `nguon` back to run another terminal operation after `chuyenKieu` has been consumed.

### Unbounded sources still need a stopping point

```java
long tong = IntStream.iterate(1, n -> n + 1)
    .limit(5)
    .asLongStream()
    .sum();

System.out.println(tong); // 15
```

`asLongStream()` does not create a stopping point itself. If an unbounded source is used and `sum()` or `toArray()` is called without an appropriate limit, the terminal operation may never finish.

## 7. Placement of conversion determines whether overflow occurs

A very common bug is **converting types after an `int` operation has already overflowed**. Once that happens, converting to `long` cannot recover the true original result.

Example computing the square of 50,000:

```java
import java.util.stream.IntStream;

// WRONG result: n * n computes in int and overflows before widening.
long sai = IntStream.of(50_000)
    .map(n -> n * n)
    .asLongStream()
    .sum();

System.out.println(sai); // -1794967296
```

`50_000 × 50_000 = 2_500_000_000`, which exceeds `Integer.MAX_VALUE = 2_147_483_647`. Convert to `long` **before multiplying**:

```java
long dung = IntStream.of(50_000)
    .asLongStream()
    .map(n -> n * n)
    .sum();

System.out.println(dung); // 2500000000
```

The two pipelines appear to differ only in the position of `asLongStream()`, yet **the multiplication semantics changed**:

```text
WRONG: int * int (may overflow) → int result → convert to long
RIGHT: int → long → long * long → long result
```

If there is only a single specific computation, you can widen the operand directly inside the lambda:

```java
long cungDung = IntStream.of(50_000)
    .mapToLong(n -> (long) n * n)
    .sum();

System.out.println(cungDung); // 2500000000
```

Here the `(long) n` cast happens **before the multiplication**, so multiplication executes in `long`.

One more note: `asLongStream()` does not fix every arithmetic error. If a calculation can still exceed `Long.MAX_VALUE`, design value bounds, use `Math.multiplyExact` to detect overflow, or use `BigInteger` if required.

## 8. Distinguishing `asLongStream` / `asDoubleStream` from `mapToLong` / `mapToDouble`

All of them produce a primitive stream of the desired target type, yet their purposes differ:

- **`asLongStream()`, `asDoubleStream()`**: convert each element's type **without performing any value transformation formula beyond Java's primitive widening rules**.
- **`mapToLong(mapper)`, `mapToDouble(mapper)`**: execute **a transformation function** to produce `long` or `double` values.

Example:

```java
import java.util.Arrays;
import java.util.stream.IntStream;

long[] a = IntStream.of(2, 4, 6)
    .asLongStream()
    .toArray();               // [2L, 4L, 6L]

long[] b = IntStream.of(2, 4, 6)
    .mapToLong(n -> n * 100L)
    .toArray();               // [200L, 400L, 600L]

double[] c = IntStream.of(2, 4, 6)
    .asDoubleStream()
    .toArray();               // [2.0, 4.0, 6.0]

double[] d = IntStream.of(2, 4, 6)
    .mapToDouble(n -> n / 10.0)
    .toArray();               // [0.2, 0.4, 0.6]

System.out.println(Arrays.toString(a));
System.out.println(Arrays.toString(b));
System.out.println(Arrays.toString(c));
System.out.println(Arrays.toString(d));
```

Note that in example `b`, `n * 100L` performs multiplication in `long` because operand `100L` is `long`; writing `n * 100` could overflow `int` before being returned as `long`.

The same requirement can have two valid styles:

```java
long tong1 = IntStream.of(50_000, 60_000)
    .asLongStream()
    .map(n -> n * n)
    .sum();

long tong2 = IntStream.of(50_000, 60_000)
    .mapToLong(n -> (long) n * n)
    .sum();

System.out.println(tong1); // 6100000000
System.out.println(tong2); // 6100000000
```

Both are valid because multiplication is evaluated in `long`. Choose whichever conveys intent more clearly: if shifting the whole pipeline to `long`, use `asLongStream`; if immediately computing one `long` value from each `int`, `mapToLong` fits well too.

### When the source is `Stream<T>`

`asLongStream` and `asDoubleStream` **do not exist on `Stream<T>`**. If the source is a list of objects:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> so = Arrays.asList(2, 4, 6);

long tong = so.stream()         // Stream<Integer>
    .mapToInt(Integer::intValue) // IntStream
    .asLongStream()              // LongStream
    .sum();

System.out.println(tong); // 12
```

This can be written more concisely with `mapToLong` directly:

```java
long tong = so.stream()
    .mapToLong(Integer::longValue)
    .sum();
```

If no output type change is needed, `mapToInt(Integer::intValue)` is also a good choice for calculations fitting in `int`; widening to `long` should stem from data or calculation requirements.

### APIs available after conversion

| After conversion step | Commonly used terminal operations |
| --- | --- |
| `LongStream` | `sum()` → `long`, `average()` → `OptionalDouble`, `toArray()` → `long[]`, `max()` → `OptionalLong` |
| `DoubleStream` | `sum()` → `double`, `average()` → `OptionalDouble`, `toArray()` → `double[]`, `max()` → `OptionalDouble` |

`OptionalLong` and `OptionalDouble` represent potentially absent results (e.g., an empty stream). Avoid calling `getAsLong()` or `getAsDouble()` unless a value is guaranteed present; use `orElse` or `orElseThrow` depending on the problem.

## 9. Comparing conversion overhead and boxing

`asLongStream` and `asDoubleStream` convert primitive to primitive. At the API level, they **do not need to allocate a wrapper object per element** as `boxed()` does. This can reduce overhead when processing large amounts of data.

However, do not conclude that a pipeline using `asDoubleStream()` is always faster than every alternative: speed also depends on the source, JIT, allocation counts, memory access, intermediate operations, and how the stream is used. Only draw performance conclusions after measuring with representative data and environment.

| Conversion | Output type | Per-element boxing? | Use when |
| --- | --- | --- | --- |
| `IntStream.asLongStream()` | `LongStream` | No | Want `long` range while staying primitive |
| `IntStream.asDoubleStream()` | `DoubleStream` | No | Want `double` processing from integers |
| `LongStream.asDoubleStream()` | `DoubleStream` | No | Want floating-point math from `long`, accepting rounding risk |
| `IntStream.boxed()` | `Stream<Integer>` | Yes | Need an object stream or generic collectors |
| `LongStream.boxed()` | `Stream<Long>` | Yes | Need `Long` or object-based APIs |
| `DoubleStream.boxed()` | `Stream<Double>` | Yes | Need `Double` or object-based APIs |

If only a single aggregated value is needed, `boxed()` is usually unnecessary:

```java
long tong = IntStream.rangeClosed(1, 100)
    .asLongStream()
    .sum();

System.out.println(tong); // 5050
```

If a `List<Long>` is needed to store results, boxing at the end boundary of the pipeline is reasonable:

```java
import java.util.List;
import java.util.stream.Collectors;

List<Long> ds = IntStream.rangeClosed(1, 3)
    .asLongStream()
    .boxed()
    .collect(Collectors.toList());

// [1L, 2L, 3L] — elements have type Long
```

Since Java 16, `Stream.toList()` can replace `collect(Collectors.toList())` in suitable situations, though `Stream.toList()` returns an unmodifiable list. Collector selection still depends on how the result will be used.

## 10. Common mistakes and fixes

| Mistake / misconception | Cause | Fix |
| --- | --- | --- |
| Calling `asLongStream()` on `LongStream` | `LongStream` is already a `long` stream and has no such method | Keep the stream as is, or use `map` if transformation is needed |
| Calling `asDoubleStream()` on `Stream<Integer>` | Method exists only on appropriate primitive streams | Use `mapToDouble(Integer::doubleValue)` or `mapToInt(...).asDoubleStream()` |
| Calling `asLongStream()` on `DoubleStream` | No such narrowing API exists | Use `mapToLong` with explicit conversion/validation rules |
| `IntStream.map(n -> n*n).asLongStream()` still gives wrong number | `int` multiplication overflowed prior to conversion | Convert first with `asLongStream().map(...)` or `mapToLong(n -> (long)n*n)` |
| Converting all `long` values to `double` then comparing equality | `double` does not represent all 64-bit integers exactly | Keep `long` when exact distinction is required |
| Assuming `asDoubleStream()` divides or normalizes values | Conversion only changes type | Add `map(n -> ...)` if a business formula is needed |
| Using `boxed()` to convert `int` to `long` | `boxed()` creates `Integer`, not `LongStream` | Use `asLongStream()` |
| Trying to reuse source stream after consuming target stream | Pipeline already consumed the source | Create a new stream |
| `sum()` on an unbounded source never returns | No stopping point | Add `limit` or bound the source |
| Using floating-point to add/subtract exact money | `double` has binary rounding error | Choose integer representation or `BigDecimal` as required |

Example compile error due to wrong stream type:

```java
import java.util.Arrays;
import java.util.List;

List<Integer> so = Arrays.asList(1, 2, 3);

// DOES NOT COMPILE: Stream<Integer> has no asLongStream().
// long tongSai = so.stream().asLongStream().sum();

// RIGHT:
long tongDung = so.stream()
    .mapToLong(Integer::longValue)
    .sum();
```

Do not overlook the types in the middle of a pipeline: `Stream<Integer>` and `IntStream` have many different methods even though both represent a sequence of integers.

## 11. Practice exercises

### Exercise 1 — Choose the right conversion

Given the data:

```java
int[] soLuong = {1_000_000_000, 1_000_000_000, 1_000_000_000};
```

Compute the exact sum as `long` using `IntStream` and `asLongStream()`. Explain why `IntStream.sum()` is unsuitable.

### Exercise 2 — Predict types and results

```java
double[] kq = IntStream.of(10, 20, 30)
    .asDoubleStream()
    .map(n -> n / 2)
    .toArray();
```

What type does each step have? What values does array `kq` contain?

### Exercise 3 — Spot overflow before conversion

```java
long x = IntStream.of(50_000)
    .map(n -> n * n)
    .asLongStream()
    .sum();
```

Does this snippet produce `2_500_000_000L`? Fix it in at least two ways.

### Exercise 4 — Precision loss when using `double`

```java
long a = 9_007_199_254_740_992L;
long b = 9_007_199_254_740_993L;

double[] values = LongStream.of(a, b)
    .asDoubleStream()
    .toArray();
```

Predict `values[0] == values[1]` and explain why. Should `DoubleStream` be used to determine whether two `long` identifiers are equal?

### Exercise 5 — Choose API by goal

The source is a `List<Integer>` holding view counts of multiple articles. You want to compute the sum as `long`, and also output a `List<Long>` containing each converted view count. Write two **independent** pipelines from the same source list; explain why you must not reuse a stream that already called `sum()`.

<details>
<summary>Reference solutions</summary>

**Exercise 1**

```java
long tong = java.util.Arrays.stream(soLuong)
    .asLongStream()
    .sum();

System.out.println(tong); // 3000000000
```

`IntStream.sum()` returns `int`, which is smaller than the true sum; `asLongStream()` widens each element to `long` before summing.

**Exercise 2**

`IntStream` → `DoubleStream` → `DoubleStream` → `double[]`. The result is `[5.0, 10.0, 15.0]`. Variable `n` inside `map` has type `double` because `asDoubleStream()` was already called.

**Exercise 3**

No. The `int` multiplication already overflowed. Two fixes:

```java
long cach1 = IntStream.of(50_000)
    .asLongStream()
    .map(n -> n * n)
    .sum();

long cach2 = IntStream.of(50_000)
    .mapToLong(n -> (long) n * n)
    .sum();

// Both equal 2500000000
```

**Exercise 4**

The comparison expression returns `true` because `2^53 + 1` cannot be represented exactly in `double` and rounds to the same value as `2^53`. Never convert to `double` to check equality of `long` identifiers.

**Exercise 5**

```java
import java.util.Arrays;
import java.util.List;
import java.util.stream.Collectors;

List<Integer> luotXem = Arrays.asList(10, 20, 30);

long tong = luotXem.stream()
    .mapToLong(Integer::longValue)
    .sum();

List<Long> duLieuLong = luotXem.stream()
    .mapToInt(Integer::intValue)
    .asLongStream()
    .boxed()
    .collect(Collectors.toList());

System.out.println(tong);         // 60
System.out.println(duLieuLong);   // [10, 20, 30]
```

Each call to `luotXem.stream()` creates a new stream. A stream already consumed by the terminal operation `sum()` cannot be used again to build a list.

</details>

## 12. Takeaways

The three core primitive numeric widening conversions are:

```java
IntStream  --asLongStream()-->   LongStream
IntStream  --asDoubleStream()--> DoubleStream
LongStream --asDoubleStream()--> DoubleStream
```

- These conversions are **lazy intermediate operations**, preserve element count, and require no boxing.
- Converting `int` → `long` and `int` → `double` preserves exact integer values; converting `long` → `double` can round.
- If an intermediate computation can overflow `int`, **widen the type before computing**.
- Use `mapToLong` / `mapToDouble` when a *transformation formula* is needed, and `asLongStream` / `asDoubleStream` when only *type widening* is needed.
- Choose data types according to value domains and precision requirements; do not use `double` for integer data or money requiring absolute precision.

Understanding the placement and limits of these conversions helps write clearer, more reliable `filter`, `map`, `reduce`, and aggregation pipelines when working with the Stream API.
