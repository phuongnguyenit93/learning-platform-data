# Using mapMulti on Primitive Streams

## 1. When one input number produces zero, one, or many output numbers

In the **Primitive Streams** chapter of **JAVA_STREAM_API**, we use `IntStream`, `LongStream`, and `DoubleStream` to process numeric data directly without boxing every element into `Integer`, `Long`, or `Double`. These Streams still support lazy pipelines with `filter`, `map`, `reduce`, and terminal operations such as `sum`, `average`, and `summaryStatistics`.

However, `map` only produces **one** output element for **each** input element. What if the data needs to emit 0, 1, or multiple values?

For example:

- Quantity `0` corresponds to **0** units to process.
- Quantity `1` corresponds to **1** unit.
- Quantity `3` corresponds to **3** units.
- An invalid measurement is **skipped**; a valid measurement can emit multiple numeric features.
- Each time-interval code can generate a sequence of positions rather than just one position.

Since **Java 16**, primitive streams provide `mapMulti` to address these scenarios directly. The lambda receives the current value and a **consumer of the matching primitive type**; calling `accept` N times emits N elements.

~~~text
                   IntStream / LongStream / DoubleStream
                                   │
                                   ▼
                        mapMulti((n, out) -> ...)
                                   │
                  ┌────────────────┼────────────────┐
                  ▼                ▼                ▼
             accept not        accept called    accept called
               called             1 time           N times
                  │                │                │
                  ▼                ▼                ▼
              0 numbers         1 number          N numbers
                  └────────────────┴────────────────┘
                                   │
                                   ▼
                      Same primitive stream type
~~~

This lesson focuses on `mapMulti` on **primitive Streams** and how to distinguish it from `mapMultiToInt`, `mapMultiToLong`, and `mapMultiToDouble` on `Stream<T>`. The examples run on **Java 17+**; `Stream.toList()` in some snippets also requires Java 16+.

## 2. Three `mapMulti` APIs and their corresponding consumers

Conceptual signatures:

~~~java
// Methods on the three primitive streams:
IntStream mapMulti(IntStream.IntMapMultiConsumer mapper);
LongStream mapMulti(LongStream.LongMapMultiConsumer mapper);
DoubleStream mapMulti(DoubleStream.DoubleMapMultiConsumer mapper);
~~~

Each specialized functional interface accepts a value and a consumer of the same type:

~~~java
// Descriptive contract form of the callbacks:
void accept(int value, IntConsumer downstream);
void accept(long value, LongConsumer downstream);
void accept(double value, DoubleConsumer downstream);
~~~

| Input Stream | Callback | Consumer emitting results | Returned Stream |
| --- | --- | --- | --- |
| `IntStream` | `IntStream.IntMapMultiConsumer` | `IntConsumer.accept(int)` | `IntStream` |
| `LongStream` | `LongStream.LongMapMultiConsumer` | `LongConsumer.accept(long)` | `LongStream` |
| `DoubleStream` | `DoubleStream.DoubleMapMultiConsumer` | `DoubleConsumer.accept(double)` | `DoubleStream` |

All three methods are named `mapMulti`, while the type of argument `n` and `out.accept(...)` is determined by the primitive stream being called.

~~~java
import java.util.stream.IntStream;

int[] result = IntStream.of(2, 0, 3)
    .mapMulti((value, out) -> {
        for (int i = 0; i < value; i++) {
            out.accept(value);
        }
    })
    .toArray();

// result = [2, 2, 3, 3, 3]
~~~

The callback **does not return a sub-stream**. It returns `void` and pushes values to `out`:

- Never call `accept`: emits **0 elements**.
- Call once: emits **1 element**.
- Call multiple times: emits **multiple elements**, in the order of calls inside the callback for that input.

Do not retain `out` for use after the callback completes or invoke it from an asynchronous task. The passed consumer is the emission mechanism for **the current processing step**, not an indefinitely open channel.

## 3. `IntStream.mapMulti`: emitting integers by rule

