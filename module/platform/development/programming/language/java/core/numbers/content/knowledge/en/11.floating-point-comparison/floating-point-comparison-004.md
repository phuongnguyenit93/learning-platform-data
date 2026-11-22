# `+0.0` and `-0.0` with the `==` Operator in Java

In Java, the two floating-point values `+0.0` (positive zero) and `-0.0` (negative zero) are **equal under the arithmetic comparison operator `==`**:

```java
System.out.println(+0.0 == -0.0);  // true
System.out.println(0.0f == -0.0f);  // true
```

However, they **do not have the same bit representation** and **cannot be substituted for each other in every operation**. For example:

```java
System.out.println(1.0 / +0.0); // Infinity
System.out.println(1.0 / -0.0); // -Infinity
```

The key takeaway of this lesson is distinguishing **arithmetic equality**, **representation identity**, and **object API equality** such as `Double.equals` or `Double.compare`. These three concepts yield different results for signed zero.

## 1. Why Does Zero Have a Sign?

Java uses IEEE 754 binary floating-point for `float` and `double`. A floating-point value has a separate **sign bit** in addition to its exponent and significand. Thus, `0.0` and `-0.0` are two distinct valid bit patterns:

| Type | `+0.0` (hex bit pattern) | `-0.0` (hex bit pattern) |
| --- | --- | --- |
| `float` (32-bit) | `0x00000000` | `0x80000000` |
| `double` (64-bit) | `0x0000000000000000` | `0x8000000000000000` |

In both types, the significand and exponent are 0; only the sign bit differs. Normally, `0.0` written without a sign is positive zero; the expression `-0.0` produces negative zero.

```java
double positiveZero = 0.0;
double negativeZero = -0.0;

System.out.println(positiveZero); // 0.0
System.out.println(negativeZero); // -0.0
```

Java having two zeros does not mean it has two integer values of 0. The types `byte`, `short`, `int`, and `long` have no separate negative zero: the integer expression `-0` has the exact same representation and value `0`. Signed zero is a property of `float`/`double`.

### The Sign of Zero Can Arise from Calculations

Negative zero does not only come from writing a literal. For instance, a very small negative value can **underflow** to `-0.0` when the result is too close to 0:

```java
double verySmallNegative = -Double.MIN_VALUE;
double roundedToNegativeZero = verySmallNegative / 2.0;
// -0.0
```

`Double.MIN_VALUE` is the smallest positive `double` greater than 0, not the negative value with the largest magnitude. Therefore, `-Double.MIN_VALUE` is a very small negative value; dividing it further by 2 rounds to negative zero.

## 2. `==` Treats `+0.0` and `-0.0` as Equal

For primitive floating-point operands, Java applies **floating-point equality** rules. Under these rules, `+0.0` and `-0.0` are considered **equal**, whereas `NaN` is not equal to any value, including itself.

```java
double a = +0.0;
double b = -0.0;

System.out.println(a == b); // true
System.out.println(a != b); // false
System.out.println(a < b);  // false
System.out.println(a > b);  // false
System.out.println(a <= b); // true
System.out.println(a >= b); // true
```

In an arithmetic comparison context, both zeros sit at the same position at the origin of the number line. `==` **does not check the sign bit**; it answers whether two numeric values are equal under Java's operator rules.

Summary table:

| Expression | Result | Meaning |
| --- | --- | --- |
| `+0.0 == -0.0` | `true` | Equal arithmetically |
| `+0.0 != -0.0` | `false` | Not considered different |
| `-0.0 < +0.0` | `false` | Not less under numeric comparison |
| `-0.0 <= +0.0` | `true` | Equal |
| `Double.NaN == Double.NaN` | `false` | Special NaN rule |

Pay attention to **operand types**. `0.0` is a `double` literal, while `0.0f` is a `float` literal. If you compare `+0.0f == -0.0`, the `float` operand is widened to `double` and then compared; the result is still `true`.

## 3. Arithmetic Equality Does Not Mean Identical Bits

You can inspect the bits of `double` and `float` using dedicated methods:

```java
long pos = Double.doubleToRawLongBits(+0.0);
long neg = Double.doubleToRawLongBits(-0.0);

System.out.println(Long.toHexString(pos)); // 0
System.out.println(Long.toHexString(neg)); // 8000000000000000
System.out.println(pos == neg);            // false
```

For `float`:

```java
int pos = Float.floatToRawIntBits(+0.0f);
int neg = Float.floatToRawIntBits(-0.0f);

System.out.println(Integer.toHexString(pos)); // 0
System.out.println(Integer.toHexString(neg)); // 80000000
```

`Double.doubleToRawLongBits` and `Float.floatToRawIntBits` are very useful when debugging bit representations, binary protocols, or numerical bugs. For signed zero, both the methods with and without `Raw` distinguish the sign; the key difference of the `Raw` version is that it preserves NaN bit patterns instead of canonicalizing NaN.

**Do not confuse** the two types of comparisons:

```java
double x = +0.0;
double y = -0.0;

boolean equalAsNumbers = x == y; // true
boolean sameBitPattern =
        Double.doubleToRawLongBits(x) == Double.doubleToRawLongBits(y); // false
```

If business logic only needs to compare numeric values, using `==` is usually appropriate for zero. If business logic needs to distinguish the sign of zero (for example in scientific computing), you must choose an appropriate check.

## 4. Why Does `1.0 / +0.0` Differ from `1.0 / -0.0`?

IEEE 754 floating-point division **uses the sign of zero**. When the numerator is finite and non-zero, and the denominator is zero, the result is infinity with the corresponding sign.

| Division | Result |
| --- | --- |
| `1.0 / +0.0` | `Infinity` |
| `1.0 / -0.0` | `-Infinity` |
| `-1.0 / +0.0` | `-Infinity` |
| `-1.0 / -0.0` | `Infinity` |
| `+0.0 / +0.0` | `NaN` |
| `-0.0 / +0.0` | `NaN` |

Therefore:

```java
double x = +0.0;
double y = -0.0;

System.out.println(x == y);  // true
System.out.println(1.0 / x); // Infinity
System.out.println(1.0 / y); // -Infinity
```

**No contradiction:** `==` asks whether two numbers have equal numeric values; division has a rule that uses the sign bit to select the sign of infinity. Two values can be equal under one comparison relation while affecting another operation differently.

For `int` or `long`, division by 0 throws `ArithmeticException` at runtime. Merely assigning an expression to a `double` target variable does not turn integer division into floating-point division:

```java
int numerator = 1;
int denominator = 0;
// double invalid = numerator / denominator; // at runtime: ArithmeticException
double floating = (double) numerator / denominator; // Infinity
```

This is an **illustrative snippet**, not a standalone program. Be sure to cast one operand to `double` **before** dividing to select floating-point division rules.

## 5. `Double.compare` and `Double.equals` Distinguish the Sign of Zero

This is the most surprising detail when moving from primitives to the `Double` wrapper:

```java
System.out.println(Double.compare(-0.0, +0.0)); // -1
System.out.println(Double.compare(+0.0, -0.0)); // 1

System.out.println(Double.valueOf(-0.0)
        .equals(Double.valueOf(+0.0))); // false
```

`Double.compare` establishes a consistent ordering for sorting floating-point numbers under wrapper rules; it treats **`-0.0` as coming before `+0.0`**. `Double.equals` defines equality based on the wrapper's canonicalized bit representation, so it **does not treat two zeros of opposite signs as equal**.

| Check method | `-0.0` vs. `+0.0` |
| --- | --- |
| Primitive `a == b` | `true` |
| Primitive `a != b` | `false` |
| `Double.compare(a, b) == 0` | `false` |
| `Double.valueOf(a).equals(Double.valueOf(b))` | `false` |
| Bit comparison with `Double.doubleToLongBits` | Different |

`Double.compare` returns a negative number, 0, or a positive number depending on the ordering; do not build algorithms that assume all non-zero results from other comparators must strictly equal `-1` or `1` as a general rule.

### Why Do Wrappers Need a Different Interpretation?

`Double.equals` and `Double.hashCode` have contracts suited for data structures like `HashMap` or `HashSet`. The Java wrapper chooses to distinguish signed zeros as two separate keys, while handling NaN consistently across `equals` and `compare`.

