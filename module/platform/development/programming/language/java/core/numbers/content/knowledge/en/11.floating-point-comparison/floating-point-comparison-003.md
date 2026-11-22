# Float.isNaN, Double.isNaN, isInfinite, and isFinite in Java

## 1. Why Classify Floating-Point Values?

In Java, `float` and `double` follow IEEE 754 binary floating-point representation. Besides finite values, they also have special values:

- **NaN** (*Not a Number*): represents a result that is not a normal real number, such as `0.0 / 0.0`.
- **+Infinity**: positive infinity, such as `1.0 / 0.0`.
- **-Infinity**: negative infinity, such as `-1.0 / 0.0`.
- **Finite values**: ordinary numbers (including +0.0, -0.0, subnormal numbers, and very large numbers that are still finite).

To check each category properly, Java provides three groups of static methods on both wrapper classes:

| Method | When does it return `true`? | Does not return `true` for |
|---|---|---|
| `Float.isNaN(float)` / `Double.isNaN(double)` | The value is NaN | ±Infinity, all finite numbers |
| `Float.isInfinite(float)` / `Double.isInfinite(double)` | The value is +Infinity or -Infinity | NaN, all finite numbers |
| `Float.isFinite(float)` / `Double.isFinite(double)` | A finite value, including ±0 and subnormal numbers | NaN, +Infinity, -Infinity |

These methods return a `boolean` and **do not modify** the checked number. If a `double` has already become NaN or infinity from a previous computation step, calling `isFinite` only detects that state; the method does not fix the result on its own.

Short example:

```java
double a = 12.5;
double b = 0.0 / 0.0;
double c = 1.0 / 0.0;

System.out.println(Double.isFinite(a));   // true
System.out.println(Double.isNaN(b));      // true
System.out.println(Double.isInfinite(c)); // true
```

**Point to remember:** a value belongs to exactly one of the three categories **NaN**, **infinity**, or **finite**. The sign of Infinity can be determined separately by comparing with `Double.POSITIVE_INFINITY` and `Double.NEGATIVE_INFINITY` (or the corresponding constants on `Float`).

## 2. Floating-Point Differs from Integers in Division by Zero

In integer arithmetic, dividing by 0 with the `/` operator throws `ArithmeticException`:

```java
// int bad = 1 / 0; // if executed, throws ArithmeticException
int numerator = 1;
int denominator = 0;
// int result = numerator / denominator; // at runtime: ArithmeticException
```

For `float`/`double`, division by 0 follows floating-point rules:

```java
double positiveInfinity = 1.0 / 0.0; // Infinity
double negativeInfinity = -1.0 / 0.0; // -Infinity
double notANumber = 0.0 / 0.0;       // NaN
```

These are values that can be stored in a `double` variable; **floating-point division does not automatically throw `ArithmeticException` because of a 0.0 denominator**.

NaN can also arise from operations that have no finite real-number result:

```java
double a = Math.sqrt(-1.0); // NaN
double b = Double.POSITIVE_INFINITY
         + Double.NEGATIVE_INFINITY; // NaN
double c = Double.POSITIVE_INFINITY * 0.0; // NaN
```

Infinity can arise from finite operations that **overflow the floating-point range**:

```java
double tooLarge = Double.MAX_VALUE * 2.0; // Infinity
float alsoTooLarge = Float.MAX_VALUE * 2.0f; // Infinity
```

Conversely, very small numbers can **underflow** to 0.0 or remain subnormal numbers; both are still **finite** according to `isFinite`.

## 3. NaN: Why Not Use `==` to Check for It?

NaN has special comparison rules. Under Java's floating-point comparison operators:

- `NaN == NaN` returns **false**, even when both sides are the exact same variable.
- `NaN != NaN` returns **true**.
- `NaN < x`, `NaN <= x`, `NaN > x`, and `NaN >= x` are all **false** for every floating-point value `x`, including NaN.

Example:

```java
double x = Double.NaN;

System.out.println(x == x); // false
System.out.println(x != x); // true
System.out.println(x < 0);  // false
System.out.println(x > 0);  // false
```

Therefore, the correct, clear, and reliable way to detect NaN is:

```java
boolean invalid = Double.isNaN(x);
```

Do not write:

```java
// boolean invalid = (x == Double.NaN); // always false
```

