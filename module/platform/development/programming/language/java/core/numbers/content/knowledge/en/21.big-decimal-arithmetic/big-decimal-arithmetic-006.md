# `negate`, `abs`, `plus`, `min`, `max`, and `signum` in `BigDecimal`

## 1. Goals and Context

In Java, BigDecimal represents decimal numbers with arbitrary precision, suitable when you need control over digits and rounding behavior (such as currency). This group of methods serves two different purposes:

- **Affecting sign or absolute value:** negate(), abs(), plus().
- **Determining sign or selecting a number by order:** signum(), min(BigDecimal), max(BigDecimal).

These are methods of java.math.BigDecimal. They **do not mutate the original object** because BigDecimal is an immutable type. The result is a BigDecimal value or, specifically for signum(), an int integer.

BigDecimal stores its value in the form unscaledValue × 10^(-scale). For example, -12.340 has scale = 3. The two numbers 2.0 and 2.00 have equal arithmetic values but different scales; this affects the representational result when using min/max.

## 2. Quick Reference Table

| Method | Meaning | Result | Key characteristic |
| --- | --- | --- | --- |
| negate() | Negates x to -x | BigDecimal | Preserves scale of x |
| abs() | Absolute value | BigDecimal | Negative becomes positive; zero and positive keep their value |
| plus() | Unary plus +x | BigDecimal | Does not add 1; does not change value or scale |
| min(y) | Selects the smaller value between x and y | BigDecimal | Based on compareTo(); when equal, returns x (the receiver object) |
| max(y) | Selects the larger value between x and y | BigDecimal | Based on compareTo(); when equal, returns x (the receiver object) |
| signum() | Determines the sign of x | int | -1 if negative, 0 if zero, 1 if positive |

In the table above, x is the BigDecimal receiving the method call; y is the other BigDecimal argument. min() and max() do not have overloads accepting MathContext.

## 3. `negate()`, `abs()`, `plus()`: Three Unary Operations

- **x.negate()** returns the opposite value of x. Positive becomes negative, negative becomes positive; for 0, the arithmetic sign remains 0.
- **x.abs()** returns the non-negative magnitude of x. You can think of it as x when x is non-negative, or x.negate() when x is negative.
- **x.plus()** is unary plus, like the mathematical meaning of +x. It is most useful when used with MathContext to apply precision/rounding.

The three zero-argument methods preserve scale, including zeros with fractional places. For example, -12.340.negate() yields 12.340 rather than automatically simplifying to 12.34.

### Java 17 Example: Flipping Sign and Preserving Original Data

Save as BigDecimalUnaryDemo.java:

~~~java
import java.math.BigDecimal;

public class BigDecimalUnaryDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("-12.340");

        System.out.println("x       = " + x);
        System.out.println("negate  = " + x.negate());
        System.out.println("abs     = " + x.abs());
        System.out.println("plus    = " + x.plus());
        System.out.println("signum  = " + x.signum());
        System.out.println("scale   = " + x.scale());
        System.out.println("x after = " + x);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac BigDecimalUnaryDemo.java
java BigDecimalUnaryDemo
~~~

Output:

~~~text
x       = -12.340
negate  = 12.340
abs     = 12.340
plus    = -12.340
signum  = -1
scale   = 3
x after = -12.340
~~~

The last statement shows the calls did not modify x. Do not use the unary minus operator or Math.abs(x) with BigDecimal; call negate() and abs() directly.

### Zero and Representation

~~~java
import java.math.BigDecimal;

public class BigDecimalZeroDemo {
    public static void main(String[] args) {
        BigDecimal z = new BigDecimal("-0.00");
        System.out.println(z);               // 0.00
        System.out.println(z.negate());      // 0.00
        System.out.println(z.abs());         // 0.00
        System.out.println(z.signum());      // 0
        System.out.println(z.scale());       // 2
        System.out.println(z.compareTo(BigDecimal.ZERO)); // 0
    }
}
~~~

BigDecimal does not maintain a separate arithmetically meaningful negative sign for zero. The input string "-0.00" becomes the value 0.00 with scale 2; signum() still returns 0. If you only need to detect whether a number equals 0, use signum() == 0 or compareTo(BigDecimal.ZERO) == 0; do not compare display strings.

## 4. `signum()`: Branching by Sign Without Losing Precision

signum() returns exactly three states:

| Value | signum() result | Meaning |
| --- | ---: | --- |
| -0.001 | -1 | Negative |
| 0, 0.00, -0.00 | 0 | Zero |
| 0.001 | 1 | Positive |

Use it when business logic branches on negative/zero/positive, such as classifying balance changes:

~~~java
import java.math.BigDecimal;