```java
java.util.Set<Double> values = new java.util.HashSet<>();
values.add(+0.0);
values.add(-0.0);
System.out.println(values.size()); // 2
```

Whereas primitive `+0.0 == -0.0` evaluates to `true`, a `HashSet<Double>` can hold both elements and treat them as **two distinct keys**. This is a real consequence when storing computed results in collections.

### Do Not Use `==` Between Two `Double` Objects to Compare Values

`==` on **two object references** asks whether they point to the same object, which is completely different from `==` on primitive `double`:

```java
Double first = Double.valueOf(+0.0);
Double second = Double.valueOf(-0.0);

// first == second: compares reference identity, not numeric equality
boolean primitiveEqual = first.doubleValue() == second.doubleValue(); // true
boolean objectEqual = first.equals(second); // false
```

Do not interpret the result of `first == second` as a signed-zero rule: that is a question about **object identity**. The fact that Java performs autoboxing/unboxing in some contexts does not mean comparing two wrapper references always unboxes them.

## 6. `Float` Has Similar Rules to `Double`

For `float`:

```java
float a = +0.0f;
float b = -0.0f;

System.out.println(a == b);                  // true
System.out.println(Float.compare(a, b));      // 1
System.out.println(Float.valueOf(a).equals(
        Float.valueOf(b)));                   // false
```

`Float.compare(-0.0f, +0.0f)` returns a negative number; `Float.compare(+0.0f, -0.0f)` returns a positive number. Therefore, when using a `List<Float>` and sorting it, negative zero can appear before positive zero even though `==` considers them equal.

Another note: `Double.NaN == Double.NaN` returns `false`, whereas `Double.compare(Double.NaN, Double.NaN) == 0` and `Double.valueOf(Double.NaN).equals(Double.valueOf(Double.NaN))` both return `true`. Wrappers define equality for collections and sorting, which does not completely match the arithmetic `==` operator.

## 7. `Math.copySign`, `Math.abs`, `Math.min`, and `Math.max`

To detect or preserve the sign of zero when needed, Java provides useful APIs.

### `Math.copySign`: Reading the Sign of Zero Without Bit Comparison

`Math.copySign(magnitude, sign)` returns a value with **magnitude from the first argument** and **sign from the second argument**.

```java
System.out.println(Math.copySign(1.0, +0.0)); // 1.0
System.out.println(Math.copySign(1.0, -0.0)); // -1.0
```

If you only need to check whether a zero is positive or negative, applying `Math.copySign(1.0, zero)` can be easy to read. This approach is used when you already know the analyzed variable is zero; avoid assuming every negative value encountered is negative zero.

### `Math.abs` Can Strip the Negative Zero Sign

```java
System.out.println(Math.abs(-0.0));  // 0.0
```

The result is positive zero. If the sign of zero is meaningful in an algorithm, taking the absolute value discards that information.

### `Math.min` and `Math.max` Handle Signed Zero Specifically

According to Java rules:

```java
System.out.println(Math.min(+0.0, -0.0)); // -0.0
System.out.println(Math.max(+0.0, -0.0)); // 0.0
```

`Math.min` chooses `-0.0` when given two zeros of opposite signs; `Math.max` chooses `+0.0`. Thus, you cannot assume every API treats signed zero the same way `==` does.

Additional note: when NaN is passed to `Math.min`/`Math.max`, the result can be NaN; when finding min/max from external data, consider your NaN-handling policy.

## 8. Cases That Produce Negative Zero and When to Keep It

Signed zero has value in certain numerical problems:

- **Underflow:** a very small negative result can round to `-0.0`, preserving the sign of the tiny value before rounding.
- **Multiplication/division:** operand signs determine the sign of zero or infinity in the result.
- **Mathematical functions:** some operations and library functions can use signed zero to select the sign of a result or preserve one-sided limit information.

Examples:

```java
double underflow = -Double.MIN_VALUE / 2.0; // -0.0
double fromProduct = -2.0 * 0.0;            // -0.0
double reciprocal = 1.0 / fromProduct;      // -Infinity
```