Sometimes you will see the `x != x` trick to detect NaN. This trick works for primitive floating-point numbers by the rules above, but **`Double.isNaN(x)` states the intent clearly**, is easier to read, and is less error-prone.

### NaN Propagates Through Operations

For ordinary floating-point addition/subtraction/multiplication/division, if one operand is NaN, the result is usually also NaN:

```java
double x = Double.NaN;
System.out.println(Double.isNaN(x + 1.0)); // true
System.out.println(Double.isNaN(x * 0.0)); // true
```

Do not apply this single rule mechanically to **every math API**: each `Math` method has its own contract for special cases. When you need to ensure valid input data, check `isFinite` **before** passing it into a calculation chain.

## 4. Infinity: Has Both Positive and Negative Signs

`Float.isInfinite` and `Double.isInfinite` return `true` for **both signs**:

```java
double plus = Double.POSITIVE_INFINITY;
double minus = Double.NEGATIVE_INFINITY;

System.out.println(Double.isInfinite(plus));  // true
System.out.println(Double.isInfinite(minus)); // true
System.out.println(Double.isNaN(plus));       // false
```

When you need to distinguish the sign:

```java
if (value == Double.POSITIVE_INFINITY) {
    // value is positive infinity
} else if (value == Double.NEGATIVE_INFINITY) {
    // value is negative infinity
}
```

This is an **illustrative code snippet** assuming a `double value` variable declared in an appropriate scope, not a standalone program.

With arithmetic comparison operators:

- `Double.POSITIVE_INFINITY > Double.MAX_VALUE` is `true`.
- `Double.NEGATIVE_INFINITY < -Double.MAX_VALUE` is `true`.
- Infinity is not NaN, and is not a finite number.

**Common mistake:** checking `!Double.isNaN(value)` and concluding that the value is finite. This is **wrong** because ±Infinity is not NaN.

## 5. isFinite: Checking Whether a Value Is Finite

`Double.isFinite(value)` is semantically equivalent to:

```java
!Double.isNaN(value) && !Double.isInfinite(value)
```

Similarly:

```java
Float.isFinite(value)
```

is equivalent to:

```java
!Float.isNaN(value) && !Float.isInfinite(value)
```

Examples:

```java
System.out.println(Double.isFinite(100.0)); // true
System.out.println(Double.isFinite(0.0)); // true
System.out.println(Double.isFinite(-0.0)); // true
System.out.println(Double.isFinite(Double.MIN_VALUE)); // true
System.out.println(Double.isFinite(Double.MAX_VALUE)); // true

System.out.println(Double.isFinite(Double.NaN)); // false
System.out.println(Double.isFinite(Double.POSITIVE_INFINITY)); // false
System.out.println(Double.isFinite(Double.NEGATIVE_INFINITY)); // false
```

**`Double.MIN_VALUE` is not the smallest negative number!** This constant is the **smallest positive non-zero** representable number (a subnormal number). `-Double.MAX_VALUE` is near the lowest negative finite bound. Confusing floating-point `MIN_VALUE` with integer `Integer.MIN_VALUE` is a very common bug.

The same applies to `Float.MIN_VALUE` and `Float.MAX_VALUE`.

### Distinguishing "Finite" from "Business-Valid"

`Double.isFinite(1.0e300)` is `true`, even though that number may be far too large for an amount of money, a weight, or a product quantity. `isFinite` **only excludes NaN and infinity**; it does not check for positivity, does not check min/max bounds, and does not assert that the number has the desired decimal precision.

To ensure a number is in the interval [0, 100], you need **both finiteness and bounds**:

```java
boolean valid = Double.isFinite(value)
        && value >= 0.0
        && value <= 100.0;
```

If an exact integer is required, you must also check the fractional part and data precision, not just `isFinite`.

## 6. Runnable Program: Full Classification

Create the file `FloatingClassificationDemo.java`:

