# Choosing BigDecimal for Exact Decimal Arithmetic Requirements in Java Streams

## 1. Problem and Goals

In Java, primitive streams such as `IntStream`, `LongStream`, and `DoubleStream` allow processing primitive integers and floating-point numbers without boxing each element. However, **the speed and convenience of `DoubleStream` do not equate to the ability to represent every decimal number accurately**.

If an application must handle **prices, invoices, taxes, interest rates, ratios requiring deterministic rounding rules, or decimal data that demands exact computation of the entered digits**, `BigDecimal` is usually more appropriate than `double`. The key distinctions are:

- `double` is a binary floating-point number according to IEEE 754, with a finite set of representable values; many decimal numbers such as `0.1` have no exact binary representation.
- `BigDecimal` stores a number as **unscaled integer × 10^(-scale)**, which allows it to preserve decimal values and addition/multiplication operations accurately, provided the input source is constructed properly and division/rounding operations are clearly designed.
- Java has `IntStream`, `LongStream`, and `DoubleStream`, **but no standard `BigDecimalStream`**. For `BigDecimal`, you typically use `Stream<BigDecimal>`, `map`, and `reduce`; when starting from a primitive stream, use `mapToObj(...)` to convert elements into `BigDecimal`.
- Converting a `double` result that already has precision error into `BigDecimal` **cannot automatically recover the exact decimal value originally intended by the business logic**.

The goal of this lesson is to understand when to choose `BigDecimal`, construct exact numbers from inputs, compute sums with Streams, apply scale and rounding in the right places, and avoid common pitfalls when using primitive stream APIs.

## 2. Why Is `double` Not Always Correct for Decimal Requirements?

`double` numbers use base 2. A number like `0.5` has a finite binary representation, whereas `0.1` and `0.2` do not. This approximation can become apparent when adding:

```java
System.out.println(0.1 + 0.2);
```

Output:

```text
0.30000000000000004
```

This is not “Java adding incorrectly”; it is a consequence of how finite binary numbers represent decimal values. `DoubleStream.sum()` also operates on `double`, so **it does not turn the calculation into exact decimal arithmetic**.

With `BigDecimal` created from decimal strings:

```java
BigDecimal a = new BigDecimal("0.1");
BigDecimal b = new BigDecimal("0.2");
BigDecimal result = a.add(b);
System.out.println(result.toPlainString());
```

Result:

```text
0.3
```

The second snippet is inside a method and requires importing `java.math.BigDecimal`. Here, the two values 0.1 and 0.2 are stored in decimal form exactly as written; the addition does not have to go through a `double` representation.

**You should not assume that `BigDecimal` automatically solves all precision issues.** Non-terminating decimal numbers such as `1 / 3` require specifying precision/scale and a rounding rule. Monetary rules such as “round per line or round after summing” remain business decisions, not self-guessed behavior of the data type.

## 3. When Should You Choose Which Type?

| Requirement | Typically Suitable Type/Stream | Reason |
| --- | --- | --- |
| Counting quantities, indices, integer values within `int` range | `int`, `IntStream` | Exact for integers within range; no boxing per element |
| Summing integers larger than `int` range but within `long` range | `long`, `LongStream` | Still exact integers within range |
| Measurement, scientific, or simulation data where binary approximation is acceptable | `double`, `DoubleStream` | Supports efficient floating-point computation |
| Currency, taxes, ratios requiring preserved decimal digits and clear rounding rules | `BigDecimal`, `Stream<BigDecimal>` | Scale-based decimal model and controlled exact arithmetic |
| Money represented as an integer of the smallest unit (e.g., cents/dong without further subdivision) | `long` / `LongStream` with overflow checking | Integers are also exact if unit conventions and bounds are controlled |
| Integers with magnitude exceeding `long` limits | `BigInteger` | Arbitrary-precision integers; no scale needed |

Choose `BigDecimal` when the requirement calls for decimal arithmetic **with exact digits and rounding behavior**, not merely because the data contains a decimal point. For scientific applications that need speed and tolerate error within defined bounds, `double` is often still the right choice.