Consider a problem simulating inspection rounds. For each positive integer `n`, we want to emit the sequence from `1` to `n`. Value `0` produces no output; negative values are invalid inputs and in this illustrative example are skipped.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

public class IntMapMultiDemo {
    public static void main(String[] args) {
        int[] slots = IntStream.of(1, 0, 3, -2, 2)
            .mapMulti((n, out) -> {
                if (n <= 0) {
                    return; // Emit no elements.
                }

                for (int index = 1; index <= n; index++) {
                    out.accept(index);
                }
            })
            .toArray();

        System.out.println(Arrays.toString(slots));
        // [1, 1, 2, 3, 1, 2]
    }
}
~~~

Each input sequentially produces:

| `n` | Emitted values |
| --- | --- |
| `1` | `1` |
| `0` | None |
| `3` | `1, 2, 3` |
| `-2` | None |
| `2` | `1, 2` |

Here `mapMulti` directly replaces creating an `IntStream.rangeClosed(1, n)` for each number. However, if the goal is truly to **emit a single numeric range**, `IntStream.range` or `rangeClosed` is usually the simpler API.

### Example of 0 or 2 results: generating number pairs

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

public class EvenPairs {
    public static void main(String[] args) {
        int[] values = IntStream.rangeClosed(1, 5)
            .mapMulti((n, out) -> {
                if ((n & 1) == 0) {
                    out.accept(n);
                    out.accept(n * 10);
                }
            })
            .toArray();

        System.out.println(Arrays.toString(values));
        // [2, 20, 4, 40]
    }
}
~~~

You can chain an `IntStream` terminal operation **without boxing**:

~~~java
int sum = IntStream.rangeClosed(1, 5)
    .mapMulti((n, out) -> {
        if (n % 2 == 0) {
            out.accept(n);
            out.accept(n * 10);
        }
    })
    .sum();

// sum = 66 (2 + 20 + 4 + 40)
~~~

If you always emit **exactly one** number per input, `map` is shorter and expresses intent more clearly. If you only keep or drop **the current number itself**, `filter` is usually better suited.

## 4. `LongStream.mapMulti`: handling quantities and long values

`LongStream` serves the `long` value domain, such as large IDs, lengths, counts, or monetary amounts stored in the smallest currency unit. `LongStream.mapMulti` uses `LongConsumer` to emit `long` values without boxing through `Long`.

Example: each number indicates how many times a service with unit price 10,000 was used. We emit the price of each usage and then compute the total:

~~~java
import java.util.Arrays;
import java.util.stream.LongStream;

public class LongMapMultiDemo {
    public static void main(String[] args) {
        long[] unitPrices = LongStream.of(2L, 0L, 3L)
            .mapMulti((quantity, out) -> {
                if (quantity < 0 || quantity > 1000) {
                    throw new IllegalArgumentException(
                        "Invalid quantity: " + quantity
                    );
                }

                for (long i = 0; i < quantity; i++) {
                    out.accept(10_000L);
                }
            })
            .toArray();

        System.out.println(Arrays.toString(unitPrices));
        // [10000, 10000, 10000, 10000, 10000]

        long total = LongStream.of(unitPrices).sum();
        System.out.println(total); // 50000
    }
}
~~~

The example enforces an **upper bound** to prevent an anomalous input quantity from making the program emit millions of elements or run too long. Real-world data must validate both correctness and business bounds before expanding.

If only the total is needed, **there is no need to create a Stream of many values**:

~~~java
long total = LongStream.of(2L, 0L, 3L)
    .map(quantity -> Math.multiplyExact(quantity, 10_000L))
    .sum();

// 50000
~~~

`Math.multiplyExact` detects overflow during multiplication, yet `LongStream.sum()` can still overflow if the total exceeds `long` range; when financial precision is mandatory, design overflow checks and an arithmetic policy accordingly. `mapMulti` is a **data-expansion** tool, not a default optimization for every summation formula.

### When is `LongStream.mapMulti` actually useful?

It is useful when downstream steps **need each individual value**: emitting event IDs, generating timestamps, or applying a distinct transformation per unit. If you only need sum, average, or count, computing directly is usually preferable.

