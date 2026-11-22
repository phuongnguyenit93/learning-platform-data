# Converting Floating-Point to Integer and Fractional Truncation — Java 17+

## 1. Understanding the conversion accurately

In Java, casting a `float` or `double` value to `int` or `long` is a **narrowing primitive conversion**. For **finite** numbers within the target type's range, Java **discards the fractional part toward zero** (*truncate toward zero*).

~~~java
double price = 12.9;
int whole = (int) price;
System.out.println(whole); // 12

double adjustment = -12.9;
int negative = (int) adjustment;
System.out.println(negative); // -12
~~~

Do not confuse this cast with **rounding to the nearest integer**:

- `(int) 12.9` → `12`.
- `(int) -12.9` → `-12`.
- Negative numbers are not automatically rounded down to `-13`.
- Casting does not automatically validate whether the data has a fractional part or falls within application bounds.

**Core idea:** `(int) value` is a **type conversion**, not a customizable rounding function and not a data-safety validation mechanism.

## 2. Cast syntax: target type in parentheses

~~~java
double reading = 17.75;
int valueAsInt = (int) reading;
long valueAsLong = (long) reading;

System.out.println(valueAsInt);  // 17
System.out.println(valueAsLong); // 17
~~~

The `(int)` or `(long)` syntax tells the compiler that you explicitly request **converting the value**. If the source is a `double` variable, Java does not allow direct assignment to `int` without a cast:

~~~java
double reading = 17.75;
// int wrong = reading; // Compile error: possible lossy conversion
int correct = (int) reading;
~~~

Example table for **finite values fitting within the `int` range**:

| Source value | `(int)` | Explanation |
|---|---:|---|
| `12.9` | 12 | Drops fraction, moves toward 0 |
| `12.1` | 12 | Does not round up |
| `-12.9` | -12 | Not -13 |
| `-12.1` | -12 | Moves toward 0 |
| `0.99` | 0 | Integer part is 0 |
| `-0.99` | 0 | `int` has no negative zero |
| `12.0` | 12 | No fractional part |
| `-0.0` | 0 | Loses negative sign of zero when becoming `int` |

Here **truncating the fractional part** means for ordinary finite numbers: the result is an integer whose magnitude **does not exceed** the source's magnitude, unless range-clamping rules apply and require separate handling.

## 3. Truncation toward 0 differs from `floor`, `ceil`, `round`, and `rint`

Java has several APIs related to floating-point numbers, but they serve **different purposes**.

| Expression | Value | Rule |
|---|---:|---|
| `(int) 12.9` | `12` | Truncate toward 0 |
| `(int) -12.9` | `-12` | Truncate toward 0 |
| `Math.floor(12.9)` | `12.0` | Largest integer not exceeding source value |
| `Math.floor(-12.9)` | `-13.0` | Round down along the number line |
| `Math.ceil(12.1)` | `13.0` | Round up along the number line |
| `Math.ceil(-12.9)` | `-12.0` | Round up along the number line |
| `Math.round(12.5)` | `13` | Round according to `Math.round`'s rule |
| `Math.round(-12.5)` | `-12` | Halfway case toward +∞ |
| `Math.rint(12.5)` | `12.0` | Halfway chooses even integer |
| `Math.rint(13.5)` | `14.0` | Halfway chooses even integer |

**Return types also differ:**

- `(int) d` returns `int`; `(long) d` returns `long`.
- `Math.floor(double)`, `Math.ceil(double)`, and `Math.rint(double)` return **`double`**, even when the value has zero fractional part.
- `Math.round(double)` returns **`long`**; whereas `Math.round(float)` returns **`int`**.

Example:

~~~java
double value = -12.9;
System.out.println((int) value);       // -12
System.out.println(Math.floor(value)); // -13.0
System.out.println(Math.ceil(value));  // -12.0
~~~

**Do not pick an API just because its name sounds like “rounding”.** Explicitly determine whether business logic requires **truncation**, **flooring**, **ceiling**, or **nearest integer**.

## 4. Special cases: NaN, infinity, and out-of-range

Casting `double`/`float` to an integer type **does not throw an exception by default** on abnormal inputs. Java has mandatory rules:

1. **NaN** converts to `0`.
2. **Positive infinity** or a value too large in the positive direction converts to the **maximum value** of the target integer type.
3. **Negative infinity** or a value too small in the negative direction converts to the **minimum value** of the target integer type.
4. For finite values within the representable range, drop the fractional part toward 0.

