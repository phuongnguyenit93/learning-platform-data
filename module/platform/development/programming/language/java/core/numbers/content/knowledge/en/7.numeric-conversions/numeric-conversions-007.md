# Narrowing `double` to `float` and Precision Loss in Java

In Java, `double` and `float` are both IEEE 754 binary floating-point types, yet they **differ in bit width and representable range**. Casting `double` to `float` is a *narrowing primitive conversion*. The cast is permitted using `(float)` syntax, but it can **round, lose precision bits, lose the ability to distinguish two values, turn into infinity, or become zero**.

```java
double original = 0.1;
float narrowed = (float) original;
double widenedAgain = narrowed;

System.out.println(original);             // 0.1
System.out.println(narrowed);             // 0.1
System.out.println(widenedAgain);         // 0.10000000149011612
System.out.println(original == widenedAgain); // false
```

On the surface both of the first two lines print `0.1`, yet they **do not hold the same binary value**. The sections below explain what happens, when it is safe, how to detect information loss, and how to choose types for real-world problems.

## 1. How do `double` and `float` differ?

| Property | `float` (binary32) | `double` (binary64) |
| --- | --- | --- |
| Storage size | 32 bits | 64 bits |
| Sign bit | 1 | 1 |
| Stored exponent bits | 8 | 11 |
| Stored fraction bits | 23 | 52 |
| Significand precision with implicit bit for normal numbers | 24 bits | 53 bits |
| Approximate decimal digits commonly used as an estimate | ~6–7 significant digits | ~15–16 significant digits |
| Largest finite positive number | Approx. `3.4028235 × 10^38` | Approx. `1.7976931348623157 × 10^308` |
| Smallest normal positive number | `Float.MIN_NORMAL`, approx. `1.17549435 × 10^-38` | `Double.MIN_NORMAL`, approx. `2.2250738585072014 × 10^-308` |
| Smallest nonzero positive number (subnormal) | `Float.MIN_VALUE`, approx. `1.4 × 10^-45` | `Double.MIN_VALUE`, approx. `4.9 × 10^-324` |

**Note:** `Float.MIN_VALUE` is **not** the negative number with the largest magnitude. It is the **smallest nonzero positive number** representable by `float`. For the finite negative value with the largest magnitude, use `-Float.MAX_VALUE`. Both types also have `+0.0`, `-0.0`, `NaN`, `+Infinity`, and `-Infinity`.

`float` is not simply "`double` printed with fewer digits." It has only 24 significand bits and a much smaller exponent range. When converting from binary64 to binary32, Java must pick a value representable in the **`float` value set**, rather than keeping all bits present in `double`.

## 2. Syntax: why is an explicit cast needed?

Converting from `float` up to `double` is a *widening primitive conversion*: Java permits it implicitly. Converting from `double` down to `float` is narrowing: in variable assignments, an explicit cast is required.

```java
float measurement = 12.5f;
double widened = measurement; // Allowed implicitly.

double source = 12.5;
// float invalid = source;     // Compile error: possible lossy conversion.
float narrowed = (float) source; // Valid.
```

For literals, `1.25` defaults to `double`, while the `f` or `F` suffix selects a `float` literal:

```java
float a = 1.25f;       // float literal.
float b = (float) 1.25; // Cast double literal to float.
double c = 1.25;       // double literal.
```

The `f` suffix is **not** a way to ignore precision loss: it indicates that the literal is evaluated as a `float` value. For example, `0.1f` is still a binary approximation of 0.1, not exact mathematical 0.1.

### When casts appear indirectly

- When **passing arguments**: a method taking `float` does not automatically accept a `double` variable.
- When **returning results**: a method declared to return `float` cannot `return` a `double` variable without a cast.
- When **assigning to a `float[]` element** or `float` field: narrowing conversion is required.
- In **compound assignment operators** like `+=`, Java has an implicit conversion rule that can mask precision loss.

```java
float sum = 0.1f;
double step = 0.2;

// sum = sum + step; // Does not compile: float + double expression has type double.
sum += step;         // Compiles; semantically roughly sum = (float)(sum + step).
```

This special compound-assignment rule does not guarantee an exact result. Avoid using it to obscure a narrowing decision in financial calculations or error-sensitive algorithms.