Conversely, `BigDecimal` does not prevent design mistakes such as wrong rates, wrong rounding timing, mistaken unit conversions, or missing validation. Precision of the **numeric type** is only one part of **business** correctness.

## 4. Constructing `BigDecimal` Properly: Avoiding `double` Error Injection

### 4.1. Three Construction Approaches to Distinguish

```java
BigDecimal exact = new BigDecimal("0.1");
BigDecimal canonical = BigDecimal.valueOf(0.1);
BigDecimal binaryExpansion = new BigDecimal(0.1);
```

This snippet is inside a method and requires importing `BigDecimal`.

- `new BigDecimal("0.1")`: **creates an exact decimal number from text**; this is the clearest choice when receiving decimal values that require precision.
- `BigDecimal.valueOf(0.1)`: converts a `double` value using the string representation of `Double.toString(double)`; this usually yields `0.1` in this example. However, if upstream already computed with error, this method cannot know the original target value.
- `new BigDecimal(0.1)`: creates a BigDecimal representing **the exact binary approximation stored in the double**, so it usually contains many unexpected decimal digits.

**Safe rule:** monetary data read from files/JSON/databases or user input should be converted from a **decimal string** or an already meaningful decimal type, avoiding going through `double`. If a library already returns `double`, you must clearly understand the source's contract before choosing how to convert it.

### 4.2. Runnable Example: Seeing the Difference

Create `BigDecimalCreationDemo.java`:

```java
import java.math.BigDecimal;

public class BigDecimalCreationDemo {
    public static void main(String[] args) {
        BigDecimal fromText = new BigDecimal("0.1");
        BigDecimal viaValueOf = BigDecimal.valueOf(0.1);
        BigDecimal fromDouble = new BigDecimal(0.1);

        System.out.println("double sum=" + (0.1 + 0.2));
        System.out.println("decimal sum=" +
                new BigDecimal("0.1").add(new BigDecimal("0.2")));
        System.out.println("text=" + fromText.toPlainString());
        System.out.println("valueOf=" + viaValueOf.toPlainString());
        System.out.println("equal by value=" +
                (fromText.compareTo(viaValueOf) == 0));
        System.out.println("new double equals text=" +
                fromDouble.equals(fromText));
        System.out.println("converted late=" +
                BigDecimal.valueOf(0.1 + 0.2).toPlainString());
    }
}
```

Run on Java 17+:

```bash
javac BigDecimalCreationDemo.java
java BigDecimalCreationDemo
```

Output:

```text
double sum=0.30000000000000004
decimal sum=0.3
text=0.1
valueOf=0.1
equal by value=true
new double equals text=false
converted late=0.30000000000000004
```

The `converted late` value shows that **you should not add using `double` first and then convert to `BigDecimal` expecting it to fix the error automatically**. If the source consists of strings `"0.1"` and `"0.2"`, convert both to `BigDecimal` **before the addition**.

`BigDecimal.valueOf(long)` and `BigDecimal.valueOf(long unscaledValue, int scale)` are different APIs: when starting from integers, they construct exact values; for example, `BigDecimal.valueOf(12345L, 2)` corresponds to `123.45`.

## 5. No Primitive Stream for BigDecimal: Use `Stream<BigDecimal>`

The standard primitive streams include:

- `IntStream`: `int` values, with `sum()`, `average()`, `mapToObj(...)`.
- `LongStream`: `long` values, with similar operations for long integers.
- `DoubleStream`: `double` values, suitable for binary floating-point numbers.
- There is no `BigDecimalStream` in the standard Java library.

To sum decimal values, a common approach is:

```java
BigDecimal total = values.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

This snippet is inside a method, assuming `values` has type `List<BigDecimal>` or a compatible collection, and requires importing `java.math.BigDecimal`. `BigDecimal.ZERO` is the **identity value** for addition: `0 + x = x`. `BigDecimal::add` combines two elements into a sum.

For an empty stream, `reduce(BigDecimal.ZERO, ...)` returns `BigDecimal.ZERO`; there is no need to call `Optional.get()` and no case of a missing sum.

When the data is primitive but each unit needs to be converted to decimal, use `mapToObj(...)` instead of continuing with `DoubleStream`:

```java
BigDecimal total = IntStream.of(10, 20, 30)
        .mapToObj(cents -> BigDecimal.valueOf(cents, 2))
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