## 5. `DoubleStream.mapMulti`: filtering measurements and emitting multiple features

`DoubleStream.mapMulti` works similarly, except the mapper takes `double` and a `DoubleConsumer`. This is the right choice when the resulting data consists of primitive floating-point numbers.

For example, for each positive, finite measurement, emit both the original value and half its value; skip `NaN`, infinite values, and non-positive numbers:

~~~java
import java.util.Arrays;
import java.util.stream.DoubleStream;

public class DoubleMapMultiDemo {
    public static void main(String[] args) {
        double[] values = DoubleStream.of(
                1.5,
                Double.NaN,
                4.0,
                Double.POSITIVE_INFINITY,
                -2.0
            )
            .mapMulti((value, out) -> {
                if (Double.isFinite(value) && value > 0.0) {
                    out.accept(value);
                    out.accept(value / 2.0);
                }
            })
            .toArray();

        System.out.println(Arrays.toString(values));
        // [1.5, 0.75, 4.0, 2.0]
    }
}
~~~

When only an average is needed, you can chain the `average()` terminal operation:

~~~java
double average = DoubleStream.of(1.5, 4.0)
    .mapMulti((value, out) -> {
        out.accept(value);
        out.accept(value / 2.0);
    })
    .average()
    .orElseThrow();

// (1.5 + 0.75 + 4.0 + 2.0) / 4 = 2.0625
~~~

**Arithmetic note:** `double` uses IEEE 754 binary floating-point; not every decimal number can be represented exactly. Summing, averaging, and parallel combination ordering can lead to rounding discrepancies. Do not use `DoubleStream` assuming all monetary calculations are exact; for financial business rules, consider smallest-unit integers or `BigDecimal` depending on requirements.

## 6. Distinguishing `IntStream.mapMulti` from `Stream<T>.mapMultiToInt`

Two API naming groups are easy to confuse because both support emitting multiple primitive values:

| API | Input source | Output | When to use |
| --- | --- | --- | --- |
| `IntStream.mapMulti` | `IntStream` | `IntStream` | Already have `int` numbers and want to emit 0–n `int` values. |
| `LongStream.mapMulti` | `LongStream` | `LongStream` | Already have `long` numbers and want to emit 0–n `long` values. |
| `DoubleStream.mapMulti` | `DoubleStream` | `DoubleStream` | Already have `double` numbers and want to emit 0–n `double` values. |
| `Stream<T>.mapMultiToInt` | `Stream<T>` | `IntStream` | Input is objects, need to emit 0–n `int` values. |
| `Stream<T>.mapMultiToLong` | `Stream<T>` | `LongStream` | Input is objects, need to emit 0–n `long` values. |
| `Stream<T>.mapMultiToDouble` | `Stream<T>` | `DoubleStream` | Input is objects, need to emit 0–n `double` values. |

### Example: from order objects to long values

~~~java
import java.util.List;
import java.util.stream.LongStream;

public class PurchaseUnits {
    record OrderLine(String sku, long unitPrice, int quantity) {}

    public static void main(String[] args) {
        List<OrderLine> lines = List.of(
            new OrderLine("BOOK", 20_000L, 2),
            new OrderLine("PEN", 5_000L, 1),
            new OrderLine("PAD", 9_000L, 0)
        );

        LongStream prices = lines.stream()
            .mapMultiToLong((line, out) -> {
                if (line.quantity() < 0 || line.quantity() > 10_000) {
                    throw new IllegalArgumentException("Invalid quantity");
                }
                for (int i = 0; i < line.quantity(); i++) {
                    out.accept(line.unitPrice());
                }
            });

        long total = prices.sum();
        System.out.println(total); // 45000
    }
}
~~~

The source is `Stream<OrderLine>`, so **`mapMultiToLong`** must be used rather than calling `LongStream.mapMulti` directly. The transformed result is a `LongStream`, so `sum()` computes directly on `long`.

If the goal is merely total order value, there is no need to expand individual units:

~~~java
long total = lines.stream()
    .mapToLong(line ->
        Math.multiplyExact(line.unitPrice(), line.quantity())
    )
    .sum();
~~~

This illustrates the operation selection principle: write according to the **actual required output**, avoiding creating unnecessary elements.

### Example: parsing strings to int without boxing the output

~~~java
import java.util.List;

public class ParseScores {
    public static void main(String[] args) {
        List<String> raw = List.of(" 10 ", "bad", "", "25");

        int total = raw.stream()
            .mapMultiToInt((text, out) -> {
                try {
                    int score = Integer.parseInt(text.trim());
                    if (score >= 0) {
                        out.accept(score);
                    }
                } catch (NumberFormatException ignored) {
                    // Unparseable data; illustrative policy is to skip.
                }
            })
            .sum();

        System.out.println(total); // 35
    }
}
~~~

In problems that must **report errors** for invalid data, do not silently ignore them by omitting `accept`. Use a result type carrying the error reason or an explicit error-handling branch.

## 7. Comparison with primitive stream `map`, `filter`, and `flatMap`

| Operation | Output elements per input | Example | When appropriate |
| --- | --- | --- | --- |
| `map` | Always exactly 1 | `map(n -> n * 2)` | 1-to-1 numeric transformation. |
| `filter` | 0 or 1, keeping the input number itself | `filter(n -> n > 0)` | Only selecting or dropping numbers. |
| `flatMap` | 0 to many | `flatMap(n -> IntStream.range(0, n))` | Mapper naturally returns a sub-stream. |
| `mapMulti` | 0 to many | `mapMulti((n, out) -> out.accept(n))` | Want to push primitive values directly. |

Both pipelines below produce the sequence `[2, 20, 4, 40]`:

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] viaFlatMap = IntStream.rangeClosed(1, 4)
    .flatMap(n -> n % 2 == 0
        ? IntStream.of(n, n * 10)
        : IntStream.empty())
    .toArray();

int[] viaMapMulti = IntStream.rangeClosed(1, 4)
    .mapMulti((n, out) -> {
        if (n % 2 == 0) {
            out.accept(n);
            out.accept(n * 10);
        }
    })
    .toArray();

System.out.println(Arrays.equals(viaFlatMap, viaMapMulti)); // true
~~~

`flatMap` requires the mapper to return the corresponding `IntStream`, `LongStream`, or `DoubleStream`. `mapMulti` lets the callback emit each value directly, so the code is often more concise when each element conditionally emits a small number of values.

In terms of performance, `mapMulti` **can** avoid allocating a sub-stream per input and reduce some intermediate overhead. However, **there is no guarantee of zero allocation**: default implementations may use internal buffers and execute logic equivalent to `flatMap`. Benchmark if performance is the deciding factor; do not mass-replace `flatMap` on intuition alone.

### Converting between primitive types

`IntStream.mapMulti` only emits `int`. If the desired output is `long` or `double`, choose a type conversion step before or after accordingly:

~~~java
import java.util.stream.IntStream;

long sum = IntStream.of(1, 2, 3)
    .mapToLong(n -> (long) n)
    .mapMulti((value, out) -> {
        out.accept(value);
        out.accept(value * 1_000_000_000L);
    })
    .sum();

// Converted to LongStream before calling LongStream.mapMulti.
~~~

There is no `IntStream.mapMultiToLong` corresponding to `Stream<T>.mapMultiToLong`. When you need to emit multiple `long` values directly from an `int` element, consider `mapToLong(...).mapMulti(...)` or a clearer conversion method.

## 8. Lazy pipelines, encounter order, and short-circuiting

`mapMulti` is an **intermediate operation**. The lambda only runs when a terminal operation pulls data. On an ordered source like `IntStream.rangeClosed`, values flow through a sequential pipeline following the source's encounter order and the emission order within each callback.

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] output = IntStream.rangeClosed(1, 3)
    .mapMulti((n, out) -> {
        out.accept(n);
        out.accept(-n);
    })
    .toArray();