## 3. What does Java do when converting `double` to `float`?

Under floating-point conversion rules, Java converts a `double` value to a `float` representation:

1. If it is **NaN**, the result remains `float` NaN.
2. If it is **+Infinity** or **-Infinity**, the result preserves the corresponding infinity.
3. If it is **+0.0** or **-0.0**, the result preserves the sign of zero.
4. If it is a **finite** value, Java rounds to the nearest representable `float` value using *round-to-nearest, ties-to-even*; if it exceeds the upper threshold, the result can be infinity; if it is too close to 0, it can be a subnormal number or signed zero.

Ordinary floating-point narrowing **does not throw `ArithmeticException` for overflow or precision loss**. The target type has `Infinity` and `0.0` values to hold the corresponding rounded results.

For values within the normal range, losing precision means two distinct `double` values can convert to the same `float`. This is **not a flaw in the cast syntax**; it is a limitation of 32-bit representation.

### Why do some values still convert accurately?

Numbers like `0.5`, `1.25`, and `12.5` have short finite binary expansions, so `float` can represent them accurately. By contrast, `0.1` has an infinite repeating binary expansion; both `double` and `float` can only store approximations.

As for integers: `float` with a 24-bit significand represents **every integer** up to magnitude `2^24 = 16_777_216`, but cannot represent **every integer** above this milestone. Larger integers can still be represented exactly if they align with the spacing between adjacent `float` numbers.

## 4. Noticeable precision loss: `0.1` and 16,777,217

### 4.1. `0.1`: printed output does not show all bits

```java
double source = 0.1d;
float smaller = (float) source;

System.out.println(source);           // 0.1
System.out.println(smaller);          // 0.1
System.out.println((double) smaller); // 0.10000000149011612
```

`System.out.println(float)` uses a decimal representation that round-trips back to the exact `float` value. Printing `0.1` **does not prove** the variable stores exact decimal 0.1. When converting `smaller` back to `double`, all bits of the **current `float` value** are preserved exactly in `double`, making the difference visible.

- `source`: binary64 approximation of 0.1.
- `smaller`: binary32 approximation of 0.1.
- `(double) smaller`: exact expression of that binary32 value in binary64.

**Casting back `float -> double` does not recover bits lost from `source`.** This is the difference between "widening the container" and "restoring information."

### 4.2. The integer 16,777,217 loses one unit

```java
double original = 16_777_217.0;
float rounded = (float) original;

System.out.println(original); // 1.6777217E7
System.out.println(rounded);  // 1.6777216E7
```

`double` has enough significand bits to represent 16,777,217 exactly. In this range, `float` has a spacing of 2 between adjacent representable numbers; 16,777,217 lies halfway between 16,777,216 and 16,777,218. With *ties-to-even*, the chosen result is **16,777,216**.

The core point is not that every value beyond 16,777,216 is wrong, but that **the resolution of `float` grows coarser as magnitude increases**.

## 5. The ULP concept and resolution at a given magnitude

*ULP* (*unit in the last place*) describes the spacing between consecutive representable numbers in a region. Java provides `Math.ulp(float)` and `Math.ulp(double)`.

```java
System.out.println(Math.ulp(1.0f)); // 1.1920929E-7
System.out.println(Math.ulp(1.0d)); // 2.220446049250313E-16
```

Near 1.0, the quantization step of `float` is around 0.000000119, whereas `double` is much smaller. As values grow large, the ULP grows larger; there is no fixed "absolute precision" across all ranges.

For example:

```java
float a = 16_777_216f;
float b = a + 1.0f;
System.out.println(a == b); // true: adding 1 cannot change the float value here.
```

This is not a bug in the `+` operator. The mathematical result falls between two representable `float` values and rounds to one of them. When accumulating many values, repeated roundings can increase error or make results depend on addition order.

### How many decimal digits can you trust?

The phrase "`float` has about 7 digits, `double` has about 15 digits" is only an **accuracy estimate**, not a guarantee that *any* 7 digits after the decimal point are exact. **Significant** digits differ from digits **after the decimal point**; error depends on magnitude, operations, and spacing between representable numbers.

If data must distinguish two values differing by 0.001 in the billions range, `float` is typically unsuitable. Compute the upper bound of your data and the required resolution in real-world units.