~~~java
System.out.println((int) Double.NaN);               // 0
System.out.println((int) Double.POSITIVE_INFINITY); // 2147483647
System.out.println((int) Double.NEGATIVE_INFINITY); // -2147483648
System.out.println((int) 1.0e100);                  // 2147483647
System.out.println((long) 1.0e100);                 // 9223372036854775807
~~~

The values above belong to **narrowing conversion**, not a validity check. If an input is NaN and gets cast to 0, you cannot infer that the user actually provided 0.

### Decision flowchart for data requiring safe conversion

~~~mermaid
flowchart TD
    A["float / double value"] --> B{"Double.isFinite(value)?"}
    B -- "No" --> X["Reject or handle NaN / Infinity"]
    B -- "Yes" --> C{"Within target type range?"}
    C -- "No" --> Y["Reject or choose a wider type"]
    C -- "Yes" --> D{"Does business logic allow losing fraction?"}
    D -- "Yes" --> E["Cast (int) or (long): truncate toward 0"]
    D -- "No" --> F{"Is the value an integer?"}
    F -- "No" --> Z["Reject or apply rounding rule"]
    F -- "Yes" --> E
~~~

When working with financial data, quantities, or array indices, **do not treat NaN → 0 or Infinity → MAX_VALUE as a safe default**.

## 5. Exact `int` range: watch the upper bound when comparing with `double`

`int` has the range:

~~~text
Integer.MIN_VALUE = -2147483648
Integer.MAX_VALUE =  2147483647
~~~

When the source is `double`, an accurate and easy-to-reason-about check is:

~~~java
static boolean inIntInputRange(double value) {
    return Double.isFinite(value)
            && value >= -2147483648.0
            && value <  2147483648.0;
}
~~~

Use an **exclusive upper bound of `2147483648.0` (2³¹)**. Why not simply write `value <= Integer.MAX_VALUE` in every context? Mixed comparison converts `Integer.MAX_VALUE` to `double`; for `int` this remains exact, yet writing an exclusive upper bound clarifies the target type boundary and avoids inadvertently accepting an out-of-range value.

Understand the validation policy: `-2147483648.5` is a number whose truncated integer part would equal `Integer.MIN_VALUE`, but **the original input lies outside the integer value range**. The function above proactively rejects out-of-range values **before truncation**, so data errors are not masked.

`double` also represents the two bounds `-2147483648.0` and `2147483648.0` accurately, so this comparison is clear.

### The `long` range has a bigger trap

`Long.MAX_VALUE` equals `9223372036854775807`, yet **`double` cannot represent that integer accurately**. The `double` value of `Long.MAX_VALUE` when widened rounds up to **2⁶³**.

Therefore, **do not rely solely on `value <= Long.MAX_VALUE` to prove a `double` value falls within the `long` range**. A range check tailored to `double` itself is:

~~~java
static boolean inLongInputRange(double value) {
    return Double.isFinite(value)
            && value >= -0x1.0p63
            && value <   0x1.0p63;
}
~~~

`0x1.0p63` is a hexadecimal floating-point `double` literal representing exactly \(2^{63}\). The lower bound \(-2^{63}\) is allowed, while the upper bound \(2^{63}\) is excluded.

If the original data is a `long` integer, **do not take a detour through `double`** and hope to get every digit back accurately. Keep the data in an integer type when unit-level precision is required.

## 6. When dropping the fraction is allowed, but NaN and overflow must be rejected

Here is a function for cases where **truncating the fractional part is permitted**, but the input must be finite and within the `int` range:

~~~java
static int truncateIntChecked(double value) {
    if (!Double.isFinite(value)
            || value < -2147483648.0
            || value >= 2147483648.0) {
        throw new IllegalArgumentException("outside int input range");
    }
    return (int) value;
}
~~~

Example:

~~~java
System.out.println(truncateIntChecked(42.75)); // 42
System.out.println(truncateIntChecked(-42.75)); // -42
~~~

Values like `Double.NaN`, `Double.POSITIVE_INFINITY`, and `2147483648.0` will be **deliberately rejected** instead of silently turning into 0 or a clamped limit.

**Business characteristic:** this function allows losing the fractional part upon casting. If the requirement is “must be a true whole integer”, an additional check is needed before casting.

## 7. When losing the fractional part is not allowed

For example, an item quantity must be whole; receiving `42.75` and truncating it to 42 could be a business bug. Check as follows:

~~~java
static int requireWholeInt(double value) {
    if (!Double.isFinite(value)
            || value < -2147483648.0
            || value >= 2147483648.0
            || value != Math.rint(value)) {
        throw new IllegalArgumentException("not a finite whole int");
    }
    return (int) value;
}
~~~