System.out.println(Arrays.toString(output));
// [1, -1, 2, -2, 3, -3]
~~~

Because Streams are lazy, merely constructing the pipeline without calling `toArray()`, `sum()`, or another terminal operation does not compute the elements. After a terminal operation, the Stream is consumed and cannot be reused.

### `limit` after `mapMulti` counts **outputs**

~~~java
int[] firstThree = IntStream.rangeClosed(1, 5)
    .mapMulti((n, out) -> {
        out.accept(n);
        out.accept(-n);
    })
    .limit(3)
    .toArray();

// [1, -1, 2]
~~~

`limit(3)` selects at most three **output elements**. It does not mean executing the mapper on exactly three **input elements**.

Do not write a mapper with an **infinite** loop expecting `limit` to automatically halt the loop inside the lambda. A callback may continue running its own statements after downstream has received enough data. Ensure every mapper invocation has finite, bounded runtime and emission count.

### `distinct`, `sorted`, and `unordered`

These operations continue to work on `IntStream`, `LongStream`, or `DoubleStream`:

~~~java
import java.util.Arrays;
import java.util.stream.IntStream;

int[] distinctSorted = IntStream.of(2, 1, 2, 3)
    .mapMulti((n, out) -> {
        out.accept(n);
        out.accept(n);
    })
    .distinct()
    .sorted()
    .toArray();

System.out.println(Arrays.toString(distinctSorted));
// [1, 2, 3]
~~~

With an ordered source, `mapMulti` preserves the relative order of emitted results. However, `unordered()` can relax ordering constraints; when running in parallel, callback execution order need not match source order. `sorted()` establishes a new ordering for the output data when a comparison criterion applies.

## 9. Parallel processing: independent and non-interfering lambdas

The Stream API rules for **behavioral parameters** still apply:

- **Stateless:** processing one element does not depend on mutable state modified while processing other elements.
- **Non-interfering:** the mapper does not modify the data source the Stream is traversing.
- **Do not rely on side effects:** do not use counter increments, writes to external lists, or I/O calls inside a mapper as a required part of the terminal result.

Example that is **unsafe** on a parallel stream:

~~~java
import java.util.ArrayList;
import java.util.List;
import java.util.stream.IntStream;

List<Integer> shared = new ArrayList<>();

int[] values = IntStream.range(0, 100_000)
    .parallel()
    .mapMulti((n, out) -> {
        shared.add(n); // Race condition on ArrayList.
        out.accept(n * 2);
    })
    .toArray();
~~~

`shared` is mutated from multiple tasks; `ArrayList` is not safe for concurrent writes from multiple threads. `mapMulti` does not make external mutations synchronized. The proper approach when only the result array is needed:

~~~java
int[] values = IntStream.range(0, 100_000)
    .parallel()
    .mapMulti((n, out) -> out.accept(n * 2))
    .toArray();
~~~

The Stream handles collecting results itself. Note that calculations can overflow `int` for large inputs, though this example remains in a safe range.

In a parallel pipeline, `forEach` does not guarantee action execution order even when the source has an encounter order. If results must follow source order, prefer collecting via `toArray()` or use `forEachOrdered` when actions must execute in order. Preserving order can limit performance, so weigh business requirements.

### Combining, performance, and aggregation

For summation, `IntStream.sum()` returns `int` and can overflow. If the total may exceed `int` range, convert to `long`:

~~~java
import java.util.stream.IntStream;

long safeRangeSum = IntStream.rangeClosed(1, 100_000)
    .mapMulti((n, out) -> out.accept(n))
    .asLongStream()
    .sum();

System.out.println(safeRangeSum); // 5_000_050_000
~~~

With `DoubleStream.sum()`, floating-point rounding discrepancies and parallel combination ordering must be accepted or addressed according to precision targets. There is no guarantee that parallel is faster: work-splitting overhead, result merging, fan-out volume, or small data sizes can degrade performance.

## 10. Complete example: validating unit counts via `IntStream.mapMulti`