```java
public class FloatingClassificationDemo {
    public static void main(String[] args) {
        double[] values = {
                0.0,
                -0.0,
                Double.MIN_VALUE,
                Double.MAX_VALUE,
                Double.POSITIVE_INFINITY,
                Double.NEGATIVE_INFINITY,
                Double.NaN
        };
        String[] labels = {
                "+0.0", "-0.0", "MIN_VALUE", "MAX_VALUE",
                "+Infinity", "-Infinity", "NaN"
        };

        for (int i = 0; i < values.length; i++) {
            double x = values[i];
            System.out.printf(
                    "%s: NaN=%b, Infinite=%b, Finite=%b%n",
                    labels[i],
                    Double.isNaN(x),
                    Double.isInfinite(x),
                    Double.isFinite(x));
        }

        float f = 3.5f;
        System.out.println("Float 3.5 finite: " + Float.isFinite(f));
        System.out.println("Float NaN: " + Float.isNaN(Float.NaN));
        System.out.println("Float +Infinity: "
                + Float.isInfinite(Float.POSITIVE_INFINITY));
    }
}
```

Compile and run with Java 17+:

```bash
javac FloatingClassificationDemo.java
java FloatingClassificationDemo
```

Exact output:

```text
+0.0: NaN=false, Infinite=false, Finite=true
-0.0: NaN=false, Infinite=false, Finite=true
MIN_VALUE: NaN=false, Infinite=false, Finite=true
MAX_VALUE: NaN=false, Infinite=false, Finite=true
+Infinity: NaN=false, Infinite=true, Finite=false
-Infinity: NaN=false, Infinite=true, Finite=false
NaN: NaN=true, Infinite=false, Finite=false
Float 3.5 finite: true
Float NaN: true
Float +Infinity: true
```

The `+` sign in `+0.0` or `+Infinity` in the label column is text supplied by the `labels` array, not a sign automatically added by `printf`. The three boolean columns are the actual API check results.

## 7. Comparing NaN and the Two ±0.0 Values

Besides NaN, floating-point numbers also have **+0.0** and **-0.0**. These two values are equal under the `==` operator but differ in their sign bit:

```java
double a = 0.0;
double b = -0.0;

System.out.println(a == b);          // true
System.out.println(1.0 / a);         // Infinity
System.out.println(1.0 / b);         // -Infinity
System.out.println(Double.isFinite(a)); // true
System.out.println(Double.isFinite(b)); // true
```

Both zeros are **finite**; `isNaN` and `isInfinite` both return false.

### `Double.compare` and `Double.equals` Have Different Rules from `==`

For primitives, `NaN == NaN` is false. However, when using `Double.compare` or the wrapper's `Double.equals` method, Java establishes an ordering/equality relation **designed to work consistently with sorting and collections**:

- `Double.compare(Double.NaN, Double.NaN)` returns **0**.
- `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` returns **true**.
- `Double.compare(+0.0, -0.0)` returns a **positive number**.
- `Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` returns **false**.

This is not a contradiction: primitive `==` applies the IEEE 754 arithmetic relation, while `compare`/`equals` are specified specifically for wrappers. When comparing for business purposes, you must know clearly whether you want **arithmetic comparison** or **distinguishing special representations**.

Illustrative program:

```java
public class FloatingComparisonDemo {
    public static void main(String[] args) {
        double nan = Double.NaN;

        System.out.println("NaN == NaN: " + (nan == nan));
        System.out.println("NaN != NaN: " + (nan != nan));
        System.out.println("NaN < 0: " + (nan < 0.0));
        System.out.println("NaN > 0: " + (nan > 0.0));
        System.out.println("Double.isNaN: " + Double.isNaN(nan));
        System.out.println("Double.compare(NaN, NaN): "
                + Double.compare(nan, Double.NaN));
        System.out.println("Double.equals(NaN): "
                + Double.valueOf(nan).equals(Double.valueOf(Double.NaN)));

        System.out.println("+0.0 == -0.0: " + (0.0 == -0.0));
        System.out.println("Double.compare(+0, -0): "
                + Double.compare(0.0, -0.0));
        System.out.println("Double.equals(+0, -0): "
                + Double.valueOf(0.0).equals(Double.valueOf(-0.0)));
    }
}
```

Save to `FloatingComparisonDemo.java`, compile, and run:

```bash
javac FloatingComparisonDemo.java
java FloatingComparisonDemo
```

Output:

```text
NaN == NaN: false
NaN != NaN: true
NaN < 0: false
NaN > 0: false
Double.isNaN: true
Double.compare(NaN, NaN): 0
Double.equals(NaN): true
+0.0 == -0.0: true
Double.compare(+0, -0): 1
Double.equals(+0, -0): false
```