`Math.rint(value)` returns a `double` rounded to the nearest integer using the round-half-to-even rule. Here we **do not use that result to alter the value**; we only use the comparison `value == Math.rint(value)` to verify that the source value is **already an integer**.

Example:

~~~java
System.out.println(requireWholeInt(42.0)); // 42
// requireWholeInt(42.5); // Throws IllegalArgumentException
~~~

**Beware prior error:** if a floating-point calculation was supposed to yield an integer but actually produced `41.99999999999999`, the exact check will reject it. This is not a bug in `Math.rint`, but a business requirement needing a decision on whether **to accept approximations with a tolerance or to use exact decimal arithmetic**. Never arbitrarily “cast whenever close to an integer” for critical data.

## 8. Further narrowing to `byte`, `short`, `char`

Converting from floating-point to a smaller integer type happens via **converting to `int` first and then narrowing further**. The behavior can differ greatly from simply dropping the fractional part.

~~~java
double input = 130.9;
byte asByte = (byte) input;
System.out.println(asByte); // -126
~~~

Two-step explanation:

1. `130.9` is converted to the `int` value `130`.
2. `130` is narrowed to `byte`, keeping the low 8 bits and interpreted as `-126`.

With `char`:

~~~java
double input = 65536.9;
char asChar = (char) input;
System.out.println((int) asChar); // 0
~~~

`65536.9` → `int` 65536 → `char` keeps low 16 bits, becoming 0.

**Do not confuse the two mechanisms:** truncating the fraction belongs to converting `float`/`double` to `int`/`long`; truncating low bits belongs to **further narrowing from `int` down to `byte`/`short`/`char`**. If business logic requires a valid `byte`/`short`/`char` value, validate against the range of the **final target type**.

## 9. Representation error can change the integer part before casting

`float` and `double` represent numbers in **binary** floating-point. A computed result can be slightly smaller or larger than an expected integer due to rounding error:

~~~java
double computed = 2.9999999999999996;
System.out.println(computed);       // 2.9999999999999996
System.out.println((int) computed); // 2
~~~

Even though a user might expect the mathematical result to be 3, Java **converts the exact stored value** and truncates toward 0, yielding 2.

Do not automatically apply `(int) (computed + 0.000001)` as a generic “fix trick”: it alters the data and can fail for negative numbers, boundary values, or different scales.

If rounding is needed, choose `Math.round`, `Math.floor`, `Math.ceil`, or an appropriate decimal rule. If exact decimal calculation is needed, consider `BigDecimal` or integers representing the smallest unit.

## 10. `BigDecimal` when business logic cannot accept error/implicit truncation

When the input value is inherently an **exact decimal** (for example, entering `"42.75"`), `BigDecimal` can clearly express the required behavior:

~~~java
java.math.BigDecimal value = new java.math.BigDecimal("42.75");

System.out.println(value.toBigInteger()); // 42: truncates fraction
// value.intValueExact(); // Throws ArithmeticException: not an integer
~~~

`toBigInteger()` returns the integer part by truncating the fraction toward 0. Meanwhile, `intValueExact()` requires no fractional loss and fitting within the `int` range; otherwise, it throws `ArithmeticException`.

~~~java
java.math.BigDecimal whole = new java.math.BigDecimal("42");
System.out.println(whole.intValueExact()); // 42
~~~

Do not write `new BigDecimal(0.1)` expecting the exact decimal value 0.1; the `double` constructor receives the previously rounded binary value. For decimal input data, use a decimal string or an equivalent intentional conversion mechanism.

**Decision point:** use casting when you **accept fractional truncation and have checked the range**, or use an exact API when **fractional loss must be rejected**.

## 11. Complete, runnable Java 17 program

Create the exact file **`FloatingToIntegerDemo.java`**:

~~~java
import java.math.BigDecimal;

public final class FloatingToIntegerDemo {
    private FloatingToIntegerDemo() {}

    static int truncateIntChecked(double value) {
        if (!Double.isFinite(value)
                || value < -2147483648.0
                || value >= 2147483648.0) {
            throw new IllegalArgumentException("outside int input range");
        }
        return (int) value;
    }

    static int requireWholeInt(double value) {
        if (!Double.isFinite(value)
                || value < -2147483648.0
                || value >= 2147483648.0
                || value != Math.rint(value)) {
            throw new IllegalArgumentException("not a finite whole int");
        }
        return (int) value;
    }