Here is a simulated scenario: the system receives attempt counts per device for the day; negative counts and counts exceeding a quota are treated as input errors. Each valid device generates a sequence of attempt numbers. Results are analyzed with `summaryStatistics()`.

~~~java
import java.util.Arrays;
import java.util.IntSummaryStatistics;
import java.util.stream.IntStream;

public class PrimitiveFanOut {
    private static final int MAX_ATTEMPTS = 100;

    static IntStream expandAttempts(IntStream counts) {
        return counts.mapMulti((count, out) -> {
            if (count < 0 || count > MAX_ATTEMPTS) {
                throw new IllegalArgumentException(
                    "Invalid attempt count: " + count
                );
            }
            for (int attempt = 1; attempt <= count; attempt++) {
                out.accept(attempt);
            }
        });
    }

    public static void main(String[] args) {
        int[] attempts = expandAttempts(
            IntStream.of(0, 3, 2)
        ).toArray();

        System.out.println(Arrays.toString(attempts));
        // [1, 2, 3, 1, 2]

        IntSummaryStatistics stats = expandAttempts(
            IntStream.of(0, 3, 2)
        ).summaryStatistics();

        System.out.println(stats.getCount()); // 5
        System.out.println(stats.getSum());   // 9
        System.out.println(stats.getMin());   // 1
        System.out.println(stats.getMax());   // 3
        System.out.println(stats.getAverage()); // 1.8
    }
}
~~~

Key points to note:

1. `expandAttempts` takes an **`IntStream`**, so it uses `IntStream.mapMulti`.
2. `count = 0` emits 0 numbers; `count = 3` emits `1, 2, 3`; `count = 2` emits `1, 2`.
3. The two calls to `expandAttempts` receive **two fresh Streams**; do not reuse a Stream after running a terminal operation.
4. The mapper is independent per `count` and mutates no external data.
5. `summaryStatistics()` computes an aggregate summary without boxing each `int`.
6. `MAX_ATTEMPTS` caps the maximum number of elements emitted per input.

In a real system, if only the **total number of attempts** is needed, use `IntStream.sum()` or `mapToLong(...).sum()` after input validation; there is no need to expand the attempt sequence. Fan-out is only appropriate when downstream logic truly must process each individual attempt.

## 11. Common mistakes

### Mistake 1: forgetting `out.accept`

~~~java
int[] result = IntStream.of(1, 2, 3)
    .mapMulti((n, out) -> {
        int doubled = n * 2; // Computed, but never emitted.
    })
    .toArray();

// result is an empty array.
~~~

This compiles, yet the result is empty because the mapper never calls `accept`. The version that **achieves the goal**:

~~~java
int[] result = IntStream.of(1, 2, 3)
    .mapMulti((n, out) -> out.accept(n * 2))
    .toArray(); // [2, 4, 6]
~~~

A `mapMulti` lambda must call `accept` to emit elements. If the mapper never calls `accept`, the output for the current element is empty.

### Mistake 2: confusing `mapMulti` with `flatMap`

~~~java
// Wrong purpose: mapMulti does not accept a lambda returning IntStream.
// .mapMulti(n -> IntStream.of(n, -n))

// Right with mapMulti:
int[] values = IntStream.of(1, 2)
    .mapMulti((n, out) -> {
        out.accept(n);
        out.accept(-n);
    })
    .toArray(); // [1, -1, 2, -2]

// Right with flatMap:
int[] sameValues = IntStream.of(1, 2)
    .flatMap(n -> IntStream.of(n, -n))
    .toArray();
~~~

### Mistake 3: unbounded data expansion

~~~java
// Validate count before emitting that many elements:
int count = 3;

int[] values = IntStream.of(count)
    .mapMulti((n, out) -> {
        if (n < 0 || n > 10_000) {
            throw new IllegalArgumentException("Quota exceeded");
        }
        for (int i = 0; i < n; i++) {
            out.accept(i);
        }
    })
    .toArray();
~~~

A huge output volume can consume time and memory even when the transformation uses only primitives. Do not put an infinite loop inside a mapper expecting a short-circuiting terminal operation to guarantee stopping it.