If the goal is to **detect NaN**, you should still call `Double.isNaN`/`Float.isNaN`, rather than trying to check via wrapper `equals` or bit comparisons.

## 8. A Range-Check Expression Can Let NaN Slip Through

This is an important logic bug. Look at checking whether a value must be in the range 0 to 100:

```java
double value = Double.NaN;

boolean outside = value < 0.0 || value > 100.0;
System.out.println(outside); // false
```

Because **every relational comparison with NaN is false**, `outside` becomes false. If the application only rejects a value when `outside == true`, NaN will **slip through** as a value that is "not out of range," even though it is actually invalid.

Safe approach:

```java
boolean accepted = Double.isFinite(value)
        && value >= 0.0
        && value <= 100.0;
```

Or if you want to check the rejection condition:

```java
boolean rejected = !Double.isFinite(value)
        || value < 0.0
        || value > 100.0;
```

By checking `isFinite` first, both NaN and ±Infinity are excluded. The short-circuit behavior of `&&`/`||` makes the validation steps clear in the expression; it is not because comparing NaN throws an exception (it does not).

If you only check `value >= 0.0 && value <= 100.0`, NaN is also excluded because both comparisons are false. However, adding `isFinite` **expresses the requirement directly** and avoids bugs when refactoring expressions into a "not outside the domain" form.

## 9. Classify Before or After Converting from `double` to `float`?

`double` has a wider magnitude range than `float`. A number that is finite as a `double` can become Infinity after narrowing to `float`:

```java
double big = 1.0e40;
float narrowed = (float) big;

System.out.println(Double.isFinite(big));  // true
System.out.println(Float.isFinite(narrowed));  // false
System.out.println(Float.isInfinite(narrowed)); // true
```

Similarly, a very small `double` value can be rounded to `0.0f` when converted to `float`. Zero is still finite, but magnitude information has been lost.

Therefore, place checks **at the appropriate data boundaries**:

- If an API accepts `double` and requires finite `double` data, check `Double.isFinite` upfront.
- If the API **must store the value as `float`**, also check **`Float.isFinite` after conversion** when Infinity is not permitted in the destination.
- If you need to prevent precision loss from casting or rounding, use other checks; `isFinite` is not enough to prove data was preserved accurately.

### Short Conversion Example

```java
double finiteDouble = 1.0e40;
float overflowedFloat = (float) finiteDouble;

System.out.println("double finite: "
        + Double.isFinite(finiteDouble));
System.out.println("float finite: "
        + Float.isFinite(overflowedFloat));
System.out.println("float infinite: "
        + Float.isInfinite(overflowedFloat));
```

Output:

```text
double finite: true
float finite: false
float infinite: true
```

This is an **illustrative snippet placed inside a Java method** (without a standalone class/`main`). It emphasizes that you should not check once on the source type and assume every subsequent conversion is safe.

## 10. Validating String Input and APIs Before Computing

Some Java floating-point parsing APIs can accept strings representing special values, such as `"NaN"`, `"Infinity"`, and `"-Infinity"`. Therefore, successful parsing does **not** mean the data is finite.

Designing a parse method that accepts **only finite numbers**:

```java
static double parseFiniteDouble(String text) {
    double value = Double.parseDouble(text);
    if (!Double.isFinite(value)) {
        throw new IllegalArgumentException("non-finite number");
    }
    return value;
}
```

`Double.parseDouble` can throw `NumberFormatException` on syntactically invalid strings; the method above uses `IllegalArgumentException` to reject parsed input that is non-finite. If the input comes from a user, translate these errors into appropriate UI/API messages instead of exposing raw stack traces.

### Runnable Program

Create the file `FiniteInputDemo.java`:

```java
public class FiniteInputDemo {
    static double parseFiniteDouble(String text) {
        double value = Double.parseDouble(text);
        if (!Double.isFinite(value)) {
            throw new IllegalArgumentException("non-finite number");
        }
        return value;
    }

    public static void main(String[] args) {
        String[] samples = {
                "1.25", "0", "NaN", "Infinity", "-Infinity",
                "1e309", "abc"
        };

        for (String text : samples) {
            try {
                double value = parseFiniteDouble(text);
                System.out.println(text + " -> accepted: " + value);
            } catch (NumberFormatException e) {
                System.out.println(text + " -> invalid format");
            } catch (IllegalArgumentException e) {
                System.out.println(text + " -> non-finite");
            }
        }
    }
}
```