public class BigDecimalSignDemo {
    static String describe(BigDecimal amount) {
        return switch (amount.signum()) {
            case -1 -> "decrease";
            case 0 -> "unchanged";
            case 1 -> "increase";
            default -> throw new IllegalStateException("Unexpected sign");
        };
    }

    public static void main(String[] args) {
        System.out.println(describe(new BigDecimal("-7.50")));
        System.out.println(describe(new BigDecimal("0.00")));
        System.out.println(describe(new BigDecimal("7.50")));
    }
}
~~~

Output:

~~~text
decrease
unchanged
increase
~~~

signum() is not a rounding operation and does not depend on scale. Do not infer digit count, magnitude, or original text sign from the -1/0/1 result.

## 5. `min()` and `max()`: Comparing Arithmetic Values

With x.min(y), the method returns the smaller value; with x.max(y), it returns the larger value. Both use BigDecimal's natural ordering, i.e., the result of compareTo().

Specific selection rules:

- If x.compareTo(y) < 0, x.min(y) returns x and x.max(y) returns y.
- If x.compareTo(y) > 0, x.min(y) returns y and x.max(y) returns x.
- If x.compareTo(y) == 0, **both x.min(y) and x.max(y) return x**, even when the scales of x and y differ.

### Java 17 Example: Ordering and Scale

Save as BigDecimalMinMaxDemo.java:

~~~java
import java.math.BigDecimal;

public class BigDecimalMinMaxDemo {
    public static void main(String[] args) {
        BigDecimal a = new BigDecimal("2.0");
        BigDecimal b = new BigDecimal("2.00");
        BigDecimal c = new BigDecimal("3.5");

        System.out.println("min(a,c) = " + a.min(c));
        System.out.println("max(a,c) = " + a.max(c));
        System.out.println("compare  = " + a.compareTo(b));
        System.out.println("equals   = " + a.equals(b));
        System.out.println("min(a,b) = " + a.min(b));
        System.out.println("min(b,a) = " + b.min(a));
        System.out.println("max(a,b) = " + a.max(b));
    }
}
~~~

Run:

~~~bash
javac BigDecimalMinMaxDemo.java
java BigDecimalMinMaxDemo
~~~

Output:

~~~text
min(a,c) = 2.0
max(a,c) = 3.5
compare  = 0
equals   = false
min(a,b) = 2.0
min(b,a) = 2.00
max(a,b) = 2.0
~~~

**Common point of confusion:** compareTo() treats 2.0 and 2.00 as arithmetically equal; equals() also considers scale and thus returns false. min/max select according to compareTo(), not equals(). When equal, the operand on the left determines the representation/scale of the result. Therefore, the result of min(a,b) may display differently from min(b,a) despite having the same value.

min/max do not automatically round, do not change the scale of the selected BigDecimal, and do not add/subtract the two numbers. To clamp a value to the interval [lower, upper] when lower <= upper, you can use x.max(lower).min(upper); define the scale policy upfront if the result will be stored or displayed in a fixed format.

## 6. Overloads Accepting `MathContext`

negate(MathContext), abs(MathContext), and plus(MathContext) have overloads that allow **applying precision and rounding rules**. They return the corresponding result rounded according to MathContext. MathContext controls **significant digits**, which is not synonymous with digits after the decimal point; to fix fractional digits, usually use setScale() with an appropriate RoundingMode.

~~~java
import java.math.BigDecimal;
import java.math.MathContext;
import java.math.RoundingMode;

public class BigDecimalContextDemo {
    public static void main(String[] args) {
        BigDecimal x = new BigDecimal("-123.4567");
        MathContext mc = new MathContext(4, RoundingMode.HALF_UP);

        System.out.println("original    = " + x);
        System.out.println("plus(mc)    = " + x.plus(mc));
        System.out.println("negate(mc)  = " + x.negate(mc));
        System.out.println("abs(mc)     = " + x.abs(mc));
        System.out.println("exact abs   = " + x.abs());
    }
}
~~~

Output:

~~~text
original    = -123.4567
plus(mc)    = -123.5
negate(mc)  = 123.5
abs(mc)     = 123.5
exact abs   = 123.4567
~~~

Here 4 is **precision = 4 significant digits**; the next digit is 5 so HALF_UP rounds. Without MathContext, the three unary operations preserve the original precision. With MathContext.UNLIMITED (precision = 0), no rounding is requested. RoundingMode.UNNECESSARY with a precision that is not large enough can raise ArithmeticException if the result requires rounding.

Specifically, plus(mc) does not mean adding any positive number: it applies unary plus and then rounds according to mc. Using MathContext for monetary calculations must adhere to actual business rounding rules.