## 6. Out of range: infinity, subnormal, and zero

Precision is not the only risk. `float` has a narrower exponent range than `double`.

### 6.1. Overflow to infinity

```java
double huge = 1.0e40;       // finite double.
float f = (float) huge;     // +Infinity.

System.out.println(f);                    // Infinity
System.out.println(Float.isInfinite(f));  // true
```

`1.0e40` is smaller than `Double.MAX_VALUE` yet vastly larger than `Float.MAX_VALUE`. The cast does not clamp automatically to `Float.MAX_VALUE` and does not throw an exception.

To check whether a result is finite, use `Float.isFinite(f)`; to check specifically for infinity, use `Float.isInfinite(f)`.

### 6.2. Underflow: collapsing to 0 or subnormal numbers

```java
double tiny = 1.0e-50;
float zero = (float) tiny;
System.out.println(zero); // 0.0

double small = 1.0e-40;
float subnormal = (float) small;
System.out.println(subnormal); // 1.0E-40
```

`1.0e-50` is too close to 0 to have a nonzero `float` under rounding rules, so the result is `0.0f`. `1.0e-40` can still become a **subnormal** `float` value (smaller than `Float.MIN_NORMAL` yet nonzero), though it usually loses many digits of relative precision.

In other words, underflow does not always produce 0 immediately: there is a subnormal region, at the cost of gradually decreasing relative precision as values approach 0.

### 6.3. NaN and the two signed zeros

```java
float notANumber = (float) Double.NaN;
System.out.println(Float.isNaN(notANumber)); // true

float negativeZero = (float) -0.0d;
System.out.println(1.0f / negativeZero); // -Infinity
```

`0.0f == -0.0f` is `true` under arithmetic comparison, yet the sign of zero can affect division and certain bit-level APIs. `NaN` does not compare equal to itself with `==`; use `Float.isNaN` instead of `value == Float.NaN`.

## 7. Information loss can propagate through mixed expressions

Java performs *binary numeric promotion* when two arithmetic operands have different types: if `double` is present, the expression is normally evaluated in `double`. However, **converting to `double` after `float` has already lost information does not recover the original value**.

```java
float f = (float) 0.1d;
double result = f + 0.2d;
System.out.println(result); // 0.30000000149011613
```

In the `+` operation above, `f` is widened to `double` and then added to `0.2d`. The value of `f` remains the binary32 approximation of 0.1. If a calculation chain needs `double` from the start, avoid casting down to `float` at an intermediate step.

### When calling methods and APIs

```java
static float narrowMeasurement(double input) {
    return (float) input; // Potentially lossy decision is made explicit.
}
```

This is an illustrative method; place it inside a class. When an external API requires `float` (such as graphics buffers, networking, or data-processing libraries), place the cast at the **data-handoff boundary** and validate bounds there. Avoid switching your entire application internals to `float` just because the target storage layer uses `float`.

With `float[]` in particular, storing a sequence of narrowed `double` values means all samples in the array are bounded by binary32 precision, even if later read back as `double`.

## 8. How do you know whether narrowing is "safe"?

The word "safe" can carry three different meanings:

1. **No unexpected NaN/infinity or zero**: requires range limits and finite values.
2. **Exact preservation of the same arithmetic value**: checks whether converting to `float` and widening back equals the original value, keeping special handling for NaN and signed zero in mind.
3. **Error within business tolerance**: requires absolute/relative tolerances, data units, and model testing; this is the practical criterion for many numerical algorithms.

### 8.1. Checking for finite values and overflow to infinity

```java
static float requireFiniteFloat(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Input must be finite");
    }
    float narrowed = (float) value;
    if (!Float.isFinite(narrowed)) {
        throw new IllegalArgumentException("Outside finite float range");
    }
    return narrowed;
}
```

This method rejects **non-finite inputs** and results that **overflow to Infinity**. It **does not** guarantee preserving every bit and **does not** reject underflow to 0 or rounding.

If business rules do not want to reject `NaN` or infinity, define the contract for them rather than assuming "every NaN is an error."

### 8.2. Checking whether arithmetic value is lost