    public static void main(String[] args) {
        double positive = 12.9;
        double negative = -12.9;
        float small = 3.99f;

        System.out.println("positive int=" + (int) positive);
        System.out.println("negative int=" + (int) negative);
        System.out.println("positive long=" + (long) positive);
        System.out.println("negative long=" + (long) negative);
        System.out.println("small negative int=" + (int) -0.99);
        System.out.println("float int=" + (int) small);

        System.out.println("byte after double=" + (byte) 130.9);
        System.out.println("char after double=" + (int) (char) 65536.9);

        System.out.println("NaN int=" + (int) Double.NaN);
        System.out.println("+Infinity int="
                + (int) Double.POSITIVE_INFINITY);
        System.out.println("-Infinity int="
                + (int) Double.NEGATIVE_INFINITY);
        System.out.println("large int=" + (int) 1.0e100);
        System.out.println("large long=" + (long) 1.0e100);

        System.out.println("round positive half=" + Math.round(12.5));
        System.out.println("round negative half=" + Math.round(-12.5));
        System.out.println("floor negative=" + Math.floor(-12.9));
        System.out.println("ceil negative=" + Math.ceil(-12.9));
        System.out.println("rint even=" + Math.rint(12.5));
        System.out.println("rint odd=" + Math.rint(13.5));

        double computed = 2.9999999999999996;
        System.out.println("precision before cast=" + computed);
        System.out.println("precision after cast=" + (int) computed);

        System.out.println("checked truncate=" + truncateIntChecked(42.75));
        System.out.println("checked exact=" + requireWholeInt(42.0));

        try {
            requireWholeInt(42.75);
        } catch (IllegalArgumentException ex) {
            System.out.println("fraction rejected");
        }
        try {
            truncateIntChecked(Double.NaN);
        } catch (IllegalArgumentException ex) {
            System.out.println("NaN rejected");
        }
        try {
            truncateIntChecked(2147483648.0);
        } catch (IllegalArgumentException ex) {
            System.out.println("overflow rejected");
        }

        System.out.println("decimal whole="
                + new BigDecimal("42").intValueExact());
        try {
            new BigDecimal("42.75").intValueExact();
        } catch (ArithmeticException ex) {
            System.out.println("decimal fractional rejected");
        }
    }
}
~~~

Requires **JDK 17 or newer**, with the terminal placed in the directory containing the file.

**Bash (Linux/macOS):**

~~~bash
javac --release 17 -encoding UTF-8 FloatingToIntegerDemo.java
java -cp . FloatingToIntegerDemo
~~~

**PowerShell (Windows):**

~~~powershell
javac --release 17 -encoding UTF-8 .\FloatingToIntegerDemo.java
java -cp . FloatingToIntegerDemo
~~~

**Exact expected output:**

~~~text
positive int=12
negative int=-12
positive long=12
negative long=-12
small negative int=0
float int=3
byte after double=-126
char after double=0
NaN int=0
+Infinity int=2147483647
-Infinity int=-2147483648
large int=2147483647
large long=9223372036854775807
round positive half=13
round negative half=-12
floor negative=-13.0
ceil negative=-12.0
rint even=12.0
rint odd=14.0
precision before cast=2.9999999999999996
precision after cast=2
checked truncate=42
checked exact=42
fraction rejected
NaN rejected
overflow rejected
decimal whole=42
decimal fractional rejected
~~~

The program requires no Maven/Gradle or libraries outside the JDK. It prints no system-dependent exception messages; the error lines are explicitly defined by the code.

**Make sure to understand the groups of results:**

- Both signs of `12.9` prove **truncation toward 0**, not always “rounding down”.
- The NaN/infinity lines illustrate **language rules**, which does not mean those inputs should be accepted.
- `byte after double`/`char after double` happen through **two narrowing steps**.
- The `Math.round`, `Math.floor`, `Math.ceil`, and `Math.rint` lines show that casting **differs from rounding**.
- The two check functions demonstrate **two different contracts**: permitting fractional truncation or requiring an exact integer.

## 12. Common mistakes