Compile and run:

```bash
javac FiniteInputDemo.java
java FiniteInputDemo
```

Output:

```text
1.25 -> accepted: 1.25
0 -> accepted: 0.0
NaN -> non-finite
Infinity -> non-finite
-Infinity -> non-finite
1e309 -> non-finite
abc -> invalid format
```

The string `"1e309"` has valid scientific notation syntax, but its magnitude exceeds the finite range of `double` and is parsed as +Infinity. Therefore, you must validate **after parsing**, not only validate string syntax.

If the value is a unit price, percentage, time interval, or a quantity with a defined domain, add range validation **after** the `isFinite` step.

## 11. Notes on `null`, Wrappers, and Missing Data

The methods `Float.isNaN(float)`, `Double.isNaN(double)`, `isInfinite`, and `isFinite` take **primitives**, not `null` values directly. If you pass a nullable wrapper variable, Java will **unbox** it first:

```java
Double nullable = null;

// boolean ok = Double.isFinite(nullable);
// will throw NullPointerException when unboxing null
```

Do not confuse "missing data" with "NaN":

- **`null`** is a reference pointing to no object, usable with `Double`/`Float`.
- **`Double.NaN`/`Float.NaN`** is a special floating-point value, **not null**.
- **Infinity** is also a special floating-point value, not null.

A safe check with an explicit policy:

```java
static boolean isPresentAndFinite(Double value) {
    return value != null && Double.isFinite(value);
}
```

This is an **illustrative method snippet**, placed inside a class. Thanks to `&&` short-circuiting, when `value == null`, Java does not evaluate the right-hand side and thus does not unbox null.

If missing data must be treated as a required-input error, do not silently turn null into 0.0; distinguish missing-data errors from non-finite-value errors for accurate handling.

## 12. isFinite Is Not an Accuracy Checker

A finite `double` number can still carry error due to binary representation:

```java
double sum = 0.1 + 0.2;
System.out.println(sum);                 // 0.30000000000000004
System.out.println(Double.isFinite(sum)); // true
System.out.println(sum == 0.3);          // false
```

`Double.isFinite(sum)` returns true because `sum` is neither NaN nor Infinity; it does **not** prove `sum` equals 0.3 under bit comparison or intended decimal representation.

For floating-point numbers, an approximate comparison check can use an **error threshold appropriate to the application domain** when the goal is comparing nearby computed results. Using only a fixed threshold without considering magnitude can fail for many problems.

When handling money or decimals that require exactness under business rules, consider `BigDecimal` with an appropriate decimal source and an explicit rounding policy. `BigDecimal` has no concept of NaN or Infinity like `double`; therefore, certain special input conversions must be rejected.

Additionally, `-0.0` is finite but differs from `+0.0` in its sign bit; if an algorithm involves reciprocals or representation preservation, consider the sign of zero.

## 13. Detecting Invalid Results After Operations

Even if all inputs are finite, the result is **not guaranteed** to stay finite. Multiplication/addition can overflow, or an indeterminate operation can produce NaN:

```java
double a = Double.MAX_VALUE;
double b = 2.0;

double product = a * b; // +Infinity
System.out.println(Double.isFinite(a)); // true
System.out.println(Double.isFinite(b)); // true
System.out.println(Double.isFinite(product)); // false
```

Therefore, in critical calculations, check finiteness at **meaningful boundaries**: when receiving input, after operations that can produce special values, and before storing/returning results if the API contract forbids such values.

Example business function that accepts only finite results:

```java
static double multiplyFinite(double a, double b) {
    if (!Double.isFinite(a) || !Double.isFinite(b)) {
        throw new IllegalArgumentException("non-finite input");
    }
    double result = a * b;
    if (!Double.isFinite(result)) {
        throw new ArithmeticException("non-finite product");
    }
    return result;
}
```

This is an **illustrative method**, placed inside a class for use. It catches NaN and Infinity, though it does not prevent every issue: the result can still **underflow to 0** or have **rounding error** while remaining finite. If those cases also matter, you must add further validation rules.

## 14. Common Mistakes