```java
static float requireExactFiniteFloat(double value) {
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("Input must be finite");
    }
    float narrowed = (float) value;
    if (!Float.isFinite(narrowed) || (double) narrowed != value) {
        throw new IllegalArgumentException("Not exactly representable as float");
    }
    return narrowed;
}
```

For **finite** values where arithmetic equality is the criterion, a round-trip comparison like this detects whether rounding changed the value. For example:

- `1.25d` converts exactly to `float`.
- `0.1d` does not preserve its `double` value when converted.
- `16_777_217d` is not preserved either.
- `1.0e40` becomes infinity and is rejected.
- `1.0e-50` becomes 0, differs from the original value, and is rejected.

The `==` check on finite numbers accepts both zeros as having the same arithmetic value: `+0.0 == -0.0`. If the contract must distinguish the **sign bit of zero**, add a check with `Double.doubleToRawLongBits`/`Float.floatToRawIntBits` after deciding how to match them; do not rely on `==` alone to enforce that.

### 8.3. Accepting error based on practical requirements

Not every application needs to preserve every `double` value verbatim. For display coordinates, sensor readings, or images, small errors may be acceptable; for finance, auditing, or identifier data, such rounding may be inappropriate.

A practical workflow:

1. Define the value range (e.g., `-1_000..1_000`) and required resolution (e.g., less than 0.0001 units).
2. Test casts at boundary points and representative values.
3. Compute error `Math.abs(original - (double) narrowed)` when both are finite, and compare against the business-defined error budget.
4. Near 0 or across multiple orders of magnitude, consider combining absolute and relative error criteria, avoiding division by 0.
5. Test full real-world operation chains, not just isolated casts.

Do not hardcode a single global epsilon for all problems. `Math.ulp` helps estimate the quantization step by magnitude, but the **final acceptance threshold must come from business requirements**.

## 9. Converting `String` and reading/writing data: do not confuse with casting

`Double.parseDouble("0.1")` returns the binary64 value nearest to 0.1; `Float.parseFloat("0.1")` returns the binary32 value nearest to 0.1. Both parse text and pick from the target type's representable value set.

```java
double d = Double.parseDouble("0.1");
float f = Float.parseFloat("0.1");

System.out.println(d); // 0.1
System.out.println(f); // 0.1
System.out.println((double) f); // 0.10000000149011612
```

The displayed string `"0.1"` is a **decimal representation** generated so that converting back to the corresponding type yields the same value; it does not mean the two types store the same binary number.

When you need to preserve exact decimal input from users (such as money), you can use:

```java
java.math.BigDecimal price = new java.math.BigDecimal("0.1");
```

`BigDecimal` is an exact decimal model at the declared value level, not a "more-bits `float`." `BigDecimal.valueOf(double)` has rules to convert from `double`'s decimal representation, yet it also cannot recover data that was previously cast down to `float`.

### `float` does not mean "less memory and always sufficient"

A `float[]` array has 32-bit elements, while `double[]` has 64-bit elements. This can be useful for huge datasets, graphics buffers, or storage protocols that mandate binary32. However, total memory also involves object overhead, alignment, and data structures. Saving space is an engineering trade-off balanced against error, not a reason to automatically narrow every calculation.

## 10. Standalone runnable Java 17+ program

Create the file `NarrowingDoubleToFloatDemo.java`:

```java
public class NarrowingDoubleToFloatDemo {
    public static void main(String[] args) {
        double d = 0.1d;
        float f = (float) d;
        double widened = f;

        System.out.println("Original double: " + d);
        System.out.println("Narrowed float: " + f);
        System.out.println("Widened again: " + widened);
        System.out.println("Round trip equal? " + (d == widened));

        double largeInteger = 16_777_217.0;
        float roundedInteger = (float) largeInteger;
        System.out.println("Integer original: " + largeInteger);
        System.out.println("Integer as float: " + roundedInteger);

        System.out.println("Float spacing near 1: " + Math.ulp(1.0f));
        System.out.println("Double spacing near 1: " + Math.ulp(1.0d));

        System.out.println("Overflow: " + (float) 1.0e40);
        System.out.println("Underflow: " + (float) 1.0e-50);
        float subnormal = (float) 1.0e-40;
        System.out.println("Subnormal: " + subnormal);

        float negativeZero = (float) -0.0d;
        System.out.println("Negative zero sign: " + (1.0f / negativeZero));
        System.out.println("NaN stays NaN? " + Float.isNaN((float) Double.NaN));

        double mixed = f + 0.2d;
        System.out.println("Mixed expression type double value: " + mixed);
    }
}
```