If a system automatically converts every `-0.0` to `+0.0`, the two values remain equal under `==`, yet certain subsequent calculations can produce different results.

In ordinary systems where zero simply means zero, distinguishing the sign may be unnecessary. **It depends on the data's purpose**: not every program should replace `==` with bit comparisons.

## 9. Designing Comparisons, Sorting, and Collection Keys

When working with signed zero, choose **one consistent rule**.

| Goal | Typical approach | Consequence |
| --- | --- | --- |
| Only ask if two primitive values are arithmetically equal? | `a == b` | `+0.0` equals `-0.0`; NaN does not equal itself |
| Need to distinguish zero's sign bit | `Double.doubleToRawLongBits(a) == Double.doubleToRawLongBits(b)` | The two zeros differ |
| Need ordering compatible with wrapper `Double` | `Double.compare(a,b)` | `-0.0` comes before `+0.0` |
| Need to use `Double` as a map/set key | `Double.equals`/`hashCode` as used by collections | Two zeros of opposite signs are treated as two keys |
| Need to treat both zeros as one key | **Normalize** `x == 0.0 ? 0.0 : x` before using as key | Intentionally loses sign distinction |
| Need to preserve zero's sign across processing | Keep primitives/raw bits or suitable data structures | Avoid losing sign via normalization or `abs` |

Example of normalizing before storing a `Double` in a set:

```java
static double normalizeZero(double x) {
    return x == 0.0 ? 0.0 : x;
}
```

This method is a **snippet to place inside a class**, not a standalone program. It converts both `-0.0` and `+0.0` to `+0.0`, while leaving all other numbers unchanged. For `NaN`, the condition `x == 0.0` is `false`, so the NaN value is returned unchanged. This is an **intentional policy** to treat signed zeros as equivalent keys, not built-in behavior of `Double.equals`.

If using a `TreeSet<Double>`, the default ordering based on wrapper comparison also distinguishes the two zeros; when using a custom comparator for an ordered set, the comparator must be consistent with the definition of "duplicate" desired by the application.

## 10. Complete Java 17+ Program

Save to **`SignedZeroEqualityDemo.java`**:

```java
import java.util.HashSet;
import java.util.Set;

public class SignedZeroEqualityDemo {
    public static void main(String[] args) {
        double positive = +0.0;
        double negative = -0.0;

        System.out.println("primitiveEquals=" + (positive == negative));
        System.out.println("primitiveNotEquals=" + (positive != negative));
        System.out.println("negativeLess=" + (negative < positive));
        System.out.println("negativeLessOrEqual=" + (negative <= positive));

        System.out.println("positiveText=" + positive);
        System.out.println("negativeText=" + negative);
        System.out.println("positiveBits=" +
                Long.toHexString(Double.doubleToRawLongBits(positive)));
        System.out.println("negativeBits=" +
                Long.toHexString(Double.doubleToRawLongBits(negative)));
        System.out.println("rawBitsEqual=" +
                (Double.doubleToRawLongBits(positive)
                        == Double.doubleToRawLongBits(negative)));

        System.out.println("reciprocalPositive=" + (1.0 / positive));
        System.out.println("reciprocalNegative=" + (1.0 / negative));
        System.out.println("zeroOverZero=" + (positive / negative));

        System.out.println("compareNegativePositive=" +
                Double.compare(negative, positive));
        System.out.println("comparePositiveNegative=" +
                Double.compare(positive, negative));
        System.out.println("wrapperEquals=" +
                Double.valueOf(negative).equals(Double.valueOf(positive)));

        Set<Double> set = new HashSet<>();
        set.add(positive);
        set.add(negative);
        System.out.println("setSize=" + set.size());

        System.out.println("copySignPositive=" + Math.copySign(1.0, positive));
        System.out.println("copySignNegative=" + Math.copySign(1.0, negative));
        System.out.println("absNegative=" + Math.abs(negative));
        System.out.println("minZero=" + Math.min(positive, negative));
        System.out.println("maxZero=" + Math.max(positive, negative));

        System.out.println("floatEquals=" + (+0.0f == -0.0f));
        System.out.println("negativeFloatBits=" +
                Integer.toHexString(Float.floatToRawIntBits(-0.0f)));
        System.out.println("negativeUnderflow=" +
                (-Double.MIN_VALUE / 2.0));

        System.out.println("nanPrimitiveEquals=" + (Double.NaN == Double.NaN));
        System.out.println("nanWrapperCompare=" +
                Double.compare(Double.NaN, Double.NaN));
    }
}
```