| Error or assumption | Why is it wrong? | How to handle |
|---|---|---|
| `int n = doubleValue;` | `double` → `int` is narrowing, no implicit assignment | Cast intentionally and validate |
| Thinking `(int) -12.9` is -13 | Cast truncates toward 0 | Result is -12; use `Math.floor` for flooring |
| Thinking `(int) 12.9` is 13 | Cast does not round to nearest | Result is 12; see `Math.round` |
| Casting NaN to 0 and treating it as valid data | Casting does not validate | Use `Double.isFinite` |
| Casting positive Infinity to `int` yields max without error | Saturation rule | Reject infinite data if business logic requires |
| Using `(int) 1e100` to test range | Cast saturates at MAX_VALUE | Check bounds beforehand |
| Thinking `(byte) 130.9` gives 130 | Two narrowing steps produce -126 | Check `byte` range |
| Thinking `(int) 2.9999999999999996` gives 3 | No rounding occurs | Actual stored value leads to 2 |
| Thinking `double <= Long.MAX_VALUE` suffices to check `long` | `Long.MAX_VALUE` rounds up when converted to `double` | Use appropriate `±2^63` boundaries |
| Thinking `Math.round` always has the same rule as `Math.rint` | Different tie-breaking rules and return types | Pick the right API per requirement |
| Casting to `int` to drop fraction even when data must stay exact | Data loss without warning | `BigDecimal.intValueExact` or explicit validation |
| Using `new BigDecimal(double)` for exact decimal | Captures binary approximation of `double` | Create from decimal string when source data is decimal |

## 13. Exercises with answers

### Exercise A — positive and negative numbers

~~~java
System.out.println((int) 8.99);
System.out.println((int) -8.99);
System.out.println((int) -0.75);
~~~

**Answer:**

~~~text
8
-8
0
~~~

Casting drops the fractional part toward 0.

### Exercise B — flooring differs from truncation

~~~java
double x = -3.8;
System.out.println((int) x);
System.out.println(Math.floor(x));
~~~

**Answer:**

~~~text
-3
-4.0
~~~

### Exercise C — NaN and infinity

~~~java
System.out.println((int) Double.NaN);
System.out.println((int) Double.POSITIVE_INFINITY);
System.out.println((long) Double.NEGATIVE_INFINITY);
~~~

**Answer:**

~~~text
0
2147483647
-9223372036854775808
~~~

These values are dictated by narrowing rules. They do not prove the inputs are allowed as valid quantities.

### Exercise D — `byte` after converting from `double`

~~~java
double value = 255.9;
System.out.println((byte) value);
~~~

**Answer:** `-1`. First `255.9` becomes `int` 255, then signed `byte` -1.

### Exercise E — quantity must be an integer

You receive `double quantity = 7.25;` and **are not allowed to lose the fractional part**. Should you use `(int) quantity`?

**Answer:** No. The cast yields 7 and loses 0.25. Require the number to be finite, within the target type's range, and have a whole-number value before converting. For exact decimal sources, you can use `BigDecimal.intValueExact()`.

### Exercise F — checking `long` bounds from `double`

Why is comparing `value <= Long.MAX_VALUE` not a sufficiently safe way to confirm every `double` can convert to `long` with its exact value?

**Answer:** `Long.MAX_VALUE = 2^63-1` cannot be represented accurately by `double`; when converted to `double`, it rounds up to `2^63`. You need to check `value < 0x1.0p63` and `value >= -0x1.0p63`, along with checking finiteness; if no fractional loss is allowed, add the condition that the value is already an integer.

## 14. Checklist and conclusion

- [ ] Distinguish **casting to `int`/`long`** from **rounding**.
- [ ] Know `(int) 12.9 == 12`, `(int) -12.9 == -12`.
- [ ] Remember `Math.floor`/`ceil`/`round`/`rint` have different rules.
- [ ] Understand conversions NaN → 0, ±Infinity → target type limits.
- [ ] Know casting does not automatically throw an error when a floating-point value exceeds range.
- [ ] Check `Double.isFinite` before using data that must be finite.
- [ ] Understand why `long` bounds need to be compared against `±2^63` in `double`.
- [ ] Distinguish casting to `byte`/`short`/`char` from casting directly to `int`/`long`.
- [ ] Know floating-point approximation error can alter the integer part after casting.
- [ ] Choose validation functions that **allow fractional truncation** or **disallow fractional loss** based on requirements.
- [ ] Know `BigDecimal.intValueExact()` rejects data with a fractional part.
- [ ] Run `FloatingToIntegerDemo.java` with Java 17+ `javac`/`java` and verify each line.

**Conclusion:** Casting `float`/`double` to an integer in Java **truncates the fractional part toward 0** when a finite value is in range. For NaN, infinity, or out-of-range data, Java applies special conversion rules without automatically treating them as business errors. Clearly choose whether you need **truncation**, **rounding**, or **exact conversion**, and validate the data before casting.