Compile and run:

```bash
javac --release 17 NarrowingDoubleToFloatDemo.java
java NarrowingDoubleToFloatDemo
```

Stdout:

```text
Original double: 0.1
Narrowed float: 0.1
Widened again: 0.10000000149011612
Round trip equal? false
Integer original: 1.6777217E7
Integer as float: 1.6777216E7
Float spacing near 1: 1.1920929E-7
Double spacing near 1: 2.220446049250313E-16
Overflow: Infinity
Underflow: 0.0
Subnormal: 1.0E-40
Negative zero sign: -Infinity
NaN stays NaN? true
Mixed expression type double value: 0.30000000149011613
```

The example demonstrates three independent phenomena: **reduced precision** (`0.1` and integer 16,777,217), **narrowed range** (infinity, zero, and subnormal), and **type-propagation rules** (adding with `double` still retains the existing `float` approximation). You can also test `1.25d` to see an exact conversion case.

## 11. Common errors and how to avoid them

| Mistake | Why it is wrong | How to handle |
| --- | --- | --- |
| Assuming `(float) d` only "renames the type" | `float` has only 24 significand bits | Determine allowable error; keep `double` if needed |
| Seeing both variables print `0.1` and concluding they are equal | `Float.toString` and `Double.toString` choose strings per type | Check widened-back value, bits, or error in context |
| Casting back `(double)(float)d` and thinking data was recovered | Widening does not restore lost bits | Keep the `double` source if still needed |
| Assuming casting an overly large value throws an exception | Large finite values can become `Infinity` | Check `Float.isFinite` and range limits |
| Assuming casting a tiny value stays nonzero | It can become subnormal or `0.0` | Check minimum threshold and error |
| Using `float` for large counters requiring unit exactness | Not every integer above `2^24` stays exact | Use `int`/`long` for integer counters |
| Using `==` to compare floating-point algorithm results with math expectations | Rounding makes different computation paths diverge | Choose tolerance criteria by units and range |
| Converting `double` down to `float` before computation and widening at the end | Error already entered at the intermediate step | Compute in `double` throughout the pipeline when needed |
| Thinking `float` suffices for money because "there are only two decimal places" | Decimals like 0.1 are not exact in binary32 | Use `BigDecimal` or integer units (cents) as appropriate |
| Overlooking `+=` accepting `double` on a `float` variable | Compound assignment performs implicit narrowing | Separate the calculation and explicit cast |
| Using `Float.MIN_VALUE` as the smallest negative value | It is the smallest positive subnormal number | Distinguish `MIN_VALUE`, `MIN_NORMAL`, `MAX_VALUE` |

## 12. Self-check questions

1. Why does `float f = d;` fail to compile for `double d`, while `float f = (float) d;` compiles?
2. Does `(double) (float) 0.1d` equal `0.1d`? Why can both print almost identically?
3. Why is `16_777_217.0d` not preserved after casting to `float`, while `16_777_216.0d` is preserved?
4. How does the difference between **precision** and **exponent range** show up when casting `1e40` and `1e-50` to `float`?
5. What does `Float.MIN_VALUE` represent? Is a subnormal `float` the same as zero?
6. When is the round-trip check `(double)(float) d == d` useful, and why must NaN or the sign of zero be handled separately if the contract requires it?
7. Why does `float f = (float) 0.1d; double x = f + 0.2d;` still carry error from `f` even though the addition expression has type `double`?
8. A measurement application accepts error below 0.01 units. What factors must be checked before storing `double` results into a `float[]`?

### Key takeaway

**Casting `double` to `float` is a rounding operation into the representable binary32 value set**, not a value-preserving conversion. Casting can cause the result to **lose precision, become ±Infinity or ±0.0, or land in the subnormal range** without throwing an exception. Keep `double` until the boundary where you genuinely must store/pass `float`, check ranges and error against business needs, and do not expect casting back up to `double` to recover lost information.