### Mistake 4: treating `mapMulti` as an object-to-primitive conversion

~~~java
// For Stream<String>, you must call mapMultiToInt:
int[] parsed = List.of("1", "2").stream()
    .mapMultiToInt((text, out) ->
        out.accept(Integer.parseInt(text))
    )
    .toArray(); // [1, 2]
~~~

`IntStream.mapMulti` exists only on `IntStream`; `Stream<String>` has no method with this signature. For object sources, use the right `mapMultiToInt/Long/Double` variant.

### Mistake 5: assuming `mapMulti` automatically improves performance

Compared to `flatMap`, `mapMulti` can be easier to write and may reduce overhead when emitting few values, yet it still obeys the Stream contract, may use internal buffering, and does not guarantee better speed or memory usage in every application. Use a profiler/benchmark if that is the selection criterion.

### Mistake 6: mixing up value domains and precision

- `IntStream.sum()` can overflow `int`; consider `asLongStream().sum()` for large totals.
- `LongStream.sum()` can also overflow `long`; check data scale and arithmetic policy.
- `DoubleStream.sum()` is subject to rounding; `NaN` or infinity may appear if inputs are not filtered.
- Primitive streams do not represent `null` per element; if the source has missing data, define a handling rule when converting from objects/Optional to primitives.

## 12. Quick selection table and self-check questions

| Requirement | Operation to consider | Reason |
| --- | --- | --- |
| `int` to 0–n `int` | `IntStream.mapMulti` | Stays in primitive stream. |
| `long` to 0–n `long` | `LongStream.mapMulti` | Emits via `LongConsumer`. |
| `double` to 0–n `double` | `DoubleStream.mapMulti` | Emits via `DoubleConsumer`. |
| `Stream<Order>` to 0–n `long` | `mapMultiToLong` | Converts object source to primitive stream. |
| `Stream<String>` to 0–n `int` | `mapMultiToInt` | Parses and emits `int` directly. |
| One `int` to exactly one `int` | `map` | Expresses 1-to-1 transformation. |
| Only keep numbers matching a condition | `filter` | No need to produce new values. |
| Mapper already returns `IntStream` | `flatMap` | Suited for flattening sub-streams. |
| Only need total quantity | `sum`/`mapToLong(...).sum()` | Avoids unnecessary fan-out. |

Self-check:

1. **What type does `IntStream.mapMulti` return?** `IntStream`; the mapper accepts an `int` and an `IntConsumer`.
2. **If an element never calls `out.accept`, how many values are produced?** None.
3. **If an element calls `out.accept` twice, how many output elements are produced?** Two elements, in the order of the two calls inside the mapper.
4. **When the input is `Stream<String>` and an `IntStream` result is desired, what do you use?** `mapMultiToInt`.
5. **Is `boxed()` needed before calling `IntStream.mapMulti`?** No; one benefit is keeping the pipeline in primitive form.
6. **Does `limit(3)` after `mapMulti` limit three inputs or outputs?** It limits the number of **output** elements.
7. **Does `parallel().mapMulti(...)` allow incrementing a shared mutable variable?** No; the mapper must remain stateless and non-interfering.
8. **If only the sum of quantities is needed, should each value be emitted `quantity` times?** Usually no; summing directly is more appropriate.
9. **Is `mapMulti` always faster than `flatMap`?** No; the API may use internal buffers and performance depends on data, implementation, and actual workload.
10. **Should `DoubleStream` be treated as the default choice for exact monetary calculations?** No; choose a numeric type suited to rounding and precision policies.

**Takeaway:** `mapMulti` on **`IntStream`, `LongStream`, and `DoubleStream`** is a transformation from **one primitive value to 0–n primitive values of the same type**, emitted via `IntConsumer`, `LongConsumer`, or `DoubleConsumer`. For object inputs, use `Stream<T>.mapMultiToInt/Long/Double`. Keep mappers independent, emit finite counts, use appropriate terminal operations, and evaluate benefits against the actual needs of the pipeline.