This snippet is inside a method with imports for `IntStream` and `BigDecimal`. The integers 10, 20, 30 represent the **smallest unit**; `BigDecimal.valueOf(cents, 2)` corresponds to 0.10, 0.20, 0.30; the total is `0.60`. This is a conversion from an **exact int** to an exact BigDecimal, unlike converting from an approximate `double` value.

If you want to continue processing BigDecimal values with `map` or `filter`, Stream methods work normally; there is simply no `BigDecimalStream.sum()` convenience method in standard Java. Use `reduce` with an appropriate operation.

## 6. Standalone Example: Summing Decimals with Stream and from Cents

Create the file `BigDecimalStreamDemo.java`:

```java
import java.math.BigDecimal;
import java.util.List;
import java.util.stream.IntStream;

public class BigDecimalStreamDemo {
    public static void main(String[] args) {
        List<BigDecimal> prices = List.of(
                new BigDecimal("10.25"),
                new BigDecimal("0.10"),
                new BigDecimal("2.65")
        );

        BigDecimal total = prices.stream()
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal fromCents = IntStream.of(1025, 10, 265)
                .mapToObj(cents -> BigDecimal.valueOf(cents, 2))
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        System.out.println("total=" + total.toPlainString());
        System.out.println("cents total=" + fromCents.toPlainString());
        System.out.println("empty=" +
                List.<BigDecimal>of().stream()
                        .reduce(BigDecimal.ZERO, BigDecimal::add));
    }
}
```

Compile/run:

```bash
javac BigDecimalStreamDemo.java
java BigDecimalStreamDemo
```

Output:

```text
total=13.00
cents total=13.00
empty=0
```

Analysis:

1. The numbers are created from strings so they have exact decimal representation.
2. `BigDecimal::add` is used to accumulate each element into the sum; 10.25 + 0.10 + 2.65 equals 13.00.
3. `mapToObj` converts integer cents into `BigDecimal` with scale 2. The value from `1025` cents is 10.25.
4. For an empty source, the identity `BigDecimal.ZERO` has scale 0 so it prints `0`, **not automatically `0.00`**. If business requirements want to display two decimal places, you can normalize the total with `setScale(2)` at the output boundary.

**Do not confuse:** `IntStream.sum()` returns `int` and addition can overflow the value range; `LongStream.sum()` can also overflow `long`. When monetary requirements may exceed primitive limits, `BigDecimal` is an appropriate choice, or overflow and bounds must be controlled by business logic.

## 7. Invoice Calculation: Subtotal, Tax, and Rounding

A practical application often consists of line items with integer quantities and decimal unit prices. You can convert each line into a line amount, then sum them using BigDecimal.

Save the file `DecimalInvoiceDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;
import java.util.Objects;

public class DecimalInvoiceDemo {
    record Line(String sku, int quantity, BigDecimal unitPrice) {
        Line {
            Objects.requireNonNull(sku);
            Objects.requireNonNull(unitPrice);
            if (quantity < 0) {
                throw new IllegalArgumentException("Negative quantity");
            }
        }

        BigDecimal amount() {
            return unitPrice.multiply(BigDecimal.valueOf(quantity));
        }
    }

    public static void main(String[] args) {
        List<Line> lines = List.of(
                new Line("BOOK", 2, new BigDecimal("19.99")),
                new Line("PEN", 3, new BigDecimal("5.00")),
                new Line("BAG", 1, new BigDecimal("14.99"))
        );

        BigDecimal subtotal = lines.stream()
                .map(Line::amount)
                .reduce(BigDecimal.ZERO, BigDecimal::add);

        BigDecimal taxRate = new BigDecimal("0.075");
        BigDecimal tax = subtotal.multiply(taxRate)
                .setScale(2, RoundingMode.HALF_UP);
        BigDecimal grandTotal = subtotal.add(tax);

        System.out.println("subtotal=" + subtotal.toPlainString());
        System.out.println("tax=" + tax.toPlainString());
        System.out.println("total=" + grandTotal.toPlainString());
    }
}
```

Run:

```bash
javac DecimalInvoiceDemo.java
java DecimalInvoiceDemo
```

Output:

```text
subtotal=69.97
tax=5.25
total=75.22
```

Steps:

- `19.99 × 2 = 39.98`; `5.00 × 3 = 15.00`; `14.99 × 1 = 14.99`; the subtotal is `69.97`.
- A 7.5% tax is represented as the rate `0.075`, not `7.5`. The product `69.97 × 0.075 = 5.24775`.
- In this example, the **assumed business rule** is to round the tax amount to 2 decimal places using `HALF_UP`, so the tax becomes `5.25`.
- The grand total is `69.97 + 5.25 = 75.22`.

You cannot infer a universal tax rounding rule for all countries, invoices, or organizations from this example. You must follow actual regulations and business requirements: whether to round per line or across the whole invoice, how many decimal places the currency has, and how refunds and tax rates are handled. A model storing prices should explicitly declare its expected currency and scale.

**Note:** using `Stream<BigDecimal>` to compute line amounts does not mutate the `Line` objects. `BigDecimal` is immutable: methods like `add`, `multiply`, and `setScale` return a **result object** without modifying the receiver itself.

## 8. Scale, Precision, and Representation: Why Does `equals` Differ from `compareTo`?

`BigDecimal` represents a value using an unscaled part and a scale. For example:

```text
1.0  = 10   × 10^(-1)   (scale 1)
1.00 = 100  × 10^(-2)   (scale 2)
```

They are equal in **numeric value** but have different representations and scales. Therefore:

- `a.compareTo(b) == 0` checks equality by **numeric value**.
- `a.equals(b)` considers both value and scale; two BigDecimals with different scales may not be `equals` even if `compareTo` returns 0.
- `a.setScale(2, roundingMode)` sets the result scale according to the rule; if no value change is needed, no rounding is required.
- `precision()` is the number of digits in the unscaled value (by BigDecimal's definition), which is **different** from `scale()`, the number of digits to the right of the decimal point (which can be negative).

Standalone runnable example—create `BigDecimalScaleDemo.java`:

```java
import java.math.BigDecimal;
import java.math.RoundingMode;
import java.util.List;

public class BigDecimalScaleDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("1.0");
        BigDecimal b = new BigDecimal("1.00");

        System.out.println("compare=" + a.compareTo(b));
        System.out.println("equals=" + a.equals(b));
        System.out.println("a scale=" + a.scale());
        System.out.println("b scale=" + b.scale());
        System.out.println("rounded=" +
                new BigDecimal("1.005")
                        .setScale(2, RoundingMode.HALF_UP));
        System.out.println("distinct=" +
                List.of(a, b).stream().distinct().count());
    }
}
```

Run:

```bash
javac BigDecimalScaleDemo.java
java BigDecimalScaleDemo
```

Output:

```text
compare=0
equals=false
a scale=1
b scale=2
rounded=1.01
distinct=2
```

Stream takeaway: `distinct()` relies on `equals` (and hash code) to determine duplicate elements, so it can retain both `1.0` and `1.00`; meanwhile, `sorted()` in natural order uses `compareTo` and treats them as equal in ordering. If an application requires deduplicating decimals by **numeric value** rather than including scale, you must normalize them or build an appropriate comparison/grouping mechanism; do not assume the two concepts are identical.

A representation like `0.00` often carries meaning for displaying money; `stripTrailingZeros()` can change the scale and how it prints (including scientific notation). Do not call it arbitrarily before exporting data or using it as a HashMap key if scale is part of the contract.

## 9. Division and Rounding Rules: Where Explicit Decisions Are Needed

Adding and multiplying `BigDecimal` values can produce exact decimal results for finite inputs, whereas division can have a **non-terminating** fractional part. For example, `1 / 3` does not have a finite number of decimal digits.

```java
BigDecimal one = BigDecimal.ONE;
BigDecimal three = BigDecimal.valueOf(3);

// Division without specifying rounding for a non-terminating quotient:
// one.divide(three); // throws ArithmeticException at runtime.

BigDecimal ratio = one.divide(
        three, 4, RoundingMode.HALF_UP); // 0.3333
```

This is an illustrative snippet inside a method and requires importing `BigDecimal` and `RoundingMode`. When choosing `scale = 4`, Java keeps four digits after the decimal point. If the business requires a 2-digit result, choose scale 2. If rounding by overall precision (number of significant digits) is required, you can use `MathContext` with a precision and rounding mode; **MathContext precision is not the same as scale**.

Some common rounding modes:

| RoundingMode | General Meaning |
| --- | --- |
| `HALF_UP` | At an exact half-way tie, rounds away from 0 |
| `HALF_EVEN` | At an exact half-way tie, chooses the even last digit; often called banker’s rounding |
| `DOWN` | Drops digits beyond scale, rounding toward 0 |
| `UP` | Rounds away from 0 if any non-zero digits are dropped |
| `UNNECESSARY` | Throws an error if the operation would require rounding |

There is no one-size-fits-all rule. `HALF_UP` is easy to explain for many billing models, but it is not automatically right for every accounting system. `HALF_EVEN` can be useful when you need to reduce cumulative bias across many rounding operations, though it must match the actual contract.

### Avoid Premature Rounding in a Reducer

BigDecimal addition **does not round** with the signature `add(BigDecimal)`—it is an exact operation, well suited for `reduce(BigDecimal.ZERO, BigDecimal::add)`. Do not add `setScale(2, ...)` at *every* reduce step if the requirement is to sum all values exactly first and round the result afterward.

Consider three values of 0.005: the exact sum is `0.015`, which then rounds to 2 decimal places using `HALF_UP` as `0.02`. However, if each 0.005 is rounded to 0.01 before summing, the total becomes `0.03`. Both can be valid business rules in different contexts; **do not arbitrarily change where rounding occurs when refactoring from a loop to a Stream**.

## 10. Reduce, Parallel Streams, and Operation Associativity

Common signature:

```java
T reduce(T identity, BinaryOperator<T> accumulator)
```

The function used to combine elements must be **associative** and have a suitable identity so that Stream can process it validly, especially when splitting into chunks in a parallel stream. Exact addition `BigDecimal::add` with identity `BigDecimal.ZERO` is a natural choice:

```java
BigDecimal sum = prices.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

If the same data is processed with `parallelStream()`, exact addition still remains consistent in numeric value for non-null inputs. However, chunking, scale state, and object allocation overhead do not automatically make parallel faster; measure on real workloads and verify representation/scale contracts if that matters.

**Avoid accumulators with shared side effects:**

```java
// Avoid using a mutable holder / sharing an external variable:
AtomicReference<BigDecimal> holder = new AtomicReference<>(BigDecimal.ZERO);
prices.parallelStream().forEach(x ->
        holder.updateAndGet(current -> current.add(x)));
```

This illustrates **what to avoid** and requires importing `AtomicReference`; it may work correctly for updates thanks to atomicity, but it is hard to read, creates contention under parallelism, and is unnecessary. Prefer `reduce` or an appropriate collector. In particular, BigDecimal is immutable, so `sum.add(x)` **does not** modify `sum`: you must use the returned value.

If you use division, subtraction, or per-step rounding inside a reducer, they are not necessarily associative. The result may depend on combination order, especially in parallel. Keep the combination exact if possible and place the rounding step where the business logic requires it.

A clean and testable pattern:

```java
BigDecimal total = prices.stream()
        .filter(java.util.Objects::nonNull)
        .reduce(BigDecimal.ZERO, BigDecimal::add)
        .setScale(2, RoundingMode.HALF_UP);
```

This snippet assumes `prices` may contain null and **business rules allow ignoring null**. If null means invalid data, you must throw an error/validate instead of silently filtering. Do not use `List.of(...)` to create a list containing null, because that API does not allow null elements.

## 11. Inputs, Formatting, and Currency Units

Choosing `BigDecimal` is not enough if the source and units are not clarified:

1. **Input data:** for the string `"12.30"`, create `new BigDecimal("12.30")` to preserve the exact decimal. For locale-specific thousands/decimal separators, parse with locale-aware configuration; the `BigDecimal(String)` constructor does not automatically understand every language format.
2. **JSON/API:** if a library parses JSON numbers into `double` first and then passes them to the application, you may have already lost the original decimal meaning. Use an appropriate parser configuration / decimal model, such as reading a decimal string or a `BigDecimal` type when the API supports it.
3. **Database:** SQL `DECIMAL/NUMERIC` types can map to `BigDecimal`; check the column and driver's precision/scale.
4. **Currency:** units such as VND, USD, JPY, etc. have different decimal-digit rules. Scale 2 in the examples is only an **illustrative assumption**, not a rule for all currencies.
5. **Negative values and refunds:** rounding rules must be tested on both positive and negative numbers; `HALF_UP`, `UP`, and `DOWN` have different directional meanings.
6. **Empty data:** the sum of an empty stream with identity `BigDecimal.ZERO` is `0`; if outputting in a two-decimal currency format, normalize at the boundary with `setScale(2, ...)` or an appropriate formatter.
7. **Wrong unit:** the same numeric value `100` differs across “100 dong”, “100 cents”, and “100 points”. Use models and variable names that clearly state the unit; `BigDecimal` does not know the currency on its own.

In cases where all monetary amounts belong to a fixed smallest unit, representing them in cents (`long`) is also an exact option, provided the range does not overflow and no smaller unit arises. For example, `12345` cents can be represented as `BigDecimal.valueOf(12345L, 2) == 123.45` in value. When calculating ratios or dividing, you may need to convert to decimal and choose rounding according to business rules.

## 12. API Differences Between `Stream<BigDecimal>` and `DoubleStream`

| Item | `DoubleStream` | `Stream<BigDecimal>` |
| --- | --- | --- |
| Element | `double` | `BigDecimal` object |
| Arithmetic | Binary, often approximate | Exact decimal with appropriate operations |
| Sum | `sum()` | `reduce(BigDecimal.ZERO, BigDecimal::add)` |
| Average | `average()` returns `OptionalDouble` | Compute sum/count then `divide(...)` with rounding |
| Scale preservation | No decimal scale | Has `scale()`, `setScale(...)` |
| Performance/memory | Advantageous when processing large volumes of numbers suited to approximation | Typically more objects and more expensive operations |
| Best suited for | Measurements, simulations, approximate floats | Money, taxes, exact business decimals |

For the average of a set of BigDecimals, you must first decide how to handle an **empty stream**. If there are n elements, compute the BigDecimal sum and divide by n with a defined scale/rounding. You cannot call `BigDecimal.divide(BigDecimal.valueOf(n))` without rounding and expect every case to succeed: many quotients do not have a finite decimal representation.

To avoid traversing the stream twice, you can use a collector/accumulator that tracks both sum and count. A stream should only be used in one pipeline with a single terminal operation; do not reuse the same stream to call `count()` and then `reduce()` a second time. Create a new stream from the collection if needed, or use a properly designed accumulator.

## 13. Common Mistakes

1. **Using `DoubleStream.sum()` and expecting an exact decimal sum.** `double` is a binary floating-point number and does not guarantee exact decimal digits.
2. **Creating `BigDecimal` with `new BigDecimal(0.1)`.** It receives the exact binary approximation of 0.1; prefer a decimal string or exact decimal input.
3. **Converting to BigDecimal after already adding with double.** `BigDecimal.valueOf(0.1 + 0.2)` holds `0.30000000000000004`; convert each value accurately before computing.
4. **Looking for `BigDecimalStream.sum()` in standard Java.** It does not exist; use `Stream<BigDecimal>.reduce(...)`.
5. **Forgetting scale and formatting.** `0` differs in presentation from `0.00`; scale conventions must be decided at the appropriate boundary.
6. **Using `equals` to compare numeric values while ignoring scale.** `1.0` and `1.00` have `compareTo == 0` but `equals == false`.
7. **Dividing decimals without specifying rounding.** `1 / 3` using divide without rounding will throw `ArithmeticException`.
8. **Rounding at every reduce step without reason.** It can change the total compared to rounding before/after; moreover, the combination operation may no longer be associative.
9. **Using a mutable holder in a parallel stream.** Increases the risk of race conditions/side effects and synchronization overhead; prefer `reduce` with an appropriate combiner.
10. **Choosing scale 2 for every currency.** You must determine the unit, currency, and legal/business rules first.
11. **Ignoring integer overflow when using cents.** `int` and `long` have limits; choose the range carefully and check for overflow.
12. **Assuming `BigDecimal` automatically knows which values are valid.** Negative data, wrong tax rates, and mismatched currencies still must be validated.
13. **Mixing `BigDecimal` and `double` without control.** A `map` step computing with `double` can introduce error into the pipeline even if the final step uses `BigDecimal`.
14. **Thinking `BigDecimal.add` mutates the receiver.** BigDecimal is immutable; always keep the returned result of the operation.
15. **Treating every floating-point problem as requiring BigDecimal.** For calculations where approximation is acceptable and speed is critical, `double` may be more suitable.

## 14. Self-Check Exercise

Given a stream of decimal values:

```java
List<BigDecimal> values = List.of(
        new BigDecimal("0.10"),
        new BigDecimal("0.20"),
        new BigDecimal("0.30")
);

BigDecimal total = values.stream()
        .reduce(BigDecimal.ZERO, BigDecimal::add);
```

This snippet is inside a method and requires importing `List` and `BigDecimal`.

**Questions:**

1. What does `total.toPlainString()` produce and why?
2. Does switching to `DoubleStream.of(0.1, 0.2, 0.3).sum()` preserve the same exact decimal contract?
3. If the stream is empty, what does the reducer above return and what is its scale?
4. For `new BigDecimal("2.0")` and `new BigDecimal("2.00")`, do `equals` and `compareTo` give the same conclusion?
5. Why does computing the ratio `1 / 3` require scale/rounding?

**Answers:**

1. `0.60`, because the numbers are constructed accurately in decimal and the largest scale among the additions is 2.
2. No. The `double` result still belongs to the binary floating-point model, even if it happens to be rounded for display into a familiar number.
3. `BigDecimal.ZERO`, which prints `0` and has scale 0. You can apply `setScale(2)` if a monetary representation like `0.00` is needed.
4. `equals` returns false because the scales differ; `compareTo` returns 0 because the numeric values are equal.
5. Because the decimal quotient is non-terminating, so an exact BigDecimal with finite scale cannot be returned without a rounding policy.

## 15. Checklist Before Choosing `BigDecimal` in a Stream

- **Is the input data truly an exact decimal?** Avoid converting an already-inaccurate `double` value while expecting to restore its original state.
- **Are the units clearly stated?** Price, smallest currency unit, quantity, and rate need to be distinguished.
- **Is the number construction appropriate?** Prefer decimal strings, `BigDecimal.valueOf(long)`, or `valueOf(unscaled, scale)` from exact integers.
- **Is the aggregation operation correct?** For sums, use `reduce(BigDecimal.ZERO, BigDecimal::add)`; do not use an accumulator that shares mutable state.
- **Is there any division?** Explicitly specify scale or `MathContext`, rounding mode, and behavior when dividing by 0.
- **At which stage does rounding happen?** Per line, after summing, or on the final result is a business decision; do not arbitrarily move its position.
- **Do you need comparison by value or by representation as well?** `compareTo` differs from `equals`; Stream's `distinct()` relies on equality.
- **Does the result need formatting?** `BigDecimal.toPlainString()` and scale express the decimal, while displaying money requires an appropriate formatter/currency.
- **Is performance acceptable?** BigDecimal is generally more expensive than primitive arithmetic; measure after ensuring correctness.

**Conclusion:** When calculations must be exact in decimal, choose `BigDecimal` right from the **data source** and keep additions/multiplications in `Stream<BigDecimal>`; convert from primitive integers using `mapToObj` when there is a clear smallest unit. For division, rounding, scale, and currency, document them as explicit rules. `DoubleStream` is a great tool for binary floating-point numbers where approximation is acceptable, but it is not a tool that guarantees decimal precision.

**References:** Java SE API `java.math.BigDecimal`, `java.math.MathContext`, `java.math.RoundingMode`; `java.util.stream.Stream.reduce`, `java.util.stream.IntStream`, `java.util.stream.DoubleStream`; Java Language Specification on floating-point values.