| Misconception | Actual result | How to handle it |
|---|---|---|
| `x == Double.NaN` checks for NaN | Always false | Use `Double.isNaN(x)` |
| `x != Double.NaN` means not NaN | Always true, even when x is NaN | Use `!Double.isNaN(x)` |
| `!isNaN(x)` means finite | Infinity is not NaN | Use `isFinite(x)` |
| `isInfinite(x)` distinguishes infinity sign | Returns true for both ±Infinity | Compare with the corresponding signed constant if needed |
| `x < min || x > max` rejects all bad data | NaN makes both sides false | Use `!isFinite(x) || x < min || x > max` |
| `isFinite` rejects huge numbers | `Double.MAX_VALUE` is still finite | Check business bounds |
| `isFinite` detects precision loss | Rounding errors are still finite | Check accuracy according to the goal |
| Checking finite `double` is enough before casting to `float` | Cast can produce Infinity | Check `Float.isFinite` after cast |
| `Double.MIN_VALUE` is the smallest negative number | It is the smallest positive non-zero number | Use `-Double.MAX_VALUE` for the finite negative bound |
| Successful parsing means a normal number | Can parse NaN/Infinity | Check `isFinite` after parsing |
| `Double.isFinite(nullWrapper)` returns false | Unboxing null throws NPE | Check `wrapper != null` first |
| Finite inputs guarantee finite output | Operations can overflow or produce NaN | Check the result when needed |

## 15. Self-Check Exercises

**Question 1.** What is `Double.isNaN(0.0 / 0.0)`?  
**Answer:** `true`.

**Question 2.** What are `Double.isInfinite(1.0 / 0.0)` and `Double.isInfinite(-1.0 / 0.0)`?  
**Answer:** Both are `true` because the method detects both signs of infinity.

**Question 3.** Is `Double.isFinite(Double.NaN)` true?  
**Answer:** No, it is `false`.

**Question 4.** Is `Double.isFinite(Double.MIN_VALUE)` true?  
**Answer:** Yes. `MIN_VALUE` is the smallest positive subnormal number, and it is still finite.

**Question 5.** Why does `double x = Double.NaN; x == x` return false?  
**Answer:** By floating-point comparison rules, NaN is not equal to any value, including itself, when using primitive `==`.

**Question 6.** Can `value < 0 || value > 100` be used to reject every invalid value?  
**Answer:** No. NaN makes both comparisons false. You must check `!Double.isFinite(value)` or verify both finiteness and domain membership.

**Question 7.** What is `Double.compare(Double.NaN, Double.NaN)`?  
**Answer:** 0. `compare` is for wrapper ordering/comparison, which differs from the primitive `==` relation.

**Question 8.** Is `+0.0 == -0.0` true, and what is `isFinite` for them?  
**Answer:** `==` is true; both are finite. They still have different sign bits.

**Question 9.** If `double x = 1e40` and then `float y = (float) x`, what do `Double.isFinite(x)` and `Float.isFinite(y)` return?  
**Answer:** True and false, respectively, because `x` is finite as a `double` while `y` becomes Infinity as a `float`.

**Question 10.** Is passing `Double nullable = null` to `Double.isNaN(nullable)` safe?  
**Answer:** No. Java needs to unbox it to `double` and will throw `NullPointerException`.

**Question 11.** Is `double x = 0.1 + 0.2` finite, and is it guaranteed to equal `0.3` via `==`?  
**Answer:** Finite, but `x == 0.3` is false in Java because `x` is 0.30000000000000004.

**Question 12.** Do two finite `double` operands guarantee a finite product?  
**Answer:** No. `Double.MAX_VALUE * 2.0` gives Infinity; check the result if the application requires a finite value.

## 16. Summary and References

- **`isNaN(x)`**: accurately detects the NaN case.
- **`isInfinite(x)`**: detects +Infinity and -Infinity.
- **`isFinite(x)`**: true only when x is neither NaN nor ±Infinity.
- **Do not use `==` to detect NaN**; `<`, `>`, `<=`, and `>=` with NaN are all false.
- **Finite does not mean valid or accurate**: you still need to check domain bounds, error tolerance, null policy, and post-operation results.
- **`float` and `double` have different ranges**; a finite `double` can become Infinity when cast to `float`.

Official API references: [Float — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Float.html), [Double — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Double.html), and [Java Language Specification — Floating-Point Operations](https://docs.oracle.com/javase/specs/jls/se17/html/jls-15.html).