Compile and run with JDK 17 or later:

```bash
javac SignedZeroEqualityDemo.java
java SignedZeroEqualityDemo
```

Exact output:

```text
primitiveEquals=true
primitiveNotEquals=false
negativeLess=false
negativeLessOrEqual=true
positiveText=0.0
negativeText=-0.0
positiveBits=0
negativeBits=8000000000000000
rawBitsEqual=false
reciprocalPositive=Infinity
reciprocalNegative=-Infinity
zeroOverZero=NaN
compareNegativePositive=-1
comparePositiveNegative=1
wrapperEquals=false
setSize=2
copySignPositive=1.0
copySignNegative=-1.0
absNegative=0.0
minZero=-0.0
maxZero=0.0
floatEquals=true
negativeFloatBits=80000000
negativeUnderflow=-0.0
nanPrimitiveEquals=false
nanWrapperCompare=0
```

The line `primitiveEquals=true` next to `rawBitsEqual=false` clearly illustrates the difference between **arithmetic value comparison** and **bit representation comparison**. The lines `compareNegativePositive=-1`, `wrapperEquals=false`, and `setSize=2` demonstrate that wrapper APIs do not share the same equality rules as primitive `==`.

## 11. Common Mistakes and Checklist

| Misconception | Correct explanation |
| --- | --- |
| "`+0.0 == -0.0` is `false` because the sign bits differ." | False: `==` compares arithmetically and gives `true`. |
| "`+0.0` and `-0.0` behave identically in every way." | False: `1.0 / ±0.0` produces infinities of opposite signs; other APIs also distinguish them. |
| "`Double.compare(+0.0,-0.0) == 0` because `==` returns `true`." | False: `Double.compare` orders `-0.0` before `+0.0`. |
| "`Double.valueOf(+0.0).equals(Double.valueOf(-0.0))` returns `true`." | False: `Double.equals` distinguishes the sign of zero. |
| "`HashSet<Double>` definitely has only one element if both zeros are added." | False: it can hold two distinct keys according to `equals`. |
| "`Float` does not have negative zero." | False: `-0.0f` has a sign bit and corresponding rules. |
| "If Java prints `-0.0`, its value is less than 0 under `<`." | False: `-0.0 < +0.0` evaluates to `false`. |
| "`Math.abs(-0.0)` preserves negative zero." | False: it returns `+0.0`. |
| "`Double.NaN == Double.NaN` is the same as `Double.compare(NaN,NaN) == 0`." | False: the `==` operator gives `false`, whereas `Double.compare` gives `0`. |
| "Comparing two `Double` objects with `==` compares numeric values." | False: two wrapper references compared with `==` check identity, unless an unboxing context applies. |

When handling signed zero, check:

1. **Are you comparing primitives or objects?** `==` on `double`/`float` treats both zeros as equal; `==` on two wrapper references checks identity.
2. **Do you want to compare arithmetic values or stored bits?** Choose `==` or `doubleToRawLongBits`/`floatToRawIntBits` accordingly.
3. **Are you sorting or using collection keys?** Understand that `Double.compare`, `Double.equals`, and `hashCode` distinguish signed zero.
4. **Does zero's sign matter in subsequent operations?** Check division, `Math.copySign`, underflow, and functions with sign rules.
5. **Does the application want to merge the two zeros?** Normalize explicitly before storing and comparing in data structures, rather than assuming collections automatically use primitive `==`.

**Remember:** `+0.0 == -0.0` is **`true`** for primitive `float`/`double`. However, their **sign bits differ**, division by zero yields **infinities of opposite signs**, and `Double.compare`/`Double.equals` **distinguish the two zero values**. Always choose the comparison rule that fits your program's goal.