## 7. Application Scenario: Handling Balances and Limits

Suppose an adjustment has a negative sign indicating money leaving an account. We can:

1. Use signum() to classify the direction of change.
2. Use abs() to display the magnitude of the adjustment.
3. Use negate() to create the opposite-sign value for a reversal entry (when business rules allow).
4. Use min()/max() to enforce arithmetic thresholds.

~~~java
import java.math.BigDecimal;

public class BigDecimalBusinessDemo {
    public static void main(String[] args) {
        BigDecimal change = new BigDecimal("-125.50");
        BigDecimal lower = new BigDecimal("-100.00");
        BigDecimal upper = new BigDecimal("100.00");

        BigDecimal limited = change.max(lower).min(upper);

        System.out.println("sign    = " + change.signum());
        System.out.println("display = " + change.abs());
        System.out.println("reverse = " + change.negate());
        System.out.println("limited = " + limited);
        System.out.println("source  = " + change);
    }
}
~~~

Output:

~~~text
sign    = -1
display = 125.50
reverse = 125.50
limited = -100.00
source  = -125.50
~~~

This snippet illustrates value transformations, **not executing a financial transaction itself**. The example also shows that clamping only bounds the number; choosing thresholds and creating reversal entries must belong to business rules. When data needs 2 decimal digits, standardize scale/rounding at input, storage, and output boundaries rather than assuming min/max always return scale 2.

## 8. Common Mistakes and How to Avoid Them

1. **Confusing plus() with add().** x.plus() keeps the value of x; to add two BigDecimals use x.add(y). Similarly, negate() only flips the sign, whereas x.subtract(y) subtracts two numbers.
2. **Using primitive operators.** BigDecimal does not directly support +, -, <, >, or Math.abs(BigDecimal). Use add/subtract/compareTo/abs/negate per the API.
3. **Confusing equality comparison with equals().** x.equals(y) can be false when scales differ; x.compareTo(y) == 0 checks equality by arithmetic value. min/max use compareTo().
4. **Assuming min/max normalize data.** When two values are equal, they pick the receiver operand; they do not coerce scale. If normalization is needed, apply setScale(...) per its own rule.
5. **Creating BigDecimal via new BigDecimal(0.1).** The double constructor preserves the exact binary value of the approximation, which can produce unexpectedly long decimals. For decimal constants, use new BigDecimal("0.1") or BigDecimal.valueOf(0.1).
6. **Passing null as an argument.** x.min(null) or x.max(null) causes NullPointerException. Ensure x and the argument are valid BigDecimals before calling.
7. **Confusing MathContext precision with scale.** new MathContext(4) generally limits 4 significant digits, not 4 fractional digits. Do not round arbitrarily if original precision is still needed.
8. **Assuming flipping sign mutates the source variable.** BigDecimal is immutable; you must save the result, e.g., x = x.negate(), when you actually want variable x to point to the object with the new value.
9. **Checking for negative numbers via strings.** signum() handles even 0.00 properly; checking if a string starts with '-' is not a reliable arithmetic sign check.

## 9. Self-Check

**Question 1.** With x = new BigDecimal("-0.000"), what is x.signum()? What is x.abs().scale()?

**Answer:** 0 and 3. BigDecimal takes the value zero, preserving scale 3 when calling the zero-argument abs().

**Question 2.** Given a = new BigDecimal("1.0"), b = new BigDecimal("1.00"). Do a.min(b) and b.min(a) display the same?

**Answer:** a.min(b) is 1.0, b.min(a) is 1.00. compareTo() equals 0 so the receiver operand is returned.

**Question 3.** To change -9.25 to 9.25, which method should you use? If x is already positive, does abs() make x negative?

**Answer:** Both x.negate() and x.abs() give 9.25 when x = -9.25, though their meanings differ; abs() never makes a positive number negative.

**Question 4.** What is the difference between new BigDecimal("12.3456").plus() and .plus(new MathContext(4, RoundingMode.HALF_UP))?

**Answer:** plus() keeps 12.3456; the overload taking MathContext rounds it to 12.35 (4 significant digits).

## 10. Takeaways

- **negate()** flips the sign; **abs()** takes the non-negative magnitude; **plus()** keeps the value (or applies rounding when passing MathContext).
- **signum()** returns -1/0/1 for exact sign checks.
- **min()/max()** choose according to compareTo(); when equal, return the receiver operand and preserve its representation.
- BigDecimal is immutable, scale is meaningful, and rounding must be specified explicitly when needed.

Refer to the standard API in the Java SE 17 documentation: java.math.BigDecimal, java.math.MathContext, and java.math.RoundingMode.